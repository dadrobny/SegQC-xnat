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
> pushed by the `scout` (or by you). This command does *not* claim items; the
> `scout` / queue loop does. If no branch exists, stop and tell the caller to
> claim it first.

**Orchestration model.** This dispatch-and-gate role is light — run it on
**Sonnet** (the heavy work is in the Opus/Sonnet subagents). A slash command can't
pin the session model, so `/model sonnet` first if you're on Opus.

## Task → sub-agent mapping

| Step | Task | Sub-agent | Model | Notes |
|---|---|---|---|---|
| 0 | **Author the item spec** | `spec-author` | **Opus** | writes `docs/aide/items/NNN-*.md` (Description, atomic AC, steps, testing strategy, deps, decisions), commits. **No code, no tests.** Skip only if the spec file already exists and is complete. |
| 1 | **Write tests** for the item | `test-writer` | Sonnet | reads spec + AC + existing test style, writes tests for every AC + adversarial cases, commits. **No production code, no pytest.** |
| 2 | **Implement** production code | `builder` | Sonnet (→ Opus on 3rd attempt) | checkout branch, implement `src/` per every AC, record decisions, set progress 🚧, commit. **No tests, no pytest.** |
| 3 | **Validate** + merge | `validator` | Sonnet | a **different** agent: runs pytest, checks AC coverage + scope + vision fit, **reconciles progress.md** (item row, stage acceptance boxes, summary rollup), then on PASS flips ✅ and direct-merges. **No new tests.** |

**Spec authoring, testing, implementation, and validation are always separate
agents.** No agent signs off its own work. Spawn a **new** instance of each per
item — never reuse across items. Pass only the **minimum** between agents: the
item number, the branch name, and (from spec-author) the list of AC.

**Command hygiene.** Sub-agents must emit git/python commands in an
allow-list-friendly shape so the run doesn't stall on prompts: no `cd` prefix,
one command per Bash call (no `&&`/`;` chaining), no `2>&1`, no command
substitution in commit messages, Python/pytest via the relative
`.venv/Scripts/python` (or `.venv/bin/python`) form, and recon via the Bash tool
with `grep` rather than PowerShell `Select-String`. Spelled out in each agent
spec and `CLAUDE.md` → *Command hygiene*.

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
   > committed. `git switch aide/NNN-short-name`, implement `src/` per every AC,
   > record decisions in the spec, set the item's progress.md row to 🚧
   > (`git pull --rebase` first), commit.
   > **Do NOT write tests and do NOT run pytest.**
   > STOP and hand back if a PR, force-push, or framework change is needed.
   > Return: one-paragraph summary of what was implemented.

4. **Validate → spawn a fresh `validator`** (a *different* agent). Brief:
   > Independently validate AIDE item NNN on branch `aide/NNN-short-name`.
   > Run the full pytest suite. Check every AC in `docs/aide/items/NNN-*.md` has a
   > test; check builder's `src/` changes are in scope; check alignment with
   > `docs/aide/vision.md`. **Reconcile `docs/aide/progress.md`**: tick this
   > item's deliverable and acceptance checkboxes, and if every deliverable in the
   > stage is now done, roll the stage status (header + summary table + objective
   > coverage) up to ✅. **Do NOT write or modify tests.**
   > PASS: flip progress.md ✅ + reconcile as above, commit, direct-merge to main,
   > re-run pytest, then delete the merged `aide/NNN-*` claim branch (local +
   > remote, safe `-d`). FAIL: report which check failed and whether builder or
   > test-writer must fix it. Do not merge.

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

- A `spec-author`, `builder`, or `validator` hands back needing a **PR**,
  **force-push**, or history rewrite.
- The item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `vision.md`, `roadmap.md`, `constitution.md`,
  `.claude/skills|commands|agents/**`, `.specify/extensions/**`) — needs a
  reviewed PR, never a direct merge.
- The **build↔validate cycle exceeds 3 rounds**, or the item is blocked /
  contradictory. Document the blocker and suggest `/speckit-aide-feedback-loop`.
