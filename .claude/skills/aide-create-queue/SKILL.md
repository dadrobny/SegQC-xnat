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

### Read the open insight inbox first

**The open inbox is an input to queue authoring, not only an output of triage**
(`.aide/conventions.md` §1 → `insights.md`). Read it with the verb, never by
opening the file — the file interleaves closed and open entries:

```
python .aide/scripts/aide.py insights list --open
```

Triage runs *at* the queue boundary, when the finished queue is closed and the
next one is unwritten, so a `defect`, `gap` or `automation` entry routed there
to "a candidate item" has been waiting for this run. Every open one is
**considered, and either queued or explicitly passed over — never silently
dropped**: an entry you queue becomes an item like any other and is ticked with
the item number it became (below), and one you pass over stays open — still a
candidate for the next queue — and is named, with why, in the hand-off.

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

   **"Run alongside" in a roadmap means independence, not concurrency.** One
   queue is live at a time, by design — the queue boundary is the human
   checkpoint. So a roadmap saying two stages "should run alongside" or "in
   parallel" is telling you they do **not** depend on each other's results, and
   may therefore be queued in either order or merged into one batch if they fit
   the cap. It is not asking for two live queues, and you cannot produce them.
   **Queue next, sequentially, and say nothing about it** — do not spend a
   paragraph explaining why you are not honouring an instruction that was never
   given. (Item-level independence *within* one queue is a different thing and
   works already: `aide claim` offers any unblocked item, so noting that two
   items may be picked up in any order is useful and correct.)
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
     `- 📋 <deliverable>. *(Item NNN)*` bullet under the right stage. A shared
     marker is shorthand, not a shared status cell: the first status change to
     any of its items splits the bullet into one per item, so the siblings keep
     📋 rather than being completed alongside.
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

### Tick every inbox entry you queued

The verb owns that edit and commits the file when git can; `N` is the entry
number `insights list --open` printed:

```
python .aide/scripts/aide.py insights tick N --pointer "item NNN"
```

Never flip the checkbox or reword the line by hand: **the claim is immutable and
ticking the checkbox is the one in-place edit**. An entry passed over is left
exactly as it stands.

## Hand-off

Close your turn by naming the inbox entries this queue absorbed (with the item
numbers they became) and the ones you passed over with why — a pass-over is
stated where the queue is reviewed, not left for the next reader to re-derive —
then both ways to proceed, in chat and in the queue-PR body if one is opened:

- **Spec the whole queue now** — run `/aide-spec-queue NNN` in one interactive
  sitting (clarify questions answered while a human is present), then let
  execution run unattended.
- **Spec per-item during execution** — run `/aide-run-queue NNN`, or manually
  `/aide-create-item` then `/aide-execute-item` per item in fresh chats.
