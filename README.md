# weak-llm-playbook

**A measurement-driven toolkit (+ Claude Code skill) for delegating coding tasks to weak/cheap LLMs.**

Probe a model's default behaviors, detect spec holes by implementation disagreement, and write the minimum sufficient instruction — by measurement, not gut feeling.

日本語版: [README.ja.md](README.ja.md)

## Key findings (measured)

From delegation experiments with local ~27B-class models (Qwen3.6-27B etc.):

1. **Weak LLMs don't fail because a task is "hard" — they fail on what you didn't write.**
   Given an explicit rule, they implement it correctly even when it is subtle or
   counterintuitive (the opposite of the standard behavior in training data).
2. There are only two failure causes: **ambiguity** (unwritten spec → the model wanders and
   fixes the spec on its own; measured cost 1.5–2.3x tokens) and **omission** (you forgot to
   write a non-default behavior → the model "correctly" implements its own default,
   diverging from your intent).
3. Therefore the orchestrator's whole job is: **write down every point where your intent
   deviates from the model's defaults, without missing one.** And "where it deviates"
   is measurable.

Full experiment log: [docs/FINDINGS.md](docs/FINDINGS.md).

## Tools

### 1. `default_probe.py` — default-behavior profiler

Sends "minimal tasks with exactly one unspecified decision" × N runs and classifies which
default the model chose. Two batteries (50 decision points total):

- `--domain code` (default, 32 points): **executes** the generated code to classify
- `--domain io` (18 points): non-coding decisions — structured output (JSON/CSV),
  extraction/interpretation, writing style, and dialogue meta-behavior (ask back vs
  proceed on missing info) — classified deterministically from the output text
- `--domain all`: both

```bash
# OpenAI-compatible endpoint (vLLM / llama.cpp / ollama / OpenAI API)
# The model name is optional — when the first arg is a URL, it is auto-detected
# from GET /v1/models (single-model servers like vLLM need nothing more):
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5

# Or specify it explicitly (required for multi-model servers / Anthropic format):
python3 skill/weak-llm-playbook/scripts/default_probe.py Qwen3.6-27B http://localhost:8000 5

# Anthropic Messages format (Anthropic API / claude-code-router)
python3 skill/weak-llm-playbook/scripts/default_probe.py claude-haiku-4-5 https://api.anthropic.com 5 nothink --api anthropic

# Cross-model diff = "what to rewrite in your instructions when switching models"
python3 skill/weak-llm-playbook/scripts/default_probe.py --diff profileA.json profileB.json

# Non-coding battery (structured output / extraction / writing style)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --domain io
```

Sample findings from the io battery (Qwen3.6-27B, all *stable* defaults — the dangerous
kind, because they never waver and silently mismatch your intent):

- "3〜5個" (3 to 5 items) → extracts the **invented midpoint 4** — neither bound
- "output as JSON" → always wrapped in a ```code fence``` (piping to `json.loads` breaks)
- English instruction + Japanese source text → responds in **Japanese**
- On missing info: a genuine 50/50 coin flip between asking back and answering with
  generic instructions (never fabricates, though) → always specify which you want

The report has four categories:
- **Not implementable** (majority of runs error) → explicitness can't save it; avoid delegation
- **Unstable** (stability < 0.8) → always specify explicitly
- **Stable defaults** → the report shows the default's content; specify only where it
  mismatches your intent (e.g. Qwen: "n-th" = 0-indexed, ranges = end-inclusive)
- **Cross-model differences** (`--diff`) → what to rewrite when switching models

Supports adaptive resampling (extra samples only in the ambiguous stability band) and
partial runs via `--only`.

### 2. `spec_holes.py` — task-driven spec-hole detection (disagreement probing)

Has the worker implement your draft spec K times, then runs all implementations on the
same inputs. **Inputs where behavior diverges = spec you forgot to write.** Detection is
mechanical — no one has to *imagine* the ambiguity.

```bash
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_topn.txt top_n \
        <model> <base_url> 5 examples/probe_inputs_topn.json
```

```
## [DIVERGED] spec holes — inputs where implementations disagree (must specify)
 ★ top_n([3,1,2], 2) → "[3,2]"×3 / "[1,2]"×1   ← hole: "top" = sorted or first-n?
## [AGREED] implicit consensus behavior — check against your intent
 - top_n([], 3) → []
not-implementable rate: 1/5
```

**Extraction mode (`--kind json`)** — for non-coding tasks (extraction, reformatting,
classification). Runs the same instruction K times per input document and diffs the JSON
outputs **field by field**; the parse-failure rate replaces the not-implementable rate:

```bash
python3 skill/weak-llm-playbook/scripts/spec_holes.py examples/draft_extract.txt - \
        http://localhost:8000 5 examples/docs_extract.json --kind json
```

Real result (customer-inquiry extraction on Qwen3.6-27B): the `quantity` field's *type*
was unstable (`"3〜5個"` string vs bare number), and the customer name converged 5/5 on
the **addressee instead of the sender** — stable, and stably wrong. The consensus list
exists precisely so you catch that.

### 3. Claude Code skill

Copy `skill/weak-llm-playbook/` into `~/.claude/skills/` and Claude Code will run the
full flow: delegation decision → profile matching → 5-block spec writing → independent
verification.

```bash
cp -r skill/weak-llm-playbook ~/.claude/skills/
```

## When to use what

| Situation | How |
|---|---|
| Everyday implementation outsourcing | Delegate spec-stable implementations to a local LLM, using the skill's 5-block template |
| Acceptance test for a new model | One `default_probe` run tells you "can it take delegation at all (not-implementable rate)" and "its default quirks" |
| Switching models | `--diff` mechanically lists the instructions you must rewrite |
| Insurance before delegating a critical task | `spec_holes` finds the holes in your own spec before you send it |

## Authentication / API keys

The repo ships **no keys**, and local endpoints (vLLM / llama.cpp / ollama) typically
need none — everything works out of the box against `http://localhost:...`.

When the endpoint requires auth (OpenAI API, Anthropic API, an authenticated proxy):

- Pass `--key YOUR_KEY`, or set an environment variable. Resolution order:
  `--key` > `PROBE_API_KEY` > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY`.
- `--api openai` sends `Authorization: Bearer <key>`.
- `--api anthropic` sends both `x-api-key` and `Authorization: Bearer` (covers the
  Anthropic API and Anthropic-format proxies like claude-code-router). A key is
  mandatory in this mode.
- Prefer environment variables over `--key` on shared machines (shell history).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 skill/weak-llm-playbook/scripts/default_probe.py claude-haiku-4-5 \
        https://api.anthropic.com 5 nothink --api anthropic
```

## Validated properties

- **Direct-endpoint probe results predict real agent-mediated delegation behavior**
  (validated 3/3)
- **Works even when the orchestrator (the one writing the spec) is a weak model**:
  the judgment is externalized into "a 2-value comparison against the profile", so even
  a Haiku-class orchestrator got all core matches right
- Zero dependencies (Python standard library only)

## Caveats

- The probes **execute generated code as-is**. Run inside a sandbox when probing
  untrusted endpoints.
- The decision-point battery is currently Python-function-centric. Other languages /
  domains can be covered by adding probes.
- Profiles are per model × quantization. Re-measure after changing quantization.

## License

MIT
