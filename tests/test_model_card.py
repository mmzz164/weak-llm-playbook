#!/usr/bin/env python3
"""model_card.py の単体テスト(合成プロファイル+同梱プロファイル、ネットワーク不要)。"""
import json

from _common import chk, finish, ROOT
import model_card as mc

# --- is_err / split_rows ---
chk("err_exec", mc.is_err("EXEC_ERR:NameError"), True)
chk("err_sql", mc.is_err("ERR:sql(OperationalError)"), True)
chk("err_json", mc.is_err("JSON不成立"), True)
chk("ok_label", mc.is_err("null埋め"), False)

rows = [
    {"id": "a", "default": "X", "stability": 1.0, "n": 5, "dist": {"X": 5}, "canonical": "X"},
    {"id": "b", "default": "Y", "stability": 0.6, "n": 15, "dist": {"Y": 9, "Z": 6}, "canonical": "Y"},
    {"id": "c", "default": "ERR:no-json", "stability": 1.0, "n": 5, "dist": {"ERR:no-json": 5}, "canonical": "ERR:no-json"},
]
ne, un, st = mc.split_rows(rows)
chk("split", ([r["id"] for r in ne], [r["id"] for r in un], [r["id"] for r in st]),
    (["c"], ["b"], ["a"]))

# --- render_model: 3セクションと表が出る ---
prof = {"model": "TestModel", "mode": "nothink", "N": 5, "base": "http://x", "domain": "io",
        "rows": rows}
md = mc.render_model("TestModel", [prof])
for want in ("# 委譲ガイド: TestModel", "| io | nothink | 3 | 1 | 1 | 1 |",
             "## 実装不能", "- [io] c:", "## 必ず明示", "- [io] b:", "安定な既定", "- a = 「X」"):
    chk(f"md has {want[:20]!r}", want in md, True)

# --- 同梱プロファイル全部でクラッシュしないこと(モデルごとにカードが出る) ---
files = sorted(str(p) for p in (ROOT / "profiles").glob("profile_*.json"))
out = mc.build_cards(files)
chk("bundled_qwen", "# 委譲ガイド: Qwen3.6-27B-NVFP4" in out, True)
chk("bundled_phi", "# 委譲ガイド: Phi-3.5-mini" in out, True)

finish("test_model_card")
