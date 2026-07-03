# AIDE conventions

The shared contract every agent, script, and human obeys. Three parts: the
**format contract** for the living documents (so scripts parse them without
heuristics), the **claim protocol** (how "in progress" is signalled), and the
**command hygiene** rules (stated once here; agent specs only point back).

---

## 1. Format contract — `docs/aide/` documents

`.aide/scripts/aide.py` (`check`, `progress set`, `queue tidy`) and
`scripts/aide_status_report.py` parse these files by exact shape. Deviating from
the shapes below breaks the tooling, so the templates in `.aide/templates/`
model them and `aide check` enforces them.

### Status icons (the only five)

| Icon | Meaning | Rank |
|------|---------|------|
| 📋 | Planned | 0 |
| 🚧 | In Progress | 3 |
| ✅ | Complete | 4 |
| ⏸️ | Deferred | 2 |
| ❌ | Excluded | 1 |

Rank is used when one item is referenced on several lines: the most-advanced
status wins.

### `progress.md` (the single source of truth for status)

Mandatory, in order (consumer in brackets):

1. **Stage summary table** — `| Stage | Title | Objectives | Status |` with one
   row per stage; `Stage` is an integer, `Status` a single icon. *(aide check,
   status report, queue-planner)*
2. **Objective coverage table** — `| Objective | Delivered by | Status |`; the
   objective cell starts with a `G<n>` code. *(status report, validator)*
3. **One `## Stage N — <title> — <icon>` section per stage.** Inside it:
   - a **Deliverables** block of **flat** bullets, each
     `- <icon> <text>. *(Item NNN)*` — one status icon, one item ref, no nested
     status-bearing sub-bullets (keep rollup unambiguous). *(builder, validator,
     aide progress, status report)*
   - an **Acceptance** block of `- [ ]` / `- [x]` checkboxes. *(validator, aide
     check rollup)*

**Rollup rule (deterministic — `aide progress` and `aide check` both apply it):**
a stage is ✅ if *every* Deliverables bullet in it is ✅; then all its Acceptance
boxes are `[x]`, and its summary-table row, section header, and any Objective row
delivered solely by complete stages read ✅. If any bullet is ✅/🚧 but not all,
the stage is 🚧. Otherwise 📋. Acceptance boxes are ticked **only** at stage
completion (per-item AC ticking is not deterministic).

### `queue-NNN.md`

- One header line `> **Status:** Live` on the active queue; superseded queues
  carry `> **Status:** ✅ Completed — superseded by queue-NNN (YYYY-MM-DD).`
  **Exactly one** queue is `Live`. *(aide check, queue tidy)*
- Work items as `### Item NNN: Short Title` + a description paragraph. Item
  numbers are **globally sequential across all queues** — never restart. *(aide
  check, scout/claim, spec-author)*

### `items/NNN-*.md`

- Filename begins with the zero-padded number. First `#` heading is
  `# Item NNN — <Title>`. *(status report title parse)*
- **No status field** in the header — status lives only in `progress.md`. The
  header carries `Created`, Stage, Queue, Objectives, Suggested branch, and a
  mandatory **Assumptions** block (see the item template). *(spec-author,
  validator)*

---

## 2. Claim protocol — how "in progress" is signalled

`progress.md`'s `🚧` edit lives on a feature branch and is invisible on `main`
until merge, so it is **not** the mid-flight signal. The shared "this item is
taken" signal is the **pushed `<branch_prefix>NNN-*` branch** (config
`git.branch_prefix`, default `aide/`). `aide claim` owns this:

1. `git fetch --all --prune`; list remote `aide/*` branches.
2. Read the live queue + `progress.md`; pick the **first** item that is 📋, whose
   dependencies are all ✅, and that has no existing `aide/NNN-*` branch.
3. Create and push `aide/NNN-short-name` (push depends on `git.mode`; `local`
   mode does not push and so has no multi-machine claim signal).

One person (or one loop) owns an item at a time. Abandoning an item means
deleting its remote branch so the item returns to the pool; `aide check` flags a
claim branch whose item is already ✅ (stale claim).

---

## 3. Command hygiene (stated once; agents point here)

The permission allow-list matches a command **prefix** and auto-approves a
compound only if every part matches. Emit commands in the shape the matcher
recognises, or an unattended run stalls on prompts:

- **No `cd` prefix and no `git -C "<path>"`.** The Bash tool's cwd is already the
  repo root; both are redundant and break prefix matching (this repo's path has
  spaces and an apostrophe). Run the bare command.
- **One command per Bash call.** Never chain with `&&` or `;` — separate calls
  each match their own rule and localise failures.
- **No `2>&1`** or other redirections — the Bash tool already captures stderr.
- **No command substitution in commits.** `$(…)`/backticks are never
  auto-approved. Use single-line `-m "msg"`, repeated `-m` for paragraphs, or
  `git commit -F <file>`.
- **Recon via the Bash tool with `grep`** (`git branch -r | grep aide/`), never
  the PowerShell tool / `Select-String` — only `Bash(...)` rules are allow-listed.
- **Python/pytest via the venv in relative form** — `.venv/Scripts/python …`
  (Windows) or `.venv/bin/python …`. Not an absolute path, not the PowerShell
  call operator: only the relative prefix is allow-listed.
- **The `aide` CLI** runs as `python .aide/scripts/aide.py <cmd>` (stdlib-only,
  venv-independent) — one allow rule covers every subcommand.

---

## 4. Git modes (`git.mode` in `aide.toml`)

Enforced **only** inside `aide claim` / `aide merge`; agent instructions are
identical across modes.

- **`auto-merge`** (default) — claim branch pushed; on validator PASS `aide merge`
  direct-merges to `main`, re-runs the test command, deletes the claim branch.
- **`pr`** — claim identical; on PASS `aide merge` pushes the branch and **stops**
  ("open a PR"). The human opens the PR (`gh pr create` stays `ask`-gated).
- **`local`** — no pushes at all (offline). Claim is a local branch only (no
  multi-machine signal); merge is local into `main`.

---

## 5. Clarify mode (`loop.clarify` in `aide.toml`)

Controls how `spec-author` resolves an ambiguous queued item:

- **`interactive`** — ask ≤3 targeted questions before writing the spec.
- **`assume`** (unattended default) — pick the most defensible default and record
  each choice in the spec's mandatory **Assumptions** block, which the validator
  surfaces so a human can audit at the queue boundary. Nothing ever hangs.

A spec written before its dependencies are *implemented* must pin their interfaces
as Assumptions; the builder/validator hand back if reality diverged.
