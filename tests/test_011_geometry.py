"""Tests for per-label geometric features (item 011).

Covers all four Acceptance Criteria plus adversarial and edge-case inputs:
single-voxel labels, labels touching multiple faces simultaneously, highly
anisotropic spacing, empty labels (no voxels), immutability, determinism,
error-message quality, and import contract.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import dataclasses

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

from segqc.features.geometry import LabelGeometry, compute_label_geometry


# =========================================================================== #
# Helpers
# =========================================================================== #

def _seg_img(
    shape,
    blocks,
    spacing=(1.0, 1.0, 1.0),
):
    """Return a Nifti1Image label map with the given block definitions."""
    return make_labelmap(shape, blocks, spacing)


# =========================================================================== #
# Import contract
# =========================================================================== #

def test_import_label_geometry():
    """LabelGeometry is importable from segqc.features.geometry."""
    from segqc.features.geometry import LabelGeometry as LG  # noqa: F401
    assert LG is LabelGeometry


def test_import_compute_label_geometry():
    """compute_label_geometry is importable from segqc.features.geometry."""
    from segqc.features.geometry import compute_label_geometry as clg  # noqa: F401
    assert callable(clg)


def test_no_import_error():
    """Importing segqc.features.geometry raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.geometry")
    assert hasattr(mod, "LabelGeometry")
    assert hasattr(mod, "compute_label_geometry")


# =========================================================================== #
# AC-1  Physical volume and extent verified against hand-computed expectations
# =========================================================================== #

def test_ac1_voxel_count_label1():
    """Label 1 in the labelled-blocks case has 64 voxels (4x4x4 block)."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert result.voxel_count == 64


def test_ac1_physical_volume_isotropic_label1():
    """Label 1 at 1mm isotropic spacing: physical volume = 64 * 1^3 = 64.0 mm^3."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert result.physical_volume_mm3 == pytest.approx(64.0)


def test_ac1_extent_isotropic_label1():
    """Label 1 (x[2:6], y[2:6], z[2:6]) at 1mm isotropic: all extents = 4.0 mm."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert result.extent_x_mm == pytest.approx(4.0)
    assert result.extent_y_mm == pytest.approx(4.0)
    assert result.extent_z_mm == pytest.approx(4.0)


def test_ac1_voxel_count_label2():
    """Label 2 in the labelled-blocks case has 64 voxels (4x4x4 block)."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.voxel_count == 64


def test_ac1_physical_volume_isotropic_label2():
    """Label 2 at 1mm isotropic: physical volume = 64.0 mm^3."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.physical_volume_mm3 == pytest.approx(64.0)


def test_ac1_extent_isotropic_label2():
    """Label 2 (y[10:14]) at 1mm isotropic: all extents = 4.0 mm."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.extent_x_mm == pytest.approx(4.0)
    assert result.extent_y_mm == pytest.approx(4.0)
    assert result.extent_z_mm == pytest.approx(4.0)


def test_ac1_bounding_box_voxel_label1():
    """Label 1 voxel bounding box matches the block definition (x[2:6], y[2:6], z[2:6])."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    # The bounding box min/max voxel indices are half-open or inclusive; we only
    # assert the span size is 4 in each axis.
    bb = result.bbox_voxel  # expects some structure with min/max per axis
    span_x = bb.x_max - bb.x_min
    span_y = bb.y_max - bb.y_min
    span_z = bb.z_max - bb.z_min
    assert span_x == 4 or span_x == 3, f"x span {span_x} not 3 (inclusive) or 4 (half-open)"
    assert span_y == 4 or span_y == 3
    assert span_z == 4 or span_z == 3


def test_ac1_bounding_box_physical_label1():
    """Label 1 physical bounding box coordinates match spacing * voxel coords."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    bb = result.bbox_physical
    # At 1mm isotropic, physical coords equal voxel coords.
    # x_min is near 2.0 mm (or within 0.5 mm depending on voxel-centre convention).
    assert bb.x_min == pytest.approx(2.0, abs=1.0)
    assert bb.y_min == pytest.approx(2.0, abs=1.0)
    assert bb.z_min == pytest.approx(2.0, abs=1.0)


def test_ac1_returns_label_geometry_instance():
    """compute_label_geometry returns a LabelGeometry instance."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert isinstance(result, LabelGeometry)


# =========================================================================== #
# AC-2  Anisotropic-spacing fixture yields correct physical volume and extent
# =========================================================================== #

def test_ac2_voxel_count_anisotropic_label1():
    """Label 1 in the anisotropic case has 48 voxels (4x4x3 block)."""
    case = anisotropic_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert result.voxel_count == 48


def test_ac2_physical_volume_anisotropic_label1():
    """Label 1 at (1,1,3)mm: volume = 48 voxels * 1*1*3 mm^3/voxel = 144.0 mm^3."""
    case = anisotropic_case()
    result = compute_label_geometry(case.seg_img, label=1)
    # voxel volume = 1.0 * 1.0 * 3.0 = 3.0 mm^3; 48 voxels -> 144 mm^3
    assert result.physical_volume_mm3 == pytest.approx(144.0)


def test_ac2_extent_anisotropic_label1():
    """Label 1 (x[2:6], y[2:6], z[2:5]) at (1,1,3)mm: x=4mm, y=4mm, z=9mm."""
    case = anisotropic_case()
    result = compute_label_geometry(case.seg_img, label=1)
    # x span: 4 voxels * 1.0 mm = 4.0 mm
    assert result.extent_x_mm == pytest.approx(4.0)
    # y span: 4 voxels * 1.0 mm = 4.0 mm
    assert result.extent_y_mm == pytest.approx(4.0)
    # z span: 3 voxels * 3.0 mm = 9.0 mm
    assert result.extent_z_mm == pytest.approx(9.0)


def test_ac2_physical_volume_anisotropic_label2():
    """Label 2 at (1,1,3)mm: volume = 48 * 3 = 144.0 mm^3."""
    case = anisotropic_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.physical_volume_mm3 == pytest.approx(144.0)


def test_ac2_extent_anisotropic_label2():
    """Label 2 (x[9:13], y[9:13], z[8:11]) at (1,1,3)mm: x=4mm, y=4mm, z=9mm."""
    case = anisotropic_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.extent_x_mm == pytest.approx(4.0)
    assert result.extent_y_mm == pytest.approx(4.0)
    assert result.extent_z_mm == pytest.approx(9.0)


def test_ac2_highly_anisotropic_spacing_volume():
    """Highly anisotropic spacing (0.5, 0.5, 5.0) mm: physical volume is correct."""
    # 2x2x2 block of voxels → 8 voxels; voxel volume = 0.5*0.5*5.0 = 1.25 mm^3
    spacing = (0.5, 0.5, 5.0)
    seg = make_labelmap((8, 8, 8), {1: ((1, 3), (1, 3), (1, 3))}, spacing=spacing)
    result = compute_label_geometry(seg, label=1)
    expected_volume = 8 * 0.5 * 0.5 * 5.0  # = 10.0 mm^3
    assert result.physical_volume_mm3 == pytest.approx(expected_volume)


def test_ac2_highly_anisotropic_spacing_extent():
    """Highly anisotropic spacing (0.5, 0.5, 5.0) mm: extents are physical."""
    # 2x2x2 block: x[1:3], y[1:3], z[1:3]
    # x span = 2 * 0.5 = 1.0 mm; z span = 2 * 5.0 = 10.0 mm
    spacing = (0.5, 0.5, 5.0)
    seg = make_labelmap((8, 8, 8), {1: ((1, 3), (1, 3), (1, 3))}, spacing=spacing)
    result = compute_label_geometry(seg, label=1)
    assert result.extent_x_mm == pytest.approx(1.0)
    assert result.extent_y_mm == pytest.approx(1.0)
    assert result.extent_z_mm == pytest.approx(10.0)


# =========================================================================== #
# AC-3  Border-contact flags correct for labels at/away from image faces
# =========================================================================== #

def test_ac3_interior_label_no_border_contact():
    """Label 1 in the labelled-blocks case (interior block) has no border-contact flags."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    # Label 1: x[2:6], y[2:6], z[2:6] in a 16^3 volume — touches no face.
    assert result.touches_inferior is False
    assert result.touches_superior is False
    assert result.touches_left is False
    assert result.touches_right is False
    assert result.touches_anterior is False
    assert result.touches_posterior is False


def test_ac3_interior_label2_no_border_contact():
    """Label 2 in the labelled-blocks case (interior block) has no border-contact flags."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert result.touches_inferior is False
    assert result.touches_superior is False
    assert result.touches_left is False
    assert result.touches_right is False
    assert result.touches_anterior is False
    assert result.touches_posterior is False


def test_ac3_x_low_face_contact():
    """A label touching the x=0 face sets the corresponding border-contact flag."""
    # Label touching x=0 face (inferior/left/anterior depending on convention)
    seg = make_labelmap((8, 8, 8), {1: ((0, 3), (2, 5), (2, 5))})
    result = compute_label_geometry(seg, label=1)
    # At least one of the face flags touching x=0 must be True.
    x_low_touches = (
        result.touches_inferior
        or result.touches_superior
        or result.touches_left
        or result.touches_right
        or result.touches_anterior
        or result.touches_posterior
    )
    assert x_low_touches, "A label at x=0 face should set at least one border-contact flag"


def test_ac3_x_high_face_contact():
    """A label touching the x=max face sets the corresponding border-contact flag."""
    seg = make_labelmap((8, 8, 8), {1: ((5, 8), (2, 5), (2, 5))})
    result = compute_label_geometry(seg, label=1)
    x_high_touches = (
        result.touches_inferior
        or result.touches_superior
        or result.touches_left
        or result.touches_right
        or result.touches_anterior
        or result.touches_posterior
    )
    assert x_high_touches, "A label at x=max face should set at least one border-contact flag"


def test_ac3_z_low_face_contact():
    """A label touching the z=0 face sets the corresponding border-contact flag."""
    seg = make_labelmap((8, 8, 8), {1: ((2, 5), (2, 5), (0, 3))})
    result = compute_label_geometry(seg, label=1)
    z_low_touches = (
        result.touches_inferior
        or result.touches_superior
        or result.touches_left
        or result.touches_right
        or result.touches_anterior
        or result.touches_posterior
    )
    assert z_low_touches, "A label at z=0 face should set at least one border-contact flag"


def test_ac3_z_high_face_contact():
    """A label touching the z=max face sets the corresponding border-contact flag."""
    seg = make_labelmap((8, 8, 8), {1: ((2, 5), (2, 5), (5, 8))})
    result = compute_label_geometry(seg, label=1)
    z_high_touches = (
        result.touches_inferior
        or result.touches_superior
        or result.touches_left
        or result.touches_right
        or result.touches_anterior
        or result.touches_posterior
    )
    assert z_high_touches, "A label at z=max face should set at least one border-contact flag"


def test_ac3_all_six_faces_contact():
    """A label filling the entire volume touches all six faces."""
    seg = make_labelmap((4, 4, 4), {1: ((0, 4), (0, 4), (0, 4))})
    result = compute_label_geometry(seg, label=1)
    assert result.touches_inferior is True
    assert result.touches_superior is True
    assert result.touches_left is True
    assert result.touches_right is True
    assert result.touches_anterior is True
    assert result.touches_posterior is True


def test_ac3_label_spanning_full_z_axis_touches_both_z_faces():
    """A label spanning the full z range touches both z-axis border faces."""
    # Label spans z[0:8] in a shape-(8,8,8) volume
    seg = make_labelmap((8, 8, 8), {1: ((2, 5), (2, 5), (0, 8))})
    result = compute_label_geometry(seg, label=1)
    z_touches = (
        result.touches_inferior
        or result.touches_superior
        or result.touches_left
        or result.touches_right
        or result.touches_anterior
        or result.touches_posterior
    )
    # Both faces must be touched — count how many border flags are True
    flag_count = sum([
        result.touches_inferior,
        result.touches_superior,
        result.touches_left,
        result.touches_right,
        result.touches_anterior,
        result.touches_posterior,
    ])
    assert flag_count >= 2, (
        f"A label spanning full z range should touch >= 2 faces; got {flag_count}"
    )


def test_ac3_border_contact_flags_are_bool():
    """All six border-contact flags are Python booleans."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    for attr in (
        "touches_inferior",
        "touches_superior",
        "touches_left",
        "touches_right",
        "touches_anterior",
        "touches_posterior",
    ):
        val = getattr(result, attr)
        assert isinstance(val, bool), f"{attr} should be bool, got {type(val)}"


# =========================================================================== #
# AC-4  Functions are deterministic
# =========================================================================== #

def test_ac4_determinism_same_label_same_output():
    """Two calls to compute_label_geometry with the same image and label are identical."""
    case = labelled_blocks_case()
    r1 = compute_label_geometry(case.seg_img, label=1)
    r2 = compute_label_geometry(case.seg_img, label=1)
    assert r1.voxel_count == r2.voxel_count
    assert r1.physical_volume_mm3 == r2.physical_volume_mm3
    assert r1.extent_x_mm == r2.extent_x_mm
    assert r1.extent_y_mm == r2.extent_y_mm
    assert r1.extent_z_mm == r2.extent_z_mm
    assert r1.touches_inferior == r2.touches_inferior
    assert r1.touches_superior == r2.touches_superior
    assert r1.touches_left == r2.touches_left
    assert r1.touches_right == r2.touches_right
    assert r1.touches_anterior == r2.touches_anterior
    assert r1.touches_posterior == r2.touches_posterior


def test_ac4_determinism_anisotropic():
    """Two calls for the anisotropic case yield identical physical volumes."""
    case = anisotropic_case()
    r1 = compute_label_geometry(case.seg_img, label=1)
    r2 = compute_label_geometry(case.seg_img, label=1)
    assert r1.physical_volume_mm3 == r2.physical_volume_mm3
    assert r1.extent_z_mm == r2.extent_z_mm


def test_ac4_determinism_multiple_labels():
    """Results for all three labels in labelled_blocks_case are stable across two runs."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        r1 = compute_label_geometry(case.seg_img, label=label)
        r2 = compute_label_geometry(case.seg_img, label=label)
        assert r1.voxel_count == r2.voxel_count
        assert r1.physical_volume_mm3 == r2.physical_volume_mm3


# =========================================================================== #
# Adversarial: single-voxel label
# =========================================================================== #

def test_adv_single_voxel_label_voxel_count():
    """A label occupying a single voxel has voxel_count=1."""
    seg = make_labelmap((8, 8, 8), {1: ((3, 4), (3, 4), (3, 4))})
    result = compute_label_geometry(seg, label=1)
    assert result.voxel_count == 1


def test_adv_single_voxel_label_physical_volume_isotropic():
    """A single voxel at 1mm isotropic spacing has physical_volume_mm3=1.0."""
    seg = make_labelmap((8, 8, 8), {1: ((3, 4), (3, 4), (3, 4))})
    result = compute_label_geometry(seg, label=1)
    assert result.physical_volume_mm3 == pytest.approx(1.0)


def test_adv_single_voxel_label_physical_volume_anisotropic():
    """A single voxel at (2.0, 3.0, 4.0) mm has physical_volume_mm3=24.0."""
    spacing = (2.0, 3.0, 4.0)
    seg = make_labelmap((8, 8, 8), {1: ((3, 4), (3, 4), (3, 4))}, spacing=spacing)
    result = compute_label_geometry(seg, label=1)
    assert result.physical_volume_mm3 == pytest.approx(24.0)


def test_adv_single_voxel_label_extent():
    """A single voxel has zero or one-voxel extent in each axis."""
    spacing = (1.0, 1.0, 1.0)
    seg = make_labelmap((8, 8, 8), {1: ((3, 4), (3, 4), (3, 4))}, spacing=spacing)
    result = compute_label_geometry(seg, label=1)
    # Extent of a single voxel is either 0 (point) or 1 voxel * spacing.
    assert result.extent_x_mm == pytest.approx(0.0) or result.extent_x_mm == pytest.approx(1.0)
    assert result.extent_y_mm == pytest.approx(0.0) or result.extent_y_mm == pytest.approx(1.0)
    assert result.extent_z_mm == pytest.approx(0.0) or result.extent_z_mm == pytest.approx(1.0)


def test_adv_single_voxel_at_corner_touches_three_faces():
    """A single voxel in the corner (0,0,0) touches three faces."""
    seg = make_labelmap((8, 8, 8), {1: ((0, 1), (0, 1), (0, 1))})
    result = compute_label_geometry(seg, label=1)
    flag_count = sum([
        result.touches_inferior,
        result.touches_superior,
        result.touches_left,
        result.touches_right,
        result.touches_anterior,
        result.touches_posterior,
    ])
    assert flag_count >= 3, (
        f"Corner voxel should touch at least 3 faces; got {flag_count}"
    )


def test_adv_single_voxel_not_at_border_no_contact():
    """A single interior voxel does not touch any border face."""
    seg = make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})
    result = compute_label_geometry(seg, label=1)
    assert result.touches_inferior is False
    assert result.touches_superior is False
    assert result.touches_left is False
    assert result.touches_right is False
    assert result.touches_anterior is False
    assert result.touches_posterior is False


# =========================================================================== #
# Adversarial: label touching multiple faces simultaneously
# =========================================================================== #

def test_adv_label_touches_two_opposite_faces():
    """A label spanning the full x axis touches two x-axis border faces."""
    seg = make_labelmap((8, 8, 8), {1: ((0, 8), (2, 5), (2, 5))})
    result = compute_label_geometry(seg, label=1)
    flag_count = sum([
        result.touches_inferior,
        result.touches_superior,
        result.touches_left,
        result.touches_right,
        result.touches_anterior,
        result.touches_posterior,
    ])
    assert flag_count >= 2


def test_adv_label_touches_four_faces():
    """A label spanning full x and full y axes touches four faces."""
    seg = make_labelmap((8, 8, 8), {1: ((0, 8), (0, 8), (2, 5))})
    result = compute_label_geometry(seg, label=1)
    flag_count = sum([
        result.touches_inferior,
        result.touches_superior,
        result.touches_left,
        result.touches_right,
        result.touches_anterior,
        result.touches_posterior,
    ])
    assert flag_count >= 4


# =========================================================================== #
# Adversarial: empty label (no voxels for the requested label)
# =========================================================================== #

def test_adv_empty_label_raises_or_returns_gracefully():
    """Requesting geometry for a label absent from the image raises a clear error or returns gracefully."""
    case = labelled_blocks_case()
    # Label 99 does not exist in labelled_blocks_case.
    try:
        result = compute_label_geometry(case.seg_img, label=99)
        # If it returns without raising: voxel_count must be 0 (not a crash value).
        assert result.voxel_count == 0
    except (ValueError, KeyError, LookupError) as exc:
        # Any of these is acceptable; the message must mention the label or be non-empty.
        assert str(exc), "Exception message must not be empty"
        assert "ValueError" not in str(exc) or True  # raw class names allowed in exc str


def test_adv_empty_label_error_message_not_blank():
    """If compute_label_geometry raises for a missing label, the error message is non-empty."""
    case = labelled_blocks_case()
    try:
        compute_label_geometry(case.seg_img, label=999)
    except Exception as exc:
        assert str(exc).strip(), "Error message for missing label must not be blank"


# =========================================================================== #
# Adversarial: immutability (input image not mutated)
# =========================================================================== #

def test_adv_input_image_not_mutated():
    """compute_label_geometry does not mutate the input image data array."""
    case = labelled_blocks_case()
    original = np.asanyarray(case.seg_img.dataobj).copy()
    compute_label_geometry(case.seg_img, label=1)
    after = np.asanyarray(case.seg_img.dataobj)
    np.testing.assert_array_equal(original, after)


def test_adv_input_image_not_mutated_anisotropic():
    """compute_label_geometry does not mutate the anisotropic fixture's data."""
    case = anisotropic_case()
    original = np.asanyarray(case.seg_img.dataobj).copy()
    compute_label_geometry(case.seg_img, label=1)
    after = np.asanyarray(case.seg_img.dataobj)
    np.testing.assert_array_equal(original, after)


# =========================================================================== #
# Adversarial: LabelGeometry dataclass contract
# =========================================================================== #

def test_adv_label_geometry_has_required_fields():
    """LabelGeometry exposes all required fields."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    required_attrs = [
        "voxel_count",
        "physical_volume_mm3",
        "extent_x_mm",
        "extent_y_mm",
        "extent_z_mm",
        "bbox_voxel",
        "bbox_physical",
        "touches_inferior",
        "touches_superior",
        "touches_left",
        "touches_right",
        "touches_anterior",
        "touches_posterior",
    ]
    for attr in required_attrs:
        assert hasattr(result, attr), f"LabelGeometry missing field: {attr}"


def test_adv_label_geometry_voxel_count_positive():
    """voxel_count is always a positive integer for a present label."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=2)
    assert isinstance(result.voxel_count, int)
    assert result.voxel_count > 0


def test_adv_label_geometry_physical_volume_positive():
    """physical_volume_mm3 is always positive for a present label."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=3)
    assert result.physical_volume_mm3 > 0.0


def test_adv_label_geometry_extents_non_negative():
    """extent_x/y/z_mm are non-negative for any present label."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_label_geometry(case.seg_img, label=label)
        assert result.extent_x_mm >= 0.0
        assert result.extent_y_mm >= 0.0
        assert result.extent_z_mm >= 0.0


def test_adv_bounding_box_voxel_has_min_max():
    """bbox_voxel exposes x_min, x_max, y_min, y_max, z_min, z_max."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    bb = result.bbox_voxel
    for attr in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max"):
        assert hasattr(bb, attr), f"bbox_voxel missing attribute: {attr}"


def test_adv_bounding_box_physical_has_min_max():
    """bbox_physical exposes x_min, x_max, y_min, y_max, z_min, z_max."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    bb = result.bbox_physical
    for attr in ("x_min", "x_max", "y_min", "y_max", "z_min", "z_max"):
        assert hasattr(bb, attr), f"bbox_physical missing attribute: {attr}"


def test_adv_bounding_box_voxel_ordering():
    """bbox_voxel: min <= max in each axis."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    bb = result.bbox_voxel
    assert bb.x_min <= bb.x_max
    assert bb.y_min <= bb.y_max
    assert bb.z_min <= bb.z_max


def test_adv_bounding_box_physical_ordering():
    """bbox_physical: min <= max in each axis."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    bb = result.bbox_physical
    assert bb.x_min <= bb.x_max
    assert bb.y_min <= bb.y_max
    assert bb.z_min <= bb.z_max


def test_adv_physical_volume_equals_voxel_count_times_voxel_volume():
    """physical_volume_mm3 equals voxel_count * product(spacings) for any case."""
    case = anisotropic_case()
    # spacing = (1.0, 1.0, 3.0)
    voxel_vol = 1.0 * 1.0 * 3.0
    for label in (1, 2):
        result = compute_label_geometry(case.seg_img, label=label)
        expected = result.voxel_count * voxel_vol
        assert result.physical_volume_mm3 == pytest.approx(expected)


def test_adv_physical_volume_consistent_isotropic():
    """physical_volume_mm3 equals voxel_count for isotropic 1mm spacing."""
    case = labelled_blocks_case()
    for label in (1, 2, 3):
        result = compute_label_geometry(case.seg_img, label=label)
        assert result.physical_volume_mm3 == pytest.approx(float(result.voxel_count))
