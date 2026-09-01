---
description: Review which instruction files actually reached recent sessions — a rule that never loaded is silently inert — and rotate the log.
argument-hint: "[optional path to a log.jsonl — defaults to docs/aide/instructions/log.jsonl]"
---

# Review instruction delivery

A `.claude/rules/` file that never loads is invisible from inside a session: it
is still there, still correct, and reaches nobody. Every instruction file the
runtime loads is auto-logged with its reason by the `InstructionsLoaded` hook
(`.claude/hooks/log_instructions_loaded.py`) into
**`docs/aide/instructions/log.jsonl`** (per-machine, gitignored). This command
turns that log into an answer: did each rule reach the sessions it should have?

Target log: **$ARGUMENTS** (if empty, the default
`docs/aide/instructions/log.jsonl`).

## Steps

1. **Report.** Run the reviewer and show the user its output:
   ```
   python .claude/scripts/review_instructions.py $ARGUMENTS
   ```
   (the argument is the log path; empty means the default). Three sections, in the
   order they cost to get wrong:
   - **Rules that never loaded** — every `.claude/rules/*.md` absent from the log;
   - **Loads per file, by reason** — `session_start` is a cost paid in every
     context, `path_glob_match` only where a scoped rule's globs matched a file
     a session read;
   - **Per-session totals** — an over-broad glob shows up as an outlier.

2. **Judge each silent rule on what it is.**
   - **A framework rule** (`aide-command-hygiene.md`) is unscoped and loads in
     every context, so silent over a non-empty log means the hook or the trust
     flag, not the rule: check the *Notes* below before anything else, then
     that `.claude/rules/aide-command-hygiene.md` is actually on disk —
     `install.py --check` will not tell you, it compares versions and retired
     files, not whether a shipped file went missing.
   - **A project's own `paths:`-scoped rule** is silent whenever no logged
     session read a matching file — the correct outcome over sessions that
     touched nothing relevant. Confirm its globs still match the files it is
     for before calling it broken; a glob that stopped matching after a rename
     is the failure this instrument exists to catch.
   - **A rule the framework has retired** is removed from `.claude/rules/` by
     `install.py --update` and is not a fault; if it is still there, the
     install is behind (`install.py --check`).

3. **Say what the report cannot say.** It measures **delivery, not reading**:
   a `Read` is never logged as a load, so a role that opened
   `.aide/conventions.md` by hand leaves no trace here. Nor does it see a
   **preloaded section skill**
   (`.claude/skills/aide-*` named in an agent's `skills:` frontmatter) — a
   preload is not an instruction file to the runtime, and needs no measuring:
   it is unconditional per spawn, so its reach is the set of agent specs that
   name it and its cost an exact structural sum, asserted in the framework
   repo's `tests/test_structural_budget.py`. Do not report a preloaded skill
   as "never loaded".

4. **`--strict` is a human check, not a gate.** `--strict` exits 1 when any
   shipped rule never loaded — an empty or missing log included, since nothing
   loaded there either. It is only meaningful over a log known to cover
   work the rule should have matched — the log has no notion of which sessions
   *should* have armed a rule — so never wire it into CI; over an arbitrary log
   a scoped rule false-alarms by construction. Run it here, by hand, when the
   log covers a queue whose work the rule is for.

5. **Rotate the log** once the findings are captured, so the next review reads
   only the sessions since and "never loaded" stops averaging over sessions
   from before a glob was last changed:
   ```
   python .claude/scripts/review_instructions.py $ARGUMENTS --rotate
   ```
   This appends every current record to `log.reviewed.jsonl` beside the log
   (`docs/aide/instructions/` by default; both stay gitignored) and truncates the
   log. The same argument as step 1, always: rotating a different log than the
   one reviewed truncates records nobody read. Always rotate at the end of a
   review.

## Notes

- The hook never blocks or alters anything — it only records.
- **An empty log has *three* causes — check trust first.** No session has run
  since the hook was installed; the log was just rotated; **or the hook never
  ran because this project folder isn't trusted**, which also silently disables
  the `.claude/settings.json` allow-list. Verify in `~/.claude.json` that this
  repo's path under `projects` has `"hasTrustDialogAccepted": true` — an exact,
  case-sensitive path string. The reviewer prints this reminder whenever the log
  is empty.
- Re-run this anytime, and from `/aide-feedback-loop`, which calls it at the
  queue boundary alongside `/aide-review-permissions` — "which rules reached
  which agents this queue" is a queue-boundary question.
