---
name: aide-create-queue
description: Generate a prioritized queue of the next batch of work items.
---

# Create Queue

Generate the next batch of prioritized work items — Step 4 of the AIDE loop,
repeated whenever the current queue is exhausted. The batch is **scoped to one
cohesive roadmap unit (a single stage, or a small phase), capped at
`loop.queue_cap` items from `aide.toml` (default ~10), whichever is smaller.**

## Prerequisites

- `docs/aide/vision.md`, `docs/aide/roadmap.md`, and `docs/aide/progress.md`
  must exist.

## Instructions

Read vision, roadmap, and progress, then write the queue from the template
**`.aide/templates/queue.md`**.

### Requirements

1. **Scope to one cohesive roadmap unit, capped at ~`loop.queue_cap` items**:
   - If the next stage's remaining items fit within the cap, queue **exactly that
     stage** and **stop at the stage boundary — even if that yields fewer items**.
     Do not pad from the following stage: a stage-sized queue keeps scope cohesive
     and makes the queue the checkpoint where one stage's lessons inform the next.
   - A small **phase** whose stages together fit within the cap may be queued
     whole.
   - A stage needing more than the cap spans multiple queues.
   The cap is a **context budget, not a target**. Prioritise by roadmap order and
   unblocked dependencies.
2. **No duplicates** — check existing `docs/aide/queue/queue-*.md` to avoid
   re-queuing completed or already-queued items.
3. **Sequential numbering** — item numbers are sequential across **all** queues;
   find the highest existing number and continue from it. Never restart.
4. **Testable items** — each item must be testable locally.
5. **Consistent format** (parsed by `aide claim` / `aide check`):
   ```
   ### Item NNN: Short Title
   Brief description of the scope and deliverables for this item.
   ```
6. **Exactly one Live queue** — the new file carries `> **Status:** Live`;
   `python .aide/scripts/aide.py check` enforces uniqueness.
7. **Wire every item into `progress.md`** — this is where item numbers are born,
   so it is also where they must be recorded in the progress tracker. For each
   `### Item NNN` you add, ensure the number appears as an `*(Item NNN)*`
   reference on the matching **deliverable bullet** under that item's roadmap
   **stage section** in `docs/aide/progress.md`:
   - Append to an existing reference when a deliverable maps to several items
     (`… *(Items 006, NNN)*`); add the reference to the bullet that has none; or,
     if the item delivers something not yet listed, add a new
     `- 📋 <deliverable>. *(Item NNN)*` bullet under the right stage.
   - **Never change a deliverable's status icon** — leave it 📋. This step only
     makes the item *trackable*; status transitions (📋→🚧→✅) are
     `aide progress set`'s job during execution.
   - Why: `aide progress set NNN` finds the bullet to flip by its `*(Item NNN)*`
     reference. An item with no reference is untracked, and `progress set` now
     hard-errors on it (engine ≥ 1.0.1) rather than silently no-op'ing — so a
     future stage's deliverables, authored (step 3) before this queue assigned
     numbers, must be back-filled here.

### Tidy the previous queue first

Mark the superseded queue NNN-1 completed with the CLI:

```
python .aide/scripts/aide.py queue tidy <NNN-1>
```

Then, if any of its item lines still read 📋, reflect their final `progress.md`
state (✅ done, ⏸️/❌ if carried or dropped). Skip if this is the first queue.

### Output

Save to `docs/aide/queue/queue-NNN.md` (next sequential number).

### Commit the queue immediately (do not leave it untracked)

The queue is a shared project document; `aide claim` reads the committed file.
Commit the new queue, the `progress.md` item-reference back-fill (requirement 7),
and the tidy-up on the current branch, each a separate Bash call:

```
git add docs/aide/queue/queue-NNN.md docs/aide/queue/queue-<NNN-1>.md docs/aide/progress.md
git commit -m "docs(aide): add work queue NNN"
```

**Push/PR is the caller's job, not this step's:**

- **Run standalone (manual)** — also `git pull --rebase` then `git push`.
- **Invoked as the `queue-planner` subagent inside `/aide-run-roadmap`** — commit
  only; the orchestrator pushes the `aide/queue-NNN` branch and opens the
  human-reviewed queue PR.

## Next Step

Two ways to proceed — suggest both to the user (and in the queue-PR body):

- **Spec the whole queue now** — run `/aide-spec-queue NNN` in one interactive
  sitting (clarify questions answered while a human is present), then let
  execution run unattended.
- **Spec per-item during execution** — run `/aide-run-queue NNN`, or manually
  `/aide-create-item` then `/aide-execute-item` per item in fresh chats.
