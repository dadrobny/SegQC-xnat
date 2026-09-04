"""Tests for item 143 -- correcting the synthetic corpus's S-axis stacking.

``build_clean_spine`` used to place ascending labels at ascending array-axis-2
slots, which -- because axis 2 is the affine-resolved superior-inferior axis
(item 116) and ascending label is head-to-tail (item 093) -- made every
in-repo synthetic fixture advance *superiorly* while real VerSe input read
through :mod:`segfacet.io` advances *caudally* (item 131). This item
reassigns the label<->slot mapping (label ``i`` moves to slot ``n - 1 - i``)
so the corpus matches real input's direction, without reshaping the physical
spine (the body layout is symmetric about the S midpoint).

Covers AC1-AC21. AC6-AC9 are a *value reconciliation* of existing tables in
``tests/test_131_tangent_direction_normalisation.py`` and
``tests/test_098_stray_components.py`` -- those tables are the builder's to
regenerate and reconcile (never this module's to edit); the tests below
either import those tables directly (AC7/AC8/AC9, whose values are expected
to survive unchanged) or assert the new caudal direction independently
(AC6), with a magnitude cross-check against a value transcribed from
test_131's pre-item table under AC3's mirror-symmetry guarantee.

Adversarial / edge cases: a single-level span (n == 1, degenerate slot
formula); a two-level span (the smallest observable reversal, folded into
AC2's parametrisation); anisotropic and degenerate ``(0.0, 1.0, 1.0)``
spacing through the same eval-harness path item 116's AC9 guarded; a
straight (``curve_amplitude_mm=0.0``) spine; a non-contiguous span still
raising ``FacetInputError``; determinism across two in-session calls; no
module-level mutation between calls; and a synthetic "advances superiorly"
spine that must fail AC1's caudal assertion (proving the assertion can
actually fail, not just pass vacuously).

AC10 and AC21's "absent from this item's diff" halves are deliberately not
unit tests here: a diff-against-a-branch claim belongs on the branch, not in
the suite (conventions §6) -- both are evidenced instead by the validator's
``aide scope 143 --base aide/queue-020`` run (spec Implementation Steps,
step 9) and by AC9's firing-set comparison / test_126_golden_retirement.py
already running in the suite, respectively.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import nibabel as nib
import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.eval.harness import EvaluationCase, evaluate_case
from segfacet.features.centroids import compute_centroid
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record
from segfacet.reference.artifact import build_and_write_default, default_artifact_path
from segfacet.synth import clean_gt as clean_gt_module
from segfacet.synth.axes import si_axis
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest, write_corpus
from segfacet.synth.golden import assert_matches_committed_artifact, build_report_for_case
from segfacet.synth.intensity import write_intensity_corpus
from segfacet.synth.regression import loaded_seg_image

import committed_artifact_guard as guard
from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS
from test_131_tangent_direction_normalisation import _PRE_ITEM_TANGENT_ANGLES_DEG

_REPO_ROOT = Path(__file__).resolve().parent.parent


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _ordered_centroid_s_mm(clean) -> List[float]:
    """Per-label centroid coordinate (mm) along the affine-resolved S/I axis,
    read straight off the raw label array in ascending-label order --
    independent of any feature extractor, rule, report, or committed
    fixture (AC1's own oracle requirement)."""
    data = np.asanyarray(clean.seg_img.dataobj)
    affine = clean.seg_img.affine
    axis = si_axis(affine)
    origin = float(affine[axis, 3])
    scale = float(affine[axis, axis])
    coords = []
    for label in clean.labels:
        idx = np.argwhere(data == label)
        assert idx.size, f"label {label!r} has no voxels"
        mean_index = float(idx[:, axis].mean())
        coords.append(origin + scale * mean_index)
    return coords


def _ordered_centroids_for_case(case: dict) -> List:
    """Ascending-label-order centroids for a corpus case, matching
    pipeline.py's own "ordered centroid sequence" construction. Copied (not
    imported) from test_131's own helper, per this repo's module-independence
    convention for item tests."""
    seg_img = loaded_seg_image(case)
    data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)
    assert labels, f"no foreground labels found in case {case.get('case_id')!r}"
    return [compute_centroid(seg_img, label) for label in labels]


# AC15 requires a byte-for-byte fresh-vs-committed comparison of
# ``docs/aide/traceability_matrix.generated.md``. Reconciled (item 149,
# 2026-09-04): this module's root idiom is now the normalised
# ``Path(__file__).resolve().parent.parent`` chain the guard's classifier
# resolves, and ``tests/committed_artifact_guard.GROUNDS`` gained its sixth
# member, ``"no-float-leaf"`` -- the traceability artifact has **zero float
# leaves** (measured 2026-09-03 over ``traceability_matrix.generated.json``),
# so there is no computed measurement for a NumPy/platform difference to
# move; it is pure rule/feature wiring structure, rendered deterministically
# and pinned ``text eol=lf``. ``ALLOWLIST`` now carries an entry for it under
# ``"no-float-leaf"``, so this comparison is both visible to the guard and
# covered, and ``test_ac14_this_module_produces_no_guard_violation`` below
# clears it rather than staying silent about it.


# =========================================================================== #
# AC1: ascending labels advance caudally in the built array
# =========================================================================== #


def test_ac1_ascending_labels_advance_caudally_default_build():
    clean = build_clean_spine()
    coords = _ordered_centroid_s_mm(clean)
    assert len(coords) >= 2
    for earlier, later in zip(coords, coords[1:]):
        assert earlier > later, f"ascending labels do not strictly decrease in S: {coords}"


def test_ac1_assertion_fails_for_a_synthetic_superiorly_advancing_array():
    """Adversarial: an array whose labels advance *superiorly* (the pre-item
    behaviour) must fail AC1's own caudal check -- proof the assertion is not
    vacuous."""
    clean = build_clean_spine(levels=("L1", "L2", "L3"))
    coords = list(reversed(_ordered_centroid_s_mm(clean)))
    with pytest.raises(AssertionError):
        for earlier, later in zip(coords, coords[1:]):
            assert earlier > later, "ascending labels do not strictly decrease in S"


# =========================================================================== #
# AC2: the caudal order holds for every span and spacing
# =========================================================================== #


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(dict(levels=("C3", "C4", "C5")), id="cervical_span"),
        pytest.param(dict(levels=("L1", "L2")), id="two_level_span"),
        pytest.param(
            dict(levels=("L1", "L2", "L3", "L4", "L5"), spacing=(0.8, 1.2, 3.0)),
            id="five_level_anisotropic_spacing",
        ),
        pytest.param(dict(curve_amplitude_mm=0.0), id="straight_spine_zero_amplitude"),
    ],
)
def test_ac2_caudal_order_holds_for_every_span_and_spacing(kwargs):
    clean = build_clean_spine(**kwargs)
    coords = _ordered_centroid_s_mm(clean)
    assert len(coords) >= 2
    for earlier, later in zip(coords, coords[1:]):
        assert earlier > later, f"{kwargs}: not strictly decreasing in S: {coords}"


# =========================================================================== #
# AC3: the correction reassigns labels and does not reshape the spine
# =========================================================================== #


def test_ac3_mirror_plus_relabel_reproduces_the_array_exactly():
    clean = build_clean_spine()
    data = np.asanyarray(clean.seg_img.dataobj)
    n = len(clean.labels)
    remap: Dict[int, int] = {clean.labels[i]: clean.labels[n - 1 - i] for i in range(n)}

    mirrored = data[:, :, ::-1]
    relabelled = np.zeros_like(mirrored)
    for old_label, new_label in remap.items():
        relabelled[mirrored == old_label] = new_label

    assert np.array_equal(relabelled, data), (
        "mirroring the array along S and reversing the label<->level "
        "assignment does not reproduce the original array -- the correction "
        "appears to have reshaped the spine, not just relabelled it"
    )


_EXPECTED_DEFAULT_SHAPE = (66, 55, 215)
_EXPECTED_DEFAULT_SPACING = (1.0, 1.0, 1.0)
_EXPECTED_DEFAULT_VOXEL_COUNTS = {20: 18750, 21: 18750, 22: 18750, 23: 18750, 24: 18750}


def test_ac3_shape_spacing_affine_and_voxel_counts_are_unaffected_by_the_correction():
    """shape/spacing/affine/voxel_counts are computed from n, spacing, and
    curve_amplitude_mm alone, entirely before the per-label loop this item's
    correction touches -- so for the default build they hold the same values
    the pre-item generator produced (spec AC3). These are generator
    parameters, not measurements: 2*margin_vox + n*body_vox + (n-1)*gap_vox
    along the stacking axis, per the module docstring's stated 25/30/25 mm
    body and 15 mm margin/gap, at 1.0 mm isotropic spacing --
    2*15 + 5*25 + 4*15 = 215 (S/I), 2*15 + 30 + 6 = 66 (L/R, +6 vox default
    curve amplitude), 2*15 + 25 = 55 (A/P); each body 30*25*25 = 18750 vox^3."""
    clean = build_clean_spine()
    assert clean.shape == _EXPECTED_DEFAULT_SHAPE
    assert clean.spacing == _EXPECTED_DEFAULT_SPACING
    assert clean.voxel_counts == _EXPECTED_DEFAULT_VOXEL_COUNTS
    affine = clean.seg_img.affine
    assert np.array_equal(affine, np.diag([1.0, 1.0, 1.0, 1.0]))


# =========================================================================== #
# AC4: item 116's contract survives intact
# =========================================================================== #


def test_ac4_stacking_axis_and_affine_si_axis_are_still_axis_2():
    """test_116_ras_native_corpus.py's own assertions run unmodified
    elsewhere in the suite (AC4's "no assertion weakened or removed" half);
    here the two structural properties it protects are re-asserted directly
    against the corrected generator, with an affine-free oracle for the
    stacking axis (mirrors test_116's own oracle, not imported from it)."""
    clean = build_clean_spine()
    data = np.asanyarray(clean.seg_img.dataobj)
    centroids = []
    for label in clean.labels:
        coords = np.argwhere(data == label)
        assert coords.size, f"label {label!r} has no voxels"
        centroids.append(coords.mean(axis=0))
    centroids_arr = np.asarray(centroids, dtype=float)
    stacking_axis = int(np.argmax(centroids_arr.var(axis=0)))
    assert stacking_axis == 2

    axcodes = nib.aff2axcodes(clean.seg_img.affine)
    si_axes = [axis for axis, code in enumerate(axcodes) if code in ("S", "I")]
    assert si_axes == [2]
    assert si_axis(clean.seg_img.affine) == 2


# =========================================================================== #
# AC5: the docstring states the corrected contract
# =========================================================================== #

_CANONICAL_KEY_PHRASE = "ascending labels advance caudally"
_FORBIDDEN_PHRASES = ("ascending axis-2", "ascending array-axis-2")


def test_ac5_docstrings_state_the_caudal_contract():
    module_doc = clean_gt_module.__doc__ or ""
    func_doc = build_clean_spine.__doc__ or ""
    assert _CANONICAL_KEY_PHRASE in module_doc, (
        f"clean_gt.py's module docstring does not carry the canonical phrase "
        f"{_CANONICAL_KEY_PHRASE!r}"
    )
    assert _CANONICAL_KEY_PHRASE in func_doc, (
        f"build_clean_spine.__doc__ does not carry the canonical phrase "
        f"{_CANONICAL_KEY_PHRASE!r}"
    )
    for forbidden in _FORBIDDEN_PHRASES:
        assert forbidden not in module_doc.lower(), (
            f"module docstring still implies ascending labels occupy ascending "
            f"axis-2 slots: {forbidden!r}"
        )
        assert forbidden not in func_doc.lower(), (
            f"build_clean_spine.__doc__ still implies ascending labels occupy "
            f"ascending axis-2 slots: {forbidden!r}"
        )


# =========================================================================== #
# AC6: every corpus case advances caudally
# =========================================================================== #

#: Transcribed verbatim from test_131_tangent_direction_normalisation.py's
#: pre-item ``_PRE_ITEM_NET_ADVANCE_S_MM`` table (measured 2026-08-31, item
#: 131). Used here only for its *magnitude*, under AC3's mirror-symmetry
#: guarantee that the correction cannot change |net advance|, only its sign
#: -- the authoritative post-fix table lives in test_131 and is the
#: builder's to reconcile, not retyped here.
_PRE_ITEM_NET_ADVANCE_S_MM_MAGNITUDE = {
    "clean_control": 160.0,
    "mode1_displace": 160.0,
    "mode2_fragment": 160.0,
    "mode3_inject_islands": 160.0,
    "mode4_relabel_swap": 160.0,
    "mode5_remove_level": 160.0,
    "mode6_crop_at_border": 160.0,
    "mode7_sequence_break": 160.0,
    "mode8_force_overlap": 142.0,
}


def test_ac6_every_corpus_case_net_advance_is_negative():
    manifest = load_manifest()
    assert set(_PRE_ITEM_NET_ADVANCE_S_MM_MAGNITUDE) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        centroids = _ordered_centroids_for_case(case)
        net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
        assert net < 0.0, (
            f"{case['case_id']}: net +S advance {net} is not negative -- ascending "
            f"labels are still advancing superiorly, not caudally"
        )
        expected_magnitude = _PRE_ITEM_NET_ADVANCE_S_MM_MAGNITUDE[case["case_id"]]
        assert abs(net) == pytest.approx(expected_magnitude, abs=1e-6), (
            f"{case['case_id']}: |net advance| {abs(net)} != pre-item magnitude "
            f"{expected_magnitude} -- AC3's mirror symmetry says the correction "
            f"must not change the magnitude, only the sign"
        )


def test_ac6_single_case_caudal_assertion_would_fail_pre_correction():
    """Adversarial: a synthetic spine whose labels advance superiorly (the
    exact pre-item shape) must fail AC6's own caudal assertion."""
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "clean_control")
    centroids = list(reversed(_ordered_centroids_for_case(case)))
    net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
    with pytest.raises(AssertionError):
        assert net < 0.0, "net +S advance is not negative"


# =========================================================================== #
# AC7/AC8: tangent_angles_deg holds for eight cases; mode4 moves only by
# item 131's measured fit asymmetry
# =========================================================================== #

_MODE4_CASE_ID = "mode4_relabel_swap"


def test_ac7_tangent_angles_deg_unmoved_on_the_eight_non_doubling_back_cases():
    manifest = load_manifest()
    assert set(_PRE_ITEM_TANGENT_ANGLES_DEG) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        if case["case_id"] == _MODE4_CASE_ID:
            continue
        seg_img = loaded_seg_image(case)
        record = extract_feature_record(seg_img, bundled_default_config())
        actual = list(record["stage3"]["curvature"]["tangent_angles_deg"])
        expected = _PRE_ITEM_TANGENT_ANGLES_DEG[case["case_id"]]
        assert actual == pytest.approx(expected, abs=1e-3), (
            f"{case['case_id']}: tangent_angles_deg moved under the corrected "
            f"corpus -- {actual} != {expected}"
        )


def test_ac8_mode4_relabel_swap_tangent_angles_within_loosened_fit_asymmetry_tolerance():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == _MODE4_CASE_ID)
    seg_img = loaded_seg_image(case)
    record = extract_feature_record(seg_img, bundled_default_config())
    actual = list(record["stage3"]["curvature"]["tangent_angles_deg"])
    expected = _PRE_ITEM_TANGENT_ANGLES_DEG[_MODE4_CASE_ID]
    assert actual == pytest.approx(expected, abs=1e-2), (
        f"mode4_relabel_swap: tangent_angles_deg {actual} moved by more than "
        f"abs=1e-2 from {expected} -- item 131 AC3 measured this curve's "
        f"spline-fit-asymmetry residual at 6.563e-03 deg on a reversing "
        f"curve; a larger move is a convention difference, not fit "
        f"asymmetry, and should not be silently loosened further"
    )


# =========================================================================== #
# AC9: no rule's firing set moves
# =========================================================================== #


def _rule_triple(finding: dict) -> Tuple[str, str, Tuple[int, ...]]:
    return (finding["rule_id"], finding["severity"], tuple(sorted(finding["labels"])))


@pytest.mark.parametrize("case_id", sorted(_PRE_098_GOLDEN_VERDICT_AND_FINDINGS.keys()))
def test_ac9_no_rule_firing_set_moves(case_id):
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == case_id)
    fresh = build_report_for_case(case)
    expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS[case_id]

    assert fresh["verdict"] == expected["verdict"], (
        f"{case_id}: verdict moved -- {fresh['verdict']!r} != {expected['verdict']!r} "
        f"(AC10: hand back, never retune a threshold to make this pass)"
    )
    actual_triples = [_rule_triple(f) for f in fresh["findings"]]
    expected_triples = [_rule_triple(f) for f in expected["findings"]]
    assert actual_triples == expected_triples, (
        f"{case_id}: (rule_id, severity, labels) firing set moved -- "
        f"{actual_triples} != {expected_triples} (AC10: hand back, never "
        f"retune a threshold to make this pass)"
    )


# AC10 ("a moved firing set is recorded and handed back, never absorbed") has
# no dedicated unit test here: its "no src/segfacet/heuristics/ file in the
# diff" half is a scope claim about a diff, which belongs on the branch, not
# in the suite (conventions §6) -- it is evidenced instead by the validator's
# `python .aide/scripts/aide.py scope 143 --base aide/queue-020` run (spec
# Implementation Steps, step 9). Its "hand back on a moved firing set" half is
# exercised by AC9 above: a moved (rule_id, severity, labels) tuple fails
# test_ac9_no_rule_firing_set_moves loudly, which is the trigger the hand-back
# is written against.


# =========================================================================== #
# AC11: every regenerator is deterministic run-to-run
# =========================================================================== #


def _tree_bytes(root: Path) -> Dict[str, bytes]:
    files = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert files, f"{root.as_posix()} produced no files"
    return files


def test_ac11_geometric_corpus_regenerates_byte_identically(tmp_path):
    dest1, dest2 = tmp_path / "corpus1", tmp_path / "corpus2"
    write_corpus(dest1)
    write_corpus(dest2)
    assert _tree_bytes(dest1) == _tree_bytes(dest2)


def test_ac11_intensity_corpus_regenerates_byte_identically(tmp_path):
    dest1, dest2 = tmp_path / "intensity1", tmp_path / "intensity2"
    write_intensity_corpus(dest1)
    write_intensity_corpus(dest2)
    assert _tree_bytes(dest1) == _tree_bytes(dest2)


def test_ac11_reference_artifact_regenerates_byte_identically(tmp_path):
    path1 = build_and_write_default(tmp_path / "reference1.json")
    path2 = build_and_write_default(tmp_path / "reference2.json")
    bytes1, bytes2 = Path(path1).read_bytes(), Path(path2).read_bytes()
    assert bytes1
    assert bytes1 == bytes2


def test_ac11_feature_catalogue_regenerates_byte_identically(tmp_path):
    from segfacet.catalogue import main as catalogue_main

    json1, md1 = tmp_path / "cat1.json", tmp_path / "cat1.md"
    json2, md2 = tmp_path / "cat2.json", tmp_path / "cat2.md"
    assert catalogue_main(["--json", str(json1), "--md", str(md1)]) == 0
    assert catalogue_main(["--json", str(json2), "--md", str(md2)]) == 0
    assert json1.read_bytes() == json2.read_bytes()
    assert md1.read_bytes() == md2.read_bytes()


def test_ac11_traceability_matrix_regenerates_byte_identically(tmp_path):
    import segfacet.traceability as traceability_module

    json1, md1 = tmp_path / "tm1.json", tmp_path / "tm1.md"
    json2, md2 = tmp_path / "tm2.json", tmp_path / "tm2.md"
    assert traceability_module.main(["--json", str(json1), "--md", str(md1)]) == 0
    assert traceability_module.main(["--json", str(json2), "--md", str(md2)]) == 0
    assert json1.read_bytes() == json2.read_bytes()
    assert md1.read_bytes() == md2.read_bytes()


def test_ac11_golden_evidence_regenerates_byte_identically(tmp_path):
    import segfacet.golden_evidence as golden_evidence_module

    out1, out2 = tmp_path / "ge1.json", tmp_path / "ge2.json"
    assert golden_evidence_module.main(["--out", str(out1)]) == 0
    assert golden_evidence_module.main(["--out", str(out2)]) == 0
    assert out1.read_bytes() == out2.read_bytes()


# =========================================================================== #
# AC12: every regenerated JSON artifact matches its committed copy through
# the item-127 helper
# =========================================================================== #


def test_ac12_geometric_corpus_manifest_matches_committed(tmp_path):
    manifest_path = write_corpus(tmp_path / "corpus")
    assert_matches_committed_artifact(
        manifest_path, _REPO_ROOT / "tests" / "corpus" / "manifest.json"
    )


def test_ac12_intensity_corpus_manifest_matches_committed(tmp_path):
    manifest_path = write_intensity_corpus(tmp_path / "intensity")
    assert_matches_committed_artifact(
        manifest_path, _REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json"
    )


def test_ac12_reference_default_matches_committed(tmp_path):
    fresh_path = build_and_write_default(tmp_path / "reference_default.json")
    assert_matches_committed_artifact(fresh_path, default_artifact_path())


def test_ac12_feature_catalogue_json_matches_committed(tmp_path):
    from segfacet.catalogue import main as catalogue_main

    json_dest, md_dest = tmp_path / "fc.json", tmp_path / "fc.md"
    assert catalogue_main(["--json", str(json_dest), "--md", str(md_dest)]) == 0
    assert_matches_committed_artifact(
        json_dest, _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    )


def test_ac12_traceability_matrix_json_matches_committed(tmp_path):
    import segfacet.traceability as traceability_module

    json_dest, md_dest = tmp_path / "tm.json", tmp_path / "tm.md"
    assert traceability_module.main(["--json", str(json_dest), "--md", str(md_dest)]) == 0
    assert_matches_committed_artifact(
        json_dest, _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.json"
    )


def test_ac12_golden_evidence_json_matches_committed(tmp_path):
    import segfacet.golden_evidence as golden_evidence_module

    out = tmp_path / "ge.json"
    assert golden_evidence_module.main(["--out", str(out)]) == 0
    assert_matches_committed_artifact(
        out, _REPO_ROOT / "docs" / "aide" / "golden_evidence.generated.json"
    )


# =========================================================================== #
# AC13: every regenerated binary fixture matches its committed copy
# byte-for-byte
# =========================================================================== #


def test_ac13_geometric_corpus_fixtures_match_committed_byte_for_byte(tmp_path):
    write_corpus(tmp_path / "corpus")
    committed_dir = _REPO_ROOT / "tests" / "corpus" / "fixtures"
    fresh_dir = tmp_path / "corpus" / "fixtures"
    committed_files = sorted(committed_dir.glob("*.nii.gz"))
    assert committed_files, "expected at least one committed geometric fixture"
    for committed_file in committed_files:
        fresh_file = fresh_dir / committed_file.name
        assert fresh_file.exists(), f"regenerated corpus is missing {fresh_file.name}"
        assert fresh_file.read_bytes() == committed_file.read_bytes(), committed_file.name


def test_ac13_intensity_corpus_fixtures_match_committed_byte_for_byte(tmp_path):
    write_intensity_corpus(tmp_path / "intensity")
    committed_dir = _REPO_ROOT / "tests" / "corpus" / "intensity" / "fixtures"
    fresh_dir = tmp_path / "intensity" / "fixtures"
    committed_files = sorted(committed_dir.glob("*.nii.gz"))
    assert committed_files, "expected at least one committed intensity fixture"
    for committed_file in committed_files:
        fresh_file = fresh_dir / committed_file.name
        assert fresh_file.exists(), f"regenerated intensity corpus is missing {fresh_file.name}"
        assert fresh_file.read_bytes() == committed_file.read_bytes(), committed_file.name


# =========================================================================== #
# AC14: no new byte-exact comparison escapes the guard
# =========================================================================== #


def test_ac14_this_module_produces_no_guard_violation():
    source = Path(__file__).read_text(encoding="utf-8")
    violations = guard.classify_module(source, "tests/test_143_s_axis_correction.py")
    assert violations == [], guard.violation_message(violations)


def test_ac14_allowlist_gains_no_new_entry():
    paths = {entry.path for entry in guard.ALLOWLIST}
    assert "docs/corpus-s-axis-correction.md" not in paths
    assert not any("143" in entry.reason for entry in guard.ALLOWLIST), (
        "an ALLOWLIST entry appears to reference item 143 -- AC14 requires "
        "zero allowlist growth for this item"
    )


# =========================================================================== #
# AC15: the two committed Markdown renderings are regenerated and match
# =========================================================================== #


def test_ac15_feature_catalogue_markdown_matches_committed_byte_for_byte(tmp_path):
    from segfacet.catalogue import main as catalogue_main

    json_dest, md_dest = tmp_path / "fc.json", tmp_path / "fc.md"
    assert catalogue_main(["--json", str(json_dest), "--md", str(md_dest)]) == 0
    committed = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
    assert md_dest.read_bytes() == committed.read_bytes()


def test_ac15_traceability_matrix_markdown_matches_committed_byte_for_byte(tmp_path):
    import segfacet.traceability as traceability_module

    json_dest, md_dest = tmp_path / "tm.json", tmp_path / "tm.md"
    assert traceability_module.main(["--json", str(json_dest), "--md", str(md_dest)]) == 0
    committed = _REPO_ROOT / "docs" / "aide" / "traceability_matrix.generated.md"
    # Byte-exact against a committed artifact allowlisted under
    # "no-float-leaf" (item 149) -- see this module's "Shared helpers"
    # section for the ground (zero float leaves).
    assert md_dest.read_bytes() == committed.read_bytes()


def test_ac15_gitattributes_still_pins_both_markdown_renderings_eol_lf():
    text = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for rel_path in (
        "docs/aide/feature_catalogue.generated.md",
        "docs/aide/traceability_matrix.generated.md",
    ):
        pattern = re.compile(re.escape(rel_path) + r"[^\n]*eol=lf")
        assert pattern.search(text), rel_path


# =========================================================================== #
# AC16/AC17: the moved/unmoved record exists, covers every artifact, and
# every row names what was compared and what happened
# =========================================================================== #

_RECORD_DOC_PATH = _REPO_ROOT / "docs" / "corpus-s-axis-correction.md"

#: The eight committed artifacts that are not a manifest-listed fixture
#: (spec Testing Strategy, AC16/AC17).
_NON_CORPUS_REQUIRED_ARTIFACTS: Tuple[str, ...] = (
    "tests/corpus/094_pre_migration_snapshot.json",
    "src/segfacet/reference/reference_default.json",
    "src/segfacet/reference/reference_verse_v1.json",
    "docs/aide/feature_catalogue.generated.json",
    "docs/aide/feature_catalogue.generated.md",
    "docs/aide/traceability_matrix.generated.json",
    "docs/aide/traceability_matrix.generated.md",
    "docs/aide/golden_evidence.generated.json",
)


def _required_artifact_paths() -> Set[str]:
    geo_manifest = json.loads((_REPO_ROOT / "tests" / "corpus" / "manifest.json").read_text(encoding="utf-8"))
    intensity_manifest = json.loads(
        (_REPO_ROOT / "tests" / "corpus" / "intensity" / "manifest.json").read_text(encoding="utf-8")
    )
    paths: Set[str] = {"tests/corpus/manifest.json", "tests/corpus/intensity/manifest.json"}
    for case in geo_manifest["cases"]:
        paths.add(f"tests/corpus/{case['scan_fixture']}")
        paths.add(f"tests/corpus/{case['seg_fixture']}")
    for case in intensity_manifest["cases"]:
        paths.add(f"tests/corpus/intensity/{case['scan_fixture']}")
        paths.add(f"tests/corpus/intensity/{case['seg_fixture']}")
    paths.update(_NON_CORPUS_REQUIRED_ARTIFACTS)
    return paths


def _parse_markdown_table(text: str) -> List[Dict[str, str]]:
    lines = [ln for ln in text.splitlines() if ln.strip().startswith("|")]
    assert len(lines) >= 3, (
        "expected docs/corpus-s-axis-correction.md to contain a markdown "
        "table (header row, separator row, and at least one data row)"
    )

    def _cells(line: str) -> List[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = [h.lower() for h in _cells(lines[0])]
    rows = []
    for line in lines[2:]:
        cells = _cells(line)
        assert len(cells) == len(header), f"row/header cell-count mismatch: {line!r}"
        rows.append(dict(zip(header, cells)))
    return rows


def _find_column(header: List[str], *needles: str) -> str:
    for col in header:
        if any(needle in col for needle in needles):
            return col
    raise AssertionError(f"no column matching {needles!r} found in header {header!r}")


def _normalise_cell_path(cell: str) -> str:
    return cell.strip().strip("`").strip()


def _load_record_rows() -> Tuple[List[Dict[str, str]], List[str]]:
    assert _RECORD_DOC_PATH.exists(), f"missing {_RECORD_DOC_PATH.as_posix()} (AC16)"
    text = _RECORD_DOC_PATH.read_text(encoding="utf-8")
    rows = _parse_markdown_table(text)
    header = list(rows[0].keys()) if rows else []
    return rows, header


def test_ac16_record_covers_exactly_the_required_artifact_set():
    rows, header = _load_record_rows()
    path_col = _find_column(header, "path", "artifact")
    row_paths = {_normalise_cell_path(row[path_col]) for row in rows}
    required = _required_artifact_paths()
    missing = required - row_paths
    extra = row_paths - required
    assert not missing, f"docs/corpus-s-axis-correction.md is missing rows for: {sorted(missing)}"
    assert not extra, f"docs/corpus-s-axis-correction.md has rows outside the required set: {sorted(extra)}"


def test_ac17_every_row_names_what_was_compared_and_what_happened():
    rows, header = _load_record_rows()
    compared_col = _find_column(header, "compared")
    verdict_col = _find_column(header, "verdict")
    detail_col = _find_column(header, "detail")
    assert rows, "expected at least one record row"
    for row in rows:
        assert row[compared_col].strip(), f"empty 'compared by' cell: {row}"
        assert row[verdict_col].strip().lower() in {"moved", "unmoved"}, f"bad verdict cell: {row}"
        assert row[detail_col].strip(), f"empty 'detail' cell: {row}"


# =========================================================================== #
# AC18: reference_verse_v1.json is unmoved, and that is recorded as evidence
# =========================================================================== #


def test_ac18_reference_verse_v1_row_reads_unmoved():
    rows, header = _load_record_rows()
    path_col = _find_column(header, "path", "artifact")
    verdict_col = _find_column(header, "verdict")
    row = next(
        (r for r in rows if _normalise_cell_path(r[path_col]) == "src/segfacet/reference/reference_verse_v1.json"),
        None,
    )
    assert row is not None, "no record row for src/segfacet/reference/reference_verse_v1.json"
    assert row[verdict_col].strip().lower() == "unmoved", (
        "reference_verse_v1.json is built from the real VerSe19 cohort, which "
        "no synthetic input feeds -- its row must read 'unmoved', not a "
        "computed comparison"
    )


# =========================================================================== #
# AC19: the loader snapshot tracks the regenerated fixtures
# =========================================================================== #


def test_ac19_snapshot_covers_all_15_entries_across_both_corpora():
    snapshot_path = _REPO_ROOT / "tests" / "corpus" / "094_pre_migration_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert len(snapshot) == 15
    assert any("intensity/fixtures" in entry["path"] for entry in snapshot.values())
    assert any(
        "intensity" not in entry["path"] and "corpus/fixtures" in entry["path"]
        for entry in snapshot.values()
    )


def test_ac19_snapshot_record_row_reads_moved():
    rows, header = _load_record_rows()
    path_col = _find_column(header, "path", "artifact")
    verdict_col = _find_column(header, "verdict")
    row = next(
        (r for r in rows if _normalise_cell_path(r[path_col]) == "tests/corpus/094_pre_migration_snapshot.json"),
        None,
    )
    assert row is not None, "no record row for tests/corpus/094_pre_migration_snapshot.json"
    assert row[verdict_col].strip().lower() == "moved", (
        "the snapshot is re-captured against the corrected fixtures, so its "
        "digests move even though the loader logic under test does not"
    )


# AC21 ("the report format contract is untouched") has no dedicated unit test
# here either, for the same reason as AC10: "report_format_contract.json is
# absent from this item's diff" is a scope claim about a diff, which belongs
# on the branch (the validator's `aide scope` run), not in the suite
# (conventions §6) -- and CLAUDE.md is explicit that the fixture is
# regenerated via `python -m tests.report_format_fixture`, "never from a
# test". AC21's other half -- tests/test_126_golden_retirement.py passing --
# needs no new assertion here: that module runs unmodified elsewhere in this
# same suite.


# =========================================================================== #
# Adversarial / edge cases beyond the direct AC tests above
# =========================================================================== #


def test_adversarial_single_level_span_does_not_raise_or_produce_empty_map():
    clean = build_clean_spine(levels=("L3",))
    assert len(clean.labels) == 1
    data = np.asanyarray(clean.seg_img.dataobj)
    assert np.any(data == clean.labels[0])


def test_adversarial_degenerate_lr_spacing_through_eval_harness_does_not_raise():
    """Mirrors test_116's own AC9 path (a degenerate (0.0, 1.0, 1.0) spacing
    fed to evaluate_case, not to build_clean_spine's own spacing argument, per
    that test's own construction) to confirm this item reopens nothing there."""
    clean = build_clean_spine(levels=["L1"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)
    case = EvaluationCase(
        case_id="item143-adversarial-zero-spacing",
        gt=gt_array,
        candidate=gt_array,
        expected={"expected_verdict": "pass"},
        spacing=(0.0, 1.0, 1.0),
    )
    result = evaluate_case(case, bundled_default_config())  # must not raise
    assert result.overlap.mean_dice == 1.0


def test_adversarial_non_contiguous_span_still_raises_facet_input_error():
    with pytest.raises(FacetInputError):
        build_clean_spine(levels=("L1", "L3"))


def test_adversarial_two_calls_in_one_session_are_equal():
    first = build_clean_spine()
    second = build_clean_spine()
    assert np.array_equal(
        np.asanyarray(first.seg_img.dataobj), np.asanyarray(second.seg_img.dataobj)
    )
    assert first.voxel_counts == second.voxel_counts
    assert first.shape == second.shape


def test_adversarial_build_clean_spine_mutates_no_module_level_state():
    first = build_clean_spine()
    data = np.asanyarray(first.seg_img.dataobj)
    data_copy = data.copy()
    data[:] = 0  # mutate the caller's own returned array in place

    second = build_clean_spine()
    assert np.array_equal(np.asanyarray(second.seg_img.dataobj), data_copy), (
        "a second call after mutating the first call's returned array "
        "produced a different result -- suggests shared/module-level state"
    )
