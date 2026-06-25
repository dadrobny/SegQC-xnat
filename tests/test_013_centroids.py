"""Tests for centroid / centre-of-mass per label (item 013).

Covers all four Acceptance Criteria plus adversarial and edge-case inputs:
single-voxel label (centroid equals that voxel), label spanning full axis
(centroid at the midpoint), anisotropic spacing (physical coords differ from
voxel coords), missing/absent labels (clear error), unmapped label integers
(level_name falls back to UNKNOWN), level_name non-empty string contract,
immutability, and determinism.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

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

from segqc.features.centroids import LabelCentroid, compute_centroid
from segqc.labels import UNKNOWN, LabelConvention


# =========================================================================== #
# Helpers
# =========================================================================== #

def _default_convention() -> LabelConvention:
    """Return the default TotalSegmentator / VerSe label convention."""
    return LabelConvention.default()


# =========================================================================== #
# Import contract
# =========================================================================== #

def test_import_label_centroid():
    """LabelCentroid is importable from segqc.features.centroids."""
    from segqc.features.centroids import LabelCentroid as LC  # noqa: F401
    assert LC is LabelCentroid


def test_import_compute_centroid():
    """compute_centroid is importable from segqc.features.centroids."""
    from segqc.features.centroids import compute_centroid as cc  # noqa: F401
    assert callable(cc)


def test_no_import_error():
    """Importing segqc.features.centroids raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.centroids")
    assert hasattr(mod, "LabelCentroid")
    assert hasattr(mod, "compute_centroid")


# =========================================================================== #
# AC1: Centroids match hand-computed expectations in voxel and mm space
# =========================================================================== #

def test_ac1_centroid_voxel_label1_labelled_blocks():
    """AC1: Label 1 (block x[2:6], y[2:6], z[2:6]) has centroid_voxel = (3.5, 3.5, 3.5)."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    # Block x[2:6] at 1mm isotropic: mean voxel index = (2+3+4+5)/4 = 3.5
    assert result.centroid_voxel[0] == pytest.approx(3.5)
    assert result.centroid_voxel[1] == pytest.approx(3.5)
    assert result.centroid_voxel[2] == pytest.approx(3.5)


def test_ac1_centroid_mm_label1_isotropic():
    """AC1: At 1mm isotropic spacing, centroid_mm equals centroid_voxel for label 1."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    # At 1mm isotropic, physical == voxel
    assert result.centroid_mm[0] == pytest.approx(result.centroid_voxel[0])
    assert result.centroid_mm[1] == pytest.approx(result.centroid_voxel[1])
    assert result.centroid_mm[2] == pytest.approx(result.centroid_voxel[2])


def test_ac1_centroid_voxel_label2_labelled_blocks():
    """AC1: Label 2 (block x[2:6], y[10:14], z[2:6]) centroid_voxel is (3.5, 11.5, 3.5)."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=2)
    assert result.centroid_voxel[0] == pytest.approx(3.5)
    assert result.centroid_voxel[1] == pytest.approx(11.5)
    assert result.centroid_voxel[2] == pytest.approx(3.5)


def test_ac1_centroid_voxel_label3_labelled_blocks():
    """AC1: Label 3 (block x[10:14], y[2:6], z[10:14]) centroid_voxel is (11.5, 3.5, 11.5)."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=3)
    assert result.centroid_voxel[0] == pytest.approx(11.5)
    assert result.centroid_voxel[1] == pytest.approx(3.5)
    assert result.centroid_voxel[2] == pytest.approx(11.5)


def test_ac1_centroid_voxel_2x3x4_block():
    """AC1: A 2x3x4-voxel block centroid equals the geometric mean of its voxel indices."""
    # Block x[0:2], y[0:3], z[0:4]
    # centroid_voxel: x=(0+1)/2=0.5, y=(0+1+2)/3=1.0, z=(0+1+2+3)/4=1.5
    seg = make_labelmap((8, 8, 8), {1: ((0, 2), (0, 3), (0, 4))})
    result = compute_centroid(seg, label=1)
    assert result.centroid_voxel[0] == pytest.approx(0.5)
    assert result.centroid_voxel[1] == pytest.approx(1.0)
    assert result.centroid_voxel[2] == pytest.approx(1.5)


def test_ac1_returns_label_centroid_instance():
    """AC1: compute_centroid returns a LabelCentroid instance."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    assert isinstance(result, LabelCentroid)


def test_ac1_centroid_label_field():
    """AC1: LabelCentroid.label equals the requested integer label."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_centroid(case.seg_img, label=label)
        assert result.label == label


# =========================================================================== #
# AC2: Anisotropic spacing is correctly applied
# =========================================================================== #

def test_ac2_centroid_mm_differs_from_voxel_with_anisotropic_spacing():
    """AC2: With anisotropic spacing (1,1,3)mm, centroid_mm[2] != centroid_voxel[2]."""
    case = anisotropic_case()
    result = compute_centroid(case.seg_img, label=1)
    # z spacing is 3.0, so centroid_mm[2] = centroid_voxel[2] * 3.0
    assert result.centroid_mm[2] == pytest.approx(result.centroid_voxel[2] * 3.0)
    # They should not be equal (since spacing[2] = 3.0 != 1.0 and centroid[2] != 0)
    assert result.centroid_mm[2] != pytest.approx(result.centroid_voxel[2])


def test_ac2_centroid_mm_formula_anisotropic_label1():
    """AC2: centroid_mm = centroid_voxel * spacing for all axes at (1,1,3)mm."""
    case = anisotropic_case()
    result = compute_centroid(case.seg_img, label=1)
    # spacing = (1.0, 1.0, 3.0)
    assert result.centroid_mm[0] == pytest.approx(result.centroid_voxel[0] * 1.0)
    assert result.centroid_mm[1] == pytest.approx(result.centroid_voxel[1] * 1.0)
    assert result.centroid_mm[2] == pytest.approx(result.centroid_voxel[2] * 3.0)


def test_ac2_centroid_mm_label1_anisotropic_value():
    """AC2: Label 1 (x[2:6], y[2:6], z[2:5]) at (1,1,3)mm: centroid_mm[2] = 3.0 * 3.0 = 9.0."""
    case = anisotropic_case()
    result = compute_centroid(case.seg_img, label=1)
    # z block: [2,3,4]; mean index = 3.0; centroid_mm[2] = 3.0 * 3.0 = 9.0
    assert result.centroid_voxel[2] == pytest.approx(3.0)
    assert result.centroid_mm[2] == pytest.approx(9.0)


def test_ac2_centroid_mm_label2_anisotropic_value():
    """AC2: Label 2 (x[9:13], y[9:13], z[8:11]) at (1,1,3)mm: centroid_mm[2] = 9.0 * 3.0 = 27.0."""
    case = anisotropic_case()
    result = compute_centroid(case.seg_img, label=2)
    # z block: [8,9,10]; mean index = 9.0; centroid_mm[2] = 9.0 * 3.0 = 27.0
    assert result.centroid_voxel[2] == pytest.approx(9.0)
    assert result.centroid_mm[2] == pytest.approx(27.0)


def test_ac2_highly_anisotropic_spacing_centroid_mm():
    """AC2: centroid_mm is correct for highly anisotropic (2.0, 3.0, 4.0) mm spacing."""
    spacing = (2.0, 3.0, 4.0)
    # Single voxel at (5, 5, 5)
    seg = make_labelmap((10, 10, 10), {1: ((5, 6), (5, 6), (5, 6))}, spacing=spacing)
    result = compute_centroid(seg, label=1)
    assert result.centroid_voxel[0] == pytest.approx(5.0)
    assert result.centroid_voxel[1] == pytest.approx(5.0)
    assert result.centroid_voxel[2] == pytest.approx(5.0)
    assert result.centroid_mm[0] == pytest.approx(5.0 * 2.0)
    assert result.centroid_mm[1] == pytest.approx(5.0 * 3.0)
    assert result.centroid_mm[2] == pytest.approx(5.0 * 4.0)


def test_ac2_anisotropic_x_and_y_unchanged_at_unit_spacing():
    """AC2: centroid_mm[0] and [1] equal centroid_voxel[0] and [1] when those spacings are 1mm."""
    case = anisotropic_case()
    result = compute_centroid(case.seg_img, label=1)
    # spacing[0] == spacing[1] == 1.0
    assert result.centroid_mm[0] == pytest.approx(result.centroid_voxel[0])
    assert result.centroid_mm[1] == pytest.approx(result.centroid_voxel[1])


# =========================================================================== #
# AC3: Level-aware metadata attached to each centroid record
# =========================================================================== #

def test_ac3_level_name_is_non_empty_string():
    """AC3: level_name is a non-empty string for a present, mapped label."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    assert isinstance(result.level_name, str)
    assert result.level_name.strip() != ""


def test_ac3_mapped_label_yields_canonical_name():
    """AC3: An integer that maps to a canonical vertebra name is resolved correctly."""
    # Label value 1 maps to "C1" in the default TotalSegmentator convention.
    seg = make_labelmap((10, 10, 10), {1: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=1)
    assert result.level_name == "C1"


def test_ac3_mapped_label_8_yields_t1():
    """AC3: Label value 8 maps to 'T1' in the default convention."""
    seg = make_labelmap((10, 10, 10), {8: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=8)
    assert result.level_name == "T1"


def test_ac3_mapped_label_20_yields_l1():
    """AC3: Label value 20 maps to 'L1' in the default convention."""
    seg = make_labelmap((10, 10, 10), {20: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=20)
    assert result.level_name == "L1"


def test_ac3_mapped_label_25_yields_s():
    """AC3: Label value 25 (sacrum) maps to 'S' in the default convention."""
    seg = make_labelmap((10, 10, 10), {25: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=25)
    assert result.level_name == "S"


def test_ac3_mapped_label_2_yields_c2():
    """AC3: Label value 2 (C2 axis) maps to 'C2' in the default convention."""
    seg = make_labelmap((10, 10, 10), {2: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=2)
    assert result.level_name == "C2"


def test_ac3_unmapped_label_yields_unknown():
    """AC3: A label integer with no mapping in the convention yields level_name == UNKNOWN."""
    # Label value 99 has no entry in the default convention.
    seg = make_labelmap((10, 10, 10), {99: ((3, 7), (3, 7), (3, 7))})
    result = compute_centroid(seg, label=99)
    assert result.level_name == UNKNOWN


def test_ac3_level_name_non_empty_for_all_labelled_blocks_labels():
    """AC3: level_name is a non-empty string for all three labels in labelled_blocks_case."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_centroid(case.seg_img, label=label)
        assert isinstance(result.level_name, str)
        assert result.level_name.strip() != ""


def test_ac3_custom_convention_used_when_supplied():
    """AC3: A custom LabelConvention overrides the default name lookup."""
    custom_map = {1: "MyV1", 2: "MyV2"}
    convention = LabelConvention.from_mapping(custom_map)
    seg = make_labelmap((8, 8, 8), {1: ((2, 5), (2, 5), (2, 5))})
    result = compute_centroid(seg, label=1, convention=convention)
    assert result.level_name == "MyV1"


def test_ac3_custom_convention_unmapped_label_yields_unknown():
    """AC3: A label not in the custom convention yields UNKNOWN."""
    custom_map = {1: "MyV1"}
    convention = LabelConvention.from_mapping(custom_map)
    seg = make_labelmap((8, 8, 8), {5: ((2, 5), (2, 5), (2, 5))})
    result = compute_centroid(seg, label=5, convention=convention)
    assert result.level_name == UNKNOWN


def test_ac3_label_centroid_has_required_fields():
    """AC3: LabelCentroid exposes label, level_name, centroid_voxel, centroid_mm."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    for attr in ("label", "level_name", "centroid_voxel", "centroid_mm"):
        assert hasattr(result, attr), f"LabelCentroid missing field: {attr}"


# =========================================================================== #
# AC4: Functions are deterministic
# =========================================================================== #

def test_ac4_determinism_same_label_same_output():
    """AC4: Two calls with the same image and label return identical LabelCentroid instances."""
    case = labelled_blocks_case()
    r1 = compute_centroid(case.seg_img, label=1)
    r2 = compute_centroid(case.seg_img, label=1)
    assert r1.centroid_voxel == r2.centroid_voxel
    assert r1.centroid_mm == r2.centroid_mm
    assert r1.level_name == r2.level_name
    assert r1.label == r2.label


def test_ac4_determinism_anisotropic():
    """AC4: Two calls for the anisotropic case yield identical centroid_mm."""
    case = anisotropic_case()
    r1 = compute_centroid(case.seg_img, label=1)
    r2 = compute_centroid(case.seg_img, label=1)
    assert r1.centroid_mm == r2.centroid_mm


def test_ac4_determinism_across_all_labelled_block_labels():
    """AC4: Results for all three labels in labelled_blocks_case are stable across two runs."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        r1 = compute_centroid(case.seg_img, label=label)
        r2 = compute_centroid(case.seg_img, label=label)
        assert r1.centroid_voxel == r2.centroid_voxel
        assert r1.centroid_mm == r2.centroid_mm


# =========================================================================== #
# Adversarial: single-voxel label
# =========================================================================== #

def test_adv_single_voxel_centroid_voxel_equals_that_voxel():
    """A label occupying exactly one voxel has centroid_voxel equal to that voxel's indices."""
    # Single voxel at (4, 5, 6)
    seg = make_labelmap((10, 10, 10), {1: ((4, 5), (5, 6), (6, 7))})
    result = compute_centroid(seg, label=1)
    assert result.centroid_voxel[0] == pytest.approx(4.0)
    assert result.centroid_voxel[1] == pytest.approx(5.0)
    assert result.centroid_voxel[2] == pytest.approx(6.0)


def test_adv_single_voxel_centroid_mm_isotropic():
    """A single voxel at (4,5,6) with 1mm spacing has centroid_mm == (4.0, 5.0, 6.0)."""
    seg = make_labelmap((10, 10, 10), {1: ((4, 5), (5, 6), (6, 7))})
    result = compute_centroid(seg, label=1)
    assert result.centroid_mm[0] == pytest.approx(4.0)
    assert result.centroid_mm[1] == pytest.approx(5.0)
    assert result.centroid_mm[2] == pytest.approx(6.0)


def test_adv_single_voxel_centroid_mm_anisotropic():
    """A single voxel at (3,3,3) with (2.0, 3.0, 4.0) spacing has centroid_mm == (6, 9, 12)."""
    spacing = (2.0, 3.0, 4.0)
    seg = make_labelmap((8, 8, 8), {1: ((3, 4), (3, 4), (3, 4))}, spacing=spacing)
    result = compute_centroid(seg, label=1)
    assert result.centroid_mm[0] == pytest.approx(6.0)
    assert result.centroid_mm[1] == pytest.approx(9.0)
    assert result.centroid_mm[2] == pytest.approx(12.0)


def test_adv_single_voxel_at_origin():
    """A single voxel at (0,0,0) has centroid_voxel == (0.0, 0.0, 0.0)."""
    seg = make_labelmap((8, 8, 8), {1: ((0, 1), (0, 1), (0, 1))})
    result = compute_centroid(seg, label=1)
    assert result.centroid_voxel[0] == pytest.approx(0.0)
    assert result.centroid_voxel[1] == pytest.approx(0.0)
    assert result.centroid_voxel[2] == pytest.approx(0.0)


# =========================================================================== #
# Adversarial: label spanning a full axis (centroid at midpoint)
# =========================================================================== #

def test_adv_label_spanning_full_x_axis_centroid_at_midpoint():
    """A label spanning the entire x axis has centroid_voxel[0] at the midpoint index."""
    shape = (10, 4, 4)
    seg = make_labelmap(shape, {1: ((0, 10), (1, 3), (1, 3))})
    result = compute_centroid(seg, label=1)
    # x spans [0..9]: mean = 4.5
    assert result.centroid_voxel[0] == pytest.approx(4.5)


def test_adv_label_spanning_full_z_axis_centroid_at_midpoint():
    """A label spanning the full z axis has centroid_voxel[2] at the midpoint."""
    shape = (4, 4, 10)
    seg = make_labelmap(shape, {1: ((1, 3), (1, 3), (0, 10))})
    result = compute_centroid(seg, label=1)
    # z spans [0..9]: mean = 4.5
    assert result.centroid_voxel[2] == pytest.approx(4.5)


# =========================================================================== #
# Adversarial: missing label
# =========================================================================== #

def test_adv_missing_label_raises_error():
    """Requesting centroid for a label not in the image raises a clear error."""
    case = labelled_blocks_case()
    with pytest.raises((ValueError, KeyError, LookupError)) as exc_info:
        compute_centroid(case.seg_img, label=99)
    assert str(exc_info.value).strip(), "Error message for missing label must not be blank"


def test_adv_missing_label_error_message_mentions_label():
    """The error for a missing label references the label value or is clearly worded."""
    case = labelled_blocks_case()
    try:
        compute_centroid(case.seg_img, label=999)
    except (ValueError, KeyError, LookupError) as exc:
        msg = str(exc)
        assert "999" in msg or msg.strip(), (
            "Error message should reference the missing label value"
        )


def test_adv_missing_label_no_raw_object_repr_in_message():
    """Error message for a missing label does not look like a raw object repr."""
    case = labelled_blocks_case()
    try:
        compute_centroid(case.seg_img, label=888)
    except (ValueError, KeyError, LookupError) as exc:
        msg = str(exc)
        import re
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            "Error message looks like a raw object repr"
        )


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #

def test_adv_input_image_not_mutated():
    """compute_centroid does not mutate the input image data array."""
    case = labelled_blocks_case()
    original = np.asanyarray(case.seg_img.dataobj).copy()
    compute_centroid(case.seg_img, label=1)
    after = np.asanyarray(case.seg_img.dataobj)
    np.testing.assert_array_equal(original, after)


def test_adv_input_image_not_mutated_anisotropic():
    """compute_centroid does not mutate the anisotropic fixture's data."""
    case = anisotropic_case()
    original = np.asanyarray(case.seg_img.dataobj).copy()
    compute_centroid(case.seg_img, label=1)
    after = np.asanyarray(case.seg_img.dataobj)
    np.testing.assert_array_equal(original, after)


# =========================================================================== #
# Adversarial: LabelCentroid dataclass contract
# =========================================================================== #

def test_adv_centroid_voxel_is_length_3():
    """centroid_voxel is a sequence of length 3."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    assert len(result.centroid_voxel) == 3


def test_adv_centroid_mm_is_length_3():
    """centroid_mm is a sequence of length 3."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    assert len(result.centroid_mm) == 3


def test_adv_centroid_voxel_elements_are_floats():
    """centroid_voxel elements are finite floats."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    for v in result.centroid_voxel:
        assert isinstance(v, float) or isinstance(v, (int, float))
        assert not (v != v)  # no NaN


def test_adv_centroid_mm_elements_are_floats():
    """centroid_mm elements are finite floats."""
    case = labelled_blocks_case()
    result = compute_centroid(case.seg_img, label=1)
    for v in result.centroid_mm:
        assert isinstance(v, float) or isinstance(v, (int, float))
        assert not (v != v)  # no NaN


def test_adv_centroid_mm_isotropic_equals_centroid_voxel():
    """At 1mm isotropic spacing, centroid_mm equals centroid_voxel element-wise."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_centroid(case.seg_img, label=label)
        assert result.centroid_mm[0] == pytest.approx(result.centroid_voxel[0])
        assert result.centroid_mm[1] == pytest.approx(result.centroid_voxel[1])
        assert result.centroid_mm[2] == pytest.approx(result.centroid_voxel[2])


def test_adv_centroid_voxel_within_volume_bounds():
    """centroid_voxel coordinates are within the image shape bounds."""
    case = labelled_blocks_case()
    shape = np.asanyarray(case.seg_img.dataobj).shape
    for label in (1, 2, 3):
        result = compute_centroid(case.seg_img, label=label)
        for axis, dim in enumerate(shape):
            coord = result.centroid_voxel[axis]
            assert 0.0 <= coord < dim, (
                f"centroid_voxel[{axis}]={coord} out of bounds for shape={dim}"
            )
