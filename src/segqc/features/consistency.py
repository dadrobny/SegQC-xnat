"""Neighbour-consistency metrics for the ordered centroid sequence (item 020).

Two families of metrics are computed:

A. **Spacing regularity** — mean inter-centroid spacing, coefficient of
   variation (CV), per-pair signed deviations, and outlier-pair flags.

B. **Monotonic progression** — whether the spline parameter *u* increases
   (non-decreasingly) at every consecutive pair in anatomical order; the
   non-monotonic pairs are listed by level name.

Public API
----------
``SpacingConsistency``
    Frozen dataclass with spacing-regularity metrics.
``MonotonicConsistency``
    Frozen dataclass with monotonic-progression metrics.
``compute_spacing_consistency(centroids, outlier_threshold_high=2.0, outlier_threshold_low=0.3) -> SpacingConsistency``
    Compute spacing metrics for an ordered centroid sequence.
``compute_monotonic_consistency(centroids, fit) -> MonotonicConsistency``
    Assess monotonicity of anatomical order against the fitted spline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import numpy as np
from scipy.optimize import minimize_scalar

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, evaluate_spline

__all__ = [
    "SpacingConsistency",
    "MonotonicConsistency",
    "compute_spacing_consistency",
    "compute_monotonic_consistency",
]

# Number of u samples in the coarse scan.  500 gives sub-mm resolution for
# typical whole-spine extents (~400 mm total arc length).
_N_SCAN: int = 500


# --------------------------------------------------------------------------- #
# Result dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SpacingConsistency:
    """Spacing-regularity metrics for the ordered centroid sequence.

    Attributes
    ----------
    mean_spacing_mm : float
        Mean inter-centroid Euclidean spacing (mm).
    cv_spacing : float
        Coefficient of variation of inter-centroid spacings
        (0 = perfectly regular).  Defined as ``std(spacings) / mean(spacings)``
        using population (ddof=0) standard deviation; 0.0 when there is only
        one spacing (no variance possible).
    spacings_mm : tuple[float, ...]
        Per-adjacent-pair spacings in anatomical order
        (length == n_centroids - 1).
    deviations_mm : tuple[float, ...]
        Signed deviation of each spacing from the mean
        (same length as spacings_mm).
    outlier_pairs : tuple[tuple[str, str], ...]
        (level_a, level_b) pairs whose spacing is flagged as an outlier
        because it exceeds ``outlier_threshold_high * mean`` or is below
        ``outlier_threshold_low * mean``.
    """

    mean_spacing_mm: float
    cv_spacing: float
    spacings_mm: tuple
    deviations_mm: tuple
    outlier_pairs: tuple


@dataclass(frozen=True)
class MonotonicConsistency:
    """Monotonic-progression metrics for the spline parameter sequence.

    Attributes
    ----------
    is_monotonic : bool
        True iff u values increase (non-decreasingly) along the anatomical
        order.  ``u[i] >= u[i+1]`` is considered non-monotonic (equal values
        are also flagged — two vertebrae at the same spline parameter indicate
        a stacking or near-coincident issue).
    non_monotonic_pairs : tuple[tuple[str, str], ...]
        (level_a, level_b) pairs where ``u[a] >= u[b]`` (spline parameter did
        not advance).
    u_values : tuple[float, ...]
        Per-centroid spline parameter values used for the assessment
        (length == n_centroids).
    """

    is_monotonic: bool
    non_monotonic_pairs: tuple
    u_values: tuple


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _euclidean_mm(a: LabelCentroid, b: LabelCentroid) -> float:
    """Return the Euclidean distance in mm between two LabelCentroid objects."""
    ax, ay, az = float(a.centroid_mm[0]), float(a.centroid_mm[1]), float(a.centroid_mm[2])
    bx, by, bz = float(b.centroid_mm[0]), float(b.centroid_mm[1]), float(b.centroid_mm[2])
    return math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)


def _sq_distance_u(u_scalar: float, pt: np.ndarray, fit: SplineFit) -> float:
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
    spline_pts = evaluate_spline(fit, u_scan)  # (_N_SCAN, 3)
    diffs = spline_pts - pt  # (_N_SCAN, 3)
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)  # (_N_SCAN,)
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
        _sq_distance_u,
        bounds=(lo, hi),
        args=(pt, fit),
        method="bounded",
        options={"xatol": 1e-6},
    )
    u_refined = float(np.clip(result.x, 0.0, 1.0))
    return u_refined


# --------------------------------------------------------------------------- #
# Public compute functions
# --------------------------------------------------------------------------- #


def compute_spacing_consistency(
    centroids: Sequence[LabelCentroid],
    outlier_threshold_high: float = 2.0,
    outlier_threshold_low: float = 0.3,
) -> SpacingConsistency:
    """Compute spacing-regularity metrics for an ordered centroid sequence.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of LabelCentroid
        objects.  Must have >= 2 entries; raises ValueError for 0 or 1 centroid.
    outlier_threshold_high:
        A spacing >= this factor * mean_spacing is flagged as an outlier
        (default 2.0 — double the mean).
    outlier_threshold_low:
        A spacing <= this factor * mean_spacing is flagged as an outlier
        (default 0.3 — less than 30 % of the mean).

    Returns
    -------
    SpacingConsistency

    Raises
    ------
    ValueError
        When ``len(centroids) < 2``.
    """
    n = len(centroids)
    if n < 2:
        raise ValueError(
            f"compute_spacing_consistency requires at least 2 centroids to "
            f"compute inter-centroid spacings, but received {n}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    # Compute pairwise Euclidean distances in mm (do not mutate input).
    spacings: List[float] = [
        _euclidean_mm(centroids[i], centroids[i + 1]) for i in range(n - 1)
    ]

    mean_mm = float(np.mean(spacings))

    # Coefficient of variation: std / mean.  With only 1 spacing, std = 0.
    if len(spacings) == 1:
        cv = 0.0
    else:
        cv = float(np.std(spacings, ddof=0) / mean_mm) if mean_mm > 0.0 else 0.0

    # Signed deviations from the mean.
    deviations: List[float] = [s - mean_mm for s in spacings]

    # Outlier flags: flag pairs that are unusually large or small.
    outlier_pairs: List[Tuple[str, str]] = []
    for i, s in enumerate(spacings):
        if s >= outlier_threshold_high * mean_mm or s <= outlier_threshold_low * mean_mm:
            outlier_pairs.append(
                (centroids[i].level_name, centroids[i + 1].level_name)
            )

    return SpacingConsistency(
        mean_spacing_mm=mean_mm,
        cv_spacing=cv,
        spacings_mm=tuple(spacings),
        deviations_mm=tuple(deviations),
        outlier_pairs=tuple(outlier_pairs),
    )


def compute_monotonic_consistency(
    centroids: Sequence[LabelCentroid],
    fit: SplineFit,
) -> MonotonicConsistency:
    """Assess whether the anatomical order is consistent with monotonically
    increasing spline parameter values.

    For each centroid, finds its closest point on the spline (coarse scan +
    scalar refinement, same approach as item 018) and records the spline
    parameter *u*.  The anatomical order is consistent with the spline when
    ``u[i] < u[i+1]`` for every consecutive pair.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of LabelCentroid
        objects.  Must have >= 2 entries; raises ValueError for 0 or 1 centroid.
    fit:
        SplineFit produced by fit_centroid_spline (item 017).

    Returns
    -------
    MonotonicConsistency

    Raises
    ------
    ValueError
        When ``len(centroids) < 2``.
    """
    n = len(centroids)
    if n < 2:
        raise ValueError(
            f"compute_monotonic_consistency requires at least 2 centroids to "
            f"assess monotonic progression, but received {n}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    # Find the closest spline parameter u* for each centroid.
    u_values: List[float] = []
    for c in centroids:
        pt = np.array(
            [float(c.centroid_mm[0]), float(c.centroid_mm[1]), float(c.centroid_mm[2])],
            dtype=np.float64,
        )
        u_star = _find_closest_u(pt, fit)
        u_values.append(u_star)

    # Identify non-monotonic consecutive pairs: u[i] >= u[i+1].
    non_monotonic_pairs: List[Tuple[str, str]] = []
    for i in range(n - 1):
        if u_values[i] >= u_values[i + 1]:
            non_monotonic_pairs.append(
                (centroids[i].level_name, centroids[i + 1].level_name)
            )

    is_monotonic = len(non_monotonic_pairs) == 0

    return MonotonicConsistency(
        is_monotonic=is_monotonic,
        non_monotonic_pairs=tuple(non_monotonic_pairs),
        u_values=tuple(u_values),
    )
