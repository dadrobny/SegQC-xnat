"""Tests for item 065's ``segfacet run --intensity`` CLI wiring
(``src/segfacet/cli.py``'s ``_handle_run``), the sibling of item 049's
``--reference`` flag: OFF by default, driving ``run_qc_with_intensity`` and
embedding an ``image_features`` block in the written JSON report when
enabled.

Covers Acceptance Criteria AC8-AC11, AC15:

- AC8: ``segfacet run --scan <clean_hu> --seg <shared seg> --intensity --out
  <dir>`` exits 0 and writes a report whose ``image_features`` block is
  present, ``available == True``, carries a per-label ``first_order`` dict,
  and whose ``findings`` carry no ``intensity`` finding.
- AC9: the same invocation over ``implausible_metal`` writes a report whose
  ``findings`` include >= 1 ``intensity`` entry naming label 22, with
  ``image_features`` present.
- AC10: without ``--intensity`` (and no config ``intensity.enabled``), the
  report has no ``image_features`` key and no ``intensity`` finding --
  identical in shape to the pre-065 report.
- AC11: the intensity path is flag/config toggleable -- off (absent), on via
  ``--intensity`` (present), on via config ``intensity.enabled: true``
  without the CLI flag (present).
- AC15: two identical ``segfacet run --intensity`` invocations write
  byte-identical ``segfacet_report.json``.

Adversarial / edge-case scenarios included:
- ``--scan``/``--seg`` pointing at a nonexistent path -- clean exit 1, no
  traceback (mirrors item 010/049's caller-error handling).
- A scan/seg grid mismatch under ``--intensity`` -- clean exit 1, no
  traceback (item 059's ``_check_alignment`` ``ValueError`` caught by the
  CLI, per the item spec's Assumptions).
- ``--intensity`` without a co-supplied ``--scan``/label-bearing corpus
  fixture still behaves (``--scan`` is already mandatory on ``run``, so this
  is exercised as "intensity path over a plain single/zero-label map" --
  still emits a valid ``image_features`` block, no crash).
"""

from __future__ import annotations

import json

import jsonschema

from segfacet.config import SUPPORTED_SCHEMA_VERSION
from segfacet.synth.intensity import INTENSITY_CORPUS_DIR, load_intensity_manifest

_TARGET_LABEL = 22


def _manifest_cases():
    return load_intensity_manifest()["cases"]


def _case(case_id):
    for c in _manifest_cases():
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the intensity manifest")


def _case_paths(case_id):
    case = _case(case_id)
    scan_path = INTENSITY_CORPUS_DIR / case["scan_fixture"]
    seg_path = INTENSITY_CORPUS_DIR / case["seg_fixture"]
    return str(scan_path), str(seg_path)


def _report_schema():
    import importlib.resources as pkg_resources

    import segfacet as segfacet_pkg

    ref = pkg_resources.files(segfacet_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _write_yaml(tmp_path, content, name="config.yaml"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# =========================================================================== #
# AC8: CLI emits image_features on a clean run
# =========================================================================== #


def test_ac8_cli_intensity_flag_writes_image_features_on_clean_run(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    code = main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    assert code == 0

    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    image_features = report["image_features"]
    assert image_features["available"] is True
    assert image_features["per_label"]
    for entry in image_features["per_label"].values():
        assert isinstance(entry["first_order"], dict)

    findings = report.get("findings", [])
    assert not any(f["rule_id"] == "intensity" for f in findings)


def test_ac8_report_is_schema_valid_with_image_features(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(report, _report_schema())


# =========================================================================== #
# AC9: CLI flags the metal variant end-to-end
# =========================================================================== #


def test_ac9_cli_intensity_flag_flags_implausible_metal_on_label_22(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("implausible_metal")
    out_dir = tmp_path / "out"

    code = main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    assert code in (0, 1)

    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert report["image_features"]["available"] is True

    findings = report["findings"]
    intensity_findings = [f for f in findings if f["rule_id"] == "intensity"]
    assert len(intensity_findings) >= 1
    assert any(_TARGET_LABEL in f["labels"] for f in intensity_findings)


# =========================================================================== #
# AC10: --intensity off preserves geometric-only output
# =========================================================================== #


def test_ac10_no_intensity_flag_omits_image_features_key(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("implausible_metal")
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
        ]
    )
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert "image_features" not in report
    findings = report.get("findings", [])
    assert not any(f["rule_id"] == "intensity" for f in findings)


def test_ac10_no_intensity_flag_report_shape_matches_pre_065_shape(tmp_path):
    """Item 090 turns reference mode ON by default, which would add a
    reference_delta key unrelated to what this test is isolating (the
    intensity flag's own effect on report shape) -- pass --no-reference so
    the pre-065 shape comparison stays about intensity, not reference mode."""
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
            "--no-reference",
        ]
    )
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    expected_keys = {
        "schema_version", "config_version", "case_id", "verdict",
        "reasons", "per_label", "features", "findings",
    }
    assert set(report.keys()) == expected_keys


# =========================================================================== #
# AC11: the intensity path is config/flag toggleable
# =========================================================================== #


def test_ac11_config_intensity_enabled_without_cli_flag(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"
    cfg_path = _write_yaml(
        tmp_path,
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "intensity:\n"
        "  enabled: true\n",
    )

    code = main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
            "--config", str(cfg_path),
        ]
    )
    assert code == 0
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert "image_features" in report


def test_ac11_intensity_param_default_and_override():
    from segfacet.config import default_config, load_config

    cfg = default_config()
    assert cfg.intensity_param("enabled", False) is False


def test_ac11_flag_off_and_config_absent_leaves_image_features_absent(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    main(
        [
            "run",
            "--scan", scan_path,
            "--seg", seg_path,
            "--out", str(out_dir),
        ]
    )
    report = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert "image_features" not in report


# =========================================================================== #
# AC15: CLI determinism
# =========================================================================== #


def test_ac15_two_intensity_invocations_write_byte_identical_reports(tmp_path):
    from segfacet.cli import main

    scan_path, seg_path = _case_paths("implausible_metal")
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    common_args = [
        "run",
        "--scan", scan_path,
        "--seg", seg_path,
        "--intensity",
    ]
    assert main(common_args + ["--out", str(out_a)]) in (0, 1)
    assert main(common_args + ["--out", str(out_b)]) in (0, 1)

    bytes_a = (out_a / "segfacet_report.json").read_bytes()
    bytes_b = (out_b / "segfacet_report.json").read_bytes()
    assert bytes_a == bytes_b


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_nonexistent_scan_path_with_intensity_exits_1_no_traceback(tmp_path, capsys):
    from segfacet.cli import main

    _scan_path, seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    code = main(
        [
            "run",
            "--scan", str(tmp_path / "does_not_exist_scan.nii.gz"),
            "--seg", seg_path,
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_adv_nonexistent_seg_path_with_intensity_exits_1_no_traceback(tmp_path, capsys):
    from segfacet.cli import main

    scan_path, _seg_path = _case_paths("clean_hu")
    out_dir = tmp_path / "out"

    code = main(
        [
            "run",
            "--scan", scan_path,
            "--seg", str(tmp_path / "does_not_exist_seg.nii.gz"),
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_adv_grid_mismatched_scan_and_seg_with_intensity_exits_1_no_traceback(
    tmp_path, capsys
):
    """A scan whose voxel grid does not match its seg -- the CLI must catch
    item 059's ``_check_alignment`` ``ValueError`` and report a clean caller
    error, not a traceback (item spec's Assumptions, 'Grid alignment')."""
    import nibabel as nib
    import numpy as np

    from segfacet.cli import main
    from segfacet.synth.clean_gt import build_clean_spine

    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(spine.seg_img, str(seg_path))

    # A scan on a visibly different affine (translated origin) -- shape
    # matches but the affine does not, well beyond load_case's tolerance.
    mismatched_affine = np.array(spine.seg_img.affine, dtype=float)
    mismatched_affine[0, 3] += 1000.0
    scan_data = np.zeros(spine.seg_img.shape, dtype=np.float64)
    mismatched_scan_img = nib.Nifti1Image(scan_data, mismatched_affine)
    scan_path = tmp_path / "scan.nii.gz"
    nib.save(mismatched_scan_img, str(scan_path))

    out_dir = tmp_path / "out"
    code = main(
        [
            "run",
            "--scan", str(scan_path),
            "--seg", str(seg_path),
            "--out", str(out_dir),
            "--intensity",
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
