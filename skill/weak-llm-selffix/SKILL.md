---
name: weak-llm-selffix
description: >-
  弱い操作者(ローカルLLM自身)が自分のエンドポイントを相手にドラフトプロンプトを機械的に
  正常化するアクションスキル。/weak-llm-fix の弱操作者版: 判断ステップを全廃し、プローブ入力は
  固定レシピ+check_inputs.pyの機械採点、ピン留め・再検証は spec_holes --fix、意図レビューは
  行わず全ピン行を人間への要確認リストとして返す。操作者は一度も自己採点しない(採点は全て
  スクリプトのexit codeが行う)。自由文タスク(レビュー・分類・要約・資料内検索)は
  apply_contract.py が影の出力契約(JSONは測定器の内部形式でありユーザーは書かない)を
  当てて測定可能にし、自由文フィールドは比較ポリシー(count/exists/free)でノイズ除外。
  "/weak-llm-selffix <ドラフト or ファイルパス>" で起動。実行と検証済み成果物まで
  欲しいなら [[weak-llm-selfrun]]。強い操作者が使うなら [[weak-llm-fix]] / [[weak-llm-run]]。
---

# weak-llm-selffix — normalize a draft prompt with zero judgment calls

You are the operator. Follow the steps EXACTLY, in order. Every gate is a
script: trust its exit code and printed output, never your own assessment.
The scripts live in the `weak-llm-playbook/scripts/` directory in the same
skills directory as this skill — call this `<scripts>` below. Put work files
in the current directory or /tmp.

## Steps

1. **Save the draft.** If the argument is a file path, use that file as
   `draft.txt`. Otherwise write the argument text to `draft.txt` unchanged.

2. **Scope gate.**
   - If the draft needs external tools (MCP, web browsing, calling other
     services), reply `OUT OF SCOPE: needs external tools` and stop.
   - (a) implementing a function / a piece of code → CODE TASK.
   - (b) extracting or reformatting data from given documents → EXTRACTION TASK.
   - (c) anything else (review, classify, summarize, look something up in
     given material, ...): run `python3 <scripts>/apply_contract.py draft.txt`.
     - exit 0 → CONTRACT TASK: from now on use `draft.contracted.txt` wherever
       these steps say `draft.txt`, and append `--policy draft.policy.json` to
       every spec_holes command. Note the "render hint" line it prints.
       Everything else works exactly like EXTRACTION.
     - exit 1 → reply `OUT OF SCOPE: no contract family matches` and stop.

3. **Endpoint.** If `$PROBE_BASE` is set, use it. Otherwise run
   `for p in 8000 8002 8003; do curl -s -m2 http://localhost:$p/v1/models; done`
   and `export PROBE_BASE=http://localhost:<first port that answered>`.
   If none answers, reply `NO ENDPOINT — start a model server first` and stop.
   NEVER start, stop or kill servers or processes. Never use pkill.

4. **Write probe inputs (fixed recipe — do not improvise).**
   - Code task → `inputs.json` = JSON array of argument tuples. Write one
     normal case first (copy the draft's own example if it has one). Then add
     one new tuple per rule, changing exactly ONE thing each time:
     - each list/str/dict argument: once empty, once with exactly 1 element,
       once containing equal elements (a tie)
     - each numeric argument: once 0, once negative, once larger than the
       container it refers to (if any)
     - anything the draft calls optional: once absent / null
   - Extraction task → `inputs.json` = JSON array of document strings:
     1. one complete document (every field present, plain formats)
     2. one document missing one field
     3. one document with two competing candidates for the same field
     4. one document in a different format (a range like "3-5", another date
        style, etc.)
   - 5–8 inputs total.
   - CONTRACT TASK: the documents are the user's target(s) — the page to
     review, the items to classify, and so on. If the user supplied fewer
     than 4, use what exists and pass `--min <number of documents>` to
     check_inputs.py in step 5.

5. **Inputs gate.** Run `python3 <scripts>/check_inputs.py inputs.json`.
   If it prints FAIL, add exactly the inputs it suggests (copy them verbatim)
   and rerun. At most 3 rounds; if still FAIL, paste its last output in your
   report and stop.

6. **Fix loop (at most 3 runs of spec_holes).**
   - Run 1: `python3 <scripts>/spec_holes.py draft.txt inputs.json --fix draft.fixed.txt`
   - If exit code is 1 (holes remain), run 2:
     `python3 <scripts>/spec_holes.py draft.fixed.txt inputs.json --fix draft.fixed2.txt`
   - If still 1, run 3 the same way (`draft.fixed2.txt` → `draft.fixed3.txt`).
   - If still 1 after run 3: reply `NOT DELEGABLE: holes remain after 3 fix
     rounds`, paste the remaining-holes lines, and stop.
   - The LAST file written is the result — call it `<final>`.

7. **Handoff gate.** Run `python3 <scripts>/check_fixed.py draft.txt <final>`.
   It must print PASS. If it prints FAIL you modified the draft text —
   go back to step 6 and regenerate; do not edit `<final>` by hand.

8. **Report — output exactly this block and nothing else:**

   ```
   FIXED PROMPT: <path of final file>
   INPUTS: inputs.json (check_inputs: PASS)
   VERIFY: <paste the "[fix] holes: N -> 0" line from spec_holes>
   PINNED (every line needs human review — intent was NOT checked):
   <paste every "- ..." line of the pin block, or "none — draft was already unambiguous">
   PROFILES: <output of: ls <scripts>/profile_*.json 2>/dev/null | grep -i "<model>" — or "none">
   NOT DONE: intent review, model-quirk injection. A human or a stronger model
   must review every pinned line before use.
   ```

   (To also execute the fixed prompt and return a verified artifact, the user
   invokes `/weak-llm-selfrun` instead — do not execute anything here.)

## Hard rules
- Never edit the draft's own text. Fixes may only APPEND pinned lines
  (check_fixed.py enforces this).
- Never mark your own work as "probably fine" — only gate scripts decide.
- Probes execute generated code on this machine. Only use trusted endpoints.
- Never start/stop/kill servers or processes. Never use pkill.
