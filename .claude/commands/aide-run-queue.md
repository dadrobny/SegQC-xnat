---
description: Iterate one AIDE queue to completion — `aide claim` claims each item, then /aide-run-item drives it (spec → tests → build → validate → merge) — looping until that queue is empty, then stops. Does NOT create the next queue. Pauses only for PRs and major structural changes.
argument-hint: "[queue number, e.g. 001 — optional; defaults to the lowest-numbered queue with open items]"
---

# Run one AIDE queue (iterator over /aide-run-item)

Drive the AIDE loop (`docs/aide/`) over **every remaining item in a single
queue**, then **stop**. This command is **queue-scoped**: it does *not* generate
the next queue — that is `/aide-run-roadmap`'s job (the loop *over* queues). This
session is only the orchestrator — do **not** author specs, write code, write
tests, or run tests yourself in the main thread. You **delegate each item to
`/aide-run-item`** and only handle claiming (via the `aide claim` CLI) and
approval gates between items.

Arguments: **$ARGUMENTS** — a queue number (if empty, the live queue: the
lowest-numbered `docs/aide/queue/queue-*.md` with open items).

**Orchestration model.** This dispatch-and-gate role is light — run it on
**Sonnet** (the heavy work is in the Opus/Sonnet subagents). A slash command can't
pin the session model, so `/model sonnet` first if you're on Opus.

**One session, one layer.** Per item, load `/aide-run-item NNN` **inline as a
skill in *this* session** — it is a prompt expansion, not a subprocess. The only
parallel/isolated contexts are the `Task` subagents (`spec-author`, `test-writer`,
`builder`, `validator`) that do the leaf work; claiming is a deterministic CLI
call, not a subagent. There is **no headless `claude -p` nesting** (an earlier
`--continuous` design tried it and was removed — see `/aide-run-roadmap` →
*Historical note*). The loop runs **in-place in the primary checkout**; for
parallel human work, isolate in a worktree per `/aide-run-roadmap` → *Working in
parallel*.

## Division of labour

| Concern | Owner | Notes |
|---|---|---|
| Claim the next 📋 item | `aide claim` (CLI) | `python .aide/scripts/aide.py claim [--queue NNN]` — syncs, checks `aide/*` branches, picks the first unclaimed unblocked 📋 item, creates + pushes `aide/NNN-*`; prints item number + branch + title. Deterministic, no subagent. |
| Run one item end-to-end | **`/aide-run-item NNN`** | spec-author (Opus) → test-writer → builder → validator+merge, incl. the ≤3-round validate cycle. See that command for the per-item detail. |
| Approval gates, looping | *orchestrator* | stays in the main thread |
| Generating the **next** queue | **not here** | only `/aide-run-roadmap` (or a manual `/aide-create-queue`) does that |

The per-item mechanics (which agent does what, the build↔validate cycle, the
Opus escalation on round 3) live in **`/aide-run-item`** — this command does not
restate them. Keeping a single source of truth for the item loop is the point of
the split.

**Command hygiene** applies to any git command you issue from this thread too. See
`.aide/conventions.md` §3 (no `cd`, one command per Bash call, no `2>&1`, no
command substitution in commits, recon via the Bash tool with `grep`). A
`PreToolUse` hook (`.claude/hooks/command_hygiene_guard.py`) enforces the
mechanical rules — a violating shape is blocked and bounced back with the fix.

## Pre-loop: resume in-flight branches

Before claiming new items, resume any interrupted ones. `aide claim` skips item
numbers that already have an `aide/*` branch, so an interrupted item would be
stranded otherwise.

**Orchestrator steps (run these yourself, not via a sub-agent):**

0. `python .aide/scripts/aide.py sync` — the deterministic preflight (fetch,
   clean-tree check). Do not improvise `git fetch`/`git status` instead.
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

Repeat until `aide claim` reports no remaining unclaimed 📋 item **in this queue**:

1. **Claim → run the CLI** (orchestrator, not a subagent):
   ```
   python .aide/scripts/aide.py claim --queue NNN
   ```
   It syncs, checks `aide/*` branches, picks the first unclaimed 📋 item with no
   blocking dependency still 📋/🚧, creates + pushes `aide/NNN-short-name`, and
   prints the item number, branch name, and title. Prints `none left` when the
   queue is exhausted.

2. **Decide (orchestrator).**
   - **Item claimed** → go to step 3.
   - **"none left"** → the queue is exhausted; go to **On queue exhaustion**.

3. **Run the item** — load `/aide-run-item NNN aide/NNN-short-name` inline as a
   skill in this session. It drives the full per-item workflow (spec → tests →
   build → validate) and merges on PASS; **wait for it to finish** before looping.

4. **Checkpoint (orchestrator).** Relay a one- or two-line summary (item,
   merged/failed, key facts). If the item reported a **PR / force-push /
   structural** stop, **pause and ask the user**. Otherwise continue to step 1.

## On queue exhaustion

When `aide claim` reports no 📋 items remain in this queue, first sweep up any
leftover claim branches (merged work leaves none in `auto-merge` mode, but `pr`
merges and abandoned claims do): `python .aide/scripts/aide.py gc` to preview,
then re-run with `--yes` if the list is right. Then **stop** and report: items
completed, branches merged/cleaned, and final test status. Point the user at
the next move (do **not** generate the next queue yourself):

- **Driving the whole roadmap?** Run **`/aide-run-roadmap`** — it generates the
  next queue behind a human-reviewed PR, then re-enters this command for that
  queue once you merge it.
- **Working a single batch manually?** Start a fresh chat and run
  `/aide-create-queue` for the next batch.

Permission prompts hit during the batch are auto-logged (`docs/aide/permissions/`);
suggest the user run **`/aide-review-permissions`** to promote recurring safe
prompts (it also **rotates** the log).

## When the orchestrator must stop and ask the user

- `/aide-run-item` hands back needing a **PR**, **force-push**, or history rewrite.
- An item needs a **major structural change** or an edit to a framework/process
  file (`CLAUDE.md`, `aide.toml`, `.aide/**`, `vision.md`, `roadmap.md`,
  `.claude/skills|commands|agents/**`) — needs a reviewed PR, never a direct merge.
- The build↔validate cycle for an item exceeds 3 rounds, or an item is blocked /
  contradictory — document the blocker and suggest `/aide-feedback-loop`.
