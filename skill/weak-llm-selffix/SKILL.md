---
name: weak-llm-selffix
description: >-
  ドラフトプロンプトを弱いLLM向けに機械的に正常化して返すアクションスキル(弱い操作者=
  ローカルLLM自身用)。手順全体(振り分け・ゲート・有界fixループ・検証)は selffix.py に
  コード化済みで、スキルは「1コマンド叩いて報告を貼る」薄い前面。自由文タスク(レビュー・
  分類・要約・資料内検索)は裏で影の出力契約が適用される(ユーザーはJSONを書かない)。
  外部ツール必須のタスクは OUT OF SCOPE(run_agent.py の領分)。
  "/weak-llm-selffix <ドラフト or ファイルパス>" で起動。実行と検証済み成果物まで
  欲しいなら [[weak-llm-selfrun]]。強い操作者が使うなら [[weak-llm-fix]] / [[weak-llm-run]]。
---

# weak-llm-selffix — one command; the procedure is code

The entire procedure — routing, gates, bounded fix loops, verification — is a
script (`selffix.py`). The steps are not yours to execute, so they cannot be
skipped, reordered, or "improved". Scripts live in
the `weak-llm-playbook/scripts/` directory in the same skills directory as this skill (call this `<scripts>`).

## Steps

1. **Save the inputs.** If the argument is a file path, use it as the draft.
   Otherwise write the argument text to `draft.txt` unchanged. If the user
   supplied target material (documents to process, pages to review, items to
   classify), save it as `inputs.json` — an array of document strings
   (or an array of argument tuples for a code task).

2. **Endpoint.** Use `$PROBE_BASE` if set; otherwise probe ports 8000/8002/8003
   with `curl -s -m2 http://localhost:<p>/v1/models` and export the first that
   answers. If none answers, reply `NO ENDPOINT — start a model server first`
   and stop. Never start, stop or kill servers.

3. **Run exactly one command:**
   `python3 <scripts>/selffix.py draft.txt [inputs.json]`

4. **Paste the result verbatim.** Everything from `==== selffix report ====`
   to the end is your entire answer. If the command exits non-zero, paste its
   final lines verbatim instead — that IS the result. `OUT OF SCOPE`,
   `NOT DELEGABLE` and `GATE FAILED` are final answers, not obstacles to route
   around.

## Hard rules
- Never execute the user's task yourself, with or without tools. Your only
  moves are: save files, run selffix.py, paste its output.
- An unverified result is worse than no result — nobody can tell it apart
  from a verified one.
- Never start/stop/kill servers or processes. Never use pkill.
