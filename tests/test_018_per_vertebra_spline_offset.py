"""Tests for per-vertebra spline offset (item 018).

Covers all eight Acceptance Criteria plus adversarial and edge-case inputs:

* AC1 — near-zero offsets (< 1.0 mm) for centroids lying on the fitted spline.
* AC2 — large offset (>= 8.0 mm) for a synthetically displaced centroid; the
  other centroids' offsets remain small (< 2.0 mm).
* AC3 — anisotropic spacing applied correctly: offset_voxel != offset_mm when
  spacing is non-isotropic; for a purely z-axis displacement with spacing
  (1, 1, sz), offset_voxel ≈ offset_mm / sz.
* AC4 — signed components are consistent with the Euclidean distance:
  sqrt(dx_mm² + dy_mm² + dz_mm²) ≈ offset_mm within 0.1 mm.
* AC5 — determinism: two identical calls return equal lists.
* AC6 — return type and structure: non-empty list of VertebralSplineOffset
  frozen dataclasses with the required fields.
* AC7 — closest_u in [0, 1] for every record.
* AC8 — empty centroids raises ValueError with a non-empty message.

Adversarial scenarios:
- GT centroids that were used to fit the spline → near-zero offset.
- Single displaced centroid in an otherwise smooth sequence → only that
  centroid has a large offset.
- Z-axis-only displacement with anisotropic z spacing → offset_voxel ≈
  offset_mm / sz.
- Isotropic 1 mm spacing → offset_voxel == offset_mm.
- Empty centroid list → ValueError.
- Output list length matches input length.
- Output order matches input order (label sequence preserved).
- Frozen dataclass immutability (field assignment raises).
- Input list not mutated by compute_spline_offsets.
- Two-centroid spline (minimum valid spline) → no crash, offsets finite.
- All offset_mm values are non-negative.
- closest_u boundary values: first centroid near u=0, last near u=1.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np
import pytest

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, fit_centroid_spline
from segqc.features.spline_offset import VertebralSplineOffset, compute_spline_offsets


# =========================================================================== #
# Helpers (mirror the style from test_017_centroid_spline_fit.py)
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
    """Return n centroids equally spaced along the z axis (straight spine)."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    """Return 6 centroids along a gentle curve in the xz-plane."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [
        _centroid(lv, (x, 0.0, z), label=i + 1)
        for i, (lv, x, z) in enumerate(zip(levels, xs, zs))
    ]


def _fit(centroids: List[LabelCentroid], degree: int = 3) -> SplineFit:
    return fit_centroid_spline(centroids, degree=degree)


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_vertebral_spline_offset():
    """VertebralSplineOffset is importable from segqc.features.spline_offset."""
    from segqc.features.spline_offset import VertebralSplineOffset as VSO  # noqa: F401
    assert VSO is VertebralSplineOffset


def test_import_compute_spline_offsets():
    """compute_spline_offsets is importable from segqc.features.spline_offset."""
    from segqc.features.spline_offset import compute_spline_offsets as cso  # noqa: F401
    assert callable(cso)


def test_no_import_error():
    """Importing segqc.features.spline_offset raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.spline_offset")
    assert hasattr(mod, "VertebralSplineOffset")
    assert hasattr(mod, "compute_spline_offsets")


# =========================================================================== #
# VertebralSplineOffset dataclass contract
# =========================================================================== #


def test_vertebral_spline_offset_has_required_fields():
    """VertebralSplineOffset exposes the required eight fields."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    rec = offsets[0]
    for attr in ("label", "level_name", "closest_u", "offset_mm", "offset_voxel",
                 "dx_mm", "dy_mm", "dz_mm"):
        assert hasattr(rec, attr), f"VertebralSplineOffset missing field: {attr}"


def test_vertebral_spline_offset_is_frozen():
    """VertebralSplineOffset is immutable (assigning a field raises an exception)."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    with pytest.raises(Exception):
        offsets[0].offset_mm = 999.0  # type: ignore[misc]


def test_vertebral_spline_offset_is_dataclass_instance():
    """compute_spline_offsets returns VertebralSplineOffset instances."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert isinstance(rec, VertebralSplineOffset)


# =========================================================================== #
# AC1: Near-zero offsets for GT centroids lying on the spline
# =========================================================================== #


def test_ac1_straight_spine_offsets_near_zero():
    """AC1: Centroids used to fit the spline have offset_mm < 1.0 mm (straight)."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert rec.offset_mm < 1.0, (
            f"Level {rec.level_name}: offset_mm={rec.offset_mm:.4f} >= 1.0 mm"
        )


def test_ac1_curved_spine_offsets_near_zero():
    """AC1: GT curved-spine centroids all have offset_mm < 1.0 mm."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert rec.offset_mm < 1.0, (
            f"Level {rec.level_name}: offset_mm={rec.offset_mm:.4f} >= 1.0 mm"
        )


def test_ac1_seven_point_spine_offsets_near_zero():
    """AC1: A 7-point GT spine has all offset_mm < 1.0 mm."""
    centroids = _straight_spine(7, spacing_mm=12.0)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert rec.offset_mm < 1.0


def test_ac1_all_offsets_are_non_negative():
    """AC1: offset_mm is non-negative for every centroid."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert rec.offset_mm >= 0.0


# =========================================================================== #
# AC2: Large offset for a synthetically displaced centroid
# =========================================================================== #


def test_ac2_displaced_centroid_has_large_offset():
    """AC2: A centroid displaced 15 mm has offset_mm >= 8.0 mm."""
    centroids = _straight_spine(6)
    # Displace centroid at index 3 by 15 mm in the x direction
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = _fit(centroids)  # Fit on the original GT centroids
    offsets = compute_spline_offsets(perturbed, fit)

    assert offsets[3].offset_mm >= 8.0, (
        f"Displaced centroid offset_mm={offsets[3].offset_mm:.4f} < 8.0 mm"
    )


def test_ac2_undisplaced_centroids_remain_small():
    """AC2: Non-displaced centroids retain offset_mm < 2.0 mm after one displacement."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)

    for i, rec in enumerate(offsets):
        if i == 3:
            continue
        assert rec.offset_mm < 2.0, (
            f"Non-displaced centroid {rec.level_name} has offset_mm={rec.offset_mm:.4f}"
        )


def test_ac2_y_axis_displacement_detected():
    """AC2: A 12 mm y-axis displacement produces offset_mm >= 8.0 mm."""
    centroids = _straight_spine(5)
    displaced_mm = (
        centroids[2].centroid_mm[0],
        centroids[2].centroid_mm[1] + 12.0,
        centroids[2].centroid_mm[2],
    )
    displaced = _centroid(centroids[2].level_name, displaced_mm, label=centroids[2].label)
    perturbed = centroids[:2] + [displaced] + centroids[3:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)

    assert offsets[2].offset_mm >= 8.0


def test_ac2_displaced_first_centroid():
    """AC2: Displacing the first centroid by 15 mm produces a large offset."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[0].centroid_mm[0] + 15.0,
        centroids[0].centroid_mm[1],
        centroids[0].centroid_mm[2],
    )
    displaced = _centroid(centroids[0].level_name, displaced_mm, label=centroids[0].label)
    perturbed = [displaced] + centroids[1:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    assert offsets[0].offset_mm >= 8.0


def test_ac2_displaced_last_centroid():
    """AC2: Displacing the last centroid by 15 mm produces a large offset."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[-1].centroid_mm[0] + 15.0,
        centroids[-1].centroid_mm[1],
        centroids[-1].centroid_mm[2],
    )
    displaced = _centroid(centroids[-1].level_name, displaced_mm, label=centroids[-1].label)
    perturbed = centroids[:-1] + [displaced]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    assert offsets[-1].offset_mm >= 8.0


# =========================================================================== #
# AC3: Correct application of anisotropic spacing
# =========================================================================== #


def test_ac3_isotropic_offset_voxel_equals_offset_mm():
    """AC3: With isotropic 1 mm spacing, offset_voxel == offset_mm."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit, spacing_mm=(1.0, 1.0, 1.0))
    for rec in offsets:
        assert math.isclose(rec.offset_mm, rec.offset_voxel, rel_tol=1e-6, abs_tol=1e-9), (
            f"Isotropic: offset_mm={rec.offset_mm:.6f}, "
            f"offset_voxel={rec.offset_voxel:.6f}"
        )


def test_ac3_none_spacing_offset_voxel_equals_offset_mm():
    """AC3: When spacing_mm=None (default), offset_voxel == offset_mm (1 mm assumed)."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets_default = compute_spline_offsets(centroids, fit)
    offsets_explicit = compute_spline_offsets(centroids, fit, spacing_mm=(1.0, 1.0, 1.0))
    for d, e in zip(offsets_default, offsets_explicit):
        assert math.isclose(d.offset_voxel, e.offset_voxel, rel_tol=1e-6, abs_tol=1e-9)


def test_ac3_z_axis_displacement_anisotropic_spacing():
    """AC3: For a z-axis displacement with spacing (1,1,sz), offset_voxel ≈ offset_mm / sz."""
    sz = 3.0
    spacing_mm = (1.0, 1.0, sz)

    # Build a straight z-spine, then displace one centroid purely in z by 15 mm
    centroids = _straight_spine(6, spacing_mm=10.0)
    displaced_mm = (
        centroids[3].centroid_mm[0],
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2] + 15.0,
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit, spacing_mm=spacing_mm)

    # For a purely z-axis offset, offset_voxel ≈ offset_mm / sz
    rec = offsets[3]
    expected_voxel = rec.offset_mm / sz
    # Allow 30% relative tolerance — closest-point search adds small deviations
    # and the offset vector is not purely z for a parametric spline
    assert math.isclose(rec.offset_voxel, expected_voxel, rel_tol=0.30), (
        f"offset_voxel={rec.offset_voxel:.4f}, expected ~{expected_voxel:.4f} "
        f"(offset_mm / sz = {rec.offset_mm:.4f} / {sz})"
    )


def test_ac3_anisotropic_spacing_different_from_isotropic():
    """AC3: Under anisotropic spacing, offset_voxel != offset_mm for a displaced centroid."""
    sz = 5.0
    spacing_mm = (1.0, 1.0, sz)

    centroids = _straight_spine(5, spacing_mm=10.0)
    displaced_mm = (
        centroids[2].centroid_mm[0],
        centroids[2].centroid_mm[1],
        centroids[2].centroid_mm[2] + 20.0,
    )
    displaced = _centroid(centroids[2].level_name, displaced_mm, label=centroids[2].label)
    perturbed = centroids[:2] + [displaced] + centroids[3:]

    fit = _fit(centroids)
    offsets_aniso = compute_spline_offsets(perturbed, fit, spacing_mm=spacing_mm)
    offsets_iso = compute_spline_offsets(perturbed, fit, spacing_mm=(1.0, 1.0, 1.0))

    # Anisotropic offset_voxel should be smaller than isotropic (larger voxels in z)
    assert offsets_aniso[2].offset_voxel < offsets_iso[2].offset_voxel, (
        "Anisotropic offset_voxel should be < isotropic offset_voxel for z-displacement"
    )


# =========================================================================== #
# AC4: Signed components sum to Euclidean distance
# =========================================================================== #


def test_ac4_vector_components_consistent_straight_spine():
    """AC4: sqrt(dx² + dy² + dz²) ≈ offset_mm (within 0.1 mm) for GT centroids."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        reconstructed = math.sqrt(rec.dx_mm ** 2 + rec.dy_mm ** 2 + rec.dz_mm ** 2)
        assert math.isclose(reconstructed, rec.offset_mm, abs_tol=0.1), (
            f"Level {rec.level_name}: reconstructed={reconstructed:.6f}, "
            f"offset_mm={rec.offset_mm:.6f}"
        )


def test_ac4_vector_components_consistent_displaced():
    """AC4: sqrt(dx² + dy² + dz²) ≈ offset_mm (within 0.1 mm) for a displaced centroid."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    for rec in offsets:
        reconstructed = math.sqrt(rec.dx_mm ** 2 + rec.dy_mm ** 2 + rec.dz_mm ** 2)
        assert math.isclose(reconstructed, rec.offset_mm, abs_tol=0.1), (
            f"Level {rec.level_name}: reconstructed={reconstructed:.6f}, "
            f"offset_mm={rec.offset_mm:.6f}"
        )


def test_ac4_vector_components_consistent_curved_spine():
    """AC4: Component-distance consistency holds on a curved spine."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        reconstructed = math.sqrt(rec.dx_mm ** 2 + rec.dy_mm ** 2 + rec.dz_mm ** 2)
        assert math.isclose(reconstructed, rec.offset_mm, abs_tol=0.1)


def test_ac4_dx_dy_dz_are_floats():
    """AC4: dx_mm, dy_mm, dz_mm are Python float (or float-compatible)."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    rec = offsets[0]
    for field in (rec.dx_mm, rec.dy_mm, rec.dz_mm):
        assert isinstance(field, (float, np.floating))


# =========================================================================== #
# AC5: Determinism
# =========================================================================== #


def test_ac5_determinism_straight_spine():
    """AC5: Two calls on the same GT straight spine return equal offset_mm values."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets_a = compute_spline_offsets(centroids, fit)
    offsets_b = compute_spline_offsets(centroids, fit)
    for a, b in zip(offsets_a, offsets_b):
        assert a.offset_mm == b.offset_mm
        assert a.closest_u == b.closest_u


def test_ac5_determinism_curved_spine():
    """AC5: Two calls on the same curved spine are deterministic."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    offsets_a = compute_spline_offsets(centroids, fit)
    offsets_b = compute_spline_offsets(centroids, fit)
    for a, b in zip(offsets_a, offsets_b):
        assert a.offset_mm == b.offset_mm
        assert a.dx_mm == b.dx_mm
        assert a.dy_mm == b.dy_mm
        assert a.dz_mm == b.dz_mm


def test_ac5_determinism_displaced():
    """AC5: Determinism holds when one centroid is displaced."""
    centroids = _straight_spine(6)
    displaced_mm = (centroids[2].centroid_mm[0] + 12.0,
                    centroids[2].centroid_mm[1],
                    centroids[2].centroid_mm[2])
    displaced = _centroid(centroids[2].level_name, displaced_mm, label=centroids[2].label)
    perturbed = centroids[:2] + [displaced] + centroids[3:]
    fit = _fit(centroids)
    offsets_a = compute_spline_offsets(perturbed, fit)
    offsets_b = compute_spline_offsets(perturbed, fit)
    for a, b in zip(offsets_a, offsets_b):
        assert a.offset_mm == b.offset_mm


def test_ac5_determinism_with_spacing():
    """AC5: Determinism holds when spacing_mm is supplied."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    spacing = (1.0, 1.0, 3.0)
    offsets_a = compute_spline_offsets(centroids, fit, spacing_mm=spacing)
    offsets_b = compute_spline_offsets(centroids, fit, spacing_mm=spacing)
    for a, b in zip(offsets_a, offsets_b):
        assert a.offset_voxel == b.offset_voxel


# =========================================================================== #
# AC6: Return type and structure
# =========================================================================== #


def test_ac6_returns_list():
    """AC6: compute_spline_offsets returns a list."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    result = compute_spline_offsets(centroids, fit)
    assert isinstance(result, list)


def test_ac6_list_length_matches_input():
    """AC6: The returned list has the same length as the input centroids."""
    for n in (2, 3, 5, 7):
        centroids = _straight_spine(n)
        fit = _fit(centroids)
        offsets = compute_spline_offsets(centroids, fit)
        assert len(offsets) == n, f"n={n}: got {len(offsets)} offsets"


def test_ac6_order_matches_input():
    """AC6: Labels in the output list match the input centroid order."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for i, (c, rec) in enumerate(zip(centroids, offsets)):
        assert rec.label == c.label, (
            f"Position {i}: output label={rec.label}, input label={c.label}"
        )
        assert rec.level_name == c.level_name, (
            f"Position {i}: output level={rec.level_name}, input level={c.level_name}"
        )


def test_ac6_level_names_preserved():
    """AC6: level_name in each record matches the source LabelCentroid."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for c, rec in zip(centroids, offsets):
        assert rec.level_name == c.level_name


def test_ac6_all_fields_are_finite():
    """AC6: Every numeric field in VertebralSplineOffset is finite."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        for field_val in (rec.offset_mm, rec.offset_voxel, rec.closest_u,
                          rec.dx_mm, rec.dy_mm, rec.dz_mm):
            assert math.isfinite(float(field_val)), (
                f"Non-finite field in {rec}: {field_val}"
            )


# =========================================================================== #
# AC7: closest_u in [0, 1]
# =========================================================================== #


def test_ac7_closest_u_in_unit_interval_straight():
    """AC7: All closest_u values are in [0.0, 1.0] for a straight spine."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert 0.0 <= rec.closest_u <= 1.0, (
            f"Level {rec.level_name}: closest_u={rec.closest_u}"
        )


def test_ac7_closest_u_in_unit_interval_curved():
    """AC7: All closest_u values are in [0.0, 1.0] for a curved spine."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert 0.0 <= rec.closest_u <= 1.0


def test_ac7_closest_u_in_unit_interval_displaced():
    """AC7: closest_u remains in [0, 1] even for a heavily displaced centroid."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = _fit(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    for rec in offsets:
        assert 0.0 <= rec.closest_u <= 1.0


def test_ac7_first_centroid_closest_u_near_zero():
    """AC7: The first centroid's closest_u is near the start of the spline."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    # The first input centroid is at u=0; the closest point should be near 0
    assert offsets[0].closest_u < 0.3, (
        f"First centroid closest_u={offsets[0].closest_u:.4f} is unexpectedly large"
    )


def test_ac7_last_centroid_closest_u_near_one():
    """AC7: The last centroid's closest_u is near the end of the spline."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert offsets[-1].closest_u > 0.7, (
        f"Last centroid closest_u={offsets[-1].closest_u:.4f} is unexpectedly small"
    )


# =========================================================================== #
# AC8: Empty centroids raises ValueError
# =========================================================================== #


def test_ac8_empty_centroids_raises_value_error():
    """AC8: compute_spline_offsets([]) raises ValueError."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    with pytest.raises(ValueError):
        compute_spline_offsets([], fit)


def test_ac8_empty_centroids_error_message_non_empty():
    """AC8: The ValueError for empty centroids has a non-empty, readable message."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    with pytest.raises(ValueError) as exc_info:
        compute_spline_offsets([], fit)
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac8_error_message_no_raw_object_repr():
    """AC8: The ValueError message is not a raw Python object repr."""
    import re
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    try:
        compute_spline_offsets([], fit)
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw object repr: {msg!r}"
        )


# =========================================================================== #
# Adversarial: immutability of input list
# =========================================================================== #


def test_adv_input_list_not_mutated():
    """compute_spline_offsets does not mutate the input centroid list."""
    centroids = _straight_spine(5)
    original = list(centroids)
    fit = _fit(centroids)
    compute_spline_offsets(centroids, fit)
    assert centroids == original


def test_adv_spline_fit_not_mutated():
    """compute_spline_offsets does not alter the SplineFit object."""
    centroids = _straight_spine(5)
    fit = _fit(centroids)
    u_before = tuple(fit.u)
    n_before = fit.n_points
    compute_spline_offsets(centroids, fit)
    assert fit.u == u_before
    assert fit.n_points == n_before


# =========================================================================== #
# Adversarial: degenerate / boundary spline inputs
# =========================================================================== #


def test_adv_two_centroid_spline_no_crash():
    """Minimum valid spline (2 centroids) does not crash compute_spline_offsets."""
    centroids = _straight_spine(2)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert len(offsets) == 2


def test_adv_two_centroid_spline_offsets_finite():
    """Offsets from a 2-centroid spline are finite and non-negative."""
    centroids = _straight_spine(2)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    for rec in offsets:
        assert math.isfinite(rec.offset_mm)
        assert rec.offset_mm >= 0.0


def test_adv_three_centroid_spline_no_crash():
    """3-centroid spline (degree clamped to 2) does not crash."""
    centroids = _straight_spine(3)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert len(offsets) == 3


def test_adv_single_centroid_query_against_multipoint_spline():
    """A single centroid queried against a 6-point spline returns 1 record."""
    full = _straight_spine(6)
    fit = _fit(full)
    single = [full[2]]
    offsets = compute_spline_offsets(single, fit)
    assert len(offsets) == 1


def test_adv_collinear_centroids_no_crash():
    """Collinear centroids (spine lies on z axis) do not crash."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0), label=1),
        _centroid("T11", (0.0, 0.0, 10.0), label=2),
        _centroid("T12", (0.0, 0.0, 20.0), label=3),
        _centroid("L1", (0.0, 0.0, 30.0), label=4),
        _centroid("L2", (0.0, 0.0, 40.0), label=5),
    ]
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert len(offsets) == 5
    for rec in offsets:
        assert math.isfinite(rec.offset_mm)


def test_adv_anisotropic_spacing_all_offsets_finite():
    """Anisotropic spacing (1, 1, 5) produces finite offset_voxel values."""
    centroids = _straight_spine(6)
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit, spacing_mm=(1.0, 1.0, 5.0))
    for rec in offsets:
        assert math.isfinite(rec.offset_voxel)
        assert rec.offset_voxel >= 0.0


def test_adv_large_mm_coordinates_no_crash():
    """Large mm coordinates (realistic whole-spine extent) do not crash."""
    levels = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]
    centroids = [
        _centroid(lv, (1.5 * i, 0.0, 16.0 * i), label=i + 1)
        for i, lv in enumerate(levels)
    ]
    fit = _fit(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert len(offsets) == len(levels)
    for rec in offsets:
        assert math.isfinite(rec.offset_mm)
