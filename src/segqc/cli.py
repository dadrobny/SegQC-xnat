"""Command-line entry point for ``segqc``.

This module defines the argument parser and subcommand dispatch for the
``segqc`` console script (see ``[project.scripts]`` in ``pyproject.toml``).

Scope (item 010): the ``run`` subcommand is fully wired — it loads both input
volumes via :func:`segqc.io.load_case`, runs the empty/near-empty check
(:func:`segqc.empty.check_empty`), builds a :class:`~segqc.verdict.Verdict`,
writes a JSON report (:func:`segqc.report.serialize_report_json`) and a
human-readable plain-text report (:func:`segqc.human_report.render_human_report`)
to ``<out>/segqc_report.json`` and ``<out>/segqc_report.txt`` respectively.
Heavy imports (NiBabel, NumPy, ...) are deferred to ``_handle_run`` so that
``segqc --help`` stays fast and import-clean.
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
from typing import Optional, Sequence

from . import __version__

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="segqc",
        description=(
            "Automated quality control for vertebra instance segmentations "
            "of spine imaging."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    run_parser = subparsers.add_parser(
        "run",
        help="Run QC on a scan + segmentation pair and write a report.",
        description=(
            "Run quality control on a scan and its instance segmentation, "
            "writing the QC report to the output directory."
        ),
    )
    run_parser.add_argument(
        "--scan",
        required=True,
        metavar="<nii>",
        help="Path to the input scan (NIfTI).",
    )
    run_parser.add_argument(
        "--seg",
        required=True,
        metavar="<nii>",
        help="Path to the instance segmentation label map (NIfTI).",
    )
    run_parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory for the QC report.",
    )
    run_parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        metavar="<level>",
        help=(
            "Log level for the segqc logger hierarchy "
            "(DEBUG/INFO/WARNING/ERROR/CRITICAL; default: WARNING)."
        ),
    )
    run_parser.set_defaults(handler=_handle_run)

    return parser


def _print_inventory(summary) -> None:
    """Print the label inventory table to stdout.

    Prints recognised labels in anatomical order, then unknown labels (if any).
    Each row shows the integer label value, anatomical name, and voxel count.
    """
    print("Label inventory:")
    print("-" * 42)

    if not summary.recognised and not summary.unknown:
        print("  (no foreground labels found)")
        return

    for value, name, count in summary.recognised:
        print(f"  {value:>4}  {name:<12}  {count:>10} voxels")

    if summary.unknown:
        print()
        print("Unknown labels:")
        for value, count in summary.unknown:
            if isinstance(count, int):
                print(f"  {value!s:>4}  (unknown)     {count:>10} voxels")
            else:
                print(f"  {value!s:>4}  (unknown)     (malformed count: {count!r})")


def _handle_run(args: argparse.Namespace) -> int:
    """Handler for ``segqc run`` — full Stage 1 pipeline.

    Loads the scan and segmentation, runs the empty/near-empty check, builds
    a :class:`~segqc.verdict.Verdict`, and writes both a JSON report and a
    human-readable plain-text report to the output directory.

    Returns 0 on pass or flagged-for-review; returns 1 on fail or input error.
    Both report files are always written before the process exits (even on fail).
    """
    # Set up logging first so any subsequent log messages respect the level.
    from segqc._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    from segqc.io import SegQCInputError, load_case  # noqa: PLC0415
    from segqc.labels import LabelConvention, summarise_inventory  # noqa: PLC0415
    from segqc.config import default_config  # noqa: PLC0415
    from segqc.empty import check_empty  # noqa: PLC0415
    from segqc.verdict import Reason, Severity, Verdict  # noqa: PLC0415
    from segqc.report import serialize_report_json  # noqa: PLC0415
    from segqc.human_report import render_human_report  # noqa: PLC0415

    logger.debug(
        "segqc run: scan=%r  seg=%r  out=%r", args.scan, args.seg, args.out
    )

    # --- 1. Load inputs ------------------------------------------------------ #
    try:
        case = load_case(args.scan, args.seg)
    except SegQCInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path = pathlib.Path(args.out)
    if out_path.exists() and not out_path.is_dir():
        print(
            f"Error: --out path exists and is not a directory: {args.out}",
            file=sys.stderr,
        )
        return 1

    # --- 2. Print inventory (preserved from item 006) ------------------------- #
    convention = LabelConvention.default()
    summary = summarise_inventory(case.label_inventory, convention)
    _print_inventory(summary)

    # --- 3. Empty/near-empty check -------------------------------------------- #
    # check_empty expects a NiBabel Nifti1Image; construct one from the already-
    # loaded Volume array so we avoid a second disk read.
    import nibabel as nib  # noqa: PLC0415

    cfg = default_config()
    seg_img = nib.Nifti1Image(case.seg.data.astype("int32"), case.seg.affine)
    check_result = check_empty(seg_img, cfg)

    # --- 4. Build Verdict from CheckResult ------------------------------------ #
    # check_empty returns plain strings; convert them into Reason objects.
    # Severity is FAIL when is_empty=True (any condition fired), PASS otherwise.
    if check_result.is_empty:
        reasons = [
            Reason(message=msg, severity=Severity.FAIL)
            for msg in check_result.reasons
        ]
    else:
        reasons = [
            Reason(message=msg, severity=Severity.PASS)
            for msg in check_result.reasons
        ]
    verdict = Verdict.build(reasons=reasons, per_label={})

    # --- 5. Derive case_id from scan filename stem ---------------------------- #
    # Strip double extension (.nii.gz) or single extension (.nii).
    scan_stem = pathlib.Path(args.scan).name
    if scan_stem.endswith(".nii.gz"):
        case_id = scan_stem[:-7]
    elif scan_stem.endswith(".nii"):
        case_id = scan_stem[:-4]
    else:
        case_id = pathlib.Path(args.scan).stem

    # --- 6. Write both reports ------------------------------------------------ #
    out_path.mkdir(parents=True, exist_ok=True)

    json_str = serialize_report_json(verdict, case_id, cfg)
    json_path = out_path / "segqc_report.json"
    json_path.write_text(json_str, encoding="utf-8")

    txt_str = render_human_report(verdict, case_id, cfg)
    txt_path = out_path / "segqc_report.txt"
    txt_path.write_text(txt_str, encoding="utf-8")

    logger.info(
        "segqc run complete -- verdict=%s  json=%s  txt=%s",
        verdict.overall.label, json_path, txt_path,
    )

    # --- 7. Exit code --------------------------------------------------------- #
    # fail → 1; pass or flagged-for-review → 0.
    if verdict.overall == Severity.FAIL:
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a process exit code.

    The console-script wrapper generated from ``[project.scripts]`` calls
    ``sys.exit(main())``, so returning an int here sets the process exit code.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    handler = getattr(args, "handler", None)
    if handler is None:
        # No subcommand given: show usage and signal a usage error.
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
