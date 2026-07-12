"""Tests for the optional PyRadiomics adapter (item 060).

Covers all 14 Acceptance Criteria plus adversarial/edge-case inputs. The
**normal, designed-for case is PyRadiomics absent** -- the bulk of these
tests exercise the builtin (degraded) path and must pass in the default
dev/CI environment. Present-path tests (AC12/AC13/AC14) are guarded by
``pytest.importorskip("radiomics")`` so they skip cleanly when PyRadiomics
is not installed, and only run/verify behaviour when it happens to be.

All tests build tiny in-memory ``Nifti1Image`` scan+seg pairs (diagonal
affines, hand-known voxel values), mirroring the house style of
``tests/test_features_intensity.py`` (item 059), whose
``compute_label_intensity`` this adapter wraps verbatim for its
``first_order`` block.

All tests are deterministic, CPU-only, and portable (no network, no
absolute paths, no services).
"""

from __future__ import annotations

import dataclasses

import nibabel as nib
import numpy as np
import pytest

from segqc.features.intensity import LabelIntensity, compute_label_intensity
from segqc.features.radiomics import (
    LabelRadiomics,
    compute_label_radiomics,
    compute_radiomics_features,
    pyradiomics_available,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

_VALUES = [10.0, 20.0, 20.0, 30.0, 40.0, 50.0, 50.0, 90.0]


def _affine(spacing=(1.0, 1.0, 1.0)):
    sx, sy, sz = (float(s) for s in spacing)
    return np.diag([sx, sy, sz, 1.0]).astype(np.float64)


def _scan_img(data, spacing=(1.0, 1.0, 1.0)):
    return nib.Nifti1Image(np.asarray(data, dtype=np.float64), _affine(spacing))


def _seg_img(data, spacing=(1.0, 1.0, 1.0)):
    return nib.Nifti1Image(np.asarray(data, dtype=np.uint16), _affine(spacing))


def _known_values_case(spacing=(1.0, 1.0, 1.0)):
    """A (1,1,8) volume, label 1 covering all 8 voxels with :data:`_VALUES`."""
    n = len(_VALUES)
    seg_data = np.ones((1, 1, n), dtype=np.uint16)
    scan_data = np.array(_VALUES, dtype=np.float64).reshape(1, 1, n)
    return _scan_img(scan_data), _seg_img(seg_data)


def _two_label_case():
    seg_data = np.zeros((6, 6, 6), dtype=np.uint16)
    seg_data[0:2, 0:2, 0:2] = 1
    seg_data[3:5, 3:5, 3:5] = 2
    scan_data = np.arange(6 * 6 * 6, dtype=np.float64).reshape(6, 6, 6)
    return _scan_img(scan_data), _seg_img(seg_data)


def _blob_case_for_present_path():
    """A small solid cube label -- enough voxels for GLCM/shape extraction
    to succeed on the present (PyRadiomics) path."""
    seg_data = np.zeros((8, 8, 8), dtype=np.uint16)
    seg_data[2:6, 2:6, 2:6] = 1
    scan_data = np.zeros((8, 8, 8), dtype=np.float64)
    rng_values = np.linspace(0.0, 100.0, num=4 * 4 * 4).reshape(4, 4, 4)
    scan_data[2:6, 2:6, 2:6] = rng_values
    return _scan_img(scan_data), _seg_img(seg_data)


# =========================================================================== #
# AC1  Module & guarded optional import
# =========================================================================== #

def test_ac1_module_imports_without_pyradiomics():
    """Importing segqc.features.radiomics raises nothing (PyRadiomics may
    be absent in this environment)."""
    import importlib

    mod = importlib.import_module("segqc.features.radiomics")
    assert mod is not None


def test_ac1_public_api_names_present():
    """The four public names + __all__ are exposed."""
    import segqc.features.radiomics as mod

    for name in ("pyradiomics_available", "LabelRadiomics",
                 "compute_label_radiomics", "compute_radiomics_features"):
        assert hasattr(mod, name), name
        assert name in mod.__all__


def test_ac1_public_callables_are_callable():
    assert callable(pyradiomics_available)
    assert callable(compute_label_radiomics)
    assert callable(compute_radiomics_features)


# =========================================================================== #
# AC2  Capability probe
# =========================================================================== #

def test_ac2_pyradiomics_available_returns_bool_and_does_not_raise():
    """pyradiomics_available() returns a bool and never raises."""
    result = pyradiomics_available()
    assert isinstance(result, bool)


def test_ac2_pyradiomics_available_reflects_environment():
    """In this dev/CI environment PyRadiomics is (as of writing) absent, so
    the probe returns False; if it happens to be installed it returns True.
    Either way it must agree with a direct import attempt."""
    try:
        import radiomics  # noqa: F401
        expected = True
    except ImportError:
        expected = False
    assert pyradiomics_available() is expected


# =========================================================================== #
# AC3  Normalised per-label result shape
# =========================================================================== #

def test_ac3_label_radiomics_is_frozen_dataclass_with_documented_fields():
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1)
    assert dataclasses.is_dataclass(result)
    field_names = {f.name for f in dataclasses.fields(result)}
    assert field_names == {"first_order", "extended", "backend", "radiomics_available"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.backend = "other"  # type: ignore[misc]


def test_ac3_field_types_are_json_friendly():
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1)
    assert isinstance(result.first_order, LabelIntensity)
    assert isinstance(result.extended, dict)
    assert isinstance(result.backend, str)
    assert isinstance(result.radiomics_available, bool)


def test_ac3_comparable_with_equality():
    scan_img, seg_img = _known_values_case()
    r1 = compute_label_radiomics(scan_img, seg_img, label=1)
    r2 = compute_label_radiomics(scan_img, seg_img, label=1)
    assert r1 == r2


# =========================================================================== #
# AC4  First-order is authoritative & backend-independent (absent path)
# =========================================================================== #

def test_ac4_first_order_equals_item059_direct_call():
    scan_img, seg_img = _two_label_case()
    for label in (1, 2):
        result = compute_label_radiomics(scan_img, seg_img, label=label)
        assert result.first_order == compute_label_intensity(scan_img, seg_img, label)


# =========================================================================== #
# AC5  Graceful degradation when absent (NORMAL case)
# =========================================================================== #

def test_ac5_absent_path_yields_builtin_markers_and_no_exception():
    """With PyRadiomics not importable (the normal env), the result carries
    the builtin markers and no exception is raised."""
    if pyradiomics_available():
        pytest.skip("PyRadiomics happens to be installed; covered by AC6 disable test instead")
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1)
    assert result.extended == {}
    assert result.backend == "builtin"
    assert result.radiomics_available is False
    assert result.first_order.voxel_count > 0


# =========================================================================== #
# AC6  Explicit disable seam
# =========================================================================== #

def test_ac6_enable_pyradiomics_false_forces_builtin_path():
    """enable_pyradiomics=False forces the builtin path regardless of
    whether PyRadiomics happens to be installed."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=False)
    assert result.extended == {}
    assert result.backend == "builtin"
    assert result.radiomics_available is False


def test_ac6_disable_seam_first_order_still_populated():
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=False)
    assert result.first_order == compute_label_intensity(scan_img, seg_img, label=1)


# =========================================================================== #
# AC7  No hard dependency
# =========================================================================== #

def test_ac7_core_imports_succeed_without_pyradiomics():
    """segqc, segqc.features, and segqc.features.radiomics all import
    cleanly (PyRadiomics is not required for the core package to load)."""
    import importlib

    for module_name in ("segqc", "segqc.features", "segqc.features.radiomics"):
        mod = importlib.import_module(module_name)
        assert mod is not None


def test_ac7_pyradiomics_declared_as_optional_extra_not_core_dependency():
    """pyproject.toml declares pyradiomics only under the `radiomics`
    optional extra, not in core [project] dependencies."""
    try:
        import tomllib  # Python 3.11+
        with open("pyproject.toml", "rb") as f:
            data = tomllib.load(f)
    except ModuleNotFoundError:
        try:
            import tomli
        except ModuleNotFoundError:
            pytest.skip("no TOML parser available (tomllib/tomli) to structurally verify pyproject.toml")
        with open("pyproject.toml", "rb") as f:
            data = tomli.load(f)

    project = data["project"]
    core_deps = " ".join(project.get("dependencies", [])).lower()
    assert "pyradiomics" not in core_deps

    optional = project.get("optional-dependencies", {})
    assert "radiomics" in optional, "expected a `radiomics` optional extra"
    radiomics_extra = " ".join(optional["radiomics"]).lower()
    assert "pyradiomics" in radiomics_extra


# =========================================================================== #
# AC8  Per-case convenience map
# =========================================================================== #

def test_ac8_compute_radiomics_features_keys_match_present_labels():
    scan_img, seg_img = _two_label_case()
    features = compute_radiomics_features(scan_img, seg_img)
    assert set(features.keys()) == {1, 2}


def test_ac8_compute_radiomics_features_values_match_single_label_calls():
    scan_img, seg_img = _two_label_case()
    features = compute_radiomics_features(scan_img, seg_img)
    for label in (1, 2):
        assert features[label] == compute_label_radiomics(scan_img, seg_img, label)


def test_ac8_background_label_excluded():
    seg_data = np.zeros((4, 4, 4), dtype=np.uint16)
    seg_data[0:2, 0:2, 0:2] = 1
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    features = compute_radiomics_features(scan_img, seg_img)
    assert 0 not in features


# =========================================================================== #
# AC9  Grid-alignment guard
# =========================================================================== #

def test_ac9_shape_mismatch_raises_value_error_on_builtin_path():
    seg_data = np.ones((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 5), dtype=np.float64)
    scan_img = _scan_img(scan_data)
    seg_img = _seg_img(seg_data)
    with pytest.raises(ValueError):
        compute_label_radiomics(scan_img, seg_img, label=1)


def test_ac9_affine_mismatch_raises_value_error_on_builtin_path():
    seg_data = np.ones((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    seg_img = _seg_img(seg_data, spacing=(1.0, 1.0, 1.0))
    scan_img = _scan_img(scan_data, spacing=(2.0, 2.0, 2.0))
    with pytest.raises(ValueError):
        compute_label_radiomics(scan_img, seg_img, label=1)


def test_ac9_shape_mismatch_raises_with_pyradiomics_enabled_too():
    """The guard fires before any PyRadiomics work is attempted, so it also
    raises when enable_pyradiomics=True (whether or not PyRadiomics is
    actually installed)."""
    seg_data = np.ones((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 5), dtype=np.float64)
    scan_img = _scan_img(scan_data)
    seg_img = _seg_img(seg_data)
    with pytest.raises(ValueError):
        compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)


def test_ac9_aligned_inputs_do_not_raise():
    scan_img, seg_img = _known_values_case()
    compute_label_radiomics(scan_img, seg_img, label=1)  # must not raise


# =========================================================================== #
# AC10  Empty / absent-label handling
# =========================================================================== #

def test_ac10_absent_label_returns_sentinel_first_order_and_empty_extended():
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=999)
    assert result.first_order.voxel_count == 0
    assert result.extended == {}


def test_ac10_all_background_mask_returns_sentinel_no_exception():
    seg_data = np.zeros((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    result = compute_label_radiomics(scan_img, seg_img, label=1)
    assert result.first_order.voxel_count == 0
    assert result.extended == {}


def test_ac10_empty_label_holds_with_pyradiomics_enabled_too():
    """Even with enable_pyradiomics=True, an empty label must not reach the
    PyRadiomics wrapper (which would error on a zero-voxel mask)."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=999, enable_pyradiomics=True)
    assert result.first_order.voxel_count == 0
    assert result.extended == {}


# =========================================================================== #
# AC11  Determinism & purity (absent path)
# =========================================================================== #

def test_ac11_determinism_repeated_calls_equal():
    scan_img, seg_img = _known_values_case()
    r1 = compute_label_radiomics(scan_img, seg_img, label=1)
    r2 = compute_label_radiomics(scan_img, seg_img, label=1)
    assert r1 == r2


def test_ac11_determinism_per_case_convenience():
    scan_img, seg_img = _two_label_case()
    f1 = compute_radiomics_features(scan_img, seg_img)
    f2 = compute_radiomics_features(scan_img, seg_img)
    assert f1 == f2


def test_ac11_compute_label_radiomics_does_not_mutate_inputs():
    scan_img, seg_img = _known_values_case()
    scan_before = np.asanyarray(scan_img.dataobj).copy()
    seg_before = np.asanyarray(seg_img.dataobj).copy()
    compute_label_radiomics(scan_img, seg_img, label=1)
    np.testing.assert_array_equal(np.asanyarray(scan_img.dataobj), scan_before)
    np.testing.assert_array_equal(np.asanyarray(seg_img.dataobj), seg_before)


def test_ac11_compute_radiomics_features_does_not_mutate_inputs():
    scan_img, seg_img = _two_label_case()
    scan_before = np.asanyarray(scan_img.dataobj).copy()
    seg_before = np.asanyarray(seg_img.dataobj).copy()
    compute_radiomics_features(scan_img, seg_img)
    np.testing.assert_array_equal(np.asanyarray(scan_img.dataobj), scan_before)
    np.testing.assert_array_equal(np.asanyarray(seg_img.dataobj), seg_before)


# =========================================================================== #
# AC12/AC13/AC14  Present path (skippable)
# =========================================================================== #

class TestPresentPath:
    """Guarded by pytest.importorskip("radiomics"); skips cleanly when
    PyRadiomics is not installed (the normal dev/CI case)."""

    @pytest.fixture(autouse=True)
    def _require_radiomics(self):
        pytest.importorskip("radiomics")

    def test_ac12_extended_is_nonempty_documented_glcm_shape_subset(self):
        scan_img, seg_img = _blob_case_for_present_path()
        result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        assert isinstance(result.extended, dict)
        assert result.extended, "extended must be non-empty when PyRadiomics is present"
        for key, value in result.extended.items():
            assert isinstance(key, str)
            assert isinstance(value, float)
            assert np.isfinite(value), (key, value)
        # documented families: GLCM + shape (per module docstring)
        lowered_keys = " ".join(result.extended.keys()).lower()
        assert "glcm" in lowered_keys
        assert "shape" in lowered_keys

    def test_ac13_present_path_backend_and_availability_markers(self):
        scan_img, seg_img = _blob_case_for_present_path()
        result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        assert result.backend == "pyradiomics"
        assert result.radiomics_available is True

    def test_ac13_present_path_first_order_invariance(self):
        """Installing/enabling PyRadiomics does not change first_order."""
        scan_img, seg_img = _blob_case_for_present_path()
        result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        assert result.first_order == compute_label_intensity(scan_img, seg_img, label=1)

    def test_ac14_present_path_determinism(self):
        scan_img, seg_img = _blob_case_for_present_path()
        r1 = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        r2 = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        assert r1.extended == r2.extended

    def test_adv_single_voxel_label_present_path_does_not_crash(self):
        """A degenerate single-voxel label on the present path: PyRadiomics
        may legitimately fail to compute some GLCM features on a 1-voxel
        mask, but the call itself must not raise, backend/availability
        markers must still be consistent, and first_order must be exact."""
        seg_data = np.zeros((5, 5, 5), dtype=np.uint16)
        seg_data[2, 2, 2] = 1
        scan_data = np.zeros((5, 5, 5), dtype=np.float64)
        scan_data[2, 2, 2] = 77.0
        scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
        result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
        assert result.first_order == compute_label_intensity(scan_img, seg_img, label=1)
        assert result.first_order.voxel_count == 1


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #

def test_adv_enable_true_with_pyradiomics_absent_still_degrades_cleanly():
    """enable_pyradiomics=True with PyRadiomics genuinely absent must not
    attempt to import a missing library mid-call -- it degrades to the
    builtin path exactly like the default."""
    if pyradiomics_available():
        pytest.skip("PyRadiomics happens to be installed in this environment")
    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=True)
    assert result.extended == {}
    assert result.backend == "builtin"
    assert result.radiomics_available is False


def test_adv_single_voxel_label_builtin_path_valid_degenerate_result():
    seg_data = np.zeros((3, 3, 3), dtype=np.uint16)
    seg_data[1, 1, 1] = 1
    scan_data = np.zeros((3, 3, 3), dtype=np.float64)
    scan_data[1, 1, 1] = 77.0
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=False)
    assert result.first_order.voxel_count == 1
    assert result.first_order.mean == pytest.approx(77.0)
    assert result.extended == {}
    assert result.backend == "builtin"


def test_adv_backend_constants_match_result_values():
    """The module exposes backend marker constants matching the string
    values actually produced on the builtin path."""
    import segqc.features.radiomics as mod

    scan_img, seg_img = _known_values_case()
    result = compute_label_radiomics(scan_img, seg_img, label=1, enable_pyradiomics=False)
    assert hasattr(mod, "RADIOMICS_BACKEND_BUILTIN")
    assert hasattr(mod, "RADIOMICS_BACKEND_PYRADIOMICS")
    assert result.backend == mod.RADIOMICS_BACKEND_BUILTIN
    assert mod.RADIOMICS_BACKEND_BUILTIN != mod.RADIOMICS_BACKEND_PYRADIOMICS


def test_adv_repeated_disabled_calls_are_pure_and_equal():
    """Repeated calls with enable_pyradiomics=False are pure and equal,
    independent of whatever the ambient PyRadiomics availability is."""
    scan_img, seg_img = _two_label_case()
    f1 = compute_radiomics_features(scan_img, seg_img, enable_pyradiomics=False)
    f2 = compute_radiomics_features(scan_img, seg_img, enable_pyradiomics=False)
    assert f1 == f2
    for label, result in f1.items():
        assert result.backend == "builtin"
        assert result.extended == {}
