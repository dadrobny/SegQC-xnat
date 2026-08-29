#!/usr/bin/env python3
"""Layout-agnostic VerSe cohort staging + reference rebuild tool (item 123).

This is an AIDE *project tool*, not part of the shipped ``segfacet`` package
(follows ``scripts/refresh_reference.py``'s path-loaded, testable-helper
shape). It exists because ``segfacet.reference.ingest.ingest_cohort`` was
built for a flat, non-recursive cohort directory with a hardcoded
``<id>_scan.nii.gz`` sibling convention (item 044), while the real VerSe19
layout nests masks under ``derivatives/sub-verseNNN/`` and names CTs
``..._ct.nii.gz`` (see ``docs/aide/dataset-verse19.md``). This tool:

1. Resolves the cohort root from ``--verse-cohort``, else the
   ``SEGFACET_VERSE_COHORT`` environment variable, else records a structured
   skip -- never a hard-coded path.
2. Discovers masks by a recursive glob for ``*_seg-vert_msk.nii.gz`` beneath
   the root, so the zip-extraction wrapper layout
   (``docs/aide/dataset-verse19.md``) and a flat layout both work.
3. Stages a flat directory of links (falling back to copies) satisfying
   ``ingest_cohort``'s convention: each mask under its own filename, plus a
   ``<subject_id>_scan.nii.gz`` sibling for every mask whose CT was found.
   Nothing is ever written beneath the cohort root.
4. Drives the existing ``build_reference`` / ``write_artifact`` machinery
   over the staged directory, writing ``<out>/reference_verse_v1.json`` --
   never the committed package copy under ``src/segfacet/``.
5. Derives the recalibrated ``mislabel.max_offset_mm`` threshold via
   :func:`derive_max_offset_mm`, a pure function of the built
   ``ReferenceDistribution``, and records the calibration evidence.

Every step's outcome (and the calibration numbers) is written to
``<out>/verse_rebuild_summary.json`` -- see this module's paired test file
(``tests/test_123_recalibrate_and_regenerate.py``) for the pinned summary
shape. An unreachable cohort (missing root, or a root with no matching
masks) is always a structured skip, never a failure: ``main`` still returns
``0`` and still writes the summary.

Usage::

    python scripts/rebuild_verse_reference.py --out out/verse-rebuild
    python scripts/rebuild_verse_reference.py --out out/verse-rebuild \\
        --verse-cohort /path/to/mounted/verse19training

Self-contained: imports only ``segfacet.*`` production modules; never imports
the ``tests`` package.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Real-VerSe vertebra-mask filename suffix (docs/aide/dataset-verse19.md).
VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"
#: Real-VerSe CT filename suffix.
VERSE_CT_SUFFIX = "_ct.nii.gz"
#: ``ingest_cohort``'s hardcoded scan-sibling suffix (item 044).
STAGED_SCAN_SUFFIX = "_scan.nii.gz"

#: Machine-local configuration variable naming the cohort root -- resolution
#: order is ``--verse-cohort`` -> this env var -> not found. Never a literal
#: dataset path in this file.
ENV_VAR = "SEGFACET_VERSE_COHORT"

#: The floor `derive_max_offset_mm` never returns below (Assumptions:
#: `mode4_relabel_swap`'s 5.143859 mm non-firing ceiling must stay clear).
_FLOOR_MM = 6.0
#: The rounding granularity `derive_max_offset_mm` rounds up to.
_ROUND_STEP_MM = 0.5
#: A qualifying level must carry at least this many `spline_offset_mm`
#: subject-level records (small-sample levels' p99 is one subject's max).
_MIN_QUALIFYING_COUNT = 10

_SUMMARY_NAME = "verse_rebuild_summary.json"


# =========================================================================== #
# Cohort resolution
# =========================================================================== #


def resolve_cohort_root(cli_value: Optional[str]) -> Optional[Path]:
    """``--verse-cohort`` if given (non-empty), else ``SEGFACET_VERSE_COHORT``
    if set to a non-empty string, else ``None``. Never hard-codes a path."""
    if cli_value:
        return Path(cli_value)
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        return Path(env_value)
    return None


def discover_masks(root: Path) -> List[Path]:
    """Recursive, sorted, layout-agnostic mask discovery beneath *root*."""
    return sorted(root.rglob(f"*{VERSE_SEG_SUFFIX}"))


def _subject_id_for_mask(mask_path: Path) -> str:
    name = mask_path.name
    return name[: -len(VERSE_SEG_SUFFIX)]


# =========================================================================== #
# Staging
# =========================================================================== #


def _link_or_copy(src: Path, dest: Path) -> str:
    """Symlink *src* at *dest*; fall back to a copy when symlinking is
    unsupported by the platform. Returns ``"symlink"`` or ``"copy"``."""
    try:
        os.symlink(src, dest)
        return "symlink"
    except (OSError, NotImplementedError):
        shutil.copy2(src, dest)
        return "copy"


def stage_cohort(
    masks: Sequence[Path], root: Path, staging_dir: Path
) -> Dict[str, Any]:
    """Build the flat staging directory ``ingest_cohort`` expects.

    Never writes beneath *root*. Returns a dict with ``stage_mode``,
    ``staged_dir``, ``subjects_without_scan`` and ``collisions``.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    stage_modes = set()
    subjects_without_scan: List[Dict[str, str]] = []
    collisions: List[Dict[str, str]] = []
    seen_subject_ids: Dict[str, Path] = {}

    for mask_path in masks:
        subject_id = _subject_id_for_mask(mask_path)
        staged_mask_name = f"{subject_id}{VERSE_SEG_SUFFIX}"
        staged_mask_path = staging_dir / staged_mask_name

        if subject_id in seen_subject_ids and seen_subject_ids[subject_id] != mask_path:
            collisions.append(
                {
                    "subject_id": subject_id,
                    "reason": (
                        f"subject_id collision after suffix stripping: "
                        f"{seen_subject_ids[subject_id]} and {mask_path} both "
                        f"stripped to {subject_id!r}; keeping the first, "
                        f"skipping the duplicate"
                    ),
                }
            )
            continue
        seen_subject_ids[subject_id] = mask_path

        if not staged_mask_path.exists():
            mode = _link_or_copy(mask_path.resolve(), staged_mask_path)
            stage_modes.add(mode)

        ct_candidates = sorted(root.rglob(f"{subject_id}{VERSE_CT_SUFFIX}"))
        if ct_candidates:
            ct_path = ct_candidates[0]
            staged_scan_path = staging_dir / f"{subject_id}{STAGED_SCAN_SUFFIX}"
            if not staged_scan_path.exists():
                mode = _link_or_copy(ct_path.resolve(), staged_scan_path)
                stage_modes.add(mode)
        else:
            subjects_without_scan.append(
                {
                    "subject_id": subject_id,
                    "reason": (
                        f"no {subject_id}{VERSE_CT_SUFFIX} found beneath the "
                        f"cohort root; staged geometry/morphology only"
                    ),
                }
            )

    stage_mode = "copy" if "copy" in stage_modes else ("symlink" if stage_modes else "none")

    return {
        "stage_mode": stage_mode,
        "staged_dir": str(staging_dir),
        "subjects_without_scan": subjects_without_scan,
        "collisions": collisions,
    }


# =========================================================================== #
# Threshold derivation (AC9-AC11)
# =========================================================================== #


def derive_max_offset_mm(distribution) -> float:
    """Pure derivation of ``mislabel.max_offset_mm`` from a built
    :class:`~segfacet.reference.schema.ReferenceDistribution`.

    Returns ``max(6.0, S)`` where ``S`` is the smallest positive multiple of
    ``0.5`` strictly greater than ``P``, and ``P`` is the maximum over levels
    whose ``spline_offset_mm.count >= 10`` of that level's
    ``feature_stats["spline_offset_mm"].percentiles["p99"]``. Levels with
    fewer than 10 subjects are excluded. Reads no file, no clock, no
    environment; returns the same value for the same input on repeated
    calls. If no level qualifies (or none carries ``spline_offset_mm``
    stats at all), returns the floor ``6.0``.
    """
    from segfacet.reference import ALL_STRATUM

    p_max: Optional[float] = None
    for strata in distribution.levels.values():
        stats = strata.get(ALL_STRATUM)
        if stats is None:
            continue
        offset_stats = stats.feature_stats.get("spline_offset_mm")
        if offset_stats is None:
            continue
        if offset_stats.count < _MIN_QUALIFYING_COUNT:
            continue
        p99 = offset_stats.percentiles.get("p99")
        if p99 is None:
            continue
        if p_max is None or p99 > p_max:
            p_max = p99

    if p_max is None:
        return _FLOOR_MM

    steps = math.floor(p_max / _ROUND_STEP_MM) + 1
    rounded = steps * _ROUND_STEP_MM
    return max(_FLOOR_MM, rounded)


def _p99_by_level(distribution) -> Dict[str, Dict[str, Any]]:
    from segfacet.reference import ALL_STRATUM

    result: Dict[str, Dict[str, Any]] = {}
    for level_name, strata in distribution.levels.items():
        stats = strata.get(ALL_STRATUM)
        if stats is None:
            continue
        offset_stats = stats.feature_stats.get("spline_offset_mm")
        if offset_stats is None:
            continue
        result[level_name] = {
            "count": offset_stats.count,
            "p99": offset_stats.percentiles.get("p99"),
        }
    return result


def _level_attaining_p(p99_by_level: Dict[str, Dict[str, Any]], qualifying_levels: Sequence[str]) -> Optional[str]:
    best_level = None
    best_p99 = None
    for level_name in qualifying_levels:
        p99 = p99_by_level[level_name]["p99"]
        if best_p99 is None or p99 > best_p99:
            best_p99 = p99
            best_level = level_name
    return best_level


def _population_stats(values: Sequence[float]) -> Dict[str, Any]:
    """Cheap count/max/p99 summary over *values* (empty-safe)."""
    if not values:
        return {"count": 0, "max": None, "p99": None}
    ordered = sorted(values)
    n = len(ordered)
    # Nearest-rank p99 -- adequate for a diagnostic summary (not the
    # artifact's own percentile machinery, which reference/aggregate.py owns).
    rank = max(0, min(n - 1, math.ceil(0.99 * n) - 1))
    return {"count": n, "max": ordered[-1], "p99": ordered[rank]}


def _terminal_interior_counts(cohort_ingest) -> Dict[str, int]:
    """Exact terminal/interior occurrence counts (AC17), derived from
    ``ingest_cohort``'s own per-subject record counts rather than a second
    feature-extraction pass: every subject with `n >= 2` present, recognised
    levels contributes exactly 2 terminal occurrences (its cranial-most and
    caudal-most present level -- or all `n` when `n == 2`,
    `features/spline_offset.py`'s AC37) and `max(0, n - 2)` interior ones.
    A subject with fewer than 2 levels contributes neither (no stage3, hence
    no offset at all)."""
    terminal_count = 0
    interior_count = 0
    for subject in cohort_ingest.subjects:
        n = len(subject.records)
        if n < 2:
            continue
        terminal_count += min(n, 2)
        interior_count += max(0, n - 2)
    return {"terminal_count": terminal_count, "interior_count": interior_count}


def _calibration_block(distribution, cohort_ingest, threshold: float) -> Dict[str, Any]:
    """Build the ``calibration`` summary block (AC17).

    ``p99_by_level`` / ``P`` are read from the built (interior-only, AC41)
    ``distribution``, so the threshold derivation is unaffected by the
    terminal exclusion. ``terminal_count`` / ``interior_count`` (amended
    2026-08-29) make the exclusion's evidence regenerable: derived from
    ``ingest_cohort``'s own per-subject record counts (see
    :func:`_terminal_interior_counts`) rather than a second, terminal-value-
    retaining feature-extraction pass, since ``reference/ingest.py``
    deliberately discards a terminal offset's *value* before it reaches a
    ``FeatureRecord`` (AC41) -- only its *occurrence* is countable from here.
    ``interior_stats`` is a genuine population summary over the exact values
    the artifact was built from.
    """
    p99_by_level = _p99_by_level(distribution)
    qualifying_levels = sorted(
        name for name, entry in p99_by_level.items() if entry["count"] >= _MIN_QUALIFYING_COUNT
    )
    p_value = None
    if qualifying_levels:
        p_value = max(p99_by_level[name]["p99"] for name in qualifying_levels)
    level_at_p = _level_attaining_p(p99_by_level, qualifying_levels) if qualifying_levels else None

    subject_level_offsets: List[Dict[str, Any]] = []
    for subject in cohort_ingest.subjects:
        for record in subject.records:
            value = record.features.get("spline_offset_mm")
            if value is not None:
                subject_level_offsets.append(
                    {"subject_id": subject.subject_id, "level_name": record.level_name, "offset_mm": value}
                )

    total = len(subject_level_offsets)
    above = sum(1 for entry in subject_level_offsets if entry["offset_mm"] >= threshold)
    fraction = (above / total) if total else 0.0

    top = sorted(subject_level_offsets, key=lambda e: e["offset_mm"], reverse=True)[:10]
    top_subject_ids = [entry["subject_id"] for entry in top]

    counts = _terminal_interior_counts(cohort_ingest)
    interior_stats = _population_stats([entry["offset_mm"] for entry in subject_level_offsets])

    return {
        "status": "ran" if qualifying_levels or p99_by_level else "skipped",
        "p99_by_level": p99_by_level,
        "qualifying_levels": qualifying_levels,
        "P": p_value,
        "level_at_p": level_at_p,
        "threshold": threshold,
        "subject_levels_above_threshold": {"count": above, "fraction": fraction},
        "top_subject_ids": top_subject_ids,
        "terminal_count": counts["terminal_count"],
        "interior_count": counts["interior_count"],
        "interior_stats": interior_stats,
        "terminal_stats_note": (
            "terminal offset values are excluded before reaching a "
            "FeatureRecord (reference/ingest.py, AC41), so only their "
            "occurrence count is regenerable from this tool; see the item "
            "123 Decisions log for the one-off per-vertebra analysis that "
            "measured their magnitude."
        ),
    }


# =========================================================================== #
# Orchestration
# =========================================================================== #


def run_rebuild(
    *,
    out_dir: "Path | str",
    verse_cohort: Optional[str] = None,
    staging_dir: Optional["Path | str"] = None,
    build_date: str = "2026-08-29",
    seg_suffix: str = VERSE_SEG_SUFFIX,
    max_cases: Optional[int] = None,
) -> Dict[str, Any]:
    """Orchestrate cohort resolution, staging, build and calibration.

    Never raises for an absent/empty cohort -- that path is always a
    structured skip. Writes only under *out_dir* (and *staging_dir*, if
    given a location outside the cohort root -- the default is
    ``<out_dir>/staged_verse``). Returns the summary dict (also written to
    ``<out_dir>/verse_rebuild_summary.json`` by :func:`main`).
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    root = resolve_cohort_root(verse_cohort)

    if root is None:
        cohort_block = {
            "status": "skipped",
            "reason": f"no cohort root: pass --verse-cohort or set {ENV_VAR}",
            "root": None,
            "mask_count": 0,
            "discovery_glob": f"*{seg_suffix}",
            "case_ids": [],
        }
        return {
            "cohort": cohort_block,
            "staging": {"status": "skipped", "stage_mode": None, "staged_dir": None, "subjects_without_scan": []},
            "build": {"status": "skipped", "artifact_path": None, "subject_count": 0, "levels": [], "config_hash": None},
            "calibration": {"status": "skipped", "p99_by_level": {}, "qualifying_levels": [], "P": None,
                             "level_at_p": None, "threshold": _FLOOR_MM,
                             "subject_levels_above_threshold": {"count": 0, "fraction": 0.0},
                             "top_subject_ids": [], "terminal_count": 0, "interior_count": 0,
                             "interior_stats": {"count": 0, "max": None, "p99": None},
                             "terminal_stats_note": "cohort skipped -- no offsets computed"},
        }

    if not root.exists():
        cohort_block = {
            "status": "skipped",
            "reason": f"cohort root does not exist: {root}",
            "root": str(root),
            "mask_count": 0,
            "discovery_glob": f"*{seg_suffix}",
            "case_ids": [],
        }
        return {
            "cohort": cohort_block,
            "staging": {"status": "skipped", "stage_mode": None, "staged_dir": None, "subjects_without_scan": []},
            "build": {"status": "skipped", "artifact_path": None, "subject_count": 0, "levels": [], "config_hash": None},
            "calibration": {"status": "skipped", "p99_by_level": {}, "qualifying_levels": [], "P": None,
                             "level_at_p": None, "threshold": _FLOOR_MM,
                             "subject_levels_above_threshold": {"count": 0, "fraction": 0.0},
                             "top_subject_ids": [], "terminal_count": 0, "interior_count": 0,
                             "interior_stats": {"count": 0, "max": None, "p99": None},
                             "terminal_stats_note": "cohort skipped -- no offsets computed"},
        }

    masks = discover_masks(root)
    if max_cases is not None:
        masks = masks[:max_cases]

    if not masks:
        cohort_block = {
            "status": "skipped",
            "reason": f"no masks matching *{seg_suffix} found beneath {root}",
            "root": str(root),
            "mask_count": 0,
            "discovery_glob": f"*{seg_suffix}",
            "case_ids": [],
        }
        return {
            "cohort": cohort_block,
            "staging": {"status": "skipped", "stage_mode": None, "staged_dir": None, "subjects_without_scan": []},
            "build": {"status": "skipped", "artifact_path": None, "subject_count": 0, "levels": [], "config_hash": None},
            "calibration": {"status": "skipped", "p99_by_level": {}, "qualifying_levels": [], "P": None,
                             "level_at_p": None, "threshold": _FLOOR_MM,
                             "subject_levels_above_threshold": {"count": 0, "fraction": 0.0},
                             "top_subject_ids": [], "terminal_count": 0, "interior_count": 0,
                             "interior_stats": {"count": 0, "max": None, "p99": None},
                             "terminal_stats_note": "cohort skipped -- no offsets computed"},
        }

    case_ids = sorted({_subject_id_for_mask(m) for m in masks})

    cohort_block: Dict[str, Any] = {
        "status": "ran",
        "reason": None,
        "root": str(root),
        "mask_count": len(masks),
        "discovery_glob": f"*{seg_suffix}",
        "case_ids": case_ids,
    }

    stage_dir_path = Path(staging_dir) if staging_dir is not None else out_path / "staged_verse"
    staging_result = stage_cohort(masks, root, stage_dir_path)
    if staging_result["collisions"]:
        cohort_block["collisions"] = staging_result["collisions"]
    staging_block = {"status": "ran", **staging_result}

    from segfacet.config import bundled_default_config
    from segfacet.reference import Provenance, aggregate_reference, config_hash, write_artifact
    from segfacet.reference.ingest import ingest_cohort

    config = bundled_default_config()

    # A single ingestion pass drives both the built distribution and the
    # calibration block's per-subject-level values -- `build_reference`
    # would otherwise re-ingest (and hence re-run the full feature engine
    # over every scan) a second time.
    cohort_ingest = ingest_cohort(
        stage_dir_path,
        config=config,
        seg_suffix=VERSE_SEG_SUFFIX,
        with_size_proxy=False,
        with_intensity=True,
        with_morphology=True,
    )

    provenance = Provenance(
        source="verse-v1",
        config_hash=config_hash(config),
        build_date=build_date,
        size_proxy_name=None,
    )
    distribution = aggregate_reference(cohort_ingest.records, provenance=provenance)

    artifact_path = out_path / "reference_verse_v1.json"
    write_artifact(distribution, artifact_path)

    build_block = {
        "status": "ran",
        "artifact_path": str(artifact_path),
        "subject_count": distribution.subject_count,
        "levels": sorted(distribution.levels.keys()),
        "config_hash": distribution.provenance.config_hash,
    }

    threshold = derive_max_offset_mm(distribution)
    calibration_block = _calibration_block(distribution, cohort_ingest, threshold)

    return {
        "cohort": cohort_block,
        "staging": staging_block,
        "build": build_block,
        "calibration": calibration_block,
    }


# =========================================================================== #
# CLI
# =========================================================================== #


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rebuild_verse_reference",
        description=(
            "Stage a real (or layout-agnostic stand-in) VerSe cohort, rebuild "
            "reference_verse_v1.json from it, and derive the recalibrated "
            "mislabel.max_offset_mm threshold."
        ),
    )
    parser.add_argument("--out", required=True, metavar="<dir>", help="Output directory.")
    parser.add_argument(
        "--verse-cohort",
        default=None,
        metavar="<dir>",
        help=f"Cohort root. Defaults to the {ENV_VAR} environment variable.",
    )
    parser.add_argument(
        "--staging-dir",
        default=None,
        metavar="<dir>",
        help="Flat staging directory (default: <out>/staged_verse).",
    )
    parser.add_argument(
        "--build-date",
        default="2026-08-29",
        metavar="<YYYY-MM-DD>",
        help="Caller-supplied ISO build date stamped into provenance (default: %(default)s).",
    )
    parser.add_argument(
        "--seg-suffix",
        default=VERSE_SEG_SUFFIX,
        metavar="<suffix>",
        help=f"Mask filename suffix (default: {VERSE_SEG_SUFFIX}).",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        metavar="<n>",
        help="Cap the number of discovered masks (for quick smoke runs).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    out_path = Path(args.out)
    out_path.mkdir(parents=True, exist_ok=True)

    summary = run_rebuild(
        out_dir=out_path,
        verse_cohort=args.verse_cohort,
        staging_dir=args.staging_dir,
        build_date=args.build_date,
        seg_suffix=args.seg_suffix,
        max_cases=args.max_cases,
    )

    summary_path = out_path / _SUMMARY_NAME
    summary_path.write_bytes(
        (json.dumps(summary, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )

    print(
        "rebuild_verse_reference: cohort={} staging={} build={} calibration={} "
        "-> summary written to {}".format(
            summary["cohort"]["status"],
            summary["staging"]["status"],
            summary["build"]["status"],
            summary["calibration"]["status"],
            summary_path,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
