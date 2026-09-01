<!--
  AIDE insight inbox — the compound-engineering capture point. The engine
  creates docs/aide/insights.md from this file, byte for byte (comment
  included, no slots to fill), the first time `aide check`, `aide claim`,
  `aide queue start` or `aide insights list` finds it missing — no role copies
  it by hand.

  Any role, at any time: when you learn something true but OUT OF SCOPE for
  your current task, append ONE line here and return to your task. Capturing
  is cheap and always allowed; ACTING on it out of scope is forbidden.

  Entry shape (checked by `aide check`, non-blocking):
    - [ ] <type> — <one line> *(<where it came from>, YYYY-MM-DD, engine X.Y.Z)*

  The date is required; the provenance before it and the engine version after
  it are free-form and may be omitted. Conventional spellings, worth following
  so a reader can scan them:
    *(item 099, 2026-07-26)*        captured while working one item
    *(items 099-101, 2026-07-27)*   a finding that spans several
    *(queue-014, 2026-07-26)*       queue planning or spec-authoring, before
                                    any item exists
    *(2026-07-26)*                  no item or queue to name
    *(item 099, 2026-07-26, engine 1.22.0)*
                                    the engine it was observed under — one read
                                    of .aide/VERSION, and the date cannot stand
                                    in for it. Worth adding everywhere, and most
                                    of all on a `framework` entry, triaged in
                                    another repo months later.
  Write whichever is honest — never bend one to fit, since the line below is
  immutable and a squeezed provenance can never be corrected. For the same
  reason, never go back and add a version to an entry that has none.
  Types:
    knowledge  — true fact worth documenting (docs, CLAUDE.md, conventions)
    defect     — something is wrong and needs a fix item
    gap        — something is missing and needs planning (roadmap/queue)
    automation — a recurring manual/agent action that deterministic code
                 could replace (a CLI verb, a script)
    framework  — belongs to AIDE itself, not this project; triage hands it
                 over to the framework repo ([framework] repo in aide.toml)

  Triage routes each entry to its destination, then ticks it in place with a
  pointer:
    - [x] <type> — <one line> *(item NNN, YYYY-MM-DD, engine X.Y.Z)* → <where it landed>
  Triage happens at the queue boundary (feedback loop) for every type that
  lands in this project; a `framework` entry leaves for another repo's issue
  tracker and may be triaged on capture or on demand.

  The captured claim is IMMUTABLE — never reworded, reordered or deleted, not
  even when it turns out to be wrong (the wrongness is the record). Ticking the
  checkbox is the one in-place edit. Everything that happens to an entry AFTER
  triage goes in an appendable status trail: dated lines, indented under the
  entry, newest last.
    - [x] framework — <the original claim, never touched> *(2026-08-20)*
      - **2026-08-20** → aide-loop issue #50
      - **2026-10-11** → resolved in engine 1.16.0
-->
# Insight Inbox

_Entries below, newest last._
