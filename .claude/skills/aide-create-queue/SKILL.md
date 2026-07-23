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
5. **A stage-closing queue ends with a stage-validation item** — when this
   queue completes a roadmap stage, its final item must be
   `Validate stage N: <stage title>`: replay the stage's use cases end-to-end
   (not just the unit suite), and flip any Environment-Gated Capability
   Verification rows the stage introduced to `✅ Verified` where the
   environment allows (`aide env --profile <name>`), else record why they stay
   `❓ Unverified`. Validation is planned, numbered work — never an implicit
   hope.
6. **Consistent format** (parsed by `aide claim` / `aide check`):
   ```
   ### Item NNN: Short Title
   Brief description of the scope and deliverables for this item.
   ```
7. **No status field** — queue state (open/done) is **derived** from
   `progress.md` (a queue is open while any of its items is 📋/🚧), and
   `aide claim` picks the lowest-numbered open queue by default. Do not write a
   `> **Status:** Live` line; the only decorative status note is the completion
   stamp `aide queue tidy` adds to superseded queues.
8. **Wire every item into `progress.md`** — this is where item numbers are born,
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

**Write no "Next:" line into the queue file.** A queue is read throughout its
own execution and again afterwards as history, so a next-step pointer inside it
drifts out of date while the file is still in active use (see
`.aide/conventions.md` §1, "No next-step pointers inside a living document").
The template's header blockquote carries the durable orientation — what the
batch derives from, and that its items are specced into `../items/` and tracked
in `progress.md`. The only status line a queue may carry is the completion stamp
`aide queue tidy` writes on a superseded queue. End the file after the last
`### Item NNN` section.

### Commit the queue immediately (do not leave it untracked)

The queue is a shared project document; `aide claim` reads the committed file.
Commit the new queue, the `progress.md` item-reference back-fill (requirement 8),
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

## Hand-off (say this, don't save it)

Close your turn by naming both ways to proceed — in chat, and in the queue-PR
body if one is opened. A PR body is the right home for a transient pointer: it
is read once, at review time, and is never mistaken for current state
afterwards. The queue file itself gets none of this.

- **Spec the whole queue now** — run `/aide-spec-queue NNN` in one interactive
  sitting (clarify questions answered while a human is present), then let
  execution run unattended.
- **Spec per-item during execution** — run `/aide-run-queue NNN`, or manually
  `/aide-create-item` then `/aide-execute-item` per item in fresh chats.
