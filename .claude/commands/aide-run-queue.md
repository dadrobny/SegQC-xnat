---
description: Orchestrate the AIDE queue to completion by spawning a sub-agent per task — scout for recon, a fresh builder per item — looping until the queue is empty. Pauses only for PRs and major structural changes.
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
| Implement one item end-to-end | `builder` | Opus | one **fresh** builder per item: create-item (if missing) → claim → implement → test → update docs/progress → commit → direct-merge |
| Approval gates, looping | *orchestrator* | — | stays in the main thread; never implements |

Pass only the **minimum** between agents — the item number, branch name, and each
agent's short summary — never replay a big transcript. Each sub-agent starts cold
on purpose. Spawn a **new** `builder` per item (don't reuse one across items);
that's what replaces "fresh chat per item".

## Loop

Repeat until the `scout` reports no remaining unclaimed 📋 item:

1. **Recon → spawn `scout`.** Ask it to `git fetch --all --prune`, read the target
   queue + `docs/aide/progress.md`, list `aide/NNN-*` remote branches / open PRs,
   and report the **next 📋 item that is not already claimed** (number +
   short-name), or "none left". Do this read-only work in the sub-agent, not here.

2. **Decide (orchestrator).** If `scout` says the next item is claimed by someone
   else, skip it / stop and report. Otherwise take the item number forward.

3. **Implement → spawn a fresh `builder`** with just the item number and this brief:
   > Execute AIDE item NNN end-to-end. If `docs/aide/items/NNN-*.md` is missing,
   > run `/speckit-aide-create-item NNN` first. Claim by creating and pushing
   > `aide/NNN-short-name`. Run `/speckit-aide-execute-item NNN` to implement +
   > test, recording decisions and flipping this item's `progress.md` row
   > (`git pull --rebase` before that edit). When the suite is green, commit
   > (plain message, **no co-author trailer**) and direct-merge to `main`
   > (`git switch main && git pull --rebase && git merge aide/NNN-short-name &&
   > git push`), then re-run `pytest` on `main`. **STOP and report back** instead
   > of proceeding if the item needs a PR, a force-push/history rewrite, or a
   > major structural / framework change. Return a one-paragraph summary:
   > item, test result, merged-or-blocked, and any follow-ups.

4. **Checkpoint (orchestrator).** Relay the `builder`'s summary to the user in one
   or two lines. If the builder reported a **PR / force-push / structural** stop,
   **pause and ask the user** how to proceed — do not start the next item. If the
   builder reported the item merged green, continue to step 1 for the next item
   **without** waiting for approval.

## Granularity rule

One sub-agent per **cohesive** task. Keep tightly-coupled steps (implement → test
→ fix → commit) inside the *same* `builder` — splitting them across isolated
agents just forces re-reading and loses iteration state. Spawn an extra
specialised sub-agent only when a task is genuinely separable (e.g. a one-off
read-only investigation a `scout` can answer, or a focused review pass).

## When the orchestrator must stop and ask the user

- A `builder` hands back needing a **PR**, **force-push**, or history rewrite.
- An item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `vision.md`, `roadmap.md`, `constitution.md`,
  `.claude/skills|commands|agents/**`, `.specify/extensions/**`) — these need a
  reviewed PR, never a direct merge.
- A `builder` can't get tests green, or the item is blocked / contradictory.
  Document the blocker in the item file and suggest `/speckit-aide-feedback-loop`.

## On queue exhaustion

When `scout` reports no 📋 items remain: summarise items completed, branches
merged, and final test status. If the roadmap has further stages, tell the user
to run `/speckit-aide-create-queue` (fresh chat) for the next batch.