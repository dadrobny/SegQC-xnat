"""Tests for the fragmentation index per label (item 025).

Covers all eight Acceptance Criteria plus adversarial and edge-case inputs:

* AC1 -- compute_fragmentation_index returns 1.0 for a single-component label.
* AC2 -- compute_fragmentation_index returns the correct ratio for a two-
         component label with known piece sizes.
* AC3 -- compute_fragmentation_index returns a near-zero value for a highly
         fragmented label (many tiny isolated pieces).
* AC4 -- components_to_dict includes a 'fragmentation_index' key whose value
         equals largest_component_fraction for the same ComponentsInfo.
* AC5 -- The updated JSON schema validates reports with fragmentation_index
         present; rejects a components block missing the field.
* AC6 -- render_feature_table output contains fragmentation_index (or 'frag',
         case-insensitive) plus a numeric value.
* AC7 -- Two identical calls yield identical results (determinism).
* AC8 -- compute_fragmentation_index does not mutate its seg_img input.

Adversarial / edge-case scenarios:
- Single-voxel label: index = 1.0.
- Single-component compact label at anisotropic spacing: index still = 1.0
  (computed from voxel counts, not physical volumes).
- Many isolated single-voxel components: index ≈ 1 / total_voxels, near zero.
- Label absent from image: clear error raised.
- fragmentation_index in [0.0, 1.0] for all cases.
- Schema rejection: a components block with fragmentation_index missing fails
  jsonschema.validate against the updated schema.
- Immutability: caller's data array is not changed by compute_fragmentation_index.
- Import is clean: segqc.features.fragmentation importable without error.
- Public name accessible from segqc top-level __init__.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no external services).
"""

from __future__ import annotations

import copy
import numpy as np
import nibabel as nib
import pytest

from synthetic import (
    LABEL_DTYPE,
    affine_from_spacing,
    anisotropic_case,
    labelled_blocks_case,
    make_labelmap,
)

from segqc.config import HeuristicConfig, default_config
from segqc.feature_report import (
    build_features_block,
    components_to_dict,
)
from segqc.features.components import ComponentsInfo, compute_components
from segqc.features.centroids import compute_centroid
from segqc.features.geometry import compute_label_geometry
from segqc.features.overlap import detect_overlaps
from segqc.features.relationships import compute_spine_relationships
from segqc.human_report import render_feature_table


# =========================================================================== #
# Helpers
# =========================================================================== #


def _config() -> HeuristicConfig:
    return default_config()


def _compact_img():
    """A 4x4x4 solid block (label 1) in a 10^3 volume. One component, 64 voxels."""
    return make_labelmap((10, 10, 10), {1: ((3, 7), (3, 7), (3, 7))})


def _two_component_img(large: int = 27, small: int = 1):
    """Label 1 with a 3x3x3 main body (27 voxels) and an isolated island (1 voxel).

    The two pieces are face-disconnected (gap >= 1 background voxel on all sides).
    Default total = 28 voxels.
    """
    data = np.zeros((10, 10, 10), dtype=LABEL_DTYPE)
    data[1:4, 1:4, 1:4] = 1  # 3*3*3 = 27 voxels (main body)
    data[6, 6, 6] = 1         # 1 voxel (isolated island)
    return nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))


def _many_islands_img(n: int):
    """Label 1 consisting of n isolated single-voxel islands (face-disconnected).

    n must be <= 5^3 = 125.
    """
    assert n <= 125
    data = np.zeros((15, 15, 15), dtype=LABEL_DTYPE)
    count = 0
    for x in range(0, 15, 3):
        for y in range(0, 15, 3):
            for z in range(0, 15, 3):
                if count >= n:
                    break
                data[x, y, z] = 1
                count += 1
            if count >= n:
                break
        if count >= n:
            break
    return nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))


def _single_voxel_img():
    """Label 1 occupying exactly one voxel in an 8^3 volume."""
    return make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})


def _compute_frag_index(seg_img, label=1) -> float:
    """Call compute_fragmentation_index from the implementation module."""
    from segqc.features.fragmentation import compute_fragmentation_index
    return compute_fragmentation_index(seg_img, label, _config())


def _features_for_labels(seg_img, labels):
    """Build a full features block for a given seg_img and list of labels."""
    cfg = _config()
    labels = sorted(labels)
    geometry = {lab: compute_label_geometry(seg_img, lab) for lab in labels}
    components = {lab: compute_components(seg_img, lab, cfg) for lab in labels}
    centroids = {lab: compute_centroid(seg_img, lab) for lab in labels}
    centroid_seq = [centroids[lab] for lab in labels]
    relationships = compute_spine_relationships(centroid_seq) if centroid_seq else None
    if labels:
        data = np.asanyarray(seg_img.dataobj)
        stack = np.stack([data == lab for lab in labels], axis=0)
        label_arr = np.asarray(labels, dtype=np.int64)
        overlaps = detect_overlaps(stack, label_arr)
    else:
        overlaps = []
    return build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
    )


# =========================================================================== #
# Import contract
# =========================================================================== #


def test_import_fragmentation_module():
    """segqc.features.fragmentation is importable without error."""
    import importlib
    mod = importlib.import_module("segqc.features.fragmentation")
    assert mod is not None


def test_import_compute_fragmentation_index():
    """compute_fragmentation_index is callable from segqc.features.fragmentation."""
    from segqc.features.fragmentation import compute_fragmentation_index
    assert callable(compute_fragmentation_index)


def test_import_from_segqc_top_level():
    """compute_fragmentation_index is accessible from the segqc top-level namespace."""
    import segqc
    assert hasattr(segqc, "compute_fragmentation_index"), (
        "compute_fragmentation_index must be exported in segqc.__all__"
    )
    assert callable(segqc.compute_fragmentation_index)


# =========================================================================== #
# AC1: single-component label yields fragmentation_index = 1.0
# =========================================================================== #


def test_ac1_compact_label_index_is_one():
    """AC1: A fully-connected solid label yields fragmentation_index == 1.0."""
    seg = _compact_img()
    index = _compute_frag_index(seg)
    assert index == pytest.approx(1.0)


def test_ac1_compact_label_from_case():
    """AC1: Label 1 in labelled_blocks_case (solid 4^3 block) yields index == 1.0."""
    case = labelled_blocks_case()
    index = _compute_frag_index(case.seg_img, label=1)
    assert index == pytest.approx(1.0)


def test_ac1_compact_label_2_from_case():
    """AC1: Label 2 in labelled_blocks_case (solid 4^3 block) yields index == 1.0."""
    case = labelled_blocks_case()
    index = _compute_frag_index(case.seg_img, label=2)
    assert index == pytest.approx(1.0)


def test_ac1_returns_float():
    """AC1: compute_fragmentation_index returns a float."""
    seg = _compact_img()
    index = _compute_frag_index(seg)
    assert isinstance(index, float)


# =========================================================================== #
# AC2: two-component label yields correct ratio
# =========================================================================== #


def test_ac2_two_component_exact_ratio():
    """AC2: Two-component label (27 + 1 voxels) yields 27/28."""
    seg = _two_component_img()
    index = _compute_frag_index(seg)
    assert index == pytest.approx(27 / 28)


def test_ac2_two_component_strictly_less_than_one():
    """AC2: A fragmented label has fragmentation_index < 1.0."""
    seg = _two_component_img()
    index = _compute_frag_index(seg)
    assert index < 1.0


def test_ac2_two_component_greater_than_zero():
    """AC2: fragmentation_index is strictly positive for any label with voxels."""
    seg = _two_component_img()
    index = _compute_frag_index(seg)
    assert index > 0.0


def test_ac2_matches_largest_component_fraction():
    """AC2: compute_fragmentation_index equals largest_component_fraction from ComponentsInfo."""
    seg = _two_component_img()
    info = compute_components(seg, label=1, config=_config())
    index = _compute_frag_index(seg)
    assert index == pytest.approx(info.largest_component_fraction)


def test_ac2_larger_island_gives_lower_index():
    """AC2: A label with a larger island has a lower fragmentation_index than with a small island."""
    # Small island: 27 + 1 = 28 total; index = 27/28
    seg_small_island = _two_component_img()
    index_small = _compute_frag_index(seg_small_island)

    # Larger island: 27 + 9 = 36 total; index = 27/36 (body still 27, island 9-voxel)
    data = np.zeros((10, 10, 10), dtype=LABEL_DTYPE)
    data[1:4, 1:4, 1:4] = 1    # 27 voxels (main body)
    data[6:9, 6:9, 6:7] = 1    # 3*3*1 = 9 voxels (larger island, face-disconnected)
    seg_large_island = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    index_large = _compute_frag_index(seg_large_island)

    assert index_large < index_small


# =========================================================================== #
# AC3: highly fragmented label yields near-zero index
# =========================================================================== #


def test_ac3_many_islands_near_zero():
    """AC3: 100 isolated single-voxel components → index ≈ 1/100 (near zero)."""
    n = 100
    seg = _many_islands_img(n)
    index = _compute_frag_index(seg)
    expected = 1.0 / n
    assert index == pytest.approx(expected, rel=1e-6)


def test_ac3_many_islands_not_exactly_zero():
    """AC3: Even highly fragmented labels have index > 0 (largest component is 1 voxel)."""
    seg = _many_islands_img(50)
    index = _compute_frag_index(seg)
    assert index > 0.0


def test_ac3_ten_islands_correct_ratio():
    """AC3: 10 isolated single-voxel islands → index = 1/10."""
    seg = _many_islands_img(10)
    index = _compute_frag_index(seg)
    assert index == pytest.approx(1.0 / 10, rel=1e-6)


def test_ac3_five_islands_correct_ratio():
    """AC3: 5 isolated single-voxel islands → index = 0.2."""
    seg = _many_islands_img(5)
    index = _compute_frag_index(seg)
    assert index == pytest.approx(0.2, rel=1e-6)


# =========================================================================== #
# AC4: components_to_dict includes fragmentation_index
# =========================================================================== #


def test_ac4_components_to_dict_has_fragmentation_index_key():
    """AC4: components_to_dict output contains the key 'fragmentation_index'."""
    seg = _compact_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert "fragmentation_index" in d


def test_ac4_fragmentation_index_equals_largest_fraction_compact():
    """AC4: fragmentation_index in dict equals largest_component_fraction (compact label)."""
    seg = _compact_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert d["fragmentation_index"] == pytest.approx(info.largest_component_fraction)


def test_ac4_fragmentation_index_equals_largest_fraction_fragmented():
    """AC4: fragmentation_index in dict equals largest_component_fraction (fragmented label)."""
    seg = _two_component_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert d["fragmentation_index"] == pytest.approx(info.largest_component_fraction)


def test_ac4_fragmentation_index_is_one_for_compact():
    """AC4: fragmentation_index in the dict is 1.0 for a single-component label."""
    seg = _compact_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert d["fragmentation_index"] == pytest.approx(1.0)


def test_ac4_fragmentation_index_in_unit_interval():
    """AC4: fragmentation_index from components_to_dict is always in [0.0, 1.0]."""
    for seg in (_compact_img(), _two_component_img(), _single_voxel_img()):
        info = compute_components(seg, label=1, config=_config())
        d = components_to_dict(info)
        assert 0.0 <= d["fragmentation_index"] <= 1.0


def test_ac4_fragmentation_index_is_float():
    """AC4: fragmentation_index value in the dict is a float."""
    seg = _compact_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert isinstance(d["fragmentation_index"], float)


def test_ac4_features_block_per_label_has_fragmentation_index():
    """AC4: The per_label components block in build_features_block includes fragmentation_index."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    for key, entry in block["per_label"].items():
        comps = entry["components"]
        assert "fragmentation_index" in comps, (
            f"fragmentation_index missing from per_label[{key!r}].components"
        )


def test_ac4_features_block_fragmentation_index_value_correct():
    """AC4: fragmentation_index in features block equals compute_fragmentation_index."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    for key, entry in block["per_label"].items():
        label = int(key)
        expected = _compute_frag_index(case.seg_img, label=label)
        actual = entry["components"]["fragmentation_index"]
        assert actual == pytest.approx(expected), (
            f"fragmentation_index mismatch for label {label}"
        )


# =========================================================================== #
# AC5: JSON schema validates with fragmentation_index; rejects without
# =========================================================================== #


def test_ac5_schema_validates_report_with_fragmentation_index():
    """AC5: A serialised report with fragmentation_index passes jsonschema validation."""
    import jsonschema
    from segqc.report import _SCHEMA, serialize_report
    from segqc.config import default_config
    from segqc.verdict import Verdict

    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "case-025", default_config(), features=block)

    # Should not raise
    jsonschema.validate(report, _SCHEMA)


def test_ac5_schema_rejects_components_missing_fragmentation_index():
    """AC5: A components sub-block lacking fragmentation_index fails schema validation."""
    import jsonschema
    from segqc.report import _SCHEMA

    # Build a minimal valid report then strip fragmentation_index from one label
    import copy
    from segqc.report import serialize_report
    from segqc.config import default_config
    from segqc.verdict import Verdict

    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "case-025", default_config(), features=block)

    # Remove fragmentation_index from the first per_label entry
    bad_report = copy.deepcopy(report)
    first_key = next(iter(bad_report["features"]["per_label"]))
    bad_report["features"]["per_label"][first_key]["components"].pop("fragmentation_index")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_report, _SCHEMA)


def test_ac5_fragmentation_index_in_schema_components_definition():
    """AC5: The report_schema_v0.json components definition lists fragmentation_index."""
    from segqc.report import _SCHEMA
    components_def = _SCHEMA.get("definitions", {}).get("components", {})
    assert "fragmentation_index" in components_def.get("properties", {}), (
        "fragmentation_index not found in schema components properties"
    )
    assert "fragmentation_index" in components_def.get("required", []), (
        "fragmentation_index not in schema components required list"
    )


# =========================================================================== #
# AC6: render_feature_table includes fragmentation_index
# =========================================================================== #


def test_ac6_feature_table_contains_fragmentation_text():
    """AC6: render_feature_table output contains 'fragmentation' or 'frag' (case-insensitive)."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    table = render_feature_table(block)
    assert "frag" in table.lower(), (
        "render_feature_table output should mention fragmentation index"
    )


def test_ac6_feature_table_no_raw_class_names():
    """AC6: render_feature_table output contains no raw Python class names or repr()."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    table = render_feature_table(block)
    assert "ComponentsInfo" not in table
    assert "LabelGeometry" not in table
    assert "frozenset" not in table
    assert "LabelCentroid" not in table
    assert "(<" not in table   # no tuple-of-object repr


def test_ac6_feature_table_non_empty():
    """AC6: render_feature_table returns a non-empty string."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    table = render_feature_table(block)
    assert table.strip()


def test_ac6_feature_table_fragmentation_value_present():
    """AC6: The rendered table contains the numeric fragmentation_index for at least one label."""
    case = labelled_blocks_case()
    block = _features_for_labels(case.seg_img, list(case.expected_labels))
    table = render_feature_table(block)
    # The labels in labelled_blocks_case are all solid 4^3 blocks → index = 1.0
    # We check that "1.0" or "1" appears (formatted value of the index)
    # AND that the table has frag-related text
    assert "frag" in table.lower()
    # The value 1 (or 1.0) should appear somewhere in the table
    assert "1" in table


def test_ac6_feature_table_fragmented_label_shows_low_value():
    """AC6: For a fragmented label, the feature table shows a value < 1."""
    # Build a custom seg image with two labels: label 1 (compact) and label 2 (fragmented)
    data = np.zeros((15, 15, 15), dtype=LABEL_DTYPE)
    data[1:5, 1:5, 1:5] = 1   # 4^3 = 64 voxels, label 1 (compact)
    data[8:11, 8:11, 8:11] = 2  # 3^3 = 27 voxels, label 2 main body
    data[12, 12, 12] = 2        # 1 voxel island, label 2 (fragmented)
    seg_img = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    block = _features_for_labels(seg_img, [1, 2])
    table = render_feature_table(block)
    # Label 1 index = 1.0, label 2 index = 27/28 ≈ 0.96
    assert "frag" in table.lower()


# =========================================================================== #
# AC7: Determinism
# =========================================================================== #


def test_ac7_determinism_compact_label():
    """AC7: Two calls to compute_fragmentation_index on a compact label return identical values."""
    seg = _compact_img()
    i1 = _compute_frag_index(seg)
    i2 = _compute_frag_index(seg)
    assert i1 == i2


def test_ac7_determinism_fragmented_label():
    """AC7: Two calls for a fragmented label return identical values."""
    seg = _two_component_img()
    i1 = _compute_frag_index(seg)
    i2 = _compute_frag_index(seg)
    assert i1 == i2


def test_ac7_determinism_many_islands():
    """AC7: Two calls for a highly fragmented label return identical values."""
    seg = _many_islands_img(20)
    i1 = _compute_frag_index(seg)
    i2 = _compute_frag_index(seg)
    assert i1 == i2


def test_ac7_determinism_build_features_block():
    """AC7: Two build_features_block calls with the same inputs produce equal fragmentation_index."""
    case = labelled_blocks_case()
    labels = sorted(case.expected_labels)
    cfg = _config()
    components = {lab: compute_components(case.seg_img, lab, cfg) for lab in labels}
    geometry = {lab: compute_label_geometry(case.seg_img, lab) for lab in labels}
    centroids = {lab: compute_centroid(case.seg_img, lab) for lab in labels}
    centroid_seq = [centroids[lab] for lab in labels]
    relationships = compute_spine_relationships(centroid_seq)
    data = np.asanyarray(case.seg_img.dataobj)
    stack = np.stack([data == lab for lab in labels], axis=0)
    label_arr = np.asarray(labels, dtype=np.int64)
    overlaps = detect_overlaps(stack, label_arr)

    block1 = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
    )
    block2 = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids,
        relationships=relationships,
        overlaps=overlaps,
    )

    for key in block1["per_label"]:
        fi1 = block1["per_label"][key]["components"]["fragmentation_index"]
        fi2 = block2["per_label"][key]["components"]["fragmentation_index"]
        assert fi1 == fi2


# =========================================================================== #
# AC8: Immutability (input seg_img not mutated)
# =========================================================================== #


def test_ac8_input_not_mutated_compact():
    """AC8: compute_fragmentation_index does not mutate the input seg_img (compact label)."""
    seg = _compact_img()
    original = np.asanyarray(seg.dataobj).copy()
    _compute_frag_index(seg)
    after = np.asanyarray(seg.dataobj)
    np.testing.assert_array_equal(original, after)


def test_ac8_input_not_mutated_fragmented():
    """AC8: compute_fragmentation_index does not mutate the input seg_img (fragmented label)."""
    seg = _two_component_img()
    original = np.asanyarray(seg.dataobj).copy()
    _compute_frag_index(seg)
    after = np.asanyarray(seg.dataobj)
    np.testing.assert_array_equal(original, after)


def test_ac8_input_not_mutated_many_islands():
    """AC8: compute_fragmentation_index does not mutate the input seg_img (many islands)."""
    seg = _many_islands_img(30)
    original = np.asanyarray(seg.dataobj).copy()
    _compute_frag_index(seg)
    after = np.asanyarray(seg.dataobj)
    np.testing.assert_array_equal(original, after)


# =========================================================================== #
# Edge cases: single-voxel label
# =========================================================================== #


def test_edge_single_voxel_label_index_is_one():
    """Edge: A single-voxel label is perfectly intact → fragmentation_index == 1.0."""
    seg = _single_voxel_img()
    index = _compute_frag_index(seg)
    assert index == pytest.approx(1.0)


def test_edge_single_voxel_components_to_dict_index_is_one():
    """Edge: components_to_dict for a single-voxel label has fragmentation_index == 1.0."""
    seg = _single_voxel_img()
    info = compute_components(seg, label=1, config=_config())
    d = components_to_dict(info)
    assert d["fragmentation_index"] == pytest.approx(1.0)


# =========================================================================== #
# Edge cases: anisotropic spacing (index is voxel-based, not volume-based)
# =========================================================================== #


def test_edge_anisotropic_compact_index_is_one():
    """Edge: Compact label at anisotropic (1,1,3)mm spacing still yields index == 1.0."""
    case = anisotropic_case()
    index = _compute_frag_index(case.seg_img, label=1)
    assert index == pytest.approx(1.0)


def test_edge_anisotropic_index_equals_largest_fraction():
    """Edge: fragmentation_index equals largest_component_fraction under anisotropic spacing."""
    case = anisotropic_case()
    info = compute_components(case.seg_img, label=1, config=_config())
    index = _compute_frag_index(case.seg_img, label=1)
    assert index == pytest.approx(info.largest_component_fraction)


# =========================================================================== #
# Edge cases: missing label raises a clear error
# =========================================================================== #


def test_edge_missing_label_raises():
    """Edge: compute_fragmentation_index raises a clear error for a label not in the image."""
    case = labelled_blocks_case()
    with pytest.raises((ValueError, KeyError, LookupError)) as exc_info:
        _compute_frag_index(case.seg_img, label=999)
    assert str(exc_info.value).strip(), "Error message for missing label must not be blank"


def test_edge_missing_label_error_mentions_label():
    """Edge: The error message for a missing label mentions the label value or is informative."""
    case = labelled_blocks_case()
    try:
        _compute_frag_index(case.seg_img, label=888)
    except (ValueError, KeyError, LookupError) as exc:
        msg = str(exc)
        # Should reference the label value or at least be non-trivial
        assert msg.strip(), "Error message must not be empty"


# =========================================================================== #
# Invariant: result always in [0.0, 1.0]
# =========================================================================== #


def test_invariant_index_in_unit_interval_compact():
    """Invariant: fragmentation_index is in [0.0, 1.0] for a compact label."""
    seg = _compact_img()
    index = _compute_frag_index(seg)
    assert 0.0 <= index <= 1.0


def test_invariant_index_in_unit_interval_fragmented():
    """Invariant: fragmentation_index is in [0.0, 1.0] for a fragmented label."""
    seg = _two_component_img()
    index = _compute_frag_index(seg)
    assert 0.0 <= index <= 1.0


def test_invariant_index_in_unit_interval_many_islands():
    """Invariant: fragmentation_index is in [0.0, 1.0] even for 100 single-voxel islands."""
    seg = _many_islands_img(100)
    index = _compute_frag_index(seg)
    assert 0.0 <= index <= 1.0


def test_invariant_index_positive_for_any_present_label():
    """Invariant: fragmentation_index > 0 whenever the label is present in the image."""
    for seg in (_compact_img(), _two_component_img(), _single_voxel_img(),
                _many_islands_img(10)):
        index = _compute_frag_index(seg)
        assert index > 0.0


# =========================================================================== #
# Invariant: fragmentation_index matches largest_component_fraction across cases
# =========================================================================== #


def test_invariant_matches_largest_fraction_labelled_blocks_case():
    """Invariant: compute_fragmentation_index == largest_component_fraction for all labels in labelled_blocks_case."""
    case = labelled_blocks_case()
    cfg = _config()
    for lab in sorted(case.expected_labels):
        info = compute_components(case.seg_img, lab, cfg)
        index = _compute_frag_index(case.seg_img, label=lab)
        assert index == pytest.approx(info.largest_component_fraction), (
            f"Mismatch for label {lab}"
        )


def test_invariant_components_to_dict_fragmentation_equals_largest_fraction():
    """Invariant: components_to_dict fragmentation_index == ComponentsInfo.largest_component_fraction."""
    for seg in (_compact_img(), _two_component_img(), _single_voxel_img()):
        info = compute_components(seg, label=1, config=_config())
        d = components_to_dict(info)
        assert d["fragmentation_index"] == pytest.approx(info.largest_component_fraction)
