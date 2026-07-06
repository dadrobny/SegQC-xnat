---
description: Drive the AIDE roadmap across MULTIPLE queues — generate a queue, run it to completion (via /aide-run-queue), then generate the next — until the roadmap is exhausted. Each new queue lands via a human-reviewed PR (the batch checkpoint).
---

# Run the AIDE roadmap (loop over queues)

The widest AIDE loop: iterate **over queues** across the whole roadmap. Where
`/aide-run-queue` runs the items *within one queue*, this command **generates
each queue and chains them** — create queue → run it → create the next → … —
until `docs/aide/roadmap.md` has no further stage to queue.

The **queue is the human checkpoint.** Items inside an approved queue flow freely
(direct-merge, no PR); the human reviews the *batch plan* roughly once per ~10
items, not every item.

**One session, one layer.** This session is the orchestrator: it drives the
current queue by loading `/aide-run-queue` **inline as a skill in this same
session** (which in turn loads `/aide-run-item` inline), and delegates only the
*leaf* work — item spec/tests/build/validate and queue *authoring* — to
**`Task` subagents** (`spec-author`, `test-writer`, `builder`, `validator`,
`queue-planner`). There is **no headless nesting**: the orchestrator never spawns
`claude -p` child processes. Each new queue is a natural session boundary — the
loop pauses at the queue PR, and the human re-invokes for the next queue, giving a
fresh session per batch.

**Command hygiene** applies to any git you issue — see `.aide/conventions.md` §3
(no `cd` prefix, one command per Bash call, no `2>&1`, no command substitution in
commit messages, recon via Bash + `grep`). A `PreToolUse` hook
(`.claude/hooks/command_hygiene_guard.py`) enforces the mechanical rules — a
violating shape is blocked and bounced back with the fix.

## Orchestration model & session scope

- **Run the orchestrator on Sonnet.** Orchestration here is light dispatch and
  gating — spawn a subagent, read its short summary, decide the next step. The
  heavy cognition lives in the subagents (`queue-planner` and `spec-author` on
  Opus; builder/validator on Sonnet). A slash command can't pin the session
  model, so if you're on Opus, `/model sonnet` before a long run.
- **All layers run inline in this one session; only leaf tasks are subagents.**
  `/aide-run-roadmap` → `/aide-run-queue` → `/aide-run-item` are loaded as skills
  in the *same* session (they are prompt expansions, not processes). The only
  parallel/isolated contexts are the `Task` subagents that do spec/test/build/
  validate/queue-authoring. This keeps orchestration state in one place and avoids
  the cold-start, stall, and cwd problems that killed the old headless design (see
  the post-mortem note below).

> **Historical note — the abandoned `--continuous` / headless-worktree design.**
> An earlier version offered a `--continuous` flag that ran the whole roadmap
> unattended by (a) spawning each layer as a nested headless `claude -p`
> subprocess and (b) isolating the loop in a dedicated git **worktree** that owned
> `main`. **Motivation:** drive the roadmap overnight without a human at each queue
> PR, bounding each layer's context by cold-starting a fresh process per queue/item.
> **Why it was removed:** on Windows the Bash tool **resets cwd to the repo root
> between calls**, so the "worktree owns `main`, `cd` in once" contract was
> impossible; headless `claude -p` children **cold-started, re-derived setup, and
> stalled on clarifying questions they couldn't answer** (a `-p` session can't be
> prompted); the 3-deep process nesting multiplied cold-start cost and failure
> points; and a parent-session death (usage-limit cutoff or restart) **lost the
> in-flight background subagent's state**. Net: it produced little reliable work.
> The single-session, git-commit-as-checkpoint model below is what replaced it —
> unattended long runs are instead handled by an *external* supervisor that
> relaunches this gated command (`.aide/loop/loop.py`, personal config in the
> gitignored `loop.local.toml`), with
> git commits + the resume logic below providing durable, restartable state.

## Determine current state first (resumable)

This loop spans sessions (it pauses for a human queue-PR merge), so always start
by working out where things stand. `git fetch --all --prune`, then read
`docs/aide/roadmap.md`, `docs/aide/progress.md`, and the queue files. The loop runs
**in-place in the primary checkout** (see *Working in parallel* below if you need
isolation).

| State | Action |
|---|---|
| **Roadmap exhausted** — every stage ✅ / deferred / excluded | Report done. Stop. |
| **An open `aide/queue-NNN` PR is awaiting merge** | Tell the user to review/merge it; **stop**. Re-invoke after merge. |
| **Latest queue merged to `main` but has 📋 items left** | Run that queue → go to **Run a queue**. |
| **Latest queue fully exhausted, roadmap has more stages** | Generate the next queue → go to **Generate the next queue**. |
| **No queue exists yet** | Generate the first queue → go to **Generate the next queue**. |

## Generate the next queue

Queue authoring is delegated to the **`queue-planner` (Opus)** subagent — never
run `/aide-create-queue` inline in the orchestrator (it would pollute this
session's context and tie queue quality to the orchestration model). The planner
writes + commits `queue-NNN.md` **and** tidies the superseded `queue-(NNN-1).md`
on whatever branch it's on, then returns a one-line summary. **You** (orchestrator)
prepare the branch and handle push/PR around it.

- `git switch -c aide/queue-NNN` off an up-to-date `main` (`git pull --rebase`).
- **Spawn `queue-planner`**: "Generate queue NNN on branch `aide/queue-NNN`;
  tidy the previous queue; commit both; do not push or PR." Wait for its summary.
- `git push -u origin aide/queue-NNN`, then open a **PR**:
  `gh pr create` titled `docs(aide): work queue NNN`, body summarising the batch.
- **STOP and tell the user**: review/edit/merge the queue PR, then re-invoke
  `/aide-run-roadmap` (or `/aide-run-queue NNN`) to execute it. A queue PR is
  the right place to reshape the plan before any code is built against it.

## Run a queue

Load **`/aide-run-queue NNN`** inline in this session and drive it to empty. When
it returns, loop back to **Generate the next queue** for NNN+1 (which branches +
PRs + stops again — the human re-invokes, giving a fresh session per queue).

## Tidy the previous queue

Whenever you generate queue NNN, first tidy the now-superseded queue NNN-1 so the
queue history stays legible and it's obvious which batch is live:

- Add/update a status line at its top, e.g.
  `> **Status:** ✅ Completed — superseded by queue-NNN (YYYY-MM-DD).`
- Mark each of its items with its final `progress.md` state (✅ done, or ⏸️/❌ if
  carried/dropped) so a stale 📋 list isn't left implying open work.
- Commit that tidy-up alongside the new queue, on the `aide/queue-NNN` branch.

This keeps exactly one **live** queue and a clean trail of closed ones.

## Working in parallel (optional worktree isolation)

The loop runs **in-place in the primary checkout** by default, which is correct
for a solo, sequential session. It switches branches constantly (`aide/NNN-*` →
`main` to merge → next), so if **you (the human) want to keep working in the repo
while the loop runs**, give the loop its own **git worktree** so your HEADs don't
collide:

- Create a sibling worktree that owns `main`: `git worktree add ../<project>-aide-loop main`,
  and keep **your** primary checkout on your own branch (git forbids `main` in two
  worktrees — that mutual exclusion is what prevents collisions).
- Give the worktree its **own venv** (`python .aide/scripts/aide.py env
  --bootstrap`, or a manual `python -m venv` + the `python.bootstrap` command from
  `aide.toml`) — an editable install otherwise resolves the project package to the
  primary `source_dir`, silently testing the wrong tree.
- Run the loop from the worktree. **Caveat:** the Bash tool resets cwd to the repo
  root between calls in this environment, so you cannot rely on a one-time `cd`;
  launch the loop *from* the worktree directory, or use `git -C <worktree>` /
  absolute paths. Remove it when done: `git worktree remove <path>`.

This is a manual convenience for genuine parallel work — not part of the automated
flow.

## If the human is unhappy with an auto-generated queue

The queue PR is the checkpoint to reshape a batch *before* any code is built, so
prefer editing the plan there. If a queue was already merged and items built, run
`/aide-feedback-loop`: adjust `vision.md`/`roadmap.md`/`progress.md` as
needed, and because merged work can't be cleanly un-merged, **identify which
already-implemented items need adapting and capture them as new corrective items**
in the next queue rather than rewriting history.

## When to stop and ask the user

- **Always, after opening each queue PR** — that pause is the whole point.
- A queue or item needs an edit to a **framework/process** file (`vision.md`,
  `roadmap.md`, `aide.toml`, `.aide/**`, `CLAUDE.md`, `.claude/**`) — reviewed
  PR, never auto-merge.
- `/aide-run-queue` reports an item blocked, a PR/force-push need, or a
  build↔validate cycle exceeding 3 rounds — surface it and pause.
