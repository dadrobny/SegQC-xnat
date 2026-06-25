---
description: Review the permission prompts hit during recent runs and promote the safe, recurring ones into the pre-approved allow-list.
argument-hint: "[optional path to a log.jsonl — defaults to docs/aide/permissions/log.jsonl]"
---

# Review permission bottlenecks

Permission prompts stall unattended `/aide-run-queue` runs. Every prompt-eligible
tool call (Bash / Edit / Write / Web…) and its grant/deny outcome is auto-logged by
the `PreToolUse` / `PostToolUse` hook (`.claude/hooks/log_permission_event.py`) into
**`docs/aide/permissions/log.jsonl`** (per-machine, gitignored). This command turns
that log into a decision: which recurring, safe prompts to make pre-approved.

Target log: **$ARGUMENTS** (if empty, the default
`docs/aide/permissions/log.jsonl`).

## Steps

1. **Aggregate.** Run the reviewer and show the user its table:
   ```
   python .claude/scripts/review_permissions.py
   ```
   (add `--log <path>` if an argument was given). It correlates each requested call
   with its completion to infer **granted vs denied**, drops calls already covered by
   an `allow` rule, and ranks what is left. Rows are tagged:
   - `new` — a real bottleneck not yet allowed (candidate for the allow-list);
   - `ask-gated` — intentionally under `ask` (PRs, force-push, framework edits) —
     usually leave it gated;
   - `auto-allowed` — already covered (shown for context only).

2. **Recommend.** For each `new` row, judge it on the **actual command shown**, not
   just the suggested rule:
   - **Promote to `allow`** only safe / read-only / routine commands with no
     destructive or outward-facing side effects (e.g. extra read-only `gh`/`git`
     queries, formatters, linters, build/test invocations).
   - **Keep under `ask`** anything that mutates remote state, rewrites history,
     deletes, or edits framework/process files.
   - **Leave** one-offs that won't recur.
   Present a short list: rule → recommend allow / ask / leave, with a one-line reason.

3. **Apply (on user confirmation).** Edit `.claude/settings.json`, adding the agreed
   rules to `permissions.allow` (or `ask`). This edit **prompts** per the existing
   policy — that is intended. Keep rules tightly scoped (prefer `Bash(gh pr view:*)`
   over `Bash(gh:*)`).

4. **Land via PR.** `.claude/settings.json` is a framework/process file: per
   `CLAUDE.md` the change must go on a branch and merge **only after PR review** — do
   **not** direct-merge. State this to the user; stop at the PR (gh pr create is
   `ask`-gated).

5. **Rotate the log** so the same prompts aren't re-reviewed next time: append the
   reviewed lines to `docs/aide/permissions/log.reviewed.jsonl` and truncate
   `docs/aide/permissions/log.jsonl`. Both stay gitignored.

## Notes

- The hook never blocks or alters a tool — it only records. If the log is missing or
  empty, there is nothing to review (no run has hit a prompt since the last rotation).
- Re-run this anytime, and from `/speckit-aide-feedback-loop`, which calls it as part
  of its process review.
