#!/usr/bin/env python3
"""One-command driver for the self-fix pipeline — the procedure as code.

Interactive agents can be talked out of following instructions (a skill is
advisory text in their context, on equal footing with the user's wishes and
whatever the processed content says). This driver removes the agent from
procedure execution entirely: routing, gates, bounded loops and verification
are plain code. An LLM is consulted only through bounded single-purpose calls
(probe-input generation, and the measurements inside spec_holes) — none of
which can skip a step, because the steps are not theirs to execute.

usage:
  fix.py draft.txt [inputs.json] [URL] [--run] [-k K]
             [--model M] [--api openai|anthropic] [--key KEY]
  inputs.json: code task = array of argument tuples / otherwise = the target
  documents (array of strings). Required for extraction/contract tasks;
  auto-generated for code tasks when omitted. Endpoint resolution: explicit URL
  > $PROBE_BASE > first of localhost:8000/8002/8003 that answers.

  Tool-requiring tasks (Jira/MCP/browse keywords) are auto-routed to
  run_agent.py --fix; its disposable children run with permissions bypassed by
  default. Set WEAK_LLM_AGENT_TOOLS=pat1,pat2 to use an allowlist instead, and
  WEAK_LLM_AGENT_CMD to override the agent command (default: claude; e.g.
  claude-local to run children on a local model).

exit codes: 0 = done (prompt fixed; with --run also executed and verified)
            1 = not delegable / gate failed / verification failed
            2 = infrastructure error (endpoint, files)
            3 = out of scope (no route)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from llm_client import LLMClient, detect_model
from spec_holes import canon, has_ja

TOOL_WORDS = ["mcp", "jira", "confluence", "github", "slack", "ブラウザ", "browser",
              "インターネット", "クロール", "crawl", "スクレイピ", "scrape", "アクセスして"]
CODE_WORDS = ["関数", "実装", "コード", "スクリプト", "def ", "function", "implement",
              "code", "script", "sql"]


def needs_tools(draft):
    low = draft.lower()
    return next((w for w in TOOL_WORDS if w in low), None)


def looks_like_code(draft):
    low = draft.lower()
    return any(w in low for w in CODE_WORDS)


def materialize_draft(arg):
    """引数がファイルならそのまま使い、生テキストならファイル化する。
    (path, text, inline) を返す。.txt/.md 風の実在しないパスはタイポとして拒否
    (打ち間違いを黙ってプロンプト扱いしない)。"""
    if os.path.isfile(arg):
        try:
            return arg, open(arg).read().strip(), False
        except OSError as e:
            print(f"!! cannot read draft: {e}"); sys.exit(2)
    if arg.endswith((".txt", ".md", ".json")):
        print(f"!! draft file not found: {arg}"); sys.exit(2)
    d = tempfile.mkdtemp(prefix="fix-")
    path = os.path.join(d, "draft.txt")
    open(path, "w").write(arg.strip() + "\n")
    print(f"[draft] inline text → {path}")
    return path, arg.strip(), True


def discover_base(cli_base):
    """接続先の自動解決: 明示 > $PROBE_BASE > 既知ポートの疎通確認。"""
    if cli_base:
        return cli_base
    env = os.environ.get("PROBE_BASE")
    if env:
        return env
    for p in (8000, 11434, 8002, 8003):  # vLLM/llama.cpp convention, ollama, spares
        base = f"http://localhost:{p}"
        try:
            urllib.request.urlopen(base + "/v1/models", timeout=2)
            print(f"[endpoint] {base}")
            return base
        except Exception:
            continue
    print("NO ENDPOINT: no model server answered on :8000/:11434/:8002/:8003 — "
          "set PROBE_BASE or pass a URL")
    sys.exit(2)


def route_agent(draft_path, word, k):
    """ツール必須タスクを run_agent.py --fix に転送する(子は既定で権限バイパス)。
    子の起動コマンドは run_agent 側が解決する($WEAK_LLM_AGENT_CMD > claude。
    環境は継承されるので、claude-local等のセッション内なら既定のままで「自分自身」)。
    許可リストに絞りたい場合は WEAK_LLM_AGENT_TOOLS=pat1,pat2。"""
    print(f"[route] agent (tool task: matched '{word}') → run_agent.py "
          "(children run with permissions bypassed by default)")
    cmd = [sys.executable, os.path.join(HERE, "run_agent.py"), draft_path, "--fix"]
    tools = os.environ.get("WEAK_LLM_AGENT_TOOLS", "")
    if tools and tools != "bypass":
        for pat in tools.split(","):
            cmd += ["--allowed", pat.strip()]
    if k:
        cmd += ["-k", str(k)]
    sys.exit(subprocess.run(cmd).returncode)


def run_tool(script, *a):
    sp = subprocess.run([sys.executable, os.path.join(HERE, script)] + [str(x) for x in a],
                        capture_output=True, text=True)
    out = (sp.stdout or "") + (sp.stderr or "")
    print(out, end="" if out.endswith("\n") else "\n")
    return sp


def gen_code_inputs(client, task):
    """コードタスクのプローブ入力をLLMに1回分ずつ書かせる(有界・パース失敗は再試行)。"""
    ja = has_ja(task)
    p = task + ("\n\nこの仕様の関数に対して、境界・空・同点・0・負数を突くテスト入力"
                "(引数の組)を6個、JSON配列の配列だけで出力してください。"
                "例: [[[3,1,2],2],[[],0]]。コードや説明は不要、JSONのみ。" if ja else
                "\n\nFor the function in this spec, output 6 test inputs (argument tuples) "
                "probing boundaries, empty, ties, zero and negatives, as a JSON array of "
                "arrays only. Example: [[[3,1,2],2],[[],0]]. No code or prose, JSON only.")
    for t in (0.0, 0.5, 0.9):
        raw = client.chat(p, temperature=t, max_tokens=400)
        m = re.search(r"\[\s*\[.*\]\s*\]", raw, re.S)
        if not m:
            continue
        try:
            cand = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(cand, list) and cand and all(isinstance(x, list) for x in cand):
            return cand
    return None


def clean_inputs(data, kind):
    """機械的な事前整形: 重複除去、(json) 空文書除去。"""
    seen, out = set(), []
    for x in data:
        if kind == "json" and not str(x).strip():
            continue
        c = canon(x)
        if c in seen:
            continue
        seen.add(c)
        out.append(x)
    return out


def parse_added_inputs(gate_stdout):
    """check_inputs の FAIL 出力からコピペ可能な提案入力を機械回収する。"""
    adds = []
    for line in gate_stdout.splitlines():
        if line.strip().startswith("[MISSING]") and "add: " in line:
            try:
                adds.append(json.loads(line[line.find("add: ") + 5:]))
            except ValueError:
                pass
    return adds


def inputs_gate(inputs_path, kind, ndocs):
    """入力ゲート(最大3周)。code は提案入力を自動追記して収束させる。"""
    for _ in range(3):
        extra = ["--min", str(min(4, ndocs))] if kind == "json" else []
        sp = run_tool("check_inputs.py", inputs_path, *extra)
        if sp.returncode == 0:
            return True
        if sp.returncode != 1:
            sys.exit(2)
        adds = parse_added_inputs(sp.stdout)
        if not adds:
            return False
        data = json.load(open(inputs_path)) + adds
        json.dump(data, open(inputs_path, "w"), ensure_ascii=False)
        ndocs = len(data)
    return False


def main():
    ap = argparse.ArgumentParser(description="self-fix pipeline driver (procedure as code)")
    ap.add_argument("draft", help="draft instruction: a file path, or the text itself")
    ap.add_argument("rest", nargs="*", help="order-free: inputs.json / URL")
    ap.add_argument("--run", action="store_true", help="also execute and replay-verify")
    ap.add_argument("-k", type=int, default=None, help="runs per probe (spec_holes default)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--key", default=None)
    args = ap.parse_args()

    inputs_path = next((a for a in args.rest if a.endswith(".json")), None)
    cli_base = next((a for a in args.rest if a.startswith(("http://", "https://"))), None)
    draft_path, draft, inline = materialize_draft(args.draft)

    # ---- routing (table lookup, no judgment)
    w = needs_tools(draft)
    if w:
        route_agent(draft_path, w, args.k)  # does not return
    base = discover_base(cli_base)

    root = os.path.splitext(draft_path)[0]
    work_draft, policy_file, family, render_hint = draft_path, None, None, None
    kind = route = None
    if inputs_path:  # 入力ファイルの形が最優先の証拠(引数の組=コード)
        try:
            data = json.load(open(inputs_path))
        except Exception as e:
            print(f"!! cannot read {inputs_path}: {e}"); sys.exit(2)
        if data and all(isinstance(x, list) for x in data):
            kind, route = "code", "code"
    if kind is None:
        sp = run_tool("apply_contract.py", draft_path)
        if sp.returncode == 0:
            work_draft = root + ".contracted.txt"
            policy_file = root + ".policy.json"
            kind = "json"
            for line in sp.stdout.splitlines():
                if line.startswith("family: "):
                    family = line[8:]
                if line.startswith("render hint:"):
                    render_hint = line.split(":", 1)[1].strip()
            route = f"contract({family})"
        elif inputs_path:
            kind, route = "json", "extraction"
        elif looks_like_code(draft):
            kind, route = "code", "code"
        else:
            print("OUT OF SCOPE: no route (not code, no target documents supplied, "
                  "and no contract family matches)")
            sys.exit(3)
    print(f"[route] {route}")

    # ---- probe inputs
    if kind == "json" and not inputs_path:
        print("!! extraction/contract tasks need the target documents: "
              "pass inputs.json (array of document strings)")
        sys.exit(2)
    if not inputs_path:
        model = args.model or detect_model(base, args.key)[0]
        client = LLMClient(model, base, api=args.api, key=args.key, think=False)
        cand = gen_code_inputs(client, draft)
        if cand is None:
            print("!! could not obtain probe inputs from the model (3 attempts); "
                  "supply inputs.json manually")
            sys.exit(2)
        inputs_path = root + ".inputs.json"
        json.dump(cand, open(inputs_path, "w"), ensure_ascii=False)
        print(f"[inputs] generated {len(cand)} -> {inputs_path}")

    data = clean_inputs(json.load(open(inputs_path)), kind)
    json.dump(data, open(inputs_path, "w"), ensure_ascii=False)
    if not inputs_gate(inputs_path, kind, len(data)):
        print("GATE FAILED: probe inputs still incomplete after 3 rounds (see above)")
        sys.exit(1)

    # ---- bounded fix loop
    cur, final, verify_line = work_draft, None, None
    wroot = os.path.splitext(work_draft)[0]
    for i in (1, 2, 3):
        out = f"{wroot}.fixed{'' if i == 1 else i}.txt"
        extra = ["--policy", policy_file] if policy_file else []
        if args.k:
            extra += ["-k", str(args.k)]
        sp = run_tool("spec_holes.py", cur, inputs_path, base, "--fix", out, *extra)
        final = out
        for line in sp.stdout.splitlines():
            if line.startswith("[fix] holes:") or line.startswith("[fix] no holes"):
                verify_line = line
        if sp.returncode == 0:
            break
        if sp.returncode != 1:
            sys.exit(2)
        cur = out
    else:
        print("NOT DELEGABLE: holes remain after 3 fix rounds (see remaining list above)")
        sys.exit(1)

    if run_tool("check_fixed.py", work_draft, final).returncode != 0:
        print("GATE FAILED: fixed prompt no longer contains the draft verbatim")
        sys.exit(1)

    # ---- optional execution + replay verification
    artifact = replay_line = None
    if args.run:
        expected = os.path.splitext(final)[0] + ".expected.json"
        # オプションの後ろに位置引数を置かない(3.10のargparseは拒否する)
        sp = run_tool("replay_check.py", expected, "--prompt", final, "--base", base)
        if sp.returncode != 0:
            print("EXECUTION FAILED VERIFICATION (see mismatches above)")
            sys.exit(1)
        for line in sp.stdout.splitlines():
            if line.startswith("PASS"):
                replay_line = line
                m = re.search(r"saved to (\S+)", line)
                artifact = m.group(1) if m else None

    # ---- report (machine-assembled; nothing here came from a model's say-so)
    pins = [l for l in open(final).read()[len(open(work_draft).read().strip()):].splitlines()
            if l.strip().startswith("- ")]
    print("\n==== fix report ====")
    print(f"ROUTE: {route}")
    print(f"FIXED PROMPT: {final}")
    print(f"INPUTS: {inputs_path} (check_inputs: PASS)")
    print(f"VERIFY: {verify_line}")
    if args.run:
        print(f"ARTIFACT: {artifact}")
        print(f"REPLAY: {replay_line}")
    if render_hint:
        print(f"RENDER HINT: {render_hint}")
    print("PINNED (every line needs human review — intent was NOT checked):")
    print("\n".join(pins) if pins else "  none — draft was already unambiguous")
    print("NOT DONE: intent review. A human or a stronger model must review "
          "every pinned line before use.")
    if inline:
        print("\n---- fixed prompt (full text — copy from here) ----")
        print(open(final).read().rstrip())


if __name__ == "__main__":
    main()
