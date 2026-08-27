#!/usr/bin/env python3
"""Spinal-curve candidate comparison tool (item 118).

Item 118 is the *deliberation* that chooses the replacement formulation for
`segfacet.features.spline` (Stage 28) -- it produces **no production code**.
This is its measurement half: an AIDE *project tool* (the shape of
``scripts/refresh_reference.py``, not part of the shipped ``segfacet``
package) that fits five candidate curve families through the same ordered
vertebra-centroid sequences the shipped pipeline uses, and scores every
evaluated family on the five judgement criteria queue-017 names:

* ``clean_pass_through`` -- how far the fitted curve strays from clean GT
  centroids it was (or was not) fit through, swept over a level-count x
  spacing grid.
* ``separation`` -- whether a displaced vertebra's offset separates from the
  clean baseline, at several displacement magnitudes.
* ``verse_scoliotic`` -- whether the most coronally-deviated real VerSe19 GT
  cases are still judged clean.
* ``degenerate_inputs`` -- whether a 2-level input and a truncated-FOV input
  survive without raising and without tripping a non-degeneracy check.
* ``determinism`` -- whether two independent fits of the same input agree
  bitwise.

Every judgement is measured in **both** circularity modes -- ``in_sample``
(the point under test is part of the fit) and ``leave_one_out`` (fit through
every *other* centroid, following the technique already in
``segfacet.synth.regression._recon_leave_one_out_offset``) -- so the cost and
benefit of excluding the point under test is visible per family rather than
argued.

The candidate identifiers are fixed strings (item 125 addresses them by
name): ``interpolating_cubic`` (today's shipped ``fit_centroid_spline``, used
unchanged as the baseline), ``smoothing_spline``, ``lsq_bspline_fixed_knots``,
``polynomial_per_plane``, and ``robust_downweighted`` (excluded -- see
``_EXCLUSION_REASONS`` -- rather than adding a new runtime dependency for an
iteratively-reweighted robust regression).

Every candidate shares one curve interface: ``evaluate(u_values) -> (N, 3)``
mm-coordinates for parameter values ``u`` in ``[0, 1]``. For the three
spline-family candidates ``u`` is the chord-length parameterisation SciPy's
``splprep`` already computes (the same values ``fit_centroid_spline`` uses);
for ``polynomial_per_plane`` -- which fits the lateral and antero-posterior
offset as low-order polynomials of the *cranio-caudal* (stacking-axis, RAS
``S``) coordinate rather than of arc length -- ``u`` is linearly remapped onto
that coordinate's own training range. One shared coarse-scan-then-refine
closest-point search (mirroring
``segfacet.features.spline_offset._find_closest_u``) therefore works
unmodified for every candidate.

Usage::

    python scripts/compare_curve_candidates.py --out out/curve-candidates
    python scripts/compare_curve_candidates.py --out out/curve-candidates \\
        --verse-cohort <path/to/the/local/VerSe19/cohort/root>

Cohort resolution (AC18): ``--verse-cohort`` if given, else the
``SEGFACET_VERSE_COHORT`` environment variable, else "not found" -- in which
case every VerSe-derived measurement degrades to a genuine, structured skip
(``status: "skipped"``) rather than a failure, and ``main`` still returns 0.
No literal dataset path lives in this file. Cohort discovery is a recursive
glob for ``*_seg-vert_msk.nii.gz`` beneath the resolved root (AC19), so a
nested or flat layout both yield the same case list.

Self-contained: imports only ``segfacet.*`` production modules (plus SciPy /
NumPy / NiBabel, already installed dependencies) -- never imports the
``tests`` package, so it runs unmodified in a deployed checkout with no test
fixtures present.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Environment variable naming the real VerSe19 cohort root (AC18) -- the
#: same variable tests/test_084_stage12_acceptance.py and
#: tests/test_091_stage14_acceptance.py already use.
VERSE_COHORT_ENV = "SEGFACET_VERSE_COHORT"

#: Real-VerSe mask filename suffix (item 082 recipe).
VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"

#: Fixed candidate identifiers (item 125 addresses them by name).
CANDIDATE_IDS: Tuple[str, ...] = (
    "interpolating_cubic",
    "smoothing_spline",
    "lsq_bspline_fixed_knots",
    "polynomial_per_plane",
    "robust_downweighted",
)

#: Candidates excluded from evaluation, with the non-empty reason recorded in
#: the artifact (AC10). ``robust_downweighted`` needs an iteratively
#: reweighted (Huber/Tukey-style) robust regression that SciPy/NumPy do not
#: ship -- adding it would mean a new runtime dependency (e.g. statsmodels or
#: scikit-learn), which the item 118 Assumptions forbid.
_EXCLUSION_REASONS: Dict[str, str] = {
    "robust_downweighted": (
        "requires an iteratively-reweighted least-squares robust regression "
        "(e.g. Huber/Tukey biweight) not available in SciPy/NumPy/NiBabel "
        "without adding a new runtime dependency; excluded per item 118's "
        "Assumptions rather than approximated."
    ),
}

#: Clean-GT sweep grid (AC12): >=3 distinct level counts including 2, and
#: >=3 distinct spacings including at least one anisotropic spacing.
SWEEP_LEVEL_COUNTS: Tuple[int, ...] = (2, 3, 5)
SWEEP_SPACINGS: Tuple[Tuple[float, float, float], ...] = (
    (1.0, 1.0, 1.0),
    (1.0, 1.0, 2.0),
    (0.8, 0.8, 1.0),
)
_SWEEP_LUMBAR_LEVELS: Tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5")
_SWEEP_CURVE_AMPLITUDE_MM = 6.0

#: Separation-sweep spine: a longer (8-level thoracic) span so the
#: fixed-knot / smoothing families have spare degrees of freedom to show a
#: measurable difference from the interpolating baseline (a 5-level span
#: leaves ``lsq_bspline_fixed_knots`` with zero spare interior knots -- see
#: ``_fit_lsq_bspline_fixed_knots``).
_SEPARATION_LEVELS: Tuple[str, ...] = ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8")
_SEPARATION_SPACING: Tuple[float, float, float] = (1.0, 1.0, 1.0)
_SEPARATION_CURVE_AMPLITUDE_MM = 6.0
_SEPARATION_MAGNITUDES_MM: Tuple[float, ...] = (5.0, 10.0, 20.0)

#: Degenerate-input fixtures (AC15).
_TWO_LEVEL_LEVELS: Tuple[str, ...] = ("L1", "L2")
_TRUNCATED_FOV_FULL_LEVELS: Tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5")
_TRUNCATED_FOV_KEEP = 3  # simulate a scan that only captured the cranial 3 of 5

#: Non-degeneracy check (item 118 Assumptions): a fit is degenerate when any
#: evaluated coordinate is non-finite, or when the fitted curve's sampled arc
#: length differs from the centroid polyline length by more than this
#: factor.
NON_DEGENERACY_ARC_LENGTH_FACTOR = 3.0

#: Determinism check sample count (AC16).
_DETERMINISM_N_SAMPLES = 100

#: Real-GT scoliotic-case selection threshold, in mm (item 118 Assumptions'
#: coronal-deviation measure): the maximum perpendicular distance, in the
#: coronal (left-right / cranio-caudal) plane, of any centroid from the
#: straight line joining the most cranial and most caudal centroid.
SCOLIOSIS_THRESHOLD_MM = 8.0

#: Closest-point search coarse-scan resolution (mirrors
#: segfacet.features.spline_offset._N_SCAN).
_N_SCAN = 500


# =========================================================================== #
# Shared curve interface + closest-point search
# =========================================================================== #


class _ParametricCurve:
    """Wraps a ``segfacet.features.spline.SplineFit``-shaped ``(t, c, k)``
    tck through :func:`segfacet.features.spline.evaluate_spline`."""

    def __init__(self, fit) -> None:
        self._fit = fit

    def evaluate(self, u_values) -> np.ndarray:
        from segfacet.features.spline import evaluate_spline

        return evaluate_spline(self._fit, u_values)


class _AxisCurve:
    """Wraps three independent per-axis callables ``fx(u), fy(u), fz(u)``."""

    def __init__(self, fx: Callable, fy: Callable, fz: Callable) -> None:
        self._fx, self._fy, self._fz = fx, fy, fz

    def evaluate(self, u_values) -> np.ndarray:
        u_arr = np.asarray(u_values, dtype=np.float64)
        return np.column_stack(
            [np.asarray(self._fx(u_arr)), np.asarray(self._fy(u_arr)), np.asarray(self._fz(u_arr))]
        )


class _PolynomialPlaneCurve:
    """Fits lateral (x) and antero-posterior (y) offset as low-order
    polynomials of the cranio-caudal (z, stacking-axis) coordinate; ``u`` in
    ``[0, 1]`` is linearly remapped onto the training z-range."""

    def __init__(self, px: np.ndarray, py: np.ndarray, z_min: float, z_max: float) -> None:
        self._px, self._py = px, py
        self._z_min, self._z_max = z_min, z_max

    def evaluate(self, u_values) -> np.ndarray:
        u_arr = np.asarray(u_values, dtype=np.float64)
        z = self._z_min + u_arr * (self._z_max - self._z_min)
        x = np.polyval(self._px, z)
        y = np.polyval(self._py, z)
        return np.column_stack([x, y, z])


def _closest_point_distance(evaluate_fn: Callable, point_mm: np.ndarray, n_scan: int = _N_SCAN) -> Tuple[float, float]:
    """Coarse-scan-then-refine closest point on ``evaluate_fn``'s curve to
    ``point_mm``. Mirrors
    ``segfacet.features.spline_offset._find_closest_u``, but works against
    any candidate exposing the shared ``evaluate(u) -> (N, 3)`` interface."""
    from scipy.optimize import minimize_scalar

    u_scan = np.linspace(0.0, 1.0, n_scan)
    pts = evaluate_fn(u_scan)
    diffs = pts - point_mm
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)
    best_idx = int(np.argmin(sq_dists))
    u_coarse = float(u_scan[best_idx])

    step = 1.0 / (n_scan - 1)
    lo = max(0.0, u_coarse - step)
    hi = min(1.0, u_coarse + step)
    if lo >= hi:
        return math.sqrt(float(sq_dists[best_idx])), u_coarse

    def _sq(u_scalar: float) -> float:
        pt = evaluate_fn(np.array([u_scalar]))[0]
        diff = pt - point_mm
        return float(np.dot(diff, diff))

    result = minimize_scalar(_sq, bounds=(lo, hi), method="bounded", options={"xatol": 1e-7})
    return math.sqrt(float(result.fun)), float(np.clip(result.x, 0.0, 1.0))


# =========================================================================== #
# Candidate fit builders
# =========================================================================== #


def _fit_interpolating_cubic(centroids: Sequence) -> _ParametricCurve:
    from segfacet.features.spline import fit_centroid_spline

    return _ParametricCurve(fit_centroid_spline(centroids))


def _fit_smoothing_spline(centroids: Sequence) -> _ParametricCurve:
    from scipy.interpolate import splprep

    from segfacet.features.spline import SplineFit

    n = len(centroids)
    k = min(3, n - 1)
    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)
    s = float(n)  # SciPy's suggested starting point: s in (m - sqrt(2m), m + sqrt(2m))
    tck, u = splprep([x, y, z], k=k, s=s)
    fit = SplineFit(tck=tck, u=tuple(float(v) for v in u), degree=k, n_points=n)
    return _ParametricCurve(fit)


def _fit_lsq_bspline_fixed_knots(centroids: Sequence) -> _AxisCurve:
    from scipy.interpolate import LSQUnivariateSpline

    from segfacet.features.spline import fit_centroid_spline

    base_fit = fit_centroid_spline(centroids)
    u_nodes = np.array(base_fit.u, dtype=np.float64)
    degree = base_fit.degree
    n = len(centroids)

    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)

    # LSQUnivariateSpline needs n > n_interior + degree + 1 data points.
    n_interior = max(0, min(3, n - degree - 2))
    knots = np.array([], dtype=np.float64)
    if n_interior > 0:
        quantiles = np.linspace(0.0, 1.0, n_interior + 2)[1:-1]
        candidate_knots = np.unique(np.quantile(u_nodes, quantiles))
        knots = candidate_knots[(candidate_knots > u_nodes.min()) & (candidate_knots < u_nodes.max())]

    def _fit_axis(coord: np.ndarray):
        if knots.size > 0:
            try:
                return LSQUnivariateSpline(u_nodes, coord, t=knots, k=degree)
            except Exception:
                pass
        return LSQUnivariateSpline(u_nodes, coord, t=np.array([], dtype=np.float64), k=degree)

    return _AxisCurve(_fit_axis(x), _fit_axis(y), _fit_axis(z))


def _fit_polynomial_per_plane(centroids: Sequence) -> _PolynomialPlaneCurve:
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)
    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    n = len(centroids)
    degree = min(3, n - 1)
    px = np.polyfit(z, x, degree)
    py = np.polyfit(z, y, degree)
    return _PolynomialPlaneCurve(px, py, float(z.min()), float(z.max()))


_CANDIDATE_BUILDERS: Dict[str, Callable[[Sequence], Any]] = {
    "interpolating_cubic": _fit_interpolating_cubic,
    "smoothing_spline": _fit_smoothing_spline,
    "lsq_bspline_fixed_knots": _fit_lsq_bspline_fixed_knots,
    "polynomial_per_plane": _fit_polynomial_per_plane,
}


# =========================================================================== #
# Synthetic fixture helpers
# =========================================================================== #


def _clean_centroids(levels: Sequence[str], spacing: Tuple[float, float, float], curve_amplitude_mm: float) -> List:
    from segfacet.features.centroids import compute_centroid
    from segfacet.synth.clean_gt import build_clean_spine

    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)
    return [compute_centroid(spine.seg_img, label) for label in spine.labels]


def _displace_centroid(centroid, magnitude_mm: float):
    per_axis = magnitude_mm / math.sqrt(2.0)
    x, y, z = centroid.centroid_mm
    return dataclasses.replace(centroid, centroid_mm=(x + per_axis, y + per_axis, z))


def _polyline_length_mm(centroids: Sequence) -> float:
    total = 0.0
    for i in range(1, len(centroids)):
        a = np.array(centroids[i - 1].centroid_mm, dtype=np.float64)
        b = np.array(centroids[i].centroid_mm, dtype=np.float64)
        total += float(np.linalg.norm(b - a))
    return total


def _arc_length_mm(evaluate_fn: Callable, n: int = 200) -> float:
    u = np.linspace(0.0, 1.0, n)
    pts = evaluate_fn(u)
    diffs = np.diff(pts, axis=0)
    return float(np.sum(np.linalg.norm(diffs, axis=1)))


def _is_degenerate(evaluate_fn: Callable, centroids: Sequence, factor: float) -> bool:
    check_u = np.linspace(0.0, 1.0, 50)
    pts = evaluate_fn(check_u)
    if not np.all(np.isfinite(pts)):
        return True
    poly_len = _polyline_length_mm(centroids)
    if poly_len <= 0.0:
        return False
    ratio = _arc_length_mm(evaluate_fn) / poly_len
    return ratio > factor or ratio < (1.0 / factor)


# =========================================================================== #
# Judgement measurement passes (AC11-AC16)
# =========================================================================== #


def _sweep_grid_cases() -> List[List]:
    cases = []
    for count in SWEEP_LEVEL_COUNTS:
        levels = _SWEEP_LUMBAR_LEVELS[:count]
        for spacing in SWEEP_SPACINGS:
            cases.append(_clean_centroids(levels, spacing, _SWEEP_CURVE_AMPLITUDE_MM))
    return cases


def _measure_clean_pass_through(fit_builder: Callable, grid_cases: List[List]) -> Dict[str, Any]:
    in_sample_max = 0.0
    loo_max = 0.0
    for centroids in grid_cases:
        fit = fit_builder(centroids)
        for c in centroids:
            pt = np.array(c.centroid_mm, dtype=np.float64)
            dist, _ = _closest_point_distance(fit.evaluate, pt)
            in_sample_max = max(in_sample_max, dist)

        # Only *interior* indices are excluded: leaving out an endpoint turns
        # the measurement into a pure extrapolation-beyond-the-fit-domain
        # question (every family's closest-point search is bounded to its
        # own u in [0, 1], so an excluded endpoint's distance is dominated by
        # inter-vertebra spacing, not by which family fit the curve -- see
        # docs/spinal-curve-model.md's "Breaking circularity" section).
        if len(centroids) >= 3:
            for i in range(1, len(centroids) - 1):
                others = centroids[:i] + centroids[i + 1 :]
                loo_fit = fit_builder(others)
                pt = np.array(centroids[i].centroid_mm, dtype=np.float64)
                dist, _ = _closest_point_distance(loo_fit.evaluate, pt)
                loo_max = max(loo_max, dist)

    return {"in_sample": {"max_mm": in_sample_max}, "leave_one_out": {"max_mm": loo_max}}


def _measure_separation(fit_builder: Callable) -> Dict[str, Any]:
    centroids = _clean_centroids(_SEPARATION_LEVELS, _SEPARATION_SPACING, _SEPARATION_CURVE_AMPLITUDE_MM)
    target_idx = len(centroids) // 2

    in_sample_points = []
    loo_points = []
    for magnitude in _SEPARATION_MAGNITUDES_MM:
        displaced = _displace_centroid(centroids[target_idx], magnitude)
        scenario = list(centroids)
        scenario[target_idx] = displaced

        fit = fit_builder(scenario)
        offsets = []
        for c in scenario:
            pt = np.array(c.centroid_mm, dtype=np.float64)
            dist, _ = _closest_point_distance(fit.evaluate, pt)
            offsets.append(dist)
        displaced_offset = offsets[target_idx]
        clean_max = max(d for i, d in enumerate(offsets) if i != target_idx)
        in_sample_points.append(
            {
                "displacement_mm": magnitude,
                "clean_max_mm": clean_max,
                "displaced_offset_mm": displaced_offset,
                "margin_mm": displaced_offset - clean_max,
            }
        )

        others = centroids[:target_idx] + centroids[target_idx + 1 :]
        loo_fit = fit_builder(others)
        clean_offsets = []
        for c in others:
            pt = np.array(c.centroid_mm, dtype=np.float64)
            dist, _ = _closest_point_distance(loo_fit.evaluate, pt)
            clean_offsets.append(dist)
        clean_max_loo = max(clean_offsets)
        pt_disp = np.array(displaced.centroid_mm, dtype=np.float64)
        disp_offset_loo, _ = _closest_point_distance(loo_fit.evaluate, pt_disp)
        loo_points.append(
            {
                "displacement_mm": magnitude,
                "clean_max_mm": clean_max_loo,
                "displaced_offset_mm": disp_offset_loo,
                "margin_mm": disp_offset_loo - clean_max_loo,
            }
        )

    return {
        "in_sample": in_sample_points,
        "leave_one_out": loo_points,
        # Scalar, dotted-path-addressable summaries alongside the per-magnitude
        # lists AC13 pins as lists (so the decision document can cite an exact
        # number the measurements table backs -- see AC5/AC6).
        "smallest_margin_mm": {
            "in_sample": min(p["margin_mm"] for p in in_sample_points),
            "leave_one_out": min(p["margin_mm"] for p in loo_points),
        },
    }


def _measure_degenerate_inputs(fit_builder: Callable) -> Dict[str, Any]:
    two_level_centroids = _clean_centroids(_TWO_LEVEL_LEVELS, (1.0, 1.0, 1.0), _SWEEP_CURVE_AMPLITUDE_MM)
    full_centroids = _clean_centroids(_TRUNCATED_FOV_FULL_LEVELS, (1.0, 1.0, 1.0), _SWEEP_CURVE_AMPLITUDE_MM)
    truncated_centroids = full_centroids[:_TRUNCATED_FOV_KEEP]

    result = {}
    for key, centroids in (("two_level", two_level_centroids), ("truncated_fov", truncated_centroids)):
        raised = False
        degenerate = True
        try:
            fit = fit_builder(centroids)
            degenerate = _is_degenerate(fit.evaluate, centroids, NON_DEGENERACY_ARC_LENGTH_FACTOR)
        except Exception:
            raised = True
        result[key] = {"raised": raised, "degenerate": degenerate}
    return result


def _measure_determinism(fit_builder: Callable) -> Dict[str, Any]:
    centroids = _clean_centroids(_TRUNCATED_FOV_FULL_LEVELS, (1.0, 1.0, 1.0), _SWEEP_CURVE_AMPLITUDE_MM)
    fit_a = fit_builder(centroids)
    fit_b = fit_builder(centroids)
    u = np.linspace(0.0, 1.0, _DETERMINISM_N_SAMPLES)
    pts_a = np.asarray(fit_a.evaluate(u))
    pts_b = np.asarray(fit_b.evaluate(u))
    identical = bool(np.array_equal(pts_a, pts_b))
    return {"identical": identical, "compared_samples": _DETERMINISM_N_SAMPLES}


# =========================================================================== #
# VerSe cohort discovery + scoliotic-case ranking (AC18-AC20)
# =========================================================================== #


def _resolve_cohort_root(verse_cohort_arg: Optional[str]) -> Optional[Path]:
    import os

    if verse_cohort_arg:
        return Path(verse_cohort_arg)
    env_value = os.environ.get(VERSE_COHORT_ENV)
    if env_value:
        return Path(env_value)
    return None


def _discover_verse_masks(root: Optional[Path]) -> Tuple[List[Path], Optional[str]]:
    if root is None:
        return [], "no VerSe cohort resolved (neither --verse-cohort nor SEGFACET_VERSE_COHORT was set)"
    if not root.is_dir():
        return [], f"resolved cohort root does not exist: {root}"
    masks = sorted(root.rglob(f"*{VERSE_SEG_SUFFIX}"))
    if not masks:
        return [], f"cohort root contains no {VERSE_SEG_SUFFIX!r} masks: {root}"
    return masks, None


def _case_stem(mask_path: Path) -> str:
    name = mask_path.name
    if name.endswith(VERSE_SEG_SUFFIX):
        return name[: -len(VERSE_SEG_SUFFIX)]
    return mask_path.stem


def _load_verse_case_centroids(mask_path: Path) -> Optional[List]:
    import nibabel as nib

    from segfacet.features.centroids import compute_centroid
    from segfacet.io import load_volume

    volume = load_volume(mask_path, integer_labels=True)
    present = sorted(int(v) for v in np.unique(volume.data) if v != 0)
    if len(present) < 2:
        return None
    img = nib.Nifti1Image(np.asarray(volume.data).astype(np.int32), volume.affine)
    return [compute_centroid(img, label) for label in present]


def _coronal_deviation_mm(centroids: Sequence) -> float:
    """Max perpendicular distance, in the coronal (x=LR, z=SI) plane, of any
    centroid from the line joining the most cranial and most caudal
    centroid."""
    points = np.array([(c.centroid_mm[0], c.centroid_mm[2]) for c in centroids], dtype=np.float64)
    cranial = points[np.argmax(points[:, 1])]
    caudal = points[np.argmin(points[:, 1])]
    line_vec = caudal - cranial
    norm = float(np.linalg.norm(line_vec))
    if norm == 0.0:
        return 0.0
    max_dev = 0.0
    for p in points:
        rel = p - cranial
        cross = line_vec[0] * rel[1] - line_vec[1] * rel[0]
        max_dev = max(max_dev, abs(float(cross)) / norm)
    return max_dev


def _measure_verse_scoliotic(
    fit_builder: Callable,
    case_centroids: Dict[str, List],
    discovery_reason: Optional[str],
) -> Dict[str, Any]:
    if discovery_reason is not None:
        return {"status": "skipped", "reason": discovery_reason}

    deviations = []
    for case_id, centroids in case_centroids.items():
        deviations.append({"case": case_id, "coronal_deviation_mm": _coronal_deviation_mm(centroids)})
    if not deviations:
        return {"status": "skipped", "reason": "no case yielded >= 2 recognised labels"}

    ranked = sorted(deviations, key=lambda r: r["coronal_deviation_mm"], reverse=True)
    selection_rule = (
        f"cases with coronal_deviation_mm >= {SCOLIOSIS_THRESHOLD_MM} mm "
        "(SCOLIOSIS_THRESHOLD_MM, the maximum perpendicular distance in the "
        "coronal plane of any centroid from the line joining the most "
        "cranial and most caudal centroid)"
    )
    selected = [r["case"] for r in ranked if r["coronal_deviation_mm"] >= SCOLIOSIS_THRESHOLD_MM]

    result: Dict[str, Any] = {
        "status": "measured",
        "ranked": ranked,
        "selection_rule": selection_rule,
        "selected": selected,
    }
    if not selected:
        result["finding"] = (
            "no case in the reachable cohort reached the "
            f"{SCOLIOSIS_THRESHOLD_MM} mm coronal-deviation threshold"
        )
        return result

    in_sample_max = 0.0
    loo_max = 0.0
    for case_id in selected:
        centroids = case_centroids[case_id]

        fit = fit_builder(centroids)
        for c in centroids:
            pt = np.array(c.centroid_mm, dtype=np.float64)
            dist, _ = _closest_point_distance(fit.evaluate, pt)
            in_sample_max = max(in_sample_max, dist)

        # Leave-one-out, mirroring the clean-GT sweep and separation passes:
        # fit through every OTHER present level, then measure the excluded
        # one -- the genuinely non-circular reading for a real scoliotic
        # case, since the in-sample fit was built to pass through the very
        # point being judged.
        for i in range(1, len(centroids) - 1):
            others = centroids[:i] + centroids[i + 1 :]
            loo_fit = fit_builder(others)
            pt = np.array(centroids[i].centroid_mm, dtype=np.float64)
            dist, _ = _closest_point_distance(loo_fit.evaluate, pt)
            loo_max = max(loo_max, dist)

    result["max_pass_through_mm"] = {"in_sample": in_sample_max, "leave_one_out": loo_max}
    return result


# =========================================================================== #
# Orchestration
# =========================================================================== #


def run_comparison(
    out_dir: "Path | str",
    *,
    verse_cohort: Optional[str] = None,
    max_verse_cases: Optional[int] = None,
) -> Dict[str, Any]:
    """Run every measurement pass and return the summary dict (also written
    to ``<out_dir>/curve_candidates.json``). Never raises for an
    absent/empty VerSe cohort -- that path is always a structured skip."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    grid_cases = _sweep_grid_cases()
    sweep = {
        "level_counts": list(SWEEP_LEVEL_COUNTS),
        "spacings": [list(s) for s in SWEEP_SPACINGS],
    }

    cohort_root = _resolve_cohort_root(verse_cohort)
    verse_masks, discovery_reason = _discover_verse_masks(cohort_root)
    if max_verse_cases is not None:
        verse_masks = verse_masks[: max_verse_cases]

    verse_case_stems = [_case_stem(p) for p in verse_masks]
    case_centroids: Dict[str, List] = {}
    for mask_path in verse_masks:
        stem = _case_stem(mask_path)
        try:
            centroids = _load_verse_case_centroids(mask_path)
        except Exception:
            centroids = None
        if centroids is not None:
            case_centroids[stem] = centroids

    candidates: Dict[str, Any] = {}
    for candidate_id in CANDIDATE_IDS:
        fit_builder = _CANDIDATE_BUILDERS.get(candidate_id)
        if fit_builder is None:
            candidates[candidate_id] = {
                "status": "excluded",
                "reason": _EXCLUSION_REASONS[candidate_id],
            }
            continue

        candidates[candidate_id] = {
            "status": "evaluated",
            "clean_pass_through": _measure_clean_pass_through(fit_builder, grid_cases),
            "separation": _measure_separation(fit_builder),
            "verse_scoliotic": _measure_verse_scoliotic(fit_builder, case_centroids, discovery_reason),
            "degenerate_inputs": _measure_degenerate_inputs(fit_builder),
            "determinism": _measure_determinism(fit_builder),
        }

    record = {
        "sweep": sweep,
        "candidates": candidates,
        "provenance": {
            "item": 118,
            "verse_cohort": str(cohort_root) if cohort_root is not None else None,
            "verse_cases": verse_case_stems,
            "verse_cases_with_ge2_labels": sorted(case_centroids.keys()),
            "verse_discovery_reason": discovery_reason,
        },
    }

    artifact_path = out_path / "curve_candidates.json"
    artifact_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compare_curve_candidates",
        description=(
            "Fit five candidate spinal-curve formulations through synthetic "
            "and (optionally) real VerSe19 GT centroid sequences, and score "
            "them on the five item-118 judgement criteria."
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory; curve_candidates.json is written here.",
    )
    parser.add_argument(
        "--verse-cohort",
        default=None,
        metavar="<dir>",
        help=(
            "Directory of a real (or stand-in) VerSe19-shaped cohort. When "
            "omitted, falls back to the SEGFACET_VERSE_COHORT environment "
            "variable, then to a genuine 'not found' skip."
        ),
    )
    parser.add_argument(
        "--max-verse-cases",
        type=int,
        default=None,
        metavar="<N>",
        help="Cap the number of discovered VerSe masks processed (default: no cap).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    record = run_comparison(
        args.out,
        verse_cohort=args.verse_cohort,
        max_verse_cases=args.max_verse_cases,
    )

    artifact_path = Path(args.out) / "curve_candidates.json"
    statuses = ", ".join(f"{cid}={entry['status']}" for cid, entry in record["candidates"].items())
    print(f"compare_curve_candidates: {statuses} -> summary written to {artifact_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
