#!/usr/bin/env python3
"""K-run prober/runner for tool-requiring tasks — disposable headless agents.

The operator session never holds tool permissions (an interactive agent can be
talked out of any textual restriction). This script launches disposable
headless agent sessions (`claude-local -p`) with an explicit tool allowlist
and a result contract, runs the task K times, and compares the JSON results
field-by-field under a compare policy — the agent-task equivalent of
spec_holes: divergence across runs = a hole in your instruction; agreement =
a default to check against your intent.

usage:
  run_agent.py task.txt [--cmd "claude-local"] [--allowed PATTERN ...]
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


def main():
    ap = argparse.ArgumentParser(description="K-run headless agent prober (tool tasks)")
    ap.add_argument("task", help="task instruction file")
    ap.add_argument("--cmd", default="claude-local", help="agent command (may include args)")
    ap.add_argument("--allowed", action="append", default=[],
                    help="tool allowlist pattern (repeatable), e.g. mcp__mcp-atlassian__*")
    ap.add_argument("-k", type=int, default=3, help="number of runs (default 3 — agent runs are expensive)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds per run (default 900)")
    ap.add_argument("--policy", default=None, help="compare-policy JSON (default: research contract's)")
    ap.add_argument("--contract", choices=["research", "none"], default="research")
    ap.add_argument("--outdir", default=None, help="artifact dir (default: alongside task file)")
    args = ap.parse_args()

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

    outdir = args.outdir or (os.path.splitext(args.task)[0] + ".runs")
    os.makedirs(outdir, exist_ok=True)
    base_cmd = shlex.split(args.cmd)

    results, stats = [], []
    for i in range(args.k):
        cmd = base_cmd + ["-p", task]
        for pat in args.allowed:
            cmd += ["--allowedTools", pat]
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
        stats.append((status, secs, j is not None))
        print(f"run {i}: {status}, {secs:.1f}s, json={'ok' if j is not None else 'MISSING'}")

    valid = [r for r in results if r is not None]
    print(f"\nvalid results: {len(valid)}/{args.k} (artifacts in {outdir}/)")
    if len(valid) < 2:
        print("!! fewer than 2 valid results — cannot compare; check the runs' raw output")
        sys.exit(1)

    diverged, consensus = compare_results(valid, policy)
    print("\n## [DIVERGED] spec holes — fields whose values differ across runs (must specify)")
    if not diverged:
        print("  none (runs agree on every compared field)")
    for key, c in diverged:
        print(f"  ★ {key} → " + " / ".join(f'"{v}" x{n}' for v, n in c.most_common()))
    print("\n## [AGREED] implicit consensus — check against your intent")
    for key, v in consensus:
        print(f"  - {key} → {v}")
    sys.exit(1 if diverged else 0)


if __name__ == "__main__":
    main()
