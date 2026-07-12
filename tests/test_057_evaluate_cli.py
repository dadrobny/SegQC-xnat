"""Tests for the evaluation-cohort manifest loader and the ``segqc evaluate``
CLI subcommand (item 057, AC1-AC7 -- the CLI/cohort-spec half of Stage-7's
final integration item).

``segqc.eval.cohort`` does not exist yet at the time this file is written;
its names (``load_cohort_manifest``) are imported **locally inside each test
function** (mirroring ``tests/test_054_metrics.py`` / ``tests/test_055_
calibrate.py``'s / ``tests/test_056_eval_report.py``'s treatment of their
then-new modules) so this file can still be collected before the module is
implemented. The ``segqc evaluate`` subcommand itself is likewise not yet
wired into ``segqc.cli``'s parser -- ``cli.main([...])`` calls below will
fail until item 057's ``_handle_evaluate`` handler is implemented; this is
expected at test-authoring time.

Running a real evaluation once implemented::

    segqc evaluate --cohort <manifest.json> --out <dir> [--calibrate]

The evaluation-cohort manifest is a small, synth-independent JSON document
(pinned in the item 057 spec's Assumptions): a top-level ``"cases"`` array,
each entry naming a ``case_id``, a ``gt`` segmentation path, an optional
``candidate`` path, an ``expected`` mapping (``Expectation.to_dict()`` /
``tests/corpus`` manifest-case shape, requiring at least
``expected_verdict``), and optional ``spacing``/``metadata``. ``gt``/
``candidate`` paths are resolved relative to the manifest file's own
directory -- exactly like the Stage-5 corpus manifest's ``seg_fixture``.

Every cohort manifest built here reuses the already-committed Stage-5
synthetic corpus fixtures (``tests/corpus/fixtures/*_seg.nii.gz``), copied
into a fresh ``tmp_path`` so the "resolved relative to the manifest's
directory" contract is exercised against real files rather than merely
asserted about.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths hard-coded, no wall clock -- ``--build-date`` is always caller-supplied
per the reproducibility Assumption).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from segqc.io import SegQCInputError
from segqc.synth.corpus import CORPUS_DIR
from segqc.synth.perturbation import FAILURE_MODE_NAMES


# =========================================================================== #
# Shared helpers
# =========================================================================== #


def _copy_corpus_fixtures(tmp_path):
    """Copy the committed corpus fixtures into ``tmp_path/fixtures`` so a
    cohort manifest written at ``tmp_path`` can reference them by a path
    relative to the manifest's own directory."""
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


def _eval_report_schema():
    import importlib.resources as pkg_resources

    import segqc.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("eval_report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


# A small, fast, real end-to-end cohort: one clean-control (self-vs-self,
# expected pass) + one border-crop failure caught by BorderRule -- used
# throughout AC3-AC7 so every ``segqc evaluate`` invocation stays cheap.
_SMALL_COHORT_CASES = [
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


# =========================================================================== #
# AC1: cohort-manifest loader builds EvaluationCases
# =========================================================================== #


def test_ac1_loader_builds_evaluation_cases_in_order_with_resolved_paths(tmp_path):
    from segqc.eval.cohort import load_cohort_manifest

    _copy_corpus_fixtures(tmp_path)
    case_with_candidate = {
        "case_id": "c1",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "candidate": "fixtures/mode6_crop_at_border_seg.nii.gz",
        "spacing": [1.0, 1.0, 1.0],
        "expected": {
            "expected_verdict": "flagged-for-review",
            "expected_rule_ids": ["border"],
            "expected_labels": [22],
            "failure_mode": 6,
            "failure_mode_name": FAILURE_MODE_NAMES[6],
        },
        "metadata": {"note": "x"},
    }
    case_without_candidate = {
        "case_id": "c2",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "expected": {"expected_verdict": "pass"},
    }
    manifest_path = _write_manifest(
        tmp_path, [case_with_candidate, case_without_candidate]
    )

    cases = load_cohort_manifest(manifest_path)

    assert [c.case_id for c in cases] == ["c1", "c2"]

    first, second = cases
    assert Path(first.gt).samefile(tmp_path / "fixtures" / "clean_control_seg.nii.gz")
    assert Path(first.candidate).samefile(
        tmp_path / "fixtures" / "mode6_crop_at_border_seg.nii.gz"
    )
    assert dict(first.expected) == case_with_candidate["expected"]
    assert first.spacing == (1.0, 1.0, 1.0)
    assert dict(first.metadata) == {"note": "x"}

    assert second.candidate is None
    assert Path(second.gt).samefile(tmp_path / "fixtures" / "clean_control_seg.nii.gz")
    assert dict(second.expected) == {"expected_verdict": "pass"}


# =========================================================================== #
# AC2: the loader rejects malformed cohort manifests cleanly
# =========================================================================== #


def _ok_case():
    return {
        "case_id": "ok",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "expected": {"expected_verdict": "pass"},
    }


@pytest.mark.parametrize(
    "build_manifest",
    [
        pytest.param(lambda ok: {"manifest_version": 1}, id="missing-cases-array"),
        pytest.param(
            lambda ok: {
                "cases": [{k: v for k, v in ok.items() if k != "case_id"}]
            },
            id="case-missing-case_id",
        ),
        pytest.param(
            lambda ok: {"cases": [{k: v for k, v in ok.items() if k != "gt"}]},
            id="case-missing-gt",
        ),
        pytest.param(
            lambda ok: {
                "cases": [{k: v for k, v in ok.items() if k != "expected"}]
            },
            id="case-missing-expected",
        ),
        pytest.param(
            lambda ok: {"cases": [{**ok, "expected": {}}]},
            id="expected-missing-expected_verdict",
        ),
        pytest.param(
            lambda ok: {"cases": [ok, dict(ok)]},
            id="duplicate-case_id",
        ),
        pytest.param(
            lambda ok: {
                "cases": [{**ok, "gt": "fixtures/does_not_exist_seg.nii.gz"}]
            },
            id="gt-path-does-not-exist",
        ),
        pytest.param(
            lambda ok: {
                "cases": [
                    {**ok, "candidate": "fixtures/does_not_exist_seg.nii.gz"}
                ]
            },
            id="candidate-path-does-not-exist",
        ),
    ],
)
def test_ac2_malformed_manifest_raises_segqc_input_error(tmp_path, build_manifest):
    from segqc.eval.cohort import load_cohort_manifest

    _copy_corpus_fixtures(tmp_path)
    manifest = build_manifest(_ok_case())
    manifest_path = tmp_path / "malformed.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SegQCInputError):
        load_cohort_manifest(manifest_path)


# =========================================================================== #
# AC3/AC4: segqc evaluate runs end-to-end and writes a schema-valid report
# =========================================================================== #


def test_ac3_evaluate_runs_end_to_end_and_writes_both_reports(tmp_path):
    from segqc import cli

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac3.json")
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        [
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
    )

    assert exit_code == 0
    assert (out_dir / "eval_report.json").exists()
    assert (out_dir / "eval_report.txt").exists()


def test_ac4_written_json_report_is_schema_valid_and_carries_metrics(tmp_path):
    from segqc import cli

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac4.json")
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        [
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
    )
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    jsonschema.validate(report, _eval_report_schema())

    assert "provenance" in report
    metrics = report["metrics"]
    assert "false_positive_rate" in metrics
    assert "per_mode" in metrics
    assert "dice_vs_flag" in metrics
    assert "feature_divergence_vs_flag" in metrics


# =========================================================================== #
# AC5: --calibrate records a round-tripping calibrated config + report block
# =========================================================================== #


def test_ac5_calibrate_writes_config_and_calibration_block(tmp_path):
    from segqc import cli
    from segqc.config import load_config

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac5.json")
    out_dir = tmp_path / "out_calibrate"

    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--calibrate",
            "--build-date",
            "2026-07-12",
            "--cohort-id",
            "test",
        ]
    )
    assert exit_code == 0

    config_path = out_dir / "calibrated_config.yaml"
    assert config_path.exists()
    reloaded = load_config(config_path)
    assert reloaded.schema_version

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert "calibration" in report


def test_ac5_without_calibrate_writes_neither_config_nor_calibration_block(tmp_path):
    from segqc import cli

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac5b.json")
    out_dir = tmp_path / "out_plain"

    exit_code = cli.main(
        [
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
    )
    assert exit_code == 0

    assert not (out_dir / "calibrated_config.yaml").exists()
    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert "calibration" not in report


# =========================================================================== #
# AC6: segqc evaluate is reproducible
# =========================================================================== #


def test_ac6_two_identical_invocations_write_byte_identical_reports(tmp_path):
    from segqc import cli

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac6.json")
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    common_args = [
        "evaluate",
        "--cohort",
        str(manifest_path),
        "--build-date",
        "2026-07-12",
        "--cohort-id",
        "repro",
    ]

    assert cli.main(common_args + ["--out", str(out_a)]) == 0
    assert cli.main(common_args + ["--out", str(out_b)]) == 0

    bytes_a = (out_a / "eval_report.json").read_bytes()
    bytes_b = (out_b / "eval_report.json").read_bytes()
    assert bytes_a == bytes_b


# =========================================================================== #
# AC7: caller-input errors exit 1 cleanly
# =========================================================================== #


def test_ac7_nonexistent_cohort_path_exits_1_with_no_traceback(tmp_path, capsys):
    from segqc import cli

    out_dir = tmp_path / "out"
    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(tmp_path / "does_not_exist.json"),
            "--out",
            str(out_dir),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out


def test_ac7_malformed_config_path_exits_1_with_no_traceback(tmp_path, capsys):
    from segqc import cli

    manifest_path = _write_manifest(tmp_path, _SMALL_COHORT_CASES, name="ac7.json")
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--config",
            str(tmp_path / "no_such_config.yaml"),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
