"""Tests for item 110 -- generalise the neighbourhood API, then wire it into
the realised record.

The pre-refactor ``compute_neighbourhood_features(centroids, offsets,
geometries, window_n, outlier_threshold)`` took three fixed typed arguments
and ``VertebralNeighbourhood`` had nine fixed stat fields. This module tests
the target, generalised API (chosen here since item 110 authorises the
test-writer to fix the exact shape):

``segfacet.features.neighbourhood``
    ``DEFAULT_FEATURES: Tuple[str, ...]``
        ``("spacing_mm", "offset_mm", "volume_mm3")`` -- the historical three.
    ``DEFAULT_SCORED: Tuple[str, ...]``
        ``("offset_mm", "volume_mm3")`` -- the historical scored pair
        (matching pre-refactor ``_deviation_score``; ``spacing_mm`` is
        deliberately excluded, see ``UNSCORED_RATIONALE``).
    ``UNSCORED_RATIONALE: Mapping[str, str]``
        Non-empty human-readable reason for every ``DEFAULT_FEATURES`` name
        not in ``DEFAULT_SCORED`` -- reconciles AC4's "reported but
        unscored" cases so the historical silent spacing mismatch cannot
        recur undocumented.
    ``VertebralNeighbourhood`` (frozen dataclass)
        ``label: int``, ``level_name: str``, ``window_labels: Tuple[int,
        ...]``, ``stats: Mapping[str, FeatureWindowStats]`` (one entry per
        name in the ``features`` mapping passed in, each carrying ``mean``/
        ``median``/``std`` over the *whole* window including the focal
        element, plus a leave-one-out ``z_score`` against the window's
        *other* members), ``deviation_score: float``, ``is_outlier: bool``.
    ``compute_neighbourhood_features(elements, features, *, scored=
    DEFAULT_SCORED, window_n=3, outlier_threshold=2.0) ->
    List[VertebralNeighbourhood]``
        ``elements`` is an ordered sequence of objects exposing ``.label``
        (int) and ``.level_name`` (str) -- ``LabelCentroid`` already has
        both, so it is reused verbatim as the element type, no new type is
        introduced. ``features`` is ``Mapping[str, Sequence[float]]``, each
        sequence the same length and order as ``elements``. ``scored`` names
        the subset of ``features`` keys whose leave-one-out z-scores are
        combined (``max``, per AC5) into ``deviation_score``.

Serialised shape (what ``feature_report.py``/``pipeline.py`` must produce,
pinned by AC8's tests below): ``stage3.per_label_neighbourhood`` -- a list,
sorted ascending by label (matching ``per_label_offsets``/
``per_label_orientations``), of dicts with keys ``label``, ``level_name``,
``window_labels``, ``stats`` (``{feature_name: {"mean":..., "median":...,
"std":..., "z_score":...}}``), ``deviation_score``, ``is_outlier``.

If the builder implements a different surface, this docstring is the
authoritative record of what was actually tested against -- reconcile there,
not here.

Covers Acceptance Criteria AC1-AC13 (AC9b included):

- AC1: ``compute_neighbourhood_features`` takes ``elements`` +
  ``features: Mapping[str, Sequence[float]]``, not three fixed typed args.
- AC2: called with one, three, and five named features, returns per-element
  stats for exactly those features, no code change.
- AC3: ``scored`` is a parameter -- selecting a different subset changes
  which anomaly drives ``deviation_score``.
- AC4: under the default selection, every ``DEFAULT_FEATURES`` name is
  either in ``DEFAULT_SCORED`` or has a non-empty ``UNSCORED_RATIONALE``
  entry.
- AC5: with the three historical features/scored pair, ``deviation_score``/
  ``is_outlier`` match literals pinned from the pre-refactor implementation
  (computed by running the CURRENT, not-yet-refactored code -- see the
  module-level comment above the pinned constants).
- AC6: leave-one-out -- the focal element's own value never enters its own
  z-score's neighbour mean/std.
- AC7: window_n=1 -> score 0.0; a near-zero neighbour std uses the
  documented ``_MIN_STD`` floor; an empty element sequence raises
  ``ValueError``.
- AC8: ``extract_feature_record`` produces ``stage3.per_label_neighbourhood``
  for a multi-label case, sorted by label.
- AC9: fewer than 2 labels -> the block is absent (no ``stage3`` key or no
  ``per_label_neighbourhood`` key), never raises -- matches every other
  Stage 3 sub-block's degrade-on-too-few-labels behaviour.
- AC9b: a realised multi-label report (``run_qc`` + ``serialize_report``,
  which embeds ``stage3.per_label_neighbourhood``) still validates against
  ``report_schema_v0.json``.
- AC10: every new leaf path appears in the realised-record union, in
  ``FEATURE_DOCS``, and exactly once in the regenerated committed catalogue;
  the drift check (item 104's logic, replicated inline over production
  helpers) is clean both directions.
- AC11: entries carry ``status == "unwired"`` in the regenerated catalogue,
  and every corpus case's verdict/findings are unchanged
  (``segfacet.synth.regression.verify_case`` still True for all).
- AC12: ``progress.md``'s Item 024 mentions no longer claim outliers are
  *flagged to a verdict*.
- AC13: regenerating the catalogue (in-memory) and the goldens (into a
  scratch directory) twice each is byte-identical.

Adversarial / edge-case scenarios included: all-identical feature values
(zero std); a NaN feature value; a scored name absent from ``features``;
duplicate names in ``scored``; a window wider than the element sequence.
"""

from __future__ import annotations

import copy
import json
import math
from typing import Dict, List, Tuple

import pytest

from segfacet.features.centroids import LabelCentroid
from segfacet.features.neighbourhood import (
    DEFAULT_FEATURES,
    DEFAULT_SCORED,
    UNSCORED_RATIONALE,
    VertebralNeighbourhood,
    _MIN_STD,
    compute_neighbourhood_features,
)

# =========================================================================== #
# Helpers
# =========================================================================== #

_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _element(label: int, level_name: str) -> LabelCentroid:
    """A minimal element: only ``.label``/``.level_name`` are used by the
    generalised engine; ``centroid_mm``/``centroid_voxel`` are along for the
    ride because ``LabelCentroid`` is reused as the element type verbatim."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=(0.0, 0.0, float(label) * 10.0),
    )


def _uniform_elements(n: int) -> List[LabelCentroid]:
    return [_element(i + 1, _LEVELS[i % len(_LEVELS)]) for i in range(n)]


def _uniform_features(
    n: int, spacing_mm: float = 10.0, offset_mm: float = 0.1, volume_mm3: float = 1000.0
) -> Dict[str, List[float]]:
    return {
        "spacing_mm": [spacing_mm] * n,
        "offset_mm": [offset_mm] * n,
        "volume_mm3": [volume_mm3] * n,
    }


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_public_surface():
    """The named public surface is importable from segfacet.features.neighbourhood."""
    assert callable(compute_neighbourhood_features)
    assert isinstance(DEFAULT_FEATURES, tuple)
    assert isinstance(DEFAULT_SCORED, tuple)
    assert isinstance(UNSCORED_RATIONALE, dict)
    assert VertebralNeighbourhood is not None


# =========================================================================== #
# AC1: named features, not three fixed typed args
# =========================================================================== #


def test_ac1_single_feature_mapping_accepted():
    """AC1: a single named feature ("volume_mm3") is accepted and reported."""
    elements = _uniform_elements(5)
    results = compute_neighbourhood_features(
        elements, {"volume_mm3": [1000.0] * 5}, scored=("volume_mm3",)
    )
    assert len(results) == 5
    for rec in results:
        assert set(rec.stats.keys()) == {"volume_mm3"}


def test_ac1_output_carries_only_the_features_passed_in():
    """AC1: stats keys equal exactly the input features mapping's keys."""
    elements = _uniform_elements(4)
    results = compute_neighbourhood_features(
        elements, {"foo": [1.0, 2.0, 3.0, 4.0]}, scored=("foo",)
    )
    for rec in results:
        assert set(rec.stats.keys()) == {"foo"}


# =========================================================================== #
# AC2: any number of base features works, no code change
# =========================================================================== #


def test_ac2_one_feature():
    elements = _uniform_elements(4)
    results = compute_neighbourhood_features(
        elements, {"a": [1.0, 2.0, 1.0, 2.0]}, scored=("a",)
    )
    for rec in results:
        assert set(rec.stats.keys()) == {"a"}


def test_ac2_three_features():
    elements = _uniform_elements(4)
    features = {
        "a": [1.0, 2.0, 1.0, 2.0],
        "b": [10.0, 20.0, 10.0, 20.0],
        "c": [0.5, 0.6, 0.5, 0.6],
    }
    results = compute_neighbourhood_features(elements, features, scored=("a", "b"))
    for rec in results:
        assert set(rec.stats.keys()) == {"a", "b", "c"}


def test_ac2_five_features():
    elements = _uniform_elements(4)
    features = {name: [float(i) for i in range(4)] for name in ("a", "b", "c", "d", "e")}
    results = compute_neighbourhood_features(elements, features, scored=("a",))
    for rec in results:
        assert set(rec.stats.keys()) == {"a", "b", "c", "d", "e"}


def test_ac2_five_features_each_stat_finite():
    elements = _uniform_elements(6)
    features = {
        name: [float(i) + idx for i in range(6)]
        for idx, name in enumerate(("a", "b", "c", "d", "e"))
    }
    results = compute_neighbourhood_features(elements, features, scored=("a", "b"))
    for rec in results:
        for name, stat in rec.stats.items():
            assert math.isfinite(stat.mean)
            assert math.isfinite(stat.median)
            assert math.isfinite(stat.std)
            assert math.isfinite(stat.z_score)


# =========================================================================== #
# AC3: the scored subset is selectable
# =========================================================================== #


def test_ac3_scored_subset_changes_which_anomaly_is_flagged():
    """AC3: an anomaly in a non-scored feature does not flag; scoring it does."""
    elements = _uniform_elements(7)
    features = {
        "quiet": [1.0] * 7,
        "loud": [1.0] * 7,
    }
    features["loud"][3] = 500.0  # anomalous at index 3

    results_unscored = compute_neighbourhood_features(elements, features, scored=("quiet",))
    assert results_unscored[3].is_outlier is False

    results_scored = compute_neighbourhood_features(elements, features, scored=("loud",))
    assert results_scored[3].is_outlier is True


def test_ac3_scored_is_a_parameter_not_hardcoded():
    """AC3: passing an entirely custom scored tuple works with no default features."""
    elements = _uniform_elements(5)
    features = {"only_one": [1.0, 1.0, 1.0, 1.0, 100.0]}
    results = compute_neighbourhood_features(elements, features, scored=("only_one",))
    assert results[-1].is_outlier is True


# =========================================================================== #
# AC4: reported and scored are reconciled under the default selection
# =========================================================================== #


def test_ac4_every_default_feature_is_scored_or_documented_unscored():
    unscored = set(DEFAULT_FEATURES) - set(DEFAULT_SCORED)
    for name in unscored:
        assert name in UNSCORED_RATIONALE, f"{name!r} is unscored but undocumented"
        assert UNSCORED_RATIONALE[name].strip(), f"empty rationale for {name!r}"


def test_ac4_spacing_mm_is_the_documented_unscored_feature():
    """AC4: spacing_mm is the historically-silent mismatch this item fixes."""
    assert "spacing_mm" in DEFAULT_FEATURES
    assert "spacing_mm" not in DEFAULT_SCORED
    assert "spacing_mm" in UNSCORED_RATIONALE


def test_ac4_default_scored_is_exactly_the_historical_pair():
    assert set(DEFAULT_SCORED) == {"offset_mm", "volume_mm3"}


def test_ac4_default_features_is_exactly_the_historical_three():
    assert set(DEFAULT_FEATURES) == {"spacing_mm", "offset_mm", "volume_mm3"}


# =========================================================================== #
# AC5: default selection reproduces today's (pre-refactor) behaviour
# =========================================================================== #
#
# These literals were captured by running the CURRENT (pre-item-110)
# src/segfacet/features/neighbourhood.py directly against the fixtures below
# (item 024's own _uniform_spine helper), via a one-off script, BEFORE any
# refactor -- not derived from this new API. See the item 110 test-writer's
# return message for the exact script. Reproduced here:
#
#   Fixture A -- n=7, offset_mm=0.1 uniform, vertebra index 3's offset
#   overwritten to 15.0mm, window_n=3 (default), outlier_threshold=2.0:
#     index 0: 0.0            False
#     index 1: 0.0            False
#     index 2: 1.0            False
#     index 3: 14900000.000000002   True
#     index 4: 1.0            False
#     index 5: 0.0            False
#     index 6: 0.0            False
#
#   Fixture B -- n=7, volume_mm3=1000.0 uniform, vertebra index 3's volume
#   overwritten to 3000.0, window_n=3 (default), outlier_threshold=2.0:
#     index 0: 0.0            False
#     index 1: 0.0            False
#     index 2: 1.0            False
#     index 3: 2000000000.0   True
#     index 4: 1.0            False
#     index 5: 0.0            False
#     index 6: 0.0            False
#
#   Fixture C -- n=6, fully uniform (no anomaly), window_n=3 (default):
#     every index: 0.0        False


def _fixture_a_offset_outlier():
    elements = _uniform_elements(7)
    offsets = [0.1] * 7
    offsets[3] = 15.0
    features = {
        "spacing_mm": [10.0] * 7,
        "offset_mm": offsets,
        "volume_mm3": [1000.0] * 7,
    }
    return elements, features


def _fixture_b_volume_outlier():
    elements = _uniform_elements(7)
    volumes = [1000.0] * 7
    volumes[3] = 3000.0
    features = {
        "spacing_mm": [10.0] * 7,
        "offset_mm": [0.1] * 7,
        "volume_mm3": volumes,
    }
    return elements, features


def _fixture_c_no_anomaly():
    elements = _uniform_elements(6)
    features = _uniform_features(6)
    return elements, features


_FIXTURE_A_DEVIATION = [
    0.0, 0.0, 1.0, 14900000.000000002, 1.0, 0.0, 0.0,
]
_FIXTURE_A_OUTLIER = [False, False, False, True, False, False, False]

_FIXTURE_B_DEVIATION = [
    0.0, 0.0, 1.0, 2000000000.0, 1.0, 0.0, 0.0,
]
_FIXTURE_B_OUTLIER = [False, False, False, True, False, False, False]


def test_ac5_fixture_a_deviation_score_parity():
    elements, features = _fixture_a_offset_outlier()
    results = compute_neighbourhood_features(elements, features, scored=DEFAULT_SCORED)
    for rec, expected in zip(results, _FIXTURE_A_DEVIATION):
        assert rec.deviation_score == pytest.approx(expected, rel=1e-9, abs=1e-9), (
            f"label={rec.label}: got {rec.deviation_score!r}, expected {expected!r}"
        )


def test_ac5_fixture_a_is_outlier_parity():
    elements, features = _fixture_a_offset_outlier()
    results = compute_neighbourhood_features(elements, features, scored=DEFAULT_SCORED)
    assert [rec.is_outlier for rec in results] == _FIXTURE_A_OUTLIER


def test_ac5_fixture_b_deviation_score_parity():
    elements, features = _fixture_b_volume_outlier()
    results = compute_neighbourhood_features(elements, features, scored=DEFAULT_SCORED)
    for rec, expected in zip(results, _FIXTURE_B_DEVIATION):
        assert rec.deviation_score == pytest.approx(expected, rel=1e-9, abs=1e-9), (
            f"label={rec.label}: got {rec.deviation_score!r}, expected {expected!r}"
        )


def test_ac5_fixture_b_is_outlier_parity():
    elements, features = _fixture_b_volume_outlier()
    results = compute_neighbourhood_features(elements, features, scored=DEFAULT_SCORED)
    assert [rec.is_outlier for rec in results] == _FIXTURE_B_OUTLIER


def test_ac5_fixture_c_no_anomaly_all_zero():
    elements, features = _fixture_c_no_anomaly()
    results = compute_neighbourhood_features(elements, features, scored=DEFAULT_SCORED)
    for rec in results:
        assert rec.deviation_score == pytest.approx(0.0, abs=1e-9)
        assert rec.is_outlier is False


def test_ac5_default_scored_parameter_matches_explicit_historical_pair():
    """AC5: calling with the default scored= (no override) matches passing
    DEFAULT_SCORED explicitly."""
    elements, features = _fixture_a_offset_outlier()
    results_default = compute_neighbourhood_features(elements, features)
    results_explicit = compute_neighbourhood_features(
        elements, features, scored=DEFAULT_SCORED
    )
    assert [r.deviation_score for r in results_default] == [
        r.deviation_score for r in results_explicit
    ]


# =========================================================================== #
# AC6: leave-one-out semantics preserved
# =========================================================================== #


def test_ac6_focal_own_value_excluded_from_its_z_score_neighbours():
    """AC6: with window_n=3 and elements [0, 0, 100] focused on index 1,
    the leave-one-out neighbour set is {0, 100} (mean 50, std 50), giving
    z_score == 1.0 -- not the naive full-window value that would result if
    the focal's own value polluted its own neighbour statistics."""
    elements = _uniform_elements(3)
    features = {"x": [0.0, 0.0, 100.0]}
    results = compute_neighbourhood_features(elements, features, scored=("x",), window_n=3)
    focal = results[1]
    assert focal.stats["x"].z_score == pytest.approx(1.0, rel=1e-9)


def test_ac6_window_labels_still_include_the_focal_element():
    elements = _uniform_elements(5)
    features = _uniform_features(5)
    results = compute_neighbourhood_features(elements, features)
    for elem, rec in zip(elements, results):
        assert elem.label in rec.window_labels


# =========================================================================== #
# AC7: degenerate windows
# =========================================================================== #


def test_ac7_window_size_one_yields_score_zero():
    elements = _uniform_elements(5)
    features = _uniform_features(5)
    results = compute_neighbourhood_features(elements, features, window_n=1)
    for rec in results:
        assert rec.deviation_score == 0.0
        assert rec.is_outlier is False


def test_ac7_min_std_floor_applied_when_neighbour_std_near_zero():
    """AC7: two identical neighbours (std 0) force the documented _MIN_STD
    floor rather than dividing by zero; z_score == diff / _MIN_STD."""
    elements = _uniform_elements(3)
    focal_value = 5.0 + 50 * _MIN_STD
    features = {"x": [5.0, focal_value, 5.0]}
    results = compute_neighbourhood_features(elements, features, scored=("x",), window_n=3)
    focal = results[1]
    expected_z = abs(focal_value - 5.0) / _MIN_STD
    assert focal.stats["x"].z_score == pytest.approx(expected_z, rel=1e-6)


def test_ac7_empty_sequence_raises_value_error():
    with pytest.raises(ValueError):
        compute_neighbourhood_features([], {"x": []}, scored=("x",))


def test_ac7_empty_sequence_error_message_non_empty():
    with pytest.raises(ValueError) as excinfo:
        compute_neighbourhood_features([], {}, scored=())
    assert str(excinfo.value).strip()


def test_ac7_window_wider_than_sequence_no_crash():
    elements = _uniform_elements(4)
    features = _uniform_features(4)
    results = compute_neighbourhood_features(elements, features, window_n=99)
    assert len(results) == 4
    for rec in results:
        assert isinstance(rec, VertebralNeighbourhood)
        assert math.isfinite(rec.deviation_score)


# =========================================================================== #
# AC8: wired into extract_feature_record and serialised
# =========================================================================== #


def _multi_label_block():
    from segfacet.config import default_config
    from segfacet.pipeline import extract_feature_record

    from synthetic import labelled_blocks_case

    case = labelled_blocks_case()
    return extract_feature_record(case.seg_img, default_config()), case


def test_ac8_multi_label_case_has_per_label_neighbourhood():
    block, case = _multi_label_block()
    assert "stage3" in block
    assert "per_label_neighbourhood" in block["stage3"]
    entries = block["stage3"]["per_label_neighbourhood"]
    assert len(entries) == len(case.expected_labels)


def test_ac8_per_label_neighbourhood_sorted_ascending_by_label():
    block, _case = _multi_label_block()
    entries = block["stage3"]["per_label_neighbourhood"]
    labels = [e["label"] for e in entries]
    assert labels == sorted(labels)


def test_ac8_per_label_neighbourhood_entries_carry_expected_keys():
    block, _case = _multi_label_block()
    entries = block["stage3"]["per_label_neighbourhood"]
    for entry in entries:
        assert set(entry.keys()) >= {
            "label", "level_name", "window_labels", "stats",
            "deviation_score", "is_outlier",
        }
        for name in DEFAULT_FEATURES:
            assert name in entry["stats"]
            assert set(entry["stats"][name].keys()) >= {"mean", "median", "std", "z_score"}


def test_ac8_serialises_json_compatible_values():
    block, _case = _multi_label_block()
    entries = block["stage3"]["per_label_neighbourhood"]
    json.dumps(entries)  # raises TypeError on non-JSON-serialisable content


# =========================================================================== #
# AC9: degrades like Stage 3 siblings on too few labels
# =========================================================================== #


def test_ac9_zero_label_map_no_stage3_key():
    from segfacet.config import default_config
    from segfacet.pipeline import extract_feature_record

    from synthetic import empty_case

    case = empty_case()
    block = extract_feature_record(case.seg_img, default_config())
    assert "stage3" not in block


def test_ac9_single_label_map_no_neighbourhood_key():
    from segfacet.config import default_config
    from segfacet.pipeline import extract_feature_record

    from synthetic import make_labelmap

    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    block = extract_feature_record(seg, default_config())
    # Matches every other Stage 3 sub-block: single-label maps carry no
    # "stage3" key at all (spline fit requires >= 2 points).
    assert "stage3" not in block


def test_ac9_single_label_never_raises():
    from segfacet.config import default_config
    from segfacet.pipeline import extract_feature_record

    from synthetic import make_labelmap

    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})
    extract_feature_record(seg, default_config())  # must not raise


# =========================================================================== #
# AC9b: the report schema admits the new block
# =========================================================================== #


def test_ac9b_multi_label_report_validates_against_schema():
    import importlib.resources

    import jsonschema

    import segfacet as _segfacet_pkg
    from segfacet.config import default_config
    from segfacet.pipeline import run_qc
    from segfacet.report import serialize_report

    from synthetic import labelled_blocks_case

    case = labelled_blocks_case()
    cfg = default_config()
    case_result, features_block = run_qc(case.seg_img, cfg)
    findings = [f.to_dict() for f in case_result.findings]
    report = serialize_report(
        case_result.verdict, "case-110", cfg, features=features_block, findings=findings
    )
    ref = importlib.resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))
    jsonschema.validate(report, schema)  # must not raise
    assert "per_label_neighbourhood" in report["features"]["stage3"]


# =========================================================================== #
# AC10: the catalogue covers the new leaf paths, drift is clean
# =========================================================================== #

_STAT_KEYS = ("mean", "median", "std", "z_score")


def _expected_new_leaf_paths() -> "set[str]":
    paths = {
        "stage3.per_label_neighbourhood[].label",
        "stage3.per_label_neighbourhood[].level_name",
        "stage3.per_label_neighbourhood[].window_labels[]",
        "stage3.per_label_neighbourhood[].deviation_score",
        "stage3.per_label_neighbourhood[].is_outlier",
    }
    for name in DEFAULT_FEATURES:
        for stat in _STAT_KEYS:
            paths.add(f"stage3.per_label_neighbourhood[].stats.{name}.{stat}")
    return paths


def _covered_paths():
    from segfacet.catalogue import iter_driver_records, iter_leaf_paths

    union: set = set()
    for _driver_id, record in iter_driver_records():
        union |= iter_leaf_paths(record)
    return frozenset(union)


def test_ac10_new_leaf_paths_realised():
    realised = _covered_paths()
    for path in _expected_new_leaf_paths():
        assert path in realised, path


def test_ac10_new_leaf_paths_documented():
    from segfacet.feature_docs import FEATURE_DOCS

    for path in _expected_new_leaf_paths():
        assert path in FEATURE_DOCS, path


def test_ac10_drift_direction1_clean_realised_vs_documented():
    """Item 104's direction-1 check (realised-but-undocumented), replicated
    over the real production helpers -- clean once regenerated."""
    from segfacet.feature_docs import FEATURE_DOCS

    realised = _covered_paths()
    documented = frozenset(FEATURE_DOCS)
    assert realised - documented == set()


def test_ac10_drift_direction2_clean_documented_vs_realised():
    from segfacet.feature_docs import FEATURE_DOCS

    realised = _covered_paths()
    documented = frozenset(FEATURE_DOCS)
    assert documented - realised == set()


def test_ac10_committed_catalogue_lists_each_new_path_exactly_once():
    from pathlib import Path

    artifact = Path(__file__).resolve().parent.parent / "docs" / "aide" / "feature_catalogue.generated.json"
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    entries = doc["entries"] if "entries" in doc else [
        e for group in doc["groups"] for e in group.get("entries", [])
    ]
    paths = [e["path"] for e in entries]
    for path in _expected_new_leaf_paths():
        count = paths.count(path)
        assert count == 1, f"{path!r} appears {count} time(s) in the committed catalogue"


# =========================================================================== #
# AC11: status is "unwired", honestly; no rule behaviour changes
# =========================================================================== #


def test_ac11_new_paths_status_unwired_in_committed_catalogue():
    from pathlib import Path

    artifact = Path(__file__).resolve().parent.parent / "docs" / "aide" / "feature_catalogue.generated.json"
    doc = json.loads(artifact.read_text(encoding="utf-8"))
    entries = doc["entries"] if "entries" in doc else [
        e for group in doc["groups"] for e in group.get("entries", [])
    ]
    by_path = {e["path"]: e for e in entries}
    for path in _expected_new_leaf_paths():
        entry = by_path.get(path)
        assert entry is not None, path
        assert entry.get("status") == "unwired", f"{path!r}: status={entry.get('status')!r}"


def test_ac11_corpus_verify_case_unchanged():
    """AC11: every corpus case's verdict/designated-rule outcome is exactly
    what the manifest already expects -- unaffected by the new unwired block."""
    import segfacet.synth  # noqa: F401 -- self-registers every operator
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.regression import verify_case

    cases = load_manifest()["cases"]
    assert cases  # anti-vacuity
    failures = [c["case_id"] for c in cases if not verify_case(c)]
    assert failures == [], f"verify_case failed for: {failures}"


def test_ac11_corpus_findings_rule_ids_unchanged():
    """AC11: every pipeline-detectable case's designated rule fires -- a
    superset check, not exact equality. Item 120's AC23 deliberately adds a
    ``mislabel`` finding to ``mode6_crop_at_border`` (its cropped centroid
    genuinely sits 17.507 mm off the fitted curve) while that case's
    ``expected_rule_ids`` in the manifest names only its designated rule,
    ``border``. Exact-equality would fail on that one case for a reason
    unrelated to item 110's own wiring, so the assertion is relaxed to
    "the designated rule(s) fire", which is item 110's actual intent, and
    still catches a designated rule that stops firing."""
    import segfacet.synth  # noqa: F401
    from segfacet.config import bundled_default_config
    from segfacet.synth.corpus import load_manifest
    from segfacet.synth.regression import pipeline_findings

    cfg = bundled_default_config()
    for case in load_manifest()["cases"]:
        if case["detection"] != "pipeline":
            continue
        findings = pipeline_findings(case, cfg)
        rule_ids = {f.rule_id for f in findings}
        assert set(case["expected_rule_ids"]) <= rule_ids, case["case_id"]


# =========================================================================== #
# AC12: progress.md's Item 024 claim matches reality
# =========================================================================== #


def _progress_item024_lines():
    from pathlib import Path

    progress = Path(__file__).resolve().parent.parent / "docs" / "aide" / "progress.md"
    text = progress.read_text(encoding="utf-8")
    return [line for line in text.splitlines() if "Item 024" in line]


def test_ac12_progress_still_references_item_024():
    assert _progress_item024_lines()


def test_ac12_progress_no_longer_claims_outliers_flagged_to_verdict():
    combined = "\n".join(_progress_item024_lines())
    assert "flags isolated anatomical outliers" not in combined, (
        "progress.md still claims outlier-flagging behaviour that no rule "
        "has ever consumed"
    )


def test_ac12_progress_describes_unwired_status():
    combined = "\n".join(_progress_item024_lines()).lower()
    assert (
        "unwired" in combined
        or "no rule" in combined
        or "not consumed" in combined
        or "consumed by no rule" in combined
    ), f"expected an honest 'unwired'/'no rule consumes it' description, got: {combined!r}"


# =========================================================================== #
# AC13: regeneration is deterministic
# =========================================================================== #


def test_ac13_catalogue_regeneration_byte_identical_twice():
    from segfacet.catalogue import build_catalogue, catalogue_to_dict, render_markdown

    cat1 = build_catalogue(strict=True)
    cat2 = build_catalogue(strict=True)
    json1 = json.dumps(catalogue_to_dict(cat1), indent=2, sort_keys=True, ensure_ascii=False)
    json2 = json.dumps(catalogue_to_dict(cat2), indent=2, sort_keys=True, ensure_ascii=False)
    assert json1 == json2
    assert render_markdown(cat1) == render_markdown(cat2)


def test_ac13_golden_regeneration_byte_identical_twice(tmp_path):
    import segfacet.synth  # noqa: F401
    from segfacet.synth.golden import write_goldens

    dest1 = tmp_path / "run1"
    dest2 = tmp_path / "run2"
    write_goldens(dest=dest1)
    write_goldens(dest=dest2)
    files1 = sorted(dest1.iterdir())
    files2 = sorted(dest2.iterdir())
    assert [p.name for p in files1] == [p.name for p in files2]
    for p1, p2 in zip(files1, files2):
        assert p1.read_bytes() == p2.read_bytes(), p1.name


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_all_identical_feature_values_zero_std():
    elements = _uniform_elements(5)
    features = {"x": [7.0] * 5}
    results = compute_neighbourhood_features(elements, features, scored=("x",))
    for rec in results:
        assert rec.stats["x"].std == pytest.approx(0.0, abs=1e-12)
        assert rec.deviation_score == pytest.approx(0.0, abs=1e-9)
        assert rec.is_outlier is False


def test_adv_nan_feature_value_raises_value_error():
    elements = _uniform_elements(4)
    features = {"x": [1.0, float("nan"), 1.0, 1.0]}
    with pytest.raises(ValueError):
        compute_neighbourhood_features(elements, features, scored=("x",))


def test_adv_scored_name_absent_from_features_raises_clear_error():
    elements = _uniform_elements(4)
    features = {"x": [1.0, 2.0, 3.0, 4.0]}
    with pytest.raises(ValueError) as excinfo:
        compute_neighbourhood_features(elements, features, scored=("y",))
    assert "y" in str(excinfo.value)


def test_adv_duplicate_scored_names_do_not_crash_and_match_deduped():
    elements = _uniform_elements(5)
    features = {"x": [1.0, 1.0, 1.0, 1.0, 100.0]}
    results_dup = compute_neighbourhood_features(elements, features, scored=("x", "x"))
    results_plain = compute_neighbourhood_features(elements, features, scored=("x",))
    assert [r.deviation_score for r in results_dup] == [
        r.deviation_score for r in results_plain
    ]


def test_adv_window_wider_than_sequence_all_elements_in_every_window():
    elements = _uniform_elements(3)
    features = _uniform_features(3)
    results = compute_neighbourhood_features(elements, features, window_n=50)
    for rec in results:
        assert len(rec.window_labels) == 3


def test_adv_input_elements_and_features_not_mutated():
    elements = _uniform_elements(5)
    features = _uniform_features(5)
    elements_snapshot = list(elements)
    features_snapshot = copy.deepcopy(features)
    compute_neighbourhood_features(elements, features)
    assert elements == elements_snapshot
    assert features == features_snapshot


def test_adv_is_outlier_is_python_bool():
    elements = _uniform_elements(4)
    features = _uniform_features(4)
    results = compute_neighbourhood_features(elements, features)
    for rec in results:
        assert isinstance(rec.is_outlier, bool)


def test_adv_frozen_dataclass_immutable():
    elements = _uniform_elements(3)
    features = _uniform_features(3)
    rec = compute_neighbourhood_features(elements, features)[0]
    with pytest.raises(Exception):
        rec.deviation_score = 999.0  # type: ignore[misc]
