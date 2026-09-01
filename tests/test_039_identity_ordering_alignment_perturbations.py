"""Tests for item 039 — identity, ordering & alignment perturbations:
displace, relabel_swap, sequence_break.

Covers Acceptance Criteria AC1-AC24:

- AC1-AC6 (Group A, ``displace``): registration; leave-one-out offset clears
  the mislabel threshold; body translated wholesale (single component,
  preserved voxel count, no bounds/fragmentation/border finding); fires the
  misalignment finding via a reconstructed ``per_label_offsets`` record fed
  to ``MislabelRule`` directly; since item 120 promoted a held-out per-label
  spline offset into the pipeline, plain ``run_qc`` now fires ``mislabel`` on
  the displaced label too (no longer a documented limitation); Expectation
  well-formed.
- AC7-AC13 (Group B, ``relabel_swap``): registration; swaps two adjacent
  bodies' identities while preserving the present-label set; the swap is
  non-monotonic on the true spatial (stacking-axis) curve; fires the
  ordering-inconsistency finding via a reconstructed ``monotonic_consistency``
  record fed to ``MislabelRule`` directly (same structural limitation);
  ``run_qc`` stays silent (empty findings, ``pass``); Expectation
  well-formed; rejects a too-small or non-adjacent input.
- AC14-AC19 (Group C, ``sequence_break``): registration; relabels the tail
  vertebra L5 (24) to the transitional label T13 (28); fires the
  ``"Non-continuous label sequence:"`` finding on ``{28}`` via the REAL
  ``run_qc`` pipeline (this operator exploits a genuine label-value/rank
  divergence, unlike displace/relabel_swap); only ``sequence`` fires (no
  spurious ``coverage``); Expectation well-formed and pipeline agrees;
  rejects a degenerate input.
- AC20-AC24 (Group D, cross-cutting): dtype/affine/shape/zooms preservation;
  same-seed reproducibility; non-mutation of the caller's input; unspecified
  target selection is seed-deterministic and self-consistent; spacing-aware
  under anisotropic spacing.

Adversarial / edge-case scenarios included:
- ``displace`` / ``sequence_break`` with an explicit target not present raise
  ``FacetInputError``.
- ``displace`` with a ``displacement_mm`` too large to fit the FOV margins
  raises ``FacetInputError``.
- ``relabel_swap`` swapping a different adjacent pair (23<->24) still fires
  the ordering finding on exactly that pair via the reconstruction.
- Two different seeds with an unspecified target may pick different
  offenders, but each result stays self-consistent.
- ``sequence_break`` with an explicit interior target still fires
  ``sequence`` but co-fires a case-level ``coverage`` finding (documented).
"""

from __future__ import annotations

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of the three operators
from segfacet.config import bundled_default_config
from segfacet.features.centroids import compute_centroid
from segfacet.features.components import compute_components
from segfacet.features.consistency import compute_monotonic_consistency
from segfacet.features.spline import fit_centroid_spline
from segfacet.features.spline_offset import compute_spline_offsets
from segfacet.heuristics.mislabel import MislabelRule
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth import (
    FAILURE_MODE_NAMES,
    build_clean_spine,
    get_perturbation,
    iter_perturbations,
    perturbation_names,
)
from segfacet.synth.axes import si_axis
from segfacet.synth.identity_ordering_alignment import (
    DisplacePerturbation,
    RelabelSwapPerturbation,
    SequenceBreakPerturbation,
)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _clean():
    return build_clean_spine()


def _findings(labelmap):
    case_result, _block = run_qc(labelmap, bundled_default_config())
    return case_result.findings


def _present_labels(labelmap):
    data = np.asanyarray(labelmap.dataobj)
    return sorted(int(v) for v in np.unique(data) if v != 0)


def _loo_offset(labelmap, label):
    """The leave-one-out offset of *label*: fit the spline through every
    OTHER present label's centroid, then measure *label*'s centroid offset
    to that fit (spacing-aware)."""
    present = _present_labels(labelmap)
    others = [l for l in present if l != label]
    other_centroids = [compute_centroid(labelmap, l) for l in others]
    fit = fit_centroid_spline(other_centroids)
    target_centroid = compute_centroid(labelmap, label)
    spacing = tuple(float(z) for z in labelmap.header.get_zooms()[:3])
    offsets = compute_spline_offsets([target_centroid], fit, spacing_mm=spacing)
    return offsets[0].offset_mm


def _reconstruct_mono_pairs(labelmap):
    """Fit the spline through the perturbed map's centroids ordered by TRUE
    spatial (stacking-axis voxel) position, then assess the ascending-label
    centroid sequence's monotonicity against it -- exposing an identity swap
    that run_qc's ascending-label refit hides. The stacking axis is resolved
    from the volume's own affine (item 116, via
    ``segfacet.synth.axes.si_axis``), not a hardcoded index."""
    present = _present_labels(labelmap)
    ascending_centroids = [compute_centroid(labelmap, l) for l in present]
    stacking_axis = si_axis(labelmap.affine)
    spatial_centroids = sorted(
        ascending_centroids, key=lambda c: c.centroid_voxel[stacking_axis]
    )
    fit = fit_centroid_spline(spatial_centroids)
    mono = compute_monotonic_consistency(ascending_centroids, fit)
    return mono.non_monotonic_pairs


# Explicit-target operator factories shared by the cross-cutting AC20-AC22
# parametrizations.
_EXPLICIT_TARGET_FACTORIES = [
    lambda: DisplacePerturbation(target_label=22),
    lambda: RelabelSwapPerturbation(target_label=21, neighbour_label=22),
    lambda: SequenceBreakPerturbation(target_label=24),
]

# Unspecified-target operator factories shared by AC23 (displace / relabel_swap
# only -- sequence_break's default target is the deterministic tail, not
# stochastic; see the item spec's Decisions log).
_UNSPECIFIED_TARGET_FACTORIES = [
    lambda: DisplacePerturbation(),
    lambda: RelabelSwapPerturbation(),
]

_OPERATOR_IDS = ["displace", "relabel_swap", "sequence_break"]
_UNSPEC_OPERATOR_IDS = ["displace", "relabel_swap"]


def _designated_rule_fires_reconstructed(operator_name, labelmap, expectation):
    """Self-consistency check for displace/relabel_swap: the designated rule
    fires (via the reconstructed record) for exactly the label(s) recorded in
    *expectation*."""
    cfg = bundled_default_config()
    record = extract_feature_record(labelmap, cfg)
    if operator_name == "displace":
        (target,) = expectation.expected_labels
        loo = _loo_offset(labelmap, target)
        target_is_terminal = False
        for entry in record["stage3"]["per_label_offsets"]:
            if entry["label"] == target:
                entry["offset_mm"] = loo
                target_is_terminal = bool(entry.get("is_terminal"))
        findings = MislabelRule().evaluate(record, cfg)
        fires = any(
            f.rule_id == "mislabel"
            and f.reason.startswith("Vertebra misaligned from spinal curve:")
            and f.labels == frozenset({target})
            for f in findings
        )
        if target_is_terminal:
            # AC39 (docs/aide/items/123-recalibrate-and-regenerate-
            # downstream-artifacts.md): mislabel never fires an offset
            # finding on a terminal vertebra, regardless of magnitude -- the
            # designated rule NOT firing here is the exclusion working as
            # designed, not a self-consistency failure (AC55).
            return not fires
        return fires
    if operator_name == "relabel_swap":
        pairs = _reconstruct_mono_pairs(labelmap)
        record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"] = [
            list(p) for p in pairs
        ]
        record["stage3"]["monotonic_consistency"]["is_monotonic"] = False
        findings = MislabelRule().evaluate(record, cfg)
        return any(
            f.rule_id == "mislabel"
            and f.reason.startswith("Vertebra ordering inconsistent with label:")
            and f.labels == expectation.expected_labels
            for f in findings
        )
    raise AssertionError(f"unknown operator {operator_name!r}")


def _designated_rule_fires_run_qc(labelmap, expectation):
    """Self-consistency check for sequence_break: the "sequence" rule fires
    via plain run_qc for exactly the label(s) recorded in *expectation*."""
    findings = _findings(labelmap)
    (target,) = expectation.expected_labels
    return any(
        f.rule_id == "sequence"
        and f.reason.startswith("Non-continuous label sequence:")
        and f.labels == frozenset({target})
        for f in findings
    )


# =========================================================================== #
# A. displace (AC1-AC6)
# =========================================================================== #


def test_ac1_displace_registered_under_displace_name():
    """AC1: get_perturbation("displace") is DisplacePerturbation;
    "displace" is in perturbation_names() and iter_perturbations()."""
    assert get_perturbation("displace") is DisplacePerturbation
    assert "displace" in perturbation_names()
    assert DisplacePerturbation in list(iter_perturbations())


def test_ac2_displace_moves_target_off_neighbour_curve_by_threshold():
    """AC2: the leave-one-out offset of label 22 is >= 15.0 mm (the default
    max_offset_mm)."""
    clean = _clean()
    result = DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0)
    assert _loo_offset(result.labelmap, 22) >= 15.0


def test_ac3_displace_translates_body_wholesale_no_spurious_flags():
    """AC3: single component, preserved voxel count, and no
    bounds/fragmentation/border finding."""
    clean = _clean()
    cfg = bundled_default_config()
    result = DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0)

    comps = compute_components(result.labelmap, 22, cfg)
    assert comps.component_count == 1

    data = np.asanyarray(result.labelmap.dataobj)
    assert int(np.count_nonzero(data == 22)) == clean.voxel_counts[22]

    findings = _findings(result.labelmap)
    assert not any(
        f.rule_id in {"bounds", "fragmentation", "border"} for f in findings
    )


def test_ac4_displace_fires_misalignment_finding_via_run_qc():
    """AC4: the item-120 held-out per-label spline offset makes the
    displaced label's own offset_mm large through plain extract_feature_record
    (no reconstruction needed), and feeding that record to MislabelRule fires
    a "mislabel" finding tagged "Vertebra misaligned from spinal curve:" on
    {22}."""
    clean = _clean()
    cfg = bundled_default_config()
    result = DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0)

    record = extract_feature_record(result.labelmap, cfg)

    findings = MislabelRule().evaluate(record, cfg)
    matches = [
        f
        for f in findings
        if f.rule_id == "mislabel"
        and f.reason.startswith("Vertebra misaligned from spinal curve:")
        and f.labels == frozenset({22})
    ]
    assert matches


def test_ac5_displace_run_qc_surfaces_mislabel_finding():
    """AC5: plain run_qc on the displaced map emits a "mislabel" finding on
    the displaced label -- the pipeline's held-out per-label spline offset
    (item 120) measures the target against a curve it did not shape, so the
    displacement is no longer absorbed."""
    clean = _clean()
    result = DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    mislabel = [f for f in findings if f.rule_id == "mislabel"]
    assert mislabel
    union = set()
    for f in mislabel:
        union |= set(f.labels)
    assert union == {22}


def test_ac6_displace_expectation_well_formed():
    """AC6: Expectation fields are pinned."""
    clean = _clean()
    result = DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 1
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[1]
    assert exp.expected_rule_ids == frozenset({"mislabel"})
    assert exp.expected_labels == frozenset({22})
    assert exp.expected_verdict == "flagged-for-review"


# =========================================================================== #
# B. relabel_swap (AC7-AC13)
# =========================================================================== #


def test_ac7_relabel_swap_registered_under_relabel_swap_name():
    """AC7: get_perturbation("relabel_swap") is RelabelSwapPerturbation;
    "relabel_swap" is in perturbation_names()."""
    assert get_perturbation("relabel_swap") is RelabelSwapPerturbation
    assert "relabel_swap" in perturbation_names()


def test_ac8_relabel_swap_exchanges_two_adjacent_bodies_preserving_label_set():
    """AC8: the present-label set is unchanged; label 21's centroid position
    (array axis 0, a fixed voxel coordinate independent of anatomical
    meaning) equals the clean GT's label-22 centroid position and vice
    versa; each label's voxel count is preserved."""
    clean = _clean()
    result = RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(
        clean.seg_img, seed=0
    )
    assert set(_present_labels(result.labelmap)) == {20, 21, 22, 23, 24}

    clean_c21 = compute_centroid(clean.seg_img, 21)
    clean_c22 = compute_centroid(clean.seg_img, 22)
    swapped_c21 = compute_centroid(result.labelmap, 21)
    swapped_c22 = compute_centroid(result.labelmap, 22)
    assert swapped_c21.centroid_voxel[0] == pytest.approx(
        clean_c22.centroid_voxel[0]
    )
    assert swapped_c22.centroid_voxel[0] == pytest.approx(
        clean_c21.centroid_voxel[0]
    )

    data = np.asanyarray(result.labelmap.dataobj)
    for label in (20, 21, 22, 23, 24):
        assert int(np.count_nonzero(data == label)) == clean.voxel_counts[label]


def test_ac9_relabel_swap_makes_centroid_order_non_monotonic_on_spatial_curve():
    """AC9: the reconstructed non_monotonic_pairs is non-empty and includes
    the ("L2", "L3") pair (labels 21 and 22)."""
    clean = _clean()
    result = RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(
        clean.seg_img, seed=0
    )
    pairs = [tuple(p) for p in _reconstruct_mono_pairs(result.labelmap)]
    assert pairs
    assert ("L2", "L3") in pairs


def test_ac10_relabel_swap_fires_ordering_finding_via_reconstructed_record():
    """AC10: replacing monotonic_consistency.non_monotonic_pairs with the
    reconstructed pairs (and is_monotonic=False), then feeding the record to
    MislabelRule fires a "mislabel" finding tagged "Vertebra ordering
    inconsistent with label:" on {21, 22}."""
    clean = _clean()
    cfg = bundled_default_config()
    result = RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(
        clean.seg_img, seed=0
    )

    record = extract_feature_record(result.labelmap, cfg)
    pairs = _reconstruct_mono_pairs(result.labelmap)
    record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"] = [
        list(p) for p in pairs
    ]
    record["stage3"]["monotonic_consistency"]["is_monotonic"] = False

    findings = MislabelRule().evaluate(record, cfg)
    matches = [
        f
        for f in findings
        if f.rule_id == "mislabel"
        and f.reason.startswith("Vertebra ordering inconsistent with label:")
        and f.labels == frozenset({21, 22})
    ]
    assert matches


def test_ac11_relabel_swap_run_qc_does_not_surface_swap():
    """Pin FLIPPED 2026-08-31 (item 132): plain run_qc on the swapped map
    now fires MislabelRule's ordering finding (Detector B) on {21, 22} with
    verdict "flagged-for-review" -- the traversal-ordered reference fit
    surfaces the swap that used to be a documented limitation."""
    clean = _clean()
    result = RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(
        clean.seg_img, seed=0
    )
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    matches = [
        f
        for f in case_result.findings
        if f.rule_id == "mislabel" and f.labels == frozenset({21, 22})
    ]
    assert matches
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac12_relabel_swap_expectation_well_formed():
    """AC12: Expectation fields are pinned."""
    clean = _clean()
    result = RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(
        clean.seg_img, seed=0
    )
    exp = result.expectation
    assert exp.failure_mode == 4
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[4]
    assert exp.expected_rule_ids == frozenset({"mislabel"})
    assert exp.expected_labels == frozenset({21, 22})
    assert exp.expected_verdict == "flagged-for-review"


def test_ac13_relabel_swap_rejects_too_small_or_non_adjacent_input():
    """AC13: a single-label map raises FacetInputError; an explicit
    non-adjacent pair (20, 23) raises FacetInputError."""
    single = build_clean_spine(levels=["L3"]).seg_img
    with pytest.raises(FacetInputError):
        RelabelSwapPerturbation().apply(single, seed=0)

    clean = _clean()
    with pytest.raises(FacetInputError):
        RelabelSwapPerturbation(target_label=20, neighbour_label=23).apply(
            clean.seg_img, seed=0
        )


# =========================================================================== #
# C. sequence_break (AC14-AC19)
# =========================================================================== #


def test_ac14_sequence_break_registered_under_sequence_break_name():
    """AC14: get_perturbation("sequence_break") is SequenceBreakPerturbation;
    "sequence_break" is in perturbation_names()."""
    assert get_perturbation("sequence_break") is SequenceBreakPerturbation
    assert "sequence_break" in perturbation_names()


def test_ac15_sequence_break_relabels_tail_vertebra_to_transitional_label():
    """AC15: label 24 (L5) is absent, label 28 (T13) is present with the
    clean GT's label-24 voxel count, and every other clean label is
    unchanged."""
    clean = _clean()
    result = SequenceBreakPerturbation().apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)
    present = set(_present_labels(result.labelmap))
    assert 24 not in present
    assert 28 in present
    assert int(np.count_nonzero(data == 28)) == clean.voxel_counts[24]
    for label in (20, 21, 22, 23):
        assert int(np.count_nonzero(data == label)) == clean.voxel_counts[label]


def test_ac16_sequence_break_fires_continuity_finding_via_run_qc():
    """AC16: run_qc emits a "sequence" finding tagged "Non-continuous label
    sequence:" naming "T13", labels == {28}."""
    clean = _clean()
    result = SequenceBreakPerturbation().apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "sequence"
        and f.reason.startswith("Non-continuous label sequence:")
        and "T13" in f.reason
        and f.labels == frozenset({28})
    ]
    assert matches


def test_ac17_sequence_break_only_fired_rule_is_sequence_no_coverage():
    """AC17: every finding has rule_id == "sequence" -- in particular no
    "coverage" finding (the surviving span stays canonically contiguous)."""
    clean = _clean()
    result = SequenceBreakPerturbation().apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert findings
    for f in findings:
        assert f.rule_id == "sequence"
    assert not any(f.rule_id == "coverage" for f in findings)


def test_ac18_sequence_break_expectation_well_formed_and_pipeline_agrees():
    """AC18: Expectation fields are pinned and verdict.overall.label matches."""
    clean = _clean()
    result = SequenceBreakPerturbation().apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 7
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[7]
    assert exp.expected_rule_ids == frozenset({"sequence"})
    assert exp.expected_labels == frozenset({28})
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac19_sequence_break_rejects_degenerate_input():
    """AC19: a single-label map (no ordering to break) raises
    FacetInputError; an explicit new_label already present raises
    FacetInputError."""
    single = build_clean_spine(levels=["L3"]).seg_img
    with pytest.raises(FacetInputError):
        SequenceBreakPerturbation().apply(single, seed=0)

    clean = _clean()
    with pytest.raises(FacetInputError):
        SequenceBreakPerturbation(target_label=24, new_label=22).apply(
            clean.seg_img, seed=0
        )


# =========================================================================== #
# D. Cross-cutting: geometry, determinism, immutability, seeding, spacing
# (AC20-AC24)
# =========================================================================== #


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac20_preserves_dtype_and_geometry(make_operator):
    """AC20: output dtype, affine, shape, and spacing all match the input."""
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
def test_ac21_reproducible_same_seed_and_input_yields_identical_array(make_operator):
    """AC21: two apply(seed=7) calls with the same explicit target/pair
    return np.array_equal outputs."""
    clean = _clean()
    r1 = make_operator().apply(clean.seg_img, seed=7)
    r2 = make_operator().apply(clean.seg_img, seed=7)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac22_apply_does_not_mutate_callers_input_array(make_operator):
    """AC22: the seg_img's data array is unchanged after apply() returns."""
    clean = _clean()
    data_before = np.array(np.asanyarray(clean.seg_img.dataobj), copy=True)
    make_operator().apply(clean.seg_img, seed=0)
    data_after = np.asanyarray(clean.seg_img.dataobj)
    assert np.array_equal(data_before, data_after)


@pytest.mark.parametrize(
    "make_operator, name",
    zip(_UNSPECIFIED_TARGET_FACTORIES, _UNSPEC_OPERATOR_IDS),
    ids=_UNSPEC_OPERATOR_IDS,
)
def test_ac23_unspecified_target_is_seed_deterministic_and_self_consistent(
    make_operator, name
):
    """AC23: two apply(seed=3) calls with no explicit target select the same
    target (identical output arrays), and the designated rule fires (via the
    reconstructed record) for exactly the label(s) recorded in
    result.expectation."""
    clean = _clean()
    r1 = make_operator().apply(clean.seg_img, seed=3)
    r2 = make_operator().apply(clean.seg_img, seed=3)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)

    assert _designated_rule_fires_reconstructed(name, r1.labelmap, r1.expectation)


@pytest.mark.parametrize(
    "make_operator, name", zip(_EXPLICIT_TARGET_FACTORIES, _OPERATOR_IDS), ids=_OPERATOR_IDS
)
def test_ac24_spacing_aware_under_anisotropic_spacing(make_operator, name):
    """AC24: each operator, applied to an anisotropic clean GT, still drives
    its designated rule and preserves the input spacing."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    result = make_operator().apply(clean.seg_img, seed=0)
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
        == (1.0, 1.0, 3.0)
    )
    if name == "displace":
        assert _loo_offset(result.labelmap, 22) >= 15.0
    elif name == "relabel_swap":
        assert _reconstruct_mono_pairs(result.labelmap)
    else:
        assert _designated_rule_fires_run_qc(result.labelmap, result.expectation)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_displace_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    FacetInputError rather than silently no-op-ing."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        DisplacePerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_sequence_break_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    FacetInputError."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        SequenceBreakPerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_displace_too_large_displacement_raises_clear_error():
    """Adversarial: a displacement_mm too large to fit inside the FOV margins
    raises FacetInputError (does not silently clip the body)."""
    clean = _clean()
    with pytest.raises(FacetInputError):
        DisplacePerturbation(target_label=22, displacement_mm=10_000.0).apply(
            clean.seg_img, seed=0
        )


def test_adv_relabel_swap_different_adjacent_pair_fires_on_exactly_that_pair():
    """Adversarial: swapping a different adjacent pair (23<->24) still fires
    the ordering finding on exactly that pair via the reconstruction."""
    clean = _clean()
    cfg = bundled_default_config()
    result = RelabelSwapPerturbation(target_label=23, neighbour_label=24).apply(
        clean.seg_img, seed=0
    )
    record = extract_feature_record(result.labelmap, cfg)
    pairs = _reconstruct_mono_pairs(result.labelmap)
    record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"] = [
        list(p) for p in pairs
    ]
    record["stage3"]["monotonic_consistency"]["is_monotonic"] = False
    findings = MislabelRule().evaluate(record, cfg)
    matches = [
        f
        for f in findings
        if f.rule_id == "mislabel"
        and f.reason.startswith("Vertebra ordering inconsistent with label:")
        and f.labels == frozenset({23, 24})
    ]
    assert matches


@pytest.mark.parametrize(
    "make_operator, name",
    zip(_UNSPECIFIED_TARGET_FACTORIES, _UNSPEC_OPERATOR_IDS),
    ids=_UNSPEC_OPERATOR_IDS,
)
def test_adv_different_seeds_unspecified_target_stay_self_consistent(
    make_operator, name
):
    """Adversarial: two different seeds with an unspecified target may pick
    different offenders, but each result stays self-consistent -- the
    designated rule fires for that result's own recorded expectation."""
    clean = _clean()
    for seed in (1, 42):
        result = make_operator().apply(clean.seg_img, seed=seed)
        assert _designated_rule_fires_reconstructed(
            name, result.labelmap, result.expectation
        )


def test_adv_sequence_break_interior_target_still_fires_sequence_with_coverage_cofire():
    """Adversarial: an explicit interior target (label 22) still fires
    "sequence" but is expected to co-fire a case-level "coverage" finding
    (documented divergence from the clean default's no-cofire case)."""
    clean = _clean()
    result = SequenceBreakPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert any(f.rule_id == "sequence" for f in findings)
    assert any(f.rule_id == "coverage" for f in findings)
