# Usage reference

日本語版: [USAGE.ja.md](USAGE.ja.md)

Everything runs on the Python standard library only. All tools speak to any
OpenAI-compatible endpoint (vLLM / llama.cpp / ollama / OpenAI API) by default,
or the Anthropic Messages format with `--api anthropic`.

## default_probe.py — default-behavior profiler

```
default_probe.py [model] [base_url] [N] [think|nothink]
                 [--domain code|io|all] [--probes PACK.json] [--only id1,id2]
                 [--api openai|anthropic] [--key KEY]
                 [--parallel N] [--assert BASELINE.json] [--validate]
default_probe.py --diff A.json B.json [C.json ...]
```

Sends "minimal tasks with exactly one unspecified decision" × N runs and classifies
which default the model chose. Each probe reports the default, its stability
(fraction of runs choosing it), the distribution, and average output tokens / seconds.
Results are saved as `profile_<model>_<mode>[_<battery>].json`.

- **model** — optional for OpenAI-compatible endpoints: if the first argument is a URL,
  the model is auto-detected from `GET /v1/models`. Required with `--api anthropic`.
- **N** — samples per probe (default 5: one at temperature 0, the rest at 0.7).
  Adaptive resampling adds samples (up to 15) only when stability lands in the
  ambiguous 0.5–0.85 band.
- **--domain** — built-in batteries: `code` (31 points, executes the generated Python),
  `io` (18 points, non-coding: structured output / extraction / writing style / dialogue
  meta), `all` for both. Both are Japanese-prompt batteries; English versions ship as packs.
- **--probes PACK.json** — load a battery from a JSON pack (see "Pack format" below).
  Overrides `--domain`.
- **--only id1,id2** — run a subset; saves to `*_partial.json` so full profiles aren't
  clobbered.
- **--parallel N** — run probes concurrently (measured ~3x wall-clock with 6 workers
  against vLLM). Per-probe adaptive resampling stays sequential.
- **--assert BASELINE.json** — drift check for CI / model upgrades. Compares the fresh
  run against a baseline profile and exits 1 on: a default change (both sides stable),
  a stability drop below 0.8, or a probe becoming not-implementable. Majority flips
  inside the unstable zone are reported as warnings only.
- **--diff A.json B.json [C.json ...]** — cross-model (or cross-language, cross-version)
  comparison matrix; flags points whose defaults differ or that are unstable anywhere.
- **--validate** — run the pack's embedded self-tests offline (no server; see below).
- **think** — enable thinking mode where supported (`chat_template_kwargs`); servers
  that reject it are detected and retried automatically, as are Anthropic models that
  reject `temperature`.

The report buckets every probe into: **not implementable** (majority errored — avoid
delegation), **unstable** (stability < 0.8 — always specify), and **stable defaults**
(specify only where the default mismatches your intent).

## spec_holes.py — task-driven spec-hole detection

```
spec_holes.py <draft.txt> <fn_name|-> [model] [base_url] [K] [inputs.json]
              [--kind code|json] [--api ...] [--key ...]
```

Disagreement probing: your draft spec is implemented/executed K times and behaviors are
compared on the same inputs. **Where runs disagree = spec you forgot to write.**

- `--kind code` (default): the worker implements `<fn_name>` K times; all implementations
  run on your probe inputs (`inputs.json` = array of argument tuples). The
  not-implementable rate doubles as a delegation-viability check.
- `--kind json`: for extraction/reformatting tasks. The same instruction runs K times per
  input document (`inputs.json` = array of strings); JSON outputs are diffed **field by
  field**, and the parse-failure rate replaces the not-implementable rate.

Report signals: **[DIVERGED]** = holes you must specify, **[AGREED]** = implicit consensus
to check against your intent, plus the failure rate. When holes exist the report ends
with **ready-to-paste spec-block suggestions** — one line per candidate behavior with
implementation counts; keep the lines matching your intent.

## model_card.py — delegation-guide generator

```
model_card.py profile_A.json ... [--glob 'profiles/profile_Qwen*.json'] [-o card.md]
```

Aggregates a model's profiles into a Markdown delegation guide: per-battery summary
table (not-implementable / unstable / stable counts + cost), the always-specify list,
and the stable-defaults checklist to compare against your intent. `_partial` profiles
are excluded automatically; multiple models produce one card each. Generated cards for
the measured models live in [../cards/](../cards/).

## Pack format (--probes)

A pack is a JSON file: `{"pack": "name", "probes": [...], "code_suffix": "..."}`.
Probe kinds:

- `kind: "text"` — classify the raw output text with ordered declarative rules
  (first match wins): `regex` / `contains` / `len_lt` / `len_ge` / `json_parses` /
  `json_type` / `json_only_keys` / `json_field` (+ `equals`, `value_regex`, `is_null`,
  `absent`, `type`) / `all` / `any`. `fallback` is returned when nothing matches.
- `kind: "sql"` — execute the generated SQL against an in-memory sqlite DB built from
  `setup` (DDL/INSERT list) and classify result rows: `rows` (exact), `col0`
  (first column), `row_count`. Dialect or syntax breakage becomes `ERR:sql(...)`.
- `kind: "code"` — execute the generated Python function: `cases` of
  `{"args": [...], "result": ...}` or `{"args": [...], "exception": true|"TypeName"}`.
- `"builtin": "<probe_id>"` — reference a built-in probe, sharing its classification
  logic while swapping only the prompt (`q`); `label_map` translates labels. This is
  how `packs/code_en.json` ports the whole coding battery in pure JSON.
- Labels starting with `ERR` are counted in the not-implementable category.
- `"tests": [{"input": "...", "expect": "label"}]` per probe — embedded self-tests,
  run offline by `--validate` (for code probes, `input` is Python source).

Bundled packs (Japanese/English pairs): instruction-following meta (`inst_ja/en`, 9 pts),
SQL domain (`sql_ja/en`, 7 pts), plus English ports of the io (16 pts) and coding
(31 pts) batteries.

## Authentication

No keys ship with the repo, and local endpoints normally need none.

- Pass `--key`, or set an environment variable. Resolution order:
  `--key` > `PROBE_API_KEY` > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY`.
- `--api openai` sends `Authorization: Bearer`; `--api anthropic` sends both `x-api-key`
  and `Bearer` (covers the Anthropic API and Anthropic-format proxies), and requires a key.
- Prefer environment variables over `--key` on shared machines.

## Tests

`python tests/run_all.py` runs ~170 unit tests (classifiers, rule engine, SQL engine,
builtin mechanism, model cards) plus `--validate` for every bundled pack — no server
required. CI runs the same on Python 3.10/3.12.
