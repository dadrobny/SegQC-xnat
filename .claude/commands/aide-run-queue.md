---
description: Run the AIDE work-item queue to completion — claim, create-item, execute-item, test, commit, direct-merge — looping until the queue is empty. Pauses only for PRs and major structural changes.
argument-hint: "[queue number, e.g. 001 — optional; defaults to the active queue]"
---

# Run the AIDE queue

Drive the AIDE loop (`docs/aide/`) over **every remaining item** in the queue,
one item at a time, until the queue is empty — without a fresh chat per item.
Apply the project's model-routing and approval policy from `CLAUDE.md`:

- **Light, read-only recon → delegate to the `scout` subagent (Sonnet):** finding
  code, reading specs, checking queue/progress state, listing branch/PR claims.
- **Heavy work → delegate to the `builder` subagent (Opus), or do it on the main
  thread if it's already Opus:** writing code, writing tests, structural work.
- **Commits and work-item direct-merges to `main` are pre-approved** — make them
  once green. **Stop and ask the user** only for: opening a **PR**, **force-push /
  history rewrite**, or a **major structural change** (pipeline redesign, or any
  edit to framework/process files: `CLAUDE.md`, `vision.md`, `roadmap.md`,
  `constitution.md`, `.claude/skills|commands|agents/**`, `.specify/extensions/**`).

Target queue: **$ARGUMENTS** (if empty, use the highest-numbered
`docs/aide/queue/queue-*.md`).

## Loop

Repeat until no 📋 items remain in the target queue:

1. **Sync & pick (scout).** `git fetch --all --prune`. Read the queue and
   `docs/aide/progress.md`; identify the next 📋 item that isn't already claimed
   (no `aide/NNN-*` remote branch / open PR for it). If every remaining item is
   blocked or claimed, stop and report.

2. **Claim.** `git switch -c aide/NNN-short-name` and **push immediately**
   (`git push -u origin aide/NNN-short-name`) so the claim is visible. (Push is
   pre-approved.)

3. **Create the item spec if missing.** If `docs/aide/items/NNN-*.md` doesn't
   exist yet, run `/speckit-aide-create-item NNN` first.

4. **Implement (builder).** Hand the item to the `builder` agent (or implement on
   the main thread if already Opus): write code + tests per the spec, run
   `python -m pytest` plus the item's manual-validation checklist, and update the
   item's Decisions and its `progress.md` row (📋→🚧→✅, scoped to this item).
   `git pull --rebase` before editing `progress.md`.

5. **Land it.** When green: commit (plain message, **no co-author trailer**),
   then direct-merge to `main`:
   `git switch main && git pull --rebase && git merge aide/NNN-short-name && git push`.
   Re-run `pytest` on merged `main` to confirm still green.

6. **Checkpoint.** Briefly report the item as done (tests + merge), then continue
   to the next item. **Do not** wait for approval to start the next item.

## When to stop and ask the user

- The next step would open a **PR**, **force-push**, or rewrite shared history.
- The item requires a **major structural change** or an edit to a framework/
  process file (these need a reviewed PR — never direct-merge them).
- Tests can't be made green, requirements are unclear/contradictory, or the item
  is blocked on an unmerged dependency. Document the blocker in the item file and
  suggest `/speckit-aide-feedback-loop`.

## On queue exhaustion

When no 📋 items remain: report a summary (items completed, branches merged, test
status). If the roadmap has more stages, tell the user to run
`/speckit-aide-create-queue` (in a fresh chat) for the next batch.