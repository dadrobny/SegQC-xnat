"""Tests for item 122 — signed, plane-stated global curvature descriptors.

The retired ``total_curvature_deg`` was ``max - min`` of the *unsigned* angle
between each tangent and the cranio-caudal axis, which halves a C-curve and
cancels a balanced S-curve. This item replaces it with five keys carrying a
sign convention and an explicit anatomical plane:
``coronal_tangent_angles_deg``, ``sagittal_tangent_angles_deg``,
``coronal_curvature_deg``, ``sagittal_curvature_deg``, ``curvature_plane``,
with ``total_curvature_deg`` redefined as
``max(coronal_curvature_deg, sagittal_curvature_deg)``.

Covers AC1-AC21 (AC22 -- the golden-regeneration-is-narrow diff -- is verified
by the item's Validation section's ``git diff`` command, not by pytest; no
test here attempts it).

Adversarial scenarios: two-centroid minimum, fewer-than-two ValueError,
coincident centroids, degenerate near-zero tangent, a doubling-back sequence
exercising ``np.unwrap`` (the ``mode4_relabel_swap`` shape), anisotropic
spacing, a cranial-first (caudally-advancing) sequence exercising traversal
direction normalisation, determinism, immutability, invariance of the
retained unsigned arrays, and a schema round-trip proving ``required`` is
load-bearing.
"""

from __future__ import annotations

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

from segfacet.catalogue import build_catalogue  # noqa: E402
from segfacet.feature_docs import FEATURE_DOCS  # noqa: E402
from segfacet.feature_report import build_features_block, curvature_to_dict  # noqa: E402
from segfacet.features.centroids import LabelCentroid  # noqa: E402
from segfacet.features.spline import fit_centroid_spline  # noqa: E402
from segfacet.features.orientation import (  # noqa: E402
    SpineCurvature,
    compute_spine_curvature,
)
from segfacet.report import _SCHEMA, serialize_report  # noqa: E402
from segfacet.synth.corpus import load_manifest  # noqa: E402
from segfacet.synth.golden import (  # noqa: E402
    build_report_for_case,
    write_goldens,
)
from segfacet.verdict import Verdict  # noqa: E402

import jsonschema  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CATALOGUE_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_CATALOGUE_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

_NEW_LEAF_PATHS = (
    "stage3.curvature.coronal_tangent_angles_deg[]",
    "stage3.curvature.sagittal_tangent_angles_deg[]",
    "stage3.curvature.coronal_curvature_deg",
    "stage3.curvature.sagittal_curvature_deg",
    "stage3.curvature.curvature_plane",
)

# =========================================================================== #
# Fixture builders (values measured in the item spec's Testing Strategy)
# =========================================================================== #


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _straight_spine(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """5 centroids at (0, 0, 10*i) -- all three sweeps 0.0."""
    return [
        _centroid(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _coronal_c_curve(n: int = 7) -> List[LabelCentroid]:
    """7 centroids: (30*sin(pi*i/6), 0, 15*i) -- coronal 116.5608, sagittal 0.0."""
    return [
        _centroid(
            _LEVELS[i % len(_LEVELS)],
            (30.0 * math.sin(math.pi * i / 6.0), 0.0, 15.0 * i),
            label=i + 1,
        )
        for i in range(n)
    ]


def _sagittal_c_curve(n: int = 7) -> List[LabelCentroid]:
    """7 centroids: (0, 30*sin(pi*i/6), 15*i) -- coronal 0.0, sagittal 116.5608."""
    return [
        _centroid(
            _LEVELS[i % len(_LEVELS)],
            (0.0, 30.0 * math.sin(math.pi * i / 6.0), 15.0 * i),
            label=i + 1,
        )
        for i in range(n)
    ]


def _balanced_s_curve() -> List[LabelCentroid]:
    """4 centroids at f=(2i+1)/8: (20*sin(2*pi*f), 0, 170*f).

    Retired total 0.0900 (below item 019 AC5's 1.0 straight bound); new
    coronal_curvature_deg 53.7979; new sagittal 0.0.
    """
    centroids = []
    for i in range(4):
        f = (2 * i + 1) / 8.0
        x = 20.0 * math.sin(2.0 * math.pi * f)
        z = 170.0 * f
        centroids.append(_centroid(_LEVELS[i], (x, 0.0, z), label=i + 1))
    return centroids


def _mode4_relabel_swap_shape() -> List[LabelCentroid]:
    """A doubling-back coronal sequence exercising the ``np.unwrap`` branch.

    The real ``mode4_relabel_swap`` corpus case swaps two adjacent labels'
    spatial (S) order, producing a local backward loop in the cranio-caudal
    direction combined with a coronal (R) excursion; the resulting coronal
    tangent-angle sequence sweeps past the +/-180 degree atan2 wrap boundary
    (measured 355.2389 deg unwrapped, confirmed by the ``mode4_relabel_swap``
    corpus-golden snapshot, retired by item 126). This fixture reproduces
    that shape at unit-test scale: an R excursion (out, past the pole, and
    back) combined with a local S-order swap between two adjacent centroids
    (indices 2 and 3 below), which is enough to push the unwrapped coronal
    sweep well past 180 degrees -- proving unwrapping is applied rather than
    the sweep being clipped at the wrap boundary.
    """
    xs = [0.0, 40.0, 65.0, 40.0, -40.0, -65.0]
    zs = [0.0, 15.0, 45.0, 30.0, 60.0, 75.0]  # indices 2 and 3 swapped in S
    return [
        _centroid(_LEVELS[i], (xs[i], 0.0, zs[i]), label=i + 1) for i in range(len(xs))
    ]


def _cranial_first_straight(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """A caudally-advancing (cranial-first) straight sequence: the same physical
    curve as ``_straight_spine`` but supplied starting at the head, so
    ``centroid_mm[-1][2] - centroid_mm[0][2] < 0`` -- the normalisation
    trigger."""
    return list(reversed(_straight_spine(n, spacing_mm)))


def _cranial_first_c_curve(n: int = 7) -> List[LabelCentroid]:
    """The same physical coronal C-curve as ``_coronal_c_curve``, supplied
    cranial-first (caudally-advancing) -- exercises traversal-direction
    normalisation on a curved, not just straight, fixture."""
    return list(reversed(_coronal_c_curve(n)))


def _retired_formula(result: SpineCurvature) -> float:
    """Recompute the retired max-min-of-unsigned-angle formula from the still-present array."""
    angles = np.asarray(result.tangent_angles_deg, dtype=np.float64)
    return float(np.max(angles) - np.min(angles))


def _curvature_for(centroids: List[LabelCentroid]) -> SpineCurvature:
    fit = fit_centroid_spline(centroids)
    return compute_spine_curvature(fit, centroids)


# =========================================================================== #
# AC1: Signed coronal angle array
# =========================================================================== #


def test_ac1_coronal_tangent_angles_length_matches_centroids():
    centroids = _coronal_c_curve(7)
    result = _curvature_for(centroids)
    assert isinstance(result.coronal_tangent_angles_deg, tuple)
    assert len(result.coronal_tangent_angles_deg) == len(centroids)


def test_ac1_coronal_c_curve_first_positive_last_negative():
    """On a coronal C-curve, first entry strictly positive, last strictly negative."""
    result = _curvature_for(_coronal_c_curve(7))
    assert result.coronal_tangent_angles_deg[0] > 0.0
    assert result.coronal_tangent_angles_deg[-1] < 0.0
    assert result.coronal_tangent_angles_deg[0] == pytest.approx(58.2804, abs=1e-3)
    assert result.coronal_tangent_angles_deg[-1] == pytest.approx(-58.2804, abs=1e-3)


# =========================================================================== #
# AC2: Signed sagittal angle array
# =========================================================================== #


def test_ac2_sagittal_tangent_angles_length_matches_centroids():
    centroids = _sagittal_c_curve(7)
    result = _curvature_for(centroids)
    assert isinstance(result.sagittal_tangent_angles_deg, tuple)
    assert len(result.sagittal_tangent_angles_deg) == len(centroids)


def test_ac2_sagittal_c_curve_first_positive_last_negative():
    """On a sagittal C-curve, first entry strictly positive, last strictly negative."""
    result = _curvature_for(_sagittal_c_curve(7))
    assert result.sagittal_tangent_angles_deg[0] > 0.0
    assert result.sagittal_tangent_angles_deg[-1] < 0.0


# =========================================================================== #
# AC3 / AC4: per-plane sweep equals the array's range
# =========================================================================== #


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve, _balanced_s_curve],
)
def test_ac3_coronal_curvature_equals_array_range(centroids_fn):
    result = _curvature_for(centroids_fn())
    angles = result.coronal_tangent_angles_deg
    expected = max(angles) - min(angles)
    assert result.coronal_curvature_deg == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve, _balanced_s_curve],
)
def test_ac4_sagittal_curvature_equals_array_range(centroids_fn):
    result = _curvature_for(centroids_fn())
    angles = result.sagittal_tangent_angles_deg
    expected = max(angles) - min(angles)
    assert result.sagittal_curvature_deg == pytest.approx(expected, abs=1e-9)


# =========================================================================== #
# AC5: A C-curve's coronal_curvature_deg equals its tangent sweep
# =========================================================================== #


def test_ac5_coronal_c_curve_equals_inter_tangent_sum():
    result = _curvature_for(_coronal_c_curve(7))
    expected = sum(result.inter_tangent_angles_deg)
    assert result.coronal_curvature_deg == pytest.approx(expected, abs=1e-6)
    assert result.coronal_curvature_deg == pytest.approx(116.5608, abs=1e-3)


def test_ac5_retired_formula_is_half_on_same_fixture():
    """The retired descriptor reports 58.2804 -- half of the new 116.5608."""
    result = _curvature_for(_coronal_c_curve(7))
    retired = _retired_formula(result)
    assert retired == pytest.approx(58.2804, abs=1e-3)
    assert result.coronal_curvature_deg == pytest.approx(2.0 * retired, abs=1e-2)


# =========================================================================== #
# AC6: A coronal-plane curve reports zero sagittal curvature
# =========================================================================== #


def test_ac6_coronal_curve_zero_sagittal():
    result = _curvature_for(_coronal_c_curve(7))
    assert result.sagittal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.coronal_curvature_deg > 20.0


# =========================================================================== #
# AC7: A sagittal-plane curve reports zero coronal curvature
# =========================================================================== #


def test_ac7_sagittal_curve_zero_coronal():
    result = _curvature_for(_sagittal_c_curve(7))
    assert result.coronal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.sagittal_curvature_deg > 20.0
    assert result.sagittal_curvature_deg == pytest.approx(116.5608, abs=1e-3)


# =========================================================================== #
# AC8: A symmetric S-curve is separated from a straight spine
# =========================================================================== #


def test_ac8_balanced_s_curve_total_at_least_20():
    result = _curvature_for(_balanced_s_curve())
    assert result.total_curvature_deg >= 20.0
    assert result.total_curvature_deg == pytest.approx(53.7979, abs=1e-3)


def test_ac8_straight_spine_reports_zero_total():
    result = _curvature_for(_straight_spine())
    assert result.total_curvature_deg == 0.0


# =========================================================================== #
# AC9: A straight spine reports zero for all three sweeps
# =========================================================================== #


def test_ac9_straight_spine_all_sweeps_zero():
    result = _curvature_for(_straight_spine())
    assert result.coronal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.sagittal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.total_curvature_deg == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# AC10: The retired formula is pinned as a regression witness (THE most
# important test in this file -- see the module docstring).
# =========================================================================== #


def test_ac10_balanced_s_curve_pins_the_cancellation_defect():
    """The regression witness: the retired max-min-of-unsigned formula reads
    below item 019 AC5's 1.0 deg straight-spine bound on a genuine S-curve,
    while the new total_curvature_deg correctly reports it as strongly
    curved. Both assertions live in one test so cancellation cannot silently
    return.
    """
    result = _curvature_for(_balanced_s_curve())
    retired = _retired_formula(result)
    assert retired < 1.0, (
        f"retired formula = {retired:.4f} >= 1.0 -- fixture no longer "
        f"demonstrates the cancellation defect"
    )
    assert retired == pytest.approx(0.0900, abs=1e-3)
    assert result.total_curvature_deg > 20.0, (
        f"new total_curvature_deg = {result.total_curvature_deg:.4f} <= 20.0 "
        f"-- the fix regressed on the same fixture that pins the defect"
    )


# =========================================================================== #
# AC11: total_curvature_deg is the larger of the two plane sweeps
# =========================================================================== #


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve, _balanced_s_curve, _mode4_relabel_swap_shape],
)
def test_ac11_total_is_max_of_plane_sweeps(centroids_fn):
    result = _curvature_for(centroids_fn())
    expected = max(result.coronal_curvature_deg, result.sagittal_curvature_deg)
    assert result.total_curvature_deg == pytest.approx(expected, abs=1e-9)


# =========================================================================== #
# AC12: curvature_plane names the plane the total came from
# =========================================================================== #


def test_ac12_coronal_c_curve_plane_is_coronal():
    result = _curvature_for(_coronal_c_curve(7))
    assert result.curvature_plane == "coronal"


def test_ac12_sagittal_c_curve_plane_is_sagittal():
    result = _curvature_for(_sagittal_c_curve(7))
    assert result.curvature_plane == "sagittal"


def test_ac12_straight_spine_tie_resolves_to_coronal():
    """An exact 0.0/0.0 tie resolves deterministically to 'coronal'."""
    result = _curvature_for(_straight_spine())
    assert result.coronal_curvature_deg == result.sagittal_curvature_deg == 0.0
    assert result.curvature_plane == "coronal"


# =========================================================================== #
# AC13: Invariance to traversal direction (reversal)
# =========================================================================== #


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _sagittal_c_curve, _balanced_s_curve],
)
def test_ac13_reversed_sequence_leaves_sweeps_unchanged(centroids_fn):
    centroids = centroids_fn()
    forward = _curvature_for(centroids)
    reversed_result = _curvature_for(list(reversed(centroids)))
    assert reversed_result.coronal_curvature_deg == pytest.approx(
        forward.coronal_curvature_deg, abs=1e-9
    )
    assert reversed_result.sagittal_curvature_deg == pytest.approx(
        forward.sagittal_curvature_deg, abs=1e-9
    )
    assert reversed_result.total_curvature_deg == pytest.approx(
        forward.total_curvature_deg, abs=1e-9
    )


# =========================================================================== #
# AC14 / AC15: Serialisation types and value equality
# =========================================================================== #


def test_ac14_serialised_types_are_json_native():
    result = _curvature_for(_balanced_s_curve())
    d = curvature_to_dict(result)
    assert isinstance(d["coronal_tangent_angles_deg"], list)
    assert all(isinstance(v, float) for v in d["coronal_tangent_angles_deg"])
    assert isinstance(d["sagittal_tangent_angles_deg"], list)
    assert all(isinstance(v, float) for v in d["sagittal_tangent_angles_deg"])
    assert isinstance(d["coronal_curvature_deg"], float)
    assert isinstance(d["sagittal_curvature_deg"], float)
    assert isinstance(d["curvature_plane"], str)


def test_ac15_serialised_values_equal_dataclass_values():
    result = _curvature_for(_balanced_s_curve())
    d = curvature_to_dict(result)
    assert d["coronal_tangent_angles_deg"] == list(result.coronal_tangent_angles_deg)
    assert d["sagittal_tangent_angles_deg"] == list(result.sagittal_tangent_angles_deg)
    assert d["coronal_curvature_deg"] == result.coronal_curvature_deg
    assert d["sagittal_curvature_deg"] == result.sagittal_curvature_deg
    assert d["curvature_plane"] == result.curvature_plane
    assert d["total_curvature_deg"] == result.total_curvature_deg


# =========================================================================== #
# AC16: Schema admits and requires the new keys
# =========================================================================== #


def _config():
    from segfacet.config import default_config

    return default_config()


def _empty_verdict() -> Verdict:
    return Verdict.build(reasons=[], per_label={})


def _full_stage3_block(centroids: List[LabelCentroid]):
    from segfacet.features.consistency import (
        compute_monotonic_consistency,
        compute_spacing_consistency,
    )
    from segfacet.features.orientation import VertebralOrientation
    from segfacet.features.spline_offset import compute_spline_offsets

    fit = fit_centroid_spline(centroids)
    offsets = compute_spline_offsets(centroids, fit)
    curvature = compute_spine_curvature(fit, centroids)
    spacing = compute_spacing_consistency(centroids)
    monotonic = compute_monotonic_consistency(centroids, fit)
    orientations = [
        VertebralOrientation(
            label=c.label,
            level_name=c.level_name,
            principal_axis=(0.0, 0.0, 1.0),
            eigenvalue_ratio=2.0,
        )
        for c in centroids
    ]
    return build_features_block(
        geometry={},
        components={},
        centroids={},
        relationships=None,
        overlaps=[],
        spline_offsets=offsets,
        orientations=orientations,
        curvature=curvature,
        spacing_consistency=spacing,
        monotonic_consistency=monotonic,
    )


def test_ac16_schema_defines_all_five_new_keys():
    curvature_def = _SCHEMA["definitions"]["stage3Curvature"]
    for key in (
        "coronal_tangent_angles_deg",
        "sagittal_tangent_angles_deg",
        "coronal_curvature_deg",
        "sagittal_curvature_deg",
        "curvature_plane",
    ):
        assert key in curvature_def["properties"], f"schema missing property {key!r}"
        assert key in curvature_def["required"], f"schema does not require {key!r}"


def test_ac16_full_report_with_new_keys_validates():
    centroids = _balanced_s_curve()
    block = _full_stage3_block(centroids)
    report = serialize_report(_empty_verdict(), "case-122", _config(), features=block)
    jsonschema.validate(report, _SCHEMA)
    curv = report["features"]["stage3"]["curvature"]
    for key in _NEW_LEAF_PATHS:
        bare = key.rsplit(".", 1)[-1].rstrip("[]")
        assert bare in curv


def test_ac16_missing_required_key_fails_validation():
    """Proves 'required' is load-bearing: dropping one new key fails validation."""
    centroids = _balanced_s_curve()
    block = _full_stage3_block(centroids)
    del block["stage3"]["curvature"]["curvature_plane"]
    with pytest.raises(jsonschema.ValidationError):
        serialize_report(_empty_verdict(), "case-122", _config(), features=block)


# =========================================================================== #
# AC17: Plane and sign convention documented at the record level
# =========================================================================== #


_RAS_MARKERS = ("ras", "r, a, s", "load_volume", "right, anterior, superior")


@pytest.mark.parametrize(
    "path,plane",
    [
        ("stage3.curvature.coronal_tangent_angles_deg[]", "coronal"),
        ("stage3.curvature.sagittal_tangent_angles_deg[]", "sagittal"),
        ("stage3.curvature.coronal_curvature_deg", "coronal"),
        ("stage3.curvature.sagittal_curvature_deg", "sagittal"),
    ],
)
def test_ac17_new_leaf_docs_name_their_plane_and_ras_precondition(path, plane):
    assert path in FEATURE_DOCS, f"FEATURE_DOCS missing entry for {path!r}"
    doc = FEATURE_DOCS[path]
    text = (doc.measures + " " + doc.computation).lower()
    assert plane in text, f"{path!r} doc does not name its plane {plane!r}: {text!r}"
    assert any(marker in text for marker in _RAS_MARKERS), (
        f"{path!r} doc does not state the RAS precondition: {text!r}"
    )


def test_ac17_curvature_plane_key_documented():
    assert "stage3.curvature.curvature_plane" in FEATURE_DOCS


# =========================================================================== #
# AC18: total_curvature_deg documentation no longer states the retired formula
# =========================================================================== #


def test_ac18_total_curvature_doc_drops_retired_formula():
    doc = FEATURE_DOCS["stage3.curvature.total_curvature_deg"]
    combined = doc.measures + " " + doc.computation
    assert "max(tangent_angles_deg)" not in combined
    assert "min(tangent_angles_deg)" not in combined
    assert "plane" in combined.lower()


def test_ac18_total_curvature_schema_description_drops_retired_formula():
    curvature_def = _SCHEMA["definitions"]["stage3Curvature"]
    description = curvature_def["properties"]["total_curvature_deg"]["description"]
    assert "max(tangent_angles_deg)" not in description
    assert "min(tangent_angles_deg)" not in description


def test_ac18_spine_curvature_docstring_drops_retired_formula():
    docstring = SpineCurvature.__doc__ or ""
    assert "max(tangent_angles_deg)" not in docstring
    assert "min(tangent_angles_deg)" not in docstring


# =========================================================================== #
# AC19: Generated feature catalogue is regenerated and drift-clean
# =========================================================================== #


def test_ac19_build_catalogue_strict_raises_nothing():
    build_catalogue(strict=True)


def test_ac19_generated_catalogue_json_contains_new_paths():
    text = _CATALOGUE_JSON.read_text(encoding="utf-8")
    assert text.strip(), "generated catalogue JSON is empty"
    for path in _NEW_LEAF_PATHS:
        assert path in text, f"{path!r} missing from committed generated catalogue JSON"


def test_ac19_generated_catalogue_md_contains_new_paths():
    text = _CATALOGUE_MD.read_text(encoding="utf-8")
    assert text.strip(), "generated catalogue markdown is empty"
    for path in _NEW_LEAF_PATHS:
        assert path in text, f"{path!r} missing from committed generated catalogue markdown"


# =========================================================================== #
# AC20: Every corpus golden regenerated and agrees with a fresh build
# =========================================================================== #


# (item 126: test_ac20_every_corpus_golden_matches_fresh_build was
# discharged -- its subject, the committed golden corpus, was retired. See
# docs/aide/golden-decision-table.md's "## Retirement execution log".)


def test_ac20_regeneration_is_byte_identical_across_two_runs(tmp_path):
    dest1 = tmp_path / "goldens1"
    dest2 = tmp_path / "goldens2"
    write_goldens(dest=dest1)
    write_goldens(dest=dest2)
    cases = load_manifest()["cases"]
    assert cases, "corpus manifest has no cases -- cannot verify determinism"
    for case in cases:
        case_id = case["case_id"]
        bytes1 = (dest1 / f"{case_id}.json").read_bytes()
        bytes2 = (dest2 / f"{case_id}.json").read_bytes()
        assert bytes1, f"regenerated golden for {case_id!r} is empty"
        assert bytes1 == bytes2, f"non-deterministic regeneration for case {case_id!r}"


def test_ac20_new_curvature_keys_present_in_every_committed_golden():
    """AC20 (item 126 replacement): re-pointed at fresh output; the
    committed golden this used to read was retired, see
    docs/aide/golden-decision-table.md's "## Retirement execution log"."""
    cases = load_manifest()["cases"]
    assert cases
    for case in cases:
        data = build_report_for_case(case)
        curv = data["features"]["stage3"]["curvature"]
        for key in (
            "coronal_tangent_angles_deg",
            "sagittal_tangent_angles_deg",
            "coronal_curvature_deg",
            "sagittal_curvature_deg",
            "curvature_plane",
        ):
            assert key in curv, f"{case['case_id']!r} fresh report missing {key!r}"


# =========================================================================== #
# AC21: The Stage-3 report golden is regenerated
# (item 126: test_ac21_stage3_report_golden_is_present_and_carries_new_keys
# was discharged -- its subject, item 022's committed Stage-3 report
# snapshot, was retired and replaced with the shared, feature-value-free
# report_format_contract.json fixture (item 126 replacement iv), which
# carries the same curvature key set -- already covered by this module's
# sibling test_ac20_new_curvature_keys_present_in_every_committed_golden
# above and by test_016/test_022's own key-set assertions (item 126 AC10).
# See docs/aide/golden-decision-table.md's "## Retirement execution log".)
# =========================================================================== #


# =========================================================================== #
# Adversarial: two-centroid minimum
# =========================================================================== #


def test_adv_two_centroids_no_crash():
    centroids = _straight_spine(2)
    result = _curvature_for(centroids)
    assert len(result.coronal_tangent_angles_deg) == 2
    assert len(result.sagittal_tangent_angles_deg) == 2
    assert math.isfinite(result.coronal_curvature_deg)
    assert math.isfinite(result.sagittal_curvature_deg)


def test_adv_fewer_than_two_centroids_raises_value_error():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_spine_curvature(fit, centroids[:1])


# =========================================================================== #
# Adversarial: coincident centroids (zero chord length)
# =========================================================================== #


def test_adv_near_coincident_1e6mm_perturbation_no_crash_finite():
    """Uses near-coincident centroids (a 1e-6 mm perturbation, well under any
    meaningful tolerance) so the spline fit succeeds and item 122's
    signed-angle logic is actually exercised on the degenerate
    near-zero-tangent case it is meant to handle. The exactly-coincident
    input (which makes ``fit_centroid_spline`` raise) is outside item 122's
    scope (item 122 owns ``compute_spine_curvature`` / ``SpineCurvature`` in
    ``orientation.py``, not the spline fit itself) and is instead exercised,
    through the pipeline's graceful degradation, by item 129
    (``tests/test_129_coincident_centroids_and_held_out_floor.py``, via
    ``extract_feature_record``).
    """
    centroids = [
        _centroid(_LEVELS[i], (5.0 + i * 1e-6, 5.0, 5.0 + i * 1e-6), label=i + 1)
        for i in range(4)
    ]
    result = _curvature_for(centroids)
    for v in result.coronal_tangent_angles_deg + result.sagittal_tangent_angles_deg:
        assert math.isfinite(v), f"non-finite signed angle for coincident centroids: {v}"
    assert math.isfinite(result.coronal_curvature_deg)
    assert math.isfinite(result.sagittal_curvature_deg)
    assert math.isfinite(result.total_curvature_deg)


# =========================================================================== #
# Adversarial: unwrap branch -- doubling-back sequence (mode4_relabel_swap shape)
# =========================================================================== #


def test_adv_doubling_back_sequence_unwraps_not_clipped_at_180():
    """The unwrapped coronal sweep is not clipped at 180 degrees; it reflects
    the honest accumulated turning. The fixture reproduces the doubling-back
    shape of the real ``mode4_relabel_swap`` corpus case (whose committed
    golden measures 355.2389 deg unwrapped) at unit-test scale; an atan2
    implementation that clipped at the wrap boundary instead of unwrapping
    could not exceed 180 degrees here."""
    result = _curvature_for(_mode4_relabel_swap_shape())
    assert math.isfinite(result.coronal_curvature_deg)
    assert result.coronal_curvature_deg >= 0.0
    assert result.coronal_curvature_deg > 180.0, (
        f"coronal_curvature_deg = {result.coronal_curvature_deg:.4f} appears "
        f"clipped at the atan2 wrap boundary rather than unwrapped"
    )


# =========================================================================== #
# Adversarial: anisotropic mm spacing on a straight spine
# =========================================================================== #


def test_adv_anisotropic_spacing_straight_spine_still_zero():
    centroids = [
        _centroid(_LEVELS[i], (0.0, 0.0, float(i) * 40.0), label=i + 1) for i in range(5)
    ]
    result = _curvature_for(centroids)
    assert result.coronal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.sagittal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.total_curvature_deg == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# Adversarial: traversal-direction normalisation (cranial-first sequence)
# =========================================================================== #


def test_adv_cranial_first_straight_spine_normalised_not_near_180():
    """Every committed fixture advances superiorly, which hid this trap: a
    cranial-first (caudally-advancing) sequence must still report near-zero
    sweeps, not angles clustered near +/-180 deg."""
    result = _curvature_for(_cranial_first_straight())
    for v in result.coronal_tangent_angles_deg:
        assert abs(v) < 90.0, f"unnormalised angle near +/-180 deg: {v}"
    assert result.coronal_curvature_deg == pytest.approx(0.0, abs=1e-9)
    assert result.sagittal_curvature_deg == pytest.approx(0.0, abs=1e-9)


def test_adv_cranial_first_c_curve_matches_caudal_first_sweep():
    """Direction normalisation makes the sweep itself invariant, even though
    the raw signed angles differ in which end starts positive."""
    caudal_first = _curvature_for(_coronal_c_curve(7))
    cranial_first = _curvature_for(_cranial_first_c_curve(7))
    assert cranial_first.coronal_curvature_deg == pytest.approx(
        caudal_first.coronal_curvature_deg, abs=1e-6
    )


# =========================================================================== #
# Adversarial: determinism
# =========================================================================== #


def test_adv_determinism_all_new_fields():
    centroids = _mode4_relabel_swap_shape()
    result_a = _curvature_for(centroids)
    result_b = _curvature_for(centroids)
    assert result_a.coronal_tangent_angles_deg == result_b.coronal_tangent_angles_deg
    assert result_a.sagittal_tangent_angles_deg == result_b.sagittal_tangent_angles_deg
    assert result_a.coronal_curvature_deg == result_b.coronal_curvature_deg
    assert result_a.sagittal_curvature_deg == result_b.sagittal_curvature_deg
    assert result_a.curvature_plane == result_b.curvature_plane
    assert result_a.total_curvature_deg == result_b.total_curvature_deg


# =========================================================================== #
# Adversarial: immutability
# =========================================================================== #


def test_adv_spine_curvature_still_frozen_with_new_fields():
    result = _curvature_for(_straight_spine())
    with pytest.raises(Exception):
        result.coronal_curvature_deg = 999.0  # type: ignore[misc]
    with pytest.raises(Exception):
        result.curvature_plane = "sagittal"  # type: ignore[misc]


# =========================================================================== #
# Adversarial: the retained unsigned arrays are unchanged by normalisation
# =========================================================================== #


def test_adv_retained_arrays_invariant_to_direction_normalisation():
    """inter_tangent_angles_deg keeps its present meaning: it is computed from
    the angle between consecutive raw tangents, which is mathematically
    invariant to a global sign flip (angle_between(-a, -b) == angle_between(a,
    b)). Reversing the traversal order of a curve reverses which physical
    tangent pair sits at each index, so the reversed sequence's
    inter_tangent_angles_deg array is the reverse of the original's -- proving
    the array is unaffected by whatever direction normalisation the new
    signed arrays apply internally, rather than merely re-asserting the
    code's own output.
    """
    forward = _curvature_for(_coronal_c_curve(7))
    cranial_first = _curvature_for(_cranial_first_c_curve(7))
    assert len(forward.inter_tangent_angles_deg) == len(cranial_first.inter_tangent_angles_deg)
    assert forward.inter_tangent_angles_deg == pytest.approx(
        tuple(reversed(cranial_first.inter_tangent_angles_deg)), abs=1e-6
    )
    # Both remain non-negative and finite regardless of traversal direction.
    for v in forward.inter_tangent_angles_deg + cranial_first.inter_tangent_angles_deg:
        assert math.isfinite(v) and v >= 0.0


def test_adv_tangent_angles_deg_length_and_finiteness_on_cranial_first_input():
    """tangent_angles_deg keeps its present (unsigned, un-normalised) meaning
    on a cranial-first input too: it is not the new descriptor's concern to
    correct it (that is item 121's territory per the Decisions log), only to
    leave it finite and correctly shaped."""
    result = _curvature_for(_cranial_first_c_curve(7))
    assert len(result.tangent_angles_deg) == 7
    for v in result.tangent_angles_deg:
        assert math.isfinite(v)
