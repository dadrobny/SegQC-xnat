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
    """Eagerly validate/resolve ``--backend`` and wire it into ``SEGQC_BACKEND``.

    Called near the top of each ``_handle_*`` handler, before any input is
    loaded, so a forced-but-unavailable GPU (or an invalid ambient
    ``SEGQC_BACKEND``) fails fast with a clean ``Error:`` message rather than
    a mid-pipeline traceback (item 075, AC3/AC5).

    When ``--backend`` was explicitly given, resolves it via
    :func:`segqc.backend.get_backend` and, on success, sets
    ``os.environ["SEGQC_BACKEND"]`` to the given token so the unmodified
    compute entry points (which auto-resolve ``backend=None -> get_backend()``
    per item 072) pick it up (AC4). When the flag was omitted, the ambient
    environment (or the ``auto`` default) governs untouched (AC6/AC7).

    Returns:
        An exit code (``1``) if backend resolution failed, else ``None`` to
        signal the caller should continue.
    """
    from segqc.backend import SegQCBackendError, get_backend  # noqa: PLC0415

    tok = getattr(args, "backend", None)
    try:
        get_backend(override=tok)
    except SegQCBackendError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if tok is not None:
        os.environ["SEGQC_BACKEND"] = tok

    return None


_DATASET_SCHEMA_HELP = (
    "Path to a declarative dataset descriptor (YAML/JSON, segqc.datasets) "
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


def _resolve_cohort_from_args(args: argparse.Namespace, *, role: "Optional[str]" = None):
    """Resolve a :class:`segqc.datasets.Cohort` from ``--dataset-schema`` /
    ``--data-root`` / ``--subset``, or ``None`` when ``--dataset-schema`` was not
    given. Raises ``DatasetSchemaError`` (caught by handlers) on any descriptor
    or resolution problem."""
    if not getattr(args, "dataset_schema", None):
        return None
    from segqc.datasets import load_descriptor, resolve  # noqa: PLC0415

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
            "Log level for the segqc logger hierarchy "
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
            "TotalSegmentator-vs-GT cohort -- see segqc.eval.cohort for the "
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
        help="Path to an evaluation-cohort manifest JSON (segqc.eval.cohort). "
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
            "Log level for the segqc logger hierarchy "
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
    _add_dataset_schema_args(evaluate_parser)
    evaluate_parser.set_defaults(handler=_handle_evaluate)

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
    """Batch ``segqc run`` over a dataset adapter (Stage 13, item 087).

    Resolves the ``--dataset-schema`` cohort and runs the single-case handler on
    each case (reusing all of :func:`_handle_run`'s logic) into
    ``<out>/<case_id>/``. Returns the worst per-case exit code (0 only if every
    case passed / was flagged); a single bad case does not abort the batch.
    """
    import copy  # noqa: PLC0415

    from segqc.datasets import DatasetSchemaError  # noqa: PLC0415

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
        f"segqc run (batch): {len(cohort)} case(s), {n_nonpass} non-pass/error "
        f"-> {out_root}"
    )
    return worst


def _handle_run(args: argparse.Namespace) -> int:
    """Handler for ``segqc run`` — full Stage 1 + Stage 4 pipeline (item 035).

    Loads the scan and segmentation, runs the empty/near-empty check, then
    extracts the Stage 2/3 feature block and runs the Stage 4 rule engine over
    it (:func:`segqc.pipeline.run_qc`), threading the empty-check's reasons in
    as case-level ``base_reasons`` so the aggregated verdict reflects both.
    When ``--intensity`` (or config ``intensity.enabled``) is set, dispatches
    to :func:`segqc.pipeline.run_qc_with_intensity` instead (item 065),
    additionally computing per-label intensity/radiomics features and
    embedding an ``image_features`` block in both reports. Writes a JSON
    report (:func:`segqc.report.serialize_report_json`, carrying ``features``
    + ``findings`` and, in intensity mode, ``image_features``) and a
    human-readable plain-text report
    (:func:`segqc.human_report.render_human_report`, carrying a Findings
    section and, in intensity mode, an Intensity features section) to
    ``<out>/segqc_report.json`` and ``<out>/segqc_report.txt`` respectively.

    Returns 0 on pass or flagged-for-review; returns 1 on fail, input/config
    error, or (in intensity mode) a scan<->seg grid-alignment error. Both
    report files are always written before the process exits on a successful
    run (even on an aggregated fail); no report is written when the config,
    input, or grid alignment fails.
    """
    # Set up logging first so any subsequent log messages respect the level.
    from segqc._logging import setup_logging  # noqa: PLC0415

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

    from segqc.io import SegQCInputError, load_case  # noqa: PLC0415
    from segqc.labels import LabelConvention, summarise_inventory  # noqa: PLC0415
    from segqc.config import (  # noqa: PLC0415
        SegQCConfigError,
        bundled_default_config,
        load_config,
    )
    from segqc.empty import check_empty  # noqa: PLC0415
    from segqc.verdict import Reason, Severity  # noqa: PLC0415
    from segqc.report import serialize_report_json  # noqa: PLC0415
    from segqc.human_report import render_human_report  # noqa: PLC0415
    from segqc.pipeline import (  # noqa: PLC0415
        run_qc,
        run_qc_with_intensity,
        run_qc_with_reference,
    )

    logger.debug(
        "segqc run: scan=%r  seg=%r  out=%r  config=%r",
        args.scan, args.seg, args.out, args.config,
    )

    # --- 0. Load config (bundled default, or --config override) -------------- #
    if args.config:
        try:
            cfg = load_config(args.config)
        except SegQCConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        cfg = bundled_default_config()

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
        from segqc.reference import (  # noqa: PLC0415
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
    )
    json_path = out_path / "segqc_report.json"
    json_path.write_text(json_str, encoding="utf-8")

    txt_str = render_human_report(
        verdict,
        case_id,
        cfg,
        findings=case_result.findings,
        image_features=image_features,
    )
    txt_path = out_path / "segqc_report.txt"
    txt_path.write_text(txt_str, encoding="utf-8")

    logger.info(
        "segqc run complete -- verdict=%s  json=%s  txt=%s",
        verdict.overall.label, json_path, txt_path,
    )

    # --- 8. Exit code --------------------------------------------------------- #
    # fail → 1; pass or flagged-for-review → 0 (from the aggregated verdict).
    if verdict.overall == Severity.FAIL:
        return 1
    return 0


def _handle_build_reference(args: argparse.Namespace) -> int:
    """Handler for ``segqc build-reference`` (item 045).

    Loads the config (bundled default or ``--config``), calls
    :func:`segqc.reference.build_reference` then
    :func:`segqc.reference.write_artifact`, prints the written path, and
    returns 0. Returns 1 (writing no ``--out`` file) on a bad ``--config``
    or a cohort-ingestion error (e.g. a nonexistent ``--cohort`` directory) --
    a caller error is reported, not a traceback.
    """
    from segqc.config import SegQCConfigError, bundled_default_config, load_config
    from segqc.datasets import DatasetSchemaError
    from segqc.reference import ReferenceArtifactError
    from segqc.reference.artifact import (
        build_reference,
        build_reference_from_cohort,
        write_artifact,
    )
    from segqc.reference.ingest import DEFAULT_SEG_SUFFIX

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
        except SegQCConfigError as exc:
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
    """Handler for ``segqc evaluate`` (item 057) -- the Stage-7 integration
    entry point.

    Loads the config (bundled default or ``--config``), loads the cohort via
    :func:`segqc.eval.cohort.load_cohort_manifest`, drives
    ``evaluate_cohort -> compute_cohort_metrics`` (items 053/054),
    optionally runs the threshold-calibration loop (``--calibrate``, item
    055), builds + writes the JSON and human-readable evaluation reports
    (item 056), and -- when calibrating and a feasible setting was found --
    records the calibrated config. Returns 1 (writing no report) on a bad
    ``--config`` or a cohort-loading error (e.g. a nonexistent ``--cohort``
    path) -- a caller error is reported, not a traceback.
    """
    from segqc._logging import setup_logging  # noqa: PLC0415

    setup_logging(args.log_level)

    code = _apply_backend_selection(args)
    if code is not None:
        return code

    from segqc.config import (  # noqa: PLC0415
        SegQCConfigError,
        bundled_default_config,
        load_config,
    )
    from segqc.datasets import DatasetSchemaError  # noqa: PLC0415
    from segqc.eval.calibrate import calibrate_thresholds, default_calibration_axes  # noqa: PLC0415
    from segqc.eval.cohort import load_cohort_manifest  # noqa: PLC0415
    from segqc.eval.harness import EvaluationCase, evaluate_cohort  # noqa: PLC0415
    from segqc.eval.metrics import compute_cohort_metrics  # noqa: PLC0415
    from segqc.eval.report import (  # noqa: PLC0415
        EvaluationProvenance,
        build_evaluation_report,
        record_calibrated_config,
        render_evaluation_report,
        write_evaluation_report,
    )
    from segqc.io import SegQCInputError  # noqa: PLC0415

    logger.debug(
        "segqc evaluate: cohort=%r  out=%r  config=%r  calibrate=%r",
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
        except SegQCConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        cfg = bundled_default_config()

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
    except (SegQCInputError, OSError, DatasetSchemaError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --- 2. Drive the harness + metrics --------------------------------------- #
    cohort = evaluate_cohort(cases, cfg)
    metrics = compute_cohort_metrics(cohort)

    # --- 3. Optional calibration ----------------------------------------------- #
    if args.calibrate:
        axes = default_calibration_axes()
        calibration = calibrate_thresholds(cases, cfg, axes)
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

    report = build_evaluation_report(metrics, provenance, calibration=calibration)

    out_path = pathlib.Path(args.out)
    json_path = write_evaluation_report(report, out_path / "eval_report.json")

    txt_str = render_evaluation_report(metrics, provenance, calibration=calibration)
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
        f"segqc evaluate: n_cases={metrics.n_cases} "
        f"fpr={metrics.false_positive_rate} calibration={calibration_status} "
        f"-> {json_path}"
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
