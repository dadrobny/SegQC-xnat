"""Tests for item 040 — committed synthetic fixture corpus spanning all 8
failure modes + the clean-control positive control, and its manifest.

Covers Acceptance Criteria AC1-AC18:

- AC1-AC6 (Group A, manifest structure & completeness): the manifest loads,
  is versioned, and round-trips through json.dumps/json.loads; every §6 mode
  0-8 is represented; case ids are unique and filesystem-safe; every case
  carries the full schema with correct types; failure_mode_name matches the
  shared FAILURE_MODE_NAMES taxonomy; expected_verdict is a valid Severity
  label.
- AC7-AC9 (Group B, detection classification): detection is one of
  {"pipeline", "reconstructed_record"}; modes 1/4/8 are classified
  reconstructed_record with the matching reconstruction technique, the rest
  are pipeline with no reconstruction; the three reconstructed-record
  fixtures genuinely hide their mode from plain run_qc.
- AC10-AC12 (Group C, fixtures load via the Stage 0 loader): every
  referenced fixture file exists; every case loads via load_case with a
  non-empty label inventory and matching scan/seg shapes; the clean_control
  fixture's inventory matches build_clean_spine()'s voxel counts exactly.
- AC13-AC18 (Group D, positive control & reproducibility): the clean_control
  case declares the queue-mandated pass verdict; the committed clean_control
  fixture actually passes the real pipeline (no findings, Severity.PASS);
  write_corpus(tmp) reproduces every fixture's loaded content; two
  write_corpus calls are byte-identical to each other and to the committed
  corpus; rebuilding each non-clean case's operator reproduces the
  manifest's expected_* fields verbatim (single source of truth); the
  one-command `main()` entry point regenerates a manifest with the same
  case-id set.

Adversarial / edge-case scenarios included:
- The case-level mode5_remove_level case (expected_labels == []) still loads
  and is schema-valid.
- Every seg_fixture path is distinct (no two cases silently share a seg).
- All nine cases share exactly one scan_fixture path (the dedup contract).
- The shared base scan is byte-identical to a freshly written base
  build_clean_spine().scan_img.
- Re-running write_corpus over an existing directory reproduces identical
  bytes (idempotent regeneration).
- load_manifest on the committed file and on a fresh write_corpus output
  (a different directory) produce equal cases (relocatable, path-relative).
- A manifest case referencing a nonexistent fixture file is detected by the
  AC10-style existence check.
- Duplicate case ids are detected by the AC3-style uniqueness check.
- An unknown detection value is detected by the AC7-style domain check.
"""

from __future__ import annotations

import json
import re

import nibabel as nib
import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator
from segfacet.config import bundled_default_config
from segfacet.io import load_case
from segfacet.pipeline import run_qc
from segfacet.synth import FAILURE_MODE_NAMES, build_clean_spine, get_perturbation
from segfacet.synth.corpus import (
    CORPUS_DIR,
    FIXTURES_DIRNAME,
    MANIFEST_PATH,
    MANIFEST_VERSION,
    load_manifest,
    main,
    write_corpus,
)
from segfacet.verdict import Severity

# =========================================================================== #
# Schema constants (mirroring the manifest schema documented in the item spec)
# =========================================================================== #

_VALID_DETECTIONS = {"pipeline", "reconstructed_record"}
_VALID_VERDICTS = {"pass", "flagged-for-review", "fail"}
_VALID_RECONSTRUCTIONS = {
    "monotonic_true_spatial_order",
    "overlap_mask_stack",
}
_RECONSTRUCTED_MODES = {4, 8}
_PIPELINE_ONLY_MODES = {0, 1, 2, 3, 5, 6, 7}

_CASE_ID_RE = re.compile(r"^[a-z0-9_]+$")

_SCHEMA_KEYS_TYPES = {
    "case_id": str,
    "failure_mode": int,
    "failure_mode_name": str,
    "detection": str,
    "perturbation": str,
    "perturbation_params": dict,
    "seed": int,
    "base": dict,
    "scan_fixture": str,
    "seg_fixture": str,
    "expected_rule_ids": list,
    "expected_labels": list,
    "expected_verdict": str,
    "detail": str,
}


# =========================================================================== #
# Helpers
# =========================================================================== #


def _manifest():
    return load_manifest()


def _cases():
    return _manifest()["cases"]


def _case(case_id):
    for c in _cases():
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _resolve(case, key):
    """Absolute path for a case's *key* fixture, resolved under CORPUS_DIR."""
    return CORPUS_DIR / case[key]


def _loaded_case(case):
    return load_case(_resolve(case, "scan_fixture"), _resolve(case, "seg_fixture"))


def _seg_nifti_from_case(case):
    """A fresh nib.Nifti1Image built from the *loaded* seg's data/affine, so
    run_qc exercises exactly the Stage-0-loaded content (per AC9/AC14)."""
    seg = _loaded_case(case).seg
    return nib.Nifti1Image(seg.data, seg.affine, dtype=seg.data.dtype)


def _findings(seg_img):
    case_result, _block = run_qc(seg_img, bundled_default_config())
    return case_result.findings


# =========================================================================== #
# A. Manifest structure & completeness (AC1-AC6)
# =========================================================================== #


def test_ac1_manifest_loads_versioned_and_round_trips():
    """AC1: load_manifest() returns a dict with manifest_version == 1 and a
    non-empty cases list; manifest.json parses via json.loads and round-trips
    through json.dumps/json.loads unchanged."""
    manifest = load_manifest()
    assert isinstance(manifest, dict)
    assert manifest["manifest_version"] == MANIFEST_VERSION == 1
    assert isinstance(manifest["cases"], list)
    assert len(manifest["cases"]) > 0

    parsed = json.loads(MANIFEST_PATH.read_text())
    assert parsed == manifest
    assert json.loads(json.dumps(manifest)) == manifest


def test_ac2_every_mode_0_through_8_represented():
    """AC2: the multiset of failure_mode over cases contains >= 1 entry for
    each of {0, ..., 8}."""
    modes = {c["failure_mode"] for c in _cases()}
    assert modes >= set(range(9))


def test_ac3_case_ids_unique_and_filesystem_safe():
    """AC3: all case_id values are distinct, non-empty, and match
    ^[a-z0-9_]+$."""
    ids = [c["case_id"] for c in _cases()]
    assert len(ids) == len(set(ids))
    for cid in ids:
        assert cid
        assert _CASE_ID_RE.match(cid), f"case_id {cid!r} is not filesystem-safe"


def test_ac4_each_case_has_full_schema_with_correct_types():
    """AC4: every case dict has every documented key with the correct
    Python type."""
    for case in _cases():
        for key, expected_type in _SCHEMA_KEYS_TYPES.items():
            assert key in case, f"case {case.get('case_id')!r} missing key {key!r}"
            assert isinstance(case[key], expected_type), (
                f"case {case.get('case_id')!r} key {key!r} has type "
                f"{type(case[key]).__name__}, expected {expected_type.__name__}"
            )


def test_ac5_failure_mode_name_matches_taxonomy():
    """AC5: case["failure_mode_name"] == FAILURE_MODE_NAMES[failure_mode]
    for every case."""
    for case in _cases():
        assert case["failure_mode_name"] == FAILURE_MODE_NAMES[case["failure_mode"]]


def test_ac6_expected_verdict_is_valid_severity_label():
    """AC6: expected_verdict is one of {"pass", "flagged-for-review",
    "fail"} for every case."""
    for case in _cases():
        assert case["expected_verdict"] in _VALID_VERDICTS


# =========================================================================== #
# B. Detection classification (AC7-AC9)
# =========================================================================== #


def test_ac7_detection_is_one_of_the_two_kinds():
    """AC7: detection is in {"pipeline", "reconstructed_record"} for every
    case."""
    for case in _cases():
        assert case["detection"] in _VALID_DETECTIONS


def test_ac8_modes_4_8_reconstructed_record_rest_pipeline():
    """AC8: every case with failure_mode in {4, 8} is reconstructed_record
    with a valid reconstruction technique; every case with failure_mode in
    {0, 1, 2, 3, 5, 6, 7} is pipeline with no reconstruction. Mode 1 moved
    into the pipeline set in item 120, which promoted a held-out per-label
    spline offset into the pipeline itself."""
    for case in _cases():
        mode = case["failure_mode"]
        if mode in _RECONSTRUCTED_MODES:
            assert case["detection"] == "reconstructed_record"
            assert case.get("reconstruction") in _VALID_RECONSTRUCTIONS
        elif mode in _PIPELINE_ONLY_MODES:
            assert case["detection"] == "pipeline"
            assert not case.get("reconstruction")
        else:
            raise AssertionError(f"unexpected failure_mode {mode!r}")


def test_ac9_reconstructed_record_fixtures_hide_mode_from_run_qc():
    """AC9: for each detection == "reconstructed_record" case, running the
    loaded seg through run_qc emits no finding whose rule_id is among that
    case's expected_rule_ids."""
    reconstructed = [c for c in _cases() if c["detection"] == "reconstructed_record"]
    assert reconstructed  # sanity: the partition is non-trivial
    for case in reconstructed:
        seg_img = _seg_nifti_from_case(case)
        findings = _findings(seg_img)
        expected_rule_ids = set(case["expected_rule_ids"])
        assert not any(f.rule_id in expected_rule_ids for f in findings)


# =========================================================================== #
# C. Fixtures load via the Stage 0 loader (AC10-AC12)
# =========================================================================== #


def test_ac10_every_referenced_fixture_file_exists():
    """AC10: every case's scan_fixture and seg_fixture, resolved under
    CORPUS_DIR, exist on disk."""
    for case in _cases():
        assert _resolve(case, "scan_fixture").exists(), case["case_id"]
        assert _resolve(case, "seg_fixture").exists(), case["case_id"]


def test_ac11_every_case_loads_via_load_case_with_nonempty_label_map():
    """AC11: load_case() succeeds for every case without raising, its
    scan/seg shapes match, and label_inventory is non-empty."""
    for case in _cases():
        loaded = _loaded_case(case)
        assert loaded.scan.data.shape == loaded.seg.data.shape, case["case_id"]
        assert len(loaded.label_inventory) > 0, case["case_id"]


def test_ac12_clean_control_fixture_is_the_default_clean_spine():
    """AC12: the clean_control case's loaded seg label_inventory keys are
    exactly {20, 21, 22, 23, 24}, each with build_clean_spine()'s voxel
    count for that label."""
    case = _case("clean_control")
    loaded = _loaded_case(case)
    clean = build_clean_spine()
    assert set(loaded.label_inventory.keys()) == {20, 21, 22, 23, 24}
    for label, count in loaded.label_inventory.items():
        assert count == clean.voxel_counts[label]


# =========================================================================== #
# D. Positive control & reproducibility (AC13-AC18)
# =========================================================================== #


def test_ac13_clean_control_declares_a_pass_verdict():
    """AC13: the manifest's failure_mode == 0 case has expected_verdict ==
    "pass", expected_rule_ids == [], expected_labels == [], and
    detection == "pipeline"."""
    case = _case("clean_control")
    assert case["failure_mode"] == 0
    assert case["expected_verdict"] == "pass"
    assert case["expected_rule_ids"] == []
    assert case["expected_labels"] == []
    assert case["detection"] == "pipeline"


def test_ac14_clean_control_fixture_actually_passes_the_real_pipeline():
    """AC14: run_qc(<loaded clean_control seg>, bundled_default_config())
    returns findings == () and verdict.overall == Severity.PASS."""
    case = _case("clean_control")
    seg_img = _seg_nifti_from_case(case)
    case_result, _block = run_qc(seg_img, bundled_default_config())
    assert case_result.findings == ()
    assert case_result.verdict.overall == Severity.PASS


def test_ac15_regeneration_reproduces_every_fixtures_content(tmp_path):
    """AC15: write_corpus(tmp) yields, for every case, a seg and scan whose
    loaded arrays and affines are np.array_equal to the committed
    fixtures."""
    dest = tmp_path / "regen"
    write_corpus(dest)
    fresh_manifest = load_manifest(dest / "manifest.json")

    for fresh_case in fresh_manifest["cases"]:
        fresh = load_case(dest / fresh_case["scan_fixture"], dest / fresh_case["seg_fixture"])
        committed = _loaded_case(_case(fresh_case["case_id"]))

        assert np.array_equal(fresh.seg.data, committed.seg.data), fresh_case["case_id"]
        assert np.array_equal(fresh.scan.data, committed.scan.data), fresh_case["case_id"]
        assert np.array_equal(fresh.seg.affine, committed.seg.affine), fresh_case["case_id"]
        assert np.array_equal(fresh.scan.affine, committed.scan.affine), fresh_case["case_id"]


def test_ac16_regeneration_is_byte_identical_across_runs_and_vs_committed(tmp_path):
    """AC16: two successive write_corpus calls into two fresh temp dirs
    produce byte-for-byte identical fixture files and manifest.json; each
    regenerated file is byte-for-byte identical to its committed
    counterpart."""
    dest1 = tmp_path / "run1"
    dest2 = tmp_path / "run2"
    manifest_path1 = write_corpus(dest1)
    manifest_path2 = write_corpus(dest2)

    assert manifest_path1.read_bytes() == manifest_path2.read_bytes()
    assert manifest_path1.read_bytes() == MANIFEST_PATH.read_bytes()

    fixtures1 = sorted((dest1 / FIXTURES_DIRNAME).glob("*.nii.gz"))
    fixtures2 = sorted((dest2 / FIXTURES_DIRNAME).glob("*.nii.gz"))
    assert [p.name for p in fixtures1] == [p.name for p in fixtures2]
    assert len(fixtures1) > 0

    for f1, f2 in zip(fixtures1, fixtures2):
        assert f1.read_bytes() == f2.read_bytes(), f1.name
        committed = CORPUS_DIR / FIXTURES_DIRNAME / f1.name
        assert f1.read_bytes() == committed.read_bytes(), f1.name


def test_ac17_manifest_expectations_equal_operators_expectation():
    """AC17: for every non-clean case, rebuilding it via
    get_perturbation(...)(...).apply(<base clean seg>, seed).expectation
    .to_dict() yields failure_mode / expected_rule_ids / expected_labels /
    expected_verdict equal to the manifest case's corresponding fields."""
    non_clean = [c for c in _cases() if c["failure_mode"] != 0]
    assert non_clean  # sanity
    for case in non_clean:
        base = build_clean_spine(**case["base"])
        operator_cls = get_perturbation(case["perturbation"])
        operator = operator_cls(**case["perturbation_params"])
        result = operator.apply(base.seg_img, case["seed"])
        expected = result.expectation.to_dict()

        assert expected["failure_mode"] == case["failure_mode"], case["case_id"]
        assert expected["expected_rule_ids"] == case["expected_rule_ids"], case["case_id"]
        assert expected["expected_labels"] == case["expected_labels"], case["case_id"]
        assert expected["expected_verdict"] == case["expected_verdict"], case["case_id"]


def test_ac18_the_one_command_regeneration_entry_point_runs(tmp_path):
    """AC18: segfacet.synth.corpus.main(["--out", tmp]) returns 0 and writes a
    manifest.json that load_manifest() parses to a dict with the same set of
    case_ids as the committed manifest."""
    out_dir = tmp_path / "regen_main"
    rc = main(["--out", str(out_dir)])
    assert rc == 0

    regenerated = load_manifest(out_dir / "manifest.json")
    committed_ids = {c["case_id"] for c in _cases()}
    regenerated_ids = {c["case_id"] for c in regenerated["cases"]}
    assert regenerated_ids == committed_ids


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_mode5_remove_level_case_level_labels_stay_schema_valid():
    """Adversarial: the case-level mode5_remove_level case (expected_labels
    == []) still loads without crashing and is schema-valid."""
    case = _case("mode5_remove_level")
    assert case["expected_labels"] == []
    assert case["failure_mode"] == 5
    loaded = _loaded_case(case)
    assert len(loaded.label_inventory) > 0


def test_adv_every_seg_fixture_path_is_distinct():
    """Adversarial: no two cases silently share a seg fixture path."""
    seg_paths = [c["seg_fixture"] for c in _cases()]
    assert len(seg_paths) == len(set(seg_paths))


def test_adv_all_cases_share_exactly_one_scan_fixture():
    """Adversarial: every case derives from the same base clean spine, so
    every case's scan_fixture is the same shared path."""
    scan_fixtures = {c["scan_fixture"] for c in _cases()}
    assert len(scan_fixtures) == 1


def test_adv_shared_base_scan_byte_identical_to_fresh_clean_spine_scan(tmp_path):
    """Adversarial: the committed shared base scan is byte-identical to a
    freshly written base build_clean_spine().scan_img (dedupe correctness)."""
    case = _case("clean_control")
    committed_path = _resolve(case, "scan_fixture")
    clean = build_clean_spine()
    fresh_path = tmp_path / "fresh_base_scan.nii.gz"
    nib.save(clean.scan_img, str(fresh_path))
    assert fresh_path.read_bytes() == committed_path.read_bytes()


def test_adv_write_corpus_idempotent_over_existing_directory(tmp_path):
    """Adversarial: re-running write_corpus over an already-populated
    directory reproduces identical bytes (idempotent regeneration)."""
    dest = tmp_path / "idempotent"
    write_corpus(dest)
    manifest_bytes_1 = (dest / "manifest.json").read_bytes()
    fixture_bytes_1 = {
        p.name: p.read_bytes() for p in (dest / FIXTURES_DIRNAME).glob("*.nii.gz")
    }

    write_corpus(dest)
    manifest_bytes_2 = (dest / "manifest.json").read_bytes()
    fixture_bytes_2 = {
        p.name: p.read_bytes() for p in (dest / FIXTURES_DIRNAME).glob("*.nii.gz")
    }

    assert manifest_bytes_1 == manifest_bytes_2
    assert fixture_bytes_1 == fixture_bytes_2


def test_adv_load_manifest_committed_and_relocated_write_produce_equal_cases(tmp_path):
    """Adversarial: load_manifest() on the committed file and on a fresh
    write_corpus output under a *different* directory produce equal cases
    lists -- the manifest is relocatable because fixture paths are
    manifest-relative."""
    dest = tmp_path / "relocated"
    write_corpus(dest)
    fresh = load_manifest(dest / "manifest.json")
    committed = load_manifest()
    assert fresh["cases"] == committed["cases"]


def test_adv_manifest_case_referencing_nonexistent_fixture_is_detected():
    """Adversarial: a case whose scan_fixture points at a file that does not
    exist on disk fails the AC10-style existence check -- proving a
    corrupted manifest entry would be caught rather than silently
    accepted."""
    bad_case = dict(_case("clean_control"))
    bad_case["scan_fixture"] = "fixtures/does_not_exist_at_all.nii.gz"
    assert not _resolve(bad_case, "scan_fixture").exists()


def test_adv_manifest_with_duplicate_case_ids_is_detected():
    """Adversarial: a manifest whose cases list has two entries sharing a
    case_id fails the AC3-style uniqueness check."""
    cases = list(_cases())
    duplicated = cases + [dict(cases[0])]
    ids = [c["case_id"] for c in duplicated]
    assert len(ids) != len(set(ids))


def test_adv_manifest_with_unknown_detection_value_is_detected():
    """Adversarial: a case carrying an unrecognised detection string fails
    the AC7-style domain check."""
    bad_case = dict(_case("clean_control"))
    bad_case["detection"] = "quantum_superposition"
    assert bad_case["detection"] not in _VALID_DETECTIONS
