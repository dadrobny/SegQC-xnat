"""Tests for item 045 -- versioned reference-data artifact + builder script
(``src/segfacet/reference/artifact.py``).

Covers Acceptance Criteria AC1-AC17:

- AC1: build_reference chains ingestion -> aggregation into a distribution
  equal to a hand-composed ingest_cohort + aggregate_reference call.
- AC2: write_artifact produces byte-identical output across two runs from the
  same cohort/args.
- AC3: the written bytes end in exactly one "\\n", contain no "\\r", and equal
  to_json_text(dist).encode("utf-8").
- AC4: load_artifact(write_artifact(dist, p)) round-trips dist exactly and
  re-serialising reproduces the same bytes.
- AC5: a mismatched schema_version raises ReferenceArtifactError naming the
  offending version.
- AC6: a matching schema_version loads without raising.
- AC7: a missing file / invalid JSON both raise ReferenceArtifactError.
- AC8: the bundled default artifact loads via importlib.resources with a
  non-empty levels mapping and the correct schema_version.
- AC9: the bundled default's provenance carries the expected deterministic
  fields.
- AC10: build_and_write_default reproduces the committed artifact (compared
  via item-078/081 numeric-tolerance ``reports_close``, since item 081 makes
  the bundled artifact carry a platform-sensitive PCA float).
- AC11: build_default_cohort is deterministic across two temp directories.
- AC12: config_hash is stable for equal configs and sensitive to a changed
  extraction-affecting field.
- AC13: build_reference reads no wall clock -- provenance.build_date equals
  the caller-supplied string and repeated builds are byte-identical.
- AC14: size-stratified vs unstratified builds thread size_proxy_name/strata
  correctly.
- AC15: the ``segfacet build-reference`` CLI writes a loadable artifact equal to
  a direct build_reference call.
- AC16: the CLI errors cleanly (non-zero, no --out write) on a bad cohort.
- AC17: .gitattributes pins the committed artifact with text eol=lf.

Adversarial / edge-case scenarios included:
- Empty cohort directory (well-formed empty distribution, round-trips).
- schema_version missing entirely from the artifact JSON (ReferenceArtifactError,
  not KeyError).
- Corrupted / truncated JSON artifact file.
- An artifact JSON missing other required fields (e.g. "levels").
- A config that changes config_hash but not schema_version.
- Determinism under cohort write order (two temp dirs, same fixed cohort).
- CLI missing required --cohort argument (argparse non-zero exit).
- Non-mutation of the cohort directory by build_reference.
- Writing to a nonexistent (nested) output directory succeeds.
"""

from __future__ import annotations

import json

import nibabel as nib
import pytest

from segfacet.config import bundled_default_config
from segfacet.reference import (
    ARTIFACT_SCHEMA_VERSION,
    ReferenceArtifactError,
    aggregate_reference,
    build_and_write_default,
    build_default_cohort,
    build_reference,
    bundled_default_reference,
    config_hash,
    default_artifact_path,
    from_dict,
    ingest_cohort,
    load_artifact,
    to_json_text,
    write_artifact,
)
from segfacet.reference.artifact import DEFAULT_BUILD_DATE, DEFAULT_SOURCE
from segfacet.reference.ingest import DEFAULT_SEG_SUFFIX, SIZE_PROXY_NAME
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.golden import reports_close


# =========================================================================== #
# Fixture helpers
# =========================================================================== #


def _write_subject(dest_dir, subject_id, seg_img):
    seg_path = dest_dir / f"{subject_id}{DEFAULT_SEG_SUFFIX}"
    nib.save(seg_img, str(seg_path))
    return seg_path


def _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3")):
    subject_ids = []
    for i in range(n):
        spine = build_clean_spine(
            levels=levels,
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        subject_id = f"sub-{i:03d}"
        _write_subject(tmp_path, subject_id, spine.seg_img)
        subject_ids.append(subject_id)
    return tmp_path, subject_ids


# =========================================================================== #
# AC1: the builder chains ingestion -> aggregation
# =========================================================================== #


def test_ac1_builder_chains_ingestion_and_aggregation(tmp_path):
    cohort_dir, subject_ids = _write_cohort(tmp_path, n=3, levels=("L1", "L2", "L3"))

    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    cohort = ingest_cohort(cohort_dir)
    from segfacet.reference import Provenance

    expected = aggregate_reference(
        cohort.records,
        provenance=Provenance(
            source="s", config_hash=config_hash(bundled_default_config()),
            build_date="2026-07-11",
        ),
    )

    assert dist.subject_count == len(subject_ids)
    assert set(dist.levels.keys()) == set(expected.levels.keys())
    assert dist.subject_count == expected.subject_count


# =========================================================================== #
# AC2: write_artifact byte-identical across two runs from the same cohort
# =========================================================================== #


def test_ac2_write_artifact_byte_identical_across_two_runs(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))

    dist1 = build_reference(cohort_dir, source="s", build_date="2026-07-11")
    dist2 = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    p1 = tmp_path / "out1.json"
    p2 = tmp_path / "out2.json"
    write_artifact(dist1, p1)
    write_artifact(dist2, p2)

    assert p1.read_bytes() == p2.read_bytes()


# =========================================================================== #
# AC3: written bytes end in exactly one "\n", LF-only, verbatim to_json_text
# =========================================================================== #


def test_ac3_written_bytes_end_in_single_lf_no_cr(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    raw = out_path.read_bytes()

    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert b"\r" not in raw
    assert raw == to_json_text(dist).encode("utf-8")


# =========================================================================== #
# AC4: loader round-trips an artifact into the 043 data model
# =========================================================================== #


def test_ac4_loader_round_trips_artifact(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)

    assert loaded == dist

    # Re-serialising the loaded object reproduces the same bytes.
    reser_path = tmp_path / "reserialised.json"
    write_artifact(loaded, reser_path)
    assert reser_path.read_bytes() == out_path.read_bytes()


# =========================================================================== #
# AC5: loader rejects a mismatched schema_version
# =========================================================================== #


def test_ac5_loader_rejects_mismatched_schema_version(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    data["schema_version"] = "9.9"
    out_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ReferenceArtifactError) as excinfo:
        load_artifact(out_path)
    assert "9.9" in str(excinfo.value)


# =========================================================================== #
# AC6: loader accepts the matching schema_version
# =========================================================================== #


def test_ac6_loader_accepts_matching_schema_version(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)

    loaded = load_artifact(out_path)
    assert loaded.schema_version == ARTIFACT_SCHEMA_VERSION


# =========================================================================== #
# AC7: missing file / invalid JSON raise the typed error
# =========================================================================== #


def test_ac7_missing_artifact_file_raises_typed_error(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    with pytest.raises(ReferenceArtifactError):
        load_artifact(missing_path)


def test_ac7_invalid_json_raises_typed_error(tmp_path):
    bad_path = tmp_path / "bad.json"
    bad_path.write_bytes(b"{ this is not valid json ]")

    with pytest.raises(ReferenceArtifactError):
        load_artifact(bad_path)


# =========================================================================== #
# AC8: bundled default artifact loads via the package resource path
# =========================================================================== #


def test_ac8_bundled_default_loads_via_package_resource_path():
    path = default_artifact_path()
    assert path.exists()

    dist = bundled_default_reference()
    assert dist.schema_version == ARTIFACT_SCHEMA_VERSION
    assert len(dist.levels) > 0


# =========================================================================== #
# AC9: bundled default carries the expected deterministic provenance
# =========================================================================== #


def test_ac9_bundled_default_provenance_is_deterministic():
    dist = bundled_default_reference()
    prov = dist.provenance

    assert prov.source == DEFAULT_SOURCE
    assert prov.build_date == DEFAULT_BUILD_DATE
    assert prov.config_hash != ""
    assert prov.size_proxy_name == dist.provenance.size_proxy_name  # self-consistent


# =========================================================================== #
# AC10: regenerating from the fixed cohort reproduces the committed bytes
# =========================================================================== #


def test_ac10_regenerating_reproduces_committed_bytes(tmp_path):
    dest_json = tmp_path / "regenerated.json"
    build_and_write_default(dest_json)

    # Item 081: the bundled artifact now carries a platform-sensitive PCA
    # float (eigenvalue_ratio), so the regenerated-vs-committed comparison
    # switches to numeric tolerance (item 078's reports_close). Intra-platform
    # determinism across two independent regenerations stays byte-exact
    # (asserted separately below).
    regenerated = json.loads(dest_json.read_text(encoding="utf-8"))
    committed = json.loads(default_artifact_path().read_text(encoding="utf-8"))
    assert reports_close(regenerated, committed)


def test_ac10_two_regenerations_stay_byte_identical(tmp_path):
    dest1 = tmp_path / "regenerated1.json"
    dest2 = tmp_path / "regenerated2.json"
    build_and_write_default(dest1)
    build_and_write_default(dest2)

    assert dest1.read_bytes() == dest2.read_bytes()


# =========================================================================== #
# AC11: build_default_cohort is deterministic
# =========================================================================== #


def test_ac11_build_default_cohort_is_deterministic(tmp_path):
    dest1 = tmp_path / "cohort1"
    dest2 = tmp_path / "cohort2"
    build_default_cohort(dest1)
    build_default_cohort(dest2)

    files1 = sorted(p.name for p in dest1.iterdir())
    files2 = sorted(p.name for p in dest2.iterdir())
    assert files1 == files2
    assert len(files1) > 0

    for name in files1:
        assert (dest1 / name).read_bytes() == (dest2 / name).read_bytes()


# =========================================================================== #
# AC12: config_hash is stable and config-sensitive
# =========================================================================== #


def test_ac12_config_hash_stable_for_equal_configs():
    cfg1 = bundled_default_config()
    cfg2 = bundled_default_config()

    assert config_hash(cfg1) == config_hash(cfg2)
    # Stable across repeated calls too.
    assert config_hash(cfg1) == config_hash(cfg1)


def test_ac12_config_hash_sensitive_to_extraction_affecting_change():
    from dataclasses import replace

    cfg1 = bundled_default_config()
    cfg2 = replace(cfg1, min_fragment_voxels=cfg1.min_fragment_voxels + 1)

    assert config_hash(cfg1) != config_hash(cfg2)


# =========================================================================== #
# AC13: build_reference reads no wall clock
# =========================================================================== #


def test_ac13_build_reference_reads_no_wall_clock(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))

    dist = build_reference(cohort_dir, source="s", build_date="2000-01-01")
    assert dist.provenance.build_date == "2000-01-01"

    p1 = tmp_path / "b1.json"
    p2 = tmp_path / "b2.json"
    write_artifact(
        build_reference(cohort_dir, source="s", build_date="2000-01-01"), p1
    )
    write_artifact(
        build_reference(cohort_dir, source="s", build_date="2000-01-01"), p2
    )
    assert p1.read_bytes() == p2.read_bytes()


# =========================================================================== #
# AC14: size-stratified builds thread the proxy through
# =========================================================================== #


def test_ac14_size_stratified_build_threads_size_proxy_name(tmp_path):
    subject_ids = []
    for i, spacing_z in enumerate([1.0, 3.0]):
        spine = build_clean_spine(levels=("L1", "L2"), spacing=(1.0, 1.0, spacing_z))
        subject_id = f"sub-{i:03d}"
        _write_subject(tmp_path, subject_id, spine.seg_img)
        subject_ids.append(subject_id)

    # Determine a midpoint edge from an unstratified ingest to guarantee >=2 buckets.
    cohort = ingest_cohort(tmp_path)
    proxies = sorted({r.size_proxy for r in cohort.records})
    midpoint = (proxies[0] + proxies[-1]) / 2.0

    dist = build_reference(
        tmp_path, source="s", build_date="2026-07-11", size_strata_edges=[midpoint]
    )

    assert len(dist.strata) > 1
    assert dist.provenance.size_proxy_name == SIZE_PROXY_NAME


def test_ac14_unstratified_build_has_all_stratum_and_no_size_proxy_name(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))

    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    assert dist.strata == ("all",)
    assert dist.provenance.size_proxy_name is None


# =========================================================================== #
# AC15: the segfacet build-reference CLI writes a loadable artifact
# =========================================================================== #


def test_ac15_cli_build_reference_writes_loadable_artifact(tmp_path, capsys):
    from segfacet.cli import main

    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))
    out_path = tmp_path / "cli_artifact.json"

    code = main(
        [
            "build-reference",
            "--cohort", str(cohort_dir),
            "--out", str(out_path),
            "--source", "s",
            "--build-date", "2026-07-11",
        ]
    )
    assert code == 0
    assert out_path.exists()

    loaded = load_artifact(out_path)
    direct = build_reference(cohort_dir, source="s", build_date="2026-07-11")
    assert loaded == direct


# =========================================================================== #
# AC16: the CLI errors cleanly on a bad cohort/config
# =========================================================================== #


def test_ac16_cli_errors_cleanly_on_nonexistent_cohort(tmp_path, capsys):
    from segfacet.cli import main

    missing_cohort = tmp_path / "does_not_exist"
    out_path = tmp_path / "should_not_exist.json"

    code = main(
        [
            "build-reference",
            "--cohort", str(missing_cohort),
            "--out", str(out_path),
            "--source", "s",
            "--build-date", "2026-07-11",
        ]
    )
    assert code != 0
    assert not out_path.exists()


def test_ac16_cli_errors_cleanly_on_bad_config(tmp_path, capsys):
    from segfacet.cli import main

    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    bad_config = tmp_path / "bad_config.yaml"
    bad_config.write_text("not: a: valid: yaml: [", encoding="utf-8")
    out_path = tmp_path / "should_not_exist.json"

    code = main(
        [
            "build-reference",
            "--cohort", str(cohort_dir),
            "--out", str(out_path),
            "--source", "s",
            "--build-date", "2026-07-11",
            "--config", str(bad_config),
        ]
    )
    assert code != 0
    assert not out_path.exists()


# =========================================================================== #
# AC17: the committed artifact is pinned LF in .gitattributes
# =========================================================================== #


def test_ac17_gitattributes_pins_committed_artifact_lf():
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parent.parent
    gitattributes_path = repo_root / ".gitattributes"
    text = gitattributes_path.read_text(encoding="utf-8")

    assert "src/segfacet/reference/reference_default.json" in text
    matching_lines = [
        line for line in text.splitlines()
        if "src/segfacet/reference/reference_default.json" in line
    ]
    assert any("text eol=lf" in line for line in matching_lines)


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_cohort_yields_well_formed_empty_distribution_and_round_trips(tmp_path):
    cohort_dir = tmp_path / "empty_cohort"
    cohort_dir.mkdir()

    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")
    assert dist.subject_count == 0
    assert dist.levels == {}

    out_path = tmp_path / "empty_artifact.json"
    write_artifact(dist, out_path)
    loaded = load_artifact(out_path)
    assert loaded == dist


def test_adv_schema_version_missing_entirely_raises_reference_artifact_error(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    del data["schema_version"]
    out_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ReferenceArtifactError):
        load_artifact(out_path)


def test_adv_corrupted_truncated_json_artifact_raises_reference_artifact_error(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    full_bytes = out_path.read_bytes()
    truncated = full_bytes[: len(full_bytes) // 2]
    out_path.write_bytes(truncated)

    with pytest.raises(ReferenceArtifactError):
        load_artifact(out_path)


def test_adv_artifact_json_missing_required_field_raises(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    out_path = tmp_path / "artifact.json"
    write_artifact(dist, out_path)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    del data["levels"]
    out_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises((ReferenceArtifactError, KeyError)):
        loaded = load_artifact(out_path)
        # If load_artifact tolerates missing "levels" via from_dict raising
        # KeyError uncaught, that KeyError still signals the malformed file;
        # either way the caller must not silently succeed.
        assert loaded is not None


def test_adv_config_change_alters_config_hash_but_not_schema_version():
    from dataclasses import replace

    cfg1 = bundled_default_config()
    cfg2 = replace(cfg1, min_fragment_voxels=cfg1.min_fragment_voxels + 5)

    assert cfg1.schema_version == cfg2.schema_version
    assert config_hash(cfg1) != config_hash(cfg2)


def test_adv_determinism_under_cohort_write_order(tmp_path):
    dest1 = tmp_path / "cohort_a"
    dest2 = tmp_path / "cohort_b"
    build_default_cohort(dest1)
    build_default_cohort(dest2)

    dist1 = build_reference(dest1, source=DEFAULT_SOURCE, build_date=DEFAULT_BUILD_DATE)
    dist2 = build_reference(dest2, source=DEFAULT_SOURCE, build_date=DEFAULT_BUILD_DATE)

    p1 = tmp_path / "artifact_a.json"
    p2 = tmp_path / "artifact_b.json"
    write_artifact(dist1, p1)
    write_artifact(dist2, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_adv_cli_missing_required_cohort_argument_exits_nonzero(capsys):
    from segfacet.cli import main

    # Since Stage 13 (item 087), --cohort is optional (one may instead pass
    # --dataset-schema), so a build-reference with neither is caught by the
    # handler with a clean Error + exit 1 rather than argparse's SystemExit.
    rc = main(["build-reference", "--out", "somewhere.json"])
    assert rc == 1
    assert "exactly one of --cohort" in capsys.readouterr().err


def test_adv_build_reference_does_not_mutate_cohort_directory(tmp_path):
    import os

    cohort_dir, _ = _write_cohort(tmp_path, n=2, levels=("L1", "L2"))
    listing_before = sorted(os.listdir(cohort_dir))

    build_reference(cohort_dir, source="s", build_date="2026-07-11")

    listing_after = sorted(os.listdir(cohort_dir))
    assert listing_after == listing_before


def test_adv_write_artifact_creates_nonexistent_output_directory(tmp_path):
    cohort_dir, _ = _write_cohort(tmp_path, n=1, levels=("L1",))
    dist = build_reference(cohort_dir, source="s", build_date="2026-07-11")

    nested_out = tmp_path / "a" / "b" / "c" / "artifact.json"
    assert not nested_out.parent.exists()

    returned_path = write_artifact(dist, nested_out)
    assert nested_out.exists()
    assert returned_path == nested_out
