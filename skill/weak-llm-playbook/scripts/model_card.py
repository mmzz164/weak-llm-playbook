#!/usr/bin/env python3
"""モデルカード(委譲ガイド)生成器.

default_probe が保存したプロファイルJSON群から、そのモデルに委譲するときの実用ガイド
(実装不能 / 必ず明示 / 安定既定の照合チェックリスト / コスト目安)を Markdown で生成する。
新モデルを測るたびに手書きしていた「要注意既定リスト」が機械的に出る。

使い方:
  python3 model_card.py profile_A.json profile_B.json ... [-o card.md]
  python3 model_card.py --glob 'profiles/profile_Qwen*.json' -o cards/qwen.md
複数モデル分のプロファイルを渡すと、モデルごとのカードを連結して出力する。
ネットワーク不要(読むのはJSONだけ)。
"""
import argparse
import glob as _glob
import json
import sys


def is_err(label):
    return (any(label.startswith(x) for x in ("EXEC_ERR", "RUN_ERR", "NO_FUNC", "LOAD_ERR", "ERR"))
            or label.startswith("JSON不成立") or label in ("JSONなし", "出力なし"))


def battery_name(prof):
    return f"{prof.get('domain') or 'code'}"


def split_rows(rows):
    ne = [r for r in rows if is_err(r["default"])]
    un = [r for r in rows if not is_err(r["default"]) and r["stability"] < 0.8]
    st = [r for r in rows if not is_err(r["default"]) and r["stability"] >= 0.8]
    return ne, un, st


def render_model(model, profs):
    out = [f"# 委譲ガイド: {model}", ""]
    out.append("プロファイル(default_probe)からの自動生成。判断点の使い方 = "
               "**実装不能**は委譲回避 / **揺れる**は必ず明示 / **安定**は意図と照合し、ズレる点だけ明示。")
    out.append("")
    out.append("| バッテリー | mode | 判断点 | 実装不能 | 揺れる | 安定 | 出力tok/サンプル | 秒/サンプル |")
    out.append("|---|---|---|---|---|---|---|---|")
    for prof in profs:
        ne, un, st = split_rows(prof["rows"])
        toks = [r["avg_out_toks"] for r in prof["rows"] if "avg_out_toks" in r]
        secs = [r["avg_sec"] for r in prof["rows"] if "avg_sec" in r]
        t = f"{sum(toks) / len(toks):.0f}" if toks else "—"
        s = f"{sum(secs) / len(secs):.1f}" if secs else "—"
        out.append(f"| {battery_name(prof)} | {prof.get('mode', '?')} | {len(prof['rows'])} "
                   f"| {len(ne)} | {len(un)} | {len(st)} | {t} | {s} |")
    out.append("")

    sec_ne, sec_un = [], []
    for prof in profs:
        b = battery_name(prof)
        ne, un, _ = split_rows(prof["rows"])
        sec_ne += [f"- [{b}] {r['id']}: {r['dist']}" for r in ne]
        sec_un += [f"- [{b}] {r['id']}: {r['dist']} (安定性 {r['stability']})" for r in un]

    out.append("## 実装不能(明示しても救えない — 委譲回避か粒度昇降)")
    out += sec_ne or ["- なし"]
    out.append("")
    out.append("## 必ず明示(揺れる — このモデルは既定を持たない)")
    out += sec_un or ["- なし"]
    out.append("")
    out.append("## 安定な既定 — 意図と照合するチェックリスト(ズレる項目だけ指示に書く)")
    for prof in profs:
        _, _, st = split_rows(prof["rows"])
        if not st:
            continue
        out.append(f"### {battery_name(prof)}")
        out += [f"- {r['id']} = 「{r['default']}」" for r in st]
        out.append("")
    out.append("---")
    out.append("生成元プロファイル: " + " / ".join(
        f"{battery_name(p)}(N={p.get('N', '?')}, {p.get('base', '?')})" for p in profs))
    out.append("")
    return "\n".join(out)


def build_cards(files):
    by_model = {}
    for f in files:
        prof = json.load(open(f))
        by_model.setdefault(prof["model"], []).append(prof)
    return "\n".join(render_model(m, ps) for m, ps in by_model.items())


def main(argv=None):
    ap = argparse.ArgumentParser(description="プロファイル群からモデルカード(委譲ガイド)をMarkdown生成")
    ap.add_argument("files", nargs="*", help="default_probe が保存した profile_*.json")
    ap.add_argument("--glob", action="append", default=[], help="プロファイルのglobパターン(複数可)")
    ap.add_argument("-o", "--out", default=None, help="出力先ファイル(省略時は標準出力)")
    args = ap.parse_args(argv)
    files = list(args.files)
    for g in args.glob:
        files += sorted(_glob.glob(g))
    files = [f for f in dict.fromkeys(files) if not f.endswith("_partial.json")]
    if not files:
        ap.error("プロファイルJSONを指定してください(_partial は自動除外)")
    md = build_cards(files)
    if args.out:
        open(args.out, "w").write(md)
        print(f"[保存] {args.out}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
