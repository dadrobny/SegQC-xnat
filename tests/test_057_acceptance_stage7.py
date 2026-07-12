"""Stage-7 G3/G7 acceptance suite for item 057 -- the roadmap's literal
Stage-7 acceptance bar, proven end-to-end over the committed Stage-5
synthetic corpus (``tests/corpus/``) plus a purpose-built graded-quality
cohort. Completes **Stage 7 and Phase 1**.

Reproducing this suite's numbers from the command line, once item 057's
``segqc evaluate`` subcommand is wired up (item 057's CLI half; see
``tests/test_057_evaluate_cli.py``)::

    # A synth-independent evaluation-cohort manifest (a directory of GT /
    # candidate NIfTI pairs + an expectations manifest -- e.g. a mounted
    # VerSe GT / TotalSegmentator-vs-GT cohort):
    segqc evaluate --cohort <manifest.json> --out <dir> [--calibrate]

The three acceptance criteria this suite asserts on directly:

* **G3 -- GT passes at a high rate (low FPR).** AC8: the clean-GT control
  classifies as a true negative and the corpus cohort's false-positive rate
  is exactly ``0.0``.
* **G7 -- injected failures caught; flag rate / feature divergence
  correlates with DICE.** AC9: every *pipeline*-detectable Sec.6 failure
  mode (``mode2_fragment``, ``mode3_inject_islands``, ``mode5_remove_
  level``, ``mode6_crop_at_border``, ``mode7_sequence_break``) is caught at
  per-mode sensitivity ``1.0``. AC10/AC11: over a purpose-built graded-
  quality cohort, DICE-vs-flag correlates negatively and feature-
  divergence-vs-flag correlates positively.
* **Calibrated thresholds + metrics recorded; evaluation reproducible.**
  AC12: two independent runs of ``evaluate_cohort -> compute_cohort_
  metrics`` over the corpus cohort agree exactly, and so does the
  serialised report built from them. AC13: ``calibrate_thresholds`` over a
  small explicit axis grid recovers a feasible best candidate whose chosen
  thresholds round-trip through ``record_calibrated_config`` ->
  ``load_config``, and the achieved metrics surface in the evaluation
  report's ``calibration`` block.

**Reconstructed-record modes 1/4/8 are deliberately NOT asserted at
sensitivity 1.0** (mirrors item 049's own acceptance-suite decision): items
040/049 document ``mode1_displace``, ``mode4_relabel_swap``, and
``mode8_force_overlap`` as structurally invisible to the plain ``run_qc``
pipeline (a single-integer label map cannot encode an overlap; the
interpolating/ascending-label spline refit absorbs the displacement/swap).
The corpus cohort here runs the plain pipeline on each candidate, so those
three cases classify ``FALSE_NEGATIVE`` -- overall cohort sensitivity is
consequently ``5/8``, not ``1.0``. This is intentional, not a bug: over-
claiming detection on the reconstructed modes would misrepresent the
system's real, honest capability.

All tests are deterministic, CPU-only, and portable (no network, no
absolute paths, no wall clock).
"""

from __future__ import annotations

import functools

import pytest

from segqc.config import bundled_default_config, load_config
from segqc.eval.calibrate import ThresholdAxis, calibrate_thresholds
from segqc.eval.harness import EvaluationCase, evaluate_cohort
from segqc.eval.metrics import compute_cohort_metrics
from segqc.eval.outcome import Outcome
from segqc.eval.report import (
    EvaluationProvenance,
    build_evaluation_report,
    record_calibrated_config,
    serialize_evaluation_report_json,
)
from segqc.io import SegQCInputError
from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.corpus import load_manifest
from segqc.synth.coverage_border_overlap import CropAtBorderPerturbation
from segqc.synth.perturbation import FAILURE_MODE_NAMES
from segqc.synth.regression import loaded_seg_image

#: Sec.6 modes the plain pipeline is documented to catch (Assumptions).
_PIPELINE_DETECTABLE_MODES = (2, 3, 5, 6, 7)
#: Sec.6 modes documented as structurally invisible to the plain pipeline.
_RECONSTRUCTED_RECORD_MODES = (1, 4, 8)


# =========================================================================== #
# Corpus-cohort helper (per the item spec's Testing Strategy)
# =========================================================================== #


def _build_corpus_cohort():
    """Build the acceptance cohort from the committed corpus manifest: GT =
    ``clean_control``'s seg fixture, candidate = each case's own seg fixture
    (``clean_control`` itself uses ``candidate = gt``, DICE 1.0, expected
    pass), ``expected`` = the manifest case dict (the exact
    ``Expectation.to_dict()`` / manifest-case shape ``classify_outcome``
    consumes)."""
    manifest_cases = load_manifest()["cases"]
    clean_case = next(c for c in manifest_cases if c["case_id"] == "clean_control")
    gt_img = loaded_seg_image(clean_case)

    eval_cases = []
    for case in manifest_cases:
        candidate_img = (
            gt_img if case["case_id"] == "clean_control" else loaded_seg_image(case)
        )
        eval_cases.append(
            EvaluationCase(
                case_id=case["case_id"],
                gt=gt_img,
                candidate=candidate_img,
                expected=case,
            )
        )
    return eval_cases


@functools.lru_cache(maxsize=1)
def _corpus_cohort_evaluation():
    return evaluate_cohort(_build_corpus_cohort(), bundled_default_config())


@functools.lru_cache(maxsize=1)
def _corpus_cohort_metrics():
    return compute_cohort_metrics(
        _corpus_cohort_evaluation(), failure_modes=FAILURE_MODE_NAMES
    )


def _per_mode(metrics, mode):
    return next(m for m in metrics.per_mode if m.failure_mode == mode)


# =========================================================================== #
# AC8: G3 -- clean GT passes; FPR is zero
# =========================================================================== #


def test_ac8_clean_control_is_true_negative():
    cohort = _corpus_cohort_evaluation()
    clean_record = next(c for c in cohort.cases if c.case_id == "clean_control")
    assert clean_record.outcome.outcome is Outcome.TRUE_NEGATIVE


def test_ac8_false_positive_rate_is_zero():
    metrics = _corpus_cohort_metrics()
    assert metrics.false_positive_rate == 0.0


# =========================================================================== #
# AC9: G7 -- pipeline-detectable failures caught at sensitivity 1.0
# =========================================================================== #


@pytest.mark.parametrize("mode", _PIPELINE_DETECTABLE_MODES)
def test_ac9_pipeline_detectable_mode_sensitivity_is_one(mode):
    metrics = _corpus_cohort_metrics()
    entry = _per_mode(metrics, mode)
    assert entry.n_cases > 0
    assert entry.sensitivity == 1.0


@pytest.mark.parametrize("mode", _RECONSTRUCTED_RECORD_MODES)
def test_reconstructed_record_modes_are_not_over_claimed_as_caught(mode):
    """Documents (does not over-claim) the Assumptions' honesty guarantee:
    modes 1/4/8 are structurally invisible to the plain pipeline, so their
    designated rule never fires here and per-mode sensitivity is 0.0, not
    1.0 -- distinct from AC9's positive claim for modes 2/3/5/6/7."""
    metrics = _corpus_cohort_metrics()
    entry = _per_mode(metrics, mode)
    assert entry.n_cases > 0
    assert entry.sensitivity == 0.0


def test_overall_corpus_sensitivity_is_five_of_eight_not_over_claimed():
    """Overall cohort sensitivity (TP / (TP + FN)) is 5/8 -- the five
    pipeline-detectable failures caught, the three reconstructed-record
    modes missed -- not 1.0 (Assumptions)."""
    metrics = _corpus_cohort_metrics()
    assert metrics.sensitivity == pytest.approx(5.0 / 8.0)


# =========================================================================== #
# AC10/AC11: G7 -- DICE-vs-flag and feature-divergence-vs-flag correlation
# signs over a purpose-built graded-quality cohort (Assumptions)
# =========================================================================== #


#: Increasing crop_depth -> monotonically shrinking retained candidate
#: volume -> monotonically decreasing DICE-vs-GT, while BorderRule fires
#: (flags) every degraded candidate regardless of depth.
_GRADED_CROP_DEPTHS = (1, 4, 8, 12, 16)


def _build_graded_quality_cohort():
    """A clean-GT positive control (unflagged, DICE 1.0) plus several
    candidates of the *same* single-level GT, degraded at increasing
    ``crop_at_border`` severity (Assumptions' recommended construction) --
    designed to exhibit the roadmap's DICE-vs-flag / divergence-vs-flag
    relationship cleanly, unlike the full 9-case corpus cohort (whose mixed
    fragment/inject/reconstructed-mode DICE movements yield an ambiguous
    sign -- see the Assumptions)."""
    base = build_clean_spine(levels=["L3"])
    gt_img = base.seg_img
    target_label = base.labels[0]

    cases = [
        EvaluationCase(
            case_id="control_clean",
            gt=gt_img,
            candidate=gt_img,
            expected={"expected_verdict": "pass"},
        )
    ]
    for i, depth in enumerate(_GRADED_CROP_DEPTHS):
        operator = CropAtBorderPerturbation(
            target_label=target_label, face="anterior", crop_depth=depth
        )
        result = operator.apply(gt_img, seed=0)
        cases.append(
            EvaluationCase(
                case_id=f"degraded_{i}",
                gt=gt_img,
                candidate=result.labelmap,
                expected={"expected_verdict": "flagged-for-review"},
            )
        )
    return cases


@functools.lru_cache(maxsize=1)
def _graded_quality_evaluation_and_metrics():
    cohort = evaluate_cohort(_build_graded_quality_cohort(), bundled_default_config())
    metrics = compute_cohort_metrics(cohort)
    return cohort, metrics


def test_graded_quality_cohort_dice_is_monotonically_decreasing():
    """Precondition for AC10/AC11 (Assumptions): DICE-vs-GT decreases
    monotonically with crop severity across the graded-quality cohort --
    verified empirically here rather than merely asserted."""
    cohort, _metrics = _graded_quality_evaluation_and_metrics()
    dice_by_case = {c.case_id: c.overlap.mean_dice for c in cohort.cases}
    ordered_dice = [dice_by_case["control_clean"]] + [
        dice_by_case[f"degraded_{i}"] for i in range(len(_GRADED_CROP_DEPTHS))
    ]
    for earlier, later in zip(ordered_dice, ordered_dice[1:]):
        assert later < earlier, (
            f"DICE series is not monotonically decreasing: {ordered_dice!r}"
        )


def test_graded_quality_cohort_every_degraded_candidate_is_flagged():
    """Precondition for AC10/AC11: every degraded candidate is actually
    flagged (BorderRule fires regardless of crop depth) and the clean
    control is not -- otherwise the flag column would be zero-variance and
    both correlations would degenerate to ``None``."""
    cohort, _metrics = _graded_quality_evaluation_and_metrics()
    flagged_by_case = {c.case_id: c.outcome.actual_flagged for c in cohort.cases}
    assert flagged_by_case["control_clean"] is False
    for i in range(len(_GRADED_CROP_DEPTHS)):
        assert flagged_by_case[f"degraded_{i}"] is True


def test_ac10_dice_vs_flag_correlation_is_negative():
    _cohort, metrics = _graded_quality_evaluation_and_metrics()
    assert metrics.dice_vs_flag.coefficient is not None
    assert metrics.dice_vs_flag.coefficient < 0


def test_ac11_feature_divergence_vs_flag_correlation_is_positive():
    _cohort, metrics = _graded_quality_evaluation_and_metrics()
    assert metrics.feature_divergence_vs_flag.coefficient is not None
    assert metrics.feature_divergence_vs_flag.coefficient > 0


# =========================================================================== #
# AC12: evaluation is deterministic
# =========================================================================== #


def test_ac12_cohort_metrics_are_equal_across_two_runs():
    config = bundled_default_config()
    cases = _build_corpus_cohort()

    metrics_a = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=FAILURE_MODE_NAMES
    )
    metrics_b = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=FAILURE_MODE_NAMES
    )
    assert metrics_a.to_dict() == metrics_b.to_dict()


def test_ac12_serialized_report_is_identical_across_two_runs():
    config = bundled_default_config()
    cases = _build_corpus_cohort()
    provenance = EvaluationProvenance(
        cohort_id="det",
        cohort_size=len(cases),
        config_version=config.schema_version,
        build_date="2026-07-12",
    )

    metrics_a = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=FAILURE_MODE_NAMES
    )
    metrics_b = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=FAILURE_MODE_NAMES
    )
    report_a = serialize_evaluation_report_json(
        build_evaluation_report(metrics_a, provenance)
    )
    report_b = serialize_evaluation_report_json(
        build_evaluation_report(metrics_b, provenance)
    )
    assert report_a == report_b


# =========================================================================== #
# AC13: calibrated thresholds + achieved metrics are recorded
# =========================================================================== #


def test_ac13_calibration_recovers_a_feasible_best_candidate(tmp_path):
    """Restricts the objective's per-mode floor check to the five
    pipeline-detectable Sec.6 modes (Assumptions): modes 1/4/8 never meet
    their designated rule under the plain pipeline regardless of the swept
    ``reference_delta`` threshold (a separate rule family entirely), so
    including them in the floor check would make every grid candidate
    infeasible by construction -- not a meaningful calibration outcome."""
    config = bundled_default_config()
    cases = _build_corpus_cohort()
    axes = (
        ThresholdAxis(
            name="reference_delta.max_robust_z",
            rule_id="reference_delta",
            param_path=("max_robust_z",),
            values=(3.0, 3.5),
        ),
    )

    result = calibrate_thresholds(
        cases, config, axes, failure_modes=_PIPELINE_DETECTABLE_MODES
    )

    assert result.best is not None
    assert result.feasible is True


def test_ac13_recorded_config_round_trips_through_load_config(tmp_path):
    config = bundled_default_config()
    cases = _build_corpus_cohort()
    axes = (
        ThresholdAxis(
            name="reference_delta.max_robust_z",
            rule_id="reference_delta",
            param_path=("max_robust_z",),
            values=(3.0, 3.5),
        ),
    )
    result = calibrate_thresholds(
        cases, config, axes, failure_modes=_PIPELINE_DETECTABLE_MODES
    )
    assert result.best is not None

    config_path = tmp_path / "calibrated.yaml"
    written_path = record_calibrated_config(config, result, axes, config_path)
    assert written_path == config_path

    reloaded = load_config(config_path)
    assert reloaded.rule_param(
        "reference_delta", "max_robust_z", None
    ) == result.best.assignment["reference_delta.max_robust_z"]


def test_ac13_report_calibration_block_carries_achieved_metrics(tmp_path):
    config = bundled_default_config()
    cases = _build_corpus_cohort()
    axes = (
        ThresholdAxis(
            name="reference_delta.max_robust_z",
            rule_id="reference_delta",
            param_path=("max_robust_z",),
            values=(3.0, 3.5),
        ),
    )
    result = calibrate_thresholds(
        cases, config, axes, failure_modes=_PIPELINE_DETECTABLE_MODES
    )
    assert result.best is not None

    metrics = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=_PIPELINE_DETECTABLE_MODES
    )
    provenance = EvaluationProvenance(
        cohort_id="calib",
        cohort_size=metrics.n_cases,
        config_version=config.schema_version,
        build_date="2026-07-12",
    )
    report = build_evaluation_report(metrics, provenance, calibration=result)

    calibration_block = report["calibration"]
    assert calibration_block["best"] is not None
    best_metrics = calibration_block["best"]["metrics"]
    assert "false_positive_rate" in best_metrics
    assert "per_mode" in best_metrics


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_empty_cohort_no_crash():
    cohort = evaluate_cohort([], bundled_default_config())
    metrics = compute_cohort_metrics(cohort)
    assert metrics.n_cases == 0
    assert metrics.false_positive_rate is None


def test_adversarial_candidate_less_case_excluded_from_correlation_pair_count():
    base = build_clean_spine(levels=["L3"])
    gt_only_case = EvaluationCase(
        case_id="gt_only", gt=base.seg_img, expected={"expected_verdict": "pass"}
    )
    with_candidate_case = EvaluationCase(
        case_id="with_candidate",
        gt=base.seg_img,
        candidate=base.seg_img,
        expected={"expected_verdict": "pass"},
    )
    cohort = evaluate_cohort(
        [gt_only_case, with_candidate_case], bundled_default_config()
    )
    metrics = compute_cohort_metrics(cohort)

    gt_only_record = next(c for c in cohort.cases if c.case_id == "gt_only")
    assert gt_only_record.overlap is None
    # Only the candidate-bearing case contributes a usable (x, y) pair --
    # the missing-overlap case is dropped, not counted as a zero.
    assert metrics.dice_vs_flag.n == 1


def test_adversarial_duplicate_case_id_raises_segqc_input_error():
    base = build_clean_spine(levels=["L3"])
    case_a = EvaluationCase(
        case_id="dup", gt=base.seg_img, expected={"expected_verdict": "pass"}
    )
    case_b = EvaluationCase(
        case_id="dup", gt=base.seg_img, expected={"expected_verdict": "pass"}
    )
    with pytest.raises(SegQCInputError):
        evaluate_cohort([case_a, case_b], bundled_default_config())
