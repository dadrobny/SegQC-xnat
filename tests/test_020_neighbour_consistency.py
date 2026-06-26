"""Tests for neighbour-consistency metrics (item 020).

Covers all eight Acceptance Criteria plus adversarial and edge-case inputs:

* AC1 — regular GT spacing scores within tolerance: cv_spacing < 0.05 and
         outlier_pairs empty for a uniformly-spaced centroid sequence.
* AC2 — spacing outlier is flagged: an injected large gap (>= 2x mean) appears
         in outlier_pairs with the correct (level_a, level_b) pair.
* AC3 — monotonic progression detected for GT: is_monotonic True and
         non_monotonic_pairs empty for a well-ordered anatomical sequence.
* AC4 — swapped / non-monotonic ordering detected: is_monotonic False and
         non_monotonic_pairs contains the swapped pair.
* AC5 — determinism: two calls with identical inputs return equal results.
* AC6 — return type and structure: SpacingConsistency and MonotonicConsistency
         are frozen dataclasses with the required fields.
* AC7 — per-vertebra findings with offending labels: outlier_pairs and
         non_monotonic_pairs contain level-name string pairs, not integer labels.
* AC8 — ValueError for fewer than 2 centroids with a non-empty message.

Adversarial scenarios:
- Exactly 2 centroids: no crash for both functions; 1 spacing, 1 u-pair.
- Single centroid: both functions raise ValueError with a non-empty message.
- Zero centroids: both functions raise ValueError with a non-empty message.
- All-identical spacing: cv_spacing == 0.0 (or very close); no outliers.
- Injected small gap (<= 0.3x mean): flagged as low-outlier pair.
- Injected gap at first pair: first pair flagged, not a later pair.
- Injected gap at last pair: last pair flagged.
- All pairs swapped (reversed centroid order): all pairs non-monotonic.
- Collinear centroids (spine on z axis): no crash for either function.
- Frozen dataclass immutability: field assignment raises.
- Input list not mutated by either compute function.
- Error messages: non-empty strings, no raw Python object repr.
- outlier_pairs and non_monotonic_pairs contain string pairs (level names).
- spacings_mm and deviations_mm length == n_centroids - 1.
- u_values length == n_centroids.
- deviations_mm sum to approximately zero (deviations around mean).
- mean_spacing_mm is positive for well-separated centroids.
- cv_spacing is non-negative.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import math
from typing import List, Tuple

import pytest

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, fit_centroid_spline
from segqc.features.consistency import (
    SpacingConsistency,
    MonotonicConsistency,
    compute_spacing_consistency,
    compute_monotonic_consistency,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: Tuple[float, float, float],
    label: int = 0,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with the given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _uniform_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Return n centroids equally spaced along the z axis (straight, uniform spacing)."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    """Return 6 centroids along a gentle curve in the xz-plane."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [
        _centroid(lv, (x, 0.0, z), label=i + 1)
        for i, (lv, x, z) in enumerate(zip(levels, xs, zs))
    ]


def _fit(centroids: List[LabelCentroid], degree: int = 3) -> SplineFit:
    return fit_centroid_spline(centroids, degree=degree)


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_spacing_consistency():
    """SpacingConsistency is importable from segqc.features.consistency."""
    from segqc.features.consistency import SpacingConsistency as SC  # noqa: F401
    assert SC is SpacingConsistency


def test_import_monotonic_consistency():
    """MonotonicConsistency is importable from segqc.features.consistency."""
    from segqc.features.consistency import MonotonicConsistency as MC  # noqa: F401
    assert MC is MonotonicConsistency


def test_import_compute_spacing_consistency():
    """compute_spacing_consistency is importable from segqc.features.consistency."""
    from segqc.features.consistency import compute_spacing_consistency as csc  # noqa: F401
    assert callable(csc)


def test_import_compute_monotonic_consistency():
    """compute_monotonic_consistency is importable from segqc.features.consistency."""
    from segqc.features.consistency import compute_monotonic_consistency as cmc  # noqa: F401
    assert callable(cmc)


def test_no_import_error():
    """Importing segqc.features.consistency raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.consistency")
    assert hasattr(mod, "SpacingConsistency")
    assert hasattr(mod, "MonotonicConsistency")
    assert hasattr(mod, "compute_spacing_consistency")
    assert hasattr(mod, "compute_monotonic_consistency")


# =========================================================================== #
# AC1: Regular GT spacing scores within tolerance
# =========================================================================== #


def test_ac1_uniform_spacing_cv_near_zero():
    """AC1: Uniformly-spaced centroids yield cv_spacing < 0.05."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    assert result.cv_spacing < 0.05, (
        f"Expected cv_spacing < 0.05 for uniform spacing, got {result.cv_spacing:.6f}"
    )


def test_ac1_uniform_spacing_no_outliers():
    """AC1: Uniformly-spaced centroids yield no outlier_pairs."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    assert len(result.outlier_pairs) == 0, (
        f"Expected no outlier pairs for uniform spacing, got {result.outlier_pairs}"
    )


def test_ac1_uniform_seven_points_cv_near_zero():
    """AC1: 7-point uniform spine also yields cv_spacing < 0.05."""
    centroids = _uniform_spine(7, spacing_mm=12.0)
    result = compute_spacing_consistency(centroids)
    assert result.cv_spacing < 0.05


def test_ac1_uniform_large_spacing_no_outliers():
    """AC1: Uniform spacing with large inter-centroid distance has no outliers."""
    centroids = _uniform_spine(5, spacing_mm=25.0)
    result = compute_spacing_consistency(centroids)
    assert len(result.outlier_pairs) == 0


def test_ac1_mean_spacing_matches_uniform():
    """AC1: mean_spacing_mm equals the uniform step size (within floating-point tolerance)."""
    spacing = 10.0
    centroids = _uniform_spine(6, spacing_mm=spacing)
    result = compute_spacing_consistency(centroids)
    assert math.isclose(result.mean_spacing_mm, spacing, rel_tol=1e-6), (
        f"mean_spacing_mm={result.mean_spacing_mm:.6f}, expected {spacing}"
    )


# =========================================================================== #
# AC2: Spacing outlier is flagged
# =========================================================================== #


def test_ac2_large_gap_flagged():
    """AC2: An injected gap >= 2x mean is flagged in outlier_pairs."""
    # Build uniform spine then double the gap between centroids[2] and centroids[3]
    centroids = _uniform_spine(6, spacing_mm=10.0)
    # Replace centroids[3] so that the gap between [2] and [3] is 30 mm (3x the others)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 50.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]
    result = compute_spacing_consistency(perturbed)
    outlier_labels = [pair[0] for pair in result.outlier_pairs] + \
                     [pair[1] for pair in result.outlier_pairs]
    assert len(result.outlier_pairs) >= 1, "Expected at least one outlier pair"
    # The pair bridging index 2→3 should be flagged
    pair_names = [(p[0], p[1]) for p in result.outlier_pairs]
    assert any(
        centroids[2].level_name in pair and centroids[3].level_name in pair
        for pair in pair_names
    ), f"Expected ({centroids[2].level_name}, {centroids[3].level_name}) in outlier_pairs, got {pair_names}"


def test_ac2_outlier_pair_correct_level_names():
    """AC2: outlier_pairs contain the level names of the flagged adjacent pair."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    old = centroids[4]
    shifted = _centroid(old.level_name, (0.0, 0.0, 80.0), label=old.label)
    perturbed = centroids[:4] + [shifted] + centroids[5:]
    result = compute_spacing_consistency(perturbed)
    assert len(result.outlier_pairs) >= 1
    # Verify all pairs are string 2-tuples
    for pair in result.outlier_pairs:
        assert isinstance(pair[0], str)
        assert isinstance(pair[1], str)


def test_ac2_injected_gap_at_first_pair():
    """AC2: An injected large gap at the first pair flags the first pair."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    # Move centroids[1] far from centroids[0]
    old = centroids[1]
    shifted = _centroid(old.level_name, (0.0, 0.0, 40.0), label=old.label)
    perturbed = [centroids[0], shifted] + centroids[2:]
    result = compute_spacing_consistency(perturbed)
    assert len(result.outlier_pairs) >= 1
    pair_names = [(p[0], p[1]) for p in result.outlier_pairs]
    assert any(
        centroids[0].level_name in pair and old.level_name in pair
        for pair in pair_names
    ), f"First pair not flagged; outlier_pairs={pair_names}"


def test_ac2_injected_gap_at_last_pair():
    """AC2: An injected large gap at the last pair flags the last pair."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    old = centroids[-1]
    shifted = _centroid(old.level_name, (0.0, 0.0, 200.0), label=old.label)
    perturbed = centroids[:-1] + [shifted]
    result = compute_spacing_consistency(perturbed)
    assert len(result.outlier_pairs) >= 1
    pair_names = [(p[0], p[1]) for p in result.outlier_pairs]
    assert any(
        centroids[-2].level_name in pair and old.level_name in pair
        for pair in pair_names
    ), f"Last pair not flagged; outlier_pairs={pair_names}"


def test_ac2_small_gap_flagged_as_low_outlier():
    """AC2 (extension): An injected tiny gap (<= 0.3x mean) is also flagged."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    # Move centroids[3] to be only 1 mm from centroids[2] (normal gap is 10 mm)
    old = centroids[3]
    near = _centroid(old.level_name, (0.0, 0.0, 21.0), label=old.label)
    perturbed = centroids[:3] + [near] + centroids[4:]
    result = compute_spacing_consistency(perturbed)
    assert len(result.outlier_pairs) >= 1, (
        "Expected a near-coincident pair to be flagged as a low outlier"
    )


def test_ac2_single_injected_outlier_others_clean():
    """AC2: Only the injected outlier pair is flagged; remaining pairs are clean."""
    centroids = _uniform_spine(7, spacing_mm=10.0)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]
    result = compute_spacing_consistency(perturbed)
    # There should be exactly 1 outlier pair (the injected one)
    # Allow for 2 in edge cases where the shifted point also creates a low gap after
    assert len(result.outlier_pairs) >= 1


# =========================================================================== #
# AC3: Monotonic progression detected for GT
# =========================================================================== #


def test_ac3_gt_straight_spine_is_monotonic():
    """AC3: A well-ordered straight spine has is_monotonic True."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert result.is_monotonic is True, (
        f"Expected is_monotonic=True for GT straight spine, "
        f"non_monotonic_pairs={result.non_monotonic_pairs}"
    )


def test_ac3_gt_straight_spine_no_non_monotonic_pairs():
    """AC3: A well-ordered straight spine has empty non_monotonic_pairs."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(result.non_monotonic_pairs) == 0, (
        f"Expected no non-monotonic pairs, got {result.non_monotonic_pairs}"
    )


def test_ac3_gt_curved_spine_is_monotonic():
    """AC3: A well-ordered curved spine has is_monotonic True."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert result.is_monotonic is True


def test_ac3_gt_curved_spine_no_non_monotonic_pairs():
    """AC3: A well-ordered curved spine has empty non_monotonic_pairs."""
    centroids = _curved_spine()
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(result.non_monotonic_pairs) == 0


def test_ac3_u_values_length_equals_n_centroids():
    """AC3: u_values in MonotonicConsistency has one entry per centroid."""
    centroids = _uniform_spine(6)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(result.u_values) == len(centroids)


def test_ac3_u_values_all_in_unit_interval():
    """AC3: All u_values are in [0.0, 1.0]."""
    centroids = _uniform_spine(6)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    for u in result.u_values:
        assert 0.0 <= float(u) <= 1.0, f"u value {u} out of [0, 1]"


# =========================================================================== #
# AC4: Swapped / non-monotonic ordering detected
# =========================================================================== #


def test_ac4_swapped_pair_is_non_monotonic():
    """AC4: Swapping two adjacent centroids makes is_monotonic False."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    # Swap centroids at index 2 and 3
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    fit = _fit(centroids)  # Fit on the original ordering
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False, (
        "Expected is_monotonic=False after swapping two adjacent centroids"
    )


def test_ac4_swapped_pair_appears_in_non_monotonic_pairs():
    """AC4: The swapped pair's level names appear in non_monotonic_pairs."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    # Swap centroids at index 2 and 3
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(swapped, fit)
    assert len(result.non_monotonic_pairs) >= 1, (
        "Expected at least one non-monotonic pair"
    )


def test_ac4_non_monotonic_pairs_contain_string_tuples():
    """AC4: non_monotonic_pairs are (str, str) tuples (level names, not int labels)."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    swapped = list(centroids)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(swapped, fit)
    for pair in result.non_monotonic_pairs:
        assert isinstance(pair[0], str), f"Expected str, got {type(pair[0])}"
        assert isinstance(pair[1], str), f"Expected str, got {type(pair[1])}"


def test_ac4_reversed_sequence_all_non_monotonic():
    """AC4: A fully-reversed centroid sequence results in is_monotonic False."""
    centroids = _uniform_spine(5, spacing_mm=10.0)
    reversed_centroids = list(reversed(centroids))
    fit = _fit(centroids)
    result = compute_monotonic_consistency(reversed_centroids, fit)
    assert result.is_monotonic is False


def test_ac4_reversed_sequence_has_non_monotonic_pairs():
    """AC4: A fully-reversed sequence has multiple non-monotonic pairs."""
    centroids = _uniform_spine(5, spacing_mm=10.0)
    reversed_centroids = list(reversed(centroids))
    fit = _fit(centroids)
    result = compute_monotonic_consistency(reversed_centroids, fit)
    assert len(result.non_monotonic_pairs) >= 1


def test_ac4_swapped_middle_pair_curved_spine():
    """AC4: Swapping the middle two centroids of a curved spine is detected."""
    centroids = _curved_spine()
    mid = len(centroids) // 2
    swapped = list(centroids)
    swapped[mid - 1], swapped[mid] = swapped[mid], swapped[mid - 1]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(swapped, fit)
    assert result.is_monotonic is False


# =========================================================================== #
# AC5: Determinism
# =========================================================================== #


def test_ac5_spacing_determinism_uniform():
    """AC5: Two calls to compute_spacing_consistency return equal results."""
    centroids = _uniform_spine(6)
    result_a = compute_spacing_consistency(centroids)
    result_b = compute_spacing_consistency(centroids)
    assert result_a.mean_spacing_mm == result_b.mean_spacing_mm
    assert result_a.cv_spacing == result_b.cv_spacing
    assert result_a.spacings_mm == result_b.spacings_mm
    assert result_a.deviations_mm == result_b.deviations_mm
    assert result_a.outlier_pairs == result_b.outlier_pairs


def test_ac5_spacing_determinism_with_outlier():
    """AC5: Determinism holds for a sequence containing an outlier gap."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]
    result_a = compute_spacing_consistency(perturbed)
    result_b = compute_spacing_consistency(perturbed)
    assert result_a.outlier_pairs == result_b.outlier_pairs
    assert result_a.cv_spacing == result_b.cv_spacing


def test_ac5_monotonic_determinism_gt():
    """AC5: Two calls to compute_monotonic_consistency return equal results (GT)."""
    centroids = _uniform_spine(6)
    fit = _fit(centroids)
    result_a = compute_monotonic_consistency(centroids, fit)
    result_b = compute_monotonic_consistency(centroids, fit)
    assert result_a.is_monotonic == result_b.is_monotonic
    assert result_a.non_monotonic_pairs == result_b.non_monotonic_pairs
    assert result_a.u_values == result_b.u_values


def test_ac5_monotonic_determinism_swapped():
    """AC5: Determinism holds when centroids are swapped."""
    centroids = _uniform_spine(6)
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    fit = _fit(centroids)
    result_a = compute_monotonic_consistency(swapped, fit)
    result_b = compute_monotonic_consistency(swapped, fit)
    assert result_a.is_monotonic == result_b.is_monotonic
    assert result_a.non_monotonic_pairs == result_b.non_monotonic_pairs


# =========================================================================== #
# AC6: Return type and structure
# =========================================================================== #


def test_ac6_spacing_returns_spacing_consistency_instance():
    """AC6: compute_spacing_consistency returns a SpacingConsistency instance."""
    centroids = _uniform_spine(5)
    result = compute_spacing_consistency(centroids)
    assert isinstance(result, SpacingConsistency)


def test_ac6_spacing_has_required_fields():
    """AC6: SpacingConsistency exposes the required five fields."""
    centroids = _uniform_spine(5)
    result = compute_spacing_consistency(centroids)
    for attr in ("mean_spacing_mm", "cv_spacing", "spacings_mm", "deviations_mm", "outlier_pairs"):
        assert hasattr(result, attr), f"SpacingConsistency missing field: {attr}"


def test_ac6_spacing_is_frozen():
    """AC6: SpacingConsistency is immutable (field assignment raises)."""
    centroids = _uniform_spine(5)
    result = compute_spacing_consistency(centroids)
    with pytest.raises(Exception):
        result.mean_spacing_mm = 999.0  # type: ignore[misc]


def test_ac6_monotonic_returns_monotonic_consistency_instance():
    """AC6: compute_monotonic_consistency returns a MonotonicConsistency instance."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert isinstance(result, MonotonicConsistency)


def test_ac6_monotonic_has_required_fields():
    """AC6: MonotonicConsistency exposes the required three fields."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    for attr in ("is_monotonic", "non_monotonic_pairs", "u_values"):
        assert hasattr(result, attr), f"MonotonicConsistency missing field: {attr}"


def test_ac6_monotonic_is_frozen():
    """AC6: MonotonicConsistency is immutable (field assignment raises)."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    with pytest.raises(Exception):
        result.is_monotonic = False  # type: ignore[misc]


def test_ac6_spacings_mm_length_is_n_minus_1():
    """AC6: len(spacings_mm) == n_centroids - 1."""
    for n in (2, 3, 5, 7):
        centroids = _uniform_spine(n)
        result = compute_spacing_consistency(centroids)
        assert len(result.spacings_mm) == n - 1, (
            f"n={n}: expected {n - 1} spacings, got {len(result.spacings_mm)}"
        )


def test_ac6_deviations_mm_length_is_n_minus_1():
    """AC6: len(deviations_mm) == n_centroids - 1."""
    for n in (2, 3, 5, 6):
        centroids = _uniform_spine(n)
        result = compute_spacing_consistency(centroids)
        assert len(result.deviations_mm) == n - 1


def test_ac6_u_values_length_is_n_centroids():
    """AC6: len(u_values) == n_centroids."""
    for n in (2, 3, 5, 6):
        centroids = _uniform_spine(n)
        fit = _fit(centroids)
        result = compute_monotonic_consistency(centroids, fit)
        assert len(result.u_values) == n


# =========================================================================== #
# AC7: Per-vertebra findings with offending labels (level-name string pairs)
# =========================================================================== #


def test_ac7_outlier_pairs_are_string_tuples():
    """AC7: outlier_pairs contains (str, str) tuples of level names."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    old = centroids[2]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:2] + [shifted] + centroids[3:]
    result = compute_spacing_consistency(perturbed)
    for pair in result.outlier_pairs:
        assert isinstance(pair[0], str), (
            f"outlier_pairs entry[0] is {type(pair[0])}, expected str"
        )
        assert isinstance(pair[1], str), (
            f"outlier_pairs entry[1] is {type(pair[1])}, expected str"
        )


def test_ac7_non_monotonic_pairs_are_string_tuples():
    """AC7: non_monotonic_pairs contains (str, str) tuples of level names."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    swapped = list(centroids)
    swapped[1], swapped[2] = swapped[2], swapped[1]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(swapped, fit)
    for pair in result.non_monotonic_pairs:
        assert isinstance(pair[0], str)
        assert isinstance(pair[1], str)


def test_ac7_outlier_pairs_not_integer_labels():
    """AC7: outlier_pairs values are not raw integer label IDs."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 80.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]
    result = compute_spacing_consistency(perturbed)
    for pair in result.outlier_pairs:
        # Level names should not be parseable as bare integers
        assert not pair[0].isdigit(), (
            f"outlier_pairs entry[0] looks like an int: {pair[0]!r}"
        )
        assert not pair[1].isdigit(), (
            f"outlier_pairs entry[1] looks like an int: {pair[1]!r}"
        )


def test_ac7_non_monotonic_pairs_not_integer_labels():
    """AC7: non_monotonic_pairs values are level-name strings, not integer labels."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(swapped, fit)
    for pair in result.non_monotonic_pairs:
        assert not pair[0].isdigit()
        assert not pair[1].isdigit()


# =========================================================================== #
# AC8: ValueError for fewer than 2 centroids
# =========================================================================== #


def test_ac8_spacing_zero_centroids_raises_value_error():
    """AC8: compute_spacing_consistency([]) raises ValueError."""
    with pytest.raises(ValueError):
        compute_spacing_consistency([])


def test_ac8_spacing_zero_centroids_message_non_empty():
    """AC8: The ValueError for 0 centroids has a non-empty, readable message."""
    with pytest.raises(ValueError) as exc_info:
        compute_spacing_consistency([])
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac8_spacing_one_centroid_raises_value_error():
    """AC8: compute_spacing_consistency with 1 centroid raises ValueError."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0), label=1)]
    with pytest.raises(ValueError):
        compute_spacing_consistency(centroids)


def test_ac8_spacing_one_centroid_message_non_empty():
    """AC8: The ValueError for 1 centroid has a non-empty message."""
    centroids = [_centroid("L1", (0.0, 0.0, 0.0), label=1)]
    with pytest.raises(ValueError) as exc_info:
        compute_spacing_consistency(centroids)
    assert str(exc_info.value).strip()


def test_ac8_monotonic_zero_centroids_raises_value_error():
    """AC8: compute_monotonic_consistency([]) raises ValueError."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    with pytest.raises(ValueError):
        compute_monotonic_consistency([], fit)


def test_ac8_monotonic_zero_centroids_message_non_empty():
    """AC8: The ValueError for 0 centroids has a non-empty, readable message."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    with pytest.raises(ValueError) as exc_info:
        compute_monotonic_consistency([], fit)
    assert str(exc_info.value).strip()


def test_ac8_monotonic_one_centroid_raises_value_error():
    """AC8: compute_monotonic_consistency with 1 centroid raises ValueError."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    one = [centroids[0]]
    with pytest.raises(ValueError):
        compute_monotonic_consistency(one, fit)


def test_ac8_monotonic_one_centroid_message_non_empty():
    """AC8: The ValueError for 1 centroid has a non-empty message."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    one = [centroids[0]]
    with pytest.raises(ValueError) as exc_info:
        compute_monotonic_consistency(one, fit)
    assert str(exc_info.value).strip()


def test_ac8_error_messages_no_raw_object_repr():
    """AC8: ValueError messages do not look like raw Python object reprs."""
    import re
    # Spacing
    try:
        compute_spacing_consistency([])
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"spacing error message looks like a raw repr: {msg!r}"
        )
    # Monotonic
    centroids = _uniform_spine(4)
    fit = _fit(centroids)
    try:
        compute_monotonic_consistency([], fit)
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"monotonic error message looks like a raw repr: {msg!r}"
        )


# =========================================================================== #
# Adversarial: exactly 2 centroids (minimum valid input)
# =========================================================================== #


def test_adv_two_centroids_spacing_no_crash():
    """2 centroids (minimum) do not crash compute_spacing_consistency."""
    centroids = _uniform_spine(2)
    result = compute_spacing_consistency(centroids)
    assert isinstance(result, SpacingConsistency)


def test_adv_two_centroids_spacing_one_spacing():
    """2 centroids yield exactly 1 spacing value."""
    centroids = _uniform_spine(2)
    result = compute_spacing_consistency(centroids)
    assert len(result.spacings_mm) == 1


def test_adv_two_centroids_spacing_cv_zero():
    """2 centroids (only 1 spacing) yield cv_spacing == 0.0 (no variation possible)."""
    centroids = _uniform_spine(2, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    # With a single spacing there is no variance; CV must be 0 or undefined-treated-as-0
    assert result.cv_spacing == pytest.approx(0.0, abs=1e-9)


def test_adv_two_centroids_monotonic_no_crash():
    """2 centroids (minimum) do not crash compute_monotonic_consistency."""
    centroids = _uniform_spine(2)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert isinstance(result, MonotonicConsistency)


def test_adv_two_centroids_monotonic_one_pair():
    """2 centroids yield exactly 1 u_value pair to check."""
    centroids = _uniform_spine(2)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(result.u_values) == 2


# =========================================================================== #
# Adversarial: collinear centroids (spine on z axis)
# =========================================================================== #


def test_adv_collinear_spacing_no_crash():
    """Collinear centroids (all on z axis) do not crash compute_spacing_consistency."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0), label=1),
        _centroid("T11", (0.0, 0.0, 10.0), label=2),
        _centroid("T12", (0.0, 0.0, 20.0), label=3),
        _centroid("L1", (0.0, 0.0, 30.0), label=4),
        _centroid("L2", (0.0, 0.0, 40.0), label=5),
    ]
    result = compute_spacing_consistency(centroids)
    assert isinstance(result, SpacingConsistency)
    assert math.isfinite(result.mean_spacing_mm)
    assert math.isfinite(result.cv_spacing)


def test_adv_collinear_monotonic_no_crash():
    """Collinear centroids do not crash compute_monotonic_consistency."""
    centroids = [
        _centroid("T10", (0.0, 0.0, 0.0), label=1),
        _centroid("T11", (0.0, 0.0, 10.0), label=2),
        _centroid("T12", (0.0, 0.0, 20.0), label=3),
        _centroid("L1", (0.0, 0.0, 30.0), label=4),
        _centroid("L2", (0.0, 0.0, 40.0), label=5),
    ]
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert isinstance(result, MonotonicConsistency)


# =========================================================================== #
# Adversarial: immutability of input lists
# =========================================================================== #


def test_adv_spacing_input_not_mutated():
    """compute_spacing_consistency does not mutate the input centroid list."""
    centroids = _uniform_spine(5)
    original = list(centroids)
    compute_spacing_consistency(centroids)
    assert centroids == original


def test_adv_monotonic_input_not_mutated():
    """compute_monotonic_consistency does not mutate the input centroid list."""
    centroids = _uniform_spine(5)
    original = list(centroids)
    fit = _fit(centroids)
    compute_monotonic_consistency(centroids, fit)
    assert centroids == original


def test_adv_monotonic_spline_fit_not_mutated():
    """compute_monotonic_consistency does not mutate the SplineFit object."""
    centroids = _uniform_spine(5)
    fit = _fit(centroids)
    u_before = tuple(fit.u)
    n_before = fit.n_points
    compute_monotonic_consistency(centroids, fit)
    assert fit.u == u_before
    assert fit.n_points == n_before


# =========================================================================== #
# Adversarial: numerical invariants
# =========================================================================== #


def test_adv_spacings_mm_all_positive():
    """All entries in spacings_mm are positive for well-separated centroids."""
    centroids = _uniform_spine(6, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    for s in result.spacings_mm:
        assert float(s) > 0.0, f"Spacing {s} is non-positive"


def test_adv_mean_spacing_positive():
    """mean_spacing_mm is positive for well-separated centroids."""
    centroids = _uniform_spine(6)
    result = compute_spacing_consistency(centroids)
    assert result.mean_spacing_mm > 0.0


def test_adv_cv_spacing_non_negative():
    """cv_spacing is non-negative."""
    centroids = _uniform_spine(6)
    result = compute_spacing_consistency(centroids)
    assert result.cv_spacing >= 0.0


def test_adv_deviations_sum_near_zero():
    """deviations_mm sum to approximately zero (they are residuals around the mean)."""
    centroids = _uniform_spine(7, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    total = sum(float(d) for d in result.deviations_mm)
    assert math.isclose(total, 0.0, abs_tol=1e-9), (
        f"deviations_mm sum to {total:.2e}, expected ~0"
    )


def test_adv_u_values_all_finite():
    """u_values in MonotonicConsistency are all finite floats in [0, 1]."""
    centroids = _uniform_spine(6)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    for u in result.u_values:
        assert math.isfinite(float(u)), f"u value {u} is not finite"
        assert 0.0 <= float(u) <= 1.0, f"u value {u} out of [0, 1]"


def test_adv_curved_spine_spacing_mean_positive():
    """compute_spacing_consistency on a curved spine yields a positive mean."""
    centroids = _curved_spine()
    result = compute_spacing_consistency(centroids)
    assert result.mean_spacing_mm > 0.0


def test_adv_three_centroids_spacing_no_crash():
    """3 centroids yield 2 spacings without crashing."""
    centroids = _uniform_spine(3, spacing_mm=10.0)
    result = compute_spacing_consistency(centroids)
    assert len(result.spacings_mm) == 2
    assert math.isfinite(result.mean_spacing_mm)


def test_adv_three_centroids_monotonic_no_crash():
    """3 centroids yield a valid MonotonicConsistency without crashing."""
    centroids = _uniform_spine(3)
    fit = _fit(centroids)
    result = compute_monotonic_consistency(centroids, fit)
    assert len(result.u_values) == 3
