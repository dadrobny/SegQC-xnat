"""Tests for overlap detection between labels (item 015).

Covers all four Acceptance Criteria plus adversarial and edge-case inputs:
a deliberately overlapping pair yields the correct pair and count, a
non-overlapping fixture yields an empty result, multiple partial overlaps with
distinct counts are each reported correctly, and results are deterministic.

Additional adversarial cases: zero labels (no pairs possible), one label (no
pairs possible), three-way overlap (voxel shared by all three labels), partial
three-label overlap (two pairs each with a different voxel set), single-voxel
overlap, all-voxels overlap, label-ordering invariant (pair always reported with
lower label first), immutability (input arrays not mutated), anatomical-name
resolution for mapped and unmapped labels, and UNKNOWN fallback.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import numpy as np
import pytest

from segqc.features.overlap import OverlapPair, detect_overlaps
from segqc.labels import UNKNOWN


# =========================================================================== #
# Helpers
# =========================================================================== #


def _mask_stack(shape, label_voxels):
    """Build a boolean mask stack and label-integer array from a dict.

    Parameters
    ----------
    shape:
        3-D spatial shape ``(X, Y, Z)``.
    label_voxels:
        ``{label_int: list_of_(x,y,z)_tuples}`` — each voxel listed belongs
        to that label.  A voxel can appear under multiple labels (overlap).

    Returns
    -------
    mask_stack : ndarray, shape ``(n_labels, X, Y, Z)``, dtype bool
    labels : ndarray, shape ``(n_labels,)``, dtype int
    """
    label_list = sorted(label_voxels.keys())
    n = len(label_list)
    stack = np.zeros((n,) + tuple(shape), dtype=bool)
    for ch, lbl in enumerate(label_list):
        for x, y, z in label_voxels[lbl]:
            stack[ch, x, y, z] = True
    return stack, np.array(label_list, dtype=np.int64)


def _block_voxels(x0, x1, y0, y1, z0, z1):
    """Return a list of (x, y, z) tuples for a half-open block."""
    return [
        (x, y, z)
        for x in range(x0, x1)
        for y in range(y0, y1)
        for z in range(z0, z1)
    ]


def _pairs_by_labels(results, a, b):
    """Return the OverlapPair(s) whose (label_a, label_b) == (min,max)(a, b)."""
    lo, hi = min(a, b), max(a, b)
    return [r for r in results if r.label_a == lo and r.label_b == hi]


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_overlap_pair():
    """OverlapPair is importable from segqc.features.overlap."""
    from segqc.features.overlap import OverlapPair as OP  # noqa: F401
    assert OP is OverlapPair


def test_import_detect_overlaps():
    """detect_overlaps is importable from segqc.features.overlap."""
    from segqc.features.overlap import detect_overlaps as do  # noqa: F401
    assert callable(do)


def test_no_import_error():
    """Importing segqc.features.overlap raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.overlap")
    assert hasattr(mod, "OverlapPair")
    assert hasattr(mod, "detect_overlaps")


# =========================================================================== #
# AC1: A fixture with a deliberately overlapping pair yields correct pair + count
# =========================================================================== #


def test_ac1_overlapping_pair_is_reported():
    """AC1: An overlapping pair (labels 1 and 2) appears in the result list."""
    # Labels 1 and 2 each occupy the same 4-voxel block — total overlap = 4.
    shared = _block_voxels(0, 2, 0, 2, 0, 1)  # 4 voxels
    stack, labels = _mask_stack(
        (4, 4, 4),
        {1: shared, 2: shared},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert len(pairs) == 1, "Expected exactly one OverlapPair for labels 1 and 2"


def test_ac1_overlapping_pair_count_correct():
    """AC1: The overlap voxel count for the shared pair equals the number of shared voxels."""
    shared = _block_voxels(0, 2, 0, 2, 0, 1)  # 4 voxels
    stack, labels = _mask_stack(
        (4, 4, 4),
        {1: shared, 2: shared},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert pairs[0].overlap_voxels == 4


def test_ac1_overlapping_pair_returns_overlap_pair_instances():
    """AC1: detect_overlaps returns a sequence of OverlapPair instances."""
    shared = _block_voxels(1, 3, 1, 3, 1, 2)
    stack, labels = _mask_stack(
        (6, 6, 6),
        {1: shared, 2: shared},
    )
    result = detect_overlaps(stack, labels)
    assert len(result) >= 1
    for item in result:
        assert isinstance(item, OverlapPair)


def test_ac1_overlapping_pair_label_fields_set():
    """AC1: OverlapPair.label_a and label_b are set to the correct label integers."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack(
        (4, 4, 4),
        {3: shared, 7: shared},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 3, 7)
    assert len(pairs) == 1
    assert pairs[0].label_a == 3
    assert pairs[0].label_b == 7


def test_ac1_partial_overlap_one_pair_8_voxels():
    """AC1: A partial 8-voxel overlap between two labels is reported with count 8."""
    # Label 1 owns voxels [0:4] on x, label 2 owns voxels [2:6] — overlap at x [2:4].
    label1 = _block_voxels(0, 4, 0, 2, 0, 2)   # 4*2*2 = 16 voxels
    label2 = _block_voxels(2, 6, 0, 2, 0, 2)   # 4*2*2 = 16 voxels
    # Shared: x[2:4], y[0:2], z[0:2] = 2*2*2 = 8 voxels
    stack, labels = _mask_stack(
        (8, 4, 4),
        {1: label1, 2: label2},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert len(pairs) == 1
    assert pairs[0].overlap_voxels == 8


def test_ac1_result_is_sequence():
    """AC1: detect_overlaps returns a list or sequence (not None, not a dict)."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    assert hasattr(result, "__iter__")
    assert hasattr(result, "__len__")


# =========================================================================== #
# AC2: A non-overlapping fixture yields an empty result
# =========================================================================== #


def test_ac2_non_overlapping_two_labels_empty():
    """AC2: Two completely non-overlapping labels yield an empty result."""
    label1 = _block_voxels(0, 4, 0, 4, 0, 4)   # first octant
    label2 = _block_voxels(4, 8, 4, 8, 4, 8)   # last octant (disjoint)
    stack, labels = _mask_stack(
        (8, 8, 8),
        {1: label1, 2: label2},
    )
    result = detect_overlaps(stack, labels)
    assert list(result) == []


def test_ac2_non_overlapping_three_labels_empty():
    """AC2: Three mutually non-overlapping labels yield an empty result."""
    stack, labels = _mask_stack(
        (12, 4, 4),
        {
            1: _block_voxels(0, 4, 0, 4, 0, 4),
            2: _block_voxels(4, 8, 0, 4, 0, 4),
            3: _block_voxels(8, 12, 0, 4, 0, 4),
        },
    )
    result = detect_overlaps(stack, labels)
    assert list(result) == []


def test_ac2_single_label_no_pairs():
    """AC2: A single label has no pair to overlap with — result is empty."""
    stack, labels = _mask_stack(
        (4, 4, 4),
        {1: _block_voxels(0, 4, 0, 4, 0, 4)},
    )
    result = detect_overlaps(stack, labels)
    assert list(result) == []


def test_ac2_zero_labels_empty():
    """AC2: An empty mask stack (no labels) yields an empty result."""
    stack = np.zeros((0, 4, 4, 4), dtype=bool)
    labels = np.array([], dtype=np.int64)
    result = detect_overlaps(stack, labels)
    assert list(result) == []


def test_ac2_adjacent_but_not_overlapping_labels_empty():
    """AC2: Two face-adjacent non-overlapping labels yield an empty result."""
    # Label 1: x[0:4]; Label 2: x[4:8] — touching face but no shared voxel.
    stack, labels = _mask_stack(
        (8, 4, 4),
        {
            1: _block_voxels(0, 4, 0, 4, 0, 4),
            2: _block_voxels(4, 8, 0, 4, 0, 4),
        },
    )
    result = detect_overlaps(stack, labels)
    assert list(result) == []


# =========================================================================== #
# AC3: Partial overlaps at different counts are each correctly reported
# =========================================================================== #


def test_ac3_two_pairs_different_overlap_counts():
    """AC3: Two overlapping pairs with 10 and 3 shared voxels are both reported correctly."""
    # Pair (1, 2): share 10 voxels in x[0:10], y[0:1], z[0:1]
    pair12_shared = _block_voxels(0, 10, 0, 1, 0, 1)   # 10 voxels
    # Pair (1, 3): share 3 voxels in x[11:14], y[0:1], z[0:1]
    pair13_shared = _block_voxels(11, 14, 0, 1, 0, 1)  # 3 voxels
    # label1 owns both shared sets
    # label2 owns pair12_shared only
    # label3 owns pair13_shared only
    stack, labels = _mask_stack(
        (16, 4, 4),
        {
            1: pair12_shared + pair13_shared,
            2: pair12_shared,
            3: pair13_shared,
        },
    )
    result = detect_overlaps(stack, labels)
    pairs_12 = _pairs_by_labels(result, 1, 2)
    pairs_13 = _pairs_by_labels(result, 1, 3)
    assert len(pairs_12) == 1, "Expected one OverlapPair for labels 1 and 2"
    assert len(pairs_13) == 1, "Expected one OverlapPair for labels 1 and 3"
    assert pairs_12[0].overlap_voxels == 10
    assert pairs_13[0].overlap_voxels == 3


def test_ac3_three_pairwise_overlaps_all_reported():
    """AC3: Three pairwise-overlapping labels each pair has its own distinct count."""
    # Three labels each pair sharing a distinct block:
    # (1,2) share 6 voxels: x[0:6], y[0:1], z[0:1]
    # (1,3) share 4 voxels: x[6:10], y[0:1], z[0:1]
    # (2,3) share 2 voxels: x[10:12], y[0:1], z[0:1]
    b12 = _block_voxels(0, 6, 0, 1, 0, 1)    # 6 voxels
    b13 = _block_voxels(6, 10, 0, 1, 0, 1)   # 4 voxels
    b23 = _block_voxels(10, 12, 0, 1, 0, 1)  # 2 voxels
    stack, labels = _mask_stack(
        (14, 4, 4),
        {
            1: b12 + b13,
            2: b12 + b23,
            3: b13 + b23,
        },
    )
    result = detect_overlaps(stack, labels)
    pairs_12 = _pairs_by_labels(result, 1, 2)
    pairs_13 = _pairs_by_labels(result, 1, 3)
    pairs_23 = _pairs_by_labels(result, 2, 3)
    assert len(pairs_12) == 1
    assert len(pairs_13) == 1
    assert len(pairs_23) == 1
    assert pairs_12[0].overlap_voxels == 6
    assert pairs_13[0].overlap_voxels == 4
    assert pairs_23[0].overlap_voxels == 2


def test_ac3_no_cross_contamination_between_pairs():
    """AC3: The voxel count for each pair is independent; counts do not bleed across pairs."""
    b12 = _block_voxels(0, 5, 0, 1, 0, 1)   # 5 voxels
    b13 = _block_voxels(5, 8, 0, 1, 0, 1)   # 3 voxels
    stack, labels = _mask_stack(
        (10, 4, 4),
        {
            1: b12 + b13,
            2: b12,
            3: b13,
        },
    )
    result = detect_overlaps(stack, labels)
    pairs_12 = _pairs_by_labels(result, 1, 2)
    pairs_13 = _pairs_by_labels(result, 1, 3)
    assert pairs_12[0].overlap_voxels == 5
    assert pairs_13[0].overlap_voxels == 3


# =========================================================================== #
# AC4: Results are deterministic
# =========================================================================== #


def test_ac4_determinism_same_result_twice():
    """AC4: Two calls with the same input return identical results."""
    shared = _block_voxels(0, 3, 0, 3, 0, 3)
    stack, labels = _mask_stack((6, 6, 6), {1: shared, 2: shared})
    r1 = detect_overlaps(stack, labels)
    r2 = detect_overlaps(stack, labels)
    assert len(r1) == len(r2)
    for a, b in zip(
        sorted(r1, key=lambda p: (p.label_a, p.label_b)),
        sorted(r2, key=lambda p: (p.label_a, p.label_b)),
    ):
        assert a.label_a == b.label_a
        assert a.label_b == b.label_b
        assert a.overlap_voxels == b.overlap_voxels


def test_ac4_determinism_non_overlapping():
    """AC4: Two calls on non-overlapping input both return empty."""
    stack, labels = _mask_stack(
        (8, 4, 4),
        {1: _block_voxels(0, 4, 0, 4, 0, 4), 2: _block_voxels(4, 8, 0, 4, 0, 4)},
    )
    r1 = detect_overlaps(stack, labels)
    r2 = detect_overlaps(stack, labels)
    assert list(r1) == list(r2)


def test_ac4_determinism_multiple_pairs():
    """AC4: Multiple overlapping pairs yield stable results across two calls."""
    b12 = _block_voxels(0, 4, 0, 1, 0, 1)
    b13 = _block_voxels(4, 7, 0, 1, 0, 1)
    stack, labels = _mask_stack(
        (8, 4, 4),
        {1: b12 + b13, 2: b12, 3: b13},
    )
    r1 = detect_overlaps(stack, labels)
    r2 = detect_overlaps(stack, labels)
    sort_key = lambda p: (p.label_a, p.label_b)  # noqa: E731
    for a, b in zip(sorted(r1, key=sort_key), sorted(r2, key=sort_key)):
        assert a.label_a == b.label_a
        assert a.label_b == b.label_b
        assert a.overlap_voxels == b.overlap_voxels


# =========================================================================== #
# Adversarial: three-way overlap (single voxel owned by all three labels)
# =========================================================================== #


def test_adv_three_way_overlap_all_pairs_reported():
    """Three labels sharing one voxel: all three pairs (1,2), (1,3), (2,3) are reported."""
    shared = [(2, 2, 2)]
    stack, labels = _mask_stack(
        (6, 6, 6),
        {1: shared, 2: shared, 3: shared},
    )
    result = detect_overlaps(stack, labels)
    # All three label pairs must appear
    pairs_12 = _pairs_by_labels(result, 1, 2)
    pairs_13 = _pairs_by_labels(result, 1, 3)
    pairs_23 = _pairs_by_labels(result, 2, 3)
    assert len(pairs_12) == 1
    assert len(pairs_13) == 1
    assert len(pairs_23) == 1


def test_adv_three_way_overlap_each_pair_count_is_one():
    """Three labels sharing exactly one voxel: every pairwise count is 1."""
    shared = [(2, 2, 2)]
    stack, labels = _mask_stack(
        (6, 6, 6),
        {1: shared, 2: shared, 3: shared},
    )
    result = detect_overlaps(stack, labels)
    for pair in result:
        assert pair.overlap_voxels == 1


# =========================================================================== #
# Adversarial: single-voxel overlap
# =========================================================================== #


def test_adv_single_voxel_overlap_count_is_one():
    """Exactly one shared voxel between two labels produces overlap_voxels == 1."""
    stack, labels = _mask_stack(
        (4, 4, 4),
        {1: [(1, 1, 1)], 2: [(1, 1, 1)]},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert len(pairs) == 1
    assert pairs[0].overlap_voxels == 1


def test_adv_single_voxel_overlap_other_voxels_not_counted():
    """Only the single shared voxel is counted; extra exclusive voxels are not."""
    # label1 has 5 voxels, label2 has 5 voxels, only 1 is shared
    exclusive1 = _block_voxels(0, 4, 0, 1, 0, 1)   # 4 voxels
    exclusive2 = _block_voxels(0, 4, 2, 3, 0, 1)   # 4 voxels
    shared = [(0, 5, 0)]
    stack, labels = _mask_stack(
        (6, 6, 6),
        {1: exclusive1 + shared, 2: exclusive2 + shared},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert len(pairs) == 1
    assert pairs[0].overlap_voxels == 1


# =========================================================================== #
# Adversarial: all voxels overlap
# =========================================================================== #


def test_adv_all_voxels_overlap_count_equals_volume():
    """When two labels share every voxel, overlap_voxels equals the total volume."""
    all_voxels = _block_voxels(0, 4, 0, 4, 0, 4)  # 64 voxels
    stack, labels = _mask_stack(
        (4, 4, 4),
        {1: all_voxels, 2: all_voxels},
    )
    result = detect_overlaps(stack, labels)
    pairs = _pairs_by_labels(result, 1, 2)
    assert len(pairs) == 1
    assert pairs[0].overlap_voxels == 64


# =========================================================================== #
# Adversarial: label ordering invariant (label_a < label_b always)
# =========================================================================== #


def test_adv_pair_lower_label_is_label_a():
    """OverlapPair always has label_a < label_b regardless of input order."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    # Deliberately put higher label first in the dict
    stack, labels = _mask_stack(
        (4, 4, 4),
        {9: shared, 2: shared},
    )
    result = detect_overlaps(stack, labels)
    assert len(result) == 1
    assert result[0].label_a < result[0].label_b
    assert result[0].label_a == 2
    assert result[0].label_b == 9


def test_adv_pair_ordering_invariant_for_all_pairs():
    """All OverlapPair records satisfy label_a < label_b."""
    b12 = _block_voxels(0, 3, 0, 1, 0, 1)
    b23 = _block_voxels(3, 6, 0, 1, 0, 1)
    stack, labels = _mask_stack(
        (8, 4, 4),
        {5: b12 + b23, 1: b12, 3: b23},
    )
    result = detect_overlaps(stack, labels)
    for pair in result:
        assert pair.label_a < pair.label_b, (
            f"label_a={pair.label_a} is not < label_b={pair.label_b}"
        )


# =========================================================================== #
# Adversarial: immutability (input arrays not mutated)
# =========================================================================== #


def test_adv_mask_stack_not_mutated():
    """detect_overlaps does not mutate the input mask stack."""
    shared = _block_voxels(0, 3, 0, 3, 0, 3)
    stack, labels = _mask_stack((6, 6, 6), {1: shared, 2: shared})
    original_stack = stack.copy()
    detect_overlaps(stack, labels)
    np.testing.assert_array_equal(stack, original_stack)


def test_adv_labels_array_not_mutated():
    """detect_overlaps does not mutate the input labels array."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 2: shared})
    original_labels = labels.copy()
    detect_overlaps(stack, labels)
    np.testing.assert_array_equal(labels, original_labels)


# =========================================================================== #
# Adversarial: anatomical-name fields on OverlapPair
# =========================================================================== #


def test_adv_overlap_pair_has_required_fields():
    """OverlapPair exposes label_a, label_b, name_a, name_b, overlap_voxels."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    assert len(result) >= 1
    pair = result[0]
    for field in ("label_a", "label_b", "name_a", "name_b", "overlap_voxels"):
        assert hasattr(pair, field), f"OverlapPair missing field: {field}"


def test_adv_name_fields_are_strings():
    """name_a and name_b are non-empty strings."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    pair = result[0]
    assert isinstance(pair.name_a, str)
    assert isinstance(pair.name_b, str)
    assert pair.name_a.strip() != ""
    assert pair.name_b.strip() != ""


def test_adv_mapped_labels_have_canonical_names():
    """Labels 1 and 2 resolve to 'C1' and 'C2' in the default convention."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    pair = result[0]
    assert pair.label_a == 1
    assert pair.label_b == 2
    assert pair.name_a == "C1"
    assert pair.name_b == "C2"


def test_adv_unmapped_labels_yield_unknown():
    """Labels with no canonical mapping fall back to UNKNOWN in name fields."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    # Labels 97 and 98 are not in the default convention.
    stack, labels = _mask_stack((4, 4, 4), {97: shared, 98: shared})
    result = detect_overlaps(stack, labels)
    assert len(result) == 1
    pair = result[0]
    assert pair.name_a == UNKNOWN
    assert pair.name_b == UNKNOWN


def test_adv_mixed_mapped_and_unmapped_labels():
    """One mapped and one unmapped label: mapped gets canonical name, unmapped gets UNKNOWN."""
    shared = _block_voxels(0, 2, 0, 2, 0, 2)
    # Label 1 -> 'C1'; label 99 -> UNKNOWN
    stack, labels = _mask_stack((4, 4, 4), {1: shared, 99: shared})
    result = detect_overlaps(stack, labels)
    assert len(result) == 1
    pair = result[0]
    assert pair.label_a == 1
    assert pair.label_b == 99
    assert pair.name_a == "C1"
    assert pair.name_b == UNKNOWN


# =========================================================================== #
# Adversarial: overlap_voxels field is a positive integer
# =========================================================================== #


def test_adv_overlap_voxels_is_positive_integer():
    """overlap_voxels is a positive integer for a non-trivial overlap."""
    shared = _block_voxels(0, 3, 0, 3, 0, 3)
    stack, labels = _mask_stack((6, 6, 6), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    pair = result[0]
    assert isinstance(pair.overlap_voxels, int)
    assert pair.overlap_voxels > 0


def test_adv_overlap_voxels_non_zero_implies_overlap():
    """Every reported OverlapPair has overlap_voxels > 0 (no spurious zero-count pairs)."""
    b12 = _block_voxels(0, 4, 0, 1, 0, 1)
    b13 = _block_voxels(4, 7, 0, 1, 0, 1)
    stack, labels = _mask_stack(
        (8, 4, 4),
        {1: b12 + b13, 2: b12, 3: b13},
    )
    result = detect_overlaps(stack, labels)
    for pair in result:
        assert pair.overlap_voxels > 0, (
            f"Pair ({pair.label_a}, {pair.label_b}) has zero overlap_voxels"
        )


# =========================================================================== #
# Adversarial: no duplicate pairs in result
# =========================================================================== #


def test_adv_no_duplicate_pairs_in_result():
    """Each (label_a, label_b) combination appears at most once in the result."""
    shared = _block_voxels(0, 4, 0, 4, 0, 4)
    stack, labels = _mask_stack((8, 8, 8), {1: shared, 2: shared})
    result = detect_overlaps(stack, labels)
    seen = set()
    for pair in result:
        key = (pair.label_a, pair.label_b)
        assert key not in seen, f"Duplicate pair {key} in result"
        seen.add(key)


def test_adv_no_duplicate_pairs_multiple_overlaps():
    """With three pairwise overlaps, no pair appears more than once."""
    b12 = _block_voxels(0, 3, 0, 1, 0, 1)
    b13 = _block_voxels(3, 5, 0, 1, 0, 1)
    b23 = _block_voxels(5, 8, 0, 1, 0, 1)
    stack, labels = _mask_stack(
        (10, 4, 4),
        {1: b12 + b13, 2: b12 + b23, 3: b13 + b23},
    )
    result = detect_overlaps(stack, labels)
    seen = set()
    for pair in result:
        key = (pair.label_a, pair.label_b)
        assert key not in seen, f"Duplicate pair {key} in result"
        seen.add(key)
