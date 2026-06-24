"""Unit tests for the NIfTI loader (item 003).

Per the item's *Fixture dependency* note, these tests build tiny NIfTI volumes
inline with NiBabel + NumPy and write them to pytest's ``tmp_path`` — they do
**not** depend on the canonical fixture builder (item 002, parallel branch). A
follow-up may migrate these onto the shared builder once item 002 merges.
"""

from __future__ import annotations

import numpy as np
import nibabel as nib
import pytest

from segqc.io import (
    Case,
    SegQCInputError,
    Volume,
    load_case,
    load_volume,
)


def _write_nii(tmp_path, data, spacing, *, name="vol.nii.gz", affine=None):
    """Write ``data`` to a NIfTI file under ``tmp_path`` and return the path.

    Spacing is encoded as a diagonal affine unless an explicit ``affine`` is
    given. Returns the path as a ``str``.
    """
    if affine is None:
        affine = np.diag([*spacing, 1.0]).astype(float)
    p = tmp_path / name
    nib.save(nib.Nifti1Image(data, affine), str(p))
    return str(p)


# --------------------------------------------------------------------------- #
# Shape / dtype
# --------------------------------------------------------------------------- #

def test_load_volume_shape_dtype_scan(tmp_path):
    """A scan loads with its shape preserved and float dtype (get_fdata)."""
    data = np.arange(2 * 3 * 4, dtype=np.float32).reshape(2, 3, 4)
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path)

    assert isinstance(vol, Volume)
    assert vol.data.shape == (2, 3, 4)
    assert np.issubdtype(vol.data.dtype, np.floating)
    assert vol.path == path


def test_load_volume_label_map_integer_dtype(tmp_path):
    """A label map loaded with integer_labels stays integer (not float cast)."""
    data = np.zeros((4, 4, 4), dtype=np.int16)
    data[0, 0, 0] = 5
    data[1, 1, 1] = 23
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path, integer_labels=True)

    assert np.issubdtype(vol.data.dtype, np.integer)
    assert vol.data.shape == (4, 4, 4)
    # Values are preserved exactly.
    assert vol.data[0, 0, 0] == 5
    assert vol.data[1, 1, 1] == 23


# --------------------------------------------------------------------------- #
# Spacing (isotropic + anisotropic) and affine
# --------------------------------------------------------------------------- #

def test_spacing_isotropic(tmp_path):
    """Isotropic (1,1,1) spacing is read back exactly."""
    data = np.zeros((3, 3, 3), dtype=np.float32)
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path)

    assert vol.spacing == pytest.approx((1.0, 1.0, 1.0))
    assert all(isinstance(s, float) for s in vol.spacing)


def test_spacing_anisotropic(tmp_path):
    """Anisotropic (0.5, 0.5, 3.0) spacing is read back exactly."""
    data = np.zeros((3, 3, 3), dtype=np.float32)
    path = _write_nii(tmp_path, data, (0.5, 0.5, 3.0))

    vol = load_volume(path)

    assert vol.spacing == pytest.approx((0.5, 0.5, 3.0))


def test_affine_preserved(tmp_path):
    """The loaded affine equals the written affine within float tolerance."""
    affine = np.array(
        [
            [0.0, 0.0, 3.0, -10.0],
            [0.5, 0.0, 0.0, 20.0],
            [0.0, 0.5, 0.0, -5.0],
            [0.0, 0.0, 0.0, 1.0],
        ]
    )
    data = np.zeros((3, 3, 3), dtype=np.float32)
    path = _write_nii(tmp_path, data, None, affine=affine)

    vol = load_volume(path)

    assert vol.affine.shape == (4, 4)
    assert np.allclose(vol.affine, affine)
    # Spacing derived from the affine (column norms), not assumed isotropic.
    assert vol.spacing == pytest.approx((0.5, 0.5, 3.0))


# --------------------------------------------------------------------------- #
# Label inventory
# --------------------------------------------------------------------------- #

def test_label_inventory(tmp_path):
    """label_inventory yields known {label: count}, background 0 excluded."""
    seg = np.zeros((4, 4, 4), dtype=np.int16)
    # 3 voxels of label 1, 2 voxels of label 7.
    seg[0, 0, 0] = 1
    seg[0, 0, 1] = 1
    seg[0, 0, 2] = 1
    seg[1, 1, 1] = 7
    seg[1, 1, 2] = 7

    scan = np.zeros((4, 4, 4), dtype=np.float32)
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine)

    case = load_case(scan_path, seg_path)

    assert isinstance(case, Case)
    assert case.label_inventory == {1: 3, 7: 2}
    assert 0 not in case.label_inventory
    assert case.foreground_voxels == 5
    # Inventory keys are plain ints, ordered ascending.
    assert list(case.label_inventory.keys()) == [1, 7]
    assert all(isinstance(k, int) for k in case.label_inventory)


def test_label_inventory_empty_segmentation(tmp_path):
    """An all-zero segmentation yields an empty inventory and 0 foreground."""
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine)

    case = load_case(scan_path, seg_path)

    assert case.label_inventory == {}
    assert case.foreground_voxels == 0


# --------------------------------------------------------------------------- #
# load_case success + compatibility
# --------------------------------------------------------------------------- #

def test_load_case_success(tmp_path):
    """A matching scan/seg pair loads into a Case with float scan + int seg."""
    affine = np.diag([0.5, 0.5, 3.0, 1.0])
    scan = np.ones((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    seg[0, 0, 0] = 1
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine)

    case = load_case(scan_path, seg_path)

    assert np.issubdtype(case.scan.data.dtype, np.floating)
    assert np.issubdtype(case.seg.data.dtype, np.integer)
    assert case.scan.spacing == pytest.approx((0.5, 0.5, 3.0))
    assert case.seg.spacing == pytest.approx((0.5, 0.5, 3.0))


def test_load_case_tolerant_affine(tmp_path):
    """Tiny float differences in the affine are tolerated (no error)."""
    affine_scan = np.diag([1.0, 1.0, 1.0, 1.0])
    affine_seg = affine_scan.copy()
    affine_seg[0, 0] += 1e-6  # well within tolerance
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine_scan)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine_seg)

    case = load_case(scan_path, seg_path)  # must not raise
    assert isinstance(case, Case)


def test_load_case_incompatible_affine_raises(tmp_path):
    """A meaningfully different affine raises SegQCInputError."""
    affine_scan = np.diag([1.0, 1.0, 1.0, 1.0])
    affine_seg = np.diag([2.0, 1.0, 1.0, 1.0])  # different spacing
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 3), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine_scan)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine_seg)

    with pytest.raises(SegQCInputError, match="incompatible affines"):
        load_case(scan_path, seg_path)


# --------------------------------------------------------------------------- #
# Error paths
# --------------------------------------------------------------------------- #

def test_load_case_shape_mismatch_raises(tmp_path):
    """Differing scan/seg shapes raise SegQCInputError naming both shapes."""
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    scan = np.zeros((3, 3, 3), dtype=np.float32)
    seg = np.zeros((3, 3, 4), dtype=np.int16)
    scan_path = _write_nii(tmp_path, scan, None, name="scan.nii.gz", affine=affine)
    seg_path = _write_nii(tmp_path, seg, None, name="seg.nii.gz", affine=affine)

    with pytest.raises(SegQCInputError) as exc_info:
        load_case(scan_path, seg_path)

    msg = str(exc_info.value)
    assert "(3, 3, 3)" in msg
    assert "(3, 3, 4)" in msg


def test_missing_file_raises(tmp_path):
    """A nonexistent path raises SegQCInputError naming the path."""
    missing = str(tmp_path / "does_not_exist.nii.gz")

    with pytest.raises(SegQCInputError) as exc_info:
        load_volume(missing)

    assert missing in str(exc_info.value)


def test_directory_path_raises(tmp_path):
    """A directory passed as a path raises a clear SegQCInputError."""
    with pytest.raises(SegQCInputError, match="directory"):
        load_volume(str(tmp_path))


def test_malformed_file_raises(tmp_path):
    """A non-NIfTI file renamed .nii.gz raises a wrapped SegQCInputError."""
    bogus = tmp_path / "not_really.nii.gz"
    bogus.write_text("this is plain text, not a NIfTI image")

    with pytest.raises(SegQCInputError) as exc_info:
        load_volume(str(bogus))

    # The wrapped error names the offending path; no raw nibabel error leaks.
    assert str(bogus) in str(exc_info.value)


# --------------------------------------------------------------------------- #
# Immutability / no caller-array mutation
# --------------------------------------------------------------------------- #

def test_volume_is_frozen(tmp_path):
    """Volume is an immutable (frozen) dataclass."""
    import dataclasses

    data = np.zeros((2, 2, 2), dtype=np.float32)
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))
    vol = load_volume(path)

    with pytest.raises(dataclasses.FrozenInstanceError):
        vol.spacing = (2.0, 2.0, 2.0)  # type: ignore[misc]


def test_returned_array_owns_its_data(tmp_path):
    """The returned array is a standalone copy, safe to read/own."""
    data = np.arange(8, dtype=np.int16).reshape(2, 2, 2)
    path = _write_nii(tmp_path, data, (1.0, 1.0, 1.0))

    vol = load_volume(path, integer_labels=True)

    assert vol.data.flags.owndata