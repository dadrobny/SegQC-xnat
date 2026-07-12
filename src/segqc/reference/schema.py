"""segqc.reference.schema — versioned reference-distribution data model.

Frozen dataclasses describing, per anatomical level and per optional
subject-size stratum, summary statistics for each heuristic-relevant
feature, plus caller-supplied provenance. Pure serialisation helpers
(``to_dict`` / ``from_dict`` / ``to_json_text``) round-trip the model to and
from plain JSON-ready builtins.

No NumPy import here — this module handles only builtin types. No file I/O,
no wall-clock reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

SCHEMA_VERSION = "1.1"
DEFAULT_PERCENTILES: Tuple[int, ...] = (1, 5, 25, 50, 75, 95, 99)
ALL_STRATUM = "all"


@dataclass(frozen=True)
class FeatureRecord:
    """A single per-case, per-level feature record (item 044's ingestion output)."""

    subject_id: str
    level_name: str
    features: Mapping[str, float]
    size_proxy: Optional[float] = None


@dataclass(frozen=True)
class Provenance:
    """Caller-supplied metadata; deterministic, no wall clock."""

    source: str
    config_hash: str
    build_date: str
    size_proxy_name: Optional[str] = None


@dataclass(frozen=True)
class FeatureStats:
    """Per (level, stratum, feature) summary statistics."""

    count: int
    mean: float
    std: float
    min: float
    max: float
    percentiles: Mapping[str, float]


@dataclass(frozen=True)
class LevelDistribution:
    """Per (level, stratum) aggregation result."""

    level_name: str
    stratum: str
    record_count: int
    feature_stats: Mapping[str, FeatureStats]


@dataclass(frozen=True)
class ReferenceDistribution:
    """The versioned reference-distribution artifact data model."""

    schema_version: str
    provenance: Provenance
    features: Tuple[str, ...]
    percentiles: Tuple[int, ...]
    subject_count: int
    strata: Tuple[str, ...]
    levels: Mapping[str, Mapping[str, LevelDistribution]]


def _feature_stats_to_dict(stats: FeatureStats) -> dict:
    return {
        "count": stats.count,
        "mean": stats.mean,
        "std": stats.std,
        "min": stats.min,
        "max": stats.max,
        "percentiles": dict(stats.percentiles),
    }


def _feature_stats_from_dict(data: Mapping) -> FeatureStats:
    return FeatureStats(
        count=int(data["count"]),
        mean=float(data["mean"]),
        std=float(data["std"]),
        min=float(data["min"]),
        max=float(data["max"]),
        percentiles={str(k): float(v) for k, v in data["percentiles"].items()},
    )


def _level_distribution_to_dict(dist: LevelDistribution) -> dict:
    return {
        "level_name": dist.level_name,
        "stratum": dist.stratum,
        "record_count": dist.record_count,
        "feature_stats": {
            name: _feature_stats_to_dict(stats)
            for name, stats in dist.feature_stats.items()
        },
    }


def _level_distribution_from_dict(data: Mapping) -> LevelDistribution:
    return LevelDistribution(
        level_name=str(data["level_name"]),
        stratum=str(data["stratum"]),
        record_count=int(data["record_count"]),
        feature_stats={
            name: _feature_stats_from_dict(stats)
            for name, stats in data["feature_stats"].items()
        },
    )


def to_dict(dist: ReferenceDistribution) -> dict:
    """Produce the canonical JSON-ready nested dict for ``dist`` (pure)."""

    return {
        "schema_version": dist.schema_version,
        "provenance": {
            "source": dist.provenance.source,
            "config_hash": dist.provenance.config_hash,
            "build_date": dist.provenance.build_date,
            "size_proxy_name": dist.provenance.size_proxy_name,
        },
        "features": list(dist.features),
        "percentiles": list(dist.percentiles),
        "subject_count": dist.subject_count,
        "strata": list(dist.strata),
        "levels": {
            level_name: {
                stratum: _level_distribution_to_dict(level_dist)
                for stratum, level_dist in strata.items()
            }
            for level_name, strata in dist.levels.items()
        },
    }


def from_dict(data: Mapping) -> ReferenceDistribution:
    """Rebuild a ``ReferenceDistribution`` from ``to_dict``'s output (pure).

    Tolerates any ``schema_version`` value; strict version enforcement is a
    concern for item 045's artifact loader, not this model.
    """

    prov_data = data["provenance"]
    provenance = Provenance(
        source=str(prov_data["source"]),
        config_hash=str(prov_data["config_hash"]),
        build_date=str(prov_data["build_date"]),
        size_proxy_name=(
            None
            if prov_data.get("size_proxy_name") is None
            else str(prov_data["size_proxy_name"])
        ),
    )
    levels = {
        level_name: {
            stratum: _level_distribution_from_dict(level_dist)
            for stratum, level_dist in strata.items()
        }
        for level_name, strata in data["levels"].items()
    }
    return ReferenceDistribution(
        schema_version=str(data["schema_version"]),
        provenance=provenance,
        features=tuple(data["features"]),
        percentiles=tuple(int(p) for p in data["percentiles"]),
        subject_count=int(data["subject_count"]),
        strata=tuple(data["strata"]),
        levels=levels,
    )


def to_json_text(dist: ReferenceDistribution) -> str:
    """Canonical text serialisation of ``dist`` (pure; no file I/O)."""

    return json.dumps(to_dict(dist), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
