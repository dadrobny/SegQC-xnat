"""Tests for item 058 -- intensity-bearing synthetic scan fixtures (HU-painted
clean scan + implausible-intensity variants), and the new parallel committed
intensity corpus (``tests/corpus/intensity/``).

Covers Acceptance Criteria AC1-AC21:

- AC1-AC6 (Group A, clean HU painter): grid alignment (shape/affine/dtype);
  per-label median inside the bone-plausible band; cortical rim strictly
  brighter than the cancellous interior; background soft-tissue-low and
  separable from every vertebra; non-mutation of the input seg; seeded
  determinism + seed-sensitivity.
- AC7-AC11 (Group B, implausible variants): a variant differs from the clean
  scan only inside the target mask (seg untouched); the metal variant's
  target median is implausibly bright (>= 2500); the soft-tissue variant's
  target median is implausibly low (<= 100); the degenerate-uniform variant
  is exactly constant on the target; variants preserve geometry and are
  deterministic per (target, fill, seed).
- AC12-AC17 (Group C, committed corpus & manifest): the manifest loads,
  is versioned, and round-trips; exactly one clean + >=2 implausible cases
  with distinct/filesystem-safe ids and distinct scan_fixture paths; every
  fixture exists and loads via load_case; every case's label map is the
  clean GT (byte-identical voxel counts); committed implausible fixtures
  differ from the clean fixture only in the target mask; manifest expected
  bands and hu_model equal the painter's ground truth (no drift).
- AC18-AC21 (Group D, reproducibility & pinning): write_intensity_corpus
  reproduces every committed fixture's loaded content; two write calls are
  byte-identical to each other and to the committed corpus; main(["--out",
  tmp]) returns 0 and reproduces the case-id set; .gitattributes pins the
  new intensity fixtures.

Adversarial / edge-case scenarios included:
- An all-background (label-free) seg painted by paint_clean_scan yields a
  background-only int16 scan with no crash.
- A target_label absent from the seg makes paint_implausible_variant a
  no-op equal to the clean scan (no spurious change, no crash).
- The degenerate-uniform variant's constant value is within the int16 range.
- The metal variant's HU values never exceed the int16 max (clean clip).
- Re-running write_intensity_corpus over an existing directory reproduces
  identical bytes (idempotent regeneration).
- load_intensity_manifest on the committed file and on a fresh
  write_intensity_corpus output (a different directory) produce equal
  cases (relocatable, path-relative).
- Requesting an unknown fill name from IMPLAUSIBLE_FILLS is detected as a
  KeyError rather than silently falling back to a default.
"""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from segfacet.io import load_case
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.intensity import (
    DEFAULT_HU_MODEL,
    IMPLAUSIBLE_FILLS,
    INTENSITY_CORPUS_DIR,
    INTENSITY_FIXTURES_DIRNAME,
    INTENSITY_MANIFEST_PATH,
    INTENSITY_MANIFEST_VERSION,
    load_intensity_manifest,
    main,
    paint_clean_scan,
    paint_implausible_variant,
    write_intensity_corpus,
)

_CASE_ID_RE = re.compile(r"^[a-z0-9_]+$")

_BONE_BAND = (100, 1500)
_METAL_MIN = 2500
_SOFT_TISSUE_MAX = 100
_INT16_MIN, _INT16_MAX = -32768, 32767


# =========================================================================== #
# Helpers
# =========================================================================== #


def _seg():
    """A fresh clean-GT seg image (labels 20-24), per the item spec."""
    return build_clean_spine().seg_img


def _seg_data(seg_img):
    return np.asanyarray(seg_img.dataobj)


def _scan_data(scan_img):
    return np.asanyarray(scan_img.dataobj)


def _under(arr, seg_data, label):
    return arr[seg_data == label]


def _manifest():
    return load_intensity_manifest()


def _cases():
    return _manifest()["cases"]


def _case(case_id):
    for c in _cases():
        if c["case_id"] == case_id:
            return c
    raise AssertionError(f"case_id {case_id!r} not found in the committed intensity manifest")


def _resolve(case, key):
    return INTENSITY_CORPUS_DIR / case[key]


def _loaded(case):
    return load_case(_resolve(case, "scan_fixture"), _resolve(case, "seg_fixture"))


# =========================================================================== #
# A. Clean HU painter (AC1-AC6)
# =========================================================================== #


def test_ac1_clean_scan_is_grid_aligned_with_the_label_map():
    """AC1: paint_clean_scan(seg_img) returns a Nifti1Image whose shape
    equals seg_img's, whose affine is np.array_equal to seg_img's, and whose
    array dtype is int16."""
    seg_img = _seg()
    scan_img = paint_clean_scan(seg_img)

    assert scan_img.shape == seg_img.shape
    assert np.array_equal(np.asarray(scan_img.affine), np.asarray(seg_img.affine))
    assert _scan_data(scan_img).dtype == np.int16


def test_ac2_every_present_label_painted_in_bone_plausible_band():
    """AC2: for every present label L, the median HU under L lies within
    [100, 1500] inclusive."""
    seg_img = _seg()
    seg_data = _seg_data(seg_img)
    scan_data = _scan_data(paint_clean_scan(seg_img))

    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    assert labels  # sanity: the clean spine has vertebrae
    for label in labels:
        median = float(np.median(_under(scan_data, seg_data, label)))
        assert _BONE_BAND[0] <= median <= _BONE_BAND[1], (label, median)


def test_ac3_cortical_rim_brighter_than_cancellous_interior():
    """AC3: for every present label L, the mean HU over the rim (mask minus
    its one-voxel binary erosion) exceeds the mean HU over the interior
    (the eroded mask) by a strictly positive margin."""
    from scipy.ndimage import binary_erosion

    seg_img = _seg()
    seg_data = _seg_data(seg_img)
    scan_data = _scan_data(paint_clean_scan(seg_img))

    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    for label in labels:
        mask = seg_data == label
        interior = binary_erosion(mask)
        rim = mask & ~interior
        assert interior.any() and rim.any(), label  # holds for the default spine
        rim_mean = float(scan_data[rim].mean())
        interior_mean = float(scan_data[interior].mean())
        assert rim_mean > interior_mean, (label, rim_mean, interior_mean)


def test_ac4_background_is_soft_tissue_low_and_separable_from_bone():
    """AC4: the median HU over background (non-labelled) voxels lies within
    background_mean +/- 3*background_std, and is strictly below the minimum
    per-label median across all vertebrae."""
    seg_img = _seg()
    seg_data = _seg_data(seg_img)
    scan_data = _scan_data(paint_clean_scan(seg_img))

    background_median = float(np.median(scan_data[seg_data == 0]))
    lo = DEFAULT_HU_MODEL.background_mean - 3 * DEFAULT_HU_MODEL.background_std
    hi = DEFAULT_HU_MODEL.background_mean + 3 * DEFAULT_HU_MODEL.background_std
    assert lo <= background_median <= hi

    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    per_label_medians = [
        float(np.median(_under(scan_data, seg_data, label))) for label in labels
    ]
    assert background_median < min(per_label_medians)


def test_ac5_painter_does_not_mutate_its_input():
    """AC5: the seg_img array is np.array_equal before and after
    paint_clean_scan(seg_img)."""
    seg_img = _seg()
    before = _seg_data(seg_img).copy()
    paint_clean_scan(seg_img)
    after = _seg_data(seg_img)
    assert np.array_equal(before, after)


def test_ac6_clean_painter_is_deterministic_and_seed_sensitive():
    """AC6: two paint_clean_scan(seg_img, seed=0) calls return
    np.array_equal arrays; seed=1 differs from seed=0 while still
    satisfying AC2 (bone-plausible per-label medians)."""
    seg_img = _seg()
    seg_data = _seg_data(seg_img)

    scan_a = _scan_data(paint_clean_scan(seg_img, seed=0))
    scan_b = _scan_data(paint_clean_scan(seg_img, seed=0))
    assert np.array_equal(scan_a, scan_b)

    scan_c = _scan_data(paint_clean_scan(seg_img, seed=1))
    assert not np.array_equal(scan_a, scan_c)

    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    for label in labels:
        median = float(np.median(_under(scan_c, seg_data, label)))
        assert _BONE_BAND[0] <= median <= _BONE_BAND[1], (label, median)


# =========================================================================== #
# B. Implausible-intensity variants (AC7-AC11)
# =========================================================================== #


def test_ac7_metal_variant_differs_from_clean_only_inside_target_mask():
    """AC7: the metal variant (target_label=22) equals the clean array at
    every voxel where seg.data != 22, differs at >= 1 voxel where seg.data
    == 22, and leaves the seg array unchanged."""
    seg_img = _seg()
    seg_data_before = _seg_data(seg_img).copy()
    clean_img = paint_clean_scan(seg_img)
    clean_data = _scan_data(clean_img)

    variant_img = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["metal"]
    )
    variant_data = _scan_data(variant_img)
    seg_data = _seg_data(seg_img)

    assert np.array_equal(seg_data, seg_data_before)  # label map untouched
    outside = seg_data != 22
    assert np.array_equal(variant_data[outside], clean_data[outside])
    inside = seg_data == 22
    assert not np.array_equal(variant_data[inside], clean_data[inside])


def test_ac8_metal_variant_target_median_is_implausibly_bright():
    """AC8: the median HU under the target label in the metal variant is
    >= 2500."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    variant_img = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["metal"]
    )
    seg_data = _seg_data(seg_img)
    variant_data = _scan_data(variant_img)
    median = float(np.median(_under(variant_data, seg_data, 22)))
    assert median >= _METAL_MIN


def test_ac9_soft_tissue_variant_target_median_is_implausibly_low():
    """AC9: the median HU under the target label in the soft-tissue variant
    is <= 100."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    variant_img = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["soft_tissue"]
    )
    seg_data = _seg_data(seg_img)
    variant_data = _scan_data(variant_img)
    median = float(np.median(_under(variant_data, seg_data, 22)))
    assert median <= _SOFT_TISSUE_MAX


def test_ac10_degenerate_uniform_variant_is_constant_on_target():
    """AC10: in the degenerate-uniform variant, the set of distinct HU
    values under the target label has size exactly 1."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    variant_img = paint_implausible_variant(
        clean_img,
        seg_img,
        target_label=22,
        fill=IMPLAUSIBLE_FILLS["degenerate_uniform"],
    )
    seg_data = _seg_data(seg_img)
    variant_data = _scan_data(variant_img)
    values = np.unique(_under(variant_data, seg_data, 22))
    assert values.size == 1


def test_ac11_variants_preserve_geometry_and_are_deterministic():
    """AC11: paint_implausible_variant returns a scan whose shape equals and
    whose affine is np.array_equal to seg_img's; two calls with the same
    (target_label, fill, seed) return np.array_equal arrays."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)

    variant_a = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["metal"], seed=0
    )
    assert variant_a.shape == seg_img.shape
    assert np.array_equal(np.asarray(variant_a.affine), np.asarray(seg_img.affine))

    variant_b = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["metal"], seed=0
    )
    assert np.array_equal(_scan_data(variant_a), _scan_data(variant_b))


# =========================================================================== #
# C. Committed intensity corpus & manifest (AC12-AC17)
# =========================================================================== #


def test_ac12_intensity_manifest_loads_versioned_and_round_trips():
    """AC12: load_intensity_manifest() returns a dict with manifest_version
    == INTENSITY_MANIFEST_VERSION (== 1) and a non-empty cases list; the
    committed manifest.json parses via json.loads and round-trips through
    json.dumps/json.loads unchanged."""
    manifest = load_intensity_manifest()
    assert isinstance(manifest, dict)
    assert manifest["manifest_version"] == INTENSITY_MANIFEST_VERSION == 1
    assert isinstance(manifest["cases"], list)
    assert len(manifest["cases"]) > 0

    parsed = json.loads(INTENSITY_MANIFEST_PATH.read_text())
    assert parsed == manifest
    assert json.loads(json.dumps(manifest)) == manifest


def test_ac13_one_clean_case_and_at_least_two_implausible_cases():
    """AC13: exactly one case has plausible == true with target_label is
    None; at least two cases have plausible == false with a non-null
    integer target_label; all case_id values are distinct and match
    ^[a-z0-9_]+$; every case's scan_fixture path is distinct."""
    cases = _cases()

    clean_cases = [c for c in cases if c["plausible"] is True]
    assert len(clean_cases) == 1
    assert clean_cases[0]["target_label"] is None

    implausible_cases = [c for c in cases if c["plausible"] is False]
    assert len(implausible_cases) >= 2
    for c in implausible_cases:
        assert c["target_label"] is not None
        assert isinstance(c["target_label"], int)

    ids = [c["case_id"] for c in cases]
    assert len(ids) == len(set(ids))
    for cid in ids:
        assert _CASE_ID_RE.match(cid), f"case_id {cid!r} is not filesystem-safe"

    scan_paths = [c["scan_fixture"] for c in cases]
    assert len(scan_paths) == len(set(scan_paths))


def test_ac14_every_fixture_exists_and_loads_via_stage0_loader():
    """AC14: for every case, the resolved scan_fixture and seg_fixture
    exist, load_case(scan, seg) returns a Case without raising, with
    matching shapes and a non-empty label_inventory."""
    for case in _cases():
        assert _resolve(case, "scan_fixture").exists(), case["case_id"]
        assert _resolve(case, "seg_fixture").exists(), case["case_id"]
        loaded = _loaded(case)
        assert loaded.scan.data.shape == loaded.seg.data.shape, case["case_id"]
        assert len(loaded.label_inventory) > 0, case["case_id"]


def test_ac15_every_case_label_map_is_the_clean_gt():
    """AC15: for every case, the loaded seg's label_inventory keys are
    exactly {20, 21, 22, 23, 24}, each with build_clean_spine()'s voxel
    count for that label."""
    clean = build_clean_spine()
    for case in _cases():
        loaded = _loaded(case)
        assert set(loaded.label_inventory.keys()) == {20, 21, 22, 23, 24}, case["case_id"]
        for label, count in loaded.label_inventory.items():
            assert count == clean.voxel_counts[label], (case["case_id"], label)


def test_ac16_committed_implausible_fixtures_differ_only_in_target_mask():
    """AC16: for every plausible == false case, the loaded scan array equals
    the loaded clean-case scan array at all voxels where seg.data !=
    target_label, and differs at >= 1 voxel where seg.data ==
    target_label."""
    clean_case = next(c for c in _cases() if c["plausible"] is True)
    clean_loaded = _loaded(clean_case)
    clean_scan_data = clean_loaded.scan.data

    implausible_cases = [c for c in _cases() if c["plausible"] is False]
    assert implausible_cases
    for case in implausible_cases:
        loaded = _loaded(case)
        target = case["target_label"]
        seg_data = loaded.seg.data
        scan_data = loaded.scan.data

        outside = seg_data != target
        assert np.array_equal(scan_data[outside], clean_scan_data[outside]), case["case_id"]
        inside = seg_data == target
        assert not np.array_equal(scan_data[inside], clean_scan_data[inside]), case["case_id"]


def test_ac17_manifest_expected_bands_equal_painter_ground_truth():
    """AC17: for every case, expected_label_hu_bands equals what the
    painter/model produces for that case, and the manifest's top-level
    hu_model equals DEFAULT_HU_MODEL as a dict."""
    manifest = _manifest()
    hu_model_dict = manifest["hu_model"]
    for field in ("background_mean", "background_std", "cancellous_mean",
                  "cancellous_std", "cortical_mean", "cortical_std", "dtype"):
        assert hu_model_dict[field] == getattr(DEFAULT_HU_MODEL, field)

    clean_case = next(c for c in _cases() if c["plausible"] is True)
    for label_str, band in clean_case["expected_label_hu_bands"].items():
        assert band == [_BONE_BAND[0], _BONE_BAND[1]], label_str

    for case in _cases():
        if case["plausible"]:
            continue
        target_str = str(case["target_label"])
        assert target_str in case["expected_label_hu_bands"], case["case_id"]
        band = case["expected_label_hu_bands"][target_str]
        fill_name = case["fill"]["name"]
        if fill_name == "metal":
            assert band[0] >= _METAL_MIN, case["case_id"]
        elif fill_name == "soft_tissue":
            assert band[1] <= _SOFT_TISSUE_MAX, case["case_id"]


# =========================================================================== #
# D. Reproducibility & .gitattributes pinning (AC18-AC21)
# =========================================================================== #


def test_ac18_regeneration_reproduces_every_committed_fixtures_content(tmp_path):
    """AC18: write_intensity_corpus(tmp) into a fresh temp dir yields, for
    every case, a scan and seg whose loaded arrays and affines are
    np.array_equal to the committed fixtures."""
    dest = tmp_path / "regen"
    write_intensity_corpus(dest)
    fresh_manifest = load_intensity_manifest(dest / "manifest.json")

    for fresh_case in fresh_manifest["cases"]:
        fresh = load_case(
            dest / fresh_case["scan_fixture"], dest / fresh_case["seg_fixture"]
        )
        committed = _loaded(_case(fresh_case["case_id"]))

        assert np.array_equal(fresh.seg.data, committed.seg.data), fresh_case["case_id"]
        assert np.array_equal(fresh.scan.data, committed.scan.data), fresh_case["case_id"]
        assert np.array_equal(fresh.seg.affine, committed.seg.affine), fresh_case["case_id"]
        assert np.array_equal(fresh.scan.affine, committed.scan.affine), fresh_case["case_id"]


def test_ac19_regeneration_is_byte_identical_across_runs_and_vs_committed(tmp_path):
    """AC19: two successive write_intensity_corpus calls into two fresh
    temp dirs produce byte-for-byte identical fixture files and
    manifest.json; each regenerated file is byte-for-byte identical to its
    committed counterpart."""
    dest1 = tmp_path / "run1"
    dest2 = tmp_path / "run2"
    manifest_path1 = write_intensity_corpus(dest1)
    manifest_path2 = write_intensity_corpus(dest2)

    assert manifest_path1.read_bytes() == manifest_path2.read_bytes()
    assert manifest_path1.read_bytes() == INTENSITY_MANIFEST_PATH.read_bytes()

    fixtures1 = sorted((dest1 / INTENSITY_FIXTURES_DIRNAME).glob("*.nii.gz"))
    fixtures2 = sorted((dest2 / INTENSITY_FIXTURES_DIRNAME).glob("*.nii.gz"))
    assert [p.name for p in fixtures1] == [p.name for p in fixtures2]
    assert len(fixtures1) > 0

    for f1, f2 in zip(fixtures1, fixtures2):
        assert f1.read_bytes() == f2.read_bytes(), f1.name
        committed = INTENSITY_CORPUS_DIR / INTENSITY_FIXTURES_DIRNAME / f1.name
        assert f1.read_bytes() == committed.read_bytes(), f1.name


def test_ac20_one_command_regeneration_entry_point_runs(tmp_path):
    """AC20: segfacet.synth.intensity.main(["--out", tmp]) returns 0 and writes
    a manifest.json that load_intensity_manifest(tmp/manifest.json) parses
    to a dict with the same set of case_ids as the committed manifest."""
    out_dir = tmp_path / "regen_main"
    rc = main(["--out", str(out_dir)])
    assert rc == 0

    regenerated = load_intensity_manifest(out_dir / "manifest.json")
    committed_ids = {c["case_id"] for c in _cases()}
    regenerated_ids = {c["case_id"] for c in regenerated["cases"]}
    assert regenerated_ids == committed_ids


def test_ac21_gitattributes_pins_the_new_intensity_fixtures():
    """AC21: .gitattributes contains a rule pinning
    tests/corpus/intensity/manifest.json to text eol=lf and a rule marking
    tests/corpus/intensity/fixtures/*.nii.gz as binary."""
    repo_root = INTENSITY_CORPUS_DIR.resolve().parents[2]
    gitattributes = (repo_root / ".gitattributes").read_text()

    assert re.search(
        r"tests/corpus/intensity/manifest\.json\s+text\s+eol=lf", gitattributes
    )
    assert re.search(
        r"tests/corpus/intensity/fixtures/\*\.nii\.gz\s+binary", gitattributes
    )


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_all_background_seg_paints_without_crash():
    """Adversarial: an all-background (label-free) seg painted by
    paint_clean_scan yields a background-only int16 scan with no crash --
    no labels to iterate, purely background noise."""
    empty_seg_data = np.zeros((6, 6, 6), dtype=np.uint16)
    affine = np.eye(4)
    import nibabel as nib

    empty_seg_img = nib.Nifti1Image(empty_seg_data, affine)
    scan_img = paint_clean_scan(empty_seg_img)
    scan_data = _scan_data(scan_img)

    assert scan_data.shape == empty_seg_data.shape
    assert scan_data.dtype == np.int16
    median = float(np.median(scan_data))
    lo = DEFAULT_HU_MODEL.background_mean - 3 * DEFAULT_HU_MODEL.background_std
    hi = DEFAULT_HU_MODEL.background_mean + 3 * DEFAULT_HU_MODEL.background_std
    assert lo <= median <= hi


def test_adv_target_label_absent_is_a_no_op():
    """Adversarial: a target_label that is absent from the seg makes
    paint_implausible_variant a no-op equal to the clean scan -- no
    spurious change, no crash."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    clean_data = _scan_data(clean_img)

    absent_label = 999
    seg_data = _seg_data(seg_img)
    assert not np.any(seg_data == absent_label)  # sanity

    variant_img = paint_implausible_variant(
        clean_img, seg_img, target_label=absent_label, fill=IMPLAUSIBLE_FILLS["metal"]
    )
    variant_data = _scan_data(variant_img)
    assert np.array_equal(variant_data, clean_data)


def test_adv_degenerate_uniform_constant_within_int16_range():
    """Adversarial: the degenerate-uniform variant's constant value under
    the target label is within the int16 range -- no overflow/clip
    surprise."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    variant_img = paint_implausible_variant(
        clean_img,
        seg_img,
        target_label=22,
        fill=IMPLAUSIBLE_FILLS["degenerate_uniform"],
    )
    seg_data = _seg_data(seg_img)
    variant_data = _scan_data(variant_img)
    values = _under(variant_data, seg_data, 22)
    assert _INT16_MIN <= int(values[0]) <= _INT16_MAX


def test_adv_metal_variant_hu_values_never_exceed_int16_max():
    """Adversarial: metal HU clips cleanly to the int16 max where a seeded
    draw would otherwise exceed it -- deterministic, no wraparound into
    negative values."""
    seg_img = _seg()
    clean_img = paint_clean_scan(seg_img)
    variant_img = paint_implausible_variant(
        clean_img, seg_img, target_label=22, fill=IMPLAUSIBLE_FILLS["metal"]
    )
    seg_data = _seg_data(seg_img)
    variant_data = _scan_data(variant_img)
    values = _under(variant_data, seg_data, 22)
    assert values.max() <= _INT16_MAX
    assert values.min() >= _INT16_MIN
    # No wraparound: every value stays strongly positive/bright, never flips
    # to a spuriously negative HU from int16 overflow.
    assert values.min() > 0


def test_adv_write_intensity_corpus_idempotent_over_existing_directory(tmp_path):
    """Adversarial: re-running write_intensity_corpus over an
    already-populated directory reproduces identical bytes (idempotent
    regeneration)."""
    dest = tmp_path / "idempotent"
    write_intensity_corpus(dest)
    manifest_bytes_1 = (dest / "manifest.json").read_bytes()
    fixture_bytes_1 = {
        p.name: p.read_bytes()
        for p in (dest / INTENSITY_FIXTURES_DIRNAME).glob("*.nii.gz")
    }

    write_intensity_corpus(dest)
    manifest_bytes_2 = (dest / "manifest.json").read_bytes()
    fixture_bytes_2 = {
        p.name: p.read_bytes()
        for p in (dest / INTENSITY_FIXTURES_DIRNAME).glob("*.nii.gz")
    }

    assert manifest_bytes_1 == manifest_bytes_2
    assert fixture_bytes_1 == fixture_bytes_2


def test_adv_load_intensity_manifest_committed_and_relocated_produce_equal_cases(tmp_path):
    """Adversarial: load_intensity_manifest() on the committed file and on a
    fresh write_intensity_corpus output under a *different* directory
    produce equal cases lists -- the manifest is relocatable because
    fixture paths are manifest-relative."""
    dest = tmp_path / "relocated"
    write_intensity_corpus(dest)
    fresh = load_intensity_manifest(dest / "manifest.json")
    committed = load_intensity_manifest()
    assert fresh["cases"] == committed["cases"]


def test_adv_unknown_fill_name_raises_keyerror():
    """Adversarial: requesting a fill type that does not exist from
    IMPLAUSIBLE_FILLS raises a KeyError rather than silently falling back
    to a default fill."""
    with pytest.raises(KeyError):
        IMPLAUSIBLE_FILLS["not_a_real_fill_type"]
