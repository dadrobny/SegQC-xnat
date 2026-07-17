"""Tests for item 029 — incomplete-coverage / missing-level rule (coverage).

Covers all 16 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:  CoverageRule registers under rule_id == "coverage"; discoverable.
- AC2:  No finding for a contiguous fixture spanning its range.
- AC3:  A missing-interior-level finding fires when an interior level is removed.
- AC4:  All missing interior levels are named in one finding, canonical order.
- AC5:  No spurious finding when the range is truncated at the FOV edge.
- AC6:  The expected-span check is config-driven (fires when configured, silent
        by default).
- AC7:  The expected-span check is border-aware (suppresses FOV-truncated ends).
- AC8:  The expected-span check still fires when the span end is not at the border.
- AC9:  The expected-count check is config-driven and fires below the minimum.
- AC10: The expected-count check does not fire when the minimum is met.
- AC11: Both opt-in checks are disabled by default.
- AC12: Default severity is FLAG; severity is config-driven.
- AC13: An unrecognised severity string raises ValueError.
- AC14: The rule is deterministic with a fixed output order (missing-interior,
        incomplete-span, count-shortfall).
- AC15: The rule tolerates an absent / None / empty relationship record.
- AC16: The rule does not mutate the input record.

Adversarial / edge-case scenarios included:
- All three checks fire at once for a single record; fixed order confirmed.
- border_aware: false un-suppresses a truncated end.
- expected_levels containing a non-canonical / unknown name is ignored.
- A single-present-level record does not crash and fires no interior/span finding.
- An interior gap whose bracketing neighbour touches a border is still flagged
  (interior gaps are never border-suppressed).
- Determinism across two run_rules calls.
- Mutation guard via deep-copy equality.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segqc.heuristics.coverage  # noqa: F401 — triggers CoverageRule registration
from segqc.heuristics import Finding, Rule, get_rule, iter_rules, run_rules
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


def _make_per_label_entry(
    label: int,
    level_name: str,
    touches_superior: bool = False,
    touches_inferior: bool = False,
) -> dict:
    """Build a minimal per_label entry carrying only level_name + border flags."""
    return {
        "label": label,
        "level_name": level_name,
        "geometry": {
            "touches_superior": touches_superior,
            "touches_inferior": touches_inferior,
        },
    }


def _make_record(
    present_levels: list,
    missing_levels: list,
    label_entries: list = None,
) -> dict:
    """Assemble a minimal build_features_block-shaped record.

    ``relationships`` carries present_levels/missing_levels (item 014 shape);
    ``per_label`` is keyed by each entry's integer label.
    """
    return {
        "relationships": {
            "present_levels": list(present_levels),
            "missing_levels": list(missing_levels),
            "is_continuous": len(missing_levels) == 0,
            "out_of_order_labels": [],
        },
        "per_label": {e["label"]: e for e in (label_entries or [])},
        "overlaps": {},
    }


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    """Write *content* to a YAML file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _coverage_yaml_header() -> str:
    """Return a YAML preamble placing the cursor inside coverage params."""
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  coverage:\n"
        "    params:\n"
    )


def _levels_yaml_list(levels: list, indent: str = "      ") -> str:
    """Render a YAML list block for expected_levels under the given indent."""
    lines = [f"{indent}expected_levels:\n"]
    for lvl in levels:
        lines.append(f"{indent}  - {lvl}\n")
    return "".join(lines)


def _cov_findings(findings):
    """Filter to only coverage-rule findings."""
    return [f for f in findings if f.rule_id == "coverage"]


def _by_tag(findings, tag: str):
    """Filter coverage findings whose reason starts with the given tag."""
    return [f for f in _cov_findings(findings) if f.reason.startswith(tag)]


_INTERIOR_TAG = "Missing interior level(s):"
_SPAN_TAG = "Incomplete coverage (span):"
_COUNT_TAG = "Below expected count:"


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'coverage') and restore after."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: CoverageRule registers under rule_id == "coverage"
# =========================================================================== #


def test_ac1_coverage_rule_is_in_registry():
    """AC1: get_rule('coverage') returns a Rule instance without raising."""
    rule = get_rule("coverage")
    assert rule.rule_id == "coverage"


def test_ac1_coverage_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'coverage'."""
    assert any(r.rule_id == "coverage" for r in iter_rules())


def test_ac1_coverage_rule_is_rule_subclass():
    """AC1: The registered CoverageRule is a subclass of segqc.heuristics.Rule."""
    assert isinstance(get_rule("coverage"), Rule)


# =========================================================================== #
# AC2: No finding for a contiguous fixture spanning its range
# =========================================================================== #


def test_ac2_contiguous_span_no_finding():
    """AC2: missing_levels == [] under default_config() yields no coverage finding."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3"),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    findings = _cov_findings(run_rules(record, default_config()))
    assert findings == [], f"Contiguous span should produce no finding; got {findings}"


# =========================================================================== #
# AC3: A missing-interior-level finding fires when an interior level is removed
# =========================================================================== #


def test_ac3_single_interior_gap_fires_exactly_one_finding():
    """AC3: missing_levels == ['L3'] emits exactly one Finding naming L3."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
        _make_per_label_entry(5, "L5"),
    ]
    record = _make_record(["L1", "L2", "L4", "L5"], ["L3"], entries)
    interior = _by_tag(run_rules(record, default_config()), _INTERIOR_TAG)
    assert len(interior) == 1
    assert interior[0].rule_id == "coverage"
    assert "L3" in interior[0].reason
    assert interior[0].labels == frozenset()


# =========================================================================== #
# AC4: All missing interior levels named in one finding, canonical order
# =========================================================================== #


def test_ac4_two_interior_gaps_one_finding_canonical_order():
    """AC4: missing_levels == ['T12', 'L2'] fires a single finding naming both,
    T12 before L2 (canonical head-to-tail order)."""
    entries = [
        _make_per_label_entry(1, "T11"),
        _make_per_label_entry(2, "T13"),
        _make_per_label_entry(3, "L1"),
        _make_per_label_entry(4, "L3"),
    ]
    record = _make_record(["T11", "T13", "L1", "L3"], ["T12", "L2"], entries)
    interior = _by_tag(run_rules(record, default_config()), _INTERIOR_TAG)
    assert len(interior) == 1, "Both missing levels must be named in one finding"
    reason = interior[0].reason
    assert "T12" in reason and "L2" in reason
    assert reason.index("T12") < reason.index("L2"), (
        f"T12 must precede L2 in canonical order; reason={reason!r}"
    )


# =========================================================================== #
# AC5: No spurious finding when the range is truncated at the FOV edge
# =========================================================================== #


def test_ac5_fov_truncated_span_no_finding():
    """AC5: Contiguous present levels with bottommost touching inferior border
    yields no finding under default_config()."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3", touches_inferior=True),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    findings = _cov_findings(run_rules(record, default_config()))
    assert findings == [], f"FOV-truncated contiguous span should not fire; got {findings}"


# =========================================================================== #
# AC6: The expected-span check is config-driven
# =========================================================================== #


def test_ac6_expected_span_beyond_present_fires_when_configured(tmp_path):
    """AC6: expected_levels extending beyond present span (non-border end) fires
    an incomplete-span finding."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3"),  # bottommost, not touching border
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    content = (
        _coverage_yaml_header() + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert len(span) == 1
    assert span[0].rule_id == "coverage"
    # Item 089 (FOV-aware default, border_aware=True): a non-truncated span
    # end only flags the single canonically-adjacent expected level (L4,
    # immediately below present L3) — not every remaining absent level.
    assert "L4" in span[0].reason
    assert "L5" not in span[0].reason


def test_ac6_expected_span_absent_by_default_no_span_finding():
    """AC6: With expected_levels absent (default), the same record emits no
    span finding."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3"),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    span = _by_tag(run_rules(record, default_config()), _SPAN_TAG)
    assert span == []


# =========================================================================== #
# AC7: The expected-span check is border-aware
# =========================================================================== #


def test_ac7_inferior_truncation_suppresses_span_finding(tmp_path):
    """AC7: Bottommost present level touches_inferior => beyond-end expected
    levels are suppressed (no incomplete-span finding) with border_aware default True."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3", touches_inferior=True),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    content = (
        _coverage_yaml_header() + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert span == [], f"Border-truncated inferior end must suppress span finding; got {span}"


def test_ac7_superior_truncation_suppresses_span_finding(tmp_path):
    """AC7: Topmost present level touches_superior => beyond-end expected levels
    at the superior end are suppressed."""
    entries = [
        _make_per_label_entry(1, "T2", touches_superior=True),
        _make_per_label_entry(2, "T3"),
        _make_per_label_entry(3, "T4"),
        _make_per_label_entry(4, "T5"),
    ]
    record = _make_record(["T2", "T3", "T4", "T5"], [], entries)
    content = (
        _coverage_yaml_header() + _levels_yaml_list(["T1", "T2", "T3", "T4", "T5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert span == [], f"Border-truncated superior end must suppress span finding; got {span}"


# =========================================================================== #
# AC8: The expected-span check still fires when the span end is not at the border
# =========================================================================== #


def test_ac8_non_border_end_still_fires(tmp_path):
    """AC8: Identical expected_levels to AC7 but span end not touching border
    still flags the absent expected level(s)."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3", touches_inferior=False),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    content = (
        _coverage_yaml_header() + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert span, "Non-border-truncated end must still fire the span finding"
    # Item 089 (FOV-aware default, border_aware=True): only the single
    # canonically-adjacent expected level (L4) is flagged beyond a
    # non-truncated end — the further, non-adjacent L5 is not.
    assert "L4" in span[0].reason
    assert "L5" not in span[0].reason


# =========================================================================== #
# AC9: The expected-count check is config-driven and fires below the minimum
# =========================================================================== #


def test_ac9_expected_count_above_present_fires(tmp_path):
    """AC9: expected_count above present count fires a count-shortfall finding
    reporting present count and expected minimum."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
    ]
    record = _make_record(["L1", "L2"], [], entries)
    content = _coverage_yaml_header() + "      expected_count: 5\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    count = _by_tag(run_rules(record, cfg), _COUNT_TAG)
    assert len(count) == 1
    assert count[0].rule_id == "coverage"
    assert count[0].labels == frozenset()
    assert "2" in count[0].reason and "5" in count[0].reason


# =========================================================================== #
# AC10: The expected-count check does not fire when the minimum is met
# =========================================================================== #


def test_ac10_expected_count_met_no_finding(tmp_path):
    """AC10: expected_count at present count does not fire."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
    ]
    record = _make_record(["L1", "L2"], [], entries)
    content = _coverage_yaml_header() + "      expected_count: 2\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    count = _by_tag(run_rules(record, cfg), _COUNT_TAG)
    assert count == []


def test_ac10_expected_count_below_present_no_finding(tmp_path):
    """AC10: expected_count below present count does not fire."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3"),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    content = _coverage_yaml_header() + "      expected_count: 1\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    count = _by_tag(run_rules(record, cfg), _COUNT_TAG)
    assert count == []


# =========================================================================== #
# AC11: Both opt-in checks are disabled by default
# =========================================================================== #


def test_ac11_default_config_never_emits_span_or_count():
    """AC11: default_config() never emits an incomplete-span or count-shortfall
    finding; only the interior check can fire."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    findings = run_rules(record, default_config())
    assert _by_tag(findings, _SPAN_TAG) == []
    assert _by_tag(findings, _COUNT_TAG) == []
    # Interior check may still fire.
    assert _by_tag(findings, _INTERIOR_TAG)


# =========================================================================== #
# AC12: Default severity is FLAG; severity is config-driven
# =========================================================================== #


def test_ac12_default_severity_is_flag():
    """AC12: With no severity param, every emitted finding has Severity.FLAG."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    findings = _cov_findings(run_rules(record, default_config()))
    assert findings
    assert all(f.severity is Severity.FLAG for f in findings)


def test_ac12_severity_param_fail_overrides_default(tmp_path):
    """AC12: With params.severity = 'fail', emitted findings have Severity.FAIL."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    content = _coverage_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _cov_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings)


# =========================================================================== #
# AC13: An unrecognised severity string raises ValueError
# =========================================================================== #


def test_ac13_unrecognised_severity_raises_value_error(tmp_path):
    """AC13: An unrecognised severity param string raises ValueError."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    content = _coverage_yaml_header() + "      severity: xyz_not_a_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac13_value_error_raised_even_with_empty_relationships(tmp_path):
    """AC13: ValueError fires even for a record without a relationships block
    (severity is parsed before per-record processing)."""
    content = _coverage_yaml_header() + "      severity: garbage\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {"per_label": {}, "relationships": None, "overlaps": {}}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac13_value_error_has_non_empty_message(tmp_path):
    """AC13: The ValueError for a bad severity has a non-empty, readable message."""
    entries = [_make_per_label_entry(1, "L1")]
    record = _make_record(["L1"], [], entries)
    content = _coverage_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError) as exc_info:
        run_rules(record, cfg)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC14: Deterministic with fixed output order
# =========================================================================== #


def test_ac14_two_runs_return_equal_lists():
    """AC14: Two successive run_rules calls return equal finding lists."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    cfg = default_config()
    run1 = _cov_findings(run_rules(record, cfg))
    run2 = _cov_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


def test_ac14_fixed_order_interior_then_span_then_count(tmp_path):
    """AC14: When all three checks fire, findings appear in order
    missing-interior, incomplete-span, count-shortfall."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),  # bottommost, not touching border
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
        + "      expected_count: 10\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _cov_findings(run_rules(record, cfg))
    assert len(findings) == 3, f"Expected 3 findings; got {len(findings)}: {findings}"
    assert findings[0].reason.startswith(_INTERIOR_TAG)
    assert findings[1].reason.startswith(_SPAN_TAG)
    assert findings[2].reason.startswith(_COUNT_TAG)


# =========================================================================== #
# AC15: Tolerates absent / None / empty relationship record
# =========================================================================== #


def test_ac15_relationships_none_returns_empty_list():
    """AC15: record['relationships'] is None => [] without raising."""
    record = {"relationships": None, "per_label": {}, "overlaps": {}}
    assert _cov_findings(run_rules(record, default_config())) == []


def test_ac15_relationships_absent_returns_empty_list():
    """AC15: record has no 'relationships' key => [] without raising."""
    record = {"per_label": {}, "overlaps": {}}
    assert _cov_findings(run_rules(record, default_config())) == []


def test_ac15_present_and_missing_levels_absent_no_raise():
    """AC15: relationships present but without present_levels/missing_levels keys."""
    record = {"relationships": {}, "per_label": {}, "overlaps": {}}
    assert _cov_findings(run_rules(record, default_config())) == []


def test_ac15_per_label_empty_no_raise():
    """AC15: per_label == {} does not crash the rule."""
    record = {
        "relationships": {"present_levels": ["L1"], "missing_levels": []},
        "per_label": {},
        "overlaps": {},
    }
    assert _cov_findings(run_rules(record, default_config())) == []


def test_ac15_per_label_absent_no_raise():
    """AC15: record has no 'per_label' key at all."""
    record = {
        "relationships": {"present_levels": ["L1"], "missing_levels": []},
        "overlaps": {},
    }
    result = _cov_findings(run_rules(record, default_config()))
    assert isinstance(result, list)


# =========================================================================== #
# AC16: The rule does not mutate the input record
# =========================================================================== #


def test_ac16_evaluate_does_not_mutate_record(tmp_path):
    """AC16: run_rules leaves the entire record (relationships, per_label,
    geometry, and every list) unchanged, even when all checks fire."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4"),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
        + "      expected_count: 10\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_ac16_missing_levels_list_not_mutated():
    """AC16: The missing_levels list inside relationships is unchanged after evaluate."""
    entries = [
        _make_per_label_entry(1, "T11"),
        _make_per_label_entry(2, "T13"),
        _make_per_label_entry(3, "L1"),
        _make_per_label_entry(4, "L3"),
    ]
    record = _make_record(["T11", "T13", "L1", "L3"], ["L2", "T12"], entries)
    original = list(record["relationships"]["missing_levels"])
    run_rules(record, default_config())
    assert record["relationships"]["missing_levels"] == original


# =========================================================================== #
# Adversarial: edge cases and combined scenarios
# =========================================================================== #


def test_adv_all_three_checks_fire_together(tmp_path):
    """Adversarial: interior gap + expected-span shortfall (non-border end) +
    below expected_count all fire together, three findings in fixed order."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(3, "L3"),  # bottommost, not touching border
    ]
    record = _make_record(["L1", "L3"], ["L2"], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["L1", "L2", "L3", "L4"])
        + "      expected_count: 10\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _cov_findings(run_rules(record, cfg))
    assert len(findings) == 3, f"Expected 3 findings; got {findings}"
    assert findings[0].reason.startswith(_INTERIOR_TAG)
    assert findings[1].reason.startswith(_SPAN_TAG)
    assert findings[2].reason.startswith(_COUNT_TAG)


def test_adv_border_aware_false_unsuppresses_truncated_end(tmp_path):
    """Adversarial: border_aware: false fires the span finding despite the
    span-end vertebra touching the image border."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(3, "L3", touches_inferior=True),
    ]
    record = _make_record(["L1", "L2", "L3"], [], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["L1", "L2", "L3", "L4", "L5"])
        + "      border_aware: false\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert span, "border_aware: false must un-suppress the truncated-end finding"


def test_adv_unknown_expected_level_name_ignored(tmp_path):
    """Adversarial: A non-canonical / unknown name in expected_levels is
    ignored without raising."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
    ]
    record = _make_record(["L1", "L2"], [], entries)
    content = (
        _coverage_yaml_header() + _levels_yaml_list(["L1", "L2", "NOT_A_LEVEL"])
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    result = _cov_findings(run_rules(record, cfg))
    assert isinstance(result, list)
    for f in result:
        assert "NOT_A_LEVEL" not in f.reason


def test_adv_single_present_level_no_crash_no_finding():
    """Adversarial: A single-present-level record (missing_levels empty) does
    not crash and fires no interior/span finding under default config."""
    entries = [_make_per_label_entry(1, "L3")]
    record = _make_record(["L3"], [], entries)
    findings = _cov_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_interior_gap_with_border_touching_neighbour_still_flagged():
    """Adversarial: An interior gap bracketed by a neighbour that touches a
    border is still flagged — interior gaps are never border-suppressed."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
        _make_per_label_entry(4, "L4", touches_inferior=True),
    ]
    record = _make_record(["L1", "L2", "L4"], ["L3"], entries)
    interior = _by_tag(run_rules(record, default_config()), _INTERIOR_TAG)
    assert interior, "Interior gap must fire even if the bottommost neighbour touches a border"
    assert "L3" in interior[0].reason


def test_adv_determinism_multi_check_record(tmp_path):
    """Adversarial: Two run_rules calls on a multi-check-firing record return
    identical lists."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(3, "L3"),
    ]
    record = _make_record(["L1", "L3"], ["L2"], entries)
    content = (
        _coverage_yaml_header()
        + _levels_yaml_list(["L1", "L2", "L3", "L4"])
        + "      expected_count: 10\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    run1 = _cov_findings(run_rules(record, cfg))
    run2 = _cov_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


def test_adv_malformed_relationships_not_a_mapping_no_raise():
    """Adversarial: relationships that is not a mapping (e.g. a string) is
    tolerated and yields no findings rather than crashing."""
    record = {"relationships": "not-a-dict", "per_label": {}, "overlaps": {}}
    result = _cov_findings(run_rules(record, default_config()))
    assert result == []


def test_adv_expected_levels_empty_list_disables_span_check(tmp_path):
    """Adversarial: expected_levels explicitly set to [] behaves like absent
    (span check disabled)."""
    entries = [
        _make_per_label_entry(1, "L1"),
        _make_per_label_entry(2, "L2"),
    ]
    record = _make_record(["L1", "L2"], [], entries)
    content = _coverage_yaml_header() + "      expected_levels: []\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    span = _by_tag(run_rules(record, cfg), _SPAN_TAG)
    assert span == []
