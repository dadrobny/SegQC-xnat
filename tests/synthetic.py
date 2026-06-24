"""Synthetic NIfTI fixture builders (item 002).

This module is the project's **shared, framework-agnostic** test-data substrate.
It builds tiny, fully-deterministic NIfTI volumes — a *scan* (intensity volume)
and an *instance label map* (integer-labelled volume) — with caller-controllable
shape, voxel spacing, and label layout. Every later test-driven item (the NIfTI
loader, label convention, CLI wiring, empty detection, verdict/report, …) is
expected to build its tests on top of these helpers rather than re-inventing
throwaway test data.

Design notes / scope (see ``docs/aide/items/002-test-harness-fixtures.md``):

* **Plain functions, no pytest import** — so the builders can be called from
  ad-hoc scripts and docs as well as from ``conftest.py`` fixtures. The
  pytest-fixture layer lives in ``tests/conftest.py``.
* **Well-formed, happy-path volumes only.** The deliberately-broken cases that
  exercise failure modes are the Stage 5 synthetic *failure* corpus and are out
  of scope here. The one exception is a single *empty* label map, included
  because Stage 1 (empty detection) needs it.
* **Simple diagonal affine** (identity rotation, zero origin, voxel sizes on the
  diagonal). Faithful real-world / oblique affine handling is item 003's
  concern; these fixtures intentionally do not cover rotated affines.
* **Deterministic** — content is computed, never random; building the same case
  twice yields byte-for-byte equal arrays. No network, no external services.

Quick start (``tests/`` is on ``sys.path`` during a pytest run, so import the
module bare)::

    from synthetic import labelled_blocks_case, write_nifti

    case = labelled_blocks_case()
    case.scan_img            # nibabel.Nifti1Image (intensity volume)
    case.seg_img             # nibabel.Nifti1Image (uint16 label map)
    case.expected_labels     # e.g. {1, 2, 3}
    case.voxel_counts        # {label: n_voxels}, hand-verifiable
    case.spacing             # (sx, sy, sz) in mm

    seg_path = write_nifti(case.seg_img, tmp_path / "seg.nii.gz")

The pytest fixtures in ``conftest.py`` (``labelled_blocks``, ``empty_labelmap``,
``anisotropic_case_fixture`` and their ``*_files`` on-disk variants) simply wrap
these builders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Sequence, Tuple

import numpy as np
import nibabel as nib

# Public dtype conventions (documented in the item's Decisions & Trade-offs):
#   * label maps  -> uint16  (ample range for instance labels, unambiguously
#     integral, matches the unsigned label maps real tools emit).
#   * scans       -> int16   (typical CT-like intensity range).
LABEL_DTYPE = np.uint16
SCAN_DTYPE = np.int16

# A "tiny but roomy enough for >=3 non-touching blocks" default volume size.
DEFAULT_SHAPE: Tuple[int, int, int] = (16, 16, 16)

Spacing = Tuple[float, float, float]
# A block is an axis-aligned box given as ((x0, x1), (y0, y1), (z0, z1)) using
# Python half-open ranges (x0 inclusive, x1 exclusive), i.e. numpy slice bounds.
Box = Tuple[Tuple[int, int], Tuple[int, int], Tuple[int, int]]


def affine_from_spacing(spacing: Spacing) -> np.ndarray:
    """Return a 4x4 affine with ``spacing`` voxel sizes on the diagonal.

    Identity rotation, zero origin — a deliberately minimal RAS-ish diagonal
    affine. The recovered zooms (``abs`` of the diagonal) equal ``spacing``.
    """
    sx, sy, sz = (float(s) for s in spacing)
    affine = np.diag([sx, sy, sz, 1.0]).astype(np.float64)
    return affine


def make_scan(
    shape: Sequence[int] = DEFAULT_SHAPE,
    spacing: Spacing = (1.0, 1.0, 1.0),
    *,
    dtype: np.dtype = SCAN_DTYPE,
    fill: int = 0,
    gradient: bool = False,
) -> nib.Nifti1Image:
    """Build a deterministic intensity volume as a ``Nifti1Image``.

    With ``gradient=False`` (default) every voxel is ``fill``. With
    ``gradient=True`` the value rises linearly along the first axis (a simple,
    reproducible non-constant texture) — useful when a test needs intensity
    variation. No randomness is involved either way.
    """
    shape = tuple(int(n) for n in shape)
    if gradient:
        # Linear ramp along axis 0, broadcast across the other two axes.
        ramp = np.arange(shape[0], dtype=np.int64).reshape(shape[0], 1, 1)
        data = np.broadcast_to(ramp, shape).astype(dtype) + np.asarray(fill, dtype=dtype)
        data = np.ascontiguousarray(data, dtype=dtype)
    else:
        data = np.full(shape, fill_value=fill, dtype=dtype)
    return nib.Nifti1Image(data, affine_from_spacing(spacing))


def make_labelmap(
    shape: Sequence[int] = DEFAULT_SHAPE,
    blocks: Mapping[int, Box] | None = None,
    spacing: Spacing = (1.0, 1.0, 1.0),
    *,
    dtype: np.dtype = LABEL_DTYPE,
) -> nib.Nifti1Image:
    """Paint integer ``blocks`` into a zero volume and return a ``Nifti1Image``.

    ``blocks`` maps ``label -> ((x0, x1), (y0, y1), (z0, z1))`` half-open boxes.
    Later entries overwrite earlier ones where boxes overlap; the well-formed
    canonical cases use non-overlapping boxes. ``blocks=None`` (or empty) yields
    an all-zero (empty) label map.
    """
    shape = tuple(int(n) for n in shape)
    data = np.zeros(shape, dtype=dtype)
    for label, ((x0, x1), (y0, y1), (z0, z1)) in (blocks or {}).items():
        data[x0:x1, y0:y1, z0:z1] = label
    return nib.Nifti1Image(data, affine_from_spacing(spacing))


def voxel_counts_of(img: nib.Nifti1Image) -> Dict[int, int]:
    """Return ``{label: voxel_count}`` for every non-zero label in a label map."""
    data = np.asanyarray(img.dataobj)
    labels, counts = np.unique(data, return_counts=True)
    return {int(lbl): int(cnt) for lbl, cnt in zip(labels, counts) if lbl != 0}


def write_nifti(img: nib.Nifti1Image, path: str | Path) -> Path:
    """Save ``img`` to ``path`` (``.nii`` or ``.nii.gz``) and return the ``Path``.

    Thin wrapper over :func:`nibabel.save`; NiBabel infers compression from the
    file extension. Used to materialise fixtures under pytest's ``tmp_path``.
    """
    path = Path(path)
    nib.save(img, str(path))
    return path


@dataclass(frozen=True)
class SyntheticCase:
    """A self-describing scan + label-map bundle with known-good metadata.

    Later items assert against these attributes (e.g. ``expected_labels`` /
    ``voxel_counts``) instead of recomputing them, so a case carries its own
    ground truth.
    """

    scan_img: nib.Nifti1Image
    seg_img: nib.Nifti1Image
    expected_labels: frozenset  # set of non-zero integer labels (empty if none)
    voxel_counts: Dict[int, int]  # {label: n_voxels}
    spacing: Spacing
    shape: Tuple[int, int, int]
    description: str = ""
    blocks: Mapping[int, Box] = field(default_factory=dict)

    def write(self, dir_path: str | Path, suffix: str = ".nii.gz") -> Tuple[Path, Path]:
        """Write ``scan``/``seg`` into ``dir_path`` and return ``(scan, seg)`` paths."""
        dir_path = Path(dir_path)
        scan_path = write_nifti(self.scan_img, dir_path / f"scan{suffix}")
        seg_path = write_nifti(self.seg_img, dir_path / f"seg{suffix}")
        return scan_path, seg_path


def _build_case(
    blocks: Mapping[int, Box],
    spacing: Spacing,
    shape: Tuple[int, int, int],
    description: str,
) -> SyntheticCase:
    """Assemble a :class:`SyntheticCase` from a block spec, computing metadata."""
    scan_img = make_scan(shape, spacing, gradient=True)
    seg_img = make_labelmap(shape, blocks, spacing)
    counts = voxel_counts_of(seg_img)
    return SyntheticCase(
        scan_img=scan_img,
        seg_img=seg_img,
        expected_labels=frozenset(counts),
        voxel_counts=counts,
        spacing=spacing,
        shape=shape,
        description=description,
        blocks=dict(blocks),
    )


# --- Canonical cases --------------------------------------------------------
#
# Block layouts are hand-chosen to be non-touching within DEFAULT_SHAPE so the
# per-label voxel counts are trivially verifiable (count = product of box edge
# lengths). Keep these stable: later items pin against the resulting metadata.


def labelled_blocks_case() -> SyntheticCase:
    """>=3 distinct labels as separated rectangular blocks, isotropic spacing.

    Three 4x4x4 = 64-voxel blocks (labels 1, 2, 3) placed apart in a 16^3
    volume at 1 mm isotropic spacing.
    """
    blocks: Dict[int, Box] = {
        1: ((2, 6), (2, 6), (2, 6)),
        2: ((2, 6), (10, 14), (2, 6)),
        3: ((10, 14), (2, 6), (10, 14)),
    }
    return _build_case(
        blocks,
        spacing=(1.0, 1.0, 1.0),
        shape=DEFAULT_SHAPE,
        description="labelled-blocks: 3 separated 4^3 blocks, isotropic 1mm",
    )


def empty_case() -> SyntheticCase:
    """An all-zero label map (no foreground labels) plus a matching scan."""
    return _build_case(
        blocks={},
        spacing=(1.0, 1.0, 1.0),
        shape=DEFAULT_SHAPE,
        description="empty: all-zero label map (no foreground)",
    )


def anisotropic_case() -> SyntheticCase:
    """A labelled volume with non-uniform spacing ``(1.0, 1.0, 3.0)`` mm.

    Two separated blocks (labels 1, 2) so it has foreground; the point of this
    case is the anisotropic affine, which loader/feature items must honour for
    physical-volume computations.
    """
    blocks: Dict[int, Box] = {
        1: ((2, 6), (2, 6), (2, 5)),   # 4*4*3 = 48 voxels
        2: ((9, 13), (9, 13), (8, 11)),  # 4*4*3 = 48 voxels
    }
    return _build_case(
        blocks,
        spacing=(1.0, 1.0, 3.0),
        shape=DEFAULT_SHAPE,
        description="anisotropic: 2 blocks, spacing (1,1,3) mm",
    )


# Registry so callers (and conftest) can iterate the canonical cases by name.
CANONICAL_CASES = {
    "labelled_blocks": labelled_blocks_case,
    "empty": empty_case,
    "anisotropic": anisotropic_case,
}
