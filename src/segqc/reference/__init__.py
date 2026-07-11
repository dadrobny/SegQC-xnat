"""segqc.reference — reference-distribution schema & per-level aggregation
core (Stage 6, item 043).

Pure ``records -> distributions`` aggregation: no file I/O, no VerSe/NiBabel
coupling. NumPy is the only heavy dependency (used solely to compute
statistics; results are stored as builtin ``float``).
"""

from .aggregate import aggregate_reference
from .schema import (
    ALL_STRATUM,
    DEFAULT_PERCENTILES,
    SCHEMA_VERSION,
    FeatureRecord,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
    from_dict,
    to_dict,
    to_json_text,
)

__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_PERCENTILES",
    "ALL_STRATUM",
    "FeatureRecord",
    "Provenance",
    "FeatureStats",
    "LevelDistribution",
    "ReferenceDistribution",
    "aggregate_reference",
    "to_dict",
    "from_dict",
    "to_json_text",
]
