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

**Write no "Next:" line into the document.** `progress.md` is edited on every
merged item and is the most-read file in the loop — a pointer saying "run
`/aide-create-queue` to generate the first batch" would still be sitting there
at queue 7 (see `.aide/conventions.md` §1, "No next-step pointers inside a
living document"). The template's header blockquote carries the durable
orientation instead. End the file after the last stage section.

## Hand-off (say this, don't save it)

Close your turn by telling the user the typical next step — in chat, not in the
file:

> Review `docs/aide/progress.md`, then start a **fresh chat session** and run
> `/aide-create-queue` to generate the first batch of work items.
