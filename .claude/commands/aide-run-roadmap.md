---
description: Drive the AIDE roadmap across MULTIPLE queues — generate a queue, run it to completion (via /aide-run-queue), then generate the next — until the roadmap is exhausted. Default gates each new queue behind a human-reviewed PR; --continuous keeps going without waiting.
argument-hint: "[--continuous] — optional; default is human-gated (PR per queue)"
---

# Run the AIDE roadmap (loop over queues)

The widest AIDE loop: iterate **over queues** across the whole roadmap. Where
`/aide-run-queue` runs the items *within one queue*, this command **generates
each queue and chains them** — create queue → run it → create the next → … —
until `docs/aide/roadmap.md` has no further stage to queue.

The **queue is the human checkpoint.** Items inside an approved queue flow freely
(direct-merge, no PR); the human reviews the *batch plan* roughly once per ~10
items, not every item.

Mode: **$ARGUMENTS**
- *(default, gated)* — each new queue lands via a **human-reviewed PR**; the loop
  **pauses** until the human merges it, then runs the queue.
- `--continuous` — don't wait: commit each new queue straight to `main` and run
  it immediately, looping until the roadmap is exhausted. The human reviews
  queues **after the fact** (git history) and course-corrects via
  `/speckit-aide-feedback-loop` if needed.

This session is only the orchestrator — delegate item execution to
`/aide-run-queue` (which delegates to `/aide-run-item`) and queue *authoring* to
the `queue-planner` subagent. **Command hygiene** applies to any git you issue:
no `cd` prefix, one command per Bash call, no `2>&1`, no command substitution in
commit messages, recon via Bash + `grep`.

## Orchestration model & session scope

- **Run the orchestrator on Sonnet.** Orchestration here is light dispatch and
  gating — spawn a subagent, read its short summary, decide the next step. The
  heavy cognition lives in the subagents (`queue-planner` and `spec-author` on
  Opus; builder/validator on Sonnet). A slash command can't pin the session
  model, so if you're on Opus, `/model sonnet` before a long run.
- **One orchestrator session ≈ one queue.** Subagents can't reliably spawn their
  own subagents, so we keep a single orchestrator + one worker level rather than
  nesting orchestrators. Bound that session to a single queue:
  - *gated* — you already stop at each queue PR; the human re-invokes for the next
    queue, so each queue gets a fresh session naturally.
  - *`--continuous`* — when a queue finishes, **start a fresh orchestrator session
    for the next queue** (re-invoke `/aide-run-roadmap --continuous`) rather than
    carrying one ever-growing session across the whole roadmap.

## Determine current state first (resumable)

This loop spans sessions (gated mode pauses for a human merge), so always start
by working out where things stand. `git fetch --all --prune`, then read
`docs/aide/roadmap.md`, `docs/aide/progress.md`, and the queue files:

| State | Action |
|---|---|
| **Roadmap exhausted** — every stage ✅ / deferred / excluded | Report done. Stop. |
| **An open `aide/queue-NNN` PR is awaiting merge** (gated) | Tell the user to review/merge it; **stop**. Re-invoke after merge. |
| **Latest queue merged to `main` but has 📋 items left** | Run that queue → go to **Run a queue**. |
| **Latest queue fully exhausted, roadmap has more stages** | Generate the next queue → go to **Generate the next queue**. |
| **No queue exists yet** | Generate the first queue → go to **Generate the next queue**. |

## Generate the next queue

Queue authoring is delegated to the **`queue-planner` (Opus)** subagent — never
run `/speckit-aide-create-queue` inline in the orchestrator (it would pollute this
session's context and tie queue quality to the orchestration model). The planner
writes + commits `queue-NNN.md` **and** tidies the superseded `queue-(NNN-1).md`
on whatever branch it's on, then returns a one-line summary. **You** (orchestrator)
prepare the branch and handle push/PR/merge around it.

1. **Gated (default):**
   - `git switch -c aide/queue-NNN` off an up-to-date `main` (`git pull --rebase`).
   - **Spawn `queue-planner`**: "Generate queue NNN on branch `aide/queue-NNN`;
     tidy the previous queue; commit both; do not push or PR." Wait for its summary.
   - `git push -u origin aide/queue-NNN`, then open a **PR**:
     `gh pr create` titled `docs(aide): work queue NNN`, body summarising the batch.
   - **STOP and tell the user**: review/edit/merge the queue PR, then re-invoke
     `/aide-run-roadmap` (or `/aide-run-queue NNN`) to execute it. A queue PR is
     the right place to reshape the plan before any code is built against it.
2. **`--continuous`:**
   - On `main` (`git pull --rebase`), **spawn `queue-planner`**: "Generate queue
     NNN on `main`; tidy the previous queue; commit both; do not push." Then
     `git push` the planner's commit to `main`.
   - Proceed immediately to **Run a queue** (do not open a PR, do not wait).

## Run a queue

Invoke **`/aide-run-queue NNN`** for the current queue. It claims and drives each
item to merge and **stops when that queue is empty** (it never creates the next
queue). When it returns:

- **Gated:** loop back to **Generate the next queue** for NNN+1 (which branches +
  PRs + stops again — the human re-invokes, giving a fresh session per queue).
- **`--continuous`:** **start a fresh orchestrator session** for the next queue —
  re-invoke `/aide-run-roadmap --continuous` (state-detection will pick up at
  *Generate the next queue* for NNN+1) — rather than carrying one ever-growing
  session across the whole roadmap. Keep going until the roadmap is exhausted or a
  hard blocker appears.

## Tidy the previous queue

Whenever you generate queue NNN, first tidy the now-superseded queue NNN-1 so the
queue history stays legible and it's obvious which batch is live:

- Add/update a status line at its top, e.g.
  `> **Status:** ✅ Completed — superseded by queue-NNN (YYYY-MM-DD).`
- Mark each of its items with its final `progress.md` state (✅ done, or ⏸️/❌ if
  carried/dropped) so a stale 📋 list isn't left implying open work.
- Commit that tidy-up alongside the new queue (gated: on the `aide/queue-NNN`
  branch; continuous: directly to `main`).

This keeps exactly one **live** queue and a clean trail of closed ones.

## If the human is unhappy with an auto-generated queue

(Most relevant in `--continuous`, where items may already be merged.) Run
`/speckit-aide-feedback-loop`: adjust `vision.md`/`roadmap.md`/`progress.md` as
needed, and because merged work can't be cleanly un-merged, **identify which
already-implemented items need adapting and capture them as new corrective items**
in the next queue rather than rewriting history. The feedback loop is the
sanctioned way to course-correct without blocking forward progress.

## When to stop and ask the user

- **Always, in gated mode, after opening each queue PR** — that pause is the
  whole point.
- A queue or item needs an edit to a **framework/process** file (`vision.md`,
  `roadmap.md`, `constitution.md`, `CLAUDE.md`, `.claude/**`,
  `.specify/extensions/**`) — reviewed PR, never auto-merge.
- `/aide-run-queue` reports an item blocked, a PR/force-push need, or a
  build↔validate cycle exceeding 3 rounds — surface it and pause.
