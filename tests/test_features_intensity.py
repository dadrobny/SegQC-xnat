"""Tests for per-label first-order intensity features (item 059).

Covers all 18 Acceptance Criteria plus adversarial and edge-case inputs:
single-voxel labels, negative HU values, mixed finite/non-finite voxels,
a single surviving finite voxel among non-finite ones, extreme percentile
ties, and affine-tolerance boundary behaviour.

All tests build tiny in-memory ``Nifti1Image`` scan+seg pairs (diagonal
affines, hand-known voxel values) so every statistic is independently
verifiable against ``numpy``'s own reductions/percentile function -- the
documented ground truth per the item spec. AC18 additionally checks the
committed item-058 clean intensity corpus (``tests/corpus/intensity/``).

All tests are deterministic, CPU-only, and portable (no network, no
absolute paths, no services).
"""

from __future__ import annotations

import ast
import dataclasses
import inspect

import nibabel as nib
import numpy as np
import pytest

from segqc.io import load_case
from segqc.synth.intensity import INTENSITY_CORPUS_DIR, load_intensity_manifest

from segqc.features.intensity import (
    LabelIntensity,
    compute_intensity_features,
    compute_label_intensity,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

_STAT_FIELDS = (
    "mean", "median", "std", "min", "max",
    "p05", "p25", "p50", "p75", "p95", "range", "iqr", "entropy",
)

# A small multi-valued fixture with hand-known statistics (sorted for
# clarity; the extractor must not assume sortedness).
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
    return _scan_img(scan_data, spacing), _seg_img(seg_data, spacing)


def _values_case(values, spacing=(1.0, 1.0, 1.0)):
    """A (1,1,len(values)) volume, label 1 covering all voxels with ``values``."""
    n = len(values)
    seg_data = np.ones((1, 1, n), dtype=np.uint16)
    scan_data = np.array(values, dtype=np.float64).reshape(1, 1, n)
    return _scan_img(scan_data, spacing), _seg_img(seg_data, spacing)


def _expected_entropy(values, bins=32):
    """Independent reference Shannon entropy (base-2, fixed-bin histogram
    over [min, max]) matching the item spec's documented definition."""
    values = np.asarray(values, dtype=np.float64)
    vmin, vmax = float(values.min()), float(values.max())
    if vmin == vmax:
        return 0.0
    hist, _ = np.histogram(values, bins=bins, range=(vmin, vmax))
    counts = hist[hist > 0].astype(np.float64)
    probs = counts / counts.sum()
    return float(-(probs * np.log2(probs)).sum())


def _assert_all_stats_none(result):
    for field_name in _STAT_FIELDS:
        assert getattr(result, field_name) is None, field_name


# =========================================================================== #
# Import contract
# =========================================================================== #

def test_import_label_intensity():
    """LabelIntensity is importable from segqc.features.intensity."""
    from segqc.features.intensity import LabelIntensity as LI  # noqa: F401
    assert LI is LabelIntensity


def test_import_compute_label_intensity():
    """compute_label_intensity is importable from segqc.features.intensity."""
    from segqc.features.intensity import compute_label_intensity as cli  # noqa: F401
    assert callable(cli)


def test_import_compute_intensity_features():
    """compute_intensity_features is importable from segqc.features.intensity."""
    from segqc.features.intensity import compute_intensity_features as cif  # noqa: F401
    assert callable(cif)


def test_no_import_error():
    """Importing segqc.features.intensity raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.intensity")
    assert hasattr(mod, "LabelIntensity")
    assert hasattr(mod, "compute_label_intensity")
    assert hasattr(mod, "compute_intensity_features")


# =========================================================================== #
# AC1  Module & pure public API
# =========================================================================== #

def test_ac1_label_intensity_is_a_dataclass_with_fields():
    """LabelIntensity is a dataclass exposing at least one field."""
    assert dataclasses.is_dataclass(LabelIntensity)
    assert dataclasses.fields(LabelIntensity)


def test_ac1_label_intensity_is_frozen():
    """LabelIntensity instances reject attribute mutation (frozen dataclass)."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.mean = 0.0  # type: ignore[misc]


def test_ac1_module_imports_only_numpy_scipy_nibabel_stdlib():
    """The module's top-level imports are restricted to NumPy/SciPy/NiBabel
    (+ dataclasses/typing/__future__), no PyRadiomics or file-I/O libraries."""
    import segqc.features.intensity as mod
    tree = ast.parse(inspect.getsource(mod))
    allowed_roots = {"numpy", "scipy", "nibabel", "dataclasses", "typing", "__future__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed_roots, f"disallowed import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                assert root in allowed_roots, f"disallowed import: {node.module}"


# =========================================================================== #
# AC2  Documented tracked-feature set
# =========================================================================== #

def test_ac2_label_intensity_has_documented_fields():
    """LabelIntensity carries exactly the AC2 fields."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    expected_fields = {"voxel_count", "n_nonfinite_excluded"} | set(_STAT_FIELDS)
    actual_fields = {f.name for f in dataclasses.fields(result)}
    assert actual_fields == expected_fields


def test_ac2_stats_are_json_friendly_scalars():
    """Count fields are int; statistic fields are float or None -- no
    nibabel objects."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert isinstance(result.voxel_count, int)
    assert isinstance(result.n_nonfinite_excluded, int)
    for field_name in _STAT_FIELDS:
        value = getattr(result, field_name)
        assert value is None or isinstance(value, float), (field_name, type(value))


def test_ac2_comparable_with_equality():
    """Two LabelIntensity instances with identical fields compare equal."""
    scan_img, seg_img = _known_values_case()
    r1 = compute_label_intensity(scan_img, seg_img, label=1)
    r2 = compute_label_intensity(scan_img, seg_img, label=1)
    assert r1 == r2


# =========================================================================== #
# AC3  Mean & median correct
# =========================================================================== #

def test_ac3_mean_correct():
    """mean equals the hand-computed mean of the known values."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.mean == pytest.approx(float(np.mean(_VALUES)))


def test_ac3_median_correct():
    """median equals the hand-computed median of the known values."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.median == pytest.approx(float(np.median(_VALUES)))


# =========================================================================== #
# AC4  Std correct (population, ddof=0)
# =========================================================================== #

def test_ac4_std_is_population_std_ddof0():
    """std equals numpy's ddof=0 (population) standard deviation."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.std == pytest.approx(float(np.std(_VALUES, ddof=0)))


# =========================================================================== #
# AC5  Min, max & range correct
# =========================================================================== #

def test_ac5_min_max_range_correct():
    """min/max match the extrema; range == max - min."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.min == pytest.approx(min(_VALUES))
    assert result.max == pytest.approx(max(_VALUES))
    assert result.range == pytest.approx(max(_VALUES) - min(_VALUES))


# =========================================================================== #
# AC6  Percentiles, median identity & IQR correct
# =========================================================================== #

def test_ac6_percentiles_correct():
    """p05/p25/p50/p75/p95 equal numpy.percentile's linear-interpolation
    result on the known values."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    for pct, field_name in ((5, "p05"), (25, "p25"), (50, "p50"), (75, "p75"), (95, "p95")):
        expected = float(np.percentile(_VALUES, pct))
        assert getattr(result, field_name) == pytest.approx(expected), field_name


def test_ac6_p50_equals_median():
    """p50 == median."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.p50 == pytest.approx(result.median)


def test_ac6_iqr_equals_p75_minus_p25():
    """iqr == p75 - p25."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.iqr == pytest.approx(result.p75 - result.p25)


# =========================================================================== #
# AC7  Intensity entropy correct & documented
# =========================================================================== #

def test_ac7_entropy_correct_on_multi_valued_region():
    """entropy matches the independently-computed 32-bin base-2 Shannon
    entropy over [min, max] of the known multi-valued region."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.entropy == pytest.approx(_expected_entropy(_VALUES), abs=1e-9)


# =========================================================================== #
# AC8  Uniform region
# =========================================================================== #

def test_ac8_uniform_region_stats():
    """A constant-intensity label yields that constant for every location
    statistic, with std/range/iqr/entropy all 0.0."""
    seg_data = np.ones((2, 2, 2), dtype=np.uint16)
    scan_data = np.full((2, 2, 2), 42.0, dtype=np.float64)
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    for field_name in ("mean", "median", "min", "max", "p05", "p25", "p50", "p75", "p95"):
        assert getattr(result, field_name) == pytest.approx(42.0), field_name
    assert result.std == 0.0
    assert result.range == 0.0
    assert result.iqr == 0.0
    assert result.entropy == 0.0


# =========================================================================== #
# AC9  Spacing invariance
# =========================================================================== #

def test_ac9_spacing_invariance_isotropic_vs_anisotropic():
    """Identical arrays under isotropic vs anisotropic affines yield
    identical first-order statistics (not voxel-volume weighted)."""
    iso_scan, iso_seg = _known_values_case(spacing=(1.0, 1.0, 1.0))
    aniso_scan, aniso_seg = _known_values_case(spacing=(0.5, 0.5, 3.0))
    r_iso = compute_label_intensity(iso_scan, iso_seg, label=1)
    r_aniso = compute_label_intensity(aniso_scan, aniso_seg, label=1)
    assert r_iso == r_aniso


# =========================================================================== #
# AC10  Grid-alignment guard -- shape
# =========================================================================== #

def test_ac10_shape_mismatch_raises_value_error_naming_shapes():
    """Mismatched scan/seg shapes raise ValueError naming both shapes."""
    seg_data = np.ones((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 5), dtype=np.float64)
    scan_img = _scan_img(scan_data)
    seg_img = _seg_img(seg_data)
    with pytest.raises(ValueError) as excinfo:
        compute_label_intensity(scan_img, seg_img, label=1)
    message = str(excinfo.value)
    assert "(4, 4, 5)" in message
    assert "(4, 4, 4)" in message


# =========================================================================== #
# AC11  Grid-alignment guard -- affine
# =========================================================================== #

def test_ac11_affine_mismatch_raises_value_error():
    """Incompatible affines (beyond tolerance) raise ValueError."""
    seg_data = np.ones((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    seg_img = _seg_img(seg_data, spacing=(1.0, 1.0, 1.0))
    scan_img = _scan_img(scan_data, spacing=(2.0, 2.0, 2.0))
    with pytest.raises(ValueError):
        compute_label_intensity(scan_img, seg_img, label=1)


def test_ac11_matching_shape_and_affine_does_not_raise():
    """A compatible scan/seg pair does not raise."""
    scan_img, seg_img = _known_values_case()
    compute_label_intensity(scan_img, seg_img, label=1)  # must not raise


# =========================================================================== #
# AC12  Empty / absent-label sentinel
# =========================================================================== #

def test_ac12_absent_label_returns_sentinel():
    """A label absent from the segmentation returns a well-formed sentinel."""
    scan_img, seg_img = _known_values_case()
    result = compute_label_intensity(scan_img, seg_img, label=999)
    assert result.voxel_count == 0
    _assert_all_stats_none(result)


def test_ac12_empty_mask_selects_no_voxels_returns_sentinel():
    """A label whose mask selects no voxels (all-background seg) returns a
    well-formed sentinel, never raising."""
    seg_data = np.zeros((4, 4, 4), dtype=np.uint16)
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.voxel_count == 0
    _assert_all_stats_none(result)


# =========================================================================== #
# AC13  Non-finite voxels excluded
# =========================================================================== #

def test_ac13_nonfinite_voxels_excluded_from_stats():
    """Stats are computed over the finite subset only; n_nonfinite_excluded
    counts the excluded voxels."""
    values = [10.0, 20.0, np.nan, 30.0, np.inf, 40.0, -np.inf]
    finite_values = [10.0, 20.0, 30.0, 40.0]
    scan_img, seg_img = _values_case(values)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.voxel_count == len(finite_values)
    assert result.n_nonfinite_excluded == len(values) - len(finite_values)
    assert result.mean == pytest.approx(float(np.mean(finite_values)))
    assert result.min == pytest.approx(min(finite_values))
    assert result.max == pytest.approx(max(finite_values))


# =========================================================================== #
# AC14  All-non-finite sentinel
# =========================================================================== #

def test_ac14_all_nonfinite_returns_sentinel():
    """A masked region whose voxels are all non-finite returns the sentinel,
    reporting n_nonfinite_excluded == masked voxel count."""
    values = [np.nan, np.inf, -np.inf, np.nan]
    scan_img, seg_img = _values_case(values)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.voxel_count == 0
    assert result.n_nonfinite_excluded == len(values)
    _assert_all_stats_none(result)


# =========================================================================== #
# AC15  Per-case convenience
# =========================================================================== #

def _two_label_case():
    seg_data = np.zeros((6, 6, 6), dtype=np.uint16)
    seg_data[0:2, 0:2, 0:2] = 1
    seg_data[3:5, 3:5, 3:5] = 2
    scan_data = np.arange(6 * 6 * 6, dtype=np.float64).reshape(6, 6, 6)
    return _scan_img(scan_data), _seg_img(seg_data)


def test_ac15_compute_intensity_features_keys_match_present_labels():
    """Returned dict keys equal the present non-zero labels."""
    scan_img, seg_img = _two_label_case()
    features = compute_intensity_features(scan_img, seg_img)
    assert set(features.keys()) == {1, 2}


def test_ac15_compute_intensity_features_values_match_single_label_calls():
    """Each dict value equals the corresponding compute_label_intensity call."""
    scan_img, seg_img = _two_label_case()
    features = compute_intensity_features(scan_img, seg_img)
    for label in (1, 2):
        assert features[label] == compute_label_intensity(scan_img, seg_img, label)


def test_ac15_background_label_excluded():
    """Background (label 0) never appears in the returned dict."""
    seg_data = np.zeros((4, 4, 4), dtype=np.uint16)
    seg_data[0:2, 0:2, 0:2] = 1
    scan_data = np.zeros((4, 4, 4), dtype=np.float64)
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    features = compute_intensity_features(scan_img, seg_img)
    assert 0 not in features


# =========================================================================== #
# AC16  Purity / immutability
# =========================================================================== #

def test_ac16_compute_label_intensity_does_not_mutate_inputs():
    """compute_label_intensity leaves scan and seg arrays byte-identical."""
    scan_img, seg_img = _known_values_case()
    scan_before = np.asanyarray(scan_img.dataobj).copy()
    seg_before = np.asanyarray(seg_img.dataobj).copy()
    compute_label_intensity(scan_img, seg_img, label=1)
    np.testing.assert_array_equal(np.asanyarray(scan_img.dataobj), scan_before)
    np.testing.assert_array_equal(np.asanyarray(seg_img.dataobj), seg_before)


def test_ac16_compute_intensity_features_does_not_mutate_inputs():
    """compute_intensity_features leaves scan and seg arrays byte-identical."""
    scan_img, seg_img = _two_label_case()
    scan_before = np.asanyarray(scan_img.dataobj).copy()
    seg_before = np.asanyarray(seg_img.dataobj).copy()
    compute_intensity_features(scan_img, seg_img)
    np.testing.assert_array_equal(np.asanyarray(scan_img.dataobj), scan_before)
    np.testing.assert_array_equal(np.asanyarray(seg_img.dataobj), seg_before)


# =========================================================================== #
# AC17  Determinism
# =========================================================================== #

def test_ac17_determinism_repeated_calls_equal():
    """Two compute_label_intensity calls on identical inputs compare equal."""
    scan_img, seg_img = _known_values_case()
    r1 = compute_label_intensity(scan_img, seg_img, label=1)
    r2 = compute_label_intensity(scan_img, seg_img, label=1)
    assert r1 == r2


def test_ac17_determinism_per_case_convenience():
    """Two compute_intensity_features calls on identical inputs compare equal."""
    scan_img, seg_img = _two_label_case()
    f1 = compute_intensity_features(scan_img, seg_img)
    f2 = compute_intensity_features(scan_img, seg_img)
    assert f1 == f2


# =========================================================================== #
# AC18  Clean-fixture sanity (item 058 corpus)
# =========================================================================== #

def test_ac18_clean_fixture_medians_within_expected_hu_bands():
    """Every vertebra label's computed median falls within the committed
    clean case's expected_label_hu_bands (item 058 manifest)."""
    manifest = load_intensity_manifest()
    clean_case = next(c for c in manifest["cases"] if c["plausible"] is True)
    scan_path = INTENSITY_CORPUS_DIR / clean_case["scan_fixture"]
    seg_path = INTENSITY_CORPUS_DIR / clean_case["seg_fixture"]
    loaded = load_case(scan_path, seg_path)
    scan_img = nib.Nifti1Image(loaded.scan.data, loaded.scan.affine)
    # loaded.seg.data is int64 (segqc.io preserves the label map's native
    # integer dtype); nibabel 5.x rejects a bare int64 array with no header,
    # so cast to int32 explicitly when reconstructing the Nifti1Image.
    seg_img = nib.Nifti1Image(loaded.seg.data.astype(np.int32), loaded.seg.affine)

    assert clean_case["expected_label_hu_bands"]  # sanity: bands present
    for label_str, band in clean_case["expected_label_hu_bands"].items():
        label = int(label_str)
        result = compute_label_intensity(scan_img, seg_img, label)
        assert result.voxel_count > 0, label
        assert result.median is not None, label
        assert band[0] <= result.median <= band[1], (label, result.median, band)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #

def test_adv_single_voxel_label_stats_are_degenerate():
    """A single-voxel label: std/range/iqr/entropy are all 0.0."""
    seg_data = np.zeros((3, 3, 3), dtype=np.uint16)
    seg_data[1, 1, 1] = 1
    scan_data = np.zeros((3, 3, 3), dtype=np.float64)
    scan_data[1, 1, 1] = 77.0
    scan_img, seg_img = _scan_img(scan_data), _seg_img(seg_data)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.voxel_count == 1
    assert result.mean == pytest.approx(77.0)
    assert result.median == pytest.approx(77.0)
    assert result.std == 0.0
    assert result.range == 0.0
    assert result.iqr == 0.0
    assert result.entropy == 0.0


def test_adv_negative_hu_values_handled():
    """Negative HU values (air/soft-tissue range) are handled correctly."""
    values = [-1000.0, -950.0, -900.0, -50.0, -30.0]
    scan_img, seg_img = _values_case(values)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.min == pytest.approx(min(values))
    assert result.max == pytest.approx(max(values))
    assert result.mean == pytest.approx(float(np.mean(values)))
    assert result.range == pytest.approx(max(values) - min(values))


def test_adv_single_finite_voxel_among_nonfinite():
    """A label with only one finite voxel among several non-finite ones is
    not a sentinel: it reports that single voxel's degenerate statistics."""
    values = [np.nan, np.inf, 55.0, -np.inf]
    scan_img, seg_img = _values_case(values)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    assert result.voxel_count == 1
    assert result.n_nonfinite_excluded == 3
    assert result.mean == pytest.approx(55.0)
    assert result.median == pytest.approx(55.0)
    assert result.std == 0.0
    assert result.entropy == 0.0


def test_adv_percentile_ties_many_repeated_values():
    """Percentiles under heavy ties match numpy.percentile exactly."""
    values = [5.0] * 9 + [100.0]
    scan_img, seg_img = _values_case(values)
    result = compute_label_intensity(scan_img, seg_img, label=1)
    for pct, field_name in ((5, "p05"), (25, "p25"), (75, "p75"), (95, "p95")):
        expected = float(np.percentile(values, pct))
        assert getattr(result, field_name) == pytest.approx(expected), field_name


def test_adv_affine_within_tolerance_does_not_raise():
    """An affine perturbed well inside io.load_case's tolerance is treated
    as compatible."""
    seg_data = np.ones((3, 3, 3), dtype=np.uint16)
    scan_data = np.zeros((3, 3, 3), dtype=np.float64)
    seg_img = _seg_img(seg_data, spacing=(1.0, 1.0, 1.0))
    affine = _affine((1.0, 1.0, 1.0))
    affine[0, 0] += 5e-5  # << rtol=1e-5, atol=1e-4 tolerance
    scan_img = nib.Nifti1Image(scan_data, affine)
    compute_label_intensity(scan_img, seg_img, label=1)  # must not raise


def test_adv_affine_beyond_tolerance_raises():
    """An affine perturbed well past io.load_case's tolerance raises."""
    seg_data = np.ones((3, 3, 3), dtype=np.uint16)
    scan_data = np.zeros((3, 3, 3), dtype=np.float64)
    seg_img = _seg_img(seg_data, spacing=(1.0, 1.0, 1.0))
    affine = _affine((1.0, 1.0, 1.0))
    affine[0, 0] += 1e-2
    scan_img = nib.Nifti1Image(scan_data, affine)
    with pytest.raises(ValueError):
        compute_label_intensity(scan_img, seg_img, label=1)
