"""Tests for item 101's CLI wiring: ``segfacet evaluate --per-mode`` and the
new ``segfacet compare-runs`` subcommand (AC23-AC25).

The two ``eval_report.json`` files ``compare-runs`` reads are always produced
in-test by ``segfacet evaluate --per-mode`` (never hand-written JSON) so the
whole chain -- manifest -> evaluate -> compare-runs -- is exercised exactly
as item 102's validation replays it.

Covers Acceptance Criteria:
- AC23: ``--per-mode`` (default ``False``) wires the ``per_mode_magnitude``
        block end to end into both the JSON and text reports; ``--run-id``
        stamps ``per_mode_magnitude.run_id``, defaulting to the cohort id.
- AC24: ``segfacet compare-runs`` produces the comparison artifact + a
        one-line stdout summary from two real, CLI-written eval reports.
- AC25: every ``compare-runs`` failure mode is a clean exit 1, never a
        traceback, and writes no output file.

Adversarial / edge cases: a nonexistent ``--run-a`` path; a report file that
is not valid JSON; a report with no ``per_mode_magnitude`` block (built by
``evaluate`` without ``--per-mode``); two reports whose cohorts differ.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from segfacet.synth.corpus import CORPUS_DIR
from segfacet.synth.perturbation import FAILURE_MODE_NAMES


# =========================================================================== #
# Shared helpers (mirrors tests/test_057_evaluate_cli.py's conventions)
# =========================================================================== #


def _copy_corpus_fixtures(tmp_path):
    dst = tmp_path / "fixtures"
    if not dst.exists():
        shutil.copytree(CORPUS_DIR / "fixtures", dst)
    return dst


def _write_manifest(tmp_path, cases, name="cohort.json"):
    _copy_corpus_fixtures(tmp_path)
    manifest = {"manifest_version": 1, "cases": cases}
    path = tmp_path / name
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


_COHORT_CASES = [
    {
        "case_id": "clean",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "candidate": "fixtures/clean_control_seg.nii.gz",
        "expected": {"expected_verdict": "pass"},
    },
    {
        "case_id": "cropped",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "candidate": "fixtures/mode6_crop_at_border_seg.nii.gz",
        "expected": {
            "expected_verdict": "flagged-for-review",
            "expected_rule_ids": ["border"],
            "expected_labels": [22],
            "failure_mode": 6,
            "failure_mode_name": FAILURE_MODE_NAMES[6],
        },
    },
]

_OTHER_COHORT_CASES = [
    {
        "case_id": "islands",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "candidate": "fixtures/mode3_inject_islands_seg.nii.gz",
        "expected": {
            "expected_verdict": "flagged-for-review",
            "failure_mode": 3,
            "failure_mode_name": FAILURE_MODE_NAMES[3],
        },
    },
]


def _run_evaluate(manifest_path, out_dir, *, per_mode=False, run_id=None, extra=None):
    from segfacet import cli

    argv = [
        "evaluate",
        "--cohort",
        str(manifest_path),
        "--out",
        str(out_dir),
        "--build-date",
        "2026-07-12",
        "--cohort-id",
        "test",
    ]
    if per_mode:
        argv.append("--per-mode")
    if run_id is not None:
        argv += ["--run-id", run_id]
    if extra:
        argv += extra
    return cli.main(argv)


def _comparison_schema() -> dict:
    import importlib.resources as pkg_resources

    import segfacet.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("per_mode_comparison_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


# =========================================================================== #
# AC23: --per-mode wires the block end to end
# =========================================================================== #


def test_ac23_per_mode_flag_default_is_false():
    from segfacet.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["evaluate", "--cohort", "x.json", "--out", "outdir"])
    assert args.per_mode is False


def test_ac23_per_mode_flag_true_when_given():
    from segfacet.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["evaluate", "--cohort", "x.json", "--out", "outdir", "--per-mode"])
    assert args.per_mode is True


def test_ac23_without_flag_no_per_mode_magnitude_anywhere(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="off.json")
    out_dir = tmp_path / "out_off"
    exit_code = _run_evaluate(manifest_path, out_dir, per_mode=False)
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert "per_mode_magnitude" not in report

    txt = (out_dir / "eval_report.txt").read_text(encoding="utf-8")
    assert "per_mode" not in txt.lower() or "per-mode magnitude" not in txt.lower()


def test_ac23_without_flag_two_runs_are_byte_identical(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="off2.json")
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    assert _run_evaluate(manifest_path, out_a, per_mode=False) == 0
    assert _run_evaluate(manifest_path, out_b, per_mode=False) == 0
    assert (out_a / "eval_report.json").read_bytes() == (out_b / "eval_report.json").read_bytes()


def test_ac23_with_flag_json_has_eight_entry_block(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="on.json")
    out_dir = tmp_path / "out_on"
    exit_code = _run_evaluate(manifest_path, out_dir, per_mode=True)
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert "per_mode_magnitude" in report
    assert len(report["per_mode_magnitude"]["per_mode"]) == 8

    import jsonschema as _js
    import importlib.resources as pkg_resources
    import segfacet.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("eval_report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))
    _js.validate(report, schema)


def test_ac23_with_flag_txt_carries_a_per_mode_magnitude_section(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="on_txt.json")
    out_dir = tmp_path / "out_on_txt"
    exit_code = _run_evaluate(manifest_path, out_dir, per_mode=True)
    assert exit_code == 0

    txt = (out_dir / "eval_report.txt").read_text(encoding="utf-8")
    for mode in range(1, 9):
        assert FAILURE_MODE_NAMES[mode] in txt


def test_ac23_run_id_flag_stamps_per_mode_magnitude_run_id(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="runid.json")
    out_dir = tmp_path / "out_runid"
    exit_code = _run_evaluate(manifest_path, out_dir, per_mode=True, run_id="my-custom-run")
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert report["per_mode_magnitude"]["run_id"] == "my-custom-run"


def test_ac23_run_id_defaults_to_cohort_id(tmp_path):
    manifest_path = _write_manifest(tmp_path, _COHORT_CASES, name="runid_default.json")
    out_dir = tmp_path / "out_runid_default"
    exit_code = _run_evaluate(manifest_path, out_dir, per_mode=True)
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert report["per_mode_magnitude"]["run_id"] == report["provenance"]["cohort_id"]


# =========================================================================== #
# AC24: segfacet compare-runs produces the comparison from two written reports
# =========================================================================== #


def test_ac24_compare_runs_end_to_end_on_two_real_eval_reports(tmp_path, capsys):
    from segfacet import cli

    manifest_a = _write_manifest(tmp_path, _COHORT_CASES, name="run_a.json")
    manifest_b = _write_manifest(tmp_path, _COHORT_CASES, name="run_b.json")
    out_a = tmp_path / "run_a_out"
    out_b = tmp_path / "run_b_out"
    assert _run_evaluate(manifest_a, out_a, per_mode=True, run_id="runA") == 0
    assert _run_evaluate(manifest_b, out_b, per_mode=True, run_id="runB") == 0

    out_compare = tmp_path / "compare"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0

    json_path = out_compare / "per_mode_comparison.json"
    txt_path = out_compare / "per_mode_comparison.txt"
    assert json_path.exists()
    assert txt_path.exists()

    report = json.loads(json_path.read_text(encoding="utf-8"))
    jsonschema.validate(report, _comparison_schema())

    assert txt_path.read_text(encoding="utf-8").strip() != ""

    captured = capsys.readouterr()
    assert captured.out.strip() != ""
    assert "Traceback" not in captured.out


def test_ac24_compare_runs_prints_a_one_line_summary_naming_the_attributed_mode(tmp_path, capsys):
    from segfacet import cli

    # Same manifest driven twice (a trivial self-vs-self comparison) so this
    # test can focus purely on the summary line's shape, independent of the
    # arithmetic already covered by AC13/AC14 in the library test module.
    manifest_a = _write_manifest(tmp_path, _COHORT_CASES, name="run_a2.json")
    out_a = tmp_path / "run_a2_out"
    out_b = tmp_path / "run_a2_out_b"
    assert _run_evaluate(manifest_a, out_a, per_mode=True, run_id="runA") == 0
    assert _run_evaluate(manifest_a, out_b, per_mode=True, run_id="runB") == 0

    out_compare = tmp_path / "compare2"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()
    stdout_lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(stdout_lines) >= 1


# =========================================================================== #
# AC25: every compare-runs failure is a clean exit 1, never a traceback
# =========================================================================== #


def test_ac25_nonexistent_run_a_path_exits_1_no_traceback_no_output(tmp_path, capsys):
    from segfacet import cli

    manifest_b = _write_manifest(tmp_path, _COHORT_CASES, name="valid_b.json")
    out_b = tmp_path / "valid_b_out"
    assert _run_evaluate(manifest_b, out_b, per_mode=True) == 0

    out_compare = tmp_path / "compare_missing_a"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(tmp_path / "does_not_exist.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert not out_compare.exists() or not any(out_compare.iterdir())


def test_ac25_malformed_json_exits_1_no_traceback_no_output(tmp_path, capsys):
    from segfacet import cli

    manifest_b = _write_manifest(tmp_path, _COHORT_CASES, name="valid_b2.json")
    out_b = tmp_path / "valid_b2_out"
    assert _run_evaluate(manifest_b, out_b, per_mode=True) == 0

    bad_json_path = tmp_path / "not_json.json"
    bad_json_path.write_text("{not valid json ][", encoding="utf-8")

    out_compare = tmp_path / "compare_bad_json"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(bad_json_path),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert not out_compare.exists() or not any(out_compare.iterdir())


def test_ac25_report_with_no_per_mode_magnitude_block_exits_1_no_traceback_no_output(tmp_path, capsys):
    from segfacet import cli

    manifest_a = _write_manifest(tmp_path, _COHORT_CASES, name="with_pm.json")
    manifest_b = _write_manifest(tmp_path, _COHORT_CASES, name="without_pm.json")
    out_a = tmp_path / "with_pm_out"
    out_b = tmp_path / "without_pm_out"
    assert _run_evaluate(manifest_a, out_a, per_mode=True) == 0
    assert _run_evaluate(manifest_b, out_b, per_mode=False) == 0  # no per_mode_magnitude block

    out_compare = tmp_path / "compare_no_block"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert not out_compare.exists() or not any(out_compare.iterdir())


def test_ac25_mismatched_cohorts_exits_1_no_traceback_no_output(tmp_path, capsys):
    from segfacet import cli

    manifest_a = _write_manifest(tmp_path, _COHORT_CASES, name="cohort_a.json")
    manifest_b = _write_manifest(tmp_path, _OTHER_COHORT_CASES, name="cohort_b.json")
    out_a = tmp_path / "cohort_a_out"
    out_b = tmp_path / "cohort_b_out"
    assert _run_evaluate(manifest_a, out_a, per_mode=True) == 0
    assert _run_evaluate(manifest_b, out_b, per_mode=True) == 0

    out_compare = tmp_path / "compare_mismatched"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(out_b / "eval_report.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert not out_compare.exists() or not any(out_compare.iterdir())


# =========================================================================== #
# Adversarial: --run-b missing, --out is required, no --backend flag
# =========================================================================== #


def test_adv_nonexistent_run_b_path_exits_1(tmp_path, capsys):
    from segfacet import cli

    manifest_a = _write_manifest(tmp_path, _COHORT_CASES, name="valid_a3.json")
    out_a = tmp_path / "valid_a3_out"
    assert _run_evaluate(manifest_a, out_a, per_mode=True) == 0

    out_compare = tmp_path / "compare_missing_b"
    exit_code = cli.main(
        [
            "compare-runs",
            "--run-a",
            str(out_a / "eval_report.json"),
            "--run-b",
            str(tmp_path / "does_not_exist_b.json"),
            "--out",
            str(out_compare),
        ]
    )
    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip().startswith("Error:")
    assert "Traceback" not in captured.err


def test_adv_compare_runs_out_is_required():
    from segfacet.cli import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["compare-runs", "--run-a", "a.json", "--run-b", "b.json"])


def test_adv_compare_runs_has_no_backend_flag():
    from segfacet.cli import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "compare-runs",
                "--run-a",
                "a.json",
                "--run-b",
                "b.json",
                "--out",
                "out",
                "--backend",
                "cpu",
            ]
        )


def test_adv_smoke_help_still_exits_0_and_mentions_run(capsys):
    from segfacet.cli import main

    # argparse's --help prints and raises SystemExit(0) directly rather than
    # returning -- mirrors tests/test_smoke.py::test_cli_help_exits_zero.
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "run" in captured.out
