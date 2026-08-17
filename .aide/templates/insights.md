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

  Append-only, with exactly two exceptions: ticking an entry's checkbox and
  appending its "→ where it landed" pointer, both at triage. Nothing else about
  a captured line may be rewritten, and no line is ever reordered or deleted.
-->
# Insight Inbox

_Entries below, newest last._
