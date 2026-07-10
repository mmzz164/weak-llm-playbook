#!/usr/bin/env python3
"""宣言的ルールエンジン(text/code)とio_enパックの単体テスト(ネットワーク不要)。"""
from _common import dp, chk, finish, PACKS

# --- _rule_match 単体 ---
R = dp._rule_match
chk("regex", R({"regex": "(?i)hello"}, "say HELLO"), True)
chk("contains", R({"contains": "abc"}, "xabcy"), True)
chk("len_lt", R({"len_lt": 5}, "abcd"), True)
chk("len_ge", R({"len_ge": 4}, "abcd"), True)
chk("json_parses_t", R({"json_parses": True}, '[1,2]'), True)
chk("json_parses_f", R({"json_parses": True}, 'x [1,2]'), False)
chk("json_type", R({"json_type": "list"}, 'here: [1,2] ok'), True)
chk("json_only_keys", R({"json_only_keys": ["a"]}, '{"a":1}'), True)
chk("json_only_keys_ng", R({"json_only_keys": ["a"]}, '{"a":1,"b":2}'), False)
chk("jf_equals", R({"json_field": "n", "equals": 3}, '{"n":3}'), True)
chk("jf_null", R({"json_field": "n", "is_null": True}, '{"n":null}'), True)
chk("jf_absent", R({"json_field": "x", "absent": True}, '{"n":1}'), True)
chk("jf_vregex", R({"json_field": "d", "value_regex": "^2026"}, '{"d":"2026-01-02"}'), True)
chk("jf_type_num", R({"json_field": "p", "type": "number"}, '{"p":19.8}'), True)
chk("jf_type_num_not_bool", R({"json_field": "p", "type": "number"}, '{"p":true}'), False)
chk("all", R({"all": [{"contains": "a"}, {"contains": "b"}]}, "ab"), True)
chk("all_ng", R({"all": [{"contains": "a"}, {"contains": "z"}]}, "ab"), False)
chk("any", R({"any": [{"contains": "z"}, {"contains": "b"}]}, "ab"), True)

# --- _compile_text: 順序と fallback ---
ct = dp._compile_text([{"label": "A", "contains": "aa"}, {"label": "B", "regex": "b+"}], "F")
chk("text_first", ct("aa and bbb"), "A")
chk("text_second", ct("bbb"), "B")
chk("text_fallback", ct("zzz"), "F")

# --- _compile_code ---
cc = dp._compile_code([
    {"args": [[]], "result": 0, "label": "zero"},
    {"args": [[]], "exception": True, "label": "raises({type})"},
], "F")
chk("code_result", cc(lambda l: 0), "zero")
chk("code_exc", cc(lambda l: 1 / 0), "raises(ZeroDivisionError)")
chk("code_fallback", cc(lambda l: None), "F")
cc2 = dp._compile_code([{"args": [[1, 2]], "result": [2, 1], "label": "rev"}], "F")
chk("code_norm_tuple", cc2(lambda l: tuple(reversed(l))), "rev")
cc3 = dp._compile_code([{"args": [5], "no_exception": True, "label": "ok"}], "F")
chk("code_noexc", cc3(lambda x: "whatever"), "ok")

# --- io_en パックの代表分類 ---
name, probes = dp.load_pack(str(PACKS / "io_en.json"))
chk("pack_name", name, "io_en")
chk("pack_len", len(probes), 16)
P = {p["id"]: p for p in probes}
chk("en_date_iso", P["io_date_fmt"]["classify"]('{"date": "2026-03-05"}'), "ISO(zero-padded)")
chk("en_date_nojson", P["io_date_fmt"]["classify"]("no json here"), "ERR:no-json")
chk("en_missing_null", P["io_missing_field"]["classify"]('{"name":"John Smith","age":null,"email":null}'), "null-filled")
chk("en_missing_omit", P["io_missing_field"]["classify"]('{"name":"John Smith"}'), "keys omitted")
chk("en_keys_snake", P["io_key_style"]["classify"]('{"author_name":"A","release_date":"2026"}'), "snake_case")
chk("en_price_num", P["io_num_unit"]["classify"]('{"price": 1980}'), "number (no unit)")
chk("en_pure_raw", P["io_pure_json"]["classify"]('[1,2,3,4,5]'), "raw JSON only")
chk("en_pure_fence", P["io_pure_json"]["classify"]('```json\n[1,2,3,4,5]\n```'), "code-fenced")
chk("en_pure_prose", P["io_pure_json"]["classify"]('Here is the array: [1,2,3,4,5].'), "with prose")
chk("en_extra_only", P["io_extra_keys"]["classify"]('{"username":"tanaka"}'), "specified key only")
chk("en_range_low", P["io_range_count"]["classify"]('{"count": 3}'), "lower bound (3)")
chk("en_csv_header", P["io_csv_header"]["classify"]('name,age\nJohn,30\nSara,25'), "header row")
chk("en_lang_ja", P["txt_sum_lang"]["classify"]('リモートワークの普及で企業のオフィス利用が変化し、ハイブリッド勤務が広がっている。'), "input language (Japanese)")
chk("en_lang_en", P["txt_sum_lang"]["classify"]('Remote work reshaped office use; 「フリーアドレス」 spread.'), "instruction language (English)")
chk("en_units_both", P["txt_units"]["classify"]('El paquete pesa 5 libras (unos 2,3 kg).'), "both (converted + original)")
chk("en_clarify_ask", P["txt_clarify"]["classify"]('Could you share the file list? Which files should I sort?'), "asks back (points out missing input)")
chk("en_clarify_howto", P["txt_clarify"]["classify"]('Use `ls -t` to sort by date:\n```bash\nls -t\n```'), "gives instructions/commands")
chk("en_list_num", P["txt_list_style"]["classify"]('1. Grind beans\n2. Boil water'), "numbered (1.)")

finish("test_pack_engine")
