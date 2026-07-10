#!/usr/bin/env python3
"""SQLエンジン・builtin参照(label_map/code_suffix)・inst/sqlパックの単体テスト(ネットワーク不要)。"""
from _common import dp, chk, finish, PACKS

# --- _extract_sql ---
chk("sql_plain", dp._extract_sql("SELECT * FROM t;"), "SELECT * FROM t")
chk("sql_fence", dp._extract_sql("```sql\nSELECT name FROM t ORDER BY name;\n```"), "SELECT name FROM t ORDER BY name")
chk("sql_with", dp._extract_sql("WITH x AS (SELECT 1) SELECT * FROM x"), "WITH x AS (SELECT 1) SELECT * FROM x")
chk("sql_none", dp._extract_sql("no sql here"), None)

# --- _compile_sql ---
cs = dp._compile_sql(
    ["CREATE TABLE t(name TEXT, v INTEGER)", "INSERT INTO t VALUES ('b',2),('a',1)"],
    [{"label": "asc", "col0": ["a", "b"]},
     {"label": "sum3", "rows": [[3]]},
     {"label": "one", "row_count": 1}],
    "F")
chk("cs_col0", cs("SELECT name FROM t ORDER BY name"), "asc")
chk("cs_count", cs("SELECT * FROM t WHERE v=1"), "one")
chk("cs_rows", cs("SELECT SUM(v) FROM t"), "sum3")
chk("cs_err_dialect", cs("SELECT TOP 2 name FROM t"), "ERR:sql(OperationalError)")
chk("cs_nosql", cs("わかりません"), "ERR:no-sql")

# --- inst_ja / sql_ja パック ---
n1, p1 = dp.load_pack(str(PACKS / "inst_ja.json"))
n2, p2 = dp.load_pack(str(PACKS / "sql_ja.json"))
chk("inst_len", (n1, len(p1)), ("inst_ja", 9))
chk("sql_len", (n2, len(p2)), ("sql_ja", 7))
P1 = {p["id"]: p for p in p1}
P2 = {p["id"]: p for p in p2}
chk("neg_break", P1["meta_negation"]["classify"]("def dedup(l):\n    return list(set(l))"), "禁止を破る(set使用)")
chk("done_ok", P1["meta_contract_done"]["classify"]("2"), "契約遵守(2のみ)")
chk("steps_4", P1["meta_steps_exact"]["classify"]("1. 湯を沸かす\n2. 茶葉を入れる\n3. 注ぐ\n4. 待つ"), "ちょうど4項目(遵守)")
chk("steps_5", P1["meta_steps_exact"]["classify"]("1. a\n2. b\n3. c\n4. d\n5. e"), "項目数違反(5以上)")
chk("p_null_first", P2["sql_null_sort"]["classify"]("SELECT name FROM items ORDER BY price"), "NULLが先頭(sqlite既定)")
chk("p_ties_limit", P2["sql_top_ties"]["classify"]("SELECT name FROM scores ORDER BY score DESC LIMIT 2"), "LIMITで切る(同点の一方を落とす)")
chk("p_case_lower", P2["sql_case_where"]["classify"]("SELECT COUNT(*) FROM users WHERE LOWER(name) = 'alice'"), "大小無視で照合(1件)")
chk("p_join_left", P2["sql_join_missing"]["classify"]("SELECT e.name, d.dname FROM emp e LEFT JOIN dept d ON e.dept_id = d.id"), "LEFT(NULLで残す)")
chk("p_agg_null", P2["sql_empty_agg"]["classify"]("SELECT MAX(price) FROM prods WHERE stock >= 1"), "NULLを返す(SQL既定)")
chk("p_dup_distinct", P2["sql_dup_output"]["classify"]("SELECT DISTINCT buyer FROM purchases"), "DISTINCT(重複除去)")

# --- code_en: builtin参照 + label_map + code_suffix ---
n3, p3 = dp.load_pack(str(PACKS / "code_en.json"))
chk("code_en_name", n3, "code_en")
chk("code_en_len", len(p3), 31)
P3 = {p["id"]: p for p in p3}
chk("q_is_english", P3["missing_key"]["q"].startswith("Write a Python function lookup"), True)
chk("suffix_set", P3["missing_key"].get("suffix"), "\nOutput code only. No explanations or tests.")
chk("names_inherited", P3["missing_key"]["names"], ["lookup", "get_value", "get"])


def raises_keyerror(d, k):
    return d[k]


chk("lm_keyerror", P3["missing_key"]["classify"](raises_keyerror), "raises (KeyError)")
chk("lm_none", P3["missing_key"]["classify"](lambda d, k: d.get(k)), "returns None")
chk("lm_range_incl", P3["range_incl"]["classify"](lambda a, b: list(range(a, b + 1))), "end inclusive")
chk("lm_dynamic_passthru", P3["missing_key"]["classify"](lambda d, k: 99), "他(99)")

# --- inst_en / sql_en ---
n4, p4 = dp.load_pack(str(PACKS / "inst_en.json"))
n5, p5 = dp.load_pack(str(PACKS / "sql_en.json"))
chk("inst_en_len", (n4, len(p4)), ("inst_en", 9))
chk("sql_en_len", (n5, len(p5)), ("sql_en", 7))
P4 = {p["id"]: p for p in p4}
P5 = {p["id"]: p for p in p5}
chk("en_neg_break", P4["meta_negation"]["classify"]("def f(l):\n    return list(set(l))"), "violates prohibition (uses set)")
chk("en_lang_honored", P4["meta_late_constraint"]["classify"]("リモートワークの普及でオフィス利用が大きく変わった。"), "constraint honored (Japanese)")
chk("en_word_variant", P4["meta_forbidden_word"]["classify"]("Coffee has a pleasant bitterness. Rich. Aromatic."), "evades with a variant (bitterness etc.)")
chk("en_sql_case", P5["sql_case_where"]["classify"]("SELECT COUNT(*) FROM users WHERE name='alice' COLLATE NOCASE"), "case-insensitive match (1 row)")

finish("test_sql_builtin")
