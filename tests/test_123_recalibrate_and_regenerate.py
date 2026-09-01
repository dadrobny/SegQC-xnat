"""Tests for item 123 -- recalibrate and regenerate every downstream artifact.

Covers Acceptance Criteria AC1-AC34
(docs/aide/items/123-recalibrate-and-regenerate-downstream-artifacts.md):

- AC1-AC8: ``scripts/rebuild_verse_reference.py`` -- the standalone tool, run
  against stand-in (never real) cohorts built in ``tmp_path``.
- AC9-AC11: ``derive_max_offset_mm`` against hand-built
  ``ReferenceDistribution``s -- no cohort involved.
- AC12-AC17: the recalibrated threshold -- shipped-default agreement, the
  config<->code agreement, the corpus window, the corpus firing behaviour,
  the docstring's recorded margins, and the calibration summary shape.
- AC18-AC22: the two reference artifacts (``reference_verse_v1.json``,
  ``reference_default.json``).
- AC23-AC27: the nine corpus goldens and the Stage-3 report golden.
- AC28: the pinned finding snapshot in ``test_098_stray_components.py``
  tracks the new threshold.
- AC29-AC32: ``.gitignore`` / ``dataset-verse19.md`` / ``reference-build.md``
  text assertions.
- AC33-AC34: the stale-pin reconciliations (sha256 fence tracking, item 120's
  two deferral fences retired).

This module never imports the real VerSe19 cohort. Every test that resolves
``SEGFACET_VERSE_COHORT`` explicitly clears it first (autouse fixture below)
-- this machine has the real ~6.6 GB cohort mounted (see the item's
Description), and an accidental real-cohort run would make the unit suite
slow, non-deterministic across machines, and would write nothing this test
module expects.

Summary shape pinned by this module (the tool does not exist yet; this is
the test-writer's contract for the builder, mirroring how
``tests/test_083_refresh_reference.py`` pins ``refresh_reference.py``'s step
names) -- ``<out>/verse_rebuild_summary.json``::

    {
      "cohort": {"status", "reason", "root", "mask_count", "discovery_glob",
                 "case_ids"},
      "staging": {"status", "stage_mode", "staged_dir",
                  "subjects_without_scan": [{"subject_id", "reason"}, ...]},
      "build": {"status", "artifact_path", "subject_count", "levels",
                "config_hash"},
      "calibration": {"status", "p99_by_level", "qualifying_levels", "P",
                       "level_at_p", "threshold",
                       "subject_levels_above_threshold": {"count", "fraction"},
                       "top_subject_ids"},
    }

Adversarial / edge cases included:
- A cohort root that is a symlink.
- A subject id collision after suffix stripping.
- A single-label mask and an exactly-four-level mask (the item-120 estimator
  fallback boundary: every offset reads 0.0 mm).
- Re-running the tool into the same ``--out``.
- ``--out`` under a not-yet-existing nested parent.
- ``SEGFACET_VERSE_COHORT`` set to an empty string (treated as unset).
- ``derive_max_offset_mm`` on a p99 exactly at a 0.5 mm multiple (the
  "strictly greater" half of AC10).
- Determinism of two tool runs against the same stand-in cohort.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import nibabel as nib
import pytest

from segfacet.config import bundled_default_config, default_config_path, load_config
from segfacet.reference import (
    ALL_STRATUM,
    FeatureStats,
    LevelDistribution,
    Provenance,
    ReferenceDistribution,
    bundled_default_reference,
    bundled_production_reference,
    bundled_production_reference_path,
    config_hash,
    load_artifact,
)
from segfacet.reference.artifact import build_and_write_default, default_artifact_path
from segfacet.features.centroids import compute_centroid
from segfacet.features.spline_offset import (
    compute_leave_one_out_spline_offsets,
    compute_spline_offsets,
)
from segfacet.features.spline import fit_centroid_spline
import segfacet.heuristics.mislabel  # noqa: F401 -- triggers MislabelRule registration
from segfacet.heuristics import run_rules
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import (
    assert_matches_committed_artifact,
    build_report_for_case,
    write_goldens,
)
from segfacet.synth.intensity import paint_clean_scan
from segfacet.synth.regression import pipeline_findings, pipeline_verdict_label

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _REPO_ROOT / "scripts" / "rebuild_verse_reference.py"
_ENV_VAR = "SEGFACET_VERSE_COHORT"
_VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"


# =========================================================================== #
# Fixtures / helpers
# =========================================================================== #


@pytest.fixture(autouse=True)
def _clear_verse_cohort_env(monkeypatch):
    """This machine has the real VerSe19 cohort mounted (item background) --
    every test in this module resolves the cohort explicitly, never through
    a real ambient environment variable."""
    monkeypatch.delenv(_ENV_VAR, raising=False)


def _load_tool():
    spec = importlib.util.spec_from_file_location("rebuild_verse_reference", _MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _read_summary(out: Path) -> dict:
    return json.loads((out / "verse_rebuild_summary.json").read_text(encoding="utf-8"))


def _write_standin_subject(
    root: Path,
    subject_id: str,
    *,
    levels=("L1", "L2", "L3", "L4", "L5"),
    spacing=(1.0, 1.0, 1.0),
    curve_amplitude_mm=6.0,
    nested: bool = True,
    with_scan: bool = True,
) -> Path:
    """Write one stand-in VerSe-shaped subject: a mask named
    ``<id>_seg-vert_msk.nii.gz`` and (optionally) a CT sibling named
    ``<id>_ct.nii.gz`` -- the real VerSe naming (docs/aide/dataset-
    verse19.md), never the synth-corpus ``_seg.nii.gz`` convention.

    ``nested=True`` places the mask/CT under an extra ``wrapper/derivatives``
    / ``wrapper/rawdata`` layer (the zip-extraction wrapper the item's AC4
    exercises); ``nested=False`` places them directly under *root*. Returns
    the mask path.
    """
    spine = build_clean_spine(levels=levels, spacing=spacing, curve_amplitude_mm=curve_amplitude_mm)

    if nested:
        mask_dir = root / "wrapper" / "derivatives" / subject_id
        ct_dir = root / "wrapper" / "rawdata" / subject_id
    else:
        mask_dir = root
        ct_dir = root
    mask_dir.mkdir(parents=True, exist_ok=True)
    ct_dir.mkdir(parents=True, exist_ok=True)

    mask_path = mask_dir / f"{subject_id}{_VERSE_SEG_SUFFIX}"
    nib.save(spine.seg_img, str(mask_path))

    if with_scan:
        scan_img = paint_clean_scan(spine.seg_img, seed=0)
        nib.save(scan_img, str(ct_dir / f"{subject_id}_ct.nii.gz"))

    return mask_path


def _build_standin_cohort(root: Path, *, n: int = 2, nested: bool = True, with_scan=True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        _write_standin_subject(
            root,
            f"sub-verse{i:03d}",
            spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
            nested=nested,
            with_scan=with_scan,
        )
    return root


def _no_traceback(text: str) -> bool:
    return "Traceback (most recent call last)" not in text


def _walk_tree(root: Path) -> dict:
    """Map of relative path -> mtime_ns for every file beneath *root*.

    ``.as_posix()``, never a bare ``str()`` of a ``relative_to(...)`` result
    -- conventions.md §6: a relative Path rendered with ``str()`` carries the
    OS-native separator, so the same tree would hash/compare differently on
    Windows even though nothing about the tree actually changed.
    """
    return {
        p.relative_to(root).as_posix(): p.stat().st_mtime_ns
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _feature_stats(p99: float, count: int = 10) -> FeatureStats:
    mean = p99 / 2.0
    return FeatureStats(
        count=count,
        mean=mean,
        std=1.0,
        min=0.0,
        max=p99,
        percentiles={
            "p1": 0.0, "p5": 0.0, "p25": mean * 0.5, "p50": mean,
            "p75": mean * 1.5, "p95": p99 * 0.9, "p99": p99,
        },
    )


def _level_dist(level_name: str, *, p99, count: int = 10, no_spline_offset=False) -> LevelDistribution:
    feature_stats = {} if no_spline_offset else {"spline_offset_mm": _feature_stats(p99, count=count)}
    return LevelDistribution(
        level_name=level_name, stratum=ALL_STRATUM, record_count=count, feature_stats=feature_stats,
    )


def _distribution(levels: dict) -> ReferenceDistribution:
    provenance = Provenance(
        source="unit-test", config_hash="deadbeef", build_date="2026-08-29", size_proxy_name=None,
    )
    return ReferenceDistribution(
        schema_version="1.2",
        provenance=provenance,
        features=("spline_offset_mm",),
        percentiles=(1, 5, 25, 50, 75, 95, 99),
        subject_count=sum(d.record_count for d in levels.values()),
        strata=(ALL_STRATUM,),
        levels={name: {ALL_STRATUM: dist} for name, dist in levels.items()},
    )


#: The fixed pre-123 commit: the last commit on ``aide/queue-017`` before
#: item 123's first commit (``4a2ae50``, "docs(123): work item spec ..."),
#: i.e. ``51d8e41``'s "progress(aide): item 121 -> done" -- the state
#: carrying items 119-122 and nothing of 123. Verified to lack
#: ``is_terminal`` anywhere in the committed ``clean_control`` corpus-golden
#: snapshot (retired by item 126).
#:
#: Pinned as a literal SHA, deliberately NOT a live
#: ``git merge-base HEAD aide/queue-017``: that live form self-invalidates
#: the moment item 123 actually merges into its recorded base, because a
#: fast-forward merge makes HEAD and ``aide/queue-017`` the *same* commit --
#: the merge-base of a branch with itself is itself, so ``git show`` would
#: then serve the POST-123 goldens as the "pre-123" baseline,
#: ``_diff_leaves`` would return ``[]``, and ``assert diffs`` would fail on
#: perfectly correct, already-merged goldens (observed post-merge on
#: ``aide/queue-017``, 2026-08-30). A fixed SHA names one immutable commit
#: regardless of what any branch pointer does afterwards, so it has no such
#: failure mode.
_PRE_123_BASE_SHA = "51d8e411b2ccc14ff10c4c244005ba007b4217d9"


def _pre_123_base_rev():
    """Verify the pinned pre-123 SHA (``_PRE_123_BASE_SHA``) is reachable in
    this checkout and return it. ``pytest.skip`` -- never a silent
    ``None``-and-guess -- if it is not: e.g. a shallow clone that never
    fetched history back that far. This realises the Testing Strategy's "if
    reading the pre-123 revision from git is not available to the test
    runner" fallback: with a pinned SHA the only way it becomes unavailable
    is missing history, which no weaker text-only substitute can compensate
    for meaningfully either, so skipping is the honest outcome."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{_PRE_123_BASE_SHA}^{{commit}}"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception as exc:  # pragma: no cover - defensive
        pytest.skip(f"git unavailable to resolve the pinned pre-123 commit: {exc}")
    if result.returncode != 0:
        pytest.skip(
            f"pinned pre-123 commit {_PRE_123_BASE_SHA} is not reachable in this "
            "checkout (likely a shallow clone) -- cannot diff against it"
        )
    return _PRE_123_BASE_SHA


def _git_show_json(rev: str, relpath: str):
    try:
        result = subprocess.run(
            ["git", "show", f"{rev}:{relpath}"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _diff_leaves(old, new, prefix: str = "") -> list:
    """Leaf-level diffs between two JSON-shaped values (dicts/lists/scalars),
    as ``(path, old_value, new_value)`` triples -- carrying the values
    directly avoids re-parsing a path string back through an ambiguous
    dict-key-vs-list-index guess (a dict keyed by a numeric-looking string,
    e.g. ``per_label["22"]``, is indistinguishable from a list index by path
    text alone). Never crashes on a shape mismatch: a differing type/length
    is one leaf."""
    if isinstance(old, dict) and isinstance(new, dict):
        results = []
        for key in sorted(set(old) | set(new)):
            child_prefix = f"{prefix}.{key}" if prefix else key
            results.extend(_diff_leaves(old.get(key), new.get(key), child_prefix))
        return results
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        results = []
        for i, (o, n) in enumerate(zip(old, new)):
            results.extend(_diff_leaves(o, n, f"{prefix}[{i}]"))
        return results
    return [] if old == new else [(prefix, old, new)]


# =========================================================================== #
# AC1: the tool runs standalone and writes its summary
# =========================================================================== #


def test_ac1_runs_standalone_no_cohort_writes_valid_summary(tmp_path):
    rr = _load_tool()
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])

    assert rc == 0
    summary_path = out / "verse_rebuild_summary.json"
    assert summary_path.is_file()
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data, "summary must be non-empty JSON"


def test_ac1_main_is_callable_with_argv_list():
    rr = _load_tool()
    assert callable(rr.main)


# =========================================================================== #
# AC2: the cohort root is machine-local configuration, never hard-coded
# =========================================================================== #


def test_ac2_no_literal_dataset_path_in_source():
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "dataset-verse19training" not in source
    # No absolute Unix path literal into a real filesystem location.
    assert "/mnt/" not in source
    assert "/home/" not in source
    assert "C:\\\\" not in source and "C:/" not in source


def test_ac2_resolves_from_env_var_when_no_cli_flag(tmp_path, monkeypatch):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=1)
    monkeypatch.setenv(_ENV_VAR, str(cohort))

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "ran"
    assert summary["cohort"]["mask_count"] == 1


def test_ac2_cli_flag_overrides_env_var(tmp_path, monkeypatch):
    rr = _load_tool()
    real_cohort = _build_standin_cohort(tmp_path / "cli-cohort", n=1)
    bogus_env_cohort = tmp_path / "does-not-exist"
    monkeypatch.setenv(_ENV_VAR, str(bogus_env_cohort))

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(real_cohort)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "ran"
    assert summary["cohort"]["mask_count"] == 1


def test_ac2_no_flag_no_env_is_not_found(tmp_path):
    rr = _load_tool()
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "skipped"
    assert summary["cohort"]["reason"]


# =========================================================================== #
# AC3: an unreachable cohort is a structured skip, not a failure
# =========================================================================== #


def test_ac3_missing_root_is_structured_skip_exit_zero(tmp_path):
    rr = _load_tool()
    out = tmp_path / "out"
    missing = tmp_path / "no-such-cohort"

    rc = rr.main(["--out", str(out), "--verse-cohort", str(missing)])

    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "skipped"
    assert summary["cohort"]["reason"]


def test_ac3_existing_root_no_matching_masks_is_structured_skip(tmp_path):
    rr = _load_tool()
    out = tmp_path / "out"
    empty_root = tmp_path / "empty-cohort"
    empty_root.mkdir()

    rc = rr.main(["--out", str(out), "--verse-cohort", str(empty_root)])

    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "skipped"
    assert summary["cohort"]["reason"]


def test_ac3_missing_root_no_traceback_and_writes_nothing_outside_out(tmp_path):
    rr = _load_tool()
    out = tmp_path / "out"
    missing = tmp_path / "no-such-cohort"

    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = rr.main(["--out", str(out), "--verse-cohort", str(missing)])

    assert rc == 0
    assert _no_traceback(buf.getvalue())
    # Nothing written outside --out: tmp_path's only child is "out".
    children = {p.name for p in tmp_path.iterdir()}
    assert children == {"out"}


# =========================================================================== #
# AC4: mask discovery is layout-agnostic
# =========================================================================== #


def test_ac4_nested_and_flat_layouts_yield_same_case_list(tmp_path):
    rr = _load_tool()
    nested_cohort = _build_standin_cohort(tmp_path / "nested", n=3, nested=True)
    flat_cohort = _build_standin_cohort(tmp_path / "flat", n=3, nested=False)

    out_nested = tmp_path / "out-nested"
    out_flat = tmp_path / "out-flat"
    rc1 = rr.main(["--out", str(out_nested), "--verse-cohort", str(nested_cohort)])
    rc2 = rr.main(["--out", str(out_flat), "--verse-cohort", str(flat_cohort)])

    assert rc1 == 0 and rc2 == 0
    summary_nested = _read_summary(out_nested)
    summary_flat = _read_summary(out_flat)

    case_ids_nested = summary_nested["cohort"]["case_ids"]
    case_ids_flat = summary_flat["cohort"]["case_ids"]
    assert case_ids_nested, "expected at least one discovered case"
    assert sorted(case_ids_nested) == case_ids_nested, "case_ids must be sorted"
    assert case_ids_nested == case_ids_flat
    assert summary_nested["cohort"]["mask_count"] == summary_flat["cohort"]["mask_count"] == 3


# =========================================================================== #
# AC5: staging produces ingest_cohort's flat convention
# =========================================================================== #


def test_ac5_staged_directory_is_flat_with_scan_siblings(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2, nested=True, with_scan=True)
    out = tmp_path / "out"
    staging_dir = tmp_path / "staged"

    rc = rr.main(
        ["--out", str(out), "--verse-cohort", str(cohort), "--staging-dir", str(staging_dir)]
    )
    assert rc == 0
    assert staging_dir.is_dir()

    staged_files = sorted(p for p in staging_dir.iterdir() if p.is_file())
    assert staged_files, "expected staged files"
    # Flat: no subdirectories under the staging dir.
    assert not any(p.is_dir() for p in staging_dir.iterdir())

    mask_names = {p.name for p in staged_files if p.name.endswith(_VERSE_SEG_SUFFIX)}
    assert mask_names == {f"sub-verse{i:03d}{_VERSE_SEG_SUFFIX}" for i in range(2)}
    for mask_name in mask_names:
        subject_id = mask_name[: -len(_VERSE_SEG_SUFFIX)]
        scan_name = f"{subject_id}_scan.nii.gz"
        assert (staging_dir / scan_name).is_file(), f"missing staged scan sibling for {subject_id}"


def test_ac5_subject_id_matches_ingest_cohorts_stem_rule(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=1, nested=True)
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["case_ids"] == ["sub-verse000"]


# =========================================================================== #
# AC6: staging never writes inside the cohort root
# =========================================================================== #


def test_ac6_cohort_root_paths_and_mtimes_unchanged_after_staged_run(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2, nested=True)
    before = _walk_tree(cohort)

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0

    after = _walk_tree(cohort)
    assert after == before, "the cohort root must be untouched by a staged run"


# =========================================================================== #
# AC7: the tool never writes the committed artifact
# =========================================================================== #


def test_ac7_committed_reference_verse_v1_is_untouched_by_a_run(tmp_path):
    committed_path = _REPO_ROOT / "src" / "segfacet" / "reference" / "reference_verse_v1.json"
    before = committed_path.read_bytes()

    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2)
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0

    after = committed_path.read_bytes()
    assert before == after

    written_artifact = out / "reference_verse_v1.json"
    assert written_artifact.is_file()


def test_ac7_no_written_path_resolves_under_src_segfacet(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2)
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0

    summary = _read_summary(out)
    src_segfacet = (_REPO_ROOT / "src" / "segfacet").resolve()

    def _walk_paths(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from _walk_paths(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from _walk_paths(v)

    for value in _walk_paths(summary):
        candidate = Path(value)
        if candidate.is_absolute() or (out / candidate).exists():
            resolved = candidate.resolve() if candidate.is_absolute() else (out / candidate).resolve()
            assert src_segfacet not in resolved.parents, f"wrote under src/segfacet: {resolved}"


# =========================================================================== #
# AC8: a subject whose CT is missing is recorded, never silently dropped
# =========================================================================== #


def test_ac8_subject_without_scan_recorded_and_still_staged(tmp_path):
    rr = _load_tool()
    cohort_root = tmp_path / "cohort"
    cohort_root.mkdir()
    _write_standin_subject(cohort_root, "sub-verse000", nested=True, with_scan=True)
    _write_standin_subject(cohort_root, "sub-verse001", nested=True, with_scan=False)

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort_root)])
    assert rc == 0

    summary = _read_summary(out)
    missing_entries = summary["staging"]["subjects_without_scan"]
    assert missing_entries, "expected sub-verse001 recorded as missing a scan"
    missing_ids = {entry["subject_id"] for entry in missing_entries}
    assert missing_ids == {"sub-verse001"}
    for entry in missing_entries:
        assert entry["reason"]

    # Still staged and still ingested: subject_count includes both subjects.
    assert summary["build"]["subject_count"] == 2

    staging_dir = Path(summary["staging"]["staged_dir"])
    assert (staging_dir / f"sub-verse001{_VERSE_SEG_SUFFIX}").is_file()


# =========================================================================== #
# AC9-AC11: derive_max_offset_mm -- pure, no cohort involved
# =========================================================================== #


def test_ac9_pure_function_deterministic_across_calls():
    rr = _load_tool()
    dist = _distribution({"L1": _level_dist("L1", p99=6.2, count=20)})
    first = rr.derive_max_offset_mm(dist)
    second = rr.derive_max_offset_mm(dist)
    assert first == second
    assert isinstance(first, float)


def test_ac10_returns_max_of_floor_and_rounded_up_p99():
    rr = _load_tool()
    # P = 6.2 at L1 (qualifying, count=20); smallest multiple of 0.5 strictly
    # greater than 6.2 is 6.5; max(6.0, 6.5) == 6.5.
    dist = _distribution(
        {
            "L1": _level_dist("L1", p99=6.2, count=20),
            "L2": _level_dist("L2", p99=3.0, count=20),
        }
    )
    assert rr.derive_max_offset_mm(dist) == pytest.approx(6.5)


def test_ac10_floor_wins_when_rounded_value_is_small():
    rr = _load_tool()
    # P = 2.0 -> rounded 2.5 -> floor 6.0 wins.
    dist = _distribution({"L1": _level_dist("L1", p99=2.0, count=20)})
    assert rr.derive_max_offset_mm(dist) == pytest.approx(6.0)


def test_ac10_low_count_level_with_huge_p99_is_ignored():
    rr = _load_tool()
    dist = _distribution(
        {
            "L1": _level_dist("L1", p99=2.0, count=20),
            "L6": _level_dist("L6", p99=999.0, count=3),  # count < 10 -- excluded
        }
    )
    assert rr.derive_max_offset_mm(dist) == pytest.approx(6.0)


def test_ac10_exactly_ten_count_qualifies():
    rr = _load_tool()
    dist = _distribution({"L1": _level_dist("L1", p99=10.0, count=10)})
    assert rr.derive_max_offset_mm(dist) == pytest.approx(10.5)


def test_ac11_every_level_below_ten_returns_floor():
    rr = _load_tool()
    dist = _distribution(
        {
            "L1": _level_dist("L1", p99=50.0, count=9),
            "L2": _level_dist("L2", p99=50.0, count=1),
        }
    )
    assert rr.derive_max_offset_mm(dist) == pytest.approx(6.0)


def test_ac11_no_spline_offset_stats_at_all_returns_floor_and_raises_nothing():
    rr = _load_tool()
    dist = _distribution(
        {
            "L1": _level_dist("L1", p99=50.0, count=20, no_spline_offset=True),
        }
    )
    assert rr.derive_max_offset_mm(dist) == pytest.approx(6.0)


def test_adv_p99_exactly_at_half_mm_multiple_rounds_up_strictly():
    """AC10's 'strictly greater' half: a p99 of exactly 6.5 must NOT return
    6.5 itself -- the next multiple, 7.0, is required."""
    rr = _load_tool()
    dist = _distribution({"L1": _level_dist("L1", p99=6.5, count=20)})
    assert rr.derive_max_offset_mm(dist) == pytest.approx(7.0)


# =========================================================================== #
# AC12-AC14: the recalibrated threshold's identity and window
# =========================================================================== #


def test_ac12_shipped_default_equals_derived_value_from_committed_artifact():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    rr = _load_tool()
    derived = rr.derive_max_offset_mm(bundled_production_reference())
    assert derived == _DEFAULT_MAX_OFFSET_MM


def test_ac13_config_yaml_agrees_with_code_default():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    cfg = load_config(default_config_path())
    assert cfg.rule_param("mislabel", "max_offset_mm", None) == _DEFAULT_MAX_OFFSET_MM


def test_ac13_default_is_no_longer_fifteen():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    assert _DEFAULT_MAX_OFFSET_MM != 15.0


def test_ac14_threshold_strictly_above_non_firing_ceiling():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    assert _DEFAULT_MAX_OFFSET_MM > 5.143859


def test_ac14_threshold_at_or_below_firing_floor():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    assert _DEFAULT_MAX_OFFSET_MM <= 17.507445


# =========================================================================== #
# AC15: the corpus's firing behaviour is unchanged by the recalibration
# =========================================================================== #


def _corpus_case(case_id):
    manifest = load_manifest()
    return next(c for c in manifest["cases"] if c["case_id"] == case_id)


def test_ac15_mode1_displace_fires_mislabel_naming_exactly_label_22():
    case = _corpus_case("mode1_displace")
    findings = [f for f in pipeline_findings(case) if f.rule_id == "mislabel"]
    assert findings
    union = set()
    for f in findings:
        union |= set(f.labels)
    assert union == {22}


def test_ac15_mode6_crop_at_border_fires_mislabel_and_border_on_label_22():
    case = _corpus_case("mode6_crop_at_border")
    findings = pipeline_findings(case)
    mislabel = [f for f in findings if f.rule_id == "mislabel"]
    border = [f for f in findings if f.rule_id == "border"]
    assert mislabel and any(22 in f.labels for f in mislabel)
    assert border and any(22 in f.labels for f in border)


def test_ac15_clean_control_fires_nothing_verdict_pass():
    case = _corpus_case("clean_control")
    assert pipeline_findings(case) == ()
    assert pipeline_verdict_label(case) == "pass"


def test_ac15_mode4_relabel_swap_fires_no_offset_misalignment_finding():
    """Narrowed 2026-08-31 (item 132): mode 4's swap now fires MislabelRule's
    ORDERING detector (Detector B, "Vertebra ordering inconsistent with
    label:") through plain run_qc, so the finding list is no longer empty --
    but Detector A's offset-MISALIGNMENT reason never fires on this case,
    which is what this recalibration test preserves."""
    case = _corpus_case("mode4_relabel_swap")
    findings = [f for f in pipeline_findings(case) if f.rule_id == "mislabel"]
    assert not any(
        f.reason.startswith("Vertebra misaligned from spinal curve:")
        for f in findings
    )


# =========================================================================== #
# AC16: the four calibration margins are recorded in mislabel.py's docstring
# =========================================================================== #


def test_ac16_docstring_records_the_margins_and_the_artifact_name():
    """Amended 2026-08-29: the docstring records the INTERIOR-only ceiling
    (2.510990 mm, mode4_relabel_swap) rather than the pre-amendment
    5.143859 mm (that reading is on mode4's cranial-terminal label 20, which
    AC39 removes from the detector's consideration entirely)."""
    import segfacet.heuristics.mislabel as mislabel_mod
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    doc = mislabel_mod.__doc__ or ""
    assert "reference_verse_v1.json" in doc
    for literal in ("2.510990", "17.507445", "18.718604"):
        assert literal in doc, f"expected margin {literal!r} recorded in the module docstring"
    assert f"{_DEFAULT_MAX_OFFSET_MM}" in doc or f"{_DEFAULT_MAX_OFFSET_MM:.1f}" in doc


def test_ac16_docstring_states_the_terminal_exclusion_and_why():
    import segfacet.heuristics.mislabel as mislabel_mod

    doc = (mislabel_mod.__doc__ or "").lower()
    assert "terminal" in doc
    assert "extrapolat" in doc, "expected the held-out-refit-extrapolation rationale recorded"


# =========================================================================== #
# AC17: the real-GT false-positive count is recorded in the summary
# =========================================================================== #


def test_ac17_calibration_block_shape_against_standin_cohort(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=3)
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0

    summary = _read_summary(out)
    calibration = summary["calibration"]
    assert "p99_by_level" in calibration
    assert isinstance(calibration["p99_by_level"], dict)
    assert "threshold" in calibration
    assert isinstance(calibration["threshold"], float)

    above = calibration["subject_levels_above_threshold"]
    assert "count" in above and "fraction" in above
    assert isinstance(above["count"], int)
    assert 0.0 <= above["fraction"] <= 1.0

    top_ids = calibration["top_subject_ids"]
    assert isinstance(top_ids, list)
    assert len(top_ids) <= 10


def test_ac17_calibration_block_reports_terminal_interior_split(tmp_path):
    """Amended 2026-08-29: the calibration block additionally reports
    terminal_count / interior_count (and per-population stats), so the
    evidence for excluding terminals is regenerable from the tool."""
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=3)
    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    assert rc == 0

    calibration = _read_summary(out)["calibration"]
    assert "terminal_count" in calibration
    assert "interior_count" in calibration
    assert isinstance(calibration["terminal_count"], int)
    assert isinstance(calibration["interior_count"], int)
    assert calibration["terminal_count"] >= 0
    assert calibration["interior_count"] >= 0
    # Every stand-in subject contributes exactly two terminal levels (its
    # cranial-most and caudal-most present level).
    assert calibration["terminal_count"] > 0


# =========================================================================== #
# AC18-AC20: reference_verse_v1.json
# =========================================================================== #


def test_ac18_every_qualifying_level_has_real_spread():
    dist = bundled_production_reference()
    max_mean = 0.0
    swept = False
    for level_name, strata in dist.levels.items():
        stats = strata.get(ALL_STRATUM)
        if stats is None:
            continue
        offset = stats.feature_stats.get("spline_offset_mm")
        if offset is None or offset.count < 10:
            continue
        swept = True
        assert offset.mean > 0.1, f"{level_name}: mean {offset.mean} mm is not real spread"
        max_mean = max(max_mean, offset.mean)
    assert swept, "expected at least one qualifying level"
    assert max_mean > 0.5


def test_ac19_artifact_identity_preserved():
    dist = load_artifact(bundled_production_reference_path())
    assert dist.schema_version == "1.2"
    assert dist.provenance.source == "verse-v1"
    assert dist.subject_count == 80
    assert "L6" in dist.levels
    assert "S" not in dist.levels

    # The level key set is pinned exactly: the real cohort's discovered
    # levels are unaffected by the estimator/threshold recalibration (only
    # spline_offset_mm's values move, never which levels were observed).
    expected_levels = frozenset(
        {f"C{i}" for i in range(1, 8)}
        | {f"T{i}" for i in range(1, 13)}
        | {f"L{i}" for i in range(1, 7)}
    )
    assert len(expected_levels) == 25
    assert set(dist.levels) == expected_levels

    expected_features = frozenset(
        {
            "component_count", "eigenvalue_ratio", "extent_x_mm", "extent_y_mm",
            "extent_z_mm", "intensity_entropy", "intensity_iqr", "intensity_max",
            "intensity_mean", "intensity_median", "intensity_min", "intensity_p05",
            "intensity_p25", "intensity_p50", "intensity_p75", "intensity_p95",
            "intensity_range", "intensity_std", "largest_component_fraction",
            "physical_volume_mm3", "spline_offset_mm",
        }
    )
    assert len(expected_features) == 21
    assert set(dist.features) == expected_features
    assert "spline_offset_mm" in dist.features


def test_ac20_config_hash_matches_current_config():
    dist = bundled_production_reference()
    assert dist.provenance.config_hash == config_hash(bundled_default_config())


# =========================================================================== #
# AC21-AC22: reference_default.json
# =========================================================================== #


def test_ac21_reference_default_matches_fresh_build_within_tolerance(tmp_path):
    """AC21: a fresh build matches the committed ``reference_default.json``
    within numeric tolerance, not byte-for-byte -- the committed artifact's
    float values differ from a freshly-computed one by ~1 ULP across numpy
    versions and platforms (item 078's ``reports_close`` convention; see
    CLAUDE.md "Note what the golden tests actually assert"). Same-session
    determinism (two fresh builds are byte-identical) is covered separately
    by test_ac21_two_fresh_builds_are_byte_identical below."""
    dest = tmp_path / "reference_default.json"
    build_and_write_default(dest)
    fresh = json.loads(dest.read_text(encoding="utf-8"))
    assert_matches_committed_artifact(fresh, default_artifact_path())


def test_ac21_two_fresh_builds_are_byte_identical(tmp_path):
    dest_a = tmp_path / "a.json"
    dest_b = tmp_path / "b.json"
    build_and_write_default(dest_a)
    build_and_write_default(dest_b)
    assert dest_a.read_bytes() == dest_b.read_bytes()


def test_ac21_config_hash_matches_ac20s():
    dist = bundled_default_reference()
    assert dist.provenance.config_hash == config_hash(bundled_default_config())


def test_ac22_default_artifact_keeps_synthetic_role():
    dist = bundled_default_reference()
    assert dist.provenance.source == "synthetic-verse-cohort"
    assert set(dist.levels) == {"L1", "L2", "L3", "L4", "L5"}


# =========================================================================== #
# AC23-AC24: the goldens agree with a fresh build and are reproducible
# =========================================================================== #


# (item 126: test_ac23_every_manifest_case_matches_committed_golden was
# discharged -- its subject, the committed golden corpus, was retired. See
# docs/aide/golden-decision-table.md's "## Retirement execution log".)


def test_ac24_write_goldens_into_two_dirs_is_byte_identical(tmp_path):
    dest1 = tmp_path / "dest1"
    dest2 = tmp_path / "dest2"
    write_goldens(dest1)
    write_goldens(dest2)

    manifest = load_manifest()
    for case in manifest["cases"]:
        name = f"{case['case_id']}.json"
        assert (dest1 / name).read_bytes() == (dest2 / name).read_bytes()


# =========================================================================== #
# AC25-AC26: every golden gains is_terminal; the two firing goldens also move
# the threshold clause (amended 2026-08-29 -- all nine goldens now change,
# replacing the pre-amendment "seven are byte-unchanged").
# =========================================================================== #

_THRESHOLD_CARRYING_CASES = frozenset({"mode1_displace", "mode6_crop_at_border"})


def _all_offset_entries(golden: dict) -> list:
    return golden.get("features", {}).get("stage3", {}).get("per_label_offsets", [])


# (item 126: test_ac25_seven_non_mislabel_goldens_gain_only_is_terminal and
# test_ac26_two_changed_goldens_move_only_is_terminal_and_the_threshold_clause
# were discharged -- both were pre/post-123 fences comparing the committed
# golden corpus's state before and after item 123 landed; item 123 has
# already landed, and the committed golden corpus both fences read (via
# git history and/or the live tree) was retired by this item. See
# docs/aide/golden-decision-table.md's "## Retirement execution log".)


# =========================================================================== #
# AC27: the Stage-3 report golden is regenerated (amended 2026-08-29 --
# replaces the pre-amendment "byte-unchanged": AC37's key reaches it too)
# =========================================================================== #


# (item 126: test_ac27_stage3_report_golden_matches_test_022_output and
# test_ac27_stage3_report_golden_offset_entries_carry_is_terminal were
# discharged -- both compared their own _straight_spine(5)-derived content
# against t022.GOLDEN_PATH, which now names the shared, feature-value-free
# tests/golden/report_format_contract.json (item 126 replacement iv),
# content unrelated to either test's input. See
# docs/aide/golden-decision-table.md's "## Retirement execution log" and
# this item's Decisions & Trade-offs log.)


# =========================================================================== #
# AC28: the pinned finding snapshot tracks the new threshold
# =========================================================================== #


def test_ac28_pinned_snapshot_reasons_name_the_current_threshold():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM
    from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS

    clause = f"(threshold {_DEFAULT_MAX_OFFSET_MM:.1f} mm)"
    mode1_reason = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode1_displace"]["findings"][0]["reason"]
    mode6_findings = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode6_crop_at_border"]["findings"]
    mode6_reason = next(f["reason"] for f in mode6_findings if f["rule_id"] == "mislabel")

    assert clause in mode1_reason
    assert clause in mode6_reason


def test_ac28_pinned_snapshot_reasons_equal_committed_golden_reasons():
    """AC28 (item 126 replacement): re-pointed at fresh output; the
    committed golden this used to read was retired, see
    docs/aide/golden-decision-table.md's "## Retirement execution log"."""
    from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS

    manifest = load_manifest()
    cases_by_id = {c["case_id"]: c for c in manifest["cases"]}

    mode1_expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode1_displace"]["findings"][0]["reason"]
    mode1_report = build_report_for_case(cases_by_id["mode1_displace"])
    mode1_actual = next(f["reason"] for f in mode1_report["findings"] if f["rule_id"] == "mislabel")
    assert mode1_actual == mode1_expected

    mode6_expected = next(
        f["reason"] for f in _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode6_crop_at_border"]["findings"]
        if f["rule_id"] == "mislabel"
    )
    mode6_report = build_report_for_case(cases_by_id["mode6_crop_at_border"])
    mode6_actual = next(f["reason"] for f in mode6_report["findings"] if f["rule_id"] == "mislabel")
    assert mode6_actual == mode6_expected


# =========================================================================== #
# AC29-AC32: configuration and documentation
# =========================================================================== #


def test_ac29_gitignore_pins_dataset_line_without_trailing_slash_and_explains_why():
    text = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = text.splitlines()
    matching = [ln for ln in lines if ln.strip() == "dataset-verse19training"]
    assert matching, ".gitignore must contain a bare 'dataset-verse19training' line"
    assert not any("dataset-verse19training/" in ln for ln in lines)
    # A nearby comment explains the absent trailing slash.
    idx = lines.index(matching[0])
    context = "\n".join(lines[max(0, idx - 6): idx])
    assert "slash" in context.lower()


def test_ac30_dataset_verse19_doc_names_env_var_and_recursive_discovery():
    text = (_REPO_ROOT / "docs" / "aide" / "dataset-verse19.md").read_text(encoding="utf-8")
    assert "dataset-verse19training/dataset-verse19training/" not in text
    assert "SEGFACET_VERSE_COHORT" in text
    assert "recursive" in text.lower() or "rglob" in text.lower()


def test_ac31_reference_build_doc_names_the_tool_and_resolution_order():
    text = (_REPO_ROOT / "docs" / "reference-build.md").read_text(encoding="utf-8")
    assert "scripts/rebuild_verse_reference.py" in text
    assert "SEGFACET_VERSE_COHORT" in text
    assert "--verse-cohort" in text
    assert "dataset-verse19training/dataset-verse19training/" not in text


def test_ac32_reference_build_doc_records_the_rebuild():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    text = (_REPO_ROOT / "docs" / "reference-build.md").read_text(encoding="utf-8")
    assert "80" in text
    threshold_str_options = (str(_DEFAULT_MAX_OFFSET_MM), f"{_DEFAULT_MAX_OFFSET_MM:.1f}")
    assert any(opt in text for opt in threshold_str_options)
    # A dated entry: a 2026- date stamp somewhere near the rebuild record.
    assert "2026-" in text


# =========================================================================== #
# AC33-AC34: stale pins reconciled
# =========================================================================== #


def test_ac33_reference_verse_v1_digest_fence_matches_committed_file():
    from test_128_reference_verse_v1_integrity import (
        _RELEASED_REFERENCE_VERSE_V1_SHA256,
    )

    digest = hashlib.sha256(bundled_production_reference_path().read_bytes()).hexdigest()
    assert digest == _RELEASED_REFERENCE_VERSE_V1_SHA256


def test_ac34_retired_test_names_absent_from_test_120_source():
    source = (_REPO_ROOT / "tests" / "test_120_leave_one_out_offset.py").read_text(encoding="utf-8")
    assert "test_ac29_reference_verse_v1_unchanged" not in source
    assert "test_ac16_default_max_offset_mm_still_15" not in source


def test_ac50_test120_field_set_includes_is_terminal():
    """AC50's actual assertion lives in test_120 (the module that owns the
    field-set test); this pins that the reconciliation landed there."""
    source = (_REPO_ROOT / "tests" / "test_120_leave_one_out_offset.py").read_text(encoding="utf-8")
    assert "is_terminal" in source


# =========================================================================== #
# Terminal-vertebra exclusion (added 2026-08-29 by human decision): AC35-AC51
# =========================================================================== #


def _straight_spine_centroids(n: int, spacing_mm: float = 10.0):
    from segfacet.features.centroids import LabelCentroid

    levels = ["T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    return [
        LabelCentroid(
            label=i + 1,
            level_name=levels[i % len(levels)],
            centroid_voxel=(0.0, 0.0, 0.0),
            centroid_mm=(0.0, 0.0, float(i) * spacing_mm),
        )
        for i in range(n)
    ]


def _write_mislabel_config(tmp_path, max_offset_mm: float):
    from segfacet.config import SUPPORTED_SCHEMA_VERSION, load_config

    content = (
        f"schema_version: '{SUPPORTED_SCHEMA_VERSION}'\n"
        "rules:\n  mislabel:\n    params:\n"
        f"      max_offset_mm: {max_offset_mm}\n"
    )
    path = tmp_path / "mislabel_config.yaml"
    path.write_text(content, encoding="utf-8")
    return load_config(path)


def _offset_entry(label, level_name, offset_mm, is_terminal=None):
    entry = {
        "label": label, "level_name": level_name, "closest_u": 0.5,
        "offset_mm": offset_mm, "offset_voxel": offset_mm,
        "dx_mm": offset_mm, "dy_mm": 0.0, "dz_mm": 0.0,
    }
    if is_terminal is not None:
        entry["is_terminal"] = is_terminal
    return entry


def _mislabel_record(entries):
    return {
        "stage3": {
            "per_label_offsets": list(entries),
            "monotonic_consistency": {"is_monotonic": True, "non_monotonic_pairs": [], "u_values": []},
        },
    }


def _mislabel_findings(findings):
    return [f for f in findings if f.rule_id == "mislabel"]


# --- AC35: the field exists, defaults False, dataclass stays frozen ------- #


def test_ac35_is_terminal_field_exists_and_defaults_false():
    import dataclasses

    from segfacet.features.spline_offset import VertebralSplineOffset

    fields = {f.name: f for f in dataclasses.fields(VertebralSplineOffset)}
    assert "is_terminal" in fields
    assert fields["is_terminal"].default is False


def test_ac35_vertebralsplineoffset_still_frozen():
    import dataclasses

    from segfacet.features.spline_offset import VertebralSplineOffset

    centroids = _straight_spine_centroids(5)
    fit = fit_centroid_spline(centroids)
    record = compute_spline_offsets(centroids, fit)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.is_terminal = True  # type: ignore[misc]


# --- AC36: first/last True, interior False, both compute functions ------- #


@pytest.mark.parametrize("compute", ["in_sample", "held_out"])
def test_ac36_first_and_last_are_terminal_interior_is_not(compute):
    centroids = _straight_spine_centroids(5)
    if compute == "in_sample":
        fit = fit_centroid_spline(centroids)
        records = compute_spline_offsets(centroids, fit)
    else:
        records = compute_leave_one_out_spline_offsets(centroids)

    assert records[0].is_terminal is True
    assert records[-1].is_terminal is True
    for r in records[1:-1]:
        assert r.is_terminal is False


# --- AC37: a sequence of one or two centroids is entirely terminal ------- #


@pytest.mark.parametrize("n", [1, 2])
def test_ac37_short_sequence_is_entirely_terminal(n):
    centroids = _straight_spine_centroids(n)
    fit = fit_centroid_spline(centroids) if n >= 2 else None
    records = (
        compute_spline_offsets(centroids, fit) if fit is not None
        else compute_leave_one_out_spline_offsets(centroids)
    )
    assert len(records) == n
    for r in records:
        assert r.is_terminal is True


# --- AC38: terminality is sequence-relative, matched by label ------------ #


def test_ac38_reversal_invariance_matches_by_label_not_index():
    centroids = _straight_spine_centroids(6)
    forward = compute_leave_one_out_spline_offsets(centroids)
    forward_terminal_labels = {r.label for r in forward if r.is_terminal}

    reversed_centroids = list(reversed(centroids))
    backward = compute_leave_one_out_spline_offsets(reversed_centroids)
    backward_terminal_labels = {r.label for r in backward if r.is_terminal}

    assert forward_terminal_labels == {centroids[0].label, centroids[-1].label}
    assert backward_terminal_labels == forward_terminal_labels


# --- AC39/AC40: MislabelRule excludes terminal entries, interior fires --- #


def test_ac39_terminal_entry_never_fires_even_at_forty_mm_over_a_thirteen_mm_threshold(tmp_path):
    cfg = _write_mislabel_config(tmp_path, max_offset_mm=13.0)
    entry = _offset_entry(20, "L1", offset_mm=40.0, is_terminal=True)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), cfg))
    assert findings == []


def test_ac39_interior_entry_over_threshold_still_fires_alongside_a_terminal_one(tmp_path):
    cfg = _write_mislabel_config(tmp_path, max_offset_mm=13.0)
    terminal_entry = _offset_entry(20, "L1", offset_mm=40.0, is_terminal=True)
    interior_entry = _offset_entry(21, "L2", offset_mm=20.0, is_terminal=False)
    findings = _mislabel_findings(run_rules(_mislabel_record([terminal_entry, interior_entry]), cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({21})


def test_ac40_none_is_terminal_value_still_fires(tmp_path):
    cfg = _write_mislabel_config(tmp_path, max_offset_mm=13.0)
    entry = _offset_entry(20, "L1", offset_mm=41.3, is_terminal=None)
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({20})


def test_ac40_absent_is_terminal_key_still_fires(tmp_path):
    cfg = _write_mislabel_config(tmp_path, max_offset_mm=13.0)
    entry = _offset_entry(20, "L1", offset_mm=41.3)  # key omitted entirely
    assert "is_terminal" not in entry
    findings = _mislabel_findings(run_rules(_mislabel_record([entry]), cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({20})


def test_ac40_test033_positional_terminal_fixtures_still_fire_unmodified():
    """AC40 exists precisely so test_033_mislabel.py needs no edit. Rather
    than re-declaring its ~20 cases here, drive its own boundary fixture
    directly through the shipped rule and confirm it still fires -- this
    fixture's offending entry sits at list index 0, which is exactly the
    positional shape AC40 must not treat as terminal."""
    import test_033_mislabel as t033

    offsets = [t033._make_offset_entry(t033._LABEL_L1, 41.3, "L1")]
    record = t033._make_record(offsets, [])
    findings = _mislabel_findings(run_rules(record, t033.default_config()))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({t033._LABEL_L1})


# --- AC41/AC42: symmetric ingest/delta exclusion -------------------------- #


def _tiny_standin_ingest_cohort(tmp_path, n=2):
    """A tiny cohort in ingest_cohort's own convention (item 044's
    '_seg.nii.gz' suffix) -- never the real-VerSe naming this module's
    rebuild-tool tests use elsewhere."""
    cohort_dir = tmp_path / "ingest_cohort"
    cohort_dir.mkdir()
    for i in range(n):
        spine = build_clean_spine(
            levels=("L1", "L2", "L3", "L4", "L5"), spacing=(1.0, 1.0, 1.0 + 0.1 * i),
            curve_amplitude_mm=4.0 + i,
        )
        nib.save(spine.seg_img, str(cohort_dir / f"subject{i}_seg.nii.gz"))
    return cohort_dir


def test_ac41_ingest_excludes_terminal_offsets_from_count(tmp_path):
    from segfacet.reference.ingest import ingest_cohort

    cohort_dir = _tiny_standin_ingest_cohort(tmp_path, n=2)
    ingested = ingest_cohort(cohort_dir, with_size_proxy=False)

    interior_occurrences = 0
    total_occurrences = 0
    for record in ingested.records:
        total_occurrences += 1
        if "spline_offset_mm" in record.features:
            interior_occurrences += 1
    assert total_occurrences > 0
    # Every subject here has 5 levels (L1-L5): 2 terminal + 3 interior each,
    # so strictly fewer occurrences carry spline_offset_mm than total.
    assert 0 < interior_occurrences < total_occurrences


def test_ac42_delta_excludes_terminal_labels_symmetrically():
    from segfacet.reference.delta import compute_reference_delta

    spine = build_clean_spine(levels=("L1", "L2", "L3", "L4", "L5"))
    config = bundled_default_config()
    block = extract_feature_record(spine.seg_img, config)

    # Identify the terminal labels from the block's own per_label_offsets.
    offsets = block["stage3"]["per_label_offsets"]
    terminal_labels = {o["label"] for o in offsets if o.get("is_terminal")}
    interior_labels = {o["label"] for o in offsets if not o.get("is_terminal")}
    assert terminal_labels, "expected at least one terminal label"
    assert interior_labels, "expected at least one interior label"

    delta = compute_reference_delta(block, bundled_production_reference())
    for label in terminal_labels:
        label_delta = delta.per_label.get(label)
        if label_delta is None:
            continue
        assert not any(fd.feature == "spline_offset_mm" for fd in label_delta.features)


# --- AC43: the committed artifact is interior-only, anomaly gone --------- #


def test_ac43_l5_below_qualifying_count_or_absent():
    dist = bundled_production_reference()
    l5 = dist.levels.get("L5", {}).get(ALL_STRATUM)
    if l5 is None:
        return
    offset = l5.feature_stats.get("spline_offset_mm")
    if offset is None:
        return
    assert offset.count < 10


def test_ac43_no_qualifying_level_p99_exceeds_thirteen():
    dist = bundled_production_reference()
    for strata in dist.levels.values():
        stats = strata.get(ALL_STRATUM)
        if stats is None:
            continue
        offset = stats.feature_stats.get("spline_offset_mm")
        if offset is None or offset.count < 10:
            continue
        p99 = offset.percentiles.get("p99")
        assert p99 is not None
        assert p99 <= 13.0, f"qualifying level p99 {p99} exceeds 13.0 mm"


def test_ac43_level_with_no_interior_occurrence_still_loads():
    # A structural round-trip: the artifact loads regardless of which levels
    # carry spline_offset_mm.
    dist = load_artifact(bundled_production_reference_path())
    assert dist.schema_version == "1.2"


# --- AC44/AC45: the human-agreed threshold and the interior ceiling ------ #


def test_ac44_default_max_offset_mm_is_thirteen():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    assert _DEFAULT_MAX_OFFSET_MM == 13.0


def _interior_offset_ceiling_over_corpus(exclude_case_ids=frozenset()):
    """Item 126 re-pointed this helper at fresh output; the committed golden
    it used to read was retired, see docs/aide/golden-decision-table.md's
    "## Retirement execution log"."""
    manifest = load_manifest()
    ceiling = 0.0
    for case in manifest["cases"]:
        if case["case_id"] in exclude_case_ids:
            continue
        report = build_report_for_case(case)
        entries = _all_offset_entries(report)
        for entry in entries[1:-1] if len(entries) > 2 else []:
            ceiling = max(ceiling, entry["offset_mm"])
    return ceiling


def test_ac45_interior_corpus_ceiling_is_2_510990():
    ceiling = _interior_offset_ceiling_over_corpus(exclude_case_ids=_THRESHOLD_CARRYING_CASES)
    assert ceiling == pytest.approx(2.510990, abs=1e-6)


def test_ac45_threshold_exceeds_the_interior_ceiling():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    ceiling = _interior_offset_ceiling_over_corpus(exclude_case_ids=_THRESHOLD_CARRYING_CASES)
    assert _DEFAULT_MAX_OFFSET_MM > ceiling


# --- AC46: FEATURE_DOCS documents the new leaf and its rationale --------- #


def test_ac46_feature_docs_entry_exists_with_rationale():
    from segfacet.feature_docs import FEATURE_DOCS

    key = "stage3.per_label_offsets[].is_terminal"
    assert key in FEATURE_DOCS
    doc = FEATURE_DOCS[key]
    text = " ".join(str(v) for v in vars(doc).values()).lower()
    assert "first" in text and "last" in text
    assert "mislabel" in text
    assert "extrapolat" in text or "refit" in text


# --- AC47: the generated catalogue regenerates drift-clean --------------- #


def test_ac47_catalogue_regenerates_byte_identical_and_contains_new_path(tmp_path):
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])

    committed_json = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"
    committed_md = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.md"
    assert json_dest.read_bytes() == committed_json.read_bytes()
    assert md_dest.read_bytes() == committed_md.read_bytes()

    record = json.loads(json_dest.read_text(encoding="utf-8"))
    paths = {entry["path"] for group in record["groups"] for entry in group["entries"]}
    assert "stage3.per_label_offsets[].is_terminal" in paths


# --- AC48: the leaf-count constants match the regenerated catalogue ------ #


def test_ac48_test103_leaf_count_constant_is_94():
    source = (_REPO_ROOT / "tests" / "test_103_feature_catalogue.py").read_text(encoding="utf-8")
    assert "94" in source


# --- AC49: the pre-119 leaf-path digest is bumped alongside the catalogue #


def test_ac49_pre_119_digest_matches_the_live_catalogue_leaf_path_set(tmp_path):
    """Reads (never recomputes/hardcodes) the committed digest fixture and
    compares it to a fresh catalogue run's own leaf-path-set digest -- this
    is expected to fail until the builder regenerates the catalogue AND
    bumps the fixture together (step 9), mirroring how AC33's sha256 fence
    is left to the builder rather than pre-guessed here."""
    import segfacet.catalogue as catalogue

    json_dest = tmp_path / "feature_catalogue.generated.json"
    md_dest = tmp_path / "feature_catalogue.generated.md"
    catalogue.main(["--json", str(json_dest), "--md", str(md_dest)])
    record = json.loads(json_dest.read_text(encoding="utf-8"))
    paths = sorted(entry["path"] for group in record["groups"] for entry in group["entries"])
    live_digest = hashlib.sha256("\n".join(paths).encode("utf-8")).hexdigest()

    fixture = json.loads(
        (_REPO_ROOT / "tests" / "corpus" / "119_pre_119_digests.json").read_text(encoding="utf-8")
    )
    assert fixture["catalogue_leaf_path_set_sha256"] == live_digest


# --- AC51: the schema admits is_terminal as optional --------------------- #


def _stage3_offset_entry_schema():
    import importlib.resources
    import segfacet as _segfacet_pkg

    ref = importlib.resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    schema = json.loads(ref.read_text(encoding="utf-8"))
    return schema["definitions"]["stage3OffsetEntry"]


def _well_formed_offset_entry_instance() -> dict:
    return {
        "label": 20, "level_name": "L1", "closest_u": 0.5,
        "offset_mm": 1.0, "offset_voxel": 1.0, "dx_mm": 1.0, "dy_mm": 0.0, "dz_mm": 0.0,
    }


def test_ac51_is_terminal_is_a_boolean_property_not_required():
    schema = _stage3_offset_entry_schema()
    assert schema["properties"]["is_terminal"]["type"] == "boolean"
    assert "is_terminal" not in schema.get("required", [])


def test_ac51_entry_with_is_terminal_validates():
    import jsonschema

    instance = _well_formed_offset_entry_instance()
    instance["is_terminal"] = True
    jsonschema.validate(instance, _stage3_offset_entry_schema())


def test_ac51_entry_without_is_terminal_still_validates():
    import jsonschema

    jsonschema.validate(_well_formed_offset_entry_instance(), _stage3_offset_entry_schema())


def test_ac51_misspelt_variant_key_fails_validation():
    import jsonschema

    instance = _well_formed_offset_entry_instance()
    instance["is_termnial"] = True  # deliberate misspelling
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, _stage3_offset_entry_schema())


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


def test_adv_terminal_entry_with_astronomically_large_offset_never_fires(tmp_path):
    """Magnitude is never the discriminator: a 1e6 mm terminal reading fires
    nothing, while a modest interior entry over threshold in the same record
    still fires."""
    cfg = _write_mislabel_config(tmp_path, max_offset_mm=13.0)
    huge_terminal = _offset_entry(20, "L1", offset_mm=1.0e6, is_terminal=True)
    modest_interior = _offset_entry(21, "L2", offset_mm=13.5, is_terminal=False)
    findings = _mislabel_findings(run_rules(_mislabel_record([huge_terminal, modest_interior]), cfg))
    assert len(findings) == 1
    assert findings[0].labels == frozenset({21})


def test_adv_all_terminal_two_centroid_sequence_has_no_interior_at_all():
    """n<=2: every returned record is terminal -- there is no interior
    population for either compute path to disagree about."""
    centroids = _straight_spine_centroids(2)
    fit = fit_centroid_spline(centroids)
    in_sample = compute_spline_offsets(centroids, fit)
    held_out = compute_leave_one_out_spline_offsets(centroids)
    for records in (in_sample, held_out):
        assert len(records) == 2
        assert all(r.is_terminal for r in records)
        assert not any(not r.is_terminal for r in records)


def test_adv_symlinked_cohort_root_is_discovered(tmp_path):
    rr = _load_tool()
    real_cohort = _build_standin_cohort(tmp_path / "real-cohort", n=2)
    link = tmp_path / "cohort-link"
    try:
        link.symlink_to(real_cohort, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("platform does not support symlinks without elevation")

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(link)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "ran"
    assert summary["cohort"]["mask_count"] == 2


def test_adv_subject_id_collision_after_suffix_stripping_is_recorded_not_overwritten(tmp_path):
    """Two distinct mask files that strip to the same subject_id (one nested
    under wrapper/, one flat) must not silently clobber one another in the
    staging directory."""
    rr = _load_tool()
    cohort_root = tmp_path / "cohort"
    cohort_root.mkdir()
    _write_standin_subject(cohort_root, "sub-verse000", nested=True)
    # A second, distinct mask that collides on subject_id after suffix
    # stripping, placed at a different nested path.
    dup_dir = cohort_root / "wrapper" / "derivatives" / "sub-verse000" / "dup"
    dup_dir.mkdir(parents=True)
    spine = build_clean_spine(levels=("L1", "L2", "L3"), curve_amplitude_mm=1.0)
    nib.save(spine.seg_img, str(dup_dir / f"sub-verse000{_VERSE_SEG_SUFFIX}"))

    out = tmp_path / "out"
    import contextlib
    import io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort_root)])

    assert rc == 0
    assert _no_traceback(buf.getvalue())
    summary = _read_summary(out)
    # Either both masks are discovered (two distinct staged names) or the
    # collision is explicitly recorded -- either way, exactly one silent
    # overwrite (mask_count == 1 with no record) is the failure this pins.
    if summary["cohort"]["mask_count"] == 1:
        assert summary["cohort"].get("collisions") or summary["staging"].get("collisions"), (
            "a subject_id collision after suffix stripping must be recorded, not silently dropped"
        )


def test_adv_single_label_mask_does_not_crash(tmp_path):
    rr = _load_tool()
    cohort_root = tmp_path / "cohort"
    cohort_root.mkdir()
    spine = build_clean_spine(levels=("L3",), curve_amplitude_mm=0.0)
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    nib.save(spine.seg_img, str(cohort_root / f"sub-verse000{_VERSE_SEG_SUFFIX}"))
    nib.save(scan_img, str(cohort_root / "sub-verse000_ct.nii.gz"))

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort_root)])
    assert rc == 0
    summary = _read_summary(out)
    assert summary["build"]["subject_count"] == 1


def test_adv_exactly_four_level_mask_yields_zero_offsets_not_a_crash(tmp_path):
    """Item 120's held-out estimator at its fallback boundary: with exactly
    four levels, k = min(3, n-1) = 3 leaves the smoothing term no freedom, so
    every held-out offset_mm reads 0.0. Pinned here so a future estimator
    change is visible (not fixed by this item)."""
    rr = _load_tool()
    cohort_root = tmp_path / "cohort"
    cohort_root.mkdir()
    spine = build_clean_spine(levels=("L1", "L2", "L3", "L4"), curve_amplitude_mm=6.0)
    scan_img = paint_clean_scan(spine.seg_img, seed=0)
    nib.save(spine.seg_img, str(cohort_root / f"sub-verse000{_VERSE_SEG_SUFFIX}"))
    nib.save(scan_img, str(cohort_root / "sub-verse000_ct.nii.gz"))

    out = tmp_path / "out"
    rc = rr.main(["--out", str(out), "--verse-cohort", str(cohort_root)])
    assert rc == 0

    artifact_path = out / "reference_verse_v1.json"
    dist = load_artifact(artifact_path)
    swept = False
    for strata in dist.levels.values():
        stats = strata.get(ALL_STRATUM)
        if stats is None:
            continue
        offset = stats.feature_stats.get("spline_offset_mm")
        if offset is None:
            continue
        swept = True
        assert offset.mean == pytest.approx(0.0, abs=1e-9)
    assert swept, "expected at least one level's spline_offset_mm in the four-level build"


def test_adv_rerun_into_same_out_overwrites_cleanly(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=2)
    out = tmp_path / "out"

    rc1 = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    summary1 = _read_summary(out)
    rc2 = rr.main(["--out", str(out), "--verse-cohort", str(cohort)])
    summary2 = _read_summary(out)

    assert rc1 == 0 and rc2 == 0
    assert summary1["cohort"]["case_ids"] == summary2["cohort"]["case_ids"]
    assert summary1["calibration"]["threshold"] == summary2["calibration"]["threshold"]


def test_adv_out_dir_under_not_yet_existing_nested_parent_is_created(tmp_path):
    rr = _load_tool()
    out = tmp_path / "brand_new" / "nested" / "out"
    assert not out.parent.exists()

    rc = rr.main(["--out", str(out)])

    assert rc == 0
    assert out.is_dir()
    assert (out / "verse_rebuild_summary.json").is_file()


def test_adv_empty_string_env_var_treated_as_unset(tmp_path, monkeypatch):
    rr = _load_tool()
    monkeypatch.setenv(_ENV_VAR, "")
    out = tmp_path / "out"

    rc = rr.main(["--out", str(out)])

    assert rc == 0
    summary = _read_summary(out)
    assert summary["cohort"]["status"] == "skipped"


def test_adv_env_var_restored_after_monkeypatch_teardown(monkeypatch):
    """Env hygiene, mirroring tests 084/091: monkeypatch's teardown must
    leave SEGFACET_VERSE_COHORT exactly as it found it (unset, since the
    autouse fixture clears it) once this test function returns."""
    monkeypatch.setenv(_ENV_VAR, "/some/probe/value")
    import os

    assert os.environ.get(_ENV_VAR) == "/some/probe/value"
    # monkeypatch's own teardown (invoked after this test returns) restores
    # the prior (cleared, via the autouse fixture) state -- nothing further
    # to do here; this test documents and exercises that the setenv call
    # itself does not leak past this function via any other mechanism.


def test_adv_two_standin_runs_produce_equal_cohort_and_calibration_blocks(tmp_path):
    rr = _load_tool()
    cohort = _build_standin_cohort(tmp_path / "cohort", n=3)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"

    rr.main(["--out", str(out_a), "--verse-cohort", str(cohort)])
    rr.main(["--out", str(out_b), "--verse-cohort", str(cohort)])

    summary_a = _read_summary(out_a)
    summary_b = _read_summary(out_b)
    assert summary_a["cohort"] == summary_b["cohort"]
    assert summary_a["calibration"] == summary_b["calibration"]
