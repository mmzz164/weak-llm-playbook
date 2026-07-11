#!/usr/bin/env python3
"""Mechanical handoff gate for a prompt fixed by spec_holes --fix.

Verifies, without judgment: the fixed file exists, still contains the original
draft verbatim as a prefix (fixes may only APPEND pinned lines), and — if
anything was appended — that the appended part is a recognized pin block.
Catches the classic weak-operator failure of paraphrasing, "improving" or
truncating the draft instead of appending to it.

usage: check_fixed.py draft.txt fixed.txt
exit codes: 0 = PASS / 1 = FAIL / 2 = unreadable file
"""
import sys

PIN_HEADERS = ("[Behavior contract", "[Output contract", "[挙動の固定", "[出力の固定")


def main():
    if len(sys.argv) != 3:
        print("usage: check_fixed.py draft.txt fixed.txt")
        sys.exit(2)
    try:
        draft = open(sys.argv[1]).read().strip()
        fixed = open(sys.argv[2]).read().strip()
    except OSError as e:
        print(f"!! cannot read file: {e}")
        sys.exit(2)

    if not fixed:
        print(f"FAIL: {sys.argv[2]} is empty")
        sys.exit(1)
    if not fixed.startswith(draft):
        print("FAIL: the fixed prompt no longer starts with the draft verbatim. "
              "Fixes may only APPEND pinned lines — never rewrite, paraphrase or "
              "truncate the draft. Regenerate with: spec_holes.py draft inputs --fix")
        sys.exit(1)
    appended = fixed[len(draft):].strip()
    if not appended:
        print("PASS: unchanged (draft had no holes)")
        return
    if not any(h in appended for h in PIN_HEADERS):
        print("FAIL: something was appended but it is not a recognized pin block "
              f"(expected one of: {', '.join(PIN_HEADERS)}). "
              "Only spec_holes --fix output belongs after the draft.")
        sys.exit(1)
    pins = [l for l in appended.splitlines() if l.strip().startswith("- ")]
    print(f"PASS: draft intact, pin block appended ({len(pins)} pinned line(s))")


if __name__ == "__main__":
    main()
