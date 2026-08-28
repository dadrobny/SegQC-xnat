"""Per-vertebra perpendicular offset from the fitted spline (item 018).

For each vertebra centroid in the ordered sequence, compute its closest-approach
distance to the parametric spline produced by :func:`segfacet.features.spline.fit_centroid_spline`.

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
    Compute one offset record per centroid, **in-sample**: the level under
    test shaped the curve it is measured against.
``compute_leave_one_out_spline_offsets(centroids, spacing_mm=None, *, backend=None) -> List[VertebralSplineOffset]``
    Compute one offset record per centroid, **held out** (item 120): the
    level under test does not shape the curve it is judged against.

Deliberate CPU fallback (item 072)
-----------------------------------
``compute_spline_offsets`` and ``compute_leave_one_out_spline_offsets`` both
accept a ``backend`` keyword for signature uniformity with the other Stage-2/3
feature functions, but their numeric work always runs on CPU: the coarse ``u``
scan, ``scipy.optimize.minimize_scalar`` refinement, and the leave-one-out
refits operate on tiny centroid arrays with no reliable CuPy equivalent, so
this is a documented, known partial-GPU-coverage limitation -- even under an
explicit GPU backend, the optimisation runs on SciPy/CPU with host arrays and
returns host results.

Held-out evaluation (item 120)
--------------------------------
``compute_spline_offsets`` is *in-sample*: the fit it is evaluated against was
shaped by every centroid it measures, including the one under test, so a
displaced vertebra pulls the smoothing spline (item 119) toward itself and its
own offset reads far below the applied displacement -- the circularity item
118 diagnosed. ``compute_leave_one_out_spline_offsets`` corrects this by
measuring each level against a curve it did not shape:

1. Fit once through all present centroids at equal weight (the "reference
   fit"), and identify the single most-deviant level under that fit -- the
   **dominant outlier**, chosen as the largest in-sample ``offset_mm``, ties
   broken by **ascending label**.
2. For each level in turn, refit through **the same chord-length
   parameterisation** (``u``) as the reference fit, but with that level's own
   weight and the dominant outlier's weight both driven to a negligible
   constant. Withholding by **down-weighting instead of dropping** keeps
   every level in the curve's parameter domain -- terminal levels are still
   measured against curve interior, not against a truncated endpoint -- while
   a negligible weight keeps the withheld level from pulling the fit toward
   itself. Withholding the case's dominant outlier too prevents one broken
   vertebra from bending its neighbours' held-out curves (outlier
   cross-talk).
3. Below four levels the held-out path falls back to the in-sample
   measurement: withholding two of four-or-fewer points leaves too few
   effective points for a refit to mean anything.

**Documented limitation.** A displaced *terminal* level on a short spine is
not reliably separable: withholding a terminal level and the dominant outlier
leaves only three points to constrain a cubic at five levels (the committed
corpus's level count), so the held-out offset under-reports the true
displacement there. Real fields of view carry far more than five levels, and
this is measurably resolved by level count alone -- not worked around here.

**Documented limitation: only the single dominant outlier is withheld.**
Step 1 identifies and withholds one outlier per refit. With **two or more**
genuinely displaced levels, every un-withheld displaced level still pulls
every *other* level's held-out curve toward itself, which can both under-report
a real displacement and over-report a clean level as displaced. Measured on
the adversarial two-opposite-displacements case (two levels displaced in
opposite directions): a genuinely **clean** level reads **31.96 mm** while one
of the **displaced** levels reads only **19.31 mm** -- the clean level can be
named an offender ahead of an actual one. This is accepted as a known, shipped
limitation (not fixed by this item); the natural follow-up is withholding
every level above some outlier cutoff, not just the single dominant one, and
is left to future work.

RAS axis contract for the direction components (item 120)
-------------------------------------------------------------
``dx_mm``, ``dy_mm`` and ``dz_mm`` are anatomically readable -- array axis 0
is left-right, axis 1 is anterior-posterior, axis 2 is cranio-caudal -- **only
because** two facts hold elsewhere in this codebase: ``segfacet.io.
load_volume`` reorients every volume to axis codes ``("R", "A", "S")``
(``io.py``'s ``_TARGET_AXCODES``) before any feature is computed, and
:func:`segfacet.features.centroids.compute_centroid` derives ``centroid_mm``
as ``centroid_voxel * spacing`` with no affine of its own. If either fact
changed, the direction components would still be well-defined numbers but
would no longer mean "left-right" / "anterior-posterior" / "cranio-caudal".
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize_scalar

import segfacet.backend as _backend_mod
from segfacet.backend import Backend
from segfacet.features.centroids import LabelCentroid
from segfacet.features.spline import SplineFit, evaluate_spline, fit_centroid_spline

__all__ = [
    "VertebralSplineOffset",
    "compute_spline_offsets",
    "compute_leave_one_out_spline_offsets",
]

# Number of u samples in the coarse scan.  500 gives sub-mm resolution for
# typical whole-spine extents (~400 mm total arc length).
_N_SCAN: int = 500

# Weight assigned to a withheld level's own point (and the case's dominant
# outlier) in a leave-one-out refit (item 120). Small enough to be
# negligible relative to the uniform 1.0 weight on every other point, but
# strictly positive -- make_splprep rejects a zero weight.
_WITHHELD_WEIGHT: float = 1e-6

# Below this many levels, withholding two of them (the level under test plus
# the dominant outlier) leaves too few effective points for a refit to mean
# anything -- fall back to the in-sample measurement (item 120, AC7).
_MIN_LEVELS_FOR_HELD_OUT: int = 4


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


def _sq_distance(
    u_scalar: float, pt: np.ndarray, fit: SplineFit, backend: Optional[Backend]
) -> float:
    """Squared Euclidean distance from pt to the spline point at parameter u."""
    spline_pt = evaluate_spline(fit, [float(u_scalar)], backend=backend)  # shape (1, 3)
    diff = pt - spline_pt[0]
    return float(np.dot(diff, diff))


def _find_closest_u(pt: np.ndarray, fit: SplineFit, backend: Optional[Backend]) -> float:
    """Return the spline parameter u* in [0, 1] closest to point pt (mm coords).

    Strategy:
    1. Coarse scan over _N_SCAN equally-spaced u values.
    2. Refine with ``minimize_scalar`` in a bracket centred on the coarse best.
    """
    u_scan = np.linspace(0.0, 1.0, _N_SCAN)
    spline_pts = evaluate_spline(fit, u_scan, backend=backend)  # (N_SCAN, 3)
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
        args=(pt, fit, backend),
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
    *,
    backend: Optional[Backend] = None,
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
    backend:
        Optional :class:`~segfacet.backend.Backend` handle, forwarded to
        :func:`~segfacet.features.spline.evaluate_spline`. When ``None`` (the
        default), resolved via :func:`segfacet.backend.get_backend`; the
        optimisation itself always runs on host NumPy/SciPy regardless (see
        the module docstring's "Deliberate CPU fallback" section).

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
    backend = backend or _backend_mod.get_backend()

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

        u_star = _find_closest_u(pt, fit, backend)

        # Displacement vector: centroid - closest spline point.
        spline_pt = evaluate_spline(fit, [u_star], backend=backend)[0]  # shape (3,)
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


# --------------------------------------------------------------------------- #
# Held-out (leave-one-out) evaluation (item 120)
# --------------------------------------------------------------------------- #


def compute_leave_one_out_spline_offsets(
    centroids: Sequence[LabelCentroid],
    spacing_mm: Optional[Tuple[float, float, float]] = None,
    *,
    backend: Optional[Backend] = None,
) -> List[VertebralSplineOffset]:
    """Compute each centroid's offset from a spline it did not shape.

    See the module docstring's "Held-out evaluation (item 120)" section for
    the full definition. In short: a reference fit through all centroids at
    equal weight identifies the case's dominant outlier (the largest
    in-sample ``offset_mm``, ties broken by **ascending label**); then, for
    each level, a refit through the reference fit's own chord-length ``u``
    down-weights that level and the dominant outlier to a negligible
    constant (never zero -- ``make_splprep`` rejects that), so the level
    under test cannot pull the curve toward itself while the curve's
    parameter domain never shrinks.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects.
    spacing_mm:
        Voxel spacings (sx, sy, sz) in mm, forwarded to
        :func:`compute_spline_offsets` for the ``offset_voxel`` conversion.
    backend:
        Optional :class:`~segfacet.backend.Backend` handle, forwarded to the
        fit/evaluate calls this function makes. The refits themselves always
        run on host NumPy/SciPy regardless -- see the module docstring's
        "Deliberate CPU fallback" section.

    Returns
    -------
    List[VertebralSplineOffset]
        One record per input centroid, in input order, with the same field
        set :func:`compute_spline_offsets` returns.

    Raises
    ------
    ValueError
        Propagated from :func:`~segfacet.features.spline.fit_centroid_spline`
        or :func:`compute_spline_offsets` (e.g. fewer than 2 centroids, or
        two centroids sharing an exactly-coincident mm-coordinate).
    """
    backend = backend or _backend_mod.get_backend()

    n_points = len(centroids)

    reference_fit = fit_centroid_spline(centroids, backend=backend)

    if n_points < _MIN_LEVELS_FOR_HELD_OUT:
        return compute_spline_offsets(
            centroids, reference_fit, spacing_mm=spacing_mm, backend=backend
        )

    in_sample = compute_spline_offsets(
        centroids, reference_fit, spacing_mm=spacing_mm, backend=backend
    )

    # Dominant outlier: largest in-sample offset_mm, ties broken by
    # ascending label.
    worst_idx = min(
        range(n_points),
        key=lambda i: (-in_sample[i].offset_mm, centroids[i].label),
    )

    records: List[Optional[VertebralSplineOffset]] = [None] * n_points
    for i in range(n_points):
        weights = [1.0] * n_points
        weights[i] = _WITHHELD_WEIGHT
        weights[worst_idx] = _WITHHELD_WEIGHT

        refit = fit_centroid_spline(
            centroids, u=reference_fit.u, weights=weights, backend=backend
        )
        record = compute_spline_offsets(
            [centroids[i]], refit, spacing_mm=spacing_mm, backend=backend
        )[0]
        records[i] = record

    return records  # type: ignore[return-value]
