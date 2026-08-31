"""Tests for item 131 -- normalise ``tangent_angles_deg[]`` for traversal direction.

Item 122 introduced a direction convention -- negate every unit tangent once,
per case, when the ordered centroids' net advance in ``+S`` is negative --
but applied it only to the signed per-plane arrays it introduced, leaving
``tangent_angles_deg[]`` (and, incidentally, ``inter_tangent_angles_deg[]``,
which turns out to already be invariant) reading the *raw* tangents. This
item makes ``tangent_angles_deg[]`` use the same ``normalised_tangents``
array the signed arrays already use, so the record carries one convention
instead of two.

Covers AC1-AC25 with direct tests (AC26 -- the regression-test-fails-before-
the-fix replay -- is verified by the item's Validation section's detached-
commit replay, not by a self-referential assertion in this module).

**Designated regression test for AC26** (the Validation section replays this
one on the pre-implementation commit and expects it to fail):
``test_ac1_cranial_first_straight_spine_reads_zero_not_180``.

Adversarial and edge cases: two-centroid minimum, fewer-than-two
``ValueError``, a purely horizontal (zero-net-advance, flat) pair, a
zero-net-advance *non-flat* doubling-back path (AC24 -- equivariance
deliberately not asserted there), near-coincident centroids, anisotropic
spacing combined with reversal, a coronal C-curve mirrored left-right (proves
``tangent_angles_deg`` depends only on the S-component, not R), a spine
reversed *and* mirrored L<->R, determinism, immutability, and a synthetic
per-element-fold implementation fed ``mode4_relabel_swap``'s tangents to show
it would produce a different array than the one global sign decision (AC4).
"""

from __future__ import annotations

import math
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from segfacet.config import bundled_default_config  # noqa: E402
from segfacet.feature_docs import FEATURE_DOCS, STATUS_OVERRIDES  # noqa: E402
from segfacet.features.centroids import LabelCentroid, compute_centroid  # noqa: E402
from segfacet.features.spline import fit_centroid_spline  # noqa: E402
from segfacet.features.orientation import (  # noqa: E402
    SpineCurvature,
    compute_spine_curvature,
)
from segfacet.pipeline import extract_feature_record, run_qc  # noqa: E402
from segfacet.report import _SCHEMA  # noqa: E402
from segfacet.synth.corpus import load_manifest  # noqa: E402
from segfacet.synth.regression import loaded_seg_image  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _REPO_ROOT / "src" / "segfacet"
_CATALOGUE_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_CATALOGUE_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

_CANONICAL_KEY_PHRASE = "normalised so the sequence advances superiorly"
_RETIRED_PHRASE = "cranial-to-caudal traversal"

# =========================================================================== #
# Fixture builders -- copied (not imported) from test_122_signed_curvature.py
# and test_121_tangent_orientation.py, per this repo's module-independence
# convention for item tests.
# =========================================================================== #

_LEVELS = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    return [
        _centroid(_LEVELS[i % len(_LEVELS)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _coronal_c_curve(n: int = 7) -> List[LabelCentroid]:
    return [
        _centroid(
            _LEVELS[i % len(_LEVELS)],
            (30.0 * math.sin(math.pi * i / 6.0), 0.0, 15.0 * i),
            label=i + 1,
        )
        for i in range(n)
    ]


def _cranial_first_straight(n: int = 5, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    """The same physical straight spine as ``_straight_spine``, supplied
    starting at the head, so ``centroid_mm[-1][2] - centroid_mm[0][2] < 0``."""
    return list(reversed(_straight_spine(n, spacing_mm)))


def _cranial_first_c_curve(n: int = 7) -> List[LabelCentroid]:
    return list(reversed(_coronal_c_curve(n)))


def _mode4_relabel_swap_shape() -> List[LabelCentroid]:
    """A doubling-back coronal sequence reproducing the real
    ``mode4_relabel_swap`` corpus case's shape at unit-test scale (indices 2
    and 3 swapped in S)."""
    xs = [0.0, 40.0, 65.0, 40.0, -40.0, -65.0]
    zs = [0.0, 15.0, 45.0, 30.0, 60.0, 75.0]
    return [
        _centroid(_LEVELS[i], (xs[i], 0.0, zs[i]), label=i + 1) for i in range(len(xs))
    ]


def _mirrored_c_curve(n: int = 7) -> List[LabelCentroid]:
    """The same physical coronal C-curve as ``_coronal_c_curve``, mirrored
    left-right (negated R). The S-component of every tangent is unaffected by
    negating R, so this fixture proves ``tangent_angles_deg`` -- an angle to
    the S axis alone -- does not move under an R-mirror."""
    return [
        _centroid(c.level_name, (-c.centroid_mm[0], c.centroid_mm[1], c.centroid_mm[2]), label=c.label)
        for c in _coronal_c_curve(n)
    ]


def _cranial_first_mirrored_c_curve(n: int = 7) -> List[LabelCentroid]:
    """The mirrored coronal C-curve, additionally supplied cranial-first --
    reversed *and* mirrored L<->R at once."""
    return list(reversed(_mirrored_c_curve(n)))


def _zero_net_advance_horizontal_pair() -> List[LabelCentroid]:
    """Two centroids at the same S, differing only in R -- net advance exactly
    0.0, a flat (not doubling-back) path."""
    return [
        _centroid("L1", (0.0, 0.0, 20.0), label=1),
        _centroid("L2", (30.0, 0.0, 20.0), label=2),
    ]


def _zero_net_advance_doubling_back() -> List[LabelCentroid]:
    """A non-flat path that goes up in S and returns to its starting S --
    net advance exactly 0.0, but the path itself is not flat."""
    zs = [0.0, 20.0, 40.0, 20.0, 0.0]
    xs = [0.0, 10.0, 0.0, -10.0, 0.0]
    return [
        _centroid(_LEVELS[i], (xs[i], 0.0, zs[i]), label=i + 1) for i in range(len(xs))
    ]


def _anisotropic_straight_spine(n: int = 5) -> List[LabelCentroid]:
    return [
        _centroid(_LEVELS[i], (0.0, 0.0, float(i) * 40.0), label=i + 1) for i in range(n)
    ]


def _near_coincident_centroids(n: int = 4) -> List[LabelCentroid]:
    return [
        _centroid(_LEVELS[i], (5.0 + i * 1e-6, 5.0, 5.0 + i * 1e-6), label=i + 1)
        for i in range(n)
    ]


def _curvature_for(centroids: List[LabelCentroid]) -> SpineCurvature:
    fit = fit_centroid_spline(centroids)
    return compute_spine_curvature(fit, centroids)


def _ordered_centroids_for_case(case: dict) -> List[LabelCentroid]:
    """Ascending-label-order centroids for a corpus case, matching
    pipeline.py's own "ordered centroid sequence" construction."""
    seg_img = loaded_seg_image(case)
    data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(data) if v != 0)
    assert labels, f"no foreground labels found in case {case.get('case_id')!r}"
    return [compute_centroid(seg_img, label) for label in labels]


# =========================================================================== #
# AC1: tangent_angles_deg is computed from direction-normalised tangents
# =========================================================================== #


def test_ac1_cranial_first_straight_spine_reads_zero_not_180():
    """Designated AC26 regression test (see module docstring): pre-fix,
    a cranial-first straight spine's tangent_angles_deg reads ~180.0
    (raw tangents point caudally relative to +S); post-fix it reads 0.0."""
    result = _curvature_for(_cranial_first_straight(5, 10.0))
    for v in result.tangent_angles_deg:
        assert v == pytest.approx(0.0, abs=1e-9), (
            f"tangent_angles_deg entry {v!r} is not ~0.0 -- tangent_angles_deg "
            f"appears to still be derived from raw (un-normalised) tangents"
        )


# =========================================================================== #
# AC2: reversal-equivariance on well-conditioned fixtures (abs=1e-9)
# =========================================================================== #


def test_ac2_straight_spine_reversal_equivariant():
    forward = _curvature_for(_straight_spine())
    reversed_result = _curvature_for(list(reversed(_straight_spine())))
    assert forward.tangent_angles_deg == pytest.approx(
        tuple(reversed(reversed_result.tangent_angles_deg)), abs=1e-9
    )


def test_ac2_coronal_c_curve_reversal_equivariant():
    forward = _curvature_for(_coronal_c_curve(7))
    reversed_result = _curvature_for(_cranial_first_c_curve(7))
    assert forward.tangent_angles_deg == pytest.approx(
        tuple(reversed(reversed_result.tangent_angles_deg)), abs=1e-9
    )


def test_ac2_clean_control_own_sequence_reversal_equivariant():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "clean_control")
    centroids = _ordered_centroids_for_case(case)
    forward = _curvature_for(centroids)
    reversed_result = _curvature_for(list(reversed(centroids)))
    assert forward.tangent_angles_deg == pytest.approx(
        tuple(reversed(reversed_result.tangent_angles_deg)), abs=1e-9
    )


# =========================================================================== #
# AC3: reversal-equivariance on a doubling-back fixture (abs=1e-2)
# =========================================================================== #


def test_ac3_doubling_back_fixture_reversal_equivariant_looser_tolerance():
    """mode4_relabel_swap's shape reverses in S; the residual (measured
    6.563e-03 deg) is spline-fit asymmetry, not a convention difference, so
    the tolerance is deliberately looser than AC2's."""
    forward = _curvature_for(_mode4_relabel_swap_shape())
    reversed_result = _curvature_for(list(reversed(_mode4_relabel_swap_shape())))
    forward_arr = np.asarray(forward.tangent_angles_deg, dtype=np.float64)
    reversed_arr = np.asarray(tuple(reversed(reversed_result.tangent_angles_deg)), dtype=np.float64)
    residual = float(np.max(np.abs(forward_arr - reversed_arr)))
    assert residual < 1e-2, (
        f"doubling-back reversal residual {residual:.6e} deg exceeds the "
        f"abs=1e-2 tolerance measured for spline-fit asymmetry on this shape"
    )


# =========================================================================== #
# AC4: one global sign decision, never a per-element fold
# =========================================================================== #


def _per_element_fold(angles) -> List[float]:
    """The rejected alternative reading of 'normalise': fold each angle into
    [0, 90] rather than applying one global sign decision."""
    return [min(a, 180.0 - a) for a in angles]


def test_ac4_mode4_relabel_swap_matches_global_decision_not_per_element_fold():
    manifest = load_manifest()
    case = next(c for c in manifest["cases"] if c["case_id"] == "mode4_relabel_swap")
    seg_img = loaded_seg_image(case)
    record = extract_feature_record(seg_img, bundled_default_config())
    actual = list(record["stage3"]["curvature"]["tangent_angles_deg"])

    expected_global = [3.2953, 177.6490, 175.2184, 1.4658, 22.0118]
    assert actual == pytest.approx(expected_global, abs=1e-3)

    rejected_fold = _per_element_fold(actual)
    max_diff = max(abs(a - b) for a, b in zip(rejected_fold, actual))
    assert max_diff > 1.0, (
        f"a per-element fold of the actual output (max diff {max_diff:.4f} deg) "
        f"nearly matches the actual output -- the fixture no longer carries "
        f"genuinely reversing tangents that would distinguish the two "
        f"implementations: fold={rejected_fold!r} actual={actual!r}"
    )
    # The per-element fold, applied to the *correct* global-decision array,
    # would itself read close to the values a wrongly-implemented fold would
    # produce -- pinned so a future reader sees exactly what AC4 rules out.
    expected_fold_if_wrongly_implemented = [3.2953, 2.3510, 4.7816, 1.4658, 22.0118]
    assert _per_element_fold(expected_global) == pytest.approx(
        expected_fold_if_wrongly_implemented, abs=1e-3
    )


# =========================================================================== #
# AC5 / AC6: no committed corpus case's tangent_angles_deg moves, and every
# corpus case's net +S advance is positive
# =========================================================================== #

_PRE_ITEM_TANGENT_ANGLES_DEG = {
    "clean_control": [8.1652, 4.0730, 0.0, 4.0730, 8.1652],
    "mode1_displace": [25.5042, 27.8238, 0.0, 27.8238, 25.5042],
    "mode2_fragment": [8.1652, 4.0730, 0.0, 4.0730, 8.1652],
    "mode3_inject_islands": [8.1498, 4.0650, 0.0, 4.0650, 8.1498],
    "mode4_relabel_swap": [3.2953, 177.6490, 175.2184, 1.4658, 22.0118],
    "mode5_remove_level": [7.6323, 3.7952, 3.7952, 7.6323],
    "mode6_crop_at_border": [28.8047, 24.3476, 0.0, 24.3476, 28.8047],
    "mode7_sequence_break": [8.1652, 4.0730, 0.0, 4.0730, 8.1652],
    "mode8_force_overlap": [13.2111, 6.9636, 0.6253, 4.9247, 5.7262],
}

_PRE_ITEM_NET_ADVANCE_S_MM = {
    "clean_control": 160.0,
    "mode1_displace": 160.0,
    "mode2_fragment": 160.0,
    "mode3_inject_islands": 160.0,
    "mode4_relabel_swap": 160.0,
    "mode5_remove_level": 160.0,
    "mode6_crop_at_border": 160.0,
    "mode7_sequence_break": 160.0,
    "mode8_force_overlap": 142.0,
}


def test_ac5_no_corpus_case_tangent_angles_deg_moves():
    manifest = load_manifest()
    assert set(_PRE_ITEM_TANGENT_ANGLES_DEG) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        record = extract_feature_record(seg_img, bundled_default_config())
        actual = list(record["stage3"]["curvature"]["tangent_angles_deg"])
        expected = _PRE_ITEM_TANGENT_ANGLES_DEG[case["case_id"]]
        assert actual == pytest.approx(expected, abs=1e-3), (
            f"{case['case_id']}: tangent_angles_deg moved -- {actual} != {expected}"
        )


def test_ac6_every_corpus_case_net_advance_positive():
    manifest = load_manifest()
    assert set(_PRE_ITEM_NET_ADVANCE_S_MM) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        centroids = _ordered_centroids_for_case(case)
        net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
        assert net > 0.0, f"{case['case_id']}: net +S advance {net} is not positive"
        expected = _PRE_ITEM_NET_ADVANCE_S_MM[case["case_id"]]
        assert net == pytest.approx(expected, abs=1e-6), (
            f"{case['case_id']}: net advance {net} != measured {expected} -- "
            f"AC5's table is no longer explained by every case advancing superiorly"
        )


# =========================================================================== #
# AC7: inter_tangent_angles_deg is reversal-equivariant and unmoved
# =========================================================================== #

_PRE_ITEM_INTER_TANGENT_ANGLES_DEG = {
    "clean_control": [4.092235, 4.072969, 4.072969, 4.092235],
    "mode1_displace": [52.786936, 27.823768, 27.823768, 52.786936],
    "mode2_fragment": [4.092235, 4.072969, 4.072969, 4.092235],
    "mode3_inject_islands": [4.084804, 4.065026, 4.065026, 4.084804],
    "mode4_relabel_swap": [179.055714, 2.430623, 173.752605, 20.545999],
    "mode5_remove_level": [3.837156, 7.590310, 3.837156],
    "mode6_crop_at_border": [52.093619, 24.347610, 24.347610, 52.093619],
    "mode7_sequence_break": [4.092235, 4.072969, 4.072969, 4.092235],
    "mode8_force_overlap": [6.247546, 7.588856, 4.299399, 0.801556],
}


def test_ac7_no_corpus_case_inter_tangent_angles_deg_moves():
    manifest = load_manifest()
    assert set(_PRE_ITEM_INTER_TANGENT_ANGLES_DEG) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        record = extract_feature_record(seg_img, bundled_default_config())
        actual = list(record["stage3"]["curvature"]["inter_tangent_angles_deg"])
        expected = _PRE_ITEM_INTER_TANGENT_ANGLES_DEG[case["case_id"]]
        assert actual == pytest.approx(expected, abs=1e-3), (
            f"{case['case_id']}: inter_tangent_angles_deg moved -- {actual} != {expected}"
        )


@pytest.mark.parametrize(
    "centroids_fn",
    [_straight_spine, _coronal_c_curve, _mode4_relabel_swap_shape],
)
def test_ac7_reversal_equivariant_on_fixtures(centroids_fn):
    centroids = centroids_fn()
    forward = _curvature_for(centroids)
    reversed_result = _curvature_for(list(reversed(centroids)))
    assert forward.inter_tangent_angles_deg == pytest.approx(
        tuple(reversed(reversed_result.inter_tangent_angles_deg)), abs=1e-2
    )


def test_ac7_reversal_equivariant_exactly_on_well_conditioned_fixtures():
    for centroids in (_straight_spine(), _coronal_c_curve(7)):
        forward = _curvature_for(centroids)
        reversed_result = _curvature_for(list(reversed(centroids)))
        assert forward.inter_tangent_angles_deg == pytest.approx(
            tuple(reversed(reversed_result.inter_tangent_angles_deg)), abs=1e-9
        )


# =========================================================================== #
# AC8: one canonical convention statement exists in code
# =========================================================================== #


def _find_canonical_convention_constants():
    import segfacet.features.orientation as orientation_mod

    found = []
    for name in orientation_mod.__all__:
        value = getattr(orientation_mod, name, None)
        if isinstance(value, str) and len(value) > 40:
            found.append((name, value))
    return found


def test_ac8_canonical_convention_constant_in_all_and_states_the_rule():
    candidates = _find_canonical_convention_constants()
    assert candidates, (
        "no module-level string constant >40 chars found in "
        "segfacet.features.orientation.__all__ -- AC8 requires one naming "
        "the direction-normalisation convention"
    )
    name, text = candidates[0]
    lower = text.lower()
    assert "negative" in lower, f"{name!r} does not name the trigger (net advance negative): {text!r}"
    assert "superior" in lower, f"{name!r} does not name the result (advances superiorly): {text!r}"
    assert "global" in lower, f"{name!r} does not state the negation is global: {text!r}"
    assert "per-element" in lower, f"{name!r} does not rule out a per-element fold: {text!r}"


def test_ac8_canonical_convention_constant_is_the_only_such_candidate():
    """A second, unrelated long string in __all__ would make AC9-AC11's
    "read the constant from one place" claim ambiguous."""
    candidates = _find_canonical_convention_constants()
    assert len(candidates) <= 1, (
        f"expected at most one canonical-convention string constant in "
        f"__all__, found {len(candidates)}: {[n for n, _ in candidates]!r}"
    )


# =========================================================================== #
# AC9: SpineCurvature docstring states the convention for both unsigned arrays
# =========================================================================== #

_ATTR_HEADER_RE = re.compile(r"^ {4}([A-Za-z_][A-Za-z0-9_]*)\s*:\s")


def _numpydoc_attribute_blocks(docstring: str):
    """Split a numpydoc-style 'Attributes' docstring into per-attribute text
    blocks, keyed by attribute name. Assumes 4-space-indented headers and
    more-deeply-indented body lines -- the format SpineCurvature's docstring
    already uses."""
    blocks = {}
    current = None
    buf: List[str] = []
    for line in docstring.splitlines():
        m = _ATTR_HEADER_RE.match(line)
        if m:
            if current is not None:
                blocks[current] = "\n".join(buf)
            current = m.group(1)
            buf = [line]
        elif current is not None:
            buf.append(line)
    if current is not None:
        blocks[current] = "\n".join(buf)
    return blocks


def test_ac9_docstring_states_convention_for_both_unsigned_arrays():
    docstring = SpineCurvature.__doc__ or ""
    blocks = _numpydoc_attribute_blocks(docstring)
    for attr in ("tangent_angles_deg", "inter_tangent_angles_deg"):
        assert attr in blocks, f"SpineCurvature docstring has no attribute block for {attr!r}"
        assert _CANONICAL_KEY_PHRASE in blocks[attr], (
            f"SpineCurvature.__doc__'s {attr!r} block does not contain the "
            f"canonical key phrase {_CANONICAL_KEY_PHRASE!r}: {blocks[attr]!r}"
        )


# =========================================================================== #
# AC10: FEATURE_DOCS states the convention for both unsigned leaf paths
# =========================================================================== #


@pytest.mark.parametrize(
    "path",
    [
        "stage3.curvature.tangent_angles_deg[]",
        "stage3.curvature.inter_tangent_angles_deg[]",
    ],
)
def test_ac10_feature_docs_state_convention(path):
    assert path in FEATURE_DOCS, f"FEATURE_DOCS missing entry for {path!r}"
    doc = FEATURE_DOCS[path]
    combined = doc.measures + " " + doc.computation
    assert _CANONICAL_KEY_PHRASE in combined, (
        f"{path!r}'s FEATURE_DOCS text does not contain the canonical key "
        f"phrase {_CANONICAL_KEY_PHRASE!r}: {combined!r}"
    )


# =========================================================================== #
# AC11: report_schema_v0.json states the convention for both unsigned keys
# =========================================================================== #


@pytest.mark.parametrize(
    "key",
    ["tangent_angles_deg", "inter_tangent_angles_deg"],
)
def test_ac11_schema_descriptions_state_convention(key):
    curvature_def = _SCHEMA["definitions"]["stage3Curvature"]
    description = curvature_def["properties"][key]["description"]
    assert _CANONICAL_KEY_PHRASE in description, (
        f"schema description for {key!r} does not contain the canonical key "
        f"phrase {_CANONICAL_KEY_PHRASE!r}: {description!r}"
    )


# =========================================================================== #
# AC12: the backwards phrase 'cranial-to-caudal traversal' is gone repo-wide
# =========================================================================== #


def test_ac12_retired_phrase_absent_under_src_segfacet():
    offenders = []
    for path in sorted(_SRC_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue
        if _RETIRED_PHRASE in text:
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == [], (
        f"{_RETIRED_PHRASE!r} still present under src/segfacet/ in: {offenders}"
    )


# =========================================================================== #
# AC13: the superseded 'unaffected by normalisation' note is gone
# =========================================================================== #


def test_ac13_superseded_unaffected_note_gone_from_orientation_module():
    orientation_src = (_SRC_DIR / "features" / "orientation.py").read_text(encoding="utf-8")
    retired_note = "tangent_angles_deg and inter_tangent_angles_deg above are unaffected"
    assert retired_note not in orientation_src, (
        f"the superseded note ({retired_note!r}) is still present in "
        f"features/orientation.py -- it now names the opposite of what the "
        f"code does for tangent_angles_deg"
    )


# =========================================================================== #
# AC14: item 122's plane and RAS statements survive the reword (delegated)
# =========================================================================== #


def test_ac14_item_122_plane_and_ras_test_still_passes():
    import test_122_signed_curvature as t122

    for path, plane in (
        ("stage3.curvature.coronal_tangent_angles_deg[]", "coronal"),
        ("stage3.curvature.sagittal_tangent_angles_deg[]", "sagittal"),
        ("stage3.curvature.coronal_curvature_deg", "coronal"),
        ("stage3.curvature.sagittal_curvature_deg", "sagittal"),
    ):
        t122.test_ac17_new_leaf_docs_name_their_plane_and_ras_precondition(path, plane)


# =========================================================================== #
# AC15-AC18: catalogue regeneration, leaf-path set, observed ranges, drift
# =========================================================================== #


def test_ac15_catalogue_regenerates_byte_identically(tmp_path):
    """Byte-exact fresh-vs-committed comparison, legitimate under item 127's
    committed-artifact guard: both docs/aide/feature_catalogue.generated.*
    carry an 'emission-clamped' ALLOWLIST entry in
    tests/committed_artifact_guard.py -- the same shape
    test_130_one_closest_point_search.py::test_ac22_... uses. This item adds
    no new allowlist entry."""
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.read_bytes() == _CATALOGUE_JSON.read_bytes()
    assert md_dest.read_bytes() == _CATALOGUE_MD.read_bytes()

    catalogue.build_catalogue(strict=True)


_PRE_ITEM_STAGE3_CURVATURE_LEAF_PATHS = (
    "stage3.curvature.coronal_curvature_deg",
    "stage3.curvature.coronal_tangent_angles_deg[]",
    "stage3.curvature.curvature_plane",
    "stage3.curvature.inter_tangent_angles_deg[]",
    "stage3.curvature.sagittal_curvature_deg",
    "stage3.curvature.sagittal_tangent_angles_deg[]",
    "stage3.curvature.tangent_angles_deg[]",
    "stage3.curvature.total_curvature_deg",
)
_PRE_ITEM_TOTAL_LEAF_PATH_COUNT = 138


def test_ac16_catalogue_leaf_path_set_unchanged():
    import json

    import segfacet.catalogue as catalogue

    fresh = catalogue.build_catalogue(strict=True)
    fresh_paths = sorted(e.path for e in fresh.entries)

    committed = json.loads(_CATALOGUE_JSON.read_text(encoding="utf-8"))
    committed_paths = sorted(
        e["path"] for g in committed["groups"] for e in g["entries"]
    )

    assert fresh_paths == committed_paths, "the catalogue's leaf-path set moved"
    assert len(fresh_paths) == _PRE_ITEM_TOTAL_LEAF_PATH_COUNT, (
        f"leaf-path count {len(fresh_paths)} != pre-item "
        f"{_PRE_ITEM_TOTAL_LEAF_PATH_COUNT} -- a path was added or removed"
    )
    curvature_paths = tuple(sorted(p for p in fresh_paths if p.startswith("stage3.curvature.")))
    assert curvature_paths == _PRE_ITEM_STAGE3_CURVATURE_LEAF_PATHS


def test_ac17_observed_range_cells_unchanged(tmp_path):
    import json

    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])
    fresh = json.loads(json_dest.read_text(encoding="utf-8"))

    entries_by_path = {
        e["path"]: e for g in fresh["groups"] for e in g["entries"]
    }

    tangent = entries_by_path["stage3.curvature.tangent_angles_deg[]"]
    assert tangent["observed"]["corpus"]["minimum"] == pytest.approx(0.0, abs=1e-6)
    assert tangent["observed"]["corpus"]["maximum"] == pytest.approx(8.1652, abs=1e-3)
    assert tangent["observed"]["verdict"] == "varies"
    assert tangent["status"] == "retune"

    inter = entries_by_path["stage3.curvature.inter_tangent_angles_deg[]"]
    assert inter["observed"]["corpus"]["minimum"] == pytest.approx(3.83716, abs=1e-3)
    assert inter["observed"]["corpus"]["maximum"] == pytest.approx(7.59031, abs=1e-3)
    assert inter["observed"]["verdict"] == "varies"
    assert inter["status"] == "retune"


def test_ac18_catalogue_drift_clean_in_both_directions():
    """Reuses item 104's own walk functions (never reimplements the
    recursion -- test_104's own AC2 forbids that in its own module, and the
    same reasoning applies here)."""
    import test_104_feature_catalogue_drift as t104

    realised = t104.covered_paths()
    documented = t104.documented_paths()
    report = t104.drift_report(
        realised=realised,
        documented=documented,
        realised_label="realised-but-undocumented",
        documented_label="documented-but-not-realised",
    )
    assert report is None, f"catalogue drift detected: {report}"


# =========================================================================== #
# AC19: no corpus case changes its findings
# =========================================================================== #


def test_ac19_no_corpus_case_changes_findings():
    import test_129_coincident_centroids_and_held_out_floor as t129

    manifest = load_manifest()
    assert set(t129._PRE_129_FINDINGS) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        case_result, _features_block = run_qc(seg_img, bundled_default_config())
        pairs = {(f.rule_id, tuple(sorted(f.labels))) for f in case_result.findings}
        expected = t129._PRE_129_FINDINGS[case["case_id"]]
        assert pairs == expected, f"{case['case_id']}: {pairs} != {expected}"


# =========================================================================== #
# AC20: no reference artifact moves
# =========================================================================== #


def test_ac20_reference_verse_v1_digest_unchanged():
    import hashlib

    import test_128_reference_verse_v1_integrity as t128

    digest = hashlib.sha256(t128._ARTIFACT.read_bytes()).hexdigest()
    assert digest == t128._RELEASED_REFERENCE_VERSE_V1_SHA256


def test_ac20_fresh_default_reference_matches_committed(tmp_path):
    import json

    from segfacet.reference.artifact import build_and_write_default, default_artifact_path
    from segfacet.synth.golden import assert_matches_committed_artifact

    dest = tmp_path / "reference_default.json"
    build_and_write_default(dest)
    fresh = json.loads(dest.read_text(encoding="utf-8"))
    assert_matches_committed_artifact(fresh, default_artifact_path())


# =========================================================================== #
# AC21: the other curvature fields are unmoved
# =========================================================================== #

_PRE_ITEM_OTHER_CURVATURE_FIELDS = {
    "clean_control": {
        "total_curvature_deg": 16.330407,
        "coronal_curvature_deg": 16.330407,
        "sagittal_curvature_deg": 0.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [8.165203, 4.072969, 0.0, -4.072969, -8.165203],
        "sagittal_tangent_angles_deg": [0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "mode1_displace": {
        "total_curvature_deg": 44.926306,
        "coronal_curvature_deg": 44.926306,
        "sagittal_curvature_deg": 42.295125,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [-15.600454, 22.463153, 0.0, -22.463153, 15.600454],
        "sagittal_tangent_angles_deg": [-21.147563, 18.160137, 0.0, -18.160137, 21.147563],
    },
    "mode2_fragment": {
        "total_curvature_deg": 16.330407,
        "coronal_curvature_deg": 16.330407,
        "sagittal_curvature_deg": 0.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [8.165203, 4.072969, 0.0, -4.072969, -8.165203],
        "sagittal_tangent_angles_deg": [0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "mode3_inject_islands": {
        "total_curvature_deg": 16.299623,
        "coronal_curvature_deg": 16.299623,
        "sagittal_curvature_deg": 0.035422,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [8.149811, 4.065017, 0.0, -4.065017, -8.149811],
        "sagittal_tangent_angles_deg": [-0.017711, -0.008789, 0.0, 0.008789, 0.017711],
    },
    "mode4_relabel_swap": {
        "total_curvature_deg": 355.238942,
        "coronal_curvature_deg": 355.238942,
        "sagittal_curvature_deg": 180.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [3.295293, 182.351007, 184.78163, 358.534236, 337.988237],
        "sagittal_tangent_angles_deg": [0.0, 180.0, 180.0, 0.0, 0.0],
    },
    "mode5_remove_level": {
        "total_curvature_deg": 15.264623,
        "coronal_curvature_deg": 15.264623,
        "sagittal_curvature_deg": 0.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [7.632311, 3.795155, -3.795155, -7.632311],
        "sagittal_tangent_angles_deg": [0.0, 0.0, 0.0, 0.0],
    },
    "mode6_crop_at_border": {
        "total_curvature_deg": 56.66451,
        "coronal_curvature_deg": 12.316259,
        "sagittal_curvature_deg": 56.66451,
        "curvature_plane": "sagittal",
        "coronal_tangent_angles_deg": [6.15813, 4.869332, 0.0, -4.869332, -6.15813],
        "sagittal_tangent_angles_deg": [-28.332255, 23.961638, 0.0, -23.961638, 28.332255],
    },
    "mode7_sequence_break": {
        "total_curvature_deg": 16.330407,
        "coronal_curvature_deg": 16.330407,
        "sagittal_curvature_deg": 0.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [8.165203, 4.072969, 0.0, -4.072969, -8.165203],
        "sagittal_tangent_angles_deg": [0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "mode8_force_overlap": {
        "total_curvature_deg": 18.937358,
        "coronal_curvature_deg": 18.937358,
        "sagittal_curvature_deg": 0.0,
        "curvature_plane": "coronal",
        "coronal_tangent_angles_deg": [13.211112, 6.963566, -0.62529, -4.924689, -5.726245],
        "sagittal_tangent_angles_deg": [0.0, 0.0, 0.0, 0.0, 0.0],
    },
}


def test_ac21_other_curvature_fields_unmoved():
    manifest = load_manifest()
    assert set(_PRE_ITEM_OTHER_CURVATURE_FIELDS) == {c["case_id"] for c in manifest["cases"]}
    for case in manifest["cases"]:
        seg_img = loaded_seg_image(case)
        record = extract_feature_record(seg_img, bundled_default_config())
        curv = record["stage3"]["curvature"]
        expected = _PRE_ITEM_OTHER_CURVATURE_FIELDS[case["case_id"]]
        for key in (
            "total_curvature_deg",
            "coronal_curvature_deg",
            "sagittal_curvature_deg",
            "coronal_tangent_angles_deg",
            "sagittal_tangent_angles_deg",
        ):
            assert curv[key] == pytest.approx(expected[key], abs=1e-6), (
                f"{case['case_id']}.{key} moved: {curv[key]} != {expected[key]}"
            )
        assert curv["curvature_plane"] == expected["curvature_plane"], (
            f"{case['case_id']}.curvature_plane moved: "
            f"{curv['curvature_plane']!r} != {expected['curvature_plane']!r}"
        )


# =========================================================================== #
# AC22: item 121's per-vertebra tangent orientations are unmoved (delegated)
# =========================================================================== #


def test_ac22_item_121_part_c_signed_angles_still_pass():
    import test_121_tangent_orientation as t121

    t121.test_ac8_coronal_c_curve_signed_angles()
    t121.test_ac9_sagittal_c_curve_signed_angles()


# =========================================================================== #
# AC23: STATUS_OVERRIDES is untouched
# =========================================================================== #

_PRE_ITEM_STATUS_OVERRIDES = {
    "stage3.curvature.tangent_angles_deg[]": (
        "retune",
        "Should be decomposed into three per-axis components -- the tangent "
        "vector's angle projected along each scan dimension -- rather than "
        "one scalar relative to the superior-inferior axis alone.",
    ),
    "stage3.curvature.inter_tangent_angles_deg[]": (
        "retune",
        "Should likewise be decomposed into three per-axis components per "
        "neighbouring vertebra pair, rather than one scalar angle.",
    ),
}


def test_ac23_status_overrides_byte_identical():
    for path, expected in _PRE_ITEM_STATUS_OVERRIDES.items():
        assert path in STATUS_OVERRIDES, f"STATUS_OVERRIDES missing {path!r}"
        assert STATUS_OVERRIDES[path] == expected, (
            f"STATUS_OVERRIDES[{path!r}] changed: {STATUS_OVERRIDES[path]!r} "
            f"!= {expected!r}"
        )


# =========================================================================== #
# AC24: the zero-net-advance tie is deterministic and documented
# =========================================================================== #


def test_ac24_zero_net_advance_doubling_back_deterministic_and_finite():
    """Reversal-equivariance is deliberately NOT asserted here: it does not
    hold for a non-flat zero-net-advance path (item 122's strict '< 0' takes
    no negation at exactly 0.0, and the un-negated, non-flat path is not its
    own reversal-mirror)."""
    centroids = _zero_net_advance_doubling_back()
    net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
    assert net == 0.0

    result_a = _curvature_for(centroids)
    result_b = _curvature_for(centroids)
    assert result_a.tangent_angles_deg == result_b.tangent_angles_deg
    for v in result_a.tangent_angles_deg:
        assert math.isfinite(v)


def test_ac24_canonical_constant_names_the_tie_break():
    name, text = _find_canonical_convention_constants()[0]
    lower = text.lower()
    assert "0" in text or "zero" in lower or "tie" in lower, (
        f"{name!r} does not name the zero-net-advance tie-break: {text!r}"
    )


# =========================================================================== #
# AC25: the committed-artifact guard reports no new violation
# =========================================================================== #


def test_ac25_committed_artifact_guard_reports_no_new_violations():
    if str(_TESTS_DIR) not in sys.path:
        sys.path.insert(0, str(_TESTS_DIR))
    import committed_artifact_guard as guard

    violations = list(guard.iter_violations(_TESTS_DIR))
    assert violations == [], f"unexpected committed-artifact-guard violations: {violations}"


# =========================================================================== #
# Adversarial: two centroids only (the minimum compute_spine_curvature accepts)
# =========================================================================== #


def test_adv_two_centroids_both_directions_finite_and_equivariant():
    forward = _curvature_for(_straight_spine(2))
    reversed_result = _curvature_for(list(reversed(_straight_spine(2))))
    assert len(forward.tangent_angles_deg) == 2
    assert len(forward.inter_tangent_angles_deg) == 1
    for v in forward.tangent_angles_deg + forward.inter_tangent_angles_deg:
        assert math.isfinite(v)
    assert forward.tangent_angles_deg == pytest.approx(
        tuple(reversed(reversed_result.tangent_angles_deg)), abs=1e-9
    )


# =========================================================================== #
# Adversarial: fewer than two centroids still raises ValueError
# =========================================================================== #


def test_adv_fewer_than_two_centroids_still_raises_value_error():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(ValueError):
        compute_spine_curvature(fit, centroids[:1])


# =========================================================================== #
# Adversarial: purely horizontal (flat) zero-net-advance pair
# =========================================================================== #


def test_adv_horizontal_pair_zero_net_advance_ninety_degrees_deterministic():
    centroids = _zero_net_advance_horizontal_pair()
    net = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
    assert net == 0.0

    result_a = _curvature_for(centroids)
    result_b = _curvature_for(centroids)
    assert result_a.tangent_angles_deg == result_b.tangent_angles_deg
    for v in result_a.tangent_angles_deg:
        assert v == pytest.approx(90.0, abs=1e-6)


# =========================================================================== #
# Adversarial: near-coincident centroids
# =========================================================================== #


def test_adv_near_coincident_centroids_finite_no_crash():
    result = _curvature_for(_near_coincident_centroids())
    for v in result.tangent_angles_deg:
        assert math.isfinite(v), f"non-finite tangent_angles_deg entry: {v}"


# =========================================================================== #
# Adversarial: anisotropic spacing combined with reversal
# =========================================================================== #


def test_adv_anisotropic_spacing_reversal_still_zero_both_ways():
    forward = _curvature_for(_anisotropic_straight_spine())
    reversed_result = _curvature_for(list(reversed(_anisotropic_straight_spine())))
    for v in forward.tangent_angles_deg:
        assert v == pytest.approx(0.0, abs=1e-9)
    for v in reversed_result.tangent_angles_deg:
        assert v == pytest.approx(0.0, abs=1e-9)


# =========================================================================== #
# Adversarial: a coronal C-curve mirrored L<->R -- proves tangent_angles_deg
# depends only on the S-component of the tangent, not R
# =========================================================================== #


def test_adv_mirrored_c_curve_tangent_angles_deg_unchanged_by_mirroring():
    forward = _curvature_for(_coronal_c_curve(7))
    mirrored = _curvature_for(_mirrored_c_curve(7))
    assert forward.tangent_angles_deg == pytest.approx(mirrored.tangent_angles_deg, abs=1e-9)


# =========================================================================== #
# Adversarial: a spine reversed AND mirrored L<->R
# =========================================================================== #


def test_adv_reversed_and_mirrored_c_curve_still_equivariant():
    mirrored_forward = _curvature_for(_mirrored_c_curve(7))
    mirrored_reversed = _curvature_for(_cranial_first_mirrored_c_curve(7))
    assert mirrored_forward.tangent_angles_deg == pytest.approx(
        tuple(reversed(mirrored_reversed.tangent_angles_deg)), abs=1e-9
    )


# =========================================================================== #
# Adversarial: determinism
# =========================================================================== #


def test_adv_determinism_two_calls_equal():
    centroids = _mode4_relabel_swap_shape()
    result_a = _curvature_for(centroids)
    result_b = _curvature_for(centroids)
    assert result_a.tangent_angles_deg == result_b.tangent_angles_deg
    assert result_a.inter_tangent_angles_deg == result_b.inter_tangent_angles_deg


# =========================================================================== #
# Adversarial: immutability -- SpineCurvature stays frozen, input untouched
# =========================================================================== #


def test_adv_spine_curvature_still_frozen():
    result = _curvature_for(_straight_spine())
    with pytest.raises(Exception):
        result.tangent_angles_deg = (0.0,)  # type: ignore[misc]


def test_adv_input_centroid_sequence_not_mutated():
    centroids = _cranial_first_c_curve(7)
    before = [c.centroid_mm for c in centroids]
    _curvature_for(centroids)
    after = [c.centroid_mm for c in centroids]
    assert before == after


# =========================================================================== #
# Adversarial: every entry stays within [0, 180] on all corpus cases, both
# directions
# =========================================================================== #


def test_adv_tangent_angles_deg_stays_in_0_180_range_both_directions():
    manifest = load_manifest()
    for case in manifest["cases"]:
        centroids = _ordered_centroids_for_case(case)
        for seq in (centroids, list(reversed(centroids))):
            result = _curvature_for(seq)
            for v in result.tangent_angles_deg:
                assert 0.0 <= v <= 180.0, f"{case['case_id']}: {v} outside [0, 180]"
            for v in result.inter_tangent_angles_deg:
                assert 0.0 <= v <= 180.0, f"{case['case_id']}: {v} outside [0, 180]"
