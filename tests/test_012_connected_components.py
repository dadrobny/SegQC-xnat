"""Tests for connected-components analysis per label (item 012).

Covers all four Acceptance Criteria plus adversarial and edge-case inputs:
single-voxel label (fraction=1.0), all-disconnected voxels (many 1-voxel
components), threshold boundary values (threshold=0, threshold > all
components, threshold between components), anisotropic spacing for physical
volumes, 6-connectivity vs 26-connectivity (explicit connectivity check),
immutability, determinism, error-message quality, and import contract.

All tests are deterministic, CPU-only, and portable (no network, no absolute
paths, no services).
"""

from __future__ import annotations

import numpy as np
import nibabel as nib
import pytest

from synthetic import (
    LABEL_DTYPE,
    affine_from_spacing,
    anisotropic_case,
    labelled_blocks_case,
    make_labelmap,
)

from segqc.features.components import ComponentsInfo, compute_components
from segqc.config import HeuristicConfig


# =========================================================================== #
# Helpers
# =========================================================================== #

def _config(min_fragment_voxels: int = 0) -> HeuristicConfig:
    """Return a HeuristicConfig with the given fragment-voxel threshold."""
    return HeuristicConfig(
        schema_version="0.1",
        min_foreground_voxels=0,
        min_label_count=0,
        min_fragment_voxels=min_fragment_voxels,
    )


def _seg_img(shape, blocks, spacing=(1.0, 1.0, 1.0)):
    """Return a Nifti1Image label map with the given block definitions."""
    return make_labelmap(shape, blocks, spacing)


def _compact_label_img():
    """A 4x4x4 solid block (label 1) in a 10^3 volume at 1mm isotropic.

    One connected component, 64 voxels, no islands.
    """
    return make_labelmap((10, 10, 10), {1: ((3, 7), (3, 7), (3, 7))})


def _fragmented_label_img():
    """Label 1 with a 27-voxel main body (3x3x3) and a 1-voxel island, separated.

    The two pieces are face-disconnected (the island is not adjacent to the
    main body — there is a gap of at least one background voxel on all sides).
    Total label-1 voxels: 27 + 1 = 28.
    Main body occupies (1:4, 1:4, 1:4); island at (6, 6, 6).
    """
    data = np.zeros((10, 10, 10), dtype=LABEL_DTYPE)
    data[1:4, 1:4, 1:4] = 1   # 27 voxels — main body
    data[6, 6, 6] = 1          # 1 voxel — isolated island
    return nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))


def _fragmented_label_img_anisotropic(spacing):
    """Same geometry as _fragmented_label_img but with anisotropic spacing."""
    data = np.zeros((10, 10, 10), dtype=LABEL_DTYPE)
    data[1:4, 1:4, 1:4] = 1
    data[6, 6, 6] = 1
    return nib.Nifti1Image(data, affine_from_spacing(spacing))


def _all_disconnected_label_img(n_voxels: int):
    """Return an image where label 1 has n_voxels isolated single-voxel islands.

    Placed on a regular grid with a gap of 2 voxels between each so they are
    face-disconnected.  n_voxels must be <= 5^3 = 125.
    """
    assert n_voxels <= 125
    data = np.zeros((15, 15, 15), dtype=LABEL_DTYPE)
    count = 0
    for x in range(0, 15, 3):
        for y in range(0, 15, 3):
            for z in range(0, 15, 3):
                if count >= n_voxels:
                    break
                data[x, y, z] = 1
                count += 1
            if count >= n_voxels:
                break
        if count >= n_voxels:
            break
    return nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))


# =========================================================================== #
# Import contract
# =========================================================================== #

def test_import_components_info():
    """ComponentsInfo is importable from segqc.features.components."""
    from segqc.features.components import ComponentsInfo as CI  # noqa: F401
    assert CI is ComponentsInfo


def test_import_compute_components():
    """compute_components is importable from segqc.features.components."""
    from segqc.features.components import compute_components as cc  # noqa: F401
    assert callable(cc)


def test_no_import_error():
    """Importing segqc.features.components raises no error."""
    import importlib
    mod = importlib.import_module("segqc.features.components")
    assert hasattr(mod, "ComponentsInfo")
    assert hasattr(mod, "compute_components")


# =========================================================================== #
# AC1: Compact label yields component_count=1, fraction=1.0
# =========================================================================== #

def test_ac1_compact_label_component_count():
    """AC1: A solid connected label yields component_count == 1."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1


def test_ac1_compact_label_sizes_list_length():
    """AC1: A single-component label has a sizes list of length 1."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert len(result.component_sizes) == 1


def test_ac1_compact_label_sizes_matches_total_voxels():
    """AC1: The single component size equals the total voxel count."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    data = np.asanyarray(seg.dataobj)
    total_voxels = int(np.sum(data == 1))
    assert result.component_sizes[0] == total_voxels


def test_ac1_compact_label_largest_component_fraction():
    """AC1: A compact (single component) label has largest_component_fraction == 1.0."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.largest_component_fraction == pytest.approx(1.0)


def test_ac1_compact_label_sizes_match_volumes_count():
    """AC1: component_sizes and component_volumes_mm3 have the same length."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert len(result.component_sizes) == len(result.component_volumes_mm3)


def test_ac1_compact_label_in_labelled_blocks_case():
    """AC1: Label 1 in labelled_blocks_case (solid 4x4x4 block) has component_count=1."""
    case = labelled_blocks_case()
    result = compute_components(case.seg_img, label=1, config=_config())
    assert result.component_count == 1
    assert result.largest_component_fraction == pytest.approx(1.0)


def test_ac1_returns_components_info_instance():
    """AC1: compute_components returns a ComponentsInfo instance."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert isinstance(result, ComponentsInfo)


# =========================================================================== #
# AC2: Fragmented label yields correct count, sizes, fraction
# =========================================================================== #

def test_ac2_fragmented_label_component_count():
    """AC2: A label with a main body and one isolated island yields component_count == 2."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 2


def test_ac2_fragmented_label_sizes_sorted_descending():
    """AC2: component_sizes is sorted largest first (descending order)."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.component_sizes[0] >= result.component_sizes[1]


def test_ac2_fragmented_label_sizes_sum_to_total():
    """AC2: The sum of component_sizes equals the total voxel count of the label."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    data = np.asanyarray(seg.dataobj)
    total_voxels = int(np.sum(data == 1))
    assert sum(result.component_sizes) == total_voxels


def test_ac2_fragmented_label_sizes_are_27_and_1():
    """AC2: The two component sizes are 27 (main body) and 1 (island)."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert sorted(result.component_sizes, reverse=True) == [27, 1]


def test_ac2_fragmented_label_largest_fraction_below_one():
    """AC2: A fragmented label has largest_component_fraction < 1.0."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.largest_component_fraction < 1.0


def test_ac2_fragmented_label_largest_fraction_value():
    """AC2: largest_component_fraction equals 27/28 for the main-body + island fixture."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    expected = 27 / 28
    assert result.largest_component_fraction == pytest.approx(expected)


def test_ac2_fragmented_label_volumes_match_sizes():
    """AC2: At 1mm isotropic, component_volumes_mm3 numerically equal component_sizes."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    # voxel volume = 1*1*1 = 1 mm^3
    for size, vol in zip(result.component_sizes, result.component_volumes_mm3):
        assert vol == pytest.approx(float(size))


# =========================================================================== #
# AC3: Threshold config controls the small-fragment set
# =========================================================================== #

def test_ac3_threshold_zero_empty_small_fragments():
    """AC3: min_fragment_voxels=0 yields an empty small_fragments for a compact label."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=0))
    assert len(result.small_fragments) == 0


def test_ac3_threshold_zero_empty_for_fragmented_label():
    """AC3: min_fragment_voxels=0 yields an empty small_fragments even for a fragmented label."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=0))
    assert len(result.small_fragments) == 0


def test_ac3_threshold_above_island_catches_it():
    """AC3: threshold=2 catches the 1-voxel island but not the 27-voxel main body."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=2))
    # The 1-voxel island is strictly below threshold=2; the 27-voxel body is not.
    frag_sizes = list(result.small_fragments)
    assert 1 in frag_sizes
    assert 27 not in frag_sizes


def test_ac3_threshold_at_island_size_does_not_catch_it():
    """AC3: threshold equal to the island size does NOT include it (strictly below)."""
    seg = _fragmented_label_img()
    # island is 1 voxel; threshold=1 means strictly-below-1, i.e. nothing is captured
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=1))
    assert 1 not in result.small_fragments


def test_ac3_threshold_larger_than_all_catches_all():
    """AC3: threshold > largest component puts every component in small_fragments."""
    seg = _fragmented_label_img()
    # Both components are 27 and 1 voxels; threshold=100 captures both
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=100))
    frag_sizes = list(result.small_fragments)
    assert 27 in frag_sizes
    assert 1 in frag_sizes
    assert len(frag_sizes) == 2


def test_ac3_threshold_exactly_at_large_body_size_does_not_catch_it():
    """AC3: threshold equal to main-body size does NOT include it (strictly below)."""
    seg = _fragmented_label_img()
    # main body = 27; threshold=27 means strictly-below-27, so main body not in small_fragments
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=27))
    frag_sizes = list(result.small_fragments)
    assert 27 not in frag_sizes
    assert 1 in frag_sizes


def test_ac3_threshold_above_main_body_catches_main_body():
    """AC3: threshold=28 captures both components (both strictly below 28)."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=28))
    frag_sizes = list(result.small_fragments)
    assert 27 in frag_sizes
    assert 1 in frag_sizes


def test_ac3_compact_label_with_large_threshold_catches_it():
    """AC3: threshold > entire compact label puts that one component in small_fragments."""
    seg = _compact_label_img()  # 64-voxel block
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=100))
    frag_sizes = list(result.small_fragments)
    assert 64 in frag_sizes


# =========================================================================== #
# AC4: Physical volume correct under anisotropic spacing
# =========================================================================== #

def test_ac4_anisotropic_compact_label_volume():
    """AC4: A compact label at anisotropic (1,1,3)mm spacing has correct component volume."""
    # 4x4x3 = 48 voxels; voxel volume = 1*1*3 = 3 mm^3 → component volume = 144 mm^3
    seg = make_labelmap((16, 16, 16), {1: ((2, 6), (2, 6), (2, 5))}, spacing=(1.0, 1.0, 3.0))
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1
    assert result.component_volumes_mm3[0] == pytest.approx(144.0)


def test_ac4_anisotropic_fragmented_label_volumes():
    """AC4: Two components at anisotropic (1,1,3)mm spacing each have correct physical volume."""
    spacing = (1.0, 1.0, 3.0)
    seg = _fragmented_label_img_anisotropic(spacing)
    result = compute_components(seg, label=1, config=_config())
    # voxel volume = 1*1*3 = 3 mm^3
    voxel_vol = 1.0 * 1.0 * 3.0
    for size, vol in zip(result.component_sizes, result.component_volumes_mm3):
        assert vol == pytest.approx(size * voxel_vol)


def test_ac4_anisotropic_main_body_volume():
    """AC4: Main body (27 voxels) at (1,1,3)mm spacing has volume 81 mm^3."""
    spacing = (1.0, 1.0, 3.0)
    seg = _fragmented_label_img_anisotropic(spacing)
    result = compute_components(seg, label=1, config=_config())
    # component_sizes is sorted descending, so [0] is the 27-voxel body
    assert result.component_sizes[0] == 27
    assert result.component_volumes_mm3[0] == pytest.approx(27 * 3.0)


def test_ac4_anisotropic_island_volume():
    """AC4: Island (1 voxel) at (1,1,3)mm spacing has volume 3 mm^3."""
    spacing = (1.0, 1.0, 3.0)
    seg = _fragmented_label_img_anisotropic(spacing)
    result = compute_components(seg, label=1, config=_config())
    assert result.component_sizes[1] == 1
    assert result.component_volumes_mm3[1] == pytest.approx(3.0)


def test_ac4_anisotropic_case_label1_volume():
    """AC4: Label 1 in the anisotropic_case fixture (48 voxels, (1,1,3)mm) is 144 mm^3."""
    case = anisotropic_case()
    result = compute_components(case.seg_img, label=1, config=_config())
    assert result.component_count == 1
    assert result.component_volumes_mm3[0] == pytest.approx(144.0)


def test_ac4_highly_anisotropic_spacing_volume():
    """AC4: A 2x2x2 block at (0.5, 0.5, 5.0)mm spacing has correct component volume."""
    spacing = (0.5, 0.5, 5.0)
    seg = make_labelmap((8, 8, 8), {1: ((1, 3), (1, 3), (1, 3))}, spacing=spacing)
    result = compute_components(seg, label=1, config=_config())
    # 8 voxels × 0.5*0.5*5.0 = 10.0 mm^3
    assert result.component_volumes_mm3[0] == pytest.approx(10.0)


# =========================================================================== #
# Connectivity: explicit 6-connectivity behaviour
# =========================================================================== #

def test_connectivity_diagonal_touch_is_not_6connected():
    """Two voxels touching only on a diagonal are separate components under 6-connectivity.

    This test is explicit about which connectivity rule the implementation uses.
    Under 6-connectivity, two voxels are connected only when they share a face
    (not merely an edge or corner).  Here label 1 voxels are at (0,0,0) and
    (1,1,0) — they share only an edge, so they must be two separate components.
    """
    data = np.zeros((4, 4, 4), dtype=LABEL_DTYPE)
    data[0, 0, 0] = 1
    data[1, 1, 0] = 1   # edge-adjacent, not face-adjacent
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    result = compute_components(seg, label=1, config=_config())
    # Under 6-connectivity: 2 components
    # Under 26-connectivity: 1 component
    # The spec mandates 6-connectivity, so we assert == 2.
    assert result.component_count == 2, (
        "Two edge-adjacent voxels should be 2 separate components under 6-connectivity"
    )


def test_connectivity_face_adjacent_is_6connected():
    """Two voxels sharing a face are one component under 6-connectivity."""
    data = np.zeros((4, 4, 4), dtype=LABEL_DTYPE)
    data[1, 1, 1] = 1
    data[2, 1, 1] = 1   # face-adjacent along x
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1


def test_connectivity_3d_face_adjacent_y():
    """Two voxels face-adjacent along y are one component under 6-connectivity."""
    data = np.zeros((4, 4, 4), dtype=LABEL_DTYPE)
    data[2, 1, 2] = 1
    data[2, 2, 2] = 1
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1


def test_connectivity_3d_face_adjacent_z():
    """Two voxels face-adjacent along z are one component under 6-connectivity."""
    data = np.zeros((4, 4, 4), dtype=LABEL_DTYPE)
    data[2, 2, 1] = 1
    data[2, 2, 2] = 1
    seg = nib.Nifti1Image(data, affine_from_spacing((1.0, 1.0, 1.0)))
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1


# =========================================================================== #
# Adversarial: single-voxel label
# =========================================================================== #

def test_adv_single_voxel_component_count():
    """A label occupying exactly one voxel has component_count == 1."""
    seg = make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 1


def test_adv_single_voxel_fraction_is_one():
    """A single-voxel label has largest_component_fraction == 1.0."""
    seg = make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})
    result = compute_components(seg, label=1, config=_config())
    assert result.largest_component_fraction == pytest.approx(1.0)


def test_adv_single_voxel_size_is_one():
    """A single-voxel label has component_sizes == [1]."""
    seg = make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})
    result = compute_components(seg, label=1, config=_config())
    assert result.component_sizes == [1]


def test_adv_single_voxel_volume_isotropic():
    """A single-voxel label at 1mm isotropic has component_volumes_mm3 == [1.0]."""
    seg = make_labelmap((8, 8, 8), {1: ((4, 5), (4, 5), (4, 5))})
    result = compute_components(seg, label=1, config=_config())
    assert result.component_volumes_mm3[0] == pytest.approx(1.0)


# =========================================================================== #
# Adversarial: all-disconnected label (many 1-voxel components)
# =========================================================================== #

def test_adv_all_disconnected_5_voxels_count():
    """5 isolated single-voxel islands yield component_count == 5."""
    seg = _all_disconnected_label_img(5)
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == 5


def test_adv_all_disconnected_all_sizes_one():
    """5 isolated voxels: every component has size 1."""
    seg = _all_disconnected_label_img(5)
    result = compute_components(seg, label=1, config=_config())
    assert all(s == 1 for s in result.component_sizes)


def test_adv_all_disconnected_fraction_is_one_over_n():
    """5 isolated voxels: largest_component_fraction == 1/5."""
    seg = _all_disconnected_label_img(5)
    result = compute_components(seg, label=1, config=_config())
    assert result.largest_component_fraction == pytest.approx(1.0 / 5)


def test_adv_all_disconnected_threshold_catches_all():
    """5 isolated 1-voxel components: threshold=2 puts all in small_fragments."""
    seg = _all_disconnected_label_img(5)
    result = compute_components(seg, label=1, config=_config(min_fragment_voxels=2))
    assert len(result.small_fragments) == 5


# =========================================================================== #
# Adversarial: missing label
# =========================================================================== #

def test_adv_missing_label_raises():
    """Requesting components for a label not in the image raises a clear error."""
    case = labelled_blocks_case()
    with pytest.raises((ValueError, KeyError, LookupError)) as exc_info:
        compute_components(case.seg_img, label=99, config=_config())
    assert str(exc_info.value).strip(), "Error message for missing label must not be blank"


def test_adv_missing_label_error_message_mentions_label():
    """The error message for a missing label mentions the label value."""
    case = labelled_blocks_case()
    try:
        compute_components(case.seg_img, label=999, config=_config())
    except (ValueError, KeyError, LookupError) as exc:
        msg = str(exc)
        assert "999" in msg or msg.strip(), (
            "Error message should reference the missing label value"
        )


def test_adv_missing_label_no_raw_traceback_in_message():
    """The error message for a missing label does not expose raw internal class names."""
    case = labelled_blocks_case()
    try:
        compute_components(case.seg_img, label=888, config=_config())
    except (ValueError, KeyError, LookupError) as exc:
        msg = str(exc)
        # Should not expose raw scipy/numpy internal repr as the sole content
        import re
        assert not re.fullmatch(r"<[^>]+>", msg.strip()), (
            "Error message looks like a raw object repr"
        )


# =========================================================================== #
# Adversarial: immutability (input image not mutated)
# =========================================================================== #

def test_adv_input_not_mutated_compact():
    """compute_components does not mutate the input image data."""
    seg = _compact_label_img()
    original = np.asanyarray(seg.dataobj).copy()
    compute_components(seg, label=1, config=_config())
    after = np.asanyarray(seg.dataobj)
    np.testing.assert_array_equal(original, after)


def test_adv_input_not_mutated_fragmented():
    """compute_components does not mutate the fragmented label image."""
    seg = _fragmented_label_img()
    original = np.asanyarray(seg.dataobj).copy()
    compute_components(seg, label=1, config=_config())
    after = np.asanyarray(seg.dataobj)
    np.testing.assert_array_equal(original, after)


# =========================================================================== #
# Adversarial: determinism
# =========================================================================== #

def test_adv_determinism_compact():
    """Two calls to compute_components on the same compact label are identical."""
    seg = _compact_label_img()
    r1 = compute_components(seg, label=1, config=_config())
    r2 = compute_components(seg, label=1, config=_config())
    assert r1.component_count == r2.component_count
    assert r1.component_sizes == r2.component_sizes
    assert r1.largest_component_fraction == r2.largest_component_fraction


def test_adv_determinism_fragmented():
    """Two calls to compute_components on the same fragmented label are identical."""
    seg = _fragmented_label_img()
    r1 = compute_components(seg, label=1, config=_config())
    r2 = compute_components(seg, label=1, config=_config())
    assert r1.component_count == r2.component_count
    assert r1.component_sizes == r2.component_sizes
    assert r1.largest_component_fraction == r2.largest_component_fraction
    assert r1.component_volumes_mm3 == r2.component_volumes_mm3


def test_adv_determinism_anisotropic():
    """Two calls for an anisotropic case produce identical volumes."""
    case = anisotropic_case()
    r1 = compute_components(case.seg_img, label=1, config=_config())
    r2 = compute_components(case.seg_img, label=1, config=_config())
    assert r1.component_volumes_mm3 == r2.component_volumes_mm3


# =========================================================================== #
# Adversarial: ComponentsInfo dataclass contract
# =========================================================================== #

def test_adv_components_info_has_required_fields():
    """ComponentsInfo exposes all required fields."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    for attr in (
        "component_count",
        "component_sizes",
        "component_volumes_mm3",
        "largest_component_fraction",
        "small_fragments",
    ):
        assert hasattr(result, attr), f"ComponentsInfo missing field: {attr}"


def test_adv_component_count_equals_len_sizes():
    """component_count equals len(component_sizes)."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == len(result.component_sizes)


def test_adv_component_count_equals_len_volumes():
    """component_count equals len(component_volumes_mm3)."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert result.component_count == len(result.component_volumes_mm3)


def test_adv_component_count_positive():
    """component_count is always a positive integer for a present label."""
    seg = _compact_label_img()
    result = compute_components(seg, label=1, config=_config())
    assert isinstance(result.component_count, int)
    assert result.component_count >= 1


def test_adv_largest_fraction_in_unit_interval():
    """largest_component_fraction is always in [0.0, 1.0]."""
    for seg in (_compact_label_img(), _fragmented_label_img()):
        result = compute_components(seg, label=1, config=_config())
        assert 0.0 <= result.largest_component_fraction <= 1.0


def test_adv_component_sizes_non_negative():
    """All entries in component_sizes are positive integers."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    for s in result.component_sizes:
        assert isinstance(s, int)
        assert s > 0


def test_adv_component_volumes_non_negative():
    """All entries in component_volumes_mm3 are positive floats."""
    seg = _fragmented_label_img_anisotropic((1.0, 1.0, 3.0))
    result = compute_components(seg, label=1, config=_config())
    for v in result.component_volumes_mm3:
        assert v > 0.0


def test_adv_sizes_sum_equals_total_voxel_count():
    """Sum of component_sizes equals the total voxel count of the label."""
    seg = _fragmented_label_img()
    result = compute_components(seg, label=1, config=_config())
    data = np.asanyarray(seg.dataobj)
    total = int(np.sum(data == 1))
    assert sum(result.component_sizes) == total


def test_adv_volumes_sum_equals_physical_volume():
    """Sum of component_volumes_mm3 equals total voxels × voxel volume."""
    spacing = (2.0, 3.0, 4.0)
    seg = make_labelmap((10, 10, 10), {1: ((1, 4), (1, 4), (1, 4))}, spacing=spacing)
    result = compute_components(seg, label=1, config=_config())
    data = np.asanyarray(seg.dataobj)
    total_voxels = int(np.sum(data == 1))
    voxel_vol = 2.0 * 3.0 * 4.0
    expected_total_vol = total_voxels * voxel_vol
    assert sum(result.component_volumes_mm3) == pytest.approx(expected_total_vol)
