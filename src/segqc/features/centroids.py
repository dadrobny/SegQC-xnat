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
from scipy.ndimage import distance_transform_edt, gaussian_filter

from segqc.labels import UNKNOWN, LabelConvention

__all__ = [
    "LabelCentroid",
    "compute_centroid",
    "CentroidFeatures",
    "compute_edt_centroids",
]

#: Anatomical level names that have no classic vertebral body (atlas / axis).
_ATLAS_AXIS_NAMES = frozenset({"C1", "C2"})


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


# --------------------------------------------------------------------------- #
# EDT-based centroid variants & centroid depth (item 023)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CentroidFeatures:
    """EDT-derived centroid variants and centroid-depth record for one label.

    Computed by :func:`compute_edt_centroids`.  Frozen and NiBabel-free, so it
    is cheaply comparable with ``==`` and serialisable.

    Attributes
    ----------
    label:
        The integer label value.
    level_name:
        Anatomical vertebra name from the convention, or
        :data:`~segqc.labels.UNKNOWN`; never empty.
    is_atlas_axis:
        ``True`` when ``level_name`` is ``"C1"`` or ``"C2"`` (vertebrae with no
        classic body).  Informational only — no special geometry is applied.
    smooth_centre_voxel / smooth_centre_mm:
        Centre of mass of the EDT-thresholded mask (voxels whose EDT is at or
        above ``smooth_threshold`` of the label's peak EDT).  Pulls the centroid
        into the robust interior core.  ``_mm`` is ``_voxel * spacing``.
    strict_centre_voxel / strict_centre_mm:
        Voxel of the peak of the Gaussian-smoothed EDT — the single deepest
        interior point.  ``_mm`` is ``_voxel * spacing``.
    centroid_depth_smooth / centroid_depth_strict:
        Distance, in voxel units, from the respective centroid voxel to the
        nearest label surface.  Derived from the EDT sampled at the
        integer-rounded centroid voxel: ``max(0, EDT - 0.5)`` (the surface lies
        midway to the nearest background voxel centre, so a surface voxel has
        depth 0.5).  High → well inside the interior; ``< 1`` → on/near the
        surface.
    smooth_threshold:
        The threshold fraction (0–1) used for the smooth centre.
    strict_sigma:
        The Gaussian sigma (voxels) used for the strict centre.
    """

    label: int
    level_name: str
    is_atlas_axis: bool
    smooth_centre_voxel: Tuple[float, float, float]
    smooth_centre_mm: Tuple[float, float, float]
    strict_centre_voxel: Tuple[float, float, float]
    strict_centre_mm: Tuple[float, float, float]
    centroid_depth_smooth: float
    centroid_depth_strict: float
    smooth_threshold: float
    strict_sigma: float


def _compute_edt(mask: np.ndarray) -> np.ndarray:
    """Euclidean distance transform of a binary ``mask`` (float64, same shape).

    Each foreground voxel holds its distance (in voxel units) to the nearest
    background voxel; background voxels are 0.
    """
    return distance_transform_edt(mask)


def _depth_from_edt(edt: np.ndarray, voxel: Tuple[float, ...]) -> float:
    """Sample ``edt`` at the integer-rounded ``voxel`` and convert to depth.

    Depth is the distance from the voxel centre to the nearest label surface:
    the surface lies halfway to the nearest background voxel centre, so we
    subtract 0.5 from the raw EDT value (clamped at 0).  A voxel adjacent to
    background (raw EDT 1.0) therefore has depth 0.5 (< 1).
    """
    idx = tuple(
        int(min(max(round(v), 0), dim - 1)) for v, dim in zip(voxel, edt.shape)
    )
    return max(0.0, float(edt[idx]) - 0.5)


def compute_edt_centroids(
    seg_img: nib.Nifti1Image,
    label: int,
    *,
    smooth_threshold: float = 0.50,
    strict_sigma: float = 1.0,
    convention: Optional[LabelConvention] = None,
) -> CentroidFeatures:
    """Compute EDT-based centroid variants and centroid depth for one label.

    Read-only (the input image is never modified) and deterministic.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.
    label:
        The integer label value to analyse.
    smooth_threshold:
        Fraction (0–1) of the label's peak EDT used to threshold the mask before
        computing the smooth centre's centre of mass.  ``0.0`` includes the whole
        label (equivalent to the plain CoM); ``1.0`` keeps only the peak voxels.
    strict_sigma:
        Gaussian sigma (in voxels) applied to the EDT before taking its argmax
        for the strict centre.  ``0.0`` disables smoothing.
    convention:
        Optional :class:`~segqc.labels.LabelConvention`; defaults to
        :meth:`LabelConvention.default`.

    Returns
    -------
    CentroidFeatures
        EDT centroid record for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    # Read-only view; we never write to it.
    data = np.asanyarray(seg_img.dataobj)

    mask = data == label
    if not mask.any():
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). "
            f"Available non-zero labels: "
            f"{sorted(int(v) for v in np.unique(data) if v != 0)}"
        )

    sx, sy, sz = _get_spacing(seg_img)
    spacing = (sx, sy, sz)

    edt = _compute_edt(mask)
    edt_max = float(edt.max())

    # --- Smooth centre: CoM of the EDT-thresholded interior core ----------- #
    thresh_mask = (edt >= smooth_threshold * edt_max) & mask
    if not thresh_mask.any():  # pragma: no cover - peak is always in the mask
        thresh_mask = mask
    smooth_coords = np.argwhere(thresh_mask)
    smooth_mean = smooth_coords.mean(axis=0)
    smooth_centre_voxel = (
        float(smooth_mean[0]),
        float(smooth_mean[1]),
        float(smooth_mean[2]),
    )

    # --- Strict centre: argmax of the Gaussian-smoothed EDT ---------------- #
    smoothed = gaussian_filter(edt, sigma=strict_sigma)
    peak = np.unravel_index(int(np.argmax(smoothed)), smoothed.shape)
    strict_centre_voxel = (float(peak[0]), float(peak[1]), float(peak[2]))

    smooth_centre_mm = tuple(v * s for v, s in zip(smooth_centre_voxel, spacing))
    strict_centre_mm = tuple(v * s for v, s in zip(strict_centre_voxel, spacing))

    centroid_depth_smooth = _depth_from_edt(edt, smooth_centre_voxel)
    centroid_depth_strict = _depth_from_edt(edt, strict_centre_voxel)

    if convention is None:
        convention = LabelConvention.default()
    level_name = convention.name_of(label)
    is_atlas_axis = level_name in _ATLAS_AXIS_NAMES

    return CentroidFeatures(
        label=label,
        level_name=level_name,
        is_atlas_axis=is_atlas_axis,
        smooth_centre_voxel=smooth_centre_voxel,
        smooth_centre_mm=smooth_centre_mm,
        strict_centre_voxel=strict_centre_voxel,
        strict_centre_mm=strict_centre_mm,
        centroid_depth_smooth=centroid_depth_smooth,
        centroid_depth_strict=centroid_depth_strict,
        smooth_threshold=float(smooth_threshold),
        strict_sigma=float(strict_sigma),
    )
