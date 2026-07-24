"""segfacet — automated quality control for vertebra instance segmentations.

This package provides an explainable, reference-grounded heuristic QC gate for
spine-segmentation label maps. See ``docs/aide/vision.md`` for the full vision.

This module is the single source of truth for the package version; the build
backend reads ``__version__`` from here (see ``[tool.hatch.version]`` in
``pyproject.toml``).
"""

__version__ = "0.0.1"

from segfacet.verdict import Reason, Severity, Verdict  # noqa: E402
from segfacet.empty import CheckResult, check_empty  # noqa: E402
from segfacet.report import serialize_report, serialize_report_json  # noqa: E402
from segfacet.human_report import render_feature_table, render_human_report  # noqa: E402
from segfacet.feature_report import build_features_block  # noqa: E402
from segfacet.features.fragmentation import compute_fragmentation_index  # noqa: E402

__all__ = [
    "__version__",
    "Severity",
    "Reason",
    "Verdict",
    "CheckResult",
    "check_empty",
    "serialize_report",
    "serialize_report_json",
    "render_human_report",
    "render_feature_table",
    "build_features_block",
    "compute_fragmentation_index",
]
