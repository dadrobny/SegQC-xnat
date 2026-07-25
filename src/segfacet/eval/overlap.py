"""DICE-vs-GT segmentation-overlap metrics, per label and aggregate (item 050).

This is the §8 **level-2** evaluation primitive: given a **candidate** instance
label map and a **ground-truth (GT)** instance label map (numpy integer
arrays of identical shape) plus voxel spacing, it computes per-label DICE
(Sorensen-Dice) and Jaccard overlap scores and two aggregate summaries over
the labels present in both maps.

Pure and spacing-aware: no file I/O, no mutation of the input arrays.
Matching is by **integer label value** (not name) — both maps are assumed to
share the same integer-to-anatomy scheme (vision Sec. 10), so label ``22`` in
the candidate is compared against label ``22`` in the GT regardless of what
anatomical name it maps to. A single :class:`~segfacet.labels.LabelConvention`
(default :meth:`~segfacet.labels.LabelConvention.default`) is used only to attach
a display ``name`` to each entry and to order ``per_label`` head-to-tail;
matching itself never depends on it, so two distinct unmapped labels are never
collapsed into one "unknown" bucket.

DICE and Jaccard, for label value ``v`` with candidate voxel count ``a``, GT
voxel count ``b``, and intersection voxel count ``i``:

    dice    = 2 * i / (a + b)
    jaccard = i / (a + b - i)

A label present in only one of the two maps is reported as an **unmatched**
entry (``dice == jaccard == 0.0``, the absent side's voxel count ``0``) rather
than raising, and is excluded from the aggregates.

This module is unrelated to :mod:`segfacet.features.overlap` (item 015), which
detects voxels shared by two or more labels *within a single* boolean mask
stack (a self-overlap/QC-flag concern); this module compares two *separate*
label maps against each other for evaluation purposes.

Public API
----------
``LabelOverlap``
    Frozen dataclass carrying the per-label overlap result.
``OverlapResult``
    Frozen dataclass carrying the full per-label breakdown plus aggregates.
``compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0), *, convention=None)
    -> OverlapResult``
    Compute per-label and aggregate DICE/Jaccard overlap between two label maps.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from segfacet.io import FacetInputError
from segfacet.labels import CANONICAL_ORDER, LabelConvention

__all__ = [
    "compute_overlap",
    "LabelOverlap",
    "OverlapResult",
]

_UNRECOGNISED_RANK = len(CANONICAL_ORDER)
_CANONICAL_RANK = {name: i for i, name in enumerate(CANONICAL_ORDER)}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LabelOverlap:
    """Per-label DICE/Jaccard overlap between a candidate and a GT label map.

    Attributes
    ----------
    value:
        The integer label value this entry matches on.
    name:
        Anatomical display name from the :class:`~segfacet.labels.LabelConvention`
        used (``segfacet.labels.UNKNOWN`` if unmapped). Naming/ordering only —
        matching is always by ``value``.
    matched:
        ``True`` when ``value`` is present (non-zero voxel count) in **both**
        maps; ``False`` when present in only one (an unmatched entry).
    dice:
        Sorensen-Dice coefficient, ``2 * intersection / (candidate + gt)``.
        ``0.0`` for an unmatched entry.
    jaccard:
        Jaccard index, ``intersection / (candidate + gt - intersection)``.
        ``0.0`` for an unmatched entry.
    candidate_voxels:
        Voxel count of this label in ``candidate`` (``0`` if absent).
    gt_voxels:
        Voxel count of this label in ``gt`` (``0`` if absent).
    intersection_voxels:
        Voxel count shared by both maps for this label.
    physical_volume_mm3:
        GT physical volume of this label: ``gt_voxels * sx * sy * sz``.
    """

    value: int
    name: str
    matched: bool
    dice: float
    jaccard: float
    candidate_voxels: int
    gt_voxels: int
    intersection_voxels: int
    physical_volume_mm3: float


@dataclass(frozen=True)
class OverlapResult:
    """Full per-label breakdown plus aggregate overlap scores.

    Attributes
    ----------
    per_label:
        One :class:`LabelOverlap` per label value present in ``candidate`` and/
        or ``gt`` (background excluded), ordered head-to-tail by
        :data:`segfacet.labels.CANONICAL_ORDER` for recognised labels then by
        ascending ``value`` for unrecognised ones.
    mean_dice:
        Unweighted arithmetic mean of ``dice`` over **matched** entries only;
        ``None`` if there are no matched entries.
    volume_weighted_dice:
        ``dice`` averaged over matched entries, weighted by each entry's
        ``physical_volume_mm3``; ``None`` if there are no matched entries or
        the total weight is ``0``.
    mean_jaccard:
        Unweighted arithmetic mean of ``jaccard`` over matched entries only;
        ``None`` if there are no matched entries.
    n_matched:
        Number of entries with ``matched is True``.
    n_unmatched:
        Number of entries with ``matched is False``.
    """

    per_label: Tuple[LabelOverlap, ...]
    mean_dice: Optional[float]
    volume_weighted_dice: Optional[float]
    mean_jaccard: Optional[float]
    n_matched: int
    n_unmatched: int


# --------------------------------------------------------------------------- #
# Ordering helper
# --------------------------------------------------------------------------- #


def _order_key(value: int, name: str) -> Tuple[int, int]:
    """Sort key placing canonically-recognised labels in anatomical order.

    Mirrors ``segfacet.labels._order_key`` but keys on the integer ``value``
    (not the name) for the tie-break, since matching here is value-based and
    two distinct unrecognised labels must never collide onto one sort slot.
    """
    return (_CANONICAL_RANK.get(name, _UNRECOGNISED_RANK), value)


# --------------------------------------------------------------------------- #
# compute_overlap
# --------------------------------------------------------------------------- #


def compute_overlap(
    candidate: np.ndarray,
    gt: np.ndarray,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    *,
    convention: Optional[LabelConvention] = None,
) -> OverlapResult:
    """Compute per-label and aggregate DICE/Jaccard overlap vs a GT label map.

    Parameters
    ----------
    candidate, gt:
        Integer label-map arrays of identical ``shape``. Background (``0``) is
        excluded from comparison. Never mutated.
    spacing:
        ``(sx, sy, sz)`` physical voxel spacing, used only to scale
        ``physical_volume_mm3`` and weight ``volume_weighted_dice``; per-label
        ``dice``/``jaccard`` are pure voxel-count ratios and do not depend on
        it. Defaults to isotropic ``(1.0, 1.0, 1.0)``.
    convention:
        The :class:`~segfacet.labels.LabelConvention` used to name and order
        entries. Defaults to :meth:`~segfacet.labels.LabelConvention.default`.
        Matching is always by integer label value regardless of convention.

    Returns
    -------
    OverlapResult

    Raises
    ------
    segfacet.io.FacetInputError
        If ``candidate.shape != gt.shape``.
    """
    if convention is None:
        convention = LabelConvention.default()

    candidate = np.asarray(candidate)
    gt = np.asarray(gt)
    if candidate.shape != gt.shape:
        raise FacetInputError(
            "compute_overlap: candidate and gt must have identical shape; "
            f"got {candidate.shape!r} vs {gt.shape!r}."
        )

    sx, sy, sz = spacing
    voxel_volume = float(sx) * float(sy) * float(sz)

    label_values = sorted(
        ({int(v) for v in np.unique(candidate)} | {int(v) for v in np.unique(gt)})
        - {0}
    )

    entries = []
    for value in label_values:
        cand_mask = candidate == value
        gt_mask = gt == value
        a = int(cand_mask.sum())
        b = int(gt_mask.sum())
        i = int(np.logical_and(cand_mask, gt_mask).sum())
        matched = a > 0 and b > 0
        dice = (2.0 * i / (a + b)) if (a + b) > 0 else 0.0
        jaccard = (i / (a + b - i)) if (a + b - i) > 0 else 0.0
        name = convention.name_of(value)
        entries.append(
            LabelOverlap(
                value=value,
                name=name,
                matched=matched,
                dice=dice,
                jaccard=jaccard,
                candidate_voxels=a,
                gt_voxels=b,
                intersection_voxels=i,
                physical_volume_mm3=b * voxel_volume,
            )
        )

    entries.sort(key=lambda e: _order_key(e.value, e.name))

    matched_entries = [e for e in entries if e.matched]
    n_matched = len(matched_entries)
    n_unmatched = len(entries) - n_matched

    if n_matched == 0:
        mean_dice = None
        mean_jaccard = None
        volume_weighted_dice = None
    else:
        mean_dice = sum(e.dice for e in matched_entries) / n_matched
        mean_jaccard = sum(e.jaccard for e in matched_entries) / n_matched
        total_weight = sum(e.physical_volume_mm3 for e in matched_entries)
        if total_weight > 0:
            volume_weighted_dice = (
                sum(e.dice * e.physical_volume_mm3 for e in matched_entries)
                / total_weight
            )
        else:
            volume_weighted_dice = None

    return OverlapResult(
        per_label=tuple(entries),
        mean_dice=mean_dice,
        volume_weighted_dice=volume_weighted_dice,
        mean_jaccard=mean_jaccard,
        n_matched=n_matched,
        n_unmatched=n_unmatched,
    )
