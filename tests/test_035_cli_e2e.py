"""End-to-end CLI tests for the item 035 rule-engine wiring (AC16-AC18, plus
the CLI-determinism half of AC29).

Covers:
- AC16: segqc run on a ground-truth-shaped fixture writes both wired reports
  (features + findings, schema-valid).
- AC17: the CLI fires a heuristic end-to-end on a crafted real label map
  (missing interior level, reachable through real extraction).
- AC18: the CLI uses the bundled default config and honours --config,
  including a clean error on a missing/invalid --config path.
- AC29 (CLI half): two CLI runs on the same inputs produce byte-identical
  segqc_report.json.

Adversarial / edge-case scenarios included:
- --config pointing at a non-existent file exits 1 with a stderr message and
  no traceback.
- --config pointing at a wrong-schema-version YAML exits 1 cleanly.
- The empty label map still writes both reports (backward-compat regression
  guard for the item-035 wiring).
"""

from __future__ import annotations

import json

import pytest

from segqc.cli import main
from segqc.config import SUPPORTED_SCHEMA_VERSION

from synthetic import make_labelmap, make_scan, write_nifti


def _run(args: list[str], capsys) -> tuple[int, str, str]:
    """Invoke ``main(args)`` and return ``(exit_code, stdout, stderr)``."""
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _write_missing_level_case(tmp_path):
    """Build a real synthetic NIfTI pair with L1 (20) and L3 (22) present but
    L2 (21) missing -- an interior gap reachable through real feature
    extraction (fires the 'coverage' rule's missing-interior-level check,
    which is always active, not opt-in)."""
    shape = (16, 16, 16)
    blocks = {
        20: ((2, 6), (2, 6), (2, 6)),
        22: ((10, 14), (10, 14), (10, 14)),
    }
    seg_img = make_labelmap(shape=shape, blocks=blocks, spacing=(1.0, 1.0, 1.0))
    scan_img = make_scan(shape=shape, spacing=(1.0, 1.0, 1.0), gradient=True)
    scan_path = write_nifti(scan_img, tmp_path / "scan.nii.gz")
    seg_path = write_nifti(seg_img, tmp_path / "seg.nii.gz")
    return scan_path, seg_path


# =========================================================================== #
# AC16: GT-shaped fixture writes both wired reports
# =========================================================================== #


def test_ac16_writes_both_report_files(labelled_blocks_files, tmp_path, capsys):
    """AC16: both segqc_report.json and segqc_report.txt are written."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    assert (out_dir / "segqc_report.json").exists()
    assert (out_dir / "segqc_report.txt").exists()


def test_ac16_json_validates_against_schema(labelled_blocks_files, tmp_path, capsys):
    """AC16: the JSON report validates against the v0 schema."""
    import jsonschema

    from segqc.report import _SCHEMA

    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, _SCHEMA)


def test_ac16_json_contains_features_block(labelled_blocks_files, tmp_path, capsys):
    """AC16: the JSON report contains a top-level 'features' block."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "features" in data
    assert "per_label" in data["features"]


def test_ac16_json_contains_findings_array(labelled_blocks_files, tmp_path, capsys):
    """AC16: the JSON report contains a top-level 'findings' array."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert "findings" in data
    assert isinstance(data["findings"], list)


def test_ac16_run_exits_without_error(labelled_blocks_files, tmp_path, capsys):
    """AC16: the run completes with an exit code of 0 or 1 (no crash / traceback)."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _out, err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys
    )
    assert code in (0, 1)
    assert "Traceback" not in err


# =========================================================================== #
# AC17: CLI fires a heuristic end-to-end on a crafted real label map
# =========================================================================== #


def test_ac17_missing_interior_level_yields_non_empty_findings(tmp_path, capsys):
    """AC17: L1/L3-present-L2-missing real fixture yields a non-empty findings
    array."""
    scan_path, seg_path = _write_missing_level_case(tmp_path)
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert data["findings"], "Expected at least one finding for the missing-interior-level fixture"


def test_ac17_missing_interior_level_verdict_not_pass(tmp_path, capsys):
    """AC17: the aggregated verdict is not 'pass' for the missing-level fixture."""
    scan_path, seg_path = _write_missing_level_case(tmp_path)
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert data["verdict"] != "pass"


def test_ac17_missing_interior_level_finding_rule_id_coverage(tmp_path, capsys):
    """AC17: the coverage rule specifically fires for the missing L2 level."""
    scan_path, seg_path = _write_missing_level_case(tmp_path)
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    rule_ids = {f["rule_id"] for f in data["findings"]}
    assert "coverage" in rule_ids


def test_ac17_exit_code_matches_aggregated_verdict(tmp_path, capsys):
    """AC17: exit code is 0 for flagged-for-review, 1 for fail, matching the
    aggregated verdict."""
    scan_path, seg_path = _write_missing_level_case(tmp_path)
    out_dir = tmp_path / "out"
    code, _out, _err = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys
    )
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    if data["verdict"] == "fail":
        assert code == 1
    else:
        assert code == 0


# =========================================================================== #
# AC18: bundled default config + --config override + clean error handling
# =========================================================================== #


def test_ac18_no_config_flag_uses_bundled_default(labelled_blocks_files, tmp_path, capsys):
    """AC18: with no --config flag, the run succeeds using the bundled default
    (config_version reflects the bundled schema_version)."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    assert data["config_version"] == SUPPORTED_SCHEMA_VERSION


def test_ac18_config_flag_loads_custom_yaml(labelled_blocks_files, tmp_path, capsys):
    """AC18: --config <path> loads that YAML file via load_config."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    custom_cfg = tmp_path / "custom.yaml"
    custom_cfg.write_text(
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n"
        "  bounds:\n"
        "    enabled: false\n",
        encoding="utf-8",
    )
    code, _out, err = _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--config", str(custom_cfg),
        ],
        capsys,
    )
    assert code in (0, 1)
    assert "Traceback" not in err
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    rule_ids = {f["rule_id"] for f in data["findings"]}
    assert "bounds" not in rule_ids


def test_ac18_missing_config_path_exits_one_clean_stderr(labelled_blocks_files, tmp_path, capsys):
    """AC18: --config pointing at a non-existent file exits 1 with a clean
    stderr message and no traceback."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    missing_cfg = tmp_path / "does_not_exist.yaml"
    code, _out, err = _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--config", str(missing_cfg),
        ],
        capsys,
    )
    assert code == 1
    assert err.strip()
    assert "Traceback" not in err


def test_ac18_invalid_schema_version_config_exits_one_clean_stderr(
    labelled_blocks_files, tmp_path, capsys
):
    """AC18: --config pointing at a wrong-version YAML exits 1 cleanly."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    bad_cfg = tmp_path / "bad_version.yaml"
    bad_cfg.write_text("schema_version: '99.9'\n", encoding="utf-8")
    code, _out, err = _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--config", str(bad_cfg),
        ],
        capsys,
    )
    assert code == 1
    assert err.strip()
    assert "Traceback" not in err


def test_ac18_malformed_yaml_config_exits_one_clean_stderr(labelled_blocks_files, tmp_path, capsys):
    """AC18: --config pointing at syntactically invalid YAML exits 1 cleanly."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    bad_cfg = tmp_path / "malformed.yaml"
    bad_cfg.write_text("schema_version: [unterminated\n", encoding="utf-8")
    code, _out, err = _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--config", str(bad_cfg),
        ],
        capsys,
    )
    assert code == 1
    assert err.strip()
    assert "Traceback" not in err


def test_ac18_invalid_config_does_not_write_reports(labelled_blocks_files, tmp_path, capsys):
    """AC18: an invalid --config error path exits before writing any report."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    missing_cfg = tmp_path / "does_not_exist.yaml"
    _run(
        [
            "run", "--scan", str(scan_path), "--seg", str(seg_path),
            "--out", str(out_dir), "--config", str(missing_cfg),
        ],
        capsys,
    )
    assert not (out_dir / "segqc_report.json").exists()


# =========================================================================== #
# AC29 (CLI half): byte-identical JSON across repeated runs
# =========================================================================== #


def test_adv_two_cli_runs_produce_byte_identical_json(labelled_blocks_files, tmp_path, capsys):
    """AC29: two CLI runs on the same inputs produce byte-identical
    segqc_report.json content."""
    scan_path, seg_path = labelled_blocks_files
    out_dir_a = tmp_path / "out_a"
    out_dir_b = tmp_path / "out_b"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir_a)], capsys)
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir_b)], capsys)
    text_a = (out_dir_a / "segqc_report.json").read_text(encoding="utf-8")
    text_b = (out_dir_b / "segqc_report.json").read_text(encoding="utf-8")
    assert text_a == text_b


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_labelmap_still_writes_both_reports(empty_labelmap_files, tmp_path, capsys):
    """Adversarial: the item-007 empty-label-map regression still writes both
    report files under the item-035 wiring (backward-compat guard)."""
    scan_path, seg_path = empty_labelmap_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    assert (out_dir / "segqc_report.json").exists()
    assert (out_dir / "segqc_report.txt").exists()


def test_adv_empty_labelmap_json_still_validates(empty_labelmap_files, tmp_path, capsys):
    """Adversarial: the empty-label-map JSON report (fail verdict) still
    validates against the extended schema."""
    import jsonschema

    from segqc.report import _SCHEMA

    scan_path, seg_path = empty_labelmap_files
    out_dir = tmp_path / "out"
    _run(["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)], capsys)
    data = json.loads((out_dir / "segqc_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(data, _SCHEMA)
    assert data["verdict"] == "fail"
