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
- **Branch per work item.** `git switch -c aide/NNN-short-name`, do the item on
  that branch, open a PR. Don't commit AIDE work directly to `main`.
- **Pull before you start, and before `execute-item` writes `progress.md`.**
  Always `git pull --rebase` first so progress edits stack cleanly.
- **Keep `progress.md` edits scoped to your item's rows.** If two PRs both
  touch it, resolve by keeping both status changes (it's an additive log, not a
  rewrite).
- **Regenerate the queue from `main`, not a stale branch** (`create-queue`
  reads vision/roadmap/progress, so it must see the latest committed state).
- **Vision / roadmap / constitution changes go through their own PR** and
  should be agreed by the team, since they cascade into every future queue.

### Shared vs. personal

- **Shared (committed):** `.specify/`, `.claude/skills/`, `.claude/commands/`,
  `.claude/settings.json`, `CLAUDE.md`, `docs/aide/`, `specs/`,
  `.specify/memory/constitution.md`.
- **Personal (git-ignored):** `.claude/settings.local.json`, any
  `.claude/*.local.*`, and credential files. Never commit credentials.
