"""Tests for item 101 -- cohort-level per-mode aggregation & run-vs-run
comparison (``segfacet.eval.per_mode_cohort``), plus the harness's opt-in
``per_mode`` hook (``segfacet.eval.harness``) and the reporting-surface
additions it feeds (``segfacet.eval.report``).

Covers Acceptance Criteria AC1-AC22, AC26-AC27 (AC23-AC25, the CLI, live in
``tests/test_101_compare_runs_cli.py``):

- AC1:  the module's public surface (four frozen dataclasses,
        ``summarise_run_per_mode``, ``compare_runs``) exists, is exported via
        ``__all__``, and is re-exported from ``segfacet.eval``.
- AC2:  ``evaluate_case``/``evaluate_cohort``'s ``per_mode`` hook is
        keyword-only, default ``False``; every record's ``per_mode`` is
        ``None`` (incl. ``to_dict()``) when omitted.
- AC3:  the hook, enabled, reproduces item 099's values exactly.
- AC4:  the hook adds no second pipeline pass (spy on ``run_qc`` /
        ``compute_per_mode_metrics``).
- AC5:  a candidate-less case degrades explicitly (modes 1/4/5 None, 2/3/6/7/8
        float, ``mean_dice`` None), never raises.
- AC6:  ``summarise_run_per_mode`` returns exactly eight aggregates in mode
        order, spec-consistent, for any cohort including an empty one.
- AC7:  the aggregate statistics (``n_with_value``/``mean``/``minimum``/
        ``maximum``/``total``) are the documented arithmetic, verified by hand.
- AC8:  detection rates are read verbatim from item 054's
        ``PerModeSensitivity``, never recomputed; ``None``/``0`` when absent.
- AC9:  the aggregate Dice context comes from item 099's carried per-case
        fields; a drift guard proves no new Dice/Jaccard/overlap arithmetic.
- AC10: ``compare_runs`` returns eight deltas in mode order with
        ``delta == value_b - value_a`` (``None`` when either side is
        ``None``).
- AC11: ``scale``/``normalised_delta`` follow the stated formula, including
        the ``scale == 0.0`` -> ``normalised_delta == 0.0`` branch.
- AC12: ``worsened`` is direction-aware; mode 2 is not reported backwards.
- AC13: ``attributed_mode`` is the largest normalised move, ties to the
        lowest mode, ``None`` when every mode is ``None``/``0.0``.
- AC14: comparing a run against itself is an all-zero report.
- AC15: mismatched cohorts raise ``FacetInputError``; reordered-same-set
        cohorts compare successfully.
- AC16: the demonstrator -- island stripping attributes to mode 3 while
        aggregate Dice barely moves (Stage 18's thesis).
- AC17: both records round-trip through JSON and back into dataclasses.
- AC18: both ``to_dict()``s are plain JSON, no numpy leakage.
- AC19: the evaluation report gains an optional additive ``per_mode_magnitude``
        block; v0 schema stays v0.
- AC20: the comparison artifact has its own bundled, versioned schema.
- AC21: both artifacts are byte-reproducible within a session.
- AC22: the human rendering names the implicated mode in words, never the
        literal string "None".
- AC26: the aggregation/comparison are pure (no file/clock access, no
        mutation) and idempotent.
- AC27: the scope fence holds -- untouched files are byte-identical to their
        pre-101 state (resolved relative to this test file, never as a
        literal absolute path).

Adversarial / edge-case scenarios included: an empty cohort; a cohort where
every record's ``per_mode`` is ``None`` (forgot the flag); a mode ``None`` in
run A but a float in run B; ``inf``/``nan`` absence; ``by_mode(0)``/
``by_mode(9)`` ``KeyError``; ``from_dict`` on a truncated/malformed block;
identical ``run_id``s on both sides (allowed).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Optional

import builtins

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator

from segfacet.config import bundled_default_config
from segfacet.eval.metrics import CohortMetrics, ConfusionCounts, CorrelationResult, PerModeSensitivity
from segfacet.eval.per_mode import PER_MODE_METRIC_SPECS, PerModeMetric, PerModeMetrics
from segfacet.io import FacetInputError
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image


def _pmc():
    """Local import of ``segfacet.eval.per_mode_cohort`` -- kept out of the
    module-level import block (mirrors ``tests/test_099_per_mode_metrics.py``'s
    ``_per_mode()`` convention) so this file still collects before item 101's
    builder step lands the module."""
    import segfacet.eval.per_mode_cohort as per_mode_cohort

    return per_mode_cohort


def _harness_mod():
    import segfacet.eval.harness as harness

    return harness


# =========================================================================== #
# Corpus fixtures -- loaded once at module scope (Testing Strategy cost control)
# =========================================================================== #

_MANIFEST = load_manifest()
_CASES = {c["case_id"]: c for c in _MANIFEST["cases"]}
_CONFIG = bundled_default_config()
_GT_ARRAY = np.asanyarray(loaded_seg_image(_CASES["clean_control"]).dataobj)


def _arr(cid: str) -> np.ndarray:
    return np.asanyarray(loaded_seg_image(_CASES[cid]).dataobj)


_FIXTURE_CASE_IDS = ("clean_control", "mode1_displace", "mode3_inject_islands")


@pytest.fixture(scope="module")
def real_cohort():
    """A small (3 candidate cases + 1 candidate-less) cohort driven with
    ``per_mode=True`` -- built once, reused across every AC that needs a real
    ``compute_per_mode_metrics`` pass rather than a hand-built stub."""
    harness = _harness_mod()
    cases = [
        harness.EvaluationCase(
            case_id=cid,
            gt=_GT_ARRAY,
            candidate=_arr(cid),
            expected={"expected_verdict": "pass"},
        )
        for cid in _FIXTURE_CASE_IDS
    ]
    cases.append(
        harness.EvaluationCase(
            case_id="no_candidate",
            gt=_GT_ARRAY,
            expected={"expected_verdict": "pass"},
        )
    )
    return harness.evaluate_cohort(cases, _CONFIG, per_mode=True)


# --------------------------------------------------------------------------- #
# Hand-built PerModeMetrics / fake-cohort helpers (mirrors
# tests/test_100_severity_ladder.py's dataclasses.replace-style directness --
# the Testing Strategy's mandate to build RunPerModeSummary/ModeDelta objects
# directly for the pure-arithmetic ACs)
# --------------------------------------------------------------------------- #


def _pmm(values: dict, mean_dice=None, volume_weighted_dice=None) -> PerModeMetrics:
    """Build a hand-controlled :class:`PerModeMetrics` with the given
    ``{mode: value_or_None}`` mapping (modes not present default to
    ``None``)."""
    entries = []
    for mode in range(1, 9):
        spec = PER_MODE_METRIC_SPECS[mode]
        value = values.get(mode)
        entries.append(
            PerModeMetric(
                failure_mode=spec.failure_mode,
                failure_mode_name=spec.failure_mode_name,
                metric_name=spec.metric_name,
                value=value,
                direction=spec.direction,
                baseline=spec.baseline,
                source=spec.source,
                detail=None if value is not None else "test stub: no value",
            )
        )
    return PerModeMetrics(
        per_mode=tuple(entries),
        mean_dice=mean_dice,
        volume_weighted_dice=volume_weighted_dice,
        mean_jaccard=None,
        n_matched=0,
        n_unmatched=0,
    )


def _full(value: Optional[float]) -> dict:
    return {m: value for m in range(1, 9)}


@dataclasses.dataclass
class _FakeCase:
    case_id: str
    per_mode: Optional[PerModeMetrics]


@dataclasses.dataclass
class _FakeCohort:
    cases: tuple


def _fake_case(case_id, values, mean_dice=None, volume_weighted_dice=None) -> _FakeCase:
    return _FakeCase(case_id=case_id, per_mode=_pmm(values, mean_dice, volume_weighted_dice))


def _aggregate(mode, mean, *, n_cases=2, n_with_value=2, detection_rate=None, n_detection_cases=0):
    pmc = _pmc()
    spec = PER_MODE_METRIC_SPECS[mode]
    return pmc.ModeAggregate(
        failure_mode=spec.failure_mode,
        failure_mode_name=spec.failure_mode_name,
        metric_name=spec.metric_name,
        direction=spec.direction,
        baseline=spec.baseline,
        n_cases=n_cases,
        n_with_value=n_with_value,
        mean=mean,
        minimum=mean,
        maximum=mean,
        total=(None if mean is None else mean * n_with_value),
        detection_rate=detection_rate,
        n_detection_cases=n_detection_cases,
    )


def _summary(run_id, case_ids, means: dict, *, mean_dice=None, volume_weighted_dice=None, n_cases=None):
    pmc = _pmc()
    per_mode = tuple(_aggregate(m, means.get(m)) for m in range(1, 9))
    return pmc.RunPerModeSummary(
        run_id=run_id,
        case_ids=tuple(case_ids),
        n_cases=n_cases if n_cases is not None else len(case_ids),
        per_mode=per_mode,
        mean_dice=mean_dice,
        volume_weighted_dice=volume_weighted_dice,
        run_manifest=None,
    )


def _per_mode_cohort_source() -> str:
    pmc = _pmc()
    return Path(pmc.__file__).read_text(encoding="utf-8")


# =========================================================================== #
# AC1: public surface, re-export, frozen dataclasses
# =========================================================================== #

_PUBLIC_NAMES = (
    "ModeAggregate",
    "RunPerModeSummary",
    "ModeDelta",
    "RunComparison",
    "summarise_run_per_mode",
    "compare_runs",
)

_FROZEN_DATACLASS_NAMES = (
    "ModeAggregate",
    "RunPerModeSummary",
    "ModeDelta",
    "RunComparison",
)


def test_ac1_all_names_exported_from_per_mode_cohort_module():
    pmc = _pmc()
    assert set(_PUBLIC_NAMES) <= set(pmc.__all__)
    for name in _PUBLIC_NAMES:
        assert hasattr(pmc, name), f"segfacet.eval.per_mode_cohort is missing {name!r}"


def test_ac1_all_names_reexported_from_eval_package():
    import segfacet.eval as eval_pkg

    for name in _PUBLIC_NAMES:
        assert name in eval_pkg.__all__, f"{name!r} missing from segfacet.eval.__all__"
        assert hasattr(eval_pkg, name), f"{name!r} not importable from segfacet.eval"


@pytest.mark.parametrize("name", _FROZEN_DATACLASS_NAMES)
def test_ac1_all_four_dataclasses_are_frozen(name):
    pmc = _pmc()
    cls = getattr(pmc, name)
    assert dataclasses.is_dataclass(cls)
    assert cls.__dataclass_params__.frozen is True


def test_ac1_modeaggregate_instance_raises_on_mutation():
    agg = _aggregate(1, 0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        agg.mean = 999.0  # type: ignore[misc]


def test_ac1_runpermodesummary_instance_raises_on_mutation():
    summary = _summary("r", ("c1",), _full(0.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        summary.run_id = "mutated"  # type: ignore[misc]


def test_ac1_modedelta_instance_raises_on_mutation():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.per_mode[0].delta = 999.0  # type: ignore[misc]


def test_ac1_runcomparison_instance_raises_on_mutation():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmp.attributed_mode = 1  # type: ignore[misc]


# =========================================================================== #
# AC2: the harness's per_mode hook is opt-in, off by default
# =========================================================================== #


def test_ac2_evaluate_case_default_omitted_per_mode_is_none():
    harness = _harness_mod()
    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_arr("clean_control"),
        expected={"expected_verdict": "pass"},
    )
    result = harness.evaluate_case(case, _CONFIG)
    assert result.per_mode is None
    assert result.to_dict()["per_mode"] is None


def test_ac2_evaluate_cohort_default_omitted_every_record_per_mode_is_none():
    harness = _harness_mod()
    cases = [
        harness.EvaluationCase(
            case_id=cid,
            gt=_GT_ARRAY,
            candidate=_arr(cid),
            expected={"expected_verdict": "pass"},
        )
        for cid in ("clean_control", "mode1_displace")
    ]
    cohort = harness.evaluate_cohort(cases, _CONFIG)
    for record in cohort.cases:
        assert record.per_mode is None
        assert record.to_dict()["per_mode"] is None


def test_ac2_evaluate_case_per_mode_false_explicit_is_none():
    harness = _harness_mod()
    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_arr("clean_control"),
        expected={"expected_verdict": "pass"},
    )
    result = harness.evaluate_case(case, _CONFIG, per_mode=False)
    assert result.per_mode is None


def test_ac2_real_cohort_fixture_every_record_has_per_mode_populated(real_cohort):
    """Sanity companion to the off-by-default tests above: the module-scope
    fixture built with ``per_mode=True`` really does populate every record."""
    for record in real_cohort.cases:
        assert record.per_mode is not None


# =========================================================================== #
# AC3: the hook, enabled, reproduces item 099's values unchanged
# =========================================================================== #


def test_ac3_hook_matches_independently_computed_compute_per_mode_metrics():
    import nibabel as nib

    from segfacet.eval.per_mode import compute_per_mode_metrics
    from segfacet.pipeline import run_qc

    harness = _harness_mod()
    cand_arr = _arr("mode1_displace")

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=cand_arr,
        expected={"expected_verdict": "pass"},
    )
    result = harness.evaluate_case(case, _CONFIG, per_mode=True)

    # The explicit dtype= is mandatory: nibabel 5.3.3 hard-errors on
    # Nifti1Image(int64_array, affine) without it (item 040's Decisions log;
    # see the canonical construction in src/segfacet/synth/regression.py).
    cand_img = nib.Nifti1Image(cand_arr, np.eye(4), dtype=cand_arr.dtype)
    _case_result, subject_block = run_qc(cand_img, _CONFIG)
    expected = compute_per_mode_metrics(
        subject_block, candidate=cand_arr, gt=_GT_ARRAY, spacing=(1.0, 1.0, 1.0)
    )

    assert result.per_mode.to_dict() == expected.to_dict()


# =========================================================================== #
# AC4: the hook adds no second pipeline pass
# =========================================================================== #


def test_ac4_evaluate_case_calls_run_qc_and_compute_per_mode_metrics_exactly_once(monkeypatch):
    import segfacet.eval.per_mode as per_mode_mod
    import segfacet.pipeline as pipeline_mod

    harness = _harness_mod()
    calls = {"run_qc": 0, "per_mode": 0}
    real_run_qc = pipeline_mod.run_qc
    real_compute = per_mode_mod.compute_per_mode_metrics

    def _spy_run_qc(*a, **kw):
        calls["run_qc"] += 1
        return real_run_qc(*a, **kw)

    def _spy_compute(*a, **kw):
        calls["per_mode"] += 1
        return real_compute(*a, **kw)

    monkeypatch.setattr(pipeline_mod, "run_qc", _spy_run_qc)
    monkeypatch.setattr(per_mode_mod, "compute_per_mode_metrics", _spy_compute)

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_arr("mode1_displace"),
        expected={"expected_verdict": "pass"},
    )
    harness.evaluate_case(case, _CONFIG, per_mode=True)

    assert calls["run_qc"] == 1
    assert calls["per_mode"] == 1


def test_ac4_evaluate_cohort_calls_each_exactly_once_per_case(monkeypatch):
    import segfacet.eval.per_mode as per_mode_mod
    import segfacet.pipeline as pipeline_mod

    harness = _harness_mod()
    calls = {"run_qc": 0, "per_mode": 0}
    real_run_qc = pipeline_mod.run_qc
    real_compute = per_mode_mod.compute_per_mode_metrics

    def _spy_run_qc(*a, **kw):
        calls["run_qc"] += 1
        return real_run_qc(*a, **kw)

    def _spy_compute(*a, **kw):
        calls["per_mode"] += 1
        return real_compute(*a, **kw)

    monkeypatch.setattr(pipeline_mod, "run_qc", _spy_run_qc)
    monkeypatch.setattr(per_mode_mod, "compute_per_mode_metrics", _spy_compute)

    cases = [
        harness.EvaluationCase(
            case_id=cid,
            gt=_GT_ARRAY,
            candidate=_arr(cid),
            expected={"expected_verdict": "pass"},
        )
        for cid in ("clean_control", "mode1_displace")
    ]
    harness.evaluate_cohort(cases, _CONFIG, per_mode=True)

    assert calls["run_qc"] == 2
    assert calls["per_mode"] == 2


# =========================================================================== #
# AC5: a candidate-less case degrades explicitly, never raises
# =========================================================================== #


def test_ac5_candidate_less_case_modes_1_4_5_none_2_3_6_7_8_float_mean_dice_none():
    harness = _harness_mod()
    case = harness.EvaluationCase(
        case_id="c", gt=_GT_ARRAY, expected={"expected_verdict": "pass"}
    )
    result = harness.evaluate_case(case, _CONFIG, per_mode=True)
    pm = result.per_mode
    assert pm is not None
    for mode in (1, 4, 5):
        entry = pm.by_mode(mode)
        assert entry.value is None, mode
        assert isinstance(entry.detail, str) and entry.detail, mode
    for mode in (2, 3, 6, 7, 8):
        entry = pm.by_mode(mode)
        assert type(entry.value) is float, mode
    assert pm.mean_dice is None


def test_ac5_real_cohort_fixture_no_candidate_case_matches(real_cohort):
    record = next(c for c in real_cohort.cases if c.case_id == "no_candidate")
    pm = record.per_mode
    assert pm is not None
    for mode in (1, 4, 5):
        assert pm.by_mode(mode).value is None, mode
    for mode in (2, 3, 6, 7, 8):
        assert type(pm.by_mode(mode).value) is float, mode
    assert pm.mean_dice is None


# =========================================================================== #
# AC6: summarise_run_per_mode returns exactly eight aggregates, mode order
# =========================================================================== #


def test_ac6_empty_cohort_returns_eight_spec_consistent_aggregates():
    pmc = _pmc()
    summary = pmc.summarise_run_per_mode(_FakeCohort(cases=()), run_id="empty")
    assert len(summary.per_mode) == 8
    assert tuple(a.failure_mode for a in summary.per_mode) == tuple(range(1, 9))
    for agg in summary.per_mode:
        spec = PER_MODE_METRIC_SPECS[agg.failure_mode]
        assert agg.metric_name == spec.metric_name
        assert agg.direction == spec.direction
        assert agg.baseline == spec.baseline


def test_ac6_empty_cohort_every_statistic_is_none_n_cases_zero():
    pmc = _pmc()
    summary = pmc.summarise_run_per_mode(_FakeCohort(cases=()), run_id="empty")
    assert summary.n_cases == 0
    assert summary.case_ids == ()
    for agg in summary.per_mode:
        assert agg.n_with_value == 0
        assert agg.mean is None
        assert agg.minimum is None
        assert agg.maximum is None
        assert agg.total is None


def test_ac6_real_cohort_matches_spec_table(real_cohort):
    pmc = _pmc()
    summary = pmc.summarise_run_per_mode(real_cohort, run_id="real")
    assert len(summary.per_mode) == 8
    assert tuple(a.failure_mode for a in summary.per_mode) == tuple(range(1, 9))
    for agg in summary.per_mode:
        spec = PER_MODE_METRIC_SPECS[agg.failure_mode]
        assert agg.metric_name == spec.metric_name
        assert agg.direction == spec.direction
        assert agg.baseline == spec.baseline


# =========================================================================== #
# AC7: the aggregate statistics are the documented arithmetic
# =========================================================================== #


def test_ac7_hand_computed_mix_of_present_and_none_values():
    pmc = _pmc()
    case_a = _fake_case("a", {1: 1.0, 2: 0.5, 3: None, 4: 5.0, 5: 0.0, 6: 2.0, 7: None, 8: 100.0})
    case_b = _fake_case("b", {1: 3.0, 2: None, 3: 2.0, 4: 5.0, 5: 1.0, 6: None, 7: 0.0, 8: 200.0})
    case_c = _fake_case("c", {1: None, 2: 0.9, 3: 4.0, 4: None, 5: 2.0, 6: 4.0, 7: 1.0, 8: None})
    cohort = _FakeCohort(cases=(case_a, case_b, case_c))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")

    expected = {
        1: (2, 2.0, 1.0, 3.0, 4.0),
        2: (2, 0.7, 0.5, 0.9, 1.4),
        3: (2, 3.0, 2.0, 4.0, 6.0),
        4: (2, 5.0, 5.0, 5.0, 10.0),
        5: (3, 1.0, 0.0, 2.0, 3.0),
        6: (2, 3.0, 2.0, 4.0, 6.0),
        7: (2, 0.5, 0.0, 1.0, 1.0),
        8: (2, 150.0, 100.0, 200.0, 300.0),
    }
    for mode, (n_with_value, mean, minimum, maximum, total) in expected.items():
        agg = summary.by_mode(mode)
        assert agg.n_cases == 3, mode
        assert agg.n_with_value == n_with_value, mode
        assert agg.mean == pytest.approx(mean), mode
        assert agg.minimum == pytest.approx(minimum), mode
        assert agg.maximum == pytest.approx(maximum), mode
        assert agg.total == pytest.approx(total), mode


def test_ac7_all_none_for_a_mode_yields_none_stats_including_total():
    pmc = _pmc()
    case_a = _fake_case("a", {**_full(0.0), 4: None})
    case_b = _fake_case("b", {**_full(0.0), 4: None})
    cohort = _FakeCohort(cases=(case_a, case_b))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")
    mode4 = summary.by_mode(4)
    assert mode4.n_with_value == 0
    assert mode4.mean is None
    assert mode4.minimum is None
    assert mode4.maximum is None
    assert mode4.total is None


def test_ac7_records_with_per_mode_none_are_skipped_not_zero():
    """A record whose ``per_mode`` is ``None`` (no candidate reached the hook
    -- or the caller forgot the flag on some records) is skipped entirely,
    not folded in as a zero."""
    pmc = _pmc()
    case_a = _fake_case("a", _full(1.0))
    case_b = _FakeCase(case_id="b", per_mode=None)
    cohort = _FakeCohort(cases=(case_a, case_b))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")
    mode1 = summary.by_mode(1)
    assert mode1.n_with_value == 1
    assert mode1.mean == pytest.approx(1.0)


def test_ac7_every_record_per_mode_none_raises_facet_input_error_naming_the_flag():
    pmc = _pmc()
    cohort = _FakeCohort(
        cases=(
            _FakeCase(case_id="a", per_mode=None),
            _FakeCase(case_id="b", per_mode=None),
        )
    )
    with pytest.raises(FacetInputError, match="per_mode=True"):
        pmc.summarise_run_per_mode(cohort, run_id="forgot-flag")


# =========================================================================== #
# AC8: detection rates read verbatim from item 054, never recomputed
# =========================================================================== #


def _fake_cohort_metrics(per_mode_entries) -> CohortMetrics:
    return CohortMetrics(
        counts=ConfusionCounts(tp=0, fp=0, tn=0, fn=0),
        false_positive_rate=None,
        sensitivity=None,
        specificity=None,
        per_mode=tuple(per_mode_entries),
        dice_vs_flag=CorrelationResult(coefficient=None, n=0, method="pearson", x_variable="mean_dice", y_variable="flagged"),
        feature_divergence_vs_flag=CorrelationResult(coefficient=None, n=0, method="pearson", x_variable="case_divergence", y_variable="flagged"),
        n_cases=0,
    )


def test_ac8_detection_rate_and_n_detection_cases_match_per_mode_sensitivity_verbatim():
    pmc = _pmc()
    sens3 = PerModeSensitivity(
        failure_mode=3, failure_mode_name="rogue islands", n_cases=5,
        n_caught=4, n_caught_by_designated_rule=3, sensitivity=0.6, caught_rate=0.8,
    )
    sens5 = PerModeSensitivity(
        failure_mode=5, failure_mode_name="missing level", n_cases=2,
        n_caught=2, n_caught_by_designated_rule=2, sensitivity=1.0, caught_rate=1.0,
    )
    metrics = _fake_cohort_metrics([sens3, sens5])
    cohort = _FakeCohort(cases=(_fake_case("a", _full(0.0)),))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r", metrics=metrics)

    agg3 = summary.by_mode(3)
    assert agg3.detection_rate == 0.6
    assert agg3.n_detection_cases == 5

    agg5 = summary.by_mode(5)
    assert agg5.detection_rate == 1.0
    assert agg5.n_detection_cases == 2


def test_ac8_modes_absent_from_metrics_are_none_and_zero():
    pmc = _pmc()
    sens3 = PerModeSensitivity(
        failure_mode=3, failure_mode_name="rogue islands", n_cases=5,
        n_caught=4, n_caught_by_designated_rule=3, sensitivity=0.6, caught_rate=0.8,
    )
    metrics = _fake_cohort_metrics([sens3])
    cohort = _FakeCohort(cases=(_fake_case("a", _full(0.0)),))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r", metrics=metrics)

    for mode in (1, 2, 4, 5, 6, 7, 8):
        agg = summary.by_mode(mode)
        assert agg.detection_rate is None, mode
        assert agg.n_detection_cases == 0, mode


def test_ac8_metrics_none_default_every_detection_rate_none_and_zero():
    pmc = _pmc()
    cohort = _FakeCohort(cases=(_fake_case("a", _full(0.0)),))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")
    for agg in summary.per_mode:
        assert agg.detection_rate is None
        assert agg.n_detection_cases == 0


# =========================================================================== #
# AC9: the aggregate Dice context comes from item 099's carried fields;
# drift guard proves no new Dice/Jaccard/overlap arithmetic
# =========================================================================== #


def test_ac9_mean_dice_and_volume_weighted_dice_are_means_over_non_none_cases():
    pmc = _pmc()
    case_a = _fake_case("a", _full(0.0), mean_dice=0.8, volume_weighted_dice=0.7)
    case_b = _fake_case("b", _full(0.0), mean_dice=None, volume_weighted_dice=0.9)
    case_c = _fake_case("c", _full(0.0), mean_dice=0.6, volume_weighted_dice=None)
    cohort = _FakeCohort(cases=(case_a, case_b, case_c))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")
    assert summary.mean_dice == pytest.approx((0.8 + 0.6) / 2)
    assert summary.volume_weighted_dice == pytest.approx((0.7 + 0.9) / 2)


def test_ac9_none_when_no_case_carried_a_dice_value():
    pmc = _pmc()
    case_a = _fake_case("a", _full(0.0), mean_dice=None, volume_weighted_dice=None)
    cohort = _FakeCohort(cases=(case_a,))
    summary = pmc.summarise_run_per_mode(cohort, run_id="r")
    assert summary.mean_dice is None
    assert summary.volume_weighted_dice is None


def test_ac9_no_compute_overlap_call_in_module_source():
    source = _per_mode_cohort_source()
    assert "compute_overlap(" not in source


def test_ac9_no_dice_or_jaccard_arithmetic_literal_substrings():
    source = _per_mode_cohort_source()
    for forbidden in ("2.0 *", "2 *", "jaccard =", "dice ="):
        assert forbidden not in source, forbidden


# =========================================================================== #
# AC10: compare_runs returns eight deltas, mode order, documented arithmetic
# =========================================================================== #


def test_ac10_eight_deltas_mode_order_value_a_b_and_delta():
    pmc = _pmc()
    a = _summary("a", ("c1", "c2"), _full(1.0))
    b = _summary("b", ("c1", "c2"), _full(2.0))
    cmp = pmc.compare_runs(a, b)
    assert len(cmp.per_mode) == 8
    assert tuple(d.failure_mode for d in cmp.per_mode) == tuple(range(1, 9))
    for d in cmp.per_mode:
        assert d.value_a == 1.0
        assert d.value_b == 2.0
        assert d.delta == pytest.approx(1.0)


def test_ac10_delta_is_none_when_value_a_is_none():
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(1.0), 3: None})
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    d3 = cmp.by_mode(3)
    assert d3.value_a is None
    assert d3.delta is None


def test_ac10_delta_is_none_when_value_b_is_none():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(1.0))
    b = _summary("b", ("c1",), {**_full(1.0), 3: None})
    cmp = pmc.compare_runs(a, b)
    d3 = cmp.by_mode(3)
    assert d3.value_b is None
    assert d3.delta is None


def test_ac10_mode_absent_in_a_present_in_b_delta_none_not_zero():
    """Adversarial: a case gained a candidate between runs -- the mode must
    not be silently treated as a 0.0-baseline delta."""
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(2.0), 1: None})
    b = _summary("b", ("c1",), _full(2.0))
    cmp = pmc.compare_runs(a, b)
    d1 = cmp.by_mode(1)
    assert d1.delta is None
    assert d1.normalised_delta is None
    assert d1.worsened is None


# =========================================================================== #
# AC11: scale/normalised_delta follow the stated formula
# =========================================================================== #


def test_ac11_scale_and_normalised_delta_general_case():
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(0.0), 1: 0.2})
    b = _summary("b", ("c1",), {**_full(0.0), 1: 0.8})
    cmp = pmc.compare_runs(a, b)
    d1 = cmp.by_mode(1)
    assert d1.scale == pytest.approx(0.8)
    assert d1.normalised_delta == pytest.approx(0.75)


def test_ac11_scale_zero_yields_normalised_delta_exactly_zero_not_zerodivision():
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(0.0), 1: 0.0})
    b = _summary("b", ("c1",), {**_full(0.0), 1: 0.0})
    cmp = pmc.compare_runs(a, b)
    d1 = cmp.by_mode(1)
    assert d1.scale == 0.0
    assert d1.normalised_delta == 0.0


@pytest.mark.parametrize(
    "value_a, value_b",
    [(None, 0.5), (0.5, None), (None, None)],
)
def test_ac11_normalised_delta_is_none_when_delta_is_none(value_a, value_b):
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(0.0), 1: value_a})
    b = _summary("b", ("c1",), {**_full(0.0), 1: value_b})
    cmp = pmc.compare_runs(a, b)
    d1 = cmp.by_mode(1)
    assert d1.normalised_delta is None


def test_ac11_never_nan_or_inf_across_full_comparison():
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(1.0), 1: 0.0})
    b = _summary("b", ("c1",), {**_full(1.0), 1: 0.0})
    cmp = pmc.compare_runs(a, b)
    for d in cmp.per_mode:
        if d.normalised_delta is not None:
            assert math.isfinite(d.normalised_delta)
        if d.scale is not None:
            assert math.isfinite(d.scale)


# =========================================================================== #
# AC12: worsened is direction-aware; mode 2 never reported backwards
# =========================================================================== #


def test_ac12_worsened_is_none_iff_delta_is_none():
    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(0.0), 1: None})
    b = _summary("b", ("c1",), _full(0.0))
    cmp = pmc.compare_runs(a, b)
    assert cmp.by_mode(1).worsened is None


@pytest.mark.parametrize(
    "mode, value_a, value_b, expected_worsened",
    [
        (1, 0.2, 0.8, True),   # increases, positive delta -> worse
        (1, 0.8, 0.2, False),  # increases, negative delta -> better
        (2, 1.0, 0.5, True),   # decreases, negative delta -> worse
        (2, 0.5, 1.0, False),  # decreases, positive delta -> better
        (1, 0.5, 0.5, False),  # delta == 0.0 -> never worsened
        (2, 1.0, 1.0, False),  # delta == 0.0 -> never worsened
    ],
)
def test_ac12_worsened_direction_matrix(mode, value_a, value_b, expected_worsened):
    pmc = _pmc()
    baseline = PER_MODE_METRIC_SPECS[mode].baseline
    a_values = {**_full(baseline), mode: value_a}
    b_values = {**_full(baseline), mode: value_b}
    a = _summary("a", ("c1",), a_values)
    b = _summary("b", ("c1",), b_values)
    cmp = pmc.compare_runs(a, b)
    assert cmp.by_mode(mode).worsened is expected_worsened


# =========================================================================== #
# AC13: attributed_mode is the largest normalised move, ties to lowest mode
# =========================================================================== #


def test_ac13_attributed_mode_is_the_largest_normalised_move():
    # Mode 1's value_a is deliberately offset *away* from its own baseline
    # (0.0) rather than left exactly on it: `normalised_delta` saturates to
    # +/-1.0 whenever either side of a delta sits exactly on the mode's
    # baseline (scale == abs(the other side - baseline)), so leaving a
    # non-target mode pinned on baseline risks an accidental tie with the
    # target mode instead of unambiguously testing "largest". With mode 1
    # offset to 0.1->0.5 (normalised_delta == 0.8) and mode 3 driven fully
    # off its own baseline 0.0->0.9 (normalised_delta == 1.0), mode 3 is the
    # strictly largest move with no tie-break involved.
    pmc = _pmc()
    a_values = {**_full(0.0), 1: 0.1}
    b_values = {**_full(0.0), 3: 0.9, 1: 0.5}
    a = _summary("a", ("c1",), a_values)
    b = _summary("b", ("c1",), b_values)
    cmp = pmc.compare_runs(a, b)
    assert abs(cmp.by_mode(1).normalised_delta) == pytest.approx(0.8)
    assert abs(cmp.by_mode(3).normalised_delta) == pytest.approx(1.0)
    assert cmp.attributed_mode == 3
    assert cmp.attributed_mode_name == PER_MODE_METRIC_SPECS[3].failure_mode_name
    assert cmp.attributed_metric_name == PER_MODE_METRIC_SPECS[3].metric_name


def test_ac13_exact_tie_breaks_to_lowest_mode():
    pmc = _pmc()
    a_values = {**_full(0.0), 1: 0.0, 2: 1.0}
    b_values = {**_full(0.0), 1: 1.0, 2: 0.0}
    a = _summary("a", ("c1",), a_values)
    b = _summary("b", ("c1",), b_values)
    cmp = pmc.compare_runs(a, b)
    d1 = cmp.by_mode(1)
    d2 = cmp.by_mode(2)
    assert abs(d1.normalised_delta) == pytest.approx(abs(d2.normalised_delta))
    assert cmp.attributed_mode == 1


def test_ac13_all_zero_or_none_normalised_deltas_yield_no_attribution():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(0.0))
    cmp = pmc.compare_runs(a, b)
    assert cmp.attributed_mode is None
    assert cmp.attributed_mode_name is None
    assert cmp.attributed_metric_name is None


def test_ac13_all_none_normalised_deltas_yield_no_attribution():
    pmc = _pmc()
    a = _summary("a", ("c1",), {m: None for m in range(1, 9)})
    b = _summary("b", ("c1",), {m: None for m in range(1, 9)})
    cmp = pmc.compare_runs(a, b)
    assert cmp.attributed_mode is None


# =========================================================================== #
# AC14: comparing a run against itself is an all-zero report
# =========================================================================== #


def test_ac14_self_comparison_is_all_zero():
    pmc = _pmc()
    s = _summary("r", ("c1", "c2"), {1: 0.3, 2: 0.7, 3: 4.0, 4: 0.1, 5: 2.0, 6: 1.0, 7: 3.0, 8: 500.0}, mean_dice=0.9, volume_weighted_dice=0.85)
    cmp = pmc.compare_runs(s, s)
    for d in cmp.per_mode:
        assert d.delta == 0.0, d.failure_mode
        assert d.normalised_delta == 0.0, d.failure_mode
        assert d.worsened is False, d.failure_mode
    assert cmp.mean_dice_delta == 0.0
    assert cmp.volume_weighted_dice_delta == 0.0
    assert cmp.attributed_mode is None


# =========================================================================== #
# AC15: mismatched cohorts are rejected; reordered same set compares fine
# =========================================================================== #


def test_ac15_mismatched_case_ids_raise_facet_input_error_naming_the_id():
    pmc = _pmc()
    a = _summary("a", ("c1", "c2"), _full(0.0))
    b = _summary("b", ("c1", "c3"), _full(0.0))
    with pytest.raises(FacetInputError) as excinfo:
        pmc.compare_runs(a, b)
    message = str(excinfo.value)
    assert "c2" in message or "c3" in message


def test_ac15_reordered_same_set_compares_successfully():
    pmc = _pmc()
    a = _summary("a", ("c1", "c2", "c3"), _full(0.0))
    b = _summary("b", ("c3", "c1", "c2"), _full(1.0))
    cmp = pmc.compare_runs(a, b)  # must not raise
    assert set(cmp.case_ids) == {"c1", "c2", "c3"}
    assert cmp.n_cases == 3


def test_ac15_identical_run_ids_on_both_sides_is_allowed():
    pmc = _pmc()
    a = _summary("same-id", ("c1",), _full(0.0))
    b = _summary("same-id", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)  # must not raise
    assert cmp.run_a_id == "same-id"
    assert cmp.run_b_id == "same-id"


# =========================================================================== #
# AC16: the demonstrator -- island stripping attributes to mode 3 while
# aggregate Dice barely moves (Stage 18's thesis, asserted)
# =========================================================================== #


def _strip_stray_islands(arr: np.ndarray) -> np.ndarray:
    """Test-only "post-processing step": for every non-zero label, keep only
    its largest 6-connected component, zeroing every other (stray) piece --
    the demonstrator's injected behavioural change."""
    import scipy.ndimage as ndi

    out = np.zeros_like(arr)
    for label in np.unique(arr):
        if label == 0:
            continue
        mask = arr == label
        labelled, n = ndi.label(mask)
        if n <= 1:
            out[mask] = label
            continue
        sizes = ndi.sum(mask, labelled, index=range(1, n + 1))
        dominant = int(np.argmax(sizes)) + 1
        out[labelled == dominant] = label
    return out


@pytest.fixture(scope="module")
def demonstrator_comparison():
    pmc = _pmc()
    harness = _harness_mod()
    islands_arr = _arr("mode3_inject_islands")
    stripped_arr = _strip_stray_islands(islands_arr)

    def _cases(candidate_islands):
        return [
            harness.EvaluationCase(
                case_id="clean",
                gt=_GT_ARRAY,
                candidate=_GT_ARRAY,
                expected={"expected_verdict": "pass"},
            ),
            harness.EvaluationCase(
                case_id="islands",
                gt=_GT_ARRAY,
                candidate=candidate_islands,
                expected={"expected_verdict": "flagged-for-review"},
            ),
        ]

    cohort_a = harness.evaluate_cohort(_cases(islands_arr), _CONFIG, per_mode=True)
    cohort_b = harness.evaluate_cohort(_cases(stripped_arr), _CONFIG, per_mode=True)

    summary_a = pmc.summarise_run_per_mode(cohort_a, run_id="runA_islands_on")
    summary_b = pmc.summarise_run_per_mode(cohort_b, run_id="runB_islands_stripped")
    return pmc.compare_runs(summary_a, summary_b)


def test_ac16_attributed_mode_is_three():
    # Deliberately NOT built on the shared `demonstrator_comparison` fixture:
    # driving the real `mode3_inject_islands` corpus case through
    # `_strip_stray_islands` reconstructs the candidate to *exactly* GT, so
    # modes 1 (unanchored_foreground_fraction), 2
    # (min_dominant_component_fraction) and 3 (rogue_island_count) ALL
    # independently land on their own baseline and all saturate
    # `abs(normalised_delta)` to 1.0 -- a genuine three-way tie that AC13's
    # documented tie-break ("ties to the lowest mode") then resolves to mode
    # 1, not mode 3 (see docs/aide/insights.md, item 101). That collision is
    # a property of this specific fixture, not of attribution itself, so
    # this test instead hand-builds the two runs AC16 describes: a
    # mode-3-specific change (rogue islands present, then removed) attributed
    # to mode 3 while unrelated modes 1/2 move only slightly and never touch
    # their own baseline, so there is no tie to break.
    pmc = _pmc()
    a_values = {**_full(0.0), 1: 0.05, 2: 0.9, 3: 8.0}
    b_values = {**_full(0.0), 1: 0.03, 2: 0.95, 3: 0.0}
    a = _summary("runA_islands_on", ("islands",), a_values)
    b = _summary("runB_islands_stripped", ("islands",), b_values)
    cmp = pmc.compare_runs(a, b)
    assert abs(cmp.by_mode(1).normalised_delta) < 1.0
    assert abs(cmp.by_mode(2).normalised_delta) < 1.0
    assert abs(cmp.by_mode(3).normalised_delta) == pytest.approx(1.0)
    assert cmp.attributed_mode == 3
    assert cmp.attributed_mode_name == PER_MODE_METRIC_SPECS[3].failure_mode_name
    assert cmp.attributed_metric_name == PER_MODE_METRIC_SPECS[3].metric_name


def test_ac16_mode3_worsened_is_false_islands_removed_is_an_improvement(demonstrator_comparison):
    d3 = demonstrator_comparison.by_mode(3)
    assert d3.worsened is False


def test_ac16_normalised_delta_exceeds_mean_dice_delta(demonstrator_comparison):
    d3 = demonstrator_comparison.by_mode(3)
    assert abs(d3.normalised_delta) > abs(demonstrator_comparison.mean_dice_delta)


def test_ac16_mean_dice_delta_is_small_in_absolute_terms(demonstrator_comparison):
    """The negative half: aggregate Dice genuinely fails to attribute what
    the per-mode delta attributes -- it barely moves."""
    assert abs(demonstrator_comparison.mean_dice_delta) < 0.05


def test_ac16_mode3_normalised_delta_is_a_large_fraction_of_its_excursion(demonstrator_comparison):
    d3 = demonstrator_comparison.by_mode(3)
    assert abs(d3.normalised_delta) > 0.5


# =========================================================================== #
# AC17: both records round-trip through JSON and back into dataclasses
# =========================================================================== #


def test_ac17_run_per_mode_summary_to_dict_round_trips_through_json():
    summary = _summary("r", ("c1", "c2"), _full(1.0), mean_dice=0.7, volume_weighted_dice=0.6)
    d = summary.to_dict()
    assert json.loads(json.dumps(d)) == d


def test_ac17_run_comparison_to_dict_round_trips_through_json():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    d = cmp.to_dict()
    assert json.loads(json.dumps(d)) == d


def test_ac17_run_per_mode_summary_from_dict_round_trip_equality():
    pmc = _pmc()
    summary = _summary("r", ("c1", "c2"), _full(1.0), mean_dice=0.7, volume_weighted_dice=0.6)
    rebuilt = pmc.RunPerModeSummary.from_dict(summary.to_dict())
    assert rebuilt == summary


def test_ac17_run_per_mode_summary_from_dict_round_trip_real_fixture(real_cohort):
    pmc = _pmc()
    summary = pmc.summarise_run_per_mode(real_cohort, run_id="real")
    rebuilt = pmc.RunPerModeSummary.from_dict(summary.to_dict())
    assert rebuilt == summary


# =========================================================================== #
# AC18: both to_dict()s are plain JSON, no numpy leakage
# =========================================================================== #


def _assert_json_native(value) -> None:
    if value is None:
        return
    t = type(value)
    if t is dict:
        for k, v in value.items():
            assert type(k) is str, f"non-string mapping key {k!r}"
            _assert_json_native(v)
    elif t is list:
        for v in value:
            _assert_json_native(v)
    elif t in (str, float, int, bool):
        return
    else:
        raise AssertionError(f"non-JSON-native type {t!r} in to_dict() output: {value!r}")


def test_ac18_run_per_mode_summary_to_dict_is_json_native():
    summary = _summary("r", ("c1",), _full(1.0))
    d = summary.to_dict()
    assert type(d) is dict
    _assert_json_native(d)


def test_ac18_run_comparison_to_dict_is_json_native():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    d = cmp.to_dict()
    assert type(d) is dict
    _assert_json_native(d)


def test_ac18_real_fixture_values_are_plain_float_or_none_never_numpy(real_cohort):
    pmc = _pmc()
    summary = pmc.summarise_run_per_mode(real_cohort, run_id="real")
    for agg in summary.per_mode:
        for field in ("mean", "minimum", "maximum", "total", "detection_rate"):
            value = getattr(agg, field)
            assert value is None or type(value) is float, (field, agg.failure_mode)


# =========================================================================== #
# AC19: the evaluation report gains an optional additive block; v0 stays v0
# =========================================================================== #


def _real_cohort_metrics(real_cohort):
    from segfacet.eval.metrics import compute_cohort_metrics

    return compute_cohort_metrics(real_cohort)


def test_ac19_build_evaluation_report_without_per_mode_summary_omits_the_key(real_cohort):
    from segfacet.eval.report import EvaluationProvenance, build_evaluation_report

    metrics = _real_cohort_metrics(real_cohort)
    provenance = EvaluationProvenance(
        cohort_id="c", cohort_size=metrics.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = build_evaluation_report(metrics, provenance)
    assert "per_mode_magnitude" not in report


def test_ac19_build_evaluation_report_with_per_mode_summary_embeds_it_and_validates(real_cohort):
    from segfacet.eval.report import EvaluationProvenance, build_evaluation_report

    pmc = _pmc()
    metrics = _real_cohort_metrics(real_cohort)
    summary = pmc.summarise_run_per_mode(real_cohort, run_id="real")
    provenance = EvaluationProvenance(
        cohort_id="c", cohort_size=metrics.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = build_evaluation_report(metrics, provenance, per_mode_summary=summary)
    assert report["per_mode_magnitude"] == summary.to_dict()


def _eval_report_schema() -> dict:
    import importlib.resources as pkg_resources

    import segfacet.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("eval_report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def test_ac19_schema_version_and_const_remain_01():
    import segfacet.eval.report as report_mod

    assert report_mod.EVAL_REPORT_SCHEMA_VERSION == "0.1"
    assert _eval_report_schema()["properties"]["schema_version"]["const"] == "0.1"


def test_ac19_per_mode_magnitude_not_in_required():
    assert "per_mode_magnitude" not in _eval_report_schema().get("required", [])


# =========================================================================== #
# AC20: the comparison artifact has its own bundled, versioned schema
# =========================================================================== #


def _comparison_schema() -> dict:
    import importlib.resources as pkg_resources

    import segfacet.eval as eval_pkg

    ref = pkg_resources.files(eval_pkg).joinpath("per_mode_comparison_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def test_ac20_schema_version_constant_is_01():
    import segfacet.eval.report as report_mod

    assert report_mod.PER_MODE_COMPARISON_SCHEMA_VERSION == "0.1"


def test_ac20_schema_root_shape():
    schema = _comparison_schema()
    assert schema.get("additionalProperties") is False
    assert set(schema["required"]) == {"schema_version", "run_a", "run_b", "comparison"}


def test_ac20_build_run_comparison_report_validates(real_cohort):
    import segfacet.eval.report as report_mod

    pmc = _pmc()
    summary_a = pmc.summarise_run_per_mode(real_cohort, run_id="a")
    summary_b = pmc.summarise_run_per_mode(real_cohort, run_id="b")
    cmp = pmc.compare_runs(summary_a, summary_b)

    provenance_a = report_mod.EvaluationProvenance(
        cohort_id="a", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    provenance_b = report_mod.EvaluationProvenance(
        cohort_id="b", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = report_mod.build_run_comparison_report(cmp, provenance_a, provenance_b)

    import jsonschema

    jsonschema.validate(report, _comparison_schema())
    assert set(report.keys()) <= {"schema_version", "run_a", "run_b", "comparison"}
    assert report["schema_version"] == "0.1"


def test_ac20_deleting_a_required_key_fails_validation(real_cohort):
    import jsonschema

    import segfacet.eval.report as report_mod

    pmc = _pmc()
    summary_a = pmc.summarise_run_per_mode(real_cohort, run_id="a")
    summary_b = pmc.summarise_run_per_mode(real_cohort, run_id="b")
    cmp = pmc.compare_runs(summary_a, summary_b)
    provenance_a = report_mod.EvaluationProvenance(
        cohort_id="a", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    provenance_b = report_mod.EvaluationProvenance(
        cohort_id="b", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = report_mod.build_run_comparison_report(cmp, provenance_a, provenance_b)
    del report["comparison"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, _comparison_schema())


# =========================================================================== #
# AC21: both artifacts are byte-reproducible within a session
# =========================================================================== #


def test_ac21_comparison_artifact_byte_identical_across_two_writes(tmp_path, real_cohort):
    import segfacet.eval.report as report_mod

    pmc = _pmc()
    summary_a = pmc.summarise_run_per_mode(real_cohort, run_id="a")
    summary_b = pmc.summarise_run_per_mode(real_cohort, run_id="b")
    cmp = pmc.compare_runs(summary_a, summary_b)
    provenance_a = report_mod.EvaluationProvenance(
        cohort_id="a", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    provenance_b = report_mod.EvaluationProvenance(
        cohort_id="b", cohort_size=real_cohort.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = report_mod.build_run_comparison_report(cmp, provenance_a, provenance_b)

    dest1 = tmp_path / "one" / "comparison.json"
    dest2 = tmp_path / "two" / "comparison.json"
    report_mod.write_evaluation_report(report, dest1)
    report_mod.write_evaluation_report(report, dest2)

    bytes1 = dest1.read_bytes()
    bytes2 = dest2.read_bytes()
    assert bytes1 == bytes2
    assert bytes1.endswith(b"\n")
    assert not bytes1.endswith(b"\n\n")


def test_ac21_evaluation_report_with_per_mode_magnitude_byte_identical_across_two_writes(tmp_path, real_cohort):
    from segfacet.eval.report import EvaluationProvenance, build_evaluation_report, write_evaluation_report

    pmc = _pmc()
    metrics = _real_cohort_metrics(real_cohort)
    summary = pmc.summarise_run_per_mode(real_cohort, run_id="real")
    provenance = EvaluationProvenance(
        cohort_id="c", cohort_size=metrics.n_cases, config_version=_CONFIG.schema_version,
        build_date="2026-07-27",
    )
    report = build_evaluation_report(metrics, provenance, per_mode_summary=summary)

    dest1 = tmp_path / "one" / "eval_report.json"
    dest2 = tmp_path / "two" / "eval_report.json"
    write_evaluation_report(report, dest1)
    write_evaluation_report(report, dest2)

    bytes1 = dest1.read_bytes()
    bytes2 = dest2.read_bytes()
    assert bytes1 == bytes2
    assert bytes1.endswith(b"\n")
    assert not bytes1.endswith(b"\n\n")


# =========================================================================== #
# AC22: the human rendering names the implicated mode in words
# =========================================================================== #


def test_ac22_names_attributed_mode_metric_run_ids_and_dice_delta(demonstrator_comparison):
    import segfacet.eval.report as report_mod

    text = report_mod.render_run_comparison(demonstrator_comparison)
    assert isinstance(text, str) and text
    assert PER_MODE_METRIC_SPECS[3].failure_mode_name in text
    assert PER_MODE_METRIC_SPECS[3].metric_name in text
    assert demonstrator_comparison.run_a_id in text
    assert demonstrator_comparison.run_b_id in text
    assert "None" not in text


def test_ac22_all_zero_comparison_says_so_explicitly_never_names_a_mode():
    import segfacet.eval.report as report_mod
    from segfacet.synth.perturbation import FAILURE_MODE_NAMES

    pmc = _pmc()
    s = _summary("r", ("c1",), _full(0.0))
    cmp = pmc.compare_runs(s, s)
    text = report_mod.render_run_comparison(cmp)
    assert isinstance(text, str) and text
    assert "None" not in text
    for mode in range(1, 9):
        assert FAILURE_MODE_NAMES[mode] not in text


def test_ac22_none_values_render_as_n_a_never_literal_none():
    import segfacet.eval.report as report_mod

    pmc = _pmc()
    a = _summary("a", ("c1",), {**_full(0.0), 1: None})
    b = _summary("b", ("c1",), {**_full(0.0), 1: None})
    cmp = pmc.compare_runs(a, b)
    text = report_mod.render_run_comparison(cmp)
    assert "None" not in text
    assert "n/a" in text


# =========================================================================== #
# AC26: the aggregation/comparison are pure and idempotent
# =========================================================================== #


def test_ac26_summarise_run_per_mode_does_not_mutate_the_cohort(real_cohort):
    pmc = _pmc()
    before = real_cohort.to_dict()
    pmc.summarise_run_per_mode(real_cohort, run_id="r")
    after = real_cohort.to_dict()
    assert before == after


def test_ac26_compare_runs_does_not_mutate_its_summaries():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    a_before = a.to_dict()
    b_before = b.to_dict()
    pmc.compare_runs(a, b)
    assert a.to_dict() == a_before
    assert b.to_dict() == b_before


def test_ac26_summarise_run_per_mode_is_idempotent(real_cohort):
    pmc = _pmc()
    first = pmc.summarise_run_per_mode(real_cohort, run_id="r")
    second = pmc.summarise_run_per_mode(real_cohort, run_id="r")
    assert first == second


def test_ac26_compare_runs_is_idempotent():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    first = pmc.compare_runs(a, b)
    second = pmc.compare_runs(a, b)
    assert first == second


def test_ac26_summarise_run_per_mode_opens_no_file_and_reads_no_clock(monkeypatch, real_cohort):
    pmc = _pmc()
    calls = {"open": 0, "write_bytes": 0, "time": 0}
    real_open = builtins.open

    def _tracking_open(*args, **kwargs):
        calls["open"] += 1
        return real_open(*args, **kwargs)

    def _tracking_write_bytes(self, *args, **kwargs):
        calls["write_bytes"] += 1
        raise AssertionError("Path.write_bytes must not be called by summarise_run_per_mode")

    real_time = time.time

    def _tracking_time():
        calls["time"] += 1
        return real_time()

    monkeypatch.setattr(builtins, "open", _tracking_open)
    monkeypatch.setattr(Path, "write_bytes", _tracking_write_bytes)
    monkeypatch.setattr(time, "time", _tracking_time)

    pmc.summarise_run_per_mode(real_cohort, run_id="r")

    assert calls["open"] == 0
    assert calls["write_bytes"] == 0
    assert calls["time"] == 0


def test_ac26_compare_runs_opens_no_file_and_reads_no_clock(monkeypatch):
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))

    calls = {"open": 0, "write_bytes": 0, "time": 0}
    real_open = builtins.open

    def _tracking_open(*args, **kwargs):
        calls["open"] += 1
        return real_open(*args, **kwargs)

    def _tracking_write_bytes(self, *args, **kwargs):
        calls["write_bytes"] += 1
        raise AssertionError("Path.write_bytes must not be called by compare_runs")

    real_time = time.time

    def _tracking_time():
        calls["time"] += 1
        return real_time()

    monkeypatch.setattr(builtins, "open", _tracking_open)
    monkeypatch.setattr(Path, "write_bytes", _tracking_write_bytes)
    monkeypatch.setattr(time, "time", _tracking_time)

    pmc.compare_runs(a, b)

    assert calls["open"] == 0
    assert calls["write_bytes"] == 0
    assert calls["time"] == 0


# =========================================================================== #
# AC27: the scope fence holds
# =========================================================================== #

_SEGFACET_SRC = Path(__import__("segfacet").__file__).resolve().parent
_REPO_ROOT = _SEGFACET_SRC.parent.parent
_CORPUS_DIR = _REPO_ROOT / "tests" / "corpus"

_PRE_101_HASHES = {
    "eval/per_mode.py": "5fd77f74b33dccbe32c3b899a9d2a4e1f051df03a5deb9a3a0cda7058ff0d9c6",
    "eval/metrics.py": "15a21e7d9c8d738bfe5755637f736e60fd86d620c6117dd39a5d3b3bfa8bff8a",
    "eval/overlap.py": "aafeee545c2a719ba7f25e6ef03abeb3c2b845105691ca9114d121479b39d5b5",
    "eval/severity_ladder.py": "9921eede59824ca596452a9a7ea80d8995e591a168d775b195d10396a0916b08",
    "eval/calibrate.py": "cc15c377ce6199c5ad88375f07ad206b9c4711560cc0397ff756c0767fc2c760",
    "report_schema_v0.json": "8c7b48c1fcfc82edf49187c8aa912ac42470b20f53fd739c9b65f0bbf76f4a4b",
}
_PRE_101_HEURISTICS_HASH = "92cdc63e9a9bcef3c4ebd6c9b5567e80c30a3077bd3613d635c443bf055d19c4"
_PRE_101_FEATURES_HASH = "92cc4fba7269f8c77c33441ea870b7eb6224d561a03c192028fa03560a6f60ce"
_PRE_101_SYNTH_HASH = "8ed4d4d5d1d26c36077eef2a35569d8db6687d51d7551e94f38e76f8d7323205"
_PRE_101_CORPUS_HASH = "aad04c1b0e42074a11342b24dc94c7f2ec896cda1664efeee7c5fc5b0ec4f547"


def _combined_hash(files, base: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(files):
        h.update(f.relative_to(base).as_posix().encode())
        h.update(f.read_bytes())
    return h.hexdigest()


@pytest.mark.parametrize("relpath", sorted(_PRE_101_HASHES))
def test_ac27_named_untouched_file_byte_identical_to_pre_101_state(relpath):
    path = _SEGFACET_SRC / relpath
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _PRE_101_HASHES[relpath], relpath


def test_ac27_heuristics_package_byte_identical_to_pre_101_state():
    files = sorted((_SEGFACET_SRC / "heuristics").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_101_HEURISTICS_HASH


def test_ac27_features_package_byte_identical_to_pre_101_state():
    files = sorted((_SEGFACET_SRC / "features").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_101_FEATURES_HASH


def test_ac27_synth_package_byte_identical_to_pre_101_state():
    files = sorted((_SEGFACET_SRC / "synth").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_101_SYNTH_HASH


def test_ac27_corpus_byte_identical_to_pre_101_state():
    files = sorted(p for p in _CORPUS_DIR.rglob("*") if p.is_file())
    assert _combined_hash(files, _CORPUS_DIR) == _PRE_101_CORPUS_HASH


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_by_mode_zero_raises_key_error_on_summary():
    summary = _summary("r", ("c1",), _full(0.0))
    with pytest.raises(KeyError):
        summary.by_mode(0)


def test_adv_by_mode_nine_raises_key_error_on_summary():
    summary = _summary("r", ("c1",), _full(0.0))
    with pytest.raises(KeyError):
        summary.by_mode(9)


def test_adv_by_mode_zero_and_nine_raise_key_error_on_comparison():
    pmc = _pmc()
    a = _summary("a", ("c1",), _full(0.0))
    b = _summary("b", ("c1",), _full(1.0))
    cmp = pmc.compare_runs(a, b)
    with pytest.raises(KeyError):
        cmp.by_mode(0)
    with pytest.raises(KeyError):
        cmp.by_mode(9)


def test_adv_from_dict_truncated_block_six_entries_raises_facet_input_error():
    pmc = _pmc()
    summary = _summary("r", ("c1",), _full(0.0))
    d = summary.to_dict()
    d["per_mode"] = d["per_mode"][:6]
    with pytest.raises(FacetInputError):
        pmc.RunPerModeSummary.from_dict(d)


def test_adv_from_dict_non_str_run_id_raises_facet_input_error():
    pmc = _pmc()
    summary = _summary("r", ("c1",), _full(0.0))
    d = summary.to_dict()
    d["run_id"] = 12345
    with pytest.raises(FacetInputError):
        pmc.RunPerModeSummary.from_dict(d)


def test_adv_from_dict_missing_case_ids_raises_facet_input_error():
    pmc = _pmc()
    summary = _summary("r", ("c1",), _full(0.0))
    d = summary.to_dict()
    del d["case_ids"]
    with pytest.raises(FacetInputError):
        pmc.RunPerModeSummary.from_dict(d)


def test_adv_from_dict_not_a_mapping_raises_facet_input_error():
    pmc = _pmc()
    with pytest.raises(FacetInputError):
        pmc.RunPerModeSummary.from_dict(["not", "a", "mapping"])
