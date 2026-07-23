---
name: aide-create-roadmap
description: Generate a staged development roadmap from the vision document.
---

# Create Roadmap

Generate a staged development roadmap — Step 2 of the AIDE loop. The roadmap
breaks the vision into incremental, demonstrable, locally-deployable stages.

## Prerequisites

- `docs/aide/vision.md` must exist (created by `/aide-create-vision`)

## Instructions

Read `docs/aide/vision.md`. If `docs/aide/roadmap.md` already exists, **update it
incrementally** — do not regenerate from scratch. If it does not exist, create it
from the template **`.aide/templates/roadmap.md`**.

### Updating an existing roadmap

1. **Read `docs/aide/progress.md` first** to see which stages are completed or in
   progress.
2. **Completed and in-progress stages are immutable** — never modify their goals,
   deliverables, dependencies, or acceptance criteria.
3. **Add new stages** at the end to cover new or changed vision features.
4. **Only planned stages may be edited.**

### Requirements

1. **Staged delivery** — incremental stages that build on each other, numbered
   from 0.
2. **Each stage is demonstrable and testable** — a runnable deliverable plus
   clear validation/acceptance criteria per stage.
3. **Objective → stage coverage table is mandatory** — every vision G-code maps
   to at least one stage (progress mirrors this table).
4. **Prescriptive detail** — most work is done by AI; be specific.
5. **Realistic scope** — each stage deployable locally, roughly a week.

### Output

Save to `docs/aide/roadmap.md`. Roadmap changes are framework-level: reviewed PR,
never a direct merge.

**Write no "Next:" line into the document.** The roadmap is re-read at every
queue boundary for the rest of the project; a next-step pointer inside it is
stale after step 3 and cannot be distinguished from a current one (see
`.aide/conventions.md` §1, "No next-step pointers inside a living document").
The template's header blockquote already carries the durable orientation — what
this derives from and what mirrors it. End the file at the last stage section.

## Hand-off (say this, don't save it)

Close your turn by telling the user the typical next step — in chat, not in the
file:

> Review `docs/aide/roadmap.md`, then start a **fresh chat session** and run
> `/aide-create-progress`.
