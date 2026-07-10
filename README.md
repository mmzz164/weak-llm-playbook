# weak-llm-playbook

![tests](https://github.com/mmzz164/weak-llm-playbook/actions/workflows/tests.yml/badge.svg)

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
default the model chose. Two batteries (49 decision points total):

- `--domain code` (default, 31 points): **executes** the generated code to classify
- `--domain io` (18 points): non-coding decisions — structured output (JSON/CSV),
  extraction/interpretation, writing style, and dialogue meta-behavior (ask back vs
  proceed on missing info) — classified deterministically from the output text
- `--domain all`: both
- `--probes pack.json`: **your own battery**, defined declaratively in JSON — no code
  changes needed. Rules cover regex/contains/length checks, JSON parsing and field
  matchers, result/exception cases for executed Python, and (`kind: "sql"`) executing
  generated SQL against an in-memory sqlite DB. A pack entry can also reference a
  built-in probe via `"builtin"` and swap only the prompt (with `label_map` translating
  labels), which makes **language ports cheap**. Bundled packs (Japanese/English pairs):
  - **instruction-following meta** (9 points): `packs/inst_ja.json` / `packs/inst_en.json` —
    do output contracts, prohibitions, conflicting instructions, constraint position, and
    count/length limits actually bind on this model? (i.e., does the 5-block template's
    "output contract" work)
  - **SQL domain** (7 points): `packs/sql_ja.json` / `packs/sql_en.json` — NULL sort order,
    top-N ties, case-sensitive matching, JOIN dropping unmatched rows, empty-set
    aggregates, duplicate output, default sort direction
  - **English io/code**: `packs/io_en.json` (16 points) / `packs/code_en.json` (the full
    built-in coding battery, 31 points, via builtin references)
- Profiles now also record `avg_out_toks` / `avg_sec` per probe — a rough
  delegation-cost axis for comparing models.
- `--parallel N`: run probes concurrently (measured 3x wall-clock speedup with 6 workers
  against vLLM; per-probe adaptive resampling unchanged).
- `--validate`: run a pack's embedded self-tests (`probes[].tests`) offline — no server
  needed. Every bundled pack ships with self-tests, and `tests/run_all.py` (run by CI)
  validates them all plus ~170 unit tests for the classifiers and the rule engine.

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
# (accepts 2+ profiles — pass 3 or more for a model matrix)
python3 skill/weak-llm-playbook/scripts/default_probe.py --diff profileA.json profileB.json

# Non-coding battery (structured output / extraction / writing style)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --domain io

# Custom battery from a JSON pack (English io battery ships as an example)
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --probes packs/io_en.json

# Drift check for CI / model upgrades: exit 1 if defaults changed, stability dropped,
# or a probe became not-implementable vs. the baseline profile
python3 skill/weak-llm-playbook/scripts/default_probe.py http://localhost:8000 5 --domain io \
        --assert profiles/profile_Qwen3.6-27B-NVFP4_nothink_io.json
```

Sample findings from the io battery (Qwen3.6-27B, all *stable* defaults — the dangerous
kind, because they never waver and silently mismatch your intent):

- "3〜5個" (3 to 5 items) → extracts the **invented midpoint 4** — neither bound
- "output as JSON" → always wrapped in a ```code fence``` (piping to `json.loads` breaks)
- English instruction + Japanese source text → responds in **Japanese**
- On missing info: a genuine 50/50 coin flip between asking back and answering with
  generic instructions (never fabricates, though) → always specify which you want

Cross-model `--diff` works on the io battery too — Qwen3.6-27B vs Phi-3.5-mini differ on
6/18 points, and the biggest one is a safety issue: on missing fields Qwen stably emits
`null`, while **Phi invents values** (and the "3–5 items" range flips from midpoint-4 to
lower-bound-3 — both stable, so switching models silently changes your extracted data).

Defaults also depend on the **prompt language**: on the same Qwen3.6, date extraction is
stably ISO with Japanese prompts (0.86) but a coin flip between ISO and "as written" with
English prompts (0.53), and the 3-to-5 range flips from stable-midpoint to
midpoint-vs-range-kept. Measure your profile in the language you actually delegate in —
that is exactly what the `*_en` / `*_ja` pack pairs are for.

The language effect goes far beyond formatting — **instruction-following itself is
language-bound, and the weaker the model the stronger the effect**. Phi-3.5-mini with
Japanese prompts violates a "do not use set" prohibition 40% of the time, ignores
"write in English" completely, and can't produce runnable SQL on 2/7 probes; with English
prompts every one of those failures disappears (all 1.0 compliant). Qwen3.6 is steadier,
but three of its coding defaults that waver under Japanese prompts become perfectly
stable in English. A model's good English benchmark behavior tells you nothing about
how it behaves when you delegate in another language — profile both.

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

When holes are found, the report ends with a **ready-to-paste spec block**: one line per
candidate behavior with implementation counts — keep the lines that match your intent,
delete the rest, and paste them into your instruction's "pitfalls" section:

```
## spec-block suggestions — keep the lines that match your intent
 ★ hole 1: top_n([3, 1, 2], 2)
    ・"top_n([3, 1, 2], 2) returns [3, 2]"   # 2/4 implementations
    ・"top_n([3, 1, 2], 2) returns [3, 1]"   # 2/4 implementations
```

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
