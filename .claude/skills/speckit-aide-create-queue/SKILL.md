---
name: speckit-aide-create-queue
description: Generate a prioritized queue of the next batch of work items.
compatibility: Requires spec-kit project structure with .specify/ directory
metadata:
  author: github-spec-kit
  source: aide:commands/create-queue.md
---

# Create Queue

Generate the next batch of prioritized work items.

## Purpose

This is Step 4 of the AI-Driven Engineering workflow. The queue contains the next batch of actionable work items prioritized from the roadmap and progress documents — **scoped to one cohesive roadmap unit (a single stage, or a small phase), capped at about 10 items, whichever is smaller** (see Requirement 1). This step is repeated whenever the current queue is exhausted.

## Prerequisites

- `docs/aide/vision.md` must exist
- `docs/aide/roadmap.md` must exist
- `docs/aide/progress.md` must exist

## Instructions

Read `docs/aide/vision.md`, `docs/aide/roadmap.md`, and `docs/aide/progress.md`, then create a prioritized queue of work items.

### Requirements

1. **Scope to one cohesive roadmap unit, capped at ~10 items** — a queue should
   cover a **single stage** (or, if a phase is small, that whole phase), **or**
   about **10 items — whichever is smaller**:
   - If the next stage's remaining items fit in **≤ ~10**, queue **exactly that
     stage** and **stop at the stage boundary — even if that yields fewer than 10
     items** (e.g. a 4-item stage → a 4-item queue). Do **not** pad the batch by
     pulling items from the following stage: a stage-sized queue keeps the scope
     cohesive and makes the queue the natural checkpoint where lessons from
     finishing one stage inform the next.
   - If a **phase** is small enough that several of its stages together fit in
     ≤ ~10 items, the queue **may span that whole phase**.
   - If a stage needs **more than ~10 items**, cap the queue at ~10 and carry the
     remainder into the next queue (the stage spans multiple queues).
   The ~10 ceiling is a **context budget, not a target** — small stages yield
   small queues. Prioritise by roadmap order and unblocked dependencies.
2. **No duplicates** — check existing queues in `docs/aide/queue/queue-*.md` to avoid re-queuing completed or already-queued items
3. **Sequential numbering** — work item numbers must be sequential across all queues. Check existing queues to find the highest item number used, then start from the next number. For example, if `queue-001.md` ends at item 10, `queue-002.md` starts at item 11.
4. **Testable items** — each item must be testable locally
5. **Sensible batch** — within the scoped stage/phase, the batch should still be a
   reasonable chunk of work (roughly a week); the stage/phase boundary and the ~10
   cap in Requirement 1 govern the size, not a fixed count.
6. **Consistent format** — each item must follow this format so other commands can parse it:
   ```
   ### Item NNN: Short Title
   Brief description of the scope and deliverables for this item.
   ```
   Where NNN is the sequential item number (e.g., 001, 012, 023).

### Queue Naming

Name the queue file sequentially: `queue-001.md`, `queue-002.md`, etc.

### Tidy the previous queue first

Before (or alongside) writing the new queue, **tidy the now-superseded queue
NNN-1** so the history stays legible and exactly one queue is "live":

- Add/update a status line at its top, e.g.
  `> **Status:** ✅ Completed — superseded by queue-NNN (YYYY-MM-DD).`
- Reflect each item's final `progress.md` state (✅ done, or ⏸️/❌ if carried or
  dropped) so a stale 📋 list isn't left implying open work.

If this is the first queue, there is nothing to tidy — skip.

### Output

Save the queue to `docs/aide/queue/queue-NNN.md` (where NNN is the next sequential number).

### Commit the queue immediately (do not leave it untracked)

A queue file is a **shared project document**, not a scratch note — an untracked
or machine-local queue is invisible to collaborators and to the scout, which
reads the committed queue. As soon as the file is written, **commit it and the
previous-queue tidy-up on the current branch**, each as a separate Bash call:

```
git add docs/aide/queue/queue-NNN.md docs/aide/queue/queue-<NNN-1>.md
git commit -m "docs(aide): add work queue NNN"
```

**Push/PR is the caller's job, not this step's:**

- **Run standalone (manual)** — also push to `main` (`git pull --rebase` first;
  queue files are additive AIDE docs, allowed per `CLAUDE.md`): `git pull --rebase`,
  then `git push`.
- **Invoked as the `queue-planner` subagent inside `/aide-run-roadmap`** — commit
  only, do **not** push or open a PR. The orchestrator handles it: in gated mode
  you're on the `aide/queue-NNN` branch and it pushes + opens the human-reviewed
  PR; in `--continuous` it pushes your commit to `main`.

Either way, do **not** end this step with the queue left only in the working tree.

## Next Step

Select an item from the queue and start a **new chat session**. Run `/speckit-aide-create-item` with the item description to create a detailed work item specification.