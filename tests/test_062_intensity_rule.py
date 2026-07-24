"""Tests for item 062 -- implausible-intensity heuristic
(``src/segfacet/heuristics/intensity.py``).

Covers Acceptance Criteria AC1-AC24:

- AC1: the rule is registered and discoverable.
- AC2: an intensity-plausible vertebra produces no finding.
- AC3: an implausibly-low median fires a low finding.
- AC4: an implausibly-high median fires a high finding.
- AC5: a degenerate (std ~= 0) distribution fires a degenerate finding.
- AC6: the low-band threshold is read from config.
- AC7: the high-band threshold is read from config.
- AC8: the degenerate-std threshold is read from config.
- AC9: flag_low: false disables the low condition.
- AC10: flag_high: false disables the high condition.
- AC11: flag_degenerate: false disables the degenerate condition.
- AC12: severity is configurable.
- AC13: an unrecognised severity string raises ValueError.
- AC14: an absent / non-mapping image_features block is silent, not an error.
- AC15: an unavailable block is silent.
- AC16: None-valued statistics are skipped, not crashed.
- AC17: the reason is explainable -- measured value vs threshold/band.
- AC18: findings flow through run_rules and verdict aggregation.
- AC19: computation is deterministic and non-mutating.
- AC20: findings are emitted in a deterministic order.
- AC21: the clean HU-painted corpus case does not fire.
- AC22: the metal implausible variant fires "too high" on the target label.
- AC23: the soft-tissue implausible variant fires "too low" on the target label.
- AC24: the degenerate-uniform variant fires the degenerate condition on the
  target label.

Adversarial / edge-case scenarios included:
- Boundary values: median exactly on either band bound does not fire;
  std exactly at the degenerate threshold does fire (inclusive).
- Empty per_label block.
- Malformed entries (non-dict label entry, entry missing first_order,
  first_order missing median/std keys).
- Multiple conditions (high + degenerate) firing on one label, fixed order.
- Determinism / non-mutation via deep-copy comparison and repeated calls.
- Runner + aggregation integration, plus a disabled rule being skipped.
- Golden safety: no image_features key -> full default registry unaffected.
"""

from __future__ import annotations

import copy
import pathlib

import nibabel as nib
import pytest

import segfacet.heuristics.intensity  # noqa: F401 — triggers IntensityRule registration
from segfacet.aggregate import build_case_result
from segfacet.config import SUPPORTED_SCHEMA_VERSION, default_config, load_config
from segfacet.feature_report import build_image_features_block
from segfacet.features.intensity import compute_intensity_features
from segfacet.heuristics import Rule, get_rule, iter_rules, run_rules
from segfacet.heuristics.intensity import IntensityRule
from segfacet.heuristics.rule import _RULES
from segfacet.synth.intensity import INTENSITY_CORPUS_DIR, load_intensity_manifest
from segfacet.verdict import Severity


# =========================================================================== #
# Helpers
# =========================================================================== #

_LOW_TAG = "Implausible intensity (too low):"
_HIGH_TAG = "Implausible intensity (too high):"
_DEGENERATE_TAG = "Implausible intensity (degenerate/uniform):"

_LABEL_L1 = 20
_LABEL_L2 = 23

_DEFAULT_MIN_PLAUSIBLE_HU = 100.0
_DEFAULT_MAX_PLAUSIBLE_HU = 2000.0
_DEFAULT_MAX_DEGENERATE_STD = 1.0

_CORPUS_TARGET_LABEL = 22


def _first_order(median=500.0, std=50.0, voxel_count=800, n_nonfinite_excluded=0):
    return {
        "voxel_count": voxel_count,
        "n_nonfinite_excluded": n_nonfinite_excluded,
        "mean": median,
        "median": median,
        "std": std,
        "min": None,
        "max": None,
        "p05": None,
        "p25": None,
        "p50": median,
        "p75": None,
        "p95": None,
        "range": None,
        "iqr": None,
        "entropy": None,
    }


def _label_entry(label, median=500.0, std=50.0, first_order=None):
    fo = first_order if first_order is not None else _first_order(median=median, std=std)
    return {"label": label, "first_order": fo, "extended": {}}


def _block(entries, available=True):
    per_label = {str(e["label"]): e for e in entries} if available else {}
    return {
        "image_features_version": "1.0",
        "available": available,
        "radiomics_available": False,
        "backend": "builtin",
        "per_label": per_label,
    }


def _record(entries, available=True):
    return {"image_features": _block(entries, available=available)}


def _intensity_findings(findings):
    """Filter to only intensity-rule findings."""
    return [f for f in findings if f.rule_id == "intensity"]


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _intensity_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  intensity:\n"
        "    params:\n"
    )


def _plausible_entry(label=_LABEL_L1):
    """An available label with no anomaly under any default threshold."""
    return _label_entry(label, median=500.0, std=50.0)


def _corpus_case(case_id):
    manifest = load_intensity_manifest()
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise KeyError(case_id)  # pragma: no cover - corpus invariant


def _corpus_record(case_id):
    """AC21-24 helper: load an item-058 committed fixture case, compute real
    intensity features (item 059), assemble the image_features block (item
    061), and wrap it as a record -- no hand-mocked statistics."""
    case = _corpus_case(case_id)
    scan_path = INTENSITY_CORPUS_DIR / case["scan_fixture"]
    seg_path = INTENSITY_CORPUS_DIR / case["seg_fixture"]
    scan_img = nib.load(str(scan_path))
    seg_img = nib.load(str(seg_path))
    intensity = compute_intensity_features(scan_img, seg_img)
    block = build_image_features_block(intensity)
    return {"image_features": block}


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'intensity') and restore
    after, mirroring the sibling rule test suites."""
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: the rule is registered and discoverable
# =========================================================================== #


def test_ac1_get_rule_returns_intensity_rule():
    rule = get_rule("intensity")
    assert rule.rule_id == "intensity"


def test_ac1_intensity_appears_exactly_once_in_iter_rules():
    matches = [r for r in iter_rules() if r.rule_id == "intensity"]
    assert len(matches) == 1


def test_ac1_intensity_rule_is_rule_subclass():
    assert isinstance(get_rule("intensity"), Rule)


# =========================================================================== #
# AC2: an intensity-plausible vertebra produces no finding
# =========================================================================== #


def test_ac2_plausible_vertebra_yields_no_finding():
    record = _record([_plausible_entry()])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# AC3: an implausibly-low median fires a low finding
# =========================================================================== #


def test_ac3_low_median_fires_exactly_one_low_finding():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)  # median < 100.0
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "intensity"
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_LOW_TAG)


# =========================================================================== #
# AC4: an implausibly-high median fires a high finding
# =========================================================================== #


def test_ac4_high_median_fires_exactly_one_high_finding():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=50.0)  # median > 2000.0
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_HIGH_TAG)


# =========================================================================== #
# AC5: a degenerate (std ~= 0) distribution fires a degenerate finding
# =========================================================================== #


def test_ac5_degenerate_std_fires_exactly_one_degenerate_finding():
    entry = _label_entry(_LABEL_L1, median=500.0, std=0.5)  # std <= 1.0, median in band
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    f = findings[0]
    assert f.labels == frozenset({_LABEL_L1})
    assert f.reason.startswith(_DEGENERATE_TAG)


# =========================================================================== #
# AC6: the low-band threshold is read from config
# =========================================================================== #


def test_ac6_low_threshold_is_config_driven(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])

    findings_default = _intensity_findings(run_rules(record, default_config()))
    assert len(findings_default) == 1
    assert findings_default[0].reason.startswith(_LOW_TAG)

    cfg_low_bound = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      min_plausible_hu: 0.0\n", "zero.yaml")
    )
    assert _intensity_findings(run_rules(record, cfg_low_bound)) == []

    cfg_raised = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      min_plausible_hu: 200.0\n", "raised.yaml")
    )
    findings_raised = _intensity_findings(run_rules(record, cfg_raised))
    assert len(findings_raised) == 1
    assert findings_raised[0].reason.startswith(_LOW_TAG)


# =========================================================================== #
# AC7: the high-band threshold is read from config
# =========================================================================== #


def test_ac7_high_threshold_is_config_driven(tmp_path):
    entry = _label_entry(_LABEL_L1, median=3000.0, std=50.0)
    record = _record([entry])

    findings_default = _intensity_findings(run_rules(record, default_config()))
    assert len(findings_default) == 1
    assert findings_default[0].reason.startswith(_HIGH_TAG)

    cfg_high = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      max_plausible_hu: 5000.0\n", "high.yaml")
    )
    assert _intensity_findings(run_rules(record, cfg_high)) == []

    cfg_low = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      max_plausible_hu: 1000.0\n", "low.yaml")
    )
    findings_low = _intensity_findings(run_rules(record, cfg_low))
    assert len(findings_low) == 1
    assert findings_low[0].reason.startswith(_HIGH_TAG)


# =========================================================================== #
# AC8: the degenerate-std threshold is read from config
# =========================================================================== #


def test_ac8_degenerate_threshold_is_config_driven(tmp_path):
    entry = _label_entry(_LABEL_L1, median=500.0, std=0.0)
    record = _record([entry])

    findings_default = _intensity_findings(run_rules(record, default_config()))
    assert len(findings_default) == 1
    assert findings_default[0].reason.startswith(_DEGENERATE_TAG)

    cfg_unreachable = load_config(
        _write_yaml(
            tmp_path, _intensity_yaml_header() + "      max_degenerate_std: -1.0\n", "unreachable.yaml"
        )
    )
    assert _intensity_findings(run_rules(record, cfg_unreachable)) == []

    entry_std3 = _label_entry(_LABEL_L1, median=500.0, std=3.0)
    record_std3 = _record([entry_std3])
    cfg_raised = load_config(
        _write_yaml(tmp_path, _intensity_yaml_header() + "      max_degenerate_std: 5.0\n", "raised.yaml")
    )
    findings_raised = _intensity_findings(run_rules(record_std3, cfg_raised))
    assert len(findings_raised) == 1
    assert findings_raised[0].reason.startswith(_DEGENERATE_TAG)


# =========================================================================== #
# AC9: flag_low: false disables the low condition
# =========================================================================== #


def test_ac9_flag_low_false_disables_only_low(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=0.5)  # would fire low AND degenerate
    record = _record([entry])
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      flag_low: false\n"))
    findings = _intensity_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _LOW_TAG not in tags
    assert _DEGENERATE_TAG in tags


# =========================================================================== #
# AC10: flag_high: false disables the high condition
# =========================================================================== #


def test_ac10_flag_high_false_disables_only_high(tmp_path):
    entry = _label_entry(_LABEL_L1, median=3000.0, std=0.5)  # would fire high AND degenerate
    record = _record([entry])
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      flag_high: false\n"))
    findings = _intensity_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _HIGH_TAG not in tags
    assert _DEGENERATE_TAG in tags


# =========================================================================== #
# AC11: flag_degenerate: false disables the degenerate condition
# =========================================================================== #


def test_ac11_flag_degenerate_false_disables_only_degenerate(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=0.5)  # would fire low AND degenerate
    record = _record([entry])
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      flag_degenerate: false\n"))
    findings = _intensity_findings(run_rules(record, cfg))
    tags = {f.reason.split(":")[0] + ":" for f in findings}
    assert _DEGENERATE_TAG not in tags
    assert _LOW_TAG in tags


# =========================================================================== #
# AC12: severity is configurable
# =========================================================================== #


def test_ac12_default_severity_is_flag():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].severity is Severity.FLAG


def test_ac12_severity_fail_overrides_default(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      severity: fail\n"))
    findings = _intensity_findings(run_rules(record, cfg))
    assert len(findings) == 1
    assert findings[0].severity is Severity.FAIL


# =========================================================================== #
# AC13: an unrecognised severity string raises ValueError
# =========================================================================== #


def test_ac13_unrecognised_severity_raises_value_error(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      severity: not-a-severity\n"))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac13_value_error_raised_even_when_nothing_would_fire(tmp_path):
    """AC13: the bad-severity ValueError fires independently of whether any
    condition would otherwise fire -- even on an empty record."""
    cfg = load_config(_write_yaml(tmp_path, _intensity_yaml_header() + "      severity: garbage\n"))
    with pytest.raises(ValueError):
        run_rules({}, cfg)


# =========================================================================== #
# AC14: an absent / non-mapping image_features block is silent, not an error
# =========================================================================== #


def test_ac14_no_image_features_key_yields_no_findings():
    findings = IntensityRule().evaluate({}, default_config())
    assert findings == []


def test_ac14_image_features_none_yields_no_findings():
    findings = IntensityRule().evaluate({"image_features": None}, default_config())
    assert findings == []


def test_ac14_image_features_non_mapping_yields_no_findings():
    findings = IntensityRule().evaluate(
        {"image_features": ["not", "a", "mapping"]}, default_config()
    )
    assert findings == []


# =========================================================================== #
# AC15: an unavailable block is silent
# =========================================================================== #


def test_ac15_unavailable_block_yields_no_findings():
    record = {
        "image_features": {
            "image_features_version": "1.0",
            "available": False,
            "radiomics_available": False,
            "backend": "builtin",
            "per_label": {},
        }
    }
    findings = IntensityRule().evaluate(record, default_config())
    assert findings == []


# =========================================================================== #
# AC16: None-valued statistics are skipped, not crashed
# =========================================================================== #


def test_ac16_none_valued_stats_skipped_not_crashed():
    absent_entry = _label_entry(
        99, first_order=_first_order(median=None, std=None, voxel_count=0)
    )
    firing_entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([absent_entry, firing_entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({_LABEL_L1})


# =========================================================================== #
# AC17: the reason is explainable
# =========================================================================== #


def test_ac17_low_reason_names_label_median_and_threshold():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert reason.strip()
    assert str(_LABEL_L1) in reason
    assert "50" in reason
    assert "100" in reason  # min_plausible_hu default


def test_ac17_high_reason_names_label_median_and_threshold():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=50.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert reason.strip()
    assert str(_LABEL_L1) in reason
    assert "3000" in reason
    assert "2000" in reason


def test_ac17_degenerate_reason_names_label_std_and_threshold():
    entry = _label_entry(_LABEL_L1, median=500.0, std=0.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    reason = findings[0].reason
    assert reason.strip()
    assert str(_LABEL_L1) in reason
    assert "0" in reason
    assert "1" in reason  # max_degenerate_std default


# =========================================================================== #
# AC18: findings flow through run_rules and verdict aggregation
# =========================================================================== #


def test_ac18_run_rules_includes_intensity_finding():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    findings = run_rules(record, default_config())
    assert any(f.rule_id == "intensity" for f in findings)


def test_ac18_verdict_escalates_and_names_the_label():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    cfg = default_config()
    result = build_case_result(run_rules(record, cfg), cfg)
    assert result.verdict.overall >= Severity.FLAG
    assert _LABEL_L1 in result.verdict.per_label
    reasons = result.verdict.per_label[_LABEL_L1]
    assert any(r.message.startswith(_LOW_TAG) for r in reasons)


# =========================================================================== #
# AC19: computation is deterministic and non-mutating
# =========================================================================== #


def test_ac19_two_evaluate_calls_return_equal_finding_lists():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=0.5)  # fires high + degenerate
    record = _record([entry])
    cfg = default_config()
    findings1 = IntensityRule().evaluate(record, cfg)
    findings2 = IntensityRule().evaluate(record, cfg)
    assert findings1 == findings2
    assert len(findings1) == 2


def test_ac19_evaluate_does_not_mutate_record():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=0.5)
    record = _record([entry])
    record_before = copy.deepcopy(record)
    IntensityRule().evaluate(record, default_config())
    assert record == record_before


# =========================================================================== #
# AC20: findings are emitted in a deterministic order
# =========================================================================== #


def test_ac20_ascending_label_then_low_high_degenerate_order():
    label_20_low = _label_entry(_LABEL_L1, median=50.0, std=50.0)  # low only
    label_23_high_and_degenerate = _label_entry(_LABEL_L2, median=3000.0, std=0.5)

    # Insert in reverse (23 before 20) and rely on the rule to sort ascending.
    block = _block([label_23_high_and_degenerate, label_20_low])
    record = {"image_features": block}
    findings = _intensity_findings(run_rules(record, default_config()))

    assert len(findings) == 3
    assert findings[0].labels == frozenset({_LABEL_L1})
    assert findings[0].reason.startswith(_LOW_TAG)
    assert findings[1].labels == frozenset({_LABEL_L2})
    assert findings[1].reason.startswith(_HIGH_TAG)
    assert findings[2].labels == frozenset({_LABEL_L2})
    assert findings[2].reason.startswith(_DEGENERATE_TAG)


# =========================================================================== #
# AC21-24: corpus-driven end-to-end (item 058 fixtures -> 059 -> 061 -> rule)
# =========================================================================== #


def test_ac21_clean_hu_corpus_case_fires_no_intensity_finding():
    record = _corpus_record("clean_hu")
    findings = _intensity_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac22_implausible_metal_corpus_case_fires_too_high_on_label_22():
    record = _corpus_record("implausible_metal")
    findings = _intensity_findings(run_rules(record, default_config()))
    matches = [
        f for f in findings
        if f.reason.startswith(_HIGH_TAG) and _CORPUS_TARGET_LABEL in f.labels
    ]
    assert len(matches) >= 1


def test_ac23_implausible_soft_tissue_corpus_case_fires_too_low_on_label_22():
    record = _corpus_record("implausible_soft_tissue")
    findings = _intensity_findings(run_rules(record, default_config()))
    matches = [
        f for f in findings
        if f.reason.startswith(_LOW_TAG) and _CORPUS_TARGET_LABEL in f.labels
    ]
    assert len(matches) >= 1


def test_ac24_degenerate_uniform_corpus_case_fires_degenerate_on_label_22():
    record = _corpus_record("degenerate_uniform")
    findings = _intensity_findings(run_rules(record, default_config()))
    matches = [
        f for f in findings
        if f.reason.startswith(_DEGENERATE_TAG) and _CORPUS_TARGET_LABEL in f.labels
    ]
    assert len(matches) >= 1


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_median_exactly_at_min_bound_does_not_fire_low():
    entry = _label_entry(_LABEL_L1, median=_DEFAULT_MIN_PLAUSIBLE_HU, std=50.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_median_exactly_at_max_bound_does_not_fire_high():
    entry = _label_entry(_LABEL_L1, median=_DEFAULT_MAX_PLAUSIBLE_HU, std=50.0)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert findings == []


def test_adv_std_exactly_at_degenerate_threshold_fires_inclusive():
    entry = _label_entry(_LABEL_L1, median=500.0, std=_DEFAULT_MAX_DEGENERATE_STD)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith(_DEGENERATE_TAG)


def test_adv_empty_per_label_yields_no_findings():
    record = {"image_features": _block([])}
    assert _intensity_findings(run_rules(record, default_config())) == []


def test_adv_non_dict_label_entry_skipped_no_raise():
    block = _block([_plausible_entry(_LABEL_L1)])
    block["per_label"]["999"] = "not-a-dict"
    record = {"image_features": block}
    result = run_rules(record, default_config())
    assert isinstance(result, list)


def test_adv_entry_missing_first_order_tolerated():
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    del entry["first_order"]
    record = _record([entry])
    result = run_rules(record, default_config())
    assert _intensity_findings(result) == []


def test_adv_first_order_missing_median_and_std_keys_tolerated():
    entry = _label_entry(_LABEL_L1)
    fo = dict(entry["first_order"])
    del fo["median"]
    del fo["std"]
    entry["first_order"] = fo
    record = _record([entry])
    result = run_rules(record, default_config())
    assert _intensity_findings(result) == []


def test_adv_high_and_degenerate_fire_on_one_label_in_fixed_order():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=0.5)
    record = _record([entry])
    findings = _intensity_findings(run_rules(record, default_config()))
    assert len(findings) == 2
    assert findings[0].reason.startswith(_HIGH_TAG)
    assert findings[1].reason.startswith(_DEGENERATE_TAG)
    assert all(f.labels == frozenset({_LABEL_L1}) for f in findings)


def test_adv_disabled_rule_is_skipped_by_runner(tmp_path):
    entry = _label_entry(_LABEL_L1, median=50.0, std=50.0)
    record = _record([entry])
    cfg = load_config(
        _write_yaml(
            tmp_path,
            f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
            "rules:\n"
            "  intensity:\n"
            "    enabled: false\n",
        )
    )
    findings = _intensity_findings(run_rules(record, cfg))
    assert findings == []


def test_adv_golden_safety_no_image_features_key_matches_pre_062_findings():
    """A record with no image_features key run through the full default
    registry contributes nothing from this rule -- confirming the 062-merge
    no-op on records that predate the image_features block."""
    record = {}
    findings = run_rules(record, default_config())
    assert _intensity_findings(findings) == []


def test_adv_determinism_via_deep_copy_and_repeated_run_rules():
    entry = _label_entry(_LABEL_L1, median=3000.0, std=0.5)
    record = _record([entry])
    record_snapshot = copy.deepcopy(record)
    cfg = default_config()

    run1 = _intensity_findings(run_rules(record, cfg))
    run2 = _intensity_findings(run_rules(record, cfg))

    assert run1 == run2
    assert record == record_snapshot
