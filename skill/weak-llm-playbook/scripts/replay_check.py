#!/usr/bin/env python3
"""Replay verifier — the final gate of the self-fix run mode.

spec_holes --fix records an expected-behavior table (<fixed>.expected.json)
whenever a prompt verifies clean: the agreed behavior for every probe input.
This script executes the task once more (or loads a given implementation) and
mechanically compares the result against that table, so a weak operator never
judges its own artifact — a verified execution is one that reproduces the
measured behavior on every probe input.

usage:
  replay_check.py expected.json --prompt fixed.txt [URL] [--attempts N]
                  [--model M] [--api openai|anthropic] [--key K]
      generate/execute with the model, verify, save the artifact
      (code kind -> <fixed>.impl.py / json kind -> <fixed>.outputs.json)
  replay_check.py expected.json --code impl.py
      verify an existing implementation offline (code kind only)

exit codes: 0 = all behaviors match / 1 = mismatch remains / 2 = bad usage
Note: executes generated code (same caveat as the probes).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model, find_json
from spec_holes import canon, extract_code, field_repr, has_ja, load_fn

CLIENT = None


def gen(prompt, temperature, max_tokens):
    return CLIENT.chat(prompt, temperature=temperature, max_tokens=max_tokens)


def behave(f, a):
    try:
        r = f(*[json.loads(json.dumps(x)) for x in a])
        return repr(r)
    except Exception as e:
        return f"EXC:{type(e).__name__}"


def verify_code_fn(f, expected):
    """[(entry, got)] for every probe input whose behavior differs from the table."""
    mism = []
    for e in expected:
        got = behave(f, e["args"])
        if got != e["behavior"]:
            mism.append((e, got))
    return mism


def verify_json_outputs(outs, expected, policy=None):
    """outs: {input_index: parsed_json_or_None}. Same contract as verify_code_fn.
    policy: per-field compare policy recorded in the expected table."""
    policy = policy or {}
    mism = []
    for e in expected:
        o = outs.get(e["input"])
        if o is None:
            got = "JSON_PARSE_FAIL"
        elif e["field"] == "(whole)":
            got = canon(o)
        elif not isinstance(o, dict):
            got = canon(o)
        else:
            got = field_repr(o, e["field"], policy.get(e["field"], "exact"))
        if got != e["value"]:
            mism.append((e, got))
    return mism


def report(mism, kind, fn):
    for e, got in mism:
        if kind == "code":
            call = f"{fn}({', '.join(repr(x) for x in e['args'])})"
            print(f"  x {call}: expected {e['behavior']}, got {got}")
        else:
            print(f"  x input #{e['input']} {e['field']}: expected {e['value']}, got {got}")


def out_path(prompt_file, suffix):
    return os.path.splitext(prompt_file)[0] + suffix


def main():
    global CLIENT
    ap = argparse.ArgumentParser(description="verify an execution against the "
                                 "expected-behavior table written by spec_holes --fix")
    ap.add_argument("expected", help="<fixed>.expected.json from spec_holes --fix")
    ap.add_argument("base_pos", nargs="?", default=None, help="endpoint URL (optional)")
    ap.add_argument("--prompt", default=None, help="fixed prompt to execute and verify")
    ap.add_argument("--code", default=None, help="existing implementation file to verify offline")
    ap.add_argument("--attempts", type=int, default=3, help="generation attempts (default 3)")
    ap.add_argument("--base", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--key", default=None)
    args = ap.parse_args()

    try:
        table = json.load(open(args.expected))
        kind, expected = table["kind"], table["expected"]
    except Exception as e:
        print(f"!! cannot read expected table {args.expected}: {e}"); sys.exit(2)
    if not expected:
        print("!! expected table is empty — nothing to verify against"); sys.exit(2)
    fn = table.get("fn")

    if args.code:
        if kind != "code":
            print("!! --code only applies to kind=code tables"); sys.exit(2)
        f, err = load_fn(extract_code(open(args.code).read()), fn)
        if f is None:
            print(f"FAIL: cannot load implementation ({err})"); sys.exit(1)
        mism = verify_code_fn(f, expected)
        if mism:
            print(f"FAIL: {len(mism)}/{len(expected)} behavior(s) differ from the table")
            report(mism, kind, fn)
            sys.exit(1)
        print(f"PASS: {args.code} reproduces all {len(expected)} measured behavior(s)")
        return

    if not args.prompt:
        print("!! need --prompt fixed.txt (or --code impl.py)"); sys.exit(2)
    task = open(args.prompt).read().strip()
    base = args.base or args.base_pos or os.environ.get("PROBE_BASE", "http://localhost:8000")
    model = args.model
    if not model:
        if args.api == "anthropic":
            ap.error("--api anthropic requires an explicit --model")
        model = detect_model(base, args.key)[0]
        print(f"# model auto-detected from {base}/v1/models: {model}")
    CLIENT = LLMClient(model, base, api=args.api, key=args.key, think=False)
    ja = has_ja(task)

    for attempt in range(1, args.attempts + 1):
        temp = 0.0 if attempt == 1 else 0.7
        if kind == "code":
            suffix = ("\n標準ライブラリのみで最小限の実装をコードのみ出力。import・説明・テスト・型チェックは不要。"
                      if ja else
                      "\nOutput only a minimal implementation using the standard library. "
                      "No explanations, tests, or type checks.")
            code = extract_code(gen(task + suffix, temp, 1200))
            f, err = load_fn(code, fn)
            if f is None:
                print(f"attempt {attempt}: implementation did not load ({err})")
                continue
            mism = verify_code_fn(f, expected)
            if not mism:
                dst = out_path(args.prompt, ".impl.py")
                open(dst, "w").write(code + "\n")
                print(f"PASS (attempt {attempt}): all {len(expected)} measured behavior(s) "
                      f"reproduced — artifact saved to {dst}")
                return
        else:
            sep = "\n\n--- 入力 ---\n" if ja else "\n\n--- input ---\n"
            docs = {}
            for e in expected:
                docs.setdefault(e["input"], e["doc"])
            outs = {i: find_json(gen(task + sep + doc, temp, 800))
                    for i, doc in sorted(docs.items())}
            mism = verify_json_outputs(outs, expected, table.get("policy"))
            if not mism:
                dst = out_path(args.prompt, ".outputs.json")
                json.dump([{"input": i, "output": outs[i]} for i in sorted(outs)],
                          open(dst, "w"), ensure_ascii=False, indent=1)
                print(f"PASS (attempt {attempt}): all {len(expected)} measured behavior(s) "
                      f"reproduced — outputs saved to {dst}")
                return
        print(f"attempt {attempt}: {len(mism)}/{len(expected)} behavior(s) differ")
        report(mism, kind, fn)
    print(f"FAIL: could not reproduce the measured behavior in {args.attempts} attempt(s). "
          "The task is not stable enough to execute unsupervised on this model.")
    sys.exit(1)


if __name__ == "__main__":
    main()
