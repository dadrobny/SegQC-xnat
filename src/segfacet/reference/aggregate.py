"""segfacet.reference.aggregate — pure per-level/per-stratum aggregation.

``aggregate_reference`` consumes a collection of per-case, per-level
``FeatureRecord``s and produces a ``ReferenceDistribution``: summary
statistics per anatomical level and optional subject-size stratum.

Pure: no file I/O, no wall-clock reads, and the caller's inputs (record
sequence, each record's ``features`` mapping) are never mutated.
"""

from __future__ import annotations

import bisect
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .schema import (
    ALL_STRATUM,
    DEFAULT_PERCENTILES,
    SCHEMA_VERSION,
    FeatureRecord,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
)


def _resolve_features(
    records: List[FeatureRecord], features: Optional[Sequence[str]]
) -> Tuple[str, ...]:
    if features is not None:
        return tuple(sorted(features))
    seen = set()
    for record in records:
        seen.update(record.features.keys())
    return tuple(sorted(seen))


def _resolve_strata(
    records: List[FeatureRecord],
    size_strata_edges: Optional[Sequence[float]],
    stratum_labels: Optional[Sequence[str]],
) -> Tuple[List[str], Dict[int, str]]:
    """Return (ordered bucket labels, {record index -> stratum label})."""

    if size_strata_edges is None:
        labels = [ALL_STRATUM]
        assignment = {i: ALL_STRATUM for i in range(len(records))}
        return labels, assignment

    sorted_edges = sorted(size_strata_edges)
    n_buckets = len(sorted_edges) + 1
    if stratum_labels is None:
        labels = [f"s{i}" for i in range(n_buckets)]
    else:
        labels = list(stratum_labels)
        if len(labels) != n_buckets:
            raise ValueError(
                f"stratum_labels must have length {n_buckets} "
                f"(len(size_strata_edges) + 1), got {len(labels)}"
            )

    assignment: Dict[int, str] = {}
    for i, record in enumerate(records):
        if record.size_proxy is None:
            raise ValueError(
                f"record for subject {record.subject_id!r} has size_proxy=None "
                "but size_strata_edges was supplied; stratification requires "
                "every record to carry a non-None size_proxy"
            )
        bucket_idx = bisect.bisect_right(sorted_edges, record.size_proxy)
        assignment[i] = labels[bucket_idx]

    return labels, assignment


def aggregate_reference(
    records: Iterable[FeatureRecord],
    *,
    provenance: Provenance,
    features: Optional[Sequence[str]] = None,
    percentiles: Sequence[int] = DEFAULT_PERCENTILES,
    size_strata_edges: Optional[Sequence[float]] = None,
    stratum_labels: Optional[Sequence[str]] = None,
) -> ReferenceDistribution:
    """Aggregate ``records`` into a ``ReferenceDistribution``.

    Pure: groups records by ``(level_name, size-stratum)``, computes
    per-feature summary statistics, and returns the resulting model. No
    file I/O, no wall-clock reads; neither the passed record sequence nor
    any record's ``features`` mapping is mutated.
    """

    record_list = list(records)  # never mutate the caller's sequence

    tracked_features = _resolve_features(record_list, features)
    bucket_order, stratum_by_index = _resolve_strata(
        record_list, size_strata_edges, stratum_labels
    )

    # Group contributing values by (level_name, stratum, feature_name).
    values_by_key: Dict[Tuple[str, str], Dict[str, List[float]]] = {}
    record_counts: Dict[Tuple[str, str], int] = {}

    for i, record in enumerate(record_list):
        stratum = stratum_by_index[i]
        key = (record.level_name, stratum)
        record_counts[key] = record_counts.get(key, 0) + 1
        feature_values = values_by_key.setdefault(key, {})
        for feature_name in tracked_features:
            if feature_name in record.features:
                feature_values.setdefault(feature_name, []).append(
                    float(record.features[feature_name])
                )

    levels: Dict[str, Dict[str, LevelDistribution]] = {}
    present_strata_order = [
        label for label in bucket_order if any(s == label for (_, s) in record_counts)
    ]

    for (level_name, stratum), count in record_counts.items():
        feature_stats: Dict[str, FeatureStats] = {}
        for feature_name, values in values_by_key[(level_name, stratum)].items():
            if not values:
                continue
            arr = np.asarray(values, dtype=float)
            std = 0.0 if len(values) == 1 else float(np.std(arr, ddof=1))
            feature_stats[feature_name] = FeatureStats(
                count=len(values),
                mean=float(np.mean(arr)),
                std=std,
                min=float(np.min(arr)),
                max=float(np.max(arr)),
                percentiles={
                    f"p{n}": float(np.percentile(arr, n)) for n in percentiles
                },
            )
        level_dist = LevelDistribution(
            level_name=level_name,
            stratum=stratum,
            record_count=count,
            feature_stats=feature_stats,
        )
        levels.setdefault(level_name, {})[stratum] = level_dist

    subject_count = len({record.subject_id for record in record_list})

    return ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=provenance,
        features=tracked_features,
        percentiles=tuple(percentiles),
        subject_count=subject_count,
        strata=tuple(present_strata_order),
        levels=levels,
    )
