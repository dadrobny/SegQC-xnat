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

## Virtual environment

All code (tests, CLI, scripts) runs inside a **local `.venv`** at the project
root. This directory is gitignored and never committed — each machine builds its
own on first use.

**Bootstrap (first time, after a fresh clone, or when `.venv` is missing):**
```powershell
# Windows (PowerShell or Git Bash)
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
```
```bash
# macOS / Linux
python -m venv .venv
.venv/bin/pip install -e .[dev]
```

**Staleness check.** Before running tests or starting a new item, verify the
env is current:
```bash
.venv/Scripts/python -c "import segqc"   # Windows Git Bash
.venv/bin/python -c "import segqc"       # macOS/Linux
```
If the import fails (or `.venv` does not exist), re-run the bootstrap above.

**Agent rule — builders and validators MUST:**
1. Check whether `.venv` exists and `import segqc` succeeds inside it.
2. If not, rebuild with the bootstrap commands before writing or running any code.
3. Invoke all Python and pytest via the venv:
   - Windows (Git Bash): `.venv/Scripts/python -m pytest`, `.venv/Scripts/pip`
   - macOS/Linux: `.venv/bin/python -m pytest`, `.venv/bin/pip`

The `Bash(python -m venv:*)`, `Bash(.venv/Scripts/python:*)`,
`Bash(.venv/bin/python:*)`, and `Bash(.venv/Scripts/pip:*)` entries in
`settings.json` cover these invocations without further prompts.

---

## Model routing, approval policy & queue runner

These three pieces tune *how* the agent works on this repo. They live in shared,
committed config so the whole team gets them.

### Model routing by task complexity (`.claude/agents/`)

Four committed subagents split work by role and cost:

- **`scout` (Haiku)** — narrow **recon + claim**: syncs the repo, reads the
  queue and progress files, checks `aide/*` branches to find the next unclaimed
  📋 item, then creates and pushes the claim branch. Returns only item number,
  branch name, and title. Never searches source code; file locations are known.
- **`builder` (Sonnet, escalates to Opus on 3rd attempt)** — **implementation
  only**: implements production code in `src/` per the item spec, records
  decisions, sets progress 🚧, commits. Does **not** write tests and does **not**
  run pytest. The orchestrator escalates to Opus only when a validator has FAILed
  the item twice already.
- **`test-writer` (Sonnet)** — **test definition only**: reads the item spec and
  AC, writes tests covering every AC plus adversarial/edge-case inputs, commits.
  Does **not** touch `src/` and does **not** run pytest.
- **`validator` (Sonnet)** — independent **quality gate**: runs pytest, checks
  that every AC has a test, verifies code scope, confirms vision fit. Does **not**
  write or modify tests. On PASS flips ✅ and direct-merges; on FAIL hands back
  identifying which agent (builder or test-writer) needs to fix it.

Delegate recon/claim to `scout`; implementation to `builder`; test authoring to
`test-writer`; verification to `validator`. Claude Code does **not** auto-detect
complexity and swap the main model — routing happens by delegating to these agents
(and by your own `/model` choice).

### Approval policy (`.claude/settings.json` permissions)

- **Auto-approved (no prompt):** read-only shell (git status/log/diff/show/branch,
  ls/grep/find), `pytest`, `pip install`, `python`, `python -m venv`,
  `.venv/Scripts/python`, `.venv/bin/python` (and their `pip`/`pytest` siblings),
  and routine git writes — `add`, `commit`, `switch`/`checkout`, `merge`,
  `pull`, and (non-force) `push`.
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

### Command hygiene (so the allow-list actually matches)

The approval rules match a command **prefix** (`git fetch`, `git commit`, …) and
auto-approve a compound (`A && B`, `A | B`) only when it can be split cleanly
*and every part* matches. Agents must therefore emit commands in a shape the
matcher recognises, or an unattended `/aide-run-queue` batch stalls on prompts
even though the rule "exists". Required form for all agents:

- **No `cd` prefix, and no `git -C "<abs path>"`.** The Bash tool's working
  directory is already the repo root, so both are redundant. `cd "<abs path>" &&
  …` turns a bare allowed command into a fragile multi-part compound, and
  `git -C "<abs path>" …` re-injects the path needlessly — and this repo's path
  contains spaces and an apostrophe (`King's`), which makes either worse. Run the
  bare command.
- **One command per Bash call.** Don't chain with `&&` or `;`. Separate calls
  each match their own rule (e.g. `git add …`, then `git commit …`, then
  `git push`), and a failure is easier to localise.
- **No `2>&1` (or other redirections).** The Bash tool already captures stderr.
- **No command substitution in commits.** `git commit -m "$(cat <<'EOF' … EOF)"`
  is **never** auto-approved — the matcher can't see inside `$(…)`. Use a
  single-line `-m "msg"`, repeated `-m "summary" -m "body"` for multiple
  paragraphs, or `git commit -F <file>`.
- **Recon goes through the Bash tool with `grep`** (`git branch -r | grep aide/`),
  never the PowerShell tool / `Select-String` — only `Bash(...)` rules are in the
  allow-list, so PowerShell-tool calls always prompt.
- **Python and pytest run through the Bash tool in the *relative* form** —
  `.venv/Scripts/python -m pytest`, `.venv/Scripts/python -c "import segqc"` (or
  the `.venv/bin/python` equivalents). The allow rule is `Bash(.venv/Scripts/python:*)`,
  which matches only the relative prefix; a PowerShell call operator or an absolute
  `& "c:\…\.venv\Scripts\python" …` path matches nothing and always prompts.

These rules are repeated in each agent spec (`.claude/agents/*.md`) so a
cold-started sub-agent sees them. After a batch, `/aide-review-permissions` is
still the backstop for anything that slipped through.

### Running the whole queue (`/aide-run-queue`)

`/aide-run-queue [NNN]` drives the AIDE loop over **every remaining 📋 item** in
the queue until empty. The invoking session acts purely as an **orchestrator** and
**spawns a sub-agent per task** rather than doing the work inline:

1. a `scout` per item — syncs, finds the next unclaimed 📋 item, claims it
   (creates + pushes the `aide/NNN-*` branch);
2. a **fresh `builder` per item** — checks out the branch, creates the item spec
   if missing, implements production code, commits (no tests, no pytest);
3. a **fresh `test-writer` per item** — reads the spec, writes AC + adversarial
   tests, commits (no production code, no pytest);
4. a **fresh `validator` per item** (a *different* agent from builder and
   test-writer) — runs pytest, checks AC coverage, checks scope and vision fit,
   then flips ✅ and direct-merges **only on PASS**; on FAIL it identifies which
   agent needs to fix it and the orchestrator re-spawns accordingly
   (cap: 3 validation rounds).

Each item is isolated like "fresh chat per item"; the orchestrator passes only the
item number + short summaries between agents and **pauses for your approval only
at PRs and major structural changes**. Use it for an unattended batch run; use the
per-step `/speckit-aide-*` commands (fresh chat each) for tighter manual control.

### Permission tracking & review (`/aide-review-permissions`)

Even with the approval policy above, unattended `/aide-run-queue` batches still
stall on the occasional permission prompt. To close that loop:

- **Auto-logging (hook).** A `PreToolUse`/`PostToolUse` hook
  (`.claude/hooks/log_permission_event.py`, registered in `.claude/settings.json`)
  records every prompt-eligible tool call (Bash/Edit/Write/Web…) and its grant/deny
  outcome — **including inside sub-agents**, which the orchestrator never sees. The
  hook only records: it never blocks or alters a tool, and always exits 0.
- **Per-machine log.** Records go to `docs/aide/permissions/log.jsonl`, which is
  **gitignored** (an append-only log written from many machines would conflict like
  `progress.md`). Only the *reviewed outcome* — allow-list edits — is shared.
- **Review.** `/aide-review-permissions` (also folded into
  `/speckit-aide-feedback-loop`) runs `.claude/scripts/review_permissions.py` to rank
  the prompts hit, infer grant/deny, drop already-allowed calls, and suggest rules.
  Promote the safe, recurring ones into `permissions.allow`; keep destructive /
  outward-facing ones under `ask`. The `settings.json` change is a framework edit —
  it lands **via PR**.
