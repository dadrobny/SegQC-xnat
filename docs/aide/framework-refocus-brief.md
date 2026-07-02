# Brief: Harmonise & re-focus the AIDE workflow into a lean standalone framework

> **Purpose:** handover brief for a downstream agent. The single deliverable is a
> **plan document** that forms the basis for building a re-focused, standalone
> AIDE framework. Investigate read-only first; present the plan for approval
> before any implementation.

## Context

This project uses **AIDE** (an AI-Driven Engineering loop) currently packaged as an
**extension of spec-kit / `specify`**, living under `.specify/` (pinned to
`0.11.7.dev0`), `.claude/skills/speckit-aide-*`, `.claude/agents/`, and
`.claude/commands/aide-run-*`. In practice AIDE runs **independently of spec-kit** —
the `/speckit-aide-*` commands are pure markdown and call no spec-kit scripts.

Working style this framework must serve:

- **Solo or very small teams**, often one person.
- **Prototype / research development**, not production or highly complex systems.
- AIDE works well as-is; the goal is refinement, not a rewrite.
- spec-kit's full formality (`specify`, `plan`, `tasks`, `analyze`, `clarify`,
  `constitution`, etc.) is **too verbose/high-overhead** for this use case — but
  some of its steps or structure may still carry ideas worth keeping.
- The current loop **automates git branching, pushing, and direct-merging to
  `main`** (see the merge policy and the scout→spec-author→test-writer→builder→
  validator agent chain). This is great for unattended automation but assumes a
  solo/main-merging model.

## Guiding mindset

Two principles govern every recommendation:

1. **Lean over formal.** Prefer fewer, clearer moving parts over spec-kit-style
   ceremony. Every added step, doc, or option must justify its overhead; when in
   doubt, cut.
2. **Token efficiency over over-formal process.** Wherever a choice trades agent
   tokens against process formality, favour the token-efficient path *unless* the
   formality earns its keep. Deterministic or boilerplate work should not consume
   agent reasoning; verbose scaffolding that a script or a terse convention could
   replace is waste. Optimise for the fewest tokens that still produce correct,
   reviewable outcomes.

## Objectives

1. **Compare** the high-level workflows of spec-kit and our AIDE adaptation.
   Identify which spec-kit skills/scripts/documents/agents correspond to gaps in
   AIDE — what AIDE is missing, what it does implicitly that should be **spelled
   out**, and which spec-kit steps are worth adopting vs. dropping as overhead.
2. **Find under-specified or missing pieces** in the current AIDE
   documents/agents/skills — ambiguities, unstated conventions, and options that
   simply aren't built in yet.
3. **Add configurability without exploding complexity.** Concretely, the automated
   branch/push/merge behaviour needs an **optional switch to disable** it (e.g. for
   more mature projects where merging to `main` unattended is undesirable — PR-only,
   or no-push modes). Default should remain the current low-friction automation.
4. **Identify deterministic work currently handed to agents that should instead be
   scripts** — the core of the token-efficiency mindset. Candidates to evaluate:
   scout's git recon + claim-branch creation, `progress.md` reconciliation, queue
   tidying/status-line updates, branch cleanup, staleness/venv checks. Move
   deterministic, token-wasting steps to scripts; keep genuine reasoning with agents.
5. **Re-package as a lean, standalone framework** — not a spec-kit extension, since
   we don't use spec-kit directly. Requirements:
   - **Project-independent:** the framework must not reference *this* project. All
     project-specific content (currently baked into `CLAUDE.md`, agent specs, paths
     like `src/segqc/`, the `.venv` bootstrap) moves into **dedicated project-config
     document(s)** that the framework references.
   - **Cross-platform & easily runnable:** include the **continuous-looping
     scripts** (important for running on personal Claude subscriptions/usage limits)
     with **user-specific configs**, designed to run on any OS — e.g. separate entry
     scripts per platform (`.ps1`/`.sh`/`.bat`) or an OS-agnostic launcher.

## Constraints & guardrails

- **Keep it automatable and lean**, per the guiding mindset above.
- **Preserve what works:** the fresh-agent-per-item isolation, the
  queue-as-checkpoint model, permission-aware command hygiene, and the
  single-source-of-truth conventions (`progress.md` for status) should carry over.
- Separate cleanly: **framework** (reusable, project-agnostic) vs. **project
  config** (this repo's specifics) vs. **personal/machine** (git-ignored:
  usage-limit loop configs, credentials).

## First-read file list (start grounded)

Read these before proposing anything — they are the current framework surface:

**Orchestration & agents**
- `.claude/commands/aide-run-item.md`, `aide-run-queue.md`, `aide-run-roadmap.md` —
  the nested orchestrators (item ⊂ queue ⊂ roadmap), incl. the continuous-loop
  design and human-checkpoint model.
- `.claude/agents/scout.md`, `queue-planner.md`, `spec-author.md`, `builder.md`,
  `test-writer.md`, `validator.md` — the six routed sub-agents (model/effort split,
  hard limits, command-hygiene rules). **Prime candidates for the "deterministic
  work → script" analysis**, especially `scout` (pure git recon/claim).

**Skills (the pure-markdown AIDE steps)**
- `.claude/skills/speckit-aide-create-vision/`, `create-roadmap/`,
  `create-progress/`, `create-queue/`, `create-item/`, `execute-item/`,
  `feedback-loop/`, `status-report/` — SKILL.md in each. Compare against the
  spec-kit skills below.

**spec-kit side (for the comparison)**
- `.specify/extensions/aide/` — `README.md`, `CHANGELOG.md`, `extension.yml`,
  `commands/`, `templates/` (how AIDE is currently packaged as an extension).
- `.specify/` root — `init-options.json`, `extensions.yml`,
  `extension-catalogs.yml`, `integration.json`, `workflows/`, `templates/`,
  `scripts/`, `memory/constitution.md` — the spec-kit machinery we largely bypass.
- The installed spec-kit skills (`speckit-specify`, `plan`, `tasks`, `analyze`,
  `clarify`, `constitution`, `implement`, `converge`, `checklist`,
  `taskstoissues`) — assess adopt / adapt / drop.

**Scripts & automation already delegated (the token-efficient precedent)**
- `scripts/aide_status_report.py` (+ `tests/test_aide_status_report.py`) — a
  deterministic doc→HTML summariser; the model for "script, not agent".
- `.claude/hooks/log_permission_event.py` — PreToolUse/PostToolUse permission
  logger.
- `.claude/scripts/review_permissions.py` (+ `.claude/commands/aide-review-permissions.md`)
  — ranks permission prompts into suggested allow-rules.

**Governing conventions & living documents**
- `CLAUDE.md` — the full team workflow: the AIDE loop, claim protocol, **merge
  policy (PR vs. direct-merge)**, model-routing table, approval/permission policy,
  command-hygiene rules, and the `.venv` bootstrap. **This is where project-specific
  content is currently entangled with framework content — the main extraction
  target.**
- `docs/aide/vision.md`, `roadmap.md`, `progress.md`, `queue/`, `items/`,
  `status/`, `permissions/`, `dataset-verse19.md` — the living documents the
  framework operates on (these must keep working across the migration).

## Expected output — a plan document

The single deliverable is a **plan document that forms the basis for building the
new framework** (read-only investigation first; no framework code applied
unattended). It must contain:

1. **Workflow comparison** — spec-kit vs. AIDE, mapping each spec-kit capability to
   *adopt / adapt / drop* with a one-line rationale (flagging token-vs-formality
   trade-offs).
2. **Gap analysis** — what to spell out clearer, which documents/options are
   missing, and which deterministic agent tasks should become scripts (with the
   expected token/complexity payoff).
3. **Proposed standalone-framework design** — directory layout; the split between
   framework / project-config / personal docs; the branch/push/merge opt-out
   design; and the cross-OS looping-script scheme. Kept deliberately minimal.
4. **Migration sketch** — how to extract from the spec-kit-extension packaging to
   the standalone framework without breaking the existing `docs/aide/` living
   documents.
5. **Sequenced implementation plan** — ordered, reviewable steps to build the
   framework from this plan, so it can drive the actual work.

Present the plan document for approval before any implementation — this is a
framework-level change and should land via review, not unattended.
