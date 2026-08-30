# Spinal curve model — formulation decision

> Item 118 ([`docs/aide/items/118-decide-the-spinal-curve-formulation.md`](aide/items/118-decide-the-spinal-curve-formulation.md)),
> Stage 28. This document is the deliberation that chooses the replacement
> curve formulation for `segfacet.features.spline` — it changes no production
> code itself. Every number quoted below is reproduced by
> [`scripts/compare_curve_candidates.py`](../scripts/compare_curve_candidates.py);
> see [Reproducing these numbers](#reproducing-these-numbers).

## Why this exists

`features/spline.py` fits an **interpolating** spline (`splprep(..., s=0)`), so
the curve passes exactly through every centroid it exists to judge:
`stage3.per_label_offsets[].offset_mm` is therefore zero (to floating-point
precision) on every committed golden and on real VerSe19 GT, and
`stage3.monotonic_consistency.is_monotonic` is `True` even on a case with a
genuinely swapped label order. A curve fit *from* the centroids and then used
to *judge* a centroid is circular unless something breaks the circle — either
the family must be stiff enough to resist bending onto an outlier, or the
fitting technique must exclude the point under test.

Five candidate families were measured on the same ordered vertebra-centroid
sequences the shipped pipeline uses, in both an `in_sample` mode (the point
under test is part of the fit — today's behaviour) and a `leave_one_out` mode
(fit through every *other* centroid, the technique already used in
`segfacet.synth.regression._recon_leave_one_out_offset`).

## Decision

### Family

**Choice:** `smoothing_spline` — the same parametric B-spline construction as
today's `fit_centroid_spline`, but with SciPy's `splprep` smoothing parameter
`s` set to the number of input points instead of `0`.

**Consequence:** the fit is no longer forced through every centroid, so a
genuinely displaced vertebra can separate from the curve — at the cost of
also no longer being a perfect pass-through fit for clean GT (the sparse-count
in-sample pass-through bound moves from effectively `0` mm to `~0.55` mm; see
Evidence). Item 119 inherits this: `stage3.per_label_offsets[].offset_mm` will
no longer read as `0.0` on the goldens (that regeneration is item 123's job,
already anticipated by this item's Testing Strategy).

**Evidence:** `lsq_bspline_fixed_knots` and `polynomial_per_plane` both show a
larger in-sample separation margin than `smoothing_spline` on a synthetic
single-vertebra displacement (`1.873170` mm and `-0.244683` mm smallest margin
respectively, against `smoothing_spline`'s `0.140882` mm — `lsq_bspline_fixed_knots`
is in fact negative, meaning it still re-absorbs the point at small
displacements), but both fail badly on **real** VerSe19 anatomy: their
in-sample max pass-through on the cohort's most coronally-deviated
(genuinely scoliotic) cases is `17.675639` mm and `27.859506` mm — large
enough to falsely flag real deformity. `smoothing_spline`'s equivalent
real-GT figure is `2.099807` mm, close to today's baseline
(`interpolating_cubic`, `0.0000422` mm) while still providing genuine,
non-zero separation. `robust_downweighted` (iteratively-reweighted robust
regression) was excluded rather than measured: it needs SciPy/NumPy
functionality this project does not ship (no Huber/Tukey-weighted spline
fit), and adding it would mean a new runtime dependency, which item 118's
Assumptions forbid.

### Degrees of freedom

**Choice:** cubic degree, clamped `k = min(3, n_points - 1)` exactly as today
(so a 2-point input still works), with the smoothing factor set to
`s = n_points` — SciPy's own documented starting point
(`s` in `(m - sqrt(2m), m + sqrt(2m))`). No fixed interior-knot count is
chosen independently of cohort size.

**Consequence:** degrees of freedom scale automatically with how many
vertebrae are present, with no per-cohort retuning — but at small level
counts there simply is no spare freedom to smooth with: a cubic spline
through 5 points has exactly enough control points for one polynomial
segment, so `smoothing_spline` provably degenerates to the same fit as the
stiffer, fixed-knot alternatives at that scale.

**Evidence:** on the synthetic clean-GT sweep (spanning the minimum-supported
level count up through a full lumbar span, over several spacings including
an anisotropic one), `smoothing_spline`'s in-sample max pass-through is
`0.552139` mm — numerically identical to `lsq_bspline_fixed_knots`'s
`0.552139` mm at the same grid point, confirming the
degenerate-to-single-segment behaviour at the sweep's smallest multi-level
count. The differentiation instead shows up at the larger, real vertebra
counts the VerSe cohort provides (see Family).

### Parameterisation

**Choice:** chord-length parameterisation — the same `u` in `[0, 1]` that
`splprep` already computes for today's interpolating fit, shared unchanged
across `interpolating_cubic`, `smoothing_spline` and
`lsq_bspline_fixed_knots`.

**Consequence:** every downstream consumer of `u` — `closest_u`, the
`_find_closest_u` scan/refine strategy, and the monotonic-`u` consistency
check — keeps its existing meaning; item 119 changes the fitting call, not
what "the spline parameter" denotes. `polynomial_per_plane` deliberately used
a *different* parameterisation (the cranio-caudal, stacking-axis coordinate
rather than arc length) — one further reason it is not the chosen family,
since adopting it would also mean redefining `u` for the whole Stage 3
consistency machinery.

**Evidence:** the shared parameterisation is directly why `smoothing_spline`
and `lsq_bspline_fixed_knots` reach numerically identical clean-GT pass-through
figures at `n = 5` (`0.552139` mm, both) — they are evaluated at the same `u`
nodes derived the same way; `polynomial_per_plane`'s own-domain reparameterisation
instead reaches `0.548571` mm at the same grid point, a different (and, on
real GT, far worse — `27.859506` mm) fit entirely.

### Breaking circularity

**Choice:** leave-one-out — fit the curve through every *other* present
level, then measure the excluded level's offset against that fit. This is
the technique `synth/regression.py`'s `_recon_leave_one_out_offset` already
uses for the mislabel reconstruction path; item 119 should make it the actual
per-label evaluation method for `stage3.per_label_offsets`, not only a
synthetic-test technique.

> **How it actually landed (2026-08-28):** the work split differently from the
> sentence above — item 119 changed the fit itself (`make_splprep` smoothing
> spline), and item **120** promoted leave-one-out into the pipeline as
> `compute_leave_one_out_spline_offsets`, per
> [`docs/aide/queue/queue-017.md`](aide/queue/queue-017.md), which owns the
> work breakdown. Item numbers in this document are the proposal's suggestion,
> not the assignment of record.

**Consequence:** every evaluated family separates a displaced vertebra almost
identically well once leave-one-out is applied — the family choice stops
being what makes displacement detectable, because the point under test never
gets a chance to bend the curve toward itself. This means the family decision
(above) is free to be driven by real-anatomy faithfulness rather than by
in-sample separation strength.

**Evidence:** in leave-one-out mode, the smallest recorded separation margin
at a 5 mm synthetic displacement is `4.999144` mm for `smoothing_spline` and
`4.999936` mm for `interpolating_cubic` — both essentially equal to the
displacement itself, regardless of family. In in-sample mode, by contrast,
`interpolating_cubic`'s smallest margin is `-0.0000232` mm (no separation at
all — the motivating bug) and `smoothing_spline`'s is only `0.140882` mm.
Leave-one-out is therefore what actually fixes Stage 28's circularity problem;
the family choice matters for a different criterion (real-anatomy fidelity).

### Deformity envelope

**Status:** PROPOSED — pending human gate. This is a proposal for a person to
decide, not a settled decision — see
[`docs/aide/progress.md`](aide/progress.md)'s `## Human gates` table, the row
naming the spinal curve model's deformity envelope (`Blocks: 119, 120, 121,
123, 125`).

**Choice:** raise `mislabel`'s `max_offset_mm` threshold (currently `15.0` mm,
tuned against today's always-zero interpolating offset) to a proposed
`25.0` mm when item 119 switches `stage3.per_label_offsets[].offset_mm` to a
leave-one-out `smoothing_spline` measurement.

**Consequence:** a real, undisplaced but strongly scoliotic spine would no
longer risk tripping the mislabel check under leave-one-out evaluation, at
the accepted cost of missing a genuine displacement smaller than the new
envelope (the false-negative trade-off this gate exists to weigh). A person
must decide whether that trade is acceptable before item 119 lands; this
document does not make that call.

**Evidence:** the highest leave-one-out offset observed on any real VerSe
GT case (including the cohort's most coronally-deviated, genuinely scoliotic
cases) under the chosen `smoothing_spline` family is `21.073357` mm —
comfortably below the proposed `25.0` mm envelope, while still above the
leave-one-out separation margin measured for even a small (5 mm) synthetic
displacement (`4.999144` mm smallest margin, i.e. a leave-one-out offset that
tracks displacement almost 1:1 once real-curvature noise is set aside). The
`25.0` mm envelope is therefore set above the noise floor real anatomy
produces, not below the smallest detectable synthetic displacement — the gate
is precisely about whether that trade-off is acceptable.

## Measurements

Every `Key` below is a dot-separated path into a freshly generated
`curve_candidates.json` (see [Reproducing these numbers](#reproducing-these-numbers)).

| Key | Value | Units | Source |
|---|---|---|---|
| candidates.interpolating_cubic.clean_pass_through.in_sample.max_mm | 0.0000138 | mm | synthetic clean-GT sweep (level counts 2/3/5 x 3 spacings incl. anisotropic) |
| candidates.smoothing_spline.clean_pass_through.in_sample.max_mm | 0.552139 | mm | synthetic clean-GT sweep (level counts 2/3/5 x 3 spacings incl. anisotropic) |
| candidates.lsq_bspline_fixed_knots.clean_pass_through.in_sample.max_mm | 0.552139 | mm | synthetic clean-GT sweep (level counts 2/3/5 x 3 spacings incl. anisotropic) |
| candidates.polynomial_per_plane.clean_pass_through.in_sample.max_mm | 0.548571 | mm | synthetic clean-GT sweep (level counts 2/3/5 x 3 spacings incl. anisotropic) |
| candidates.interpolating_cubic.separation.smallest_margin_mm.in_sample | -0.0000232 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), in-sample |
| candidates.smoothing_spline.separation.smallest_margin_mm.in_sample | 0.140882 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), in-sample |
| candidates.lsq_bspline_fixed_knots.separation.smallest_margin_mm.in_sample | -0.244683 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), in-sample |
| candidates.polynomial_per_plane.separation.smallest_margin_mm.in_sample | 1.873170 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), in-sample |
| candidates.smoothing_spline.separation.smallest_margin_mm.leave_one_out | 4.999144 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), leave-one-out |
| candidates.interpolating_cubic.separation.smallest_margin_mm.leave_one_out | 4.999936 | mm | synthetic separation sweep (T1-T8, displacements 5/10/20 mm), leave-one-out |
| candidates.smoothing_spline.verse_scoliotic.max_pass_through_mm.in_sample | 2.099807 | mm | VerSe19 real GT (n=80 discovered, 17 selected as coronally deviated), in-sample |
| candidates.lsq_bspline_fixed_knots.verse_scoliotic.max_pass_through_mm.in_sample | 17.675639 | mm | VerSe19 real GT (n=80 discovered, 17 selected as coronally deviated), in-sample |
| candidates.polynomial_per_plane.verse_scoliotic.max_pass_through_mm.in_sample | 27.859506 | mm | VerSe19 real GT (n=80 discovered, 17 selected as coronally deviated), in-sample |
| candidates.interpolating_cubic.verse_scoliotic.max_pass_through_mm.in_sample | 0.0000422 | mm | VerSe19 real GT (n=80 discovered, 17 selected as coronally deviated), in-sample |
| candidates.smoothing_spline.verse_scoliotic.max_pass_through_mm.leave_one_out | 21.073357 | mm | VerSe19 real GT (n=80 discovered, 17 selected as coronally deviated), leave-one-out |
| candidates.smoothing_spline.determinism.compared_samples | 100 | samples | synthetic determinism run (two independent fits, same input) |

**Non-degeneracy check** (used for `degenerate_inputs`, both fixtures, every
evaluated candidate: `raised: false`, `degenerate: false`): a fit is
degenerate if any evaluated coordinate is non-finite, or if the fitted
curve's sampled arc length differs from the centroid polyline length by more
than a factor of `3.0`.

**Coronal-deviation measure** (used to rank and select the VerSe19 scoliotic
cases above): the maximum perpendicular distance, in mm, of any centroid from
the straight line joining the most cranial and most caudal centroid, measured
in the left-right / cranio-caudal (coronal) plane of the RAS-reoriented
volume `segfacet.io.load_volume` guarantees. Selection rule: every case with
`coronal_deviation_mm` at or above `8.0` mm (`SCOLIOSIS_THRESHOLD_MM`); 17 of
the 80 discovered VerSe19 cases qualified.

## Reproducing these numbers

**Command:** `.venv/bin/python scripts/compare_curve_candidates.py --out out/curve-candidates --verse-cohort dataset-verse19training`

**Artifact path:** `out/curve-candidates/curve_candidates.json` — every `Key`
above is a dot-separated path into this JSON (e.g.
`candidates.smoothing_spline.clean_pass_through.in_sample.max_mm`).

**Tolerance:** 0.001 mm absolute difference between a quoted `Value` and the
freshly-generated artifact's resolved value for every mm-scale row; exact
equality for the one count-valued row (`compared_samples`). Every measurement
here is deterministic (no RNG, no wall-clock reads) — a fresh run produces
bit-identical `candidates`/`sweep` blocks (see the tool's own `--out`-to-`--out`
determinism check), so the 0.001 mm tolerance exists only to absorb ordinary
cross-platform floating-point noise, not genuine drift. When the VerSe19
cohort is unreachable, every VerSe-sourced row above (`Source` mentioning
"VerSe19") is skipped rather than checked — a run without `--verse-cohort`
records those `verse_scoliotic` blocks as `status: "skipped"` with a reason,
never a silent pass.

## Revisions to apply when item 119 implements this

Three amendments to the decision above, recorded after the measurements were
taken. None invalidates a measured number: the comparison script fitted
`smoothing_spline` through `splprep`, and the amended API carries identical `s`
semantics, so every value in `## Measurements` still reproduces.

> **Correction (2026-08-30, measured at item 125's stage validation):** the
> "still reproduces" claim above is true for 15 of the 16 documented keys but
> not all 16. Re-running `scripts/compare_curve_candidates.py --verse-cohort
> dataset-verse19training` against the shipped `fit_centroid_spline`
> (`make_splprep`) reproduces every key within the stated 0.001 mm tolerance
> **except** `candidates.smoothing_spline.verse_scoliotic.max_pass_through_mm.leave_one_out`,
> which measures `20.683092` mm against the documented `21.073357` mm.
> `make_splprep` is an independent smoothing-spline implementation, not a
> `splprep` wrapper — an identical `s` does not guarantee an identical fit for
> every input, and one of the 17 selected scoliotic cases' leave-one-out fits
> is sensitive to the difference. Immaterial to the shipped
> `mislabel.max_offset_mm = 13.0`: item 123's interior-only recalibration
> superseded the `25.0` mm envelope this figure fed (see
> [`docs/reference-build.md`](reference-build.md), rebuild records 2026-08-29).

### The fit uses `make_splprep`, not `splprep`

Item 119 constructs the curve with `scipy.interpolate.make_splprep`. SciPy
documents `splprep` as a legacy FITPACK wrapper and `make_splprep` as its
supported replacement, so building a new formulation on the legacy interface
would mean adopting a deprecation on the day it ships.

Three consequences item 119 owns:

- **Dependency floor.** `make_splprep` was added in SciPy 1.15.0.
  `pyproject.toml` currently declares `scipy>=1.7`, so that bound rises to
  `>=1.15`. `constraints.txt` already pins `scipy==1.17.1`, so CI is unaffected.
- **Return shape.** `make_splprep` returns a `(BSpline, u)` pair, not
  `(tck, u)`. This is not a rename: evaluation moves from `splev(u, tck)` to
  `spl(u)`, and the derivative from `splev(u, tck, der=1)` to `spl(u, nu=1)`.
  Every consumer of `SplineFit` is affected — `spline_offset.py`,
  `consistency.py`, `orientation.py`, `neighbourhood.py`.
- **The smoothing choice is unchanged.** `s` keeps its meaning as a bound on
  the weighted sum of squared residuals, so `### Degrees of freedom`'s
  `s = n_points` carries over verbatim.

### Spline weights — deferred, not rejected

`make_splprep` accepts a per-point weight vector `w`, where `w[i]` is the
reciprocal of the standard deviation of point `i`'s positional error. The
decision above fits every centroid with equal weight. Two uses are identified
and deliberately deferred beyond Stage 28:

- **Down-weight vertebrae touching the image border.** A vertebra clipped by
  the field of view has a truncated voxel cloud, so its centroid is displaced
  toward the image interior by an amount reflecting the crop rather than
  anatomy. Fitting it at full weight drags the curve toward that artefact. The
  per-label border-contact signal this needs already exists — it is what
  `heuristics/border.py` reads.
- **Up-weight the terminal vertebrae when they are clear of the border.** A
  spline is least constrained at its ends, so the cranial-most and caudal-most
  levels (C1/C2, L5/S1) carry the most influence over end behaviour and the
  least support. Weighting them up where they are known-complete stabilises the
  ends. Doing so where they are clipped would amplify the first problem, which
  is why the two uses are one scheme rather than two.

Deferred because the weighting scheme would itself need calibrating against
real GT, whereas Stage 28's remit is to make the offset and orientation
features carry signal at all. Equal weights are the honest baseline to measure
that against.

### The deformity envelope is expected to be revised

`### Deformity envelope` proposes one envelope covering all anatomy. A later
refinement is anticipated: separate envelopes for normal and scoliotic spines,
so that a curve magnitude which is a finding in one population is expected
anatomy in the other.

That refinement points at **pathology differentiation** — telling a scoliotic
spine from a normal one — which is a different objective from the failure-mode
detection this repository is scoped to, where the question is whether a
*segmentation* is wrong rather than whether an *anatomy* is atypical. Recorded
here so the distinction is deliberate when it is taken up. Whether it belongs
in FACET at all is a `vision.md` question, not one item 119 should answer by
implementing it.
