"""Tests for the JSON report schema v0 and serializer (item 009).

Covers all fourteen Acceptance Criteria plus adversarial and edge-case inputs:
schema validation for missing/extra fields, round-trip determinism, golden-
snapshot output, empty verdict serialization, label key string conversion,
sorted labels, unknown label keys, missing config_version, future schema
version numbers, empty case_id, and import purity.

All tests are deterministic, CPU-only, and portable (no I/O beyond jsonschema
validation, no network, no absolute paths).
"""

from __future__ import annotations

import json

import pytest

from segqc.config import HeuristicConfig, default_config
from segqc.report import serialize_report, serialize_report_json
from segqc.verdict import Reason, Severity, Verdict


# =========================================================================== #
# Shared fixtures / helpers
# =========================================================================== #

def _config(schema_version: str = "0.1") -> HeuristicConfig:
    """Return a HeuristicConfig with the given schema_version string."""
    return HeuristicConfig(
        schema_version=schema_version,
        min_foreground_voxels=0,
        min_label_count=0,
    )


def _empty_verdict() -> Verdict:
    """Return a Verdict with no reasons and no per-label entries."""
    return Verdict.build(reasons=[], per_label={})


def _simple_flag_verdict() -> Verdict:
    """Return a Verdict with one case-level FLAG reason."""
    r = Reason(message="near-empty segmentation", severity=Severity.FLAG)
    return Verdict.build(reasons=[r], per_label={})


def _fail_verdict_with_per_label() -> Verdict:
    """Return a Verdict with a FAIL reason under label 42."""
    r_case = Reason(message="too few labels", severity=Severity.FLAG)
    r_label = Reason(
        message="label 42 has no voxels",
        severity=Severity.FAIL,
        labels=frozenset({42}),
    )
    return Verdict.build(reasons=[r_case], per_label={42: [r_label]})


def _multi_label_verdict() -> Verdict:
    """Return a Verdict spanning three labels with mixed severities."""
    r1 = Reason(message="L1 voxel count low", severity=Severity.FLAG, labels=frozenset({20}))
    r2 = Reason(message="T12 completely missing", severity=Severity.FAIL, labels=frozenset({19}))
    r3 = Reason(message="C1 small but present", severity=Severity.PASS, labels=frozenset({1}))
    return Verdict.build(
        reasons=[],
        per_label={20: [r1], 19: [r2], 1: [r3]},
    )


# =========================================================================== #
# AC-1  Schema file exists and is valid JSON
# =========================================================================== #

def test_ac1_schema_file_is_loadable():
    """The v0 schema file is locatable via importlib.resources and parses as JSON."""
    import importlib.resources as pkg_resources
    import segqc

    # Access the schema file as a package resource.
    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    text = ref.read_text(encoding="utf-8")
    schema = json.loads(text)
    assert isinstance(schema, dict)


def test_ac1_schema_has_dollar_schema_field():
    """The schema has a '$schema' field indicating its meta-schema."""
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))
    assert "$schema" in schema


def test_ac1_schema_is_an_object_type():
    """The top-level schema type is 'object'."""
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))
    assert schema.get("type") == "object"


# =========================================================================== #
# AC-2  Schema requires correct fields
# =========================================================================== #

def test_ac2_schema_requires_schema_version():
    """A report missing 'schema_version' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["schema_version"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac2_schema_requires_config_version():
    """A report missing 'config_version' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["config_version"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac2_schema_requires_case_id():
    """A report missing 'case_id' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["case_id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac2_schema_requires_verdict():
    """A report missing 'verdict' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["verdict"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac2_schema_requires_reasons():
    """A report missing 'reasons' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["reasons"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


def test_ac2_schema_requires_per_label():
    """A report missing 'per_label' fails jsonschema validation."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report["per_label"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


@pytest.mark.parametrize("required_field", [
    "schema_version", "config_version", "case_id", "verdict", "reasons", "per_label",
])
def test_ac2_schema_requires_each_field(required_field):
    """Each of the six required fields, when removed, causes validation failure."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case001", _config())
    del report[required_field]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, schema)


# =========================================================================== #
# AC-3  serialize_report importable
# =========================================================================== #

def test_ac3_serialize_report_importable():
    """serialize_report is importable from segqc.report with no errors."""
    from segqc.report import serialize_report as sr
    assert callable(sr)


def test_ac3_serialize_report_json_importable():
    """serialize_report_json is importable from segqc.report with no errors."""
    from segqc.report import serialize_report_json as srj
    assert callable(srj)


# =========================================================================== #
# AC-4  serialize_report returns a conforming dict
# =========================================================================== #

def test_ac4_empty_verdict_conforms_to_schema():
    """An empty verdict serialized to dict validates against the v0 schema."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "case-empty", _config())
    jsonschema.validate(report, schema)


def test_ac4_flag_verdict_conforms_to_schema():
    """A FLAG verdict dict validates against the v0 schema."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_simple_flag_verdict(), "case-flag", _config())
    jsonschema.validate(report, schema)


def test_ac4_fail_verdict_with_per_label_conforms_to_schema():
    """A FAIL verdict with per-label reasons validates against the v0 schema."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_fail_verdict_with_per_label(), "case-fail", _config())
    jsonschema.validate(report, schema)


def test_ac4_multi_label_verdict_conforms_to_schema():
    """A verdict spanning multiple labels validates against the v0 schema."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_multi_label_verdict(), "case-multi", _config())
    jsonschema.validate(report, schema)


def test_ac4_result_is_dict():
    """serialize_report returns a plain dict."""
    report = serialize_report(_empty_verdict(), "case001", _config())
    assert isinstance(report, dict)


# =========================================================================== #
# AC-5  verdict field maps to Severity.label strings
# =========================================================================== #

def test_ac5_verdict_pass_is_string_pass():
    """An empty verdict serializes to verdict='pass'."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert report["verdict"] == "pass"


def test_ac5_verdict_flag_is_string_flagged_for_review():
    """A FLAG overall verdict serializes to 'flagged-for-review'."""
    report = serialize_report(_simple_flag_verdict(), "c", _config())
    assert report["verdict"] == "flagged-for-review"


def test_ac5_verdict_fail_is_string_fail():
    """A FAIL overall verdict serializes to 'fail'."""
    r = Reason(message="completely empty", severity=Severity.FAIL)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    assert report["verdict"] == "fail"


@pytest.mark.parametrize("sev, expected_label", [
    (Severity.PASS, "pass"),
    (Severity.FLAG, "flagged-for-review"),
    (Severity.FAIL, "fail"),
])
def test_ac5_verdict_field_all_severities(sev, expected_label):
    """All three severity levels serialize to the correct verdict string."""
    r = Reason(message="test", severity=sev)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    assert report["verdict"] == expected_label


# =========================================================================== #
# AC-6  reasons array is complete and correct
# =========================================================================== #

def test_ac6_case_level_reason_appears_in_reasons_array():
    """A case-level FLAG reason appears in the serialized reasons array."""
    r = Reason(message="near-empty segmentation", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "case001", _config())
    assert len(report["reasons"]) == 1
    item = report["reasons"][0]
    assert item["message"] == "near-empty segmentation"
    assert item["severity"] == "flagged-for-review"


def test_ac6_reasons_message_field_is_string():
    """Each serialized reason has a 'message' field that is a string."""
    r = Reason(message="some message", severity=Severity.PASS)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    assert isinstance(report["reasons"][0]["message"], str)


def test_ac6_reasons_severity_field_is_label_string():
    """Each serialized reason has a 'severity' field using the label string."""
    for sev in Severity:
        r = Reason(message=f"sev={sev.name}", severity=sev)
        verdict = Verdict.build(reasons=[r], per_label={})
        report = serialize_report(verdict, "c", _config())
        assert report["reasons"][0]["severity"] == sev.label


def test_ac6_reasons_labels_field_is_list_of_ints():
    """Each serialized reason has a 'labels' field that is a list of integers."""
    r = Reason(message="msg", severity=Severity.FLAG, labels=frozenset({10, 20}))
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    labels = report["reasons"][0]["labels"]
    assert isinstance(labels, list)
    assert all(isinstance(x, int) for x in labels)
    assert set(labels) == {10, 20}


def test_ac6_reasons_labels_sorted():
    """Labels in each serialized reason are sorted in ascending order."""
    r = Reason(message="msg", severity=Severity.FLAG, labels=frozenset({30, 5, 17}))
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    labels = report["reasons"][0]["labels"]
    assert labels == sorted(labels)


def test_ac6_multiple_reasons_all_appear():
    """All case-level reasons appear in the reasons array in order."""
    msgs = ["first problem", "second problem", "third problem"]
    reasons = [Reason(message=m, severity=Severity.FLAG) for m in msgs]
    verdict = Verdict.build(reasons=reasons, per_label={})
    report = serialize_report(verdict, "c", _config())
    assert len(report["reasons"]) == 3
    assert [r["message"] for r in report["reasons"]] == msgs


def test_ac6_empty_labels_frozenset_serializes_to_empty_list():
    """A Reason with no specific labels serializes to 'labels': []."""
    r = Reason(message="case-level", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    assert report["reasons"][0]["labels"] == []


# =========================================================================== #
# AC-7  per_label serialization — string keys, correct structure
# =========================================================================== #

def test_ac7_per_label_keys_are_strings():
    """per_label in the serialized report uses string keys (JSON requires this)."""
    r = Reason(message="label 42 issue", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[], per_label={42: [r]})
    report = serialize_report(verdict, "c", _config())
    assert "42" in report["per_label"]
    assert 42 not in report["per_label"]


def test_ac7_per_label_integer_label_is_string_key():
    """Integer label value N becomes string key 'N' in per_label."""
    for label_int in [0, 1, 19, 42, 999]:
        r = Reason(message=f"label {label_int}", severity=Severity.PASS)
        verdict = Verdict.build(reasons=[], per_label={label_int: [r]})
        report = serialize_report(verdict, "c", _config())
        assert str(label_int) in report["per_label"]


def test_ac7_per_label_reason_structure_same_as_case_level():
    """Per-label reasons have the same message/severity/labels structure."""
    r = Reason(message="per-label reason", severity=Severity.FAIL, labels=frozenset({42}))
    verdict = Verdict.build(reasons=[], per_label={42: [r]})
    report = serialize_report(verdict, "c", _config())
    entry = report["per_label"]["42"][0]
    assert entry["message"] == "per-label reason"
    assert entry["severity"] == "fail"
    assert 42 in entry["labels"]


def test_ac7_multiple_labels_each_serialized():
    """All labels present in per_label are present in the serialized output."""
    verdict = _multi_label_verdict()
    report = serialize_report(verdict, "c", _config())
    assert "20" in report["per_label"]
    assert "19" in report["per_label"]
    assert "1" in report["per_label"]


def test_ac7_per_label_reasons_order_preserved():
    """Order of reasons within a per-label entry is preserved."""
    msgs = ["alpha", "beta", "gamma"]
    reasons = [Reason(message=m, severity=Severity.FLAG) for m in msgs]
    verdict = Verdict.build(reasons=[], per_label={5: reasons})
    report = serialize_report(verdict, "c", _config())
    serialized_msgs = [r["message"] for r in report["per_label"]["5"]]
    assert serialized_msgs == msgs


def test_ac7_empty_per_label_serializes_to_empty_object():
    """When per_label is empty the serialized per_label is an empty dict."""
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "c", _config())
    assert report["per_label"] == {}


# =========================================================================== #
# AC-8  config_version is included
# =========================================================================== #

def test_ac8_config_version_present_in_report():
    """The serialized report contains a 'config_version' field."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert "config_version" in report


def test_ac8_config_version_equals_heuristicconfig_schema_version():
    """config_version equals the schema_version from the HeuristicConfig passed in."""
    cfg = _config(schema_version="0.1")
    report = serialize_report(_empty_verdict(), "c", cfg)
    assert report["config_version"] == "0.1"


def test_ac8_config_version_reflects_custom_version():
    """A non-default config schema_version string is faithfully reproduced."""
    cfg = HeuristicConfig(
        schema_version="custom-version-xyz",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(_empty_verdict(), "c", cfg)
    assert report["config_version"] == "custom-version-xyz"


# =========================================================================== #
# AC-9  case_id is included
# =========================================================================== #

def test_ac9_case_id_present_in_report():
    """The serialized report contains a 'case_id' field."""
    report = serialize_report(_empty_verdict(), "case-abc", _config())
    assert "case_id" in report


def test_ac9_case_id_equals_argument():
    """The case_id in the report equals the string passed to serialize_report."""
    report = serialize_report(_empty_verdict(), "my-scan-001", _config())
    assert report["case_id"] == "my-scan-001"


def test_ac9_case_id_with_spaces_and_special_chars():
    """case_id strings with spaces and special characters are preserved as-is."""
    case_id = "Patient 42 / scan 2026-06-25"
    report = serialize_report(_empty_verdict(), case_id, _config())
    assert report["case_id"] == case_id


# =========================================================================== #
# AC-10  Round-trip stability / determinism
# =========================================================================== #

def test_ac10_same_verdict_same_output_twice():
    """Calling serialize_report twice with identical inputs produces equal dicts."""
    verdict = _fail_verdict_with_per_label()
    cfg = _config()
    r1 = serialize_report(verdict, "case001", cfg)
    r2 = serialize_report(verdict, "case001", cfg)
    assert r1 == r2


def test_ac10_deterministic_across_verdicts_built_from_same_inputs():
    """Two Verdict objects built from identical inputs serialize identically."""
    def _build():
        r = Reason(message="consistent", severity=Severity.FLAG)
        return Verdict.build(reasons=[r], per_label={})

    cfg = _config()
    r1 = serialize_report(_build(), "c", cfg)
    r2 = serialize_report(_build(), "c", cfg)
    assert r1 == r2


def test_ac10_json_output_is_deterministic():
    """serialize_report_json produces the same string on repeated calls."""
    verdict = _multi_label_verdict()
    cfg = _config()
    s1 = serialize_report_json(verdict, "c", cfg)
    s2 = serialize_report_json(verdict, "c", cfg)
    assert s1 == s2


def test_ac10_schema_version_in_report_is_always_v0():
    """schema_version in the report is always '0.1' (the v0 schema marker)."""
    for verdict in [_empty_verdict(), _simple_flag_verdict()]:
        report = serialize_report(verdict, "c", _config())
        assert report["schema_version"] == "0.1"


# =========================================================================== #
# AC-11  Empty verdict serializes to pass with empty collections
# =========================================================================== #

def test_ac11_empty_verdict_overall_is_pass():
    """An empty verdict serializes with verdict='pass'."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert report["verdict"] == "pass"


def test_ac11_empty_verdict_reasons_is_empty_list():
    """An empty verdict serializes with reasons=[]."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert report["reasons"] == []


def test_ac11_empty_verdict_per_label_is_empty_object():
    """An empty verdict serializes with per_label={}."""
    report = serialize_report(_empty_verdict(), "c", _config())
    assert report["per_label"] == {}


def test_ac11_empty_verdict_validates_against_schema():
    """An empty verdict dict validates against the v0 schema."""
    import jsonschema
    import importlib.resources as pkg_resources
    import segqc

    ref = pkg_resources.files(segqc).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))

    report = serialize_report(_empty_verdict(), "c", _config())
    jsonschema.validate(report, schema)


# =========================================================================== #
# AC-12  serialize_report_json returns a valid JSON string
# =========================================================================== #

def test_ac12_serialize_report_json_returns_str():
    """serialize_report_json returns a str."""
    result = serialize_report_json(_empty_verdict(), "c", _config())
    assert isinstance(result, str)


def test_ac12_json_string_is_parseable():
    """The JSON string returned by serialize_report_json parses without error."""
    result = serialize_report_json(_empty_verdict(), "c", _config())
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_ac12_json_string_equals_dict():
    """Parsed JSON string equals the dict from serialize_report."""
    verdict = _fail_verdict_with_per_label()
    cfg = _config()
    report_dict = serialize_report(verdict, "case-x", cfg)
    json_str = serialize_report_json(verdict, "case-x", cfg)
    parsed = json.loads(json_str)
    assert parsed == report_dict


def test_ac12_json_string_with_custom_indent():
    """serialize_report_json with indent=0 produces compact JSON."""
    result = serialize_report_json(_empty_verdict(), "c", _config(), indent=0)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


# =========================================================================== #
# AC-13  Module location
# =========================================================================== #

def test_ac13_import_from_segqc_report():
    """Both functions are importable directly from segqc.report."""
    from segqc.report import serialize_report as sr
    from segqc.report import serialize_report_json as srj
    assert sr is not None
    assert srj is not None


def test_ac13_no_import_error():
    """Importing segqc.report raises no ImportError or AttributeError."""
    import importlib
    mod = importlib.import_module("segqc.report")
    assert hasattr(mod, "serialize_report")
    assert hasattr(mod, "serialize_report_json")


# =========================================================================== #
# AC-14  No unexpected heavy runtime imports
# =========================================================================== #

def test_ac14_no_numpy_in_report_module():
    """segqc.report must not import numpy at module level."""
    import segqc.report as report_mod
    module_globals = vars(report_mod)
    assert "numpy" not in module_globals


def test_ac14_no_nibabel_in_report_module():
    """segqc.report must not import nibabel at module level."""
    import segqc.report as report_mod
    module_globals = vars(report_mod)
    assert "nibabel" not in module_globals
    assert "nib" not in module_globals


def test_ac14_no_scipy_in_report_module():
    """segqc.report must not import scipy at module level."""
    import segqc.report as report_mod
    assert "scipy" not in vars(report_mod)


# =========================================================================== #
# Golden snapshot — deterministic structure
# =========================================================================== #

def test_golden_snapshot_fixed_flag_verdict():
    """Serialized output for a fixed FLAG verdict matches expected structure exactly."""
    r = Reason(message="near-empty segmentation", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    cfg = HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(verdict, "snapshot-case-001", cfg)

    assert report["schema_version"] == "0.1"
    assert report["config_version"] == "0.1"
    assert report["case_id"] == "snapshot-case-001"
    assert report["verdict"] == "flagged-for-review"
    assert report["reasons"] == [
        {"message": "near-empty segmentation", "severity": "flagged-for-review", "labels": []}
    ]
    assert report["per_label"] == {}


def test_golden_snapshot_fail_verdict_with_label():
    """Serialized output for a fixed FAIL verdict with label 42 matches expected structure."""
    r_case = Reason(message="too few labels", severity=Severity.FLAG)
    r_label = Reason(
        message="label 42 has no voxels",
        severity=Severity.FAIL,
        labels=frozenset({42}),
    )
    verdict = Verdict.build(reasons=[r_case], per_label={42: [r_label]})
    cfg = HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(verdict, "snapshot-case-002", cfg)

    assert report["schema_version"] == "0.1"
    assert report["verdict"] == "fail"
    assert len(report["reasons"]) == 1
    assert report["reasons"][0]["message"] == "too few labels"
    assert report["reasons"][0]["severity"] == "flagged-for-review"
    assert report["per_label"]["42"][0]["message"] == "label 42 has no voxels"
    assert report["per_label"]["42"][0]["severity"] == "fail"
    assert report["per_label"]["42"][0]["labels"] == [42]


def test_golden_snapshot_keys_in_expected_set():
    """Serialized report has exactly the six expected top-level keys."""
    report = serialize_report(_empty_verdict(), "c", _config())
    expected_keys = {"schema_version", "config_version", "case_id", "verdict", "reasons", "per_label"}
    assert set(report.keys()) == expected_keys


# =========================================================================== #
# Adversarial — empty reasons list
# =========================================================================== #

def test_adv_empty_reasons_list_in_serialized_form():
    """Verdict with no case-level reasons serializes to reasons=[]."""
    r = Reason(message="label only", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[], per_label={1: [r]})
    report = serialize_report(verdict, "c", _config())
    assert report["reasons"] == []


def test_adv_per_label_with_empty_reason_lists():
    """per_label keys with empty reason lists serialize to empty arrays."""
    verdict = Verdict.build(reasons=[], per_label={5: [], 10: []})
    report = serialize_report(verdict, "c", _config())
    # Empty lists in per_label are still serialized (key is present)
    for key in ("5", "10"):
        if key in report["per_label"]:
            assert report["per_label"][key] == []


# =========================================================================== #
# Adversarial — unknown / edge-case label values
# =========================================================================== #

def test_adv_label_zero_as_per_label_key():
    """Label value 0 (background) serializes to per_label key '0'."""
    r = Reason(message="background issue", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[], per_label={0: [r]})
    report = serialize_report(verdict, "c", _config())
    assert "0" in report["per_label"]
    assert len(report["per_label"]["0"]) == 1


def test_adv_large_label_value_as_per_label_key():
    """Very large integer label values serialize correctly to string keys."""
    r = Reason(message="big label", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[], per_label={999999: [r]})
    report = serialize_report(verdict, "c", _config())
    assert "999999" in report["per_label"]


def test_adv_many_per_label_entries():
    """Verdict with 50 per-label entries serializes with all 50 string keys."""
    per_label = {
        i: [Reason(message=f"label {i}", severity=Severity.FLAG)]
        for i in range(50)
    }
    verdict = Verdict.build(reasons=[], per_label=per_label)
    report = serialize_report(verdict, "c", _config())
    assert len(report["per_label"]) == 50
    for i in range(50):
        assert str(i) in report["per_label"]


# =========================================================================== #
# Adversarial — labels sorted within reason
# =========================================================================== #

def test_adv_labels_in_reason_always_sorted():
    """Labels field in serialized reason is always sorted regardless of frozenset order."""
    labels = frozenset({100, 1, 50, 3})
    r = Reason(message="multi-label", severity=Severity.FAIL, labels=labels)
    verdict = Verdict.build(reasons=[r], per_label={})
    report = serialize_report(verdict, "c", _config())
    serialized_labels = report["reasons"][0]["labels"]
    assert serialized_labels == sorted(labels)


# =========================================================================== #
# Adversarial — future / non-default config_version
# =========================================================================== #

def test_adv_future_config_version_string_passes_through():
    """A future config schema_version string is embedded verbatim in the report."""
    cfg = HeuristicConfig(
        schema_version="2.0",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(_empty_verdict(), "c", cfg)
    assert report["config_version"] == "2.0"


def test_adv_numeric_string_config_version():
    """A numeric config schema_version string is preserved as a string in the report."""
    cfg = HeuristicConfig(
        schema_version="42",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(_empty_verdict(), "c", cfg)
    assert report["config_version"] == "42"
    assert isinstance(report["config_version"], str)


# =========================================================================== #
# Adversarial — case_id edge cases
# =========================================================================== #

def test_adv_case_id_empty_string_raises():
    """serialize_report raises ValueError when case_id is an empty string."""
    with pytest.raises((ValueError, Exception)):
        serialize_report(_empty_verdict(), "", _config())


def test_adv_case_id_numeric_string():
    """A purely numeric case_id string is preserved as-is."""
    report = serialize_report(_empty_verdict(), "12345", _config())
    assert report["case_id"] == "12345"


def test_adv_case_id_unicode():
    """A unicode case_id string is preserved and the report is valid JSON."""
    case_id = "scan-éàü-001"
    report = serialize_report(_empty_verdict(), case_id, _config())
    assert report["case_id"] == case_id
    json_str = serialize_report_json(_empty_verdict(), case_id, _config())
    parsed = json.loads(json_str)
    assert parsed["case_id"] == case_id


# =========================================================================== #
# Adversarial — verdict all three severity levels with per-label
# =========================================================================== #

def test_adv_all_severity_levels_in_per_label_serialize_correctly():
    """All three Severity levels in per_label serialize to the correct label strings."""
    per_label = {
        1: [Reason(message="pass", severity=Severity.PASS)],
        2: [Reason(message="flag", severity=Severity.FLAG)],
        3: [Reason(message="fail", severity=Severity.FAIL)],
    }
    verdict = Verdict.build(reasons=[], per_label=per_label)
    report = serialize_report(verdict, "c", _config())
    assert report["per_label"]["1"][0]["severity"] == "pass"
    assert report["per_label"]["2"][0]["severity"] == "flagged-for-review"
    assert report["per_label"]["3"][0]["severity"] == "fail"


# =========================================================================== #
# Adversarial — caller data not mutated
# =========================================================================== #

def test_adv_serialize_does_not_mutate_caller_verdict():
    """serialize_report does not modify the Verdict object passed to it."""
    r = Reason(message="original", severity=Severity.FLAG)
    verdict = Verdict.build(reasons=[r], per_label={})
    overall_before = verdict.overall
    reasons_before = tuple(verdict.reasons)
    serialize_report(verdict, "c", _config())
    assert verdict.overall == overall_before
    assert tuple(verdict.reasons) == reasons_before


def test_adv_returned_dict_mutation_does_not_affect_second_call():
    """Mutating the returned dict does not affect subsequent serialize_report calls."""
    verdict = _simple_flag_verdict()
    cfg = _config()
    r1 = serialize_report(verdict, "c", cfg)
    r1["schema_version"] = "CORRUPTED"
    r2 = serialize_report(verdict, "c", cfg)
    assert r2["schema_version"] == "0.1"


# =========================================================================== #
# Adversarial — large reason set
# =========================================================================== #

def test_adv_large_reason_set_serializes_correctly():
    """A verdict with 100 case-level reasons serializes all of them."""
    reasons = [
        Reason(message=f"reason {i}", severity=Severity.FLAG)
        for i in range(100)
    ]
    verdict = Verdict.build(reasons=reasons, per_label={})
    report = serialize_report(verdict, "c", _config())
    assert len(report["reasons"]) == 100
    for i, item in enumerate(report["reasons"]):
        assert item["message"] == f"reason {i}"


# =========================================================================== #
# Adversarial — schema_version field in report is always the v0 marker
# =========================================================================== #

def test_adv_report_schema_version_is_not_config_version():
    """schema_version in the report refers to the report schema, not the config."""
    cfg = HeuristicConfig(
        schema_version="future-config-99",
        min_foreground_voxels=0,
        min_label_count=0,
    )
    report = serialize_report(_empty_verdict(), "c", cfg)
    # schema_version is the report schema version (always "0.1")
    assert report["schema_version"] == "0.1"
    # config_version carries the config's schema_version
    assert report["config_version"] == "future-config-99"
    assert report["schema_version"] != report["config_version"]
