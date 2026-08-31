#!/usr/bin/env python3
"""One-command reference-refresh wrapper (item 083).

This is an AIDE *project tool*, not part of the shipped ``segfacet`` package
(mirrors ``scripts/aide_status_report.py``'s path-loaded, testable-helper
shape). In one ``main(argv)`` invocation it refreshes the project's reference
artifacts and re-runs the Stage-7 evaluation, so a maintainer who changed a
feature or config can rebuild and re-check *everything* with one command
(usable in CI):

1. Rebuilds the synthetic default reference artifact (item 045's
   ``build_and_write_default``) into ``<out>/reference_default.json`` --
   never touching the committed package copy.
2. Synthesizes a tiny, deterministic self-vs-self evaluation cohort from the
   production synth builders (``segfacet.synth.clean_gt.build_clean_spine``)
   into ``<out>/eval_cohort/``.
3. Runs ``segfacet evaluate`` over that cohort (in-process, via
   ``segfacet.cli.main``), producing ``<out>/eval_synthetic/eval_report.json``.

Every step's outcome is recorded in a machine-checkable structured summary: a
``dict`` returned from :func:`run_refresh` *and* written to
``<out>/refresh_summary.json``, with a per-step ``name``/``status``
(``ran``/``skipped``/``failed``)/``reason``.

Usage::

    python scripts/refresh_reference.py --out out/refresh

For a real VerSe cohort, use ``scripts/rebuild_verse_reference.py`` (item
123) instead -- this wrapper's real-VerSe mode is retired (item 133,
2026-08-31): it never handled the real nested VerSe19 layout, and the
dedicated script owns discovery, staging, build and threshold calibration
end to end.

Self-contained: imports only ``segfacet.*`` production modules; never imports
the ``tests`` package nor reads the test corpus fixtures, so it runs unmodified
in a deployed checkout with no test fixtures present.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Canonical per-step names used in the summary (stable identifiers a test
#: asserts on).
STEP_SYNTH_REBUILD = "synthetic-default-rebuild"
STEP_EVAL_COHORT = "synthetic-eval-cohort"
STEP_SYNTH_EVALUATE = "synthetic-evaluate"

#: Fixed, literal recipe for the self-vs-self synthesis cohort -- deterministic
#: ``build_clean_spine`` parameters only (no RNG, no wall clock).
_EVAL_COHORT_RECIPE = (
    {
        "case_id": "refresh-eval-000",
        "levels": ("L1", "L2", "L3", "L4", "L5"),
        "spacing": (1.0, 1.0, 1.0),
        "curve_amplitude_mm": 6.0,
    },
    {
        "case_id": "refresh-eval-001",
        "levels": ("L1", "L2", "L3", "L4"),
        "spacing": (1.0, 1.0, 1.2),
        "curve_amplitude_mm": 4.0,
    },
)


def _step(name: str, status: str, reason: str, output: Optional[str] = None) -> Dict[str, Any]:
    return {"name": name, "status": status, "reason": reason, "output": output}


def synthesize_eval_cohort(out_dir: "Path | str", *, spec: Optional[Any] = None) -> Path:
    """Write a deterministic self-vs-self clean-spine eval cohort (GT +
    byte-identical candidate NIfTIs + an ``evaluate``-shape manifest) into
    ``<out_dir>/eval_cohort`` from ``segfacet.synth.clean_gt.build_clean_spine``.

    ``gt``/``candidate`` manifest paths are stored relative to the manifest's
    own directory (item 057's resolution rule), so the cohort directory is
    relocatable. Returns the written manifest path.

    Reads no wall clock; no RNG beyond the seeded synth builders. ``spec`` is
    reserved for a future custom recipe; when ``None`` the fixed
    ``_EVAL_COHORT_RECIPE`` is used.
    """
    import nibabel as nib

    from segfacet.synth.clean_gt import build_clean_spine

    recipe = spec if spec is not None else _EVAL_COHORT_RECIPE

    cohort_dir = Path(out_dir) / "eval_cohort"
    cohort_dir.mkdir(parents=True, exist_ok=True)

    cases: List[Dict[str, Any]] = []
    for entry in recipe:
        case_id = entry["case_id"]
        spine = build_clean_spine(
            levels=entry["levels"],
            spacing=entry["spacing"],
            curve_amplitude_mm=entry["curve_amplitude_mm"],
        )
        gt_name = f"{case_id}_gt.nii.gz"
        cand_name = f"{case_id}_cand.nii.gz"
        nib.save(spine.seg_img, str(cohort_dir / gt_name))
        # Self-vs-self: candidate is byte-identical to GT.
        (cohort_dir / cand_name).write_bytes((cohort_dir / gt_name).read_bytes())

        cases.append(
            {
                "case_id": case_id,
                "gt": gt_name,
                "candidate": cand_name,
                "expected": {"expected_verdict": "pass"},
            }
        )

    manifest = {"manifest_version": 1, "cases": cases}
    manifest_path = cohort_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


def _run_synthetic_eval(manifest_path: Path, out_subdir: Path, *, build_date: str, cohort_id: str) -> Path:
    from segfacet.cli import main as segfacet_main

    rc = segfacet_main(
        [
            "evaluate",
            "--cohort",
            str(manifest_path),
            "--out",
            str(out_subdir),
            "--build-date",
            build_date,
            "--cohort-id",
            cohort_id,
        ]
    )
    if rc != 0:
        raise RuntimeError(f"segfacet evaluate exited with code {rc} for {manifest_path}")
    return out_subdir / "eval_report.json"


def run_refresh(
    out_dir: "Path | str",
    *,
    build_date: str = "2026-07-15",
) -> Dict[str, Any]:
    """Orchestrate the synthetic refresh; write only under ``out_dir``;
    return the summary dict."""
    from segfacet.reference import build_and_write_default

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    steps: List[Dict[str, Any]] = []

    # -- synthetic-default-rebuild ------------------------------------- #
    default_json = out_path / "reference_default.json"
    build_and_write_default(default_json)
    steps.append(
        _step(
            STEP_SYNTH_REBUILD,
            "ran",
            "rebuilt the synthetic default reference artifact",
            str(default_json),
        )
    )

    # -- synthetic-eval-cohort ------------------------------------------ #
    manifest_path = synthesize_eval_cohort(out_path)
    steps.append(
        _step(
            STEP_EVAL_COHORT,
            "ran",
            "synthesized a self-vs-self clean-spine eval cohort",
            str(manifest_path),
        )
    )

    # -- synthetic-evaluate ---------------------------------------------- #
    eval_out = out_path / "eval_synthetic"
    eval_report = _run_synthetic_eval(
        manifest_path, eval_out, build_date=build_date, cohort_id="refresh-synthetic"
    )
    steps.append(
        _step(
            STEP_SYNTH_EVALUATE,
            "ran",
            "ran segfacet evaluate over the synthetic self-vs-self cohort",
            str(eval_report),
        )
    )

    return {
        "out_dir": str(out_path),
        "steps": steps,
    }


#: Pointer message for the retired VerSe mode (AC8) -- a single line, no
#: traceback, naming the tool that actually does the job.
_VERSE_RETIRED_MESSAGE = (
    "refresh_reference: --verse-cohort is retired; use "
    "scripts/rebuild_verse_reference.py <verse-root> --out <dir> instead."
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refresh_reference",
        description=(
            "Refresh the synthetic default reference artifact and re-run "
            "the Stage-7 evaluation in one command."
        ),
    )
    parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory; every artifact this tool writes lives here.",
    )
    parser.add_argument(
        "--verse-cohort",
        default=None,
        metavar="<dir>",
        help=(
            "Retired (item 133): use scripts/rebuild_verse_reference.py "
            "instead. Supplying this flag is a hard error."
        ),
    )
    parser.add_argument(
        "--verse-seg-suffix",
        default=None,
        metavar="<suffix>",
        help=(
            "Retired (item 133): use scripts/rebuild_verse_reference.py "
            "instead. Supplying this flag is a hard error."
        ),
    )
    parser.add_argument(
        "--build-date",
        default="2026-07-15",
        metavar="<YYYY-MM-DD>",
        help="Fixed ISO build-date stamped into rebuilt artifacts (default: %(default)s).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.verse_cohort is not None or args.verse_seg_suffix is not None:
        print(_VERSE_RETIRED_MESSAGE, file=sys.stderr)
        return 2

    out_path = Path(args.out)
    summary = run_refresh(out_path, build_date=args.build_date)

    summary_path = out_path / "refresh_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    steps_by_name = {step["name"]: step for step in summary["steps"]}
    synthetic_ok = all(
        steps_by_name.get(name, {}).get("status") == "ran"
        for name in (STEP_SYNTH_REBUILD, STEP_EVAL_COHORT, STEP_SYNTH_EVALUATE)
    )

    print(
        "refresh_reference: "
        + ", ".join(f"{s['name']}={s['status']}" for s in summary["steps"])
        + f" -> summary written to {summary_path}"
    )

    return 0 if synthetic_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
