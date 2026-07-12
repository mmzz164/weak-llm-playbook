"""llm_client の頑健化(思考ブロック除去・モデル自動検出の順序)の単体テスト。"""
from _common import chk, finish

import llm_client as lc  # noqa: E402 (_common が scripts を path に載せている)

# ---- <think>ブロック除去(ollama等の思考モデル対策)
chk("closed think stripped", lc._strip_think("<think>reasoning...</think>hello"), "hello")
chk("multiple blocks", lc._strip_think("<think>a</think>x<think>b</think>y"), "xy")
chk("truncated think drops tail", lc._strip_think("head <think>never closed"), "head ")
chk("plain text untouched", lc._strip_think("plain [1, 2]"), "plain [1, 2]")

# ---- embedding系モデルを自動検出の後ろへ(ollamaはpull済み全モデルを列挙する)
chk("embed demoted", lc._order_models(["nomic-embed-text", "qwen3:8b"]),
    ["qwen3:8b", "nomic-embed-text"])
chk("stable order for chat models", lc._order_models(["b-model", "a-model"]),
    ["b-model", "a-model"])
chk("all-embed still returned", lc._order_models(["x-embed"]), ["x-embed"])


# ---- /no_think ソフトスイッチの自動フォールバック
# (chat_template_kwargs を無視するサーバー=ollama等で、思考が予算を食い潰し
#  本文が空になったら /no_think 付きで再試行し、効いたら以後常用する)
class FakeTransport(lc.LLMClient):
    def __init__(self, answers):
        super().__init__("m", "http://x", think=False)
        self.answers = list(answers)
        self.prompts = []

    def _openai_raw(self, prompt, temperature, max_tokens):
        self.prompts.append(prompt)
        return self.answers.pop(0)


c = FakeTransport(["<think>ran out of budget", "answer [[1], 2]", "next answer"])
chk("empty-think triggers retry", c.chat("q1"), "answer [[1], 2]")
chk("retry appended /no_think", c.prompts[1].endswith("/no_think"), True)
chk("soft switch remembered", c._soft_nothink, True)
chk("subsequent calls keep it", (c.chat("q2"), c.prompts[2].endswith("/no_think")),
    ("next answer", True))

c2 = FakeTransport(["<think>done</think>real answer"])
chk("normal think stripped without retry", c2.chat("q"), "real answer")
chk("no retry when text present", len(c2.prompts), 1)

finish("test_client")
