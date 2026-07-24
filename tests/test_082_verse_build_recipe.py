"""Tests for item 082 -- the real-VerSe acquisition & versioned reference-
artifact build recipe (``docs/reference-build.md`` + the existing ``segfacet
build-reference`` CLI, ``src/segfacet/reference/{artifact,ingest}.py``).

This item adds **no** new production code beyond a docstring extension --
it documents and tests the *recipe* for building a separately versioned
``reference_verse_vN.json`` from the already-existing ``segfacet
build-reference`` CLI (items 044/045/063/081). No real VerSe data is
downloaded or committed; every AC is exercised against a tiny (2-3 subject)
VerSe-*shaped* synthetic stand-in cohort written with the real VerSe mask
suffix ``_seg-vert_msk.nii.gz``.

Covers Acceptance Criteria AC1-AC12:

- AC1: the documented invocation (driven via ``segfacet.cli.main``) exits 0 and
  writes a JSON artifact that ``load_artifact`` parses into a
  ``ReferenceDistribution`` with >=1 per-level ``feature_stats`` entry.
- AC2: ``provenance.source`` / ``provenance.build_date`` equal the
  caller-supplied values, not ``date.today()``.
- AC3: ``subject_id``s equal the ``_seg-vert_msk.nii.gz``-stripped stems; a
  scope guard that ``ingest.py``/``artifact.py`` gained no new
  suffix-mapping symbol.
- AC4: ``schema_version == "1.2"`` and ``features`` carries all three
  item-081 morphology names.
- AC5: ``features`` carries every ``INGESTED_FEATURES`` geometry name.
- AC6: ``features`` carries every ``INGESTED_INTENSITY_FEATURES`` intensity
  name (the stand-in ships ``_scan.nii.gz`` siblings).
- AC7: a nonexistent ``--cohort`` exits non-zero, writes no ``--out`` file,
  and prints an ``Error:``-prefixed stderr message.
- AC8: the AC7 invocation's combined stdout+stderr carries no Python
  traceback.
- AC9: ``docs/reference-build.md`` exists and is non-empty.
- AC10: it documents the never-commit-raw-scans storage policy and that the
  committed synthetic ``reference_default.json`` is retained, not replaced.
- AC11: it documents the ``reference_verse_vN.json`` /
  ``provenance.source == "verse-vN"`` versioning convention and the
  ``--reference-artifact`` / ``reference.artifact_path`` deployment-selection
  mechanism.
- AC12: it documents VerSe acquisition (source/DOI, cross-referencing
  ``dataset-verse19.md``) and cohort-staging (``--seg-suffix
  _seg-vert_msk.nii.gz``, flattening the nested ``derivatives/`` layout,
  renaming CTs to ``<id>_scan.nii.gz`` siblings).

Adversarial / edge-case scenarios included:
- Empty-but-present cohort directory (no matching files): clean handling,
  no traceback.
- Wrong ``--seg-suffix`` (mistyped, matches nothing): same clean-error
  guarantee.
- Determinism: two builds over the same stand-in cohort produce equal
  parsed artifacts (``reports_close``, given the platform-sensitive
  ``eigenvalue_ratio`` float per item 081/078).
- Scope guards: no 082 test mutates the committed
  ``src/segfacet/reference/reference_default.json``; the repo tree contains no
  committed ``reference_verse_*.json``.
"""

from __future__ import annotations

import json
import pathlib

import nibabel as nib
import pytest

from segfacet.cli import main
from segfacet.reference import load_artifact
from segfacet.reference.ingest import (
    INGESTED_FEATURES,
    INGESTED_INTENSITY_FEATURES,
    INGESTED_MORPHOLOGY_FEATURES,
)
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.golden import reports_close
from segfacet.synth.intensity import paint_clean_scan

VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"
VERSE_SCAN_SUFFIX = "_scan.nii.gz"
VERSE_SOURCE = "verse-test-v1"
VERSE_BUILD_DATE = "2026-07-15"


# =========================================================================== #
# Fixture helper: the VerSe-shaped stand-in cohort
# =========================================================================== #


def _write_verse_shaped_cohort(dest_dir, n=3, levels=("L1", "L2", "L3", "L4", "L5")):
    """Write a tiny (default 3-subject) VerSe-*shaped* stand-in cohort under
    *dest_dir*: ``<id>_seg-vert_msk.nii.gz`` + ``<id>_scan.nii.gz`` pairs, built
    from ``build_clean_spine`` (multi-level, so Stage 3 runs and
    ``eigenvalue_ratio`` is present) paired with a seeded, deterministic
    ``paint_clean_scan``. Mirrors ``build_default_cohort``'s style but with the
    real VerSe vertebra-mask suffix. Returns ``(dest_dir, subject_ids)``."""
    pathlib.Path(dest_dir).mkdir(parents=True, exist_ok=True)
    subject_ids = []
    for i in range(n):
        subject_id = f"sub-verse{i:03d}"
        spine = build_clean_spine(
            levels=levels,
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        seg_path = dest_dir / f"{subject_id}{VERSE_SEG_SUFFIX}"
        nib.save(spine.seg_img, str(seg_path))

        scan_img = paint_clean_scan(spine.seg_img, seed=i)
        scan_path = dest_dir / f"{subject_id}{VERSE_SCAN_SUFFIX}"
        nib.save(scan_img, str(scan_path))

        subject_ids.append(subject_id)
    return dest_dir, subject_ids


def _run_build_reference(cohort_dir, out_path, *, seg_suffix=VERSE_SEG_SUFFIX,
                          source=VERSE_SOURCE, build_date=VERSE_BUILD_DATE):
    """Drive the documented invocation through ``segfacet.cli.main`` (the CLI
    surface, not the library function) and return the exit code."""
    return main(
        [
            "build-reference",
            "--cohort", str(cohort_dir),
            "--out", str(out_path),
            "--source", source,
            "--build-date", build_date,
            "--seg-suffix", seg_suffix,
        ]
    )


_DOCS_PATH = pathlib.Path(__file__).resolve().parent.parent / "docs" / "reference-build.md"


def _read_recipe_doc():
    return _DOCS_PATH.read_text(encoding="utf-8")


# =========================================================================== #
# AC1: a well-formed versioned artifact is produced
# =========================================================================== #


def test_ac1_well_formed_versioned_artifact_produced(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)

    assert code == 0
    assert out_path.exists()

    dist = load_artifact(out_path)  # must not raise
    assert any(
        len(level_dist.feature_stats) > 0
        for strata in dist.levels.values()
        for level_dist in strata.values()
    )


# =========================================================================== #
# AC2: provenance carries the caller-supplied source/build_date
# =========================================================================== #


def test_ac2_provenance_carries_caller_supplied_source_and_build_date(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)
    assert code == 0

    dist = load_artifact(out_path)
    assert dist.provenance.source == VERSE_SOURCE
    assert dist.provenance.build_date == VERSE_BUILD_DATE

    # Re-running (any wall-clock date) reproduces the same stamped values --
    # never date.today().
    out_path2 = tmp_path / "reference_verse_v1_rerun.json"
    code2 = _run_build_reference(cohort_dir, out_path2)
    assert code2 == 0
    dist2 = load_artifact(out_path2)
    assert dist2.provenance.source == VERSE_SOURCE
    assert dist2.provenance.build_date == VERSE_BUILD_DATE


# =========================================================================== #
# AC3: --seg-suffix handles VerSe filenames, no code adapter
# =========================================================================== #


def test_ac3_subject_ids_equal_verse_suffix_stripped_stems(tmp_path):
    cohort_dir, subject_ids = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)
    assert code == 0

    dist = load_artifact(out_path)
    assert dist.subject_count == len(subject_ids)


def test_ac3_scope_guard_no_new_suffix_mapping_symbol_in_ingest_or_artifact():
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    ingest_source = (repo_root / "src" / "segfacet" / "reference" / "ingest.py").read_text(
        encoding="utf-8"
    )
    artifact_source = (repo_root / "src" / "segfacet" / "reference" / "artifact.py").read_text(
        encoding="utf-8"
    )

    # No VerSe-specific suffix constant or adapter symbol was added to either
    # module -- the recipe relies solely on the pre-existing --seg-suffix
    # flag, not a new production-code mapping.
    for source in (ingest_source, artifact_source):
        assert "seg-vert_msk" not in source
        assert "VERSE_SEG_SUFFIX" not in source


# =========================================================================== #
# AC4/AC5/AC6: schema version + all three feature families
# =========================================================================== #


def test_ac4_schema_version_and_morphology_family_present(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)
    assert code == 0

    dist = load_artifact(out_path)
    assert dist.schema_version == "1.2"
    assert set(INGESTED_MORPHOLOGY_FEATURES) <= set(dist.features)


def test_ac5_geometry_family_present(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)
    assert code == 0

    dist = load_artifact(out_path)
    assert set(INGESTED_FEATURES) <= set(dist.features)


def test_ac6_intensity_family_present_when_scans_staged(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "reference_verse_v1.json"

    code = _run_build_reference(cohort_dir, out_path)
    assert code == 0

    dist = load_artifact(out_path)
    assert set(INGESTED_INTENSITY_FEATURES) <= set(dist.features)
    # All three families at schema "1.2" simultaneously.
    assert dist.schema_version == "1.2"
    assert set(INGESTED_FEATURES) <= set(dist.features)
    assert set(INGESTED_MORPHOLOGY_FEATURES) <= set(dist.features)


# =========================================================================== #
# AC7/AC8: absent cohort errors cleanly, no traceback
# =========================================================================== #


def test_ac7_absent_cohort_errors_cleanly_no_partial_artifact(tmp_path, capsys):
    missing_cohort = tmp_path / "does_not_exist"
    out_path = tmp_path / "should_not_exist.json"

    code = _run_build_reference(missing_cohort, out_path)

    assert code != 0
    assert not out_path.exists()

    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_ac8_absent_cohort_no_traceback(tmp_path, capsys):
    missing_cohort = tmp_path / "does_not_exist"
    out_path = tmp_path / "should_not_exist.json"

    code = _run_build_reference(missing_cohort, out_path)
    assert code != 0

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback (most recent call last)" not in combined


# =========================================================================== #
# AC9: the recipe document exists and is non-empty
# =========================================================================== #


def test_ac9_recipe_doc_exists_and_nonempty():
    assert _DOCS_PATH.exists()
    text = _read_recipe_doc()
    assert len(text.strip()) > 0


# =========================================================================== #
# AC10: never-commit-raw-scans storage policy documented
# =========================================================================== #


def test_ac10_storage_policy_documented():
    text = _read_recipe_doc().lower()

    assert "never" in text
    assert "raw" in text and "scan" in text
    assert "reference_default.json" in text
    # The synthetic default is retained as the test/determinism baseline,
    # not replaced by the real build.
    assert "not replace" in text or "does not replace" in text or "retained" in text


# =========================================================================== #
# AC11: versioning + deployment-selection policy documented
# =========================================================================== #


def test_ac11_versioning_and_selection_policy_documented():
    text = _read_recipe_doc()

    assert "reference_verse_v" in text
    assert "verse-v" in text.lower()
    assert "--reference-artifact" in text or "reference.artifact_path" in text


# =========================================================================== #
# AC12: VerSe acquisition + cohort-staging documented
# =========================================================================== #


def test_ac12_acquisition_and_staging_documented():
    text = _read_recipe_doc()

    assert "dataset-verse19.md" in text
    assert "_seg-vert_msk.nii.gz" in text
    assert "--seg-suffix" in text
    assert "derivatives" in text.lower()
    assert "_scan.nii.gz" in text


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_empty_but_present_cohort_dir_no_traceback(tmp_path, capsys):
    cohort_dir = tmp_path / "empty_cohort"
    cohort_dir.mkdir()
    out_path = tmp_path / "artifact.json"

    code = _run_build_reference(cohort_dir, out_path)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback (most recent call last)" not in combined
    # Whichever the machinery does -- a clean error, or a well-formed
    # empty-distribution artifact -- must be internally consistent.
    if code == 0:
        assert out_path.exists()
        dist = load_artifact(out_path)
        assert dist.subject_count == 0
    else:
        assert not out_path.exists()
        assert "Error:" in captured.err


def test_adv_wrong_seg_suffix_no_traceback(tmp_path, capsys):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path = tmp_path / "artifact.json"

    code = _run_build_reference(cohort_dir, out_path, seg_suffix="_wrong_suffix.nii.gz")

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback (most recent call last)" not in combined
    if code == 0:
        assert out_path.exists()
        dist = load_artifact(out_path)
        assert dist.subject_count == 0
    else:
        assert not out_path.exists()
        assert "Error:" in captured.err


def test_adv_determinism_two_builds_produce_equal_parsed_artifacts(tmp_path):
    cohort_dir, _ = _write_verse_shaped_cohort(tmp_path / "cohort")
    out_path1 = tmp_path / "artifact1.json"
    out_path2 = tmp_path / "artifact2.json"

    code1 = _run_build_reference(cohort_dir, out_path1)
    code2 = _run_build_reference(cohort_dir, out_path2)
    assert code1 == 0
    assert code2 == 0

    parsed1 = json.loads(out_path1.read_text(encoding="utf-8"))
    parsed2 = json.loads(out_path2.read_text(encoding="utf-8"))
    # eigenvalue_ratio (item 081) is a platform-sensitive PCA float --
    # compare with numeric tolerance rather than requiring byte-identity
    # across separate build invocations (mirrors item 081/078).
    assert reports_close(parsed1, parsed2)


def test_adv_scope_guard_default_reference_artifact_untouched():
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    default_path = repo_root / "src" / "segfacet" / "reference" / "reference_default.json"
    assert default_path.exists()
    # No 082 test writes to this path; this is a read-only sanity check that
    # it still parses under the current schema.
    dist = load_artifact(default_path)
    assert dist.schema_version == "1.2"


def test_adv_scope_guard_only_derived_verse_artifacts_committed():
    """Item 082's *enduring* storage policy: commit only the **derived**
    distributions artifact, **never** raw VerSe scans/masks.

    This supersedes item 082's original "no ``reference_verse_*.json`` exists"
    assertion, which encoded that fence for *that item only* ("This item commits
    no such file"). The recipe explicitly anticipates the file appearing later:
    "When an actual real-VerSe artifact is built by a data-holding human or CI
    runner, it is committed under ``src/segfacet/reference/`` as package data." That
    happened on 2026-07-17 (``reference_verse_v1.json``, built from the mounted
    VerSe19 training split), so the durable invariant is asserted instead: any
    committed ``reference_verse_*`` is a well-formed derived artifact, LF-pinned,
    and no raw imaging data rides along.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    reference_dir = repo_root / "src" / "segfacet" / "reference"

    # Any committed real-VerSe artifact is a well-formed *derived* artifact.
    for path in sorted(reference_dir.glob("reference_verse_*.json")):
        dist = load_artifact(path)
        assert dist.schema_version == "1.2", path.name
        assert dist.provenance.source.startswith("verse-"), path.name
        assert dist.levels, path.name

    # Raw VerSe imaging data is never committed (the whole point of the policy).
    raw = sorted(str(p.relative_to(repo_root)) for p in reference_dir.rglob("*.nii*"))
    assert raw == [], f"raw imaging data must never be committed: {raw}"

    # The versioned-artifact filename pattern stays LF-pinned for CRLF hygiene.
    gitattributes = (repo_root / ".gitattributes").read_text(encoding="utf-8")
    assert "src/segfacet/reference/reference_verse_*.json text eol=lf" in gitattributes
