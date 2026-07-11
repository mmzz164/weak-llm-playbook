---
name: weak-llm-selfrun
description: >-
  [[weak-llm-selffix]] の実行版アクションスキル(弱い操作者=ローカルLLM自身用)。
  ドラフトを機械的に正常化した上でそのまま実行し、fix時に記録した答え合わせ表
  (expected.json)との再生照合を通った成果物だけを返す。手順全体は selffix.py --run に
  コード化済みで、スキルは「1コマンド叩いて報告を貼る」薄い前面。外部ツール必須の
  タスクは run_agent.py に自動転送(子セッションのみ権限バイパス)。
  "/weak-llm-selfrun <ドラフト or ファイルパス>" で起動。プロンプトだけ欲しいなら
  [[weak-llm-selffix]]。強い操作者が使うなら [[weak-llm-run]]。
---

# weak-llm-selfrun — one command; normalize, execute, replay-verify

Identical to weak-llm-selffix, except the one command includes `--run`: after
fixing the prompt, the script executes it and verifies the execution against
the recorded expected-behavior table. Scripts live in
the `weak-llm-playbook/scripts/` directory in the same skills directory as this skill (call this `<scripts>`).

## Steps

1. Same as weak-llm-selffix step 1 (save draft, and any target material as
   `inputs.json`).

2. **Run exactly one command:**
   `python3 <scripts>/selffix.py draft.txt [inputs.json] --run`
   The script discovers the endpoint itself and auto-routes tool-requiring
   tasks to disposable agent sessions. Never start, stop or kill servers.

3. **Paste the result verbatim** (the report block, or the command's final
   lines on a non-zero exit — that IS the result). `NO ENDPOINT`,
   `OUT OF SCOPE`, `NOT DELEGABLE`, `GATE FAILED` and
   `EXECUTION FAILED VERIFICATION` are final answers, not obstacles to route
   around.

4. **Render (only if the report has a RENDER HINT line).** Convert the
   `.outputs.json` artifact into a short human-readable block following that
   hint, and append it after the report. People read the rendering; machines
   and reviews use the JSON artifact.

## Hard rules
- Never execute the user's task yourself, with or without tools. The ONLY
  execution in this skill happens inside selffix.py's verified pipeline.
- An unverified result is worse than no result — nobody can tell it apart
  from a verified one.
- Never start/stop/kill servers or processes. Never use pkill.
