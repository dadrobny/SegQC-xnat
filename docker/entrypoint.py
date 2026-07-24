"""Container entry script — XNAT mounted-directory inputs -> ``segfacet run`` (item 068).

This script is the process the container image actually invokes for the
`segfacet-xnat` XNAT Container Service command (item 067's ``command.json``). It
translates XNAT's mounted-directory input/output convention into a single
``segfacet run`` invocation and leaves the two report files where XNAT collects
them as output resources.

Pinned in-image path (item 067's ``command-line`` invokes this exact path):

    /app/docker/entrypoint.py

Mount / argument contract (matches ``command.json`` verbatim; see item 067):

    python /app/docker/entrypoint.py \
        --scan-dir /input/scan --seg-dir /input/seg --out-dir /output \
        --config-dir /input/config --reference-dir /input/reference \
        [--reference] [--intensity]

Mapping performed here:

- ``--scan-dir`` / ``--seg-dir`` (required): resolve to the single NIfTI file
  (``*.nii`` / ``*.nii.gz``, case-insensitive, top-level non-recursive) found
  in the directory, mapped to ``segfacet run --scan`` / ``--seg``.
- ``--out-dir`` (required): passed verbatim as ``segfacet run --out``. ``segfacet
  run`` itself creates the directory and writes ``segfacet_report.json`` /
  ``segfacet_report.txt`` there.
- ``--config-dir`` (optional): resolves the single ``*.yaml``/``*.yml`` file,
  if any, mapped to ``segfacet run --config``. Absent/empty is a no-op (the
  bundled default config is used).
- ``--reference-dir`` (optional): resolves the single ``*.json`` file, if
  any, mapped to ``segfacet run --reference --reference-artifact``. Absent/empty
  is a no-op.
- ``--reference`` / ``--intensity`` (``store_true`` toggles): forwarded
  verbatim to ``segfacet run --reference`` / ``--intensity``. ``--reference`` is
  only ever added once, even when both the toggle and a resolved reference
  file are present (see :func:`build_run_argv`).

Invocation mechanism (see item 068's Decisions log / Assumptions): the
pipeline is invoked in-process via ``segfacet.cli.main(argv)``, not by shelling
out to the ``segfacet`` console script -- this reuses ``segfacet.cli``'s own
``Error:``-to-stderr / return-1 error convention and keeps this script fully
unit-testable Docker-free.

Any error raised while resolving inputs (a missing/empty/ambiguous mount, or
a non-NIfTI-only directory) is surfaced as a single ``Error: ...`` line on
stderr and a non-zero return code -- never a raw traceback -- and happens
*before* ``segfacet.cli.main`` is ever called, so a broken mount never leaves a
partial report behind.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

# Extensions recognised as "NIfTI" (case-insensitive), matching what
# segfacet.io.load_volume documents.
_NIFTI_PATTERNS = ("*.nii", "*.nii.gz")


class EntryScriptError(Exception):
    """Raised when the entry script cannot resolve/validate its own inputs.

    Caught in :func:`main`, printed as a single ``Error: <message>`` line to
    stderr, and converted to a non-zero return code -- never propagated as a
    raw traceback.
    """


def _build_parser() -> argparse.ArgumentParser:
    """Construct the entry script's own argument parser.

    Mirrors item 067's ``command.json`` command-line exactly: three required
    mounted-directory flags, two optional override-directory flags, and two
    boolean toggles. Unknown/extra arguments are a normal argparse usage
    error (``SystemExit``), matching the pin in the item's Assumptions.
    """
    parser = argparse.ArgumentParser(
        prog="entrypoint.py",
        description=(
            "XNAT Container Service entry point: maps mounted-directory "
            "inputs to a single `segfacet run` invocation."
        ),
    )
    parser.add_argument(
        "--scan-dir",
        required=True,
        metavar="<dir>",
        help="Directory containing exactly one scan NIfTI file.",
    )
    parser.add_argument(
        "--seg-dir",
        required=True,
        metavar="<dir>",
        help="Directory containing exactly one segmentation NIfTI file.",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        metavar="<dir>",
        help="Output directory for the QC report(s).",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        metavar="<dir>",
        help=(
            "Optional directory containing at most one *.yaml/*.yml "
            "heuristic-config override file."
        ),
    )
    parser.add_argument(
        "--reference-dir",
        default=None,
        metavar="<dir>",
        help=(
            "Optional directory containing at most one *.json reference "
            "artifact override file."
        ),
    )
    parser.add_argument(
        "--reference",
        action="store_true",
        default=False,
        help="Enable reference mode (forwarded to `segfacet run --reference`).",
    )
    parser.add_argument(
        "--intensity",
        action="store_true",
        default=False,
        help="Enable intensity mode (forwarded to `segfacet run --intensity`).",
    )
    return parser


def _matches_any_pattern(name: str, patterns: Iterable[str]) -> bool:
    """Case-insensitive glob-style suffix match against ``patterns``.

    ``patterns`` are simple ``"*.ext"`` globs (the only shape used in this
    module); matching is done on lowercased names so mixed-case extensions
    (e.g. ``CASE.YAML``) are recognised regardless of filesystem case
    sensitivity.
    """
    lowered = name.lower()
    for pattern in patterns:
        suffix = pattern.lower().lstrip("*")
        if lowered.endswith(suffix):
            return True
    return False


def resolve_required_nifti(dir_path: Union[str, Path], role: str) -> Path:
    """Resolve the single NIfTI file inside a required mount directory.

    ``role`` is a human-readable label (e.g. ``"scan"`` / ``"segmentation"``)
    used to build a clear error message naming the offending mount.

    Raises :class:`EntryScriptError` when:

    - ``dir_path`` does not exist, or is not a directory;
    - the directory contains zero NIfTI (``*.nii``/``*.nii.gz``,
      case-insensitive) files (including when it is empty or contains only
      non-NIfTI files);
    - the directory contains two or more NIfTI files (ambiguous).
    """
    directory = Path(dir_path)
    if not directory.exists():
        raise EntryScriptError(
            f"{role} directory does not exist: {directory}"
        )
    if not directory.is_dir():
        raise EntryScriptError(
            f"{role} directory is not a directory: {directory}"
        )

    matches = [
        entry
        for entry in directory.iterdir()
        if entry.is_file() and _matches_any_pattern(entry.name, _NIFTI_PATTERNS)
    ]
    matches.sort(key=lambda p: p.name)

    if not matches:
        raise EntryScriptError(
            f"no NIfTI file (*.nii/*.nii.gz) found in {role} directory: {directory}"
        )
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches)
        raise EntryScriptError(
            f"ambiguous {role} directory {directory}: found {len(matches)} "
            f"NIfTI files ({names}); expected exactly one"
        )
    return matches[0]


def resolve_optional_file(
    dir_path: Optional[Union[str, Path]],
    patterns: Sequence[str],
    role: str,
) -> Optional[Path]:
    """Resolve an optional single override file inside a directory.

    Returns ``None`` (no-op) when ``dir_path`` is ``None``, does not exist,
    or contains no file matching ``patterns``. Raises
    :class:`EntryScriptError` when two or more files match (ambiguous
    override -- the optional resolver refuses to guess).
    """
    if dir_path is None:
        return None

    directory = Path(dir_path)
    if not directory.exists() or not directory.is_dir():
        return None

    matches = [
        entry
        for entry in directory.iterdir()
        if entry.is_file() and _matches_any_pattern(entry.name, patterns)
    ]
    matches.sort(key=lambda p: p.name)

    if not matches:
        return None
    if len(matches) > 1:
        names = ", ".join(m.name for m in matches)
        raise EntryScriptError(
            f"ambiguous {role} directory {directory}: found {len(matches)} "
            f"matching files ({names}); expected at most one"
        )
    return matches[0]


def build_run_argv(
    scan: Union[str, Path],
    seg: Union[str, Path],
    out_dir: Union[str, Path],
    config: Optional[Union[str, Path]],
    reference_file: Optional[Union[str, Path]],
    reference_flag: bool,
    intensity_flag: bool,
) -> List[str]:
    """Pure, side-effect-free assembler for the ``segfacet run`` argv.

    Order: ``["run", "--scan", scan, "--seg", seg, "--out", out_dir]``, then
    ``["--config", config]`` iff ``config`` is not ``None``; ``["--reference"]``
    iff ``reference_flag`` or ``reference_file`` is truthy (added at most
    once); ``["--reference-artifact", reference_file]`` iff ``reference_file``
    is not ``None``; ``["--intensity"]`` iff ``intensity_flag``.
    """
    argv: List[str] = [
        "run",
        "--scan", str(scan),
        "--seg", str(seg),
        "--out", str(out_dir),
    ]

    if config is not None:
        argv.extend(["--config", str(config)])

    if reference_flag or reference_file is not None:
        argv.append("--reference")

    if reference_file is not None:
        argv.extend(["--reference-artifact", str(reference_file)])

    if intensity_flag:
        argv.append("--intensity")

    return argv


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry-script entry point. Returns a process exit code.

    Parses arguments, resolves the mounted-directory inputs, assembles the
    ``segfacet run`` argv, and invokes ``segfacet.cli.main`` -- resolved at call
    time (``import segfacet.cli`` then ``segfacet.cli.main(...)``) so tests that
    monkeypatch ``segfacet.cli.main`` are observed. Any input-resolution error
    (or any other unexpected exception) is caught, printed as a single
    ``Error: <message>`` line to stderr, and converted into return code 1 --
    *before* ``segfacet.cli.main`` is ever called for a resolution error, so a
    broken mount never leaves a partial report behind.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        scan = resolve_required_nifti(args.scan_dir, "scan")
        seg = resolve_required_nifti(args.seg_dir, "segmentation")
        config = resolve_optional_file(args.config_dir, ("*.yaml", "*.yml"), "config")
        reference_file = resolve_optional_file(args.reference_dir, ("*.json",), "reference")
    except EntryScriptError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    run_argv = build_run_argv(
        scan=scan,
        seg=seg,
        out_dir=args.out_dir,
        config=config,
        reference_file=reference_file,
        reference_flag=args.reference,
        intensity_flag=args.intensity,
    )

    try:
        import segfacet.cli  # noqa: PLC0415

        return segfacet.cli.main(run_argv)
    except Exception as exc:  # noqa: BLE001 - convert any unexpected failure to a clean error
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
