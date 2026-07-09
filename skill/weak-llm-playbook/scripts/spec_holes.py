#!/usr/bin/env python3
"""タスク駆動スペック穴検出器 (disagreement probing).

ドラフト仕様をワーカーモデルに K 回実装させ、同じ入力で全実装を実行して
挙動が割れた入力 = 仕様の穴(モデルが既定を持たない未指定判断点)を機械的に検出する。
固定バッテリー(default_probe.py)がカバーしない「このタスク固有の曖昧さ」を、
操作者の推論に頼らず炙り出す。

出力は2部構成:
  [発散] 実装間で挙動が割れた入力 → 仕様に必ず明示すべき穴
  [合意] 全実装が一致した暗黙挙動 → 一覧を見て意図と合うか照合するだけ(合わなければ明示)

使い方:
  python3 spec_holes.py <task.txt> <関数名> [model] [base_url] [K] [inputs.json]
    task.txt    : ワーカーに渡す予定のドラフト仕様(自然文)
    関数名       : 生成コードから取り出す関数
    inputs.json : 発注側が用意するプローブ入力(引数の組の配列)。推奨。
                  例: [[[3,1,2],2],[[],0],[[1,2],5]]
                  省略時はワーカー自身に提案させる(弱いモデルだと壊れた JSON を
                  返して失敗しうるため、発注側供給が確実)
  例) python3 spec_holes.py draft.txt top_n Qwen3.6-27B-NVFP4 http://localhost:8000 5 probe_inputs.json
  model省略時(openai互換のみ): /v1/models から自動検出。"" をプレースホルダにしてもよい

  --kind json : コードを介さない抽出・整形タスク用。inputs.json は入力テキスト(文字列)の配列。
    各入力に同じ指示を K 回実行し、JSON出力のフィールド単位で発散=仕様の穴を検出する。
  例) python3 spec_holes.py draft_extract.txt - http://localhost:8000 5 docs.json --kind json
"""
import sys, json, re, types, urllib.request
from collections import Counter

import argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model, find_json

ap = argparse.ArgumentParser(description="タスク駆動スペック穴検出(任意エンドポイント対応)")
ap.add_argument("task_file")
ap.add_argument("fn_name")
ap.add_argument("model", nargs="?", default=None,
                help="省略(または\"\")で /v1/models から自動検出 (openai互換のみ)")
ap.add_argument("base",  nargs="?", default="http://localhost:8000")
ap.add_argument("k",     nargs="?", type=int, default=5)
ap.add_argument("inputs", nargs="?", default=None, help="発注側プローブ入力のJSONファイル(推奨)")
ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
ap.add_argument("--key", default=None)
ap.add_argument("--kind", choices=["code", "json"], default="code",
                help="code=関数実装(既定) / json=抽出・構造化タスク: 各入力テキストにK回実行し"
                     "JSON出力のフィールド単位で発散を検出(fn_name は '-' でよい)")
_argv = sys.argv[1:]
if len(_argv) > 2 and _argv[2].startswith(("http://", "https://")):
    _argv.insert(2, "")   # 第3引数がURL = model省略とみなし繰り上げ
args = ap.parse_args(_argv)
TASK_FILE, FN_NAME, MODEL, BASE, K = args.task_file, args.fn_name, args.model, args.base, args.k
if not MODEL:
    if args.api == "anthropic":
        ap.error("--api anthropic では model を明示してください(自動検出は openai互換の /v1/models のみ)")
    _models = detect_model(BASE, args.key)
    MODEL = _models[0]
    print(f"# model未指定 → {BASE}/v1/models から自動検出: {MODEL}"
          + (f" (他{len(_models)-1}件)" if len(_models) > 1 else ""))

TASK = open(TASK_FILE).read().strip()
CLIENT = LLMClient(MODEL, BASE, api=args.api, key=args.key, think=False)

def gen(prompt, temperature, max_tokens=600):
    return CLIENT.chat(prompt, temperature=temperature, max_tokens=max_tokens)

# ==== 抽出モード (--kind json) ====
# コードを介さないタスク(抽出・整形・分類)向け。各入力テキストに同じ指示を K 回実行し、
# JSON出力をフィールド単位で比較。実行間で値が割れたフィールド = 指示に書いていない仕様。
if args.kind == "json":
    if not args.inputs:
        print("!! --kind json では inputs.json(入力テキスト文字列の配列)が必須"); sys.exit(2)
    texts = json.load(open(args.inputs))
    if not (isinstance(texts, list) and texts and all(isinstance(x, str) for x in texts)):
        print("!! inputs.json は文字列(入力テキスト)の配列にしてください"); sys.exit(2)
    print(f"# スペック穴検出(抽出モード): model={MODEL} K={K} 入力{len(texts)}件")

    total = bad = 0
    per_input = []
    for doc in texts:
        outs = []
        for k in range(K):
            raw = gen(TASK + "\n\n--- 入力 ---\n" + doc, 0.0 if k == 0 else 0.7, max_tokens=800)
            j = find_json(raw)
            total += 1
            if j is None:
                bad += 1
            else:
                outs.append(j)
        per_input.append((doc, outs))
    print(f"JSON取得: {total - bad}/{total} (パース失敗率 {bad / total:.0%})")
    if bad / total >= 0.5:
        print("!! パース失敗率50%超: 出力形式自体が崩れている(形式の明示強化か委譲回避を検討)")

    def canon(v):
        return json.dumps(v, ensure_ascii=False, sort_keys=True)

    diverged, consensus = [], []
    for i, (doc, outs) in enumerate(per_input):
        label = doc[:24].replace("\n", " ")
        if len(outs) < 3:
            print(f"  (入力#{i}「{label}…」: 有効出力{len(outs)}件<3 のため分析スキップ)")
            continue
        if all(isinstance(o, dict) for o in outs):
            for key in sorted(set().union(*[set(o) for o in outs])):
                vals = [canon(o[key]) if key in o else "(キーなし)" for o in outs]
                c = Counter(vals)
                (diverged if len(c) > 1 else consensus).append(
                    (i, label, key, c if len(c) > 1 else vals[0]))
        else:  # dict以外(配列等)は全体で比較
            c = Counter(canon(o) for o in outs)
            (diverged if len(c) > 1 else consensus).append(
                (i, label, "(全体)", c if len(c) > 1 else canon(outs[0])))

    print("\n## [発散] 仕様の穴 — 実行間で値が割れたフィールド(必ず明示すべき)")
    if not diverged:
        print("  なし(この入力集合では割れなかった)")
    for i, label, key, c in diverged:
        dist = " / ".join(f"「{v}」×{n}" for v, n in c.most_common())
        print(f"  ★ 入力#{i}「{label}…」 {key} → {dist}")
        print("     → 形式・欠損時の値・単位・解釈のどれが未指定かを決め、指示に例として固定せよ")

    print("\n## [合意] 暗黙の一致挙動 — 意図と合うか照合せよ(合わなければ明示)")
    for i, label, key, v in consensus:
        print(f"  - 入力#{i} {key} → {v}")

    print(f"\nまとめ: 穴 {len(diverged)}件 / 合意 {len(consensus)}件 / パース失敗 {bad}/{total}")
    sys.exit(0)

def extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()

def load_fn(code, name):
    mod = types.ModuleType("impl")
    try:
        exec(code, mod.__dict__)
    except Exception as e:
        return None, f"LOAD_ERR:{type(e).__name__}"
    f = getattr(mod, name, None)
    if callable(f):
        return f, None
    for k, v in mod.__dict__.items():
        if callable(v) and not k.startswith("_") and isinstance(v, types.FunctionType):
            return v, None
    return None, "NO_FUNC"

# --- 1. K個の実装を生成 ---
print(f"# スペック穴検出: fn={FN_NAME} model={MODEL} K={K}")
impls, broken, attempts = [], 0, 0
MAX_ATTEMPTS = K * 3
while len(impls) < K and attempts < MAX_ATTEMPTS:
    temp = 0.0 if attempts == 0 else 0.7
    attempts += 1
    code = extract_code(gen(TASK + "\n標準ライブラリのみで最小限の実装をコードのみ出力。"
                            "import・説明・テスト・型チェックは不要。", temp, max_tokens=1200))
    f, err = load_fn(code, FN_NAME)
    if f is None:
        broken += 1
        continue
    impls.append(f)
fail_rate = broken / attempts if attempts else 0
print(f"実装取得: {len(impls)}/{K} (試行{attempts}回, ロード失敗{broken}回 = 実装不能率 {fail_rate:.0%})")
if fail_rate >= 0.5:
    print("!! 実装不能率50%超: このタスクはこのモデルには不安定(委譲回避か粒度昇降を検討)")
if len(impls) < 3:
    print("!! 有効実装が3未満のため発散分析は不可")
    sys.exit(2)

# --- 2. エッジ入力を収集(発注側ファイル優先 + ワーカー提案を補助的に合併) ---
inputs = []
src = []
if args.inputs:
    try:
        for a in json.load(open(args.inputs)):
            if isinstance(a, list):
                inputs.append(a)
        src.append(f"発注側{len(inputs)}個")
    except Exception as e:
        print(f"!! inputs.json の読込失敗: {e}"); sys.exit(2)
ARGS_PROMPT = (TASK + f"\n\nこの仕様の関数 {FN_NAME} に対して、曖昧な点・境界・エッジケースを突く"
               "テスト入力(引数の組)を8個、JSON配列の配列だけで出力してください。"
               '例: [[[3,1,2], 2], [[], 0]]。コードや説明は不要、JSONのみ。')
n0 = len(inputs)
for t in (0.3, 0.9):
    try:
        raw = gen(ARGS_PROMPT, t, max_tokens=400)
        m = re.search(r"\[\s*\[.*?\]\s*\]", raw, re.S)
        cand = json.loads(m.group(0))
        if not (isinstance(cand, list) and all(isinstance(a, list) for a in cand)):
            continue
        if any(len(repr(a)) > 200 for a in cand):   # 反復崩壊などの異常値を除外
            continue
        for a in cand:
            if repr(a) not in {repr(x) for x in inputs}:
                inputs.append(a)
    except Exception:
        pass
if len(inputs) > n0:
    src.append(f"ワーカー提案{len(inputs)-n0}個")
if not inputs:
    print("!! エッジ入力なし: inputs.json を発注側で用意して再実行せよ"); sys.exit(2)
print(f"エッジ入力: {len(inputs)}個({' + '.join(src)})")

# --- 3. 全実装 × 全入力 を実行し、挙動を比較 ---
def behave(f, args):
    try:
        r = f(*[json.loads(json.dumps(a)) for a in args])  # 実装間の破壊的変更を隔離
        return repr(r)
    except Exception as e:
        return f"EXC:{type(e).__name__}"

# 全入力で例外を吐く「壊れた実装」は発散分析から除外(実装不能率側で数える)
matrix = {id(f): [behave(f, args) for args in inputs] for f in impls}
alive = [f for f in impls if not all(b.startswith("EXC:") for b in matrix[id(f)])]
dead = len(impls) - len(alive)
if dead:
    print(f"(全入力で例外の壊れ実装 {dead}個を発散分析から除外)")
if len(alive) < 3:
    print("!! 生きた実装が3未満のため発散分析は不可"); sys.exit(2)

diverged, consensus = [], []
for j, args in enumerate(inputs):
    behaviors = [matrix[id(f)][j] for f in alive]
    c = Counter(behaviors)
    if len(c) > 1:
        diverged.append((args, c))
    else:
        consensus.append((args, behaviors[0]))

# --- 4. レポート ---
print("\n## [発散] 仕様の穴 — 実装間で挙動が割れた入力(必ず明示すべき)")
if not diverged:
    print("  なし(この入力集合では割れなかった)")
for args, c in diverged:
    dist = " / ".join(f"「{b}」×{n}" for b, n in c.most_common())
    print(f"  ★ {FN_NAME}(*{args!r}) → {dist}")
    print(f"     → どちらが意図か決め、急所ブロックに例として固定せよ")

print("\n## [合意] 暗黙の一致挙動 — 意図と合うか照合せよ(合わなければ明示)")
for args, b in consensus:
    print(f"  - {FN_NAME}(*{args!r}) → {b}")

print(f"\nまとめ: 穴 {len(diverged)}件 / 合意 {len(consensus)}件 / 実装不能率 {broken}/{K}")
