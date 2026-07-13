"""Tests for item 064 -- level-aware intensity delta-to-reference computation
(``segqc.reference.delta.compute_intensity_reference_delta``).

Covers Acceptance Criteria AC1-AC11 (Group A -- the compute half):

- AC1: compute_reference_delta (geometry) is unchanged and intensity-inert.
- AC2: compute_intensity_reference_delta scores each label's intensity value
  against its own level.
- AC3: the feature value equals the image_features first-order value.
- AC4: the lookup is level-aware.
- AC5: an out-of-band intensity value flags out-of-range.
- AC6: a large deviation yields a large robust-z and RMS distribution
  distance.
- AC7: a label whose level (or stratum) is absent from the reference is
  available: false.
- AC8: a reference with no intensity distributions yields empty intensity
  features.
- AC9: a missing/None first-order value contributes no feature.
- AC10: an unavailable image_features block yields no intensity scores.
- AC11: compute_intensity_reference_delta is deterministic and non-mutating.

Adversarial / edge-case scenarios included:
- Empty per_label features_block -> empty per_label result.
- Value exactly on a percentile bound is in-range; just past it is
  out-of-range.
- Level-aware isolation: the same value scored against two levels gives
  opposite out-of-range verdicts (AC4 positive+negative in one test).
- Mixed sentinel/populated first-order values within a single label.
- Determinism / non-mutation via deep-copy comparison, including the
  reference and image_features inputs.
- A genuine 061-shaped image_features block built via
  build_image_features_block(compute_intensity_features(...)) over a real
  painted synthetic scan, joined against a real geometric features_block.
"""

from __future__ import annotations

import copy
import json

import pytest

from segqc.feature_report import build_image_features_block
from segqc.features.intensity import LabelIntensity
from segqc.reference import (
    ALL_STRATUM,
    DEFAULT_PERCENTILES,
    IQR_TO_SIGMA,
    SCHEMA_VERSION,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
    compute_reference_delta,
    reference_delta_to_dict,
)
from segqc.reference.delta import (
    INTENSITY_FEATURE_PREFIX,
    compute_intensity_reference_delta,
)


# =========================================================================== #
# Hand-built reference fixtures
# =========================================================================== #

PROV = Provenance(
    source="test-cohort-064", config_hash="cfg-hash-064", build_date="2000-01-01",
    size_proxy_name=None,
)

# L1's intensity_median band: mean 200, std 30, symmetric percentile grid.
INTENSITY_MEDIAN_L1 = FeatureStats(
    count=10, mean=200.0, std=30.0, min=100.0, max=300.0,
    percentiles={
        "p1": 110.0, "p5": 130.0, "p25": 180.0, "p50": 200.0,
        "p75": 220.0, "p95": 270.0, "p99": 290.0,
    },
)

# A second, independently-scaled intensity feature tracked alongside
# intensity_median (for the multi-feature RMS distribution_distance test).
INTENSITY_MEAN_L1 = FeatureStats(
    count=10, mean=195.0, std=25.0, min=100.0, max=290.0,
    percentiles={
        "p1": 115.0, "p5": 135.0, "p25": 175.0, "p50": 195.0,
        "p75": 215.0, "p95": 260.0, "p99": 280.0,
    },
)

# L2's intensity_median band: a disjoint, much lower range than L1's -- used
# to prove the lookup is level-aware (AC4).
INTENSITY_MEDIAN_L2 = FeatureStats(
    count=10, mean=50.0, std=8.0, min=20.0, max=80.0,
    percentiles={
        "p1": 22.0, "p5": 26.0, "p25": 40.0, "p50": 50.0,
        "p75": 60.0, "p95": 74.0, "p99": 78.0,
    },
)

# A geometry feature, for the AC1 intensity-inertness check.
PHYSICAL_VOLUME_STATS = FeatureStats(
    count=10, mean=50.0, std=20.0, min=0.0, max=100.0,
    percentiles={
        "p1": 10.0, "p5": 20.0, "p25": 40.0, "p50": 50.0,
        "p75": 60.0, "p95": 80.0, "p99": 90.0,
    },
)


def _build_reference(levels, *, stratum=ALL_STRATUM, features=None):
    """``levels`` is a mapping ``level_name -> {feature_name: FeatureStats}``."""
    level_map = {}
    all_names = set()
    for level_name, feature_stats in levels.items():
        level_map[level_name] = {
            stratum: LevelDistribution(
                level_name=level_name, stratum=stratum, record_count=10,
                feature_stats=dict(feature_stats),
            )
        }
        all_names.update(feature_stats.keys())
    if features is None:
        features = tuple(sorted(all_names))
    return ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=PROV,
        features=features,
        percentiles=DEFAULT_PERCENTILES,
        subject_count=10,
        strata=(stratum,),
        levels=level_map,
    )


def _two_level_reference():
    return _build_reference({
        "L1": {"intensity_median": INTENSITY_MEDIAN_L1, "intensity_mean": INTENSITY_MEAN_L1},
        "L2": {"intensity_median": INTENSITY_MEDIAN_L2},
    })


def _single_feature_reference():
    return _build_reference({"L1": {"intensity_median": INTENSITY_MEDIAN_L1}})


def _geometry_only_reference():
    """A reference carrying only a geometric feature -- no intensity_*
    distributions at all (AC8's backward-compatibility fixture)."""
    return _build_reference({"L1": {"physical_volume_mm3": PHYSICAL_VOLUME_STATS}})


def _mixed_reference():
    """A reference carrying both a geometry feature and an intensity feature
    for the same level (AC1's intensity-inertness fixture)."""
    return _build_reference({
        "L1": {
            "physical_volume_mm3": PHYSICAL_VOLUME_STATS,
            "intensity_median": INTENSITY_MEDIAN_L1,
        },
    })


def _features_block(entries):
    """``entries`` is a list of ``(label, level_name)``. Mirrors item 046's
    ``_features_block`` join surface but only carries what the intensity
    compute function reads: label + level_name (plus a geometry stub so the
    fixture doubles as a valid geometric features_block for AC1)."""
    per_label = {}
    for entry in entries:
        label, level_name = entry[0], entry[1]
        geometry = entry[2] if len(entry) > 2 else {}
        per_label[str(label)] = {
            "label": label, "level_name": level_name, "geometry": dict(geometry),
        }
    return {"per_label": per_label}


def _image_features(intensity_by_label, *, available=True):
    return build_image_features_block(intensity_by_label, available=available)


def _label_intensity(**overrides):
    fields = dict(
        voxel_count=500, n_nonfinite_excluded=0,
        mean=200.0, median=200.0, std=30.0, min=140.0, max=260.0,
        p05=150.0, p25=180.0, p50=200.0, p75=220.0, p95=250.0,
        range=120.0, iqr=40.0, entropy=3.0,
    )
    fields.update(overrides)
    return LabelIntensity(**fields)


def _feature_delta(label_delta, feature_name):
    for fd in label_delta.features:
        if fd.feature == feature_name:
            return fd
    raise AssertionError(f"{feature_name} not present in {label_delta.features!r}")


def _expected_robust_z(value, stats):
    iqr = stats.percentiles["p75"] - stats.percentiles["p25"]
    return None if iqr == 0 else (value - stats.percentiles["p50"]) / (iqr / IQR_TO_SIGMA)


# =========================================================================== #
# AC1: compute_reference_delta (geometry) is unchanged and intensity-inert
# =========================================================================== #


def test_ac1_geometric_compute_is_intensity_inert():
    reference = _mixed_reference()
    block = _features_block([(20, "L1", {"physical_volume_mm3": 50.0})])

    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[20]

    feature_names = {fd.feature for fd in label_delta.features}
    assert "physical_volume_mm3" in feature_names
    assert not any(name.startswith(INTENSITY_FEATURE_PREFIX) for name in feature_names)
    assert not any(
        name.startswith(INTENSITY_FEATURE_PREFIX)
        for name in label_delta.out_of_range_features
    )


def test_ac1_intensity_feature_prefix_constant():
    assert INTENSITY_FEATURE_PREFIX == "intensity_"


# =========================================================================== #
# AC2: each label's intensity value is scored against its own level
# =========================================================================== #


def test_ac2_label_scored_against_its_own_level():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity(median=200.0)})  # == p50

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]

    assert label_delta.available is True
    assert len(label_delta.features) == 1
    fd = label_delta.features[0]
    assert fd.feature == "intensity_median"
    assert fd.out_of_range is False
    assert fd.robust_z == pytest.approx(0.0)


# =========================================================================== #
# AC3: the feature value equals the image_features first-order value
# =========================================================================== #


def test_ac3_feature_value_equals_first_order_value_with_prefix_stripped():
    reference = _two_level_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity(median=213.0, mean=201.5)})

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]

    fd_median = _feature_delta(label_delta, "intensity_median")
    fd_mean = _feature_delta(label_delta, "intensity_mean")
    assert fd_median.value == pytest.approx(213.0)
    assert fd_mean.value == pytest.approx(201.5)


# =========================================================================== #
# AC4: the lookup is level-aware
# =========================================================================== #


def test_ac4_same_value_scored_against_two_levels_gives_opposite_verdicts():
    reference = _two_level_reference()
    image_features = _image_features({20: _label_intensity(median=205.0)})

    block_level_a = _features_block([(20, "L1")])
    delta_a = compute_intensity_reference_delta(block_level_a, image_features, reference)
    fd_a = _feature_delta(delta_a.per_label[20], "intensity_median")
    assert fd_a.out_of_range is False  # inside L1's band (p1=110..p99=290)

    block_level_b = _features_block([(20, "L2")])
    delta_b = compute_intensity_reference_delta(block_level_b, image_features, reference)
    fd_b = _feature_delta(delta_b.per_label[20], "intensity_median")
    assert fd_b.out_of_range is True  # far outside L2's band (p1=22..p99=78)


# =========================================================================== #
# AC5: an out-of-band intensity value flags out-of-range
# =========================================================================== #


def test_ac5_out_of_band_value_flags_out_of_range_and_is_listed():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity(median=1000.0)})  # >> p99 (290)

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]
    fd = _feature_delta(label_delta, "intensity_median")

    assert fd.out_of_range is True
    assert label_delta.out_of_range_features == ("intensity_median",)


# =========================================================================== #
# AC6: a large deviation yields a large robust-z and RMS distribution
# distance
# =========================================================================== #


def test_ac6_large_deviation_yields_large_robust_z_and_rms_distance():
    reference = _two_level_reference()
    block = _features_block([(20, "L1")])
    median_value = 1000.0
    mean_value = 210.0
    image_features = _image_features(
        {20: _label_intensity(median=median_value, mean=mean_value)}
    )

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]
    fd_median = _feature_delta(label_delta, "intensity_median")
    fd_mean = _feature_delta(label_delta, "intensity_mean")

    expected_rz_median = _expected_robust_z(median_value, INTENSITY_MEDIAN_L1)
    expected_rz_mean = _expected_robust_z(mean_value, INTENSITY_MEAN_L1)
    assert fd_median.robust_z == pytest.approx(expected_rz_median)
    assert fd_median.robust_z > 10.0
    assert fd_mean.robust_z == pytest.approx(expected_rz_mean)

    expected_rms = (
        (expected_rz_median ** 2 + expected_rz_mean ** 2) / 2.0
    ) ** 0.5
    assert label_delta.distribution_distance == pytest.approx(expected_rms)


# =========================================================================== #
# AC7: a label whose level (or stratum) is absent from the reference is
# available: false
# =========================================================================== #


def test_ac7_absent_level_yields_unavailable_not_a_crash():
    reference = _single_feature_reference()
    block = _features_block([(99, "UNKNOWN")])
    image_features = _image_features({99: _label_intensity()})

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[99]

    assert label_delta.available is False
    assert label_delta.features == ()
    assert label_delta.distribution_distance is None
    assert label_delta.out_of_range_features == ()


def test_ac7_absent_stratum_yields_unavailable_not_a_crash():
    reference = _single_feature_reference()  # only carries stratum "all"
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity()})

    delta = compute_intensity_reference_delta(
        block, image_features, reference, stratum="s1"
    )
    assert delta.per_label[20].available is False

    delta_default = compute_intensity_reference_delta(block, image_features, reference)
    assert delta_default.per_label[20].available is True


# =========================================================================== #
# AC8: a reference with no intensity distributions yields empty intensity
# features
# =========================================================================== #


def test_ac8_geometry_only_reference_yields_empty_intensity_features():
    reference = _geometry_only_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity()})

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]

    assert label_delta.available is True
    assert label_delta.features == ()
    assert label_delta.distribution_distance is None
    assert label_delta.out_of_range_features == ()


# =========================================================================== #
# AC9: a missing/None first-order value contributes no feature
# =========================================================================== #


def test_ac9_none_first_order_value_omits_that_feature_but_scores_siblings():
    reference = _two_level_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features(
        {20: _label_intensity(median=None, mean=201.0)}
    )

    delta = compute_intensity_reference_delta(block, image_features, reference)
    label_delta = delta.per_label[20]
    feature_names = {fd.feature for fd in label_delta.features}

    assert "intensity_median" not in feature_names
    assert "intensity_mean" in feature_names


def test_ac9_sentinel_label_intensity_yields_no_intensity_features():
    reference = _two_level_reference()
    block = _features_block([(20, "L1")])
    sentinel = LabelIntensity(
        voxel_count=0, n_nonfinite_excluded=5,
        mean=None, median=None, std=None, min=None, max=None,
        p05=None, p25=None, p50=None, p75=None, p95=None,
        range=None, iqr=None, entropy=None,
    )
    image_features = _image_features({20: sentinel})

    delta = compute_intensity_reference_delta(block, image_features, reference)
    assert delta.per_label[20].features == ()
    assert delta.per_label[20].distribution_distance is None


# =========================================================================== #
# AC10: an unavailable image_features block yields no intensity scores
# =========================================================================== #


def test_ac10_absent_image_features_yields_no_intensity_scores():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])

    delta = compute_intensity_reference_delta(block, None, reference)
    assert delta.per_label[20].features == ()


def test_ac10_non_mapping_image_features_yields_no_intensity_scores():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])

    delta = compute_intensity_reference_delta(block, ["not", "a", "mapping"], reference)
    assert delta.per_label[20].features == ()


def test_ac10_unavailable_image_features_yields_no_intensity_scores():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features({20: _label_intensity()}, available=False)

    delta = compute_intensity_reference_delta(block, image_features, reference)
    assert delta.per_label[20].features == ()
    # must not raise, and the label is still processed (level-available).
    assert delta.per_label[20].available is True


# =========================================================================== #
# AC11: computation is deterministic and non-mutating
# =========================================================================== #


def test_ac11_deterministic_and_non_mutating():
    reference = _two_level_reference()
    block = _features_block([(20, "L1")])
    image_features = _image_features(
        {20: _label_intensity(median=213.0, mean=201.5)}
    )

    block_before = copy.deepcopy(block)
    reference_before = copy.deepcopy(reference)
    image_features_before = copy.deepcopy(image_features)

    delta1 = compute_intensity_reference_delta(block, image_features, reference)
    delta2 = compute_intensity_reference_delta(block, image_features, reference)

    assert delta1 == delta2

    text1 = json.dumps(reference_delta_to_dict(delta1), sort_keys=True)
    text2 = json.dumps(reference_delta_to_dict(delta2), sort_keys=True)
    assert text1 == text2

    assert block == block_before
    assert reference == reference_before
    assert image_features == image_features_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_features_block_yields_empty_per_label():
    reference = _two_level_reference()
    block = _features_block([])
    image_features = _image_features({})

    delta = compute_intensity_reference_delta(block, image_features, reference)
    assert delta.per_label == {}

    delta_dict = reference_delta_to_dict(delta)
    assert delta_dict["per_label"] == {}
    json.dumps(delta_dict)  # must not raise


def test_adv_value_exactly_on_bound_is_in_range_just_past_is_out():
    reference = _single_feature_reference()
    block = _features_block([(20, "L1")])
    p1 = INTENSITY_MEDIAN_L1.percentiles["p1"]

    image_on_bound = _image_features({20: _label_intensity(median=p1)})
    delta_on_bound = compute_intensity_reference_delta(block, image_on_bound, reference)
    fd_on_bound = _feature_delta(delta_on_bound.per_label[20], "intensity_median")
    assert fd_on_bound.out_of_range is False

    image_below_bound = _image_features({20: _label_intensity(median=p1 - 0.0001)})
    delta_below_bound = compute_intensity_reference_delta(
        block, image_below_bound, reference
    )
    fd_below_bound = _feature_delta(delta_below_bound.per_label[20], "intensity_median")
    assert fd_below_bound.out_of_range is True


def test_adv_mixed_sentinel_and_populated_labels_in_one_block():
    reference = _two_level_reference()
    block = _features_block([(20, "L1"), (21, "L1")])
    sentinel = LabelIntensity(
        voxel_count=0, n_nonfinite_excluded=5,
        mean=None, median=None, std=None, min=None, max=None,
        p05=None, p25=None, p50=None, p75=None, p95=None,
        range=None, iqr=None, entropy=None,
    )
    image_features = _image_features(
        {20: sentinel, 21: _label_intensity(median=205.0, mean=201.0)}
    )

    delta = compute_intensity_reference_delta(block, image_features, reference)
    assert delta.per_label[20].features == ()
    assert len(delta.per_label[21].features) == 2


def test_adv_determinism_non_mutation_via_deep_copy_comparison():
    reference = _two_level_reference()
    block = _features_block([(20, "L1"), (21, "L2")])
    image_features = _image_features(
        {20: _label_intensity(median=205.0), 21: _label_intensity(median=55.0)}
    )
    block_snapshot = copy.deepcopy(block)
    reference_snapshot = copy.deepcopy(reference)
    image_features_snapshot = copy.deepcopy(image_features)

    compute_intensity_reference_delta(block, image_features, reference)

    assert block == block_snapshot
    assert reference == reference_snapshot
    assert image_features == image_features_snapshot


def test_adv_real_061_shaped_block_composes_over_a_painted_synthetic_scan():
    """One integration-flavoured test confirming the genuine 061 shape (built
    via build_image_features_block(compute_intensity_features(...)) over a
    real painted scan) is consumed correctly, joined against a real
    geometric features_block from extract_feature_record."""
    from segqc.config import bundled_default_config
    from segqc.features.intensity import compute_intensity_features
    from segqc.pipeline import extract_feature_record
    from segqc.synth.clean_gt import build_clean_spine
    from segqc.synth.intensity import paint_clean_scan

    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    config = bundled_default_config()

    geo_block = extract_feature_record(spine.seg_img, config)
    intensity_by_label = compute_intensity_features(scan_img, spine.seg_img)
    image_features = build_image_features_block(intensity_by_label)

    reference = _two_level_reference()  # only carries "L1"/"L2" -- fine, AC7 path
    delta = compute_intensity_reference_delta(geo_block, image_features, reference)
    reference_delta_to_dict(delta)  # must serialise without raising

    present_labels = {int(entry["label"]) for entry in geo_block["per_label"].values()}
    assert set(delta.per_label.keys()) == present_labels
