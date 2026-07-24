"""Tests for the evaluation cohort model & harness driver (item 053).

Covers all sixteen Acceptance Criteria plus adversarial and edge-case inputs.
The cohort under test is assembled **entirely in memory** from the Stage-5
synthetic generator (``segfacet.synth.clean_gt.build_clean_spine`` /
``segfacet.synth.corpus.build_corpus``) -- per the item's Assumptions, no disk
I/O and no VerSe/TotalSegmentator download are exercised here; the harness's
own path-source resolution is documented but not tested. ``candidate=None``
means "score the GT against itself" (the clean positive control); a present
``candidate`` is a Stage-5 perturbed segmentation scored against its clean
base as GT.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import json

import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.eval.feature_match import compute_feature_match
from segfacet.eval.outcome import Outcome, classify_outcome
from segfacet.eval.overlap import compute_overlap
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import build_corpus


# =========================================================================== #
# Helpers
# =========================================================================== #


@functools.lru_cache(maxsize=1)
def _config():
    return bundled_default_config()


@functools.lru_cache(maxsize=1)
def _corpus_by_id():
    return {case.case_id: case for case in build_corpus()}


def _gt_for(corpus_case):
    """Rebuild the clean base spine a corpus case's perturbation started from."""
    return build_clean_spine(**corpus_case.base)


def _verdict_label(seg_img, config=None):
    config = config or _config()
    case_result, _block = run_qc(seg_img, config)
    return case_result.verdict.overall.label


# =========================================================================== #
# AC1: module & public API exist
# =========================================================================== #


def test_ac1_import_from_harness_module():
    """AC1: all five names import from segfacet.eval.harness."""
    from segfacet.eval.harness import (  # noqa: F401
        CaseEvaluation,
        CohortEvaluation,
        EvaluationCase,
        evaluate_case,
        evaluate_cohort,
    )

    assert callable(evaluate_case)
    assert callable(evaluate_cohort)


def test_ac1_reexported_from_eval_package():
    """AC1: all five names are re-exported from segfacet.eval."""
    from segfacet.eval import (
        CaseEvaluation,
        CohortEvaluation,
        EvaluationCase,
        evaluate_case,
        evaluate_cohort,
    )

    assert callable(evaluate_case)
    assert callable(evaluate_cohort)


def test_ac1_module_dunder_all():
    """AC1: segfacet.eval.harness.__all__ lists all five public names."""
    import segfacet.eval.harness as harness_mod

    assert set(harness_mod.__all__) >= {
        "EvaluationCase",
        "CaseEvaluation",
        "CohortEvaluation",
        "evaluate_case",
        "evaluate_cohort",
    }


# =========================================================================== #
# AC2: EvaluationCase model
# =========================================================================== #


def test_ac2_construction_and_field_values():
    """AC2: EvaluationCase carries required + optional fields with defaults."""
    from segfacet.eval.harness import EvaluationCase

    clean = build_clean_spine(levels=["L1", "L2"])
    expected = {"expected_verdict": "pass"}
    case = EvaluationCase(case_id="c1", gt=clean.seg_img, expected=expected)

    assert case.case_id == "c1"
    assert case.gt is clean.seg_img
    assert case.candidate is None
    assert case.expected == expected
    assert case.spacing is None
    assert case.metadata is None


def test_ac2_optional_fields_populated():
    """AC2: candidate/spacing/metadata are stored when given."""
    from segfacet.eval.harness import EvaluationCase

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="c2",
        gt=clean.seg_img,
        candidate=clean.seg_img,
        expected={"expected_verdict": "pass"},
        spacing=(1.0, 1.0, 1.0),
        metadata={"source": "unit-test"},
    )
    assert case.candidate is clean.seg_img
    assert case.spacing == (1.0, 1.0, 1.0)
    assert case.metadata == {"source": "unit-test"}


def test_ac2_is_frozen_dataclass():
    """AC2: EvaluationCase is a frozen dataclass -- attribute assignment raises."""
    from segfacet.eval.harness import EvaluationCase

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="c3", gt=clean.seg_img, expected={"expected_verdict": "pass"}
    )
    assert dataclasses.is_dataclass(case)
    assert dataclasses.fields(EvaluationCase)
    with pytest.raises(dataclasses.FrozenInstanceError):
        case.case_id = "changed"


def test_ac2_does_not_mutate_passed_arguments():
    """AC2: the expected mapping and gt array passed in are unchanged after use."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    gt_array = np.asanyarray(clean.seg_img.dataobj).copy()
    expected = {"expected_verdict": "pass"}
    expected_before = copy.deepcopy(expected)
    gt_before = gt_array.copy()

    case = EvaluationCase(
        case_id="c4", gt=gt_array, expected=expected, spacing=clean.spacing
    )
    evaluate_case(case, _config())

    assert expected == expected_before
    np.testing.assert_array_equal(gt_array, gt_before)


# =========================================================================== #
# AC3: seg-source resolution (Nifti1Image and ndarray)
# =========================================================================== #


def test_ac3_nifti1image_sources_yield_well_formed_evaluation():
    """AC3: gt/candidate given as Nifti1Image both resolve and produce a record."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="nifti-case",
        gt=clean.seg_img,
        candidate=clean.seg_img,
        expected={"expected_verdict": "pass"},
    )
    result = evaluate_case(case, _config())
    assert result.case_id == "nifti-case"
    assert result.outcome is not None
    assert result.candidate_present is True


def test_ac3_ndarray_sources_yield_well_formed_evaluation():
    """AC3: gt/candidate given as ndarray (spacing-derived affine) resolve too."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)
    case = EvaluationCase(
        case_id="ndarray-case",
        gt=gt_array,
        candidate=gt_array,
        expected={"expected_verdict": "pass"},
        spacing=clean.spacing,
    )
    result = evaluate_case(case, _config())
    assert result.case_id == "ndarray-case"
    assert result.outcome is not None
    assert result.candidate_present is True


def test_ac3_ndarray_source_defaults_to_isotropic_spacing():
    """AC3: an ndarray source with no spacing given still resolves (default isotropic)."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)
    case = EvaluationCase(
        case_id="ndarray-default-spacing",
        gt=gt_array,
        expected={"expected_verdict": "pass"},
    )
    result = evaluate_case(case, _config())  # must not raise
    assert result.outcome is not None


# =========================================================================== #
# AC4: outcome always populated
# =========================================================================== #


def test_ac4_outcome_matches_direct_classify_outcome_call_no_candidate():
    """AC4: outcome equals classify_outcome(expected, run_qc(gt, config)[0]) when no candidate."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2", "L3"])
    expected = {"expected_verdict": "pass"}
    case = EvaluationCase(case_id="ac4-a", gt=clean.seg_img, expected=expected)
    result = evaluate_case(case, _config())

    direct_case_result, _block = run_qc(clean.seg_img, _config())
    direct_outcome = classify_outcome(expected, direct_case_result)
    assert result.outcome == direct_outcome


def test_ac4_outcome_matches_direct_classify_outcome_call_with_candidate():
    """AC4: outcome equals classify_outcome(expected, run_qc(candidate, config)[0]) when present."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode2_fragment"]
    gt = _gt_for(corpus_case)
    expected = corpus_case.expectation.to_dict()

    case = EvaluationCase(
        case_id="ac4-b",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    result = evaluate_case(case, _config())

    direct_case_result, _block = run_qc(corpus_case.seg_img, _config())
    direct_outcome = classify_outcome(expected, direct_case_result)
    assert result.outcome == direct_outcome


# =========================================================================== #
# AC5: subject-under-QC selection
# =========================================================================== #


def test_ac5_actual_verdict_follows_candidate_not_gt():
    """AC5: when candidate/GT verdicts differ, recorded actual_verdict matches the candidate's."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode2_fragment"]
    gt = _gt_for(corpus_case)
    expected = corpus_case.expectation.to_dict()

    gt_verdict = _verdict_label(gt.seg_img)
    candidate_verdict = _verdict_label(corpus_case.seg_img)
    # Sanity: the perturbation actually changes the verdict (fragmentation
    # is a "pipeline"-detectable mode).
    assert candidate_verdict != gt_verdict

    case = EvaluationCase(
        case_id="ac5",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    result = evaluate_case(case, _config())
    assert result.outcome.actual_verdict == candidate_verdict
    assert result.outcome.actual_verdict != gt_verdict


# =========================================================================== #
# AC6: overlap populated & correct with a candidate
# =========================================================================== #


def test_ac6_overlap_equals_direct_compute_overlap_call():
    """AC6: overlap equals compute_overlap(candidate_array, gt_array, gt_spacing)."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode5_remove_level"]
    gt = _gt_for(corpus_case)
    expected = corpus_case.expectation.to_dict()

    case = EvaluationCase(
        case_id="ac6",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    result = evaluate_case(case, _config())

    candidate_arr = np.asanyarray(corpus_case.seg_img.dataobj)
    gt_arr = np.asanyarray(gt.seg_img.dataobj)
    gt_spacing = tuple(float(z) for z in gt.seg_img.header.get_zooms()[:3])
    direct = compute_overlap(candidate_arr, gt_arr, gt_spacing)

    assert result.overlap == direct


# =========================================================================== #
# AC7: feature-match populated & correct with a candidate
# =========================================================================== #


def test_ac7_feature_match_equals_direct_compute_feature_match_call():
    """AC7: feature_match equals compute_feature_match(candidate_block, extract_feature_record(gt))."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode5_remove_level"]
    gt = _gt_for(corpus_case)
    expected = corpus_case.expectation.to_dict()

    case = EvaluationCase(
        case_id="ac7",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    result = evaluate_case(case, _config())

    candidate_block = extract_feature_record(corpus_case.seg_img, _config())
    gt_block = extract_feature_record(gt.seg_img, _config())
    direct = compute_feature_match(candidate_block, gt_block)

    assert result.feature_match == direct


# =========================================================================== #
# AC8: missing candidate -> unavailable, not errored
# =========================================================================== #


def test_ac8_no_candidate_leaves_overlap_and_feature_match_none():
    """AC8: candidate=None -> overlap/feature_match None, candidate_present False, outcome populated."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2", "L3"])
    case = EvaluationCase(
        case_id="ac8", gt=clean.seg_img, expected={"expected_verdict": "pass"}
    )
    result = evaluate_case(case, _config())  # must not raise

    assert result.overlap is None
    assert result.feature_match is None
    assert result.candidate_present is False
    assert result.outcome is not None


# =========================================================================== #
# AC9: one record per case, order preserved
# =========================================================================== #


def test_ac9_cohort_count_order_and_case_ids():
    """AC9: evaluate_cohort returns len(cases) records, in order, with matching case_ids."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    clean_a = build_clean_spine(levels=["L1", "L2"])
    clean_b = build_clean_spine(levels=["L3", "L4", "L5"])
    corpus_case = _corpus_by_id()["mode2_fragment"]
    corpus_gt = _gt_for(corpus_case)

    cases = [
        EvaluationCase(
            case_id="first", gt=clean_a.seg_img, expected={"expected_verdict": "pass"}
        ),
        EvaluationCase(
            case_id="second", gt=clean_b.seg_img, expected={"expected_verdict": "pass"}
        ),
        EvaluationCase(
            case_id="third",
            gt=corpus_gt.seg_img,
            candidate=corpus_case.seg_img,
            expected=corpus_case.expectation.to_dict(),
        ),
    ]
    cohort = evaluate_cohort(cases, _config())
    assert cohort.n_cases == 3
    assert [record.case_id for record in cohort.cases] == ["first", "second", "third"]


# =========================================================================== #
# AC10: perturbed candidate is distinguishable
# =========================================================================== #


def test_ac10_pipeline_detectable_perturbation_is_caught_and_dice_below_one():
    """AC10: mode2_fragment -> expected_failure True, positive outcome, mean_dice < 1.0.

    fragment carves an interior slab out of the target label's own voxels (the
    label stays present -- and therefore matched -- in both candidate and GT,
    just with fewer voxels), which is what guarantees a sub-1.0 matched-label
    DICE rather than an excluded unmatched entry (as remove_level's full-label
    deletion would give).
    """
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode2_fragment"]
    assert corpus_case.detection == "pipeline"
    gt = _gt_for(corpus_case)
    expected = corpus_case.expectation.to_dict()

    case = EvaluationCase(
        case_id="ac10",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    result = evaluate_case(case, _config())

    assert result.outcome.expected_failure is True
    assert result.outcome.outcome in (Outcome.TRUE_POSITIVE, Outcome.FALSE_NEGATIVE)
    assert result.overlap.mean_dice < 1.0


# =========================================================================== #
# AC11: identical candidate scores perfect DICE & passes
# =========================================================================== #


def test_ac11_identical_candidate_is_perfect_dice_and_true_negative():
    """AC11: candidate array == GT array, clean expectation -> mean_dice 1.0, TRUE_NEGATIVE."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["clean_control"]
    assert corpus_case.expectation.to_dict()["expected_verdict"] == "pass"
    gt = _gt_for(corpus_case)

    case = EvaluationCase(
        case_id="ac11",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,  # identity perturbation: array-equal to gt
        expected=corpus_case.expectation.to_dict(),
    )
    result = evaluate_case(case, _config())

    assert result.overlap.mean_dice == 1.0
    assert result.outcome.outcome is Outcome.TRUE_NEGATIVE


# =========================================================================== #
# AC12: deterministic serialisation
# =========================================================================== #


def test_ac12_to_dict_is_json_serialisable_and_deterministic():
    """AC12: cohort.to_dict() JSON-dumps byte-identically across two runs, keys present."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    corpus_case = _corpus_by_id()["mode2_fragment"]
    gt = _gt_for(corpus_case)
    clean = build_clean_spine(levels=["L1", "L2"])

    cases = [
        EvaluationCase(
            case_id="no-candidate",
            gt=clean.seg_img,
            expected={"expected_verdict": "pass"},
        ),
        EvaluationCase(
            case_id="with-candidate",
            gt=gt.seg_img,
            candidate=corpus_case.seg_img,
            expected=corpus_case.expectation.to_dict(),
        ),
    ]

    cohort_a = evaluate_cohort(cases, _config())
    cohort_b = evaluate_cohort(cases, _config())

    dict_a = cohort_a.to_dict()
    dict_b = cohort_b.to_dict()
    dump_a = json.dumps(dict_a, sort_keys=True)
    dump_b = json.dumps(dict_b, sort_keys=True)
    assert dump_a == dump_b

    # Round-trippable.
    round_tripped = json.loads(dump_a)
    assert round_tripped == dict_a

    records = dict_a["cases"]
    assert len(records) == 2
    by_id = {r["case_id"]: r for r in records}
    assert "outcome" in by_id["no-candidate"]
    assert by_id["no-candidate"]["overlap"] is None
    assert by_id["no-candidate"]["feature_match"] is None
    assert "outcome" in by_id["with-candidate"]
    assert by_id["with-candidate"]["overlap"] is not None
    assert by_id["with-candidate"]["feature_match"] is not None


def test_ac12_outcome_enum_reduced_to_string():
    """AC12: the Outcome enum is reduced to a plain string in to_dict()."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="ac12-enum", gt=clean.seg_img, expected={"expected_verdict": "pass"}
    )
    result = evaluate_case(case, _config())
    outcome_dict = result.to_dict()["outcome"]
    assert isinstance(outcome_dict["outcome"], str)


# =========================================================================== #
# AC13: non-mutation
# =========================================================================== #


def test_ac13_evaluate_case_does_not_mutate_inputs():
    """AC13: evaluate_case leaves the case, config, and gt/candidate arrays unchanged."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    corpus_case = _corpus_by_id()["mode2_fragment"]
    gt = _gt_for(corpus_case)
    gt_array = np.asanyarray(gt.seg_img.dataobj).copy()
    candidate_array = np.asanyarray(corpus_case.seg_img.dataobj).copy()
    expected = corpus_case.expectation.to_dict()
    expected_before = copy.deepcopy(expected)
    config = _config()
    config_before = copy.deepcopy(config)

    case = EvaluationCase(
        case_id="ac13",
        gt=gt.seg_img,
        candidate=corpus_case.seg_img,
        expected=expected,
    )
    evaluate_case(case, config)

    np.testing.assert_array_equal(
        np.asanyarray(gt.seg_img.dataobj), gt_array
    )
    np.testing.assert_array_equal(
        np.asanyarray(corpus_case.seg_img.dataobj), candidate_array
    )
    assert case.expected == expected_before
    assert config == config_before


def test_ac13_evaluate_cohort_does_not_mutate_inputs():
    """AC13: evaluate_cohort leaves every case's arrays/mapping unchanged."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    clean = build_clean_spine(levels=["L1", "L2"])
    gt_array = np.asanyarray(clean.seg_img.dataobj).copy()
    expected = {"expected_verdict": "pass"}
    expected_before = copy.deepcopy(expected)

    cases = [
        EvaluationCase(case_id="only", gt=clean.seg_img, expected=expected),
    ]
    evaluate_cohort(cases, _config())

    np.testing.assert_array_equal(np.asanyarray(clean.seg_img.dataobj), gt_array)
    assert expected == expected_before


# =========================================================================== #
# AC14: shape-mismatch raises clearly
# =========================================================================== #


def test_ac14_shape_mismatched_candidate_and_gt_raises_segfacet_input_error():
    """AC14: candidate/gt arrays of different shape raise FacetInputError."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    gt_array = np.zeros((10, 10, 10), dtype=np.int64)
    candidate_array = np.zeros((12, 10, 10), dtype=np.int64)
    gt_array[2:5, 2:5, 2:5] = 20
    candidate_array[2:5, 2:5, 2:5] = 20

    case = EvaluationCase(
        case_id="ac14",
        gt=gt_array,
        candidate=candidate_array,
        expected={"expected_verdict": "pass"},
        spacing=(1.0, 1.0, 1.0),
    )
    with pytest.raises(FacetInputError):
        evaluate_case(case, _config())


def test_ac14_shape_mismatch_not_raw_value_error():
    """AC14: the shape mismatch is a FacetInputError, not a bare numpy ValueError."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    gt_array = np.zeros((8, 8, 8), dtype=np.int64)
    candidate_array = np.zeros((8, 8, 9), dtype=np.int64)
    gt_array[1:3, 1:3, 1:3] = 20
    candidate_array[1:3, 1:3, 1:3] = 20

    case = EvaluationCase(
        case_id="ac14b",
        gt=gt_array,
        candidate=candidate_array,
        expected={"expected_verdict": "pass"},
        spacing=(1.0, 1.0, 1.0),
    )
    try:
        evaluate_case(case, _config())
    except FacetInputError:
        pass
    else:
        pytest.fail("expected FacetInputError")


# =========================================================================== #
# AC15: empty cohort
# =========================================================================== #


def test_ac15_empty_cohort_returns_zero_records():
    """AC15: evaluate_cohort([], config) -> zero records, no raise."""
    from segfacet.eval.harness import evaluate_cohort

    cohort = evaluate_cohort([], _config())  # must not raise
    assert cohort.n_cases == 0
    assert tuple(cohort.cases) == ()


def test_ac15_empty_cohort_to_dict_is_json_serialisable():
    """AC15: an empty cohort's to_dict() is JSON-serialisable with zero cases."""
    from segfacet.eval.harness import evaluate_cohort

    cohort = evaluate_cohort([], _config())
    d = cohort.to_dict()
    assert d["cases"] == []
    json.dumps(d)  # must not raise


# =========================================================================== #
# AC16: duplicate case ids rejected
# =========================================================================== #


def test_ac16_duplicate_case_ids_raise_segfacet_input_error():
    """AC16: two cases sharing a case_id raise FacetInputError."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    clean = build_clean_spine(levels=["L1", "L2"])
    cases = [
        EvaluationCase(
            case_id="dup", gt=clean.seg_img, expected={"expected_verdict": "pass"}
        ),
        EvaluationCase(
            case_id="dup", gt=clean.seg_img, expected={"expected_verdict": "pass"}
        ),
    ]
    with pytest.raises(FacetInputError):
        evaluate_cohort(cases, _config())


def test_ac16_duplicate_case_ids_not_raw_key_error():
    """AC16: the duplicate case_id rejection is FacetInputError, not a bare KeyError."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    clean = build_clean_spine(levels=["L1", "L2"])
    cases = [
        EvaluationCase(
            case_id="dup2", gt=clean.seg_img, expected={"expected_verdict": "pass"}
        ),
        EvaluationCase(
            case_id="dup2", gt=clean.seg_img, expected={"expected_verdict": "pass"}
        ),
    ]
    try:
        evaluate_cohort(cases, _config())
    except FacetInputError:
        pass
    else:
        pytest.fail("expected FacetInputError")


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_malformed_expected_verdict_propagates_from_outcome_module():
    """A malformed expected mapping (bad verdict label) raises FacetInputError,
    propagated unmodified from item 052's classify_outcome -- evaluate_case does
    not swallow or degrade it into a malformed record."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(
        case_id="bad-expected",
        gt=clean.seg_img,
        expected={"expected_verdict": "bogus-not-a-real-verdict"},
    )
    with pytest.raises(FacetInputError):
        evaluate_case(case, _config())


def test_adv_missing_expected_verdict_key_propagates():
    """An expected mapping missing 'expected_verdict' entirely raises FacetInputError."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2"])
    case = EvaluationCase(case_id="no-verdict-key", gt=clean.seg_img, expected={})
    with pytest.raises(FacetInputError):
        evaluate_case(case, _config())


def test_adv_zero_spacing_component_no_raise_and_zeroes_physical_volume():
    """A zero spacing component on an ndarray source is handled -- no raise, and
    overlap's physical_volume_mm3 collapses to zero while dice is unaffected.

    A single-level GT is used to keep the pipeline on the Stage-2-only path
    (no spline/orientation Stage-3 extractors that could divide by a
    zero-derived spacing component)."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)

    case = EvaluationCase(
        case_id="zero-spacing",
        gt=gt_array,
        candidate=gt_array,
        expected={"expected_verdict": "pass"},
        spacing=(0.0, 1.0, 1.0),
    )
    result = evaluate_case(case, _config())  # must not raise

    assert result.overlap.mean_dice == 1.0
    for entry in result.overlap.per_label:
        assert entry.physical_volume_mm3 == 0.0


def test_adv_single_label_gt_no_stage3_handled_without_raising():
    """A single-label GT (features block has no stage3) still evaluates cleanly
    against a candidate, and the unavailable spline_offset_mm feature does not
    crash the feature-match primitive."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1"])

    case = EvaluationCase(
        case_id="single-label",
        gt=clean.seg_img,
        candidate=clean.seg_img,
        expected={"expected_verdict": "pass"},
    )
    result = evaluate_case(case, _config())  # must not raise

    assert result.feature_match is not None
    assert result.feature_match.n_matched == 1
    entry = result.feature_match.per_label[0]
    offset_diff = next(
        d for d in entry.differences if d.feature == "spline_offset_mm"
    )
    assert offset_diff.available is False


def test_adv_candidate_only_label_surfaces_as_unmatched_in_overlap_and_features():
    """A candidate label absent from GT (and vice versa) surfaces as an unmatched
    entry in both overlap and feature_match, rather than raising."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1", "L2", "L3"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)
    candidate_array = gt_array.copy()
    # Relabel the last present level's voxels to an unmapped value not present
    # in the GT -- candidate gains an extra label, GT loses that label.
    last_label = clean.labels[-1]
    candidate_array[candidate_array == last_label] = 999

    case = EvaluationCase(
        case_id="unmatched-labels",
        gt=gt_array,
        candidate=candidate_array,
        expected={"expected_verdict": "fail"},
        spacing=clean.spacing,
    )
    result = evaluate_case(case, _config())  # must not raise

    overlap_values = {entry.value: entry.matched for entry in result.overlap.per_label}
    assert overlap_values.get(999) is False
    assert overlap_values.get(last_label) is False

    feature_values = {
        entry.value: entry.matched for entry in result.feature_match.per_label
    }
    assert feature_values.get(999) is False
    assert feature_values.get(last_label) is False


def test_adv_mixed_nifti1image_and_ndarray_sources_in_one_cohort():
    """A cohort mixing Nifti1Image-sourced and ndarray-sourced cases evaluates
    both without error, source-agnostically."""
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort

    clean_a = build_clean_spine(levels=["L1", "L2"])
    clean_b = build_clean_spine(levels=["L3", "L4", "L5"])
    gt_b_array = np.asanyarray(clean_b.seg_img.dataobj)

    cases = [
        EvaluationCase(
            case_id="nifti-sourced",
            gt=clean_a.seg_img,
            candidate=clean_a.seg_img,
            expected={"expected_verdict": "pass"},
        ),
        EvaluationCase(
            case_id="ndarray-sourced",
            gt=gt_b_array,
            candidate=gt_b_array,
            expected={"expected_verdict": "pass"},
            spacing=clean_b.spacing,
        ),
    ]
    cohort = evaluate_cohort(cases, _config())  # must not raise
    assert cohort.n_cases == 2
    assert [r.case_id for r in cohort.cases] == ["nifti-sourced", "ndarray-sourced"]
    for record in cohort.cases:
        assert record.overlap.mean_dice == 1.0


def test_adv_negative_spacing_component_does_not_raise():
    """A negative spacing component on an ndarray source is degenerate input but
    must not crash the resolver or the overlap primitive.

    A single-level GT keeps the pipeline on the Stage-2-only path, avoiding
    Stage-3 spline/orientation extractors that a negative-determinant affine
    could otherwise upset."""
    from segfacet.eval.harness import EvaluationCase, evaluate_case

    clean = build_clean_spine(levels=["L1"])
    gt_array = np.asanyarray(clean.seg_img.dataobj)

    case = EvaluationCase(
        case_id="negative-spacing",
        gt=gt_array,
        candidate=gt_array,
        expected={"expected_verdict": "pass"},
        spacing=(-1.0, 1.0, 1.0),
    )
    evaluate_case(case, _config())  # must not raise
