# weak-llm-playbook

![tests](https://github.com/mmzz164/weak-llm-playbook/actions/workflows/tests.yml/badge.svg)

弱い/安価なLLMへのコーディング・テキストタスク委譲を、勘ではなく**測定**で運用する。

English version: [README.md](README.md)

## 考え方

弱いLLMは「難しいから」失敗するのではない。失敗するのは**書いていないこと**——仕様が曖昧か、
モデルの既定と違うルールを書き漏らしたか(そして危険なのは安定した既定のほう。揺れないので、
意図とのズレに気づけない)。だから、モデルの既定を測り、仕様の穴を機械的に検出して、
本当に必要なことだけを書く。

## クイックスタート

依存ゼロ(Python標準ライブラリのみ)。OpenAI互換エンドポイント
(vLLM / llama.cpp / ollama / OpenAI API)とAnthropic APIに対応。

```bash
# 1. モデルの既定をプロファイル(モデル名はエンドポイントから自動検出)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5

# 2. 委譲前にドラフト仕様の穴を検出
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_topn.txt top_n \
        http://localhost:8000 5 examples/probe_inputs_topn.json

# 3. 溜まったプロファイルから委譲ガイドを生成
python3 skill/weak-llm-playbook/scripts/model_card.py --glob 'profiles/*.json' -o card.md
```

## 中身

| | |
|---|---|
| `default_probe.py` | モデルがどの既定を選ぶか(組み込み49判断点、コーディング+非コーディング)、その安定性とコストを測る。モデル間diff、CIドリフト検知(`--assert`)、並列実行。 |
| `spec_holes.py` | ドラフト仕様をK回実装させ、挙動が割れた入力=書き忘れた仕様を検出。貼るだけの急所ブロック案まで出す。 |
| `model_card.py` | プロファイル群をMarkdownの委譲ガイドに集約。 |
| `packs/` | 判断点バッテリーをただのJSONで定義(指示遵守・SQL・日英ペア)。コードを触らずに自分のドメインを追加できる。 |
| `cards/`, `profiles/` | 測定済みモデルの生成済みガイドと生プロファイル。 |
| `skill/` | Claude Code スキル: 分類→プロファイル照合→スペック作成→独立検証のフロー一式。 |

## 設計の元になった発見

- 明示した規則は、反直感なものでも守られる。失敗の原因は常に曖昧さか書き漏らしで、
  「難しさ」ではない。
- 一番効くのは安定した既定: 例えば「3〜5個」は5回中5回、**発明された中央値4**として
  抽出される。
- 既定も、指示遵守そのものも、**プロンプトの言語**に依存する: Phi-3.5は「setを使うな」を
  日本語では40%の確率で破るが、英語では一度も破らない。委譲に使う言語で測ること。
- モデルを替えると挙動が黙って変わる(欠損フィールド: Qwenは`null`、Phiは値を捏造)。
  `--diff` が機械的に捕まえる。

詳細: [docs/FINDINGS.md](docs/FINDINGS.md)(実験ログ)·
[docs/USAGE.ja.md](docs/USAGE.ja.md)(CLIリファレンス)

## 注意

- プローブは**生成コードを実行する**。信頼できないエンドポイントにはサンドボックスを。
- プロファイルはモデル×量子化×プロンプト言語ごと。どれかが変わったら再測定
  (それを自動化するのが `--assert`)。

## License

MIT
