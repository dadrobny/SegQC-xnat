"""Tests for item 044 -- VerSe GT ingestion: cohort loader & feature-extraction
driver (``src/segfacet/reference/ingest.py``).

Covers Acceptance Criteria AC1-AC14:

- AC1: one FeatureRecord per (subject, present-level) over an N-subject,
  L-level cohort -- exactly N x L records, one per present level per subject.
- AC2: emitted geometry features equal the real ``extract_feature_record``
  values for the same image (byte/float-equal), confirming the driver reads
  the real feature engine.
- AC3: ``spline_offset_mm`` is populated for a >=2-level subject and equals
  ``stage3.per_label_offsets[*].offset_mm``.
- AC4: every record's ``level_name`` is a member of ``CANONICAL_ORDER``.
- AC5: a subject missing an interior level ingests without error and
  contributes no record for that level.
- AC6: unknown/unmapped integer labels are skipped, not turned into levels,
  and recorded in ``SubjectIngest.skipped_labels``.
- AC7: transitional anatomy (T13/L6) ingests as its canonical name without
  crashing the non-contiguous ordering.
- AC8: a per-subject size proxy (mean physical volume) is stamped identically
  on every record for that subject, and ``CohortIngest.size_proxy_name ==
  SIZE_PROXY_NAME``.
- AC9: the flattened records feed ``aggregate_reference`` unchanged
  (``subject_count`` / ``levels`` match).
- AC10: subject-level stratification round-trips through the size proxy.
- AC11: discovery is deterministic and complete -- exactly the
  ``*<seg_suffix>`` files, ordered by ascending ``subject_id``.
- AC12: two independent ``ingest_cohort`` calls over the same directory
  produce field-by-field-equal results.
- AC13: an empty/record-less cohort yields a well-formed empty result that
  composes with ``aggregate_reference``.
- AC14: inputs are not mutated and no wall clock / disk write happens.

Adversarial / edge-case scenarios included:
- Single-level subject: no ``stage3``, so records carry no
  ``spline_offset_mm`` and ingestion does not raise.
- Missing interior level (a gapped span): the omitted level is present for
  other subjects but never for the gapped one.
- Unknown label (value 99 painted into a corner of the volume): surfaces in
  ``skipped_labels``, emits no record for it.
- Transitional label (28 / 29): yields "T13" / "L6" records.
- Empty directory and a directory with only non-matching files
  (``README.txt``, a stray ``_scan.nii.gz`` with no matching ``_seg``).
- Nonexistent cohort directory.
- Duplicate subject_id via an explicit ``ingest_subject(subject_id=...)`` call
  colliding with a cohort file's derived id (checked via CohortIngest
  containing both when both are separately ingested into records list).
- Determinism under a non-alphabetical write order.
- Non-mutation / no writes verified via directory listing + config deep copy.
"""

from __future__ import annotations

import copy
import os

import nibabel as nib
import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.labels import CANONICAL_ORDER, LabelConvention
from segfacet.pipeline import extract_feature_record
from segfacet.reference import Provenance, aggregate_reference
from segfacet.reference.ingest import (
    DEFAULT_SEG_SUFFIX,
    INGESTED_FEATURES,
    SIZE_PROXY_NAME,
    CohortIngest,
    SubjectIngest,
    ingest_cohort,
    ingest_subject,
)
from segfacet.synth.clean_gt import build_clean_spine

PROV = Provenance(
    source="test-cohort", config_hash="cfg-hash", build_date="2000-01-01"
)


# =========================================================================== #
# Fixture helpers
# =========================================================================== #


def _write_subject(dest_dir, subject_id, seg_img, scan_img=None):
    """Write one subject's ``_seg.nii.gz`` (+ optional ``_scan.nii.gz``)."""
    seg_path = dest_dir / f"{subject_id}{DEFAULT_SEG_SUFFIX}"
    nib.save(seg_img, str(seg_path))
    if scan_img is not None:
        scan_path = dest_dir / f"{subject_id}_scan.nii.gz"
        nib.save(scan_img, str(scan_path))
    return seg_path


def _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3", "L4", "L5")):
    """Write N subjects with deterministic per-subject variation to tmp_path.

    Variation comes from ``spacing`` and ``curve_amplitude_mm`` (per the item
    spec's Assumptions: no RNG, fixed and reproducible).
    """
    subject_ids = []
    for i in range(n):
        spine = build_clean_spine(
            levels=levels,
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        subject_id = f"sub-{i:03d}"
        _write_subject(tmp_path, subject_id, spine.seg_img, spine.scan_img)
        subject_ids.append(subject_id)
    return tmp_path, subject_ids


def _zero_label(seg_img, label):
    """Return a new Nifti1Image with all voxels of ``label`` zeroed out."""
    data = np.asanyarray(seg_img.dataobj).copy()
    data[data == label] = 0
    return nib.Nifti1Image(data, seg_img.affine)


def _paint_unknown_label(seg_img, value=99):
    """Return a new Nifti1Image with one corner voxel set to an unknown label."""
    data = np.asanyarray(seg_img.dataobj).copy()
    data[0, 0, 0] = value
    return nib.Nifti1Image(data, seg_img.affine)


# =========================================================================== #
# AC1: one record per (subject, present-level)
# =========================================================================== #


def test_ac1_one_record_per_subject_present_level(tmp_path):
    cohort_dir, subject_ids = _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3"))
    result = ingest_cohort(cohort_dir)

    assert len(result.records) == 3 * 3
    for subject in result.subjects:
        level_names = [r.level_name for r in subject.records]
        assert len(level_names) == 3
        assert set(level_names) == {"L1", "L2", "L3"}
        assert len(set(level_names)) == len(level_names)  # exactly one per level


# =========================================================================== #
# AC2: emitted geometry matches the real feature engine
# =========================================================================== #


def test_ac2_emitted_features_match_extracted_geometry(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    _write_subject(tmp_path, "sub-000", spine.seg_img, spine.scan_img)

    config = bundled_default_config()
    result = ingest_cohort(tmp_path, config=config)
    subject = result.subjects[0]

    block = extract_feature_record(spine.seg_img, config)
    for label_str, entry in block["per_label"].items():
        level_name = entry["level_name"]
        record = next(r for r in subject.records if r.level_name == level_name)
        geometry = entry["geometry"]
        assert record.features["physical_volume_mm3"] == geometry["physical_volume_mm3"]
        assert record.features["extent_x_mm"] == geometry["extent_x_mm"]
        assert record.features["extent_y_mm"] == geometry["extent_y_mm"]
        assert record.features["extent_z_mm"] == geometry["extent_z_mm"]


# =========================================================================== #
# AC3: spline_offset_mm populated for >=2-level subject
# =========================================================================== #


def test_ac3_spline_offset_populated_for_multi_level_subject(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    _write_subject(tmp_path, "sub-000", spine.seg_img, spine.scan_img)

    config = bundled_default_config()
    result = ingest_cohort(tmp_path, config=config)
    subject = result.subjects[0]

    block = extract_feature_record(spine.seg_img, config)
    offsets_by_label = {
        entry["label"]: entry["offset_mm"]
        for entry in block["stage3"]["per_label_offsets"]
    }
    level_name_by_label = {
        int(k): v["level_name"] for k, v in block["per_label"].items()
    }

    for record in subject.records:
        label = next(
            lbl for lbl, name in level_name_by_label.items() if name == record.level_name
        )
        assert "spline_offset_mm" in record.features
        offset = record.features["spline_offset_mm"]
        assert offset == pytest.approx(offsets_by_label[label])
        assert np.isfinite(offset)


# =========================================================================== #
# AC4: level names normalised to canonical names
# =========================================================================== #


def test_ac4_level_names_are_canonical(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))
    result = ingest_cohort(cohort_dir)

    assert len(result.records) > 0
    for record in result.records:
        assert record.level_name in CANONICAL_ORDER
        assert record.level_name != "20"


# =========================================================================== #
# AC5: missing interior level tolerated
# =========================================================================== #


def test_ac5_missing_interior_level_ingests_without_error(tmp_path):
    convention = LabelConvention.default()

    complete = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    _write_subject(tmp_path, "sub-000", complete.seg_img, complete.scan_img)

    gapped_source = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    l2_label = convention.value_of("L2")
    gapped_seg = _zero_label(gapped_source.seg_img, l2_label)
    _write_subject(tmp_path, "sub-001", gapped_seg, gapped_source.scan_img)

    result = ingest_cohort(tmp_path)  # must not raise

    gapped_subject = next(s for s in result.subjects if s.subject_id == "sub-001")
    gapped_levels = {r.level_name for r in gapped_subject.records}
    assert "L2" not in gapped_levels
    assert gapped_levels == {"L1", "L3"}

    # No record anywhere in the cohort carries subject_id "sub-001" & level L2.
    assert not any(
        r.subject_id == "sub-001" and r.level_name == "L2" for r in result.records
    )
    # L2 is still present for the other (complete) subject.
    assert any(r.level_name == "L2" for r in result.records)


# =========================================================================== #
# AC6: unknown labels skipped, recorded in skipped_labels
# =========================================================================== #


def test_ac6_unknown_label_is_skipped_not_ingested(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    seg_with_unknown = _paint_unknown_label(spine.seg_img, value=99)
    _write_subject(tmp_path, "sub-000", seg_with_unknown, spine.scan_img)

    result = ingest_cohort(tmp_path)
    subject = result.subjects[0]

    assert 99 in subject.skipped_labels
    assert not any(r.level_name not in CANONICAL_ORDER for r in subject.records)
    assert len(subject.records) == 2  # only L1, L2 -- no fabricated record for 99


# =========================================================================== #
# AC7: transitional anatomy (T13 / L6)
# =========================================================================== #


def test_ac7_transitional_label_ingests_as_canonical_name(tmp_path):
    convention = LabelConvention.default()

    spine = build_clean_spine(levels=("T12",), spacing=(1.0, 1.0, 1.0))
    t13_value = convention.value_of("T13")
    data = np.asanyarray(spine.seg_img.dataobj).copy()
    t12_value = convention.value_of("T12")
    data[data == t12_value] = t13_value
    seg_img = nib.Nifti1Image(data, spine.seg_img.affine)
    _write_subject(tmp_path, "sub-000", seg_img, spine.scan_img)

    result = ingest_cohort(tmp_path)  # must not raise / crash on non-contiguous rank
    subject = result.subjects[0]

    assert len(subject.records) == 1
    assert subject.records[0].level_name == "T13"


def test_ac7_l6_label_ingests_as_canonical_name(tmp_path):
    convention = LabelConvention.default()

    spine = build_clean_spine(levels=("L5",), spacing=(1.0, 1.0, 1.0))
    l6_value = convention.value_of("L6")
    l5_value = convention.value_of("L5")
    data = np.asanyarray(spine.seg_img.dataobj).copy()
    data[data == l5_value] = l6_value
    seg_img = nib.Nifti1Image(data, spine.seg_img.affine)
    _write_subject(tmp_path, "sub-000", seg_img, spine.scan_img)

    result = ingest_cohort(tmp_path)
    subject = result.subjects[0]

    assert len(subject.records) == 1
    assert subject.records[0].level_name == "L6"


# =========================================================================== #
# AC8: per-subject size proxy
# =========================================================================== #


def test_ac8_size_proxy_stamped_identically_on_every_subject_record(tmp_path):
    cohort_dir, subject_ids = _write_cohort(tmp_path, n=2, levels=("L1", "L2", "L3"))
    result = ingest_cohort(cohort_dir, with_size_proxy=True)

    assert result.size_proxy_name == SIZE_PROXY_NAME

    for subject in result.subjects:
        proxies = {r.size_proxy for r in subject.records}
        assert len(proxies) == 1  # identical across the subject's records
        proxy = proxies.pop()
        assert proxy is not None
        expected = sum(r.features["physical_volume_mm3"] for r in subject.records) / len(
            subject.records
        )
        assert proxy == pytest.approx(expected)


def test_ac8_size_proxy_disabled_yields_none(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1", "L2"))
    result = ingest_cohort(cohort_dir, with_size_proxy=False)

    assert result.size_proxy_name is None
    for record in result.records:
        assert record.size_proxy is None


# =========================================================================== #
# AC9: composes with aggregate_reference unchanged
# =========================================================================== #


def test_ac9_flattened_records_feed_aggregate_reference_unchanged(tmp_path):
    cohort_dir, subject_ids = _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3"))
    result = ingest_cohort(cohort_dir)

    dist = aggregate_reference(result.records, provenance=PROV)

    assert dist.subject_count == len(subject_ids)
    assert set(dist.levels.keys()) == {"L1", "L2", "L3"}


# =========================================================================== #
# AC10: subject-level stratification round-trips through the size proxy
# =========================================================================== #


def test_ac10_stratification_round_trips_through_size_proxy(tmp_path):
    subject_ids = []
    for i, spacing_z in enumerate([1.0, 3.0]):
        spine = build_clean_spine(
            levels=("L1", "L2"), spacing=(1.0, 1.0, spacing_z)
        )
        subject_id = f"sub-{i:03d}"
        _write_subject(tmp_path, subject_id, spine.seg_img, spine.scan_img)
        subject_ids.append(subject_id)

    result = ingest_cohort(tmp_path)
    proxies = sorted({r.size_proxy for r in result.records})
    assert len(proxies) >= 2

    midpoint = (proxies[0] + proxies[-1]) / 2.0
    dist = aggregate_reference(
        result.records, provenance=PROV, size_strata_edges=[midpoint]
    )
    assert len(dist.strata) > 1


# =========================================================================== #
# AC11: deterministic and complete discovery
# =========================================================================== #


def test_ac11_discovery_is_deterministic_and_complete(tmp_path):
    cohort_dir, subject_ids = _write_cohort(tmp_path, n=3, levels=("L1", "L2"))
    (cohort_dir / "README.txt").write_text("not a subject", encoding="utf-8")
    # A stray scan with no matching _seg file must not be treated as a subject.
    stray_scan = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0)).scan_img
    nib.save(stray_scan, str(cohort_dir / "orphan_scan.nii.gz"))

    result = ingest_cohort(cohort_dir)

    discovered_ids = [s.subject_id for s in result.subjects]
    assert discovered_ids == sorted(subject_ids)
    assert len(result.subjects) == len(subject_ids)


# =========================================================================== #
# AC12: deterministic over a fixed cohort
# =========================================================================== #


def test_ac12_ingestion_is_deterministic_across_calls(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3"))

    result1 = ingest_cohort(cohort_dir)
    result2 = ingest_cohort(cohort_dir)

    assert [s.subject_id for s in result1.subjects] == [
        s.subject_id for s in result2.subjects
    ]
    assert [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy)
        for r in result1.records
    ] == [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy)
        for r in result2.records
    ]


def test_ac12_determinism_survives_nonalphabetical_write_order(tmp_path):
    # Write subjects in reverse-alphabetical filesystem order.
    for subject_id in ["sub-002", "sub-000", "sub-001"]:
        spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
        _write_subject(tmp_path, subject_id, spine.seg_img, spine.scan_img)

    result = ingest_cohort(tmp_path)
    assert [s.subject_id for s in result.subjects] == ["sub-000", "sub-001", "sub-002"]
    record_subject_ids = [r.subject_id for r in result.records]
    assert record_subject_ids == sorted(record_subject_ids)


# =========================================================================== #
# AC13: empty / record-less cohort
# =========================================================================== #


def test_ac13_empty_cohort_yields_well_formed_empty_result(tmp_path):
    result = ingest_cohort(tmp_path)  # empty directory

    assert result.subjects == ()
    assert result.records == ()

    dist = aggregate_reference(result.records, provenance=PROV)
    assert dist.subject_count == 0
    assert dist.levels == {}


def test_ac13_directory_with_only_nonmatching_files_yields_empty_result(tmp_path):
    (tmp_path / "README.txt").write_text("nothing here", encoding="utf-8")
    stray_scan = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0)).scan_img
    nib.save(stray_scan, str(tmp_path / "orphan_scan.nii.gz"))

    result = ingest_cohort(tmp_path)

    assert result.subjects == ()
    assert result.records == ()


# =========================================================================== #
# AC14: no mutation, no wall clock, no writes
# =========================================================================== #


def test_ac14_no_mutation_and_no_writes(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))

    config = bundled_default_config()
    config_before = copy.deepcopy(config)
    convention = LabelConvention.default()
    # LabelConvention is a frozen dataclass whose maps are MappingProxyType,
    # which copy.deepcopy cannot pickle. Snapshot the mapping as a plain dict
    # instead -- picklable, and sufficient to prove the convention's contents
    # are unchanged after the call.
    convention_before = dict(convention.value_to_name)

    listing_before = sorted(os.listdir(cohort_dir))

    ingest_cohort(cohort_dir, config=config, convention=convention)

    listing_after = sorted(os.listdir(cohort_dir))
    assert listing_after == listing_before
    assert config == config_before
    assert dict(convention.value_to_name) == convention_before


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_single_level_subject_no_spline_offset(tmp_path):
    spine = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0))
    _write_subject(tmp_path, "sub-000", spine.seg_img, spine.scan_img)

    result = ingest_cohort(tmp_path)  # must not raise

    assert len(result.records) == 1
    record = result.records[0]
    assert "spline_offset_mm" not in record.features
    for feature_name in ("physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm"):
        assert feature_name in record.features


def test_adv_zero_level_subject_yields_no_records(tmp_path):
    spine = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0))
    empty_data = np.zeros_like(np.asanyarray(spine.seg_img.dataobj))
    empty_seg = nib.Nifti1Image(empty_data, spine.seg_img.affine)
    _write_subject(tmp_path, "sub-000", empty_seg, spine.scan_img)

    result = ingest_cohort(tmp_path)  # must not raise

    subject = result.subjects[0]
    assert subject.records == ()
    assert subject.skipped_labels == ()
    assert result.records == ()


def test_adv_nonexistent_cohort_directory_handled(tmp_path):
    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises((FileNotFoundError, OSError)):
        ingest_cohort(missing_dir)


def test_adv_mixed_real_and_unknown_labels(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    seg_with_unknown = _paint_unknown_label(spine.seg_img, value=77)
    _write_subject(tmp_path, "sub-000", seg_with_unknown, spine.scan_img)

    result = ingest_cohort(tmp_path)
    subject = result.subjects[0]

    assert set(r.level_name for r in subject.records) == {"L1", "L2", "L3"}
    assert 77 in subject.skipped_labels
    assert len(subject.records) == 3


def test_adv_duplicate_subject_id_across_two_ingest_subject_calls(tmp_path):
    spine_a = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0))
    spine_b = build_clean_spine(levels=("L2",), spacing=(1.0, 1.0, 1.0))
    path_a = _write_subject(tmp_path, "case-A", spine_a.seg_img, spine_a.scan_img)
    path_b = _write_subject(tmp_path, "case-B", spine_b.seg_img, spine_b.scan_img)

    config = bundled_default_config()
    result_a = ingest_subject(path_a, config=config, subject_id="dup")
    result_b = ingest_subject(path_b, config=config, subject_id="dup")

    combined = result_a.records + result_b.records
    assert all(r.subject_id == "dup" for r in combined)
    # aggregate_reference correctly folds these into a single subject_count.
    dist = aggregate_reference(combined, provenance=PROV)
    assert dist.subject_count == 1


def test_adv_corrupted_filename_not_matching_suffix_is_ignored(tmp_path):
    spine = build_clean_spine(levels=("L1",), spacing=(1.0, 1.0, 1.0))
    # Deliberately malformed / non-conforming filenames.
    nib.save(spine.seg_img, str(tmp_path / "not_a_subject.nii.gz"))
    nib.save(spine.seg_img, str(tmp_path / "sub-000_segmentation.nii.gz"))

    result = ingest_cohort(tmp_path)

    assert result.subjects == ()
    assert result.records == ()


def test_adv_custom_seg_suffix_is_honoured(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    nib.save(spine.seg_img, str(tmp_path / "sub-000_labels.nii.gz"))
    # This one should NOT be picked up under the custom suffix.
    nib.save(spine.seg_img, str(tmp_path / "sub-001_seg.nii.gz"))

    result = ingest_cohort(tmp_path, seg_suffix="_labels.nii.gz")

    assert [s.subject_id for s in result.subjects] == ["sub-000"]


def test_adv_default_seg_suffix_constant_value():
    assert DEFAULT_SEG_SUFFIX == "_seg.nii.gz"
    assert SIZE_PROXY_NAME == "mean_vertebra_volume_mm3"
    assert "physical_volume_mm3" in INGESTED_FEATURES
    assert "spline_offset_mm" in INGESTED_FEATURES


def test_adv_ingest_subject_returns_dataclass_with_expected_types(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    path = _write_subject(tmp_path, "sub-000", spine.seg_img, spine.scan_img)

    result = ingest_subject(path, config=bundled_default_config())

    assert isinstance(result, SubjectIngest)
    assert result.subject_id == "sub-000"
    assert result.seg_path == str(path)
    assert isinstance(result.records, tuple)
    assert isinstance(result.skipped_labels, tuple)


def test_adv_ingest_cohort_returns_cohortingest_dataclass(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    result = ingest_cohort(cohort_dir)
    assert isinstance(result, CohortIngest)
    assert isinstance(result.subjects, tuple)
    assert isinstance(result.records, tuple)
