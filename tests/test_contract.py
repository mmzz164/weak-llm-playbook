"""影の契約まわりの単体テスト: field_repr(比較ポリシー)/ apply_contract の族選択 /
ポリシーの答え合わせ表への同梱と再生照合。"""
from collections import Counter

from _common import chk, finish, ROOT

import apply_contract as ac  # noqa: E402 (_common が scripts を path に載せている)
import replay_check as rc  # noqa: E402
import spec_holes as sh  # noqa: E402

# ---- field_repr: 比較ポリシー
o = {"issues": [1, 2], "verdict": "ok", "empty": None}
chk("count list", sh.field_repr(o, "issues", "count"), "len=2")
chk("count str", sh.field_repr({"s": "abc"}, "s", "count"), "len=3")
chk("count non-sized falls back to canon", sh.field_repr({"n": 7}, "n", "count"), "7")
chk("exact", sh.field_repr(o, "verdict", "exact"), '"ok"')
chk("exact missing", sh.field_repr(o, "nope", "exact"), "(missing)")
chk("exists present", sh.field_repr(o, "verdict", "exists"), "present")
chk("exists null = absent", sh.field_repr(o, "empty", "exists"), "(absent)")
chk("exists missing = absent", sh.field_repr(o, "nope", "exists"), "(absent)")

# ---- apply_contract: 族選択は表引き
TPL = ac.load_templates(str(ROOT / "skill" / "weak-llm-playbook" / "scripts" / "contracts"))
chk("4 families shipped", sorted(t["family"] for t in TPL),
    ["classify", "research", "review", "summary"])

t, hits = ac.pick("このページをレビューしてください。", TPL)
chk("review matched", t["family"], "review")
t, hits = ac.pick("この問い合わせメールをカテゴリに分類して", TPL)
chk("classify matched (2 hits beat others)", t["family"], "classify")
chk("classify hit count", len(hits), 2)
t, hits = ac.pick("Summarize this article.", TPL)
chk("en summary matched", t["family"], "summary")
chk("poem matches nothing", ac.pick("好きな詩を書いてください。", TPL), None)

for t in TPL:
    for req in ("policy", "instruction_ja", "instruction_en", "render_ja", "render_en"):
        chk(f"{t['family']} has {req}", req in t, True)
    chk(f"{t['family']} has a free field",
        any(v == "free" for v in t["policy"].values()), True)

# ---- ポリシーは答え合わせ表に同梱され、再生照合で同じ変換が使われる
tbl = sh.build_expected("json", None, [(0, "doc…", "issues", "len=1"), (0, "doc…", "verdict", '"minor"')],
                        ["doc full"], {"issues": "count", "verdict": "exact", "summary": "free"})
chk("policy embedded", tbl["policy"]["issues"], "count")

outs = {0: {"issues": [{"type": "typo"}], "verdict": "minor", "summary": "毎回違う自由文"}}
chk("replay with policy passes", rc.verify_json_outputs(outs, tbl["expected"], tbl["policy"]), [])
outs2 = {0: {"issues": [], "verdict": "minor", "summary": "x"}}
m = rc.verify_json_outputs(outs2, tbl["expected"], tbl["policy"])
chk("count mismatch caught", len(m), 1)
chk("count mismatch got", m[0][1], "len=0")

# ---- pinブロックの件数フレーズ
blk = sh.pin_block_json([(0, "lbl", "issues", Counter({"len=2": 3, "len=1": 2}))], ja=False)
chk("en count pin phrase", 'count of "issues" = 2' in blk, True)
blk = sh.pin_block_json([(0, "lbl", "issues", Counter({"len=2": 3, "len=1": 2}))], ja=True)
chk("ja count pin phrase", '"issues" の件数 = 2' in blk, True)

finish("test_contract")
