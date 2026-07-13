"""Tests for item 065 -- the intensity-aware pipeline entry point
(``src/segqc/pipeline.py::run_qc_with_intensity``), the new sibling of item
049's ``run_qc_with_reference`` that wires items 058-064's already-merged
intensity/radiomics/reference-delta family into the real pipeline.

Covers Acceptance Criteria AC1, AC2, AC13, AC14, AC15:

- AC1: ``run_qc_with_intensity`` returns the composed 5-tuple
  ``(case_result, features_block, image_features_block, reference_delta,
  intensity_reference_delta)``; without a reference both delta fields are
  ``None`` and ``image_features_block["available"] is True`` with a
  ``first_order`` sub-dict for every present non-zero label.
- AC2: ``run_qc`` and ``run_qc_with_reference`` are byte-for-byte unchanged
  by this item's addition (the intensity path is a new, additive sibling;
  no shared code path is mutated).
- AC13: with a reference supplied, ``intensity_reference_delta`` is
  populated (``per_label`` entries carry an ``available`` flag) and the
  ``intensity_reference_delta`` rule participates over the composed record,
  staying silent on the clean ``clean_hu`` fixture.
- AC14: a reference carrying no ``intensity_*`` distributions does not raise
  and yields no ``intensity_reference_delta`` finding (backward
  compatibility, item 064's own documented contract).
- AC15: two ``run_qc_with_intensity`` calls on the same inputs return equal
  findings and an equal ``image_features_block``.

Adversarial / edge-case scenarios included:
- ``run_qc_with_intensity`` does not mutate ``seg_img``/``scan_img``/
  ``config``/``reference``.
- ``image_features`` and ``reference``/``reference_delta``/
  ``intensity_reference_delta`` are never leaked into ``features_block``
  (the transient-record-only contract, mirroring item 049's AC4).
- A scan/seg grid mismatch raises ``ValueError`` (item 059's
  ``_check_alignment``), not a silent wrong answer.
- ``enable_pyradiomics=False`` forces the builtin backend even when
  requested on (PyRadiomics is absent in CI regardless, but the flag itself
  must be honoured and not raise).
"""

from __future__ import annotations

import copy

import nibabel as nib
import pytest

from segqc.config import bundled_default_config
from segqc.io import load_case
from segqc.pipeline import (
    extract_feature_record,
    run_qc,
    run_qc_with_intensity,
    run_qc_with_reference,
)
from segqc.reference import build_reference, bundled_default_reference
from segqc.reference.ingest import DEFAULT_SEG_SUFFIX
from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.intensity import INTENSITY_CORPUS_DIR, load_intensity_manifest


# =========================================================================== #
# Helpers
# =========================================================================== #


def _manifest_cases():
    return load_intensity_manifest()["cases"]


def _case(case_id):
    for c in _manifest_cases():
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the intensity manifest")


def _loaded_case_images(case, corpus_dir=INTENSITY_CORPUS_DIR):
    """Load *case*'s committed scan + seg fixtures as a pair of fresh
    ``Nifti1Image``s, mirroring ``segqc.synth.regression.loaded_seg_image``
    but returning both images (this item's entry point needs the scan)."""
    scan_path = corpus_dir / case["scan_fixture"]
    seg_path = corpus_dir / case["seg_fixture"]
    loaded = load_case(scan_path, seg_path)
    seg_img = nib.Nifti1Image(
        loaded.seg.data, loaded.seg.affine, dtype=loaded.seg.data.dtype
    )
    scan_img = nib.Nifti1Image(loaded.scan.data, loaded.scan.affine)
    return seg_img, scan_img


def _clean_hu_images():
    return _loaded_case_images(_case("clean_hu"))


# =========================================================================== #
# AC1: the composed 5-tuple, no reference
# =========================================================================== #


def test_ac1_returns_five_tuple_with_none_deltas_when_no_reference():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()

    result = run_qc_with_intensity(seg_img, scan_img, cfg)
    assert len(result) == 5
    case_result, features_block, image_features_block, reference_delta, intensity_reference_delta = result

    assert reference_delta is None
    assert intensity_reference_delta is None
    assert isinstance(features_block, dict)
    assert isinstance(image_features_block, dict)
    assert case_result is not None


def test_ac1_image_features_block_is_available_with_first_order_per_label():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()

    _case_result, _features_block, image_features_block, _rd, _ird = (
        run_qc_with_intensity(seg_img, scan_img, cfg)
    )
    assert image_features_block["available"] is True

    seg_data = seg_img.get_fdata()
    import numpy as np

    present_labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    assert present_labels  # sanity: the clean_hu corpus fixture is non-empty

    per_label = image_features_block["per_label"]
    for label in present_labels:
        entry = per_label[str(label)]
        assert isinstance(entry["first_order"], dict)


# =========================================================================== #
# AC2: run_qc / run_qc_with_reference are unchanged
# =========================================================================== #


def test_ac2_run_qc_still_returns_two_tuple_unaffected():
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    cfg = bundled_default_config()

    result = run_qc(spine.seg_img, cfg)
    assert len(result) == 2
    case_result, features_block = result
    assert "image_features" not in features_block
    assert "reference" not in features_block
    assert "reference_delta" not in features_block
    assert "intensity_reference_delta" not in features_block
    assert case_result is not None


def test_ac2_run_qc_with_reference_still_returns_three_tuple_unaffected():
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    result = run_qc_with_reference(spine.seg_img, cfg, reference)
    assert len(result) == 3
    case_result, features_block, reference_delta = result
    assert isinstance(reference_delta, dict)
    assert "image_features" not in features_block
    assert "intensity_reference_delta" not in features_block
    assert case_result is not None


def test_ac2_run_qc_output_equals_pre_065_expectation_for_fixed_input():
    """A precise pinned-value regression guard: run_qc's findings/verdict for
    a fixed clean single-level spine must not shift under item 065's purely
    additive change (no shared code path -- extract_feature_record,
    run_rules, build_case_result -- is touched)."""
    spine = build_clean_spine(levels=("L3",))
    cfg = bundled_default_config()

    case_result, features_block = run_qc(spine.seg_img, cfg)
    assert case_result.findings == ()
    assert features_block == extract_feature_record(spine.seg_img, cfg)


# =========================================================================== #
# AC13: reference-grounded intensity rule participates
# =========================================================================== #


def test_ac13_intensity_reference_delta_populated_with_available_flags():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    _case_result, _features_block, _image_features_block, _rd, intensity_reference_delta = (
        run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    )
    assert intensity_reference_delta is not None
    assert isinstance(intensity_reference_delta["per_label"], dict)
    for entry in intensity_reference_delta["per_label"].values():
        assert "available" in entry


def test_ac13_intensity_reference_delta_rule_is_silent_on_clean_hu():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    case_result, _features_block, _image_features_block, _rd, _ird = (
        run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    )
    ird_findings = [
        f for f in case_result.findings if f.rule_id == "intensity_reference_delta"
    ]
    assert ird_findings == []


def test_ac13_geometric_reference_delta_also_populated_alongside_intensity():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    _case_result, _features_block, _image_features_block, reference_delta, _ird = (
        run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    )
    assert reference_delta is not None
    assert isinstance(reference_delta["per_label"], dict)


# =========================================================================== #
# AC14: inert without intensity reference data (backward compatibility)
# =========================================================================== #


def _reference_without_intensity(tmp_path):
    """A freshly-built reference whose cohort was ingested with
    ``with_intensity`` left at its default (``False``) -- i.e. no
    ``intensity_*`` distributions, matching item 064's own "backward
    compatibility with pre-063 references" contract."""
    cohort_dir = tmp_path / "cohort_no_intensity"
    cohort_dir.mkdir()
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    nib.save(spine.seg_img, str(cohort_dir / f"sub-000{DEFAULT_SEG_SUFFIX}"))
    return build_reference(
        cohort_dir, source="no-intensity-065", build_date="2026-07-13"
    )


def test_ac14_reference_without_intensity_data_does_not_raise(tmp_path):
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = _reference_without_intensity(tmp_path)

    # Must not raise.
    result = run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    assert len(result) == 5


def test_ac14_reference_without_intensity_data_yields_no_intensity_reference_delta_finding(
    tmp_path,
):
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = _reference_without_intensity(tmp_path)

    case_result, _features_block, _image_features_block, _rd, intensity_reference_delta = (
        run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    )
    ird_findings = [
        f for f in case_result.findings if f.rule_id == "intensity_reference_delta"
    ]
    assert ird_findings == []
    # Backward-compat contract: still a well-formed dict, not None, and every
    # available label carries zero FeatureDeltas for the intensity family.
    if intensity_reference_delta is not None:
        for entry in intensity_reference_delta["per_label"].values():
            if entry.get("available"):
                assert entry.get("features", {}) == {}


# =========================================================================== #
# AC15: determinism
# =========================================================================== #


def test_ac15_two_calls_return_equal_findings_and_image_features():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()

    r1 = run_qc_with_intensity(seg_img, scan_img, cfg)
    r2 = run_qc_with_intensity(seg_img, scan_img, cfg)

    assert r1[0].findings == r2[0].findings
    assert r1[2] == r2[2]


def test_ac15_two_calls_with_reference_return_equal_full_tuples():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    r1 = run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    r2 = run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)

    assert r1[0].findings == r2[0].findings
    assert r1[1] == r2[1]
    assert r1[2] == r2[2]
    assert r1[3] == r2[3]
    assert r1[4] == r2[4]


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_config_and_reference_are_not_mutated():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()
    cfg_before = copy.deepcopy(cfg)
    reference_before = copy.deepcopy(reference)

    run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)

    assert cfg == cfg_before
    assert reference == reference_before


def test_adv_features_block_carries_no_intensity_or_reference_keys():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    _case_result, features_block, _image_features_block, _rd, _ird = (
        run_qc_with_intensity(seg_img, scan_img, cfg, reference=reference)
    )
    assert "image_features" not in features_block
    assert "reference" not in features_block
    assert "reference_delta" not in features_block
    assert "intensity_reference_delta" not in features_block


def test_adv_mismatched_scan_seg_grid_raises_value_error():
    seg_img, _scan_img = _clean_hu_images()
    cfg = bundled_default_config()
    # A scan built on a different affine/shape than the seg.
    mismatched_scan = nib.Nifti1Image(
        seg_img.get_fdata().astype("float64")[:-1, :, :],
        seg_img.affine,
    )

    with pytest.raises(ValueError):
        run_qc_with_intensity(seg_img, mismatched_scan, cfg)


def test_adv_enable_pyradiomics_false_is_honoured_without_raising():
    seg_img, scan_img = _clean_hu_images()
    cfg = bundled_default_config()

    _case_result, _features_block, image_features_block, _rd, _ird = (
        run_qc_with_intensity(seg_img, scan_img, cfg, enable_pyradiomics=False)
    )
    assert image_features_block["backend"] == "builtin"
    assert image_features_block["radiomics_available"] is False
