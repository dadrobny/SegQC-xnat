"""Tests for the DICE-vs-GT overlap module (item 050).

Covers all thirteen Acceptance Criteria plus adversarial and edge-case inputs,
built on tiny hand-constructed integer label arrays so every expected DICE/
Jaccard value is hand-computed and exact.

Additional adversarial cases: a single-voxel label, a label fully contained in
the other (asymmetric sizes, DICE < 1), a matched label with zero intersection,
a negative/very large unmapped integer label, zero spacing components, and
determinism / non-mutation checks.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import numpy as np
import pytest

from segqc.io import SegQCInputError
from segqc.labels import CANONICAL_ORDER, UNKNOWN, LabelConvention


# =========================================================================== #
# Helpers
# =========================================================================== #


def _array(shape, label_voxels):
    """Build an integer label array from ``{label: [(idx, ...), ...]}``."""
    arr = np.zeros(shape, dtype=np.int64)
    for label, voxels in label_voxels.items():
        for idx in voxels:
            arr[idx] = label
    return arr


def _range_1d(n, label_voxels):
    """Build a 1-D integer label array of length ``n``.

    ``label_voxels`` is ``{label: (start, stop)}`` half-open index ranges.
    """
    arr = np.zeros((n,), dtype=np.int64)
    for label, (start, stop) in label_voxels.items():
        arr[start:stop] = label
    return arr


# =========================================================================== #
# AC1: module & public API exist
# =========================================================================== #


def test_ac1_import_from_overlap_module():
    """AC1: compute_overlap, LabelOverlap, OverlapResult import from segqc.eval.overlap."""
    from segqc.eval.overlap import (  # noqa: F401
        LabelOverlap,
        OverlapResult,
        compute_overlap,
    )

    assert callable(compute_overlap)


def test_ac1_reexported_from_eval_package():
    """AC1: compute_overlap is re-exported from segqc.eval."""
    from segqc.eval import compute_overlap

    assert callable(compute_overlap)


def test_ac1_module_dunder_all():
    """AC1: segqc.eval.overlap.__all__ lists all three public names."""
    import segqc.eval.overlap as overlap_mod

    assert set(overlap_mod.__all__) >= {
        "compute_overlap",
        "LabelOverlap",
        "OverlapResult",
    }


def test_ac1_label_overlap_is_frozen_dataclass_with_fields():
    """AC1: LabelOverlap is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.overlap import LabelOverlap

    assert dataclasses.is_dataclass(LabelOverlap)
    assert dataclasses.fields(LabelOverlap)[0].name  # non-empty
    field_names = {f.name for f in dataclasses.fields(LabelOverlap)}
    assert field_names == {
        "value",
        "name",
        "matched",
        "dice",
        "jaccard",
        "candidate_voxels",
        "gt_voxels",
        "intersection_voxels",
        "physical_volume_mm3",
    }
    params = LabelOverlap.__dataclass_params__
    assert params.frozen is True


def test_ac1_overlap_result_is_frozen_dataclass_with_fields():
    """AC1: OverlapResult is frozen and carries the documented fields."""
    import dataclasses

    from segqc.eval.overlap import OverlapResult

    assert dataclasses.is_dataclass(OverlapResult)
    field_names = {f.name for f in dataclasses.fields(OverlapResult)}
    assert field_names == {
        "per_label",
        "mean_dice",
        "volume_weighted_dice",
        "mean_jaccard",
        "n_matched",
        "n_unmatched",
    }
    params = OverlapResult.__dataclass_params__
    assert params.frozen is True


def test_ac1_compute_overlap_default_spacing():
    """AC1: compute_overlap accepts (candidate, gt) with a default spacing."""
    from segqc.eval.overlap import compute_overlap

    arr = _range_1d(4, {1: (0, 4)})
    result = compute_overlap(arr, arr)
    assert result.n_matched == 1


# =========================================================================== #
# AC2: identical maps -> DICE 1.0 per label
# =========================================================================== #


def test_ac2_identical_maps_all_dice_one():
    """AC2: candidate == gt with two labels -> every entry has dice == jaccard == 1.0."""
    from segqc.eval.overlap import compute_overlap

    arr = _range_1d(10, {1: (0, 4), 2: (4, 10)})
    result = compute_overlap(arr, arr)
    assert len(result.per_label) == 2
    for entry in result.per_label:
        assert entry.matched is True
        assert entry.dice == 1.0
        assert entry.jaccard == 1.0
        assert entry.intersection_voxels == entry.candidate_voxels == entry.gt_voxels


def test_ac2_identical_maps_aggregates_one():
    """AC2: identical maps -> mean_dice, mean_jaccard, volume_weighted_dice all 1.0."""
    from segqc.eval.overlap import compute_overlap

    arr = _range_1d(10, {1: (0, 4), 2: (4, 10)})
    result = compute_overlap(arr, arr)
    assert result.mean_dice == 1.0
    assert result.mean_jaccard == 1.0
    assert result.volume_weighted_dice == 1.0


# =========================================================================== #
# AC3: disjoint masks -> DICE 0.0
# =========================================================================== #


def test_ac3_disjoint_same_label_dice_zero():
    """AC3: a label present in both maps but on disjoint voxels -> dice == jaccard == 0.0."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(10, {1: (0, 4)})
    gt = _range_1d(10, {1: (6, 10)})
    result = compute_overlap(candidate, gt)
    assert len(result.per_label) == 1
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.intersection_voxels == 0
    assert entry.dice == 0.0
    assert entry.jaccard == 0.0
    assert result.mean_dice == 0.0


# =========================================================================== #
# AC4: half-overlap matches the hand-computed DICE/Jaccard
# =========================================================================== #


def test_ac4_partial_overlap_hand_computed():
    """AC4: a=10, b=8, i=4 -> dice == 2*4/18, jaccard == 4/(18-4)."""
    from segqc.eval.overlap import compute_overlap

    # candidate label 1 occupies [0:10) (a=10); gt label 1 occupies [6:14) (b=8);
    # intersection is [6:10) -> i=4.
    candidate = _range_1d(20, {1: (0, 10)})
    gt = _range_1d(20, {1: (6, 14)})
    result = compute_overlap(candidate, gt)
    entry = result.per_label[0]
    assert entry.candidate_voxels == 10
    assert entry.gt_voxels == 8
    assert entry.intersection_voxels == 4
    assert entry.dice == pytest.approx(2 * 4 / 18)
    assert entry.jaccard == pytest.approx(4 / (18 - 4))


# =========================================================================== #
# AC5: unmatched labels are reported, not errors
# =========================================================================== #


def test_ac5_candidate_only_label_is_unmatched():
    """AC5: a label present only in candidate is unmatched with dice/jaccard 0 and gt_voxels 0."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(10, {1: (0, 4)})
    gt = _range_1d(10, {})
    result = compute_overlap(candidate, gt)
    assert len(result.per_label) == 1
    entry = result.per_label[0]
    assert entry.matched is False
    assert entry.dice == 0.0
    assert entry.jaccard == 0.0
    assert entry.gt_voxels == 0
    assert entry.candidate_voxels == 4


def test_ac5_gt_only_label_is_unmatched():
    """AC5: a label present only in gt is unmatched with dice/jaccard 0 and candidate_voxels 0."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(10, {})
    gt = _range_1d(10, {2: (0, 5)})
    result = compute_overlap(candidate, gt)
    assert len(result.per_label) == 1
    entry = result.per_label[0]
    assert entry.matched is False
    assert entry.dice == 0.0
    assert entry.jaccard == 0.0
    assert entry.candidate_voxels == 0
    assert entry.gt_voxels == 5


def test_ac5_no_exception_raised():
    """AC5: unmatched labels never raise."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(10, {1: (0, 4)})
    gt = _range_1d(10, {2: (5, 9)})
    compute_overlap(candidate, gt)  # must not raise


def test_ac5_unmatched_excluded_from_aggregates_and_counted():
    """AC5: unmatched entries are excluded from aggregates and counted in n_unmatched."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(10, {1: (0, 4)})
    gt = _range_1d(10, {2: (5, 9)})
    result = compute_overlap(candidate, gt)
    assert result.n_matched == 0
    assert result.n_unmatched == 2
    assert result.mean_dice is None
    assert result.mean_jaccard is None
    assert result.volume_weighted_dice is None


# =========================================================================== #
# AC6: unweighted aggregates are the mean over matched labels only
# =========================================================================== #


def test_ac6_mean_over_matched_only():
    """AC6: mean_dice/mean_jaccard equal the hand mean over matched labels only."""
    from segqc.eval.overlap import compute_overlap

    # Label 1: matched, full overlap -> dice 1.0, jaccard 1.0.
    # Label 2: matched, disjoint -> dice 0.0, jaccard 0.0.
    # Label 3: candidate-only -> unmatched, excluded.
    candidate = _array(
        (40,),
        {1: [(i,) for i in range(0, 4)], 2: [(i,) for i in range(10, 14)], 3: [(i,) for i in range(20, 24)]},
    )
    gt = _array(
        (40,),
        {1: [(i,) for i in range(0, 4)], 2: [(i,) for i in range(16, 20)]},
    )
    result = compute_overlap(candidate, gt)
    assert result.n_matched == 2
    assert result.n_unmatched == 1
    matched = [e for e in result.per_label if e.matched]
    assert result.mean_dice == pytest.approx(sum(e.dice for e in matched) / 2)
    assert result.mean_jaccard == pytest.approx(sum(e.jaccard for e in matched) / 2)
    assert result.mean_dice == pytest.approx((1.0 + 0.0) / 2)


# =========================================================================== #
# AC7: volume-weighted aggregate uses GT physical volume
# =========================================================================== #


def test_ac7_physical_volume_uses_gt_voxels_and_spacing():
    """AC7: physical_volume_mm3 == gt_voxels * sx * sy * sz for every entry."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10), 2: (10, 12)})
    gt = _range_1d(20, {1: (0, 8), 2: (10, 14)})
    spacing = (0.5, 2.0, 1.5)
    result = compute_overlap(candidate, gt, spacing=spacing)
    sx, sy, sz = spacing
    for entry in result.per_label:
        assert entry.physical_volume_mm3 == pytest.approx(
            entry.gt_voxels * sx * sy * sz
        )


def test_ac7_volume_weighted_dice_hand_computed_and_differs_from_mean():
    """AC7: volume_weighted_dice equals the hand weighted mean and differs from mean_dice."""
    from segqc.eval.overlap import compute_overlap

    # Label 1: full overlap -> dice 1.0, gt volume 2 voxels (small).
    # Label 2: partial overlap -> dice < 1.0, gt volume 20 voxels (large).
    candidate = _array(
        (60,),
        {1: [(i,) for i in range(0, 2)], 2: [(i,) for i in range(10, 30)]},
    )
    gt = _array(
        (60,),
        {1: [(i,) for i in range(0, 2)], 2: [(i,) for i in range(20, 40)]},
    )
    spacing = (1.0, 1.0, 1.0)
    result = compute_overlap(candidate, gt, spacing=spacing)
    matched = {e.value: e for e in result.per_label if e.matched}
    assert set(matched) == {1, 2}
    total_weight = sum(e.physical_volume_mm3 for e in matched.values())
    expected = sum(e.dice * e.physical_volume_mm3 for e in matched.values()) / total_weight
    assert result.volume_weighted_dice == pytest.approx(expected)
    unweighted_mean = sum(e.dice for e in matched.values()) / len(matched)
    assert matched[1].dice != matched[2].dice  # sanity: differing DICE
    assert result.volume_weighted_dice != pytest.approx(unweighted_mean)


# =========================================================================== #
# AC8: per-label DICE/Jaccard are spacing-invariant
# =========================================================================== #


def test_ac8_dice_jaccard_identical_across_spacing():
    """AC8: per-label dice/jaccard and mean aggregates are identical across spacings."""
    from segqc.eval.overlap import compute_overlap

    candidate = _array(
        (40,),
        {1: [(i,) for i in range(0, 10)], 2: [(i,) for i in range(15, 20)]},
    )
    gt = _array(
        (40,),
        {1: [(i,) for i in range(4, 14)], 2: [(i,) for i in range(15, 25)]},
    )
    iso = compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0))
    aniso = compute_overlap(candidate, gt, spacing=(0.5, 1.0, 3.0))

    assert iso.mean_dice == pytest.approx(aniso.mean_dice)
    assert iso.mean_jaccard == pytest.approx(aniso.mean_jaccard)
    for e_iso, e_aniso in zip(iso.per_label, aniso.per_label):
        assert e_iso.value == e_aniso.value
        assert e_iso.dice == pytest.approx(e_aniso.dice)
        assert e_iso.jaccard == pytest.approx(e_aniso.jaccard)


def test_ac8_physical_volume_scales_with_spacing():
    """AC8: physical_volume_mm3 reflects spacing while dice/jaccard do not."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10)})
    gt = _range_1d(20, {1: (0, 8)})
    iso = compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0))
    aniso = compute_overlap(candidate, gt, spacing=(0.5, 1.0, 3.0))
    assert iso.per_label[0].physical_volume_mm3 == pytest.approx(8.0)
    assert aniso.per_label[0].physical_volume_mm3 == pytest.approx(8.0 * 0.5 * 1.0 * 3.0)
    assert iso.per_label[0].dice == pytest.approx(aniso.per_label[0].dice)


# =========================================================================== #
# AC9: empty inputs yield a well-formed empty result
# =========================================================================== #


def test_ac9_all_zero_inputs_empty_result():
    """AC9: two all-background arrays yield an empty per_label, zero counts, None aggregates."""
    from segqc.eval.overlap import compute_overlap

    candidate = np.zeros((10,), dtype=np.int64)
    gt = np.zeros((10,), dtype=np.int64)
    result = compute_overlap(candidate, gt)
    assert result.per_label == ()
    assert result.n_matched == 0
    assert result.n_unmatched == 0
    assert result.mean_dice is None
    assert result.mean_jaccard is None
    assert result.volume_weighted_dice is None


# =========================================================================== #
# AC10: labels are named and ordered via the Stage-0 convention
# =========================================================================== #


def test_ac10_names_match_default_convention():
    """AC10: LabelOverlap.name equals convention.name_of(value) for L1 and L3."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {20: (0, 4), 22: (10, 14)})
    gt = _range_1d(20, {20: (0, 4), 22: (10, 14)})
    result = compute_overlap(candidate, gt)
    by_value = {e.value: e for e in result.per_label}
    assert by_value[20].name == "L1"
    assert by_value[22].name == "L3"


def test_ac10_per_label_ordered_canonically_then_by_value():
    """AC10: per_label is ordered by CANONICAL_ORDER for recognised, then value for unrecognised."""
    from segqc.eval.overlap import compute_overlap

    # Values inserted out of canonical order: L3(22), C1(1), unmapped(500), T1(8).
    label_map = {22: (0, 2), 1: (2, 4), 500: (4, 6), 8: (6, 8)}
    candidate = _range_1d(20, label_map)
    gt = _range_1d(20, label_map)
    result = compute_overlap(candidate, gt)
    names_in_order = [e.name for e in result.per_label]
    # Recognised labels: C1, T1, L3 in that canonical order; unmapped(500) last.
    expected_recognised = ["C1", "T1", "L3"]
    recognised_names = [n for n in names_in_order if n != UNKNOWN]
    assert recognised_names == expected_recognised
    assert names_in_order[-1] == UNKNOWN


# =========================================================================== #
# AC11: unmapped labels match by value and are not collapsed
# =========================================================================== #


def test_ac11_two_unmapped_labels_stay_separate():
    """AC11: two distinct unmapped labels produce two separate UNKNOWN-named entries."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {900: (0, 4), 901: (10, 18)})
    gt = _range_1d(20, {900: (0, 4), 901: (10, 14)})
    result = compute_overlap(candidate, gt)
    assert len(result.per_label) == 2
    by_value = {e.value: e for e in result.per_label}
    assert set(by_value) == {900, 901}
    for entry in by_value.values():
        assert entry.name == UNKNOWN
    # Independent DICE: label 900 is a full match, label 901 is partial.
    assert by_value[900].dice == 1.0
    assert by_value[901].dice != 1.0


# =========================================================================== #
# AC12: mismatched array shapes raise SegQCInputError
# =========================================================================== #


def test_ac12_mismatched_shapes_raise_segqc_input_error():
    """AC12: candidate/gt of different shape raise SegQCInputError."""
    from segqc.eval.overlap import compute_overlap

    candidate = np.zeros((10,), dtype=np.int64)
    gt = np.zeros((12,), dtype=np.int64)
    with pytest.raises(SegQCInputError):
        compute_overlap(candidate, gt)


def test_ac12_mismatched_shapes_not_raw_value_error():
    """AC12: the shape mismatch is a SegQCInputError, not a bare numpy ValueError."""
    from segqc.eval.overlap import compute_overlap

    candidate = np.zeros((4, 4), dtype=np.int64)
    gt = np.zeros((4, 5), dtype=np.int64)
    try:
        compute_overlap(candidate, gt)
    except SegQCInputError:
        pass
    else:
        pytest.fail("expected SegQCInputError")


# =========================================================================== #
# AC13: pure, deterministic, and non-mutating
# =========================================================================== #


def test_ac13_deterministic_across_two_calls():
    """AC13: two calls on the same inputs return equal per_label ordering and aggregates."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10), 900: (12, 16)})
    gt = _range_1d(20, {1: (4, 14), 900: (12, 15)})
    r1 = compute_overlap(candidate, gt)
    r2 = compute_overlap(candidate, gt)
    assert len(r1.per_label) == len(r2.per_label)
    for e1, e2 in zip(r1.per_label, r2.per_label):
        assert e1 == e2
    assert r1.mean_dice == r2.mean_dice
    assert r1.mean_jaccard == r2.mean_jaccard
    assert r1.volume_weighted_dice == r2.volume_weighted_dice
    assert r1.n_matched == r2.n_matched
    assert r1.n_unmatched == r2.n_unmatched


def test_ac13_inputs_not_mutated():
    """AC13: candidate and gt arrays are byte-for-byte unchanged after the call."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10), 900: (12, 16)})
    gt = _range_1d(20, {1: (4, 14), 900: (12, 15)})
    candidate_before = candidate.copy()
    gt_before = gt.copy()
    compute_overlap(candidate, gt)
    np.testing.assert_array_equal(candidate, candidate_before)
    np.testing.assert_array_equal(gt, gt_before)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_single_voxel_label_matched():
    """A single-voxel matched label has candidate_voxels == gt_voxels == 1, dice == 1.0."""
    from segqc.eval.overlap import compute_overlap

    candidate = _array((10,), {5: [(3,)]})
    gt = _array((10,), {5: [(3,)]})
    result = compute_overlap(candidate, gt)
    entry = result.per_label[0]
    assert entry.candidate_voxels == 1
    assert entry.gt_voxels == 1
    assert entry.dice == 1.0


def test_adv_asymmetric_containment_dice_less_than_one():
    """A label fully contained in the other (asymmetric sizes) yields DICE < 1."""
    from segqc.eval.overlap import compute_overlap

    # candidate label occupies [0:2) fully inside gt's [0:10).
    candidate = _range_1d(20, {1: (0, 2)})
    gt = _range_1d(20, {1: (0, 10)})
    result = compute_overlap(candidate, gt)
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.intersection_voxels == 2
    assert entry.candidate_voxels == 2
    assert entry.gt_voxels == 10
    expected_dice = 2 * 2 / (2 + 10)
    assert entry.dice == pytest.approx(expected_dice)
    assert entry.dice < 1.0


def test_adv_matched_label_zero_intersection_nonzero_both_sides():
    """A label present (non-zero voxels) in both maps but zero intersection is matched, DICE 0."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {7: (0, 3)})
    gt = _range_1d(20, {7: (10, 15)})
    result = compute_overlap(candidate, gt)
    entry = result.per_label[0]
    assert entry.matched is True
    assert entry.candidate_voxels == 3
    assert entry.gt_voxels == 5
    assert entry.intersection_voxels == 0
    assert entry.dice == 0.0
    assert entry.jaccard == 0.0


def test_adv_negative_and_large_unmapped_label_still_computed():
    """A negative or very large unmapped integer label is named UNKNOWN and still computed."""
    from segqc.eval.overlap import compute_overlap

    candidate = np.zeros((10,), dtype=np.int64)
    gt = np.zeros((10,), dtype=np.int64)
    candidate[0:3] = -7
    gt[0:3] = -7
    candidate[5:8] = 10_000_000
    gt[5:8] = 10_000_000
    result = compute_overlap(candidate, gt)
    by_value = {e.value: e for e in result.per_label}
    assert set(by_value) == {-7, 10_000_000}
    for entry in by_value.values():
        assert entry.name == UNKNOWN
        assert entry.matched is True
        assert entry.dice == 1.0


def test_adv_zero_spacing_component_zeroes_physical_volume_but_not_dice():
    """A zero spacing component zeroes physical_volume_mm3 while per-label dice is unaffected."""
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10)})
    gt = _range_1d(20, {1: (0, 8)})
    result = compute_overlap(candidate, gt, spacing=(0.0, 1.0, 1.0))
    entry = result.per_label[0]
    assert entry.physical_volume_mm3 == 0.0
    assert entry.dice == pytest.approx(2 * 8 / (10 + 8))


def test_adv_all_weights_zero_volume_weighted_dice_is_none():
    """When every matched label's GT voxel count is nonzero but spacing collapses volume to zero,
    volume_weighted_dice still computes (weight 0 for every matched entry -> falls back to None).
    """
    from segqc.eval.overlap import compute_overlap

    candidate = _range_1d(20, {1: (0, 10), 2: (10, 15)})
    gt = _range_1d(20, {1: (0, 8), 2: (10, 14)})
    result = compute_overlap(candidate, gt, spacing=(0.0, 1.0, 1.0))
    assert result.n_matched == 2
    assert result.volume_weighted_dice is None


def test_adv_custom_convention_overrides_naming():
    """A caller-supplied convention names labels instead of the default."""
    from segqc.eval.overlap import compute_overlap

    custom = LabelConvention.from_mapping({42: "Custom"})
    candidate = _range_1d(10, {42: (0, 4)})
    gt = _range_1d(10, {42: (0, 4)})
    result = compute_overlap(candidate, gt, convention=custom)
    assert result.per_label[0].name == "Custom"


def test_adv_3d_shape_supported():
    """compute_overlap works on 3-D arrays, not just 1-D."""
    from segqc.eval.overlap import compute_overlap

    candidate = np.zeros((4, 4, 4), dtype=np.int64)
    gt = np.zeros((4, 4, 4), dtype=np.int64)
    candidate[0:2, 0:2, 0:2] = 3
    gt[0:2, 0:2, 0:2] = 3
    result = compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0))
    assert result.per_label[0].dice == 1.0
    assert result.per_label[0].candidate_voxels == 8
