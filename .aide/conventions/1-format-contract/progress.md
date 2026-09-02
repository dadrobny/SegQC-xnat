### `progress.md` (the single source of truth for status)

Mandatory, in order (consumer in brackets):

1. **Stage summary table** — `| Stage | Title | Objectives | Status |` with one
   row per stage; `Stage` is an integer, `Status` a single icon. *(aide check,
   status report, queue-planner)*
2. **Objective coverage table** — `| Objective | Delivered by | Status |`; the
   objective cell starts with a `G<n>` code. *(status report, validator)*
3. **One `## Stage N — <title> — <icon>` section per stage.** Inside it:
   - a **Deliverables** block of **flat** bullets, each
     `- <icon> <text>. *(Item NNN)*` — one status icon, one item ref, no nested
     status-bearing sub-bullets (keep rollup unambiguous). *(builder, validator,
     aide progress, status report)*
   - an **Acceptance** block of `- [ ]` / `- [x]` checkboxes, ticked only by
     `aide progress accept` — never derived. *(validator)*

**Item references on a deliverable bullet.** The `*(Item NNN)*` suffix is what
ties an item to the bullet whose status it moves — `aide progress set NNN` finds
the bullet by it, and `check`/`status`/`claim` derive queue state from it, so an
item no bullet references is untracked. **Suffix means suffix**: only the
trailing marker that ends the bullet (its last wrapped line) attributes. A
reference form earlier in the bullet's prose — "- ✅ Consolidate parsers,
absorbing *(Item 095)*'s scope *(Item 094)*" — is free text: here 094 is the
bullet's item and the mention of 095 moves nothing, so a ✅ bullet cannot mark a
live sibling complete just by naming it. A bullet whose references all sit
mid-prose tracks nothing, and `aide check` warns about it. These forms are all
accepted for the marker, and all mean the same thing to every command:

| Form | Reads as |
|---|---|
| `*(Item 006)*` | 6 |
| `*(Items 006, 044)*` | 6, 44 — one deliverable, several items |
| `*(Items 041, 053, 057)*` | 41, 53, 57 — a list is any length |
| `*(Items 089/090)*` | 89, 90 |
| `*(Items 071–075)*` | 71, 72, 73, 74, 75 — inclusive, hyphen or en-dash |
| `*(Items 006, 044–046)*` | 6, 44, 45, 46 — an element may be a range |

Spacing around a separator does not matter. A range spanning more than 50 is
read as a typo and contributes only its endpoints. Prefer the explicit list when
the items are not contiguous; a range is only shorthand for one.

**A marker naming several items is shorthand, never a shared status cell.** One
bullet carries one icon, so while items share a marker they share a status —
and the first flip would otherwise carry the siblings with it. It does not:
`aide progress set` and `aide merge` **desugar** the bullet first, into one
bullet per item with the same text and one `*(Item NNN)*` each, and move only
the item named. The others keep the status they had. Nothing is asked of the
author — write the shared marker freely; the file simply grows a row the first
time its items diverge.

**Rollup rule (deterministic — `aide progress` and `aide check` both apply it):**
a stage is ✅ if *every* Deliverables bullet in it is ✅; then its summary-table
row, section header, and any Objective row delivered solely by complete stages
read ✅ (unless the objective is linked to an Outcome target that is not
`✅ Met` — see below). If any bullet is ✅/🚧 but not all, the stage is 🚧.
Otherwise 📋.

**Acceptance boxes are attestations, and no rollup ever ticks one.** They are
outside the derivation entirely: the rollup skips checkbox lines, `aide check`
never gates a ✅ stage on them, and `aide progress set` leaves them exactly as
the author wrote them. A box is ticked only by a human — or by an agent acting
on a check it actually performed — via:

```
aide progress accept <stage> (--criterion N | --all) [--evidence "<text>"]
```

The reason is that a derived tick is not an attestation. While `progress set`
auto-ticked, a box deliberately left `[ ]` in a ✅ stage — the honest record of
a criterion that shipped unmet — was silently flipped back on the next status
change for *any* item in *any* stage, converting a recorded shortfall into a
false claim that nobody had made. A stage may be ✅ with an unticked box; say
why in an annotation beside it.

**The attestation is immutable; what is recorded about it is not.** The same
rule `insights.md` runs on, and load-bearing for the same reason: an
attestation that turns out to be wrong is the record, and a correction written
beneath it teaches what a silent rewrite would erase. So the criterion line is
never reworded once anything has been claimed against it, and every later
statement about it goes in an appendable **correction trail** — dated lines
indented under the box, newest last:

```
- [ ] Benchmark run end to end. *(validator, 2026-08-29: on this CPU-only machine)*
  - **2026-09-01** → the host has four GPUs; the CPU-only basis was misread
  - **2026-09-02** → retracted: re-run pending on a host we have identified
```

Three verbs, and **none of them edits the original line**:

```
aide progress amend   <stage> --criterion N --evidence "<the corrected basis>"
aide progress retract <stage> --criterion N --reason   "<why it is withdrawn>"
aide progress reword  <stage> --criterion N --text     "<the new wording>"
```

- **`amend` appends, and only to a ticked box.** The attestation stands; what
  was recorded about it was wrong or thin. This is the whole guard, and it is
  structural rather than advisory: **a verb that can only add cannot be used to
  make an inconvenient attestation agree with a shipped stage.** Over-using it
  costs verbosity, never truth.
- **`retract` unticks, and keeps the original attestation visible.** The
  criterion does not hold after all, so the box reads as *claimed, then
  withdrawn, for this reason* — not as one nobody ever ticked. **A retraction
  is a finding, so the verb routes it like one**: an `insights.md` `- [ ] gap`
  entry in the same commit, exactly as a `❌ Not met` outcome target does. That
  is what keeps the honest path the cheap one.
- **`reword` is the one amendment that edits rather than appends**, and it is
  safe for exactly one reason: nothing has been claimed yet. It **refuses over
  a box that is ticked, annotated, or already carries a correction trail** —
  the precondition is mechanical, so no role has to remember it. Rewording a
  criterion an attestation was made against would silently re-point that
  attestation at a different claim.

**`reword` writes both documents or neither.** `roadmap.md` mirrors a stage's
criteria, so a rewording that lands in one file is precisely the two-file drift
the verb exists to remove. The Nth box is matched to the Nth non-`Target:`
bullet of the roadmap stage's **Validation / acceptance** block; if the two
cannot be lined up, **nothing is written** and the message says which counts
disagreed.

Neither `amend` nor `retract` takes `--all`: each attestation was made
separately and is corrected or withdrawn separately. Both refuse without a
stated reason. And `aide check` warns on every retracted criterion while
`aide status` prints it, so a withdrawal stays visible instead of living only
in one commit's diff.

**What a stage's ✅ means — and what it deliberately does not.** The rollup
makes stage status track exactly one thing: *the planned work shipped*. An
Acceptance box is therefore an observable check **of the built thing** (the
CLI runs, the artifact validates) — something completing the deliverables can
guarantee. A **measured outcome** the work aims for but cannot guarantee by
construction (an error-rate target, a benchmark result) must NOT be an
Acceptance box: it would hold the stage's honest record hostage to a result the
work cannot promise. Such goals go in the **Outcome targets** table below.

**Outcome targets (optional, additive).** A `## Outcome targets` section in
`progress.md` with one row per measured goal:

```
| Target | Objective | Attempted by | Status | Evidence / follow-up |
|--------|-----------|--------------|--------|----------------------|
| Held-out FPR ≤ 0.10 | G3 | Stage 14 | ❌ Not met | FPR 0.975 → gap insight, item 0NN |
```

Status is table-local (like the env-gated verification table's): `❓
Unverified` until measured, then `✅ Met (date, evidence)` or `❌ Not met
(result → follow-up)`. Semantics *(aide progress, aide check, aide status)*:

- A target **never blocks its stage** — the stage closes when its work ships.
  It gates the **Objective coverage rows** instead: an objective linked to a
  target that is not `✅ Met` cannot roll up to ✅, and `aide check` errors on
  an objective claimed ✅ over a `❌ Not met` target (the goal-level mirror of
  the deliverable-level over-claim error).
- Marking a target `❌ Not met` is a *finding*, so route it like one: append a
  `- [ ] gap — …` line to `insights.md` in the same edit. The feedback loop
  then plans the follow-on deliverables explicitly — needing more work than
  planned to hit a goal is normal, and it enters through the queue, not by
  retro-editing a closed stage's deliverable list.
- `aide status` prints every target not yet `✅ Met`, so the state stays
  visible even though the stage summary table does not carry it.
