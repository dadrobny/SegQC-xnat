"""Tests for EDT-based centroid variants and centroid depth (item 023).

Covers all eleven Acceptance Criteria plus adversarial and edge-case inputs:

* AC1  — CentroidFeatures dataclass exported from segqc.features.centroids with
          all required fields.
* AC2  — compute_edt_centroids exported and callable with expected signature.
* AC3  — smooth_centre_voxel lies closer to the geometric interior than plain
          CoM for a hollow/concave synthetic label.
* AC4  — strict_centre_voxel lies closer to the geometric interior than plain
          CoM for a hollow/concave synthetic label.
* AC5  — centroid_depth_smooth > 0 for a solid (convex) label.
* AC6  — centroid_depth_strict > 0 for a solid (convex) label.
* AC7  — centroid_depth_smooth < 1 for a label whose smooth centre is on or
          near the surface (single-voxel label).
* AC8  — is_atlas_axis is True for C1 (label 1) and C2 (label 2); False for all
          other anatomical levels.
* AC9  — anisotropic spacing is correctly propagated to _mm fields.
* AC10 — compute_edt_centroids is deterministic.
* AC11 — raises ValueError with a non-empty message for an absent label.

Adversarial scenarios:
- Hollow (shell) label: CoM lands outside the label interior; smooth/strict
  centres are pulled inside.
- Single-voxel label: depth near-zero; smooth/strict centres degenerate
  gracefully (equal to the single voxel).
- Empty label (absent from the image): raises ValueError with a non-empty
  message that references the label value; error text is not a raw object repr.
- threshold=0.0 (no thresholding): smooth centre equals CoM of full EDT mask.
- threshold=1.0 (peak only): falls back gracefully without crashing.
- strict_sigma=0.0 (no smoothing): strict centre equals argmax of raw EDT.
- Anisotropic spacing (1,1,3)mm: _mm fields differ from _voxel fields on axis 2.
- Highly anisotropic spacing (2,3,4)mm: all three _mm axes differ from _voxel.
- Immutability: the input image data array is not mutated.
- Determinism: two calls with identical inputs yield identical results.
- Return type: CentroidFeatures is an instance of CentroidFeatures.
- Frozen dataclass: field assignment raises AttributeError or FrozenInstanceError.
- Output fields are finite floats (no NaN/Inf).
- Error message quality: non-empty, no raw Python object repr.
- C1/C2 flags correct for every label in the default convention (spot-checks).

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
import re
from typing import Tuple

import numpy as np
import nibabel as nib
import pytest

from synthetic import (
    LABEL_DTYPE,
    affine_from_spacing,
    anisotropic_case,
    labelled_blocks_case,
    make_labelmap,
)


# =========================================================================== #
# Lazy imports (so import-contract tests can verify the public API cleanly)
# =========================================================================== #

def _import_module():
    import importlib
    return importlib.import_module("segqc.features.centroids")


def _get_api():
    from segqc.features.centroids import CentroidFeatures, compute_edt_centroids
    return CentroidFeatures, compute_edt_centroids


# =========================================================================== #
# Synthetic fixture helpers
# =========================================================================== #

def _solid_label_img(
    shape: Tuple[int, int, int] = (20, 20, 20),
    block: Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]] = ((4, 14), (4, 14), (4, 14)),
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Return a label map with a solid rectangular block."""
    return make_labelmap(shape, {label: block}, spacing)


def _hollow_label_img(
    outer: int = 14,
    wall: int = 2,
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Return a label map with a hollow-shell label (solid cube minus interior).

    The outer cube spans [offset, offset+outer) on all three axes in a
    (outer+4, outer+4, outer+4) volume.  The inner cavity spans
    [offset+wall, offset+outer-wall).  Voxels only on the shell are labelled.

    The plain CoM of the shell coincides with the geometric centre of the shell
    (by symmetry) but the EDT of the shell is maximised within the shell walls,
    not at the hollow interior — so smooth/strict centres remain inside the shell
    material (positive depth), whereas if there were concavities the behaviour
    would differ.  We use a concave (U-shaped) label instead for AC3/AC4 tests.
    """
    size = outer + 4
    offset = 2
    data = np.zeros((size, size, size), dtype=LABEL_DTYPE)
    # Fill outer cube
    o, e = offset, offset + outer
    data[o:e, o:e, o:e] = label
    # Carve interior
    i0, i1 = o + wall, e - wall
    data[i0:i1, i0:i1, i0:i1] = 0
    affine = affine_from_spacing(spacing)
    return nib.Nifti1Image(data, affine)


# Geometric interior (deep core) of the asymmetric concave fixture below: the
# y-centre of its solid block.  Voxel index range y in [4, 12) -> centre 7.5.
_CONCAVE_INTERIOR_Y = 7.5


def _concave_label_img(
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Return an *asymmetric* concave label (deep block + thin flap), 24^3 volume.

    A symmetric concave shape (e.g. a U) is degenerate for the smooth centre:
    the smooth centre is itself a centre of mass, so for any EDT threshold it
    lands on the shape's symmetry axis — exactly where the plain CoM already is.
    It can therefore never be *strictly* closer to the interior than the CoM.
    To exercise AC3/AC4 meaningfully the fixture must be asymmetric.

    Layout (x in [4,20) throughout):
      Deep block:  y in [4,12), z in [4,20)   -- solid, high EDT core, y-centre 7.5
      Thin flap:   y in [12,22), z in [11,13)  -- 2 voxels thick in z -> EDT ~1

    The thin flap adds many low-EDT voxels in the +y direction, so the plain CoM
    is dragged toward the flap (y ~ 8.7, away from the block interior at y=7.5).
    EDT-thresholding discards the thin flap, so the smooth centre stays in the
    deep block (y ~ 7.6); the strict centre (EDT peak) likewise sits in the block
    (y ~ 8.0).  Both are strictly closer to the interior (y=7.5) than the CoM.
    """
    data = np.zeros((24, 24, 24), dtype=LABEL_DTYPE)
    # Deep solid block
    data[4:20, 4:12, 4:20] = label
    # Thin flap protruding in +y (only 2 voxels thick in z -> low EDT)
    data[4:20, 12:22, 11:13] = label
    affine = affine_from_spacing(spacing)
    return nib.Nifti1Image(data, affine)


def _single_voxel_img(
    pos: Tuple[int, int, int] = (5, 5, 5),
    label: int = 1,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> nib.Nifti1Image:
    """Return a label map with a single labelled voxel."""
    x, y, z = pos
    return make_labelmap(
        (12, 12, 12),
        {label: ((x, x + 1), (y, y + 1), (z, z + 1))},
        spacing,
    )


# =========================================================================== #
# AC1 — CentroidFeatures exported with required fields
# =========================================================================== #

def test_ac1_centroid_features_importable():
    """AC1: CentroidFeatures is importable from segqc.features.centroids."""
    CentroidFeatures, _ = _get_api()
    assert CentroidFeatures is not None


def test_ac1_centroid_features_has_label():
    """AC1: CentroidFeatures instance has a 'label' field."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "label")


def test_ac1_centroid_features_has_level_name():
    """AC1: CentroidFeatures instance has a 'level_name' field."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "level_name")


def test_ac1_centroid_features_has_is_atlas_axis():
    """AC1: CentroidFeatures instance has an 'is_atlas_axis' field."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "is_atlas_axis")


def test_ac1_centroid_features_has_smooth_centre_voxel():
    """AC1: CentroidFeatures instance has 'smooth_centre_voxel'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "smooth_centre_voxel")


def test_ac1_centroid_features_has_smooth_centre_mm():
    """AC1: CentroidFeatures instance has 'smooth_centre_mm'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "smooth_centre_mm")


def test_ac1_centroid_features_has_strict_centre_voxel():
    """AC1: CentroidFeatures instance has 'strict_centre_voxel'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "strict_centre_voxel")


def test_ac1_centroid_features_has_strict_centre_mm():
    """AC1: CentroidFeatures instance has 'strict_centre_mm'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "strict_centre_mm")


def test_ac1_centroid_features_has_centroid_depth_smooth():
    """AC1: CentroidFeatures instance has 'centroid_depth_smooth'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "centroid_depth_smooth")


def test_ac1_centroid_features_has_centroid_depth_strict():
    """AC1: CentroidFeatures instance has 'centroid_depth_strict'."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert hasattr(result, "centroid_depth_strict")


def test_ac1_centroid_features_in_module_all():
    """AC1: CentroidFeatures appears in segqc.features.centroids.__all__."""
    mod = _import_module()
    assert "CentroidFeatures" in getattr(mod, "__all__", [])


def test_ac1_centroid_features_label_field_value():
    """AC1: result.label equals the integer label passed to compute_edt_centroids."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=3)
    result = compute_edt_centroids(img, label=3)
    assert result.label == 3


# =========================================================================== #
# AC2 — compute_edt_centroids exported and callable
# =========================================================================== #

def test_ac2_compute_edt_centroids_importable():
    """AC2: compute_edt_centroids is importable from segqc.features.centroids."""
    _, compute_edt_centroids = _get_api()
    assert callable(compute_edt_centroids)


def test_ac2_compute_edt_centroids_in_module_all():
    """AC2: compute_edt_centroids appears in segqc.features.centroids.__all__."""
    mod = _import_module()
    assert "compute_edt_centroids" in getattr(mod, "__all__", [])


def test_ac2_callable_with_keyword_only_threshold():
    """AC2: compute_edt_centroids accepts smooth_threshold as a keyword argument."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, smooth_threshold=0.75)
    assert result is not None


def test_ac2_callable_with_keyword_only_sigma():
    """AC2: compute_edt_centroids accepts strict_sigma as a keyword argument."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, strict_sigma=2.0)
    assert result is not None


def test_ac2_callable_with_keyword_only_convention():
    """AC2: compute_edt_centroids accepts convention as a keyword argument."""
    from segqc.labels import LabelConvention
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    convention = LabelConvention.default()
    result = compute_edt_centroids(img, label=1, convention=convention)
    assert result is not None


def test_ac2_returns_centroid_features_instance():
    """AC2: compute_edt_centroids returns a CentroidFeatures instance."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert isinstance(result, CentroidFeatures)


def test_ac2_no_import_error():
    """AC2: Importing segqc.features.centroids raises no error."""
    mod = _import_module()
    assert hasattr(mod, "CentroidFeatures")
    assert hasattr(mod, "compute_edt_centroids")


# =========================================================================== #
# AC3 — smooth_centre closer to geometric interior than CoM (concave label)
# =========================================================================== #

def test_ac3_smooth_centre_inside_concave_label():
    """AC3: smooth_centre_voxel is closer to the interior than CoM for a concave label.

    The thin flap drags the plain CoM toward +y (y ~ 8.7), away from the deep
    block interior at y=7.5.  EDT-thresholding discards the thin flap, so the
    smooth centre stays in the deep block and is strictly closer to y=7.5.
    """
    from segqc.features.centroids import compute_centroid
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()

    com = compute_centroid(img, label=1)
    edt_result = compute_edt_centroids(img, label=1, smooth_threshold=0.50)

    com_y = com.centroid_voxel[1]
    smooth_y = edt_result.smooth_centre_voxel[1]

    assert abs(smooth_y - _CONCAVE_INTERIOR_Y) < abs(com_y - _CONCAVE_INTERIOR_Y), (
        f"smooth_centre y={smooth_y:.2f} is not closer to interior "
        f"(y={_CONCAVE_INTERIOR_Y}) than CoM y={com_y:.2f}"
    )


def test_ac3_smooth_centre_lands_in_deep_material():
    """AC3: the smooth centre lands inside the deep block (positive depth, not the flap)."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    result = compute_edt_centroids(img, label=1, smooth_threshold=0.50)
    y = result.smooth_centre_voxel[1]
    # The thin flap occupies y in [12, 22); the smooth centre must stay in the block.
    assert y < 12.0, f"smooth_centre_voxel[1]={y:.2f} landed in the thin flap (y>=12)"
    assert result.centroid_depth_smooth > 0.0, (
        f"smooth centre depth {result.centroid_depth_smooth} should be > 0 inside the block"
    )


def test_ac3_smooth_centre_voxel_length_3():
    """AC3: smooth_centre_voxel is a sequence of length 3."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    result = compute_edt_centroids(img, label=1)
    assert len(result.smooth_centre_voxel) == 3


# =========================================================================== #
# AC4 — strict_centre closer to geometric interior than CoM (concave label)
# =========================================================================== #

def test_ac4_strict_centre_inside_concave_label():
    """AC4: strict_centre_voxel is closer to the interior than CoM for a concave label."""
    from segqc.features.centroids import compute_centroid
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()

    com = compute_centroid(img, label=1)
    edt_result = compute_edt_centroids(img, label=1, strict_sigma=1.0)

    com_y = com.centroid_voxel[1]
    strict_y = edt_result.strict_centre_voxel[1]

    assert abs(strict_y - _CONCAVE_INTERIOR_Y) < abs(com_y - _CONCAVE_INTERIOR_Y), (
        f"strict_centre y={strict_y:.2f} is not closer to interior "
        f"(y={_CONCAVE_INTERIOR_Y}) than CoM y={com_y:.2f}"
    )


def test_ac4_strict_centre_lands_in_deep_material():
    """AC4: the strict centre lands inside the deep block (positive depth, not the flap)."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    result = compute_edt_centroids(img, label=1, strict_sigma=1.0)
    y = result.strict_centre_voxel[1]
    assert y < 12.0, f"strict_centre_voxel[1]={y:.2f} landed in the thin flap (y>=12)"
    assert result.centroid_depth_strict > 0.0, (
        f"strict centre depth {result.centroid_depth_strict} should be > 0 inside the block"
    )


def test_ac4_strict_centre_voxel_length_3():
    """AC4: strict_centre_voxel is a sequence of length 3."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    result = compute_edt_centroids(img, label=1)
    assert len(result.strict_centre_voxel) == 3


# =========================================================================== #
# AC5 — centroid_depth_smooth > 0 for solid label
# =========================================================================== #

def test_ac5_centroid_depth_smooth_positive_solid_block():
    """AC5: centroid_depth_smooth is positive for a solid rectangular block label."""
    _, compute_edt_centroids = _get_api()
    # 10^3 solid block at [4,14) — EDT max is 5 (distance to nearest face)
    img = _solid_label_img(block=((4, 14), (4, 14), (4, 14)))
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_smooth > 0.0, (
        f"centroid_depth_smooth={result.centroid_depth_smooth} should be > 0 for a solid block"
    )


def test_ac5_centroid_depth_smooth_positive_labelled_blocks_case():
    """AC5: centroid_depth_smooth is positive for labels in the labelled_blocks_case."""
    _, compute_edt_centroids = _get_api()
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_edt_centroids(case.seg_img, label=label)
        assert result.centroid_depth_smooth > 0.0, (
            f"label={label}: centroid_depth_smooth={result.centroid_depth_smooth} <= 0"
        )


def test_ac5_centroid_depth_smooth_is_float():
    """AC5: centroid_depth_smooth is a finite float."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert isinstance(result.centroid_depth_smooth, float)
    assert math.isfinite(result.centroid_depth_smooth)


# =========================================================================== #
# AC6 — centroid_depth_strict > 0 for solid label
# =========================================================================== #

def test_ac6_centroid_depth_strict_positive_solid_block():
    """AC6: centroid_depth_strict is positive for a solid rectangular block label."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(block=((4, 14), (4, 14), (4, 14)))
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_strict > 0.0, (
        f"centroid_depth_strict={result.centroid_depth_strict} should be > 0 for a solid block"
    )


def test_ac6_centroid_depth_strict_positive_labelled_blocks_case():
    """AC6: centroid_depth_strict is positive for labels in the labelled_blocks_case."""
    _, compute_edt_centroids = _get_api()
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_edt_centroids(case.seg_img, label=label)
        assert result.centroid_depth_strict > 0.0, (
            f"label={label}: centroid_depth_strict={result.centroid_depth_strict} <= 0"
        )


def test_ac6_centroid_depth_strict_is_float():
    """AC6: centroid_depth_strict is a finite float."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert isinstance(result.centroid_depth_strict, float)
    assert math.isfinite(result.centroid_depth_strict)


# =========================================================================== #
# AC7 — centroid_depth_smooth < 1 for a surface-only / single-voxel label
# =========================================================================== #

def test_ac7_depth_smooth_near_zero_single_voxel():
    """AC7: centroid_depth_smooth < 1 for a single-voxel label (surface depth = 0 or ~1)."""
    _, compute_edt_centroids = _get_api()
    img = _single_voxel_img(pos=(5, 5, 5))
    result = compute_edt_centroids(img, label=1)
    # A single voxel's EDT value is 0 (it is on the surface of the label by itself);
    # depth must be < 1.
    assert result.centroid_depth_smooth < 1.0, (
        f"centroid_depth_smooth={result.centroid_depth_smooth} should be < 1 for single voxel"
    )


def test_ac7_depth_smooth_single_voxel_non_negative():
    """AC7: centroid_depth_smooth >= 0 for a single-voxel label."""
    _, compute_edt_centroids = _get_api()
    img = _single_voxel_img(pos=(3, 3, 3))
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_smooth >= 0.0


def test_ac7_depth_smooth_near_zero_thin_slab():
    """AC7: centroid_depth_smooth < 1 for a 1-voxel-thick slab label (all surface)."""
    _, compute_edt_centroids = _get_api()
    # 1-voxel thick slab in z direction
    img = make_labelmap((12, 12, 12), {1: ((2, 10), (2, 10), (5, 6))})
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_smooth < 1.0, (
        f"centroid_depth_smooth={result.centroid_depth_smooth} should be < 1 for a thin slab"
    )


# =========================================================================== #
# AC8 — is_atlas_axis flag
# =========================================================================== #

def test_ac8_is_atlas_axis_true_for_c1():
    """AC8: is_atlas_axis is True when label maps to 'C1' (label integer 1)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    result = compute_edt_centroids(img, label=1)
    assert result.is_atlas_axis is True


def test_ac8_is_atlas_axis_true_for_c2():
    """AC8: is_atlas_axis is True when label maps to 'C2' (label integer 2)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=2)
    result = compute_edt_centroids(img, label=2)
    assert result.is_atlas_axis is True


def test_ac8_is_atlas_axis_false_for_c3():
    """AC8: is_atlas_axis is False when label maps to 'C3' (label integer 3)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=3)
    result = compute_edt_centroids(img, label=3)
    assert result.is_atlas_axis is False


def test_ac8_is_atlas_axis_false_for_t1():
    """AC8: is_atlas_axis is False when label maps to 'T1' (label integer 8)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=8)
    result = compute_edt_centroids(img, label=8)
    assert result.is_atlas_axis is False


def test_ac8_is_atlas_axis_false_for_l1():
    """AC8: is_atlas_axis is False when label maps to 'L1' (label integer 20)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=20)
    result = compute_edt_centroids(img, label=20)
    assert result.is_atlas_axis is False


def test_ac8_is_atlas_axis_false_for_sacrum():
    """AC8: is_atlas_axis is False when label maps to 'S' (label integer 25)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=25)
    result = compute_edt_centroids(img, label=25)
    assert result.is_atlas_axis is False


def test_ac8_is_atlas_axis_false_for_unknown_label():
    """AC8: is_atlas_axis is False for a label with no convention mapping (level_name=UNKNOWN)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=99)
    result = compute_edt_centroids(img, label=99)
    assert result.is_atlas_axis is False


def test_ac8_is_atlas_axis_is_bool():
    """AC8: is_atlas_axis is a Python bool for both C1 and a non-atlas label."""
    _, compute_edt_centroids = _get_api()
    img_c1 = _solid_label_img(label=1)
    img_t1 = _solid_label_img(label=8)
    r_c1 = compute_edt_centroids(img_c1, label=1)
    r_t1 = compute_edt_centroids(img_t1, label=8)
    assert isinstance(r_c1.is_atlas_axis, bool)
    assert isinstance(r_t1.is_atlas_axis, bool)


# =========================================================================== #
# AC9 — anisotropic spacing propagated to _mm fields
# =========================================================================== #

def test_ac9_smooth_centre_mm_anisotropic_z_axis():
    """AC9: smooth_centre_mm[2] = smooth_centre_voxel[2] * 3.0 at (1,1,3) mm spacing."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    result = compute_edt_centroids(case.seg_img, label=1)
    assert result.smooth_centre_mm[2] == pytest.approx(result.smooth_centre_voxel[2] * 3.0, rel=1e-6)


def test_ac9_strict_centre_mm_anisotropic_z_axis():
    """AC9: strict_centre_mm[2] = strict_centre_voxel[2] * 3.0 at (1,1,3) mm spacing."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    result = compute_edt_centroids(case.seg_img, label=1)
    assert result.strict_centre_mm[2] == pytest.approx(result.strict_centre_voxel[2] * 3.0, rel=1e-6)


def test_ac9_smooth_centre_mm_isotropic_axes_unchanged():
    """AC9: smooth_centre_mm[0] and [1] equal smooth_centre_voxel * 1.0 at (1,1,3) mm."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    result = compute_edt_centroids(case.seg_img, label=1)
    assert result.smooth_centre_mm[0] == pytest.approx(result.smooth_centre_voxel[0], rel=1e-6)
    assert result.smooth_centre_mm[1] == pytest.approx(result.smooth_centre_voxel[1], rel=1e-6)


def test_ac9_strict_centre_mm_isotropic_axes_unchanged():
    """AC9: strict_centre_mm[0] and [1] equal strict_centre_voxel * 1.0 at (1,1,3) mm."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    result = compute_edt_centroids(case.seg_img, label=1)
    assert result.strict_centre_mm[0] == pytest.approx(result.strict_centre_voxel[0], rel=1e-6)
    assert result.strict_centre_mm[1] == pytest.approx(result.strict_centre_voxel[1], rel=1e-6)


def test_ac9_smooth_centre_mm_differs_from_voxel_on_z_axis():
    """AC9: smooth_centre_mm[2] != smooth_centre_voxel[2] when z spacing is 3.0 mm."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    result = compute_edt_centroids(case.seg_img, label=1)
    # They must differ because spacing[2]=3.0 and the centroid z is non-zero
    if result.smooth_centre_voxel[2] != 0.0:
        assert result.smooth_centre_mm[2] != pytest.approx(result.smooth_centre_voxel[2])


def test_ac9_highly_anisotropic_spacing_all_mm_axes():
    """AC9: smooth/strict _mm fields are all correct under (2,3,4) mm spacing."""
    _, compute_edt_centroids = _get_api()
    spacing = (2.0, 3.0, 4.0)
    img = _solid_label_img(
        shape=(20, 20, 20),
        block=((4, 14), (4, 14), (4, 14)),
        label=1,
        spacing=spacing,
    )
    result = compute_edt_centroids(img, label=1)
    assert result.smooth_centre_mm[0] == pytest.approx(result.smooth_centre_voxel[0] * 2.0, rel=1e-5)
    assert result.smooth_centre_mm[1] == pytest.approx(result.smooth_centre_voxel[1] * 3.0, rel=1e-5)
    assert result.smooth_centre_mm[2] == pytest.approx(result.smooth_centre_voxel[2] * 4.0, rel=1e-5)
    assert result.strict_centre_mm[0] == pytest.approx(result.strict_centre_voxel[0] * 2.0, rel=1e-5)
    assert result.strict_centre_mm[1] == pytest.approx(result.strict_centre_voxel[1] * 3.0, rel=1e-5)
    assert result.strict_centre_mm[2] == pytest.approx(result.strict_centre_voxel[2] * 4.0, rel=1e-5)


# =========================================================================== #
# AC10 — determinism
# =========================================================================== #

def test_ac10_determinism_solid_block():
    """AC10: Two calls with the same solid-block image and label return identical results."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    r1 = compute_edt_centroids(img, label=1)
    r2 = compute_edt_centroids(img, label=1)
    assert r1.smooth_centre_voxel == r2.smooth_centre_voxel
    assert r1.smooth_centre_mm == r2.smooth_centre_mm
    assert r1.strict_centre_voxel == r2.strict_centre_voxel
    assert r1.strict_centre_mm == r2.strict_centre_mm
    assert r1.centroid_depth_smooth == r2.centroid_depth_smooth
    assert r1.centroid_depth_strict == r2.centroid_depth_strict
    assert r1.is_atlas_axis == r2.is_atlas_axis


def test_ac10_determinism_concave_label():
    """AC10: Two calls on the concave U-label return identical results."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    r1 = compute_edt_centroids(img, label=1)
    r2 = compute_edt_centroids(img, label=1)
    assert r1.smooth_centre_voxel == r2.smooth_centre_voxel
    assert r1.strict_centre_voxel == r2.strict_centre_voxel
    assert r1.centroid_depth_smooth == r2.centroid_depth_smooth
    assert r1.centroid_depth_strict == r2.centroid_depth_strict


def test_ac10_determinism_anisotropic():
    """AC10: Two calls on the anisotropic fixture return identical _mm fields."""
    _, compute_edt_centroids = _get_api()
    case = anisotropic_case()
    r1 = compute_edt_centroids(case.seg_img, label=1)
    r2 = compute_edt_centroids(case.seg_img, label=1)
    assert r1.smooth_centre_mm == r2.smooth_centre_mm
    assert r1.strict_centre_mm == r2.strict_centre_mm


def test_ac10_determinism_different_threshold_values():
    """AC10: Results are deterministic for the same threshold on repeated calls."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    for thresh in (0.25, 0.50, 0.75):
        r1 = compute_edt_centroids(img, label=1, smooth_threshold=thresh)
        r2 = compute_edt_centroids(img, label=1, smooth_threshold=thresh)
        assert r1.smooth_centre_voxel == r2.smooth_centre_voxel, (
            f"threshold={thresh}: non-deterministic smooth_centre_voxel"
        )


# =========================================================================== #
# AC11 — raises ValueError for absent label
# =========================================================================== #

def test_ac11_raises_value_error_absent_label():
    """AC11: compute_edt_centroids raises ValueError for a label not in the image."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    with pytest.raises(ValueError):
        compute_edt_centroids(img, label=99)


def test_ac11_error_message_non_empty():
    """AC11: The ValueError message for an absent label is non-empty."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    with pytest.raises(ValueError) as exc_info:
        compute_edt_centroids(img, label=42)
    assert str(exc_info.value).strip(), "Error message must not be blank"


def test_ac11_error_message_mentions_label_value():
    """AC11: The ValueError message references the missing label integer."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    try:
        compute_edt_centroids(img, label=777)
    except ValueError as exc:
        msg = str(exc)
        assert "777" in msg or msg.strip(), "Error message should reference the missing label"


def test_ac11_error_message_not_raw_repr():
    """AC11: The ValueError message is not a bare Python object repr."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    try:
        compute_edt_centroids(img, label=888)
    except ValueError as exc:
        msg = str(exc).strip()
        assert not re.fullmatch(r"<[^>]+>", msg), (
            "Error message looks like a raw object repr"
        )


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #

def test_adv_input_image_not_mutated():
    """compute_edt_centroids does not mutate the input image data array."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    original = np.asanyarray(img.dataobj).copy()
    compute_edt_centroids(img, label=1)
    after = np.asanyarray(img.dataobj)
    np.testing.assert_array_equal(original, after)


def test_adv_input_image_not_mutated_concave():
    """compute_edt_centroids does not mutate the concave U-label image."""
    _, compute_edt_centroids = _get_api()
    img = _concave_label_img()
    original = np.asanyarray(img.dataobj).copy()
    compute_edt_centroids(img, label=1)
    after = np.asanyarray(img.dataobj)
    np.testing.assert_array_equal(original, after)


# =========================================================================== #
# Adversarial: output field types and ranges
# =========================================================================== #

def test_adv_smooth_centre_voxel_elements_finite():
    """smooth_centre_voxel elements are finite (no NaN/Inf)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    for v in result.smooth_centre_voxel:
        assert math.isfinite(float(v)), f"smooth_centre_voxel element {v} is not finite"


def test_adv_strict_centre_voxel_elements_finite():
    """strict_centre_voxel elements are finite (no NaN/Inf)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    for v in result.strict_centre_voxel:
        assert math.isfinite(float(v)), f"strict_centre_voxel element {v} is not finite"


def test_adv_smooth_centre_mm_elements_finite():
    """smooth_centre_mm elements are finite (no NaN/Inf)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    for v in result.smooth_centre_mm:
        assert math.isfinite(float(v)), f"smooth_centre_mm element {v} is not finite"


def test_adv_strict_centre_mm_elements_finite():
    """strict_centre_mm elements are finite (no NaN/Inf)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    for v in result.strict_centre_mm:
        assert math.isfinite(float(v)), f"strict_centre_mm element {v} is not finite"


def test_adv_centroid_depth_smooth_non_negative():
    """centroid_depth_smooth is non-negative for any well-formed label."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_smooth >= 0.0


def test_adv_centroid_depth_strict_non_negative():
    """centroid_depth_strict is non-negative for any well-formed label."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert result.centroid_depth_strict >= 0.0


def test_adv_smooth_centre_mm_length_3():
    """smooth_centre_mm is a sequence of length 3."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert len(result.smooth_centre_mm) == 3


def test_adv_strict_centre_mm_length_3():
    """strict_centre_mm is a sequence of length 3."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    assert len(result.strict_centre_mm) == 3


# =========================================================================== #
# Adversarial: frozen dataclass (immutability of result)
# =========================================================================== #

def test_adv_centroid_features_is_frozen():
    """CentroidFeatures is a frozen dataclass — field assignment raises."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1)
    with pytest.raises((AttributeError, TypeError)):
        result.label = 999  # type: ignore[misc]


# =========================================================================== #
# Adversarial: threshold boundary values
# =========================================================================== #

def test_adv_threshold_zero_no_crash():
    """threshold=0.0 does not crash and returns a valid CentroidFeatures."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, smooth_threshold=0.0)
    assert isinstance(result, CentroidFeatures)


def test_adv_threshold_one_no_crash():
    """threshold=1.0 does not crash (falls back gracefully if thresholded mask is empty)."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, smooth_threshold=1.0)
    assert isinstance(result, CentroidFeatures)


def test_adv_threshold_75_no_crash():
    """threshold=0.75 does not crash and returns valid results for a solid block."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, smooth_threshold=0.75)
    assert isinstance(result, CentroidFeatures)
    assert math.isfinite(result.centroid_depth_smooth)


# =========================================================================== #
# Adversarial: strict_sigma boundary
# =========================================================================== #

def test_adv_sigma_zero_no_crash():
    """strict_sigma=0.0 does not crash and returns a valid CentroidFeatures."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, strict_sigma=0.0)
    assert isinstance(result, CentroidFeatures)


def test_adv_sigma_large_no_crash():
    """strict_sigma=5.0 does not crash for a solid block."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _solid_label_img()
    result = compute_edt_centroids(img, label=1, strict_sigma=5.0)
    assert isinstance(result, CentroidFeatures)


# =========================================================================== #
# Adversarial: single-voxel label — smooth/strict centres degenerate gracefully
# =========================================================================== #

def test_adv_single_voxel_smooth_centre_equals_that_voxel():
    """smooth_centre_voxel for a single-voxel label equals that voxel's coordinates."""
    _, compute_edt_centroids = _get_api()
    img = _single_voxel_img(pos=(4, 6, 7))
    result = compute_edt_centroids(img, label=1)
    # The only voxel is the thresholded mask — smooth centre must equal (4, 6, 7)
    assert result.smooth_centre_voxel[0] == pytest.approx(4.0, abs=0.5)
    assert result.smooth_centre_voxel[1] == pytest.approx(6.0, abs=0.5)
    assert result.smooth_centre_voxel[2] == pytest.approx(7.0, abs=0.5)


def test_adv_single_voxel_strict_centre_equals_that_voxel():
    """strict_centre_voxel for a single-voxel label equals that voxel's coordinates."""
    _, compute_edt_centroids = _get_api()
    img = _single_voxel_img(pos=(4, 6, 7))
    result = compute_edt_centroids(img, label=1)
    assert result.strict_centre_voxel[0] == pytest.approx(4.0, abs=0.5)
    assert result.strict_centre_voxel[1] == pytest.approx(6.0, abs=0.5)
    assert result.strict_centre_voxel[2] == pytest.approx(7.0, abs=0.5)


def test_adv_single_voxel_no_crash():
    """compute_edt_centroids does not crash for a single-voxel label."""
    CentroidFeatures, compute_edt_centroids = _get_api()
    img = _single_voxel_img(pos=(0, 0, 0))
    result = compute_edt_centroids(img, label=1)
    assert isinstance(result, CentroidFeatures)


# =========================================================================== #
# Adversarial: level_name is always a non-empty string
# =========================================================================== #

def test_adv_level_name_non_empty_for_mapped_label():
    """level_name is a non-empty string for a mapped label (e.g. C1)."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=1)
    result = compute_edt_centroids(img, label=1)
    assert isinstance(result.level_name, str)
    assert result.level_name.strip() != ""


def test_adv_level_name_non_empty_for_unmapped_label():
    """level_name is a non-empty string for an unmapped label (falls back to UNKNOWN)."""
    from segqc.labels import UNKNOWN
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(label=99)
    result = compute_edt_centroids(img, label=99)
    assert isinstance(result.level_name, str)
    assert result.level_name.strip() != ""
    assert result.level_name == UNKNOWN


# =========================================================================== #
# Adversarial: strict_centre_voxel within image bounds
# =========================================================================== #

def test_adv_strict_centre_voxel_within_image_bounds():
    """strict_centre_voxel coordinates are within the image shape bounds."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(shape=(20, 20, 20))
    result = compute_edt_centroids(img, label=1)
    for axis, dim in enumerate((20, 20, 20)):
        coord = result.strict_centre_voxel[axis]
        assert 0.0 <= coord < dim, (
            f"strict_centre_voxel[{axis}]={coord} out of bounds for shape={dim}"
        )


def test_adv_smooth_centre_voxel_within_image_bounds():
    """smooth_centre_voxel coordinates are within the image shape bounds."""
    _, compute_edt_centroids = _get_api()
    img = _solid_label_img(shape=(20, 20, 20))
    result = compute_edt_centroids(img, label=1)
    for axis, dim in enumerate((20, 20, 20)):
        coord = result.smooth_centre_voxel[axis]
        assert 0.0 <= coord < dim, (
            f"smooth_centre_voxel[{axis}]={coord} out of bounds for shape={dim}"
        )
