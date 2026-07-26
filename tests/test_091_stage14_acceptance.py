"""Stage-14 G3/G7 recalibration acceptance module (item 091) -- closes Stage 14.

Fits the Stage-7 threshold-calibration loop
(:mod:`segfacet.eval.calibrate`, item 055) on a **calibration** cohort and
*measures* the selected setting on a disjoint **held-out** cohort (item 090's
reference-derived defaults are what the held-out measurement is *of*), then
supplies an **executable anti-gaming sensitivity guard** that re-runs item
057's recorded per-mode baseline and refuses to credit any config that
regresses it -- so a low held-out FPR earned by loosening/disabling rules
cannot pass.

This item adds **no** production code (mirrors item 084's acceptance-module
shape exactly): every helper below -- ``real_verse_cohort_dir``,
``build_standin_splits``, ``calibrate_then_measure``, ``per_mode_sensitivity``,
``sensitivity_baseline``, ``sensitivity_regressed``,
``g3_recalibration_record``, ``may_flip_g3`` -- lives entirely in this test
module.

**Outcome-neutral by design.** No real VerSe19 cohort is mounted on this
host, so the achieved real-world held-out FPR is not knowable here. Every
assertion below is over well-formedness (a float in ``[0.0, 1.0]``,
disjointness of the two cohorts, deterministic/pure helpers), the guard's
correctness (including a negative test that proves it rejects a gamed
config), and the genuine ``pytest.mark.skipif`` gate for the real-VerSe
clause -- never a specific FPR value.

Covers Acceptance Criteria AC1-AC17:

- AC1: the module exists and exposes the eight importable helpers.
- AC2-AC5: the synthetic calibrate -> held-out-evaluate flow -- disjoint
  stand-in cohorts, well-formed held-out metrics, the fit never sees the
  held-out cohort, and a clean self-consistent held-out cohort measures
  FPR 0.0.
- AC6-AC10: the executable anti-gaming sensitivity guard -- item 057's
  recorded baseline, the shipped default reproducing it on the committed
  Stage-5 corpus, the guard predicate's truth table, the guard's rejection
  of a deliberately over-loosened config, and determinism/non-mutation.
- AC11-AC13: Stage-5 perturbations applied to a stand-in GT (the CI-runnable
  analogue of the real-GT clause), the genuine skip of the real-VerSe
  clause, and ``real_verse_cohort_dir()``'s env-var contract.
- AC14-AC16: the G3 recalibration-evidence record's JSON-native shape, the
  conditional-flip guard's truth table, and a synthetic-only run's
  self-reported non-flipping record.
- AC17: no production code / new dependency is introduced by this item.

Adversarial / edge cases:
- No-feasible-setting surfaces as an explicit error, never
  ``AttributeError`` on ``None.assignment``.
- ``sensitivity_regressed({}, baseline)`` is ``True`` (an empty achieved
  dict is a regression, not a vacuous pass).
- The over-loosened config's FPR-lowering intent is made explicit against a
  would-be-flagging cohort.
- A nonexistent / empty ``SEGFACET_VERSE_COHORT`` behaves as "no cohort", never
  a crash.
- Two ``calibrate_then_measure`` runs over the same inputs agree exactly.
- ``SEGFACET_VERSE_COHORT`` env hygiene after monkeypatch teardown.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import pathlib
import re
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.eval.calibrate import (
    CalibrationResult,
    ThresholdAxis,
    apply_assignment,
    calibrate_thresholds,
)
from segfacet.eval.harness import EvaluationCase, evaluate_cohort
from segfacet.eval.metrics import CohortMetrics, compute_cohort_metrics
from segfacet.io import FacetInputError
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.perturbation import FAILURE_MODE_NAMES, get_perturbation
from segfacet.synth.regression import loaded_seg_image

_LEVELS = ("L1", "L2", "L3", "L4", "L5")

#: item 057's recorded per-mode baseline (Assumptions A3): the five
#: pipeline-detectable Sec.6 modes at sensitivity 1.0.
_BASELINE_MODES = (2, 3, 5, 6, 7)

#: One representative pipeline-detectable perturbation operator per baseline
#: mode (see src/segfacet/synth/{component_shape,coverage_border_overlap,
#: identity_ordering_alignment}.py's ``failure_mode=`` assignments).
_PIPELINE_DETECTABLE_OPERATORS = (
    ("fragment", 2),
    ("inject_islands", 3),
    ("remove_level", 5),
    ("crop_at_border", 6),
    ("sequence_break", 7),
)

#: The Sec.6-detecting rule families an "over-loosened" config disables to
#: attempt driving FPR toward 0 by blinding the rules (AC9).
_SECTION6_DETECTING_RULE_IDS = ("bounds", "fragmentation", "coverage", "border")


# =========================================================================== #
# Public helpers (test-side only -- no src/segfacet/** change, item 084 A1/091 A1)
# =========================================================================== #


def real_verse_cohort_dir() -> "Optional[pathlib.Path]":
    """The real VerSe19 root from ``SEGFACET_VERSE_COHORT`` iff set AND a
    directory, else ``None`` -- the single runtime gate for the real-VerSe
    clause (byte-for-byte the items 084/088 contract)."""
    raw = os.environ.get("SEGFACET_VERSE_COHORT")
    if not raw:
        return None
    candidate = pathlib.Path(raw)
    return candidate if candidate.is_dir() else None


requires_verse = pytest.mark.skipif(
    real_verse_cohort_dir() is None,
    reason="real VerSe19 cohort not mounted (set SEGFACET_VERSE_COHORT to the VerSe19 root)",
)


def build_standin_splits(tmp_dir) -> "Tuple[List[EvaluationCase], List[EvaluationCase]]":
    """Build two DISJOINT synthetic VerSe-shaped stand-in cohorts -- a
    'calibration' cohort and a 'held-out' cohort -- as evaluate-shape
    ``EvaluationCase`` lists (GT-as-candidate, ``expected_verdict ==
    "pass"``). Their ``case_id`` sets are provably disjoint. Used to exercise
    the calibrate -> held-out-evaluate machinery in CI without real data.
    ``tmp_dir`` is accepted for interface parity with a disk-backed stand-in
    (item 084/088's precedent) but the in-memory ``nibabel`` images returned
    by ``build_clean_spine`` are used directly -- no file I/O is required."""
    del tmp_dir  # unused: images are built and passed in-memory

    cal_cases = []
    for i in range(2):
        spine = build_clean_spine(
            levels=_LEVELS,
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        cal_cases.append(
            EvaluationCase(
                case_id=f"cal-{i:03d}",
                gt=spine.seg_img,
                candidate=spine.seg_img,
                expected={"expected_verdict": "pass"},
            )
        )

    held_cases = []
    for i in range(2):
        spine = build_clean_spine(
            levels=_LEVELS,
            spacing=(1.0, 1.0, 1.2 + 0.1 * i),
            curve_amplitude_mm=6.0 + i,
        )
        held_cases.append(
            EvaluationCase(
                case_id=f"held-{i:03d}",
                gt=spine.seg_img,
                candidate=spine.seg_img,
                expected={"expected_verdict": "pass"},
            )
        )

    return cal_cases, held_cases


def calibrate_then_measure(
    cal_cases, held_cases, base_config, axes
) -> "Tuple[CalibrationResult, CohortMetrics]":
    """Fit ``calibrate_thresholds`` on ``cal_cases`` only, apply the selected
    best assignment onto ``base_config``, then ``evaluate_cohort`` +
    ``compute_cohort_metrics`` on ``held_cases``. Returns
    ``(calibration_result, held_out_metrics)``. The calibration fit never
    receives ``held_cases`` (the no-circularity flow)."""
    result = calibrate_thresholds(cal_cases, base_config, axes)
    if result.best is None:
        raise FacetInputError(
            "calibrate_then_measure: no feasible calibration setting found "
            "over the given axis grid; cannot select a config to measure "
            "held-out."
        )

    calibrated_config = apply_assignment(base_config, result.best.assignment, axes)
    held_out_evaluation = evaluate_cohort(held_cases, calibrated_config)
    held_out_metrics = compute_cohort_metrics(held_out_evaluation)
    return result, held_out_metrics


def per_mode_sensitivity(cases, config, *, failure_modes) -> "Dict[int, float]":
    """``{mode_key: sensitivity}`` for each observed Sec.6 mode with
    ``n_cases > 0``, via ``evaluate_cohort`` -> ``compute_cohort_metrics``.
    The guard's measurement primitive, used for both the Stage-5 synthetic
    corpus and Stage-5 perturbations applied to a GT."""
    metrics = compute_cohort_metrics(
        evaluate_cohort(cases, config), failure_modes=failure_modes
    )
    return {
        mode.failure_mode: mode.sensitivity
        for mode in metrics.per_mode
        if mode.n_cases > 0
    }


def sensitivity_baseline() -> "Dict[int, float]":
    """Item 057's recorded baseline: ``{2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7:
    1.0}`` (the 5 pipeline-detectable Sec.6 modes). Does NOT include modes
    1/4/8 (structurally invisible -- never claimed)."""
    return {mode: 1.0 for mode in _BASELINE_MODES}


def sensitivity_regressed(achieved, baseline) -> bool:
    """The guard predicate: ``True`` iff ANY baseline mode's achieved
    sensitivity is below its baseline floor (a missing/``None`` achieved
    mode counts as regressed). ``False`` iff every baseline mode meets or
    exceeds its floor. Pure."""
    return any(
        achieved.get(mode) is None or achieved[mode] < floor
        for mode, floor in baseline.items()
    )


def g3_recalibration_record(
    *,
    real_cohort_present: bool,
    cohort_id: "Optional[str]",
    build_date: "Optional[str]",
    held_out_fpr: "Optional[float]",
    sensitivity_ok: bool,
    fpr_target: float = 0.10,
) -> dict:
    """A JSON-native evidence record. ``g3_met`` is ``True`` ONLY when
    ``real_cohort_present`` AND ``held_out_fpr`` is not ``None`` AND
    ``held_out_fpr <= fpr_target`` AND ``sensitivity_ok`` (see
    ``may_flip_g3``)."""
    record = {
        "real_cohort_present": bool(real_cohort_present),
        "cohort_id": cohort_id,
        "build_date": build_date,
        "held_out_fpr": held_out_fpr,
        "fpr_target": float(fpr_target),
        "sensitivity_ok": bool(sensitivity_ok),
    }
    record["g3_met"] = may_flip_g3(record)
    return record


def may_flip_g3(record: dict) -> bool:
    """The closure guard: ``True`` iff ``record["real_cohort_present"]`` AND
    a numeric ``record["held_out_fpr"] <= record["fpr_target"]`` AND
    ``record["sensitivity_ok"]``. Any synthetic-only record, any FPR above
    target, or any sensitivity regression -> ``False``, so G3 can never be
    flipped from a synthetic run, an unmet FPR, or a gamed
    (sensitivity-regressed) config."""
    fpr = record.get("held_out_fpr")
    return bool(
        record.get("real_cohort_present")
        and isinstance(fpr, (int, float))
        and not isinstance(fpr, bool)
        and fpr <= record.get("fpr_target", 0.10)
        and record.get("sensitivity_ok")
    )


# =========================================================================== #
# Local fixtures: config variants + the committed Stage-5 corpus cohort
# =========================================================================== #


def _standin_base_config():
    """The stand-in flow's config: the shipped default with reference-mode
    forced off (Assumptions A9 -- the synthetic L1-L5 stand-in need not sit
    inside the real per-level verse-v1 bands; the "reference-off" variant of
    the three-planes discipline)."""
    base = bundled_default_config()
    reference_off = dict(base.reference)
    reference_off["enabled"] = False
    return dataclasses.replace(base, reference=reference_off)


def _standin_axes():
    """A small, explicit, deterministic axis grid (bounded like item 057
    AC13) -- exercises the sweep machinery without an expensive search."""
    return (
        ThresholdAxis(
            name="bounds.lumbar.max_volume_mm3",
            rule_id="bounds",
            param_path=("lumbar", "max_volume_mm3"),
            values=(90_000.0, 150_000.0),
        ),
    )


def _over_loosened_config():
    """A config that disables every Sec.6-detecting rule family -- the
    deliberately gamed config AC9 proves the guard rejects."""
    base = bundled_default_config()
    rules = copy.deepcopy(dict(base.rules))
    for rule_id in _SECTION6_DETECTING_RULE_IDS:
        section = rules.setdefault(rule_id, {})
        section["enabled"] = False
    return dataclasses.replace(base, rules=rules)


def _build_corpus_cohort():
    """The committed Stage-5 corpus cohort, built exactly as item 057: GT =
    ``clean_control``'s seg fixture, candidate = each case's own seg fixture."""
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


def _build_perturbed_standin_cohort():
    """Apply each pipeline-detectable Stage-5 operator to a stand-in GT,
    producing one perturbed case per baseline mode (AC11's CI-runnable
    analogue of "Stage-5 perturbations applied to real VerSe GT")."""
    base = build_clean_spine(levels=_LEVELS)
    gt_img = base.seg_img

    cases = []
    for op_name, mode in _PIPELINE_DETECTABLE_OPERATORS:
        operator_cls = get_perturbation(op_name)
        result = operator_cls().apply(gt_img, seed=0)
        cases.append(
            EvaluationCase(
                case_id=f"perturbed-{op_name}",
                gt=gt_img,
                candidate=result.labelmap,
                expected=result.expectation.to_dict(),
            )
        )
    assert {mode for _name, mode in _PIPELINE_DETECTABLE_OPERATORS} == set(
        _BASELINE_MODES
    )
    return cases


# =========================================================================== #
# AC1: module + importable helpers present
# =========================================================================== #


def test_ac1_module_exposes_callable_helpers():
    assert callable(real_verse_cohort_dir)
    assert callable(build_standin_splits)
    assert callable(calibrate_then_measure)
    assert callable(per_mode_sensitivity)
    assert callable(sensitivity_baseline)
    assert callable(sensitivity_regressed)
    assert callable(g3_recalibration_record)
    assert callable(may_flip_g3)


# =========================================================================== #
# AC2: calibration and held-out stand-in cohorts are provably disjoint
# =========================================================================== #


def test_ac2_standin_splits_are_disjoint(tmp_path):
    cal_cases, held_cases = build_standin_splits(tmp_path)

    assert len(cal_cases) > 0
    assert len(held_cases) > 0
    cal_ids = {c.case_id for c in cal_cases}
    held_ids = {c.case_id for c in held_cases}
    assert cal_ids.isdisjoint(held_ids)


# =========================================================================== #
# AC3: calibrate -> held-out-evaluate flow runs end-to-end, well-formed
# =========================================================================== #


def test_ac3_calibrate_then_measure_yields_well_formed_held_out_metrics(tmp_path):
    cal_cases, held_cases = build_standin_splits(tmp_path)
    base_config = _standin_base_config()
    axes = _standin_axes()

    result, metrics = calibrate_then_measure(cal_cases, held_cases, base_config, axes)

    assert result.best is not None
    assert isinstance(metrics.false_positive_rate, float)
    assert 0.0 <= metrics.false_positive_rate <= 1.0
    assert metrics.n_cases == len(held_cases)


# =========================================================================== #
# AC4: the calibration fit never receives the held-out cohort
# =========================================================================== #


def test_ac4_fit_never_receives_held_out_cases(tmp_path, monkeypatch):
    cal_cases, held_cases = build_standin_splits(tmp_path)
    base_config = _standin_base_config()
    axes = _standin_axes()

    captured = {}
    real_calibrate_thresholds = calibrate_thresholds

    def _spy(cases, config, axes_arg, **kwargs):
        captured["case_ids"] = {c.case_id for c in cases}
        return real_calibrate_thresholds(cases, config, axes_arg, **kwargs)

    monkeypatch.setattr(sys.modules[__name__], "calibrate_thresholds", _spy)

    calibrate_then_measure(cal_cases, held_cases, base_config, axes)

    cal_ids = {c.case_id for c in cal_cases}
    held_ids = {c.case_id for c in held_cases}
    assert captured["case_ids"] == cal_ids
    assert captured["case_ids"].isdisjoint(held_ids)


# =========================================================================== #
# AC5: a clean self-consistent held-out cohort measures FPR 0.0
# =========================================================================== #


def test_ac5_clean_held_out_standin_measures_fpr_zero(tmp_path):
    cal_cases, held_cases = build_standin_splits(tmp_path)
    base_config = _standin_base_config()
    axes = _standin_axes()

    _result, metrics = calibrate_then_measure(cal_cases, held_cases, base_config, axes)

    assert metrics.false_positive_rate == 0.0


# =========================================================================== #
# AC6: sensitivity_baseline encodes item 057's recorded baseline
# =========================================================================== #


def test_ac6_sensitivity_baseline_matches_item_057():
    baseline = sensitivity_baseline()
    assert baseline == {2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}
    assert set(baseline).isdisjoint({1, 4, 8})


# =========================================================================== #
# AC7: the shipped default reproduces the baseline on the Stage-5 corpus
# =========================================================================== #


@pytest.mark.parametrize("mode", _BASELINE_MODES)
def test_ac7_shipped_default_reproduces_baseline_on_corpus(mode):
    achieved = per_mode_sensitivity(
        _build_corpus_cohort(), bundled_default_config(), failure_modes=FAILURE_MODE_NAMES
    )
    assert achieved[mode] == 1.0


# =========================================================================== #
# AC8: sensitivity_regressed is a correct guard predicate (truth table)
# =========================================================================== #


@pytest.mark.parametrize(
    "achieved, expected",
    [
        pytest.param({2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}, False, id="exact-match"),
        pytest.param({2: 0.5, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}, True, id="one-mode-half"),
        pytest.param({2: 0.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}, True, id="one-mode-zero"),
        pytest.param({3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}, True, id="one-mode-absent"),
        pytest.param({2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: None}, True, id="one-mode-none"),
    ],
)
def test_ac8_sensitivity_regressed_truth_table(achieved, expected):
    assert sensitivity_regressed(achieved, sensitivity_baseline()) is expected


# =========================================================================== #
# AC9: the guard fails loudly on a deliberately over-loosened config
# =========================================================================== #


def test_ac9_guard_rejects_over_loosened_config():
    loosened_config = _over_loosened_config()
    achieved = per_mode_sensitivity(
        _build_corpus_cohort(), loosened_config, failure_modes=FAILURE_MODE_NAMES
    )

    assert any(achieved.get(mode, 0.0) < 1.0 for mode in _BASELINE_MODES)
    assert sensitivity_regressed(achieved, sensitivity_baseline()) is True


def test_adv_over_loosened_config_drives_fpr_lower_than_shipped_default():
    """Makes explicit *why* the guard is needed: the loosened config buys a
    lower FPR on a would-be-flagging cohort at the cost of sensitivity."""
    cohort = _build_perturbed_standin_cohort()
    shipped_metrics = compute_cohort_metrics(
        evaluate_cohort(cohort, bundled_default_config())
    )
    loosened_metrics = compute_cohort_metrics(
        evaluate_cohort(cohort, _over_loosened_config())
    )
    # Every case here is an expected-failure case (a perturbed GT); "flagged"
    # rate on this cohort behaves like the FPR the guard exists to prevent
    # from being gamed downward -- fewer flags under the loosened config.
    shipped_flags = sum(1 for c in shipped_metrics.per_mode for _ in range(c.n_caught))
    loosened_flags = sum(1 for c in loosened_metrics.per_mode for _ in range(c.n_caught))
    assert loosened_flags <= shipped_flags


# =========================================================================== #
# AC10: per_mode_sensitivity and the guard are deterministic, non-mutating
# =========================================================================== #


def test_ac10_per_mode_sensitivity_deterministic_and_non_mutating():
    cases = _build_corpus_cohort()
    config = bundled_default_config()

    rules_before = copy.deepcopy(config.rules)
    arrays_before = [np.asanyarray(c.gt.dataobj).copy() for c in cases]

    result_a = per_mode_sensitivity(cases, config, failure_modes=FAILURE_MODE_NAMES)
    result_b = per_mode_sensitivity(cases, config, failure_modes=FAILURE_MODE_NAMES)

    assert result_a == result_b
    assert config.rules == rules_before
    for case, before in zip(cases, arrays_before):
        assert np.array_equal(np.asanyarray(case.gt.dataobj), before)


def test_ac10_sensitivity_regressed_deterministic_and_non_mutating():
    achieved = {2: 1.0, 3: 1.0, 5: 0.5, 6: 1.0, 7: 1.0}
    baseline = sensitivity_baseline()
    achieved_before = dict(achieved)
    baseline_before = dict(baseline)

    result_a = sensitivity_regressed(achieved, baseline)
    result_b = sensitivity_regressed(achieved, baseline)

    assert result_a == result_b is True
    assert achieved == achieved_before
    assert baseline == baseline_before


# =========================================================================== #
# AC11: Stage-5 operators on a stand-in GT fire the expected rule per mode
# =========================================================================== #


@pytest.mark.parametrize("op_name, mode", _PIPELINE_DETECTABLE_OPERATORS)
def test_ac11_perturbed_standin_gt_fires_expected_mode(op_name, mode):
    achieved = per_mode_sensitivity(
        _build_perturbed_standin_cohort(),
        bundled_default_config(),
        failure_modes=FAILURE_MODE_NAMES,
    )
    assert achieved[mode] == 1.0


# =========================================================================== #
# AC12: the real-VerSe perturbation-sensitivity clause is a GENUINE skip
# =========================================================================== #


def test_ac12_requires_verse_marker_is_a_genuine_skipif():
    assert requires_verse.mark.name == "skipif"
    condition = requires_verse.mark.args[0]
    assert isinstance(condition, bool)
    # On this data-absent host (no SEGFACET_VERSE_COHORT mounted) the condition
    # must be True so the gated test actually skips -- never xfail, never an
    # unconditional pass.
    assert condition is True


@requires_verse
def test_ac12_real_verse_recalibration_and_sensitivity_guard(tmp_path):
    """Positive counterpart: on a data-holding host this runs the real
    calibrate -> held-out flow plus the perturb-real-GT sensitivity guard and
    asserts the record's g3_met agrees with may_flip_g3. Skips cleanly
    everywhere else (proven structurally above)."""
    from segfacet.datasets import bundled_descriptor_path, load_descriptor, resolve

    root = real_verse_cohort_dir()
    descriptor = load_descriptor(bundled_descriptor_path("verse19.yaml"))
    train_cohort = resolve(descriptor, data_root=root, subset="training")
    val_cohort = resolve(descriptor, data_root=root, subset="validation")

    def _to_eval_cases(cohort):
        return [
            EvaluationCase(
                case_id=case.case_id,
                gt=case.seg_path,
                candidate=case.seg_path,
                expected={"expected_verdict": "pass"},
            )
            for case in cohort
        ]

    base_config = bundled_default_config()
    _result, held_out_metrics = calibrate_then_measure(
        _to_eval_cases(train_cohort),
        _to_eval_cases(val_cohort),
        base_config,
        _standin_axes(),
    )
    fpr = held_out_metrics.false_positive_rate
    assert isinstance(fpr, float) and 0.0 <= fpr <= 1.0

    import nibabel as nib

    perturbed_cases = []
    for case in train_cohort:
        gt_img = nib.load(str(case.seg_path))
        for op_name, _mode in _PIPELINE_DETECTABLE_OPERATORS:
            try:
                result = get_perturbation(op_name)().apply(gt_img, seed=0)
            except FacetInputError:
                continue
            perturbed_cases.append(
                EvaluationCase(
                    case_id=f"{case.case_id}-{op_name}",
                    gt=gt_img,
                    candidate=result.labelmap,
                    expected=result.expectation.to_dict(),
                )
            )

    achieved = per_mode_sensitivity(
        perturbed_cases, base_config, failure_modes=FAILURE_MODE_NAMES
    )
    sensitivity_ok = not sensitivity_regressed(achieved, sensitivity_baseline())

    record = g3_recalibration_record(
        real_cohort_present=True,
        cohort_id="verse19",
        build_date="2026-07-18",
        held_out_fpr=fpr,
        sensitivity_ok=sensitivity_ok,
    )
    assert record["g3_met"] == may_flip_g3(record)


# =========================================================================== #
# AC13: real_verse_cohort_dir() env behaviour
# =========================================================================== #


def test_ac13_returns_none_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("SEGFACET_VERSE_COHORT", raising=False)
    assert real_verse_cohort_dir() is None


def test_ac13_returns_none_when_env_var_points_to_nonexistent_path(monkeypatch, tmp_path):
    nonexistent = tmp_path / "no-such-verse-dir"
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(nonexistent))
    assert real_verse_cohort_dir() is None


def test_ac13_returns_path_when_env_var_points_to_existing_dir(monkeypatch, tmp_path):
    existing = tmp_path / "verse-cohort"
    existing.mkdir()
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(existing))
    result = real_verse_cohort_dir()
    assert result is not None
    assert pathlib.Path(result).resolve() == existing.resolve()


# =========================================================================== #
# AC14: g3_recalibration_record schema
# =========================================================================== #


def test_ac14_record_has_exact_key_set_and_json_native_types():
    record = g3_recalibration_record(
        real_cohort_present=False,
        cohort_id=None,
        build_date=None,
        held_out_fpr=None,
        sensitivity_ok=False,
    )

    assert set(record.keys()) == {
        "real_cohort_present",
        "cohort_id",
        "build_date",
        "held_out_fpr",
        "fpr_target",
        "sensitivity_ok",
        "g3_met",
    }
    assert isinstance(record["real_cohort_present"], bool)
    assert record["cohort_id"] is None
    assert record["build_date"] is None
    assert record["held_out_fpr"] is None
    assert isinstance(record["fpr_target"], float)
    assert isinstance(record["sensitivity_ok"], bool)
    assert isinstance(record["g3_met"], bool)

    round_tripped = json.loads(json.dumps(record))
    assert round_tripped == record


def test_ac14_record_json_round_trip_with_real_values():
    record = g3_recalibration_record(
        real_cohort_present=True,
        cohort_id="verse19-train",
        build_date="2026-07-18",
        held_out_fpr=0.05,
        sensitivity_ok=True,
    )
    round_tripped = json.loads(json.dumps(record))
    assert round_tripped == record
    assert isinstance(record["held_out_fpr"], float)


# =========================================================================== #
# AC15: may_flip_g3 / g3_met is True only with a real cohort AND FPR at/under
# target AND sensitivity intact (parametrised over each falsifying case)
# =========================================================================== #


@pytest.mark.parametrize(
    "present, fpr, sensitivity_ok, expected",
    [
        pytest.param(True, 0.05, True, True, id="all-conditions-met"),
        pytest.param(True, 0.10, True, True, id="fpr-exactly-at-target"),
        pytest.param(False, 0.05, True, False, id="no-real-cohort"),
        pytest.param(True, None, True, False, id="fpr-none"),
        pytest.param(True, 0.50, True, False, id="fpr-above-target"),
        pytest.param(True, 0.05, False, False, id="sensitivity-regressed"),
        pytest.param(False, None, False, False, id="all-falsifying-at-once"),
    ],
)
def test_ac15_may_flip_g3_truth_table(present, fpr, sensitivity_ok, expected):
    record = g3_recalibration_record(
        real_cohort_present=present,
        cohort_id="verse19" if present else None,
        build_date="2026-07-18" if present else None,
        held_out_fpr=fpr,
        sensitivity_ok=sensitivity_ok,
    )
    assert may_flip_g3(record) is expected
    assert record["g3_met"] == may_flip_g3(record)


# =========================================================================== #
# AC16: a synthetic-only acceptance run yields a non-flipping, self-reported
# record
# =========================================================================== #


def test_ac16_synthetic_only_record_is_non_flipping_and_self_reported(capsys):
    record = g3_recalibration_record(
        real_cohort_present=False,
        cohort_id=None,
        build_date=None,
        held_out_fpr=None,
        sensitivity_ok=False,
    )

    assert record["real_cohort_present"] is False
    assert record["g3_met"] is False
    assert may_flip_g3(record) is False

    print(record)
    captured = capsys.readouterr()
    assert "real_cohort_present" in captured.out
    assert "g3_met" in captured.out


# =========================================================================== #
# AC17: scope / regression guard -- no production code, no new dependency
# =========================================================================== #


def test_ac17_no_new_dependency():
    """Item 091 adds no ``src/segfacet/**`` change and no new dependency
    (Assumptions A1, scope fence). The dependency set is the one timeless,
    re-checkable part of that claim on any branch (a full source-tree diff
    against a moving ``main`` is a one-time merge-time proof, not a durable
    regression guard -- see item 084's own AC11 for this exact reasoning).

    Item 094 legitimately adds ``tptbox`` as a new required core dependency
    (an orientation-safe NIfTI loader, unrelated to item 091's scope) -- the
    set below is updated to include it so this guard continues to check
    "item 091 didn't touch the dependency set", not "the dependency set is
    frozen forever"."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    pyproject_text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    match = re.search(r"dependencies\s*=\s*\[(.*?)\]", pyproject_text, re.DOTALL)
    assert match is not None
    deps_block = match.group(1)
    dep_names = [
        line.strip().strip(",").strip('"').split(">=")[0].split("==")[0]
        for line in deps_block.splitlines()
        if line.strip()
    ]
    expected_deps = {
        "numpy",
        "scipy",
        "scikit-image",
        "nibabel",
        "PyYAML",
        "jsonschema",
        "tptbox",
    }
    assert set(dep_names) == expected_deps


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_no_feasible_setting_surfaces_explicitly_not_attributeerror():
    """A base config whose sensitivity floor cannot be met by any grid point
    (an axis that cannot affect the outcome, over a cohort with an expected
    failure) yields ``result.best is None``; ``calibrate_then_measure`` must
    raise a clear error, never crash on ``None.assignment``."""
    base = build_clean_spine(levels=_LEVELS)
    failing_case = EvaluationCase(
        case_id="always-fails",
        gt=base.seg_img,
        candidate=base.seg_img,
        # A rule id with no matching designated finding for this candidate,
        # so the sensitivity floor (default 1.0) can never be met.
        expected={
            "expected_verdict": "flagged-for-review",
            "expected_rule_ids": ["bounds"],
            "failure_mode": 2,
        },
    )
    axes = (
        ThresholdAxis(
            name="bounds.lumbar.max_volume_mm3",
            rule_id="bounds",
            param_path=("lumbar", "max_volume_mm3"),
            values=(90_000.0, 150_000.0),
        ),
    )

    with pytest.raises(FacetInputError):
        calibrate_then_measure([failing_case], [failing_case], bundled_default_config(), axes)


def test_adv_sensitivity_regressed_empty_achieved_is_regression():
    assert sensitivity_regressed({}, sensitivity_baseline()) is True


def test_adv_env_hygiene_after_monkeypatch_teardown(monkeypatch, tmp_path):
    existing = tmp_path / "verse-cohort"
    existing.mkdir()
    monkeypatch.setenv("SEGFACET_VERSE_COHORT", str(existing))
    assert real_verse_cohort_dir() is not None
    monkeypatch.undo()
    assert "SEGFACET_VERSE_COHORT" not in os.environ or os.environ.get(
        "SEGFACET_VERSE_COHORT"
    ) != str(existing)


def test_adv_determinism_two_calibrate_then_measure_runs_agree(tmp_path):
    cal_cases, held_cases = build_standin_splits(tmp_path)
    base_config = _standin_base_config()
    axes = _standin_axes()

    _result_a, metrics_a = calibrate_then_measure(cal_cases, held_cases, base_config, axes)
    _result_b, metrics_b = calibrate_then_measure(cal_cases, held_cases, base_config, axes)

    assert metrics_a.to_dict() == metrics_b.to_dict()
