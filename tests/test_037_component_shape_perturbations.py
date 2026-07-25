"""Tests for item 037 — component & shape perturbations: fragment, fuse,
inject_islands.

Covers Acceptance Criteria AC1-AC22:

- AC1-AC6 (Group A, ``fragment``): registration; splits target into >=2
  comparable disconnected pieces; bounding box preserved / bounds stays
  silent; fires the fragmentation-kind finding; Expectation is well-formed
  and the pipeline agrees; un-perturbed present labels stay unflagged.
- AC7-AC12 (Group B, ``fuse``): registration; absorbs an adjacent neighbour;
  the surviving label fires the fragmentation-kind finding; Expectation is
  well-formed and the pipeline agrees; un-perturbed present labels stay
  unflagged; a single-label input raises FacetInputError.
- AC13-AC18 (Group C, ``inject_islands``): registration; adds a tiny
  disconnected component; the injected island does not read as
  fragmentation; fires the island-kind finding; Expectation is well-formed
  and the pipeline agrees; no border/overlap finding and only the target is
  flagged.
- AC19-AC22 (Group D, cross-cutting): dtype/affine/shape/zooms preservation;
  same-seed reproducibility; non-mutation of the caller's input; unspecified
  target selection is seed-deterministic and the Expectation is
  self-consistent with the pipeline.

Adversarial / edge-case scenarios included:
- ``fragment`` / ``inject_islands`` with an explicit target absent from the
  map raise FacetInputError rather than silently no-op-ing.
- ``fuse`` with an explicit non-adjacent pair raises FacetInputError.
- Each operator still fires its designated rule and preserves spacing under
  anisotropic spacing.
- Two different seeds with an unspecified target may pick different labels,
  but each result stays self-consistent with its own Expectation.
- The injected island's small volume does not push the target below the
  ``bounds`` rule's ``min_volume_mm3`` (no spurious ``bounds`` finding).
"""

from __future__ import annotations

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of the three operators
from segfacet.config import bundled_default_config
from segfacet.features.components import compute_components
from segfacet.features.geometry import compute_label_geometry
from segfacet.heuristics.bounds import DEFAULT_BOUNDS
from segfacet.heuristics.fragmentation import (
    DEFAULT_FRAGMENTATION_INDEX_THRESHOLD,
    DEFAULT_ISLAND_MIN_VOXELS,
)
from segfacet.io import FacetInputError
from segfacet.pipeline import run_qc
from segfacet.synth import (
    FAILURE_MODE_NAMES,
    build_clean_spine,
    get_perturbation,
    iter_perturbations,
    perturbation_names,
)
from segfacet.synth.component_shape import (
    FragmentPerturbation,
    FusePerturbation,
    InjectIslandsPerturbation,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _clean():
    return build_clean_spine()


def _findings(labelmap):
    case_result, _block = run_qc(labelmap, bundled_default_config())
    return case_result.findings


def _flagged_present_labels(findings):
    """Union of every non-empty finding.labels (present-label attribution)."""
    result = set()
    for finding in findings:
        result |= set(finding.labels)
    return result


# Explicit-target operator factories shared by the cross-cutting AC19-AC21
# parametrizations.
_EXPLICIT_TARGET_FACTORIES = [
    lambda: FragmentPerturbation(target_label=22),
    lambda: FusePerturbation(target_label=20, neighbour_label=21),
    lambda: InjectIslandsPerturbation(target_label=22),
]

# Unspecified-target operator factories shared by AC22 and the adversarial
# seed-varying test.
_UNSPECIFIED_TARGET_FACTORIES = [
    lambda: FragmentPerturbation(),
    lambda: FusePerturbation(),
    lambda: InjectIslandsPerturbation(),
]

_OPERATOR_IDS = ["fragment", "fuse", "inject_islands"]


# =========================================================================== #
# A. fragment (AC1-AC6)
# =========================================================================== #


def test_ac1_fragment_registered_under_fragment_name():
    """AC1: get_perturbation("fragment") is FragmentPerturbation; "fragment"
    is in perturbation_names() and iter_perturbations()."""
    assert get_perturbation("fragment") is FragmentPerturbation
    assert "fragment" in perturbation_names()
    assert FragmentPerturbation in list(iter_perturbations())


def test_ac2_fragment_splits_target_into_comparable_disconnected_pieces():
    """AC2: component_count >= 2, fragmentation_index < 0.75, and every
    non-dominant component is >= island_min_voxels (a genuine fragment)."""
    clean = _clean()
    cfg = bundled_default_config()
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    comp = compute_components(result.labelmap, 22, cfg)
    assert comp.component_count >= 2
    assert comp.largest_component_fraction < DEFAULT_FRAGMENTATION_INDEX_THRESHOLD
    for size in comp.component_sizes[1:]:
        assert size >= DEFAULT_ISLAND_MIN_VOXELS


def test_ac3_fragment_preserves_bounding_box_and_bounds_stays_silent():
    """AC3: extent_x/y/z_mm are unchanged and no "bounds" finding fires."""
    clean = _clean()
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    geo_before = compute_label_geometry(clean.seg_img, 22)
    geo_after = compute_label_geometry(result.labelmap, 22)
    assert geo_after.extent_x_mm == geo_before.extent_x_mm
    assert geo_after.extent_y_mm == geo_before.extent_y_mm
    assert geo_after.extent_z_mm == geo_before.extent_z_mm
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "bounds" for f in findings)


def test_ac4_fragment_fires_fragmentation_kind_finding_on_target():
    """AC4: a Finding with rule_id == "fragmentation", reason starting
    "Fragmentation:", and labels == frozenset({22})."""
    clean = _clean()
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "fragmentation"
        and f.reason.startswith("Fragmentation:")
        and f.labels == frozenset({22})
    ]
    assert matches


def test_ac5_fragment_expectation_well_formed_and_pipeline_agrees():
    """AC5: Expectation fields are pinned and verdict.overall.label matches."""
    clean = _clean()
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 2
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[2]
    assert exp.expected_rule_ids == frozenset({"fragmentation"})
    assert exp.expected_labels == frozenset({22})
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac6_fragment_leaves_other_present_labels_unflagged():
    """AC6: every finding.labels is a subset of {22}."""
    clean = _clean()
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    for f in findings:
        assert f.labels <= frozenset({22})


# =========================================================================== #
# B. fuse (AC7-AC12)
# =========================================================================== #


def test_ac7_fuse_registered_under_fuse_name():
    """AC7: get_perturbation("fuse") is FusePerturbation; "fuse" is in
    perturbation_names()."""
    assert get_perturbation("fuse") is FusePerturbation
    assert "fuse" in perturbation_names()


def test_ac8_fuse_absorbs_adjacent_neighbour_into_target():
    """AC8: label 21 is absent from the fused map; label 20's voxel count
    equals the sum of the clean GT's label-20 and label-21 counts."""
    clean = _clean()
    result = FusePerturbation(target_label=20, neighbour_label=21).apply(
        clean.seg_img, seed=0
    )
    data = np.asanyarray(result.labelmap.dataobj)
    present = {int(v) for v in np.unique(data) if v != 0}
    assert 21 not in present
    fused_count = int(np.count_nonzero(data == 20))
    assert fused_count == clean.voxel_counts[20] + clean.voxel_counts[21]


def test_ac9_fused_surviving_label_fires_fragmentation_kind_finding():
    """AC9: compute_components(20) shows >=2 components and index < 0.75;
    run_qc emits a "Fragmentation:" finding on {20}."""
    clean = _clean()
    cfg = bundled_default_config()
    result = FusePerturbation(target_label=20, neighbour_label=21).apply(
        clean.seg_img, seed=0
    )
    comp = compute_components(result.labelmap, 20, cfg)
    assert comp.component_count >= 2
    assert comp.largest_component_fraction < DEFAULT_FRAGMENTATION_INDEX_THRESHOLD
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "fragmentation"
        and f.reason.startswith("Fragmentation:")
        and f.labels == frozenset({20})
    ]
    assert matches


def test_ac10_fuse_expectation_well_formed_and_pipeline_agrees():
    """AC10: Expectation fields are pinned (rule id included) and
    verdict.overall.label matches."""
    clean = _clean()
    result = FusePerturbation(target_label=20, neighbour_label=21).apply(
        clean.seg_img, seed=0
    )
    exp = result.expectation
    assert exp.failure_mode == 2
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[2]
    assert "fragmentation" in exp.expected_rule_ids
    assert exp.expected_labels == frozenset({20})
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac11_fuse_leaves_other_present_labels_unflagged():
    """AC11: every finding.labels is a subset of {20} (the case-level
    coverage finding for the now-missing level carries labels == frozenset())."""
    clean = _clean()
    result = FusePerturbation(target_label=20, neighbour_label=21).apply(
        clean.seg_img, seed=0
    )
    findings = _findings(result.labelmap)
    for f in findings:
        assert f.labels <= frozenset({20})


def test_ac12_fuse_rejects_input_with_fewer_than_two_labels():
    """AC12: applying FusePerturbation() to a single-label map raises
    FacetInputError."""
    single = build_clean_spine(levels=["L3"]).seg_img
    with pytest.raises(FacetInputError):
        FusePerturbation().apply(single, seed=0)


# =========================================================================== #
# C. inject_islands (AC13-AC18)
# =========================================================================== #


def test_ac13_inject_islands_registered_under_inject_islands_name():
    """AC13: get_perturbation("inject_islands") is InjectIslandsPerturbation;
    "inject_islands" is in perturbation_names()."""
    assert get_perturbation("inject_islands") is InjectIslandsPerturbation
    assert "inject_islands" in perturbation_names()


def test_ac14_inject_islands_adds_tiny_disconnected_component():
    """AC14: component_count >= 2 and at least one non-dominant component is
    strictly below island_min_voxels (50)."""
    clean = _clean()
    cfg = bundled_default_config()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    comp = compute_components(result.labelmap, 22, cfg)
    assert comp.component_count >= 2
    assert any(size < DEFAULT_ISLAND_MIN_VOXELS for size in comp.component_sizes[1:])


def test_ac15_injected_island_does_not_read_as_fragmentation():
    """AC15: largest_component_fraction stays >= 0.75 and no
    "Fragmentation:" finding is attributed to label 22."""
    clean = _clean()
    cfg = bundled_default_config()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    comp = compute_components(result.labelmap, 22, cfg)
    assert comp.largest_component_fraction >= DEFAULT_FRAGMENTATION_INDEX_THRESHOLD
    findings = _findings(result.labelmap)
    assert not any(
        f.reason.startswith("Fragmentation:") and 22 in f.labels for f in findings
    )


def test_ac16_inject_islands_fires_island_kind_finding_on_target():
    """AC16: a Finding with rule_id == "fragmentation", reason starting
    "Rogue island(s):", and labels == frozenset({22})."""
    clean = _clean()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "fragmentation"
        and f.reason.startswith("Rogue island(s):")
        and f.labels == frozenset({22})
    ]
    assert matches


def test_ac17_inject_islands_expectation_well_formed_and_pipeline_agrees():
    """AC17: Expectation fields are pinned and verdict.overall.label matches."""
    clean = _clean()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 3
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[3]
    assert exp.expected_rule_ids == frozenset({"fragmentation"})
    assert exp.expected_labels == frozenset({22})
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac18_inject_islands_no_border_or_overlap_and_only_target_flagged():
    """AC18: no "border" or "overlap" finding fires, and every finding's
    labels is a subset of {22}."""
    clean = _clean()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "border" for f in findings)
    assert not any(f.rule_id == "overlap" for f in findings)
    for f in findings:
        assert f.labels <= frozenset({22})


# =========================================================================== #
# D. Cross-cutting: geometry, determinism, immutability, seeding (AC19-AC22)
# =========================================================================== #


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac19_preserves_dtype_and_geometry(make_operator):
    """AC19: output dtype, affine, shape, and spacing all match the input."""
    clean = _clean()
    result = make_operator().apply(clean.seg_img, seed=0)
    in_data = np.asanyarray(clean.seg_img.dataobj)
    out_data = np.asanyarray(result.labelmap.dataobj)
    assert out_data.dtype == in_data.dtype
    assert np.array_equal(result.labelmap.affine, clean.seg_img.affine)
    assert out_data.shape == in_data.shape
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
    )


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac20_reproducible_same_seed_and_input_yields_identical_array(make_operator):
    """AC20: two apply(seed=7) calls with the same explicit target return
    np.array_equal outputs."""
    clean = _clean()
    r1 = make_operator().apply(clean.seg_img, seed=7)
    r2 = make_operator().apply(clean.seg_img, seed=7)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac21_apply_does_not_mutate_callers_input_array(make_operator):
    """AC21: the seg_img's data array is unchanged after apply() returns."""
    clean = _clean()
    data_before = np.array(np.asanyarray(clean.seg_img.dataobj), copy=True)
    make_operator().apply(clean.seg_img, seed=0)
    data_after = np.asanyarray(clean.seg_img.dataobj)
    assert np.array_equal(data_before, data_after)


@pytest.mark.parametrize(
    "make_operator", _UNSPECIFIED_TARGET_FACTORIES, ids=_OPERATOR_IDS
)
def test_ac22_unspecified_target_is_seed_deterministic_and_self_consistent(
    make_operator,
):
    """AC22: two apply(seed=3) calls with no explicit target select the same
    label (identical output arrays), and the pipeline flags exactly
    result.expectation.expected_labels."""
    clean = _clean()
    r1 = make_operator().apply(clean.seg_img, seed=3)
    r2 = make_operator().apply(clean.seg_img, seed=3)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)

    findings = _findings(r1.labelmap)
    flagged = _flagged_present_labels(findings)
    assert flagged == r1.expectation.expected_labels


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_fragment_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    FacetInputError rather than silently no-op-ing."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        FragmentPerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_inject_islands_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    FacetInputError rather than silently no-op-ing."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        InjectIslandsPerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_fuse_explicit_non_adjacent_pair_raises():
    """Adversarial: fuse requires the target/neighbour pair to be adjacent;
    a non-adjacent explicit pair raises FacetInputError."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        FusePerturbation(target_label=20, neighbour_label=23).apply(
            clean.seg_img, seed=0
        )


def test_adv_fuse_explicit_neighbour_absent_raises():
    """Adversarial: an explicit neighbour_label not present in the map
    raises FacetInputError."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        FusePerturbation(target_label=20, neighbour_label=999).apply(
            clean.seg_img, seed=0
        )


def test_adv_fragment_anisotropic_spacing_still_fires_and_preserves_spacing():
    """Adversarial: fragment on an anisotropic clean GT still fires the
    fragmentation-kind finding and preserves spacing (voxel-count-based
    thresholds are spacing-independent)."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    result = FragmentPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
    )
    findings = _findings(result.labelmap)
    assert any(
        f.rule_id == "fragmentation"
        and f.reason.startswith("Fragmentation:")
        and f.labels == frozenset({22})
        for f in findings
    )


def test_adv_fuse_anisotropic_spacing_still_fires_and_preserves_spacing():
    """Adversarial: fuse on an anisotropic clean GT still fires the
    fragmentation-kind finding on the surviving label and preserves spacing."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    result = FusePerturbation(target_label=20, neighbour_label=21).apply(
        clean.seg_img, seed=0
    )
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
    )
    findings = _findings(result.labelmap)
    assert any(
        f.rule_id == "fragmentation" and f.labels == frozenset({20}) for f in findings
    )


def test_adv_inject_islands_anisotropic_spacing_still_fires_and_preserves_spacing():
    """Adversarial: inject_islands on an anisotropic clean GT still fires
    the island-kind finding and preserves spacing (island_min_voxels is a
    voxel count, independent of spacing)."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
    )
    findings = _findings(result.labelmap)
    assert any(
        f.rule_id == "fragmentation"
        and f.reason.startswith("Rogue island(s):")
        and f.labels == frozenset({22})
        for f in findings
    )


@pytest.mark.parametrize(
    "make_operator", _UNSPECIFIED_TARGET_FACTORIES, ids=_OPERATOR_IDS
)
def test_adv_different_seeds_unspecified_target_stay_self_consistent(make_operator):
    """Adversarial: two different seeds with an unspecified target may pick
    different labels, but each result stays self-consistent -- the pipeline
    flags exactly that result's expectation.expected_labels."""
    clean = _clean()
    for seed in (1, 42):
        result = make_operator().apply(clean.seg_img, seed=seed)
        findings = _findings(result.labelmap)
        flagged = _flagged_present_labels(findings)
        assert flagged == result.expectation.expected_labels


def test_adv_inject_islands_does_not_trip_bounds_min_volume():
    """Adversarial: the injected island's small volume does not push the
    target below the bounds rule's min_volume_mm3 (no spurious "bounds"
    finding)."""
    clean = _clean()
    result = InjectIslandsPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    geo = compute_label_geometry(result.labelmap, 22)
    bounds = DEFAULT_BOUNDS["lumbar"]
    assert geo.physical_volume_mm3 >= bounds["min_volume_mm3"]
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "bounds" for f in findings)
