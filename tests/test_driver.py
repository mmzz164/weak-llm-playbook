"""fix.py(手順のコード化ドライバ)と run_agent.py(K回比較)の単体テスト。"""
import io
import os
import tempfile
from collections import Counter
from contextlib import redirect_stdout

from _common import chk, finish

import run_agent as ra  # noqa: E402 (_common が scripts を path に載せている)
import fix as sf  # noqa: E402

# ---- ドラフトの受け取り: ファイル / インライン文字列 / タイポ拒否
_td = tempfile.mkdtemp()
_fp = os.path.join(_td, "d.txt")
open(_fp, "w").write("hello")
chk("file draft passthrough", sf.materialize_draft(_fp), (_fp, "hello", False))
_p, _text, _inline = sf.materialize_draft("インラインの指示文")
chk("inline draft materialized", (_text, _inline, os.path.isfile(_p)),
    ("インラインの指示文", True, True))
try:
    sf.materialize_draft("darft.txt")
    chk("typo guard trips", "no exit", "SystemExit(2)")
except SystemExit as e:
    chk("typo guard exit 2", e.code, 2)

# ---- ルーティング(表引き)
chk("tool word mcp", sf.needs_tools("SORAのチケットをMCPで探して"), "mcp")
chk("tool word jira", sf.needs_tools("Jiraから最新チケットを取得"), "jira")
chk("no tool word", sf.needs_tools("このページをレビューして"), None)
chk("code words ja", sf.looks_like_code("split_csv 関数を実装してください"), True)
chk("code words en", sf.looks_like_code("Implement a parser function."), True)
chk("not code", sf.looks_like_code("この文書を要約して"), False)

# ---- check_inputs FAIL出力からの提案回収
GATE_OUT = """# check_inputs: kind=code, 1 input(s)
[ok] consistent arity (2)
[MISSING] count: only 1 tuple(s), need >= 5 — add more cases from the recipe
[MISSING] pos 0 (list): no empty value — add: [[], 2]
[MISSING] pos 1 (int): no zero — add: [[3, 1, 2], 0]
FAIL: 3 item(s) missing — add the suggested inputs above and rerun"""
adds = sf.parse_added_inputs(GATE_OUT)
chk("collects 2 pasteable adds", adds, [[[], 2], [[3, 1, 2], 0]])

# ---- 入力の機械整形
chk("dedupe code", sf.clean_inputs([[[1], 1], [[1], 1], [[], 0]], "code"),
    [[[1], 1], [[], 0]])
chk("drop blank docs", sf.clean_inputs(["a", " ", "a", "b"], "json"), ["a", "b"])


# ---- コード入力のLLM生成(パース失敗→再試行→成功)
class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)

    def chat(self, prompt, temperature=0.0, max_tokens=0):
        return self.answers.pop(0)


good = FakeClient(['no json here', '[[[3,1,2],2],[[],0]]'])
chk("gen retries then parses", sf.gen_code_inputs(good, "implement f")[0],
    [[[3, 1, 2], 2], [[], 0]])
bad = FakeClient(["nope", "still nope", "```code```"])
cand, last_raw = sf.gen_code_inputs(bad, "implement f")
chk("gen gives up after 3", cand, None)
chk("gen keeps last raw for diagnostics", last_raw, "```code```")

# ---- run_agent: ポリシー付きK回比較
POL = {"results": "count", "count": "exact", "not_found": "exact", "notes": "free"}
A = {"results": [1, 2, 3], "count": 3, "not_found": False, "notes": "x"}
B = {"results": [1, 2, 3, 4, 5], "count": 5, "not_found": False, "notes": "totally different"}
div, cons = ra.compare_results([A, A, B], POL)
chk("diverged fields", sorted(k for k, _ in div), ["count", "results"])
chk("results compared by count", dict(div)["results"], Counter({"len=3": 2, "len=5": 1}))
chk("agreed not_found", ("not_found", "false") in cons, True)
chk("notes excluded (free)", any(k == "notes" for k, _ in div + cons), False)

div, cons = ra.compare_results([A, A, A], POL)
chk("stable agent agrees", div, [])

div, cons = ra.compare_results([[1], [2]], POL)
chk("non-dict falls back to whole", div[0][0], "(whole)")

# ---- SORA実測の再現: 件数が同じ比較(count)では見えない顔ぶれ差を set:id が捕まえる
POL_SET = {"results": "set:id", "count": "exact", "not_found": "exact", "notes": "free"}
ten = {"results": [{"id": f"SORA-{i}"} for i in range(17376, 17386)],
       "count": 10, "not_found": False, "notes": "a"}
ten_other = {"results": [{"id": f"SORA-{i}"} for i in range(17300, 17310)],
             "count": 10, "not_found": False, "notes": "b"}
div, cons = ra.compare_results([ten, ten_other], {"results": "count"})
chk("count policy blind to membership", any(k == "results" for k, _ in div), False)
div, cons = ra.compare_results([ten, ten_other], POL_SET)
chk("set:id catches membership diff", any(k == "results" for k, _ in div), True)
div, cons = ra.compare_results([ten, ten], POL_SET)
chk("set:id agrees on same lineup", div, [])

# ---- run_agent --fix: 発散→ピン行への翻訳
DIV = [("count", Counter({"3": 2, "5": 1})),
       ("results", Counter({'set{"A"}': 2, 'set{"B"}': 1})),
       ("items", Counter({"len=10": 2, "len=5": 1}))]
auto, manual = ra.pin_lines(DIV, ja=True)
chk("scalar pinned with majority", auto[0], '- "count" = 3 とする   # 他候補: 5 (1)')
chk("len pinned as item count", '"items" は 10件とする' in auto[1], True)
chk("set becomes FILL-IN", len(manual), 1)
chk("FILL-IN mentions ordering", "並び順" in manual[0], True)
auto_en, manual_en = ra.pin_lines(DIV, ja=False)
chk("en scalar pin", auto_en[0], '- "count" = 3   # alternatives: 5 (1)')
chk("en FILL-IN", "FILL IN" in manual_en[0], True)

# ---- 多数派なしのタイ(2/4/20等)は自動ピンしない — 先頭値で固定すると誤誘導になる
TIE = [("count", Counter({"2": 1, "4": 1, "20": 1}))]
auto_t, manual_t = ra.pin_lines(TIE, ja=True)
chk("tie: nothing auto-pinned", auto_t, [])
chk("tie: becomes FILL-IN", len(manual_t), 1)
chk("tie: shows observed values", '"2" x1' in manual_t[0] and "多数派なし" in manual_t[0], True)
_, manual_te = ra.pin_lines(TIE, ja=False)
chk("tie: en wording", "no majority" in manual_te[0], True)


# ---- report: 顔ぶれ(set)が割れたら「読み方」の結論行を出す(値の羅列で終わらせない)
def _report_out(div, cons, ja):
    buf = io.StringIO()
    with redirect_stdout(buf):
        ra.report(div, cons, ja)
    return buf.getvalue()


out = _report_out([("results", Counter({'set{"A"}': 1, 'set{"B"}': 1, 'set{"C"}': 1}))],
                  [("not_found", "false")], ja=True)
chk("report: ja reading line on lineup split", "読み方" in out and "列挙" in out, True)
out = _report_out([("results", Counter({'set{"A"}': 2, 'set{"B"}': 1}))], [], ja=False)
chk("report: en reading line", "WHAT to enumerate" in out, True)
out = _report_out([("count", Counter({"3": 2, "5": 1}))], [], ja=True)
chk("report: no reading line without lineup split", "読み方" in out, False)


# ---- 子コマンドの権限: 既定バイパス / --allowed で許可リスト / --no-bypass で素
class _Args:
    def __init__(self, allowed=(), no_bypass=False):
        self.allowed = list(allowed)
        self.no_bypass = no_bypass


chk("default is bypass",
    ra.child_cmd(["claude"], "t", _Args()),
    ["claude", "-p", "t", "--dangerously-skip-permissions"])
chk("--allowed switches bypass off",
    ra.child_cmd(["claude"], "t", _Args(allowed=["mcp__x__*"])),
    ["claude", "-p", "t", "--allowedTools", "mcp__x__*"])
chk("--no-bypass is plain",
    ra.child_cmd(["claude"], "t", _Args(no_bypass=True)),
    ["claude", "-p", "t"])

finish("test_driver")
