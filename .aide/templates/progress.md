<!--
  AIDE progress template. Step 3. THE single source of truth for implementation
  status (item specs carry no status field). Parsed by aide.py (check, progress
  set) and scripts/aide_status_report.py — follow the shapes EXACTLY:
    - Stage summary table  | Stage | Title | Objectives | Status |  (Stage = int, Status = one icon)
    - Objective coverage   | Objective | Delivered by | Status |    (Objective starts with G<n>)
    - One "## Stage N — <title> — <icon>" section per stage, each with:
        Deliverables = FLAT bullets "- <icon> <text>. *(Item NNN)*"  (no nested status bullets)
        Acceptance   = "- [ ]" / "- [x]" checkboxes
  Rollup (aide progress + aide check enforce it): a stage is ✅ iff every
  Deliverables bullet is ✅ -> then its Acceptance boxes are [x] and its summary
  row / header / delivered objectives read ✅. Mixed -> 🚧. None started -> 📋.
  Update INCREMENTALLY; never reset a non-planned status back to 📋.
  Stage ✅ means "the planned work shipped", nothing more; a MEASURED goal the
  work cannot guarantee (an error-rate target, a benchmark) belongs in the
  optional "Outcome targets" table, which gates the Objective rows instead
  (an objective linked to a target that is not ✅ Met cannot roll up to ✅).

  Optional "Environment-Gated Capability Verification" section: include it
  ONLY if the project has ANY stage introducing a capability gated behind an
  optional package or external tool (GPU library, Docker, an optional pip
  extra, ...). It is deliberately OUTSIDE the stage-summary rollup above — a
  stage's ✅ still only requires its fallback/skip-clean path to pass; this
  table is a separate, additive visibility mechanism so a green suite is never
  mistaken for "the optional dependency was actually exercised." See
  conventions.md's Environment-Gated Capability Verification rule; omit this
  whole section if the project has no such capability.

  Fill-in conventions: `{{slot}}` = literal value; _italic line_ = guidance to
  read then replace. Delete this comment in the generated file.
-->
# {{project-name}} — Progress Tracker

> **Status:** Draft v1 · **Created:** {{yyyy-mm-dd}}
> Step 3 of the AIDE loop · mirrors [`roadmap.md`](roadmap.md) · the single
> source of truth for status; queue state is derived from it, and item specs
> deliberately carry none.

## Status legend

| Icon | Meaning |
|------|---------|
| 📋 | Planned |
| 🚧 | In Progress |
| ✅ | Complete |
| ⏸️ | Deferred |
| ❌ | Excluded |

## Stage summary

_One row per roadmap stage._

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | {{title}} | (foundation) | 📋 |

## Objective coverage

_One row per vision objective._

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 {{short}} | Stage 1 | 📋 |

## Environment-Gated Capability Verification  <!-- OPTIONAL: delete if not applicable -->

_One row per capability gated behind an optional package or external tool.
Status is `❓ Unverified` until a human or CI runner with the dependency
present actually exercises the gated path (not inferred from a skip-clean
pytest run), then `✅ Verified ({{yyyy-mm-dd}}, {{host/CI description}})`._

| Capability | Package / Tool | Introduced by | Status | Notes |
|------------|-----------------|----------------|--------|-------|
| {{capability}} | {{package or tool name}} | Stage {{n}} *(Item {{nnn}})* | ❓ Unverified | {{notes}} |

## Outcome targets  <!-- OPTIONAL: delete if no roadmap stage commits to a measured result -->

_One row per measured outcome the roadmap commits to (an empirical result —
an error rate, a benchmark — that shipped work enables but cannot guarantee).
Status is `❓ Unverified` until measured, then `✅ Met ({{yyyy-mm-dd}},
{{evidence}})` or `❌ Not met ({{measured result}} → {{follow-up}})`. A target
never holds its stage open — stages track shipped work — but an objective
linked to a target that is not ✅ Met cannot roll up to ✅. When marking a
target ❌ Not met, append a `- [ ] gap — …` insight in the same edit so the
feedback loop plans the follow-on work._

| Target | Objective | Attempted by | Status | Evidence / follow-up |
|--------|-----------|--------------|--------|----------------------|
| {{measurable target}} | G{{n}} | Stage {{n}} | ❓ Unverified | {{notes}} |

---

## Stage 0 — {{title}} — 📋

**Goal.** {{one line}}

**Deliverables.**

_Flat bullets only — one per deliverable, each with its item reference. See
`.aide/conventions.md` § format contract for the exact shape._

- 📋 {{deliverable}}. *(Item {{nnn}})*

**Acceptance.**

_One checkbox per acceptance criterion from the matching roadmap stage. Ticked
only by `aide progress accept <stage> --criterion N`, by whoever verified it —
never derived from the rollup. A stage may be ✅ with a box left unticked; when
it is, annotate the box with why._

- [ ] {{acceptance check}}

---

_Repeat "## Stage N — Title — icon" per stage._
