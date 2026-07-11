#!/usr/bin/env python3
"""タスク駆動スペック穴検出器 (disagreement probing) + プロンプト自動修正 (--fix).

ドラフト仕様をワーカーモデルに K 回実装/実行させ、同じ入力で挙動を比較する。
割れた所 = モデルが推測で埋めるしかなかった所 = 発注側の書き忘れ。

--fix OUT.txt を付けると、割れた挙動を多数派で固定した改訂版プロンプトを書き出し、
それを同じ手順で再測定して「穴が消えたか」まで検証する(消え残りがあれば exit 1)。
使う側は OUT.txt を読み、意図と違う固定行だけ書き直せばよい。

使い方:
  python3 spec_holes.py <task.txt> <関数名|-> [model] [base_url] [K] [inputs.json]
                        [--kind code|json] [--fix OUT.txt] [--api ...] [--key ...]
    task.txt    : ワーカーに渡す予定のドラフト仕様(自然文)
    inputs.json : --kind code なら引数の組の配列(例 [[[3,1,2],2],[[],0]])。
                  --kind json なら入力テキスト(文字列)の配列。
  例) spec_holes.py draft.txt top_n http://localhost:8000 5 inputs.json --fix fixed.txt
  model省略時(openai互換のみ): /v1/models から自動検出。
"""
import argparse
import json
import os
import re
import sys
import types
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model, find_json

CLIENT = None   # main() で初期化


def gen(prompt, temperature, max_tokens=600):
    return CLIENT.chat(prompt, temperature=temperature, max_tokens=max_tokens)


def has_ja(text):
    return re.search(r"[ぁ-んァ-ヶ一-龠]", text) is not None


def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def load_fn(code, name):
    mod = types.ModuleType("impl")
    try:
        exec(code, mod.__dict__)
    except Exception as e:
        return None, f"LOAD_ERR:{type(e).__name__}"
    f = getattr(mod, name, None)
    if callable(f):
        return f, None
    for k, v in mod.__dict__.items():
        if callable(v) and not k.startswith("_") and isinstance(v, types.FunctionType):
            return v, None
    return None, "NO_FUNC"


# ==== 抽出モード (--kind json) ====

def probe_json(task, texts, K):
    """各入力テキストに同じ指示をK回実行し、JSON出力をフィールド単位で比較。"""
    sep = "\n\n--- 入力 ---\n" if has_ja(task) else "\n\n--- input ---\n"
    total = bad = 0
    per_input = []
    for doc in texts:
        outs = []
        for k in range(K):
            raw = gen(task + sep + doc, 0.0 if k == 0 else 0.7, max_tokens=800)
            j = find_json(raw)
            total += 1
            if j is None:
                bad += 1
            else:
                outs.append(j)
        per_input.append((doc, outs))

    diverged, consensus, skipped = [], [], []
    for i, (doc, outs) in enumerate(per_input):
        label = doc[:24].replace("\n", " ")
        if len(outs) < 3:
            skipped.append((i, label, len(outs)))
            continue
        if all(isinstance(o, dict) for o in outs):
            for key in sorted(set().union(*[set(o) for o in outs])):
                vals = [canon(o[key]) if key in o else "(missing)" for o in outs]
                c = Counter(vals)
                (diverged if len(c) > 1 else consensus).append(
                    (i, label, key, c if len(c) > 1 else vals[0]))
        else:  # dict以外(配列等)は全体で比較
            c = Counter(canon(o) for o in outs)
            (diverged if len(c) > 1 else consensus).append(
                (i, label, "(whole)", c if len(c) > 1 else canon(outs[0])))
    return dict(total=total, bad=bad, skipped=skipped,
                diverged=diverged, consensus=consensus)


def report_json(res):
    total, bad = res["total"], res["bad"]
    print(f"JSON parsed: {total - bad}/{total} (parse-failure rate {bad / total:.0%})")
    if bad / total >= 0.5:
        print("!! parse-failure rate >50%: the output format itself is broken (strengthen format instructions or avoid delegation)")
    for i, label, n in res["skipped"]:
        print(f"  (input #{i} \"{label}…\": only {n} valid outputs (<3), skipped)")

    print("\n## [DIVERGED] spec holes — fields whose values differ across runs (must specify)")
    if not res["diverged"]:
        print("  none (no divergence on this input set)")
    for i, label, key, c in res["diverged"]:
        dist = " / ".join(f"\"{v}\" x{n}" for v, n in c.most_common())
        print(f"  ★ input #{i} \"{label}…\" {key} → {dist}")

    print("\n## [AGREED] implicit consensus — check against your intent (specify if it differs)")
    for i, label, key, v in res["consensus"]:
        print(f"  - input #{i} {key} → {v}")
    print(f"\nsummary: {len(res['diverged'])} hole(s) / {len(res['consensus'])} agreed / parse failures {bad}/{total}")


# ==== コードモード (--kind code) ====

def collect_inputs(task, fn_name, inputs_file):
    """プローブ入力: 発注側ファイル優先 + ワーカー提案を補助的に合併(1回だけ)。"""
    inputs, src = [], []
    if inputs_file:
        try:
            for a in json.load(open(inputs_file)):
                if isinstance(a, list):
                    inputs.append(a)
            src.append(f"user-supplied {len(inputs)}")
        except Exception as e:
            print(f"!! failed to read inputs.json: {e}"); sys.exit(2)
    if has_ja(task):
        args_prompt = (task + f"\n\nこの仕様の関数 {fn_name} に対して、曖昧な点・境界・エッジケースを突く"
                       "テスト入力(引数の組)を8個、JSON配列の配列だけで出力してください。"
                       '例: [[[3,1,2], 2], [[], 0]]。コードや説明は不要、JSONのみ。')
    else:
        args_prompt = (task + f"\n\nFor the function {fn_name} in this spec, output 8 test inputs "
                       "(argument tuples) that probe ambiguities, boundaries, and edge cases, "
                       "as a JSON array of arrays only. Example: [[[3,1,2], 2], [[], 0]]. "
                       "No code or explanations, JSON only.")
    n0 = len(inputs)
    for t in (0.3, 0.9):
        try:
            raw = gen(args_prompt, t, max_tokens=400)
            m = re.search(r"\[\s*\[.*?\]\s*\]", raw, re.S)
            cand = json.loads(m.group(0))
            if not (isinstance(cand, list) and all(isinstance(a, list) for a in cand)):
                continue
            if any(len(repr(a)) > 200 for a in cand):   # 反復崩壊などの異常値を除外
                continue
            for a in cand:
                if repr(a) not in {repr(x) for x in inputs}:
                    inputs.append(a)
        except Exception:
            pass
    if len(inputs) > n0:
        src.append(f"worker-proposed {len(inputs)-n0}")
    if not inputs:
        print("!! no probe inputs: supply inputs.json and rerun"); sys.exit(2)
    print(f"probe inputs: {len(inputs)} ({' + '.join(src)})")
    return inputs


def probe_code(task, fn_name, inputs, K):
    """K個の実装を生成し、全実装×全入力で挙動を比較。"""
    suffix = ("\n標準ライブラリのみで最小限の実装をコードのみ出力。import・説明・テスト・型チェックは不要。"
              if has_ja(task) else
              "\nOutput only a minimal implementation using the standard library. "
              "No explanations, tests, or type checks.")
    impls, broken, attempts = [], 0, 0
    while len(impls) < K and attempts < K * 3:
        temp = 0.0 if attempts == 0 else 0.7
        attempts += 1
        code = extract_code(gen(task + suffix, temp, max_tokens=1200))
        f, err = load_fn(code, fn_name)
        if f is None:
            broken += 1
            continue
        impls.append(f)
    res = dict(n=len(impls), K=K, attempts=attempts, broken=broken,
               dead=0, alive=0, diverged=[], consensus=[], fatal=None)
    if len(impls) < 3:
        res["fatal"] = "fewer than 3 valid implementations"
        return res

    def behave(f, a):
        try:
            r = f(*[json.loads(json.dumps(x)) for x in a])  # 実装間の破壊的変更を隔離
            return repr(r)
        except Exception as e:
            return f"EXC:{type(e).__name__}"

    matrix = {id(f): [behave(f, a) for a in inputs] for f in impls}
    alive = [f for f in impls if not all(b.startswith("EXC:") for b in matrix[id(f)])]
    res["dead"] = len(impls) - len(alive)
    res["alive"] = len(alive)
    if len(alive) < 3:
        res["fatal"] = "fewer than 3 live implementations"
        return res
    for j, a in enumerate(inputs):
        c = Counter(matrix[id(f)][j] for f in alive)
        if len(c) > 1:
            res["diverged"].append((a, c))
        else:
            res["consensus"].append((a, c.most_common(1)[0][0]))
    return res


def report_code(res, fn_name):
    rate = res["broken"] / res["attempts"] if res["attempts"] else 0
    print(f"implementations: {res['n']}/{res['K']} (attempts {res['attempts']}, "
          f"load failures {res['broken']} = not-implementable rate {rate:.0%})")
    if rate >= 0.5:
        print("!! not-implementable rate >50%: this task is unstable on this model (avoid delegation or change granularity)")
    if res["dead"]:
        print(f"(excluded {res['dead']} broken implementation(s) that raised on every input)")
    if res["fatal"]:
        print(f"!! {res['fatal']}; divergence analysis not possible"); sys.exit(2)

    print("\n## [DIVERGED] spec holes — inputs where implementations disagree (must specify)")
    if not res["diverged"]:
        print("  none (no divergence on this input set)")
    for a, c in res["diverged"]:
        dist = " / ".join(f"\"{b}\" x{n}" for b, n in c.most_common())
        print(f"  ★ {fn_name}(*{a!r}) → {dist}")

    print("\n## [AGREED] implicit consensus — check against your intent (specify if it differs)")
    for a, b in res["consensus"]:
        print(f"  - {fn_name}(*{a!r}) → {b}")
    print(f"\nsummary: {len(res['diverged'])} hole(s) / {len(res['consensus'])} agreed / "
          f"not-implementable {res['broken']}/{res['K']}")


# ==== --fix: 多数派で固定した改訂版プロンプトを生成 ====

def _behavior_phrase(call, b, ja):
    if b.startswith("EXC:"):
        t = b[4:]
        return f"- {call} は {t} を送出する" if ja else f"- {call} raises {t}"
    return f"- {call} == {b}"


def pin_block_code(diverged, alive, fn_name, ja):
    head = ("[挙動の固定 — spec_holes --fix による自動生成。実装間で解釈が割れた点を多数派の挙動で固定した。"
            "意図と違う行は書き直すこと。]" if ja else
            "[Behavior contract — auto-generated by spec_holes --fix. Points where implementations "
            "disagreed, pinned to the majority behavior. Rewrite any line that does not match your intent.]")
    lines = [head]
    for a, c in diverged:
        call = f"{fn_name}({', '.join(repr(x) for x in a)})"
        (top, n), *rest = c.most_common()
        alts = " / ".join(f"{b} ({m}/{alive})" for b, m in rest)
        note = (f"   # 他候補: {alts}" if ja else f"   # alternatives: {alts}") if rest else ""
        lines.append(_behavior_phrase(call, top, ja) + note)
    return "\n".join(lines)


def pin_block_json(diverged, ja):
    head = ("[出力の固定 — spec_holes --fix による自動生成。実行間で値が割れたフィールドを多数派で固定した。"
            "意図と違う行は書き直すこと。]" if ja else
            "[Output contract — auto-generated by spec_holes --fix. Fields whose values diverged "
            "across runs, pinned to the majority. Rewrite any line that does not match your intent.]")
    lines = [head]
    for i, label, key, c in diverged:
        (top, n), *rest = c.most_common()
        alts = " / ".join(f"{v} ({m})" for v, m in rest)
        note = (f"   # 他候補: {alts}" if ja else f"   # alternatives: {alts}") if rest else ""
        if ja:
            lines.append(f"- 入力例「{label}…」では \"{key}\" = {top} とする{note}")
        else:
            lines.append(f"- for input \"{label}…\": \"{key}\" = {top}{note}")
    return "\n".join(lines)


def main():
    global CLIENT
    ap = argparse.ArgumentParser(description="task-driven spec-hole detection (works against any endpoint)")
    ap.add_argument("task_file")
    ap.add_argument("fn_name")
    ap.add_argument("model", nargs="?", default=None,
                    help="omit (or \"\") to auto-detect from /v1/models (OpenAI-compatible only)")
    ap.add_argument("base",  nargs="?", default="http://localhost:8000")
    ap.add_argument("k",     nargs="?", type=int, default=5)
    ap.add_argument("inputs", nargs="?", default=None, help="JSON file of user-supplied probe inputs (recommended)")
    ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--key", default=None)
    ap.add_argument("--kind", choices=["code", "json"], default="code",
                    help="code=function implementation (default) / json=extraction tasks: run the instruction "
                         "K times per input text and detect field-level divergence (pass '-' as fn_name)")
    ap.add_argument("--fix", metavar="OUT.txt", default=None,
                    help="write a revised prompt with diverging behaviors pinned to the majority, "
                         "then re-probe it to verify the holes are gone (exit 1 if any remain)")
    _argv = sys.argv[1:]
    if len(_argv) > 2 and _argv[2].startswith(("http://", "https://")):
        _argv.insert(2, "")   # 第3引数がURL = model省略とみなし繰り上げ
    args = ap.parse_args(_argv)

    model = args.model
    if not model:
        if args.api == "anthropic":
            ap.error("--api anthropic requires an explicit model (auto-detection uses the OpenAI-compatible /v1/models only)")
        models = detect_model(args.base, args.key)
        model = models[0]
        print(f"# model not specified → auto-detected from {args.base}/v1/models: {model}"
              + (f" (+{len(models)-1} more)" if len(models) > 1 else ""))

    task = open(args.task_file).read().strip()
    CLIENT = LLMClient(model, args.base, api=args.api, key=args.key, think=False)
    K = args.k
    ja = has_ja(task)

    if args.kind == "json":
        if not args.inputs:
            print("!! --kind json requires inputs.json (an array of input text strings)"); sys.exit(2)
        texts = json.load(open(args.inputs))
        if not (isinstance(texts, list) and texts and all(isinstance(x, str) for x in texts)):
            print("!! inputs.json must be an array of strings (input texts)"); sys.exit(2)
        print(f"# spec-hole detection (extraction mode): model={model} K={K} inputs={len(texts)}")
        res = probe_json(task, texts, K)
        report_json(res)
        probe_again = lambda t: probe_json(t, texts, K)
        block = lambda d: pin_block_json(d, ja)
    else:
        print(f"# spec-hole detection: fn={args.fn_name} model={model} K={K}")
        inputs = collect_inputs(task, args.fn_name, args.inputs)
        res = probe_code(task, args.fn_name, inputs, K)
        report_code(res, args.fn_name)
        probe_again = lambda t: probe_code(t, args.fn_name, inputs, K)
        block = lambda d: pin_block_code(d, res["alive"], args.fn_name, ja)

    if not args.fix:
        return

    # --- --fix: 改訂版プロンプトの生成と再検証 ---
    if not res["diverged"]:
        open(args.fix, "w").write(task + "\n")
        print(f"\n[fix] no holes found — draft is already unambiguous; wrote it unchanged to {args.fix}")
        return
    fixed = task + "\n\n" + block(res["diverged"]) + "\n"
    open(args.fix, "w").write(fixed)
    print(f"\n[fix] wrote revised prompt to {args.fix} ({len(res['diverged'])} behavior(s) pinned)")
    print("[fix] re-probing the revised prompt to verify...")
    res2 = probe_again(fixed)
    before, after = len(res["diverged"]), len(res2["diverged"])
    print(f"[fix] holes: {before} → {after}")
    if after == 0:
        print(f"[fix] verified: behavior is now reproducible. Review {args.fix} and rewrite any pinned line that does not match your intent.")
    else:
        print("[fix] remaining holes:")
        if args.kind == "json":
            for i, label, key, c in res2["diverged"]:
                print(f"  ★ input #{i} \"{label}…\" {key} → " + " / ".join(f"\"{v}\" x{n}" for v, n in c.most_common()))
        else:
            for a, c in res2["diverged"]:
                print(f"  ★ {args.fn_name}(*{a!r}) → " + " / ".join(f"\"{b}\" x{n}" for b, n in c.most_common()))
        print(f"[fix] pin these manually in {args.fix} (or rerun --fix on it), then re-verify.")
        sys.exit(1)


if __name__ == "__main__":
    main()
