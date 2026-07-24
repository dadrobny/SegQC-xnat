"""Tests for item 033 — mislabel / misalignment rule (mislabel).

Covers all 20 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:  MislabelRule registers under rule_id == "mislabel"; discoverable.
- AC2:  No finding for a well-aligned record (offsets below threshold, no
        non-monotonic pairs).
- AC3:  Detector A fires for a displaced vertebra (large spline offset).
- AC4:  Detector A finding is attributed to the single offending label.
- AC5:  Detector A reason carries the offset deviation magnitude.
- AC6:  max_offset_mm is config-driven and the comparison is inclusive.
- AC7:  The default offset threshold flags a large outlier but not a small
        offset.
- AC8:  Detector B fires for a swapped / mislabelled pair.
- AC9:  Detector B finding is attributed to both offending labels.
- AC10: Both offending levels are named in the Detector B reason.
- AC11: Multiple offset outliers each yield one finding, ascending label
        order.
- AC12: Multiple non-monotonic pairs each yield one finding, ascending
        (level_a, level_b) order.
- AC13: Detector A is config-gated by flag_offset_outliers.
- AC14: Detector B is config-gated by flag_order_inconsistency.
- AC15: Default severity is FLAG, and severity is config-driven for both
        detectors.
- AC16: An unrecognised severity string raises ValueError, before any
        per-record processing.
- AC17: The rule is deterministic.
- AC18: The rule tolerates degenerate / malformed records.
- AC19: The rule reads only the offset, monotonic-consistency, and
        per_label blocks.
- AC20: The rule does not mutate the input record.

Adversarial / edge-case scenarios included:
- stage3 absent / None / non-dict.
- per_label_offsets absent / None / non-list.
- monotonic_consistency absent / non-dict; non_monotonic_pairs non-list.
- An offset entry missing offset_mm (treated as 0.0, not flagged).
- An offset entry missing label (skipped).
- A non_monotonic_pairs entry that is not a two-element sequence (skipped).
- per_label absent -> unresolvable Detector B name omitted from labels but
  still named in the reason.
- Inclusive-threshold boundary at max_offset_mm.
- Determinism across two run_rules calls, including ordering guarantees.
- Mutation guard via deep-copy equality of the record and nested blocks.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segfacet.heuristics.mislabel  # noqa: F401 — triggers MislabelRule registration
from segfacet.heuristics import Finding, Rule, get_rule, iter_rules, run_rules
from segfacet.heuristics.mislabel import MislabelRule
from segfacet.heuristics.rule import _RULES
from segfacet.verdict import Severity
from segfacet.config import (
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

_MISALIGN_TAG = "Vertebra misaligned from spinal curve:"
_MISLABEL_TAG = "Vertebra ordering inconsistent with label:"


def _make_offset_entry(label: int, offset_mm: float, level_name: str = "?") -> dict:
    """Build a minimal per_label_offsets entry matching spline_offset_to_dict's
    (item 018) shape."""
    return {
        "label": label,
        "level_name": level_name,
        "offset_mm": offset_mm,
    }


def _make_per_label(mapping: dict) -> dict:
    """Build a per_label dict ({label: level_name}) matching item 016's shape."""
    return {
        str(label): {"label": label, "level_name": level_name}
        for label, level_name in mapping.items()
    }


def _make_record(
    offsets: list,
    pairs: list,
    per_label: dict | None = None,
    **other_fields,
) -> dict:
    """Assemble a minimal build_features_block-shaped record: a stage3
    sub-dict carrying per_label_offsets + monotonic_consistency, a top-level
    per_label map, plus any extra fields."""
    record = {
        "stage3": {
            "per_label_offsets": list(offsets),
            "monotonic_consistency": {
                "is_monotonic": len(pairs) == 0,
                "non_monotonic_pairs": [list(p) for p in pairs],
                "u_values": [],
            },
        },
    }
    if per_label is not None:
        record["per_label"] = per_label
    record.update(other_fields)
    return record


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _mislabel_yaml_header() -> str:
    """Return a YAML preamble placing the cursor inside mislabel params."""
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  mislabel:\n"
        "    params:\n"
    )


def _mislabel_findings(findings):
    """Filter to only mislabel-rule findings."""
    return [f for f in findings if f.rule_id == "mislabel"]


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'mislabel') and restore
    after."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: MislabelRule registers under rule_id == "mislabel"
# =========================================================================== #


def test_ac1_mislabel_rule_is_in_registry():
    """AC1: get_rule('mislabel') returns a Rule instance without raising."""
    rule = get_rule("mislabel")
    assert rule.rule_id == "mislabel"


def test_ac1_mislabel_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'mislabel'."""
    assert any(r.rule_id == "mislabel" for r in iter_rules())


def test_ac1_mislabel_rule_is_rule_subclass():
    """AC1: The registered MislabelRule is a subclass of segfacet.heuristics.Rule."""
    assert isinstance(get_rule("mislabel"), Rule)


# =========================================================================== #
# AC2: No finding for a well-aligned record
# =========================================================================== #


def test_ac2_well_aligned_record_no_finding():
    """AC2: All offsets below default threshold and empty non_monotonic_pairs
    under default_config() yields []."""
    offsets = [
        _make_offset_entry(_LABEL_T12, 0.5, "T12"),
        _make_offset_entry(_LABEL_L1, 1.2, "L1"),
        _make_offset_entry(_LABEL_L2, 0.8, "L2"),
    ]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# AC3 / AC4 / AC5: Detector A fires for a displaced vertebra
# =========================================================================== #


def test_ac3_detector_a_fires_for_displaced_vertebra():
    """AC3: One offset entry at/above threshold (41.3mm) emits exactly one
    Finding with rule_id == 'mislabel'."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].rule_id == "mislabel"


def test_ac4_detector_a_finding_attributed_to_single_label():
    """AC4: labels == frozenset({20}) for the AC3 entry."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


def test_ac5_detector_a_reason_carries_offset_magnitude():
    """AC5: The finding's reason contains the offset magnitude ('41.3')."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert "41.3" in findings[0].reason
    assert findings[0].reason.startswith(_MISALIGN_TAG)


# =========================================================================== #
# AC6: max_offset_mm is config-driven, inclusive comparison
# =========================================================================== #


def test_ac6_config_threshold_inclusive_boundary(tmp_path):
    """AC6: With max_offset_mm == 20.0, a 19.9mm entry yields no finding while
    a 20.0mm entry yields exactly one (inclusive >=)."""
    offsets = [
        _make_offset_entry(_LABEL_T12, 19.9, "T12"),
        _make_offset_entry(_LABEL_L1, 20.0, "L1"),
    ]
    record = _make_record(offsets, [])
    content = _mislabel_yaml_header() + "      max_offset_mm: 20.0\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC7: Default offset threshold flags a large outlier, not a small offset
# =========================================================================== #


def test_ac7_default_threshold_flags_large_not_small():
    """AC7: Under default_config() (15.0mm), a 3.0mm entry yields no finding
    while a 40.0mm entry yields exactly one."""
    offsets = [
        _make_offset_entry(_LABEL_T12, 3.0, "T12"),
        _make_offset_entry(_LABEL_L1, 40.0, "L1"),
    ]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC8 / AC9 / AC10: Detector B fires for a swapped / mislabelled pair
# =========================================================================== #


def test_ac8_detector_b_fires_for_swapped_pair():
    """AC8: One non_monotonic_pairs entry ["L1", "L2"] (offsets below
    threshold) emits exactly one Finding with rule_id == 'mislabel'."""
    offsets = [
        _make_offset_entry(_LABEL_L1, 1.0, "L1"),
        _make_offset_entry(_LABEL_L2, 1.0, "L2"),
    ]
    per_label = _make_per_label({_LABEL_L1: "L1", _LABEL_L2: "L2"})
    record = _make_record(offsets, [["L1", "L2"]], per_label=per_label)
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].rule_id == "mislabel"


def test_ac9_detector_b_finding_attributed_to_both_labels():
    """AC9: labels == frozenset({20, 21}) with per_label mapping L1->20,
    L2->21."""
    offsets = []
    per_label = _make_per_label({_LABEL_L1: "L1", _LABEL_L2: "L2"})
    record = _make_record(offsets, [["L1", "L2"]], per_label=per_label)
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1, _LABEL_L2})


def test_ac10_both_offending_levels_named_in_reason():
    """AC10: The resolved integer labels 20 and 21 both appear in the
    reason."""
    offsets = []
    per_label = _make_per_label({_LABEL_L1: "L1", _LABEL_L2: "L2"})
    record = _make_record(offsets, [["L1", "L2"]], per_label=per_label)
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert "20" in reason
    assert "21" in reason
    assert reason.startswith(_MISLABEL_TAG)


# =========================================================================== #
# AC11: Multiple offset outliers, ascending label order
# =========================================================================== #


def test_ac11_multiple_offset_outliers_ascending_label_order():
    """AC11: Three above-threshold entries with labels 21, 19, 20 (fed
    unsorted) emit three findings ordered 19, 20, 21."""
    offsets = [
        _make_offset_entry(_LABEL_L2, 30.0, "L2"),
        _make_offset_entry(_LABEL_T12, 25.0, "T12"),
        _make_offset_entry(_LABEL_L1, 20.0, "L1"),
    ]
    record = _make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 3
    assert findings[0].labels == frozenset({_LABEL_T12})
    assert findings[1].labels == frozenset({_LABEL_L1})
    assert findings[2].labels == frozenset({_LABEL_L2})


# =========================================================================== #
# AC12: Multiple non-monotonic pairs, ascending (level_a, level_b) order
# =========================================================================== #


def test_ac12_multiple_pairs_ascending_name_pair_order():
    """AC12: [["T12","L1"], ["L1","L2"]] fed in reverse order emits two
    findings ordered ("L1","L2") then ("T12","L1") — ascending by name
    pair."""
    per_label = _make_per_label(
        {_LABEL_T12: "T12", _LABEL_L1: "L1", _LABEL_L2: "L2"}
    )
    record = _make_record(
        [], [["L1", "L2"], ["T12", "L1"]], per_label=per_label
    )
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert findings[0].labels == frozenset({_LABEL_L1, _LABEL_L2})
    assert findings[1].labels == frozenset({_LABEL_T12, _LABEL_L1})


# =========================================================================== #
# AC13: Detector A config-gated by flag_offset_outliers
# =========================================================================== #


def test_ac13_flag_offset_outliers_false_suppresses_detector_a(tmp_path):
    """AC13: With flag_offset_outliers == false, a record carrying an
    above-threshold offset and a non-monotonic pair yields no offset finding
    but still yields the order finding."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    content = _mislabel_yaml_header() + "      flag_offset_outliers: false\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_MISLABEL_TAG)


# =========================================================================== #
# AC14: Detector B config-gated by flag_order_inconsistency
# =========================================================================== #


def test_ac14_flag_order_inconsistency_false_suppresses_detector_b(tmp_path):
    """AC14: With flag_order_inconsistency == false, a record carrying an
    above-threshold offset and a non-monotonic pair yields no order finding
    but still yields the offset finding."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    content = (
        _mislabel_yaml_header() + "      flag_order_inconsistency: false\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_MISALIGN_TAG)


# =========================================================================== #
# AC15: Default severity is FLAG, config-driven for both detectors
# =========================================================================== #


def test_ac15_default_severity_is_flag_for_both_detectors():
    """AC15: With no severity param, both an offset finding and an order
    finding have Severity.FLAG."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert all(f.severity is Severity.FLAG for f in findings)


def test_ac15_severity_param_fail_overrides_default_for_both_detectors(
    tmp_path,
):
    """AC15: With params.severity = 'fail', both emitted findings have
    Severity.FAIL."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    content = _mislabel_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert len(findings) == 2
    assert all(f.severity is Severity.FAIL for f in findings)


# =========================================================================== #
# AC16: An unrecognised severity string raises ValueError before any
# per-record processing
# =========================================================================== #


def test_ac16_unrecognised_severity_raises_value_error(tmp_path):
    """AC16: An unrecognised severity param string raises ValueError."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    record = _make_record(offsets, [])
    content = _mislabel_yaml_header() + "      severity: xyz_not_a_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac16_value_error_raised_before_per_record_processing(tmp_path):
    """AC16: ValueError fires even for a degenerate record with no stage3 at
    all — severity is parsed before any per-record processing (so the raise
    cannot come from per-detector iteration)."""
    content = _mislabel_yaml_header() + "      severity: garbage\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac16_value_error_has_non_empty_message(tmp_path):
    """AC16: The ValueError for a bad severity has a non-empty, readable
    message."""
    content = _mislabel_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {}
    with pytest.raises(ValueError) as exc_info:
        run_rules(record, cfg)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC17: Deterministic
# =========================================================================== #


def test_ac17_two_runs_return_equal_lists():
    """AC17: Two successive run_rules calls return equal finding lists in the
    same order."""
    offsets = [
        _make_offset_entry(_LABEL_L2, 30.0, "L2"),
        _make_offset_entry(_LABEL_T12, 25.0, "T12"),
    ]
    per_label = _make_per_label(
        {_LABEL_T12: "T12", _LABEL_L1: "L1", _LABEL_L2: "L2"}
    )
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    cfg = default_config()
    run1 = _mislabel_findings(run_rules(record, cfg))
    run2 = _mislabel_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


# =========================================================================== #
# AC18: Tolerates degenerate / malformed records
# =========================================================================== #


def test_ac18_stage3_absent_no_raise():
    """AC18: record has no 'stage3' key at all."""
    record = {}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert isinstance(result, list)
    assert result == []


def test_ac18_stage3_none_no_raise():
    """AC18: stage3 == None is treated as no stage3 block."""
    record = {"stage3": None}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_stage3_non_dict_no_raise():
    """AC18: stage3 == [] (a non-dict placeholder) is treated as {}."""
    record = {"stage3": []}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_per_label_offsets_absent_no_raise():
    """AC18: stage3 present but per_label_offsets absent yields no offset
    findings."""
    record = {"stage3": {"monotonic_consistency": {"non_monotonic_pairs": []}}}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_per_label_offsets_none_no_raise():
    """AC18: per_label_offsets == None is treated as no offsets."""
    record = {
        "stage3": {
            "per_label_offsets": None,
            "monotonic_consistency": {"non_monotonic_pairs": []},
        }
    }
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_per_label_offsets_non_list_no_raise():
    """AC18: per_label_offsets == {} (non-list placeholder) is treated as no
    offsets."""
    record = {
        "stage3": {
            "per_label_offsets": {},
            "monotonic_consistency": {"non_monotonic_pairs": []},
        }
    }
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_monotonic_consistency_absent_no_raise():
    """AC18: monotonic_consistency absent yields no order findings."""
    record = {"stage3": {"per_label_offsets": []}}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_monotonic_consistency_none_no_raise():
    """AC18: monotonic_consistency == None is treated as {}."""
    record = {"stage3": {"per_label_offsets": [], "monotonic_consistency": None}}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_monotonic_consistency_non_dict_no_raise():
    """AC18: monotonic_consistency == [] (non-dict placeholder) is treated as
    {}."""
    record = {"stage3": {"per_label_offsets": [], "monotonic_consistency": []}}
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_non_monotonic_pairs_absent_no_raise():
    """AC18: monotonic_consistency present but non_monotonic_pairs absent
    yields no order findings."""
    record = {
        "stage3": {"per_label_offsets": [], "monotonic_consistency": {}},
    }
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_non_monotonic_pairs_none_no_raise():
    """AC18: non_monotonic_pairs == None is treated as no pairs."""
    record = {
        "stage3": {
            "per_label_offsets": [],
            "monotonic_consistency": {"non_monotonic_pairs": None},
        }
    }
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_non_monotonic_pairs_non_list_no_raise():
    """AC18: non_monotonic_pairs == {} (non-list placeholder) is treated as
    no pairs."""
    record = {
        "stage3": {
            "per_label_offsets": [],
            "monotonic_consistency": {"non_monotonic_pairs": {}},
        }
    }
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_offset_entry_missing_offset_mm_treated_as_zero():
    """AC18: An offset entry missing offset_mm is treated as 0.0, hence not
    flagged."""
    offsets = [{"label": _LABEL_L1, "level_name": "L1"}]
    record = _make_record(offsets, [])
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_offset_entry_missing_label_skipped():
    """AC18: An offset entry missing label is skipped, even though its
    offset_mm is above threshold."""
    offsets = [{"level_name": "L1", "offset_mm": 41.3}]
    record = _make_record(offsets, [])
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_non_monotonic_pair_not_two_element_skipped():
    """AC18: A non_monotonic_pairs entry that is not a two-element sequence
    is skipped."""
    record = _make_record([], [["L1"], ["T12", "L1", "L2"]])
    result = _mislabel_findings(run_rules(record, default_config()))
    assert result == []


def test_ac18_per_label_absent_unresolvable_name_omitted_from_labels():
    """AC18: per_label absent -> a Detector B name cannot be resolved; it is
    omitted from labels but still named in the reason."""
    record = _make_record([], [["T12", "L1"]])
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset()
    reason = findings[0].reason
    assert "T12" in reason
    assert "L1" in reason


# =========================================================================== #
# AC19: The rule reads only offset / monotonic-consistency / per_label blocks
# =========================================================================== #


def test_ac19_field_isolation_identical_findings():
    """AC19: Two records with identical per_label_offsets, monotonic
    consistency, and per_label but different overlaps / relationships /
    stage3.spacing_consistency / stage3.curvature / geometry fields yield
    identical finding lists.

    Evaluated directly via MislabelRule().evaluate() (rather than run_rules)
    so the comparison isolates AC19's claim about the mislabel rule alone."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})

    def _record(overlaps, relationships, extra_stage3, spacing_mm):
        record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
        record["stage3"].update(extra_stage3)
        record["overlaps"] = overlaps
        record["relationships"] = relationships
        record["spacing_mm"] = spacing_mm
        return record

    record_a = _record(
        overlaps=[{"label_a": 1, "label_b": 2, "overlap_voxels": 5}],
        relationships={"present_levels": ["L1"]},
        extra_stage3={"spacing_consistency": {"a": 1}, "curvature": {"k": 1.0}},
        spacing_mm=[1.0, 1.0, 1.0],
    )
    record_b = _record(
        overlaps=[],
        relationships={"present_levels": []},
        extra_stage3={"spacing_consistency": None, "curvature": None},
        spacing_mm=[9.9, 8.8, 7.7],
    )
    findings_a = MislabelRule().evaluate(record_a, default_config())
    findings_b = MislabelRule().evaluate(record_b, default_config())
    assert len(findings_a) == 2 and len(findings_b) == 2
    for fa, fb in zip(findings_a, findings_b):
        assert fa.rule_id == fb.rule_id
        assert fa.severity == fb.severity
        assert fa.labels == fb.labels
        assert fa.reason == fb.reason


# =========================================================================== #
# AC20: The rule does not mutate the input record
# =========================================================================== #


def test_ac20_evaluate_does_not_mutate_record(tmp_path):
    """AC20: run_rules leaves the entire record (stage3 sub-block and every
    nested list/dict) unchanged, even when findings fire."""
    offsets = [
        _make_offset_entry(_LABEL_T12, 25.0, "T12"),
        _make_offset_entry(_LABEL_L1, 41.3, "L1"),
    ]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1", _LABEL_L2: "L2"})
    record = _make_record(offsets, [["L1", "L2"]], per_label=per_label)
    content = _mislabel_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_ac20_stage3_sub_blocks_not_mutated():
    """AC20: The stage3.per_label_offsets list and monotonic_consistency
    dict (including nested pairs) are unchanged after evaluate."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    original_stage3 = copy.deepcopy(record["stage3"])
    run_rules(record, default_config())
    assert record["stage3"] == original_stage3


# =========================================================================== #
# Adversarial / additional edge cases
# =========================================================================== #


def test_adv_determinism_with_degenerate_record():
    """Adversarial: two run_rules calls on a record with degenerate stage3
    placeholders return identical (empty) lists."""
    record = {"stage3": {"per_label_offsets": {}, "monotonic_consistency": []}}
    cfg = default_config()
    run1 = _mislabel_findings(run_rules(record, cfg))
    run2 = _mislabel_findings(run_rules(record, cfg))
    assert run1 == run2 == []


def test_adv_bad_severity_raises_even_with_degenerate_stage3(tmp_path):
    """Adversarial: an invalid severity raises even when stage3 is a
    non-dict placeholder — severity parsing happens up-front, independent of
    whether any entries would fire."""
    content = _mislabel_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {"stage3": []}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_offset_findings_ordered_before_order_findings():
    """Adversarial: the combined finding list is offset findings first, then
    order findings — verified with both detectors firing simultaneously."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    findings = _mislabel_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert findings[0].reason.startswith(_MISALIGN_TAG)
    assert findings[1].reason.startswith(_MISLABEL_TAG)


def test_adv_all_offsets_below_threshold_yield_no_findings(tmp_path):
    """Adversarial: every offset entry below a high threshold yields zero
    findings, not a partial/empty-but-crashing result."""
    offsets = [
        _make_offset_entry(_LABEL_T12, 1.0, "T12"),
        _make_offset_entry(_LABEL_L1, 2.0, "L1"),
    ]
    record = _make_record(offsets, [])
    content = _mislabel_yaml_header() + "      max_offset_mm: 100.0\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert findings == []


def test_adv_max_offset_mm_boundary_exactly_at_threshold(tmp_path):
    """Adversarial: an offset exactly equal to a custom max_offset_mm fires
    (inclusive >= comparison), reinforcing AC6's boundary semantics."""
    offsets = [_make_offset_entry(_LABEL_L1, 7.5, "L1")]
    record = _make_record(offsets, [])
    content = _mislabel_yaml_header() + "      max_offset_mm: 7.5\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert len(findings) == 1


def test_adv_both_gates_false_yields_no_findings(tmp_path):
    """Adversarial: with both flag_offset_outliers and
    flag_order_inconsistency disabled, no findings are emitted even though
    both signals would otherwise fire."""
    offsets = [_make_offset_entry(_LABEL_L1, 41.3, "L1")]
    per_label = _make_per_label({_LABEL_T12: "T12", _LABEL_L1: "L1"})
    record = _make_record(offsets, [["T12", "L1"]], per_label=per_label)
    content = (
        _mislabel_yaml_header()
        + "      flag_offset_outliers: false\n"
        + "      flag_order_inconsistency: false\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _mislabel_findings(run_rules(record, cfg))
    assert findings == []
