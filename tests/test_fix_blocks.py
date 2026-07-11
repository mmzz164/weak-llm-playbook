#!/usr/bin/env python3
"""spec_holes --fix のピン留めブロック生成の単体テスト(ネットワーク不要)。"""
from collections import Counter

from _common import chk, finish
import spec_holes as sh

chk("ja_detect", sh.has_ja("上位n件を返す"), True)
chk("en_detect", sh.has_ja("return the top n items"), False)

div = [([[3, 1, 2], 2], Counter({"[3, 2]": 3, "[3, 1]": 2})),
       ([[1], 0], Counter({"EXC:ValueError": 4, "[]": 1}))]
b = sh.pin_block_code(div, 5, "top_n", ja=True)
chk("code_ja_head", b.startswith("[挙動の固定"), True)
chk("code_ja_pin", "- top_n([3, 1, 2], 2) == [3, 2]" in b, True)
chk("code_ja_alt", "# 他候補: [3, 1] (2/5)" in b, True)
chk("code_ja_exc", "- top_n([1], 0) は ValueError を送出する" in b, True)
b2 = sh.pin_block_code(div, 5, "top_n", ja=False)
chk("code_en_head", b2.startswith("[Behavior contract"), True)
chk("code_en_alt", "# alternatives: [3, 1] (2/5)" in b2, True)
chk("code_en_exc", "- top_n([1], 0) raises ValueError" in b2, True)

jd = [(0, "山田様 3月5日に", "quantity", Counter({'"3〜5個"': 4, '"3〜5"': 1}))]
jb = sh.pin_block_json(jd, ja=True)
chk("json_ja_head", jb.startswith("[出力の固定"), True)
chk("json_ja_pin", '"quantity" = "3〜5個" とする' in jb, True)
chk("json_ja_alt", '# 他候補: "3〜5" (1)' in jb, True)
jb2 = sh.pin_block_json(jd, ja=False)
chk("json_en_pin", 'for input "山田様 3月5日に…": "quantity" = "3〜5個"' in jb2, True)

finish("test_fix_blocks")
