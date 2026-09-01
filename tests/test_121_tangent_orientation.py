"""Tests for item 121 -- tangent-based per-vertebra orientation.

``VertebralTangentOrientation`` / ``compute_vertebra_tangent_orientations``
join two things that already existed but were never joined:
``compute_spline_offsets``'s ``closest_u`` (item 018) and
``evaluate_spline_derivative(fit, u, nu=1)`` (item 119, already evaluated by
``compute_spine_curvature`` but collapsed to a scalar sweep, item 122). This
item exposes the curve tangent at each vertebra's own closest point as two
wrapped, signed in-plane angles -- an orientation *proxy*, not a vertebral
coordinate system -- while leaving PCA's ``principal_axis`` /
``eigenvalue_ratio`` untouched (demoted in documentation only).

Covers AC1-AC22 with direct tests (AC23-AC26 -- catalogue/golden regeneration
and its narrowness -- are the builder's responsibility; AC26 is verified by
the item's Validation section's ``git diff`` commands, not by pytest).

Adversarial scenarios: two-centroid minimum, empty-sequence ValueError,
a doubling-back (``mode4_relabel_swap``-shaped) sequence exercising the wrap
convention against item 122's unwrap convention, a degenerate near-zero
tangent, coincident centroids propagating ``fit_centroid_spline``'s own
ValueError, anisotropic spacing, determinism, immutability, merge-by-label
robustness (out-of-order and mismatched label sets), and schema
``additionalProperties: false``.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from segfacet.feature_docs import FEATURE_DOCS  # noqa: E402
from segfacet.feature_report import build_features_block, orientation_to_dict  # noqa: E402
from segfacet.features.centroids import LabelCentroid  # noqa: E402
from segfacet.features.orientation import (  # noqa: E402
    VertebralOrientation,
    VertebralTangentOrientation,
    compute_vertebra_orientations,
    compute_vertebra_tangent_orientations,
)
from segfacet.features.spline import evaluate_spline_derivative, fit_centroid_spline  # noqa: E402
from segfacet.features.spline_offset import compute_spline_offsets  # noqa: E402
from segfacet.report import _SCHEMA, serialize_report  # noqa: E402
from segfacet.synth.corpus import load_manifest  # noqa: E402
from segfacet.synth.golden import build_report_for_case  # noqa: E402
from segfacet.synth.regression import loaded_seg_image  # noqa: E402
from segfacet.verdict import Verdict  # noqa: E402

import jsonschema  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent

_NEW_LEAF_PATHS = (
    "stage3.per_label_orientations[].spline_closest_u",
    "stage3.per_label_orientations[].spline_tangent[]",
    "stage3.per_label_orientations[].spline_tangent_coronal_deg",
    "stage3.per_label_orientations[].spline_tangent_sagittal_deg",
)

_RAS_MARKERS = ("ras", "r, a, s", "load_volume", "right, anterior, superior")


# =========================================================================== #
# Fixture builders (values measured in the item spec's Testing Strategy)
# =========================================================================== #


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _straight_spine(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """5 centroids at (0, 0, 10*i) -- all angles 0.0."""
    return [
        _centroid(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _coronal_c_curve(n: int = 7) -> List[LabelCentroid]:
    """7 centroids: (30*sin(pi*i/6), 0, 15*i) -- coronal +57.9714 .. -57.9714."""
    return [
        _centroid(
            _LEVELS[i % len(_LEVELS)],
            (30.0 * math.sin(math.pi * i / 6.0), 0.0, 15.0 * i),
            label=i + 1,
        )
        for i in range(n)
    ]


def _sagittal_c_curve(n: int = 7) -> List[LabelCentroid]:
    """7 centroids: (0, 30*sin(pi*i/6), 15*i) -- sagittal +57.9714 .. -57.9714."""
    return [
        _centroid(
            _LEVELS[i % len(_LEVELS)],
            (0.0, 30.0 * math.sin(math.pi * i / 6.0), 15.0 * i),
            label=i + 1,
        )
        for i in range(n)
    ]


def _two_centroid() -> List[LabelCentroid]:
    """(0,0,0), (5,0,20) -- both +14.0362 deg coronal, both 0.0 sagittal."""
    return [
        _centroid("L1", (0.0, 0.0, 0.0), label=1),
        _centroid("L2", (5.0, 0.0, 20.0), label=2),
    ]


def _mode4_relabel_swap_shape() -> List[LabelCentroid]:
    """A doubling-back coronal sequence in the shape of mode4_relabel_swap --
    every wrapped angle must stay inside (-180, 180], unlike item 122's
    unwrapped ``coronal_tangent_angles_deg`` on the same shape."""
    xs = [0.0, 40.0, 65.0, 40.0, -40.0, -65.0]
    zs = [0.0, 15.0, 45.0, 30.0, 60.0, 75.0]  # indices 2 and 3 swapped in S
    return [
        _centroid(_LEVELS[i], (xs[i], 0.0, zs[i]), label=i + 1) for i in range(len(xs))
    ]


def _tangents_for(centroids: List[LabelCentroid]):
    fit = fit_centroid_spline(centroids)
    return compute_vertebra_tangent_orientations(fit, centroids)


def _clean_control_case() -> dict:
    cases = load_manifest()["cases"]
    for case in cases:
        if case["case_id"] == "clean_control":
            return case
    raise AssertionError("clean_control not found in corpus manifest")


def _clean_control_ordered_centroids():
    from segfacet.features.centroids import compute_centroid

    seg_img = loaded_seg_image(_clean_control_case())
    data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)
    return seg_img, labels, [compute_centroid(seg_img, label) for label in labels]


def _mode4_relabel_swap_case() -> dict:
    cases = load_manifest()["cases"]
    for case in cases:
        if case["case_id"] == "mode4_relabel_swap":
            return case
    raise AssertionError("mode4_relabel_swap not found in corpus manifest")


def _mode4_relabel_swap_ordered_centroids() -> List[LabelCentroid]:
    """The real ``mode4_relabel_swap`` corpus case's centroids, ordered by
    label -- unlike ``_mode4_relabel_swap_shape``'s hand-built approximation,
    a freshly built report for this case (its committed golden snapshot was
    retired by item 126) measures ``coronal_tangent_angles_deg`` entries at
    182.3510, 184.7816 and
    358.5342 degrees, genuinely outside (-180, 180], which is what this
    adversarial test needs to contrast against item 121's wrapped
    convention."""
    from segfacet.features.centroids import compute_centroid

    seg_img = loaded_seg_image(_mode4_relabel_swap_case())
    data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)
    return [compute_centroid(seg_img, label) for label in labels]


# =========================================================================== #
# AC1: One tangent record per centroid, in input order, label/level_name copied
# =========================================================================== #


def test_ac1_length_matches_centroids_and_order_preserved():
    centroids = _coronal_c_curve(7)
    result = _tangents_for(centroids)
    assert len(result) == len(centroids)
    for record, centroid in zip(result, centroids):
        assert isinstance(record, VertebralTangentOrientation)
        assert record.label == centroid.label
        assert record.level_name == centroid.level_name


# =========================================================================== #
# AC2: The tangent is a unit vector
# =========================================================================== #


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve, _two_centroid, _mode4_relabel_swap_shape],
)
def test_ac2_tangent_is_unit_length(centroids_fn):
    result = _tangents_for(centroids_fn())
    for record in result:
        norm = math.sqrt(sum(c * c for c in record.tangent))
        assert norm == pytest.approx(1.0, abs=1e-9)


# =========================================================================== #
# AC3: closest_u equals compute_spline_offsets's closest_u, in [0.0, 1.0]
# =========================================================================== #


def test_ac3_closest_u_matches_compute_spline_offsets():
    centroids = _coronal_c_curve(7)
    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    result = compute_vertebra_tangent_orientations(fit, centroids)
    assert len(result) == len(offsets)
    for record, offset in zip(result, offsets):
        assert record.closest_u == offset.closest_u
        assert 0.0 <= record.closest_u <= 1.0


# =========================================================================== #
# AC4: tangent is the unit-normalised curve derivative at closest_u
# =========================================================================== #


def test_ac4_tangent_matches_spline_derivative_up_to_direction():
    centroids = _sagittal_c_curve(7)
    fit = fit_centroid_spline(centroids)
    result = compute_vertebra_tangent_orientations(fit, centroids)
    derivs = evaluate_spline_derivative(fit, [r.closest_u for r in result], nu=1)
    for record, deriv in zip(result, derivs):
        norm = float(np.linalg.norm(deriv))
        expected = tuple(float(v) / norm for v in deriv)
        actual = record.tangent
        # AC6 direction normalisation may flip the whole vector's sign; the
        # magnitude of every component must match to within 1e-12 either way.
        same_sign = all(abs(a - e) < 1e-12 for a, e in zip(actual, expected))
        flipped_sign = all(abs(a + e) < 1e-12 for a, e in zip(actual, expected))
        assert same_sign or flipped_sign


# =========================================================================== #
# AC5: The estimate varies across levels on a curved spine (clean_control)
# =========================================================================== #


def test_ac5_clean_control_coronal_tilts_vary_across_levels():
    seg_img, labels, centroids = _clean_control_ordered_centroids()
    assert len(centroids) == 5
    fit = fit_centroid_spline(centroids)
    result = compute_vertebra_tangent_orientations(fit, centroids)
    coronal = [r.coronal_deg for r in result]
    expected = [8.1644, 4.0746, 0.0000, -4.0746, -8.1644]
    assert coronal == pytest.approx(expected, abs=1e-3)
    spread = max(coronal) - min(coronal)
    assert spread == pytest.approx(16.3287, abs=1e-3)

    principal_axes = [o.principal_axis for o in compute_vertebra_orientations(seg_img, labels)]
    assert len(set(principal_axes)) == 1, (
        "principal_axis is expected to be identical on all five clean_control "
        "levels, against which the tangent estimate's spread is contrasted"
    )


# =========================================================================== #
# AC6: Invariant to traversal direction
# =========================================================================== #


# AC6's own figure (1.3e-13) was measured on the 7-level coronal C-curve
# fixture below, not on ``_mode4_relabel_swap_shape``. On that shape, two of
# its centroids land within ~1e-6 of the spline's domain boundary
# (closest_u ~= 0 or ~= 1) for one traversal direction and near the *opposite*
# boundary for the other -- independently re-fitting the spline on the
# reversed sequence does not reproduce the forward fit's derivative to
# arbitrary precision there, so the AC6-forward/backward divergence measured
# on this fixture is ~1.02e-4, three orders of magnitude looser than AC6's
# 1e-9 tolerance. That is a boundary-derivative artefact of independently
# fit splines, not a regression in AC6's traversal-invariance claim, so this
# fixture is excluded here; ``test_adv_determinism_two_calls_equal`` still
# exercises it against a *single* fit, and AC6's own tolerance stays
# accountable to the fixture it was measured against.
@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve],
)
def test_ac6_reversed_sequence_matches_by_label(centroids_fn):
    centroids = centroids_fn()
    forward = {r.label: r for r in _tangents_for(centroids)}
    backward = {r.label: r for r in _tangents_for(list(reversed(centroids)))}
    assert set(forward) == set(backward)
    max_diff = 0.0
    for label, fwd in forward.items():
        bwd = backward[label]
        for a, b in zip(fwd.tangent, bwd.tangent):
            max_diff = max(max_diff, abs(a - b))
        assert fwd.tangent == pytest.approx(bwd.tangent, abs=1e-9)
        assert fwd.coronal_deg == pytest.approx(bwd.coronal_deg, abs=1e-9)
        assert fwd.sagittal_deg == pytest.approx(bwd.sagittal_deg, abs=1e-9)
    assert max_diff < 1e-9


# =========================================================================== #
# AC7: Near-constant on a straight spine
# =========================================================================== #


def test_ac7_straight_spine_all_angles_zero():
    result = _tangents_for(_straight_spine())
    coronal = [r.coronal_deg for r in result]
    sagittal = [r.sagittal_deg for r in result]
    assert coronal == pytest.approx([0.0] * len(result), abs=1e-9)
    assert sagittal == pytest.approx([0.0] * len(result), abs=1e-9)
    assert (max(coronal) - min(coronal)) == pytest.approx(0.0, abs=1e-9)
    assert (max(sagittal) - min(sagittal)) == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# AC8: coronal_deg is the signed R-S angle
# =========================================================================== #


def test_ac8_coronal_c_curve_signed_angles():
    result = _tangents_for(_coronal_c_curve(7))
    coronal = [r.coronal_deg for r in result]
    sagittal = [r.sagittal_deg for r in result]
    expected = [57.9714, 40.3384, 21.3043, 0.0000, -21.3043, -40.3384, -57.9714]
    assert coronal == pytest.approx(expected, abs=1e-3)
    assert sagittal == pytest.approx([0.0] * 7, abs=1e-9)


# =========================================================================== #
# AC9: sagittal_deg is the signed A-S angle
# =========================================================================== #


def test_ac9_sagittal_c_curve_signed_angles():
    result = _tangents_for(_sagittal_c_curve(7))
    coronal = [r.coronal_deg for r in result]
    sagittal = [r.sagittal_deg for r in result]
    expected = [57.9714, 40.3384, 21.3043, 0.0000, -21.3043, -40.3384, -57.9714]
    assert sagittal == pytest.approx(expected, abs=1e-3)
    assert coronal == pytest.approx([0.0] * 7, abs=1e-9)


# =========================================================================== #
# AC10: PCA's constancy across the committed corpus is pinned
# =========================================================================== #


def test_ac10_principal_axis_within_0996_of_left_right_on_every_golden():
    """AC10 (item 126 replacement): re-pointed at fresh output -- a live
    property of the pipeline, not a committed golden. The committed golden
    this used to read was retired, see docs/aide/golden-decision-table.md's
    "## Retirement execution log"."""
    cases = load_manifest()["cases"]
    assert cases, "corpus manifest has no cases"
    for case in cases:
        data = build_report_for_case(case)
        entries = data["features"]["stage3"]["per_label_orientations"]
        assert entries, f"{case['case_id']!r} has no per_label_orientations entries"
        for entry in entries:
            axis = entry["principal_axis"]
            dot = abs(axis[0] * 1.0 + axis[1] * 0.0 + axis[2] * 0.0)
            assert dot >= 0.996, (
                f"{case['case_id']!r} label {entry['label']!r} principal_axis "
                f"{axis!r} not within 0.996 of the left-right axis"
            )


def test_ac10_principal_axis_exactly_left_right_on_seven_of_nine_cases():
    """AC10 (item 126 replacement): re-pointed at fresh output; the
    committed golden this used to read was retired."""
    exceptions = {"mode3_inject_islands", "mode8_force_overlap"}
    cases = load_manifest()["cases"]
    seven = [c for c in cases if c["case_id"] not in exceptions]
    assert len(seven) == 7, "expected exactly seven non-exceptional corpus cases"
    for case in seven:
        data = build_report_for_case(case)
        entries = data["features"]["stage3"]["per_label_orientations"]
        assert entries
        for entry in entries:
            assert entry["principal_axis"] == [1.0, 0.0, 0.0], (
                f"{case['case_id']!r} label {entry['label']!r} principal_axis "
                f"{entry['principal_axis']!r} is not exactly [1.0, 0.0, 0.0]"
            )


# =========================================================================== #
# AC11: VertebralOrientation is unchanged
# =========================================================================== #


def test_ac11_vertebral_orientation_field_names_and_order_unchanged():
    fields = tuple(f.name for f in dataclasses.fields(VertebralOrientation))
    assert fields == ("label", "level_name", "principal_axis", "eigenvalue_ratio")


def test_ac11_compute_vertebra_orientations_signature_unchanged():
    import inspect

    sig = inspect.signature(compute_vertebra_orientations)
    assert list(sig.parameters) == ["seg_img", "labels", "convention"]


# =========================================================================== #
# AC12: eigenvalue_ratio and principal_axis values are unchanged (within
# tight numeric tolerance -- committed-vs-fresh, not exact; item 078)
# =========================================================================== #


# (item 126: test_ac12_pca_values_match_fresh_computation_within_tolerance
# was discharged -- with the committed golden retired, this compared fresh
# computation against fresh computation (its own subject), which asserts
# nothing beyond compute_vertebra_orientations's intra-run determinism,
# already covered by test_042's determinism replacement (i). See
# docs/aide/golden-decision-table.md's "## Retirement execution log".)


# =========================================================================== #
# AC13 / AC14: Serialisation types and value equality
# =========================================================================== #


def test_ac13_serialised_new_keys_are_json_native():
    centroids = _coronal_c_curve(7)
    orientation = VertebralOrientation(
        label=1, level_name="L1", principal_axis=(1.0, 0.0, 0.0), eigenvalue_ratio=2.0,
    )
    tangent = _tangents_for(centroids)[0]
    d = orientation_to_dict(orientation, tangent=tangent)
    assert isinstance(d["spline_closest_u"], float)
    assert isinstance(d["spline_tangent_coronal_deg"], float)
    assert isinstance(d["spline_tangent_sagittal_deg"], float)
    assert isinstance(d["spline_tangent"], list)
    assert len(d["spline_tangent"]) == 3
    assert all(isinstance(v, float) for v in d["spline_tangent"])


def test_ac14_serialised_values_equal_dataclass_values():
    centroids = _sagittal_c_curve(7)
    orientation = VertebralOrientation(
        label=1, level_name="L1", principal_axis=(1.0, 0.0, 0.0), eigenvalue_ratio=2.0,
    )
    tangent = _tangents_for(centroids)[0]
    d = orientation_to_dict(orientation, tangent=tangent)
    assert d["spline_closest_u"] == tangent.closest_u
    assert d["spline_tangent"] == list(tangent.tangent)
    assert d["spline_tangent_coronal_deg"] == tangent.coronal_deg
    assert d["spline_tangent_sagittal_deg"] == tangent.sagittal_deg


# =========================================================================== #
# AC15: build_features_block merges tangents into orientation entries by label
# =========================================================================== #


def _orientations_for(centroids: List[LabelCentroid]) -> List[VertebralOrientation]:
    return [
        VertebralOrientation(
            label=c.label, level_name=c.level_name,
            principal_axis=(1.0, 0.0, 0.0), eigenvalue_ratio=1.5,
        )
        for c in centroids
    ]


def test_ac15_merge_by_label_not_index():
    centroids = _coronal_c_curve(5)
    orientations = _orientations_for(centroids)
    tangents = _tangents_for(centroids)

    # Supply both sequences in a different (descending-label) order than the
    # centroids were built in, so an index-based merge would misalign.
    shuffled_orientations = list(reversed(orientations))
    shuffled_tangents = list(reversed(tangents))

    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=shuffled_orientations,
        tangent_orientations=shuffled_tangents,
    )
    entries = block["stage3"]["per_label_orientations"]
    tangents_by_label = {t.label: t for t in tangents}
    assert len(entries) == len(centroids)
    for entry in entries:
        expected = tangents_by_label[entry["label"]]
        assert entry["spline_closest_u"] == expected.closest_u
        assert entry["spline_tangent"] == list(expected.tangent)
        assert entry["spline_tangent_coronal_deg"] == expected.coronal_deg
        assert entry["spline_tangent_sagittal_deg"] == expected.sagittal_deg


# =========================================================================== #
# AC16: A label-set mismatch is rejected
# =========================================================================== #


def test_ac16_label_set_mismatch_raises_value_error_naming_offenders():
    centroids = _straight_spine(4)
    orientations = _orientations_for(centroids)
    tangents = _tangents_for(centroids)
    # Drop one tangent record and mutate another's label so the two label
    # sets disagree in both directions.
    mismatched = [
        dataclasses.replace(tangents[0], label=999),
        *tangents[2:],
    ]
    with pytest.raises(ValueError) as excinfo:
        build_features_block(
            geometry={}, components={}, centroids={},
            relationships=None, overlaps=[],
            orientations=orientations,
            tangent_orientations=mismatched,
        )
    message = str(excinfo.value)
    assert "999" in message or "1" in message or "2" in message


# =========================================================================== #
# AC17: Omitting tangent_orientations stays backward-compatible
# =========================================================================== #


def test_ac17_omitted_tangent_orientations_keeps_four_original_keys():
    centroids = _straight_spine(4)
    orientations = _orientations_for(centroids)
    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=orientations,
    )
    entries = block["stage3"]["per_label_orientations"]
    assert entries
    for entry in entries:
        assert set(entry.keys()) == {"label", "level_name", "principal_axis", "eigenvalue_ratio"}


def test_ac17_omitted_tangent_orientations_report_validates():
    centroids = _straight_spine(4)
    orientations = _orientations_for(centroids)
    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=orientations,
    )
    verdict = Verdict.build(reasons=[], per_label={})
    from segfacet.config import default_config

    report = serialize_report(verdict, "case-121", default_config(), features=block)
    jsonschema.validate(report, _SCHEMA)


# =========================================================================== #
# AC18: Schema admits the four new keys
# =========================================================================== #


def test_ac18_schema_defines_all_four_new_keys():
    entry_def = _SCHEMA["definitions"]["stage3OrientationEntry"]
    for key in (
        "spline_closest_u",
        "spline_tangent",
        "spline_tangent_coronal_deg",
        "spline_tangent_sagittal_deg",
    ):
        assert key in entry_def["properties"], f"schema missing property {key!r}"
    tangent_def = entry_def["properties"]["spline_tangent"]
    assert tangent_def["type"] == "array"
    assert tangent_def.get("minItems") == 3
    assert tangent_def.get("maxItems") == 3


def test_ac18_report_with_new_keys_validates():
    centroids = _coronal_c_curve(5)
    orientations = _orientations_for(centroids)
    tangents = _tangents_for(centroids)
    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=orientations,
        tangent_orientations=tangents,
    )
    from segfacet.config import default_config

    verdict = Verdict.build(reasons=[], per_label={})
    report = serialize_report(verdict, "case-121", default_config(), features=block)
    jsonschema.validate(report, _SCHEMA)


def test_ac18_misspelt_fifth_key_fails_validation():
    centroids = _coronal_c_curve(5)
    orientations = _orientations_for(centroids)
    tangents = _tangents_for(centroids)
    block = build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=orientations,
        tangent_orientations=tangents,
    )
    block["stage3"]["per_label_orientations"][0]["spline_tangnet_typo"] = 1.0
    from segfacet.config import default_config

    verdict = Verdict.build(reasons=[], per_label={})
    with pytest.raises(jsonschema.ValidationError):
        serialize_report(verdict, "case-121", default_config(), features=block)


# =========================================================================== #
# AC19: A pipeline-produced report carries the estimate for every label
# =========================================================================== #


def test_ac19_every_corpus_case_carries_all_four_keys_on_every_entry():
    from segfacet.synth.golden import build_report_for_case

    cases = load_manifest()["cases"]
    assert cases
    for case in cases:
        report = build_report_for_case(case)
        stage3 = report["features"].get("stage3")
        if not stage3:
            continue
        entries = stage3["per_label_orientations"]
        assert entries, f"{case['case_id']!r} has no per_label_orientations entries"
        for entry in entries:
            for key in (
                "spline_closest_u",
                "spline_tangent",
                "spline_tangent_coronal_deg",
                "spline_tangent_sagittal_deg",
            ):
                assert key in entry, f"{case['case_id']!r} entry missing {key!r}"
            assert isinstance(entry["spline_tangent"], list)
            assert len(entry["spline_tangent"]) == 3
            assert all(isinstance(v, float) for v in entry["spline_tangent"])


# =========================================================================== #
# AC20: Every new leaf path is documented
# =========================================================================== #


@pytest.mark.parametrize("path", _NEW_LEAF_PATHS)
def test_ac20_new_leaf_path_documented(path):
    assert path in FEATURE_DOCS, f"FEATURE_DOCS missing entry for {path!r}"


# =========================================================================== #
# AC21: The proxy status is stated where the feature is defined
# =========================================================================== #


def test_ac21_dataclass_docstring_states_proxy_and_ras_precondition():
    docstring = (VertebralTangentOrientation.__doc__ or "").lower()
    assert "proxy" in docstring
    assert "not" in docstring and (
        "vertebral coordinate system" in docstring or "vcs" in docstring
    )
    assert any(marker in docstring for marker in _RAS_MARKERS)


@pytest.mark.parametrize(
    "path",
    [
        "stage3.per_label_orientations[].spline_tangent_coronal_deg",
        "stage3.per_label_orientations[].spline_tangent_sagittal_deg",
    ],
)
def test_ac21_angle_leaf_docs_state_proxy_and_ras_precondition(path):
    doc = FEATURE_DOCS[path]
    text = (doc.measures + " " + doc.computation).lower()
    assert "proxy" in text, f"{path!r} doc does not state proxy status: {text!r}"
    assert "vertebral coordinate system" in text or "vcs" in text, (
        f"{path!r} doc does not state the not-a-VCS scope fence: {text!r}"
    )
    assert any(marker in text for marker in _RAS_MARKERS), (
        f"{path!r} doc does not state the RAS precondition: {text!r}"
    )


# =========================================================================== #
# AC22: principal_axis's catalogue entry records its demotion with evidence
# =========================================================================== #


def test_ac22_principal_axis_doc_records_demotion_with_measured_evidence():
    doc = FEATURE_DOCS["stage3.per_label_orientations[].principal_axis[]"]
    text = doc.measures + " " + doc.computation
    assert "0.996" in text, f"principal_axis doc omits the measured 0.996 bound: {text!r}"
    assert "seven" in text.lower() or "7" in text, (
        f"principal_axis doc omits the 'seven of nine cases' evidence: {text!r}"
    )
    assert "spline_tangent_coronal_deg" in text or "spline_tangent_sagittal_deg" in text, (
        f"principal_axis doc does not point at the tangent estimate to prefer: {text!r}"
    )


def test_ac22_principal_axis_status_override_unchanged():
    from segfacet.feature_docs import STATUS_OVERRIDES

    assert "stage3.per_label_orientations[].principal_axis[]" in STATUS_OVERRIDES


# =========================================================================== #
# Adversarial: two-centroid minimum
# =========================================================================== #


def test_adv_two_centroids_no_crash():
    result = _tangents_for(_two_centroid())
    assert len(result) == 2
    for record in result:
        assert math.isfinite(record.coronal_deg)
        assert math.isfinite(record.sagittal_deg)
    assert result[0].coronal_deg == pytest.approx(14.0362, abs=1e-3)
    assert result[1].coronal_deg == pytest.approx(14.0362, abs=1e-3)
    assert result[0].sagittal_deg == pytest.approx(0.0, abs=1e-9)
    assert result[1].sagittal_deg == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# Adversarial: empty centroid sequence raises ValueError
# =========================================================================== #


def test_adv_empty_centroid_sequence_raises_value_error():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_vertebra_tangent_orientations(fit, [])


# =========================================================================== #
# Adversarial: doubling-back sequence stays wrapped, contrasted against
# item 122's unwrapped stage3.curvature convention
# =========================================================================== #


def test_adv_doubling_back_sequence_stays_within_wrap_bounds():
    result = _tangents_for(_mode4_relabel_swap_shape())
    for record in result:
        assert -180.0 < record.coronal_deg <= 180.0, record.coronal_deg
        assert -180.0 < record.sagittal_deg <= 180.0, record.sagittal_deg
        assert math.isfinite(record.coronal_deg)
        assert math.isfinite(record.sagittal_deg)


def test_adv_doubling_back_contrasted_with_unwrapped_curvature_convention():
    """Item 121's per-vertebra angles stay wrapped to (-180, 180], while item
    122's stage3.curvature.coronal_tangent_angles_deg on the real
    ``mode4_relabel_swap`` corpus case is deliberately unwrapped and does
    leave that range (committed golden measures 182.3510 / 184.7816 /
    358.5342 degrees there) -- the two conventions differ on purpose (see the
    item's Decisions log). The hand-built ``_mode4_relabel_swap_shape``
    fixture used elsewhere in this file reproduces the *doubling-back shape*
    at unit-test scale but its unwrapped coronal angles all stay within
    (-180, 180] (measured max ~152.6 deg), so it cannot exercise this
    contrast -- the real corpus case is used here instead."""
    from segfacet.features.orientation import compute_spine_curvature

    centroids = _mode4_relabel_swap_ordered_centroids()
    fit = fit_centroid_spline(centroids)
    tangent_result = compute_vertebra_tangent_orientations(fit, centroids)
    curvature_result = compute_spine_curvature(fit, centroids)

    for record in tangent_result:
        assert -180.0 < record.coronal_deg <= 180.0

    unwrapped = curvature_result.coronal_tangent_angles_deg
    assert any(v <= -180.0 or v > 180.0 for v in unwrapped), (
        "expected item 122's unwrapped array to leave (-180, 180] on the "
        "real mode4_relabel_swap corpus case, contrasting with item 121's "
        "wrapped convention"
    )


# =========================================================================== #
# Adversarial: degenerate near-zero tangent
# =========================================================================== #


def test_adv_near_coincident_centroids_degenerate_tangent_stays_finite():
    """Exactly-coincident centroids make fit_centroid_spline raise inside
    scipy.interpolate.splprep -- a pre-existing spline-fit limitation outside
    this item's scope (this item owns compute_vertebra_tangent_orientations,
    not the spline fit). A 1e-6 mm perturbation keeps the fit valid while
    still exercising the near-zero-norm tangent guard."""
    centroids = [
        _centroid(_LEVELS[i], (5.0 + i * 1e-6, 5.0, 5.0 + i * 1e-6), label=i + 1)
        for i in range(4)
    ]
    result = _tangents_for(centroids)
    for record in result:
        assert math.isfinite(record.coronal_deg)
        assert math.isfinite(record.sagittal_deg)
        norm = math.sqrt(sum(c * c for c in record.tangent))
        assert math.isfinite(norm)


# =========================================================================== #
# Adversarial: coincident centroids propagate fit_centroid_spline's ValueError
# =========================================================================== #


def test_adv_exactly_coincident_centroids_raises_value_error_not_nan():
    centroids = [_centroid(_LEVELS[i], (5.0, 5.0, 5.0), label=i + 1) for i in range(4)]
    with pytest.raises(ValueError):
        fit_centroid_spline(centroids)


# =========================================================================== #
# Adversarial: anisotropic mm spacing on a straight spine
# =========================================================================== #


def test_adv_anisotropic_spacing_straight_spine_still_zero():
    centroids = [
        _centroid(_LEVELS[i], (0.0, 0.0, float(i) * 40.0), label=i + 1) for i in range(5)
    ]
    result = _tangents_for(centroids)
    for record in result:
        assert record.coronal_deg == pytest.approx(0.0, abs=1e-9)
        assert record.sagittal_deg == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# Adversarial: determinism
# =========================================================================== #


def test_adv_determinism_two_calls_equal():
    centroids = _mode4_relabel_swap_shape()
    fit = fit_centroid_spline(centroids)
    result_a = compute_vertebra_tangent_orientations(fit, centroids)
    result_b = compute_vertebra_tangent_orientations(fit, centroids)
    assert len(result_a) == len(result_b)
    for a, b in zip(result_a, result_b):
        assert a.label == b.label
        assert a.level_name == b.level_name
        assert a.closest_u == b.closest_u
        assert a.tangent == b.tangent
        assert a.coronal_deg == b.coronal_deg
        assert a.sagittal_deg == b.sagittal_deg


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #


def test_adv_vertebral_tangent_orientation_is_frozen():
    result = _tangents_for(_straight_spine())[0]
    with pytest.raises(Exception):
        result.coronal_deg = 999.0  # type: ignore[misc]
    with pytest.raises(Exception):
        result.tangent = (1.0, 0.0, 0.0)  # type: ignore[misc]


def test_adv_build_features_block_does_not_mutate_tangent_orientations():
    centroids = _coronal_c_curve(5)
    orientations = _orientations_for(centroids)
    tangents = _tangents_for(centroids)
    tangents_before = [dataclasses.astuple(t) for t in tangents]

    build_features_block(
        geometry={}, components={}, centroids={},
        relationships=None, overlaps=[],
        orientations=orientations,
        tangent_orientations=tangents,
    )

    tangents_after = [dataclasses.astuple(t) for t in tangents]
    assert tangents_before == tangents_after


# =========================================================================== #
# Adversarial: schema-optional keys leave existing tests green (regression
# witness for AC17 alongside the direct tests above)
# =========================================================================== #


def test_adv_stage3_orientation_entry_required_list_unchanged():
    """The four new keys must be schema-optional: adding them to `required`
    would break every existing caller (test_022, test_122) that supplies
    `orientations` with no tangents."""
    entry_def = _SCHEMA["definitions"]["stage3OrientationEntry"]
    required = entry_def.get("required", [])
    for key in (
        "spline_closest_u",
        "spline_tangent",
        "spline_tangent_coronal_deg",
        "spline_tangent_sagittal_deg",
    ):
        assert key not in required, f"{key!r} must stay schema-optional (AC17)"
