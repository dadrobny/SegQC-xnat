"""Per-failure-mode acceptance tests (item 035, AC19-AC27) plus the no-false-
flags and determinism gate (AC28-AC29) -- the Stage 4 G2 coverage gate.

For each of the eight Sec 6 failure modes a crafted, minimal feature record
(matching build_features_block's shape) is fed straight to run_rules under
bundled_default_config(); the mapped rule_id is asserted to fire with the
expected offending labels / reason content. A ground-truth crafted record is
asserted to pass cleanly (no findings). run_qc determinism is checked at the
pipeline level (CLI-level byte-identical determinism lives in
test_035_cli_e2e.py).

Label convention (item 004): T12 == 19, L1 == 20, L2 == 21.
"""

from __future__ import annotations

import copy

import pytest

from segfacet.aggregate import build_case_result
from segfacet.config import bundled_default_config
from segfacet.heuristics import run_rules
from segfacet.pipeline import run_qc
from segfacet.verdict import Severity

from synthetic import make_labelmap

_T12 = 19
_L1 = 20
_L2 = 21


def _cfg():
    return bundled_default_config()


def _rule_ids(findings):
    return {f.rule_id for f in findings}


# =========================================================================== #
# Mode 1 (mislabel: misalignment / spline-offset)
# =========================================================================== #


def _mode1_record() -> dict:
    return {
        "per_label": {_L1: {"label": _L1, "level_name": "L1"}},
        "relationships": {},
        "overlaps": [],
        "stage3": {
            "per_label_offsets": [
                {"label": _L1, "level_name": "L1", "offset_mm": 15.0}
            ],
            "monotonic_consistency": {"non_monotonic_pairs": []},
        },
    }


def test_ac19_mode1_misalignment_fires_mislabel():
    """AC19: mode 1 (misalignment) fires 'mislabel' with labels == {L1 (20)}."""
    findings = run_rules(_mode1_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "mislabel"]
    assert hits
    assert any(f.labels == frozenset({_L1}) for f in hits)


# =========================================================================== #
# Mode 2 (bounds: over-/under-segmentation)
# =========================================================================== #


def _mode2_record() -> dict:
    return {
        "per_label": {
            _L1: {
                "label": _L1,
                "level_name": "L1",
                "geometry": {
                    "physical_volume_mm3": 500_000.0,  # far above lumbar max
                    "extent_x_mm": 60.0,
                    "extent_y_mm": 60.0,
                    "extent_z_mm": 60.0,
                },
            }
        },
        "relationships": {},
        "overlaps": [],
    }


def test_ac20_mode2_over_segmentation_fires_bounds():
    """AC20: mode 2 (over-/under-segmentation) fires 'bounds' for L1 (20)."""
    findings = run_rules(_mode2_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "bounds"]
    assert hits
    assert any(f.labels == frozenset({_L1}) for f in hits)


# =========================================================================== #
# Mode 3 (fragmentation: rogue island)
# =========================================================================== #


def _mode3_record() -> dict:
    return {
        "per_label": {
            _L1: {
                "label": _L1,
                "level_name": "L1",
                "components": {
                    "component_count": 2,
                    "component_sizes": [1000, 5],
                    "component_volumes_mm3": [1000.0, 5.0],
                    "largest_component_fraction": 1000 / 1005,
                    "fragmentation_index": 1000 / 1005,
                    "small_fragments": [],
                },
            }
        },
        "relationships": {},
        "overlaps": [],
    }


def test_ac21_mode3_rogue_island_fires_fragmentation():
    """AC21: mode 3 (rogue island) fires 'fragmentation' with the island tag."""
    findings = run_rules(_mode3_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "fragmentation"]
    assert hits
    island_hits = [f for f in hits if f.reason.startswith("Rogue island(s):")]
    assert island_hits
    assert any(f.labels == frozenset({_L1}) for f in island_hits)


# =========================================================================== #
# Mode 4 (mislabel: semantic ordering)
# =========================================================================== #


def _mode4_record() -> dict:
    return {
        "per_label": {
            _L1: {"label": _L1, "level_name": "L1"},
            _L2: {"label": _L2, "level_name": "L2"},
        },
        "relationships": {},
        "overlaps": [],
        "stage3": {
            "per_label_offsets": [],
            "monotonic_consistency": {"non_monotonic_pairs": [["L2", "L1"]]},
        },
    }


def test_ac22_mode4_semantic_mislabelling_fires_mislabel():
    """AC22: mode 4 (semantic mislabelling) fires 'mislabel' naming both
    L1 (20) and L2 (21)."""
    findings = run_rules(_mode4_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "mislabel"]
    assert hits
    order_hits = [f for f in hits if f.reason.startswith("Vertebra ordering inconsistent with label:")]
    assert order_hits
    assert any({_L1, _L2} <= f.labels for f in order_hits)


# =========================================================================== #
# Mode 5 (coverage: missing levels)
# =========================================================================== #


def _mode5_record() -> dict:
    return {
        "per_label": {
            _L1: {"label": _L1, "level_name": "L1", "geometry": {}},
            _L2: {"label": _L2, "level_name": "L2", "geometry": {}},
        },
        "relationships": {
            "present_levels": ["L1", "L2"],
            "missing_levels": ["T12"],
            "is_continuous": True,
            "out_of_order_labels": [],
        },
        "overlaps": [],
    }


def test_ac23_mode5_missing_levels_fires_coverage():
    """AC23: mode 5 (missing levels) fires a case-level 'coverage' finding
    naming T12."""
    findings = run_rules(_mode5_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "coverage"]
    assert hits
    assert any(f.labels == frozenset() and "T12" in f.reason for f in hits)


# =========================================================================== #
# Mode 6 (border: partial vertebra at image border)
# =========================================================================== #


def _mode6_record() -> dict:
    return {
        "per_label": {
            _L1: {
                "label": _L1,
                "level_name": "L1",
                "geometry": {
                    "touches_left": True,
                    "touches_right": False,
                    "touches_anterior": False,
                    "touches_posterior": False,
                    "touches_superior": False,
                    "touches_inferior": False,
                },
            }
        },
        "relationships": {"present_levels": ["L1"]},
        "overlaps": [],
    }


def test_ac24_mode6_border_partial_fires_border():
    """AC24: mode 6 (border-partial) fires 'border' for L1 (20) via an
    in-plane face touch."""
    findings = run_rules(_mode6_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "border"]
    assert hits
    assert any(f.labels == frozenset({_L1}) for f in hits)


# =========================================================================== #
# Mode 7 (sequence: non-continuous label sequence)
# =========================================================================== #


def _mode7_record() -> dict:
    return {
        "per_label": {
            _L1: {"label": _L1, "level_name": "L1"},
            _T12: {"label": _T12, "level_name": "T12"},
        },
        "relationships": {
            "present_levels": ["T12", "L1"],
            "missing_levels": [],
            "is_continuous": False,
            "out_of_order_labels": ["L1", "T12"],
        },
        "overlaps": [],
    }


def test_ac25_mode7_non_continuous_sequence_fires_sequence():
    """AC25: mode 7 (non-continuous sequence) fires 'sequence' attributing
    both L1 (20) and T12 (19)."""
    findings = run_rules(_mode7_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "sequence"]
    assert hits
    assert any({_L1, _T12} <= f.labels for f in hits)


# =========================================================================== #
# Mode 8 (overlap: overlapping segments)
# =========================================================================== #


def _mode8_record() -> dict:
    return {
        "per_label": {},
        "relationships": {},
        "overlaps": [
            {
                "label_a": _L1,
                "label_b": _L2,
                "name_a": "L1",
                "name_b": "L2",
                "overlap_voxels": 40,
            }
        ],
    }


def test_ac26_mode8_overlapping_segments_fires_overlap():
    """AC26: mode 8 (overlapping segments) fires 'overlap' for {L1, L2}."""
    findings = run_rules(_mode8_record(), _cfg())
    hits = [f for f in findings if f.rule_id == "overlap"]
    assert hits
    assert any(f.labels == frozenset({_L1, _L2}) for f in hits)


# =========================================================================== #
# AC27: All eight modes are covered by the run engine together
# =========================================================================== #


_MODE_RECORDS_AND_RULE_IDS = [
    (1, _mode1_record, "mislabel"),
    (2, _mode2_record, "bounds"),
    (3, _mode3_record, "fragmentation"),
    (4, _mode4_record, "mislabel"),
    (5, _mode5_record, "coverage"),
    (6, _mode6_record, "border"),
    (7, _mode7_record, "sequence"),
    (8, _mode8_record, "overlap"),
]


def test_ac27_each_of_eight_modes_fires_its_mapped_rule():
    """AC27: every one of the eight crafted mode records fires >=1 finding of
    its mapped rule_id under bundled_default_config() -- the single
    assertion that the Stage 4 G2 gate is met."""
    for mode_number, build_record, expected_rule_id in _MODE_RECORDS_AND_RULE_IDS:
        findings = run_rules(build_record(), _cfg())
        fired_rule_ids = _rule_ids(findings)
        assert expected_rule_id in fired_rule_ids, (
            f"Mode {mode_number} did not fire rule_id {expected_rule_id!r}; "
            f"fired: {fired_rule_ids}"
        )


def test_ac27_union_of_all_modes_covers_every_mapped_rule_id():
    """AC27: the union of rule_ids fired across all eight records covers every
    mapped rule_id at least once."""
    union: set = set()
    for _mode_number, build_record, _expected_rule_id in _MODE_RECORDS_AND_RULE_IDS:
        union |= _rule_ids(run_rules(build_record(), _cfg()))
    expected = {
        "mislabel",
        "bounds",
        "fragmentation",
        "coverage",
        "border",
        "sequence",
        "overlap",
    }
    assert expected <= union


# =========================================================================== #
# AC28: A ground-truth crafted example passes with no findings
# =========================================================================== #


def _gt_pass_record() -> dict:
    """A crafted in-range GT record: every metric inside default bounds,
    single component per label, continuous relationships, no overlaps, no
    stage3 outliers -- must yield zero findings and an overall PASS verdict.
    """
    per_label = {}
    for label, level_name, volume, extents in (
        (_T12, "T12", 40_000.0, (50.0, 50.0, 40.0)),  # thoracic
        (_L1, "L1", 60_000.0, (60.0, 60.0, 60.0)),  # lumbar
        (_L2, "L2", 60_000.0, (60.0, 60.0, 60.0)),  # lumbar
    ):
        ex, ey, ez = extents
        per_label[label] = {
            "label": label,
            "level_name": level_name,
            "geometry": {
                "physical_volume_mm3": volume,
                "extent_x_mm": ex,
                "extent_y_mm": ey,
                "extent_z_mm": ez,
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
        }
    return {
        "per_label": per_label,
        "relationships": {
            "present_levels": ["T12", "L1", "L2"],
            "missing_levels": [],
            "is_continuous": True,
            "out_of_order_labels": [],
        },
        "overlaps": [],
        "stage3": {
            "per_label_offsets": [
                {"label": _T12, "level_name": "T12", "offset_mm": 5.0},
                {"label": _L1, "level_name": "L1", "offset_mm": 5.0},
                {"label": _L2, "level_name": "L2", "offset_mm": 5.0},
            ],
            "monotonic_consistency": {"non_monotonic_pairs": []},
        },
    }


def test_ac28_gt_record_yields_no_findings():
    """AC28: run_rules over the crafted GT record yields []."""
    findings = run_rules(_gt_pass_record(), _cfg())
    assert findings == []


def test_ac28_gt_record_yields_pass_verdict():
    """AC28: build_case_result(...).verdict has overall == Severity.PASS."""
    findings = run_rules(_gt_pass_record(), _cfg())
    result = build_case_result(findings, _cfg())
    assert result.verdict.overall == Severity.PASS


# =========================================================================== #
# AC29: The wired pipeline is deterministic (run_qc half)
# =========================================================================== #


def test_ac29_run_qc_deterministic_findings_and_verdict():
    """AC29: two run_qc calls on the same seg_img/config return equal findings
    tuples and equal verdicts."""
    seg = make_labelmap(blocks={20: ((2, 6), (2, 6), (2, 6)), 21: ((9, 13), (9, 13), (9, 13))})
    cfg = _cfg()
    result1, block1 = run_qc(seg, cfg)
    result2, block2 = run_qc(seg, cfg)
    assert result1.findings == result2.findings
    assert result1.verdict == result2.verdict
    assert block1 == block2


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_mode_records_do_not_mutate_between_repeated_run_rules_calls():
    """Adversarial: calling run_rules twice on the same crafted mode record
    does not mutate it and yields equal findings."""
    record = _mode3_record()
    before = copy.deepcopy(record)
    findings1 = run_rules(record, _cfg())
    findings2 = run_rules(record, _cfg())
    assert record == before
    assert findings1 == findings2


def test_adv_gt_record_is_not_accidentally_flagged_by_any_single_rule():
    """Adversarial: no individual rule_id appears anywhere in the GT record's
    (empty) finding set -- guards against a silently-added rule regressing
    the no-false-flag guarantee."""
    findings = run_rules(_gt_pass_record(), _cfg())
    assert _rule_ids(findings) == set()


def test_adv_each_mode_record_is_isolated_from_the_others():
    """Adversarial: running rules on one mode's record does not leak findings
    belonging to another mode's mapped rule (each record is minimal and only
    fires its own mapped rule, modulo bounds' universal per-label check)."""
    # Mode 8 (overlap-only record, empty per_label) must not fire sequence,
    # coverage, border, bounds, fragmentation, or mislabel -- only overlap.
    findings = run_rules(_mode8_record(), _cfg())
    assert _rule_ids(findings) == {"overlap"}


def test_adv_mode5_record_does_not_also_fire_sequence():
    """Adversarial: the mode 5 (missing-levels) record, which has
    is_continuous=True and no out_of_order_labels, does not spuriously fire
    'sequence'."""
    findings = run_rules(_mode5_record(), _cfg())
    assert "sequence" not in _rule_ids(findings)
