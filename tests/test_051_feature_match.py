"""Tests for the feature-set match / divergence-by-label module (item 051).

Covers all fourteen Acceptance Criteria plus adversarial and edge-case inputs,
built on tiny hand-constructed ``features`` block dicts (schema-shaped, per
``feature_report.build_features_block``) so every expected difference/score is
hand-computed and exact.

Additional adversarial cases: empty blocks on both sides, a negative volume
difference, a matched label with every tracked feature unavailable, a matched
label missing ``centroid`` entirely, and a Stage-2-only block (no ``stage3``)
on both sides.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import copy
import math

import pytest

from segqc.io import SegQCInputError
from segqc.labels import UNKNOWN


# =========================================================================== #
# Helpers
# =========================================================================== #


def _entry(
    label,
    level_name,
    *,
    volume=1000.0,
    ex=10.0,
    ey=10.0,
    ez=10.0,
    centroid_mm=(0.0, 0.0, 0.0),
):
    """Build a single ``per_label`` entry (Stage-2 geometry + centroid only)."""
    return {
        "label": label,
        "level_name": level_name,
        "geometry": {
            "physical_volume_mm3": volume,
            "extent_x_mm": ex,
            "extent_y_mm": ey,
            "extent_z_mm": ez,
        },
        "centroid": {"centroid_mm": list(centroid_mm)},
    }


def _block(entries, offsets=None):
    """Build a minimal ``features`` block dict from a list of per_label entries.

    ``offsets`` is an optional list of ``(label, offset_mm)`` pairs added under
    ``stage3.per_label_offsets``.
    """
    block = {
        "features_version": "0.2" if offsets is not None else "0.1",
        "per_label": {str(e["label"]): e for e in entries},
    }
    if offsets is not None:
        block["stage3"] = {
            "per_label_offsets": [
                {"label": lbl, "offset_mm": off} for lbl, off in offsets
            ]
        }
    return block


# =========================================================================== #
# AC1: module & public API exist
# =========================================================================== #


def test_ac1_import_from_feature_match_module():
    """AC1: all five names import from segqc.eval.feature_match."""
    from segqc.eval.feature_match import (  # noqa: F401
        TRACKED_FEATURES,
        FeatureDifference,
        FeatureMatchResult,
        LabelFeatureDivergence,
        compute_feature_match,
    )

    assert callable(compute_feature_match)


def test_ac1_reexported_from_eval_package():
    """AC1: compute_feature_match is re-exported from segqc.eval."""
    from segqc.eval import compute_feature_match

    assert callable(compute_feature_match)


def test_ac1_module_dunder_all():
    """AC1: segqc.eval.feature_match.__all__ lists all five public names."""
    import segqc.eval.feature_match as fm_mod

    assert set(fm_mod.__all__) >= {
        "compute_feature_match",
        "TRACKED_FEATURES",
        "FeatureDifference",
        "LabelFeatureDivergence",
        "FeatureMatchResult",
    }


def test_ac1_feature_difference_is_frozen_dataclass_with_fields():
    """AC1: FeatureDifference is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.feature_match import FeatureDifference

    assert dataclasses.is_dataclass(FeatureDifference)
    field_names = {f.name for f in dataclasses.fields(FeatureDifference)}
    assert field_names == {
        "feature",
        "candidate_value",
        "gt_value",
        "absolute",
        "relative",
        "available",
    }
    assert FeatureDifference.__dataclass_params__.frozen is True


def test_ac1_label_feature_divergence_is_frozen_dataclass_with_fields():
    """AC1: LabelFeatureDivergence is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.feature_match import LabelFeatureDivergence

    assert dataclasses.is_dataclass(LabelFeatureDivergence)
    field_names = {f.name for f in dataclasses.fields(LabelFeatureDivergence)}
    assert field_names == {
        "value",
        "name",
        "matched",
        "differences",
        "centroid_distance_mm",
        "divergence_score",
    }
    assert LabelFeatureDivergence.__dataclass_params__.frozen is True


def test_ac1_feature_match_result_is_frozen_dataclass_with_fields():
    """AC1: FeatureMatchResult is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.feature_match import FeatureMatchResult

    assert dataclasses.is_dataclass(FeatureMatchResult)
    field_names = {f.name for f in dataclasses.fields(FeatureMatchResult)}
    assert field_names == {
        "per_label",
        "case_divergence",
        "mean_centroid_distance_mm",
        "n_matched",
        "n_unmatched",
    }
    assert FeatureMatchResult.__dataclass_params__.frozen is True


# =========================================================================== #
# AC2: TRACKED_FEATURES is the documented ordered set
# =========================================================================== #


def test_ac2_tracked_features_documented_tuple():
    """AC2: TRACKED_FEATURES equals the documented ordered tuple."""
    from segqc.eval.feature_match import TRACKED_FEATURES

    assert TRACKED_FEATURES == (
        "physical_volume_mm3",
        "extent_x_mm",
        "extent_y_mm",
        "extent_z_mm",
        "spline_offset_mm",
    )


def test_ac2_differences_one_per_tracked_feature_in_order():
    """AC2: a matched label's differences has one entry per name, in order."""
    from segqc.eval.feature_match import TRACKED_FEATURES, compute_feature_match

    block = _block([_entry(20, "L1")], offsets=[(20, 1.0)])
    result = compute_feature_match(block, block)
    entry = result.per_label[0]
    assert tuple(d.feature for d in entry.differences) == TRACKED_FEATURES


# =========================================================================== #
# AC3: identical feature sets -> zero divergence everywhere
# =========================================================================== #


def test_ac3_identical_blocks_all_zero():
    """AC3: same block on both sides -> every difference/score is exactly zero."""
    from segqc.eval.feature_match import compute_feature_match

    block = _block(
        [
            _entry(20, "L1", volume=1000.0, centroid_mm=(1.0, 2.0, 3.0)),
            _entry(21, "L2", volume=2000.0, centroid_mm=(4.0, 5.0, 6.0)),
        ],
        offsets=[(20, 0.5), (21, 1.5)],
    )
    result = compute_feature_match(block, block)
    for entry in result.per_label:
        assert entry.matched is True
        for diff in entry.differences:
            assert diff.available is True
            assert diff.absolute == 0.0
            assert diff.relative == 0.0
        assert entry.centroid_distance_mm == 0.0
        assert entry.divergence_score == 0.0
    assert result.case_divergence == 0.0
    assert result.mean_centroid_distance_mm == 0.0


# =========================================================================== #
# AC4: a scalar feature difference is signed and matches the hand value
# =========================================================================== #


def test_ac4_candidate_larger_gives_positive_difference():
    """AC4: candidate volume > GT volume -> positive absolute/relative."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=1200.0)])
    gt = _block([_entry(20, "L1", volume=1000.0)])
    result = compute_feature_match(cand, gt)
    diff = result.per_label[0].differences[0]
    assert diff.feature == "physical_volume_mm3"
    assert diff.absolute == pytest.approx(200.0)
    assert diff.relative == pytest.approx(200.0 / 1000.0)
    assert diff.absolute > 0
    assert diff.relative > 0


def test_ac4_candidate_smaller_gives_negative_difference():
    """AC4: candidate volume < GT volume -> negative absolute/relative."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=800.0)])
    gt = _block([_entry(20, "L1", volume=1000.0)])
    result = compute_feature_match(cand, gt)
    diff = result.per_label[0].differences[0]
    assert diff.absolute == pytest.approx(-200.0)
    assert diff.relative == pytest.approx(-200.0 / 1000.0)
    assert diff.absolute < 0
    assert diff.relative < 0


# =========================================================================== #
# AC5: perturbing one label localises the divergence to that label
# =========================================================================== #


def test_ac5_single_label_perturbation_is_localised():
    """AC5: only the perturbed label has a non-zero divergence score."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1", volume=1000.0), _entry(21, "L2", volume=2000.0)])
    cand = copy.deepcopy(gt)
    cand["per_label"]["20"]["geometry"]["physical_volume_mm3"] = 1500.0

    result = compute_feature_match(cand, gt)
    by_value = {e.value: e for e in result.per_label}

    perturbed = by_value[20]
    assert perturbed.divergence_score > 0.0
    vol_diff = next(
        d for d in perturbed.differences if d.feature == "physical_volume_mm3"
    )
    assert vol_diff.absolute != 0.0

    unperturbed = by_value[21]
    assert unperturbed.divergence_score == 0.0
    for diff in unperturbed.differences:
        assert diff.absolute == 0.0


# =========================================================================== #
# AC6: centroid displacement is the Euclidean distance of centroid_mm
# =========================================================================== #


def test_ac6_centroid_distance_hand_computed():
    """AC6: a (3, 4, 0) centroid shift yields centroid_distance_mm == 5.0."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1", centroid_mm=(0.0, 0.0, 0.0))])
    cand = _block([_entry(20, "L1", centroid_mm=(3.0, 4.0, 0.0))])
    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    assert entry.centroid_distance_mm == pytest.approx(5.0)
    # Not folded into divergence_score: no scalar features differ.
    assert entry.divergence_score == 0.0


def test_ac6_centroid_distance_zero_when_equal():
    """AC6: equal centroids yield centroid_distance_mm == 0.0."""
    from segqc.eval.feature_match import compute_feature_match

    block = _block([_entry(20, "L1", centroid_mm=(1.0, 2.0, 3.0))])
    result = compute_feature_match(block, block)
    assert result.per_label[0].centroid_distance_mm == 0.0


# =========================================================================== #
# AC7: per-label divergence score is the mean abs relative over available features
# =========================================================================== #


def test_ac7_divergence_score_hand_computed():
    """AC7: divergence_score equals mean(abs(relative)) over available features."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1", volume=1000.0, ex=10.0, ey=10.0, ez=10.0)])
    cand = _block([_entry(20, "L1", volume=1100.0, ex=8.0, ey=10.0, ez=10.0)])
    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    rel_vol = 100.0 / 1000.0
    rel_ex = -2.0 / 10.0
    expected = (abs(rel_vol) + abs(rel_ex)) / 2.0
    assert entry.divergence_score == pytest.approx(expected)


def test_ac7_divergence_score_none_when_no_defined_relative():
    """AC7: no tracked feature has a defined relative -> divergence_score is None."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1", volume=0.0, ex=0.0, ey=0.0, ez=0.0)])
    cand = _block([_entry(20, "L1", volume=5.0, ex=5.0, ey=5.0, ez=5.0)])
    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.divergence_score is None


# =========================================================================== #
# AC8: case-level divergence aggregates the per-label scores
# =========================================================================== #


def test_ac8_case_aggregates_hand_computed():
    """AC8: case_divergence/mean_centroid_distance_mm equal the hand means."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block(
        [
            _entry(20, "L1", volume=1000.0, centroid_mm=(0.0, 0.0, 0.0)),
            _entry(21, "L2", volume=2000.0, centroid_mm=(0.0, 0.0, 0.0)),
        ]
    )
    cand = copy.deepcopy(gt)
    cand["per_label"]["20"]["geometry"]["physical_volume_mm3"] = 1100.0
    cand["per_label"]["20"]["centroid"]["centroid_mm"] = [3.0, 4.0, 0.0]
    # label 21 unchanged -> score 0.0, centroid distance 0.0

    result = compute_feature_match(cand, gt)
    matched = [e for e in result.per_label if e.matched]
    expected_div = sum(e.divergence_score for e in matched) / len(matched)
    expected_cent = sum(e.centroid_distance_mm for e in matched) / len(matched)
    assert result.case_divergence == pytest.approx(expected_div)
    assert result.mean_centroid_distance_mm == pytest.approx(expected_cent)


def test_ac8_no_qualifying_labels_aggregates_none():
    """AC8: zero matched labels -> case_divergence and mean_centroid_distance_mm are None."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1")])
    gt = _block([_entry(21, "L2")])
    result = compute_feature_match(cand, gt)
    assert result.n_matched == 0
    assert result.case_divergence is None
    assert result.mean_centroid_distance_mm is None


# =========================================================================== #
# AC9: a label present on only one side is unmatched, not an error
# =========================================================================== #


def test_ac9_candidate_only_label_is_unmatched():
    """AC9: a label only in candidate is unmatched with empty differences and None scores."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1"), _entry(21, "L2")])
    gt = _block([_entry(20, "L1")])
    result = compute_feature_match(cand, gt)
    by_value = {e.value: e for e in result.per_label}
    entry = by_value[21]
    assert entry.matched is False
    assert entry.differences == ()
    assert entry.centroid_distance_mm is None
    assert entry.divergence_score is None
    assert result.n_unmatched == 1


def test_ac9_gt_only_label_is_unmatched_and_excluded_from_aggregates():
    """AC9: a label only in GT is unmatched, no raise, excluded from aggregates."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=1000.0)])
    gt = _block([_entry(20, "L1", volume=1000.0), _entry(23, "L4")])
    result = compute_feature_match(cand, gt)  # must not raise
    by_value = {e.value: e for e in result.per_label}
    entry = by_value[23]
    assert entry.matched is False
    assert entry.differences == ()
    assert entry.centroid_distance_mm is None
    assert entry.divergence_score is None
    assert result.n_unmatched == 1
    assert result.n_matched == 1
    # Aggregates reflect only the matched, identical label 20.
    assert result.case_divergence == 0.0


# =========================================================================== #
# AC10: a tracked feature unavailable on one side is marked, not fabricated
# =========================================================================== #


def test_ac10_offset_present_only_on_candidate_side():
    """AC10: spline_offset_mm present in candidate stage3 but absent in gt -> unavailable."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1")], offsets=[(20, 2.5)])
    gt = _block([_entry(20, "L1")])  # no stage3 at all
    result = compute_feature_match(cand, gt)  # must not raise
    entry = result.per_label[0]
    offset_diff = next(
        d for d in entry.differences if d.feature == "spline_offset_mm"
    )
    assert offset_diff.available is False
    assert offset_diff.absolute is None
    assert offset_diff.relative is None
    assert offset_diff.candidate_value == 2.5
    assert offset_diff.gt_value is None
    # Excluded from the divergence score (only the four geometry features count,
    # all identical here -> zero).
    assert entry.divergence_score == 0.0


def test_ac10_offset_present_only_on_gt_side():
    """AC10: spline_offset_mm present in gt stage3 but absent in candidate -> unavailable."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1")])
    gt = _block([_entry(20, "L1")], offsets=[(20, 1.0)])
    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    offset_diff = next(
        d for d in entry.differences if d.feature == "spline_offset_mm"
    )
    assert offset_diff.available is False
    assert offset_diff.absolute is None
    assert offset_diff.relative is None
    assert offset_diff.candidate_value is None
    assert offset_diff.gt_value == 1.0


# =========================================================================== #
# AC11: a zero GT value yields relative is None but a defined absolute
# =========================================================================== #


def test_ac11_zero_gt_value_relative_none_absolute_defined():
    """AC11: GT volume 0.0, candidate non-zero -> absolute defined, relative None."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1", volume=0.0)])
    cand = _block([_entry(20, "L1", volume=42.0)])
    result = compute_feature_match(cand, gt)
    diff = next(
        d
        for d in result.per_label[0].differences
        if d.feature == "physical_volume_mm3"
    )
    assert diff.absolute == pytest.approx(42.0)
    assert diff.relative is None
    assert diff.available is True


# =========================================================================== #
# AC12: entries are named and ordered via the Stage-0 convention
# =========================================================================== #


def test_ac12_ordered_canonically_then_by_value_with_unmapped_distinct():
    """AC12: per_label is ordered by CANONICAL_ORDER then value; unmapped stay distinct."""
    from segqc.eval.feature_match import compute_feature_match

    entries_cand = [
        _entry(22, "L3"),
        _entry(1, "C1"),
        _entry(901, UNKNOWN),
        _entry(8, "T1"),
        _entry(900, UNKNOWN),
    ]
    entries_gt = [copy.deepcopy(e) for e in entries_cand]
    cand = _block(entries_cand)
    gt = _block(entries_gt)
    result = compute_feature_match(cand, gt)
    names_in_order = [e.name for e in result.per_label]
    recognised = [n for n in names_in_order if n != UNKNOWN]
    assert recognised == ["C1", "T1", "L3"]
    # Both unmapped labels present, distinct, ordered by ascending value, last.
    unmapped_entries = [e for e in result.per_label if e.name == UNKNOWN]
    assert [e.value for e in unmapped_entries] == [900, 901]
    assert names_in_order[-2:] == [UNKNOWN, UNKNOWN]


def test_ac12_matched_name_is_gt_authoritative():
    """AC12: for a matched label, name comes from the GT side's level_name."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "WrongName")])
    gt = _block([_entry(20, "L1")])
    result = compute_feature_match(cand, gt)
    assert result.per_label[0].name == "L1"


# =========================================================================== #
# AC13: malformed input raises SegQCInputError
# =========================================================================== #


def test_ac13_candidate_not_a_mapping_raises():
    """AC13: candidate=None raises SegQCInputError."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1")])
    with pytest.raises(SegQCInputError):
        compute_feature_match(None, gt)


def test_ac13_missing_per_label_raises():
    """AC13: a block dict lacking per_label raises SegQCInputError."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1")])
    with pytest.raises(SegQCInputError):
        compute_feature_match({}, gt)


def test_ac13_per_label_not_a_dict_raises():
    """AC13: per_label as a list (not a mapping) raises SegQCInputError."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1")])
    bad = {"features_version": "0.1", "per_label": []}
    with pytest.raises(SegQCInputError):
        compute_feature_match(bad, gt)


def test_ac13_not_raw_type_error_or_attribute_error():
    """AC13: malformed input is a SegQCInputError, not a bare TypeError/AttributeError."""
    from segqc.eval.feature_match import compute_feature_match

    gt = _block([_entry(20, "L1")])
    try:
        compute_feature_match(42, gt)
    except SegQCInputError:
        pass
    else:
        pytest.fail("expected SegQCInputError")


# =========================================================================== #
# AC14: pure, deterministic, and non-mutating
# =========================================================================== #


def test_ac14_deterministic_across_two_calls():
    """AC14: two calls on the same inputs return equal per_label ordering and aggregates."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block(
        [_entry(20, "L1", volume=1200.0), _entry(900, UNKNOWN)],
        offsets=[(20, 1.0)],
    )
    gt = _block(
        [_entry(20, "L1", volume=1000.0), _entry(900, UNKNOWN)],
        offsets=[(20, 0.5)],
    )
    r1 = compute_feature_match(cand, gt)
    r2 = compute_feature_match(cand, gt)
    assert r1 == r2
    assert r1.case_divergence == r2.case_divergence
    assert r1.mean_centroid_distance_mm == r2.mean_centroid_distance_mm
    assert r1.n_matched == r2.n_matched
    assert r1.n_unmatched == r2.n_unmatched


def test_ac14_inputs_not_mutated():
    """AC14: candidate and gt block dicts (and nested dicts) are unchanged after the call."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=1200.0)], offsets=[(20, 1.0)])
    gt = _block([_entry(20, "L1", volume=1000.0)], offsets=[(20, 0.5)])
    cand_before = copy.deepcopy(cand)
    gt_before = copy.deepcopy(gt)
    compute_feature_match(cand, gt)
    assert cand == cand_before
    assert gt == gt_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_blocks_both_sides():
    """Both blocks empty -> per_label == (), counts 0, aggregates None."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([])
    gt = _block([])
    result = compute_feature_match(cand, gt)
    assert result.per_label == ()
    assert result.n_matched == 0
    assert result.n_unmatched == 0
    assert result.case_divergence is None
    assert result.mean_centroid_distance_mm is None


def test_adv_negative_volume_difference():
    """A matched label with candidate volume below GT yields negative absolute/relative."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=-50.0)])
    gt = _block([_entry(20, "L1", volume=100.0)])
    result = compute_feature_match(cand, gt)
    diff = next(
        d
        for d in result.per_label[0].differences
        if d.feature == "physical_volume_mm3"
    )
    assert diff.absolute == pytest.approx(-150.0)
    assert diff.relative == pytest.approx(-1.5)


def test_adv_all_tracked_features_unavailable_but_matched():
    """A matched label with every tracked feature missing on one side -> divergence_score None, matched True."""
    from segqc.eval.feature_match import FeatureDifference, compute_feature_match

    cand_entry = _entry(20, "L1")
    del cand_entry["geometry"]["extent_x_mm"]
    del cand_entry["geometry"]["extent_y_mm"]
    del cand_entry["geometry"]["extent_z_mm"]
    del cand_entry["geometry"]["physical_volume_mm3"]
    cand = _block([cand_entry])
    gt = _block([_entry(20, "L1")])

    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.divergence_score is None
    for diff in entry.differences:
        assert isinstance(diff, FeatureDifference)
        assert diff.available is False
        assert diff.absolute is None
        assert diff.relative is None


def test_adv_matched_label_missing_centroid_entirely():
    """A matched label missing the centroid entry -> centroid_distance_mm is None, no crash."""
    from segqc.eval.feature_match import compute_feature_match

    cand_entry = _entry(20, "L1")
    del cand_entry["centroid"]
    cand = _block([cand_entry])
    gt = _block([_entry(20, "L1")])

    result = compute_feature_match(cand, gt)  # must not raise
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.centroid_distance_mm is None


def test_adv_stage2_only_blocks_no_stage3_on_either_side():
    """Neither block has stage3 -> spline_offset_mm unavailable everywhere, others still compared."""
    from segqc.eval.feature_match import compute_feature_match

    cand = _block([_entry(20, "L1", volume=1100.0)])
    gt = _block([_entry(20, "L1", volume=1000.0)])
    result = compute_feature_match(cand, gt)
    entry = result.per_label[0]
    offset_diff = next(
        d for d in entry.differences if d.feature == "spline_offset_mm"
    )
    assert offset_diff.available is False
    assert offset_diff.candidate_value is None
    assert offset_diff.gt_value is None
    vol_diff = next(
        d for d in entry.differences if d.feature == "physical_volume_mm3"
    )
    assert vol_diff.available is True
    assert vol_diff.absolute == pytest.approx(100.0)
