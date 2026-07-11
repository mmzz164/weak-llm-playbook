# Delegation guide: Phi-3.5-mini

Auto-generated from default_probe profiles. How to read: **not implementable** → avoid delegation / **unstable** → always specify / **stable** → check against your intent and specify only the mismatches.

| battery | mode | points | not impl. | unstable | stable | out-tok/sample | sec/sample |
|---|---|---|---|---|---|---|---|
| code | nothink | 31 | 2 | 0 | 29 | — | — |
| inst_en | nothink | 9 | 0 | 1 | 8 | 114 | 2.6 |
| inst_ja | nothink | 9 | 0 | 1 | 8 | 106 | 2.5 |
| io | nothink | 18 | 0 | 4 | 14 | — | — |
| sql_en | nothink | 7 | 0 | 0 | 7 | 62 | 1.4 |
| sql_ja | nothink | 7 | 2 | 0 | 5 | 61 | 1.5 |

## Not implementable (explicitness won't save it — avoid delegation or change granularity)
- [code] dedup_order: {'EXEC_ERR:NameError': 2, 'order preserved': 1, 'sorted': 2}
- [code] split_multi: {'EXEC_ERR:ModuleNotFoundError': 2, 'collapses whitespace': 2, 'ERR': 1}
- [sql_ja] sql_empty_agg: {'ERR:sql(OperationalError)': 5}
- [sql_ja] sql_order_unspec: {'ERR:sql(OperationalError)': 6, 'ascending': 1}

## Must specify (unstable — the model has no default)
- [inst_en] meta_length_limit: {'limit honored (<=110 chars)': 10, 'slightly over (<=200 chars)': 5} (stability 0.67)
- [inst_ja] meta_negation: {'honors prohibition': 9, 'violates prohibition (uses set)': 6} (stability 0.6)
- [io] io_missing_field: {'values invented/other': 11, 'ERR:no-json': 4} (stability 0.73)
- [io] io_csv_header: {'no header': 8, 'header row': 7} (stability 0.53)
- [io] txt_name_order: {'family-given (Yamada Taro)': 2, 'given-family (Taro Yamada)': 2, 'other/no romaji': 1} (stability 0.4)
- [io] txt_clarify: {'gives instructions/commands': 10, 'asks back (points out missing input)': 4, 'fabricates data': 1} (stability 0.67)

## Stable defaults — checklist to compare against your intent (write only the mismatches)
### code
- interval_touch = "touching merged"
- round_half = "half_up(2.5→3)"
- avg_empty = "raises"
- topn_short = "returns all when short"
- split_case = "case-insensitive"
- fib_index = "fib(0)=0,fib(1)=1,fib(2)=1"
- palindrome_norm = "strict comparison"
- neg_modulo = "python-style (2)"
- div_zero = "raises (ZeroDiv)"
- range_incl = "other([2, 3])"
- sort_case = "ASCII order (uppercase first)"
- empty_split = "empty list"
- missing_key = "returns None"
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
- date_fmt = "other('2026/07/08')"
- round_ndigits = "2 decimals"
- max_empty = "raises (IndexError)"
- dup_count = "distinct duplicated values (2)"
- capitalize_rest = "first letter only (rest kept)"

### inst_en
- meta_negation = "honors prohibition"
- meta_contract_done = "contract honored (bare 2)"
- meta_conflict_order = "follows later instruction (one sentence)"
- meta_late_constraint = "constraint honored (Japanese)"
- meta_early_constraint = "constraint honored (Japanese)"
- meta_forbidden_word = "honors prohibition"
- meta_steps_exact = "exactly 4 items (honored)"
- meta_dont_explain = "code only (honored)"

### inst_ja
- meta_contract_done = "contract honored (bare 2)"
- meta_conflict_order = "follows later instruction (one sentence)"
- meta_late_constraint = "constraint ignored (responds in Japanese)"
- meta_early_constraint = "constraint ignored (responds in Japanese)"
- meta_length_limit = "slightly over (<=99 chars)"
- meta_forbidden_word = "honors prohibition"
- meta_steps_exact = "exactly 4 items (honored)"
- meta_dont_explain = "code only (honored)"

### io
- io_date_fmt = "ISO (zero-padded)"
- io_key_style = "camelCase"
- io_num_unit = "number (no unit)"
- io_bool_style = "bool(true)"
- io_pure_json = "with prose"
- io_extra_keys = "specified key only"
- io_date_ambig = "MM/DD (Jan 2)"
- io_range_count = "lower bound (3)"
- txt_sum_lang = "input language (Japanese)"
- txt_sum_format = "prose"
- txt_sum_length = "short paragraph (<240 chars)"
- txt_tone = "polite (keigo)"
- txt_units = "unit kept (pounds)"
- txt_list_style = "numbered (1.)"

### sql_en
- sql_null_sort = "NULLs first (sqlite default)"
- sql_top_ties = "LIMIT cuts a tie"
- sql_case_where = "case-insensitive match (1 row)"
- sql_join_missing = "INNER (drops dept-less employee)"
- sql_empty_agg = "returns NULL (SQL default)"
- sql_dup_output = "DISTINCT (dedup)"
- sql_order_unspec = "ascending"

### sql_ja
- sql_null_sort = "NULLs first (sqlite default)"
- sql_top_ties = "LIMIT cuts a tie"
- sql_case_where = "case-sensitive (0 rows)"
- sql_join_missing = "INNER (drops dept-less employee)"
- sql_dup_output = "duplicates kept"

---
Source profiles: code(N=5, ?) / inst_en(N=5, http://localhost:8002) / inst_ja(N=5, http://localhost:8002) / io(N=5, http://localhost:8002) / sql_en(N=5, http://localhost:8002) / sql_ja(N=5, http://localhost:8002)
