<!--
  AIDE queue template. Step 4. The next batch of work items — scoped to ONE
  cohesive roadmap unit (a single stage, or a small phase), capped at
  loop.queue_cap items, whichever is smaller. Parsed by aide.py (check, queue
  tidy), aide claim, and the status report.
  Mandatory shapes:
    - "> **Status:** Live" header line (exactly one queue is Live; superseded
      queues read "> **Status:** ✅ Completed — superseded by queue-NNN (date).")
    - Each item: "### Item NNN: Short Title" + a description paragraph.
  Item numbers are GLOBALLY SEQUENTIAL across all queues — never restart.
-->
# <Project> — Work Queue NNN

> **Status:** Live · **Created:** YYYY-MM-DD
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).

---

## Scope of this queue

<Which roadmap stage/phase this batch delivers, and the milestone it completes.>

**Prioritisation.** <Why these items, in this order; the critical path and what is
parallelisable.>

**Numbering.** Continues at the next free integer: **NNN–MMM**.

---

## Work items

### Item NNN: <Short Title>
<One paragraph: scope and deliverables for this item. End with a *Testable:*
sentence naming how it is verified locally.>

### Item NNN+1: <Short Title>
<…>

---

Next: `aide claim` picks the first unclaimed unblocked item, or run
`/aide-create-item NNN` to spec one.
