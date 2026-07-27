"""Command-line entry point for ``segfacet``.

This module defines the argument parser and subcommand dispatch for the
``segfacet`` console script (see ``[project.scripts]`` in ``pyproject.toml``).

Scope (item 010): the ``run`` subcommand is fully wired — it loads both input
volumes via :func:`segfacet.io.load_case`, runs the empty/near-empty check
(:func:`segfacet.empty.check_empty`), builds a :class:`~segfacet.verdict.Verdict`,
writes a JSON report (:func:`segfacet.report.serialize_report_json`) and a
human-readable plain-text report (:func:`segfacet.human_report.render_human_report`)
to ``<out>/segfacet_report.json`` and ``<out>/segfacet_report.txt`` respectively.
Heavy imports (NiBabel, NumPy, ...) are deferred to ``_handle_run`` so that
``segfacet --help`` stays fast and import-clean.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
from typing import Optional, Sequence

from . import __version__

logger = logging.getLogger(__name__)

_BACKEND_HELP = (
    "Compute backend for feature extraction: 'cpu' (NumPy/SciPy), "
    "'gpu' (CuPy; requires the optional gpu extra + a CUDA device), or "
    "'auto' (GPU when available, else CPU). Omitted = auto (today's "
    "default); forcing gpu without CuPy exits 1 with a clear error."
)


def _apply_backend_selection(args: argparse.Namespace) -> Optional[int]:
    """Eagerly validate/resolve ``--backend`` and wire it into ``SEGFACET_BACKEND``.

    Called near the top of each ``_handle_*`` handler, before any input is
    loaded, so a forced-but-unavailable GPU (or an invalid ambient
    ``SEGFACET_BACKEND``) fails fast with a clean ``Error:`` message rather than
    a mid-pipeline traceback (item 075, AC3/AC5).

    When ``--backend`` was explicitly given, resolves it via
    :func:`segfacet.backend.get_backend` and, on success, sets
    ``os.environ["SEGFACET_BACKEND"]`` to the given token so the unmodified
    compute entry points (which auto-resolve ``backend=None -> get_backend()``
    per item 072) pick it up (AC4). When the flag was omitted, the ambient
    environment (or the ``auto`` default) governs untouched (AC6/AC7).

    Returns:
        An exit code (``1``) if backend resolution failed, else ``None`` to
        signal the caller should continue.
    """
    from segfacet.backend import FacetBackendError, get_backend  # noqa: PLC0415

    tok = getattr(args, "backend", None)
    try:
        get_backend(override=tok)
    except FacetBackendError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if tok is not None:
        os.environ["SEGFACET_BACKEND"] = tok

    return None


_DATASET_SCHEMA_HELP = (
    "Path to a declarative dataset descriptor (YAML/JSON, segfacet.datasets) "
    "mapping a nested/varied dataset (e.g. VerSe's derivatives/rawdata layout) "
    "onto the internal cohort interface -- ingested directly, no manual staging. "
    "Mutually exclusive with the flat --cohort discovery."
)


def _add_dataset_schema_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared Stage-13 dataset-adapter flags to a subcommand parser."""
    parser.add_argument(
        "--dataset-schema", default=None, metavar="<descriptor>", help=_DATASET_SCHEMA_HELP,
    )
    parser.add_argument(
        "--data-root", default=None, metavar="<dir>",
        help="Override the descriptor's data_root (so one committed descriptor "
             "works across machines). Only used with --dataset-schema.",
    )
    parser.add_argument(
        "--subset", default=None, metavar="<name>",
        help="Name of a subset in the descriptor (a folder split / CSV / id-list "
             "/ glob) to restrict to. Only used with --dataset-schema.",
    )


_RUN_MANIFEST_HELP = (
    "Stage 17 run-manifest provenance flags (item 096): each is optional and "
    "caller-supplied; the resulting 'run_manifest' block is emitted only "
    "when at least one of them is given (a plain invocation with none of "
    "these flags omits the block entirely, preserving the report's shape)."
)


def _add_run_manifest_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared Stage-17 run-manifest provenance flags (item 096) to a
    subcommand parser."""
    parser.add_argument(
        "--segmenter-version", default=None, metavar="<str>",
        help=f"Version string of the segmenter that produced the input. {_RUN_MANIFEST_HELP}",
    )
    parser.add_argument(
        "--segmenter-sha", default=None, metavar="<str>",
        help="Commit SHA (or similar) of the segmenter that produced the input.",
    )
    parser.add_argument(
        "--weights-hash", default=None, metavar="<str>",
        help="Hash of the segmenter's weights.",
    )
    parser.add_argument(
        "--seed", type=int, default=None, metavar="<int>",
        help="Integer seed used by the segmenter/pipeline. 0 is a meaningful "
             "value, distinct from omitting the flag.",
    )
    parser.add_argument(
        "--dataset-id", default=None, metavar="<str>",
        help="Identifier for the dataset the input belongs to.",
    )
    parser.add_argument(
        "--postproc-toggles", default=None, metavar="<json>",
        help="JSON object of free-form post-processing toggles (e.g. "
             '\'{"largest_component_only": true}\'). Must parse to a JSON '
             "object (mapping); malformed JSON or a non-object value exits 1 "
             "with a clear Error: message.",
    )


def _parse_postproc_toggles(raw: "Optional[str]") -> "Optional[dict]":
    """Parse ``--postproc-toggles``'s raw JSON string into a dict.

    Returns ``None`` when *raw* is ``None`` (flag omitted). Raises
    :class:`ValueError` with a clear message when *raw* is not valid JSON, or
    parses to a JSON value that is not an object (mapping) -- an explicitly
    empty ``'{}'`` is valid and returns ``{}``.
    """
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--postproc-toggles is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            "--postproc-toggles must be a JSON object (mapping), not "
            f"{type(parsed).__name__}."
        )
    return parsed


def _build_run_manifest_from_args(args: argparse.Namespace) -> "Optional[dict]":
    """Build the ``run_manifest`` dict (or ``None``) from the Stage-17 flags
    on *args*. Raises :class:`ValueError` on malformed ``--postproc-toggles``
    (caught by the caller and reported as a clean ``Error:`` message)."""
    from segfacet.run_manifest import build_run_manifest  # noqa: PLC0415

    postproc_toggles = _parse_postproc_toggles(getattr(args, "postproc_toggles", None))
    manifest = build_run_manifest(
        segmenter_version=getattr(args, "segmenter_version", None),
        segmenter_sha=getattr(args, "segmenter_sha", None),
        weights_hash=getattr(args, "weights_hash", None),
        seed=getattr(args, "seed", None),
        dataset_id=getattr(args, "dataset_id", None),
        postproc_toggles=postproc_toggles,
    )
    return None if manifest is None else manifest.to_dict()


def _resolve_cohort_from_args(args: argparse.Namespace, *, role: "Optional[str]" = None):
    """Resolve a :class:`segfacet.datasets.Cohort` from ``--dataset-schema`` /
    ``--data-root`` / ``--subset``, or ``None`` when ``--dataset-schema`` was not
    given. Raises ``DatasetSchemaError`` (caught by handlers) on any descriptor
    or resolution problem."""
    if not getattr(args, "dataset_schema", None):
        return None
    from segfacet.datasets import load_descriptor, resolve  # noqa: PLC0415

    descriptor = load_descriptor(args.dataset_schema)
    return resolve(
        descriptor,
        data_root=getattr(args, "data_root", None),
        subset=getattr(args, "subset", None),
        role=role,
    )


def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="segfacet",
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
        default=None,
        metavar="<nii>",
        help="Path to the input scan (NIfTI). Required for a single-case run; "
             "omit when using --dataset-schema (batch mode).",
    )
    run_parser.add_argument(
        "--seg",
        default=None,
        metavar="<nii>",
        help="Path to the instance segmentation label map (NIfTI). Required for "
             "a single-case run; omit when using --dataset-schema (batch mode).",
    )
    run_parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory for the QC report (single case), or the parent "
             "directory for per-case <out>/<case_id>/ reports (--dataset-schema).",
    )
    run_parser.add_argument(
        "--config",
        default=None,
        metavar="<yaml>",
        help=(
            "Path to a custom heuristic-config YAML file. When omitted, the "
            "bundled default_config.yaml (item 035) is used."
        ),
    )
    run_parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        metavar="<level>",
        help=(
            "Log level for the segfacet logger hierarchy "
            "(DEBUG/INFO/WARNING/ERROR/CRITICAL; default: WARNING)."
        ),
    )
    run_parser.add_argument(
        "--reference",
        action="store_true",
        default=False,
        help=(
            "Explicitly enable reference mode (item 049): compute a "
            "delta-to-reference block against a VerSe-style reference "
            "distribution and embed it in the report. Reference mode is ON "
            "by default as of item 090 (grounded on the bundled verse-v1 "
            "production artifact) -- this flag is now redundant with the "
            "default but kept for explicitness/back-compat; use "
            "--no-reference to disable."
        ),
    )
    run_parser.add_argument(
        "--no-reference",
        action="store_true",
        default=False,
        help=(
            "Disable reference mode (item 090), restoring the reference-"
            "less report shape (item 049's original OFF-by-default "
            "behaviour). Overrides --reference and any config "
            "reference.enabled: true."
        ),
    )
    run_parser.add_argument(
        "--reference-artifact",
        default=None,
        metavar="<json>",
        help=(
            "Path to a reference artifact JSON (item 045) to load when "
            "reference mode is enabled. When omitted, the bundled "
            "production artifact (bundled_production_reference(), "
            "verse-v1) is used (item 090; was bundled_default_reference() "
            "under item 049)."
        ),
    )
    run_parser.add_argument(
        "--intensity",
        action="store_true",
        default=False,
        help=(
            "Enable intensity mode (item 065): compute per-label first-order "
            "intensity/radiomics features from --scan and embed an "
            "image_features block in the report, letting the intensity / "
            "intensity_reference_delta rules fire. OFF by default -- falls "
            "back to config intensity.enabled when the flag itself is not "
            "given."
        ),
    )
    run_parser.add_argument(
        "--backend",
        default=None,
        choices=["cpu", "gpu", "auto"],
        metavar="<cpu|gpu|auto>",
        help=_BACKEND_HELP,
    )
    _add_dataset_schema_args(run_parser)
    _add_run_manifest_args(run_parser)
    run_parser.set_defaults(handler=_handle_run)

    build_reference_parser = subparsers.add_parser(
        "build-reference",
        help="Build a versioned reference-data artifact from a cohort directory.",
        description=(
            "Chain cohort ingestion (item 044) and aggregation (item 043) "
            "into a versioned reference-data artifact JSON file, ready for "
            "the delta-to-reference rules (items 046-049) to consume."
        ),
    )
    build_reference_parser.add_argument(
        "--cohort",
        default=None,
        metavar="<dir>",
        help="Path to a flat cohort directory to ingest (item 044 convention). "
             "Provide this OR --dataset-schema.",
    )
    build_reference_parser.add_argument(
        "--out",
        required=True,
        metavar="<json>",
        help="Destination path for the written reference artifact JSON.",
    )
    build_reference_parser.add_argument(
        "--source",
        default="synthetic-verse-cohort",
        metavar="<label>",
        help="Free-text provenance label for the cohort (default: %(default)s).",
    )
    build_reference_parser.add_argument(
        "--build-date",
        default="2026-07-11",
        metavar="<YYYY-MM-DD>",
        help=(
            "Fixed ISO build-date stamped into the artifact's provenance "
            "(default: %(default)s -- a fixed value, not 'today', to keep "
            "rebuilds reproducible)."
        ),
    )
    build_reference_parser.add_argument(
        "--config",
        default=None,
        metavar="<yaml>",
        help=(
            "Path to a custom heuristic-config YAML file. When omitted, the "
            "bundled default_config.yaml (item 035) is used."
        ),
    )
    build_reference_parser.add_argument(
        "--seg-suffix",
        default=None,
        metavar="<suffix>",
        help=(
            "Filename suffix identifying a subject's label map within "
            "--cohort (default: the item 044 convention '_seg.nii.gz')."
        ),
    )
    build_reference_parser.add_argument(
        "--size-strata-edges",
        default=None,
        nargs="+",
        type=float,
        metavar="<edge>",
        help=(
            "Optional size-proxy stratum edges (one or more floats); when "
            "given, the artifact is size-stratified."
        ),
    )
    build_reference_parser.add_argument(
        "--backend",
        default=None,
        choices=["cpu", "gpu", "auto"],
        metavar="<cpu|gpu|auto>",
        help=_BACKEND_HELP,
    )
    _add_dataset_schema_args(build_reference_parser)
    build_reference_parser.set_defaults(handler=_handle_build_reference)

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Run a Stage-7 evaluation over a cohort and write a metrics report.",
        description=(
            "Run a reproducible Stage-7 evaluation: load an evaluation-cohort "
            "manifest (a JSON document naming a set of GT / optional-candidate "
            "/ expected-verdict cases -- e.g. a mounted VerSe GT or "
            "TotalSegmentator-vs-GT cohort -- see segfacet.eval.cohort for the "
            "exact shape), drive it through evaluate_cohort -> "
            "compute_cohort_metrics (items 053/054), optionally calibrate "
            "rule thresholds against it (--calibrate, items 055/056), and "
            "write <out>/eval_report.json + <out>/eval_report.txt (and, when "
            "calibrating, <out>/calibrated_config.yaml). Example manifest "
            "shape:\n"
            '  {"manifest_version": 1, "cases": [{"case_id": "sub-001", '
            '"gt": "gt/sub-001.nii.gz", "candidate": "cand/sub-001.nii.gz", '
            '"expected": {"expected_verdict": "pass"}}]}\n'
            "gt/candidate paths are resolved relative to the manifest file's "
            "own directory."
        ),
    )
    evaluate_parser.add_argument(
        "--cohort",
        default=None,
        metavar="<json>",
        help="Path to an evaluation-cohort manifest JSON (segfacet.eval.cohort). "
             "Provide this OR --dataset-schema (which evaluates the resolved "
             "cohort as GT-as-expected-pass, quantifying the GT false-positive "
             "rate).",
    )
    evaluate_parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory for the evaluation report(s).",
    )
    evaluate_parser.add_argument(
        "--config",
        default=None,
        metavar="<yaml>",
        help=(
            "Path to a custom heuristic-config YAML file. When omitted, the "
            "bundled default_config.yaml (item 035) is used."
        ),
    )
    evaluate_parser.add_argument(
        "--calibrate",
        action="store_true",
        default=False,
        help=(
            "Also run the threshold-calibration loop (item 055) over the "
            "cohort using the default calibration axes, and -- when a "
            "feasible setting is found -- write <out>/calibrated_config.yaml "
            "and embed a 'calibration' block in the JSON report."
        ),
    )
    evaluate_parser.add_argument(
        "--cohort-id",
        default=None,
        metavar="<label>",
        help=(
            "Free-text identifier for the evaluated cohort, stamped into the "
            "report's provenance block (default: the --cohort filename stem)."
        ),
    )
    evaluate_parser.add_argument(
        "--build-date",
        default="2026-07-12",
        metavar="<YYYY-MM-DD>",
        help=(
            "Fixed ISO build-date stamped into the report's provenance "
            "(default: %(default)s -- a fixed value, not 'today', to keep "
            "repeated evaluations byte-reproducible)."
        ),
    )
    evaluate_parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        metavar="<level>",
        help=(
            "Log level for the segfacet logger hierarchy "
            "(DEBUG/INFO/WARNING/ERROR/CRITICAL; default: WARNING)."
        ),
    )
    evaluate_parser.add_argument(
        "--backend",
        default=None,
        choices=["cpu", "gpu", "auto"],
        metavar="<cpu|gpu|auto>",
        help=_BACKEND_HELP,
    )
    evaluate_parser.add_argument(
        "--reference",
        action="store_true",
        default=False,
        help=(
            "Attach a reference distribution (item 046) while evaluating: "
            "every case is run through run_qc_with_reference instead of "
            "plain run_qc, so the reference-derived bounds/fragmentation "
            "rule sources (item 090) and the reference_delta rule (item 047) "
            "actually engage (item 092). OFF by default -- unlike `segfacet "
            "run`, evaluate does NOT default this on from config, since a "
            "cohort evaluated without an explicit, matching reference "
            "artifact (e.g. a synthetic corpus against the real verse-v1 "
            "artifact) would silently score against the wrong distribution "
            "(the three-planes discipline, item 090)."
        ),
    )
    evaluate_parser.add_argument(
        "--reference-artifact",
        default=None,
        metavar="<json>",
        help=(
            "Path to a reference artifact JSON (item 045) to load when "
            "--reference is given. When omitted, the bundled production "
            "artifact (bundled_production_reference(), verse-v1) is used."
        ),
    )
    evaluate_parser.add_argument(
        "--per-mode",
        action="store_true",
        default=False,
        help=(
            "Attach a cohort-level per-mode magnitude summary (item 101): "
            "compute_per_mode_metrics is run once per case (item 099) and "
            "aggregated into a 'per_mode_magnitude' block in both "
            "eval_report.json and eval_report.txt. OFF by default -- "
            "with the flag omitted, the written report is byte-identical "
            "to the pre-101 output."
        ),
    )
    evaluate_parser.add_argument(
        "--run-id",
        default=None,
        metavar="<label>",
        help=(
            "Free-text label stamped into 'per_mode_magnitude.run_id' when "
            "--per-mode is given (default: the report's cohort id). Ignored "
            "without --per-mode."
        ),
    )
    _add_dataset_schema_args(evaluate_parser)
    _add_run_manifest_args(evaluate_parser)
    evaluate_parser.set_defaults(handler=_handle_evaluate)

    compare_runs_parser = subparsers.add_parser(
        "compare-runs",
        help="Diff two --per-mode evaluation reports into a run-vs-run comparison (item 101).",
        description=(
            "Read two eval_report.json files written by 'segfacet evaluate "
            "--per-mode', rehydrate their 'per_mode_magnitude' blocks, and "
            "diff them into a schema-validated run-vs-run comparison "
            "artifact: <out>/per_mode_comparison.json + "
            "<out>/per_mode_comparison.txt, naming the failure mode the "
            "change is attributed to. No array computation is performed "
            "here (two JSON documents and float arithmetic only), so this "
            "subcommand has no --backend flag."
        ),
    )
    compare_runs_parser.add_argument(
        "--run-a",
        required=True,
        metavar="<eval_report.json>",
        help="Path to run A's eval_report.json, written with --per-mode.",
    )
    compare_runs_parser.add_argument(
        "--run-b",
        required=True,
        metavar="<eval_report.json>",
        help="Path to run B's eval_report.json, written with --per-mode.",
    )
    compare_runs_parser.add_argument(
        "--out",
        required=True,
        metavar="<dir>",
        help="Output directory for the comparison report(s).",
    )
    compare_runs_parser.add_argument(
        "--run-a-id",
        default=None,
        metavar="<label>",
        help="Override label for run A in the comparison report (default: its own per_mode_magnitude.run_id).",
    )
    compare_runs_parser.add_argument(
        "--run-b-id",
        default=None,
        metavar="<label>",
        help="Override label for run B in the comparison report (default: its own per_mode_magnitude.run_id).",
    )
    compare_runs_parser.add_argument(
        "--build-date",
        default="2026-07-27",
        metavar="<YYYY-MM-DD>",
        help=(
            "Fixed ISO build-date stamped into the comparison report's "
            "provenance blocks (default: %(default)s -- a fixed value, not "
            "'today', to keep repeated comparisons byte-reproducible)."
        ),
    )
    compare_runs_parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        metavar="<level>",
        help=(
            "Log level for the segfacet logger hierarchy "
            "(DEBUG/INFO/WARNING/ERROR/CRITICAL; default: WARNING)."
        ),
    )
    compare_runs_parser.set_defaults(handler=_handle_compare_runs)

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


def _run_batch(args: argparse.Namespace) -> int:
    """Batch ``segfacet run`` over a dataset adapter (Stage 13, item 087).

    Resolves the ``--dataset-schema`` cohort and runs the single-case handler on
    each case (reusing all of :func:`_handle_run`'s logic) into
    ``<out>/<case_id>/``. Returns the worst per-case exit code (0 only if every
    case passed / was flagged); a single bad case does not abort the batch.
    """
    import copy  # noqa: PLC0415

    from segfacet.datasets import DatasetSchemaError  # noqa: PLC0415

    try:
        cohort = _resolve_cohort_from_args(args, role=None)
    except DatasetSchemaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if cohort is None or len(cohort) == 0:
        print("Error: --dataset-schema resolved an empty cohort.", file=sys.stderr)
        return 1

    out_root = pathlib.Path(args.out)
    worst = 0
    n_nonpass = 0
    for case in cohort:
        case_args = copy.copy(args)
        case_args.dataset_schema = None
        case_args.scan = case.scan_path
        case_args.seg = case.seg_path
        case_args.out = str(out_root / case.case_id)
        rc = _handle_run(case_args)
        if rc != 0:
            n_nonpass += 1
            worst = rc
    print(
        f"segfacet run (batch): {len(cohort)} case(s), {n_nonpass} non-pass/error "
        f"-> {out_root}"
    )
    return worst


def _handle_run(args: argparse.Namespace) -> int:
    """Handler for ``segfacet run`` — full Stage 1 + Stage 4 pipeline (item 035).

    Loads the scan and segmentation, runs the empty/near-empty check, then
    extracts the Stage 2/3 feature block and runs the Stage 4 rule engine over
    it (:func:`segfacet.pipeline.run_qc`), threading the empty-check's reasons in
    as case-level ``base_reasons`` so the aggregated verdict reflects both.
    When ``--intensity`` (or config ``intensity.enabled``) is set, dispatches
    to :func:`segfacet.pipeline.run_qc_with_intensity` instead (item 065),
    additionally computing per-label intensity/radiomics features and
    embedding an ``image_features`` block in both reports. Writes a JSON
    report (:func:`segfacet.report.serialize_report_json`, carrying ``features``
    + ``findings`` and, in intensity mode, ``image_features``) and a
    human-readable plain-text report
    (:func:`segfacet.human_report.render_human_report`, carrying a Findings
    section and, in intensity mode, an Intensity features section) to
    ``<out>/segfacet_report.json`` and ``<out>/segfacet_report.txt`` respectively.

    Returns 0 on pass or flagged-for-review; returns 1 on fail, input/config
    error, or (in intensity mode) a scan<->seg grid-alignment error. Both
    report files are always written before the process exits on a successful
    run (even on an aggregated fail); no report is written when the config,
    input, or grid alignment fails.
    """
    # Set up logging first so any subsequent log messages respect the level.
    from segfacet._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    # Batch mode: --dataset-schema runs QC on every case in the resolved cohort,
    # writing per-case reports under <out>/<case_id>/ (Stage 13, item 087).
    if getattr(args, "dataset_schema", None):
        return _run_batch(args)
    if not args.scan or not args.seg:
        print(
            "Error: provide --scan and --seg (single case) or --dataset-schema "
            "(batch mode).",
            file=sys.stderr,
        )
        return 1

    code = _apply_backend_selection(args)
    if code is not None:
        return code

    from segfacet.io import FacetInputError, load_case  # noqa: PLC0415
    from segfacet.labels import LabelConvention, summarise_inventory  # noqa: PLC0415
    from segfacet.config import (  # noqa: PLC0415
        FacetConfigError,
        bundled_default_config,
        load_config,
    )
    from segfacet.empty import check_empty  # noqa: PLC0415
    from segfacet.verdict import Reason, Severity  # noqa: PLC0415
    from segfacet.report import serialize_report_json  # noqa: PLC0415
    from segfacet.human_report import render_human_report  # noqa: PLC0415
    from segfacet.pipeline import (  # noqa: PLC0415
        run_qc,
        run_qc_with_intensity,
        run_qc_with_reference,
    )

    logger.debug(
        "segfacet run: scan=%r  seg=%r  out=%r  config=%r",
        args.scan, args.seg, args.out, args.config,
    )

    # --- 0. Load config (bundled default, or --config override) -------------- #
    if args.config:
        try:
            cfg = load_config(args.config)
        except FacetConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        cfg = bundled_default_config()

    # --- 0b. Optional run-manifest provenance (item 096) ----------------------- #
    try:
        run_manifest = _build_run_manifest_from_args(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- 1. Load inputs ------------------------------------------------------ #
    try:
        case = load_case(args.scan, args.seg)
    except FacetInputError as exc:
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

    seg_img = nib.Nifti1Image(case.seg.data.astype("int32"), case.seg.affine)
    check_result = check_empty(seg_img, cfg)

    # --- 4. Convert CheckResult into Stage-1 base reasons --------------------- #
    # check_empty returns plain strings; convert them into Reason objects.
    # Severity is FAIL when is_empty=True (any condition fired), PASS otherwise.
    if check_result.is_empty:
        base_reasons = [
            Reason(message=msg, severity=Severity.FAIL)
            for msg in check_result.reasons
        ]
    else:
        base_reasons = [
            Reason(message=msg, severity=Severity.PASS)
            for msg in check_result.reasons
        ]

    # --- 5. Extract features, run the Stage 4 rules, aggregate the verdict --- #
    # Reference mode -- ON by default as of item 090 (was OFF by default,
    # item 049); enabled via --reference or config reference.enabled (now
    # defaulting True), and forced off via --no-reference regardless of
    # either.
    reference_enabled = (
        bool(args.reference) or bool(cfg.reference_param("enabled", True))
    ) and not bool(args.no_reference)
    # Intensity mode (item 065) -- OFF by default; enabled via --intensity or
    # config intensity.enabled.
    intensity_enabled = bool(args.intensity) or bool(
        cfg.intensity_param("enabled", False)
    )

    reference = None
    reference_delta = None
    if reference_enabled:
        from segfacet.reference import (  # noqa: PLC0415
            ReferenceArtifactError,
            bundled_production_reference,
            load_artifact,
        )

        artifact_path = args.reference_artifact or cfg.reference_param(
            "artifact_path", None
        )
        try:
            if artifact_path:
                reference = load_artifact(artifact_path)
            else:
                # Item 090: the default production reference is verse-v1
                # (was the synthetic bundled_default_reference() under item
                # 049).
                reference = bundled_production_reference()
        except (ReferenceArtifactError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    stratum = cfg.reference_param("stratum", "all")
    lower_pct = cfg.reference_param("lower_pct", 1)
    upper_pct = cfg.reference_param("upper_pct", 99)

    image_features = None
    if intensity_enabled:
        scan_img = nib.Nifti1Image(case.scan.data, case.scan.affine)
        radiomics_enabled = bool(cfg.intensity_param("radiomics", True))
        try:
            (
                case_result,
                features_block,
                image_features,
                reference_delta,
                _intensity_reference_delta,
            ) = run_qc_with_intensity(
                seg_img,
                scan_img,
                cfg,
                reference=reference,
                base_reasons=base_reasons,
                enable_pyradiomics=radiomics_enabled,
                stratum=stratum,
                lower_pct=lower_pct,
                upper_pct=upper_pct,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    elif reference_enabled:
        case_result, features_block, reference_delta = run_qc_with_reference(
            seg_img,
            cfg,
            reference,
            base_reasons=base_reasons,
            stratum=stratum,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
        )
    else:
        case_result, features_block = run_qc(seg_img, cfg, base_reasons=base_reasons)
    verdict = case_result.verdict

    # --- 6. Derive case_id from scan filename stem ---------------------------- #
    # Strip double extension (.nii.gz) or single extension (.nii).
    scan_stem = pathlib.Path(args.scan).name
    if scan_stem.endswith(".nii.gz"):
        case_id = scan_stem[:-7]
    elif scan_stem.endswith(".nii"):
        case_id = scan_stem[:-4]
    else:
        case_id = pathlib.Path(args.scan).stem

    # --- 7. Write both reports ------------------------------------------------ #
    out_path.mkdir(parents=True, exist_ok=True)

    findings_dicts = [f.to_dict() for f in case_result.findings]

    json_str = serialize_report_json(
        verdict,
        case_id,
        cfg,
        features=features_block,
        findings=findings_dicts,
        reference_delta=reference_delta,
        image_features=image_features,
        run_manifest=run_manifest,
    )
    json_path = out_path / "segfacet_report.json"
    json_path.write_text(json_str, encoding="utf-8")

    txt_str = render_human_report(
        verdict,
        case_id,
        cfg,
        findings=case_result.findings,
        image_features=image_features,
        features=features_block,
    )
    txt_path = out_path / "segfacet_report.txt"
    txt_path.write_text(txt_str, encoding="utf-8")

    logger.info(
        "segfacet run complete -- verdict=%s  json=%s  txt=%s",
        verdict.overall.label, json_path, txt_path,
    )

    # --- 8. Exit code --------------------------------------------------------- #
    # fail → 1; pass or flagged-for-review → 0 (from the aggregated verdict).
    if verdict.overall == Severity.FAIL:
        return 1
    return 0


def _handle_build_reference(args: argparse.Namespace) -> int:
    """Handler for ``segfacet build-reference`` (item 045).

    Loads the config (bundled default or ``--config``), calls
    :func:`segfacet.reference.build_reference` then
    :func:`segfacet.reference.write_artifact`, prints the written path, and
    returns 0. Returns 1 (writing no ``--out`` file) on a bad ``--config``
    or a cohort-ingestion error (e.g. a nonexistent ``--cohort`` directory) --
    a caller error is reported, not a traceback.
    """
    from segfacet.config import FacetConfigError, bundled_default_config, load_config
    from segfacet.datasets import DatasetSchemaError
    from segfacet.reference import ReferenceArtifactError
    from segfacet.reference.artifact import (
        build_reference,
        build_reference_from_cohort,
        write_artifact,
    )
    from segfacet.reference.ingest import DEFAULT_SEG_SUFFIX

    code = _apply_backend_selection(args)
    if code is not None:
        return code

    if bool(args.cohort) == bool(args.dataset_schema):
        print(
            "Error: provide exactly one of --cohort (flat directory) or "
            "--dataset-schema (dataset adapter).",
            file=sys.stderr,
        )
        return 1

    if args.config:
        try:
            cfg = load_config(args.config)
        except FacetConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        cfg = bundled_default_config()

    seg_suffix = args.seg_suffix if args.seg_suffix is not None else DEFAULT_SEG_SUFFIX

    try:
        if args.dataset_schema:
            cohort = _resolve_cohort_from_args(args, role="gt")
            dist = build_reference_from_cohort(
                cohort,
                source=args.source,
                build_date=args.build_date,
                config=cfg,
                size_strata_edges=args.size_strata_edges,
            )
        else:
            dist = build_reference(
                args.cohort,
                source=args.source,
                build_date=args.build_date,
                config=cfg,
                seg_suffix=seg_suffix,
                size_strata_edges=args.size_strata_edges,
            )
    except (OSError, ReferenceArtifactError, DatasetSchemaError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path = write_artifact(dist, args.out)
    print(f"Wrote reference artifact to {out_path}")
    return 0


def _handle_evaluate(args: argparse.Namespace) -> int:
    """Handler for ``segfacet evaluate`` (item 057) -- the Stage-7 integration
    entry point.

    Loads the config (bundled default or ``--config``), loads the cohort via
    :func:`segfacet.eval.cohort.load_cohort_manifest`, drives
    ``evaluate_cohort -> compute_cohort_metrics`` (items 053/054),
    optionally runs the threshold-calibration loop (``--calibrate``, item
    055), builds + writes the JSON and human-readable evaluation reports
    (item 056), and -- when calibrating and a feasible setting was found --
    records the calibrated config. Returns 1 (writing no report) on a bad
    ``--config`` or a cohort-loading error (e.g. a nonexistent ``--cohort``
    path) -- a caller error is reported, not a traceback.
    """
    from segfacet._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    code = _apply_backend_selection(args)
    if code is not None:
        return code

    from segfacet.config import (  # noqa: PLC0415
        FacetConfigError,
        bundled_default_config,
        load_config,
    )
    from segfacet.datasets import DatasetSchemaError  # noqa: PLC0415
    from segfacet.eval.calibrate import calibrate_thresholds, default_calibration_axes  # noqa: PLC0415
    from segfacet.eval.cohort import load_cohort_manifest  # noqa: PLC0415
    from segfacet.eval.harness import EvaluationCase, evaluate_cohort  # noqa: PLC0415
    from segfacet.eval.metrics import compute_cohort_metrics  # noqa: PLC0415
    from segfacet.eval.per_mode_cohort import summarise_run_per_mode  # noqa: PLC0415
    from segfacet.eval.report import (  # noqa: PLC0415
        EvaluationProvenance,
        build_evaluation_report,
        record_calibrated_config,
        render_evaluation_report,
        write_evaluation_report,
    )
    from segfacet.io import FacetInputError  # noqa: PLC0415

    logger.debug(
        "segfacet evaluate: cohort=%r  out=%r  config=%r  calibrate=%r",
        args.cohort, args.out, args.config, args.calibrate,
    )

    if bool(args.cohort) == bool(args.dataset_schema):
        print(
            "Error: provide exactly one of --cohort (manifest JSON) or "
            "--dataset-schema (dataset adapter, evaluated as GT-as-expected-pass).",
            file=sys.stderr,
        )
        return 1

    # --- 0. Load config (bundled default, or --config override) -------------- #
    if args.config:
        try:
            cfg = load_config(args.config)
        except FacetConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        cfg = bundled_default_config()

    # --- 0b. Optional run-manifest provenance (item 096) ----------------------- #
    try:
        run_manifest = _build_run_manifest_from_args(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- 1. Load the cohort (a manifest, or GT-as-expected-pass from an adapter) - #
    try:
        if args.dataset_schema:
            resolved = _resolve_cohort_from_args(args, role="gt")
            # Each resolved GT case is a should-pass case (candidate == GT itself):
            # metrics.false_positive_rate is then the fraction of GT wrongly flagged.
            cases = [
                EvaluationCase(
                    case_id=c.case_id,
                    gt=c.seg_path,
                    expected={"expected_verdict": "pass"},
                )
                for c in resolved
            ]
            if not cases:
                print("Error: --dataset-schema resolved an empty cohort.", file=sys.stderr)
                return 1
        else:
            cases = load_cohort_manifest(args.cohort)
    except (FacetInputError, OSError, DatasetSchemaError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- 1b. Optional reference distribution (item 092) ------------------------ #
    reference = None
    if args.reference:
        from segfacet.reference import (  # noqa: PLC0415
            ReferenceArtifactError,
            bundled_production_reference,
            load_artifact,
        )

        try:
            if args.reference_artifact:
                reference = load_artifact(args.reference_artifact)
            else:
                reference = bundled_production_reference()
        except (ReferenceArtifactError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    stratum = cfg.reference_param("stratum", "all")
    lower_pct = cfg.reference_param("lower_pct", 1)
    upper_pct = cfg.reference_param("upper_pct", 99)

    # --- 2. Drive the harness + metrics --------------------------------------- #
    cohort = evaluate_cohort(
        cases,
        cfg,
        reference=reference,
        stratum=stratum,
        lower_pct=lower_pct,
        upper_pct=upper_pct,
        per_mode=args.per_mode,
    )
    metrics = compute_cohort_metrics(cohort)

    # --- 3. Optional calibration ----------------------------------------------- #
    if args.calibrate:
        axes = default_calibration_axes()
        calibration = calibrate_thresholds(
            cases,
            cfg,
            axes,
            reference=reference,
            stratum=stratum,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
        )
    else:
        axes = None
        calibration = None

    # --- 4. Build + write reports ---------------------------------------------- #
    _cohort_src = args.cohort or args.subset or args.dataset_schema
    cohort_id = args.cohort_id or pathlib.Path(_cohort_src).stem
    provenance = EvaluationProvenance(
        cohort_id=cohort_id,
        cohort_size=metrics.n_cases,
        config_version=cfg.schema_version,
        build_date=args.build_date,
    )

    # --- 4b. Optional cohort-level per-mode summary (item 101) ------------------ #
    per_mode_summary = None
    if args.per_mode:
        per_mode_summary = summarise_run_per_mode(
            cohort,
            run_id=args.run_id or cohort_id,
            metrics=metrics,
            run_manifest=run_manifest,
        )

    report = build_evaluation_report(
        metrics,
        provenance,
        calibration=calibration,
        run_manifest=run_manifest,
        per_mode_summary=per_mode_summary,
    )

    out_path = pathlib.Path(args.out)
    json_path = write_evaluation_report(report, out_path / "eval_report.json")

    txt_str = render_evaluation_report(
        metrics, provenance, calibration=calibration, per_mode_summary=per_mode_summary
    )
    txt_path = out_path / "eval_report.txt"
    txt_path.write_text(txt_str, encoding="utf-8")

    # --- 5. Optionally record the calibrated config ----------------------------- #
    if calibration is not None and calibration.best is not None:
        record_calibrated_config(
            cfg, calibration, axes, out_path / "calibrated_config.yaml"
        )

    # --- 6. Summary + exit code -------------------------------------------------- #
    calibration_status = "n/a" if calibration is None else calibration.status
    print(
        f"segfacet evaluate: n_cases={metrics.n_cases} "
        f"fpr={metrics.false_positive_rate} calibration={calibration_status} "
        f"-> {json_path}"
    )
    return 0


def _read_eval_report_json(path: str, label: str) -> dict:
    """Read + parse *path* as a JSON object for ``compare-runs``.

    Raises :class:`segfacet.io.FacetInputError` (never a bare ``OSError``/
    ``json.JSONDecodeError``) with a message naming *label* (``"--run-a"``
    or ``"--run-b"``) on any failure -- a nonexistent path, an unreadable
    file, malformed JSON, or a JSON value that is not an object.
    """
    from segfacet.io import FacetInputError  # noqa: PLC0415

    p = pathlib.Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise FacetInputError(f"compare-runs: cannot read {label} ({p}): {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FacetInputError(
            f"compare-runs: {label} ({p}) is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise FacetInputError(
            f"compare-runs: {label} ({p}) is not a JSON object (mapping)."
        )
    return data


def _rehydrate_per_mode_summary(report: dict, path: str, label: str):
    """Rehydrate a ``RunPerModeSummary`` from *report*'s ``per_mode_magnitude``
    block, raising :class:`segfacet.io.FacetInputError` naming *label* when
    the block is absent or malformed."""
    from segfacet.eval.per_mode_cohort import RunPerModeSummary  # noqa: PLC0415
    from segfacet.io import FacetInputError  # noqa: PLC0415

    block = report.get("per_mode_magnitude")
    if block is None:
        raise FacetInputError(
            f"compare-runs: {label} ({path}) has no 'per_mode_magnitude' block -- "
            "was it written with 'segfacet evaluate --per-mode'?"
        )
    return RunPerModeSummary.from_dict(block)


def _provenance_from_report(report: dict, build_date: str):
    """Build an ``EvaluationProvenance`` for the comparison artifact from one
    side's original evaluation report's ``provenance`` block, restamped with
    *build_date* (the comparator's own, caller-supplied build date -- never
    the wall clock)."""
    from segfacet.eval.report import EvaluationProvenance  # noqa: PLC0415

    prov = report.get("provenance") if isinstance(report.get("provenance"), dict) else {}
    return EvaluationProvenance(
        cohort_id=prov.get("cohort_id", ""),
        cohort_size=prov.get("cohort_size", 0),
        config_version=prov.get("config_version", ""),
        build_date=build_date,
        reference_schema_version=prov.get("reference_schema_version"),
        segfacet_version=prov.get("segfacet_version"),
    )


def _handle_compare_runs(args: argparse.Namespace) -> int:
    """Handler for ``segfacet compare-runs`` (item 101).

    Reads two ``eval_report.json`` files written by ``segfacet evaluate
    --per-mode``, rehydrates their ``per_mode_magnitude`` blocks into
    ``RunPerModeSummary``\\ s, diffs them via
    :func:`segfacet.eval.per_mode_cohort.compare_runs`, and writes
    ``<out>/per_mode_comparison.json`` (schema-validated) +
    ``<out>/per_mode_comparison.txt``. Every failure -- a missing/unreadable
    path, malformed JSON, a report with no ``per_mode_magnitude`` block, or
    mismatched cohorts -- is reported as a clean ``Error:`` message on
    stderr and returns ``1`` without writing any output file; no exception
    escapes this handler.
    """
    from segfacet._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    import dataclasses  # noqa: PLC0415

    from segfacet.eval.per_mode_cohort import compare_runs  # noqa: PLC0415
    from segfacet.eval.report import (  # noqa: PLC0415
        build_run_comparison_report,
        render_run_comparison,
        write_evaluation_report,
    )
    from segfacet.io import FacetInputError  # noqa: PLC0415

    try:
        report_a = _read_eval_report_json(args.run_a, "--run-a")
        report_b = _read_eval_report_json(args.run_b, "--run-b")

        summary_a = _rehydrate_per_mode_summary(report_a, args.run_a, "--run-a")
        summary_b = _rehydrate_per_mode_summary(report_b, args.run_b, "--run-b")

        if args.run_a_id:
            summary_a = dataclasses.replace(summary_a, run_id=args.run_a_id)
        if args.run_b_id:
            summary_b = dataclasses.replace(summary_b, run_id=args.run_b_id)

        comparison = compare_runs(summary_a, summary_b)

        provenance_a = _provenance_from_report(report_a, args.build_date)
        provenance_b = _provenance_from_report(report_b, args.build_date)

        comparison_report = build_run_comparison_report(
            comparison, provenance_a, provenance_b
        )
        txt_str = render_run_comparison(comparison)
    except FacetInputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive: no traceback ever escapes
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    out_path = pathlib.Path(args.out)
    json_path = write_evaluation_report(
        comparison_report, out_path / "per_mode_comparison.json"
    )
    txt_path = out_path / "per_mode_comparison.txt"
    txt_path.write_text(txt_str, encoding="utf-8")

    print(comparison.summary())
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
