"""segqc.reference — reference-distribution schema & per-level aggregation
core (Stage 6, item 043).

Pure ``records -> distributions`` aggregation: no file I/O, no VerSe/NiBabel
coupling. NumPy is the only heavy dependency (used solely to compute
statistics; results are stored as builtin ``float``).
"""

from .aggregate import aggregate_reference
from .ingest import (
    DEFAULT_SCAN_SUFFIX,
    DEFAULT_SEG_SUFFIX,
    INGESTED_FEATURES,
    SIZE_PROXY_NAME,
    CohortIngest,
    SubjectIngest,
    ingest_cohort,
    ingest_subject,
)
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
    "DEFAULT_SEG_SUFFIX",
    "DEFAULT_SCAN_SUFFIX",
    "SIZE_PROXY_NAME",
    "INGESTED_FEATURES",
    "SubjectIngest",
    "CohortIngest",
    "ingest_subject",
    "ingest_cohort",
]
