# weak-llm-playbook

![tests](https://github.com/mmzz164/weak-llm-playbook/actions/workflows/tests.yml/badge.svg)

Delegate coding and text tasks to weak/cheap LLMs — driven by **measurement**
instead of gut feeling.

日本語版: [README.ja.md](README.ja.md)

## The problem, in one true story

We asked a local model to extract order quantities. The source said "3–5
items". The model extracted **4** — an invented midpoint — five runs out of
five. No error, no warning, perfectly stable: every downstream record would
have been silently wrong.

Weak LLMs don't fail because tasks are hard. They fail on **what you didn't
write** — and the stable failures are the dangerous ones, because they never
waver and so are never noticed. This toolkit makes those failures measurable,
and fixes them mechanically: run your instruction K times, compare the results
on the same inputs, and **wherever they disagree is a spec you forgot to
write**. Pin it, re-measure, verify it's gone.

## Try it in 10 seconds — no model, no GPU, no API key

```bash
python3 demo/demo.py
```

The real pipeline runs against a deterministic mock model: an ambiguity is
found ("top n" — by value, or the first n?), pinned, verified (`holes: 2 → 0`),
executed, and the execution replay-verified.

## Use it on your endpoint

Zero dependencies (Python standard library only). Works with any
OpenAI-compatible endpoint (vLLM / llama.cpp / ollama / OpenAI API) or the
Anthropic API.

```bash
export PROBE_BASE=http://localhost:8000       # ollama: http://localhost:11434

# One command. Write your instruction in a file, the way you'd naturally
# write it, then:
python3 tools/fix.py draft.txt
#   -> it finds what you forgot to specify, pins it, and hands back a fixed
#      prompt verified to behave the same on every run. You review the
#      PINNED lines. That's the whole workflow.

# Add --run to also execute the fixed prompt and return a verified result:
python3 tools/fix.py draft.txt --run

# Working on documents (extract fields / review a page / classify)?
# Pass them along as a JSON array of strings:
python3 tools/fix.py draft.txt documents.json --run

# Tasks that need external tools (search a tracker through MCP, ...) are
# auto-routed to disposable agent sessions — needs an agent CLI like `claude`.
```

Under the hood, `tools/spec_holes.py` is the measuring engine — run the
instruction K times, diff the results, pin the divergences. Use it directly
(`python3 tools/spec_holes.py examples/draft_topn.txt examples/probe_inputs_topn.json --fix`),
and vendor it anywhere: it and `tools/llm_client.py` are two stdlib-only files.
Per-model habit profiles: `tools/default_probe.py` + `tools/model_card.py`.

Full CLI reference, pack format, compare policies:
[docs/USAGE.md](docs/USAGE.md).

## Findings that shaped the design

- Explicit rules are followed, even counterintuitive ones. Failures trace back
  to ambiguity or omission — never to "difficulty".
- Stable defaults bite hardest: e.g. "3–5 items" is extracted as the invented
  midpoint **4**, five runs out of five.
- Defaults — and instruction-following itself — depend on the **prompt
  language**: one 3.8B model breaks a "don't use set" prohibition 40% of the
  time in Japanese and never in English. Measure in the language you delegate in.
- Switching models silently changes behavior (missing fields: one model emits
  `null`, another invents values). `--diff` catches it mechanically.
- A textual "stop" instruction held **0/2 times** against an agent's
  helpfulness drive. Procedures must be code and permissions must be enforced
  by the harness — which is exactly how these tools are built.

Details: [docs/FINDINGS.md](docs/FINDINGS.md) (lab log).

## Caveats

- Probes **execute generated code**. Use a sandbox for untrusted endpoints.
- Profiles are per model × quantization × prompt language — re-measure when any
  of them changes (`--assert` automates exactly that).
- Free-form *quality* (is this a good summary?) is not measurable here; the
  tools verify structure, counts, lineups and reproducibility.

## License

MIT
