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
-->
# <Project> — Progress Tracker

> **Status:** Draft v1 · **Created:** YYYY-MM-DD
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

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | <Title> | (foundation) | 📋 |
| 1 | <Title> | G1 | 📋 |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 <short> | Stage 1 | 📋 |

---

## Stage 0 — <Title> — 📋

**Goal.** <one line>

**Deliverables.**
- 📋 <Deliverable, one flat bullet with its item ref.> *(Item 001)*
- 📋 <…> *(Item 002)*

**Acceptance.**
- [ ] <Acceptance check from the roadmap stage.>
- [ ] <…>

---

## Stage 1 — <Title> — 📋

**Goal.** <one line>

**Deliverables.**
- 📋 <…> *(Item 003)*

**Acceptance.**
- [ ] <…>

<!-- repeat per stage -->

---

Next: run `/aide-create-queue` to generate the first batch.
