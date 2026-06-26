"""Tests for the features-block JSON serialisation & feature table (item 016).

Covers all eight Acceptance Criteria plus adversarial / edge-case inputs:

* AC1 — features block round-trips into a schema-validated report.
* AC2 — every feature family (geometry/components/centroid + relationships +
  overlaps) appears in the JSON.
* AC3 — anisotropic physical volumes / extents / centroid-mm round-trip exactly.
* AC4 — schema extension is backward-compatible (feature-free report still valid;
  schema_version stays "0.1").
* AC5 — deterministic output + committed golden snapshot, stable key ordering.
* AC6 — per-case human-readable feature table, no Python-internal leakage.
* AC7 — empty / single-label maps handled.
* AC8 — pure / immutable / import-clean.

The tests compute the *real* feature objects from the synthetic fixtures
(``compute_label_geometry``, ``compute_components``, ``compute_centroid``,
``detect_overlaps``, ``compute_spine_relationships``) and feed them through
``build_features_block`` → ``serialize_report`` — exercising the whole
consolidation path against actual data rather than mocks.

All tests are deterministic, CPU-only, and portable (no network, no GPU).
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import numpy as np
import pytest

from segqc.config import HeuristicConfig, default_config
from segqc.feature_report import (
    FEATURES_VERSION,
    build_features_block,
    centroid_to_dict,
    components_to_dict,
    geometry_to_dict,
    overlap_to_dict,
    relationships_to_dict,
)
from segqc.features.centroids import compute_centroid
from segqc.features.components import compute_components
from segqc.features.geometry import compute_label_geometry
from segqc.features.overlap import detect_overlaps
from segqc.features.relationships import compute_spine_relationships
from segqc.human_report import render_feature_table
from segqc.report import serialize_report, serialize_report_json
from segqc.verdict import Verdict

from synthetic import (
    anisotropic_case,
    empty_case,
    labelled_blocks_case,
    make_labelmap,
)

GOLDEN_PATH = pathlib.Path(__file__).parent / "golden" / "016_features_report.json"


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _config() -> HeuristicConfig:
    """A config with schema_version 0.1 and a zero fragment threshold."""
    return default_config()


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _mask_stack(seg_img, labels):
    """Build a (n_labels, X, Y, Z) boolean stack + label array for overlap detection."""
    data = np.asanyarray(seg_img.dataobj)
    stack = np.stack([data == lab for lab in labels], axis=0)
    return stack, np.asarray(labels, dtype=np.int64)


def _features_for_case(case, config=None):
    """Compute every Stage 2 feature for a synthetic case and assemble the block.

    Returns ``(features_block, geometry_map, components_map, centroid_map,
    relationships, overlaps)`` so individual tests can cross-check against the
    source objects.
    """
    if config is None:
        config = _config()
    labels = sorted(case.expected_labels)

    geometry = {lab: compute_label_geometry(case.seg_img, lab) for lab in labels}
    components = {lab: compute_components(case.seg_img, lab, config) for lab in labels}
    centroids = {lab: compute_centroid(case.seg_img, lab) for lab in labels}

    # Relationships consume an ordered sequence of LabelCentroid (item 014).
    centroid_seq = [centroids[lab] for lab in labels]
    relationships = (
        compute_spine_relationships(centroid_seq) if centroid_seq else None
    )

    # Overlaps consume a boolean mask stack (item 015).
    if labels:
        stack, label_arr = _mask_stack(case.seg_img, labels)
        overlaps = detect_overlaps(stack, label_arr)
    else:
        overlaps = []

    block = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
    )
    return block, geometry, components, centroids, relationships, overlaps


# =========================================================================== #
# AC1 — features block round-trips into a validated report
# =========================================================================== #


def test_ac1_features_block_validates_in_report():
    """serialize_report(..., features=block) returns a dict with a top-level
    'features' key and passes schema validation without raising."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)

    report = serialize_report(_empty_verdict(), "case-001", _config(), features=block)

    assert "features" in report
    assert report["features"]["features_version"] == FEATURES_VERSION
    # serialize_report validates against the extended schema internally; reaching
    # here without a ValidationError is the round-trip success.


def test_ac1_direct_jsonschema_validate_passes():
    """The produced report validates directly against the loaded v0 schema."""
    import jsonschema

    from segqc.report import _SCHEMA

    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    report = serialize_report(_empty_verdict(), "case-001", _config(), features=block)

    # Should not raise.
    jsonschema.validate(report, _SCHEMA)


# =========================================================================== #
# AC2 — every feature family appears in the JSON
# =========================================================================== #


def test_ac2_all_families_present():
    """Each per-label entry has geometry/components/centroid; the block has a
    relationships object and an overlaps array."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)

    assert set(block.keys()) == {
        "features_version",
        "per_label",
        "relationships",
        "overlaps",
    }
    assert block["per_label"], "per_label must not be empty for a multi-label case"
    for key, entry in block["per_label"].items():
        assert "geometry" in entry
        assert "components" in entry
        assert "centroid" in entry
        assert "label" in entry
        assert "level_name" in entry

    assert isinstance(block["overlaps"], list)
    assert block["relationships"] is not None
    assert "present_levels" in block["relationships"]


def test_ac2_per_label_keys_match_all_labels():
    """No label is silently dropped from per_label."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    expected = {str(lab) for lab in case.expected_labels}
    assert set(block["per_label"].keys()) == expected


# =========================================================================== #
# AC3 — anisotropic fixture round-trips correct physical volumes / extents
# =========================================================================== #


def test_ac3_anisotropic_physical_values_preserved():
    """Serialised geometry physical values + centroid_mm equal the source compute
    outputs exactly (float equality) for the anisotropic fixture."""
    case = anisotropic_case()
    block, geometry, _comp, centroids, _rel, _ov = _features_for_case(case)

    for lab in sorted(case.expected_labels):
        entry = block["per_label"][str(lab)]
        g = geometry[lab]
        c = centroids[lab]

        assert entry["geometry"]["physical_volume_mm3"] == g.physical_volume_mm3
        assert entry["geometry"]["extent_x_mm"] == g.extent_x_mm
        assert entry["geometry"]["extent_y_mm"] == g.extent_y_mm
        assert entry["geometry"]["extent_z_mm"] == g.extent_z_mm
        assert entry["centroid"]["centroid_mm"] == list(c.centroid_mm)
        assert entry["centroid"]["centroid_voxel"] == list(c.centroid_voxel)


def test_ac3_anisotropic_survives_json_text_round_trip():
    """Physical values survive a full JSON text encode/decode round-trip."""
    case = anisotropic_case()
    block, geometry, *_ = _features_for_case(case)
    text = serialize_report_json(_empty_verdict(), "aniso", _config(), features=block)
    parsed = json.loads(text)

    for lab in sorted(case.expected_labels):
        entry = parsed["features"]["per_label"][str(lab)]
        assert entry["geometry"]["physical_volume_mm3"] == geometry[lab].physical_volume_mm3


# =========================================================================== #
# AC4 — schema extension is backward-compatible
# =========================================================================== #


def test_ac4_feature_free_report_still_valid():
    """A report produced WITHOUT features (item-009 shape) still validates and
    carries no 'features' key."""
    report = serialize_report(_empty_verdict(), "no-features", _config())
    assert "features" not in report
    assert report["schema_version"] == "0.1"


def test_ac4_features_is_optional_property():
    """The extended schema keeps schema_version const '0.1' and lists features as
    an optional (non-required) property."""
    from segqc.report import _SCHEMA

    assert _SCHEMA["properties"]["schema_version"]["const"] == "0.1"
    assert "features" in _SCHEMA["properties"]
    assert "features" not in _SCHEMA["required"]


def test_ac4_009_style_report_validates_against_extended_schema():
    """Explicitly validate a feature-free report against the extended schema."""
    import jsonschema

    from segqc.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "no-features", _config())
    jsonschema.validate(report, _SCHEMA)


# =========================================================================== #
# AC5 — deterministic output / golden snapshot
# =========================================================================== #


def test_ac5_deterministic_repeated_serialisation():
    """Serialising the same inputs twice yields equal dicts."""
    case = labelled_blocks_case()
    block_a, *_ = _features_for_case(case)
    block_b, *_ = _features_for_case(case)
    assert block_a == block_b

    r1 = serialize_report(_empty_verdict(), "c", _config(), features=block_a)
    r2 = serialize_report(_empty_verdict(), "c", _config(), features=block_b)
    assert r1 == r2


def test_ac5_per_label_ascending_label_order():
    """per_label is assembled in ascending integer-label order."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    keys = list(block["per_label"].keys())
    assert keys == sorted(keys, key=int)


def test_ac5_overlaps_sorted_by_label_pair():
    """overlaps are sorted by (label_a, label_b) even if input is shuffled."""
    # Build a fixture with two overlapping label channels, fed in reverse order.
    case = labelled_blocks_case()
    _block, geometry, components, centroids, relationships, _ov = _features_for_case(case)

    from segqc.features.overlap import OverlapPair

    unsorted = [
        OverlapPair(label_a=2, label_b=3, name_a="C2", name_b="C3", overlap_voxels=5),
        OverlapPair(label_a=1, label_b=2, name_a="C1", name_b="C2", overlap_voxels=7),
    ]
    block = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=unsorted,
    )
    pairs = [(o["label_a"], o["label_b"]) for o in block["overlaps"]]
    assert pairs == sorted(pairs)


def test_ac5_golden_snapshot():
    """serialize_report_json for the labelled-blocks fixture equals the committed
    golden JSON string byte-for-byte."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    produced = serialize_report_json(_empty_verdict(), "golden-case", _config(), features=block)

    golden = GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == golden, (
        "Golden snapshot drift. If this change is intentional, regenerate "
        f"{GOLDEN_PATH.name}."
    )


# =========================================================================== #
# AC6 — per-case human-readable feature table
# =========================================================================== #


def test_ac6_feature_table_non_empty_and_lists_labels():
    """render_feature_table returns a non-empty str listing per-label data."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    table = render_feature_table(block)

    assert isinstance(table, str)
    assert table.strip()
    # Each level name should appear in the rendered table.
    for entry in block["per_label"].values():
        assert entry["level_name"] in table
    assert "Overlaps:" in table
    assert "Relationships:" in table


def test_ac6_feature_table_no_python_internals_leak():
    """The table contains no raw class names, repr tuples, or frozenset text."""
    case = anisotropic_case()
    block, *_ = _features_for_case(case)
    table = render_feature_table(block)

    for forbidden in (
        "frozenset",
        "BBox(",
        "LabelGeometry",
        "ComponentsInfo",
        "LabelCentroid",
        "OverlapPair",
        "SpineRelationships",
        "dict_keys",
        "(np.",
        "array(",
    ):
        assert forbidden not in table, f"leaked {forbidden!r} into feature table"


def test_ac6_feature_table_deterministic_label_order():
    """The table lists labels in ascending order regardless of dict insertion."""
    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    # Reverse the insertion order of per_label to prove the renderer re-sorts.
    block["per_label"] = dict(reversed(list(block["per_label"].items())))

    table = render_feature_table(block)
    # Positions of each level name should be in ascending-label order.
    positions = [
        table.index(block["per_label"][str(lab)]["level_name"])
        for lab in sorted(int(k) for k in block["per_label"])
    ]
    assert positions == sorted(positions)


# =========================================================================== #
# AC7 — empty / single-label maps handled
# =========================================================================== #


def test_ac7_single_label_map():
    """A single-label map yields empty overlaps and a <=1 entry relationships."""
    seg = make_labelmap(blocks={1: ((2, 6), (2, 6), (2, 6))})

    class _Case:
        seg_img = seg
        expected_labels = frozenset({1})

    block, *_ = _features_for_case(_Case())

    assert block["overlaps"] == []
    assert len(block["per_label"]) == 1
    assert block["relationships"] is not None
    assert len(block["relationships"]["present_levels"]) <= 1
    assert block["relationships"]["neighbour_spacings_mm"] == []

    # Still validates + renders.
    serialize_report(_empty_verdict(), "single", _config(), features=block)
    assert render_feature_table(block).strip()


def test_ac7_zero_label_map():
    """A zero-label map yields empty per_label/overlaps and validates + renders."""
    case = empty_case()
    block, *_ = _features_for_case(case)

    assert block["per_label"] == {}
    assert block["overlaps"] == []
    # relationships is None (no centroids) -> serialises to null, still valid.
    assert block["relationships"] is None

    report = serialize_report(_empty_verdict(), "empty", _config(), features=block)
    assert report["features"]["relationships"] is None
    assert render_feature_table(block).strip()


def test_ac7_relationships_none_serialises_to_json_null():
    """A None relationships round-trips through JSON text as null."""
    case = empty_case()
    block, *_ = _features_for_case(case)
    text = serialize_report_json(_empty_verdict(), "empty", _config(), features=block)
    assert json.loads(text)["features"]["relationships"] is None


# =========================================================================== #
# AC8 — pure / immutable / import-clean
# =========================================================================== #


def test_ac8_inputs_not_mutated():
    """The converters and assembler do not mutate their dataclass inputs."""
    case = labelled_blocks_case()
    _block, geometry, components, centroids, relationships, overlaps = _features_for_case(case)

    # Snapshot the source dataclasses, run conversion again, assert unchanged.
    geom_before = {k: dataclasses.astuple(v) for k, v in geometry.items()}
    comp_before = {k: dataclasses.astuple(v) for k, v in components.items()}
    cent_before = {k: dataclasses.astuple(v) for k, v in centroids.items()}

    build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
    )

    assert {k: dataclasses.astuple(v) for k, v in geometry.items()} == geom_before
    assert {k: dataclasses.astuple(v) for k, v in components.items()} == comp_before
    assert {k: dataclasses.astuple(v) for k, v in centroids.items()} == cent_before


def test_ac8_returned_lists_not_aliased():
    """Mutating a list inside the returned block does not touch the source."""
    case = labelled_blocks_case()
    _block, _g, components, *_ = _features_for_case(case)
    lab = next(iter(components))
    d = components_to_dict(components[lab])
    original = list(components[lab].component_sizes)
    d["component_sizes"].append(999999)
    assert list(components[lab].component_sizes) == original


def test_ac8_no_heavy_imports_in_feature_report_module():
    """segqc.feature_report imports no numpy/nibabel/scipy at module level."""
    import segqc.feature_report as fr

    g = vars(fr)
    for forbidden in ("numpy", "np", "nibabel", "nib", "scipy"):
        assert forbidden not in g, f"{forbidden} leaked into feature_report globals"


def test_ac8_converters_are_pure_functions():
    """Calling a converter twice yields equal (but independent) dicts."""
    case = labelled_blocks_case()
    _block, geometry, _comp, centroids, relationships, overlaps = _features_for_case(case)
    lab = next(iter(geometry))

    assert geometry_to_dict(geometry[lab]) == geometry_to_dict(geometry[lab])
    assert centroid_to_dict(centroids[lab]) == centroid_to_dict(centroids[lab])
    assert relationships_to_dict(relationships) == relationships_to_dict(relationships)
    assert relationships_to_dict(None) is None
    assert [overlap_to_dict(o) for o in overlaps] == [overlap_to_dict(o) for o in overlaps]


# =========================================================================== #
# Adversarial — malformed feature dict rejected by direct validation
# =========================================================================== #


def test_malformed_features_rejected_by_schema():
    """A features block missing a required key is rejected by jsonschema."""
    import jsonschema

    from segqc.report import _SCHEMA

    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    # Drop a required key from a per_label geometry entry.
    bad = json.loads(json.dumps(block))  # deep copy
    some_label = next(iter(bad["per_label"]))
    del bad["per_label"][some_label]["geometry"]["voxel_count"]

    report = serialize_report(_empty_verdict(), "c", _config())
    report["features"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_unknown_feature_key_rejected():
    """additionalProperties:false rejects an unexpected key in the features block."""
    import jsonschema

    from segqc.report import _SCHEMA

    case = labelled_blocks_case()
    block, *_ = _features_for_case(case)
    bad = json.loads(json.dumps(block))
    bad["unexpected_key"] = 123

    report = serialize_report(_empty_verdict(), "c", _config())
    report["features"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)
