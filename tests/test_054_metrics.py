"""Tests for cohort-level metrics aggregation: FPR-on-GT, per-failure-mode
sensitivity, and DICE-vs-flag / feature-divergence-vs-flag correlation (item
054 -- Stage-7 aggregation over item 053's per-case evaluation records).

Covers all eighteen Acceptance Criteria plus adversarial and edge-case inputs.
Every input is a **hand-built** ``CohortEvaluation`` assembled entirely in
memory from item 052/050/051's frozen dataclasses via two small factories
(``_outcome``/``_case``/``_cohort``) -- no pipeline, no rule evaluation, no
label-map or file I/O, and no ``HeuristicConfig`` stub, per the item's Testing
Strategy. Every expected count/rate/coefficient is hand-computed (Pearson and
Spearman via small pure-Python helpers, independent of the production
module's ``numpy``-based implementation).

``segqc.eval.metrics`` does not exist yet at the time this file is written;
its names are imported **locally inside each test function** (mirroring
``tests/test_053_eval_harness.py``'s treatment of the then-new harness names)
so the file can still be collected before the module is implemented.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math

import pytest

from segqc.eval.feature_match import FeatureMatchResult
from segqc.eval.harness import CaseEvaluation, CohortEvaluation
from segqc.eval.outcome import CaseOutcome, Outcome
from segqc.eval.overlap import OverlapResult
from segqc.io import SegQCInputError


# =========================================================================== #
# Fixture factories
# =========================================================================== #


def _outcome(**kwargs) -> CaseOutcome:
    """Build a CaseOutcome with every field defaulted (a clean TN), overridable
    by keyword. ``outcome``/``caught`` are derived from ``expected_failure``/
    ``actual_flagged`` unless explicitly overridden, keeping every hand-built
    case internally consistent with item 052's semantics."""
    expected_failure = kwargs.get("expected_failure", False)
    actual_flagged = kwargs.get("actual_flagged", False)
    fields = dict(
        outcome=Outcome.from_flags(expected_failure, actual_flagged),
        expected_verdict="fail" if expected_failure else "pass",
        actual_verdict="fail" if actual_flagged else "pass",
        expected_failure=expected_failure,
        actual_flagged=actual_flagged,
        caught=(actual_flagged if expected_failure else None),
        failure_mode=None,
        failure_mode_name=None,
        expected_rule_ids=(),
        expected_labels=(),
        fired_rule_ids=(),
        designated_rule_fired=False,
        caught_by_designated_rule=False,
    )
    fields.update(kwargs)
    return CaseOutcome(**fields)


def _case(outcome_kwargs, dice=None, divergence=None, case_id="c") -> CaseEvaluation:
    """Build one CaseEvaluation: a CaseOutcome from ``outcome_kwargs``, an
    optional OverlapResult (``dice`` a float for both aggregates, or a
    ``(mean_dice, volume_weighted_dice)`` pair when they must differ), and an
    optional FeatureMatchResult (``case_divergence=divergence``). ``dice``/
    ``divergence`` both ``None`` means no candidate was present."""
    outcome = _outcome(**outcome_kwargs)

    overlap = None
    if dice is not None:
        mean_dice, vw_dice = dice if isinstance(dice, tuple) else (dice, dice)
        overlap = OverlapResult(
            per_label=(),
            mean_dice=mean_dice,
            volume_weighted_dice=vw_dice,
            mean_jaccard=None,
            n_matched=1,
            n_unmatched=0,
        )

    feature_match = None
    if divergence is not None:
        feature_match = FeatureMatchResult(
            per_label=(),
            case_divergence=divergence,
            mean_centroid_distance_mm=None,
            n_matched=1,
            n_unmatched=0,
        )

    candidate_present = dice is not None or divergence is not None
    return CaseEvaluation(
        case_id=case_id,
        outcome=outcome,
        overlap=overlap,
        feature_match=feature_match,
        candidate_present=candidate_present,
        subject="candidate" if candidate_present else "gt",
        metadata=None,
    )


def _cohort(cases) -> CohortEvaluation:
    return CohortEvaluation(cases=tuple(cases))


# =========================================================================== #
# Independent (pure-Python, non-numpy) Pearson/Spearman helpers, used only to
# hand-compute expected coefficients for AC8/AC9/AC11/AC12.
# =========================================================================== #


def _pearson(xs, ys):
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    return cov / math.sqrt(var_x * var_y)


def _avg_ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman(xs, ys):
    return _pearson(_avg_ranks(xs), _avg_ranks(ys))


def _assert_plain_json_types(obj):
    """Recursively assert obj contains only dict/list/str/int/float/bool/None."""
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_plain_json_types(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_plain_json_types(v)
    else:
        assert obj is None or isinstance(obj, (str, int, float, bool))


# =========================================================================== #
# AC1: module & public API exist
# =========================================================================== #


def test_ac1_imports_from_metrics_module_and_reexport():
    """AC1: all five names import from segqc.eval.metrics and are re-exported
    from segqc.eval."""
    from segqc.eval.metrics import (  # noqa: F401
        CohortMetrics,
        ConfusionCounts,
        CorrelationResult,
        PerModeSensitivity,
        compute_cohort_metrics,
    )
    from segqc.eval import compute_cohort_metrics as reexported

    assert reexported is compute_cohort_metrics


def test_ac1_module_dunder_all():
    """AC1: segqc.eval.metrics.__all__ lists all five public names."""
    import segqc.eval.metrics as metrics_mod

    assert set(metrics_mod.__all__) == {
        "compute_cohort_metrics",
        "ConfusionCounts",
        "PerModeSensitivity",
        "CorrelationResult",
        "CohortMetrics",
    }


def test_ac1_dataclasses_are_frozen_with_documented_fields():
    """AC1: each result dataclass is frozen and carries the documented fields."""
    from segqc.eval.metrics import (
        CohortMetrics,
        ConfusionCounts,
        CorrelationResult,
        PerModeSensitivity,
    )

    expectations = {
        ConfusionCounts: {"tp", "fp", "tn", "fn"},
        PerModeSensitivity: {
            "failure_mode",
            "failure_mode_name",
            "n_cases",
            "n_caught",
            "n_caught_by_designated_rule",
            "sensitivity",
            "caught_rate",
        },
        CorrelationResult: {"coefficient", "n", "method", "x_variable", "y_variable"},
        CohortMetrics: {
            "counts",
            "false_positive_rate",
            "sensitivity",
            "specificity",
            "per_mode",
            "dice_vs_flag",
            "feature_divergence_vs_flag",
            "n_cases",
        },
    }
    for cls, fields in expectations.items():
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True
        assert {f.name for f in dataclasses.fields(cls)} >= fields


# =========================================================================== #
# AC2: confusion counts
# =========================================================================== #


def test_ac2_confusion_counts_aggregated_correctly():
    """AC2: counts.tp/fp/tn/fn match a known TP/FP/TN/FN mix; n_cases matches."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = (
        [
            _case(
                {"expected_failure": True, "actual_flagged": True}, case_id=f"tp{i}"
            )
            for i in range(2)
        ]
        + [_case({"expected_failure": False, "actual_flagged": True}, case_id="fp0")]
        + [
            _case(
                {"expected_failure": False, "actual_flagged": False}, case_id=f"tn{i}"
            )
            for i in range(3)
        ]
        + [_case({"expected_failure": True, "actual_flagged": False}, case_id="fn0")]
    )
    result = compute_cohort_metrics(_cohort(cases))

    assert result.counts.tp == 2
    assert result.counts.fp == 1
    assert result.counts.tn == 3
    assert result.counts.fn == 1
    assert result.n_cases == 7


# =========================================================================== #
# AC3/AC4: FPR on GT
# =========================================================================== #


def test_ac3_fpr_is_fp_over_fp_plus_tn():
    """AC3: 4 TN + 1 FP among the expected-pass set -> FPR == 0.2, unaffected
    by the expected-failure records also present."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = (
        [
            _case(
                {"expected_failure": False, "actual_flagged": False}, case_id=f"tn{i}"
            )
            for i in range(4)
        ]
        + [_case({"expected_failure": False, "actual_flagged": True}, case_id="fp0")]
        + [_case({"expected_failure": True, "actual_flagged": True}, case_id="tp0")]
        + [_case({"expected_failure": True, "actual_flagged": False}, case_id="fn0")]
    )
    result = compute_cohort_metrics(_cohort(cases))

    assert result.false_positive_rate == pytest.approx(0.2)


def test_ac4_fpr_sentinel_when_no_expected_pass_cases():
    """AC4: a cohort of only expected-failure records -> false_positive_rate is
    None (no divide-by-zero)."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case({"expected_failure": True, "actual_flagged": True}, case_id="tp0"),
        _case({"expected_failure": True, "actual_flagged": False}, case_id="fn0"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.false_positive_rate is None


# =========================================================================== #
# AC5/AC6/AC7: per-mode sensitivity
# =========================================================================== #


def test_ac5_per_mode_sensitivity_designated_vs_caught_rate():
    """AC5: n=4 expected-failure cases of mode 4, j=3 caught by the designated
    rule, c=4 caught at all -> sensitivity == 0.75, caught_rate == 1.0."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 4,
                "caught": True,
                "caught_by_designated_rule": True,
            },
            case_id=f"designated{i}",
        )
        for i in range(3)
    ] + [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 4,
                "caught": True,
                "caught_by_designated_rule": False,
            },
            case_id="incidental",
        )
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert len(result.per_mode) == 1
    pm = result.per_mode[0]
    assert pm.failure_mode == 4
    assert pm.n_cases == 4
    assert pm.n_caught_by_designated_rule == 3
    assert pm.n_caught == 4
    assert pm.sensitivity == pytest.approx(0.75)
    assert pm.caught_rate == pytest.approx(1.0)


def test_ac6_per_mode_sentinel_for_requested_mode_with_no_cases():
    """AC6: failure_modes=[7] with no mode-7 record -> n_cases == 0 and both
    rates are None, no divide-by-zero."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 4,
                "caught": True,
                "caught_by_designated_rule": True,
            },
            case_id="a",
        )
    ]
    result = compute_cohort_metrics(_cohort(cases), failure_modes=[7])

    assert len(result.per_mode) == 1
    pm = result.per_mode[0]
    assert pm.failure_mode == 7
    assert pm.n_cases == 0
    assert pm.n_caught == 0
    assert pm.n_caught_by_designated_rule == 0
    assert pm.sensitivity is None
    assert pm.caught_rate is None


def test_ac7_per_mode_grouping_over_observed_modes_when_omitted():
    """AC7: with failure_modes=None, one entry per distinct observed mode,
    ordered ascending with a trailing None entry; expected-pass records
    contribute to no entry."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 2,
                "failure_mode_name": "mode-two",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            case_id="m2a",
        ),
        _case(
            {
                "expected_failure": True,
                "actual_flagged": False,
                "failure_mode": 2,
                "failure_mode_name": "mode-two",
                "caught": False,
                "caught_by_designated_rule": False,
            },
            case_id="m2b",
        ),
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 1,
                "failure_mode_name": "mode-one",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            case_id="m1a",
        ),
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": None,
                "caught": True,
                "caught_by_designated_rule": True,
            },
            case_id="mNone",
        ),
        _case({"expected_failure": False, "actual_flagged": False}, case_id="pass0"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    modes = [pm.failure_mode for pm in result.per_mode]
    assert modes == [1, 2, None]

    by_mode = {pm.failure_mode: pm for pm in result.per_mode}
    assert by_mode[1].n_cases == 1
    assert by_mode[2].n_cases == 2
    assert by_mode[None].n_cases == 1
    assert by_mode[2].failure_mode_name == "mode-two"


# =========================================================================== #
# AC8/AC9/AC10: DICE-vs-flag correlation
# =========================================================================== #


def test_ac8_dice_vs_flag_correlation_matches_hand_computed_pearson():
    """AC8: lower DICE co-occurs with flagged, higher with not-flagged -> a
    negative coefficient matching the independently hand-computed Pearson
    value to abs tol 1e-9."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.2, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.3, case_id="b"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.9, case_id="c"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.95, case_id="d"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    expected = _pearson([0.2, 0.3, 0.9, 0.95], [1.0, 1.0, 0.0, 0.0])
    assert result.dice_vs_flag.coefficient < 0
    assert result.dice_vs_flag.coefficient == pytest.approx(expected, abs=1e-9)
    assert result.dice_vs_flag.n == 4
    assert result.dice_vs_flag.method == "pearson"
    assert result.dice_vs_flag.x_variable == "mean_dice"
    assert result.dice_vs_flag.y_variable == "flagged"


def test_ac9_correlation_excludes_cases_without_usable_dice():
    """AC9: cases with overlap is None (no candidate) or a None selected DICE
    value are skipped, not errors -- n and coefficient are unchanged."""
    from segqc.eval.metrics import compute_cohort_metrics

    base_cases = [
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.2, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.3, case_id="b"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.9, case_id="c"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.95, case_id="d"),
    ]
    no_candidate = _case(
        {"expected_failure": True, "actual_flagged": True}, dice=None, case_id="e"
    )
    null_dice_value = dataclasses.replace(
        _case({"expected_failure": True, "actual_flagged": False}, dice=0.5, case_id="f"),
        overlap=OverlapResult(
            per_label=(),
            mean_dice=None,
            volume_weighted_dice=None,
            mean_jaccard=None,
            n_matched=0,
            n_unmatched=0,
        ),
    )
    result = compute_cohort_metrics(_cohort(base_cases + [no_candidate, null_dice_value]))

    expected = _pearson([0.2, 0.3, 0.9, 0.95], [1.0, 1.0, 0.0, 0.0])
    assert result.dice_vs_flag.n == 4
    assert result.dice_vs_flag.coefficient == pytest.approx(expected, abs=1e-9)


def test_ac10_correlation_sentinel_fewer_than_two_pairs():
    """AC10(a): a single usable pair -> coefficient is None, n is still 1."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [_case({"expected_failure": False, "actual_flagged": True}, dice=0.4, case_id="a")]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.dice_vs_flag.coefficient is None
    assert result.dice_vs_flag.n == 1


def test_ac10_correlation_sentinel_zero_variance_dice():
    """AC10(b): all DICE values equal -> coefficient is None (zero x-variance)."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.5, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.5, case_id="b"),
        _case({"expected_failure": True, "actual_flagged": True}, dice=0.5, case_id="c"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.dice_vs_flag.coefficient is None
    assert result.dice_vs_flag.n == 3


def test_ac10_correlation_sentinel_zero_variance_flag():
    """AC10(c): every case flagged -> coefficient is None (zero y-variance)."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.2, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.5, case_id="b"),
        _case({"expected_failure": True, "actual_flagged": True}, dice=0.9, case_id="c"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.dice_vs_flag.coefficient is None
    assert result.dice_vs_flag.n == 3


# =========================================================================== #
# AC11: feature-divergence-vs-flag correlation
# =========================================================================== #


def test_ac11_feature_divergence_vs_flag_positive_and_excludes_missing():
    """AC11: higher case_divergence co-occurs with flagged -> a positive
    coefficient matching the hand-computed value; a feature_match is None
    case is excluded from n."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case({"expected_failure": False, "actual_flagged": False}, divergence=0.1, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": False}, divergence=0.2, case_id="b"),
        _case({"expected_failure": True, "actual_flagged": True}, divergence=0.8, case_id="c"),
        _case({"expected_failure": True, "actual_flagged": True}, divergence=0.9, case_id="d"),
        _case({"expected_failure": True, "actual_flagged": True}, divergence=None, case_id="e"),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    expected = _pearson([0.1, 0.2, 0.8, 0.9], [0.0, 0.0, 1.0, 1.0])
    assert result.feature_divergence_vs_flag.coefficient > 0
    assert result.feature_divergence_vs_flag.coefficient == pytest.approx(
        expected, abs=1e-9
    )
    assert result.feature_divergence_vs_flag.n == 4
    assert result.feature_divergence_vs_flag.x_variable == "case_divergence"
    assert result.feature_divergence_vs_flag.y_variable == "flagged"


# =========================================================================== #
# AC12: Spearman option
# =========================================================================== #


def test_ac12_spearman_rank_correlation_exceeds_pearson_for_uneven_spacing():
    """AC12: for a strictly monotone but unevenly-spaced DICE/flag
    arrangement, the Spearman coefficient (rank-based, magnitude fixed by the
    2-vs-2 split regardless of spacing) has a larger magnitude than the
    Pearson coefficient (which is sensitive to the uneven spacing); pearson
    remains the default method."""
    from segqc.eval.metrics import compute_cohort_metrics

    xs = [0.1, 0.4, 0.6, 0.9]
    ys = [1.0, 1.0, 0.0, 0.0]
    cases = [
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.1, case_id="a"),
        _case({"expected_failure": False, "actual_flagged": True}, dice=0.4, case_id="b"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.6, case_id="c"),
        _case({"expected_failure": False, "actual_flagged": False}, dice=0.9, case_id="d"),
    ]
    cohort = _cohort(cases)

    default_result = compute_cohort_metrics(cohort)
    pearson_result = compute_cohort_metrics(cohort, correlation_method="pearson")
    spearman_result = compute_cohort_metrics(cohort, correlation_method="spearman")

    expected_pearson = _pearson(xs, ys)
    expected_spearman = _spearman(xs, ys)

    assert default_result.dice_vs_flag.method == "pearson"
    assert default_result.dice_vs_flag.coefficient == pytest.approx(
        expected_pearson, abs=1e-9
    )
    assert pearson_result.dice_vs_flag.coefficient == pytest.approx(
        expected_pearson, abs=1e-9
    )
    assert spearman_result.dice_vs_flag.method == "spearman"
    assert spearman_result.dice_vs_flag.coefficient == pytest.approx(
        expected_spearman, abs=1e-9
    )
    assert 0 < abs(pearson_result.dice_vs_flag.coefficient) < 1
    assert abs(spearman_result.dice_vs_flag.coefficient) > abs(
        pearson_result.dice_vs_flag.coefficient
    )


# =========================================================================== #
# AC13: dice_metric selection
# =========================================================================== #


def test_ac13_dice_metric_selects_volume_weighted_aggregate():
    """AC13: with dice_metric='volume_weighted_dice', the correlation reads
    volume_weighted_dice (not mean_dice) -- proven by mean_dice being
    constant (zero variance -> None) while volume_weighted_dice varies and
    anti-correlates with flag."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=(0.5, 0.9),
            case_id="a",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=(0.5, 0.8),
            case_id="b",
        ),
        _case(
            {"expected_failure": True, "actual_flagged": True},
            dice=(0.5, 0.2),
            case_id="c",
        ),
        _case(
            {"expected_failure": True, "actual_flagged": True},
            dice=(0.5, 0.1),
            case_id="d",
        ),
    ]
    cohort = _cohort(cases)

    mean_result = compute_cohort_metrics(cohort)
    assert mean_result.dice_vs_flag.coefficient is None  # constant mean_dice

    vw_result = compute_cohort_metrics(cohort, dice_metric="volume_weighted_dice")
    assert vw_result.dice_vs_flag.coefficient is not None
    assert vw_result.dice_vs_flag.coefficient < 0
    assert vw_result.dice_vs_flag.x_variable == "volume_weighted_dice"


# =========================================================================== #
# AC14: overall derived rates
# =========================================================================== #


def test_ac14_overall_sensitivity_and_specificity():
    """AC14: sensitivity == TP/(TP+FN), specificity == TN/(TN+FP), and
    specificity == 1 - fpr when both are defined."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = (
        [
            _case({"expected_failure": True, "actual_flagged": True}, case_id=f"tp{i}")
            for i in range(3)
        ]
        + [_case({"expected_failure": True, "actual_flagged": False}, case_id="fn0")]
        + [
            _case({"expected_failure": False, "actual_flagged": False}, case_id=f"tn{i}")
            for i in range(2)
        ]
        + [
            _case({"expected_failure": False, "actual_flagged": True}, case_id=f"fp{i}")
            for i in range(2)
        ]
    )
    result = compute_cohort_metrics(_cohort(cases))

    assert result.sensitivity == pytest.approx(0.75)
    assert result.specificity == pytest.approx(0.5)
    assert result.specificity == pytest.approx(1 - result.false_positive_rate)


def test_ac14_sensitivity_none_when_no_failure_cases():
    """AC14: a cohort with no expected-failure cases -> sensitivity is None."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [_case({"expected_failure": False, "actual_flagged": False}, case_id="a")]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.sensitivity is None


# =========================================================================== #
# AC15: empty cohort
# =========================================================================== #


def test_ac15_empty_cohort_yields_all_sentinel_metrics():
    """AC15: an empty CohortEvaluation -> all-zero counts, all-None rates,
    empty per_mode, and both correlations sentinel with n == 0, no crash."""
    from segqc.eval.metrics import compute_cohort_metrics

    result = compute_cohort_metrics(_cohort([]))

    assert result.n_cases == 0
    assert result.counts.tp == 0
    assert result.counts.fp == 0
    assert result.counts.tn == 0
    assert result.counts.fn == 0
    assert result.false_positive_rate is None
    assert result.sensitivity is None
    assert result.specificity is None
    assert result.per_mode == ()
    assert result.dice_vs_flag.coefficient is None
    assert result.dice_vs_flag.n == 0
    assert result.feature_divergence_vs_flag.coefficient is None
    assert result.feature_divergence_vs_flag.n == 0


def test_ac15_empty_cohort_with_requested_modes_yields_sentinel_entries():
    """AC15 (per-mode variant): an empty cohort with failure_modes supplied
    still returns one all-sentinel entry per requested mode."""
    from segqc.eval.metrics import compute_cohort_metrics

    result = compute_cohort_metrics(_cohort([]), failure_modes=[1, 2])

    assert [pm.failure_mode for pm in result.per_mode] == [1, 2]
    for pm in result.per_mode:
        assert pm.n_cases == 0
        assert pm.sensitivity is None
        assert pm.caught_rate is None


# =========================================================================== #
# AC16: to_dict() serialisation & determinism
# =========================================================================== #


def test_ac16_to_dict_is_plain_json_and_round_trips():
    """AC16: to_dict() contains only plain JSON types and round-trips through
    json.dumps/json.loads unchanged."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 2,
                "failure_mode_name": "mode-two",
                "caught": True,
                "caught_by_designated_rule": True,
            },
            dice=0.2,
            divergence=0.8,
            case_id="p",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.9,
            divergence=0.1,
            case_id="q",
        ),
    ]
    result = compute_cohort_metrics(_cohort(cases))
    d = result.to_dict()

    _assert_plain_json_types(d)
    assert json.loads(json.dumps(d)) == d


def test_ac16_repeated_calls_are_equal_and_byte_identical():
    """AC16: two compute_cohort_metrics calls on the same cohort produce equal
    CohortMetrics and byte-identical sort_keys=True JSON."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 2,
                "caught": True,
                "caught_by_designated_rule": True,
            },
            dice=0.2,
            divergence=0.8,
            case_id="p",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.9,
            divergence=0.1,
            case_id="q",
        ),
    ]
    cohort = _cohort(cases)

    result_a = compute_cohort_metrics(cohort)
    result_b = compute_cohort_metrics(cohort)

    assert result_a == result_b
    assert json.dumps(result_a.to_dict(), sort_keys=True) == json.dumps(
        result_b.to_dict(), sort_keys=True
    )


# =========================================================================== #
# AC17: malformed arguments
# =========================================================================== #


def test_ac17_unrecognised_correlation_method_raises():
    """AC17: an unrecognised correlation_method raises SegQCInputError, not a
    raw KeyError/ValueError."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [_case({"expected_failure": False, "actual_flagged": False}, case_id="a")]
    with pytest.raises(SegQCInputError):
        compute_cohort_metrics(_cohort(cases), correlation_method="kendall")


def test_ac17_unrecognised_dice_metric_raises():
    """AC17: an unrecognised dice_metric raises SegQCInputError, not a raw
    KeyError/AttributeError."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [_case({"expected_failure": False, "actual_flagged": False}, case_id="a")]
    with pytest.raises(SegQCInputError):
        compute_cohort_metrics(_cohort(cases), dice_metric="jaccard")


# =========================================================================== #
# AC18: pure, deterministic, non-mutating
# =========================================================================== #


def test_ac18_pure_non_mutating_deterministic():
    """AC18: the input cohort and its records are unchanged after the call;
    repeated calls return equal results (no file I/O is exercised anywhere in
    this test file, matching the module's documented purity)."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {"expected_failure": True, "actual_flagged": True, "failure_mode": 1},
            dice=0.3,
            divergence=0.7,
            case_id="x",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.95,
            divergence=0.05,
            case_id="y",
        ),
    ]
    cohort = _cohort(cases)
    snapshot = copy.deepcopy(cohort)

    result_a = compute_cohort_metrics(cohort)
    result_b = compute_cohort_metrics(cohort)

    assert cohort == snapshot
    assert cohort.cases == snapshot.cases
    assert result_a == result_b


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_incidental_rule_catch_is_not_designated_sensitivity():
    """A mode where every case was caught by an incidental rule (caught is
    True but caught_by_designated_rule is False) -> caught_rate == 1.0 while
    sensitivity == 0.0, making the designated-rule strictness visible."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 5,
                "caught": True,
                "caught_by_designated_rule": False,
            },
            case_id=f"m5-{i}",
        )
        for i in range(3)
    ]
    result = compute_cohort_metrics(_cohort(cases), failure_modes=[5])

    pm = result.per_mode[0]
    assert pm.caught_rate == pytest.approx(1.0)
    assert pm.sensitivity == pytest.approx(0.0)


def test_adversarial_none_failure_mode_groups_and_counts_toward_recall():
    """An expected-failure record with failure_mode is None groups into the
    trailing None per-mode entry and still contributes to overall recall."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {"expected_failure": True, "actual_flagged": True, "failure_mode": None},
            case_id="a",
        ),
        _case(
            {"expected_failure": True, "actual_flagged": False, "failure_mode": None},
            case_id="b",
        ),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert len(result.per_mode) == 1
    assert result.per_mode[0].failure_mode is None
    assert result.per_mode[0].n_cases == 2
    assert result.sensitivity == pytest.approx(0.5)


def test_adversarial_identical_dice_but_defined_feature_correlation():
    """A cohort with candidates present but every DICE value identical ->
    dice_vs_flag is sentinel (zero variance) while
    feature_divergence_vs_flag, built from varying divergence values on the
    same cases, may still be defined."""
    from segqc.eval.metrics import compute_cohort_metrics

    cases = [
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.7,
            divergence=0.1,
            case_id="a",
        ),
        _case(
            {"expected_failure": False, "actual_flagged": False},
            dice=0.7,
            divergence=0.2,
            case_id="b",
        ),
        _case(
            {"expected_failure": True, "actual_flagged": True},
            dice=0.7,
            divergence=0.8,
            case_id="c",
        ),
        _case(
            {"expected_failure": True, "actual_flagged": True},
            dice=0.7,
            divergence=0.9,
            case_id="d",
        ),
    ]
    result = compute_cohort_metrics(_cohort(cases))

    assert result.dice_vs_flag.coefficient is None
    assert result.dice_vs_flag.n == 4
    assert result.feature_divergence_vs_flag.coefficient is not None
    assert result.feature_divergence_vs_flag.coefficient > 0
