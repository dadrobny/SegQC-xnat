"""Stage-6 G3 acceptance suite for item 049 — clean ground truth sits inside
the reference ranges; size-distorting perturbations fall outside
(``src/segqc/pipeline.py::run_qc_with_reference`` over the committed
Stage-5 synthetic corpus, ``tests/corpus/``).

Building & evaluating against a reference (item 045's reproducible commands,
threaded through item 049's CLI/pipeline wiring):
    # Build a fresh artifact from a mounted VerSe-style cohort directory:
    segqc build-reference --cohort <dir> --out reference.json
    # Regenerate the bundled default from the fixed synthetic cohort:
    python -m segqc.reference.artifact
    # Evaluate a real case against a reference (reference mode, off by
    # default -- see item 049's Assumptions):
    segqc run --scan <nii> --seg <nii> --out <dir> --reference \
        [--reference-artifact <json>]

Covers Acceptance Criteria AC10-AC12:

- AC10: G3 positive control -- clean_control's reference_delta has every
  available label's out_of_range_features == [] and no reference_delta
  finding fires.
- AC11: G3 detection -- mode3_inject_islands and mode6_crop_at_border (both
  targeting label 22 = L3) yield a non-empty out_of_range_features for label
  22 and >= 1 reference_delta finding naming label 22.
- AC12: reference loading is covered end-to-end -- bundled_default_reference()
  and a fresh build_reference() both cover L1-L5.

Adversarial / edge-case scenarios included:
- Determinism: re-running mode3_inject_islands through run_qc_with_reference
  twice yields an equal reference_delta.
- A level absent from the reference yields available: false, not a crash
  (checked against an intentionally narrow reference).
- The clean_control case does not spuriously flag under a freshly built
  (not just bundled) reference either.
"""

from __future__ import annotations

import copy

import pytest

import segqc.synth  # noqa: F401 -- triggers self-registration of every operator
from segqc.config import bundled_default_config
from segqc.pipeline import run_qc_with_reference
from segqc.reference import build_reference, bundled_default_reference
from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.corpus import load_manifest
from segqc.synth.regression import loaded_seg_image

_MANIFEST = load_manifest()
_CASES = _MANIFEST["cases"]
_LEVELS_L1_L5 = ("L1", "L2", "L3", "L4", "L5")
_LABEL_L3 = 22


def _case(case_id):
    for c in _CASES:
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed manifest")


def _ref_findings(case_result):
    return [f for f in case_result.findings if f.rule_id == "reference_delta"]


# =========================================================================== #
# AC10: G3 positive control -- clean GT sits inside the reference ranges
# =========================================================================== #


def test_ac10_clean_control_has_no_out_of_range_features():
    case = _case("clean_control")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    cfg = bundled_default_config()

    _case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    for label_key, entry in reference_delta["per_label"].items():
        if entry["available"]:
            assert entry["out_of_range_features"] == [], (
                f"label {label_key} unexpectedly out-of-range in clean_control: "
                f"{entry['out_of_range_features']!r}"
            )


def test_ac10_clean_control_yields_no_reference_delta_finding():
    case = _case("clean_control")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    cfg = bundled_default_config()

    case_result, _features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    assert _ref_findings(case_result) == []


# =========================================================================== #
# AC11: G3 detection -- size-distorting perturbations fall outside the
# reference
# =========================================================================== #


@pytest.mark.parametrize("case_id", ["mode3_inject_islands", "mode6_crop_at_border"])
def test_ac11_size_distorting_perturbation_flags_label_22_out_of_range(case_id):
    case = _case(case_id)
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    cfg = bundled_default_config()

    _case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    entry = reference_delta["per_label"][str(_LABEL_L3)]
    assert entry["out_of_range_features"] != []


@pytest.mark.parametrize("case_id", ["mode3_inject_islands", "mode6_crop_at_border"])
def test_ac11_size_distorting_perturbation_fires_reference_delta_finding_on_label_22(
    case_id,
):
    case = _case(case_id)
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    cfg = bundled_default_config()

    case_result, _features_block, _reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    ref_findings = _ref_findings(case_result)
    assert len(ref_findings) >= 1
    assert any(_LABEL_L3 in f.labels for f in ref_findings)


# =========================================================================== #
# AC12: reference loading is covered end-to-end
# =========================================================================== #


def test_ac12_bundled_default_reference_covers_l1_to_l5():
    reference = bundled_default_reference()
    assert set(_LEVELS_L1_L5).issubset(set(reference.levels.keys()))


def test_ac12_fresh_build_reference_covers_l1_to_l5(tmp_path):
    import nibabel as nib

    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX

    cohort_dir = tmp_path / "cohort"
    cohort_dir.mkdir()
    for i, amplitude in enumerate((3.0, 5.0, 8.0)):
        spine = build_clean_spine(
            levels=_LEVELS_L1_L5,
            spacing=(1.0, 1.0, 0.8 + 0.2 * i),
            curve_amplitude_mm=amplitude,
        )
        nib.save(spine.seg_img, str(cohort_dir / f"sub-{i:03d}{DEFAULT_SEG_SUFFIX}"))

    reference = build_reference(cohort_dir, source="fresh-049", build_date="2026-07-11")
    assert set(_LEVELS_L1_L5).issubset(set(reference.levels.keys()))


def test_ac12_both_references_are_usable_by_run_qc_with_reference(tmp_path):
    import nibabel as nib

    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX

    case = _case("clean_control")
    seg_img = loaded_seg_image(case)
    cfg = bundled_default_config()

    bundled = bundled_default_reference()
    run_qc_with_reference(seg_img, cfg, bundled)  # must not raise

    cohort_dir = tmp_path / "cohort"
    cohort_dir.mkdir()
    for i, amplitude in enumerate((3.0, 5.0, 8.0)):
        spine = build_clean_spine(
            levels=_LEVELS_L1_L5,
            spacing=(1.0, 1.0, 0.8 + 0.2 * i),
            curve_amplitude_mm=amplitude,
        )
        nib.save(spine.seg_img, str(cohort_dir / f"sub-{i:03d}{DEFAULT_SEG_SUFFIX}"))
    fresh = build_reference(cohort_dir, source="fresh-049b", build_date="2026-07-11")
    run_qc_with_reference(seg_img, cfg, fresh)  # must not raise


# =========================================================================== #
# Determinism
# =========================================================================== #


def test_determinism_mode3_inject_islands_reference_delta_is_repeatable():
    case = _case("mode3_inject_islands")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    cfg = bundled_default_config()

    _r1, _b1, delta1 = run_qc_with_reference(seg_img, cfg, reference)
    _r2, _b2, delta2 = run_qc_with_reference(seg_img, cfg, reference)
    assert delta1 == delta2


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_level_absent_from_reference_yields_available_false_not_a_crash():
    case = _case("clean_control")
    seg_img = loaded_seg_image(case)
    cfg = bundled_default_config()

    # A reference built only over L1/L2 -- L3/L4/L5 (labels present in the
    # clean_control corpus fixture) are absent from this narrow reference.
    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX
    import nibabel as nib
    import tempfile
    import pathlib

    with tempfile.TemporaryDirectory() as tmp:
        cohort_dir = pathlib.Path(tmp)
        spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
        nib.save(spine.seg_img, str(cohort_dir / f"sub-000{DEFAULT_SEG_SUFFIX}"))
        narrow_reference = build_reference(
            cohort_dir, source="narrow-049", build_date="2026-07-11"
        )

    case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, narrow_reference
    )
    # Labels for levels the narrow reference never saw (L3/L4/L5) must be
    # marked unavailable, not crash the pipeline.
    unavailable_entries = [
        entry for entry in reference_delta["per_label"].values()
        if not entry["available"]
    ]
    assert unavailable_entries  # at least one label falls outside the narrow reference
    for entry in unavailable_entries:
        assert entry["out_of_range_features"] == []
    # No crash means we got here; case_result is well-formed.
    assert case_result is not None


def test_adv_clean_control_does_not_flag_under_a_freshly_built_reference():
    """The clean_control base spine (spacing 1.0mm, amplitude 6mm, L1-L5)
    sits interior to a freshly built reference's per-level bands too, not
    only the bundled default -- guarding against an accidental dependency on
    the specific bundled artifact's exact percentiles."""
    import nibabel as nib
    import tempfile
    import pathlib

    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX

    case = _case("clean_control")
    seg_img = loaded_seg_image(case)
    cfg = bundled_default_config()

    with tempfile.TemporaryDirectory() as tmp:
        cohort_dir = pathlib.Path(tmp)
        for i, (spacing_z, amplitude) in enumerate(
            [(0.8, 3.0), (1.0, 6.0), (1.2, 8.0)]
        ):
            spine = build_clean_spine(
                levels=_LEVELS_L1_L5,
                spacing=(1.0, 1.0, spacing_z),
                curve_amplitude_mm=amplitude,
            )
            nib.save(
                spine.seg_img, str(cohort_dir / f"sub-{i:03d}{DEFAULT_SEG_SUFFIX}")
            )
        fresh_reference = build_reference(
            cohort_dir, source="fresh-clean-049", build_date="2026-07-11"
        )

    case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, fresh_reference
    )
    for label_key, entry in reference_delta["per_label"].items():
        if entry["available"]:
            assert entry["out_of_range_features"] == [], (
                f"label {label_key} unexpectedly out-of-range under a "
                f"freshly built reference: {entry['out_of_range_features']!r}"
            )
    assert _ref_findings(case_result) == []


def test_adv_reference_delta_is_json_serialisable_and_non_mutating_for_perturbed_case():
    import json

    case = _case("mode6_crop_at_border")
    seg_img = loaded_seg_image(case)
    reference = bundled_default_reference()
    reference_before = copy.deepcopy(reference)
    cfg = bundled_default_config()

    _case_result, _features_block, reference_delta = run_qc_with_reference(
        seg_img, cfg, reference
    )
    json.dumps(reference_delta, allow_nan=False)  # must not raise
    assert reference == reference_before
