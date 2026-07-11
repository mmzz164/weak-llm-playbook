---
name: weak-llm-selfrun
description: >-
  [[weak-llm-selffix]] の実行版アクションスキル(弱い操作者=ローカルLLM自身用)。
  ドラフトを機械的に正常化した上でそのまま実行し、fix時に記録した答え合わせ表
  (expected.json)との再生照合を通った成果物だけを返す。手順全体は selffix.py --run に
  コード化済みで、スキルは「1コマンド叩いて報告を貼る」薄い前面。
  "/weak-llm-selfrun <ドラフト or ファイルパス>" で起動。プロンプトだけ欲しいなら
  [[weak-llm-selffix]]。強い操作者が使うなら [[weak-llm-run]]。
---

# weak-llm-selfrun — one command; normalize, execute, replay-verify

Identical to weak-llm-selffix, except the one command includes `--run`: after
fixing the prompt, the script executes it and verifies the execution against
the recorded expected-behavior table. Scripts live in
the `weak-llm-playbook/scripts/` directory in the same skills directory as this skill (call this `<scripts>`).

## Steps

1–2. Same as weak-llm-selffix steps 1–2 (save draft and any target material
   as `inputs.json`; resolve `$PROBE_BASE`; never start servers).

3. **Run exactly one command:**
   `python3 <scripts>/selffix.py draft.txt [inputs.json] --run`

4. **Paste the result verbatim** (from `==== selffix report ====` to the end;
   non-zero exit → paste its final lines instead — that IS the result).
   `OUT OF SCOPE`, `NOT DELEGABLE`, `GATE FAILED` and
   `EXECUTION FAILED VERIFICATION` are final answers, not obstacles to route
   around.

5. **Render (only if the report has a RENDER HINT line).** Convert the
   `.outputs.json` artifact into a short human-readable block following that
   hint, and append it after the report. People read the rendering; machines
   and reviews use the JSON artifact.

## Hard rules
- Never execute the user's task yourself, with or without tools. The ONLY
  execution in this skill happens inside selffix.py's verified pipeline.
- An unverified result is worse than no result — nobody can tell it apart
  from a verified one.
- Never start/stop/kill servers or processes. Never use pkill.
