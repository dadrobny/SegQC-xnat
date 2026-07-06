"""Tests for item 032 — overlap rule (overlap).

Covers all 15 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:  OverlapRule registers under rule_id == "overlap"; discoverable.
- AC2:  No finding for a record whose overlaps list is empty.
- AC3:  A finding fires for two deliberately intersecting labels.
- AC4:  The offending pair is attributed by both integer labels.
- AC5:  The overlap magnitude appears in the reason.
- AC6:  Both offending labels are named in the reason.
- AC7:  Multiple overlapping pairs each yield one finding, in ascending
        (label_a, label_b) order.
- AC8:  min_overlap_voxels suppresses sub-threshold pairs and is
        config-driven.
- AC9:  The default threshold flags any present overlap.
- AC10: Default severity is FLAG, and severity is config-driven.
- AC11: An unrecognised severity string raises ValueError.
- AC12: The rule is deterministic.
- AC13: The rule tolerates degenerate / malformed records.
- AC14: The rule reads only the overlaps block (spacing-agnostic).
- AC15: The rule does not mutate the input record.

Adversarial / edge-case scenarios included:
- overlaps absent / None / empty-list / non-list ({}) placeholder.
- An overlaps entry missing overlap_voxels (treated as 0, suppressed).
- An overlaps entry missing a label field (contributes no finding).
- min_overlap_voxels threshold boundary is inclusive (>=).
- Determinism across two run_rules calls, including ascending order.
- Mutation guard via deep-copy equality of the record and its entries.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segqc.heuristics.overlap  # noqa: F401 — triggers OverlapRule registration
from segqc.heuristics import Finding, Rule, get_rule, iter_rules, run_rules
from segqc.heuristics.overlap import OverlapRule
from segqc.heuristics.rule import _RULES
from segqc.verdict import Severity
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    default_config,
    load_config,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

# Default label convention (item 004): the labels used throughout this file.
_LABEL_T12 = 19
_LABEL_L1 = 20
_LABEL_L2 = 21


def _make_overlap_entry(
    label_a: int,
    label_b: int,
    overlap_voxels: int,
    name_a: str = "?",
    name_b: str = "?",
) -> dict:
    """Build a minimal overlaps entry matching overlap_to_dict's (item 016)
    shape."""
    return {
        "label_a": label_a,
        "label_b": label_b,
        "name_a": name_a,
        "name_b": name_b,
        "overlap_voxels": overlap_voxels,
    }


def _make_record(entries: list, **other_fields) -> dict:
    """Assemble a minimal build_features_block-shaped record: a top-level
    overlaps list plus any extra fields."""
    record = {"overlaps": list(entries)}
    record.update(other_fields)
    return record


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _overlap_yaml_header() -> str:
    """Return a YAML preamble placing the cursor inside overlap params."""
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  overlap:\n"
        "    params:\n"
    )


def _overlap_findings(findings):
    """Filter to only overlap-rule findings."""
    return [f for f in findings if f.rule_id == "overlap"]


_OVERLAP_TAG = "Overlapping segments:"


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'overlap') and restore after."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: OverlapRule registers under rule_id == "overlap"
# =========================================================================== #


def test_ac1_overlap_rule_is_in_registry():
    """AC1: get_rule('overlap') returns a Rule instance without raising."""
    rule = get_rule("overlap")
    assert rule.rule_id == "overlap"


def test_ac1_overlap_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'overlap'."""
    assert any(r.rule_id == "overlap" for r in iter_rules())


def test_ac1_overlap_rule_is_rule_subclass():
    """AC1: The registered OverlapRule is a subclass of segqc.heuristics.Rule."""
    assert isinstance(get_rule("overlap"), Rule)


# =========================================================================== #
# AC2: No finding for disjoint labels
# =========================================================================== #


def test_ac2_empty_overlaps_list_no_finding():
    """AC2: overlaps == [] under default_config() yields no overlap finding."""
    record = _make_record([])
    findings = _overlap_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# AC3 / AC4 / AC5 / AC6: A finding fires for intersecting labels; attribution,
# magnitude, and names in the reason
# =========================================================================== #


def test_ac3_single_pair_fires_exactly_one_finding():
    """AC3: One overlaps entry (20, 21, 37) emits exactly one Finding with
    rule_id == 'overlap'."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].rule_id == "overlap"


def test_ac4_offending_pair_attributed_by_both_labels():
    """AC4: labels == frozenset({20, 21}) — both members of the pair."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1, _LABEL_L2})


def test_ac5_overlap_magnitude_appears_in_reason():
    """AC5: The shared-voxel count ('37') appears in the finding's reason."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert "37" in findings[0].reason


def test_ac6_both_offending_labels_named_in_reason():
    """AC6: Both integer labels (20 and 21) appear in the finding's reason."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert "20" in reason
    assert "21" in reason
    assert reason.startswith(_OVERLAP_TAG)


# =========================================================================== #
# AC7: Multiple overlapping pairs each yield one finding, ascending order
# =========================================================================== #


def test_ac7_multiple_pairs_ascending_label_order():
    """AC7: Three entries fed out of order emit three findings ordered
    ascending (label_a, label_b): (19,20), (19,21), (20,21)."""
    entries = [
        _make_overlap_entry(_LABEL_T12, _LABEL_L2, 5, "T12", "L2"),  # (19, 21)
        _make_overlap_entry(_LABEL_T12, _LABEL_L1, 3, "T12", "L1"),  # (19, 20)
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 7, "L1", "L2"),  # (20, 21)
    ]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 3
    assert findings[0].labels == frozenset({_LABEL_T12, _LABEL_L1})
    assert findings[1].labels == frozenset({_LABEL_T12, _LABEL_L2})
    assert findings[2].labels == frozenset({_LABEL_L1, _LABEL_L2})


# =========================================================================== #
# AC8: min_overlap_voxels suppresses sub-threshold pairs, config-driven
# =========================================================================== #


def test_ac8_threshold_suppresses_below_and_flags_at_boundary(tmp_path):
    """AC8: With min_overlap_voxels == 5, a 4-voxel pair yields no finding
    while a 5-voxel pair yields exactly one (inclusive boundary)."""
    entries = [
        _make_overlap_entry(_LABEL_T12, _LABEL_L1, 4, "T12", "L1"),
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 5, "L1", "L2"),
    ]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      min_overlap_voxels: 5\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _overlap_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1, _LABEL_L2})


# =========================================================================== #
# AC9: Default threshold flags any present overlap
# =========================================================================== #


def test_ac9_default_threshold_flags_one_voxel_overlap():
    """AC9: With no min_overlap_voxels param, a 1-voxel entry yields exactly
    one finding."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 1, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1


# =========================================================================== #
# AC10: Default severity is FLAG, and severity is config-driven
# =========================================================================== #


def test_ac10_default_severity_is_flag():
    """AC10: With no severity param, an overlap finding has Severity.FLAG."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert findings
    assert all(f.severity is Severity.FLAG for f in findings)


def test_ac10_severity_param_fail_overrides_default(tmp_path):
    """AC10: With params.severity = 'fail', the emitted finding has
    Severity.FAIL."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _overlap_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings)


# =========================================================================== #
# AC11: An unrecognised severity string raises ValueError
# =========================================================================== #


def test_ac11_unrecognised_severity_raises_value_error(tmp_path):
    """AC11: An unrecognised severity param string raises ValueError."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      severity: xyz_not_a_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac11_value_error_raised_before_per_record_processing(tmp_path):
    """AC11: ValueError fires even for an empty overlaps record — severity is
    parsed before any per-record processing (so the raise cannot come from
    entry iteration)."""
    content = _overlap_yaml_header() + "      severity: garbage\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record([])
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac11_value_error_has_non_empty_message(tmp_path):
    """AC11: The ValueError for a bad severity has a non-empty, readable
    message."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError) as exc_info:
        run_rules(record, cfg)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC12: Deterministic
# =========================================================================== #


def test_ac12_two_runs_return_equal_lists():
    """AC12: Two successive run_rules calls return equal finding lists in the
    same order."""
    entries = [
        _make_overlap_entry(_LABEL_T12, _LABEL_L2, 5, "T12", "L2"),
        _make_overlap_entry(_LABEL_T12, _LABEL_L1, 3, "T12", "L1"),
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 7, "L1", "L2"),
    ]
    record = _make_record(entries)
    cfg = default_config()
    run1 = _overlap_findings(run_rules(record, cfg))
    run2 = _overlap_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


# =========================================================================== #
# AC13: Tolerates degenerate / malformed records
# =========================================================================== #


def test_ac13_overlaps_absent_no_raise():
    """AC13: record has no 'overlaps' key at all."""
    record = {}
    result = _overlap_findings(run_rules(record, default_config()))
    assert isinstance(result, list)
    assert result == []


def test_ac13_overlaps_none_no_raise():
    """AC13: overlaps == None is treated as no overlaps."""
    record = {"overlaps": None}
    result = _overlap_findings(run_rules(record, default_config()))
    assert result == []


def test_ac13_overlaps_empty_list_no_raise():
    """AC13: overlaps == [] yields no findings without raising."""
    record = {"overlaps": []}
    result = _overlap_findings(run_rules(record, default_config()))
    assert result == []


def test_ac13_overlaps_non_list_placeholder_no_raise():
    """AC13: overlaps == {} (a non-list placeholder used in sibling unit
    tests) is treated as no overlaps, not a list to iterate."""
    record = {"overlaps": {}}
    result = _overlap_findings(run_rules(record, default_config()))
    assert result == []


def test_ac13_entry_missing_overlap_voxels_treated_as_zero_and_suppressed():
    """AC13: An entry missing overlap_voxels is treated as 0 and suppressed
    under the default threshold, even amid other flagged pairs."""
    entries = [
        {"label_a": _LABEL_T12, "label_b": _LABEL_L1, "name_a": "T12", "name_b": "L1"},
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 5, "L1", "L2"),
    ]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1, _LABEL_L2})


def test_ac13_entry_missing_label_field_contributes_no_finding():
    """AC13: An entry missing a label field contributes no finding."""
    entries = [
        {"label_b": _LABEL_L1, "name_a": "?", "name_b": "L1", "overlap_voxels": 10},
    ]
    record = _make_record(entries)
    findings = _overlap_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac13_no_per_label_or_relationships_keys_no_raise():
    """AC13: The record carries no per_label / relationships keys at all."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    assert "per_label" not in record
    assert "relationships" not in record
    findings = _overlap_findings(run_rules(record, default_config()))
    assert len(findings) == 1


# =========================================================================== #
# AC14: The rule reads only the overlaps block (spacing-agnostic)
# =========================================================================== #


def test_ac14_spacing_agnostic_identical_findings():
    """AC14: Two records with identical overlaps but different per_label /
    relationships / stage3 / mm fields yield identical finding lists.

    Evaluated directly via OverlapRule().evaluate() (rather than run_rules)
    so the comparison isolates AC14's claim about the overlap rule alone —
    it must not be perturbed by sibling rules (e.g. item 031's BorderRule)
    that also inspect per_label but expect a different shape."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record_a = _make_record(
        entries,
        per_label={"foo": 1},
        relationships={"present_levels": ["L1", "L2"]},
        stage3={"a": 1},
        spacing_mm=[1.0, 1.0, 1.0],
    )
    record_b = _make_record(
        entries,
        per_label={"bar": 999},
        relationships={"present_levels": []},
        stage3=None,
        spacing_mm=[9.9, 8.8, 7.7],
    )
    findings_a = OverlapRule().evaluate(record_a, default_config())
    findings_b = OverlapRule().evaluate(record_b, default_config())
    assert len(findings_a) == 1 and len(findings_b) == 1
    assert findings_a[0].rule_id == findings_b[0].rule_id
    assert findings_a[0].severity == findings_b[0].severity
    assert findings_a[0].labels == findings_b[0].labels
    assert findings_a[0].reason == findings_b[0].reason


# =========================================================================== #
# AC15: The rule does not mutate the input record
# =========================================================================== #


def test_ac15_evaluate_does_not_mutate_record(tmp_path):
    """AC15: run_rules leaves the entire record (overlaps list and every
    entry dict) unchanged, even when findings fire."""
    entries = [
        _make_overlap_entry(_LABEL_T12, _LABEL_L2, 5, "T12", "L2"),
        _make_overlap_entry(_LABEL_T12, _LABEL_L1, 3, "T12", "L1"),
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 7, "L1", "L2"),
    ]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_ac15_overlaps_list_and_entries_not_mutated():
    """AC15: The overlaps list (including each entry dict) is unchanged after
    evaluate."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 37, "L1", "L2")]
    record = _make_record(entries)
    original = copy.deepcopy(record["overlaps"])
    run_rules(record, default_config())
    assert record["overlaps"] == original


# =========================================================================== #
# Adversarial / additional edge cases
# =========================================================================== #


def test_adv_determinism_with_degenerate_record():
    """Adversarial: two run_rules calls on a record with overlaps == {} (a
    non-list placeholder) return identical (empty) lists."""
    record = {"overlaps": {}}
    cfg = default_config()
    run1 = _overlap_findings(run_rules(record, cfg))
    run2 = _overlap_findings(run_rules(record, cfg))
    assert run1 == run2 == []


def test_adv_bad_severity_unused_when_no_overlaps_present_still_raises(tmp_path):
    """Adversarial: an invalid severity raises even when overlaps is a
    non-list placeholder — severity parsing happens up-front, independent of
    whether any entries would fire."""
    content = _overlap_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {"overlaps": {}}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_min_overlap_voxels_boundary_exactly_at_threshold(tmp_path):
    """Adversarial: overlap_voxels exactly equal to min_overlap_voxels fires
    (inclusive >= comparison), reinforcing AC8's boundary semantics."""
    entries = [_make_overlap_entry(_LABEL_L1, _LABEL_L2, 3, "L1", "L2")]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      min_overlap_voxels: 3\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _overlap_findings(run_rules(record, cfg))
    assert len(findings) == 1


def test_adv_multiple_pairs_all_below_threshold_yield_no_findings(tmp_path):
    """Adversarial: every pair below a high threshold yields zero findings,
    not a partial/empty-but-crashing result."""
    entries = [
        _make_overlap_entry(_LABEL_T12, _LABEL_L1, 1, "T12", "L1"),
        _make_overlap_entry(_LABEL_L1, _LABEL_L2, 2, "L1", "L2"),
    ]
    record = _make_record(entries)
    content = _overlap_yaml_header() + "      min_overlap_voxels: 100\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _overlap_findings(run_rules(record, cfg))
    assert findings == []
