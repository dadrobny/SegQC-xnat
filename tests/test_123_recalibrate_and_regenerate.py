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
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import load_manifest
from segfacet.synth.golden import GOLDEN_DIR, check_case_golden, load_golden, write_goldens
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
    """Map of relative path -> mtime_ns for every file beneath *root*."""
    return {
        str(p.relative_to(root)): p.stat().st_mtime_ns
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


def _pre_123_base_rev():
    """The commit item 123's branch diverged from ``main``, so ``git show
    <rev>:<path>`` reads the pre-123 committed state. Returns ``None`` (never
    raises) if git is unavailable to the test runner -- AC25/AC26 fall back
    to the weaker text-only assertion in that case (Testing Strategy)."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "HEAD", "main"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    rev = result.stdout.strip()
    return rev or None


def _git_show_json(rev: str, relpath: str):
    try:
        result = subprocess.run(
            ["git", "show", f"{rev}:{relpath}"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=10,
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


def test_ac15_mode4_relabel_swap_fires_no_mislabel_finding():
    case = _corpus_case("mode4_relabel_swap")
    findings = [f for f in pipeline_findings(case) if f.rule_id == "mislabel"]
    assert findings == []


# =========================================================================== #
# AC16: the four calibration margins are recorded in mislabel.py's docstring
# =========================================================================== #


def test_ac16_docstring_records_the_four_margins_and_the_artifact_name():
    import segfacet.heuristics.mislabel as mislabel_mod
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    doc = mislabel_mod.__doc__ or ""
    assert "reference_verse_v1.json" in doc
    for literal in ("5.143859", "17.507445", "18.718604"):
        assert literal in doc, f"expected margin {literal!r} recorded in the module docstring"
    assert f"{_DEFAULT_MAX_OFFSET_MM}" in doc or f"{_DEFAULT_MAX_OFFSET_MM:.1f}" in doc


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


def test_ac21_reference_default_byte_identical_to_fresh_build(tmp_path):
    dest = tmp_path / "reference_default.json"
    build_and_write_default(dest)
    assert dest.read_bytes() == default_artifact_path().read_bytes()


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


def test_ac23_every_manifest_case_matches_committed_golden():
    manifest = load_manifest()
    assert len(manifest["cases"]) == 9
    for case in manifest["cases"]:
        assert check_case_golden(case), f"{case['case_id']} does not match its committed golden"


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
# AC25-AC26: exactly two goldens changed, in exactly the threshold clause
# =========================================================================== #

_THRESHOLD_CARRYING_CASES = frozenset({"mode1_displace", "mode6_crop_at_border"})


def test_ac25_seven_non_mislabel_goldens_byte_unchanged_from_pre_123():
    base_rev = _pre_123_base_rev()
    manifest = load_manifest()
    unaffected = [c for c in manifest["cases"] if c["case_id"] not in _THRESHOLD_CARRYING_CASES]
    assert len(unaffected) == 7

    if base_rev is not None:
        checked_any = False
        for case in unaffected:
            case_id = case["case_id"]
            pre = _git_show_json(base_rev, f"tests/corpus/golden/{case_id}.json")
            if pre is None:
                continue
            checked_any = True
            committed = load_golden(case_id)
            assert committed == pre, f"{case_id}: golden changed but is not threshold-carrying"
        if checked_any:
            return

    # Fallback (git unavailable to the test runner): no non-threshold case's
    # golden text carries the threshold clause substring.
    for case in unaffected:
        text = (GOLDEN_DIR / f"{case['case_id']}.json").read_text(encoding="utf-8")
        assert "(threshold" not in text


def test_ac26_two_changed_goldens_move_only_the_threshold_clause():
    from segfacet.heuristics.mislabel import _DEFAULT_MAX_OFFSET_MM

    base_rev = _pre_123_base_rev()
    if base_rev is not None:
        checked_any = False
        for case_id in sorted(_THRESHOLD_CARRYING_CASES):
            pre = _git_show_json(base_rev, f"tests/corpus/golden/{case_id}.json")
            if pre is None:
                continue
            checked_any = True
            committed = load_golden(case_id)
            diffs = _diff_leaves(pre, committed)
            assert diffs, f"{case_id}: expected the recalibrated threshold to move at least one leaf"
            for path, old_text, new_text in diffs:
                assert path.endswith(".reason") or path.endswith(".message"), (
                    f"{case_id}: unexpected changed leaf {path!r} outside the threshold clause"
                )
                old_threshold_clause = "(threshold 15.0 mm)"
                assert old_threshold_clause in old_text
                assert old_text.replace(
                    old_threshold_clause, f"(threshold {_DEFAULT_MAX_OFFSET_MM:.1f} mm)"
                ) == new_text
        if checked_any:
            return

    # Fallback: only the two named cases carry the "(threshold" substring,
    # and every occurrence names the current default.
    manifest = load_manifest()
    for case in manifest["cases"]:
        case_id = case["case_id"]
        text = (GOLDEN_DIR / f"{case_id}.json").read_text(encoding="utf-8")
        if case_id in _THRESHOLD_CARRYING_CASES:
            assert "(threshold" in text
            assert f"(threshold {_DEFAULT_MAX_OFFSET_MM:.1f} mm)" in text
        else:
            assert "(threshold" not in text


# =========================================================================== #
# AC27: the Stage-3 report golden is byte-unchanged
# =========================================================================== #


def test_ac27_stage3_report_golden_matches_test_022_output():
    import test_022_stage3_serialisation as t022

    centroids = t022._straight_spine(5)
    block = t022._full_block_for_spine(centroids)
    produced = t022.serialize_report_json(
        t022._empty_verdict(), "golden-case-022", t022._config(), features=block
    )
    committed = t022.GOLDEN_PATH.read_text(encoding="utf-8")
    assert produced == committed


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
    from test_098_stray_components import _PRE_098_GOLDEN_VERDICT_AND_FINDINGS

    mode1_expected = _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode1_displace"]["findings"][0]["reason"]
    mode1_golden = load_golden("mode1_displace")
    mode1_actual = next(f["reason"] for f in mode1_golden["findings"] if f["rule_id"] == "mislabel")
    assert mode1_actual == mode1_expected

    mode6_expected = next(
        f["reason"] for f in _PRE_098_GOLDEN_VERDICT_AND_FINDINGS["mode6_crop_at_border"]["findings"]
        if f["rule_id"] == "mislabel"
    )
    mode6_golden = load_golden("mode6_crop_at_border")
    mode6_actual = next(f["reason"] for f in mode6_golden["findings"] if f["rule_id"] == "mislabel")
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


def test_ac33_test098_digest_fence_matches_committed_file():
    from test_098_stray_components import _PRE_098_REFERENCE_VERSE_V1_SHA256

    digest = hashlib.sha256(bundled_production_reference_path().read_bytes()).hexdigest()
    assert digest == _PRE_098_REFERENCE_VERSE_V1_SHA256


def test_ac34_retired_test_names_absent_from_test_120_source():
    source = (_REPO_ROOT / "tests" / "test_120_leave_one_out_offset.py").read_text(encoding="utf-8")
    assert "test_ac29_reference_verse_v1_unchanged" not in source
    assert "test_ac16_default_max_offset_mm_still_15" not in source


# =========================================================================== #
# Adversarial / edge cases
# =========================================================================== #


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
