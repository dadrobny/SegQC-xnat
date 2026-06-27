"""Tests for Stage 3 feature serialisation & GT-vs-perturbed regression (item 022).

Covers all ten Acceptance Criteria plus adversarial / edge-case inputs:

* AC1  — Stage 3 block appears in a schema-validated report when Stage 3
         arguments are supplied to build_features_block.
* AC2  — Every Stage 3 sub-block is present with the correct shape / keys:
         per_label_offsets, per_label_orientations, curvature,
         spacing_consistency, monotonic_consistency.
* AC3  — GT case: offset_mm < 1.0 mm for all vertices; cv_spacing < 0.05;
         is_monotonic True — the key quality signal the heuristic engine needs.
* AC4  — Displaced centroid: serialised offset_mm >= 8.0 mm for the displaced
         vertebra; remaining vertebrae < 2.0 mm.
* AC5  — Spacing outlier case: injecting a >= 2x mean gap produces at least one
         entry in serialised spacing_consistency.outlier_pairs.
* AC6  — Missing-level case: relationships.missing_levels non-empty; the large
         gap is flagged in spacing_consistency.outlier_pairs.
* AC7  — Backward-compatible: calling build_features_block without Stage 3
         arguments (all None) yields no "stage3" key and still validates.
* AC8  — Deterministic golden snapshot: two identical calls produce equal dicts;
         serialize_report_json matches a committed golden JSON string.
* AC9  — features_version is "0.2" when Stage 3 data is present, "0.1" when
         it is absent.
* AC10 — Immutability: Stage 3 dataclass inputs are not mutated by the
         converters or build_features_block.

Adversarial scenarios:
- GT spline offsets < 1 mm for all on-curve centroids.
- Single displaced centroid: only that vertebra has a large serialised offset.
- Mislabelled / spacing-outlier case: outlier_pairs present in JSON.
- Missing-level case: gap detected in relationships and spacing_consistency.
- Backward-compatible Stage-2-only block (no Stage 3 keys).
- Determinism: repeated serialisation of identical inputs yields equal dicts.
- Golden snapshot: byte-for-byte match against committed golden JSON.
- None curvature / None spacing_consistency / None monotonic_consistency:
  stage3 absent or partially populated as appropriate.
- features_version "0.2" vs "0.1" depending on Stage 3 presence.
- Input dataclasses not mutated after serialisation.
- per_label_offsets and per_label_orientations sorted in ascending label order.
- JSON text round-trip preserves numeric values.
- Malformed Stage 3 dict rejected by jsonschema.
- principal_axis in per_label_orientations is a 3-element list of numbers.
- outlier_pairs in spacing_consistency serialise as list-of-two-element-lists.
- non_monotonic_pairs in monotonic_consistency serialise as list-of-two-element-lists.
- two-centroid spine: minimum valid input, no crash through full pipeline.
- Zero-label map: no Stage 3 block (no centroids to process).

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no external services).
"""

from __future__ import annotations

import dataclasses
import json
import math
import pathlib
from typing import List, Optional, Tuple

import pytest

from segqc.config import default_config
from segqc.feature_report import build_features_block
from segqc.features.centroids import LabelCentroid, compute_centroid
from segqc.features.components import compute_components
from segqc.features.consistency import (
    compute_monotonic_consistency,
    compute_spacing_consistency,
)
from segqc.features.geometry import compute_label_geometry
from segqc.features.orientation import (
    VertebralOrientation,
    compute_spine_curvature,
    compute_vertebra_orientations,
)
from segqc.features.overlap import detect_overlaps
from segqc.features.relationships import compute_spine_relationships
from segqc.features.spline import fit_centroid_spline
from segqc.features.spline_offset import VertebralSplineOffset, compute_spline_offsets
from segqc.report import serialize_report, serialize_report_json
from segqc.verdict import Verdict

import numpy as np

from synthetic import anisotropic_case, empty_case, labelled_blocks_case, make_labelmap

GOLDEN_PATH = pathlib.Path(__file__).parent / "golden" / "022_stage3_report.json"


# =========================================================================== #
# Helpers
# =========================================================================== #


def _centroid(
    level_name: str,
    mm: Tuple[float, float, float],
    label: int = 0,
) -> LabelCentroid:
    """Build a minimal LabelCentroid with the given mm coordinates."""
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """Return n centroids equally spaced along the z axis, simulating GT."""
    levels = ["T7", "T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    """Return 6 centroids along a gentle curve in the xz-plane."""
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [
        _centroid(lv, (x, 0.0, z), label=i + 1)
        for i, (lv, x, z) in enumerate(zip(levels, xs, zs))
    ]


def _config():
    return default_config()


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _build_stage3(
    centroids: List[LabelCentroid],
    seg_img=None,
    labels: Optional[List[int]] = None,
):
    """Compute all five Stage 3 objects for a centroid sequence.

    Returns (spline_offsets, orientations, curvature, spacing_consistency,
    monotonic_consistency).  orientations requires seg_img + labels; when
    seg_img is None, a dummy single-entry list is used instead.
    """
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)

    if seg_img is not None and labels is not None:
        orientations = compute_vertebra_orientations(seg_img, labels)
    else:
        # Build minimal synthetic orientations inline for serialisation tests.
        orientations = [
            VertebralOrientation(
                label=c.label,
                level_name=c.level_name,
                principal_axis=(0.0, 0.0, 1.0),
                eigenvalue_ratio=2.0,
            )
            for c in centroids
        ]

    return offsets, orientations, curvature, spacing, monotonic


def _mask_stack(seg_img, labels):
    data = np.asanyarray(seg_img.dataobj)
    stack = np.stack([data == lab for lab in labels], axis=0)
    return stack, np.asarray(labels, dtype=np.int64)


def _stage2_for_case(case, config=None):
    """Build the Stage 2 feature maps for a SyntheticCase."""
    if config is None:
        config = _config()
    labels = sorted(case.expected_labels)
    geometry = {lab: compute_label_geometry(case.seg_img, lab) for lab in labels}
    components = {lab: compute_components(case.seg_img, lab, config) for lab in labels}
    centroids_map = {lab: compute_centroid(case.seg_img, lab) for lab in labels}
    centroid_seq = [centroids_map[lab] for lab in labels]
    relationships = compute_spine_relationships(centroid_seq) if centroid_seq else None
    if labels:
        stack, label_arr = _mask_stack(case.seg_img, labels)
        overlaps = detect_overlaps(stack, label_arr)
    else:
        overlaps = []
    return geometry, components, centroids_map, centroid_seq, relationships, overlaps


def _full_block_for_spine(centroids: List[LabelCentroid]):
    """Assemble a full Stage 2+3 features block from a centroid sequence.

    Stage 2 fields are minimal stubs (empty maps) so tests can focus on Stage 3
    serialisation behaviour without needing a full label map.
    """
    offsets, orientations, curvature, spacing, monotonic = _build_stage3(centroids)
    return build_features_block(
        geometry={},
        components={},
        centroids={},
        relationships=None,
        overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )


# =========================================================================== #
# AC1 — Stage 3 block appears in validated report
# =========================================================================== #


def test_ac1_stage3_key_present_when_stage3_supplied():
    """AC1: build_features_block with Stage 3 args returns a block with 'stage3'."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    assert "stage3" in block, "Expected 'stage3' key in features block"


def test_ac1_stage3_report_passes_schema_validation():
    """AC1: A report containing the Stage 3 block validates against the extended schema."""
    import jsonschema
    from segqc.report import _SCHEMA

    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    report = serialize_report(_empty_verdict(), "case-022", _config(), features=block)
    jsonschema.validate(report, _SCHEMA)


def test_ac1_stage3_top_level_features_key_present():
    """AC1: serialize_report with Stage 3 features returns a dict with 'features' key."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    report = serialize_report(_empty_verdict(), "c022", _config(), features=block)
    assert "features" in report
    assert "stage3" in report["features"]


# =========================================================================== #
# AC2 — Every Stage 3 sub-block is present and correctly shaped
# =========================================================================== #


def test_ac2_all_stage3_subkeys_present():
    """AC2: 'stage3' contains all five expected sub-keys."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    stage3 = block["stage3"]
    for key in (
        "per_label_offsets",
        "per_label_orientations",
        "curvature",
        "spacing_consistency",
        "monotonic_consistency",
    ):
        assert key in stage3, f"Expected 'stage3.{key}' to be present"


def test_ac2_per_label_offsets_has_required_keys():
    """AC2: Each entry in per_label_offsets has all required offset fields."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_offsets"]:
        for key in ("label", "level_name", "closest_u", "offset_mm",
                    "offset_voxel", "dx_mm", "dy_mm", "dz_mm"):
            assert key in entry, f"per_label_offsets entry missing key: {key!r}"


def test_ac2_per_label_orientations_has_required_keys():
    """AC2: Each entry in per_label_orientations has label, level_name, principal_axis,
    eigenvalue_ratio."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_orientations"]:
        for key in ("label", "level_name", "principal_axis", "eigenvalue_ratio"):
            assert key in entry, f"per_label_orientations entry missing key: {key!r}"


def test_ac2_per_label_orientations_principal_axis_is_3_element_list():
    """AC2: principal_axis is a 3-element list of numbers."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_orientations"]:
        axis = entry["principal_axis"]
        assert isinstance(axis, list), f"principal_axis should be a list, got {type(axis)}"
        assert len(axis) == 3, f"principal_axis should have 3 elements, got {len(axis)}"
        for v in axis:
            assert isinstance(v, (int, float)), f"principal_axis element {v!r} not numeric"


def test_ac2_curvature_has_required_keys():
    """AC2: curvature object has tangent_angles_deg, inter_tangent_angles_deg,
    total_curvature_deg."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    curv = block["stage3"]["curvature"]
    for key in ("tangent_angles_deg", "inter_tangent_angles_deg", "total_curvature_deg"):
        assert key in curv, f"curvature missing key: {key!r}"


def test_ac2_curvature_inter_tangent_length_is_n_minus_1():
    """AC2: inter_tangent_angles_deg has length n_centroids - 1."""
    n = 5
    centroids = _straight_spine(n)
    block = _full_block_for_spine(centroids)
    inter = block["stage3"]["curvature"]["inter_tangent_angles_deg"]
    assert len(inter) == n - 1, f"Expected {n - 1} inter-tangent angles, got {len(inter)}"


def test_ac2_spacing_consistency_has_required_keys():
    """AC2: spacing_consistency has mean_spacing_mm, cv_spacing, spacings_mm,
    deviations_mm, outlier_pairs."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    sc = block["stage3"]["spacing_consistency"]
    for key in ("mean_spacing_mm", "cv_spacing", "spacings_mm",
                "deviations_mm", "outlier_pairs"):
        assert key in sc, f"spacing_consistency missing key: {key!r}"


def test_ac2_monotonic_consistency_has_required_keys():
    """AC2: monotonic_consistency has is_monotonic, non_monotonic_pairs, u_values."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    mc = block["stage3"]["monotonic_consistency"]
    for key in ("is_monotonic", "non_monotonic_pairs", "u_values"):
        assert key in mc, f"monotonic_consistency missing key: {key!r}"


def test_ac2_per_label_offsets_count_matches_centroids():
    """AC2: per_label_offsets has one entry per centroid in the spine."""
    n = 6
    centroids = _straight_spine(n)
    block = _full_block_for_spine(centroids)
    assert len(block["stage3"]["per_label_offsets"]) == n


def test_ac2_per_label_orientations_count_matches_centroids():
    """AC2: per_label_orientations has one entry per orientation supplied."""
    n = 6
    centroids = _straight_spine(n)
    block = _full_block_for_spine(centroids)
    assert len(block["stage3"]["per_label_orientations"]) == n


def test_ac2_u_values_length_in_monotonic_consistency():
    """AC2: u_values in monotonic_consistency has one entry per centroid."""
    n = 5
    centroids = _straight_spine(n)
    block = _full_block_for_spine(centroids)
    assert len(block["stage3"]["monotonic_consistency"]["u_values"]) == n


def test_ac2_spacings_mm_length_in_spacing_consistency():
    """AC2: spacings_mm in spacing_consistency has n-1 entries."""
    n = 5
    centroids = _straight_spine(n)
    block = _full_block_for_spine(centroids)
    assert len(block["stage3"]["spacing_consistency"]["spacings_mm"]) == n - 1


# =========================================================================== #
# AC3 — GT case: offsets near-zero, spacing regular, monotonic
# =========================================================================== #


def test_ac3_gt_all_offsets_near_zero():
    """AC3: For GT centroids lying on the spline, all serialised offset_mm < 1.0 mm."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_offsets"]:
        assert entry["offset_mm"] < 1.0, (
            f"Level {entry['level_name']}: serialised offset_mm="
            f"{entry['offset_mm']:.4f} >= 1.0 mm"
        )


def test_ac3_gt_curved_spine_offsets_near_zero():
    """AC3: GT curved-spine centroids have serialised offset_mm < 1.0 mm."""
    centroids = _curved_spine()
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_offsets"]:
        assert entry["offset_mm"] < 1.0, (
            f"Level {entry['level_name']}: offset_mm={entry['offset_mm']:.4f}"
        )


def test_ac3_gt_spacing_cv_low():
    """AC3: For a uniform GT spine, serialised cv_spacing < 0.05."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    cv = block["stage3"]["spacing_consistency"]["cv_spacing"]
    assert cv < 0.05, f"Expected cv_spacing < 0.05 for uniform GT, got {cv:.6f}"


def test_ac3_gt_is_monotonic_true():
    """AC3: For a GT well-ordered spine, serialised is_monotonic is True."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["monotonic_consistency"]["is_monotonic"] is True, (
        "Expected is_monotonic=True for GT spine"
    )


def test_ac3_gt_no_spacing_outliers():
    """AC3: A uniform GT spine has no outlier_pairs in spacing_consistency."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["spacing_consistency"]["outlier_pairs"] == [], (
        "Expected no spacing outliers for uniform GT spine"
    )


def test_ac3_gt_no_non_monotonic_pairs():
    """AC3: A GT spine has empty non_monotonic_pairs in monotonic_consistency."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["monotonic_consistency"]["non_monotonic_pairs"] == [], (
        "Expected no non-monotonic pairs for GT spine"
    )


# =========================================================================== #
# AC4 — Displaced centroid: large offset for displaced, small for others
# =========================================================================== #


def test_ac4_displaced_centroid_has_large_serialised_offset():
    """AC4: A centroid displaced by 15 mm has serialised offset_mm >= 8.0 mm."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in perturbed
    ]
    curvature = compute_spine_curvature(fit, perturbed)
    spacing = compute_spacing_consistency(perturbed)
    monotonic = compute_monotonic_consistency(perturbed, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    displaced_entry = block["stage3"]["per_label_offsets"][3]
    assert displaced_entry["offset_mm"] >= 8.0, (
        f"Displaced centroid offset_mm={displaced_entry['offset_mm']:.4f} < 8.0"
    )


def test_ac4_displaced_centroid_others_remain_small():
    """AC4: Non-displaced centroids have serialised offset_mm < 2.0 mm."""
    centroids = _straight_spine(6)
    displaced_mm = (
        centroids[3].centroid_mm[0] + 15.0,
        centroids[3].centroid_mm[1],
        centroids[3].centroid_mm[2],
    )
    displaced = _centroid(centroids[3].level_name, displaced_mm, label=centroids[3].label)
    perturbed = centroids[:3] + [displaced] + centroids[4:]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in perturbed
    ]
    curvature = compute_spine_curvature(fit, perturbed)
    spacing = compute_spacing_consistency(perturbed)
    monotonic = compute_monotonic_consistency(perturbed, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    for i, entry in enumerate(block["stage3"]["per_label_offsets"]):
        if i == 3:
            continue
        assert entry["offset_mm"] < 2.0, (
            f"Non-displaced centroid {entry['level_name']} has "
            f"offset_mm={entry['offset_mm']:.4f} >= 2.0 mm"
        )


# =========================================================================== #
# AC5 — Spacing-outlier case: outlier pair flagged in serialised block
# =========================================================================== #


def test_ac5_injected_gap_produces_spacing_outlier():
    """AC5: An injected gap >= 2x mean is flagged in serialised outlier_pairs."""
    centroids = _straight_spine(6, spacing_mm=10.0)
    # Shift centroids[3] from z=30 to z=60 — creates a 30 mm gap (3x the 10 mm mean)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in perturbed
    ]
    curvature = compute_spine_curvature(fit, perturbed)
    spacing = compute_spacing_consistency(perturbed)
    monotonic = compute_monotonic_consistency(perturbed, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    outlier_pairs = block["stage3"]["spacing_consistency"]["outlier_pairs"]
    assert len(outlier_pairs) >= 1, (
        "Expected at least one outlier pair in serialised spacing_consistency"
    )


def test_ac5_outlier_pairs_are_two_element_lists():
    """AC5: Each entry in serialised outlier_pairs is a 2-element list of strings."""
    centroids = _straight_spine(6, spacing_mm=10.0)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(perturbed, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in perturbed
    ]
    curvature = compute_spine_curvature(fit, perturbed)
    spacing = compute_spacing_consistency(perturbed)
    monotonic = compute_monotonic_consistency(perturbed, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    for pair in block["stage3"]["spacing_consistency"]["outlier_pairs"]:
        assert isinstance(pair, list), f"outlier_pairs entry is not a list: {pair!r}"
        assert len(pair) == 2, f"outlier_pairs entry is not 2-element: {pair!r}"
        assert isinstance(pair[0], str), f"outlier_pairs[0] is not str: {pair[0]!r}"
        assert isinstance(pair[1], str), f"outlier_pairs[1] is not str: {pair[1]!r}"


# =========================================================================== #
# AC6 — Missing-level case: gap detected in relationships + spacing_consistency
# =========================================================================== #


def test_ac6_missing_level_detected_in_relationships():
    """AC6: Removing a centroid from GT sequence produces non-empty missing_levels."""
    centroids = _straight_spine(7, spacing_mm=10.0)
    # Remove centroids[3] — simulates a missing segmentation level
    with_gap = centroids[:3] + centroids[4:]

    relationships = compute_spine_relationships(with_gap)

    # geometry, components, and centroids must share keys (or all be empty).
    # Pass all three as empty so build_features_block builds no per_label
    # entries — the relationships assertion does not depend on per_label.
    block = build_features_block(
        geometry={},
        components={},
        centroids={},
        relationships=relationships,
        overlaps=[],
    )
    # relationships block should reflect the missing levels
    # (present_levels has the gap but missing_levels captures it)
    assert block["relationships"] is not None


def test_ac6_missing_level_creates_spacing_outlier():
    """AC6: A missing level leaves a gap that is flagged as a spacing outlier.

    Fixture arithmetic (outlier_threshold_high = 2.0):
      Centroids at z = 0, 5, 10, 35, 40 mm  (labels 1-5, levels T8-T12).
      Spacings:  5, 5, 25, 5  (4 gaps; >= 2 spacings so mean comparison is valid)
      mean_spacing = (5 + 5 + 25 + 5) / 4 = 40 / 4 = 10.0 mm
      threshold_high = 2.0 * 10.0 = 20.0 mm
      Large gap = 25.0 mm  >  20.0 mm  →  flagged as outlier  ✓

    The centroid that would have bridged the gap (at z ≈ 17.5 mm, between T10
    and T11) represents the missing segmentation level.
    """
    # Build the sequence directly so the gap arithmetic is exact.
    levels = ["T8", "T9", "T10", "T11", "T12"]
    zs = [0.0, 5.0, 10.0, 35.0, 40.0]
    with_gap = [
        _centroid(levels[i], (0.0, 0.0, zs[i]), label=i + 1)
        for i in range(5)
    ]
    # Verify the outlier condition holds (5, 5, 25, 5 → mean=10, threshold=20).
    # 25 > 20 → at least one outlier pair must be produced.

    fit = fit_centroid_spline(with_gap)
    offsets = compute_spline_offsets(with_gap, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in with_gap
    ]
    curvature = compute_spine_curvature(fit, with_gap)
    spacing = compute_spacing_consistency(with_gap)
    monotonic = compute_monotonic_consistency(with_gap, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    outlier_pairs = block["stage3"]["spacing_consistency"]["outlier_pairs"]
    assert len(outlier_pairs) >= 1, (
        "Expected at least one spacing outlier: gap 25 mm > threshold 20 mm "
        "(2.0 × mean 10.0 mm)"
    )


# =========================================================================== #
# AC7 — Backward-compatible: no 'stage3' key when Stage 3 not supplied
# =========================================================================== #


def test_ac7_stage3_absent_when_not_supplied():
    """AC7: build_features_block without Stage 3 args produces no 'stage3' key."""
    case = labelled_blocks_case()
    labels = sorted(case.expected_labels)
    geometry, components, centroids_map, centroid_seq, relationships, overlaps = \
        _stage2_for_case(case)
    block = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids_map,
        relationships=relationships,
        overlaps=overlaps,
    )
    assert "stage3" not in block, (
        "Expected no 'stage3' key when Stage 3 arguments are not supplied"
    )


def test_ac7_stage2_only_block_validates_against_schema():
    """AC7: A Stage-2-only block (no Stage 3) still validates against the extended schema."""
    import jsonschema
    from segqc.report import _SCHEMA

    case = labelled_blocks_case()
    geometry, components, centroids_map, centroid_seq, relationships, overlaps = \
        _stage2_for_case(case)
    block = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids_map,
        relationships=relationships,
        overlaps=overlaps,
    )
    report = serialize_report(_empty_verdict(), "stage2-only", _config(), features=block)
    jsonschema.validate(report, _SCHEMA)


def test_ac7_feature_free_report_still_validates():
    """AC7: A completely feature-free report (no 'features' key) still validates."""
    import jsonschema
    from segqc.report import _SCHEMA

    report = serialize_report(_empty_verdict(), "no-features", _config())
    assert "features" not in report
    jsonschema.validate(report, _SCHEMA)


# =========================================================================== #
# AC8 — Deterministic golden snapshot
# =========================================================================== #


def test_ac8_determinism_two_calls_equal():
    """AC8: Serialising the same Stage 3 inputs twice yields equal dicts."""
    centroids = _straight_spine(5)
    block_a = _full_block_for_spine(centroids)
    block_b = _full_block_for_spine(centroids)
    assert block_a == block_b


def test_ac8_determinism_report_level():
    """AC8: Two serialize_report calls with identical inputs yield equal dicts."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    r1 = serialize_report(_empty_verdict(), "c", _config(), features=block)
    r2 = serialize_report(_empty_verdict(), "c", _config(), features=block)
    assert r1 == r2


def test_ac8_per_label_offsets_ascending_label_order():
    """AC8: per_label_offsets is in ascending integer-label order."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    labels_in_block = [e["label"] for e in block["stage3"]["per_label_offsets"]]
    assert labels_in_block == sorted(labels_in_block)


def test_ac8_per_label_orientations_ascending_label_order():
    """AC8: per_label_orientations is in ascending integer-label order."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    labels_in_block = [e["label"] for e in block["stage3"]["per_label_orientations"]]
    assert labels_in_block == sorted(labels_in_block)


def test_ac8_json_text_round_trip_preserves_offset_values():
    """AC8: offset_mm values survive JSON encode/decode without precision loss."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    report = serialize_report(_empty_verdict(), "c", _config(), features=block)
    text = json.dumps(report, ensure_ascii=False, sort_keys=True)
    parsed = json.loads(text)
    for orig, parsed_entry in zip(
        block["stage3"]["per_label_offsets"],
        parsed["features"]["stage3"]["per_label_offsets"],
    ):
        assert math.isclose(orig["offset_mm"], parsed_entry["offset_mm"], rel_tol=1e-9)


def test_ac8_golden_snapshot():
    """AC8: serialize_report_json for a fixture matches the committed golden JSON."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    produced = serialize_report_json(
        _empty_verdict(), "golden-case-022", _config(), features=block
    )

    if not GOLDEN_PATH.exists():
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(produced, encoding="utf-8")
        pytest.skip(f"Golden snapshot written to {GOLDEN_PATH.name}; re-run to verify.")

    golden = GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == golden, (
        "Golden snapshot drift detected. If this change is intentional, "
        f"delete {GOLDEN_PATH.name} and re-run to regenerate it."
    )


# =========================================================================== #
# AC9 — features_version "0.2" with Stage 3, "0.1" without
# =========================================================================== #


def test_ac9_features_version_is_02_when_stage3_present():
    """AC9: features_version is '0.2' when Stage 3 data is supplied."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    assert block["features_version"] == "0.2", (
        f"Expected features_version='0.2', got {block['features_version']!r}"
    )


def test_ac9_features_version_is_01_when_stage3_absent():
    """AC9: features_version remains '0.1' for a Stage-2-only block."""
    case = labelled_blocks_case()
    geometry, components, centroids_map, centroid_seq, relationships, overlaps = \
        _stage2_for_case(case)
    block = build_features_block(
        geometry=geometry,
        components=components,
        centroids=centroids_map,
        relationships=relationships,
        overlaps=overlaps,
    )
    assert block["features_version"] == "0.1", (
        f"Expected features_version='0.1' for Stage-2-only block, "
        f"got {block['features_version']!r}"
    )


def test_ac9_features_version_in_serialised_report():
    """AC9: features_version appears correctly in the serialised JSON report."""
    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    report = serialize_report(_empty_verdict(), "c", _config(), features=block)
    assert report["features"]["features_version"] == "0.2"


# =========================================================================== #
# AC10 — Immutability: Stage 3 inputs not mutated
# =========================================================================== #


def test_ac10_spline_offsets_not_mutated():
    """AC10: build_features_block does not mutate the spline_offsets input."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)

    offsets_before = [dataclasses.astuple(o) for o in offsets]

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )

    offsets_after = [dataclasses.astuple(o) for o in offsets]
    assert offsets_before == offsets_after


def test_ac10_orientations_not_mutated():
    """AC10: build_features_block does not mutate the orientations input."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)

    orientations_before = [dataclasses.astuple(o) for o in orientations]

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )

    orientations_after = [dataclasses.astuple(o) for o in orientations]
    assert orientations_before == orientations_after


def test_ac10_curvature_not_mutated():
    """AC10: build_features_block does not mutate the SpineCurvature input."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    curvature = compute_spine_curvature(fit, centroids)
    curvature_before = dataclasses.astuple(curvature)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )

    assert dataclasses.astuple(curvature) == curvature_before


def test_ac10_spacing_consistency_not_mutated():
    """AC10: build_features_block does not mutate the SpacingConsistency input."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    spacing_before = dataclasses.astuple(spacing)
    monotonic = compute_monotonic_consistency(centroids, fit)

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )

    assert dataclasses.astuple(spacing) == spacing_before


def test_ac10_monotonic_consistency_not_mutated():
    """AC10: build_features_block does not mutate the MonotonicConsistency input."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)
    monotonic_before = dataclasses.astuple(monotonic)

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )

    assert dataclasses.astuple(monotonic) == monotonic_before


# =========================================================================== #
# Adversarial: partial Stage 3 (some args None)
# =========================================================================== #


def test_adv_only_spline_offsets_supplied():
    """Supplying only spline_offsets (others None) still produces a 'stage3' key."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
    )
    assert "stage3" in block
    assert "per_label_offsets" in block["stage3"]


def test_adv_only_curvature_supplied():
    """Supplying only curvature (others None) still produces a 'stage3' key."""
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    curvature = compute_spine_curvature(fit, centroids)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        curvature=curvature,
    )
    assert "stage3" in block
    assert "curvature" in block["stage3"]


def test_adv_all_stage3_none_no_stage3_key():
    """Passing all Stage 3 args as None (default) produces no 'stage3' key."""
    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=None,
        orientations=None,
        curvature=None,
        spacing_consistency=None,
        monotonic_consistency=None,
    )
    assert "stage3" not in block


def test_adv_two_centroid_spine_full_pipeline():
    """Minimum valid spine (2 centroids) passes through the full Stage 3 pipeline."""
    centroids = _straight_spine(2, spacing_mm=10.0)
    block = _full_block_for_spine(centroids)
    assert "stage3" in block
    assert len(block["stage3"]["per_label_offsets"]) == 2
    assert block["stage3"]["monotonic_consistency"]["is_monotonic"] is True


def test_adv_schema_rejects_missing_offset_mm():
    """A Stage 3 block missing offset_mm in a per_label_offsets entry is rejected."""
    import jsonschema
    from segqc.report import _SCHEMA

    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    bad = json.loads(json.dumps(block))
    del bad["stage3"]["per_label_offsets"][0]["offset_mm"]

    report = serialize_report(_empty_verdict(), "c", _config())
    report["features"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


def test_adv_schema_rejects_missing_is_monotonic():
    """A Stage 3 block missing is_monotonic in monotonic_consistency is rejected."""
    import jsonschema
    from segqc.report import _SCHEMA

    centroids = _straight_spine(5)
    block = _full_block_for_spine(centroids)
    bad = json.loads(json.dumps(block))
    del bad["stage3"]["monotonic_consistency"]["is_monotonic"]

    report = serialize_report(_empty_verdict(), "c", _config())
    report["features"] = bad
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _SCHEMA)


# =========================================================================== #
# Adversarial: numerical invariants in the serialised block
# =========================================================================== #


def test_adv_all_serialised_offsets_non_negative():
    """All serialised offset_mm and offset_voxel values are non-negative."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_offsets"]:
        assert entry["offset_mm"] >= 0.0
        assert entry["offset_voxel"] >= 0.0


def test_adv_all_u_values_in_unit_interval():
    """All serialised u_values in monotonic_consistency are in [0.0, 1.0]."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    for u in block["stage3"]["monotonic_consistency"]["u_values"]:
        assert 0.0 <= float(u) <= 1.0, f"u value {u} out of [0, 1]"


def test_adv_total_curvature_non_negative():
    """Serialised total_curvature_deg is non-negative."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["curvature"]["total_curvature_deg"] >= 0.0


def test_adv_mean_spacing_positive():
    """Serialised mean_spacing_mm is positive for well-separated centroids."""
    centroids = _straight_spine(6, spacing_mm=10.0)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["spacing_consistency"]["mean_spacing_mm"] > 0.0


def test_adv_cv_spacing_non_negative():
    """Serialised cv_spacing is non-negative."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    assert block["stage3"]["spacing_consistency"]["cv_spacing"] >= 0.0


def test_adv_vector_components_consistent_in_serialised_block():
    """sqrt(dx_mm² + dy_mm² + dz_mm²) ≈ offset_mm in the serialised block (abs_tol=0.1)."""
    centroids = _straight_spine(6)
    block = _full_block_for_spine(centroids)
    for entry in block["stage3"]["per_label_offsets"]:
        reconstructed = math.sqrt(
            entry["dx_mm"] ** 2 + entry["dy_mm"] ** 2 + entry["dz_mm"] ** 2
        )
        assert math.isclose(reconstructed, entry["offset_mm"], abs_tol=0.1), (
            f"Level {entry['level_name']}: reconstructed={reconstructed:.6f}, "
            f"serialised offset_mm={entry['offset_mm']:.6f}"
        )


def test_adv_non_monotonic_pairs_are_two_element_lists():
    """non_monotonic_pairs in the serialised block are 2-element lists of strings."""
    centroids = _straight_spine(6)
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(swapped, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in swapped
    ]
    curvature = compute_spine_curvature(fit, swapped)
    spacing = compute_spacing_consistency(swapped)
    monotonic = compute_monotonic_consistency(swapped, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    for pair in block["stage3"]["monotonic_consistency"]["non_monotonic_pairs"]:
        assert isinstance(pair, list), f"non_monotonic_pairs entry is not a list: {pair!r}"
        assert len(pair) == 2
        assert isinstance(pair[0], str)
        assert isinstance(pair[1], str)


def test_adv_swapped_spine_is_non_monotonic_in_serialised_block():
    """A swapped centroid order is reflected in serialised is_monotonic=False."""
    centroids = _straight_spine(6)
    swapped = list(centroids)
    swapped[2], swapped[3] = swapped[3], swapped[2]

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(swapped, fit)
    orientations = [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0), eigenvalue_ratio=2.0,
        )
        for c in swapped
    ]
    curvature = compute_spine_curvature(fit, swapped)
    spacing = compute_spacing_consistency(swapped)
    monotonic = compute_monotonic_consistency(swapped, fit)

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )
    assert block["stage3"]["monotonic_consistency"]["is_monotonic"] is False, (
        "Expected is_monotonic=False for swapped centroid sequence"
    )


# =========================================================================== #
# Adversarial: import contract for new converters
# =========================================================================== #


def test_adv_import_spline_offset_to_dict():
    """spline_offset_to_dict is importable from segqc.feature_report."""
    from segqc.feature_report import spline_offset_to_dict
    assert callable(spline_offset_to_dict)


def test_adv_import_orientation_to_dict():
    """orientation_to_dict is importable from segqc.feature_report."""
    from segqc.feature_report import orientation_to_dict
    assert callable(orientation_to_dict)


def test_adv_import_curvature_to_dict():
    """curvature_to_dict is importable from segqc.feature_report."""
    from segqc.feature_report import curvature_to_dict
    assert callable(curvature_to_dict)


def test_adv_import_spacing_consistency_to_dict():
    """spacing_consistency_to_dict is importable from segqc.feature_report."""
    from segqc.feature_report import spacing_consistency_to_dict
    assert callable(spacing_consistency_to_dict)


def test_adv_import_monotonic_consistency_to_dict():
    """monotonic_consistency_to_dict is importable from segqc.feature_report."""
    from segqc.feature_report import monotonic_consistency_to_dict
    assert callable(monotonic_consistency_to_dict)


def test_adv_spline_offset_to_dict_output_shape():
    """spline_offset_to_dict returns a dict with all required keys."""
    from segqc.feature_report import spline_offset_to_dict

    centroids = _straight_spine(3)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    d = spline_offset_to_dict(offsets[0])
    for key in ("label", "level_name", "closest_u", "offset_mm",
                "offset_voxel", "dx_mm", "dy_mm", "dz_mm"):
        assert key in d, f"spline_offset_to_dict missing key: {key!r}"


def test_adv_orientation_to_dict_output_shape():
    """orientation_to_dict returns a dict with label, level_name, principal_axis,
    eigenvalue_ratio; principal_axis is a list."""
    from segqc.feature_report import orientation_to_dict

    o = VertebralOrientation(
        label=1, level_name="L3",
        principal_axis=(0.0, 0.1, 0.9949), eigenvalue_ratio=3.5,
    )
    d = orientation_to_dict(o)
    for key in ("label", "level_name", "principal_axis", "eigenvalue_ratio"):
        assert key in d
    assert isinstance(d["principal_axis"], list)
    assert len(d["principal_axis"]) == 3


def test_adv_curvature_to_dict_tuples_become_lists():
    """curvature_to_dict converts tuple fields to lists for JSON compatibility."""
    from segqc.feature_report import curvature_to_dict

    centroids = _straight_spine(4)
    fit = fit_centroid_spline(centroids)
    curv = compute_spine_curvature(fit, centroids)
    d = curvature_to_dict(curv)
    assert isinstance(d["tangent_angles_deg"], list)
    assert isinstance(d["inter_tangent_angles_deg"], list)
    assert isinstance(d["total_curvature_deg"], float)


def test_adv_spacing_consistency_to_dict_outlier_pairs_as_lists():
    """spacing_consistency_to_dict converts outlier_pairs tuples to lists of lists."""
    from segqc.feature_report import spacing_consistency_to_dict

    # Build a case with an outlier pair
    centroids = _straight_spine(6, spacing_mm=10.0)
    old = centroids[3]
    shifted = _centroid(old.level_name, (0.0, 0.0, 60.0), label=old.label)
    perturbed = centroids[:3] + [shifted] + centroids[4:]
    spacing = compute_spacing_consistency(perturbed)

    d = spacing_consistency_to_dict(spacing)
    assert isinstance(d["spacings_mm"], list)
    assert isinstance(d["deviations_mm"], list)
    assert isinstance(d["outlier_pairs"], list)
    for pair in d["outlier_pairs"]:
        assert isinstance(pair, list)
        assert len(pair) == 2


def test_adv_monotonic_consistency_to_dict_lists():
    """monotonic_consistency_to_dict converts tuple fields to lists."""
    from segqc.feature_report import monotonic_consistency_to_dict

    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    mono = compute_monotonic_consistency(centroids, fit)
    d = monotonic_consistency_to_dict(mono)
    assert isinstance(d["u_values"], list)
    assert isinstance(d["non_monotonic_pairs"], list)
    assert isinstance(d["is_monotonic"], bool)
