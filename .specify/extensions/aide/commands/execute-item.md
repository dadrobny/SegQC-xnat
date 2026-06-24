---
description: "Implement a work item and update progress tracking."
---

# Execute Work Item

Implement a work item as specified in the docs/aide/items/ directory.

## Purpose

This is Step 6 of the AI-Driven Engineering workflow. This step takes a detailed work item specification and implements it — writing code, tests, configuration, and documentation as specified.

## User Input

$ARGUMENTS

## Instructions

### Item Selection

If `$ARGUMENTS` is provided, treat it as an item number. Find the matching file in `docs/aide/items/` (e.g., item 5 maps to `docs/aide/items/005-*.md`).

If `$ARGUMENTS` is empty, automatically pick the next item:
1. Read `docs/aide/progress.md` and scan `docs/aide/items/` for existing work item files
2. Select the first work item whose status in `docs/aide/progress.md` is 📋 (Planned) — i.e., it has a spec but hasn't been started yet
3. Tell the user which item was auto-selected before proceeding

### Claim the Item Before Implementing (distributed safety)

Because `progress.md`'s `🚧` mark lives on your branch and is invisible to
collaborators on `main`, the shared "in progress" signal is the **pushed
`aide/NNN-*` branch** (see *Claiming a work item* in `CLAUDE.md`). Before writing
any code:

1. `git fetch --all --prune`, then check no one else has claimed this item:
   `git branch -r | grep aide/` and (with a GitHub remote) `gh pr list --state open`.
   If another collaborator's branch/PR already exists for this item number, stop
   and coordinate rather than duplicating work.
2. Ensure you are on `aide/NNN-short-name` and **push it now** so the claim is
   visible: `git switch -c aide/NNN-short-name` (if not already created) then
   `git push -u origin aide/NNN-short-name` (a WIP/empty commit is fine). A draft
   PR at this point is encouraged.
3. `git pull --rebase` before the first `progress.md` edit so status lines stack
   cleanly.

### During Implementation

1. **Follow the specification** — implement exactly what the work item describes
2. **Document decisions** — as you make implementation choices, UPDATE the work item's "Decisions & Trade-offs" section with:
   - What was decided
   - Why this approach over alternatives
   - Any trade-offs or future considerations
3. **Update progress** — update `docs/aide/progress.md` status:
   - 📋 → 🚧 when starting implementation
   - 🚧 → ✅ when implementation is complete
4. **Scope your updates** — only update progress rows that correspond to YOUR item number. Do NOT mark other items as complete, even if their criteria happen to be satisfied as a side effect of your work. Each item must go through its own create-item → execute-item cycle.

### On Smooth Completion

- No feedback loop needed
- Ensure work item decisions are documented
- Mark progress as complete

### On Issues

If you encounter problems (unclear requirements, blocked, need help):
- Document the issue in the work item
- Tell the user to run `/speckit-aide-feedback-loop` to adjust the process

## Next Step

- **More items in queue?** Start a **new chat session** and run `/speckit-aide-create-item` for the next queue item, then `/speckit-aide-execute-item` to implement it.
- **Queue exhausted?** Start a **new chat session** and run `/speckit-aide-create-queue` to generate the next batch.
- **All stages complete?** The project is done!
