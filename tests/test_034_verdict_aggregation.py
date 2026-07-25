"""Tests for the verdict-aggregation layer (item 034).

Covers all 22 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:      segfacet.aggregate public API (__all__ contents).
- AC2-AC5:  Severity-dominance verdict mapping (no findings / all-FLAG /
            mixed-with-FAIL / all-PASS).
- AC6-AC9:  Case-level vs per-vertebra attribution; message carried verbatim.
- AC10:     CaseResult bundles the derived verdict and full finding tuple.
- AC11-AC12: base_reasons / base_per_label merged, preceding finding-derived
            reasons; base FAIL still governs dominance.
- AC13:     Per-label attribution is ascending-label-sorted and deterministic
            regardless of frozenset iteration order.
- AC14-AC18: flag_escalation_count policy — default disabled, threshold met,
            below threshold, never fires on already-fail, config-driven
            end-to-end (same findings, different config -> different verdict).
- AC19:     aggregate_verdict does not mutate its inputs.
- AC20:     Deterministic output across repeated calls.
- AC21:     finding_to_reason field-by-field mapping.
- AC22:     HeuristicConfig.policy_param reads the 'verdict' config section.

Adversarial / edge-case scenarios included:
- Escalation boundary: exactly threshold fires (inclusive >=), one fewer does not.
- flag_escalation_count == 0 and negative are both treated as disabled.
- Empty per_label / empty reasons round-trip for the no-findings case.
- Mutating the caller's base_per_label after the call does not alter the
  returned verdict (independent-copy check beyond simple equality).
- A finding whose labels overlap an existing base_per_label bucket keeps base
  entries first, finding entries after, for that same label.
- policy_param on a HeuristicConfig built via load_config from a temp YAML,
  both with and without a 'verdict' section.
- build_case_result determinism (not just aggregate_verdict determinism).
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from segfacet.aggregate import (
    CaseResult,
    aggregate_verdict,
    build_case_result,
    finding_to_reason,
)
from segfacet.config import SUPPORTED_SCHEMA_VERSION, HeuristicConfig, default_config, load_config
from segfacet.heuristics.finding import Finding
from segfacet.verdict import Reason, Severity, Verdict

# Default convention integer labels (T12 == 19, L1 == 20, L2 == 21).
T12 = 19
L1 = 20
L2 = 21


# =========================================================================== #
# Helpers
# =========================================================================== #


def _finding(severity, labels=(), reason="a finding", rule_id="stub"):
    """Build a Finding from (severity, labels, reason) with a default rule_id."""
    return Finding(rule_id=rule_id, severity=severity, reason=reason, labels=frozenset(labels))


def _n_flag_findings(n, rule_id="stub"):
    """Build a list of n case-level Severity.FLAG findings."""
    return [
        _finding(Severity.FLAG, labels=(), reason=f"flag finding {i}", rule_id=rule_id)
        for i in range(n)
    ]


def _config_with_escalation(n):
    """Return a HeuristicConfig with verdict.flag_escalation_count == n."""
    defaults = dict(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        min_foreground_voxels=0,
        min_label_count=0,
    )
    return HeuristicConfig(**defaults, verdict={"flag_escalation_count": n})


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    """Write *content* to a YAML file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# =========================================================================== #
# AC1: public API
# =========================================================================== #


def test_ac1_aggregate_module_exposes_public_names():
    """AC1: segfacet.aggregate exposes all four public names via __all__."""
    import segfacet.aggregate as agg

    assert set(agg.__all__) == {
        "aggregate_verdict",
        "build_case_result",
        "CaseResult",
        "finding_to_reason",
    }
    for name in agg.__all__:
        assert hasattr(agg, name)


# =========================================================================== #
# AC2-AC5: severity-dominance verdict mapping
# =========================================================================== #


def test_ac2_no_findings_yields_pass():
    """AC2: aggregate_verdict([], default_config()) is PASS with empty reasons/per_label."""
    verdict = aggregate_verdict([], default_config())
    assert verdict.overall == Severity.PASS
    assert verdict.overall.label == "pass"
    assert verdict.reasons == ()
    assert verdict.per_label == {}


def test_ac3_only_flag_findings_yield_flagged_for_review():
    """AC3: All-FLAG findings under default_config() yield overall == FLAG."""
    findings = _n_flag_findings(3)
    verdict = aggregate_verdict(findings, default_config())
    assert verdict.overall == Severity.FLAG
    assert verdict.overall.label == "flagged-for-review"


def test_ac4_any_fail_finding_yields_fail():
    """AC4: A FAIL finding mixed with FLAG findings under default_config() yields FAIL."""
    findings = [
        _finding(Severity.FLAG, labels=(), reason="flag one"),
        _finding(Severity.FAIL, labels=(), reason="fail one"),
        _finding(Severity.FLAG, labels=(), reason="flag two"),
    ]
    verdict = aggregate_verdict(findings, default_config())
    assert verdict.overall == Severity.FAIL
    assert verdict.overall.label == "fail"


def test_ac5_all_pass_findings_yield_pass():
    """AC5: All-PASS findings under default_config() yield overall == PASS (no escalation)."""
    findings = [_finding(Severity.PASS, labels=(), reason=f"pass {i}") for i in range(5)]
    verdict = aggregate_verdict(findings, default_config())
    assert verdict.overall == Severity.PASS


# =========================================================================== #
# AC6-AC9: attribution and verbatim messages
# =========================================================================== #


def test_ac6_case_level_finding_becomes_case_level_reason():
    """AC6: A Finding with empty labels yields exactly one case-level reason."""
    f = _finding(Severity.FLAG, labels=(), reason="case-level flag")
    verdict = aggregate_verdict([f], default_config())
    assert len(verdict.reasons) == 1
    assert verdict.reasons[0].message == f.reason
    assert verdict.reasons[0].severity == f.severity
    assert verdict.per_label == {}


def test_ac7_single_label_finding_filed_under_its_label():
    """AC7: A Finding with labels=={L1} is filed under per_label[L1], no case-level reason."""
    f = _finding(Severity.FLAG, labels=(L1,), reason="single-label flag")
    verdict = aggregate_verdict([f], default_config())
    assert verdict.reasons == ()
    assert L1 in verdict.per_label
    assert len(verdict.per_label[L1]) == 1
    r = verdict.per_label[L1][0]
    assert r.message == f.reason
    assert r.severity == f.severity
    assert r.labels == frozenset({L1})


def test_ac8_multi_label_finding_attributed_to_every_label():
    """AC8: A Finding with labels=={L1, L2} appears under both buckets with full label set."""
    f = _finding(Severity.FAIL, labels=(L1, L2), reason="overlap pair")
    verdict = aggregate_verdict([f], default_config())
    assert L1 in verdict.per_label
    assert L2 in verdict.per_label
    for label in (L1, L2):
        assert len(verdict.per_label[label]) == 1
        r = verdict.per_label[label][0]
        assert r.labels == frozenset({L1, L2})


def test_ac9_reason_message_carried_verbatim():
    """AC9: The derived Reason.message equals the source finding.reason exactly."""
    text = "Vertebra L1 volume 12345 mm3 exceeds the configured maximum."
    f = _finding(Severity.FAIL, labels=(L1,), reason=text)
    verdict = aggregate_verdict([f], default_config())
    r = verdict.per_label[L1][0]
    assert r.message == text
    assert "stub" not in r.message  # no rule_id prefix injected


# =========================================================================== #
# AC10, AC21: CaseResult / finding_to_reason
# =========================================================================== #


def test_ac10_case_result_bundles_verdict_and_findings():
    """AC10: build_case_result bundles the derived verdict and the full finding tuple."""
    fs = [
        _finding(Severity.FLAG, labels=(), reason="a", rule_id="alpha"),
        _finding(Severity.FAIL, labels=(L1,), reason="b", rule_id="beta"),
    ]
    cfg = default_config()
    result = build_case_result(fs, cfg)
    assert isinstance(result, CaseResult)
    assert result.findings == tuple(fs)
    for original, stored in zip(fs, result.findings):
        assert stored.rule_id == original.rule_id
        assert stored.severity == original.severity
        assert stored.reason == original.reason
        assert stored.labels == original.labels
    assert result.verdict == aggregate_verdict(fs, cfg)


def test_ac21_finding_to_reason_maps_fields_faithfully():
    """AC21: finding_to_reason maps message/severity/labels from the Finding exactly."""
    f = Finding(rule_id="bounds", severity=Severity.FAIL, reason="too large", labels=frozenset({L1, L2}))
    r = finding_to_reason(f)
    assert isinstance(r, Reason)
    assert r.message == f.reason
    assert r.severity == f.severity
    assert r.labels == f.labels


# =========================================================================== #
# AC11-AC12: merge with base reasons/per_label
# =========================================================================== #


def test_ac11_base_reasons_merged_not_discarded():
    """AC11: A base FAIL reason survives merge alongside FLAG findings; overall stays FAIL."""
    base_reasons = [Reason(message="empty segmentation", severity=Severity.FAIL)]
    findings = _n_flag_findings(2)
    verdict = aggregate_verdict(findings, default_config(), base_reasons=base_reasons)
    assert verdict.overall == Severity.FAIL
    messages = [r.message for r in verdict.reasons]
    assert "empty segmentation" in messages
    for f in findings:
        assert f.reason in messages


def test_ac12_base_reasons_precede_finding_derived_reasons():
    """AC12: base_reasons appear first (input order), then finding-derived case-level reasons."""
    base_reasons = [
        Reason(message="base one", severity=Severity.FLAG),
        Reason(message="base two", severity=Severity.FLAG),
    ]
    findings = [
        _finding(Severity.FLAG, labels=(), reason="finding one"),
        _finding(Severity.FLAG, labels=(), reason="finding two"),
    ]
    verdict = aggregate_verdict(findings, default_config(), base_reasons=base_reasons)
    messages = [r.message for r in verdict.reasons]
    assert messages == ["base one", "base two", "finding one", "finding two"]


def test_ac12_base_per_label_precedes_finding_entries_for_shared_label():
    """AC12: For a label in both base_per_label and a finding, base entries come first."""
    base_reason = Reason(message="base per-label", severity=Severity.FLAG, labels=frozenset({L1}))
    base_per_label = {L1: [base_reason]}
    f = _finding(Severity.FLAG, labels=(L1,), reason="finding per-label")
    verdict = aggregate_verdict([f], default_config(), base_per_label=base_per_label)
    messages = [r.message for r in verdict.per_label[L1]]
    assert messages == ["base per-label", "finding per-label"]


# =========================================================================== #
# AC13: deterministic ascending-label attribution
# =========================================================================== #


def test_ac13_multi_label_attribution_is_ascending_label_sorted():
    """AC13: A finding with labels {21, 19, 20} populates buckets 19, 20, 21 (ascending)."""
    f = _finding(Severity.FLAG, labels=(L2, T12, L1), reason="mislabel span")
    verdict = aggregate_verdict([f], default_config())
    assert sorted(verdict.per_label.keys()) == [T12, L1, L2]
    for label in (T12, L1, L2):
        assert len(verdict.per_label[label]) == 1


def test_ac13_per_label_structure_independent_of_frozenset_iteration_order():
    """AC13: Repeated calls with an equivalent finding yield identical per_label structure."""
    f1 = _finding(Severity.FLAG, labels=(L2, T12, L1), reason="mislabel span")
    f2 = _finding(Severity.FLAG, labels=(T12, L1, L2), reason="mislabel span")
    v1 = aggregate_verdict([f1], default_config())
    v2 = aggregate_verdict([f2], default_config())
    assert v1.per_label.keys() == v2.per_label.keys()
    for label in v1.per_label:
        assert v1.per_label[label] == v2.per_label[label]


# =========================================================================== #
# AC14-AC18: flag_escalation_count policy
# =========================================================================== #


def test_ac14_default_policy_is_pure_dominance_no_escalation():
    """AC14: Ten FLAG findings under default_config() still yield FLAG (no escalation)."""
    findings = _n_flag_findings(10)
    verdict = aggregate_verdict(findings, default_config())
    assert verdict.overall == Severity.FLAG


def test_ac15_escalation_fires_at_threshold():
    """AC15: With flag_escalation_count==3 and exactly 3 FLAG findings, overall becomes FAIL."""
    cfg = _config_with_escalation(3)
    findings = _n_flag_findings(3)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FAIL
    assert any(
        r.severity == Severity.FAIL and "escalat" in r.message.lower()
        for r in verdict.reasons
    )


def test_ac16_below_threshold_stays_flagged_for_review():
    """AC16: With flag_escalation_count==3 and only 2 FLAG findings, no escalation occurs."""
    cfg = _config_with_escalation(3)
    findings = _n_flag_findings(2)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FLAG
    assert not any(r.severity == Severity.FAIL for r in verdict.reasons)


def test_ac17_escalation_never_fires_on_already_fail_dominance():
    """AC17: With flag_escalation_count==1 and a FAIL present, no synthetic escalation reason."""
    cfg = _config_with_escalation(1)
    findings = [
        _finding(Severity.FAIL, labels=(), reason="hard failure"),
        _finding(Severity.FLAG, labels=(), reason="a flag"),
    ]
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FAIL
    assert not any("escalat" in r.message.lower() for r in verdict.reasons)
    # Exactly the two original reasons -- nothing synthetic appended.
    assert len(verdict.reasons) == 2


def test_ac18_same_findings_flip_verdict_via_config_alone():
    """AC18: The same 3 FLAG findings yield FLAG under default_config() but FAIL under escalation."""
    findings = _n_flag_findings(3)
    verdict_default = aggregate_verdict(findings, default_config())
    verdict_escalated = aggregate_verdict(findings, _config_with_escalation(3))
    assert verdict_default.overall == Severity.FLAG
    assert verdict_escalated.overall == Severity.FAIL


# =========================================================================== #
# AC19: no input mutation
# =========================================================================== #


def test_ac19_findings_list_and_findings_unmutated():
    """AC19: The findings list and each Finding are unchanged after the call."""
    findings = [
        _finding(Severity.FLAG, labels=(L1,), reason="a", rule_id="alpha"),
        _finding(Severity.FAIL, labels=(), reason="b", rule_id="beta"),
    ]
    before = copy.deepcopy(findings)
    aggregate_verdict(findings, default_config())
    assert findings == before


def test_ac19_base_reasons_and_base_per_label_unmutated():
    """AC19: base_reasons sequence and base_per_label mapping (incl. inner lists) are unchanged."""
    base_reasons = [Reason(message="base", severity=Severity.FLAG)]
    base_per_label = {L1: [Reason(message="base label", severity=Severity.FLAG, labels=frozenset({L1}))]}
    base_reasons_before = copy.deepcopy(base_reasons)
    base_per_label_before = copy.deepcopy(base_per_label)
    findings = _n_flag_findings(1)
    aggregate_verdict(findings, default_config(), base_reasons=base_reasons, base_per_label=base_per_label)
    assert base_reasons == base_reasons_before
    assert base_per_label == base_per_label_before


def test_ac19_mutating_caller_base_per_label_after_call_does_not_alter_verdict():
    """AC19: Mutating the caller's base_per_label after the call leaves the returned verdict intact."""
    base_per_label = {L1: [Reason(message="base label", severity=Severity.FLAG, labels=frozenset({L1}))]}
    verdict = aggregate_verdict([], default_config(), base_per_label=base_per_label)
    snapshot = verdict.per_label[L1]
    base_per_label[L1].append(Reason(message="mutated in", severity=Severity.FAIL))
    base_per_label[99] = [Reason(message="new label", severity=Severity.FAIL)]
    assert verdict.per_label[L1] == snapshot
    assert 99 not in verdict.per_label


# =========================================================================== #
# AC20: determinism
# =========================================================================== #


def test_ac20_aggregate_verdict_is_deterministic():
    """AC20: Two aggregate_verdict calls on identical inputs return equal results."""
    findings = [
        _finding(Severity.FLAG, labels=(L1, L2), reason="a"),
        _finding(Severity.FAIL, labels=(), reason="b"),
    ]
    cfg = default_config()
    v1 = aggregate_verdict(findings, cfg)
    v2 = aggregate_verdict(findings, cfg)
    assert v1.overall == v2.overall
    assert v1.reasons == v2.reasons
    assert v1.per_label == v2.per_label


def test_ac20_build_case_result_is_deterministic():
    """AC20: Two build_case_result calls on identical inputs return equal results."""
    findings = [
        _finding(Severity.FLAG, labels=(L1,), reason="a"),
        _finding(Severity.PASS, labels=(), reason="b"),
    ]
    cfg = default_config()
    r1 = build_case_result(findings, cfg)
    r2 = build_case_result(findings, cfg)
    assert r1.verdict.overall == r2.verdict.overall
    assert r1.verdict.reasons == r2.verdict.reasons
    assert r1.verdict.per_label == r2.verdict.per_label
    assert r1.findings == r2.findings


# =========================================================================== #
# AC22: HeuristicConfig.policy_param
# =========================================================================== #


def test_ac22_policy_param_default_on_default_config():
    """AC22: default_config().policy_param('flag_escalation_count', 0) == 0."""
    assert default_config().policy_param("flag_escalation_count", 0) == 0


def test_ac22_policy_param_returns_configured_value():
    """AC22: A HeuristicConfig with verdict={'flag_escalation_count': 5} returns 5."""
    cfg = _config_with_escalation(5)
    assert cfg.policy_param("flag_escalation_count", 0) == 5


def test_ac22_policy_param_returns_default_for_absent_key():
    """AC22: An absent key returns the supplied default."""
    cfg = _config_with_escalation(5)
    assert cfg.policy_param("some_other_knob", "fallback") == "fallback"


def test_ac22_load_config_without_verdict_section_uses_default(tmp_path):
    """AC22: load_config on a YAML with no verdict section yields policy_param default 0."""
    p = _write_yaml(tmp_path, f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n")
    cfg = load_config(p)
    assert cfg.policy_param("flag_escalation_count", 0) == 0


def test_ac22_load_config_with_verdict_section_round_trips(tmp_path):
    """AC22: load_config on a YAML with a verdict section reads flag_escalation_count."""
    p = _write_yaml(tmp_path, (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "verdict:\n"
        "  flag_escalation_count: 5\n"
    ))
    cfg = load_config(p)
    assert cfg.policy_param("flag_escalation_count", 0) == 5


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_escalation_boundary_one_fewer_does_not_fire():
    """Adversarial: threshold - 1 FLAG findings does not escalate (exclusive below)."""
    cfg = _config_with_escalation(4)
    findings = _n_flag_findings(3)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FLAG


def test_adv_escalation_boundary_exact_threshold_fires():
    """Adversarial: exactly threshold FLAG findings fires (inclusive >=)."""
    cfg = _config_with_escalation(4)
    findings = _n_flag_findings(4)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FAIL


def test_adv_escalation_count_zero_disabled_even_with_many_flags():
    """Adversarial: flag_escalation_count == 0 never escalates, however many FLAG findings."""
    cfg = _config_with_escalation(0)
    findings = _n_flag_findings(50)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FLAG


def test_adv_escalation_count_negative_disabled():
    """Adversarial: a negative flag_escalation_count is treated as disabled."""
    cfg = _config_with_escalation(-1)
    findings = _n_flag_findings(10)
    verdict = aggregate_verdict(findings, cfg)
    assert verdict.overall == Severity.FLAG


def test_adv_empty_reasons_and_per_label_round_trip():
    """Adversarial: the no-findings, no-base verdict has reasons==() and per_label=={}."""
    verdict = aggregate_verdict([], default_config(), base_reasons=(), base_per_label=None)
    assert verdict.reasons == ()
    assert verdict.per_label == {}


def test_adv_case_result_findings_tuple_independent_of_input_list():
    """Adversarial: mutating the caller's findings list after the call doesn't change CaseResult.findings."""
    findings = [_finding(Severity.FLAG, labels=(), reason="a")]
    result = build_case_result(findings, default_config())
    findings.append(_finding(Severity.FAIL, labels=(), reason="b"))
    assert len(result.findings) == 1


def test_adv_finding_to_reason_preserves_empty_labels():
    """Adversarial: finding_to_reason on a case-level finding yields Reason with empty labels."""
    f = Finding(rule_id="r", severity=Severity.PASS, reason="ok", labels=frozenset())
    r = finding_to_reason(f)
    assert r.labels == frozenset()


def test_adv_multiple_findings_same_label_all_attributed():
    """Adversarial: two distinct findings on the same label both appear in that label's bucket."""
    f1 = _finding(Severity.FLAG, labels=(L1,), reason="first issue", rule_id="alpha")
    f2 = _finding(Severity.FAIL, labels=(L1,), reason="second issue", rule_id="beta")
    verdict = aggregate_verdict([f1, f2], default_config())
    messages = [r.message for r in verdict.per_label[L1]]
    assert messages == ["first issue", "second issue"]
    assert verdict.overall == Severity.FAIL


def test_adv_default_config_still_constructs_after_verdict_field_added():
    """Adversarial: default_config() still constructs cleanly (backward compat with new field)."""
    cfg = default_config()
    assert isinstance(cfg, HeuristicConfig)
    assert cfg.verdict == {}
