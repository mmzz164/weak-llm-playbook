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
"""
import sys, json, re, types, urllib.request
from collections import Counter

import argparse, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient

ap = argparse.ArgumentParser(description="タスク駆動スペック穴検出(任意エンドポイント対応)")
ap.add_argument("task_file")
ap.add_argument("fn_name")
ap.add_argument("model", nargs="?", default="Qwen3.6-27B-NVFP4")
ap.add_argument("base",  nargs="?", default="http://localhost:8000")
ap.add_argument("k",     nargs="?", type=int, default=5)
ap.add_argument("inputs", nargs="?", default=None, help="発注側プローブ入力のJSONファイル(推奨)")
ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
ap.add_argument("--key", default=None)
args = ap.parse_args()
TASK_FILE, FN_NAME, MODEL, BASE, K = args.task_file, args.fn_name, args.model, args.base, args.k

TASK = open(TASK_FILE).read().strip()
CLIENT = LLMClient(MODEL, BASE, api=args.api, key=args.key, think=False)

def gen(prompt, temperature, max_tokens=600):
    return CLIENT.chat(prompt, temperature=temperature, max_tokens=max_tokens)

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
