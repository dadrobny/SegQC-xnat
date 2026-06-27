"""Local vertebra neighbourhood comparison (item 024).

For each vertebra in the ordered centroid sequence, compute sliding-window
statistics over the surrounding neighbours:

* Mean, median, and std of inter-centroid **spacing** (mm) within the window.
* Mean, median, and std of **spline offset** (mm) within the window.
* Mean, median, and std of **label volume** (mm³) within the window.
* A per-vertebra **deviation score** (non-negative scalar) summarising how
  anomalous the focal vertebra is relative to its neighbours.
* An **outlier flag** when the deviation score exceeds a configurable threshold.

The window of width ``n`` centred at position ``i`` spans indices
``max(0, i - n//2)`` to ``min(len-1, i + n//2)`` inclusive.  At the
boundaries the window is asymmetric but the focal vertebra is always included.

Public API
----------
``VertebralNeighbourhood``
    Frozen dataclass with per-vertebra neighbourhood statistics.
``compute_neighbourhood_features(centroids, offsets, geometries, window_n=3,
    outlier_threshold=2.0) -> List[VertebralNeighbourhood]``
    Compute one record per centroid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence

import numpy as np

from segqc.features.centroids import LabelCentroid
from segqc.features.geometry import LabelGeometry
from segqc.features.spline_offset import VertebralSplineOffset

__all__ = [
    "VertebralNeighbourhood",
    "compute_neighbourhood_features",
]


# --------------------------------------------------------------------------- #
# VertebralNeighbourhood dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VertebralNeighbourhood:
    """Per-vertebra local neighbourhood statistics.

    Attributes
    ----------
    label : int
        Integer label value of the focal vertebra.
    level_name : str
        Anatomical name of the focal vertebra.
    window_labels : tuple[int, ...]
        Integer label values of all vertebrae in the window (including focal).
    mean_spacing_mm : float
        Mean inter-centroid spacing (mm) within the window.
    median_spacing_mm : float
        Median inter-centroid spacing (mm) within the window.
    std_spacing_mm : float
        Standard deviation of inter-centroid spacings within the window.
    mean_offset_mm : float
        Mean spline offset (mm) within the window.
    median_offset_mm : float
        Median spline offset (mm) within the window.
    std_offset_mm : float
        Standard deviation of spline offsets within the window.
    mean_volume_mm3 : float
        Mean label volume (mm³) within the window.
    median_volume_mm3 : float
        Median label volume (mm³) within the window.
    std_volume_mm3 : float
        Standard deviation of label volumes within the window.
    deviation_score : float
        Per-vertebra scalar summarising how anomalous the focal vertebra is
        relative to its neighbours (non-negative; 0 = perfectly consistent).
    is_outlier : bool
        True when deviation_score exceeds the configured threshold.
    """

    label: int
    level_name: str
    window_labels: tuple
    mean_spacing_mm: float
    median_spacing_mm: float
    std_spacing_mm: float
    mean_offset_mm: float
    median_offset_mm: float
    std_offset_mm: float
    mean_volume_mm3: float
    median_volume_mm3: float
    std_volume_mm3: float
    deviation_score: float
    is_outlier: bool


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

# Minimum std denominator to avoid division by zero when all window values are
# identical.  Chosen to be safely below any real mm deviation of interest while
# keeping the normalised score meaningful.
_MIN_STD: float = 1e-6


def _euclidean(a: tuple, b: tuple) -> float:
    """Return Euclidean distance (mm) between two 3-tuples."""
    return math.sqrt(
        (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
    )


def _safe_std(values: np.ndarray) -> float:
    """Return std of *values*; returns 0.0 when fewer than 2 elements."""
    if len(values) < 2:
        return 0.0
    return float(np.std(values, ddof=0))


def _window_spacing(centroids: Sequence[LabelCentroid], win_start: int, win_end: int) -> np.ndarray:
    """Return pairwise inter-centroid spacings within window [win_start, win_end].

    For a window of k vertebrae there are k-1 pairs.  When k == 1 (single
    vertebra), returns an empty array so callers get 0-valued statistics.
    """
    if win_end <= win_start:
        return np.array([], dtype=np.float64)
    spacings = []
    for j in range(win_start, win_end):
        spacings.append(_euclidean(centroids[j].centroid_mm, centroids[j + 1].centroid_mm))
    return np.array(spacings, dtype=np.float64)


def _deviation_score(
    focal_offset: float,
    focal_volume: float,
    win_offsets: np.ndarray,
    win_volumes: np.ndarray,
    focal_idx_in_window: int,
) -> float:
    """Compute the deviation score for the focal vertebra.

    Strategy: leave-one-out z-score — compare the focal vertebra's offset and
    volume against the *remaining* window members (its neighbours only, not
    itself).  This prevents the focal vertebra's own anomalous value from
    inflating the local mean/std and masking its own deviation.

    When the window std is near zero (homogeneous neighbours) we use a fixed
    reference of _MIN_STD so the formula remains numerically stable and the
    score stays near 0 for consistent spines.

    When there are no neighbours (window size 1), the score is 0.0 by
    definition — there is nothing to compare against.

    The result is always non-negative.
    """
    # Build neighbour-only arrays (leave out the focal element).
    neighbour_offsets = np.concatenate(
        [win_offsets[:focal_idx_in_window], win_offsets[focal_idx_in_window + 1:]]
    )
    neighbour_volumes = np.concatenate(
        [win_volumes[:focal_idx_in_window], win_volumes[focal_idx_in_window + 1:]]
    )

    if len(neighbour_offsets) == 0:
        # Single-element window: no neighbours — score is 0.
        return 0.0

    # Offset component
    mean_off = float(np.mean(neighbour_offsets))
    std_off = max(float(np.std(neighbour_offsets, ddof=0)), _MIN_STD)
    z_off = abs(focal_offset - mean_off) / std_off

    # Volume component
    mean_vol = float(np.mean(neighbour_volumes))
    std_vol = max(float(np.std(neighbour_volumes, ddof=0)), _MIN_STD)
    z_vol = abs(focal_volume - mean_vol) / std_vol

    # Combined score: take the maximum of the two normalised deviations so
    # that a large anomaly in either dimension is clearly visible.
    return float(max(z_off, z_vol))


# --------------------------------------------------------------------------- #
# Public compute function
# --------------------------------------------------------------------------- #


def compute_neighbourhood_features(
    centroids: Sequence[LabelCentroid],
    offsets: Sequence[VertebralSplineOffset],
    geometries: Mapping[int, LabelGeometry],
    window_n: int = 3,
    outlier_threshold: float = 2.0,
) -> List[VertebralNeighbourhood]:
    """Compute local neighbourhood statistics for each vertebra.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical) sequence of LabelCentroid objects.
        Must have >= 1 entry; raises ValueError when empty.
    offsets:
        Per-vertebra spline offsets from compute_spline_offsets (item 018).
        Must be in the same order as centroids and have the same length.
    geometries:
        Mapping from integer label to LabelGeometry (item 011).
        Must contain an entry for every label in centroids.
    window_n:
        Total window width (must be >= 1 and odd). Default 3 (= focal + 1 on
        each side). Raises ValueError when window_n < 1.
    outlier_threshold:
        Deviation score threshold above which a vertebra is flagged as an
        outlier. Default 2.0.

    Returns
    -------
    List[VertebralNeighbourhood]
        One record per centroid, in the same order as the input sequence.

    Raises
    ------
    ValueError
        When centroids is empty or window_n < 1.
    """
    if len(centroids) == 0:
        raise ValueError(
            "compute_neighbourhood_features requires at least one centroid, "
            "but received an empty sequence."
        )
    if window_n < 1:
        raise ValueError(
            f"window_n must be >= 1, got {window_n!r}."
        )

    n = len(centroids)
    half = window_n // 2

    # Pre-extract per-vertebra arrays (same order as centroids).
    offset_vals = np.array([float(o.offset_mm) for o in offsets], dtype=np.float64)
    volume_vals = np.array(
        [float(geometries[c.label].physical_volume_mm3) for c in centroids],
        dtype=np.float64,
    )

    records: List[VertebralNeighbourhood] = []

    for i, c in enumerate(centroids):
        # Window bounds (inclusive on both ends).
        win_start = max(0, i - half)
        win_end = min(n - 1, i + half)

        # Window label IDs (as Python ints).
        window_labels = tuple(int(centroids[j].label) for j in range(win_start, win_end + 1))

        # --- Spacing statistics (pairwise distances within the window) ---
        spacings = _window_spacing(centroids, win_start, win_end)
        if len(spacings) == 0:
            mean_spacing = 0.0
            median_spacing = 0.0
            std_spacing = 0.0
        else:
            mean_spacing = float(np.mean(spacings))
            median_spacing = float(np.median(spacings))
            std_spacing = _safe_std(spacings)

        # --- Offset statistics ---
        win_offsets = offset_vals[win_start : win_end + 1]
        mean_offset = float(np.mean(win_offsets))
        median_offset = float(np.median(win_offsets))
        std_offset = _safe_std(win_offsets)

        # --- Volume statistics ---
        win_volumes = volume_vals[win_start : win_end + 1]
        mean_volume = float(np.mean(win_volumes))
        median_volume = float(np.median(win_volumes))
        std_volume = _safe_std(win_volumes)

        # --- Deviation score ---
        # Index of the focal vertebra within the window slice.
        focal_idx_in_window = i - win_start
        score = _deviation_score(
            focal_offset=float(offset_vals[i]),
            focal_volume=float(volume_vals[i]),
            win_offsets=win_offsets,
            win_volumes=win_volumes,
            focal_idx_in_window=focal_idx_in_window,
        )

        is_outlier = bool(score >= outlier_threshold)

        records.append(
            VertebralNeighbourhood(
                label=int(c.label),
                level_name=c.level_name,
                window_labels=window_labels,
                mean_spacing_mm=mean_spacing,
                median_spacing_mm=median_spacing,
                std_spacing_mm=std_spacing,
                mean_offset_mm=mean_offset,
                median_offset_mm=median_offset,
                std_offset_mm=std_offset,
                mean_volume_mm3=mean_volume,
                median_volume_mm3=median_volume,
                std_volume_mm3=std_volume,
                deviation_score=score,
                is_outlier=is_outlier,
            )
        )

    return records
