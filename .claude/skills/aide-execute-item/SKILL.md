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
progress.md (see `.aide/conventions.md` §2). Before writing any code, run the
deterministic preflight — do **not** improvise `git fetch`/`git status`/`git
switch` yourself:

```
python .aide/scripts/aide.py sync            # fetch + clean-tree check
python .aide/scripts/aide.py claim           # claim the next unclaimed item
```

or, resuming an existing claim, `python .aide/scripts/aide.py sync --item NNN`
(it lands on the claim branch and pulls it up to date). Verify the venv first:
`python .aide/scripts/aide.py env` (add `--bootstrap` if missing/stale).

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
6. **Capture out-of-scope insights** — anything true but beyond this item (a
   doc gap, a latent defect, a missing capability, a recurring manual step
   deterministic code could replace, an AIDE-framework issue) gets ONE
   appended line in `docs/aide/insights.md` (create from
   `.aide/templates/insights.md` verbatim if missing), then carry on:

       - [ ] <knowledge|defect|gap|automation|framework> — <one line> *(item NNN, YYYY-MM-DD)*

   The feedback loop triages the inbox at the queue boundary; never act on an
   insight out of scope here.

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

## Hand-off (say this, don't save it)

Close your turn by telling the user where the loop stands — in chat. Nothing
here goes into `progress.md` or the item spec; the documents record state, not
instructions.

- **More items in queue?** New chat → `/aide-create-item` then
  `/aide-execute-item` (or let `/aide-run-queue` drive them).
- **Queue exhausted?** New chat → `/aide-create-queue` for the next batch.
- **All stages complete?** The project is done!
