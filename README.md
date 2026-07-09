# weak-llm-playbook

**弱い/安価なLLMへのコーディング委譲を、勘ではなく測定で運用するツールキット+Claude Codeスキル。**

*A measurement-driven toolkit (+ Claude Code skill) for delegating coding tasks to weak/cheap LLMs: probe a model's default behaviors, detect spec holes by implementation disagreement, and write the minimum sufficient instruction.*

## 背景にある発見(実測)

ローカル27B級モデル(Qwen3.6-27B等)への委譲実験で分かったこと:

1. **弱LLMは「難しいから」失敗するのではなく「書いていないこと」で失敗する。**
   明示された規則なら、subtleでも反直感(標準挙動と逆の仕様)でも正しく実装する。
2. 失敗要因は2つだけ:**曖昧**(未記述の仕様→探索で発散、コスト1.5〜2.3倍)と
   **省略**(既定と異なる挙動の書き忘れ→モデルの既定で「正しく」実装され意図とズレる)。
3. よって発注側の仕事は「**意図がモデルの既定からズレる点を、1つも言い落とさず書くこと**」に尽きる。
   そして「どこがズレるか」は測定できる。

詳細な実験ログは [docs/FINDINGS.md](docs/FINDINGS.md)。

## ツール

### 1. `default_probe.py` — モデルの既定挙動プロファイラ

「1点だけ未指定の極小タスク」を32判断点×N回投げ、生成コードを**実行**してどの既定を選んだか分類。

```bash
# OpenAI互換エンドポイント (vLLM / llama.cpp / ollama / OpenAI API)
python3 skill/weak-llm-playbook/scripts/default_probe.py Qwen3.6-27B http://localhost:8000 5

# Anthropic Messages形式 (Anthropic API / claude-code-router)
python3 skill/weak-llm-playbook/scripts/default_probe.py claude-haiku-4-5 https://api.anthropic.com 5 nothink --api anthropic

# モデル間diff = 「モデルを替えたら指示のどこを書き換えるか」
python3 skill/weak-llm-playbook/scripts/default_probe.py --diff profileA.json profileB.json
```

出力は4分類:
- **実装不能**(多数派がエラー)→ 明示しても救えない。委譲回避
- **揺れる**(安定性<0.8)→ 必ず明示
- **安定な既定** → 中身を提示。意図と食い違う点だけ明示(例: Qwenは「n番目」=0始まり、範囲=終端含む)
- **モデル間差**(--diff)→ 乗り換え時に書き換える点

適応リサンプリング(曖昧帯だけ自動で追加サンプル)、`--only`での部分実行に対応。

### 2. `spec_holes.py` — タスク駆動スペック穴検出(disagreement probing)

ドラフト仕様をワーカーにK回実装させ、同じ入力で全実装を実行。**挙動が割れた入力=あなたが
書き忘れている仕様**として機械検出する。曖昧さを想像する能力が不要になる。

```bash
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_topn.txt top_n \
        <model> <base_url> 5 examples/probe_inputs_topn.json
```

```
## [発散] 仕様の穴 — 実装間で挙動が割れた入力(必ず明示すべき)
 ★ top_n([3,1,2], 2) → 「[3,2]」×3 / 「[1,2]」×1   ← 「上位」=ソートか先頭かの穴
## [合意] 暗黙の一致挙動 — 意図と合うか照合せよ
 - top_n([], 3) → []
実装不能率 1/5
```

### 3. Claude Code スキル

`skill/weak-llm-playbook/` を `~/.claude/skills/` にコピーすると、Claude Codeが
委譲判断→プロファイル照合→5ブロックスペック作成→独立検証のフローを実行できる。

```bash
cp -r skill/weak-llm-playbook ~/.claude/skills/
```

## 使いどころ

| 場面 | 使い方 |
|---|---|
| 日常の実装外注 | 仕様を固められる実装をローカルLLMへ。スキルの5ブロックテンプレで指示 |
| 新モデルの受け入れ検査 | `default_probe` 一発で「委譲に耐えるか(実装不能率)」「既定のクセ」が出る |
| モデル乗り換え | `--diff` で「書き換えるべき指示」が機械的に出る |
| 重要タスクの委譲前保険 | `spec_holes` で自分の仕様書の穴を投げる前に検出 |

## 検証済みの性質

- **直叩きプローブの予測は実委譲(エージェント経由)の挙動と一致**(検証3/3)
- **操作者(スペックを書く側)が弱いモデルでも回る**: 判断が「プロファイルとの2値比較」に
  外部化されているため、Haiku級でも核心の照合は全問正解だった
- 依存ゼロ(Python標準ライブラリのみ)

## 注意

- プローブは生成コードを**そのまま実行**する。信頼できないエンドポイントに対しては
  サンドボックス内で実行すること。
- 判断点バッテリーは現状Python関数中心。他言語・他ドメインはプローブ追加で拡張可能。
- プロファイルはモデル×量子化ごと。量子化を変えたら再測定を推奨。

## License

MIT
