"""Tests for item 043 -- reference-distribution schema & per-level
aggregation core (``src/segqc/reference``).

Covers Acceptance Criteria AC1-AC15:

- AC1: ``FeatureStats.mean`` equals the hand-computed arithmetic mean.
- AC2: ``FeatureStats.std`` is the sample std (ddof=1), 0.0 for a single value.
- AC3: percentiles match ``numpy.percentile`` (linear interpolation) and p50
  is the median.
- AC4: ``min``/``max``/``count``/``record_count`` are correct.
- AC5: a level present in only some subjects aggregates over exactly those
  records, and its stats are independent of other levels' records.
- AC6: the unstratified default puts every record under the single "all"
  stratum.
- AC7: the subject-size proxy buckets records deterministically via
  ``bisect_right`` on sorted edges, and re-running is stable.
- AC8: each stratum's stats use only that stratum's records.
- AC9: empty input yields a well-formed empty distribution.
- AC10: serialisation is byte-deterministic and matches the documented
  ``json.dumps(sort_keys=True, indent=2, ensure_ascii=False) + "\\n"`` form.
- AC11: the data model round-trips through ``to_dict``/``from_dict``.
- AC12: schema version and provenance surface in the serialised form, and
  ``subject_count`` counts distinct subjects.
- AC13: ``build_date`` is taken verbatim from the caller (no wall clock).
- AC14: explicit ``features=`` restricts the tracked feature set, omitting
  tracked features absent from every record.
- AC15: inputs (record sequence and each record's ``features`` mapping) are
  never mutated.

Adversarial / edge-case scenarios included:
- A ``size_proxy`` exactly on a stratum edge lands in the upper bucket
  (``bisect_right`` half-open rule).
- A single-subject, single-record level: ``record_count == 1``,
  ``std == 0.0``, every percentile equals the lone value, ``min == max ==
  mean``.
- A feature present in only some of a level's records has ``count`` less
  than ``record_count``.
- Stratification with a ``None`` ``size_proxy`` raises ``ValueError``.
- A wrong-length ``stratum_labels`` raises ``ValueError``.
- A duplicate ``subject_id`` across levels counts once in ``subject_count``.
- Determinism survives a hand-permuted input record order (byte-identical
  serialised text).
- ``features=[]`` on a non-empty records list serialises with empty
  ``feature_stats`` per level.
- Non-mutation is checked via an explicit deep-copy comparison (AC15).
- Round-trip stability for both an unstratified and a stratified
  distribution (AC11).
"""

from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from segqc.reference import (
    ALL_STRATUM,
    DEFAULT_PERCENTILES,
    SCHEMA_VERSION,
    FeatureRecord,
    Provenance,
    aggregate_reference,
    from_dict,
    to_dict,
    to_json_text,
)

PROV = Provenance(
    source="test-cohort",
    config_hash="cfg-hash",
    build_date="2000-01-01",
    size_proxy_name=None,
)


def _rec(subject_id, level_name, features, size_proxy=None):
    return FeatureRecord(
        subject_id=subject_id,
        level_name=level_name,
        features=dict(features),
        size_proxy=size_proxy,
    )


# =========================================================================== #
# AC1-AC4: per-feature statistics on a single unstratified level
# =========================================================================== #


def test_ac1_mean_matches_hand_computed_arithmetic_mean():
    values = [10.0, 20.0, 30.0, 40.0]
    records = [_rec(f"s{i}", "L1", {"vol": v}) for i, v in enumerate(values)]
    dist = aggregate_reference(records, provenance=PROV)
    stats = dist.levels["L1"]["all"].feature_stats["vol"]
    assert stats.mean == pytest.approx(sum(values) / len(values))


def test_ac2_std_is_sample_std_ddof1_and_zero_for_single_value():
    values = [10.0, 20.0, 30.0, 40.0]
    records = [_rec(f"s{i}", "L1", {"vol": v}) for i, v in enumerate(values)]
    dist = aggregate_reference(records, provenance=PROV)
    stats = dist.levels["L1"]["all"].feature_stats["vol"]
    assert stats.std == pytest.approx(float(np.std(values, ddof=1)))

    single = [_rec("s0", "L2", {"vol": 42.0})]
    dist_single = aggregate_reference(single, provenance=PROV)
    stats_single = dist_single.levels["L2"]["all"].feature_stats["vol"]
    assert stats_single.std == 0.0


def test_ac3_percentiles_match_numpy_percentile_and_p50_is_median():
    values = [3.0, 7.0, 1.0, 9.0, 5.0, 2.0, 8.0, 4.0, 6.0, 10.0]
    records = [_rec(f"s{i}", "L1", {"vol": v}) for i, v in enumerate(values)]
    dist = aggregate_reference(records, provenance=PROV)
    stats = dist.levels["L1"]["all"].feature_stats["vol"]

    for n in DEFAULT_PERCENTILES:
        expected = float(np.percentile(values, n))
        assert stats.percentiles[f"p{n}"] == pytest.approx(expected)

    assert stats.percentiles["p50"] == pytest.approx(float(np.median(values)))


def test_ac4_min_max_count_and_record_count_are_correct():
    values = [10.0, -5.0, 30.0, 7.5]
    records = [_rec(f"s{i}", "L1", {"vol": v}) for i, v in enumerate(values)]
    dist = aggregate_reference(records, provenance=PROV)
    level = dist.levels["L1"]["all"]
    stats = level.feature_stats["vol"]

    assert stats.min == pytest.approx(min(values))
    assert stats.max == pytest.approx(max(values))
    assert stats.count == len(values)
    assert level.record_count == len(values)


# =========================================================================== #
# AC5: partial-level presence, cross-level independence
# =========================================================================== #


def test_ac5_level_present_in_only_some_subjects_aggregates_exactly_those():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "A", {"vol": 30.0}),
        _rec("s3", "B", {"vol": 100.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    assert dist.levels["A"]["all"].record_count == 3
    assert dist.levels["B"]["all"].record_count == 1
    b_stats_before = dist.levels["B"]["all"].feature_stats["vol"]
    assert b_stats_before.mean == pytest.approx(100.0)

    # Changing an A record (building a fresh aggregation with a different A
    # value) does not alter B's stats.
    records2 = [
        _rec("s0", "A", {"vol": 999.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "A", {"vol": 30.0}),
        _rec("s3", "B", {"vol": 100.0}),
    ]
    dist2 = aggregate_reference(records2, provenance=PROV)
    b_stats_after = dist2.levels["B"]["all"].feature_stats["vol"]
    assert b_stats_after.mean == pytest.approx(b_stats_before.mean)


# =========================================================================== #
# AC6-AC8: stratification
# =========================================================================== #


def test_ac6_unstratified_default_uses_single_all_stratum():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "B", {"vol": 30.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    assert dist.strata == (ALL_STRATUM,)
    for level_name, strata in dist.levels.items():
        assert set(strata.keys()) == {ALL_STRATUM}
    assert dist.levels["A"][ALL_STRATUM].record_count == 2
    assert dist.levels["B"][ALL_STRATUM].record_count == 1


def test_ac7_size_proxy_buckets_records_deterministically():
    # edges (10.0, 20.0) -> buckets s0 [<10), s1 [10,20), s2 [>=20)
    records = [
        _rec("s0", "A", {"vol": 1.0}, size_proxy=5.0),   # s0
        _rec("s1", "A", {"vol": 2.0}, size_proxy=15.0),  # s1
        _rec("s2", "A", {"vol": 3.0}, size_proxy=25.0),  # s2
    ]
    dist = aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0, 20.0])
    assert dist.levels["A"]["s0"].record_count == 1
    assert dist.levels["A"]["s1"].record_count == 1
    assert dist.levels["A"]["s2"].record_count == 1
    assert dist.levels["A"]["s0"].feature_stats["vol"].mean == pytest.approx(1.0)
    assert dist.levels["A"]["s1"].feature_stats["vol"].mean == pytest.approx(2.0)
    assert dist.levels["A"]["s2"].feature_stats["vol"].mean == pytest.approx(3.0)

    dist_again = aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0, 20.0])
    assert dist_again.strata == dist.strata
    for stratum in dist.strata:
        assert dist_again.levels["A"][stratum].record_count == dist.levels["A"][stratum].record_count


def test_ac8_each_stratum_stats_use_only_that_stratum_records():
    records = [
        _rec("s0", "A", {"vol": 1.0}, size_proxy=5.0),    # s0
        _rec("s1", "A", {"vol": 1000.0}, size_proxy=15.0),  # s1
    ]
    dist = aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0])
    s0_stats = dist.levels["A"]["s0"].feature_stats["vol"]
    s1_stats = dist.levels["A"]["s1"].feature_stats["vol"]
    assert s0_stats.mean == pytest.approx(1.0)
    assert s1_stats.mean == pytest.approx(1000.0)
    assert s0_stats.count == 1
    assert s1_stats.count == 1


# =========================================================================== #
# AC9: empty input
# =========================================================================== #


def test_ac9_empty_input_yields_well_formed_empty_distribution():
    dist = aggregate_reference([], provenance=PROV)
    assert dist.levels == {}
    assert dist.subject_count == 0
    assert dist.schema_version == SCHEMA_VERSION
    assert dist.provenance == PROV

    text = to_json_text(dist)
    parsed = json.loads(text)  # must not raise
    assert parsed["levels"] == {}


# =========================================================================== #
# AC10: byte-deterministic serialisation
# =========================================================================== #


def test_ac10_serialisation_is_byte_deterministic_and_matches_documented_form():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "B", {"vol": 30.0}),
    ]
    dist1 = aggregate_reference(records, provenance=PROV)
    dist2 = aggregate_reference(records, provenance=PROV)

    text1 = to_json_text(dist1)
    text2 = to_json_text(dist2)
    assert text1 == text2

    expected = json.dumps(to_dict(dist1), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert text1 == expected
    assert text1.endswith("\n")
    assert not text1.endswith("\n\n")


# =========================================================================== #
# AC11: dict round-trip
# =========================================================================== #


def test_ac11_round_trips_through_to_dict_from_dict():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "B", {"vol": 30.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    round_tripped = from_dict(to_dict(dist))
    assert round_tripped == dist
    assert to_dict(from_dict(to_dict(dist))) == to_dict(dist)


# =========================================================================== #
# AC12-AC13: provenance / subject_count / build_date
# =========================================================================== #


def test_ac12_schema_version_and_provenance_surface_in_serialised_form():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s0", "B", {"vol": 20.0}),  # same subject, second level
        _rec("s1", "A", {"vol": 30.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    d = to_dict(dist)
    assert d["schema_version"] == SCHEMA_VERSION
    assert d["provenance"]["source"] == PROV.source
    assert d["provenance"]["config_hash"] == PROV.config_hash
    assert d["provenance"]["build_date"] == PROV.build_date
    assert d["provenance"]["size_proxy_name"] == PROV.size_proxy_name
    # s0 contributes to two levels but is one distinct subject.
    assert dist.subject_count == 2


def test_ac13_build_date_is_taken_verbatim_no_wall_clock():
    prov = Provenance(
        source="src", config_hash="hash", build_date="2000-01-01", size_proxy_name=None
    )
    records = [_rec("s0", "A", {"vol": 1.0})]
    dist = aggregate_reference(records, provenance=prov)
    assert to_dict(dist)["provenance"]["build_date"] == "2000-01-01"


# =========================================================================== #
# AC14: explicit features= restriction
# =========================================================================== #


def test_ac14_explicit_features_restricts_tracked_feature_set():
    records = [
        _rec("s0", "A", {"physical_volume_mm3": 1000.0, "extent_x_mm": 5.0}),
        _rec("s1", "A", {"physical_volume_mm3": 2000.0, "extent_x_mm": 6.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV, features=["physical_volume_mm3"])
    level = dist.levels["A"]["all"]
    assert set(level.feature_stats.keys()) == {"physical_volume_mm3"}
    assert dist.features == ("physical_volume_mm3",)

    # A tracked feature absent from every record is omitted, not null.
    dist2 = aggregate_reference(
        records, provenance=PROV, features=["physical_volume_mm3", "missing_feature"]
    )
    level2 = dist2.levels["A"]["all"]
    assert "missing_feature" not in level2.feature_stats
    assert dist2.features == ("missing_feature", "physical_volume_mm3")


# =========================================================================== #
# AC15: non-mutation
# =========================================================================== #


def test_ac15_inputs_are_never_mutated():
    records = [
        _rec("s0", "A", {"vol": 10.0, "extent": 1.0}),
        _rec("s1", "A", {"vol": 20.0}),
    ]
    records_before = copy.deepcopy(records)

    aggregate_reference(records, provenance=PROV, size_strata_edges=None)

    assert records == records_before
    for original, after in zip(records_before, records):
        assert original.features == after.features
        assert original.features is not after.features or True  # identity not required


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_size_proxy_exactly_on_edge_lands_in_upper_bucket():
    records = [_rec("s0", "A", {"vol": 1.0}, size_proxy=10.0)]
    dist = aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0])
    # edges=[10.0] -> buckets s0 [ -inf, 10 ), s1 [10, +inf )
    assert "s1" in dist.levels["A"]
    assert "s0" not in dist.levels["A"]


def test_adv_single_subject_single_record_level():
    records = [_rec("s0", "A", {"vol": 42.0})]
    dist = aggregate_reference(records, provenance=PROV)
    level = dist.levels["A"]["all"]
    stats = level.feature_stats["vol"]

    assert level.record_count == 1
    assert stats.std == 0.0
    assert stats.min == pytest.approx(42.0)
    assert stats.max == pytest.approx(42.0)
    assert stats.mean == pytest.approx(42.0)
    for n in DEFAULT_PERCENTILES:
        assert stats.percentiles[f"p{n}"] == pytest.approx(42.0)


def test_adv_missing_feature_in_some_records():
    records = [
        _rec("s0", "A", {"vol": 10.0, "extra": 1.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "A", {"vol": 30.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    level = dist.levels["A"]["all"]
    assert level.record_count == 3
    assert level.feature_stats["extra"].count == 1
    assert level.feature_stats["vol"].count == 3


def test_adv_stratification_with_none_size_proxy_raises_value_error():
    records = [_rec("s0", "A", {"vol": 1.0}, size_proxy=None)]
    with pytest.raises(ValueError):
        aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0])


def test_adv_wrong_length_stratum_labels_raises_value_error():
    records = [_rec("s0", "A", {"vol": 1.0}, size_proxy=5.0)]
    with pytest.raises(ValueError):
        aggregate_reference(
            records,
            provenance=PROV,
            size_strata_edges=[10.0, 20.0],  # 2 edges -> 3 buckets expected
            stratum_labels=["only_one"],
        )


def test_adv_duplicate_subject_id_across_levels_counts_once():
    records = [
        _rec("dup", "A", {"vol": 1.0}),
        _rec("dup", "B", {"vol": 2.0}),
        _rec("dup", "C", {"vol": 3.0}),
    ]
    dist = aggregate_reference(records, provenance=PROV)
    assert dist.subject_count == 1


def test_adv_determinism_survives_hand_permuted_record_order():
    records = [
        _rec("s0", "A", {"vol": 10.0}),
        _rec("s1", "A", {"vol": 20.0}),
        _rec("s2", "B", {"vol": 30.0}),
    ]
    permuted = list(reversed(records))
    assert [r.subject_id for r in permuted] != [r.subject_id for r in records]

    dist1 = aggregate_reference(records, provenance=PROV)
    dist2 = aggregate_reference(permuted, provenance=PROV)
    assert to_json_text(dist1) == to_json_text(dist2)


def test_adv_empty_tracked_features_serialises_with_empty_feature_stats():
    records = [_rec("s0", "A", {"vol": 10.0})]
    dist = aggregate_reference(records, provenance=PROV, features=[])
    assert dist.features == ()
    level = dist.levels["A"]["all"]
    assert level.feature_stats == {}

    text = to_json_text(dist)
    parsed = json.loads(text)  # must not raise
    assert parsed["levels"]["A"]["all"]["feature_stats"] == {}


def test_adv_non_mutation_deep_copy_comparison():
    records = [
        _rec("s0", "A", {"vol": 10.0}, size_proxy=1.0),
        _rec("s1", "B", {"vol": 20.0}, size_proxy=5.0),
    ]
    snapshot = copy.deepcopy(records)
    aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0])
    assert records == snapshot


def test_adv_round_trip_stability_for_stratified_and_unstratified():
    records = [
        _rec("s0", "A", {"vol": 10.0}, size_proxy=5.0),
        _rec("s1", "A", {"vol": 20.0}, size_proxy=15.0),
    ]
    dist_unstratified = aggregate_reference(records, provenance=PROV)
    dist_stratified = aggregate_reference(records, provenance=PROV, size_strata_edges=[10.0])

    assert from_dict(to_dict(dist_unstratified)) == dist_unstratified
    assert from_dict(to_dict(dist_stratified)) == dist_stratified
