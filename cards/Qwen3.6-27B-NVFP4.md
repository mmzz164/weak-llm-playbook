# Delegation guide: Qwen3.6-27B-NVFP4

Auto-generated from default_probe profiles. How to read: **not implementable** → avoid delegation / **unstable** → always specify / **stable** → check against your intent and specify only the mismatches.

| battery | mode | points | not impl. | unstable | stable | out-tok/sample | sec/sample |
|---|---|---|---|---|---|---|---|
| code | nothink | 31 | 0 | 4 | 27 | — | — |
| code_en | nothink | 31 | 0 | 0 | 31 | 32 | 1.1 |
| inst_en | nothink | 9 | 0 | 0 | 9 | 38 | 0.8 |
| inst_ja | nothink | 9 | 0 | 1 | 8 | 44 | 1.4 |
| io | nothink | 18 | 0 | 1 | 17 | — | — |
| io_en | nothink | 16 | 0 | 4 | 12 | — | — |
| sql_en | nothink | 7 | 0 | 0 | 7 | 15 | 0.3 |
| sql_ja | nothink | 7 | 0 | 0 | 7 | 14 | 0.5 |

## Not implementable (explicitness won't save it — avoid delegation or change granularity)
- none

## Must specify (unstable — the model has no default)
- [code] avg_empty: {'例外': 8, '0を返す': 7} (stability 0.53)
- [code] fib_index: {'fib(0)=0,fib(1)=1,fib(2)=1': 8, 'ERR': 7} (stability 0.53)
- [code] clamp_pct: {'0-100%表記': 11, '他(25.00%)': 3, '他(25.0%)': 1} (stability 0.73)
- [code] dup_count: {'他(5)': 8, '他(3)': 4, '他({1: 2, 3: 3})': 1, '重複した値の種類数(2)': 2} (stability 0.53)
- [inst_ja] meta_length_limit: {'軽微超過(〜99字)': 7, '制限遵守(〜55字)': 8} (stability 0.53)
- [io] txt_clarify: {'逆質問(不足を指摘)': 7, '手順/コマンドを答える': 8} (stability 0.53)
- [io_en] io_date_fmt: {'as written (March 5, 2026)': 8, 'ISO(zero-padded)': 7} (stability 0.53)
- [io_en] io_range_count: {'midpoint (4)': 7, 'range kept': 8} (stability 0.53)
- [io_en] txt_sum_length: {'short paragraph (<400 chars)': 11, 'long (>=400 chars)': 4} (stability 0.73)
- [io_en] txt_clarify: {'asks back (points out missing input)': 8, 'gives instructions/commands': 7} (stability 0.53)

## Stable defaults — checklist to compare against your intent (write only the mismatches)
### code
- interval_touch = "接触も統合"
- round_half = "half_up(2.5→3)"
- dedup_order = "順序保持"
- topn_short = "不足時は全件"
- split_case = "大小無視"
- palindrome_norm = "厳密一致"
- neg_modulo = "python式(2)"
- div_zero = "例外(ZeroDiv)"
- range_incl = "終端含む"
- sort_case = "ASCII順"
- split_multi = "空白畳む"
- empty_split = "空リスト"
- missing_key = "例外(KeyError)"
- flatten = "深く平坦化"
- nth_index = "0-indexed"
- none_input = "例外(TypeError)"
- reverse_default = "昇順"
- title_case = "各語頭大文字"
- int_div = "float(1.5)"
- slice_oob = "全件(クランプ)"
- neg_index = "負index許容(末尾)"
- strip_parse = "空白除去して解釈"
- bool_case = "大小無視でTrue"
- date_fmt = "ISO(0埋め)"
- round_ndigits = "小数2桁"
- max_empty = "例外(ValueError)"
- capitalize_rest = "先頭のみ大文字化(残り保持)"

### code_en
- interval_touch = "touching merged"
- round_half = "half-up (2.5→3)"
- avg_empty = "returns 0"
- dedup_order = "order preserved"
- topn_short = "returns all when short"
- split_case = "case-insensitive"
- fib_index = "fib(0)=0,fib(1)=1,fib(2)=1"
- palindrome_norm = "strict comparison"
- neg_modulo = "python-style (2)"
- div_zero = "raises (ZeroDiv)"
- range_incl = "end inclusive"
- sort_case = "ASCII order (uppercase first)"
- split_multi = "collapses whitespace"
- empty_split = "empty list"
- missing_key = "raises (KeyError)"
- flatten = "deep flatten"
- nth_index = "0-indexed"
- none_input = "例外(TypeError)"
- reverse_default = "ascending"
- title_case = "capitalize each word"
- clamp_pct = "0-100 scale"
- int_div = "float(1.5)"
- slice_oob = "clamps (returns all)"
- neg_index = "negative index allowed (tail)"
- strip_parse = "strips whitespace then parses"
- bool_case = "case-insensitive True"
- date_fmt = "ISO (zero-padded)"
- round_ndigits = "2 decimals"
- max_empty = "例外(ValueError)"
- dup_count = "他(5)"
- capitalize_rest = "first letter only (rest kept)"

### inst_en
- meta_negation = "honors prohibition"
- meta_contract_done = "contract honored (bare 2)"
- meta_conflict_order = "follows later instruction (one sentence)"
- meta_late_constraint = "constraint honored (Japanese)"
- meta_early_constraint = "constraint honored (Japanese)"
- meta_length_limit = "slightly over (<=200 chars)"
- meta_forbidden_word = "honors prohibition"
- meta_steps_exact = "exactly 4 items (honored)"
- meta_dont_explain = "code only (honored)"

### inst_ja
- meta_negation = "禁止を守る"
- meta_contract_done = "契約遵守(2のみ)"
- meta_conflict_order = "後の指示に従う(1文)"
- meta_late_constraint = "制約遵守(英語で応答)"
- meta_early_constraint = "制約遵守(英語で応答)"
- meta_forbidden_word = "禁止を守る"
- meta_steps_exact = "ちょうど4項目(遵守)"
- meta_dont_explain = "コードのみ(遵守)"

### io
- io_date_fmt = "ISO(0埋め)"
- io_missing_field = "null埋め"
- io_key_style = "camelCase"
- io_num_unit = "数値(単位なし)"
- io_bool_style = "bool(true)"
- io_pure_json = "コードフェンス付き"
- io_extra_keys = "指定キーのみ"
- io_date_ambig = "MM/DD解釈(1月2日)"
- io_range_count = "中央(4)"
- io_csv_header = "ヘッダあり"
- txt_sum_lang = "入力言語(日本語)で応答"
- txt_sum_format = "散文"
- txt_sum_length = "短段落(240字未満)"
- txt_tone = "敬語"
- txt_name_order = "姓-名(Yamada Taro)"
- txt_units = "単位そのまま(ポンド)"
- txt_list_style = "番号付き(1.)"

### io_en
- io_missing_field = "null-filled"
- io_key_style = "camelCase"
- io_num_unit = "number (no unit)"
- io_bool_style = "bool(true)"
- io_pure_json = "code-fenced"
- io_extra_keys = "specified key only"
- io_date_ambig = "MM/DD (Jan 2)"
- io_csv_header = "header row"
- txt_sum_lang = "input language (Japanese)"
- txt_sum_format = "prose"
- txt_units = "unit kept (pounds)"
- txt_list_style = "numbered (1.)"

### sql_en
- sql_null_sort = "NULLs first (sqlite default)"
- sql_top_ties = "LIMIT cuts a tie"
- sql_case_where = "case-sensitive (0 rows)"
- sql_join_missing = "INNER (drops dept-less employee)"
- sql_empty_agg = "returns NULL (SQL default)"
- sql_dup_output = "DISTINCT (dedup)"
- sql_order_unspec = "ascending"

### sql_ja
- sql_null_sort = "NULLが先頭(sqlite既定)"
- sql_top_ties = "LIMITで切る(同点の一方を落とす)"
- sql_case_where = "大文字小文字を区別(0件)"
- sql_join_missing = "INNER(部署なし従業員を落とす)"
- sql_empty_agg = "NULLを返す(SQL既定)"
- sql_dup_output = "DISTINCT(重複除去)"
- sql_order_unspec = "昇順"

---
Source profiles: code(N=5, ?) / code_en(N=5, http://localhost:8000) / inst_en(N=5, http://localhost:8000) / inst_ja(N=5, http://localhost:8000) / io(N=5, http://localhost:8000) / io_en(N=5, http://localhost:8000) / sql_en(N=5, http://localhost:8000) / sql_ja(N=5, http://localhost:8000)
