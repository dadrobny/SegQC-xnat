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

**Template fill-in conventions** (readable rendered *and* machine-checkable):
a template uses `{{slot-name}}` for a literal value to substitute, and an
_italic line_ for authoring guidance to read then replace with real prose.
Both render as ordinary markdown — nothing is swallowed by a renderer the way
an unescaped `<Placeholder>` tag would be. `aide check` flags any `{{...}}`
left in a generated `docs/aide/**.md` file as an unfilled template slot.
Dates are always **ISO 8601** (`YYYY-MM-DD`) — the templates' `{{yyyy-mm-dd}}`
slot spells the format out so no separate lookup is needed.

**Header blockquote** — every living document opens with one, carrying its step
number in the loop, what it derives from, and what derives from it. Those are
structural facts that hold as long as the document exists, so a reader landing
anywhere in `docs/aide/` can place the file without cross-referencing. Keep the
line current when a document's relationships change. The transient hand-off
("run `/aide-…` next") is spoken by the skill that wrote the file, not stored
in it.

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

**Structural positions only.** The parsers read icons *only* at structural
positions: a table row's **Status (last) cell**, a stage header's **trailing**
`— <icon>`, and the **leading** icon of a deliverable bullet. An icon anywhere
else — prose, mid-bullet, a title — is plain text and is never read as status,
so authors need not avoid the icon vocabulary in free text. `aide check` still
*warns* on such stray icons in the status-bearing documents (`progress.md`,
queue files) so they stay unambiguous for human readers; other documents are
not scanned.

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

**Item references on a deliverable bullet.** The `*(Item NNN)*` suffix is what
ties an item to the bullet whose status it moves — `aide progress set NNN` finds
the bullet by it, and `check`/`status`/`claim` derive queue state from it, so an
item no bullet references is untracked. Four forms are accepted, and all four
mean the same thing to every command:

| Form | Reads as |
|---|---|
| `*(Item 006)*` | 6 |
| `*(Items 006, 044)*` | 6, 44 — one deliverable, several items |
| `*(Items 041, 053, 057)*` | 41, 53, 57 — a list is any length |
| `*(Items 089/090)*` | 89, 90 |
| `*(Items 071–075)*` | 71, 72, 73, 74, 75 — inclusive, hyphen or en-dash |
| `*(Items 006, 044–046)*` | 6, 44, 45, 46 — an element may be a range |

Spacing around a separator does not matter. A range spanning more than 50 is
read as a typo and contributes only its endpoints. Prefer the explicit list when
the items are not contiguous; a range is only shorthand for one.

**Rollup rule (deterministic — `aide progress` and `aide check` both apply it):**
a stage is ✅ if *every* Deliverables bullet in it is ✅; then all its Acceptance
boxes are `[x]`, and its summary-table row, section header, and any Objective row
delivered solely by complete stages read ✅ (unless the objective is linked to an
Outcome target that is not `✅ Met` — see below). If any bullet is ✅/🚧 but not all,
the stage is 🚧. Otherwise 📋. Acceptance boxes are ticked **only** at stage
completion (per-item AC ticking is not deterministic).

**What a stage's ✅ means — and what it deliberately does not.** The rollup
makes stage status track exactly one thing: *the planned work shipped*. An
Acceptance box is therefore an observable check **of the built thing** (the
CLI runs, the artifact validates) — something completing the deliverables can
guarantee. A **measured outcome** the work aims for but cannot guarantee by
construction (an error-rate target, a benchmark result) must NOT be an
Acceptance box: it would either be auto-ticked into an over-claim or hold the
stage 🚧 forever against work that genuinely shipped. Such goals go in the
**Outcome targets** table below.

**Outcome targets (optional, additive).** A `## Outcome targets` section in
`progress.md` with one row per measured goal:

```
| Target | Objective | Attempted by | Status | Evidence / follow-up |
|--------|-----------|--------------|--------|----------------------|
| Held-out FPR ≤ 0.10 | G3 | Stage 14 | ❌ Not met | FPR 0.975 → gap insight, item 0NN |
```

Status is table-local (like the env-gated verification table's): `❓
Unverified` until measured, then `✅ Met (date, evidence)` or `❌ Not met
(result → follow-up)`. Semantics *(aide progress, aide check, aide status)*:

- A target **never blocks its stage** — the stage closes when its work ships.
  It gates the **Objective coverage rows** instead: an objective linked to a
  target that is not `✅ Met` cannot roll up to ✅, and `aide check` errors on
  an objective claimed ✅ over a `❌ Not met` target (the goal-level mirror of
  the deliverable-level over-claim error).
- Marking a target `❌ Not met` is a *finding*, so route it like one: append a
  `- [ ] gap — …` line to `insights.md` in the same edit. The feedback loop
  then plans the follow-on deliverables explicitly — needing more work than
  planned to hit a goal is normal, and it enters through the queue, not by
  retro-editing a closed stage's deliverable list.
- `aide status` prints every target not yet `✅ Met`, so the state stays
  visible even though the stage summary table does not carry it.

### `queue-NNN.md`

- **Queue state is derived, not declared.** A queue is **open** iff any of its
  items is 📋/🚧 in `progress.md`, else **done**; "the live queue" is the
  lowest-numbered open one (`aide claim`'s default). A `> **Status:**` line is
  optional decoration for human readers — `aide queue tidy` stamps a completion
  note on superseded queues, and `aide check` warns only when a declared status
  contradicts the derived state. *(aide check, claim, queue tidy)*
- Work items as `### Item NNN: Short Title` + a description paragraph. Item
  numbers are **globally sequential across all queues** — never restart. *(aide
  check, scout/claim, spec-author)*

### `items/NNN-*.md`

- Filename begins with the zero-padded number. First `#` heading is
  `# Item NNN — Title`. *(status report title parse)*
- **No status field** in the header — status lives only in `progress.md`. The
  header carries `Created`, Stage, Queue, Objectives, Suggested branch, and a
  mandatory **Assumptions** block (see the item template). *(spec-author,
  validator)*

### `insights.md` (optional, additive — the compound-engineering inbox)

Where out-of-scope learning goes so it is never lost *and* never acted on out
of scope. Any role, at any time, appends **one line** and returns to its task:

```
- [ ] <type> — <one line> *(item NNN, YYYY-MM-DD)*
```

with `<type>` one of **knowledge** (document it), **defect** (fix it), **gap**
(plan it), **automation** (a recurring manual/agent action deterministic code
could replace — script it), **framework** (belongs to AIDE itself). The item
ref is optional for roles outside an item. The file is **append-only**;
`aide check` shape-checks entries (warning, never error — capture must stay
cheap). Template: `.aide/templates/insights.md` (copy verbatim).

**Triage** happens at the queue boundary (the feedback loop): each unchecked
entry is routed — `knowledge` → the owning document; `defect`/`gap` →
candidate items for the queue being authored (so the queue PR reviews them);
`automation` → a candidate item that adds a CLI verb/script *and* the
skill/agent edit mandating it; `framework` → a GitHub issue on
`[framework] repo` from `aide.toml` (via `gh`; if unset/offline the entry
stays pending). A routed entry is ticked in place:
`- [x] … → <where it landed>`.

### Environment-gated capabilities (optional, additive)

A capability gated behind an optional package or external tool (a GPU
library, Docker, a large/optional pip extra, ...) must degrade gracefully —
its tests skip cleanly (never fail, never silently pass as if exercised) when
the dependency is absent, mirroring the project's existing optional-extra
pattern. That graceful-fallback bar is enough for a stage to reach ✅ under the
rollup rule above — **but** a skip-clean pytest run is not evidence the
optional path was ever run for real, and nothing else records that gap by
default. Two additive, non-blocking mechanisms close it:

- The item template's optional **Environment / Hardware Dependencies**
  section — filled in by any item introducing such a capability, naming the
  package/tool, its `pyproject`/equivalent declaration, and the required
  fallback behaviour.
- `progress.md`'s optional **Environment-Gated Capability Verification**
  table — one row per capability, starting `❓ Unverified`. A stage-closing
  item's Implementation Steps must add/update the row(s) for any capability
  its stage introduced. The row flips to `✅ Verified (date, host/CI)` only
  when a human or a CI runner that actually has the dependency present has
  run the gated path — never inferred from the stage's own ✅ status.

Both mechanisms are opt-in: a project with no environment-gated capability
omits them entirely.

Two additions make the verification *planned* rather than hoped-for:

- **`[validation]` environment profiles** (`aide.toml`, optional) — named,
  deterministic environment checks: `<name> = "<python expression>"`, true iff
  the environment provides the capability (e.g.
  `gpu = "__import__('torch').cuda.is_available()"`). Evaluated by
  `aide env --profile <name>` (exit 0 iff satisfied) in the project venv.
- **Stage-validation items** — a queue that closes a roadmap stage ends with a
  `Validate stage N` item that replays the stage's use cases end-to-end and
  updates the capability table (✅ Verified where the profile is satisfied,
  else an explicit ❓ Unverified with the reason). Item specs may also carry an
  optional **Validation** section (see the item template) that the validator
  must execute — tests prove the code runs; validation observes that it does
  something meaningful.

---

## 2. Claim protocol — how "in progress" is signalled

`progress.md`'s `🚧` edit lives on a feature branch and is invisible on `main`
until merge, so it is **not** the mid-flight signal. The shared "this item is
taken" signal is the **pushed `<branch_prefix>NNN-*` branch** (config
`git.branch_prefix`, default `aide/`). `aide claim` owns this:

1. `git fetch --all --prune`; list remote `aide/*` branches.
2. Read the live queue (lowest-numbered open queue) + `progress.md`; pick the
   **first** item that is 📋, whose dependencies are all ✅, and that has no
   existing `aide/NNN-*` branch. With `loop.claim_scope = "all-open"` in
   `aide.toml`, claiming scans **every** open queue in number order instead —
   opt-in, because the one-queue scope is also the human-checkpoint boundary.
3. Create and push `aide/NNN-short-name` (push depends on `git.mode`; `local`
   mode does not push and so has no multi-machine claim signal).

One person (or one loop) owns an item at a time. Abandoning an item means
deleting its remote branch so the item returns to the pool; `aide check` flags a
claim branch whose item is already ✅ (stale claim), and `aide gc` deletes such
branches — local and remote — deterministically (dry-run by default, `--yes` to
act; `--merged` also collects branches already merged into main).

---

## 3. Command hygiene (canonical rules)

These rules keep shell commands robust, legible, and failure-localised on **any**
runtime — they hold whether or not a runtime has a permission model. This section
is the single canonical statement of the rules and their rationale; each
agent/command carries a short *positive-form primer* of the same rules so the
correct shape is in context up front (fewer wasted retries). How these rules are
**enforced**, and any provider-specific **command shaping** a permission policy
demands on top of them, are *adapter* concerns — see the adapter's README.

The rules (runtime-general):

- **If an `aide` verb covers it, the raw git form is wrong.** Session preflight
  (fetch, clean-tree check, landing on the right branch) is `aide sync
  [--item NNN]`; claiming is `aide claim`; landing is `aide merge`; branch
  clean-up is `aide gc`. Do not improvise the equivalent `git fetch`/`git
  status`/`git switch` sequences — the verbs exist so every run does these
  steps identically and no step is forgotten.
- **One command per call.** Never chain with `&&` or `;` — separate calls localise
  failures and keep each invocation legible.
- **No `cd` prefix and no directory-changing wrapper** (`git -C "<path>"`). The
  tool's working directory is already the repo root; both are redundant and brittle
  when the repo path contains spaces or apostrophes. Run the bare command.
- **No `2>&1`** or other redirections — the tool already captures stderr.
- **No command substitution in commits.** Avoid `$(…)`/backticks; use single-line
  `-m "msg"`, repeated `-m` for paragraphs, or `git commit -F <file>`.

The `aide` CLI always runs as `python .aide/scripts/aide.py <cmd>` — stdlib-only
and venv-independent, so it works before any project venv exists and identically
across runtimes.

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
