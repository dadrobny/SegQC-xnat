# Plan: AIDE as a standalone, multi-provider framework repo

> **Status:** 📝 Draft — for review · **Created:** 2026-07-03 · **Updated:** 2026-07-07
> Motivation and a concrete, reversible plan to lift the AIDE framework out of
> this repo into a standalone, multi-provider repository — with SegQC-xnat as its
> first consumer. Records the exact core/adapter boundary, the target repo shape,
> the language/platform dependencies, and the extraction steps.
> Investigation-first; no extraction is performed unattended.

---

## 1. Motivation and the three-layer model

AIDE currently lives *inside* this repo, hand-maintained in-tree. The goal is to
lift it into its own repository so any project — and eventually any LLM runtime —
can install it and pull updates, while SegQC-xnat becomes its **first consumer**
rather than its owner. This document records the motivation, the exact
core/adapter boundary, and a concrete, reversible plan to get there.

A working install is **three layers**, and it needs all three:

| Layer | What it is | This repo | Depends on Claude? |
|---|---|---|---|
| **Engine** (provider-agnostic core) | The workflow concepts + the deterministic machinery every runtime shares | `.aide/conventions.md`, `.aide/templates/`, `.aide/scripts/aide.py`, the `docs/aide/` *formats*, the loop *decision logic* | **No** |
| **Adapter** (provider harness) | How one specific agent runtime *drives* the engine: role agents, workflow entry-points, orchestrators, permissions | all of `.claude/` **+** `loop.py`'s usage-probe | **Yes — 100% Claude Code** |
| **Project config** (per-repo) | This project's facts and living documents | `aide.toml`, `docs/aide/**` | No |

The load-bearing distinction: **`.aide/` is the provider-agnostic engine,
`.claude/` is the *Claude adapter*.** They are co-equal halves of "the framework,"
not core + optional glue. A different runtime (Cursor, Copilot, Gemini CLI, a raw
SDK driver) **replaces `.claude/` wholesale** while reusing `.aide/` unchanged.
The engine was deliberately built as a stdlib CLI with no Claude coupling to make
this possible — verified: `grep -i "claude\|anthropic" .aide/scripts/aide.py` →
nothing.

---

## 2. Core vs. adapter — the exact inventory

Drawn from the actual tree, so the extraction in §6 is mechanical, not
guesswork.

### 2.1 Provider-agnostic engine (moves to `core/`, unchanged)

- `.aide/conventions.md` — format contract, claim protocol, command-hygiene,
  git/clarify modes. *(Command-hygiene is the one section with a mild Claude
  tint — "the permission allow-list" — but the rules themselves, one command per
  call etc., are runtime-general; see §4.3.)*
- `.aide/templates/` — five markdown templates. Pure content.
- `.aide/scripts/aide.py` (+ `tests/`) — **the shared engine.** Zero Claude
  coupling. `check`, `progress set`, `queue tidy`, `claim`, `merge`, `env`. Every
  adapter calls this identically.
- `.aide/loop/loop.py` — **decision loop is core; the usage-probe is not** (§4.4).
- The `docs/aide/` document *shapes* (parsed by `aide.py`) and the seven workflow
  *steps* (vision→roadmap→progress→queue→item→execute→feedback).

### 2.2 Claude-specific adapter (moves to `adapters/claude/`)

- `.claude/agents/*.md` (5) — sub-agent specs with `model:`/`effort:`
  frontmatter. **Claude Code's agent format**, Claude model names.
- `.claude/skills/aide-*/SKILL.md` (9) — the workflow steps as Claude Code
  skills. **Claude Code's skill format.**
- `.claude/commands/aide-run-*.md`, `aide-review-permissions.md` (4) — slash-
  command orchestrators. **Claude Code's command format.**
- `.claude/settings.json` — permission allow/ask-list + hook registration.
  **Claude Code's permission model.**
- `.claude/hooks/log_permission_event.py`, `.claude/scripts/review_permissions.py`
  — permission logging/review. **Claude Code hook API.**
- `loop.py`'s probe: `USAGE_URL`, the `~/.claude/.credentials.json` OAuth token,
  the default `claude "/aide-run-roadmap"` command. **Anthropic-subscription
  specific** (already config-overridable — good seam).

### 2.3 Project config (stays in the consuming repo, never in the framework)

- `aide.toml`, `docs/aide/vision|roadmap|progress|queue|items`, and the
  project-specific `.gitignore` block.

---

## 3. Standalone-repo design

A new repo named **`aide-loop`**. Structure makes the three-layer split
*physical*:

```
aide-loop/                          # the framework repo
├── core/                           # LAYER 1 — provider-agnostic engine
│   ├── conventions.md
│   ├── templates/                  # vision, roadmap, progress, queue, item
│   ├── scripts/aide.py  + tests/
│   ├── loop/loop.py     + tests/   # decision loop + a pluggable usage-probe
│   └── VERSION
├── adapters/
│   ├── ADAPTER-SPEC.md             # the CONTRACT every adapter fulfils (§4.1)
│   ├── claude/                     # LAYER 2 — the reference adapter (complete)
│   │   ├── agents/  skills/  commands/  hooks/
│   │   ├── settings.json
│   │   ├── usage_probe.py          # the Anthropic OAuth probe, lifted out of loop.py
│   │   └── README.md               # AIDE-concept → Claude-Code-primitive map
│   ├── copilot/                    # second adapter — future work (§4.2)
│   ├── cursor/README.md            # porting stub (contract → Cursor primitives)
│   └── gemini/README.md            # porting stub (→ .gemini/commands)
├── docs/  (quickstart.md · concepts.md)
├── install.py                      # cross-OS installer (§3.2)
└── README.md  · LICENSE
```

### 3.1 What "install into a project" produces

`python install.py --adapter claude --into <target-repo>`:

1. copies `core/` → `<target>/.aide/`
2. copies `adapters/claude/{agents,skills,commands,hooks,settings.json}` →
   `<target>/.claude/` (**non-clobbering merge** — never overwrite an existing
   `settings.json`; emit a `.aide-merge` diff for the human instead)
3. copies `adapters/claude/usage_probe.py` → `<target>/.aide/loop/`
4. scaffolds `<target>/aide.toml` from a template (prompts for `source_dir`,
   `test_command`, `git.mode`)
5. appends the framework `.gitignore` block if absent
6. records the installed `VERSION` in `aide.toml` for later `install.py --update`

Stdlib-only, so it runs on any OS with the Python the engine already needs.
`--update` re-copies `core/` (engine is owned by the framework) but **never**
touches `docs/aide/` or `aide.toml` (owned by the project) — the same
core-vs-config boundary, enforced by the installer.

### 3.2 This repo becomes the first *consumer*

SegQC-xnat currently *owns* the framework in-tree. Post-extraction it **consumes**
it: `.aide/` and the `aide-*` parts of `.claude/` are re-materialised by
`install.py` pointing at the `aide-loop` repo (pinned to a `VERSION`), instead of
being hand-maintained here. The living documents (`docs/aide/**`) and `aide.toml`
stay. This is the acid test that the extraction preserved a working install.

---

## 4. Multi-provider generality

Claude is the **reference** adapter (fully built, proven). Generality is real —
not aspirational — **because the deterministic 80% (`aide.py`) is already shared
and provider-neutral.** Porting to a new runtime is re-expressing ~18 markdown
control files in that runtime's format; the git/document/merge logic does not
move.

### 4.1 The adapter contract (`ADAPTER-SPEC.md`)

An adapter must provide, in whatever form its runtime uses:

1. **Seven workflow entry-points** — the AIDE steps. Claude Code expresses them
   as *skills*; Cursor/Copilot/Gemini as *commands/prompts*; a raw SDK as prompt
   files + a driver.
2. **Five role definitions** mapped to **capability tiers**, not model names, so
   each adapter binds tiers to its own models:

   | Role | Tier | Why |
   |---|---|---|
   | queue-planner | **T3 (strongest)** | one plan cascades into ~10 items |
   | spec-author | **T3** | the item's single source of truth |
   | test-writer / builder / validator | **T2 (mid)** | well-scoped against a fixed spec/tests |
   | *(recon/claim)* | **none — it's `aide claim`** | deterministic, not an agent |

   Claude binds T3→Opus, T2→Sonnet, recon→(retired). A runtime without
   sub-agents degrades gracefully to "fresh chat per role" guidance.
3. **Three orchestrators** (item ⊂ queue ⊂ roadmap) — or, where a runtime can't
   nest prompt-expansions, a manual runbook that calls the same `aide.py` steps
   in the same order.
4. **The shared CLI invocation** — every adapter invokes the aide CLI (today
   `python .aide/scripts/aide.py`). This is the contract's anchor: identical
   across providers, and implementation-agnostic (§5.3).
5. **Optional** — permission pre-approval + logging (only runtimes that have a
   permission model; Claude Code does, most others don't).

### 4.2 The second adapter: GitHub Copilot (future work)

The first non-Claude adapter targets **GitHub Copilot** — `.github/prompts/` for
the seven workflow entry-points, `.github/agents/` for the five role definitions,
and no permission allow-list (Copilot has none). Building it to a working degree
is the **only real test** that `core/` is genuinely provider-agnostic: a contract
with just Claude behind it can silently smuggle in Claude assumptions, and a
second concrete runtime is what flushes them out.

This is **explicitly future work — the next step after extraction lands**, not
part of the initial extraction. Sequencing it after SegQC becomes a consumer (§6)
keeps the first PR focused on "did extraction preserve a working install?" before
generality is exercised for real.

### 4.3 Porting guides (stubs, honest about gaps)

`adapters/{cursor,gemini}/README.md` map the contract to each runtime's
primitives and state what does **not** translate:

- **Cursor** — rules/commands, **no true sub-agents** → orchestrators become
  guided single-agent role-prompts; skills → `.cursor/commands/`.
- **Gemini CLI** — `.gemini/commands/`.

The command-hygiene section's "permission allow-list" framing is Claude-specific
and moves into the Claude adapter README; `core/conventions.md` keeps only the
runtime-general rules (one command per call, no `cd`, no chained `&&`).

### 4.4 The loop's usage-probe is the one core/adapter seam to cut

`loop.py` today hardwires Anthropic's OAuth usage endpoint. Split it:

- **`core/loop/loop.py`** keeps the RUN/WAIT/STOP_WEEKLY/ERR decision loop,
  deadlines, relaunch, and a **probe interface** (`get_usage() -> {...}` or
  `None`).
- **`adapters/claude/usage_probe.py`** implements the Anthropic OAuth probe.
- Config `[loop] usage_probe = "anthropic-oauth" | "none"` selects it; `none`
  falls back to a plain time-cadence relaunch (works for any provider / any
  subscription that lacks a usage API).

Small refactor, already eased by `command`/`credentials_path` being config today.

---

## 5. Language dependence: Python in the engine

The engine is Python end to end — `aide.py` (CLI), `loop.py` (supervisor),
`install.py` (installer), and the Claude hooks are all stdlib Python 3.11+ — and
every adapter, whatever its runtime, shells out to `python .aide/scripts/aide.py`.
So a consuming project needs a Python interpreter on the machine even when its own
code is in another language. Worth being explicit about what that buys and what
dropping it would cost.

### 5.1 Reasons to rely on Python

- **Usually already present.** The interpreter is a given for Python projects
  (this repo included) and near-universal on developer/CI machines; for the common
  case it costs nothing to require.
- **Stdlib-only, zero install.** `aide.py` imports nothing outside the standard
  library, so the engine runs on a stock interpreter with no dependency
  resolution — the reason it works *before* the project venv exists.
- **Cross-platform for free.** One `aide.py` behaves identically on
  Windows/macOS/Linux; the shell-script alternative would need per-OS variants and
  careful quoting.
- **Legible contribution surface.** The deterministic logic (TOML parse, git
  plumbing, markdown-section edits) stays readable to the people most likely to
  extend it.

### 5.2 What full Python-independence would cost

- The realistic path to "no interpreter at all" is a **compiled single binary** —
  reimplement `aide.py`'s subcommands in Go/Rust, or freeze with
  PyInstaller/Nuitka, and ship per-OS binaries. That adds a build-and-release
  matrix and, for a rewrite, a second language to maintain.
- Only the executable triad (`aide.py`, `loop.py`, `install.py`) plus the two
  Python hooks would move; `conventions.md` and the templates are already
  language-neutral markdown.
- Net: **moderate effort, low near-term payoff** — it matters only for adopters
  with no Python whatsoever, which is neither this repo nor most LLM-tooling
  environments. Defer until a real no-Python consumer actually appears.

### 5.3 Platform independence without Python

If the aim is "no Python dependency," not "no interpreter of any kind," the move is
smaller than a full rewrite, because the adapter contract (§4.1) anchors on
*invoking the aide CLI*, not on how it is implemented:

- Reimplement the ~six subcommands (`check`, `progress`, `queue`, `claim`,
  `merge`, `env`) as a compiled binary exposing the identical CLI surface. Every
  adapter's "run the aide CLI" step becomes a drop-in substitution — `aide check`
  in place of `python .aide/scripts/aide.py check` — with no change to any adapter.
- Replace the two Python hooks with the target runtime's native hook mechanism
  (they are Claude-adapter-local anyway, §2.2).
- Templates, conventions, and document formats carry over unchanged.

So platform independence is a bounded, mechanical swap; full *language*
independence (§5.2) is the larger, lower-value undertaking. Both stay deferred
until a consumer actually needs them.

---

## 6. Extraction sketch (clean copy, reversible)

1. **Prove the split in-place first** (this repo, before any new repo exists):
   write `ADAPTER-SPEC.md` and the core/adapter refactor of `loop.py` **here**,
   validated against the working Claude adapter. If the contract can't describe
   the thing that already works, it's wrong — cheaper to learn now.
2. **Create `aide-loop` by clean copy**, not history surgery: copy `.aide/**`
   into `core/` and the `aide-*` `.claude/**` files into `adapters/claude/`, and
   leave a pointer in the new repo's README back to this repo's history for
   provenance. (History-preserving `git filter-repo` was considered and rejected —
   more effort than the faithful-history payoff is worth for a fresh framework
   repo.)
3. **Write `install.py`** + `--update`; dogfood by installing into a scratch repo
   and running `aide check` + one item end-to-end.
4. **Convert SegQC to a consumer** (§3.2): replace the in-tree framework with an
   `install.py` materialisation pinned to `VERSION`; confirm the full suite +
   `aide check` still green. This PR is where "did extraction break anything?" is
   answered.
5. **Only then, as follow-on work,** build the GitHub Copilot adapter (§4.2) and
   the remaining porting stubs.

Reversible: until step 4 merges, SegQC still has its working in-tree copy; the new
repo is additive.
