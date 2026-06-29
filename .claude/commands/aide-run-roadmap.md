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
`/aide-run-queue` (which delegates to `/aide-run-item`). **Command hygiene**
applies to any git you issue: no `cd` prefix, one command per Bash call, no
`2>&1`, no command substitution in commit messages, recon via Bash + `grep`.

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

1. Work out the next queue number NNN (highest existing + 1) and **tidy the old
   queue document** first (see *Tidy the previous queue* below).
2. **Gated (default):**
   - `git switch -c aide/queue-NNN` off an up-to-date `main` (`git pull --rebase`).
   - Run `/speckit-aide-create-queue` (it generates **and commits** `queue-NNN.md`
     on this branch; see that skill).
   - `git push -u origin aide/queue-NNN`, then open a **PR**:
     `gh pr create` titled `docs(aide): work queue NNN` describing the batch.
   - **STOP and tell the user**: review/edit/merge the queue PR, then re-invoke
     `/aide-run-roadmap` (or `/aide-run-queue NNN`) to execute it. A queue PR is
     the right place to reshape the plan before any code is built against it.
3. **`--continuous`:**
   - On `main` (`git pull --rebase`), run `/speckit-aide-create-queue` — it
     commits `queue-NNN.md` straight to `main` — then `git push`.
   - Proceed immediately to **Run a queue** (do not open a PR, do not wait).

## Run a queue

Invoke **`/aide-run-queue NNN`** for the current queue. It claims and drives each
item to merge and **stops when that queue is empty** (it never creates the next
queue). When it returns:

- **Gated:** loop back to **Generate the next queue** for NNN+1 (which branches +
  PRs + stops again).
- **`--continuous`:** loop back to **Generate the next queue** for NNN+1 and keep
  going — no pause — until the roadmap is exhausted or a hard blocker appears.

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
