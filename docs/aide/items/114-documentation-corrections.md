# Item 114 — Documentation corrections: `bounds.py` comments and Stage 17's acceptance box

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 114
> **Objectives:** G7
> **Suggested branch:** `aide/114-documentation-corrections`

---

## Description

Two small, unrelated documentation defects, batched because neither justifies
its own spec→test→build→validate→merge cycle.

**(a) `heuristics/bounds.py` names retired labels.** Comments near lines ~44,
~53 and ~59 still read "S and Cocygis are intentionally omitted (unbounded)" —
labels item 093 retired when the TPTBox convention became the default. The
*behaviour* is correct and must not change: `_LEVEL_GROUP` derives the omission
generically from `CANONICAL_ORDER` by name prefix, so `S1`-`S6` and `Cocc` are
still correctly treated as unbounded. Only the comment text names labels that no
longer exist in the convention, which will mislead the next reader.

**(b) Stage 17's acceptance box contradicts itself.** `progress.md` renders its
fourth Stage 17 acceptance box as `- [x] A real segmenter output round-trips
with correct level names.` while that same line's annotation opens *"Not ticked:
no real SPINEPS output is available…"*. A reader — or an `aide check` rollup —
gets the opposite answer depending on which half it reads. Item 097's Decisions
log makes the intent clear: met in mechanics (a committed synthetic
TPTBox-labelled fixture covers the round-trip unconditionally), unmet in reality
(no real SPINEPS output exists here). The honest state is already carried by the
Environment-Gated Capability Verification row *"Real SPINEPS-output
label-convention round-trip — ❓ Unverified"*.

**In scope.** The comment text; unticking the box while keeping its annotation;
checking whether anything mechanically pressures a ✅ stage into ticking every
box.

**Not in scope.** Any behavioural change to `bounds.py`. Reopening Stage 17 —
it stays ✅, exactly as Stage 14 stays ✅ with two `❌ Not met` Outcome targets.
Adding a third acceptance state to the format contract (that is a framework
change, see Decisions).

## Acceptance Criteria

- [ ] **AC1: no retired label name survives in `bounds.py`.** No comment in
  `src/segfacet/heuristics/bounds.py` names a label absent from
  `CANONICAL_ORDER` — specifically not `Cocygis`, and not a bare `S` used as a
  label name.
- [ ] **AC2: the replacement text is accurate.** The comments name the labels
  actually omitted today (`S1`-`S6`, `Cocc`) and describe the generic
  name-prefix derivation rather than a hardcoded list.
- [ ] **AC3: behaviour is byte-identical.** The `bounds` rule produces
  identical findings on every committed corpus case, before and after.
- [ ] **AC4: the box is unticked.** Stage 17's fourth acceptance box reads
  `- [ ]`.
- [ ] **AC5: the annotation is kept and reconciled.** The existing explanation
  remains and no longer opens with a claim that contradicts the box's state.
- [ ] **AC6: it agrees with the verification row.** The box, its annotation and
  the ❓ Unverified Environment-Gated row tell one consistent story.
- [ ] **AC7: Stage 17 stays ✅.** The stage summary row and section heading are
  unchanged.
- [ ] **AC8: no new `aide check` warning.** `python .aide/scripts/aide.py check`
  reports no warning that was absent before this item.
- [ ] **AC9: the tick-pressure question is answered.** Whether `aide check`'s
  rollup requires every acceptance box ticked before a stage may be ✅ is
  determined empirically and recorded — if it does, that pressure is itself a
  defect and is logged to `insights.md` rather than worked around.

## Assumptions

- **Untick and keep the annotation** (maintainer, 2026-08-12), rather than
  rewording the criterion to a mechanics-only claim or introducing a third
  acceptance state. Rewording would quietly redefine the criterion after the
  fact and lose the real-data intent from the record; a third state is a
  format-contract change belonging to `aide-loop`.
- **The Outcome-targets precedent applies.** A stage may be ✅ with a recorded
  unmet criterion — established when Stage 14 closed with two `❌ Not met`
  Outcome targets. So unticking does not reopen Stage 17.
- **`bounds.py`'s behaviour genuinely is comment-only affected.** AC3 verifies
  this rather than assuming it; if the omission turns out to be hardcoded
  anywhere, hand back — that is a behavioural defect, not a comment fix.

## Implementation Steps

1. Read the three comment sites in `bounds.py` and confirm `_LEVEL_GROUP`
   derives omissions generically (record the evidence).
2. Rewrite the comments per AC2.
3. Run the corpus and diff `bounds` findings against pre-change output (AC3).
4. Untick Stage 17's fourth acceptance box; reword the annotation's opening so
   it explains rather than contradicts.
5. Run `aide check` before and after; determine empirically whether an unticked
   box in a ✅ stage produces a warning (AC9) and record the answer.
6. If it does, log the pressure to `insights.md` as a framework entry.

## Testing Strategy

New module `tests/test_114_documentation_corrections.py`:

- AC1: assert no retired label name appears in `bounds.py`'s source.
- AC2: assert the current label names do appear.
- AC3: run the `bounds` rule over the corpus records and compare findings to the
  committed goldens.
- AC4/AC5/AC6: parse `progress.md`, locate Stage 17's acceptance list, assert
  the box state, that the annotation is present, and that the verification row
  still reads ❓ Unverified.
- AC7: assert the stage summary row and heading still carry ✅.

Adversarial: a comment mentioning a retired name inside a docstring example
(must still be caught or explicitly exempted); Stage 17 section not found (clear
failure, not a silent pass).

## Validation

Run `python .aide/scripts/aide.py check` before and after, and record both
outputs — this is the evidence for AC8 and the empirical answer to AC9.

## Dependencies

None blocking. Item 107 (if landed) removes the `heuristics/**` fences this
item's comment edit would otherwise force a re-pin of.

## Authorised paths

- `src/segfacet/heuristics/bounds.py`
- `docs/aide/progress.md`
- `docs/aide/insights.md`
- `tests/test_114_documentation_corrections.py`
- `docs/aide/items/114-documentation-corrections.md`

## Decisions & Trade-offs

- **A comment-only edit to `src/segfacet/**` is why this item exists in a
  remediation stage at all**: before item 107, changing three comment lines
  trips three `heuristics/**` package digests plus `_PRE_105_SRC_HASH`. That
  cost ratio — four re-pins for a comment — is one of the clearest arguments in
  item 107's case, and is recorded here as evidence.
- **Five comment sites, not three.** The Description names lines ~44, ~53,
  ~59; the actual retired-label mentions are at lines 44, 53, 59, 268 and 351
  (docstring step-list and the inline skip comment inside `evaluate`). All
  five were rewritten; the Description undercounted them.
- **AC2 wording chosen to make the fragile guard legible.** Rather than a
  drive-by name swap, the `_LEVEL_GROUP` comment (lines 43-53) now spells out
  the prefix-matching mechanism and calls out explicitly that `Cocc` starts
  with `C` but is excluded only by the cervical branch's
  `_name[1].isdigit()` guard — the one line a future "simplification" could
  silently break. `_level_group`'s docstring, `BoundsRule`'s class docstring,
  and the inline skip comment in `evaluate` were updated to name `S1`-`S6`
  and `Cocc` instead of the retired `S`/`Cocygis`.
- **Behaviour confirmed unchanged (AC3).** `_LEVEL_GROUP`'s construction and
  `_level_group()` were not touched — only comments. Verified by running
  `tests/test_027_level_aware_bounds.py` (83 tests, incl. `test_027`'s own
  bounds-rule suite) and `tests/test_heuristics_bounds_source.py` together:
  83 passed. The pre-existing AC3 behavioural-pin tests in
  `test_114_documentation_corrections.py` (which assert `_level_group` on
  every `CANONICAL_ORDER` name plus the `Cocc`/unknown/custom adversarial
  cases) also pass unchanged.
- **AC9 empirical answer: `aide check` does NOT mechanically pressure a ✅
  stage into ticking every acceptance box.** Ran
  `python .aide/scripts/aide.py check` both before (per the task's AC8
  baseline) and after unticking Stage 17's fourth acceptance box while
  leaving the Stage 17 section heading and stage-summary row at ✅. Both runs
  produced the identical 9 warnings and `aide check: OK (9 warning(s))`:
  - `progress.md:340`, `progress.md:459`, `progress.md:638` — status icon
    outside a structural status position
  - `queue/queue-002.md:80` — same
  - `insights.md:51`, `insights.md:58`, `insights.md:60` — entry format
  - `stale claim branch aide/queue-016`, `stale claim branch
    aide/specs-queue-015` — local branch state, unrelated to this edit
  No new warning appeared and no warning about an unticked box in a ✅ stage
  was raised. Since the rollup applies no such pressure, there is no
  framework defect to log to `insights.md` for this item.
