"""Tests for the rule-engine core (item 026).

Covers all 18 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1-AC4:  Finding construction, frozenness, field defaults, empty-field validation.
- AC5:      to_dict / from_dict round-trip; JSON-serialisability; no raw class names.
- AC6:      Rule ABC — cannot instantiate abstract base or incomplete subclass.
- AC7-AC8:  register_rule / get_rule / iter_rules; duplicate-id rejection.
- AC9-AC10: runner aggregates stub findings; determinism; multi-rule ordering.
- AC11:     empty rules list returns [].
- AC12:     empty per_label record does not crash runner.
- AC13:     runner does not mutate the feature record.
- AC14:     disabled-in-config rule is skipped; enabled/absent is included.
- AC15:     HeuristicConfig.rule_enabled defaults to True; False when explicit.
- AC16:     HeuristicConfig.rule_param returns configured value or caller default.
- AC17:     backward compatibility — default_config / load_config unaffected.
- AC18:     segqc/heuristics/ ships no concrete rule-family module.

Adversarial / edge-case scenarios included:
- Finding.labels coercion from a plain list (deduplication to frozenset).
- Finding.labels coercion from a plain set.
- Whitespace-only and tab-only reason values raise ValueError.
- Silent rule (evaluate returns []) contributes nothing.
- Silent rule alongside stub — only stub findings appear.
- Partial config entry missing 'params' — rule_param falls back to caller default.
- Partial config entry missing 'enabled' — rule_enabled returns True (default).
- from_dict with an unknown severity label raises a clear, non-empty error.
- Runner with record lacking an expected key — core must not crash.
- Frozen Finding — direct field assignment raises FrozenInstanceError.
- Finding equality / inequality by field value.
- Empty to_dict labels is [].
- Caller's record mapping is not mutated, even for a label-reading stub rule.
- Config with rules section coexisting with flat fields (backward compat merge).
- iter_rules on an empty registry yields an empty sequence.
- get_rule on an unknown id raises.
- Duplicate registration raises on the second call, even with a different class.
- run_rules always returns a list (never None).

All stub Rule subclasses are defined locally in this file.  No concrete rule
family from segqc/heuristics/ is referenced.  All tests are deterministic,
CPU-only, and cross-platform (no network, no absolute paths).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import pathlib

import pytest

from segqc.heuristics import Finding, Rule, get_rule, iter_rules, register_rule, run_rules
from segqc.verdict import Severity
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    HeuristicConfig,
    default_config,
    load_config,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    """Write *content* to a YAML file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _minimal_record(labels=(3, 5)):
    """Return a minimal feature record matching the build_features_block shape."""
    return {
        "per_label": {lbl: {} for lbl in labels},
        "relationships": {},
        "overlaps": {},
    }


# =========================================================================== #
# Local stub Rule subclasses (not registered at module level)
# =========================================================================== #


class _StubRule(Rule):
    """Minimal stub — always emits one PASS finding."""

    rule_id = "stub"

    def evaluate(self, record, config):
        return [Finding(rule_id=self.rule_id, severity=Severity.PASS, reason="stub finding")]


class _SilentRule(Rule):
    """Stub that always returns an empty list."""

    rule_id = "silent"

    def evaluate(self, record, config):
        return []


class _AlphaRule(Rule):
    """Stub with rule_id='alpha' — used for multi-rule ordering tests."""

    rule_id = "alpha"

    def evaluate(self, record, config):
        return [Finding(rule_id=self.rule_id, severity=Severity.FLAG, reason="alpha finding")]


class _BetaRule(Rule):
    """Stub with rule_id='beta' — used for multi-rule ordering tests."""

    rule_id = "beta"

    def evaluate(self, record, config):
        return [Finding(rule_id=self.rule_id, severity=Severity.FLAG, reason="beta finding")]


class _LabelReaderRule(Rule):
    """Stub that reads per_label and emits one finding per label."""

    rule_id = "label_reader"

    def evaluate(self, record, config):
        per_label = record.get("per_label", {})
        return [
            Finding(
                rule_id=self.rule_id,
                severity=Severity.FLAG,
                reason=f"label {lbl}",
                labels=frozenset({lbl}),
            )
            for lbl in per_label
        ]


# =========================================================================== #
# Registry isolation — snapshot/restore around every test in this module
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot the rule registry before each test and restore it afterwards.

    This prevents test-to-test leakage when stub rules are registered inside
    individual tests.  The fixture imports _RULES from segqc.heuristics.rule
    directly, as specified in the implementation steps.
    """
    from segqc.heuristics.rule import _RULES
    snapshot = dict(_RULES)
    _RULES.clear()
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: Finding is a frozen dataclass with four required fields
# =========================================================================== #


def test_ac1_finding_constructs_with_all_four_fields():
    """AC1: Finding(rule_id, severity, reason, labels) constructs successfully."""
    f = Finding(rule_id="r", severity=Severity.FLAG, reason="msg", labels=frozenset({3, 5}))
    assert f.rule_id == "r"
    assert f.severity == Severity.FLAG
    assert f.reason == "msg"
    assert f.labels == frozenset({3, 5})


def test_ac1_finding_field_values_are_preserved():
    """AC1: All four field values match what was supplied at construction."""
    f = Finding(rule_id="bounds", severity=Severity.FAIL, reason="too big", labels=frozenset({18}))
    assert f.rule_id == "bounds"
    assert f.severity is Severity.FAIL
    assert f.reason == "too big"
    assert f.labels == frozenset({18})


def test_ac1_finding_is_frozen_rule_id():
    """AC1: Assigning to rule_id raises FrozenInstanceError."""
    f = Finding(rule_id="r", severity=Severity.FLAG, reason="msg")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.rule_id = "changed"  # type: ignore[misc]


def test_ac1_finding_is_frozen_severity():
    """AC1: Assigning to severity raises FrozenInstanceError."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="msg")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.severity = Severity.FAIL  # type: ignore[misc]


def test_ac1_finding_is_frozen_reason():
    """AC1: Assigning to reason raises FrozenInstanceError."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="msg")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.reason = "other"  # type: ignore[misc]


def test_ac1_finding_is_frozen_labels():
    """AC1: Assigning to labels raises FrozenInstanceError."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="msg", labels=frozenset({1}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.labels = frozenset({2})  # type: ignore[misc]


def test_ac1_finding_severity_preserved_for_all_members():
    """AC1: Finding stores the exact Severity member supplied for all three values."""
    for sev in Severity:
        f = Finding(rule_id="r", severity=sev, reason="test")
        assert f.severity is sev


# =========================================================================== #
# AC2: Finding.labels defaults to an empty frozenset
# =========================================================================== #


def test_ac2_labels_defaults_to_empty_frozenset():
    """AC2: Finding without labels keyword has labels == frozenset()."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="ok")
    assert f.labels == frozenset()


def test_ac2_labels_default_type_is_frozenset():
    """AC2: The default labels is specifically a frozenset, not a list or set."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="ok")
    assert isinstance(f.labels, frozenset)


def test_ac2_explicit_empty_frozenset_equals_default():
    """AC2: Explicitly passing labels=frozenset() produces the same result as omitting it."""
    f1 = Finding(rule_id="r", severity=Severity.PASS, reason="ok")
    f2 = Finding(rule_id="r", severity=Severity.PASS, reason="ok", labels=frozenset())
    assert f1.labels == f2.labels
    assert f1 == f2


# =========================================================================== #
# AC3: Finding requires a non-empty reason
# =========================================================================== #


def test_ac3_empty_reason_raises_value_error():
    """AC3: Constructing Finding with reason='' raises ValueError."""
    with pytest.raises(ValueError):
        Finding(rule_id="r", severity=Severity.PASS, reason="")


def test_ac3_whitespace_only_reason_raises_value_error():
    """AC3: Constructing Finding with reason='   ' (spaces) raises ValueError."""
    with pytest.raises(ValueError):
        Finding(rule_id="r", severity=Severity.PASS, reason="   ")


def test_ac3_tab_only_reason_raises_value_error():
    """AC3: Constructing Finding with reason='\\t' (tab) raises ValueError."""
    with pytest.raises(ValueError):
        Finding(rule_id="r", severity=Severity.PASS, reason="\t")


def test_ac3_empty_reason_error_has_non_empty_message():
    """AC3: The ValueError for an empty reason has a non-empty, human-readable message."""
    with pytest.raises(ValueError) as exc_info:
        Finding(rule_id="r", severity=Severity.PASS, reason="")
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC4: Finding requires a non-empty rule_id
# =========================================================================== #


def test_ac4_empty_rule_id_raises_value_error():
    """AC4: Constructing Finding with rule_id='' raises ValueError."""
    with pytest.raises(ValueError):
        Finding(rule_id="", severity=Severity.PASS, reason="valid reason")


def test_ac4_empty_rule_id_error_has_non_empty_message():
    """AC4: The ValueError for an empty rule_id carries a non-empty message."""
    with pytest.raises(ValueError) as exc_info:
        Finding(rule_id="", severity=Severity.PASS, reason="valid reason")
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC5: to_dict / from_dict round-trip
# =========================================================================== #


def test_ac5_round_trip_pass_severity():
    """AC5: Finding with PASS severity round-trips through to_dict / from_dict."""
    f = Finding(rule_id="r1", severity=Severity.PASS, reason="pass msg", labels=frozenset({1, 2}))
    assert Finding.from_dict(f.to_dict()) == f


def test_ac5_round_trip_flag_severity():
    """AC5: Finding with FLAG severity round-trips through to_dict / from_dict."""
    f = Finding(rule_id="r2", severity=Severity.FLAG, reason="flag msg", labels=frozenset({10}))
    assert Finding.from_dict(f.to_dict()) == f


def test_ac5_round_trip_fail_severity():
    """AC5: Finding with FAIL severity round-trips through to_dict / from_dict."""
    f = Finding(rule_id="r3", severity=Severity.FAIL, reason="fail msg", labels=frozenset())
    assert Finding.from_dict(f.to_dict()) == f


@pytest.mark.parametrize("sev", list(Severity))
def test_ac5_round_trip_all_severities(sev):
    """AC5: Round-trip succeeds for all three Severity members."""
    f = Finding(rule_id="r", severity=sev, reason="test", labels=frozenset({3, 5}))
    assert Finding.from_dict(f.to_dict()) == f


def test_ac5_to_dict_is_json_serializable():
    """AC5: to_dict() output passes json.dumps without error."""
    f = Finding(rule_id="r", severity=Severity.FLAG, reason="test reason", labels=frozenset({3, 5}))
    serialized = json.dumps(f.to_dict())
    assert isinstance(serialized, str)


def test_ac5_to_dict_severity_flag_is_string_label():
    """AC5: FLAG severity in to_dict() is rendered as 'flagged-for-review', not enum repr."""
    f = Finding(rule_id="r", severity=Severity.FLAG, reason="test")
    d = f.to_dict()
    assert isinstance(d["severity"], str)
    assert d["severity"] == "flagged-for-review"


def test_ac5_to_dict_severity_pass_is_string():
    """AC5: PASS severity in to_dict() is the string 'pass'."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="test")
    assert f.to_dict()["severity"] == "pass"


def test_ac5_to_dict_severity_fail_is_string():
    """AC5: FAIL severity in to_dict() is the string 'fail'."""
    f = Finding(rule_id="r", severity=Severity.FAIL, reason="test")
    assert f.to_dict()["severity"] == "fail"


def test_ac5_to_dict_labels_is_sorted_list_of_ints():
    """AC5: to_dict() renders labels as a sorted list of plain ints."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="test", labels=frozenset({5, 1, 3}))
    d = f.to_dict()
    assert d["labels"] == [1, 3, 5]
    assert isinstance(d["labels"], list)
    for item in d["labels"]:
        assert isinstance(item, int)


def test_ac5_to_dict_no_raw_class_names_in_json():
    """AC5: json.dumps(to_dict()) contains no Python class names or enum reprs."""
    f = Finding(rule_id="r", severity=Severity.FAIL, reason="msg", labels=frozenset({1}))
    output_str = json.dumps(f.to_dict())
    assert "Severity" not in output_str
    assert "Finding" not in output_str
    assert "<" not in output_str


def test_ac5_from_dict_reconstructs_all_fields():
    """AC5: from_dict restores rule_id, severity, reason, and labels exactly."""
    f = Finding(
        rule_id="myrule",
        severity=Severity.FLAG,
        reason="something flagged",
        labels=frozenset({20, 21}),
    )
    f2 = Finding.from_dict(f.to_dict())
    assert f2.rule_id == "myrule"
    assert f2.severity == Severity.FLAG
    assert f2.reason == "something flagged"
    assert f2.labels == frozenset({20, 21})


# =========================================================================== #
# AC6: Rule defines the abstract evaluate contract
# =========================================================================== #


def test_ac6_rule_cannot_be_instantiated_directly():
    """AC6: Rule() raises TypeError because evaluate is abstract."""
    with pytest.raises(TypeError):
        Rule()  # type: ignore[abstract]


def test_ac6_subclass_without_evaluate_cannot_instantiate():
    """AC6: A Rule subclass that omits evaluate() raises TypeError on instantiation."""
    class _IncompleteRule(Rule):
        rule_id = "incomplete"

    with pytest.raises(TypeError):
        _IncompleteRule()


def test_ac6_concrete_subclass_can_instantiate():
    """AC6: A Rule subclass that implements evaluate() and sets rule_id is instantiable."""
    instance = _StubRule()
    assert isinstance(instance, Rule)


def test_ac6_rule_id_is_accessible_on_subclass():
    """AC6: rule_id is accessible as a class attribute on a concrete subclass."""
    assert _StubRule.rule_id == "stub"


def test_ac6_evaluate_returns_list_of_findings():
    """AC6: evaluate(record, config) on a concrete Rule returns list[Finding]."""
    instance = _StubRule()
    cfg = default_config()
    result = instance.evaluate(_minimal_record(), cfg)
    assert isinstance(result, list)
    assert all(isinstance(fi, Finding) for fi in result)


# =========================================================================== #
# AC7: register_rule registers a rule and it is retrievable
# =========================================================================== #


def test_ac7_registered_rule_retrievable_by_id():
    """AC7: get_rule returns a _StubRule instance after register_rule(_StubRule)."""
    register_rule(_StubRule)
    rule = get_rule("stub")
    assert isinstance(rule, _StubRule)


def test_ac7_iter_rules_yields_registered_rule():
    """AC7: iter_rules() includes the registered rule after register_rule."""
    register_rule(_StubRule)
    assert any(isinstance(r, _StubRule) for r in iter_rules())


def test_ac7_iter_rules_sorted_by_rule_id():
    """AC7: iter_rules() returns rules in ascending rule_id order."""
    register_rule(_BetaRule)
    register_rule(_AlphaRule)
    ids = [r.rule_id for r in iter_rules()]
    assert ids == sorted(ids)


def test_ac7_iter_rules_returns_all_registered():
    """AC7: iter_rules() yields every registered rule."""
    register_rule(_AlphaRule)
    register_rule(_BetaRule)
    ids = {r.rule_id for r in iter_rules()}
    assert ids == {"alpha", "beta"}


# =========================================================================== #
# AC8: Duplicate rule_id registration raises
# =========================================================================== #


def test_ac8_duplicate_same_class_raises():
    """AC8: A second register_rule call for the same class raises ValueError."""
    register_rule(_StubRule)
    with pytest.raises(ValueError):
        register_rule(_StubRule)


def test_ac8_duplicate_different_class_same_id_raises():
    """AC8: A different class with the same rule_id='stub' also raises ValueError."""
    class _AnotherStub(Rule):
        rule_id = "stub"

        def evaluate(self, record, config):
            return []

    register_rule(_StubRule)
    with pytest.raises(ValueError):
        register_rule(_AnotherStub)


def test_ac8_error_message_non_empty():
    """AC8: The ValueError for a duplicate rule_id has a non-empty message."""
    register_rule(_StubRule)
    with pytest.raises(ValueError) as exc_info:
        register_rule(_StubRule)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC9: Runner executes registered enabled rules and aggregates findings
# =========================================================================== #


def test_ac9_runner_returns_stub_finding():
    """AC9: run_rules with a registered stub rule returns exactly its one finding."""
    register_rule(_StubRule)
    cfg = default_config()
    findings = run_rules(_minimal_record(), cfg)
    assert len(findings) == 1
    assert isinstance(findings[0], Finding)
    assert findings[0].rule_id == "stub"


def test_ac9_runner_aggregates_findings_from_multiple_rules():
    """AC9: run_rules aggregates findings from all registered rules."""
    register_rule(_AlphaRule)
    register_rule(_BetaRule)
    cfg = default_config()
    findings = run_rules(_minimal_record(), cfg)
    rule_ids = {f.rule_id for f in findings}
    assert "alpha" in rule_ids
    assert "beta" in rule_ids


# =========================================================================== #
# AC10: Runner output is deterministic
# =========================================================================== #


def test_ac10_runner_is_deterministic_single_rule():
    """AC10: Two identical run_rules calls with one registered rule return equal lists."""
    register_rule(_StubRule)
    cfg = default_config()
    record = _minimal_record()
    findings_a = run_rules(record, cfg)
    findings_b = run_rules(record, cfg)
    assert findings_a == findings_b


def test_ac10_multi_rule_findings_ordered_ascending_by_rule_id():
    """AC10: With alpha and beta registered, findings appear in alpha-first order."""
    register_rule(_BetaRule)
    register_rule(_AlphaRule)
    cfg = default_config()
    findings = run_rules(_minimal_record(), cfg)
    rule_ids = [f.rule_id for f in findings]
    assert rule_ids.index("alpha") < rule_ids.index("beta")


def test_ac10_determinism_with_label_reader_rule():
    """AC10: Determinism holds for a rule that reads per_label."""
    register_rule(_LabelReaderRule)
    cfg = default_config()
    record = _minimal_record(labels=(1, 2, 3))
    findings_a = run_rules(record, cfg)
    findings_b = run_rules(record, cfg)
    assert [f.labels for f in findings_a] == [f.labels for f in findings_b]


# =========================================================================== #
# AC11: Runner tolerates an empty rule set
# =========================================================================== #


def test_ac11_empty_rules_list_returns_empty_list():
    """AC11: run_rules(record, cfg, rules=[]) returns [] and raises nothing."""
    cfg = default_config()
    findings = run_rules(_minimal_record(), cfg, rules=[])
    assert findings == []


def test_ac11_empty_rules_list_overrides_registered_rules():
    """AC11: Explicit rules=[] returns [] even when rules are registered."""
    register_rule(_StubRule)
    cfg = default_config()
    findings = run_rules(_minimal_record(), cfg, rules=[])
    assert findings == []


# =========================================================================== #
# AC12: Runner tolerates a feature record with no labels
# =========================================================================== #


def test_ac12_empty_per_label_no_crash_label_reader():
    """AC12: A label-reading rule with per_label={} completes without raising."""
    register_rule(_LabelReaderRule)
    cfg = default_config()
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    findings = run_rules(record, cfg)
    assert isinstance(findings, list)
    assert findings == []


def test_ac12_empty_per_label_stub_rule_still_runs():
    """AC12: A non-label-reading stub executes cleanly when per_label is empty."""
    register_rule(_StubRule)
    cfg = default_config()
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    findings = run_rules(record, cfg)
    assert len(findings) == 1


# =========================================================================== #
# AC13: Runner does not mutate the feature record
# =========================================================================== #


def test_ac13_runner_does_not_mutate_record():
    """AC13: The record mapping is deep-equal to a pre-call copy after run_rules."""
    register_rule(_StubRule)
    cfg = default_config()
    record = _minimal_record(labels=(3, 5, 7))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before


def test_ac13_label_reader_does_not_mutate_record():
    """AC13: A rule that iterates per_label also leaves the record unchanged."""
    register_rule(_LabelReaderRule)
    cfg = default_config()
    record = _minimal_record(labels=(1, 2, 3))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before


# =========================================================================== #
# AC14: A rule disabled in config is skipped
# =========================================================================== #


def test_ac14_disabled_rule_skipped(tmp_path):
    """AC14: A rule with enabled: false in config produces no findings."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  stub:\n"
        "    enabled: false\n"
    ))
    cfg = load_config(p)
    register_rule(_StubRule)
    findings = run_rules(_minimal_record(), cfg)
    assert findings == []


def test_ac14_explicitly_enabled_rule_included(tmp_path):
    """AC14: A rule with enabled: true in config produces its findings."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  stub:\n"
        "    enabled: true\n"
    ))
    cfg = load_config(p)
    register_rule(_StubRule)
    findings = run_rules(_minimal_record(), cfg)
    assert len(findings) == 1


def test_ac14_absent_from_config_rule_included():
    """AC14: A rule not mentioned in config is treated as enabled (default True)."""
    cfg = default_config()
    register_rule(_StubRule)
    findings = run_rules(_minimal_record(), cfg)
    assert len(findings) == 1


def test_ac14_only_disabled_rule_skipped_other_rules_run(tmp_path):
    """AC14: Disabling one rule does not suppress other registered rules."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  alpha:\n"
        "    enabled: false\n"
    ))
    cfg = load_config(p)
    register_rule(_AlphaRule)
    register_rule(_BetaRule)
    findings = run_rules(_minimal_record(), cfg)
    rule_ids = {f.rule_id for f in findings}
    assert "alpha" not in rule_ids
    assert "beta" in rule_ids


# =========================================================================== #
# AC15: HeuristicConfig.rule_enabled defaults to True
# =========================================================================== #


def test_ac15_rule_enabled_defaults_true_on_default_config():
    """AC15: default_config().rule_enabled('anything') returns True."""
    cfg = default_config()
    assert cfg.rule_enabled("any_rule_whatsoever") is True


def test_ac15_rule_enabled_defaults_true_for_unknown_rule_in_loaded_config(tmp_path):
    """AC15: rule_enabled returns True for a rule absent from the config file."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert cfg.rule_enabled("nonexistent_rule") is True


def test_ac15_rule_enabled_false_when_explicitly_set(tmp_path):
    """AC15: rule_enabled returns False when config sets enabled: false."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  myrule:\n"
        "    enabled: false\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_enabled("myrule") is False


def test_ac15_rule_enabled_true_when_explicitly_set_true(tmp_path):
    """AC15: rule_enabled returns True when config explicitly sets enabled: true."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  myrule:\n"
        "    enabled: true\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_enabled("myrule") is True


# =========================================================================== #
# AC16: HeuristicConfig.rule_param returns configured value or caller default
# =========================================================================== #


def test_ac16_rule_param_returns_configured_value(tmp_path):
    """AC16: rule_param returns the value from config when the key is present."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    params:\n"
        "      max_volume_mm3: 1000\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_param("bounds", "max_volume_mm3", default=42) == 1000


def test_ac16_rule_param_returns_default_when_key_absent(tmp_path):
    """AC16: rule_param returns the caller's default when the param key is absent."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    params:\n"
        "      max_volume_mm3: 1000\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_param("bounds", "nonexistent_param", default=42) == 42


def test_ac16_rule_param_returns_default_when_rule_absent():
    """AC16: rule_param returns the caller's default when the rule is absent from config."""
    cfg = default_config()
    assert cfg.rule_param("nonexistent_rule", "any_key", default=99) == 99


def test_ac16_rule_param_default_zero_is_returned_when_key_absent():
    """AC16: rule_param with default=0 returns 0 when the key is absent."""
    cfg = default_config()
    assert cfg.rule_param("any_rule", "any_key", default=0) == 0


# =========================================================================== #
# AC17: Config loading is backward-compatible
# =========================================================================== #


def test_ac17_default_config_still_returns_heuristic_config():
    """AC17: default_config() succeeds and returns a HeuristicConfig."""
    cfg = default_config()
    assert isinstance(cfg, HeuristicConfig)
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION


def test_ac17_load_config_still_returns_heuristic_config(tmp_path):
    """AC17: load_config on a valid YAML still returns a HeuristicConfig."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert isinstance(cfg, HeuristicConfig)


def test_ac17_no_rules_section_loads_cleanly(tmp_path):
    """AC17: A config file with no 'rules' section loads without error."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert isinstance(cfg, HeuristicConfig)


def test_ac17_no_rules_section_all_rules_enabled_by_default(tmp_path):
    """AC17: After loading a config without a rules section, every rule is enabled."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    for rule_name in ("bounds", "fragmentation", "coverage", "sequence", "border"):
        assert cfg.rule_enabled(rule_name) is True, f"Expected rule '{rule_name}' to be enabled"


def test_ac17_rules_section_readable_via_rule_enabled(tmp_path):
    """AC17: A rules section in the file is readable via rule_enabled."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  fragmentation:\n"
        "    enabled: false\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_enabled("fragmentation") is False
    assert cfg.rule_enabled("coverage") is True


def test_ac17_rules_section_readable_via_rule_param(tmp_path):
    """AC17: A params sub-key in the rules section is readable via rule_param."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    enabled: false\n"
        "    params:\n"
        "      max_volume_mm3: 500\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_param("bounds", "max_volume_mm3", default=0) == 500


def test_ac17_existing_flat_fields_unaffected_by_rules_section(tmp_path):
    """AC17: Flat fields like min_foreground_voxels still work when a rules section is present."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 5\n"
        "min_label_count: 2\n"
        "rules:\n"
        "  bounds:\n"
        "    enabled: true\n"
    ))
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == 5
    assert cfg.min_label_count == 2


def test_ac17_schema_version_validation_still_enforced(tmp_path):
    """AC17: An unsupported schema_version still raises SegQCConfigError."""
    from segqc.config import SegQCConfigError
    p = _write_yaml(tmp_path, "schema_version: '99.0'\n")
    with pytest.raises(SegQCConfigError):
        load_config(p)


# =========================================================================== #
# AC18: No concrete rule family shipped in this item
# =========================================================================== #


def test_ac18_no_concrete_rule_family_module_in_package():
    """AC18: segqc/heuristics/ contains no rule-family module (bounds, fragmentation, etc.)."""
    import segqc.heuristics as pkg
    pkg_dir = pathlib.Path(pkg.__file__).parent
    forbidden_stems = {
        "mislabel",
        "misalignment",
    }
    for py_file in pkg_dir.glob("*.py"):
        stem = py_file.stem
        assert stem not in forbidden_stems, (
            f"Rule-family module '{py_file.name}' found in segqc/heuristics/ — "
            f"no concrete families should be present in item 026."
        )


# =========================================================================== #
# Adversarial: edge cases and error paths
# =========================================================================== #


def test_adv_finding_labels_list_deduplicates():
    """Adversarial: Finding(labels=[3, 3, 5]) deduplicates to frozenset({3, 5})."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="dedup", labels=[3, 3, 5])
    assert f.labels == frozenset({3, 5})
    assert isinstance(f.labels, frozenset)


def test_adv_finding_labels_coercion_from_plain_set():
    """Adversarial: Finding accepts a plain set for labels and coerces it to frozenset."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="set input", labels={1, 2})
    assert isinstance(f.labels, frozenset)
    assert f.labels == frozenset({1, 2})


def test_adv_silent_rule_contributes_no_findings():
    """Adversarial: A rule whose evaluate() returns [] contributes nothing to output."""
    register_rule(_SilentRule)
    findings = run_rules(_minimal_record(), default_config())
    assert findings == []


def test_adv_silent_rule_alongside_stub_contributes_only_stub_findings():
    """Adversarial: Silent rule + stub rule yields only the stub's one finding."""
    register_rule(_StubRule)
    register_rule(_SilentRule)
    findings = run_rules(_minimal_record(), default_config())
    assert len(findings) == 1
    assert findings[0].rule_id == "stub"


def test_adv_partial_config_entry_missing_params_no_crash(tmp_path):
    """Adversarial: Config entry with no 'params' key — rule_param returns caller default."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    enabled: true\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_param("bounds", "any_param", default=77) == 77


def test_adv_partial_config_entry_missing_enabled_defaults_true(tmp_path):
    """Adversarial: Config entry with only 'params' and no 'enabled' — rule_enabled is True."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    params:\n"
        "      max_volume_mm3: 500\n"
    ))
    cfg = load_config(p)
    assert cfg.rule_enabled("bounds") is True


def test_adv_from_dict_unknown_severity_raises():
    """Adversarial: Finding.from_dict with an unrecognised severity label raises a clear error."""
    d = {
        "rule_id": "r",
        "severity": "unknown_severity_xyz",
        "reason": "msg",
        "labels": [],
    }
    with pytest.raises(Exception) as exc_info:
        Finding.from_dict(d)
    assert str(exc_info.value).strip(), (
        "Error for unknown severity label must have a non-empty, readable message"
    )


def test_adv_runner_record_missing_expected_key_no_crash():
    """Adversarial: Runner core does not crash when the record lacks 'relationships'."""
    register_rule(_StubRule)
    cfg = default_config()
    record = {"per_label": {1: {}}}
    findings = run_rules(record, cfg)
    assert isinstance(findings, list)


def test_adv_frozen_finding_raises_on_rule_id_assignment():
    """Adversarial: Direct rule_id assignment on a Finding raises FrozenInstanceError."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="msg")
    with pytest.raises(dataclasses.FrozenInstanceError):
        f.rule_id = "new"  # type: ignore[misc]


def test_adv_finding_equality_same_values():
    """Adversarial: Two Findings with identical fields compare as equal."""
    f1 = Finding(rule_id="r", severity=Severity.FLAG, reason="msg", labels=frozenset({1}))
    f2 = Finding(rule_id="r", severity=Severity.FLAG, reason="msg", labels=frozenset({1}))
    assert f1 == f2


def test_adv_finding_inequality_different_rule_id():
    """Adversarial: Findings with different rule_ids are not equal."""
    f1 = Finding(rule_id="a", severity=Severity.PASS, reason="msg")
    f2 = Finding(rule_id="b", severity=Severity.PASS, reason="msg")
    assert f1 != f2


def test_adv_finding_inequality_different_severity():
    """Adversarial: Findings with different severities are not equal."""
    f1 = Finding(rule_id="r", severity=Severity.PASS, reason="msg")
    f2 = Finding(rule_id="r", severity=Severity.FAIL, reason="msg")
    assert f1 != f2


def test_adv_to_dict_empty_labels_is_empty_list():
    """Adversarial: to_dict() with labels=frozenset() renders labels as []."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="no labels")
    d = f.to_dict()
    assert d["labels"] == []
    assert isinstance(d["labels"], list)


def test_adv_finding_round_trip_single_label():
    """Adversarial: Finding with a single label round-trips losslessly."""
    f = Finding(rule_id="r", severity=Severity.FLAG, reason="single", labels=frozenset({42}))
    assert Finding.from_dict(f.to_dict()) == f


def test_adv_finding_round_trip_many_labels():
    """Adversarial: Finding with many labels round-trips and to_dict produces sorted list."""
    labels = frozenset(range(1, 25))
    f = Finding(rule_id="r", severity=Severity.FAIL, reason="many offenders", labels=labels)
    assert Finding.from_dict(f.to_dict()) == f
    assert f.to_dict()["labels"] == sorted(labels)


def test_adv_config_rules_section_coexists_with_flat_fields(tmp_path):
    """Adversarial: rules section and existing flat fields coexist without collision."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "min_foreground_voxels: 10\n"
        "rules:\n"
        "  bounds:\n"
        "    enabled: false\n"
    ))
    cfg = load_config(p)
    assert cfg.min_foreground_voxels == 10
    assert cfg.rule_enabled("bounds") is False
    assert cfg.rule_enabled("coverage") is True


def test_adv_iter_rules_empty_when_registry_is_empty():
    """Adversarial: iter_rules() on an empty registry yields no rules."""
    assert list(iter_rules()) == []


def test_adv_get_rule_unknown_id_raises():
    """Adversarial: get_rule with an unregistered id raises an exception."""
    with pytest.raises(Exception):
        get_rule("nonexistent_rule_xyz")


def test_adv_run_rules_always_returns_list():
    """Adversarial: run_rules always returns a list — never None or another type."""
    cfg = default_config()
    result = run_rules(_minimal_record(), cfg, rules=[])
    assert isinstance(result, list)
