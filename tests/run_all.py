#!/usr/bin/env python3
"""全テストランナー: 単体テスト3本+全パックの埋め込みセルフテスト(--validate)。
依存ゼロ(標準ライブラリのみ)。CIからは `python tests/run_all.py` を呼ぶ。"""
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
PROBE = ROOT / "skill" / "weak-llm-playbook" / "scripts" / "default_probe.py"

failed = []

for t in sorted(HERE.glob("test_*.py")):
    r = subprocess.run([sys.executable, str(t)], cwd=str(HERE))
    if r.returncode != 0:
        failed.append(t.name)

for pack in sorted((ROOT / "packs").glob("*.json")):
    r = subprocess.run([sys.executable, str(PROBE), "--probes", str(pack), "--validate"],
                       capture_output=True, text=True)
    tail = (r.stdout or r.stderr).strip().splitlines()
    print(f"validate {pack.name}: {tail[-1] if tail else '(no output)'}")
    if r.returncode != 0:
        failed.append(f"validate:{pack.name}")

if failed:
    print(f"\nFAILED: {failed}")
    sys.exit(1)
print("\nALL PASSED")
