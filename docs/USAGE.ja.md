# 使い方リファレンス

English version: [USAGE.md](USAGE.md)

依存はPython標準ライブラリのみ。全ツールは既定でOpenAI互換エンドポイント
(vLLM / llama.cpp / ollama / OpenAI API)、`--api anthropic` でAnthropic Messages形式に対応。

## default_probe.py — 既定挙動プロファイラ

```
default_probe.py [model] [base_url] [N] [think|nothink]
                 [--domain code|io|all] [--probes PACK.json] [--only id1,id2]
                 [--api openai|anthropic] [--key KEY]
                 [--parallel N] [--assert BASELINE.json] [--validate]
default_probe.py --diff A.json B.json [C.json ...]
```

「1点だけ未指定の極小タスク」をN回投げ、どの既定を選んだかを分類する。各判断点について
既定・安定性(同じ選択をした割合)・分布・平均出力トークン/秒を報告し、
`profile_<model>_<mode>[_<battery>].json` に保存する。

- **model** — OpenAI互換なら省略可: 先頭引数がURLだと `GET /v1/models` から自動検出。
  `--api anthropic` では必須。
- **N** — 判断点ごとのサンプル数(既定5: temp0を1回+temp0.7を残り)。安定性が曖昧帯
  (0.5〜0.85)のときだけ最大15まで適応リサンプリング。
- **--domain** — 組み込みバッテリー: `code`(31点、生成Pythonを実行)/ `io`(18点、
  コーディング以外: 構造化出力・抽出・文章・対話メタ)/ `all` で両方。いずれも日本語
  プロンプト。英語版はパックとして同梱。
- **--probes PACK.json** — 判断点を外部JSONから読み込む(下記「パック形式」)。--domainより優先。
- **--only id1,id2** — 一部だけ実行。保存は `*_partial.json` で本体プロファイルを汚さない。
- **--parallel N** — プローブ並列実行(vLLM相手にワーカー6で実測約3倍)。
  プローブ内の適応リサンプリングは従来どおり直列。
- **--assert BASELINE.json** — ドリフト検知(CI・モデル更新の回帰テスト)。ベースラインと
  比較し、既定変化(両側安定時)・安定性の0.8割れ・実装不能化で exit 1。不安定圏内の
  多数派変化は警告のみ。
- **--diff A.json B.json [C.json ...]** — モデル間(言語間・バージョン間)の行列比較。
  既定が違う点・どこかで不安定な点にフラグ。
- **--validate** — パック埋め込みセルフテストのオフライン実行(サーバー不要。下記参照)。
- **think** — 思考モード(chat_template_kwargs)。非対応サーバーや temperature 拒否の
  Anthropicモデルは自動検知して再試行する。

レポートは全判断点を **実装不能**(多数派がエラー=委譲回避)/ **揺れる**(安定性<0.8=必ず明示)/
**安定な既定**(意図とズレる点だけ明示)の3分類で出す。

## spec_holes.py — タスク駆動スペック穴検出

```
spec_holes.py <draft.txt> <関数名|-> [model] [base_url] [K] [inputs.json]
              [--kind code|json] [--api ...] [--key ...]
```

disagreement probing: ドラフト仕様をK回実装/実行させ、同じ入力で挙動を比較する。
**割れた所=あなたが書き忘れている仕様**。

- `--kind code`(既定): ワーカーが `<関数名>` をK回実装し、発注側のプローブ入力
  (`inputs.json` = 引数の組の配列)で全実装を実行。実装不能率が委譲可否の判断材料を兼ねる。
- `--kind json`: 抽出・整形タスク用。同じ指示を入力文書(`inputs.json` = 文字列配列)ごとに
  K回実行し、JSON出力を**フィールド単位**で比較。パース失敗率が実装不能率の代役。

シグナルは3つ: **[DIVERGED]**(発散)=必ず明示すべき穴 / **[AGREED]**(合意)=意図と照合すべき暗黙挙動 / 失敗率。
発散があるとレポート末尾に**spec-block suggestions(急所ブロック案)**(候補挙動ごとの貼るだけ1行+実装数)が出るので、
意図に合う行だけ残して指示に貼ればよい。

## model_card.py — 委譲ガイド生成器

```
model_card.py profile_A.json ... [--glob 'profiles/profile_Qwen*.json'] [-o card.md]
```

モデルのプロファイル群をMarkdownの委譲ガイドに集約する: バッテリーごとのサマリ表
(実装不能/揺れる/安定の数+コスト)、必ず明示リスト、意図と照合する安定既定チェックリスト。
`_partial` は自動除外。複数モデル混在ならモデルごとにカードを連結。生成済みカードは
[../cards/](../cards/) に同梱。

## パック形式(--probes)

パックは `{"pack": "名前", "probes": [...], "code_suffix": "..."}` のJSON。プローブ種別:

- `kind: "text"` — 出力テキストを宣言的ルール(先勝ち)で分類:
  `regex` / `contains` / `len_lt` / `len_ge` / `json_parses` / `json_type` /
  `json_only_keys` / `json_field`(+ `equals`, `value_regex`, `is_null`, `absent`, `type`)/
  `all` / `any`。どれにも一致しなければ `fallback`。
- `kind: "sql"` — `setup`(DDL/INSERTの配列)で作った sqlite(:memory:) に生成SQLを実行し、
  結果行で分類: `rows`(完全一致)/ `col0`(第1列)/ `row_count`。方言前提や構文崩れは
  `ERR:sql(...)` になる。
- `kind: "code"` — 生成Python関数を実行: `cases` に `{"args": [...], "result": ...}` または
  `{"args": [...], "exception": true|"型名"}`。
- `"builtin": "<probe_id>"` — 組み込み判断点を参照し、分類ロジックを共有したまま
  プロンプト(`q`)だけ差し替える(`label_map` でラベルの読み替えも可能)。
  `packs/code_en.json` はこの仕組みでコーディングバッテリー全点の英語プロンプト版を
  JSONだけで実現している。ラベルは全バッテリー共通で英語。
- `ERR` で始まるラベルは実装不能カテゴリに集計される。
- 各プローブに `"tests": [{"input": "...", "expect": "ラベル"}]` を書くと `--validate` が
  オフラインで検証する(codeプローブの input はPythonソース文字列)。

同梱パック(日英ペア): 指示遵守メタ(`inst_ja/en`, 9点)、SQL(`sql_ja/en`, 7点)、
ioバッテリー英語版(16点)、コーディングバッテリー英語版(31点)。

## 認証

リポジトリにキーは含まれず、ローカルエンドポイントは通常キー不要。

- `--key` か環境変数で渡す。解決順: `--key` > `PROBE_API_KEY` > `ANTHROPIC_API_KEY` >
  `OPENAI_API_KEY`。
- `--api openai` は `Authorization: Bearer`、`--api anthropic` は `x-api-key` と `Bearer` の
  両方を送る(本家APIとAnthropic形式プロキシをカバー)。anthropicではキー必須。
- 共有マシンでは `--key` より環境変数を推奨。

## テスト

`python tests/run_all.py` が単体テスト約170項目(分類器・ルールエンジン・SQLエンジン・
builtin機構・モデルカード)+全同梱パックの `--validate` を実行する(サーバー不要)。
CIはPython 3.10/3.12で同じものを回す。
