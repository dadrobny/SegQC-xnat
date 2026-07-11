"""Tests for the QC-verdict comparison / per-case outcome classification module
(item 052 — §8 level-1 primitive).

Covers all seventeen Acceptance Criteria plus adversarial and edge-case inputs,
built on small hand-written ``expected``-side dicts (``Expectation.to_dict()`` /
``tests/corpus`` manifest-case shaped) and an ``actual`` side assembled directly
from ``segqc.verdict.Verdict.build(...)`` + a tuple of
``segqc.heuristics.finding.Finding`` objects (bundled into a
``segqc.aggregate.CaseResult``), per the Testing Strategy's guidance to avoid a
``HeuristicConfig`` stub entirely. Every expected outcome/flag is hand-reasoned
and exact.

Additional adversarial cases: an expected failure with no ``expected_rule_ids``
(no designated rule to credit even though caught), a clean case flagged by
multiple rules (FP lists every fired rule id), duplicate ``rule_id``s across
findings (deduplicated), ``expected_labels`` given as ``frozenset``/``list``/
``set`` (normalise identically), and a ``flagged-for-review`` actual verdict
against a ``flagged-for-review`` expected verdict (TP under the default
threshold).

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import copy

import pytest

from segqc.aggregate import CaseResult
from segqc.heuristics.finding import Finding
from segqc.io import SegQCInputError
from segqc.verdict import Reason, Severity, Verdict


# =========================================================================== #
# Helpers
# =========================================================================== #


def _finding(rule_id, severity, labels=()):
    """Build a single Finding with a fixed non-empty reason string."""
    return Finding(rule_id=rule_id, severity=severity, reason="test reason", labels=labels)


def _actual(findings=()):
    """Assemble a CaseResult from findings, deriving the Verdict directly via
    Verdict.build (no HeuristicConfig stub needed)."""
    findings = tuple(findings)
    reasons = tuple(
        Reason(message=f.reason, severity=f.severity, labels=f.labels) for f in findings
    )
    verdict = Verdict.build(reasons=reasons, per_label={})
    return CaseResult(verdict=verdict, findings=findings)


def _expected(
    verdict,
    *,
    rule_ids=None,
    labels=None,
    failure_mode=None,
    failure_mode_name=None,
):
    """Build a minimal expected-side mapping, only including keys given."""
    d = {"expected_verdict": verdict}
    if rule_ids is not None:
        d["expected_rule_ids"] = rule_ids
    if labels is not None:
        d["expected_labels"] = labels
    if failure_mode is not None:
        d["failure_mode"] = failure_mode
    if failure_mode_name is not None:
        d["failure_mode_name"] = failure_mode_name
    return d


# =========================================================================== #
# AC1: module & public API exist
# =========================================================================== #


def test_ac1_import_from_outcome_module():
    """AC1: classify_outcome, Outcome, CaseOutcome import from segqc.eval.outcome."""
    from segqc.eval.outcome import CaseOutcome, Outcome, classify_outcome  # noqa: F401

    assert callable(classify_outcome)


def test_ac1_reexported_from_eval_package():
    """AC1: classify_outcome is re-exported from segqc.eval."""
    from segqc.eval import classify_outcome

    assert callable(classify_outcome)


def test_ac1_module_dunder_all():
    """AC1: segqc.eval.outcome.__all__ lists all three public names."""
    import segqc.eval.outcome as outcome_mod

    assert set(outcome_mod.__all__) >= {"classify_outcome", "Outcome", "CaseOutcome"}


def test_ac1_outcome_enum_members_and_labels():
    """AC1: Outcome has exactly the four documented members with the correct labels."""
    from segqc.eval.outcome import Outcome

    assert {m.name for m in Outcome} == {
        "TRUE_POSITIVE",
        "FALSE_POSITIVE",
        "TRUE_NEGATIVE",
        "FALSE_NEGATIVE",
    }
    assert Outcome.TRUE_POSITIVE.label == "TP"
    assert Outcome.FALSE_POSITIVE.label == "FP"
    assert Outcome.TRUE_NEGATIVE.label == "TN"
    assert Outcome.FALSE_NEGATIVE.label == "FN"


def test_ac1_case_outcome_is_frozen_dataclass_with_fields():
    """AC1: CaseOutcome is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.outcome import CaseOutcome

    assert dataclasses.is_dataclass(CaseOutcome)
    field_names = {f.name for f in dataclasses.fields(CaseOutcome)}
    assert field_names == {
        "outcome",
        "expected_verdict",
        "actual_verdict",
        "expected_failure",
        "actual_flagged",
        "caught",
        "failure_mode",
        "failure_mode_name",
        "expected_rule_ids",
        "expected_labels",
        "fired_rule_ids",
        "designated_rule_fired",
        "caught_by_designated_rule",
    }
    assert CaseOutcome.__dataclass_params__.frozen is True


# =========================================================================== #
# AC2: clean GT that passes -> TN
# =========================================================================== #


def test_ac2_clean_gt_passes_is_true_negative():
    """AC2: pass expectation + no-findings PASS CaseResult -> TN."""
    from segqc.eval.outcome import Outcome, classify_outcome

    result = classify_outcome(_expected("pass"), _actual([]))
    assert result.outcome is Outcome.TRUE_NEGATIVE
    assert result.expected_failure is False
    assert result.actual_flagged is False
    assert result.caught is None
    assert result.actual_verdict == "pass"
    assert result.expected_verdict == "pass"


# =========================================================================== #
# AC3: clean GT wrongly flagged -> FP
# =========================================================================== #


def test_ac3_clean_gt_flagged_is_false_positive():
    """AC3: pass expectation + a FLAG CaseResult -> FP, fired_rule_ids populated."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual([_finding("bounds", Severity.FLAG, {5})])
    result = classify_outcome(_expected("pass"), actual)
    assert result.outcome is Outcome.FALSE_POSITIVE
    assert result.expected_failure is False
    assert result.actual_flagged is True
    assert result.caught is None
    assert result.fired_rule_ids == ("bounds",)


def test_ac3_clean_gt_failed_is_false_positive():
    """AC3: pass expectation + a FAIL CaseResult -> FP."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual([_finding("bounds", Severity.FAIL, {5})])
    result = classify_outcome(_expected("pass"), actual)
    assert result.outcome is Outcome.FALSE_POSITIVE
    assert result.actual_flagged is True
    assert result.fired_rule_ids == ("bounds",)


# =========================================================================== #
# AC4: known failure caught by its designated rule on the expected label -> TP
# =========================================================================== #


def test_ac4_known_failure_caught_by_designated_rule():
    """AC4: fail expectation + a matching designated-rule Finding on the label -> TP, caught."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected(
        "fail",
        rule_ids={"fragmentation"},
        labels={22},
        failure_mode=2,
        failure_mode_name="fragmentation",
    )
    actual = _actual([_finding("fragmentation", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.outcome is Outcome.TRUE_POSITIVE
    assert result.expected_failure is True
    assert result.actual_flagged is True
    assert result.caught is True
    assert result.failure_mode == 2
    assert result.failure_mode_name == "fragmentation"
    assert result.designated_rule_fired is True
    assert result.caught_by_designated_rule is True


# =========================================================================== #
# AC5: known failure that passes -> FN, mode missed
# =========================================================================== #


def test_ac5_known_failure_missed_is_false_negative():
    """AC5: same fail expectation as AC4 + a no-findings PASS CaseResult -> FN, both flags False."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected(
        "fail",
        rule_ids={"fragmentation"},
        labels={22},
        failure_mode=2,
        failure_mode_name="fragmentation",
    )
    result = classify_outcome(expected, _actual([]))
    assert result.outcome is Outcome.FALSE_NEGATIVE
    assert result.expected_failure is True
    assert result.actual_flagged is False
    assert result.caught is False
    assert result.designated_rule_fired is False
    assert result.caught_by_designated_rule is False


# =========================================================================== #
# AC6: flag counts as a raised concern by default (ternary -> binary reduction)
# =========================================================================== #


def test_ac6_flag_only_verdict_is_true_positive_against_fail_expectation():
    """AC6: default threshold -> a FLAG-only CaseResult vs a fail expectation is TP."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual([_finding("r", Severity.FLAG, {1})])
    result = classify_outcome(_expected("fail", rule_ids={"r"}, labels={1}), actual)
    assert result.actual_flagged is True
    assert result.outcome is Outcome.TRUE_POSITIVE


def test_ac6_flagged_for_review_expectation_is_a_failure():
    """AC6: an expected_verdict of flagged-for-review yields expected_failure True by default."""
    from segqc.eval.outcome import classify_outcome

    result = classify_outcome(_expected("flagged-for-review"), _actual([]))
    assert result.expected_failure is True


# =========================================================================== #
# AC7: positive_severity raises the bar for "flagged"
# =========================================================================== #


def test_ac7_stricter_threshold_flag_only_is_not_flagged():
    """AC7: with positive_severity=FAIL, a FLAG-only CaseResult is not actual_flagged."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual([_finding("r", Severity.FLAG, {1})])
    result = classify_outcome(
        _expected("pass"), actual, positive_severity=Severity.FAIL
    )
    assert result.actual_flagged is False
    assert result.outcome is Outcome.TRUE_NEGATIVE


def test_ac7_stricter_threshold_flag_only_vs_fail_expectation_is_false_negative():
    """AC7: with positive_severity=FAIL, a FLAG-only CaseResult vs a fail expectation is FN."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual([_finding("r", Severity.FLAG, {1})])
    result = classify_outcome(
        _expected("fail", rule_ids={"r"}, labels={1}),
        actual,
        positive_severity=Severity.FAIL,
    )
    assert result.outcome is Outcome.FALSE_NEGATIVE


def test_ac7_stricter_threshold_reduces_flagged_for_review_expectation_symmetrically():
    """AC7: with positive_severity=FAIL, a flagged-for-review expectation is expected_failure False."""
    from segqc.eval.outcome import classify_outcome

    result = classify_outcome(
        _expected("flagged-for-review"), _actual([]), positive_severity=Severity.FAIL
    )
    assert result.expected_failure is False


# =========================================================================== #
# AC8: flagged by an incidental (non-designated) rule -> TP, not credited
# =========================================================================== #


def test_ac8_incidental_rule_is_true_positive_but_not_designated_credited():
    """AC8: only an "other" rule fires -> TP, caught True, designated flags False."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels={22})
    actual = _actual([_finding("other", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.outcome is Outcome.TRUE_POSITIVE
    assert result.caught is True
    assert result.designated_rule_fired is False
    assert result.caught_by_designated_rule is False


# =========================================================================== #
# AC9: designated rule fired on the WRONG label -> fired, not credited
# =========================================================================== #


def test_ac9_designated_rule_wrong_label_not_credited():
    """AC9: designated rule fires on K != expected label L -> fired True, credited False."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels={22})
    actual = _actual([_finding("r", Severity.FAIL, {99})])
    result = classify_outcome(expected, actual)
    assert result.designated_rule_fired is True
    assert result.caught_by_designated_rule is False
    assert result.outcome is Outcome.TRUE_POSITIVE
    assert result.caught is True


# =========================================================================== #
# AC10: partial label match counts (>=1 expected label suffices)
# =========================================================================== #


def test_ac10_partial_label_match_credits_designated_rule():
    """AC10: expected_labels={L1, L2}, finding hits only L1 -> caught_by_designated_rule True."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels={22, 23})
    actual = _actual([_finding("r", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.caught_by_designated_rule is True


# =========================================================================== #
# AC11: case-level expected finding (no expected labels) -> rule id match suffices
# =========================================================================== #


def test_ac11_empty_expected_labels_rule_id_match_suffices():
    """AC11: expected_labels={} + Finding(rule_id="r", labels={}) -> both designated flags True."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels=set())
    actual = _actual([_finding("r", Severity.FAIL, set())])
    result = classify_outcome(expected, actual)
    assert result.designated_rule_fired is True
    assert result.caught_by_designated_rule is True


# =========================================================================== #
# AC12: multiple expected rule ids -- any one firing credits the mode
# =========================================================================== #


def test_ac12_multiple_expected_rule_ids_any_one_credits():
    """AC12: expected_rule_ids={"r1","r2"} + Finding("r2", labels={L}) on expected L -> both credited."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r1", "r2"}, labels={22})
    actual = _actual([_finding("r2", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.designated_rule_fired is True
    assert result.caught_by_designated_rule is True


# =========================================================================== #
# AC13: expected side accepts the Expectation.to_dict() / manifest-case mapping
# =========================================================================== #


def test_ac13_full_manifest_case_shaped_dict_round_trips():
    """AC13: a full manifest-case-shaped dict (all keys) populates every corresponding field."""
    from segqc.eval.outcome import classify_outcome

    expected = {
        "expected_verdict": "fail",
        "expected_rule_ids": ["fragmentation"],
        "expected_labels": [22],
        "failure_mode": 2,
        "failure_mode_name": "fragmentation",
        "detail": "synthetic fragmentation perturbation",
    }
    actual = _actual([_finding("fragmentation", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.expected_rule_ids == ("fragmentation",)
    assert result.expected_labels == (22,)
    assert result.failure_mode == 2
    assert result.failure_mode_name == "fragmentation"


def test_ac13_minimal_expected_verdict_only_defaults():
    """AC13: {"expected_verdict": "pass"} defaults failure_mode/name to None and tuples to ()."""
    from segqc.eval.outcome import classify_outcome

    result = classify_outcome({"expected_verdict": "pass"}, _actual([]))
    assert result.failure_mode is None
    assert result.failure_mode_name is None
    assert result.expected_rule_ids == ()
    assert result.expected_labels == ()


# =========================================================================== #
# AC14: rule-id/label sets are order-independent and deduplicated
# =========================================================================== #


def test_ac14_unsorted_duplicated_inputs_normalise_identically():
    """AC14: unsorted lists with a duplicate, and out-of-order findings, still normalise sorted+deduped."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected(
        "fail",
        rule_ids=["r2", "r1", "r1"],
        labels=[23, 22, 22],
    )
    actual = _actual(
        [
            _finding("r2", Severity.FAIL, {23}),
            _finding("r1", Severity.FAIL, {22}),
        ]
    )
    result = classify_outcome(expected, actual)
    assert result.expected_rule_ids == ("r1", "r2")
    assert result.expected_labels == (22, 23)
    assert result.fired_rule_ids == ("r1", "r2")


# =========================================================================== #
# AC15: malformed expected input raises SegQCInputError
# =========================================================================== #


def test_ac15_expected_not_a_mapping_raises():
    """AC15: expected=None raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    with pytest.raises(SegQCInputError):
        classify_outcome(None, _actual([]))


def test_ac15_expected_missing_verdict_key_raises():
    """AC15: an empty expected mapping (no expected_verdict) raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    with pytest.raises(SegQCInputError):
        classify_outcome({}, _actual([]))


def test_ac15_expected_verdict_unrecognised_label_raises():
    """AC15: an unrecognised expected_verdict string raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    with pytest.raises(SegQCInputError):
        classify_outcome({"expected_verdict": "bogus"}, _actual([]))


def test_ac15_not_raw_key_error_or_value_error():
    """AC15: malformed expected input is a SegQCInputError, not a bare KeyError/ValueError."""
    from segqc.eval.outcome import classify_outcome

    try:
        classify_outcome({}, _actual([]))
    except SegQCInputError:
        pass
    else:
        pytest.fail("expected SegQCInputError")


# =========================================================================== #
# AC16: malformed actual input raises SegQCInputError
# =========================================================================== #


def test_ac16_actual_none_raises():
    """AC16: actual=None raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    with pytest.raises(SegQCInputError):
        classify_outcome(_expected("pass"), None)


def test_ac16_actual_is_a_mapping_not_case_result_raises():
    """AC16: actual as a plain mapping (not a CaseResult) raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    with pytest.raises(SegQCInputError):
        classify_outcome(_expected("pass"), {"verdict": "pass"})


def test_ac16_actual_missing_findings_attribute_raises():
    """AC16: an object with .verdict but no .findings raises SegQCInputError."""
    from segqc.eval.outcome import classify_outcome

    class _NoFindings:
        verdict = Verdict.build(reasons=(), per_label={})

    with pytest.raises(SegQCInputError):
        classify_outcome(_expected("pass"), _NoFindings())


def test_ac16_not_raw_attribute_error():
    """AC16: malformed actual input is a SegQCInputError, not a bare AttributeError."""
    from segqc.eval.outcome import classify_outcome

    try:
        classify_outcome(_expected("pass"), None)
    except SegQCInputError:
        pass
    else:
        pytest.fail("expected SegQCInputError")


# =========================================================================== #
# AC17: pure, deterministic, and non-mutating
# =========================================================================== #


def test_ac17_deterministic_across_two_calls():
    """AC17: two calls on the same inputs return equal CaseOutcomes."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels={22})
    actual = _actual([_finding("r", Severity.FAIL, {22})])
    r1 = classify_outcome(expected, actual)
    r2 = classify_outcome(expected, actual)
    assert r1 == r2


def test_ac17_inputs_not_mutated():
    """AC17: the expected dict and the actual CaseResult are unchanged after the call."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels={22})
    actual = _actual([_finding("r", Severity.FAIL, {22})])
    expected_before = copy.deepcopy(expected)
    actual_findings_before = actual.findings
    actual_verdict_before = actual.verdict

    classify_outcome(expected, actual)

    assert expected == expected_before
    assert actual.findings == actual_findings_before
    assert actual.verdict == actual_verdict_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_no_expected_rule_ids_but_still_true_positive():
    """A fail expectation with no expected_rule_ids -> TP by verdict, no designated credit."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected("fail")
    actual = _actual([_finding("some_rule", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.outcome is Outcome.TRUE_POSITIVE
    assert result.caught is True
    assert result.designated_rule_fired is False
    assert result.caught_by_designated_rule is False


def test_adv_clean_case_flagged_by_multiple_rules_lists_all():
    """A clean case flagged by two rules -> FP with both rule ids in fired_rule_ids."""
    from segqc.eval.outcome import Outcome, classify_outcome

    actual = _actual(
        [
            _finding("bounds", Severity.FLAG, {5}),
            _finding("fragmentation", Severity.FAIL, {6}),
        ]
    )
    result = classify_outcome(_expected("pass"), actual)
    assert result.outcome is Outcome.FALSE_POSITIVE
    assert result.fired_rule_ids == ("bounds", "fragmentation")


def test_adv_duplicate_rule_ids_across_findings_deduplicated():
    """Two findings sharing the same rule_id (different labels) -> fired_rule_ids has one entry."""
    from segqc.eval.outcome import classify_outcome

    actual = _actual(
        [
            _finding("bounds", Severity.FLAG, {5}),
            _finding("bounds", Severity.FLAG, {6}),
        ]
    )
    result = classify_outcome(_expected("pass"), actual)
    assert result.fired_rule_ids == ("bounds",)


@pytest.mark.parametrize("label_container", [frozenset({22}), {22}, [22], (22,)])
def test_adv_expected_labels_container_types_normalise_identically(label_container):
    """expected_labels given as frozenset/set/list/tuple all normalise to the same tuple."""
    from segqc.eval.outcome import classify_outcome

    expected = _expected("fail", rule_ids={"r"}, labels=label_container)
    actual = _actual([_finding("r", Severity.FAIL, {22})])
    result = classify_outcome(expected, actual)
    assert result.expected_labels == (22,)
    assert result.caught_by_designated_rule is True


def test_adv_flagged_for_review_actual_against_flagged_for_review_expected_is_true_positive():
    """A flagged-for-review actual verdict vs a flagged-for-review expectation -> TP under default threshold."""
    from segqc.eval.outcome import Outcome, classify_outcome

    expected = _expected("flagged-for-review", rule_ids={"r"}, labels={1})
    actual = _actual([_finding("r", Severity.FLAG, {1})])
    result = classify_outcome(expected, actual)
    assert result.outcome is Outcome.TRUE_POSITIVE
    assert result.actual_verdict == "flagged-for-review"
    assert result.expected_verdict == "flagged-for-review"


def test_adv_empty_findings_list_is_pass_verdict():
    """An actual CaseResult with an empty findings tuple has actual_verdict 'pass'."""
    from segqc.eval.outcome import classify_outcome

    result = classify_outcome(_expected("pass"), _actual([]))
    assert result.actual_verdict == "pass"
    assert result.fired_rule_ids == ()
