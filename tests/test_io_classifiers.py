#!/usr/bin/env python3
"""組み込みioバッテリー分類器の単体テスト(合成出力・ネットワーク不要)。"""
from _common import dp, chk, finish

CASES = [
    (dp._io_date, '{"date": "2026-03-05"}', "ISO(0埋め)"),
    (dp._io_date, '```json\n{"date": "2026/3/5"}\n```', "スラッシュ等"),
    (dp._io_date, 'はい、こちらです: {"date": "3月5日"}', "和文のまま"),
    (dp._io_missing, '{"name":"田中太郎","age":null,"email":null}', "null埋め"),
    (dp._io_missing, '{"name":"田中太郎"}', "キー省略"),
    (dp._io_missing, '{"name":"田中太郎","age":"","email":""}', "空文字埋め"),
    (dp._io_missing, '{"name":"田中太郎","age":30,"email":"t@example.com"}', "値を発明/他"),
    (dp._io_keys, '{"title":"本","author_name":"著者","release_date":"2026-01-01"}', "snake_case"),
    (dp._io_keys, '{"title":"本","authorName":"著者","releaseDate":"2026-01-01"}', "camelCase"),
    (dp._io_price, '{"price": 1980}', "数値(単位なし)"),
    (dp._io_price, '{"price": "1980円"}', "文字列(単位つき)"),
    (dp._io_price, '{"price": "1980"}', "文字列(数値)"),
    (dp._io_bool, '{"in_stock": true}', "bool(true)"),
    (dp._io_bool, '{"in_stock": "あり"}', "文字列(あり)"),
    (dp._io_pure, '[1, 2, 3, 4, 5]', "生JSONのみ"),
    (dp._io_pure, '```json\n[1,2,3,4,5]\n```', "コードフェンス付き"),
    (dp._io_pure, 'こちらが配列です: [1,2,3,4,5] です。', "説明文つき"),
    (dp._io_extra, '{"username": "tanaka"}', "指定キーのみ"),
    (dp._io_extra, '{"username": "tanaka", "id": 1}', "キー追加"),
    (dp._io_dambig, '2026-01-02', "MM/DD解釈(1月2日)"),
    (dp._io_dambig, '2026-02-01', "DD/MM解釈(2月1日)"),
    (dp._io_range, '{"count": 3}', "下限(3)"),
    (dp._io_range, '{"count": 5}', "上限(5)"),
    (dp._io_range, '{"count": "3〜5"}', "範囲のまま"),
    (dp._io_csv, '名前,年齢\n田中,30\n佐藤,25', "ヘッダあり"),
    (dp._io_csv, '田中,30\n佐藤,25', "ヘッダなし"),
    (dp._io_csv, '```csv\nname,age\n田中,30\n```', "ヘッダあり"),
    (dp._txt_lang, 'リモートワークで企業のオフィス利用が変化し、ハイブリッド勤務が広がっている。', "入力言語(日本語)で応答"),
    (dp._txt_lang, 'Remote work has changed office usage, and hybrid work is spreading.', "指示言語(英語)で応答"),
    (dp._txt_fmt, '- 固定席の廃止\n- ハイブリッド勤務の拡大', "箇条書き"),
    (dp._txt_fmt, 'リモートワークの普及でオフィスの役割が変わった。', "散文"),
    (dp._txt_len, '短い要約。', "1〜2文(80字未満)"),
    (dp._txt_len, 'あ' * 100, "短段落(240字未満)"),
    (dp._txt_len, 'あ' * 300, "長文(240字以上)"),
    (dp._txt_tone, '承知しました。15時からで問題ありません。よろしくお願いします。', "敬語"),
    (dp._txt_tone, 'いいよ、15時で!', "カジュアル"),
    (dp._txt_name, 'Taro Yamada', "名-姓(Taro Yamada)"),
    (dp._txt_name, 'YAMADA Taro', "姓-名(Yamada Taro)"),
    (dp._txt_units, '荷物の重さは5ポンドです。', "単位そのまま(ポンド)"),
    (dp._txt_units, '荷物の重さは約2.3kgです。', "換算(kg)"),
    (dp._txt_units, '荷物の重さは5ポンド(約2.3kg)です。', "併記"),
    (dp._txt_clarify, 'ファイル一覧を共有してください。どのファイルを並べ替えますか?', "逆質問(不足を指摘)"),
    (dp._txt_clarify, '`ls -t` コマンドで日付順に並べられます。\n```bash\nls -t\n```', "手順/コマンドを答える"),
    (dp._txt_clarify, '- report_2026.pdf\n- data.csv\n- notes.txt', "架空データで進める"),
    (dp._txt_list, '1. 豆を挽く\n2. お湯を沸かす', "番号付き(1.)"),
    (dp._txt_list, '① 豆を挽く\n② お湯を沸かす', "丸数字"),
    (dp._txt_list, '- 豆を挽く\n- お湯を沸かす', "記号(-/・)"),
]

for fn, inp, want in CASES:
    chk(f"{fn.__name__}:{inp[:24]!r}", fn(inp), want)

finish("test_io_classifiers")
