<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->

## Team workflow: spec-kit + AIDE

This project uses [spec-kit](https://github.com/github/spec-kit) with the
**AIDE** (AI-Driven Engineering) extension. The framework is **committed to the
repo and shared via GitHub** — it is the single source of truth.

### Setup is already done — do not re-initialize

- The framework lives in `.specify/` and `.claude/skills/` and is version
  controlled. A teammate only needs to `git clone` and use Claude Code; the
  `/speckit-*` and `/speckit-aide-*` commands work immediately.
- **Do not run `specify init` or `specify extension add`** in this project.
  That re-scaffolds and can overwrite our committed adaptations. The `specify`
  CLI is only needed by whoever deliberately upgrades the framework version
  (pinned at `0.11.7.dev0` in `.specify/init-options.json`); they do it once,
  commit, and everyone pulls.

### The AIDE loop (preferred workflow)

Living documents under `docs/aide/`. Start a fresh chat per step:

1. `/speckit-aide-create-vision` → `docs/aide/vision.md`   (once)
2. `/speckit-aide-create-roadmap` → `docs/aide/roadmap.md`  (once)
3. `/speckit-aide-create-progress` → `docs/aide/progress.md` (once)
4. `/speckit-aide-create-queue` → `docs/aide/queue/queue-NNN.md`
5. `/speckit-aide-create-item` → `docs/aide/items/NNN-*.md`
6. `/speckit-aide-execute-item` → implements + updates `progress.md`
7. `/speckit-aide-feedback-loop` → refine process at any step

Repeat 5–6 until the queue is empty, then back to 4. AIDE commands are pure
markdown — they call no helper scripts, so they run on Windows, macOS, and
Linux alike.

### Parallel work across machines (avoid merge conflicts)

`docs/aide/progress.md` and the active `queue-NNN.md` are shared, single files
that everyone touches — they are the main conflict hotspots. Conventions:

- **One person owns a work item at a time.** Each `docs/aide/items/NNN-*.md`
  has its own file, so two people working different items rarely collide.
- **Branch per work item, pushed immediately.** `git switch -c aide/NNN-short-name`,
  then `git push -u origin aide/NNN-short-name` **before doing real work** — the
  pushed branch is the shared "in progress" signal (see *Claiming a work item*
  below). Do the item on that branch; once it's green you may merge it **straight
  to `main` with no PR** (see *Merge policy* below). Don't work directly on `main`
  itself.
- **Pull before you start, and before `execute-item` writes `progress.md`.**
  Always `git pull --rebase` first so progress edits stack cleanly.
- **Keep `progress.md` edits scoped to your item's rows.** If two PRs both
  touch it, resolve by keeping both status changes (it's an additive log, not a
  rewrite).
- **Regenerate the queue from `main`, not a stale branch** (`create-queue`
  reads vision/roadmap/progress, so it must see the latest committed state).
- **Framework / process changes require a reviewed PR** — vision, roadmap,
  constitution, `CLAUDE.md`, skills, and AIDE commands. They cascade into every
  future queue, so they need team agreement before landing (see *Merge policy*
  below).

### Claiming a work item (how "in progress" is signalled)

`progress.md` is **not** a reliable mid-flight status board: its `📋 → 🚧`
edit is made on your feature branch and stays invisible on `main` until the PR
merges, and it tracks stage deliverables rather than individual items. The
reliable, shared "this item is taken" signal is therefore the **pushed
`aide/NNN-*` branch** (and its open/draft PR). Protocol — follow it whenever you
pick up an item (i.e. at `create-item` / `execute-item`):

1. **Before you pick, sync and check what's already claimed:**
   - `git fetch --all --prune`
   - `git branch -r | grep aide/` — remote work-item branches
   - `gh pr list --state open` — open/draft PRs (if using a GitHub remote)

   If a branch or PR already exists for that item number, it's claimed — pick
   another item or coordinate with the owner.
2. **Claim by pushing the branch *before* real work:**
   `git switch -c aide/NNN-short-name && git push -u origin aide/NNN-short-name`
   (an empty/WIP commit is fine). Now anyone who fetches sees the item is owned.
   Opening a **draft PR** at this point is encouraged — it makes the claim more
   visible and shows mergeable status.
3. **Do the work on that branch**, then merge it to `main` — a work item may
   merge directly, no PR required (see *Merge policy* below).
4. **Release / hand off:** if you abandon an item, delete the remote branch
   (`git push origin --delete aide/NNN-short-name`) and close its PR so the item
   returns to the pool.

> ⚠️ A branch only signals ownership **after you push it and others fetch**.
> Push at the *start*, not the end, and always `git fetch` before picking — a
> local-only branch tells collaborators nothing.

### Merge policy: PR vs. direct merge

Two categories, two rules:

- **Framework / process changes require a reviewed PR** (team agreement). These
  change *how everyone works* and cascade into every future queue and item:
  `docs/aide/vision.md`, `docs/aide/roadmap.md`,
  `.specify/memory/constitution.md`, `CLAUDE.md`, `.claude/skills/`, and the
  `.specify/extensions/` AIDE commands. Put them on their own branch and merge
  **only after PR review**.
- **Work-item execution may merge straight to `main` — no PR**, to keep the loop
  streamlined. The code, tests, the item spec (`docs/aide/items/NNN-*.md`), and
  your scoped `progress.md` status edits for a single item can be merged directly
  into `main` once green (`git switch main && git pull --rebase && git merge
  aide/NNN-short-name && git push`). You still **branch per item** (`aide/NNN-*`,
  pushed immediately) for the claim signal and isolation — direct merge relaxes
  the *review gate*, not the branch.

> Rule of thumb: if the change would alter a *future* queue or item (process,
> docs, commands), it needs a PR. If it only *executes* the current item, merge it.

### Shared vs. personal

- **Shared (committed):** `.specify/`, `.claude/skills/`, `.claude/commands/`,
  `.claude/agents/`, `.claude/settings.json`, `CLAUDE.md`, `docs/aide/`,
  `specs/`, `.specify/memory/constitution.md`.
- **Personal (git-ignored):** `.claude/settings.local.json`, any
  `.claude/*.local.*`, and credential files. Never commit credentials.

## Model routing, approval policy & queue runner

These three pieces tune *how* the agent works on this repo. They live in shared,
committed config so the whole team gets them.

### Model routing by task complexity (`.claude/agents/`)

Two committed subagents split work by cost/capability:

- **`scout` (Sonnet)** — light, **read-only** recon: finding code, reading specs,
  checking queue/progress state, listing branch/PR claims, running pre-approved
  read-only shell commands. Never edits, commits, or pushes.
- **`builder` (Opus)** — heavy **implementation**: implementing items, writing/
  restructuring pipeline code, writing tests, non-trivial debugging and refactors.
- **`validator` (Opus)** — independent, **adversarial validation** of a builder's
  work: confirms tests pass, checks the code against the item's Acceptance
  Criteria/description *and* the project vision, then actively tries to break it
  with hostile/edge-case inputs and adds tests to close gaps. A *different* agent
  from the builder — the implementer never signs off its own work.

Delegate "where is X / what's the current state" to `scout`; keep code, tests,
and structural work on `builder` (or the main thread when it's already Opus); and
gate every implemented item through a separate `validator`. Claude Code does
**not** auto-detect complexity and swap the main model — routing happens by
delegating to these agents (and by your own `/model` choice).

### Approval policy (`.claude/settings.json` permissions)

- **Auto-approved (no prompt):** read-only shell (git status/log/diff/show/branch,
  ls/grep/find), `pytest`, `pip install`, `python`, and routine git writes —
  `add`, `commit`, `switch`/`checkout`, `merge`, `pull`, and (non-force) `push`.
- **Always prompts (`ask`):** opening a **PR** (`gh pr …`), **force-push** /
  `reset --hard` / `rebase` (history rewrite), and **edits to framework/process
  files** — `CLAUDE.md`, `docs/aide/vision.md`, `docs/aide/roadmap.md`,
  `.specify/memory/constitution.md`, and everything under `.claude/skills`,
  `.claude/commands`, `.claude/agents`, `.specify/extensions`.
- **Default mode is `default`** — anything not explicitly allowed still prompts,
  so novel/major actions are gated by default.

Rule of thumb: *executing* a work item (code, tests, commit, direct-merge) flows
without prompts; anything that changes *how everyone works*, or touches the
remote in a hard-to-reverse way, asks first.

### Running the whole queue (`/aide-run-queue`)

`/aide-run-queue [NNN]` drives the AIDE loop over **every remaining 📋 item** in
the queue until empty. The invoking session acts purely as an **orchestrator** and
**spawns a sub-agent per task** rather than doing the work inline, with
**implementation and validation kept on separate agents**:

1. a `scout` for each recon/pick;
2. a **fresh `builder` per item** — create-item (if needed) → claim → implement +
   test → commit on the branch (it does **not** merge);
3. a **fresh `validator` per item** (a *different* agent) — confirms tests pass,
   checks the item spec + vision, adversarially attacks the code and adds tests,
   then flips the row to ✅ and direct-merges **only on PASS**; on FAIL it hands
   back and the orchestrator re-spawns a builder (cap: 3 build↔validate rounds).

Each item is isolated like "fresh chat per item"; the orchestrator passes only the
item number + short summaries between agents and **pauses for your approval only
at PRs and major structural changes**. Use it for an unattended batch run; use the
per-step `/speckit-aide-*` commands (fresh chat each) for tighter manual control.
