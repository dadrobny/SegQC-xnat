"""Tests for item 120 -- per-vertebra offset that separates, held out.

Item 119 changed **how the curve is fitted**; this item changes **how a
per-label offset is evaluated against it**, promoting a held-out (leave-one-
out, corrected for terminal-truncation and outlier cross-talk) measurement
from the test harness into the pipeline itself. After this item,
``stage3.per_label_offsets[].offset_mm`` is a level's closest-approach
distance to a curve *that level did not shape*, so a displaced vertebra
separates at roughly its true magnitude and ``MislabelRule`` fires through
plain ``run_qc``.

Covers Acceptance Criteria AC1-AC31:

- AC1/AC2: ``fit_centroid_spline``'s new ``u=`` and ``weights=`` keywords.
- AC3-AC9: ``compute_leave_one_out_spline_offsets`` -- public surface,
  domain preservation, held-out separation, dominant-outlier withholding,
  the < 4 levels fallback, determinism, and the clean-GT ceiling sweep.
- AC10/AC13: the default fit and the in-sample function keep their meaning.
- AC11/AC12: the pipeline call-site swap and the serialised record's shape.
- AC14-AC17: ``MislabelRule`` reads the direction components, tolerates
  their absence, keeps its threshold, and both corpus margins hold.
- AC18-AC24: the corpus's honest pipeline-detection promotion, measured
  through ``synth.regression`` and cohort metrics.
- AC25-AC30: goldens, the Stage-3 report golden, the bundled reference
  artifact and the generated catalogue are regenerated and reproducible.
- AC31: the RAS axis contract the direction components rely on.

Adversarial and edge cases:
- A perfectly straight spine -- every held-out offset near zero.
- Two levels displaced in opposite directions -- both separate.
- A displaced terminal level: not separable at 5 levels, separable at 8.
- Highly anisotropic spacing, including a 30 mm z-step.
- Exactly 4 levels -- the first count the held-out path runs on.
- One level removed from the front/middle/back of a 6-level sequence.
- Input immutability, frozen records, all-finite fields.
- ``weights`` containing 0.0, a negative value, a NaN, and a wrong length.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

from segfacet.config import bundled_default_config, default_config
from segfacet.features.centroids import LabelCentroid, compute_centroid
from segfacet.features.spline import SplineFit, evaluate_spline, fit_centroid_spline
from segfacet.features.spline_offset import (
    VertebralSplineOffset,
    compute_leave_one_out_spline_offsets,
    compute_spline_offsets,
)
import segfacet.heuristics.mislabel  # noqa: F401 -- triggers MislabelRule registration
from segfacet.heuristics import run_rules
from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import GOLDEN_DIR, check_case_golden, load_golden, write_goldens
from segfacet.synth.regression import (
    loaded_seg_image,
    pipeline_findings,
    pipeline_verdict_label,
    verify_case,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

_PRE_119_DIGESTS = json.loads(
    (_REPO_ROOT / "tests" / "corpus" / "119_pre_119_digests.json").read_text(encoding="utf-8")
)

# Pre-120 sha256 of the untouched real-GT reference artifact (AC29). Captured
# by the test-writer while this file was still in its pre-120 state -- this
# item never rebuilds it (real VerSe cohort, item 123's).
_PRE_120_REFERENCE_VERSE_V1_SHA256 = (
    "978c63d0367d9dd018f472aaa034740d42a04c47b95ccf0501cc128ad0638826"
)


# =========================================================================== #
# Helpers (mirror tests/test_017_centroid_spline_fit.py / test_119's style)
# =========================================================================== #


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _centroids_from_clean_spine(levels, spacing, curve_amplitude_mm=6.0) -> List[LabelCentroid]:
    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)
    return [compute_centroid(spine.seg_img, lbl) for lbl in spine.labels]


def _five_level_clean_spine() -> List[LabelCentroid]:
    return _centroids_from_clean_spine(("L1", "L2", "L3", "L4", "L5"), (1.0, 1.0, 1.0))


def _eight_level_thoracic_spine(spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=6.0) -> List[LabelCentroid]:
    return _centroids_from_clean_spine(
        ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"), spacing, curve_amplitude_mm
    )


def _displace_index(centroids, idx: int, magnitude_mm: float, axis: int = 0) -> LabelCentroid:
    c = centroids[idx]
    mm = list(c.centroid_mm)
    mm[axis] += magnitude_mm
    return dataclasses.replace(c, centroid_mm=tuple(mm))


def _coord_appears(msg: str, value: float) -> bool:
    """True if *value* shows up in *msg* under any plausible numeric
    formatting (mirrors test_119's ``_coord_appears``)."""
    candidates = {str(value), f"{value:g}", repr(value)}
    if float(value).is_integer():
        candidates.add(str(int(value)))
    return any(c in msg for c in candidates)


def _mode1_displace_case_and_centroids():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode1_displace")
    seg_img = loaded_seg_image(case)
    data = np.asanyarray(seg_img.dataobj)
    present = sorted(int(v) for v in np.unique(data) if v != 0)
    centroids = [compute_centroid(seg_img, lbl) for lbl in present]
    spacing = tuple(float(z) for z in seg_img.header.get_zooms()[:3])
    return case, centroids, spacing


def _mislabel_record(offsets: list, pairs: list = ()) -> dict:
    """A minimal build_features_block-shaped record (mirrors
    test_033_mislabel.py's ``_make_record``)."""
    return {
        "stage3": {
            "per_label_offsets": list(offsets),
            "monotonic_consistency": {
                "is_monotonic": len(pairs) == 0,
                "non_monotonic_pairs": [list(p) for p in pairs],
                "u_values": [],
            },
        },
    }


def _mislabel_findings(findings):
    return [f for f in findings if f.rule_id == "mislabel"]


# =========================================================================== #
# AC1: The fit accepts an explicit parameterisation
# =========================================================================== #


def test_ac1_explicit_u_matches_default_fit_bytes():
    centroids = _straight_spine(6)
    default_fit = fit_centroid_spline(centroids)
    explicit_fit = fit_centroid_spline(centroids, u=default_fit.u)

    assert tuple(float(v) for v in explicit_fit.u) == default_fit.u
    np.testing.assert_array_equal(explicit_fit.spline.t, default_fit.spline.t)
    np.testing.assert_array_equal(explicit_fit.spline.c, default_fit.spline.c)


def test_ac1_arbitrary_u_stored_verbatim():
    centroids = _straight_spine(5)
    custom_u = (0.0, 0.1, 0.4, 0.7, 1.0)
    fit = fit_centroid_spline(centroids, u=custom_u)
    assert fit.u == custom_u


# =========================================================================== #
# AC2: The fit accepts per-point weights, validated
# =========================================================================== #


def test_ac2_valid_weights_accepted():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids, weights=(1.0, 1.0, 1.0, 1.0, 1.0))
    assert isinstance(fit, SplineFit)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert np.all(np.isfinite(pts))


def test_ac2_wrong_length_weights_raise_readable_value_error():
    centroids = _straight_spine(5)
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids, weights=(1.0, 1.0, 1.0))
    msg = str(exc_info.value)
    assert msg.strip()
    assert _coord_appears(msg, 3) or _coord_appears(msg, 5)
    assert "Invalid inputs" not in msg


def test_ac2_zero_weight_raises_readable_value_error():
    centroids = _straight_spine(5)
    weights = [1.0, 1.0, 0.0, 1.0, 1.0]
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids, weights=weights)
    msg = str(exc_info.value)
    assert msg.strip()
    assert "Invalid inputs" not in msg


def test_ac2_negative_weight_raises_readable_value_error():
    centroids = _straight_spine(5)
    weights = [1.0, 1.0, -2.5, 1.0, 1.0]
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids, weights=weights)
    msg = str(exc_info.value)
    assert msg.strip()
    assert _coord_appears(msg, -2.5)
    assert "Invalid inputs" not in msg


def test_ac2_nan_weight_raises_readable_value_error():
    centroids = _straight_spine(5)
    weights = [1.0, float("nan"), 1.0, 1.0, 1.0]
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids, weights=weights)
    msg = str(exc_info.value)
    assert msg.strip()
    assert "Invalid inputs" not in msg


# =========================================================================== #
# AC3: A held-out per-label offset function is public
# =========================================================================== #


def test_ac3_function_exported_and_matches_in_sample_field_set():
    import segfacet.features.spline_offset as so_mod

    assert hasattr(so_mod, "compute_leave_one_out_spline_offsets")
    assert "compute_leave_one_out_spline_offsets" in so_mod.__all__

    centroids = _five_level_clean_spine()
    fit = fit_centroid_spline(centroids)
    in_sample = compute_spline_offsets(centroids, fit)
    held_out = compute_leave_one_out_spline_offsets(centroids)

    assert len(held_out) == len(centroids)
    assert [r.label for r in held_out] == [c.label for c in centroids]
    in_sample_fields = {f.name for f in dataclasses.fields(in_sample[0])}
    held_out_fields = {f.name for f in dataclasses.fields(held_out[0])}
    assert held_out_fields == in_sample_fields


# =========================================================================== #
# AC4: The held-out curve keeps the full parameter domain
# =========================================================================== #


def test_ac4_terminal_levels_measured_against_curve_interior():
    centroids = _five_level_clean_spine()
    records = compute_leave_one_out_spline_offsets(centroids)
    assert len(records) == 5
    for r in records:
        assert 0.0 <= r.closest_u <= 1.0
        assert r.closest_u != 0.0
        assert r.closest_u != 1.0


# =========================================================================== #
# AC5: A level cannot shape the curve it is judged against
# =========================================================================== #


def test_ac5_displaced_interior_level_separates_only_held_out():
    centroids = _five_level_clean_spine()
    idx = 2
    scenario = list(centroids)
    scenario[idx] = _displace_index(centroids, idx, 18.0, axis=0)

    held_out = compute_leave_one_out_spline_offsets(scenario)
    assert abs(held_out[idx].offset_mm - 18.0) <= 2.0

    fit_in_sample = fit_centroid_spline(scenario)
    in_sample = compute_spline_offsets(scenario, fit_in_sample)
    assert in_sample[idx].offset_mm < 2.0


# =========================================================================== #
# AC6: The dominant outlier is withheld too, chosen deterministically
# =========================================================================== #


def test_ac6_mode1_displace_dominant_outlier_exceeds_by_at_least_9mm():
    """Measured on the item's own branch: 18.719 mm vs 8.701 mm."""
    case, centroids, spacing = _mode1_displace_case_and_centroids()
    records = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing)
    by_label = {r.label: r.offset_mm for r in records}

    target = case["perturbation_params"]["target_label"]
    assert target in by_label

    sorted_offsets = sorted(by_label.values(), reverse=True)
    assert by_label[target] == sorted_offsets[0]
    assert by_label[target] - sorted_offsets[1] >= 9.0


def test_ac6_tie_break_rule_is_documented():
    import segfacet.features.spline_offset as so_mod

    doc = (so_mod.__doc__ or "") + (compute_leave_one_out_spline_offsets.__doc__ or "")
    assert "ascending" in doc.lower()
    assert "label" in doc.lower()


# =========================================================================== #
# AC7: Fewer than four levels falls back to the in-sample measurement
# =========================================================================== #


@pytest.mark.parametrize("n", [2, 3])
def test_ac7_fewer_than_four_levels_falls_back_to_in_sample(n):
    centroids = _straight_spine(n)
    fit = fit_centroid_spline(centroids)
    expected = compute_spline_offsets(centroids, fit)

    held_out = compute_leave_one_out_spline_offsets(centroids)
    assert held_out == expected


# =========================================================================== #
# AC8: The held-out offsets are deterministic
# =========================================================================== #


def test_ac8_two_calls_return_equal_lists():
    centroids = _five_level_clean_spine()
    first = compute_leave_one_out_spline_offsets(centroids)
    second = compute_leave_one_out_spline_offsets(centroids)
    assert first == second


# =========================================================================== #
# AC9: The clean-GT ceiling is bounded
# =========================================================================== #


def test_ac9_clean_gt_sweep_held_out_ceiling_bounded():
    """Over build_clean_spine at 2/3/5 levels x three spacings, the max
    held-out offset_mm is <= 2.0 mm (measured: 1.072494 mm at 5 levels x
    (0.8, 0.8, 1.0) -- a different quantity from item 119's in-sample
    pass-through, see the item's Assumptions)."""
    levels_pool = ("L1", "L2", "L3", "L4", "L5")
    level_counts = (2, 3, 5)
    spacings = ((1.0, 1.0, 1.0), (1.0, 1.0, 2.0), (0.8, 0.8, 1.0))

    overall_max = 0.0
    for count in level_counts:
        levels = levels_pool[:count]
        for spacing in spacings:
            centroids = _centroids_from_clean_spine(levels, spacing, curve_amplitude_mm=6.0)
            records = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing)
            for r in records:
                overall_max = max(overall_max, r.offset_mm)

    assert overall_max > 0.0
    assert overall_max <= 2.0, f"held-out ceiling {overall_max:.6f} mm exceeds 2.0 mm"


# =========================================================================== #
# AC10: The fit itself is unchanged
# =========================================================================== #


def test_ac10_default_fit_unaffected_by_new_keywords():
    import test_119_curve_formulation as t119

    for name, centroids in t119._ac7_fixtures().items():
        fit_bare = fit_centroid_spline(centroids)
        fit_explicit_none = fit_centroid_spline(centroids, u=None, weights=None)

        assert fit_bare.smoothing == fit_explicit_none.smoothing == float(len(centroids))
        assert fit_bare.degree == fit_explicit_none.degree
        assert fit_bare.n_points == fit_explicit_none.n_points == len(centroids)
        assert fit_bare.u == fit_explicit_none.u, name
        np.testing.assert_array_equal(fit_bare.spline.t, fit_explicit_none.spline.t)
        np.testing.assert_array_equal(fit_bare.spline.c, fit_explicit_none.spline.c)


# =========================================================================== #
# AC11: The pipeline evaluates offsets held-out
# =========================================================================== #


def test_ac11_pipeline_source_calls_leave_one_out_not_in_sample():
    source = (_REPO_ROOT / "src" / "segfacet" / "pipeline.py").read_text(encoding="utf-8")
    assert "compute_leave_one_out_spline_offsets" in source
    assert "compute_spline_offsets(" not in source


def test_ac11_extract_feature_record_offsets_match_leave_one_out_values():
    clean = build_clean_spine()
    config = bundled_default_config()
    record = extract_feature_record(clean.seg_img, config)

    centroids = [compute_centroid(clean.seg_img, lbl) for lbl in clean.labels]
    spacing = tuple(float(z) for z in clean.seg_img.header.get_zooms()[:3])
    expected = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing)

    got = record["stage3"]["per_label_offsets"]
    assert got, "extract_feature_record produced no per_label_offsets"
    assert len(got) == len(expected)
    for entry, exp in zip(got, expected):
        assert entry["label"] == exp.label
        assert entry["offset_mm"] == pytest.approx(exp.offset_mm, abs=1e-6)


# =========================================================================== #
# AC12: The serialised record's shape is unchanged
# =========================================================================== #


def test_ac12_catalogue_leaf_path_set_unchanged_from_pre_119(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    record = json.loads(json_dest.read_text(encoding="utf-8"))
    paths = sorted(entry["path"] for group in record["groups"] for entry in group["entries"])
    digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    assert digest == _PRE_119_DIGESTS["catalogue_leaf_path_set_sha256"], (
        "the catalogue's set of leaf feature paths changed -- item 120 must add "
        "and remove no feature path"
    )


def test_ac12_per_label_offsets_entry_field_set_exact():
    clean = build_clean_spine()
    record = extract_feature_record(clean.seg_img, bundled_default_config())
    entries = record["stage3"]["per_label_offsets"]
    assert entries, "expected at least one per_label_offsets entry"
    expected_fields = {
        "label",
        "level_name",
        "closest_u",
        "offset_mm",
        "offset_voxel",
        "dx_mm",
        "dy_mm",
        "dz_mm",
    }
    for entry in entries:
        assert set(entry.keys()) == expected_fields


# =========================================================================== #
# AC13: The in-sample function keeps its meaning
# =========================================================================== #


def test_ac13_in_sample_function_signature_and_semantics_unchanged():
    import test_018_per_vertebra_spline_offset as t018

    centroids = t018._straight_spine(6)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    assert len(offsets) == len(centroids)
    for o in offsets:
        assert o.offset_mm < 1.0


# =========================================================================== #
# AC14: mislabel reads the direction components
# =========================================================================== #


def _offset_entry_dir(label, level_name, dx, dy, dz):
    offset_mm = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
    return {
        "label": label,
        "level_name": level_name,
        "offset_mm": offset_mm,
        "dx_mm": dx,
        "dy_mm": dy,
        "dz_mm": dz,
    }


def test_ac14_dominant_axis_left_right():
    entry = _offset_entry_dir(20, "L1", dx=-20.0, dy=1.0, dz=1.0)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith("Vertebra misaligned from spinal curve:")
    assert "left-right" in findings[0].reason


def test_ac14_dominant_axis_anterior_posterior():
    entry = _offset_entry_dir(20, "L1", dx=1.0, dy=-20.0, dz=1.0)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "anterior-posterior" in findings[0].reason


def test_ac14_dominant_axis_cranio_caudal():
    entry = _offset_entry_dir(20, "L1", dx=1.0, dy=1.0, dz=20.0)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "cranio-caudal" in findings[0].reason


def test_ac14_tie_x_vs_y_prefers_left_right():
    entry = _offset_entry_dir(20, "L1", dx=15.0, dy=15.0, dz=1.0)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "left-right" in findings[0].reason


def test_ac14_tie_y_vs_z_prefers_anterior_posterior():
    entry = _offset_entry_dir(20, "L1", dx=1.0, dy=15.0, dz=15.0)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "anterior-posterior" in findings[0].reason


# =========================================================================== #
# AC15: mislabel tolerates a record with no direction components
# =========================================================================== #


def test_ac15_no_direction_components_omits_clause():
    entry = {"label": 20, "level_name": "L1", "offset_mm": 41.3}
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert findings[0].reason.startswith("Vertebra misaligned from spinal curve:")
    assert "predominantly" not in findings[0].reason


def test_ac15_partial_direction_components_omits_clause():
    entry = {
        "label": 20,
        "level_name": "L1",
        "offset_mm": 41.3,
        "dx_mm": 10.0,
        "dy_mm": 5.0,
        # dz_mm deliberately missing
    }
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "predominantly" not in findings[0].reason


def test_ac15_non_finite_direction_component_omits_clause_no_exception():
    entry = _offset_entry_dir(20, "L1", dx=10.0, dy=5.0, dz=float("nan"))
    entry["offset_mm"] = 41.3
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), default_config()))
    assert len(findings) == 1
    assert "predominantly" not in findings[0].reason


# =========================================================================== #
# AC16: The offset threshold is untouched
# =========================================================================== #


def test_ac16_default_max_offset_mm_still_15():
    assert _DEFAULT_MAX_OFFSET_MM == 15.0


# =========================================================================== #
# AC17: Both threshold margins hold and are asserted
# =========================================================================== #


def test_ac17_threshold_margins_hold_on_corpus():
    manifest = load_manifest()
    # These two cases are the item's own deliberate new mislabel firings
    # (AC18, AC23); the "must not raise" ceiling excludes them.
    firing_cases = {"mode1_displace", "mode6_crop_at_border"}

    ceiling = 0.0
    for case in manifest["cases"]:
        if case["case_id"] in firing_cases:
            continue
        golden = load_golden(case["case_id"])
        offsets = golden.get("features", {}).get("stage3", {}).get("per_label_offsets", [])
        for o in offsets:
            ceiling = max(ceiling, o["offset_mm"])
    assert ceiling < 15.0, f"non-firing ceiling {ceiling} mm reaches the threshold"

    mode1_golden = load_golden("mode1_displace")
    mode1_offsets = mode1_golden["features"]["stage3"]["per_label_offsets"]
    displaced = next(o for o in mode1_offsets if o["label"] == 22)
    assert displaced["offset_mm"] > 15.0, "displaced label 22 must exceed the threshold"


# =========================================================================== #
# AC18: mislabel fires through plain run_qc on mode 1, naming exactly {22}
# =========================================================================== #


def test_ac18_mislabel_fires_through_plain_run_qc_naming_label_22():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode1_displace")

    findings = _mislabel_findings(pipeline_findings(case))
    assert findings, "expected at least one mislabel finding via plain run_qc"
    assert any(f.reason.startswith("Vertebra misaligned from spinal curve:") for f in findings)

    union = set()
    for f in findings:
        union |= set(f.labels)
    assert union == {22}


# =========================================================================== #
# AC19: The clean control still fires nothing
# =========================================================================== #


def test_ac19_clean_control_fires_nothing():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "clean_control")
    assert pipeline_findings(case) == ()
    assert pipeline_verdict_label(case) == "pass"


# =========================================================================== #
# AC20: mode1_displace no longer needs a reconstruction
# =========================================================================== #


def test_ac20_mode1_manifest_entry_is_pipeline_detected():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode1_displace")
    assert case["detection"] == "pipeline"
    assert not case.get("reconstruction")

    detail = (case.get("detail") or "").lower()
    assert "not surfaced" not in detail
    assert "hidden from run_qc" not in detail
    assert "absorbs the displaced centroid" not in detail


# =========================================================================== #
# AC21: The mode-1 reconstruction workaround is retired
# =========================================================================== #


def test_ac21_leave_one_out_reconstruction_retired():
    from segfacet.synth import regression as regression_mod

    assert "leave_one_out_offset" not in regression_mod.RECONSTRUCTIONS
    assert not hasattr(regression_mod, "_recon_leave_one_out_offset")
    assert set(regression_mod.RECONSTRUCTIONS) == {
        "monotonic_true_spatial_order",
        "overlap_mask_stack",
    }


# =========================================================================== #
# AC22: Every corpus case still verifies
# =========================================================================== #


def test_ac22_every_corpus_case_verifies():
    manifest = load_manifest()
    assert len(manifest["cases"]) == 9
    for case in manifest["cases"]:
        assert verify_case(case), f"{case['case_id']} failed verify_case"


# =========================================================================== #
# AC23: The border-crop case's new mislabel finding is deliberate and pinned
# =========================================================================== #


def test_ac23_border_crop_case_gains_mislabel_finding_border_unchanged():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode6_crop_at_border")

    findings = pipeline_findings(case)
    mislabel = _mislabel_findings(findings)
    assert mislabel
    union = set()
    for f in mislabel:
        union |= set(f.labels)
    assert 22 in union

    assert pipeline_verdict_label(case) == "flagged-for-review"

    border_findings = [f for f in findings if f.rule_id == "border"]
    assert border_findings
    border_union = set()
    for f in border_findings:
        border_union |= set(f.labels)
    assert border_union == {22}

    golden = load_golden("mode6_crop_at_border")
    offsets = golden["features"]["stage3"]["per_label_offsets"]
    entry = next(o for o in offsets if o["label"] == 22)
    assert entry["offset_mm"] == pytest.approx(17.507, abs=0.05)


# =========================================================================== #
# AC24: The corpus's pipeline-detection count is 6 of 8
# =========================================================================== #


def _corpus_cohort_metrics():
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort
    from segfacet.eval.metrics import compute_cohort_metrics
    from segfacet.synth.perturbation import FAILURE_MODE_NAMES

    manifest_cases = load_manifest()["cases"]
    clean_case = next(c for c in manifest_cases if c["case_id"] == "clean_control")
    gt_img = loaded_seg_image(clean_case)

    eval_cases = []
    for case in manifest_cases:
        candidate_img = (
            gt_img if case["case_id"] == "clean_control" else loaded_seg_image(case)
        )
        eval_cases.append(
            EvaluationCase(case_id=case["case_id"], gt=gt_img, candidate=candidate_img, expected=case)
        )
    evaluation = evaluate_cohort(eval_cases, bundled_default_config())
    return compute_cohort_metrics(evaluation, failure_modes=FAILURE_MODE_NAMES)


def test_ac24_corpus_pipeline_detection_is_six_of_eight():
    metrics = _corpus_cohort_metrics()
    assert metrics.sensitivity == pytest.approx(6.0 / 8.0)

    expected_sensitivity = {1: 1.0, 2: 1.0, 3: 1.0, 4: 0.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 0.0}
    for mode, expected in expected_sensitivity.items():
        entry = next(m for m in metrics.per_mode if m.failure_mode == mode)
        assert entry.sensitivity == pytest.approx(expected), f"mode {mode}"


# =========================================================================== #
# AC25: The nine corpus goldens are regenerated and reproducible
# =========================================================================== #


def test_ac25_every_manifest_case_matches_committed_golden():
    manifest = load_manifest()
    for case in manifest["cases"]:
        assert check_case_golden(case), f"{case['case_id']} does not match its committed golden"


def test_ac25_write_goldens_into_two_dirs_is_byte_identical(tmp_path):
    dest1 = tmp_path / "goldens1"
    dest2 = tmp_path / "goldens2"
    write_goldens(dest1)
    write_goldens(dest2)

    files1 = sorted(p.name for p in dest1.glob("*.json"))
    files2 = sorted(p.name for p in dest2.glob("*.json"))
    assert files1, "write_goldens produced no files"
    assert files1 == files2
    for name in files1:
        assert (dest1 / name).read_bytes() == (dest2 / name).read_bytes()


# =========================================================================== #
# AC26: The regeneration moves no verdict except the item's own deliverable,
# and every real change lies under features.stage3 or findings/verdict
# =========================================================================== #


# Pre-120 committed (verdict, [(rule_id, labels), ...]) per case, captured
# while this file was still in its pre-120 state -- not by re-reading a file
# this item's step 9 rewrites.
_PRE_120_VERDICTS_AND_FINDINGS = {
    "clean_control": ("pass", []),
    "mode1_displace": ("pass", []),
    "mode2_fragment": ("flagged-for-review", [("fragmentation", [22])]),
    "mode3_inject_islands": ("flagged-for-review", [("fragmentation", [22])]),
    "mode4_relabel_swap": ("pass", []),
    "mode5_remove_level": ("flagged-for-review", [("coverage", [])]),
    "mode6_crop_at_border": ("flagged-for-review", [("border", [22])]),
    "mode7_sequence_break": ("flagged-for-review", [("sequence", [28])]),
    "mode8_force_overlap": ("pass", []),
}


def test_ac26_regeneration_moves_no_verdict_outside_mode1s_own_deliverable():
    manifest = load_manifest()
    assert set(c["case_id"] for c in manifest["cases"]) == set(_PRE_120_VERDICTS_AND_FINDINGS)

    for case in manifest["cases"]:
        case_id = case["case_id"]
        golden = load_golden(case_id)
        expected_verdict, _ = _PRE_120_VERDICTS_AND_FINDINGS[case_id]

        if case_id == "mode1_displace":
            # AC18: this item's literal deliverable -- the displaced level
            # now separates through plain run_qc, so this one case's verdict
            # moves pass -> flagged-for-review.
            assert golden["verdict"] == "flagged-for-review"
        else:
            assert golden["verdict"] == expected_verdict, f"{case_id}: verdict moved"


def test_ac26_changes_confined_to_stage3_and_findings_and_verdict(tmp_path):
    fresh_dir = tmp_path / "fresh"
    write_goldens(fresh_dir)

    for case_path in GOLDEN_DIR.glob("*.json"):
        case_id = case_path.stem
        committed = json.loads(case_path.read_text(encoding="utf-8"))
        fresh = json.loads((fresh_dir / case_path.name).read_text(encoding="utf-8"))

        for key in committed:
            if key in ("features", "findings", "verdict"):
                continue
            assert fresh.get(key) == committed.get(key), f"{case_id}: {key} changed"

        committed_features = committed.get("features", {})
        fresh_features = fresh.get("features", {})
        assert set(fresh_features) == set(committed_features), f"{case_id}: feature block set changed"
        for key in committed_features:
            if key == "stage3":
                continue
            assert fresh_features.get(key) == committed_features.get(key), (
                f"{case_id}: features.{key} changed"
            )


# =========================================================================== #
# AC27: The Stage-3 report golden is regenerated
# =========================================================================== #


def test_ac27_stage3_report_golden_matches_test_022_output():
    import test_022_stage3_serialisation as t022

    centroids = t022._straight_spine(5)
    block = t022._full_block_for_spine(centroids)
    produced = t022.serialize_report_json(
        t022._empty_verdict(), "golden-case-022", t022._config(), features=block
    )
    committed = t022.GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == committed


# =========================================================================== #
# AC28: The bundled default reference artifact is rebuilt
# =========================================================================== #


def test_ac28_reference_default_matches_fresh_build(tmp_path):
    from segfacet.reference.artifact import build_and_write_default, default_artifact_path

    dest = tmp_path / "reference_default.json"
    build_and_write_default(dest)
    assert dest.read_bytes() == default_artifact_path().read_bytes()


def test_ac28_spline_offset_mm_distribution_has_nonzero_mean():
    from segfacet.reference.artifact import default_artifact_path

    record = json.loads(default_artifact_path().read_text(encoding="utf-8"))
    levels = record.get("levels", {})
    assert levels, "expected at least one level in the default reference artifact"

    found_nonzero = False
    for level_block in levels.values():
        stats = (
            level_block.get("all", {}).get("feature_stats", {}).get("spline_offset_mm")
        )
        if not stats:
            continue
        mean = stats.get("mean")
        assert mean is not None
        if mean != 0.0:
            found_nonzero = True
    assert found_nonzero, (
        "expected at least one level's spline_offset_mm mean to be non-zero "
        "under the held-out estimator"
    )


# =========================================================================== #
# AC29: reference_verse_v1.json is untouched
# =========================================================================== #


def test_ac29_reference_verse_v1_unchanged():
    path = _REPO_ROOT / "src" / "segfacet" / "reference" / "reference_verse_v1.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _PRE_120_REFERENCE_VERSE_V1_SHA256, (
        "reference_verse_v1.json changed -- its rebuild needs the real VerSe "
        "cohort and is item 123's, not item 120's"
    )


# =========================================================================== #
# AC30: The generated catalogue is regenerated and its prose is true
# =========================================================================== #


def test_ac30_catalogue_regeneration_matches_committed_artifacts(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()


def test_ac30_spline_offset_group_note_describes_held_out_evaluation_and_ras():
    from segfacet.feature_docs import GROUP_INTROS

    note = GROUP_INTROS["Spline Offset"]
    assert "held-out" in note.lower() or "held out" in note.lower()
    assert "R" in note and "A" in note and "S" in note


# =========================================================================== #
# AC31: The RAS contract is stated where the feature is defined
# =========================================================================== #


def test_ac31_io_target_axcodes_still_ras():
    import segfacet.io as io_mod

    assert io_mod._TARGET_AXCODES == ("R", "A", "S")


def test_ac31_spline_offset_module_docstring_states_ras_contract():
    import segfacet.features.spline_offset as so_mod

    doc = so_mod.__doc__ or ""
    assert "load_volume" in doc
    assert "centroid_voxel" in doc
    assert "spacing" in doc
    assert "R" in doc and "A" in doc and "S" in doc


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_straight_spine_all_held_out_offsets_near_zero():
    centroids = _straight_spine(6)
    records = compute_leave_one_out_spline_offsets(centroids)
    for r in records:
        assert r.offset_mm < 1.0


def test_adv_two_opposite_displacements_both_separate():
    centroids = _eight_level_thoracic_spine()
    idx_a, idx_b = 2, 5
    scenario = list(centroids)
    scenario[idx_a] = _displace_index(centroids, idx_a, 15.0, axis=0)
    scenario[idx_b] = _displace_index(centroids, idx_b, -15.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario)
    others_max = max(
        r.offset_mm for i, r in enumerate(records) if i not in (idx_a, idx_b)
    )
    assert records[idx_a].offset_mm > others_max
    assert records[idx_a].offset_mm > 5.0
    assert records[idx_b].offset_mm > others_max
    assert records[idx_b].offset_mm > 5.0


def test_adv_terminal_displacement_five_levels_not_separable():
    """A documented limitation, not a defect (see the spec's Assumptions):
    withholding a terminal level and the dominant outlier leaves only three
    points to constrain a cubic at five levels."""
    centroids = _five_level_clean_spine()
    scenario = list(centroids)
    scenario[0] = _displace_index(centroids, 0, 18.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario)
    assert records[0].offset_mm < 5.0


def test_adv_terminal_displacement_eight_levels_is_separable():
    centroids = _eight_level_thoracic_spine()
    scenario = list(centroids)
    scenario[0] = _displace_index(centroids, 0, 18.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario)
    assert records[0].offset_mm > 10.0


def test_adv_anisotropic_spacing_offset_voxel_conversion_correct():
    spacing = (0.8, 0.8, 1.0)
    centroids = _centroids_from_clean_spine(("L1", "L2", "L3", "L4", "L5"), spacing)
    records = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing)
    for r in records:
        expected_voxel = math.sqrt(
            (r.dx_mm / spacing[0]) ** 2 + (r.dy_mm / spacing[1]) ** 2 + (r.dz_mm / spacing[2]) ** 2
        )
        assert r.offset_voxel == pytest.approx(expected_voxel, rel=1e-6)


def test_adv_30mm_z_step_ranking_unchanged():
    spacing = (0.5, 0.5, 30.0)
    centroids = _eight_level_thoracic_spine(spacing=spacing)
    idx = 3
    scenario = list(centroids)
    scenario[idx] = _displace_index(centroids, idx, 20.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario, spacing_mm=spacing)
    assert records[idx].offset_mm == max(r.offset_mm for r in records)
    for r in records:
        assert math.isfinite(r.offset_voxel)


def test_adv_exactly_four_levels_runs_held_out_path_finite():
    centroids = _straight_spine(4)
    records = compute_leave_one_out_spline_offsets(centroids)
    assert len(records) == 4
    for r in records:
        assert math.isfinite(r.offset_mm)


@pytest.mark.parametrize("remove_index_name", ["front", "middle", "back"])
def test_adv_one_level_removed_from_six_level_sequence(remove_index_name):
    full = _straight_spine(6)
    index = {"front": 0, "middle": 3, "back": 5}[remove_index_name]
    remaining = full[:index] + full[index + 1 :]

    records = compute_leave_one_out_spline_offsets(remaining)
    assert len(records) == len(remaining)
    for r in records:
        assert math.isfinite(r.offset_mm)


def test_adv_input_not_mutated_records_frozen_all_fields_finite():
    centroids = _five_level_clean_spine()
    original = list(centroids)

    records = compute_leave_one_out_spline_offsets(centroids)
    assert centroids == original

    with pytest.raises(Exception):
        records[0].offset_mm = 0.0  # type: ignore[misc]

    for r in records:
        assert isinstance(r, VertebralSplineOffset)
        assert math.isfinite(r.offset_mm)
        assert math.isfinite(r.offset_voxel)
        assert math.isfinite(r.closest_u)
        assert math.isfinite(r.dx_mm)
        assert math.isfinite(r.dy_mm)
        assert math.isfinite(r.dz_mm)
