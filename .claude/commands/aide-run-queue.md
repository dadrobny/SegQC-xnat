---
description: Iterate one AIDE queue to completion — a scout claims each item, then /aide-run-item drives it (spec → tests → build → validate → merge) — looping until that queue is empty, then stops. Does NOT create the next queue. Pauses only for PRs and major structural changes.
argument-hint: "[queue number, e.g. 001 — optional; defaults to the highest-numbered queue]"
---

# Run one AIDE queue (iterator over /aide-run-item)

Drive the AIDE loop (`docs/aide/`) over **every remaining item in a single
queue**, then **stop**. This command is **queue-scoped**: it does *not* generate
the next queue — that is `/aide-run-roadmap`'s job (the loop *over* queues). This
session is only the orchestrator — do **not** author specs, write code, write
tests, or run tests yourself in the main thread. You **delegate each item to
`/aide-run-item`** and only handle claiming and approval gates between items.

Target queue: **$ARGUMENTS** (if empty, use the highest-numbered
`docs/aide/queue/queue-*.md`).

**Orchestration model.** This dispatch-and-gate role is light — run it on
**Sonnet** (the heavy work is in the Opus/Sonnet subagents). A slash command can't
pin the session model, so `/model sonnet` first if you're on Opus.

## Division of labour

| Concern | Owner | Notes |
|---|---|---|
| Claim the next 📋 item | `scout` (Haiku) | syncs, checks `aide/*` branches, picks the first unclaimed unblocked 📋 item, pushes `aide/NNN-*`; returns item number + branch + title |
| Run one item end-to-end | **`/aide-run-item NNN`** | spec-author (Opus) → test-writer → builder → validator+merge, incl. the ≤3-round validate cycle. See that command for the per-item detail. |
| Approval gates, looping | *orchestrator* | stays in the main thread |
| Generating the **next** queue | **not here** | only `/aide-run-roadmap` (or a manual `/speckit-aide-create-queue`) does that |

The per-item mechanics (which agent does what, the build↔validate cycle, the
Opus escalation on round 3) live in **`/aide-run-item`** — this command does not
restate them. Keeping a single source of truth for the item loop is the point of
the split.

**Command hygiene** applies to any git command you issue from this thread too: no
`cd` prefix, one command per Bash call, no `2>&1`, no command substitution in
commit messages, recon via the Bash tool with `grep`. See `CLAUDE.md` →
*Command hygiene*.

## Pre-loop: resume in-flight branches

Before claiming new items, resume any interrupted ones. The scout skips item
numbers that already have an `aide/*` branch, so an interrupted item would be
stranded otherwise.

**Orchestrator steps (run these yourself, not via a sub-agent):**

1. `git branch | grep aide/` — list local `aide/*` branches.
2. If none, skip to the loop.
3. For each `aide/NNN-*` branch, read `docs/aide/progress.md`: if the item is
   already ✅/❌, skip it; if 🚧 or 📋, it is unfinished.
4. For each unfinished item (item-number order), hand it to **`/aide-run-item NNN
   aide/NNN-short-name`**. `/aide-run-item` is itself resumable — its spec-author
   step no-ops if the spec exists, and the validate/build cycle picks up from
   whatever is already committed — so just run it.
5. Process each resumed item to PASS+merge (or a user-stop) before claiming new
   work below.

## Loop

Repeat until the `scout` reports no remaining unclaimed 📋 item **in this queue**:

1. **Claim → spawn `scout`** with the queue number:
   > Sync the repo, check `git branch -r` for existing `aide/*` branches, read
   > `docs/aide/queue/queue-NNN.md` and `docs/aide/progress.md`, find the first
   > unclaimed 📋 item with no blocking dependency still 📋/🚧, then create and
   > push `aide/NNN-short-name`. Return: item number, branch name, item title.
   > If none left in this queue, say "none left".

2. **Decide (orchestrator).**
   - **Item returned** → go to step 3.
   - **"none left"** → the queue is exhausted; go to **On queue exhaustion**.

3. **Run the item → invoke `/aide-run-item NNN aide/NNN-short-name`.** This drives
   the full per-item workflow and merges on PASS. Wait for it to return.

4. **Checkpoint (orchestrator).** Relay a one- or two-line summary (item,
   merged/failed, key facts). If `/aide-run-item` reported a **PR / force-push /
   structural** stop, **pause and ask the user**. Otherwise continue to step 1.

## On queue exhaustion

When `scout` reports no 📋 items remain in this queue, **stop** and report:
items completed, branches merged, and final test status. Then point the user at
the next move (do **not** generate the next queue yourself):

- **Driving the whole roadmap?** Run **`/aide-run-roadmap`** — it generates and
  gates the next queue (human-reviewed PR by default, or `--continuous` to keep
  going), then re-enters this command for that queue.
- **Working a single batch manually?** Start a fresh chat and run
  `/speckit-aide-create-queue` for the next batch.

Permission prompts hit during the batch are auto-logged (`docs/aide/permissions/`);
suggest the user run **`/aide-review-permissions`** to promote recurring safe
prompts (it also **rotates** the log).

## When the orchestrator must stop and ask the user

- `/aide-run-item` hands back needing a **PR**, **force-push**, or history rewrite.
- An item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `vision.md`, `roadmap.md`, `constitution.md`,
  `.claude/skills|commands|agents/**`, `.specify/extensions/**`) — needs a
  reviewed PR, never a direct merge.
- The build↔validate cycle for an item exceeds 3 rounds, or an item is blocked /
  contradictory — document the blocker and suggest `/speckit-aide-feedback-loop`.
