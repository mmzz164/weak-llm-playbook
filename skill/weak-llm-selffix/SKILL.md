---
name: weak-llm-selffix
description: >-
  ドラフトプロンプトを弱いLLM向けに機械的に正常化して返すアクションスキル(弱い操作者=
  ローカルLLM自身用)。手順全体(振り分け・エンドポイント探索・ゲート・有界fixループ・検証)は
  selffix.py にコード化済みで、スキルは「1コマンド叩いて報告を貼る」薄い前面。自由文タスク
  (レビュー・分類・要約・資料内検索)は裏で影の出力契約が適用され(ユーザーはJSONを書かない)、
  外部ツール必須のタスクは run_agent.py に自動転送される(使い捨ての子セッションのみ権限
  バイパス、操作者自身は権限を持たない)。"/weak-llm-selffix <ドラフト or ファイルパス>" で
  起動。実行と検証済み成果物まで欲しいなら [[weak-llm-selfrun]]。強い操作者が使うなら
  [[weak-llm-fix]] / [[weak-llm-run]]。
---

# weak-llm-selffix — one command; the procedure is code

The entire procedure — routing, endpoint discovery, gates, bounded fix loops,
verification, agent hand-off — is a script (`selffix.py`). The steps are not
yours to execute, so they cannot be skipped, reordered, or "improved".
Scripts live in the `weak-llm-playbook/scripts/` directory in the same skills directory as this skill (call this
`<scripts>`).

## Steps

1. **Save the inputs.** If the argument is a file path, use it as the draft.
   Otherwise write the argument text to `draft.txt` unchanged. If the user
   supplied target material (documents to process, pages to review, items to
   classify), save it as `inputs.json` — an array of document strings
   (or an array of argument tuples for a code task).

2. **Run exactly one command:**
   `python3 <scripts>/selffix.py draft.txt [inputs.json]`
   The script discovers the endpoint itself ($PROBE_BASE, then ports
   8000/8002/8003) and auto-routes tool-requiring tasks to disposable agent
   sessions. Never start, stop or kill servers.

3. **Paste the result verbatim.** Everything from `==== selffix report ====`
   (or run_agent's DIVERGED/AGREED report) to the end is your entire answer.
   If the command exits non-zero, paste its final lines verbatim instead —
   that IS the result. `NO ENDPOINT`, `OUT OF SCOPE`, `NOT DELEGABLE` and
   `GATE FAILED` are final answers, not obstacles to route around.

## Hard rules
- Never execute the user's task yourself, with or without tools. Your only
  moves are: save files, run selffix.py, paste its output.
- An unverified result is worse than no result — nobody can tell it apart
  from a verified one.
- Never start/stop/kill servers or processes. Never use pkill.
