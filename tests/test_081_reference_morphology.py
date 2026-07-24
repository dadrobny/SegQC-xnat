"""Tests for item 081 -- expanding the reference feature vocabulary with a
third per-level family, geometric morphology (``src/segfacet/reference/*``).

Covers Acceptance Criteria AC1-AC20:

- AC1: ``INGESTED_MORPHOLOGY_FEATURES`` equals the pinned 3-name tuple and is
  exported in ``segfacet.reference.ingest.__all__``.
- AC2: the geometry/intensity/morphology 3-family split is preserved --
  ``INGESTED_FEATURES``/``INGESTED_INTENSITY_FEATURES`` unchanged, all three
  constants pairwise disjoint.
- AC3: ``fragmentation_index`` is tracked nowhere (no family constant, no
  rebuilt bundled ``feature_stats`` key).
- AC4: default ingestion (``with_morphology=False``) carries no morphology key.
- AC5: ``with_morphology=True`` folds in per-level values matching the
  extractor's own ``components``/orientation blocks for a multi-level subject.
- AC6: a single-label subject omits ``eigenvalue_ratio`` (no Stage 3), never
  inserts ``None``, and does not raise.
- AC7: morphology ingestion is deterministic and read-only.
- AC8: ``aggregate_reference`` tracks morphology with no core change
  (source-text marker on ``aggregate.py`` plus hand-verifiable stats).
- AC9: schema version bumped to "1.2" and enforced by the loader.
- AC10: ``build_reference`` threads ``with_morphology`` (default on).
- AC11: the bundled artifact carries per-level morphology distributions for
  L1-L5 under schema "1.2".
- AC12: enabling morphology does not alter geometric or intensity stats.
- AC13: ``compute_morphology_reference_delta`` scores morphology via its own
  read path (components/orientation blocks, never ``entry["geometry"]``).
- AC14: out-of-range bounds are switchable on the morphology delta.
- AC15: the geometry delta (``compute_reference_delta``) stays inert on
  morphology.
- AC16: the intensity delta (``compute_intensity_reference_delta``) stays
  inert on morphology.
- AC17: the regenerated artifact is intra-platform byte-identical and matches
  the committed file within numeric tolerance (``reports_close``).
- AC18: (verified by edits to ``test_045_reference_artifact.py`` and
  ``test_063_reference_intensity.py`` -- see those files' regeneration tests,
  now comparing regenerated-vs-committed via ``reports_close``.)
- AC19: (verified by edits updating the "1.1" schema-version literals in
  ``test_063_reference_intensity.py`` and ``test_aide_status_report.py`` to
  "1.2".)
- AC20: scope guard -- no ``src/segfacet/features/**`` or ``aggregate.py`` edit,
  ``.gitattributes`` still pins the committed artifact.

Adversarial / edge-case scenarios included:
- A cohort mixing a multi-level and a single-level subject under
  ``with_morphology=True``: ``eigenvalue_ratio`` for the former's levels only.
- A fragmented synthetic case (``component_count`` > 1, largest fraction < 1)
  produces distinct, finite morphology values and a non-trivial delta.
- ``from_dict(to_dict(dist))`` round-trips a morphology-bearing reference; a
  ``with_morphology=False`` reference still writes/loads under "1.2".
- Idempotent regeneration on the same platform.
"""

from __future__ import annotations

import copy
import inspect
import os

import nibabel as nib
import numpy as np
import pytest

from segfacet.config import bundled_default_config
from segfacet.labels import LabelConvention
from segfacet.pipeline import extract_feature_record
from segfacet.reference import (
    ALL_STRATUM,
    ARTIFACT_SCHEMA_VERSION,
    DEFAULT_PERCENTILES,
    SCHEMA_VERSION,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceArtifactError,
    ReferenceDistribution,
    aggregate_reference,
    bundled_default_reference,
    build_and_write_default,
    build_default_cohort,
    build_reference,
    compute_intensity_reference_delta,
    compute_reference_delta,
    default_artifact_path,
    from_dict,
    load_artifact,
    to_dict,
    write_artifact,
)
from segfacet.reference.delta import compute_morphology_reference_delta
from segfacet.reference.ingest import (
    DEFAULT_SEG_SUFFIX,
    INGESTED_FEATURES,
    INGESTED_INTENSITY_FEATURES,
    INGESTED_MORPHOLOGY_FEATURES,
    ingest_cohort,
    ingest_subject,
)
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.golden import reports_close

PROV = Provenance(
    source="test-cohort-081", config_hash="cfg-hash-081", build_date="2000-01-01"
)

EXPECTED_MORPHOLOGY_FEATURES = (
    "largest_component_fraction",
    "component_count",
    "eigenvalue_ratio",
)


# =========================================================================== #
# Fixture helpers
# =========================================================================== #


def _extract(seg_img, config=None):
    """Authoritative ``extract_feature_record`` output for a seg image."""
    if config is None:
        config = bundled_default_config()
    return extract_feature_record(seg_img, config)


def _geom_intensity_stats(dist, level_name, stratum="all"):
    """The ``INGESTED_FEATURES ∪ INGESTED_INTENSITY_FEATURES`` subset of a
    level's ``feature_stats`` -- for the AC12 additivity check."""
    tracked = set(INGESTED_FEATURES) | set(INGESTED_INTENSITY_FEATURES)
    level_dist = dist.levels[level_name][stratum]
    return {
        name: stats
        for name, stats in level_dist.feature_stats.items()
        if name in tracked
    }


def _assert_stats_close(actual, expected, *, level_name, feature_name):
    """Assert two ``FeatureStats`` are equal up to float tolerance.

    Used for the AC12 additivity check, which compares the *committed* bundled
    artifact against a *regenerated* build: their geometric/intensity floats can
    differ in the last ULPs across NumPy/BLAS versions (e.g. ``std`` at the 15th
    digit on NumPy 2.5), so an exact ``==`` is too brittle -- this mirrors the
    module's ``reports_close`` policy for regenerated-vs-committed comparisons.
    ``count`` is an integer and must still match exactly.
    """
    ctx = f"{level_name}/{feature_name}"
    assert actual.count == expected.count, ctx
    assert actual.mean == pytest.approx(expected.mean), ctx
    assert actual.std == pytest.approx(expected.std), ctx
    assert actual.min == pytest.approx(expected.min), ctx
    assert actual.max == pytest.approx(expected.max), ctx
    assert set(actual.percentiles) == set(expected.percentiles), ctx
    for key in actual.percentiles:
        assert actual.percentiles[key] == pytest.approx(expected.percentiles[key]), f"{ctx} p{key}"


def _fragment_first_level(spine, convention):
    """Return a new seg image where the first recognised level gains a
    disconnected single-voxel island at the FOV corner (background, given
    ``build_clean_spine``'s margin from every face), producing a genuinely
    fragmented label (``component_count == 2``,
    ``largest_component_fraction < 1.0``)."""
    seg_data = np.asanyarray(spine.seg_img.dataobj).copy()
    label_values = sorted(v for v in np.unique(seg_data) if v != 0)
    target_label = label_values[0]
    assert seg_data[0, 0, 0] == 0, "corner voxel expected to be background"
    seg_data[0, 0, 0] = target_label
    fragmented_img = nib.Nifti1Image(seg_data, spine.seg_img.affine)
    target_level_name = convention.name_of(int(target_label))
    return fragmented_img, target_level_name


def _write_subject(dest_dir, subject_id, seg_img):
    seg_path = dest_dir / f"{subject_id}{DEFAULT_SEG_SUFFIX}"
    nib.save(seg_img, str(seg_path))
    return seg_path


def _build_morphology_reference(levels, *, stratum=ALL_STRATUM, features=None):
    """``levels`` is a mapping ``level_name -> {feature_name: FeatureStats}``
    (mirrors item 064's hand-built reference fixture helper)."""
    level_map = {}
    all_names = set()
    for level_name, feature_stats in levels.items():
        level_map[level_name] = {
            stratum: LevelDistribution(
                level_name=level_name, stratum=stratum, record_count=10,
                feature_stats=dict(feature_stats),
            )
        }
        all_names.update(feature_stats.keys())
    if features is None:
        features = tuple(sorted(all_names))
    return ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=PROV,
        features=features,
        percentiles=DEFAULT_PERCENTILES,
        subject_count=10,
        strata=(stratum,),
        levels=level_map,
    )


def _morphology_features_block(entries):
    """``entries`` is a list of ``(label, level_name, components_dict,
    eigenvalue_ratio_or_None)``. Builds a minimal ``features_block`` carrying
    only what ``compute_morphology_reference_delta`` reads."""
    per_label = {}
    orientations = []
    for label, level_name, components, eigenvalue_ratio in entries:
        per_label[str(label)] = {
            "label": label,
            "level_name": level_name,
            "geometry": {},
            "components": dict(components),
        }
        if eigenvalue_ratio is not None:
            orientations.append(
                {"label": label, "level_name": level_name, "eigenvalue_ratio": eigenvalue_ratio}
            )
    block = {"per_label": per_label}
    if orientations:
        block["stage3"] = {"per_label_orientations": orientations}
    return block


# =========================================================================== #
# Group A: family vocabulary & the 3-family split (AC1-AC3)
# =========================================================================== #


def test_ac1_morphology_vocabulary_constant_and_exported():
    assert INGESTED_MORPHOLOGY_FEATURES == EXPECTED_MORPHOLOGY_FEATURES
    from segfacet.reference import ingest as ingest_module

    assert "INGESTED_MORPHOLOGY_FEATURES" in ingest_module.__all__


def test_ac2_three_family_split_preserved_and_pairwise_disjoint():
    assert INGESTED_FEATURES == (
        "physical_volume_mm3",
        "extent_x_mm",
        "extent_y_mm",
        "extent_z_mm",
        "spline_offset_mm",
    )
    assert len(INGESTED_INTENSITY_FEATURES) == 13
    assert all(name.startswith("intensity_") for name in INGESTED_INTENSITY_FEATURES)

    geometry_set = set(INGESTED_FEATURES)
    intensity_set = set(INGESTED_INTENSITY_FEATURES)
    morphology_set = set(INGESTED_MORPHOLOGY_FEATURES)

    assert geometry_set.isdisjoint(intensity_set)
    assert geometry_set.isdisjoint(morphology_set)
    assert intensity_set.isdisjoint(morphology_set)
    assert not (morphology_set & geometry_set)


def test_ac3_fragmentation_index_not_tracked_in_any_family_or_bundled_stats():
    for family in (INGESTED_FEATURES, INGESTED_INTENSITY_FEATURES, INGESTED_MORPHOLOGY_FEATURES):
        assert "fragmentation_index" not in family

    dist = bundled_default_reference()
    for level_name, strata in dist.levels.items():
        for stratum, level_dist in strata.items():
            assert "fragmentation_index" not in level_dist.feature_stats


# =========================================================================== #
# Group B: ingestion read path (AC4-AC7)
# =========================================================================== #


def test_ac4_default_ingestion_has_no_morphology_keys(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"))
    _write_subject(tmp_path, "sub-000", spine.seg_img)

    result_subject = ingest_subject(
        tmp_path / f"sub-000{DEFAULT_SEG_SUFFIX}", config=bundled_default_config()
    )  # with_morphology defaults False
    for record in result_subject.records:
        assert not any(k in EXPECTED_MORPHOLOGY_FEATURES for k in record.features)

    result_cohort = ingest_cohort(tmp_path)  # with_morphology defaults False
    for record in result_cohort.records:
        assert not any(k in EXPECTED_MORPHOLOGY_FEATURES for k in record.features)


def test_ac5_with_morphology_true_matches_extractor_per_label(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    convention = LabelConvention.default()
    seg_path = _write_subject(tmp_path, "sub-000", spine.seg_img)

    result = ingest_subject(
        seg_path, config=bundled_default_config(), with_morphology=True
    )

    block = _extract(spine.seg_img)
    orientations_by_label = {
        int(e["label"]): e["eigenvalue_ratio"]
        for e in block.get("stage3", {}).get("per_label_orientations", [])
    }

    for record in result.records:
        label_value = convention.value_of(record.level_name)
        entry = block["per_label"][str(label_value)]
        assert record.features["largest_component_fraction"] == pytest.approx(
            entry["components"]["largest_component_fraction"]
        )
        assert record.features["component_count"] == pytest.approx(
            float(entry["components"]["component_count"])
        )
        assert label_value in orientations_by_label
        assert record.features["eigenvalue_ratio"] == pytest.approx(
            orientations_by_label[label_value]
        )


def test_ac6_single_label_subject_omits_eigenvalue_ratio_no_none_no_raise(tmp_path):
    spine = build_clean_spine(levels=("L1",))
    seg_path = _write_subject(tmp_path, "sub-000", spine.seg_img)

    result = ingest_subject(
        seg_path, config=bundled_default_config(), with_morphology=True
    )  # must not raise

    assert len(result.records) == 1
    record = result.records[0]
    assert "largest_component_fraction" in record.features
    assert "component_count" in record.features
    assert "eigenvalue_ratio" not in record.features
    for value in record.features.values():
        assert value is not None


def test_ac7_morphology_ingestion_deterministic_and_read_only(tmp_path):
    for i in range(2):
        spine = build_clean_spine(levels=("L1", "L2", "L3"))
        _write_subject(tmp_path, f"sub-{i:03d}", spine.seg_img)

    config = bundled_default_config()
    config_before = copy.deepcopy(config)
    convention = LabelConvention.default()
    convention_before = dict(convention.value_to_name)
    listing_before = sorted(os.listdir(tmp_path))

    result1 = ingest_cohort(tmp_path, config=config, convention=convention, with_morphology=True)
    result2 = ingest_cohort(tmp_path, config=config, convention=convention, with_morphology=True)

    assert [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy) for r in result1.records
    ] == [
        (r.subject_id, r.level_name, dict(r.features), r.size_proxy) for r in result2.records
    ]
    assert any(
        any(k in EXPECTED_MORPHOLOGY_FEATURES for k in r.features) for r in result1.records
    )
    assert sorted(os.listdir(tmp_path)) == listing_before
    assert config == config_before
    assert dict(convention.value_to_name) == convention_before


# =========================================================================== #
# Group C: aggregation (generic core, no edit) & schema version (AC8-AC9)
# =========================================================================== #


def test_ac8_aggregate_reference_tracks_morphology_with_no_core_change(tmp_path):
    for i in range(2):
        spine = build_clean_spine(levels=("L1", "L2"))
        _write_subject(tmp_path, f"sub-{i:03d}", spine.seg_img)

    result = ingest_cohort(tmp_path, with_morphology=True)
    dist = aggregate_reference(result.records, provenance=PROV)

    morphology_names_present = {
        name for name in dist.features if name in EXPECTED_MORPHOLOGY_FEATURES
    }
    assert morphology_names_present == set(EXPECTED_MORPHOLOGY_FEATURES)

    l1_records = [
        r for r in result.records
        if r.level_name == "L1" and "largest_component_fraction" in r.features
    ]
    assert l1_records
    values = [r.features["largest_component_fraction"] for r in l1_records]
    stats = dist.levels["L1"]["all"].feature_stats["largest_component_fraction"]
    assert stats.count == len(values)
    assert stats.mean == pytest.approx(sum(values) / len(values))
    assert stats.min == pytest.approx(min(values))
    assert stats.max == pytest.approx(max(values))

    # Guard: aggregate.py stays generic -- no morphology-specific special-
    # casing was introduced (mirrors item 063's AC8 source-text marker).
    from segfacet.reference import aggregate as aggregate_module

    source = inspect.getsource(aggregate_module)
    assert "morphology" not in source.lower()


def test_ac9_schema_version_bumped_and_enforced(tmp_path):
    assert SCHEMA_VERSION == "1.2"
    assert ARTIFACT_SCHEMA_VERSION == "1.2"

    spine = build_clean_spine(levels=("L1",))
    _write_subject(tmp_path, "sub-000", spine.seg_img)
    dist = build_reference(tmp_path, source="s", build_date="2026-07-15")
    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)

    loaded = load_artifact(out_path)  # must not raise
    assert loaded.schema_version == "1.2"

    import json

    data = json.loads(out_path.read_text(encoding="utf-8"))
    data["schema_version"] = "1.1"
    out_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReferenceArtifactError):
        load_artifact(out_path)


# =========================================================================== #
# Group D: build pipeline & regenerated bundled artifact (AC10-AC12)
# =========================================================================== #


def test_ac10_build_reference_threads_with_morphology(tmp_path):
    for i in range(2):
        spine = build_clean_spine(levels=("L1", "L2"))
        _write_subject(tmp_path, f"sub-{i:03d}", spine.seg_img)

    dist_on = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=True)
    dist_off = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=False)

    assert set(EXPECTED_MORPHOLOGY_FEATURES) <= set(dist_on.features)
    assert not (set(dist_off.features) & set(EXPECTED_MORPHOLOGY_FEATURES))


def test_ac10_build_reference_default_with_morphology_is_true(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"))
    _write_subject(tmp_path, "sub-000", spine.seg_img)

    default_dist = build_reference(tmp_path, source="s", build_date="2026-07-15")
    explicit_on = build_reference(
        tmp_path, source="s", build_date="2026-07-15", with_morphology=True
    )
    assert set(default_dist.features) == set(explicit_on.features)


def test_ac11_bundled_artifact_carries_morphology_distributions_for_lumbar_levels():
    dist = bundled_default_reference()

    assert dist.schema_version == "1.2"
    assert set(EXPECTED_MORPHOLOGY_FEATURES) <= set(dist.features)

    for level_name in ("L1", "L2", "L3", "L4", "L5"):
        assert level_name in dist.levels
        level_dist = dist.levels[level_name]["all"]
        for feature_name in EXPECTED_MORPHOLOGY_FEATURES:
            assert feature_name in level_dist.feature_stats, (
                f"level {level_name} missing morphology stat {feature_name}"
            )
            stats = level_dist.feature_stats[feature_name]
            assert math_isfinite(stats.count)
            assert math_isfinite(stats.mean)
            assert math_isfinite(stats.min)
            assert math_isfinite(stats.max)
            for pct_value in stats.percentiles.values():
                assert math_isfinite(pct_value)


def math_isfinite(value):
    import math

    return math.isfinite(value)


def test_ac12_geometric_and_intensity_stats_identical_with_and_without_morphology(tmp_path):
    for i in range(2):
        spine = build_clean_spine(levels=("L1", "L2", "L3"))
        _write_subject(tmp_path, f"sub-{i:03d}", spine.seg_img)

    dist_on = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=True)
    dist_off = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=False)

    for level_name in ("L1", "L2", "L3"):
        stats_on = _geom_intensity_stats(dist_on, level_name)
        stats_off = _geom_intensity_stats(dist_off, level_name)
        assert set(stats_on.keys()) == set(stats_off.keys())
        for feature_name, stats in stats_on.items():
            assert stats == stats_off[feature_name]


def test_ac12_bundled_default_geometric_and_intensity_stats_identical_on_off_morphology():
    import tempfile
    from pathlib import Path

    dist_on = bundled_default_reference()  # with_morphology=True (default build)
    with tempfile.TemporaryDirectory() as tmp_dir:
        cohort_dir = build_default_cohort(Path(tmp_dir))
        dist_off = build_reference(
            cohort_dir,
            source="synthetic-verse-cohort",
            build_date="2026-07-15",
            with_morphology=False,
        )

    for level_name in ("L1", "L2", "L3", "L4", "L5"):
        stats_on = _geom_intensity_stats(dist_on, level_name)
        stats_off = _geom_intensity_stats(dist_off, level_name)
        assert set(stats_on.keys()) == set(stats_off.keys())
        for feature_name, stats in stats_on.items():
            # dist_on is the *committed* bundled artifact, dist_off a fresh
            # rebuild -- compare with float tolerance (see _assert_stats_close),
            # not exact ==, so last-ULP drift across NumPy/BLAS versions doesn't
            # break the additivity check.
            _assert_stats_close(
                stats, stats_off[feature_name],
                level_name=level_name, feature_name=feature_name,
            )


# =========================================================================== #
# Group E: delta-to-reference read path (AC13-AC16)
# =========================================================================== #


def test_ac13_morphology_delta_scores_via_its_own_read_path():
    bundled = bundled_default_reference()
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    config = bundled_default_config()
    block = extract_feature_record(spine.seg_img, config)

    delta = compute_morphology_reference_delta(block, bundled)  # must not raise

    present_labels = {int(entry["label"]) for entry in block["per_label"].values()}
    assert set(delta.per_label.keys()) == present_labels

    orientations_by_label = {
        int(e["label"]) for e in block.get("stage3", {}).get("per_label_orientations", [])
    }
    for label, label_delta in delta.per_label.items():
        entry = block["per_label"][str(label)]
        expected_names = set()
        if "components" in entry:
            expected_names |= {"largest_component_fraction", "component_count"}
        if label in orientations_by_label:
            expected_names.add("eigenvalue_ratio")

        got_names = {fd.feature for fd in label_delta.features}
        assert got_names == expected_names
        for fd in label_delta.features:
            assert fd.feature in EXPECTED_MORPHOLOGY_FEATURES


def test_ac14_out_of_range_bounds_switchable_on_morphology_delta():
    stats = FeatureStats(
        count=10, mean=0.7, std=0.15, min=0.2, max=1.0,
        percentiles={
            "p1": 0.30, "p5": 0.45, "p25": 0.60, "p50": 0.70,
            "p75": 0.80, "p95": 0.92, "p99": 0.97,
        },
    )
    reference = _build_morphology_reference({"L1": {"largest_component_fraction": stats}})
    # A value between p1 (0.30) and p5 (0.45) -- inside the default (1, 99)
    # band, but outside the tighter (5, 95) band.
    value = 0.35
    block = _morphology_features_block(
        [(20, "L1", {"largest_component_fraction": value, "component_count": 1}, None)]
    )

    delta_default = compute_morphology_reference_delta(block, reference)
    fd_default = delta_default.per_label[20].features[0]
    assert fd_default.out_of_range is False

    delta_tight = compute_morphology_reference_delta(block, reference, lower_pct=5, upper_pct=95)
    fd_tight = None
    for fd in delta_tight.per_label[20].features:
        if fd.feature == "largest_component_fraction":
            fd_tight = fd
    assert fd_tight is not None
    assert fd_tight.out_of_range is True


def test_ac15_geometry_delta_stays_inert_on_morphology():
    bundled = bundled_default_reference()
    assert set(EXPECTED_MORPHOLOGY_FEATURES) <= set(bundled.features)

    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    config = bundled_default_config()
    block = extract_feature_record(spine.seg_img, config)

    delta = compute_reference_delta(block, bundled)

    for label, label_delta in delta.per_label.items():
        for fd in label_delta.features:
            assert fd.feature not in EXPECTED_MORPHOLOGY_FEATURES
        for name in label_delta.out_of_range_features:
            assert name not in EXPECTED_MORPHOLOGY_FEATURES


def test_ac16_intensity_delta_stays_inert_on_morphology():
    from segfacet.feature_report import build_image_features_block
    from segfacet.features.intensity import compute_intensity_features
    from segfacet.synth.intensity import paint_clean_scan

    bundled = bundled_default_reference()
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    config = bundled_default_config()

    block = extract_feature_record(spine.seg_img, config)
    intensity_by_label = compute_intensity_features(scan_img, spine.seg_img)
    image_features = build_image_features_block(intensity_by_label)

    delta = compute_intensity_reference_delta(block, image_features, bundled)

    for label, label_delta in delta.per_label.items():
        for fd in label_delta.features:
            assert fd.feature not in EXPECTED_MORPHOLOGY_FEATURES
        for name in label_delta.out_of_range_features:
            assert name not in EXPECTED_MORPHOLOGY_FEATURES


# =========================================================================== #
# Group F: reproducibility, tolerance switch, scope guards (AC17, AC20)
# =========================================================================== #


def test_ac17_regenerated_artifact_deterministic_and_matches_committed_within_tolerance(tmp_path):
    import json

    dest1 = tmp_path / "regen1.json"
    dest2 = tmp_path / "regen2.json"
    build_and_write_default(dest1)
    build_and_write_default(dest2)

    # Intra-platform determinism stays byte-exact.
    assert dest1.read_bytes() == dest2.read_bytes()

    regenerated = json.loads(dest1.read_text(encoding="utf-8"))
    committed = json.loads(default_artifact_path().read_text(encoding="utf-8"))
    assert reports_close(regenerated, committed)


def test_ac20_scope_guard_no_features_engine_edit_and_gitattributes_pin():
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    features_dir = repo_root / "src" / "segfacet" / "features"
    for py_file in features_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        assert "INGESTED_MORPHOLOGY_FEATURES" not in text
        assert "compute_morphology_reference_delta" not in text

    from segfacet.reference import aggregate as aggregate_module

    source = inspect.getsource(aggregate_module)
    assert "morphology" not in source.lower()

    gitattributes_text = (repo_root / ".gitattributes").read_text(encoding="utf-8")
    matching_lines = [
        line
        for line in gitattributes_text.splitlines()
        if "src/segfacet/reference/reference_default.json" in line
    ]
    assert any("text eol=lf" in line for line in matching_lines)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_mixed_multi_level_and_single_level_cohort_under_morphology(tmp_path):
    multi = build_clean_spine(levels=("L1", "L2"))
    single = build_clean_spine(levels=("L1",))
    _write_subject(tmp_path, "sub-multi", multi.seg_img)
    _write_subject(tmp_path, "sub-single", single.seg_img)

    result = ingest_cohort(tmp_path, with_morphology=True)  # must not raise

    by_subject = {s.subject_id: s for s in result.subjects}
    assert all("eigenvalue_ratio" in r.features for r in by_subject["sub-multi"].records)
    assert all("eigenvalue_ratio" not in r.features for r in by_subject["sub-single"].records)
    # Both still carry the label-only morphology features.
    for subject in ("sub-multi", "sub-single"):
        for record in by_subject[subject].records:
            assert "largest_component_fraction" in record.features
            assert "component_count" in record.features


def test_adv_fragmented_case_yields_distinct_finite_values_and_nontrivial_delta(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2", "L3"))
    convention = LabelConvention.default()
    fragmented_img, fragmented_level = _fragment_first_level(spine, convention)
    seg_path = _write_subject(tmp_path, "sub-000", fragmented_img)

    result = ingest_subject(seg_path, config=bundled_default_config(), with_morphology=True)
    by_level = {r.level_name: r for r in result.records}

    fragmented_record = by_level[fragmented_level]
    assert fragmented_record.features["component_count"] == pytest.approx(2.0)
    assert fragmented_record.features["largest_component_fraction"] < 1.0
    assert math_isfinite(fragmented_record.features["largest_component_fraction"])

    # A non-fragmented sibling level stays a single, whole component.
    other_level = next(name for name in by_level if name != fragmented_level)
    assert by_level[other_level].features["component_count"] == pytest.approx(1.0)
    assert by_level[other_level].features["largest_component_fraction"] == pytest.approx(1.0)

    # A non-trivial delta against the bundled reference for the fragmented
    # level (the fraction is markedly below the clean-cohort's degenerate 1.0
    # baseline).
    bundled = bundled_default_reference()
    block = extract_feature_record(fragmented_img, bundled_default_config())
    delta = compute_morphology_reference_delta(block, bundled)
    frag_label = convention.value_of(fragmented_level)
    fd_fraction = next(
        fd for fd in delta.per_label[frag_label].features
        if fd.feature == "largest_component_fraction"
    )
    assert fd_fraction.out_of_range is True


def test_adv_morphology_bearing_reference_round_trips(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"))
    _write_subject(tmp_path, "sub-000", spine.seg_img)
    dist = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=True)
    assert set(EXPECTED_MORPHOLOGY_FEATURES) <= set(dist.features)

    assert from_dict(to_dict(dist)) == dist

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)
    assert loaded == dist


def test_adv_morphology_free_reference_round_trips_under_new_schema(tmp_path):
    spine = build_clean_spine(levels=("L1", "L2"))
    _write_subject(tmp_path, "sub-000", spine.seg_img)
    dist = build_reference(tmp_path, source="s", build_date="2026-07-15", with_morphology=False)
    assert dist.schema_version == "1.2"
    assert not (set(dist.features) & set(EXPECTED_MORPHOLOGY_FEATURES))

    assert from_dict(to_dict(dist)) == dist

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)  # must not raise under "1.2"
    assert loaded == dist


def test_adv_regeneration_is_idempotent(tmp_path):
    dest1 = tmp_path / "run1.json"
    dest2 = tmp_path / "run2.json"
    build_and_write_default(dest1)
    build_and_write_default(dest2)
    assert dest1.read_bytes() == dest2.read_bytes()
