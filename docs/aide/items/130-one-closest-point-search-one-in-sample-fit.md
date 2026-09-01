# Item 130 — One closest-point search, one in-sample fit

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 130
> **Objectives:** G7
> **Suggested branch:** `aide/130-one-closest-point-search-one`

---

## Description

Stage 29 deliverable **D6**. Two duplications in the spline layer, both
located and both measured, are collapsed into one implementation each.

**The closest-point search exists three times.** The identical
coarse-scan-over-`u`-then-`scipy.optimize.minimize_scalar` algorithm is
written out in full in three places with no link between them:

| location | bracket | `xatol` | backend param |
|---|---|---|---|
| `features/spline_offset.py::_find_closest_u` (line 255) | ±1 coarse step | `1e-6` | yes |
| `features/consistency.py::_find_closest_u` (line 128) | ±1 coarse step | `1e-6` | no |
| `scripts/compare_curve_candidates.py::_closest_point_distance` (line 208) | ±1 coarse step | `1e-7` | n/a |

Each carries its own `_N_SCAN = 500`. A change to the scan resolution, the
refinement bracket or `xatol` has to be made in three places, and a
divergence between the first two would surface as an inconsistency between
`stage3.per_label_offsets[].closest_u` and
`stage3.monotonic_consistency.u_values[]` — a wrong number in the record,
not a red test. This item gives the search **one owner**,
`features/spline.py` (the module that owns `SplineFit` and `evaluate_spline`
and is already imported by every caller), and re-points all three callers at
it — the script included, so `docs/spinal-curve-model.md`'s published
measurements are made by the shipped code rather than by a private copy of
it.

**The in-sample fit is computed twice per case.** `pipeline.py:194` fits
`fit_centroid_spline(ordered_centroids)` for curvature / tangent
orientations / monotonic consistency, and
`compute_leave_one_out_spline_offsets` immediately fits the *same* spline
again as its internal `reference_fit` (`spline_offset.py:468`). The offset
layer gains a keyword-only `fit=` so the pipeline can fit once and hand the
result down, while the function keeps working standalone (fitting internally
only when no fit is passed) — it is public API with callers in the test
suite and in `synth/`.

**This is a consolidation, not a behaviour change.** Every existing
value-level assertion in `test_017`–`test_023`, `test_119`–`test_122`,
`test_125` and `test_129` must pass **unchanged**; that, plus the
byte-unchanged committed feature catalogue, is the evidence that nothing
moved. The item is written so equality is structural rather than lucky: the
consolidated helper reproduces each call site's current arithmetic exactly
(same scan grid, same bracket, same clipping, curve evaluated at the
**clipped** parameter to derive the point and the distance), and the script
keeps its own `xatol=1e-7` by passing it rather than by owning a copy.

**Not in this item.** No change to the curve formulation, the smoothing
factor, the held-out floor, or `mislabel`'s thresholds. No change to what
`compute_monotonic_consistency` *judges* — item 132 owns that, and this item
exists partly so 132 is made against one implementation. No de-duplication
of the two *runtime* in-sample searches per case
(`compute_vertebra_tangent_orientations` and `compute_monotonic_consistency`
each search all `n` centroids against the same fit): they are numerically
identical today, caching one into the other is a value-carrying change to
what `u_values[]` is derived from, and that is item 132's decision, not
this item's. No regeneration of any committed artifact.

## Acceptance Criteria

- [ ] **AC1: the shared search is public API of the spline module.**
  `segfacet.features.spline` exports `find_closest_point` and
  `ClosestPointOnCurve`, both listed in the module's `__all__`.

- [ ] **AC2: `ClosestPointOnCurve` carries parameter, point and distance.**
  It is a frozen dataclass with exactly the fields `closest_u: float`,
  `point_mm: tuple` (three floats) and `distance_mm: float`.

- [ ] **AC3: the search accepts a `SplineFit`.**
  `find_closest_point(point_mm, fit)` returns a `ClosestPointOnCurve` whose
  `closest_u` matches the minimising parameter for that fit.

- [ ] **AC4: the search accepts a bare curve evaluator.**
  `find_closest_point(point_mm, evaluate)` — where `evaluate` is any callable
  mapping an array of `u` values to an `(N, 3)` mm-coordinate array — returns
  the same record type, so a caller with no `SplineFit` (the comparison
  script's polynomial and axis-wise candidates) needs no copy of the
  algorithm.

- [ ] **AC5: the returned parameter is in the closed unit interval.**
  For any query point and any supported curve, `0.0 <= closest_u <= 1.0`.

- [ ] **AC6: the three returned fields are mutually consistent.**
  `point_mm` equals the curve evaluated at `closest_u`, and `distance_mm`
  equals the Euclidean norm of `query_point - point_mm`, both to within
  floating-point equality of a direct recomputation.

- [ ] **AC7: the search's defaults are named module constants.**
  `segfacet.features.spline` exposes the coarse-scan resolution and the
  refinement tolerance as module-level constants whose values are `500` and
  `1e-6`, and they are `find_closest_point`'s defaults.

- [ ] **AC8: `n_scan` is honoured.** A call with a non-default `n_scan`
  evaluates the curve on a coarse grid of exactly that many parameter values.

- [ ] **AC9: `xatol` is honoured.** A call with a non-default `xatol` reaches
  `minimize_scalar` with that value in its `options`.

- [ ] **AC10: invalid search parameters raise a readable `ValueError`.**
  `n_scan < 2` and `xatol <= 0` each raise `ValueError` naming the offending
  parameter and its value — never a `ZeroDivisionError` or a raw SciPy
  message.

- [ ] **AC11: the search accepts `backend=None` for signature uniformity.**
  `find_closest_point` has a keyword-only `backend` parameter defaulting to
  `None`, matching the Stage-2/3 feature-function convention (item 072), and
  the numeric work runs on host NumPy/SciPy regardless.

- [ ] **AC12: exactly one `minimize_scalar` call site remains.** An AST walk
  over every `.py` file under `src/` and `scripts/` finds exactly one call to
  `minimize_scalar`, and it is in `src/segfacet/features/spline.py`.

- [ ] **AC13: the two feature modules no longer define the search.** Neither
  `segfacet.features.spline_offset` nor `segfacet.features.consistency`
  defines a module-level `_find_closest_u`, and neither module's source
  contains a coarse `linspace` scan of its own; each reaches the search
  through `segfacet.features.spline.find_closest_point`.

- [ ] **AC14: the comparison script delegates and keeps its tolerance.**
  `scripts/compare_curve_candidates.py` obtains every closest point from
  `segfacet.features.spline.find_closest_point`, passing `xatol=1e-7`, and
  defines no coarse-scan-plus-refine of its own.

- [ ] **AC15: the offset layer accepts an externally supplied in-sample fit.**
  `compute_leave_one_out_spline_offsets` has a keyword-only `fit` parameter
  defaulting to `None`; when a `SplineFit` is supplied it is used as the
  reference fit and the function makes **no** `fit_centroid_spline` call for
  it.

- [ ] **AC16: supplying the fit changes no value.** For the same centroid
  sequence, `compute_leave_one_out_spline_offsets(centroids, spacing_mm=s)`
  and `compute_leave_one_out_spline_offsets(centroids, spacing_mm=s,
  fit=fit_centroid_spline(centroids))` return equal lists, field for field.

- [ ] **AC17: a mismatched fit is rejected.** Passing a `fit` whose
  `n_points` differs from `len(centroids)` raises `ValueError` naming both
  counts.

- [ ] **AC18: the pipeline fits the in-sample spline once per case.**
  `extract_feature_record` on a five-label clean spine calls
  `fit_centroid_spline` exactly **6** times (one in-sample fit plus the five
  held-out refits), and on a three-label map exactly **1** time (one
  in-sample fit; the sub-five-level path takes the in-sample fallback and
  refits nothing).

- [ ] **AC19: the one fit is the one every Stage-3 consumer sees.**
  `pipeline.py`'s source binds a single `fit_centroid_spline(...)` result and
  passes that same object to the curvature, tangent-orientation,
  monotonic-consistency and held-out-offset calls.

- [ ] **AC20: the two in-sample searches agree exactly.** For a clean spine
  and for a spine with one displaced level,
  `compute_monotonic_consistency(centroids, fit).u_values` equals
  `[o.closest_u for o in compute_spline_offsets(centroids, fit)]` element for
  element, exactly — the property the three-copy state could have violated
  silently.

- [ ] **AC21: item 129's coincident-centroid pre-check is preserved.** A
  label map in which two labels share an exact centroid still yields a record
  whose `stage3_unavailable` names reason `coincident_centroids` and both
  levels, with no `stage3` key and no exception.

- [ ] **AC22: the committed feature catalogue does not move.** A fresh
  `segfacet.catalogue` regeneration byte-matches the committed
  `docs/aide/feature_catalogue.generated.json` and
  `docs/aide/feature_catalogue.generated.md`.

- [ ] **AC23: the catalogue's `closest_u` computation text stays true.**
  `feature_docs`' entry for `stage3.per_label_offsets[].closest_u` describes
  a 500-point coarse scan refined by a bounded `minimize_scalar` at
  `xatol 1e-6`, and those two numbers equal the shipped module constants
  asserted in AC7.

- [ ] **AC24: the search is deterministic and non-mutating.** Two calls with
  the same query point and curve return equal `ClosestPointOnCurve` records,
  and neither the query point array nor the centroid sequence passed to
  `compute_leave_one_out_spline_offsets` is mutated.

- [ ] **AC25: the decision document's measurements still reproduce.**
  `tests/test_118_curve_formulation_decision.py`'s non-VerSe reproduction
  check — a fresh `scripts/compare_curve_candidates.py` run resolving every
  non-VerSe row of `docs/spinal-curve-model.md`'s measurements table within
  its stated 0.001 mm tolerance — passes against the delegating script.

## Assumptions

Clarify mode is `assume` (`aide.toml` → `loop.clarify`). Each default below
was taken rather than asked.

- **The search's owner is `features/spline.py`, not a new module.** It
  already owns `SplineFit`, `evaluate_spline` and
  `find_coincident_centroid_pair`, and is already imported by both feature
  callers and by the script. A fourth module would add an import edge for no
  gain. Pins: `spline.py` gains a `scipy.optimize` import at module top; no
  import cycle is created (`spline.py` imports neither `spline_offset` nor
  `consistency`).

- **One function, two accepted curve shapes.** `find_closest_point` takes
  either a `SplineFit` or a callable evaluator, normalised internally to one
  evaluator, rather than shipping two public entry points. The script's
  candidates (`_ParametricCurve`, `_AxisCurve`, `_PolynomialPlaneCurve`)
  expose `evaluate(u) -> (N, 3)` and are not `SplineFit`s, so the callable
  form is required; a second public name for the `SplineFit` case would be
  ceremony.

- **The script keeps `xatol=1e-7` by passing it, not by owning a copy.**
  Unifying the script onto the feature default `1e-6` would move its numbers
  by an unmeasured amount against a 0.001 mm reproduction tolerance on
  values as small as `0.0000138` mm. Passing the tolerance keeps
  `docs/spinal-curve-model.md`'s table exactly reproducible while still
  leaving one definition of the algorithm.

- **`distance_mm` is derived by evaluating the curve at the clipped
  parameter**, not read from `minimize_scalar`'s `result.fun`. The two are
  bit-identical today (`result.fun` is `f(result.x)`, the bracket lies
  inside `[0, 1]` so the clip is an identity, and both call sites evaluate
  the same deterministic curve function), and deriving it keeps AC6's three
  fields consistent by construction.

- **The supplied `fit` is validated on count, not on geometry.**
  `compute_leave_one_out_spline_offsets` checks `fit.n_points ==
  len(centroids)` and documents that the caller must supply the in-sample
  fit through *these* centroids at the module defaults. Re-deriving the fit
  to verify it would reinstate the second fit this item exists to remove.
  The length check runs up front, before the one-centroid early return, so a
  mismatched fit is always rejected loudly (a `SplineFit` always has
  `n_points >= 2`, so passing one alongside a single centroid is by
  definition a mismatch).

- **The unreachable degenerate-bracket guard is preserved verbatim.** All
  three current copies carry an `if lo >= hi: return u_coarse` branch. For
  any `n_scan >= 2` the bracket is non-empty, so the branch is dead
  defensive code; it is carried into the shared helper unchanged rather than
  removed, because deleting it is a behaviour question and this item changes
  no behaviour. Recorded in Decisions & Trade-offs, not silently dropped.

- **`compute_spline_offsets`'s public signature is unchanged.**
  `test_120::test_ac13_in_sample_function_signature_and_semantics_unchanged`
  pins it, and no caller needs a change there — only its internals move to
  the shared helper.

- **Item 072's eight-function `backend` roster is not extended.**
  `tests/test_072_backend_feature_port.py`'s AC2 enumerates a fixed list of
  functions; `find_closest_point` takes `backend=None` for consistency
  (AC11) but is not added to that list, so `test_072` needs no
  reconciliation.

- **No human gate.** The offset module's docstring records that closing the
  four-level blind spot needs a change to the fit's *degree*, governed by
  the 2026-08-27 "Spinal curve model — the deformity envelope" gate. This
  item changes no degree, no smoothing factor and no threshold, so it raises
  no gate and resolves none.

## Implementation Steps

1. **`src/segfacet/features/spline.py` — add the shared search.**
   - Add `from scipy.optimize import minimize_scalar` at module top.
   - Add module constants for the coarse-scan resolution (`500`) and the
     refinement tolerance (`1e-6`), each with a one-line comment saying what
     it buys (sub-mm resolution over a ~400 mm whole-spine extent).
   - Add the frozen dataclass `ClosestPointOnCurve(closest_u, point_mm,
     distance_mm)`.
   - Add `find_closest_point(point_mm, curve, *, n_scan=<const>,
     xatol=<const>, backend=None) -> ClosestPointOnCurve`:
     validate `n_scan >= 2` and `xatol > 0` with readable `ValueError`s;
     normalise `curve` to an evaluator (a `SplineFit` becomes a closure over
     `evaluate_spline(fit, u, backend=backend)`); coarse-scan
     `np.linspace(0.0, 1.0, n_scan)`, take `argmin` of the squared distances
     via `np.einsum("ij,ij->i", diffs, diffs)`; bracket
     `lo = max(0.0, u_coarse - step)`, `hi = min(1.0, u_coarse + step)` with
     `step = 1.0 / (n_scan - 1)`; if `lo >= hi` skip refinement (defensive,
     see Assumptions); otherwise `minimize_scalar(..., bounds=(lo, hi),
     method="bounded", options={"xatol": xatol})` and clip `result.x` into
     `[0, 1]`; evaluate the curve once at the final parameter to fill
     `point_mm` and `distance_mm`.
   - Document the contract in the docstring: parameter domain `[0, 1]`
     closed, the bracket rule, the tolerance, determinism, the host-CPU
     fallback, and that `closest_u` is the value item 132 reuses. Extend the
     module's `Public API` docstring section and `__all__`.

2. **`src/segfacet/features/spline_offset.py` — delegate the search, accept a
   fit.**
   - Delete `_sq_distance` and `_find_closest_u` and the module's own
     `_N_SCAN`; import `find_closest_point` from `features.spline`.
   - In `compute_spline_offsets`, replace the `_find_closest_u` +
     `evaluate_spline` pair with one `find_closest_point(pt, fit,
     backend=backend)` call, taking `closest_u` and `point_mm` from the
     record and computing `diff = pt - point_mm` as before.
   - Give `compute_leave_one_out_spline_offsets` a keyword-only
     `fit: Optional[SplineFit] = None`. Validate `fit.n_points ==
     len(centroids)` up front (before the one-centroid early return) with a
     `ValueError` naming both counts. Use `fit` as `reference_fit` when
     supplied; otherwise fit internally exactly as today. The per-level
     refits are untouched.
   - Update the module docstring's opening "The closest point on the spline
     is found by…" paragraph to point at the shared helper. **Preserve every
     substring the existing suite pins**: the `minimize_scalar` mention in
     the "Deliberate CPU fallback" section, and the "Held-out evaluation",
     "four-level blind spot", "Terminal-vertebra exclusion" and "RAS axis
     contract" sections verbatim (see Testing Strategy).
   - Document the new `fit` parameter in the function docstring, including
     the caller's obligation (the in-sample fit through these centroids at
     the module defaults) and the count check.

3. **`src/segfacet/features/consistency.py` — delegate the search.**
   Delete `_sq_distance_u`, `_find_closest_u`, the module `_N_SCAN` and the
   `scipy.optimize` and `evaluate_spline` imports that become unused; call
   `find_closest_point(pt, fit).closest_u` in
   `compute_monotonic_consistency`. Nothing else in the module changes.

4. **`src/segfacet/pipeline.py` — pass the single fit down.** Add
   `fit=fit` to the `compute_leave_one_out_spline_offsets(...)` call and
   update the comment above the `fit = fit_centroid_spline(...)` line to say
   the one in-sample fit now serves curvature, tangent orientations,
   monotonic consistency *and* the held-out offsets' reference fit. Leave
   item 129's coincident-centroid pre-check and the `>= 2 labels` guard
   exactly as they are — the single fit stays inside the same `elif` branch,
   after the pre-check. Do not introduce the substring
   `compute_spline_offsets(` into this file
   (`test_120::test_ac11_pipeline_source_calls_leave_one_out_not_in_sample`
   forbids it).

5. **`scripts/compare_curve_candidates.py` — delegate.** Reduce
   `_closest_point_distance` to a thin wrapper that calls
   `find_closest_point(point_mm, evaluate_fn, n_scan=n_scan, xatol=1e-7)`
   and returns the existing `(distance_mm, closest_u)` tuple, so its eight
   call sites are untouched; drop the local `minimize_scalar` import and the
   inline `_sq` objective. Keep the import deferred inside the function, in
   the script's existing style. Update the module docstring's "One shared
   coarse-scan-then-refine closest-point search (mirroring
   `segfacet.features.spline_offset._find_closest_u`)" sentence and the
   `_N_SCAN` comment's "mirrors `segfacet.features.spline_offset._N_SCAN`"
   claim — both name a symbol that no longer exists. Do not introduce the
   substring `SplineFit(` into this file (pinned by
   `test_119::test_ac24_script_source_builds_no_splinefit_by_hand_and_imports_no_splprep`).

6. **Confirm nothing moved.** Run the full suite; `test_017`–`test_023`,
   `test_119`–`test_122`, `test_125` and `test_129` must pass with no edit
   to any of them. If a value-level assertion fails, the consolidation is
   not equivalent — fix the consolidation, never the assertion.

## Authorised paths

**May change:**

- `src/segfacet/features/spline.py` — owns the one closest-point search
  (AC1–AC11).
- `src/segfacet/features/spline_offset.py` — delegates the search; gains the
  keyword-only `fit=` (AC13, AC15–AC17).
- `src/segfacet/features/consistency.py` — delegates the search (AC13).
- `src/segfacet/pipeline.py` — binds one in-sample fit and passes it down
  (AC18, AC19).
- `scripts/compare_curve_candidates.py` — delegates the search, keeps
  `xatol=1e-7` (AC14, AC25).
- `tests/test_130_one_closest_point_search.py` — this item's tests.
- `docs/aide/items/130-one-closest-point-search-one-in-sample-fit.md` — this
  spec.

**Asserts against:**

- `docs/aide/feature_catalogue.generated.json` — AC22 pins it byte-for-byte
  against a fresh `segfacet.catalogue` regeneration. Allowlisted for
  byte-exact fresh-vs-committed comparison in
  `tests/committed_artifact_guard.py` under ground `emission-clamped` (item
  127); this item adds no allowlist entry.
- `docs/aide/feature_catalogue.generated.md` — same, the rendered form.
- `src/segfacet/feature_docs.py` — AC23 reads the
  `stage3.per_label_offsets[].closest_u` entry's `computation` text and pins
  it against the shipped constants. Not modified: the text stays true
  because the defaults do not change.
- `docs/spinal-curve-model.md` — AC25 reads the measurements table and its
  stated tolerance and requires every non-VerSe row still to resolve from a
  fresh script run. Not modified.
- `tests/test_118_curve_formulation_decision.py` — AC25 imports its
  reproduction check and re-runs it, the pattern
  `test_119::test_ac25_test_118_ac6_reproduction_stays_green` already uses.
  Not modified.
- `src/segfacet/features/orientation.py` — AC19/AC20 pin that
  `compute_spine_curvature` and `compute_vertebra_tangent_orientations`
  still receive the pipeline's single fit and that the tangent layer's
  `closest_u` values agree with the offsets'. Not modified.

## Testing Strategy

New module: **`tests/test_130_one_closest_point_search.py`**. One focused
test per AC, plus the adversarial cases below.

**Per-AC notes where the mechanics are not obvious:**

- **AC8/AC9 (parameters honoured).** Monkeypatch
  `segfacet.features.spline.minimize_scalar` with a recording wrapper that
  delegates to the real one, and assert the recorded `options["xatol"]`.
  For `n_scan`, wrap the evaluator in a counting closure and assert the
  coarse call received exactly `n_scan` parameter values.
- **AC12 (one call site).** Walk every `.py` under `src/` and `scripts/`
  with `ast`, count `ast.Call` nodes whose callee resolves to the name
  `minimize_scalar`, assert the count is 1 and the file is
  `src/segfacet/features/spline.py`. Use the AST, **not** a `grep` over
  lines — import statements and docstrings mention the name legitimately.
- **AC18 (fit count).** The count must be taken at **two** patch points with
  one shared counter: `segfacet.features.spline.fit_centroid_spline` (which
  `pipeline.py` reaches through its deferred, call-time import) and
  `segfacet.features.spline_offset.fit_centroid_spline` (bound at import
  time by that module's top-level `from … import`, so patching the spline
  module alone misses every refit). Each wrapper delegates to the real
  function. Fixtures: `build_clean_spine()` (five levels → 6) and
  `build_clean_spine(levels=("L1", "L2", "L3"))` (→ 1).
- **AC22 (catalogue).** Regenerate into `tmp_path` via
  `segfacet.catalogue.main(["--json", …, "--md", …])` and compare
  `read_bytes()` against the committed pair — the shape
  `test_129::test_ac20_catalogue_regeneration_matches_committed_artifacts`
  uses. This comparison is legitimate under item 127's guard because both
  paths are on `tests/committed_artifact_guard.py`'s `ALLOWLIST`
  (`emission-clamped`). Do **not** add any other byte-exact fresh-vs-committed
  float comparison to this module, and do **not** hash a source file against
  a hardcoded literal to prove scope — scope is proved by the diff against
  the Authorised paths list ([`.aide/conventions.md`](../../../.aide/conventions.md) §1).
- **AC25 (script reproduction).** Import
  `tests/test_118_curve_formulation_decision.py` and call its non-VerSe
  reproduction test directly, the way
  `test_119::test_ac25_test_118_ac6_reproduction_stays_green` does, so a
  regression fails under item 130's own module too.

**Adversarial / edge cases:**

- Query point *on* the curve (offset ≈ 0) and query point far off it, on the
  same fit — both return a `closest_u` inside `[0, 1]`.
- Query point beyond both curve ends (extrapolation direction): the result
  clamps to an endpoint parameter rather than escaping `[0, 1]`.
- A two-centroid fit (degree clamped to 1) and a three-centroid fit — the
  shortest curves the search can be asked about.
- `n_scan=2` (the smallest legal grid) returns a finite record; `n_scan=1`
  and `n_scan=0` raise `ValueError`; `xatol=0.0` and `xatol=-1.0` raise
  `ValueError`.
- A curve evaluator returning a non-finite coordinate is not silently turned
  into a NaN `closest_u` — assert the failure mode is observable
  (`ValueError`, or a NaN distance the caller can see), not a silent
  plausible number.
- `compute_leave_one_out_spline_offsets` with `fit=` supplied for a
  four-level sequence (the sub-five-level in-sample fallback) and for a
  six-level sequence (the held-out path), each equal to the standalone call.
- `fit=` with `n_points` one too high and one too low, and with a
  single-centroid sequence — each a `ValueError` naming both counts.
- Determinism: two `extract_feature_record` calls on the same fixture
  produce equal `per_label_offsets` and equal `monotonic_consistency`.
- Immutability: the centroid sequence and the query array are unchanged
  after every call.

**Existing tests to reconcile.** This item changes no default and no
observable value, so nothing should need editing — the sweep below names
what a careless change would break, and each must pass **unmodified**:

- `tests/test_120_leave_one_out_offset.py`
  - `test_ac11_pipeline_source_calls_leave_one_out_not_in_sample` — asserts
    `"compute_spline_offsets(" not in pipeline.py`. Step 4 must not
    introduce that substring.
  - `test_ac11_extract_feature_record_offsets_match_leave_one_out_values` —
    compares the pipeline's offsets against a **standalone** (no `fit=`)
    call; the strongest existing evidence that passing the fit is
    equivalent.
  - `test_ac13_in_sample_function_signature_and_semantics_unchanged` — pins
    `compute_spline_offsets`'s signature.
  - `test_ac6_tie_break_rule_is_documented` (docstring must keep
    "ascending" + "label") and
    `test_ac31_spline_offset_module_docstring_states_ras_contract`
    (docstring must keep `load_volume`, `centroid_voxel`, `spacing`, and
    `R`/`A`/`S`).
- `tests/test_129_coincident_centroids_and_held_out_floor.py`
  - `test_ac25_docstring_states_five_level_floor_and_reason` (docstring must
    keep "five", "cubic", "interpolat", "weight") and
    `test_ac26_docstring_records_measured_limitation_and_governing_gate`
    (must keep "0.001", "15", "degree", and "human gate"/"deformity") — the
    docstring rewrite in step 2 is the likeliest accidental breakage in this
    item.
  - `test_ac20_catalogue_regeneration_matches_committed_artifacts`,
    `test_ac21_floor_is_five`, and the four-level blind-spot tests.
- `tests/test_119_curve_formulation.py`
  - `test_ac24_script_source_builds_no_splinefit_by_hand_and_imports_no_splprep`
    — step 5 must not introduce `SplineFit(` into the script.
  - `test_ac24_parametric_curve_wraps_via_evaluate_spline` — inspects
    `_ParametricCurve`'s source, which this item does not touch.
  - `test_ac25_test_118_ac6_reproduction_stays_green`.
- `tests/test_072_backend_feature_port.py` — AC2's fixed eight-function
  roster is not extended (see Assumptions), so no change is due here.
- `tests/test_018_per_vertebra_spline_offset.py`,
  `tests/test_020_neighbour_consistency.py`,
  `tests/test_022_stage3_serialisation.py`,
  `tests/test_121_tangent_orientation.py`,
  `tests/test_122_signed_curvature.py`,
  `tests/test_125_stage28_validation.py`,
  `tests/test_123_recalibrate_and_regenerate.py` — value-level assertions
  over `closest_u`, `offset_mm` and `u_values[]`; all must pass unchanged.
  These are the item's real proof, and no test module above may be edited.

## Validation

The unit suite proves equivalence; two things need observing beyond it.

1. **The published measurements are made by the shipped code.** Run

   ```
   .venv/bin/python scripts/compare_curve_candidates.py --out out/curve-candidates
   ```

   Confirm it exits 0 and that every non-VerSe row of
   `docs/spinal-curve-model.md`'s measurements table resolves in
   `out/curve-candidates/curve_candidates.json` within the document's stated
   0.001 mm tolerance. *(Discard the `out/` directory afterwards; nothing
   under it is committed.)*

   The VerSe-sourced rows are gated on the real VerSe19 cohort, reached
   through the `SEGFACET_VERSE_COHORT` environment variable rather than
   through an `aide.toml` `[validation]` profile (none of `pyradiomics` /
   `docker` / `gpu` covers a dataset mount). When that variable is unset or
   does not point at a directory, re-run with `--verse-cohort <root>` is not
   possible: record those rows as **❓ Unverified** with that reason. Never
   report them as passing on the strength of a clean skip.

2. **One search, one fit, visible in the tree.** Confirm
   `grep -rn minimize_scalar src/ scripts/` reports call-and-import lines in
   `src/segfacet/features/spline.py` only, and that a single-case CLI run
   still produces a report:

   ```
   .venv/bin/python -m segfacet run --seg tests/corpus/fixtures/clean_control_seg.nii.gz --out out/130-check --no-reference
   ```

   `--no-reference` is required: the default real-VerSe19 reference is not
   calibrated for the tiny synthetic corpus fixtures (see `CLAUDE.md`
   Gotchas, measured at item 125). Confirm the report contains a `stage3`
   block with `per_label_offsets` and `monotonic_consistency`.

## Dependencies

- **Item 126** (✅) — the golden retirement. With the whole-record snapshots
  gone, a change in this layer has no snapshot regeneration surface, which
  is why a pure consolidation can assert "nothing moved" against
  value-level tests rather than against regenerated files.
- **Item 127** (✅) — the committed-artifact guard and its allowlist. AC22's
  byte-exact catalogue comparison is legitimate only because both catalogue
  paths carry an `emission-clamped` allowlist entry; the guard classifies
  this item's new test module.
- **Item 129** (✅) — `pipeline.py`'s `stage3_unavailable` pre-check for
  coincident centroids (AC21 preserves it) and
  `_MIN_LEVELS_FOR_HELD_OUT = 5` (AC18's three-label expectation depends on
  it).

**Downstream:** item 131 (tangent-angle normalisation) and item 132
(monotonicity judged against the smoothed fit) both build on the
consolidated search; item 132 reuses `find_closest_point(...).closest_u`
rather than adding a fourth copy. Item 135 replays Stage 29's acceptance.

## Decisions & Trade-offs

**Amended post-merge (2026-08-31): the `test_072` "needs no reconciliation"
Assumption was wrong.**

`compute_spline_offsets` originally passed the `SplineFit` straight to
`find_closest_point`, which wraps it in a closure over
`segfacet.features.spline.evaluate_spline` — not `spline_offset`'s own name.
`spline_offset.py` no longer imported `evaluate_spline` at all (only
`find_closest_point`), so
`tests/test_072_backend_feature_port.py::test_ac10_spline_offsets_forwards_backend_to_evaluate_spline`,
which `monkeypatch.setattr(spline_offset_mod, "evaluate_spline", spy)`, raised
`AttributeError: <module 'segfacet.features.spline_offset'> does not have the
attribute 'evaluate_spline'` — a genuine regression, not a false alarm; that
test asserts a real observable (backend forwarding), pinned before this item
existed. Fixed on the production side, honestly: `spline_offset.py` now
imports `evaluate_spline` at module level and builds its own
`_evaluate(u_values) -> evaluate_spline(fit, u_values, backend=backend)`
closure, passed to `find_closest_point` as the callable-evaluator curve
(rather than the bare `SplineFit`) so the search's evaluation route runs
through `spline_offset`'s own patchable name and still forwards `backend`.
Numerically identical to the pre-fix path — `find_closest_point`'s own
`SplineFit` branch built the same closure over the *same* `evaluate_spline`
function, just reached from `spline.py`'s namespace instead of
`spline_offset`'s — so no `_sq_distance`/`minimize_scalar` call count,
`u_values`, or catalogue value changes; verified directly (non-pytest) by
reproducing AC10's monkeypatch and asserting `len(received) > 0` and
`sentinel_backend in received`. The Assumptions section's "Item 072's
eight-function `backend` roster is not extended... so `test_072` needs no
reconciliation" claim is superseded by this note — no roster edit was needed,
but a production-side call-routing fix was.

**Confirmed at implementation time (2026-08-31):**

- **`find_closest_point` normalises `curve` internally, no new public
  entry point.** A `SplineFit` is wrapped in a closure over `evaluate_spline`
  the moment it is recognised (`isinstance(curve, SplineFit)`); a bare
  callable is used as-is. Matches the Assumptions section exactly.
- **`compute_spline_offsets` takes `closest_u` and `point_mm` straight off
  the `ClosestPointOnCurve` record and derives `dx_mm`/`dy_mm`/`dz_mm` from
  `pt - point_mm`, keeping its own `offset_mm = sqrt(dx**2+dy**2+dz**2)`
  computation rather than reusing `distance_mm`** — the same arithmetic the
  prior `_find_closest_u` + separate `evaluate_spline` call performed, so no
  rounding path changes. Verified: `docs/aide/feature_catalogue.generated.json`
  and `.md` regenerate byte-identical to the committed pair (AC22), and
  `test_017`-`test_023`, `test_119`-`test_122`, `test_125`, `test_129` were
  read in full and require no edits under this diff.
- **The CLI validation command in this spec's "Validation" section is
  slightly stale against the shipped CLI**: `segfacet run` now requires both
  `--scan` and `--seg` (a prior stage added that constraint after this spec
  was written); `--seg` alone errors with "provide --scan and --seg". Ran the
  check with `--scan` pointed at the same fixture as `--seg` instead — the
  scan's pixel content is irrelevant to confirming the `stage3` block shape
  the Validation step asks for. Not a defect in this item's scope; logged to
  `docs/aide/insights.md` for the spec/CLI drift.
- **VerSe-sourced rows in `docs/spinal-curve-model.md`'s measurements table
  are ❓ Unverified**, exactly per the Validation section's documented
  fallback: `SEGFACET_VERSE_COHORT` is unset in this environment and no
  `--verse-cohort` root is available. All 11 non-VerSe rows were confirmed to
  reproduce within the stated 0.001 mm tolerance by running
  `tests/test_118_curve_formulation_decision.py`'s reproduction helpers
  directly against a fresh `scripts/compare_curve_candidates.py` run (the
  same check `test_130`'s AC25 test performs).

Recorded at spec time, confirmed unchanged during implementation:

- **The degenerate-bracket branch is dead code and is kept anyway.** With
  `step = 1/(n_scan - 1) > 0` and `u_coarse ∈ [0, 1]`, `lo = max(0, u_c -
  step)` is always strictly less than `hi = min(1, u_c + step)`, so the
  `lo >= hi` guard present in all three current copies cannot fire for any
  `n_scan >= 2`. It is carried into the shared helper unchanged: removing it
  is a behaviour question, and this item changes no behaviour. Worth
  revisiting when something else legitimately touches the helper.
- **The two runtime in-sample searches per case are left in place.**
  `compute_vertebra_tangent_orientations` (via `compute_spline_offsets`) and
  `compute_monotonic_consistency` each search all `n` centroids against the
  same fit and get the same answers. Caching one into the other would halve
  the searches, but it changes what `u_values[]` is *derived from*, which is
  item 132's territory. AC20 pins the agreement instead, so the redundancy
  is now an asserted invariant rather than an unobserved coincidence.
