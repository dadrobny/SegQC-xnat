---
description: Drive the AIDE roadmap across MULTIPLE queues — generate a queue, run it to completion (via /aide-run-queue), then generate the next — until the roadmap is exhausted. Default gates each new queue behind a human-reviewed PR; --continuous keeps going without waiting.
argument-hint: "[--continuous] [--worktree] — optional; default is human-gated (PR per queue), in-place"
---

# Run the AIDE roadmap (loop over queues)

The widest AIDE loop: iterate **over queues** across the whole roadmap. Where
`/aide-run-queue` runs the items *within one queue*, this command **generates
each queue and chains them** — create queue → run it → create the next → … —
until `docs/aide/roadmap.md` has no further stage to queue.

The **queue is the human checkpoint.** Items inside an approved queue flow freely
(direct-merge, no PR); the human reviews the *batch plan* roughly once per ~10
items, not every item.

Mode: **$ARGUMENTS**
- *(default, gated)* — each new queue lands via a **human-reviewed PR**; the loop
  **pauses** until the human merges it, then runs the queue.
- `--continuous` — don't wait: commit each new queue straight to `main` and run
  it immediately, looping until the roadmap is exhausted. The human reviews
  queues **after the fact** (git history) and course-corrects via
  `/speckit-aide-feedback-loop` if needed.

This session is only the orchestrator — delegate item execution to
`/aide-run-queue` (which delegates to `/aide-run-item`) and queue *authoring* to
the `queue-planner` subagent. **Command hygiene** applies to any git you issue:
no `cd` prefix, one command per Bash call, no `2>&1`, no command substitution in
commit messages, recon via Bash + `grep`.

## Orchestration model & session scope

- **Run the orchestrator on Sonnet.** Orchestration here is light dispatch and
  gating — spawn a subagent, read its short summary, decide the next step. The
  heavy cognition lives in the subagents (`queue-planner` and `spec-author` on
  Opus; builder/validator on Sonnet). A slash command can't pin the session
  model, so if you're on Opus, `/model sonnet` before a long run.
- **The two modes execute differently** (because the `Task` subagent tool can't
  reliably spawn its *own* subagents, but a fresh `claude` process can):
  - **Gated (default) — inline, interactive, one session per queue.** Each layer
    loads the next as a skill in *this* session; only the leaf (`/aide-run-item`)
    spawns worker subagents. The human re-invokes per queue, so each queue gets a
    fresh session naturally. **No headless sessions are used in gated mode.**
  - **`--continuous` — headless nesting in an isolated worktree.** Each layer
    spawns the next as a **fresh `claude` subprocess** (`claude --model sonnet -p
    "/aide-run-queue NNN --continuous"`), run inside a dedicated **git worktree**
    (see below). The Bash call blocks until that child exits — that is how "the
    higher level waits for the lower to finish." A `claude -p` child is a full
    session, so it *can* spawn its own subagents; this is what makes true nesting
    work. Each child cold-starts, does one queue/item, and exits, keeping every
    layer's context bounded.

> **⚠️ Billing & opt-in.** Headless `claude -p` sessions may count against a
> **separate API usage limit**, distinct from interactive sessions. They are used
> **only** behind the explicit `--continuous` flag — gated mode draws none. Don't
> reach for `claude -p` outside this path. Standardise the spawn as
> `claude --model sonnet -p "<slash command>"` (stable prefix first) so it stays
> inside the allow-list and pins the cheap model.

> **Permission posture is essential for `--continuous`.** A headless `claude -p`
> child **cannot answer a permission prompt** — any non-allow-listed tool call
> stalls or denies it instead of asking. So a continuous run is only as reliable
> as the `permissions.allow` list (and likely `--permission-mode acceptEdits` for
> builders' file edits). Keep the allow-list current via `/aide-review-permissions`.

## Worktree isolation (`--worktree`, implied by `--continuous`)

Worktree isolation and the headless `--continuous` mechanism are **orthogonal**:
isolation is about *where* the loop runs; `--continuous` is about *how* layers
nest. Any multi-item loop switches branches constantly (`aide/NNN-*` → `main` to
merge → next), so if it shares the **one** working directory with the human (or
another loop), their HEADs collide — exactly the failure that lands commits on the
wrong branch. So **isolation is good practice for any multi-item loop where
parallel work is possible**, independent of `--continuous`:

- **`--worktree`** (opt-in) — run this gated/interactive loop in its own worktree.
  **Recommended whenever you (or another loop) will touch the repo in parallel.**
- **`--continuous`** — **always** isolated (it *must* be, since its headless
  children run with the worktree as cwd); `--continuous` implies `--worktree`.
- Neither flag — runs in-place in the primary checkout (fine for a solo,
  sequential session with no parallel work).

When isolating, operate in a **dedicated git worktree**:

1. **Create a sibling worktree that owns `main`.** From the repo root, derive a
   sibling path (e.g. `../segqc-aide-loop`) and `git worktree add <path> main`.
   The loop does *all* its branch create/checkout/merge work there.
   - **Contract:** the human's primary checkout must **stay off `main`** (work on
     your own branch). Git forbids the same branch in two worktrees, so the loop
     owning `main` and the human staying off it is what keeps the validator's
     `switch main && merge` working. If `main` is already checked out in the
     primary, stop and ask the user to switch off it first.
2. **Give the worktree its own `.venv`.** A worktree has its own `src/`, but the
   primary checkout's venv resolves `import segqc` (editable install) to the
   *primary* source — so the worktree **must** bootstrap its own venv or tests
   would silently exercise the wrong code. In the worktree: `python -m venv .venv`
   then `.venv/Scripts/pip install -e .[dev]` (or `.venv/bin/...`).
3. **Operate inside the worktree.** Mechanism depends on mode:
   - *`--continuous`* → spawn the `claude -p` children with their **cwd set to the
     worktree**; they (and their workers) operate entirely there.
   - *gated `--worktree`* → `cd <worktree>` **once** at the start as its own Bash
     call (the Bash tool's cwd persists across calls). This is the one allowed
     exception to the "no `cd`" hygiene rule — it is a standalone `cd`, not a
     `cd X && cmd` compound, so subsequent **bare** git/python commands still match
     the allow-list, now operating in the worktree. The primary checkout is never
     touched.
4. **Clean up on exit / resume.** When the roadmap is exhausted (or you abort),
   `git worktree remove <path>`; on resume, `git worktree prune` and reuse an
   existing loop worktree rather than stacking new ones.

> The framework places the worktree as a **sibling of wherever the repo lives** —
> it makes no assumption about that location. Heavy git churn is happiest on a
> fast local disk; keeping the repo off a synced/cloud folder is a **user setup
> concern**, not something this workflow handles.

## Determine current state first (resumable)

This loop spans sessions (gated mode pauses for a human merge), so always start
by working out where things stand. `git fetch --all --prune`, then read
`docs/aide/roadmap.md`, `docs/aide/progress.md`, and the queue files.

**If `--worktree` or `--continuous`:** before the state check, ensure the **loop
worktree** exists (create it + its venv per *Worktree isolation* above, or
reuse/prune an existing one) and operate inside it (cwd for `--continuous`
children; a one-time `cd` for gated `--worktree`).

| State | Action |
|---|---|
| **Roadmap exhausted** — every stage ✅ / deferred / excluded | Report done. Stop. |
| **An open `aide/queue-NNN` PR is awaiting merge** (gated) | Tell the user to review/merge it; **stop**. Re-invoke after merge. |
| **Latest queue merged to `main` but has 📋 items left** | Run that queue → go to **Run a queue**. |
| **Latest queue fully exhausted, roadmap has more stages** | Generate the next queue → go to **Generate the next queue**. |
| **No queue exists yet** | Generate the first queue → go to **Generate the next queue**. |

## Generate the next queue

Queue authoring is delegated to the **`queue-planner` (Opus)** subagent — never
run `/speckit-aide-create-queue` inline in the orchestrator (it would pollute this
session's context and tie queue quality to the orchestration model). The planner
writes + commits `queue-NNN.md` **and** tidies the superseded `queue-(NNN-1).md`
on whatever branch it's on, then returns a one-line summary. **You** (orchestrator)
prepare the branch and handle push/PR/merge around it.

1. **Gated (default):**
   - `git switch -c aide/queue-NNN` off an up-to-date `main` (`git pull --rebase`).
   - **Spawn `queue-planner`**: "Generate queue NNN on branch `aide/queue-NNN`;
     tidy the previous queue; commit both; do not push or PR." Wait for its summary.
   - `git push -u origin aide/queue-NNN`, then open a **PR**:
     `gh pr create` titled `docs(aide): work queue NNN`, body summarising the batch.
   - **STOP and tell the user**: review/edit/merge the queue PR, then re-invoke
     `/aide-run-roadmap` (or `/aide-run-queue NNN`) to execute it. A queue PR is
     the right place to reshape the plan before any code is built against it.
2. **`--continuous`:**
   - On `main` (`git pull --rebase`), **spawn `queue-planner`**: "Generate queue
     NNN on `main`; tidy the previous queue; commit both; do not push." Then
     `git push` the planner's commit to `main`.
   - Proceed immediately to **Run a queue** (do not open a PR, do not wait).

## Run a queue

Run the current queue to completion, then move on. **How** depends on the mode:

- **Gated:** load **`/aide-run-queue NNN`** inline in this session and drive it to
  empty. When it returns, loop back to **Generate the next queue** for NNN+1
  (which branches + PRs + stops again — the human re-invokes, giving a fresh
  session per queue).
- **`--continuous`:** spawn a **fresh headless child** for the queue, in the loop
  worktree, and **wait for it to exit**:
  ```
  claude --model sonnet -p "/aide-run-queue NNN --continuous"
  ```
  (run with the worktree as cwd). The child drives that queue to empty and exits;
  the blocking Bash call is the orchestrator "waiting for the lower session to
  end." When it returns, loop to **Generate the next queue** for NNN+1 and spawn
  the next child. Keep going until the roadmap is exhausted or a hard blocker
  appears, then **remove the worktree**.

## Tidy the previous queue

Whenever you generate queue NNN, first tidy the now-superseded queue NNN-1 so the
queue history stays legible and it's obvious which batch is live:

- Add/update a status line at its top, e.g.
  `> **Status:** ✅ Completed — superseded by queue-NNN (YYYY-MM-DD).`
- Mark each of its items with its final `progress.md` state (✅ done, or ⏸️/❌ if
  carried/dropped) so a stale 📋 list isn't left implying open work.
- Commit that tidy-up alongside the new queue (gated: on the `aide/queue-NNN`
  branch; continuous: directly to `main`).

This keeps exactly one **live** queue and a clean trail of closed ones.

## If the human is unhappy with an auto-generated queue

(Most relevant in `--continuous`, where items may already be merged.) Run
`/speckit-aide-feedback-loop`: adjust `vision.md`/`roadmap.md`/`progress.md` as
needed, and because merged work can't be cleanly un-merged, **identify which
already-implemented items need adapting and capture them as new corrective items**
in the next queue rather than rewriting history. The feedback loop is the
sanctioned way to course-correct without blocking forward progress.

## When to stop and ask the user

- **Always, in gated mode, after opening each queue PR** — that pause is the
  whole point.
- A queue or item needs an edit to a **framework/process** file (`vision.md`,
  `roadmap.md`, `constitution.md`, `CLAUDE.md`, `.claude/**`,
  `.specify/extensions/**`) — reviewed PR, never auto-merge.
- `/aide-run-queue` reports an item blocked, a PR/force-push need, or a
  build↔validate cycle exceeding 3 rounds — surface it and pause.
