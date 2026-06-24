"""Smoke tests for the segqc package scaffolding (item 001).

These tests intentionally cover only that the package imports and the CLI parses
and dispatches cleanly. The full test harness and synthetic NIfTI fixtures are
item 002; real ``run`` behaviour is item 006.
"""

import pytest

import segqc
from segqc.cli import main


def test_import_package():
    """`import segqc` succeeds and exposes a non-empty version string."""
    assert isinstance(segqc.__version__, str)
    assert segqc.__version__ != ""


def test_cli_help_exits_zero(capsys):
    """`segqc --help` exits 0 and mentions the `run` subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    assert "run" in capsys.readouterr().out


def test_cli_version_exits_zero(capsys):
    """`segqc --version` exits 0 and prints the package version."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert segqc.__version__ in capsys.readouterr().out


def test_run_subcommand_help(capsys):
    """`segqc run --help` exits 0 and lists --scan/--seg/--out."""
    with pytest.raises(SystemExit) as exc_info:
        main(["run", "--help"])
    assert exc_info.value.code == 0
    out = capsys.readouterr().out
    assert "--scan" in out
    assert "--seg" in out
    assert "--out" in out


def test_run_stub_returns_zero(tmp_path):
    """`segqc run` stub returns 0 and performs no file I/O."""
    out_dir = tmp_path / "out"
    rc = main(["run", "--scan", "a", "--seg", "b", "--out", str(out_dir)])
    assert rc == 0
    # The stub must not create or modify the output directory.
    assert not out_dir.exists()
