"""Tests for the empty / near-empty detection module (item 007).

Covers all ten Acceptance Criteria plus adversarial and edge-case inputs:
threshold boundary values (exactly at, one below, one above), single-voxel /
single-label maps, both thresholds firing simultaneously, metadata invariants,
reason-string quality, determinism, and the module's import contract.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import dataclasses

import numpy as np
import nibabel as nib
import pytest

from segqc.config import HeuristicConfig, default_config
from segqc.empty import CheckResult, check_empty

from synthetic import (
    LABEL_DTYPE,
    anisotropic_case,
    empty_case,
    labelled_blocks_case,
    make_labelmap,
    make_scan,
)


# =========================================================================== #
# Helpers
# =========================================================================== #

def _config(min_foreground_voxels: int = 0, min_label_count: int = 0) -> HeuristicConfig:
    """Return a HeuristicConfig with the given threshold values."""
    return HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=min_foreground_voxels,
        min_label_count=min_label_count,
    )


def _single_label_n_voxels(n: int) -> nib.Nifti1Image:
    """Return a tiny label map with exactly n foreground voxels, all label=1.

    Uses a flat 1-D shape to make the geometry trivial.  n must be <= 64.
    """
    assert 0 <= n <= 64
    data = np.zeros((64,), dtype=LABEL_DTYPE)
    data[:n] = 1
    data = data.reshape((8, 8, 1))
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    return nib.Nifti1Image(data, affine)


def _k_label_map(k: int, voxels_per_label: int = 8) -> nib.Nifti1Image:
    """Return a label map with exactly k distinct non-zero labels.

    Each label occupies voxels_per_label voxels in a flat volume.
    """
    assert k >= 0
    total = k * voxels_per_label if k > 0 else 1
    data = np.zeros((max(total, 1),), dtype=LABEL_DTYPE)
    for label in range(1, k + 1):
        start = (label - 1) * voxels_per_label
        data[start : start + voxels_per_label] = label
    data = data.reshape((-1, 1, 1))
    affine = np.diag([1.0, 1.0, 1.0, 1.0])
    return nib.Nifti1Image(data, affine)


# =========================================================================== #
# AC-1  Empty label map → failure
# =========================================================================== #

def test_ac1_empty_map_is_empty_default_config():
    """An all-zero label map returns is_empty=True with default config."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    assert result.is_empty is True


def test_ac1_empty_map_has_reasons():
    """An all-zero label map returns at least one reason string."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    assert len(result.reasons) >= 1


def test_ac1_empty_map_reason_is_string():
    """Reason strings for an empty map are non-empty str objects."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    for reason in result.reasons:
        assert isinstance(reason, str)
        assert len(reason) > 0


def test_ac1_empty_map_with_high_thresholds_is_still_empty():
    """An all-zero map is empty regardless of how high min_* thresholds are set."""
    case = empty_case()
    cfg = _config(min_foreground_voxels=9999, min_label_count=9999)
    result = check_empty(case.seg_img, cfg)
    assert result.is_empty is True


def test_ac1_all_zero_data_directly():
    """A freshly constructed all-zero Nifti1Image is detected as empty."""
    data = np.zeros((4, 4, 4), dtype=LABEL_DTYPE)
    img = nib.Nifti1Image(data, np.eye(4))
    result = check_empty(img, default_config())
    assert result.is_empty is True


def test_ac1_single_voxel_all_zero_is_empty():
    """A single-voxel all-zero volume is detected as empty."""
    data = np.zeros((1, 1, 1), dtype=LABEL_DTYPE)
    img = nib.Nifti1Image(data, np.eye(4))
    result = check_empty(img, default_config())
    assert result.is_empty is True


# =========================================================================== #
# AC-2  Foreground-voxel threshold fires correctly
# =========================================================================== #

def test_ac2_below_foreground_threshold_is_empty():
    """A map with fewer foreground voxels than min_foreground_voxels → is_empty=True."""
    img = _single_label_n_voxels(3)
    cfg = _config(min_foreground_voxels=5)
    result = check_empty(img, cfg)
    assert result.is_empty is True


def test_ac2_below_threshold_reason_mentions_voxel_count():
    """The reason string for a voxel-count failure mentions the actual voxel count."""
    img = _single_label_n_voxels(3)
    cfg = _config(min_foreground_voxels=5)
    result = check_empty(img, cfg)
    assert any("3" in r for r in result.reasons), (
        f"Expected '3' (actual count) in at least one reason; got: {result.reasons}"
    )


def test_ac2_exactly_at_foreground_threshold_passes():
    """Exactly min_foreground_voxels voxels → is_empty=False (boundary is inclusive)."""
    n = 5
    img = _single_label_n_voxels(n)
    cfg = _config(min_foreground_voxels=n)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_ac2_one_above_foreground_threshold_passes():
    """One more than min_foreground_voxels → is_empty=False."""
    n = 5
    img = _single_label_n_voxels(n + 1)
    cfg = _config(min_foreground_voxels=n)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_ac2_one_below_foreground_threshold_fails():
    """One fewer than min_foreground_voxels → is_empty=True."""
    n = 5
    img = _single_label_n_voxels(n - 1)
    cfg = _config(min_foreground_voxels=n)
    result = check_empty(img, cfg)
    assert result.is_empty is True


def test_ac2_zero_min_foreground_voxels_skips_check():
    """min_foreground_voxels=0 (default) does not flag a map with foreground."""
    img = _single_label_n_voxels(1)
    cfg = _config(min_foreground_voxels=0)
    result = check_empty(img, cfg)
    # Only should fail if also empty — which it isn't (has 1 voxel).
    assert result.is_empty is False


def test_ac2_reason_mentions_threshold_value():
    """The reason string for a voxel-count failure mentions the threshold."""
    img = _single_label_n_voxels(2)
    cfg = _config(min_foreground_voxels=10)
    result = check_empty(img, cfg)
    assert any("10" in r for r in result.reasons), (
        f"Expected '10' (threshold) in at least one reason; got: {result.reasons}"
    )


# =========================================================================== #
# AC-3  Label-count threshold fires correctly
# =========================================================================== #

def test_ac3_below_label_count_threshold_is_empty():
    """A map with fewer distinct labels than min_label_count → is_empty=True."""
    img = _k_label_map(1)  # 1 label
    cfg = _config(min_label_count=3)
    result = check_empty(img, cfg)
    assert result.is_empty is True


def test_ac3_below_threshold_reason_mentions_label_count():
    """The reason string for a label-count failure mentions the actual label count."""
    img = _k_label_map(1)
    cfg = _config(min_label_count=3)
    result = check_empty(img, cfg)
    assert any("1" in r for r in result.reasons), (
        f"Expected '1' (actual count) in at least one reason; got: {result.reasons}"
    )


def test_ac3_exactly_at_label_threshold_passes():
    """Exactly min_label_count distinct labels → is_empty=False (boundary inclusive)."""
    k = 3
    img = _k_label_map(k)
    cfg = _config(min_label_count=k)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_ac3_one_below_label_threshold_fails():
    """One fewer than min_label_count distinct labels → is_empty=True."""
    k = 3
    img = _k_label_map(k - 1)
    cfg = _config(min_label_count=k)
    result = check_empty(img, cfg)
    assert result.is_empty is True


def test_ac3_one_above_label_threshold_passes():
    """One more than min_label_count distinct labels → is_empty=False."""
    k = 3
    img = _k_label_map(k + 1)
    cfg = _config(min_label_count=k)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_ac3_zero_min_label_count_skips_check():
    """min_label_count=0 (default) does not flag a single-label map."""
    img = _k_label_map(1)
    cfg = _config(min_label_count=0)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_ac3_reason_mentions_threshold_value():
    """The reason string for a label-count failure mentions the threshold."""
    img = _k_label_map(1)
    cfg = _config(min_label_count=5)
    result = check_empty(img, cfg)
    assert any("5" in r for r in result.reasons), (
        f"Expected '5' (threshold) in at least one reason; got: {result.reasons}"
    )


# =========================================================================== #
# AC-4  Populated map passes with default thresholds
# =========================================================================== #

def test_ac4_labelled_blocks_passes_default_config():
    """The labelled-blocks fixture (3 labels, 192 voxels) passes with default config."""
    case = labelled_blocks_case()
    result = check_empty(case.seg_img, default_config())
    assert result.is_empty is False


def test_ac4_populated_map_has_no_reasons():
    """A passing result has an empty reasons collection."""
    case = labelled_blocks_case()
    result = check_empty(case.seg_img, default_config())
    assert len(result.reasons) == 0


def test_ac4_anisotropic_case_passes_default_config():
    """The anisotropic fixture (2 labels) also passes with default config."""
    case = anisotropic_case()
    result = check_empty(case.seg_img, default_config())
    assert result.is_empty is False


def test_ac4_single_label_single_voxel_passes_default_config():
    """A single voxel with a non-zero label passes with default thresholds."""
    img = _single_label_n_voxels(1)
    result = check_empty(img, default_config())
    assert result.is_empty is False


# =========================================================================== #
# AC-5  Both thresholds can fire simultaneously
# =========================================================================== #

def test_ac5_both_thresholds_fire_single_voxel_single_label():
    """A single-voxel single-label map fires both thresholds when both are set > 1."""
    img = _single_label_n_voxels(1)
    cfg = _config(min_foreground_voxels=2, min_label_count=2)
    result = check_empty(img, cfg)
    assert result.is_empty is True
    assert len(result.reasons) >= 2


def test_ac5_both_reasons_distinct():
    """When both thresholds fire, the two reason strings are distinct."""
    img = _single_label_n_voxels(1)
    cfg = _config(min_foreground_voxels=2, min_label_count=2)
    result = check_empty(img, cfg)
    assert len(set(result.reasons)) == len(result.reasons), (
        "Duplicate reason strings found; each condition should produce a unique reason."
    )


def test_ac5_only_label_count_threshold_fires():
    """When only the label-count threshold fires, exactly one reason is returned."""
    # 10 voxels, 1 label → foreground OK, label count fails
    img = _k_label_map(k=1, voxels_per_label=10)
    cfg = _config(min_foreground_voxels=5, min_label_count=3)
    result = check_empty(img, cfg)
    assert result.is_empty is True
    # The voxel-count reason should NOT fire (10 >= 5).
    assert result.foreground_voxels == 10


def test_ac5_only_voxel_count_threshold_fires():
    """When only the voxel-count threshold fires, at least the voxel reason is present."""
    # 3 voxels, 3 labels → label count OK, voxel count fails
    img = _k_label_map(k=3, voxels_per_label=1)
    cfg = _config(min_foreground_voxels=10, min_label_count=2)
    result = check_empty(img, cfg)
    assert result.is_empty is True
    assert result.label_count == 3


# =========================================================================== #
# AC-6  Metadata always returned
# =========================================================================== #

def test_ac6_empty_map_reports_zero_foreground_voxels():
    """An all-zero map reports foreground_voxels=0."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    assert result.foreground_voxels == 0


def test_ac6_empty_map_reports_zero_label_count():
    """An all-zero map reports label_count=0."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    assert result.label_count == 0


def test_ac6_labelled_blocks_foreground_voxel_count():
    """The labelled-blocks fixture reports the correct foreground voxel count."""
    case = labelled_blocks_case()
    # 3 blocks, each 4x4x4 = 64 voxels → 192 total foreground voxels.
    result = check_empty(case.seg_img, default_config())
    assert result.foreground_voxels == 192


def test_ac6_labelled_blocks_label_count():
    """The labelled-blocks fixture reports 3 distinct labels."""
    case = labelled_blocks_case()
    result = check_empty(case.seg_img, default_config())
    assert result.label_count == 3


def test_ac6_metadata_returned_when_threshold_fires():
    """foreground_voxels and label_count are populated even when is_empty=True."""
    img = _single_label_n_voxels(3)
    cfg = _config(min_foreground_voxels=10)
    result = check_empty(img, cfg)
    assert result.is_empty is True
    assert result.foreground_voxels == 3
    assert result.label_count == 1


def test_ac6_metadata_positive_for_non_empty_map():
    """foreground_voxels > 0 and label_count > 0 for any non-empty map."""
    case = labelled_blocks_case()
    result = check_empty(case.seg_img, default_config())
    assert result.foreground_voxels > 0
    assert result.label_count > 0


# =========================================================================== #
# AC-7  Config controls thresholds
# =========================================================================== #

def test_ac7_raising_foreground_threshold_changes_verdict():
    """Raising min_foreground_voxels above actual count flips pass → fail."""
    img = _single_label_n_voxels(5)
    cfg_low = _config(min_foreground_voxels=0)
    cfg_high = _config(min_foreground_voxels=10)
    assert not check_empty(img, cfg_low).is_empty
    assert check_empty(img, cfg_high).is_empty


def test_ac7_raising_label_count_threshold_changes_verdict():
    """Raising min_label_count above actual count flips pass → fail."""
    img = _k_label_map(2)
    cfg_low = _config(min_label_count=0)
    cfg_high = _config(min_label_count=5)
    assert not check_empty(img, cfg_low).is_empty
    assert check_empty(img, cfg_high).is_empty


def test_ac7_same_image_different_configs_different_results():
    """The same image produces different results under different configs."""
    case = labelled_blocks_case()
    result_default = check_empty(case.seg_img, default_config())
    result_strict = check_empty(case.seg_img, _config(min_foreground_voxels=9999))
    assert not result_default.is_empty
    assert result_strict.is_empty


def test_ac7_input_image_not_mutated_by_check():
    """check_empty does not mutate the input label map's data array."""
    case = labelled_blocks_case()
    original_data = np.asanyarray(case.seg_img.dataobj).copy()
    check_empty(case.seg_img, _config(min_foreground_voxels=9999))
    after_data = np.asanyarray(case.seg_img.dataobj)
    assert np.array_equal(original_data, after_data)


# =========================================================================== #
# AC-8  Module location / importability
# =========================================================================== #

def test_ac8_check_empty_importable_from_segqc_empty():
    """check_empty is importable from segqc.empty."""
    from segqc.empty import check_empty as ce  # noqa: F401
    assert callable(ce)


def test_ac8_checkresult_importable_from_segqc_empty():
    """CheckResult is importable from segqc.empty."""
    from segqc.empty import CheckResult as CR  # noqa: F401
    assert CR is CheckResult


def test_ac8_no_import_error():
    """Importing segqc.empty raises no ImportError."""
    import importlib
    mod = importlib.import_module("segqc.empty")
    assert hasattr(mod, "check_empty")
    assert hasattr(mod, "CheckResult")


# =========================================================================== #
# AC-9  No non-stdlib runtime imports beyond numpy/nibabel
# =========================================================================== #

def test_ac9_empty_module_has_no_scipy():
    """segqc.empty must not have scipy in its module namespace."""
    import segqc.empty as empty_mod
    assert "scipy" not in vars(empty_mod)


def test_ac9_empty_module_has_no_verdict_import():
    """segqc.empty must not import segqc.verdict at module level."""
    import segqc.empty as empty_mod
    module_globals = vars(empty_mod)
    for name, val in module_globals.items():
        if hasattr(val, "__module__"):
            assert "verdict" not in getattr(val, "__module__", ""), (
                f"Found an object from segqc.verdict in segqc.empty namespace: {name}"
            )


def test_ac9_empty_module_has_no_skimage():
    """segqc.empty must not import skimage."""
    import segqc.empty as empty_mod
    assert "skimage" not in vars(empty_mod)


# =========================================================================== #
# AC-10  Reason strings are human-friendly
# =========================================================================== #

def test_ac10_empty_map_reason_no_class_names():
    """Reason strings must not contain raw Python class names like 'Nifti1Image'."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    for reason in result.reasons:
        assert "Nifti1Image" not in reason
        assert "ndarray" not in reason
        assert "numpy" not in reason


def test_ac10_voxel_threshold_reason_no_exception_text():
    """Voxel-count threshold reason must not contain exception-type names."""
    img = _single_label_n_voxels(2)
    cfg = _config(min_foreground_voxels=10)
    result = check_empty(img, cfg)
    for reason in result.reasons:
        assert "ValueError" not in reason
        assert "TypeError" not in reason
        assert "AttributeError" not in reason
        assert "Exception" not in reason


def test_ac10_label_count_reason_no_exception_text():
    """Label-count threshold reason must not contain exception-type names."""
    img = _k_label_map(1)
    cfg = _config(min_label_count=5)
    result = check_empty(img, cfg)
    for reason in result.reasons:
        assert "ValueError" not in reason
        assert "TypeError" not in reason
        assert "AttributeError" not in reason


def test_ac10_reasons_are_readable_sentences():
    """Reason strings for non-trivial failures read like human sentences (not tracebacks)."""
    img = _single_label_n_voxels(2)
    cfg = _config(min_foreground_voxels=10, min_label_count=3)
    result = check_empty(img, cfg)
    for reason in result.reasons:
        # Must not look like a traceback path (no 'File "...'  or 'Traceback')
        assert "Traceback" not in reason
        assert 'File "' not in reason
        # Must not be excessively long (a simple sentence)
        assert len(reason) < 500


# =========================================================================== #
# Adversarial: boundary and degenerate inputs
# =========================================================================== #

def test_adv_single_voxel_single_label_metadata():
    """A 1-voxel, 1-label map has foreground_voxels=1 and label_count=1."""
    img = _single_label_n_voxels(1)
    result = check_empty(img, default_config())
    assert result.foreground_voxels == 1
    assert result.label_count == 1


def test_adv_single_voxel_volume_shape():
    """check_empty handles a (1, 1, 1) shaped volume correctly."""
    data = np.array([[[1]]], dtype=LABEL_DTYPE)
    img = nib.Nifti1Image(data, np.eye(4))
    result = check_empty(img, default_config())
    assert result.foreground_voxels == 1
    assert result.label_count == 1
    assert result.is_empty is False


def test_adv_large_foreground_count():
    """A large volume (64^3 all-ones) reports correct foreground count."""
    data = np.ones((64, 64, 64), dtype=LABEL_DTYPE)
    img = nib.Nifti1Image(data, np.eye(4))
    result = check_empty(img, default_config())
    assert result.foreground_voxels == 64 ** 3
    assert result.label_count == 1
    assert result.is_empty is False


def test_adv_many_labels():
    """A map with 20 distinct labels reports label_count=20."""
    img = _k_label_map(k=20, voxels_per_label=4)
    result = check_empty(img, default_config())
    assert result.label_count == 20
    assert result.foreground_voxels == 80


def test_adv_threshold_exactly_1_fires_on_empty():
    """min_foreground_voxels=1 fires on an empty map (0 < 1)."""
    case = empty_case()
    cfg = _config(min_foreground_voxels=1)
    result = check_empty(case.seg_img, cfg)
    assert result.is_empty is True


def test_adv_threshold_exactly_1_passes_on_1_voxel():
    """min_foreground_voxels=1 passes on a 1-voxel map (1 >= 1)."""
    img = _single_label_n_voxels(1)
    cfg = _config(min_foreground_voxels=1)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_adv_threshold_min_label_count_1_fires_on_empty():
    """min_label_count=1 fires on an empty map (0 < 1)."""
    case = empty_case()
    cfg = _config(min_label_count=1)
    result = check_empty(case.seg_img, cfg)
    assert result.is_empty is True


def test_adv_threshold_min_label_count_1_passes_on_1_label():
    """min_label_count=1 passes on a 1-label map (1 >= 1)."""
    img = _k_label_map(1)
    cfg = _config(min_label_count=1)
    result = check_empty(img, cfg)
    assert result.is_empty is False


def test_adv_determinism_same_inputs_same_result():
    """Two calls to check_empty with the same inputs produce identical results."""
    case = labelled_blocks_case()
    cfg = _config(min_foreground_voxels=100, min_label_count=2)
    r1 = check_empty(case.seg_img, cfg)
    r2 = check_empty(case.seg_img, cfg)
    assert r1.is_empty == r2.is_empty
    assert r1.foreground_voxels == r2.foreground_voxels
    assert r1.label_count == r2.label_count
    assert r1.reasons == r2.reasons


def test_adv_checkresult_is_frozen():
    """CheckResult is a frozen dataclass — assignment to a field must raise."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        result.is_empty = False  # type: ignore[misc]


def test_adv_float32_label_map_handled():
    """check_empty does not raise when given a float32 label map (non-standard dtype)."""
    data = np.zeros((8, 8, 8), dtype=np.float32)
    data[0, 0, 0] = 1.0
    data[1, 1, 1] = 2.0
    img = nib.Nifti1Image(data, np.eye(4))
    result = check_empty(img, default_config())
    assert result.foreground_voxels == 2
    assert result.is_empty is False


def test_adv_anisotropic_spacing_does_not_affect_voxel_count():
    """Physical spacing has no effect on voxel-count comparisons (counts are in voxels)."""
    case = anisotropic_case()
    result = check_empty(case.seg_img, default_config())
    # anisotropic case has 2 labels, 48 voxels each = 96 total foreground voxels.
    assert result.foreground_voxels == 96
    assert result.label_count == 2


def test_adv_result_is_checkresult_instance():
    """check_empty always returns a CheckResult instance."""
    case = labelled_blocks_case()
    result = check_empty(case.seg_img, default_config())
    assert isinstance(result, CheckResult)


def test_adv_reasons_is_not_list_or_mutable():
    """CheckResult.reasons is an immutable collection (tuple, not list)."""
    case = empty_case()
    result = check_empty(case.seg_img, default_config())
    # Accept tuple; reject list (which is mutable and would violate the frozen contract).
    assert not isinstance(result.reasons, list), (
        "reasons should not be a mutable list; use a tuple or other immutable sequence"
    )
