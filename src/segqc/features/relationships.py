"""Inter-vertebra relationships (item 014).

Given an ordered sequence of :class:`~segqc.features.centroids.LabelCentroid`
records, computes:

* **present_levels** — anatomical names in canonical head-to-tail order.
* **missing_levels** — levels absent within the observed span [min..max].
* **neighbour_spacings_mm** — Euclidean distances between adjacent centroids
  (in canonical order).
* **is_continuous** — whether the *input* order is monotonically non-decreasing
  in canonical rank.
* **out_of_order_labels** — labels (in input order) that broke monotonicity.

Public API
----------
``SpineRelationships``
    Frozen dataclass carrying the result.
``compute_spine_relationships(centroids, convention=None) -> SpineRelationships``
    Entry-point function.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from segqc.features.centroids import LabelCentroid
from segqc.labels import CANONICAL_ORDER, UNKNOWN, LabelConvention

__all__ = [
    "SpineRelationships",
    "compute_spine_relationships",
]

# Canonical rank for O(1) comparisons.
_CANONICAL_RANK: dict[str, int] = {name: i for i, name in enumerate(CANONICAL_ORDER)}


@dataclass(frozen=True)
class SpineRelationships:
    """Inter-vertebra relationship record for a single segmentation case.

    Attributes
    ----------
    present_levels:
        Anatomical names of the recognised labels in canonical head-to-tail order.
    missing_levels:
        Levels absent within the [min_present .. max_present] span, in canonical order.
    neighbour_spacings_mm:
        Euclidean distances (mm) between adjacent centroids in canonical order.
        Length is ``len(present_levels) - 1``; empty when fewer than 2 levels present.
    is_continuous:
        ``True`` iff the *input* order of level names is monotonically
        non-decreasing in canonical rank.
    out_of_order_labels:
        Label names (in input order) that broke monotonicity. Empty when
        ``is_continuous`` is ``True``.
    """

    present_levels: List[str]
    missing_levels: List[str]
    neighbour_spacings_mm: List[float]
    is_continuous: bool
    out_of_order_labels: List[str]


def compute_spine_relationships(
    centroids: Sequence[LabelCentroid],
    convention: Optional[LabelConvention] = None,
) -> SpineRelationships:
    """Compute inter-vertebra relationships from an ordered centroid sequence.

    Parameters
    ----------
    centroids:
        Sequence of :class:`~segqc.features.centroids.LabelCentroid` records.
        May be supplied in any order; ``present_levels`` is always in canonical
        order. ``UNKNOWN`` and non-canonical level names are silently skipped.
    convention:
        Unused — reserved for API symmetry with sibling functions. Level names
        are read directly from ``LabelCentroid.level_name`` and compared against
        :data:`~segqc.labels.CANONICAL_ORDER`.

    Returns
    -------
    SpineRelationships
    """
    # Keep only centroids whose level_name is in CANONICAL_ORDER.
    # UNKNOWN and any custom/non-canonical names are silently skipped.
    known = [c for c in centroids if c.level_name in _CANONICAL_RANK]

    # --- AC4: continuity assessed against *input* order of known centroids --- #
    is_continuous = True
    out_of_order_labels: List[str] = []
    prev_rank = -1
    for c in known:
        rank = _CANONICAL_RANK[c.level_name]
        if rank < prev_rank:
            is_continuous = False
            out_of_order_labels.append(c.level_name)
        else:
            prev_rank = rank

    # --- AC1: sort known centroids by canonical rank for remaining computations --- #
    sorted_centroids = sorted(known, key=lambda c: _CANONICAL_RANK[c.level_name])
    present_levels: List[str] = [c.level_name for c in sorted_centroids]

    # --- AC2: missing levels within the span [min_present .. max_present] --- #
    missing_levels: List[str] = []
    if len(present_levels) >= 2:
        lo = _CANONICAL_RANK[present_levels[0]]
        hi = _CANONICAL_RANK[present_levels[-1]]
        present_set = set(present_levels)
        missing_levels = [
            name
            for name in CANONICAL_ORDER[lo : hi + 1]
            if name not in present_set
        ]

    # --- AC3: neighbour spacings in canonical order --- #
    neighbour_spacings_mm: List[float] = []
    for i in range(len(sorted_centroids) - 1):
        a = sorted_centroids[i].centroid_mm
        b = sorted_centroids[i + 1].centroid_mm
        dist = math.sqrt(sum((bi - ai) ** 2 for ai, bi in zip(a, b)))
        neighbour_spacings_mm.append(float(dist))

    return SpineRelationships(
        present_levels=present_levels,
        missing_levels=missing_levels,
        neighbour_spacings_mm=neighbour_spacings_mm,
        is_continuous=is_continuous,
        out_of_order_labels=out_of_order_labels,
    )
