# weak-llm-playbook

**弱い/安価なLLMへのコーディング委譲を、勘ではなく測定で運用するツールキット+Claude Codeスキル。**

English version: [README.md](README.md)

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

「1点だけ未指定の極小タスク」をN回投げ、どの既定を選んだか分類。2バッテリー計50判断点:

- `--domain code`(既定, 32点): 生成コードを**実行**して分類
- `--domain io`(18点): コーディング以外 — 構造化出力(JSON/CSV)・抽出解釈・文章スタイル・
  対話メタ(情報不足時に逆質問するか進めるか)— 出力テキストを決定論分類
- `--domain all`: 両方
- `--probes pack.json`: **独自バッテリーをJSONで宣言的に定義**(本体のコード変更不要)。
  ルールは regex/contains/長さ・JSONパース/フィールド照合・実行コードの結果/例外ケースに対応。
  `packs/io_en.json`(ioバッテリーの英語版)がリファレンス実例を兼ねる。

```bash
# OpenAI互換エンドポイント (vLLM / llama.cpp / ollama / OpenAI API)
# モデル名は省略可 — 先頭引数がURLなら GET /v1/models から自動検出する
# (vLLM等の単一モデルサーバーならこれだけで動く):
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5

# 明示指定(複数モデル配信サーバー / Anthropic形式では必須):
python3 skill/weak-llm-playbook/scripts/default_probe.py Qwen3.6-27B http://localhost:8000 5

# Anthropic Messages形式 (Anthropic API / claude-code-router)
python3 skill/weak-llm-playbook/scripts/default_probe.py claude-haiku-4-5 https://api.anthropic.com 5 nothink --api anthropic

# モデル間diff = 「モデルを替えたら指示のどこを書き換えるか」(2個以上=行列比較も可)
python3 skill/weak-llm-playbook/scripts/default_probe.py --diff profileA.json profileB.json

# コーディング以外バッテリー(構造化出力/抽出/文章スタイル)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --domain io

# JSONパックによる独自バッテリー(英語版ioバッテリーを例として同梱)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --probes packs/io_en.json

# ドリフト検知(CI・モデル更新の回帰テスト): ベースラインに対して既定変化・
# 安定性低下・実装不能化があれば exit 1
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --domain io \
        --assert profiles/profile_Qwen3.6-27B-NVFP4_nothink_io.json
```

ioバッテリーの実測例(Qwen3.6-27B, すべて**安定した**既定 — 揺れないぶん意図とのズレに
気づけない、いちばん危険な種類):

- 「3〜5個」→ **中央値4を発明**して抽出(下限でも上限でもない)
- 「JSONで出力」→ 常に```フェンス付き(`json.loads` へのパイプ直結が壊れる)
- 英語の指示+日本語の本文 → **日本語**で応答
- 情報不足時: 逆質問と一般論回答が真の五分五分(ただし捏造は0)→ どちらを望むか必ず明示

ioバッテリーでもモデル間 `--diff` は成立 — Qwen3.6-27B vs Phi-3.5-mini は6/18点で相違。
最大の差は安全性に直結: 欠損フィールドをQwenは安定して `null` にするが、**Phiは値を捏造**する
(範囲「3〜5個」も中央4→下限3に入れ替わる — どちらも安定なので、モデルを替えると
抽出データが黙って変わる)。

さらに既定は**プロンプトの言語**にも依存する: 同じQwen3.6でも、日付抽出は日本語プロンプト
ならISOで安定(0.86)なのに、英語プロンプトではISOと「原文のまま」の五分五分(0.53)。
範囲「3 to 5」も中央値安定→中央値vs範囲保持に割れる。**委譲で実際に使う言語で測るべき**で、
そのために `--probes packs/io_en.json` がある。

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

**抽出モード(`--kind json`)** — コードを介さないタスク(抽出・整形・分類)用。
同じ指示を入力文書ごとにK回実行し、JSON出力を**フィールド単位**で比較。
実装不能率の代わりにパース失敗率を見る:

```bash
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_extract.txt - \
        http://localhost:8000 5 examples/docs_extract.json --kind json
```

実測結果(問い合わせメールの抽出, Qwen3.6-27B): `quantity` の**型**が不安定
(文字列 `"3〜5個"` vs 素の数値)で発散を検出。さらに顧客名は5/5全実行が
**差出人ではなく宛名**に収束 — 安定して、安定したまま間違う。[合意]リストは
まさにこれを捕まえるためにある。

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

## 認証 / APIキーの扱い

リポジトリに**キーは一切含まれない**。ローカルエンドポイント(vLLM / llama.cpp / ollama)は
通常認証不要なので、`http://localhost:...` 相手ならそのまま動く。

認証が必要なエンドポイント(OpenAI API・Anthropic API・認証付きプロキシ)の場合:

- `--key YOUR_KEY` を渡すか、環境変数を設定する。解決順:
  `--key` > `PROBE_API_KEY` > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY`。
- `--api openai` は `Authorization: Bearer <key>` を送る。
- `--api anthropic` は `x-api-key` と `Authorization: Bearer` の**両方**を送る
  (Anthropic API本家と claude-code-router 等のAnthropic形式プロキシの双方をカバー)。
  このモードではキー必須。
- 共有マシンでは `--key` よりも環境変数を推奨(シェル履歴に残るため)。

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 skill/weak-llm-playbook/scripts/default_probe.py claude-haiku-4-5 \
        https://api.anthropic.com 5 nothink --api anthropic
```

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
