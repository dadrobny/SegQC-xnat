"""Tests for the threshold-calibration loop (item 055 -- Stage-7 calibration
over item 053's harness + item 054's metrics).

Covers all fifteen Acceptance Criteria plus adversarial and edge-case inputs.
``segqc.eval.calibrate`` does not exist yet at the time this file is written;
its names are imported **locally inside each test function** (mirroring
``tests/test_053_eval_harness.py`` / ``tests/test_054_metrics.py``'s treatment
of their then-new modules) so the file can still be collected before the
module is implemented. Names from the already-merged ``segqc.eval.harness``
and ``segqc.eval.metrics`` modules (items 053/054) are imported at the top of
the file as usual.

Three complementary techniques keep this suite fast and precise:

1. **Pure config-transformation tests** (AC1-AC4, adversarial) exercise
   ``ThresholdAxis``/``apply_assignment`` directly against a bare
   ``segqc.config.default_config()`` -- no pipeline, no evaluation.
2. **Direct ``CalibrationObjective.evaluate(metrics)`` unit tests** (AC6) feed
   hand-built ``CohortMetrics`` (mirroring test_054's ``_outcome``/``_case``
   factories) straight into the objective, independent of the grid loop.
3. **Stub-patched grid-loop tests** (AC5, AC8-AC12, AC14, AC15, most
   adversarial cases) monkeypatch ``evaluate_cohort`` so
   ``calibrate_thresholds`` runs its real grid/selection/serialisation logic
   against small, fully-controlled hand-built ``CaseEvaluation`` records
   (via ``compute_cohort_metrics``, run for real) without invoking the actual
   QC pipeline per grid point -- exactly the "fake/stub cohort object
   exposing ``.cases``" approach the item's Testing Strategy documents as an
   alternative to a full synthetic cohort. The stub is installed at
   ``segqc.eval.harness.evaluate_cohort`` *and*, if importable,
   ``segqc.eval.calibrate.evaluate_cohort`` (``raising=False``) so it takes
   effect whichever import style (module-level or per-call local import) the
   new module ends up using.
4. **Real small synthetic-cohort tests** (AC7, AC13, an empty-cohort
   adversarial case) exercise the true pipeline end-to-end on tiny
   single-level ground truths built directly as raw ``ndarray`` label maps
   (bare rectangular blocks at integer vertebra label 22 / "L3"), following
   ``tests/test_053_eval_harness.py``'s own adversarial pattern of
   constructing raw arrays rather than the heavier ``segqc.synth`` corpus
   machinery. A single, compact, off-border label keeps every other default
   rule (coverage/sequence/border/mislabel/fragmentation/reference_delta)
   silent, isolating the swept ``bounds`` threshold as the only variable
   signal (see ``_bounds_case`` below).

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from segqc.config import default_config
from segqc.eval.harness import CaseEvaluation, CohortEvaluation, EvaluationCase
from segqc.eval.metrics import (
    CohortMetrics,
    ConfusionCounts,
    CorrelationResult,
    PerModeSensitivity,
    compute_cohort_metrics,
)
from segqc.eval.outcome import CaseOutcome, Outcome
from segqc.io import SegQCInputError

LUMBAR_LABEL = 22  # "L3" per segqc.labels.DEFAULT_LABEL_MAP


# =========================================================================== #
# Hand-built CaseEvaluation factory (mirrors test_054's _outcome/_case)
# =========================================================================== #


def _outcome(**kwargs) -> CaseOutcome:
    """Build a CaseOutcome with every field defaulted (a clean TN), overridable
    by keyword -- see tests/test_054_metrics.py's identical factory."""
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


def _stub_case(outcome_kwargs, case_id="c") -> CaseEvaluation:
    """A CaseEvaluation with no overlap/feature_match -- only outcome matters
    for the metrics calibrate_thresholds' objective reads (FPR, sensitivity,
    per-mode designated-rule catch)."""
    return CaseEvaluation(
        case_id=case_id,
        outcome=_outcome(**outcome_kwargs),
        overlap=None,
        feature_match=None,
        candidate_present=False,
        subject="gt",
        metadata=None,
    )


def _make_evaluate_cohort_stub(builder):
    """Return a stand-in for ``segqc.eval.harness.evaluate_cohort`` that
    ignores ``cases``/``positive_severity`` and instead derives the cohort
    entirely from ``config`` via ``builder(config) -> list[CaseEvaluation]``,
    so a grid point's config value deterministically controls the resulting
    metrics without running the real pipeline."""

    def _stub(cases, config, *, positive_severity=None):
        return CohortEvaluation(cases=tuple(builder(config)))

    return _stub


def _patch_evaluate_cohort(monkeypatch, stub):
    """Install *stub* in place of ``evaluate_cohort`` for calibrate_thresholds.

    Patches the source module (``segqc.eval.harness.evaluate_cohort``) --
    effective if the new module does a per-call local import, matching
    ``segqc.eval.harness.evaluate_case``'s own lazy-import-of-pipeline
    convention -- and, if importable, ``segqc.eval.calibrate.evaluate_cohort``
    directly (``raising=False``) -- effective if it is instead imported once
    at module load time. Whichever style the implementation uses, the stub
    takes effect.
    """
    import segqc.eval.harness as harness_mod

    monkeypatch.setattr(harness_mod, "evaluate_cohort", stub)
    try:
        import segqc.eval.calibrate as calibrate_mod
    except ImportError:
        return
    monkeypatch.setattr(calibrate_mod, "evaluate_cohort", stub, raising=False)


def _assert_plain_json_types(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            _assert_plain_json_types(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_plain_json_types(v)
    else:
        assert obj is None or isinstance(obj, (str, int, float, bool))


# =========================================================================== #
# Real single-level raw-array GT builder for AC7/AC13/adversarial-empty
# =========================================================================== #


def _bounds_case(case_id, dims, expected_verdict, **expected_extra):
    """Build an EvaluationCase from a raw ndarray: a single compact
    rectangular block of ``LUMBAR_LABEL`` voxels sized ``dims`` (x, y, z),
    isotropic 1mm spacing so ``physical_volume_mm3 == prod(dims)`` exactly
    and each ``extent_*_mm == dims[i]`` exactly (segqc.features.geometry).
    Placed well away from the volume border so no other default rule
    (coverage/sequence/border/mislabel/fragmentation) fires."""
    shape = (160, 160, 160)
    arr = np.zeros(shape, dtype=np.int64)
    x, y, z = dims
    arr[10 : 10 + x, 10 : 10 + y, 10 : 10 + z] = LUMBAR_LABEL
    expected = {"expected_verdict": expected_verdict}
    expected.update(expected_extra)
    return EvaluationCase(
        case_id=case_id, gt=arr, expected=expected, spacing=(1.0, 1.0, 1.0)
    )


# =========================================================================== #
# AC1: ThresholdAxis defines a sweepable parameter
# =========================================================================== #


def test_ac1_constructs_with_documented_fields():
    """AC1: ThresholdAxis carries name/rule_id/param_path/values verbatim."""
    from segqc.eval.calibrate import ThresholdAxis

    axis = ThresholdAxis(
        name="lumbar_max_volume",
        rule_id="bounds",
        param_path=("lumbar", "max_volume_mm3"),
        values=(1000.0, 2000.0),
    )
    assert axis.name == "lumbar_max_volume"
    assert axis.rule_id == "bounds"
    assert axis.param_path == ("lumbar", "max_volume_mm3")
    assert axis.values == (1000.0, 2000.0)


def test_ac1_coerces_list_inputs_to_tuples():
    """AC1: list-typed param_path/values are coerced to tuples (immutable/hashable)."""
    from segqc.eval.calibrate import ThresholdAxis

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=["max_robust_z"], values=[1.0, 2.0]
    )
    assert axis.param_path == ("max_robust_z",)
    assert axis.values == (1.0, 2.0)
    hash(axis)  # must not raise -- confirms fields are hashable tuples


def test_ac1_empty_param_path_raises_segqc_input_error():
    """AC1: an empty param_path raises SegQCInputError."""
    from segqc.eval.calibrate import ThresholdAxis

    with pytest.raises(SegQCInputError):
        ThresholdAxis(name="k", rule_id="bounds", param_path=(), values=(1.0,))


def test_ac1_empty_values_raises_segqc_input_error():
    """AC1: an empty values tuple raises SegQCInputError."""
    from segqc.eval.calibrate import ThresholdAxis

    with pytest.raises(SegQCInputError):
        ThresholdAxis(
            name="k", rule_id="bounds", param_path=("lumbar", "max_volume_mm3"), values=()
        )


# =========================================================================== #
# AC2: applying an axis produces a new config with the nested param set
# =========================================================================== #


def test_ac2_apply_assignment_sets_nested_param_and_preserves_other_fields():
    """AC2: apply_assignment sets rules[bounds][params][lumbar][max_volume_mm3]
    while every other config field is preserved."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment

    base_config = default_config()
    axis = ThresholdAxis(
        name="lumbar_max_volume",
        rule_id="bounds",
        param_path=("lumbar", "max_volume_mm3"),
        values=(999.0, 5000.0),
    )
    new_config = apply_assignment(base_config, {"lumbar_max_volume": 999.0}, (axis,))

    group = new_config.rule_param("bounds", "lumbar", {})
    assert group["max_volume_mm3"] == 999.0
    assert new_config.schema_version == base_config.schema_version
    assert new_config.min_fragment_voxels == base_config.min_fragment_voxels
    assert new_config.verdict == base_config.verdict
    assert new_config.reference == base_config.reference


def test_ac2_apply_assignment_creates_intermediate_dicts_when_absent():
    """AC2: rules/params/nested dicts are created as needed for a fresh rule id."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment

    base_config = default_config()
    assert base_config.rules == {}
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5,)
    )
    new_config = apply_assignment(base_config, {"k": 2.5}, (axis,))
    assert new_config.rule_param("reference_delta", "max_robust_z", None) == 2.5


# =========================================================================== #
# AC3: application never mutates the base config
# =========================================================================== #


def test_ac3_apply_assignment_does_not_mutate_base_config():
    """AC3: base_config (and its rules dict) is unchanged after apply_assignment."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment

    base_config = default_config()
    base_before = copy.deepcopy(base_config)
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(2.5,)
    )
    apply_assignment(base_config, {"k": 2.5}, (axis,))

    assert base_config == base_before
    assert base_config.rules == {}


def test_ac3_repeated_application_yields_independent_configs():
    """AC3: two applications off the same base yield independent configs with
    no shared nested state."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment

    base_config = default_config()
    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0)
    )
    config_a = apply_assignment(base_config, {"k": 1.0}, (axis,))
    config_b = apply_assignment(base_config, {"k": 2.0}, (axis,))

    assert config_a is not config_b
    assert config_a.rules is not config_b.rules
    assert config_a.rule_param("reference_delta", "max_robust_z", None) == 1.0
    assert config_b.rule_param("reference_delta", "max_robust_z", None) == 2.0

    # Mutating one candidate's nested dict directly must not leak into the other.
    config_a.rules["reference_delta"]["params"]["max_robust_z"] = -1.0
    assert config_b.rule_param("reference_delta", "max_robust_z", None) == 2.0


# =========================================================================== #
# AC4: the grid is the deterministic Cartesian product of the axes
# =========================================================================== #


def _trivial_stub(config):
    return [_stub_case({"expected_failure": False, "actual_flagged": False}, case_id="tn0")]


def test_ac4_grid_is_cartesian_product_last_axis_fastest(monkeypatch):
    """AC4: N axes with k_i values each yield prod(k_i) assignments, axes in
    given order, values in each axis's order, last axis varying fastest."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_trivial_stub))

    axis_a = ThresholdAxis(
        name="a", rule_id="bounds", param_path=("lumbar", "max_volume_mm3"), values=(10.0, 20.0)
    )
    axis_b = ThresholdAxis(
        name="b", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0, 3.0)
    )
    result = calibrate_thresholds([], default_config(), (axis_a, axis_b))

    assert len(result.candidates) == 6
    assignments = [c.assignment for c in result.candidates]
    assert assignments == [
        {"a": 10.0, "b": 1.0},
        {"a": 10.0, "b": 2.0},
        {"a": 10.0, "b": 3.0},
        {"a": 20.0, "b": 1.0},
        {"a": 20.0, "b": 2.0},
        {"a": 20.0, "b": 3.0},
    ]


def test_ac4_empty_axes_yields_single_empty_assignment(monkeypatch):
    """AC4: an empty axis sequence yields exactly one candidate: the empty
    assignment (base config unchanged)."""
    from segqc.eval.calibrate import calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_trivial_stub))

    result = calibrate_thresholds([], default_config(), ())
    assert len(result.candidates) == 1
    assert result.candidates[0].assignment == {}


# =========================================================================== #
# AC5: each candidate is evaluated via 053 + 054
# =========================================================================== #


def test_ac5_one_candidate_result_per_grid_point_in_order(monkeypatch):
    """AC5: result.candidates has one CandidateResult per grid point, in grid
    order, each carrying a real CohortMetrics."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_trivial_stub))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0, 3.0)
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert len(result.candidates) == 3
    assert [c.assignment for c in result.candidates] == [{"k": 1.0}, {"k": 2.0}, {"k": 3.0}]
    for candidate in result.candidates:
        assert isinstance(candidate.metrics, CohortMetrics)
        assert candidate.metrics.n_cases == 1


# =========================================================================== #
# AC6: the objective classifies feasibility
# =========================================================================== #


def _metrics_with_per_mode(per_mode, false_positive_rate=0.0):
    return CohortMetrics(
        counts=ConfusionCounts(tp=0, fp=0, tn=0, fn=0),
        false_positive_rate=false_positive_rate,
        sensitivity=None,
        specificity=None,
        per_mode=per_mode,
        dice_vs_flag=CorrelationResult(
            coefficient=None, n=0, method="pearson", x_variable="mean_dice", y_variable="flagged"
        ),
        feature_divergence_vs_flag=CorrelationResult(
            coefficient=None,
            n=0,
            method="pearson",
            x_variable="case_divergence",
            y_variable="flagged",
        ),
        n_cases=0,
    )


def test_ac6_objective_feasible_when_every_present_mode_meets_floor():
    """AC6: every reported per-mode sensitivity (n_cases>0) >= floor -> feasible."""
    from segqc.eval.calibrate import CalibrationObjective

    metrics = _metrics_with_per_mode(
        (
            PerModeSensitivity(
                failure_mode=1,
                failure_mode_name=None,
                n_cases=2,
                n_caught=2,
                n_caught_by_designated_rule=2,
                sensitivity=1.0,
                caught_rate=1.0,
            ),
        )
    )
    feasible, score = CalibrationObjective().evaluate(metrics)
    assert feasible is True
    assert score == pytest.approx(0.0)


def test_ac6_objective_infeasible_when_a_present_mode_misses_floor():
    """AC6: any present-mode sensitivity below the floor -> infeasible."""
    from segqc.eval.calibrate import CalibrationObjective

    metrics = _metrics_with_per_mode(
        (
            PerModeSensitivity(
                failure_mode=1,
                failure_mode_name=None,
                n_cases=2,
                n_caught=1,
                n_caught_by_designated_rule=1,
                sensitivity=0.5,
                caught_rate=0.5,
            ),
        )
    )
    feasible, _score = CalibrationObjective(sensitivity_floor=1.0).evaluate(metrics)
    assert feasible is False


def test_ac6_objective_default_floor_is_one():
    """AC6/Assumptions: CalibrationObjective() defaults sensitivity_floor to 1.0."""
    from segqc.eval.calibrate import CalibrationObjective

    assert CalibrationObjective().sensitivity_floor == pytest.approx(1.0)


# =========================================================================== #
# AC7: selection recovers a known separating threshold
# =========================================================================== #


def test_ac7_selection_recovers_separating_bounds_threshold():
    """AC7: on a real cohort where only a mid-range max_volume_mm3 both passes
    the clean case and catches the oversized injected failure, calibrate_
    thresholds selects that value as best, feasible, minimal FPR."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    clean_case = _bounds_case("clean", (22, 22, 21), "pass")  # volume 10164 mm3
    failure_case = _bounds_case(
        "oversized",
        (60, 60, 36),  # volume 129600 mm3
        "fail",
        expected_rule_ids=["bounds"],
        expected_labels=[LUMBAR_LABEL],
        failure_mode=1,
    )

    axis = ThresholdAxis(
        name="lumbar_max_volume",
        rule_id="bounds",
        param_path=("lumbar", "max_volume_mm3"),
        # 5000: too tight -> clean case falsely flagged too.
        # 50000: separates clean (10164, passes) from oversized (129600, caught).
        # 150000: too loose -> oversized no longer exceeds the threshold.
        values=(5000.0, 50000.0, 150000.0),
    )
    result = calibrate_thresholds([clean_case, failure_case], default_config(), (axis,))

    assert result.feasible is True
    assert result.best is not None
    assert result.best.assignment == {"lumbar_max_volume": 50000.0}
    assert result.best.metrics.false_positive_rate == pytest.approx(0.0)


# =========================================================================== #
# AC8: among feasible candidates, the minimum-FPR one is chosen
# =========================================================================== #


def _ac8_build(config):
    threshold = config.rule_param("reference_delta", "max_robust_z", None)
    fp_flag = threshold == 10.0
    return [
        _stub_case({"expected_failure": False, "actual_flagged": fp_flag}, case_id="clean0"),
        _stub_case({"expected_failure": False, "actual_flagged": False}, case_id="clean1"),
        _stub_case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 1,
                "caught_by_designated_rule": True,
            },
            case_id="fail0",
        ),
    ]


def test_ac8_minimum_fpr_feasible_candidate_is_chosen(monkeypatch):
    """AC8: two feasible candidates (0.5 vs 0.0 FPR) -> the 0.0-FPR one wins."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_ac8_build))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(10.0, 20.0)
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert result.candidates[0].feasible is True
    assert result.candidates[0].metrics.false_positive_rate == pytest.approx(0.5)
    assert result.candidates[1].feasible is True
    assert result.candidates[1].metrics.false_positive_rate == pytest.approx(0.0)
    assert result.best is not None
    assert result.best.assignment == {"k": 20.0}


# =========================================================================== #
# AC9: ties break deterministically
# =========================================================================== #


def test_ac9_fpr_tie_broken_by_sensitivity_then_grid_order(monkeypatch):
    """AC9: three candidates all feasible with FPR==0.0; candidate 2 beats
    candidate 1 on higher overall sensitivity, and beats candidate 3 (an exact
    tie with candidate 2 on both FPR and sensitivity) on earliest grid order."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    def _build(config):
        value = config.rule_param("reference_delta", "max_robust_z", None)
        # Every candidate: 1 clean (never flagged) + 2 same-mode failure cases,
        # both caught_by_designated_rule (per-mode floor 1.0 always satisfied),
        # but differing in how many are also actual_flagged (drives the coarse
        # overall CohortMetrics.sensitivity independently of per-mode catch).
        second_flagged = value != 1.0
        return [
            _stub_case({"expected_failure": False, "actual_flagged": False}, case_id="clean0"),
            _stub_case(
                {
                    "expected_failure": True,
                    "actual_flagged": True,
                    "failure_mode": 1,
                    "caught_by_designated_rule": True,
                },
                case_id="fail0",
            ),
            _stub_case(
                {
                    "expected_failure": True,
                    "actual_flagged": second_flagged,
                    "failure_mode": 1,
                    "caught_by_designated_rule": True,
                },
                case_id="fail1",
            ),
        ]

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_build))

    axis = ThresholdAxis(
        name="k",
        rule_id="reference_delta",
        param_path=("max_robust_z",),
        values=(1.0, 2.0, 3.0),
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert [c.feasible for c in result.candidates] == [True, True, True]
    fprs = [c.metrics.false_positive_rate for c in result.candidates]
    assert fprs == [pytest.approx(0.0), pytest.approx(0.0), pytest.approx(0.0)]
    sensitivities = [c.metrics.sensitivity for c in result.candidates]
    assert sensitivities == [pytest.approx(0.5), pytest.approx(1.0), pytest.approx(1.0)]

    assert result.best is not None
    assert result.best.assignment == {"k": 2.0}


# =========================================================================== #
# AC10: infeasible objective is reported, not crashed
# =========================================================================== #


def _ac10_build(config):
    return [
        _stub_case(
            {
                "expected_failure": True,
                "actual_flagged": False,
                "failure_mode": 1,
                "caught_by_designated_rule": False,
            },
            case_id="fail0",
        ),
    ]


def test_ac10_no_feasible_setting_reported_without_raising(monkeypatch):
    """AC10: no candidate meets the (default) floor -> best is None, feasible
    is False, status is a machine-readable reason, no exception raised."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_ac10_build))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0)
    )
    result = calibrate_thresholds([], default_config(), (axis,))  # must not raise

    assert result.best is None
    assert result.feasible is False
    assert result.status == "no-feasible-setting"
    assert len(result.candidates) == 2  # every grid point still evaluated & recorded


# =========================================================================== #
# AC11: the loop is deterministic
# =========================================================================== #


def test_ac11_repeated_calls_are_equal_and_byte_identical(monkeypatch):
    """AC11: two calls with the same inputs return equal best assignments and
    byte-identical to_dict() JSON."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_ac8_build))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(10.0, 20.0)
    )
    base_config = default_config()

    result_a = calibrate_thresholds([], base_config, (axis,))
    result_b = calibrate_thresholds([], base_config, (axis,))

    assert result_a.best.assignment == result_b.best.assignment
    assert json.dumps(result_a.to_dict(), sort_keys=True) == json.dumps(
        result_b.to_dict(), sort_keys=True
    )


# =========================================================================== #
# AC12: the result is well-formed and consumable by the recording step
# =========================================================================== #


def test_ac12_to_dict_round_trips_and_best_assignment_reproduces_metrics(monkeypatch):
    """AC12: to_dict() round-trips byte-identically through json.dumps/loads,
    and re-applying result.best.assignment reproduces the config that
    produced result.best.metrics."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment, calibrate_thresholds

    stub = _make_evaluate_cohort_stub(_ac8_build)
    _patch_evaluate_cohort(monkeypatch, stub)

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(10.0, 20.0)
    )
    base_config = default_config()
    result = calibrate_thresholds([], base_config, (axis,))

    assert result.best is not None
    d = result.to_dict()
    _assert_plain_json_types(d)
    assert json.loads(json.dumps(d)) == d

    rebuilt_config = apply_assignment(base_config, result.best.assignment, (axis,))
    # Re-fetch evaluate_cohort now (after patching) so we call the stub, not
    # whatever was bound at module-import time.
    from segqc.eval.harness import evaluate_cohort as patched_evaluate_cohort

    rebuilt_cohort = patched_evaluate_cohort([], rebuilt_config)
    rebuilt_metrics = compute_cohort_metrics(rebuilt_cohort)
    assert rebuilt_metrics == result.best.metrics


# =========================================================================== #
# AC13: a documented default grid over both rule families is provided
# =========================================================================== #


def test_ac13_default_axes_cover_both_rule_families_and_run_without_error():
    """AC13: default_calibration_axes() covers reference_delta and bounds, and
    is a valid input to calibrate_thresholds on a small real cohort."""
    from segqc.eval.calibrate import calibrate_thresholds, default_calibration_axes
    from segqc.synth.clean_gt import build_clean_spine

    axes = default_calibration_axes()
    assert len(axes) >= 2
    rule_ids = {axis.rule_id for axis in axes}
    assert "bounds" in rule_ids
    assert "reference_delta" in rule_ids

    reference_axes = [axis for axis in axes if axis.rule_id == "reference_delta"]
    reference_keys = {axis.param_path[-1] for axis in reference_axes}
    assert reference_keys & {"max_robust_z", "max_distribution_distance"}

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="smoke", gt=clean.seg_img, expected={"expected_verdict": "pass"}
    )
    result = calibrate_thresholds([case], default_config(), axes)  # must not raise
    assert result.n_candidates == len(result.candidates)
    assert result.n_candidates >= 1


# =========================================================================== #
# AC14: a grid-size guard prevents runaway sweeps
# =========================================================================== #


def test_ac14_grid_size_guard_raises_before_any_evaluation(monkeypatch):
    """AC14: a grid exceeding max_grid_size raises SegQCInputError before
    evaluate_cohort is ever called."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    def _boom(*_args, **_kwargs):
        raise AssertionError(
            "evaluate_cohort must not be called when the grid exceeds max_grid_size"
        )

    import segqc.eval.harness as harness_mod

    monkeypatch.setattr(harness_mod, "evaluate_cohort", _boom)
    try:
        import segqc.eval.calibrate as calibrate_mod

        monkeypatch.setattr(calibrate_mod, "evaluate_cohort", _boom, raising=False)
    except ImportError:
        pass

    axis_a = ThresholdAxis(
        name="a", rule_id="bounds", param_path=("lumbar", "max_volume_mm3"), values=(1.0, 2.0, 3.0)
    )
    axis_b = ThresholdAxis(
        name="b", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0, 3.0)
    )
    with pytest.raises(SegQCInputError):
        calibrate_thresholds([], default_config(), (axis_a, axis_b), max_grid_size=5)


# =========================================================================== #
# AC15: the shipped config and inputs are not persisted or mutated
# =========================================================================== #


def test_ac15_inputs_not_mutated(monkeypatch):
    """AC15: base_config, cases, and axes are unchanged after the call."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_trivial_stub))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0)
    )
    axes = (axis,)
    axes_before = copy.deepcopy(axes)

    base_config = default_config()
    base_config_before = copy.deepcopy(base_config)

    gt_array = np.zeros((4, 4, 4), dtype=np.int64)
    gt_before = gt_array.copy()
    expected = {"expected_verdict": "pass"}
    expected_before = copy.deepcopy(expected)
    case = EvaluationCase(case_id="c0", gt=gt_array, expected=expected)
    cases = [case]

    calibrate_thresholds(cases, base_config, axes)  # must not raise

    assert base_config == base_config_before
    assert axes == axes_before
    np.testing.assert_array_equal(gt_array, gt_before)
    assert case.expected == expected_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_axis_targets_nonexistent_param_path_creates_it():
    """A ThresholdAxis naming a brand-new rule id / param path is a valid
    input: apply_assignment creates the nested structure rather than erroring."""
    from segqc.eval.calibrate import ThresholdAxis, apply_assignment

    base_config = default_config()
    axis = ThresholdAxis(
        name="new",
        rule_id="a_brand_new_rule",
        param_path=("nested", "deep", "key"),
        values=(1,),
    )
    new_config = apply_assignment(base_config, {"new": 1}, (axis,))

    assert new_config.rule_param("a_brand_new_rule", "nested", None) == {"deep": {"key": 1}}
    # Untouched rule sections stay absent, unaffected by the new one.
    assert "bounds" not in new_config.rules


def test_adversarial_single_axis_single_value_grid(monkeypatch):
    """A single axis with a single value yields exactly one candidate."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_trivial_stub))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(3.5,)
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert len(result.candidates) == 1
    assert result.candidates[0].assignment == {"k": 3.5}


def test_adversarial_empty_cohort_no_crash_and_trivially_feasible():
    """An empty cases list -> evaluate_cohort's own empty-cohort behaviour
    (item 053 AC15) propagates: zero-case metrics, no modes present, so the
    default sensitivity floor is trivially satisfied (nothing to catch) and
    the loop reports a well-formed feasible result without any stub."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0)
    )
    result = calibrate_thresholds([], default_config(), (axis,))  # must not raise

    assert result.n_candidates == 2
    for candidate in result.candidates:
        assert candidate.metrics.n_cases == 0
        assert candidate.feasible is True
    assert result.feasible is True
    assert result.best is not None


def test_adversarial_mode_with_zero_cases_excluded_from_floor():
    """A per-mode entry with n_cases == 0 (sensitivity is None) does not
    itself cause infeasibility -- it is excluded from the floor check."""
    from segqc.eval.calibrate import CalibrationObjective

    metrics = _metrics_with_per_mode(
        (
            PerModeSensitivity(
                failure_mode=9,
                failure_mode_name=None,
                n_cases=0,
                n_caught=0,
                n_caught_by_designated_rule=0,
                sensitivity=None,
                caught_rate=None,
            ),
        )
    )
    feasible, _score = CalibrationObjective().evaluate(metrics)
    assert feasible is True


def test_adversarial_none_fpr_sorts_as_best_in_selection(monkeypatch):
    """A candidate with no expected-pass cases (false_positive_rate is None)
    beats a feasible candidate with a real, nonzero FPR -- None sorts as
    best/lowest per the item's documented ordering rule."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    def _build(config):
        value = config.rule_param("reference_delta", "max_robust_z", None)
        failure = _stub_case(
            {
                "expected_failure": True,
                "actual_flagged": True,
                "failure_mode": 1,
                "caught_by_designated_rule": True,
            },
            case_id="fail0",
        )
        if value == 1.0:
            # No expected-pass case at all -> false_positive_rate is None.
            return [failure]
        # An expected-pass case that is flagged -> a real, nonzero FPR.
        clean_flagged = _stub_case(
            {"expected_failure": False, "actual_flagged": True}, case_id="clean0"
        )
        return [failure, clean_flagged]

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_build))

    axis = ThresholdAxis(
        name="k", rule_id="reference_delta", param_path=("max_robust_z",), values=(1.0, 2.0)
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert result.candidates[0].metrics.false_positive_rate is None
    assert result.candidates[1].metrics.false_positive_rate == pytest.approx(1.0)
    assert result.best is not None
    assert result.best.assignment == {"k": 1.0}


def test_adversarial_all_candidates_infeasible_still_evaluates_every_grid_point(
    monkeypatch,
):
    """When every candidate is infeasible, the full grid is still evaluated
    (not short-circuited) and every CandidateResult is retained."""
    from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds

    _patch_evaluate_cohort(monkeypatch, _make_evaluate_cohort_stub(_ac10_build))

    axis = ThresholdAxis(
        name="k",
        rule_id="reference_delta",
        param_path=("max_robust_z",),
        values=(1.0, 2.0, 3.0),
    )
    result = calibrate_thresholds([], default_config(), (axis,))

    assert len(result.candidates) == 3
    assert all(c.feasible is False for c in result.candidates)
    assert result.best is None
    assert result.feasible is False
    assert result.status == "no-feasible-setting"
