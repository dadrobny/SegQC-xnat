# ADAPTER-SPEC — the contract every AIDE adapter fulfils

> The AIDE install is **three layers**: the provider-agnostic **engine** (`.aide/`),
> a provider **adapter** (for Claude Code, `.claude/`), and per-repo **project
> config** (`aide.toml`, `docs/aide/`). This document is the **contract between the
> engine and an adapter** — what a runtime must express, in its own primitives, to
> drive the engine. It is engine-level (provider-neutral): the Claude adapter is
> the reference implementation, not the definition. See `README.md` for the loop
> and `conventions.md` for the format/claim/hygiene rules an adapter inherits
> unchanged.

An adapter is a translation layer, not a rewrite. The deterministic 80% —
git/document/merge/env logic — already lives in `scripts/aide.py` and is invoked
identically by every runtime. An adapter re-expresses only the ~18 markdown
control files (entry-points, roles, orchestrators) plus, optionally, a permission
policy and a usage probe. Nothing below re-implements engine logic.

A conforming adapter provides all of §1–§4; §5–§6 are optional and only apply to
runtimes whose feature set supports them.

---

## 1. Seven workflow entry-points

The AIDE loop is seven steps (README §"The AIDE loop"). An adapter exposes each as
whatever its runtime uses to launch a scoped unit of work — Claude Code uses
*skills* (`.claude/skills/aide-*`), Cursor/Copilot/Gemini use *commands/prompts*,
a raw SDK uses prompt files + a driver.

| # | Step | Produces | One-time? |
|---|---|---|---|
| 1 | create-vision | `docs/aide/vision.md` | once |
| 2 | create-roadmap | `docs/aide/roadmap.md` | once |
| 3 | create-progress | `docs/aide/progress.md` | once |
| 4 | create-queue | `docs/aide/queue/queue-NNN.md` | repeats |
| 5 | create-item | `docs/aide/items/NNN-*.md` | repeats |
| 6 | execute-item | tests + code + validation + merge; updates `progress.md` | repeats |
| 7 | feedback-loop | process/document improvements | as needed |

Every entry-point reads and writes the documents in the **exact shapes** fixed by
`conventions.md` §1 (so `aide.py` parses them) and uses the **status icons** and
**rollup rule** defined there. These formats are engine-owned; an adapter must not
redefine them.

## 2. Five role definitions, bound to capability *tiers*

The work is split across five fresh, role-scoped sub-agents. The contract names
**capability tiers**, not models — each adapter binds a tier to one of its own
runtime's models (as high as necessary, as low as adequate). No role signs off its
own work; a fresh instance per item.

| Role | Tier | Why the tier |
|---|---|---|
| queue-planner | **T3 (strongest)** | one plan cascades into ~10 items |
| spec-author | **T3** | the item spec is its single source of truth, cascading into 3 downstream roles |
| test-writer | **T2 (mid)** | well-scoped against a fixed spec |
| builder | **T2** (may escalate to **T3** on a late retry) | implements `source_dir` against a fixed spec + tests |
| validator | **T2** | quality gate against fixed AC; reconciles + merges |

Recon/claim is **not a role** — it is deterministic (`aide claim`), so no agent and
no tier. The Claude reference binds **T3→Opus, T2→Sonnet** (builder→Opus on its
third attempt), with `max` reserved for intractable one-offs. A runtime without
sub-agents degrades gracefully to "a fresh chat per role" guidance — the roles and
their tiers still hold.

## 3. Three orchestrators (item ⊂ queue ⊂ roadmap)

The nested drivers that sequence the roles. Where a runtime can nest
prompt-expansions (Claude Code loads them as skills in one session), express them
that way; where it cannot, a **manual runbook** that calls the same `aide.py` steps
in the same order satisfies the contract.

- **run-item** — one already-claimed item end-to-end: spec-author → test-writer →
  builder → validator+merge, with a ≤`loop.validation_rounds` build↔validate cycle.
- **run-queue** — `aide claim` each item, then run-item it, until the queue empties.
  Does **not** create the next queue.
- **run-roadmap** — generate a queue → run it → generate the next, until the
  roadmap is exhausted. **Each new queue lands via a human-reviewed checkpoint**
  (for Claude, a PR) — one human review per ~10 items.

Git commits are the durable checkpoint, so a restart re-enters cleanly regardless
of how the orchestrator is expressed.

## 4. The shared CLI invocation (the contract's anchor)

Every adapter invokes the **same deterministic CLI** for all mechanical work —
recon/claim, progress reconciliation, queue tidy, merge+cleanup, venv check, the
consistency check:

```
python .aide/scripts/aide.py {check, progress, queue, claim, merge, env}
```

This is the anchor that makes generality real rather than aspirational: it is
identical across providers and **implementation-agnostic** — a future compiled
`aide` binary exposing the same subcommands is a drop-in substitution (`aide check`
for `python .aide/scripts/aide.py check`) with no change to any adapter. Adapters
never re-implement these subcommands.

---

## 5. Optional: permission pre-approval + logging

Only runtimes with a permission model provide this; most do not. The Claude adapter
supplies a permission allow/ask-list (`settings.json`), a `PreToolUse`
command-hygiene guard, and permission logging/review. The **command-hygiene rules**
themselves (one command per call, no `cd`, no chained `&&`, no `2>&1`) live in
`conventions.md` §3 and are runtime-general; only the *enforcement mechanism* and
the "permission allow-list" framing are adapter-local. A runtime with no permission
model simply omits this section and relies on the hygiene rules being followed.

## 6. Optional: usage probe (unattended long runs)

The engine's supervisor (`loop/loop.py`) gates unattended relaunches on real usage
numbers via a **pluggable probe** — the one core/adapter seam in the loop:

- **Engine (`loop/loop.py`)** owns the RUN/WAIT/STOP_WEEKLY decision loop,
  deadlines, and relaunch. It contains no provider specifics.
- **Adapter (`usage_probe.py`, installed next to `loop.py`)** implements
  `get_usage(cfg) -> dict | None` — the raw usage document (`five_hour`/`seven_day`
  utilisation + `resets_at`) the engine interprets, or `None` when it can't be read.
- **Config** `[loop] usage_probe` selects it: the Claude adapter ships
  `"anthropic-oauth"` (the OAuth usage endpoint); `"none"` ships no probe and the
  loop relaunches on a plain time cadence — the graceful default for any runtime or
  subscription without a usage API.

An adapter for a runtime with no usage endpoint sets `usage_probe = "none"` and
ships no probe file; the contract is still satisfied.

---

## Conformance checklist

- [ ] Seven workflow entry-points, each honouring the `conventions.md` document shapes.
- [ ] Five roles bound to T3/T2 tiers (recon/claim left to `aide claim`).
- [ ] Three orchestrators (or a manual runbook calling the same `aide.py` steps in order).
- [ ] Every mechanical action routed through `python .aide/scripts/aide.py …`.
- [ ] *(if the runtime has one)* a permission policy enforcing `conventions.md` §3.
- [ ] *(if unattended runs are wanted)* a `usage_probe.py`, or `usage_probe = "none"`.
