"""Tests for item 124 -- observed-range column in the generated feature
catalogue (``segfacet.observed_range`` + its join into ``segfacet.catalogue``).

Covers Acceptance Criteria AC1-AC23:

- AC1:  every catalogue entry with >=1 numeric driver value carries an
        ``observed.corpus`` object with ``covered: True`` and non-null
        ``count``/``minimum``/``maximum``/``span``/``magnitude``.
- AC2:  each of the 21 ``reference_verse_v1.json`` feature names resolves to
        exactly one catalogue leaf path.
- AC3:  each AC2-resolved path carries a populated ``observed.reference``.
- AC4:  an unresolved path's ``observed.reference`` is ``covered: False``
        with every numeric field ``None`` (never ``0``, never omitted).
- AC5:  an injected pre-123-magnitude reference flags exactly
        ``stage3.per_label_offsets[].offset_mm`` as ``"degenerate"``.
- AC6:  a legitimately-constant synthetic path (``dy_mm``) reads
        ``"constant-synthetic"``, never ``"degenerate"``.
- AC7:  a placeholder-only path reads ``"placeholder"``.
- AC8:  every id in the placeholder-tier constant is a live driver id.
- AC9:  the verdict vocabulary is closed to the six named values.
- AC10: the shipped catalogue has zero ``"degenerate"`` entries.
- AC11: ``offset_mm`` reads ``"varies"`` with reference magnitude > 1.0.
- AC12: the JSON's top-level ``observed_summary`` sums to the entry count.
- AC13/AC14: the Markdown table gains ``observed range`` / ``observed
        verdict`` columns, the latter closed to the AC9 vocabulary.
- AC15: every emitted float under ``observed`` round-trips through
        ``float(f"{v:.6g}")``.
- AC16: two same-session regenerations are byte-identical.
- AC17: the committed artifacts match a fresh regeneration.
- AC18: the regenerated leaf-path set is unchanged (138 paths).
- AC19: ``schema_version`` is bumped to ``"1.1"`` (reconciled to ``"1.2"`` by
        item 148, 2026-09-04, which added the ``mode_roles`` shape).
- AC20: ``aide_status_report.py``'s loader accepts the bumped schema.
- AC21: a missing/unparseable/mis-versioned reference degrades, never raises.
- AC22: ``--reference PATH`` is accepted and steers the reference population.
- AC23: an ambiguous reference-name match resolves to no leaf path.

Adversarial / edge-case scenarios included: verdict-rule ordering
(reference-degenerate + corpus-informative must stay "degenerate";
placeholder + large hand-typed constant must stay "placeholder"); the
``1e-3`` floor boundary (exactly-at vs. just-above); an all-negative
population's sign handling; booleans excluded from numeric aggregation; the
six empty-container paths classified without crashing; scalar-list
element-wise collection; determinism/immutability of
``build_observed_ranges``; quantisation idempotence; empty-input degeneracy.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import segfacet.synth  # noqa: F401 -- triggers self-registration of every operator

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMMITTED_JSON = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
_COMMITTED_MD = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
_ASR_MODULE_PATH = _REPO_ROOT / "scripts" / "aide_status_report.py"

# Pre-123 spline_offset_mm magnitudes (Description, "What the verdict is
# calibrated against"). Constructed in-test rather than read from git history.
_PRE123_MIN = 5.928524174262729e-10
_PRE123_MAX = 0.0003081687597848005

_VERDICTS = {
    "varies",
    "degenerate",
    "constant-synthetic",
    "placeholder",
    "non-numeric",
    "unobserved",
}


def _observed_range():
    import segfacet.observed_range as observed_range

    return observed_range


def _catalogue():
    import segfacet.catalogue as catalogue

    return catalogue


@pytest.fixture(scope="module")
def observed_range_module():
    return _observed_range()


@pytest.fixture(scope="module")
def catalogue_module():
    return _catalogue()


@pytest.fixture(scope="module")
def full_catalogue(catalogue_module):
    return catalogue_module.build_catalogue()


@pytest.fixture(scope="module")
def catalogue_dict(catalogue_module, full_catalogue):
    return catalogue_module.catalogue_to_dict(full_catalogue)


@pytest.fixture(scope="module")
def committed_json_dict():
    return json.loads(_COMMITTED_JSON.read_bytes().decode("utf-8"))


def _entry(cat, path):
    for entry in cat.entries:
        if entry.path == path:
            return entry
    raise AssertionError(f"no catalogue entry for path {path!r}")


def _json_entry(json_dict, path):
    for group in json_dict["groups"]:
        for entry in group["entries"]:
            if entry["path"] == path:
                return entry
    raise AssertionError(f"no JSON entry for path {path!r}")


def _bundled_reference():
    from segfacet.reference.artifact import bundled_production_reference

    return bundled_production_reference()


def _make_reference_distribution(feature_stats_overrides):
    """Build a minimal, in-memory ``ReferenceDistribution`` starting from the
    shipped bundled production reference, but with the given per-feature
    ``(min, max)`` overrides applied to every (level, stratum) that carries
    that feature. Everything else (levels, other features' stats, counts,
    percentiles) is left at shipped-like magnitudes so only the targeted
    feature's magnitude changes.
    """
    from segfacet.reference.schema import FeatureStats, LevelDistribution

    base = _bundled_reference()
    new_levels = {}
    for level_name, strata in base.levels.items():
        new_strata = {}
        for stratum, level_dist in strata.items():
            new_feature_stats = {}
            for feature_name, stats in level_dist.feature_stats.items():
                if feature_name in feature_stats_overrides:
                    lo, hi = feature_stats_overrides[feature_name]
                    new_feature_stats[feature_name] = FeatureStats(
                        count=stats.count,
                        mean=stats.mean,
                        std=stats.std,
                        min=lo,
                        max=hi,
                        percentiles=stats.percentiles,
                    )
                else:
                    new_feature_stats[feature_name] = stats
            new_strata[stratum] = LevelDistribution(
                level_name=level_dist.level_name,
                stratum=level_dist.stratum,
                record_count=level_dist.record_count,
                feature_stats=new_feature_stats,
            )
        new_levels[level_name] = new_strata

    import dataclasses

    return dataclasses.replace(base, levels=new_levels)


def _make_reference_with_features(feature_ranges):
    """Build a minimal, standalone ``ReferenceDistribution`` carrying exactly
    the given ``{feature_name: (min, max)}`` entries under one level/stratum
    -- for testing resolution rules against feature names that do not exist
    in the shipped reference (e.g. AC23's deliberately ambiguous ``"mean"``).
    """
    from segfacet.reference.schema import (
        FeatureStats,
        LevelDistribution,
        Provenance,
        ReferenceDistribution,
        SCHEMA_VERSION,
    )

    feature_stats = {
        name: FeatureStats(count=10, mean=(lo + hi) / 2, std=0.0, min=lo, max=hi, percentiles={})
        for name, (lo, hi) in feature_ranges.items()
    }
    level_dist = LevelDistribution(
        level_name="L1", stratum="all", record_count=10, feature_stats=feature_stats
    )
    return ReferenceDistribution(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(source="test", config_hash="test", build_date="2026-08-30"),
        features=tuple(feature_ranges),
        percentiles=(1, 5, 25, 50, 75, 95, 99),
        subject_count=1,
        strata=("all",),
        levels={"L1": {"all": level_dist}},
    )


# =========================================================================== #
# AC1: every numeric path carries a corpus range
# =========================================================================== #


def test_ac1_every_numeric_entry_has_covered_corpus_range(
    catalogue_module, full_catalogue, observed_range_module
):
    driver_records = dict(catalogue_module.iter_driver_records())
    leaf_values = {}
    for record in driver_records.values():
        for path, values in observed_range_module.iter_leaf_values(record).items():
            leaf_values.setdefault(path, []).extend(values)

    for entry in full_catalogue.entries:
        values = leaf_values.get(entry.path, [])
        numeric_values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not numeric_values:
            continue
        corpus = entry.observed.corpus
        assert corpus.covered is True, entry.path
        assert corpus.count is not None, entry.path
        assert corpus.minimum is not None, entry.path
        assert corpus.maximum is not None, entry.path
        assert corpus.span is not None, entry.path
        assert corpus.magnitude is not None, entry.path


# =========================================================================== #
# AC2: every reference feature resolves to exactly one leaf path
# =========================================================================== #


def test_ac2_every_reference_feature_resolves_uniquely(observed_range_module, full_catalogue):
    reference = _bundled_reference()
    leaf_paths = {e.path for e in full_catalogue.entries}
    resolved = observed_range_module.resolve_reference_features(leaf_paths)

    for feature_name in reference.features:
        assert feature_name in resolved, feature_name
        target = resolved[feature_name]
        assert target in leaf_paths, (feature_name, target)

    # No name left unresolved, and each resolves to exactly one path (a dict
    # value per key is inherently singular; assert the key set matches).
    assert set(resolved.keys()) >= set(reference.features)


# =========================================================================== #
# AC3: reference-covered paths carry a reference range
# =========================================================================== #


def test_ac3_reference_covered_paths_have_populated_reference_range(
    observed_range_module, full_catalogue
):
    # Restricted to the reference's actual 21 feature names, mirroring
    # test_ac2's pattern -- resolve_reference_features(leaf_paths) also
    # resolves names the reference does not carry (e.g. rule 3's unique
    # last-segment match on a name like item 121's
    # "spline_tangent_sagittal_deg", which legitimately has no backing stats
    # and so is `covered: False`; that is AC4's concern, not AC3's).
    reference = _bundled_reference()
    leaf_paths = {e.path for e in full_catalogue.entries}
    resolved = observed_range_module.resolve_reference_features(leaf_paths)

    for feature_name in reference.features:
        assert feature_name in resolved, feature_name
        path = resolved[feature_name]
        entry = _entry(full_catalogue, path)
        ref = entry.observed.reference
        assert ref.covered is True, (feature_name, path)
        assert ref.count is not None, path
        assert ref.minimum is not None, path
        assert ref.maximum is not None, path
        assert ref.span is not None, path
        assert ref.magnitude is not None, path


def test_ac3_reference_range_aggregates_across_levels_and_strata(
    observed_range_module, catalogue_module
):
    reference = _bundled_reference()
    # spline_offset_mm is documented (item 123) to carry 23 levels.
    per_level_mins = []
    per_level_maxs = []
    per_level_counts = 0
    for strata in reference.levels.values():
        for level_dist in strata.values():
            stats = level_dist.feature_stats.get("spline_offset_mm")
            if stats is not None:
                per_level_mins.append(stats.min)
                per_level_maxs.append(stats.max)
                per_level_counts += stats.count

    driver_records = list(catalogue_module.iter_driver_records())
    ranges = observed_range_module.build_observed_ranges(
        driver_records=driver_records, reference=reference
    )
    observed = ranges.get("stage3.per_label_offsets[].offset_mm")
    assert observed is not None
    assert observed.reference.minimum == pytest.approx(min(per_level_mins), rel=1e-5)
    assert observed.reference.maximum == pytest.approx(max(per_level_maxs), rel=1e-5)
    assert observed.reference.count == per_level_counts


# =========================================================================== #
# AC4: an uncovered path is marked uncovered, not zero
# =========================================================================== #


def test_ac4_uncovered_reference_path_is_null_not_zero(full_catalogue):
    # dy_mm is not among the 21 reference features (Description).
    entry = _entry(full_catalogue, "stage3.per_label_offsets[].dy_mm")
    ref = entry.observed.reference
    assert ref.covered is False
    assert ref.minimum is None
    assert ref.maximum is None
    assert ref.span is None
    assert ref.magnitude is None


# =========================================================================== #
# AC5: a dead reference feature is flagged degenerate
# =========================================================================== #


def test_ac5_pre123_magnitude_reference_flags_offset_mm_degenerate(observed_range_module):
    dead_reference = _make_reference_distribution(
        {"spline_offset_mm": (_PRE123_MIN, _PRE123_MAX)}
    )
    ranges = observed_range_module.build_observed_ranges(reference=dead_reference)
    entry_range = ranges["stage3.per_label_offsets[].offset_mm"]
    assert entry_range.verdict == "degenerate"


def test_ac5_only_the_targeted_path_is_flagged_degenerate(observed_range_module):
    dead_reference = _make_reference_distribution(
        {"spline_offset_mm": (_PRE123_MIN, _PRE123_MAX)}
    )
    ranges = observed_range_module.build_observed_ranges(reference=dead_reference)
    degenerate_paths = [p for p, r in ranges.items() if r.verdict == "degenerate"]
    assert degenerate_paths == ["stage3.per_label_offsets[].offset_mm"]


# =========================================================================== #
# AC6: a legitimately-constant synthetic path is not flagged
# =========================================================================== #


def test_ac6_constant_synthetic_dy_mm_not_degenerate(full_catalogue):
    entry = _entry(full_catalogue, "stage3.per_label_offsets[].dy_mm")
    assert entry.observed.verdict == "constant-synthetic"
    assert entry.observed.verdict != "degenerate"


# =========================================================================== #
# AC7: a placeholder-only path is marked as such
# =========================================================================== #


def test_ac7_placeholder_only_path_marked_placeholder(full_catalogue):
    entry = _entry(
        full_catalogue,
        "reference_delta.{label}.features.physical_volume_mm3.z_score",
    )
    assert entry.observed.verdict == "placeholder"


# =========================================================================== #
# AC8: the placeholder driver ids are live
# =========================================================================== #


def test_ac8_placeholder_driver_ids_are_live(catalogue_module, observed_range_module):
    live_driver_ids = {driver_id for driver_id, _record in catalogue_module.iter_driver_records()}
    for driver_id in observed_range_module._PLACEHOLDER_DRIVER_IDS:
        assert driver_id in live_driver_ids, driver_id


# =========================================================================== #
# AC9: the verdict vocabulary is closed
# =========================================================================== #


def test_ac9_verdict_vocabulary_closed(full_catalogue):
    for entry in full_catalogue.entries:
        assert entry.observed.verdict in _VERDICTS, (entry.path, entry.observed.verdict)


# =========================================================================== #
# AC10: the shipped catalogue reports no degenerate feature
# =========================================================================== #


def test_ac10_shipped_catalogue_has_zero_degenerate(committed_json_dict):
    degenerate_paths = [
        e["path"]
        for g in committed_json_dict["groups"]
        for e in g["entries"]
        if e["observed"]["verdict"] == "degenerate"
    ]
    assert degenerate_paths == []


# =========================================================================== #
# AC11: offset_mm reads as varying
# =========================================================================== #


def test_ac11_offset_mm_varies_with_magnitude_above_one(committed_json_dict):
    entry = _json_entry(committed_json_dict, "stage3.per_label_offsets[].offset_mm")
    assert entry["observed"]["verdict"] == "varies"
    assert entry["observed"]["reference"]["magnitude"] > 1.0


# =========================================================================== #
# AC12: the JSON carries a summary block
# =========================================================================== #


def test_ac12_observed_summary_present_and_sums_to_entry_count(catalogue_dict, full_catalogue):
    summary = catalogue_dict["observed_summary"]
    assert set(summary.keys()) == _VERDICTS
    assert sum(summary.values()) == len(full_catalogue.entries)


def test_ac12_committed_summary_matches_committed_entry_count(committed_json_dict):
    summary = committed_json_dict["observed_summary"]
    total_entries = sum(len(g["entries"]) for g in committed_json_dict["groups"])
    assert sum(summary.values()) == total_entries


# =========================================================================== #
# AC13/AC14: the Markdown table gains the two columns
# =========================================================================== #


def test_ac13_markdown_header_has_observed_range_column(catalogue_module, full_catalogue):
    md = catalogue_module.render_markdown(full_catalogue)
    header = [l for l in md.splitlines() if l.strip().startswith("|")][0]
    assert "observed range" in header


def test_ac14_markdown_header_has_observed_verdict_column(catalogue_module, full_catalogue):
    md = catalogue_module.render_markdown(full_catalogue)
    header = [l for l in md.splitlines() if l.strip().startswith("|")][0]
    assert "observed verdict" in header


def test_ac14_every_row_verdict_cell_is_in_vocabulary(catalogue_module, full_catalogue):
    md = catalogue_module.render_markdown(full_catalogue)
    table_rows = [l for l in md.splitlines() if l.strip().startswith("|")]
    header_cells = [c.strip() for c in table_rows[0].strip("|").split("|")]
    verdict_col = header_cells.index("observed verdict")
    body_rows = table_rows[2:]
    assert body_rows, "expected at least one data row"
    for row in body_rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert cells[verdict_col] in _VERDICTS, row


# =========================================================================== #
# AC15: emitted floats are quantised
# =========================================================================== #


def _walk_observed_floats(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("minimum", "maximum", "span", "magnitude") and isinstance(value, float):
                yield value
            else:
                yield from _walk_observed_floats(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_observed_floats(value)


def test_ac15_every_observed_float_is_six_sig_fig_quantised(catalogue_dict):
    found_any = False
    for group in catalogue_dict["groups"]:
        for entry in group["entries"]:
            for value in _walk_observed_floats(entry["observed"]):
                found_any = True
                assert value == float(f"{value:.6g}"), value
    assert found_any, "expected at least one quantised float under observed"


# =========================================================================== #
# AC16: regeneration is byte-identical run-to-run
# =========================================================================== #


def test_ac16_regenerate_twice_in_one_session_byte_identical(catalogue_module, tmp_path):
    dest1_json = tmp_path / "run1.json"
    dest1_md = tmp_path / "run1.md"
    dest2_json = tmp_path / "run2.json"
    dest2_md = tmp_path / "run2.md"

    catalogue_module.main(["--json", str(dest1_json), "--md", str(dest1_md)])
    catalogue_module.main(["--json", str(dest2_json), "--md", str(dest2_md)])

    assert dest1_json.read_bytes() == dest2_json.read_bytes()
    assert dest1_md.read_bytes() == dest2_md.read_bytes()


# =========================================================================== #
# AC17: the committed artifacts match a fresh regeneration
# =========================================================================== #


def test_ac17_committed_docs_match_fresh_regeneration(catalogue_module, tmp_path):
    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue_module.main(["--json", str(json_dest), "--md", str(md_dest)])

    assert json_dest.read_bytes() == _COMMITTED_JSON.read_bytes()
    assert md_dest.read_bytes() == _COMMITTED_MD.read_bytes()


# =========================================================================== #
# AC18: the entry set is unchanged
# =========================================================================== #


def test_ac18_entry_set_has_138_paths(full_catalogue):
    paths = {e.path for e in full_catalogue.entries}
    assert len(paths) == 138


def test_ac18_committed_entry_set_matches_regenerated(full_catalogue, committed_json_dict):
    regenerated_paths = {e.path for e in full_catalogue.entries}
    committed_paths = {
        e["path"] for g in committed_json_dict["groups"] for e in g["entries"]
    }
    assert regenerated_paths == committed_paths


# =========================================================================== #
# AC19: the schema version is bumped
# =========================================================================== #


def test_ac19_schema_version_is_1_2(catalogue_dict):
    assert catalogue_dict["schema_version"] == "1.2"


def test_ac19_committed_schema_version_is_1_2(committed_json_dict):
    assert committed_json_dict["schema_version"] == "1.2"


# =========================================================================== #
# AC20: the status report accepts the new schema
# =========================================================================== #


@pytest.fixture(scope="module")
def asr():
    spec = importlib.util.spec_from_file_location("aide_status_report_124", _ASR_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_ac20_load_feature_catalog_returns_nonempty_tuple(asr):
    groups = asr.load_feature_catalog(_COMMITTED_JSON)
    assert isinstance(groups, tuple)
    assert groups


# =========================================================================== #
# AC21: a missing reference degrades, never raises
# =========================================================================== #


def test_ac21_nonexistent_reference_path_degrades(observed_range_module, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    ranges = observed_range_module.build_observed_ranges(reference=missing)
    assert ranges
    for r in ranges.values():
        assert r.reference.covered is False


def test_ac21_directory_as_reference_path_degrades(observed_range_module, tmp_path):
    a_directory = tmp_path / "a_directory"
    a_directory.mkdir()
    ranges = observed_range_module.build_observed_ranges(reference=a_directory)
    assert ranges
    for r in ranges.values():
        assert r.reference.covered is False


def test_ac21_malformed_json_reference_degrades(observed_range_module, tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{this is not valid json", encoding="utf-8")
    ranges = observed_range_module.build_observed_ranges(reference=malformed)
    assert ranges
    for r in ranges.values():
        assert r.reference.covered is False


def test_ac21_unrecognised_schema_version_reference_degrades(observed_range_module, tmp_path):
    unknown = tmp_path / "unknown_version.json"
    unknown.write_text(
        json.dumps({"schema_version": "not-a-real-version-999", "levels": {}, "features": []}),
        encoding="utf-8",
    )
    ranges = observed_range_module.build_observed_ranges(reference=unknown)
    assert ranges
    for r in ranges.values():
        assert r.reference.covered is False


def test_ac21_degraded_reference_build_catalogue_does_not_raise(catalogue_module, tmp_path):
    missing = tmp_path / "does_not_exist.json"
    cat = catalogue_module.build_catalogue(reference=missing)
    assert isinstance(cat, catalogue_module.FeatureCatalogue)
    for entry in cat.entries:
        assert entry.observed.reference.covered is False


# =========================================================================== #
# AC22: the reference source is injectable
# =========================================================================== #


def test_ac22_main_accepts_reference_flag(catalogue_module, tmp_path):
    from segfacet.reference.artifact import write_artifact

    alt_reference = _make_reference_distribution(
        {"spline_offset_mm": (_PRE123_MIN, _PRE123_MAX)}
    )
    alt_path = tmp_path / "alt_reference.json"
    write_artifact(alt_reference, alt_path)

    json_dest = tmp_path / "catalogue.json"
    md_dest = tmp_path / "catalogue.md"
    catalogue_module.main(
        ["--json", str(json_dest), "--md", str(md_dest), "--reference", str(alt_path)]
    )
    data = json.loads(json_dest.read_bytes().decode("utf-8"))
    entry = _json_entry(data, "stage3.per_label_offsets[].offset_mm")
    assert entry["observed"]["verdict"] == "degenerate"


# =========================================================================== #
# AC23: no reference feature name is resolved ambiguously
# =========================================================================== #


def test_ac23_ambiguous_last_segment_match_resolves_to_none(observed_range_module, catalogue_module):
    # "mean" is not in PATH_ALIASES or INGESTED_INTENSITY_FEATURES, so a
    # reference feature literally named "mean" falls to rule (3), the
    # last-segment fallback -- and the shipped catalogue has >1 leaf path
    # ending in ".mean" (e.g. two distinct neighbourhood-stats means and
    # image_features' per-label first-order mean), which must resolve
    # ambiguously to none of them, mirroring item 110's AC11b discipline.
    driver_records = list(catalogue_module.iter_driver_records())
    leaf_union = set()
    for _driver_id, record in driver_records:
        leaf_union |= catalogue_module.iter_leaf_paths(record)
    candidates = [p for p in leaf_union if p.rstrip("[]").rsplit(".", 1)[-1] == "mean"]
    assert len(candidates) > 1, "expected the shipped catalogue to carry an ambiguous 'mean' last segment"

    ambiguous_reference = _make_reference_with_features({"mean": (1.0, 2.0)})
    ranges = observed_range_module.build_observed_ranges(
        driver_records=driver_records, reference=ambiguous_reference
    )
    for path in candidates:
        assert ranges[path].reference.covered is False, path


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_verdict_order_degenerate_beats_varies(observed_range_module):
    # A path that is reference-degenerate AND corpus-informative (non-zero
    # driver-set spread, exactly pre-123 offset_mm) must read "degenerate".
    dead_reference = _make_reference_distribution(
        {"spline_offset_mm": (_PRE123_MIN, _PRE123_MAX)}
    )
    ranges = observed_range_module.build_observed_ranges(reference=dead_reference)
    entry_range = ranges["stage3.per_label_offsets[].offset_mm"]
    assert entry_range.corpus.covered is True
    assert entry_range.corpus.informative is True
    assert entry_range.verdict == "degenerate"


def test_adv_verdict_order_placeholder_beats_varies(observed_range_module):
    # A driver record realising a placeholder-only path with a large
    # hand-typed constant must still read "placeholder", not "varies". Built
    # through the real dataclasses/converter (mirroring catalogue.py's own
    # "reference_delta" placeholder driver) so the record has the true
    # ``reference_delta.per_label.<label>...`` shape that
    # ``normalise_leaf_path`` rule (d) collapses to
    # ``reference_delta.{label}...`` -- a hand-nested
    # ``{"reference_delta": {"L1": ...}}`` dict does not normalise that way.
    from segfacet.reference.delta import (
        FeatureDelta,
        LabelDelta,
        ReferenceDelta,
        reference_delta_to_dict,
    )

    large_feature_delta = FeatureDelta(
        feature="physical_volume_mm3",
        value=18750.0,
        z_score=999999.0,
        robust_z=0.2,
        percentile_rank=55.0,
        out_of_range=False,
    )
    large_label_delta = LabelDelta(
        label=1,
        level_name="L1",
        stratum="all",
        available=True,
        features=(large_feature_delta,),
        distribution_distance=0.2,
        out_of_range_features=(),
    )
    large_reference_delta = ReferenceDelta(
        reference_delta_version="1.0",
        reference_schema_version="1.0",
        reference_source="synthetic-placeholder",
        stratum="all",
        lower_pct=1,
        upper_pct=99,
        per_label={1: large_label_delta},
    )
    driver_records = [
        (
            "reference_delta",
            {"reference_delta": reference_delta_to_dict(large_reference_delta)},
        )
    ]
    ranges = observed_range_module.build_observed_ranges(driver_records=driver_records)
    entry_range = ranges["reference_delta.{label}.features.physical_volume_mm3.z_score"]
    assert entry_range.corpus.informative is True
    assert entry_range.verdict == "placeholder"


def test_adv_floor_boundary_exactly_at_floor_not_informative(observed_range_module):
    floor = observed_range_module.NEGLIGIBLE_MAGNITUDE
    driver_records = [("clean", {"leaf": floor})]
    ranges = observed_range_module.build_observed_ranges(driver_records=driver_records)
    assert ranges["leaf"].corpus.magnitude == pytest.approx(floor)
    assert ranges["leaf"].corpus.informative is False


def test_adv_floor_boundary_just_above_floor_is_informative(observed_range_module):
    floor = observed_range_module.NEGLIGIBLE_MAGNITUDE
    just_above = floor + 1e-9
    driver_records = [("clean", {"leaf": just_above})]
    ranges = observed_range_module.build_observed_ranges(driver_records=driver_records)
    assert ranges["leaf"].corpus.informative is True


def test_adv_sign_handling_all_negative_population_is_informative(observed_range_module):
    driver_records = [
        ("clean", {"leaf": -500.0}),
        ("single_label", {"leaf": -1.0}),
    ]
    ranges = observed_range_module.build_observed_ranges(driver_records=driver_records)
    corpus = ranges["leaf"].corpus
    assert corpus.magnitude == pytest.approx(500.0)
    assert corpus.informative is True


def test_adv_boolean_values_are_not_numeric(full_catalogue):
    for path in (
        "stage3.per_label_offsets[].is_terminal",
        "relationships.is_continuous",
    ):
        entry = _entry(full_catalogue, path)
        assert entry.observed.verdict == "non-numeric", path
        assert entry.observed.corpus.covered is False, path


def test_adv_iter_leaf_values_bool_excluded_none_skipped(observed_range_module):
    record = {"a": True, "b": None, "c": 3.5}
    values = observed_range_module.iter_leaf_values(record)
    assert all(not isinstance(v, bool) for v in values.get("a", []))
    assert "b" not in values or values["b"] == []
    assert 3.5 in values.get("c", [])


@pytest.mark.parametrize(
    "path",
    [
        "per_label",
        "overlaps[]",
        "per_label.{label}.components.small_fragments[]",
        "stage3.monotonic_consistency.non_monotonic_pairs[]",
        "stage3.spacing_consistency.outlier_pairs[]",
        "reference_delta.{label}.out_of_range_features[]",
    ],
)
def test_adv_empty_container_paths_are_classified_not_dropped(full_catalogue, path):
    entry = _entry(full_catalogue, path)
    assert entry.observed.verdict in _VERDICTS, path


def test_adv_scalar_list_collected_element_wise(full_catalogue):
    entry = _entry(full_catalogue, "stage3.curvature.tangent_angles_deg[]")
    assert entry.observed.corpus.count is not None
    assert entry.observed.corpus.count > 1


def test_adv_build_observed_ranges_deterministic(observed_range_module, catalogue_module):
    driver_records = list(catalogue_module.iter_driver_records())
    first = observed_range_module.build_observed_ranges(driver_records=driver_records)
    second = observed_range_module.build_observed_ranges(driver_records=driver_records)
    assert first == second


def test_adv_build_observed_ranges_does_not_mutate_inputs(observed_range_module, catalogue_module):
    driver_records = list(catalogue_module.iter_driver_records())
    snapshot = copy.deepcopy(driver_records)
    reference = _bundled_reference()
    reference_snapshot = copy.deepcopy(reference)

    observed_range_module.build_observed_ranges(driver_records=driver_records, reference=reference)

    assert driver_records == snapshot
    assert reference == reference_snapshot


def test_adv_quantise_is_idempotent_over_shipped_values(catalogue_module, committed_json_dict):
    quantise = catalogue_module._quantise
    for group in committed_json_dict["groups"]:
        for entry in group["entries"]:
            for value in _walk_observed_floats(entry["observed"]):
                once = quantise(value)
                twice = quantise(once)
                assert once == twice, value


def test_adv_build_observed_ranges_empty_driver_records_returns_empty_mapping(
    observed_range_module,
):
    assert observed_range_module.build_observed_ranges(driver_records=[]) == {}


def test_adv_iter_leaf_values_empty_record_returns_empty_mapping(observed_range_module):
    assert observed_range_module.iter_leaf_values({}) == {}
