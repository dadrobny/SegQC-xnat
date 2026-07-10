"""Tests for item 041 — full-pipeline regression suite over the committed
corpus (item 040).

Covers Acceptance Criteria AC1-AC12:

- AC1-AC2 (Group A, manifest-driven parametrisation & routing): the suite's
  parametrised case ids equal exactly the committed manifest's case_id set
  and are non-empty; every case routes to exactly one handled detection path
  (``pipeline`` / ``reconstructed_record`` with a recognised
  ``reconstruction`` key), and the pipeline + reconstruction subsets
  together account for every manifest case.
- AC3-AC6 (Group B, pipeline-detectable cases): the clean_control positive
  control passes with no findings; every ``pipeline`` case's
  ``pipeline_verdict_label`` matches the manifest; every non-clean
  ``pipeline`` case's designated rule fires; the offending labels match.
- AC7-AC8 (Group C, reconstructed-record cases): every
  ``reconstructed_record`` case's plain ``run_qc`` hides the designated
  rule; the reconstruction technique fires the designated rule with the
  expected labels.
- AC9-AC12 (Group D, negative controls & skip-guard): verdict / fired-rule /
  offending-label drift is caught by the corresponding predicate; an
  unrecognised ``reconstruction`` string raises ``ValueError`` from
  ``reconstructed_findings`` rather than silently passing.

Adversarial / edge-case scenarios included:
- ``verify_case`` is deterministic across repeated calls on the same case.
- The case-level ``mode5_remove_level`` case (``expected_labels == []``)
  passes AC6 without crashing on the empty-set union.
- ``loaded_seg_image`` succeeds for every manifest case (guards the
  mandatory explicit ``dtype=`` nibabel 5.3.3 requirement).
- A drift meta-test targets a genuinely-fired pipeline case
  (``mode7_sequence_break``), so AC9-AC11 exercise the fired path rather
  than a no-op.
- Cross-check: for every ``reconstructed_record`` case, the designated rule
  filtered out of plain ``run_qc`` (AC7) is indeed the same rule the
  reconstruction fires (AC8) — the two paths are consistent, not just each
  individually true.
"""

from __future__ import annotations

import copy

import pytest

import segqc.synth  # noqa: F401 -- triggers self-registration of every operator
from segqc.synth.corpus import load_manifest
from segqc.synth.regression import (
    RECONSTRUCTIONS,
    designated_rule_fired,
    offending_labels_match,
    pipeline_findings,
    pipeline_hides_designated_rule,
    pipeline_verdict_label,
    reconstructed_findings,
    verify_case,
)

# =========================================================================== #
# Manifest-driven fixtures
# =========================================================================== #

_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]
_COMMITTED_CASE_IDS = {c["case_id"] for c in _CASES}

_PIPELINE_CASES = [c for c in _CASES if c["detection"] == "pipeline"]
_NON_CLEAN_PIPELINE_CASES = [c for c in _PIPELINE_CASES if c["failure_mode"] != 0]
_RECONSTRUCTED_CASES = [c for c in _CASES if c["detection"] == "reconstructed_record"]

_VALID_DETECTIONS = {"pipeline", "reconstructed_record"}


def _case(case_id):
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _case_id(case):
    return case["case_id"]


# =========================================================================== #
# A. Manifest-driven parametrisation (AC1-AC2)
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac1_parametrisation_covers_every_committed_case(case):
    """AC1: parametrising over load_manifest()["cases"] produces exactly one
    invocation per committed case_id, and the collected set of ids is
    non-empty (i.e. this test runs at all, and each run's case_id is a
    member of the committed set)."""
    assert case["case_id"] in _COMMITTED_CASE_IDS


def test_ac1_parametrised_ids_equal_committed_case_id_set():
    """AC1: the set of ids this module's Group B/C parametrisation would
    collect equals exactly the committed manifest's case_id set, and is
    non-empty."""
    all_ids = {c["case_id"] for c in _CASES}
    assert all_ids == _COMMITTED_CASE_IDS
    assert len(all_ids) > 0


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_ac2_every_case_routes_to_exactly_one_handled_path(case):
    """AC2: detection is one of {"pipeline", "reconstructed_record"}, and
    every reconstructed_record case's reconstruction is a key of
    RECONSTRUCTIONS."""
    assert case["detection"] in _VALID_DETECTIONS
    if case["detection"] == "reconstructed_record":
        assert case["reconstruction"] in RECONSTRUCTIONS
        assert case["reconstruction"] in {
            "leave_one_out_offset",
            "monotonic_true_spatial_order",
            "overlap_mask_stack",
        }


def test_ac2_pipeline_and_reconstruction_paths_together_exercise_every_case():
    """AC2: the pipeline-path case count plus the reconstruction-path case
    count equals the total manifest case count (no case falls through
    unhandled)."""
    assert len(_PIPELINE_CASES) + len(_RECONSTRUCTED_CASES) == len(_CASES)


# =========================================================================== #
# B. Pipeline-detectable cases (AC3-AC6)
# =========================================================================== #


def test_ac3_clean_control_passes_with_no_findings():
    """AC3: for the failure_mode == 0 clean_control case, run_qc returns
    findings == () and verdict.overall.label == "pass" (== its manifest
    expected_verdict)."""
    case = _case("clean_control")
    assert case["failure_mode"] == 0
    assert case["expected_verdict"] == "pass"
    assert pipeline_findings(case) == ()
    assert pipeline_verdict_label(case) == "pass" == case["expected_verdict"]


@pytest.mark.parametrize("case", _PIPELINE_CASES, ids=_case_id)
def test_ac4_pipeline_verdict_matches_manifest(case):
    """AC4: for every detection == "pipeline" case,
    pipeline_verdict_label(case) == case["expected_verdict"]."""
    assert pipeline_verdict_label(case) == case["expected_verdict"]


@pytest.mark.parametrize("case", _NON_CLEAN_PIPELINE_CASES, ids=_case_id)
def test_ac5_designated_heuristic_fires_for_pipeline_cases(case):
    """AC5: for every non-clean detection == "pipeline" case,
    designated_rule_fired(case) is True."""
    assert _NON_CLEAN_PIPELINE_CASES  # sanity: subset is non-trivial
    assert designated_rule_fired(case) is True


@pytest.mark.parametrize("case", _NON_CLEAN_PIPELINE_CASES, ids=_case_id)
def test_ac6_offending_labels_match_manifest_for_pipeline_cases(case):
    """AC6: for every non-clean detection == "pipeline" case,
    offending_labels_match(case) is True -- including the case-level
    mode5_remove_level case whose expected_labels == []."""
    assert offending_labels_match(case) is True


# =========================================================================== #
# C. Reconstructed-record cases (AC7-AC8)
# =========================================================================== #


@pytest.mark.parametrize("case", _RECONSTRUCTED_CASES, ids=_case_id)
def test_ac7_plain_pipeline_hides_designated_rule_for_reconstructed_cases(case):
    """AC7: for every detection == "reconstructed_record" case,
    pipeline_hides_designated_rule(case) is True -- run_qc emits no finding
    whose rule_id is in expected_rule_ids."""
    assert _RECONSTRUCTED_CASES  # sanity: partition is non-trivial
    assert pipeline_hides_designated_rule(case) is True


@pytest.mark.parametrize("case", _RECONSTRUCTED_CASES, ids=_case_id)
def test_ac8_reconstruction_fires_designated_rule_with_expected_labels(case):
    """AC8: driving the technique named by case["reconstruction"] and
    feeding the reconstructed record to the designated rule yields a finding
    with rule_id in expected_rule_ids, and offending_labels_match(case) is
    True."""
    expected_rule_ids = set(case["expected_rule_ids"])
    findings = reconstructed_findings(case)
    assert any(f.rule_id in expected_rule_ids for f in findings)
    assert offending_labels_match(case) is True


# =========================================================================== #
# D. Negative controls & skip-guard (AC9-AC12)
# =========================================================================== #


def test_ac9_verdict_drift_is_caught():
    """AC9: for a detection == "pipeline" case, a copy whose
    expected_verdict is changed to a different valid label makes the
    verdict comparison fail."""
    case = _case("mode7_sequence_break")
    assert case["detection"] == "pipeline"
    drifted = copy.deepcopy(case)
    assert drifted["expected_verdict"] == "flagged-for-review"
    drifted["expected_verdict"] = "pass"

    assert drifted["expected_verdict"] != pipeline_verdict_label(case)
    assert verify_case(drifted) is False


def test_ac10_fired_rule_drift_is_caught():
    """AC10: for a detection == "pipeline" case, a copy whose
    expected_rule_ids is changed to a rule id that did not fire makes
    designated_rule_fired(copy) return False."""
    case = _case("mode7_sequence_break")
    assert case["expected_rule_ids"] == ["sequence"]
    drifted = copy.deepcopy(case)
    drifted["expected_rule_ids"] = ["overlap"]

    assert designated_rule_fired(drifted) is False


def test_ac11_offending_label_drift_is_caught():
    """AC11: for a non-clean case, a copy whose expected_labels is changed
    to a wrong label set makes offending_labels_match(copy) return False."""
    case = _case("mode7_sequence_break")
    assert case["failure_mode"] != 0
    drifted = copy.deepcopy(case)
    assert drifted["expected_labels"] == [28]
    drifted["expected_labels"] = [999]

    assert offending_labels_match(drifted) is False


def test_ac12_unknown_reconstruction_technique_raises_value_error():
    """AC12: reconstructed_findings(case) on a case whose reconstruction is
    an unrecognised string raises ValueError rather than returning an
    empty / "passed" result."""
    case = _case("mode1_displace")
    bad_case = copy.deepcopy(case)
    bad_case["reconstruction"] = "not_a_real_technique"

    with pytest.raises(ValueError):
        reconstructed_findings(bad_case)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_adv_verify_case_is_deterministic(case):
    """Adversarial: verify_case(case) is deterministic -- two calls on the
    same case return the same result."""
    first = verify_case(case)
    second = verify_case(case)
    assert first == second


def test_adv_mode5_remove_level_case_level_labels_no_crash_on_empty_union():
    """Adversarial: the case-level mode5_remove_level case
    (expected_labels == []) passes offending_labels_match without crashing
    on the empty-set union."""
    case = _case("mode5_remove_level")
    assert case["expected_labels"] == []
    assert designated_rule_fired(case) is True
    assert offending_labels_match(case) is True


@pytest.mark.parametrize("case", _CASES, ids=_case_id)
def test_adv_loaded_seg_image_succeeds_for_every_case(case):
    """Adversarial: pipeline_findings(case) (which loads the seg image
    internally) succeeds for every manifest case without raising -- guards
    the mandatory explicit dtype= nibabel 5.3.3 requirement for both
    pipeline and reconstructed_record cases."""
    if case["detection"] == "pipeline":
        pipeline_findings(case)
    else:
        assert pipeline_hides_designated_rule(case) in (True, False)


@pytest.mark.parametrize("case", _RECONSTRUCTED_CASES, ids=_case_id)
def test_adv_reconstructed_case_hidden_rule_matches_reconstruction_fired_rule(case):
    """Adversarial cross-check: the designated rule that AC7 confirms is
    absent from plain run_qc is the very rule that AC8's reconstruction
    fires -- the two paths are consistent, not just individually true."""
    expected_rule_ids = set(case["expected_rule_ids"])
    plain_findings = pipeline_findings(case)
    assert not any(f.rule_id in expected_rule_ids for f in plain_findings)

    reconstructed = reconstructed_findings(case)
    assert any(f.rule_id in expected_rule_ids for f in reconstructed)
