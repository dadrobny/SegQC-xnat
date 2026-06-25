"""End-to-end CLI tests for ``segqc run`` (items 006, 008-010).

These tests exercise the fully-wired ``run`` subcommand: loading real NIfTI
fixtures from disk, printing the label inventory, writing the v0 JSON and
plain-text reports, and handling error paths. All I/O is isolated to pytest's
``tmp_path``.

Fixtures are sourced from ``conftest.py`` (item 002's canonical set).

Report format: v0 JSON schema (``schema_version`` = ``"0.1"``), required fields:
``schema_version``, ``config_version``, ``case_id``, ``verdict``, ``reasons``,
``per_label``.  Exit codes: 0 for pass/flagged-for-review, 1 for fail or input
error.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from segqc.cli import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], capsys) -> tuple[int, str, str]:
    """Invoke ``main(args)`` and return ``(exit_code, stdout, stderr)``."""
    code = main(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# Core happy-path tests
# ---------------------------------------------------------------------------


def test_run_loads_and_exits_zero(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` on a valid fixture exits 0."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0, f"Expected exit 0, got {code}; stderr: {_stderr}"


def test_run_prints_label_inventory(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` prints at least one label line to stdout.

    The labelled-blocks fixture has labels 1, 2, 3 which map to C1, C2, C3 in
    the default TotalSegmentator/VerSe convention. At minimum, stdout must
    contain anatomical names and voxel counts.
    """
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    # Header must be present
    assert "Label inventory:" in stdout
    # At least one anatomical name from the fixture labels 1, 2, 3 -> C1, C2, C3
    assert any(name in stdout for name in ("C1", "C2", "C3"))
    # At least one voxel count (64 voxels per 4^3 block)
    assert "64" in stdout


def test_run_writes_json_report(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` creates ``segqc_report.json`` in the output directory."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    report_path = out_dir / "segqc_report.json"
    assert report_path.exists(), "segqc_report.json not found in output dir"


def test_run_json_fields(labelled_blocks_files, tmp_path, capsys):
    """The v0 JSON report contains all required top-level keys with the right types."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    report_path = out_dir / "segqc_report.json"
    with report_path.open(encoding="utf-8") as fh:
        data = json.load(fh)

    # v0 schema required fields
    assert "schema_version" in data and data["schema_version"] == "0.1"
    assert "config_version" in data and isinstance(data["config_version"], str)
    assert data["config_version"] != ""
    assert "case_id" in data and isinstance(data["case_id"], str)
    assert data["case_id"] != ""
    assert "verdict" in data and data["verdict"] in ("pass", "flagged-for-review", "fail")
    assert "reasons" in data and isinstance(data["reasons"], list)
    assert "per_label" in data and isinstance(data["per_label"], dict)


def test_run_json_inventory_matches_fixture(labelled_blocks_files, tmp_path, capsys):
    """v0 JSON report for labelled-blocks fixture has pass verdict and correct case_id.

    The labelled-blocks fixture has labels 1, 2, 3 (192 foreground voxels total).
    With default config thresholds (min_foreground_voxels=0, min_label_count=0),
    the empty check does not fire, so the overall verdict must be 'pass'.
    The case_id is derived from the scan filename stem ('scan').
    """
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    # labelled-blocks has 3 non-zero labels -> no empty condition fires -> pass
    assert data["verdict"] == "pass"
    # case_id is derived from the scan filename 'scan.nii.gz' -> 'scan'
    assert data["case_id"] == "scan"
    # per_label is a dict (may be empty at Stage 1; what matters is the type)
    assert isinstance(data["per_label"], dict)


# ---------------------------------------------------------------------------
# Error-handling tests
# ---------------------------------------------------------------------------


def test_run_missing_scan_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when the scan file does not exist."""
    seg_path = tmp_path / "seg.nii.gz"
    # Create a dummy seg so the error is definitively about the scan
    import nibabel as nib
    import numpy as np
    nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.int16), np.eye(4)),
             str(seg_path))

    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(tmp_path / "nonexistent.nii.gz"),
         "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 1, f"Expected exit 1, got {code}"
    assert "Error:" in stderr, "No error message printed to stderr"
    # No output dir / report should have been created
    assert not out_dir.exists() or not (out_dir / "segqc_report.json").exists()


def test_run_missing_seg_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when the segmentation file does not exist."""
    scan_path = tmp_path / "scan.nii.gz"
    import nibabel as nib
    import numpy as np
    nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.int16), np.eye(4)),
             str(scan_path))

    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path),
         "--seg", str(tmp_path / "nonexistent.nii.gz"),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 1, f"Expected exit 1, got {code}"
    assert "Error:" in stderr


# ---------------------------------------------------------------------------
# Output-directory creation
# ---------------------------------------------------------------------------


def test_run_creates_nested_out_dir(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` creates ``--out`` and any missing parent directories."""
    scan_path, seg_path = labelled_blocks_files
    # Use a deeply nested path that doesn't exist yet
    out_dir = tmp_path / "a" / "b" / "c" / "qc_out"
    assert not out_dir.exists()
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    assert (out_dir / "segqc_report.json").exists()


# ---------------------------------------------------------------------------
# CLI flag behaviour
# ---------------------------------------------------------------------------


def test_run_log_level_default_no_crash(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` without ``--log-level`` succeeds (default WARNING)."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0


def test_run_log_level_debug(labelled_blocks_files, tmp_path, capsys):
    """``segqc run --log-level DEBUG`` succeeds and exits 0."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir), "--log-level", "DEBUG"],
        capsys,
    )
    assert code == 0


def test_run_help_lists_log_level(capsys):
    """``segqc run --help`` exits 0 and the help text mentions ``--log-level``."""
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--log-level" in captured.out


def test_run_help_still_exits_zero(capsys):
    """``segqc run --help`` still exits 0 after item 006 changes (regression guard)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--help"])
    assert exc_info.value.code == 0


def test_top_level_help_still_exits_zero(capsys):
    """``segqc --help`` still exits 0 (regression guard)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# Empty label map
# ---------------------------------------------------------------------------


def test_run_empty_labelmap_inventory(empty_labelmap_files, tmp_path, capsys):
    """``segqc run`` on an empty label map exits 1 (fail verdict) and writes v0 report.

    An all-zero segmentation triggers the empty-detection check (condition 1:
    no foreground voxels), which sets is_empty=True and produces a fail verdict.
    The CLI therefore exits 1. Both report files are still written before exit.
    """
    scan_path, seg_path = empty_labelmap_files
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    # Empty segmentation -> fail verdict -> exit code 1
    assert code == 1, f"Expected exit 1 for empty label map, got {code}"
    assert "no foreground labels found" in stdout
    # JSON is still written even on fail
    report_path = out_dir / "segqc_report.json"
    assert report_path.exists(), "segqc_report.json must be written even on fail verdict"
    with report_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    # v0 schema fields
    assert data["schema_version"] == "0.1"
    assert data["verdict"] == "fail"
    # At least one reason must be present explaining the failure
    assert len(data["reasons"]) >= 1
    assert any("foreground" in r["message"].lower() or "empty" in r["message"].lower()
               for r in data["reasons"])


# ---------------------------------------------------------------------------
# Adversarial tests (validator pass — item 006)
# ---------------------------------------------------------------------------


def test_run_out_is_existing_file_exits_one(labelled_blocks_files, tmp_path, capsys):
    """``segqc run`` exits 1 and prints an error when ``--out`` is an existing file.

    If <out> names an existing regular file, ``mkdir`` raises ``FileExistsError``.
    The CLI must catch it cleanly (exit 1 + error to stderr) rather than letting
    the traceback propagate to the caller.
    """
    scan_path, seg_path = labelled_blocks_files
    # Create a file where --out should be a directory
    existing_file = tmp_path / "conflict.txt"
    existing_file.write_text("I am a file, not a directory")
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(existing_file)],
        capsys,
    )
    assert code == 1, (
        f"Expected exit 1 when --out is an existing file, got {code}; "
        f"stderr: {stderr!r}"
    )
    assert stderr.strip(), "Expected an error message on stderr"


def test_run_directory_as_scan_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when ``--scan`` is a directory."""
    scan_dir = tmp_path / "scan_dir"
    scan_dir.mkdir()
    import nibabel as nib
    import numpy as np

    seg_path = tmp_path / "seg.nii.gz"
    nib.save(
        nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.int16), np.eye(4)),
        str(seg_path),
    )
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_dir), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 1
    assert "Error:" in stderr


def test_run_garbage_file_as_seg_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when ``--seg`` is a non-NIfTI (garbage) file."""
    import nibabel as nib
    import numpy as np

    scan_path = tmp_path / "scan.nii.gz"
    nib.save(
        nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.float32), np.eye(4)),
        str(scan_path),
    )
    garbage = tmp_path / "garbage.nii.gz"
    garbage.write_bytes(b"\x00\x01garbage binary data not a nifti")
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(garbage),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 1
    assert "Error:" in stderr


def test_run_shape_mismatch_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when scan and seg have different shapes."""
    import nibabel as nib
    import numpy as np

    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((10, 10, 10), dtype=np.float32), np.eye(4)),
             str(scan_path))
    nib.save(nib.Nifti1Image(np.zeros((8, 8, 8), dtype=np.int16), np.eye(4)),
             str(seg_path))
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 1
    assert "Error:" in stderr


def test_run_anisotropic_spacing_pass_verdict(tmp_path, capsys):
    """``segqc run`` on the anisotropic fixture exits 0 with a pass verdict.

    The anisotropic case has 2 labels and 96 foreground voxels. With default
    thresholds the empty check does not fire, so the verdict must be 'pass'
    and the exit code 0. This confirms the CLI handles non-isotropic affines
    without crashing and the v0 report is written correctly.
    """
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from synthetic import anisotropic_case

    scan_path, seg_path = anisotropic_case().write(tmp_path, suffix=".nii.gz")
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    # anisotropic_case has foreground labels -> no empty condition fires -> pass
    assert data["verdict"] == "pass"
    assert data["schema_version"] == "0.1"


def test_run_unknown_labels_pass_verdict(tmp_path, capsys):
    """``segqc run`` with unknown labels still exits 0 at Stage 1 (empty check only).

    Labels 100 and 200 are not in the TotalSegmentator/VerSe convention. The
    Stage 1 pipeline only checks for emptiness; unknown labels do not trigger a
    fail. With 250 foreground voxels and default thresholds, the verdict is 'pass'
    and the exit code 0. The stdout inventory must show those labels as unknown.
    """
    import nibabel as nib
    import numpy as np

    arr = np.zeros((10, 10, 10), dtype=np.uint16)
    arr[0:5, 0:5, 0:5] = 100   # not in default convention
    arr[5:10, 5:10, 5:10] = 200  # not in default convention
    seg_img = nib.Nifti1Image(arr, np.eye(4))
    scan_img = nib.Nifti1Image(np.zeros((10, 10, 10), dtype=np.float32), np.eye(4))
    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(scan_img, str(scan_path))
    nib.save(seg_img, str(seg_path))
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    # Non-empty segmentation -> no empty condition fires -> pass verdict -> exit 0
    assert code == 0
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        report = json.load(fh)
    assert report["schema_version"] == "0.1"
    assert report["verdict"] == "pass"
    # The stdout inventory line must mention the unknown labels
    assert "100" in stdout or "200" in stdout, (
        "Expected unknown label values (100, 200) to appear in stdout inventory"
    )


def test_run_single_voxel_volume(tmp_path, capsys):
    """``segqc run`` handles a 1x1x1 volume without crashing and writes a v0 report.

    A single non-zero voxel is non-empty by definition. With default thresholds
    the empty check does not fire, so the verdict is 'pass' and exit code 0.
    The v0 report must contain all required schema fields.
    """
    import nibabel as nib
    import numpy as np

    scan_img = nib.Nifti1Image(np.zeros((1, 1, 1), dtype=np.float32), np.eye(4))
    seg_img = nib.Nifti1Image(np.ones((1, 1, 1), dtype=np.int16), np.eye(4))
    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(scan_img, str(scan_path))
    nib.save(seg_img, str(seg_path))
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    assert (out_dir / "segqc_report.json").exists()
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        report = json.load(fh)
    # v0 schema required fields must all be present
    assert report["schema_version"] == "0.1"
    assert report["verdict"] == "pass"
    assert isinstance(report["reasons"], list)
    assert isinstance(report["per_label"], dict)


def test_run_affine_mismatch_exits_one(tmp_path, capsys):
    """``segqc run`` exits 1 when scan and seg have incompatible affines."""
    import nibabel as nib
    import numpy as np

    affine1 = np.eye(4, dtype=np.float64)
    affine2 = np.eye(4, dtype=np.float64)
    affine2[0, 0] = 1.1  # well outside tolerance (rtol=1e-5, atol=1e-4)

    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    nib.save(nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.float32), affine1),
             str(scan_path))
    nib.save(nib.Nifti1Image(np.ones((4, 4, 4), dtype=np.int16), affine2),
             str(seg_path))
    out_dir = tmp_path / "out"
    code, _stdout, stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 1
    assert "Error:" in stderr
