<!--
  AIDE insight inbox — the compound-engineering capture point. Copy this file
  VERBATIM (comment included, no slots to fill) to docs/aide/insights.md the
  first time an insight needs a home.

  Any role, at any time: when you learn something true but OUT OF SCOPE for
  your current task, append ONE line here and return to your task. Capturing
  is cheap and always allowed; ACTING on it out of scope is forbidden.

  Entry shape (checked by `aide check`, non-blocking):
    - [ ] <type> — <one line> *(item NNN, YYYY-MM-DD)*     (item ref optional)
  Types:
    knowledge  — true fact worth documenting (docs, CLAUDE.md, conventions)
    defect     — something is wrong and needs a fix item
    gap        — something is missing and needs planning (roadmap/queue)
    automation — a recurring manual/agent action that deterministic code
                 could replace (a CLI verb, a script)
    framework  — belongs to AIDE itself, not this project; triage hands it
                 over to the framework repo ([framework] repo in aide.toml)

  Triage happens at the queue boundary (feedback loop): each entry is routed
  to its destination, then ticked in place with a pointer:
    - [x] <type> — <one line> *(item NNN, YYYY-MM-DD)* → <where it landed>

  Append-only: never rewrite, reorder, or delete existing lines.
-->
# Insight Inbox

_Entries below, newest last._

- [x] framework — `/aide-review-permissions` and `.claude/scripts/review_permissions.py` still tell the human to add promoted rules to `.claude/settings.json`, which is a *generated* artifact once `settings.overlay.json` is adopted; they should target `permissions.allow.add` in the overlay instead *(2026-07-22)* → fixed in aide-loop PR #8, shipped in engine 1.2.0 and installed here
- [ ] knowledge — a stage validation must resolve `[validation]` profiles per machine via `aide env --profile <name>` and record ❓ Unverified on a non-zero exit; never assume a capability from a previous run's result, which is local state and is deliberately not stored *(2026-07-22)*
- [ ] defect — `CLAUDE.md` links to `.aide/README.md` three times (lines 5, 170, 258) but the installer never creates that file: `.aide/` holds only `conventions.md`, `VERSION`, `templates/`, `scripts/`, `loop/`. The loop/agents/merge-policy content those links promise lives in aide-loop's own `README.md`, which a consumer does not receive — so either point them at `.aide/conventions.md` or have the framework install a `core/README.md` *(2026-07-23)*
- [ ] framework — `_parse_item_status` treats *every* "Item NNN" mention in `progress.md` as a status reference, inheriting whatever icon terminates the line (or the enclosing bullet), so prose that merely *discusses* an item is read as declaring its status: items 044/047 resolve to 🚧 because the environment-gated table's Notes cell name-drops them and ends "G3 stays 🚧", and items 060/070 resolve to planned via a Notes cell with no trailing icon and via `- [x]` acceptance checkboxes. That is what makes queue-005/006/007/008 warn "marked completed but still has open items". Restrict the parse to the documented `*(Item NNN)*` reference on a deliverable bullet *(2026-07-23)*
- [ ] defect — items 056, 062 and 064 have no `*(Item NNN)*` reference anywhere in `progress.md`: they shipped but were never wired to a deliverable bullet, so they read as planned forever, hold queue-006/007 open, and are invisible to the queue-planner. `aide progress set` now hard-errors on exactly this, so back-fill the references *(2026-07-23)*
- [ ] framework — 54 of `aide check`'s 60 warnings here are "status icon outside a structural status position" fired on narrative prose ("**G3 stays 🚧**"), which `conventions.md` §1 explicitly permits ("authors need not avoid the icon vocabulary in free text"). The warning fires precisely when the convention is being followed, and the noise buries the six substantive warnings — narrow it or drop it *(2026-07-23)*
- [ ] framework — no way to express a stage whose deliverables all shipped but whose *goal* was not met and is deliberately held open. Stage 14 (G3: real FPR ≤ 0.10, actual 0.975/1.0) is honestly 🚧 with every deliverable ✅, so the rollup warns "all deliverables ✅ but summary shows in-progress" permanently and the only way to silence it is to claim a success that did not happen. The deferred rework is not an existing deliverable, so no bullet can carry ⏸️ instead *(2026-07-23)*
