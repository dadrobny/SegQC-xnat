### `queue-NNN.md`

- **Queue state is derived, not declared.** A queue is **open** iff any of its
  items is 📋/🚧 in `progress.md`, else **done**; "the live queue" is the
  lowest-numbered open one (`aide claim`'s default). A `> **Status:**` line is
  optional decoration for human readers — `aide queue tidy` stamps a completion
  note on superseded queues, and `aide check` warns only when a declared status
  contradicts the derived state. *(aide check, claim, queue tidy)*
- Work items as `### Item NNN: Short Title` + a description paragraph. Item
  numbers are **globally sequential across all queues** — never restart. *(aide
  check, scout/claim, spec-author)*
- **One queue is live at a time, deliberately.** The queue boundary is the human
  checkpoint — one review per batch — so the model offers no concurrency above
  the item level, and a roadmap cannot ask for it. Three senses of "parallel"
  get confused here — the first two are real and useful, the third is the one
  the model does not offer:
  - **Item independence within a queue** — supported: `aide claim` offers any
    unblocked item, so items may be worked in any order. Say this freely.
  - **Stage independence** — a scheduling *fact* ("Stage 19 needs nothing from
    Stage 17"), which tells a planner the two may be queued in either order, or
    merged into one batch if they fit the cap. Write it as independence, not as
    "run alongside": the planner will queue sequentially either way, and the
    softer phrasing only makes roadmap and queues appear to contradict.
  - **Concurrent live queues** — not offered. `loop.claim_scope = "all-open"`
    widens *claiming* across every open queue, but nothing creates a second live
    queue, and the one-queue scope is itself the checkpoint boundary.
