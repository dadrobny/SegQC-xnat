<!--
  AIDE queue template. Step 4. The next batch of work items — scoped to ONE
  cohesive roadmap unit (a single stage, or a small phase), capped at
  loop.queue_cap items, whichever is smaller. Parsed by aide.py (check, queue
  tidy), aide claim, and the status report.
  Mandatory shapes:
    - Each item: "### Item NNN: Short Title" + a description paragraph.
  Queue state (open/done) is DERIVED from progress.md — no status field is
  needed; "the live queue" is simply the lowest-numbered queue with open items.
  A "> **Status:**" note (e.g. the one `aide queue tidy` stamps on completion)
  is decorative, for human readers only.
  Item numbers are GLOBALLY SEQUENTIAL across all queues — never restart.

  Fill-in conventions: `{{slot}}` = literal value; _italic line_ = guidance to
  read then replace. Delete this comment in the generated file.
-->
# {{project-name}} — Work Queue {{nnn}}

> **Created:** {{yyyy-mm-dd}}
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).

---

## Scope of this queue

_Which roadmap stage/phase this batch delivers, and the milestone it completes._

**Prioritisation.** {{why these items, in this order; the critical path and
what is parallelisable}}

**Numbering.** Continues at the next free integer: **{{nnn}}–{{mmm}}**.

---

## Work items

_One "### Item NNN: Title" section per item — add as many as this batch needs
(see `loop.queue_cap` in `aide.toml`)._

### Item {{nnn}}: {{short title}}

{{one paragraph: scope and deliverables for this item}}. *Testable:*
{{how it is verified locally}}.

---

Next: `aide claim` picks the first unclaimed unblocked item, or run
`/aide-create-item NNN` to spec one.
