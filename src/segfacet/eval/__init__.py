"""Stage-7 evaluation package (§8: candidate-vs-reference comparison primitives).

Each module in this package is a pure, independent comparison primitive that
scores one aspect of a candidate result against a reference/ground-truth
counterpart; item 053's evaluation harness assembles them per case. This
package performs no cohort aggregation, correlation, or verdict-interpretation
logic of its own.

Currently exposes the level-2 **DICE-vs-GT** segmentation-overlap primitive
(item 050; see :mod:`segfacet.eval.overlap`), the level-3 **feature-set
match / divergence-by-label** primitive (item 051; see
:mod:`segfacet.eval.feature_match`), the level-1 **QC-verdict comparison /
per-case outcome classification** primitive (item 052; see
:mod:`segfacet.eval.outcome`), the **evaluation cohort model & harness driver**
(item 053; see :mod:`segfacet.eval.harness`) that assembles the three per case
against the real pipeline, the **cohort-level metrics aggregation** (item
054; see :mod:`segfacet.eval.metrics`) that reduces a harness cohort to
FPR-on-GT, per-§6-mode sensitivity, and DICE-vs-flag / feature-divergence-vs-
flag correlations, the **threshold-calibration loop** (item 055; see
:mod:`segfacet.eval.calibrate`) that sweeps a config-parameter grid through 053
+ 054 and selects the best feasible setting against a documented objective,
and the **evaluation report (JSON + human) and calibrated-config recorder**
(item 056; see :mod:`segfacet.eval.report`) that renders 054's metrics + 055's
chosen calibration into a versioned, schema-validated JSON report, a
stdlib-only plain-text rendering, and a byte-reproducible calibrated
``HeuristicConfig`` YAML writer, and the **per-mode failure-magnitude metric
surface** (item 099; see :mod:`segfacet.eval.per_mode`) that maps each of the
eight §6 failure modes to one named scalar metric measuring *how much* of the
mode is present in a single case, complementing item 054's per-mode
*sensitivity* (a cohort-wide *detection-rate*, not a per-case magnitude), and
the **severity-ladder monotonicity & cross-mode specificity harness** (item
100; see :mod:`segfacet.eval.severity_ladder`) that runs item 099's eight
metrics over a *graded* synthetic-severity stimulus per mode, proving each
metric moves monotonically with its own mode's severity and is comparatively
insensitive to the others -- the graded-stimulus counterpart to item 099's
per-case isolation surface, and the **cohort-level per-mode report with
run-vs-run comparison** (item 101; see :mod:`segfacet.eval.per_mode_cohort`)
that aggregates item 099's per-case magnitudes over a cohort and diffs two
runs' summaries into a normalised, direction-aware, schema-validated
comparison artifact -- reachable via ``segfacet evaluate --per-mode`` and the
new ``segfacet compare-runs`` subcommand.
"""

from __future__ import annotations

from .cohort import (
    EVAL_COHORT_MANIFEST_VERSION,
    load_cohort_manifest,
)
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
from .per_mode import (
    MetricSpec,
    PerModeMetric,
    PerModeMetrics,
    PER_MODE_METRIC_SPECS,
    compute_per_mode_metrics,
)
from .per_mode_cohort import (
    ModeAggregate,
    ModeDelta,
    RunComparison,
    RunPerModeSummary,
    compare_runs,
    summarise_run_per_mode,
)
from .report import (
    EVAL_REPORT_SCHEMA_VERSION,
    PER_MODE_COMPARISON_SCHEMA_VERSION,
    EvaluationProvenance,
    build_evaluation_report,
    build_run_comparison_report,
    record_calibrated_config,
    render_evaluation_report,
    render_run_comparison,
    serialize_evaluation_report_json,
    write_evaluation_report,
)
from .severity_ladder import (
    COUPLING_THRESHOLD,
    DEGENERATE_LADDER_MODES,
    KNOWN_CROSS_MODE_COUPLINGS,
    LADDER_SEED,
    RECORDED_MARGINS,
    SEVERITY_LADDERS,
    SUPPLEMENTARY_LADDERS,
    CrossModeCoupling,
    HarnessResult,
    HarnessVerdict,
    LadderPoint,
    LadderResult,
    LadderRungSpec,
    LadderSpec,
    LadderVerdict,
    evaluate_ladder,
    run_severity_harness,
    score_harness,
)

__all__ = [
    "EVAL_COHORT_MANIFEST_VERSION",
    "load_cohort_manifest",
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
    "MetricSpec",
    "PerModeMetric",
    "PerModeMetrics",
    "PER_MODE_METRIC_SPECS",
    "compute_per_mode_metrics",
    "ModeAggregate",
    "RunPerModeSummary",
    "ModeDelta",
    "RunComparison",
    "summarise_run_per_mode",
    "compare_runs",
    "PER_MODE_COMPARISON_SCHEMA_VERSION",
    "build_run_comparison_report",
    "render_run_comparison",
    "ThresholdAxis",
    "apply_assignment",
    "CalibrationObjective",
    "CandidateResult",
    "CalibrationResult",
    "calibrate_thresholds",
    "default_calibration_axes",
    "EVAL_REPORT_SCHEMA_VERSION",
    "EvaluationProvenance",
    "build_evaluation_report",
    "serialize_evaluation_report_json",
    "write_evaluation_report",
    "render_evaluation_report",
    "record_calibrated_config",
    "LadderRungSpec",
    "LadderSpec",
    "LadderPoint",
    "LadderResult",
    "HarnessResult",
    "LadderVerdict",
    "HarnessVerdict",
    "CrossModeCoupling",
    "SEVERITY_LADDERS",
    "SUPPLEMENTARY_LADDERS",
    "DEGENERATE_LADDER_MODES",
    "KNOWN_CROSS_MODE_COUPLINGS",
    "RECORDED_MARGINS",
    "COUPLING_THRESHOLD",
    "LADDER_SEED",
    "evaluate_ladder",
    "run_severity_harness",
    "score_harness",
]
