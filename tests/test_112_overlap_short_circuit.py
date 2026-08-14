"""Tests for item 112 -- ``compute_per_mode_metrics(overlap_result=...)``
short-circuit (``segfacet.eval.per_mode``), plus the ``eval.harness`` call
site that now supplies its already-computed ``OverlapResult`` instead of
letting ``compute_per_mode_metrics`` recompute it.

Covers Acceptance Criteria AC1-AC8:

- AC1: the ``overlap_result=None`` keyword exists, is keyword-only, and the
       default path (omitted, or explicit ``None``) is exactly today's
       behaviour.
- AC2: for the same inputs, the returned ``PerModeMetrics`` is field-by-field
       equal whether ``overlap_result`` is supplied or computed internally.
- AC3: with a result supplied, a spy on ``compute_overlap`` records zero
       calls from inside ``compute_per_mode_metrics``.
- AC4: the harness's ``evaluate_case``/``evaluate_cohort`` supply their own
       ``OverlapResult``; a spy confirms ``compute_overlap`` is called
       exactly once per candidate-present case (previously twice).
- AC5: harness per-case and cohort output is identical to the pre-item-112
       ("slow path": overlap computed once for the ``overlap`` field, then
       again inside ``compute_per_mode_metrics``) recomputation.
- AC6: a supplied ``OverlapResult`` that does not correspond to the given
       ``candidate``/``gt`` (different shape, or same shape but a disjoint
       label set) raises a clear error naming ``overlap_result`` rather than
       silently returning wrong numbers.
- AC7: the docstring names the checked invariants (shape, label set) and
       states that a same-shape-but-wrong result is otherwise trusted.
- AC8: existing call sites that never pass the keyword (``severity_ladder``,
       ``catalogue``) are untouched and keep producing the same output.

Adversarial / edge-case scenarios included:
- ``overlap_result=None`` passed explicitly (AC1).
- A matching ``OverlapResult`` for an empty (all-background) candidate/GT
  pair, extending AC2's equality check to the degenerate case.
- A caller-supplied ``OverlapResult`` computed with *different spacing* than
  the ``spacing=`` argument -- documented and tested as accepted (spacing is
  not one of the cheap invariants ``OverlapResult`` can carry, since it does
  not store spacing at all; only shape/label-set are checked per AC6/AC7).
- The same ``OverlapResult`` object reused across two calls: neither the
  object's fields nor its nested ``per_label`` tuple are mutated or replaced.
"""

from __future__ import annotations

import dataclasses
import inspect
import re

import numpy as np
import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator

from segfacet.config import bundled_default_config
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth.corpus import load_manifest
from segfacet.synth.regression import loaded_seg_image
from segfacet.verdict import Severity


def _per_mode():
    import segfacet.eval.per_mode as per_mode

    return per_mode


def _overlap_mod():
    import segfacet.eval.overlap as overlap

    return overlap


def _harness_mod():
    import segfacet.eval.harness as harness

    return harness


def _severity_ladder_mod():
    import segfacet.eval.severity_ladder as severity_ladder

    return severity_ladder


def _catalogue_mod():
    import segfacet.catalogue as catalogue

    return catalogue


# =========================================================================== #
# Corpus fixtures -- loaded once at module scope (Testing Strategy cost control)
# =========================================================================== #

_MANIFEST = load_manifest()
_CASES = {c["case_id"]: c for c in _MANIFEST["cases"]}
_CONFIG = bundled_default_config()
_GT_ARRAY = np.asanyarray(loaded_seg_image(_CASES["clean_control"]).dataobj)
_SPACING = (1.0, 1.0, 1.0)


def _arr(cid: str) -> np.ndarray:
    return np.asanyarray(loaded_seg_image(_CASES[cid]).dataobj)


_CAND_ARRAY = _arr("mode1_displace")
_CAND_RECORD = extract_feature_record(loaded_seg_image(_CASES["mode1_displace"]), _CONFIG)


def _spy(calls: dict, key: str, real):
    def _wrapped(*a, **kw):
        calls[key] = calls.get(key, 0) + 1
        return real(*a, **kw)

    return _wrapped


# =========================================================================== #
# AC1: the keyword exists, is keyword-only, and defaults to None
# =========================================================================== #


def test_ac1_overlap_result_keyword_defaults_to_none():
    pm = _per_mode()
    sig = inspect.signature(pm.compute_per_mode_metrics)
    assert "overlap_result" in sig.parameters
    param = sig.parameters["overlap_result"]
    assert param.default is None
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_ac1_omitted_and_explicit_none_are_identical():
    pm = _per_mode()
    omitted = pm.compute_per_mode_metrics(
        _CAND_RECORD, candidate=_CAND_ARRAY, gt=_GT_ARRAY, spacing=_SPACING
    )
    explicit_none = pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=None,
    )
    assert omitted.to_dict() == explicit_none.to_dict()


# =========================================================================== #
# AC2: results are identical whether overlap_result is supplied or computed
# =========================================================================== #


def test_ac2_supplied_result_matches_internally_computed():
    pm = _per_mode()
    overlap = _overlap_mod()

    internal = pm.compute_per_mode_metrics(
        _CAND_RECORD, candidate=_CAND_ARRAY, gt=_GT_ARRAY, spacing=_SPACING
    )
    precomputed = overlap.compute_overlap(_CAND_ARRAY, _GT_ARRAY, _SPACING)
    supplied = pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=precomputed,
    )

    internal_dict = internal.to_dict()
    supplied_dict = supplied.to_dict()
    assert internal_dict == supplied_dict
    # Field-by-field, not just to_dict() equality -- the dataclasses
    # themselves must agree entry for entry.
    for field in dataclasses.fields(pm.PerModeMetrics):
        assert getattr(internal, field.name) == getattr(supplied, field.name)


def test_ac2_matches_for_empty_label_map_pair():
    """Degenerate/boundary case: both candidate and gt are all-background,
    and the supplied ``OverlapResult`` genuinely corresponds to that pair."""
    pm = _per_mode()
    overlap = _overlap_mod()

    empty_cand = np.zeros((4, 4, 4), dtype=np.uint16)
    empty_gt = np.zeros((4, 4, 4), dtype=np.uint16)

    internal = pm.compute_per_mode_metrics({}, candidate=empty_cand, gt=empty_gt, spacing=_SPACING)
    precomputed = overlap.compute_overlap(empty_cand, empty_gt, _SPACING)
    supplied = pm.compute_per_mode_metrics(
        {}, candidate=empty_cand, gt=empty_gt, spacing=_SPACING, overlap_result=precomputed
    )
    assert internal.to_dict() == supplied.to_dict()


# =========================================================================== #
# AC3: the internal compute_overlap call is genuinely skipped
# =========================================================================== #


def test_ac3_no_internal_compute_overlap_call_when_result_supplied(monkeypatch):
    pm = _per_mode()
    overlap = _overlap_mod()

    # Compute the real result *before* patching, so the value fed in is
    # genuinely correct -- only the internal call-avoidance is under test.
    precomputed = overlap.compute_overlap(_CAND_ARRAY, _GT_ARRAY, _SPACING)

    calls = {}
    real = pm.compute_overlap
    monkeypatch.setattr(pm, "compute_overlap", _spy(calls, "compute_overlap", real))

    pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=precomputed,
    )
    assert calls.get("compute_overlap", 0) == 0


def test_ac3_internal_call_still_happens_when_result_is_none(monkeypatch):
    """Control for AC3: the default (``overlap_result=None``) path must still
    call ``compute_overlap`` exactly once -- proves the spy itself works and
    that the short-circuit is conditional, not unconditional."""
    pm = _per_mode()

    calls = {}
    real = pm.compute_overlap
    monkeypatch.setattr(pm, "compute_overlap", _spy(calls, "compute_overlap", real))

    pm.compute_per_mode_metrics(
        _CAND_RECORD, candidate=_CAND_ARRAY, gt=_GT_ARRAY, spacing=_SPACING
    )
    assert calls.get("compute_overlap", 0) == 1


# =========================================================================== #
# AC4: the harness passes its own OverlapResult -- one compute_overlap call
# per candidate-present case, not two.
#
# ``compute_overlap`` is looked up in two places at call time: harness.py
# re-imports it fresh from ``segfacet.eval.overlap`` inside evaluate_case's
# body on every call, while per_mode.py bound its own module-level name once
# at import time. A patch on only one of the two would silently miss half
# the calls, so both are patched with the *same* shared counter.
# =========================================================================== #


def test_ac4_evaluate_case_calls_compute_overlap_exactly_once(monkeypatch):
    harness = _harness_mod()
    overlap = _overlap_mod()
    pm = _per_mode()

    calls = {}
    real = overlap.compute_overlap
    spy = _spy(calls, "compute_overlap", real)
    monkeypatch.setattr(overlap, "compute_overlap", spy)
    monkeypatch.setattr(pm, "compute_overlap", spy)

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_CAND_ARRAY,
        expected={"expected_verdict": "pass"},
    )
    harness.evaluate_case(case, _CONFIG, per_mode=True)

    assert calls.get("compute_overlap", 0) == 1


def test_ac4_evaluate_cohort_calls_compute_overlap_once_per_candidate_case(monkeypatch):
    harness = _harness_mod()
    overlap = _overlap_mod()
    pm = _per_mode()

    calls = {}
    real = overlap.compute_overlap
    spy = _spy(calls, "compute_overlap", real)
    monkeypatch.setattr(overlap, "compute_overlap", spy)
    monkeypatch.setattr(pm, "compute_overlap", spy)

    cases = [
        harness.EvaluationCase(
            case_id=cid,
            gt=_GT_ARRAY,
            candidate=_arr(cid),
            expected={"expected_verdict": "pass"},
        )
        for cid in ("clean_control", "mode1_displace")
    ]
    # A candidate-less case must not call compute_overlap at all.
    cases.append(
        harness.EvaluationCase(
            case_id="no_candidate", gt=_GT_ARRAY, expected={"expected_verdict": "pass"}
        )
    )
    harness.evaluate_cohort(cases, _CONFIG, per_mode=True)

    assert calls.get("compute_overlap", 0) == 2


def test_ac4_without_per_mode_still_calls_compute_overlap_once(monkeypatch):
    """``per_mode=False`` (the default) never touches ``compute_per_mode_metrics``
    at all -- the harness's own overlap call is the only one, before and
    after this item."""
    harness = _harness_mod()
    overlap = _overlap_mod()

    calls = {}
    real = overlap.compute_overlap
    monkeypatch.setattr(overlap, "compute_overlap", _spy(calls, "compute_overlap", real))

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_CAND_ARRAY,
        expected={"expected_verdict": "pass"},
    )
    harness.evaluate_case(case, _CONFIG, per_mode=False)

    assert calls.get("compute_overlap", 0) == 1


# =========================================================================== #
# AC5: harness output is unchanged -- every field matches an independent
# "slow path" recomputation (overlap computed once for `.overlap`, then again
# inside compute_per_mode_metrics via overlap_result=None) -- i.e. exactly
# what the harness produced before item 112.
# =========================================================================== #


def _slow_path_case_dict(cand_arr, gt_arr, case_id, expected_verdict, spacing=_SPACING):
    """Independently reproduce the pre-item-112 evaluate_case computation for
    a candidate-present case: two separate compute_overlap/compute_per_mode_metrics
    passes, mirroring what the harness did before it could share the result."""
    import nibabel as nib

    from segfacet.eval.feature_match import compute_feature_match
    from segfacet.eval.outcome import classify_outcome
    from segfacet.eval.overlap import compute_overlap

    pm = _per_mode()
    harness = _harness_mod()

    cand_img = nib.Nifti1Image(cand_arr, np.eye(4), dtype=cand_arr.dtype)
    gt_img = nib.Nifti1Image(gt_arr, np.eye(4), dtype=gt_arr.dtype)
    case_result, subject_block = run_qc(cand_img, _CONFIG)
    outcome = classify_outcome(
        {"expected_verdict": expected_verdict}, case_result, positive_severity=Severity.FLAG
    )
    overlap_result = compute_overlap(cand_arr, gt_arr, spacing)
    gt_block = extract_feature_record(gt_img, _CONFIG)
    feature_match = compute_feature_match(subject_block, gt_block)
    per_mode_metrics = pm.compute_per_mode_metrics(
        subject_block, candidate=cand_arr, gt=gt_arr, spacing=spacing, overlap_result=None
    )

    expected = harness.CaseEvaluation(
        case_id=case_id,
        outcome=outcome,
        overlap=overlap_result,
        feature_match=feature_match,
        candidate_present=True,
        subject="candidate",
        metadata=None,
        per_mode=per_mode_metrics,
    )
    return expected.to_dict()


def test_ac5_evaluate_case_output_matches_slow_path_recomputation():
    harness = _harness_mod()

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_CAND_ARRAY,
        expected={"expected_verdict": "pass"},
    )
    actual = harness.evaluate_case(case, _CONFIG, per_mode=True)

    expected_dict = _slow_path_case_dict(_CAND_ARRAY, _GT_ARRAY, "c", "pass")
    assert actual.to_dict() == expected_dict


def test_ac5_evaluate_case_output_matches_slow_path_without_per_mode():
    """Same equality holds when per_mode=False -- the harness's own overlap
    field must be untouched by this item regardless of the flag."""
    harness = _harness_mod()

    case = harness.EvaluationCase(
        case_id="c",
        gt=_GT_ARRAY,
        candidate=_CAND_ARRAY,
        expected={"expected_verdict": "pass"},
    )
    actual = harness.evaluate_case(case, _CONFIG, per_mode=False)

    expected_dict = _slow_path_case_dict(_CAND_ARRAY, _GT_ARRAY, "c", "pass")
    expected_dict["per_mode"] = None
    assert actual.to_dict() == expected_dict


def test_ac5_evaluate_cohort_output_matches_slow_path_recomputation():
    harness = _harness_mod()

    fixture_ids = ("clean_control", "mode1_displace")
    cases = [
        harness.EvaluationCase(
            case_id=cid,
            gt=_GT_ARRAY,
            candidate=_arr(cid),
            expected={"expected_verdict": "pass"},
        )
        for cid in fixture_ids
    ]
    result = harness.evaluate_cohort(cases, _CONFIG, per_mode=True)
    assert result.n_cases == len(fixture_ids)

    for cid, record in zip(fixture_ids, result.cases):
        expected_dict = _slow_path_case_dict(_arr(cid), _GT_ARRAY, cid, "pass")
        assert record.to_dict() == expected_dict


# =========================================================================== #
# AC6: a mismatched OverlapResult is rejected cheaply, naming the mismatch
# =========================================================================== #


def test_ac6_shape_mismatched_result_raises():
    pm = _per_mode()
    overlap = _overlap_mod()

    smaller_cand = _CAND_ARRAY[:-1]
    smaller_gt = _GT_ARRAY[:-1]
    assert smaller_cand.shape != _CAND_ARRAY.shape
    wrong_result = overlap.compute_overlap(smaller_cand, smaller_gt, _SPACING)

    with pytest.raises(FacetInputError) as excinfo:
        pm.compute_per_mode_metrics(
            _CAND_RECORD,
            candidate=_CAND_ARRAY,
            gt=_GT_ARRAY,
            spacing=_SPACING,
            overlap_result=wrong_result,
        )
    assert "overlap_result" in str(excinfo.value).lower()


def test_ac6_label_set_mismatched_result_raises():
    pm = _per_mode()
    overlap = _overlap_mod()

    # Same shape as the real pair, but every foreground voxel's label is
    # shifted well outside the real candidate/gt label set -- a disjoint
    # label-set disagreement with no shape difference at all.
    shifted_cand = np.where(_CAND_ARRAY != 0, _CAND_ARRAY.astype(np.int64) + 1000, 0).astype(
        _CAND_ARRAY.dtype
    )
    assert shifted_cand.shape == _CAND_ARRAY.shape
    assert set(np.unique(shifted_cand)) != set(np.unique(_CAND_ARRAY))
    wrong_result = overlap.compute_overlap(shifted_cand, _GT_ARRAY, _SPACING)

    with pytest.raises(FacetInputError) as excinfo:
        pm.compute_per_mode_metrics(
            _CAND_RECORD,
            candidate=_CAND_ARRAY,
            gt=_GT_ARRAY,
            spacing=_SPACING,
            overlap_result=wrong_result,
        )
    assert "overlap_result" in str(excinfo.value).lower()


def test_ac6_different_spacing_is_accepted_not_validated():
    """Adversarial: a supplied OverlapResult computed with *different
    spacing* than the ``spacing=`` argument. ``OverlapResult`` stores no
    spacing field at all (only per-label voxel counts and physical volumes
    already folded in), so spacing agreement is not one of the cheap
    invariants AC6 can check -- documented behaviour is that it is accepted,
    not rejected, consistent with AC7's "trusted beyond the checked
    invariants" contract."""
    pm = _per_mode()
    overlap = _overlap_mod()

    other_spacing = (2.0, 2.0, 2.0)
    result_other_spacing = overlap.compute_overlap(_CAND_ARRAY, _GT_ARRAY, other_spacing)

    # Must not raise: shape and label set both agree with the real pair.
    supplied = pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=result_other_spacing,
    )
    # The caller-supplied result's aggregate fields propagate verbatim,
    # including whatever spacing they were computed with.
    assert supplied.mean_dice == result_other_spacing.mean_dice
    assert supplied.volume_weighted_dice == result_other_spacing.volume_weighted_dice


# =========================================================================== #
# AC7: the docstring names the checked invariants and the trust boundary
# =========================================================================== #


def test_ac7_docstring_names_checked_invariants_and_trust_boundary():
    pm = _per_mode()
    doc = pm.compute_per_mode_metrics.__doc__
    assert doc is not None
    assert "overlap_result" in doc
    assert re.search(r"shape", doc, re.IGNORECASE)
    assert re.search(r"label", doc, re.IGNORECASE)
    assert re.search(r"trust", doc, re.IGNORECASE)


# =========================================================================== #
# AC8: no other call site changes behaviour
# =========================================================================== #


def test_ac8_severity_ladder_call_sites_do_not_pass_overlap_result():
    sl = _severity_ladder_mod()
    source = inspect.getsource(sl)
    assert "overlap_result" not in source


def test_ac8_catalogue_call_site_does_not_pass_overlap_result():
    catalogue = _catalogue_mod()
    source = inspect.getsource(catalogue)
    assert "overlap_result" not in source


def test_ac8_evaluate_ladder_default_path_is_unaffected():
    """A real, unmodified call site (``severity_ladder.evaluate_ladder``,
    which calls ``compute_per_mode_metrics`` without the new keyword) must
    keep producing identical, deterministic output."""
    sl = _severity_ladder_mod()

    spec = sl.SEVERITY_LADDERS[1]
    first = sl.evaluate_ladder(spec)
    second = sl.evaluate_ladder(spec)

    assert dataclasses.asdict(first) == dataclasses.asdict(second)


# =========================================================================== #
# Adversarial: the same OverlapResult object reused across two calls must
# not be mutated.
# =========================================================================== #


def test_reused_overlap_result_object_is_not_mutated():
    pm = _per_mode()
    overlap = _overlap_mod()

    shared = overlap.compute_overlap(_CAND_ARRAY, _GT_ARRAY, _SPACING)
    before = dataclasses.asdict(shared)
    per_label_before = shared.per_label

    pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=shared,
    )
    pm.compute_per_mode_metrics(
        _CAND_RECORD,
        candidate=_CAND_ARRAY,
        gt=_GT_ARRAY,
        spacing=_SPACING,
        overlap_result=shared,
    )

    assert dataclasses.asdict(shared) == before
    assert shared.per_label is per_label_before
