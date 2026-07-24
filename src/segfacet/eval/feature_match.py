"""Feature-set match / divergence-by-label, candidate vs GT (item 051).

This is the §8 **level-3** evaluation primitive: given the **already-extracted**
Stage 2-3 ``features`` block dicts (as produced by
``segfacet.pipeline.extract_feature_record`` / ``segfacet.feature_report.build_features_block``)
of a **candidate** case and its **ground-truth (GT)** case, it compares them
per anatomical (integer) label and reports per-feature differences, a
per-label divergence score, and a per-label centroid displacement, plus
case-level aggregates.

Pure and reuse-only: this module never recomputes geometry, extents,
centroids, or spline offsets from label-map arrays -- it reads the values the
Stage 2-3 feature engine already computed and does no file or array I/O.
Matching is by **integer label value** (mirroring item 050's decision): both
blocks are assumed to share the same integer-to-anatomy scheme (vision
Sec. 10), so label ``22`` in candidate is compared with label ``22`` in GT.
The anatomical ``name`` attached to each entry comes straight from the
block's ``level_name`` field (GT side authoritative for a matched label) --
:data:`segfacet.labels.CANONICAL_ORDER` / :data:`segfacet.labels.UNKNOWN` supply
only display ordering and the unknown-name sentinel, never the match key, so
two distinct unmapped labels are never collapsed into one bucket.

Tracked scalar features (:data:`TRACKED_FEATURES`, a fixed, documented,
non-configurable ordered set):

    physical_volume_mm3, extent_x_mm, extent_y_mm, extent_z_mm,
    spline_offset_mm

The first four are read from a label entry's ``geometry`` sub-dict;
``spline_offset_mm`` is the Stage-3 per-label perpendicular offset read from
the block's ``stage3.per_label_offsets`` list and is legitimately absent for
Stage-2-only blocks (marked ``available=False``, never an error).

For each tracked feature, per matched label:

    absolute = candidate_value - gt_value                    (signed)
    relative = absolute / gt_value   if gt_value != 0 else None

A feature missing from either side is ``available=False`` with
``absolute``/``relative`` both ``None``. The per-label ``divergence_score``
is the mean of ``abs(relative)`` over tracked features that are available on
both sides *and* have a defined ``relative``; ``None`` if none qualify.

Centroid displacement (``centroid_distance_mm``, the Euclidean distance
between the two sides' ``centroid_mm`` vectors) is reported **separately**,
never folded into ``divergence_score`` -- a mm displacement has no natural
dimensionless denominator, so mixing it into the mean-of-relatives score
would either dimension the score or require an arbitrary length scale.

A label present on only one side is an **unmatched** entry (``matched=False``,
empty ``differences``, ``None`` scores) -- never dropped, never a crash --
and is excluded from the case-level aggregates.

This module is unrelated to item 050's :mod:`segfacet.eval.overlap` (voxel-level
DICE/Jaccard on label maps) and item 052 (verdict-outcome classification); it
produces per-case, per-label feature-divergence numbers only, with no
cross-case aggregation, calibration, or flag/verdict interpretation (items
053-055).

Public API
----------
``TRACKED_FEATURES``
    The fixed, ordered tuple of tracked scalar feature names.
``FeatureDifference``
    Frozen dataclass carrying one tracked feature's candidate/GT values and
    absolute/relative difference.
``LabelFeatureDivergence``
    Frozen dataclass carrying one label's full comparison (differences,
    centroid displacement, divergence score).
``FeatureMatchResult``
    Frozen dataclass carrying the full per-label breakdown plus case-level
    aggregates.
``compute_feature_match(candidate, gt) -> FeatureMatchResult``
    Compute per-label and case-level feature-set divergence between two
    ``features`` block dicts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from segfacet.io import FacetInputError
from segfacet.labels import CANONICAL_ORDER, UNKNOWN

__all__ = [
    "compute_feature_match",
    "TRACKED_FEATURES",
    "FeatureDifference",
    "LabelFeatureDivergence",
    "FeatureMatchResult",
]

TRACKED_FEATURES: Tuple[str, ...] = (
    "physical_volume_mm3",
    "extent_x_mm",
    "extent_y_mm",
    "extent_z_mm",
    "spline_offset_mm",
)

_UNRECOGNISED_RANK = len(CANONICAL_ORDER)
_CANONICAL_RANK = {name: i for i, name in enumerate(CANONICAL_ORDER)}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FeatureDifference:
    """One tracked feature's candidate/GT values and difference for a label.

    Attributes
    ----------
    feature:
        The tracked feature name (one of :data:`TRACKED_FEATURES`).
    candidate_value:
        The value read from the candidate block's entry, or ``None`` if
        absent.
    gt_value:
        The value read from the GT block's entry, or ``None`` if absent.
    absolute:
        ``candidate_value - gt_value`` (signed); ``None`` unless both values
        are available.
    relative:
        ``absolute / gt_value``; ``None`` unless both values are available
        *and* ``gt_value != 0`` (avoids divide-by-zero).
    available:
        ``True`` only when both ``candidate_value`` and ``gt_value`` are
        present.
    """

    feature: str
    candidate_value: Optional[float]
    gt_value: Optional[float]
    absolute: Optional[float]
    relative: Optional[float]
    available: bool


@dataclass(frozen=True)
class LabelFeatureDivergence:
    """One label's full candidate-vs-GT feature comparison.

    Attributes
    ----------
    value:
        The integer label value this entry matches on.
    name:
        Anatomical display name -- the GT entry's ``level_name`` for a
        matched label (GT is the reference truth), else the present side's
        ``level_name`` for an unmatched label (``segfacet.labels.UNKNOWN`` if
        absent/unmapped). Naming/ordering only -- matching is always by
        ``value``.
    matched:
        ``True`` when ``value`` is present in **both** blocks' ``per_label``;
        ``False`` when present in only one (an unmatched entry).
    differences:
        One :class:`FeatureDifference` per :data:`TRACKED_FEATURES`, in
        order, for a matched label; ``()`` for an unmatched one.
    centroid_distance_mm:
        Euclidean distance between the candidate and GT ``centroid_mm``
        vectors; ``None`` for an unmatched label or if either side's
        centroid is missing.
    divergence_score:
        Mean of ``abs(relative)`` over tracked features that are
        ``available`` and have a defined ``relative``; ``None`` if no
        tracked feature qualifies (including for an unmatched label).
    """

    value: int
    name: str
    matched: bool
    differences: Tuple[FeatureDifference, ...]
    centroid_distance_mm: Optional[float]
    divergence_score: Optional[float]


@dataclass(frozen=True)
class FeatureMatchResult:
    """Full per-label breakdown plus case-level feature-divergence aggregates.

    Attributes
    ----------
    per_label:
        One :class:`LabelFeatureDivergence` per label value present in
        ``candidate`` and/or ``gt``, ordered head-to-tail by
        :data:`segfacet.labels.CANONICAL_ORDER` for recognised names then by
        ascending ``value`` for unrecognised ones.
    case_divergence:
        Unweighted arithmetic mean of ``divergence_score`` over **matched**
        entries with a defined score; ``None`` if none qualify.
    mean_centroid_distance_mm:
        Unweighted arithmetic mean of ``centroid_distance_mm`` over matched
        entries with a defined distance; ``None`` if none qualify.
    n_matched:
        Number of entries with ``matched is True``.
    n_unmatched:
        Number of entries with ``matched is False``.
    """

    per_label: Tuple[LabelFeatureDivergence, ...]
    case_divergence: Optional[float]
    mean_centroid_distance_mm: Optional[float]
    n_matched: int
    n_unmatched: int


# --------------------------------------------------------------------------- #
# Input validation + accessors
# --------------------------------------------------------------------------- #


def _require_block(obj: Any, side: str) -> Mapping[str, Any]:
    """Validate ``obj`` is a features-block mapping with a ``per_label`` mapping."""
    if not isinstance(obj, Mapping):
        raise FacetInputError(
            f"compute_feature_match: {side} must be a features block mapping "
            f"(dict-like); got {type(obj).__name__!r}."
        )
    per_label = obj.get("per_label")
    if not isinstance(per_label, Mapping):
        raise FacetInputError(
            f"compute_feature_match: {side} must have a 'per_label' mapping; "
            f"got {type(per_label).__name__!r}."
        )
    return obj


def _offset_map(block: Mapping[str, Any]) -> Dict[int, float]:
    """Build ``{label: offset_mm}`` from ``block.stage3.per_label_offsets``."""
    stage3 = block.get("stage3") or {}
    offsets = stage3.get("per_label_offsets") or []
    return {int(o["label"]): float(o["offset_mm"]) for o in offsets}


def _scalar_value(
    entry: Optional[Mapping[str, Any]],
    offset_map: Dict[int, float],
    label: int,
    feature: str,
) -> Optional[float]:
    """Read one tracked feature's value for a label entry, or ``None`` if absent."""
    if feature == "spline_offset_mm":
        return offset_map.get(label)
    if entry is None:
        return None
    geometry = entry.get("geometry") or {}
    value = geometry.get(feature)
    return None if value is None else float(value)


def _order_key(value: int, name: str) -> Tuple[int, int]:
    """Sort key placing canonically-recognised labels in anatomical order."""
    return (_CANONICAL_RANK.get(name, _UNRECOGNISED_RANK), value)


def _centroid_distance(
    cand_entry: Optional[Mapping[str, Any]],
    gt_entry: Optional[Mapping[str, Any]],
) -> Optional[float]:
    """Euclidean distance between two entries' ``centroid.centroid_mm`` vectors."""
    cand_centroid = (cand_entry or {}).get("centroid") or {}
    gt_centroid = (gt_entry or {}).get("centroid") or {}
    cand_mm = cand_centroid.get("centroid_mm")
    gt_mm = gt_centroid.get("centroid_mm")
    if cand_mm is None or gt_mm is None:
        return None
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(cand_mm, gt_mm)))


# --------------------------------------------------------------------------- #
# compute_feature_match
# --------------------------------------------------------------------------- #


def compute_feature_match(
    candidate: Mapping[str, Any], gt: Mapping[str, Any]
) -> FeatureMatchResult:
    """Compute per-label and case-level feature-set divergence vs a GT block.

    Parameters
    ----------
    candidate, gt:
        ``features`` block dicts as produced by
        ``segfacet.pipeline.extract_feature_record`` /
        ``segfacet.feature_report.build_features_block`` -- each carrying a
        top-level ``per_label`` mapping (keyed by ``str(label)``, each entry
        carrying ``label``, ``level_name``, ``geometry``, ``centroid``, ...)
        and an optional ``stage3.per_label_offsets`` list. Never mutated.

    Returns
    -------
    FeatureMatchResult

    Raises
    ------
    segfacet.io.FacetInputError
        If either argument is not a mapping, or lacks a ``per_label``
        mapping.
    """
    candidate = _require_block(candidate, "candidate")
    gt = _require_block(gt, "gt")

    cand_pl: Mapping[str, Any] = candidate["per_label"]
    gt_pl: Mapping[str, Any] = gt["per_label"]
    cand_off = _offset_map(candidate)
    gt_off = _offset_map(gt)

    label_values = sorted({int(k) for k in cand_pl} | {int(k) for k in gt_pl})

    entries = []
    for value in label_values:
        cand_entry = cand_pl.get(str(value))
        gt_entry = gt_pl.get(str(value))
        matched = cand_entry is not None and gt_entry is not None

        if gt_entry is not None and gt_entry.get("level_name") is not None:
            name = gt_entry["level_name"]
        elif cand_entry is not None and cand_entry.get("level_name") is not None:
            name = cand_entry["level_name"]
        else:
            name = UNKNOWN

        if not matched:
            entries.append(
                LabelFeatureDivergence(
                    value=value,
                    name=name,
                    matched=False,
                    differences=(),
                    centroid_distance_mm=None,
                    divergence_score=None,
                )
            )
            continue

        differences = []
        for feature in TRACKED_FEATURES:
            cv = _scalar_value(cand_entry, cand_off, value, feature)
            gv = _scalar_value(gt_entry, gt_off, value, feature)
            available = cv is not None and gv is not None
            absolute = (cv - gv) if available else None
            relative = (
                (absolute / gv) if (available and gv != 0) else None
            )
            differences.append(
                FeatureDifference(
                    feature=feature,
                    candidate_value=cv,
                    gt_value=gv,
                    absolute=absolute,
                    relative=relative,
                    available=available,
                )
            )

        centroid_distance_mm = _centroid_distance(cand_entry, gt_entry)

        rels = [
            abs(d.relative)
            for d in differences
            if d.available and d.relative is not None
        ]
        divergence_score = (sum(rels) / len(rels)) if rels else None

        entries.append(
            LabelFeatureDivergence(
                value=value,
                name=name,
                matched=True,
                differences=tuple(differences),
                centroid_distance_mm=centroid_distance_mm,
                divergence_score=divergence_score,
            )
        )

    entries.sort(key=lambda e: _order_key(e.value, e.name))

    matched_entries = [e for e in entries if e.matched]
    n_matched = len(matched_entries)
    n_unmatched = len(entries) - n_matched

    div_scores = [
        e.divergence_score for e in matched_entries if e.divergence_score is not None
    ]
    case_divergence = (sum(div_scores) / len(div_scores)) if div_scores else None

    centroid_dists = [
        e.centroid_distance_mm
        for e in matched_entries
        if e.centroid_distance_mm is not None
    ]
    mean_centroid_distance_mm = (
        (sum(centroid_dists) / len(centroid_dists)) if centroid_dists else None
    )

    return FeatureMatchResult(
        per_label=tuple(entries),
        case_divergence=case_divergence,
        mean_centroid_distance_mm=mean_centroid_distance_mm,
        n_matched=n_matched,
        n_unmatched=n_unmatched,
    )
