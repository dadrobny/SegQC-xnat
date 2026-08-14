"""Local vertebra neighbourhood comparison, generalised (item 110; item 024).

For each element in an ordered sequence, compute sliding-window statistics
over the surrounding neighbours for an arbitrary, caller-named set of
features:

* Mean, median, and std of every named feature within the window (the window
  always includes the focal element).
* A leave-one-out z-score per feature: the focal element's value compared
  against the *remaining* window members only (its neighbours, not itself).
* A per-element **deviation score** (non-negative scalar), the ``max`` of the
  leave-one-out z-scores of a caller-selected scored subset of the features.
* An **outlier flag** when the deviation score exceeds a configurable
  threshold.

The window of width ``n`` centred at position ``i`` spans indices
``max(0, i - n//2)`` to ``min(len-1, i + n//2)`` inclusive. At the boundaries
the window is asymmetric but the focal element is always included.

Item 110 generalisation
------------------------
The pre-item-110 API took three fixed typed arguments (``centroids``,
``offsets``, ``geometries``) and computed inter-centroid spacing internally
via ``_window_spacing``. The mechanism itself -- leave-one-out z-score of a
focal element against a sliding window of its neighbours -- is entirely
feature-agnostic, so it now takes an ordered element sequence plus a
``{feature_name: values}`` mapping:

* ``spacing_mm`` is now a **caller-supplied per-element value**, not an
  internally computed pairwise inter-centroid distance. The caller (
  ``pipeline.py``) is responsible for deriving one spacing value per element
  (see that module for the boundary convention used at the first/last
  element).
* Any number of named features may be passed; which subset is scored into
  ``deviation_score`` is the ``scored`` parameter, not a hardcoded pair.
* ``DEFAULT_FEATURES``/``DEFAULT_SCORED`` reproduce the historical three
  features and historical scored pair exactly, so the pre-refactor
  ``deviation_score``/``is_outlier`` behaviour is unchanged under the
  defaults (AC5). ``UNSCORED_RATIONALE`` documents the one default feature
  that is reported but deliberately not scored, closing the historical
  silent mismatch where ``spacing_mm`` was reported but never fed into
  ``_deviation_score``.

Public API
----------
``FeatureWindowStats``
    Frozen dataclass: ``mean``/``median``/``std`` (over the whole window,
    including the focal element) plus a leave-one-out ``z_score`` (excluding
    the focal element) for one named feature.
``VertebralNeighbourhood``
    Frozen dataclass with per-element neighbourhood statistics.
``DEFAULT_FEATURES``
    ``("spacing_mm", "offset_mm", "volume_mm3")`` -- the historical three.
``DEFAULT_SCORED``
    ``("offset_mm", "volume_mm3")`` -- the historical scored pair.
``UNSCORED_RATIONALE``
    ``{feature_name: reason}`` for every ``DEFAULT_FEATURES`` name not in
    ``DEFAULT_SCORED``.
``compute_neighbourhood_features(elements, features, *, scored=DEFAULT_SCORED,
    window_n=3, outlier_threshold=2.0) -> List[VertebralNeighbourhood]``
    Compute one record per element.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np

__all__ = [
    "FeatureWindowStats",
    "VertebralNeighbourhood",
    "DEFAULT_FEATURES",
    "DEFAULT_SCORED",
    "UNSCORED_RATIONALE",
    "compute_neighbourhood_features",
]


# --------------------------------------------------------------------------- #
# Default feature selection (item 110 AC4/AC5)
# --------------------------------------------------------------------------- #

# The historical three base features (pre-item-110 fixed fields).
DEFAULT_FEATURES: Tuple[str, ...] = ("spacing_mm", "offset_mm", "volume_mm3")

# The historical scored pair -- matches pre-item-110 _deviation_score exactly.
DEFAULT_SCORED: Tuple[str, ...] = ("offset_mm", "volume_mm3")

# AC4: every DEFAULT_FEATURES name not in DEFAULT_SCORED must carry a
# non-empty, documented reason here -- reconciles "reported but unscored" so
# the historical silent spacing_mm mismatch cannot recur undocumented.
UNSCORED_RATIONALE: Dict[str, str] = {
    "spacing_mm": (
        "spacing_mm is a caller-supplied per-element value (see "
        "pipeline.py::extract_feature_record for the boundary convention "
        "used at the first/last element), not a geometric quantity this "
        "module derives. It is reported for context but deliberately "
        "excluded from deviation_score so the default scored pair matches "
        "the pre-item-110 implementation exactly (item 110 AC5); scoring "
        "spacing is left to a future item with its own threshold "
        "calibration."
    ),
}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FeatureWindowStats:
    """Window statistics for one named feature at one focal element.

    Attributes
    ----------
    mean, median, std:
        Computed over the *whole* window (including the focal element).
    z_score:
        Leave-one-out z-score: the focal element's value compared against
        the window's *other* members only (excluding itself). ``0.0`` when
        the window has no neighbours (e.g. ``window_n == 1``).
    """

    mean: float
    median: float
    std: float
    z_score: float


@dataclass(frozen=True)
class VertebralNeighbourhood:
    """Per-element local neighbourhood statistics.

    Attributes
    ----------
    label:
        Integer label value of the focal element.
    level_name:
        Anatomical name of the focal element.
    window_labels:
        Integer label values of all elements in the window (including focal).
    stats:
        ``{feature_name: FeatureWindowStats}`` -- one entry per name in the
        ``features`` mapping passed to :func:`compute_neighbourhood_features`.
    deviation_score:
        Per-element scalar summarising how anomalous the focal element is
        relative to its neighbours (non-negative; 0 = perfectly consistent):
        the ``max`` of the leave-one-out z-scores of the ``scored`` feature
        subset.
    is_outlier:
        True when deviation_score exceeds the configured threshold.
    """

    label: int
    level_name: str
    window_labels: Tuple[int, ...]
    stats: Mapping[str, FeatureWindowStats]
    deviation_score: float
    is_outlier: bool


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

# Minimum std denominator to avoid division by zero when all neighbour values
# are identical. Chosen to be safely below any real deviation of interest
# while keeping the normalised score meaningful.
_MIN_STD: float = 1e-6


def _safe_std(values: np.ndarray) -> float:
    """Return std of *values*; returns 0.0 when fewer than 2 elements."""
    if len(values) < 2:
        return 0.0
    return float(np.std(values, ddof=0))


def _leave_one_out_z(window_values: np.ndarray, focal_idx: int, focal_value: float) -> float:
    """Leave-one-out z-score of ``focal_value`` against the *other* window
    members (excludes ``window_values[focal_idx]`` from the neighbour mean
    and std). Returns 0.0 when there are no neighbours (single-element
    window). Uses ``_MIN_STD`` as a floor for a near-zero neighbour std.
    """
    neighbours = np.concatenate(
        [window_values[:focal_idx], window_values[focal_idx + 1:]]
    )
    if len(neighbours) == 0:
        return 0.0
    mean_n = float(np.mean(neighbours))
    std_n = max(float(np.std(neighbours, ddof=0)), _MIN_STD)
    return abs(focal_value - mean_n) / std_n


# --------------------------------------------------------------------------- #
# Public compute function
# --------------------------------------------------------------------------- #


def compute_neighbourhood_features(
    elements: Sequence,
    features: Mapping[str, Sequence[float]],
    *,
    scored: Sequence[str] = DEFAULT_SCORED,
    window_n: int = 3,
    outlier_threshold: float = 2.0,
) -> List[VertebralNeighbourhood]:
    """Compute local neighbourhood statistics for each element.

    Parameters
    ----------
    elements:
        Ordered (head-to-tail anatomical) sequence of objects exposing
        ``.label`` (int) and ``.level_name`` (str) -- e.g.
        ``segfacet.features.centroids.LabelCentroid``. Must have >= 1 entry;
        raises ``ValueError`` when empty.
    features:
        ``{feature_name: values}``, each ``values`` sequence the same length
        and order as ``elements``. Any number of named features is accepted.
        Every value must be finite (a NaN/inf value raises ``ValueError``).
        Never mutated.
    scored:
        The subset of ``features`` keys whose leave-one-out z-scores are
        combined (``max``) into ``deviation_score``. Duplicate names are
        deduplicated. Every name must be present in ``features`` -- an
        absent name raises ``ValueError`` naming it. Defaults to
        :data:`DEFAULT_SCORED`.
    window_n:
        Total window width (must be >= 1). Default 3 (= focal + 1 on each
        side). Raises ``ValueError`` when ``window_n < 1``.
    outlier_threshold:
        Deviation score threshold above which an element is flagged as an
        outlier. Default 2.0.

    Returns
    -------
    List[VertebralNeighbourhood]
        One record per element, in the same order as the input sequence.

    Raises
    ------
    ValueError
        When ``elements`` is empty, ``window_n < 1``, a feature's values
        contain a non-finite (NaN/inf) entry, a feature's length does not
        match ``len(elements)``, or a ``scored`` name is absent from
        ``features``.
    """
    if len(elements) == 0:
        raise ValueError(
            "compute_neighbourhood_features requires at least one element, "
            "but received an empty sequence."
        )
    if window_n < 1:
        raise ValueError(f"window_n must be >= 1, got {window_n!r}.")

    n = len(elements)
    half = window_n // 2

    feature_arrays: Dict[str, np.ndarray] = {}
    for name, values in features.items():
        if len(values) != n:
            raise ValueError(
                f"features[{name!r}] has length {len(values)}, expected "
                f"{n} (one value per element)."
            )
        arr = np.array([float(v) for v in values], dtype=np.float64)
        if not np.all(np.isfinite(arr)):
            raise ValueError(
                f"features[{name!r}] contains a non-finite (NaN/inf) value; "
                "all feature values must be finite."
            )
        feature_arrays[name] = arr

    # Dedupe scored names, preserving order; validate presence.
    scored_names = list(dict.fromkeys(scored))
    for name in scored_names:
        if name not in feature_arrays:
            raise ValueError(
                f"scored feature {name!r} is not present in the features "
                f"mapping (available: {sorted(feature_arrays)})."
            )

    records: List[VertebralNeighbourhood] = []

    for i in range(n):
        win_start = max(0, i - half)
        win_end = min(n - 1, i + half)
        focal_idx_in_window = i - win_start

        window_labels = tuple(int(elements[j].label) for j in range(win_start, win_end + 1))

        stats: Dict[str, FeatureWindowStats] = {}
        z_by_name: Dict[str, float] = {}
        for name, arr in feature_arrays.items():
            window_vals = arr[win_start : win_end + 1]
            mean_v = float(np.mean(window_vals))
            median_v = float(np.median(window_vals))
            std_v = _safe_std(window_vals)
            z = _leave_one_out_z(window_vals, focal_idx_in_window, float(arr[i]))
            stats[name] = FeatureWindowStats(
                mean=mean_v, median=median_v, std=std_v, z_score=z
            )
            z_by_name[name] = z

        score = max((z_by_name[name] for name in scored_names), default=0.0)
        is_outlier = bool(score >= outlier_threshold)

        records.append(
            VertebralNeighbourhood(
                label=int(elements[i].label),
                level_name=elements[i].level_name,
                window_labels=window_labels,
                stats=stats,
                deviation_score=float(score),
                is_outlier=is_outlier,
            )
        )

    return records
