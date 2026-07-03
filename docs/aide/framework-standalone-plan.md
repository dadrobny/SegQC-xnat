# Plan: AIDE as a standalone, multi-provider framework repo

> **Status:** 📝 Draft — for review · **Created:** 2026-07-03
> Expands the deferred step 8 of [PR #21](https://github.com/dadrobny/SegQC-xnat/pull/21)
> (the standalone-framework refactor). Answers: *what is actually needed to
> install AIDE, how do `.aide/` and `.claude/` relate, what is provider-agnostic
> vs. Claude-specific, and how do we ship this as its own repo usable from other
> LLM runtimes?* Investigation-first; no extraction is performed unattended.

---

## 1. The packaging question, answered

The current README says the framework is "installed by copying `.aide/` + the
`.claude/` glue + writing one `aide.toml`." That is correct but **under-frames
the `.claude/` half** — it reads as optional "glue" when it is in fact the entire
control surface for the intended (Claude Code) workflow. AIDE is really **three
layers**, and an install needs all three:

| Layer | What it is | This repo | Depends on Claude? |
|---|---|---|---|
| **Engine** (provider-agnostic core) | The workflow concepts + the deterministic machinery every runtime shares | `.aide/conventions.md`, `.aide/templates/`, `.aide/scripts/aide.py`, the `docs/aide/` *formats*, the loop *decision logic* | **No** |
| **Adapter** (provider harness) | How one specific agent runtime *drives* the engine: role agents, workflow entry-points, orchestrators, permissions | all of `.claude/` **+** `loop.py`'s usage-probe | **Yes — 100% Claude Code** |
| **Project config** (per-repo) | This project's facts and living documents | `aide.toml`, `docs/aide/**` | No |

The key realisation: **`.aide/` is the engine, `.claude/` is the *Claude
adapter*.** They are co-equal halves of "the framework," not core + optional
extras. A different runtime (Cursor, Copilot, Gemini CLI, a raw SDK driver) would
**replace `.claude/` wholesale** while reusing `.aide/` unchanged. That is the
whole reason the engine was built as a stdlib CLI with no Claude coupling —
verified: `grep -i "claude\|anthropic" .aide/scripts/aide.py` → nothing.

So the README fix is a **reframe, not a correction**: install = **engine +
one provider adapter + project config**. §6 lands it.

---

## 2. Core vs. adapter — the exact inventory

Drawn from the actual tree, so the extraction in §5 is mechanical, not
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

A new repo, working name **`aide-loop`** (final name is an open decision, §7).
Structure makes the three-layer split *physical*:

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
│   ├── cursor/README.md            # porting guide (contract → Cursor primitives)
│   ├── copilot/README.md           # porting guide (→ .github/prompts, agents)
│   └── generic-sdk/                # a minimal, runnable non-Claude adapter (§4.2)
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
4. **The shared CLI invocation** — every adapter runs `python .aide/scripts/aide.py`.
   This is the contract's anchor: identical across providers.
5. **Optional** — permission pre-approval + logging (only runtimes that have a
   permission model; Claude Code does, most others don't).

### 4.2 Prove it with one non-Claude adapter

`adapters/generic-sdk/` — a **minimal but runnable** adapter (e.g. a thin Python
driver over any chat API, or Aider) that fulfils the contract without Claude
Code's skill/agent machinery. Building it to a working degree is the **only real
test** that `core/` is genuinely provider-agnostic; a spec with just Claude behind
it can silently smuggle in Claude assumptions. This is the highest-value item in
Phase C.

### 4.3 Porting guides (stubs, honest about gaps)

`adapters/{cursor,copilot}/README.md` map the contract to each runtime's
primitives and state what does **not** translate:

- **Cursor** — rules/commands, **no true sub-agents** → orchestrators become
  guided single-agent role-prompts; skills → `.cursor/commands/`.
- **Copilot** — `.github/prompts/` (commands), `.github/agents/` (limited
  agents); no permission allow-list.
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

## 5. Extraction sketch (history-preserving, reversible)

1. **Prove the split in-place first** (this repo, before any new repo exists):
   write `ADAPTER-SPEC.md` and the core/adapter refactor of `loop.py` **here**,
   validated against the working Claude adapter. If the contract can't describe
   the thing that already works, it's wrong — cheaper to learn now.
2. **Create `aide-loop`** with `git filter-repo` (or subtree) so `.aide/**` and
   the `aide-*` `.claude/**` files carry their commit history into `core/` and
   `adapters/claude/`. Clean-copy fallback if history-surgery on the shared paths
   is fiddly.
3. **Write `install.py`** + `--update`; dogfood by installing into a scratch repo
   and running `aide check` + one item end-to-end.
4. **Convert SegQC to a consumer** (§3.2): replace the in-tree framework with an
   `install.py` materialisation pinned to `VERSION`; confirm the full suite +
   `aide check` still green. This PR is where "did extraction break anything?" is
   answered.
5. **Only then** build the generic-sdk adapter (§4.2) and the porting stubs.

Reversible: until step 4 merges, SegQC still has its working in-tree copy; the new
repo is additive.

---

## 6. The immediate, in-this-PR fix

Independent of the whole extraction, one small correction belongs now, because it
addresses the exact confusion that prompted this plan: **reframe the README
install line** from "`.aide/` + `.claude/` glue" to "**engine (`.aide/`) + one
provider adapter (`.claude/` = Claude Code) + `aide.toml`**", and add a one-line
"Providers" note that the Claude adapter is the reference and others are portable
via the (coming) adapter contract. No structural change — just honest framing.
*(Also already done in this PR: removed the 11 empty, untracked `speckit-*` skill
dirs left behind by the earlier `git rm`.)*

---

## 7. Open decisions for you

1. **Repo name** — `aide-loop`? `aide-framework`? something else. (Plan uses
   `aide-loop` as a placeholder.)
2. **Extraction method** — history-preserving `git filter-repo` (more faithful,
   more effort) vs. clean copy with a pointer back to this repo's history
   (simpler). Recommend `filter-repo` for the engine, clean-copy tolerable for
   the adapter.
3. **How far to build the second adapter** — a runnable `generic-sdk` (best proof,
   more work) vs. porting-guide stubs only (cheaper, weaker guarantee). Recommend
   at least a minimal runnable one; it's the only true portability test.
4. **Scope of THIS PR** — land just the §6 README reframe here, and keep the
   extraction (Phases A–D) as a follow-up, or fold more in? Recommend: README
   reframe only here; extraction is its own repo + PR.
