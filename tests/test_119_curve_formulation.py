"""Tests for item 119 -- implement the chosen curve formulation.

Item 119 replaces the interpolating ``splprep(..., s=0)`` fit in
``segfacet.features.spline`` with ``scipy.interpolate.make_splprep(..., s=n_points)``,
per the decision recorded in ``docs/spinal-curve-model.md`` and approved by the
2026-08-27 human gate. This is not a rename: ``make_splprep`` returns a
``(BSpline, u)`` pair, so ``SplineFit`` loses its ``tck`` field and gains
``spline`` (a ``scipy.interpolate.BSpline``) and ``smoothing`` (the ``s``
actually used).

**Contract fixed here** (the spec leaves the derivative-helper's name to the
test suite): a public first-derivative evaluator named
``evaluate_spline_derivative(fit, u_values, nu=1, *, backend=None) -> np.ndarray``
with the same ``(N, 3)`` / device-marshalling contract as ``evaluate_spline``
(AC14). ``segfacet.features.orientation.compute_spine_curvature`` must call
this helper rather than importing SciPy itself.

Covers Acceptance Criteria AC1-AC27:

- AC1-AC6: direct unit assertions on ``fit_centroid_spline``'s return shape
  (``make_splprep`` import, no legacy FITPACK wrappers, ``smoothing`` default
  and override, degree clamp, chord-length ``u`` parameterisation).
- AC7/AC8: item 017's clean-GT fixtures stay within its own 0.5 mm unit
  tolerance while the synthetic ``build_clean_spine`` sweep exceeds it once,
  bounded at 0.56 mm and inside stage 28's 1.0 mm acceptance bound -- a
  matched pair, both directions asserted.
- AC9/AC10: a displaced vertebra separates under leave-one-out evaluation but
  not in-sample -- also a matched pair.
- AC11-AC13: determinism and degenerate/edge-count inputs (2-level, truncated
  FOV).
- AC14/AC15: the new derivative helper and curvature preservation.
- AC16/AC17: coincident and near-coincident centroids.
- AC18-AC22: corpus goldens, the Stage-3 report golden, the regeneration's
  narrowness, the untouched ``mislabel`` threshold, and the byte-identical
  ``pipeline.py``.
- AC23: the raised SciPy floor.
- AC24/AC25: the candidate-comparison tool's candidate identities and the
  decision document's reproduced numbers.
- AC26/AC27: the feature-catalogue prose and regenerated artifacts.

Adversarial and edge cases:
- Zero/one centroid still raise ValueError with a readable message.
- Collinear centroids reduce to (near-)exact fit, no degeneracy.
- Highly anisotropic mm coordinates.
- One level removed from the middle/front/back of a 6-level sequence.
- ``smoothing=0.0`` and ``smoothing=1e6`` -- neither raises, both finite.
- Input sequence immutability; ``SplineFit`` stays frozen.
- ``evaluate_spline`` at u=0.0, u=1.0, and 500 interior values: no NaN/Inf.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

from segfacet.features.centroids import LabelCentroid, compute_centroid
from segfacet.features.orientation import compute_spine_curvature
from segfacet.features.spline import SplineFit, evaluate_spline, fit_centroid_spline
from segfacet.features.spline_offset import compute_spline_offsets
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import GOLDEN_DIR, check_case_golden, load_golden, write_goldens

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Pre-119 sha256 digests (pipeline.py bytes; the catalogue's sorted leaf-path
# set), captured by the test-writer while those artifacts were still in their
# pre-119 state. Held in an external fixture rather than as string literals
# in this file's own source, per test_115's AC8 discriminator: a digest
# compared against a value pulled from a committed JSON snapshot is an
# "external" comparison, not a hardcoded-literal "fence" -- see
# tests/test_094_tptbox_image_layer.py's data_sha256 lookup for the same
# pattern.
_PRE_119_DIGESTS = json.loads(
    (_REPO_ROOT / "tests" / "corpus" / "119_pre_119_digests.json").read_text(encoding="utf-8")
)


# =========================================================================== #
# Helpers (mirrors tests/test_017_centroid_spline_fit.py's fixture style)
# =========================================================================== #


def _centroid(level_name: str, mm: Tuple[float, float, float], label: int = 0) -> LabelCentroid:
    return LabelCentroid(
        label=label,
        level_name=level_name,
        centroid_voxel=(0.0, 0.0, 0.0),
        centroid_mm=mm,
    )


def _straight_spine(n: int = 6, spacing_mm: float = 10.0) -> List[LabelCentroid]:
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm))
        for i in range(n)
    ]


def _curved_spine() -> List[LabelCentroid]:
    levels = ["T8", "T9", "T10", "T11", "T12", "L1"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    return [_centroid(lv, (x, 0.0, z)) for lv, x, z in zip(levels, xs, zs)]


def _anisotropic_spine() -> List[LabelCentroid]:
    levels = ["T10", "T11", "T12", "L1", "L2"]
    return [
        _centroid(levels[i], (float(i) * 0.5, float(i) * 0.5, float(i) * 30.0))
        for i in range(5)
    ]


def _dist3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return math.sqrt(sum((bi - ai) ** 2 for ai, bi in zip(a, b)))


def _centroids_from_clean_spine(levels, spacing, curve_amplitude_mm=6.0) -> List[LabelCentroid]:
    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)
    return [compute_centroid(spine.seg_img, lbl) for lbl in spine.labels]


def _polyline_length_mm(centroids) -> float:
    total = 0.0
    for i in range(1, len(centroids)):
        a = np.array(centroids[i - 1].centroid_mm, dtype=np.float64)
        b = np.array(centroids[i].centroid_mm, dtype=np.float64)
        total += float(np.linalg.norm(b - a))
    return total


def _arc_length_mm(fit: SplineFit, n: int = 200) -> float:
    u = np.linspace(0.0, 1.0, n)
    pts = evaluate_spline(fit, u)
    diffs = np.diff(pts, axis=0)
    return float(np.sum(np.linalg.norm(diffs, axis=1)))


# =========================================================================== #
# AC1: The fit is built with make_splprep
# =========================================================================== #


def test_ac1_module_imports_make_splprep():
    import segfacet.features.spline as spline_mod

    source = Path(spline_mod.__file__).read_text(encoding="utf-8")
    assert "make_splprep" in source
    assert "from scipy.interpolate import" in source


def test_ac1_fit_spline_attribute_is_bspline_instance():
    from scipy.interpolate import BSpline

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit.spline, BSpline)


# =========================================================================== #
# AC2: The legacy FITPACK wrappers are gone from the package
# =========================================================================== #


def test_ac2_no_module_imports_splprep_or_splev():
    import ast

    src_root = _REPO_ROOT / "src" / "segfacet"
    offenders = []
    for path in src_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in ("splprep", "splev"):
                        offenders.append(f"{path}: imports {alias.name}")
            if isinstance(node, ast.Attribute) and node.attr in ("splprep", "splev"):
                offenders.append(f"{path}: references .{node.attr}")
            if isinstance(node, ast.Name) and node.id in ("splprep", "splev"):
                offenders.append(f"{path}: references bare name {node.id}")
    assert offenders == [], f"legacy FITPACK wrapper usage found: {offenders}"


# =========================================================================== #
# AC3: Smoothing defaults to the input-point count
# =========================================================================== #


@pytest.mark.parametrize("n", range(2, 9))
def test_ac3_default_smoothing_equals_n_points(n):
    centroids = _straight_spine(n)
    fit = fit_centroid_spline(centroids)
    assert fit.smoothing == float(n)
    assert fit.n_points == n


# =========================================================================== #
# AC4: Smoothing is overridable; smoothing=0.0 reproduces an interpolating fit
# =========================================================================== #


def _ac7_fixtures():
    """Item 017's own GT fixtures (straight 6/7, curved 6, anisotropic 5),
    each also with one level removed -- the population AC7 and AC4 replay."""
    fixtures = {
        "straight6": _straight_spine(6),
        "straight7": _straight_spine(7, spacing_mm=12.0),
        "curved6": _curved_spine(),
        "anisotropic5": _anisotropic_spine(),
    }
    cases = dict(fixtures)
    for name, cs in fixtures.items():
        if len(cs) >= 3:
            mid = len(cs) // 2
            cases[f"{name}_missing_mid"] = cs[:mid] + cs[mid + 1 :]
    return cases


def test_ac4_smoothing_zero_reproduces_interpolating_fit_on_gt_fixtures():
    for name, centroids in _ac7_fixtures().items():
        fit = fit_centroid_spline(centroids, smoothing=0.0)
        pts = evaluate_spline(fit, list(fit.u))
        for i, c in enumerate(centroids):
            dist = _dist3((pts[i, 0], pts[i, 1], pts[i, 2]), c.centroid_mm)
            assert dist < 1e-3, f"{name}[{i}] is {dist:.6f} mm from an s=0 fit"


def test_ac4_default_smoothing_does_not_pass_through_within_1e3mm():
    """The default (s=n_points) fit is NOT within 1e-3 mm of every centroid
    on at least one of item 017's GT fixtures -- distinguishing it from the
    smoothing=0.0 interpolating fit above."""
    any_exceeds = False
    for name, centroids in _ac7_fixtures().items():
        fit = fit_centroid_spline(centroids)
        pts = evaluate_spline(fit, list(fit.u))
        for i, c in enumerate(centroids):
            dist = _dist3((pts[i, 0], pts[i, 1], pts[i, 2]), c.centroid_mm)
            if dist >= 1e-3:
                any_exceeds = True
    assert any_exceeds, "expected the default smoothing fit to differ from s=0 on at least one fixture"


# =========================================================================== #
# AC5: The degree clamp is unchanged
# =========================================================================== #


@pytest.mark.parametrize("n", range(2, 9))
def test_ac5_degree_clamped_to_min_requested_and_n_minus_1(n):
    centroids = _straight_spine(n)
    fit = fit_centroid_spline(centroids, degree=3)
    assert fit.degree == min(3, n - 1)


def test_ac5_explicit_degree_2_used_when_enough_points():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids, degree=2)
    assert fit.degree == 2


# =========================================================================== #
# AC6: The chord-length parameterisation is unchanged in meaning
# =========================================================================== #


def test_ac6_u_length_starts_zero_ends_one_strictly_increasing():
    centroids = _straight_spine(7)
    fit = fit_centroid_spline(centroids)
    assert len(fit.u) == 7
    assert float(fit.u[0]) == pytest.approx(0.0)
    assert float(fit.u[-1]) == pytest.approx(1.0)
    u_vals = [float(v) for v in fit.u]
    for i in range(1, len(u_vals)):
        assert u_vals[i] > u_vals[i - 1]


# =========================================================================== #
# AC7/AC8: matched pair -- item 017's bound holds; the sweep exceeds it once
# =========================================================================== #


def test_ac7_item017_gt_fixtures_stay_within_half_mm():
    """AC7: on item 017's own GT fixtures (straight 6/7, curved 6, anisotropic
    5, each with one level removed), evaluating at fit.u stays within 0.5 mm
    of every input centroid. Measured worst case on this branch: 0.19198 mm
    on the curved fixture."""
    overall_max = 0.0
    for name, centroids in _ac7_fixtures().items():
        fit = fit_centroid_spline(centroids)
        pts = evaluate_spline(fit, list(fit.u))
        for i, c in enumerate(centroids):
            dist = _dist3((pts[i, 0], pts[i, 1], pts[i, 2]), c.centroid_mm)
            overall_max = max(overall_max, dist)
            assert dist < 0.5, f"{name}[{i}] is {dist:.5f} mm from the spline (AC7 bound: 0.5 mm)"
    # The bound is not vacuous: the worst case should be well inside it.
    assert overall_max < 0.5


def test_ac8_clean_gt_sweep_exceeds_half_mm_but_stays_under_0_56mm():
    """AC8: over build_clean_spine's level-count x spacing sweep grid, the
    max in-sample closest-approach distance is > 0.5 mm and <= 0.56 mm --
    both halves asserted so this value cannot silently move without this test
    noticing (recorded: 0.552139 mm).

    The 0.5 mm lower half is *not* an acceptance bound. Stage 28's acceptance
    line was raised to 1.0 mm on 2026-08-28 precisely because it had been
    reusing item 017's AC1 -- a unit tolerance on that item's own fixtures,
    checked by test_ac7 above -- across this much wider sweep, which the
    approved smoothing formulation does not satisfy. What the lower half pins
    is that the sweep still reaches past that unit tolerance: if it stopped
    doing so, the fit would have drifted back toward interpolation and the
    approved formulation would no longer be what is running.
    """
    levels_pool = ("L1", "L2", "L3", "L4", "L5")
    level_counts = (2, 3, 5)
    spacings = ((1.0, 1.0, 1.0), (1.0, 1.0, 2.0), (0.8, 0.8, 1.0))

    overall_max = 0.0
    for count in level_counts:
        levels = levels_pool[:count]
        for spacing in spacings:
            centroids = _centroids_from_clean_spine(levels, spacing, curve_amplitude_mm=6.0)
            fit = fit_centroid_spline(centroids)
            offsets = compute_spline_offsets(centroids, fit, spacing_mm=spacing)
            for offset in offsets:
                overall_max = max(overall_max, offset.offset_mm)

    assert overall_max > 0.5, (
        f"expected the sweep to exceed item 017's 0.5 mm unit tolerance at some "
        f"grid point (got max {overall_max:.6f} mm) -- if this no longer exceeds "
        f"0.5 mm, the fit has drifted back toward interpolation and is no longer "
        f"the formulation item 118's gate approved. Re-measure, do not silently "
        f"accept a smaller max."
    )
    assert overall_max <= 0.56, f"sweep max {overall_max:.6f} mm exceeds the 0.56 mm ceiling"
    # Stage 28's acceptance bound (raised 0.5 -> 1.0 mm on 2026-08-28). Implied
    # by the 0.56 ceiling above, but asserted in its own right so the criterion
    # the stage is ticked against is checked somewhere rather than inferred.
    assert overall_max < 1.0, (
        f"sweep max {overall_max:.6f} mm breaches stage 28's 1.0 mm pass-through "
        f"acceptance bound"
    )


# =========================================================================== #
# AC9/AC10: matched pair -- leave-one-out separates, in-sample does not
# =========================================================================== #


def _separation_fixture():
    """The decision document's separation fixture: 8 thoracic levels, 1 mm
    isotropic, 6 mm curve amplitude."""
    return _centroids_from_clean_spine(
        ("T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"),
        (1.0, 1.0, 1.0),
        curve_amplitude_mm=6.0,
    )


def _displace_middle(centroids, magnitude_mm: float = 5.0):
    target_idx = len(centroids) // 2
    per_axis = magnitude_mm / math.sqrt(2.0)
    c = centroids[target_idx]
    x, y, z = c.centroid_mm
    displaced = dataclasses.replace(c, centroid_mm=(x + per_axis, y + per_axis, z))
    return target_idx, displaced


def test_ac9_displaced_vertebra_separates_under_leave_one_out():
    """AC9: fitting through the other seven levels and measuring with
    compute_spline_offsets, the displaced centroid's offset exceeds the
    largest of the seven clean centroids' offsets by >= 4.5 mm. (Decision
    document records 4.999144 mm as the smallest margin over 5/10/20 mm.)"""
    centroids = _separation_fixture()
    target_idx, displaced = _displace_middle(centroids, magnitude_mm=5.0)

    others = centroids[:target_idx] + centroids[target_idx + 1 :]
    fit_others = fit_centroid_spline(others)

    clean_offsets = compute_spline_offsets(others, fit_others)
    clean_max = max(o.offset_mm for o in clean_offsets)

    displaced_offset = compute_spline_offsets([displaced], fit_others)[0].offset_mm

    margin = displaced_offset - clean_max
    assert margin >= 4.5, f"leave-one-out margin {margin:.6f} mm is below the 4.5 mm bound"


def test_ac10_in_sample_evaluation_does_not_separate():
    """AC10: with the displaced centroid included in the fit, the same
    margin is below 0.5 mm -- the reason AC9 must be leave-one-out."""
    centroids = _separation_fixture()
    target_idx, displaced = _displace_middle(centroids, magnitude_mm=5.0)

    scenario = list(centroids)
    scenario[target_idx] = displaced
    fit_scenario = fit_centroid_spline(scenario)

    offsets = compute_spline_offsets(scenario, fit_scenario)
    displaced_offset = offsets[target_idx].offset_mm
    clean_max = max(o.offset_mm for i, o in enumerate(offsets) if i != target_idx)

    margin = displaced_offset - clean_max
    assert margin < 0.5, f"in-sample margin {margin:.6f} mm should stay below 0.5 mm"


# =========================================================================== #
# AC11: Two fits of the same input are identical
# =========================================================================== #


def test_ac11_determinism_curved_spine_full_shape():
    centroids = _curved_spine()
    fit1 = fit_centroid_spline(centroids)
    fit2 = fit_centroid_spline(centroids)

    assert fit1.u == fit2.u
    assert fit1.degree == fit2.degree
    assert fit1.n_points == fit2.n_points
    assert fit1.smoothing == fit2.smoothing
    np.testing.assert_array_equal(fit1.spline.t, fit2.spline.t)
    np.testing.assert_array_equal(fit1.spline.c, fit2.spline.c)

    pts1 = evaluate_spline(fit1, list(fit1.u))
    pts2 = evaluate_spline(fit2, list(fit2.u))
    np.testing.assert_array_equal(pts1, pts2)


# =========================================================================== #
# AC12: A 2-level input fits without error
# =========================================================================== #


def test_ac12_two_level_input_fits_without_error():
    centroids = _straight_spine(2)
    fit = fit_centroid_spline(centroids)
    assert fit.degree == 1
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert pts.shape == (3, 3)
    assert np.all(np.isfinite(pts))


# =========================================================================== #
# AC13: A truncated-FOV input fits without error and is not degenerate
# =========================================================================== #


def test_ac13_truncated_fov_input_not_degenerate():
    full = _centroids_from_clean_spine(("L1", "L2", "L3", "L4", "L5"), (1.0, 1.0, 1.0), curve_amplitude_mm=6.0)
    truncated = full[:3]  # keep only the cranial 3 of 5

    fit = fit_centroid_spline(truncated)
    u_vals = np.linspace(0.0, 1.0, 50)
    pts = evaluate_spline(fit, u_vals)
    assert np.all(np.isfinite(pts))

    poly_len = _polyline_length_mm(truncated)
    arc_len = _arc_length_mm(fit)
    assert poly_len > 0.0
    ratio = arc_len / poly_len
    assert (1.0 / 3.0) <= ratio <= 3.0, f"arc-length ratio {ratio:.4f} exceeds the 3.0x non-degeneracy factor"


# =========================================================================== #
# AC14: A first-derivative evaluator is public and used
# =========================================================================== #


def test_ac14_derivative_helper_is_exported():
    import segfacet.features.spline as spline_mod

    assert hasattr(spline_mod, "evaluate_spline_derivative")
    assert "evaluate_spline_derivative" in spline_mod.__all__
    assert callable(spline_mod.evaluate_spline_derivative)


def test_ac14_derivative_helper_returns_n3_float64_array():
    from segfacet.features.spline import evaluate_spline_derivative

    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids)
    u_vals = [0.0, 0.25, 0.5, 0.75, 1.0]
    derivs = evaluate_spline_derivative(fit, u_vals)
    assert derivs.shape == (5, 3)
    assert derivs.dtype == np.float64
    assert np.all(np.isfinite(derivs))


def test_ac14_orientation_module_does_not_import_scipy_directly():
    import segfacet.features.orientation as orientation_mod

    source = Path(orientation_mod.__file__).read_text(encoding="utf-8")
    assert "import scipy" not in source
    assert "from scipy" not in source


# =========================================================================== #
# AC15: Curvature values are preserved for a clean fixture
# =========================================================================== #


def test_ac15_clean_lumbar_curvature_finite_and_shape_preserved():
    clean = build_clean_spine()  # default L1-L5 lumbar
    centroids = [compute_centroid(clean.seg_img, lbl) for lbl in clean.labels]
    fit = fit_centroid_spline(centroids)
    curvature = compute_spine_curvature(fit, centroids)

    n = len(centroids)
    assert len(curvature.tangent_angles_deg) == n
    assert len(curvature.inter_tangent_angles_deg) == n - 1
    assert len(curvature.coronal_tangent_angles_deg) == n
    assert len(curvature.sagittal_tangent_angles_deg) == n

    for v in curvature.tangent_angles_deg + curvature.inter_tangent_angles_deg:
        assert math.isfinite(v)
    for v in curvature.coronal_tangent_angles_deg + curvature.sagittal_tangent_angles_deg:
        assert math.isfinite(v)
    assert math.isfinite(curvature.total_curvature_deg)

    assert curvature.curvature_plane in {"coronal", "sagittal"}
    expected_total = max(curvature.coronal_curvature_deg, curvature.sagittal_curvature_deg)
    assert curvature.total_curvature_deg == pytest.approx(expected_total)

    coronal_sweep = max(curvature.coronal_tangent_angles_deg) - min(curvature.coronal_tangent_angles_deg)
    sagittal_sweep = max(curvature.sagittal_tangent_angles_deg) - min(curvature.sagittal_tangent_angles_deg)
    assert curvature.coronal_curvature_deg == pytest.approx(coronal_sweep)
    assert curvature.sagittal_curvature_deg == pytest.approx(sagittal_sweep)


# =========================================================================== #
# AC16/AC17: coincident and near-coincident centroids
# =========================================================================== #


def _coord_appears(msg: str, coord: float) -> bool:
    """True if *coord* shows up in *msg* under any plausible numeric
    formatting (plain float repr, %g, or a bare int-looking form)."""
    candidates = {str(coord), f"{coord:g}", repr(coord)}
    if float(coord).is_integer():
        candidates.add(str(int(coord)))
    return any(c in msg for c in candidates)


def test_ac16_exactly_coincident_centroids_raise_readable_value_error():
    centroids = _straight_spine(5)
    duplicate_mm = centroids[1].centroid_mm
    centroids[2] = dataclasses.replace(centroids[2], centroid_mm=duplicate_mm)

    with pytest.raises(ValueError) as exc_info:
        fit_centroid_spline(centroids)

    msg = str(exc_info.value)
    assert msg.strip(), "ValueError message must not be blank"
    assert centroids[1].level_name in msg, f"message does not name level {centroids[1].level_name!r}: {msg!r}"
    assert centroids[2].level_name in msg, f"message does not name level {centroids[2].level_name!r}: {msg!r}"
    for coord in duplicate_mm:
        assert _coord_appears(msg, coord), f"message does not name coordinate {coord!r}: {msg!r}"
    assert "Invalid inputs" not in msg
    assert "theoretically impossible result" not in msg.lower()


def test_ac17_near_coincident_centroids_still_fit():
    """Mirrors test_122_signed_curvature.py's near-coincident adversarial
    fixture (1e-6 mm perturbation), which must stay green unmodified."""
    levels = ["T8", "T9", "T10", "T11"]
    centroids = [
        _centroid(levels[i], (5.0 + i * 1e-6, 5.0, 5.0 + i * 1e-6), label=i + 1)
        for i in range(4)
    ]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert np.all(np.isfinite(pts))


# =========================================================================== #
# AC18: The nine corpus goldens are regenerated and agree with a fresh build
# =========================================================================== #


def test_ac18_every_manifest_case_matches_committed_golden():
    manifest = load_manifest()
    for case in manifest["cases"]:
        assert check_case_golden(case), f"{case['case_id']} does not match its committed golden"


def test_ac18_write_goldens_into_two_dirs_is_byte_identical(tmp_path):
    dest1 = tmp_path / "goldens1"
    dest2 = tmp_path / "goldens2"
    write_goldens(dest1)
    write_goldens(dest2)

    files1 = sorted(p.name for p in dest1.glob("*.json"))
    files2 = sorted(p.name for p in dest2.glob("*.json"))
    assert files1, "write_goldens produced no files"
    assert files1 == files2

    for name in files1:
        assert (dest1 / name).read_bytes() == (dest2 / name).read_bytes()


# =========================================================================== #
# AC19: The Stage-3 report golden is regenerated
# =========================================================================== #


def test_ac19_stage3_report_golden_matches_test_022_output():
    import test_022_stage3_serialisation as t022

    centroids = t022._straight_spine(5)
    block = t022._full_block_for_spine(centroids)
    produced = t022.serialize_report_json(
        t022._empty_verdict(), "golden-case-022", t022._config(), features=block
    )
    committed = t022.GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == committed


# =========================================================================== #
# AC20: The regeneration moves no verdict and no finding
# =========================================================================== #


# Pre-119 committed (verdict, [(rule_id, labels), ...]) per case, captured as
# a fixture constant -- not by re-reading a file this item rewrites.
_PRE_119_VERDICTS_AND_FINDINGS = {
    "clean_control": ("pass", []),
    "mode1_displace": ("pass", []),
    "mode2_fragment": ("flagged-for-review", [("fragmentation", [22])]),
    "mode3_inject_islands": ("flagged-for-review", [("fragmentation", [22])]),
    "mode4_relabel_swap": ("pass", []),
    "mode5_remove_level": ("flagged-for-review", [("coverage", [])]),
    "mode6_crop_at_border": ("flagged-for-review", [("border", [22])]),
    "mode7_sequence_break": ("flagged-for-review", [("sequence", [28])]),
    "mode8_force_overlap": ("pass", []),
}


def _leaf_paths(node, prefix=()):
    """Yield dotted-tuple paths to every scalar/list leaf in a nested dict."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _leaf_paths(value, prefix + (key,))
    else:
        yield prefix


def test_ac20_regeneration_moves_no_verdict_or_finding():
    manifest = load_manifest()
    assert set(c["case_id"] for c in manifest["cases"]) == set(_PRE_119_VERDICTS_AND_FINDINGS)

    for case in manifest["cases"]:
        case_id = case["case_id"]
        golden = load_golden(case_id)
        expected_verdict, expected_findings = _PRE_119_VERDICTS_AND_FINDINGS[case_id]

        assert golden["verdict"] == expected_verdict, f"{case_id}: verdict moved"
        actual_findings = [
            (f["rule_id"], list(f.get("labels", []))) for f in golden.get("findings", [])
        ]
        assert actual_findings == expected_findings, f"{case_id}: findings moved"


def test_ac20_diff_against_committed_goldens_stays_under_stage3(tmp_path):
    """Every changed JSON leaf between a fresh regeneration and the committed
    goldens lies under features.stage3."""
    fresh_dir = tmp_path / "fresh"
    write_goldens(fresh_dir)

    for case_path in GOLDEN_DIR.glob("*.json"):
        case_id = case_path.stem
        committed = json.loads(case_path.read_text(encoding="utf-8"))
        fresh = json.loads((fresh_dir / case_path.name).read_text(encoding="utf-8"))

        committed_leaves = set(_leaf_paths(committed))
        fresh_leaves = set(_leaf_paths(fresh))
        assert committed_leaves == fresh_leaves, f"{case_id}: leaf-path set changed"

        for path in committed_leaves:
            node_committed = committed
            node_fresh = fresh
            for key in path:
                node_committed = node_committed[key]
                node_fresh = node_fresh[key]
            if node_committed != node_fresh:
                assert "stage3" in path, (
                    f"{case_id}: change outside features.stage3 at {'.'.join(path)}: "
                    f"{node_committed!r} -> {node_fresh!r}"
                )


# =========================================================================== #
# AC21: mislabel's threshold is untouched and unreached
# =========================================================================== #


def test_ac21_mislabel_default_threshold_unchanged():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    assert _DEFAULT_MAX_OFFSET_MM == 15.0


def test_ac21_no_regenerated_golden_offset_reaches_2mm():
    manifest = load_manifest()
    for case in manifest["cases"]:
        golden = load_golden(case["case_id"])
        offsets = golden.get("features", {}).get("stage3", {}).get("per_label_offsets", [])
        for offset in offsets:
            assert offset["offset_mm"] < 2.0, (
                f"{case['case_id']}: offset_mm {offset['offset_mm']} reaches the "
                f"15.0/25.0 threshold-adjacency region item 123 owns"
            )


# =========================================================================== #
# AC22: The pipeline's offset evaluation is unchanged
# =========================================================================== #


def test_ac22_pipeline_is_byte_identical_to_pre_119():
    pipeline_path = _REPO_ROOT / "src" / "segfacet" / "pipeline.py"
    digest = hashlib.sha256(pipeline_path.read_bytes()).hexdigest()
    assert digest == _PRE_119_DIGESTS["pipeline_sha256"], (
        "src/segfacet/pipeline.py changed -- leave-one-out promotion is item 120's, "
        "not item 119's"
    )


def test_ac22_pipeline_fits_through_all_present_centroids_single_call():
    source = (_REPO_ROOT / "src" / "segfacet" / "pipeline.py").read_text(encoding="utf-8")
    assert source.count("compute_spline_offsets(") == 1
    assert "leave_one_out" not in source
    assert "_recon_leave_one_out_offset" not in source


# =========================================================================== #
# AC23: The SciPy floor is raised
# =========================================================================== #


def test_ac23_scipy_floor_raised_other_bounds_unchanged():
    text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"scipy>=1.15"' in text
    assert '"scipy>=1.7"' not in text
    for other in (
        '"numpy>=1.26,<3"',
        '"scikit-image>=0.19"',
        '"nibabel>=4.0"',
        '"PyYAML>=5.4"',
        '"jsonschema>=3.2"',
        '"tptbox==0.7.5"',
    ):
        assert other in text, f"unexpected change to dependency bound: {other!r} missing"


# =========================================================================== #
# AC24: The candidate-comparison tool keeps its candidate identities
# =========================================================================== #


def _load_compare_script():
    script_path = _REPO_ROOT / "scripts" / "compare_curve_candidates.py"
    spec = importlib.util.spec_from_file_location("compare_curve_candidates_119", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_ac24_interpolating_cubic_is_s_zero_fit_via_shipped_function():
    mod = _load_compare_script()
    centroids = _curved_spine()
    curve = mod._fit_interpolating_cubic(centroids)
    expected_fit = fit_centroid_spline(centroids, smoothing=0.0)
    pts = curve.evaluate(list(expected_fit.u))
    ref = evaluate_spline(expected_fit, list(expected_fit.u))
    np.testing.assert_allclose(pts, ref)


def test_ac24_smoothing_spline_candidate_is_s_n_points_fit_via_shipped_function():
    mod = _load_compare_script()
    centroids = _curved_spine()
    curve = mod._fit_smoothing_spline(centroids)
    expected_fit = fit_centroid_spline(centroids)
    pts = curve.evaluate(list(expected_fit.u))
    ref = evaluate_spline(expected_fit, list(expected_fit.u))
    np.testing.assert_allclose(pts, ref)


def test_ac24_script_source_builds_no_splinefit_by_hand_and_imports_no_splprep():
    source = (_REPO_ROOT / "scripts" / "compare_curve_candidates.py").read_text(encoding="utf-8")
    assert "SplineFit(" not in source
    assert "import splprep" not in source
    assert "from scipy.interpolate import splprep" not in source


def test_ac24_parametric_curve_wraps_via_evaluate_spline():
    import inspect

    mod = _load_compare_script()
    source = inspect.getsource(mod._ParametricCurve)
    assert "evaluate_spline" in source
    assert ".tck" not in source


# =========================================================================== #
# AC25: The decision document's quoted numbers still reproduce
# =========================================================================== #


def test_ac25_test_118_ac6_reproduction_stays_green(tmp_path):
    """Import test_118 (unmodified) and re-run its AC6 non-VerSe reproduction
    check directly, so a regression here fails loudly under item 119 too."""
    import test_118_curve_formulation_decision as t118

    text = t118._read_doc()
    tolerance = t118._parsed_tolerance(text)
    rows = t118._measurements_table(text)
    non_verse_rows = [r for r in rows if not t118._is_verse_sourced(r)]
    assert non_verse_rows

    mod = t118._load_script()
    out = tmp_path / "out"
    rc = mod.main(["--out", str(out)])
    assert rc == 0
    record = t118._read_artifact(out)

    for row in non_verse_rows:
        t118._assert_row_reproduces(row, record, tolerance)


# =========================================================================== #
# AC26: The feature catalogue no longer documents an interpolating fit
# =========================================================================== #


def test_ac26_spline_offset_note_describes_smoothing_fit_via_make_splprep():
    from segfacet.feature_docs import GROUP_INTROS

    note = GROUP_INTROS["Spline Offset"]
    assert "make_splprep" in note
    assert "s = n_points" in note or "s=n_points" in note
    assert "s=0" not in note
    assert "passes exactly through every centroid" not in note


def test_ac26_orientation_curvature_note_no_longer_names_splev():
    from segfacet.feature_docs import FEATURE_DOCS, GROUP_INTROS

    assert "splev" not in GROUP_INTROS["Orientation & Curvature"]
    tangent_doc = FEATURE_DOCS["stage3.curvature.tangent_angles_deg[]"]
    assert "splev" not in tangent_doc.computation


# =========================================================================== #
# AC27: The generated catalogue artifacts are regenerated
# =========================================================================== #


# The committed docs/aide/feature_catalogue.generated.json's sorted set of
# leaf `path` values is unchanged pre-119 (this item adds and removes no
# feature path -- only prose changes); pinned via a sha256 in
# _PRE_119_DIGESTS, captured while the catalogue was still in its pre-119
# state.


def test_ac27_catalogue_regeneration_matches_committed_artifacts(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()


def test_ac27_catalogue_leaf_path_set_unchanged_from_pre_119(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    record = json.loads(json_dest.read_text(encoding="utf-8"))
    paths = sorted(entry["path"] for group in record["groups"] for entry in group["entries"])
    digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()
    assert digest == _PRE_119_DIGESTS["catalogue_leaf_path_set_sha256"], (
        "the catalogue's set of leaf feature paths changed -- item 119 must add "
        "and remove no feature path"
    )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_zero_centroids_raises_value_error():
    with pytest.raises(ValueError):
        fit_centroid_spline([])


def test_adv_one_centroid_raises_value_error():
    with pytest.raises(ValueError):
        fit_centroid_spline([_centroid("L1", (0.0, 0.0, 0.0))])


def test_adv_collinear_centroids_no_degeneracy():
    levels = ["T8", "T9", "T10", "T11", "T12"]
    centroids = [_centroid(lv, (0.0, 0.0, float(i) * 10.0)) for i, lv in enumerate(levels)]
    fit = fit_centroid_spline(centroids)
    pts = evaluate_spline(fit, list(fit.u))
    for i, c in enumerate(centroids):
        # Collinear inputs are the easiest possible case for a smoothing fit
        # to reproduce almost exactly -- well inside item 017's 0.5 mm bound.
        assert _dist3((pts[i, 0], pts[i, 1], pts[i, 2]), c.centroid_mm) < 0.5


def test_adv_highly_anisotropic_spacing_no_crash():
    centroids = _anisotropic_spine()
    fit = fit_centroid_spline(centroids)
    assert isinstance(fit, SplineFit)
    pts = evaluate_spline(fit, [0.0, 0.5, 1.0])
    assert np.all(np.isfinite(pts))


@pytest.mark.parametrize("remove_index_name", ["front", "middle", "back"])
def test_adv_one_level_removed_from_six_level_sequence(remove_index_name):
    full = _straight_spine(6)
    index = {"front": 0, "middle": 3, "back": 5}[remove_index_name]
    remaining = full[:index] + full[index + 1 :]
    fit = fit_centroid_spline(remaining)
    assert isinstance(fit, SplineFit)
    pts = evaluate_spline(fit, list(fit.u))
    assert np.all(np.isfinite(pts))


def test_adv_smoothing_zero_never_raises():
    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids, smoothing=0.0)
    assert fit.smoothing == 0.0
    pts = evaluate_spline(fit, list(fit.u))
    assert np.all(np.isfinite(pts))


def test_adv_smoothing_absurdly_loose_stays_finite_and_non_degenerate():
    centroids = _centroids_from_clean_spine(("L1", "L2", "L3", "L4", "L5"), (1.0, 1.0, 1.0), curve_amplitude_mm=6.0)
    fit = fit_centroid_spline(centroids, smoothing=1e6)
    assert fit.smoothing == 1e6
    u_vals = np.linspace(0.0, 1.0, 50)
    pts = evaluate_spline(fit, u_vals)
    assert np.all(np.isfinite(pts))

    poly_len = _polyline_length_mm(centroids)
    arc_len = _arc_length_mm(fit)
    ratio = arc_len / poly_len
    assert (1.0 / 3.0) <= ratio <= 3.0


def test_adv_input_list_not_mutated():
    centroids = _straight_spine(5)
    original = list(centroids)
    fit_centroid_spline(centroids)
    assert centroids == original


def test_adv_spline_fit_is_frozen():
    centroids = _straight_spine(5)
    fit = fit_centroid_spline(centroids)
    with pytest.raises(Exception):
        fit.n_points = 0  # type: ignore[misc]


def test_adv_evaluate_spline_endpoints_and_interior_no_nan_no_inf():
    centroids = _curved_spine()
    fit = fit_centroid_spline(centroids)
    u_vals = list(np.linspace(0.0, 1.0, 500))
    u_vals[0] = 0.0
    u_vals[-1] = 1.0
    pts = evaluate_spline(fit, u_vals)
    assert not np.any(np.isnan(pts))
    assert not np.any(np.isinf(pts))
