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

### Asking posture

Roadmap authoring is **interactive regardless of `loop.clarify`** — that
setting governs `spec-author` on queued items, nothing else
(`.aide/conventions.md` §5). The staging derives from the written vision; where
the vision leaves a sequencing decision open — what to build first, where a
phase boundary falls, which objective a stage prioritises — ask the human
rather than assuming, and present the result as a draft for review.

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
   clear validation/acceptance criteria per stage. Acceptance bullets are
   observable checks *of the built thing*; a measured outcome the work cannot
   guarantee (an error-rate target, a benchmark result) is written as a
   `Target:` bullet instead, which progress.md tracks in its Outcome targets
   table (gating the objective, not the stage).
3. **Objective → stage coverage table is mandatory** — every vision G-code maps
   to at least one stage (progress mirrors this table).
4. **Prescriptive detail** — most work is done by AI; be specific.
5. **Realistic scope** — each stage deployable locally, roughly a week.

### Output

Save to `docs/aide/roadmap.md`. Roadmap changes are framework-level: reviewed PR,
never a direct merge.

## Hand-off

Close your turn by telling the user, in chat:

> Review `docs/aide/roadmap.md` — it is a draft until you have read it — then
> start a **fresh chat session** and run `/aide-create-progress`.
