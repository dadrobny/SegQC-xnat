"""Per-label geometric features: volume, extent, bounding box, border-contact (item 011).

Given a NIfTI instance label map and a target label integer, compute the
following geometric properties for that label's voxel set:

* **voxel_count** — number of voxels carrying that label value.
* **physical_volume_mm3** — voxel_count * product of voxel spacings (mm^3).
* **extent_x/y/z_mm** — physical span (mm) of the label along each image axis,
  defined as the number of occupied voxels along that axis multiplied by the
  corresponding spacing, i.e. ``(max_idx - min_idx + 1) * spacing``.
* **bbox_voxel** / **bbox_physical** — axis-aligned bounding box as a
  :class:`BBox` dataclass exposing ``x_min``, ``x_max``, ``y_min``, ``y_max``,
  ``z_min``, ``z_max`` in voxel indices (inclusive) or mm coordinates.
* **touches_inferior/superior/left/right/anterior/posterior** — bool flags
  indicating whether the label touches each face of the image volume.  The
  mapping from image axes to anatomical directions is:

  ========================  ==================
  Image face                Anatomical flag
  ========================  ==================
  x == 0                    touches_inferior
  x == shape[0]-1           touches_superior
  y == 0                    touches_left
  y == shape[1]-1           touches_right
  z == 0                    touches_anterior
  z == shape[2]-1           touches_posterior
  ========================  ==================

  This mapping is a pragmatic convention for tools that work in any orientation
  without a reliable RAS header; downstream callers that have orientation
  information can remap as needed.

Public API
----------
``BBox``
    Axis-aligned bounding box with per-axis min/max attributes.
``LabelGeometry``
    All geometric properties for a single label.
``compute_label_geometry(seg_img, label) -> LabelGeometry``
    Extract geometry for ``label`` from a NiBabel ``Nifti1Image``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import nibabel as nib

__all__ = [
    "BBox",
    "LabelGeometry",
    "compute_label_geometry",
]


# --------------------------------------------------------------------------- #
# BBox dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BBox:
    """Axis-aligned bounding box with named per-axis min/max attributes.

    For voxel bounding boxes the values are integer voxel indices (inclusive).
    For physical bounding boxes the values are mm coordinates derived from the
    image affine (voxel-centre convention).
    """

    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float


# --------------------------------------------------------------------------- #
# LabelGeometry dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LabelGeometry:
    """All geometric features computed for a single integer label.

    All fields are populated by :func:`compute_label_geometry`; the dataclass
    is frozen (immutable) and carries no NiBabel objects so it is cheaply
    serialisable and can be compared with ``==``.

    Attributes
    ----------
    voxel_count:
        Number of voxels with the target label value.
    physical_volume_mm3:
        voxel_count * product of voxel spacings in mm^3.
    extent_x_mm, extent_y_mm, extent_z_mm:
        Physical span of the label along each axis in mm, computed as
        ``(bbox_max_index - bbox_min_index + 1) * spacing``.
    bbox_voxel:
        Axis-aligned bounding box in integer voxel-index coordinates (inclusive
        at both ends).
    bbox_physical:
        Axis-aligned bounding box in mm (voxel-centre convention, i.e. the
        physical coordinate of each boundary voxel's centre).
    touches_inferior, touches_superior:
        True if any voxel of this label occupies the x=0 or x=shape[0]-1 face.
    touches_left, touches_right:
        True if any voxel of this label occupies the y=0 or y=shape[1]-1 face.
    touches_anterior, touches_posterior:
        True if any voxel of this label occupies the z=0 or z=shape[2]-1 face.
    """

    voxel_count: int
    physical_volume_mm3: float
    extent_x_mm: float
    extent_y_mm: float
    extent_z_mm: float
    bbox_voxel: BBox
    bbox_physical: BBox
    touches_inferior: bool
    touches_superior: bool
    touches_left: bool
    touches_right: bool
    touches_anterior: bool
    touches_posterior: bool


# --------------------------------------------------------------------------- #
# Core compute function
# --------------------------------------------------------------------------- #


def _get_spacing(seg_img: nib.Nifti1Image) -> Tuple[float, float, float]:
    """Extract (sx, sy, sz) voxel spacings in mm from a NiBabel image."""
    zooms = seg_img.header.get_zooms()
    # header.get_zooms() returns absolute voxel sizes (already positive)
    sx = float(zooms[0])
    sy = float(zooms[1])
    sz = float(zooms[2])
    return sx, sy, sz


def compute_label_geometry(
    seg_img: nib.Nifti1Image,
    label: int,
) -> LabelGeometry:
    """Compute geometric features for a single integer label in a NIfTI label map.

    The function is **read-only** — the input image is never modified.  It is
    **deterministic**: identical inputs always produce identical outputs.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer label map.  The header's
        voxel dimensions (``get_zooms()``) are used for all physical-space
        computations; only diagonal / isotropic-by-axis affines are expected
        from the synthetic fixtures, but the function handles anisotropic
        spacings correctly.
    label:
        The integer label value to extract geometry for.

    Returns
    -------
    LabelGeometry
        All geometric properties for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    # Read the array without copying — np.asanyarray returns a view where
    # possible; we never write to it, so the input is not mutated.
    data = np.asanyarray(seg_img.dataobj)

    # Locate voxels for the requested label.
    coords = np.argwhere(data == label)  # shape (N, 3) or (0, 3)

    if coords.shape[0] == 0:
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). Available labels: "
            f"{sorted(int(v) for v in np.unique(data) if v != 0)}"
        )

    voxel_count = int(coords.shape[0])

    # Voxel spacings from the NiBabel header (mm).
    sx, sy, sz = _get_spacing(seg_img)
    voxel_volume = sx * sy * sz
    physical_volume_mm3 = float(voxel_count * voxel_volume)

    # Bounding box in voxel coordinates (inclusive min/max).
    x_min_v = int(coords[:, 0].min())
    x_max_v = int(coords[:, 0].max())
    y_min_v = int(coords[:, 1].min())
    y_max_v = int(coords[:, 1].max())
    z_min_v = int(coords[:, 2].min())
    z_max_v = int(coords[:, 2].max())

    bbox_voxel = BBox(
        x_min=x_min_v,
        x_max=x_max_v,
        y_min=y_min_v,
        y_max=y_max_v,
        z_min=z_min_v,
        z_max=z_max_v,
    )

    # Physical extent: (inclusive voxel span) * spacing.
    # A 4-voxel-wide block (indices 2,3,4,5) has span = 5-2+1 = 4 voxels.
    extent_x_mm = float((x_max_v - x_min_v + 1) * sx)
    extent_y_mm = float((y_max_v - y_min_v + 1) * sy)
    extent_z_mm = float((z_max_v - z_min_v + 1) * sz)

    # Physical bounding box: voxel-centre coordinates, i.e. voxel_index * spacing.
    # The affine is diagonal so voxel (i, j, k) maps to physical (i*sx, j*sy, k*sz).
    bbox_physical = BBox(
        x_min=float(x_min_v * sx),
        x_max=float(x_max_v * sx),
        y_min=float(y_min_v * sy),
        y_max=float(y_max_v * sy),
        z_min=float(z_min_v * sz),
        z_max=float(z_max_v * sz),
    )

    # Border-contact flags: does the label touch each face of the image volume?
    # Face mapping: x=0 -> inferior, x=max -> superior,
    #               y=0 -> left,     y=max -> right,
    #               z=0 -> anterior, z=max -> posterior.
    shape = data.shape
    touches_inferior  = bool(x_min_v == 0)
    touches_superior  = bool(x_max_v == shape[0] - 1)
    touches_left      = bool(y_min_v == 0)
    touches_right     = bool(y_max_v == shape[1] - 1)
    touches_anterior  = bool(z_min_v == 0)
    touches_posterior = bool(z_max_v == shape[2] - 1)

    return LabelGeometry(
        voxel_count=voxel_count,
        physical_volume_mm3=physical_volume_mm3,
        extent_x_mm=extent_x_mm,
        extent_y_mm=extent_y_mm,
        extent_z_mm=extent_z_mm,
        bbox_voxel=bbox_voxel,
        bbox_physical=bbox_physical,
        touches_inferior=touches_inferior,
        touches_superior=touches_superior,
        touches_left=touches_left,
        touches_right=touches_right,
        touches_anterior=touches_anterior,
        touches_posterior=touches_posterior,
    )
