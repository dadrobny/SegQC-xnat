---
description: Drive a single AIDE work item end-to-end — author spec (Opus), write tests, implement, validate, merge — via fresh sub-agents. The reusable unit that /aide-run-queue loops over. Pauses only for PRs and major structural changes.
argument-hint: "<item number, e.g. 014> [branch name — optional; defaults to the existing aide/NNN-* branch]"
---

# Run one AIDE work item (sub-agent orchestrator)

Take **one** already-claimed work item from `docs/aide/` through the full
workflow — **spec → tests → implementation → validation → merge** — and stop.
**This session is only the orchestrator:** do not author the spec, write code,
write tests, or run tests yourself in the main thread. **Spawn a fresh sub-agent
for each distinct task** so every task runs in its own isolated context.

Item: **$ARGUMENTS** (first token = item number NNN; optional second token =
branch name, else the existing `aide/NNN-*` branch).

> **Prerequisite:** the item must already be **claimed** — an `aide/NNN-*` branch
> created by `python .aide/scripts/aide.py claim` (or by you). This command does
> *not* claim items; the queue loop does. If no branch exists, stop and tell the
> caller to claim it first.

**Orchestration model.** This dispatch-and-gate role is light — run it on
**Sonnet** (the heavy work is in the Opus/Sonnet subagents). A slash command can't
pin the session model, so `/model sonnet` first if you're on Opus.

## Task → sub-agent mapping

| Step | Task | Sub-agent | Model | Notes |
|---|---|---|---|---|
| 0 | **Author the item spec** | `spec-author` | **Opus** | writes `docs/aide/items/NNN-*.md` (Description, atomic AC, steps, testing strategy, deps, decisions), commits. **No code, no tests.** Skip only if the spec file already exists and is complete. |
| 1 | **Write tests** for the item | `test-writer` | Sonnet | reads spec + AC + existing test style, writes tests for every AC + adversarial cases, commits. **No production code, no pytest.** |
| 2 | **Implement** production code | `builder` | Sonnet (→ Opus on 3rd attempt) | checkout branch, implement `source_dir` per every AC, record decisions, set progress in-progress (`aide progress set NNN in-progress`), commit. **No tests, no pytest.** |
| 3 | **Validate** + merge | `validator` | Sonnet | a **different** agent: runs pytest, checks AC coverage + scope + vision fit, then on PASS reconciles + merges via the CLI (`aide progress set NNN in-review`, `aide merge NNN` — `merge` writes the ✅ itself once the merge lands). **No new tests.** |

**Spec authoring, testing, implementation, and validation are always separate
agents.** No agent signs off its own work. Spawn a **new** instance of each per
item — never reuse across items. Pass only the **minimum** between agents: the
item number, the branch name, and (from spec-author) the list of AC.

**Command hygiene.** Sub-agents (and you) emit git/CLI commands in the
allow-list-friendly shape defined once in `.aide/conventions.md` §3 (no `cd`, one
command per Bash call, no `2>&1`, no command substitution in commits, venv Python
in relative form, the `aide` CLI as `python .aide/scripts/aide.py …`). A
`PreToolUse` hook (`.claude/hooks/command_hygiene_guard.py`) enforces the
mechanical rules — a violating shape is blocked and bounced back with the fix, so
prefer the right shape first time.

## Steps

1. **Spec → spawn `spec-author` (Opus).** Brief:
   > Author the work-item spec for AIDE item NNN on branch `aide/NNN-short-name`.
   > If `docs/aide/items/NNN-*.md` already exists and is complete, just return its
   > Acceptance Criteria. Otherwise read the queue line, roadmap stage, progress
   > rows, and vision; write the full spec with atomic, testable AC; commit it.
   > **Do NOT write code or tests; do NOT run pytest.**
   > Return: spec path + the list of Acceptance Criteria.

2. **Write tests → spawn a fresh `test-writer`.** Brief:
   > Write tests for AIDE item NNN on branch `aide/NNN-short-name`. The spec
   > (`docs/aide/items/NNN-*.md`) is committed. Read it for all Acceptance
   > Criteria and Decisions; read `tests/` for style. Write tests covering every
   > AC (named clearly) plus adversarial edge cases. Commit to the branch.
   > **Do NOT touch `src/` and do NOT run pytest.**
   > Return: bullet list of AC → test-name mappings and adversarial scenarios.

3. **Implement → spawn a fresh `builder`.** Brief:
   > Implement AIDE item NNN on branch `aide/NNN-short-name`. Spec and tests are
   > committed. `git switch aide/NNN-short-name`, implement `source_dir` (from
   > `aide.toml`) per every AC, record decisions in the spec, then
   > `python .aide/scripts/aide.py progress set NNN in-progress`, commit.
   > **Do NOT write tests and do NOT run pytest.**
   > STOP and hand back if a PR, force-push, or framework change is needed.
   > Return: one-paragraph summary of what was implemented.

4. **Validate → spawn a fresh `validator`** (a *different* agent). Brief:
   > Independently validate AIDE item NNN on branch `aide/NNN-short-name`.
   > Run the full pytest suite. Check every AC in `docs/aide/items/NNN-*.md` has a
   > test; check builder's `source_dir` changes are in scope; check alignment with
   > `docs/aide/vision.md` and the spec's Assumptions. **Do NOT write or modify
   > tests.**
   > PASS: reconcile + merge via the CLI —
   > `python .aide/scripts/aide.py progress set NNN in-review` then
   > `python .aide/scripts/aide.py merge NNN` (honours git.mode: direct-merge +
   > re-test + branch cleanup for auto-merge; push-and-stop for pr; local merge for
   > local). **`in-review`, never `done`** — ✅ means merged and is written by
   > `merge` itself, so under `pr` the item stays 🔍 until a human merges the PR;
   > marking it done here is what once let the exhaustion sweep target an open
   > PR's head branch. FAIL: report which check failed and whether builder or test-writer
   > must fix it. Do not merge.

5. **Build/test ↔ validate cycle (orchestrator).** Read the verdict:
   - **FAIL — suite red (code bug)** → fresh `builder` on the same branch with the
     reproduce steps; then a fresh `validator`.
   - **FAIL — missing AC coverage** → fresh `test-writer`; then a fresh `validator`.
   - **FAIL — out-of-scope / vision conflict** → fresh `builder` to revert/fix;
     then a fresh `validator`.
   - Cap at **3 validation rounds**. Still failing after round 3 → stop, document
     the blocker in the item file, ask the user.
   - **Round-3 builder** (validator FAILed twice): spawn with `model: opus` and say
     "attempt 3, validator failed twice — hard defect, deeper analysis on Opus."
   - **PASS** → the validator has reconciled progress and merged.

6. **Report.** Return a one- or two-line summary (item, merged/failed, key facts).
   If any agent reported a **PR / force-push / structural** stop, surface it so the
   caller can pause for the user.

## When to stop and ask the user

- **A human gate blocks this item** (`aide check` warns; `aide gate list` shows
  it). Report it and stop. Never run `aide gate approve` — a person decides.
- A `spec-author`, `builder`, or `validator` hands back needing a **PR**,
  **force-push**, or history rewrite.
- The item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `aide.toml`, `.aide/**`, `vision.md`, `roadmap.md`,
  `.claude/skills|commands|agents/**`) — needs a reviewed PR, never a direct merge.
- The **build↔validate cycle exceeds 3 rounds**, or the item is blocked /
  contradictory. Document the blocker and suggest `/aide-feedback-loop`.
