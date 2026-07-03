---
name: aide-spec-queue
description: Batch-author work-item specs for every unspecced item in a queue, interactively, on one branch — front-loading the human so execution can then run unattended.
---

# Spec a whole queue (batch, interactive)

Author the item specs for **all unspecced items in one queue** in a single
interactive sitting, committing them on **one branch/PR** — a second human
checkpoint mirroring the queue PR. Rationale ("front-load the human"): spec
authoring is where human input pays most, so answer the clarify questions while a
human is present, then let implementation (`/aide-run-queue`) run unattended, and
review the merged results afterwards.

`/aide-run-item` already skips spec-authoring when a complete spec exists, so
pre-authored specs make the execution loop composable as-is.

## User Input

$ARGUMENTS — a queue number (optional; defaults to the Live queue).

## Instructions

1. **Identify the queue** (`docs/aide/queue/queue-NNN.md`, the Live one if no
   argument) and list its items that have **no** spec file in `docs/aide/items/`.
   If none, report "queue fully specced" and stop.
2. **One branch for the whole batch** — not per-item claim branches (those are
   created later, at execution time, by `aide claim`):
   ```
   git switch -c aide/specs-queue-NNN
   ```
3. **Loop over the unspecced items in queue order.** For each, author the spec
   per the `aide-create-item` skill and `.aide/templates/item.md`, with clarify
   mode forced to **`interactive`** regardless of `loop.clarify`: ask the user
   up to 3 targeted questions per ambiguous item (batch related questions
   together to respect the user's time), and encode the answers. When run as an
   orchestrator, spawn a fresh `spec-author` per item with "clarify mode:
   interactive" in its brief and relay its questions to the user.
4. **Pin cross-item interfaces as Assumptions.** These specs are written before
   their dependencies are *implemented*, so every interface a spec relies on from
   an earlier (unbuilt) item goes into its **Assumptions** block; the
   builder/validator hand back if reality diverged. This keeps spec-first
   optional, not load-bearing.
5. **Commit per spec** on the batch branch (separate Bash calls):
   ```
   git add docs/aide/items/NNN-*.md
   git commit -m "docs(NNN): work item spec for <short title>"
   ```
6. **Land the batch.** Push the branch and open a PR for human review of the
   whole spec set (`gh pr create` is ask-gated — that pause is intended):
   ```
   git push -u origin aide/specs-queue-NNN
   ```
   After the PR merges, run `/aide-run-queue NNN` — execution proceeds
   unattended, claiming per-item branches as usual.

## Hard limits

- Specs only: no production code, no tests, no `pytest`, no `progress.md` edits.
- Do not create per-item `aide/NNN-*` claim branches — execution does that.

## Command hygiene

Follow `.aide/conventions.md` §3.
