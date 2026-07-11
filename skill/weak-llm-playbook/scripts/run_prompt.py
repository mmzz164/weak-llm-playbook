#!/usr/bin/env python3
"""正常化済みプロンプトを弱LLMに1回実行させ、出力を標準出力に返す最小ランナー。

使い方:
  run_prompt.py <prompt.txt> [--input FILE] [--base URL] [--model NAME]
                [--max-tokens N] [--temp T] [--api openai|anthropic] [--key KEY]
  - --input があればプロンプト末尾に区切り付きで連結(抽出タスクの対象文書など)
  - 接続先は --base > $PROBE_BASE > http://localhost:8000、モデルは /v1/models から自動検出
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import LLMClient, detect_model


def build_prompt(task, input_text):
    if not input_text:
        return task
    sep = "\n\n--- 入力 ---\n" if re.search(r"[ぁ-んァ-ヶ一-龠]", task) else "\n\n--- input ---\n"
    return task + sep + input_text


def main():
    ap = argparse.ArgumentParser(description="run a (fixed) prompt once against a weak LLM")
    ap.add_argument("prompt_file", help="prompt text file (e.g. the output of spec_holes --fix)")
    ap.add_argument("--input", default=None, help="optional input document appended to the prompt")
    ap.add_argument("--base", default=None, help="endpoint base URL (default: $PROBE_BASE or http://localhost:8000)")
    ap.add_argument("--model", default=None, help="model name (default: auto-detect from /v1/models)")
    ap.add_argument("--max-tokens", type=int, default=2000)
    ap.add_argument("--temp", type=float, default=0.0)
    ap.add_argument("--api", choices=["openai", "anthropic"], default="openai")
    ap.add_argument("--key", default=None)
    args = ap.parse_args()

    base = args.base or os.environ.get("PROBE_BASE", "http://localhost:8000")
    model = args.model
    if not model:
        if args.api == "anthropic":
            ap.error("--api anthropic requires an explicit model")
        model = detect_model(base, args.key)[0]
        print(f"# model auto-detected: {model}", file=sys.stderr)

    task = open(args.prompt_file).read().strip()
    input_text = open(args.input).read().strip() if args.input else None
    client = LLMClient(model, base, api=args.api, key=args.key, think=False)
    print(client.chat(build_prompt(task, input_text),
                      temperature=args.temp, max_tokens=args.max_tokens))


if __name__ == "__main__":
    main()
