"""Stage-8 acceptance suite for item 065 -- the roadmap's Stage-8 bar (image-
based / radiomics features, phase 2) proven end-to-end over item 058's
committed intensity corpus (``tests/corpus/intensity/``), driven through the
real pipeline entry point ``segfacet.pipeline.run_qc_with_intensity``. Completes
Stage 8.

Reproducing this suite's outcomes from the command line, once item 065's CLI
wiring is live (see ``tests/test_065_cli_intensity.py``)::

    segfacet run --scan <scan.nii.gz> --seg <seg.nii.gz> --out <dir> --intensity

The roadmap Stage-8 bar this suite closes: image-based (first-order
intensity) features are computed on real fixtures and fed into an
explainable rule; the clean ground-truth scan stays intensity-silent while
each of the three canonical implausible-intensity failure modes (metal /
soft-tissue / degenerate-uniform) is caught, and caught **only** on the
label it was painted onto (item 058's target label, L3 = integer 22) -- the
untouched levels stay plausible.

Covers Acceptance Criteria AC3-AC7, AC16:

- AC3: the clean_hu fixture is intensity-silent -- no ``intensity`` finding.
- AC4: the implausible_metal fixture fires an above-band ("too high")
  ``intensity`` finding on label 22.
- AC5: the implausible_soft_tissue fixture fires a below-band ("too low")
  ``intensity`` finding on label 22.
- AC6: the degenerate_uniform fixture fires a degenerate/uniform
  ``intensity`` finding on label 22.
- AC7: on every implausible variant, every ``intensity`` finding names
  exactly label 22 -- no other (untouched) label is flagged.
- AC16: this module itself, driving the committed corpus through the real
  pipeline, is the dedicated Stage-8 acceptance suite.

All tests are deterministic, CPU-only, and portable (no network, no
absolute paths, no wall clock).
"""

from __future__ import annotations

import nibabel as nib
import pytest

from segfacet.config import bundled_default_config
from segfacet.io import load_case
from segfacet.pipeline import run_qc_with_intensity
from segfacet.synth.intensity import INTENSITY_CORPUS_DIR, load_intensity_manifest

_TARGET_LABEL = 22

_MANIFEST = load_intensity_manifest()
_CASES = _MANIFEST["cases"]


def _case(case_id):
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _loaded_case_images(case, corpus_dir=INTENSITY_CORPUS_DIR):
    scan_path = corpus_dir / case["scan_fixture"]
    seg_path = corpus_dir / case["seg_fixture"]
    loaded = load_case(scan_path, seg_path)
    seg_img = nib.Nifti1Image(
        loaded.seg.data, loaded.seg.affine, dtype=loaded.seg.data.dtype
    )
    scan_img = nib.Nifti1Image(loaded.scan.data, loaded.scan.affine)
    return seg_img, scan_img


def _intensity_findings(case_result):
    return [f for f in case_result.findings if f.rule_id == "intensity"]


def _run(case_id):
    seg_img, scan_img = _loaded_case_images(_case(case_id))
    cfg = bundled_default_config()
    return run_qc_with_intensity(seg_img, scan_img, cfg)


# =========================================================================== #
# AC3: clean fixture is intensity-silent
# =========================================================================== #


def test_ac3_clean_hu_yields_no_intensity_finding():
    case_result, _features, _image_features, _rd, _ird = _run("clean_hu")
    assert _intensity_findings(case_result) == []


def test_ac3_clean_hu_image_features_available():
    _case_result, _features, image_features, _rd, _ird = _run("clean_hu")
    assert image_features["available"] is True
    assert image_features["per_label"]  # at least one label present


# =========================================================================== #
# AC4: metal variant fires "too high"
# =========================================================================== #


def test_ac4_implausible_metal_fires_intensity_finding_on_label_22():
    case_result, _features, _image_features, _rd, _ird = _run("implausible_metal")
    findings = _intensity_findings(case_result)
    assert len(findings) >= 1
    assert any(_TARGET_LABEL in f.labels for f in findings)


def test_ac4_implausible_metal_reason_denotes_too_high():
    case_result, _features, _image_features, _rd, _ird = _run("implausible_metal")
    findings = _intensity_findings(case_result)
    assert any("too high" in f.reason.lower() for f in findings)


# =========================================================================== #
# AC5: soft-tissue variant fires "too low"
# =========================================================================== #


def test_ac5_implausible_soft_tissue_fires_intensity_finding_on_label_22():
    case_result, _features, _image_features, _rd, _ird = _run(
        "implausible_soft_tissue"
    )
    findings = _intensity_findings(case_result)
    assert len(findings) >= 1
    assert any(_TARGET_LABEL in f.labels for f in findings)


def test_ac5_implausible_soft_tissue_reason_denotes_too_low():
    case_result, _features, _image_features, _rd, _ird = _run(
        "implausible_soft_tissue"
    )
    findings = _intensity_findings(case_result)
    assert any("too low" in f.reason.lower() for f in findings)


# =========================================================================== #
# AC6: degenerate variant fires "degenerate/uniform"
# =========================================================================== #


def test_ac6_degenerate_uniform_fires_intensity_finding_on_label_22():
    case_result, _features, _image_features, _rd, _ird = _run("degenerate_uniform")
    findings = _intensity_findings(case_result)
    assert len(findings) >= 1
    assert any(_TARGET_LABEL in f.labels for f in findings)


def test_ac6_degenerate_uniform_reason_denotes_degenerate_or_uniform():
    case_result, _features, _image_features, _rd, _ird = _run("degenerate_uniform")
    findings = _intensity_findings(case_result)
    assert any(
        "degenerate" in f.reason.lower() or "uniform" in f.reason.lower()
        for f in findings
    )


# =========================================================================== #
# AC7: only the target label is intensity-flagged
# =========================================================================== #


@pytest.mark.parametrize(
    "case_id", ["implausible_metal", "implausible_soft_tissue", "degenerate_uniform"]
)
def test_ac7_only_label_22_is_intensity_flagged(case_id):
    case_result, _features, _image_features, _rd, _ird = _run(case_id)
    findings = _intensity_findings(case_result)
    assert findings  # precondition: something fired for this variant
    flagged_labels = set()
    for f in findings:
        flagged_labels |= f.labels
    assert flagged_labels == {_TARGET_LABEL}


# =========================================================================== #
# AC16: Stage-8 acceptance suite present and green -- summary assertions
# =========================================================================== #


def test_ac16_stage8_bar_summary_over_the_full_committed_corpus():
    """A single consolidated check of the roadmap's Stage-8 acceptance bar:
    clean silent, every implausible variant caught on exactly label 22."""
    outcomes = {}
    for case in _CASES:
        case_result, _features, image_features, _rd, _ird = run_qc_with_intensity(
            *_loaded_case_images(case), bundled_default_config()
        )
        outcomes[case["case_id"]] = {
            "image_features_available": image_features["available"],
            "intensity_labels": frozenset().union(
                *[f.labels for f in _intensity_findings(case_result)]
            )
            if _intensity_findings(case_result)
            else frozenset(),
        }

    assert outcomes["clean_hu"]["image_features_available"] is True
    assert outcomes["clean_hu"]["intensity_labels"] == frozenset()

    for case_id in (
        "implausible_metal",
        "implausible_soft_tissue",
        "degenerate_uniform",
    ):
        assert outcomes[case_id]["image_features_available"] is True
        assert outcomes[case_id]["intensity_labels"] == frozenset({_TARGET_LABEL})


# =========================================================================== #
# Determinism (mirrors items 049/057's acceptance-suite determinism checks)
# =========================================================================== #


@pytest.mark.parametrize(
    "case_id",
    ["clean_hu", "implausible_metal", "implausible_soft_tissue", "degenerate_uniform"],
)
def test_determinism_intensity_findings_repeatable_across_two_runs(case_id):
    seg_img, scan_img = _loaded_case_images(_case(case_id))
    cfg = bundled_default_config()

    r1 = run_qc_with_intensity(seg_img, scan_img, cfg)
    r2 = run_qc_with_intensity(seg_img, scan_img, cfg)
    assert r1[0].findings == r2[0].findings
    assert r1[2] == r2[2]
