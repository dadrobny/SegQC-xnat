"""Per-vertebra perpendicular offset from the fitted spline (item 018).

For each vertebra centroid in the ordered sequence, compute its closest-approach
distance to the parametric spline produced by :func:`segqc.features.spline.fit_centroid_spline`.

The closest point on the spline is found by:
1. Coarse scan over N_SCAN=500 uniformly-spaced u values to locate the
   approximate minimum.
2. Refinement with ``scipy.optimize.minimize_scalar`` bracketed around the
   coarse minimum for sub-mm accuracy.

The result is a :class:`VertebralSplineOffset` per centroid capturing the
Euclidean distance in mm and in voxel units (anisotropic-aware), the raw
signed-component displacement vector (dx_mm, dy_mm, dz_mm), and the spline
parameter value of the closest point.

Public API
----------
``VertebralSplineOffset``
    Frozen dataclass with per-centroid offset data.
``compute_spline_offsets(centroids, fit, spacing_mm=None) -> List[VertebralSplineOffset]``
    Compute one offset record per centroid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize_scalar

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, evaluate_spline

__all__ = [
    "VertebralSplineOffset",
    "compute_spline_offsets",
]

# Number of u samples in the coarse scan.  500 gives sub-mm resolution for
# typical whole-spine extents (~400 mm total arc length).
_N_SCAN: int = 500


# --------------------------------------------------------------------------- #
# VertebralSplineOffset dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VertebralSplineOffset:
    """Per-vertebra perpendicular offset from the fitted spline.

    Attributes
    ----------
    label : int
        The integer label value.
    level_name : str
        Anatomical vertebra name (from the source LabelCentroid).
    closest_u : float
        Spline parameter value (0..1) of the closest point on the curve.
    offset_mm : float
        Euclidean distance (mm) from the centroid to the closest spline point.
        Near-zero for on-curve centroids; large for displaced vertebrae.
    offset_voxel : float
        Same distance expressed in voxel units.  Equal to offset_mm when
        spacing_mm is isotropic 1 mm; differs under anisotropic spacing.
    dx_mm : float
        x-component of the displacement vector (centroid_mm[0] - spline_x),
        in mm.
    dy_mm : float
        y-component of the displacement vector, in mm.
    dz_mm : float
        z-component of the displacement vector, in mm.
    """

    label: int
    level_name: str
    closest_u: float
    offset_mm: float
    offset_voxel: float
    dx_mm: float
    dy_mm: float
    dz_mm: float


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _sq_distance(u_scalar: float, pt: np.ndarray, fit: SplineFit) -> float:
    """Squared Euclidean distance from pt to the spline point at parameter u."""
    spline_pt = evaluate_spline(fit, [float(u_scalar)])  # shape (1, 3)
    diff = pt - spline_pt[0]
    return float(np.dot(diff, diff))


def _find_closest_u(pt: np.ndarray, fit: SplineFit) -> float:
    """Return the spline parameter u* in [0, 1] closest to point pt (mm coords).

    Strategy:
    1. Coarse scan over _N_SCAN equally-spaced u values.
    2. Refine with ``minimize_scalar`` in a bracket centred on the coarse best.
    """
    u_scan = np.linspace(0.0, 1.0, _N_SCAN)
    spline_pts = evaluate_spline(fit, u_scan)  # (N_SCAN, 3)
    diffs = spline_pts - pt  # (N_SCAN, 3)
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)  # (N_SCAN,)
    best_idx = int(np.argmin(sq_dists))
    u_coarse = float(u_scan[best_idx])

    # Bracket for refinement: one step each side (clamped to [0, 1]).
    step = 1.0 / (_N_SCAN - 1)
    lo = max(0.0, u_coarse - step)
    hi = min(1.0, u_coarse + step)

    if lo >= hi:
        # Degenerate bracket (e.g. only 2-point spline at boundary) — skip refinement.
        return u_coarse

    result = minimize_scalar(
        _sq_distance,
        bounds=(lo, hi),
        args=(pt, fit),
        method="bounded",
        options={"xatol": 1e-6},
    )
    u_refined = float(np.clip(result.x, 0.0, 1.0))
    return u_refined


# --------------------------------------------------------------------------- #
# Public compute function
# --------------------------------------------------------------------------- #


def compute_spline_offsets(
    centroids: Sequence[LabelCentroid],
    fit: SplineFit,
    spacing_mm: Optional[Tuple[float, float, float]] = None,
) -> List[VertebralSplineOffset]:
    """Compute the perpendicular offset of each centroid from the fitted spline.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects.  Must be the same sequence
        (or a subset) used to produce ``fit``.
    fit:
        The SplineFit produced by fit_centroid_spline.
    spacing_mm:
        Voxel spacings (sx, sy, sz) in mm used to convert offset_mm to
        offset_voxel.  When None, isotropic 1 mm spacing is assumed (so
        offset_voxel == offset_mm).

    Returns
    -------
    List[VertebralSplineOffset]
        One record per centroid, in the same order as the input sequence.
        The list is never empty when centroids is non-empty.

    Raises
    ------
    ValueError
        When centroids is empty or fit has fewer than 2 points.
    """
    if len(centroids) == 0:
        raise ValueError(
            "compute_spline_offsets requires at least one centroid, "
            "but received an empty sequence."
        )

    # Determine per-axis voxel spacings (default: isotropic 1 mm).
    if spacing_mm is None:
        sx, sy, sz = 1.0, 1.0, 1.0
    else:
        sx, sy, sz = float(spacing_mm[0]), float(spacing_mm[1]), float(spacing_mm[2])

    records: List[VertebralSplineOffset] = []

    for c in centroids:
        pt = np.array(
            [float(c.centroid_mm[0]), float(c.centroid_mm[1]), float(c.centroid_mm[2])],
            dtype=np.float64,
        )

        u_star = _find_closest_u(pt, fit)

        # Displacement vector: centroid - closest spline point.
        spline_pt = evaluate_spline(fit, [u_star])[0]  # shape (3,)
        diff = pt - spline_pt  # (dx_mm, dy_mm, dz_mm)

        dx_mm = float(diff[0])
        dy_mm = float(diff[1])
        dz_mm = float(diff[2])

        # Euclidean distance in mm.
        offset_mm = float(math.sqrt(dx_mm ** 2 + dy_mm ** 2 + dz_mm ** 2))

        # Voxel-space distance: anisotropic-correct sqrt of scaled components.
        offset_voxel = float(
            math.sqrt((dx_mm / sx) ** 2 + (dy_mm / sy) ** 2 + (dz_mm / sz) ** 2)
        )

        records.append(
            VertebralSplineOffset(
                label=c.label,
                level_name=c.level_name,
                closest_u=u_star,
                offset_mm=offset_mm,
                offset_voxel=offset_voxel,
                dx_mm=dx_mm,
                dy_mm=dy_mm,
                dz_mm=dz_mm,
            )
        )

    return records
