"""同梱デモ(demo/demo.py)のスモークテスト: オフラインで全ループが完走すること。"""
import subprocess
import sys

from _common import chk, finish, ROOT

r = subprocess.run([sys.executable, str(ROOT / "demo" / "demo.py")],
                   capture_output=True, text=True, timeout=120)
chk("demo exits 0", r.returncode, 0)
chk("divergence was found and closed", "[fix] holes: 2 → 0" in r.stdout, True)
chk("execution replay-verified", "REPLAY: PASS" in r.stdout, True)
chk("pins carry alternatives", "# alternatives:" in r.stdout, True)

finish("test_demo")
