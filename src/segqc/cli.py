"""Command-line entry point for ``segqc``.

This module defines the argument parser and subcommand dispatch for the
``segqc`` console script (see ``[project.scripts]`` in ``pyproject.toml``).

Scope (item 001): this is *scaffolding only*. The ``run`` subcommand exists and
parses its flags, but its handler is a stub that performs **no** file I/O and
exits cleanly — the real pipeline (load → inventory → stub JSON) is wired up in
item 006. Keep heavy imports (SciPy, scikit-image, NiBabel) out of this module
so ``segqc --help`` stays fast and import-clean.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence

from . import __version__


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
    run_parser.set_defaults(handler=_handle_run)

    return parser


def _handle_run(args: argparse.Namespace) -> int:
    """Stub handler for ``segqc run``.

    Performs no file I/O — it only confirms the arguments parsed. The real
    implementation (load volumes, print label inventory, write stub JSON) lands
    in item 006.
    """
    print(
        "segqc run is not yet implemented (Item 006).\n"
        f"  parsed --scan {args.scan!r}\n"
        f"  parsed --seg  {args.seg!r}\n"
        f"  parsed --out  {args.out!r}\n"
        "No files were read or written."
    )
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
