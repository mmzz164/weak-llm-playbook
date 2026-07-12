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

finish("test_client")
