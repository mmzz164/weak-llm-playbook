---
name: weak-llm-selfrun
description: >-
  [[weak-llm-selffix]] の実行版アクションスキル(弱い操作者=ローカルLLM自身用)。
  ドラフトを機械的に正常化(selffixの手順1〜7)した上でそのまま実行し、fix時に記録した
  答え合わせ表(expected.json)との再生照合(replay_check.py)を通った成果物だけを返す。
  判断ステップなし・自己採点なし(合否は全てスクリプトのexit code)。
  "/weak-llm-selfrun <ドラフト or ファイルパス>" で起動。プロンプトだけ欲しいなら
  [[weak-llm-selffix]]。強い操作者が使うなら [[weak-llm-run]]。
---

# weak-llm-selfrun — normalize, execute, and return a replay-verified artifact

You are the operator. Follow the steps EXACTLY, in order. Every gate is a
script: trust its exit code and printed output, never your own assessment.
The scripts live in the `weak-llm-playbook/scripts/` directory in the same
skills directory as this skill — call this `<scripts>` below.

## Steps

1–7. **Normalize.** Follow steps 1–7 of weak-llm-selffix (its SKILL.md is in
   the same skills directory) exactly, including its scope gate and every
   gate script. Continue from the state where the fixed prompt `<final>`
   exists and check_fixed.py printed PASS.

8. **Execute + replay gate.** spec_holes --fix has written the expected-behavior
   table next to `<final>` (same name, `.expected.json` instead of `.txt`). Run:
   `python3 <scripts>/replay_check.py <final-root>.expected.json --prompt <final>`
   - PASS → it prints the artifact path (`.impl.py` for code, `.outputs.json`
     for extraction and contract tasks). That artifact is the verified result.
   - FAIL (it retries 3 times internally — do NOT rerun it in a loop) → reply
     `EXECUTION FAILED VERIFICATION`, paste its mismatch lines, and stop.

9. **Render (CONTRACT TASK only).** Convert the `.outputs.json` artifact into
   a short human-readable block, following the "render hint" line that
   apply_contract.py printed in step 2. People read the rendering; machines
   and reviews use the JSON artifact.

10. **Report — output exactly this block and nothing else:**

   ```
   FIXED PROMPT: <path of final file>
   INPUTS: inputs.json (check_inputs: PASS)
   VERIFY: <paste the "[fix] holes: N -> 0" line from spec_holes>
   ARTIFACT: <path printed by replay_check>
   REPLAY: <paste replay_check's PASS line>
   PINNED (every line needs human review — intent was NOT checked):
   <paste every "- ..." line of the pin block, or "none — draft was already unambiguous">
   NOT DONE: intent review, model-quirk injection. A human or a stronger model
   must review every pinned line before use.
   <CONTRACT TASK only: the rendered block from step 9>
   ```

## Hard rules
- Same as weak-llm-selffix, plus:
- The ONLY execution allowed is `replay_check.py` in step 8. Never run the
  task "directly" or outside the gates — an unverified result is worse than
  no result, because nobody can tell it apart from a verified one.
- Never start/stop/kill servers or processes. Never use pkill.
