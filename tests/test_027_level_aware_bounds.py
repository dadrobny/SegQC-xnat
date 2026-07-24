"""Tests for item 027 — level-aware min/max bounds rules (volume & extent).

Covers all 14 Acceptance Criteria plus adversarial and edge-case inputs:

- AC1:   BoundsRule registers under rule_id == "bounds"; discoverable via registry.
- AC2:   No findings when all labels lie within their level-aware bounds.
- AC3:   An oversized physical_volume_mm3 fires a Finding for the correct label/level.
- AC4:   An undersized physical_volume_mm3 fires a Finding for the correct label/level.
- AC5:   An out-of-range extent (x/y/z) fires a Finding naming the offending axis.
- AC6:   Bounds are level-aware: same measurement judged against its group's bounds.
- AC7:   Config-supplied bounds override the shipped defaults (tight fires; loose passes).
- AC8:   Shipped hand-set defaults fire on a grossly oversized label; plausible label passes.
- AC9:   Physical (mm3) volume is compared, not voxel count; anisotropy is respected.
- AC10:  Every bounds Finding reason contains the measured value and the violated bound.
- AC11:  Labels in unbounded groups (S, Cocygis, unknown) are always skipped.
- AC12:  Default finding severity is Severity.FLAG; params.severity config overrides it.
- AC13:  The rule is deterministic: two identical runs return equal finding lists in the
         same order.
- AC14:  evaluate on a record with empty or absent per_label returns [] without raising.

Adversarial / edge-case scenarios included:
- Value exactly equal to min or max bound (inclusive) — does not fire.
- Two metrics violated on the same label yield two separate findings.
- level_name from an unrecognised custom convention is skipped without crashing.
- geometry sub-dict missing one metric key — remaining metrics still checked; no crash.
- Unrecognised severity param string raises ValueError (raises path pinned).
- Findings are ordered ascending by label integer for a multi-label record.
- Two labels with identical voxel_count but different physical_volume_mm3 are judged
  independently on the mm3 field (AC9 anisotropy adversarial).
- evaluate does not mutate the caller's record mapping.
- Partial group config override (one key only) — the overridden key takes effect.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

import segfacet.heuristics.bounds  # noqa: F401 — triggers BoundsRule registration
from segfacet.heuristics import Finding, get_rule, iter_rules, run_rules
from segfacet.heuristics.bounds import DEFAULT_BOUNDS
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


def _make_label_entry(
    label: int,
    level_name: str,
    volume_mm3: float = 5000.0,
    extent_x_mm: float = 20.0,
    extent_y_mm: float = 20.0,
    extent_z_mm: float = 30.0,
    voxel_count: int = 5000,
) -> dict:
    """Build a minimal per_label entry matching the build_features_block shape."""
    return {
        "label": label,
        "level_name": level_name,
        "geometry": {
            "physical_volume_mm3": volume_mm3,
            "extent_x_mm": extent_x_mm,
            "extent_y_mm": extent_y_mm,
            "extent_z_mm": extent_z_mm,
            "voxel_count": voxel_count,
        },
    }


def _make_record(*entries: dict) -> dict:
    """Build a feature record whose per_label is keyed by each entry's label int."""
    return {
        "per_label": {e["label"]: e for e in entries},
        "relationships": {},
        "overlaps": {},
    }


def _write_yaml(
    tmp_path: pathlib.Path, content: str, name: str = "config.yaml"
) -> pathlib.Path:
    """Write *content* to a YAML file under *tmp_path* and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _bounds_findings(findings):
    """Filter to only bounds-rule findings."""
    return [f for f in findings if f.rule_id == "bounds"]


def _wide_group_yaml(group: str) -> str:
    """Return a YAML snippet giving *group* permissive bounds (1..1e9)."""
    return (
        f"      {group}:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )


def _tight_group_yaml(group: str) -> str:
    """Return a YAML snippet giving *group* maximally restrictive bounds."""
    return (
        f"      {group}:\n"
        "        min_volume_mm3: 1000000000.0\n"
        "        max_volume_mm3: 1000000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 1.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 1.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 1.0\n"
    )


def _bounds_yaml_header() -> str:
    return (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    params:\n"
    )


# =========================================================================== #
# Registry isolation — snapshot / restore around every test
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot _RULES before each test (includes 'bounds') and restore after.

    The module-level import of segfacet.heuristics.bounds registers BoundsRule
    at collection time; this snapshot captures that state so tests that clear
    or mutate _RULES do not bleed into one another.
    """
    snapshot = dict(_RULES)
    yield
    _RULES.clear()
    _RULES.update(snapshot)


# =========================================================================== #
# AC1: BoundsRule registers under rule_id == "bounds"
# =========================================================================== #


def test_ac1_bounds_rule_is_in_registry():
    """AC1: get_rule('bounds') returns a Rule instance without raising."""
    rule = get_rule("bounds")
    assert rule.rule_id == "bounds"


def test_ac1_bounds_appears_in_iter_rules():
    """AC1: iter_rules() yields at least one rule with rule_id == 'bounds'."""
    assert any(r.rule_id == "bounds" for r in iter_rules())


# =========================================================================== #
# AC2: No findings when every label is within its level-aware bounds
# =========================================================================== #


def test_ac2_no_findings_when_all_labels_within_bounds(tmp_path):
    """AC2: All labels comfortably inside configured bounds produce no bounds findings."""
    content = (
        _bounds_yaml_header()
        + _wide_group_yaml("cervical")
        + _wide_group_yaml("thoracic")
        + _wide_group_yaml("lumbar")
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(
        _make_label_entry(3, "C3", volume_mm3=5000.0),
        _make_label_entry(11, "T5", volume_mm3=10000.0),
        _make_label_entry(22, "L3", volume_mm3=20000.0),
    )
    assert _bounds_findings(run_rules(record, cfg)) == []


# =========================================================================== #
# AC3: Oversized volume fires a finding for the correct label and level
# =========================================================================== #


def test_ac3_oversized_volume_fires_finding(tmp_path):
    """AC3: physical_volume_mm3 above max_volume_mm3 emits a Finding with the correct label."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=5000.0))
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({22})]
    assert len(label_findings) >= 1, "Expected at least one finding for oversized label 22"


def test_ac3_oversized_volume_finding_reason_names_level_and_metric(tmp_path):
    """AC3: The oversized-volume finding reason mentions the level_name and the volume metric."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=5000.0))
    all_findings = _bounds_findings(run_rules(record, cfg))
    vol_finding = next(
        (
            f for f in all_findings
            if f.labels == frozenset({22})
            and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
        ),
        None,
    )
    assert vol_finding is not None, "Expected a finding mentioning 'volume' or 'mm3'"
    reason_lower = vol_finding.reason.lower()
    assert "l3" in reason_lower or "lumbar" in reason_lower, (
        f"Reason should name level 'L3' or 'lumbar'; got {vol_finding.reason!r}"
    )


# =========================================================================== #
# AC4: Undersized volume fires a finding for the correct label and level
# =========================================================================== #


def test_ac4_undersized_volume_fires_finding(tmp_path):
    """AC4: physical_volume_mm3 below min_volume_mm3 emits a Finding with the correct label."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 10000.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=500.0))
    findings = _bounds_findings(run_rules(record, cfg))
    label_findings = [f for f in findings if f.labels == frozenset({3})]
    assert len(label_findings) >= 1, "Expected at least one finding for undersized label 3"


def test_ac4_undersized_volume_reason_names_level_and_metric(tmp_path):
    """AC4: The undersized-volume finding reason names the level and the volume metric."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 10000.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=500.0))
    all_findings = _bounds_findings(run_rules(record, cfg))
    vol_finding = next(
        (
            f for f in all_findings
            if f.labels == frozenset({3})
            and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
        ),
        None,
    )
    assert vol_finding is not None, "Expected a finding mentioning 'volume' or 'mm3'"
    reason_lower = vol_finding.reason.lower()
    assert "c3" in reason_lower or "cervical" in reason_lower, (
        f"Reason should name level 'C3' or 'cervical'; got {vol_finding.reason!r}"
    )


# =========================================================================== #
# AC5: Out-of-range extent fires a finding naming the offending axis
# =========================================================================== #


def test_ac5_oversized_extent_x_fires_finding(tmp_path):
    """AC5: extent_x_mm above max_extent_x_mm emits a Finding for the correct label."""
    content = (
        _bounds_yaml_header()
        + "      thoracic:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(11, "T5", volume_mm3=5000.0, extent_x_mm=50.0))
    all_findings = _bounds_findings(run_rules(record, cfg))
    x_finding = next(
        (
            f for f in all_findings
            if f.labels == frozenset({11})
            and ("_x_" in f.reason or "x" in f.reason.lower())
        ),
        None,
    )
    assert x_finding is not None, "Expected a finding mentioning the x-axis extent"


def test_ac5_undersized_extent_z_fires_finding(tmp_path):
    """AC5: extent_z_mm below min_extent_z_mm emits a Finding naming the z-axis."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 50.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=5000.0, extent_z_mm=5.0))
    all_findings = _bounds_findings(run_rules(record, cfg))
    z_finding = next(
        (
            f for f in all_findings
            if f.labels == frozenset({22})
            and ("_z_" in f.reason or "z" in f.reason.lower())
        ),
        None,
    )
    assert z_finding is not None, "Expected a finding mentioning the z-axis extent"


def test_ac5_extent_finding_labels_correct_label(tmp_path):
    """AC5: The extent finding's labels frozenset contains exactly the offending label."""
    content = (
        _bounds_yaml_header()
        + "      thoracic:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 1.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(11, "T5", volume_mm3=5000.0, extent_x_mm=50.0))
    all_findings = _bounds_findings(run_rules(record, cfg))
    assert all(f.labels == frozenset({11}) for f in all_findings), (
        "Every finding should attribute only label 11"
    )


# =========================================================================== #
# AC6: Bounds are level-aware
# =========================================================================== #


def test_ac6_same_volume_fires_for_cervical_not_lumbar(tmp_path):
    """AC6: 5000 mm3 fires for a cervical label (max 1000) but not a lumbar label (max 100000)."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
        "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 100000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # 5000 mm3 exceeds cervical max (1000) but is within lumbar max (100000)
    record = _make_record(
        _make_label_entry(3, "C3", volume_mm3=5000.0),
        _make_label_entry(22, "L3", volume_mm3=5000.0),
    )
    all_findings = _bounds_findings(run_rules(record, cfg))
    cervical_vol_findings = [
        f for f in all_findings
        if f.labels == frozenset({3})
        and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
    ]
    lumbar_vol_findings = [
        f for f in all_findings
        if f.labels == frozenset({22})
        and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
    ]
    assert len(cervical_vol_findings) >= 1, "C3 should fire (5000 > cervical max 1000)"
    assert lumbar_vol_findings == [], "L3 should not fire (5000 < lumbar max 100000)"


# =========================================================================== #
# AC7: Config-supplied bounds override the shipped defaults
# =========================================================================== #


def test_ac7_tight_config_fires_where_loose_config_passes(tmp_path):
    """AC7: Tightening max_volume_mm3 causes a label that passes loose config to fire."""
    loose_content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 10000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    tight_content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 100.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    loose_cfg = load_config(_write_yaml(tmp_path, loose_content, name="loose.yaml"))
    tight_cfg = load_config(_write_yaml(tmp_path, tight_content, name="tight.yaml"))
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=500.0))
    loose_findings = _bounds_findings(run_rules(record, loose_cfg))
    tight_findings = _bounds_findings(run_rules(record, tight_cfg))
    assert loose_findings == [], "Volume 500 should pass under loose max (10 000 000)"
    assert len(tight_findings) >= 1, "Volume 500 should fire under tight max (100)"


def test_ac7_loose_config_passes_label_that_tight_config_fires(tmp_path):
    """AC7: Loosening max_volume_mm3 passes a label that would fire under a tighter config."""
    tight_content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 500.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    loose_content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 10000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    tight_cfg = load_config(_write_yaml(tmp_path, tight_content, name="tight.yaml"))
    loose_cfg = load_config(_write_yaml(tmp_path, loose_content, name="loose.yaml"))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=5000.0))
    tight_findings = _bounds_findings(run_rules(record, tight_cfg))
    loose_findings = _bounds_findings(run_rules(record, loose_cfg))
    assert len(tight_findings) >= 1, "Volume 5000 should fire under tight max (500)"
    assert loose_findings == [], "Volume 5000 should pass under loose max (10 000 000)"


# =========================================================================== #
# AC8: Shipped hand-set defaults apply when no config is supplied
# =========================================================================== #


def test_ac8_defaults_fire_grossly_oversized_cervical_label():
    """AC8: With default_config(), a 10x-default-max cervical label fires a bounds finding."""
    max_vol = DEFAULT_BOUNDS["cervical"]["max_volume_mm3"]
    oversized_vol = max_vol * 10.0
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=oversized_vol))
    findings = _bounds_findings(run_rules(record, default_config()))
    assert len(findings) >= 1, (
        f"Expected a finding for cervical volume {oversized_vol} (10x default max {max_vol})"
    )


def test_ac8_defaults_pass_anatomically_plausible_lumbar_label():
    """AC8: With default_config(), a mid-range lumbar label produces no bounds findings."""
    g = DEFAULT_BOUNDS["lumbar"]
    mid_vol = (g["min_volume_mm3"] + g["max_volume_mm3"]) / 2.0
    mid_x = (g["min_extent_x_mm"] + g["max_extent_x_mm"]) / 2.0
    mid_y = (g["min_extent_y_mm"] + g["max_extent_y_mm"]) / 2.0
    mid_z = (g["min_extent_z_mm"] + g["max_extent_z_mm"]) / 2.0
    record = _make_record(
        _make_label_entry(
            22, "L3",
            volume_mm3=mid_vol,
            extent_x_mm=mid_x,
            extent_y_mm=mid_y,
            extent_z_mm=mid_z,
        )
    )
    findings = _bounds_findings(run_rules(record, default_config()))
    assert findings == [], (
        f"Mid-range lumbar values should not fire under defaults. Got: {findings}"
    )


# =========================================================================== #
# AC9: Physical (mm3) volume is used, not voxel count
# =========================================================================== #


def test_ac9_physical_mm3_used_not_voxel_count(tmp_path):
    """AC9: Two labels with equal voxel_count but different mm3 are judged on mm3 alone."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 10000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    same_voxels = 1000
    # L3: physical volume within bounds (5000 < max 10000)
    in_bounds = _make_label_entry(22, "L3", volume_mm3=5000.0, voxel_count=same_voxels)
    # L5: same voxel_count but physical volume above max (50000 > 10000)
    out_of_bounds = _make_label_entry(24, "L5", volume_mm3=50000.0, voxel_count=same_voxels)
    record = _make_record(in_bounds, out_of_bounds)
    findings = _bounds_findings(run_rules(record, cfg))
    labels_flagged = {lbl for f in findings for lbl in f.labels}
    assert 24 in labels_flagged, "L5 (50000 mm3, same voxels) should fire"
    assert 22 not in labels_flagged, "L3 (5000 mm3, same voxels) should not fire"


# =========================================================================== #
# AC10: Finding reason reports the measured value and violated bound
# =========================================================================== #


def test_ac10_finding_reason_contains_measured_value(tmp_path):
    """AC10: The bounds finding reason string contains the actual measured volume value."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=9999.0))
    vol_finding = next(
        (
            f for f in _bounds_findings(run_rules(record, cfg))
            if f.labels == frozenset({22})
            and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
        ),
        None,
    )
    assert vol_finding is not None, "Expected a volume-related finding"
    assert "9999" in vol_finding.reason, (
        f"Measured value 9999 not found in reason: {vol_finding.reason!r}"
    )


def test_ac10_finding_reason_contains_violated_bound(tmp_path):
    """AC10: The bounds finding reason string contains the violated bound value."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=9999.0))
    vol_finding = next(
        (
            f for f in _bounds_findings(run_rules(record, cfg))
            if f.labels == frozenset({22})
            and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
        ),
        None,
    )
    assert vol_finding is not None, "Expected a volume-related finding"
    assert "1000" in vol_finding.reason, (
        f"Violated bound 1000.0 not found in reason: {vol_finding.reason!r}"
    )


def test_ac10_finding_reason_is_non_empty_string():
    """AC10: Every bounds finding has a non-empty reason string."""
    max_vol = DEFAULT_BOUNDS["cervical"]["max_volume_mm3"]
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=max_vol * 10.0))
    findings = _bounds_findings(run_rules(record, default_config()))
    assert findings, "Expected at least one finding"
    assert all(isinstance(f.reason, str) and f.reason.strip() for f in findings)


# =========================================================================== #
# AC11: Labels in unbounded groups are skipped
# =========================================================================== #


def test_ac11_label_S_skipped(tmp_path):
    """AC11: A label with level_name 'S' produces no bounds finding regardless of volume."""
    # Use a tight config so anything in any bounded group would fire
    content = _bounds_yaml_header() + _tight_group_yaml("lumbar")
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(27, "S", volume_mm3=999999999.0))
    assert _bounds_findings(run_rules(record, cfg)) == [], (
        "Label 'S' should be skipped"
    )


def test_ac11_label_Cocygis_skipped(tmp_path):
    """AC11: A label with level_name 'Cocygis' produces no bounds finding."""
    content = _bounds_yaml_header() + _tight_group_yaml("lumbar")
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(28, "Cocygis", volume_mm3=999999999.0))
    assert _bounds_findings(run_rules(record, cfg)) == [], (
        "Label 'Cocygis' should be skipped"
    )


def test_ac11_label_unknown_skipped(tmp_path):
    """AC11: A label with level_name 'unknown' produces no bounds finding."""
    content = _bounds_yaml_header() + _tight_group_yaml("cervical")
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(99, "unknown", volume_mm3=999999999.0))
    assert _bounds_findings(run_rules(record, cfg)) == [], (
        "Label 'unknown' should be skipped"
    )


# =========================================================================== #
# AC12: Default severity is FLAG; severity is config-driven
# =========================================================================== #


def test_ac12_default_severity_is_flag(tmp_path):
    """AC12: With no severity param configured, every bounds finding has Severity.FLAG."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=99999.0))
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings, "Expected at least one finding"
    assert all(f.severity is Severity.FLAG for f in findings), (
        f"All bounds findings should have Severity.FLAG by default; got "
        f"{[f.severity for f in findings]}"
    )


def test_ac12_severity_param_fail_overrides_default(tmp_path):
    """AC12: With params.severity = 'fail', every bounds finding has Severity.FAIL."""
    content = (
        _bounds_yaml_header()
        + "      severity: fail\n"
        "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=99999.0))
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings, "Expected at least one finding"
    assert all(f.severity is Severity.FAIL for f in findings), (
        f"All findings should be Severity.FAIL; got {[f.severity for f in findings]}"
    )


def test_ac12_default_severity_without_any_rules_config():
    """AC12: With default_config() (no rules section), findings have Severity.FLAG."""
    max_vol = DEFAULT_BOUNDS["thoracic"]["max_volume_mm3"]
    record = _make_record(_make_label_entry(11, "T5", volume_mm3=max_vol * 10.0))
    findings = _bounds_findings(run_rules(record, default_config()))
    assert findings, "Expected at least one finding"
    assert all(f.severity is Severity.FLAG for f in findings)


# =========================================================================== #
# AC13: The rule is deterministic
# =========================================================================== #


def test_ac13_deterministic_two_runs_identical(tmp_path):
    """AC13: Two successive run_rules calls on the same inputs return equal finding lists."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
        "      thoracic:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 5000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(
        _make_label_entry(2, "C2", volume_mm3=5000.0),   # oversized cervical
        _make_label_entry(9, "T3", volume_mm3=10000.0),  # oversized thoracic
    )
    run1 = _bounds_findings(run_rules(record, cfg))
    run2 = _bounds_findings(run_rules(record, cfg))
    assert run1 == run2, f"Non-deterministic output:\nrun1={run1}\nrun2={run2}"


# =========================================================================== #
# AC14: Empty or absent per_label returns []
# =========================================================================== #


def test_ac14_empty_per_label_returns_empty_list():
    """AC14: evaluate on a record with per_label={} returns [] without raising."""
    record = {"per_label": {}, "relationships": {}, "overlaps": {}}
    findings = _bounds_findings(run_rules(record, default_config()))
    assert findings == []


def test_ac14_absent_per_label_returns_empty_list():
    """AC14: evaluate on a record with no 'per_label' key returns [] without raising."""
    record = {"relationships": {}, "overlaps": {}}
    findings = _bounds_findings(run_rules(record, default_config()))
    assert findings == []


# =========================================================================== #
# Adversarial: edge cases and error paths
# =========================================================================== #


def test_adv_value_at_max_bound_inclusive_does_not_fire(tmp_path):
    """Adversarial: A volume exactly equal to max_volume_mm3 passes (inclusive bound)."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 10000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=10000.0))
    vol_findings = [
        f for f in _bounds_findings(run_rules(record, cfg))
        if f.labels == frozenset({22})
        and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
    ]
    assert vol_findings == [], "Exact max bound is inclusive — should not fire"


def test_adv_value_at_min_bound_inclusive_does_not_fire(tmp_path):
    """Adversarial: A volume exactly equal to min_volume_mm3 passes (inclusive bound)."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 500.0\n"
        "        max_volume_mm3: 1000000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=500.0))
    vol_findings = [
        f for f in _bounds_findings(run_rules(record, cfg))
        if f.labels == frozenset({3})
        and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
    ]
    assert vol_findings == [], "Exact min bound is inclusive — should not fire"


def test_adv_two_metrics_violated_produces_two_findings(tmp_path):
    """Adversarial: A label violating both volume and extent_x yields at least two findings."""
    content = (
        _bounds_yaml_header()
        + "      thoracic:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(
        _make_label_entry(11, "T5", volume_mm3=9999.0, extent_x_mm=999.0)
    )
    label_findings = [
        f for f in _bounds_findings(run_rules(record, cfg))
        if f.labels == frozenset({11})
    ]
    assert len(label_findings) >= 2, (
        f"Expected at least 2 findings (volume + extent_x) for T5; got {len(label_findings)}"
    )


def test_adv_custom_level_name_skipped_no_crash(tmp_path):
    """Adversarial: A level_name not in any group (e.g. 'Q5') is silently skipped."""
    content = _bounds_yaml_header() + _tight_group_yaml("cervical")
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(99, "Q5", volume_mm3=999999999.0))
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings == [], "Unknown level_name 'Q5' should produce no findings"


def test_adv_geometry_missing_key_no_crash(tmp_path):
    """Adversarial: geometry dict missing one key is handled gracefully; no exception raised."""
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # Geometry missing extent_z_mm
    entry = {
        "label": 22,
        "level_name": "L3",
        "geometry": {
            "physical_volume_mm3": 9999.0,
            "extent_x_mm": 20.0,
            "extent_y_mm": 20.0,
            # extent_z_mm intentionally absent
            "voxel_count": 5000,
        },
    }
    record = {"per_label": {22: entry}, "relationships": {}, "overlaps": {}}
    # Must not raise; may produce findings for metrics that are present
    findings = _bounds_findings(run_rules(record, cfg))
    assert isinstance(findings, list)


def test_adv_unrecognised_severity_string_raises_value_error(tmp_path):
    """Adversarial: An unrecognised severity param string raises ValueError (raises path pinned)."""
    content = (
        _bounds_yaml_header()
        + "      severity: xyz_not_a_severity\n"
        "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=9999.0))
    with pytest.raises(ValueError):
        run_rules(record, cfg)


def test_adv_findings_ordered_ascending_by_label(tmp_path):
    """Adversarial: When two labels both fire, label 3 findings precede label 22 findings."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
        "      lumbar:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(
        _make_label_entry(3, "C3", volume_mm3=9999.0),
        _make_label_entry(22, "L3", volume_mm3=9999.0),
    )
    findings = _bounds_findings(run_rules(record, cfg))
    assert findings, "Expected findings for both labels"
    # All findings for label 3 must come before any finding for label 22
    label_seq = [min(f.labels) for f in findings]
    positions_3 = [i for i, lbl in enumerate(label_seq) if lbl == 3]
    positions_22 = [i for i, lbl in enumerate(label_seq) if lbl == 22]
    if positions_3 and positions_22:
        assert max(positions_3) < min(positions_22), (
            f"Label 3 findings should precede label 22; order: {label_seq}"
        )


def test_adv_evaluate_does_not_mutate_record(tmp_path):
    """Adversarial: run_rules leaves the caller's record mapping unchanged."""
    content = (
        _bounds_yaml_header()
        + "      cervical:\n"
        "        min_volume_mm3: 1.0\n"
        "        max_volume_mm3: 1000.0\n"
        "        min_extent_x_mm: 1.0\n"
        "        max_extent_x_mm: 10000.0\n"
        "        min_extent_y_mm: 1.0\n"
        "        max_extent_y_mm: 10000.0\n"
        "        min_extent_z_mm: 1.0\n"
        "        max_extent_z_mm: 10000.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(_make_label_entry(3, "C3", volume_mm3=9999.0))
    record_before = copy.deepcopy(record)
    run_rules(record, cfg)
    assert record == record_before, "run_rules must not mutate the caller's record"


def test_adv_partial_group_config_override_takes_effect(tmp_path):
    """Adversarial: Partial override of one key (max_volume_mm3 only) takes effect."""
    # Only set max_volume_mm3; other lumbar keys stay at defaults via per-key merge
    content = (
        _bounds_yaml_header()
        + "      lumbar:\n"
        "        max_volume_mm3: 100.0\n"
    )
    cfg = load_config(_write_yaml(tmp_path, content))
    # volume 500 exceeds the partial-config max (100)
    record = _make_record(_make_label_entry(22, "L3", volume_mm3=500.0))
    vol_findings = [
        f for f in _bounds_findings(run_rules(record, cfg))
        if f.labels == frozenset({22})
        and ("volume" in f.reason.lower() or "mm3" in f.reason.lower())
    ]
    assert vol_findings, (
        "Partial config override (max_volume_mm3=100) should fire for volume 500"
    )


def test_adv_all_three_unbounded_groups_in_same_record_no_findings(tmp_path):
    """Adversarial: A record with only S/Cocygis/unknown labels produces no findings."""
    content = _bounds_yaml_header() + _tight_group_yaml("cervical")
    cfg = load_config(_write_yaml(tmp_path, content))
    record = _make_record(
        _make_label_entry(27, "S", volume_mm3=999999999.0),
        _make_label_entry(28, "Cocygis", volume_mm3=999999999.0),
        _make_label_entry(99, "unknown", volume_mm3=999999999.0),
    )
    assert _bounds_findings(run_rules(record, cfg)) == [], (
        "Records with only S/Cocygis/unknown labels should produce no bounds findings"
    )


def test_adv_single_label_single_voxel_volume_no_crash(tmp_path):
    """Adversarial: A single-voxel label (tiny volume) with a default config does not crash."""
    record = _make_record(
        _make_label_entry(3, "C3", volume_mm3=0.001, voxel_count=1)
    )
    findings = _bounds_findings(run_rules(record, default_config()))
    assert isinstance(findings, list)
