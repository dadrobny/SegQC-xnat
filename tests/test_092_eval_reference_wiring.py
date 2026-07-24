"""Regression tests for item 092 -- threading a reference distribution
through the Stage-7 evaluation harness (``eval.harness.evaluate_case`` /
``evaluate_cohort``) and the calibration loop (``eval.calibrate.
calibrate_thresholds``).

Context. Items 089/090 (Stage 14) shipped reference-derived ``bounds`` /
``fragmentation`` defaults and a ``reference_delta`` rule that only fire once
a :class:`~segfacet.reference.schema.ReferenceDistribution` is attached to the
record fed to the rule engine -- which only ever happened via
``pipeline.run_qc_with_reference``. ``eval.harness.evaluate_case`` called
plain ``run_qc`` unconditionally, so every FPR measured through ``segfacet
evaluate`` (Stage 7/12/14's "Real VerSe GT" metric, and every
``calibrate_thresholds`` grid point) silently degraded to the hand-set
fallback -- item 090's shipped recalibration was never actually exercised by
the metric meant to validate it. This module proves the fix: an explicit
``reference=`` now reaches ``run_qc_with_reference`` and the reference-gated
rules actually fire, while the default (``reference=None``) is byte-for-byte
the original reference-blind behaviour (no regression for any pre-092
caller, incl. the Stage-5 golden harness and every existing eval/calibrate
test).
"""

from __future__ import annotations

import json
import shutil

import pytest

from segfacet.config import bundled_default_config
from segfacet.eval.calibrate import ThresholdAxis, calibrate_thresholds
from segfacet.eval.harness import EvaluationCase, evaluate_case, evaluate_cohort
from segfacet.reference import bundled_default_reference, write_artifact
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import CORPUS_DIR


def _clean_case(case_id="c-clean"):
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    return EvaluationCase(
        case_id=case_id,
        gt=spine.seg_img,
        expected={"expected_verdict": "pass"},
    )


def _outlier_case(case_id="c-outlier"):
    """Engineered to sit far outside the bundled default reference (mirrors
    test_049_reference_integration.py's ``_far_outlier_seg_and_reference``)."""
    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(20.0, 20.0, 20.0))
    return EvaluationCase(
        case_id=case_id,
        gt=spine.seg_img,
        expected={"expected_verdict": "pass"},
    )


# --------------------------------------------------------------------------- #
# evaluate_case / evaluate_cohort
# --------------------------------------------------------------------------- #


def test_reference_none_is_byte_identical_to_pre_092_behaviour():
    """No regression: reference=None (the default) yields the same outcome
    as calling evaluate_case with no reference kwarg at all."""
    case = _clean_case()
    cfg = bundled_default_config()

    explicit_none = evaluate_case(case, cfg, reference=None)
    omitted = evaluate_case(case, cfg)

    assert explicit_none.outcome == omitted.outcome
    assert explicit_none.to_dict() == omitted.to_dict()


def test_reference_delta_rule_fires_only_when_reference_is_attached():
    """The reference_delta rule contributes no findings under plain run_qc
    (reference=None); given a reference whose bands the case sits far
    outside, evaluate_case's outcome reflects a reference_delta-driven
    finding once reference= is supplied."""
    case = _outlier_case()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    without_reference = evaluate_case(case, cfg)
    with_reference = evaluate_case(case, cfg, reference=reference)

    # Reference-blind: the case's own outcome carries no reference-driven
    # verdict change signal we can inspect directly from CaseEvaluation, but
    # we can assert the two runs diverge -- the reference-aware run must not
    # be identical to the reference-blind run for an engineered outlier.
    assert with_reference.to_dict() != without_reference.to_dict()


def test_evaluate_cohort_forwards_reference_to_every_case():
    cases = [_clean_case("a"), _outlier_case("b")]
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    cohort = evaluate_cohort(cases, cfg, reference=reference)

    assert cohort.n_cases == 2
    # Cross-check: driving each case individually with the same reference
    # yields the same per-case outcomes evaluate_cohort produced.
    direct = [evaluate_case(c, cfg, reference=reference) for c in cases]
    assert [rec.outcome for rec in cohort.cases] == [d.outcome for d in direct]


def test_evaluate_cohort_reference_none_matches_omitted_kwarg():
    cases = [_clean_case("a"), _outlier_case("b")]
    cfg = bundled_default_config()

    explicit_none = evaluate_cohort(cases, cfg, reference=None)
    omitted = evaluate_cohort(cases, cfg)

    assert explicit_none.to_dict() == omitted.to_dict()


def test_evaluate_case_does_not_mutate_reference_or_case():
    import copy

    import numpy as np

    case = _outlier_case()
    cfg = bundled_default_config()
    reference = bundled_default_reference()
    reference_before = copy.deepcopy(reference)
    gt_data_before = np.array(case.gt.dataobj, copy=True)

    evaluate_case(case, cfg, reference=reference)

    assert reference == reference_before
    assert np.array_equal(np.asarray(case.gt.dataobj), gt_data_before)


def test_evaluate_case_stratum_and_percentiles_are_threaded_through(monkeypatch):
    """A custom stratum/percentile triple reaches run_qc_with_reference
    unchanged (mirrors test_049's AC1 custom-percentile assertion)."""
    captured = {}

    from segfacet.pipeline import run_qc_with_reference as _real

    def _spy(seg_img, config, reference, **kwargs):
        captured.update(kwargs)
        return _real(seg_img, config, reference, **kwargs)

    monkeypatch.setattr("segfacet.pipeline.run_qc_with_reference", _spy)

    case = _clean_case()
    cfg = bundled_default_config()
    reference = bundled_default_reference()

    evaluate_case(
        case, cfg, reference=reference, stratum="all", lower_pct=5, upper_pct=95
    )

    assert captured == {"stratum": "all", "lower_pct": 5, "upper_pct": 95}


# --------------------------------------------------------------------------- #
# calibrate_thresholds
# --------------------------------------------------------------------------- #


def test_calibrate_thresholds_forwards_reference_to_every_candidate():
    """A reference_delta axis has no effect under reference=None (the rule
    never fires without an attached reference), but does affect the outcome
    once reference= is supplied -- proving calibrate_thresholds actually
    forwards it into evaluate_cohort for every grid point."""
    cases = [_outlier_case("o1"), _outlier_case("o2")]
    cfg = bundled_default_config()
    reference = bundled_default_reference()
    axes = (
        ThresholdAxis(
            name="reference_delta.max_robust_z",
            rule_id="reference_delta",
            param_path=("max_robust_z",),
            values=(50.0,),
        ),
    )

    blind = calibrate_thresholds(cases, cfg, axes)
    aware = calibrate_thresholds(cases, cfg, axes, reference=reference)

    blind_fpr = blind.candidates[0].metrics.false_positive_rate
    aware_fpr = aware.candidates[0].metrics.false_positive_rate

    assert blind_fpr == pytest.approx(0.0)
    assert aware_fpr is not None
    assert aware_fpr != blind_fpr


def test_calibrate_thresholds_reference_none_matches_omitted_kwarg():
    cases = [_clean_case("a")]
    cfg = bundled_default_config()
    axes = (
        ThresholdAxis(
            name="bounds.lumbar.max_volume_mm3",
            rule_id="bounds",
            param_path=("lumbar", "max_volume_mm3"),
            values=(120_000.0,),
        ),
    )

    explicit_none = calibrate_thresholds(cases, cfg, axes, reference=None)
    omitted = calibrate_thresholds(cases, cfg, axes)

    assert (
        explicit_none.candidates[0].metrics.false_positive_rate
        == omitted.candidates[0].metrics.false_positive_rate
    )


# --------------------------------------------------------------------------- #
# ``segfacet evaluate --reference`` / ``--reference-artifact`` (CLI)
# --------------------------------------------------------------------------- #


def _write_reference_artifact(tmp_path):
    path = tmp_path / "reference.json"
    write_artifact(bundled_default_reference(), path)
    return path


def _write_manifest(tmp_path, cases, name="cohort.json"):
    dst = tmp_path / "fixtures"
    if not dst.exists():
        shutil.copytree(CORPUS_DIR / "fixtures", dst)
    manifest = {"manifest_version": 1, "cases": cases}
    path = tmp_path / name
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


_CLEAN_ONLY_COHORT = [
    {
        "case_id": "clean",
        "gt": "fixtures/clean_control_seg.nii.gz",
        "candidate": "fixtures/clean_control_seg.nii.gz",
        "expected": {"expected_verdict": "pass"},
    },
]


def test_cli_evaluate_without_reference_flag_defaults_off(tmp_path):
    """No --reference given: behaviour is unchanged from pre-092 (the flag
    is opt-in, not inherited from config's reference.enabled)."""
    from segfacet import cli

    manifest_path = _write_manifest(tmp_path, _CLEAN_ONLY_COHORT, name="off.json")
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        ["evaluate", "--cohort", str(manifest_path), "--out", str(out_dir)]
    )
    assert exit_code == 0

    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert report["metrics"]["false_positive_rate"] == 0.0


def test_cli_evaluate_reference_artifact_flag_is_accepted_and_runs(tmp_path):
    from segfacet import cli

    manifest_path = _write_manifest(tmp_path, _CLEAN_ONLY_COHORT, name="ref.json")
    artifact_path = _write_reference_artifact(tmp_path)
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--reference",
            "--reference-artifact",
            str(artifact_path),
        ]
    )
    assert exit_code == 0
    report = json.loads((out_dir / "eval_report.json").read_text(encoding="utf-8"))
    assert "false_positive_rate" in report["metrics"]


def test_cli_evaluate_reference_artifact_without_reference_flag_is_a_no_op(tmp_path):
    """--reference-artifact alone (no --reference) does not enable reference
    mode -- mirrors --reference-artifact's documented gating."""
    from segfacet import cli

    manifest_path = _write_manifest(tmp_path, _CLEAN_ONLY_COHORT, name="noop.json")
    artifact_path = _write_reference_artifact(tmp_path)
    out_dir_a = tmp_path / "out_a"
    out_dir_b = tmp_path / "out_b"

    cli.main(
        ["evaluate", "--cohort", str(manifest_path), "--out", str(out_dir_a)]
    )
    cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir_b),
            "--reference-artifact",
            str(artifact_path),
        ]
    )

    report_a = json.loads((out_dir_a / "eval_report.json").read_text(encoding="utf-8"))
    report_b = json.loads((out_dir_b / "eval_report.json").read_text(encoding="utf-8"))
    assert (
        report_a["metrics"]["false_positive_rate"]
        == report_b["metrics"]["false_positive_rate"]
    )


def test_cli_evaluate_nonexistent_reference_artifact_exits_1_with_no_traceback(
    tmp_path, capsys
):
    from segfacet import cli

    manifest_path = _write_manifest(tmp_path, _CLEAN_ONLY_COHORT, name="bad_ref.json")
    out_dir = tmp_path / "out"

    exit_code = cli.main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_dir),
            "--reference",
            "--reference-artifact",
            str(tmp_path / "does_not_exist.json"),
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() != ""
    assert "Traceback" not in captured.err
