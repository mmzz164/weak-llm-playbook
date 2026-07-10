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
  --probes pack.json で判断点を外部定義(宣言的ルール。packs/io_en.json 参照)。
  --diff A.json B.json [C.json ...] でモデル間比較(2個以上)。
  --assert baseline.json でドリフト検知(既定変化/安定性低下/実装不能化→exit 1。CI用)。
"""
import sys, json, re, urllib.request, types

# diffモード: python3 default_probe.py --diff A.json B.json [C.json ...](2個以上)
if len(sys.argv) > 1 and sys.argv[1] == "--diff":
    import json as _j
    profs = [_j.load(open(f)) for f in sys.argv[2:]]
    if len(profs) < 2:
        print("--diff にはプロファイルJSONを2個以上指定してください"); sys.exit(2)
    models = [p["model"] for p in profs]
    maps = [{r["id"]: r for r in p["rows"]} for p in profs]
    ids = []
    for m in maps:                                    # 出現順を保った和集合
        ids += [i for i in m if i not in ids]
    print("# 既定プロファイル diff: " + "  vs  ".join(models))
    w = 20
    print(f"{'probe':<18} " + " ".join(f"{m[:w]:<{w}}" for m in models) + " 差分")
    diffs = []
    for pid in ids:
        rs = [m.get(pid) for m in maps]
        cs = [r["canonical"] if r else "—" for r in rs]
        ss = [r["stability"] if r else None for r in rs]
        present = [c for c in cs if c != "—"]
        flag = ""
        if len(set(present)) > 1: flag = "★既定が違う"
        elif any(s is not None and s < 0.8 for s in ss): flag = "△不安定なモデルあり"
        print(f"{pid:<18} " + " ".join(f"{c[:w]:<{w}}" for c in cs) + f" {flag}")
        if flag: diffs.append((pid, rs, flag))
    print(f"\n## モデル差のある判断点(={len(diffs)}件): ここは『モデルを替えたら書き換える』対象")
    for pid, rs, flag in diffs:
        detail = " / ".join(f"{m}=「{r['canonical']}」(安定{r['stability']})" if r else f"{m}=—"
                            for m, r in zip(models, rs))
        print(f"  - {pid}: {detail}  {flag}")
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
ap.add_argument("--probes", default=None, metavar="PACK.json",
                help="プローブパックJSON(判断点を外部定義)。指定時は --domain より優先")
ap.add_argument("--assert", dest="assert_base", default=None, metavar="BASELINE.json",
                help="ベースラインプロファイルと比較し、既定変化/安定性低下/実装不能化があれば exit 1 (CI・モデル更新の回帰検知用)")
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

def gen(prompt, temperature, code=True, suffix=None):
    if code:
        sfx = "\nコードのみ出力。説明・テスト不要。" if suffix is None else suffix
        return CLIENT.chat(prompt + sfx,
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

# ==== プローブパック (--probes pack.json): 判断点を外部JSONで定義する ====
# パック形式: {"pack": "名前", "probes": [{...}]}
#   text プローブ: {"id", "kind":"text", "q", "classify":[<rule>...], "fallback"}
#     rule = {"label": L, <条件>}。条件は最初に一致した rule の label を返す:
#       regex / contains / len_lt / len_ge       … 出力テキスト全体に対して
#       json_parses: true|false                  … 出力がそのまま json.loads 可能か
#       json_type: "dict"|"list"                 … find_json の結果型
#       json_only_keys: [k...]                   … dictのキー集合が完全一致
#       json_field: k + (equals / value_regex / is_null / absent / type)
#       all: [rule...] / any: [rule...]          … 複合条件(labelは外側に)
#   code プローブ: {"id", "kind":"code", "q", "names":[関数名候補],
#                  "cases":[{"args":[...], "result":... | "exception": true|"型名",
#                            "label": L}...], "fallback"}
#     生成コードを実行し、casesを順に評価(argsで呼び result 一致 / 例外一致 → label)。
# エラー系ラベルは "ERR" 始まりにすると実装不能カテゴリとして集計される。

def _norm(x):
    if isinstance(x, tuple): x = list(x)
    if isinstance(x, list): return [_norm(v) for v in x]
    if isinstance(x, dict): return {k: _norm(v) for k, v in x.items()}
    return x

def _rule_match(r, text):
    if "all" in r: return all(_rule_match(s, text) for s in r["all"])
    if "any" in r: return any(_rule_match(s, text) for s in r["any"])
    if "json_parses" in r:
        try: json.loads(text.strip()); ok = True
        except Exception: ok = False
        return ok == r["json_parses"]
    if "json_type" in r:
        j = find_json(text)
        return isinstance(j, {"dict": dict, "list": list}[r["json_type"]])
    if "json_only_keys" in r:
        j = find_json(text)
        return isinstance(j, dict) and set(j.keys()) == set(r["json_only_keys"])
    if "json_field" in r:
        j = find_json(text)
        if not isinstance(j, dict): return False
        f = r["json_field"]
        if r.get("absent"): return f not in j
        if f not in j: return False
        v = j[f]
        if r.get("is_null"): return v is None
        if "equals" in r: return v == r["equals"]
        if "value_regex" in r: return v is not None and re.search(r["value_regex"], str(v)) is not None
        if "type" in r:
            t = r["type"]
            if t == "number": return isinstance(v, (int, float)) and not isinstance(v, bool)
            return isinstance(v, {"string": str, "bool": bool, "list": list, "dict": dict}[t])
        return True   # フィールドが存在する、のみ
    if "regex" in r: return re.search(r["regex"], text) is not None
    if "contains" in r: return r["contains"] in text
    if "len_lt" in r: return len(text.strip()) < r["len_lt"]
    if "len_ge" in r: return len(text.strip()) >= r["len_ge"]
    return False

def _compile_text(rules, fallback):
    def classify(text):
        for r in rules:
            try:
                if _rule_match(r, text): return r["label"]
            except Exception:
                continue
        return fallback
    return classify

def _compile_code(cases, fallback):
    def classify(fn):
        for c in cases:
            a = c.get("args", [])
            try:
                res = fn(*[json.loads(json.dumps(x)) for x in a])
            except Exception as e:
                exc = c.get("exception")
                if exc is True or exc == type(e).__name__:
                    return c["label"].replace("{type}", type(e).__name__)
                continue
            if "result" in c and _norm(res) == _norm(c["result"]):
                return c["label"]
            if c.get("no_exception"):   # 呼べて例外が出なければよい
                return c["label"]
        return fallback
    return classify

def _extract_sql(text):
    t = text.strip()
    m = re.search(r"```(?:sql)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    m = re.search(r"(?is)\b(select|with)\b.*?(;|\Z)", t)
    return m.group(0).rstrip(";").strip() if m else None

def _compile_sql(setup, rules, fallback):
    """kind="sql": 生成SQLをsqlite(:memory:)で実行し、結果行を宣言的ルールで分類。
    rule = {"label", "rows": [[..]] 完全一致 / "col0": [..] 第1列一致 / "row_count": n}
    SQL不抽出→ERR:no-sql / 実行エラー(方言前提含む)→ERR:sql(型名)"""
    def classify(text):
        sql = _extract_sql(text)
        if not sql:
            return "ERR:no-sql"
        import sqlite3
        db = sqlite3.connect(":memory:")
        for s in setup:
            db.execute(s)
        try:
            rows = [list(r) for r in db.execute(sql).fetchall()]
        except Exception as e:
            return f"ERR:sql({type(e).__name__})"
        finally:
            db.close()
        for r in rules:
            if "rows" in r and _norm(rows) == _norm(r["rows"]): return r["label"]
            if "col0" in r and [w[0] for w in rows if w] == r["col0"]: return r["label"]
            if "row_count" in r and len(rows) == r["row_count"]: return r["label"]
        return fallback
    return classify

def load_pack(path):
    """パック読込。各プローブは text/sql/code の宣言的定義か、"builtin" で組み込み判断点を参照
    (q=プロンプトだけ差し替え可能=言語ポートが軽い)。"label_map" で分類ラベルを翻訳、
    パック直下の "code_suffix" で codeプローブの追記文(既定は日本語)を差し替え。"""
    pk = json.load(open(path))
    builtin = {b["id"]: b for b in PROBES + PROBES_IO}
    sfx = pk.get("code_suffix")
    probes = []
    for p in pk["probes"]:
        if "builtin" in p:
            base = builtin.get(p["builtin"])
            if base is None:
                raise SystemExit(f"{path}: builtin '{p['builtin']}' は存在しない")
            lm = p.get("label_map") or {}
            def _wrap(cl=base["classify"], lm=lm):
                def g(x):
                    y = cl(x)
                    return lm.get(y, y)
                return g
            d = dict(base)
            d["id"] = p.get("id", base["id"])
            d["q"] = p.get("q", base["q"])
            d["classify"] = _wrap()
            if sfx is not None and d.get("kind") != "text":
                d["suffix"] = sfx
            probes.append(d)
            continue
        kind = p.get("kind", "text")
        if kind == "text":
            probes.append(dict(id=p["id"], q=p["q"], kind="text",
                               classify=_compile_text(p["classify"], p.get("fallback", "他"))))
        elif kind == "sql":
            probes.append(dict(id=p["id"], q=p["q"], kind="text",   # 実行経路はtextと同じ
                               classify=_compile_sql(p["setup"], p["classify"],
                                                     p.get("fallback", "他"))))
        else:
            d = dict(id=p["id"], q=p["q"], names=p.get("names", []),
                     classify=_compile_code(p["cases"], p.get("fallback", "他")))
            if sfx is not None:
                d["suffix"] = sfx
            probes.append(d)
    name = pk.get("pack") or os.path.splitext(os.path.basename(path))[0]
    return name, probes

def _one(p, temp):
    try:
        if p.get("kind") == "text":
            return p["classify"](gen(p["q"], temp, code=False))
        code = extract_code(gen(p["q"], temp, suffix=p.get("suffix")))
        fn, err = load_fn(code, p["names"])
        return err if fn is None else p["classify"](fn)
    except Exception as e:
        return f"RUN_ERR:{type(e).__name__}"

def run_probe(p, adaptive=True, max_n=15, band=(0.5, 0.85)):
    from collections import Counter
    import time as _t
    usage = []                              # (出力トークン, 秒) — 委譲単価の目安
    def sample(temp):
        CLIENT.last_usage = None
        t0 = _t.time()
        lab = _one(p, temp)
        dt = _t.time() - t0
        if CLIENT.last_usage and CLIENT.last_usage.get("out") is not None:
            usage.append((CLIENT.last_usage["out"], dt))
        return lab
    labels = [sample(0.0)]                  # 1回目=temp0=正準既定
    labels += [sample(0.7) for _ in range(N - 1)]
    def stab():
        c = Counter(labels); return c.most_common(1)[0][1] / len(labels), c
    s, c = stab()
    # 適応的リサンプリング: 安定性が曖昧帯なら追加サンプルで精密化
    while adaptive and band[0] <= s < band[1] and len(labels) < max_n:
        labels.append(sample(0.7))
        s, c = stab()
    top = c.most_common(1)[0][0]
    row = dict(id=p["id"], default=top, stability=round(s, 2), n=len(labels),
               dist=dict(c), canonical=labels[0])
    if usage:
        row["avg_out_toks"] = round(sum(u for u, _ in usage) / len(usage))
        row["avg_sec"] = round(sum(d for _, d in usage) / len(usage), 2)
    return row

if __name__ == "__main__":
    tag = "thinking" if THINK else "nothink"
    if args.probes:
        pack_name, PROBES = load_pack(args.probes)
        print(f"(プローブパック: {pack_name} = {len(PROBES)}点)")
    elif args.domain == "io":
        pack_name = "io"; PROBES = PROBES_IO
    elif args.domain == "all":
        pack_name = "all"; PROBES = PROBES + PROBES_IO
    else:
        pack_name = "code"
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
    dom = "" if pack_name == "code" else f"_{pack_name}"
    outp = os.path.join(os.getcwd(), f"profile_{safe}_{tag}{dom}{part}.json")
    json.dump({"model": MODEL, "mode": tag, "N": N, "base": BASE, "api": args.api,
               "domain": pack_name, "rows": rows},
              open(outp, "w"), ensure_ascii=False, indent=1)
    print(f"\n[保存] {outp}")
    priced = [r for r in rows if "avg_out_toks" in r]
    if priced:
        tot = sum(r["avg_out_toks"] * r["n"] for r in priced)
        avg_s = sum(r["avg_sec"] for r in priced) / len(priced)
        print(f"(概算: 出力 計{tot}tok / 平均 {avg_s:.1f}s/サンプル — 委譲単価の目安としてJSONにも保存)")
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

    # ドリフト検知 (--assert): ベースラインと比較して回帰があれば exit 1
    if args.assert_base:
        base = json.load(open(args.assert_base))
        bmap = {r["id"]: r for r in base["rows"]}
        hard, soft, info = [], [], []
        for r in rows:
            b = bmap.get(r["id"])
            if not b:
                info.append(f"{r['id']}: ベースラインに無い判断点(新規)"); continue
            r_err, b_err = _is_err(r["default"]), _is_err(b["default"])
            if r_err and not b_err:
                hard.append(f"{r['id']}: 実装不能化 「{b['default']}」→「{r['default']}」 {r['dist']}")
            elif r["default"] != b["default"]:
                if r["stability"] >= 0.8 and b["stability"] >= 0.8:
                    hard.append(f"{r['id']}: 既定変化 「{b['default']}」(安定{b['stability']})"
                                f"→「{r['default']}」(安定{r['stability']})")
                else:
                    soft.append(f"{r['id']}: 多数派が変化したが不安定圏 "
                                f"「{b['default']}」({b['stability']})→「{r['default']}」({r['stability']})")
            elif r["stability"] < 0.8 <= b["stability"]:
                hard.append(f"{r['id']}: 安定性低下 {b['stability']}→{r['stability']} {r['dist']}")
        missing = [i for i in bmap if i not in {r['id'] for r in rows}]
        if missing:
            info.append(f"未実行(ベースラインのみ): {', '.join(missing)}")
        print(f"\n## ドリフト検知: ベースライン={base['model']} ({args.assert_base})")
        for m in hard: print(f"  ★ {m}")
        for m in soft: print(f"  △ {m}")
        for m in info: print(f"  ・ {m}")
        if hard:
            print(f"\nDRIFT: ★{len(hard)}件 → 指示の書き換え・委譲可否の再判断が必要 (exit 1)")
            sys.exit(1)
        print(f"\nドリフトなし(★0件, △{len(soft)}件) (exit 0)")
