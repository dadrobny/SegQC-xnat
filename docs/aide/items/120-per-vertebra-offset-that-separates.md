# Item 120 — Per-vertebra offset that separates, with its direction components

> **Created:** 2026-08-28 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation (deliverable **D3**)
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 120
> **Objectives:** G2 (detect catalogued failure modes), G7 (evaluable & regression-testable)
> **Suggested branch:** `aide/120-per-vertebra-offset-that-separates`

---

## Description

Item 119 replaced the interpolating spline with a smoothing fit
(`make_splprep`, `s = n_points`). That changed **how the curve is fitted**; it
deliberately did not change **how a per-label offset is evaluated against it**,
and pinned `src/segfacet/pipeline.py` byte-identical to prove so (item 119's
AC22). The consequence is measurable on this branch: `stage3
.per_label_offsets[].offset_mm` is still an *in-sample* measurement, so a
vertebra displaced 18.4 mm off the spinal curve reads **1.570 mm** on the
`mode1_displace` corpus case — the smoothing fit absorbs it, exactly the
circularity item 118 diagnosed, merely reduced rather than removed.
`MislabelRule`'s offset detector still cannot fire through `run_qc` on any
input.

**This item makes the per-label offset a held-out measurement, in the
pipeline.** After it, `offset_mm` for a level is that level's closest-approach
distance to a curve the level itself did not shape, so a displacement shows up
at roughly its true magnitude (mode 1: **18.719 mm**, against an applied
displacement of 18.4 mm). `mislabel` fires through plain `run_qc` naming the
displaced label; `mode1_displace` stops needing its `reconstructed_record`
workaround and becomes a `pipeline` case; the corpus's honest
pipeline-detection count moves from 5 of 8 modes to 6 of 8.

**Who owns the promotion.** [`docs/spinal-curve-model.md`](../../spinal-curve-model.md)'s
"Breaking circularity" section says item **119** "should make it the actual
per-label evaluation method for `stage3.per_label_offsets`", while
[`queue-017.md`](../queue/queue-017.md) assigns "promote it from the test
harness into the pipeline" to item **120**. The disagreement is recorded in
[`insights.md`](../insights.md) (2026-08-27). It is settled by what shipped:
item 119 is ✅ merged with an acceptance criterion (its AC22) asserting
`pipeline.py` unchanged, and its Assumptions state the split as "119 changes
the **fit**, 120 changes the **evaluation**". **Item 120 owns the promotion**,
and it is this item — not item 119 — that retires item 119's AC22 scope fence.
The decision document is not edited here: it is item 118's deliverable and a
signed record of a modelling decision, and the item numbers inside it are the
drift the insight already captures.

**What "leave-one-out" has to mean to work.** The queue proposes lifting
`synth/regression.py::_recon_leave_one_out_offset` — drop the level, refit
through the rest, measure the dropped level — into the pipeline. That helper
measures **one** level (the perturbation's known target) and is correct for
that use. Applied to *every* level it produces two failures, both measured on
this branch before this spec was written:

- **Terminal-level truncation.** Dropping the cranial-most or caudal-most level
  shortens the curve's parameter domain, and the closest-point search is bounded
  to `u` in `[0, 1]`, so the dropped level's nearest curve point is an endpoint
  a whole inter-level spacing away. On the **clean** `clean_control` fixture,
  L1 and L5 read **40.200 mm** — a clean spine flagged at any threshold below
  that. Item 118 knew the endpoint case was different and excluded it from its
  own measurements: `scripts/compare_curve_candidates.py`'s
  `_measure_clean_pass_through` loops `range(1, len(centroids) - 1)` with a
  comment saying why. A pipeline feature has no such luxury — every level needs
  a value.
- **Outlier cross-talk.** The displaced level remains in every *other* level's
  held-out fit, so it bends those curves too. On `mode1_displace` the
  neighbours L2/L4 read **25.036 mm** and the terminals **33.196 mm**, all
  *above* the displaced level's own 18.869 mm — the strongest signal lands on
  the wrong labels, and `synth.regression.offending_labels_match` (which
  requires set equality against `expected_labels`) fails.

So this item promotes leave-one-out with two corrections the measurements
force, both of which keep the estimator's meaning — the level under test does
not shape the curve it is judged against — while removing the artefacts:

1. **Withhold by down-weighting instead of dropping, over a parameterisation
   computed from all present centroids.** The withheld level stays in the
   chord-length `u` and in the knot placement, so the curve's domain never
   shrinks and no extrapolation is needed — but its weight is negligible, so it
   cannot pull the fit. Clean `clean_control` terminals fall from 40.200 mm to
   **0.109 mm**.
2. **Withhold the case's dominant outlier as well.** A reference fit through
   all centroids at equal weight identifies the single most-deviant level;
   every per-level refit withholds that level too, so one broken vertebra
   cannot contaminate its neighbours' readings. On `mode1_displace` the
   neighbours fall from 25.036 mm to **8.701 mm** while the displaced level
   holds at **18.719 mm**, making it the strict maximum.

The result on the committed corpus, measured on this branch: the clean control
peaks at 0.674 mm, `mode1_displace`'s displaced label reads 18.719 mm, and no
other case's non-target level exceeds 8.701 mm.

**Direction components.** `dx_mm`, `dy_mm` and `dz_mm` are computed and
catalogued today and read by no rule. They become meaningful here because they
are measured against a curve the level did not shape, and their anatomical
reading rests on a contract that is currently implicit: `io.load_volume`
reorients every volume to `("R", "A", "S")` (`io.py`'s `_TARGET_AXCODES`), and
`compute_centroid` derives `centroid_mm` as `centroid_voxel * spacing` with no
affine of its own — so, and **only** so, array axis 0 is left–right, axis 1
anterior–posterior and axis 2 cranio-caudal. This item states that contract
where the feature is defined and has `mislabel` read the components, naming the
dominant displacement direction in its finding text.

**Not in scope.** The **fit** — item 119's; `fit_centroid_spline`'s default
behaviour is unchanged here, so item 119's AC7/AC8 pass-through numbers and
stage 28's 1.0 mm pass-through bound are untouched. `mislabel`'s
`max_offset_mm` threshold and `reference_verse_v1.json` (item 123's).
Orientation and `principal_axis` (item 121's). Curvature (item 122's, merged).
`monotonic_consistency` and the mode-4 signal — nothing here makes
`is_monotonic` false, and `mode4_relabel_swap` stays a `reconstructed_record`
case. Per-point weighting as a *modelling* choice — down-weighting
field-of-view-clipped vertebrae is deferred by the decision document and stays
deferred (see [Assumptions](#assumptions)); the weights used here are a
hold-out mechanism, not an anatomical prior.

## Acceptance Criteria

- [ ] **AC1: The fit accepts an explicit parameterisation.**
  `fit_centroid_spline(centroids, u=<sequence>)` returns a `SplineFit` whose
  `u` equals the supplied values, and passing the `u` of a default fit of the
  same centroids reproduces that fit's `spline.t` and `spline.c` array-equal.

- [ ] **AC2: The fit accepts per-point weights, validated.**
  `fit_centroid_spline(centroids, weights=<sequence>)` accepts a
  strictly-positive sequence of length `n_points`; a wrong-length sequence, and
  a sequence containing a zero, a negative value or a NaN, each raise
  `ValueError` whose message names the offending length or value, not a raw
  FITPACK message.

- [ ] **AC3: A held-out per-label offset function is public.**
  `segfacet.features.spline_offset` exports
  `compute_leave_one_out_spline_offsets(centroids, spacing_mm=None, *,
  backend=None)`, which returns a list of `VertebralSplineOffset` — one per
  input centroid, in input order, with the same field set `compute_spline_offsets`
  returns.

- [ ] **AC4: The held-out curve keeps the full parameter domain.** For a clean
  5-level spine, every record returned by
  `compute_leave_one_out_spline_offsets` has `0.0 <= closest_u <= 1.0` and no
  record's `closest_u` is exactly `0.0` or `1.0` — the terminal levels are
  measured against curve interior, not against a truncated endpoint.

- [ ] **AC5: A level cannot shape the curve it is judged against.** For a
  5-level spine with one interior centroid displaced 18 mm along a non-stacking
  axis, that level's `offset_mm` from `compute_leave_one_out_spline_offsets` is
  within `2.0` mm of the applied displacement, where its `compute_spline_offsets`
  (in-sample) reading is below `2.0` mm in total.

- [ ] **AC6: The dominant outlier is withheld too, chosen deterministically.**
  On `mode1_displace`'s committed fixture the displaced label 22 has the
  strictly largest `offset_mm` of the five levels, exceeding the next largest
  by at least `9.0` mm. *(Measured: 18.719 mm against 8.701 mm.)* The level
  chosen as dominant outlier is the one with the largest in-sample offset, ties
  broken by ascending label.

- [ ] **AC7: Fewer than four levels falls back to the in-sample measurement.**
  For 2 and 3 centroids, `compute_leave_one_out_spline_offsets` returns records
  equal to `compute_spline_offsets`' for the same inputs, and raises nothing.
  *(Below four levels, withholding two of them leaves too few effective points
  for the refit to mean anything.)*

- [ ] **AC8: The held-out offsets are deterministic.** Two successive
  `compute_leave_one_out_spline_offsets` calls on the same centroid sequence
  return equal lists, field for field.

- [ ] **AC9: The clean-GT ceiling is bounded.** Over
  `synth.clean_gt.build_clean_spine` at level counts 2, 3 and 5 × spacings
  `(1,1,1)`, `(1,1,2)`, `(0.8,0.8,1)` at 6 mm curve amplitude, the maximum
  held-out `offset_mm` is `<= 2.0` mm. *(Measured on this branch:
  `1.072494` mm, at 5 levels × `(0.8, 0.8, 1.0)`. This is a **different
  quantity** from the in-sample pass-through that stage 28's 1.0 mm acceptance
  bound governs — see [Assumptions](#assumptions).)*

- [ ] **AC10: The fit itself is unchanged.** For the curved 6-level and
  anisotropic 5-level fixtures of `tests/test_017_centroid_spline_fit.py`, a
  default `fit_centroid_spline` call's `smoothing`, `degree`, `n_points`, `u`,
  `spline.t` and `spline.c` are unchanged from their pre-120 values, and
  `tests/test_017_centroid_spline_fit.py` stays green **unmodified**.

- [ ] **AC11: The pipeline evaluates offsets held-out.**
  `extract_feature_record` obtains `stage3.per_label_offsets` from
  `compute_leave_one_out_spline_offsets`, and `src/segfacet/pipeline.py`
  contains no call to `compute_spline_offsets`.

- [ ] **AC12: The serialised record's shape is unchanged.** The sorted set of
  leaf paths produced by `python -m segfacet.catalogue` is unchanged from its
  pre-120 value — this item adds and removes no feature path — and every
  `per_label_offsets[]` entry still carries exactly `label`, `level_name`,
  `closest_u`, `offset_mm`, `offset_voxel`, `dx_mm`, `dy_mm`, `dz_mm`.

- [ ] **AC13: The in-sample function keeps its meaning.**
  `compute_spline_offsets` is unchanged in signature and semantics, and
  `tests/test_018_per_vertebra_spline_offset.py` stays green **unmodified**.

- [ ] **AC14: `mislabel` reads the direction components.** A `MislabelRule`
  offset finding's `reason` names the dominant displacement direction as one of
  `"left-right"`, `"anterior-posterior"` or `"cranio-caudal"`, selected as the
  largest of `|dx_mm|`, `|dy_mm|`, `|dz_mm|` with ties broken in that order;
  the reason still starts with `"Vertebra misaligned from spinal curve:"`.

- [ ] **AC15: `mislabel` tolerates a record with no direction components.** An
  offset entry carrying only `label`, `level_name` and `offset_mm` still
  produces a finding, with the direction clause omitted and no exception —
  `tests/test_033_mislabel.py` stays green **unmodified**.

- [ ] **AC16: The offset threshold is untouched.** `heuristics/mislabel.py`'s
  `_DEFAULT_MAX_OFFSET_MM` is still `15.0`; the recalibration is item 123's.

- [ ] **AC17: Both threshold margins hold and are asserted.** On the committed
  corpus, the largest `stage3.per_label_offsets[].offset_mm` over every case
  that must not raise a `mislabel` offset finding is strictly below `15.0`, and
  `mode1_displace`'s label-22 offset is strictly above it. *(Measured:
  clean-control ceiling 0.674 mm — a 14.3 mm lower margin; displaced reading
  18.719 mm — a 3.7 mm upper margin.)*

- [ ] **AC18: `mislabel` fires through plain `run_qc` on the mode-1 case,
  naming exactly the displaced label.** For `mode1_displace`,
  `synth.regression.pipeline_findings` contains at least one `mislabel` finding
  whose reason starts with the misalignment tag, and the union of `labels` over
  all its `mislabel` findings is exactly `{22}`.

- [ ] **AC19: The clean control still fires nothing.**
  `synth.regression.pipeline_findings(clean_control)` is empty and its verdict
  is `pass`.

- [ ] **AC20: `mode1_displace` no longer needs a reconstruction.** Its entry in
  `tests/corpus/manifest.json` has `detection == "pipeline"` and a falsy
  `reconstruction`, and its `detail` prose no longer claims the mode is hidden
  from `run_qc`.

- [ ] **AC21: The mode-1 reconstruction workaround is retired.**
  `segfacet.synth.regression.RECONSTRUCTIONS` has no `"leave_one_out_offset"`
  key and the module defines no `_recon_leave_one_out_offset`; the two
  remaining techniques (`monotonic_true_spatial_order`, `overlap_mask_stack`)
  are unchanged.

- [ ] **AC22: Every corpus case still verifies.**
  `synth.regression.verify_case(case)` is `True` for all nine cases in
  `tests/corpus/manifest.json`.

- [ ] **AC23: The border-crop case's new mislabel finding is deliberate and
  pinned.** `mode6_crop_at_border` now also emits a `mislabel` offset finding
  on label 22 through plain `run_qc` — its cropped centroid genuinely sits
  `17.507` mm off the curve — while its verdict stays `flagged-for-review` and
  its designated `border` finding still resolves to exactly `{22}`.

- [ ] **AC24: The corpus's pipeline-detection count is 6 of 8.** Cohort metrics
  over the committed corpus report overall sensitivity `6/8`, with per-mode
  sensitivity `1.0` for modes 1, 2, 3, 5, 6 and 7 and `0.0` for modes 4 and 8.

- [ ] **AC25: The nine corpus goldens are regenerated and reproducible.** For
  every case, `synth.golden.check_case_golden(case)` is `True`, and two
  `write_goldens` runs into different directories are byte-identical to each
  other.

- [ ] **AC26: The regeneration moves no verdict.** For all nine regenerated
  goldens, `verdict` is unchanged from its pre-120 committed value, and every
  changed JSON leaf lies under `features.stage3` or under `findings`.

- [ ] **AC27: The Stage-3 report golden is regenerated.**
  `tests/golden/022_stage3_report.json` matches
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`'s produced text
  exactly, with that test unmodified.

- [ ] **AC28: The bundled default reference artifact is rebuilt.**
  `src/segfacet/reference/reference_default.json` is byte-identical to a fresh
  `python -m segfacet.reference.artifact` build, and its per-level
  `spline_offset_mm` distribution has a non-zero mean.

- [ ] **AC29: `reference_verse_v1.json` is untouched.**
  `src/segfacet/reference/reference_verse_v1.json` is byte-identical to its
  pre-120 state; rebuilding it needs the real VerSe cohort and is item 123's.

- [ ] **AC30: The generated catalogue is regenerated and its prose is true.**
  `docs/aide/feature_catalogue.generated.json` and `.md` are byte-identical to
  a fresh `python -m segfacet.catalogue` run, and `feature_docs.py`'s "Spline
  Offset" group note describes a held-out evaluation and states the RAS axis
  contract for `dx_mm`/`dy_mm`/`dz_mm`.

- [ ] **AC31: The RAS contract is stated where the feature is defined.**
  `features/spline_offset.py`'s module docstring names `io.load_volume`'s
  `("R", "A", "S")` reorientation and `compute_centroid`'s affine-free
  `centroid_voxel * spacing` as the two facts that make `dx_mm`/`dy_mm`/`dz_mm`
  anatomically readable, and a test asserts that `segfacet.io`'s target axcodes
  are still `("R", "A", "S")` so the contract cannot silently lapse.

## Assumptions

- **Item 120 owns the leave-one-out promotion; the decision document is not
  edited.** `docs/spinal-curve-model.md` assigns it to item 119 and
  `queue-017.md` to item 120. Item 119 shipped ✅ with `pipeline.py` pinned
  byte-identical (its AC22) and its Assumptions recording the 119-fit /
  120-evaluation split, so the shipped repository already answers the question.
  The queue is the authority on item boundaries; the decision document is a
  signed record of a *modelling* decision, and rewriting its item numbers from
  inside a later item would edit a completed deliverable to tidy a
  cross-reference. The drift itself is already captured in `insights.md`
  (2026-08-27) for triage at the queue boundary.

- **Naive per-level leave-one-out is not shippable, and the two corrections are
  this item's design decision.** Measured on this branch under item 119's fit,
  dropping each level in turn and refitting gives, on the **clean**
  `clean_control` fixture, `L1 = 40.200`, `L2 = 1.008`, `L3 = 0.675`,
  `L4 = 1.008`, `L5 = 40.200` mm; and on `mode1_displace`, `L1 = 33.196`,
  `L2 = 25.036`, `L3 = 18.869`, `L4 = 25.036`, `L5 = 33.196` mm. Both are
  unusable — the first flags a clean spine, the second flags four innocent
  labels harder than the guilty one. The domain-preserving down-weighted refit
  with dominant-outlier withholding described above is what this item ships
  instead. It is still leave-one-out in the sense the human gate approved (the
  point under test never gets a chance to bend the curve toward itself); it
  differs only in *how* the point is withheld. No new human gate is raised: the
  clinical question the gate answered — how much curvature is normal anatomy —
  is unchanged by the mechanism.

- **The weights used here are a hold-out mechanism, not the deferred anatomical
  weighting.** `docs/spinal-curve-model.md`'s "Spline weights — deferred, not
  rejected" section defers down-weighting field-of-view-clipped vertebrae and
  up-weighting known-clear terminal levels, because such weights would need
  calibrating against real GT. That deferral stands. The weights this item
  passes are `1.0` everywhere except a negligible value on the one or two
  levels being withheld, carry no anatomical prior, and are never derived from
  a border-contact or reference signal.

- **The held-out ceiling is a new quantity, not the stage's pass-through
  bound.** Stage 28's acceptance line — a clean GT spine within **1.0 mm**
  across level counts and spacings, raised from 0.5 mm on 2026-08-28 with the
  rationale in `roadmap.md`'s Stage 28 acceptance note — governs the
  **in-sample** pass-through of the fit, which item 119 measured at
  `0.552139` mm and which this item does not touch (AC10). The held-out ceiling
  measured here (`1.072494` mm on the same grid, AC9) is a different
  measurement of a different thing, and reading it against the 1.0 mm line
  would be a category error. Item 125 ticks that acceptance line against item
  119's in-sample number.

- **The gate's proposed `max_offset_mm = 25.0` would silence the corpus's own
  mode-1 case, so item 123 must re-measure rather than carry the number over.**
  The approved gate text (`progress.md`, `## Human gates`, 2026-08-27) records
  "max_offset_mm raised 15.0 -> 25.0", justified by a `21.073357` mm
  leave-one-out ceiling measured across VerSe19 GT. That ceiling was measured
  with **plain, interior-only** leave-one-out
  (`scripts/compare_curve_candidates.py`, `range(1, len(centroids) - 1)`) — a
  different estimator from the one this item ships. Under the shipped estimator
  `mode1_displace`'s displaced label reads **18.719 mm**, so a 25.0 mm
  threshold would stop it firing and undo this item's deliverable. This item
  therefore leaves the threshold at `15.0` (AC16), records both margins (AC17),
  and hands item 123 the requirement to re-measure the real-GT ceiling **under
  the shipped estimator** before moving it. Captured in
  [`insights.md`](../insights.md).

- **A displaced *terminal* level on a short spine is not separable, and that is
  a documented limitation, not a defect.** Measured on synthetic centroid
  geometry with the cranial-most level displaced 18 mm, the estimator reports
  `18.17` mm at 8 levels, `18.06` at 12 and `18.03` at 17 — but only `1.88` mm
  at 5 levels, where withholding a terminal level and the dominant outlier
  leaves three points to constrain a cubic. Real fields of view carry far more
  than five levels; the committed corpus is five levels by construction
  (Stage 21's premise) and its mode-1 target is interior. Stated in the
  function's docstring; not worked around here.

- **The corpus manifest, the goldens, the Stage-3 report golden, the catalogue
  and `reference_default.json` are all regenerated in this item.**
  `queue-017.md` assigns "the nine committed goldens" and
  `reference_default.json` to item 123. Under this repo's `auto-merge` mode
  (`aide.toml` `[git] mode`) the validator runs the full suite and a red suite
  cannot merge, so deferring them is unexecutable: they are derived from the
  offsets this item changes. Item 119 resolved the identical tension the same
  way. Item 123's remaining work is untouched — `max_offset_mm` and
  `reference_verse_v1.json` (AC16, AC29).

- **Item 119's AC22 scope fence is retired here, by design.**
  `tests/test_119_curve_formulation.py::test_ac22_pipeline_is_byte_identical_to_pre_119`
  and `::test_ac22_pipeline_fits_through_all_present_centroids_single_call`
  exist solely to assert that item 119 did *not* do this item's work. They
  cannot both stand and let item 120 land. Both are deleted, and the
  now-unused `pipeline_sha256` key is dropped from
  `tests/corpus/119_pre_119_digests.json`. The fixture file itself stays (its
  `catalogue_leaf_path_set_sha256` still backs item 119's AC27 and this item's
  AC12), so `docs/aide/golden-decision-table.md` needs no new row and
  `tests/test_105_golden_decision_table.py`'s 30-fixture count is unaffected.

- **`aide check --queue 017` reports cross-spec errors against items 118, 119
  and 122 that this item cannot clear.** All three are ✅ and merged, so
  nothing will land on top of this item's assertions. Most of the collisions
  are the 119 → 120 deferral working exactly as designed: item 119 pins
  `src/segfacet/pipeline.py`, `src/segfacet/heuristics/mislabel.py`,
  `src/segfacet/features/spline_offset.py`, `src/segfacet/synth/regression.py`
  and `tests/corpus/manifest.json` under **Asserts against** precisely because
  it deferred them here, and this item lists them under **May change**. The
  rest are item 118's spline-layer pins. Clearing any of them would mean
  editing a completed item's spec, which is out of scope. The check does not
  discount completed items — recorded in [`insights.md`](../insights.md)
  (2026-08-27, item 119). Three pins that would have added collisions without
  carrying any acceptance criterion (`docs/aide/golden-decision-table.md`,
  `tests/test_105_golden_decision_table.py`, `.gitattributes`) were deliberately
  left out of **Asserts against** — see the note at the end of that section.

- **Interface pinned from the shipped item-119 API.** `SplineFit` carries
  `spline` (a `scipy.interpolate.BSpline`), `smoothing`, `u`, `degree` and
  `n_points`; `fit_centroid_spline(centroids, degree=3, *, smoothing=None,
  backend=None)`; `evaluate_spline(fit, u_values, *, backend=None)` returns
  `(N, 3)`; `scipy.interpolate.make_splprep` accepts `u=` and a **strictly
  positive** `w=` (zero weights are rejected, so the withheld weight is a small
  positive constant, not zero). Verified against the merged code on this
  branch.

## Implementation Steps

The code path in `src/segfacet` (see `aide.toml` `project.source_dir`):

1. **`features/spline.py` — parameterisation and weights passthrough.** Add
   keyword-only `u: Optional[Sequence[float]] = None` and
   `weights: Optional[Sequence[float]] = None` to `fit_centroid_spline`. When
   `u` is given, forward it to `make_splprep(..., u=...)` instead of letting it
   compute chord length, and store it on the returned `SplineFit` verbatim.
   When `weights` is given, validate length `== n_points` and every value
   finite and `> 0`, raising `ValueError` naming the offending length or value
   (AC2), then forward as `w=`. Both default to today's behaviour when `None`
   (AC10). Extend the module docstring's "Curve formulation" section with a
   short "(item 120)" paragraph naming the two keywords and what they are for.

2. **`features/spline_offset.py` — the held-out evaluation.** Add
   `compute_leave_one_out_spline_offsets(centroids, spacing_mm=None, *,
   backend=None)`:

   - Fit once through all centroids with defaults; keep that fit's `u`.
   - If `len(centroids) < 4`, return `compute_spline_offsets(centroids, fit,
     spacing_mm=spacing_mm, backend=backend)` unchanged (AC7).
   - Compute the in-sample offsets from that fit and take `worst` as the index
     of the largest `offset_mm`, ties broken by ascending `label` (AC6).
   - For each index `i`: build weights of `1.0` with a module-level
     `_WITHHELD_WEIGHT = 1e-6` at `i` and at `worst`; refit via
     `fit_centroid_spline(centroids, u=fit.u, weights=w)`; take that level's
     record from `compute_spline_offsets([centroids[i]], refit,
     spacing_mm=spacing_mm, backend=backend)[0]`.
   - Return the records in input order.

   Export it from `__all__`. Extend the module docstring with the RAS axis
   contract (AC31), the held-out definition, and the short-spine terminal
   limitation from [Assumptions](#assumptions).

3. **`pipeline.py`.** In `extract_feature_record`'s `len(labels) >= 2` branch,
   import and call `compute_leave_one_out_spline_offsets(ordered_centroids,
   spacing_mm=spacing_mm)` in place of `compute_spline_offsets(...)`. The `fit`
   is still needed for `curvature` and `monotonic_consistency` and stays as it
   is. `offset_by_label` (item 110's neighbourhood wiring) is unchanged and now
   aggregates the held-out values (AC11).

4. **`heuristics/mislabel.py`.** In `_detect_offset_outliers`, read
   `dx_mm`/`dy_mm`/`dz_mm` from each entry when all three are present and
   finite; pick the dominant axis by largest absolute value, ties resolved
   x → y → z; append `", predominantly <direction>"` after the millimetre
   figure and before the threshold clause. Omit the clause entirely when any
   component is missing or non-finite (AC15). Do not change
   `_DEFAULT_MAX_OFFSET_MM`, the tag constants, the ordering, or the finding's
   `labels` (AC16). Record the three direction names and the RAS reasoning in
   the module docstring's "Design decisions" list.

5. **`synth/corpus.py`.** In `CASE_RECIPE`, change the `mode1_displace` entry
   to `detection="pipeline"` with no `reconstruction`, and correct the `detail`
   prose the manifest carries so it no longer says the mode is not surfaced by
   plain `run_qc` (AC20). Update the module docstring sentence naming which
   cases are `reconstructed_record`.

6. **`synth/regression.py`.** Delete `_recon_leave_one_out_offset` and its
   `RECONSTRUCTIONS` entry; update the module docstring's technique list
   (AC21). Leave the `RECONSTRUCTIONS` export and the other two handlers alone.

7. **`synth/identity_ordering_alignment.py`.** Correct the
   `DisplacePerturbation` docstring that documents the "displaced centroid is
   absorbed back" pipeline limitation — no longer true. Docstring only; no
   generator behaviour changes, so the committed `.nii.gz` fixtures stay
   byte-stable.

8. **`feature_docs.py`.** Rewrite the "Spline Offset" group note to describe
   the held-out evaluation and state the RAS axis contract for the direction
   components. Prose only; add and remove no `FEATURE_DOCS` key (AC12, AC30).

9. **Regenerate, in this order** — each through the venv, never by hand-editing
   the artifact:

   ```
   .venv/bin/python -m segfacet.synth.corpus
   .venv/bin/python -m segfacet.synth.golden
   .venv/bin/python -m segfacet.reference.artifact
   .venv/bin/python -m segfacet.catalogue
   ```

   Confirm the corpus regeneration rewrites `tests/corpus/manifest.json` only —
   the `.nii.gz` fixtures must not move. Then rewrite
   `tests/golden/022_stage3_report.json` from
   `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`'s `produced`
   text, writing bytes with `\n` (`write_bytes`, never `write_text` — see
   CLAUDE.md's committed-fixture gotcha).

10. **Reconcile the existing tests listed in
    [Testing Strategy](#testing-strategy)**, then run the
    [Validation](#validation) audit before committing.

## Authorised paths

**May change:**

- `src/segfacet/features/spline.py` — the `u` and `weights` keywords and their
  validation (AC1, AC2). The default fit path is unchanged (AC10).
- `src/segfacet/features/spline_offset.py` — the held-out offset function, the
  RAS contract and the limitation note (AC3–AC9, AC13, AC31).
- `src/segfacet/pipeline.py` — the one call-site swap (AC11).
- `src/segfacet/heuristics/mislabel.py` — the direction clause in the offset
  finding's reason (AC14, AC15). Threshold untouched (AC16).
- `src/segfacet/synth/corpus.py` — the `mode1_displace` recipe row and its
  `detail` prose (AC20).
- `src/segfacet/synth/regression.py` — retire `_recon_leave_one_out_offset` and
  its `RECONSTRUCTIONS` entry (AC21).
- `src/segfacet/synth/identity_ordering_alignment.py` — docstring only; it
  documents a pipeline limitation this item removes.
- `src/segfacet/feature_docs.py` — "Spline Offset" group prose (AC30). No key
  added or removed.
- `src/segfacet/reference/reference_default.json` — regenerated via
  `python -m segfacet.reference.artifact`, never hand-edited (AC28).
- `docs/aide/feature_catalogue.generated.json` — regenerated via
  `python -m segfacet.catalogue`, never hand-edited (AC12, AC30).
- `docs/aide/feature_catalogue.generated.md` — likewise (AC30).
- `tests/corpus/manifest.json` — regenerated via
  `python -m segfacet.synth.corpus`, never hand-edited (AC20).
- `tests/corpus/golden/*.json` — the nine goldens, regenerated via
  `python -m segfacet.synth.golden`, never hand-edited (AC25, AC26).
- `tests/golden/022_stage3_report.json` — regenerated from the test's
  `produced` text, never hand-edited (AC27).
- `tests/corpus/119_pre_119_digests.json` — drop the now-unused
  `pipeline_sha256` key; `catalogue_leaf_path_set_sha256` stays and still backs
  AC12.
- `tests/test_120_leave_one_out_offset.py` — the new test module.
- `tests/test_119_curve_formulation.py` — delete the two `test_ac22_*`
  functions, which exist only to fence item 119 out of this item's work. No
  other test in the module changes.
- `tests/test_039_identity_ordering_alignment_perturbations.py` —
  `test_ac5_displace_run_qc_does_not_surface_mislabel_finding` asserts the
  limitation this item removes and must be inverted;
  `test_ac4_displace_fires_misalignment_finding_via_reconstructed_offsets`
  reaches the finding through a hand-built leave-one-out record and should
  reach it through plain `run_qc`. Those two tests and the module docstring's
  Group A summary only.
- `tests/test_040_synthetic_corpus.py` — `_RECONSTRUCTED_MODES`,
  `_PIPELINE_ONLY_MODES` and `_VALID_RECONSTRUCTIONS` move mode 1 across, and
  `test_ac8_modes_1_4_8_reconstructed_record_rest_pipeline` is renamed with its
  docstring corrected. No other assertion changes.
- `tests/test_041_regression_suite.py` — the inline valid-technique literal set
  in the `detection`/`reconstruction` well-formedness check drops
  `"leave_one_out_offset"`. That literal only.
- `tests/test_057_acceptance_stage7.py` — `_PIPELINE_DETECTABLE_MODES` and
  `_RECONSTRUCTED_RECORD_MODES` move mode 1 across;
  `test_overall_corpus_sensitivity_is_five_of_eight_not_over_claimed` becomes
  six of eight and is renamed, along with the module docstring's `5/8`
  sentence (AC24).
- `docs/aide/insights.md` — append-only, per the out-of-scope-insight rule.
- `tests/test_098_stray_components.py` —
  `test_ac15_golden_verdict_and_findings_unchanged` for `mode1_displace` and
  `mode6_crop_at_border`: both cases' verdict/findings shape is a direct
  consequence of AC18/AC20/AC23's deliberate behaviour change (widened by
  human decision, 2026-08-28).
- `tests/test_102_stage18_validation.py` —
  `test_ac5_report_verdict_and_findings_match_pre_098_snapshot`, same two
  cases, same reason (widened by human decision, 2026-08-28).
- `tests/test_116_ras_native_corpus.py` —
  `test_ac7_case_identity_preserved_vs_merge_base`, same two cases, same
  reason (widened by human decision, 2026-08-28).
- `tests/test_110_neighbourhood_wiring.py` —
  `test_ac11_corpus_findings_rule_ids_unchanged`, whose exact-equality
  assertion AC23 deliberately breaks for `mode6_crop_at_border` (widened by
  human decision, 2026-08-28; see the "Collateral test breakage" entry in
  Decisions & Trade-offs, now resolved by this widening).
- `tests/test_119_curve_formulation.py` — additionally
  `test_ac20_regeneration_moves_no_verdict_or_finding` and
  `test_ac21_no_regenerated_golden_offset_reaches_2mm`, both of which pin
  pre-120 behaviour this item deliberately supersedes (widened by human
  decision, 2026-08-28).
- `tests/test_115_stage26_validation.py` — asserts against
  `tests/corpus/119_pre_119_digests.json`, whose `pipeline_sha256` key this
  item's step 9 drops (widened by human decision, 2026-08-28).
- `tests/test_120_leave_one_out_offset.py` — the redundant second digest fence,
  against the same dropped `pipeline_sha256` key (widened by human decision,
  2026-08-28). Listed above as this item's new test module too; this is the one
  assertion in it that exists only to retire an older fence.
- `docs/aide/golden-decision-table.md` — the "asserted by" cell naming
  the deleted `test_ac22_pipeline_is_byte_identical_to_pre_119` (widened by
  human decision, 2026-08-28). This reverses this spec's own earlier decision
  not to pin them (see the "Asserts against" note below this list, now
  superseded for these two paths only): the table's own row text for
  `tests/corpus/119_pre_119_digests.json` already predicted that item 120
  ends the `pipeline_sha256` fence's life, so updating the row is this
  item's job, not a later one's.
- `tests/test_105_golden_decision_table.py` — the same deleted-test reference
  the table row above carries, checked from the test side (widened by the same
  2026-08-28 human decision).

**Asserts against:**

- `src/segfacet/reference/reference_verse_v1.json` — read, not changed (AC29).
  Its rebuild needs the real VerSe cohort and is item 123's.
- `src/segfacet/io.py` — read, not changed. AC31 pins `_TARGET_AXCODES` as
  `("R", "A", "S")`, the fact that makes the direction components readable.
- `src/segfacet/features/centroids.py` — read, not changed. AC31 pins that
  `centroid_mm` is `centroid_voxel * spacing` with no affine.
- `src/segfacet/features/consistency.py` — read, not changed. It and the two
  paths below consume the fit or the offset *values*; if any needs editing,
  step 3 reached too far.
- `src/segfacet/features/orientation.py` — read, not changed; consumes the fit
  or the offset values, as `consistency.py` above.
- `src/segfacet/features/neighbourhood.py` — read, not changed; consumes the
  fit or the offset values, as `consistency.py` above.
- `tests/test_017_centroid_spline_fit.py` — read, not changed. AC10 is
  satisfied by this module staying green as committed.
- `tests/test_018_per_vertebra_spline_offset.py` — read, not changed. AC13 is
  satisfied by this module staying green as committed, which is what proves
  `compute_spline_offsets` kept its in-sample meaning.
- `tests/test_033_mislabel.py` — read, not changed. AC15 is satisfied by this
  module staying green as committed.
- `docs/spinal-curve-model.md` — read, not changed. It is item 118's signed
  deliverable; the item-number drift in its "Breaking circularity" section is
  resolved in this spec's Description and captured in `insights.md`.
- `tests/corpus/fixtures/*.nii.gz` — read, not changed. No generator behaviour
  changes, so the committed volumes must be byte-stable across step 9.

`.gitattributes` is deliberately **not** pinned here: this item adds and
removes no non-`.py` fixture under `tests/`, so the existing `text eol=lf`
pins already cover everything regenerated in step 9. Pinning it would only
collide with items 119 and 122, which legitimately edited it and are merged.

`docs/aide/golden-decision-table.md` and `tests/test_105_golden_decision_table.py`
were originally scoped out on the same reasoning (this item adds/removes no
fixture, so the documented fixture count doesn't move) — but that reasoning
missed that this item *retires an assertion on an existing, already-pinned*
fixture (`tests/corpus/119_pre_119_digests.json`'s `pipeline_sha256` key and
`test_ac22_pipeline_is_byte_identical_to_pre_119`), which the table's own row
names by test id. Human decision, 2026-08-28: widen the May-change list (see
above) to cover the table row's "asserted by" cell and the deleted-test
reference `tests/test_105_golden_decision_table.py` checks against, rather
than leaving that reconciliation to a later item.

## Testing Strategy

New module: **`tests/test_120_leave_one_out_offset.py`** — one focused test per
AC, plus the adversarial cases below. It may import
`segfacet.synth.clean_gt.build_clean_spine`, `segfacet.synth.regression` and
`tests/synthetic.py` helpers.

**Per-AC coverage.** AC1–AC2 are direct unit assertions on
`fit_centroid_spline`'s new keywords. AC3–AC8 exercise
`compute_leave_one_out_spline_offsets` on constructed centroid sequences
(clean, one-interior-displaced, 2- and 3-level). AC9 rebuilds item 119's 3 × 3
sweep grid. AC10/AC13 assert the unchanged default fit and in-sample function.
AC11–AC12 are source and catalogue-shape assertions. AC14–AC17 drive
`MislabelRule` over hand-built records and over the corpus. AC18–AC24 go
through `synth.regression`'s `pipeline_findings`, `verify_case` and the cohort
metrics. AC25–AC30 use `check_case_golden`, `write_goldens` into two `tmp_path`
directories, a fresh catalogue regeneration and a fresh reference build. AC31
asserts `segfacet.io`'s target axcodes and reads the two docstrings.

**Adversarial and edge cases.**

- A perfectly straight spine — every held-out offset `≈ 0`; no level is
  spuriously flagged merely because one of them was chosen as dominant outlier.
- Two levels displaced in opposite directions — both exceed the threshold and
  both are named; only one is withheld as dominant outlier, so the second is
  still measured against a curve it does not shape.
- A displaced **terminal** level at 5 levels — asserted **not** separable, so
  the documented limitation is pinned rather than assumed away; at 8 levels,
  asserted separable.
- Highly anisotropic spacing (`(0.8, 0.8, 1.0)`, and a 30 mm z-step) — the
  `offset_voxel` conversion stays spacing-correct and the ranking is unchanged.
- Exactly 4 levels — the first count at which the held-out path runs; must not
  raise and must stay finite.
- One level removed from the middle, the front and the back of a 6-level
  sequence.
- The input centroid sequence is not mutated; the returned records are frozen
  dataclasses; every returned field is finite.
- `weights` containing `0.0`, a negative value, a NaN, and a wrong length — each
  raises `ValueError` with a readable message (AC2), never a raw FITPACK
  message.

**Existing tests to reconcile** (these pin behaviour this item changes; the
first validation round fails on them, not on new code, unless they are
handled):

| Test | Why it moves | Resolution |
|---|---|---|
| `test_119_curve_formulation.py::test_ac22_pipeline_is_byte_identical_to_pre_119` | Hashes `pipeline.py` against a pre-119 digest; this item edits that file. | Delete the test and the `pipeline_sha256` key. Authorised — see Assumptions. |
| `test_119_curve_formulation.py::test_ac22_pipeline_fits_through_all_present_centroids_single_call` | Asserts `pipeline.py` calls `compute_spline_offsets` once and contains no `leave_one_out`. Both become false by design. | Delete. Authorised. |
| `test_039::test_ac5_displace_run_qc_does_not_surface_mislabel_finding` | Asserts plain `run_qc` emits **no** `mislabel` finding — the exact limitation this item removes. | Invert and rename: `run_qc` now fires `mislabel` on the displaced label. Authorised. |
| `test_039::test_ac4_displace_fires_misalignment_finding_via_reconstructed_offsets` | Reaches the finding by hand-patching a leave-one-out offset into the record. | Re-express against plain `run_qc`. Authorised. |
| `test_040::test_ac8_modes_1_4_8_reconstructed_record_rest_pipeline` | `_RECONSTRUCTED_MODES = {1, 4, 8}` and `_PIPELINE_ONLY_MODES = {0, 2, 3, 5, 6, 7}`; mode 1 crosses over. | Move mode 1, rename the test, correct its docstring. Authorised. |
| `test_040::test_ac9_reconstructed_record_fixtures_hide_mode_from_run_qc` | Iterates the reconstructed cases; mode 1 leaves the set. | **No change expected** — the two remaining cases still hide their mode. Verify. |
| `test_041` `detection`/`reconstruction` well-formedness check | Its inline valid-technique set names `"leave_one_out_offset"`, which is retired. | Drop that literal. Authorised. |
| `test_042_golden_determinism.py` (nine cases, `reports_close`) | Every `stage3` offset moves, and two cases gain a `mislabel` finding. | Regenerate the nine goldens (step 9). |
| `test_042::AC16` (reconstructed-case goldens) | Iterates `_RECONSTRUCTED_CASES`; mode 1 leaves the list. | **No change expected.** Verify; if a count is pinned, stop and hand back. |
| `test_057::test_reconstructed_record_modes_are_not_over_claimed_as_caught` | Parametrised over `_RECONSTRUCTED_RECORD_MODES = (1, 4, 8)`; mode 1's sensitivity is no longer 0.0. | Move mode 1 into `_PIPELINE_DETECTABLE_MODES`. Authorised. |
| `test_057::test_overall_corpus_sensitivity_is_five_of_eight_not_over_claimed` | Asserts `5/8`; it becomes `6/8` (AC24). | Update the value, the name and the docstring. Authorised. |
| `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` | Strict text equality against `tests/golden/022_stage3_report.json`. | Regenerate the golden (step 9). Never edit the test. |
| `test_103_feature_catalogue.py::test_ac19_committed_docs_match_fresh_regeneration` | The "Spline Offset" group prose changes. | Regenerate the catalogue (step 9). |
| `test_045_reference_artifact.py::test_ac10_regenerating_reproduces_committed_bytes` | Compares a fresh build against the committed `reference_default.json`, whose `spline_offset_mm` distribution this item changes. | Rebuild the artifact (step 9). |
| `test_063_reference_intensity.py::{test_ac13_default_cohort_geometric_stats_identical_on_off_intensity, test_ac15_bundled_artifact_regenerates_byte_identically}` | Same cause. | Same. |
| `test_081_reference_morphology.py::{test_ac12_bundled_default_geometric_and_intensity_stats_identical_on_off_morphology, test_ac17_regenerated_artifact_deterministic_and_matches_committed_within_tolerance}` | Same cause. | Same. `grep -l build_and_write_default tests/` finds this family mechanically — the sweep item 119's `insights.md` entry asks for. |
| `test_110_neighbourhood_wiring.py` | Aggregates `offset_mm` mean/median/std, which stop being zeros. | **No change expected** if its assertions are structural. Verify; if it pins values, hand back rather than editing blind. |
| `test_036_clean_gt.py::AC11` (`offset_mm < 15.0`) | Clean offsets rise from `~1e-4` mm to at most `1.07` mm. | **No change expected.** |
| `test_033_mislabel.py` | Builds records without direction components and matches the reason by `startswith`. | **No change expected** — AC15 exists to keep it green unmodified. |
| `test_018_per_vertebra_spline_offset.py`, `test_017_centroid_spline_fit.py` | Exercise `compute_spline_offsets` / `fit_centroid_spline` directly, neither of whose default behaviour changes. | **No change expected** — AC10/AC13 are satisfied by them staying green. |
| `test_049_acceptance_stage6.py`, `test_090`, `test_092`, `test_097`, `test_098`, `test_101_per_mode_cohort.py`, `test_109_attribution_scale.py` | Score cases against the reference, or read per-mode detection. | **Expected to survive** once `reference_default.json` is rebuilt. Confirm by running them; if one genuinely fails, stop and hand back rather than editing it. |

## Validation

Beyond the unit suite, observe the promotion on the corpus. No `[validation]`
profile is required — everything runs on the default CPU venv against committed
fixtures.

1. **See the rule fire end to end.**

   ```
   .venv/bin/python -m segfacet.cli run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/mode1_displace_seg.nii.gz --out out/mode1-120
   ```

   The report must carry a `mislabel` finding naming label 22 (L3), reading
   roughly `18.7 mm off the fitted spinal curve, predominantly left-right`, and
   **no** `mislabel` finding on any other label. Repeat with
   `clean_control_seg.nii.gz`: the verdict is `pass` with no findings at all.

2. **Audit the regeneration's narrowness (AC26).**

   ```
   git diff aide/queue-017 -- tests/corpus/golden tests/golden
   ```

   Every changed hunk must fall inside a `"stage3"` object or a `"findings"`
   array. A changed `"verdict"`, `"stage2"` or `"schema_version"` line means
   the change reached further than this item allows — stop and hand back.

3. **Confirm the fixtures did not move.**

   ```
   git diff aide/queue-017 --stat -- tests/corpus/fixtures
   ```

   Must be empty: no generator behaviour changed, so only
   `tests/corpus/manifest.json` may differ under `tests/corpus/`.

4. **Confirm the item's boundary held.**

   ```
   git diff aide/queue-017 --stat
   ```

   Must list neither `src/segfacet/reference/reference_verse_v1.json` nor
   `docs/spinal-curve-model.md`, and `heuristics/mislabel.py`'s
   `_DEFAULT_MAX_OFFSET_MM` must still read `15.0`.

5. **Record the margins (AC17).** From the regenerated goldens, note the
   largest `offset_mm` on every case that raises no `mislabel` offset finding,
   and on `mode1_displace`, and write both into the Decisions log — they are
   the evidence item 123 needs to recalibrate `max_offset_mm` under the shipped
   estimator rather than carrying the gate's 25.0 over.

## Dependencies

- **Item 118** (✅) — the recorded formulation decision in
  [`docs/spinal-curve-model.md`](../../spinal-curve-model.md), whose "Breaking
  circularity" section chooses leave-one-out, and
  `scripts/compare_curve_candidates.py`, whose interior-only measurement loop
  is the evidence that the endpoint case was already known to be different.
- **Item 119** (✅) — the shipped smoothing fit this item evaluates against:
  `SplineFit.spline`/`smoothing`, `fit_centroid_spline`'s `smoothing` keyword,
  and `evaluate_spline`'s `(N, 3)` contract. Its AC22 fence is retired here.
- **Item 018** (✅) — `compute_spline_offsets`, `VertebralSplineOffset` and the
  `closest_u` search this item reuses unchanged.
- **Item 033** (✅) — `MislabelRule`'s offset detector, whose finding text gains
  the direction clause.
- **Item 040 / item 042** (✅) — the corpus recipe, the `detection`
  discriminator, `write_goldens` and `check_case_golden`.
- **Item 103** (✅) — the catalogue generator AC12/AC30 regenerate through.
- **Human gate: "Spinal curve model — the deformity envelope"** — ✅ Approved by
  a person on 2026-08-27 (`progress.md`, `## Human gates`; `Blocks: 119, 120,
  121, 123, 125`). This item is unblocked. Its approval text is honoured in
  full except that the `max_offset_mm` figure it names is left to item 123 to
  re-measure under the shipped estimator — see [Assumptions](#assumptions).

**Downstream:** item 121 adds the tangent-based orientation proxy on the same
fit; item 123 recalibrates `max_offset_mm` (and **must** re-measure the real-GT
ceiling under this item's estimator before adopting 25.0) and rebuilds
`reference_verse_v1.json`; item 125 validates Stage 28 end to end and records
the 5-of-8 to 6-of-8 detection count in `progress.md`.

## Decisions & Trade-offs

- **Weight construction.** `compute_leave_one_out_spline_offsets` builds a
  fresh `[1.0] * n_points` list per level, sets `weights[i]` and
  `weights[worst_idx]` to the module-level `_WITHHELD_WEIGHT = 1e-6`, and
  refits with `u=reference_fit.u`. When `i == worst_idx` (the level under
  test is itself the dominant outlier) the same index is set twice with no
  special-casing needed — the result is the same single withheld point,
  which is the correct behaviour: the dominant outlier's own held-out
  reading only withholds itself, since there is no *second* level left to
  additionally withhold.

- **Dominant-outlier tie-break implementation.** `min(range(n), key=lambda i:
  (-in_sample[i].offset_mm, centroids[i].label))` selects the largest
  in-sample `offset_mm`, ties broken by ascending `label` — matches AC6's
  wording directly (negating the offset turns "largest offset" into "min
  key", and the label is the natural ascending tiebreaker for `min`).

- **`mislabel`'s direction tie-break uses `max()`'s first-occurrence
  semantics.** `_dominant_direction` builds `[(|dx|, "left-right"), (|dy|,
  "anterior-posterior"), (|dz|, "cranio-caudal")]` in that fixed order and
  calls `max(components, key=lambda c: c[0])`; Python's `max` returns the
  *first* maximal element on a tie, which reproduces the required x -> y ->
  z tie order without an explicit tie-break branch. Verified against AC14's
  two tie tests (dx==dy -> left-right; dy==dz -> anterior-posterior).

- **`identity_ordering_alignment.py`'s `detail=` string, not just its
  docstrings, needed correcting.** The Authorised paths note for this file
  says "docstring only", but `corpus.py`'s `write_corpus` takes the
  manifest's `"detail"` field verbatim from `DisplacePerturbation.apply()`'s
  `Expectation.detail` — there is no separate corpus-level override. AC20
  requires the *manifest's* detail prose to stop claiming the mode is hidden
  from `run_qc`, which is only reachable by editing that f-string. This
  changes no voxel data and no generator behaviour (the string is descriptive
  metadata folded into the committed manifest at regeneration, same as any
  other text this item's step 9 regenerates) — kept inside the spirit of the
  "docstring only, no generator behaviour changes" constraint.

- **AC26 implemented per the coherent reading, not the literal text.** As
  already logged in `insights.md` (2026-08-28), AC26's prose ("verdict is
  unchanged from its pre-120 committed value" for "all nine") contradicts
  AC18/AC20, which require `mode1_displace` to fire `mislabel` through plain
  `run_qc` and lose its `reconstructed_record` status — and severity-dominance
  verdict aggregation (`aggregate.py`) makes a verdict move from `pass` to
  `flagged-for-review` an unavoidable consequence of a genuine new finding on
  a case with zero prior findings. Implemented and tested per the committed
  `test_120_leave_one_out_offset.py::test_ac26_regeneration_moves_no_verdict_outside_mode1s_own_deliverable`:
  every other case's verdict is byte-for-byte unchanged; `mode1_displace`
  alone moves to `flagged-for-review`, and every other changed JSON leaf
  (across all nine goldens) lies under `features.stage3` or `findings`.

- **Threshold margins measured on the regenerated corpus (Validation step 5).**
  Over the nine regenerated goldens, the largest `per_label_offsets[].offset_mm`
  on every case that must not raise a `mislabel` offset finding is
  **5.143859 mm** (`mode4_relabel_swap`'s largest reading; the clean control
  alone peaks at **0.673278 mm**) — a margin of **9.86 mm** below the 15.0 mm
  threshold on the tightest non-firing case. `mode1_displace`'s displaced
  label 22 reads **18.718604 mm**, a margin of **3.72 mm** above the
  threshold. `mode6_crop_at_border`'s deliberate new finding (AC23) reads
  **17.507445 mm** on label 22, a margin of **2.51 mm** above the threshold.
  These are the numbers item 123 needs to re-measure the real-GT ceiling
  under this item's estimator before moving `max_offset_mm`.

- **Collateral test breakage outside this item's Authorised paths, not
  fixed here.** `tests/test_110_neighbourhood_wiring.py::
  test_ac11_corpus_findings_rule_ids_unchanged` asserts, for every
  `detection == "pipeline"` corpus case, that the *full* set of fired
  `rule_id`s equals `set(case["expected_rule_ids"])`. AC23 deliberately adds
  a `mislabel` finding to `mode6_crop_at_border` while its
  `expected_rule_ids` stays `["border"]` (the designated rule only), so this
  one assertion now fails for that case. `tests/test_110_neighbourhood_wiring.py`
  is item 110's (✅ merged) and is not in this item's Authorised paths — its
  Testing Strategy table named only that file's `offset_mm` aggregation
  stats as something to verify, not this assertion, so this is a genuine gap
  in the reconciliation table rather than something this item was authorised
  to touch. Left unedited per the table's own escape hatch ("if it pins
  values, hand back rather than editing blind"); logged in `insights.md`
  (2026-08-28) for a human/validator to decide the follow-up (widen this
  item's scope, or a small authorised fix in a later item).

- **Multi-outlier limitation shipped as a known, documented limitation
  (human decision, 2026-08-28).** `compute_leave_one_out_spline_offsets`
  withholds only the single dominant outlier per refit (Decisions entry
  above, "Weight construction"). With two or more genuinely displaced
  levels, every un-withheld displaced level still pulls every *other*
  level's held-out curve toward itself. Measured on the adversarial
  two-opposite-displacements case: a genuinely **clean** level reads
  **31.96 mm** while one of the **displaced** levels reads only **19.31 mm**
  — a clean vertebra can be named an offender ahead of an actual one. The
  project owner accepted this as a known limitation to ship now rather than
  a defect to fix in this item: it is measured, reproducible, and does not
  regress anything this item's AC pin (the single-outlier corpus cases all
  measure correctly). The limitation is now stated plainly, with these
  numbers, in `src/segfacet/features/spline_offset.py`'s module docstring so
  a reader of the code learns it without opening this spec. The accepted
  follow-up — withhold every level above some outlier cutoff, not just the
  single dominant one — is logged in `insights.md` (2026-08-28) for a later
  item; not implemented here per "do not redesign the estimator."

- **Authorised paths widened after initial commit (human decision,
  2026-08-28).** The reconciliation table under-scoped this item's blast
  radius: several already-merged tests assert exact shapes (verdict/findings
  snapshots, rule-id sets, pre-120 offset ceilings, a deleted-test reference
  in the golden-decision-table) that this item's deliberate behaviour change
  — `mode1_displace` and `mode6_crop_at_border` now firing `mislabel` through
  plain `run_qc` — necessarily breaks. Rather than leave those breakages as
  "collateral, fixed later" (the disposition originally recorded for
  `test_110_neighbourhood_wiring.py` above), the owner widened this item's
  May-change list to cover all of them in one pass: `test_098_stray_
  components.py`, `test_102_stage18_validation.py`, `test_116_ras_native_
  corpus.py`, `test_110_neighbourhood_wiring.py`, the two `test_119_curve_
  formulation.py` pre-120-pinning tests, `test_115_stage26_validation.py`,
  the redundant digest fence in `test_120_leave_one_out_offset.py`, and
  `docs/aide/golden-decision-table.md` / `test_105_golden_decision_table.py`
  (see the Authorised paths section for the full list and per-file reasons).
  This does not change any measured value or redesign the estimator — it
  only aligns the spec's authorised scope with the behaviour this item
  already, deliberately, produces.
