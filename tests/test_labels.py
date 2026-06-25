"""Unit tests for the label-convention module (item 004).

Covers the default TotalSegmentator/VerSe mapping (bijection + transitional
vertebrae), bidirectional lookup, custom overrides, graceful unknown/out-of-range
handling, and the inventory summariser over the item 002 synthetic fixtures and
inline mappings.
"""

from __future__ import annotations

import pytest

from segqc.io import SegQCInputError
from segqc.labels import (
    CANONICAL_ORDER,
    DEFAULT_LABEL_MAP,
    UNKNOWN,
    InventorySummary,
    LabelConvention,
    summarise_inventory,
)


# --------------------------------------------------------------------------- #
# Default mapping: bijection + coverage
# --------------------------------------------------------------------------- #

def test_default_is_bijection():
    """The default map has unique values and unique names (a bijection)."""
    values = list(DEFAULT_LABEL_MAP.keys())
    names = list(DEFAULT_LABEL_MAP.values())
    assert len(values) == len(set(values))
    assert len(names) == len(set(names))


def test_default_round_trips():
    """Every default entry inverts in both directions."""
    conv = LabelConvention.default()
    for value, name in DEFAULT_LABEL_MAP.items():
        assert conv.name_of(value) == name
        assert conv.value_of(name) == value
    # And the reverse composition holds for names too.
    for name in DEFAULT_LABEL_MAP.values():
        assert conv.name_of(conv.value_of(name)) == name


def test_default_covers_transitional_and_ranges():
    """C1-C7, T1-T13, L1-L6, and the sacrum are all present."""
    names = set(DEFAULT_LABEL_MAP.values())
    expected = (
        {f"C{i}" for i in range(1, 8)}
        | {f"T{i}" for i in range(1, 14)}   # includes T13
        | {f"L{i}" for i in range(1, 7)}    # includes L6
        | {"S"}
    )
    assert expected <= names


def test_canonical_order_matches_map_names():
    """Every default name appears in CANONICAL_ORDER (so it can be ordered)."""
    for name in DEFAULT_LABEL_MAP.values():
        assert name in CANONICAL_ORDER


def test_canonical_order_is_anatomical():
    """T13 sits between T12 and L1; integer order would not give this."""
    order = list(CANONICAL_ORDER)
    assert order.index("T12") < order.index("T13") < order.index("L1")
    assert order.index("L5") < order.index("L6") < order.index("S")
    assert order.index("C7") < order.index("T1")


# --------------------------------------------------------------------------- #
# Bidirectional lookup
# --------------------------------------------------------------------------- #

def test_value_to_name_known():
    conv = LabelConvention.default()
    assert conv.name_of(1) == "C1"
    assert conv.name_of(19) == "T12"
    assert conv.name_of(20) == "L1"
    assert conv.name_of(25) == "S"
    assert conv.name_of(28) == "T13"
    assert conv.name_of(29) == "L6"


def test_name_to_value_known():
    conv = LabelConvention.default()
    assert conv.value_of("C1") == 1
    assert conv.value_of("T12") == 19
    assert conv.value_of("S") == 25
    assert conv.value_of("L6") == 29


def test_name_lookup_is_case_and_whitespace_insensitive():
    conv = LabelConvention.default()
    assert conv.value_of("c1") == 1
    assert conv.value_of("  l1  ") == 20
    assert conv.value_of("t13") == 28


def test_is_known():
    conv = LabelConvention.default()
    assert conv.is_known(1) is True
    assert conv.is_known(25) is True
    assert conv.is_known(999) is False
    assert conv.is_known(27) is False  # 27 intentionally unmapped (no T13 there)


# --------------------------------------------------------------------------- #
# Unknown / out-of-range handling (never crashes)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value", [0, 27, 99, 1000, -1, -50])
def test_value_to_name_unknown_returns_sentinel(value):
    conv = LabelConvention.default()
    assert conv.name_of(value) == UNKNOWN
    assert conv.is_known(value) is False


def test_name_to_value_unknown_returns_none():
    conv = LabelConvention.default()
    assert conv.value_of("Z9") is None
    assert conv.value_of("not-a-vertebra") is None
    assert conv.value_of("") is None


def test_value_of_none_does_not_leak_attributeerror():
    """value_of(None) must not leak a raw AttributeError from .strip().

    value_of is documented as total/non-throwing for a missing name. A None
    argument currently leaks `'NoneType' object has no attribute 'strip'` —
    a library internal the vision says callers should never see. Acceptable:
    return None, or raise the project's typed SegQCInputError.
    """
    conv = LabelConvention.default()
    try:
        result = conv.value_of(None)  # type: ignore[arg-type]
    except SegQCInputError:
        return  # a clear, typed error is acceptable
    assert result is None


def test_convention_is_immutable_no_dict_leak():
    """The frozen convention must not leak a mutable mapping that corrupts it.

    The dataclass is frozen and the class docstring promises immutability
    ("external mutation can't leak in"). Mutating the returned value_to_name
    must not change what name_of resolves to.
    """
    conv = LabelConvention.default()
    try:
        conv.value_to_name[1] = "HACKED"  # type: ignore[index]
    except TypeError:
        pass  # an immutable mapping (e.g. MappingProxyType) correctly forbids it
    assert conv.name_of(1) == "C1"


# --------------------------------------------------------------------------- #
# Custom override
# --------------------------------------------------------------------------- #

def test_custom_override_applies_both_directions():
    """A custom mapping fully replaces the default."""
    conv = LabelConvention.from_mapping({100: "C1", 200: "L5"})
    assert conv.name_of(100) == "C1"
    assert conv.value_of("C1") == 100
    assert conv.name_of(200) == "L5"
    assert conv.value_of("L5") == 200
    # Default values no longer resolve under the override.
    assert conv.name_of(1) == UNKNOWN
    assert conv.value_of("S") is None


def test_override_round_trips():
    mapping = {5: "Foo", 6: "Bar", 7: "Baz"}
    conv = LabelConvention.from_mapping(mapping)
    for value, name in mapping.items():
        assert conv.name_of(value) == name
        assert conv.value_of(name) == value


def test_override_duplicate_name_raises():
    with pytest.raises(SegQCInputError, match="Duplicate vertebra name"):
        LabelConvention.from_mapping({1: "C1", 2: "C1"})


def test_override_duplicate_name_case_insensitive_raises():
    """Names differing only by case collide (lookup is case-insensitive)."""
    with pytest.raises(SegQCInputError, match="Duplicate vertebra name"):
        LabelConvention.from_mapping({1: "C1", 2: "c1"})


def test_override_non_integer_key_raises():
    with pytest.raises(SegQCInputError, match="must be integers"):
        LabelConvention.from_mapping({"not-an-int": "C1"})


# --------------------------------------------------------------------------- #
# Adversarial: non-integer keys must be REJECTED, not silently coerced
# (Decision 6 / from_mapping docstring: "raises ... a key is not an integer").
# `int(...)` truncates/parses non-integers, corrupting the label map — the
# vision requires keeping label maps integer and failing loudly.
# --------------------------------------------------------------------------- #

def test_override_non_integral_float_key_raises():
    """A float key like 2.5 is NOT an integer — it must raise, not truncate to 2."""
    with pytest.raises(SegQCInputError, match="must be integers"):
        LabelConvention.from_mapping({2.5: "C1"})


def test_override_string_integer_key_raises():
    """A string key like '5' is NOT an integer — it must raise, not parse to 5."""
    with pytest.raises(SegQCInputError, match="must be integers"):
        LabelConvention.from_mapping({"5": "C1"})


def test_override_float_key_cannot_silently_collide():
    """{2: 'C1', 2.5: 'C2'} must not silently collapse to a single value.

    With int()-coercion both keys become 2 and one entry is lost without any
    error — a silent duplicate-value collision that drops data. Rejecting the
    non-integer key (or detecting the collision) is required; silently winning
    is not.
    """
    with pytest.raises(SegQCInputError):
        LabelConvention.from_mapping({2: "C1", 2.5: "C2"})


def test_default_unaffected_by_override():
    """Building an override does not mutate the shared default map."""
    before = dict(DEFAULT_LABEL_MAP)
    LabelConvention.from_mapping({100: "C1"})
    assert DEFAULT_LABEL_MAP == before


# --------------------------------------------------------------------------- #
# Inventory summariser — synthetic fixtures
# --------------------------------------------------------------------------- #

def test_summarise_labelled_blocks(labelled_blocks):
    """labelled_blocks has labels {1,2,3} -> C1,C2,C3, all recognised, in order."""
    inventory = labelled_blocks.voxel_counts  # {1: 64, 2: 64, 3: 64}
    summary = summarise_inventory(inventory)

    assert isinstance(summary, InventorySummary)
    assert summary.unknown == []
    assert summary.n_unknown == 0
    assert summary.present_levels == ["C1", "C2", "C3"]
    assert summary.recognised == [
        (1, "C1", inventory[1]),
        (2, "C2", inventory[2]),
        (3, "C3", inventory[3]),
    ]


def test_summarise_empty(empty_labelmap):
    """The empty fixture (no foreground) summarises to empty collections."""
    summary = summarise_inventory(empty_labelmap.voxel_counts)
    assert summary.recognised == []
    assert summary.unknown == []
    assert summary.n_recognised == 0
    assert summary.n_unknown == 0
    assert summary.present_levels == []


def test_summarise_anisotropic(anisotropic):
    """Counts are passed through verbatim (summariser is geometry-agnostic)."""
    inventory = anisotropic.voxel_counts  # {1: 48, 2: 48}
    summary = summarise_inventory(inventory)
    assert summary.present_levels == ["C1", "C2"]
    assert summary.recognised == [
        (1, "C1", inventory[1]),
        (2, "C2", inventory[2]),
    ]


# --------------------------------------------------------------------------- #
# Inventory summariser — unknown labels, ordering
# --------------------------------------------------------------------------- #

def test_summarise_with_unknown_label():
    """A mapped label and an out-of-range label split correctly."""
    summary = summarise_inventory({20: 100, 999: 5})
    assert summary.recognised == [(20, "L1", 100)]
    assert summary.unknown == [(999, 5)]


def test_summarise_unknown_includes_negative_and_zero():
    """Negative / unmapped labels are surfaced, never dropped or crashing."""
    summary = summarise_inventory({-3: 2, 0: 7, 1: 10, 27: 4})
    # Only 1 -> C1 is recognised; -3, 0, 27 are unknown.
    assert summary.recognised == [(1, "C1", 10)]
    assert summary.unknown == [(-3, 2), (0, 7), (27, 4)]  # sorted by value


def test_summarise_orders_recognised_anatomically_not_by_value():
    """T13 (value 28) sorts between T12 (19) and L1 (20), not after them."""
    summary = summarise_inventory({20: 1, 28: 1, 19: 1})  # L1, T13, T12
    assert summary.present_levels == ["T12", "T13", "L1"]


def test_summarise_with_custom_convention():
    """A custom convention is honoured by the summariser."""
    conv = LabelConvention.from_mapping({100: "C1"})
    summary = summarise_inventory({100: 9, 1: 3}, conv)
    assert summary.recognised == [(100, "C1", 9)]
    assert summary.unknown == [(1, 3)]


def test_summarise_empty_mapping():
    summary = summarise_inventory({})
    assert summary.recognised == []
    assert summary.unknown == []


# --------------------------------------------------------------------------- #
# Adversarial invariants that SHOULD already hold (regression guards)
# --------------------------------------------------------------------------- #

def test_summarise_does_not_mutate_caller_inventory():
    """The summariser must not mutate the caller's inventory mapping."""
    inventory = {1: 10, 999: 5, -3: 2}
    snapshot = dict(inventory)
    summarise_inventory(inventory)
    assert inventory == snapshot


def test_default_factory_returns_independent_instances():
    """Two default() instances must not share mutable state with each other."""
    a = LabelConvention.default()
    b = LabelConvention.default()
    assert a.value_to_name == b.value_to_name
    # Building an override or touching one must never alter the shipped default.
    LabelConvention.from_mapping({100: "C1"})
    assert LabelConvention.default().name_of(1) == "C1"


def test_override_unicode_name_round_trips():
    """Non-ASCII names survive normalisation and round-trip in both directions."""
    conv = LabelConvention.from_mapping({1: "Vértebra", 2: "Ω-level"})
    assert conv.name_of(1) == "Vértebra"
    assert conv.value_of("vértebra".upper()) == 1
    assert conv.value_of("Ω-LEVEL") == 2


def test_summarise_large_inventory():
    """A large inventory partitions correctly and stays ordered (no crash)."""
    inventory = {i: 1 for i in range(1, 5001)}
    summary = summarise_inventory(inventory)
    # Default map covers values 1..26, 28, 29 (27 unmapped) -> 28 recognised.
    assert summary.n_recognised == len(DEFAULT_LABEL_MAP)
    assert summary.n_unknown == 5000 - len(DEFAULT_LABEL_MAP)
    # Recognised come out in canonical anatomical order.
    assert summary.present_levels[:3] == ["C1", "C2", "C3"]
    assert "T13" in summary.present_levels
    # Unknown stay sorted ascending by value.
    unknown_values = [v for v, _c in summary.unknown]
    assert unknown_values == sorted(unknown_values)


# --------------------------------------------------------------------------- #
# Integration with the loader's Case.label_inventory (item 003 -> 004)
# --------------------------------------------------------------------------- #

def test_summarise_loader_case_inventory(labelled_blocks_files):
    """End-to-end: load a fixture via item 003, summarise its inventory."""
    from segqc.io import load_case

    scan_path, seg_path = labelled_blocks_files
    case = load_case(scan_path, seg_path)
    summary = summarise_inventory(case.label_inventory)
    assert summary.present_levels == ["C1", "C2", "C3"]
    assert summary.unknown == []
    # Counts match what the loader reported.
    for value, _name, count in summary.recognised:
        assert count == case.label_inventory[value]