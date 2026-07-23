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
