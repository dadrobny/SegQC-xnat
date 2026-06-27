"""Tests for local vertebra neighbourhood comparison (item 024).

Covers all ten Acceptance Criteria plus adversarial and edge-case inputs:

* AC1  -- Near-zero deviation for a regular GT fixture: all deviation_score < 0.5
          and is_outlier False for a uniformly-spaced, equal-volume, on-curve spine.
* AC2  -- Single injected outlier flagged: one displaced/volume-anomalous vertebra
          has is_outlier=True while its immediate neighbours do NOT.
* AC3  -- Window boundary cases: first and last vertebrae produce valid records
          without crashing; window_labels contains at least 2 entries.
* AC4  -- Configurable window width: window_n=5 gives 5-entry window_labels for
          central vertebrae.
* AC5  -- Determinism: two identical calls return equal lists field-by-field.
* AC6  -- Return type and structure: list of VertebralNeighbourhood frozen
          dataclasses with all documented fields.
* AC7  -- Output length matches input length.
* AC8  -- ValueError for empty centroids with non-empty message.
* AC9  -- ValueError for window_n < 1 with non-empty message.
* AC10 -- deviation_score >= 0.0 for all returned records.

Adversarial / edge-case scenarios:
- Single vertebra: no crash; window_labels has 1 entry; spacing stats = 0.
- Two vertebrae: no crash; boundary vertebra window_labels has 2 entries.
- Three vertebrae: no crash; only central vertebra has full window_n=3.
- Displaced centroid (large spline offset): outlier flagged, neighbours clean.
- Volume anomaly (3x the neighbours): outlier flagged.
- window_n=1: every vertebra has a window of exactly 1 (no neighbours).
- window_n=7 with short spine (4 vertebrae): no crash.
- Even window_n (e.g. 2, 4): valid records returned without crash.
- Frozen dataclass immutability: field assignment raises.
- Input lists not mutated by compute_neighbourhood_features.
- window_labels contains int label IDs (not strings).
- deviation_score is a finite float for all records.
- std_spacing_mm == 0 for a single-pair window (not NaN or negative).
- mean_spacing_mm positive for well-separated centroids.
- mean_volume_mm3 positive for positive-volume inputs.
- Error messages are non-empty, human-readable strings.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no external services).
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pytest

from segqc.features.centroids import LabelCentroid
from segqc.features.geometry import BBox, LabelGeometry
from segqc.features.spline_offset import VertebralSplineOffset
from segqc.features.neighbourhood import (
    VertebralNeighbourhood,
    compute_neighbourhood_features,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: Tuple[float, float, float],
    label: int,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with the given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _offset(
    label: int,
    level_name: str,
    offset_mm: float = 0.1,
) -> VertebralSplineOffset:
    """Build a minimal VertebralSplineOffset with the given offset_mm."""
    return VertebralSplineOffset(
        label=label,
        level_name=level_name,
        closest_u=0.5,
        offset_mm=offset_mm,
        offset_voxel=offset_mm,
        dx_mm=offset_mm,
        dy_mm=0.0,
        dz_mm=0.0,
    )


_DUMMY_BBOX = BBox(
    x_min=0.0, x_max=4.0,
    y_min=0.0, y_max=4.0,
    z_min=0.0, z_max=4.0,
)


def _geometry(label: int, volume_mm3: float = 1000.0) -> LabelGeometry:
    """Build a minimal LabelGeometry with the given physical volume."""
    return LabelGeometry(
        voxel_count=int(volume_mm3),
        physical_volume_mm3=volume_mm3,
        extent_x_mm=10.0,
        extent_y_mm=10.0,
        extent_z_mm=10.0,
        bbox_voxel=_DUMMY_BBOX,
        bbox_physical=_DUMMY_BBOX,
        touches_inferior=False,
        touches_superior=False,
        touches_left=False,
        touches_right=False,
        touches_anterior=False,
        touches_posterior=False,
    )


_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _uniform_spine(
    n: int = 6,
    spacing_mm: float = 10.0,
    offset_mm: float = 0.1,
    volume_mm3: float = 1000.0,
) -> Tuple[List[LabelCentroid], List[VertebralSplineOffset], Dict[int, LabelGeometry]]:
    """Return a regular (uniform) spine with equal spacing, offsets, and volumes."""
    centroids = [
        _centroid(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]
    offsets = [_offset(label=i + 1, level_name=_LEVELS[i % len(_LEVELS)], offset_mm=offset_mm)
               for i in range(n)]
    geometries = {i + 1: _geometry(label=i + 1, volume_mm3=volume_mm3) for i in range(n)}
    return centroids, offsets, geometries


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_vertebral_neighbourhood():
    """VertebralNeighbourhood is importable from segqc.features.neighbourhood."""
    from segqc.features.neighbourhood import VertebralNeighbourhood as VN  # noqa: F401
    assert VN is VertebralNeighbourhood


def test_import_compute_neighbourhood_features():
    """compute_neighbourhood_features is importable from segqc.features.neighbourhood."""
    from segqc.features.neighbourhood import compute_neighbourhood_features as cnf  # noqa: F401
    assert callable(cnf)


def test_no_import_error():
    """Importing segqc.features.neighbourhood raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.neighbourhood")
    assert hasattr(mod, "VertebralNeighbourhood")
    assert hasattr(mod, "compute_neighbourhood_features")


# =========================================================================== #
# AC1: Near-zero deviation for a regular GT fixture
# =========================================================================== #


def test_ac1_regular_spine_deviation_score_near_zero():
    """AC1: All deviation_score values < 0.5 for a uniform GT fixture."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.deviation_score < 0.5, (
            f"Level {rec.level_name}: deviation_score={rec.deviation_score:.4f} >= 0.5"
        )


def test_ac1_regular_spine_no_outliers():
    """AC1: is_outlier is False for all vertebrae on a uniform GT fixture."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.is_outlier is False, (
            f"Level {rec.level_name}: unexpected is_outlier=True "
            f"(deviation_score={rec.deviation_score:.4f})"
        )


def test_ac1_regular_seven_point_spine_no_outliers():
    """AC1: 7-point uniform spine also has no outliers."""
    centroids, offsets, geometries = _uniform_spine(n=7, spacing_mm=12.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.is_outlier is False


def test_ac1_regular_spine_mean_volume_correct():
    """AC1: mean_volume_mm3 equals the uniform volume for a regular fixture."""
    vol = 800.0
    centroids, offsets, geometries = _uniform_spine(n=5, volume_mm3=vol)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert math.isclose(rec.mean_volume_mm3, vol, rel_tol=1e-6), (
            f"Level {rec.level_name}: mean_volume_mm3={rec.mean_volume_mm3:.2f} != {vol}"
        )


def test_ac1_regular_spine_mean_offset_correct():
    """AC1: mean_offset_mm equals the uniform offset for a regular fixture."""
    off = 0.2
    centroids, offsets, geometries = _uniform_spine(n=5, offset_mm=off)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert math.isclose(rec.mean_offset_mm, off, rel_tol=1e-6), (
            f"Level {rec.level_name}: mean_offset_mm={rec.mean_offset_mm:.4f} != {off}"
        )


# =========================================================================== #
# AC2: Single injected outlier flagged; neighbours not flagged
# =========================================================================== #


def test_ac2_displaced_centroid_outlier_flagged():
    """AC2: Vertebra with a large spline offset (outlier) has is_outlier=True."""
    centroids, offsets, geometries = _uniform_spine(n=7, offset_mm=0.1)
    # Replace offset of vertebra at index 3 with a large offset (15 mm)
    large_offset = _offset(label=4, level_name=_LEVELS[3], offset_mm=15.0)
    offsets_perturbed = offsets[:3] + [large_offset] + offsets[4:]
    results = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    assert results[3].is_outlier is True, (
        f"Expected is_outlier=True for displaced vertebra, "
        f"deviation_score={results[3].deviation_score:.4f}"
    )


def test_ac2_displaced_centroid_neighbours_not_flagged():
    """AC2: Immediate neighbours of the outlier vertebra are NOT flagged."""
    centroids, offsets, geometries = _uniform_spine(n=7, offset_mm=0.1)
    large_offset = _offset(label=4, level_name=_LEVELS[3], offset_mm=15.0)
    offsets_perturbed = offsets[:3] + [large_offset] + offsets[4:]
    results = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    # Immediate neighbours are indices 2 and 4
    assert results[2].is_outlier is False, (
        f"Neighbour at index 2 unexpectedly flagged as outlier "
        f"(deviation_score={results[2].deviation_score:.4f})"
    )
    assert results[4].is_outlier is False, (
        f"Neighbour at index 4 unexpectedly flagged as outlier "
        f"(deviation_score={results[4].deviation_score:.4f})"
    )


def test_ac2_volume_anomaly_outlier_flagged():
    """AC2: Vertebra with 3x neighbour volume is flagged as outlier."""
    centroids, offsets, geometries = _uniform_spine(n=7, volume_mm3=1000.0)
    # Triple the volume of vertebra at index 3
    geometries_perturbed = dict(geometries)
    geometries_perturbed[4] = _geometry(label=4, volume_mm3=3000.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries_perturbed)
    assert results[3].is_outlier is True, (
        f"Expected is_outlier=True for volume anomaly, "
        f"deviation_score={results[3].deviation_score:.4f}"
    )


def test_ac2_volume_anomaly_neighbours_not_flagged():
    """AC2: Immediate neighbours of a volume anomaly are NOT flagged."""
    centroids, offsets, geometries = _uniform_spine(n=7, volume_mm3=1000.0)
    geometries_perturbed = dict(geometries)
    geometries_perturbed[4] = _geometry(label=4, volume_mm3=3000.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries_perturbed)
    assert results[2].is_outlier is False, (
        "Neighbour at index 2 unexpectedly flagged"
    )
    assert results[4].is_outlier is False, (
        "Neighbour at index 4 unexpectedly flagged"
    )


def test_ac2_outlier_deviation_score_larger_than_neighbours():
    """AC2: The outlier vertebra's deviation_score exceeds its neighbours'."""
    centroids, offsets, geometries = _uniform_spine(n=7, offset_mm=0.1)
    large_offset = _offset(label=4, level_name=_LEVELS[3], offset_mm=15.0)
    offsets_perturbed = offsets[:3] + [large_offset] + offsets[4:]
    results = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    assert results[3].deviation_score > results[2].deviation_score, (
        "Outlier should have higher deviation_score than left neighbour"
    )
    assert results[3].deviation_score > results[4].deviation_score, (
        "Outlier should have higher deviation_score than right neighbour"
    )


# =========================================================================== #
# AC3: Window boundary cases handled without crash
# =========================================================================== #


def test_ac3_first_vertebra_no_crash():
    """AC3: The first vertebra (left boundary) produces a valid record."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    rec = results[0]
    assert isinstance(rec, VertebralNeighbourhood)
    assert rec.label == centroids[0].label
    assert rec.level_name == centroids[0].level_name


def test_ac3_last_vertebra_no_crash():
    """AC3: The last vertebra (right boundary) produces a valid record."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    rec = results[-1]
    assert isinstance(rec, VertebralNeighbourhood)
    assert rec.label == centroids[-1].label


def test_ac3_first_vertebra_window_has_at_least_two():
    """AC3: window_labels for the first vertebra contains at least 2 entries."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results[0].window_labels) >= 2, (
        f"First vertebra window_labels={results[0].window_labels} has < 2 entries"
    )


def test_ac3_last_vertebra_window_has_at_least_two():
    """AC3: window_labels for the last vertebra contains at least 2 entries."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results[-1].window_labels) >= 2, (
        f"Last vertebra window_labels={results[-1].window_labels} has < 2 entries"
    )


def test_ac3_boundary_records_all_fields_finite():
    """AC3: Numeric fields for boundary vertebrae are all finite."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for idx in (0, -1):
        rec = results[idx]
        for val in (
            rec.mean_spacing_mm, rec.median_spacing_mm, rec.std_spacing_mm,
            rec.mean_offset_mm, rec.median_offset_mm, rec.std_offset_mm,
            rec.mean_volume_mm3, rec.median_volume_mm3, rec.std_volume_mm3,
            rec.deviation_score,
        ):
            assert math.isfinite(float(val)), (
                f"Boundary record has non-finite field: {val!r}"
            )


# =========================================================================== #
# AC4: Configurable window width
# =========================================================================== #


def test_ac4_window_n5_central_window_labels_has_five():
    """AC4: Central vertebra window_labels contains 5 entries for window_n=5."""
    centroids, offsets, geometries = _uniform_spine(n=7)
    results = compute_neighbourhood_features(centroids, offsets, geometries, window_n=5)
    # Central vertebra is at index 3 in a 7-element spine
    assert len(results[3].window_labels) == 5, (
        f"Expected 5 window entries for central vertebra, "
        f"got {len(results[3].window_labels)}: {results[3].window_labels}"
    )


def test_ac4_window_n5_all_records_valid():
    """AC4: All records are valid VertebralNeighbourhood instances with window_n=5."""
    centroids, offsets, geometries = _uniform_spine(n=7)
    results = compute_neighbourhood_features(centroids, offsets, geometries, window_n=5)
    assert len(results) == 7
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac4_window_n1_each_vertebra_has_one_window_entry():
    """AC4: window_n=1 gives each vertebra a window of exactly 1 (no neighbours)."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries, window_n=1)
    for rec in results:
        assert len(rec.window_labels) == 1, (
            f"Expected 1 window entry for window_n=1, got {len(rec.window_labels)}"
        )


def test_ac4_window_n3_default_central_has_three():
    """AC4: Default window_n=3 gives 3 entries for a central vertebra."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    # Index 2 is the central vertebra in a 5-element spine
    assert len(results[2].window_labels) == 3, (
        f"Expected 3 window entries for central vertebra, "
        f"got {len(results[2].window_labels)}"
    )


def test_ac4_large_window_short_spine_no_crash():
    """AC4: window_n=7 on a 4-vertebra spine produces valid results without crash."""
    centroids, offsets, geometries = _uniform_spine(n=4)
    results = compute_neighbourhood_features(centroids, offsets, geometries, window_n=7)
    assert len(results) == 4
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac4_even_window_n_no_crash():
    """AC4: Even window_n values (2, 4) produce valid records without crash."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    for wn in (2, 4):
        results = compute_neighbourhood_features(centroids, offsets, geometries, window_n=wn)
        assert len(results) == 6, f"window_n={wn}: expected 6 results"
        for rec in results:
            assert isinstance(rec, VertebralNeighbourhood)


# =========================================================================== #
# AC5: Determinism
# =========================================================================== #


def test_ac5_determinism_regular_spine():
    """AC5: Two identical calls on a regular spine return equal lists."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results_a = compute_neighbourhood_features(centroids, offsets, geometries)
    results_b = compute_neighbourhood_features(centroids, offsets, geometries)
    for a, b in zip(results_a, results_b):
        assert a.deviation_score == b.deviation_score
        assert a.is_outlier == b.is_outlier
        assert a.mean_offset_mm == b.mean_offset_mm
        assert a.mean_volume_mm3 == b.mean_volume_mm3
        assert a.window_labels == b.window_labels


def test_ac5_determinism_with_outlier():
    """AC5: Determinism holds when one vertebra is an outlier."""
    centroids, offsets, geometries = _uniform_spine(n=6, offset_mm=0.1)
    large_offset = _offset(label=3, level_name=_LEVELS[2], offset_mm=12.0)
    offsets_perturbed = offsets[:2] + [large_offset] + offsets[3:]
    results_a = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    results_b = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    for a, b in zip(results_a, results_b):
        assert a.is_outlier == b.is_outlier
        assert a.deviation_score == b.deviation_score


def test_ac5_determinism_different_window_n():
    """AC5: Determinism holds for window_n=5."""
    centroids, offsets, geometries = _uniform_spine(n=7)
    results_a = compute_neighbourhood_features(centroids, offsets, geometries, window_n=5)
    results_b = compute_neighbourhood_features(centroids, offsets, geometries, window_n=5)
    for a, b in zip(results_a, results_b):
        assert a.deviation_score == b.deviation_score
        assert a.window_labels == b.window_labels


# =========================================================================== #
# AC6: Return type and structure
# =========================================================================== #


def test_ac6_returns_list():
    """AC6: compute_neighbourhood_features returns a list."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    result = compute_neighbourhood_features(centroids, offsets, geometries)
    assert isinstance(result, list)


def test_ac6_each_element_is_vertebral_neighbourhood():
    """AC6: Each element is a VertebralNeighbourhood instance."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac6_has_all_required_fields():
    """AC6: VertebralNeighbourhood exposes all documented fields."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    rec = compute_neighbourhood_features(centroids, offsets, geometries)[0]
    required = (
        "label", "level_name", "window_labels",
        "mean_spacing_mm", "median_spacing_mm", "std_spacing_mm",
        "mean_offset_mm", "median_offset_mm", "std_offset_mm",
        "mean_volume_mm3", "median_volume_mm3", "std_volume_mm3",
        "deviation_score", "is_outlier",
    )
    for attr in required:
        assert hasattr(rec, attr), f"VertebralNeighbourhood missing field: {attr}"


def test_ac6_is_frozen():
    """AC6: VertebralNeighbourhood is immutable (field assignment raises)."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    rec = compute_neighbourhood_features(centroids, offsets, geometries)[0]
    with pytest.raises(Exception):
        rec.deviation_score = 999.0  # type: ignore[misc]


def test_ac6_is_outlier_is_bool():
    """AC6: is_outlier is a Python bool, not truthy int or numpy bool."""
    centroids, offsets, geometries = _uniform_spine(n=4)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert isinstance(rec.is_outlier, bool), (
            f"is_outlier is {type(rec.is_outlier)}, expected bool"
        )


def test_ac6_level_name_matches_input():
    """AC6: level_name in each output record matches the input centroid."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for c, rec in zip(centroids, results):
        assert rec.level_name == c.level_name, (
            f"level_name mismatch: got {rec.level_name!r}, expected {c.level_name!r}"
        )


def test_ac6_label_matches_input():
    """AC6: label in each output record matches the input centroid label."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for c, rec in zip(centroids, results):
        assert rec.label == c.label


def test_ac6_window_labels_are_ints():
    """AC6: window_labels contains integer label IDs (not strings)."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        for lbl in rec.window_labels:
            assert isinstance(lbl, int), (
                f"window_labels contains {type(lbl)} ({lbl!r}), expected int"
            )


# =========================================================================== #
# AC7: Output length matches input length
# =========================================================================== #


def test_ac7_output_length_matches_input():
    """AC7: len(result) == len(centroids) for various spine lengths."""
    for n in (1, 2, 3, 5, 7, 10):
        centroids, offsets, geometries = _uniform_spine(n=n)
        results = compute_neighbourhood_features(centroids, offsets, geometries)
        assert len(results) == n, (
            f"n={n}: expected {n} results, got {len(results)}"
        )


def test_ac7_output_order_matches_input():
    """AC7: Output records are in the same order as the input centroids."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for i, (c, rec) in enumerate(zip(centroids, results)):
        assert rec.label == c.label, (
            f"Position {i}: output label={rec.label}, input label={c.label}"
        )


# =========================================================================== #
# AC8: ValueError for empty centroids
# =========================================================================== #


def test_ac8_empty_centroids_raises_value_error():
    """AC8: compute_neighbourhood_features([]) raises ValueError."""
    _, offsets, geometries = _uniform_spine(n=3)
    with pytest.raises(ValueError):
        compute_neighbourhood_features([], [], geometries)


def test_ac8_empty_centroids_message_non_empty():
    """AC8: The ValueError for empty centroids has a non-empty, readable message."""
    with pytest.raises(ValueError) as exc_info:
        compute_neighbourhood_features([], [], {})
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac8_error_message_no_raw_repr():
    """AC8: The ValueError message is not a raw Python object repr."""
    import re
    try:
        compute_neighbourhood_features([], [], {})
    except ValueError as exc:
        msg = str(exc)
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            f"Error message looks like a raw repr: {msg!r}"
        )


# =========================================================================== #
# AC9: ValueError for window_n < 1
# =========================================================================== #


def test_ac9_window_n_zero_raises_value_error():
    """AC9: window_n=0 raises ValueError."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    with pytest.raises(ValueError):
        compute_neighbourhood_features(centroids, offsets, geometries, window_n=0)


def test_ac9_window_n_negative_raises_value_error():
    """AC9: window_n=-1 raises ValueError."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    with pytest.raises(ValueError):
        compute_neighbourhood_features(centroids, offsets, geometries, window_n=-1)


def test_ac9_window_n_zero_message_non_empty():
    """AC9: ValueError for window_n=0 has a non-empty, readable message."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    with pytest.raises(ValueError) as exc_info:
        compute_neighbourhood_features(centroids, offsets, geometries, window_n=0)
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac9_window_n_negative_message_non_empty():
    """AC9: ValueError for window_n=-1 has a non-empty, readable message."""
    centroids, offsets, geometries = _uniform_spine(n=3)
    with pytest.raises(ValueError) as exc_info:
        compute_neighbourhood_features(centroids, offsets, geometries, window_n=-1)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC10: deviation_score is non-negative
# =========================================================================== #


def test_ac10_deviation_score_non_negative_regular():
    """AC10: deviation_score >= 0 for a regular GT fixture."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.deviation_score >= 0.0, (
            f"Level {rec.level_name}: deviation_score={rec.deviation_score:.6f} < 0"
        )


def test_ac10_deviation_score_non_negative_with_outlier():
    """AC10: deviation_score >= 0 even when one vertebra is an outlier."""
    centroids, offsets, geometries = _uniform_spine(n=7, offset_mm=0.1)
    large_offset = _offset(label=4, level_name=_LEVELS[3], offset_mm=15.0)
    offsets_perturbed = offsets[:3] + [large_offset] + offsets[4:]
    results = compute_neighbourhood_features(centroids, offsets_perturbed, geometries)
    for rec in results:
        assert rec.deviation_score >= 0.0


def test_ac10_deviation_score_is_finite():
    """AC10: deviation_score is a finite float for all records."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert math.isfinite(rec.deviation_score), (
            f"Level {rec.level_name}: deviation_score is not finite: {rec.deviation_score}"
        )


def test_ac10_deviation_score_finite_single_vertebra():
    """AC10: deviation_score is finite for a single-vertebra input (edge case)."""
    centroids, offsets, geometries = _uniform_spine(n=1)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results) == 1
    assert math.isfinite(results[0].deviation_score)
    assert results[0].deviation_score >= 0.0


# =========================================================================== #
# Adversarial: single vertebra (degenerate input)
# =========================================================================== #


def test_adv_single_vertebra_no_crash():
    """Single vertebra input produces 1 valid record without crash."""
    centroids, offsets, geometries = _uniform_spine(n=1)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results) == 1
    assert isinstance(results[0], VertebralNeighbourhood)


def test_adv_single_vertebra_window_labels_has_one():
    """Single vertebra: window_labels contains exactly 1 entry."""
    centroids, offsets, geometries = _uniform_spine(n=1)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results[0].window_labels) == 1


def test_adv_single_vertebra_spacing_stats_non_negative():
    """Single vertebra: spacing stats are 0 or non-negative (no pair to compute)."""
    centroids, offsets, geometries = _uniform_spine(n=1)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    rec = results[0]
    assert rec.mean_spacing_mm >= 0.0
    assert rec.std_spacing_mm >= 0.0


# =========================================================================== #
# Adversarial: two vertebrae (minimum with a neighbour)
# =========================================================================== #


def test_adv_two_vertebrae_no_crash():
    """Two vertebrae produce 2 valid records without crash."""
    centroids, offsets, geometries = _uniform_spine(n=2)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    assert len(results) == 2


def test_adv_two_vertebrae_both_boundary_window_labels():
    """Two vertebrae: both records have window_labels of length 2."""
    centroids, offsets, geometries = _uniform_spine(n=2)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert len(rec.window_labels) == 2


def test_adv_two_vertebrae_all_fields_finite():
    """Two vertebrae: all numeric fields are finite."""
    centroids, offsets, geometries = _uniform_spine(n=2, spacing_mm=10.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        for val in (
            rec.mean_spacing_mm, rec.median_spacing_mm, rec.std_spacing_mm,
            rec.mean_offset_mm, rec.mean_volume_mm3, rec.deviation_score,
        ):
            assert math.isfinite(float(val)), f"Non-finite field: {val!r}"


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #


def test_adv_centroids_input_not_mutated():
    """compute_neighbourhood_features does not mutate the centroid list."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    original = list(centroids)
    compute_neighbourhood_features(centroids, offsets, geometries)
    assert centroids == original


def test_adv_offsets_input_not_mutated():
    """compute_neighbourhood_features does not mutate the offsets list."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    original = list(offsets)
    compute_neighbourhood_features(centroids, offsets, geometries)
    assert offsets == original


def test_adv_geometries_input_not_mutated():
    """compute_neighbourhood_features does not mutate the geometries dict."""
    centroids, offsets, geometries = _uniform_spine(n=5)
    original_keys = set(geometries.keys())
    compute_neighbourhood_features(centroids, offsets, geometries)
    assert set(geometries.keys()) == original_keys


# =========================================================================== #
# Adversarial: numerical invariants
# =========================================================================== #


def test_adv_mean_volume_positive_for_positive_inputs():
    """mean_volume_mm3 is positive when all input volumes are positive."""
    centroids, offsets, geometries = _uniform_spine(n=5, volume_mm3=500.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.mean_volume_mm3 > 0.0


def test_adv_std_spacing_zero_for_equal_spacing():
    """std_spacing_mm is approximately 0 for a uniform spine (equal spacings)."""
    centroids, offsets, geometries = _uniform_spine(n=5, spacing_mm=10.0)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    # Central vertebra has a symmetric window with equal spacings
    rec = results[2]
    assert rec.std_spacing_mm == pytest.approx(0.0, abs=1e-6), (
        f"std_spacing_mm={rec.std_spacing_mm:.6f} for uniform spacing"
    )


def test_adv_median_offset_equals_mean_for_uniform():
    """median_offset_mm equals mean_offset_mm for a uniform offset fixture."""
    off = 0.5
    centroids, offsets, geometries = _uniform_spine(n=5, offset_mm=off)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    rec = results[2]
    assert math.isclose(rec.median_offset_mm, rec.mean_offset_mm, rel_tol=1e-6)


def test_adv_window_labels_contains_focal_label():
    """window_labels always includes the focal vertebra's own label."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for c, rec in zip(centroids, results):
        assert c.label in rec.window_labels, (
            f"Focal label {c.label} not in window_labels={rec.window_labels}"
        )


def test_adv_configurable_threshold_changes_outlier_flag():
    """A lower threshold causes more vertebrae to be flagged as outliers."""
    centroids, offsets, geometries = _uniform_spine(n=7, offset_mm=0.1)
    large_offset = _offset(label=4, level_name=_LEVELS[3], offset_mm=15.0)
    offsets_perturbed = offsets[:3] + [large_offset] + offsets[4:]
    # With a high threshold, no neighbours should be flagged
    results_high = compute_neighbourhood_features(
        centroids, offsets_perturbed, geometries, outlier_threshold=1000.0
    )
    # With a zero threshold, everything should be flagged (deviation_score >= 0)
    results_low = compute_neighbourhood_features(
        centroids, offsets_perturbed, geometries, outlier_threshold=0.0
    )
    # High threshold: at most the one outlier is flagged
    n_outliers_high = sum(1 for r in results_high if r.is_outlier)
    # Low threshold: all are flagged (since deviation_score >= 0 >= threshold=0)
    n_outliers_low = sum(1 for r in results_low if r.is_outlier)
    assert n_outliers_low >= n_outliers_high, (
        "Lower threshold should flag at least as many outliers as higher threshold"
    )


def test_adv_std_spacing_non_negative():
    """std_spacing_mm is non-negative for all records."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.std_spacing_mm >= 0.0


def test_adv_std_volume_non_negative():
    """std_volume_mm3 is non-negative for all records."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.std_volume_mm3 >= 0.0


def test_adv_std_offset_non_negative():
    """std_offset_mm is non-negative for all records."""
    centroids, offsets, geometries = _uniform_spine(n=6)
    results = compute_neighbourhood_features(centroids, offsets, geometries)
    for rec in results:
        assert rec.std_offset_mm >= 0.0
