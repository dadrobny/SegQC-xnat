"""Tests for item 063 -- extending reference distributions with per-level
intensity feature distributions (``src/segfacet/reference/{ingest,schema,artifact}.py``).

Covers Acceptance Criteria AC1-AC16:

- AC1: ``INGESTED_INTENSITY_FEATURES`` equals the pinned 13-name tuple;
  ``INGESTED_FEATURES`` (geometry) stays byte-identical, no intensity leak.
- AC2: default ``with_intensity=False`` ingestion is geometry-only even when
  a sibling scan exists.
- AC3: ``with_intensity=True`` + aligned painted scan folds in per-label
  intensity stats matching ``compute_label_intensity`` exactly.
- AC4: ``with_intensity=True`` with no sibling scan degrades to
  geometry-only, no raise.
- AC5: an all-NaN-under-label scan contributes no ``intensity_*`` key for
  that label (never a ``None`` value in ``features``).
- AC6: a grid-misaligned scan raises ``ValueError``.
- AC7: ingestion stays deterministic and read-only under
  ``with_intensity=True``.
- AC8: ``aggregate_reference`` tracks intensity features with no core change
  (guarded by a source-text marker on ``aggregate.py``, plus
  hand-verifiable stats).
- AC9: schema version bumped to "1.2" (item 081) and enforced by the loader.
- AC10: ``build_reference`` threads ``with_intensity`` (default on).
- AC11: ``build_default_cohort`` writes a painted, aligned, reproducible
  scan per subject.
- AC12: the bundled artifact carries per-level intensity distributions for
  L1-L5 under schema "1.2".
- AC13: enabling intensity does not alter geometric stats.
- AC14: the existing delta computation stays inert on intensity reference
  features.
- AC15: the bundled artifact regenerates byte-identically.
- AC16: intensity-bearing and geometry-only references both round-trip.

Adversarial / edge-case scenarios included:
- A cohort mixing a scan-bearing subject and a scan-less subject under
  ``with_intensity=True``: intensity for the former only, no crash.
- A NaN-filled label alongside a normal label in the same subject: only the
  NaN label's record omits intensity keys.
- ``with_intensity=True`` over a scan-less cohort still loads under "1.2"
  (backward tolerance).
- Idempotent regeneration: two ``build_and_write_default`` calls to two
  different temp destinations reproduce identical bytes.
"""

from __future__ import annotations

import copy
import inspect
import json
import os

import nibabel as nib
import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.features.intensity import compute_label_intensity
from segfacet.labels import LabelConvention
from segfacet.pipeline import extract_feature_record
from segfacet.reference import (
    ARTIFACT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    Provenance,
    ReferenceArtifactError,
    aggregate_reference,
    bundled_default_reference,
    build_and_write_default,
    build_default_cohort,
    build_reference,
    compute_reference_delta,
    default_artifact_path,
    from_dict,
    load_artifact,
    to_dict,
    write_artifact,
)
from segfacet.reference.ingest import (
    DEFAULT_SEG_SUFFIX,
    INGESTED_FEATURES,
    ingest_cohort,
    ingest_subject,
)
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.golden import assert_matches_committed_artifact
from segfacet.synth.intensity import paint_clean_scan

# INGESTED_INTENSITY_FEATURES is item 063's new companion constant -- not yet
# part of the module's stable exports at spec time, so import it directly
# from the ingest submodule per the item spec's "Public interface" section.
from segfacet.reference.ingest import INGESTED_INTENSITY_FEATURES

PROV = Provenance(
    source="test-cohort", config_hash="cfg-hash", build_date="2000-01-01"
)

EXPECTED_INTENSITY_FEATURES = (
    "intensity_mean",
    "intensity_median",
    "intensity_std",
    "intensity_min",
    "intensity_max",
    "intensity_p05",
    "intensity_p25",
    "intensity_p50",
    "intensity_p75",
    "intensity_p95",
    "intensity_range",
    "intensity_iqr",
    "intensity_entropy",
)


# =========================================================================== #
# Fixture helpers
# =========================================================================== #


def _painted_case(dest_dir, subject_id, levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0)):
    """Write ``<subject_id>_seg.nii.gz`` + a painted ``_scan.nii.gz`` sibling.

    The scan is item 058's deterministic HU painter (``paint_clean_scan``),
    seeded 0 -- distinct from ``build_clean_spine``'s own trivial ramp
    ``scan_img``, and the source item 063's ingestion path is meant to read.
    """
    spine = build_clean_spine(levels=levels, spacing=spacing)
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    seg_path = dest_dir / f"{subject_id}{DEFAULT_SEG_SUFFIX}"
    scan_path = dest_dir / f"{subject_id}_scan.nii.gz"
    nib.save(spine.seg_img, str(seg_path))
    nib.save(scan_img, str(scan_path))
    return spine, seg_path, scan_path


def _geom_stats(dist, level_name, stratum="all"):
    """The ``INGESTED_FEATURES`` subset of a level's ``feature_stats``."""
    level_dist = dist.levels[level_name][stratum]
    return {
        name: stats
        for name, stats in level_dist.feature_stats.items()
        if name in INGESTED_FEATURES
    }


def _nan_under_label(scan_img, seg_img, label):
    """Return a float32 copy of ``scan_img`` with all voxels under ``label``
    replaced by NaN (produces item 059's all-``None`` sentinel for that
    label when fed through ``compute_label_intensity``)."""
    seg_data = np.asanyarray(seg_img.dataobj)
    scan_data = np.asanyarray(scan_img.dataobj).astype(np.float32)
    scan_data[seg_data == label] = np.nan
    return nib.Nifti1Image(scan_data, scan_img.affine)


# =========================================================================== #
# AC1: new intensity vocabulary constant; geometry vocabulary unchanged
# =========================================================================== #


def test_ac1_intensity_vocabulary_constant_and_geometry_unchanged():
    assert INGESTED_INTENSITY_FEATURES == EXPECTED_INTENSITY_FEATURES
    assert INGESTED_FEATURES == (
        "physical_volume_mm3",
        "extent_x_mm",
        "extent_y_mm",
        "extent_z_mm",
        "spline_offset_mm",
    )
    assert not any(name.startswith("intensity_") for name in INGESTED_FEATURES)


# =========================================================================== #
# AC2: intensity opt-in; default ingestion is geometry-only
# =========================================================================== #


def test_ac2_default_ingestion_is_geometry_only_despite_scan_present(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))

    result_subject = ingest_subject(
        tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}",
        config=bundled_default_config(),
        scan_path=tmp_path / "sub-000_scan.nii.gz",
    )  # with_intensity defaults False
    for record in result_subject.records:
        assert not any(k.startswith("intensity_") for k in record.features)

    result_cohort = ingest_cohort(tmp_path)  # with_intensity defaults False
    for record in result_cohort.records:
        assert not any(k.startswith("intensity_") for k in record.features)


# =========================================================================== #
# AC3: with_intensity=True + aligned scan folds in matching per-label stats
# =========================================================================== #


def test_ac3_with_intensity_true_folds_in_matching_stats(tmp_path):
    spine, seg_path, scan_path = _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    convention = LabelConvention.default()

    result = ingest_subject(
        seg_path,
        config=bundled_default_config(),
        scan_path=scan_path,
        with_intensity=True,
    )

    scan_img = nib.load(str(scan_path))
    for record in result.records:
        label_value = convention.value_of(record.level_name)
        expected = compute_label_intensity(scan_img, spine.seg_img, label_value)
        for field_name in (
            "mean", "median", "std", "min", "max",
            "p05", "p25", "p50", "p75", "p95", "range", "iqr", "entropy",
        ):
            expected_value = getattr(expected, field_name)
            key = f"intensity_{field_name}"
            if expected_value is None:
                assert key not in record.features
            else:
                assert record.features[key] == pytest.approx(expected_value)


# =========================================================================== #
# AC4: with_intensity=True, no scan -> geometry-only, no raise
# =========================================================================== #


def test_ac4_with_intensity_true_no_scan_degrades_to_geometry_only(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    seg_path = tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}"
    nib.save(spine.seg_img, str(seg_path))

    result = ingest_subject(
        seg_path,
        config=bundled_default_config(),
        scan_path=None,
        with_intensity=True,
    )  # must not raise

    assert len(result.records) == 2
    for record in result.records:
        assert not any(k.startswith("intensity_") for k in record.features)
        assert "physical_volume_mm3" in record.features


# =========================================================================== #
# AC5: sentinel intensity contributes no key (never a None value)
# =========================================================================== #


def test_ac5_all_nan_label_omits_intensity_keys(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    convention = LabelConvention.default()
    l1_label = convention.value_of("L1")
    nan_scan_img = _nan_under_label(scan_img, spine.seg_img, l1_label)

    seg_path = tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}"
    scan_path = tmp_path / "sub-000_scan.nii.gz"
    nib.save(spine.seg_img, str(seg_path))
    nib.save(nan_scan_img, str(scan_path))

    result = ingest_subject(
        seg_path,
        config=bundled_default_config(),
        scan_path=scan_path,
        with_intensity=True,
    )

    by_level = {r.level_name: r for r in result.records}
    for key in by_level["L1"].features:
        assert not key.startswith("intensity_")
        assert by_level["L1"].features[key] is not None
    assert any(k.startswith("intensity_") for k in by_level["L2"].features)
    for value in by_level["L2"].features.values():
        assert value is not None


# =========================================================================== #
# AC6: a grid-misaligned scan raises ValueError
# =========================================================================== #


def test_ac6_misaligned_scan_raises_value_error(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    seg_path = tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}"
    nib.save(spine.seg_img, str(seg_path))

    # A scan with a different array shape than the seg -- structural
    # misalignment, not a per-label data condition.
    mismatched_shape = tuple(d + 1 for d in spine.seg_img.shape)
    bad_scan_data = np.zeros(mismatched_shape, dtype=np.int16)
    bad_scan_img = nib.Nifti1Image(bad_scan_data, spine.seg_img.affine)
    scan_path = tmp_path / "sub-000_scan.nii.gz"
    nib.save(bad_scan_img, str(scan_path))

    with pytest.raises(ValueError):
        ingest_subject(
            seg_path,
            config=bundled_default_config(),
            scan_path=scan_path,
            with_intensity=True,
        )


# =========================================================================== #
# AC7: deterministic and read-only under with_intensity=True
# =========================================================================== #


def test_ac7_ingestion_deterministic_and_read_only_with_intensity(tmp_path):
    for i in range(2):
        _painted_case(tmp_path, f"sub-{i:03d}", levels=("L1", "L2", "L3"))

    config = bundled_default_config()
    config_before = copy.deepcopy(config)
    convention = LabelConvention.default()
    convention_before = dict(convention.value_to_name)
    listing_before = sorted(os.listdir(tmp_path))

    result1 = ingest_cohort(tmp_path, config=config, convention=convention, with_intensity=True)
    result2 = ingest_cohort(tmp_path, config=config, convention=convention, with_intensity=True)

    assert [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy) for r in result1.records
    ] == [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy) for r in result2.records
    ]
    assert any(
        any(k.startswith("intensity_") for k in r.features) for r in result1.records
    )
    assert sorted(os.listdir(tmp_path)) == listing_before
    assert config == config_before
    assert dict(convention.value_to_name) == convention_before


# =========================================================================== #
# AC8: aggregate_reference tracks intensity with no core change
# =========================================================================== #


def test_ac8_aggregate_reference_tracks_intensity_with_no_core_change(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    _painted_case(tmp_path, "sub-001", levels=("L1", "L2"))

    result = ingest_cohort(tmp_path, with_intensity=True)
    dist = aggregate_reference(result.records, provenance=PROV)

    intensity_names_present = {
        name for name in dist.features if name.startswith("intensity_")
    }
    assert intensity_names_present  # at least one intensity feature tracked
    assert intensity_names_present <= set(INGESTED_INTENSITY_FEATURES)
    for name in ("physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm"):
        assert name in dist.features

    # Hand-verify one intensity feature's stats against the raw record values.
    l1_records = [r for r in result.records if r.level_name == "L1" and "intensity_mean" in r.features]
    assert l1_records
    values = [r.features["intensity_mean"] for r in l1_records]
    stats = dist.levels["L1"]["all"].feature_stats["intensity_mean"]
    assert stats.count == len(values)
    assert stats.mean == pytest.approx(sum(values) / len(values))
    assert stats.min == pytest.approx(min(values))
    assert stats.max == pytest.approx(max(values))

    # Guard: aggregate.py carries no intensity-specific special-casing --
    # it is generic over any named feature per item 043's design, and this
    # item's Assumptions/Implementation Steps mandate the file stays
    # unmodified. A source-text marker check catches an accidental edit
    # that special-cases the "intensity" vocabulary.
    from segfacet.reference import aggregate as aggregate_module

    source = inspect.getsource(aggregate_module)
    assert "intensity" not in source.lower()


# =========================================================================== #
# AC9: schema version bumped and enforced
# =========================================================================== #


def test_ac9_schema_version_bumped_and_enforced(tmp_path):
    # Item 081 bumped the schema to "1.2" (additive morphology vocabulary);
    # this test's own version-bump/enforcement behaviour is otherwise
    # unaffected -- only the literal is updated.
    assert SCHEMA_VERSION == "1.2"
    assert ARTIFACT_SCHEMA_VERSION == "1.2"

    _painted_case(tmp_path, "sub-000", levels=("L1",))
    dist = build_reference(tmp_path, source="s", build_date="2026-07-11")
    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)

    loaded = load_artifact(out_path)  # must not raise
    assert loaded.schema_version == "1.2"

    import json

    data = json.loads(out_path.read_text(encoding="utf-8"))
    data["schema_version"] = "1.0"
    out_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReferenceArtifactError):
        load_artifact(out_path)


# =========================================================================== #
# AC10: build_reference threads with_intensity (default on)
# =========================================================================== #


def test_ac10_build_reference_threads_with_intensity(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    _painted_case(tmp_path, "sub-001", levels=("L1", "L2"))

    dist_on = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=True
    )
    dist_off = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=False
    )

    assert any(name.startswith("intensity_") for name in dist_on.features)
    assert not any(name.startswith("intensity_") for name in dist_off.features)


def test_ac10_build_reference_default_with_intensity_is_true(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))

    default_dist = build_reference(tmp_path, source="s", build_date="2026-07-11")
    explicit_on = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=True
    )
    assert set(default_dist.features) == set(explicit_on.features)


# =========================================================================== #
# AC11: build_default_cohort writes a painted, aligned, reproducible scan
# =========================================================================== #


def test_ac11_build_default_cohort_writes_aligned_reproducible_scans(tmp_path):
    from segfacet.io import load_case

    dest1 = tmp_path / "cohort1"
    dest2 = tmp_path / "cohort2"
    build_default_cohort(dest1)
    build_default_cohort(dest2)

    seg_files = sorted(p for p in os.listdir(dest1) if p.endswith("_seg.nii.gz"))
    assert seg_files  # non-empty

    for seg_name in seg_files:
        subject_id = seg_name[: -len("_seg.nii.gz")]
        scan_name = f"{subject_id}_scan.nii.gz"
        assert (dest1 / scan_name).exists()

        case = load_case(dest1 / scan_name, dest1 / seg_name)  # must not raise
        assert case.seg.data.shape == case.scan.data.shape

        # int16 array byte-reproducible across the two independent builds.
        scan_img_1 = nib.load(str(dest1 / scan_name))
        scan_img_2 = nib.load(str(dest2 / scan_name))
        data_1 = np.asanyarray(scan_img_1.dataobj)
        data_2 = np.asanyarray(scan_img_2.dataobj)
        assert np.array_equal(data_1, data_2)
        assert scan_img_1.get_data_dtype() == np.int16


# =========================================================================== #
# AC12: the bundled artifact carries per-level intensity for L1-L5
# =========================================================================== #


def test_ac12_bundled_artifact_carries_intensity_distributions_for_lumbar_levels():
    dist = bundled_default_reference()

    assert dist.schema_version == "1.2"
    assert any(name.startswith("intensity_") for name in dist.features)

    for level_name in ("L1", "L2", "L3", "L4", "L5"):
        assert level_name in dist.levels
        level_dist = dist.levels[level_name]["all"]
        tracked_intensity = [
            name for name in level_dist.feature_stats if name.startswith("intensity_")
        ]
        assert tracked_intensity, f"level {level_name} has no tracked intensity stats"


# =========================================================================== #
# AC13: enabling intensity does not alter geometric stats
# =========================================================================== #


def test_ac13_geometric_stats_identical_with_and_without_intensity(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2", "L3"))
    _painted_case(tmp_path, "sub-001", levels=("L1", "L2", "L3"))

    dist_on = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=True
    )
    dist_off = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=False
    )

    for level_name in ("L1", "L2", "L3"):
        geom_on = _geom_stats(dist_on, level_name)
        geom_off = _geom_stats(dist_off, level_name)
        assert set(geom_on.keys()) == set(geom_off.keys())
        for feature_name, stats_on in geom_on.items():
            stats_off = geom_off[feature_name]
            assert stats_on == stats_off


def test_ac13_default_cohort_geometric_stats_identical_on_off_intensity():
    import tempfile
    from pathlib import Path

    dist_on = bundled_default_reference()  # with_intensity=True (default build)
    with tempfile.TemporaryDirectory() as tmp_dir:
        cohort_dir = build_default_cohort(Path(tmp_dir))
        dist_off = build_reference(
            cohort_dir,
            source="synthetic-verse-cohort",
            build_date="2026-07-11",
            with_intensity=False,
        )

    for level_name in ("L1", "L2", "L3", "L4", "L5"):
        geom_on = _geom_stats(dist_on, level_name)
        geom_off = _geom_stats(dist_off, level_name)
        assert set(geom_on.keys()) == set(geom_off.keys())
        for feature_name, stats_on in geom_on.items():
            assert stats_on == geom_off[feature_name]


# =========================================================================== #
# AC14: the existing delta computation stays inert on intensity
# =========================================================================== #


def test_ac14_delta_computation_stays_inert_on_intensity():
    bundled = bundled_default_reference()
    assert any(name.startswith("intensity_") for name in bundled.features)

    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    config = bundled_default_config()
    features_block = extract_feature_record(spine.seg_img, config)

    delta = compute_reference_delta(features_block, bundled)

    for label, label_delta in delta.per_label.items():
        for feature_delta in label_delta.features:
            assert not feature_delta.feature.startswith("intensity_")
        for name in label_delta.out_of_range_features:
            assert not name.startswith("intensity_")


# =========================================================================== #
# AC15: the bundled artifact regenerates byte-identically
# =========================================================================== #


def test_ac15_bundled_artifact_regenerates_byte_identically(tmp_path):
    dest1 = tmp_path / "regen1.json"
    dest2 = tmp_path / "regen2.json"
    build_and_write_default(dest1)
    build_and_write_default(dest2)

    # Item 081: the bundled artifact now carries a platform-sensitive PCA
    # float (eigenvalue_ratio), so the regenerated-vs-committed comparison
    # switches to numeric tolerance (item 127's assert_matches_committed_artifact,
    # item 078's reports_close semantics). Intra-platform determinism across
    # two independent regenerations stays byte-exact (asserted separately
    # above).
    assert dest1.read_bytes() == dest2.read_bytes()
    regenerated = json.loads(dest1.read_text(encoding="utf-8"))
    assert_matches_committed_artifact(regenerated, default_artifact_path())


def test_ac15_gitattributes_still_pins_bundled_artifact_lf():
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    text = (repo_root / ".gitattributes").read_text(encoding="utf-8")
    matching_lines = [
        line
        for line in text.splitlines()
        if "src/segfacet/reference/reference_default.json" in line
    ]
    assert any("text eol=lf" in line for line in matching_lines)


# =========================================================================== #
# AC16: intensity and geometry-only references both round-trip
# =========================================================================== #


def test_ac16_intensity_bearing_reference_round_trips(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    dist = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=True
    )
    assert any(name.startswith("intensity_") for name in dist.features)

    assert from_dict(to_dict(dist)) == dist

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)
    assert loaded == dist


def test_ac16_geometry_only_reference_under_new_schema_round_trips(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    dist = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=False
    )
    assert dist.schema_version == "1.2"
    assert not any(name.startswith("intensity_") for name in dist.features)

    assert from_dict(to_dict(dist)) == dist

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)  # must not raise under "1.2"
    assert loaded == dist


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_mixed_scan_bearing_and_scan_less_subjects(tmp_path):
    _painted_case(tmp_path, "sub-000", levels=("L1", "L2"))
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    nib.save(spine.seg_img, str(tmp_path / f"sub-001{DEFAULT_SEG_SUFFIX}"))
    # sub-001 deliberately has no sibling scan file.

    result = ingest_cohort(tmp_path, with_intensity=True)  # must not raise

    by_subject = {s.subject_id: s for s in result.subjects}
    assert any(
        any(k.startswith("intensity_") for k in r.features)
        for r in by_subject["sub-000"].records
    )
    for record in by_subject["sub-001"].records:
        assert not any(k.startswith("intensity_") for k in record.features)


def test_adv_nan_label_alongside_normal_label_siblings_keep_keys(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"), spacing=(1.0, 1.0, 1.0))
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    convention = LabelConvention.default()
    l2_label = convention.value_of("L2")
    nan_scan_img = _nan_under_label(scan_img, spine.seg_img, l2_label)

    seg_path = tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}"
    scan_path = tmp_path / "sub-000_scan.nii.gz"
    nib.save(spine.seg_img, str(seg_path))
    nib.save(nan_scan_img, str(scan_path))

    result = ingest_subject(
        seg_path, config=bundled_default_config(), scan_path=scan_path, with_intensity=True
    )
    by_level = {r.level_name: r for r in result.records}
    assert not any(k.startswith("intensity_") for k in by_level["L2"].features)
    assert any(k.startswith("intensity_") for k in by_level["L1"].features)
    assert any(k.startswith("intensity_") for k in by_level["L3"].features)


def test_adv_with_intensity_true_over_scan_less_cohort_loads_under_new_schema(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, 1.0))
    nib.save(spine.seg_img, str(tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}"))

    dist = build_reference(
        tmp_path, source="s", build_date="2026-07-11", with_intensity=True
    )
    assert dist.schema_version == "1.2"
    assert not any(name.startswith("intensity_") for name in dist.features)

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)  # backward-tolerant: no raise
    assert loaded == dist


def test_adv_regeneration_is_idempotent(tmp_path):
    dest1 = tmp_path / "run1.json"
    dest2 = tmp_path / "run2.json"
    build_and_write_default(dest1)
    build_and_write_default(dest2)
    assert dest1.read_bytes() == dest2.read_bytes()
