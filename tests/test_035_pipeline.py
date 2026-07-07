"""Tests for the feature-extraction + QC orchestration pipeline (item 035, AC6-AC9).

Covers:
- AC6: extract_feature_record builds a schema-valid feature block.
- AC7: extract_feature_record is robust to degenerate label maps (empty,
  single-label).
- AC8: run_qc runs rules + aggregates over the extracted record.
- AC9: run_qc threads the Stage 1 base reasons through.

Adversarial / edge-case scenarios included:
- run_qc is deterministic across repeated calls on the same seg_img/config.
- run_qc does not mutate the config or leak state between calls.
- A single-label map still produces a valid, renderable features block.
"""

from __future__ import annotations

import copy

import pytest

from segqc.aggregate import aggregate_verdict, build_case_result
from segqc.config import default_config
from segqc.heuristics import run_rules
from segqc.pipeline import extract_feature_record, run_qc
from segqc.report import serialize_report
from segqc.verdict import Reason, Severity, Verdict

from synthetic import empty_case, labelled_blocks_case, make_labelmap


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _config():
    return default_config()


# =========================================================================== #
# AC6: extract_feature_record builds a schema-valid feature block
# =========================================================================== #


def test_ac6_multi_label_case_has_expected_top_level_keys():
    """AC6: a multi-label case yields a dict with the five expected keys."""
    case = labelled_blocks_case()
    block = extract_feature_record(case.seg_img, _config())
    assert set(block.keys()) >= {
        "features_version",
        "per_label",
        "relationships",
        "overlaps",
        "stage3",
    }


def test_ac6_multi_label_case_per_label_populated():
    """AC6: per_label has one entry per expected label."""
    case = labelled_blocks_case()
    block = extract_feature_record(case.seg_img, _config())
    assert set(block["per_label"].keys()) == {str(lab) for lab in case.expected_labels}


def test_ac6_multi_label_case_embeds_and_validates_in_report():
    """AC6: embedding the block via serialize_report(..., features=block)
    validates against the schema without raising."""
    case = labelled_blocks_case()
    block = extract_feature_record(case.seg_img, _config())
    report = serialize_report(_empty_verdict(), "case-035", _config(), features=block)
    assert report["features"]["features_version"] == block["features_version"]


def test_ac6_multi_label_case_has_stage3_subblock():
    """AC6: with >=2 labels, a non-None stage3 sub-block is present."""
    case = labelled_blocks_case()
    block = extract_feature_record(case.seg_img, _config())
    assert "stage3" in block
    assert block["stage3"] is not None


# =========================================================================== #
# AC7: extract_feature_record is robust to degenerate label maps
# =========================================================================== #


def test_ac7_zero_label_map_empty_per_label():
    """AC7: a zero-label map yields an empty per_label dict without raising."""
    case = empty_case()
    block = extract_feature_record(case.seg_img, _config())
    assert block["per_label"] == {}


def test_ac7_zero_label_map_empty_overlaps():
    """AC7: a zero-label map yields overlaps == []."""
    case = empty_case()
    block = extract_feature_record(case.seg_img, _config())
    assert block["overlaps"] == []


def test_ac7_zero_label_map_relationships_none():
    """AC7: a zero-label map yields relationships == None."""
    case = empty_case()
    block = extract_feature_record(case.seg_img, _config())
    assert block["relationships"] is None


def test_ac7_zero_label_map_no_stage3_key():
    """AC7: a zero-label map's block carries no 'stage3' key at all."""
    case = empty_case()
    block = extract_feature_record(case.seg_img, _config())
    assert "stage3" not in block


def test_ac7_single_label_map_has_geometry_components_centroid():
    """AC7: a single-label map's sole per_label entry has geometry, components,
    and centroid sub-blocks, without raising."""
    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    block = extract_feature_record(seg, _config())
    assert len(block["per_label"]) == 1
    entry = next(iter(block["per_label"].values()))
    assert "geometry" in entry
    assert "components" in entry
    assert "centroid" in entry


def test_ac7_single_label_map_no_stage3_key():
    """AC7: a single-label map's block carries no 'stage3' key (spline fit
    needs >= 2 centroids)."""
    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    block = extract_feature_record(seg, _config())
    assert "stage3" not in block


def test_ac7_single_label_map_validates_in_report():
    """AC7: the single-label block still embeds and validates in a report."""
    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    block = extract_feature_record(seg, _config())
    report = serialize_report(_empty_verdict(), "single", _config(), features=block)
    # Reaching here without a jsonschema.ValidationError is the assertion;
    # additionally confirm the features block round-tripped intact.
    assert report["features"]["per_label"] == block["per_label"]


def test_ac7_zero_label_map_does_not_raise():
    """AC7: extracting features from an all-zero label map never raises."""
    case = empty_case()
    # Should not raise -- explicit call outside any try/except to fail loudly
    # in pytest if it does.
    extract_feature_record(case.seg_img, _config())


# =========================================================================== #
# AC8: run_qc runs rules + aggregates over the extracted record
# =========================================================================== #


def test_ac8_run_qc_returns_case_result_and_block_tuple():
    """AC8: run_qc returns a (CaseResult, features_block) pair."""
    from segqc.aggregate import CaseResult

    case = labelled_blocks_case()
    case_result, block = run_qc(case.seg_img, _config())
    assert isinstance(case_result, CaseResult)
    assert isinstance(block, dict)


def test_ac8_run_qc_findings_equal_run_rules_over_extracted_block():
    """AC8: CaseResult.findings == tuple(run_rules(features_block, config))."""
    case = labelled_blocks_case()
    cfg = _config()
    case_result, block = run_qc(case.seg_img, cfg)
    assert case_result.findings == tuple(run_rules(block, cfg))


def test_ac8_run_qc_verdict_equals_aggregate_verdict_composition():
    """AC8: CaseResult.verdict == aggregate_verdict(findings, config)."""
    case = labelled_blocks_case()
    cfg = _config()
    case_result, block = run_qc(case.seg_img, cfg)
    expected_findings = run_rules(block, cfg)
    expected_verdict = aggregate_verdict(expected_findings, cfg)
    assert case_result.verdict == expected_verdict


def test_ac8_run_qc_threads_base_per_label_through_aggregation():
    """AC8: run_qc's verdict composition matches the full aggregate_verdict
    signature, including base_reasons and base_per_label."""
    case = labelled_blocks_case()
    cfg = _config()
    base_reasons = [Reason(message="stage 1 note", severity=Severity.PASS)]
    base_per_label = {1: [Reason(message="l1 note", severity=Severity.PASS, labels=frozenset({1}))]}
    case_result, block = run_qc(
        case.seg_img, cfg, base_reasons=base_reasons, base_per_label=base_per_label
    )
    expected_findings = run_rules(block, cfg)
    expected_verdict = aggregate_verdict(
        expected_findings, cfg, base_reasons=base_reasons, base_per_label=base_per_label
    )
    assert case_result.verdict == expected_verdict


# =========================================================================== #
# AC9: run_qc threads the Stage 1 base reasons through
# =========================================================================== #


def test_ac9_base_fail_reason_yields_fail_overall():
    """AC9: a FAIL base_reason on a record producing no findings yields overall
    == Severity.FAIL."""
    case = empty_case()  # zero labels -> no findings possible
    cfg = _config()
    base_reasons = [Reason(message="empty segmentation", severity=Severity.FAIL)]
    case_result, block = run_qc(case.seg_img, cfg, base_reasons=base_reasons)
    assert case_result.verdict.overall == Severity.FAIL


def test_ac9_base_fail_reason_message_present_in_verdict_reasons():
    """AC9: the base FAIL reason's message is present in the returned verdict's
    reasons."""
    case = empty_case()
    cfg = _config()
    base_reasons = [Reason(message="empty segmentation", severity=Severity.FAIL)]
    case_result, block = run_qc(case.seg_img, cfg, base_reasons=base_reasons)
    messages = [r.message for r in case_result.verdict.reasons]
    assert "empty segmentation" in messages


def test_ac9_no_findings_on_empty_case_record():
    """AC9: the empty case's extracted record produces no rule findings at all
    (isolating that the FAIL comes from the base reason, not the rules)."""
    case = empty_case()
    cfg = _config()
    case_result, block = run_qc(case.seg_img, cfg, base_reasons=[])
    assert case_result.findings == ()


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_run_qc_deterministic_across_repeated_calls():
    """Adversarial: two run_qc calls on the same seg_img/config return equal
    findings tuples and equal verdicts."""
    case = labelled_blocks_case()
    cfg = _config()
    result1, block1 = run_qc(case.seg_img, cfg)
    result2, block2 = run_qc(case.seg_img, cfg)
    assert result1.findings == result2.findings
    assert result1.verdict == result2.verdict
    assert block1 == block2


def test_adv_run_qc_does_not_mutate_config():
    """Adversarial: run_qc does not mutate the passed HeuristicConfig."""
    case = labelled_blocks_case()
    cfg = _config()
    cfg_before = copy.deepcopy(cfg)
    run_qc(case.seg_img, cfg)
    assert cfg == cfg_before


def test_adv_run_qc_does_not_mutate_base_reasons_list():
    """Adversarial: run_qc does not mutate the caller's base_reasons list."""
    case = empty_case()
    cfg = _config()
    base_reasons = [Reason(message="empty segmentation", severity=Severity.FAIL)]
    base_before = copy.deepcopy(base_reasons)
    run_qc(case.seg_img, cfg, base_reasons=base_reasons)
    assert base_reasons == base_before


def test_adv_extract_feature_record_deterministic():
    """Adversarial: two extract_feature_record calls on the same inputs yield
    equal blocks."""
    case = labelled_blocks_case()
    cfg = _config()
    block1 = extract_feature_record(case.seg_img, cfg)
    block2 = extract_feature_record(case.seg_img, cfg)
    assert block1 == block2


def test_adv_run_qc_on_single_label_case_no_crash():
    """Adversarial: run_qc on a single-label map does not crash and returns a
    valid (CaseResult, block) pair with no stage3 sub-block."""
    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    cfg = _config()
    case_result, block = run_qc(seg, cfg)
    assert "stage3" not in block
    assert isinstance(case_result.findings, tuple)
