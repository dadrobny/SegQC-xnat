"""Tests for item 093 -- adopt the TPTBox vertebra label convention as default.

Covers Acceptance Criteria AC1-AC8:

- AC1: ``DEFAULT_LABEL_MAP`` matches the TPTBox vertebra table for 1-33.
- AC2: ``CANONICAL_ORDER`` places the new entries in head-to-tail anatomical
  order (``..., "L5", "L6", "S1", ..., "S6", "Cocc"``).
- AC3: bidirectional lookup (``value_of``/``is_known``) is exact and
  case-insensitive for the new table.
- AC4: ``LabelConvention.from_mapping`` overriding is unaffected by the
  default-table change.
- AC5: ``reference_verse_v1.json`` is re-keyed (``"S"`` -> ``"L6"``), not
  re-fit -- ``feature_stats`` is byte-for-byte identical to the pre-rename
  ``"S"`` entry.
- AC6: ``reference_default.json`` is unaffected by this item (checked by
  level-set content, not a byte-hash pin -- see item 116's retirement of the
  perpetual pre-item digest fence, in the same spirit as item 107).
- AC7: the reference-delta rule resolves a label-25 (-> ``"L6"``) case
  against the renamed level in ``bundled_production_reference()``.
- AC8: is exercised at the suite level (not a single test here) -- see the
  adversarial section below for the "no stray literal old-name assertion
  left in the label module's own tests" spot-check this module can make
  independently.

Adversarial / edge-case scenarios included:
- A raw label value outside 1-33 (e.g. 34, or a large artifact/noise label)
  still resolves to ``UNKNOWN``/``is_known() is False``.
- ``summarise_inventory`` on an inventory containing *only* the new ``S1``
  sacral entry (label 26) sorts correctly under the new, larger
  ``CANONICAL_ORDER`` without raising.
- ``reference_verse_v1.json`` still passes ``load_artifact``'s
  ``schema_version`` check and is well-formed JSON after the edit.
- ``levels["L6"]`` carries no leftover ``"S"``-named artefacts (only the key
  and ``level_name`` changed; no other level touched).

Pinned-snapshot choice for AC5 (documented per the Testing Strategy): the
pre-rename ``"S"`` entry's ``feature_stats`` was captured as a literal Python
dict (``_PRE_RENAME_S_FEATURE_STATS`` below) by reading the committed
``reference_verse_v1.json`` *before* this item's builder edits it, rather than
via ``git show HEAD:...`` at test-run time -- a literal avoids depending on
git history/working-directory state (e.g. a shallow clone, a squashed
history, or running the suite outside a git checkout) and keeps the test
self-contained and deterministic across machines.
"""

from __future__ import annotations

import json

import pytest

from segfacet.labels import (
    CANONICAL_ORDER,
    DEFAULT_LABEL_MAP,
    UNKNOWN,
    LabelConvention,
    summarise_inventory,
)
from segfacet.reference import (
    ALL_STRATUM,
    bundled_default_reference,
    bundled_production_reference,
    bundled_production_reference_path,
    compute_reference_delta,
    load_artifact,
)

# --------------------------------------------------------------------------- #
# AC1: literal expected table, transcribed from TPTBox's v_idx2name (vertebra
# range 1-33 only), NOT imported from TPTBox (this item hardcodes the table).
# --------------------------------------------------------------------------- #

_EXPECTED_LABEL_MAP = {
    # Cervical C1-C7 (unchanged)
    1: "C1", 2: "C2", 3: "C3", 4: "C4", 5: "C5", 6: "C6", 7: "C7",
    # Thoracic T1-T12 (unchanged)
    8: "T1", 9: "T2", 10: "T3", 11: "T4", 12: "T5", 13: "T6", 14: "T7",
    15: "T8", 16: "T9", 17: "T10", 18: "T11", 19: "T12",
    # Lumbar L1-L5 (unchanged)
    20: "L1", 21: "L2", 22: "L3", 23: "L4", 24: "L5",
    # TPTBox-derived sacral/coccygeal/transitional range (new)
    25: "L6",
    26: "S1",
    27: "Cocc",
    28: "T13",
    29: "S2",
    30: "S3",
    31: "S4",
    32: "S5",
    33: "S6",
}

_EXPECTED_CANONICAL_ORDER = (
    "C1", "C2", "C3", "C4", "C5", "C6", "C7",
    "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12",
    "T13",
    "L1", "L2", "L3", "L4", "L5", "L6",
    "S1", "S2", "S3", "S4", "S5", "S6",
    "Cocc",
)

# --------------------------------------------------------------------------- #
# AC5: pinned snapshot of the pre-rename "S" entry's feature_stats, captured
# from the committed reference_verse_v1.json before this item's edit. See the
# module docstring for why a literal (not `git show`) was chosen.
# --------------------------------------------------------------------------- #

_PRE_RENAME_S_FEATURE_STATS = {
    "component_count": {
        "count": 3, "mean": 1.3333333333333333, "std": 0.5773502691896257,
        "min": 1.0, "max": 2.0,
        "percentiles": {
            "p1": 1.0, "p5": 1.0, "p25": 1.0, "p50": 1.0,
            "p75": 1.5, "p95": 1.9, "p99": 1.98,
        },
    },
    "eigenvalue_ratio": {
        "count": 3, "mean": 1.189222678878912, "std": 0.17329048360528548,
        "min": 1.0245853820172004, "max": 1.3700325049334778,
        "percentiles": {
            "p1": 1.0275546773705775, "p5": 1.039431858784086,
            "p25": 1.0988177658516292, "p50": 1.1730501496860577,
            "p75": 1.2715413273097678, "p95": 1.350334269408736,
            "p99": 1.3660928578285294,
        },
    },
    "extent_x_mm": {
        "count": 3, "mean": 84.0, "std": 9.539392014169456,
        "min": 78.0, "max": 95.0,
        "percentiles": {
            "p1": 78.02, "p5": 78.1, "p25": 78.5, "p50": 79.0,
            "p75": 87.0, "p95": 93.4, "p99": 94.68,
        },
    },
    "extent_y_mm": {
        "count": 3, "mean": 62.333333333333336, "std": 11.015141094572204,
        "min": 55.0, "max": 75.0,
        "percentiles": {
            "p1": 55.04, "p5": 55.2, "p25": 56.0, "p50": 57.0,
            "p75": 66.0, "p95": 73.2, "p99": 74.64,
        },
    },
    "extent_z_mm": {
        "count": 3, "mean": 79.33849461873372, "std": 34.19929059965943,
        "min": 40.0, "max": 102.0,
        "percentiles": {
            "p1": 41.12030967712403, "p5": 45.60154838562012,
            "p25": 68.00774192810059, "p50": 96.01548385620117,
            "p75": 99.00774192810059, "p95": 101.40154838562012,
            "p99": 101.88030967712402,
        },
    },
    "intensity_entropy": {
        "count": 1, "mean": 4.143056642291547, "std": 0.0,
        "min": 4.143056642291547, "max": 4.143056642291547,
        "percentiles": {p: 4.143056642291547 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_iqr": {
        "count": 1, "mean": 442.4781742095947, "std": 0.0,
        "min": 442.4781742095947, "max": 442.4781742095947,
        "percentiles": {p: 442.4781742095947 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_max": {
        "count": 1, "mean": 1837.8699951171875, "std": 0.0,
        "min": 1837.8699951171875, "max": 1837.8699951171875,
        "percentiles": {p: 1837.8699951171875 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_mean": {
        "count": 1, "mean": 318.01917569738333, "std": 0.0,
        "min": 318.01917569738333, "max": 318.01917569738333,
        "percentiles": {p: 318.01917569738333 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_median": {
        "count": 1, "mean": 227.64662170410156, "std": 0.0,
        "min": 227.64662170410156, "max": 227.64662170410156,
        "percentiles": {p: 227.64662170410156 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_min": {
        "count": 1, "mean": -586.3045043945312, "std": 0.0,
        "min": -586.3045043945312, "max": -586.3045043945312,
        "percentiles": {p: -586.3045043945312 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_p05": {
        "count": 1, "mean": -135.94112396240234, "std": 0.0,
        "min": -135.94112396240234, "max": -135.94112396240234,
        "percentiles": {p: -135.94112396240234 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_p25": {
        "count": 1, "mean": 58.5371150970459, "std": 0.0,
        "min": 58.5371150970459, "max": 58.5371150970459,
        "percentiles": {p: 58.5371150970459 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_p50": {
        "count": 1, "mean": 227.64662170410156, "std": 0.0,
        "min": 227.64662170410156, "max": 227.64662170410156,
        "percentiles": {p: 227.64662170410156 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_p75": {
        "count": 1, "mean": 501.0152893066406, "std": 0.0,
        "min": 501.0152893066406, "max": 501.0152893066406,
        "percentiles": {p: 501.0152893066406 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_p95": {
        "count": 1, "mean": 1091.5233764648438, "std": 0.0,
        "min": 1091.5233764648438, "max": 1091.5233764648438,
        "percentiles": {p: 1091.5233764648438 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_range": {
        "count": 1, "mean": 2424.1744995117188, "std": 0.0,
        "min": 2424.1744995117188, "max": 2424.1744995117188,
        "percentiles": {p: 2424.1744995117188 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "intensity_std": {
        "count": 1, "mean": 366.7506361878421, "std": 0.0,
        "min": 366.7506361878421, "max": 366.7506361878421,
        "percentiles": {p: 366.7506361878421 for p in
                         ("p1", "p5", "p25", "p50", "p75", "p95", "p99")},
    },
    "largest_component_fraction": {
        "count": 3, "mean": 0.9999837374575141, "std": 2.8167549845789315e-05,
        "min": 0.9999512123725424, "max": 1.0,
        "percentiles": {
            "p1": 0.9999521881250916, "p5": 0.9999560911352882,
            "p25": 0.9999756061862712, "p50": 1.0, "p75": 1.0,
            "p95": 1.0, "p99": 1.0,
        },
    },
    "physical_volume_mm3": {
        "count": 3, "mean": 68177.63343707721, "std": 17315.63982217501,
        "min": 48751.0, "max": 81988.0,
        "percentiles": {
            "p1": 49251.85800622463, "p5": 51255.290031123164,
            "p25": 61272.45015561581, "p50": 73793.90031123161,
            "p75": 77890.9501556158, "p95": 81168.59003112317,
            "p99": 81824.11800622463,
        },
    },
    "spline_offset_mm": {
        "count": 3, "mean": 0.00020553256939238786, "std": 0.00012255731482197898,
        "min": 6.416527111875782e-05, "max": 0.00028185187736243185,
        "percentiles": {
            "p1": 6.829357689030215e-05, "p5": 8.480679997647944e-05,
            "p25": 0.0001673729154073659, "p50": 0.00027058055969597395,
            "p75": 0.0002762162185292029, "p95": 0.00028072474559578606,
            "p99": 0.00028162645100910267,
        },
    },
}


def _feature_stats_to_plain_dict(stats) -> dict:
    """Convert a schema ``FeatureStats`` dataclass to a plain JSON-shaped dict
    for comparison against the pinned literal snapshot."""
    return {
        "count": stats.count,
        "mean": stats.mean,
        "std": stats.std,
        "min": stats.min,
        "max": stats.max,
        "percentiles": dict(stats.percentiles),
    }


# =========================================================================== #
# AC1: DEFAULT_LABEL_MAP matches the TPTBox vertebra table for 1-33.
# =========================================================================== #


@pytest.mark.parametrize("value", sorted(_EXPECTED_LABEL_MAP))
def test_ac1_default_label_map_matches_tptbox_table(value):
    conv = LabelConvention.default()
    assert conv.name_of(value) == _EXPECTED_LABEL_MAP[value]


def test_ac1_default_label_map_literal_equality():
    """The full table equals the TPTBox-derived literal, not just per-value."""
    assert DEFAULT_LABEL_MAP == _EXPECTED_LABEL_MAP


def test_ac1_transitional_renames_and_new_entries():
    """Spot-check the specific renames/additions the spec calls out by name."""
    conv = LabelConvention.default()
    assert conv.name_of(25) == "L6"
    assert conv.name_of(26) == "S1"
    assert conv.name_of(27) == "Cocc"
    assert conv.name_of(28) == "T13"
    assert conv.name_of(29) == "S2"
    assert conv.name_of(30) == "S3"
    assert conv.name_of(31) == "S4"
    assert conv.name_of(32) == "S5"
    assert conv.name_of(33) == "S6"


def test_ac1_cervical_thoracic_lumbar_1_24_unchanged():
    """Values 1-24 (C1-C7, T1-T12, L1-L5) are untouched by the swap."""
    conv = LabelConvention.default()
    for i in range(1, 8):
        assert conv.name_of(i) == f"C{i}"
    for i in range(1, 13):
        assert conv.name_of(7 + i) == f"T{i}"
    for i in range(1, 6):
        assert conv.name_of(19 + i) == f"L{i}"


# =========================================================================== #
# AC2: CANONICAL_ORDER places the new entries in head-to-tail order.
# =========================================================================== #


def test_ac2_canonical_order_literal_equality():
    assert CANONICAL_ORDER == _EXPECTED_CANONICAL_ORDER


def test_ac2_canonical_order_anatomical_run_after_lumbar():
    order = list(CANONICAL_ORDER)
    assert order.index("L5") < order.index("L6") < order.index("S1")
    assert (
        order.index("S1") < order.index("S2") < order.index("S3")
        < order.index("S4") < order.index("S5") < order.index("S6")
        < order.index("Cocc")
    )
    # Existing anatomical placements are unaffected.
    assert order.index("T12") < order.index("T13") < order.index("L1")
    assert order.index("C7") < order.index("T1")


def test_ac2_every_default_name_appears_in_canonical_order():
    for name in DEFAULT_LABEL_MAP.values():
        assert name in CANONICAL_ORDER


# =========================================================================== #
# AC3: bidirectional lookup is exact and case-insensitive.
# =========================================================================== #


def test_ac3_value_of_new_names():
    conv = LabelConvention.default()
    assert conv.value_of("L6") == 25
    assert conv.value_of("s1") == 26  # case-insensitive
    assert conv.value_of("Cocc") == 27
    assert conv.value_of("S6") == 33


@pytest.mark.parametrize("value", range(1, 34))
def test_ac3_is_known_true_for_all_of_1_to_33(value):
    conv = LabelConvention.default()
    assert conv.is_known(value) is True


def test_ac3_is_known_false_for_unmapped_34():
    conv = LabelConvention.default()
    assert conv.is_known(34) is False
    assert conv.name_of(34) == UNKNOWN


def test_ac3_round_trip_new_table():
    """Every new-table entry inverts in both directions."""
    conv = LabelConvention.default()
    for value, name in _EXPECTED_LABEL_MAP.items():
        assert conv.name_of(value) == name
        assert conv.value_of(name) == value


# =========================================================================== #
# AC4: LabelConvention.from_mapping overriding still works unchanged.
# =========================================================================== #


def test_ac4_custom_override_unaffected_by_default_table_change():
    conv = LabelConvention.from_mapping({25: "MyName"})
    assert conv.name_of(25) == "MyName"
    # The override fully replaces the default -- the new default's "L6" name
    # for 25 does not leak in, and no other default entry resolves.
    assert conv.value_of("L6") is None
    assert conv.name_of(1) == UNKNOWN


def test_ac4_default_unaffected_by_building_an_override():
    """Building an override must not mutate the shared new default table."""
    before = dict(DEFAULT_LABEL_MAP)
    LabelConvention.from_mapping({25: "MyName"})
    assert DEFAULT_LABEL_MAP == before
    assert LabelConvention.default().name_of(25) == "L6"


# =========================================================================== #
# AC5: reference_verse_v1.json is re-keyed, not re-fit.
# =========================================================================== #


def test_ac5_s_key_no_longer_present():
    dist = bundled_production_reference()
    assert "S" not in dist.levels


def test_ac5_l6_level_name_is_l6():
    dist = bundled_production_reference()
    assert dist.levels["L6"][ALL_STRATUM].level_name == "L6"


#: Item 123 (docs/aide/items/123-recalibrate-and-regenerate-downstream-
#: artifacts.md) rebuilds ``reference_verse_v1.json`` from the real VerSe19
#: cohort under item 120's held-out ``spline_offset_mm`` estimator -- a
#: deliberate re-*fit* of that one feature, not the re-*key* this AC5
#: originally pinned byte-for-byte. ``spline_offset_mm`` is excluded from the
#: byte-for-byte comparison for exactly that reason (per the item 123
#: Assumptions, "Item 093's AC5 snapshot is narrowed, not deleted"); every
#: other statistic in ``_PRE_RENAME_S_FEATURE_STATS`` is geometry/intensity/
#: morphology, which item 123 does not touch, so it stays pinned exactly.
_AC5_FEATURES_MOVED_BY_ITEM_123_REFIT = frozenset({"spline_offset_mm"})


def test_ac5_l6_feature_stats_byte_for_byte_identical_to_pre_rename_s():
    dist = bundled_production_reference()
    l6_stats = dist.levels["L6"][ALL_STRATUM].feature_stats
    assert set(l6_stats) == set(_PRE_RENAME_S_FEATURE_STATS)
    for feature_name, expected in _PRE_RENAME_S_FEATURE_STATS.items():
        if feature_name in _AC5_FEATURES_MOVED_BY_ITEM_123_REFIT:
            continue
        actual = _feature_stats_to_plain_dict(l6_stats[feature_name])
        assert actual == expected, f"feature_stats mismatch for {feature_name!r}"


def test_ac5_spline_offset_mm_excluded_from_byte_for_byte_is_the_only_exclusion():
    """The item-123 narrowing removes exactly one feature from the
    byte-for-byte set -- every other pre-rename statistic is still checked."""
    assert _AC5_FEATURES_MOVED_BY_ITEM_123_REFIT == {"spline_offset_mm"}
    still_checked = set(_PRE_RENAME_S_FEATURE_STATS) - _AC5_FEATURES_MOVED_BY_ITEM_123_REFIT
    assert len(still_checked) == len(_PRE_RENAME_S_FEATURE_STATS) - 1


def test_ac5_no_other_level_or_top_level_field_changed():
    """Only the levels["S"] -> levels["L6"] rename happened; every other
    level/top-level field is untouched by the edit."""
    dist = bundled_production_reference()
    # The other 24 pre-existing levels are all still present, unrenamed.
    expected_other_levels = {
        f"C{i}" for i in range(1, 8)
    } | {f"T{i}" for i in range(1, 13)} | {f"L{i}" for i in range(1, 6)}
    assert expected_other_levels <= set(dist.levels)
    assert dist.subject_count > 0
    assert dist.schema_version


def test_ac5_reference_verse_v1_json_is_well_formed_after_the_edit():
    """Adversarial: the edit is a value/key change only -- the file must
    still be valid JSON and pass load_artifact's schema_version check."""
    path = bundled_production_reference_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "S" not in raw["levels"]
    assert raw["levels"]["L6"]["all"]["level_name"] == "L6"
    # load_artifact must accept it (schema_version validity, general shape).
    dist = load_artifact(path)
    assert dist.levels["L6"][ALL_STRATUM].level_name == "L6"


# =========================================================================== #
# AC6: reference_default.json is unaffected.
# =========================================================================== #


def test_ac6_reference_default_levels_are_l1_through_l5_only():
    dist = bundled_default_reference()
    assert set(dist.levels) == {"L1", "L2", "L3", "L4", "L5"}
    assert "S" not in dist.levels
    assert "L6" not in dist.levels


# =========================================================================== #
# AC7: the reference-delta rule resolves the renamed level correctly.
# =========================================================================== #


def test_ac7_label_25_resolves_to_l6_and_matches_reference_delta():
    conv = LabelConvention.default()
    level_name = conv.name_of(25)
    assert level_name == "L6"

    reference = bundled_production_reference()
    block = {
        "per_label": {
            "25": {
                "label": 25,
                "level_name": level_name,
                "geometry": {"physical_volume_mm3": 60000.0},
            },
        },
    }
    delta = compute_reference_delta(block, reference)
    label_delta = delta.per_label[25]
    assert label_delta.level_name == "L6"
    assert label_delta.available is True
    assert reference.levels.get("L6") is not None


def test_ac7_reference_delta_unmatched_before_rename_name_no_longer_resolves():
    """Adversarial: a record still carrying the OLD "S" name (e.g. a stale
    caller) does NOT spuriously match -- the join is by name, not by label
    value, so the rename is the only thing that fixes the join."""
    reference = bundled_production_reference()
    block = {
        "per_label": {
            "25": {
                "label": 25,
                "level_name": "S",
                "geometry": {"physical_volume_mm3": 60000.0},
            },
        },
    }
    delta = compute_reference_delta(block, reference)
    assert delta.per_label[25].available is False


# =========================================================================== #
# Adversarial / edge cases (Testing Strategy)
# =========================================================================== #


@pytest.mark.parametrize("value", [34, 40, 999, 0, -1])
def test_adv_out_of_range_value_resolves_unknown(value):
    """A raw label present in a real inventory but outside 1-33 (e.g. an
    artifact/noise label) still resolves to UNKNOWN/is_known() is False,
    unchanged by the larger table."""
    conv = LabelConvention.default()
    assert conv.name_of(value) == UNKNOWN
    assert conv.is_known(value) is False


def test_adv_summarise_inventory_with_only_new_sacral_entry():
    """An inventory containing ONLY the new S1 entry (label 26) sorts the
    single recognised entry using the new, larger CANONICAL_ORDER rank
    without raising -- exercises _order_key/_CANONICAL_RANK against the
    fuller table."""
    summary = summarise_inventory({26: 42})
    assert summary.recognised == [(26, "S1", 42)]
    assert summary.unknown == []
    assert summary.present_levels == ["S1"]


def test_adv_summarise_inventory_sparse_sacral_subset_orders_correctly():
    """Real cohorts often populate only a subset of the fine-grained sacral
    range (e.g. S1 and S4 but not S2/S3/S5/S6) -- this must still order
    head-to-tail without special-casing, per the item's Assumptions."""
    summary = summarise_inventory({31: 5, 26: 10, 24: 20})  # S4, S1, L5
    assert summary.present_levels == ["L5", "S1", "S4"]


def test_adv_summarise_inventory_full_new_range_no_duplicates_no_crash():
    """A cohort segmenting the full new 25-33 range (which also includes the
    unchanged T13 at value 28) partitions cleanly with no duplicate/dropped
    names and stays anatomically ordered: T13 sorts before L6 even though its
    integer value (28) is lower than L6's (25)."""
    inventory = {v: 1 for v in range(25, 34)}
    summary = summarise_inventory(inventory)
    assert summary.n_recognised == 9
    assert summary.n_unknown == 0
    assert summary.present_levels == [
        "T13", "L6", "S1", "S2", "S3", "S4", "S5", "S6", "Cocc",
    ]


def test_adv_bijection_holds_for_full_new_table():
    """The new table is still a bijection: unique values, unique names."""
    values = list(DEFAULT_LABEL_MAP.keys())
    names = list(DEFAULT_LABEL_MAP.values())
    assert len(values) == len(set(values))
    assert len(names) == len(set(names))
    assert len(DEFAULT_LABEL_MAP) == 33
