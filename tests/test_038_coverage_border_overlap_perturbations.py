"""Tests for item 038 — coverage, border & overlap perturbations:
remove_level, crop_at_border, force_overlap.

Covers Acceptance Criteria AC1-AC28:

- AC1-AC9 (Group A, ``remove_level``): registration; deletes exactly the
  target interior level; fires the missing-interior-level coverage finding
  naming L3; no spurious border flag; only-coverage/case-level findings;
  Expectation well-formed and pipeline agrees; unspecified target picks an
  interior level; rejects a span with no interior level; rejects an explicit
  terminal target.
- AC10-AC17 (Group B, ``crop_at_border``): registration; target contacts the
  chosen in-plane face; fires the border finding on the target; no spurious
  bounds flag; Expectation well-formed and pipeline agrees; other present
  labels stay unflagged; default in-plane face flags a terminal target too;
  rejects an unknown face string.
- AC18-AC23 (Group C, ``force_overlap``): registration; assigns shared
  voxels to the target; drives the overlap rule via a reconstructed
  mask-stack + OverlapRule; Expectation well-formed; run_qc shows NO overlap
  finding (documented one-hot limitation); rejects a too-small / non-adjacent
  input.
- AC24-AC28 (Group D, cross-cutting): dtype/affine/shape/zooms preservation;
  same-seed reproducibility; non-mutation of the caller's input; unspecified
  target selection is seed-deterministic and self-consistent; spacing-aware
  under anisotropic spacing.

Adversarial / edge-case scenarios included:
- ``remove_level`` / ``crop_at_border`` / ``force_overlap`` with an explicit
  target not present in the map raise SegQCInputError.
- ``crop_at_border`` against each of the four in-plane faces sets the
  matching ``touches_*`` flag and fires ``border``.
- ``crop_at_border`` retains a physical volume above the level group's
  minimum (no spurious ``bounds``).
- ``force_overlap`` under anisotropic spacing still yields ``k > 0`` shared
  voxels.
- Two different seeds with an unspecified target may pick different
  offenders, but each result stays self-consistent.
"""

from __future__ import annotations

import numpy as np
import pytest

import segqc.synth  # noqa: F401 -- triggers self-registration of the three operators
from segqc.config import bundled_default_config
from segqc.feature_report import overlap_to_dict
from segqc.features.geometry import compute_label_geometry
from segqc.features.overlap import detect_overlaps
from segqc.heuristics.bounds import DEFAULT_BOUNDS
from segqc.heuristics.overlap import OverlapRule
from segqc.io import SegQCInputError
from segqc.pipeline import run_qc
from segqc.synth import (
    FAILURE_MODE_NAMES,
    build_clean_spine,
    get_perturbation,
    iter_perturbations,
    perturbation_names,
)
from segqc.synth.coverage_border_overlap import (
    CropAtBorderPerturbation,
    ForceOverlapPerturbation,
    RemoveLevelPerturbation,
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


# Explicit-target operator factories shared by the cross-cutting AC24-AC26
# parametrizations.
_EXPLICIT_TARGET_FACTORIES = [
    lambda: RemoveLevelPerturbation(target_label=22),
    lambda: CropAtBorderPerturbation(target_label=22, face="anterior"),
    lambda: ForceOverlapPerturbation(target_label=20, neighbour_label=21),
]

# Unspecified-target operator factories shared by AC27 and the adversarial
# seed-varying test.
_UNSPECIFIED_TARGET_FACTORIES = [
    lambda: RemoveLevelPerturbation(),
    lambda: CropAtBorderPerturbation(),
    lambda: ForceOverlapPerturbation(),
]

_OPERATOR_IDS = ["remove_level", "crop_at_border", "force_overlap"]


def _designated_rule_fires(operator_name, labelmap, clean_data, expectation):
    """Return True iff *operator_name*'s designated rule fires for the
    entity actually recorded in *expectation* (self-consistency check used
    by AC27/AC28 and the different-seeds adversarial test)."""
    if operator_name == "remove_level":
        findings = _findings(labelmap)
        return any(
            f.rule_id == "coverage" and f.reason.startswith("Missing interior level(s):")
            for f in findings
        )
    if operator_name == "crop_at_border":
        findings = _findings(labelmap)
        (target,) = expectation.expected_labels
        return any(
            f.rule_id == "border" and target in f.labels for f in findings
        )
    if operator_name == "force_overlap":
        target, neighbour = sorted(expectation.expected_labels)
        data = np.asanyarray(labelmap.dataobj)
        stack = np.stack([data == target, clean_data == neighbour])
        pairs = detect_overlaps(stack, np.array([target, neighbour]))
        return len(pairs) > 0 and pairs[0].overlap_voxels > 0
    raise AssertionError(f"unknown operator {operator_name!r}")


# =========================================================================== #
# A. remove_level (AC1-AC9)
# =========================================================================== #


def test_ac1_remove_level_registered_under_remove_level_name():
    """AC1: get_perturbation("remove_level") is RemoveLevelPerturbation;
    "remove_level" is in perturbation_names() and iter_perturbations()."""
    assert get_perturbation("remove_level") is RemoveLevelPerturbation
    assert "remove_level" in perturbation_names()
    assert RemoveLevelPerturbation in list(iter_perturbations())


def test_ac2_remove_level_deletes_exactly_the_target_interior_level():
    """AC2: label 22 is absent, every other clean label (20,21,23,24) keeps
    its original clean voxel count."""
    clean = _clean()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)
    present = {int(v) for v in np.unique(data) if v != 0}
    assert 22 not in present
    for label in (20, 21, 23, 24):
        assert label in present
        assert int(np.count_nonzero(data == label)) == clean.voxel_counts[label]


def test_ac3_remove_level_fires_missing_interior_level_finding_naming_l3():
    """AC3: a "coverage" finding tagged "Missing interior level(s):" naming
    "L3", case-level (labels == frozenset())."""
    clean = _clean()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "coverage"
        and f.reason.startswith("Missing interior level(s):")
        and "L3" in f.reason
        and f.labels == frozenset()
    ]
    assert matches


def test_ac4_remove_level_produces_no_spurious_border_flag():
    """AC4: no "border" finding fires."""
    clean = _clean()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "border" for f in findings)


def test_ac5_remove_level_only_fired_rule_is_coverage_and_case_level():
    """AC5: every finding has rule_id == "coverage" and every finding.labels
    is empty (case-level)."""
    clean = _clean()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert findings
    for f in findings:
        assert f.rule_id == "coverage"
        assert f.labels == frozenset()


def test_ac6_remove_level_expectation_well_formed_and_pipeline_agrees():
    """AC6: Expectation fields are pinned and verdict.overall.label matches."""
    clean = _clean()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 5
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[5]
    assert exp.expected_rule_ids == frozenset({"coverage"})
    assert exp.expected_labels == frozenset()
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac7_remove_level_unspecified_target_removes_interior_level():
    """AC7: an unspecified target removes a non-terminal level (not in
    {20, 24}), expected_labels stays empty, and a coverage finding fires."""
    clean = _clean()
    result = RemoveLevelPerturbation().apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)
    present = {int(v) for v in np.unique(data) if v != 0}
    removed = set(clean.labels) - present
    assert len(removed) == 1
    (removed_label,) = removed
    assert removed_label not in (20, 24)
    assert result.expectation.expected_labels == frozenset()
    case_result, block = run_qc(result.labelmap, bundled_default_config())
    relationships = block.get("relationships")
    assert relationships is not None
    assert len(relationships.get("missing_levels") or []) > 0
    assert any(f.rule_id == "coverage" for f in case_result.findings)


def test_ac8_remove_level_rejects_span_with_no_interior_level():
    """AC8: applying RemoveLevelPerturbation() to a two-label map (no
    interior level) raises SegQCInputError."""
    two_label = build_clean_spine(levels=["L1", "L2"]).seg_img
    with pytest.raises(SegQCInputError):
        RemoveLevelPerturbation().apply(two_label, seed=0)


def test_ac9_remove_level_rejects_explicit_terminal_target():
    """AC9: an explicit terminal target (label 20, superior span end) raises
    SegQCInputError."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        RemoveLevelPerturbation(target_label=20).apply(clean.seg_img, seed=0)


# =========================================================================== #
# B. crop_at_border (AC10-AC17)
# =========================================================================== #


def test_ac10_crop_at_border_registered_under_crop_at_border_name():
    """AC10: get_perturbation("crop_at_border") is CropAtBorderPerturbation;
    "crop_at_border" is in perturbation_names()."""
    assert get_perturbation("crop_at_border") is CropAtBorderPerturbation
    assert "crop_at_border" in perturbation_names()


def test_ac11_crop_at_border_makes_target_contact_chosen_face():
    """AC11: touches_anterior becomes True after crop, was False on the
    clean GT's label 22."""
    clean = _clean()
    geo_before = compute_label_geometry(clean.seg_img, 22)
    assert geo_before.touches_anterior is False
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    geo_after = compute_label_geometry(result.labelmap, 22)
    assert geo_after.touches_anterior is True


def test_ac12_crop_at_border_fires_border_finding_on_target():
    """AC12: a "border" finding tagged "Partial vertebra clipped by FOV:" on
    labels == frozenset({22})."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    findings = _findings(result.labelmap)
    matches = [
        f
        for f in findings
        if f.rule_id == "border"
        and f.reason.startswith("Partial vertebra clipped by FOV:")
        and f.labels == frozenset({22})
    ]
    assert matches


def test_ac13_crop_at_border_produces_no_spurious_bounds_flag():
    """AC13: no "bounds" finding fires."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "bounds" for f in findings)


def test_ac14_crop_at_border_expectation_well_formed_and_pipeline_agrees():
    """AC14: Expectation fields are pinned and verdict.overall.label matches."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    exp = result.expectation
    assert exp.failure_mode == 6
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[6]
    assert exp.expected_rule_ids == frozenset({"border"})
    assert exp.expected_labels == frozenset({22})
    assert exp.expected_verdict == "flagged-for-review"
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == "flagged-for-review"


def test_ac15_crop_at_border_leaves_other_present_labels_unflagged():
    """AC15: every non-empty finding.labels is a subset of {22}."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    findings = _findings(result.labelmap)
    for f in findings:
        if f.labels:
            assert f.labels <= frozenset({22})


def test_ac16_crop_at_border_default_face_flags_terminal_target():
    """AC16: default face on a terminal target (label 20) still fires a
    "border" finding on {20} -- in-plane clip is always unexpected."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=20).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert any(
        f.rule_id == "border" and f.labels == frozenset({20}) for f in findings
    )


def test_ac17_crop_at_border_rejects_unknown_face_string():
    """AC17: an unknown face string raises SegQCInputError."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        CropAtBorderPerturbation(target_label=22, face="diagonal").apply(
            clean.seg_img, seed=0
        )


# =========================================================================== #
# C. force_overlap (AC18-AC23)
# =========================================================================== #


def test_ac18_force_overlap_registered_under_force_overlap_name():
    """AC18: get_perturbation("force_overlap") is ForceOverlapPerturbation;
    "force_overlap" is in perturbation_names()."""
    assert get_perturbation("force_overlap") is ForceOverlapPerturbation
    assert "force_overlap" in perturbation_names()


def test_ac19_force_overlap_assigns_shared_voxels_to_target():
    """AC19: intersection of perturbed target mask and clean neighbour mask
    is k > 0; neighbour's perturbed count equals clean count minus k."""
    clean = _clean()
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    result = ForceOverlapPerturbation(
        target_label=20, neighbour_label=21, overlap_depth=3
    ).apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)
    k = int(np.count_nonzero((data == 20) & (clean_data == 21)))
    assert k > 0
    neighbour_after = int(np.count_nonzero(data == 21))
    assert neighbour_after == clean.voxel_counts[21] - k


def test_ac20_force_overlap_drives_overlap_rule_with_offending_pair():
    """AC20: detect_overlaps over a reconstructed two-channel mask stack
    [(perturbed==20), (clean==21)] -> OverlapRule fires a "overlap" finding
    tagged "Overlapping segments:" on {20, 21}."""
    clean = _clean()
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    result = ForceOverlapPerturbation(
        target_label=20, neighbour_label=21, overlap_depth=3
    ).apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)

    stack = np.stack([data == 20, clean_data == 21])
    pairs = detect_overlaps(stack, np.array([20, 21]))
    record = {"overlaps": [overlap_to_dict(p) for p in pairs]}
    findings = OverlapRule().evaluate(record, bundled_default_config())

    matches = [
        f
        for f in findings
        if f.rule_id == "overlap"
        and f.reason.startswith("Overlapping segments:")
        and f.labels == frozenset({20, 21})
    ]
    assert matches


def test_ac21_force_overlap_expectation_well_formed():
    """AC21: Expectation fields are pinned."""
    clean = _clean()
    result = ForceOverlapPerturbation(
        target_label=20, neighbour_label=21, overlap_depth=3
    ).apply(clean.seg_img, seed=0)
    exp = result.expectation
    assert exp.failure_mode == 8
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[8]
    assert exp.expected_rule_ids == frozenset({"overlap"})
    assert exp.expected_labels == frozenset({20, 21})
    assert exp.expected_verdict == "flagged-for-review"


def test_ac22_force_overlap_run_qc_shows_no_overlap_finding():
    """AC22: run_qc on the perturbed labelmap emits NO "overlap" finding --
    a single-integer label map cannot carry a voxel shared by two labels, so
    the overlap is structurally invisible to the plain run_qc path
    (documented limitation, not a bug)."""
    clean = _clean()
    result = ForceOverlapPerturbation(
        target_label=20, neighbour_label=21, overlap_depth=3
    ).apply(clean.seg_img, seed=0)
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "overlap" for f in findings)


def test_ac23_force_overlap_rejects_too_small_or_non_adjacent_input():
    """AC23: a single-label map raises SegQCInputError; a non-adjacent
    explicit pair (20, 23) raises SegQCInputError."""
    single = build_clean_spine(levels=["L3"]).seg_img
    with pytest.raises(SegQCInputError):
        ForceOverlapPerturbation().apply(single, seed=0)

    clean = _clean()
    with pytest.raises(SegQCInputError):
        ForceOverlapPerturbation(target_label=20, neighbour_label=23).apply(
            clean.seg_img, seed=0
        )


# =========================================================================== #
# D. Cross-cutting: geometry, determinism, immutability, seeding, spacing
# (AC24-AC28)
# =========================================================================== #


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac24_preserves_dtype_and_geometry(make_operator):
    """AC24: output dtype, affine, shape, and spacing all match the input."""
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
def test_ac25_reproducible_same_seed_and_input_yields_identical_array(make_operator):
    """AC25: two apply(seed=7) calls with the same explicit target return
    np.array_equal outputs."""
    clean = _clean()
    r1 = make_operator().apply(clean.seg_img, seed=7)
    r2 = make_operator().apply(clean.seg_img, seed=7)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)


@pytest.mark.parametrize("make_operator", _EXPLICIT_TARGET_FACTORIES, ids=_OPERATOR_IDS)
def test_ac26_apply_does_not_mutate_callers_input_array(make_operator):
    """AC26: the seg_img's data array is unchanged after apply() returns."""
    clean = _clean()
    data_before = np.array(np.asanyarray(clean.seg_img.dataobj), copy=True)
    make_operator().apply(clean.seg_img, seed=0)
    data_after = np.asanyarray(clean.seg_img.dataobj)
    assert np.array_equal(data_before, data_after)


@pytest.mark.parametrize(
    "make_operator, name", zip(_UNSPECIFIED_TARGET_FACTORIES, _OPERATOR_IDS), ids=_OPERATOR_IDS
)
def test_ac27_unspecified_target_is_seed_deterministic_and_self_consistent(
    make_operator, name
):
    """AC27: two apply(seed=3) calls with no explicit target select the same
    target (identical output arrays), and the designated rule fires for the
    label(s)/level actually recorded in result.expectation."""
    clean = _clean()
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    r1 = make_operator().apply(clean.seg_img, seed=3)
    r2 = make_operator().apply(clean.seg_img, seed=3)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)

    assert _designated_rule_fires(name, r1.labelmap, clean_data, r1.expectation)


@pytest.mark.parametrize(
    "make_operator, name", zip(_EXPLICIT_TARGET_FACTORIES, _OPERATOR_IDS), ids=_OPERATOR_IDS
)
def test_ac28_spacing_aware_under_anisotropic_spacing(make_operator, name):
    """AC28: each operator, applied to an anisotropic clean GT, still drives
    its designated rule and preserves the input spacing."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    result = make_operator().apply(clean.seg_img, seed=0)
    assert (
        result.labelmap.header.get_zooms()[:3]
        == clean.seg_img.header.get_zooms()[:3]
        == (1.0, 1.0, 3.0)
    )
    assert _designated_rule_fires(name, result.labelmap, clean_data, result.expectation)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_remove_level_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    SegQCInputError rather than silently no-op-ing."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        RemoveLevelPerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_crop_at_border_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    SegQCInputError."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        CropAtBorderPerturbation(target_label=999).apply(clean.seg_img, seed=0)


def test_adv_force_overlap_explicit_target_absent_raises_clear_error():
    """Adversarial: an explicit target_label not present in the map raises
    SegQCInputError."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        ForceOverlapPerturbation(target_label=999, neighbour_label=21).apply(
            clean.seg_img, seed=0
        )


def test_adv_force_overlap_explicit_neighbour_absent_raises_clear_error():
    """Adversarial: an explicit neighbour_label not present in the map
    raises SegQCInputError."""
    clean = _clean()
    with pytest.raises(SegQCInputError):
        ForceOverlapPerturbation(target_label=20, neighbour_label=999).apply(
            clean.seg_img, seed=0
        )


@pytest.mark.parametrize("face", ["left", "right", "anterior", "posterior"])
def test_adv_crop_at_border_each_in_plane_face_sets_touches_flag_and_fires(face):
    """Adversarial: crop_at_border against each of the four in-plane faces
    sets the matching touches_* flag and fires a "border" finding."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face=face).apply(
        clean.seg_img, seed=0
    )
    geo = compute_label_geometry(result.labelmap, 22)
    assert getattr(geo, f"touches_{face}") is True
    findings = _findings(result.labelmap)
    assert any(
        f.rule_id == "border" and f.labels == frozenset({22}) for f in findings
    )


def test_adv_crop_at_border_retains_volume_above_group_minimum():
    """Adversarial: the retained body's physical_volume_mm3 stays >= the
    lumbar level group's min_volume_mm3 (no spurious "bounds" finding)."""
    clean = _clean()
    result = CropAtBorderPerturbation(target_label=22, face="anterior").apply(
        clean.seg_img, seed=0
    )
    geo = compute_label_geometry(result.labelmap, 22)
    bounds = DEFAULT_BOUNDS["lumbar"]
    assert geo.physical_volume_mm3 >= bounds["min_volume_mm3"]
    findings = _findings(result.labelmap)
    assert not any(f.rule_id == "bounds" for f in findings)


def test_adv_force_overlap_anisotropic_spacing_still_yields_shared_voxels():
    """Adversarial: force_overlap under anisotropic spacing still produces
    k > 0 shared voxels (the reassigned slab is a voxel count, independent
    of spacing)."""
    clean = build_clean_spine(spacing=(1.0, 1.0, 3.0))
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    result = ForceOverlapPerturbation(
        target_label=20, neighbour_label=21, overlap_depth=3
    ).apply(clean.seg_img, seed=0)
    data = np.asanyarray(result.labelmap.dataobj)
    k = int(np.count_nonzero((data == 20) & (clean_data == 21)))
    assert k > 0


@pytest.mark.parametrize(
    "make_operator, name", zip(_UNSPECIFIED_TARGET_FACTORIES, _OPERATOR_IDS), ids=_OPERATOR_IDS
)
def test_adv_different_seeds_unspecified_target_stay_self_consistent(make_operator, name):
    """Adversarial: two different seeds with an unspecified target may pick
    different offenders, but each result stays self-consistent -- the
    designated rule fires for that result's own recorded expectation."""
    clean = _clean()
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    for seed in (1, 42):
        result = make_operator().apply(clean.seg_img, seed=seed)
        assert _designated_rule_fires(name, result.labelmap, clean_data, result.expectation)
