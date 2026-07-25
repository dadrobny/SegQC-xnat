"""Tests for item 031 — border-partial-vertebra rule (border).

Covers all 16 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:  BorderRule registers under rule_id == "border"; discoverable.
- AC2:  No finding for a fully-interior label.
- AC3:  A finding fires for a label touching the volume boundary.
- AC4:  The offending vertebra is attributed by its integer label.
- AC5:  An expected superior FOV-end truncation is suppressed by default.
- AC6:  An expected inferior FOV-end truncation is suppressed by default.
- AC7:  A mid-spine cranio-caudal clip IS flagged.
- AC8:  An in-plane clip on a terminal vertebra is still flagged.
- AC9:  report_expected_ends surfaces expected end truncations.
- AC10: Multiple border-touching labels each yield one finding, in ascending
        integer-label order.
- AC11: Default severity is FLAG; severity is config-driven.
- AC12: An unrecognised severity string raises ValueError.
- AC13: The rule is deterministic.
- AC14: The rule is spacing-agnostic.
- AC15: The rule tolerates degenerate / malformed records.
- AC16: The rule does not mutate the input record.

Adversarial / edge-case scenarios included:
- A terminal vertebra touching the opposite end face is flagged unexpected.
- An entry whose geometry is present but every flag False produces no
  finding even amid other flagged labels (interior amid clipped).
- Determinism across two run_rules calls; ascending integer-label order.
- Mutation guard via deep-copy equality.
- Missing per_label entries / absent geometry sub-block tolerated.
- Missing relationships / empty present_levels treated as unexpected.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segfacet.heuristics.border  # noqa: F401 — triggers BorderRule registration
from segfacet.heuristics import Finding, Rule, get_rule, iter_rules, run_rules
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

_ALL_FACES = (
    "touches_superior",
    "touches_inferior",
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)


def _make_entry(label: int, level_name: str, touched_faces=(), **other_geom) -> dict:
    """Build a minimal per_label entry with the six touches_* flags, defaulting
    all to False except the named *touched_faces*."""
    geometry = {face: (face in touched_faces) for face in _ALL_FACES}
    geometry.update(other_geom)
    return {"label": label, "level_name": level_name, "geometry": geometry}


def _make_record(present_levels: list, entries: list) -> dict:
    """Assemble a minimal build_features_block-shaped record: per_label keyed
    by integer label, plus relationships.present_levels."""
    return {
        "relationships": {"present_levels": list(present_levels)},
        "per_label": {e["label"]: e for e in entries},
    }


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _border_yaml_header() -> str:
    """Return a YAML preamble placing the cursor inside border params."""
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  border:\n"
        "    params:\n"
    )


def _border_findings(findings):
    """Filter to only border-rule findings."""
    return [f for f in findings if f.rule_id == "border"]


_UNEXPECTED_CLIP_TAG = "Partial vertebra clipped by FOV:"
_EXPECTED_END_TAG = "Partial vertebra at FOV end (expected):"


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'border') and restore after."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: BorderRule registers under rule_id == "border"
# =========================================================================== #


def test_ac1_border_rule_is_in_registry():
    """AC1: get_rule('border') returns a Rule instance without raising."""
    rule = get_rule("border")
    assert rule.rule_id == "border"


def test_ac1_border_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'border'."""
    assert any(r.rule_id == "border" for r in iter_rules())


def test_ac1_border_rule_is_rule_subclass():
    """AC1: The registered BorderRule is a subclass of segfacet.heuristics.Rule."""
    assert isinstance(get_rule("border"), Rule)


# =========================================================================== #
# AC2: No finding for a fully-interior label
# =========================================================================== #


def test_ac2_fully_interior_label_no_finding():
    """AC2: A single per_label entry with all six touches_* flags False under
    default_config() yields no border finding."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=())]
    record = _make_record(["L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == [], f"Interior label should produce no finding; got {findings}"


# =========================================================================== #
# AC3 / AC4: A finding fires for a label touching the boundary; attributed by
# its integer label
# =========================================================================== #


def test_ac3_in_plane_touch_fires_exactly_one_finding():
    """AC3: touches_left == True (in-plane face) emits exactly one Finding
    with rule_id == 'border'."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = _make_record(["L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].rule_id == "border"


def test_ac4_offending_vertebra_attributed_by_integer_label():
    """AC4: label == 20 => finding.labels == frozenset({20})."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = _make_record(["L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC5 / AC6: Expected FOV-end truncation suppressed by default
# =========================================================================== #


def test_ac5_expected_superior_end_suppressed_by_default():
    """AC5: present_levels[0] touching only touches_superior yields no finding
    under default_config()."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac6_expected_inferior_end_suppressed_by_default():
    """AC6: present_levels[-1] touching only touches_inferior yields no
    finding under default_config()."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=()),
        _make_entry(_LABEL_L1, "L1", touched_faces=("touches_inferior",)),
    ]
    record = _make_record(["T12", "L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# AC7: A mid-spine cranio-caudal clip IS flagged
# =========================================================================== #


def test_ac7_mid_spine_superior_touch_is_flagged():
    """AC7: A level that is neither present_levels[0] nor [-1] touching
    touches_superior emits exactly one finding naming that label."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=()),
        _make_entry(_LABEL_L1, "L1", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L2, "L2", touched_faces=()),
    ]
    record = _make_record(["T12", "L1", "L2"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})
    assert findings[0].reason.startswith(_UNEXPECTED_CLIP_TAG)


# =========================================================================== #
# AC8: An in-plane clip on a terminal vertebra is still flagged
# =========================================================================== #


def test_ac8_terminal_vertebra_with_in_plane_touch_is_flagged():
    """AC8: present_levels[0] touching both touches_superior and touches_left
    still emits one finding (in-plane makes it unexpected)."""
    entries = [
        _make_entry(
            _LABEL_T12, "T12", touched_faces=("touches_superior", "touches_left")
        ),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_T12})


# =========================================================================== #
# AC9: report_expected_ends surfaces expected end truncations
# =========================================================================== #


def test_ac9_report_expected_ends_surfaces_finding(tmp_path):
    """AC9: With report_expected_ends true, the AC5 record emits exactly one
    finding at end_severity default (Severity.PASS), label-attributed."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    content = _border_yaml_header() + "      report_expected_ends: true\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _border_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].severity is Severity.PASS
    assert findings[0].labels == frozenset({_LABEL_T12})
    assert findings[0].reason.startswith(_EXPECTED_END_TAG)


def test_ac9_report_expected_ends_uses_end_severity_override(tmp_path):
    """AC9: end_severity overrides the severity used for expected-end
    findings when report_expected_ends is true."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    content = (
        _border_yaml_header()
        + "      report_expected_ends: true\n"
        + "      end_severity: flagged-for-review\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _border_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].severity is Severity.FLAG


# =========================================================================== #
# AC10: Multiple border-touching labels each yield one finding, in ascending
# integer-label order
# =========================================================================== #


def test_ac10_multiple_offenders_ascending_label_order():
    """AC10: Two unexpected clips (labels 21, 19) plus one interior label
    yield exactly two findings ordered by ascending integer label."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_left",)),  # 19
        _make_entry(_LABEL_L1, "L1", touched_faces=()),  # 20, interior
        _make_entry(_LABEL_L2, "L2", touched_faces=("touches_right",)),  # 21
    ]
    record = _make_record(["T12", "L1", "L2"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert findings[0].labels == frozenset({_LABEL_T12})
    assert findings[1].labels == frozenset({_LABEL_L2})


# =========================================================================== #
# AC11: Default severity is FLAG, and severity is config-driven
# =========================================================================== #


def test_ac11_default_severity_is_flag():
    """AC11: With no severity param, an unexpected-clip finding has
    Severity.FLAG."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = _make_record(["L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings
    assert all(f.severity is Severity.FLAG for f in findings)


def test_ac11_severity_param_fail_overrides_default(tmp_path):
    """AC11: With params.severity = 'fail', the emitted finding has
    Severity.FAIL."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = _make_record(["L1"], entries)
    content = _border_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _border_findings(run_rules(record, cfg))
    assert findings
    assert all(f.severity is Severity.FAIL for f in findings)


# =========================================================================== #
# AC12: An unrecognised severity string raises ValueError
# =========================================================================== #


def test_ac12_unrecognised_severity_raises_value_error(tmp_path):
    """AC12: An unrecognised severity param string raises ValueError."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = _make_record(["L1"], entries)
    content = _border_yaml_header() + "      severity: xyz_not_a_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac12_value_error_raised_before_per_record_processing(tmp_path):
    """AC12: ValueError fires even for an empty / interior record — severity
    is parsed before any per-record processing."""
    content = _border_yaml_header() + "      severity: garbage\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record = {"per_label": {}, "relationships": None}
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac12_value_error_has_non_empty_message(tmp_path):
    """AC12: The ValueError for a bad severity has a non-empty, readable
    message."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=())]
    record = _make_record(["L1"], entries)
    content = _border_yaml_header() + "      severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    with pytest.raises(ValueError) as exc_info:
        run_rules(record, cfg)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC13: Deterministic
# =========================================================================== #


def test_ac13_two_runs_return_equal_lists():
    """AC13: Two successive run_rules calls return equal finding lists in the
    same order."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_left",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
        _make_entry(_LABEL_L2, "L2", touched_faces=("touches_right",)),
    ]
    record = _make_record(["T12", "L1", "L2"], entries)
    cfg = default_config()
    run1 = _border_findings(run_rules(record, cfg))
    run2 = _border_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


# =========================================================================== #
# AC14: Spacing-agnostic
# =========================================================================== #


def test_ac14_spacing_agnostic_identical_findings():
    """AC14: Two records with identical touches_* flags but different mm /
    spacing / extent / volume geometry fields yield identical finding lists."""
    entries_a = [
        _make_entry(
            _LABEL_L1,
            "L1",
            touched_faces=("touches_left",),
            physical_volume_mm3=1234.5,
            extent_x_mm=10.0,
            bbox=[0, 1, 2, 3, 4, 5],
        )
    ]
    entries_b = [
        _make_entry(
            _LABEL_L1,
            "L1",
            touched_faces=("touches_left",),
            physical_volume_mm3=9999.9,
            extent_x_mm=999.0,
            bbox=[10, 20, 30, 40, 50, 60],
        )
    ]
    record_a = _make_record(["L1"], entries_a)
    record_b = _make_record(["L1"], entries_b)
    findings_a = _border_findings(run_rules(record_a, default_config()))
    findings_b = _border_findings(run_rules(record_b, default_config()))
    assert len(findings_a) == 1 and len(findings_b) == 1
    assert findings_a[0].rule_id == findings_b[0].rule_id
    assert findings_a[0].severity == findings_b[0].severity
    assert findings_a[0].labels == findings_b[0].labels
    assert findings_a[0].reason == findings_b[0].reason


# =========================================================================== #
# AC15: Tolerates degenerate / malformed records
# =========================================================================== #


def test_ac15_per_label_empty_no_raise():
    """AC15: per_label == {} returns [] without raising."""
    record = {"per_label": {}, "relationships": {"present_levels": []}}
    assert _border_findings(run_rules(record, default_config())) == []


def test_ac15_per_label_absent_no_raise():
    """AC15: record has no 'per_label' key at all."""
    record = {"relationships": {"present_levels": []}}
    result = _border_findings(run_rules(record, default_config()))
    assert isinstance(result, list)
    assert result == []


def test_ac15_entry_without_geometry_contributes_no_finding():
    """AC15: A per_label entry with no 'geometry' sub-block contributes no
    finding and does not crash."""
    record = {
        "per_label": {_LABEL_L1: {"label": _LABEL_L1, "level_name": "L1"}},
        "relationships": {"present_levels": ["L1"]},
    }
    result = _border_findings(run_rules(record, default_config()))
    assert result == []


def test_ac15_relationships_none_border_touch_treated_unexpected():
    """AC15: relationships None/absent with a border-touching label is
    treated as unexpected (surfaced), not crashing."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_superior",))]
    record = {"per_label": {e["label"]: e for e in entries}, "relationships": None}
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


def test_ac15_relationships_absent_border_touch_treated_unexpected():
    """AC15: record has no 'relationships' key at all; a border-touching
    label is still surfaced as unexpected."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_inferior",))]
    record = {"per_label": {e["label"]: e for e in entries}}
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


def test_ac15_present_levels_empty_border_touch_treated_unexpected():
    """AC15: present_levels == [] with a border-touching label is treated as
    unexpected (terminal distinction unavailable), with no crash."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_superior",))]
    record = _make_record([], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC16: The rule does not mutate the input record
# =========================================================================== #


def test_ac16_evaluate_does_not_mutate_record(tmp_path):
    """AC16: run_rules leaves the entire record (relationships, per_label, and
    every nested geometry sub-block) unchanged, even when findings fire."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_left",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L2, "L2", touched_faces=()),
    ]
    record = _make_record(["T12", "L1", "L2"], entries)
    content = _border_yaml_header() + "      severity: fail\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_ac16_per_label_dict_not_mutated():
    """AC16: per_label mapping (including nested geometry sub-dicts) is
    unchanged after evaluate."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    original = copy.deepcopy(record["per_label"])
    run_rules(record, default_config())
    assert record["per_label"] == original


def test_ac16_relationships_not_mutated():
    """AC16: relationships.present_levels is unchanged after evaluate."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    original = list(record["relationships"]["present_levels"])
    run_rules(record, default_config())
    assert record["relationships"]["present_levels"] == original


# =========================================================================== #
# Adversarial / additional edge cases
# =========================================================================== #


def test_adv_terminal_vertebra_touching_opposite_end_is_flagged():
    """Adversarial: the superior-most present level touching touches_inferior
    (the opposite end) is flagged unexpected — the mid/opposite-end
    inconsistency reinforces AC7's classification."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_inferior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_T12})


def test_adv_interior_label_amid_clipped_labels_no_finding_for_it():
    """Adversarial: an entry whose geometry is present but every flag False
    produces no finding even amid other flagged labels."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_left",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),  # interior, amid clips
        _make_entry(_LABEL_L2, "L2", touched_faces=("touches_right",)),
    ]
    record = _make_record(["T12", "L1", "L2"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    labels_flagged = {label for f in findings for label in f.labels}
    assert _LABEL_L1 not in labels_flagged
    assert labels_flagged == {_LABEL_T12, _LABEL_L2}


def test_adv_single_present_level_double_end_touch_flagged():
    """Adversarial: a lone present level is simultaneously present_levels[0]
    and [-1]; touching both touches_superior and touches_inferior is
    'expected' at both ends and thus suppressed by default."""
    entries = [
        _make_entry(
            _LABEL_L1, "L1", touched_faces=("touches_superior", "touches_inferior")
        )
    ]
    record = _make_record(["L1"], entries)
    findings = _border_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_report_expected_ends_false_explicit_no_finding(tmp_path):
    """Adversarial: explicitly setting report_expected_ends: false behaves
    identically to the (default) suppressed path."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    content = _border_yaml_header() + "      report_expected_ends: false\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _border_findings(run_rules(record, cfg))
    assert findings == []


def test_adv_bad_end_severity_unused_on_default_path_no_raise(tmp_path):
    """Adversarial: a malformed end_severity does not raise when
    report_expected_ends is left at its default (false) — it's only
    validated on the report_expected_ends == true path."""
    entries = [
        _make_entry(_LABEL_T12, "T12", touched_faces=("touches_superior",)),
        _make_entry(_LABEL_L1, "L1", touched_faces=()),
    ]
    record = _make_record(["T12", "L1"], entries)
    content = _border_yaml_header() + "      end_severity: not_a_real_severity\n"
    cfg = load_config(_write_yaml(tmp_path, content))
    findings = _border_findings(run_rules(record, cfg))
    assert findings == []


def test_adv_determinism_with_degenerate_record():
    """Adversarial: two run_rules calls on a record with no relationships
    return identical lists."""
    entries = [_make_entry(_LABEL_L1, "L1", touched_faces=("touches_left",))]
    record = {"per_label": {e["label"]: e for e in entries}}
    cfg = default_config()
    run1 = _border_findings(run_rules(record, cfg))
    run2 = _border_findings(run_rules(record, cfg))
    assert run1 == run2
