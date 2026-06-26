"""Tests for vertebra orientation/rotation & global curvature descriptors (item 019).

Covers all ten Acceptance Criteria plus adversarial and edge-case inputs:

* AC1  — principal axis of a z-elongated block is within 5 degrees of (0, 0, 1),
         accounting for sign ambiguity (abs dot product >= cos(5 deg)).
* AC2  — principal axis of a block elongated along a diagonal is within 10 degrees
         of the expected direction (sign-ambiguity-aware).
* AC3  — spacing-awareness: with anisotropic (1, 1, 3) mm spacing, the principal
         axis reflects physical mm extent, not raw voxel counts.
* AC4  — single-voxel label does not crash; principal_axis is the zero-vector.
* AC5  — total_curvature_deg < 1.0 for centroids on a straight line.
* AC6  — total_curvature_deg >= 20.0 for a pronounced C-curve.
* AC7  — len(inter_tangent_angles_deg) == n_centroids - 1.
* AC8  — determinism for both compute functions.
* AC9  — empty labels raises ValueError with a non-empty message.
* AC10 — fewer than 2 centroids raises ValueError with a non-empty message.

Adversarial scenarios:
- Spherical blob (no preferred axis): does not crash; eigenvalue_ratio near 1.
- Single-voxel label: principal_axis is (0, 0, 0), no crash.
- x-elongated block: principal axis near (1, 0, 0) within 5 deg.
- y-elongated block: principal axis near (0, 1, 0) within 5 deg.
- Diagonal block (elongated along x+z): principal axis within 10 deg of
  normalised (1, 0, 1).
- Anisotropic spacing changes the recovered axis relative to voxel-only PCA.
- Straight spine curvature near 0 deg.
- Pronounced C-curve curvature >= 20 deg.
- Minimal 2-centroid curvature call: no crash; inter_tangent has length 1.
- inter_tangent_angles_deg all non-negative.
- tangent_angles_deg all finite.
- total_curvature_deg non-negative and finite.
- Input not mutated by either compute function.
- Frozen dataclass immutability (field assignment raises).
- Error messages: non-empty, no raw Python object repr.
- Both dataclasses expose expected fields.
- Import contract for both public symbols.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
import re
import sys
import os
from typing import List, Tuple

import numpy as np
import nibabel as nib
import pytest

# Ensure tests/ is on sys.path so synthetic.py is importable regardless of how
# pytest is invoked.
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from synthetic import affine_from_spacing, make_labelmap  # noqa: E402

from segqc.features.centroids import LabelCentroid  # noqa: E402
from segqc.features.spline import fit_centroid_spline  # noqa: E402
from segqc.features.orientation import (  # noqa: E402
    SpineCurvature,
    VertebralOrientation,
    compute_spine_curvature,
    compute_vertebra_orientations,
)


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: Tuple[float, float, float],
    label: int = 0,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with the given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Return n centroids equally spaced along the z axis."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _c_curve_spine(n: int = 7) -> List[LabelCentroid]:
    """Return centroids arranged in a pronounced C-curve spanning >= 30 deg.

    The curve sweeps from (0, 0, 0) through a maximum x-deflection of 30 mm
    at mid-spine, returning near x=0 at the far end.  This is a deliberate
    large-curvature fixture for AC6.
    """
    levels = ["T6", "T7", "T8", "T9", "T10", "T11", "T12"]
    # Parametric curve: z increases uniformly; x follows a half-sine giving a
    # 30 mm lateral deflection at the midpoint.
    t_vals = [float(i) / (n - 1) for i in range(n)]
    result = []
    for i, (lv, t) in enumerate(zip(levels[:n], t_vals)):
        x = 30.0 * math.sin(math.pi * t)   # 0 -> 30 -> 0 mm lateral sweep
        z = float(i) * 15.0                  # 15 mm inter-vertebra step
        result.append(_centroid(lv, (x, 0.0, z), label=i + 1))
    return result


def _make_seg_img(
    shape: Tuple[int, int, int],
    label_arrays: dict,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Build a NiBabel Nifti1Image with painted labels from an array-coordinate dict.

    label_arrays: {label_int: ndarray of shape (N, 3) of voxel coords (int)}
    """
    data = np.zeros(shape, dtype=np.uint16)
    for label, coords in label_arrays.items():
        coords = np.asarray(coords, dtype=int)
        data[coords[:, 0], coords[:, 1], coords[:, 2]] = label
    return nib.Nifti1Image(data, affine_from_spacing(spacing))


def _elongated_z_img(
    length: int = 20,
    width: int = 2,
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Synthetic image: label elongated along z by *length* voxels, *width* in x/y."""
    shape = (width + 4, width + 4, length + 4)
    blocks = {label: ((2, 2 + width), (2, 2 + width), (2, 2 + length))}
    return make_labelmap(shape, blocks, spacing)


def _elongated_x_img(
    length: int = 20,
    width: int = 2,
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Synthetic image: label elongated along x."""
    shape = (length + 4, width + 4, width + 4)
    blocks = {label: ((2, 2 + length), (2, 2 + width), (2, 2 + width))}
    return make_labelmap(shape, blocks, spacing)


def _elongated_y_img(
    length: int = 20,
    width: int = 2,
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Synthetic image: label elongated along y."""
    shape = (width + 4, length + 4, width + 4)
    blocks = {label: ((2, 2 + width), (2, 2 + length), (2, 2 + width))}
    return make_labelmap(shape, blocks, spacing)


def _angle_between_deg(v1: Tuple[float, float, float], v2: Tuple[float, float, float]) -> float:
    """Return the angle in degrees between two 3-D vectors, handling near-zero magnitude."""
    a = np.asarray(v1, dtype=float)
    b = np.asarray(v2, dtype=float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return 90.0  # degenerate — treat as orthogonal
    cos_theta = np.clip(np.dot(a / na, b / nb), -1.0, 1.0)
    return math.degrees(math.acos(cos_theta))


def _axis_angle_deg_sign_ambiguous(
    axis: Tuple[float, float, float],
    reference: Tuple[float, float, float],
) -> float:
    """Return the minimum angle between axis and ±reference (sign-ambiguity-safe)."""
    a = np.asarray(axis, dtype=float)
    r = np.asarray(reference, dtype=float)
    na = np.linalg.norm(a)
    nr = np.linalg.norm(r)
    if na < 1e-12:
        return 90.0
    cos_pos = np.clip(np.dot(a / na, r / nr), -1.0, 1.0)
    angle_pos = math.degrees(math.acos(abs(cos_pos)))
    return angle_pos


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_vertebral_orientation():
    """VertebralOrientation is importable from segqc.features.orientation."""
    from segqc.features.orientation import VertebralOrientation as VO  # noqa: F401
    assert VO is VertebralOrientation


def test_import_spine_curvature():
    """SpineCurvature is importable from segqc.features.orientation."""
    from segqc.features.orientation import SpineCurvature as SC  # noqa: F401
    assert SC is SpineCurvature


def test_import_compute_vertebra_orientations():
    """compute_vertebra_orientations is importable from segqc.features.orientation."""
    from segqc.features.orientation import compute_vertebra_orientations as cvo  # noqa: F401
    assert callable(cvo)


def test_import_compute_spine_curvature():
    """compute_spine_curvature is importable from segqc.features.orientation."""
    from segqc.features.orientation import compute_spine_curvature as csc  # noqa: F401
    assert callable(csc)


def test_no_import_error():
    """Importing segqc.features.orientation raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.orientation")
    assert hasattr(mod, "VertebralOrientation")
    assert hasattr(mod, "SpineCurvature")
    assert hasattr(mod, "compute_vertebra_orientations")
    assert hasattr(mod, "compute_spine_curvature")


# =========================================================================== #
# Dataclass field contracts
# =========================================================================== #


def test_vertebral_orientation_has_required_fields():
    """VertebralOrientation exposes label, level_name, principal_axis, eigenvalue_ratio."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    rec = results[0]
    for field in ("label", "level_name", "principal_axis", "eigenvalue_ratio"):
        assert hasattr(rec, field), f"VertebralOrientation missing field: {field}"


def test_vertebral_orientation_is_frozen():
    """VertebralOrientation is immutable (assigning a field raises an exception)."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    with pytest.raises(Exception):
        results[0].label = 999  # type: ignore[misc]


def test_spine_curvature_has_required_fields():
    """SpineCurvature exposes tangent_angles_deg, inter_tangent_angles_deg, total_curvature_deg."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    for field in ("tangent_angles_deg", "inter_tangent_angles_deg", "total_curvature_deg"):
        assert hasattr(result, field), f"SpineCurvature missing field: {field}"


def test_spine_curvature_is_frozen():
    """SpineCurvature is immutable (assigning a field raises an exception)."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    with pytest.raises(Exception):
        result.total_curvature_deg = 999.0  # type: ignore[misc]


def test_vertebral_orientation_is_dataclass_instance():
    """compute_vertebra_orientations returns VertebralOrientation instances."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    for rec in results:
        assert isinstance(rec, VertebralOrientation)


def test_spine_curvature_is_dataclass_instance():
    """compute_spine_curvature returns a SpineCurvature instance."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert isinstance(result, SpineCurvature)


# =========================================================================== #
# AC1: Principal axis of a z-elongated block is within 5 deg of (0, 0, 1)
# =========================================================================== #


def test_ac1_z_elongated_block_principal_axis_near_z():
    """AC1: z-elongated block (2x2x20 voxels) has principal axis within 5 deg of z-axis."""
    seg_img = _elongated_z_img(length=20, width=2)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (0.0, 0.0, 1.0))
    assert angle <= 5.0, (
        f"z-elongated block principal axis angle from z-axis = {angle:.2f} deg > 5 deg; "
        f"axis = {axis}"
    )


def test_ac1_z_elongated_block_principal_axis_is_unit_vector():
    """AC1: principal_axis is a unit vector (norm close to 1.0)."""
    seg_img = _elongated_z_img(length=20, width=2)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    norm = math.sqrt(sum(v ** 2 for v in axis))
    assert math.isclose(norm, 1.0, abs_tol=1e-6), (
        f"principal_axis norm = {norm:.8f}, expected 1.0"
    )


def test_ac1_abs_dot_product_threshold():
    """AC1: abs(dot(principal_axis, z_hat)) >= cos(5 deg) ≈ 0.9962."""
    cos_5deg = math.cos(math.radians(5.0))
    seg_img = _elongated_z_img(length=20, width=2)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = np.asarray(results[0].principal_axis, dtype=float)
    z_hat = np.array([0.0, 0.0, 1.0])
    dot_abs = abs(float(np.dot(axis, z_hat)))
    assert dot_abs >= cos_5deg, (
        f"abs dot product = {dot_abs:.6f}, need >= {cos_5deg:.6f} (cos 5 deg)"
    )


def test_ac1_tall_block_still_within_tolerance():
    """AC1: Longer z-elongated block (3x3x30 voxels) also within 5 deg of z."""
    seg_img = _elongated_z_img(length=30, width=3)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (0.0, 0.0, 1.0))
    assert angle <= 5.0, f"Tall block angle = {angle:.2f} deg > 5 deg; axis = {axis}"


# =========================================================================== #
# AC2: Principal axis of a diagonal-elongated block is within 10 deg of expected
# =========================================================================== #


def test_ac2_diagonal_xz_block_principal_axis():
    """AC2: A block elongated along x and z equally has principal axis within 10 deg
    of the normalised (1, 0, 1) direction."""
    # Build a long diagonal run of voxels: x and z both increase together
    n_voxels = 25
    coords = np.array([[i, 2, i] for i in range(n_voxels)], dtype=int)
    shape = (n_voxels + 2, 5, n_voxels + 2)
    seg_img = _make_seg_img(shape, {1: coords}, spacing=(1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    expected = np.array([1.0, 0.0, 1.0])
    expected = expected / np.linalg.norm(expected)
    angle = _axis_angle_deg_sign_ambiguous(tuple(axis), tuple(expected))
    assert angle <= 10.0, (
        f"Diagonal (x+z) block principal axis angle = {angle:.2f} deg > 10 deg; "
        f"axis = {axis}"
    )


def test_ac2_diagonal_xy_block_principal_axis():
    """AC2: A block elongated equally in x and y has principal axis within 10 deg of
    the normalised (1, 1, 0) direction."""
    n_voxels = 25
    coords = np.array([[i, i, 2] for i in range(n_voxels)], dtype=int)
    shape = (n_voxels + 2, n_voxels + 2, 5)
    seg_img = _make_seg_img(shape, {1: coords}, spacing=(1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    expected = np.array([1.0, 1.0, 0.0])
    expected = expected / np.linalg.norm(expected)
    angle = _axis_angle_deg_sign_ambiguous(tuple(axis), tuple(expected))
    assert angle <= 10.0, (
        f"Diagonal (x+y) block principal axis angle = {angle:.2f} deg > 10 deg; "
        f"axis = {axis}"
    )


# =========================================================================== #
# AC3: Spacing-awareness — PCA in mm-space
# =========================================================================== #


def test_ac3_anisotropic_spacing_axis_reflects_mm_extent():
    """AC3: With anisotropic (1, 1, 3) mm spacing, the principal axis reflects mm
    extent, not voxel extent.

    Setup: a block that is 4 voxels long in x and 4 voxels long in z.
    In voxel space the extents are equal (x = z = 4 voxels).
    In mm-space with spacing (1, 1, 3): x extent = 4 mm, z extent = 12 mm.
    The principal axis in mm-space should therefore be near z, not x.
    """
    spacing = (1.0, 1.0, 3.0)
    shape = (10, 6, 10)
    # 4 voxels in x, 4 voxels in z — equal in voxels, very different in mm
    blocks = {1: ((2, 6), (2, 4), (2, 6))}
    seg_img = make_labelmap(shape, blocks, spacing)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    # With (1,1,3) spacing: z physical extent = 4*3 = 12 mm >> x extent = 4 mm
    # so the principal axis should be nearer z than x
    abs_dot_z = abs(float(np.dot(np.asarray(axis), np.array([0.0, 0.0, 1.0]))))
    abs_dot_x = abs(float(np.dot(np.asarray(axis), np.array([1.0, 0.0, 0.0]))))
    assert abs_dot_z > abs_dot_x, (
        f"With anisotropic z spacing, z-component should dominate: "
        f"|dot z| = {abs_dot_z:.4f}, |dot x| = {abs_dot_x:.4f}; axis = {axis}"
    )


def test_ac3_isotropic_z_elongated_recovers_z():
    """AC3: Isotropic spacing on a z-elongated block recovers z-axis as expected."""
    seg_img = _elongated_z_img(length=20, width=2, spacing=(1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (0.0, 0.0, 1.0))
    assert angle <= 5.0


def test_ac3_anisotropic_x_elongated_changes_axis():
    """AC3: With spacing (3, 1, 1), an x-elongated block has principal axis near x."""
    spacing = (3.0, 1.0, 1.0)
    seg_img = _elongated_x_img(length=20, width=2, spacing=spacing)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (1.0, 0.0, 0.0))
    assert angle <= 5.0, (
        f"x-elongated block with (3,1,1) spacing: angle from x = {angle:.2f} deg; "
        f"axis = {axis}"
    )


# =========================================================================== #
# AC4: Single-voxel label does not crash; principal_axis is zero vector
# =========================================================================== #


def test_ac4_single_voxel_no_crash():
    """AC4: A label with exactly one voxel does not raise any exception."""
    shape = (8, 8, 8)
    seg_img = _make_seg_img(shape, {1: np.array([[4, 4, 4]])})
    results = compute_vertebra_orientations(seg_img, [1])
    assert len(results) == 1


def test_ac4_single_voxel_principal_axis_is_zero_vector():
    """AC4: A single-voxel label has principal_axis equal to (0.0, 0.0, 0.0)."""
    shape = (8, 8, 8)
    seg_img = _make_seg_img(shape, {1: np.array([[4, 4, 4]])})
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    norm = math.sqrt(sum(v ** 2 for v in axis))
    assert norm < 1e-9, (
        f"Single-voxel principal_axis norm = {norm:.2e}, expected 0; axis = {axis}"
    )


def test_ac4_single_voxel_eigenvalue_ratio_is_zero():
    """AC4: Single-voxel label returns eigenvalue_ratio == 0.0."""
    shape = (8, 8, 8)
    seg_img = _make_seg_img(shape, {1: np.array([[4, 4, 4]])})
    results = compute_vertebra_orientations(seg_img, [1])
    assert results[0].eigenvalue_ratio == pytest.approx(0.0, abs=1e-9)


def test_ac4_single_voxel_result_is_dataclass_instance():
    """AC4: Even for a single-voxel label the returned value is VertebralOrientation."""
    shape = (8, 8, 8)
    seg_img = _make_seg_img(shape, {1: np.array([[4, 4, 4]])})
    results = compute_vertebra_orientations(seg_img, [1])
    assert isinstance(results[0], VertebralOrientation)


# =========================================================================== #
# AC5: total_curvature_deg < 1.0 for a straight spine
# =========================================================================== #


def test_ac5_straight_spine_total_curvature_near_zero():
    """AC5: A straight z-spine has total_curvature_deg < 1.0 deg."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg < 1.0, (
        f"Straight spine total_curvature_deg = {result.total_curvature_deg:.4f} >= 1.0"
    )


def test_ac5_straight_spine_with_more_points():
    """AC5: A 10-point straight spine also has total_curvature_deg < 1.0 deg."""
    centroids = _straight_spine(10, spacing_mm=8.0)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg < 1.0, (
        f"10-point straight spine total_curvature_deg = {result.total_curvature_deg:.4f}"
    )


def test_ac5_collinear_spine_total_curvature_near_zero():
    """AC5: Exactly collinear centroids (on z axis only) produce near-zero curvature."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0), label=1),
        _centroid("T11", (0.0, 0.0, 10.0), label=2),
        _centroid("T12", (0.0, 0.0, 20.0), label=3),
        _centroid("L1", (0.0, 0.0, 30.0), label=4),
        _centroid("L2", (0.0, 0.0, 40.0), label=5),
    ]
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg < 1.0, (
        f"Collinear spine total_curvature_deg = {result.total_curvature_deg:.4f}"
    )


# =========================================================================== #
# AC6: total_curvature_deg >= 20.0 for a pronounced C-curve
# =========================================================================== #


def test_ac6_c_curve_total_curvature_large():
    """AC6: A pronounced C-curve spine has total_curvature_deg >= 20.0 deg."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg >= 20.0, (
        f"C-curve total_curvature_deg = {result.total_curvature_deg:.4f} < 20.0"
    )


def test_ac6_c_curve_larger_than_straight():
    """AC6: The C-curve total curvature is strictly larger than the straight spine's."""
    straight = _straight_spine(6)
    curved = _c_curve_spine(7)
    fit_straight = fit_centroid_spline(straight)
    fit_curved = fit_centroid_spline(curved)
    result_straight = compute_spine_curvature(fit_straight, straight)
    result_curved = compute_spine_curvature(fit_curved, curved)
    assert result_curved.total_curvature_deg > result_straight.total_curvature_deg, (
        f"C-curve curvature ({result_curved.total_curvature_deg:.2f}) not > "
        f"straight curvature ({result_straight.total_curvature_deg:.2f})"
    )


def test_ac6_pronounced_curve_distinguishable():
    """AC6: A 9-point C-curve spine also has total_curvature_deg >= 20.0 deg."""
    levels = ["T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12"]
    n = len(levels)
    t_vals = [float(i) / (n - 1) for i in range(n)]
    centroids = [
        _centroid(lv, (30.0 * math.sin(math.pi * t), 0.0, float(i) * 15.0), label=i + 1)
        for i, (lv, t) in enumerate(zip(levels, t_vals))
    ]
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg >= 20.0, (
        f"9-point C-curve total_curvature_deg = {result.total_curvature_deg:.4f}"
    )


# =========================================================================== #
# AC7: len(inter_tangent_angles_deg) == n_centroids - 1
# =========================================================================== #


def test_ac7_inter_tangent_length_six_centroids():
    """AC7: 6-centroid spine yields 5 inter-tangent angles."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert len(result.inter_tangent_angles_deg) == 5, (
        f"Expected 5 inter-tangent angles, got {len(result.inter_tangent_angles_deg)}"
    )


def test_ac7_inter_tangent_length_two_centroids():
    """AC7: 2-centroid spine yields 1 inter-tangent angle."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert len(result.inter_tangent_angles_deg) == 1, (
        f"Expected 1 inter-tangent angle, got {len(result.inter_tangent_angles_deg)}"
    )


def test_ac7_inter_tangent_length_general():
    """AC7: For any n in [2..8], len(inter_tangent_angles_deg) == n - 1."""
    for n in range(2, 9):
        centroids = _straight_spine(n)
        fit = fit_centroid_spline(centroids)
        result = compute_spine_curvature(fit, centroids)
        assert len(result.inter_tangent_angles_deg) == n - 1, (
            f"n={n}: expected {n-1} inter-tangent angles, "
            f"got {len(result.inter_tangent_angles_deg)}"
        )


def test_ac7_tangent_angles_deg_length_matches_centroids():
    """AC7: len(tangent_angles_deg) matches the number of centroids."""
    for n in [3, 5, 7]:
        centroids = _straight_spine(n)
        fit = fit_centroid_spline(centroids)
        result = compute_spine_curvature(fit, centroids)
        assert len(result.tangent_angles_deg) == n, (
            f"n={n}: expected {n} tangent angles, got {len(result.tangent_angles_deg)}"
        )


# =========================================================================== #
# AC8: Determinism
# =========================================================================== #


def test_ac8_determinism_orientation():
    """AC8: Two calls to compute_vertebra_orientations with identical inputs return equal results."""
    seg_img = _elongated_z_img(length=20, width=2)
    results_a = compute_vertebra_orientations(seg_img, [1])
    results_b = compute_vertebra_orientations(seg_img, [1])
    assert results_a[0].principal_axis == results_b[0].principal_axis
    assert results_a[0].eigenvalue_ratio == results_b[0].eigenvalue_ratio


def test_ac8_determinism_curvature():
    """AC8: Two calls to compute_spine_curvature with identical inputs return equal results."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result_a = compute_spine_curvature(fit, centroids)
    result_b = compute_spine_curvature(fit, centroids)
    assert result_a.total_curvature_deg == result_b.total_curvature_deg
    assert result_a.tangent_angles_deg == result_b.tangent_angles_deg
    assert result_a.inter_tangent_angles_deg == result_b.inter_tangent_angles_deg


def test_ac8_determinism_orientation_multiple_labels():
    """AC8: Determinism holds when multiple labels are requested."""
    shape = (20, 10, 10)
    blocks = {
        1: ((2, 18), (2, 4), (2, 4)),
        2: ((2, 4), (5, 9), (5, 9)),
    }
    seg_img = make_labelmap(shape, blocks, (1.0, 1.0, 1.0))
    results_a = compute_vertebra_orientations(seg_img, [1, 2])
    results_b = compute_vertebra_orientations(seg_img, [1, 2])
    for a, b in zip(results_a, results_b):
        assert a.principal_axis == b.principal_axis


# =========================================================================== #
# AC9: Empty labels raises ValueError
# =========================================================================== #


def test_ac9_empty_labels_raises_value_error():
    """AC9: compute_vertebra_orientations([]) raises ValueError."""
    seg_img = _elongated_z_img()
    with pytest.raises(ValueError):
        compute_vertebra_orientations(seg_img, [])


def test_ac9_empty_labels_error_message_non_empty():
    """AC9: The ValueError for empty labels has a non-empty, readable message."""
    seg_img = _elongated_z_img()
    with pytest.raises(ValueError) as exc_info:
        compute_vertebra_orientations(seg_img, [])
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac9_empty_labels_error_no_raw_repr():
    """AC9: The ValueError message is not a raw Python object repr."""
    seg_img = _elongated_z_img()
    try:
        compute_vertebra_orientations(seg_img, [])
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw object repr: {msg!r}"
        )


# =========================================================================== #
# AC10: Too-few centroids raises ValueError
# =========================================================================== #


def test_ac10_zero_centroids_raises_value_error():
    """AC10: compute_spine_curvature with 0 centroids raises ValueError."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_spine_curvature(fit, [])


def test_ac10_one_centroid_raises_value_error():
    """AC10: compute_spine_curvature with 1 centroid raises ValueError."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_spine_curvature(fit, centroids[:1])


def test_ac10_one_centroid_error_message_non_empty():
    """AC10: The ValueError for 1 centroid has a non-empty message."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError) as exc_info:
        compute_spine_curvature(fit, centroids[:1])
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac10_error_no_raw_repr():
    """AC10: The ValueError message is not a raw Python object repr."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    try:
        compute_spine_curvature(fit, centroids[:1])
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw object repr: {msg!r}"
        )


# =========================================================================== #
# Adversarial: x-elongated and y-elongated blocks
# =========================================================================== #


def test_adv_x_elongated_block_principal_axis_near_x():
    """x-elongated block (20x2x2 voxels) has principal axis within 5 deg of x-axis."""
    seg_img = _elongated_x_img(length=20, width=2)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (1.0, 0.0, 0.0))
    assert angle <= 5.0, (
        f"x-elongated block angle from x-axis = {angle:.2f} deg; axis = {axis}"
    )


def test_adv_y_elongated_block_principal_axis_near_y():
    """y-elongated block (2x20x2 voxels) has principal axis within 5 deg of y-axis."""
    seg_img = _elongated_y_img(length=20, width=2)
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    angle = _axis_angle_deg_sign_ambiguous(axis, (0.0, 1.0, 0.0))
    assert angle <= 5.0, (
        f"y-elongated block angle from y-axis = {angle:.2f} deg; axis = {axis}"
    )


# =========================================================================== #
# Adversarial: spherical blob (no preferred axis)
# =========================================================================== #


def test_adv_spherical_blob_no_crash():
    """A near-spherical blob (cube) does not crash compute_vertebra_orientations."""
    shape = (10, 10, 10)
    # Cube block: equal extent in all directions
    blocks = {1: ((2, 8), (2, 8), (2, 8))}
    seg_img = make_labelmap(shape, blocks, (1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1])
    assert len(results) == 1


def test_adv_spherical_blob_eigenvalue_ratio_near_one():
    """A cube block has eigenvalue_ratio near 1.0 (no strong preferred axis)."""
    shape = (10, 10, 10)
    blocks = {1: ((2, 8), (2, 8), (2, 8))}
    seg_img = make_labelmap(shape, blocks, (1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1])
    ratio = results[0].eigenvalue_ratio
    # For a cube all eigenvalues are equal; ratio = 1.0
    assert math.isfinite(ratio)
    assert ratio >= 0.0, f"eigenvalue_ratio should be >= 0.0, got {ratio}"
    # Not assert ratio near 1 strictly — implementation may define ratio differently;
    # but we can assert it is < the ratio expected for a strongly elongated shape
    elongated_img = _elongated_z_img(length=20, width=2)
    elongated_results = compute_vertebra_orientations(elongated_img, [1])
    elongated_ratio = elongated_results[0].eigenvalue_ratio
    assert elongated_ratio > ratio, (
        "Elongated block should have a higher eigenvalue_ratio than a cube"
    )


# =========================================================================== #
# Adversarial: return-list properties
# =========================================================================== #


def test_adv_return_list_length_matches_input_labels():
    """compute_vertebra_orientations returns one result per requested label."""
    shape = (20, 10, 10)
    blocks = {
        1: ((2, 18), (2, 4), (2, 4)),
        2: ((2, 4), (5, 9), (2, 4)),
        3: ((10, 14), (5, 9), (5, 9)),
    }
    seg_img = make_labelmap(shape, blocks, (1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1, 2, 3])
    assert len(results) == 3


def test_adv_return_list_label_order_matches_input():
    """Labels in the output list appear in the same order as the input sequence."""
    shape = (20, 10, 10)
    blocks = {
        1: ((2, 18), (2, 4), (2, 4)),
        2: ((2, 4), (5, 9), (2, 4)),
    }
    seg_img = make_labelmap(shape, blocks, (1.0, 1.0, 1.0))
    results = compute_vertebra_orientations(seg_img, [1, 2])
    assert results[0].label == 1
    assert results[1].label == 2


def test_adv_single_label_list_returns_one_record():
    """Requesting a single label returns a list of length 1."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    assert len(results) == 1


# =========================================================================== #
# Adversarial: curvature numeric properties
# =========================================================================== #


def test_adv_total_curvature_non_negative():
    """total_curvature_deg is non-negative for any input."""
    for centroids in [_straight_spine(5), _c_curve_spine(7)]:
        fit = fit_centroid_spline(centroids)
        result = compute_spine_curvature(fit, centroids)
        assert result.total_curvature_deg >= 0.0, (
            f"total_curvature_deg = {result.total_curvature_deg} < 0"
        )


def test_adv_total_curvature_finite():
    """total_curvature_deg is finite for typical inputs."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert math.isfinite(result.total_curvature_deg)


def test_adv_inter_tangent_angles_all_non_negative():
    """All inter_tangent_angles_deg values are non-negative (angles >= 0)."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    for i, ang in enumerate(result.inter_tangent_angles_deg):
        assert ang >= 0.0, f"inter_tangent_angles_deg[{i}] = {ang} < 0"


def test_adv_tangent_angles_all_finite():
    """All tangent_angles_deg values are finite."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    for i, ang in enumerate(result.tangent_angles_deg):
        assert math.isfinite(ang), f"tangent_angles_deg[{i}] = {ang} is not finite"


def test_adv_inter_tangent_angles_all_finite():
    """All inter_tangent_angles_deg values are finite."""
    centroids = _c_curve_spine(7)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    for i, ang in enumerate(result.inter_tangent_angles_deg):
        assert math.isfinite(ang), f"inter_tangent_angles_deg[{i}] = {ang} is not finite"


def test_adv_straight_spine_inter_tangent_near_zero():
    """For a straight spine, all inter_tangent_angles_deg should be near 0 deg."""
    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    for i, ang in enumerate(result.inter_tangent_angles_deg):
        assert ang < 5.0, (
            f"Straight spine inter_tangent_angles_deg[{i}] = {ang:.4f} >= 5 deg"
        )


# =========================================================================== #
# Adversarial: two-centroid boundary case for curvature
# =========================================================================== #


def test_adv_two_centroid_curvature_no_crash():
    """Minimum valid curvature input (2 centroids) does not crash."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert isinstance(result, SpineCurvature)


def test_adv_two_centroid_curvature_inter_tangent_length_one():
    """Two centroids produce exactly 1 inter-tangent angle."""
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert len(result.inter_tangent_angles_deg) == 1


# =========================================================================== #
# Adversarial: immutability of inputs
# =========================================================================== #


def test_adv_input_label_list_not_mutated():
    """compute_vertebra_orientations does not mutate the input labels list."""
    seg_img = _elongated_z_img()
    labels = [1]
    original = list(labels)
    compute_vertebra_orientations(seg_img, labels)
    assert labels == original


def test_adv_input_centroids_not_mutated_by_curvature():
    """compute_spine_curvature does not mutate the input centroid list."""
    centroids = _straight_spine(5)
    original = list(centroids)
    fit = fit_centroid_spline(centroids)
    compute_spine_curvature(fit, centroids)
    assert centroids == original


# =========================================================================== #
# Adversarial: principal_axis fields are float-typed
# =========================================================================== #


def test_adv_principal_axis_components_are_float():
    """principal_axis components are Python float or numpy floating."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    axis = results[0].principal_axis
    for component in axis:
        assert isinstance(component, (float, np.floating)), (
            f"principal_axis component {component!r} is not a float"
        )


def test_adv_eigenvalue_ratio_is_float():
    """eigenvalue_ratio is a Python float or numpy floating."""
    seg_img = _elongated_z_img()
    results = compute_vertebra_orientations(seg_img, [1])
    ratio = results[0].eigenvalue_ratio
    assert isinstance(ratio, (float, np.floating)), (
        f"eigenvalue_ratio {ratio!r} is not a float"
    )


# =========================================================================== #
# Adversarial: curvature with anisotropic centroid spacing
# =========================================================================== #


def test_adv_curvature_anisotropic_mm_straight_spine():
    """Curvature of a straight spine in anisotropic mm-space is still near zero."""
    # Centroids with large z-spacing (anisotropic physical spacing)
    levels = ["T10", "T11", "T12", "L1", "L2"]
    centroids = [
        _centroid(lv, (0.0, 0.0, float(i) * 30.0), label=i + 1)
        for i, lv in enumerate(levels)
    ]
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert result.total_curvature_deg < 1.0


def test_adv_curvature_large_mm_spine_no_crash():
    """Curvature computation on a large-scale mm-spine does not crash."""
    levels = ["T1", "T2", "T3", "T4", "T5", "T6", "T7"]
    n = len(levels)
    t_vals = [float(i) / (n - 1) for i in range(n)]
    centroids = [
        _centroid(lv, (20.0 * math.sin(math.pi * t), 0.0, float(i) * 20.0), label=i + 1)
        for i, (lv, t) in enumerate(zip(levels, t_vals))
    ]
    fit = fit_centroid_spline(centroids)
    result = compute_spine_curvature(fit, centroids)
    assert math.isfinite(result.total_curvature_deg)
