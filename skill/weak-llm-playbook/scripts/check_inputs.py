#!/usr/bin/env python3
"""Mechanical gate for probe inputs (inputs.json) written by an operator.

Grades the inputs WITHOUT understanding the task: structure, count, duplicates,
and pattern coverage per argument position (empty / size-1 / ties for sized
arguments; zero / negative for numeric arguments). Every missing pattern comes
with a copy-pasteable suggested input, so a weak operator can fix the file by
following the output literally instead of judging its own work.

usage: check_inputs.py inputs.json [--kind auto|code|json] [--min N]
  kind auto (default): array of strings = json (extraction), array of argument
  tuples = code. --min overrides the required count (code: 5, json: 4).
exit codes: 0 = PASS / 1 = FAIL / 2 = unreadable or malformed file
"""
import argparse
import copy
import json
import sys


def die(msg):
    print(f"!! {msg}")
    sys.exit(2)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def is_sized(v):
    return isinstance(v, (str, list, dict))


def canon(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def detect_kind(data):
    if isinstance(data, list) and data:
        if all(isinstance(x, str) for x in data):
            return "json"
        if all(isinstance(x, list) for x in data):
            return "code"
    return None


def suggest(base, pos, value):
    """Copy the first tuple and replace one position — a new, valid input."""
    t = copy.deepcopy(base)
    t[pos] = value
    return json.dumps(t, ensure_ascii=False)


def empty_like(v):
    return "" if isinstance(v, str) else ([] if isinstance(v, list) else {})


def single_like(v):
    if isinstance(v, str):
        return v[:1] or "x"
    if isinstance(v, list):
        return v[:1] or [1]
    k = next(iter(v), "k")
    return {k: v.get(k, 1)} if v else {"k": 1}


def ties_like(v):
    if isinstance(v, str):
        return (v[:1] or "a") * 2
    e = v[0] if v else 1
    return [e, e]


def check_code(tuples, min_n):
    oks, missing = [], []

    n = len(tuples)
    if n >= min_n:
        oks.append(f"count: {n} >= {min_n}")
    else:
        missing.append((f"count: only {n} tuple(s), need >= {min_n}",
                        "add more cases from the recipe"))

    arities = sorted({len(t) for t in tuples})
    if len(arities) == 1:
        oks.append(f"consistent arity ({arities[0]})")
    else:
        die(f"argument tuples have mixed arities {arities} — every tuple must "
            "have the same number of arguments (one per function parameter)")

    seen = {}
    for i, t in enumerate(tuples):
        c = canon(t)
        if c in seen:
            missing.append((f"duplicate tuples: #{i} == #{seen[c]} ({c})",
                            "replace one of them with a new case"))
        seen.setdefault(c, i)
    if not any(m[0].startswith("duplicate") for m in missing):
        oks.append("no duplicate tuples")

    base = tuples[0]
    for pos in range(arities[0]):
        col = [t[pos] for t in tuples]
        sized = [v for v in col if is_sized(v)]
        nums = [v for v in col if is_num(v)]
        tname = type(sized[0] if sized else (nums[0] if nums else col[0])).__name__
        tag = f"pos {pos} ({tname})"
        if sized:
            if any(len(v) == 0 for v in sized):
                oks.append(f"{tag}: empty value present")
            else:
                missing.append((f"{tag}: no empty value",
                                f"add: {suggest(base, pos, empty_like(sized[0]))}"))
            if any(len(v) == 1 for v in sized):
                oks.append(f"{tag}: size-1 value present")
            else:
                missing.append((f"{tag}: no size-1 value",
                                f"add: {suggest(base, pos, single_like(sized[0]))}"))
            listy = [v for v in sized if isinstance(v, (list, str))]
            if listy:
                if any(len(v) > len(set(json.dumps(e) for e in v)) for v in listy):
                    oks.append(f"{tag}: ties (equal elements) present")
                else:
                    missing.append((f"{tag}: no ties (equal elements)",
                                    f"add: {suggest(base, pos, ties_like(listy[0]))}"))
        if nums:
            if any(v == 0 for v in nums):
                oks.append(f"{tag}: zero present")
            else:
                missing.append((f"{tag}: no zero", f"add: {suggest(base, pos, 0)}"))
            if any(v < 0 for v in nums):
                oks.append(f"{tag}: negative present")
            else:
                missing.append((f"{tag}: no negative", f"add: {suggest(base, pos, -1)}"))
        if not sized and not nums:
            oks.append(f"{tag}: no mechanical pattern applies")
    return oks, missing


def check_json(texts, min_n):
    oks, missing = [], []
    n = len(texts)
    if n >= min_n:
        oks.append(f"count: {n} >= {min_n}")
    else:
        missing.append((f"count: only {n} document(s), need >= {min_n}",
                        "add more documents from the recipe"))
    blanks = [i for i, t in enumerate(texts) if not t.strip()]
    if blanks:
        missing.append((f"blank document(s): #{', #'.join(map(str, blanks))}",
                        "replace with real documents"))
    else:
        oks.append("no blank documents")
    seen = {}
    dup = False
    for i, t in enumerate(texts):
        if t in seen:
            missing.append((f"duplicate documents: #{i} == #{seen[t]}",
                            "replace one of them with a new document"))
            dup = True
        seen.setdefault(t, i)
    if not dup:
        oks.append("no duplicate documents")
    return oks, missing


JSON_RECIPE = ("recipe reminder (NOT machine-checkable — spec_holes' divergence "
               "report is the real gate here):\n"
               "  1. one complete document (every field present, plain formats)\n"
               "  2. one document missing one field\n"
               "  3. one document with two competing candidates for the same field\n"
               "  4. one document using a different format (range / other date style)")


def main():
    ap = argparse.ArgumentParser(description="mechanical gate for probe inputs")
    ap.add_argument("inputs", help="inputs.json (array of argument tuples or of document strings)")
    ap.add_argument("--kind", choices=["auto", "code", "json"], default="auto")
    ap.add_argument("--min", type=int, default=None, help="required count (code: 5, json: 4)")
    args = ap.parse_args()

    try:
        data = json.load(open(args.inputs))
    except Exception as e:
        die(f"cannot read {args.inputs}: {e}")
    if not (isinstance(data, list) and data):
        die(f"{args.inputs} must be a non-empty JSON array")

    kind = args.kind if args.kind != "auto" else detect_kind(data)
    if kind is None:
        die("cannot infer kind: use an array of strings (json mode) or an array "
            "of argument tuples (code mode), or pass --kind")
    if kind == "code" and not all(isinstance(x, list) for x in data):
        die("code mode: every element must be an array (one argument tuple per call)")
    if kind == "json" and not all(isinstance(x, str) for x in data):
        die("json mode: every element must be a string (one input document)")

    min_n = args.min if args.min is not None else (5 if kind == "code" else 4)
    print(f"# check_inputs: kind={kind}, {len(data)} input(s)")
    oks, missing = (check_code if kind == "code" else check_json)(data, min_n)
    for m in oks:
        print(f"[ok] {m}")
    for m, fix in missing:
        print(f"[MISSING] {m} — {fix}")
    if kind == "json":
        print(JSON_RECIPE)
    if missing:
        print(f"FAIL: {len(missing)} item(s) missing — add the suggested inputs above and rerun")
        sys.exit(1)
    print("PASS: mechanical checklist covered")


if __name__ == "__main__":
    main()
