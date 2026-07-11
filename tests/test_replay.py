"""spec_holes の答え合わせ表(build_expected)と replay_check の照合ロジックの単体テスト。"""
from _common import chk, finish

import replay_check as rc  # noqa: E402 (_common が scripts を path に載せている)
import spec_holes as sh  # noqa: E402

# ---- expected_path / build_expected
chk("expected_path", sh.expected_path("d.fixed.txt"), "d.fixed.expected.json")

tbl = sh.build_expected("code", "top_n", [([[3, 1, 2], 2], "[3, 2]"), ([[], 2], "[]")])
chk("code table kind", tbl["kind"], "code")
chk("code table fn", tbl["fn"], "top_n")
chk("code table rows", len(tbl["expected"]), 2)

jt = sh.build_expected("json", None,
                       [(0, "doc-A…", "name", '"佐藤"'), (1, "doc-B…", "qty", "3")],
                       ["doc-A full text", "doc-B full text"])
chk("json table embeds full doc", jt["expected"][0]["doc"], "doc-A full text")
chk("json table field", jt["expected"][1]["field"], "qty")


# ---- verify_code_fn
def good(lst, n):
    return sorted(lst, reverse=True)[:n]


def bad(lst, n):
    return lst[:n]


chk("code verify pass", rc.verify_code_fn(good, tbl["expected"]), [])
mism = rc.verify_code_fn(bad, tbl["expected"])
chk("code verify catches 1", len(mism), 1)
chk("code verify reports got", mism[0][1], "[3, 1]")


def raiser(x):
    raise KeyError("k")


etbl = sh.build_expected("code", "f", [([[]], "EXC:KeyError")])
chk("exception behavior matches", rc.verify_code_fn(raiser, etbl["expected"]), [])

# ---- verify_json_outputs
exp = [
    {"input": 0, "doc": "d0", "field": "name", "value": '"佐藤"'},
    {"input": 0, "doc": "d0", "field": "memo", "value": "(missing)"},
    {"input": 1, "doc": "d1", "field": "(whole)", "value": "[1, 2]"},
]
chk("json verify pass", rc.verify_json_outputs({0: {"name": "佐藤"}, 1: [1, 2]}, exp), [])

m = rc.verify_json_outputs({0: {"name": "山田", "memo": "x"}, 1: None}, exp)
chk("json verify catches 3", len(m), 3)
chk("wrong value reported", m[0][1], '"山田"')
chk("missing expectation vs present", m[1][1], '"x"')
chk("parse failure label", m[2][1], "JSON_PARSE_FAIL")

finish("test_replay")
