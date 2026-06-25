---
description: Orchestrate the AIDE queue to completion — scout claims items, builder implements, test-writer writes tests, then validator gates the merge — looping until the queue is empty. Pauses only for PRs and major structural changes.
argument-hint: "[queue number, e.g. 001 — optional; defaults to the highest-numbered queue]"
---

# Run the AIDE queue (sub-agent orchestrator)

Drive the AIDE loop (`docs/aide/`) over **every remaining item** in the queue
until it is empty. **This session is only the orchestrator** — do **not** do
recon, write code, write tests, or run tests yourself in the main thread. Instead
**spawn a sub-agent for each distinct task** so every task runs in its own
isolated context. This thread keeps a small context and only dispatches and gates
approvals.

Target queue: **$ARGUMENTS** (if empty, use the highest-numbered
`docs/aide/queue/queue-*.md`).

## Task → sub-agent mapping

| Task | Sub-agent | Model | Notes |
|---|---|---|---|
| Sync, pick next 📋 item, claim branch | `scout` | Haiku | reads queue + progress, checks `aide/*` branches, creates + pushes claim branch; returns item number + branch name |
| **Implement** production code | `builder` | Sonnet (→ Opus on 3rd attempt) | one **fresh** builder per item: checkout branch, create item spec if missing, implement `src/`, record decisions, set progress 🚧, commit. **No tests, no pytest.** |
| **Write tests** for the item | `test-writer` | Sonnet | one **fresh** test-writer per item: reads spec + AC + existing test style, writes tests for all AC + adversarial cases, commits. **No production code, no pytest.** |
| **Validate** the item | `validator` | Sonnet | a **different** agent: runs pytest, checks AC test coverage, checks code scope, checks vision fit. **No new tests.** On PASS flips ✅ and direct-merges; on FAIL hands back with the responsible agent identified. |
| Approval gates, looping | *orchestrator* | — | stays in the main thread; never implements, writes tests, or validates |

**Implementation, testing, and validation are always separate agents.** No agent
signs off its own work.

Pass only the **minimum** between agents — the item number and branch name.
Each sub-agent starts cold on purpose. Spawn a **new** instance of each agent
per item (never reuse across items).

## Loop

Repeat until the `scout` reports no remaining unclaimed 📋 item:

1. **Claim → spawn `scout`** with the queue number and this brief:
   > Sync the repo, check `git branch -r` for existing `aide/*` branches, read
   > `docs/aide/queue/queue-NNN.md` and `docs/aide/progress.md`, find the first
   > unclaimed 📋 item (no blocking dependencies still 📋/🚧), then create and
   > push `aide/NNN-short-name`. Return: item number, branch name, item title.
   > If none left, say "none left".

2. **Decide (orchestrator).** If `scout` says "none left", stop and report
   completion. Otherwise take the item number and branch name forward.

3. **Write tests → spawn a fresh `test-writer`** with the item number + branch
   and this brief:
   > Write tests for AIDE item NNN on branch `aide/NNN-short-name`.
   > If `docs/aide/items/NNN-*.md` is missing, run `/speckit-aide-create-item NNN`
   > first. Read the spec for all Acceptance Criteria and Decisions. Read `tests/`
   > for style conventions. Write tests covering every AC (named clearly) plus
   > adversarial edge cases. Commit to the branch.
   > **Do NOT touch `src/` and do NOT run pytest.**
   > Return: bullet list of AC → test name mappings and adversarial scenarios.

4. **Implement → spawn a fresh `builder`** with the item number + branch and
   this brief:
   > Implement AIDE item NNN on branch `aide/NNN-short-name`. The item spec and
   > tests are already committed. Check out the branch
   > (`git switch aide/NNN-short-name`), implement production code in `src/` per
   > every Acceptance Criterion in `docs/aide/items/NNN-*.md`, record decisions,
   > set progress.md row to 🚧 (`git pull --rebase` first), commit.
   > **Do NOT write tests and do NOT run pytest.**
   > STOP and hand back if a PR, force-push, or framework change is needed.
   > Return: one-paragraph summary of what was implemented.

5. **Validate → spawn a fresh `validator`** (a *different* agent) with the item
   number + branch and this brief:
   > Independently validate AIDE item NNN on branch `aide/NNN-short-name`.
   > Run the full pytest suite. Check that every AC in `docs/aide/items/NNN-*.md`
   > has at least one test. Check builder's `src/` changes are scoped to this
   > item. Check alignment with `docs/aide/vision.md`.
   > **Do NOT write or modify tests.**
   > PASS: flip progress.md ✅, commit, direct-merge to main, re-run pytest.
   > FAIL: report which check failed and whether the builder or test-writer needs
   > to fix it. Do not merge.

6. **Build/test ↔ validate cycle (orchestrator).** Read the validator's verdict:
   - **FAIL — suite red (code bug)** → spawn a **fresh `builder`** on the same
     branch with the validator's reproduce steps; fix + re-commit; then spawn a
     **fresh `validator`** again.
   - **FAIL — missing AC test coverage** → spawn a **fresh `test-writer`** on the
     same branch; add the missing tests; then spawn a **fresh `validator`** again.
   - **FAIL — out-of-scope or vision conflict** → spawn a **fresh `builder`** to
     revert/fix; then spawn a **fresh `validator`** again.
   - Cap at **3 total validation rounds**. If still failing after round 3, stop
     and ask the user.
   - **Round 3 builder** (validator has FAILed twice): spawn with `model: opus`
     and say explicitly: "This is attempt 3 — the validator has failed twice.
     You are on Opus; treat this as a hard defect requiring deeper analysis."
   - **PASS** → the validator has merged; continue to step 1 for the next item.

7. **Checkpoint (orchestrator).** Relay a one- or two-line summary to the user
   (item, merged/failed, key facts). If any agent reported a **PR / force-push /
   structural** stop, **pause and ask the user**. Otherwise continue without
   waiting for approval.

## Granularity rule

One sub-agent per **cohesive** task. Tightly-coupled steps within a role (e.g.
implement → record decisions → commit for builder, or write AC tests → write
adversarial tests → commit for test-writer) stay inside the **same** agent
invocation — splitting them forces re-reading and loses state. The deliberate
separation across roles — implement / test / validate — is the independence that
makes the review gate meaningful.
Spawn other specialised sub-agents only when a task is genuinely separable (e.g. a
one-off read-only investigation a `scout` can answer).

## When the orchestrator must stop and ask the user

- A `builder` or `validator` hands back needing a **PR**, **force-push**, or
  history rewrite.
- An item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `vision.md`, `roadmap.md`, `constitution.md`,
  `.claude/skills|commands|agents/**`, `.specify/extensions/**`) — these need a
  reviewed PR, never a direct merge.
- A `builder` can't get tests green, the **build↔validate cycle exceeds 3 rounds**,
  or the item is blocked / contradictory. Document the blocker in the item file
  and suggest `/speckit-aide-feedback-loop`.

## On queue exhaustion

When `scout` reports no 📋 items remain: summarise items completed, branches
merged, and final test status. Permission prompts hit during the batch are
auto-logged (`docs/aide/permissions/`, via the `PreToolUse`/`PostToolUse` hook);
recommend the user run **`/aide-review-permissions`** to promote recurring, safe
prompts into the allow-list so the next batch runs with fewer interruptions. If
the roadmap has further stages, tell the user to run `/speckit-aide-create-queue`
(fresh chat) for the next batch.