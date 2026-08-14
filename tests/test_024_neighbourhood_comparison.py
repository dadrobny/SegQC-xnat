"""Tests for local vertebra neighbourhood comparison (item 024), updated to
item 110's generalised API: ``compute_neighbourhood_features(elements,
features, *, scored=DEFAULT_SCORED, window_n=3, outlier_threshold=2.0)``.

``elements`` is an ordered sequence exposing ``.label``/``.level_name``
(``LabelCentroid`` is reused verbatim, no new type introduced). ``features``
is ``Mapping[str, Sequence[float]]``; ``DEFAULT_FEATURES`` is the historical
``("spacing_mm", "offset_mm", "volume_mm3")`` triple and ``DEFAULT_SCORED``
is the historical ``("offset_mm", "volume_mm3")`` pair. Per-record stats now
live under ``rec.stats[name].{mean,median,std,z_score}`` rather than nine
fixed fields (e.g. what was ``rec.mean_offset_mm`` is now
``rec.stats["offset_mm"].mean``).

Every behavioural assertion from the pre-refactor module survives; only the
calling convention and field-access shape changed (item 110's Assumptions
explicitly authorise this file's update).

Covers all ten original Acceptance Criteria plus adversarial and edge-case
inputs:

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
* AC8  -- ValueError for empty elements with non-empty message.
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

from segfacet.features.centroids import LabelCentroid
from segfacet.features.neighbourhood import (
    DEFAULT_SCORED,
    VertebralNeighbourhood,
    compute_neighbourhood_features,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _element(level_name: str, mm: Tuple[float, float, float], label: int) -> LabelCentroid:
    """Build a minimal LabelCentroid used as the generalised engine's element
    type; only ``.label``/``.level_name`` are read by the engine itself."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _uniform_spine(
    n: int = 6,
    spacing_mm: float = 10.0,
    offset_mm: float = 0.1,
    volume_mm3: float = 1000.0,
) -> Tuple[List[LabelCentroid], Dict[str, List[float]]]:
    """Return a regular (uniform) spine: elements plus a features mapping
    with the historical spacing_mm/offset_mm/volume_mm3 triple."""
    elements = [
        _element(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]
    features = {
        "spacing_mm": [spacing_mm] * n,
        "offset_mm": [offset_mm] * n,
        "volume_mm3": [volume_mm3] * n,
    }
    return elements, features


def _with_offset(features: Dict[str, List[float]], index: int, offset_mm: float) -> Dict[str, List[float]]:
    """Return a copy of *features* with offset_mm[index] overwritten."""
    new_features = {k: list(v) for k, v in features.items()}
    new_features["offset_mm"][index] = offset_mm
    return new_features


def _with_volume(features: Dict[str, List[float]], index: int, volume_mm3: float) -> Dict[str, List[float]]:
    """Return a copy of *features* with volume_mm3[index] overwritten."""
    new_features = {k: list(v) for k, v in features.items()}
    new_features["volume_mm3"][index] = volume_mm3
    return new_features


def _call(elements, features, **kwargs):
    kwargs.setdefault("scored", DEFAULT_SCORED)
    return compute_neighbourhood_features(elements, features, **kwargs)


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_vertebral_neighbourhood():
    """VertebralNeighbourhood is importable from segfacet.features.neighbourhood."""
    from segfacet.features.neighbourhood import VertebralNeighbourhood as VN  # noqa: F401
    assert VN is VertebralNeighbourhood


def test_import_compute_neighbourhood_features():
    """compute_neighbourhood_features is importable from segfacet.features.neighbourhood."""
    from segfacet.features.neighbourhood import compute_neighbourhood_features as cnf  # noqa: F401
    assert callable(cnf)


def test_no_import_error():
    """Importing segfacet.features.neighbourhood raises no error."""
    import importlib
    mod = importlib.import_module("segfacet.features.neighbourhood")
    assert hasattr(mod, "VertebralNeighbourhood")
    assert hasattr(mod, "compute_neighbourhood_features")


# =========================================================================== #
# AC1: Near-zero deviation for a regular GT fixture
# =========================================================================== #


def test_ac1_regular_spine_deviation_score_near_zero():
    """AC1: All deviation_score values < 0.5 for a uniform GT fixture."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.deviation_score < 0.5, (
            f"Level {rec.level_name}: deviation_score={rec.deviation_score:.4f} >= 0.5"
        )


def test_ac1_regular_spine_no_outliers():
    """AC1: is_outlier is False for all vertebrae on a uniform GT fixture."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.is_outlier is False, (
            f"Level {rec.level_name}: unexpected is_outlier=True "
            f"(deviation_score={rec.deviation_score:.4f})"
        )


def test_ac1_regular_seven_point_spine_no_outliers():
    """AC1: 7-point uniform spine also has no outliers."""
    elements, features = _uniform_spine(n=7, spacing_mm=12.0)
    results = _call(elements, features)
    for rec in results:
        assert rec.is_outlier is False


def test_ac1_regular_spine_mean_volume_correct():
    """AC1: mean volume_mm3 equals the uniform volume for a regular fixture."""
    vol = 800.0
    elements, features = _uniform_spine(n=5, volume_mm3=vol)
    results = _call(elements, features)
    for rec in results:
        assert math.isclose(rec.stats["volume_mm3"].mean, vol, rel_tol=1e-6), (
            f"Level {rec.level_name}: mean volume_mm3={rec.stats['volume_mm3'].mean:.2f} != {vol}"
        )


def test_ac1_regular_spine_mean_offset_correct():
    """AC1: mean offset_mm equals the uniform offset for a regular fixture."""
    off = 0.2
    elements, features = _uniform_spine(n=5, offset_mm=off)
    results = _call(elements, features)
    for rec in results:
        assert math.isclose(rec.stats["offset_mm"].mean, off, rel_tol=1e-6), (
            f"Level {rec.level_name}: mean offset_mm={rec.stats['offset_mm'].mean:.4f} != {off}"
        )


# =========================================================================== #
# AC2: Single injected outlier flagged; neighbours not flagged
# =========================================================================== #


def test_ac2_displaced_centroid_outlier_flagged():
    """AC2: Vertebra with a large spline offset (outlier) has is_outlier=True."""
    elements, features = _uniform_spine(n=7, offset_mm=0.1)
    features = _with_offset(features, 3, 15.0)
    results = _call(elements, features)
    assert results[3].is_outlier is True, (
        f"Expected is_outlier=True for displaced vertebra, "
        f"deviation_score={results[3].deviation_score:.4f}"
    )


def test_ac2_displaced_centroid_neighbours_not_flagged():
    """AC2: Immediate neighbours of the outlier vertebra are NOT flagged."""
    elements, features = _uniform_spine(n=7, offset_mm=0.1)
    features = _with_offset(features, 3, 15.0)
    results = _call(elements, features)
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
    elements, features = _uniform_spine(n=7, volume_mm3=1000.0)
    features = _with_volume(features, 3, 3000.0)
    results = _call(elements, features)
    assert results[3].is_outlier is True, (
        f"Expected is_outlier=True for volume anomaly, "
        f"deviation_score={results[3].deviation_score:.4f}"
    )


def test_ac2_volume_anomaly_neighbours_not_flagged():
    """AC2: Immediate neighbours of a volume anomaly are NOT flagged."""
    elements, features = _uniform_spine(n=7, volume_mm3=1000.0)
    features = _with_volume(features, 3, 3000.0)
    results = _call(elements, features)
    assert results[2].is_outlier is False, (
        "Neighbour at index 2 unexpectedly flagged"
    )
    assert results[4].is_outlier is False, (
        "Neighbour at index 4 unexpectedly flagged"
    )


def test_ac2_outlier_deviation_score_larger_than_neighbours():
    """AC2: The outlier vertebra's deviation_score exceeds its neighbours'."""
    elements, features = _uniform_spine(n=7, offset_mm=0.1)
    features = _with_offset(features, 3, 15.0)
    results = _call(elements, features)
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
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    rec = results[0]
    assert isinstance(rec, VertebralNeighbourhood)
    assert rec.label == elements[0].label
    assert rec.level_name == elements[0].level_name


def test_ac3_last_vertebra_no_crash():
    """AC3: The last vertebra (right boundary) produces a valid record."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    rec = results[-1]
    assert isinstance(rec, VertebralNeighbourhood)
    assert rec.label == elements[-1].label


def test_ac3_first_vertebra_window_has_at_least_two():
    """AC3: window_labels for the first vertebra contains at least 2 entries."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    assert len(results[0].window_labels) >= 2, (
        f"First vertebra window_labels={results[0].window_labels} has < 2 entries"
    )


def test_ac3_last_vertebra_window_has_at_least_two():
    """AC3: window_labels for the last vertebra contains at least 2 entries."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    assert len(results[-1].window_labels) >= 2, (
        f"Last vertebra window_labels={results[-1].window_labels} has < 2 entries"
    )


def test_ac3_boundary_records_all_fields_finite():
    """AC3: Numeric fields for boundary vertebrae are all finite."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    for idx in (0, -1):
        rec = results[idx]
        for name, stat in rec.stats.items():
            assert math.isfinite(stat.mean), (name, "mean")
            assert math.isfinite(stat.median), (name, "median")
            assert math.isfinite(stat.std), (name, "std")
        assert math.isfinite(rec.deviation_score)


# =========================================================================== #
# AC4: Configurable window width
# =========================================================================== #


def test_ac4_window_n5_central_window_labels_has_five():
    """AC4: Central vertebra window_labels contains 5 entries for window_n=5."""
    elements, features = _uniform_spine(n=7)
    results = _call(elements, features, window_n=5)
    # Central vertebra is at index 3 in a 7-element spine
    assert len(results[3].window_labels) == 5, (
        f"Expected 5 window entries for central vertebra, "
        f"got {len(results[3].window_labels)}: {results[3].window_labels}"
    )


def test_ac4_window_n5_all_records_valid():
    """AC4: All records are valid VertebralNeighbourhood instances with window_n=5."""
    elements, features = _uniform_spine(n=7)
    results = _call(elements, features, window_n=5)
    assert len(results) == 7
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac4_window_n1_each_vertebra_has_one_window_entry():
    """AC4: window_n=1 gives each vertebra a window of exactly 1 (no neighbours)."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features, window_n=1)
    for rec in results:
        assert len(rec.window_labels) == 1, (
            f"Expected 1 window entry for window_n=1, got {len(rec.window_labels)}"
        )


def test_ac4_window_n3_default_central_has_three():
    """AC4: Default window_n=3 gives 3 entries for a central vertebra."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    # Index 2 is the central vertebra in a 5-element spine
    assert len(results[2].window_labels) == 3, (
        f"Expected 3 window entries for central vertebra, "
        f"got {len(results[2].window_labels)}"
    )


def test_ac4_large_window_short_spine_no_crash():
    """AC4: window_n=7 on a 4-vertebra spine produces valid results without crash."""
    elements, features = _uniform_spine(n=4)
    results = _call(elements, features, window_n=7)
    assert len(results) == 4
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac4_even_window_n_no_crash():
    """AC4: Even window_n values (2, 4) produce valid records without crash."""
    elements, features = _uniform_spine(n=6)
    for wn in (2, 4):
        results = _call(elements, features, window_n=wn)
        assert len(results) == 6, f"window_n={wn}: expected 6 results"
        for rec in results:
            assert isinstance(rec, VertebralNeighbourhood)


# =========================================================================== #
# AC5: Determinism
# =========================================================================== #


def test_ac5_determinism_regular_spine():
    """AC5: Two identical calls on a regular spine return equal lists."""
    elements, features = _uniform_spine(n=6)
    results_a = _call(elements, features)
    results_b = _call(elements, features)
    for a, b in zip(results_a, results_b):
        assert a.deviation_score == b.deviation_score
        assert a.is_outlier == b.is_outlier
        assert a.stats["offset_mm"].mean == b.stats["offset_mm"].mean
        assert a.stats["volume_mm3"].mean == b.stats["volume_mm3"].mean
        assert a.window_labels == b.window_labels


def test_ac5_determinism_with_outlier():
    """AC5: Determinism holds when one vertebra is an outlier."""
    elements, features = _uniform_spine(n=6, offset_mm=0.1)
    features = _with_offset(features, 2, 12.0)
    results_a = _call(elements, features)
    results_b = _call(elements, features)
    for a, b in zip(results_a, results_b):
        assert a.is_outlier == b.is_outlier
        assert a.deviation_score == b.deviation_score


def test_ac5_determinism_different_window_n():
    """AC5: Determinism holds for window_n=5."""
    elements, features = _uniform_spine(n=7)
    results_a = _call(elements, features, window_n=5)
    results_b = _call(elements, features, window_n=5)
    for a, b in zip(results_a, results_b):
        assert a.deviation_score == b.deviation_score
        assert a.window_labels == b.window_labels


# =========================================================================== #
# AC6: Return type and structure
# =========================================================================== #


def test_ac6_returns_list():
    """AC6: compute_neighbourhood_features returns a list."""
    elements, features = _uniform_spine(n=5)
    result = _call(elements, features)
    assert isinstance(result, list)


def test_ac6_each_element_is_vertebral_neighbourhood():
    """AC6: Each element is a VertebralNeighbourhood instance."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)


def test_ac6_has_all_required_fields():
    """AC6: VertebralNeighbourhood exposes all documented fields, including
    the historical three features under .stats."""
    elements, features = _uniform_spine(n=3)
    rec = _call(elements, features)[0]
    required = ("label", "level_name", "window_labels", "stats", "deviation_score", "is_outlier")
    for attr in required:
        assert hasattr(rec, attr), f"VertebralNeighbourhood missing field: {attr}"
    for name in ("spacing_mm", "offset_mm", "volume_mm3"):
        assert name in rec.stats
        for stat_name in ("mean", "median", "std", "z_score"):
            assert hasattr(rec.stats[name], stat_name), (name, stat_name)


def test_ac6_is_frozen():
    """AC6: VertebralNeighbourhood is immutable (field assignment raises)."""
    elements, features = _uniform_spine(n=3)
    rec = _call(elements, features)[0]
    with pytest.raises(Exception):
        rec.deviation_score = 999.0  # type: ignore[misc]


def test_ac6_is_outlier_is_bool():
    """AC6: is_outlier is a Python bool, not truthy int or numpy bool."""
    elements, features = _uniform_spine(n=4)
    results = _call(elements, features)
    for rec in results:
        assert isinstance(rec.is_outlier, bool), (
            f"is_outlier is {type(rec.is_outlier)}, expected bool"
        )


def test_ac6_level_name_matches_input():
    """AC6: level_name in each output record matches the input element."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    for elem, rec in zip(elements, results):
        assert rec.level_name == elem.level_name, (
            f"level_name mismatch: got {rec.level_name!r}, expected {elem.level_name!r}"
        )


def test_ac6_label_matches_input():
    """AC6: label in each output record matches the input element's label."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    for elem, rec in zip(elements, results):
        assert rec.label == elem.label


def test_ac6_window_labels_are_ints():
    """AC6: window_labels contains integer label IDs (not strings)."""
    elements, features = _uniform_spine(n=5)
    results = _call(elements, features)
    for rec in results:
        for lbl in rec.window_labels:
            assert isinstance(lbl, int), (
                f"window_labels contains {type(lbl)} ({lbl!r}), expected int"
            )


# =========================================================================== #
# AC7: Output length matches input length
# =========================================================================== #


def test_ac7_output_length_matches_input():
    """AC7: len(result) == len(elements) for various spine lengths."""
    for n in (1, 2, 3, 5, 7, 10):
        elements, features = _uniform_spine(n=n)
        results = _call(elements, features)
        assert len(results) == n, (
            f"n={n}: expected {n} results, got {len(results)}"
        )


def test_ac7_output_order_matches_input():
    """AC7: Output records are in the same order as the input elements."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for i, (elem, rec) in enumerate(zip(elements, results)):
        assert rec.label == elem.label, (
            f"Position {i}: output label={rec.label}, input label={elem.label}"
        )


# =========================================================================== #
# AC8: ValueError for empty elements
# =========================================================================== #


def test_ac8_empty_elements_raises_value_error():
    """AC8: compute_neighbourhood_features([], ...) raises ValueError."""
    with pytest.raises(ValueError):
        _call([], {"spacing_mm": [], "offset_mm": [], "volume_mm3": []})


def test_ac8_empty_elements_message_non_empty():
    """AC8: The ValueError for empty elements has a non-empty, readable message."""
    with pytest.raises(ValueError) as exc_info:
        _call([], {"spacing_mm": [], "offset_mm": [], "volume_mm3": []})
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac8_error_message_no_raw_repr():
    """AC8: The ValueError message is not a raw Python object repr."""
    import re
    try:
        _call([], {"spacing_mm": [], "offset_mm": [], "volume_mm3": []})
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
    elements, features = _uniform_spine(n=3)
    with pytest.raises(ValueError):
        _call(elements, features, window_n=0)


def test_ac9_window_n_negative_raises_value_error():
    """AC9: window_n=-1 raises ValueError."""
    elements, features = _uniform_spine(n=3)
    with pytest.raises(ValueError):
        _call(elements, features, window_n=-1)


def test_ac9_window_n_zero_message_non_empty():
    """AC9: ValueError for window_n=0 has a non-empty, readable message."""
    elements, features = _uniform_spine(n=3)
    with pytest.raises(ValueError) as exc_info:
        _call(elements, features, window_n=0)
    assert str(exc_info.value).strip(), "ValueError message must not be blank"


def test_ac9_window_n_negative_message_non_empty():
    """AC9: ValueError for window_n=-1 has a non-empty, readable message."""
    elements, features = _uniform_spine(n=3)
    with pytest.raises(ValueError) as exc_info:
        _call(elements, features, window_n=-1)
    assert str(exc_info.value).strip()


# =========================================================================== #
# AC10: deviation_score is non-negative
# =========================================================================== #


def test_ac10_deviation_score_non_negative_regular():
    """AC10: deviation_score >= 0 for a regular GT fixture."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.deviation_score >= 0.0, (
            f"Level {rec.level_name}: deviation_score={rec.deviation_score:.6f} < 0"
        )


def test_ac10_deviation_score_non_negative_with_outlier():
    """AC10: deviation_score >= 0 even when one vertebra is an outlier."""
    elements, features = _uniform_spine(n=7, offset_mm=0.1)
    features = _with_offset(features, 3, 15.0)
    results = _call(elements, features)
    for rec in results:
        assert rec.deviation_score >= 0.0


def test_ac10_deviation_score_is_finite():
    """AC10: deviation_score is a finite float for all records."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert math.isfinite(rec.deviation_score), (
            f"Level {rec.level_name}: deviation_score is not finite: {rec.deviation_score}"
        )


def test_ac10_deviation_score_finite_single_vertebra():
    """AC10: deviation_score is finite for a single-vertebra input (edge case)."""
    elements, features = _uniform_spine(n=1)
    results = _call(elements, features)
    assert len(results) == 1
    assert math.isfinite(results[0].deviation_score)
    assert results[0].deviation_score >= 0.0


# =========================================================================== #
# Adversarial: single vertebra (degenerate input)
# =========================================================================== #


def test_adv_single_vertebra_no_crash():
    """Single vertebra input produces 1 valid record without crash."""
    elements, features = _uniform_spine(n=1)
    results = _call(elements, features)
    assert len(results) == 1
    assert isinstance(results[0], VertebralNeighbourhood)


def test_adv_single_vertebra_window_labels_has_one():
    """Single vertebra: window_labels contains exactly 1 entry."""
    elements, features = _uniform_spine(n=1)
    results = _call(elements, features)
    assert len(results[0].window_labels) == 1


def test_adv_single_vertebra_spacing_stats_non_negative():
    """Single vertebra: spacing stats are 0 or non-negative (no pair to compute)."""
    elements, features = _uniform_spine(n=1)
    results = _call(elements, features)
    rec = results[0]
    assert rec.stats["spacing_mm"].mean >= 0.0
    assert rec.stats["spacing_mm"].std >= 0.0


# =========================================================================== #
# Adversarial: two vertebrae (minimum with a neighbour)
# =========================================================================== #


def test_adv_two_vertebrae_no_crash():
    """Two vertebrae produce 2 valid records without crash."""
    elements, features = _uniform_spine(n=2)
    results = _call(elements, features)
    assert len(results) == 2


def test_adv_two_vertebrae_both_boundary_window_labels():
    """Two vertebrae: both records have window_labels of length 2."""
    elements, features = _uniform_spine(n=2)
    results = _call(elements, features)
    for rec in results:
        assert len(rec.window_labels) == 2


def test_adv_two_vertebrae_all_fields_finite():
    """Two vertebrae: all numeric fields are finite."""
    elements, features = _uniform_spine(n=2, spacing_mm=10.0)
    results = _call(elements, features)
    for rec in results:
        for name, stat in rec.stats.items():
            assert math.isfinite(stat.mean), name
        assert math.isfinite(rec.deviation_score)


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #


def test_adv_elements_input_not_mutated():
    """compute_neighbourhood_features does not mutate the elements list."""
    elements, features = _uniform_spine(n=5)
    original = list(elements)
    _call(elements, features)
    assert elements == original


def test_adv_features_input_not_mutated():
    """compute_neighbourhood_features does not mutate the features mapping."""
    elements, features = _uniform_spine(n=5)
    import copy as _copy
    original = _copy.deepcopy(features)
    _call(elements, features)
    assert features == original


# =========================================================================== #
# Adversarial: numerical invariants
# =========================================================================== #


def test_adv_mean_volume_positive_for_positive_inputs():
    """mean volume_mm3 is positive when all input volumes are positive."""
    elements, features = _uniform_spine(n=5, volume_mm3=500.0)
    results = _call(elements, features)
    for rec in results:
        assert rec.stats["volume_mm3"].mean > 0.0


def test_adv_std_spacing_zero_for_equal_spacing():
    """std spacing_mm is 0 for a uniform spine (equal spacings everywhere)."""
    elements, features = _uniform_spine(n=5, spacing_mm=10.0)
    results = _call(elements, features)
    # Central vertebra has a symmetric window with equal spacings
    rec = results[2]
    assert rec.stats["spacing_mm"].std == pytest.approx(0.0, abs=1e-6), (
        f"std spacing_mm={rec.stats['spacing_mm'].std:.6f} for uniform spacing"
    )


def test_adv_median_offset_equals_mean_for_uniform():
    """median offset_mm equals mean offset_mm for a uniform offset fixture."""
    off = 0.5
    elements, features = _uniform_spine(n=5, offset_mm=off)
    results = _call(elements, features)
    rec = results[2]
    assert math.isclose(
        rec.stats["offset_mm"].median, rec.stats["offset_mm"].mean, rel_tol=1e-6
    )


def test_adv_window_labels_contains_focal_label():
    """window_labels always includes the focal vertebra's own label."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for elem, rec in zip(elements, results):
        assert elem.label in rec.window_labels, (
            f"Focal label {elem.label} not in window_labels={rec.window_labels}"
        )


def test_adv_configurable_threshold_changes_outlier_flag():
    """A lower threshold causes more vertebrae to be flagged as outliers."""
    elements, features = _uniform_spine(n=7, offset_mm=0.1)
    features = _with_offset(features, 3, 15.0)
    # With a high threshold, no neighbours should be flagged
    results_high = _call(elements, features, outlier_threshold=1000.0)
    # With a zero threshold, everything should be flagged (deviation_score >= 0)
    results_low = _call(elements, features, outlier_threshold=0.0)
    # High threshold: at most the one outlier is flagged
    n_outliers_high = sum(1 for r in results_high if r.is_outlier)
    # Low threshold: all are flagged (since deviation_score >= 0 >= threshold=0)
    n_outliers_low = sum(1 for r in results_low if r.is_outlier)
    assert n_outliers_low >= n_outliers_high, (
        "Lower threshold should flag at least as many outliers as higher threshold"
    )


def test_adv_std_spacing_non_negative():
    """std spacing_mm is non-negative for all records."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.stats["spacing_mm"].std >= 0.0


def test_adv_std_volume_non_negative():
    """std volume_mm3 is non-negative for all records."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.stats["volume_mm3"].std >= 0.0


def test_adv_std_offset_non_negative():
    """std offset_mm is non-negative for all records."""
    elements, features = _uniform_spine(n=6)
    results = _call(elements, features)
    for rec in results:
        assert rec.stats["offset_mm"].std >= 0.0
