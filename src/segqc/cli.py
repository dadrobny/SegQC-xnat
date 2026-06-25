"""Command-line entry point for ``segqc``.

This module defines the argument parser and subcommand dispatch for the
``segqc`` console script (see ``[project.scripts]`` in ``pyproject.toml``).

Scope (item 006): the ``run`` subcommand is fully wired — it loads both input
volumes via :func:`segqc.io.load_case`, resolves anatomical names via
:func:`segqc.labels.summarise_inventory`, prints the labelled inventory to
stdout, and writes a stub JSON report to ``<out>/segqc_report.json``.
Heavy imports (NiBabel, NumPy, ...) are deferred to ``_handle_run`` so that
``segqc --help`` stays fast and import-clean.
"""

from __future__ import annotations

import argparse
import json
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


def _write_stub_json(
    out_dir: str,
    case,
    summary,
    cfg,
) -> pathlib.Path:
    """Write the stub JSON report to ``<out_dir>/segqc_report.json``.

    Creates ``out_dir`` (including any missing parents) if it does not exist,
    then writes a UTF-8 JSON file with the following top-level keys:

    - ``scan_path``             -- absolute path of the scan NIfTI
    - ``seg_path``              -- absolute path of the segmentation NIfTI
    - ``spacing``               -- [sx, sy, sz] voxel sizes in mm
    - ``foreground_voxels``     -- total non-background voxel count
    - ``label_inventory``       -- list of ``{label, name, voxels}`` objects
    - ``config_schema_version`` -- from ``default_config().schema_version``

    Returns the :class:`pathlib.Path` of the written file.
    """
    out_path = pathlib.Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    label_inventory = [
        {"label": v, "name": n, "voxels": c}
        for v, n, c in summary.recognised
    ]
    # Include unknown labels that have a valid integer count; skip malformed
    # ones so the JSON stays schema-clean (no null/non-integer values).
    for v, c in summary.unknown:
        if isinstance(c, int):
            label_inventory.append({
                "label": int(v) if isinstance(v, int) else str(v),
                "name": "unknown",
                "voxels": c,
            })

    report = {
        "scan_path": case.scan.path,
        "seg_path": case.seg.path,
        "spacing": list(case.scan.spacing),
        "foreground_voxels": case.foreground_voxels,
        "label_inventory": label_inventory,
        "config_schema_version": cfg.schema_version,
    }

    report_path = out_path / "segqc_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


def _handle_run(args: argparse.Namespace) -> int:
    """Handler for ``segqc run``.

    Loads the scan and segmentation, prints the labelled inventory, and writes
    a stub JSON report. Returns 0 on success, 1 on input error.
    """
    # Set up logging first so any subsequent log messages respect the level.
    from segqc._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    from segqc.io import SegQCInputError, load_case  # noqa: PLC0415
    from segqc.labels import LabelConvention, summarise_inventory  # noqa: PLC0415
    from segqc.config import default_config  # noqa: PLC0415

    logger.debug(
        "segqc run: scan=%r  seg=%r  out=%r", args.scan, args.seg, args.out
    )

    try:
        case = load_case(args.scan, args.seg)
    except SegQCInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    convention = LabelConvention.default()
    summary = summarise_inventory(case.label_inventory, convention)
    cfg = default_config()

    _print_inventory(summary)
    report_path = _write_stub_json(args.out, case, summary, cfg)

    logger.info("segqc run complete -- report written to %s", report_path)
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
