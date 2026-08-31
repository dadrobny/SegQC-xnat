"""Tests for item 129 -- coincident centroids in the pipeline, and the
4-level held-out boundary.

Two small-centroid-count defects in the spline-offset layer, sharing a
surface (``features/spline.py`` / ``features/spline_offset.py`` and the
Stage-3 branch of ``pipeline.py``):

- **D4**: a label map with two centroids sharing an exact mm-coordinate used
  to make ``extract_feature_record`` raise straight through
  ``fit_centroid_spline``'s ``ValueError``, losing every Stage 1/2 feature
  along with it. This item degrades gracefully instead: the Stage 3 block is
  omitted and the cause is recorded under ``features["stage3_unavailable"]``.
- **D5**: ``compute_leave_one_out_spline_offsets``'s held-out path claimed to
  activate at 4 levels, but a 4-point cubic (``k=3``) interpolates all four
  points regardless of the weights, so the "held-out" curve was the in-sample
  curve. ``_MIN_LEVELS_FOR_HELD_OUT`` moves from 4 to 5 -- an honesty fix with
  no numeric consequence (the two paths already agreed to ~1e-13 mm at
  n=4) -- and the four-level blind spot is asserted, not only documented.

Covers Acceptance Criteria AC1-AC34 (see the item spec's Acceptance Criteria
section for the exact wording each test below is named for).

Adversarial and edge cases:
- Three mutually coincident labels (degrades once, naming the first pair).
- A coincident pair among five labels with three well-separated others.
- A coincident pair where one label is a single voxel.
- Near-coincident (1e-9 mm) exercised at both the helper and the pipeline
  level -- the complement of AC3/AC9.
- The degraded record round-tripping through ``serialize_report`` -> JSON.
- ``segfacet run`` with ``--no-reference`` and with the default reference.
- The n=4 blind spot with the displaced level at each of the four positions.
- n=5 with a terminal level displaced (still takes the held-out path).
- Determinism of the held-out computation at n=4.

Two existing modules are touched only as their own reconciliation requires:
``tests/test_120_leave_one_out_offset.py`` (AC24: the fallback
parametrisation extends to 4) and ``tests/test_122_signed_curvature.py``
(AC19: the mis-named near-coincident fixture is renamed).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from pathlib import Path
from typing import List, Tuple

import jsonschema
import numpy as np
import pytest

from segfacet.cli import main
from segfacet.config import bundled_default_config, default_config_path
from segfacet.features.centroids import LabelCentroid, compute_centroid
from segfacet.features.spline import fit_centroid_spline
from segfacet.features.spline_offset import (
    compute_leave_one_out_spline_offsets,
    compute_spline_offsets,
)
import segfacet.heuristics.mislabel as mislabel_mod  # noqa: F401 -- registration + AC32
from segfacet.human_report import render_human_report
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.report import _SCHEMA, serialize_report
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image
from segfacet.verdict import Verdict

from synthetic import make_labelmap, make_scan, write_nifti

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TESTS_DIR = Path(__file__).resolve().parent

# =========================================================================== #
# Fixture builders
# =========================================================================== #

_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    return [
        _centroid(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _displace_index(centroids, idx: int, magnitude_mm: float, axis: int = 0) -> LabelCentroid:
    c = centroids[idx]
    mm = list(c.centroid_mm)
    mm[axis] += magnitude_mm
    return dataclasses.replace(c, centroid_mm=tuple(mm))


def _coord_appears(msg: str, value: float) -> bool:
    """True if *value* shows up in *msg* under any plausible numeric
    formatting (mirrors test_119/test_120's ``_coord_appears``)."""
    candidates = {str(value), f"{value:g}", repr(value)}
    if float(value).is_integer():
        candidates.add(str(int(value)))
    return any(c in msg for c in candidates)


def _coincident_label_map():
    """The item spec's reference realisation: label 21 (L2) as a hollow
    shell, label 22 (L3) as a concentric core -- both boxes are centred on
    the same point, so both centroids resolve to an exact shared
    mm-coordinate ((9.5, 9.5, 19.5) mm, measured 2026-08-31) regardless of
    the voxel-centre convention used to compute it."""
    blocks = {
        21: ((5, 15), (5, 15), (10, 30)),
        22: ((8, 12), (8, 12), (17, 23)),
    }
    return make_labelmap(shape=(20, 20, 40), blocks=blocks, spacing=(1.0, 1.0, 1.0))


def _triple_coincident_label_map():
    """Three concentric, centre-sharing boxes: labels 21 (L2), 22 (L3), 23
    (L4) all resolve to the same centroid."""
    blocks = {
        21: ((5, 15), (5, 15), (10, 30)),
        22: ((8, 12), (8, 12), (17, 23)),
        23: ((9, 11), (9, 11), (19, 21)),
    }
    return make_labelmap(shape=(20, 20, 40), blocks=blocks, spacing=(1.0, 1.0, 1.0))


def _five_label_with_one_coincident_pair():
    """Labels 1/2/3 well separated in a disjoint corner of the volume; 21/22
    concentric as in :func:`_coincident_label_map`."""
    blocks = {
        1: ((1, 3), (1, 3), (1, 3)),
        2: ((1, 3), (1, 3), (5, 7)),
        3: ((1, 3), (1, 3), (34, 36)),
        21: ((5, 15), (5, 15), (10, 30)),
        22: ((8, 12), (8, 12), (17, 23)),
    }
    return make_labelmap(shape=(20, 20, 40), blocks=blocks, spacing=(1.0, 1.0, 1.0))


def _single_voxel_coincident_label_map():
    """Label 30 (S3) is a 3x3x3 box centred on (10.5, 10.5, 20.5) mm; label
    31 (S4) punches through its single centre voxel (applied second, so it
    overwrites), leaving a single-voxel label whose centroid coincides with
    the hollowed-out box's centroid (both centred on the same point)."""
    blocks = {
        30: ((9, 12), (9, 12), (19, 22)),
        31: ((10, 11), (10, 11), (20, 21)),
    }
    return make_labelmap(shape=(20, 20, 40), blocks=blocks, spacing=(1.0, 1.0, 1.0))


def _near_coincident_pipeline_map():
    """Two adjacent single-voxel labels, one voxel apart in index space, at
    an x-spacing of 1e-9 mm -- their mm-coordinates differ by ~1e-9 mm:
    near-coincident, never exactly equal."""
    blocks = {
        1: ((0, 1), (0, 4), (0, 4)),
        2: ((1, 2), (0, 4), (0, 4)),
    }
    return make_labelmap(shape=(4, 4, 4), blocks=blocks, spacing=(1e-9, 1.0, 1.0))


def _one_label_map():
    return make_labelmap(shape=(16, 16, 16), blocks={1: ((2, 6), (2, 6), (2, 6))})


def _empty_label_map():
    return make_labelmap(shape=(16, 16, 16), blocks=None)


def _well_separated_three_label_map():
    blocks = {
        1: ((2, 6), (2, 6), (2, 6)),
        2: ((2, 6), (10, 14), (2, 6)),
        3: ((10, 14), (2, 6), (2, 6)),
    }
    return make_labelmap(shape=(16, 16, 16), blocks=blocks)


def _assert_coincidence(seg_img, label_a: int, label_b: int):
    """Assert (and return) that *label_a* and *label_b* share a centroid --
    the required precondition check (Testing Strategy) so a future change to
    ``compute_centroid`` fails loudly instead of turning every D4 test here
    into a vacuous pass on a non-coincident map."""
    ca = compute_centroid(seg_img, label_a)
    cb = compute_centroid(seg_img, label_b)
    assert ca.centroid_mm == cb.centroid_mm, (
        f"fixture precondition failed: label {label_a} centroid {ca.centroid_mm} "
        f"!= label {label_b} centroid {cb.centroid_mm} -- this fixture must "
        f"produce an exact coincidence for the D4 tests to mean anything"
    )
    return ca, cb


def _run_cli(args, capsys):
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _load_rebuild_tool():
    import importlib.util
    import sys

    module_path = _REPO_ROOT / "scripts" / "rebuild_verse_reference.py"
    spec = importlib.util.spec_from_file_location("rebuild_verse_reference", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# =========================================================================== #
# AC1: the coincidence check is a public helper
# =========================================================================== #


def test_ac1_helper_exported_and_in_all():
    import segfacet.features.spline as spline_mod

    assert hasattr(spline_mod, "find_coincident_centroid_pair")
    assert "find_coincident_centroid_pair" in spline_mod.__all__


# =========================================================================== #
# AC2: the helper names the first coincident pair deterministically
# =========================================================================== #


def test_ac2_first_pair_named_deterministically():
    from segfacet.features.spline import find_coincident_centroid_pair

    coord = (5.0, 5.0, 5.0)
    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", coord, label=2),
        _centroid("L3", coord, label=3),  # a second coincidence -- ignored
        _centroid("L4", (10.0, 10.0, 10.0), label=4),
    ]
    result1 = find_coincident_centroid_pair(centroids)
    result2 = find_coincident_centroid_pair(centroids)

    assert result1 is not None
    assert isinstance(result1.coordinate_mm, tuple)
    assert all(isinstance(v, float) for v in result1.coordinate_mm)
    assert result1.coordinate_mm == coord
    assert (result1.level_a, result1.level_b) == ("L2", "L3")
    assert (result1.label_a, result1.label_b) == (2, 3)
    assert result1 == result2


# =========================================================================== #
# AC3: the helper returns None when no pair is coincident
# =========================================================================== #


def test_ac3_none_for_pairwise_distinct_centroids():
    from segfacet.features.spline import find_coincident_centroid_pair

    assert find_coincident_centroid_pair(_straight_spine(5)) is None


def test_ac3_none_for_near_coincident_1e9mm():
    from segfacet.features.spline import find_coincident_centroid_pair

    centroids = [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", (1e-9, 0.0, 0.0), label=2),
        _centroid("L3", (20.0, 0.0, 0.0), label=3),
    ]
    assert find_coincident_centroid_pair(centroids) is None


# =========================================================================== #
# AC4: fit_centroid_spline's error is unchanged
# =========================================================================== #


def test_ac4_fit_still_raises_naming_coordinate_and_levels():
    coord = (9.5, 9.5, 19.5)
    centroids = [
        _centroid("L2", coord, label=21),
        _centroid("L3", coord, label=22),
    ]
    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids)
    msg = str(exc_info.value)
    assert "L2" in msg and "L3" in msg
    assert _coord_appears(msg, 9.5)
    assert _coord_appears(msg, 19.5)


# =========================================================================== #
# AC5: extract_feature_record no longer raises on coincident centroids
# =========================================================================== #


def test_ac5_extract_feature_record_returns_dict_not_raise():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    record = extract_feature_record(seg_img, bundled_default_config())
    assert isinstance(record, dict)


# =========================================================================== #
# AC6: the degraded record omits the Stage 3 block
# =========================================================================== #


def test_ac6_degraded_record_omits_stage3():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    record = extract_feature_record(seg_img, bundled_default_config())
    assert "stage3" not in record
    assert record["features_version"] == "0.1"


# =========================================================================== #
# AC7: the degraded record carries every Stage 1/2 feature
# =========================================================================== #


def test_ac7_degraded_record_carries_stage1_2_features():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    record = extract_feature_record(seg_img, bundled_default_config())

    per_label = record["per_label"]
    assert {int(k) for k in per_label} == {21, 22}
    for entry in per_label.values():
        assert "geometry" in entry
        assert "components" in entry
        assert "centroid" in entry
    assert "relationships" in record
    assert "overlaps" in record


# =========================================================================== #
# AC8: the record records the cause
# =========================================================================== #


def test_ac8_stage3_unavailable_records_cause():
    seg_img = _coincident_label_map()
    ca, _cb = _assert_coincidence(seg_img, 21, 22)
    record = extract_feature_record(seg_img, bundled_default_config())

    info = record["stage3_unavailable"]
    assert info["reason"] == "coincident_centroids"
    assert info["levels"] == ["L2", "L3"]
    assert info["labels"] == [21, 22]
    assert info["coordinate_mm"] == list(ca.centroid_mm)
    assert isinstance(info["coordinate_mm"], list)
    assert all(isinstance(v, float) for v in info["coordinate_mm"])

    detail = info["detail"]
    assert isinstance(detail, str)
    assert "\n" not in detail
    assert "L2" in detail and "L3" in detail
    for v in ca.centroid_mm:
        assert _coord_appears(detail, v)


# =========================================================================== #
# AC9: the key is absent when Stage 3 succeeds (or is itself absent)
# =========================================================================== #


@pytest.mark.parametrize(
    "label_map_fn",
    [_well_separated_three_label_map, _one_label_map, _empty_label_map],
)
def test_ac9_key_absent_when_stage3_succeeds_or_is_absent(label_map_fn):
    seg_img = label_map_fn()
    record = extract_feature_record(seg_img, bundled_default_config())
    assert "stage3_unavailable" not in record


# =========================================================================== #
# AC10: the degradation is deterministic
# =========================================================================== #


def test_ac10_degradation_deterministic():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    r1 = extract_feature_record(seg_img, bundled_default_config())
    r2 = extract_feature_record(seg_img, bundled_default_config())
    assert r1 == r2


# =========================================================================== #
# AC11: the input image is not mutated
# =========================================================================== #


def test_ac11_input_seg_array_not_mutated():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    before = np.asanyarray(seg_img.dataobj).copy()
    extract_feature_record(seg_img, bundled_default_config())
    after = np.asanyarray(seg_img.dataobj)
    assert np.array_equal(before, after)


# =========================================================================== #
# AC12: the report schema admits the key
# =========================================================================== #


def test_ac12_serialize_report_accepts_stage3_unavailable():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    case_result, features_block = run_qc(seg_img, bundled_default_config())

    report = serialize_report(
        case_result.verdict, "case-129", bundled_default_config(), features=features_block
    )
    assert report["features"]["stage3_unavailable"]["reason"] == "coincident_centroids"


def test_ac12_schema_defines_optional_stage3_unavailable_with_description():
    features_def = _SCHEMA["definitions"]["features"]
    assert "stage3_unavailable" in features_def["properties"]
    assert "stage3_unavailable" not in (features_def.get("required") or [])
    description = features_def["properties"]["stage3_unavailable"].get("description")
    assert description, "stage3_unavailable schema property has no description"


# =========================================================================== #
# AC13: the schema still rejects an unknown key
# =========================================================================== #


def test_ac13_invented_key_still_rejected():
    seg_img = _well_separated_three_label_map()
    record = extract_feature_record(seg_img, bundled_default_config())
    record["stage3_unavailble"] = {"reason": "coincident_centroids"}  # deliberate typo

    with pytest.raises(jsonschema.ValidationError):
        serialize_report(
            Verdict.build(reasons=[], per_label={}), "case-129", bundled_default_config(),
            features=record,
        )


# =========================================================================== #
# AC14: run_qc produces a verdict for the degraded case
# =========================================================================== #


def test_ac14_run_qc_yields_verdict_for_degraded_case():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    case_result, features_block = run_qc(seg_img, bundled_default_config())
    assert features_block["stage3_unavailable"]["reason"] == "coincident_centroids"
    assert case_result.verdict is not None


# =========================================================================== #
# AC15: the human report names the coincident levels
# =========================================================================== #


def test_ac15_human_report_names_coincident_levels_and_coordinate():
    seg_img = _coincident_label_map()
    ca, _cb = _assert_coincidence(seg_img, 21, 22)
    case_result, features_block = run_qc(seg_img, bundled_default_config())

    text = render_human_report(
        case_result.verdict, "case-129", bundled_default_config(), features=features_block
    )
    assert "L2" in text and "L3" in text
    for v in ca.centroid_mm:
        assert _coord_appears(text, v)


# =========================================================================== #
# AC16: the human report is byte-identical when the key is absent
# =========================================================================== #


def test_ac16_human_report_unaffected_when_key_absent():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "clean_control")
    seg_img = loaded_seg_image(case)

    case_result, features_block = run_qc(seg_img, bundled_default_config())
    assert "stage3_unavailable" not in features_block

    text = render_human_report(
        case_result.verdict, "case-129", bundled_default_config(), features=features_block
    )
    assert "Degraded features:" not in text


# =========================================================================== #
# AC17: segfacet run --no-reference yields a report, not a traceback
# =========================================================================== #


def test_ac17_cli_no_reference_survives_and_names_levels(tmp_path, capsys):
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    scan_img = make_scan(shape=(20, 20, 40), spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"

    code, _out, err = _run_cli(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--no-reference",
        ],
        capsys,
    )
    assert code == 0, err
    assert "Traceback" not in err

    json_path = out_dir / "segfacet_report.json"
    txt_path = out_dir / "segfacet_report.txt"
    assert json_path.exists()
    assert txt_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["features"]["stage3_unavailable"]["reason"] == "coincident_centroids"

    text = txt_path.read_text(encoding="utf-8")
    assert "L2" in text and "L3" in text


# =========================================================================== #
# AC18: segfacet run with the default reference also survives
# =========================================================================== #


def test_ac18_cli_default_reference_also_survives(tmp_path, capsys):
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    scan_img = make_scan(shape=(20, 20, 40), spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    out_dir = tmp_path / "out"

    code, _out, err = _run_cli(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0, err
    assert "Traceback" not in err
    assert (out_dir / "segfacet_report.json").exists()
    assert (out_dir / "segfacet_report.txt").exists()


# =========================================================================== #
# AC20: the catalogue does not move
# =========================================================================== #


def test_ac20_catalogue_regeneration_matches_committed_artifacts(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()


# =========================================================================== #
# AC21: the boundary is five
# =========================================================================== #


def test_ac21_floor_is_five():
    import segfacet.features.spline_offset as so_mod

    assert so_mod._MIN_LEVELS_FOR_HELD_OUT == 5


# =========================================================================== #
# AC22: four levels take the in-sample fallback
# =========================================================================== #


@pytest.mark.parametrize("spacing_mm", [(1.0, 1.0, 1.0), (0.8, 0.8, 2.0)])
def test_ac22_four_levels_take_in_sample_fallback(spacing_mm):
    centroids = _straight_spine(4)
    fit = fit_centroid_spline(centroids)
    expected = compute_spline_offsets(centroids, fit, spacing_mm=spacing_mm)

    held_out = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing_mm)
    assert held_out == expected


# =========================================================================== #
# AC23: five levels still take the held-out path
# =========================================================================== #


def test_ac23_five_levels_still_take_held_out_path():
    centroids = _straight_spine(5)
    idx = 2
    scenario = list(centroids)
    scenario[idx] = _displace_index(centroids, idx, 15.0, axis=0)

    held_out = compute_leave_one_out_spline_offsets(scenario)
    fit_in_sample = fit_centroid_spline(scenario)
    in_sample = compute_spline_offsets(scenario, fit_in_sample)

    assert held_out != in_sample
    assert held_out[idx].offset_mm > in_sample[idx].offset_mm


# =========================================================================== #
# AC25/AC26: the docstring states the floor, why, and the measured limitation
# =========================================================================== #


def test_ac25_docstring_states_five_level_floor_and_reason():
    import segfacet.features.spline_offset as so_mod

    doc = (so_mod.__doc__ or "").lower()
    assert "five" in doc
    assert "cubic" in doc
    assert "interpolat" in doc
    assert "weight" in doc


def test_ac26_docstring_records_measured_limitation_and_governing_gate():
    import segfacet.features.spline_offset as so_mod

    doc = so_mod.__doc__ or ""
    assert "0.001" in doc
    assert "15" in doc
    assert "degree" in doc.lower()
    assert "human gate" in doc.lower() or "deformity" in doc.lower()


# =========================================================================== #
# AC27: the four-level blind spot is asserted, not only documented
# =========================================================================== #


def test_ac27_four_level_blind_spot_asserted():
    centroids = _straight_spine(4)
    idx = 1  # an interior level (0 and 3 are the terminal ends at n=4)
    scenario = list(centroids)
    scenario[idx] = _displace_index(centroids, idx, 15.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario)
    assert len(records) == 4
    for r in records:
        assert r.offset_mm < 0.001


# =========================================================================== #
# AC28: the corpus's four-level case is numerically unmoved
# =========================================================================== #

# Values measured on the pre-item tree (2026-08-31), captured via
# extract_feature_record(loaded_seg_image(mode5_remove_level_case), ...) --
# the corpus's only four-level case, per the spec's Assumptions.
_PRE_129_MODE5_REMOVE_LEVEL_OFFSETS_MM = {
    20: 8.999145394285883e-05,
    21: 7.671141041439496e-08,
    23: 7.671141041439002e-08,
    24: 8.977793575361994e-05,
}


def test_ac28_mode5_remove_level_offsets_numerically_unmoved():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode5_remove_level")
    seg_img = loaded_seg_image(case)

    record = extract_feature_record(seg_img, bundled_default_config())
    offsets = record["stage3"]["per_label_offsets"]
    assert offsets, "mode5_remove_level produced no per_label_offsets"
    assert len(offsets) == 4

    seen = set()
    for o in offsets:
        expected = _PRE_129_MODE5_REMOVE_LEVEL_OFFSETS_MM[o["label"]]
        assert o["offset_mm"] == pytest.approx(expected, abs=1e-9)
        assert o["offset_mm"] < mislabel_mod._DEFAULT_MAX_OFFSET_MM
        seen.add(o["label"])
    assert seen == set(_PRE_129_MODE5_REMOVE_LEVEL_OFFSETS_MM)


# =========================================================================== #
# AC29: no corpus case changes its findings
# =========================================================================== #

# (rule_id, sorted(labels)) pairs measured on the pre-item tree (2026-08-31)
# via run_qc(loaded_seg_image(case), bundled_default_config()) for every
# case in tests/corpus/manifest.json.
_PRE_129_FINDINGS = {
    "clean_control": set(),
    "mode1_displace": {("mislabel", (22,))},
    "mode2_fragment": {("fragmentation", (22,))},
    "mode3_inject_islands": {("fragmentation", (22,))},
    "mode4_relabel_swap": set(),
    "mode5_remove_level": {("coverage", ())},
    "mode6_crop_at_border": {("border", (22,)), ("mislabel", (22,))},
    "mode7_sequence_break": {("sequence", (28,))},
    "mode8_force_overlap": set(),
}


def test_ac29_no_corpus_case_changes_findings():
    manifest = load_manifest()
    assert set(_PRE_129_FINDINGS) == {c["case_id"] for c in manifest["cases"]}

    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        case_result, _features_block = run_qc(seg_img, bundled_default_config())
        pairs = {(f.rule_id, tuple(sorted(f.labels))) for f in case_result.findings}
        expected = _PRE_129_FINDINGS[case["case_id"]]
        assert pairs == expected, f"{case['case_id']}: {pairs} != {expected}"


# =========================================================================== #
# AC30: the released VerSe artifact is untouched
# =========================================================================== #


def test_ac30_released_verse_v1_digest_unchanged():
    import test_128_reference_verse_v1_integrity as t128

    digest = hashlib.sha256(t128._ARTIFACT.read_bytes()).hexdigest()
    assert digest == t128._RELEASED_REFERENCE_VERSE_V1_SHA256


# =========================================================================== #
# AC31: the default artifact still matches a fresh build
# =========================================================================== #


def test_ac31_fresh_default_build_matches_committed_within_tolerance(tmp_path):
    from segfacet.reference.artifact import build_and_write_default, default_artifact_path
    from segfacet.synth.golden import assert_matches_committed_artifact

    dest = tmp_path / "reference_default.json"
    build_and_write_default(dest)
    fresh = json.loads(dest.read_text(encoding="utf-8"))
    assert_matches_committed_artifact(fresh, default_artifact_path())


# =========================================================================== #
# AC32: the calibrated threshold is unchanged
# =========================================================================== #


def test_ac32_calibrated_max_offset_mm_unchanged():
    from segfacet.reference.artifact import bundled_production_reference

    tool = _load_rebuild_tool()
    assert mislabel_mod._DEFAULT_MAX_OFFSET_MM == 13.0
    assert mislabel_mod._DEFAULT_MAX_OFFSET_MM == pytest.approx(
        tool.derive_max_offset_mm(bundled_production_reference())
    )

    config_text = default_config_path().read_text(encoding="utf-8")
    assert "max_offset_mm: 13.0" in config_text


# =========================================================================== #
# AC33: no new byte-exact committed-artifact comparison is introduced
# =========================================================================== #


def test_ac33_committed_artifact_guard_reports_no_new_violations():
    import sys

    if str(_TESTS_DIR) not in sys.path:
        sys.path.insert(0, str(_TESTS_DIR))
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_TESTS_DIR))
    assert violations == [], f"unexpected committed-artifact-guard violations: {violations}"


# =========================================================================== #
# AC34: no retired golden path is referenced
# =========================================================================== #


def test_ac34_no_retired_golden_path_referenced_in_this_file():
    this_file_text = Path(__file__).read_text(encoding="utf-8")
    # Built via concatenation so this very assertion does not itself embed
    # the literal string it is checking for the absence of.
    retired_dir = "tests/corpus/" + "golden/"
    retired_016 = "tests/golden/" + "016_features_report.json"
    retired_022 = "tests/golden/" + "022_stage3_report.json"
    assert retired_dir not in this_file_text
    assert retired_016 not in this_file_text
    assert retired_022 not in this_file_text


# =========================================================================== #
# Adversarial / edge cases -- D4
# =========================================================================== #


def test_adv_three_mutually_coincident_degrades_once_naming_first_pair():
    seg_img = _triple_coincident_label_map()
    c21 = compute_centroid(seg_img, 21)
    c22 = compute_centroid(seg_img, 22)
    c23 = compute_centroid(seg_img, 23)
    assert c21.centroid_mm == c22.centroid_mm == c23.centroid_mm

    record = extract_feature_record(seg_img, bundled_default_config())
    info = record["stage3_unavailable"]
    assert info["reason"] == "coincident_centroids"
    assert info["labels"] == [21, 22]
    assert info["levels"] == ["L2", "L3"]

    record2 = extract_feature_record(seg_img, bundled_default_config())
    assert record2["stage3_unavailable"] == info


def test_adv_coincident_pair_among_five_labels_still_degrades():
    seg_img = _five_label_with_one_coincident_pair()
    c21 = compute_centroid(seg_img, 21)
    c22 = compute_centroid(seg_img, 22)
    assert c21.centroid_mm == c22.centroid_mm

    record = extract_feature_record(seg_img, bundled_default_config())
    assert "stage3" not in record
    assert record["stage3_unavailable"]["reason"] == "coincident_centroids"
    assert {int(k) for k in record["per_label"]} == {1, 2, 3, 21, 22}


def test_adv_single_voxel_coincident_pair_degrades():
    seg_img = _single_voxel_coincident_label_map()
    c30 = compute_centroid(seg_img, 30)
    c31 = compute_centroid(seg_img, 31)
    assert c30.centroid_mm == c31.centroid_mm

    record = extract_feature_record(seg_img, bundled_default_config())
    info = record["stage3_unavailable"]
    assert info["reason"] == "coincident_centroids"
    assert info["labels"] == [30, 31]
    assert info["levels"] == ["S3", "S4"]


def test_adv_near_coincident_pipeline_does_not_degrade():
    """The complement of AC3/AC9 at the pipeline level: a 1e-9 mm
    perturbation must not trip the guard -- Stage 3 is computed and no
    ``stage3_unavailable`` key appears."""
    seg_img = _near_coincident_pipeline_map()
    c1 = compute_centroid(seg_img, 1)
    c2 = compute_centroid(seg_img, 2)
    assert c1.centroid_mm != c2.centroid_mm
    dx = abs(c1.centroid_mm[0] - c2.centroid_mm[0])
    assert 0.0 < dx < 1e-6

    record = extract_feature_record(seg_img, bundled_default_config())
    assert "stage3_unavailable" not in record
    assert "stage3" in record


def test_adv_degraded_record_round_trips_through_serialize_and_json():
    seg_img = _coincident_label_map()
    _assert_coincidence(seg_img, 21, 22)
    case_result, features_block = run_qc(seg_img, bundled_default_config())

    report1 = serialize_report(
        case_result.verdict, "case-129", bundled_default_config(), features=features_block
    )
    text1 = json.dumps(report1, sort_keys=True)
    round_tripped = json.loads(text1)
    text2 = json.dumps(round_tripped, sort_keys=True)
    assert text1 == text2
    assert round_tripped["features"]["stage3_unavailable"]["reason"] == "coincident_centroids"

    report2 = serialize_report(
        case_result.verdict, "case-129", bundled_default_config(), features=features_block
    )
    assert json.dumps(report2, sort_keys=True) == text1


# =========================================================================== #
# Adversarial / edge cases -- D5
# =========================================================================== #


@pytest.mark.parametrize("idx", [0, 1, 2, 3])
def test_adv_four_level_blind_spot_at_every_position(idx):
    centroids = _straight_spine(4)
    scenario = list(centroids)
    scenario[idx] = _displace_index(centroids, idx, 15.0, axis=0)

    records = compute_leave_one_out_spline_offsets(scenario)
    assert len(records) == 4
    for r in records:
        assert r.offset_mm < 0.001


def test_adv_five_level_terminal_displacement_uses_held_out_path():
    centroids = _straight_spine(5)
    scenario = list(centroids)
    scenario[0] = _displace_index(centroids, 0, 15.0, axis=0)

    held_out = compute_leave_one_out_spline_offsets(scenario)
    fit_in_sample = fit_centroid_spline(scenario)
    in_sample = compute_spline_offsets(scenario, fit_in_sample)

    assert held_out != in_sample
    for r in held_out:
        assert math.isfinite(r.offset_mm)


def test_adv_leave_one_out_n4_deterministic():
    centroids = _straight_spine(4)
    first = compute_leave_one_out_spline_offsets(centroids)
    second = compute_leave_one_out_spline_offsets(centroids)
    assert first == second
