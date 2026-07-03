# AIDE — AI-Driven Engineering framework

A lean, standalone loop for driving a project from vision to shipped code with
fresh, role-scoped sub-agents and deterministic scripts for the mechanical parts.
Two principles govern everything: **lean over formal**, **token efficiency over
over-formal process** — deterministic work is scripted, only genuine reasoning is
spent on agents.

This directory is the **engine** — the provider-agnostic core, versioned
(`VERSION`) and naming no specific project. A full install is **three parts:
engine (`.aide/`) + one provider adapter + project config (`aide.toml`)**. The
*adapter* is what a specific agent runtime uses to drive the engine; for **Claude
Code** it is the `.claude/` directory (agents, skills, commands, `settings.json`,
hooks) — **required, not optional glue**. A different runtime (Cursor, Copilot,
Gemini CLI, a raw SDK driver) would replace `.claude/` wholesale while reusing
`.aide/` unchanged — the engine has zero Claude coupling by design. All project
facts live in `aide.toml` and `docs/aide/`.

> **Providers.** Claude Code is the *reference* adapter (the one built here).
> Porting to another runtime means re-expressing the `.claude/` control files
> (agents, skills, commands) in that runtime's format; the deterministic engine
> (`aide.py`) is shared unchanged. See `docs/aide/framework-standalone-plan.md`.

- **`conventions.md`** — the format contract, claim protocol, command hygiene,
  git modes, clarify mode. Read it; the loop assumes it.
- **`templates/`** — the mandatory-core document templates (vision, roadmap,
  progress, queue, item). Every section is annotated with its downstream consumer.
- **`scripts/aide.py`** — the stdlib-only CLI: `check`, `progress`, `queue`,
  `claim`, `merge`, `env`. Run as `python .aide/scripts/aide.py <cmd>`.
- **`loop/`** — the usage-gated supervisor for long unattended runs.

---

## The AIDE loop

Living documents under `docs/aide/`. Steps 1–3 are one-time; 4–6 repeat.

1. **create-vision** → `vision.md` (once)
2. **create-roadmap** → `roadmap.md` (once)
3. **create-progress** → `progress.md` (once)
4. **create-queue** → `queue/queue-NNN.md` — the next batch (one stage / small
   phase, ≤ `loop.queue_cap` items)
5. **create-item** → `items/NNN-*.md` — one testable spec
6. **execute-item** → tests + implementation + validation + merge; updates
   `progress.md`

Repeat 5–6 until the queue empties, then back to 4. The skills (`.claude/skills/
aide-*`) are pure markdown and run on any OS.

### Orchestrators (item ⊂ queue ⊂ roadmap)

Three nested commands. The invoking session is a light **orchestrator** that
spawns a sub-agent per leaf task and gates approvals — run it on **Sonnet**
(`/model sonnet` if needed).

- **`/aide-run-item NNN`** — one already-claimed item end-to-end: spec-author →
  test-writer → builder → validator+merge, with a ≤`loop.validation_rounds`
  build↔validate cycle.
- **`/aide-run-queue [NNN]`** — claims each item (`aide claim`) then runs it via
  `/aide-run-item`, until the queue empties. Does **not** create the next queue.
- **`/aide-run-roadmap`** — loops over queues: generate a queue → run it →
  generate the next, until the roadmap is exhausted. **Each new queue lands via a
  human-reviewed PR** — the batch checkpoint where a human reviews the plan once
  per ~10 items.

All three load each other **as skills in the same session** (prompt expansions,
not subprocesses). The only isolated contexts are the `Task` sub-agents doing the
leaf work. Git commits are the durable checkpoint, so a restart re-enters cleanly.

---

## Model routing by role (`.claude/agents/`)

Five sub-agents split work by role and cost; each pins a `model` and an `effort`
(as high as necessary, as low as adequate). Deterministic recon/claim is **not**
an agent — orchestrators call `aide claim`.

| Agent | Model | Effort | Role |
|---|---|---|---|
| `queue-planner` | Opus | xhigh | authors one queue batch (cascades into ~10 items) |
| `spec-author` | Opus | high | authors one item spec (cascades into 3 downstream agents) |
| `test-writer` | Sonnet | medium | writes AC + adversarial tests |
| `builder` | Sonnet (→Opus round 3) | medium | implements `source_dir` to satisfy every AC |
| `validator` | Sonnet | medium | quality gate: pytest, AC coverage, scope, vision fit; reconciles + merges |

`max` is reserved for genuinely intractable one-offs. No agent signs off its own
work; a fresh instance per item.

**Deterministic work is scripted, not delegated** — recon/claim, progress
reconciliation, queue tidy, merge+cleanup, venv check, and the consistency check
are `aide.py` subcommands. Agents keep only the reasoning: prioritisation, AC
design, test design, implementation, quality judgment.

---

## Merge policy

- **Work-item execution** may merge straight to `main` (no PR) once green —
  `aide merge` does it per `git.mode`. Still branch per item for the claim signal.
- **Framework / process changes require a reviewed PR**: `aide.toml`,
  `.aide/**`, `docs/aide/vision.md`, `docs/aide/roadmap.md`, `CLAUDE.md`,
  `.claude/skills|commands|agents/**`. They cascade into every future queue, so
  they need team agreement.

Rule of thumb: if the change alters a *future* queue/item, it needs a PR; if it
only *executes* the current item, merge it.

---

## Shared vs. personal

- **Shared (committed):** `.aide/` (minus loop.local.toml), `aide.toml`,
  `.claude/{agents,commands,skills,hooks,settings.json}`, `CLAUDE.md`,
  `docs/aide/` living documents.
- **Personal (git-ignored):** `.aide/loop/loop.local.toml`,
  `.claude/settings.local.json`, `docs/aide/permissions/*.jsonl`,
  `docs/aide/status/*.html`, credentials. Never commit credentials.

---

## Unattended long runs

`/aide-run-roadmap` pauses at each queue PR by design. For genuinely unattended
overnight runs, an **external supervisor** (`.aide/loop/loop.py`, configured by a
gitignored `loop.local.toml`) relaunches the gated command when usage limits
allow, relying on git commits + the resume logic for durable state. There is no
in-process headless nesting (an earlier `--continuous` design was removed — it
lost in-flight state on cutoff and stalled on prompts it couldn't answer).
