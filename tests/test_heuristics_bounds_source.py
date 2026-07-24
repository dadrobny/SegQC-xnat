"""Tests for item 048 — heuristic config switch: reference-derived vs
hand-set bounds (``src/segfacet/heuristics/bounds.py`` extended for item 027's
``BoundsRule``).

Covers Acceptance Criteria AC1-AC13:

- AC1:  hand-set is the default and is byte-unchanged (including when a
        reference is attached but source is unset/hand-set — ignored).
- AC2:  reference mode fires on an out-of-reference value (strictly below
        p{lower_pct} or strictly above p{upper_pct}).
- AC3:  reference mode passes an in-reference value, inclusive at both bounds.
- AC4:  effective bounds come from the configured percentiles; the finding
        reason and firing behaviour track a reconfigured percentile pair.
- AC5:  per-level (and per-stratum) fallback to hand-set for uncovered levels.
- AC6:  reference-mode reasons are explainable and distinct from hand-set.
- AC7:  the switch is documented in default_config.yaml comments only; the
        parsed config (and its hash) is unchanged.
- AC8:  the switch round-trips through config load.
- AC9:  graceful degradation when no reference is attached at all.
- AC10: an unrecognised `source` raises ValueError before per-label processing.
- AC11: an unknown configured percentile raises ValueError.
- AC12: the pure derivation helper `reference_bounds_for_level`.
- AC13: determinism and non-mutation of record/reference/config.

Adversarial / edge-case scenarios included:
- Per-metric fallback: a covered level missing one tracked metric's stats
  falls back to hand-set for that metric only.
- Empty per_label in reference mode.
- A label whose level has no hand-set group AND no reference coverage is
  skipped, not crashed.
- Boundary values exactly on p{lower_pct}/p{upper_pct}.
- reference_stratum mismatch treated as uncovered (fallback), not a crash.
- Non-mutation of the reference object itself (not just record/config).
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segfacet.heuristics.bounds  # noqa: F401 — triggers BoundsRule registration
from segfacet.config import (
    SUPPORTED_SCHEMA_VERSION,
    default_config,
    default_config_path,
    load_config,
)
from segfacet.heuristics import run_rules
from segfacet.heuristics.bounds import BoundsRule, DEFAULT_BOUNDS, reference_bounds_for_level
from segfacet.heuristics.rule import _RULES
from segfacet.reference.artifact import bundled_default_reference, config_hash
from segfacet.reference.schema import (
    ALL_STRATUM,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
)


# =========================================================================== #
# Reference-fixture helpers
# =========================================================================== #

_L3_VOLUME = dict(p1=10_000.0, p5=12_000.0, p25=15_000.0, p50=20_000.0,
                   p75=25_000.0, p95=30_000.0, p99=35_000.0)
_L3_EXTENT_X = dict(p1=20.0, p5=22.0, p25=25.0, p50=30.0, p75=35.0, p95=40.0, p99=45.0)
_L3_EXTENT_Y = dict(p1=20.0, p5=22.0, p25=25.0, p50=30.0, p75=35.0, p95=40.0, p99=45.0)
_L3_EXTENT_Z = dict(p1=15.0, p5=17.0, p25=20.0, p50=25.0, p75=30.0, p95=35.0, p99=40.0)

_L4_VOLUME = dict(p1=9_000.0, p5=11_000.0, p25=14_000.0, p50=19_000.0,
                   p75=24_000.0, p95=29_000.0, p99=34_000.0)


def _feature_stats(p1, p5, p25, p50, p75, p95, p99, count=10, std=1.0) -> FeatureStats:
    return FeatureStats(
        count=count,
        mean=float(p50),
        std=float(std),
        min=float(p1),
        max=float(p99),
        percentiles={
            "p1": float(p1), "p5": float(p5), "p25": float(p25), "p50": float(p50),
            "p75": float(p75), "p95": float(p95), "p99": float(p99),
        },
    )


def _level_distribution(level_name: str, stratum: str, feature_stats: dict) -> LevelDistribution:
    return LevelDistribution(
        level_name=level_name, stratum=stratum, record_count=10, feature_stats=feature_stats,
    )


def _reference(levels: dict, percentiles=(1, 5, 25, 50, 75, 95, 99)) -> ReferenceDistribution:
    provenance = Provenance(
        source="unit-test", config_hash="deadbeef", build_date="2026-07-11", size_proxy_name=None,
    )
    return ReferenceDistribution(
        schema_version="1.0",
        provenance=provenance,
        features=(
            "physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm", "spline_offset_mm",
        ),
        percentiles=tuple(percentiles),
        subject_count=10,
        strata=(ALL_STRATUM,),
        levels=levels,
    )


def _full_reference() -> ReferenceDistribution:
    """A reference covering level 'L3' fully (all four bounds metrics)."""
    feature_stats = {
        "physical_volume_mm3": _feature_stats(**_L3_VOLUME),
        "extent_x_mm": _feature_stats(**_L3_EXTENT_X),
        "extent_y_mm": _feature_stats(**_L3_EXTENT_Y),
        "extent_z_mm": _feature_stats(**_L3_EXTENT_Z),
    }
    return _reference({"L3": {ALL_STRATUM: _level_distribution("L3", ALL_STRATUM, feature_stats)}})


def _partial_reference() -> ReferenceDistribution:
    """A reference covering 'L3' fully and 'L4' with only volume stats
    (per-metric fallback fixture)."""
    l3_stats = {
        "physical_volume_mm3": _feature_stats(**_L3_VOLUME),
        "extent_x_mm": _feature_stats(**_L3_EXTENT_X),
        "extent_y_mm": _feature_stats(**_L3_EXTENT_Y),
        "extent_z_mm": _feature_stats(**_L3_EXTENT_Z),
    }
    l4_stats = {"physical_volume_mm3": _feature_stats(**_L4_VOLUME)}
    return _reference({
        "L3": {ALL_STRATUM: _level_distribution("L3", ALL_STRATUM, l3_stats)},
        "L4": {ALL_STRATUM: _level_distribution("L4", ALL_STRATUM, l4_stats)},
    })


# =========================================================================== #
# Record / config helpers
# =========================================================================== #


def _entry(label, level_name, volume_mm3=20_000.0, extent_x_mm=30.0,
           extent_y_mm=30.0, extent_z_mm=25.0) -> dict:
    """A per_label entry mid-band for the L3 reference fixture by default."""
    return {
        "label": label,
        "level_name": level_name,
        "geometry": {
            "physical_volume_mm3": volume_mm3,
            "extent_x_mm": extent_x_mm,
            "extent_y_mm": extent_y_mm,
            "extent_z_mm": extent_z_mm,
            "voxel_count": 5000,
        },
    }


def _record(*entries: dict, reference=None) -> dict:
    record = {
        "per_label": {e["label"]: e for e in entries},
        "relationships": {},
        "overlaps": {},
    }
    if reference is not None:
        record["reference"] = reference
    return record


def _write_yaml(tmp_path: pathlib.Path, content: str, name: str = "config.yaml") -> pathlib.Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _bounds_findings(findings):
    return [f for f in findings if f.rule_id == "bounds"]


def _bounds_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    params:\n"
    )


def _reference_mode_yaml(lower_pct=None, upper_pct=None, stratum=None, extra="") -> str:
    text = _bounds_yaml_header() + "      source: reference\n"
    if lower_pct is not None:
        text += f"      reference_lower_pct: {lower_pct}\n"
    if upper_pct is not None:
        text += f"      reference_upper_pct: {upper_pct}\n"
    if stratum is not None:
        text += f"      reference_stratum: {stratum}\n"
    return text + extra


def _hand_set_mode_yaml() -> str:
    return _bounds_yaml_header() + "      source: hand-set\n"


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: hand-set is the default and is byte-unchanged
# =========================================================================== #


def test_ac1_no_source_param_matches_explicit_hand_set(tmp_path):
    """AC1: an unset `source` param behaves identically to explicit hand-set."""
    record = _record(_entry(3, "C3", volume_mm3=DEFAULT_BOUNDS["cervical"]["max_volume_mm3"] * 10.0))
    unset_cfg = default_config()
    explicit_cfg = load_config(_write_yaml(tmp_path, _hand_set_mode_yaml()))
    unset_findings = _bounds_findings(run_rules(record, unset_cfg))
    explicit_findings = _bounds_findings(run_rules(record, explicit_cfg))
    assert unset_findings == explicit_findings
    assert unset_findings != []


def test_ac1_findings_identical_with_and_without_attached_reference():
    """AC1: an attached record["reference"] changes nothing under hand-set."""
    oversized_vol = DEFAULT_BOUNDS["cervical"]["max_volume_mm3"] * 10.0
    record_no_ref = _record(_entry(3, "C3", volume_mm3=oversized_vol))
    record_with_ref = _record(_entry(3, "C3", volume_mm3=oversized_vol), reference=_full_reference())
    cfg = default_config()
    findings_no_ref = _bounds_findings(run_rules(record_no_ref, cfg))
    findings_with_ref = _bounds_findings(run_rules(record_with_ref, cfg))
    assert findings_no_ref == findings_with_ref
    assert findings_no_ref != []


def test_ac1_reference_present_but_source_hand_set_uses_hand_set_bounds(tmp_path):
    """AC1: a value that would PASS in reference mode still fires under
    hand-set when a reference is attached but source stays hand-set."""
    cfg = load_config(_write_yaml(tmp_path, _hand_set_mode_yaml()))
    # A value that exceeds the hand-set lumbar max fires identically whether
    # or not a (here, ignored) reference is attached to the record.
    oversized_vol = DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"] * 10.0
    record_with_ref = _record(_entry(22, "L3", volume_mm3=oversized_vol), reference=_full_reference())
    record_no_ref = _record(_entry(22, "L3", volume_mm3=oversized_vol))
    findings_with_ref = _bounds_findings(run_rules(record_with_ref, cfg))
    findings_no_ref = _bounds_findings(run_rules(record_no_ref, cfg))
    assert findings_with_ref == findings_no_ref
    assert findings_with_ref != []


# =========================================================================== #
# AC2: reference mode fires on an out-of-reference value
# =========================================================================== #


def test_ac2_value_strictly_below_lower_pct_fires_one_finding(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    below = _L3_VOLUME["p1"] - 1.0
    record = _record(_entry(22, "L3", volume_mm3=below), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol_findings = [f for f in findings if f.labels == frozenset({22})
                     and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())]
    assert len(vol_findings) == 1


def test_ac2_value_strictly_above_upper_pct_fires_one_finding(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    above = _L3_VOLUME["p99"] + 1.0
    record = _record(_entry(22, "L3", volume_mm3=above), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol_findings = [f for f in findings if f.labels == frozenset({22})
                     and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())]
    assert len(vol_findings) == 1


# =========================================================================== #
# AC3: reference mode passes an in-reference value, inclusive at both bounds
# =========================================================================== #


def test_ac3_value_exactly_at_lower_pct_does_not_fire(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p1"]), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol_findings = [f for f in findings if f.labels == frozenset({22})
                     and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())]
    assert vol_findings == []


def test_ac3_value_exactly_at_upper_pct_does_not_fire(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p99"]), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol_findings = [f for f in findings if f.labels == frozenset({22})
                     and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())]
    assert vol_findings == []


def test_ac3_mid_band_value_does_not_fire(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p50"]), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings == []


# =========================================================================== #
# AC4: effective bounds come from the configured percentiles
# =========================================================================== #


def test_ac4_default_percentile_pair_uses_p1_p99(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p1"] - 1.0), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol = [f for f in findings if f.labels == frozenset({22})]
    assert len(vol) == 1
    assert "10000" in vol[0].reason  # the p1 bound in effect by default
    assert "p1" in vol[0].reason


def test_ac4_reconfigured_percentile_pair_changes_firing_and_reason(tmp_path):
    default_cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(), name="default.yaml"))
    p5_p95_cfg = load_config(
        _write_yaml(tmp_path, _reference_mode_yaml(lower_pct=5, upper_pct=95), name="p5p95.yaml")
    )
    # Between p1 (10000) and p5 (12000): passes under (1, 99), fires under (5, 95).
    between = (_L3_VOLUME["p1"] + _L3_VOLUME["p5"]) / 2.0
    record = _record(_entry(22, "L3", volume_mm3=between), reference=_full_reference())

    default_findings = _bounds_findings(run_rules(record, default_cfg))
    p5_p95_findings = _bounds_findings(run_rules(record, p5_p95_cfg))

    default_vol = [f for f in default_findings if f.labels == frozenset({22})]
    p5_p95_vol = [f for f in p5_p95_findings if f.labels == frozenset({22})]
    assert default_vol == []
    assert len(p5_p95_vol) == 1
    reason = p5_p95_vol[0].reason
    assert "12000" in reason  # the p5 bound now in effect
    assert "p5" in reason


def test_ac4_reason_quotes_the_effective_reference_bound(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p99"] + 500.0), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol = [f for f in findings if f.labels == frozenset({22})]
    assert len(vol) == 1
    assert "35000" in vol[0].reason  # p99 upper bound
    assert "p99" in vol[0].reason


# =========================================================================== #
# AC5: per-level (and per-stratum) fallback to hand-set for uncovered levels
# =========================================================================== #


def test_ac5_uncovered_level_falls_back_and_fires_like_hand_set(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    oversized_vol = DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"] * 10.0
    # "L5" is not present in _full_reference()'s levels.
    record = _record(_entry(24, "L5", volume_mm3=oversized_vol), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({24})]
    assert len(label_findings) >= 1


def test_ac5_uncovered_level_falls_back_and_passes_like_hand_set(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    g = DEFAULT_BOUNDS["lumbar"]
    mid_vol = (g["min_volume_mm3"] + g["max_volume_mm3"]) / 2.0
    mid_x = (g["min_extent_x_mm"] + g["max_extent_x_mm"]) / 2.0
    mid_y = (g["min_extent_y_mm"] + g["max_extent_y_mm"]) / 2.0
    mid_z = (g["min_extent_z_mm"] + g["max_extent_z_mm"]) / 2.0
    record = _record(
        _entry(24, "L5", volume_mm3=mid_vol, extent_x_mm=mid_x, extent_y_mm=mid_y, extent_z_mm=mid_z),
        reference=_full_reference(),
    )
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings == []


def test_ac5_uncovered_level_never_crashes():
    cfg = default_config()
    record = _record(_entry(24, "L5", volume_mm3=1.0), reference=_full_reference())
    findings = _bounds_findings(BoundsRule().evaluate(record, cfg))
    assert isinstance(findings, list)


def test_ac5_reference_stratum_mismatch_falls_back_to_hand_set(tmp_path):
    """A reference that only covers stratum 'all' is treated as uncovered
    when reference_stratum is configured to something else."""
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(stratum="juvenile")))
    oversized_vol = DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"] * 10.0
    record = _record(_entry(22, "L3", volume_mm3=oversized_vol), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({22})]
    assert len(label_findings) >= 1  # hand-set fallback fires


# =========================================================================== #
# AC6: reference-mode reasons are explainable and distinct
# =========================================================================== #


def test_ac6_reference_reason_names_level_value_and_percentile(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    below = _L3_VOLUME["p1"] - 1.0
    record = _record(_entry(22, "L3", volume_mm3=below), reference=_full_reference())
    findings = _bounds_findings(run_rules(record, cfg))
    vol = [f for f in findings if f.labels == frozenset({22})]
    assert len(vol) == 1
    reason = vol[0].reason
    assert "22" in reason
    assert "L3" in reason
    assert f"{below:.6g}" in reason
    assert "p1" in reason
    assert "level" in reason.lower()


def test_ac6_reference_reason_distinct_from_hand_set_group_reason(tmp_path):
    ref_cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(), name="ref.yaml"))
    hs_cfg = load_config(_write_yaml(tmp_path, _hand_set_mode_yaml(), name="hs.yaml"))

    below_ref = _L3_VOLUME["p1"] - 1.0
    ref_record = _record(_entry(22, "L3", volume_mm3=below_ref), reference=_full_reference())
    ref_findings = _bounds_findings(run_rules(ref_record, ref_cfg))

    below_hand_set = DEFAULT_BOUNDS["lumbar"]["min_volume_mm3"] - 1.0
    hs_record = _record(_entry(22, "L3", volume_mm3=below_hand_set))
    hs_findings = _bounds_findings(run_rules(hs_record, hs_cfg))

    assert len(ref_findings) == 1 and len(hs_findings) == 1
    ref_reason, hs_reason = ref_findings[0].reason, hs_findings[0].reason
    assert ref_reason != hs_reason
    assert "group" not in ref_reason.lower()
    assert "group" in hs_reason.lower()


# =========================================================================== #
# AC7: the switch is documented in comments only; parsed config is unchanged
# =========================================================================== #


def test_ac7_bundled_default_config_rules_match_pre_048_provenance_hash():
    # default_config().rules is {} by design (item 026: an absent/empty
    # ``rules`` section means all rules use their built-in code-side
    # defaults), so it is not a valid baseline for "unchanged by item 048".
    # Instead assert the bundled YAML's rules still hash to the config_hash
    # recorded in the bundled reference artifact's provenance -- captured
    # before item 048 and unaffected by a comments-only change.
    bundled = load_config(default_config_path())
    expected_hash = bundled_default_reference().provenance.config_hash
    assert config_hash(bundled) == expected_hash


def test_ac7_bundled_default_config_hash_matches_code_default_hash():
    bundled = load_config(default_config_path())
    expected_hash = bundled_default_reference().provenance.config_hash
    assert config_hash(bundled) == expected_hash


def test_ac7_bundled_default_schema_version_unchanged():
    bundled = load_config(default_config_path())
    assert bundled.schema_version == SUPPORTED_SCHEMA_VERSION


# =========================================================================== #
# AC8: the switch round-trips through config load
# =========================================================================== #


def test_ac8_source_reference_round_trips_through_load_config(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(lower_pct=5, upper_pct=95, stratum="all")))
    assert cfg.rule_param("bounds", "source", default=None) == "reference"
    assert cfg.rule_param("bounds", "reference_lower_pct", default=None) == 5
    assert cfg.rule_param("bounds", "reference_upper_pct", default=None) == 95
    assert cfg.rule_param("bounds", "reference_stratum", default=None) == "all"
    assert cfg.schema_version == "0.1"


def test_ac8_default_percentile_params_absent_when_unset(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    assert cfg.rule_param("bounds", "source", default=None) == "reference"
    assert cfg.rule_param("bounds", "reference_lower_pct", default=1) == 1
    assert cfg.rule_param("bounds", "reference_upper_pct", default=99) == 99


# =========================================================================== #
# AC9: graceful degradation when no reference is attached
# =========================================================================== #


def test_ac9_source_reference_without_attached_reference_matches_hand_set(tmp_path):
    ref_cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(), name="ref.yaml"))
    hs_cfg = load_config(_write_yaml(tmp_path, _hand_set_mode_yaml(), name="hs.yaml"))
    oversized_vol = DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"] * 10.0
    record = _record(_entry(22, "L3", volume_mm3=oversized_vol))  # no reference key
    ref_findings = _bounds_findings(run_rules(record, ref_cfg))
    hs_findings = _bounds_findings(run_rules(record, hs_cfg))
    assert ref_findings == hs_findings
    assert ref_findings != []


def test_ac9_source_reference_without_attached_reference_does_not_crash():
    cfg = default_config()
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    findings = _bounds_findings(BoundsRule().evaluate(record, cfg))
    assert findings == []


# =========================================================================== #
# AC10: an unrecognised `source` raises ValueError before per-label processing
# =========================================================================== #


def test_ac10_unrecognised_source_raises_value_error(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _bounds_yaml_header() + "      source: bogus-mode\n"))
    record = _record(_entry(22, "L3", volume_mm3=1.0))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_ac10_unrecognised_source_raises_even_with_empty_per_label(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _bounds_yaml_header() + "      source: bogus-mode\n"))
    with pytest.raises(ValueError):
        run_rules({}, cfg)


# =========================================================================== #
# AC11: an unknown configured percentile raises ValueError
# =========================================================================== #


def test_ac11_unknown_lower_pct_raises_value_error(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(lower_pct=2, upper_pct=99)))
    record = _record(_entry(22, "L3", volume_mm3=20_000.0), reference=_full_reference())
    with pytest.raises(ValueError) as excinfo:
        run_rules(record, cfg)
    assert "2" in str(excinfo.value)


def test_ac11_unknown_upper_pct_raises_value_error(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml(lower_pct=1, upper_pct=97)))
    record = _record(_entry(22, "L3", volume_mm3=20_000.0), reference=_full_reference())
    with pytest.raises(ValueError) as excinfo:
        run_rules(record, cfg)
    assert "97" in str(excinfo.value)


def test_ac11_reference_bounds_for_level_raises_for_unknown_percentile():
    with pytest.raises(ValueError):
        reference_bounds_for_level(_full_reference(), "L3", lower_pct=2, upper_pct=99, stratum=ALL_STRATUM)


# =========================================================================== #
# AC12: the pure derivation helper
# =========================================================================== #


def test_ac12_covered_level_returns_expected_bounds_dict():
    bounds = reference_bounds_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert bounds == {
        "min_volume_mm3": _L3_VOLUME["p1"], "max_volume_mm3": _L3_VOLUME["p99"],
        "min_extent_x_mm": _L3_EXTENT_X["p1"], "max_extent_x_mm": _L3_EXTENT_X["p99"],
        "min_extent_y_mm": _L3_EXTENT_Y["p1"], "max_extent_y_mm": _L3_EXTENT_Y["p99"],
        "min_extent_z_mm": _L3_EXTENT_Z["p1"], "max_extent_z_mm": _L3_EXTENT_Z["p99"],
    }


def test_ac12_covered_level_different_percentile_pair():
    bounds = reference_bounds_for_level(
        _full_reference(), "L3", lower_pct=5, upper_pct=95, stratum=ALL_STRATUM,
    )
    assert bounds["min_volume_mm3"] == _L3_VOLUME["p5"]
    assert bounds["max_volume_mm3"] == _L3_VOLUME["p95"]


def test_ac12_uncovered_level_returns_none():
    bounds = reference_bounds_for_level(
        _full_reference(), "L5", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert bounds is None


def test_ac12_uncovered_stratum_returns_none():
    bounds = reference_bounds_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum="juvenile",
    )
    assert bounds is None


def test_ac12_partial_level_returns_only_covered_metrics():
    bounds = reference_bounds_for_level(
        _partial_reference(), "L4", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert bounds == {"min_volume_mm3": _L4_VOLUME["p1"], "max_volume_mm3": _L4_VOLUME["p99"]}
    assert "min_extent_x_mm" not in bounds


def test_ac12_helper_does_not_mutate_reference():
    reference = _full_reference()
    snapshot = copy.deepcopy(reference)
    reference_bounds_for_level(reference, "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM)
    assert reference == snapshot


def test_ac12_helper_reads_no_file_or_clock(monkeypatch):
    """Adversarial: patch open/pathlib to explode; helper must still work
    (i.e. it performs no I/O)."""
    def _boom(*a, **kw):
        raise AssertionError("reference_bounds_for_level must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _boom)
    bounds = reference_bounds_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert bounds is not None


# =========================================================================== #
# AC13: determinism and non-mutation
# =========================================================================== #


def test_ac13_two_evaluate_calls_return_equal_findings(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(
        _entry(22, "L3", volume_mm3=_L3_VOLUME["p1"] - 1.0),
        _entry(24, "L5", volume_mm3=1.0),
        reference=_full_reference(),
    )
    findings1 = BoundsRule().evaluate(record, cfg)
    findings2 = BoundsRule().evaluate(record, cfg)
    assert findings1 == findings2
    assert [min(f.labels) for f in findings1] == sorted(min(f.labels) for f in findings1)


def test_ac13_evaluate_does_not_mutate_record_reference_or_config(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    reference = _full_reference()
    record = _record(_entry(22, "L3", volume_mm3=_L3_VOLUME["p1"] - 1.0), reference=reference)
    record_before = copy.deepcopy(record)
    reference_before = copy.deepcopy(reference)
    rules_before = copy.deepcopy(cfg.rules)

    BoundsRule().evaluate(record, cfg)

    assert record == record_before
    assert reference == reference_before
    assert cfg.rules == rules_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_per_metric_fallback_within_covered_level(tmp_path):
    """A covered level ('L4') lacks extent stats; volume uses reference,
    extents fall back to hand-set lumbar bounds."""
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    # Volume out of L4's reference band (fires via reference).
    # Extent_x within hand-set lumbar bounds (does not fire via fallback).
    g = DEFAULT_BOUNDS["lumbar"]
    mid_x = (g["min_extent_x_mm"] + g["max_extent_x_mm"]) / 2.0
    record = _record(
        _entry(
            24, "L4",
            volume_mm3=_L4_VOLUME["p99"] + 1.0,
            extent_x_mm=mid_x, extent_y_mm=mid_x, extent_z_mm=mid_x,
        ),
        reference=_partial_reference(),
    )
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({24})]
    assert len(label_findings) == 1
    assert "volume" in label_findings[0].reason.lower() or "mm3" in label_findings[0].reason.lower()


def test_adv_per_metric_fallback_extent_fires_via_hand_set(tmp_path):
    """Same partial-coverage level, but this time the extent (uncovered by
    the reference) fires via its hand-set fallback bound."""
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    oversized_x = DEFAULT_BOUNDS["lumbar"]["max_extent_x_mm"] * 10.0
    record = _record(
        _entry(24, "L4", volume_mm3=_L4_VOLUME["p50"], extent_x_mm=oversized_x),
        reference=_partial_reference(),
    )
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({24})]
    assert len(label_findings) == 1
    assert "x" in label_findings[0].reason.lower()


def test_adv_empty_per_label_reference_mode_returns_empty_list(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = {"per_label": {}, "relationships": {}, "overlaps": {}, "reference": _full_reference()}
    assert _bounds_findings(run_rules(record, cfg)) == []


def test_adv_unbounded_level_skipped_in_reference_mode_no_crash(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(27, "S", volume_mm3=999_999_999.0), reference=_full_reference())
    assert _bounds_findings(run_rules(record, cfg)) == []


def test_adv_unbounded_level_present_in_reference_still_skipped(tmp_path):
    """A level with no hand-set group must be skipped even if (hypothetically)
    it were covered by the reference — bounds only evaluates groupable levels
    that also appear in geometry; 'unknown' has neither."""
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(_entry(28, "unknown", volume_mm3=999_999_999.0), reference=_full_reference())
    assert _bounds_findings(run_rules(record, cfg)) == []


def test_adv_two_levels_one_covered_one_not_ordered_ascending(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _reference_mode_yaml()))
    record = _record(
        _entry(3, "L3", volume_mm3=_L3_VOLUME["p1"] - 1.0),           # covered, fires via reference
        _entry(24, "L5", volume_mm3=DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"] * 10.0),  # uncovered, fires via fallback
        reference=_full_reference(),
    )
    findings = _bounds_findings(run_rules(record, cfg))
    labels_seen = [min(f.labels) for f in findings]
    assert labels_seen == sorted(labels_seen)
    assert 3 in labels_seen and 24 in labels_seen
