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

  Fill-in conventions: `{{slot}}` = literal value; _italic line_ = guidance to
  read then replace. Delete this comment in the generated file.
-->
# {{project-name}} — Progress Tracker

> **Status:** Draft v1 · **Created:** {{yyyy-mm-dd}}
> Step 3 of the AIDE loop. Single source of truth for status, per stage,
> deliverable, and acceptance criterion.

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

---

## Stage 0 — {{title}} — 📋

**Goal.** {{one line}}

**Deliverables.**

_Flat bullets only — one per deliverable, each with its item reference. See
`.aide/conventions.md` § format contract for the exact shape._

- 📋 {{deliverable}}. *(Item {{nnn}})*

**Acceptance.**

_One checkbox per acceptance criterion from the matching roadmap stage._

- [ ] {{acceptance check}}

---

_Repeat "## Stage N — Title — icon" per stage._

---

Next: run `/aide-create-queue` to generate the first batch.
