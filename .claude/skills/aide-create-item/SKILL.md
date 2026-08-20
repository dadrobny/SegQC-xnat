---
name: aide-create-item
description: Create a detailed work item specification from a queue item.
---

# Create Work Item

Create a comprehensive work item specification — Step 5 of the AIDE loop. The
item spec contains everything needed to implement one queue item: acceptance
criteria, assumptions, implementation steps, and testing strategy.

## User Input

$ARGUMENTS

## Instructions

### Item selection

If `$ARGUMENTS` is provided, treat it as an item number: look it up in the queue
files under `docs/aide/queue/`.

If empty, automatically pick the next item:
1. Read the live queue — the lowest-numbered `docs/aide/queue/queue-NNN.md`
   that still has open (📋/🚧) items per `progress.md`.
2. Cross-reference `docs/aide/items/` and `docs/aide/progress.md`.
3. Select the first queue item with **no existing work-item file**. A ✅/🚧 mark in
   progress.md alone is NOT sufficient to skip — the file must exist. If
   progress.md shows ✅ but no file exists, flag the inconsistency first.
4. Tell the user which item was auto-selected.

### Claim check (distributed safety)

Picking an item is a **claim** (see `.aide/conventions.md` §2). The simplest path
is the CLI, which checks and claims in one step:

```
python .aide/scripts/aide.py claim --dry-run     # see what would be picked
python .aide/scripts/aide.py claim               # create + push aide/NNN-*
```

If selecting manually instead: `git fetch --all --prune`, check
`git branch -r | grep aide/` for an existing `aide/NNN-*` branch, and stop if the
item is already claimed.

### Clarify before writing (per `loop.clarify` in `aide.toml`)

- **`interactive`** — if the queued one-liner is ambiguous, ask the user **≤3
  targeted questions** before writing, and encode the answers.
- **`assume`** — do not block: pick the most defensible default per ambiguity and
  record each one in the spec's **Assumptions** block for later audit.

### Work item creation

Write `docs/aide/items/NNN-descriptive-name.md` from the template
**`.aide/templates/item.md`**. Mandatory sections (each annotated in the template
with its downstream consumer):

- **Header** — `Created` date + `status tracked in progress.md` pointer, Stage,
  Queue, Objectives, Suggested branch. **No `Status:`/`Completed:` field** —
  implementation status lives only in `progress.md` (a duplicated status has no
  owner and only drifts).
- **Description** — scope and deliverables, bounded to this one item; state what
  it is *not*.
- **Acceptance Criteria** — each atomic, observable, directly testable; split
  compound criteria.
- **Assumptions** — every clarify-mode default and every interface pinned before
  its dependency is implemented. "None." if fully specified.
- **Implementation Steps** — the intended code path in `project.source_dir`
  (from `aide.toml`).
- **Authorised paths** — the files this item may change, at the narrowest glob
  that covers the work, plus anything its tests pin without changing (**Asserts
  against**). Scope is proved by the diff against this list, so never specify a
  test that hashes another file's bytes against a hardcoded literal instead —
  see `.aide/conventions.md` §1.
- **Testing Strategy** — one test per AC plus adversarial/edge cases.
- **Dependencies** — item numbers this relies on (must be ✅/🚧).
- **Decisions & Trade-offs** — initialise with "To be updated during
  implementation."

Add project-specific sections only when the project genuinely needs them (e.g. a
services checklist for a system with external services) — not by default.

### Commit the spec immediately (do not leave it untracked)

The spec is the source of truth for every downstream step. Commit it on the
item's `aide/NNN-*` claim branch as soon as it is written (separate Bash calls):

```
git add docs/aide/items/NNN-descriptive-name.md
git commit -m "docs(NNN): work item spec for <short title>"
```

(Inside `/aide-run-item`, the `spec-author` agent performs this commit.)

## Hand-off

Close your turn by telling the user, in chat:

> Start a **fresh chat session** and run `/aide-execute-item NNN` to implement
> it.

If batch-speccing the queue via `/aide-spec-queue`, continue to the next
unspecced item instead — the batch skill owns the hand-off.
