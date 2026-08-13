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
  mapping from array axes to these six anatomical flags is **derived from the
  image's affine** (item 108), via ``nibabel.aff2axcodes`` — it is *not* a
  fixed axis order.  For each array axis, ``aff2axcodes`` reports which
  anatomical direction that axis' *increasing* index points toward (its
  "axcode" letter, one of R/L/A/P/S/I); the axis' low face (index 0) and high
  face (index ``shape[axis]-1``) are then named from the opposite/matching
  ends of that letter's L/R, A/P or S/I pair. E.g. for a volume whose affine
  resolves to RAS axcodes (``segfacet.io`` reorients every loaded volume to
  RAS — item 094), array axis 0 runs left→right, so its low face is
  ``touches_left`` and its high face is ``touches_right``; axis 1 runs
  posterior→anterior (``touches_posterior`` / ``touches_anterior``); axis 2
  runs inferior→superior (``touches_inferior`` / ``touches_superior``). A
  volume stored under any other axis order/orientation yields the same six
  flags for the same physical anatomy, because the mapping is read from that
  volume's own affine rather than assumed. A missing or degenerate (singular)
  affine — one ``aff2axcodes`` cannot resolve to six distinct directions — is
  a hard error (:class:`ValueError`) rather than a silent mis-assignment; see
  :func:`_face_map_from_affine`.

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
from typing import Optional, Tuple

import numpy as np
import nibabel as nib

import segfacet.backend as _backend_mod
from segfacet.backend import Backend

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
    touches_inferior, touches_superior, touches_left, touches_right,
    touches_anterior, touches_posterior:
        True if any voxel of this label occupies the corresponding face of
        the image volume. Which array axis/index carries which of these six
        flags is derived from the image's affine (item 108) -- see the
        module docstring and :func:`_face_map_from_affine`; it is *not* a
        fixed axis order.
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


# Anatomical axcode letter -> (flag name for the axis' *low*-index face,
# flag name for its *high*-index face). ``aff2axcodes`` reports, per array
# axis, which direction *increasing* index points toward; the low face is
# therefore the opposite end of that pair, the high face the named end.
_AXCODE_TO_FACES = {
    "R": ("touches_left", "touches_right"),
    "L": ("touches_right", "touches_left"),
    "A": ("touches_posterior", "touches_anterior"),
    "P": ("touches_anterior", "touches_posterior"),
    "S": ("touches_inferior", "touches_superior"),
    "I": ("touches_superior", "touches_inferior"),
}


def _face_map_from_affine(affine) -> Tuple[Tuple[str, str], Tuple[str, str], Tuple[str, str]]:
    """Derive the per-array-axis (low_face, high_face) flag-name triple from
    *affine* (item 108).

    Parameters
    ----------
    affine:
        A 4x4 NIfTI affine (or ``None``).

    Returns
    -------
    tuple of 3 (low_face, high_face) pairs
        One pair per array axis (0, 1, 2), each a ``touches_*`` attribute
        name.

    Raises
    ------
    ValueError
        If *affine* is ``None``, or ``nibabel.aff2axcodes`` cannot resolve
        one of the three array axes to a distinct anatomical direction (a
        singular/rank-deficient affine) -- a degenerate affine per AC9,
        surfaced as a clear error rather than a silent mis-assignment.
    """
    if affine is None:
        raise ValueError(
            "compute_label_geometry requires a non-None affine to derive the "
            "touches_* face mapping (item 108); the segmentation image's "
            "affine is None."
        )
    axcodes = nib.aff2axcodes(affine)
    if len(axcodes) != 3 or any(code is None for code in axcodes):
        raise ValueError(
            "compute_label_geometry cannot derive the touches_* face mapping "
            f"from a degenerate affine (nib.aff2axcodes resolved to {axcodes!r}, "
            "not three distinct anatomical directions); the affine is missing, "
            "singular, or otherwise rank-deficient."
        )
    return tuple(_AXCODE_TO_FACES[code] for code in axcodes)  # type: ignore[return-value]


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
    *,
    backend: Optional[Backend] = None,
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
    backend:
        Optional :class:`~segfacet.backend.Backend` handle routing the array
        operations through ``numpy`` (CPU) or ``cupy`` (GPU).  When ``None``
        (the default), resolved via :func:`segfacet.backend.get_backend`
        (auto-detect, honouring ``SEGFACET_BACKEND``).  The CPU path is
        numerically byte-identical regardless of whether ``backend`` is
        explicit or auto-resolved.

    Returns
    -------
    LabelGeometry
        All geometric properties for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    backend = backend or _backend_mod.get_backend()
    xp = backend.xp

    # Read the array without copying — np.asanyarray returns a view where
    # possible; we never write to it, so the input is not mutated.
    data = xp.asarray(np.asanyarray(seg_img.dataobj))

    # Locate voxels for the requested label.
    coords = xp.argwhere(data == label)  # shape (N, 3) or (0, 3)

    if coords.shape[0] == 0:
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). Available labels: "
            f"{sorted(int(v) for v in np.unique(np.asanyarray(seg_img.dataobj)) if v != 0)}"
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

    # Border-contact flags: does the label touch each face of the image
    # volume? The array-axis -> anatomical-face mapping is derived from
    # seg_img.affine (item 108), not assumed.
    shape = data.shape
    face_map = _face_map_from_affine(seg_img.affine)
    min_v = (x_min_v, y_min_v, z_min_v)
    max_v = (x_max_v, y_max_v, z_max_v)

    face_flags = {
        "touches_inferior": False,
        "touches_superior": False,
        "touches_left": False,
        "touches_right": False,
        "touches_anterior": False,
        "touches_posterior": False,
    }
    for axis in range(3):
        low_face, high_face = face_map[axis]
        if min_v[axis] == 0:
            face_flags[low_face] = True
        if max_v[axis] == shape[axis] - 1:
            face_flags[high_face] = True

    touches_inferior = face_flags["touches_inferior"]
    touches_superior = face_flags["touches_superior"]
    touches_left = face_flags["touches_left"]
    touches_right = face_flags["touches_right"]
    touches_anterior = face_flags["touches_anterior"]
    touches_posterior = face_flags["touches_posterior"]

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
