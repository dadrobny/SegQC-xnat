---
description: Orchestrate the AIDE queue to completion by spawning a sub-agent per task — scout for recon, builder for implementation, then a separate validator that adversarially gates the merge — looping until the queue is empty. Pauses only for PRs and major structural changes.
argument-hint: "[queue number, e.g. 001 — optional; defaults to the active queue]"
---

# Run the AIDE queue (sub-agent orchestrator)

Drive the AIDE loop (`docs/aide/`) over **every remaining item** in the queue
until it is empty. **This session is only the orchestrator** — do **not** do
recon, write code, or run tests yourself in the main thread. Instead **spawn a
sub-agent for each distinct task** (via the Agent tool) so every task runs in its
own isolated context — the same isolation as the AIDE "fresh chat per item" rule,
while this thread keeps a small context and just dispatches and gates approvals.

Target queue: **$ARGUMENTS** (if empty, use the highest-numbered
`docs/aide/queue/queue-*.md`).

## Task → sub-agent mapping

| Task | Sub-agent | Model | Notes |
|---|---|---|---|
| Sync, pick next 📋 item, check claims | `scout` | Sonnet | read-only; returns the item number + short-name + claim status |
| **Implement** one item | `builder` | Opus | one **fresh** builder per item: create-item (if missing) → claim → implement → test → set progress 🚧 → commit on the branch. **Does NOT merge.** |
| **Validate** that item | `validator` | Opus | a **different** agent: tests pass + matches spec + serves the vision + adversarial break-attempts + adds tests. On PASS flips progress ✅ and direct-merges; on FAIL hands back. |
| Approval gates, looping | *orchestrator* | — | stays in the main thread; never implements or validates |

**Implementation and validation are always separate agents.** The agent that
wrote the code must never be the one that signs it off — spawn a fresh
`validator` (not the same `builder` instance) so the review is genuinely
independent.

Pass only the **minimum** between agents — the item number, branch name, and each
agent's short summary — never replay a big transcript. Each sub-agent starts cold
on purpose. Spawn a **new** `builder` and a **new** `validator` per item (don't
reuse across items); that's what replaces "fresh chat per item".

## Loop

Repeat until the `scout` reports no remaining unclaimed 📋 item:

1. **Recon → spawn `scout`.** Ask it to `git fetch --all --prune`, read the target
   queue + `docs/aide/progress.md`, list `aide/NNN-*` remote branches / open PRs,
   and report the **next 📋 item that is not already claimed** (number +
   short-name), or "none left". Do this read-only work in the sub-agent, not here.

2. **Decide (orchestrator).** If `scout` says the next item is claimed by someone
   else, skip it / stop and report. Otherwise take the item number forward.

3. **Implement → spawn a fresh `builder`** with just the item number and this brief:
   > Implement AIDE item NNN. If `docs/aide/items/NNN-*.md` is missing, run
   > `/speckit-aide-create-item NNN` first. Claim by creating and pushing
   > `aide/NNN-short-name`. Run `/speckit-aide-execute-item NNN` to implement +
   > test, recording decisions and setting this item's `progress.md` row to 🚧
   > (`git pull --rebase` before that edit). When the suite is green, commit on
   > the branch (plain message, **no co-author trailer**). **Do NOT merge and do
   > NOT flip the row to ✅ — a separate validator does that.** STOP and report
   > back if the item needs a PR, force-push, or a major structural / framework
   > change. Return a one-paragraph summary: item, branch, test result, and any
   > follow-ups.

4. **Validate → spawn a fresh `validator`** (a *different* agent from the builder)
   with the item number + branch and this brief:
   > Independently validate AIDE item NNN on branch `aide/NNN-short-name`, where a
   > builder has implemented and committed (unmerged). Confirm `python -m pytest`
   > passes; check the code against every Acceptance Criterion + the Description in
   > `docs/aide/items/NNN-*.md`; confirm it serves `docs/aide/vision.md`. Then
   > **adversarially try to break it** with hostile/edge-case inputs and **add
   > focused tests** for any gaps (inline `tmp_path`, project style). Verdict:
   > **PASS** only if everything holds incl. your new tests — then commit the
   > tests, flip the `progress.md` row to ✅ (`git pull --rebase` first), and
   > direct-merge to `main`, re-running `pytest` on `main`. **FAIL** if the suite
   > is red, a criterion is unmet, it fights the vision, or an adversarial test
   > exposes a defect — leave the tests committed on the branch, do NOT merge, and
   > hand back exact reproduce steps. STOP for PR / force-push / structural needs.

5. **Build ↔ validate cycle (orchestrator).** Read the `validator`'s verdict:
   - **FAIL with a fixable defect** → spawn a **fresh `builder`** on the same
     branch with the validator's reproduce steps; have it fix + re-commit; then
     spawn a **fresh `validator`** again. Cap at **3 build↔validate rounds**; if
     still failing, stop and ask the user.
   - **PASS** → the validator has merged; continue.

6. **Checkpoint (orchestrator).** Relay the builder + validator summaries to the
   user in one or two lines (item, what was attacked, tests added, merged). If
   either agent reported a **PR / force-push / structural** stop, **pause and ask
   the user**. Otherwise continue to step 1 for the next item **without** waiting
   for approval.

## Granularity rule

One sub-agent per **cohesive** task. Keep tightly-coupled steps (implement → test
→ fix → commit) inside the *same* `builder` — splitting *those* across isolated
agents just forces re-reading and loses iteration state. The deliberate exception
is **validation**, which is *always* a separate `validator` agent: independence is
the whole point of a review gate, so the reviewer must not be the implementer.
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