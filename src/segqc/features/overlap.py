"""Voxel-level overlap detection between vertebra labels (item 015).

Detects voxels shared by two or more label channels in a boolean mask stack
and returns one :class:`OverlapPair` per overlapping pair.

Standard 3-D integer label maps cannot represent a voxel belonging to two
labels simultaneously (only one integer fits per voxel).  This module
therefore accepts a **boolean mask stack**: a 4-D numpy array of shape
``(n_labels, X, Y, Z)`` together with a 1-D array of label integers of length
``n_labels``.  A voxel at ``(x, y, z)`` is considered overlapping for labels
``i`` and ``j`` when both ``stack[i, x, y, z]`` and ``stack[j, x, y, z]``
are ``True``.

Public API
----------
``OverlapPair``
    Frozen dataclass carrying the result for a single overlapping label pair.
``detect_overlaps(mask_stack, labels, convention=None) -> list[OverlapPair]``
    Find all overlapping pairs in a boolean mask stack.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import List, Optional

import numpy as np

from segqc.labels import LabelConvention

__all__ = [
    "OverlapPair",
    "detect_overlaps",
]


# --------------------------------------------------------------------------- #
# OverlapPair dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OverlapPair:
    """Record for a single pair of overlapping labels.

    Pair ordering is always enforced: ``label_a < label_b``.

    Attributes
    ----------
    label_a:
        The lower integer label value of the pair.
    label_b:
        The higher integer label value of the pair.
    name_a:
        Anatomical vertebra name for ``label_a`` from the
        :class:`~segqc.labels.LabelConvention`, or
        :data:`~segqc.labels.UNKNOWN` for unmapped integers.
    name_b:
        Anatomical vertebra name for ``label_b``.
    overlap_voxels:
        Number of voxels that belong to both labels simultaneously.
    """

    label_a: int
    label_b: int
    name_a: str
    name_b: str
    overlap_voxels: int


# --------------------------------------------------------------------------- #
# Core detection function
# --------------------------------------------------------------------------- #


def detect_overlaps(
    mask_stack: np.ndarray,
    labels: np.ndarray,
    convention: Optional[LabelConvention] = None,
) -> List[OverlapPair]:
    """Detect voxel-level overlap between every pair of label channels.

    The function is **read-only** — the input arrays are never modified.  It is
    **deterministic**: identical inputs always produce identical outputs.

    Parameters
    ----------
    mask_stack:
        Boolean 4-D array of shape ``(n_labels, X, Y, Z)``.  Each channel
        ``mask_stack[i]`` is the binary foreground mask for label
        ``labels[i]``.  A voxel set to ``True`` in two or more channels is
        considered overlapping.
    labels:
        1-D integer array of length ``n_labels`` mapping channel index to
        label integer.  Must be the same length as ``mask_stack.shape[0]``.
    convention:
        Optional :class:`~segqc.labels.LabelConvention` used to resolve
        anatomical names.  Defaults to the shipped TotalSegmentator / VerSe
        convention when ``None``.

    Returns
    -------
    list[OverlapPair]
        One :class:`OverlapPair` per pair with at least one shared voxel.
        Pairs with zero shared voxels are omitted.  The list is sorted by
        ``(label_a, label_b)`` for deterministic ordering.
    """
    if convention is None:
        convention = LabelConvention.default()

    n_labels = mask_stack.shape[0]
    if n_labels < 2:
        return []

    result: List[OverlapPair] = []

    for i, j in combinations(range(n_labels), 2):
        # Bitwise AND over the two boolean channels counts shared voxels.
        overlap_count = int(np.count_nonzero(mask_stack[i] & mask_stack[j]))
        if overlap_count == 0:
            continue

        # Enforce label_a < label_b ordering.
        raw_a = int(labels[i])
        raw_b = int(labels[j])
        if raw_a > raw_b:
            raw_a, raw_b = raw_b, raw_a

        result.append(
            OverlapPair(
                label_a=raw_a,
                label_b=raw_b,
                name_a=convention.name_of(raw_a),
                name_b=convention.name_of(raw_b),
                overlap_voxels=overlap_count,
            )
        )

    result.sort(key=lambda p: (p.label_a, p.label_b))
    return result
