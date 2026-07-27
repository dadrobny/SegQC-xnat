"""Tests for item 099 -- per-mode metric API: one named magnitude metric per
§6 failure mode (``segfacet.eval.per_mode``).

Covers Acceptance Criteria AC1-AC25:

- AC1:  the module's public surface (``MetricSpec``, ``PerModeMetric``,
        ``PerModeMetrics``, ``PER_MODE_METRIC_SPECS``,
        ``compute_per_mode_metrics``) exists, is exported via ``__all__``,
        and is re-exported from ``segfacet.eval``; the two result dataclasses
        are frozen.
- AC2:  ``PER_MODE_METRIC_SPECS`` covers exactly modes 1-8 (not 0), each
        entry's ``failure_mode``/``failure_mode_name`` self-consistent with
        ``synth.perturbation.FAILURE_MODE_NAMES``.
- AC3:  metric names are unique, unit-suffixed, and ``direction``/``source``
        are drawn from their fixed vocabularies.
- AC4:  the result always carries all eight entries, in mode order, for any
        input.
- AC5:  ``value`` is uniformly ``float`` or ``None`` -- never ``int``,
        ``numpy.float64``, or ``bool``.
- AC6-AC14: the eight metrics, one focused test per mode, hand-computed
  against the committed corpus (values verified independently against the
  existing, already-shipped primitives each metric is built from --
  ``extract_feature_record``, ``compute_overlap``, ``BorderRule`` --
  before this test file was written, per the item's Testing Strategy).
- AC15: the isolation matrix -- every metric peaks on its own designated
        corpus case -- asserted against a frozen literal 8x9 table, plus a
        negative control proving the dominance check can fail.
- AC16: the clean control sits at baseline for all eight metrics.
- AC17: the aggregate overlap context (``mean_dice``, ``volume_weighted_dice``,
        ``n_matched``, ``n_unmatched``) is taken verbatim from ``compute_overlap``.
- AC18: no new Dice/Jaccard arithmetic; the module's only overlap route is
        ``compute_overlap``.
- AC19: ``to_dict()`` is plain-JSON-shaped and round-trips through
        ``json.dumps``/``json.loads``.
- AC20: the API never mutates ``record``, ``candidate``, or ``gt``.
- AC21: the API is idempotent.
- AC22: a record missing an optional block (empty ``{}``, or a genuine
        0-label record) degrades to ``None`` with a detail, never raising.
- AC23: a missing ``candidate``/``gt`` degrades to ``None`` with a detail for
        the three paired metrics; the five record-sourced metrics still
        resolve.
- AC24: a candidate/GT shape mismatch propagates ``FacetInputError``.
- AC25: the scope fence holds -- ``eval/metrics.py``, ``report_schema_v0.json``,
        ``cli.py``, ``heuristics/**`` and the committed goldens are untouched;
        ``per_mode.py`` never imports ``segfacet.eval.metrics``.

Adversarial / edge-case scenarios included:
- Empty record ``{}`` (AC22) and a genuine 0-/1-label ``extract_feature_record``
  record (no ``stage3`` key, ``relationships is None`` for the 0-label case).
- Missing candidate only / GT only / both (AC23).
- Candidate/GT shape mismatch (AC24).
- ``candidate``/``gt`` both all-zero -- mode 1 is ``None`` (empty GT
  denominator), not ``nan``/``ZeroDivisionError``; modes 4/5 are ``0.0``.
- ``candidate is gt`` (same object) -- every paired metric at baseline,
  ``mean_dice == 1.0``.
- ``island_size_ratio`` boundary: a stray component exactly at
  ``ratio * dominant`` does not count (strictly below); ``ratio=0.0`` never
  counts; ``ratio`` above ``1.0`` counts every stray component;
  ``island_size_ratio`` is keyword-only (a positional call raises ``TypeError``).
- A malformed record (``per_label`` a list, ``components`` a string) degrades
  to ``None`` with a detail rather than raising ``TypeError``.
- Non-isotropic spacing: the seven voxel-ratio metrics and mode 5's count are
  spacing-invariant; the aggregate fields match ``compute_overlap`` called
  with that same spacing.
- Mode 6's suppression of an *expected* FOV-end touch (a hand-built record
  the synthetic corpus never exercises, since its clean spine touches no
  face).
- Mode 4's "present in GT" restriction and mode 5's "majority background"
  restriction are each shown to matter by an unrestricted hand-computation
  that would give a different (wrong, mode-7-colliding) answer.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from synthetic import make_labelmap

from segfacet.config import bundled_default_config
from segfacet.eval.overlap import compute_overlap
from segfacet.feature_report import overlap_to_dict
from segfacet.features.overlap import detect_overlaps
from segfacet.heuristics.border import BorderRule
from segfacet.heuristics.fov import derive_fov_coverage
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.perturbation import FAILURE_MODE_NAMES
from segfacet.synth.regression import loaded_seg_image


def _per_mode():
    """Local import of ``segfacet.eval.per_mode`` -- kept out of the
    module-level import block (mirrors ``tests/test_054_metrics.py``'s
    convention for a module that does not exist yet at the time this file is
    written) so this file still collects before item 099's builder step
    lands the module."""
    import segfacet.eval.per_mode as per_mode

    return per_mode


# =========================================================================== #
# Corpus fixtures -- loaded/built once at module scope (Testing Strategy)
# =========================================================================== #

_MANIFEST = load_manifest()
_CASES = {c["case_id"]: c for c in _MANIFEST["cases"]}
_CASE_IDS = sorted(_CASES)
_CONFIG = bundled_default_config()

_ARRAYS = {
    cid: np.asanyarray(loaded_seg_image(case).dataobj) for cid, case in _CASES.items()
}
_RECORDS = {
    cid: extract_feature_record(loaded_seg_image(case), _CONFIG)
    for cid, case in _CASES.items()
}
_GT_ARRAY = _ARRAYS["clean_control"]


def _mode8_record_with_overlaps() -> dict:
    """``mode8_force_overlap``'s record with its ``overlaps`` block replaced
    by the committed ``overlap_mask_stack`` reconstruction technique
    (mirrors ``synth.regression._recon_overlap_mask_stack``) -- a plain
    single-integer label map cannot encode a genuine overlap (item 040), so
    mode 8's signal must come from this reconstructed block."""
    case = _CASES["mode8_force_overlap"]
    target = case["perturbation_params"]["target_label"]
    neighbour = case["perturbation_params"]["neighbour_label"]

    clean = build_clean_spine(**case["base"])
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    data = _ARRAYS["mode8_force_overlap"]

    stack = np.stack([data == target, clean_data == neighbour])
    pairs = detect_overlaps(stack, np.array([target, neighbour]))

    record = dict(_RECORDS["mode8_force_overlap"])
    record["overlaps"] = [overlap_to_dict(p) for p in pairs]
    return record


_MODE8_RECORD = _mode8_record_with_overlaps()


def _value(result, failure_mode: int):
    """Fetch a result's entry for *failure_mode* by AC4's guaranteed
    ascending-mode-order tuple layout (``per_mode[failure_mode - 1]``)."""
    entry = result.per_mode[failure_mode - 1]
    assert entry.failure_mode == failure_mode
    return entry.value


def _record_for(cid: str) -> dict:
    """The record to feed for the record-sourced metrics of case *cid* --
    the mode-8 reconstructed record for ``mode8_force_overlap``, the plain
    corpus record otherwise."""
    if cid == "mode8_force_overlap":
        return _MODE8_RECORD
    return _RECORDS[cid]


# --------------------------------------------------------------------------- #
# Hand-built record helpers (mirrors tests/test_089_fov_aware_coverage_border.py
# and tests/test_098_stray_components.py's local conventions)
# --------------------------------------------------------------------------- #

_ALL_FACES = (
    "touches_superior",
    "touches_inferior",
    "touches_left",
    "touches_right",
    "touches_anterior",
    "touches_posterior",
)


def _geometry(touched_faces=()) -> dict:
    return {face: (face in touched_faces) for face in _ALL_FACES}


def _components(component_sizes, stray_component_sizes=None) -> dict:
    total = sum(component_sizes) if component_sizes else 1
    lcf = (component_sizes[0] / total) if component_sizes else 1.0
    stray = (
        list(stray_component_sizes)
        if stray_component_sizes is not None
        else list(component_sizes[1:])
    )
    return {
        "component_count": len(component_sizes),
        "component_sizes": list(component_sizes),
        "component_volumes_mm3": [float(s) for s in component_sizes],
        "largest_component_fraction": lcf,
        "small_fragments": [],
        "fragmentation_index": lcf,
        "stray_component_count": len(stray),
        "stray_component_sizes": stray,
        "stray_volume_mm3": float(sum(stray)),
        "stray_volume_fraction": 1.0 - lcf,
    }


def _entry(label: int, level_name: str, touched_faces=(), components=None) -> dict:
    return {
        "label": label,
        "level_name": level_name,
        "geometry": _geometry(touched_faces),
        "components": components or _components([1]),
    }


def _hand_record(entries, present_levels=None, missing_levels=(), overlaps=None) -> dict:
    """A minimal ``build_features_block``-shaped record: ``per_label`` keyed
    by each entry's integer label, ``relationships`` carrying
    ``present_levels``/``out_of_order_labels`` (item 014 shape)."""
    if present_levels is None:
        present_levels = [e["level_name"] for e in entries]
    return {
        "per_label": {e["label"]: e for e in entries},
        "relationships": {
            "present_levels": list(present_levels),
            "missing_levels": list(missing_levels),
            "neighbour_spacings_mm": [],
            "is_continuous": len(missing_levels) == 0,
            "out_of_order_labels": [],
        },
        "overlaps": overlaps if overlaps is not None else [],
    }


# =========================================================================== #
# AC1: public surface, re-export, frozen dataclasses
# =========================================================================== #

_PUBLIC_NAMES = (
    "MetricSpec",
    "PerModeMetric",
    "PerModeMetrics",
    "PER_MODE_METRIC_SPECS",
    "compute_per_mode_metrics",
)


def test_ac1_all_five_names_exported_from_per_mode_module():
    pm = _per_mode()
    assert set(_PUBLIC_NAMES) <= set(pm.__all__)
    for name in _PUBLIC_NAMES:
        assert hasattr(pm, name), f"segfacet.eval.per_mode is missing {name!r}"


def test_ac1_all_five_names_reexported_from_eval_package():
    import segfacet.eval as eval_pkg

    for name in _PUBLIC_NAMES:
        assert name in eval_pkg.__all__, f"{name!r} missing from segfacet.eval.__all__"
        assert hasattr(eval_pkg, name), f"{name!r} not importable from segfacet.eval"


def test_ac1_permodemetric_is_frozen_dataclass():
    pm = _per_mode()
    assert dataclasses.is_dataclass(pm.PerModeMetric)
    record = _hand_record([_entry(1, "L1")])
    result = pm.compute_per_mode_metrics(record)
    entry = result.per_mode[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.value = 999.0  # type: ignore[misc]


def test_ac1_permodemetrics_is_frozen_dataclass():
    pm = _per_mode()
    assert dataclasses.is_dataclass(pm.PerModeMetrics)
    record = _hand_record([_entry(1, "L1")])
    result = pm.compute_per_mode_metrics(record)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.n_matched = 999  # type: ignore[misc]


def test_ac1_metricspec_is_frozen_dataclass():
    pm = _per_mode()
    assert dataclasses.is_dataclass(pm.MetricSpec)
    spec = pm.PER_MODE_METRIC_SPECS[1]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.baseline = 999.0  # type: ignore[misc]


# =========================================================================== #
# AC2: the spec registry covers exactly modes 1-8
# =========================================================================== #


def test_ac2_key_set_is_exactly_one_through_eight():
    pm = _per_mode()
    assert set(pm.PER_MODE_METRIC_SPECS.keys()) == {1, 2, 3, 4, 5, 6, 7, 8}


def test_ac2_clean_control_mode_zero_is_not_a_key():
    pm = _per_mode()
    assert 0 not in pm.PER_MODE_METRIC_SPECS


@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 6, 7, 8])
def test_ac2_spec_failure_mode_field_matches_its_key(mode):
    pm = _per_mode()
    assert pm.PER_MODE_METRIC_SPECS[mode].failure_mode == mode


@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 6, 7, 8])
def test_ac2_spec_failure_mode_name_matches_failure_mode_names(mode):
    pm = _per_mode()
    spec = pm.PER_MODE_METRIC_SPECS[mode]
    assert spec.failure_mode_name == FAILURE_MODE_NAMES[mode]


# =========================================================================== #
# AC3: metric names unique, unit-suffixed; direction/source vocabularies
# =========================================================================== #

_EXPECTED_METRIC_NAMES = {
    1: "unanchored_foreground_fraction",
    2: "min_dominant_component_fraction",
    3: "rogue_island_count",
    4: "mislabelled_volume_fraction",
    5: "missing_level_count",
    6: "fov_clipped_label_count",
    7: "out_of_order_label_count",
    8: "overlapping_voxel_count",
}
_EXPECTED_DIRECTIONS = {
    1: "increases",
    2: "decreases",
    3: "increases",
    4: "increases",
    5: "increases",
    6: "increases",
    7: "increases",
    8: "increases",
}
_EXPECTED_SOURCES = {
    1: "candidate_vs_gt",
    2: "record",
    3: "record",
    4: "candidate_vs_gt",
    5: "candidate_vs_gt",
    6: "record",
    7: "record",
    8: "record",
}
_EXPECTED_BASELINES = {m: (1.0 if m == 2 else 0.0) for m in range(1, 9)}


def test_ac3_metric_names_match_the_spec_table():
    pm = _per_mode()
    for mode, name in _EXPECTED_METRIC_NAMES.items():
        assert pm.PER_MODE_METRIC_SPECS[mode].metric_name == name


def test_ac3_metric_names_are_pairwise_distinct():
    pm = _per_mode()
    names = [spec.metric_name for spec in pm.PER_MODE_METRIC_SPECS.values()]
    assert len(names) == len(set(names))


def test_ac3_every_metric_name_ends_in_fraction_or_count():
    pm = _per_mode()
    pattern = re.compile(r"_(fraction|count)$")
    for spec in pm.PER_MODE_METRIC_SPECS.values():
        assert pattern.search(spec.metric_name), spec.metric_name


def test_ac3_direction_values_match_the_spec_table():
    pm = _per_mode()
    for mode, direction in _EXPECTED_DIRECTIONS.items():
        assert pm.PER_MODE_METRIC_SPECS[mode].direction == direction


def test_ac3_source_values_match_the_spec_table():
    pm = _per_mode()
    for mode, source in _EXPECTED_SOURCES.items():
        assert pm.PER_MODE_METRIC_SPECS[mode].source == source


def test_ac3_every_direction_is_one_of_the_two_valid_values():
    pm = _per_mode()
    for spec in pm.PER_MODE_METRIC_SPECS.values():
        assert spec.direction in ("increases", "decreases")


def test_ac3_every_source_is_one_of_the_two_valid_values():
    pm = _per_mode()
    for spec in pm.PER_MODE_METRIC_SPECS.values():
        assert spec.source in ("record", "candidate_vs_gt")


# =========================================================================== #
# AC4: the result always carries all eight entries, in mode order
# =========================================================================== #


def test_ac4_empty_record_no_candidate_gt_yields_eight_entries_in_order():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics({})
    assert len(result.per_mode) == 8
    assert tuple(e.failure_mode for e in result.per_mode) == (1, 2, 3, 4, 5, 6, 7, 8)


def test_ac4_real_record_with_candidate_and_gt_yields_eight_entries_in_order():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    assert len(result.per_mode) == 8
    assert tuple(e.failure_mode for e in result.per_mode) == (1, 2, 3, 4, 5, 6, 7, 8)
    assert result.per_mode is not None
    # never dropped, reordered, or replaced by None
    assert all(e is not None for e in result.per_mode)


# =========================================================================== #
# AC5: value is uniformly float or None
# =========================================================================== #


def test_ac5_values_are_float_or_none_never_int_numpy_or_bool():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"],
        candidate=_ARRAYS["mode1_displace"],
        gt=_GT_ARRAY,
    )
    for entry in result.per_mode:
        assert entry.value is None or type(entry.value) is float
        assert type(entry.value) is not bool
        assert type(entry.value) is not int


def test_ac5_all_eight_are_non_none_floats_on_a_fully_populated_case():
    """On mode1_displace vs clean_control every one of the eight modes
    resolves (the seven record-sourced modes read a real corpus record, the
    paired routes get real arrays) -- a positive sweep proving AC5 isn't
    vacuously true only for None entries."""
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"],
        candidate=_ARRAYS["mode1_displace"],
        gt=_GT_ARRAY,
    )
    for entry in result.per_mode:
        assert type(entry.value) is float


# =========================================================================== #
# AC6: mode 1 -- unanchored_foreground_fraction
# =========================================================================== #


def test_ac6_mode1_matches_hand_formula_on_mode1_displace():
    pm = _per_mode()
    cand = _ARRAYS["mode1_displace"]
    expected = float(np.count_nonzero((cand != 0) & (_GT_ARRAY == 0))) / float(
        np.count_nonzero(_GT_ARRAY != 0)
    )
    result = pm.compute_per_mode_metrics(_RECORDS["mode1_displace"], candidate=cand, gt=_GT_ARRAY)
    assert _value(result, 1) == pytest.approx(expected, abs=1e-9)


def test_ac6_mode1_own_case_exceeds_014():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    assert _value(result, 1) > 0.14


def test_ac6_mode1_clean_control_vs_itself_is_zero():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    assert _value(result, 1) == 0.0


def test_ac6_mode1_is_none_when_gt_has_no_foreground():
    pm = _per_mode()
    zero_cand = np.zeros_like(_GT_ARRAY)
    zero_gt = np.zeros_like(_GT_ARRAY)
    result = pm.compute_per_mode_metrics({}, candidate=zero_cand, gt=zero_gt)
    assert _value(result, 1) is None


# =========================================================================== #
# AC7: mode 2 -- min_dominant_component_fraction
# =========================================================================== #


def test_ac7_mode2_matches_min_fragmentation_index_over_per_label():
    pm = _per_mode()
    record = _RECORDS["mode3_inject_islands"]
    expected = min(
        entry["components"].get(
            "fragmentation_index", entry["components"]["largest_component_fraction"]
        )
        for entry in record["per_label"].values()
    )
    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 2) == pytest.approx(expected, abs=1e-9)


def test_ac7_mode2_mode2_fragment_is_half():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["mode2_fragment"])
    assert _value(result, 2) == pytest.approx(0.5, abs=1e-9)


def test_ac7_mode2_clean_control_is_one():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["clean_control"])
    assert _value(result, 2) == pytest.approx(1.0, abs=1e-9)


def test_ac7_mode2_falls_back_to_largest_component_fraction_when_alias_absent():
    pm = _per_mode()
    comp = _components([100, 40])
    del comp["fragmentation_index"]
    record = _hand_record([_entry(1, "L1", components=comp)])
    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 2) == pytest.approx(100 / 140, abs=1e-9)


# =========================================================================== #
# AC8: mode 3 -- rogue_island_count and its ratio parameter
# =========================================================================== #


def test_ac8_mode3_default_ratio_separates_mode3_from_mode2():
    pm = _per_mode()
    r2 = pm.compute_per_mode_metrics(_RECORDS["mode2_fragment"])
    r3 = pm.compute_per_mode_metrics(_RECORDS["mode3_inject_islands"])
    assert _value(r3, 3) == pytest.approx(1.0, abs=1e-9)
    assert _value(r2, 3) == pytest.approx(0.0, abs=1e-9)


def test_ac8_mode3_stray_component_count_is_one_for_both_but_ratio_separates():
    """Both mode2_fragment ([9000, 9000]) and mode3_inject_islands
    ([18750, 27]) have stray_component_count == 1 -- the size-ratio test,
    not the count, is what separates them (item 098's own limitation)."""
    r2 = _RECORDS["mode2_fragment"]["per_label"]["22"]["components"]
    r3 = _RECORDS["mode3_inject_islands"]["per_label"]["22"]["components"]
    assert r2["stray_component_count"] == 1
    assert r3["stray_component_count"] == 1


def test_ac8_mode3_raising_ratio_to_one_makes_mode2_fragment_flag_too():
    """A stand-in for ``mode2_fragment``'s shape ([9000, 9000], where stray
    equals -- not strictly less than -- dominant, so it can never flip at
    ratio 1.0; see the exact-equality boundary test below) with the stray
    component strictly below the dominant one at ratio 1.0 ([100, 99]):
    raising the ratio from the default (0.10, which does not count a stray
    of 99 against a threshold of 10) to 1.0 (threshold 100) flips the count
    from 0 to 1."""
    pm = _per_mode()
    comp = _components([100, 99])
    record = _hand_record([_entry(1, "L1", components=comp)])
    baseline = pm.compute_per_mode_metrics(record)
    assert _value(baseline, 3) == pytest.approx(0.0, abs=1e-9)
    result = pm.compute_per_mode_metrics(record, island_size_ratio=1.0)
    assert _value(result, 3) == pytest.approx(1.0, abs=1e-9)


def test_ac8_island_size_ratio_is_keyword_only():
    pm = _per_mode()
    with pytest.raises(TypeError):
        pm.compute_per_mode_metrics(_RECORDS["clean_control"], 0.5)  # type: ignore[misc]


def test_ac8_boundary_stray_exactly_at_ratio_times_dominant_does_not_count():
    pm = _per_mode()
    comp = _components([100, 50])  # stray == [50], threshold == 0.5*100 == 50
    record = _hand_record([_entry(1, "L1", components=comp)])
    result = pm.compute_per_mode_metrics(record, island_size_ratio=0.5)
    assert _value(result, 3) == 0.0


def test_ac8_boundary_stray_strictly_below_ratio_times_dominant_does_count():
    pm = _per_mode()
    comp = _components([100, 49])  # stray == [49] < threshold 50
    record = _hand_record([_entry(1, "L1", components=comp)])
    result = pm.compute_per_mode_metrics(record, island_size_ratio=0.5)
    assert _value(result, 3) == 1.0


def test_ac8_ratio_zero_never_counts_any_corpus_case():
    pm = _per_mode()
    for cid in _CASE_IDS:
        result = pm.compute_per_mode_metrics(_record_for(cid), island_size_ratio=0.0)
        assert _value(result, 3) == 0.0, cid


def test_ac8_ratio_above_one_counts_every_stray_component():
    pm = _per_mode()
    comp = _components([1000, 999, 998])
    record = _hand_record([_entry(1, "L1", components=comp)])
    result = pm.compute_per_mode_metrics(record, island_size_ratio=1.5)
    assert _value(result, 3) == 2.0


# =========================================================================== #
# AC9: mode 4 -- mislabelled_volume_fraction
# =========================================================================== #


def test_ac9_mode4_relabel_swap_is_04():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode4_relabel_swap"],
        candidate=_ARRAYS["mode4_relabel_swap"],
        gt=_GT_ARRAY,
    )
    assert _value(result, 4) == pytest.approx(0.4, abs=1e-9)


def test_ac9_mode4_sequence_break_is_zero_relabel_target_absent_from_gt():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode7_sequence_break"],
        candidate=_ARRAYS["mode7_sequence_break"],
        gt=_GT_ARRAY,
    )
    assert _value(result, 4) == 0.0


def test_ac9_mode4_unrestricted_variant_would_give_02_on_sequence_break():
    """Adversarial (the mode4/mode7 separator, spelled out): dropping the
    "candidate label present in GT" clause on mode7_sequence_break's GT-vs-
    candidate pair gives 0.2 (a direct collision with mode4_relabel_swap's
    0.4) -- proving the restriction is load-bearing, not cosmetic."""
    cand = _ARRAYS["mode7_sequence_break"]
    gt_fg = _GT_ARRAY != 0
    denom = np.count_nonzero(gt_fg)
    unrestricted_mask = gt_fg & (cand != 0) & (cand != _GT_ARRAY)
    unrestricted = np.count_nonzero(unrestricted_mask) / denom
    assert unrestricted == pytest.approx(0.2, abs=1e-9)


def test_ac9_mode4_clean_control_is_zero():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    assert _value(result, 4) == 0.0


# =========================================================================== #
# AC10: mode 5 -- missing_level_count, computed through compute_overlap
# =========================================================================== #


def test_ac10_mode5_remove_level_is_one():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode5_remove_level"],
        candidate=_ARRAYS["mode5_remove_level"],
        gt=_GT_ARRAY,
    )
    assert _value(result, 5) == 1.0


def test_ac10_mode5_sequence_break_is_zero_label_fully_covered():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode7_sequence_break"],
        candidate=_ARRAYS["mode7_sequence_break"],
        gt=_GT_ARRAY,
    )
    assert _value(result, 5) == 0.0


def test_ac10_mode5_sequence_break_naive_unmatched_count_would_have_fired():
    """Adversarial (the mode5/mode7 separator): a bare
    OverlapResult.n_unmatched count reads 2 on mode7_sequence_break -- a
    renamed level is n_unmatched too -- so the "majority background" clause
    is what drives mode 5 to 0 there while n_unmatched alone would not."""
    result = compute_overlap(_ARRAYS["mode7_sequence_break"], _GT_ARRAY, (1.0, 1.0, 1.0))
    assert result.n_unmatched == 2


def test_ac10_mode5_clean_control_is_zero():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    assert _value(result, 5) == 0.0


# =========================================================================== #
# AC11: mode 6 -- fov_clipped_label_count
# =========================================================================== #


def test_ac11_mode6_crop_at_border_is_one():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["mode6_crop_at_border"])
    assert _value(result, 6) == 1.0


@pytest.mark.parametrize(
    "cid", [c for c in _CASE_IDS if c != "mode6_crop_at_border"]
)
def test_ac11_mode6_every_other_corpus_case_is_zero(cid):
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_record_for(cid))
    assert _value(result, 6) == 0.0, cid


# =========================================================================== #
# AC12: mode 6 agrees with the border rule
# =========================================================================== #

_UNEXPECTED_CLIP_TAG = "Partial vertebra clipped by FOV:"


@pytest.mark.parametrize("cid", _CASE_IDS)
def test_ac12_mode6_agrees_with_border_rule_distinct_label_count(cid):
    pm = _per_mode()
    record = _record_for(cid)
    result = pm.compute_per_mode_metrics(record)

    findings = BorderRule().evaluate(record, _CONFIG)
    border_labels = set()
    for f in findings:
        if f.reason.startswith(_UNEXPECTED_CLIP_TAG):
            border_labels |= set(f.labels)

    assert _value(result, 6) == float(len(border_labels)), cid


def test_ac12_mode6_zero_on_expected_fov_end_touch_real_data_case():
    """The synthetic corpus's clean spine touches no face, so this real-data
    case (a terminal vertebra legitimately touching its own FOV end) is
    exercised only by this hand-built record."""
    pm = _per_mode()
    entries = [
        _entry(20, "L1", touched_faces=("touches_superior",)),
        _entry(21, "L2"),
        _entry(22, "L3"),
    ]
    record = _hand_record(entries, present_levels=["L1", "L2", "L3"])
    fov = derive_fov_coverage(record)
    assert fov.superior_end_level == "L1"

    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 6) == 0.0


# =========================================================================== #
# AC13: mode 7 -- out_of_order_label_count
# =========================================================================== #


def test_ac13_mode7_sequence_break_is_one():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["mode7_sequence_break"])
    assert _value(result, 7) == 1.0


@pytest.mark.parametrize(
    "cid", [c for c in _CASE_IDS if c != "mode7_sequence_break"]
)
def test_ac13_mode7_every_other_corpus_case_is_zero(cid):
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_record_for(cid))
    assert _value(result, 7) == 0.0, cid


def test_ac13_mode7_matches_hand_formula():
    pm = _per_mode()
    record = _RECORDS["mode7_sequence_break"]
    expected = float(len(record["relationships"]["out_of_order_labels"]))
    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 7) == expected


# =========================================================================== #
# AC14: mode 8 -- overlapping_voxel_count
# =========================================================================== #


@pytest.mark.parametrize("cid", _CASE_IDS)
def test_ac14_mode8_plain_extract_feature_record_is_zero(cid):
    """A plain extract_feature_record for any corpus case has an empty
    overlaps list -- a single-integer label map cannot encode an overlap
    (item 040) -- so mode 8 reads 0.0, never None (present-but-empty)."""
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS[cid])
    assert _value(result, 8) == 0.0, cid


def test_ac14_mode8_reconstructed_overlaps_is_1950():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_MODE8_RECORD)
    assert _value(result, 8) == pytest.approx(1950.0, abs=1e-9)


def test_ac14_mode8_matches_hand_formula():
    pm = _per_mode()
    expected = float(sum(e["overlap_voxels"] for e in _MODE8_RECORD["overlaps"]))
    result = pm.compute_per_mode_metrics(_MODE8_RECORD)
    assert _value(result, 8) == expected


def test_ac14_mode8_absent_overlaps_key_is_none():
    pm = _per_mode()
    record = {k: v for k, v in _RECORDS["clean_control"].items() if k != "overlaps"}
    assert "overlaps" not in record
    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 8) is None


def test_ac14_mode8_present_but_empty_list_is_zero():
    pm = _per_mode()
    record = dict(_RECORDS["clean_control"])
    record["overlaps"] = []
    result = pm.compute_per_mode_metrics(record)
    assert _value(result, 8) == 0.0


# =========================================================================== #
# AC15: the isolation matrix -- every metric peaks on its own designated case
# (the load-bearing test)
# =========================================================================== #

_OWN_CASE = {
    1: "mode1_displace",
    2: "mode2_fragment",
    3: "mode3_inject_islands",
    4: "mode4_relabel_swap",
    5: "mode5_remove_level",
    6: "mode6_crop_at_border",
    7: "mode7_sequence_break",
    8: "mode8_force_overlap",
}

# Frozen literal table -- one row per mode, one column per corpus case.
# Values independently verified against the already-shipped primitives each
# metric is built from (extract_feature_record / compute_overlap / BorderRule)
# before this test file was written.
_EXPECTED_ISOLATION_MATRIX = {
    1: {
        "clean_control": 0.0,
        "mode1_displace": 0.1456,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.000288,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 0.12,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 0.1232,
    },
    2: {
        "clean_control": 1.0,
        "mode1_displace": 1.0,
        "mode2_fragment": 0.5,
        "mode3_inject_islands": 0.9985620706183096,
        "mode4_relabel_swap": 1.0,
        "mode5_remove_level": 1.0,
        "mode6_crop_at_border": 1.0,
        "mode7_sequence_break": 1.0,
        "mode8_force_overlap": 1.0,
    },
    3: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 1.0,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 0.0,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 0.0,
    },
    4: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.0,
        "mode4_relabel_swap": 0.4,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 0.0,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 0.0208,
    },
    5: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.0,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 1.0,
        "mode6_crop_at_border": 0.0,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 0.0,
    },
    6: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.0,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 1.0,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 0.0,
    },
    7: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.0,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 0.0,
        "mode7_sequence_break": 1.0,
        "mode8_force_overlap": 0.0,
    },
    8: {
        "clean_control": 0.0,
        "mode1_displace": 0.0,
        "mode2_fragment": 0.0,
        "mode3_inject_islands": 0.0,
        "mode4_relabel_swap": 0.0,
        "mode5_remove_level": 0.0,
        "mode6_crop_at_border": 0.0,
        "mode7_sequence_break": 0.0,
        "mode8_force_overlap": 1950.0,
    },
}


def _is_diagonal_dominant(matrix, baselines, own_case) -> bool:
    """True iff, for every mode m, |value[m][own_case[m]] - baseline[m]| is
    strictly greater than |value[m][j] - baseline[m]| for every other case j."""
    for mode, row in matrix.items():
        base = baselines[mode]
        own = own_case[mode]
        own_dev = abs(row[own] - base)
        for cid, val in row.items():
            if cid == own:
                continue
            if not (own_dev > abs(val - base)):
                return False
    return True


def _build_actual_matrix(pm, island_size_ratio: float = 0.10):
    matrix = {m: {} for m in range(1, 9)}
    for cid in _CASE_IDS:
        result = pm.compute_per_mode_metrics(
            _record_for(cid),
            candidate=_ARRAYS[cid],
            gt=_GT_ARRAY,
            island_size_ratio=island_size_ratio,
        )
        for entry in result.per_mode:
            matrix[entry.failure_mode][cid] = entry.value
    return matrix


def test_ac15_frozen_table_itself_is_diagonally_dominant():
    """Sanity: the hand-verified frozen literal table satisfies the
    dominance property it is supposed to demonstrate."""
    assert _is_diagonal_dominant(_EXPECTED_ISOLATION_MATRIX, _EXPECTED_BASELINES, _OWN_CASE)


def test_ac15_actual_matrix_matches_frozen_table():
    pm = _per_mode()
    actual = _build_actual_matrix(pm)
    for mode, row in _EXPECTED_ISOLATION_MATRIX.items():
        for cid, expected in row.items():
            assert actual[mode][cid] == pytest.approx(expected, abs=1e-6), (mode, cid)


def test_ac15_each_metric_peaks_on_its_own_designated_case():
    pm = _per_mode()
    actual = _build_actual_matrix(pm)
    assert _is_diagonal_dominant(actual, _EXPECTED_BASELINES, _OWN_CASE)


def test_ac15_negative_control_swapping_mode3_row_into_mode2_breaks_dominance():
    """Negative control: assign mode 3's per-case row (rogue_island_count) to
    mode 2's slot -- against mode 2's baseline (1.0) this produces a tie
    between several cases rather than a strict peak on mode2_fragment,
    proving the dominance assertion can actually fail."""
    corrupted = copy.deepcopy(_EXPECTED_ISOLATION_MATRIX)
    corrupted[2] = dict(corrupted[3])
    assert not _is_diagonal_dominant(corrupted, _EXPECTED_BASELINES, _OWN_CASE)


# =========================================================================== #
# AC16: the clean control is at baseline for all eight metrics
# =========================================================================== #


def test_ac16_clean_control_all_eight_at_baseline_and_not_none():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    for entry in result.per_mode:
        assert entry.value is not None
        expected_baseline = 1.0 if entry.failure_mode == 2 else 0.0
        assert entry.value == pytest.approx(expected_baseline, abs=1e-9)
        assert entry.baseline == pytest.approx(expected_baseline, abs=1e-9)


# =========================================================================== #
# AC17: the aggregate overlap context comes verbatim from compute_overlap
# =========================================================================== #


def test_ac17_aggregate_fields_match_compute_overlap_when_both_given():
    pm = _per_mode()
    expected = compute_overlap(_ARRAYS["mode1_displace"], _GT_ARRAY, (1.0, 1.0, 1.0))
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    assert result.mean_dice == expected.mean_dice
    assert result.volume_weighted_dice == expected.volume_weighted_dice
    assert result.n_matched == expected.n_matched
    assert result.n_unmatched == expected.n_unmatched


def test_ac17_aggregate_fields_are_none_none_zero_zero_when_missing():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["clean_control"])
    assert result.mean_dice is None
    assert result.volume_weighted_dice is None
    assert result.n_matched == 0
    assert result.n_unmatched == 0


def test_ac17_aggregate_fields_none_when_only_candidate_given():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["clean_control"], candidate=_GT_ARRAY)
    assert result.mean_dice is None
    assert result.n_matched == 0
    assert result.n_unmatched == 0


# =========================================================================== #
# AC18: no new overlap code
# =========================================================================== #


def _per_mode_source() -> str:
    pm = _per_mode()
    return Path(pm.__file__).read_text(encoding="utf-8")


def test_ac18_no_dice_or_jaccard_arithmetic_literal_substrings():
    source = _per_mode_source()
    for forbidden in ("2.0 *", "2 *", "jaccard =", "dice ="):
        assert forbidden not in source, forbidden


def test_ac18_module_calls_compute_overlap():
    source = _per_mode_source()
    assert "compute_overlap(" in source


def test_ac18_module_does_not_import_eval_metrics():
    """AC25 forbids importing ``segfacet.eval.metrics``, not mentioning it --
    the module's docstring legitimately references
    ``segfacet.eval.metrics.PerModeSensitivity`` to explain how this API
    differs from it, so only actual import statements are checked."""
    source = _per_mode_source()
    assert re.search(r"^(import|from)\s+segfacet\.eval\.metrics", source, re.MULTILINE) is None


# =========================================================================== #
# AC19: to_dict() round-trips through JSON unchanged
# =========================================================================== #


def _assert_json_native(value):
    if value is None:
        return
    t = type(value)
    if t is dict:
        for v in value.values():
            _assert_json_native(v)
    elif t is list:
        for v in value:
            _assert_json_native(v)
    elif t in (str, float, int, bool):
        return
    else:
        raise AssertionError(f"non-JSON-native type {t!r} in to_dict() output: {value!r}")


def test_ac19_to_dict_round_trips_through_json():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    d = result.to_dict()
    assert json.loads(json.dumps(d)) == d


def test_ac19_to_dict_contains_only_json_native_types():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    d = result.to_dict()
    assert type(d) is dict
    _assert_json_native(d)


def test_ac19_to_dict_has_no_tuples():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["clean_control"])
    d = result.to_dict()
    assert isinstance(d["per_mode"], list)
    for entry in d["per_mode"]:
        assert isinstance(entry, dict)


# =========================================================================== #
# AC20: the API never mutates its inputs
# =========================================================================== #


def test_ac20_record_is_not_mutated():
    pm = _per_mode()
    record = copy.deepcopy(_RECORDS["mode1_displace"])
    snapshot = copy.deepcopy(record)
    pm.compute_per_mode_metrics(
        record, candidate=_ARRAYS["mode1_displace"].copy(), gt=_GT_ARRAY.copy()
    )
    assert record == snapshot


def test_ac20_candidate_and_gt_arrays_are_not_mutated():
    pm = _per_mode()
    cand = _ARRAYS["mode1_displace"].copy()
    gt = _GT_ARRAY.copy()
    cand_before = cand.copy()
    gt_before = gt.copy()
    pm.compute_per_mode_metrics(_RECORDS["mode1_displace"], candidate=cand, gt=gt)
    assert np.array_equal(cand, cand_before)
    assert np.array_equal(gt, gt_before)


# =========================================================================== #
# AC21: the API is idempotent
# =========================================================================== #


def test_ac21_two_successive_calls_are_dataclass_equal():
    pm = _per_mode()
    first = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    second = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    assert first == second


def test_ac21_two_successive_calls_have_equal_to_dict_output():
    pm = _per_mode()
    first = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    second = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    assert first.to_dict() == second.to_dict()


# =========================================================================== #
# AC22: a record missing an optional block degrades to None, not an exception
# =========================================================================== #


def test_ac22_empty_record_yields_none_for_the_five_record_derived_modes():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics({})
    for mode in (2, 3, 6, 7, 8):
        entry = result.per_mode[mode - 1]
        assert entry.value is None, mode
        assert isinstance(entry.detail, str) and entry.detail, mode


def test_ac22_zero_label_record_relationships_none_no_stage3_no_per_label():
    seg_img = make_labelmap(blocks={})
    record = extract_feature_record(seg_img, _CONFIG)
    assert record["per_label"] == {}
    assert record["relationships"] is None
    assert record["overlaps"] == []
    assert "stage3" not in record

    pm = _per_mode()
    result = pm.compute_per_mode_metrics(record)
    for mode in (2, 3, 6, 7):
        assert result.per_mode[mode - 1].value is None, mode
    assert result.per_mode[8 - 1].value == 0.0


def test_ac22_one_label_record_no_stage3_modes_resolve_from_single_entry():
    seg_img = make_labelmap(blocks={1: ((0, 4), (0, 4), (0, 4))})
    record = extract_feature_record(seg_img, _CONFIG)
    assert "stage3" not in record

    pm = _per_mode()
    result = pm.compute_per_mode_metrics(record)
    assert result.per_mode[7 - 1].value == 0.0  # mode 7
    assert result.per_mode[2 - 1].value is not None  # mode 2 resolves
    assert result.per_mode[3 - 1].value is not None  # mode 3 resolves
    assert result.per_mode[6 - 1].value is not None  # mode 6 resolves


def test_ac22_malformed_per_label_as_list_degrades_to_none_not_typeerror():
    pm = _per_mode()
    record = {"per_label": [1, 2, 3], "relationships": None, "overlaps": []}
    result = pm.compute_per_mode_metrics(record)  # must not raise
    for mode in (2, 3, 6):
        assert result.per_mode[mode - 1].value is None, mode


def test_ac22_malformed_components_as_string_degrades_to_none_not_typeerror():
    pm = _per_mode()
    record = {
        "per_label": {1: {"label": 1, "level_name": "L1", "components": "not-a-dict"}},
        "relationships": None,
        "overlaps": [],
    }
    result = pm.compute_per_mode_metrics(record)  # must not raise
    assert result.per_mode[2 - 1].value is None
    assert result.per_mode[3 - 1].value is None


# =========================================================================== #
# AC23: a missing candidate/GT pair degrades to None, not an exception
# =========================================================================== #


def test_ac23_missing_candidate_only():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["mode2_fragment"], gt=_GT_ARRAY)
    for mode in (1, 4, 5):
        entry = result.per_mode[mode - 1]
        assert entry.value is None, mode
        assert isinstance(entry.detail, str) and entry.detail
    assert result.per_mode[2 - 1].value == pytest.approx(0.5, abs=1e-9)


def test_ac23_missing_gt_only():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode2_fragment"], candidate=_ARRAYS["mode2_fragment"]
    )
    for mode in (1, 4, 5):
        entry = result.per_mode[mode - 1]
        assert entry.value is None, mode
        assert isinstance(entry.detail, str) and entry.detail


def test_ac23_both_missing_five_record_modes_still_resolve():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(_RECORDS["mode2_fragment"])
    for mode in (1, 4, 5):
        assert result.per_mode[mode - 1].value is None, mode
    for mode in (2, 3, 6, 7, 8):
        assert result.per_mode[mode - 1].value is not None, mode


# =========================================================================== #
# AC24: a candidate/GT shape mismatch propagates FacetInputError
# =========================================================================== #


def test_ac24_shape_mismatch_raises_facet_input_error():
    pm = _per_mode()
    mismatched = _GT_ARRAY[:-1]
    assert mismatched.shape != _GT_ARRAY.shape
    with pytest.raises(FacetInputError):
        pm.compute_per_mode_metrics(
            _RECORDS["clean_control"], candidate=mismatched, gt=_GT_ARRAY
        )


def test_ac24_shape_mismatch_is_a_caller_error_not_a_silent_none():
    """Distinguishing this from AC23's degradation: a shape mismatch is a
    caller error that must propagate, not be swallowed into None."""
    pm = _per_mode()
    mismatched = np.zeros((2, 2, 2), dtype=_GT_ARRAY.dtype)
    with pytest.raises(FacetInputError):
        pm.compute_per_mode_metrics({}, candidate=mismatched, gt=_GT_ARRAY)


# =========================================================================== #
# AC25: the scope fence holds
# =========================================================================== #

_SEGFACET_SRC = Path(
    __import__("segfacet").__file__
).resolve().parent

_PRE_099_HASHES = {
    "report_schema_v0.json": "8c7b48c1fcfc82edf49187c8aa912ac42470b20f53fd739c9b65f0bbf76f4a4b",
    # Updated by item 101 (added --per-mode / compare-runs to cli.py, a change
    # authorized by item 101's own spec, not scope creep on this file).
    "cli.py": "0284d05b819c384ebb3fead90d256d46466a390812e73b379b1880ad12f28b32",
    "eval/metrics.py": "15a21e7d9c8d738bfe5755637f736e60fd86d620c6117dd39a5d3b3bfa8bff8a",
}
_PRE_099_HEURISTICS_COMBINED_HASH = (
    "92cdc63e9a9bcef3c4ebd6c9b5567e80c30a3077bd3613d635c443bf055d19c4"
)
_PRE_099_GOLDEN_COMBINED_HASH = (
    "08fc9ddc0b149d109eb5f6a5265b7a768ec1ae1f6a518316c4719d4a617ef2a3"
)


@pytest.mark.parametrize("relpath", sorted(_PRE_099_HASHES))
def test_ac25_named_file_byte_identical_to_pre_099_state(relpath):
    path = _SEGFACET_SRC / relpath
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _PRE_099_HASHES[relpath], relpath


def test_ac25_heuristics_package_byte_identical_to_pre_099_state():
    heur_files = sorted((_SEGFACET_SRC / "heuristics").rglob("*.py"))
    h = hashlib.sha256()
    for f in heur_files:
        h.update(f.relative_to(_SEGFACET_SRC).as_posix().encode())
        h.update(f.read_bytes())
    assert h.hexdigest() == _PRE_099_HEURISTICS_COMBINED_HASH


def test_ac25_committed_goldens_byte_identical_to_pre_099_state():
    golden_dir = Path(__file__).resolve().parent / "corpus" / "golden"
    files = sorted(golden_dir.glob("*.json"))
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode())
        h.update(f.read_bytes())
    assert h.hexdigest() == _PRE_099_GOLDEN_COMBINED_HASH


def test_ac25_eval_metrics_public_names_unchanged():
    from segfacet.eval.metrics import CohortMetrics, PerModeSensitivity

    cohort_fields = {f.name for f in dataclasses.fields(CohortMetrics)}
    assert cohort_fields == {
        "counts",
        "false_positive_rate",
        "sensitivity",
        "specificity",
        "per_mode",
        "dice_vs_flag",
        "feature_divergence_vs_flag",
        "n_cases",
    }
    assert dataclasses.is_dataclass(PerModeSensitivity)


def test_ac25_per_mode_module_does_not_import_eval_metrics():
    source = _per_mode_source()
    assert "from segfacet.eval import metrics" not in source
    assert "from segfacet.eval.metrics import" not in source
    assert "import segfacet.eval.metrics" not in source


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_candidate_and_gt_both_all_zero_mode1_is_none_not_nan():
    pm = _per_mode()
    zero_cand = np.zeros_like(_GT_ARRAY)
    zero_gt = np.zeros_like(_GT_ARRAY)
    result = pm.compute_per_mode_metrics({}, candidate=zero_cand, gt=zero_gt)
    assert result.per_mode[0].value is None
    assert not (isinstance(result.per_mode[0].value, float) and result.per_mode[0].value != result.per_mode[0].value)


def test_adv_candidate_and_gt_both_all_zero_modes4_5_are_zero():
    pm = _per_mode()
    zero_cand = np.zeros_like(_GT_ARRAY)
    zero_gt = np.zeros_like(_GT_ARRAY)
    result = pm.compute_per_mode_metrics({}, candidate=zero_cand, gt=zero_gt)
    assert result.per_mode[4 - 1].value == 0.0
    assert result.per_mode[5 - 1].value == 0.0


def test_adv_candidate_is_gt_same_object_every_paired_metric_at_baseline():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["clean_control"], candidate=_GT_ARRAY, gt=_GT_ARRAY
    )
    assert result.per_mode[1 - 1].value == 0.0
    assert result.per_mode[4 - 1].value == 0.0
    assert result.per_mode[5 - 1].value == 0.0
    assert result.mean_dice == 1.0


def test_adv_non_isotropic_spacing_seven_voxel_ratio_metrics_are_invariant():
    pm = _per_mode()
    isotropic = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"],
        candidate=_ARRAYS["mode1_displace"],
        gt=_GT_ARRAY,
        spacing=(1.0, 1.0, 1.0),
    )
    anisotropic = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"],
        candidate=_ARRAYS["mode1_displace"],
        gt=_GT_ARRAY,
        spacing=(0.5, 1.0, 2.0),
    )
    for mode in (1, 2, 3, 4, 6, 7, 8):
        assert isotropic.per_mode[mode - 1].value == pytest.approx(
            anisotropic.per_mode[mode - 1].value, abs=1e-9
        ), mode


def test_adv_non_isotropic_spacing_mode5_count_is_spacing_invariant():
    pm = _per_mode()
    isotropic = pm.compute_per_mode_metrics(
        _RECORDS["mode5_remove_level"],
        candidate=_ARRAYS["mode5_remove_level"],
        gt=_GT_ARRAY,
        spacing=(1.0, 1.0, 1.0),
    )
    anisotropic = pm.compute_per_mode_metrics(
        _RECORDS["mode5_remove_level"],
        candidate=_ARRAYS["mode5_remove_level"],
        gt=_GT_ARRAY,
        spacing=(0.5, 1.0, 2.0),
    )
    assert isotropic.per_mode[5 - 1].value == anisotropic.per_mode[5 - 1].value


def test_adv_non_isotropic_spacing_aggregate_matches_compute_overlap():
    pm = _per_mode()
    spacing = (0.5, 1.0, 2.0)
    expected = compute_overlap(_ARRAYS["mode1_displace"], _GT_ARRAY, spacing)
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"],
        candidate=_ARRAYS["mode1_displace"],
        gt=_GT_ARRAY,
        spacing=spacing,
    )
    assert result.mean_dice == expected.mean_dice
    assert result.volume_weighted_dice == expected.volume_weighted_dice


def test_adv_default_spacing_is_isotropic_when_unspecified():
    pm = _per_mode()
    result = pm.compute_per_mode_metrics(
        _RECORDS["mode1_displace"], candidate=_ARRAYS["mode1_displace"], gt=_GT_ARRAY
    )
    expected = compute_overlap(_ARRAYS["mode1_displace"], _GT_ARRAY, (1.0, 1.0, 1.0))
    assert result.mean_dice == expected.mean_dice
