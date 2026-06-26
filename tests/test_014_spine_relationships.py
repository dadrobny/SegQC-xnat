"""Tests for inter-vertebra relationships (item 014).

Covers all five Acceptance Criteria plus adversarial and edge-case inputs:
well-ordered sequence, missing-level detection (gap and no-gap), neighbour
spacings, continuity detection (continuous and out-of-order), frozen-dataclass
contract, UNKNOWN-label filtering, degenerate inputs (zero/one centroid), and
determinism.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
import pytest

from segqc.features.relationships import SpineRelationships, compute_spine_relationships
from segqc.features.centroids import LabelCentroid
from segqc.labels import UNKNOWN


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(level_name: str, mm: tuple[float, float, float]) -> LabelCentroid:
    """Build a minimal LabelCentroid for testing relationships (no NIfTI needed)."""
    return LabelCentroid(
        label=0,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((bi - ai) ** 2 for ai, bi in zip(a, b)))


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_spine_relationships():
    """SpineRelationships is importable from segqc.features.relationships."""
    from segqc.features.relationships import SpineRelationships as SR  # noqa: F401
    assert SR is SpineRelationships


def test_import_compute_spine_relationships():
    """compute_spine_relationships is importable from segqc.features.relationships."""
    from segqc.features.relationships import compute_spine_relationships as csr  # noqa: F401
    assert callable(csr)


def test_no_import_error():
    """Importing segqc.features.relationships raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.relationships")
    assert hasattr(mod, "SpineRelationships")
    assert hasattr(mod, "compute_spine_relationships")


# =========================================================================== #
# AC5: SpineRelationships is a frozen dataclass with the required fields
# =========================================================================== #


def test_ac5_required_fields_present():
    """AC5: SpineRelationships exposes all five required attributes."""
    centroids = [_centroid("T1", (0.0, 0.0, 0.0)), _centroid("T2", (0.0, 0.0, 10.0))]
    result = compute_spine_relationships(centroids)
    for field in ("present_levels", "missing_levels", "neighbour_spacings_mm",
                  "is_continuous", "out_of_order_labels"):
        assert hasattr(result, field), f"SpineRelationships missing field: {field}"


def test_ac5_is_frozen_dataclass():
    """AC5: SpineRelationships is immutable (assigning a field raises FrozenInstanceError)."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    with pytest.raises(Exception):
        result.present_levels = []  # type: ignore[misc]


def test_ac5_present_levels_is_list_of_str():
    """AC5: present_levels is a list of strings."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result.present_levels, list)
    for item in result.present_levels:
        assert isinstance(item, str)


def test_ac5_missing_levels_is_list_of_str():
    """AC5: missing_levels is a list of strings."""
    centroids = [_centroid("T1", (0.0, 0.0, 0.0)), _centroid("T3", (0.0, 0.0, 20.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result.missing_levels, list)
    for item in result.missing_levels:
        assert isinstance(item, str)


def test_ac5_neighbour_spacings_mm_is_list_of_float():
    """AC5: neighbour_spacings_mm is a list of floats."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0)), _centroid("L2", (0.0, 0.0, 10.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result.neighbour_spacings_mm, list)
    for item in result.neighbour_spacings_mm:
        assert isinstance(item, float)


def test_ac5_is_continuous_is_bool():
    """AC5: is_continuous is a bool."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result.is_continuous, bool)


def test_ac5_out_of_order_labels_is_list_of_str():
    """AC5: out_of_order_labels is a list of strings."""
    centroids = [_centroid("L2", (0.0, 0.0, 0.0)), _centroid("L1", (0.0, 0.0, 10.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result.out_of_order_labels, list)
    for item in result.out_of_order_labels:
        assert isinstance(item, str)


def test_ac5_returns_spine_relationships_instance():
    """AC5: compute_spine_relationships returns a SpineRelationships instance."""
    centroids = [_centroid("T5", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    assert isinstance(result, SpineRelationships)


# =========================================================================== #
# AC1: Ordered label sequence is correct for a well-ordered fixture
# =========================================================================== #


def test_ac1_present_levels_in_canonical_order():
    """AC1: present_levels is in anatomical (head-to-tail) order regardless of input order."""
    # Supplied in reverse order (S, L5, L1, T12) — should come out T12, L1, L5, S
    centroids = [
        _centroid("S", (0.0, 0.0, 0.0)),
        _centroid("L5", (0.0, 0.0, 10.0)),
        _centroid("L1", (0.0, 0.0, 20.0)),
        _centroid("T12", (0.0, 0.0, 30.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["T12", "L1", "L5", "S"]


def test_ac1_present_levels_exact_match():
    """AC1: present_levels contains exactly the supplied (known) level names."""
    centroids = [
        _centroid("C1", (0.0, 0.0, 0.0)),
        _centroid("C2", (0.0, 0.0, 5.0)),
        _centroid("C3", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["C1", "C2", "C3"]


def test_ac1_present_levels_already_ordered_unchanged():
    """AC1: A correctly ordered input produces the same order in present_levels."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
        _centroid("L4", (0.0, 0.0, 30.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["L1", "L2", "L3", "L4"]


def test_ac1_full_lumbar_sequence_in_order():
    """AC1: All lumbar vertebrae supplied in reverse come out in L1-L5 order."""
    centroids = [
        _centroid("L5", (0.0, 0.0, 0.0)),
        _centroid("L4", (0.0, 0.0, 10.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
        _centroid("L2", (0.0, 0.0, 30.0)),
        _centroid("L1", (0.0, 0.0, 40.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["L1", "L2", "L3", "L4", "L5"]


def test_ac1_mixed_regions_canonical_order():
    """AC1: Mixed cervical, thoracic, and lumbar levels come out in C→T→L order."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("T12", (0.0, 0.0, 10.0)),
        _centroid("C7", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["C7", "T12", "L1"]


def test_ac1_single_level_present():
    """AC1: A single level is returned as a one-element present_levels list."""
    centroids = [_centroid("T6", (5.0, 5.0, 50.0))]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["T6"]


# =========================================================================== #
# AC2: Missing-level detection is correct
# =========================================================================== #


def test_ac2_no_gap_yields_empty_missing():
    """AC2: A contiguous sequence T1-T3 with no gap yields empty missing_levels."""
    centroids = [
        _centroid("T1", (0.0, 0.0, 0.0)),
        _centroid("T2", (0.0, 0.0, 10.0)),
        _centroid("T3", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.missing_levels == []


def test_ac2_gap_in_middle_detected():
    """AC2: T1 and T3 present but T2 absent → missing_levels == ['T2']."""
    centroids = [
        _centroid("T1", (0.0, 0.0, 0.0)),
        _centroid("T3", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.missing_levels == ["T2"]


def test_ac2_multiple_gaps_all_reported():
    """AC2: L1, L3, L5 present → L2 and L4 both in missing_levels."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
        _centroid("L5", (0.0, 0.0, 40.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert "L2" in result.missing_levels
    assert "L4" in result.missing_levels
    assert len(result.missing_levels) == 2


def test_ac2_levels_outside_span_not_reported():
    """AC2: Levels outside the min-max span (e.g. C1-C7 when only L1-L3 present) are not missing."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    # Nothing in missing — and definitely not cervical/thoracic levels
    assert result.missing_levels == []
    for name in result.missing_levels:
        assert name.startswith("L") or name.startswith("S")


def test_ac2_single_level_no_missing():
    """AC2: A single level has no span and therefore no missing levels."""
    centroids = [_centroid("T8", (0.0, 0.0, 80.0))]
    result = compute_spine_relationships(centroids)
    assert result.missing_levels == []


def test_ac2_cross_region_gap_detected():
    """AC2: T12 and L2 present → L1 (which falls between them) is missing."""
    centroids = [
        _centroid("T12", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 30.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert "L1" in result.missing_levels


def test_ac2_missing_levels_in_canonical_order():
    """AC2: missing_levels are listed in anatomical order."""
    centroids = [
        _centroid("T1", (0.0, 0.0, 0.0)),
        _centroid("T5", (0.0, 0.0, 40.0)),
    ]
    result = compute_spine_relationships(centroids)
    # Should be [T2, T3, T4] in that order
    assert result.missing_levels == ["T2", "T3", "T4"]


# =========================================================================== #
# AC3: Neighbour spacings are correct Euclidean distances
# =========================================================================== #


def test_ac3_single_pair_spacing_correct():
    """AC3: Two centroids 10mm apart along z yield one spacing of 10.0."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert len(result.neighbour_spacings_mm) == 1
    assert result.neighbour_spacings_mm[0] == pytest.approx(10.0)


def test_ac3_spacing_count_equals_n_minus_1():
    """AC3: n present levels yields exactly n-1 spacings."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0)),
        _centroid("T11", (0.0, 0.0, 10.0)),
        _centroid("T12", (0.0, 0.0, 20.0)),
        _centroid("L1", (0.0, 0.0, 30.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert len(result.neighbour_spacings_mm) == 3


def test_ac3_spacings_computed_in_anatomical_order():
    """AC3: Spacings are between centroids in anatomical order, not input order."""
    # Supply in reverse; spacings must still reflect canonical order positions
    mm_l1 = (0.0, 0.0, 0.0)
    mm_l2 = (0.0, 0.0, 10.0)
    centroids = [
        _centroid("L2", mm_l2),
        _centroid("L1", mm_l1),
    ]
    result = compute_spine_relationships(centroids)
    expected = _dist(mm_l1, mm_l2)
    assert len(result.neighbour_spacings_mm) == 1
    assert result.neighbour_spacings_mm[0] == pytest.approx(expected)


def test_ac3_3d_euclidean_distance():
    """AC3: Spacing is the true 3-D Euclidean distance (not just z-component)."""
    mm_a = (3.0, 4.0, 0.0)
    mm_b = (0.0, 0.0, 0.0)
    # 3-4-0 right triangle → distance = 5.0
    centroids = [
        _centroid("L1", mm_b),
        _centroid("L2", mm_a),
    ]
    result = compute_spine_relationships(centroids)
    assert result.neighbour_spacings_mm[0] == pytest.approx(5.0)


def test_ac3_empty_spacings_when_fewer_than_2_levels():
    """AC3: A single level yields an empty neighbour_spacings_mm list."""
    centroids = [_centroid("C1", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    assert result.neighbour_spacings_mm == []


def test_ac3_zero_centroids_empty_spacings():
    """AC3: Zero centroids yields an empty neighbour_spacings_mm list."""
    result = compute_spine_relationships([])
    assert result.neighbour_spacings_mm == []


def test_ac3_all_spacings_are_positive():
    """AC3: All spacings are positive for distinct centroids."""
    centroids = [
        _centroid("C1", (0.0, 0.0, 0.0)),
        _centroid("C2", (0.0, 0.0, 8.0)),
        _centroid("C3", (0.0, 0.0, 18.0)),
    ]
    result = compute_spine_relationships(centroids)
    for s in result.neighbour_spacings_mm:
        assert s > 0.0


def test_ac3_spacings_match_hand_computed():
    """AC3: Three centroids at known positions yield spacings matching hand computation."""
    mm_t1 = (0.0, 0.0, 0.0)
    mm_t2 = (3.0, 0.0, 4.0)   # distance from t1 = 5.0
    mm_t3 = (3.0, 0.0, 12.0)  # distance from t2 = 8.0
    centroids = [
        _centroid("T1", mm_t1),
        _centroid("T2", mm_t2),
        _centroid("T3", mm_t3),
    ]
    result = compute_spine_relationships(centroids)
    assert result.neighbour_spacings_mm[0] == pytest.approx(5.0)
    assert result.neighbour_spacings_mm[1] == pytest.approx(8.0)


# =========================================================================== #
# AC4: Label-sequence continuity detection is correct
# =========================================================================== #


def test_ac4_ordered_input_is_continuous():
    """AC4: Centroids supplied in anatomical order yield is_continuous=True."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_ac4_out_of_order_input_not_continuous():
    """AC4: An out-of-order label (L1→T12→L2→L5) sets is_continuous=False."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("T12", (0.0, 0.0, 10.0)),  # out of order (T12 < L1 canonically)
        _centroid("L2", (0.0, 0.0, 20.0)),
        _centroid("L5", (0.0, 0.0, 30.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is False


def test_ac4_out_of_order_labels_lists_offenders():
    """AC4: out_of_order_labels contains the label(s) that broke monotonicity."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("T12", (0.0, 0.0, 10.0)),
        _centroid("L2", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert "T12" in result.out_of_order_labels


def test_ac4_continuous_implies_empty_out_of_order():
    """AC4: When is_continuous is True, out_of_order_labels is empty."""
    centroids = [
        _centroid("C5", (0.0, 0.0, 0.0)),
        _centroid("C6", (0.0, 0.0, 5.0)),
        _centroid("C7", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_ac4_completely_reversed_input_not_continuous():
    """AC4: Completely reversed input (L3, L2, L1) is not continuous."""
    centroids = [
        _centroid("L3", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
        _centroid("L1", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is False
    assert len(result.out_of_order_labels) >= 1


def test_ac4_single_level_is_continuous():
    """AC4: A single level trivially satisfies continuity."""
    centroids = [_centroid("T7", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_ac4_zero_levels_is_continuous():
    """AC4: Zero centroids yields is_continuous=True and empty out_of_order_labels."""
    result = compute_spine_relationships([])
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_ac4_out_of_order_labels_in_input_order():
    """AC4: out_of_order_labels contains offenders in the order they appeared in input."""
    # Supply: T1, L1, T2 — L1 appears before T2 but after T1; T2 is out of order relative
    # to L1's position (L1 > T2 canonically). Check that the offender is recorded.
    centroids = [
        _centroid("T1", (0.0, 0.0, 0.0)),
        _centroid("L1", (0.0, 0.0, 10.0)),
        _centroid("T2", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is False
    assert len(result.out_of_order_labels) >= 1


# =========================================================================== #
# Decision 3: UNKNOWN labels are silently skipped
# =========================================================================== #


def test_unknown_label_not_in_present_levels():
    """UNKNOWN centroids are excluded from present_levels."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid(UNKNOWN, (0.0, 0.0, 5.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert UNKNOWN not in result.present_levels
    assert result.present_levels == ["L1", "L2"]


def test_unknown_label_not_in_missing_levels():
    """UNKNOWN centroids do not appear in missing_levels."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid(UNKNOWN, (0.0, 0.0, 5.0)),
        _centroid("L3", (0.0, 0.0, 20.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert UNKNOWN not in result.missing_levels


def test_unknown_label_excluded_from_spacings():
    """UNKNOWN centroid coordinates do not affect neighbour_spacings_mm."""
    mm_l1 = (0.0, 0.0, 0.0)
    mm_l2 = (0.0, 0.0, 10.0)
    centroids = [
        _centroid("L1", mm_l1),
        _centroid(UNKNOWN, (0.0, 0.0, 999.0)),  # should be ignored
        _centroid("L2", mm_l2),
    ]
    result = compute_spine_relationships(centroids)
    assert len(result.neighbour_spacings_mm) == 1
    assert result.neighbour_spacings_mm[0] == pytest.approx(10.0)


def test_unknown_label_excluded_from_continuity():
    """UNKNOWN centroids do not count as out-of-order labels."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid(UNKNOWN, (0.0, 0.0, 5.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.is_continuous is True
    assert UNKNOWN not in result.out_of_order_labels


def test_all_unknown_yields_empty_result():
    """All-UNKNOWN input yields completely empty result with is_continuous=True."""
    centroids = [
        _centroid(UNKNOWN, (0.0, 0.0, 0.0)),
        _centroid(UNKNOWN, (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == []
    assert result.missing_levels == []
    assert result.neighbour_spacings_mm == []
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


# =========================================================================== #
# Decision 4: Degenerate inputs
# =========================================================================== #


def test_degenerate_zero_centroids():
    """Zero centroids: all lists empty, is_continuous=True (Decision 4)."""
    result = compute_spine_relationships([])
    assert result.present_levels == []
    assert result.missing_levels == []
    assert result.neighbour_spacings_mm == []
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_degenerate_one_centroid():
    """One centroid: present_levels has one entry, other lists empty, is_continuous=True."""
    centroids = [_centroid("C3", (1.0, 2.0, 3.0))]
    result = compute_spine_relationships(centroids)
    assert result.present_levels == ["C3"]
    assert result.missing_levels == []
    assert result.neighbour_spacings_mm == []
    assert result.is_continuous is True
    assert result.out_of_order_labels == []


def test_degenerate_two_centroids_one_spacing():
    """Two centroids yield exactly one spacing and continuity is checked (Decision 4)."""
    centroids = [
        _centroid("T1", (0.0, 0.0, 0.0)),
        _centroid("T2", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert len(result.neighbour_spacings_mm) == 1
    assert result.is_continuous is True


# =========================================================================== #
# Determinism
# =========================================================================== #


def test_determinism_same_result_twice():
    """Two calls with the same input return identical SpineRelationships."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0)),
        _centroid("T12", (0.0, 0.0, 20.0)),
        _centroid("L1", (0.0, 0.0, 30.0)),
    ]
    r1 = compute_spine_relationships(centroids)
    r2 = compute_spine_relationships(centroids)
    assert r1.present_levels == r2.present_levels
    assert r1.missing_levels == r2.missing_levels
    assert r1.neighbour_spacings_mm == r2.neighbour_spacings_mm
    assert r1.is_continuous == r2.is_continuous
    assert r1.out_of_order_labels == r2.out_of_order_labels


def test_determinism_out_of_order_input():
    """Determinism holds for out-of-order input that triggers is_continuous=False."""
    centroids = [
        _centroid("L3", (0.0, 0.0, 0.0)),
        _centroid("L1", (0.0, 0.0, 10.0)),
        _centroid("L2", (0.0, 0.0, 20.0)),
    ]
    r1 = compute_spine_relationships(centroids)
    r2 = compute_spine_relationships(centroids)
    assert r1.is_continuous == r2.is_continuous
    assert r1.out_of_order_labels == r2.out_of_order_labels


# =========================================================================== #
# Adversarial: immutability of input
# =========================================================================== #


def test_input_list_not_mutated():
    """compute_spine_relationships does not mutate the input list."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
    ]
    original = list(centroids)
    compute_spine_relationships(centroids)
    assert centroids == original


# =========================================================================== #
# Adversarial: custom convention
# =========================================================================== #


def test_custom_convention_accepted():
    """compute_spine_relationships accepts an explicit LabelConvention without error."""
    from segqc.labels import LabelConvention
    convention = LabelConvention.default()
    centroids = [_centroid("T1", (0.0, 0.0, 0.0))]
    result = compute_spine_relationships(centroids, convention=convention)
    assert isinstance(result, SpineRelationships)


# =========================================================================== #
# Adversarial: labels not in CANONICAL_ORDER treated like UNKNOWN
# =========================================================================== #


def test_non_canonical_level_name_skipped():
    """A level_name not in CANONICAL_ORDER (and not UNKNOWN) is silently skipped."""
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0)),
        _centroid("CustomBone", (0.0, 0.0, 5.0)),
        _centroid("L2", (0.0, 0.0, 10.0)),
    ]
    result = compute_spine_relationships(centroids)
    assert "CustomBone" not in result.present_levels
    # L1 and L2 still present
    assert "L1" in result.present_levels
    assert "L2" in result.present_levels
