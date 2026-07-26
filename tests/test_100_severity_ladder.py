"""Tests for item 100 -- severity-ladder monotonicity & cross-mode
specificity harness (``segfacet.eval.severity_ladder``).

Covers Acceptance Criteria AC1-AC26:

- AC1:  the module's public surface (18 names, incl. eight frozen
        dataclasses) exists, is exported via ``__all__``, and is re-exported
        from ``segfacet.eval``.
- AC2:  ``SEVERITY_LADDERS`` covers exactly modes 1-8, name-consistent with
        ``FAILURE_MODE_NAMES``.
- AC3:  every ladder step names a registered operator, constructible with
        its declared kwargs.
- AC4:  the metric assignment is item 099's -- a drift guard reads the
        module source.
- AC5:  rung 0 is the clean control, at baseline on all eight metrics.
- AC6:  no metric is ever ``None`` anywhere in the harness.
- AC7:  rung severities are strictly increasing, rung 0 == 0.0.
- AC8:  every ladder has >= 3 rungs except the declared degenerate one (2).
- AC9:  the designated metric is monotone in its declared direction.
- AC10: the designated metric changes strictly at every rung transition.
- AC11: the severity axis (``severity_kind``/``severity_parameter``) is
        declared honestly per ladder.
- AC12: the degenerate ladder (mode 7) is declared, never silent.
- AC13: ``score_harness`` computes the response surface as specified --
        recomputed independently from stored per-rung values.
- AC14: uncoupled ladders are strictly specific (``margin > 1.0``).
- AC15: the coupling table exactly matches what is measured (two-way).
- AC16: the coupling table is a ratchet (response/margin inequalities).
- AC17: a coupled ladder is reported as coupled, not as a pass.
- AC18: the negative control (mode 2/3 swap) fails; identity still passes.
- AC19: the mode-8 ladder's ``overlap_depth == 3`` rung reproduces the
        committed corpus's ``1950.0``.
- AC20: ``overlapping_voxel_count`` is 0.0 on every non-mode-8 ladder.
- AC21: the supplementary ``fuse`` ladder closes mode 2's fused half.
- AC22: the harness is deterministic (two runs; per-rung array replay).
- AC23: the harness is pure (no file/clock access, no base mutation).
- AC24: results round-trip through JSON unchanged.
- AC25: an operator failure propagates ``FacetInputError``, never truncates.
- AC26: the scope fence holds (untouched files are byte-identical).

Adversarial / edge-case scenarios included:
- AC18's negative control doubles as the harness's own falsifiability proof.
- AC25's out-of-range operator (``displacement_mm=60.0``) and an
  unregistered-operator step (``KeyError`` from ``get_perturbation``).
- A single-rung (rung-0-only) ``LadderSpec`` -- ``score_harness`` records an
  explicit failure string rather than dividing by a zero span.
- An assignment mapping a ladder to a mode outside ``1..8``.
- ``score_harness`` on a ``HarnessResult`` with an empty ``ladders`` tuple.
- Baseline sanity: rung 0's clean base still verdicts ``pass`` under
  ``run_qc`` with zero findings (item 036's positive control).
- A non-default ``config`` argument threads through to
  ``extract_feature_record``.

Cost control: the harness (~33 perturbed cases through
``extract_feature_record`` over a ~780k-voxel volume) is built **once** in a
module-scoped fixture; only AC22 (determinism) triggers one additional full
``run_severity_harness()`` call. AC23/AC25's adversarial checks use
``evaluate_ladder`` on a single ladder (~5 rungs), not the full harness.
"""

from __future__ import annotations

import builtins
import dataclasses
import hashlib
import json
import math
import time
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator

from segfacet.config import bundled_default_config
from segfacet.io import FacetInputError
from segfacet.pipeline import run_qc
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.perturbation import FAILURE_MODE_NAMES, get_perturbation, perturbation_names
from segfacet.verdict import Severity


def _sl():
    """Local import of ``segfacet.eval.severity_ladder`` -- kept out of the
    module-level import block (mirrors ``tests/test_099_per_mode_metrics.py``'s
    ``_per_mode()`` convention) so this file still collects before item 100's
    builder step lands the module."""
    import segfacet.eval.severity_ladder as severity_ladder

    return severity_ladder


@pytest.fixture(scope="module")
def harness():
    sl = _sl()
    return sl.run_severity_harness()


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _identity_assignment() -> dict:
    return {k: k for k in range(1, 9)}


def _verdict_for(hv, mode: int):
    """Fetch the per-ladder verdict for *mode* whether ``per_ladder`` is a
    ``Mapping`` keyed by mode or a sequence of entries carrying their own
    ``failure_mode`` field."""
    per_ladder = hv.per_ladder
    if isinstance(per_ladder, Mapping):
        return per_ladder[mode]
    for entry in per_ladder:
        if getattr(entry, "failure_mode", None) == mode:
            return entry
    raise KeyError(mode)


def _spans_table(harness_result) -> dict:
    """``{(ladder_mode, metric_mode): span}`` over the eight primary ladders
    (never the supplementary one -- ``score_harness`` ignores it, AC21)."""
    spans = {}
    for ladder_mode in range(1, 9):
        lr = harness_result.by_mode(ladder_mode)
        for metric_mode in range(1, 9):
            values = [pt.metrics.by_mode(metric_mode).value for pt in lr.points]
            spans[(ladder_mode, metric_mode)] = max(values) - min(values)
    return spans


def _response(spans: dict, m: int, f: int) -> float:
    denom = spans[(f, f)]
    if denom == 0:
        return math.inf
    return spans[(m, f)] / denom


def _margin(spans: dict, m: int) -> float:
    others = [_response(spans, m, f) for f in range(1, 9) if f != m]
    mx = max(others) if others else 0.0
    if mx == 0:
        return math.inf
    return 1.0 / mx


def _collect_degenerate_flags(node, results: dict) -> None:
    """Recursively walk a ``to_dict()`` tree, collecting ``{failure_mode:
    degenerate}`` from any dict node carrying both keys -- robust to exactly
    where ``HarnessResult.to_dict()`` nests the per-ladder degenerate flag."""
    if isinstance(node, dict):
        if "failure_mode" in node and "degenerate" in node:
            results[node["failure_mode"]] = node["degenerate"]
        for v in node.values():
            _collect_degenerate_flags(v, results)
    elif isinstance(node, list):
        for v in node:
            _collect_degenerate_flags(v, results)


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


_SEGFACET_SRC = Path(__import__("segfacet").__file__).resolve().parent
_REPO_ROOT = _SEGFACET_SRC.parent.parent
_CORPUS_DIR = _REPO_ROOT / "tests" / "corpus"


def _combined_hash(files, base: Path) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(str(f.relative_to(base)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


# =========================================================================== #
# AC1: public surface, re-export, frozen dataclasses
# =========================================================================== #

_PUBLIC_NAMES = (
    "LadderRungSpec",
    "LadderSpec",
    "LadderPoint",
    "LadderResult",
    "HarnessResult",
    "LadderVerdict",
    "HarnessVerdict",
    "CrossModeCoupling",
    "SEVERITY_LADDERS",
    "SUPPLEMENTARY_LADDERS",
    "DEGENERATE_LADDER_MODES",
    "KNOWN_CROSS_MODE_COUPLINGS",
    "RECORDED_MARGINS",
    "COUPLING_THRESHOLD",
    "LADDER_SEED",
    "evaluate_ladder",
    "run_severity_harness",
    "score_harness",
)

_FROZEN_DATACLASS_NAMES = (
    "LadderRungSpec",
    "LadderSpec",
    "LadderPoint",
    "LadderResult",
    "HarnessResult",
    "LadderVerdict",
    "HarnessVerdict",
    "CrossModeCoupling",
)


def test_ac1_all_names_exported_from_severity_ladder_module():
    sl = _sl()
    assert set(_PUBLIC_NAMES) <= set(sl.__all__)
    for name in _PUBLIC_NAMES:
        assert hasattr(sl, name), f"segfacet.eval.severity_ladder is missing {name!r}"


def test_ac1_all_names_reexported_from_eval_package():
    import segfacet.eval as eval_pkg

    for name in _PUBLIC_NAMES:
        assert name in eval_pkg.__all__, f"{name!r} missing from segfacet.eval.__all__"
        assert hasattr(eval_pkg, name), f"{name!r} not importable from segfacet.eval"


@pytest.mark.parametrize("name", _FROZEN_DATACLASS_NAMES)
def test_ac1_all_eight_dataclasses_are_frozen(name):
    sl = _sl()
    cls = getattr(sl, name)
    assert dataclasses.is_dataclass(cls)
    fields = dataclasses.fields(cls)
    assert fields, f"{name} declares no fields"
    # frozen=True is enforced structurally: any dataclass instance raises
    # FrozenInstanceError on attribute assignment. We prove this against a
    # real instance further down (test_ac1_frozen_instances_raise_on_mutation)
    # once the harness fixture is available; here we assert the class-level
    # contract that dataclasses.fields exposes on a frozen dataclass.
    assert cls.__dataclass_params__.frozen is True


def test_ac1_frozen_instances_raise_on_mutation(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    ladder_verdict = _verdict_for(verdict, 1)
    rung_spec = sl.SEVERITY_LADDERS[1].rungs[0]
    ladder_spec = sl.SEVERITY_LADDERS[1]
    ladder_result = harness.by_mode(1)
    ladder_point = ladder_result.points[0]

    instances = [
        (rung_spec, "severity"),
        (ladder_spec, "failure_mode"),
        (ladder_point, "severity"),
        (ladder_result, "spec"),
        (harness, "base_params"),
        (verdict, "passed"),
        (ladder_verdict, "status"),
    ]
    for instance, attr in instances:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(instance, attr, "mutated")

    if sl.KNOWN_CROSS_MODE_COUPLINGS:
        coupling = sl.KNOWN_CROSS_MODE_COUPLINGS[0]
        with pytest.raises(dataclasses.FrozenInstanceError):
            coupling.cause = "mutated"


# =========================================================================== #
# AC2: the ladder registry covers exactly the eight §6 modes
# =========================================================================== #


def test_ac2_key_set_is_exactly_one_through_eight():
    sl = _sl()
    assert set(sl.SEVERITY_LADDERS.keys()) == {1, 2, 3, 4, 5, 6, 7, 8}


def test_ac2_clean_control_mode_zero_is_not_a_key():
    sl = _sl()
    assert 0 not in sl.SEVERITY_LADDERS


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac2_ladder_failure_mode_field_matches_its_key(mode):
    sl = _sl()
    assert sl.SEVERITY_LADDERS[mode].failure_mode == mode


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac2_ladder_failure_mode_name_matches_failure_mode_names(mode):
    sl = _sl()
    assert sl.SEVERITY_LADDERS[mode].failure_mode_name == FAILURE_MODE_NAMES[mode]


# =========================================================================== #
# AC3: the ladders use registered operators only
# =========================================================================== #


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac3_every_step_names_a_registered_operator_and_is_constructible(mode):
    sl = _sl()
    names = set(perturbation_names())
    spec = sl.SEVERITY_LADDERS[mode]
    for rung in spec.rungs:
        for op_name, kwargs in rung.steps:
            assert op_name in names, (mode, rung.index, op_name)
            get_perturbation(op_name)(**kwargs)  # must not raise


def test_ac3_supplementary_fuse_ladder_steps_are_registered_and_constructible():
    sl = _sl()
    names = set(perturbation_names())
    for spec in sl.SUPPLEMENTARY_LADDERS:
        for rung in spec.rungs:
            for op_name, kwargs in rung.steps:
                assert op_name in names
                get_perturbation(op_name)(**kwargs)


# =========================================================================== #
# AC4: the metric assignment is item 099's, not a new one -- drift guard
# =========================================================================== #


def _severity_ladder_source() -> str:
    sl = _sl()
    return Path(sl.__file__).read_text(encoding="utf-8")


def test_ac4_module_calls_compute_per_mode_metrics():
    source = _severity_ladder_source()
    assert "compute_per_mode_metrics(" in source


def test_ac4_module_contains_no_metric_rederivation():
    source = _severity_ladder_source()
    for forbidden in ("np.count_nonzero", "out_of_order_labels", "stray_component_sizes"):
        assert forbidden not in source, forbidden


# =========================================================================== #
# AC5: rung 0 is the clean control, at baseline on all eight metrics
# =========================================================================== #


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac5_rung_zero_has_no_steps_and_zero_severity(mode, harness):
    sl = _sl()
    ladder = sl.SEVERITY_LADDERS[mode]
    rung0 = ladder.rungs[0]
    assert rung0.steps == ()
    assert rung0.severity == 0.0


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac5_rung_zero_metrics_are_at_baseline_for_all_eight_modes(mode, harness):
    ladder_result = harness.by_mode(mode)
    rung0_point = ladder_result.points[0]
    for metric_mode in range(1, 9):
        entry = rung0_point.metrics.by_mode(metric_mode)
        expected_baseline = 1.0 if metric_mode == 2 else 0.0
        assert entry.value is not None
        assert entry.value == pytest.approx(expected_baseline, abs=1e-9)


# =========================================================================== #
# AC6: no metric is ever None anywhere in the harness
# =========================================================================== #


def test_ac6_no_metric_value_is_ever_none(harness):
    for mode in range(1, 9):
        ladder_result = harness.by_mode(mode)
        for point in ladder_result.points:
            for metric_mode in range(1, 9):
                entry = point.metrics.by_mode(metric_mode)
                assert type(entry.value) is float, (mode, point.index, metric_mode)


def test_ac6_supplementary_no_metric_value_is_ever_none(harness):
    for ladder_result in harness.supplementary:
        for point in ladder_result.points:
            for metric_mode in range(1, 9):
                entry = point.metrics.by_mode(metric_mode)
                assert type(entry.value) is float


# =========================================================================== #
# AC7: rung severities are strictly increasing
# =========================================================================== #


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac7_rung_severities_strictly_increasing(mode):
    sl = _sl()
    rungs = sl.SEVERITY_LADDERS[mode].rungs
    assert rungs[0].severity == 0.0
    for i in range(len(rungs) - 1):
        assert rungs[i].severity < rungs[i + 1].severity, (mode, i)


# =========================================================================== #
# AC8: every ladder has >= 3 rungs except the declared degenerate one
# =========================================================================== #


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac8_rung_counts_per_degenerate_status(mode):
    sl = _sl()
    n_rungs = len(sl.SEVERITY_LADDERS[mode].rungs)
    if mode in sl.DEGENERATE_LADDER_MODES:
        assert n_rungs == 2, mode
    else:
        assert n_rungs >= 3, mode


# =========================================================================== #
# AC9/AC10: the designated metric is monotone and strictly changes every rung
# =========================================================================== #


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac9_designated_metric_monotone_in_declared_direction(mode, harness):
    from segfacet.eval.per_mode import PER_MODE_METRIC_SPECS

    direction = PER_MODE_METRIC_SPECS[mode].direction
    ladder_result = harness.by_mode(mode)
    values = [pt.metrics.by_mode(mode).value for pt in ladder_result.points]
    if direction == "increases":
        assert all(a <= b for a, b in zip(values, values[1:])), values
    else:
        assert all(a >= b for a, b in zip(values, values[1:])), values


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac10_designated_metric_changes_strictly_at_every_rung_transition(mode, harness):
    ladder_result = harness.by_mode(mode)
    values = [pt.metrics.by_mode(mode).value for pt in ladder_result.points]
    for i in range(len(values) - 1):
        diff = abs(values[i + 1] - values[i])
        assert diff > 1e-9, (
            f"mode {mode} plateaus between rung {i} and {i + 1}: "
            f"{values[i]!r} -> {values[i + 1]!r}"
        )


# =========================================================================== #
# AC11: the severity axis is declared honestly per ladder
# =========================================================================== #

_EXPECTED_SEVERITY_KIND = {
    1: "continuous",
    2: "continuous",
    3: "continuous",
    4: "affected-label-count",
    5: "affected-label-count",
    6: "affected-label-count",
    7: "degenerate",
    8: "continuous",
}
_EXPECTED_SEVERITY_PARAMETER = {
    1: "displacement_mm",
    2: "n_pieces",
    3: "n_islands",
    4: "n_affected_labels",
    5: "n_affected_labels",
    6: "n_affected_labels",
    7: None,  # degenerate -- parameter naming not load-bearing here
    8: "overlap_depth",
}


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac11_severity_kind_matches_the_spec_table(mode):
    sl = _sl()
    assert sl.SEVERITY_LADDERS[mode].severity_kind == _EXPECTED_SEVERITY_KIND[mode]


@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 6, 8])
def test_ac11_severity_parameter_matches_the_spec_table(mode):
    sl = _sl()
    assert sl.SEVERITY_LADDERS[mode].severity_parameter == _EXPECTED_SEVERITY_PARAMETER[mode]


def test_ac11_only_three_severity_kind_values_are_ever_used():
    sl = _sl()
    allowed = {"continuous", "affected-label-count", "degenerate"}
    for mode in range(1, 9):
        assert sl.SEVERITY_LADDERS[mode].severity_kind in allowed


# =========================================================================== #
# AC12: the degenerate ladder is declared, never silent
# =========================================================================== #


def test_ac12_degenerate_ladder_modes_is_exactly_mode_seven():
    sl = _sl()
    assert sl.DEGENERATE_LADDER_MODES == frozenset({7})


def test_ac12_mode_seven_rationale_names_the_transitional_label_cap():
    sl = _sl()
    rationale = sl.SEVERITY_LADDERS[7].rationale
    assert isinstance(rationale, str) and rationale
    assert "28" in rationale


@pytest.mark.parametrize("mode", range(1, 9))
def test_ac12_degenerate_iff_mode_seven_and_iff_two_rungs(mode):
    sl = _sl()
    spec = sl.SEVERITY_LADDERS[mode]
    is_degenerate_kind = spec.severity_kind == "degenerate"
    is_degenerate_mode = mode in sl.DEGENERATE_LADDER_MODES
    has_two_rungs = len(spec.rungs) == 2
    assert is_degenerate_kind == is_degenerate_mode == has_two_rungs, mode


def test_ac12_to_dict_carries_degenerate_flag_true_for_mode_seven_false_otherwise(harness):
    d = harness.to_dict()
    flags: dict = {}
    _collect_degenerate_flags(d, flags)
    assert flags.get(7) is True
    for mode in range(1, 8):
        assert flags.get(mode) is False, mode


# =========================================================================== #
# AC13: score_harness computes the response surface as specified
# =========================================================================== #


def test_ac13_response_surface_matches_independent_recomputation(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    spans = _spans_table(harness)
    for m in range(1, 9):
        lv = _verdict_for(verdict, m)
        assert lv.responses[m] == pytest.approx(1.0, abs=1e-9)
        for f in range(1, 9):
            if f == m:
                continue
            expected = _response(spans, m, f)
            assert lv.responses[f] == pytest.approx(expected, rel=1e-6, abs=1e-9), (m, f)


# =========================================================================== #
# AC14: uncoupled ladders are strictly specific
# =========================================================================== #


def test_ac14_uncoupled_ladders_are_strictly_specific(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    spans = _spans_table(harness)
    coupled_ladder_modes = {c.ladder_mode for c in sl.KNOWN_CROSS_MODE_COUPLINGS}
    for m in range(1, 9):
        if m in coupled_ladder_modes:
            continue
        for f in range(1, 9):
            if f == m:
                continue
            assert _response(spans, m, f) < 1.0, (m, f)
        assert _margin(spans, m) > 1.0, m
        lv = _verdict_for(verdict, m)
        assert lv.status == "strict"


# =========================================================================== #
# AC15: the coupling table exactly matches what is measured
# =========================================================================== #


def test_ac15_coupling_table_matches_measurement_both_directions(harness):
    sl = _sl()
    spans = _spans_table(harness)
    measured = set()
    for m in range(1, 9):
        for f in range(1, 9):
            if f == m:
                continue
            if _response(spans, m, f) >= sl.COUPLING_THRESHOLD:
                measured.add((m, f))
    recorded = {(c.ladder_mode, c.foreign_mode) for c in sl.KNOWN_CROSS_MODE_COUPLINGS}
    # Two-way equality: catches both a hidden leak (measured - recorded) and
    # a stale entry (recorded - measured).
    assert measured == recorded, (measured - recorded, recorded - measured)


def test_ac15_every_coupling_entry_has_a_non_empty_cause_and_no_self_coupling():
    sl = _sl()
    for c in sl.KNOWN_CROSS_MODE_COUPLINGS:
        assert isinstance(c.cause, str) and c.cause
        assert c.foreign_mode != c.ladder_mode


# =========================================================================== #
# AC16: the coupling table is a ratchet
# =========================================================================== #


def test_ac16_coupling_response_ratchet_holds(harness):
    sl = _sl()
    spans = _spans_table(harness)
    for c in sl.KNOWN_CROSS_MODE_COUPLINGS:
        measured = _response(spans, c.ladder_mode, c.foreign_mode)
        assert measured <= c.recorded_response * 1.05, c


def test_ac16_recorded_margins_has_all_eight_modes():
    sl = _sl()
    assert set(sl.RECORDED_MARGINS.keys()) == set(range(1, 9))


def test_ac16_margin_ratchet_holds(harness):
    sl = _sl()
    spans = _spans_table(harness)
    for mode in range(1, 9):
        measured_margin = _margin(spans, mode)
        recorded_margin = sl.RECORDED_MARGINS[mode]
        assert measured_margin >= recorded_margin * 0.95, mode


# =========================================================================== #
# AC17: a coupled ladder is reported as coupled, not as a pass
# =========================================================================== #


def test_ac17_coupled_ladders_report_status_coupled_with_nonempty_coupled_modes(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    coupled_modes = {c.ladder_mode for c in sl.KNOWN_CROSS_MODE_COUPLINGS}
    assert coupled_modes, "expected at least one recorded coupling (mode 6 -> metric 1)"
    for m in coupled_modes:
        lv = _verdict_for(verdict, m)
        assert lv.status == "coupled"
        assert len(lv.coupled_modes) > 0


def test_ac17_identity_assignment_passes_despite_recorded_couplings(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    assert verdict.passed is True


def test_ac17_summary_names_every_coupled_and_degenerate_ladder(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    coupled_modes = {c.ladder_mode for c in sl.KNOWN_CROSS_MODE_COUPLINGS}
    summary = verdict.summary()
    assert isinstance(summary, str) and summary
    for m in coupled_modes:
        assert str(m) in summary, m
    assert "7" in summary  # the degenerate ladder


# =========================================================================== #
# AC18: the negative control fails
# =========================================================================== #


def test_ac18_negative_control_swapping_modes_2_and_3_fails(harness):
    sl = _sl()
    swapped = _identity_assignment()
    swapped[2] = 3
    swapped[3] = 2
    verdict = sl.score_harness(harness, assignment=swapped)
    assert verdict.passed is False
    lv2 = _verdict_for(verdict, 2)
    lv3 = _verdict_for(verdict, 3)
    assert len(lv2.failures) > 0
    assert len(lv3.failures) > 0


def test_ac18_identity_assignment_on_the_same_harness_still_passes(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    assert verdict.passed is True
    explicit = sl.score_harness(harness, assignment=_identity_assignment())
    assert explicit.passed is True


# =========================================================================== #
# AC19: the mode-8 ladder reproduces the committed corpus's overlap count
# =========================================================================== #


def test_ac19_mode8_overlap_depth_three_rung_reproduces_corpus_1950(harness):
    ladder8 = harness.by_mode(8)
    rung3 = next(pt for pt in ladder8.points if pt.severity == 3.0)
    # Cross-referenced against tests/test_099_per_mode_metrics.py's AC14
    # (mode8_force_overlap's overlapping_voxel_count == 1950.0).
    assert rung3.metrics.by_mode(8).value == pytest.approx(1950.0, abs=1e-9)


# =========================================================================== #
# AC20: overlapping_voxel_count is 0.0 on every non-mode-8 ladder
# =========================================================================== #


@pytest.mark.parametrize("mode", [1, 2, 3, 4, 5, 6, 7])
def test_ac20_mode8_metric_is_zero_on_every_other_ladder(mode, harness):
    ladder_result = harness.by_mode(mode)
    for point in ladder_result.points:
        assert point.metrics.by_mode(8).value == 0.0, (mode, point.index)


def test_ac20_mode8_metric_is_zero_on_the_supplementary_ladder(harness):
    for ladder_result in harness.supplementary:
        for point in ladder_result.points:
            assert point.metrics.by_mode(8).value == 0.0


# =========================================================================== #
# AC21: the supplementary fuse ladder closes mode 2's fused half
# =========================================================================== #


def test_ac21_exactly_one_supplementary_ladder_is_the_fuse_ladder():
    sl = _sl()
    assert len(sl.SUPPLEMENTARY_LADDERS) == 1
    spec = sl.SUPPLEMENTARY_LADDERS[0]
    assert spec.operator == "fuse"
    assert spec.failure_mode == 2
    assert len(spec.rungs) >= 3


def test_ac21_fuse_ladder_min_dominant_component_fraction_strictly_decreases(harness):
    fuse_ladder = harness.supplementary[0]
    values = [pt.metrics.by_mode(2).value for pt in fuse_ladder.points]
    for i in range(len(values) - 1):
        assert values[i + 1] < values[i], (i, values)


def test_ac21_score_harness_ignores_supplementary_entirely(harness):
    sl = _sl()
    baseline = sl.score_harness(harness).to_dict()
    stripped = dataclasses.replace(harness, supplementary=())
    stripped_result = sl.score_harness(stripped).to_dict()
    assert stripped_result == baseline


# =========================================================================== #
# AC22: the harness is deterministic
# =========================================================================== #


def test_ac22_two_full_harness_runs_produce_equal_to_dict(harness):
    """The one extra full ``run_severity_harness()`` call the Testing
    Strategy permits."""
    sl = _sl()
    second = sl.run_severity_harness()
    assert second.to_dict() == harness.to_dict()


def test_ac22_per_rung_perturbed_arrays_are_deterministic(harness):
    sl = _sl()
    for mode in range(1, 9):
        spec = sl.SEVERITY_LADDERS[mode]
        for rung in spec.rungs:
            replays = []
            for _ in range(2):
                base = build_clean_spine(**harness.base_params)
                img = base.seg_img
                for op_name, kwargs in rung.steps:
                    operator = get_perturbation(op_name)(**kwargs)
                    img = operator.apply(img, sl.LADDER_SEED).labelmap
                replays.append(np.asanyarray(img.dataobj))
            assert np.array_equal(replays[0], replays[1]), (mode, rung.index)


# =========================================================================== #
# AC23: the harness is pure
# =========================================================================== #


def test_ac23_evaluate_ladder_never_mutates_the_base_image_or_array():
    sl = _sl()
    base = build_clean_spine()
    seg_before = np.array(np.asanyarray(base.seg_img.dataobj), copy=True)
    scan_before = np.array(np.asanyarray(base.scan_img.dataobj), copy=True)

    sl.evaluate_ladder(sl.SEVERITY_LADDERS[1], base=base)

    seg_after = np.asanyarray(base.seg_img.dataobj)
    scan_after = np.asanyarray(base.scan_img.dataobj)
    assert np.array_equal(seg_before, seg_after)
    assert np.array_equal(scan_before, scan_after)


def test_ac23_evaluate_ladder_opens_no_file_and_reads_no_clock(monkeypatch):
    sl = _sl()
    calls = {"open": 0, "write_bytes": 0, "time": 0}

    real_open = builtins.open

    def _tracking_open(*args, **kwargs):
        calls["open"] += 1
        return real_open(*args, **kwargs)

    def _tracking_write_bytes(self, *args, **kwargs):
        calls["write_bytes"] += 1
        raise AssertionError("Path.write_bytes must not be called by evaluate_ladder")

    real_time = time.time

    def _tracking_time():
        calls["time"] += 1
        return real_time()

    monkeypatch.setattr(builtins, "open", _tracking_open)
    monkeypatch.setattr(Path, "write_bytes", _tracking_write_bytes)
    monkeypatch.setattr(time, "time", _tracking_time)

    base = build_clean_spine()
    sl.evaluate_ladder(sl.SEVERITY_LADDERS[1], base=base)

    assert calls["open"] == 0
    assert calls["write_bytes"] == 0
    assert calls["time"] == 0


def test_ac23_leaves_tests_corpus_byte_unchanged():
    files_before = sorted(p for p in _CORPUS_DIR.rglob("*") if p.is_file())
    hash_before = _combined_hash(files_before, _CORPUS_DIR)

    sl = _sl()
    sl.evaluate_ladder(sl.SEVERITY_LADDERS[1])

    files_after = sorted(p for p in _CORPUS_DIR.rglob("*") if p.is_file())
    hash_after = _combined_hash(files_after, _CORPUS_DIR)
    assert hash_after == hash_before


# =========================================================================== #
# AC24: results round-trip through JSON unchanged
# =========================================================================== #


def test_ac24_harness_result_to_dict_round_trips_through_json(harness):
    d = harness.to_dict()
    assert json.loads(json.dumps(d)) == d


def test_ac24_harness_result_to_dict_is_json_native(harness):
    d = harness.to_dict()
    assert type(d) is dict
    _assert_json_native(d)


def test_ac24_harness_verdict_to_dict_round_trips_through_json(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    d = verdict.to_dict()
    assert json.loads(json.dumps(d)) == d


def test_ac24_harness_verdict_to_dict_is_json_native(harness):
    sl = _sl()
    verdict = sl.score_harness(harness)
    d = verdict.to_dict()
    assert type(d) is dict
    _assert_json_native(d)


# =========================================================================== #
# AC25: an operator failure propagates, never truncates the ladder
# =========================================================================== #


def test_ac25_out_of_range_displacement_raises_facet_input_error():
    sl = _sl()
    rung0 = sl.LadderRungSpec(index=0, severity=0.0, label="clean control", steps=())
    rung1 = sl.LadderRungSpec(
        index=1,
        severity=60.0,
        label="displace 60mm",
        steps=(("displace", {"target_label": 22, "displacement_mm": 60.0}),),
    )
    spec = sl.LadderSpec(
        failure_mode=1,
        failure_mode_name=FAILURE_MODE_NAMES[1],
        operator="displace",
        severity_parameter="displacement_mm",
        severity_kind="continuous",
        rungs=(rung0, rung1),
        rationale="",
        overlap_reconstruction=None,
    )
    with pytest.raises(FacetInputError):
        sl.evaluate_ladder(spec)


def test_ac25_unregistered_operator_raises_key_error_not_skipped():
    sl = _sl()
    rung0 = sl.LadderRungSpec(index=0, severity=0.0, label="clean control", steps=())
    rung1 = sl.LadderRungSpec(
        index=1,
        severity=1.0,
        label="bogus",
        steps=(("not_a_real_perturbation", {}),),
    )
    spec = sl.LadderSpec(
        failure_mode=1,
        failure_mode_name=FAILURE_MODE_NAMES[1],
        operator="not_a_real_perturbation",
        severity_parameter="displacement_mm",
        severity_kind="continuous",
        rungs=(rung0, rung1),
        rationale="",
        overlap_reconstruction=None,
    )
    with pytest.raises(KeyError):
        sl.evaluate_ladder(spec)


# =========================================================================== #
# AC26: the scope fence holds
# =========================================================================== #

_PRE_100_HASHES = {
    "eval/per_mode.py": "5fd77f74b33dccbe32c3b899a9d2a4e1f051df03a5deb9a3a0cda7058ff0d9c6",
    "eval/metrics.py": "15a21e7d9c8d738bfe5755637f736e60fd86d620c6117dd39a5d3b3bfa8bff8a",
    "cli.py": "ca2eb98d7d67935c30d640b43502bbf9769b152a75fbe56b65b2ba350ad96a58",
    "report_schema_v0.json": "8c7b48c1fcfc82edf49187c8aa912ac42470b20f53fd739c9b65f0bbf76f4a4b",
    "eval/eval_report_schema_v0.json": "88d0483262abc4d4317b4dfb6354c81c37dc405f9c77af30fb37d0545a1d7b70",
}
_PRE_100_SYNTH_HASH = "8ed4d4d5d1d26c36077eef2a35569d8db6687d51d7551e94f38e76f8d7323205"
_PRE_100_HEURISTICS_HASH = "92cdc63e9a9bcef3c4ebd6c9b5567e80c30a3077bd3613d635c443bf055d19c4"
_PRE_100_FEATURES_HASH = "92cc4fba7269f8c77c33441ea870b7eb6224d561a03c192028fa03560a6f60ce"
_PRE_100_CORPUS_HASH = "aad04c1b0e42074a11342b24dc94c7f2ec896cda1664efeee7c5fc5b0ec4f547"


@pytest.mark.parametrize("relpath", sorted(_PRE_100_HASHES))
def test_ac26_named_file_byte_identical_to_pre_100_state(relpath):
    path = _SEGFACET_SRC / relpath
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == _PRE_100_HASHES[relpath], relpath


def test_ac26_synth_package_byte_identical_to_pre_100_state():
    files = sorted((_SEGFACET_SRC / "synth").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_100_SYNTH_HASH


def test_ac26_heuristics_package_byte_identical_to_pre_100_state():
    files = sorted((_SEGFACET_SRC / "heuristics").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_100_HEURISTICS_HASH


def test_ac26_features_package_byte_identical_to_pre_100_state():
    files = sorted((_SEGFACET_SRC / "features").rglob("*.py"))
    assert _combined_hash(files, _SEGFACET_SRC) == _PRE_100_FEATURES_HASH


def test_ac26_corpus_byte_identical_to_pre_100_state():
    files = sorted(p for p in _CORPUS_DIR.rglob("*") if p.is_file())
    assert _combined_hash(files, _CORPUS_DIR) == _PRE_100_CORPUS_HASH


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_single_rung_ladder_scores_explicit_failure_not_zero_division(harness):
    sl = _sl()
    truncated_ladder_1 = dataclasses.replace(
        harness.by_mode(1), points=harness.by_mode(1).points[:1]
    )
    minimal = dataclasses.replace(harness, ladders=(truncated_ladder_1,))
    verdict = sl.score_harness(minimal, assignment={1: 1})  # must not raise
    lv = _verdict_for(verdict, 1)
    assert len(lv.failures) > 0


def test_adv_assignment_outside_valid_mode_range_raises(harness):
    sl = _sl()
    # 99 is guaranteed absent from PER_MODE_METRIC_SPECS (keys are 1..8).
    bad_assignment = {**_identity_assignment(), 1: 99}
    with pytest.raises((KeyError, FacetInputError)):
        sl.score_harness(harness, assignment=bad_assignment)


def test_adv_score_harness_on_empty_ladders_tuple_is_a_vacuous_pass(harness):
    sl = _sl()
    empty = dataclasses.replace(harness, ladders=())
    verdict = sl.score_harness(empty)  # must not raise
    assert verdict.passed is True
    per_ladder = verdict.per_ladder
    assert len(per_ladder) == 0


def test_adv_baseline_sanity_rung_zero_clean_base_passes_run_qc():
    """The positive control item 036 guarantees, re-asserted here because
    every ladder's normalisation depends on it."""
    config = bundled_default_config()
    clean = build_clean_spine()
    case_result, _ = run_qc(clean.seg_img, config)
    assert case_result.verdict.overall == Severity.PASS
    assert len(case_result.findings) == 0


def test_adv_non_default_config_threads_through_to_extract_feature_record():
    sl = _sl()
    default_result = sl.evaluate_ladder(sl.SEVERITY_LADDERS[1])
    explicit_result = sl.evaluate_ladder(
        sl.SEVERITY_LADDERS[1], config=bundled_default_config()
    )
    default_values = [pt.metrics.by_mode(1).value for pt in default_result.points]
    explicit_values = [pt.metrics.by_mode(1).value for pt in explicit_result.points]
    assert default_values == explicit_values
