"""Tests for item 036 — synthetic-corpus foundation: perturbation framework.

Covers Acceptance Criteria AC12-AC23 (Group B, the perturbation framework, and
Group C, determinism/immutability):

- AC12: Perturbation is an abstract base.
- AC13: Expectation has the pinned frozen-dataclass shape.
- AC14: Expectation.to_dict() is JSON-ready.
- AC15: PerturbationResult is an unpackable named pair.
- AC16: the registry registers and looks up by name.
- AC17: duplicate and unknown names are rejected.
- AC18: IdentityPerturbation is registered under "identity".
- AC19: identity returns an array equal to its input.
- AC20: identity's expectation is the well-formed clean control.
- AC21: identity's expectation is consistent with the pipeline.
- AC22: perturbation output is reproducible (same seed + input -> identical
  array).
- AC23: apply does not mutate the caller's input.

Adversarial / edge-case scenarios included:
- Registering Perturbation() itself (the abstract base) raises TypeError.
- Duplicate-name collision across two distinct classes.
- Unknown-name lookup raises KeyError with a non-empty message.
- Mutation-safety check via a distinctive sentinel voxel value.
- Identity is seed-independent (two different seeds still yield equal
  arrays).
- Expectation with an unvalidated/free-form expected_verdict string is still
  constructible (the framework does not validate verdict strings).
- PerturbationResult is a genuine 2-tuple (len == 2, isinstance tuple).
- Registry isolation: a throwaway registration in one test does not leak into
  perturbation_names()/iter_perturbations() of another test.
"""

from __future__ import annotations

import dataclasses
import json

import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.pipeline import run_qc
from segfacet.synth import (
    CLEAN_CONTROL_MODE,
    FAILURE_MODE_NAMES,
    Expectation,
    IdentityPerturbation,
    Perturbation,
    PerturbationResult,
    build_clean_spine,
    get_perturbation,
    iter_perturbations,
    perturbation_names,
    register_perturbation,
)

from synthetic import make_labelmap


# =========================================================================== #
# Registry isolation -- snapshot/restore around every test in this module
# =========================================================================== #


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot the perturbation registry before each test and restore it
    afterwards, mirroring the item-026/032 _RULES snapshot idiom, so
    throwaway registrations in one test never leak into another."""
    from segfacet.synth.perturbation import _PERTURBATIONS

    snapshot = dict(_PERTURBATIONS)
    yield
    _PERTURBATIONS.clear()
    _PERTURBATIONS.update(snapshot)


# =========================================================================== #
# Helpers
# =========================================================================== #


def _dummy_expectation() -> Expectation:
    return Expectation(
        failure_mode=CLEAN_CONTROL_MODE,
        failure_mode_name=FAILURE_MODE_NAMES[0],
        expected_rule_ids=frozenset(),
        expected_labels=frozenset(),
        expected_verdict="pass",
    )


def _default_clean_seg_img():
    return build_clean_spine().seg_img


# =========================================================================== #
# AC12: Perturbation is an abstract base
# =========================================================================== #


def test_ac12_perturbation_cannot_be_instantiated_directly():
    """AC12: Perturbation() raises TypeError because apply is abstract."""
    with pytest.raises(TypeError):
        Perturbation()  # type: ignore[abstract]


def test_ac12_subclass_without_apply_cannot_instantiate():
    """AC12: a Perturbation subclass that omits apply() raises TypeError."""

    class _IncompletePerturbation036(Perturbation):
        name = "incomplete_036"

    with pytest.raises(TypeError):
        _IncompletePerturbation036()


def test_ac12_concrete_subclass_declares_name_and_apply():
    """AC12: a concrete subclass with name + apply(self, labelmap, seed)
    instantiates and is a Perturbation."""

    class _ConcretePerturbation036(Perturbation):
        name = "concrete_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    instance = _ConcretePerturbation036()
    assert isinstance(instance, Perturbation)
    assert instance.name == "concrete_036"


# =========================================================================== #
# AC13: Expectation has the pinned shape
# =========================================================================== #


def test_ac13_expectation_constructs_with_pinned_fields():
    """AC13: Expectation constructs with the five pinned fields."""
    exp = Expectation(
        failure_mode=1,
        failure_mode_name=FAILURE_MODE_NAMES[1],
        expected_rule_ids=frozenset({"mislabel"}),
        expected_labels=frozenset({20}),
        expected_verdict="flagged-for-review",
    )
    assert exp.failure_mode == 1
    assert exp.failure_mode_name == FAILURE_MODE_NAMES[1]
    assert exp.expected_rule_ids == frozenset({"mislabel"})
    assert exp.expected_labels == frozenset({20})
    assert exp.expected_verdict == "flagged-for-review"


def test_ac13_identically_constructed_expectations_compare_equal():
    """AC13: two identically-constructed Expectations compare equal."""
    kwargs = dict(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        expected_rule_ids=frozenset({"overlap"}),
        expected_labels=frozenset({20, 21}),
        expected_verdict="fail",
    )
    assert Expectation(**kwargs) == Expectation(**kwargs)


def test_ac13_expectation_is_frozen():
    """AC13: Expectation is a frozen dataclass -- field assignment raises."""
    exp = _dummy_expectation()
    with pytest.raises(dataclasses.FrozenInstanceError):
        exp.failure_mode = 5  # type: ignore[misc]


# =========================================================================== #
# AC14: Expectation.to_dict() is JSON-ready
# =========================================================================== #


def test_ac14_to_dict_rule_ids_sorted_list():
    """AC14: to_dict()["expected_rule_ids"] == ["overlap"] (sorted list)."""
    exp = Expectation(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        expected_rule_ids=frozenset({"overlap"}),
        expected_labels=frozenset({21, 20}),
        expected_verdict="fail",
    )
    assert exp.to_dict()["expected_rule_ids"] == ["overlap"]


def test_ac14_to_dict_labels_sorted_list():
    """AC14: to_dict()["expected_labels"] == [20, 21] (sorted list)."""
    exp = Expectation(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        expected_rule_ids=frozenset({"overlap"}),
        expected_labels=frozenset({21, 20}),
        expected_verdict="fail",
    )
    assert exp.to_dict()["expected_labels"] == [20, 21]


def test_ac14_to_dict_scalar_fields_verbatim():
    """AC14: to_dict()'s scalar fields match verbatim."""
    exp = Expectation(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        expected_rule_ids=frozenset({"overlap"}),
        expected_labels=frozenset({21, 20}),
        expected_verdict="fail",
    )
    d = exp.to_dict()
    assert d["failure_mode"] == 8
    assert d["failure_mode_name"] == FAILURE_MODE_NAMES[8]
    assert d["expected_verdict"] == "fail"


def test_ac14_to_dict_is_json_dumpable():
    """AC14: json.dumps accepts the to_dict() output."""
    exp = Expectation(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        expected_rule_ids=frozenset({"overlap"}),
        expected_labels=frozenset({21, 20}),
        expected_verdict="fail",
    )
    serialized = json.dumps(exp.to_dict())
    assert isinstance(serialized, str)


# =========================================================================== #
# AC15: PerturbationResult is an unpackable named pair
# =========================================================================== #


def test_ac15_unpacks_to_labelmap_and_expectation():
    """AC15: lm, ex = result unpacks to (img, exp)."""
    img = make_labelmap()
    exp = _dummy_expectation()
    result = PerturbationResult(labelmap=img, expectation=exp)
    lm, ex = result
    assert lm is img
    assert ex is exp


def test_ac15_named_attribute_access():
    """AC15: result.labelmap is img and result.expectation is exp."""
    img = make_labelmap()
    exp = _dummy_expectation()
    result = PerturbationResult(labelmap=img, expectation=exp)
    assert result.labelmap is img
    assert result.expectation is exp


# =========================================================================== #
# AC16: The registry registers and looks up by name
# =========================================================================== #


def test_ac16_get_perturbation_returns_registered_class():
    """AC16: get_perturbation returns the registered class."""

    class _Dummy036(Perturbation):
        name = "dummy_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_Dummy036)
    assert get_perturbation("dummy_036") is _Dummy036


def test_ac16_name_appears_in_perturbation_names():
    """AC16: the registered name appears in perturbation_names()."""

    class _Dummy036b(Perturbation):
        name = "dummy_036b"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_Dummy036b)
    assert "dummy_036b" in perturbation_names()


def test_ac16_class_appears_in_iter_perturbations():
    """AC16: the registered class appears in iter_perturbations()."""

    class _Dummy036c(Perturbation):
        name = "dummy_036c"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_Dummy036c)
    assert _Dummy036c in list(iter_perturbations())


def test_ac16_iter_perturbations_sorted_by_name():
    """AC16: iter_perturbations() is sorted by name."""

    class _Zzz036(Perturbation):
        name = "zzz_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    class _Aaa036(Perturbation):
        name = "aaa_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_Zzz036)
    register_perturbation(_Aaa036)
    names = [cls.name for cls in iter_perturbations()]
    assert names == sorted(names)


# =========================================================================== #
# AC17: Duplicate and unknown names are rejected
# =========================================================================== #


def test_ac17_duplicate_name_raises_value_error():
    """AC17: a second class registered under an already-used name raises
    ValueError."""

    class _DupA036(Perturbation):
        name = "dup_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    class _DupB036(Perturbation):
        name = "dup_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_DupA036)
    with pytest.raises(ValueError):
        register_perturbation(_DupB036)


def test_ac17_unknown_name_raises_key_error():
    """AC17: get_perturbation on an unregistered name raises KeyError."""
    with pytest.raises(KeyError):
        get_perturbation("does-not-exist-036")


# =========================================================================== #
# AC18: IdentityPerturbation is registered under "identity"
# =========================================================================== #


def test_ac18_identity_registered_under_identity_name():
    """AC18: get_perturbation("identity") returns IdentityPerturbation."""
    assert get_perturbation("identity") is IdentityPerturbation


# =========================================================================== #
# AC19: Identity returns an array equal to its input
# =========================================================================== #


def test_ac19_identity_array_equals_input():
    """AC19: identity's output data array equals the input's."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    in_data = np.asanyarray(seg_img.dataobj)
    out_data = np.asanyarray(result.labelmap.dataobj)
    assert np.array_equal(in_data, out_data)


def test_ac19_identity_preserves_affine():
    """AC19: identity's output affine equals the input's affine."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert np.array_equal(result.labelmap.affine, seg_img.affine)


def test_ac19_identity_preserves_spacing():
    """AC19: identity's output get_zooms()[:3] equals the input's spacing."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert result.labelmap.header.get_zooms()[:3] == seg_img.header.get_zooms()[:3]


# =========================================================================== #
# AC20: Identity's expectation is the well-formed clean control
# =========================================================================== #


def test_ac20_identity_expectation_failure_mode_is_clean_control():
    """AC20: failure_mode == CLEAN_CONTROL_MODE == 0."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert result.expectation.failure_mode == CLEAN_CONTROL_MODE
    assert result.expectation.failure_mode == 0


def test_ac20_identity_expectation_failure_mode_name():
    """AC20: failure_mode_name == FAILURE_MODE_NAMES[0]."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert result.expectation.failure_mode_name == FAILURE_MODE_NAMES[0]


def test_ac20_identity_expectation_empty_rule_ids_and_labels():
    """AC20: expected_rule_ids and expected_labels are both empty frozensets."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert result.expectation.expected_rule_ids == frozenset()
    assert result.expectation.expected_labels == frozenset()


def test_ac20_identity_expectation_verdict_is_pass():
    """AC20: expected_verdict == "pass"."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    assert result.expectation.expected_verdict == "pass"


# =========================================================================== #
# AC21: Identity's expectation is consistent with the pipeline
# =========================================================================== #


def test_ac21_identity_perturbed_clean_gt_has_no_findings():
    """AC21: running the identity-perturbed clean GT through run_qc yields
    findings == ()."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.findings == ()


def test_ac21_identity_expectation_matches_pipeline_verdict():
    """AC21: verdict.overall.label == result.expectation.expected_verdict."""
    seg_img = _default_clean_seg_img()
    result = IdentityPerturbation().apply(seg_img, seed=0)
    case_result, _block = run_qc(result.labelmap, bundled_default_config())
    assert case_result.verdict.overall.label == result.expectation.expected_verdict


# =========================================================================== #
# AC22: Perturbation output is reproducible
# =========================================================================== #


def test_ac22_same_seed_same_input_yields_identical_array():
    """AC22: two identity apply() calls at seed=7 return array_equal outputs."""
    seg_img = _default_clean_seg_img()
    r1 = IdentityPerturbation().apply(seg_img, seed=7)
    r2 = IdentityPerturbation().apply(seg_img, seed=7)
    data1 = np.asanyarray(r1.labelmap.dataobj)
    data2 = np.asanyarray(r2.labelmap.dataobj)
    assert np.array_equal(data1, data2)


# =========================================================================== #
# AC23: apply does not mutate the caller's input
# =========================================================================== #


def test_ac23_apply_does_not_mutate_input_array():
    """AC23: the seg_img's data array is unchanged after apply()."""
    seg_img = _default_clean_seg_img()
    data_before = np.array(np.asanyarray(seg_img.dataobj), copy=True)
    IdentityPerturbation().apply(seg_img, seed=0)
    data_after = np.asanyarray(seg_img.dataobj)
    assert np.array_equal(data_before, data_after)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_registering_incomplete_subclass_never_reaches_registry():
    """Adversarial: an abstract (incomplete) Perturbation subclass cannot be
    instantiated even after registration -- register_perturbation stores the
    class, not an instance, so registration itself succeeds but instantiation
    still fails."""

    class _IncompleteRegistered036(Perturbation):
        name = "incomplete_registered_036"

    register_perturbation(_IncompleteRegistered036)
    cls = get_perturbation("incomplete_registered_036")
    with pytest.raises(TypeError):
        cls()


def test_adv_duplicate_name_error_message_non_empty():
    """Adversarial: the ValueError for a duplicate name has a non-empty
    message."""

    class _DupMsgA036(Perturbation):
        name = "dup_msg_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    class _DupMsgB036(Perturbation):
        name = "dup_msg_036"

        def apply(self, labelmap, seed):
            return PerturbationResult(labelmap=labelmap, expectation=_dummy_expectation())

    register_perturbation(_DupMsgA036)
    with pytest.raises(ValueError) as exc_info:
        register_perturbation(_DupMsgB036)
    assert str(exc_info.value).strip()


def test_adv_mutation_safety_sentinel_voxel_preserved_on_input():
    """Adversarial: a distinctive sentinel voxel value on the input is still
    present (unchanged) on the caller's array after apply()."""
    seg_img = make_labelmap(blocks={7: ((2, 6), (2, 6), (2, 6))})
    data = np.asanyarray(seg_img.dataobj)
    sentinel_index = (3, 3, 3)
    assert int(data[sentinel_index]) == 7  # sanity: sentinel is inside the block
    IdentityPerturbation().apply(seg_img, seed=0)
    data_after = np.asanyarray(seg_img.dataobj)
    assert int(data_after[sentinel_index]) == 7


def test_adv_identity_is_seed_independent():
    """Adversarial: identity ignores the seed -- two different seeds still
    yield equal output arrays."""
    seg_img = _default_clean_seg_img()
    r_seed0 = IdentityPerturbation().apply(seg_img, seed=0)
    r_seed999 = IdentityPerturbation().apply(seg_img, seed=999)
    data0 = np.asanyarray(r_seed0.labelmap.dataobj)
    data999 = np.asanyarray(r_seed999.labelmap.dataobj)
    assert np.array_equal(data0, data999)


def test_adv_expectation_with_arbitrary_verdict_string_is_constructible():
    """Adversarial: Expectation does not validate expected_verdict -- an
    arbitrary/free-form string is still accepted (validated elsewhere)."""
    exp = Expectation(
        failure_mode=3,
        failure_mode_name=FAILURE_MODE_NAMES[3],
        expected_rule_ids=frozenset({"fragmentation"}),
        expected_labels=frozenset({21}),
        expected_verdict="not-a-real-verdict",
    )
    assert exp.expected_verdict == "not-a-real-verdict"


def test_adv_perturbation_result_is_a_two_element_tuple():
    """Adversarial: PerturbationResult is a genuine 2-element tuple."""
    img = make_labelmap()
    exp = _dummy_expectation()
    result = PerturbationResult(labelmap=img, expectation=exp)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_adv_registry_isolation_does_not_leak_across_tests():
    """Adversarial: a name registered by an earlier test in this module (e.g.
    'dummy_036' from AC16) is not visible here -- the autouse snapshot/restore
    fixture prevented leakage."""
    assert "dummy_036" not in perturbation_names()
    assert "dup_036" not in perturbation_names()
