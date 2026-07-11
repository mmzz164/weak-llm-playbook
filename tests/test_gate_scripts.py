"""check_inputs.py / check_fixed.py(fixループの機械ゲート)の単体テスト。"""
import json
import pathlib
import subprocess
import sys
import tempfile

from _common import chk, finish, ROOT

SCRIPTS = ROOT / "tools"
import check_inputs as ci  # noqa: E402 (_common が scripts を path に載せている)

# ---- check_code: 完全なセットは指摘ゼロ
FULL = [[[3, 1, 2], 2], [[], 2], [[5], 2], [[2, 2, 1], 2], [[3, 1, 2], 0], [[3, 1, 2], -1]]
_, missing = ci.check_code(FULL, 5)
chk("full set has no missing", missing, [])

# ---- check_code: 1件だけだと count + 5パターンの計6指摘
_, missing = ci.check_code([[[3, 1, 2], 2]], 5)
chk("incomplete set misses 6", len(missing), 6)
tags = " / ".join(m for m, _ in missing)
for pat in ("count", "empty", "size-1", "ties", "zero", "negative"):
    chk(f"incomplete flags {pat}", pat in tags, True)

# ---- 提案をそのままコピペすればPASSに収束する(弱操作者の想定動作)
cur = [[[3, 1, 2], 2]]
for _ in range(3):
    _, missing = ci.check_code(cur, 5)
    if not missing:
        break
    for _, fix in missing:
        if fix.startswith("add: "):
            cur.append(json.loads(fix[5:]))
_, missing = ci.check_code(cur, 5)
chk("following suggestions verbatim converges", missing, [])

# ---- 重複検出
_, missing = ci.check_code([[[1], 1], [[1], 1], [[], 0], [["a", "a"], -1], [[2], 2]], 5)
chk("duplicate tuples flagged", any("duplicate" in m for m, _ in missing), True)

# ---- check_json
_, missing = ci.check_json(["a", "b", "c", "d"], 4)
chk("json ok", missing, [])
_, missing = ci.check_json(["a", "a", "", "b"], 4)
chk("json dup+blank", len(missing), 2)

# ---- detect_kind
chk("kind json", ci.detect_kind(["x"]), "json")
chk("kind code", ci.detect_kind([[1]]), "code")
chk("kind unknown", ci.detect_kind([1]), None)

# ---- CLI end-to-end (exit codes)
with tempfile.TemporaryDirectory() as td:
    p = pathlib.Path(td)

    def run(script, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
                              capture_output=True, text=True).returncode

    (p / "good.json").write_text(json.dumps(FULL))
    chk("cli inputs PASS", run("check_inputs.py", p / "good.json"), 0)
    (p / "few.json").write_text('[[[1, 2], 2]]')
    chk("cli inputs FAIL", run("check_inputs.py", p / "few.json"), 1)
    (p / "arity.json").write_text('[[[1, 2], 2], [[1], 1, 9]]')
    chk("cli mixed arity = 2", run("check_inputs.py", p / "arity.json"), 2)

    draft = "Implement top_n(lst, n)."
    (p / "d.txt").write_text(draft)
    (p / "ok.txt").write_text(draft + "\n\n[Behavior contract — pinned]\n- top_n([3,1,2],2) == [3, 2]\n")
    chk("cli fixed PASS", run("check_fixed.py", p / "d.txt", p / "ok.txt"), 0)
    (p / "same.txt").write_text(draft + "\n")
    chk("cli fixed unchanged PASS", run("check_fixed.py", p / "d.txt", p / "same.txt"), 0)
    (p / "para.txt").write_text("Implement a top-n function.\n\n[Behavior contract]\n- x\n")
    chk("cli paraphrase FAIL", run("check_fixed.py", p / "d.txt", p / "para.txt"), 1)
    (p / "junk.txt").write_text(draft + "\n\nmake it fast and well-documented\n")
    chk("cli junk append FAIL", run("check_fixed.py", p / "d.txt", p / "junk.txt"), 1)

finish("test_gate_scripts")
