"""Tests for item 109 -- magnitude-sensitive per-mode attribution
(``segfacet.eval.per_mode_cohort``).

Repairs the saturating ``normalised_delta`` in ``compare_runs``: the old
formula ``delta / max(abs(value_a - baseline), abs(value_b - baseline))``
ties at exactly +/-1.0 whenever either run sits on its metric's baseline,
which is seven of the eight ``PER_MODE_METRIC_SPECS`` baselines. This module
covers the fix's classification and attribution rules:

- AC1:  bounded metrics (the three ``*_fraction`` metrics, modes 1/2/4) scale
        by their derivable full swing -- the distance from ``baseline`` to
        the metric's other range bound -- not by the per-comparison adaptive
        max-observed-distance the old formula used.
- AC1b: no metric's divisor depends on the actual run values (a proxy for
        "no supervision dependency" -- the divisor is fixed at the classi-
        fication/spec level, never computed from ``value_a``/``value_b``).
- AC2:  the five count metrics (modes 3/5/6/7/8) are raw by default --
        ``normalised_delta is None``, ``delta`` remains available.
- AC3/AC4: the reviewed-threshold mechanism exists and is unset for every
        shipped metric.
- AC5/AC7/AC10: attribution follows magnitude, not mode number; the lowest-
        mode tie-break fires only on an exact tie.
- AC6:  a bounded metric with one run on baseline no longer saturates unless
        the other run is genuinely at the far end of the range.
- AC8/AC9: unnormalisable modes are excluded from attribution visibly
        (``excluded_modes``), and true no-attribution states a reason
        (``unattributable_reason``) rather than falling back to the lowest
        mode.
- AC11: comparisons where neither run sits on baseline AND the old adaptive
        scale already equalled the metric's derivable full swing (one run at
        the far bound) are numerically unchanged by the fix -- pinned from
        the pre-fix implementation (see that test's docstring for how the
        pin was derived).
- AC12: ``render_run_comparison`` distinguishes "not normalisable" from
        "normalised to 0.0" in its no-attribution message.

Interpretive note (see this agent's final report for the full explanation):
item 109's authorised paths exclude ``src/segfacet/eval/per_mode.py`` (item
112 owns the only sanctioned change there), so AC3's "``MetricSpec`` gains an
optional reference-excursion field" is implemented here as a new, additive,
``per_mode_cohort``-local companion table (``MODE_SCALE_SPECS`` /
``ModeScaleSpec``) rather than a literal edit to ``per_mode.MetricSpec`` --
the per-metric classification the Assumptions section requires ("each of the
eight metrics carries an explicit, reviewed class") without touching the
out-of-scope file. Bounded metrics (modes 1/2/4) declare a non-``None``
``full_swing``; unbounded metrics (3/5/6/7/8) declare ``full_swing=None`` and
an unset (``None``) ``reference_excursion`` by default.

Adversarial / edge-case scenarios included: both runs identical (bounded
metrics land on an honest ``0.0``, unbounded metrics land on ``None``, never
a fallback attribution); a metric value of ``None`` (absent from a record,
propagating through delta/normalised_delta); a bounded metric already at the
far end of its range on both sides (delta 0.0, not a saturated 1.0); a
NaN/inf finiteness guard across the full comparison.
"""

from __future__ import annotations

import dataclasses
import json
import math
from typing import Optional

import jsonschema
import pytest

from segfacet.eval.per_mode import PER_MODE_METRIC_SPECS


def _comparison_schema() -> dict:
    import importlib.resources

    import segfacet.eval as eval_pkg

    ref = importlib.resources.files(eval_pkg).joinpath("per_mode_comparison_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def _pmc():
    """Local import, mirrors ``tests/test_101_per_mode_cohort.py``'s
    ``_pmc()`` convention so this file still collects before item 109's
    builder step lands the fix."""
    import segfacet.eval.per_mode_cohort as per_mode_cohort

    return per_mode_cohort


BOUNDED_MODES = (1, 2, 4)
UNBOUNDED_MODES = (3, 5, 6, 7, 8)


# --------------------------------------------------------------------------- #
# Fixture helpers (duplicated from test_101_per_mode_cohort.py's own
# duplication-over-cross-import convention -- see that file's
# ``_tuples_to_lists`` rationale)
# --------------------------------------------------------------------------- #


def _full(value: Optional[float]) -> dict:
    return {m: value for m in range(1, 9)}


def _summary(run_id, case_ids, means: dict):
    pmc = _pmc()
    per_mode = []
    for mode in range(1, 9):
        spec = PER_MODE_METRIC_SPECS[mode]
        mean = means.get(mode)
        per_mode.append(
            pmc.ModeAggregate(
                failure_mode=spec.failure_mode,
                failure_mode_name=spec.failure_mode_name,
                metric_name=spec.metric_name,
                direction=spec.direction,
                baseline=spec.baseline,
                n_cases=len(case_ids),
                n_with_value=len(case_ids),
                mean=mean,
                minimum=mean,
                maximum=mean,
                total=(None if mean is None else mean * len(case_ids)),
                detection_rate=None,
                n_detection_cases=0,
            )
        )
    return pmc.RunPerModeSummary(
        run_id=run_id,
        case_ids=tuple(case_ids),
        n_cases=len(case_ids),
        per_mode=tuple(per_mode),
        mean_dice=None,
        volume_weighted_dice=None,
        run_manifest=None,
    )


def _cmp(a_values: dict, b_values: dict):
    pmc = _pmc()
    a = _summary("a", ("c1",), a_values)
    b = _summary("b", ("c1",), b_values)
    return pmc.compare_runs(a, b)


# =========================================================================== #
# AC1: bounded metrics scale by their derivable full swing
# =========================================================================== #


@pytest.mark.parametrize("mode", BOUNDED_MODES)
def test_ac1_bounded_metric_scale_is_the_declared_full_swing(mode):
    pmc = _pmc()
    spec = PER_MODE_METRIC_SPECS[mode]
    scale_spec = pmc.MODE_SCALE_SPECS[mode]
    assert scale_spec.full_swing is not None, mode

    # value_a/value_b are deliberately generic (neither on baseline nor at
    # the far bound) -- the point is that scale does not depend on them.
    baseline = spec.baseline
    far = 1.0 - baseline
    a_values = {**_full(baseline), mode: baseline + 0.3 * (far - baseline)}
    b_values = {**_full(baseline), mode: baseline + 0.6 * (far - baseline)}
    cmp = _cmp(a_values, b_values)
    d = cmp.by_mode(mode)
    assert d.scale == pytest.approx(scale_spec.full_swing)


@pytest.mark.parametrize("mode", BOUNDED_MODES)
def test_ac1_bounded_metric_scale_is_data_independent_not_adaptive(mode):
    """The bug: the old formula recomputed ``scale`` from ``value_a``/
    ``value_b`` on every comparison (adaptive, and hence saturating). The
    fix's scale is a fixed property of the metric's declaration -- varying
    the actual values (while staying off baseline and off the far bound)
    must not move it."""
    pmc = _pmc()
    spec = PER_MODE_METRIC_SPECS[mode]
    baseline = spec.baseline
    far = 1.0 - baseline  # baseline is 0.0 or 1.0 for every bounded metric
    mid = baseline + 0.5 * (far - baseline)
    near_baseline = baseline + 0.1 * (far - baseline)
    near_far = baseline + 0.9 * (far - baseline)

    def _values(value):
        return {**_full(baseline), mode: value}

    scale_small = pmc.compare_runs(
        _summary("a", ("c1",), _values(near_baseline)),
        _summary("b", ("c1",), _values(mid)),
    ).by_mode(mode).scale
    scale_large = pmc.compare_runs(
        _summary("a", ("c1",), _values(near_far)),
        _summary("b", ("c1",), _values(mid)),
    ).by_mode(mode).scale

    assert scale_small == pytest.approx(scale_large)
    assert scale_small == pytest.approx(pmc.MODE_SCALE_SPECS[mode].full_swing)


# =========================================================================== #
# AC1b: no scale depends on supervision (proxy: the divisor never depends on
# the actual run values, including for candidate_vs_gt-sourced metrics)
# =========================================================================== #


@pytest.mark.parametrize("mode", BOUNDED_MODES)
def test_ac1b_bounded_metric_divisor_unchanged_across_wildly_different_value_pairs(mode):
    """Simulates "two different GT inputs, identical candidates": the only
    channel through which a different GT could reach this module is a
    different pair of aggregated values for the same metric. The divisor
    (``scale``) must be identical across both."""
    spec = PER_MODE_METRIC_SPECS[mode]
    baseline = spec.baseline
    far = 1.0 - baseline

    scenario_1 = _cmp(
        {**_full(baseline), mode: baseline + 0.05 * (far - baseline)},
        {**_full(baseline), mode: baseline + 0.20 * (far - baseline)},
    )
    scenario_2 = _cmp(
        {**_full(baseline), mode: baseline + 0.60 * (far - baseline)},
        {**_full(baseline), mode: baseline + 0.99 * (far - baseline)},
    )
    assert scenario_1.by_mode(mode).scale == pytest.approx(scenario_2.by_mode(mode).scale)


@pytest.mark.parametrize("mode", (1, 4, 5))  # source == "candidate_vs_gt"
def test_ac1b_candidate_vs_gt_sourced_metrics_scale_ignores_the_actual_values(mode):
    """Modes 1/4/5 are ``source: "candidate_vs_gt"`` by item 099's design
    (a metric may use GT). AC1b constrains only the *divisor*: whether the
    metric is bounded (1/4 -- scale fixed at 1.0) or raw (5 -- scale always
    ``None``), the divisor must be identical across two very different value
    pairs standing in for two different GT inputs."""
    scenario_1 = _cmp({**_full(0.0), mode: 0.01}, {**_full(0.0), mode: 0.02})
    scenario_2 = _cmp({**_full(0.0), mode: 0.9}, {**_full(0.0), mode: 0.99})
    assert scenario_1.by_mode(mode).scale == scenario_2.by_mode(mode).scale


# =========================================================================== #
# AC2: everything else (the five count metrics) is raw by default
# =========================================================================== #


@pytest.mark.parametrize("mode", UNBOUNDED_MODES)
def test_ac2_unbounded_metric_normalised_delta_is_none_raw_delta_available(mode):
    cmp = _cmp({**_full(0.0), mode: 2.0}, {**_full(0.0), mode: 7.0})
    d = cmp.by_mode(mode)
    assert d.normalised_delta is None
    assert d.scale is None
    assert d.delta == pytest.approx(5.0)
    assert d.value_a == pytest.approx(2.0)
    assert d.value_b == pytest.approx(7.0)


@pytest.mark.parametrize("mode", UNBOUNDED_MODES)
def test_ac2_unbounded_mode_scale_spec_has_no_full_swing(mode):
    pmc = _pmc()
    assert pmc.MODE_SCALE_SPECS[mode].full_swing is None


# =========================================================================== #
# AC3/AC4: the reviewed-threshold mechanism exists, unset for every metric
# =========================================================================== #


def test_ac3_mode_scale_spec_carries_a_reference_excursion_field():
    pmc = _pmc()
    for mode in range(1, 9):
        assert hasattr(pmc.MODE_SCALE_SPECS[mode], "reference_excursion"), mode


def test_ac3_reference_excursion_docstring_states_it_is_a_human_review_decision():
    pmc = _pmc()
    doc = (pmc.ModeScaleSpec.__doc__ or "").lower()
    assert "review" in doc
    assert "rationale" in doc


def test_ac3_setting_reference_excursion_scales_that_metric(monkeypatch):
    """When a mode's ``reference_excursion`` is set, ``compare_runs`` scales
    by it instead of leaving the metric raw."""
    pmc = _pmc()
    original = pmc.MODE_SCALE_SPECS[3]
    patched_spec = dataclasses.replace(original, reference_excursion=5.0)
    patched_table = dict(pmc.MODE_SCALE_SPECS)
    patched_table[3] = patched_spec
    monkeypatch.setattr(pmc, "MODE_SCALE_SPECS", patched_table)

    cmp = _cmp({**_full(0.0), 3: 0.0}, {**_full(0.0), 3: 5.0})
    d = cmp.by_mode(3)
    assert d.scale == pytest.approx(5.0)
    assert d.normalised_delta == pytest.approx(1.0)


def test_ac4_every_shipped_mode_scale_spec_leaves_reference_excursion_unset():
    pmc = _pmc()
    for mode in range(1, 9):
        assert pmc.MODE_SCALE_SPECS[mode].reference_excursion is None, mode


# =========================================================================== #
# AC5: attribution follows magnitude regardless of mode number
# =========================================================================== #


def test_ac5_larger_mover_wins_when_it_is_the_higher_numbered_mode():
    cmp = _cmp({**_full(0.0), 1: 0.0, 4: 0.0}, {**_full(0.0), 1: 0.2, 4: 0.8})
    assert cmp.attributed_mode == 4


def test_ac5_larger_mover_wins_when_it_is_the_lower_numbered_mode():
    cmp = _cmp({**_full(0.0), 1: 0.0, 4: 0.0}, {**_full(0.0), 1: 0.8, 4: 0.2})
    assert cmp.attributed_mode == 1


# =========================================================================== #
# AC6: baseline no longer saturates
# =========================================================================== #


def test_ac6_one_run_on_baseline_other_short_of_far_end_stays_below_one():
    cmp = _cmp({**_full(0.0), 1: 0.0}, {**_full(0.0), 1: 0.5})
    d = cmp.by_mode(1)
    assert abs(d.normalised_delta) < 1.0
    assert d.normalised_delta == pytest.approx(0.5)


def test_ac6_one_run_on_baseline_other_at_far_end_is_exactly_one_the_sanctioned_exception():
    cmp = _cmp({**_full(0.0), 1: 0.0}, {**_full(0.0), 1: 1.0})
    d = cmp.by_mode(1)
    assert abs(d.normalised_delta) == pytest.approx(1.0)


# =========================================================================== #
# AC7: the differential case (0.1 vs 0.9 from a shared baseline) works
# =========================================================================== #


def test_ac7_point_one_vs_point_nine_from_shared_baseline_attributes_to_the_larger_move():
    cmp = _cmp({**_full(0.0), 1: 0.0, 4: 0.0}, {**_full(0.0), 1: 0.1, 4: 0.9})
    d1 = cmp.by_mode(1)
    d4 = cmp.by_mode(4)
    assert d1.normalised_delta == pytest.approx(0.1)
    assert d4.normalised_delta == pytest.approx(0.9)
    assert cmp.attributed_mode == 4
    assert cmp.attributed_mode_name == PER_MODE_METRIC_SPECS[4].failure_mode_name
    assert cmp.attributed_metric_name == PER_MODE_METRIC_SPECS[4].metric_name


# =========================================================================== #
# AC8/AC9: unnormalisable modes are excluded visibly; true no-attribution
# states a reason, never a fallback to the lowest mode
# =========================================================================== #


def test_ac8_comparison_over_unbounded_metrics_only_lists_the_excluded_modes():
    # Bounded modes (1/2/4) carry no value on either side -- their delta is
    # None (a data gap, not a classification exclusion). Unbounded modes
    # carry real, differing values -- they have a raw delta but no scale, so
    # AC8 requires them to be visibly excluded from attribution.
    a_values = {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    b_values = {3: 5.0, 5: 2.0, 6: 3.0, 7: 1.0, 8: 4.0}
    cmp = _cmp(a_values, b_values)

    for mode in (1, 2, 4):
        assert cmp.by_mode(mode).delta is None

    assert cmp.excluded_modes == UNBOUNDED_MODES
    for mode in UNBOUNDED_MODES:
        assert cmp.by_mode(mode).delta is not None
        assert cmp.by_mode(mode).normalised_delta is None


def test_ac9_no_metric_normalisable_yields_none_with_a_stated_reason_not_lowest_mode_fallback():
    a_values = {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    b_values = {3: 5.0, 5: 2.0, 6: 3.0, 7: 1.0, 8: 4.0}
    cmp = _cmp(a_values, b_values)

    assert cmp.attributed_mode is None
    assert cmp.attributed_mode_name is None
    assert cmp.attributed_metric_name is None
    assert isinstance(cmp.unattributable_reason, str) and cmp.unattributable_reason
    assert "not normalisable" in cmp.unattributable_reason.lower()
    # The pre-fix bug's failure mode was exactly this: falling through to the
    # documented lowest-mode tie-break instead of reporting no attribution.
    assert cmp.attributed_mode != 1


def test_ac8b_fully_degenerate_comparison_serialises_excluded_modes_and_reason():
    # Same fully-degenerate scenario as AC9 (no metric normalisable), but
    # asserted through the *serialised* form -- to_dict() -- and validated
    # against the bundled schema. AC8b requires a reader of the serialised
    # output to be able to read which modes were excluded and why, rather
    # than infer it from the Python properties (which every other test of
    # this scenario stops at).
    a_values = {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    b_values = {3: 5.0, 5: 2.0, 6: 3.0, 7: 1.0, 8: 4.0}
    cmp = _cmp(a_values, b_values)
    doc = cmp.to_dict()

    assert doc["attributed_mode"] is None
    assert doc["excluded_modes"] == list(UNBOUNDED_MODES)
    assert isinstance(doc["unattributable_reason"], str) and doc["unattributable_reason"]
    assert "not normalisable" in doc["unattributable_reason"].lower()

    # The bundled schema requires both keys in every comparison document,
    # including this fully-degenerate one -- prove it is actually
    # satisfiable here, not just in the successful-attribution case the
    # existing schema test covers.
    schema = _comparison_schema()
    comparison_schema = schema["definitions"]["comparison"]
    jsonschema.validate(doc, comparison_schema)


# =========================================================================== #
# AC10: the lowest-mode tie-break is last-resort only
# =========================================================================== #


def test_ac10_exact_tie_breaks_to_the_lowest_mode():
    # Both modes legitimately reach their full swing (an honest tie, not the
    # saturation bug): mode 1 goes baseline(0.0) -> far end(1.0), mode 2 goes
    # far end(0.0) -> baseline(1.0). abs(normalised_delta) == 1.0 for both.
    cmp = _cmp({**_full(0.0), 1: 0.0, 2: 0.0}, {**_full(0.0), 1: 1.0, 2: 1.0})
    d1 = cmp.by_mode(1)
    d2 = cmp.by_mode(2)
    assert abs(d1.normalised_delta) == pytest.approx(abs(d2.normalised_delta))
    assert cmp.attributed_mode == 1


def test_ac10_ac7_scenario_does_not_reach_the_tie_break():
    cmp = _cmp({**_full(0.0), 1: 0.0, 4: 0.0}, {**_full(0.0), 1: 0.1, 4: 0.9})
    d1 = cmp.by_mode(1)
    d4 = cmp.by_mode(4)
    assert abs(d1.normalised_delta) != pytest.approx(abs(d4.normalised_delta))
    # attribution must be decided by magnitude comparison, not by falling
    # through to "lowest mode" -- mode 4 (not mode 1) wins.
    assert cmp.attributed_mode == 4


# =========================================================================== #
# AC11: unchanged where it was already right
#
# Pin derivation: these exact per-mode values (scale/normalised_delta/
# attributed_mode) were captured by running the CURRENT (pre-item-109)
# ``segfacet.eval.per_mode_cohort.compare_runs`` against this fixture,
# executed via:
#     .venv/bin/python - <<'EOF'
#     import segfacet.eval.per_mode_cohort as pmc
#     ... (build the two RunPerModeSummary objects below, call compare_runs)
#     EOF
# on branch aide/109-magnitude-sensitive-per-mode-attribution before any
# item-109 change landed. The fixture deliberately keeps every mode off its
# own baseline, and for the three bounded metrics (1/2/4) additionally
# drives one side of each to the metric's far range bound -- the case AC6
# names as the sanctioned exception where the old adaptive
# ``max(abs(value_a - baseline), abs(value_b - baseline))`` already equals
# the new fixed full-swing divisor, so the two formulas coincide and the
# numbers are genuinely unchanged by the fix. (The five unbounded modes'
# ``normalised_delta`` do change, from a numeric 0.0 to None -- that is the
# sanctioned AC2 change, not something AC11 claims stays the same; this test
# only pins the bounded metrics' normalised_delta and the resulting
# attributed_mode, both of which are identical before and after the fix.)
# =========================================================================== #


def test_ac11_bounded_metrics_and_attributed_mode_unchanged_when_one_side_already_at_far_bound():
    a_values = {1: 0.4, 2: 0.9, 3: 1.0, 4: 0.25, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    b_values = {1: 1.0, 2: 0.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    cmp = _cmp(a_values, b_values)

    d1 = cmp.by_mode(1)
    assert d1.scale == pytest.approx(1.0)
    assert d1.normalised_delta == pytest.approx(0.6)

    d2 = cmp.by_mode(2)
    assert d2.scale == pytest.approx(1.0)
    assert d2.normalised_delta == pytest.approx(-0.9)

    d4 = cmp.by_mode(4)
    assert d4.scale == pytest.approx(1.0)
    assert d4.normalised_delta == pytest.approx(0.75)

    assert cmp.attributed_mode == 2
    assert cmp.attributed_mode_name == PER_MODE_METRIC_SPECS[2].failure_mode_name
    assert cmp.attributed_metric_name == PER_MODE_METRIC_SPECS[2].metric_name


# =========================================================================== #
# AC12: the report distinguishes "not normalisable" from "normalised to 0.0"
# =========================================================================== #


def test_ac12_render_states_not_normalisable_when_no_metric_can_be_scaled():
    import segfacet.eval.report as report_mod

    a_values = {3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
    b_values = {3: 5.0, 5: 2.0, 6: 3.0, 7: 1.0, 8: 4.0}
    cmp = _cmp(a_values, b_values)
    text = report_mod.render_run_comparison(cmp)
    assert "not normalisable" in text.lower()
    assert "normalised to 0.0" not in text.lower()


def test_ac12_render_states_normalised_to_zero_when_bounded_metrics_did_not_move():
    import segfacet.eval.report as report_mod

    values = {1: 0.4, 2: 0.6, 4: 0.3}
    cmp = _cmp(values, values)
    text = report_mod.render_run_comparison(cmp)
    assert "normalised to 0.0" in text.lower()
    assert "not normalisable" not in text.lower()


def test_ac12_module_docstring_describes_the_new_rule():
    pmc = _pmc()
    doc = (pmc.__doc__ or "").lower()
    assert "full swing" in doc or "full-swing" in doc
    assert "raw" in doc


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_both_runs_identical_bounded_zero_unbounded_none_no_fallback_attribution():
    values = {1: 0.3, 2: 0.7, 3: 4.0, 4: 0.1, 5: 2.0, 6: 1.0, 7: 3.0, 8: 500.0}
    cmp = _cmp(values, values)
    for mode in BOUNDED_MODES:
        d = cmp.by_mode(mode)
        assert d.delta == 0.0
        assert d.normalised_delta == 0.0
    for mode in UNBOUNDED_MODES:
        d = cmp.by_mode(mode)
        assert d.delta == 0.0
        assert d.normalised_delta is None
    assert cmp.attributed_mode is None


@pytest.mark.parametrize("mode", range(1, 9))
def test_adv_metric_value_none_on_one_side_normalised_delta_is_none(mode):
    a_values = {**_full(0.0), mode: None}
    b_values = _full(0.0)
    cmp = _cmp(a_values, b_values)
    d = cmp.by_mode(mode)
    assert d.value_a is None
    assert d.delta is None
    assert d.normalised_delta is None


@pytest.mark.parametrize("mode", BOUNDED_MODES)
def test_adv_bounded_metric_already_at_far_end_both_runs_is_zero_not_saturated(mode):
    far = 1.0 - PER_MODE_METRIC_SPECS[mode].baseline
    cmp = _cmp({**_full(0.0), mode: far}, {**_full(0.0), mode: far})
    d = cmp.by_mode(mode)
    assert d.delta == 0.0
    assert d.normalised_delta == 0.0


def test_adv_finiteness_guard_across_a_full_comparison():
    a_values = {1: 0.1, 2: 0.9, 3: 3.0, 4: 0.2, 5: 1.0, 6: 0.0, 7: 2.0, 8: 10.0}
    b_values = {1: 0.9, 2: 0.1, 3: 8.0, 4: 0.8, 5: 4.0, 6: 5.0, 7: 0.0, 8: 0.0}
    cmp = _cmp(a_values, b_values)
    for d in cmp.per_mode:
        if d.scale is not None:
            assert math.isfinite(d.scale), d.failure_mode
        if d.normalised_delta is not None:
            assert math.isfinite(d.normalised_delta), d.failure_mode
