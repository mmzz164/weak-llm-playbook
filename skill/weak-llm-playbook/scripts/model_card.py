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
    out = [f"# Delegation guide: {model}", ""]
    out.append("Auto-generated from default_probe profiles. How to read: "
               "**not implementable** → avoid delegation / **unstable** → always specify / "
               "**stable** → check against your intent and specify only the mismatches.")
    out.append("")
    out.append("| battery | mode | points | not impl. | unstable | stable | out-tok/sample | sec/sample |")
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
        sec_un += [f"- [{b}] {r['id']}: {r['dist']} (stability {r['stability']})" for r in un]

    out.append("## Not implementable (explicitness won't save it — avoid delegation or change granularity)")
    out += sec_ne or ["- none"]
    out.append("")
    out.append("## Must specify (unstable — the model has no default)")
    out += sec_un or ["- none"]
    out.append("")
    out.append("## Stable defaults — checklist to compare against your intent (write only the mismatches)")
    for prof in profs:
        _, _, st = split_rows(prof["rows"])
        if not st:
            continue
        out.append(f"### {battery_name(prof)}")
        out += [f"- {r['id']} = \"{r['default']}\"" for r in st]
        out.append("")
    out.append("---")
    out.append("Source profiles: " + " / ".join(
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
    ap = argparse.ArgumentParser(description="generate a Markdown delegation guide (model card) from profiles")
    ap.add_argument("files", nargs="*", help="profile_*.json files saved by default_probe")
    ap.add_argument("--glob", action="append", default=[], help="glob pattern(s) for profiles")
    ap.add_argument("-o", "--out", default=None, help="output file (default: stdout)")
    args = ap.parse_args(argv)
    files = list(args.files)
    for g in args.glob:
        files += sorted(_glob.glob(g))
    files = [f for f in dict.fromkeys(files) if not f.endswith("_partial.json")]
    if not files:
        ap.error("specify profile JSONs (_partial files are excluded automatically)")
    md = build_cards(files)
    if args.out:
        open(args.out, "w").write(md)
        print(f"[saved] {args.out}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
