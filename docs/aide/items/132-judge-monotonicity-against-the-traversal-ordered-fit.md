# Item 132 — Judge monotonicity against a traversal-ordered smoothed fit so mode 4 fires

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 132
> **Objectives:** G2 (detect the catalogued failure modes), G7 (evaluable & regression-testable)
> **Suggested branch:** `aide/132-judge-monotonicity-against-the-smoothed`

---

## Description

`stage3.monotonic_consistency` is supposed to answer one question: *does the
anatomical (ascending-label) order of the vertebrae agree with the order in
which they lie along the spinal curve?* It does not, because the curve it
judges against is fitted **through the centroids in the very order under
test**. `pipeline.py` binds one in-sample fit — `fit_centroid_spline(ordered_centroids)`
(item 130) — and `compute_monotonic_consistency` reads each centroid's
`closest_u` on that curve. `splprep`'s chord-length parameterisation advances
along the input sequence, so when two adjacent levels are swapped the curve
simply doubles back and follows the swap, and `u` still increases. The check
is self-referential and cannot fail on a pure ordering defect.

**Measured on this checkout (2026-08-31, `run_qc` + `bundled_default_config()`
over `tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz`).** Labels 21 and
22 have exchanged voxel identities, so the ascending-label centroid sequence
zigzags in S: `z = 27, 107, 67, 147, 187` mm. The fitted curve tracks that
zigzag (sampled at `u = 0.1 … 0.5` it runs `z = 106 → 128 → 114 → 87 → 69`),
and the resulting parameters —

```
u = [0.000000561, 0.329247302, 0.525340908, 0.835605486, 0.996848947]
```

— increase at every consecutive pair. `is_monotonic` reads `True`,
`non_monotonic_pairs` is empty, `run_qc` emits **no finding at all** and the
verdict is `pass`. Stage 28's third acceptance criterion ("`is_monotonic` is
`False` on the mode-4 case") is therefore measured unmet, pinned by
`tests/test_125_stage28_validation.py::test_ac7_mode4_relabel_swap_is_monotonic_pinned_true`,
and `mode4_relabel_swap` is carried in `tests/corpus/manifest.json` as
`detection="reconstructed_record"` — the workaround that feeds a hand-rebuilt
monotonic-consistency record to `MislabelRule` because the shipped pipeline
cannot see the swap.

**The fix.** Judge the closest-point parameters against a curve fitted through
the centroids in their **geometric traversal order** rather than in the order
under test. The traversal order is the centroids sorted by their S coordinate
(`centroid_mm[2]`) in the direction the supplied sequence itself advances —
the same net-advance convention items 122 and 131 established for the tangent
arrays, so a caudal-first caller is not judged non-monotonic merely for
travelling the other way. That direction rule is not decoration: measured
2026-08-31, all 80 real VerSe19 training subjects advance *caudally* in
ascending-label order (net S advance `−26` to `−531` mm) while every synthetic
corpus fixture advances superiorly.

When the traversal order *is* the supplied order — every clean case, all 80
real VerSe19 subjects, every corpus fixture but this one — nothing changes at
all: no second fit is made, the caller's `fit` is used, and the `u_values` are
bit-identical to today's. When it differs, one reference
refit is made from the reordered centroids (same degree, same smoothing as the
supplied fit — only the input ordering differs), and the swapped levels then
read out of order.

Measured with that construction in place (same fixtures, same config):
`mode4_relabel_swap` gives

```
u = [0.000050774, 0.500000000, 0.250363632, 0.749636368, 0.999949226]
is_monotonic       = False
non_monotonic_pairs = [["L2", "L3"]]
```

and `run_qc` now emits `MislabelRule`'s ordering finding (Detector B, rule_id
`mislabel`) on labels `{21, 22}` with verdict `flagged-for-review` — exactly
the manifest's already-recorded `expected_rule_ids` / `expected_labels` /
`expected_verdict`. Every other corpus case's `u_values`, findings and verdict
are unchanged, character for character.

So the second half of the item is closing the loop: flip item 125's pin, move
`mode4_relabel_swap` to `detection="pipeline"` by regenerating the manifest
from the generator, and reconcile the tests across the suite that pin the old
reality (mode 4 is invisible to `run_qc`; the corpus catches 6 of 8 modes).

**What this item is NOT.**

- It does **not** change the spline formulation. Family, degree, smoothing and
  chord-length parameterisation are item 118's human-gated decision and item
  119's implementation; the reference refit reuses the supplied fit's own
  `degree` and `smoothing`. No gate is reopened.
- It does **not** change the fit that `pipeline.py` binds and hands to
  curvature, tangent orientations and the held-out offset layer. Item 130's
  "one in-sample fit per case" holds for every case whose anatomical order
  already is its traversal order; only a case that disagrees pays one extra
  fit, and only for the monotonicity check.
- It does **not** change the monotonicity *criterion*. `u[i] >= u[i+1]` still
  marks a pair, equal parameters still count as a violation, and no tolerance
  is introduced (see Assumptions).
- It does **not** tick Stage 28's acceptance box, or any Stage 29 box. Item
  135's replay does that.
- It does **not** rewrite signed text: `feature_docs.STATUS_OVERRIDES`'
  `is_monotonic` entry ("Should be wired into the sequence rule directly") and
  `golden-decision-table.md` are left exactly as they stand.
- It regenerates **no** golden snapshot: item 126 retired all eleven, and the
  corpus `.nii.gz` fixtures are untouched by this change.

## Acceptance Criteria

- [ ] **AC1: mode 4 is non-monotonic through the shipped record builder.**
  `extract_feature_record` on `tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz`
  (loaded through `synth.regression.loaded_seg_image`) yields
  `stage3.monotonic_consistency.is_monotonic is False`.

- [ ] **AC2: the swapped pair is named.** The same record's
  `stage3.monotonic_consistency.non_monotonic_pairs` equals `[["L2", "L3"]]`
  — exactly one pair, the two swapped levels, in that order.

- [ ] **AC3: the clean control stays monotonic.** `extract_feature_record` on
  `clean_control_seg.nii.gz` yields `is_monotonic is True` with
  `non_monotonic_pairs == []`.

- [ ] **AC4: no clean case's parameters move.** For every manifest case other
  than `mode4_relabel_swap`, the record's
  `stage3.monotonic_consistency.u_values` matches the pre-item values
  transcribed in this spec's Testing Strategy to within `1e-9` — the whole
  sequence, in order, one comparison per case. (The claim is that the curve
  did not move; the *exact* form of it is AC9's element-for-element identity
  against `compute_spline_offsets`.)

- [ ] **AC5: the traversal order is the S order in the sequence's own
  direction.** For a clean centroid sequence and for that same sequence
  reversed, each paired with **its own** `fit_centroid_spline` result,
  `compute_monotonic_consistency` returns `is_monotonic is True` in both
  cases — a caudal-first traversal is not a defect.

- [ ] **AC6: a swap is detected regardless of traversal direction.** A clean
  sequence with two adjacent centroids swapped, and the reversed copy of that
  swapped sequence, each paired with its own fit, both return
  `is_monotonic is False` with exactly one pair naming the same two levels.
  Assert the pair as an unordered set: the members appear in the *supplied*
  sequence's order, so the forward case measures `("L3", "L2")` and the
  reversed case `("L2", "L3")`.

- [ ] **AC7: an already-ordered sequence makes no second fit.**
  `compute_monotonic_consistency` on a sequence already in traversal order
  calls `fit_centroid_spline` zero times (patch-counted at
  `segfacet.features.consistency.fit_centroid_spline`), and on an
  out-of-order sequence calls it exactly once.

- [ ] **AC8: item 130's per-case fit count is unchanged for clean input.**
  `extract_feature_record` on a five-label clean spine still calls
  `fit_centroid_spline` exactly 6 times and on a three-label map exactly 1
  time (`tests/test_130_one_closest_point_search.py`'s AC18 tests pass
  unedited).

- [ ] **AC9: item 130's AC20 agreement survives for in-order input.** For a
  clean five-level spine and for one with a level displaced perpendicular to
  the spine axis, `compute_monotonic_consistency(centroids, fit).u_values`
  still equals `[o.closest_u for o in compute_spline_offsets(centroids, fit)]`
  element for element, exactly.

- [ ] **AC10: the reference refit inherits the supplied fit's parameters.**
  When a refit happens, it is made with the supplied `SplineFit`'s own
  `degree` and `smoothing` — asserted by patching
  `segfacet.features.consistency.fit_centroid_spline` and inspecting the
  keyword arguments it received.

- [ ] **AC11: an exact S tie does not by itself flag a pair.** A sequence
  whose two adjacent centroids share an identical S coordinate but differ in
  the transverse plane keeps its input order in the traversal sort (the sort
  is stable), so no refit is triggered and the sequence is still reported
  monotonic (measured `is_monotonic is True`, `non_monotonic_pairs == ()`).

- [ ] **AC12: the monotonicity criterion is unchanged.** Two centroids that
  resolve to the *same* `closest_u` are still reported as a non-monotonic
  pair (`u[i] >= u[i+1]`, equality included) — no tolerance band is
  introduced.

- [ ] **AC13: mode 4 fires `mislabel` through plain `run_qc`.** `run_qc` on
  the `mode4_relabel_swap` fixture with `bundled_default_config()` returns
  exactly one finding, with `rule_id == "mislabel"`,
  `labels == frozenset({21, 22})`, severity `flagged-for-review`, and a
  `reason` starting `"Vertebra ordering inconsistent with label:"`.

- [ ] **AC14: mode 4's verdict is `flagged-for-review`.** The same `run_qc`
  call's `case_result.verdict.overall.label` is `"flagged-for-review"`,
  matching the manifest's `expected_verdict`.

- [ ] **AC15: the corpus generator classifies mode 4 as pipeline-detected.**
  `segfacet.synth.corpus.CASE_RECIPE`'s `mode4_relabel_swap` entry has
  `detection == "pipeline"` and `reconstruction is None`.

- [ ] **AC16: the committed manifest records the new classification.**
  `tests/corpus/manifest.json`'s `mode4_relabel_swap` case has
  `detection == "pipeline"` and `reconstruction is None`.

- [ ] **AC17: the manifest's mode-4 `detail` no longer claims the pipeline
  misses the swap.** The case's `detail` string contains neither
  `"Not surfaced by plain run_qc"` nor `"reconstructed"`, and names the
  `mislabel` ordering detector as the path that catches it.

- [ ] **AC18: the manifest regenerates byte-identically and matches the
  committed file.** Two `write_corpus` calls into two fresh temp directories
  produce byte-identical `manifest.json` files, each byte-identical to
  `tests/corpus/manifest.json`
  (`tests/test_040_synthetic_corpus.py::test_ac16_…` passes unedited).

- [ ] **AC19: the corpus `.nii.gz` fixtures do not move.** Every regenerated
  fixture is byte-identical to its committed counterpart, and `git diff`
  reports no change under `tests/corpus/fixtures/`.

- [ ] **AC20: the detection partition is reconciled.**
  `tests/test_040_synthetic_corpus.py`'s `_RECONSTRUCTED_MODES == {8}` and
  `_PIPELINE_ONLY_MODES == {0, 1, 2, 3, 4, 5, 6, 7}`, and its AC8 test agrees
  with the regenerated manifest.

- [ ] **AC21: mode 4 is claimed as caught, at full sensitivity.**
  `tests/test_057_acceptance_stage7.py`'s `_PIPELINE_DETECTABLE_MODES`
  includes 4, `_RECONSTRUCTED_RECORD_MODES == (8,)`, and the per-mode
  sensitivity for mode 4 over the corpus cohort is `1.0`.

- [ ] **AC22: the honest overall corpus sensitivity is 7/8.** The corpus
  cohort's overall sensitivity is `7/8` — the seven pipeline-detectable
  failures caught, mode 8 still missed.

- [ ] **AC23: item 125's mode-4 pin is flipped, not widened.**
  `tests/test_125_stage28_validation.py`'s AC7 tests assert
  `is_monotonic is False`, `non_monotonic_pairs == [["L2", "L3"]]` and
  `detection == "pipeline"`, and each assertion message names item 132 as
  what changed it.

- [ ] **AC24: item 039's "run_qc does not surface the swap" pin is flipped.**
  `tests/test_039_identity_ordering_alignment_perturbations.py`'s AC11 test
  asserts that `run_qc` on the swapped map now fires `mislabel` on
  `{21, 22}` with verdict `flagged-for-review`, its assertion message naming
  item 132.

- [ ] **AC25: item 129's "no corpus case changes findings" baseline is
  reconciled.** `tests/test_129_coincident_centroids_and_held_out_floor.py`'s
  `_PRE_129_FINDINGS["mode4_relabel_swap"]` is `{("mislabel", (21, 22))}`,
  carrying a dated comment naming item 132, and its AC29 test passes.

- [ ] **AC26: the shared verdict+findings shape expectation is reconciled.**
  `tests/test_098_stray_components.py`'s
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode4_relabel_swap"]` records the
  `flagged-for-review` verdict and the single `mislabel` ordering finding,
  and every module that imports it (`test_089`, `test_090`, `test_094`,
  `test_102`, `test_108`, `test_123`) passes unedited on that account.

- [ ] **AC27: item 123's offset-calibration claim is preserved, not
  deleted.** `tests/test_123_recalibrate_and_regenerate.py`'s AC15 mode-4
  test still asserts that no *offset* (`"Vertebra misaligned from spinal
  curve:"`) `mislabel` finding fires on `mode4_relabel_swap`, distinguishing
  Detector A from the ordering Detector B that now does fire.

- [ ] **AC28: the catalogue text tells the truth about the reference
  curve.** `feature_docs`' `computation` strings for
  `stage3.monotonic_consistency.is_monotonic`,
  `.non_monotonic_pairs[]` and `.u_values[]` state that `u` is measured
  against a curve fitted in traversal order, and the committed
  `docs/aide/feature_catalogue.generated.json` / `.md` regenerate
  byte-identical to their committed copies.

- [ ] **AC29: the catalogue's measured content does not move.** The
  regenerated catalogue still carries **138** leaf entries and the
  `observed_summary` `{"constant-synthetic": 4, "degenerate": 0,
  "non-numeric": 39, "placeholder": 12, "unobserved": 0, "varies": 83}`, and
  each of the three `stage3.monotonic_consistency` entries keeps its
  pre-item `observed` block and `status` — only their `computation` strings
  change.

- [ ] **AC30: signed text is untouched.**
  `feature_docs.STATUS_OVERRIDES`' `stage3.monotonic_consistency.*` entries
  and `docs/aide/golden-decision-table.md` are byte-identical to their
  pre-item state.

- [ ] **AC31: the regression test fails before the fix.** With
  `compute_monotonic_consistency` reverted to judging against the supplied
  fit alone, AC1's test fails; the test module records this as a
  fails-before-the-fix obligation.

- [ ] **AC32: no Stage 28 or Stage 29 acceptance box is ticked here.**
  `docs/aide/progress.md` is unchanged by this item's diff (item 135 owns
  every tick).

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`), so each ambiguity
below was resolved with the most defensible default and recorded here.

- **The queue's "through the `sequence` rule" is a mis-naming; the rule is
  `mislabel`.** `heuristics/sequence.py`'s `SequenceRule` reads
  `relationships.out_of_order_labels` and never touches
  `monotonic_consistency`. The rule that consumes `non_monotonic_pairs` is
  `MislabelRule`'s Detector B (`heuristics/mislabel.py::_detect_order_inconsistency`,
  `rule_id == "mislabel"`), which is also what the manifest's mode-4
  `expected_rule_ids` has always said. Measured, not inferred: with the fix
  prototyped, `run_qc` emits one `mislabel` finding. This item targets
  `mislabel`; `sequence.py` is not in the authorised paths.

- **The traversal order is the S coordinate, in the supplied sequence's own
  net-advance direction.** `centroid_mm[2]` is the superior–inferior axis
  under this repo's RAS axis contract — which holds because `io.load_volume`
  reorients every input to `("R", "A", "S")` before the pipeline sees it
  (item 094), *not* because stored files happen to be RAS; measured
  2026-08-31, VerSe19's masks are not, and reading one with a bare
  `nibabel.load` puts S on some other axis entirely. Every consumer of this
  rule is downstream of the loader, so the contract holds where it is used.
  `orientation.py`'s item-122 convention rests on the same contract and
  already decides direction by
  `centroids[-1].centroid_mm[2] - centroids[0].centroid_mm[2] < 0`. The same
  strict `< 0` test is reused, so a net advance of exactly zero sorts
  ascending. A projection onto the centroid cloud's first principal axis was
  considered and rejected: it introduces a second, uncalibrated notion of
  "along the spine" for no measured benefit, since the S axis separates
  adjacent levels by a full inter-level spacing (~40 mm on the corpus) on
  every case in the corpus and the real cohort.

  Direction-awareness is load-bearing here rather than decorative: item 131's
  2026-08-31 `insights.md` entry records that
  `synth/clean_gt.py::build_clean_spine` stacks ascending labels along
  **ascending** S, so every in-repo synthetic fixture advances superiorly
  (`clean_control` puts `L1` at `S = 27` mm and `L5` at `S = 187` mm) while
  real VerSe19 input, ordered by ascending label, advances caudally. A rule
  that sorted ascending-S unconditionally would read every real subject as
  fully non-monotonic while every corpus fixture stayed green.

- **No tolerance band is added to the monotonicity criterion.** The queue
  asked what tie handling keeps a clean case from firing. Measured answer:
  none is needed. The smallest consecutive `u` gap across all nine corpus
  fixtures is `0.1655` (`mode8_force_overlap`), and across all 80 real
  VerSe19 training subjects it is `0.0314` (`sub-verse407_split-verse262`,
  20 levels — the densest subject in the cohort, and the floor scales as
  `~1/n`). Both are four to five orders of magnitude above
  `find_closest_point`'s `xatol` of `1e-6`. Introducing a band would also be a new
  uncalibrated threshold and would contradict the documented contract that
  equal parameters count as a violation (`MonotonicConsistency`'s docstring,
  `feature_docs`' `non_monotonic_pairs[]` computation text, and
  `tests/test_020_neighbour_consistency.py`'s AC4 group). The strict
  criterion is kept unchanged.

- **The reference refit inherits `degree` and `smoothing` from the supplied
  `SplineFit`.** `SplineFit` records both, and forwarding them means the
  reference curve differs from the caller's fit *only* in input ordering. For
  the pipeline's default path this is a no-op (`degree=3`, `smoothing=5.0` on
  a five-level case, measured), and it keeps a caller that supplied a custom
  degree — `tests/test_020_neighbour_consistency.py` passes `degree=3`
  explicitly — from being judged against a differently-shaped curve.

- **`test_020`'s existing AC4 expectations survive unchanged.** Prototyped
  and measured: the two adjacent-swap tests still return `is_monotonic
  False`, and `test_ac4_reversed_sequence_all_non_monotonic` still returns
  `False` because it supplies a fit built on the *un*-reversed sequence — a
  mismatched fit, not a direction question. AC5's direction-invariance claim
  is about a reversed sequence paired with its **own** fit, which is a
  different scenario and does not collide.

- **The manifest is regenerated, never hand-edited.** `write_corpus`
  (`src/segfacet/synth/corpus.py`) is the only writer; the `detection` /
  `reconstruction` fields come from `CASE_RECIPE` and the `detail` string
  from `RelabelSwapPerturbation`'s `Expectation` in
  `src/segfacet/synth/identity_ordering_alignment.py`. Editing
  `tests/corpus/manifest.json` directly would pass AC16 and fail AC18.

- **No `.gitattributes` change is needed.** `tests/corpus/manifest.json`
  already carries a `text eol=lf` pin (line 6) and already sits in
  `tests/test_111_golden_guard.py`'s `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES`, as
  do both generated catalogue files. This item adds **no** new byte-exact
  comparison against a committed float-carrying artifact, so item 127's
  enforced allowlist needs no entry — reuse the existing coverage
  (`test_040`'s AC16, `test_130`'s AC22) rather than writing a new
  byte-compare.

- **`monotonic_true_spatial_order` stays registered.** Mode 4 stops *using*
  the reconstruction technique, but `synth.regression.RECONSTRUCTIONS` keeps
  the entry: `tests/test_039_…`'s AC9/AC10 still exercise it directly, and
  `test_041`'s AC2 only checks that every reconstructed case's technique *is*
  a registry key, never that every key is used.

- **The observed-range column does not move.**
  `catalogue.iter_driver_records()` yields `clean`, `zero_label`,
  `single_label`, `overlaps`, `fragmented`, `missing_level`,
  `sequence_break` and `image_features` — no relabel-swap driver — and every
  one of those is already in traversal order, so no driver record's
  `monotonic_consistency` values change. AC29 pins that.

- **`aide check --queue 018`'s cross-item errors naming this item are moot,
  not unresolved.** Twenty-one of them pair item 132 against items 126, 127,
  129, 130 and 131 — every one of which is already ✅ merged. The check is
  order-blind: it reports "item 132 may change X, which item 130 pins" without
  knowing item 130's assertions already ran and passed on a tree that predates
  this change. The overlaps are real and intended (this item's whole
  deliverable is to move `manifest.json`'s mode-4 row and the catalogue's
  three `computation` cells), and nothing later in queue 018 — items 133, 134,
  135 — touches any of the pinned paths. Do not widen a pin or narrow an edit
  to silence them.

- **No human gate is raised.** The item changes neither the curve family, the
  smoothing law, nor the parameterisation, so item 118's gated formulation
  decision is not reopened, and nothing here needs an out-of-band approval.

## Implementation Steps

1. **`src/segfacet/features/consistency.py` — add the traversal-order
   helper.** A private `_traversal_order(centroids) -> List[int]` returning
   `sorted(range(n), key=lambda i: float(centroids[i].centroid_mm[2]),
   reverse=(net_advance_s < 0.0))`, where `net_advance_s` is
   `float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])`.
   Python's `sorted` is stable, so exact S ties keep their input order (AC11).
   Cross-reference `orientation.py`'s item-122 direction convention in the
   docstring rather than restating the rule.

2. **`src/segfacet/features/consistency.py` — pick the reference curve.** In
   `compute_monotonic_consistency`, after the existing `n < 2` guard, compute
   `order = _traversal_order(centroids)`. When `order == list(range(n))` use
   the supplied `fit` unchanged; otherwise call
   `fit_centroid_spline([centroids[i] for i in order], degree=fit.degree,
   smoothing=fit.smoothing)` once and use that. Import
   `fit_centroid_spline` at module level beside the existing
   `find_closest_point` import so AC7/AC10's patch point is
   `segfacet.features.consistency.fit_centroid_spline`.

3. **`src/segfacet/features/consistency.py` — search against the reference
   curve.** The `find_closest_point(pt, …).closest_u` loop and the
   `u[i] >= u[i+1]` pair loop are otherwise unchanged; only the curve
   argument moves from `fit` to the reference curve. Update the module
   docstring's section B and `MonotonicConsistency`'s / the function's
   docstrings to say what `u` is now measured against, why the ordering under
   test cannot shape that curve, and that a case already in traversal order
   makes no second fit.

4. **`src/segfacet/synth/identity_ordering_alignment.py` — retire the
   `detail` claim.** `RelabelSwapPerturbation`'s `Expectation.detail`
   currently reads "Not surfaced by plain run_qc (the ascending-label refit
   yields a monotonic spline parameter) -- asserted via a reconstructed
   monotonic-consistency record fed to MislabelRule directly (see item 039
   Assumptions)." Replace the second sentence with the measured truth: the
   swap is caught by `MislabelRule`'s ordering detector through plain
   `run_qc`, because the monotonicity check judges against a traversal-ordered
   curve (item 132). Leave the first sentence, the `failure_mode`,
   `expected_rule_ids`, `expected_labels` and `expected_verdict` alone — all
   four already describe the new reality.

5. **`src/segfacet/synth/corpus.py` — reclassify the case.** In
   `CASE_RECIPE`, `mode4_relabel_swap` becomes `detection="pipeline"` with no
   `reconstruction`. Update the module docstring's note about which cases are
   reconstructed (it currently names mode 4 alongside the pre-120 history of
   mode 1) with a dated line naming item 132.

6. **Regenerate the manifest.** Run `write_corpus` over `tests/corpus/`
   (never hand-edit `manifest.json`), then confirm `git diff --stat` shows
   `tests/corpus/manifest.json` alone — no `.nii.gz` fixture may move
   (AC19).

7. **`src/segfacet/feature_docs.py` — correct the three `computation`
   strings** for `stage3.monotonic_consistency.is_monotonic`,
   `.non_monotonic_pairs[]` and `.u_values[]` so each names the
   traversal-ordered reference curve. Touch nothing in `STATUS_OVERRIDES`
   (AC30).

8. **Regenerate the committed catalogue** (`docs/aide/feature_catalogue.generated.json`
   and `.md`) through the same path `tests/test_104_*` and item 130's AC22
   use, and confirm the diff is confined to those three `computation` cells
   (AC29).

9. **Reconcile the tests listed in Testing Strategy's "existing tests to
   reconcile"** — the partition constants, the sensitivity figures, and the
   four pins that record the old reality. Each flipped assertion carries
   item 132 in its message or an adjacent dated comment; none is deleted or
   widened into vacuity.

10. **Run the full suite** (`.venv/bin/python -m pytest`) and confirm green,
    then the Validation section's replays.

## Authorised paths

**May change:**

- `src/segfacet/features/consistency.py` — the traversal-order helper, the
  reference-curve choice and the docstrings (AC1–AC12).
- `src/segfacet/synth/corpus.py` — `CASE_RECIPE`'s mode-4 `detection` /
  `reconstruction` and the module docstring (AC15).
- `src/segfacet/synth/identity_ordering_alignment.py` —
  `RelabelSwapPerturbation`'s `Expectation.detail` only (AC17).
- `src/segfacet/feature_docs.py` — the three `stage3.monotonic_consistency`
  `computation` strings only; `STATUS_OVERRIDES` is out of bounds (AC28,
  AC30).
- `tests/corpus/manifest.json` — regenerated by `write_corpus`, never
  hand-edited (AC16–AC18).
- `docs/aide/feature_catalogue.generated.json` — regenerated (AC28, AC29).
- `docs/aide/feature_catalogue.generated.md` — regenerated (AC28, AC29).
- `tests/test_132_monotonicity_against_traversal_order.py` — this item's own
  test module.
- `tests/test_125_stage28_validation.py` — flip the AC7 mode-4 pin and its
  module-docstring line (AC23); this item is the authorised flipper, as the
  pin's own docstring instructs.
- `tests/test_039_identity_ordering_alignment_perturbations.py` — flip the
  AC11 "run_qc does not surface the swap" test and its docstring (AC24).
- `tests/test_129_coincident_centroids_and_held_out_floor.py` —
  `_PRE_129_FINDINGS`'s mode-4 entry and its comment (AC25).
- `tests/test_098_stray_components.py` —
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`'s mode-4 entry and its comment
  (AC26). No other constant or test in that module changes.
- `tests/test_123_recalibrate_and_regenerate.py` — narrow the AC15 mode-4
  test to Detector A and rename it accordingly (AC27).
- `tests/test_040_synthetic_corpus.py` — `_RECONSTRUCTED_MODES`,
  `_PIPELINE_ONLY_MODES` and the module-docstring line naming modes 1/4/8
  (AC20).
- `tests/test_057_acceptance_stage7.py` — `_PIPELINE_DETECTABLE_MODES`,
  `_RECONSTRUCTED_RECORD_MODES`, the 6/8 sensitivity test (value, name and
  docstring) and the module-docstring line quoting `6/8` (AC21, AC22).
- `docs/aide/items/132-judge-monotonicity-against-the-traversal-ordered-fit.md`
  — this spec's Decisions log.
- `docs/aide/insights.md` — append-only capture of out-of-scope findings.

**Asserts against:**

- `tests/corpus/fixtures/*.nii.gz` — AC1–AC4, AC13, AC14 and AC19 read every
  committed fixture and AC19 pins that none of their bytes move; the
  regeneration in step 6 must reproduce them unchanged.
- `src/segfacet/pipeline.py` — AC8 counts `fit_centroid_spline` calls per
  `extract_feature_record` through it; unchanged by this item.
- `src/segfacet/features/spline.py` — AC7/AC10 patch and inspect
  `fit_centroid_spline`'s signature and `SplineFit`'s `degree`/`smoothing`
  fields; unchanged by this item.
- `src/segfacet/features/spline_offset.py` — AC9 compares against
  `compute_spline_offsets`' `closest_u`; unchanged by this item.
- `src/segfacet/heuristics/mislabel.py` — AC13 pins Detector B's `rule_id`,
  labels and reason prefix; unchanged by this item.
- `tests/test_130_one_closest_point_search.py` — AC8 and AC9 require its
  AC18 and AC20 tests to pass **unedited**; this item does not change that
  module.
- `tests/test_111_golden_guard.py` — the Assumptions' claim that no
  allowlist entry is needed is proved by that module passing unedited.
- `docs/aide/golden-decision-table.md` — AC30 pins it byte-identical.
- `docs/aide/progress.md` — AC32 pins it unchanged by this item.

## Testing Strategy

New module: **`tests/test_132_monotonicity_against_traversal_order.py`**, one
focused test per AC, plus the adversarial cases below.

**Per-AC notes where the mechanics are not obvious.**

- **AC4 (no clean case's parameters move).** The pre-item values, measured
  2026-08-31 through `run_qc(loaded_seg_image(case), bundled_default_config())`,
  are a module constant in the new test file:

  | case | `u_values` |
  |---|---|
  | `clean_control` | `0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226` |
  | `mode1_displace` | `0.000000561, 0.234074709, 0.500000025, 0.765925291, 0.999999440` |
  | `mode2_fragment` | `0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226` |
  | `mode3_inject_islands` | `0.000049227, 0.250369752, 0.500000000, 0.749630248, 0.999950773` |
  | `mode5_remove_level` | `0.000000561, 0.250621894, 0.749378106, 0.999999440` |
  | `mode6_crop_at_border` | `0.000000561, 0.237035382, 0.500000024, 0.762964618, 0.999999440` |
  | `mode7_sequence_break` | `0.000050774, 0.250363632, 0.500000000, 0.749636368, 0.999949226` |
  | `mode8_force_overlap` | `0.000061555, 0.165598814, 0.437861146, 0.718006432, 0.999999440` |

  Compare with `pytest.approx(..., abs=1e-9)` rather than `==` on the
  literals: the values above are 9-decimal transcriptions of live floats, and
  the claim is that the curve did not move, not that a decimal literal
  round-trips. The exact form of that claim is AC9's identity, which needs no
  transcribed constant at all.

- **AC7/AC10 (fit count and forwarded parameters).** `monkeypatch.setattr`
  `segfacet.features.consistency.fit_centroid_spline` with a wrapper that
  records `(args, kwargs)` and delegates to the real function. Assert zero
  calls for an in-order sequence, one call for an out-of-order one, and that
  the recorded `kwargs` carry the supplied fit's `degree` and `smoothing`.
  This is why step 2 imports the symbol at module level.

- **AC11 (S tie).** Build five centroids at `z = 0, 10, 10, 20, 30` mm with
  distinct `x` values. Assert the traversal sort returns the identity
  permutation and no refit is made. Deliberately *not* asserted: whether the
  tie itself is flagged as non-monotonic — that is AC12's separate,
  pre-existing contract.

- **AC12 (equal parameters still violate).** Reuse the existing contract's
  shape rather than inventing a fixture: two centroids placed symmetrically
  about the curve so both resolve to the same `closest_u`, asserted to appear
  as a pair. If a same-`u` pair proves impossible to construct stably, fall
  back to asserting the source-level criterion (`>=`, not `>`) via the
  module's AST — and say so in the Decisions log.

- **AC22 (7/8).** Recompute from the corpus cohort metrics, not from a
  transcribed constant, and assert `pytest.approx(7.0 / 8.0)`.

- **AC29 (catalogue measured content).** Regenerate into `tmp_path`, load the
  fresh JSON, and assert the leaf-entry count, the `observed_summary` dict,
  and the three entries' `observed`/`status` values against constants
  transcribed here from the **pre-item** committed file — never by re-reading
  a file this item rewrites. The pre-item `computation` strings — what step 7
  replaces, and what the test asserts is no longer present — are:
  `is_monotonic` → `"False as soon as u[i] >= u[i+1] anywhere in the ordered
  sequence."`; `non_monotonic_pairs[]` → `"Consecutive (level_a, level_b)
  pairs where u[i] >= u[i+1]; equal u values count as a violation too."`;
  `u_values[]` → `"The closest_u value computed for every vertebra in the
  ordered centroid sequence."`. Their pre-item `observed` blocks are
  non-numeric for the first two, and for `u_values[]`:
  `count 24`, `minimum 5.6119e-07`, `maximum 0.999999`, `span 0.999999`,
  `verdict "varies"`, sources `clean, fragmented, missing_level, overlaps,
  sequence_break`.

- **AC31 (fails before the fix).** Assert the *behaviour*, not a source
  string: a test that reproduces the pre-item construction inline
  (`find_closest_point` against the supplied `fit`) on the mode-4 centroids
  and asserts that construction yields a monotonic sequence — documenting
  precisely what the fix changed and failing loudly if the old and new
  constructions ever converge.

**Adversarial and edge cases.**

- Two centroids only (`n == 2`): both orderings are trivially traversal
  order; assert no refit and `is_monotonic is True` for a clean pair.
- `n < 2`: the existing `ValueError` and its message are unchanged.
- Determinism: two `compute_monotonic_consistency` calls on the same inputs
  return equal `MonotonicConsistency` values, including for the refit path.
- Immutability: neither the `centroids` sequence nor any `LabelCentroid` is
  mutated, and the supplied `SplineFit` is not rebound or modified.
- A doubly-swapped sequence (two disjoint adjacent swaps in a seven-level
  spine) must name **both** pairs — measured `(("L2", "L1"), ("L6", "L5"))`.
  Note the pair members appear in the *supplied* order, so a swapped pair
  reads `(later_level, earlier_level)` when the swap put them that way; the
  reversed copy of a swapped sequence therefore names the same two levels in
  the opposite order (AC6).
- A sequence whose S coordinates are strictly monotonic but whose transverse
  excursion is large (the scoliotic shape): still monotonic, no refit.
- `run_qc` on `mode4_relabel_swap` twice returns equal monotonicity blocks
  and equal findings (determinism through the pipeline).

**Existing tests to reconcile** — each pins the pre-item reality and will
fail on the first validation round otherwise:

| module | what pins the old behaviour | reconciliation |
|---|---|---|
| `tests/test_125_stage28_validation.py` | `test_ac7_mode4_relabel_swap_is_monotonic_pinned_true` (`is_monotonic is True`, `non_monotonic_pairs == []`); `test_ac7_mode4_manifest_detection_still_reconstructed_record`; module-docstring AC7/AC15 lines | flip both, per the pin's own instruction ("update the pin, don't just widen it"), naming item 132 |
| `tests/test_039_identity_ordering_alignment_perturbations.py` | `test_ac11_relabel_swap_run_qc_does_not_surface_swap` (`findings == ()`, verdict `pass`) | flip to the measured `mislabel` finding on `{21, 22}`, naming item 132 |
| `tests/test_129_coincident_centroids_and_held_out_floor.py` | `_PRE_129_FINDINGS["mode4_relabel_swap"] = set()`, asserted by `test_ac29_no_corpus_case_changes_findings` | set to `{("mislabel", (21, 22))}` with a dated comment |
| `tests/test_098_stray_components.py` | `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode4_relabel_swap"] = {"verdict": "pass", "findings": []}`, imported by six modules | record the new verdict and finding once; the six consumers need no edit |
| `tests/test_123_recalibrate_and_regenerate.py` | `test_ac15_mode4_relabel_swap_fires_no_mislabel_finding` (no `mislabel` finding at all) | narrow to Detector A's reason prefix and rename |
| `tests/test_040_synthetic_corpus.py` | `_RECONSTRUCTED_MODES = {4, 8}`, `_PIPELINE_ONLY_MODES` without 4, docstring line | move mode 4 across |
| `tests/test_057_acceptance_stage7.py` | `_PIPELINE_DETECTABLE_MODES = (1,2,3,5,6,7)`, `_RECONSTRUCTED_RECORD_MODES = (4, 8)`, `test_overall_corpus_sensitivity_is_six_of_eight_not_over_claimed`, docstring line 46 | add mode 4, drop it from the reconstructed tuple, 6/8 → 7/8 (rename the test) |

**Checked and expected to need no edit** (verify, do not pre-emptively
change): `tests/test_041_regression_suite.py` (its partitions are derived
from the manifest, and mode 4 satisfies the pipeline path's AC4–AC6
assertions as measured); `tests/test_042_golden_determinism.py` (AC16
parameterises over the manifest's reconstructed cases and still has mode 8);
`tests/test_020_neighbour_consistency.py` (AC3/AC4 outcomes all reproduced
under the new construction — see Assumptions); `tests/test_130_one_closest_point_search.py`
(AC18/AC20 reproduced); `tests/test_121_tangent_orientation.py`,
`tests/test_122_signed_curvature.py`, `tests/test_131_tangent_direction_normalisation.py`
(they pin tangent/curvature arrays from the *unchanged* pipeline fit);
`tests/test_099_per_mode_metrics.py`, `tests/test_101_per_mode_cohort.py`,
`tests/test_102_stage18_validation.py` (per-mode metrics are computed against
ground truth, not `run_qc` verdicts); `tests/test_126_golden_retirement.py`;
`tests/test_111_golden_guard.py`. `tests/test_120_leave_one_out_offset.py`'s
`_PRE_120_VERDICTS_AND_FINDINGS` names mode 4 as `("pass", [])` but is
**unused** by any test in that module — leave the historical record alone.

## Validation

Beyond the suite, replay the behaviour the stage cares about. Each command is
run from the repo root with the venv bootstrapped.

1. **The swap is caught end-to-end through the CLI.**
   `.venv/bin/segfacet run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz --no-reference --out <tmp>`
   (the console script installed by `pip install -e .[dev]`; there is no
   `segfacet/__main__.py`, so `python -m segfacet` does not work, and both
   `--scan` and `--seg` are required — the trap item 130's spec hit)
   and inspect the JSON report: `verdict` is `flagged-for-review` and the
   findings list carries the `mislabel` ordering finding naming labels 21 and
   22. `--no-reference` is required — see `CLAUDE.md`'s Gotchas: the default
   real-VerSe19 reference is not calibrated for the tiny synthetic fixtures
   and floods a bare CLI run with `bounds`/`reference_delta` findings.
2. **The clean control still fires nothing** through the same CLI invocation
   on `clean_control_seg.nii.gz`: empty findings, verdict `pass`.
3. **The real cohort stays monotonic.** Over every subject discovered by
   `sorted(root.rglob("*_seg-vert_msk.nii.gz"))` beneath the VerSe19 training
   cohort, `compute_monotonic_consistency` returns `is_monotonic is True`,
   no subject triggers a reference refit (each subject's label order already
   is its traversal order), and no subject's `u_values` change.

   **Already measured, 2026-08-31, on the full cohort while specing this
   item** — the replay confirms it after the change lands, and any deviation
   is a regression, not a discovery: 80 subjects discovered, 4 to 20 levels
   each; **0** triggered a reference refit, **0** were non-monotonic before or
   after, **0** had any `u_values` change, and the smallest consecutive `u`
   gap across the whole cohort was `0.0314` on `sub-verse407_split-verse262`
   (20 levels).

   **Load every mask through `segfacet.io.load_volume(path,
   integer_labels=True)`, never `nibabel.load`.** VerSe's masks are not
   stored RAS-resolving; `load_volume` reorients to `("R", "A", "S")` (item
   094) and the pipeline only ever sees that output, so `centroid_mm[2]` is
   the S axis only after it. Measured 2026-08-31 on the first eight
   subjects: through `load_volume` the net S advance runs `−26` to `−364` mm
   (caudal-first, as ascending-label order on real anatomy should be), no
   subject refits, and every one stays monotonic; through a raw `nibabel.load`
   the same eight report a net advance of `−6.5` to `+2.1` mm — the S axis is
   not axis 2 at all — and seven of the eight come out spuriously
   non-monotonic. A sweep that skips the loader measures nothing.

   **Environment:** the cohort is a gitignored local checkout addressed by
   `SEGFACET_VERSE_COHORT` (or the `dataset-verse19training` symlink); there
   is no `[validation]` profile for it, so the established `_real_verse_root`
   + `requires_real_verse` skip-clean pattern applies. When the cohort is
   absent, record this replay as **❓ Unverified** with that reason — never a
   silent pass.
4. **Manifest regeneration is a no-op on a second run.** Run `write_corpus`
   into two fresh temp directories after step 6 and confirm
   `git status --porcelain tests/corpus/` is empty afterwards.

## Dependencies

- **Item 126** (✅) — the golden retirement. Because all eleven whole-record
  snapshots are gone, mode 4's changed verdict regenerates nothing; the
  replacement verdict+findings shape expectation
  (`_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`) is the single place AC26 updates.
- **Item 127** (✅) — the committed-artifact comparison helper and the
  enforced byte-exact allowlist this item must not need to extend.
- **Item 129** (✅) — the coincident-centroid pre-check that keeps a
  degenerate case out of Stage 3 before the monotonicity check runs, and the
  `_PRE_129_FINDINGS` baseline AC25 reconciles.
- **Item 130** (✅) — the shared `find_closest_point` and the single in-sample
  fit this item builds on; its Decisions log names this change as "item 132's
  territory" and its AC18/AC20 are the invariants AC8/AC9 preserve.
- **Item 131** (✅) — the traversal-direction convention (net advance in `+S`)
  that AC5's direction rule reuses rather than reinventing.

**Downstream:** item 135 (Stage 29 validation) replays this change to tick
Stage 28's unticked mode-4 acceptance half and Stage 29's second acceptance
box; neither tick happens here.

## Decisions & Trade-offs

To be updated during implementation.
