"""Tests for the bundled default heuristic-config file (item 035, AC1-AC5).

Covers:
- AC1: the bundled default config file exists and loads via
  ``segqc.config.default_config_path()`` + ``load_config``.
- AC2: the file declares every rule family and the verdict policy.
- AC3: documented thresholds match the shipped code defaults.
- AC4: ``bundled_default_config()`` is a convenience for the file.
- AC5: the bundled config reproduces the built-in defaults' verdict on a
  crafted ground-truth record.

Adversarial / edge-case scenarios included:
- ``default_config_path()`` returns an existing, readable file.
- Every one of the seven rule ids is present and enabled, not just a subset.
- The bounds group threshold is reachable via ``rule_param`` (nested dict).
- ``bundled_default_config()`` equality is checked field-by-field, not just
  by identity.
"""

from __future__ import annotations

import pathlib

import pytest

from segqc.aggregate import build_case_result
from segqc.config import (
    SUPPORTED_SCHEMA_VERSION,
    bundled_default_config,
    default_config,
    default_config_path,
    load_config,
)
from segqc.heuristics import run_rules

# Default label convention (item 004): the labels used throughout this file.
_LABEL_L1 = 20


# =========================================================================== #
# AC1: The bundled default config file exists and loads
# =========================================================================== #


def test_ac1_default_config_path_returns_existing_file():
    """AC1: default_config_path() returns a path to an existing, readable file."""
    path = default_config_path()
    assert isinstance(path, pathlib.Path)
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip()


def test_ac1_default_config_path_named_default_config_yaml():
    """AC1: the bundled file is named default_config.yaml."""
    path = default_config_path()
    assert path.name == "default_config.yaml"


def test_ac1_loading_default_config_path_yields_correct_schema_version():
    """AC1: load_config(default_config_path()) returns schema_version == '0.1'."""
    cfg = load_config(default_config_path())
    assert cfg.schema_version == SUPPORTED_SCHEMA_VERSION
    assert cfg.schema_version == "0.1"


def test_ac1_loading_default_config_path_does_not_raise():
    """AC1: loading the bundled file never raises SegQCConfigError."""
    # Simply not raising is the assertion; load_config already validates the
    # schema_version and YAML syntax internally.
    load_config(default_config_path())


# =========================================================================== #
# AC2: The file declares every rule family and the verdict policy
# =========================================================================== #


def test_ac2_all_seven_rule_families_present_and_enabled():
    """AC2: rules mapping has an entry for each of the seven rule ids, enabled."""
    cfg = load_config(default_config_path())
    for rule_id in (
        "bounds",
        "fragmentation",
        "coverage",
        "sequence",
        "border",
        "overlap",
        "mislabel",
    ):
        assert rule_id in cfg.rules, f"Missing rule section: {rule_id!r}"
        assert cfg.rule_enabled(rule_id) is True, f"{rule_id!r} is not enabled"


def test_ac2_verdict_section_has_flag_escalation_count_key():
    """AC2: the verdict section contains a flag_escalation_count key."""
    cfg = load_config(default_config_path())
    assert "flag_escalation_count" in cfg.verdict


def test_ac2_no_extra_or_missing_rule_ids():
    """AC2: exactly the seven expected rule ids are declared, no more, no fewer."""
    cfg = load_config(default_config_path())
    assert set(cfg.rules.keys()) == {
        "bounds",
        "fragmentation",
        "coverage",
        "sequence",
        "border",
        "overlap",
        "mislabel",
    }


# =========================================================================== #
# AC3: Documented thresholds match the shipped code defaults
# =========================================================================== #


def test_ac3_fragmentation_index_threshold_matches_code_default():
    """AC3: fragmentation.fragmentation_index_threshold == 0.75."""
    cfg = load_config(default_config_path())
    assert cfg.rule_param("fragmentation", "fragmentation_index_threshold", None) == 0.75


def test_ac3_island_min_voxels_matches_code_default():
    """AC3: fragmentation.island_min_voxels == 50."""
    cfg = load_config(default_config_path())
    assert cfg.rule_param("fragmentation", "island_min_voxels", None) == 50


def test_ac3_min_overlap_voxels_matches_code_default():
    """AC3: overlap.min_overlap_voxels == 1."""
    cfg = load_config(default_config_path())
    assert cfg.rule_param("overlap", "min_overlap_voxels", None) == 1


def test_ac3_max_offset_mm_matches_code_default():
    """AC3: mislabel.max_offset_mm == 15.0."""
    cfg = load_config(default_config_path())
    assert cfg.rule_param("mislabel", "max_offset_mm", None) == 15.0


def test_ac3_flag_escalation_count_matches_code_default():
    """AC3: verdict.flag_escalation_count == 0 (disabled, matching the built-in default)."""
    cfg = load_config(default_config_path())
    assert cfg.policy_param("flag_escalation_count", None) == 0


def test_ac3_lumbar_max_volume_mm3_reachable_via_rule_param():
    """AC3: a bounds group value (lumbar.max_volume_mm3 == 120000) is reachable
    via rule_param, matching heuristics.bounds.DEFAULT_BOUNDS."""
    from segqc.heuristics.bounds import DEFAULT_BOUNDS

    cfg = load_config(default_config_path())
    lumbar_params = cfg.rule_params("bounds").get("lumbar", {})
    assert lumbar_params.get("max_volume_mm3") == DEFAULT_BOUNDS["lumbar"]["max_volume_mm3"]
    assert lumbar_params.get("max_volume_mm3") == 120000.0


def test_ac3_all_bounds_groups_present():
    """AC3: cervical, thoracic, and lumbar groups are all present in bounds.params."""
    cfg = load_config(default_config_path())
    bounds_params = cfg.rule_params("bounds")
    for group in ("cervical", "thoracic", "lumbar"):
        assert group in bounds_params


# =========================================================================== #
# AC4: bundled_default_config() is a convenience for the file
# =========================================================================== #


def test_ac4_bundled_default_config_equals_load_config_of_path():
    """AC4: bundled_default_config() == load_config(default_config_path())."""
    bundled = bundled_default_config()
    loaded = load_config(default_config_path())
    assert bundled == loaded


def test_ac4_bundled_default_config_is_heuristic_config_instance():
    """AC4: bundled_default_config() returns a HeuristicConfig."""
    from segqc.config import HeuristicConfig

    assert isinstance(bundled_default_config(), HeuristicConfig)


def test_ac4_bundled_default_config_field_by_field_equality():
    """AC4: field-by-field equality, not merely dataclass equality by chance."""
    bundled = bundled_default_config()
    loaded = load_config(default_config_path())
    assert bundled.schema_version == loaded.schema_version
    assert bundled.rules == loaded.rules
    assert bundled.verdict == loaded.verdict
    assert bundled.min_foreground_voxels == loaded.min_foreground_voxels
    assert bundled.min_label_count == loaded.min_label_count


def test_ac4_bundled_default_config_deterministic_across_calls():
    """AC4: two calls to bundled_default_config() are equal (idempotent, no
    shared mutable state leaking between calls)."""
    assert bundled_default_config() == bundled_default_config()


# =========================================================================== #
# AC5: The bundled config reproduces the built-in defaults' verdict
# =========================================================================== #


def _gt_record() -> dict:
    """A crafted ground-truth-shaped record with no findings under either config."""
    return {
        "per_label": {
            _LABEL_L1: {
                "label": _LABEL_L1,
                "level_name": "L1",
                "geometry": {
                    "physical_volume_mm3": 60000.0,
                    "extent_x_mm": 60.0,
                    "extent_y_mm": 60.0,
                    "extent_z_mm": 60.0,
                    "touches_superior": False,
                    "touches_inferior": False,
                    "touches_left": False,
                    "touches_right": False,
                    "touches_anterior": False,
                    "touches_posterior": False,
                },
                "components": {
                    "component_count": 1,
                    "component_sizes": [1000],
                    "component_volumes_mm3": [1000.0],
                    "largest_component_fraction": 1.0,
                    "fragmentation_index": 1.0,
                    "small_fragments": [],
                },
            },
        },
        "relationships": {
            "present_levels": ["L1"],
            "missing_levels": [],
            "is_continuous": True,
            "out_of_order_labels": [],
        },
        "overlaps": [],
    }


def test_ac5_bundled_and_builtin_default_yield_same_verdict():
    """AC5: run_rules over a crafted GT record under bundled_default_config()
    and under default_config() yields the same overall verdict."""
    record = _gt_record()
    bundled_findings = run_rules(record, bundled_default_config())
    builtin_findings = run_rules(record, default_config())

    bundled_result = build_case_result(bundled_findings, bundled_default_config())
    builtin_result = build_case_result(builtin_findings, default_config())
    assert bundled_result.verdict.overall == builtin_result.verdict.overall


def test_ac5_bundled_and_builtin_default_yield_same_findings():
    """AC5: the findings lists are equal between bundled and built-in defaults."""
    record = _gt_record()
    bundled_findings = run_rules(record, bundled_default_config())
    builtin_findings = run_rules(record, default_config())
    assert bundled_findings == builtin_findings


def test_ac5_bundled_default_yields_pass_on_gt_record():
    """AC5: the shared GT record is unflagged (pass) under the bundled config,
    confirming the file adds no behaviour beyond documenting the defaults."""
    record = _gt_record()
    findings = run_rules(record, bundled_default_config())
    result = build_case_result(findings, bundled_default_config())
    assert findings == []
    from segqc.verdict import Severity

    assert result.verdict.overall == Severity.PASS


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_default_config_path_is_absolute():
    """Adversarial: default_config_path() is an absolute path (works regardless
    of the caller's current working directory)."""
    path = default_config_path()
    assert path.is_absolute()


def test_adv_loading_default_config_twice_yields_equal_configs():
    """Adversarial: loading the file twice yields equal (not just similarly
    shaped) HeuristicConfig objects."""
    cfg1 = load_config(default_config_path())
    cfg2 = load_config(default_config_path())
    assert cfg1 == cfg2


def test_adv_min_foreground_voxels_and_min_label_count_still_zero():
    """Adversarial: the bundled file keeps the Stage 1 empty-check fields at
    their unchanged 0 defaults, so empty-detection behaviour is preserved."""
    cfg = load_config(default_config_path())
    assert cfg.min_foreground_voxels == 0
    assert cfg.min_label_count == 0
