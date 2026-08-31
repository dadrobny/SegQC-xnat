"""Tests for item 130 -- one closest-point search, one in-sample fit.

Two duplications in the spline layer are collapsed into one implementation
each: the coarse-scan-then-``minimize_scalar``-refine closest-point search,
written out three times (``features/spline_offset.py``,
``features/consistency.py``, ``scripts/compare_curve_candidates.py``), gains
one owner -- ``segfacet.features.spline.find_closest_point`` -- and the
pipeline's in-sample fit, computed twice per case (once directly, once again
inside ``compute_leave_one_out_spline_offsets``), is fit once and passed
down via a new keyword-only ``fit=`` parameter.

Covers Acceptance Criteria AC1-AC25 (see the item spec's Acceptance Criteria
section for the exact wording each test below is named for). This is a pure
consolidation -- no default and no observable value changes -- so every
existing value-level test (test_017-test_023, test_119-test_122, test_125,
test_129) must keep passing unmodified; none of those modules is edited
here.

Adversarial and edge cases:
- Query point exactly on the curve, and a query equidistant from two curve
  regions (a symmetric spine, queried on its own axis of symmetry).
- Query points beyond both curve ends: closest_u clamps to 0.0 / 1.0 rather
  than escaping [0, 1].
- Two-centroid and three-centroid fits -- the shortest curves the search can
  be asked about.
- n_scan=2 (smallest legal grid); n_scan in {1, 0, -5} and xatol in
  {0.0, -1.0} each raise ValueError naming the offending parameter.
- A callable evaluator returning the wrong shape, and one returning a
  non-finite coordinate -- the failure mode must be observable, not a
  silently plausible number.
- fit= supplied for a four-level sequence (sub-five in-sample fallback) and
  a six-level sequence (held-out path), each equal to the standalone call.
- fit= with n_points one too high, one too low, and against a
  single-centroid sequence -- each a ValueError naming both counts.
- A scratch module under tmp_path adding a second minimize_scalar call site,
  proving the AST sweep would catch it.
- Determinism of find_closest_point and of extract_feature_record's
  per_label_offsets / monotonic_consistency; non-mutation of the query
  array and the centroid sequence.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services). Symbols this item introduces (``find_closest_point``,
``ClosestPointOnCurve``, the ``fit=`` keyword) are imported inside the tests
that need them so collection succeeds before the builder lands.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.features.centroids import LabelCentroid, compute_centroid
from segfacet.features.consistency import compute_monotonic_consistency
from segfacet.features.spline import evaluate_spline, fit_centroid_spline
from segfacet.features.spline_offset import (
    compute_leave_one_out_spline_offsets,
    compute_spline_offsets,
)
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine

from synthetic import make_labelmap

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _REPO_ROOT / "src"
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"


# =========================================================================== #
# Helpers (mirror tests/test_120_leave_one_out_offset.py's style)
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
        _centroid(levels[i % len(levels)], (0.0, 0.0, float(i) * spacing_mm), label=i + 1)
        for i in range(n)
    ]


def _displace_index(centroids, idx: int, magnitude_mm: float, axis: int = 0) -> LabelCentroid:
    c = centroids[idx]
    mm = list(c.centroid_mm)
    mm[axis] += magnitude_mm
    return dataclasses.replace(c, centroid_mm=tuple(mm))


def _clean_spine_seg_img(levels, spacing=(1.0, 1.0, 1.0), curve_amplitude_mm=6.0):
    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)
    return spine.seg_img


def _centroids_from_clean_spine(levels, spacing, curve_amplitude_mm=6.0) -> List[LabelCentroid]:
    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)
    return [compute_centroid(spine.seg_img, lbl) for lbl in spine.labels]


def _five_level_clean_spine() -> List[LabelCentroid]:
    return _centroids_from_clean_spine(("L1", "L2", "L3", "L4", "L5"), (1.0, 1.0, 1.0))


def _coincident_label_map():
    """Mirrors tests/test_129_coincident_centroids_and_held_out_floor.py's
    reference realisation: labels 21/22 resolve to the same centroid."""
    blocks = {
        21: ((5, 15), (5, 15), (10, 30)),
        22: ((8, 12), (8, 12), (17, 23)),
    }
    return make_labelmap(shape=(20, 20, 40), blocks=blocks, spacing=(1.0, 1.0, 1.0))


def _iter_py_files(root: Path):
    return sorted(root.rglob("*.py"))


def _count_minimize_scalar_calls(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "minimize_scalar":
                count += 1
    return count


def _patched_fit_call_counter(monkeypatch):
    """Patch both points a fit_centroid_spline call can be reached through
    (item spec Testing Strategy, AC18 note): pipeline.py's deferred,
    call-time import from segfacet.features.spline, and
    segfacet.features.spline_offset's own top-level import binding."""
    import segfacet.features.spline as spline_mod
    import segfacet.features.spline_offset as so_mod

    counter = {"n": 0}
    real_fit = spline_mod.fit_centroid_spline

    def counting_fit(*args, **kwargs):
        counter["n"] += 1
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(spline_mod, "fit_centroid_spline", counting_fit)
    monkeypatch.setattr(so_mod, "fit_centroid_spline", counting_fit)
    return counter


# =========================================================================== #
# AC1: the shared search is public API of the spline module
# =========================================================================== #


def test_ac1_shared_search_is_public_api():
    import segfacet.features.spline as spline_mod

    assert hasattr(spline_mod, "find_closest_point")
    assert hasattr(spline_mod, "ClosestPointOnCurve")
    assert "find_closest_point" in spline_mod.__all__
    assert "ClosestPointOnCurve" in spline_mod.__all__


# =========================================================================== #
# AC2: ClosestPointOnCurve carries parameter, point and distance
# =========================================================================== #


def test_ac2_closest_point_on_curve_is_frozen_with_exact_fields():
    from segfacet.features.spline import ClosestPointOnCurve

    field_names = {f.name for f in dataclasses.fields(ClosestPointOnCurve)}
    assert field_names == {"closest_u", "point_mm", "distance_mm"}

    instance = ClosestPointOnCurve(closest_u=0.5, point_mm=(1.0, 2.0, 3.0), distance_mm=4.0)
    assert len(instance.point_mm) == 3
    assert all(isinstance(v, float) for v in instance.point_mm)
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.closest_u = 0.9


# =========================================================================== #
# AC3: the search accepts a SplineFit
# =========================================================================== #


def test_ac3_accepts_splinefit_and_matches_minimising_parameter():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    query = np.array([0.0, 0.0, 25.0])

    result = find_closest_point(query, fit)

    u_grid = np.linspace(0.0, 1.0, 5000)
    pts = evaluate_spline(fit, u_grid)
    dists = np.linalg.norm(pts - query, axis=1)
    assert result.distance_mm <= float(dists.min()) + 1e-6


# =========================================================================== #
# AC4: the search accepts a bare curve evaluator
# =========================================================================== #


def test_ac4_accepts_bare_evaluator_callable():
    from segfacet.features.spline import ClosestPointOnCurve, find_closest_point

    def evaluate(u_values):
        u = np.asarray(u_values, dtype=np.float64)
        return np.column_stack([u, np.zeros_like(u), np.zeros_like(u)])

    result = find_closest_point(np.array([0.5, 0.0, 0.0]), evaluate)
    assert isinstance(result, ClosestPointOnCurve)
    assert abs(result.closest_u - 0.5) < 1e-4


# =========================================================================== #
# AC5: the returned parameter is in the closed unit interval
# =========================================================================== #


@pytest.mark.parametrize(
    "query",
    [
        np.array([0.0, 0.0, 25.0]),  # near the interior
        np.array([500.0, 500.0, 500.0]),  # far off the curve
        np.array([0.0, 0.0, -1000.0]),  # far beyond the start
        np.array([0.0, 0.0, 1000.0]),  # far beyond the end
    ],
)
def test_ac5_closest_u_in_closed_unit_interval(query):
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    result = find_closest_point(query, fit)
    assert 0.0 <= result.closest_u <= 1.0


# =========================================================================== #
# AC6: the three returned fields are mutually consistent
# =========================================================================== #


def test_ac6_returned_fields_mutually_consistent():
    from segfacet.features.spline import find_closest_point

    centroids = _five_level_clean_spine()
    fit = fit_centroid_spline(centroids)
    query = np.array([12.0, -4.0, 30.0])

    result = find_closest_point(query, fit)

    recomputed_point = evaluate_spline(fit, [result.closest_u])[0]
    np.testing.assert_allclose(result.point_mm, recomputed_point, atol=1e-9)
    recomputed_dist = float(np.linalg.norm(query - recomputed_point))
    assert abs(result.distance_mm - recomputed_dist) < 1e-9


# =========================================================================== #
# AC7: the search's defaults are named module constants
# =========================================================================== #


def test_ac7_named_constants_are_the_search_defaults():
    import inspect

    import segfacet.features.spline as spline_mod

    module_ints = {
        name: val
        for name, val in vars(spline_mod).items()
        if not name.startswith("__") and isinstance(val, int) and not isinstance(val, bool)
    }
    module_floats = {
        name: val for name, val in vars(spline_mod).items() if not name.startswith("__") and isinstance(val, float)
    }
    assert 500 in module_ints.values(), "no module-level int constant equal to 500"
    assert any(abs(v - 1e-6) < 1e-15 for v in module_floats.values()), (
        "no module-level float constant equal to 1e-6"
    )

    sig = inspect.signature(spline_mod.find_closest_point)
    assert sig.parameters["n_scan"].default == 500
    assert sig.parameters["xatol"].default == 1e-6


# =========================================================================== #
# AC8: n_scan is honoured
# =========================================================================== #


def test_ac8_n_scan_honoured_by_coarse_evaluator_call():
    from segfacet.features.spline import find_closest_point

    calls = []

    def evaluate(u_values):
        u = np.asarray(u_values, dtype=np.float64)
        calls.append(u.shape[0])
        return np.column_stack([u, np.zeros_like(u), np.zeros_like(u)])

    find_closest_point(np.array([0.3, 0.0, 0.0]), evaluate, n_scan=17)

    assert calls, "evaluator was never called for the coarse scan"
    assert calls[0] == 17


# =========================================================================== #
# AC9: xatol is honoured
# =========================================================================== #


def test_ac9_xatol_reaches_minimize_scalar_options(monkeypatch):
    import segfacet.features.spline as spline_mod
    from scipy.optimize import minimize_scalar as real_minimize_scalar

    recorded = {}

    def recording_minimize_scalar(*args, **kwargs):
        recorded["xatol"] = kwargs.get("options", {}).get("xatol")
        return real_minimize_scalar(*args, **kwargs)

    monkeypatch.setattr(spline_mod, "minimize_scalar", recording_minimize_scalar)

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    spline_mod.find_closest_point(np.array([0.0, 0.0, 22.0]), fit, xatol=1e-3)

    assert recorded.get("xatol") == 1e-3


# =========================================================================== #
# AC10: invalid search parameters raise a readable ValueError
# =========================================================================== #


@pytest.mark.parametrize("n_scan", [1, 0, -5])
def test_ac10_invalid_n_scan_raises_readable_value_error(n_scan):
    from segfacet.features.spline import find_closest_point

    fit = fit_centroid_spline(_straight_spine(4))
    with pytest.raises(ValueError) as exc_info:
        find_closest_point(np.array([0.0, 0.0, 0.0]), fit, n_scan=n_scan)
    msg = str(exc_info.value)
    assert "n_scan" in msg
    assert str(n_scan) in msg


@pytest.mark.parametrize("xatol", [0.0, -1.0])
def test_ac10_invalid_xatol_raises_readable_value_error(xatol):
    from segfacet.features.spline import find_closest_point

    fit = fit_centroid_spline(_straight_spine(4))
    with pytest.raises(ValueError) as exc_info:
        find_closest_point(np.array([0.0, 0.0, 0.0]), fit, xatol=xatol)
    msg = str(exc_info.value)
    assert "xatol" in msg
    assert str(xatol) in msg


# =========================================================================== #
# AC11: the search accepts backend=None for signature uniformity
# =========================================================================== #


def test_ac11_backend_keyword_only_defaults_to_none():
    import inspect

    import segfacet.features.spline as spline_mod

    sig = inspect.signature(spline_mod.find_closest_point)
    backend_param = sig.parameters["backend"]
    assert backend_param.default is None
    assert backend_param.kind == inspect.Parameter.KEYWORD_ONLY


# =========================================================================== #
# AC12: exactly one minimize_scalar call site remains
# =========================================================================== #


def test_ac12_exactly_one_minimize_scalar_call_site():
    hits = {}
    for root in (_SRC_ROOT, _SCRIPTS_ROOT):
        for path in _iter_py_files(root):
            count = _count_minimize_scalar_calls(path)
            if count:
                hits[path] = count
    total = sum(hits.values())
    assert total == 1, f"expected exactly one minimize_scalar call site, found: {hits}"
    (only_path,) = hits.keys()
    assert only_path == _SRC_ROOT / "segfacet" / "features" / "spline.py"


def test_adversarial_ac12_sweep_detects_a_second_call_site(tmp_path):
    """Proves the AST sweep would actually catch a second call site rather
    than passing vacuously: a scratch module under tmp_path adding its own
    minimize_scalar call is counted alongside the real tree."""
    scratch_file = tmp_path / "extra_closest_point.py"
    scratch_file.write_text(
        "from scipy.optimize import minimize_scalar\n"
        "\n"
        "def bad():\n"
        "    return minimize_scalar(lambda u: u ** 2, bounds=(0, 1), method='bounded')\n",
        encoding="utf-8",
    )

    hits = {}
    for path in list(_iter_py_files(_SRC_ROOT)) + list(_iter_py_files(_SCRIPTS_ROOT)) + [scratch_file]:
        count = _count_minimize_scalar_calls(path)
        if count:
            hits[path] = count

    assert sum(hits.values()) == 2
    assert scratch_file in hits


# =========================================================================== #
# AC13: the two feature modules no longer define the search
# =========================================================================== #


def test_ac13_spline_offset_no_longer_defines_search():
    import segfacet.features.spline_offset as so_mod

    assert not hasattr(so_mod, "_find_closest_u")
    source = Path(so_mod.__file__).read_text(encoding="utf-8")
    assert "linspace" not in source
    assert "find_closest_point" in source


def test_ac13_consistency_no_longer_defines_search():
    import segfacet.features.consistency as consistency_mod

    assert not hasattr(consistency_mod, "_find_closest_u")
    source = Path(consistency_mod.__file__).read_text(encoding="utf-8")
    assert "linspace" not in source
    assert "find_closest_point" in source


# =========================================================================== #
# AC14: the comparison script delegates and keeps its tolerance
# =========================================================================== #


def test_ac14_script_delegates_and_keeps_xatol():
    source = (_SCRIPTS_ROOT / "compare_curve_candidates.py").read_text(encoding="utf-8")
    assert "find_closest_point" in source
    assert "xatol=1e-7" in source
    assert "linspace" not in source


# =========================================================================== #
# AC15: the offset layer accepts an externally supplied in-sample fit
# =========================================================================== #


def test_ac15_leave_one_out_accepts_supplied_fit_and_skips_own_call(monkeypatch):
    import segfacet.features.spline_offset as so_mod

    centroids = _five_level_clean_spine()
    fit = fit_centroid_spline(centroids)

    calls = {"n": 0}
    real_fit = so_mod.fit_centroid_spline

    def counting_fit(*args, **kwargs):
        calls["n"] += 1
        return real_fit(*args, **kwargs)

    monkeypatch.setattr(so_mod, "fit_centroid_spline", counting_fit)

    result = compute_leave_one_out_spline_offsets(centroids, fit=fit)

    assert calls["n"] == 0
    assert len(result) == 5


# =========================================================================== #
# AC16: supplying the fit changes no value
# =========================================================================== #


def test_ac16_supplying_fit_changes_no_value():
    centroids = _five_level_clean_spine()
    spacing = (1.0, 1.0, 1.0)

    without_fit = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing)
    fit = fit_centroid_spline(centroids)
    with_fit = compute_leave_one_out_spline_offsets(centroids, spacing_mm=spacing, fit=fit)

    assert without_fit == with_fit


# =========================================================================== #
# AC17: a mismatched fit is rejected
# =========================================================================== #


def test_ac17_mismatched_fit_count_rejected():
    centroids = _five_level_clean_spine()
    other_fit = fit_centroid_spline(_straight_spine(4))

    with pytest.raises(ValueError) as exc_info:
        compute_leave_one_out_spline_offsets(centroids, fit=other_fit)
    msg = str(exc_info.value)
    assert "4" in msg
    assert "5" in msg


@pytest.mark.parametrize("n_fit,n_centroids", [(6, 5), (4, 5), (2, 1)])
def test_adversarial_ac17_mismatched_fit_off_by_one_and_single_centroid(n_fit, n_centroids):
    """n_fit=2 / n_centroids=1 exercises the Assumptions note: the count
    check runs before the one-centroid early return, so it always fires."""
    fit = fit_centroid_spline(_straight_spine(n_fit))
    centroids = _straight_spine(n_centroids)

    with pytest.raises(ValueError) as exc_info:
        compute_leave_one_out_spline_offsets(centroids, fit=fit)
    msg = str(exc_info.value)
    assert str(n_fit) in msg
    assert str(n_centroids) in msg


# =========================================================================== #
# AC18: the pipeline fits the in-sample spline once per case
# =========================================================================== #


def test_ac18_five_level_spine_fits_exactly_six_times(monkeypatch):
    counter = _patched_fit_call_counter(monkeypatch)
    seg_img = _clean_spine_seg_img(("L1", "L2", "L3", "L4", "L5"))

    extract_feature_record(seg_img, bundled_default_config())

    assert counter["n"] == 6


def test_ac18_three_level_map_fits_exactly_once(monkeypatch):
    counter = _patched_fit_call_counter(monkeypatch)
    seg_img = _clean_spine_seg_img(("L1", "L2", "L3"))

    extract_feature_record(seg_img, bundled_default_config())

    assert counter["n"] == 1


# =========================================================================== #
# AC19: the one fit is the one every Stage-3 consumer sees
# =========================================================================== #


def _matching_call_text(source: str, call_name: str) -> str:
    """Return the full ``call_name(...)`` call text, matching parens rather
    than a fixed-width window, so a check against its contents cannot be
    satisfied by unrelated code that happens to follow nearby."""
    start = source.index(call_name)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced parens while scanning call {call_name!r}")


def test_ac19_pipeline_binds_one_fit_and_reuses_it():
    from segfacet import pipeline as pipeline_mod

    source = Path(pipeline_mod.__file__).read_text(encoding="utf-8")

    assert source.count("fit = fit_centroid_spline(") == 1, (
        "expected exactly one 'fit = fit_centroid_spline(...)' binding"
    )

    for call_name in (
        "compute_spine_curvature(",
        "compute_vertebra_tangent_orientations(",
        "compute_monotonic_consistency(",
        "compute_leave_one_out_spline_offsets(",
    ):
        call_text = _matching_call_text(source, call_name)
        # 'fit' as a whole argument/keyword token, not a substring hit
        # inside some other identifier (e.g. 'fit_centroid_spline').
        args = call_text[len(call_name) : -1]
        tokens = {tok.strip().split("=")[-1].strip() for tok in args.split(",")}
        assert "fit" in tokens, f"{call_name} call does not pass the bound 'fit' object: {call_text!r}"


# =========================================================================== #
# AC20: the two in-sample searches agree exactly
# =========================================================================== #


def test_ac20_monotonic_and_offset_closest_u_agree_clean():
    centroids = _five_level_clean_spine()
    fit = fit_centroid_spline(centroids)

    mono = compute_monotonic_consistency(centroids, fit)
    offsets = compute_spline_offsets(centroids, fit)

    assert list(mono.u_values) == [o.closest_u for o in offsets]


def test_ac20_monotonic_and_offset_closest_u_agree_displaced():
    centroids = _five_level_clean_spine()
    displaced = list(centroids)
    displaced[2] = _displace_index(centroids, 2, 18.0, axis=0)
    fit = fit_centroid_spline(displaced)

    mono = compute_monotonic_consistency(displaced, fit)
    offsets = compute_spline_offsets(displaced, fit)

    assert list(mono.u_values) == [o.closest_u for o in offsets]


# =========================================================================== #
# AC21: item 129's coincident-centroid pre-check is preserved
# =========================================================================== #


def test_ac21_coincident_centroids_precheck_preserved():
    seg_img = _coincident_label_map()

    record = extract_feature_record(seg_img, bundled_default_config())

    assert "stage3" not in record
    info = record["stage3_unavailable"]
    assert info["reason"] == "coincident_centroids"
    assert set(info["levels"]) == {"L2", "L3"}
    assert set(info["labels"]) == {21, 22}


# =========================================================================== #
# AC22: the committed feature catalogue does not move
# =========================================================================== #


def test_ac22_catalogue_regeneration_matches_committed_artifacts(tmp_path):
    """Byte-exact fresh-vs-committed catalogue comparison. Legitimate under
    item 127's committed-artifact guard: both
    docs/aide/feature_catalogue.generated.{json,md} carry an
    'emission-clamped' entry on tests/committed_artifact_guard.py's
    ALLOWLIST -- the same shape
    tests/test_129_coincident_centroids_and_held_out_floor.py's
    test_ac20_catalogue_regeneration_matches_committed_artifacts uses. Do
    not add any other byte-exact fresh-vs-committed float comparison to this
    module (item 130 Testing Strategy, AC22 note)."""
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"

    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()


# =========================================================================== #
# AC23: the catalogue's closest_u computation text stays true
# =========================================================================== #


def test_ac23_catalogue_closest_u_text_matches_shipped_constants():
    import inspect

    import segfacet.features.spline as spline_mod
    from segfacet.feature_docs import FEATURE_DOCS

    sig = inspect.signature(spline_mod.find_closest_point)
    n_scan_default = sig.parameters["n_scan"].default
    xatol_default = sig.parameters["xatol"].default
    assert n_scan_default == 500
    assert xatol_default == 1e-6

    doc = FEATURE_DOCS["stage3.per_label_offsets[].closest_u"]
    assert "500" in doc.computation
    assert "minimize_scalar" in doc.computation
    assert "1e-6" in doc.computation


# =========================================================================== #
# AC24: the search is deterministic and non-mutating
# =========================================================================== #


def test_ac24_deterministic_two_calls_equal():
    from segfacet.features.spline import find_closest_point

    centroids = _five_level_clean_spine()
    fit = fit_centroid_spline(centroids)
    query = np.array([5.0, -3.0, 40.0])

    r1 = find_closest_point(query, fit)
    r2 = find_closest_point(query, fit)

    assert r1 == r2


def test_ac24_query_array_not_mutated():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    query = np.array([1.0, 2.0, 25.0])
    before = query.copy()

    find_closest_point(query, fit)

    np.testing.assert_array_equal(query, before)


def test_ac24_leave_one_out_does_not_mutate_centroids():
    centroids = _five_level_clean_spine()
    before = [dataclasses.replace(c) for c in centroids]

    compute_leave_one_out_spline_offsets(centroids)

    assert centroids == before


# =========================================================================== #
# AC25: the decision document's measurements still reproduce
# =========================================================================== #


def test_ac25_test_118_non_verse_reproduction_stays_green(tmp_path):
    """Import test_118 (unmodified) and re-run its AC6 non-VerSe
    reproduction check directly, so a regression in the delegating script
    fails loudly under item 130's own module too (the pattern
    tests/test_119_curve_formulation.py's
    test_ac25_test_118_ac6_reproduction_stays_green uses)."""
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
# Adversarial / edge cases
# =========================================================================== #


def test_adversarial_query_point_on_curve_reads_near_zero_distance():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)
    on_curve_point = evaluate_spline(fit, [0.5])[0]

    result = find_closest_point(on_curve_point, fit)

    assert result.distance_mm < 1e-4


def test_adversarial_query_equidistant_from_two_curve_regions():
    from segfacet.features.spline import find_closest_point

    levels = ["T8", "T9", "T10", "T11", "T12"]
    xs = [0.0, 5.0, 0.0, -5.0, 0.0]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0]
    centroids = [_centroid(lv, (x, 0.0, z)) for lv, x, z in zip(levels, xs, zs)]
    fit = fit_centroid_spline(centroids)
    query = np.array([0.0, 0.0, 20.0])  # centre, on the axis of symmetry

    result = find_closest_point(query, fit)

    assert 0.0 <= result.closest_u <= 1.0
    recomputed_point = evaluate_spline(fit, [result.closest_u])[0]
    np.testing.assert_allclose(result.point_mm, recomputed_point, atol=1e-9)


def test_adversarial_query_beyond_start_clamps_to_zero():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)  # spans z = 0..50
    fit = fit_centroid_spline(centroids)

    result = find_closest_point(np.array([0.0, 0.0, -1000.0]), fit)

    assert result.closest_u == 0.0


def test_adversarial_query_beyond_end_clamps_to_one():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)  # spans z = 0..50
    fit = fit_centroid_spline(centroids)

    result = find_closest_point(np.array([0.0, 0.0, 1000.0]), fit)

    assert result.closest_u == 1.0


@pytest.mark.parametrize("n", [2, 3])
def test_adversarial_shortest_curves_return_valid_closest_point(n):
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(n)
    fit = fit_centroid_spline(centroids)

    result = find_closest_point(np.array([5.0, 0.0, 0.0]), fit)

    assert 0.0 <= result.closest_u <= 1.0
    assert math.isfinite(result.distance_mm)


def test_adversarial_n_scan_two_returns_finite_record():
    from segfacet.features.spline import find_closest_point

    centroids = _straight_spine(6)
    fit = fit_centroid_spline(centroids)

    result = find_closest_point(np.array([0.0, 0.0, 25.0]), fit, n_scan=2)

    assert math.isfinite(result.closest_u)
    assert math.isfinite(result.distance_mm)
    assert all(math.isfinite(v) for v in result.point_mm)


def test_adversarial_evaluator_wrong_shape_raises_readably():
    from segfacet.features.spline import find_closest_point

    def bad_evaluate(u_values):
        # returns (N,) instead of the required (N, 3)
        return np.asarray(u_values, dtype=np.float64)

    with pytest.raises((ValueError, IndexError)) as exc_info:
        find_closest_point(np.array([0.0, 0.0, 0.0]), bad_evaluate)
    assert str(exc_info.value).strip()


def test_adversarial_non_finite_evaluator_output_is_observable():
    from segfacet.features.spline import find_closest_point

    def nan_evaluate(u_values):
        u = np.asarray(u_values, dtype=np.float64)
        pts = np.column_stack([u, np.zeros_like(u), np.zeros_like(u)])
        pts[len(pts) // 2] = np.nan
        return pts

    try:
        result = find_closest_point(np.array([0.5, 0.0, 0.0]), nan_evaluate)
    except (ValueError, FloatingPointError) as exc:
        assert str(exc).strip()
    else:
        assert math.isnan(result.distance_mm) or math.isnan(result.closest_u)


def test_adversarial_fit_supplied_matches_standalone_four_level_fallback():
    centroids = _straight_spine(4)
    standalone = compute_leave_one_out_spline_offsets(centroids)
    fit = fit_centroid_spline(centroids)

    with_fit = compute_leave_one_out_spline_offsets(centroids, fit=fit)

    assert standalone == with_fit


def test_adversarial_fit_supplied_matches_standalone_six_level_held_out():
    centroids = _centroids_from_clean_spine(
        ("T1", "T2", "T3", "T4", "T5", "T6"), (1.0, 1.0, 1.0)
    )
    standalone = compute_leave_one_out_spline_offsets(centroids)
    fit = fit_centroid_spline(centroids)

    with_fit = compute_leave_one_out_spline_offsets(centroids, fit=fit)

    assert standalone == with_fit


def test_adversarial_extract_feature_record_determinism():
    seg_img = _clean_spine_seg_img(("L1", "L2", "L3", "L4", "L5"))

    r1 = extract_feature_record(seg_img, bundled_default_config())
    r2 = extract_feature_record(seg_img, bundled_default_config())

    assert r1["stage3"]["per_label_offsets"] == r2["stage3"]["per_label_offsets"]
    assert r1["stage3"]["monotonic_consistency"] == r2["stage3"]["monotonic_consistency"]
