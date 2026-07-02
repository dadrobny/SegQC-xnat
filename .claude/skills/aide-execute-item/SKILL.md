---
name: aide-execute-item
description: Implement a work item and update progress tracking.
---

# Execute Work Item

Implement a work item as specified in `docs/aide/items/` — Step 6 of the AIDE
loop: code, tests, configuration, and documentation as specified.

## User Input

$ARGUMENTS

## Instructions

### Item selection

If `$ARGUMENTS` is provided, treat it as an item number (item 5 →
`docs/aide/items/005-*.md`).

If empty: read `docs/aide/progress.md` and `docs/aide/items/`, select the first
item whose status is 📋 and that has a spec file, and tell the user which was
auto-selected.

### Claim the item before implementing (distributed safety)

The shared "in progress" signal is the **pushed `aide/NNN-*` branch**, not
progress.md (see `.aide/conventions.md` §2). Before writing any code, ensure the
item is claimed — the CLI checks branches and claims in one step:

```
python .aide/scripts/aide.py claim
```

or, resuming an existing claim, `git switch aide/NNN-short-name`. Verify the venv
first: `python .aide/scripts/aide.py env` (add `--bootstrap` if missing/stale).

### During implementation

1. **Follow the specification** — implement exactly what the item describes, in
   `project.source_dir` / `project.tests_dir` from `aide.toml`.
2. **Honour the Assumptions block** — if a pinned interface diverged from
   reality, stop and revise the spec rather than guessing.
3. **Document decisions** — update the item's "Decisions & Trade-offs" section as
   you make choices.
4. **Update progress via the CLI** (it flips the row, rolls up the stage, and
   commits — never hand-edit the rollup):
   ```
   python .aide/scripts/aide.py progress set NNN in-progress   # when starting
   python .aide/scripts/aide.py progress set NNN done          # when complete
   ```
5. **Scope your updates** — only your item's rows. Do NOT mark other items
   complete, even if their criteria happen to be satisfied as a side effect.

### On completion

Run the test suite via the venv (`.venv/Scripts/python -m pytest` or
`.venv/bin/python -m pytest`). Once green, merge per the configured git mode:

```
python .aide/scripts/aide.py merge NNN
```

(`auto-merge` direct-merges + re-tests + deletes the claim branch; `pr` pushes
and stops for a human PR; `local` merges offline.)

### On issues

If you hit unclear requirements or a blocker: document it in the work item and
run `/aide-feedback-loop` to adjust the process.

## Next Step

- **More items in queue?** New chat → `/aide-create-item` then
  `/aide-execute-item` (or let `/aide-run-queue` drive them).
- **Queue exhausted?** New chat → `/aide-create-queue` for the next batch.
- **All stages complete?** The project is done!
