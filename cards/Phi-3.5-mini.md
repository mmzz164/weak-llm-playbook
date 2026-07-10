# 委譲ガイド: Phi-3.5-mini

プロファイル(default_probe)からの自動生成。判断点の使い方 = **実装不能**は委譲回避 / **揺れる**は必ず明示 / **安定**は意図と照合し、ズレる点だけ明示。

| バッテリー | mode | 判断点 | 実装不能 | 揺れる | 安定 | 出力tok/サンプル | 秒/サンプル |
|---|---|---|---|---|---|---|---|
| code | nothink | 31 | 2 | 0 | 29 | — | — |
| inst_en | nothink | 9 | 0 | 1 | 8 | 114 | 2.6 |
| inst_ja | nothink | 9 | 0 | 1 | 8 | 106 | 2.5 |
| io | nothink | 18 | 0 | 4 | 14 | — | — |
| sql_en | nothink | 7 | 0 | 0 | 7 | 62 | 1.4 |
| sql_ja | nothink | 7 | 2 | 0 | 5 | 61 | 1.5 |

## 実装不能(明示しても救えない — 委譲回避か粒度昇降)
- [code] dedup_order: {'EXEC_ERR:NameError': 2, '順序保持': 1, 'ソート済': 2}
- [code] split_multi: {'EXEC_ERR:ModuleNotFoundError': 2, '空白畳む': 2, 'ERR': 1}
- [sql_ja] sql_empty_agg: {'ERR:sql(OperationalError)': 5}
- [sql_ja] sql_order_unspec: {'ERR:sql(OperationalError)': 6, '昇順': 1}

## 必ず明示(揺れる — このモデルは既定を持たない)
- [inst_en] meta_length_limit: {'limit honored (<=110 chars)': 10, 'slightly over (<=200 chars)': 5} (安定性 0.67)
- [inst_ja] meta_negation: {'禁止を守る': 9, '禁止を破る(set使用)': 6} (安定性 0.6)
- [io] io_missing_field: {'値を発明/他': 11, 'JSON不成立': 4} (安定性 0.73)
- [io] io_csv_header: {'ヘッダなし': 8, 'ヘッダあり': 7} (安定性 0.53)
- [io] txt_name_order: {'姓-名(Yamada Taro)': 2, '名-姓(Taro Yamada)': 2, '他/ローマ字なし': 1} (安定性 0.4)
- [io] txt_clarify: {'手順/コマンドを答える': 10, '逆質問(不足を指摘)': 4, '架空データで進める': 1} (安定性 0.67)

## 安定な既定 — 意図と照合するチェックリスト(ズレる項目だけ指示に書く)
### code
- interval_touch = 「接触も統合」
- round_half = 「half_up(2.5→3)」
- avg_empty = 「例外」
- topn_short = 「不足時は全件」
- split_case = 「大小無視」
- fib_index = 「fib(0)=0,fib(1)=1,fib(2)=1」
- palindrome_norm = 「厳密一致」
- neg_modulo = 「python式(2)」
- div_zero = 「例外(ZeroDiv)」
- range_incl = 「他([2, 3])」
- sort_case = 「ASCII順」
- empty_split = 「空リスト」
- missing_key = 「None返す」
- flatten = 「深く平坦化」
- nth_index = 「0-indexed」
- none_input = 「例外(TypeError)」
- reverse_default = 「昇順」
- title_case = 「各語頭大文字」
- clamp_pct = 「0-100%表記」
- int_div = 「float(1.5)」
- slice_oob = 「全件(クランプ)」
- neg_index = 「負index許容(末尾)」
- strip_parse = 「空白除去して解釈」
- bool_case = 「大小無視でTrue」
- date_fmt = 「他('2026/07/08')」
- round_ndigits = 「小数2桁」
- max_empty = 「例外(IndexError)」
- dup_count = 「重複した値の種類数(2)」
- capitalize_rest = 「先頭のみ大文字化(残り保持)」

### inst_en
- meta_negation = 「honors prohibition」
- meta_contract_done = 「contract honored (bare 2)」
- meta_conflict_order = 「follows later instruction (one sentence)」
- meta_late_constraint = 「constraint honored (Japanese)」
- meta_early_constraint = 「constraint honored (Japanese)」
- meta_forbidden_word = 「honors prohibition」
- meta_steps_exact = 「exactly 4 items (honored)」
- meta_dont_explain = 「code only (honored)」

### inst_ja
- meta_contract_done = 「契約遵守(2のみ)」
- meta_conflict_order = 「後の指示に従う(1文)」
- meta_late_constraint = 「制約無視(日本語で応答)」
- meta_early_constraint = 「制約無視(日本語で応答)」
- meta_length_limit = 「軽微超過(〜99字)」
- meta_forbidden_word = 「禁止を守る」
- meta_steps_exact = 「ちょうど4項目(遵守)」
- meta_dont_explain = 「コードのみ(遵守)」

### io
- io_date_fmt = 「ISO(0埋め)」
- io_key_style = 「camelCase」
- io_num_unit = 「数値(単位なし)」
- io_bool_style = 「bool(true)」
- io_pure_json = 「説明文つき」
- io_extra_keys = 「指定キーのみ」
- io_date_ambig = 「MM/DD解釈(1月2日)」
- io_range_count = 「下限(3)」
- txt_sum_lang = 「入力言語(日本語)で応答」
- txt_sum_format = 「散文」
- txt_sum_length = 「短段落(240字未満)」
- txt_tone = 「敬語」
- txt_units = 「単位そのまま(ポンド)」
- txt_list_style = 「番号付き(1.)」

### sql_en
- sql_null_sort = 「NULLs first (sqlite default)」
- sql_top_ties = 「LIMIT cuts a tie」
- sql_case_where = 「case-insensitive match (1 row)」
- sql_join_missing = 「INNER (drops dept-less employee)」
- sql_empty_agg = 「returns NULL (SQL default)」
- sql_dup_output = 「DISTINCT (dedup)」
- sql_order_unspec = 「ascending」

### sql_ja
- sql_null_sort = 「NULLが先頭(sqlite既定)」
- sql_top_ties = 「LIMITで切る(同点の一方を落とす)」
- sql_case_where = 「大文字小文字を区別(0件)」
- sql_join_missing = 「INNER(部署なし従業員を落とす)」
- sql_dup_output = 「重複そのまま」

---
生成元プロファイル: code(N=5, ?) / inst_en(N=5, http://localhost:8002) / inst_ja(N=5, http://localhost:8002) / io(N=5, http://localhost:8002) / sql_en(N=5, http://localhost:8002) / sql_ja(N=5, http://localhost:8002)
