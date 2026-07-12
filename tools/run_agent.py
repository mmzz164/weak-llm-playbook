#!/usr/bin/env python3
"""K-run prober/runner for tool-requiring tasks — disposable headless agents.

The operator session never holds tool permissions (an interactive agent can be
talked out of any textual restriction). This script launches disposable
headless agent sessions (`claude -p`, or your local-LLM wrapper via --cmd)
with a result contract, runs the task K times, and compares the JSON results
field-by-field under a compare policy — the agent-task equivalent of
spec_holes: divergence across runs = a hole in your instruction; agreement =
a default to check against your intent.

usage:
  run_agent.py task.txt [--cmd "claude"] [--allowed PATTERN ...]
               [-k K] [--timeout SEC] [--policy POLICY.json]
               [--contract research|none] [--outdir DIR]

  --cmd      agent command; may contain arguments ("python3 mock_agent.py")
  --allowed  tool allowlist patterns passed as --allowedTools (repeatable);
             ONLY these children hold tool permissions, never the caller
  --contract research (default): if the task has no output contract yet,
             append contracts/research.json's contract + use its policy
exit codes: 0 = runs agree on every compared field / 1 = divergence or too
            few valid results / 2 = infrastructure error
"""
import argparse
import json
import os
import shlex
import subprocess
import tempfile
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from llm_client import find_json
from spec_holes import field_repr, has_ja

CONTRACT_MARKS = ("[Output contract", "[出力契約")


def compare_results(results, policy):
    """有効なJSON結果同士をポリシー付きでフィールド比較。(diverged, consensus) を返す。"""
    policy = policy or {}
    diverged, consensus = [], []
    dicts = [r for r in results if isinstance(r, dict)]
    if len(dicts) != len(results):  # dict以外が混ざったら全体比較に落とす
        c = Counter(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in results)
        return ([("(whole)", c)] if len(c) > 1 else [], [("(whole)", next(iter(c)))])
    for key in sorted(set().union(*[set(d) for d in dicts])):
        pol = policy.get(key, "exact")
        if pol == "free":
            continue
        c = Counter(field_repr(d, key, pol) for d in dicts)
        (diverged if len(c) > 1 else consensus).append((key, c if len(c) > 1 else next(iter(c))))
    return diverged, consensus


def pin_lines(diverged, ja):
    """発散フィールドをピン行に翻訳する。値の割れ=多数派で自動ピン(auto)、
    顔ぶれ(set)の割れ=データ依存なので値では固定できず、人間が条件を書く(manual)。"""
    auto, manual = [], []
    for key, c in diverged:
        (top, n), *rest = c.most_common()
        alts = " / ".join(f"{v} ({m})" for v, m in rest)
        note = (f"   # 他候補: {alts}" if ja else f"   # alternatives: {alts}") if rest else ""
        if top.startswith("len="):
            auto.append(f'- "{key}" は {top[4:]}件とする{note}' if ja else
                        f'- count of "{key}" = {top[4:]}{note}')
        elif top.startswith("set{"):
            manual.append(f'- ★要記入: "{key}" の顔ぶれが実行ごとに異なる。並び順・範囲・'
                          "フィルタ条件を1行で明記すること" if ja else
                          f'- ★FILL IN: the lineup of "{key}" differs across runs. '
                          "Specify ordering/range/filter in one line")
        else:
            auto.append(f'- "{key}" = {top} とする{note}' if ja else
                        f'- "{key}" = {top}{note}')
    return auto, manual


def child_cmd(base_cmd, task, args):
    """子セッションの起動コマンド。--allowed 指定時は許可リスト、
    未指定なら既定でバイパス(--no-bypass で素の権限確認に戻せる)。"""
    cmd = base_cmd + ["-p", task]
    if args.allowed:
        for pat in args.allowed:
            cmd += ["--allowedTools", pat]
    elif not args.no_bypass:
        cmd.append("--dangerously-skip-permissions")
    return cmd


def probe(task, args, outdir):
    """タスクをK回実行して比較。(valid, diverged, consensus) を返す。"""
    os.makedirs(outdir, exist_ok=True)
    base_cmd = shlex.split(args.cmd)
    results = []
    for i in range(args.k):
        cmd = child_cmd(base_cmd, task, args)
        t0 = time.time()
        try:
            sp = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
            raw, status = sp.stdout, ("ok" if sp.returncode == 0 else f"exit {sp.returncode}")
        except subprocess.TimeoutExpired:
            raw, status = "", "TIMEOUT"
        except FileNotFoundError:
            print(f"!! agent command not found: {base_cmd[0]}"); sys.exit(2)
        secs = time.time() - t0
        open(os.path.join(outdir, f"run{i}.txt"), "w").write(raw)
        j = find_json(raw) if raw else None
        if j is not None:
            json.dump(j, open(os.path.join(outdir, f"result{i}.json"), "w"),
                      ensure_ascii=False, indent=1)
        results.append(j)
        print(f"run {i}: {status}, {secs:.1f}s, json={'ok' if j is not None else 'MISSING'}")
    valid = [r for r in results if r is not None]
    print(f"valid results: {len(valid)}/{args.k} (artifacts in {outdir}/)")
    if len(valid) < 2:
        return valid, None, None
    d, c = compare_results(valid, probe.policy)
    return valid, d, c


def report(diverged, consensus):
    print("\n## [DIVERGED] spec holes — fields whose values differ across runs (must specify)")
    if not diverged:
        print("  none (runs agree on every compared field)")
    for key, c in diverged:
        print(f"  ★ {key} → " + " / ".join(f'"{v}" x{n}' for v, n in c.most_common()))
    print("\n## [AGREED] implicit consensus — check against your intent")
    for key, v in consensus:
        print(f"  - {key} → {v}")


def main():
    ap = argparse.ArgumentParser(description="K-run headless agent prober (tool tasks)")
    ap.add_argument("task", help="task instruction: a file path, or the text itself")
    ap.add_argument("--cmd", default=os.environ.get("WEAK_LLM_AGENT_CMD", "claude"),
                    help="agent command, may include args. Default: $WEAK_LLM_AGENT_CMD, "
                         "else 'claude'. Children inherit this session's environment, so "
                         "launched from inside a local-LLM wrapper session (claude-local "
                         "etc.), plain 'claude' already runs as that same setup — "
                         "'run as myself'. Set WEAK_LLM_AGENT_CMD in your shell profile "
                         "to fix the command for plain-terminal use.")
    ap.add_argument("--allowed", action="append", default=[],
                    help="tool allowlist pattern (repeatable), e.g. mcp__mcp-atlassian__*. "
                         "Giving this switches OFF the default bypass.")
    ap.add_argument("--bypass", action="store_true",
                    help="(default behavior; kept for compatibility)")
    ap.add_argument("--no-bypass", action="store_true",
                    help="no bypass and no allowlist: children ask permissions normally "
                         "(headless children usually cannot answer prompts — mostly for debugging)")
    ap.add_argument("-k", type=int, default=3, help="number of runs (default 3 — agent runs are expensive)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per run (default 900)")
    ap.add_argument("--policy", default=None, help="compare-policy JSON (default: research contract's)")
    ap.add_argument("--contract", choices=["research", "none"], default="research")
    ap.add_argument("--outdir", default=None, help="artifact dir (default: alongside task file)")
    ap.add_argument("--fix", nargs="?", const="", metavar="OUT.txt", default=None,
                    help="write a revised task with diverging behaviors pinned to the majority, "
                         "then re-probe it (K more runs) to verify — same UX as spec_holes --fix. "
                         "Data-dependent holes (set lineups) become FILL-IN lines for you.")
    args = ap.parse_args()

    if not os.path.isfile(args.task):
        if args.task.endswith((".txt", ".md", ".json")):
            print(f"!! task file not found: {args.task}"); sys.exit(2)
        d = tempfile.mkdtemp(prefix="agent-")
        path = os.path.join(d, "task.txt")
        open(path, "w").write(args.task.strip() + "\n")
        print(f"[task] inline text → {path}")
        args.task = path
    try:
        task = open(args.task).read().strip()
    except OSError as e:
        print(f"!! cannot read task: {e}"); sys.exit(2)

    policy = json.load(open(args.policy)) if args.policy else None
    if args.contract == "research" and not any(m in task for m in CONTRACT_MARKS):
        tpl = json.load(open(os.path.join(HERE, "contracts", "research.json")))
        task += "\n\n" + tpl["instruction_ja" if has_ja(task) else "instruction_en"]
        if policy is None:
            policy = tpl["policy"]
        print(f"[contract] appended research contract (policy: {len(policy)} field(s))")
    probe.policy = policy

    src = ("--cmd" if "--cmd" in sys.argv else
           ("$WEAK_LLM_AGENT_CMD" if os.environ.get("WEAK_LLM_AGENT_CMD") else
            "default — inherits this session's environment"))
    print(f"[agent] children run via: {args.cmd} ({src})")
    outdir = args.outdir or (os.path.splitext(args.task)[0] + ".runs")
    valid, diverged, consensus = probe(task, args, outdir)
    if diverged is None:
        print("!! fewer than 2 valid results — cannot compare; check the runs' raw output")
        sys.exit(1)
    report(diverged, consensus)

    if args.fix is None:
        sys.exit(1 if diverged else 0)

    # --- --fix: 改訂版タスクの生成と再検証(spec_holes --fix と同じ体験) ---
    fix_out = args.fix or (os.path.splitext(args.task)[0] + ".fixed.txt")
    ja = has_ja(task)
    if not diverged:
        open(fix_out, "w").write(task + "\n")
        print(f"\n[fix] no holes found — task is already reproducible; wrote it unchanged to {fix_out}")
        return
    auto, manual = pin_lines(diverged, ja)
    head = ("[挙動の固定 — run_agent --fix による自動生成。実行間で割れた点を多数派で固定した。"
            "意図と違う行は書き直すこと。]" if ja else
            "[Behavior contract — auto-generated by run_agent --fix. Points that diverged "
            "across runs, pinned to the majority. Rewrite any line that does not match your intent.]")
    fixed = task + "\n\n" + head + "\n" + "\n".join(auto + manual) + "\n"
    open(fix_out, "w").write(fixed)
    print(f"\n[fix] wrote revised task to {fix_out} "
          f"({len(auto)} pinned, {len(manual)} FILL-IN line(s))")
    if manual:
        print("[fix] FILL-IN lines need your input (data-dependent lineups cannot be pinned "
              "to values). Edit them, then re-run:")
        print(f"[fix]   run_agent.py {fix_out}" +
              "".join(f' --allowed "{p}"' for p in args.allowed))
        sys.exit(1)
    print(f"[fix] re-probing the revised task ({args.k} more runs) to verify...")
    _, d2, c2 = probe(fixed, args, outdir + ".fix")
    if d2 is None:
        print("!! re-probe produced fewer than 2 valid results"); sys.exit(1)
    print(f"[fix] holes: {len(diverged)} → {len(d2)}")
    if d2:
        report(d2, c2)
        print(f"[fix] holes remain — edit {fix_out} (or rerun --fix on it) and re-verify.")
        sys.exit(1)
    print(f"[fix] verified: the task now behaves reproducibly. Review {fix_out} and rewrite "
          "any pinned line that does not match your intent.")


if __name__ == "__main__":
    main()
