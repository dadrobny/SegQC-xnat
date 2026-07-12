"""Stage-7 evaluation package (§8: candidate-vs-reference comparison primitives).

Each module in this package is a pure, independent comparison primitive that
scores one aspect of a candidate result against a reference/ground-truth
counterpart; item 053's evaluation harness assembles them per case. This
package performs no cohort aggregation, correlation, or verdict-interpretation
logic of its own.

Currently exposes the level-2 **DICE-vs-GT** segmentation-overlap primitive
(item 050; see :mod:`segqc.eval.overlap`), the level-3 **feature-set
match / divergence-by-label** primitive (item 051; see
:mod:`segqc.eval.feature_match`), the level-1 **QC-verdict comparison /
per-case outcome classification** primitive (item 052; see
:mod:`segqc.eval.outcome`), the **evaluation cohort model & harness driver**
(item 053; see :mod:`segqc.eval.harness`) that assembles the three per case
against the real pipeline, the **cohort-level metrics aggregation** (item
054; see :mod:`segqc.eval.metrics`) that reduces a harness cohort to
FPR-on-GT, per-§6-mode sensitivity, and DICE-vs-flag / feature-divergence-vs-
flag correlations, and the **threshold-calibration loop** (item 055; see
:mod:`segqc.eval.calibrate`) that sweeps a config-parameter grid through 053
+ 054 and selects the best feasible setting against a documented objective.
"""

from __future__ import annotations

from .calibrate import (
    CalibrationObjective,
    CalibrationResult,
    CandidateResult,
    ThresholdAxis,
    apply_assignment,
    calibrate_thresholds,
    default_calibration_axes,
)
from .feature_match import (
    FeatureDifference,
    FeatureMatchResult,
    LabelFeatureDivergence,
    TRACKED_FEATURES,
    compute_feature_match,
)
from .harness import (
    CaseEvaluation,
    CohortEvaluation,
    EvaluationCase,
    evaluate_case,
    evaluate_cohort,
)
from .metrics import (
    CohortMetrics,
    ConfusionCounts,
    CorrelationResult,
    PerModeSensitivity,
    compute_cohort_metrics,
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
    "EvaluationCase",
    "CaseEvaluation",
    "CohortEvaluation",
    "evaluate_case",
    "evaluate_cohort",
    "compute_cohort_metrics",
    "ConfusionCounts",
    "PerModeSensitivity",
    "CorrelationResult",
    "CohortMetrics",
    "ThresholdAxis",
    "apply_assignment",
    "CalibrationObjective",
    "CandidateResult",
    "CalibrationResult",
    "calibrate_thresholds",
    "default_calibration_axes",
]
