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

3. **Apply (on user confirmation) — to the right file.** Where the agreed rules go
   depends on whether this project has adopted the settings overlay. The reviewer
   prints the answer at the end of its output; it is:
   - **`.claude/settings.overlay.json` exists** → add the rules to its
     `permissions.allow.add` list. `settings.json` is a **generated** artifact here
     (`install.py --update` regenerates it as framework-base + overlay), so a rule
     written into `settings.json` is silently discarded on the next update.
   - **no overlay** → add them to `permissions.allow` in `.claude/settings.json`
     directly, as before.

   Either edit **prompts** per the existing policy — that is intended. Keep rules
   tightly scoped (prefer `Bash(gh pr view:*)` over `Bash(gh:*)`).

4. **Land via PR.** The settings file you edited — overlay or `settings.json` — is a
   framework/process file: per `CLAUDE.md` the change must go on a branch and merge
   **only after PR review** — do **not** direct-merge. State this to the user; stop
   at the PR (gh pr create is `ask`-gated).

5. **Rotate the log** so the same prompts aren't re-reviewed next time and the
   raw log doesn't grow without bound. Run:
   ```
   python .claude/scripts/review_permissions.py --rotate
   ```
   This archives every current record into `docs/aide/permissions/log.reviewed.jsonl`
   and truncates `docs/aide/permissions/log.jsonl` (both stay gitignored). Do this
   **after** you've captured the allow-rule decisions in step 2–4 — once rotated,
   those records are no longer in the live review. Always rotate at the end of a
   review; an un-rotated log re-surfaces the same prompts and balloons over time
   (it has reached ~1 MB / thousands of records when left unrotated).

## Notes

- The hook never blocks or alters a tool — it only records.
- **An empty log has *two* causes — check trust first.** Either no run has hit a
  prompt since the last rotation, **or the logging hook never ran because this
  project folder isn't trusted.** Crucially, an untrusted folder *also* silently
  disables the `.claude/settings.json` allow-list you're trying to tune — both the
  hook and the allow-list are gated by the same trust flag. So the symptom
  "permission prompts keep firing **and** the review log is empty" almost always
  means **untrusted folder**, not a missing rule. Verify before chasing rules: in
  `~/.claude.json`, find this repo's path under `projects` and confirm
  `"hasTrustDialogAccepted": true`. The key is an **exact, case-sensitive** path
  string — mind `c:` vs `C:` and any OneDrive/symlinked spelling (a mismatched key
  is a *different*, untrusted project). Fix by re-opening the folder to accept the
  trust prompt, or setting that flag. (The reviewer script prints this reminder
  whenever the log is empty.)
- Re-run this anytime, and from `/aide-feedback-loop`, which calls it as part
  of its process review.
