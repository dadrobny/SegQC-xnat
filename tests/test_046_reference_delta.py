"""Tests for item 046 -- delta-to-reference feature computation
(``src/segfacet/reference/delta.py``).

Covers Acceptance Criteria AC1-AC15:

- AC1: a case value equal to the reference mean yields z_score == 0.0 and
  in-range.
- AC2: a case value equal to the reference median yields robust_z == 0.0 and
  percentile_rank == 50.0.
- AC3: a far upper-tail value yields a large positive z, top percentile, and
  out-of-range.
- AC4: a far lower-tail value yields a large negative z, bottom percentile,
  and out-of-range.
- AC5: percentile_rank interpolates over the stored grid (exact at anchors,
  strictly between adjacent anchors otherwise, monotonic non-decreasing).
- AC6: a degenerate reference (std == 0 / IQR == 0) yields null z, not
  NaN/inf.
- AC7: out_of_range honours the configurable bound percentiles.
- AC8: distribution_distance is the RMS of the defined robust-z values.
- AC9: a level absent from the reference yields available == False, not a
  crash.
- AC10: a tracked feature absent from the case block is omitted, not
  fabricated.
- AC11: the serialised block validates against the extended report schema.
- AC12: the block metadata carries reference provenance.
- AC13: a stratum absent for a level yields available == False.
- AC14: an out-of-grid bound percentile raises ValueError.
- AC15: computation is deterministic and non-mutating.

Adversarial / edge-case scenarios included:
- Empty case (per_label == {}).
- Value exactly on a bound is in-range; just below is out-of-range.
- All-features-degenerate label: distribution_distance is None but
  percentile_rank/out_of_range remain defined; no NaN/Infinity in JSON.
- A feature the reference tracks but a level's feature_stats omits is
  skipped for that label, without error.
- Determinism / non-mutation via deep-copy comparison.
- Schema round-trip: json.dumps/json.loads is unchanged; a null z_score
  still validates.
- Flat-segment percentile tie-break returns the lower rank.
- Bundled default reference smoke test over a real extracted case.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

from segfacet.config import bundled_default_config
from segfacet.reference import (
    ALL_STRATUM,
    DEFAULT_PERCENTILES,
    SCHEMA_VERSION,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
    bundled_default_reference,
    compute_reference_delta,
    reference_delta_to_dict,
    DEFAULT_LOWER_PCT,
    DEFAULT_UPPER_PCT,
    IQR_TO_SIGMA,
    REFERENCE_DELTA_VERSION,
)
from segfacet.pipeline import extract_feature_record
from segfacet.report import serialize_report
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.verdict import Verdict


# =========================================================================== #
# Hand-built reference fixtures
# =========================================================================== #

PROV = Provenance(
    source="test-cohort-046", config_hash="cfg-hash-046", build_date="2000-01-01",
    size_proxy_name=None,
)

# A "normal" feature: mean 50, std 20, symmetric percentile grid 0..100.
PHYSICAL_VOLUME_STATS = FeatureStats(
    count=10, mean=50.0, std=20.0, min=0.0, max=100.0,
    percentiles={
        "p1": 10.0, "p5": 20.0, "p25": 40.0, "p50": 50.0,
        "p75": 60.0, "p95": 80.0, "p99": 90.0,
    },
)

# A second, independently-scaled "normal" feature (for the multi-feature
# distribution_distance RMS test).
EXTENT_X_STATS = FeatureStats(
    count=10, mean=10.0, std=4.0, min=2.0, max=18.0,
    percentiles={
        "p1": 3.0, "p5": 4.0, "p25": 8.0, "p50": 10.0,
        "p75": 12.0, "p95": 16.0, "p99": 17.0,
    },
)

# A degenerate constant feature: std == 0 (and IQR == 0 too).
EXTENT_Y_CONST_STATS = FeatureStats(
    count=5, mean=7.0, std=0.0, min=7.0, max=7.0,
    percentiles={f"p{n}": 7.0 for n in DEFAULT_PERCENTILES},
)

# A skewed feature: std != 0 but IQR == 0 (p25 == p50 == p75).
EXTENT_Z_SKEWED_STATS = FeatureStats(
    count=5, mean=6.0, std=3.0, min=1.0, max=20.0,
    percentiles={
        "p1": 1.0, "p5": 2.0, "p25": 5.0, "p50": 5.0,
        "p75": 5.0, "p95": 15.0, "p99": 19.0,
    },
)

SPLINE_OFFSET_STATS = FeatureStats(
    count=10, mean=2.0, std=1.0, min=0.0, max=5.0,
    percentiles={
        "p1": 0.2, "p5": 0.5, "p25": 1.2, "p50": 2.0,
        "p75": 2.8, "p95": 3.6, "p99": 4.5,
    },
)

FULL_FEATURE_STATS = {
    "physical_volume_mm3": PHYSICAL_VOLUME_STATS,
    "extent_x_mm": EXTENT_X_STATS,
    "extent_y_mm": EXTENT_Y_CONST_STATS,
    "extent_z_mm": EXTENT_Z_SKEWED_STATS,
    "spline_offset_mm": SPLINE_OFFSET_STATS,
}


def _reference(feature_stats, *, level_name="L1", stratum=ALL_STRATUM):
    """Build a minimal ReferenceDistribution with one level/stratum carrying
    ``feature_stats`` (only stratum "all" is populated -- AC13/adv exercise a
    stratum request the reference never carries)."""
    level = LevelDistribution(
        level_name=level_name, stratum=stratum, record_count=10,
        feature_stats=dict(feature_stats),
    )
    features = tuple(sorted(feature_stats.keys()))
    return ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=PROV,
        features=features,
        percentiles=DEFAULT_PERCENTILES,
        subject_count=10,
        strata=(stratum,),
        levels={level_name: {stratum: level}},
    )


def _full_reference():
    return _reference(FULL_FEATURE_STATS)


def _features_block(entries, stage3_offsets=None):
    """``entries`` is a list of ``(label, level_name, geometry_dict)``."""
    per_label = {}
    for label, level_name, geometry in entries:
        per_label[str(label)] = {
            "label": label, "level_name": level_name, "geometry": dict(geometry),
        }
    block = {"per_label": per_label}
    if stage3_offsets is not None:
        block["stage3"] = {
            "per_label_offsets": [dict(o) for o in stage3_offsets]
        }
    return block


def _expected_z(value, stats):
    return None if stats.std == 0 else (value - stats.mean) / stats.std


def _expected_robust_z(value, stats):
    iqr = stats.percentiles["p75"] - stats.percentiles["p25"]
    return None if iqr == 0 else (value - stats.percentiles["p50"]) / (iqr / IQR_TO_SIGMA)


def _feature_delta(label_delta, feature_name):
    for fd in label_delta.features:
        if fd.feature == feature_name:
            return fd
    raise AssertionError(f"{feature_name} not present in {label_delta.features!r}")


# =========================================================================== #
# AC1: value == mean -> z_score == 0.0, in-range
# =========================================================================== #


def test_ac1_value_equal_to_mean_yields_zero_z_score_and_in_range():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": PHYSICAL_VOLUME_STATS.mean}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "physical_volume_mm3")
    assert fd.z_score == pytest.approx(0.0)
    assert fd.out_of_range is False


# =========================================================================== #
# AC2: value == median -> robust_z == 0.0, percentile_rank == 50.0
# =========================================================================== #


def test_ac2_value_equal_to_median_yields_zero_robust_z_and_rank_50():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": PHYSICAL_VOLUME_STATS.percentiles["p50"]}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "physical_volume_mm3")
    assert fd.robust_z == pytest.approx(0.0)
    assert fd.percentile_rank == pytest.approx(50.0)


# =========================================================================== #
# AC3: far upper tail -> large positive z, rank 100.0, out-of-range
# =========================================================================== #


def test_ac3_far_upper_tail_value_yields_large_positive_z_top_rank_and_oor():
    reference = _full_reference()
    value = 100000.0  # >> max (100.0) and >> p99 (90.0)
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": value}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "physical_volume_mm3")
    assert fd.z_score == pytest.approx(_expected_z(value, PHYSICAL_VOLUME_STATS))
    assert fd.z_score > 10.0
    assert fd.robust_z == pytest.approx(_expected_robust_z(value, PHYSICAL_VOLUME_STATS))
    assert fd.robust_z > 10.0
    assert fd.percentile_rank == pytest.approx(100.0)
    assert fd.out_of_range is True


# =========================================================================== #
# AC4: far lower tail -> large negative z, rank 0.0, out-of-range
# =========================================================================== #


def test_ac4_far_lower_tail_value_yields_large_negative_z_bottom_rank_and_oor():
    reference = _full_reference()
    value = -100000.0  # << min (0.0) and << p1 (10.0)
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": value}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "physical_volume_mm3")
    assert fd.z_score == pytest.approx(_expected_z(value, PHYSICAL_VOLUME_STATS))
    assert fd.z_score < -10.0
    assert fd.percentile_rank == pytest.approx(0.0)
    assert fd.out_of_range is True


# =========================================================================== #
# AC5: percentile_rank interpolates over the stored grid
# =========================================================================== #


def test_ac5_percentile_rank_exact_at_anchor_and_monotonic_between():
    reference = _full_reference()
    stats = PHYSICAL_VOLUME_STATS

    block_anchor = _features_block([
        (20, "L1", {"physical_volume_mm3": stats.percentiles["p25"]}),
    ])
    delta_anchor = compute_reference_delta(block_anchor, reference)
    fd_anchor = _feature_delta(delta_anchor.per_label[20], "physical_volume_mm3")
    assert fd_anchor.percentile_rank == pytest.approx(25.0)

    # A value strictly between p25 (40.0, rank 25) and p50 (50.0, rank 50)
    # returns a rank strictly between 25 and 50.
    mid_value = (stats.percentiles["p25"] + stats.percentiles["p50"]) / 2.0
    block_mid = _features_block([
        (20, "L1", {"physical_volume_mm3": mid_value}),
    ])
    delta_mid = compute_reference_delta(block_mid, reference)
    fd_mid = _feature_delta(delta_mid.per_label[20], "physical_volume_mm3")
    assert 25.0 < fd_mid.percentile_rank < 50.0

    # Monotonic non-decreasing across three increasing values.
    ranks = []
    for v in (stats.min, stats.percentiles["p25"], stats.percentiles["p50"], stats.max):
        block = _features_block([(20, "L1", {"physical_volume_mm3": v})])
        d = compute_reference_delta(block, reference)
        ranks.append(_feature_delta(d.per_label[20], "physical_volume_mm3").percentile_rank)
    assert ranks == sorted(ranks)


# =========================================================================== #
# AC6: degenerate reference (std == 0 / IQR == 0) yields null z, not NaN/inf
# =========================================================================== #


def test_ac6_std_zero_yields_null_z_score_not_nan_or_inf():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"extent_y_mm": 7.0}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "extent_y_mm")
    assert fd.z_score is None

    text = json.dumps(reference_delta_to_dict(delta), allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text


def test_ac6_iqr_zero_yields_null_robust_z_not_nan_or_inf():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"extent_z_mm": 9.0}),
    ])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "extent_z_mm")
    assert fd.robust_z is None
    # std != 0 here, so z_score is still defined and finite.
    assert fd.z_score is not None
    assert math.isfinite(fd.z_score)

    text = json.dumps(reference_delta_to_dict(delta), allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text


# =========================================================================== #
# AC7: out_of_range honours configurable bound percentiles
# =========================================================================== #


def test_ac7_out_of_range_honours_configurable_bound_percentiles():
    reference = _full_reference()
    stats = PHYSICAL_VOLUME_STATS

    # Default (1, 99): a value between p1 (10) and p99 (90) is in-range.
    block_in = _features_block([(20, "L1", {"physical_volume_mm3": 50.0})])
    delta_in = compute_reference_delta(block_in, reference)
    assert _feature_delta(delta_in.per_label[20], "physical_volume_mm3").out_of_range is False

    # With (25, 75): a value between p25 (40) and p75 (60) is in-range...
    block_mid = _features_block([(20, "L1", {"physical_volume_mm3": 45.0})])
    delta_mid = compute_reference_delta(block_mid, reference, lower_pct=25, upper_pct=75)
    assert _feature_delta(delta_mid.per_label[20], "physical_volume_mm3").out_of_range is False

    # ...while a value just below p25 (40) is out-of-range under those bounds.
    block_low = _features_block([(20, "L1", {"physical_volume_mm3": 39.0})])
    delta_low = compute_reference_delta(block_low, reference, lower_pct=25, upper_pct=75)
    assert _feature_delta(delta_low.per_label[20], "physical_volume_mm3").out_of_range is True

    # The same 39.0 value is in-range under the default (1, 99) bounds.
    delta_low_default = compute_reference_delta(block_low, reference)
    assert _feature_delta(delta_low_default.per_label[20], "physical_volume_mm3").out_of_range is False


# =========================================================================== #
# AC8: distribution_distance is the RMS of the defined robust-z values
# =========================================================================== #


def test_ac8_distribution_distance_is_rms_of_defined_robust_z_values():
    reference = _full_reference()
    vol_value = 54.0
    ext_x_value = 11.0
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": vol_value, "extent_x_mm": ext_x_value}),
    ])
    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[20]

    rz_vol = _expected_robust_z(vol_value, PHYSICAL_VOLUME_STATS)
    rz_ext = _expected_robust_z(ext_x_value, EXTENT_X_STATS)
    expected_rms = math.sqrt((rz_vol ** 2 + rz_ext ** 2) / 2.0)

    assert label_delta.distribution_distance == pytest.approx(expected_rms)

    # A feature whose robust_z is None (extent_y_mm, IQR == 0) does not
    # contribute to the aggregate.
    block_with_degenerate = _features_block([
        (20, "L1", {
            "physical_volume_mm3": vol_value,
            "extent_x_mm": ext_x_value,
            "extent_y_mm": 7.0,
        }),
    ])
    delta2 = compute_reference_delta(block_with_degenerate, reference)
    assert delta2.per_label[20].distribution_distance == pytest.approx(expected_rms)


# =========================================================================== #
# AC9: a level absent from the reference yields available == False
# =========================================================================== #


def test_ac9_absent_level_yields_unavailable_not_a_crash():
    reference = _full_reference()
    block = _features_block([
        (99, "UNKNOWN", {"physical_volume_mm3": 50.0}),
    ])
    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[99]

    assert label_delta.available is False
    assert label_delta.features == ()
    assert label_delta.distribution_distance is None
    assert label_delta.out_of_range_features == ()


# =========================================================================== #
# AC10: a tracked feature absent from the case block is omitted
# =========================================================================== #


def test_ac10_tracked_feature_absent_from_case_block_is_omitted():
    reference = _full_reference()
    # No stage3 block at all -> no spline_offset_mm for this label, even
    # though the reference tracks it.
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
    ])
    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[20]

    feature_names = {fd.feature for fd in label_delta.features}
    assert "spline_offset_mm" not in feature_names
    assert "physical_volume_mm3" in feature_names


# =========================================================================== #
# AC11: the serialised block validates against the extended report schema
# =========================================================================== #


def test_ac11_serialised_block_validates_against_report_schema():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
    ])
    delta = compute_reference_delta(block, reference)
    delta_dict = reference_delta_to_dict(delta)

    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(
        verdict, "case-046", bundled_default_config(), reference_delta=delta_dict,
    )
    assert report["reference_delta"] == delta_dict


# =========================================================================== #
# AC12: the block metadata carries reference provenance
# =========================================================================== #


def test_ac12_block_metadata_carries_reference_provenance():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
    ])
    delta = compute_reference_delta(block, reference, lower_pct=5, upper_pct=95)
    delta_dict = reference_delta_to_dict(delta)

    assert delta_dict["reference_delta_version"] == REFERENCE_DELTA_VERSION
    assert delta_dict["reference_schema_version"] == reference.schema_version
    assert delta_dict["reference_source"] == reference.provenance.source
    assert delta_dict["stratum"] == ALL_STRATUM
    assert delta_dict["lower_pct"] == 5
    assert delta_dict["upper_pct"] == 95


# =========================================================================== #
# AC13: a stratum absent for a level yields available == False
# =========================================================================== #


def test_ac13_stratum_absent_for_level_yields_unavailable():
    reference = _full_reference()  # only carries stratum "all" for "L1"
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
    ])

    delta_missing_stratum = compute_reference_delta(block, reference, stratum="s1")
    assert delta_missing_stratum.per_label[20].available is False

    # The default stratum ("all") resolves against the unstratified reference.
    delta_default = compute_reference_delta(block, reference)
    assert delta_default.per_label[20].available is True


# =========================================================================== #
# AC14: an out-of-grid bound percentile raises ValueError
# =========================================================================== #


def test_ac14_out_of_grid_bound_percentile_raises_value_error():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
    ])

    with pytest.raises(ValueError):
        compute_reference_delta(block, reference, lower_pct=2)

    # The default (1, 99) is present in DEFAULT_PERCENTILES and is accepted.
    compute_reference_delta(block, reference)  # must not raise
    compute_reference_delta(
        block, reference, lower_pct=DEFAULT_LOWER_PCT, upper_pct=DEFAULT_UPPER_PCT,
    )  # must not raise


# =========================================================================== #
# AC15: computation is deterministic and non-mutating
# =========================================================================== #


def test_ac15_deterministic_and_non_mutating():
    reference = _full_reference()
    block = _features_block(
        [
            (20, "L1", {
                "physical_volume_mm3": 54.0, "extent_x_mm": 11.0, "extent_y_mm": 7.0,
            }),
        ],
        stage3_offsets=[{"label": 20, "offset_mm": 1.5}],
    )
    block_before = copy.deepcopy(block)
    reference_before = copy.deepcopy(reference)

    delta1 = compute_reference_delta(block, reference)
    delta2 = compute_reference_delta(block, reference)

    assert delta1 == delta2

    text1 = json.dumps(reference_delta_to_dict(delta1), sort_keys=True)
    text2 = json.dumps(reference_delta_to_dict(delta2), sort_keys=True)
    assert text1 == text2

    assert block == block_before
    assert reference == reference_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_case_yields_empty_per_label():
    reference = _full_reference()
    block = _features_block([])
    delta = compute_reference_delta(block, reference)
    assert delta.per_label == {}

    delta_dict = reference_delta_to_dict(delta)
    assert delta_dict["per_label"] == {}
    json.dumps(delta_dict)  # must not raise


def test_adv_value_exactly_on_bound_is_in_range_one_below_is_out():
    reference = _full_reference()
    p1 = PHYSICAL_VOLUME_STATS.percentiles["p1"]

    block_on_bound = _features_block([(20, "L1", {"physical_volume_mm3": p1})])
    delta_on_bound = compute_reference_delta(block_on_bound, reference)
    assert _feature_delta(delta_on_bound.per_label[20], "physical_volume_mm3").out_of_range is False

    block_below_bound = _features_block([(20, "L1", {"physical_volume_mm3": p1 - 0.0001})])
    delta_below_bound = compute_reference_delta(block_below_bound, reference)
    assert _feature_delta(delta_below_bound.per_label[20], "physical_volume_mm3").out_of_range is True


def test_adv_all_features_degenerate_label_has_null_distance_but_defined_rank():
    degenerate_stats = FeatureStats(
        count=5, mean=3.0, std=0.0, min=3.0, max=3.0,
        percentiles={f"p{n}": 3.0 for n in DEFAULT_PERCENTILES},
    )
    reference = _reference({"physical_volume_mm3": degenerate_stats})
    block = _features_block([(20, "L1", {"physical_volume_mm3": 3.0})])

    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[20]
    fd = _feature_delta(label_delta, "physical_volume_mm3")

    assert fd.z_score is None
    assert fd.robust_z is None
    assert label_delta.distribution_distance is None
    # percentile_rank and out_of_range remain defined.
    assert isinstance(fd.percentile_rank, float)
    assert isinstance(fd.out_of_range, bool)

    text = json.dumps(reference_delta_to_dict(delta), allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text


def test_adv_feature_tracked_by_reference_but_stats_absent_for_level_is_skipped():
    # The reference tracks "spline_offset_mm" (in .features) but this level's
    # feature_stats omits it entirely.
    partial_stats = {"physical_volume_mm3": PHYSICAL_VOLUME_STATS}
    level = LevelDistribution(
        level_name="L1", stratum=ALL_STRATUM, record_count=10,
        feature_stats=partial_stats,
    )
    reference = ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=PROV,
        features=("physical_volume_mm3", "spline_offset_mm"),
        percentiles=DEFAULT_PERCENTILES,
        subject_count=10,
        strata=(ALL_STRATUM,),
        levels={"L1": {ALL_STRATUM: level}},
    )
    block = _features_block(
        [(20, "L1", {"physical_volume_mm3": 50.0})],
        stage3_offsets=[{"label": 20, "offset_mm": 1.5}],
    )

    delta = compute_reference_delta(block, reference)  # must not raise
    feature_names = {fd.feature for fd in delta.per_label[20].features}
    assert "spline_offset_mm" not in feature_names
    assert "physical_volume_mm3" in feature_names


def test_adv_determinism_non_mutation_via_deep_copy_comparison():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"physical_volume_mm3": 50.0}),
        (21, "L1", {"physical_volume_mm3": 60.0}),
    ])
    block_snapshot = copy.deepcopy(block)
    reference_snapshot = copy.deepcopy(reference)

    compute_reference_delta(block, reference)

    assert block == block_snapshot
    assert reference == reference_snapshot


def test_adv_schema_round_trip_survives_json_dumps_loads_with_null_z_score():
    reference = _full_reference()
    block = _features_block([
        (20, "L1", {"extent_y_mm": 7.0}),  # std == 0 -> null z_score
    ])
    delta = compute_reference_delta(block, reference)
    delta_dict = reference_delta_to_dict(delta)

    round_tripped = json.loads(json.dumps(delta_dict))
    assert round_tripped == delta_dict
    assert round_tripped["per_label"]["20"]["features"]["extent_y_mm"]["z_score"] is None

    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(
        verdict, "case-046-null-z", bundled_default_config(), reference_delta=delta_dict,
    )
    assert report["reference_delta"]["per_label"]["20"]["features"]["extent_y_mm"]["z_score"] is None


def test_adv_flat_percentile_segment_tie_break_returns_lower_rank():
    # p25 == p50 == p75 == 5.0 (extent_z_mm's skewed stats); the value 5.0
    # sits on a flat segment of the anchor mapping and must resolve to the
    # lower of the tied ranks (25.0), not 50.0 or 75.0.
    reference = _full_reference()
    block = _features_block([(20, "L1", {"extent_z_mm": 5.0})])
    delta = compute_reference_delta(block, reference)
    fd = _feature_delta(delta.per_label[20], "extent_z_mm")
    assert fd.percentile_rank == pytest.approx(25.0)


def test_adv_bundled_default_reference_composes_with_a_real_extracted_case():
    reference = bundled_default_reference()
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    config = bundled_default_config()
    block = extract_feature_record(spine.seg_img, config)

    delta = compute_reference_delta(block, reference)  # must not raise
    reference_delta_to_dict(delta)  # must serialise without raising

    present_labels = {int(entry["label"]) for entry in block["per_label"].values()}
    assert set(delta.per_label.keys()) == present_labels
    # At least one present lumbar-level label is marked available (the
    # bundled default reference was built over the same synthetic levels).
    assert any(ld.available for ld in delta.per_label.values())
