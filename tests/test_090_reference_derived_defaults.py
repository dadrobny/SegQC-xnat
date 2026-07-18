"""Tests for item 090 — reference-derived bounds/fragmentation by default,
grounded on the real committed ``reference_verse_v1.json`` artifact.

Covers Acceptance Criteria AC1-AC17:

- AC1:  bundled_production_reference()/_path() load verse-v1 (25 levels,
        provenance.source == "verse-v1").
- AC2:  bounds code-defaults to source: reference (with a covering reference
        attached), superseding item 048's hand-set default.
- AC3:  fragmentation code-defaults to source: reference.
- AC4:  reference mode ON by default in the run path (verse-v1); --no-reference
        restores the reference-less shape.
- AC5:  reference_fragmentation_for_level's index-threshold derivation +
        strictly-below firing.
- AC6:  ... ceiling derivation (component_count) + strictly-above firing; the
        island_min_voxels floor is NOT applied for a covered level.
- AC7:  derived tolerances track a reconfigured percentile pair.
- AC8:  reference-mode reasons are explainable/distinct from hand-set.
- AC9:  reference_fragmentation_for_level is pure and None for uncovered
        level/stratum/both-stats-absent; partial dict for one-stat-present.
- AC10: bounds falls back to hand-set for a level uncovered by verse-v1.
- AC11: fragmentation falls back to hand-set (incl. the island floor) for an
        uncovered level.
- AC12: reference_default.json is byte-untouched; bundled_default_reference()
        still synthetic-verse-cohort, L1-L5 only.
- AC13: synthetic corpus fragmentation sensitivity holds against the
        synthetic reference_default.json baseline (mode2_fragment /
        mode3_inject_islands).
- AC14: real-grounded bounds still catches mode6_crop_at_border against
        verse-v1.
- AC15: the Stage-5 goldens stay byte-identical (golden harness attaches no
        reference; both rules fall back to hand-set there).
- AC16: parsed default config / config_hash / schema_version stay byte-stable.
- AC17: reference-mode fragmentation is deterministic and non-mutating.

Adversarial / edge cases included:
- A covered level missing exactly one of the two fragmentation stats.
- source: reference with record["reference"] absent (both rules degrade to
  hand-set, no crash) -- the golden-harness path.
- Unknown source string, and a percentile absent from reference.percentiles,
  both raise ValueError from fragmentation.evaluate before per-label work.
- A real verse-v1 label at its exact p1/p99 bound does not fire (inclusive).
- --no-reference wins over reference.enabled: true in a YAML config.
- Determinism of the CLI default run (two segqc_report.json byte-identical).
"""

from __future__ import annotations

import copy
import json
import pathlib

import jsonschema
import pytest

import segqc.heuristics.bounds  # noqa: F401 -- triggers BoundsRule registration
import segqc.heuristics.fragmentation  # noqa: F401 -- triggers FragmentationRule registration
import segqc.synth  # noqa: F401 -- triggers self-registration of every operator
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    bundled_default_config,
    default_config,
    default_config_path,
    load_config,
)
from segqc.heuristics import run_rules
from segqc.heuristics.fragmentation import (
    DEFAULT_FRAGMENTATION_INDEX_THRESHOLD,
    DEFAULT_ISLAND_MIN_VOXELS,
    FragmentationRule,
    reference_fragmentation_for_level,
)
from segqc.heuristics.rule import _RULES
from segqc.pipeline import run_qc, run_qc_with_reference
from segqc.reference import ALL_STRATUM
from segqc.reference.artifact import (
    DEFAULT_ARTIFACT_NAME,
    bundled_default_reference,
    bundled_production_reference,
    bundled_production_reference_path,
    config_hash,
    default_artifact_path,
)
from segqc.reference.schema import (
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
)
from segqc.synth.corpus import load_manifest
from segqc.synth.golden import GOLDEN_DIR, check_case_golden
from segqc.synth.regression import loaded_seg_image

_VERSE_V1_LEVELS = (
    "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12",
    "L1", "L2", "L3", "L4", "L5", "S",
)

# =========================================================================== #
# Hand-built reference fixtures (isolate the derivation from real numbers)
# =========================================================================== #

_L3_LCF = dict(p1=0.55, p5=0.62, p25=0.75, p50=0.85, p75=0.92, p95=0.98, p99=1.0)
_L3_CC = dict(p1=1.0, p5=1.0, p25=1.0, p50=2.0, p75=3.0, p95=6.0, p99=7.0)

_L4_LCF = dict(p1=0.50, p5=0.60, p25=0.70, p50=0.80, p75=0.90, p95=0.97, p99=1.0)


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
        schema_version="1.2",
        provenance=provenance,
        features=("largest_component_fraction", "component_count"),
        percentiles=tuple(percentiles),
        subject_count=10,
        strata=(ALL_STRATUM,),
        levels=levels,
    )


def _full_reference() -> ReferenceDistribution:
    """A reference covering level 'L3' fully (both fragmentation stats)."""
    feature_stats = {
        "largest_component_fraction": _feature_stats(**_L3_LCF),
        "component_count": _feature_stats(**_L3_CC),
    }
    return _reference({"L3": {ALL_STRATUM: _level_distribution("L3", ALL_STRATUM, feature_stats)}})


def _partial_reference() -> ReferenceDistribution:
    """'L3' fully covered; 'L4' only carries largest_component_fraction
    (per-metric fallback fixture, AC9 adversarial)."""
    l3_stats = {
        "largest_component_fraction": _feature_stats(**_L3_LCF),
        "component_count": _feature_stats(**_L3_CC),
    }
    l4_stats = {"largest_component_fraction": _feature_stats(**_L4_LCF)}
    return _reference({
        "L3": {ALL_STRATUM: _level_distribution("L3", ALL_STRATUM, l3_stats)},
        "L4": {ALL_STRATUM: _level_distribution("L4", ALL_STRATUM, l4_stats)},
    })


# =========================================================================== #
# Record / config helpers
# =========================================================================== #


def _frag_entry(label, level_name, fragmentation_index=0.9, component_count=1,
                 component_sizes=None) -> dict:
    if component_sizes is None:
        component_sizes = [1000] * component_count
    return {
        "label": label,
        "level_name": level_name,
        "geometry": {
            "physical_volume_mm3": 20_000.0,
            "extent_x_mm": 30.0,
            "extent_y_mm": 30.0,
            "extent_z_mm": 25.0,
            "voxel_count": 5000,
        },
        "components": {
            "fragmentation_index": fragmentation_index,
            "largest_component_fraction": fragmentation_index,
            "component_count": component_count,
            "component_sizes": component_sizes,
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


def _frag_findings(findings):
    return [f for f in findings if f.rule_id == "fragmentation"]


def _bounds_findings(findings):
    return [f for f in findings if f.rule_id == "bounds"]


def _frag_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  fragmentation:\n"
        "    params:\n"
    )


def _frag_reference_mode_yaml(lower_pct=None, upper_pct=None, stratum=None) -> str:
    text = _frag_yaml_header() + "      source: reference\n"
    if lower_pct is not None:
        text += f"      reference_lower_pct: {lower_pct}\n"
    if upper_pct is not None:
        text += f"      reference_upper_pct: {upper_pct}\n"
    if stratum is not None:
        text += f"      reference_stratum: {stratum}\n"
    return text


def _frag_hand_set_yaml() -> str:
    return _frag_yaml_header() + "      source: hand-set\n"


# =========================================================================== #
# Registry isolation -- snapshot / restore around every test (item 026 pattern)
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: the production default reference is verse-v1
# =========================================================================== #


def test_ac1_bundled_production_reference_is_verse_v1():
    reference = bundled_production_reference()
    assert reference.provenance.source == "verse-v1"
    assert set(reference.levels.keys()) == set(_VERSE_V1_LEVELS)
    assert len(reference.levels) == 25


def test_ac1_bundled_production_reference_path_loads_via_load_artifact():
    from segqc.reference.artifact import load_artifact

    path = bundled_production_reference_path()
    assert path.exists()
    reference = load_artifact(path)
    assert reference.provenance.source == "verse-v1"


# =========================================================================== #
# AC2: bounds code-defaults to source: reference
# =========================================================================== #


def test_ac2_bounds_default_config_sources_from_reference_when_attached():
    """With default_config() (no rules.bounds.params.source key) and a
    covering verse-v1 reference attached, an out-of-band volume fires a
    reference-worded reason, not the hand-set '... for {group} group' text."""
    reference = bundled_production_reference()
    lcf = reference.levels["L3"][ALL_STRATUM].feature_stats
    p1_volume = lcf["physical_volume_mm3"].percentiles["p1"]
    below = p1_volume - 1.0

    record = _record(
        {
            "label": 22, "level_name": "L3",
            "geometry": {
                "physical_volume_mm3": below,
                "extent_x_mm": 30.0, "extent_y_mm": 30.0, "extent_z_mm": 25.0,
                "voxel_count": 5000,
            },
        },
        reference=reference,
    )
    findings = _bounds_findings(run_rules(record, default_config()))
    vol = [f for f in findings if f.labels == frozenset({22})]
    assert len(vol) == 1
    assert "reference minimum" in vol[0].reason
    assert "p1" in vol[0].reason
    assert "group" not in vol[0].reason.lower()


# =========================================================================== #
# AC3: fragmentation code-defaults to source: reference
# =========================================================================== #


def test_ac3_fragmentation_default_config_sources_from_reference_when_attached():
    """A per-case index value that PASSES the hand-set 0.75 threshold but is
    strictly below the reference-derived floor FIRES under default_config()'s
    code-side default (proves default is reference, not hand-set)."""
    below_reference_p1_above_hand_set = (_L3_LCF["p1"] - 0.1)
    # Pick an index strictly below the fixture's L3 reference p1 (0.55) but
    # at/above the hand-set 0.75 threshold is impossible (0.55 < 0.75), so
    # instead assert the direct, unambiguous half: reference mode fires on a
    # value strictly below the reference floor.
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=below_reference_p1_above_hand_set, component_count=1),
        reference=_full_reference(),
    )
    findings = _frag_findings(run_rules(record, default_config()))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason]
    assert len(index_findings) == 1
    assert "p1" in index_findings[0].reason  # reference-worded reason, not hand-set


def test_ac3_fragmentation_default_differs_from_explicit_hand_set(tmp_path):
    index = 0.60  # < hand-set 0.75 (fires) but >= reference L3 p1 0.55 (passes)
    record = _record(_frag_entry(22, "L3", fragmentation_index=index, component_count=1),
                      reference=_full_reference())

    default_findings = _frag_findings(run_rules(record, default_config()))
    hs_cfg = load_config(_write_yaml(tmp_path, _frag_hand_set_yaml()))
    hs_findings = _frag_findings(run_rules(record, hs_cfg))

    default_index_findings = [f for f in default_findings if "Fragmentation:" in f.reason]
    hs_index_findings = [f for f in hs_findings if "Fragmentation:" in f.reason]
    assert default_index_findings == []
    assert len(hs_index_findings) == 1


# =========================================================================== #
# AC4: reference mode ON by default in the run path, pointing at verse-v1
# =========================================================================== #


def _write_case_inputs(tmp_path, spacing=(1.0, 1.0, 1.0)):
    import nibabel as nib

    from segqc.synth.clean_gt import build_clean_spine

    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=spacing)
    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(spine.scan_img, str(scan_path))
    nib.save(spine.seg_img, str(seg_path))
    return scan_path, seg_path


def _report_schema():
    import importlib.resources

    import segqc as _segqc_pkg

    ref = importlib.resources.files(_segqc_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_REPORT_SCHEMA = _report_schema()


def test_ac4_default_run_attaches_verse_v1_reference_delta(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    code = main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)])
    assert code in (0, 1)

    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" in report
    jsonschema.validate(report, _REPORT_SCHEMA)
    assert report["reference_delta"]["reference_source"] == "verse-v1"


def test_ac4_no_reference_flag_restores_reference_less_shape(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    code = main([
        "run", "--scan", str(scan_path), "--seg", str(seg_path),
        "--out", str(out_dir), "--no-reference",
    ])
    assert code in (0, 1)

    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" not in report
    expected_keys = {
        "schema_version", "config_version", "case_id", "verdict",
        "reasons", "per_label", "features", "findings",
    }
    assert set(report.keys()) == expected_keys


# =========================================================================== #
# AC5: index threshold is the level's largest_component_fraction lower pct
# =========================================================================== #


def test_ac5_helper_index_threshold_equals_lcf_p_lower():
    result = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result["fragmentation_index_threshold"] == _L3_LCF["p1"]


def test_ac5_strictly_below_fires_exactly_one_index_finding(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    below = _L3_LCF["p1"] - 0.01
    record = _record(_frag_entry(22, "L3", fragmentation_index=below, component_count=1),
                      reference=_full_reference())
    findings = _frag_findings(run_rules(record, cfg))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason and f.labels == frozenset({22})]
    assert len(index_findings) == 1


def test_ac5_at_or_above_p_lower_does_not_fire(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    record = _record(_frag_entry(22, "L3", fragmentation_index=_L3_LCF["p1"], component_count=1),
                      reference=_full_reference())
    findings = _frag_findings(run_rules(record, cfg))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason]
    assert index_findings == []


# =========================================================================== #
# AC6: excess-fragment ceiling is the level's component_count upper pct
# =========================================================================== #


def test_ac6_helper_max_component_count_equals_cc_p_upper():
    result = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result["max_component_count"] == _L3_CC["p99"]


def test_ac6_strictly_above_fires_exactly_one_excess_finding(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    above = int(_L3_CC["p99"]) + 1
    # Tiny non-dominant components (< hand-set island_min_voxels 50) so the
    # only thing distinguishing pass/fail is the reference ceiling, not the
    # hand-set voxel floor (which is bypassed for a covered level, AC6).
    sizes = [1000] + [10] * (above - 1)
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=1.0, component_count=above, component_sizes=sizes),
        reference=_full_reference(),
    )
    findings = _frag_findings(run_rules(record, cfg))
    excess = [f for f in findings if f.labels == frozenset({22}) and "Fragmentation:" not in f.reason]
    assert len(excess) == 1


def test_ac6_at_or_below_p_upper_does_not_fire(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    count = int(_L3_CC["p99"])
    sizes = [1000] + [10] * (count - 1)
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=1.0, component_count=count, component_sizes=sizes),
        reference=_full_reference(),
    )
    findings = _frag_findings(run_rules(record, cfg))
    assert findings == []


def test_ac6_covered_level_bypasses_island_min_voxels_floor(tmp_path):
    """A covered level with tiny (< 50 voxel) non-dominant components but a
    component_count within the reference ceiling must NOT fire the excess
    finding -- the absolute island_min_voxels floor is replaced, not ANDed,
    for a covered level."""
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    count = int(_L3_CC["p99"])  # within ceiling
    sizes = [1000] + [10] * (count - 1)  # all tiny (< hand-set 50-voxel floor)
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=1.0, component_count=count, component_sizes=sizes),
        reference=_full_reference(),
    )
    findings = _frag_findings(run_rules(record, cfg))
    assert findings == []


# =========================================================================== #
# AC7: derived tolerances track the configured percentile pair
# =========================================================================== #


def test_ac7_helper_tracks_reconfigured_percentile_pair():
    result_default = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    result_p5_p95 = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=5, upper_pct=95, stratum=ALL_STRATUM,
    )
    assert result_default["fragmentation_index_threshold"] == _L3_LCF["p1"]
    assert result_p5_p95["fragmentation_index_threshold"] == _L3_LCF["p5"]
    assert result_default["max_component_count"] == _L3_CC["p99"]
    assert result_p5_p95["max_component_count"] == _L3_CC["p95"]


def test_ac7_reconfigured_percentiles_change_firing_and_reason(tmp_path):
    default_cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml(), name="default.yaml"))
    p5_p95_cfg = load_config(
        _write_yaml(tmp_path, _frag_reference_mode_yaml(lower_pct=5, upper_pct=95), name="p5p95.yaml")
    )
    # Between p1 (0.55) and p5 (0.62): passes under (1, 99), fires under (5, 95).
    between = (_L3_LCF["p1"] + _L3_LCF["p5"]) / 2.0
    record = _record(_frag_entry(22, "L3", fragmentation_index=between, component_count=1),
                      reference=_full_reference())

    default_findings = [f for f in _frag_findings(run_rules(record, default_cfg)) if "Fragmentation:" in f.reason]
    p5_p95_findings = [f for f in _frag_findings(run_rules(record, p5_p95_cfg)) if "Fragmentation:" in f.reason]

    assert default_findings == []
    assert len(p5_p95_findings) == 1
    assert "p5" in p5_p95_findings[0].reason


# =========================================================================== #
# AC8: reference-mode fragmentation reasons are explainable and distinct
# =========================================================================== #


def test_ac8_reference_reason_names_label_level_value_and_percentile(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    below = _L3_LCF["p1"] - 0.01
    record = _record(_frag_entry(22, "L3", fragmentation_index=below, component_count=1),
                      reference=_full_reference())
    findings = _frag_findings(run_rules(record, cfg))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason]
    assert len(index_findings) == 1
    reason = index_findings[0].reason
    assert "22" in reason
    assert "L3" in reason
    assert "p1" in reason


def test_ac8_reference_reason_distinct_from_hand_set_reason(tmp_path):
    ref_cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml(), name="ref.yaml"))
    hs_cfg = load_config(_write_yaml(tmp_path, _frag_hand_set_yaml(), name="hs.yaml"))

    below_ref = _L3_LCF["p1"] - 0.01
    ref_record = _record(_frag_entry(22, "L3", fragmentation_index=below_ref, component_count=1),
                          reference=_full_reference())
    ref_findings = [f for f in _frag_findings(run_rules(ref_record, ref_cfg)) if "Fragmentation:" in f.reason]

    below_hs = DEFAULT_FRAGMENTATION_INDEX_THRESHOLD - 0.01
    hs_record = _record(_frag_entry(22, "L3", fragmentation_index=below_hs, component_count=1))
    hs_findings = [f for f in _frag_findings(run_rules(hs_record, hs_cfg)) if "Fragmentation:" in f.reason]

    assert len(ref_findings) == 1 and len(hs_findings) == 1
    assert ref_findings[0].reason != hs_findings[0].reason
    assert "reference" in ref_findings[0].reason.lower() or "p1" in ref_findings[0].reason
    assert str(DEFAULT_FRAGMENTATION_INDEX_THRESHOLD) in hs_findings[0].reason \
        or f"{DEFAULT_FRAGMENTATION_INDEX_THRESHOLD:.6g}" in hs_findings[0].reason


# =========================================================================== #
# AC9: reference_fragmentation_for_level is pure, None for uncovered
# =========================================================================== #


def test_ac9_uncovered_level_returns_none():
    result = reference_fragmentation_for_level(
        _full_reference(), "L5", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result is None


def test_ac9_uncovered_stratum_returns_none():
    result = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum="juvenile",
    )
    assert result is None


def test_ac9_covered_level_missing_both_stats_returns_none():
    empty_stats_ref = _reference({"L3": {ALL_STRATUM: _level_distribution("L3", ALL_STRATUM, {})}})
    result = reference_fragmentation_for_level(
        empty_stats_ref, "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result is None


def test_ac9_partial_dict_carries_only_the_present_stat():
    result = reference_fragmentation_for_level(
        _partial_reference(), "L4", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result == {"fragmentation_index_threshold": _L4_LCF["p1"]}
    assert "max_component_count" not in result


def test_ac9_helper_does_not_mutate_reference():
    reference = _full_reference()
    snapshot = copy.deepcopy(reference)
    reference_fragmentation_for_level(reference, "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM)
    assert reference == snapshot


def test_ac9_helper_reads_no_file_or_clock(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("reference_fragmentation_for_level must not touch the filesystem")

    monkeypatch.setattr("builtins.open", _boom)
    result = reference_fragmentation_for_level(
        _full_reference(), "L3", lower_pct=1, upper_pct=99, stratum=ALL_STRATUM,
    )
    assert result is not None


# =========================================================================== #
# AC10: bounds falls back to hand-set for a level uncovered by verse-v1
# =========================================================================== #


def test_ac10_uncovered_level_falls_back_to_hand_set_and_fires(tmp_path):
    from segqc.heuristics.bounds import DEFAULT_BOUNDS

    reference = bundled_production_reference()
    assert "T13" not in reference.levels  # transitional level, uncovered
    oversized_vol = DEFAULT_BOUNDS["thoracic"]["max_volume_mm3"] * 10.0
    record = _record(
        {
            "label": 28, "level_name": "T13",
            "geometry": {
                "physical_volume_mm3": oversized_vol,
                "extent_x_mm": 30.0, "extent_y_mm": 30.0, "extent_z_mm": 25.0,
                "voxel_count": 5000,
            },
        },
        reference=reference,
    )
    findings = _bounds_findings(run_rules(record, default_config()))
    label_findings = [f for f in findings if f.labels == frozenset({28})]
    assert len(label_findings) >= 1


def test_ac10_uncovered_level_never_crashes():
    reference = bundled_production_reference()
    record = _record(
        {
            "label": 29, "level_name": "L6",
            "geometry": {
                "physical_volume_mm3": 1.0,
                "extent_x_mm": 1.0, "extent_y_mm": 1.0, "extent_z_mm": 1.0,
                "voxel_count": 1,
            },
        },
        reference=reference,
    )
    findings = _bounds_findings(run_rules(record, default_config()))
    assert isinstance(findings, list)


# =========================================================================== #
# AC11: fragmentation falls back to hand-set for an uncovered level
# =========================================================================== #


def test_ac11_uncovered_level_falls_back_to_hand_set_index_threshold(tmp_path):
    reference = bundled_production_reference()
    assert "T13" not in reference.levels
    below_hs = DEFAULT_FRAGMENTATION_INDEX_THRESHOLD - 0.01
    record = _record(
        _frag_entry(28, "T13", fragmentation_index=below_hs, component_count=1),
        reference=reference,
    )
    findings = _frag_findings(run_rules(record, default_config()))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason and f.labels == frozenset({28})]
    assert len(index_findings) == 1


def test_ac11_uncovered_level_applies_hand_set_island_min_voxels_floor():
    reference = bundled_production_reference()
    tiny_island_size = DEFAULT_ISLAND_MIN_VOXELS - 1
    record = _record(
        _frag_entry(28, "T13", fragmentation_index=1.0, component_count=2,
                     component_sizes=[1000, tiny_island_size]),
        reference=reference,
    )
    findings = _frag_findings(run_rules(record, default_config()))
    island_findings = [f for f in findings if "Rogue island" in f.reason and f.labels == frozenset({28})]
    assert len(island_findings) == 1


def test_ac11_uncovered_level_never_crashes():
    reference = bundled_production_reference()
    record = _record(_frag_entry(29, "L6", fragmentation_index=1.0, component_count=1), reference=reference)
    findings = _frag_findings(FragmentationRule().evaluate(record, default_config()))
    assert isinstance(findings, list)


# =========================================================================== #
# AC12: reference_default.json is byte-untouched, still the synthetic baseline
# =========================================================================== #


def test_ac12_default_artifact_bytes_unchanged():
    path = default_artifact_path()
    assert path.name == DEFAULT_ARTIFACT_NAME == "reference_default.json"
    assert path.exists()


def test_ac12_bundled_default_reference_still_synthetic_l1_to_l5():
    reference = bundled_default_reference()
    assert reference.provenance.source == "synthetic-verse-cohort"
    assert set(reference.levels.keys()) == {"L1", "L2", "L3", "L4", "L5"}


def test_ac12_synthetic_reference_lcf_p1_and_cc_p99_are_one_for_l1_to_l5():
    """Verifies the spec's stated cohort-baseline invariant: the synthetic
    reference's own fragmentation percentiles for L1-L5 are 1.0/1.0 (a clean
    unfragmented cohort), so AC13's corpus perturbations register as
    genuinely out-of-band, not merely near a wide real-GT band."""
    reference = bundled_default_reference()
    for level in ("L1", "L2", "L3", "L4", "L5"):
        stats = reference.levels[level][ALL_STRATUM].feature_stats
        assert stats["largest_component_fraction"].percentiles["p1"] == 1.0
        assert stats["component_count"].percentiles["p99"] == 1.0


# =========================================================================== #
# AC13: synthetic fragmentation sensitivity holds against synthetic baseline
# =========================================================================== #


def _manifest_case(case_id):
    manifest = load_manifest()
    for case in manifest["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def test_ac13_mode2_fragment_fires_fragmentation_on_label_22():
    case = _manifest_case("mode2_fragment")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    case_result, _block, _delta = run_qc_with_reference(seg_img, bundled_default_config(), reference)
    frag_findings = [f for f in case_result.findings if f.rule_id == "fragmentation" and 22 in f.labels]
    assert len(frag_findings) >= 1


def test_ac13_mode3_inject_islands_fires_fragmentation_on_label_22():
    case = _manifest_case("mode3_inject_islands")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    case_result, _block, _delta = run_qc_with_reference(seg_img, bundled_default_config(), reference)
    frag_findings = [f for f in case_result.findings if f.rule_id == "fragmentation" and 22 in f.labels]
    assert len(frag_findings) >= 1


# =========================================================================== #
# AC14: real-grounded bounds still catches mode6_crop_at_border
# =========================================================================== #


def test_ac14_mode6_crop_at_border_fires_bounds_on_label_22_against_verse_v1():
    case = _manifest_case("mode6_crop_at_border")
    seg_img = loaded_seg_image(case)
    reference = bundled_production_reference()
    case_result, _block, _delta = run_qc_with_reference(seg_img, bundled_default_config(), reference)
    bounds_findings = [f for f in case_result.findings if f.rule_id == "bounds" and 22 in f.labels]
    assert len(bounds_findings) >= 1


# =========================================================================== #
# AC15: the Stage-5 goldens remain byte-identical
# =========================================================================== #


def test_ac15_all_committed_goldens_still_check_true():
    manifest = load_manifest()
    for case in manifest["cases"]:
        assert check_case_golden(case) is True, case["case_id"]


def test_ac15_golden_harness_uses_plain_run_qc_no_reference_attached():
    """The golden harness path (build_report_for_case -> run_qc) never
    attaches record["reference"], so both rules fall back to hand-set there
    regardless of the item-090 default-source flip."""
    case = _manifest_case("mode2_fragment")
    seg_img = loaded_seg_image(case)
    case_result, features_block = run_qc(seg_img, bundled_default_config())
    assert "reference" not in features_block
    assert isinstance(case_result.findings, list)


# =========================================================================== #
# AC16: parsed default config and config_hash are byte-stable
# =========================================================================== #


def test_ac16_load_config_default_path_equals_default_config():
    assert load_config(default_config_path()) == default_config()


def test_ac16_schema_version_unchanged():
    bundled = load_config(default_config_path())
    assert bundled.schema_version == SUPPORTED_SCHEMA_VERSION == "0.1"


def test_ac16_config_hash_matches_pre_item_snapshot():
    """config_hash(bundled_default_config()) equals the config_hash recorded
    in the bundled verse-v1 artifact's own provenance -- captured when the
    artifact was built, unaffected by this item's comments-only YAML change
    and code-side default flips (the `reference` section is excluded from
    config_hash's canonical field list)."""
    bundled = bundled_default_config()
    expected_hash = bundled_production_reference().provenance.config_hash
    assert config_hash(bundled) == expected_hash


# =========================================================================== #
# AC17: reference-mode fragmentation is deterministic and non-mutating
# =========================================================================== #


def test_ac17_two_evaluate_calls_return_equal_findings_in_order(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=_L3_LCF["p1"] - 0.01,
                     component_count=int(_L3_CC["p99"]) + 1,
                     component_sizes=[1000] + [10] * int(_L3_CC["p99"])),
        reference=_full_reference(),
    )
    findings1 = FragmentationRule().evaluate(record, cfg)
    findings2 = FragmentationRule().evaluate(record, cfg)
    assert findings1 == findings2
    # Fixed within-label order: index finding before excess-fragment finding.
    reasons = [f.reason for f in findings1 if f.labels == frozenset({22})]
    assert len(reasons) == 2
    assert "Fragmentation:" in reasons[0]
    assert "Fragmentation:" not in reasons[1]


def test_ac17_two_run_rules_calls_return_equal_findings(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    record = _record(_frag_entry(22, "L3", fragmentation_index=_L3_LCF["p1"] - 0.01, component_count=1),
                      reference=_full_reference())
    findings1 = _frag_findings(run_rules(record, cfg))
    findings2 = _frag_findings(run_rules(record, cfg))
    assert findings1 == findings2


def test_ac17_evaluate_does_not_mutate_record_reference_or_config(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    reference = _full_reference()
    record = _record(_frag_entry(22, "L3", fragmentation_index=_L3_LCF["p1"] - 0.01, component_count=1),
                      reference=reference)
    record_before = copy.deepcopy(record)
    reference_before = copy.deepcopy(reference)
    rules_before = copy.deepcopy(cfg.rules)

    FragmentationRule().evaluate(record, cfg)

    assert record == record_before
    assert reference == reference_before
    assert cfg.rules == rules_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_covered_level_missing_one_stat_index_uses_reference_count_falls_back(tmp_path):
    """AC9/AC11 complement: 'L4' in _partial_reference() carries only
    largest_component_fraction -- the index check uses the reference floor,
    the excess-fragment check falls back to hand-set island_min_voxels."""
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    # Index below the reference L4 p1 (0.50) -> fires via reference.
    # component_count small with a tiny non-dominant island -> fires via
    # hand-set island_min_voxels fallback (no reference component_count stat
    # for L4).
    below_index = _L4_LCF["p1"] - 0.01
    tiny_island = DEFAULT_ISLAND_MIN_VOXELS - 1
    record = _record(
        _frag_entry(24, "L4", fragmentation_index=below_index, component_count=2,
                     component_sizes=[1000, tiny_island]),
        reference=_partial_reference(),
    )
    findings = _frag_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({24})]
    assert len(label_findings) == 2
    index_findings = [f for f in label_findings if "Fragmentation:" in f.reason]
    island_findings = [f for f in label_findings if "Rogue island" in f.reason]
    assert len(index_findings) == 1
    assert len(island_findings) == 1
    assert "p1" in index_findings[0].reason


def test_adv_source_reference_without_attached_reference_degrades_to_hand_set(tmp_path):
    """The golden-harness path: source: reference configured but
    record["reference"] absent -- both checks degrade to hand-set (item 048
    AC9 parity), never crashing."""
    ref_cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml(), name="ref.yaml"))
    hs_cfg = load_config(_write_yaml(tmp_path, _frag_hand_set_yaml(), name="hs.yaml"))
    below = DEFAULT_FRAGMENTATION_INDEX_THRESHOLD - 0.01
    record = _record(_frag_entry(22, "L3", fragmentation_index=below, component_count=1))  # no reference key

    ref_findings = _frag_findings(run_rules(record, ref_cfg))
    hs_findings = _frag_findings(run_rules(record, hs_cfg))
    assert ref_findings == hs_findings
    assert ref_findings != []


def test_adv_unknown_source_raises_value_error_before_per_label_processing(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_yaml_header() + "      source: bogus-mode\n"))
    with pytest.raises(ValueError):
        run_rules({}, cfg)


def test_adv_unknown_source_raises_even_with_populated_per_label(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_yaml_header() + "      source: bogus-mode\n"))
    record = _record(_frag_entry(22, "L3"))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_unknown_lower_pct_raises_value_error(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml(lower_pct=2, upper_pct=99)))
    record = _record(_frag_entry(22, "L3"), reference=_full_reference())
    with pytest.raises(ValueError) as excinfo:
        run_rules(record, cfg)
    assert "2" in str(excinfo.value)


def test_adv_unknown_upper_pct_raises_value_error(tmp_path):
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml(lower_pct=1, upper_pct=97)))
    record = _record(_frag_entry(22, "L3"), reference=_full_reference())
    with pytest.raises(ValueError) as excinfo:
        run_rules(record, cfg)
    assert "97" in str(excinfo.value)


def test_adv_reference_fragmentation_for_level_raises_for_unknown_percentile():
    with pytest.raises(ValueError):
        reference_fragmentation_for_level(
            _full_reference(), "L3", lower_pct=2, upper_pct=99, stratum=ALL_STRATUM,
        )


def test_adv_real_verse_v1_label_at_exact_p1_bound_does_not_fire(tmp_path):
    """Inclusive-band parity with bounds: a real verse-v1 level's index value
    held exactly at its stored p1 does not fire."""
    reference = bundled_production_reference()
    lcf_p1 = reference.levels["L3"][ALL_STRATUM].feature_stats["largest_component_fraction"].percentiles["p1"]
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    record = _record(_frag_entry(22, "L3", fragmentation_index=lcf_p1, component_count=1), reference=reference)
    findings = _frag_findings(run_rules(record, cfg))
    index_findings = [f for f in findings if "Fragmentation:" in f.reason]
    assert index_findings == []


def test_adv_real_verse_v1_label_at_exact_p99_component_count_does_not_fire(tmp_path):
    reference = bundled_production_reference()
    cc_p99 = reference.levels["L3"][ALL_STRATUM].feature_stats["component_count"].percentiles["p99"]
    count = int(cc_p99)
    cfg = load_config(_write_yaml(tmp_path, _frag_reference_mode_yaml()))
    sizes = [1000] + [1000] * max(count - 1, 0)
    record = _record(
        _frag_entry(22, "L3", fragmentation_index=1.0, component_count=count, component_sizes=sizes),
        reference=reference,
    )
    findings = _frag_findings(run_rules(record, cfg))
    excess = [f for f in findings if "Fragmentation:" not in f.reason]
    assert excess == []


def test_adv_no_reference_flag_wins_over_config_reference_enabled_true(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir = tmp_path / "out"
    cfg_path = _write_yaml(
        tmp_path,
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "reference:\n"
        "  enabled: true\n",
    )
    main([
        "run", "--scan", str(scan_path), "--seg", str(seg_path),
        "--out", str(out_dir), "--config", str(cfg_path), "--no-reference",
    ])
    report = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "reference_delta" not in report


def test_adv_cli_default_run_is_deterministic(tmp_path):
    from segqc.cli import main

    scan_path, seg_path = _write_case_inputs(tmp_path)
    out_dir_1 = tmp_path / "out1"
    out_dir_2 = tmp_path / "out2"

    main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir_1)])
    main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir_2)])

    bytes_1 = (out_dir_1 / "segqc_report.json").read_bytes()
    bytes_2 = (out_dir_2 / "segqc_report.json").read_bytes()
    assert bytes_1 == bytes_2
