"""テスト共通: scripts を import path に載せ、ネットワーク不要の引数で default_probe を読み込む。"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKS = ROOT / "packs"
sys.path.insert(0, str(ROOT / "tools"))
sys.argv = ["default_probe.py", "dummy-model", "http://localhost:1"]  # 自動検出を回避

import default_probe as dp  # noqa: E402

_fails = []


def chk(name, got, want):
    if got != want:
        _fails.append(f"NG {name}: {got!r} != {want!r}")


def finish(label):
    print(f"{label}: {'FAIL' if _fails else 'OK'} ({len(_fails)} failures)")
    for f in _fails:
        print(" ", f)
    sys.exit(1 if _fails else 0)
