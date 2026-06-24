"""NIfTI input/output for ``segqc`` — the in-memory volume model.

This module is the I/O substrate every downstream feature, heuristic, and
report consumer reads from (item 003). It loads a **scan** and an **instance
label map** from NIfTI, preserving spacing/affine and correctly handling
anisotropic voxels, and exposes an immutable in-memory representation.

Scope (item 003): I/O + the volume model only. Anatomical-vertebra naming is
item 004; logging/config is item 005; CLI wiring is item 006; geometric and
intensity features are Stage 2+. This module raises plain
:class:`SegQCInputError` exceptions and exposes only a *raw* label inventory
(label value -> voxel count); it makes no pass/fail judgement.

Public API
----------
``load_volume(path, *, integer_labels=False) -> Volume``
    Load a single NIfTI volume.
``load_case(scan_path, seg_path) -> Case``
    Load a scan + segmentation pair, validate compatibility, and attach the
    label inventory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Tuple, Union

import nibabel as nib
import numpy as np

__all__ = [
    "SegQCInputError",
    "Volume",
    "Case",
    "load_volume",
    "load_case",
]

# Accept str or os.PathLike (e.g. pathlib.Path) anywhere a path is taken.
PathLike = Union[str, "os.PathLike[str]"]

# Tolerance for affine/spacing compatibility in ``load_case``. Real scan/seg
# pairs can carry tiny float differences from header round-tripping; compare
# within an absolute+relative tolerance rather than demanding bit equality.
_AFFINE_ATOL = 1e-4
_AFFINE_RTOL = 1e-5


class SegQCInputError(Exception):
    """Raised when an input scan or segmentation cannot be loaded or is invalid.

    Carries a clear, actionable message (naming the offending path, or the
    mismatched shapes). Raised in place of bare ``OSError``/``FileNotFoundError``
    or NiBabel internals, so callers have a single exception type to catch.
    """


@dataclass(frozen=True)
class Volume:
    """An immutable, in-memory NIfTI volume.

    Attributes
    ----------
    data:
        The voxel array. Float64 for scans (via ``get_fdata``); the header's
        native integer dtype for label maps (``integer_labels=True``).
    spacing:
        Physical voxel sizes ``(sx, sy, sz)``, derived from the affine — not
        assumed isotropic.
    affine:
        The 4x4 voxel-to-world affine, as ``float`` (a copy of
        ``img.affine``).
    path:
        The source file path the volume was loaded from.
    """

    data: np.ndarray
    spacing: Tuple[float, float, float]
    affine: np.ndarray
    path: str


@dataclass(frozen=True)
class Case:
    """A scan + segmentation pair with a raw label inventory.

    Attributes
    ----------
    scan:
        The intensity scan as a float :class:`Volume`.
    seg:
        The instance label map as an integer :class:`Volume`.
    label_inventory:
        Mapping ``{label_value: voxel_count}`` over present **non-zero** labels
        (background ``0`` excluded), sorted by label value. Anatomical naming
        is item 004's concern; this is the raw integer inventory only.
    foreground_voxels:
        Total count of non-zero (foreground) voxels in ``seg`` — the sum of
        ``label_inventory`` values. Exposed for item 007 (empty detection).
    """

    scan: Volume
    seg: Volume
    label_inventory: Dict[int, int]
    foreground_voxels: int


def _spacing_from_affine(affine: np.ndarray) -> Tuple[float, float, float]:
    """Derive physical voxel sizes from the 4x4 affine.

    Uses the column norms of the 3x3 direction/scale block, which equals
    ``nibabel.affines.voxel_sizes``. Returns plain Python floats.
    """
    sizes = nib.affines.voxel_sizes(affine)
    return (float(sizes[0]), float(sizes[1]), float(sizes[2]))


def load_volume(path: PathLike, *, integer_labels: bool = False) -> Volume:
    """Load a single NIfTI volume into an immutable :class:`Volume`.

    Parameters
    ----------
    path:
        Path to a NIfTI file (``.nii`` or ``.nii.gz``).
    integer_labels:
        When ``True``, read the array in the header's native (integer) dtype,
        suitable for label maps — label values are **not** silently cast to
        float. When ``False`` (default), read intensity data as float64 via
        :meth:`nibabel.Nifti1Image.get_fdata`.

    Returns
    -------
    Volume
        With ``data``, affine-derived ``spacing``, the 4x4 ``affine``, and the
        source ``path``.

    Raises
    ------
    SegQCInputError
        If the path does not exist, is a directory, or cannot be read as a
        NIfTI image (the underlying error is wrapped, never leaked).
    """
    path_str = os.fspath(path)

    if not os.path.exists(path_str):
        raise SegQCInputError(f'Input file does not exist: "{path_str}"')
    if os.path.isdir(path_str):
        raise SegQCInputError(f'Input path is a directory, not a file: "{path_str}"')

    try:
        img = nib.load(path_str)
    except Exception as exc:  # nibabel raises ImageFileError, OSError, etc.
        raise SegQCInputError(
            f'Failed to read NIfTI file "{path_str}": {exc}'
        ) from exc

    affine = np.asarray(img.affine, dtype=float)
    spacing = _spacing_from_affine(affine)

    try:
        if integer_labels:
            # Preserve the header's native dtype; round defensively in case the
            # stored dtype is float-typed but holds integral label values, then
            # cast to a signed integer type. Avoids get_fdata()'s float cast.
            raw = np.asarray(img.dataobj)
            if np.issubdtype(raw.dtype, np.floating):
                data = np.rint(raw).astype(np.int64)
            else:
                data = raw.astype(np.int64, copy=True)
        else:
            data = img.get_fdata(dtype=np.float64)
    except Exception as exc:
        raise SegQCInputError(
            f'Failed to read voxel data from "{path_str}": {exc}'
        ) from exc

    # Ensure the returned array is a standalone copy: the caller's arrays must
    # never be mutated, and the data must not be a memmap/view onto the file
    # object. np.array copies a non-owning view.
    if not data.flags.owndata:
        data = np.array(data)

    return Volume(data=data, spacing=spacing, affine=affine, path=path_str)


def _label_inventory(seg_data: np.ndarray) -> Tuple[Dict[int, int], int]:
    """Compute ``{label: voxel_count}`` over non-zero labels, plus foreground total.

    Background (``0``) is excluded from the inventory. The mapping is ordered by
    ascending label value.
    """
    values, counts = np.unique(seg_data, return_counts=True)
    inventory: Dict[int, int] = {}
    foreground = 0
    for value, count in zip(values, counts):
        ivalue = int(value)
        if ivalue == 0:
            continue
        inventory[ivalue] = int(count)
        foreground += int(count)
    return inventory, foreground


def load_case(scan_path: PathLike, seg_path: PathLike) -> Case:
    """Load a scan + segmentation pair and validate their compatibility.

    The scan is loaded as float64; the segmentation is loaded with its native
    integer dtype preserved. The two volumes must share the same array shape
    and a compatible affine/spacing (equal within tolerance); otherwise a
    :class:`SegQCInputError` naming the mismatch is raised. A raw label
    inventory (non-zero labels only) is computed and attached.

    Parameters
    ----------
    scan_path:
        Path to the intensity scan NIfTI.
    seg_path:
        Path to the instance label map NIfTI.

    Returns
    -------
    Case
        With ``scan``, ``seg``, ``label_inventory`` and ``foreground_voxels``.

    Raises
    ------
    SegQCInputError
        On any load failure, on a shape mismatch (message names both shapes),
        or on an incompatible affine (message names the tolerance).
    """
    scan = load_volume(scan_path, integer_labels=False)
    seg = load_volume(seg_path, integer_labels=True)

    if scan.data.shape != seg.data.shape:
        raise SegQCInputError(
            "Scan and segmentation have mismatched shapes: "
            f'scan {scan.data.shape} ("{scan.path}") vs '
            f'segmentation {seg.data.shape} ("{seg.path}").'
        )

    if not np.allclose(scan.affine, seg.affine, rtol=_AFFINE_RTOL, atol=_AFFINE_ATOL):
        raise SegQCInputError(
            "Scan and segmentation have incompatible affines (beyond tolerance "
            f"rtol={_AFFINE_RTOL}, atol={_AFFINE_ATOL}):\n"
            f'  scan affine ("{scan.path}"):\n{scan.affine}\n'
            f'  segmentation affine ("{seg.path}"):\n{seg.affine}'
        )

    inventory, foreground = _label_inventory(seg.data)

    return Case(
        scan=scan,
        seg=seg,
        label_inventory=inventory,
        foreground_voxels=foreground,
    )