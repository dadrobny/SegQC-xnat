"""Centre-of-mass (centroid) per vertebra label (item 013).

Given a NIfTI instance label map and a target integer label, compute:

* **centroid_voxel** — (x, y, z) floating-point voxel indices of the centre of
  mass, i.e. the mean position of all voxels carrying that label value.
* **centroid_mm** — physical coordinate derived by element-wise multiplication
  with the voxel spacings: ``centroid_mm[i] = centroid_voxel[i] * spacing[i]``.
  Correct under anisotropic spacing.
* **level_name** — anatomical vertebra name (e.g. ``"C1"``, ``"L3"``, ``"S"``)
  looked up from a :class:`segqc.labels.LabelConvention`.  Falls back to
  :data:`segqc.labels.UNKNOWN` for unmapped integer labels; never empty.

Public API
----------
``LabelCentroid``
    Frozen dataclass carrying the result for a single label.
``compute_centroid(seg_img, label, convention=None) -> LabelCentroid``
    Extract the centroid for ``label`` from a NiBabel ``Nifti1Image``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import nibabel as nib

from segqc.labels import UNKNOWN, LabelConvention

__all__ = [
    "LabelCentroid",
    "compute_centroid",
]


# --------------------------------------------------------------------------- #
# LabelCentroid dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LabelCentroid:
    """Centre-of-mass record for a single integer label.

    All fields are populated by :func:`compute_centroid`; the dataclass is
    frozen (immutable) and carries no NiBabel objects so it is cheaply
    serialisable and can be compared with ``==``.

    Attributes
    ----------
    label:
        The integer label value.
    level_name:
        Anatomical vertebra name from the :class:`~segqc.labels.LabelConvention`
        (e.g. ``"C1"``, ``"T8"``, ``"S"``), or :data:`~segqc.labels.UNKNOWN`
        when the integer has no mapping.
    centroid_voxel:
        (x, y, z) centre of mass in voxel-index space, as a 3-tuple of floats.
        The values are the means of the voxel coordinate arrays along each axis.
    centroid_mm:
        (x, y, z) centre of mass in mm, derived by element-wise multiplication
        ``centroid_voxel[i] * spacing[i]``.  Differs from ``centroid_voxel``
        when spacing is not 1 mm isotropic.
    """

    label: int
    level_name: str
    centroid_voxel: Tuple[float, float, float]
    centroid_mm: Tuple[float, float, float]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_spacing(seg_img: nib.Nifti1Image) -> Tuple[float, float, float]:
    """Extract (sx, sy, sz) voxel spacings in mm from a NiBabel image."""
    zooms = seg_img.header.get_zooms()
    return float(zooms[0]), float(zooms[1]), float(zooms[2])


# --------------------------------------------------------------------------- #
# Core compute function
# --------------------------------------------------------------------------- #


def compute_centroid(
    seg_img: nib.Nifti1Image,
    label: int,
    convention: Optional[LabelConvention] = None,
) -> LabelCentroid:
    """Compute the centre-of-mass centroid for a single integer label.

    The function is **read-only** — the input image is never modified.  It is
    **deterministic**: identical inputs always produce identical outputs.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.  The
        header's voxel dimensions (``get_zooms()``) are used for the physical
        coordinate computation; only diagonal / isotropic-by-axis affines are
        expected from the synthetic fixtures, but anisotropic spacings are
        handled correctly.
    label:
        The integer label value to compute the centroid for.
    convention:
        Optional :class:`~segqc.labels.LabelConvention` used to resolve the
        anatomical level name.  When ``None`` (default), the shipped
        TotalSegmentator / VerSe convention (:meth:`LabelConvention.default`)
        is used.

    Returns
    -------
    LabelCentroid
        Centroid record for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    # Read the array without copying — np.asanyarray returns a view where
    # possible; we never write to it, so the input is not mutated.
    data = np.asanyarray(seg_img.dataobj)

    # Locate all voxels for the requested label.  Shape is (N, 3) when N > 0.
    coords = np.argwhere(data == label)

    if coords.shape[0] == 0:
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). "
            f"Available non-zero labels: "
            f"{sorted(int(v) for v in np.unique(data) if v != 0)}"
        )

    # Centre of mass: mean of voxel coordinates along each axis.
    cx = float(np.mean(coords[:, 0]))
    cy = float(np.mean(coords[:, 1]))
    cz = float(np.mean(coords[:, 2]))
    centroid_voxel: Tuple[float, float, float] = (cx, cy, cz)

    # Physical centroid: element-wise multiplication with voxel spacings.
    sx, sy, sz = _get_spacing(seg_img)
    centroid_mm: Tuple[float, float, float] = (cx * sx, cy * sy, cz * sz)

    # Anatomical level name from the convention.
    if convention is None:
        convention = LabelConvention.default()
    level_name: str = convention.name_of(label)

    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=centroid_voxel,
        centroid_mm=centroid_mm,
    )
