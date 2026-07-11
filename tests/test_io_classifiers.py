#!/usr/bin/env python3
"""組み込みioバッテリー分類器の単体テスト(合成出力・ネットワーク不要)。"""
from _common import dp, chk, finish

CASES = [
    (dp._io_date, '{"date": "2026-03-05"}', "ISO (zero-padded)"),
    (dp._io_date, '```json\n{"date": "2026/3/5"}\n```', "slash/other numeric"),
    (dp._io_date, 'はい、こちらです: {"date": "3月5日"}', "as written (Japanese)"),
    (dp._io_missing, '{"name":"田中太郎","age":null,"email":null}', "null-filled"),
    (dp._io_missing, '{"name":"田中太郎"}', "keys omitted"),
    (dp._io_missing, '{"name":"田中太郎","age":"","email":""}', "empty strings"),
    (dp._io_missing, '{"name":"田中太郎","age":30,"email":"t@example.com"}', "values invented/other"),
    (dp._io_keys, '{"title":"本","author_name":"著者","release_date":"2026-01-01"}', "snake_case"),
    (dp._io_keys, '{"title":"本","authorName":"著者","releaseDate":"2026-01-01"}', "camelCase"),
    (dp._io_price, '{"price": 1980}', "number (no unit)"),
    (dp._io_price, '{"price": "1980円"}', "string with unit"),
    (dp._io_price, '{"price": "1980"}', "string number"),
    (dp._io_bool, '{"in_stock": true}', "bool(true)"),
    (dp._io_bool, '{"in_stock": "あり"}', "string(あり)"),
    (dp._io_pure, '[1, 2, 3, 4, 5]', "raw JSON only"),
    (dp._io_pure, '```json\n[1,2,3,4,5]\n```', "code-fenced"),
    (dp._io_pure, 'こちらが配列です: [1,2,3,4,5] です。', "with prose"),
    (dp._io_extra, '{"username": "tanaka"}', "specified key only"),
    (dp._io_extra, '{"username": "tanaka", "id": 1}', "extra keys added"),
    (dp._io_dambig, '2026-01-02', "MM/DD (Jan 2)"),
    (dp._io_dambig, '2026-02-01', "DD/MM (Feb 1)"),
    (dp._io_range, '{"count": 3}', "lower bound (3)"),
    (dp._io_range, '{"count": 5}', "upper bound (5)"),
    (dp._io_range, '{"count": "3〜5"}', "range kept"),
    (dp._io_csv, '名前,年齢\n田中,30\n佐藤,25', "header row"),
    (dp._io_csv, '田中,30\n佐藤,25', "no header"),
    (dp._io_csv, '```csv\nname,age\n田中,30\n```', "header row"),
    (dp._txt_lang, 'リモートワークで企業のオフィス利用が変化し、ハイブリッド勤務が広がっている。', "input language (Japanese)"),
    (dp._txt_lang, 'Remote work has changed office usage, and hybrid work is spreading.', "instruction language (English)"),
    (dp._txt_fmt, '- 固定席の廃止\n- ハイブリッド勤務の拡大', "bullet points"),
    (dp._txt_fmt, 'リモートワークの普及でオフィスの役割が変わった。', "prose"),
    (dp._txt_len, '短い要約。', "1-2 sentences (<80 chars)"),
    (dp._txt_len, 'あ' * 100, "short paragraph (<240 chars)"),
    (dp._txt_len, 'あ' * 300, "long (>=240 chars)"),
    (dp._txt_tone, '承知しました。15時からで問題ありません。よろしくお願いします。', "polite (keigo)"),
    (dp._txt_tone, 'いいよ、15時で!', "casual"),
    (dp._txt_name, 'Taro Yamada', "given-family (Taro Yamada)"),
    (dp._txt_name, 'YAMADA Taro', "family-given (Yamada Taro)"),
    (dp._txt_units, '荷物の重さは5ポンドです。', "unit kept (pounds)"),
    (dp._txt_units, '荷物の重さは約2.3kgです。', "converted (kg)"),
    (dp._txt_units, '荷物の重さは5ポンド(約2.3kg)です。', "both (converted + original)"),
    (dp._txt_clarify, 'ファイル一覧を共有してください。どのファイルを並べ替えますか?', "asks back (points out missing input)"),
    (dp._txt_clarify, '`ls -t` コマンドで日付順に並べられます。\n```bash\nls -t\n```', "gives instructions/commands"),
    (dp._txt_clarify, '- report_2026.pdf\n- data.csv\n- notes.txt', "fabricates data"),
    (dp._txt_list, '1. 豆を挽く\n2. お湯を沸かす', "numbered (1.)"),
    (dp._txt_list, '① 豆を挽く\n② お湯を沸かす', "circled numbers"),
    (dp._txt_list, '- 豆を挽く\n- お湯を沸かす', "bullets (-/*)"),
]

for fn, inp, want in CASES:
    chk(f"{fn.__name__}:{inp[:24]!r}", fn(inp), want)

finish("test_io_classifiers")
