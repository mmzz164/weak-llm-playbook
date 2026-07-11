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
        print("--diff requires 2 or more profile JSONs"); sys.exit(2)
    models = [p["model"] for p in profs]
    maps = [{r["id"]: r for r in p["rows"]} for p in profs]
    ids = []
    for m in maps:                                    # 出現順を保った和集合
        ids += [i for i in m if i not in ids]
    print("# default-profile diff: " + "  vs  ".join(models))
    w = 20
    print(f"{'probe':<18} " + " ".join(f"{m[:w]:<{w}}" for m in models) + " diff")
    diffs = []
    for pid in ids:
        rs = [m.get(pid) for m in maps]
        cs = [r["canonical"] if r else "—" for r in rs]
        ss = [r["stability"] if r else None for r in rs]
        present = [c for c in cs if c != "—"]
        flag = ""
        if len(set(present)) > 1: flag = "★ default differs"
        elif any(s is not None and s < 0.8 for s in ss): flag = "△ unstable on some model"
        print(f"{pid:<18} " + " ".join(f"{c[:w]:<{w}}" for c in cs) + f" {flag}")
        if flag: diffs.append((pid, rs, flag))
    print(f"\n## decision points that differ across models ({len(diffs)}): rewrite these when switching models")
    for pid, rs, flag in diffs:
        detail = " / ".join(f"{m}=\"{r['canonical']}\" (stability {r['stability']})" if r else f"{m}=—"
                            for m, r in zip(models, rs))
        print(f"  - {pid}: {detail}  {flag}")
    print("\nThis table = where the points you must specify swap from model to model, even for the same intent.")
    sys.exit(0)

import argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model, find_json

ap = argparse.ArgumentParser(description="default-behavior probe (works against any endpoint)")
ap.add_argument("model", nargs="?", default=None,
                help="omit (or \"\") to auto-detect from /v1/models (OpenAI-compatible only)")
ap.add_argument("base",  nargs="?", default="http://localhost:8000")
ap.add_argument("n",     nargs="?", type=int, default=5)
ap.add_argument("mode",  nargs="?", default="nothink", help="'think' enables thinking mode")
ap.add_argument("--api", choices=["openai", "anthropic"], default="openai",
                help="endpoint format (default: OpenAI-compatible /v1/chat/completions)")
ap.add_argument("--key", default=None, help="API key (falls back to PROBE_API_KEY/ANTHROPIC_API_KEY/OPENAI_API_KEY)")
ap.add_argument("--only", default=None, help="comma-separated probe ids to run (e.g. missing_key,range_incl)")
ap.add_argument("--domain", choices=["code", "io", "all"], default="code",
                help="built-in battery: code=coding (default) / io=structured output, extraction, writing / all=both")
ap.add_argument("--probes", default=None, metavar="PACK.json",
                help="probe pack JSON (externally defined decision points); overrides --domain")
ap.add_argument("--assert", dest="assert_base", default=None, metavar="BASELINE.json",
                help="compare against a baseline profile; exit 1 on default changes / stability drops / newly not-implementable probes (CI regression check)")
ap.add_argument("--parallel", type=int, default=1, metavar="N",
                help="number of concurrent probe workers (default 1 = sequential; per-probe adaptive resampling is unchanged)")
ap.add_argument("--validate", action="store_true",
                help="run the pack's embedded self-tests (probes[].tests) and exit; no server needed")
_argv = sys.argv[1:]
if _argv and _argv[0].startswith(("http://", "https://")):
    _argv.insert(0, "")   # 先頭がURL = model省略とみなし繰り上げ
args = ap.parse_args(_argv)
MODEL, BASE, N = args.model, args.base, args.n
if not MODEL:
    if args.validate:
        MODEL = "(validate)"   # セルフテストはネットワーク不要なので自動検出しない
    elif args.api == "anthropic":
        ap.error("--api anthropic requires an explicit model (auto-detection uses the OpenAI-compatible /v1/models only)")
    else:
        _models = detect_model(BASE, args.key)
        MODEL = _models[0]
        print(f"# model not specified → auto-detected from {BASE}/v1/models: {MODEL}"
              + (f" (+{len(_models)-1} more: {', '.join(_models[1:4])})" if len(_models) > 1 else ""))
THINK = args.mode in ("1", "think", "true")

# クライアントはスレッドローカル(--parallel 対応)。last_usage 等の状態がスレッド間で混ざらない
import threading as _th
_TLS = _th.local()
def _client():
    c = getattr(_TLS, "client", None)
    if c is None:
        c = LLMClient(MODEL, BASE, api=args.api, key=args.key, think=THINK)
        _TLS.client = c
    return c

def gen(prompt, temperature, code=True, suffix=None):
    if code:
        sfx = "\nコードのみ出力。説明・テスト不要。" if suffix is None else suffix
        return _client().chat(prompt + sfx,
                              temperature=temperature, max_tokens=2000 if THINK else 400)
    # textプローブ: 出力指示はプローブ文自身が持つ。要約・返信が切れないよう上限は広め
    return _client().chat(prompt, temperature=temperature, max_tokens=2000 if THINK else 600)

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
        classify=lambda f: "touching merged" if f([[1,2],[2,3]])==[[1,3]] else ("touching kept separate" if f([[1,2],[2,3]])==[[1,2],[2,3]] else "other"),
    ),
    dict(
        id="round_half",
        q="Pythonで float を最も近い整数に丸める関数 round_half を書いて。",
        names=["round_half","round_to_int"],
        classify=lambda f: "half_up(2.5→3)" if f(2.5)==3 else ("banker(2.5→2)" if f(2.5)==2 else "other"),
    ),
    dict(
        id="avg_empty",
        q="Pythonで数値リストの平均を返す関数 average を書いて。",
        names=["average","avg","mean"],
        classify=lambda f: _try(f, [], zero="returns 0", err="raises", ok0=lambda r: r==0),
    ),
    dict(
        id="dedup_order",
        q="Pythonでリストから重複を除く関数 dedup を書いて。",
        names=["dedup","dedupe","unique"],
        classify=lambda f: ("order preserved" if list(f([3,1,3,2,1]))==[3,1,2] else ("sorted" if list(f([3,1,3,2,1]))==[1,2,3] else "other")),
    ),
    dict(
        id="topn_short",
        q="Pythonでリストと数nを受け取り上位n件を返す関数 top_n を書いて(降順)。",
        names=["top_n","topn"],
        classify=lambda f: _try2(f, [1,2], 5, short="returns all when short", err="raises/error"),
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
        classify=lambda f: ("normalizes (case/spaces)" if f("A man a plan a canal Panama")==True else ("strict comparison" if f("A man a plan a canal Panama")==False else "other")),
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
        return zero if ok0(r) else f"other({r!r})"
    except Exception:
        return err

def _try2(f, lst, n, short, err):
    try:
        r = f(lst, n)
        return short if list(r)==[2,1] or list(r)==[1,2] else f"other({list(r)!r})"
    except Exception:
        return err

def _try_wc(f):
    try:
        r = f("The the THE cat")
        the = sum(v for k,v in r.items() if k.lower()=="the")
        if the==3: return "case-insensitive"
        if r.get("the",0)==1 and r.get("The",0)==1: return "case-sensitive"
        return f"other({dict(r)!r})"
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
        r=f(-7,3); return "python-style (2)" if r==2 else ("C-style (-1)" if r==-1 else f"other({r})")
    except Exception: return "ERR"
def _p_div_zero(f):
    try:
        r=f(1,0)
        if r is None: return "returns None"
        if isinstance(r,float) and _math.isinf(r): return "returns inf"
        return f"other({r})"
    except ZeroDivisionError: return "raises (ZeroDiv)"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_range_incl(f):
    try:
        r=list(f(1,4))
        if r==[1,2,3,4]: return "end inclusive"
        if r==[1,2,3]: return "end exclusive"
        return f"other({r})"
    except Exception: return "ERR"
def _p_sort_case(f):
    try:
        r=list(f(["banana","apple","Cherry"]))
        if r==["apple","banana","Cherry"]: return "case-insensitive"
        if r==["Cherry","apple","banana"]: return "ASCII order (uppercase first)"
        return f"other({r})"
    except Exception: return "ERR"
def _p_split_multi(f):
    try:
        r=list(f("a  b"))
        if r==["a","b"]: return "collapses whitespace"
        if r==["a","","b"]: return "keeps empty items"
        return f"other({r})"
    except Exception: return "ERR"
def _p_empty_split(f):
    try:
        r=list(f(""))
        if r==[]: return "empty list"
        if r==[""]: return "one empty string"
        return f"other({r})"
    except Exception: return "ERR"
def _p_missing_key(f):
    try:
        r=f({"a":1},"x")
        if r is None: return "returns None"
        return f"other({r})"
    except KeyError: return "raises (KeyError)"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_flatten(f):
    try:
        r=list(f([1,[2,[3,4]]]))
        if r==[1,2,3,4]: return "deep flatten"
        if r==[1,2,[3,4]]: return "one level only"
        return f"other({r})"
    except Exception: return "ERR"
def _p_nth_index(f):
    try:
        r=f([10,20,30],1)
        if r==10: return "1-indexed"
        if r==20: return "0-indexed"
        return f"other({r})"
    except Exception: return "ERR"
def _p_none_input(f):
    try:
        r=f(None)
        if r==0: return "treats None as empty (0)"
        return f"other({r})"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_reverse_default(f):
    try:
        r=list(f([3,1,2]))
        if r==[1,2,3]: return "ascending"
        if r==[3,2,1]: return "descending"
        return f"other({r})"
    except Exception: return "ERR"
def _p_title_case(f):
    try:
        r=f("hello world")
        if r=="Hello World": return "capitalize each word"
        if r=="Hello world": return "first word only"
        return f"other({r!r})"
    except Exception: return "ERR"
def _p_clamp_pct(f):
    try:
        r=f(0.25)
        if r in (25, 25.0): return "0-100 scale"
        if r in (0.25,): return "kept as 0-1"
        return f"other({r})"
    except Exception: return "ERR"
def _p_int_div(f):
    try:
        r=f([1,2])
        if r==1.5: return "float(1.5)"
        if r==1: return "int truncated (1)"
        return f"other({r})"
    except Exception: return "ERR"
def _p_slice_oob(f):
    try:
        r=list(f([1,2,3],5))
        if r==[1,2,3]: return "clamps (returns all)"
        return f"other({r})"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_neg_index(f):
    try:
        r=f([10,20,30],-1)
        if r==30: return "negative index allowed (tail)"
        return f"other({r})"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_strip_parse(f):
    try:
        r=f(" 42 ")
        if r==42: return "strips whitespace then parses"
        return f"other({r!r})"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_bool_case(f):
    try:
        vals=[f("true"),f("True"),f("TRUE")]
        if all(v is True for v in vals): return "case-insensitive True"
        if f("true") is True and f("True") is not True: return "lowercase only"
        return f"other({vals})"
    except Exception: return "ERR"
def _p_date_fmt(f):
    try:
        r=str(f(2026,7,8))
        if r=="2026-07-08": return "ISO (zero-padded)"
        if r in ("2026-7-8","2026/7/8"): return "unpadded/other separator"
        return f"other({r!r})"
    except Exception: return "ERR"
def _p_round_ndigits(f):
    try:
        r=f(3.14159)
        if r==3.14: return "2 decimals"
        if r==3: return "integer"
        if r==3.1: return "1 decimal"
        return f"other({r})"
    except Exception: return "ERR"
def _p_max_empty(f):
    try:
        r=f([])
        if r is None: return "returns None"
        return f"other({r})"
    except Exception as e: return f"raises ({type(e).__name__})"
def _p_dup_count(f):
    try:
        r=f([1,1,2,3,3,3])
        if r in (2,): return "distinct duplicated values (2)"
        if r in (4,): return "extra occurrences (4)"
        return f"other({r})"
    except Exception: return "ERR"
def _p_capitalize_rest(f):
    try:
        r=f("hELLO")
        if r=="Hello": return "lowers the rest"
        if r=="HELLO": return "first letter only (rest kept)"
        return f"other({r!r})"
    except Exception: return "ERR"
def _p_sort_mixed(f):
    try:
        r=f([3,1,2,"a"])
        return f"other/success({r})"
    except Exception as e: return f"raises ({type(e).__name__})"

# ==== io バッテリー: コーディング以外の判断点(構造化出力・抽出・文章・対話メタ) ====
# kind="text": 生成コードの実行ではなく、出力テキストそのものを決定論的に分類する。

_find_json = find_json   # llm_client.find_json を共用

def _strip_fence(text):
    m = re.search(r"```[a-z]*\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def _io_date(t):
    j = _find_json(t)
    v = str(j.get("date")) if isinstance(j, dict) and j.get("date") is not None else None
    if v is None: return "ERR:no-json/field"
    if v == "2026-03-05": return "ISO (zero-padded)"
    if re.match(r"2026[/.]0?3[/.]0?5", v): return "slash/other numeric"
    if "3月5日" in v: return "as written (Japanese)"
    return f"other({v[:20]})"

def _io_missing(t):
    j = _find_json(t)
    if not isinstance(j, dict): return "ERR:no-json"
    if "age" not in j and "email" not in j: return "keys omitted"
    vals = [j.get("age"), j.get("email")]
    if all(v is None for v in vals): return "null-filled"
    if all(v == "" for v in vals if v is not None): return "empty strings"
    return "values invented/other"

def _io_keys(t):
    j = _find_json(t)
    if not isinstance(j, dict) or not j: return "ERR:no-json"
    ks = list(j.keys())
    if any("_" in k for k in ks): return "snake_case"
    if any(re.search(r"[a-z][A-Z]", k) for k in ks): return "camelCase"
    return "single words/other"

def _io_price(t):
    j = _find_json(t)
    v = j.get("price") if isinstance(j, dict) else None
    if isinstance(v, (int, float)): return "number (no unit)"
    if isinstance(v, str):
        if "円" in v: return "string with unit"
        if v.replace(",", "").isdigit(): return "string number"
    return "ERR:no-json/other"

def _io_bool(t):
    j = _find_json(t)
    v = j.get("in_stock") if isinstance(j, dict) else None
    if v is True: return "bool(true)"
    if isinstance(v, str): return f"string({v[:10]})"
    if v == 1: return "number(1)"
    return "ERR:no-json/other"

def _io_pure(t):
    s = t.strip()
    try:
        json.loads(s); return "raw JSON only"
    except Exception:
        pass
    if s.startswith("```"): return "code-fenced"
    if _find_json(s) is not None: return "with prose"
    return "ERR:no-json"

def _io_extra(t):
    j = _find_json(t)
    if not isinstance(j, dict): return "ERR:no-json"
    return "specified key only" if set(j.keys()) == {"username"} else "extra keys added"

def _io_dambig(t):
    if "2026-01-02" in t: return "MM/DD (Jan 2)"
    if "2026-02-01" in t: return "DD/MM (Feb 1)"
    return "other/not converted"

def _io_range(t):
    j = _find_json(t)
    v = j.get("count") if isinstance(j, dict) else None
    if v == 3: return "lower bound (3)"
    if v == 5: return "upper bound (5)"
    if v == 4: return "midpoint (4)"
    if isinstance(v, (list, str)): return "range kept"
    return "ERR:no-json/other"

def _io_csv(t):
    body = _strip_fence(t)
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines: return "ERR:empty"
    first = lines[0]
    if re.search(r"名前|氏名|name|年齢|age", first, re.I): return "header row"
    if re.search(r"田中|佐藤|30|25", first): return "no header"
    return "other"

_SUM_SRC = ("リモートワークの普及により、企業のオフィス利用は大きく変化した。多くの企業が固定席を廃止し、"
            "フリーアドレス制を導入している。一方で、対面での偶発的な会話が減り、部門を越えた情報共有が"
            "難しくなったという調査結果もある。これを受けて、出社日を週2〜3日に固定するハイブリッド型の"
            "勤務制度を採用する企業が増えている。また、オフィスの役割を「作業の場」から「協働の場」へ"
            "再定義する動きも見られる。")

def _txt_lang(t):
    ja = len(re.findall(r"[ぁ-んァ-ヶ一-龠]", t))
    en = len(re.findall(r"[A-Za-z]", t))
    return "input language (Japanese)" if ja > en else "instruction language (English)"

def _txt_fmt(t):
    if re.search(r"^\s*([-・*•]|\d+[.)]|[①-⑩])", t, re.M): return "bullet points"
    return "prose"

def _txt_len(t):
    n = len(t.strip())
    if n < 80: return "1-2 sentences (<80 chars)"
    if n < 240: return "short paragraph (<240 chars)"
    return "long (>=240 chars)"

def _txt_tone(t):
    return "polite (keigo)" if len(re.findall(r"です|ます|ました|ません|ございます|ください", t)) >= 2 else "casual"

def _txt_name(t):
    lo = t.lower()
    it, iy = lo.find("taro"), lo.find("yamada")
    if it < 0 or iy < 0: return "other/no romaji"
    return "given-family (Taro Yamada)" if it < iy else "family-given (Yamada Taro)"

def _txt_units(t):
    lb = "ポンド" in t
    kg = re.search(r"kg|キロ", t) is not None
    if lb and kg: return "both (converted + original)"
    if lb: return "unit kept (pounds)"
    if kg: return "converted (kg)"
    return "other"

def _txt_clarify(t):
    if re.search(r"[??]|教えて|提供|共有|貼り付け|お知らせ", t) and re.search(r"一覧|ファイル|リスト|データ", t):
        return "asks back (points out missing input)"
    if re.search(r"```|ls\s+-|sort\b|コマンド", t): return "gives instructions/commands"
    if len([l for l in t.splitlines() if re.match(r"\s*([-・*\d]|\S+\.(txt|log|csv|pdf))", l)]) >= 3:
        return "fabricates data"
    return "other"

def _txt_list(t):
    m = re.search(r"^\s*(\d+[.)]|[①-⑩]|[-・*•])", t, re.M)
    if not m: return "prose"
    h = m.group(1)
    if h in "①②③④⑤⑥⑦⑧⑨⑩": return "circled numbers"   # "①".isdigit()==True なので先に判定
    if h[0].isdigit(): return "numbered (1.)"
    return "bullets (-/*)"

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
                raise SystemExit(f"{path}: unknown builtin '{p['builtin']}'")
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
            if p.get("tests"):
                d["tests"] = p["tests"]
            probes.append(d)
            continue
        kind = p.get("kind", "text")
        if kind == "text":
            d = dict(id=p["id"], q=p["q"], kind="text",
                     classify=_compile_text(p["classify"], p.get("fallback", "other")))
        elif kind == "sql":
            d = dict(id=p["id"], q=p["q"], kind="text",   # 実行経路はtextと同じ
                     classify=_compile_sql(p["setup"], p["classify"], p.get("fallback", "other")))
        else:
            d = dict(id=p["id"], q=p["q"], names=p.get("names", []),
                     classify=_compile_code(p["cases"], p.get("fallback", "other")))
            if sfx is not None:
                d["suffix"] = sfx
        if p.get("tests"):
            d["tests"] = p["tests"]
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
        c = _client()
        c.last_usage = None
        t0 = _t.time()
        lab = _one(p, temp)
        dt = _t.time() - t0
        if c.last_usage and c.last_usage.get("out") is not None:
            usage.append((c.last_usage["out"], dt))
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
        print(f"(probe pack: {pack_name} = {len(PROBES)} points)")
    elif args.domain == "io":
        pack_name = "io"; PROBES = PROBES_IO
    elif args.domain == "all":
        pack_name = "all"; PROBES = PROBES + PROBES_IO
    else:
        pack_name = "code"
    if args.only:
        wanted = set(args.only.split(","))
        PROBES = [p for p in PROBES if p["id"] in wanted]
        print(f"(--only: limited to {len(PROBES)} points)")

    # --validate: パック埋め込みセルフテストのみ実行(ネットワーク不要)
    if args.validate:
        if not args.probes:
            ap.error("--validate requires --probes")
        total = fails = 0
        for p in PROBES:
            for t in p.get("tests") or []:
                total += 1
                if p.get("kind") == "text":
                    got = p["classify"](t["input"])
                else:   # codeプローブ: input はPythonソース文字列
                    fn, err = load_fn(t["input"], p.get("names", []))
                    got = err if fn is None else p["classify"](fn)
                if got != t["expect"]:
                    fails += 1
                    print(f"NG {p['id']}: {t['input'][:50]!r} → {got!r} (expected {t['expect']!r})")
        print(f"validate: {total - fails}/{total} passed"
              + ("" if total else " (no tests defined in this pack)"))
        sys.exit(1 if fails else 0)

    print(f"# default profile: {MODEL} [{tag}] (N={N}: 1x temp0 + {N-1}x temp0.7"
          + (f", parallel {args.parallel}" if args.parallel > 1 else "") + ")")
    print(f"{'probe':<18} {'default(temp0)':<22} {'stab.':<7} distribution")
    rows = []
    if args.parallel > 1:
        from concurrent.futures import ThreadPoolExecutor
        ex = ThreadPoolExecutor(max_workers=args.parallel)
        results = ex.map(run_probe, PROBES)
    else:
        results = map(run_probe, PROBES)
    for r in results:
        rows.append(r)
        print(f"{r['id']:<18} {r['canonical']:<22} {r['stability']:<5}(n={r['n']:<2}) {r['dist']}")
    if args.parallel > 1:
        ex.shutdown()
    # JSON保存(diff用)
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9_.-]", "_", MODEL)
    part = "_partial" if args.only else ""
    dom = "" if pack_name == "code" else f"_{pack_name}"
    outp = os.path.join(os.getcwd(), f"profile_{safe}_{tag}{dom}{part}.json")
    json.dump({"model": MODEL, "mode": tag, "N": N, "base": BASE, "api": args.api,
               "domain": pack_name, "rows": rows},
              open(outp, "w"), ensure_ascii=False, indent=1)
    print(f"\n[saved] {outp}")
    priced = [r for r in rows if "avg_out_toks" in r]
    if priced:
        tot = sum(r["avg_out_toks"] * r["n"] for r in priced)
        avg_s = sum(r["avg_sec"] for r in priced) / len(priced)
        print(f"(approx cost: {tot} output tokens total / {avg_s:.1f}s per sample — also saved in the JSON)")
    def _is_err(label):
        return (any(label.startswith(x) for x in ("EXEC_ERR", "RUN_ERR", "NO_FUNC", "LOAD_ERR", "ERR"))
                or label.startswith("ERR:no-json") or label == "ERR:no-json" or label == "ERR:empty")
    # 明示が必要な判断点 = 安定性が低い(揺れる)= モデルが既定を持っていない
    print("\n## not implementable (majority errored — this model can't reliably do this kind of task)")
    for r in rows:
        if _is_err(r["default"]):
            print(f"  - {r['id']}: {r['dist']} → explicitness won't save it; avoid delegation or change granularity")
    print("## must specify (stability < 0.8 — the model has no stable default)")
    for r in rows:
        if not _is_err(r["default"]) and r["stability"] < 0.8:
            print(f"  - {r['id']}: unstable {r['dist']} → always specify in real tasks")
    print("## no need to specify (stable — trust the default IF it matches your intent)")
    for r in rows:
        if not _is_err(r["default"]) and r["stability"] >= 0.8:
            print(f"  - {r['id']}: stable default = \"{r['default']}\". Skip if it matches your intent")

    # ドリフト検知 (--assert): ベースラインと比較して回帰があれば exit 1
    if args.assert_base:
        base = json.load(open(args.assert_base))
        bmap = {r["id"]: r for r in base["rows"]}
        hard, soft, info = [], [], []
        for r in rows:
            b = bmap.get(r["id"])
            if not b:
                info.append(f"{r['id']}: not in baseline (new probe)"); continue
            r_err, b_err = _is_err(r["default"]), _is_err(b["default"])
            if r_err and not b_err:
                hard.append(f"{r['id']}: became not-implementable \"{b['default']}\" → \"{r['default']}\" {r['dist']}")
            elif r["default"] != b["default"]:
                if r["stability"] >= 0.8 and b["stability"] >= 0.8:
                    hard.append(f"{r['id']}: default changed \"{b['default']}\" (stab {b['stability']})"
                                f" → \"{r['default']}\" (stab {r['stability']})")
                else:
                    soft.append(f"{r['id']}: majority flipped but within unstable zone "
                                f"\"{b['default']}\" ({b['stability']}) → \"{r['default']}\" ({r['stability']})")
            elif r["stability"] < 0.8 <= b["stability"]:
                hard.append(f"{r['id']}: stability dropped {b['stability']} → {r['stability']} {r['dist']}")
        missing = [i for i in bmap if i not in {r['id'] for r in rows}]
        if missing:
            info.append(f"not run (baseline only): {', '.join(missing)}")
        print(f"\n## drift check: baseline={base['model']} ({args.assert_base})")
        for m in hard: print(f"  ★ {m}")
        for m in soft: print(f"  △ {m}")
        for m in info: print(f"  ・ {m}")
        if hard:
            print(f"\nDRIFT: {len(hard)} ★ item(s) → rewrite instructions / re-judge delegation (exit 1)")
            sys.exit(1)
        print(f"\nno drift (★0, △{len(soft)}) (exit 0)")
