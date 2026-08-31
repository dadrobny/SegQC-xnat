"""Tests for item 116 -- making the synthetic corpus RAS-native.

Covers Acceptance Criteria AC1-AC13:

- AC1: ``build_clean_spine`` stacks bodies along array axis 2, and the
  emitted affine resolves to axcodes carrying S/I on axis 2.
- AC2: for every fixture the generator emits, the affine-derived S/I axis
  matches the array axis the body centroids actually vary along -- asserted
  directly (an independent, affine-free oracle), not by source inspection.
  An adversarial fixture whose affine is deliberately mutated to lie about
  this must fail the same check.
- AC3: loading a generated fixture through ``segfacet.io.load_volume`` is an
  array-identity operation.
- AC4: ``clean_gt.py``'s docstring states the affine-derived contract and no
  longer claims axis 0 is superior-inferior.
- AC5: ``CropAtBorderPerturbation`` resolves a named face's axis from the
  volume's own affine, not a hardcoded index -- proven behaviourally with
  hand-built fixtures in several different axis orders.
- AC6: cropping toward each of the six named anatomical faces sets that
  face's ``touches_*`` flag on the real generator's output.
- AC7: every corpus case still trips the same ``(rule_id, labels)`` pairs as
  the pre-migration corpus, sourced from the goldens at a pinned reference
  commit (``aeb2f55``, read from git history).
- AC8: the ``mode6_crop_at_border`` per-mode sensitivity is restored to 1.0.
- AC9: a ``(0.0, 1.0, 1.0)`` spacing through the eval harness does not raise.
- AC10/AC11: regenerating fixtures, the manifest, and goldens twice is
  byte-identical, and the manifest still describes every canonical case.

Adversarial / edge cases: a single-body spine; a spine with an interior
level removed; anisotropic spacing; a fixture whose affine is deliberately
made untruthful (AC2 must fail for it).

All fixtures are built in-memory or under pytest's ``tmp_path`` -- no
absolute filesystem paths, no network. The AC7 reference-golden lookup shells
out to ``git`` read-only against the local repository and skips (rather than
errors) if ``git`` or the pinned commit is unavailable, since it is a
robustness aid, not this item's core contract.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from segfacet.config import bundled_default_config
from segfacet.eval.harness import EvaluationCase, evaluate_case, evaluate_cohort
from segfacet.eval.metrics import compute_cohort_metrics
from segfacet.features.geometry import compute_label_geometry
from segfacet.io import load_volume
from segfacet.synth import clean_gt as clean_gt_module
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.coverage_border_overlap import (
    CropAtBorderPerturbation,
    RemoveLevelPerturbation,
)
from segfacet.synth.corpus import CASE_RECIPE, load_manifest, write_corpus
from segfacet.synth.golden import build_report_for_case, write_goldens
from segfacet.synth.perturbation import FAILURE_MODE_NAMES
from segfacet.synth.regression import loaded_seg_image


_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent


# =========================================================================== #
# Shared helpers -- an affine-free oracle for "which axis does the array
# actually stack along", independent of segfacet.features.geometry so AC1/AC2
# are not just re-testing the production code against itself.
# =========================================================================== #


def _stacking_axis_from_array(seg_img, labels) -> int:
    """The array axis whose per-label centroid coordinate varies the most
    across *labels* -- the axis the bodies are actually stacked along,
    computed purely from voxel data (no affine involved)."""
    data = np.asanyarray(seg_img.dataobj)
    centroids = []
    for label in labels:
        coords = np.argwhere(data == label)
        assert coords.size, f"label {label!r} has no voxels"
        centroids.append(coords.mean(axis=0))
    centroids = np.asarray(centroids, dtype=float)
    variances = centroids.var(axis=0)
    return int(np.argmax(variances))


def _si_axis_from_affine(affine) -> int:
    """The array axis whose ``nib.aff2axcodes`` letter is S or I."""
    axcodes = nib.aff2axcodes(affine)
    for axis, code in enumerate(axcodes):
        if code in ("S", "I"):
            return axis
    raise AssertionError(f"affine resolves no S/I axis: {axcodes!r}")


def _affine_truthful(seg_img, labels) -> bool:
    """True iff the affine's claimed S/I axis matches the axis the array
    actually stacks along (an independent, affine-free oracle)."""
    return _si_axis_from_affine(seg_img.affine) == _stacking_axis_from_array(seg_img, labels)


def _affine_for_axcodes(spacing, axcodes) -> np.ndarray:
    """A 4x4 axis-permutation/flip affine (no rotation) resolving to
    *axcodes*, with *spacing* magnitudes on each array axis. Mirrors
    tests/test_108_affine_faces.py's fixture builder -- not imported from
    segfacet, so this test does not assume the production mapping mechanism,
    only its observable result."""
    world_axis = {
        "L": (0, -1), "R": (0, 1),
        "P": (1, -1), "A": (1, 1),
        "I": (2, -1), "S": (2, 1),
    }
    m = np.zeros((4, 4))
    m[3, 3] = 1.0
    for arr_axis, code in enumerate(axcodes):
        w_axis, sign = world_axis[code]
        m[w_axis, arr_axis] = sign * float(spacing[arr_axis])
    return m


def _labelmap_with_block(shape, box, label=1, spacing=(1.0, 1.0, 1.0), axcodes=("R", "A", "S")):
    (x0, x1), (y0, y1), (z0, z1) = box
    data = np.zeros(shape, dtype=np.uint16)
    data[x0:x1, y0:y1, z0:z1] = label
    affine = _affine_for_axcodes(spacing, axcodes)
    return nib.Nifti1Image(data, affine)


# =========================================================================== #
# AC1: bodies stack along the superior-inferior axis
# =========================================================================== #


def test_ac1_bodies_stack_along_array_axis_2():
    clean = build_clean_spine()
    assert _stacking_axis_from_array(clean.seg_img, clean.labels) == 2


def test_ac1_affine_resolves_si_onto_axis_2():
    clean = build_clean_spine()
    axcodes = nib.aff2axcodes(clean.seg_img.affine)
    assert axcodes[2] in ("S", "I")


# =========================================================================== #
# AC2: the affine tells the truth
# =========================================================================== #


def test_ac2_affine_matches_actual_array_variation_for_default_spine():
    clean = build_clean_spine()
    assert _affine_truthful(clean.seg_img, clean.labels) is True


@pytest.mark.parametrize(
    "case", CASE_RECIPE, ids=lambda entry: entry.case_id,
)
def test_ac2_affine_truthful_for_every_generated_fixture(case):
    """AC2 over every canonical corpus case (freshly built in-memory, not
    from disk) -- each operator's output must still carry a truthful
    affine."""
    from segfacet.synth.perturbation import get_perturbation

    clean = build_clean_spine(**case.base)
    operator_cls = get_perturbation(case.perturbation)
    operator = operator_cls(**case.perturbation_params)
    result = operator.apply(clean.seg_img, case.seed)

    data = np.asanyarray(result.labelmap.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)
    if len(labels) < 2:
        pytest.skip(f"case {case.case_id!r} has fewer than 2 present labels")
    assert _affine_truthful(result.labelmap, labels) is True, (
        f"case {case.case_id!r}: affine-claimed S/I axis does not match the "
        "axis the array actually stacks along"
    )


def test_adv_untruthful_affine_fails_ac2_check():
    """Adversarial: a fixture whose affine is deliberately mutated to claim
    the wrong S/I axis must FAIL the AC2 truthfulness check."""
    clean = build_clean_spine()
    data = np.array(np.asanyarray(clean.seg_img.dataobj), copy=True)
    good_affine = np.array(clean.seg_img.affine, copy=True)

    # Swap the affine's axis-0 and axis-2 rows so it now claims axis 0 (not
    # axis 2) carries S/I -- the array itself is untouched, so it still
    # genuinely stacks along axis 2.
    bad_affine = good_affine.copy()
    bad_affine[[0, 2]] = bad_affine[[2, 0]]
    mutated = nib.Nifti1Image(data, bad_affine)

    assert _affine_truthful(mutated, clean.labels) is False


# =========================================================================== #
# AC3: no reorientation on load
# =========================================================================== #


def test_ac3_load_volume_is_array_identity(tmp_path):
    clean = build_clean_spine()
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(clean.seg_img, str(seg_path))

    volume = load_volume(seg_path, integer_labels=True)
    original = np.asanyarray(clean.seg_img.dataobj)

    assert volume.data.shape == original.shape
    assert np.array_equal(volume.data, original)
    assert np.allclose(np.asarray(volume.affine), np.asarray(clean.seg_img.affine), atol=1e-6)


# =========================================================================== #
# AC4: the docstring states the new contract
# =========================================================================== #


def test_ac4_docstring_no_longer_claims_axis_0_is_superior_inferior():
    doc = (clean_gt_module.__doc__ or "").lower()
    assert "axis 0 is superior-inferior" not in doc, (
        "clean_gt.py's docstring still claims the legacy axis-0 convention"
    )


def test_ac4_docstring_states_affine_as_source_of_truth():
    doc = (clean_gt_module.__doc__ or "").lower()
    assert "affine" in doc, (
        "clean_gt.py's docstring does not mention the affine as the source "
        "of the axis convention"
    )
    assert "axis 2" in doc, (
        "clean_gt.py's docstring does not document axis 2 as the stacking axis"
    )


# =========================================================================== #
# AC5: operators select axes by anatomical intent (resolved via the affine)
# =========================================================================== #


@pytest.mark.parametrize(
    "axcodes",
    [("R", "A", "S"), ("S", "R", "A"), ("A", "S", "R")],
    ids=["ras-axis2-is-s", "sra-axis0-is-s", "asr-axis1-is-s"],
)
def test_ac5_crop_at_border_resolves_superior_from_each_fixtures_own_affine(axcodes):
    """AC5: the same 'superior' crop request, applied to fixtures whose S/I
    direction sits on a *different* array axis each time, always sets
    touches_superior on the result -- proving the axis is resolved from each
    fixture's own affine, not a hardcoded index."""
    shape = (20, 20, 20)
    box = ((8, 12), (8, 12), (8, 12))  # centered -- touches no face yet
    seg = _labelmap_with_block(shape, box, label=1, axcodes=axcodes)

    result = CropAtBorderPerturbation(target_label=1, face="superior", crop_depth=3).apply(
        seg, seed=0
    )
    geo = compute_label_geometry(result.labelmap, label=1)
    assert geo.touches_superior is True
    assert geo.touches_inferior is False
    assert geo.touches_left is False
    assert geo.touches_right is False
    assert geo.touches_anterior is False
    assert geo.touches_posterior is False


# =========================================================================== #
# AC6: crop-at-border names the face it cropped -- all six faces
# =========================================================================== #


@pytest.mark.parametrize(
    "face", ["superior", "inferior", "left", "right", "anterior", "posterior"]
)
def test_ac6_crop_at_border_sets_the_matching_touches_flag(face):
    clean = build_clean_spine()
    target = clean.labels[len(clean.labels) // 2]  # an interior body

    geo_before = compute_label_geometry(clean.seg_img, target)
    assert getattr(geo_before, f"touches_{face}") is False

    result = CropAtBorderPerturbation(target_label=target, face=face, crop_depth=3).apply(
        clean.seg_img, seed=0
    )
    geo_after = compute_label_geometry(result.labelmap, target)
    assert getattr(geo_after, f"touches_{face}") is True


# =========================================================================== #
# AC7: every mode still fires its designated rule on the same labels
# =========================================================================== #


#: The commit whose committed goldens are the AC7 identity reference:
#: ``aeb2f55`` -- "Merge pull request #55 from dadrobny/chore/framework-1.21.0",
#: the last ``main`` commit before queue-017 landed (PR #56, 2026-08-30).
#:
#: This used to be ``git merge-base HEAD main``. That was correct only while
#: queue-017 was an open PR: the strip logic below assumes the reference
#: golden predates item 120, and once PR #56 merged, every branch's merge base
#: became current ``main``, whose goldens already carry item 120's added pair.
#: Measured 2026-08-31 --
#: ``git show aeb2f55:tests/corpus/golden/mode1_displace.json | grep -c '"mislabel"'``
#: gives 0, while the same probe at ``fda97b0`` (``main`` after PR #56) gives 1
#: -- so ``mode1_displace`` and ``mode6_crop_at_border`` failed by
#: construction against a moving merge base. ``aeb2f55`` is the exact snapshot
#: every queue-017 branch was validated against, so identity vs. that commit
#: is what the strip logic always meant.
#:
#: The goldens are read from git history (``git show <sha>:<path>``), never
#: from the working tree, so item 126's deletion of
#: ``tests/corpus/golden/*.json`` does not affect this test.
_REFERENCE_GOLDEN_SHA = "aeb2f5581878b76336de5716ed118dcea37dfb61"


def _reference_sha():
    """Return ``_REFERENCE_GOLDEN_SHA`` if it is reachable in this clone, else
    ``None`` (no ``git``, or a shallow checkout that does not carry the
    commit). CI checks out with ``fetch-depth: 0``, so it is reachable there."""
    try:
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{_REFERENCE_GOLDEN_SHA}^{{commit}}"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if probe.returncode != 0:
        return None
    return _REFERENCE_GOLDEN_SHA


def _reference_golden(case_id: str, sha: str) -> dict:
    result = subprocess.run(
        ["git", "show", f"{sha}:tests/corpus/golden/{case_id}.json"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git show failed for {sha}:tests/corpus/golden/{case_id}.json: {result.stderr}"
        )
    return json.loads(result.stdout)


def _rule_label_pairs(findings) -> list:
    return sorted((f["rule_id"], tuple(sorted(f["labels"]))) for f in findings)


_MANIFEST_CASES = load_manifest()["cases"]
_REFERENCE_SHA = _reference_sha()


#: Item 120 makes the per-vertebra spline offset a held-out measurement,
#: which deliberately adds a ``mislabel`` finding on label 22 to these two
#: cases (AC18/AC23) that the pre-120 reference snapshot's committed golden
#: (``_REFERENCE_GOLDEN_SHA``) does not carry. Widened by human decision, 2026-08-28 -- see
#: docs/aide/items/120-per-vertebra-offset-that-separates.md's Authorised
#: paths entry for this test.
_ITEM_120_ADDED_MISLABEL_PAIR = ("mislabel", (22,))
_ITEM_120_NEW_MISLABEL_CASES = frozenset({"mode1_displace", "mode6_crop_at_border"})


@pytest.mark.skipif(
    _REFERENCE_SHA is None,
    reason="reference commit aeb2f55 not present in this clone",
)
@pytest.mark.parametrize("case", _MANIFEST_CASES, ids=lambda c: c["case_id"])
def test_ac7_case_identity_preserved_vs_merge_base(case):
    """AC7: the freshly-built report's (rule_id, sorted labels) pairs match
    the pre-migration committed golden's exactly -- numeric feature values may
    move, but which rule fires on which labels must not. The reference golden
    is the one committed at ``_REFERENCE_GOLDEN_SHA`` (``aeb2f55``), read from
    git history. The ``_vs_merge_base`` in this test's name is historical --
    it was a moving ``git merge-base HEAD main`` until 2026-08-31 -- and is
    kept because other artefacts reference the test by name.

    Except for ``mode1_displace`` and ``mode6_crop_at_border``, where item
    120 deliberately adds a ``mislabel`` finding on label 22 (AC18/AC23):
    that one added pair is stripped from the fresh side before comparing so
    the rest of each case's rule/label identity is still pinned exactly."""
    fresh = build_report_for_case(case)
    committed = _reference_golden(case["case_id"], _REFERENCE_SHA)
    fresh_pairs = _rule_label_pairs(fresh["findings"])
    if case["case_id"] in _ITEM_120_NEW_MISLABEL_CASES:
        assert _ITEM_120_ADDED_MISLABEL_PAIR in fresh_pairs, (
            f"case {case['case_id']!r}: expected item 120's deliberate "
            "mislabel finding on label 22, but it did not fire"
        )
        fresh_pairs = [p for p in fresh_pairs if p != _ITEM_120_ADDED_MISLABEL_PAIR]
    assert fresh_pairs == _rule_label_pairs(committed["findings"]), (
        f"case {case['case_id']!r}: designated rule/labels changed relative "
        "to the pre-migration reference golden (aeb2f55)"
    )


# =========================================================================== #
# AC8: mode-6 sensitivity is restored
# =========================================================================== #


def _build_corpus_cohort():
    manifest_cases = load_manifest()["cases"]
    clean_case = next(c for c in manifest_cases if c["case_id"] == "clean_control")
    gt_img = loaded_seg_image(clean_case)

    eval_cases = []
    for case in manifest_cases:
        candidate_img = gt_img if case["case_id"] == "clean_control" else loaded_seg_image(case)
        eval_cases.append(
            EvaluationCase(
                case_id=case["case_id"], gt=gt_img, candidate=candidate_img, expected=case
            )
        )
    return eval_cases


def test_ac8_mode6_crop_at_border_sensitivity_is_restored_to_one():
    cohort = evaluate_cohort(_build_corpus_cohort(), bundled_default_config())
    metrics = compute_cohort_metrics(cohort, failure_modes=FAILURE_MODE_NAMES)
    entry = next(m for m in metrics.per_mode if m.failure_mode == 6)
    assert entry.n_cases > 0
    assert entry.sensitivity == 1.0


# =========================================================================== #
# AC9: the degenerate-spacing path does not raise
# =========================================================================== #


def test_ac9_zero_spacing_component_does_not_raise_and_zeroes_physical_volume():
    clean = build_clean_spine(levels=["L1"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)

    case = EvaluationCase(
        case_id="ac9-zero-spacing",
        gt=gt_array,
        candidate=gt_array,
        expected={"expected_verdict": "pass"},
        spacing=(0.0, 1.0, 1.0),
    )
    result = evaluate_case(case, bundled_default_config())  # must not raise

    assert result.overlap.mean_dice == 1.0
    for entry in result.overlap.per_label:
        assert entry.physical_volume_mm3 == 0.0


# =========================================================================== #
# AC10/AC11: fixtures, manifest, and goldens regenerate twice byte-identically
# =========================================================================== #


def test_ac10_regenerating_corpus_twice_is_byte_identical(tmp_path):
    dest1 = tmp_path / "corpus1"
    dest2 = tmp_path / "corpus2"
    write_corpus(dest1)
    write_corpus(dest2)

    files1 = {p.relative_to(dest1).as_posix(): p.read_bytes() for p in dest1.rglob("*") if p.is_file()}
    files2 = {p.relative_to(dest2).as_posix(): p.read_bytes() for p in dest2.rglob("*") if p.is_file()}
    assert files1 == files2
    assert files1  # sanity: not vacuously empty


def test_ac10_regenerating_goldens_twice_is_byte_identical(tmp_path):
    dest1 = tmp_path / "golden1"
    dest2 = tmp_path / "golden2"
    write_goldens(dest1)
    write_goldens(dest2)

    files1 = {p.name: p.read_bytes() for p in dest1.glob("*.json")}
    files2 = {p.name: p.read_bytes() for p in dest2.glob("*.json")}
    assert files1 == files2
    assert files1


def test_ac11_manifest_regenerates_byte_identically(tmp_path):
    dest1 = tmp_path / "m1"
    dest2 = tmp_path / "m2"
    path1 = write_corpus(dest1)
    path2 = write_corpus(dest2)
    assert path1.read_bytes() == path2.read_bytes()


def test_ac11_manifest_still_describes_every_canonical_case(tmp_path):
    dest = tmp_path / "corpus"
    manifest_path = write_corpus(dest)
    manifest = load_manifest(manifest_path)
    case_ids = {c["case_id"] for c in manifest["cases"]}
    expected_ids = {entry.case_id for entry in CASE_RECIPE}
    assert case_ids == expected_ids


# =========================================================================== #
# Adversarial -- single-body spine
# =========================================================================== #


def test_adv_single_body_spine_stacking_axis_is_still_axis_2():
    clean = build_clean_spine(levels=["L3"])
    axcodes = nib.aff2axcodes(clean.seg_img.affine)
    assert axcodes[2] in ("S", "I")

    data = np.asanyarray(clean.seg_img.dataobj)
    coords = np.argwhere(data == clean.labels[0])
    # A non-degenerate extent along axis 2 (the body has real thickness
    # there), consistent with axis 2 being the stacking/body axis even with
    # only one body present (no cross-label variance to compare against).
    assert coords[:, 2].max() > coords[:, 2].min()


# =========================================================================== #
# Adversarial -- a spine with one interior level missing
# =========================================================================== #


def test_adv_spine_with_missing_level_still_stacks_correctly_on_axis_2():
    clean = build_clean_spine()
    result = RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0)
    remaining_labels = [label for label in clean.labels if label != 22]

    assert _stacking_axis_from_array(result.labelmap, remaining_labels) == 2
    assert _affine_truthful(result.labelmap, remaining_labels) is True


# =========================================================================== #
# Adversarial -- anisotropic spacing
# =========================================================================== #


def test_adv_anisotropic_spacing_preserves_stacking_axis_and_truthfulness():
    clean = build_clean_spine(spacing=(2.0, 0.5, 1.5))
    assert _stacking_axis_from_array(clean.seg_img, clean.labels) == 2
    assert _affine_truthful(clean.seg_img, clean.labels) is True
    assert clean.seg_img.header.get_zooms()[:3] == pytest.approx((2.0, 0.5, 1.5))
