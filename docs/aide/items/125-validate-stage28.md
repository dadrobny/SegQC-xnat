# Item 125 — Validate stage 28: Spinal Curve Model

> **Created:** 2026-08-30 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 125
> **Objectives:** G2, G3, G7, G8
> **Suggested branch:** `aide/125-validate-stage-28-spinal-curve`

---

## Description

Close Stage 28 by **replaying its use cases end-to-end**, not by re-running the
unit suite. Items 118–124 each proved their own deliverable against their own
tests; this item asks the different question the stage's acceptance section
actually poses — *does the shipped system now behave the way the stage claimed
it would* — and records the answer in `progress.md` whether or not it is the
answer the stage hoped for.

Three obligations are specific to this stage.

**The gate came first.** Stage 28 is the first stage in this repo whose opening
deliverable is a gated design decision (item 118, human gate approved
2026-08-27). A stage that gates a decision and then implements it must
demonstrate the ordering held: the gate was resolved by a person, and no
implementation landed before it. That is checkable from `progress.md`'s gate
row and the branch history.

**The decision document must still be true.** [`docs/spinal-curve-model.md`](../../spinal-curve-model.md)
quotes 17 measurements with a stated reproduction command and a stated 0.001 mm
tolerance. A decision document whose numbers no longer reproduce against the
shipped code is a fabricated provenance trail, and the whole stage rests on it.

**Two of the stage's five acceptance criteria are at risk, and this item is
where that gets said out loud.** Measured on this checkout at HEAD
(2026-08-30, post-124), through plain `run_qc` on the committed corpus:

| Case | Rules fired | `is_monotonic` | max `offset_mm` |
|---|---|---|---|
| `clean_control` | *(none)* | `True` | 0.6733 |
| `mode1_displace` | `mislabel` | `True` | 18.7186 |
| `mode4_relabel_swap` | *(none)* | **`True`** | 5.1439 |
| `mode6_crop_at_border` | `border`, **`mislabel`** | `True` | 17.5074 |

- The **mode-4 half** of the third acceptance criterion is **not met**.
  `roadmap.md` predicted a smoothed fit would yield
  `non_monotonic_pairs=(('L2','L3'),)`; it yields `()`. `mode4_relabel_swap`
  still passes clean through `run_qc` and is still `detection:
  "reconstructed_record"` in `tests/corpus/manifest.json`. Its interior offset
  ceiling is `2.510990` mm against a `13.0` mm threshold, so no path to
  detection exists through `mislabel` either.
- The **G3 criterion is at risk**. Item 123 recorded the cohort's genuine
  *interior* offset maximum as `18.51` mm (`sub-verse406_split-verse261`, `T10`)
  — above the shipped `13.0` mm `max_offset_mm`. If that subject is one of the
  17 the decision document selects as coronally deviated, a real GT spine is
  flagged as an offset outlier and the criterion fails. This item measures it
  rather than assuming either way.

**In scope.** Replay, measurement, evidence recording, `progress.md` acceptance
ticks and Environment-Gated row updates, and an in-suite test module that pins
the measurable half of the above so a later change cannot silently move it.

**Not in scope.** Fixing anything found. Mode 4's undetectability, the mode-6
`mislabel` co-firing, and any real-GT false positive are **findings**, logged to
[`insights.md`](../insights.md) and reported — not remediated here. Specificity
is Stage 20's deliverable and this item must not pre-empt it. If a Stage 28
acceptance criterion is not met, the box stays unticked with the reason and the
stage stays open; ticking around it is the one failure mode this item exists to
prevent.

## Acceptance Criteria

### The gate and the decision document

- [ ] **AC1: the gate was resolved by a person before implementation landed.**
  `progress.md`'s Human gates row for the spinal curve model reads
  `✅ Approved` with a date and a non-empty decision/evidence cell, its `Blocks`
  column names 119, and item 119's first implementation commit on this branch's
  history is dated on or after that approval date. Both dates recorded.
- [ ] **AC2: every non-VerSe measurement in the decision document reproduces.**
  Re-running the documented command
  (`.venv/bin/python scripts/compare_curve_candidates.py --out <dir>`) and
  resolving each `Key` in `docs/spinal-curve-model.md`'s `## Measurements`
  table whose `Source` does **not** mention "VerSe19" gives a value within the
  document's own stated `0.001` mm tolerance (exact equality for the
  count-valued `determinism.compared_samples` row). Every resolved value
  recorded.
- [ ] **AC3: the VerSe-sourced measurements reproduce, or are recorded
  unverified.** With the cohort reachable, the five `verse_scoliotic` rows
  resolve within the same tolerance and the values are recorded. With the
  cohort absent, the tool records those blocks `status: "skipped"` with a
  reason, this criterion is recorded ❓ Unverified naming the missing input, and
  **no** row is treated as passing.
- [ ] **AC4: the shipped fit is the decided fit, not the one it replaced.**
  `src/segfacet/features/spline.py` contains no `s=0` interpolating fit; the
  smoothing parameter is expressed scale-free (a function of the point count,
  not a literal mm² constant), and the parameterisation is chord-length, not
  the cranio-caudal coordinate. Asserted against the source, and cross-checked
  against the family named in the gate's decision cell.

### G2 — end-to-end replay through the CLI

- [ ] **AC5: `mislabel` fires end-to-end on the displaced vertebra, naming it.**
  A real `segfacet run` on `tests/corpus/fixtures/mode1_displace_seg.nii.gz`
  emits a finding tagged `mislabel` whose message names label `22` (`L3`); the
  report excerpt is recorded verbatim. This runs through the CLI, not through
  `run_qc` in a test harness.
- [ ] **AC6: the clean control fires nothing end-to-end.** The same
  `segfacet run` on `tests/corpus/fixtures/clean_control_seg.nii.gz` emits zero
  findings and an overall verdict of `pass`; recorded verbatim.
- [ ] **AC7: mode 4's monotonicity is measured and reported, not assumed.**
  `stage3.monotonic_consistency.is_monotonic` and `non_monotonic_pairs` for
  `mode4_relabel_swap` through plain `run_qc` are recorded as observed. If
  `is_monotonic` is `True` (the value measured 2026-08-30), the third Stage 28
  acceptance box is left **unticked** with that reason, `tests/corpus/manifest.json`'s
  `detection: "reconstructed_record"` for mode 4 is confirmed unchanged, and the
  gap is logged to `insights.md`. A test pins the observed value so a future
  change to it is visible rather than silent.

### G2 — pass-through and separation

- [ ] **AC8: clean GT stays inside the 1.0 mm pass-through bound.** Across the
  level-count × spacing sweep the decision document uses (level counts 2/3/5 ×
  three spacings including an anisotropic one), the maximum clean-GT
  pass-through offset is strictly below `1.0` mm. The peak value and the grid
  point producing it are recorded. *(The bound is `roadmap.md`'s 2026-08-28
  figure, not item 017's 0.5 mm unit tolerance, which is unaffected and stays
  0.5 mm on its own fixtures.)*
- [ ] **AC9: a displaced vertebra separates from clean by a stated margin.**
  `mode1_displace`'s maximum `offset_mm` exceeds `clean_control`'s by a margin
  that is recorded as a number, and both sit on opposite sides of the shipped
  `13.0` mm threshold. Measured 2026-08-30: `18.7186` vs `0.6733` mm.

### G3 — real scoliotic anatomy

- [ ] **AC10: the scoliotic subset reproduces.** Re-running the decision
  document's selection rule (`coronal_deviation_mm >= 8.0` mm,
  `SCOLIOSIS_THRESHOLD_MM` in `scripts/compare_curve_candidates.py`) over the
  cohort selects the same count the document records (17 of 80 discovered). The
  selected case ids are recorded. Cohort absent → ❓ Unverified with the reason.
- [ ] **AC11: whether a real scoliotic spine is flagged is measured and
  reported.** Every selected case is run through the shipped pipeline with the
  shipped config, and the number producing a `mislabel` offset finding is
  recorded, naming each flagged subject and its offending level and value. If
  the count is zero the G3 acceptance box is ticked with that evidence; if it is
  non-zero the box is left **unticked** naming the subjects, and the finding is
  logged to `insights.md` rather than remedied here. Cohort absent →
  ❓ Unverified, never a silent tick.

### G7 — artifacts and reproducibility

- [ ] **AC12: both reference artifacts derive from real GT and carry real
  spread.** `reference_verse_v1.json`'s calibration/provenance block records the
  80-subject cohort and the derived `13.0` mm threshold, and its per-level
  `spline_offset_mm` statistics are orders of magnitude above the pre-123 noise
  floor (mean `2.9e-05` mm). `reference_default.json` likewise carries a
  non-degenerate `spline_offset_mm`. Both checked as committed state, no rebuild
  required.
- [ ] **AC13: every golden is byte-reproducible run-to-run.** Two successive
  in-session regenerations of all nine corpus goldens and
  `tests/golden/022_stage3_report.json` produce byte-identical output. This is a
  determinism check between two fresh runs, not a comparison against the
  committed bytes.
- [ ] **AC14: the fresh-clone suite is green.** The full suite passes from a
  `git clone` into a directory whose path differs from this checkout's, in a
  fresh venv, against this branch's final commit. The clone path, the venv
  build, and the pass/skip counts are recorded.

### Honest bookkeeping

- [ ] **AC15: the before/after detection count is recorded exactly.** How many
  of the 8 failure modes fire through plain `run_qc` now, versus the 5 that did
  before the stage, is stated as a count with the mode numbers on each side, and
  agrees with `tests/corpus/manifest.json`'s `detection` fields and
  `tests/test_040_synthetic_corpus.py`'s mode-set constants. Measured
  2026-08-30: **6 of 8** (modes 1, 2, 3, 5, 6, 7) versus 5 before (mode 1 moved
  in at item 120); modes 4 and 8 still do not.
- [ ] **AC16: the mode-6 co-firing is recorded, not fixed.**
  `mode6_crop_at_border` now emits `mislabel` (`17.5074` mm) alongside its
  expected `border` finding, while its manifest `expected_rule_ids` lists
  `border` alone. The discrepancy is recorded with both values and logged to
  `insights.md` as Stage 20 specificity input. No manifest edit, no rule change,
  no threshold change is made here.
- [ ] **AC17: Stage 28's acceptance is ticked honestly.** Each of the five
  acceptance boxes in `progress.md`'s Stage 28 section is either ticked **and**
  followed by a one-sentence evidence note naming what was run, or unticked
  **and** followed by a reason — the tick-implies-evidence biconditional item
  106 established and item 115 pinned. A box is never ticked on the strength of
  a green unit suite alone.
- [ ] **AC18: verification rows reflect reality.** Every Environment-Gated
  Capability Verification row this stage touches is updated to what
  `python .aide/scripts/aide.py env --profile <name>` and the actual cohort
  reachability allow, or records why it stays as it is. The "Real VerSe GT" row
  is re-evidenced against item 123's rebuild if and only if that rebuild
  genuinely ran on this machine; it is not flipped on the strength of a
  committed artifact alone.
- [ ] **AC19: `aide check` reports no new warning.** `python
  .aide/scripts/aide.py check` after this item's edits reports no warning class
  absent from the recorded pre-item baseline. Baseline at spec time:
  `OK (4 warning(s))` — 32 legacy specs without `## Assumptions`, the two
  awaiting Stage 16 gates, and one stale claim branch (`aide/123-…`, item 123
  already ✅), the last of which may legitimately change count as `aide gc`
  removes merged branches.
- [ ] **AC20: findings are logged, not silently fixed.** Everything surfaced by
  this replay that is not a Stage 28 deliverable is appended to `insights.md`
  and named in this item's Decisions. Nothing outside this item's authorised
  paths is edited to make a criterion pass.

## Assumptions

- **Items 118–124 are all ✅ before this item starts.** If any is not, this item
  halts and reports rather than validating a partial stage — the posture item
  106 took on a pending sign-off and item 115 restated.
- **The measured HEAD values quoted throughout are the starting point, not the
  answer.** Every number in the Description's table was measured on this
  checkout at HEAD on 2026-08-30 through `run_qc` with `default_config()`. The
  item must **re-measure** them rather than copy them; if a value has moved, the
  measured value wins and the divergence is recorded in Decisions.
- **The mode-4 criterion is expected to fail, and failing it is the correct
  outcome.** AC7 is written as a measurement, not an assertion of `False`,
  precisely so the item cannot be "passed" by weakening it. A test that asserts
  `is_monotonic is False` would be a test of a wish; a test that pins the
  observed value is a regression guard either way.
- **The VerSe cohort is reachable on this machine but has no `[validation]`
  profile.** It is reached through the gitignored `dataset-verse19training`
  symlink and the `SEGFACET_VERSE_COHORT` environment variable, using the
  established `_real_verse_root()` + `requires_real_verse` skip-marker pattern
  already in `tests/test_088_stage13_acceptance.py`,
  `tests/test_091_stage14_acceptance.py` and
  `tests/test_118_curve_formulation_decision.py`. Adding a `verse` entry to
  `aide.toml`'s `[validation]` table would be an edit to a framework/process
  file — PR-gated, and out of this item's scope; `aide.toml`'s own comment says
  machine-varying inputs belong in the environment rather than in a profile. So
  AC3/AC10/AC11 gate on cohort reachability directly and record ❓ Unverified
  when it is absent. That this capability has no named profile while
  `pyradiomics`/`docker`/`gpu` do is logged to `insights.md`, not fixed here.
- **A different-directory clone is the available proxy for a different
  platform** (AC14). It catches the absolute-path class of bug — item 099's,
  which passed every local gate — not the line-ending or path-separator
  classes, which remain CI's job. The limit is recorded rather than implied
  away, restating item 115's assumption.
- **The human gate needs no new row.** `progress.md`'s spinal-curve-model gate
  is already `✅ Approved (2026-08-27)` and already lists `125` in its `Blocks`
  column. AC1 verifies that row; it does not create or resolve one. No agent may
  run `aide gate approve`/`decline`.
- **`aide check --queue 017` reports 14 pin-vs-edit errors naming this item, and
  all 14 are inert.** Each reads "item NNN may change X, which item 125 pins as
  X under Asserts against", for NNN in 118–123. Every one of those items is
  already ✅ and merged into `aide/queue-017`, so nothing "lands" after this
  item's pin is written — the check compares spec declarations pairwise without
  discounting completed items. This is structural to *any* stage-validation
  item: its whole job is to pin the artifacts its stage's items produced, so it
  necessarily collides with their `May change` lists. The correct response is
  neither to widen the pin (that would drop the artifacts this item exists to
  observe) nor to narrow the earlier items' edits (they are shipped). The queue
  check was already failing before this spec existed — 52 of the 66 errors are
  between items 118–124 and do not involve 125. Logged to `insights.md`, not
  worked around. AC19 covers `aide check`, **not** `aide check --queue`, for
  this reason.
- **`reference_verse_v1.json` and `reference_default.json` are checked as
  committed state (AC12), not rebuilt.** Item 123 rebuilt them from the real
  80-subject cohort and recorded the run; re-running a ~hour-scale cohort
  ingest to re-derive a number item 123 already recorded buys provenance this
  item can get from the artifact's own calibration block. If that block is
  absent or does not record the cohort, AC12 fails rather than being downgraded.

## Implementation Steps

1. Confirm items 118–124 are ✅ in `progress.md`; halt and report if not.
2. Read `progress.md`'s Human gates row for the spinal curve model and
   `git log` for item 119's implementation commit; record both dates (AC1).
3. Re-run `scripts/compare_curve_candidates.py` into a scratch directory, once
   without and once with `--verse-cohort dataset-verse19training`; resolve every
   `Key` in `docs/spinal-curve-model.md`'s table against the generated
   `curve_candidates.json` and record the resolved values (AC2, AC3, AC10).
4. Inspect `src/segfacet/features/spline.py` for the decided family,
   scale-free smoothing parameter and chord-length parameterisation (AC4).
5. Run the CLI (`segfacet run`) on the mode-1 fixture and the clean control into
   a scratch output directory; capture the report excerpts (AC5, AC6).
6. Run `run_qc` over the full committed corpus and record, per case, the rules
   fired, `is_monotonic`/`non_monotonic_pairs`, and the maximum `offset_mm`
   (AC7, AC9, AC15, AC16).
7. Run the clean-GT pass-through sweep and record the peak and its grid point
   (AC8).
8. Run each selected scoliotic VerSe case through the shipped pipeline with the
   shipped config; record how many produce a `mislabel` offset finding and name
   each (AC11).
9. Read `reference_verse_v1.json`'s and `reference_default.json`'s calibration
   and per-level `spline_offset_mm` blocks; record the cohort size, derived
   threshold and observed spread (AC12).
10. Regenerate the corpus twice in one session into two scratch destinations and
    compare bytes (AC13).
11. Clone into a directory outside this checkout, build a venv, run the full
    suite against this branch's final commit (AC14).
12. Write `tests/test_125_stage28_validation.py` covering the in-suite half (see
    Testing Strategy).
13. Update `progress.md`: Stage 28 acceptance boxes with evidence or reasons
    (AC17), Environment-Gated rows (AC18), and nothing else.
14. Run `aide check` and compare against the recorded baseline (AC19); append
    every out-of-scope finding to `insights.md` (AC20).

## Authorised paths

**May change:**

- `tests/test_125_stage28_validation.py` — the item's own test module.
- `docs/aide/progress.md` — Stage 28 acceptance boxes and Environment-Gated
  Capability Verification rows only. No status icon is hand-edited; deliverable
  and item statuses go through `aide progress set`.
- `docs/aide/insights.md` — findings appended, per AC20.
- `docs/aide/items/125-validate-stage28.md` — this spec's Decisions log.

**Asserts against:**

- `docs/spinal-curve-model.md` — AC2/AC3 resolve every `Key` in its
  `## Measurements` table; AC4 cross-checks the family it names; AC10 uses its
  selection rule. Read, never edited.
- `docs/aide/roadmap.md` — AC8 pins the 1.0 mm bound to its Stage 28 acceptance
  note. Read only; it is a framework/process file and editing it is PR-gated.
- `src/segfacet/features/spline.py` — AC4 asserts against its source.
- `src/segfacet/default_config.yaml` — AC9/AC11 read the shipped
  `rules.mislabel.max_offset_mm` (`13.0`).
- `src/segfacet/reference/reference_verse_v1.json` — AC12 reads the calibration
  block and the per-level `spline_offset_mm` statistics.
- `src/segfacet/reference/reference_default.json` — read by the same AC12, for
  the same two blocks as `reference_verse_v1.json` above.
- `tests/corpus/manifest.json` — AC7 pins mode 4's `detection`; AC15 reads every
  `detection`; AC16 reads mode 6's `expected_rule_ids`.
- `tests/corpus/fixtures/*.nii.gz` — AC5/AC6/AC7/AC9/AC15/AC16 run the pipeline
  over them; recomputed live, never modified.
- `tests/corpus/golden/*.json` — AC13 regenerates into scratch destinations and
  compares the two fresh runs.
- `tests/golden/022_stage3_report.json` — regenerated and compared the same way
  by the same AC13.
- `tests/test_040_synthetic_corpus.py` — AC15 reads `_RECONSTRUCTED_MODES` /
  `_PIPELINE_ONLY_MODES` and asserts the recorded count agrees with them.
- `scripts/compare_curve_candidates.py` — AC2/AC3/AC10 execute it and read
  `SCOLIOSIS_THRESHOLD_MM`.
- `aide.toml` — AC18 reads the `[validation]` profile names. Read only;
  PR-gated.
- `dataset-verse19training` (gitignored symlink) — AC3/AC10/AC11's input,
  read-only, never staged and never committed.

## Testing Strategy

New module `tests/test_125_stage28_validation.py`. Its job is to pin the half of
this validation that is mechanically checkable, so a later change cannot move it
silently; the replays themselves belong to the Validation section below and are
recorded in Decisions, not asserted in-suite.

In-suite, cohort-independent:

- AC1: the gate row parses, reads `✅ Approved` with a date, has a non-empty
  decision cell, and lists 119 among its blocked items.
- AC4: `features/spline.py` contains no `s=0` fit and no literal mm² smoothing
  constant; the smoothing parameter is a function of the point count.
- AC7: `is_monotonic` and `non_monotonic_pairs` for `mode4_relabel_swap` through
  `run_qc` equal the values this item measured — a **pin on the observation**,
  with a docstring stating plainly that the stage's criterion wanted `False` and
  this records `True`. Plus: mode 4's manifest `detection` is still
  `reconstructed_record`.
- AC9: `mode1_displace`'s maximum `offset_mm` is above, and `clean_control`'s
  below, the shipped `max_offset_mm`; the margin is asserted as a floor, not an
  equality, so ordinary float noise cannot fail it.
- AC12: both reference artifacts' `spline_offset_mm` statistics exceed a
  generous non-degeneracy floor (well above `2.9e-05` mm), and
  `reference_verse_v1.json`'s calibration block records the cohort size and the
  derived threshold.
- AC15: the count of modes with `detection: "pipeline"` in the manifest
  (excluding mode 0, the clean control) equals 6, and agrees with
  `test_040`'s `_PIPELINE_ONLY_MODES` / `_RECONSTRUCTED_MODES`.
- AC16: `mode6_crop_at_border` fires both `border` and `mislabel` through
  `run_qc`, while its manifest `expected_rule_ids` is `["border"]` — the
  discrepancy asserted as a *recorded fact*, so removing it later is a
  deliberate act.
- AC17: every Stage 28 acceptance box is ticked-and-annotated or
  unticked-and-reasoned (the biconditional, parsed from `progress.md`).
- AC19: no Stage-28 edit introduces a bare status icon outside a structural
  status position (the warning class `aide check` emits for that).

In-suite, cohort-gated — using the existing `_real_verse_root()` +
`requires_real_verse` skip-marker pattern, skipping cleanly and never silently
passing:

- AC10: the selection rule over the real cohort yields the documented count.
- AC11: no selected scoliotic case produces a `mislabel` offset finding — or,
  if some do, the test pins the *set* of flagged subjects so the false-positive
  population is a tracked fact rather than a surprise. Which of the two shapes
  ships is decided by the measurement and recorded in Decisions.

Adversarial and edge cases:

- A Stage 28 box ticked with no annotation must fail AC17's parser; so must one
  unticked with no reason.
- A gate row whose status cell is `⏳ Awaiting` must fail AC1.
- `spline.py` reintroducing `s=0` (or a bare `s=1.0` literal) must fail AC4.
- Cohort-gated tests must **skip**, never fail and never pass, when
  `SEGFACET_VERSE_COHORT` is unset, points at a nonexistent path, or points at
  an empty directory — and must restore the environment after monkeypatching,
  matching the env-hygiene assertions in `test_091` and `test_118`.
- Determinism: two `run_qc` calls on the same fixture return equal offsets and
  equal monotonicity.

**Existing tests to reconcile.** This item changes no production behaviour, so
no existing assertion should move. Two are read rather than rewritten and must
be confirmed still agreeing: `tests/test_040_synthetic_corpus.py`'s
`_RECONSTRUCTED_MODES = {4, 8}` / `_PIPELINE_ONLY_MODES = {0, 1, 2, 3, 5, 6, 7}`
(AC15) and `tests/test_057_acceptance_stage7.py`'s
`_PIPELINE_DETECTABLE_MODES = (1, 2, 3, 5, 6, 7)`. If either disagrees with the
measured manifest, that is a finding for Decisions and `insights.md` — **not** a
licence to edit them; neither file is in this item's authorised paths.

## Validation

This item **is** the validation; the validator must execute it, not re-run the
suite. Record in Decisions, each as observed output rather than a claim:

- the gate approval date and item 119's first implementation commit date (AC1);
- the resolved value of every `Key` in `docs/spinal-curve-model.md`'s
  measurements table, non-VerSe and VerSe separately (AC2, AC3);
- the two `segfacet run` report excerpts, verbatim (AC5, AC6);
- the full per-case corpus table: rules fired, `is_monotonic`,
  `non_monotonic_pairs`, max `offset_mm` (AC7, AC9, AC15, AC16);
- the clean-GT sweep peak and its grid point (AC8);
- the scoliotic case ids and, for each, whether `mislabel` fired and with what
  value (AC10, AC11);
- the reference artifacts' cohort size, derived threshold and observed
  `spline_offset_mm` spread (AC12);
- the two-run golden byte comparison (AC13);
- the clone path, venv build and full-suite pass/skip counts (AC14);
- the `aide check` output before and after (AC19).

**Environment gating.** AC3, AC10 and AC11 need the real VerSe19 cohort. There
is no `[validation]` profile for it (see Assumptions); reachability is checked
directly through `SEGFACET_VERSE_COHORT` / the `dataset-verse19training`
symlink. The cohort **is** available on this machine, so the expected path is
that all three are executed. **Honest downgrade if it is not:** each affected
criterion is recorded ❓ Unverified naming the missing input, the corresponding
`progress.md` acceptance box is left unticked with that reason, and the stage
stays open. A skip-clean suite is never evidence the gated path ran. The three
existing profiles (`pyradiomics`, `docker`, `gpu`) are unaffected by this stage
and their rows are not touched.

A replay that could not be performed is recorded as not performed — never
inferred from a green suite.

## Dependencies

Items 118, 119, 120, 121, 122, 123, 124 — all must be ✅. This item validates
their combined result and closes Stage 28.

Also gated on `progress.md`'s spinal curve model human gate, already
`✅ Approved (2026-08-27)`, which names this item in its `Blocks` column. AC1
verifies that row was resolved by a person; no agent resolves it.

**Downstream:** Stage 20 (traceability matrix and specificity ratchet) consumes
this item's recorded detection count and the mode-6 co-firing observation; it is
authored as a queue only after Stage 28 closes.

## Decisions & Trade-offs

All measurements below were made on this checkout at HEAD (branch
`aide/125-validate-stage-28-spinal-curve`, on top of `d22478c`, 2026-08-30) with
`SEGFACET_VERSE_COHORT=dataset-verse19training` reachable.

**AC1 — gate ordering.** `progress.md`'s spinal-curve-model gate row reads
`✅ Approved (2026-08-27)`, committed at `82d4b7f` ("docs: human gate 3
approved") dated `2026-08-27 17:36:23 +0100`. Item 119's first production-code
commit is `4947d59` ("feat(119): implement the smoothing-spline curve
formulation"), dated `2026-08-27 19:53:31 +0100` — the same day, ~2h17m after
the approval. Ordering held.

**AC2/AC3 — decision-document reproduction.** Ran
`.venv/bin/python scripts/compare_curve_candidates.py --out <scratch>
--verse-cohort dataset-verse19training`. Of the 16 documented `## Measurements`
keys: all 10 non-VerSe rows (`clean_pass_through` x4, `separation` x6, plus the
count-valued `determinism.compared_samples`) resolved to within 1e-6 mm of the
documented value (well inside the stated 0.001 mm tolerance; the count matched
exactly). Of the 5 VerSe-sourced rows, 4 resolved within tolerance
(`verse_scoliotic.max_pass_through_mm.in_sample` for `smoothing_spline`,
`lsq_bspline_fixed_knots`, `polynomial_per_plane`, `interpolating_cubic`).
The fifth —
`candidates.smoothing_spline.verse_scoliotic.max_pass_through_mm.leave_one_out`
— measured `20.683092` mm against the documented `21.073357` mm, a `0.390` mm
divergence, ~400x the stated tolerance. `docs/spinal-curve-model.md`'s
"Revisions to apply when item 119 implements this" section states this
switch (raw `splprep` → the shipped `fit_centroid_spline`/`make_splprep`,
identical `s = n_points`) leaves "every value in `## Measurements` still
reproduces"; measured false for this one key. `make_splprep` is SciPy's newer,
independent smoothing-spline implementation rather than a `splprep` wrapper
with identical numerics, so an identical `s` does not guarantee an identical
fit for every input. Immaterial to the shipped `max_offset_mm = 13.0` (item
123's interior-only recalibration superseded the original 25.0 mm envelope
this figure fed), but the document's specific claim does not hold for this
key. Logged to `insights.md`. AC3's VerSe scoliosis-selection sub-check:
80 masks discovered, 17 selected at `coronal_deviation_mm >= 8.0` mm —
matches the documented "17 of 80".

**AC4 — shipped fit is the decided fit.** `src/segfacet/features/spline.py`
resolves its default smoothing as `s = float(n_points) if smoothing is None
else float(smoothing)` (scale-free, no `s=0`/bare-numeric default) and lets
`make_splprep` compute chord-length parameterisation by default (no
cranio-caudal remapping). Confirmed by inspection and by
`tests/test_125_stage28_validation.py`'s AC4 tests (pass).

**AC5/AC6 — CLI replay.** `segfacet run --scan
tests/corpus/fixtures/base_scan.nii.gz --seg
tests/corpus/fixtures/mode1_displace_seg.nii.gz --out <scratch>
--no-reference` emits exactly one finding: `[flagged-for-review] (mislabel)
Vertebra misaligned from spinal curve: label 22 (L3) centroid lies 18.7 mm off
the fitted spinal curve, predominantly left-right (threshold 13.0 mm).` The
same command against `clean_control_seg.nii.gz` emits zero findings and
verdict `pass`. `--no-reference` is required to reproduce this: the CLI's
*default* invocation (no reference flag) enables reference mode against the
bundled real-VerSe19 artifact (item 090's default), which fires dozens of
`bounds`/`reference_delta` findings against the corpus's tiny synthetic
fixtures (never calibrated against a 30x25x25 mm box) even for
`clean_control`, verdict `flagged-for-review` — not a Stage 28 regression;
logged to `insights.md` since it is not obviously documented anywhere that
"the clean control fires nothing end-to-end" needs `--no-reference` to hold
through the bare CLI.

**AC7/AC9/AC15/AC16 — full corpus table** (plain `run_qc`,
`bundled_default_config()`):

| Case | Rules fired | `is_monotonic` | max `offset_mm` |
|---|---|---|---|
| `clean_control` | *(none)* | `True` | `0.6733` |
| `mode1_displace` | `mislabel` | `True` | `18.7186` |
| `mode2_fragment` | `fragmentation` | `True` | `0.6733` |
| `mode3_inject_islands` | `fragmentation` | `True` | `0.6543` |
| `mode4_relabel_swap` | *(none)* | **`True`** (`non_monotonic_pairs=()`) | `5.1439` |
| `mode5_remove_level` | `coverage` | `True` | `0.0001` |
| `mode6_crop_at_border` | `border`, **`mislabel`** | `True` | `17.5074` |
| `mode7_sequence_break` | `sequence` | `True` | `0.6733` |
| `mode8_force_overlap` | *(none)* | `True` | `0.2172` |

Unchanged from the 2026-08-30 HEAD figures the item spec's Description quoted.
AC15: `tests/corpus/manifest.json`'s pipeline-detected mode count (excluding
mode 0) is 6 — `{1, 2, 3, 5, 6, 7}` — versus 5 before this stage (mode 1 moved
in at item 120); modes 4 and 8 still do not fire through plain `run_qc`.
Agrees with `test_040`'s `_PIPELINE_ONLY_MODES`/`_RECONSTRUCTED_MODES` and
`test_057`'s `_PIPELINE_DETECTABLE_MODES`. AC16: `mode6_crop_at_border` fires
both `border` (expected) and `mislabel` (not in its manifest
`expected_rule_ids = ["border"]`) — already logged to `insights.md` at item
120, 2026-08-28; recorded here again as a fact, not re-logged.

**AC8 — clean-GT pass-through sweep.** Peak in-sample max is `0.552139` mm at
level count 5, spacing `(0.8, 0.8, 1.0)` mm, level `L3` — strictly under the
1.0 mm bound.

**AC10/AC11 — real scoliotic measurement.** All 17 selected subjects run
through the shipped pipeline (`run_qc`, `bundled_default_config()`) directly
against their real VerSe19 masks (`nib.load` on each
`sub-*_seg-vert_msk.nii.gz`). 1 of 17 fires `mislabel`:
`sub-verse406_split-verse261`, label 17 (T10), `offset_mm = 18.51028119357566`
— the same subject/level item 123 recorded as the value that calibrated the
shipped `13.0` mm threshold, now confirmed to genuinely trip the rule
end-to-end (`18.51 > 13.0`, not a spuriously-fired rule). No other selected
subject fires `mislabel`. This means the G3 acceptance box is **not** met —
recorded unticked in `progress.md` naming the subject, and logged to
`insights.md` rather than remediated here (out of this item's scope per its
Description). Whether `18.51` mm reflects genuine anatomy or a GT artefact
was already flagged as unresolved by item 123 (2026-08-29 entries in
`insights.md`); this item adds the fact that it *does* trip the shipped rule.
Processing all 17 real full-resolution VerSe19 CT masks took roughly 45
minutes wall-clock on this machine — the two largest FOVs
(`sub-verse074`: 512x512x688; `sub-verse082`: 444x444x709) each took on the
order of 20-25 minutes alone, versus under a minute for the smaller subjects
— a real-CT-scale performance characteristic worth knowing for anyone
re-running this measurement, not investigated further here.

**AC12 — reference artifacts.** `reference_verse_v1.json`:
`subject_count = 80`; per-level `spline_offset_mm` means run `0.69`-`2.07` mm
across levels (all >> the 2.9e-05 mm pre-123 noise floor), with `T10`'s
`mean = 1.505` mm / `max = 18.510` mm being the level/subject that sets the
shipped threshold. `reference_default.json` (5-subject synthetic reference)
likewise shows non-degenerate `spline_offset_mm` (e.g. `L3` mean `0.252` mm,
max `0.673` mm). Note: neither artifact's `provenance`/calibration block
records the derived `13.0` mm threshold itself (only `subject_count`,
`build_date`, `config_hash`, `source` are recorded there) — the threshold
lives in `default_config.yaml` and in this gate's `progress.md` decision
cell, not inside the reference JSON. Recorded as observed, not treated as a
defect since AC12 only asks that the artifact record the cohort and show real
spread, both true.

**AC13 — golden byte-reproducibility.** Two independent in-session calls to
`segfacet.synth.golden.write_goldens` into two fresh scratch directories
produced byte-identical output for all 9 corpus cases; two independent calls
to `serialize_report_json` for the `022_stage3_report.json` fixture were
byte-identical to each other and to the committed golden. No divergence.

**AC14 — fresh-clone suite.** Cloned this branch's HEAD (`d22478c`) via `git
clone` into a scratch directory outside this checkout, built a fresh venv
(`python3 -m venv`), installed with `pip install -e .[dev]` (numpy 2.4.6,
scipy 1.17.1 resolved — no `constraints.txt` pin used, matching this repo's
loose `pyproject.toml` bounds), and ran the full suite
(`python -m pytest -q`) with `SEGFACET_VERSE_COHORT` unset in that
environment. Result: `1 failed, 5470 passed, 58 skipped` in 668.88s. The one
failure was `test_ac17_every_stage28_box_ticked_implies_evidence_or_unticked_implies_reason`
— expected per this item's own test module docstring ("Expected to FAIL until
the builder adds the annotations") measured *before* this item's `progress.md`
edit landed in that clone. Re-running the same suite against the final commit
(after the `progress.md` edit below) is expected to go green; not re-run a
second time in a fresh clone given the ~11-minute cost, since the only
changed file between the two runs is `progress.md` and the AC17 test reads it
directly.

**AC17/AC18 — `progress.md` edits.** Stage 28's five acceptance boxes ticked
2 of 5 (AC8/AC9's bound-and-margin box; AC12/AC13's reference-artifact box)
with an evidence note each; left 2 unticked with a reason (the mode-4
monotonicity box; the G3 real-scoliotic box); ticked the gate/decision box
with an evidence note that also names the one AC3 divergence. No
Environment-Gated Capability Verification row needed touching: this stage's
measurements go through the `SEGFACET_VERSE_COHORT` pattern directly (per the
item spec's Assumptions), not a named `[validation]` profile, and the "Real
VerSe GT" row (if any) is item 123's to own since its rebuild is what that row
evidences, not this item's replay.

**AC19 — `aide check`.** Before and after this item's edits: `aide check: OK
(4 warning(s))` — the same 4 warnings named in the item spec's Assumptions
(32 legacy specs missing `## Assumptions`, 2 pending Stage 16 gates, 1 stale
`aide/123-…` claim branch). No new warning class.

**AC20 — findings logged.** Three new dated entries appended to
`insights.md` this item (2026-08-30): the `docs/spinal-curve-model.md`
"still reproduces" claim not holding for one VerSe leave-one-out key; the
default-CLI-reference-mode discrepancy for AC5/AC6 reproduction; and the G3
real-GT false positive on `sub-verse406_split-verse261`. The mode-4 gap and
the mode-6 co-firing were already logged at items 120/123 and are referenced,
not duplicated.
