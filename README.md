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

## The three tools

Delegating to a cheap LLM is like outsourcing to a new contractor: every gap in your
instructions gets filled with *its* habits, not yours. Each tool covers one step.

**`default_probe.py` — learn the model's habits.** *(run once per model)*
Asks ~50 tiny tasks that each leave exactly one thing unspecified — e.g. "return the
n-th element" (0- or 1-indexed?) — several times each, and records what the model picked
and how consistently. The result sorts every habit into: unstable (**always write it in
your instruction**), stable but possibly not what you meant (**check it** — Qwen extracts
"3–5 items" as the invented midpoint 4, every single time), or safe to leave out.
Bonus: diff two models, or fail CI when an upgrade changes a habit (`--assert`).

**`spec_holes.py` — find and fix the holes in your instruction.** *(run before an important task)*
Gives your draft instruction to the model 5 times and compares the results on the same
inputs. Wherever they disagree, the model had to guess — that's a spec you forgot to
write. With `--fix out.txt` it closes the loop: it **writes a revised prompt** with every
diverging behavior pinned (majority choice, alternatives kept as comments), then re-probes
the revised prompt to **verify the ambiguity is gone**. You review one file and rewrite
only the pinned lines that don't match your intent — editing concrete lines is far easier
than imagining ambiguities.

**`model_card.py` — turn the measurements into a one-page guide.** *(when profiles pile up)*
Profiles are JSON; this merges a model's profiles into a Markdown cheat sheet — what not
to delegate, what to always specify, which defaults to double-check — so you write
instructions from one page instead of digging through JSON.

Also in the repo: `packs/` (the decision-point batteries as plain JSON — add your own
domain or language without touching code), `profiles/` and `cards/` (raw measurements
and generated guides for the models measured so far), and `skill/` — four Claude Code
skills: `/weak-llm-fix` (hand it a draft prompt, get back the normalized one),
`/weak-llm-run` (normalize, execute on the weak LLM, verify, return the result),
`/weak-llm-selffix` (the weak-operator variant: the weak LLM runs the fix loop on
*itself* — every step is graded by gate scripts, never by the model, and all pinned
lines come back for human review; add `run` to also execute the fixed prompt and
verify the result by replaying the measured behaviors; free-form tasks like
"review this page" get a shadow JSON contract behind the scenes, so users never
write JSON), and `weak-llm-playbook` (the decision-layer reference they build on).

## Quickstart

Zero dependencies (Python standard library only). Works with any OpenAI-compatible
endpoint (vLLM / llama.cpp / ollama / OpenAI API) or the Anthropic API.

```bash
# 1. Profile a model's defaults (model name auto-detected from the endpoint)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5

# 2. Find the holes in your draft spec — and get a fixed, verified prompt back
#    (everything after the draft is optional and order-free; function name, model,
#     and mode are auto-detected. Set PROBE_BASE once to drop the URL too.)
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_topn.txt \
        examples/probe_inputs_topn.json http://localhost:8000 --fix

# 3. Turn accumulated profiles into a delegation guide
python3 skill/weak-llm-playbook/scripts/model_card.py --glob 'profiles/*.json' -o card.md
```

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
