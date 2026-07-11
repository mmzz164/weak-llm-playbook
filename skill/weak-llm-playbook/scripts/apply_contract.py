#!/usr/bin/env python3
"""Shadow-contract applier: turn a free-form draft into a measurable task.

Users write instructions in plain language ("review this page"); JSON is the
measurement instrument's interface, not the user's. This script scans the
contract templates (contracts/*.json), picks the family whose keywords appear
in the draft (most hits wins, ties break alphabetically), and writes:

  <draft>.contracted.txt  = draft + the family's output-contract instruction
  <draft>.policy.json     = per-field compare policy for spec_holes --policy

Selection is a table lookup, not a judgment call — a weak operator runs this
and follows the printed result. Add a family by dropping a JSON file into
contracts/; no code changes needed.

usage: apply_contract.py draft.txt [--dir DIR] [--list]
exit codes: 0 = applied / 1 = no family matches / 2 = unreadable
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spec_holes import has_ja

DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contracts")


def load_templates(cdir):
    tpls = []
    for p in sorted(glob.glob(os.path.join(cdir, "*.json"))):
        try:
            t = json.load(open(p))
            t["_path"] = p
            tpls.append(t)
        except Exception as e:
            print(f"!! skipping unreadable template {p}: {e}")
    return tpls


def pick(task, templates):
    """(template, matched_keywords) で最多ヒットの族を返す。同数はfamily名の辞書順。"""
    low = task.lower()
    best = None
    for t in sorted(templates, key=lambda t: t.get("family", "")):
        hits = [k for k in t.get("match", []) if k.lower() in low]
        if hits and (best is None or len(hits) > len(best[1])):
            best = (t, hits)
    return best


def main():
    ap = argparse.ArgumentParser(description="append a shadow output contract to a free-form draft")
    ap.add_argument("draft", nargs="?", help="draft instruction file")
    ap.add_argument("--dir", default=DEFAULT_DIR, help="contract templates directory")
    ap.add_argument("--list", action="store_true", help="list available families and exit")
    args = ap.parse_args()

    templates = load_templates(args.dir)
    if args.list:
        for t in templates:
            print(f"{t['family']}: match={', '.join(t['match'])}")
        return
    if not args.draft:
        print("!! usage: apply_contract.py draft.txt"); sys.exit(2)
    if not templates:
        print(f"!! no templates found in {args.dir}"); sys.exit(2)
    try:
        task = open(args.draft).read().strip()
    except OSError as e:
        print(f"!! cannot read draft: {e}"); sys.exit(2)

    chosen = pick(task, templates)
    if chosen is None:
        print("no contract family matches this draft "
              f"(families: {', '.join(t['family'] for t in templates)})")
        sys.exit(1)
    t, hits = chosen
    lang = "ja" if has_ja(task) else "en"
    instruction = t[f"instruction_{lang}"]

    root = os.path.splitext(args.draft)[0]
    out_draft = root + ".contracted.txt"
    out_policy = root + ".policy.json"
    open(out_draft, "w").write(task + "\n\n" + instruction + "\n")
    json.dump(t["policy"], open(out_policy, "w"), ensure_ascii=False, indent=1)

    print(f"family: {t['family']} (matched: {', '.join(hits)})")
    print(f"contracted draft: {out_draft}")
    print(f"compare policy:  {out_policy}")
    print(f"render hint:     {t.get(f'render_{lang}', '(none)')}")


if __name__ == "__main__":
    main()
