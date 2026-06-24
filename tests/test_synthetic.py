"""Contract tests for the synthetic NIfTI fixture builders (item 002).

These assert the builders' *own* contract — shape, dtype, label set, per-label
voxel counts, affine/spacing, on-disk round-trip and determinism. Validation
deliberately uses ``nibabel.load`` directly (not the future ``segqc`` loader),
so this item is self-contained and does not pre-empt item 003's design.
"""

from __future__ import annotations

import numpy as np
import nibabel as nib
import pytest

import synthetic
from synthetic import (
    LABEL_DTYPE,
    SCAN_DTYPE,
    affine_from_spacing,
    anisotropic_case,
    empty_case,
    labelled_blocks_case,
    make_labelmap,
    write_nifti,
)


def _zooms(img: nib.Nifti1Image):
    """Voxel spacing recovered from the image header zooms."""
    return tuple(float(z) for z in img.header.get_zooms()[:3])


def test_affine_encodes_spacing():
    """`affine_from_spacing((1,1,3))` puts the voxel sizes on the diagonal."""
    affine = affine_from_spacing((1.0, 1.0, 3.0))
    assert affine.shape == (4, 4)
    assert np.allclose(np.diag(affine), [1.0, 1.0, 3.0, 1.0])
    # Pure scaling: off-diagonal (rotation) block is zero.
    rotation = affine[:3, :3] - np.diag(np.diag(affine[:3, :3]))
    assert np.allclose(rotation, 0.0)
    assert np.allclose(affine[:3, 3], 0.0)  # zero origin


def test_labelled_blocks_shape_and_labels():
    """Labelled-blocks case has expected shape, label set, and voxel counts."""
    case = labelled_blocks_case()
    seg = np.asanyarray(case.seg_img.dataobj)

    assert seg.shape == (16, 16, 16)
    assert seg.dtype == LABEL_DTYPE
    assert case.scan_img.shape == (16, 16, 16)
    assert np.asanyarray(case.scan_img.dataobj).dtype == SCAN_DTYPE

    # >=3 distinct foreground labels.
    assert case.expected_labels == {1, 2, 3}
    assert len(case.expected_labels) >= 3

    # Each block is 4*4*4 = 64 voxels (hand-computed from the box definitions).
    assert case.voxel_counts == {1: 64, 2: 64, 3: 64}
    # Metadata matches the actual array.
    observed = {
        int(lbl): int(cnt)
        for lbl, cnt in zip(*np.unique(seg, return_counts=True))
        if lbl != 0
    }
    assert observed == case.voxel_counts


def test_empty_case_has_no_foreground():
    """The empty label map is all zeros — no foreground labels."""
    case = empty_case()
    seg = np.asanyarray(case.seg_img.dataobj)
    assert seg.max() == 0
    assert set(np.unique(seg)) == {0}
    assert case.expected_labels == frozenset()
    assert case.voxel_counts == {}


def test_anisotropic_spacing_roundtrip():
    """Spacing recovered from the header matches the requested anisotropy."""
    case = anisotropic_case()
    assert case.spacing == (1.0, 1.0, 3.0)
    assert _zooms(case.seg_img) == pytest.approx((1.0, 1.0, 3.0))
    assert _zooms(case.scan_img) == pytest.approx((1.0, 1.0, 3.0))
    # Affine diagonal also reflects the spacing.
    assert np.allclose(np.diag(case.seg_img.affine)[:3], [1.0, 1.0, 3.0])
    # The case has foreground (two 48-voxel blocks).
    assert case.voxel_counts == {1: 48, 2: 48}


@pytest.mark.parametrize("suffix", [".nii", ".nii.gz"])
def test_on_disk_roundtrip(tmp_path, suffix):
    """Write a fixture, reload via nibabel, assert array + affine equality."""
    case = anisotropic_case()
    seg_path = write_nifti(case.seg_img, tmp_path / f"seg{suffix}")
    assert seg_path.exists()

    reloaded = nib.load(str(seg_path))
    np.testing.assert_array_equal(
        np.asanyarray(reloaded.dataobj), np.asanyarray(case.seg_img.dataobj)
    )
    np.testing.assert_allclose(reloaded.affine, case.seg_img.affine)
    assert np.asanyarray(reloaded.dataobj).dtype == LABEL_DTYPE


def test_case_write_helper_round_trips(tmp_path):
    """`SyntheticCase.write` produces a loadable scan+seg pair."""
    case = labelled_blocks_case()
    scan_path, seg_path = case.write(tmp_path)
    assert scan_path.exists() and seg_path.exists()
    seg = nib.load(str(seg_path))
    np.testing.assert_array_equal(
        np.asanyarray(seg.dataobj), np.asanyarray(case.seg_img.dataobj)
    )


def test_determinism():
    """Building the same case twice yields byte-for-byte equal arrays."""
    a = labelled_blocks_case()
    b = labelled_blocks_case()
    np.testing.assert_array_equal(
        np.asanyarray(a.seg_img.dataobj), np.asanyarray(b.seg_img.dataobj)
    )
    np.testing.assert_array_equal(
        np.asanyarray(a.scan_img.dataobj), np.asanyarray(b.scan_img.dataobj)
    )
    np.testing.assert_array_equal(a.scan_img.affine, b.scan_img.affine)


def test_make_labelmap_overlap_last_wins():
    """Documented overlap semantics: later block overwrites earlier."""
    img = make_labelmap(
        (8, 8, 8),
        {1: ((0, 4), (0, 4), (0, 4)), 2: ((2, 6), (2, 6), (2, 6))},
    )
    data = np.asanyarray(img.dataobj)
    # The overlap region (2:4, 2:4, 2:4) must carry label 2.
    assert np.all(data[2:4, 2:4, 2:4] == 2)


def test_conftest_in_memory_fixtures(labelled_blocks, empty_labelmap, anisotropic):
    """The conftest pytest-fixture layer yields the expected case bundles."""
    assert labelled_blocks.expected_labels == {1, 2, 3}
    assert empty_labelmap.expected_labels == frozenset()
    assert anisotropic.spacing == (1.0, 1.0, 3.0)


def test_conftest_on_disk_fixtures(labelled_blocks_files):
    """The `*_files` fixtures write loadable NIfTI files under tmp_path."""
    scan_path, seg_path = labelled_blocks_files
    assert scan_path.exists() and seg_path.exists()
    seg = nib.load(str(seg_path))
    observed = {
        int(lbl): int(cnt)
        for lbl, cnt in zip(*np.unique(np.asanyarray(seg.dataobj), return_counts=True))
        if lbl != 0
    }
    assert observed == {1: 64, 2: 64, 3: 64}


def test_canonical_registry_covers_all_cases():
    """The registry exposes exactly the three canonical builders."""
    assert set(synthetic.CANONICAL_CASES) == {
        "labelled_blocks",
        "empty",
        "anisotropic",
    }
    for name, builder in synthetic.CANONICAL_CASES.items():
        case = builder()
        assert isinstance(case, synthetic.SyntheticCase)
        assert case.shape == (16, 16, 16)
