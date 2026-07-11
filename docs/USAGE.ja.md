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

## spec_holes.py — タスク駆動スペック穴検出+プロンプト修正

```
spec_holes.py <draft.txt> [inputs.json] [URL] [K] [関数名] [モデル名]   # draft以降は順不同
              [--kind auto|code|json] [--fix [OUT.txt]] [--api ...] [--key ...]

# 最小形(接続先を一度だけ設定しておけば):
export PROBE_BASE=http://localhost:8003
spec_holes.py draft.txt inputs.json --fix
```

disagreement probing: ドラフト仕様をK回実装/実行させ、同じ入力で挙動を比較する。
**割れた所=あなたが書き忘れている仕様**。

draft以降の位置引数は**形で判別されるので順不同**: URL=接続先 / `*.json`=プローブ入力 /
整数=K / 1つ目の単語=関数名 / 2つ目=モデル名。そして全部省略可能——接続先は
`$PROBE_BASE`、モデルは `/v1/models` から自動検出、関数名は生成コードから自動発見、
モードは inputs.json の中身から推定(**文字列の配列**=抽出(json)モード /
**引数の組の配列**=コードモード)。

- コードモード: ワーカーが関数をK回実装し、プローブ入力で全実装を実行。
  実装不能率が委譲可否の判断材料を兼ねる。
- jsonモード: 抽出・整形タスク用。同じ指示を入力文書ごとにK回実行し、JSON出力を
  **フィールド単位**で比較。パース失敗率が実装不能率の代役。

シグナルは3つ: **[DIVERGED]**(発散)=必ず明示すべき穴 / **[AGREED]**(合意)=意図と照合すべき暗黙挙動 / 失敗率。

- `--fix [OUT.txt]` — ループを閉じる(出力先は省略時 `<draft>.fixed.txt`): 改訂版プロンプト(ドラフト+発散挙動を多数派でピン留めした
  「挙動の固定」ブロック、他候補はコメント併記)を書き出し、**それを再測定して曖昧さの消滅を検証**する。
  穴が残らなければ exit 0、残れば exit 1(残存リストつき)。ブロックや生成指示の言語は
  ドラフトの言語に自動追従。OUT.txt を読み、意図と違うピン行だけ書き直せばよい——
  多数派ピンは意図の推測ではなく**挙動の再現性の確保**であり、レビュー対象を
  「想像上の曖昧さ」から「具体的な行」に変えるのが目的。検証が通ると
  答え合わせ表 `<fixed>.expected.json` も書き出す(後述の replay_check.py が実行検証に使う)。
- `--policy POLICY.json`(jsonモード)— フィールドごとの比較ポリシー
  `{field: exact|count|exists|set:<key>|free}`。`count` は件数のみ(言い回しでなく粒度を比較)、
  `exists` は有無のみ、`set:<key>` は配列要素の<key>キーの集合(順序・他フィールドを無視した顔ぶれ比較)、`free` は比較から完全除外。これが自由文タスクを測定可能にする
  仕掛け(後述の apply_contract.py 参照)。ポリシーは答え合わせ表に同梱され、
  replay_check も同じ変換で照合する。

## check_inputs.py / check_fixed.py — fixループの機械ゲート

どちらも操作者の作業成果物をexit codeで採点する(0=PASS / 1=FAIL / 2=ファイル不正)。
これにより、fixループを弱い操作者——弱LLM自身(`skill/weak-llm-selffix`)を含む——に
回させても、操作者の自己申告を一切信用せずに済む。

```
check_inputs.py inputs.json [--kind auto|code|json] [--min N]
```

タスクを理解せずにプローブ入力を採点する: 構造・件数(code: 5以上 / json: 4以上)・
重複、そして引数位置ごとのパターン網羅——サイズを持つ引数(list/str/dict)は
空・要素1個・同点(等しい要素)、数値引数は0・負数(その型が実際に現れる位置のみ)。
不足パターンは**そのままコピペできる提案入力つき**で報告され、提案を字面どおり
追加すればPASSに収束する。json(抽出)モードは構造チェックのみ機械化可能で、
レシピの残り(欠損文書・競合候補など)は spec_holes の発散レポート側が受け持つ。

```
check_fixed.py draft.txt fixed.txt
```

`--fix` 出力の受け渡しゲート: 修正版プロンプトは**ドラフト原文をそのまま先頭に含む**
こと(修正はピン行の追記のみ)、追記部分は既知のピンブロックであること。弱い操作者に
ありがちな「ドラフトの言い換え・勝手な改善・切り詰め」を機械的に捕まえる。

## replay_check.py — 実行結果の再生照合器(runモード)

```
replay_check.py <fixed>.expected.json --prompt fixed.txt [URL] [--attempts N]
replay_check.py <fixed>.expected.json --code impl.py
```

`--fix` の検証が通ると、spec_holes は**答え合わせ表** `<fixed>.expected.json`
(全プローブ入力の合意挙動)も書き出す。replay_check は修正済みプロンプトをもう一度
実行し(生成は最大 `--attempts` 回、既定3)、結果をこの表と機械照合する——
**測定済みの挙動を全プローブ入力で再現できた実行だけが合格**。PASSで成果物を
プロンプトの隣に保存(コード=`.impl.py` / 抽出=`.outputs.json`)。`--code` は
既存の実装ファイルをオフラインで照合する。生成コードを実行する点はプローブと同じ注意。

## apply_contract.py — 自由文タスクへの「影の契約」

```
apply_contract.py draft.txt [--dir DIR] [--list]
```

普通の人はJSON仕様なんて書かない——だからここでは**JSONは測定器の内部形式であって、
ユーザーの入力形式ではない**。普通の言葉のドラフト(「このページをレビューして」)を渡すと、
キーワードの表引きで契約族(`contracts/*.json`: review / classify / summary / research)を
選び、その族の出力契約をドラフトに追記(`<draft>.contracted.txt`)し、対応する比較ポリシー
(`<draft>.policy.json`)を `spec_holes --policy` 用に書き出す。自由文フィールドは `free`
指定なので、言い回しの揺れは報告されず、本物の発散(尺度・件数・ゼロ件の流儀・欠損の扱い)
だけが残る。選択は表引きであって判断ではないので、弱い操作者でも回せる。族の追加は
`contracts/` にJSONを置くだけ(コード変更不要)。

## selffix.py — パイプライン全体を1コマンドに

```
selffix.py draft.txt [inputs.json] [URL] [--run] [-k K]
```

self-fix手順の全体をコードとして実行する: エンドポイント探索($PROBE_BASE→:8000/:8002/:8003)、
振り分け(外部ツール語→run_agent.py --fixへ自動転送。子は既定バイパス、WEAK_LLM_AGENT_TOOLS /
WEAK_LLM_AGENT_CMD で調整 / 引数の組の入力→コード / 契約族マッチ→影の契約 / 文書入力→抽出)、コードタスクのプローブ入力生成
(有界のLLM呼び出し+check_inputsの提案で自動補修)、有界fixループ、受け渡しゲート、
そして `--run` で実行+再生照合まで。exit: 0=完了 / 1=委譲不適・検証失敗 / 2=インフラ /
3=対象外。`skill/weak-llm-selffix` と `skill/weak-llm-selfrun` はこのコマンドの薄い前面
——対話エージェントは指示を「説得」で破れるが、手順が自分の実行物でなければ飛ばしようがない。

## run_agent.py — ツール必須タスクのK回プローブ

```
run_agent.py task.txt [--cmd "claude"] [--allowed mcp__server__*] [--bypass]
             [-k 3] [--timeout 900] [--policy POLICY.json] [--contract research|none]
```

外部ツールが要るタスク(トラッカー検索など)では、操作者セッションはツール権限を
**一切持たない**のが原則。このスクリプトが使い捨てのheadlessエージェント(`<cmd> -p`)を
明示的な `--allowedTools` 許可リスト付きで起動し、契約が無ければresearch契約を追記して
K回実行、結果JSONを比較ポリシー付きでフィールド比較する——エージェントタスク版の
spec_holes(発散=指示の穴)。各runの生ログと `result<i>.json` を成果物として保存。

`--fix [OUT.txt]` は spec_holes と同じ体験でループを閉じる: 発散した挙動をピン留めした
改訂版タスクを書き出し(スカラー・件数は多数派で自動ピン。顔ぶれの割れはIDを固定しても
使い回せないので「★要記入」行=並び順・範囲・フィルタを書く欄になる)、それをK回
再測定して穴の before → after を報告する。

子は**既定で** `--dangerously-skip-permissions` 付きで走る。`--allowed` を渡すと許可リスト方式に切り替わる(`--no-bypass` で素の権限確認)。トレードオフ: バイパスされた子は全ツール(Bash・ファイル書き込み・全MCP)を持ったまま、注入された命令を含み得る外部コンテンツを処理する——信頼できない素材には `--allowed` を。

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
