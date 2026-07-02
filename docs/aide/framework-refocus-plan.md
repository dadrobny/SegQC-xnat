# Plan: AIDE as a lean, standalone framework

> **Status:** 📝 Draft — awaiting approval · **Created:** 2026-07-02
> Deliverable of [`framework-refocus-brief.md`](framework-refocus-brief.md).
> Read-only investigation of the current framework surface (orchestrators, six
> agents, eight skills, `.specify/` packaging, scripts/hooks, `CLAUDE.md`, the
> personal loop scripts). Nothing here is implemented yet — every step in §5
> lands via a reviewed PR.

Two principles govern every recommendation (from the brief):
**lean over formal** and **token efficiency over over-formal process**.

---

## 1. Workflow comparison — spec-kit vs. AIDE

AIDE already runs independently of spec-kit: the `/speckit-aide-*` skills are
pure markdown, call none of the `.specify/scripts/` PowerShell helpers, and the
only living artifacts are under `docs/aide/`. What remains of spec-kit is
packaging (`.specify/`, skill naming, frontmatter) and ten installed spec-kit
skills we never invoke.

### Capability map: adopt / adapt / drop

| spec-kit capability | Verdict | Rationale (token vs. formality) |
|---|---|---|
| `specify` (feature spec) | **Drop** | The AIDE item spec covers this at the right granularity; a second spec layer per feature is pure ceremony. |
| `clarify` (targeted clarification Qs) | **Adapt** | Don't keep the command; fold its one good idea into `spec-author`/create-item: when the queued one-liner is ambiguous, ask ≤3 targeted questions (or hand back) instead of guessing. Today this is implicit ("hand back rather than guessing") — spell it out. **Must not block automation:** a config/flag (`clarify = "interactive" \| "assume"`) lets unattended runs skip the prompt, pick the most reasonable default, and record it in a mandatory **Assumptions** block of the spec so a human can audit later (§2.4). |
| `plan` (implementation plan + design artifacts) | **Drop** | Roadmap (project altitude) + item Implementation Steps (item altitude) already plan at both levels. A third artifact would be re-derived context, i.e. token waste. |
| `tasks` (dependency-ordered task list) | **Drop** | The queue *is* the task list, with dependency ordering built into queue-planner's rules. |
| `analyze` (cross-artifact consistency check) | **Adapt as a script** | The idea is right, the execution wrong: consistency between progress/queue/items (numbering, statuses, orphans, stale claims) is deterministic — it should be `aide check` (§2.3), not an agent reading three documents. |
| `constitution` | **Adapt, minimally** | `.specify/memory/constitution.md` is still the unfilled upstream template — evidence it earns nothing here. The useful residue (a short list of project principles the validator checks "vision fit" against) already lives in `vision.md`. Drop the file; keep principles in vision/project config. |
| Template-enforced document structure (spec-kit's templates mandate sections) | **Adopt into the vision/doc templates** | Spec-kit's one structural virtue: required sections exist in every project because the template says so, not because the agent remembered. The redesigned `.aide/templates/` (§3.5) make the load-bearing sections **mandatory** — for vision: principles/constraints (what the validator checks against), out-of-scope, success criteria — and `aide check` verifies their presence, so every project the framework lands in gets them by construction. |
| `implement` | **Drop** | `execute-item` / `/aide-run-item` is the same step, better factored (fresh agents, independent validation). |
| `converge` (assess code vs. spec, append tasks) | **Drop (keep the pattern)** | The feedback-loop already encodes the same move: merged work that misses the mark becomes *corrective items in the next queue*. No new command needed. |
| `checklist` | **Drop** | Checklist generation per feature is formality with no consumer in this workflow. |
| `taskstoissues` | **Drop** | Solo/small-team, items live in files; GitHub-issue mirroring is overhead. Revisit only if a team adopts issue tracking. |
| `agent-context` extension | **Drop** | Its job (regenerate an agent-context section) is superseded by the project-config design in §3 — one config file agents read directly, nothing to regenerate. |
| `.specify/` machinery (scripts, templates, workflows, catalogs, integration manifests) | **Drop** | ~30 files of scaffolding nothing invokes. The pinned `specify` CLI dependency disappears with it. |
| Fresh-chat-per-step discipline | **Adopt (already have)** | Carried over and improved: fresh *sub-agent* per task inside one orchestrator session. |
| Versioned, shareable packaging (`extension add`) | **Adapt** | The one genuinely good spec-kit idea for us: the framework should be a self-contained, versioned directory that drops into any project. §3 replaces `specify extension add` with a plain copy-in `.aide/` directory — no CLI, no catalog. |

**Net:** nothing in spec-kit needs to be *added* to AIDE as a step. Two ideas
survive as adaptations (clarify-before-spec convention; `analyze` reborn as a
deterministic `aide check` script), one as packaging inspiration.

---

## 2. Gap analysis

### 2.1 Under-specified or drifting pieces (spell out / fix)

1. **The item-spec template exists in two divergent versions.** The
   `create-item` skill mandates a heavyweight "Testing Prerequisites (CRITICAL)"
   section (Docker services, ports, env vars, health checks — upstream AIDE
   boilerplate irrelevant to a CPU-only Python library), while `spec-author`
   prescribes a leaner section list. **One template file** (framework-owned,
   §3), with the services boilerplate demoted to an optional block the project
   config enables. Payoff: every spec-author run stops paying for and emitting
   an unused checklist.
2. **Command-hygiene rules are copy-pasted 9×** (six agents, three
   orchestrators, `CLAUDE.md`) — proven drift risk. Most of the section exists
   only because agents run raw multi-step git; once the git mechanics move into
   the `aide` CLI (§2.3) the section shrinks to a few lines, kept in **one**
   framework doc that agent specs reference.
3. **Stale `--continuous` references** survive the mode's removal:
   [`create-queue` SKILL.md](../../.claude/skills/speckit-aide-create-queue/SKILL.md)
   ("in `--continuous` it pushes your commit to `main`") and
   [`watch_and_resume.bat`](../../watch_and_resume.bat) ERR path (`claude
   "/aide-run-roadmap --continuous"`). Fix during migration; symptom of §2.1.2.
4. **Misleading packaging metadata.** Skills carry
   `compatibility: Requires spec-kit project structure with .specify/ directory`
   (false) and `speckit-aide-*` names for a framework that doesn't use
   spec-kit. Rename to `aide-*`, drop the frontmatter claims.
5. **The progress.md / queue format is a de-facto contract with no spec.**
   `aide_status_report.py` already parses stage tables, status icons, item rows;
   scout/validator/planner edit them by prose instruction. Write the format down
   once (framework doc) and have `aide check` enforce it — the precondition for
   every script in §2.3.
6. **Project specifics are baked into framework prose**: `src/segqc/`,
   `tests/`, `.venv` bootstrap commands, "CPU-only, cross-platform", vision
   G-codes appear inside agent specs, skills, and `CLAUDE.md`. This is the main
   extraction target → project config (§3).
7. **The branch/push/merge policy is hardcoded** in validator, scout, and the
   orchestrators (direct-merge to `main`, push claim branches, delete after
   merge) with no way to run PR-gated or offline. → §3.3.
8. **Claim protocol edge cases are unstated**: what happens to a claim branch
   when an item is abandoned mid-run is documented for humans (delete the remote
   branch) but no agent or script owns it; `aide check` should flag claim
   branches whose item is ✅ or stale.

### 2.2 What's missing entirely

- **A project-config document** (the framework↔project seam). §3.2.
- **A merge-mode switch.** §3.3.
- **Cross-OS loop scripts as framework citizens.** Today: a Windows-only
  personal `.bat` (with the §2.1.3 bug) + `check_usage.ps1`; the `.sh`
  counterpart it claims to port doesn't exist in the repo. §3.4.
- **A consistency checker** (`aide check`) — the deterministic replacement for
  both spec-kit `analyze` and validator's manual "progress is consistent"
  cross-reading.

### 2.3 Deterministic agent work → scripts (the token-efficiency core)

Precedent already proves the model: `aide_status_report.py` (614 lines,
tested, deterministic) replaced what would otherwise be an agent re-reading
every document per report. Apply the same move to the loop's hot path. All of
these become subcommands of **one** CLI (`aide.py`, §3.1) so a single
allow-rule covers them and agents can't drift on invocation shape.

| Candidate | Today | Proposal | Payoff |
|---|---|---|---|
| **Scout (recon + claim)** | A Haiku agent spawn per item: fetch, `git branch -r`, read queue + progress, pick first unclaimed unblocked 📋, create + push branch | `aide claim [--queue NNN]` — fully deterministic once the format contract (§2.1.5) exists | Eliminates an entire agent per item (~10–30k tokens each, plus spawn latency and prompt-stall risk). The `scout` agent is **retired**; orchestrators call the script. Biggest single win. |
| **progress.md reconciliation** | builder hand-edits its row to 🚧; validator hand-edits row + acceptance checkboxes + stage rollup — each edit means reading the ~300-line file into context and getting a 3-way rollup rule right | `aide progress set NNN in-progress\|done` (auto pull-rebase, row flip, checkbox tick, stage/objective rollup, commit) | Removes the most error-prone mechanical edit in the loop (the "recurring staleness failure mode" the validator doc itself names). Validator keeps the PASS/FAIL *judgment*; loses the file surgery. |
| **Queue tidying** | queue-planner prose-edits the superseded queue's status line + item states | `aide queue tidy NNN` | Small per-run, but removes a whole class of planner instructions and keeps queue history mechanically consistent. |
| **Merge + branch cleanup** | validator runs 6 git commands (switch/pull/merge/push/branch -d/push --delete) as separate calls, with safety prose around each | `aide merge NNN` — honours the merge-mode config (§3.3), re-runs the test command, deletes the claim branch | Collapses the longest command sequence in any agent; the merge-mode switch gets exactly one implementation point. |
| **venv staleness check/bootstrap** | Prose instructions repeated in CLAUDE.md + agents ("try import, else rebuild") | `aide env` (checks/bootstraps per project config) | Minor tokens, major consistency; worktree-venv rule enforced in code. |
| **Consistency check** | Validator step 5 reads progress/spec/queue and cross-references by eye; nothing checks numbering or stale claims | `aide check` (format contract, sequential numbering, one live queue, claim-branch↔status agreement) | Run at loop start and pre-merge; converts a recurring judgment task into a boolean. |
| **Kept with agents** (explicitly *not* scripted) | — | queue-planner, spec-author, test-writer, builder, validator verdicts, feedback-loop | These are genuine reasoning: prioritisation, AC design, test design, implementation, quality judgment. Model/effort routing table carries over unchanged (minus scout). |

### 2.4 Workflow options to build in (human-focus vs. unattended)

Two modes the current framework implies but never names; both become explicit
and cheap:

- **Clarify without blocking.** Spec authoring is where human input pays most,
  but a question mid-unattended-run is a stall. So clarification gets a mode
  switch (`aide.toml` default, overridable per invocation): `interactive` —
  spec-author asks ≤3 targeted questions before writing; `assume` — it picks
  the most defensible default and records each one in a mandatory
  **Assumptions** section of the item spec, which the validator surfaces in its
  report and the human can audit at the queue boundary. Unattended runs default
  to `assume`; nothing ever hangs waiting for input.

- **Spec-first batch pass ("front-load the human").** A natural rhythm for a
  reviewed-but-automated flow: after a queue lands, spec **all** its items in
  one interactive sitting (clarify questions answered while a human is
  present), then let implementation run unattended, then review the merged
  results. There is **no structural roadblock**: `/aide-run-item` already
  skips spec-authoring when a complete spec exists, so pre-authored specs make
  the execution loop composable as-is. What it needs is a name and two rules:
  - A skill/command, `/aide-spec-queue [NNN]` — loops spec-author (in
    `interactive` mode) over every unspecced item in the queue, committing all
    specs on **one branch/PR** (a second human checkpoint mirroring the
    queue PR), rather than on per-item claim branches. Claim branches are then
    created at execution time as today.
  - A dependency caveat the template states: a spec written before its
    dependencies are *implemented* must pin interfaces as **assumptions**
    (same Assumptions block), and the builder/validator hand back if reality
    diverged — keeping spec-first optional, not mandated.

  The `create-queue` skill's "Next step" section and queue-PR body suggest it:
  *"spec the whole queue now (`/aide-spec-queue`) or spec per-item during
  execution."*

Secondary effect: `.claude/settings.json` shrinks — one
`Bash(python .aide/scripts/aide.py:*)`-style allow rule replaces a dozen
git-shape rules agents currently depend on, and the permission-prompt attack
surface for unattended runs drops with it. The `aide` CLI stays
**stdlib-only and venv-independent** (it must run before/without the project
venv and inside any project).

---

## 3. Proposed standalone-framework design

### 3.1 Directory layout

```
<project>/
├── .aide/                          # THE FRAMEWORK — project-agnostic, copy-in, versioned
│   ├── README.md                   #   the workflow guide (absorbs CLAUDE.md's framework half)
│   ├── VERSION
│   ├── conventions.md              #   format contract (§2.1.5), claim protocol, command hygiene (once)
│   ├── templates/                  #   vision / roadmap / progress / queue / item templates
│   ├── scripts/
│   │   ├── aide.py                 #   single CLI: claim · progress · queue · merge · env · check · status · permissions
│   │   └── tests/                  #   the CLI is tested like aide_status_report.py is today
│   └── loop/
│       ├── loop.py                 #   usage-gated supervisor (absorbs check_usage + watch_and_resume logic)
│       ├── watch_and_resume.ps1|.sh|.bat  # thin one-line wrappers → python loop.py
│       └── loop.local.toml.example
├── aide.toml                       # PROJECT CONFIG — the only file edited when adopting AIDE
├── docs/aide/                      # LIVING DOCUMENTS — unchanged location, unchanged formats
├── .claude/
│   ├── agents/                     # 5 agents (scout retired), project words replaced by aide.toml refs
│   ├── commands/                   # aide-run-item / -queue / -roadmap / -review-permissions
│   ├── skills/aide-*/              # renamed from speckit-aide-*, de-spec-kit-ed
│   ├── hooks/log_permission_event.py
│   └── settings.json               # slimmed allow-list (§2.3) + unchanged ask-gates
└── CLAUDE.md                       # thin: project intro + pointer to .aide/README.md + aide.toml
```

`.specify/` is deleted (§4). The framework is "installed" by copying `.aide/`
+ `.claude/` glue and writing `aide.toml` — no CLI, no catalog, no pinned
`specify` version. When it stabilises, `.aide/` can be extracted to its own
repo and pulled in per-project (plain copy or `git subtree`); v1 deliberately
stays in-repo but is structured for that extraction.

### 3.2 The three-way split

| Layer | Lives in | Examples |
|---|---|---|
| **Framework** (reusable, project-agnostic) | `.aide/` (minus config), `.claude/agents\|commands\|skills\|hooks` | orchestrators, agents, templates, `aide.py`, loop scripts, conventions doc |
| **Project config** (committed, per-repo) | `aide.toml`, `docs/aide/**`, thin `CLAUDE.md`, path-scoped `settings.json` rules | source/tests paths, test command, venv layout, merge mode, vision/roadmap/progress |
| **Personal / machine** (gitignored) | `.aide/loop/loop.local.toml`, `docs/aide/permissions/log*.jsonl`, `docs/aide/status/`, `.claude/settings.local.json` | usage caps, stop-after deadlines, credentials, logs, generated HTML |

`aide.toml` (TOML: stdlib-parseable via `tomllib`, human-readable, terse) is
the single seam. Sketch:

```toml
[project]
name = "SegQC-xnat"
source_dir = "src/segqc"
tests_dir = "tests"
docs_dir = "docs/aide"          # default; scripts derive queue/items/… from it

[python]
venv = ".venv"
bootstrap = "pip install -e .[dev]"
test_command = ".venv/Scripts/python -m pytest"   # per-OS resolved by aide.py

[git]
mode = "auto-merge"             # auto-merge | pr | local   (§3.3)
main_branch = "main"
branch_prefix = "aide/"

[loop]
queue_cap = 10
validation_rounds = 3
clarify = "assume"              # interactive | assume   (§2.4)
```

Agents get project facts one of two ways, both cheap: `aide.py` consumes the
values inside its subcommands (most cases — agents never see the paths), and
agent specs replace literal `src/segqc/` mentions with "the `source_dir` from
`aide.toml`" (agents Read the ~20-line file when they genuinely need a path).
No generation step, nothing to regenerate or drift.

### 3.3 Branch/push/merge opt-out

One config key, `git.mode`, enforced **only inside `aide claim` / `aide
merge`** — agent and orchestrator instructions stay identical across modes:

- **`auto-merge`** (default — current behaviour): claim branch pushed at claim
  time; on validator PASS, `aide merge` direct-merges to `main`, re-runs tests,
  deletes the claim branch. Zero added friction for the solo/prototype case.
- **`pr`**: claim identical; on PASS, `aide merge` pushes the branch and stops
  with "open a PR" (or opens a draft PR if `gh` is available — `gh pr create`
  stays `ask`-gated, so this is a natural human checkpoint). The queue-PR
  checkpoint already works this way; `pr` mode extends the same gate to items.
- **`local`**: no pushes at all (offline / no-remote prototyping). Claim is a
  local branch only — the config documents that this disables the
  multi-machine claim signal; merge is local into `main`.

Deliberately **not** configurable: the fresh-agent-per-item isolation, the
queue-as-checkpoint PR, the single-source-of-truth rule for `progress.md`, the
3-round validation cap default. Every knob must earn its keep; these are the
framework's identity.

### 3.4 Cross-OS looping scripts

Collapse `watch_and_resume.bat` + `check_usage.ps1` into one
**`loop.py`** (stdlib `urllib` for the OAuth usage endpoint — the endpoint
logic in `check_usage.ps1` ports 1:1), because Python is the one runtime every
AIDE project already has:

- Reads personal knobs from gitignored `.aide/loop/loop.local.toml`
  (`max_weekly_pct`, `daily_reserve_pct`, `max_session_pct`, `stop_after`,
  `interval`, credentials path) — the committed `.example` documents them.
- Same decision loop as today: RUN → `claude "/aide-run-roadmap"`; WAIT until
  the 5-hour window resets; STOP on the weekly ceiling / deadline; ERR → run
  once to re-auth. Fixes the `--continuous` leftover on the ERR path.
- Thin `watch_and_resume.ps1` / `.sh` / `.bat` wrappers (one line each:
  `python .aide/loop/loop.py "$@"`) so "double-click / one command on any OS"
  still works.
- The framework ships the scripts; the *config* is personal — matching the
  brief's framework/personal split and legitimising what is currently an
  untracked root-level `.bat`.

### 3.5 Document templates: redesign, don't transplant

The `.aide/templates/` are **designed fresh**, not lifted from the current
skill prose — the current layouts grew by accretion (upstream AIDE boilerplate
+ per-project patches) and §2.1.1 shows what that produces. Design rules:

- **Every section earns its place** — for each template, state (in a template
  comment) what downstream consumer reads the section: the validator, a script
  parser, the queue-planner, or a human checkpoint. A section with no consumer
  is deleted, not carried.
- **Mandatory core, optional extensions.** Mandatory sections are the ones
  agents/scripts depend on (vision: principles/constraints, out-of-scope,
  success criteria; item: description, AC, assumptions, decisions; progress:
  the §2.1.5 machine-parseable status tables). Project-specific blocks
  (services/deployment checklists, dataset notes) are opt-in via `aide.toml`.
- **Concise but specific** — templates model the target register: short
  declarative sections, no restated context, no filler prose; specificity goes
  into AC and constraints, not narrative length.
- **Parse-friendly by construction**: status icons, item headings, and tables
  follow the format contract so `aide check` / `aide progress` / the status
  report parse them without heuristics.

Consequence for this repo: the existing `docs/aide/` documents **may be
regenerated against the new templates rather than preserved byte-for-byte**.
Breaking the current project's workflow mid-stream is acceptable — recreate
vision/roadmap/progress from the new templates (content carried over,
structure new) and restart the loop from the current stage. This simplifies
migration (§4) considerably: the format contract only has to serve the new
templates, not also every historical layout.

---

## 4. Migration sketch

Ground rule: **`docs/aide/` keeps its paths**, but per §3.5 the living
documents are **regenerated against the new templates** rather than preserved
byte-for-byte — content (stages, statuses, decisions, item history) carries
over; structure follows the new format contract. Everything below lands via
reviewed PRs (per the existing merge policy).

1. **Additive first.** Introduce `.aide/` (README, conventions, templates,
   `aide.py`, loop) and `aide.toml` alongside the existing framework. Nothing
   references them yet → zero breakage risk while the CLI grows its tests.
2. **Rewire consumers.** Point agents/orchestrators at `aide.py` subcommands
   and `aide.toml` values; retire `scout`; slim the hygiene sections to a
   reference to `.aide/conventions.md`. The loop is behaviourally identical
   (same claims, same merges) — only the mechanics move.
3. **Rename skills** `speckit-aide-*` → `aide-*` (content re-based on the §3.5
   templates, minus spec-kit frontmatter, the stale `--continuous` text, and
   the Testing-Prerequisites boilerplate now living in the shared item
   template), and add the new `/aide-spec-queue` (§2.4). Update the references
   in `CLAUDE.md`, orchestrators, and agent specs in the same PR. Solo team →
   clean rename, no alias period.
3b. **Regenerate the living documents** from the new templates (vision,
   roadmap, progress; queues/items regenerated only if the format contract
   requires it — closed queues may be left as history with a pointer). One PR,
   reviewed against the old documents to confirm no content was lost; the loop
   restarts from the current stage afterwards.
4. **Slim `CLAUDE.md`.** Framework half (loop description, claim protocol,
   merge policy, routing table, hygiene) moves to `.aide/README.md` /
   `conventions.md`; `CLAUDE.md` keeps the project intro, venv specifics, and
   pointers. `settings.json`: swap the agent-facing git-shape rules for the
   `aide.py` rule; keep all `ask` gates (update the constitution path out).
5. **Delete `.specify/`** after a reference sweep (known referents: skill
   frontmatter `source:` lines — gone with the rename; `CLAUDE.md` and
   settings `ask` entries for `constitution.md` — updated in step 4; the
   constitution template is unfilled, nothing to preserve).
6. **Verify with the framework itself:** run `aide check`, the full test suite
   (CLI tests + existing project tests), then one real item end-to-end through
   `/aide-run-item` in each git mode (`auto-merge` on a scratch item; `pr` and
   `local` on a throwaway branch) before calling the migration done.

Rollback story: steps are separable PRs; until step 5 the old and new surfaces
coexist, so any step can be reverted independently.

## 5. Sequenced implementation plan

Each step is one reviewable PR, ordered so the loop keeps working throughout.
(These are framework changes — per the merge policy they do **not**
direct-merge.)

| # | Step | Contents | Done when |
|---|---|---|---|
| 1 | **Skeleton + config + template redesign** | `.aide/` layout, `README.md` stub, `conventions.md` v1 (format contract §2.1.5, claim protocol, hygiene), `aide.toml`, templates designed fresh per §3.5 (mandatory core incl. vision principles/out-of-scope/success criteria and the item Assumptions block; every section annotated with its consumer) | `aide.toml` parses; templates + format contract reviewed; no behaviour change |
| 2 | **`aide.py` core** | `check`, `progress set`, `queue tidy` subcommands + tests (stdlib-only, cross-platform) | tests green; `aide check` passes against current `docs/aide/` |
| 3 | **`aide.py` git layer** | `claim`, `merge`, `env` honouring `[git]`/`[python]` config incl. all three modes + tests | dry-run + scratch-repo tests green in all modes |
| 4 | **Rewire agents & orchestrators** | scout retired; builder/validator/planner call `aide.py`; hygiene sections → one reference; `settings.json` allow-list slimmed | one real item runs end-to-end via `/aide-run-item` with no permission stalls |
| 5 | **Skills rename + de-spec-kit + workflow options** | `speckit-aide-*` → `aide-*`, frontmatter/drift fixes (§2.1.3–4), references updated; clarify mode (`interactive`/`assume` + Assumptions block) wired into spec-author; new `/aide-spec-queue` skill (§2.4) | `/aide-create-queue` etc. invocable; grep finds no `speckit-aide` refs; a queue can be batch-specced then executed unattended |
| 5b | **Regenerate living documents** | vision/roadmap/progress re-issued from the new templates (content carried, structure new; closed queues kept as history) | side-by-side review confirms no content lost; `aide check` green; loop resumes from the current stage |
| 6 | **Loop scripts** | `loop.py` + 3 wrappers + `loop.local.toml.example`; delete root `watch_and_resume.bat` / `check_usage.ps1` | supervised run gates correctly against live usage numbers on Windows; wrappers lint on macOS/Linux (best-effort until a second OS is available) |
| 7 | **Slim CLAUDE.md + delete `.specify/`** | migration steps 4–5 above | fresh-clone smoke test: clone → read CLAUDE.md → run one item |
| 8 | *(optional, later)* **Extract `.aide/` to its own repo** | subtree/copy-in packaging, VERSION discipline | a second project adopts it by copy + `aide.toml` |

Steps 1–3 are pure additions (safe to build while normal queue work continues);
4–7 are the cut-over; 8 waits until the framework has survived a few queues.

---

### Open questions for the reviewer

1. **CLI invocation shape:** `python .aide/scripts/aide.py <cmd>` (zero
   install) vs. a console-script `aide <cmd>` (nicer, but needs an install step
   and per-venv wiring). Plan assumes the former for leanness.
2. **Skill rename timing:** clean break (step 5) assumes no other
   machine/branch is mid-queue during cut-over — acceptable solo; flag if not.
3. **`pr` mode ambition:** stop-at-push (leanest) vs. auto-open a draft PR via
   `gh` when available. Plan proposes stop-at-push with draft-PR as a config
   nicety, since `gh pr create` is `ask`-gated anyway.
