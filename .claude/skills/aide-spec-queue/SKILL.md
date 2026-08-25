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

$ARGUMENTS — a queue number (optional; defaults to the live queue — the
lowest-numbered one with open items).

## Instructions

1. **Identify the queue** (`docs/aide/queue/queue-NNN.md`, the Live one if no
   argument) and list its items that have **no** spec file in `docs/aide/items/`.
   If none, report "queue fully specced" and stop.
2. **One branch for the whole batch** — not per-item claim branches (those are
   created later, at execution time, by `aide claim`). Let the CLI name it; a
   hand-typed name that `aide claim` does not recognise as a queue branch
   retargets the merge silently:
   ```
   python .aide/scripts/aide.py queue start NNN --specs
   ```
3. **Loop over the unspecced items in queue order.** For each, author the spec
   per the `aide-create-item` skill and `.aide/templates/item.md`, with clarify
   mode forced to **`interactive`** regardless of `loop.clarify`: ask the user
   up to 3 targeted questions per ambiguous item (batch related questions
   together to respect the user's time), and encode the answers. When run as an
   orchestrator, spawn a fresh `spec-author` per item with "clarify mode:
   interactive" in its brief and relay its questions to the user.
4. **Pin cross-item interfaces as Assumptions — from both ends.** These specs
   are written before their dependencies are *implemented*, so every interface a
   spec relies on from an earlier (unbuilt) item goes into its **Assumptions**
   block; the builder/validator hand back if reality diverged. And the
   *producing* spec must enumerate the **serialised** shape its consumers read
   (JSON layout, which records appear in a walk, what strict mode rejects), not
   only its API — otherwise each consumer independently ships a tolerant reader
   plus a hand-back clause where a straight assertion belonged. This keeps
   spec-first optional, not load-bearing.
5. **Reconcile the batch before landing it.** Every spec is visible at once,
   which is the one moment a cross-item collision is cheap to fix. Run the
   check rather than reading N specs against each other by eye:
   ```
   python .aide/scripts/aide.py check --queue NNN
   ```
   It reports two specs claiming **May change** on the same path, one spec's
   **May change** overlapping another's **Asserts against** (the collision that
   reliably reaches CI as a red test in the *earlier* item, for doing exactly
   what the loop asked), and dependency cycles or dependencies on items that
   exist nowhere. Fix each by amending a spec, naming which side changed.

   Then spawn the **`spec-reviewer`** agent once, for what the check cannot
   decide, because it turns on what a criterion *means* rather than what a spec
   declares — an AC that cannot be satisfied without touching a path its own
   spec never authorised or its Assumptions bar; a consumer asserting against a
   shape its producer never pinned; a dependency aside pointing the wrong way.
   Write the report first so the agent starts from it instead of re-deriving
   it, substituting this project's `docs_dir` (shown at its `docs/aide`
   default):
   ```
   python .aide/scripts/aide.py check --queue NNN --report docs/aide/status/queue-NNN-specs.json
   ```
   Give the agent the queue number and that path. It **reviews**, it does not
   fix: relay its findings to the user and let them arbitrate — every recorded
   instance needed a human call on which side was wrong (correct the AC, or
   widen the authorised paths). Apply the decisions to the specs yourself, then
   re-run the check. The report is derived output under `<docs_dir>/status/`;
   do not commit it. The installer's `.gitignore` block covers the default
   location only, so if this project moved `docs_dir`, confirm the directory is
   actually ignored before writing there.
6. **Commit per spec** on the batch branch (separate Bash calls):
   ```
   git add docs/aide/items/NNN-*.md
   git commit -m "docs(NNN): work item spec for <short title>"
   ```
7. **Land the batch.** Push the specs and open a PR for human review of the
   whole spec set (`gh pr create` is ask-gated — that pause is intended). Step 2
   already set the upstream, so this types no branch name either:
   ```
   git push
   ```
   After the PR merges, run `/aide-run-queue NNN` — execution proceeds
   unattended, claiming per-item branches as usual.

## Hard limits

- Specs only: no production code, no tests, no `pytest`, no `progress.md` edits.
- Do not create per-item `aide/NNN-*` claim branches — execution does that.

## Command hygiene

Follow `.aide/conventions.md` §3 (no `cd`, one command per Bash call, no `2>&1`,
no command substitution in commits, recon via the Bash tool with `grep`, the
`aide` CLI as `python .aide/scripts/aide.py …`). A `PreToolUse` hook
(`.claude/hooks/command_hygiene_guard.py`) enforces the mechanical rules — a
violating shape is blocked and bounced back with the fix.
