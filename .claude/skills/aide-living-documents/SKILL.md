---
name: aide-living-documents
description: Load before writing a living AIDE document (item spec, queue, progress, roadmap, vision, insights) — the shapes aide.py parses (conventions §1).
user-invocable: false
paths:
  - "**/progress.md"
  - "**/roadmap.md"
  - "**/vision.md"
  - "**/insights.md"
  - "**/queue/*.md"
  - "**/items/*.md"
---

<!-- reach: spec-author, queue-planner
     Literal, not measured: this body is preloaded into exactly the agent
     specs whose `skills:` frontmatter names `aide-living-documents` — the two
     roles that write a living document. As a `paths:` rule it armed on
     every spawn (29 and 24 arms in two measured sessions, issue #85),
     because reading an item spec matches the same globs as writing one; the
     `paths:` above inject nothing on a read (issue #85, measured): the
     description sits in every interactive session's skill listing regardless,
     and the globs only narrow when the runtime auto-invokes the skill on its
     own. The four roles that write none of the shape-parsed documents are
     deliberately not listed — the one line they do append, the insight entry,
     has its shape on the floor in `AGENT-CONTEXT.md`. `tests/test_structural_budget.py` compares this line to the `skills:`
     lists. -->

<!-- triggers: all
     The interactive half, declared so the glob evaluator stays on an
     assertion path: the roles whose named reads match the `paths:` above —
     what a rule with these globs would arm, and what the loop no longer
     pays. Every role names an item spec or `insights.md`, so: all. -->

<!-- pins: .aide/conventions/1-format-contract/status-icons.md
     Quoted from that section; `test_rule_pins.py` fails if either copy moves
     alone. One block per section file, so seven blocks follow.
     - 📋 Planned
     - 🚧 In Progress
     - 🔍 In Review
     - ✅ Complete
     - ⏸️ Deferred
     - ❌ Excluded
     - a table row's Status (last) cell, a stage header's trailing `— <icon>`,
       and the leading icon of a deliverable bullet
     - An icon anywhere else — prose, mid-bullet, a title — is plain text and
       is never read as status
-->

<!-- pins: .aide/conventions/1-format-contract.md
     - a literal value to substitute
     - authoring guidance to read then replace
-->

<!-- pins: .aide/conventions/1-format-contract/progress.md
     - ticked only by `aide progress accept` — never derived
-->

<!-- pins: .aide/conventions/1-format-contract/items.md
     - An acceptance criterion is an invariant over the resulting content
     - never a bound on the diff that produced it
-->

<!-- pins: .aide/conventions/1-format-contract/human-gates.md
     - Resolving is a CLI operation, never a hand edit
-->

<!-- pins: .aide/conventions/1-format-contract/insights.md
     - Capture is a plain append; everything after it has a verb
     - Ticking the checkbox is the one in-place edit
     - The open inbox is an input to queue authoring, not only an output of
       triage
     - considered, and either queued or explicitly passed over — never
       silently dropped
-->

<!-- pins: .aide/conventions/5-clarify-mode.md
     - Root documents are authored through their loop entry point,
       interactively — whatever `loop.clarify` says
     - Do not write a root document directly, however well the template shape
       is known
     - ask until the mandatory sections are grounded in their answers, and
       never fill **Guiding principles**, **Out of scope**, or **Success
       criteria** from assumption
-->

# Living-document shapes

`.aide/scripts/aide.py` parses these files by exact shape. `.aide/conventions.md`
§1 is the source of truth and carries one file per shape (`§1 → progress.md` is
`conventions/1-format-contract/progress.md`, and so on); this file is **delivery,
not a second source of truth**, and carries only the shape rules — the durable
artifact, insight-immutability and human-gate rules are in `AGENT-CONTEXT.md`,
already in this context.

It is preloaded into the two roles that write a living document —
`spec-author` and `queue-planner` — so it is in context before the first
write, and an interactive session
sees its description in the skill listing, with the `paths:` above keeping the
runtime's own invocation of it to work on one of these files. The globs match
by document name rather than by `project.docs_dir`, so they hold whatever a
consumer configured.

**The six status icons, and nothing else:** 📋 Planned · 🚧 In Progress ·
🔍 In Review · ✅ Complete · ⏸️ Deferred · ❌ Excluded. They are read at
**structural positions only** — a table row's **Status (last) cell**, a stage
header's **trailing** `— <icon>`, and the **leading** icon of a deliverable
bullet. An icon anywhere else — prose, mid-bullet, a title — is plain text and
is never read as status.

**`{{slot}}` is a literal value to substitute; an _italic line_ is authoring
guidance to read then replace.** `aide check` flags any `{{…}}` surviving into a
generated document as an unfilled slot, so guidance must never be written as a
slot.

**Prefer the verb to a hand edit**: `aide progress set`, `aide progress accept`,
`aide queue tidy`, `aide gate`. Acceptance boxes are **ticked only by
`aide progress accept` — never derived**, and the one hand edit anyone makes in
`progress.md` is adding a row to the `## Human gates` table, which has no verb —
**resolving is a CLI operation, never a hand edit** (`aide gate` only lists,
approves and declines).

**An acceptance criterion is an invariant over the resulting content** (§1 →
`items.md`) — never a bound on the diff that produced it, and never a premise
about a sibling item's schedule. Its test outlives the branch it was written on:
a criterion that cannot be re-checked once the item has merged is not one the
suite can keep. The diff-time half of such a claim ("this item did not touch X")
is `aide scope`'s, declared under `## Asserts against`; a premise that a sibling
has not landed yet is guaranteed to become false, so the later item's spec lists
that test file under **May change** from the start.

**Capture is a plain append; everything after it has a verb** (§1 →
`insights.md`): `aide insights list --open` reads the backlog without the
closed history around it, `aide insights tick N --pointer "<where it landed>"`
closes an entry — **ticking the checkbox is the one in-place edit**, and the
verb owns it, so a hand-flipped `[x]` is the improvised form of `tick` — and
`aide insights archive --before <date> --yes` moves closed entries out (a dry
run without `--yes`). Reading the file raw costs the whole closed history to
see a working set of a dozen lines; editing it by hand is the failure `tick`
exists to prevent.

**The open inbox is an input to queue authoring, not only an output of triage**
(§1 → `insights.md`). Triage happens *at* the queue boundary, when the next
queue does not exist yet, so a `defect`, `gap` or `automation` entry routed
there to "a candidate item" waits in the inbox for whoever authors that queue:
`aide insights list --open` is one of its inputs, beside vision, roadmap and
progress. Every open entry of those three types is **considered, and either
queued or explicitly passed over — never silently dropped**; a queued one is
ticked with the item number it became, and a passed-over one stays open,
because an unchecked entry is still a candidate.

**Root documents are authored through their loop entry point, interactively —
whatever `loop.clarify` says** (`.aide/conventions.md` §5); here that entry point
is `/aide-create-vision` / `/aide-create-roadmap`, which carries the
existing-document check and the draft-for-review hand-off. **Do not write a root
document directly, however well the template shape is known** — ask until the
mandatory sections are grounded in their answers, and never fill **Guiding
principles**, **Out of scope**, or **Success criteria** from assumption.
