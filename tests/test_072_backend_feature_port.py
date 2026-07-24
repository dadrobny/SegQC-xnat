"""Tests for porting Stage-2/3 geometric/topological features to the backend
abstraction (item 072).

Covers all 14 Acceptance Criteria from
``docs/aide/items/072-port-feature-extraction-to-backend.md`` plus the listed
adversarial/edge cases. Item 071's real GPU-less host means every GPU-selection
behaviour (AC6, AC7, AC8, adversarial fake-GPU checks) is exercised by
duck-typed fake ``Backend``/``ndimage``/``cupy`` objects -- never a real CuPy
install -- mirroring ``tests/test_071_backend.py``'s ``fake_cupy`` pattern.
Only the genuine-CuPy equivalence spot-check (AC12/AC13) is
``pytest.importorskip``-gated and is expected to skip on this host.

AC1 (the CPU-path regression guard) is proved by the validator running the
full pre-existing Stage-2/3 suite (test_011/012/013/017/018/023/025)
unmodified; this module additionally re-runs a representative fixture through
``compute_label_geometry`` and checks it against a hard-coded pre-port value.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no real GPU).
"""

from __future__ import annotations

import inspect
import types

import numpy as np
import pytest

import segfacet.backend as backend_mod
from segfacet.backend import ENV_VAR, get_backend, cupy_available
from segfacet.config import HeuristicConfig
from segfacet.features.centroids import (
    LabelCentroid,
    compute_centroid,
    compute_edt_centroids,
)
from segfacet.features.components import compute_components
from segfacet.features.fragmentation import compute_fragmentation_index
from segfacet.features.geometry import compute_label_geometry
from segfacet.features.spline import evaluate_spline, fit_centroid_spline
from segfacet.features.spline_offset import compute_spline_offsets

from synthetic import labelled_blocks_case

# Stable reference to the real get_backend, captured before any test installs
# a spy -- so repeated spy installs never chain onto a previous spy.
_REAL_GET_BACKEND = backend_mod.get_backend


# =========================================================================== #
# Helpers / fixtures
# =========================================================================== #


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Hermetic default: SEGFACET_BACKEND unset unless a test sets it."""
    monkeypatch.delenv(ENV_VAR, raising=False)


def _config(min_fragment_voxels: int = 0) -> HeuristicConfig:
    """Return a HeuristicConfig with the given fragment-voxel threshold."""
    return HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
        min_fragment_voxels=min_fragment_voxels,
    )


def _make_centroids(n: int = 5):
    """Return n LabelCentroid objects along a gentle curve (mm-coordinates)."""
    assert n >= 2
    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3"]
    xs = [0.0, 1.0, 2.5, 3.0, 2.5, 1.0, 0.5, 0.2]
    zs = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
    return [
        LabelCentroid(
            label=i + 1,
            level_name=levels[i % len(levels)],
            centroid_voxel=(float(i), 0.0, float(i) * 2.0),
            centroid_mm=(xs[i % len(xs)], 0.0, zs[i % len(zs)]),
        )
        for i in range(n)
    ]


def _install_get_backend_spy(monkeypatch):
    """Patch segfacet.backend.get_backend with a call-counting spy that still
    delegates to the real implementation, per AC3's testing-strategy bullet."""
    calls = {"count": 0}

    def spy(*args, **kwargs):
        calls["count"] += 1
        return _REAL_GET_BACKEND(*args, **kwargs)

    monkeypatch.setattr(backend_mod, "get_backend", spy)
    return calls


def _fake_gpu_backend():
    """A duck-typed fake-GPU Backend: is_gpu=True, xp/ndimage are fakes whose
    spline/ndimage entry points raise if ever touched -- proving the
    CPU-fallback path (AC8) never calls them."""

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "GPU entry point must not be called for the CPU-fallback path"
        )

    fake_cupy = types.ModuleType("fake_cupy")
    fake_cupy.splprep = _forbidden
    fake_cupy.splev = _forbidden
    fake_ndimage = types.SimpleNamespace(
        label=_forbidden,
        distance_transform_edt=_forbidden,
        gaussian_filter=_forbidden,
    )
    return types.SimpleNamespace(name="gpu", is_gpu=True, xp=fake_cupy, ndimage=fake_ndimage)


class _FakeDeviceArray:
    """Minimal stand-in for a device (e.g. CuPy) array: exposes both the
    CuPy-style ``.get()`` host-transfer method and ``__array__`` so whichever
    marshalling mechanism the port uses can convert it to host NumPy."""

    def __init__(self, values):
        self._arr = np.asarray(values, dtype=np.float64)

    def get(self):
        return self._arr

    def __array__(self, dtype=None):
        return self._arr if dtype is None else self._arr.astype(dtype)


def _load_pyproject():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open("pyproject.toml", "rb") as f:
        return tomllib.load(f)


# =========================================================================== #
# AC1  CPU-path regression guard (hard-coded pre-port meta-assertion)
# =========================================================================== #


def test_ac1_regression_guard_pre_port_hardcoded_value():
    """A representative fixture through compute_label_geometry matches the
    hard-coded pre-port value (64 voxels, 64.0 mm^3) -- the full pre-existing
    Stage-2/3 suite proves the rest of the CPU path is unchanged by running
    unmodified (validator's job, not a new test here)."""
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, label=1)
    assert result.voxel_count == 64
    assert result.physical_volume_mm3 == pytest.approx(64.0)


# =========================================================================== #
# AC2  backend keyword present, defaulting to None, on all eight functions
# =========================================================================== #


def test_ac2_all_ported_functions_have_backend_keyword_default_none():
    functions = [
        compute_label_geometry,
        compute_components,
        compute_centroid,
        compute_edt_centroids,
        compute_fragmentation_index,
        fit_centroid_spline,
        evaluate_spline,
        compute_spline_offsets,
    ]
    for fn in functions:
        sig = inspect.signature(fn)
        assert "backend" in sig.parameters, f"{fn.__name__} is missing a 'backend' parameter"
        param = sig.parameters["backend"]
        assert param.default is None, f"{fn.__name__}'s 'backend' parameter does not default to None"


# =========================================================================== #
# AC3  backend=None auto-resolves via get_backend(); explicit backend does not
# =========================================================================== #


def test_ac3_backend_none_consults_get_backend(monkeypatch):
    case = labelled_blocks_case()
    config = _config()
    centroids = _make_centroids(5)
    cpu = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=cpu)

    specs = [
        ("compute_label_geometry", compute_label_geometry, (case.seg_img, 1)),
        ("compute_components", compute_components, (case.seg_img, 1, config)),
        ("compute_centroid", compute_centroid, (case.seg_img, 1)),
        ("compute_edt_centroids", compute_edt_centroids, (case.seg_img, 1)),
        ("compute_fragmentation_index", compute_fragmentation_index, (case.seg_img, 1, config)),
        ("fit_centroid_spline", fit_centroid_spline, (centroids,)),
        ("evaluate_spline", evaluate_spline, (fit, [0.0, 0.5, 1.0])),
        ("compute_spline_offsets", compute_spline_offsets, (centroids, fit)),
    ]
    for name, fn, args in specs:
        calls = _install_get_backend_spy(monkeypatch)
        fn(*args, backend=None)
        assert calls["count"] >= 1, f"{name}(backend=None) did not consult get_backend()"


def test_ac3_explicit_backend_does_not_consult_get_backend(monkeypatch):
    case = labelled_blocks_case()
    config = _config()
    centroids = _make_centroids(5)
    cpu = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=cpu)

    specs = [
        ("compute_label_geometry", compute_label_geometry, (case.seg_img, 1)),
        ("compute_components", compute_components, (case.seg_img, 1, config)),
        ("compute_centroid", compute_centroid, (case.seg_img, 1)),
        ("compute_edt_centroids", compute_edt_centroids, (case.seg_img, 1)),
        ("compute_fragmentation_index", compute_fragmentation_index, (case.seg_img, 1, config)),
        ("fit_centroid_spline", fit_centroid_spline, (centroids,)),
        ("evaluate_spline", evaluate_spline, (fit, [0.0, 0.5, 1.0])),
        ("compute_spline_offsets", compute_spline_offsets, (centroids, fit)),
    ]
    for name, fn, args in specs:
        calls = _install_get_backend_spy(monkeypatch)
        fn(*args, backend=cpu)
        assert calls["count"] == 0, f"{name}(backend=<explicit cpu>) consulted get_backend()"


# =========================================================================== #
# AC4  Explicit CPU backend equals the backend=None default on this host
# =========================================================================== #


def test_ac4_geometry_explicit_cpu_equals_default():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    assert compute_label_geometry(case.seg_img, 1, backend=None) == compute_label_geometry(
        case.seg_img, 1, backend=cpu
    )


def test_ac4_components_explicit_cpu_equals_default():
    case = labelled_blocks_case()
    config = _config()
    cpu = get_backend(override="cpu")
    assert compute_components(case.seg_img, 1, config, backend=None) == compute_components(
        case.seg_img, 1, config, backend=cpu
    )


def test_ac4_centroid_explicit_cpu_equals_default():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    assert compute_centroid(case.seg_img, 1, backend=None) == compute_centroid(
        case.seg_img, 1, backend=cpu
    )


def test_ac4_edt_centroids_explicit_cpu_equals_default():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    assert compute_edt_centroids(case.seg_img, 1, backend=None) == compute_edt_centroids(
        case.seg_img, 1, backend=cpu
    )


def test_ac4_fragmentation_explicit_cpu_equals_default():
    case = labelled_blocks_case()
    config = _config()
    cpu = get_backend(override="cpu")
    default = compute_fragmentation_index(case.seg_img, 1, config, backend=None)
    explicit = compute_fragmentation_index(case.seg_img, 1, config, backend=cpu)
    assert default == pytest.approx(explicit)


def test_ac4_spline_fit_and_evaluate_explicit_cpu_equals_default():
    centroids = _make_centroids(5)
    cpu = get_backend(override="cpu")
    fit_default = fit_centroid_spline(centroids, backend=None)
    fit_cpu = fit_centroid_spline(centroids, backend=cpu)
    assert fit_default.degree == fit_cpu.degree
    assert fit_default.n_points == fit_cpu.n_points
    assert fit_default.u == fit_cpu.u

    u_values = [0.0, 0.25, 0.5, 0.75, 1.0]
    pts_default = evaluate_spline(fit_default, u_values, backend=None)
    pts_cpu = evaluate_spline(fit_cpu, u_values, backend=cpu)
    assert np.array_equal(pts_default, pts_cpu)


def test_ac4_spline_offsets_explicit_cpu_equals_default():
    centroids = _make_centroids(5)
    cpu = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=cpu)
    default = compute_spline_offsets(centroids, fit, backend=None)
    explicit = compute_spline_offsets(centroids, fit, backend=cpu)
    assert default == explicit


# =========================================================================== #
# AC5  Backend.ndimage accessor exists (CPU) and wraps scipy.ndimage
# =========================================================================== #


def test_ac5_cpu_ndimage_functions_are_callable():
    cpu = get_backend(override="cpu")
    assert hasattr(cpu, "ndimage")
    assert callable(cpu.ndimage.label)
    assert callable(cpu.ndimage.distance_transform_edt)
    assert callable(cpu.ndimage.gaussian_filter)


def test_ac5_cpu_ndimage_label_matches_scipy():
    import scipy.ndimage as scipy_ndimage

    cpu = get_backend(override="cpu")
    mask = np.zeros((4, 4, 4), dtype=bool)
    mask[1, 1, 1] = True
    mask[3, 3, 3] = True
    labelled_a, n_a = cpu.ndimage.label(mask)
    labelled_b, n_b = scipy_ndimage.label(mask)
    assert n_a == n_b
    np.testing.assert_array_equal(labelled_a, labelled_b)


def test_ac5_cpu_ndimage_distance_transform_edt_matches_scipy():
    import scipy.ndimage as scipy_ndimage

    cpu = get_backend(override="cpu")
    mask = np.ones((5, 5, 5), dtype=bool)
    mask[2, 2, 2] = False
    edt_a = cpu.ndimage.distance_transform_edt(mask)
    edt_b = scipy_ndimage.distance_transform_edt(mask)
    np.testing.assert_array_equal(edt_a, edt_b)


def test_ac5_cpu_ndimage_gaussian_filter_matches_scipy():
    import scipy.ndimage as scipy_ndimage

    cpu = get_backend(override="cpu")
    arr = np.random.RandomState(0).rand(6, 6, 6)
    out_a = cpu.ndimage.gaussian_filter(arr, sigma=1.0)
    out_b = scipy_ndimage.gaussian_filter(arr, sigma=1.0)
    np.testing.assert_array_equal(out_a, out_b)


# =========================================================================== #
# AC6  compute_components labels via Backend.ndimage
# =========================================================================== #


def test_ac6_compute_components_routes_label_through_backend_ndimage():
    import scipy.ndimage as scipy_ndimage

    calls = {"count": 0}

    def label_spy(*args, **kwargs):
        calls["count"] += 1
        return scipy_ndimage.label(*args, **kwargs)

    fake_ndimage = types.SimpleNamespace(
        label=label_spy,
        distance_transform_edt=scipy_ndimage.distance_transform_edt,
        gaussian_filter=scipy_ndimage.gaussian_filter,
    )
    fake_backend = types.SimpleNamespace(name="cpu", is_gpu=False, xp=np, ndimage=fake_ndimage)

    case = labelled_blocks_case()
    config = _config()
    result = fake_backend and compute_components(case.seg_img, 1, config, backend=fake_backend)
    direct = compute_components(case.seg_img, 1, config, backend=get_backend(override="cpu"))

    assert calls["count"] >= 1, "compute_components did not call backend.ndimage.label"
    assert result == direct


# =========================================================================== #
# AC7  compute_edt_centroids routes EDT + smoothing via Backend.ndimage
# =========================================================================== #


def test_ac7_compute_edt_centroids_routes_edt_and_gaussian_through_backend_ndimage():
    import scipy.ndimage as scipy_ndimage

    calls = {"edt": 0, "gaussian": 0}

    def edt_spy(*args, **kwargs):
        calls["edt"] += 1
        return scipy_ndimage.distance_transform_edt(*args, **kwargs)

    def gaussian_spy(*args, **kwargs):
        calls["gaussian"] += 1
        return scipy_ndimage.gaussian_filter(*args, **kwargs)

    fake_ndimage = types.SimpleNamespace(
        label=scipy_ndimage.label,
        distance_transform_edt=edt_spy,
        gaussian_filter=gaussian_spy,
    )
    fake_backend = types.SimpleNamespace(name="cpu", is_gpu=False, xp=np, ndimage=fake_ndimage)

    case = labelled_blocks_case()
    result = compute_edt_centroids(case.seg_img, 1, backend=fake_backend)
    direct = compute_edt_centroids(case.seg_img, 1, backend=get_backend(override="cpu"))

    assert calls["edt"] >= 1, "compute_edt_centroids did not call backend.ndimage.distance_transform_edt"
    assert calls["gaussian"] >= 1, "compute_edt_centroids did not call backend.ndimage.gaussian_filter"
    assert result == direct


# =========================================================================== #
# AC8  Spline steps run on CPU even under an explicit GPU backend
# =========================================================================== #


def test_ac8_spline_functions_stay_on_cpu_under_gpu_backend():
    gpu_backend = _fake_gpu_backend()
    cpu_backend = get_backend(override="cpu")
    centroids = _make_centroids(5)

    fit_gpu = fit_centroid_spline(centroids, backend=gpu_backend)
    fit_cpu = fit_centroid_spline(centroids, backend=cpu_backend)
    assert fit_gpu.degree == fit_cpu.degree
    assert fit_gpu.u == fit_cpu.u

    u_values = [0.0, 0.3, 0.7, 1.0]
    pts_gpu = evaluate_spline(fit_gpu, u_values, backend=gpu_backend)
    pts_cpu = evaluate_spline(fit_cpu, u_values, backend=cpu_backend)
    assert isinstance(pts_gpu, np.ndarray)
    assert type(pts_gpu).__module__.startswith("numpy")
    assert np.array_equal(pts_gpu, pts_cpu)

    offsets_gpu = compute_spline_offsets(centroids, fit_gpu, backend=gpu_backend)
    offsets_cpu = compute_spline_offsets(centroids, fit_cpu, backend=cpu_backend)
    assert offsets_gpu == offsets_cpu


# =========================================================================== #
# AC9  Spline CPU fallback documented in module docstrings
# =========================================================================== #


def test_ac9_spline_module_docstring_documents_cpu_fallback():
    import segfacet.features.spline as spline_mod

    doc = (spline_mod.__doc__ or "").lower()
    assert "cpu" in doc, "spline.py module docstring does not mention CPU"
    assert "fallback" in doc, "spline.py module docstring does not document the CPU fallback"


def test_ac9_spline_offset_module_docstring_documents_cpu_fallback():
    import segfacet.features.spline_offset as spline_offset_mod

    doc = (spline_offset_mod.__doc__ or "").lower()
    assert "cpu" in doc, "spline_offset.py module docstring does not mention CPU"
    assert "fallback" in doc, "spline_offset.py module docstring does not document the CPU fallback"


# =========================================================================== #
# AC10  backend threads transitively through wrappers
# =========================================================================== #


def test_ac10_fragmentation_index_forwards_backend_to_compute_components(monkeypatch):
    import segfacet.features.components as components_mod

    real_compute_components = components_mod.compute_components
    received = {}

    def spy(*args, **kwargs):
        received["backend"] = kwargs.get("backend")
        return real_compute_components(*args, **kwargs)

    monkeypatch.setattr(components_mod, "compute_components", spy)

    case = labelled_blocks_case()
    config = _config()
    sentinel_backend = get_backend(override="cpu")
    compute_fragmentation_index(case.seg_img, 1, config, backend=sentinel_backend)

    assert received.get("backend") is sentinel_backend


def test_ac10_spline_offsets_forwards_backend_to_evaluate_spline(monkeypatch):
    import segfacet.features.spline_offset as spline_offset_mod

    real_evaluate_spline = spline_offset_mod.evaluate_spline
    received = []

    def spy(fit, u_values, **kwargs):
        received.append(kwargs.get("backend"))
        return real_evaluate_spline(fit, u_values, **kwargs)

    monkeypatch.setattr(spline_offset_mod, "evaluate_spline", spy)

    centroids = _make_centroids(5)
    sentinel_backend = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=sentinel_backend)
    compute_spline_offsets(centroids, fit, backend=sentinel_backend)

    assert len(received) > 0, "compute_spline_offsets never called evaluate_spline"
    assert sentinel_backend in received, "compute_spline_offsets did not forward its backend to evaluate_spline"


# =========================================================================== #
# AC11  Read-only and deterministic under the CPU backend
# =========================================================================== #


def test_ac11_geometry_deterministic_and_read_only():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    original = np.asanyarray(case.seg_img.dataobj).copy()
    r1 = compute_label_geometry(case.seg_img, 1, backend=cpu)
    r2 = compute_label_geometry(case.seg_img, 1, backend=cpu)
    assert r1 == r2
    np.testing.assert_array_equal(original, np.asanyarray(case.seg_img.dataobj))


def test_ac11_components_deterministic_and_read_only():
    case = labelled_blocks_case()
    config = _config()
    cpu = get_backend(override="cpu")
    original = np.asanyarray(case.seg_img.dataobj).copy()
    r1 = compute_components(case.seg_img, 1, config, backend=cpu)
    r2 = compute_components(case.seg_img, 1, config, backend=cpu)
    assert r1 == r2
    np.testing.assert_array_equal(original, np.asanyarray(case.seg_img.dataobj))


def test_ac11_centroid_deterministic_and_read_only():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    original = np.asanyarray(case.seg_img.dataobj).copy()
    r1 = compute_centroid(case.seg_img, 1, backend=cpu)
    r2 = compute_centroid(case.seg_img, 1, backend=cpu)
    assert r1 == r2
    np.testing.assert_array_equal(original, np.asanyarray(case.seg_img.dataobj))


def test_ac11_edt_centroids_deterministic_and_read_only():
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    original = np.asanyarray(case.seg_img.dataobj).copy()
    r1 = compute_edt_centroids(case.seg_img, 1, backend=cpu)
    r2 = compute_edt_centroids(case.seg_img, 1, backend=cpu)
    assert r1 == r2
    np.testing.assert_array_equal(original, np.asanyarray(case.seg_img.dataobj))


def test_ac11_fragmentation_deterministic_and_read_only():
    case = labelled_blocks_case()
    config = _config()
    cpu = get_backend(override="cpu")
    original = np.asanyarray(case.seg_img.dataobj).copy()
    r1 = compute_fragmentation_index(case.seg_img, 1, config, backend=cpu)
    r2 = compute_fragmentation_index(case.seg_img, 1, config, backend=cpu)
    assert r1 == pytest.approx(r2)
    np.testing.assert_array_equal(original, np.asanyarray(case.seg_img.dataobj))


def test_ac11_spline_fit_deterministic_and_input_not_mutated():
    centroids = _make_centroids(5)
    before = list(centroids)
    cpu = get_backend(override="cpu")
    fit1 = fit_centroid_spline(centroids, backend=cpu)
    fit2 = fit_centroid_spline(centroids, backend=cpu)
    assert fit1.degree == fit2.degree
    assert fit1.u == fit2.u
    assert centroids == before


def test_ac11_spline_offsets_deterministic_and_input_not_mutated():
    centroids = _make_centroids(5)
    before = list(centroids)
    cpu = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=cpu)
    r1 = compute_spline_offsets(centroids, fit, backend=cpu)
    r2 = compute_spline_offsets(centroids, fit, backend=cpu)
    assert r1 == r2
    assert centroids == before


# =========================================================================== #
# AC12 / AC13  GPU-gated equivalence spot-check
# =========================================================================== #


def test_ac12_cupy_genuinely_absent_on_this_host():
    """Non-vacuous check: this host truly lacks cupy, so the guarded
    equivalence spot-check below genuinely skips rather than vacuously
    passing."""
    if cupy_available():
        pytest.skip("This test targets a CuPy-absent host only.")
    assert cupy_available() is False


def test_ac12_ac13_gpu_cpu_equivalence_spot_check():
    """AC12: skips cleanly (via pytest.importorskip) when cupy is absent --
    the state of this host. AC13: when cupy IS importable, compares
    physical_volume_mm3 and a smooth-centre centroid variant between the CPU
    and GPU backends, asserting agreement within rtol=1e-5, atol=1e-8
    (documented tolerance acknowledging NumPy-vs-CuPy floating-point drift)."""
    pytest.importorskip("cupy")

    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    gpu = get_backend(override="gpu")

    geom_cpu = compute_label_geometry(case.seg_img, 1, backend=cpu)
    geom_gpu = compute_label_geometry(case.seg_img, 1, backend=gpu)
    assert geom_cpu.physical_volume_mm3 == pytest.approx(
        geom_gpu.physical_volume_mm3, rel=1e-5, abs=1e-8
    )

    edt_cpu = compute_edt_centroids(case.seg_img, 1, backend=cpu)
    edt_gpu = compute_edt_centroids(case.seg_img, 1, backend=gpu)
    for i in range(3):
        assert edt_cpu.smooth_centre_mm[i] == pytest.approx(
            edt_gpu.smooth_centre_mm[i], rel=1e-5, abs=1e-8
        )


# =========================================================================== #
# AC14  No cucim dependency introduced
# =========================================================================== #


def test_ac14_no_cucim_anywhere_in_pyproject():
    data = _load_pyproject()
    assert "cucim" not in str(data).lower()


def test_ac14_core_dependencies_unchanged_no_new_gpu_dep():
    data = _load_pyproject()
    core_deps = " ".join(data["project"].get("dependencies", [])).lower()
    assert "cupy" not in core_deps
    assert "cucim" not in core_deps


def test_ac14_gpu_extra_lists_cupy_only():
    data = _load_pyproject()
    optional = data["project"].get("optional-dependencies", {})
    assert "gpu" in optional, "expected a `gpu` optional extra"
    gpu_extra = [dep.lower() for dep in optional["gpu"]]
    assert any("cupy" in dep for dep in gpu_extra)
    assert not any("cucim" in dep for dep in gpu_extra)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_missing_label_raises_value_error_through_backend_path():
    """Empty/degenerate label still raises ValueError, unchanged, through the
    backend path -- for both backend=None (auto-resolve) and an explicit CPU
    backend."""
    case = labelled_blocks_case()
    cpu = get_backend(override="cpu")
    config = _config()

    for backend in (None, cpu):
        with pytest.raises(ValueError):
            compute_label_geometry(case.seg_img, 999, backend=backend)
        with pytest.raises(ValueError):
            compute_centroid(case.seg_img, 999, backend=backend)
        with pytest.raises(ValueError):
            compute_components(case.seg_img, 999, config, backend=backend)
        with pytest.raises(ValueError):
            compute_edt_centroids(case.seg_img, 999, backend=backend)


def test_adv_two_centroid_spline_degree_clamp_under_gpu_backend():
    """A 2-centroid spline (degree clamped to 1) under an explicit GPU
    backend still CPU-falls-back correctly and returns finite host results."""
    gpu_backend = _fake_gpu_backend()
    centroids = _make_centroids(2)
    fit = fit_centroid_spline(centroids, backend=gpu_backend)
    assert fit.degree == 1
    pts = evaluate_spline(fit, [0.0, 1.0], backend=gpu_backend)
    assert isinstance(pts, np.ndarray)
    assert pts.shape == (2, 3)
    assert np.all(np.isfinite(pts))


def test_adv_env_var_cpu_used_when_backend_none(monkeypatch):
    """SEGFACET_BACKEND=cpu set in the environment while calling backend=None
    (the default) resolves to CPU, matching an explicit CPU backend call."""
    monkeypatch.setenv(ENV_VAR, "cpu")
    case = labelled_blocks_case()
    result = compute_label_geometry(case.seg_img, 1, backend=None)
    expected = compute_label_geometry(case.seg_img, 1, backend=get_backend(override="cpu"))
    assert result == expected


def test_adv_device_array_input_marshalled_to_host_for_evaluate_spline():
    """A device-array-like input (exposing both .get() and __array__, as a
    CuPy array would) to evaluate_spline is marshalled to host NumPy without
    error and yields finite results."""
    centroids = _make_centroids(4)
    cpu = get_backend(override="cpu")
    fit = fit_centroid_spline(centroids, backend=cpu)
    device_u = _FakeDeviceArray([0.0, 0.5, 1.0])
    pts = evaluate_spline(fit, device_u, backend=cpu)
    assert isinstance(pts, np.ndarray)
    assert pts.shape == (3, 3)
    assert np.all(np.isfinite(pts))


def test_adv_fake_gpu_backend_genuinely_differs_from_cpu():
    """Confirms the fake-GPU Backend used in AC8/adversarial tests genuinely
    differs from the CPU backend (its xp/ndimage are the fakes), so AC8's
    "never touched" assertion is not vacuous."""
    gpu_backend = _fake_gpu_backend()
    cpu_backend = get_backend(override="cpu")
    assert gpu_backend.xp is not cpu_backend.xp
    assert gpu_backend.ndimage is not cpu_backend.ndimage
    assert gpu_backend.is_gpu is True
    assert cpu_backend.is_gpu is False
