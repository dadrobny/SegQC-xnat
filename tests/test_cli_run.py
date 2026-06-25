"""End-to-end CLI tests for ``segqc run`` (item 006).

These tests exercise the fully-wired ``run`` subcommand: loading real NIfTI
fixtures from disk, printing the label inventory, writing the stub JSON report,
and handling error paths. All I/O is isolated to pytest's ``tmp_path``.

Fixtures are sourced from ``conftest.py`` (item 002's canonical set).
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
    """The stub JSON report contains all required top-level keys with the right types."""
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

    assert "scan_path" in data and isinstance(data["scan_path"], str)
    assert "seg_path" in data and isinstance(data["seg_path"], str)
    assert "spacing" in data and isinstance(data["spacing"], list) and len(data["spacing"]) == 3
    assert all(isinstance(v, float) for v in data["spacing"])
    assert "foreground_voxels" in data and isinstance(data["foreground_voxels"], int)
    assert data["foreground_voxels"] > 0
    assert "label_inventory" in data and isinstance(data["label_inventory"], list)
    assert len(data["label_inventory"]) > 0
    # Each entry must have label, name, voxels
    for entry in data["label_inventory"]:
        assert "label" in entry
        assert "name" in entry and isinstance(entry["name"], str)
        assert "voxels" in entry and isinstance(entry["voxels"], int)
    assert "config_schema_version" in data and isinstance(data["config_schema_version"], str)


def test_run_json_inventory_matches_fixture(labelled_blocks_files, tmp_path, capsys):
    """JSON inventory matches the known labelled-blocks voxel counts."""
    scan_path, seg_path = labelled_blocks_files
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    # labelled_blocks has 3 labels each with 64 voxels (4x4x4 blocks)
    assert data["foreground_voxels"] == 192  # 3 * 64
    label_map = {e["label"]: e["voxels"] for e in data["label_inventory"]}
    for label in (1, 2, 3):
        assert label in label_map, f"Label {label} missing from JSON inventory"
        assert label_map[label] == 64, f"Label {label} expected 64 voxels, got {label_map[label]}"


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
    """``segqc run`` on an empty label map prints '(no foreground labels found)'."""
    scan_path, seg_path = empty_labelmap_files
    out_dir = tmp_path / "out"
    code, stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path), "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    assert "no foreground labels found" in stdout
    # JSON is still written
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["foreground_voxels"] == 0
    assert data["label_inventory"] == []


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


def test_run_anisotropic_spacing_preserved_in_json(tmp_path, capsys):
    """JSON ``spacing`` reflects the actual anisotropic voxel sizes (not defaulted to 1)."""
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
    # anisotropic_case uses (1.0, 1.0, 3.0) spacing
    assert data["spacing"] == pytest.approx([1.0, 1.0, 3.0]), (
        f"Expected spacing [1.0, 1.0, 3.0] in JSON, got {data['spacing']}"
    )
    assert all(isinstance(v, float) for v in data["spacing"])


def test_run_unknown_labels_in_json(tmp_path, capsys):
    """Unknown labels (not in TotalSegmentator convention) appear in JSON inventory."""
    import nibabel as nib
    import numpy as np

    data = np.zeros((10, 10, 10), dtype=np.uint16)
    data[0:5, 0:5, 0:5] = 100   # not in default convention
    data[5:10, 5:10, 5:10] = 200  # not in default convention
    seg_img = nib.Nifti1Image(data, np.eye(4))
    scan_img = nib.Nifti1Image(np.zeros((10, 10, 10), dtype=np.float32), np.eye(4))
    scan_path = tmp_path / "scan.nii.gz"
    seg_path = tmp_path / "seg.nii.gz"
    import nibabel as nib
    nib.save(scan_img, str(scan_path))
    nib.save(seg_img, str(seg_path))
    out_dir = tmp_path / "out"
    code, _stdout, _stderr = _run(
        ["run", "--scan", str(scan_path), "--seg", str(seg_path),
         "--out", str(out_dir)],
        capsys,
    )
    assert code == 0
    with (out_dir / "segqc_report.json").open(encoding="utf-8") as fh:
        report = json.load(fh)
    labels_in_json = {e["label"] for e in report["label_inventory"]}
    assert 100 in labels_in_json, "Unknown label 100 should appear in JSON inventory"
    assert 200 in labels_in_json, "Unknown label 200 should appear in JSON inventory"
    for entry in report["label_inventory"]:
        assert entry["name"] == "unknown", (
            f"Label {entry['label']} should have name 'unknown', got {entry['name']!r}"
        )


def test_run_single_voxel_volume(tmp_path, capsys):
    """``segqc run`` handles a 1x1x1 volume without crashing."""
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
    assert report["foreground_voxels"] == 1


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
