### Human gates (optional, additive)

A **decision only a person can make**, blocking work until they make it. A
`## Human gates` section in `progress.md`, one row per gate:

```
| Gate | Blocks | Status | Decision / evidence |
|------|--------|--------|---------------------|
| Golden-file retirement approved | 106 | ⏳ Awaiting | — |
| Real segmenter output available | stage 21 | ⏳ Awaiting | — |
```

- **Blocks** — item numbers (any §1 reference form, or bare: `106`,
  `110, 111`, `106–108`), `stage N`, or `all`.
- **Status** — table-local vocabulary, like Outcome targets': `⏳ Awaiting`,
  then `✅ Approved (date)` or `❌ Declined (date)`.

**Why not an acceptance box.** Those are observable checks *of the built thing*
— something completing the deliverables can guarantee. A steering decision is
not that, and overloading the checkboxes would repeat exactly the conflation
Outcome targets were introduced to avoid. Gates get their own table for the
same reason.

**Reach is per gate, and never a queue.** A queue is an *incidental* batch
boundary — part of a stage, one stage, or several small ones — so "the live
queue" names different work from one week to the next while the decision has
not changed. Blocking is tied to the units that mean something:

| Blocks | Reaches | Use when |
|---|---|---|
| `106`, `110, 111`, `106–108` | exactly those items | the decision affects one thread; the queue keeps producing other work |
| `stage N` | every item that stage's deliverables reference, resolved live | the decision could *invalidate* a stage's work, so racing ahead is waste to throw away |
| `all` | every item, everywhere | a programme-level stop — sign-off, budget, legal |

`stage N` resolves through `progress.md` each time it is read, so a gate's reach
follows the roadmap as the stage's contents change rather than freezing a list
written when the gate was raised. Only the person who knows what the pending
decision might change can judge which reach applies, so the table asks them.

**Where a gate is raised, and where it lives.** Same split as Outcome targets:
raised wherever it is noticed, recorded in one place.

- **`roadmap.md`** — a stage whose work needs a decision or an out-of-band
  prerequisite says so in its own section. This is the usual home for a gate
  known at planning time, and it naturally implies `Blocks: stage N`.
- **`items/NNN-*.md`** — a gate discovered while specifying one item is noted
  in its Validation or Assumptions block, implying `Blocks: NNN`.
- **`progress.md`** — the **authoritative row**, always. It is the single source
  of truth for status and the only place the CLI reads, so a gate that exists
  only as prose in a roadmap or a spec blocks nothing.

**Any role may raise a gate; only a person may resolve one.** Creating a blocker
is safe — the worst case is work pausing for a human — so an agent noticing that
a decision is needed should add the row and say so. Removing one is not safe,
and no agent may run `aide gate approve`/`decline`: a gate exists precisely
because the decision is not derivable from the work, so an agent resolving it
destroys the only thing it was protecting.

**A declined gate keeps blocking.** It is resolved — someone decided — but the
decision was "no", so releasing the work would run exactly what was refused.
The remedy is to re-plan: drop the blocked items, or change what the gate asks.
Only `✅ Approved` opens a gate; an unrecognised status blocks too, so a typo
in the mark cannot silently open one.

Semantics *(aide claim, check, status, gate)*:

- **`aide claim` will not offer a blocked item**, and reports the gate as the
  reason rather than an unexplained "none left".
- **`aide check` warns** on every gate still blocking — a normal state, not a
  defect; the point is that it is visible instead of buried in a spec's prose.
- **`aide status`** prints them, like Outcome targets.
- **Resolving is a CLI operation**, never a hand edit:
  ```
  aide gate (list | approve <n> | decline <n>) [--evidence "…"]
  ```

Agents *read* gates — to know why they must stop — and stop.
