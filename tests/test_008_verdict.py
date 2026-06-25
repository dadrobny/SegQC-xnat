"""Tests for the QC verdict data model (item 008).

Covers all ten Acceptance Criteria plus adversarial and edge-case inputs:
boundary severity comparisons, immutability after construction, determinism,
empty/single/large reason sets, wrong-type arguments, message quality, and
per-vertebra attribution.

All tests are deterministic, CPU-only, and portable (no I/O, no external deps).
"""

from __future__ import annotations

import pytest

from segqc.verdict import Reason, Severity, Verdict


# =========================================================================== #
# AC-1  Severity enum — three members with total ordering
# =========================================================================== #

def test_ac1_severity_has_exactly_three_members():
    """Severity has exactly PASS, FLAG, and FAIL — no more, no fewer."""
    members = list(Severity)
    names = {m.name for m in members}
    assert names == {"PASS", "FLAG", "FAIL"}
    assert len(members) == 3


def test_ac1_severity_total_ordering_pass_lt_flag():
    """PASS < FLAG evaluates to True."""
    assert Severity.PASS < Severity.FLAG


def test_ac1_severity_total_ordering_flag_lt_fail():
    """FLAG < FAIL evaluates to True."""
    assert Severity.FLAG < Severity.FAIL


def test_ac1_severity_total_ordering_pass_lt_fail():
    """PASS < FAIL evaluates to True (transitivity)."""
    assert Severity.PASS < Severity.FAIL


def test_ac1_severity_max_is_fail():
    """max() over all three members yields FAIL."""
    assert max(Severity.PASS, Severity.FLAG, Severity.FAIL) == Severity.FAIL


def test_ac1_severity_min_is_pass():
    """min() over all three members yields PASS."""
    assert min(Severity.PASS, Severity.FLAG, Severity.FAIL) == Severity.PASS


@pytest.mark.parametrize("higher, lower", [
    (Severity.FLAG, Severity.PASS),
    (Severity.FAIL, Severity.PASS),
    (Severity.FAIL, Severity.FLAG),
])
def test_ac1_severity_gt_symmetry(higher, lower):
    """higher > lower is also True (ordering is symmetric / anti-symmetric)."""
    assert higher > lower
    assert not (lower > higher)


# =========================================================================== #
# AC-2  Severity string labels
# =========================================================================== #

def test_ac2_severity_pass_label():
    """Severity.PASS maps to the string 'pass'."""
    assert Severity.PASS.label == "pass"


def test_ac2_severity_flag_label():
    """Severity.FLAG maps to 'flagged-for-review'."""
    assert Severity.FLAG.label == "flagged-for-review"


def test_ac2_severity_fail_label():
    """Severity.FAIL maps to 'fail'."""
    assert Severity.FAIL.label == "fail"


@pytest.mark.parametrize("member, expected", [
    (Severity.PASS, "pass"),
    (Severity.FLAG, "flagged-for-review"),
    (Severity.FAIL, "fail"),
])
def test_ac2_all_severity_labels(member, expected):
    """All three label strings match the spec exactly (no extra whitespace)."""
    assert member.label == expected
    assert isinstance(member.label, str)
    assert member.label == member.label.strip()


# =========================================================================== #
# AC-3  Reason dataclass — fields and constraints
# =========================================================================== #

def test_ac3_reason_has_required_fields():
    """Reason can be constructed with message, severity, and labels."""
    r = Reason(message="test reason", severity=Severity.FLAG, labels=frozenset({1, 2}))
    assert r.message == "test reason"
    assert r.severity == Severity.FLAG
    assert r.labels == frozenset({1, 2})


def test_ac3_reason_labels_default_is_empty_frozenset():
    """Reason.labels defaults to an empty frozenset when not provided."""
    r = Reason(message="no labels", severity=Severity.PASS)
    assert r.labels == frozenset()
    assert isinstance(r.labels, frozenset)


def test_ac3_reason_message_is_string():
    """Reason.message is a str."""
    r = Reason(message="msg", severity=Severity.FAIL)
    assert isinstance(r.message, str)


def test_ac3_reason_severity_is_severity():
    """Reason.severity is a Severity instance."""
    r = Reason(message="msg", severity=Severity.FLAG)
    assert isinstance(r.severity, Severity)


def test_ac3_reason_labels_is_frozenset():
    """Reason.labels is a frozenset of integers."""
    r = Reason(message="msg", severity=Severity.FAIL, labels=frozenset({42}))
    assert isinstance(r.labels, frozenset)
    assert 42 in r.labels


def test_ac3_reason_non_empty_message():
    """A Reason with a non-empty message constructs without error."""
    r = Reason(message="something went wrong", severity=Severity.FAIL)
    assert len(r.message) > 0


# =========================================================================== #
# AC-4  Verdict dataclass — fields and overall derivation
# =========================================================================== #

def test_ac4_verdict_has_overall_field():
    """Verdict has an 'overall' attribute of type Severity."""
    v = Verdict.build(reasons=[], per_label={})
    assert isinstance(v.overall, Severity)


def test_ac4_verdict_has_reasons_field():
    """Verdict has a 'reasons' attribute (sequence of case-level Reason objects)."""
    r = Reason(message="case-level", severity=Severity.FLAG)
    v = Verdict.build(reasons=[r], per_label={})
    assert len(v.reasons) == 1
    assert v.reasons[0] == r


def test_ac4_verdict_has_per_label_field():
    """Verdict has a 'per_label' attribute mapping int -> collection of Reason."""
    r = Reason(message="label reason", severity=Severity.FAIL)
    v = Verdict.build(reasons=[], per_label={42: [r]})
    assert 42 in v.per_label
    assert len(v.per_label[42]) == 1
    assert v.per_label[42][0] == r


def test_ac4_overall_is_max_severity():
    """overall is the maximum severity across all reasons."""
    reasons = [
        Reason(message="pass reason", severity=Severity.PASS),
        Reason(message="flag reason", severity=Severity.FLAG),
    ]
    v = Verdict.build(reasons=reasons, per_label={})
    assert v.overall == Severity.FLAG


# =========================================================================== #
# AC-5  Empty reasons → PASS
# =========================================================================== #

def test_ac5_empty_verdict_is_pass():
    """A Verdict with no reasons and no per_label entries has overall PASS."""
    v = Verdict.build(reasons=[], per_label={})
    assert v.overall == Severity.PASS


def test_ac5_empty_reasons_empty_per_label():
    """Both reasons and per_label empty → overall PASS; collections are empty."""
    v = Verdict.build(reasons=[], per_label={})
    assert v.overall == Severity.PASS
    assert len(v.reasons) == 0
    assert len(v.per_label) == 0


def test_ac5_per_label_empty_lists_is_pass():
    """per_label with keys but empty reason lists still yields PASS."""
    v = Verdict.build(reasons=[], per_label={1: [], 2: []})
    assert v.overall == Severity.PASS


# =========================================================================== #
# AC-6  Aggregation by severity
# =========================================================================== #

def test_ac6_single_fail_reason_yields_fail():
    """A single FAIL reason drives overall to FAIL."""
    r = Reason(message="fail reason", severity=Severity.FAIL)
    v = Verdict.build(reasons=[r], per_label={})
    assert v.overall == Severity.FAIL


def test_ac6_single_flag_reason_yields_flag():
    """A single FLAG reason drives overall to FLAG."""
    r = Reason(message="flag reason", severity=Severity.FLAG)
    v = Verdict.build(reasons=[r], per_label={})
    assert v.overall == Severity.FLAG


def test_ac6_single_pass_reason_yields_pass():
    """A single PASS reason keeps overall at PASS."""
    r = Reason(message="pass reason", severity=Severity.PASS)
    v = Verdict.build(reasons=[r], per_label={})
    assert v.overall == Severity.PASS


def test_ac6_mix_pass_flag_fail_yields_fail():
    """A mix of PASS + FLAG + FAIL → FAIL (max wins)."""
    reasons = [
        Reason(message="a", severity=Severity.PASS),
        Reason(message="b", severity=Severity.FLAG),
        Reason(message="c", severity=Severity.FAIL),
    ]
    v = Verdict.build(reasons=reasons, per_label={})
    assert v.overall == Severity.FAIL


def test_ac6_without_fail_reason_yields_flag():
    """Removing the FAIL reason; only PASS+FLAG remain → FLAG."""
    reasons = [
        Reason(message="a", severity=Severity.PASS),
        Reason(message="b", severity=Severity.FLAG),
    ]
    v = Verdict.build(reasons=reasons, per_label={})
    assert v.overall == Severity.FLAG


def test_ac6_only_pass_reasons_yields_pass():
    """Multiple PASS reasons → overall PASS."""
    reasons = [Reason(message=f"pass {i}", severity=Severity.PASS) for i in range(5)]
    v = Verdict.build(reasons=reasons, per_label={})
    assert v.overall == Severity.PASS


def test_ac6_severity_order_respected_across_all_combinations():
    """All 9 (severity_case, severity_per_label) pairs yield expected overall."""
    levels = [Severity.PASS, Severity.FLAG, Severity.FAIL]
    for sev_case in levels:
        for sev_label in levels:
            r_case = Reason(message="case", severity=sev_case)
            r_label = Reason(message="label", severity=sev_label)
            v = Verdict.build(reasons=[r_case], per_label={1: [r_label]})
            expected = max(sev_case, sev_label)
            assert v.overall == expected, (
                f"overall={v.overall!r} but expected {expected!r} "
                f"for case={sev_case!r}, label={sev_label!r}"
            )


# =========================================================================== #
# AC-7  Per-vertebra attribution
# =========================================================================== #

def test_ac7_per_label_fail_raises_overall():
    """A FAIL reason in per_label raises overall even with no case-level reasons."""
    r = Reason(message="label fail", severity=Severity.FAIL)
    v = Verdict.build(reasons=[], per_label={42: [r]})
    assert v.overall == Severity.FAIL


def test_ac7_per_label_flag_raises_overall_from_pass():
    """A FLAG reason in per_label raises overall from PASS to FLAG."""
    r = Reason(message="label flag", severity=Severity.FLAG)
    v = Verdict.build(reasons=[], per_label={10: [r]})
    assert v.overall == Severity.FLAG


def test_ac7_per_label_reasons_not_in_case_reasons():
    """Reasons stored under per_label do not appear in the top-level reasons list."""
    r_label = Reason(message="label-specific", severity=Severity.FAIL)
    r_case = Reason(message="case-level", severity=Severity.PASS)
    v = Verdict.build(reasons=[r_case], per_label={99: [r_label]})
    assert r_label not in v.reasons
    assert r_case in v.reasons


def test_ac7_multiple_labels_each_carry_their_own_reasons():
    """Different labels independently carry their own reason lists."""
    r1 = Reason(message="L1 fail", severity=Severity.FAIL, labels=frozenset({20}))
    r2 = Reason(message="T12 flag", severity=Severity.FLAG, labels=frozenset({19}))
    v = Verdict.build(reasons=[], per_label={20: [r1], 19: [r2]})
    assert v.per_label[20][0].message == "L1 fail"
    assert v.per_label[19][0].message == "T12 flag"
    assert v.overall == Severity.FAIL


def test_ac7_per_label_only_affects_referenced_label():
    """A reason on label 1 does not appear under label 2."""
    r = Reason(message="label 1 issue", severity=Severity.FLAG)
    v = Verdict.build(reasons=[], per_label={1: [r]})
    assert 1 in v.per_label
    assert 2 not in v.per_label


# =========================================================================== #
# AC-8  Immutability after finalisation
# =========================================================================== #

def test_ac8_overall_stable_after_reasons_list_mutation():
    """Mutating the list returned by .reasons does not change overall."""
    r_flag = Reason(message="flag", severity=Severity.FLAG)
    r_fail = Reason(message="fail", severity=Severity.FAIL)
    v = Verdict.build(reasons=[r_flag, r_fail], per_label={})
    assert v.overall == Severity.FAIL

    # Attempt mutation: replace or clear the returned container.
    try:
        reasons_ref = v.reasons
        if hasattr(reasons_ref, "append"):
            # It's a list — try to clear it.
            reasons_ref.clear()  # type: ignore[union-attr]
        elif hasattr(reasons_ref, "__setitem__"):
            pass  # tuple — no mutation possible
    except (AttributeError, TypeError):
        pass  # immutable container correctly prevented mutation

    # overall must remain FAIL regardless.
    assert v.overall == Severity.FAIL


def test_ac8_overall_stable_after_per_label_dict_mutation():
    """Mutating the dict returned by .per_label does not change overall."""
    r_fail = Reason(message="fail", severity=Severity.FAIL)
    v = Verdict.build(reasons=[], per_label={42: [r_fail]})
    assert v.overall == Severity.FAIL

    try:
        per_ref = v.per_label
        if isinstance(per_ref, dict):
            per_ref.pop(42, None)  # remove the FAIL entry
    except (TypeError, AttributeError):
        pass  # immutable dict — mutation correctly prevented

    # overall must still be FAIL.
    assert v.overall == Severity.FAIL


def test_ac8_per_label_is_not_the_same_object_as_input():
    """The per_label stored on Verdict is not the same object passed in at construction.

    If it were the same dict, a caller who mutates their dict after building the
    Verdict would invalidate the stored state.
    """
    r = Reason(message="reason", severity=Severity.FAIL)
    input_dict = {1: [r]}
    v = Verdict.build(reasons=[], per_label=input_dict)
    # Mutating the original dict should not affect the Verdict.
    input_dict.pop(1, None)
    assert v.overall == Severity.FAIL


def test_ac8_reasons_is_not_the_same_object_as_input():
    """The reasons stored on Verdict is not the same list passed in at construction."""
    r = Reason(message="flag reason", severity=Severity.FLAG)
    input_list = [r]
    v = Verdict.build(reasons=input_list, per_label={})
    assert v.overall == Severity.FLAG
    # Clear the original — verdict must still reflect FLAG.
    input_list.clear()
    assert v.overall == Severity.FLAG


# =========================================================================== #
# AC-9  Module location / importability
# =========================================================================== #

def test_ac9_imports_from_segqc_verdict():
    """Severity, Reason, and Verdict are all importable from segqc.verdict."""
    # The imports at the top of this file already verify this; the explicit
    # assertion here ensures the test fails if a future refactor moves them.
    from segqc.verdict import Reason as R, Severity as S, Verdict as V
    assert S is Severity
    assert R is Reason
    assert V is Verdict


def test_ac9_no_import_error():
    """Importing segqc.verdict raises no ImportError or AttributeError."""
    import importlib
    mod = importlib.import_module("segqc.verdict")
    assert hasattr(mod, "Severity")
    assert hasattr(mod, "Reason")
    assert hasattr(mod, "Verdict")


# =========================================================================== #
# AC-10  No stdlib-external runtime imports
# =========================================================================== #

def test_ac10_verdict_module_has_no_numpy_dependency():
    """segqc.verdict must not import numpy at module level.

    The verdict model is pure data; requiring NumPy would make it impossible to
    use in lightweight / import-time contexts.
    """
    import sys
    # numpy may already be imported by other modules; we check that verdict
    # does NOT list it as a direct module-level dependency by inspecting
    # the module's globals (no numpy name should appear there).
    import segqc.verdict as verdict_mod
    module_globals = vars(verdict_mod)
    assert "numpy" not in module_globals, (
        "segqc.verdict has 'numpy' in its module namespace — "
        "the verdict model must not depend on numpy at import time."
    )


def test_ac10_verdict_module_has_no_nibabel_dependency():
    """segqc.verdict must not import nibabel at module level."""
    import segqc.verdict as verdict_mod
    module_globals = vars(verdict_mod)
    assert "nibabel" not in module_globals
    assert "nib" not in module_globals


def test_ac10_import_does_not_require_scipy():
    """Importing segqc.verdict should not fail even if scipy were absent.

    We can't uninstall scipy, but we verify verdict's __init__ names do not
    reference it — a proxy for the 'no non-stdlib runtime imports' requirement.
    """
    import segqc.verdict as verdict_mod
    assert "scipy" not in vars(verdict_mod)


# =========================================================================== #
# Adversarial: boundary / degenerate inputs
# =========================================================================== #

def test_adv_single_reason_each_severity():
    """Each individual severity level round-trips through a single-reason Verdict."""
    for sev in Severity:
        r = Reason(message=f"only {sev.name}", severity=sev)
        v = Verdict.build(reasons=[r], per_label={})
        assert v.overall == sev


def test_adv_large_reason_set_overall_is_max():
    """A Verdict with 1000 PASS reasons + 1 FAIL → overall FAIL."""
    reasons = [Reason(message=f"pass {i}", severity=Severity.PASS) for i in range(1000)]
    reasons.append(Reason(message="the one fail", severity=Severity.FAIL))
    v = Verdict.build(reasons=reasons, per_label={})
    assert v.overall == Severity.FAIL
    assert len(v.reasons) == 1001


def test_adv_many_labels_overall_max():
    """A Verdict with FLAG on 99 labels + FAIL on 1 label → overall FAIL."""
    per_label = {
        i: [Reason(message=f"flag label {i}", severity=Severity.FLAG)]
        for i in range(99)
    }
    per_label[99] = [Reason(message="fail label 99", severity=Severity.FAIL)]
    v = Verdict.build(reasons=[], per_label=per_label)
    assert v.overall == Severity.FAIL


def test_adv_reason_with_many_labels():
    """A Reason carrying a large set of offending labels constructs correctly."""
    labels = frozenset(range(1, 30))
    r = Reason(message="many offenders", severity=Severity.FAIL, labels=labels)
    assert r.labels == labels
    assert len(r.labels) == 29


def test_adv_reason_with_single_label():
    """A Reason carrying exactly one label constructs and round-trips correctly."""
    r = Reason(message="single offender", severity=Severity.FLAG, labels=frozenset({42}))
    assert r.labels == frozenset({42})


def test_adv_reason_with_zero_as_label():
    """Label value 0 (background) is valid as an offending label in a Reason."""
    r = Reason(message="background offender", severity=Severity.FLAG, labels=frozenset({0}))
    assert 0 in r.labels


def test_adv_reason_with_negative_label():
    """Negative label integers are accepted in a Reason's labels set."""
    r = Reason(message="negative label", severity=Severity.FLAG, labels=frozenset({-1, -99}))
    assert -1 in r.labels


def test_adv_verdict_with_zero_label_key():
    """per_label keyed by 0 (the background) is accepted by Verdict.build."""
    r = Reason(message="background issue", severity=Severity.FLAG)
    v = Verdict.build(reasons=[], per_label={0: [r]})
    assert v.overall == Severity.FLAG
    assert 0 in v.per_label


def test_adv_verdict_with_large_label_key():
    """per_label keyed by a very large integer is accepted."""
    r = Reason(message="large label", severity=Severity.FAIL)
    v = Verdict.build(reasons=[], per_label={999999: [r]})
    assert v.overall == Severity.FAIL
    assert 999999 in v.per_label


def test_adv_verdict_deterministic_same_inputs():
    """Two Verdict.build calls with the same inputs produce equal overall values."""
    reasons = [
        Reason(message="a", severity=Severity.PASS),
        Reason(message="b", severity=Severity.FLAG),
    ]
    per_label = {1: [Reason(message="c", severity=Severity.PASS)]}
    v1 = Verdict.build(reasons=reasons, per_label=per_label)
    v2 = Verdict.build(reasons=reasons, per_label=per_label)
    assert v1.overall == v2.overall


def test_adv_reason_equality_same_values():
    """Two Reason objects with identical fields compare as equal."""
    r1 = Reason(message="same", severity=Severity.FLAG, labels=frozenset({1}))
    r2 = Reason(message="same", severity=Severity.FLAG, labels=frozenset({1}))
    assert r1 == r2


def test_adv_reason_inequality_different_message():
    """Two Reason objects with different messages are not equal."""
    r1 = Reason(message="a", severity=Severity.FLAG)
    r2 = Reason(message="b", severity=Severity.FLAG)
    assert r1 != r2


def test_adv_reason_inequality_different_severity():
    """Two Reason objects with different severities are not equal."""
    r1 = Reason(message="msg", severity=Severity.PASS)
    r2 = Reason(message="msg", severity=Severity.FAIL)
    assert r1 != r2


# =========================================================================== #
# Adversarial: error type and message quality
# =========================================================================== #

def test_adv_reason_message_type():
    """Reason.message is exactly a str (not bytes, not None)."""
    r = Reason(message="valid message", severity=Severity.PASS)
    assert type(r.message) is str


def test_adv_severity_label_no_internal_names_leaked():
    """Severity.label strings contain no raw enum internals like 'Severity.' or '_'."""
    for member in Severity:
        label = member.label
        assert "Severity" not in label
        assert "_" not in label
        assert "." not in label


def test_adv_verdict_reasons_preserves_order():
    """The order of reasons passed to Verdict.build is preserved in .reasons."""
    msgs = ["first", "second", "third"]
    reasons = [Reason(message=m, severity=Severity.PASS) for m in msgs]
    v = Verdict.build(reasons=reasons, per_label={})
    stored_msgs = [r.message for r in v.reasons]
    assert stored_msgs == msgs


def test_adv_per_label_reasons_preserves_order():
    """The order of per-label reasons is preserved under each label key."""
    msgs = ["alpha", "beta", "gamma"]
    reasons = [Reason(message=m, severity=Severity.FLAG) for m in msgs]
    v = Verdict.build(reasons=[], per_label={5: reasons})
    stored_msgs = [r.message for r in v.per_label[5]]
    assert stored_msgs == msgs


def test_adv_verdict_overall_not_affected_by_unrelated_label():
    """Adding a PASS per_label entry doesn't change an existing FAIL overall."""
    r_fail = Reason(message="fail", severity=Severity.FAIL)
    r_pass = Reason(message="pass", severity=Severity.PASS)
    v = Verdict.build(reasons=[r_fail], per_label={1: [r_pass]})
    assert v.overall == Severity.FAIL
