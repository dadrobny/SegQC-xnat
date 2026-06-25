"""Tests for the human-readable report renderer (item 010).

Covers all renderer-side Acceptance Criteria (AC-1 through AC-8 and AC-17) plus
adversarial and edge-case inputs: empty verdict, single-reason verdict, all three
severity levels, per-label attribution, missing case_id, large reason sets,
special characters in messages, determinism, immutability, and import purity.

All tests are deterministic, CPU-only, and portable (no I/O, no network, no
absolute paths).
"""

from __future__ import annotations

import pytest

from segqc.config import HeuristicConfig
from segqc.human_report import render_human_report
from segqc.verdict import Reason, Severity, Verdict


# =========================================================================== #
# Shared helpers
# =========================================================================== #

def _config() -> HeuristicConfig:
    return HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
    )


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _pass_verdict() -> Verdict:
    r = Reason(message="all checks passed", severity=Severity.PASS)
    return Verdict.build(reasons=[r], per_label={})


def _flag_verdict() -> Verdict:
    r = Reason(message="near-empty segmentation detected", severity=Severity.FLAG)
    return Verdict.build(reasons=[r], per_label={})


def _fail_verdict() -> Verdict:
    r = Reason(message="Segmentation is completely empty (0 foreground voxels)", severity=Severity.FAIL)
    return Verdict.build(reasons=[r], per_label={})


def _fail_verdict_with_per_label() -> Verdict:
    r_case = Reason(message="too few distinct labels", severity=Severity.FLAG)
    r_label = Reason(
        message="label 42 has zero voxels",
        severity=Severity.FAIL,
        labels=frozenset({42}),
    )
    return Verdict.build(reasons=[r_case], per_label={42: [r_label]})


# =========================================================================== #
# AC-1  render_human_report importable
# =========================================================================== #

def test_ac1_render_human_report_importable():
    """render_human_report is importable from segqc.human_report with no errors."""
    from segqc.human_report import render_human_report as rhr
    assert callable(rhr)


def test_ac1_no_import_error():
    """Importing segqc.human_report raises no ImportError or AttributeError."""
    import importlib
    mod = importlib.import_module("segqc.human_report")
    assert hasattr(mod, "render_human_report")


# =========================================================================== #
# AC-2  Returns a non-empty string
# =========================================================================== #

def test_ac2_empty_verdict_returns_nonempty_string():
    """render_human_report with an empty verdict returns a non-empty str."""
    result = render_human_report(_empty_verdict(), "case-001", _config())
    assert isinstance(result, str)
    assert len(result) > 0


def test_ac2_fail_verdict_returns_nonempty_string():
    """render_human_report with a fail verdict returns a non-empty str."""
    result = render_human_report(_fail_verdict(), "case-002", _config())
    assert isinstance(result, str)
    assert len(result) > 0


def test_ac2_result_is_str_not_bytes():
    """render_human_report returns exactly a str, not bytes or bytearray."""
    result = render_human_report(_empty_verdict(), "c", _config())
    assert type(result) is str


# =========================================================================== #
# AC-3  Contains the verdict string
# =========================================================================== #

def test_ac3_pass_verdict_string_in_output():
    """Output for a pass verdict contains the string 'pass'."""
    result = render_human_report(_empty_verdict(), "c", _config())
    assert "pass" in result.lower()


def test_ac3_flag_verdict_string_in_output():
    """Output for a flag verdict contains 'flagged-for-review'."""
    result = render_human_report(_flag_verdict(), "c", _config())
    assert "flagged-for-review" in result


def test_ac3_fail_verdict_string_in_output():
    """Output for a fail verdict contains the string 'fail'."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "fail" in result.lower()


@pytest.mark.parametrize("verdict_fn, expected_label", [
    (_empty_verdict, "pass"),
    (_flag_verdict, "flagged-for-review"),
    (_fail_verdict, "fail"),
])
def test_ac3_all_verdict_labels_present(verdict_fn, expected_label):
    """Each verdict level produces output containing the corresponding label string."""
    result = render_human_report(verdict_fn(), "c", _config())
    assert expected_label in result


# =========================================================================== #
# AC-4  Contains all case-level reason messages
# =========================================================================== #

def test_ac4_single_reason_message_in_output():
    """A single case-level reason message appears in the rendered output."""
    r = Reason(message="near-empty segmentation detected", severity=Severity.FAIL)
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    assert "near-empty segmentation detected" in result


def test_ac4_multiple_reason_messages_all_in_output():
    """All three case-level reason messages appear in the rendered output."""
    msgs = ["first problem", "second problem", "third problem"]
    reasons = [Reason(message=m, severity=Severity.FLAG) for m in msgs]
    verdict = Verdict.build(reasons=reasons, per_label={})
    result = render_human_report(verdict, "c", _config())
    for msg in msgs:
        assert msg in result, f"Expected reason message {msg!r} in output"


def test_ac4_empty_reasons_list_no_crash():
    """A verdict with no case-level reasons renders without error."""
    r_label = Reason(message="label issue", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[], per_label={1: [r_label]})
    result = render_human_report(verdict, "c", _config())
    assert isinstance(result, str)
    assert len(result) > 0


# =========================================================================== #
# AC-5  Contains per-label reason messages
# =========================================================================== #

def test_ac5_per_label_reason_message_in_output():
    """A per-label reason message appears in the rendered output."""
    r = Reason(message="label 42 has zero voxels", severity=Severity.FAIL, labels=frozenset({42}))
    verdict = Verdict.build(reasons=[], per_label={42: [r]})
    result = render_human_report(verdict, "c", _config())
    assert "label 42 has zero voxels" in result


def test_ac5_multiple_per_label_messages_all_in_output():
    """All per-label reason messages across multiple labels appear in the output."""
    r1 = Reason(message="L1 issue found", severity=Severity.FLAG, labels=frozenset({20}))
    r2 = Reason(message="T12 completely absent", severity=Severity.FAIL, labels=frozenset({19}))
    verdict = Verdict.build(reasons=[], per_label={20: [r1], 19: [r2]})
    result = render_human_report(verdict, "c", _config())
    assert "L1 issue found" in result
    assert "T12 completely absent" in result


def test_ac5_per_label_and_case_level_both_in_output():
    """Both case-level and per-label reason messages appear together."""
    verdict = _fail_verdict_with_per_label()
    result = render_human_report(verdict, "c", _config())
    assert "too few distinct labels" in result
    assert "label 42 has zero voxels" in result


# =========================================================================== #
# AC-6  Contains case_id
# =========================================================================== #

def test_ac6_case_id_in_output():
    """The case_id argument appears somewhere in the rendered string."""
    result = render_human_report(_empty_verdict(), "my-scan-001", _config())
    assert "my-scan-001" in result


def test_ac6_different_case_ids_appear_correctly():
    """Different case_id values each appear in their respective rendered strings."""
    for case_id in ("scan-A", "patient-42", "test_case_xyz"):
        result = render_human_report(_empty_verdict(), case_id, _config())
        assert case_id in result, f"Expected case_id {case_id!r} in output"


def test_ac6_numeric_case_id_in_output():
    """A numeric string case_id appears in the rendered output."""
    result = render_human_report(_empty_verdict(), "12345", _config())
    assert "12345" in result


# =========================================================================== #
# AC-7  Determinism
# =========================================================================== #

def test_ac7_same_inputs_same_output_twice():
    """Two calls with identical inputs produce the same string."""
    verdict = _fail_verdict_with_per_label()
    cfg = _config()
    r1 = render_human_report(verdict, "case-det", cfg)
    r2 = render_human_report(verdict, "case-det", cfg)
    assert r1 == r2


def test_ac7_empty_verdict_deterministic():
    """An empty verdict renders deterministically on repeated calls."""
    verdict = _empty_verdict()
    cfg = _config()
    results = [render_human_report(verdict, "c", cfg) for _ in range(5)]
    assert len(set(results)) == 1


def test_ac7_multi_label_verdict_deterministic():
    """A multi-label verdict renders deterministically."""
    per_label = {
        i: [Reason(message=f"issue with label {i}", severity=Severity.FLAG)]
        for i in range(1, 6)
    }
    verdict = Verdict.build(reasons=[], per_label=per_label)
    cfg = _config()
    r1 = render_human_report(verdict, "c", cfg)
    r2 = render_human_report(verdict, "c", cfg)
    assert r1 == r2


# =========================================================================== #
# AC-8  No raw Python internals in output
# =========================================================================== #

def test_ac8_no_severity_class_name_in_output():
    """'Severity' class name must not appear in the rendered output."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "Severity" not in result


def test_ac8_no_reason_class_name_in_output():
    """'Reason(' repr must not appear in the rendered output."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "Reason(" not in result


def test_ac8_no_verdict_class_name_in_output():
    """'Verdict(' repr must not appear in the rendered output."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "Verdict(" not in result


def test_ac8_no_frozenset_in_output():
    """'frozenset' must not appear in the rendered output."""
    r = Reason(message="multi-label issue", severity=Severity.FAIL, labels=frozenset({1, 2}))
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    assert "frozenset" not in result


def test_ac8_no_traceback_in_output():
    """'Traceback' must not appear in the rendered output."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "Traceback" not in result


def test_ac8_no_valueerror_in_output():
    """'ValueError' must not appear in the rendered output."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "ValueError" not in result


def test_ac8_no_none_type_in_output():
    """'NoneType' must not appear in the rendered output."""
    result = render_human_report(_empty_verdict(), "c", _config())
    assert "NoneType" not in result


# =========================================================================== #
# AC-17  No stdlib-external imports at module level
# =========================================================================== #

def test_ac17_no_numpy_at_module_level():
    """segqc.human_report must not import numpy at module level."""
    import segqc.human_report as hr_mod
    assert "numpy" not in vars(hr_mod)


def test_ac17_no_nibabel_at_module_level():
    """segqc.human_report must not import nibabel at module level."""
    import segqc.human_report as hr_mod
    assert "nibabel" not in vars(hr_mod)
    assert "nib" not in vars(hr_mod)


def test_ac17_no_scipy_at_module_level():
    """segqc.human_report must not import scipy at module level."""
    import segqc.human_report as hr_mod
    assert "scipy" not in vars(hr_mod)


# =========================================================================== #
# Adversarial: edge cases on verdict content
# =========================================================================== #

def test_adv_completely_empty_verdict_renders():
    """A verdict with zero reasons and zero per_label entries renders without crash."""
    result = render_human_report(_empty_verdict(), "empty-case", _config())
    assert isinstance(result, str)
    assert len(result) > 0
    assert "pass" in result.lower()


def test_adv_single_fail_reason_only():
    """A verdict with only one FAIL reason renders correctly."""
    r = Reason(message="nothing found at all", severity=Severity.FAIL)
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    assert "nothing found at all" in result
    assert "fail" in result.lower()


def test_adv_large_reason_set_all_messages_present():
    """A verdict with 20 reasons has all message strings present in the output."""
    msgs = [f"reason number {i}" for i in range(20)]
    reasons = [Reason(message=m, severity=Severity.FLAG) for m in msgs]
    verdict = Verdict.build(reasons=reasons, per_label={})
    result = render_human_report(verdict, "c", _config())
    for msg in msgs:
        assert msg in result


def test_adv_many_per_label_entries_all_present():
    """A verdict with 10 per-label entries has all messages in the output."""
    per_label = {
        i: [Reason(message=f"issue at label {i}", severity=Severity.FLAG)]
        for i in range(1, 11)
    }
    verdict = Verdict.build(reasons=[], per_label=per_label)
    result = render_human_report(verdict, "c", _config())
    for i in range(1, 11):
        assert f"issue at label {i}" in result


def test_adv_special_characters_in_message_preserved():
    """Reason messages with special characters are preserved in the output."""
    msg = "voxel count < threshold: 3 < 100 (delta=97)"
    r = Reason(message=msg, severity=Severity.FAIL)
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    assert msg in result


def test_adv_unicode_case_id_in_output():
    """A unicode case_id string appears in the rendered output."""
    case_id = "scan-éàü-001"
    result = render_human_report(_empty_verdict(), case_id, _config())
    assert case_id in result


def test_adv_render_does_not_mutate_verdict():
    """render_human_report does not modify the Verdict object passed to it."""
    r = Reason(message="test reason", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    overall_before = verdict.overall
    reasons_count_before = len(verdict.reasons)
    render_human_report(verdict, "c", _config())
    assert verdict.overall == overall_before
    assert len(verdict.reasons) == reasons_count_before


def test_adv_repeated_calls_do_not_accumulate_state():
    """Calling render_human_report multiple times does not grow the output."""
    verdict = _flag_verdict()
    cfg = _config()
    r1 = render_human_report(verdict, "c", cfg)
    r2 = render_human_report(verdict, "c", cfg)
    r3 = render_human_report(verdict, "c", cfg)
    assert r1 == r2 == r3


def test_adv_single_label_map_renders():
    """A verdict with a single per-label entry renders without error."""
    r = Reason(message="only one label flagged", severity=Severity.FLAG, labels=frozenset({1}))
    verdict = Verdict.build(reasons=[], per_label={1: [r]})
    result = render_human_report(verdict, "single-label", _config())
    assert "only one label flagged" in result
    assert "single-label" in result


def test_adv_no_labels_at_all_renders():
    """A completely empty verdict (no foreground labels) renders sensibly."""
    verdict = Verdict.build(reasons=[], per_label={})
    result = render_human_report(verdict, "no-labels", _config())
    assert "no-labels" in result
    assert isinstance(result, str)
    assert len(result) > 0


def test_adv_reason_with_empty_labels_frozenset_renders():
    """A Reason with no specific label attribution renders without showing frozenset."""
    r = Reason(message="case-level flag", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    assert "frozenset" not in result
    assert "case-level flag" in result


def test_adv_all_three_severity_levels_render_correctly():
    """Rendering verdicts with each severity level returns the correct label."""
    for sev, expected in [
        (Severity.PASS, "pass"),
        (Severity.FLAG, "flagged-for-review"),
        (Severity.FAIL, "fail"),
    ]:
        r = Reason(message=f"test {sev.name}", severity=sev)
        verdict = Verdict.build(reasons=[r], per_label={})
        result = render_human_report(verdict, "c", _config())
        assert expected in result, f"Expected {expected!r} in output for {sev.name}"


def test_adv_human_report_is_readable_length():
    """The rendered report is not excessively long for a simple verdict."""
    r = Reason(message="one simple reason", severity=Severity.FAIL)
    verdict = Verdict.build(reasons=[r], per_label={})
    result = render_human_report(verdict, "c", _config())
    # Reasonable upper bound: no report should be > 10 KB for a trivial verdict
    assert len(result) < 10_000


def test_adv_report_contains_newlines():
    """The rendered report contains at least one newline (is multi-line)."""
    result = render_human_report(_fail_verdict(), "c", _config())
    assert "\n" in result
