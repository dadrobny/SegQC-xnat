"""Tests for item 064 -- level-aware intensity delta-to-reference rule
(``src/segqc/heuristics/intensity_reference_delta.py``).

Covers Acceptance Criteria AC12-AC26 (Group B/C -- the rule half):

- AC12: the rule is registered and discoverable.
- AC13: an in-distribution intensity produces no finding.
- AC14: an out-of-range intensity feature fires an out-of-range finding.
- AC15: a large robust-z fires a robust-z finding.
- AC16: a large distribution-distance fires a label-level finding.
- AC17: the robust-z threshold is read from config.
- AC18: the distribution-distance threshold is read from config.
- AC19: each firing condition is independently toggleable.
- AC20: severity is configurable and an unknown string raises.
- AC21: an absent/non-mapping block is silent, and an available: false
  label produces no finding.
- AC22: a reference lacking intensity distributions makes the rule inert.
- AC23: the reason cites the reference and is explainable.
- AC24: the rule is deterministic, non-mutating, and orders findings
  deterministically.
- AC25: findings flow through run_rules and verdict aggregation.
- AC26: adding the rule does not perturb existing pipeline output.

Adversarial / edge-case scenarios included:
- Empty per_label block.
- Malformed entries (non-dict label entry, missing features, non-list
  out_of_range_features, null robust_z).
- Value exactly on the robust-z / distribution-distance thresholds.
- available: false mixed with available: true (positive control).
- All three conditions firing on one label, in fixed order.
- Determinism / non-mutation via deep-copy comparison.
- Runner + aggregation integration, plus a disabled rule being skipped.
- Golden safety: no intensity_reference_delta key -> full default registry
  unaffected, and default_config.yaml is unmodified.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segqc.heuristics.intensity_reference_delta  # noqa: F401 — triggers IntensityReferenceDeltaRule registration
from segqc.aggregate import build_case_result
from segqc.config import SUPPORTED_SCHEMA_VERSION, default_config, load_config
from segqc.heuristics import Rule, get_rule, iter_rules, run_rules
from segqc.heuristics.intensity_reference_delta import IntensityReferenceDeltaRule
from segqc.heuristics.rule import _RULES
from segqc.verdict import Severity


# =========================================================================== #
# Helpers
# =========================================================================== #

_OUT_OF_RANGE_TAG = "Level-aware intensity out-of-range:"
_ROBUST_Z_TAG = "Level-aware intensity robust-z outlier:"
_DISTANCE_TAG = "Level-aware intensity distribution-distance outlier:"

_LABEL_L1 = 20
_LABEL_L2 = 23


def _feature(
    value=200.0,
    z_score=0.0,
    robust_z=0.0,
    percentile_rank=50.0,
    out_of_range=False,
):
    return {
        "value": value,
        "z_score": z_score,
        "robust_z": robust_z,
        "percentile_rank": percentile_rank,
        "out_of_range": out_of_range,
    }


def _label_entry(
    label,
    level_name="L1",
    available=True,
    distribution_distance=1.0,
    out_of_range_features=None,
    features=None,
):
    return {
        "label": label,
        "level_name": level_name,
        "available": available,
        "distribution_distance": distribution_distance,
        "out_of_range_features": list(out_of_range_features or []),
        "features": dict(features or {}),
    }


def _block(entries, lower_pct=1, upper_pct=99, stratum="all"):
    """``entries`` is a list of label-entry dicts (as from _label_entry),
    keyed by str(label) as reference_delta_to_dict shapes it (item 046,
    reused verbatim by item 064's compute function)."""
    per_label = {str(e["label"]): e for e in entries}
    return {
        "reference_delta_version": "1.0",
        "stratum": stratum,
        "lower_pct": lower_pct,
        "upper_pct": upper_pct,
        "per_label": per_label,
    }


def _in_distribution_entry(label=_LABEL_L1, level_name="L1"):
    """An available label with no anomaly under any default threshold."""
    return _label_entry(
        label,
        level_name=level_name,
        available=True,
        distribution_distance=0.5,
        out_of_range_features=[],
        features={
            "intensity_median": _feature(
                value=200.0, z_score=0.1, robust_z=0.1,
                percentile_rank=52.0, out_of_range=False,
            ),
        },
    )


def _record(entries, lower_pct=1, upper_pct=99):
    return {
        "intensity_reference_delta": _block(entries, lower_pct=lower_pct, upper_pct=upper_pct)
    }


def _int_findings(findings):
    """Filter to only intensity_reference_delta-rule findings."""
    return [f for f in findings if f.rule_id == "intensity_reference_delta"]


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _intensity_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  intensity_reference_delta:\n"
        "    params:\n"
    )


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'intensity_reference_delta')
    and restore after, mirroring the sibling rule test suites."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC12: the rule is registered and discoverable
# =========================================================================== #


def test_ac12_get_rule_returns_intensity_reference_delta_rule():
    rule = get_rule("intensity_reference_delta")
    assert rule.rule_id == "intensity_reference_delta"


def test_ac12_intensity_reference_delta_appears_exactly_once_in_iter_rules():
    matches = [r for r in iter_rules() if r.rule_id == "intensity_reference_delta"]
    assert len(matches) == 1


def test_ac12_intensity_reference_delta_rule_is_rule_subclass():
    assert isinstance(get_rule("intensity_reference_delta"), Rule)


# =========================================================================== #
# AC13: an in-distribution intensity produces no finding
# =========================================================================== #


def test_ac13_in_distribution_intensity_yields_no_finding():
    record = _record([_in_distribution_entry()])
    findings = _int_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# AC14: an out-of-range intensity feature fires an out-of-range finding
# =========================================================================== #


def test_ac14_out_of_range_feature_fires_exactly_one_finding():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.5,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(
                value=1000.0, z_score=8.1, robust_z=0.1,
                percentile_rank=100.0, out_of_range=True,
            ),
        },
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "intensity_reference_delta"
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_OUT_OF_RANGE_TAG)


# =========================================================================== #
# AC15: a large robust-z fires a robust-z finding, isolated
# =========================================================================== #


def test_ac15_large_robust_z_fires_isolated_robust_z_finding():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.5,
        out_of_range_features=[],
        features={
            "intensity_median": _feature(
                value=260.0, z_score=1.0, robust_z=6.4,
                percentile_rank=90.0, out_of_range=False,
            ),
        },
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_ROBUST_Z_TAG)
    assert "intensity_median" in f.reason


# =========================================================================== #
# AC16: a large distribution-distance fires a label-level finding, isolated
# =========================================================================== #


def test_ac16_large_distribution_distance_fires_isolated_finding():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=[],
        features={
            "intensity_median": _feature(
                value=200.0, z_score=0.1, robust_z=0.1,
                percentile_rank=52.0, out_of_range=False,
            ),
        },
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_DISTANCE_TAG)


# =========================================================================== #
# AC17: the robust-z threshold is read from config
# =========================================================================== #


def test_ac17_robust_z_threshold_is_config_driven(tmp_path):
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.5,
        out_of_range_features=[],
        features={"intensity_median": _feature(robust_z=4.0)},
    )
    record = _record([entry])

    findings_default = _int_findings(run_rules(record, default_config()))
    assert len(findings_default) == 1
    assert findings_default[0].reason.startswith(_ROBUST_Z_TAG)

    cfg_high = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      max_robust_z: 10.0\n", "high.yaml")
    )
    assert _int_findings(run_rules(record, cfg_high)) == []

    cfg_low = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      max_robust_z: 1.0\n", "low.yaml")
    )
    findings_low = _int_findings(run_rules(record, cfg_low))
    assert len(findings_low) == 1
    assert findings_low[0].reason.startswith(_ROBUST_Z_TAG)


# =========================================================================== #
# AC18: the distribution-distance threshold is read from config
# =========================================================================== #


def test_ac18_distribution_distance_threshold_is_config_driven(tmp_path):
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.0,
        out_of_range_features=[],
        features={"intensity_median": _feature()},
    )
    record = _record([entry])

    findings_default = _int_findings(run_rules(record, default_config()))
    assert len(findings_default) == 1
    assert findings_default[0].reason.startswith(_DISTANCE_TAG)

    cfg_high = load_config(
        _write_yaml(
            tmp_path,
            _intensity_yaml_header() + "      max_distribution_distance: 10.0\n",
            "high.yaml",
        )
    )
    assert _int_findings(run_rules(record, cfg_high)) == []

    cfg_low = load_config(
        _write_yaml(
            tmp_path,
            _intensity_yaml_header() + "      max_distribution_distance: 1.0\n",
            "low.yaml",
        )
    )
    findings_low = _int_findings(run_rules(record, cfg_low))
    assert len(findings_low) == 1
    assert findings_low[0].reason.startswith(_DISTANCE_TAG)


# =========================================================================== #
# AC19: each firing condition is independently toggleable
# =========================================================================== #


def test_ac19_flag_out_of_range_false_disables_only_out_of_range(tmp_path):
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,  # would also fire distance
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(
                robust_z=6.4, out_of_range=True,  # would also fire robust-z
            ),
        },
    )
    record = _record([entry])
    cfg = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      flag_out_of_range: false\n")
    )
    findings = _int_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _OUT_OF_RANGE_TAG not in tags
    assert _DISTANCE_TAG in tags
    assert _ROBUST_Z_TAG in tags


def test_ac19_flag_robust_z_false_disables_only_robust_z(tmp_path):
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(robust_z=6.4, out_of_range=True),
        },
    )
    record = _record([entry])
    cfg = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      flag_robust_z: false\n")
    )
    findings = _int_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _ROBUST_Z_TAG not in tags
    assert _OUT_OF_RANGE_TAG in tags
    assert _DISTANCE_TAG in tags


def test_ac19_flag_distribution_distance_false_disables_only_distance(tmp_path):
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(robust_z=6.4, out_of_range=True),
        },
    )
    record = _record([entry])
    cfg = load_config(
        _write_yaml(
            tmp_path, _intensity_yaml_header() + "      flag_distribution_distance: false\n"
        )
    )
    findings = _int_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _DISTANCE_TAG not in tags
    assert _OUT_OF_RANGE_TAG in tags
    assert _ROBUST_Z_TAG in tags


# =========================================================================== #
# AC20: severity is configurable and an unknown string raises
# =========================================================================== #


def test_ac20_default_severity_is_flag():
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].severity is Severity.FLAG


def test_ac20_severity_fail_overrides_default(tmp_path):
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    cfg = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      severity: fail\n")
    )
    findings = _int_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].severity is Severity.FAIL


def test_ac20_unrecognised_severity_raises_value_error(tmp_path):
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    cfg = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      severity: not-a-severity\n")
    )
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac20_value_error_raised_even_when_nothing_would_fire(tmp_path):
    """The bad-severity ValueError fires independently of whether any
    condition would otherwise fire -- even on an empty record."""
    cfg = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      severity: garbage\n")
    )
    with pytest.raises(ValueError):
        run_rules({}, cfg)


# =========================================================================== #
# AC21: an absent/non-mapping block is silent, and an available: false
# label produces no finding
# =========================================================================== #


def test_ac21_no_intensity_reference_delta_key_yields_no_findings():
    findings = IntensityReferenceDeltaRule().evaluate({}, default_config())
    assert findings == []


def test_ac21_intensity_reference_delta_none_yields_no_findings():
    findings = IntensityReferenceDeltaRule().evaluate(
        {"intensity_reference_delta": None}, default_config()
    )
    assert findings == []


def test_ac21_intensity_reference_delta_non_mapping_yields_no_findings():
    findings = IntensityReferenceDeltaRule().evaluate(
        {"intensity_reference_delta": ["not", "a", "mapping"]}, default_config()
    )
    assert findings == []


def test_ac21_unavailable_label_yields_no_finding():
    entry = _label_entry(
        99,
        level_name="UNKNOWN",
        available=False,
        distribution_distance=None,
        out_of_range_features=[],
        features={},
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac21_unavailable_label_silent_even_alongside_firing_available_label():
    """Positive control: an available, anomalous label still fires while an
    unavailable label in the same block contributes nothing."""
    unavailable = _label_entry(
        99, level_name="UNKNOWN", available=False,
        distribution_distance=None, out_of_range_features=[], features={},
    )
    firing = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([unavailable, firing])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC22: a reference lacking intensity distributions makes the rule inert
# =========================================================================== #


def test_ac22_empty_intensity_features_and_null_distance_yields_no_findings():
    """Mirrors the AC8 compute-side output: an available label with empty
    features / empty out_of_range_features / null distribution_distance."""
    entry = _label_entry(
        _LABEL_L1,
        available=True,
        distribution_distance=None,
        out_of_range_features=[],
        features={},
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac22_geometry_only_reference_block_across_multiple_labels_is_inert():
    entries = [
        _label_entry(_LABEL_L1, distribution_distance=None, features={}),
        _label_entry(_LABEL_L2, level_name="L4", distribution_distance=None, features={}),
    ]
    record = _record(entries)
    result = run_rules(record, default_config())
    assert _int_findings(result) == []


# =========================================================================== #
# AC23: the reason cites the reference and is explainable
# =========================================================================== #


def test_ac23_out_of_range_reason_names_label_level_feature_value_and_context():
    entry = _label_entry(
        _LABEL_L1,
        level_name="L1",
        distribution_distance=0.5,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(
                value=1000.0, percentile_rank=100.0, out_of_range=True,
            ),
        },
    )
    record = _record([entry], lower_pct=1, upper_pct=99)
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert reason.strip()
    assert str(_LABEL_L1) in reason
    assert "L1" in reason
    assert "intensity_median" in reason
    assert "1000" in reason
    assert "100" in reason  # percentile_rank
    assert "1" in reason and "99" in reason  # (lower_pct, upper_pct) band


# =========================================================================== #
# AC24: the rule is deterministic, non-mutating, and orders findings
# deterministically
# =========================================================================== #


def test_ac24_two_evaluate_calls_return_equal_finding_lists():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={"intensity_median": _feature(robust_z=6.4, out_of_range=True)},
    )
    record = _record([entry])
    cfg = default_config()
    findings1 = IntensityReferenceDeltaRule().evaluate(record, cfg)
    findings2 = IntensityReferenceDeltaRule().evaluate(record, cfg)
    assert findings1 == findings2
    assert len(findings1) == 3


def test_ac24_evaluate_does_not_mutate_record():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={"intensity_median": _feature(robust_z=6.4, out_of_range=True)},
    )
    record = _record([entry])
    record_before = copy.deepcopy(record)
    IntensityReferenceDeltaRule().evaluate(record, default_config())
    assert record == record_before


def test_ac24_ascending_label_then_distance_then_out_of_range_then_robust_z():
    label_20 = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(out_of_range=True, robust_z=0.1),
        },
    )
    label_23 = _label_entry(
        _LABEL_L2,
        level_name="L4",
        distribution_distance=0.1,
        out_of_range_features=[],
        features={"intensity_mean": _feature(robust_z=6.0)},
    )
    # Insert in reverse (23 before 20) and rely on the rule to sort ascending.
    record = _record([label_23, label_20])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 3
    assert findings[0].labels == frozenset({_LABEL_L1})
    assert findings[0].reason.startswith(_DISTANCE_TAG)
    assert findings[1].labels == frozenset({_LABEL_L1})
    assert findings[1].reason.startswith(_OUT_OF_RANGE_TAG)
    assert findings[2].labels == frozenset({_LABEL_L2})
    assert findings[2].reason.startswith(_ROBUST_Z_TAG)


def test_ac24_multiple_out_of_range_features_ascending_by_name():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.1,
        out_of_range_features=["intensity_std", "intensity_median"],  # deliberately unsorted
        features={
            "intensity_std": _feature(out_of_range=True),
            "intensity_median": _feature(out_of_range=True),
        },
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert all(f.reason.startswith(_OUT_OF_RANGE_TAG) for f in findings)
    assert "intensity_median" in findings[0].reason
    assert "intensity_std" in findings[1].reason


# =========================================================================== #
# AC25: findings flow through run_rules and verdict aggregation
# =========================================================================== #


def test_ac25_run_rules_includes_intensity_reference_delta_finding():
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    findings = run_rules(record, default_config())
    assert any(f.rule_id == "intensity_reference_delta" for f in findings)


def test_ac25_verdict_escalates_and_names_the_label():
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    cfg = default_config()
    result = build_case_result(run_rules(record, cfg), cfg)
    assert result.verdict.overall >= Severity.FLAG
    assert _LABEL_L1 in result.verdict.per_label
    reasons = result.verdict.per_label[_LABEL_L1]
    assert any(r.message.startswith(_DISTANCE_TAG) for r in reasons)


# =========================================================================== #
# AC26: adding the rule does not perturb existing pipeline output
# =========================================================================== #


def test_ac26_no_intensity_reference_delta_key_matches_pre_064_findings():
    """A record with no intensity_reference_delta key run through the full
    default registry contributes nothing from this rule -- confirming the
    064-merge no-op on records that predate the block."""
    record = {}
    findings = run_rules(record, default_config())
    assert _int_findings(findings) == []


def test_ac26_default_config_yaml_declares_no_intensity_reference_delta_section():
    """Item 065 owns adding the documented YAML section; this item's
    default_config.yaml diff must be empty, so the rule is enabled only via
    the absent-section rule_enabled fallback."""
    import yaml

    from segqc.config import default_config_path

    with open(default_config_path(), "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    rules_section = raw.get("rules", {}) if isinstance(raw, dict) else {}
    assert "intensity_reference_delta" not in rules_section


def test_ac26_rule_is_enabled_by_default_via_absent_section_fallback():
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1  # enabled by default, no explicit config section


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_per_label_yields_no_findings():
    record = {"intensity_reference_delta": _block([])}
    assert _int_findings(run_rules(record, default_config())) == []


def test_adv_non_dict_label_entry_skipped_no_raise():
    block = _block([_in_distribution_entry(_LABEL_L1)])
    block["per_label"]["999"] = "not-a-dict"
    record = {"intensity_reference_delta": block}
    result = run_rules(record, default_config())
    assert isinstance(result, list)


def test_adv_entry_missing_features_key_tolerated():
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    del entry["features"]
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_DISTANCE_TAG)


def test_adv_out_of_range_features_non_list_tolerated():
    entry = _label_entry(_LABEL_L1, distribution_distance=0.1)
    entry["out_of_range_features"] = {"intensity_median": True}  # not a list
    record = _record([entry])
    result = run_rules(record, default_config())
    assert isinstance(result, list)  # must not raise


def test_adv_null_robust_z_never_fires_robust_z_condition():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.1,
        out_of_range_features=[],
        features={"intensity_median": _feature(robust_z=None)},
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_robust_z_exactly_at_threshold_fires_inclusive():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.1,
        out_of_range_features=[],
        features={"intensity_median": _feature(robust_z=3.5)},  # default threshold
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_ROBUST_Z_TAG)


def test_adv_robust_z_negative_exactly_at_threshold_fires_via_abs():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=0.1,
        out_of_range_features=[],
        features={"intensity_median": _feature(robust_z=-3.5)},
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_ROBUST_Z_TAG)


def test_adv_distribution_distance_exactly_at_threshold_fires_inclusive():
    entry = _label_entry(_LABEL_L1, distribution_distance=3.0)  # default threshold
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_DISTANCE_TAG)


def test_adv_distribution_distance_just_below_threshold_does_not_fire():
    entry = _label_entry(_LABEL_L1, distribution_distance=2.999)
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_all_three_conditions_fire_on_one_label_in_fixed_order():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={
            "intensity_median": _feature(robust_z=6.4, out_of_range=True),
        },
    )
    record = _record([entry])
    findings = _int_findings(run_rules(record, default_config()))
    assert len(findings) == 3
    assert findings[0].reason.startswith(_DISTANCE_TAG)
    assert findings[1].reason.startswith(_OUT_OF_RANGE_TAG)
    assert findings[2].reason.startswith(_ROBUST_Z_TAG)
    assert all(f.labels == frozenset({_LABEL_L1}) for f in findings)


def test_adv_disabled_rule_is_skipped_by_runner(tmp_path):
    entry = _label_entry(_LABEL_L1, distribution_distance=4.2)
    record = _record([entry])
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "rules:\n"
            "  intensity_reference_delta:\n"
            "    enabled: false\n",
        )
    )
    findings = _int_findings(run_rules(record, cfg))
    assert findings == []


def test_adv_reason_tags_distinct_from_geometric_reference_delta_tags():
    """The intensity tags must not collide with item 047's geometric
    'Reference ...' tags, so a reader (and downstream tooling) can tell the
    two reference-delta families apart."""
    assert not _OUT_OF_RANGE_TAG.startswith("Reference ")
    assert not _ROBUST_Z_TAG.startswith("Reference ")
    assert not _DISTANCE_TAG.startswith("Reference ")


def test_adv_determinism_via_deep_copy_and_repeated_run_rules():
    entry = _label_entry(
        _LABEL_L1,
        distribution_distance=4.2,
        out_of_range_features=["intensity_median"],
        features={"intensity_median": _feature(robust_z=6.4, out_of_range=True)},
    )
    record = _record([entry])
    record_snapshot = copy.deepcopy(record)
    cfg = default_config()

    run1 = _int_findings(run_rules(record, cfg))
    run2 = _int_findings(run_rules(record, cfg))

    assert run1 == run2
    assert record == record_snapshot
