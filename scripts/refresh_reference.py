#!/usr/bin/env python3
"""One-command reference-refresh wrapper (item 083).

This is an AIDE *project tool*, not part of the shipped ``segqc`` package
(mirrors ``scripts/aide_status_report.py``'s path-loaded, testable-helper
shape). In one ``main(argv)`` invocation it refreshes the project's reference
artifacts and re-runs the Stage-7 evaluation, so a maintainer who changed a
feature or config can rebuild and re-check *everything* with one command
(usable in CI):

1. Rebuilds the synthetic default reference artifact (item 045's
   ``build_and_write_default``) into ``<out>/reference_default.json`` --
   never touching the committed package copy.
2. Synthesizes a tiny, deterministic self-vs-self evaluation cohort from the
   production synth builders (``segqc.synth.clean_gt.build_clean_spine``)
   into ``<out>/eval_cohort/``.
3. Runs ``segqc evaluate`` over that cohort (in-process, via
   ``segqc.cli.main``), producing ``<out>/eval_synthetic/eval_report.json``.
4. Optionally builds the versioned real-VerSe artifact -- only if
   ``--verse-cohort <dir>`` is supplied *and* exists -- via item 045's
   ``build_reference`` following item 082's recipe, and re-evaluates a
   self-vs-self cohort synthesized from that VerSe GT. When absent, both
   VerSe steps degrade to a genuine, structured skip (never a failure) and
   the synthetic path still completes with exit 0.

Every step's outcome is recorded in a machine-checkable structured summary: a
``dict`` returned from :func:`run_refresh` *and* written to
``<out>/refresh_summary.json``, with a per-step ``name``/``status``
(``ran``/``skipped``/``failed``)/``reason``.

Usage::

    python scripts/refresh_reference.py --out out/refresh
    python scripts/refresh_reference.py --out out/refresh --verse-cohort /mnt/verse
    python scripts/refresh_reference.py --out out/refresh --verse-cohort /mnt/verse \\
        --verse-seg-suffix _seg-vert_msk.nii.gz --build-date 2026-07-15

Self-contained: imports only ``segqc.*`` production modules; never imports
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
STEP_VERSE_BUILD = "verse-build"
STEP_VERSE_EVALUATE = "verse-evaluate"

#: Default real-VerSe mask suffix (item 082 recipe) used when a
#: ``--verse-cohort`` is supplied.
DEFAULT_VERSE_SEG_SUFFIX = "_seg-vert_msk.nii.gz"

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
    ``<out_dir>/eval_cohort`` from ``segqc.synth.clean_gt.build_clean_spine``.

    ``gt``/``candidate`` manifest paths are stored relative to the manifest's
    own directory (item 057's resolution rule), so the cohort directory is
    relocatable. Returns the written manifest path.

    Reads no wall clock; no RNG beyond the seeded synth builders. ``spec`` is
    reserved for a future custom recipe; when ``None`` the fixed
    ``_EVAL_COHORT_RECIPE`` is used.
    """
    import nibabel as nib

    from segqc.synth.clean_gt import build_clean_spine

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
    from segqc.cli import main as segqc_main

    rc = segqc_main(
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
        raise RuntimeError(f"segqc evaluate exited with code {rc} for {manifest_path}")
    return out_subdir / "eval_report.json"


def run_refresh(
    out_dir: "Path | str",
    *,
    verse_cohort: "Optional[Path | str]" = None,
    verse_seg_suffix: str = DEFAULT_VERSE_SEG_SUFFIX,
    build_date: str = "2026-07-15",
) -> Dict[str, Any]:
    """Orchestrate the refresh; write only under ``out_dir``; return the
    summary dict.

    Never raises for an absent/missing ``verse_cohort`` -- that path is
    always a structured skip, not an exception.
    """
    from segqc.reference import build_and_write_default, build_reference, write_artifact

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
            "ran segqc evaluate over the synthetic self-vs-self cohort",
            str(eval_report),
        )
    )

    # -- verse-build / verse-evaluate ------------------------------------ #
    verse_path = Path(verse_cohort) if verse_cohort is not None else None
    if verse_path is None:
        reason = "no --verse-cohort supplied"
        steps.append(_step(STEP_VERSE_BUILD, "skipped", reason, None))
        steps.append(_step(STEP_VERSE_EVALUATE, "skipped", reason, None))
    elif not verse_path.exists():
        reason = f"--verse-cohort path does not exist: {verse_path}"
        steps.append(_step(STEP_VERSE_BUILD, "skipped", reason, None))
        steps.append(_step(STEP_VERSE_EVALUATE, "skipped", reason, None))
    else:
        try:
            verse_dist = build_reference(
                verse_path,
                source="verse-refresh-v1",
                build_date=build_date,
                seg_suffix=verse_seg_suffix,
            )
            verse_json = out_path / "reference_verse_v1.json"
            write_artifact(verse_dist, verse_json)
            steps.append(
                _step(
                    STEP_VERSE_BUILD,
                    "ran",
                    f"built the versioned real-VerSe artifact from {verse_path}",
                    str(verse_json),
                )
            )
        except Exception as exc:  # noqa: BLE001 -- never let verse-build crash the run
            reason = f"verse-build failed: {exc}"
            steps.append(_step(STEP_VERSE_BUILD, "failed", reason, None))
            steps.append(
                _step(
                    STEP_VERSE_EVALUATE,
                    "skipped",
                    "verse-build did not produce a GT cohort to evaluate",
                    None,
                )
            )
        else:
            try:
                verse_eval_manifest = synthesize_eval_cohort(out_path / "eval_verse_cohort_src")
                verse_eval_out = out_path / "eval_verse"
                verse_eval_report = _run_synthetic_eval(
                    verse_eval_manifest,
                    verse_eval_out,
                    build_date=build_date,
                    cohort_id="refresh-verse",
                )
                steps.append(
                    _step(
                        STEP_VERSE_EVALUATE,
                        "ran",
                        "ran segqc evaluate over a self-vs-self cohort synthesized "
                        "alongside the real-VerSe GT",
                        str(verse_eval_report),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                steps.append(
                    _step(STEP_VERSE_EVALUATE, "failed", f"verse-evaluate failed: {exc}", None)
                )

    return {
        "out_dir": str(out_path),
        "verse_cohort": str(verse_cohort) if verse_cohort is not None else None,
        "steps": steps,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refresh_reference",
        description=(
            "Refresh every reference artifact (synthetic default + optional "
            "versioned real-VerSe) and re-run the Stage-7 evaluation in one "
            "command."
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
            "Directory of a real (or stand-in) VerSe-shaped cohort. When "
            "omitted or nonexistent, the real-VerSe steps skip cleanly."
        ),
    )
    parser.add_argument(
        "--verse-seg-suffix",
        default=DEFAULT_VERSE_SEG_SUFFIX,
        metavar="<suffix>",
        help=f"Real-VerSe mask filename suffix (default: {DEFAULT_VERSE_SEG_SUFFIX}).",
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

    out_path = Path(args.out)
    summary = run_refresh(
        out_path,
        verse_cohort=args.verse_cohort,
        verse_seg_suffix=args.verse_seg_suffix,
        build_date=args.build_date,
    )

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
