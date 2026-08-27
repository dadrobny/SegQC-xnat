# Item 119 — Implement the chosen curve formulation

> **Created:** 2026-08-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation (deliverable **D2**)
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 119
> **Objectives:** G2, G7
> **Suggested branch:** `aide/119-implement-the-chosen-curve-formulation`

---

## Description

Replace the interpolating spline fit in `src/segfacet/features/spline.py` with
the formulation [`docs/spinal-curve-model.md`](../../spinal-curve-model.md)
records and the human gate approved on 2026-08-27 (see `progress.md`'s
`## Human gates`, the row blocking 119/120/121/123/125):

- **Family** — smoothing spline, the same parametric B-spline construction as
  today with SciPy's smoothing parameter `s` set to the number of input points
  instead of `0`.
- **Degrees of freedom** — `s = n_points`, cubic degree clamped `k = min(3,
  n_points - 1)` exactly as today.
- **Parameterisation** — chord-length `u` in `[0, 1]`, shared and unchanged, so
  `closest_u`, `_find_closest_u` and the monotonic-`u` consistency check keep
  their existing meaning.
- **API** — built with `scipy.interpolate.make_splprep`, not the legacy
  `splprep` (the decision document's first amendment). This is not a rename:
  the call returns a `(BSpline, u)` pair, so evaluation moves from
  `splev(u, tck)` to `spl(u)` and the first derivative from
  `splev(u, tck, der=1)` to `spl(u, nu=1)`. `SplineFit` loses its `tck` field
  and gains `spline` (a `BSpline`) and `smoothing` (the `s` actually used), so
  every direct consumer migrates with it.

**This item changes how the curve is fitted. It does not change how a
per-label offset is evaluated against that curve.** `stage3.per_label_offsets[]`
stays an *in-sample* measurement here; promoting leave-one-out from
`synth/regression.py::_recon_leave_one_out_offset` into `pipeline.py` is item
120's deliverable (D3), and the recalibration of `mislabel`'s `max_offset_mm`
(15.0 → 25.0) plus the rebuild of both reference artifacts is item 123's (D6).
Item 119 must nonetheless *demonstrate* that the new fit separates a displaced
vertebra under leave-one-out evaluation, because that is the margin the
decision document states and the queue names as this item's testable criterion —
it does so at the `fit_centroid_spline` / `compute_spline_offsets` API level,
without touching `pipeline.py`. See [Assumptions](#assumptions) for why the
split falls here.

Measured on this branch before writing this spec, the change moves every
committed golden's `stage3` offsets (max `offset_mm` per case goes from
`~1e-4` mm to between `0.09` and `1.58` mm) while leaving **every case's
verdict and every finding's `(rule_id, labels)` unchanged** — no rule's
threshold is crossed, `is_monotonic` stays `True` everywhere including
`mode4_relabel_swap`. So this item regenerates the goldens it invalidates and
lands on a green suite, in the same shape item 122 used; it does not restore
the mode-4 signal, which needs item 120's evaluation change.

**Not in scope:** per-point spline weights (deferred by the decision document's
second amendment); separate normal/scoliotic deformity envelopes (deferred by
its third); any feature outside the spline layer (queue-017's scope fence);
`pipeline.py`; `heuristics/mislabel.py`; either `reference_*.json` artifact.

## Acceptance Criteria

- [ ] **AC1: The fit is built with `make_splprep`.**
  `segfacet.features.spline` imports `make_splprep` from `scipy.interpolate`,
  and `fit_centroid_spline(...)` returns a `SplineFit` whose `spline` attribute
  is an instance of `scipy.interpolate.BSpline`.

- [ ] **AC2: The legacy FITPACK wrappers are gone from the package.** No module
  under `src/segfacet/` imports `splprep` or `splev` from `scipy.interpolate`,
  and no module calls either name.

- [ ] **AC3: Smoothing defaults to the input-point count.** For every level
  count `n` in 2..8, `fit_centroid_spline(centroids).smoothing == float(n)`
  and `SplineFit.n_points == n`.

- [ ] **AC4: Smoothing is overridable, and `smoothing=0.0` reproduces an
  interpolating fit.** `fit_centroid_spline(centroids, smoothing=0.0)` passes
  within `1e-3` mm of every input centroid on the clean-GT sweep fixtures of
  AC7, where the default (`smoothing=None` → `s = n_points`) does not.

- [ ] **AC5: The degree clamp is unchanged.** `SplineFit.degree ==
  min(requested_degree, n_points - 1)` for `n_points` in 2..8 at
  `requested_degree=3`, and `== 2` when `degree=2` is passed with ≥3 points.

- [ ] **AC6: The chord-length parameterisation is unchanged in meaning.**
  `SplineFit.u` has length `n_points`, starts at exactly `0.0`, ends at exactly
  `1.0`, and is strictly increasing.

- [ ] **AC7: Item 017's 0.5 mm clean-GT pass-through bound still holds,
  unweakened.** On item 017's own GT fixtures — a straight spine (6 and 7
  levels), the curved 6-level spine, the anisotropic 5-level spine, and each
  with one level removed — evaluating the fit at `fit.u` lands within
  `0.5` mm of every input centroid. *(Measured on this branch under the new
  formulation: worst case `0.19198` mm, on the curved fixture.)*

- [ ] **AC8: The synthetic clean-GT sweep's in-sample pass-through is bounded
  at 0.56 mm.** Over `synth.clean_gt.build_clean_spine` at level counts 2, 3
  and 5 × spacings `(1,1,1)`, `(1,1,2)`, `(0.8,0.8,1)` with a 6 mm curve
  amplitude, the maximum closest-approach distance from any centroid to the
  fitted curve is `> 0.5` mm and `≤ 0.56` mm — matching
  `docs/spinal-curve-model.md`'s recorded `0.552139` mm. *(Both halves are
  asserted: the bound is a ceiling, and the `> 0.5` half pins that this grid
  is genuinely the one place the sweep exceeds item 017's fixture bound, so the
  discrepancy recorded in [Assumptions](#assumptions) cannot be silently
  "fixed" by a later tweak without this test noticing.)*

- [ ] **AC9: A displaced vertebra separates under leave-one-out evaluation.**
  On the decision document's separation fixture (8 thoracic levels, 1 mm
  isotropic, 6 mm curve amplitude, the middle centroid displaced by 5 mm
  along `(1,1,0)/√2`): fitting through the other seven levels and measuring
  with `compute_spline_offsets`, the displaced centroid's `offset_mm` exceeds
  the largest of the seven clean centroids' `offset_mm` against that same fit
  by at least `4.5` mm. *(The decision document records `4.999144` mm as the
  smallest margin over displacements 5/10/20 mm.)*

- [ ] **AC10: In-sample evaluation does not separate, and that is recorded.**
  On the same fixture with the displaced centroid *included* in the fit, the
  same margin is below `0.5` mm — the reason AC9 must be measured
  leave-one-out. *(Recorded in-sample smallest margin: `0.140882` mm.)*

- [ ] **AC11: Two fits of the same input are identical.** For the curved
  6-level fixture, two successive `fit_centroid_spline` calls yield equal `u`
  tuples, equal `degree`, equal `n_points`, equal `smoothing`, array-equal
  `spline.t`, array-equal `spline.c`, and array-equal results from
  `evaluate_spline` at the same `u` values.

- [ ] **AC12: A 2-level input fits without error.** `fit_centroid_spline` on
  exactly 2 centroids returns a `SplineFit` with `degree == 1` and no
  exception, and `evaluate_spline(fit, [0.0, 0.5, 1.0])` returns a finite
  `(3, 3)` array.

- [ ] **AC13: A truncated-FOV input fits without error and is not degenerate.**
  Keeping only the cranial 3 of a 5-level clean spine, the fit raises nothing,
  every evaluated coordinate is finite, and the fitted curve's sampled arc
  length is within a factor of `3.0` of the centroid polyline length — item
  118's own non-degeneracy check.

- [ ] **AC14: A first-derivative evaluator is public and used.**
  `segfacet.features.spline` exposes a derivative evaluation helper that
  returns an `(N, 3)` float64 array for `N` parameter values, and
  `segfacet.features.orientation.compute_spine_curvature` obtains its tangents
  through that helper rather than importing SciPy itself.

- [ ] **AC15: Curvature values are preserved for a clean fixture within the
  fit's own change.** `compute_spine_curvature` on the clean 5-level lumbar
  fixture returns finite `tangent_angles_deg`, `inter_tangent_angles_deg` and
  signed-curvature values of the same shape and sign convention item 122
  established (the tuple lengths, the `curvature_plane` string domain, and
  `total_curvature_deg == max − min` of the signed sagittal/coronal series are
  unchanged).

- [ ] **AC16: Exactly-coincident centroids raise a readable error, not a raw
  FITPACK message.** `fit_centroid_spline` on a sequence containing two
  exactly-coincident centroid mm-coordinates raises `ValueError` whose message
  names the duplicated coordinate and the offending `level_name`s, and contains
  neither `"Invalid inputs"` nor `"theoretically impossible result"`. *(Under
  `make_splprep` at `s = n_points` the unguarded failure is a five-line FITPACK
  iteration message — worse than today's; this AC keeps item 017's AC5
  message-quality contract from regressing. See
  [`insights.md`](../insights.md)'s 2026-08-27 entry.)*

- [ ] **AC17: Near-coincident centroids still fit.** A 5-level sequence spaced
  `1e-6` mm apart fits without raising and evaluates finite — the fixture
  `tests/test_122_signed_curvature.py::test_adv_all_centroids_coincident_no_crash_finite`
  relies on, which must stay green unmodified.

- [ ] **AC18: The nine corpus goldens are regenerated and agree with a fresh
  build.** For every case in `tests/corpus/manifest.json`,
  `synth.golden.check_case_golden(case)` is `True`, and two `write_goldens`
  runs into different directories are byte-identical to each other.

- [ ] **AC19: The Stage-3 report golden is regenerated.**
  `tests/golden/022_stage3_report.json` matches
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`'s produced text
  exactly, with that test unmodified.

- [ ] **AC20: The regeneration moves no verdict and no finding.** For all nine
  regenerated goldens, `verdict` is byte-identical to its pre-119 committed
  value and the ordered list of `(rule_id, labels)` over `findings` is
  unchanged; every changed JSON leaf lies under `features.stage3`.

- [ ] **AC21: `mislabel`'s threshold is untouched and unreached.**
  `heuristics/mislabel.py`'s `max_offset_mm` default is still `15.0`, and no
  regenerated golden's `stage3.per_label_offsets[].offset_mm` reaches `2.0` mm
  — the recalibration to `25.0` is item 123's.

- [ ] **AC22: The pipeline's offset evaluation is unchanged.**
  `src/segfacet/pipeline.py` is byte-identical to its pre-119 state, and
  `extract_feature_record` still computes `stage3.per_label_offsets` from a
  single fit through *all* present centroids — leave-one-out promotion is item
  120's.

- [ ] **AC23: The SciPy floor is raised.** `pyproject.toml`'s `project
  .dependencies` contains `scipy>=1.15` and no other dependency bound in that
  list changes.

- [ ] **AC24: The candidate-comparison tool keeps its candidate identities.**
  In `scripts/compare_curve_candidates.py`, `_fit_interpolating_cubic` produces
  an interpolating (`s = 0`) fit and `_fit_smoothing_spline` an `s = n_points`
  fit, both via the shipped `fit_centroid_spline`, and neither constructs a
  `SplineFit` by hand nor imports `splprep`.

- [ ] **AC25: The decision document's quoted numbers still reproduce.** A fresh
  `scripts/compare_curve_candidates.py` run (without a VerSe cohort) reproduces
  every non-VerSe `Key`/`Value` row of `docs/spinal-curve-model.md`'s
  Measurements table within its stated `0.001` mm tolerance — i.e.
  `test_118_curve_formulation_decision.py::test_ac6_non_verse_measurements_reproduce_from_fresh_run`
  stays green with that test module unmodified.

- [ ] **AC26: The feature catalogue no longer documents an interpolating fit.**
  `feature_docs.py`'s "Spline Offset" group note describes a smoothing fit at
  `s = n_points` built with `make_splprep`, and contains neither `"s=0"` nor
  `"passes exactly through every centroid"`; the "Orientation & Curvature"
  note no longer names `splev`.

- [ ] **AC27: The generated catalogue artifacts are regenerated.**
  `docs/aide/feature_catalogue.generated.json` and `.md` are byte-identical to
  a fresh `python -m segfacet.catalogue` regeneration, and the committed
  artifacts' set of leaf `path` values is unchanged from pre-119 (this item
  adds and removes no feature path).

## Assumptions

- **Leave-one-out is demonstrated here but wired in item 120.**
  `docs/spinal-curve-model.md`'s "Breaking circularity" section says "item 119
  should make it the actual per-label evaluation method for
  `stage3.per_label_offsets`", while queue-017 assigns "promote it from the
  test harness into the pipeline" to **item 120**, whose testable criteria are
  exactly the promotion's payoff (`mislabel` fires through plain `run_qc` on
  the mode-1 case; `mode1_displace` no longer needs a reconstruction; the
  recalibrated threshold sits between the clean and displaced distributions).
  The queue is the authority on item boundaries and the gate's approval text
  assigns no item, so the split is taken here: 119 changes the **fit**, 120
  changes the **evaluation**. AC9 satisfies the queue's stated testable
  criterion for 119 at the API level. If a reviewer reads the decision document
  as binding the promotion to 119, this item and 120 should be merged rather
  than 119 widened unilaterally.

- **Item 017's AC1 is honoured on item 017's GT fixtures, and the sweep
  exceeds it at one grid point.** Measured on this branch under the approved
  formulation: item 017's fixtures peak at `0.19198` mm (AC7, comfortably
  inside 0.5 mm), while the `build_clean_spine` sweep peaks at `0.552139` mm at
  5 levels × `(0.8, 0.8, 1.0)` spacing (AC8). The decision document states this
  outcome explicitly ("the sparse-count in-sample pass-through bound moves from
  effectively 0 mm to ~0.55 mm") and the gate approved the formulation
  including it. Stage 28's acceptance line — "A clean GT spine stays within
  item 017's 0.5 mm pass-through bound **across level counts and spacings**" —
  is therefore not literally satisfiable by the approved formulation at that one
  grid point. This item does **not** weaken item 017's AC1; it records the
  discrepancy in both directions (AC7 and AC8) so item 125 ticks that
  acceptance line against measured fact rather than against the aspiration.
  Captured for the queue boundary in [`insights.md`](../insights.md).

- **`SplineFit.tck` is removed rather than shimmed.** Retaining a derived
  `(t, c, k)` tuple would keep the legacy interface the decision document's
  first amendment exists to retire, and only two call sites read it directly
  (`spline.evaluate_spline`, `orientation.compute_spine_curvature`). Every
  other consumer — `spline_offset.py`, `consistency.py`,
  `sagittal_projection.py` — already goes through `evaluate_spline` and needs
  no change. (`neighbourhood.py` consumes offset *values*, never the fit.)

- **`fit_centroid_spline` gains a `smoothing` keyword** with signature
  `fit_centroid_spline(centroids, degree=3, *, smoothing=None, backend=None)`:
  `None` means `s = float(n_points)`, an explicit float is used verbatim. This
  is what lets `scripts/compare_curve_candidates.py` keep an honest
  interpolating baseline (AC4, AC24) without reintroducing `splprep`.

- **`pyproject.toml` is in this item's authorised paths**, limited to the one
  `scipy` bound. `make_splprep` was added in SciPy 1.15.0, so leaving
  `scipy>=1.7` would let a fresh install resolve a SciPy that cannot import the
  package. `pyproject.toml` is not one of the framework/process files that
  require a hand-back (`CLAUDE.md`, `aide.toml`, `.aide/**`, `vision.md`,
  `roadmap.md`, `.claude/**`). `constraints.txt` already pins `scipy==1.17.1`
  and is untouched, so CI is unaffected.

- **`max_offset_mm` moves in item 123, not here.** The gate's approval text
  records `15.0 → 25.0` as part of the approved decision, and queue-017 assigns
  "`mislabel`'s `max_offset_mm`" to item 123's recalibration deliverable. It is
  safe to defer: measured on this branch, the largest `offset_mm` any corpus
  case reaches under this item's change is `1.5775` mm (`mode6_crop_at_border`),
  so the rule's behaviour is identical at 15.0 and at 25.0 for every case that
  exists today. Raising it here would be an unverifiable threshold change with
  no observable effect, made in the item that lacks the leave-one-out
  distributions justifying it.

- **The goldens are regenerated here, not left red for item 123.** Queue-017
  says this item "should leave the corpus tests red in a way item 123 clears";
  under this repo's `auto-merge` mode (`aide.toml` `[git] mode`) the validator
  runs the full suite and a red suite cannot merge, so that instruction is
  unexecutable as written. Item 122 hit the same tension and resolved it by
  regenerating its own goldens; the same resolution is taken here, bounded by
  AC20 (no verdict, no finding, nothing outside `features.stage3` moves) so the
  regeneration stays auditable and item 123's remaining work — the threshold
  and both reference artifacts — is untouched.

- **Both `reference_*.json` artifacts are left stale on purpose.**
  `reference_default.json`'s `spline_offset_mm` distribution is noise about zero
  (L1 mean `7.4e-05` mm, std `2.1e-05` mm), so after this item a clean case's
  `~0.35` mm offset scores thousands of sigma out and
  `run_qc_with_reference` produces extra `reference_delta` findings (measured:
  `clean_control` goes from 6 to 21 reference-delta findings against the
  bundled default). The existing reference tests survive this — item 049's
  clean-control control builds its bracketing reference *from current code* in
  a temp cohort, and item 049's AC11 asserts `out_of_range_features != []`,
  which extra entries do not break — but the builder must confirm it rather
  than assume it (see [Testing Strategy](#testing-strategy)). Rebuilding either
  artifact is item 123's; `reference_verse_v1.json` additionally cannot be
  rebuilt without the real cohort and is byte-pinned by
  `test_098_stray_components.py`.

- **`aide check --queue 017` reports four pre-existing cross-spec errors that
  this item cannot clear.** They are all overlaps with items **118** and
  **122**, both already ✅ and merged, so nothing will land on top of this
  item's assertions: 118's spec pins `src/segfacet/features/spline.py` (the
  file this item exists to change) and lists `docs/spinal-curve-model.md` and
  `tests/test_118_curve_formulation_decision.py` as may-change, while 122
  lists `tests/test_122_signed_curvature.py`. This item's pins on those three
  files are load-bearing (AC15, AC17, AC25) and are kept; clearing the errors
  would mean editing a completed item's spec, which is out of scope here. The
  cross-spec check does not discount completed items — recorded in
  [`insights.md`](../insights.md).

- **The coincident-centroid crash is fixed to the extent of not regressing.**
  AC16 converts a SciPy failure into a descriptive `ValueError`; it does not
  make coincident centroids *fittable* (that would be a behaviour change about
  which point to keep, outside this item). Without it, rewriting this call site
  would replace today's `ValueError: Invalid inputs.` with a five-line FITPACK
  iteration message — a regression against item 017's AC5.

## Implementation Steps

The code path in `src/segfacet` (see `aide.toml` `project.source_dir`):

1. **`features/spline.py` — the `SplineFit` shape.** Replace the `tck: tuple`
   field with `spline` (the `scipy.interpolate.BSpline` returned by
   `make_splprep`) and add `smoothing: float`. Keep `u`, `degree`, `n_points`
   and the frozen dataclass. Update the class docstring: `t`/`c`/`k` are now
   reachable as `spline.t` / `spline.c` / `spline.k`.

2. **`features/spline.py` — the fit.** Change the import to
   `from scipy.interpolate import make_splprep`. Add the keyword-only
   `smoothing: Optional[float] = None` parameter; resolve
   `s = float(n_points) if smoothing is None else float(smoothing)`. Replace
   `tck, u = splprep([x, y, z], k=effective_degree, s=0)` with
   `spl, u = make_splprep([x, y, z], k=effective_degree, s=s)`. Record `s` on
   the returned `SplineFit`. Update the module docstring's "Deliberate CPU
   fallback (item 072)" paragraph, which names `splprep`/`splev`.

3. **`features/spline.py` — the coincident-centroid guard (AC16).** Before
   fitting, detect exactly-equal consecutive mm-coordinate triples among the
   input centroids. On a hit, raise `ValueError` naming the repeated coordinate
   and the `level_name`s that share it. Do not catch-and-rewrap SciPy's
   exception as the primary mechanism — the pre-check gives a message that
   names the actual cause; a defensive `except ValueError` around the
   `make_splprep` call may re-raise with the same style for any residual
   FITPACK failure, and must not swallow it.

4. **`features/spline.py` — evaluation.** `evaluate_spline` keeps its
   signature and its device-array marshalling, and evaluates via
   `fit.spline(host_u_values)`, which already returns `(N, 3)` — the
   `np.column_stack` over `splev`'s three-array list is no longer needed; cast
   to `float64` and return. Add a public first-derivative helper (AC14) with
   the same marshalling and `(N, 3)` contract, evaluating
   `fit.spline(host_u_values, nu=nu)`; export it from `__all__`.

5. **`features/orientation.py`.** Drop `from scipy.interpolate import splev`.
   Replace `derivs = splev(u_array, fit.tck, der=1)` with a call to step 4's
   helper, which returns `(n, 3)` directly — the `np.column_stack` over three
   arrays that follows it collapses to a single cast. Update the docstrings at
   the module head and on `compute_spine_curvature` that name `splev`. Nothing
   else in the function changes: item 122's signed-curvature reduction, its
   direction normalisation and its `curvature_plane` selection are untouched
   (AC15).

6. **`synth/identity_ordering_alignment.py`.** Correct the module docstring's
   `(item 017, splprep(..., s=0)), the displaced centroid is absorbed back`
   sentence, which is no longer true of the shipped fit. Docstring only — no
   generator behaviour changes.

7. **`pyproject.toml`.** `"scipy>=1.7"` → `"scipy>=1.15"`. Nothing else.

8. **`feature_docs.py`.** Rewrite the "Spline Offset" group note (currently
   "`scipy.interpolate.splprep, s=0 -> passes exactly through every centroid`")
   to describe the smoothing fit at `s = n_points` via `make_splprep`, and the
   "Orientation & Curvature" / `computation` string that names
   `splev, der=1`. Prose only; add and remove no `FEATURE_DOCS` key (AC27).

9. **`scripts/compare_curve_candidates.py`.** `_fit_interpolating_cubic` calls
   `fit_centroid_spline(centroids, smoothing=0.0)`; `_fit_smoothing_spline`
   calls `fit_centroid_spline(centroids)` and drops both its local `splprep`
   import and its hand-built `SplineFit(...)`. Check `_ParametricCurve` (around
   line 166), which wraps a `SplineFit`: it must go through `evaluate_spline`,
   not through `.tck`.

10. **Regenerate the corpus goldens:**
    `.venv/bin/python -m segfacet.synth.golden` — the one-command path; it
    writes canonical JSON bytes with `write_bytes`, so the `.gitattributes` LF
    pin on `tests/corpus/golden/*.json` holds.

11. **Regenerate `tests/golden/022_stage3_report.json`** by writing the
    `produced` text from `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`
    to that path — the test deliberately no longer self-heals (item 111). Write
    bytes with `\n`, never `write_text`.

12. **Regenerate the feature catalogue:** `.venv/bin/python -m segfacet.catalogue`
    (the same command `test_103`'s AC19 comparison uses).

13. **Reconcile the existing tests listed in [Testing Strategy](#testing-strategy)**,
    then run the [Validation](#validation) diff audit before committing.

## Authorised paths

**May change:**

- `src/segfacet/features/spline.py` — the fit itself: `make_splprep`,
  `s = n_points`, the `SplineFit` shape, the coincident guard, the derivative
  helper (AC1–AC6, AC11–AC14, AC16, AC17).
- `src/segfacet/features/orientation.py` — migrate the `splev(..., der=1)`
  tangent evaluation onto the new helper (AC2, AC14, AC15).
- `src/segfacet/synth/identity_ordering_alignment.py` — module docstring only;
  it asserts the shipped fit is `splprep(..., s=0)`.
- `src/segfacet/feature_docs.py` — the "Spline Offset" and
  "Orientation & Curvature" prose (AC26). No key added or removed.
- `scripts/compare_curve_candidates.py` — `_fit_interpolating_cubic`,
  `_fit_smoothing_spline` and `_ParametricCurve`, so the tool's candidate
  identities survive the `SplineFit` change (AC24, AC25).
- `pyproject.toml` — the single `scipy` lower bound (AC23).
- `docs/aide/feature_catalogue.generated.json` — regenerated via
  `python -m segfacet.catalogue`, never hand-edited (AC27).
- `docs/aide/feature_catalogue.generated.md` — likewise (AC27).
- `tests/corpus/golden/*.json` — the nine goldens, regenerated via
  `python -m segfacet.synth.golden`, never hand-edited (AC18, AC20).
- `tests/golden/022_stage3_report.json` — regenerated from the test's
  `produced` text, never hand-edited (AC19).
- `tests/test_119_curve_formulation.py` — the new test module.
- `tests/test_017_centroid_spline_fit.py` — `test_ac4_determinism_curved_spine`
  reads `fit1.tck[0]`, which no longer exists; re-express it against
  `fit.spline.t`. That one assertion only — item 017's AC1 tolerance and
  fixtures must not move (AC7).
- `tests/test_074_benchmark.py`, `tests/test_094_tptbox_image_layer.py`,
  `tests/test_095_env_migration.py` — each hardcodes `"scipy>=1.7"` in an
  "existing core dependencies unchanged" set; update that one literal to
  `"scipy>=1.15"` in each. No other assertion in these modules changes.
- `tests/test_072_backend_feature_port.py` — the fake-CuPy module installs
  forbidden `splprep`/`splev` attributes; add `make_splprep` alongside them so
  the guard still covers the call the fit actually makes. Names only.
- `docs/aide/insights.md` — append-only, per the out-of-scope-insight rule.

**Asserts against:**

- `src/segfacet/pipeline.py` — read and pinned byte-identical by AC22; the
  leave-one-out promotion is item 120's.
- `src/segfacet/heuristics/mislabel.py` — read and pinned by AC21:
  `max_offset_mm` stays `15.0`; item 123 raises it.
- `src/segfacet/reference/reference_default.json` and
  `src/segfacet/reference/reference_verse_v1.json` — read, not changed. Both
  are stale after this item by design (item 123 rebuilds them); the second is
  additionally byte-pinned by `test_098_stray_components.py`.
- `src/segfacet/synth/regression.py` — read, not changed.
  `_recon_leave_one_out_offset` is the technique AC9 mirrors and the workaround
  item 120 retires.
- `src/segfacet/features/spline_offset.py`, `features/consistency.py`,
  `features/sagittal_projection.py` — read, not changed. All three reach the
  curve through `evaluate_spline`, so the `SplineFit` change must be
  transparent to them; if any needs editing, the migration in step 4 is wrong.
- `constraints.txt` — read, not changed (already `scipy==1.17.1`).
- `docs/spinal-curve-model.md` — read, not changed. AC25 pins that its quoted
  non-VerSe numbers still reproduce.
- `tests/test_118_curve_formulation_decision.py` — read, not changed. AC25 is
  satisfied by this module staying green as committed.
- `tests/test_122_signed_curvature.py` — read, not changed. AC17 pins its
  near-coincident adversarial fixture; AC15 pins its signed-curvature contract.
- `tests/corpus/manifest.json` — read, not changed. The nine cases and their
  committed fixtures are the population AC18/AC20 regenerate against.
- `.gitattributes` — read, not changed: every file this item regenerates is
  already pinned (`tests/corpus/golden/*.json`, `tests/golden/*.json`,
  `docs/aide/feature_catalogue.generated.{json,md}`, `src/segfacet/**/*.py`).

`docs/aide/golden-decision-table.md` needs no entry on either list: this item
adds and removes no leaf path, so its measured `N/M leaf paths unwired` cells
hold untouched.

## Testing Strategy

New module: **`tests/test_119_curve_formulation.py`** — one focused test per
AC, plus the adversarial cases below. It may import
`segfacet.synth.clean_gt.build_clean_spine` and `tests/synthetic.py` helpers;
it must not import `scripts/compare_curve_candidates.py` as a package (load it
by path, the pattern `test_118` and `test_083` already use).

**Per-AC coverage.** AC1–AC6 are direct unit assertions on
`fit_centroid_spline`'s return. AC7 replays item 017's five fixture shapes.
AC8 rebuilds the 3 × 3 sweep grid. AC9/AC10 build the 8-level separation
fixture and measure both circularity modes with `compute_spline_offsets`.
AC11–AC13 are determinism / degenerate-input cases. AC14/AC15 exercise
`compute_spine_curvature` end to end. AC16/AC17 are the coincident and
near-coincident inputs. AC18–AC20 use `synth.golden.check_case_golden`,
`write_goldens` into two `tmp_path` directories, and a structural diff of the
regenerated goldens' `verdict`/`findings` against the pre-119 committed values
(captured as a fixture constant, not by re-reading a file this item rewrites).
AC21–AC22 are source/threshold assertions. AC23/AC26/AC27 read
`pyproject.toml`, `FEATURE_DOCS` and a fresh catalogue regeneration. AC24/AC25
load the comparison script by path.

**Adversarial and edge cases.**

- Zero and one centroid still raise `ValueError` with a human-readable message
  and no raw SciPy repr (item 017's AC5 contract, unchanged).
- Collinear centroids (a perfectly straight spine) — the smoothing fit must
  reduce to the exact line, offsets `≈ 0`, no degeneracy.
- Highly anisotropic mm coordinates (z-step 30 mm, x/y sub-mm).
- One level removed from the middle, the front and the back of a 6-level
  sequence.
- `smoothing=0.0` and `smoothing=1e6` (an absurdly loose bound) — neither
  raises; the latter is permitted to be near-linear but must stay finite and
  non-degenerate by AC13's arc-length ratio.
- Input sequence not mutated by the fit; `SplineFit` still frozen.
- `evaluate_spline` at `u = 0.0`, `u = 1.0` and 500 interior values: no NaN,
  no Inf.

**Existing tests to reconcile** (these pin behaviour this item changes; the
first validation round fails on them, not on new code, unless they are handled):

| Test | Why it moves | Resolution |
|---|---|---|
| `test_017_centroid_spline_fit.py::test_ac4_determinism_curved_spine` | Reads `fit1.tck[0]`; the field is gone. | Re-express against `fit.spline.t`. Authorised. |
| `test_017` AC1 / AC2 / AC3 pass-through tests | Offsets move from `0.0` to up to `0.19` mm at `fit.u`. | **No change** — all stay inside the 0.5 mm bound (measured). If any fails, the fit is wrong, not the test. |
| `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` | Strict text equality against `tests/golden/022_stage3_report.json`. | Regenerate the golden (step 11). Never edit the test. |
| `test_042_golden_determinism.py` (nine cases) | `reports_close` compares numeric leaves at `rel_tol=1e-9`; every `stage3` offset moves. | Regenerate the nine goldens (step 10). |
| `test_074_benchmark.py::test_ac13_core_dependencies_unchanged_no_cupy` | Hardcodes `"scipy>=1.7"`. | Update the literal to `"scipy>=1.15"`. |
| `test_094_tptbox_image_layer.py::test_ac1_existing_core_dependencies_unchanged` | Same literal. | Same. |
| `test_095_env_migration.py` (core-bounds-unchanged set) | Same literal. | Same. |
| `test_103_feature_catalogue.py::test_ac19_committed_docs_match_fresh_regeneration` | The group-note prose changes, so the committed artifact's bytes must too. | Regenerate the catalogue (step 12). |
| `test_072_backend_feature_port.py` | Installs forbidden `splprep`/`splev` on the fake CuPy module; the fit now calls `make_splprep`. | Add `make_splprep` to the forbidden names so the guard still bites. |
| `test_118_curve_formulation_decision.py::test_ac6_non_verse_measurements_reproduce_from_fresh_run` | `_fit_interpolating_cubic` delegates to `fit_centroid_spline`, which is no longer interpolating — the baseline's `0.0000138` mm would become `~0.55` mm. | Step 9. This test must stay green **unmodified** (AC25); editing it would falsify the decision document. |
| `test_036_clean_gt.py::AC11` (`offset_mm < 15.0`) | Offsets move but stay ≪ 15.0. | No change expected. |
| `test_018_per_vertebra_spline_offset.py` (`< 1.0` / `< 2.0` clean bounds, `>= 8.0` displaced bounds) | Clean offsets rise to ≤ `0.55` mm; displaced offsets rise. | No change expected — verify, do not pre-emptively edit. |
| `test_049_acceptance_stage6.py` AC10/AC11, `test_090`, `test_092`, `test_097`, `test_098` | Score cases against a reference whose `spline_offset_mm` distribution is now stale, adding `reference_delta` findings. | **Expected to survive**: AC10 builds its bracketing reference from current code in a temp cohort, AC11 asserts a non-empty set, and the rest filter by `rule_id`/label. Confirm by running them; if any genuinely fails, stop and hand back rather than editing it — the fix is item 123's reference rebuild. |

## Validation

Beyond the unit suite, observe the change on the corpus. No `[validation]`
profile is required — everything here runs on the default CPU venv with the
committed fixtures.

1. **See the feature come alive.**

   ```
   .venv/bin/python -m segfacet.synth.golden --out out/goldens-119
   ```

   Inspect `out/goldens-119/clean_control.json` at
   `features.stage3.per_label_offsets`: `offset_mm` values are now on the order
   of `1e-1` mm (max `≈ 0.347` for this case) where the committed pre-119
   golden read `≈ 1e-4`. `mode6_crop_at_border` is the largest at `≈ 1.578` mm.

2. **Audit the regeneration's narrowness (AC20).**

   ```
   git diff aide/queue-017 -- tests/corpus/golden tests/golden
   ```

   Every changed hunk must fall inside a `"stage3"` object. A changed
   `"verdict"`, `"findings"`, `"stage2"` or `"schema_version"` line means the
   change reached further than this item allows — stop and hand back.

3. **Confirm the decision document still reproduces (AC25).**

   ```
   .venv/bin/python scripts/compare_curve_candidates.py --out out/curve-candidates-119
   ```

   Then check `out/curve-candidates-119/curve_candidates.json`:
   `candidates.interpolating_cubic.clean_pass_through.in_sample.max_mm` must
   still read `≈ 0.0000138` (the baseline is still interpolating) and
   `candidates.smoothing_spline.clean_pass_through.in_sample.max_mm` still
   `≈ 0.552139`. If the first has moved toward the second, step 9 was missed
   and the tool is measuring the shipped fit twice under two names.

4. **Confirm the item's own boundary held.** `git diff aide/queue-017 --stat`
   must list neither `src/segfacet/pipeline.py` nor
   `src/segfacet/heuristics/mislabel.py` nor either `reference_*.json`.

## Dependencies

- **Item 118** (✅) — the decision this item implements, in
  [`docs/spinal-curve-model.md`](../../spinal-curve-model.md), together with
  its three "Revisions to apply when item 119 implements this" amendments and
  `scripts/compare_curve_candidates.py`.
- **Item 122** (✅) — owns `compute_spine_curvature`'s signed-curvature
  reduction, which AC15 pins unchanged across the tangent-source migration.
- **Item 042 / item 078** (✅) — provide `write_goldens`, `check_case_golden`
  and the numeric-tolerance comparison AC18 is judged by.
- **Item 103** (✅) — provides the catalogue generator AC27 regenerates through.
- **Human gate: "Spinal curve model — the deformity envelope"** — ✅ Approved
  by a person on 2026-08-27 (`progress.md`, `## Human gates`). This item is
  unblocked.

**Downstream:** item 120 promotes leave-one-out into `pipeline.py` on top of
this fit; item 121 joins `closest_u` to the tangent this item's derivative
helper exposes; item 123 recalibrates `max_offset_mm` and rebuilds both
reference artifacts; item 125 validates Stage 28 end to end.

## Decisions & Trade-offs

To be updated during implementation.
