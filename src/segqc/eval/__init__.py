"""Stage-7 evaluation package (§8: candidate-vs-reference comparison primitives).

Each module in this package is a pure, independent comparison primitive that
scores one aspect of a candidate result against a reference/ground-truth
counterpart; item 053's evaluation harness assembles them per case. This
package performs no cohort aggregation, correlation, or verdict-interpretation
logic of its own.

Currently exposes the level-2 **DICE-vs-GT** segmentation-overlap primitive
(item 050; see :mod:`segqc.eval.overlap`), the level-3 **feature-set
match / divergence-by-label** primitive (item 051; see
:mod:`segqc.eval.feature_match`), and the level-1 **QC-verdict comparison /
per-case outcome classification** primitive (item 052; see
:mod:`segqc.eval.outcome`).
"""

from __future__ import annotations

from .feature_match import (
    FeatureDifference,
    FeatureMatchResult,
    LabelFeatureDivergence,
    TRACKED_FEATURES,
    compute_feature_match,
)
from .outcome import CaseOutcome, Outcome, classify_outcome
from .overlap import LabelOverlap, OverlapResult, compute_overlap

__all__ = [
    "compute_overlap",
    "LabelOverlap",
    "OverlapResult",
    "compute_feature_match",
    "TRACKED_FEATURES",
    "FeatureDifference",
    "LabelFeatureDivergence",
    "FeatureMatchResult",
    "classify_outcome",
    "Outcome",
    "CaseOutcome",
]
