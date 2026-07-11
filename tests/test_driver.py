"""selffix.py(手順のコード化ドライバ)と run_agent.py(K回比較)の単体テスト。"""
from collections import Counter

from _common import chk, finish

import run_agent as ra  # noqa: E402 (_common が scripts を path に載せている)
import selffix as sf  # noqa: E402

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
chk("gen retries then parses", sf.gen_code_inputs(good, "implement f"),
    [[[3, 1, 2], 2], [[], 0]])
bad = FakeClient(["nope", "still nope", "```code```"])
chk("gen gives up after 3", sf.gen_code_inputs(bad, "implement f"), None)

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

finish("test_driver")
