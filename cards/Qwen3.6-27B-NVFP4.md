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
- [code] avg_empty: {'raises': 8, 'returns 0': 7} (stability 0.53)
- [code] fib_index: {'fib(0)=0,fib(1)=1,fib(2)=1': 8, 'ERR': 7} (stability 0.53)
- [code] clamp_pct: {'0-100 scale': 11, 'other(25.00%)': 3, 'other(25.0%)': 1} (stability 0.73)
- [code] dup_count: {'other(5)': 8, 'other(3)': 4, 'other({1: 2, 3: 3})': 1, 'distinct duplicated values (2)': 2} (stability 0.53)
- [inst_ja] meta_length_limit: {'slightly over (<=99 chars)': 7, 'limit honored (<=55 chars)': 8} (stability 0.53)
- [io] txt_clarify: {'asks back (points out missing input)': 7, 'gives instructions/commands': 8} (stability 0.53)
- [io_en] io_date_fmt: {'as written (March 5, 2026)': 8, 'ISO(zero-padded)': 7} (stability 0.53)
- [io_en] io_range_count: {'midpoint (4)': 7, 'range kept': 8} (stability 0.53)
- [io_en] txt_sum_length: {'short paragraph (<400 chars)': 11, 'long (>=400 chars)': 4} (stability 0.73)
- [io_en] txt_clarify: {'asks back (points out missing input)': 8, 'gives instructions/commands': 7} (stability 0.53)

## Stable defaults — checklist to compare against your intent (write only the mismatches)
### code
- interval_touch = "touching merged"
- round_half = "half_up(2.5→3)"
- dedup_order = "order preserved"
- topn_short = "returns all when short"
- split_case = "case-insensitive"
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
- none_input = "raises (TypeError)"
- reverse_default = "ascending"
- title_case = "capitalize each word"
- int_div = "float(1.5)"
- slice_oob = "clamps (returns all)"
- neg_index = "negative index allowed (tail)"
- strip_parse = "strips whitespace then parses"
- bool_case = "case-insensitive True"
- date_fmt = "ISO (zero-padded)"
- round_ndigits = "2 decimals"
- max_empty = "raises (ValueError)"
- capitalize_rest = "first letter only (rest kept)"

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
- none_input = "raises (TypeError)"
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
- max_empty = "raises (ValueError)"
- dup_count = "other(5)"
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
- meta_negation = "honors prohibition"
- meta_contract_done = "contract honored (bare 2)"
- meta_conflict_order = "follows later instruction (one sentence)"
- meta_late_constraint = "constraint honored (responds in English)"
- meta_early_constraint = "constraint honored (responds in English)"
- meta_forbidden_word = "honors prohibition"
- meta_steps_exact = "exactly 4 items (honored)"
- meta_dont_explain = "code only (honored)"

### io
- io_date_fmt = "ISO (zero-padded)"
- io_missing_field = "null-filled"
- io_key_style = "camelCase"
- io_num_unit = "number (no unit)"
- io_bool_style = "bool(true)"
- io_pure_json = "code-fenced"
- io_extra_keys = "specified key only"
- io_date_ambig = "MM/DD (Jan 2)"
- io_range_count = "midpoint (4)"
- io_csv_header = "header row"
- txt_sum_lang = "input language (Japanese)"
- txt_sum_format = "prose"
- txt_sum_length = "short paragraph (<240 chars)"
- txt_tone = "polite (keigo)"
- txt_name_order = "family-given (Yamada Taro)"
- txt_units = "unit kept (pounds)"
- txt_list_style = "numbered (1.)"

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
- sql_null_sort = "NULLs first (sqlite default)"
- sql_top_ties = "LIMIT cuts a tie"
- sql_case_where = "case-sensitive (0 rows)"
- sql_join_missing = "INNER (drops dept-less employee)"
- sql_empty_agg = "returns NULL (SQL default)"
- sql_dup_output = "DISTINCT (dedup)"
- sql_order_unspec = "ascending"

---
Source profiles: code(N=5, ?) / code_en(N=5, http://localhost:8000) / inst_en(N=5, http://localhost:8000) / inst_ja(N=5, http://localhost:8000) / io(N=5, http://localhost:8000) / io_en(N=5, http://localhost:8000) / sql_en(N=5, http://localhost:8000) / sql_ja(N=5, http://localhost:8000)
