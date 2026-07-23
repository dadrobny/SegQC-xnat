---
name: aide-create-progress
description: Create a progress tracking file from the vision and roadmap.
---

# Create Progress File

Create the progress tracker — Step 3 of the AIDE loop and **the single source of
truth for implementation status** (item specs carry no status field).

## Prerequisites

- `docs/aide/vision.md` and `docs/aide/roadmap.md` must exist.

## Instructions

Read both documents. If `docs/aide/progress.md` already exists, **update it
incrementally** — do not regenerate from scratch. If it does not exist, create it
from the template **`.aide/templates/progress.md`**.

### Format contract (machine-parsed — follow exactly)

`progress.md` is parsed and edited by `python .aide/scripts/aide.py`
(`check`, `progress set`) and the status report. The shapes in
`.aide/conventions.md` §1 are mandatory:

- Stage summary table `| Stage | Title | Objectives | Status |`;
- Objective coverage table `| Objective | Delivered by | Status |`;
- one `## Stage N — <title> — <icon>` section per stage, with **flat**
  deliverable bullets `- <icon> <text>. *(Item NNN)*` and `- [ ]` acceptance
  checkboxes;
- status icons only from the five-icon legend (📋 🚧 ✅ ⏸️ ❌).

Run `python .aide/scripts/aide.py check` after writing — it must pass.

### Updating an existing progress file

1. **Preserve all existing statuses** — never reset a non-planned status to 📋.
2. **Add new rows** for stages/deliverables that appear in the roadmap but are
   not yet tracked.
3. **Do not remove rows** — mark ⏸️ Deferred (with a note) instead.
4. **Never uncheck** an already-checked acceptance box.

### Output

Save to `docs/aide/progress.md`.

## Hand-off

Close your turn by telling the user, in chat:

> Review `docs/aide/progress.md`, then start a **fresh chat session** and run
> `/aide-create-queue` to generate the first batch of work items.
