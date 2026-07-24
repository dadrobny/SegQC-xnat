"""Tests for the JSON + human-readable report 'findings' extension (item 035,
AC10-AC15).

Covers:
- AC10: the schema gains an optional top-level 'findings' array.
- AC11: serialize_report embeds findings and still validates.
- AC12: findings serialise losslessly (rule_id, severity label, reason
  verbatim, sorted-int labels).
- AC13: omitting findings preserves the prior report shape.
- AC14: the human report renders a Findings section.
- AC15: the human report is backward-compatible and non-empty with no
  findings.

Adversarial / edge-case scenarios included:
- A finding with an empty labels frozenset (case-level) renders a no-label
  marker rather than an empty/garbled line.
- Passing Finding objects directly (not just .to_dict() dicts) to
  render_human_report.
- Malformed / additionalProperties-violating findings entries are rejected
  by jsonschema.
"""

from __future__ import annotations

import json

import pytest

from segfacet.config import HeuristicConfig, default_config
from segfacet.heuristics.finding import Finding
from segfacet.human_report import render_human_report
from segfacet.report import serialize_report, serialize_report_json
from segfacet.verdict import Reason, Severity, Verdict

# Default label convention (item 004): the labels used throughout this file.
_LABEL_T12 = 19
_LABEL_L1 = 20
_LABEL_L2 = 21


def _config() -> HeuristicConfig:
    return default_config()


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _sample_findings() -> list:
    return [
        Finding(
            rule_id="bounds",
            severity=Severity.FLAG,
            reason="Vertebra L1 volume 130000 mm3 exceeds max 120000 mm3.",
            labels=frozenset({_LABEL_L1}),
        ),
        Finding(
            rule_id="coverage",
            severity=Severity.FLAG,
            reason="Missing interior level(s): T12",
            labels=frozenset(),
        ),
        Finding(
            rule_id="overlap",
            severity=Severity.FAIL,
            reason="Overlapping segments: L1 <-> L2 (40 voxels)",
            labels=frozenset({_LABEL_L1, _LABEL_L2}),
        ),
    ]


# =========================================================================== #
# AC10: The schema gains an optional 'findings' array
# =========================================================================== #


def test_ac10_schema_has_findings_property():
    """AC10: the loaded schema's top-level properties include 'findings'."""
    from segfacet.report import _SCHEMA

    assert "findings" in _SCHEMA["properties"]


def test_ac10_findings_not_in_required():
    """AC10: 'findings' is not a required top-level property."""
    from segfacet.report import _SCHEMA

    assert "findings" not in _SCHEMA["required"]


def test_ac10_findings_property_is_array_of_finding_refs():
    """AC10: findings' schema type is array, whose items resolve to a
    definition requiring rule_id/severity/reason/labels with
    additionalProperties false."""
    from segfacet.report import _SCHEMA

    findings_schema = _SCHEMA["properties"]["findings"]
    assert findings_schema["type"] == "array"
    ref = findings_schema["items"]["$ref"]
    def_name = ref.rsplit("/", 1)[-1]
    finding_def = _SCHEMA["definitions"][def_name]
    assert finding_def["additionalProperties"] is False
    assert set(finding_def["required"]) == {"rule_id", "severity", "reason", "labels"}


def test_ac10_finding_def_rule_id_requires_non_empty_string():
    """AC10: the finding definition's rule_id has minLength >= 1."""
    from segfacet.report import _SCHEMA

    ref = _SCHEMA["properties"]["findings"]["items"]["$ref"]
    def_name = ref.rsplit("/", 1)[-1]
    finding_def = _SCHEMA["definitions"][def_name]
    rule_id_schema = finding_def["properties"]["rule_id"]
    assert rule_id_schema.get("minLength", 0) >= 1


def test_ac10_finding_def_severity_is_enum_of_three_labels():
    """AC10: the finding definition's severity is the pass/flagged/fail enum."""
    from segfacet.report import _SCHEMA

    ref = _SCHEMA["properties"]["findings"]["items"]["$ref"]
    def_name = ref.rsplit("/", 1)[-1]
    finding_def = _SCHEMA["definitions"][def_name]
    severity_schema = finding_def["properties"]["severity"]
    assert set(severity_schema["enum"]) == {"pass", "flagged-for-review", "fail"}


def test_ac10_schema_version_stays_0_1():
    """AC10: schema_version's const is unchanged at '0.1'."""
    from segfacet.report import _SCHEMA

    assert _SCHEMA["properties"]["schema_version"]["const"] == "0.1"


# =========================================================================== #
# AC11: serialize_report embeds findings and still validates
# =========================================================================== #


def test_ac11_serialize_report_with_findings_validates():
    """AC11: serialize_report(..., findings=[...]) validates without raising."""
    import jsonschema

    from segfacet.report import _SCHEMA

    findings_dicts = [f.to_dict() for f in _sample_findings()]
    report = serialize_report(
        _empty_verdict(), "case-035", _config(), findings=findings_dicts
    )
    jsonschema.validate(report, _SCHEMA)


def test_ac11_serialize_report_findings_list_equals_passed_dicts():
    """AC11: the returned dict's findings list equals the passed dicts exactly."""
    findings_dicts = [f.to_dict() for f in _sample_findings()]
    report = serialize_report(
        _empty_verdict(), "case-035", _config(), findings=findings_dicts
    )
    assert report["findings"] == findings_dicts


def test_ac11_serialize_report_json_with_findings_round_trips():
    """AC11: serialize_report_json embeds findings and the JSON text parses
    back to the same structure."""
    findings_dicts = [f.to_dict() for f in _sample_findings()]
    text = serialize_report_json(
        _empty_verdict(), "case-035", _config(), findings=findings_dicts
    )
    parsed = json.loads(text)
    assert parsed["findings"] == findings_dicts


# =========================================================================== #
# AC12: Findings serialise losslessly
# =========================================================================== #


def test_ac12_finding_rule_id_carried_verbatim():
    """AC12: each embedded finding's rule_id matches the source Finding."""
    findings = _sample_findings()
    report = serialize_report(
        _empty_verdict(), "c", _config(), findings=[f.to_dict() for f in findings]
    )
    for source, embedded in zip(findings, report["findings"]):
        assert embedded["rule_id"] == source.rule_id


def test_ac12_finding_severity_carried_as_string_label():
    """AC12: each embedded finding's severity is the string label, not the enum."""
    findings = _sample_findings()
    report = serialize_report(
        _empty_verdict(), "c", _config(), findings=[f.to_dict() for f in findings]
    )
    for source, embedded in zip(findings, report["findings"]):
        assert embedded["severity"] == source.severity.label
        assert isinstance(embedded["severity"], str)


def test_ac12_finding_reason_carried_verbatim():
    """AC12: each embedded finding's reason string matches the source exactly."""
    findings = _sample_findings()
    report = serialize_report(
        _empty_verdict(), "c", _config(), findings=[f.to_dict() for f in findings]
    )
    for source, embedded in zip(findings, report["findings"]):
        assert embedded["reason"] == source.reason


def test_ac12_finding_labels_carried_as_sorted_int_list():
    """AC12: each embedded finding's labels is a sorted list of plain ints."""
    findings = _sample_findings()
    report = serialize_report(
        _empty_verdict(), "c", _config(), findings=[f.to_dict() for f in findings]
    )
    for source, embedded in zip(findings, report["findings"]):
        assert embedded["labels"] == sorted(source.labels)
        assert all(isinstance(x, int) for x in embedded["labels"])


def test_ac12_case_level_finding_serialises_empty_labels_list():
    """AC12: a case-level finding (empty labels frozenset) serialises to []."""
    findings = _sample_findings()
    report = serialize_report(
        _empty_verdict(), "c", _config(), findings=[f.to_dict() for f in findings]
    )
    coverage_finding = next(f for f in report["findings"] if f["rule_id"] == "coverage")
    assert coverage_finding["labels"] == []


# =========================================================================== #
# AC13: Omitting findings preserves the prior report shape
# =========================================================================== #


def test_ac13_no_findings_key_when_omitted():
    """AC13: serialize_report with no findings arg produces no 'findings' key."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert "findings" not in report


def test_ac13_no_findings_key_when_none_explicit():
    """AC13: serialize_report with findings=None also omits the key."""
    report = serialize_report(_empty_verdict(), "c", _config(), findings=None)
    assert "findings" not in report


def test_ac13_omitted_findings_report_still_validates():
    """AC13: the findings-free report still validates against the extended schema."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config())
    jsonschema.validate(report, _SCHEMA)


def test_ac13_omitted_findings_matches_item_009_shape():
    """AC13: without findings/features the report has exactly the six item-009 keys."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert set(report.keys()) == {
        "schema_version",
        "config_version",
        "case_id",
        "verdict",
        "reasons",
        "per_label",
    }


# =========================================================================== #
# AC14: The human report renders a Findings section
# =========================================================================== #


def test_ac14_findings_section_header_present():
    """AC14: render_human_report with findings shows a 'Findings' section."""
    result = render_human_report(_empty_verdict(), "c", _config(), findings=_sample_findings())
    assert "Findings" in result


def test_ac14_findings_section_lists_each_rule_id():
    """AC14: each finding's rule_id appears in the rendered output."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    for f in findings:
        assert f.rule_id in result


def test_ac14_findings_section_lists_each_severity_label():
    """AC14: each finding's severity label appears in the rendered output."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    for f in findings:
        assert f.severity.label in result


def test_ac14_findings_section_reason_verbatim():
    """AC14: each finding's reason string appears verbatim in the output."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    for f in findings:
        assert f.reason in result


def test_ac14_findings_section_lists_offending_labels():
    """AC14: a label-attributed finding's integer labels appear in the output."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    assert str(_LABEL_L1) in result
    assert str(_LABEL_L2) in result


def test_ac14_case_level_finding_has_explicit_no_label_marker():
    """AC14: the case-level (coverage) finding's absence of labels is rendered
    with an explicit marker, not silently dropped."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    # The coverage finding has no labels; its reason must still appear, and no
    # raw 'frozenset()' text is allowed anywhere in the output.
    assert "Missing interior level(s): T12" in result
    assert "frozenset" not in result


def test_ac14_accepts_finding_dicts_as_well_as_objects():
    """AC14: render_human_report accepts a list of Finding.to_dict() dicts too."""
    findings = _sample_findings()
    dicts = [f.to_dict() for f in findings]
    result_from_dicts = render_human_report(_empty_verdict(), "c", _config(), findings=dicts)
    for f in findings:
        assert f.reason in result_from_dicts
        assert f.rule_id in result_from_dicts


# =========================================================================== #
# AC15: Backward-compatible and "(none)" rendering
# =========================================================================== #


def test_ac15_omitted_findings_unchanged_item_010_report():
    """AC15: render_human_report with findings omitted still returns the
    item-010 report (Verdict / Reasons / Per-label sections)."""
    result = render_human_report(_empty_verdict(), "c", _config())
    assert "Verdict:" in result
    assert "Reasons:" in result
    assert "Per-label findings:" in result


def test_ac15_empty_findings_list_renders_none():
    """AC15: findings=[] renders the Findings section as '(none)'."""
    result = render_human_report(_empty_verdict(), "c", _config(), findings=[])
    assert "Findings" in result
    # The section body must contain a "(none)" marker.
    idx = result.index("Findings")
    tail = result[idx:]
    assert "(none)" in tail


def test_ac15_both_variants_non_empty():
    """AC15: both the omitted-findings and empty-findings-list variants are
    non-empty strings."""
    omitted = render_human_report(_empty_verdict(), "c", _config())
    empty_list = render_human_report(_empty_verdict(), "c", _config(), findings=[])
    assert omitted
    assert empty_list


def test_ac15_no_raw_python_internals_leak_with_findings():
    """AC15: no repr/frozenset/class-name text appears even with findings present."""
    findings = _sample_findings()
    result = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    for forbidden in ("frozenset", "Finding(", "Severity.", "Reason(", "Traceback"):
        assert forbidden not in result


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_serialize_report_findings_and_features_together():
    """Adversarial: findings and features can be embedded in the same report
    call and both validate."""
    import jsonschema

    from segfacet.feature_report import build_features_block
    from segfacet.report import _SCHEMA

    block = build_features_block(
        geometry={}, components={}, centroids={}, relationships=None, overlaps=[]
    )
    findings_dicts = [f.to_dict() for f in _sample_findings()]
    report = serialize_report(
        _empty_verdict(), "c", _config(), features=block, findings=findings_dicts
    )
    assert "features" in report
    assert "findings" in report
    jsonschema.validate(report, _SCHEMA)


def test_adv_malformed_finding_missing_required_key_rejected():
    """Adversarial: a findings entry missing a required key fails validation."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config())
    report["findings"] = [{"rule_id": "bounds", "severity": "pass", "reason": "x"}]  # missing labels
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_adv_malformed_finding_unknown_key_rejected():
    """Adversarial: additionalProperties:false rejects an unexpected key in a
    findings entry."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config())
    report["findings"] = [
        {
            "rule_id": "bounds",
            "severity": "pass",
            "reason": "x",
            "labels": [],
            "extra_unexpected_key": 1,
        }
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_adv_malformed_finding_empty_rule_id_rejected():
    """Adversarial: an empty-string rule_id violates minLength and is rejected."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config())
    report["findings"] = [{"rule_id": "", "severity": "pass", "reason": "x", "labels": []}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_adv_malformed_finding_bad_severity_enum_rejected():
    """Adversarial: an unrecognised severity string violates the enum."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config())
    report["findings"] = [
        {"rule_id": "bounds", "severity": "not-a-severity", "reason": "x", "labels": []}
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_adv_empty_findings_list_validates():
    """Adversarial: findings=[] (present but empty) still validates."""
    import jsonschema

    from segfacet.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "c", _config(), findings=[])
    assert report["findings"] == []
    jsonschema.validate(report, _SCHEMA)


def test_adv_render_human_report_findings_deterministic():
    """Adversarial: two render_human_report calls with the same findings
    produce identical output."""
    findings = _sample_findings()
    r1 = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    r2 = render_human_report(_empty_verdict(), "c", _config(), findings=findings)
    assert r1 == r2
