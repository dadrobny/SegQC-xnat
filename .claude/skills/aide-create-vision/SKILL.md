---
name: aide-create-vision
description: Create a comprehensive vision document for a new project.
---

# Create Vision

Create the project vision document — Step 1 of the AIDE loop. The vision is the
foundation every subsequent step (roadmap, progress, queues, items) derives from.

## User Input

$ARGUMENTS

## Instructions

### Existing vision check

Before creating, check if `docs/aide/vision.md` already exists.
- If it exists, **warn the user** and show a brief summary of the existing vision.
- Ask for confirmation before overwriting.
- If the user wants to update rather than replace, incorporate their input as
  amendments to the existing document.

### Creating the vision

Write `docs/aide/vision.md` from the template **`.aide/templates/vision.md`** —
it defines the required structure. The mandatory core sections (do not drop):

- **Guiding principles** — the validator checks every implementation against
  these.
- **Goals & objectives** — numbered G-codes; the roadmap and progress tracker
  trace to them.
- **Out of scope** — the validator flags work that contradicts this.
- **Success criteria** — observable statements the roadmap must deliver.

Requirements:

1. **Be exhaustive** — cover the full project scope.
2. **Explain reasoning** — justify what is included and why.
3. **Document exclusions** — state what is out of scope and why.
4. **Be specific** — technology choices, constraints, and assumptions.
5. **Concise but specific** — short declarative sections, no filler; specificity
   goes into objectives and constraints, not narrative length.

### Output

Save to `docs/aide/vision.md`. Vision changes are framework-level: they land via
a reviewed PR, never a direct merge.

**Write no "Next:" line into the document.** `vision.md` outlives this step by
the whole life of the project, so a next-step pointer inside it is stale as soon
as the roadmap exists (see `.aide/conventions.md` §1, "No next-step pointers
inside a living document"). The durable orientation is already in the header
blockquote the template provides — keep that, and stop the file at Success
criteria.

## Hand-off (say this, don't save it)

Close your turn by telling the user the typical next step — in chat, not in the
file:

> Review `docs/aide/vision.md`, then start a **fresh chat session** and run
> `/aide-create-roadmap`.

A fresh session matters here: the roadmap should be derived from the written
vision, not from this conversation's memory of drafting it.
