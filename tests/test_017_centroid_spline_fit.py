"""Tests for centroid spline fit (item 017).

Covers all six Acceptance Criteria plus adversarial and edge-case inputs:

* AC1 — spline evaluates within 0.5 mm of each input centroid on GT-like fixtures.
* AC2 — robustness when one level is deliberately removed (no crash; valid SplineFit).
* AC3 — degree clamped for short sequences (2 points → linear, 3 points → at
  most quadratic); no exception raised.
* AC4 — determinism: repeated fits with identical inputs return identical tck/u.
* AC5 — degenerate inputs (0 or 1 centroid) raise ValueError with a non-empty,
  human-readable message; collinear points are accepted without error.
* AC6 — evaluate_spline returns an (N, 3) float array; no NaN or Inf for
  well-conditioned inputs.

Adversarial scenarios:
- Zero centroids → ValueError.
- Single centroid → ValueError.
- Exactly 2 centroids → degree clamped to 1 (linear), valid fit.
- Exactly 3 centroids → degree clamped to 2 (quadratic), valid fit.
- Collinear centroids (all on a line) → valid fit, no crash.
- Missing level (one centroid removed from a 5-point sequence).
- Highly anisotropic spacing (mm coords differ greatly between axes).
- Input list not mutated by fit_centroid_spline.
- Evaluate at u=0, u=1, and intermediate u values.
- evaluate_spline at many u values → no NaN, no Inf.
- Error message quality (no raw SciPy repr / traceback string in ValueError).
- Import contract for SplineFit, fit_centroid_spline, evaluate_spline.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
import re
from typing import List

import numpy as np
import pytest

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, evaluate_spline, fit_centroid_spline


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: tuple[float, float, float],
    label: int = 0,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Return n centroids equally spaced along the z axis (a straight spine)."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm))
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    """Return 6 centroids along a gentle curve in the xz-plane (realistic shape)."""
    # z increases with each level, x shifts slightly (mild scoliosis-like curve)
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [_centroid(lv, (x, 0.0, z)) for lv, x, z in zip(levels, xs, zs)]


def _dist3(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((bi - ai) ** 2 for ai, bi in zip(a, b)))


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_spline_fit():
    """SplineFit is importable from segqc.features.spline."""
    from segqc.features.spline import SplineFit as SF  # noqa: F401
    assert SF is SplineFit


def test_import_fit_centroid_spline():
    """fit_centroid_spline is importable from segqc.features.spline."""
    from segqc.features.spline import fit_centroid_spline as fcs  # noqa: F401
    assert callable(fcs)


def test_import_evaluate_spline():
    """evaluate_spline is importable from segqc.features.spline."""
    from segqc.features.spline import evaluate_spline as es  # noqa: F401
    assert callable(es)


def test_no_import_error():
    """Importing segqc.features.spline raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.spline")
    assert hasattr(mod, "SplineFit")
    assert hasattr(mod, "fit_centroid_spline")
    assert hasattr(mod, "evaluate_spline")


# =========================================================================== #
# SplineFit dataclass contract
# =========================================================================== #


def test_spline_fit_is_frozen_dataclass():
    """SplineFit is immutable (assigning a field raises FrozenInstanceError)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(Exception):
        fit.n_points = 0  # type: ignore[misc]


def test_spline_fit_has_required_fields():
    """SplineFit exposes tck, u, degree, and n_points."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    for attr in ("tck", "u", "degree", "n_points"):
        assert hasattr(fit, attr), f"SplineFit missing field: {attr}"


def test_spline_fit_n_points_matches_input():
    """SplineFit.n_points equals the number of centroids supplied."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    assert fit.n_points == 6


def test_spline_fit_u_length_matches_n_points():
    """SplineFit.u has the same length as the number of input centroids."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    assert len(fit.u) == 5


def test_spline_fit_u_starts_at_zero():
    """SplineFit.u[0] is 0.0 (start of the parametric domain)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    assert float(fit.u[0]) == pytest.approx(0.0)


def test_spline_fit_u_ends_at_one():
    """SplineFit.u[-1] is 1.0 (end of the parametric domain)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    assert float(fit.u[-1]) == pytest.approx(1.0)


def test_spline_fit_u_monotonically_increasing():
    """SplineFit.u is strictly monotonically increasing."""
    centroids = _straight_spine(7)
    fit = fit_centroid_spline(centroids)
    u_vals = [float(v) for v in fit.u]
    for i in range(1, len(u_vals)):
        assert u_vals[i] > u_vals[i - 1], (
            f"u is not monotonically increasing at index {i}: {u_vals}"
        )


def test_spline_fit_returns_spline_fit_instance():
    """fit_centroid_spline returns a SplineFit instance."""
    centroids = _straight_spine(5)
    result = fit_centroid_spline(centroids)
    assert isinstance(result, SplineFit)


# =========================================================================== #
# AC1: Spline passes within tolerance of input centroids on GT fixtures
# =========================================================================== #


def test_ac1_straight_spine_spline_passes_through_centroids():
    """AC1: Evaluating the spline at its u values returns points within 0.5 mm
    of the original centroid_mm coordinates (straight spine)."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5, (
            f"Centroid {i} ({c.level_name}) is {dist:.4f} mm from the spline "
            f"(tolerance 0.5 mm)"
        )


def test_ac1_curved_spine_spline_passes_through_centroids():
    """AC1: Evaluating the spline at its u values returns points within 0.5 mm
    of the original centroid_mm coordinates (curved spine)."""
    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5, (
            f"Centroid {i} ({c.level_name}) is {dist:.4f} mm from the spline "
            f"(tolerance 0.5 mm)"
        )


def test_ac1_anisotropic_mm_coords_within_tolerance():
    """AC1: Anisotropic mm spacing (z much larger than x/y) still fits within 0.5 mm."""
    # Simulate anisotropic physical spacing: z-step = 30 mm, x/y small
    levels = ["T10", "T11", "T12", "L1", "L2"]
    centroids = [
        _centroid(levels[i], (float(i) * 0.5, float(i) * 0.5, float(i) * 30.0))
        for i in range(5)
    ]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5, (
            f"Anisotropic centroid {i} is {dist:.4f} mm from the spline"
        )


def test_ac1_seven_point_spine_all_within_tolerance():
    """AC1: A 7-point spine fits within 0.5 mm at all input parameter values."""
    centroids = _straight_spine(7, spacing_mm=12.0)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5


# =========================================================================== #
# AC2: Robustness when one level is deliberately removed
# =========================================================================== #


def test_ac2_missing_level_does_not_raise():
    """AC2: Removing one centroid from a 6-point sequence does not raise."""
    full = _straight_spine(6)
    # Remove the 3rd centroid (index 2) — simulate a missing level
    missing_one = full[:2] + full[3:]
    fit = fit_centroid_spline(missing_one)
    assert isinstance(fit, SplineFit)


def test_ac2_missing_level_spline_is_evaluable():
    """AC2: A spline fitted with one level missing can be evaluated at arbitrary u."""
    full = _straight_spine(6)
    missing_one = full[:2] + full[3:]
    fit = fit_centroid_spline(missing_one)
    u_test = [0.0, 0.25, 0.5, 0.75, 1.0]
    pts = evaluate_spline(fit, u_test)
    assert pts.shape == (5, 3)


def test_ac2_missing_first_level_no_crash():
    """AC2: Removing the first centroid does not crash."""
    full = _straight_spine(6)
    without_first = full[1:]
    fit = fit_centroid_spline(without_first)
    assert isinstance(fit, SplineFit)


def test_ac2_missing_last_level_no_crash():
    """AC2: Removing the last centroid does not crash."""
    full = _straight_spine(6)
    without_last = full[:-1]
    fit = fit_centroid_spline(without_last)
    assert isinstance(fit, SplineFit)


def test_ac2_missing_level_remaining_centroids_within_tolerance():
    """AC2: After removing one level the spline still passes within 0.5 mm of
    the remaining input centroids."""
    full = _straight_spine(6)
    # Remove the middle centroid
    missing_one = full[:2] + full[3:]
    fit = fit_centroid_spline(missing_one)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(missing_one):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5, (
            f"After missing-level removal, centroid {i} is {dist:.4f} mm "
            f"from the spline (tolerance 0.5 mm)"
        )


def test_ac2_missing_level_curved_spine_no_crash():
    """AC2: Removing one level from a curved spine does not crash."""
    curved = _curved_spine()
    # Remove the 2nd centroid
    missing_one = curved[:1] + curved[2:]
    fit = fit_centroid_spline(missing_one)
    assert isinstance(fit, SplineFit)


# =========================================================================== #
# AC3: Degree is clamped for short sequences
# =========================================================================== #


def test_ac3_two_points_degree_clamped_to_linear():
    """AC3: With 2 centroids the effective degree is 1 (linear), not 3."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids, degree=3)
    assert fit.degree == 1


def test_ac3_two_points_no_exception():
    """AC3: Fitting on exactly 2 centroids raises no exception."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)


def test_ac3_three_points_degree_clamped_to_at_most_quadratic():
    """AC3: With 3 centroids the effective degree is at most 2, not 3."""
    centroids = _straight_spine(3)
    fit = fit_centroid_spline(centroids, degree=3)
    assert fit.degree <= 2


def test_ac3_three_points_no_exception():
    """AC3: Fitting on exactly 3 centroids raises no exception."""
    centroids = _straight_spine(3)
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)


def test_ac3_four_points_degree_clamped_to_at_most_three():
    """AC3: With 4 centroids the effective degree is at most 3."""
    centroids = _straight_spine(4)
    fit = fit_centroid_spline(centroids, degree=3)
    assert fit.degree <= 3


def test_ac3_two_points_spline_is_evaluable():
    """AC3: A spline from 2 centroids can be evaluated at u in [0, 1]."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert pts.shape == (3, 3)


def test_ac3_three_points_spline_passes_through_inputs():
    """AC3: A 3-point spline still passes within 0.5 mm of each input centroid."""
    centroids = _straight_spine(3)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5


def test_ac3_custom_degree_respected_when_enough_points():
    """AC3: Supplying degree=2 with >=3 points uses degree 2 (no clamping needed)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids, degree=2)
    assert fit.degree == 2


# =========================================================================== #
# AC4: Determinism
# =========================================================================== #


def test_ac4_determinism_straight_spine():
    """AC4: Two fits on the same straight spine return identical u values."""
    centroids = _straight_spine(6)
    fit1 = fit_centroid_spline(centroids)
    fit2 = fit_centroid_spline(centroids)
    assert list(fit1.u) == list(fit2.u)


def test_ac4_determinism_curved_spine():
    """AC4: Two fits on the same curved spine return identical tck knot vectors."""
    centroids = _curved_spine()
    fit1 = fit_centroid_spline(centroids)
    fit2 = fit_centroid_spline(centroids)
    np.testing.assert_array_equal(fit1.tck[0], fit2.tck[0])


def test_ac4_determinism_evaluate_spline():
    """AC4: Evaluating the same SplineFit twice at the same u values returns
    identical arrays."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    u_vals = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    pts1 = evaluate_spline(fit, u_vals)
    pts2 = evaluate_spline(fit, u_vals)
    np.testing.assert_array_equal(pts1, pts2)


def test_ac4_determinism_n_points():
    """AC4: SplineFit.n_points is identical across two calls."""
    centroids = _straight_spine(5)
    fit1 = fit_centroid_spline(centroids)
    fit2 = fit_centroid_spline(centroids)
    assert fit1.n_points == fit2.n_points


def test_ac4_determinism_degree():
    """AC4: SplineFit.degree is identical across two calls."""
    centroids = _straight_spine(5)
    fit1 = fit_centroid_spline(centroids)
    fit2 = fit_centroid_spline(centroids)
    assert fit1.degree == fit2.degree


def test_ac4_determinism_missing_level():
    """AC4: Missing-level variant is also deterministic."""
    full = _straight_spine(6)
    missing = full[:2] + full[3:]
    fit1 = fit_centroid_spline(missing)
    fit2 = fit_centroid_spline(missing)
    assert list(fit1.u) == list(fit2.u)


# =========================================================================== #
# AC5: Graceful handling of degenerate inputs
# =========================================================================== #


def test_ac5_zero_centroids_raises_value_error():
    """AC5: Zero centroids raises ValueError."""
    with pytest.raises(ValueError):
        fit_centroid_spline([])


def test_ac5_zero_centroids_error_message_non_empty():
    """AC5: The ValueError for zero centroids has a non-empty message."""
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline([])
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac5_one_centroid_raises_value_error():
    """AC5: A single centroid raises ValueError."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    with pytest.raises(ValueError):
        fit_centroid_spline(centroids)


def test_ac5_one_centroid_error_message_non_empty():
    """AC5: The ValueError for one centroid has a non-empty message."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids)
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac5_error_message_no_raw_object_repr():
    """AC5: The ValueError message does not look like a raw Python object repr."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    try:
        fit_centroid_spline(centroids)
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw object repr: {msg!r}"
        )


def test_ac5_error_message_no_scipy_traceback_string():
    """AC5: The ValueError message does not leak raw SciPy internal names."""
    centroids = []
    try:
        fit_centroid_spline(centroids)
    except ValueError as exc:
        msg = str(exc).lower()
        # Must not be a raw traceback dump — check for obviously bad patterns
        assert "traceback" not in msg, (
            "Error message contains 'traceback' — may be leaking internal SciPy error"
        )


def test_ac5_collinear_points_no_crash():
    """AC5: Collinear centroids (all on the z axis) are accepted without error."""
    levels = ["T8", "T9", "T10", "T11", "T12"]
    centroids = [_centroid(lv, (0.0, 0.0, float(i) * 10.0)) for i, lv in enumerate(levels)]
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)


def test_ac5_collinear_with_identical_x_y_no_crash():
    """AC5: Centroids with x=0, y=0 and varying z only are collinear; no crash."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
        _centroid("L4", (0.0, 0.0, 30.0)),
    ]
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)


def test_ac5_collinear_spline_evaluable():
    """AC5: A spline through collinear points can be evaluated at arbitrary u."""
    centroids = [_centroid("T" + str(8 + i), (0.0, 0.0, float(i) * 10.0)) for i in range(5)]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert pts.shape == (3, 3)


# =========================================================================== #
# AC6: evaluate_spline returns (N, 3) float array; no NaN or Inf
# =========================================================================== #


def test_ac6_output_shape_single_u():
    """AC6: evaluate_spline with one u value returns shape (1, 3)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.5])
    assert pts.shape == (1, 3)


def test_ac6_output_shape_multiple_u():
    """AC6: evaluate_spline with N u values returns shape (N, 3)."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    u_vals = [0.0, 0.25, 0.5, 0.75, 1.0]
    pts = evaluate_spline(fit, u_vals)
    assert pts.shape == (5, 3)


def test_ac6_output_dtype_is_float():
    """AC6: evaluate_spline output array has a float dtype."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert np.issubdtype(pts.dtype, np.floating)


def test_ac6_no_nan_values():
    """AC6: evaluate_spline returns no NaN for a well-conditioned input."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    u_vals = list(np.linspace(0.0, 1.0, 50))
    pts = evaluate_spline(fit, u_vals)
    assert not np.any(np.isnan(pts)), "evaluate_spline returned NaN values"


def test_ac6_no_inf_values():
    """AC6: evaluate_spline returns no Inf for a well-conditioned input."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    u_vals = list(np.linspace(0.0, 1.0, 50))
    pts = evaluate_spline(fit, u_vals)
    assert not np.any(np.isinf(pts)), "evaluate_spline returned Inf values"


def test_ac6_evaluate_at_u_zero():
    """AC6: evaluate_spline at u=0 returns a finite 3-D point."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0])
    assert pts.shape == (1, 3)
    assert np.all(np.isfinite(pts))


def test_ac6_evaluate_at_u_one():
    """AC6: evaluate_spline at u=1 returns a finite 3-D point."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [1.0])
    assert pts.shape == (1, 3)
    assert np.all(np.isfinite(pts))


def test_ac6_evaluate_at_all_input_u_values():
    """AC6: evaluate_spline at SplineFit.u returns an (n_points, 3) array."""
    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    assert pts.shape == (fit.n_points, 3)
    assert np.all(np.isfinite(pts))


def test_ac6_evaluate_100_u_values_no_nan():
    """AC6: Evaluating at 100 linearly-spaced u values produces no NaN."""
    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids)
    u_vals = list(np.linspace(0.0, 1.0, 100))
    pts = evaluate_spline(fit, u_vals)
    assert pts.shape == (100, 3)
    assert not np.any(np.isnan(pts))


# =========================================================================== #
# Adversarial: immutability of input list
# =========================================================================== #


def test_adv_input_list_not_mutated():
    """fit_centroid_spline does not mutate the input centroid list."""
    centroids = _straight_spine(5)
    original = list(centroids)
    fit_centroid_spline(centroids)
    assert centroids == original


def test_adv_input_list_not_mutated_curved():
    """fit_centroid_spline does not mutate a curved-spine centroid list."""
    centroids = _curved_spine()
    original = list(centroids)
    fit_centroid_spline(centroids)
    assert centroids == original


# =========================================================================== #
# Adversarial: boundary n_points values (n=4 and n=5)
# =========================================================================== #


def test_adv_four_points_valid_fit():
    """Four centroids produce a valid SplineFit with no exception."""
    centroids = _straight_spine(4)
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)
    assert fit.n_points == 4


def test_adv_five_points_valid_fit():
    """Five centroids produce a valid SplineFit with no exception."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)
    assert fit.n_points == 5


def test_adv_five_points_cubic_degree():
    """Five centroids with degree=3 use degree 3 (not clamped)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids, degree=3)
    assert fit.degree == 3


# =========================================================================== #
# Adversarial: spline endpoint proximity for straight spine
# =========================================================================== #


def test_adv_straight_spine_start_near_first_centroid():
    """Evaluating a straight spine at u=0 gives a point near the first centroid."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0])
    dist = _dist3(
        (pts[0, 0], pts[0, 1], pts[0, 2]),
        centroids[0].centroid_mm,
    )
    assert dist < 0.5, f"Spline start is {dist:.4f} mm from first centroid"


def test_adv_straight_spine_end_near_last_centroid():
    """Evaluating a straight spine at u=1 gives a point near the last centroid."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [1.0])
    dist = _dist3(
        (pts[0, 0], pts[0, 1], pts[0, 2]),
        centroids[-1].centroid_mm,
    )
    assert dist < 0.5, f"Spline end is {dist:.4f} mm from last centroid"


# =========================================================================== #
# Adversarial: large mm coordinates (physical volumes)
# =========================================================================== #


def test_adv_large_mm_coordinates_no_crash():
    """Centroids with large mm values (realistic whole-spine physical extent) fit without crash."""
    # Realistic whole-spine: ~400 mm total, 25 vertebrae, ~16 mm apart
    levels = [
        "C1", "C2", "C3", "C4", "C5", "C6", "C7",
        "T1", "T2", "T3", "T4", "T5", "T6", "T7",
    ]
    centroids = [
        _centroid(lv, (1.5 * i, 0.0, 16.0 * i))
        for i, lv in enumerate(levels)
    ]
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)
    assert fit.n_points == len(levels)


def test_adv_large_mm_coordinates_within_tolerance():
    """Large-coordinate spine: spline still passes within 0.5 mm of input centroids."""
    levels = ["T1", "T2", "T3", "T4", "T5"]
    centroids = [
        _centroid(lv, (2.0 * i, 0.5 * i, 20.0 * i))
        for i, lv in enumerate(levels)
    ]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5


# =========================================================================== #
# Adversarial: highly anisotropic mm spacing
# =========================================================================== #


def test_adv_highly_anisotropic_spacing_no_crash():
    """Highly anisotropic spacing (z-spacing 10x larger than x/y) does not crash."""
    # z spacing = 30 mm, x/y spacing = 1 mm
    levels = ["L1", "L2", "L3", "L4", "L5"]
    centroids = [
        _centroid(lv, (float(i), float(i), float(i) * 30.0))
        for i, lv in enumerate(levels)
    ]
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)


def test_adv_highly_anisotropic_spacing_within_tolerance():
    """Highly anisotropic spacing: spline still within 0.5 mm of each input centroid."""
    levels = ["T10", "T11", "T12", "L1", "L2"]
    centroids = [
        _centroid(lv, (0.1 * i, 0.0, 30.0 * i))
        for i, lv in enumerate(levels)
    ]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        dist = _dist3(
            (pts[i, 0], pts[i, 1], pts[i, 2]),
            c.centroid_mm,
        )
        assert dist < 0.5
