#!/usr/bin/env python3
"""既定プローブ・ハーネス.
モデルごとに「明示しなくても選ぶ既定挙動」を測る. 各プローブは1点だけ未指定の極小タスク.
生成コードを実行しどちらの既定を選んだか分類. N回繰り返して 既定 と 安定性 を出す.

使い方: python3 default_probe.py [model] [base_url] [N]
  例: python3 default_probe.py Qwen3.6-27B-NVFP4 http://localhost:8000 5
  model省略時(openai互換のみ): /v1/models から自動検出
  例: python3 default_probe.py "" http://localhost:8000 5   ← ""でも省略でも可
  --domain io で「コーディング以外」の判断点(構造化出力・抽出・文章・対話メタ)を測定。
  --domain all で両バッテリー。既定は code(従来の32点)。
"""
import sys, json, re, urllib.request, types

# diffモード: python3 default_probe.py --diff A.json B.json
if len(sys.argv) > 1 and sys.argv[1] == "--diff":
    import json as _j
    A = _j.load(open(sys.argv[2])); B = _j.load(open(sys.argv[3]))
    ma, mb = A["model"], B["model"]
    da = {r["id"]: r for r in A["rows"]}; db = {r["id"]: r for r in B["rows"]}
    print(f"# 既定プロファイル diff: A={ma}  vs  B={mb}")
    print(f"{'probe':<18} {'A既定':<20} {'B既定':<20} 差分")
    diffs = []
    for pid in da:
        a, b = da[pid], db.get(pid)
        if not b: continue
        ca, cb = a["canonical"], b["canonical"]
        sa, sb = a["stability"], b["stability"]
        flag = ""
        if ca != cb: flag = "★既定が違う"
        elif sa < 0.8 or sb < 0.8: flag = "△どちらか不安定"
        print(f"{pid:<18} {ca[:20]:<20} {cb[:20]:<20} {flag}")
        if flag: diffs.append((pid, ca, cb, sa, sb, flag))
    print(f"\n## モデル差のある判断点(={len(diffs)}件): ここは『モデルを替えたら書き換える』対象")
    for pid, ca, cb, sa, sb, flag in diffs:
        print(f"  - {pid}: {ma}=「{ca}」(安定{sa}) / {mb}=「{cb}」(安定{sb})  {flag}")
    print("\nこの差分表 = 同じ意図でもモデルによって明示すべき点が入れ替わる箇所。")
    sys.exit(0)

import argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model, find_json

ap = argparse.ArgumentParser(description="既定プローブ(任意エンドポイント対応)")
ap.add_argument("model", nargs="?", default=None,
                help="省略(または\"\")で /v1/models から自動検出 (openai互換のみ)")
ap.add_argument("base",  nargs="?", default="http://localhost:8000")
ap.add_argument("n",     nargs="?", type=int, default=5)
ap.add_argument("mode",  nargs="?", default="nothink", help="think で思考モード")
ap.add_argument("--api", choices=["openai", "anthropic"], default="openai",
                help="エンドポイント形式 (既定: openai互換 /v1/chat/completions)")
ap.add_argument("--key", default=None, help="APIキー (省略時 PROBE_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY)")
ap.add_argument("--only", default=None, help="実行する判断点をカンマ区切りで限定 (例: missing_key,range_incl)")
ap.add_argument("--domain", choices=["code", "io", "all"], default="code",
                help="判断点バッテリー: code=コーディング(既定) / io=構造化出力・抽出・文章 / all=両方")
_argv = sys.argv[1:]
if _argv and _argv[0].startswith(("http://", "https://")):
    _argv.insert(0, "")   # 先頭がURL = model省略とみなし繰り上げ
args = ap.parse_args(_argv)
MODEL, BASE, N = args.model, args.base, args.n
if not MODEL:
    if args.api == "anthropic":
        ap.error("--api anthropic では model を明示してください(自動検出は openai互換の /v1/models のみ)")
    _models = detect_model(BASE, args.key)
    MODEL = _models[0]
    print(f"# model未指定 → {BASE}/v1/models から自動検出: {MODEL}"
          + (f" (他{len(_models)-1}件: {', '.join(_models[1:4])})" if len(_models) > 1 else ""))
THINK = args.mode in ("1", "think", "true")
CLIENT = LLMClient(MODEL, BASE, api=args.api, key=args.key, think=THINK)

def gen(prompt, temperature, code=True):
    if code:
        return CLIENT.chat(prompt + "\nコードのみ出力。説明・テスト不要。",
                           temperature=temperature, max_tokens=2000 if THINK else 400)
    # textプローブ: 出力指示はプローブ文自身が持つ。要約・返信が切れないよう上限は広め
    return CLIENT.chat(prompt, temperature=temperature, max_tokens=2000 if THINK else 600)

def extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def load_fn(code, names):
    mod = types.ModuleType("probe")
    try:
        exec(code, mod.__dict__)
    except Exception as e:
        return None, f"EXEC_ERR:{type(e).__name__}"
    for n in names:
        if hasattr(mod, n) and callable(getattr(mod, n)):
            return getattr(mod, n), None
    # fallback: 最初の関数
    for k, v in mod.__dict__.items():
        if callable(v) and not k.startswith("_") and isinstance(v, types.FunctionType):
            return v, None
    return None, "NO_FUNC"

# 各プローブ: prompt / 関数名候補 / classify(fn)->ラベル
# classify は「どちらの既定を選んだか」を短いラベルで返す. 例外は "ERR" 扱い.
PROBES = [
    dict(
        id="interval_touch",
        q="Pythonで区間[start,end]のリストを受け取り、重なる区間を統合して返す関数 merge_intervals を書いて。",
        names=["merge_intervals","merge"],
        classify=lambda f: "接触も統合" if f([[1,2],[2,3]])==[[1,3]] else ("接触は非統合" if f([[1,2],[2,3]])==[[1,2],[2,3]] else "他"),
    ),
    dict(
        id="round_half",
        q="Pythonで float を最も近い整数に丸める関数 round_half を書いて。",
        names=["round_half","round_to_int"],
        classify=lambda f: "half_up(2.5→3)" if f(2.5)==3 else ("banker(2.5→2)" if f(2.5)==2 else "他"),
    ),
    dict(
        id="avg_empty",
        q="Pythonで数値リストの平均を返す関数 average を書いて。",
        names=["average","avg","mean"],
        classify=lambda f: _try(f, [], zero="0を返す", err="例外", ok0=lambda r: r==0),
    ),
    dict(
        id="dedup_order",
        q="Pythonでリストから重複を除く関数 dedup を書いて。",
        names=["dedup","dedupe","unique"],
        classify=lambda f: ("順序保持" if list(f([3,1,3,2,1]))==[3,1,2] else ("ソート済" if list(f([3,1,3,2,1]))==[1,2,3] else "他")),
    ),
    dict(
        id="topn_short",
        q="Pythonでリストと数nを受け取り上位n件を返す関数 top_n を書いて(降順)。",
        names=["top_n","topn"],
        classify=lambda f: _try2(f, [1,2], 5, short="不足時は全件", err="例外/エラー"),
    ),
    dict(
        id="split_case",
        q="Pythonで文章中の単語の出現回数を数える関数 word_count を書いて(dictで返す)。",
        names=["word_count","count_words"],
        classify=lambda f: _try_wc(f),
    ),
    dict(
        id="fib_index",
        q="Pythonでn番目のフィボナッチ数を返す関数 fib を書いて。",
        names=["fib","fibonacci"],
        classify=lambda f: _try_fib(f),
    ),
    dict(
        id="palindrome_norm",
        q="Pythonで文字列が回文か判定する関数 is_palindrome を書いて。",
        names=["is_palindrome"],
        classify=lambda f: ("正規化する" if f("A man a plan a canal Panama")==True else ("厳密一致" if f("A man a plan a canal Panama")==False else "他")),
    ),
    dict(id="neg_modulo", q="Pythonで整数aをbで割った剰余を返す関数 mod(a,b) を書いて。",
         names=["mod","modulo","remainder"], classify=lambda f: _p_neg_modulo(f)),
    dict(id="div_zero", q="Pythonでa÷bを計算して返す関数 divide(a,b) を書いて。",
         names=["divide","div"], classify=lambda f: _p_div_zero(f)),
    dict(id="range_incl", q="Pythonで整数aからbまでの数のリストを返す関数 numbers_between(a,b) を書いて。",
         names=["numbers_between","nums_between","int_range"], classify=lambda f: _p_range_incl(f)),
    dict(id="sort_case", q="Pythonで文字列リストをアルファベット順に並べ替える関数 sort_names を書いて。",
         names=["sort_names","sort_strings"], classify=lambda f: _p_sort_case(f)),
    dict(id="split_multi", q="Pythonで文章を単語に分割してリストで返す関数 tokenize(text) を書いて。",
         names=["tokenize","split_words","words"], classify=lambda f: _p_split_multi(f)),
    dict(id="empty_split", q="Pythonで文章を空白で単語に分割する関数 split_words(text) を書いて。",
         names=["split_words","tokenize"], classify=lambda f: _p_empty_split(f)),
    dict(id="missing_key", q="Pythonで辞書dからキーkの値を取り出す関数 lookup(d,k) を書いて。",
         names=["lookup","get_value","get"], classify=lambda f: _p_missing_key(f)),
    dict(id="flatten", q="Pythonでネストしたリストを平坦化する関数 flatten を書いて。",
         names=["flatten"], classify=lambda f: _p_flatten(f)),
    dict(id="nth_index", q="Pythonでリストのn番目の要素を返す関数 get_nth(lst,n) を書いて。",
         names=["get_nth","nth","get_element"], classify=lambda f: _p_nth_index(f)),
    dict(id="none_input", q="Pythonでリストの要素数を返す関数 count_items(lst) を書いて。",
         names=["count_items","count","size"], classify=lambda f: _p_none_input(f)),
    dict(id="reverse_default", q="Pythonで数値リストを並べ替える関数 sort_numbers を書いて。",
         names=["sort_numbers","sort_nums","sort_list"], classify=lambda f: _p_reverse_default(f)),
    dict(id="title_case", q="Pythonで文字列を見出し(タイトル)用に整形する関数 titlecase(text) を書いて。",
         names=["titlecase","title_case","to_title"], classify=lambda f: _p_title_case(f)),
    dict(id="clamp_pct", q="Pythonで比率(0.0〜1.0)をパーセンテージに変換する関数 to_percent(x) を書いて。",
         names=["to_percent","percent","pct"], classify=lambda f: _p_clamp_pct(f)),
    dict(id="int_div", q="Pythonで数値リストの平均を返す関数 mean_value を書いて。",
         names=["mean_value","mean","average"], classify=lambda f: _p_int_div(f)),
    dict(id="slice_oob", q="Pythonでリストの先頭からn個を返す関数 take(lst,n) を書いて。",
         names=["take","first_n","head"], classify=lambda f: _p_slice_oob(f)),
    dict(id="neg_index", q="Pythonでリストのi番目の要素を返す関数 at(lst,i) を書いて。",
         names=["at","get_at","element"], classify=lambda f: _p_neg_index(f)),
    dict(id="strip_parse", q="Pythonで文字列を整数に変換する関数 to_int(s) を書いて。",
         names=["to_int","parse_int","str_to_int"], classify=lambda f: _p_strip_parse(f)),
    dict(id="bool_case", q="Pythonで文字列を真偽値に変換する関数 to_bool(s) を書いて。",
         names=["to_bool","parse_bool","str_to_bool"], classify=lambda f: _p_bool_case(f)),
    dict(id="date_fmt", q="Pythonで年・月・日から日付文字列を作る関数 format_date(y,m,d) を書いて。",
         names=["format_date","make_date","date_str"], classify=lambda f: _p_date_fmt(f)),
    dict(id="round_ndigits", q="Pythonで金額(float)を表示用に丸める関数 round_money(x) を書いて。",
         names=["round_money","round_amount","format_money"], classify=lambda f: _p_round_ndigits(f)),
    dict(id="max_empty", q="Pythonでリストの最大値を返す関数 maximum(lst) を書いて。",
         names=["maximum","max_value","get_max"], classify=lambda f: _p_max_empty(f)),
    dict(id="dup_count", q="Pythonでリスト中の重複の数を数える関数 count_duplicates(lst) を書いて。",
         names=["count_duplicates","count_dups","duplicates"], classify=lambda f: _p_dup_count(f)),
    dict(id="capitalize_rest", q="Pythonで文字列の先頭を大文字にする関数 capitalize_first(s) を書いて。",
         names=["capitalize_first","cap_first","capitalize"], classify=lambda f: _p_capitalize_rest(f)),
]

def _try(f, arg, zero, err, ok0):
    try:
        r = f(arg)
        return zero if ok0(r) else f"他({r!r})"
    except Exception:
        return err

def _try2(f, lst, n, short, err):
    try:
        r = f(lst, n)
        return short if list(r)==[2,1] or list(r)==[1,2] else f"他({list(r)!r})"
    except Exception:
        return err

def _try_wc(f):
    try:
        r = f("The the THE cat")
        the = sum(v for k,v in r.items() if k.lower()=="the")
        if the==3: return "大小無視"
        if r.get("the",0)==1 and r.get("The",0)==1: return "大小区別"
        return f"他({dict(r)!r})"
    except Exception:
        return "ERR"

def _try_fib(f):
    try:
        v0, v1, v2 = f(0), f(1), f(2)
        return f"fib(0)={v0},fib(1)={v1},fib(2)={v2}"
    except Exception:
        return "ERR"

import math as _math
def _p_neg_modulo(f):
    try:
        r=f(-7,3); return "python式(2)" if r==2 else ("C式(-1)" if r==-1 else f"他({r})")
    except Exception: return "ERR"
def _p_div_zero(f):
    try:
        r=f(1,0)
        if r is None: return "None返す"
        if isinstance(r,float) and _math.isinf(r): return "inf返す"
        return f"他({r})"
    except ZeroDivisionError: return "例外(ZeroDiv)"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_range_incl(f):
    try:
        r=list(f(1,4))
        if r==[1,2,3,4]: return "終端含む"
        if r==[1,2,3]: return "終端含まず"
        return f"他({r})"
    except Exception: return "ERR"
def _p_sort_case(f):
    try:
        r=list(f(["banana","apple","Cherry"]))
        if r==["apple","banana","Cherry"]: return "大小無視"
        if r==["Cherry","apple","banana"]: return "ASCII順"
        return f"他({r})"
    except Exception: return "ERR"
def _p_split_multi(f):
    try:
        r=list(f("a  b"))
        if r==["a","b"]: return "空白畳む"
        if r==["a","","b"]: return "空要素残す"
        return f"他({r})"
    except Exception: return "ERR"
def _p_empty_split(f):
    try:
        r=list(f(""))
        if r==[]: return "空リスト"
        if r==[""]: return "空文字1件"
        return f"他({r})"
    except Exception: return "ERR"
def _p_missing_key(f):
    try:
        r=f({"a":1},"x")
        if r is None: return "None返す"
        return f"他({r})"
    except KeyError: return "例外(KeyError)"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_flatten(f):
    try:
        r=list(f([1,[2,[3,4]]]))
        if r==[1,2,3,4]: return "深く平坦化"
        if r==[1,2,[3,4]]: return "1段のみ"
        return f"他({r})"
    except Exception: return "ERR"
def _p_nth_index(f):
    try:
        r=f([10,20,30],1)
        if r==10: return "1-indexed"
        if r==20: return "0-indexed"
        return f"他({r})"
    except Exception: return "ERR"
def _p_none_input(f):
    try:
        r=f(None)
        if r==0: return "空扱い(0)"
        return f"他({r})"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_reverse_default(f):
    try:
        r=list(f([3,1,2]))
        if r==[1,2,3]: return "昇順"
        if r==[3,2,1]: return "降順"
        return f"他({r})"
    except Exception: return "ERR"
def _p_title_case(f):
    try:
        r=f("hello world")
        if r=="Hello World": return "各語頭大文字"
        if r=="Hello world": return "文頭のみ"
        return f"他({r!r})"
    except Exception: return "ERR"
def _p_clamp_pct(f):
    try:
        r=f(0.25)
        if r in (25, 25.0): return "0-100%表記"
        if r in (0.25,): return "0-1のまま"
        return f"他({r})"
    except Exception: return "ERR"
def _p_int_div(f):
    try:
        r=f([1,2])
        if r==1.5: return "float(1.5)"
        if r==1: return "int切り捨て(1)"
        return f"他({r})"
    except Exception: return "ERR"
def _p_slice_oob(f):
    try:
        r=list(f([1,2,3],5))
        if r==[1,2,3]: return "全件(クランプ)"
        return f"他({r})"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_neg_index(f):
    try:
        r=f([10,20,30],-1)
        if r==30: return "負index許容(末尾)"
        return f"他({r})"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_strip_parse(f):
    try:
        r=f(" 42 ")
        if r==42: return "空白除去して解釈"
        return f"他({r!r})"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_bool_case(f):
    try:
        vals=[f("true"),f("True"),f("TRUE")]
        if all(v is True for v in vals): return "大小無視でTrue"
        if f("true") is True and f("True") is not True: return "小文字のみ"
        return f"他({vals})"
    except Exception: return "ERR"
def _p_date_fmt(f):
    try:
        r=str(f(2026,7,8))
        if r=="2026-07-08": return "ISO(0埋め)"
        if r in ("2026-7-8","2026/7/8"): return "非0埋め/他区切り"
        return f"他({r!r})"
    except Exception: return "ERR"
def _p_round_ndigits(f):
    try:
        r=f(3.14159)
        if r==3.14: return "小数2桁"
        if r==3: return "整数丸め"
        if r==3.1: return "小数1桁"
        return f"他({r})"
    except Exception: return "ERR"
def _p_max_empty(f):
    try:
        r=f([])
        if r is None: return "None返す"
        return f"他({r})"
    except Exception as e: return f"例外({type(e).__name__})"
def _p_dup_count(f):
    try:
        r=f([1,1,2,3,3,3])
        if r in (2,): return "重複した値の種類数(2)"
        if r in (4,): return "余分な出現数(4)"
        return f"他({r})"
    except Exception: return "ERR"
def _p_capitalize_rest(f):
    try:
        r=f("hELLO")
        if r=="Hello": return "残りを小文字化"
        if r=="HELLO": return "先頭のみ大文字化(残り保持)"
        return f"他({r!r})"
    except Exception: return "ERR"
def _p_sort_mixed(f):
    try:
        r=f([3,1,2,"a"])
        return f"他/成功({r})"
    except Exception as e: return f"例外({type(e).__name__})"

# ==== io バッテリー: コーディング以外の判断点(構造化出力・抽出・文章・対話メタ) ====
# kind="text": 生成コードの実行ではなく、出力テキストそのものを決定論的に分類する。

_find_json = find_json   # llm_client.find_json を共用

def _strip_fence(text):
    m = re.search(r"```[a-z]*\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def _io_date(t):
    j = _find_json(t)
    v = str(j.get("date")) if isinstance(j, dict) and j.get("date") is not None else None
    if v is None: return "JSON不成立/キー欠落"
    if v == "2026-03-05": return "ISO(0埋め)"
    if re.match(r"2026[/.]0?3[/.]0?5", v): return "スラッシュ等"
    if "3月5日" in v: return "和文のまま"
    return f"他({v[:20]})"

def _io_missing(t):
    j = _find_json(t)
    if not isinstance(j, dict): return "JSON不成立"
    if "age" not in j and "email" not in j: return "キー省略"
    vals = [j.get("age"), j.get("email")]
    if all(v is None for v in vals): return "null埋め"
    if all(v == "" for v in vals if v is not None): return "空文字埋め"
    return "値を発明/他"

def _io_keys(t):
    j = _find_json(t)
    if not isinstance(j, dict) or not j: return "JSON不成立"
    ks = list(j.keys())
    if any("_" in k for k in ks): return "snake_case"
    if any(re.search(r"[a-z][A-Z]", k) for k in ks): return "camelCase"
    return "単語のみ/他"

def _io_price(t):
    j = _find_json(t)
    v = j.get("price") if isinstance(j, dict) else None
    if isinstance(v, (int, float)): return "数値(単位なし)"
    if isinstance(v, str):
        if "円" in v: return "文字列(単位つき)"
        if v.replace(",", "").isdigit(): return "文字列(数値)"
    return "JSON不成立/他"

def _io_bool(t):
    j = _find_json(t)
    v = j.get("in_stock") if isinstance(j, dict) else None
    if v is True: return "bool(true)"
    if isinstance(v, str): return f"文字列({v[:10]})"
    if v == 1: return "数値(1)"
    return "JSON不成立/他"

def _io_pure(t):
    s = t.strip()
    try:
        json.loads(s); return "生JSONのみ"
    except Exception:
        pass
    if s.startswith("```"): return "コードフェンス付き"
    if _find_json(s) is not None: return "説明文つき"
    return "JSONなし"

def _io_extra(t):
    j = _find_json(t)
    if not isinstance(j, dict): return "JSON不成立"
    return "指定キーのみ" if set(j.keys()) == {"username"} else "キー追加"

def _io_dambig(t):
    if "2026-01-02" in t: return "MM/DD解釈(1月2日)"
    if "2026-02-01" in t: return "DD/MM解釈(2月1日)"
    return "他/変換せず"

def _io_range(t):
    j = _find_json(t)
    v = j.get("count") if isinstance(j, dict) else None
    if v == 3: return "下限(3)"
    if v == 5: return "上限(5)"
    if v == 4: return "中央(4)"
    if isinstance(v, (list, str)): return "範囲のまま"
    return "JSON不成立/他"

def _io_csv(t):
    body = _strip_fence(t)
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines: return "出力なし"
    first = lines[0]
    if re.search(r"名前|氏名|name|年齢|age", first, re.I): return "ヘッダあり"
    if re.search(r"田中|佐藤|30|25", first): return "ヘッダなし"
    return "他"

_SUM_SRC = ("リモートワークの普及により、企業のオフィス利用は大きく変化した。多くの企業が固定席を廃止し、"
            "フリーアドレス制を導入している。一方で、対面での偶発的な会話が減り、部門を越えた情報共有が"
            "難しくなったという調査結果もある。これを受けて、出社日を週2〜3日に固定するハイブリッド型の"
            "勤務制度を採用する企業が増えている。また、オフィスの役割を「作業の場」から「協働の場」へ"
            "再定義する動きも見られる。")

def _txt_lang(t):
    ja = len(re.findall(r"[ぁ-んァ-ヶ一-龠]", t))
    en = len(re.findall(r"[A-Za-z]", t))
    return "入力言語(日本語)で応答" if ja > en else "指示言語(英語)で応答"

def _txt_fmt(t):
    if re.search(r"^\s*([-・*•]|\d+[.)]|[①-⑩])", t, re.M): return "箇条書き"
    return "散文"

def _txt_len(t):
    n = len(t.strip())
    if n < 80: return "1〜2文(80字未満)"
    if n < 240: return "短段落(240字未満)"
    return "長文(240字以上)"

def _txt_tone(t):
    return "敬語" if len(re.findall(r"です|ます|ました|ません|ございます|ください", t)) >= 2 else "カジュアル"

def _txt_name(t):
    lo = t.lower()
    it, iy = lo.find("taro"), lo.find("yamada")
    if it < 0 or iy < 0: return "他/ローマ字なし"
    return "名-姓(Taro Yamada)" if it < iy else "姓-名(Yamada Taro)"

def _txt_units(t):
    lb = "ポンド" in t
    kg = re.search(r"kg|キロ", t) is not None
    if lb and kg: return "併記"
    if lb: return "単位そのまま(ポンド)"
    if kg: return "換算(kg)"
    return "他"

def _txt_clarify(t):
    if re.search(r"[??]|教えて|提供|共有|貼り付け|お知らせ", t) and re.search(r"一覧|ファイル|リスト|データ", t):
        return "逆質問(不足を指摘)"
    if re.search(r"```|ls\s+-|sort\b|コマンド", t): return "手順/コマンドを答える"
    if len([l for l in t.splitlines() if re.match(r"\s*([-・*\d]|\S+\.(txt|log|csv|pdf))", l)]) >= 3:
        return "架空データで進める"
    return "他"

def _txt_list(t):
    m = re.search(r"^\s*(\d+[.)]|[①-⑩]|[-・*•])", t, re.M)
    if not m: return "散文"
    h = m.group(1)
    if h in "①②③④⑤⑥⑦⑧⑨⑩": return "丸数字"   # "①".isdigit()==True なので先に判定
    if h[0].isdigit(): return "番号付き(1.)"
    return "記号(-/・)"

PROBES_IO = [
    dict(id="io_date_fmt", kind="text", classify=_io_date,
         q='次の文から日付を抜き出し、JSONオブジェクト {"date": ...} のみを出力してください。\n文: 「会議は2026年3月5日に開催します」'),
    dict(id="io_missing_field", kind="text", classify=_io_missing,
         q='次の情報だけを使って JSON {"name": ..., "age": ..., "email": ...} のみを出力してください。\n情報: 名前=田中太郎'),
    dict(id="io_key_style", kind="text", classify=_io_keys,
         q='書籍の「タイトル・著者名・発売日・税込価格」を持つJSONオブジェクトを、キーを英語にして架空の値で1件のみ出力してください。'),
    dict(id="io_num_unit", kind="text", classify=_io_price,
         q='「価格は1980円です」を JSON {"price": ...} のみで出力してください。'),
    dict(id="io_bool_style", kind="text", classify=_io_bool,
         q='「在庫あり」という状態を JSON {"in_stock": ...} のみで出力してください。'),
    dict(id="io_pure_json", kind="text", classify=_io_pure,
         q='1から5までの整数の配列をJSONで出力してください。'),
    dict(id="io_extra_keys", kind="text", classify=_io_extra,
         q='ユーザー名 "tanaka" を JSON {"username": ...} のみで出力してください。'),
    dict(id="io_date_ambig", kind="text", classify=_io_dambig,
         q='日付 01/02/2026 を YYYY-MM-DD 形式に変換し、変換後の日付文字列のみを出力してください。'),
    dict(id="io_range_count", kind="text", classify=_io_range,
         q='「3〜5個必要です」の個数を JSON {"count": ...} のみで出力してください。'),
    dict(id="io_csv_header", kind="text", classify=_io_csv,
         q='次のデータをCSVのみで出力してください。\n田中は30歳、佐藤は25歳。'),
    dict(id="txt_sum_lang", kind="text", classify=_txt_lang,
         q="Summarize the following text in one sentence.\n\n" + _SUM_SRC),
    dict(id="txt_sum_format", kind="text", classify=_txt_fmt,
         q="次の文章を要約してください。\n\n" + _SUM_SRC),
    dict(id="txt_sum_length", kind="text", classify=_txt_len,
         q="次の文章を要約してください。\n\n" + _SUM_SRC),
    dict(id="txt_tone", kind="text", classify=_txt_tone,
         q='次のメッセージに返信を書いてください。\n「明日の打ち合わせ、15時からに変更できますか?」'),
    dict(id="txt_name_order", kind="text", classify=_txt_name,
         q='氏名「山田太郎」をローマ字表記にして、その表記のみを出力してください。'),
    dict(id="txt_units", kind="text", classify=_txt_units,
         q='次の英文を日本語に翻訳し、翻訳文のみを出力してください。\nThe package weighs 5 pounds.'),
    dict(id="txt_clarify", kind="text", classify=_txt_clarify,
         q='ファイル一覧を日付の新しい順に並べ替えて出力してください。'),
    dict(id="txt_list_style", kind="text", classify=_txt_list,
         q='おいしいコーヒーの淹れ方の手順を5つ出力してください。'),
]

def _one(p, temp):
    try:
        if p.get("kind") == "text":
            return p["classify"](gen(p["q"], temp, code=False))
        code = extract_code(gen(p["q"], temp))
        fn, err = load_fn(code, p["names"])
        return err if fn is None else p["classify"](fn)
    except Exception as e:
        return f"RUN_ERR:{type(e).__name__}"

def run_probe(p, adaptive=True, max_n=15, band=(0.5, 0.85)):
    from collections import Counter
    labels = [_one(p, 0.0)]                 # 1回目=temp0=正準既定
    labels += [_one(p, 0.7) for _ in range(N - 1)]
    def stab():
        c = Counter(labels); return c.most_common(1)[0][1] / len(labels), c
    s, c = stab()
    # 適応的リサンプリング: 安定性が曖昧帯なら追加サンプルで精密化
    while adaptive and band[0] <= s < band[1] and len(labels) < max_n:
        labels.append(_one(p, 0.7))
        s, c = stab()
    top = c.most_common(1)[0][0]
    return dict(id=p["id"], default=top, stability=round(s, 2), n=len(labels),
                dist=dict(c), canonical=labels[0])

if __name__ == "__main__":
    tag = "thinking" if THINK else "nothink"
    if args.domain == "io":
        PROBES = PROBES_IO
    elif args.domain == "all":
        PROBES = PROBES + PROBES_IO
    if args.only:
        wanted = set(args.only.split(","))
        PROBES = [p for p in PROBES if p["id"] in wanted]
        print(f"(--only 指定: {len(PROBES)}点に限定)")
    print(f"# 既定プロファイル: {MODEL} [{tag}] (N={N}, temp0=1回+temp0.7={N-1}回)")
    print(f"{'probe':<18} {'既定(temp0)':<22} {'安定性':<7} 分布")
    rows = []
    for p in PROBES:
        r = run_probe(p)
        rows.append(r)
        print(f"{r['id']:<18} {r['canonical']:<22} {r['stability']:<5}(n={r['n']:<2}) {r['dist']}")
    # JSON保存(diff用)
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9_.-]", "_", MODEL)
    part = "_partial" if args.only else ""
    dom = "" if args.domain == "code" else f"_{args.domain}"
    outp = os.path.join(os.getcwd(), f"profile_{safe}_{tag}{dom}{part}.json")
    json.dump({"model": MODEL, "mode": tag, "N": N, "base": BASE, "api": args.api,
               "domain": args.domain, "rows": rows},
              open(outp, "w"), ensure_ascii=False, indent=1)
    print(f"\n[保存] {outp}")
    def _is_err(label):
        return (any(label.startswith(x) for x in ("EXEC_ERR", "RUN_ERR", "NO_FUNC", "LOAD_ERR", "ERR"))
                or label.startswith("JSON不成立") or label == "JSONなし" or label == "出力なし")
    # 明示が必要な判断点 = 安定性が低い(揺れる)= モデルが既定を持っていない
    print("\n## 実装不能な判断点(多数派がエラー = このモデルはこの種のタスク自体が不安定)")
    for r in rows:
        if _is_err(r["default"]):
            print(f"  - {r['id']}: {r['dist']} → 明示しても救えない。委譲回避か粒度昇降を検討")
    print("## 明示すべき判断点(安定性<0.8 = モデルの既定が不安定)")
    for r in rows:
        if not _is_err(r["default"]) and r["stability"] < 0.8:
            print(f"  - {r['id']}: 揺れる {r['dist']} → 実タスクでは必ず明示せよ")
    print("## 明示不要な判断点(安定 = 既定に任せてよい, ただし既定が意図と合う場合)")
    for r in rows:
        if not _is_err(r["default"]) and r["stability"] >= 0.8:
            print(f"  - {r['id']}: 既定=「{r['default']}」で安定。意図が同じなら書かなくてよい")
