# weak-llm-playbook

![tests](https://github.com/mmzz164/weak-llm-playbook/actions/workflows/tests.yml/badge.svg)

Delegate coding and text tasks to weak/cheap LLMs — driven by **measurement** instead of
gut feeling.

日本語版: [README.ja.md](README.ja.md)

## The idea

Weak LLMs don't fail because tasks are hard. They fail on **what you didn't write**:
either the spec is ambiguous, or you omitted a rule that differs from the model's default
(and stable defaults are the dangerous ones — they never waver and silently mismatch your
intent). So: measure the model's defaults, detect the holes in your spec mechanically,
and write only what's actually needed.

## Quickstart

Zero dependencies (Python standard library only). Works with any OpenAI-compatible
endpoint (vLLM / llama.cpp / ollama / OpenAI API) or the Anthropic API.

```bash
# 1. Profile a model's defaults (model name auto-detected from the endpoint)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5

# 2. Find the holes in your draft spec before you delegate
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_topn.txt top_n \
        http://localhost:8000 5 examples/probe_inputs_topn.json

# 3. Turn accumulated profiles into a delegation guide
python3 skill/weak-llm-playbook/scripts/model_card.py --glob 'profiles/*.json' -o card.md
```

## What's inside

| | |
|---|---|
| `default_probe.py` | Measures which defaults a model picks (49 built-in decision points, coding and non-coding), how stable they are, and what they cost. Cross-model diff, CI drift check (`--assert`), parallel runs. |
| `spec_holes.py` | Implements your draft spec K times and flags inputs where the runs disagree — the spec you forgot to write — then emits ready-to-paste spec-block suggestions. |
| `model_card.py` | Aggregates profiles into a Markdown delegation guide. |
| `packs/` | Decision-point batteries as plain JSON (instruction-following, SQL, Japanese/English pairs). Add your own domain without touching code. |
| `cards/`, `profiles/` | Generated guides and raw profiles for the models measured so far. |
| `skill/` | A Claude Code skill that runs the whole flow: classify → match profile → write the spec → verify independently. |

## Findings that shaped the design

- Explicit rules are followed, even counterintuitive ones. Failures trace back to
  ambiguity or omission — never to "difficulty".
- Stable defaults bite hardest: e.g. "3–5 items" is extracted as the invented midpoint
  **4**, five runs out of five.
- Defaults — and instruction-following itself — depend on the **prompt language**:
  Phi-3.5 breaks a "don't use set" prohibition 40% of the time in Japanese and never in
  English. Measure in the language you delegate in.
- Switching models silently changes behavior (missing fields: Qwen emits `null`, Phi
  invents values). `--diff` catches it mechanically.

Details: [docs/FINDINGS.md](docs/FINDINGS.md) (lab log) ·
[docs/USAGE.md](docs/USAGE.md) (full CLI reference)

## Caveats

- Probes **execute generated code**. Use a sandbox for untrusted endpoints.
- Profiles are per model × quantization × prompt language — re-measure when any of them
  changes (`--assert` automates exactly that).

## License

MIT
