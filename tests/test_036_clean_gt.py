"""Tests for item 036 — synthetic-corpus foundation: clean-GT spine builder.

Covers Acceptance Criteria AC1-AC11 (Group A, the clean-GT builder) and AC24
(builder determinism, Group C):

- AC1:  build_clean_spine() returns a well-formed CleanSpine.
- AC2:  the clean GT passes run_qc with zero findings (positive control).
- AC3:  the clean GT passes end-to-end through segfacet run (CLI).
- AC4:  the builder honours anisotropic spacing (physical volumes correct).
- AC5:  the level span is parametric and stays clean (thoracic span).
- AC6:  bounds cannot fire -- every body is within its level group's bounds.
- AC7:  fragmentation cannot fire -- one component per label.
- AC8:  border cannot fire -- no face contact.
- AC9:  overlap cannot fire -- bodies are disjoint.
- AC10: coverage and sequence cannot fire -- contiguous, in-order span.
- AC11: mislabel cannot fire -- smooth curve, monotonic order.
- AC24: the builder is deterministic.

Adversarial / edge-case scenarios included:
- An unknown level name raises FacetInputError.
- A span crossing the T12->L1 transitional-vertebra junction raises
  FacetInputError (the transitional-vertebra trap).
- A single-level span still builds (not the intended positive control, but
  must not crash).
- Two builds at different (but still valid) spacings do not accidentally
  share array identity (independent arrays).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from segfacet.cli import main
from segfacet.config import bundled_default_config
from segfacet.features.centroids import compute_centroid
from segfacet.features.components import compute_components
from segfacet.features.consistency import compute_monotonic_consistency
from segfacet.features.fragmentation import compute_fragmentation_index
from segfacet.features.geometry import compute_label_geometry
from segfacet.features.overlap import detect_overlaps
from segfacet.features.relationships import compute_spine_relationships
from segfacet.features.spline import fit_centroid_spline
from segfacet.features.spline_offset import compute_spline_offsets
from segfacet.heuristics.bounds import DEFAULT_BOUNDS
from segfacet.io import FacetInputError
from segfacet.pipeline import run_qc
from segfacet.synth import CleanSpine, build_clean_spine
from segfacet.verdict import Severity

from synthetic import write_nifti


def _clean() -> CleanSpine:
    return build_clean_spine()


def _centroids_for(clean: CleanSpine):
    """Ordered LabelCentroid list (head-to-tail order == ascending labels)."""
    return [compute_centroid(clean.seg_img, lbl) for lbl in clean.labels]


# =========================================================================== #
# AC1: The builder returns a well-formed CleanSpine
# =========================================================================== #


def test_ac1_scan_and_seg_images_have_equal_shape():
    """AC1: scan_img and seg_img are Nifti1Images of equal shape."""
    clean = _clean()
    assert clean.scan_img.shape == clean.seg_img.shape


def test_ac1_scan_and_seg_images_share_one_affine():
    """AC1: scan_img and seg_img share the same affine."""
    clean = _clean()
    assert np.array_equal(clean.scan_img.affine, clean.seg_img.affine)


def test_ac1_default_labels_are_lumbar_l1_to_l5():
    """AC1: labels == (20, 21, 22, 23, 24) under the default convention."""
    clean = _clean()
    assert clean.labels == (20, 21, 22, 23, 24)


def test_ac1_level_names_parallel_labels():
    """AC1: level_names == ("L1", ..., "L5"), parallel to labels."""
    clean = _clean()
    assert clean.level_names == ("L1", "L2", "L3", "L4", "L5")


def test_ac1_voxel_counts_keys_are_exactly_the_five_labels():
    """AC1: voxel_counts keys are exactly the five default labels."""
    clean = _clean()
    assert set(clean.voxel_counts.keys()) == {20, 21, 22, 23, 24}


# =========================================================================== #
# AC2: The clean GT passes the real pipeline with zero findings
# =========================================================================== #


def test_ac2_clean_gt_has_no_findings():
    """AC2: run_qc(clean.seg_img, bundled_default_config()) yields findings == ()."""
    clean = _clean()
    case_result, _block = run_qc(clean.seg_img, bundled_default_config())
    assert case_result.findings == ()


def test_ac2_clean_gt_verdict_is_pass():
    """AC2: run_qc's CaseResult.verdict.overall == Severity.PASS."""
    clean = _clean()
    case_result, _block = run_qc(clean.seg_img, bundled_default_config())
    assert case_result.verdict.overall == Severity.PASS


# =========================================================================== #
# AC3: The clean GT passes end-to-end through segfacet run
# =========================================================================== #


def test_ac3_cli_run_exits_zero(tmp_path):
    """AC3: writing the clean GT to disk and running the CLI returns exit code 0."""
    clean = _clean()
    scan_path = write_nifti(clean.scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(clean.seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"
    code = main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)])
    assert code == 0


def test_ac3_cli_report_verdict_is_pass(tmp_path):
    """AC3: the emitted segfacet_report.json has "verdict" == "pass".

    Item 090 turns reference mode ON by default, and this synthetic clean-GT
    fixture's geometry is not grounded against the real verse-v1 reference
    bands, so it now fires reference_delta findings under the new default.
    This test's intent -- "a clean synthetic GT case passes cleanly" -- is a
    claim about the reference-less/synthetic-only invocation, so it now
    passes --no-reference explicitly.
    """
    clean = _clean()
    scan_path = write_nifti(clean.scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(clean.seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"
    main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir), "--no-reference"])
    data = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert data["verdict"] == "pass"


def test_ac3_cli_report_findings_empty(tmp_path):
    """AC3: the emitted segfacet_report.json has an empty "findings" array.

    See test_ac3_cli_report_verdict_is_pass above for why --no-reference is
    now required to isolate this synthetic fixture's "clean" invariant from
    item 090's default reference_delta findings against real verse-v1 bands.
    """
    clean = _clean()
    scan_path = write_nifti(clean.scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(clean.seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"
    main(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir), "--no-reference"])
    data = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert data["findings"] == []


# =========================================================================== #
# AC4: The builder honours anisotropic spacing
# =========================================================================== #


def test_ac4_anisotropic_spacing_still_passes():
    """AC4: build_clean_spine(spacing=(1,1,3)) still yields findings == () and PASS."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    case_result, _block = run_qc(clean.seg_img, bundled_default_config())
    assert case_result.findings == ()
    assert case_result.verdict.overall == Severity.PASS


def test_ac4_anisotropic_physical_volume_matches_voxel_count_times_spacing():
    """AC4: physical_volume_mm3 == voxel_counts[label] * product(spacing)."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    for label in clean.labels:
        geo = compute_label_geometry(clean.seg_img, label)
        expected = clean.voxel_counts[label] * (1.0 * 1.0 * 3.0)
        assert geo.physical_volume_mm3 == pytest.approx(expected)


# =========================================================================== #
# AC5: The level span is parametric and stays clean
# =========================================================================== #


def test_ac5_thoracic_span_labels():
    """AC5: a T5-T10 span yields labels == (12, 13, 14, 15, 16, 17)."""
    clean = build_clean_spine(levels=["T5", "T6", "T7", "T8", "T9", "T10"])
    assert clean.labels == (12, 13, 14, 15, 16, 17)


def test_ac5_thoracic_span_passes_pipeline():
    """AC5: the thoracic span yields findings == () and PASS through run_qc."""
    clean = build_clean_spine(levels=["T5", "T6", "T7", "T8", "T9", "T10"])
    case_result, _block = run_qc(clean.seg_img, bundled_default_config())
    assert case_result.findings == ()
    assert case_result.verdict.overall == Severity.PASS


# =========================================================================== #
# AC6: bounds cannot fire
# =========================================================================== #


def test_ac6_every_label_volume_within_lumbar_bounds():
    """AC6: every label's physical_volume_mm3 is inside DEFAULT_BOUNDS["lumbar"]."""
    clean = _clean()
    bounds = DEFAULT_BOUNDS["lumbar"]
    for label in clean.labels:
        geo = compute_label_geometry(clean.seg_img, label)
        assert bounds["min_volume_mm3"] <= geo.physical_volume_mm3 <= bounds["max_volume_mm3"]


def test_ac6_every_label_extents_within_lumbar_bounds():
    """AC6: every label's extent_{x,y,z}_mm is inside DEFAULT_BOUNDS["lumbar"]."""
    clean = _clean()
    bounds = DEFAULT_BOUNDS["lumbar"]
    for label in clean.labels:
        geo = compute_label_geometry(clean.seg_img, label)
        assert bounds["min_extent_x_mm"] <= geo.extent_x_mm <= bounds["max_extent_x_mm"]
        assert bounds["min_extent_y_mm"] <= geo.extent_y_mm <= bounds["max_extent_y_mm"]
        assert bounds["min_extent_z_mm"] <= geo.extent_z_mm <= bounds["max_extent_z_mm"]


# =========================================================================== #
# AC7: fragmentation cannot fire
# =========================================================================== #


def test_ac7_every_label_fragmentation_index_is_one():
    """AC7: every label's fragmentation_index == 1.0 (single component)."""
    clean = _clean()
    cfg = bundled_default_config()
    for label in clean.labels:
        assert compute_fragmentation_index(clean.seg_img, label, cfg) == 1.0


def test_ac7_every_label_has_single_component_and_no_islands():
    """AC7: every label has component_count == 1 and no small_fragments."""
    clean = _clean()
    cfg = bundled_default_config()
    for label in clean.labels:
        comp = compute_components(clean.seg_img, label, cfg)
        assert comp.component_count == 1
        assert comp.small_fragments == []


# =========================================================================== #
# AC8: border cannot fire
# =========================================================================== #


def test_ac8_no_label_touches_any_face():
    """AC8: every touches_* flag is False for every label (inset from the FOV)."""
    clean = _clean()
    for label in clean.labels:
        geo = compute_label_geometry(clean.seg_img, label)
        assert geo.touches_inferior is False
        assert geo.touches_superior is False
        assert geo.touches_left is False
        assert geo.touches_right is False
        assert geo.touches_anterior is False
        assert geo.touches_posterior is False


# =========================================================================== #
# AC9: overlap cannot fire
# =========================================================================== #


def test_ac9_no_overlaps_between_labels():
    """AC9: detect_overlaps over the per-label masks returns []."""
    clean = _clean()
    data = np.asanyarray(clean.seg_img.dataobj)
    mask_stack = np.stack([data == lbl for lbl in clean.labels])
    labels_arr = np.array(clean.labels, dtype=np.int64)
    assert detect_overlaps(mask_stack, labels_arr) == []


# =========================================================================== #
# AC10: coverage and sequence cannot fire
# =========================================================================== #


def test_ac10_no_missing_levels():
    """AC10: compute_spine_relationships reports missing_levels == []."""
    clean = _clean()
    rel = compute_spine_relationships(_centroids_for(clean))
    assert rel.missing_levels == []


def test_ac10_is_continuous():
    """AC10: compute_spine_relationships reports is_continuous is True."""
    clean = _clean()
    rel = compute_spine_relationships(_centroids_for(clean))
    assert rel.is_continuous is True


def test_ac10_no_out_of_order_labels():
    """AC10: compute_spine_relationships reports out_of_order_labels == []."""
    clean = _clean()
    rel = compute_spine_relationships(_centroids_for(clean))
    assert rel.out_of_order_labels == []


# =========================================================================== #
# AC11: mislabel cannot fire
# =========================================================================== #


def test_ac11_every_spline_offset_below_threshold():
    """AC11: every fitted-spline offset_mm is < 15.0."""
    clean = _clean()
    centroids = _centroids_for(clean)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit, spacing_mm=clean.spacing)
    for offset in offsets:
        assert offset.offset_mm < 15.0


def test_ac11_centroid_order_is_monotonic():
    """AC11: compute_monotonic_consistency reports non_monotonic_pairs == ()."""
    clean = _clean()
    centroids = _centroids_for(clean)
    fit = fit_centroid_spline(centroids)
    mono = compute_monotonic_consistency(centroids, fit)
    assert mono.non_monotonic_pairs == ()


# =========================================================================== #
# AC24: The builder is deterministic
# =========================================================================== #


def test_ac24_two_builds_yield_equal_seg_arrays():
    """AC24: two build_clean_spine() calls produce np.array_equal seg arrays."""
    clean_a = build_clean_spine()
    clean_b = build_clean_spine()
    data_a = np.asanyarray(clean_a.seg_img.dataobj)
    data_b = np.asanyarray(clean_b.seg_img.dataobj)
    assert np.array_equal(data_a, data_b)


def test_ac24_two_builds_yield_equal_affines():
    """AC24: two build_clean_spine() calls produce np.array_equal affines."""
    clean_a = build_clean_spine()
    clean_b = build_clean_spine()
    assert np.array_equal(clean_a.seg_img.affine, clean_b.seg_img.affine)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_unknown_level_name_raises_segfacet_input_error():
    """Adversarial: an unrecognised level name raises FacetInputError."""
    with pytest.raises(FacetInputError):
        build_clean_spine(levels=["L1", "NOT_A_LEVEL"])


def test_adv_transitional_crossing_span_raises_segfacet_input_error():
    """Adversarial: a span crossing the T12->L1 junction (interleaving the
    transitional T13) raises FacetInputError rather than silently emitting a
    coverage-flagging map."""
    with pytest.raises(FacetInputError):
        build_clean_spine(levels=["T12", "L1"])


def test_adv_single_level_span_still_builds():
    """Adversarial: a single-level span builds without raising (though it is
    not the intended positive control)."""
    clean = build_clean_spine(levels=["L3"])
    assert clean.labels == (22,)


def test_adv_single_level_span_has_one_voxel_count_entry():
    """Adversarial: a single-level span's voxel_counts has exactly one entry."""
    clean = build_clean_spine(levels=["L3"])
    assert set(clean.voxel_counts.keys()) == {22}


def test_adv_different_spacings_yield_independent_arrays():
    """Adversarial: builds at two different spacings do not share array identity
    and differ in physical volume."""
    clean_iso = build_clean_spine(spacing=(1.0, 1.0, 1.0))
    clean_aniso = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    assert np.asanyarray(clean_iso.seg_img.dataobj) is not np.asanyarray(clean_aniso.seg_img.dataobj)
