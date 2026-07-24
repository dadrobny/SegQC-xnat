"""Tests for the container entry script ``docker/entrypoint.py`` (item 068).

Docker-free: the script is loaded via ``importlib.util.spec_from_file_location``
because ``docker/`` is a repo-root deployment directory, not part of the
installed ``segfacet`` package (see item 068's Assumptions). Mock XNAT mount
directories are built under pytest's ``tmp_path``; real ``segfacet.cli.main``
calls are only exercised for the true happy-path / malformed-input tests --
everywhere else ``segfacet.cli.main`` is monkeypatched to a spy so these tests
stay fast and isolate the entry script's own resolution/argv-assembly logic.

One focused test per Acceptance Criterion (AC1-AC22), plus adversarial/edge
cases called out in the item's Testing Strategy.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from synthetic import write_nifti

REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRYPOINT_PATH = REPO_ROOT / "docker" / "entrypoint.py"
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"


def _load_entrypoint_module():
    """Load ``docker/entrypoint.py`` as a standalone module (not a package)."""
    spec = importlib.util.spec_from_file_location("_segfacet_entrypoint_068", ENTRYPOINT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def entrypoint():
    return _load_entrypoint_module()


# =========================================================================== #
# Helpers
# =========================================================================== #


def _make_scan_dir(tmp_path, case, name="scan", filename="scan.nii.gz"):
    scan_dir = tmp_path / name
    scan_dir.mkdir(parents=True, exist_ok=True)
    write_nifti(case.scan_img, scan_dir / filename)
    return scan_dir


def _make_seg_dir(tmp_path, case, name="seg", filename="seg.nii.gz"):
    seg_dir = tmp_path / name
    seg_dir.mkdir(parents=True, exist_ok=True)
    write_nifti(case.seg_img, seg_dir / filename)
    return seg_dir


class _SpyMain:
    """Records the argv it is called with and returns a fixed exit code."""

    def __init__(self, return_code=0):
        self.return_code = return_code
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return self.return_code


# =========================================================================== #
# AC1  Entry script present with a callable main
# =========================================================================== #


def test_ac1_entrypoint_module_exists_at_pinned_path():
    assert ENTRYPOINT_PATH.is_file(), "docker/entrypoint.py must exist"


def test_ac1_entrypoint_exposes_callable_main(entrypoint):
    assert callable(entrypoint.main)


def test_ac1_main_accepts_argv_none_default(entrypoint, tmp_path, monkeypatch):
    # main(argv=None) must fall back to sys.argv[1:] like a normal argparse
    # entry point. Supply a well-formed (but failing, to stay hermetic)
    # invocation via sys.argv and confirm main() still returns a plain int
    # rather than raising, proving the argv=None default path works.
    missing_scan_dir = tmp_path / "no_such_scan_dir"
    missing_seg_dir = tmp_path / "no_such_seg_dir"
    out_dir = tmp_path / "output"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "entrypoint.py",
            "--scan-dir", str(missing_scan_dir),
            "--seg-dir", str(missing_seg_dir),
            "--out-dir", str(out_dir),
        ],
    )
    rc = entrypoint.main(None)
    assert isinstance(rc, int)
    assert rc != 0


# =========================================================================== #
# AC2 / AC3  Single scan/seg file resolution
# =========================================================================== #


def test_ac2_resolve_required_nifti_finds_single_scan_file(entrypoint, tmp_path, labelled_blocks):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    resolved = entrypoint.resolve_required_nifti(scan_dir, "scan")
    assert Path(resolved).resolve() == (scan_dir / "scan.nii.gz").resolve()


def test_ac2_build_run_argv_places_scan_after_scan_flag(entrypoint, tmp_path):
    argv = entrypoint.build_run_argv(
        scan="/input/scan/scan.nii.gz",
        seg="/input/seg/seg.nii.gz",
        out_dir="/output",
        config=None,
        reference_file=None,
        reference_flag=False,
        intensity_flag=False,
    )
    idx = argv.index("--scan")
    assert argv[idx + 1] == "/input/scan/scan.nii.gz"


def test_ac3_resolve_required_nifti_finds_single_seg_file(entrypoint, tmp_path, labelled_blocks):
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    resolved = entrypoint.resolve_required_nifti(seg_dir, "segmentation")
    assert Path(resolved).resolve() == (seg_dir / "seg.nii.gz").resolve()


def test_ac3_build_run_argv_places_seg_after_seg_flag(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/input/scan/scan.nii.gz",
        seg="/input/seg/seg.nii.gz",
        out_dir="/output",
        config=None,
        reference_file=None,
        reference_flag=False,
        intensity_flag=False,
    )
    idx = argv.index("--seg")
    assert argv[idx + 1] == "/input/seg/seg.nii.gz"


# =========================================================================== #
# AC4  --out-dir maps verbatim to segfacet run --out
# =========================================================================== #


def test_ac4_build_run_argv_maps_out_dir_to_out_flag(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/input/scan/scan.nii.gz",
        seg="/input/seg/seg.nii.gz",
        out_dir="/output",
        config=None,
        reference_file=None,
        reference_flag=False,
        intensity_flag=False,
    )
    idx = argv.index("--out")
    assert argv[idx + 1] == "/output"


# =========================================================================== #
# AC5  Happy path produces both report files
# =========================================================================== #


def test_ac5_happy_path_returns_zero_and_writes_both_reports(tmp_path, labelled_blocks, entrypoint):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )

    assert rc == 0
    assert (out_dir / "segfacet_report.json").is_file()
    assert (out_dir / "segfacet_report.txt").is_file()


def test_ac5_happy_path_json_report_parses(tmp_path, labelled_blocks, entrypoint):
    import json

    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )

    parsed = json.loads((out_dir / "segfacet_report.json").read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)


# =========================================================================== #
# AC6 / AC7  Optional config resolution
# =========================================================================== #


def test_ac6_config_dir_with_single_yaml_file_maps_to_config_flag(entrypoint, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "custom.yaml"
    config_file.write_text("thresholds: {}\n", encoding="utf-8")

    resolved = entrypoint.resolve_optional_file(config_dir, ("*.yaml", "*.yml"), "config")
    assert Path(resolved).resolve() == config_file.resolve()

    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=str(config_file), reference_file=None,
        reference_flag=False, intensity_flag=False,
    )
    idx = argv.index("--config")
    assert argv[idx + 1] == str(config_file)


def test_ac7_config_dir_missing_is_noop(entrypoint, tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    resolved = entrypoint.resolve_optional_file(missing_dir, ("*.yaml", "*.yml"), "config")
    assert resolved is None


def test_ac7_config_dir_empty_is_noop(entrypoint, tmp_path):
    empty_dir = tmp_path / "config"
    empty_dir.mkdir()
    resolved = entrypoint.resolve_optional_file(empty_dir, ("*.yaml", "*.yml"), "config")
    assert resolved is None


def test_ac7_run_succeeds_with_missing_config_dir(tmp_path, labelled_blocks, entrypoint):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
            "--config-dir", str(tmp_path / "no_such_config_dir"),
        ]
    )
    assert rc == 0
    assert (out_dir / "segfacet_report.json").is_file()


# =========================================================================== #
# AC8 / AC9  Optional reference resolution
# =========================================================================== #


def test_ac8_reference_dir_with_single_json_file_maps_to_both_flags(entrypoint, tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    reference_file = reference_dir / "ref.json"
    reference_file.write_text("{}", encoding="utf-8")

    resolved = entrypoint.resolve_optional_file(reference_dir, ("*.json",), "reference")
    assert Path(resolved).resolve() == reference_file.resolve()

    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=str(reference_file),
        reference_flag=False, intensity_flag=False,
    )
    assert "--reference" in argv
    idx = argv.index("--reference-artifact")
    assert argv[idx + 1] == str(reference_file)


def test_ac9_reference_dir_missing_is_noop(entrypoint, tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    resolved = entrypoint.resolve_optional_file(missing_dir, ("*.json",), "reference")
    assert resolved is None


def test_ac9_reference_dir_empty_is_noop_and_argv_has_no_reference_artifact(entrypoint, tmp_path):
    empty_dir = tmp_path / "reference"
    empty_dir.mkdir()
    resolved = entrypoint.resolve_optional_file(empty_dir, ("*.json",), "reference")
    assert resolved is None

    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=None,
        reference_flag=False, intensity_flag=False,
    )
    assert "--reference-artifact" not in argv


# =========================================================================== #
# AC10  --reference toggle forwarded verbatim, no artifact when file absent
# =========================================================================== #


def test_ac10_reference_toggle_alone_adds_reference_but_not_artifact(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=None,
        reference_flag=True, intensity_flag=False,
    )
    assert "--reference" in argv
    assert "--reference-artifact" not in argv


def test_ac10_no_reference_toggle_and_no_file_omits_reference(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=None,
        reference_flag=False, intensity_flag=False,
    )
    assert "--reference" not in argv


# =========================================================================== #
# AC11  --intensity toggle forwarded verbatim
# =========================================================================== #


def test_ac11_intensity_flag_present_when_given(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=None,
        reference_flag=False, intensity_flag=True,
    )
    assert "--intensity" in argv


def test_ac11_intensity_flag_absent_when_not_given(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file=None,
        reference_flag=False, intensity_flag=False,
    )
    assert "--intensity" not in argv


# =========================================================================== #
# AC12  --reference never duplicated
# =========================================================================== #


def test_ac12_reference_toggle_plus_file_yields_single_reference_flag(entrypoint):
    argv = entrypoint.build_run_argv(
        scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
        config=None, reference_file="/input/reference/ref.json",
        reference_flag=True, intensity_flag=False,
    )
    assert argv.count("--reference") == 1
    assert "--reference-artifact" in argv


# =========================================================================== #
# AC13  Invokes segfacet run via segfacet.cli.main
# =========================================================================== #


def test_ac13_main_calls_segfacet_cli_main_with_assembled_argv(tmp_path, labelled_blocks, entrypoint, monkeypatch):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    spy = _SpyMain(return_code=0)
    monkeypatch.setattr("segfacet.cli.main", spy)

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
            "--intensity",
        ]
    )

    assert rc == 0
    assert len(spy.calls) == 1
    called_argv = spy.calls[0]
    assert called_argv[0] == "run"
    assert "--scan" in called_argv
    assert "--seg" in called_argv
    assert "--out" in called_argv
    assert "--intensity" in called_argv


def test_ac13_main_propagates_segfacet_cli_main_exit_code(tmp_path, labelled_blocks, entrypoint, monkeypatch):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    spy = _SpyMain(return_code=17)
    monkeypatch.setattr("segfacet.cli.main", spy)

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc == 17


# =========================================================================== #
# AC14  Missing scan dir
# =========================================================================== #


def test_ac14_missing_scan_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"
    missing_scan_dir = tmp_path / "no_such_scan_dir"

    rc = entrypoint.main(
        [
            "--scan-dir", str(missing_scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err
    assert str(missing_scan_dir) in captured.err or "scan" in captured.err.lower()


# =========================================================================== #
# AC15  Empty scan dir (no NIfTI)
# =========================================================================== #


def test_ac15_empty_scan_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


# =========================================================================== #
# AC16  Ambiguous scan dir (>=2 NIfTI files)
# =========================================================================== #


def test_ac16_ambiguous_scan_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    write_nifti(labelled_blocks.scan_img, scan_dir / "scan_a.nii.gz")
    write_nifti(labelled_blocks.scan_img, scan_dir / "scan_b.nii.gz")
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


# =========================================================================== #
# AC17  Missing seg dir
# =========================================================================== #


def test_ac17_missing_seg_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"
    missing_seg_dir = tmp_path / "no_such_seg_dir"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(missing_seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


# =========================================================================== #
# AC18  Non-NIfTI file in a required dir
# =========================================================================== #


def test_ac18_scan_dir_with_only_non_nifti_file_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    (scan_dir / "notes.txt").write_text("not a scan", encoding="utf-8")
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_ac18_seg_dir_with_only_non_nifti_file_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = tmp_path / "seg"
    seg_dir.mkdir()
    (seg_dir / "notes.txt").write_text("not a segmentation", encoding="utf-8")
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


# =========================================================================== #
# AC19  Malformed segmentation -> clear error, no traceback
# =========================================================================== #


def test_ac19_malformed_segmentation_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = tmp_path / "seg"
    seg_dir.mkdir()
    # A file with a NIfTI extension but garbage/unreadable content.
    (seg_dir / "broken.nii.gz").write_bytes(b"not a real nifti file at all")
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


# =========================================================================== #
# AC20  Ambiguous optional override dir
# =========================================================================== #


def test_ac20_ambiguous_config_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    (config_dir / "b.yaml").write_text("b: 2\n", encoding="utf-8")

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
            "--config-dir", str(config_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_ac20_ambiguous_reference_dir_returns_nonzero_and_errors(tmp_path, labelled_blocks, entrypoint, capsys):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir()
    (reference_dir / "a.json").write_text("{}", encoding="utf-8")
    (reference_dir / "b.json").write_text("{}", encoding="utf-8")

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
            "--reference-dir", str(reference_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_ac20_resolve_optional_file_raises_on_two_matches(entrypoint, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "a.yaml").write_text("a: 1\n", encoding="utf-8")
    (config_dir / "b.yml").write_text("b: 2\n", encoding="utf-8")

    with pytest.raises(entrypoint.EntryScriptError):
        entrypoint.resolve_optional_file(config_dir, ("*.yaml", "*.yml"), "config")


# =========================================================================== #
# AC21  No report written on an entry-script input error
# =========================================================================== #


@pytest.mark.parametrize(
    "break_kind",
    ["missing_scan", "empty_scan", "ambiguous_scan", "missing_seg", "non_nifti_scan", "ambiguous_config"],
)
def test_ac21_no_report_written_on_input_error(tmp_path, labelled_blocks, entrypoint, break_kind):
    out_dir = tmp_path / "output"
    scan_dir = tmp_path / "scan"
    seg_dir = tmp_path / "seg"
    config_dir = tmp_path / "config"
    args = None

    if break_kind == "missing_scan":
        seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
        args = ["--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir)]
    elif break_kind == "empty_scan":
        scan_dir.mkdir()
        seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
        args = ["--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir)]
    elif break_kind == "ambiguous_scan":
        scan_dir.mkdir()
        write_nifti(labelled_blocks.scan_img, scan_dir / "a.nii.gz")
        write_nifti(labelled_blocks.scan_img, scan_dir / "b.nii.gz")
        seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
        args = ["--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir)]
    elif break_kind == "missing_seg":
        scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
        args = ["--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir)]
    elif break_kind == "non_nifti_scan":
        scan_dir.mkdir()
        (scan_dir / "notes.txt").write_text("nope", encoding="utf-8")
        seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
        args = ["--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir)]
    elif break_kind == "ambiguous_config":
        scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
        seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
        config_dir.mkdir()
        (config_dir / "a.yaml").write_text("a: 1\n", encoding="utf-8")
        (config_dir / "b.yaml").write_text("b: 2\n", encoding="utf-8")
        args = [
            "--scan-dir", str(scan_dir), "--seg-dir", str(seg_dir), "--out-dir", str(out_dir),
            "--config-dir", str(config_dir),
        ]

    rc = entrypoint.main(args)
    assert rc != 0
    assert not (out_dir / "segfacet_report.json").exists()
    assert not (out_dir / "segfacet_report.txt").exists()


# =========================================================================== #
# AC22  Dockerfile copies the script to the pinned in-image path
# =========================================================================== #


def test_ac22_dockerfile_copies_docker_dir_to_app_docker():
    text = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert re.search(r"COPY\s+docker/\s+/app/docker/", text), (
        "Dockerfile must contain a `COPY docker/ /app/docker/` step so "
        "entrypoint.py lands at /app/docker/entrypoint.py"
    )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_case_insensitive_nifti_extension_is_recognised(entrypoint, tmp_path, labelled_blocks):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    write_nifti(labelled_blocks.scan_img, scan_dir / "CASE.NII.GZ")
    resolved = entrypoint.resolve_required_nifti(scan_dir, "scan")
    assert Path(resolved).name == "CASE.NII.GZ"


def test_adv_plain_nii_extension_is_recognised(entrypoint, tmp_path, labelled_blocks):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    write_nifti(labelled_blocks.scan_img, scan_dir / "scan.nii")
    resolved = entrypoint.resolve_required_nifti(scan_dir, "scan")
    assert Path(resolved).name == "scan.nii"


def test_adv_nifti_file_alongside_hidden_dotfile_is_unambiguous(entrypoint, tmp_path, labelled_blocks):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    write_nifti(labelled_blocks.scan_img, scan_dir / "scan.nii.gz")
    (scan_dir / ".hidden").write_text("", encoding="utf-8")
    resolved = entrypoint.resolve_required_nifti(scan_dir, "scan")
    assert Path(resolved).name == "scan.nii.gz"


def test_adv_out_dir_that_does_not_exist_yet_is_created_by_segfacet_run(tmp_path, labelled_blocks, entrypoint):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "brand_new_output_dir"
    assert not out_dir.exists()

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc == 0
    assert out_dir.is_dir()
    assert (out_dir / "segfacet_report.json").is_file()


def test_adv_scan_dir_that_is_a_file_errors_cleanly(entrypoint, tmp_path, labelled_blocks, capsys):
    scan_path_as_file = tmp_path / "scan_not_a_dir"
    scan_path_as_file.write_text("i am a file, not a directory", encoding="utf-8")
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_path_as_file),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err


def test_adv_build_run_argv_is_deterministic(entrypoint):
    kwargs = dict(
        scan="/input/scan/scan.nii.gz",
        seg="/input/seg/seg.nii.gz",
        out_dir="/output",
        config="/input/config/custom.yaml",
        reference_file="/input/reference/ref.json",
        reference_flag=True,
        intensity_flag=True,
    )
    first = entrypoint.build_run_argv(**kwargs)
    second = entrypoint.build_run_argv(**kwargs)
    assert first == second
    assert first.count("--reference") == 1


def test_adv_build_run_argv_never_emits_reference_twice_across_all_toggle_combinations(entrypoint):
    for reference_flag in (True, False):
        for reference_file in (None, "/input/reference/ref.json"):
            argv = entrypoint.build_run_argv(
                scan="/scan.nii.gz", seg="/seg.nii.gz", out_dir="/output",
                config=None, reference_file=reference_file,
                reference_flag=reference_flag, intensity_flag=False,
            )
            assert argv.count("--reference") <= 1


def test_adv_extra_unknown_argument_is_a_usage_error(entrypoint, capsys):
    with pytest.raises(SystemExit):
        entrypoint.main(["--not-a-real-flag", "value"])


def test_adv_unexpected_exception_from_segfacet_cli_main_becomes_clean_error(
    tmp_path, labelled_blocks, entrypoint, monkeypatch, capsys
):
    scan_dir = _make_scan_dir(tmp_path, labelled_blocks)
    seg_dir = _make_seg_dir(tmp_path, labelled_blocks)
    out_dir = tmp_path / "output"

    def _boom(argv):
        raise RuntimeError("unexpected boom")

    monkeypatch.setattr("segfacet.cli.main", _boom)

    rc = entrypoint.main(
        [
            "--scan-dir", str(scan_dir),
            "--seg-dir", str(seg_dir),
            "--out-dir", str(out_dir),
        ]
    )
    assert rc != 0
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Traceback" not in captured.err
