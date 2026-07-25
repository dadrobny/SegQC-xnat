"""Stage-7 evaluation report (JSON + human) and calibrated-config recording
(item 056).

Renders item 054's cohort-level :class:`~segfacet.eval.metrics.CohortMetrics`
and item 055's optional :class:`~segfacet.eval.calibrate.CalibrationResult` into
a versioned, schema-validated JSON report, a stdlib-only plain-text
rendering of the same numbers, and provides the byte-reproducible
persistence mechanism for a chosen calibration's thresholds (written into a
``HeuristicConfig`` YAML file that round-trips through
:func:`segfacet.config.load_config`).

This is the Stage-7 analogue of the Stage-1 per-case report (see
``segfacet.report``/items 009 and ``segfacet.human_report``/item 010): a bundled
versioned JSON schema loaded via ``importlib.resources`` and validated on
every build, plus a stdlib-only deterministic plain-text renderer. It also
follows items 043/045's byte-reproducible artifact-write pattern
(``Path.write_bytes`` on a ``"\\n"``-terminated string, caller-supplied
provenance, no wall clock).

**Artifact-production only.** This module contains no ``segfacet evaluate``
CLI entry point, no cohort assembly, and no new metrics/calibration
mathematics -- it only renders/persists what items 054/055 already computed.
It writes **no** living project-tracking documents (that transcription is
item 057's job at Stage-7 close) and never touches the bundled
``src/segfacet/default_config.yaml``; every write goes to the caller-supplied
``path`` argument only.

Public API
----------
``EvaluationProvenance``
    Frozen dataclass: caller-supplied report identity/reproducibility
    metadata (``cohort_id``, ``cohort_size``, ``config_version``,
    ``build_date``, optional ``reference_schema_version``/``segfacet_version``).
``build_evaluation_report(metrics, provenance, *, calibration=None) -> dict``
    Assemble + schema-validate the report dict.
``serialize_evaluation_report_json(report, indent=2) -> str``
    Deterministic JSON string (sorted keys).
``write_evaluation_report(report, path) -> Path``
    Byte-reproducible JSON write (``Path.write_bytes``, single trailing
    ``"\\n"``).
``render_evaluation_report(metrics, provenance, *, calibration=None) -> str``
    Stdlib-only plain-text rendering of the same numbers.
``record_calibrated_config(base_config, calibration_result, axes, path) -> Path``
    Apply a calibration's chosen assignment onto a config and write it as a
    byte-reproducible YAML file that round-trips through ``load_config``.

Dependencies: :mod:`segfacet.eval.metrics` (item 054), :mod:`segfacet.eval.calibrate`
(item 055), :mod:`segfacet.config` (items 005/035), ``jsonschema``, ``PyYAML``.
"""

from __future__ import annotations

import importlib.resources as _pkg_resources
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Union

from segfacet.io import FacetInputError

from .calibrate import apply_assignment

if TYPE_CHECKING:  # pragma: no cover - typing only
    from segfacet.config import HeuristicConfig
    from segfacet.eval.calibrate import CalibrationResult, ThresholdAxis
    from segfacet.eval.metrics import CohortMetrics

__all__ = [
    "EVAL_REPORT_SCHEMA_VERSION",
    "EvaluationProvenance",
    "build_evaluation_report",
    "serialize_evaluation_report_json",
    "write_evaluation_report",
    "render_evaluation_report",
    "record_calibrated_config",
]

# --------------------------------------------------------------------------- #
# Module-level schema cache
# --------------------------------------------------------------------------- #


def _load_eval_schema() -> dict:
    """Load and parse ``eval_report_schema_v0.json`` via ``importlib.resources``
    (mirrors ``segfacet.report._load_schema``)."""
    import segfacet.eval as _eval_pkg  # local import to avoid circular deps at module level

    ref = _pkg_resources.files(_eval_pkg).joinpath("eval_report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA: dict = _load_eval_schema()

#: Evaluation-report schema version discriminator -- always "0.1" for v0.
EVAL_REPORT_SCHEMA_VERSION: str = "0.1"


# --------------------------------------------------------------------------- #
# EvaluationProvenance
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvaluationProvenance:
    """Caller-supplied evaluation-report identity/reproducibility metadata.

    Every field is caller-supplied -- this module performs no system-time
    lookups of any kind, so identical inputs always produce byte-identical
    reports.

    Attributes
    ----------
    cohort_id:
        Free-text identifier for the evaluated cohort.
    cohort_size:
        Number of cases in the cohort. Callers should pass
        ``metrics.n_cases`` for consistency (checked by AC4's caller
        contract, not enforced here).
    config_version:
        The ``HeuristicConfig.schema_version`` that produced the metrics.
    build_date:
        Caller-supplied ISO ``"YYYY-MM-DD"`` string.
    reference_schema_version:
        Optional schema_version of the reference distribution used, if any.
    segfacet_version:
        Optional segfacet package version string.
    """

    cohort_id: str
    cohort_size: int
    config_version: str
    build_date: str
    reference_schema_version: Optional[str] = None
    segfacet_version: Optional[str] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict for this provenance block."""
        return {
            "cohort_id": self.cohort_id,
            "cohort_size": self.cohort_size,
            "config_version": self.config_version,
            "build_date": self.build_date,
            "reference_schema_version": self.reference_schema_version,
            "segfacet_version": self.segfacet_version,
        }


# --------------------------------------------------------------------------- #
# Calibration summary (internal)
# --------------------------------------------------------------------------- #


def _calibration_block(calibration: "CalibrationResult") -> dict:
    """Reduce a :class:`~segfacet.eval.calibrate.CalibrationResult` to the
    focused ``calibration`` report block: ``status``, ``objective``, and the
    chosen ``best`` candidate's assignment + achieved metrics (not the full
    per-candidate sweep)."""
    best = calibration.best
    return {
        "status": calibration.status,
        "objective": {"sensitivity_floor": calibration.objective.sensitivity_floor},
        "best": (
            None
            if best is None
            else {
                "assignment": dict(best.assignment),
                "metrics": best.metrics.to_dict(),
            }
        ),
    }


# --------------------------------------------------------------------------- #
# build_evaluation_report
# --------------------------------------------------------------------------- #


def build_evaluation_report(
    metrics: "CohortMetrics",
    provenance: EvaluationProvenance,
    *,
    calibration: "Optional[CalibrationResult]" = None,
) -> dict:
    """Assemble + schema-validate the v0 evaluation-report dict.

    Parameters
    ----------
    metrics:
        The :class:`~segfacet.eval.metrics.CohortMetrics` to embed verbatim
        (via ``metrics.to_dict()``) under ``"metrics"``.
    provenance:
        The :class:`EvaluationProvenance` to embed (via ``to_dict()``) under
        ``"provenance"``.
    calibration:
        Optional :class:`~segfacet.eval.calibrate.CalibrationResult`. When
        given, a focused ``"calibration"`` summary block is added. When
        ``None`` (default), no ``"calibration"`` key is emitted.

    Returns
    -------
    dict
        A fresh, schema-valid report dict.

    Raises
    ------
    jsonschema.ValidationError
        If the assembled report does not conform to the bundled v0 schema
        (should never happen in normal use -- indicates a serialiser bug).
    """
    import jsonschema  # lazy: only imported when actually building

    report: dict = {
        "schema_version": EVAL_REPORT_SCHEMA_VERSION,
        "provenance": provenance.to_dict(),
        "metrics": metrics.to_dict(),
    }

    if calibration is not None:
        report["calibration"] = _calibration_block(calibration)

    jsonschema.validate(report, _SCHEMA)
    return report


# --------------------------------------------------------------------------- #
# JSON serialisation / writing
# --------------------------------------------------------------------------- #


def serialize_evaluation_report_json(report: dict, indent: int = 2) -> str:
    """Return a deterministic JSON string for *report* (sorted keys).

    Repeated calls on the same input yield the identical string.
    """
    return json.dumps(report, indent=indent, sort_keys=True)


def write_evaluation_report(report: dict, path: Union[str, "os.PathLike"]) -> Path:
    """Write *report* to *path* as UTF-8 bytes ending in exactly one
    ``"\\n"`` (``Path.write_bytes``, **not** ``write_text`` -- mirrors
    ``segfacet.reference.artifact.write_artifact``).

    Creates parent directories as needed. Returns the written path.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = serialize_evaluation_report_json(report)
    out_path.write_bytes((text + "\n").encode("utf-8"))
    return out_path


# --------------------------------------------------------------------------- #
# Human-readable rendering
# --------------------------------------------------------------------------- #


def _fmt_metric(value: "Optional[float]") -> str:
    """Format a metric value for the human renderer: ``None`` -> ``"n/a"``,
    otherwise a fixed-precision decimal string. Never emits the literal
    string ``"None"``."""
    if value is None:
        return "n/a"
    return f"{value:.4f}"


def render_evaluation_report(
    metrics: "CohortMetrics",
    provenance: EvaluationProvenance,
    *,
    calibration: "Optional[CalibrationResult]" = None,
) -> str:
    """Render a human-readable plain-text evaluation report.

    Stdlib-only, deterministic (same discipline as
    ``segfacet.human_report.render_human_report``): every value is formatted
    explicitly, so the output contains no raw Python class names, dataclass
    ``repr()``, tuples, or enum reprs. ``None`` metric sentinels (item 054's
    documented no-expected-pass-cases / zero-variance-correlation cases)
    render as ``"n/a"``, never the literal string ``"None"``.

    Parameters
    ----------
    metrics:
        The :class:`~segfacet.eval.metrics.CohortMetrics` to render.
    provenance:
        The :class:`EvaluationProvenance` to render.
    calibration:
        Optional :class:`~segfacet.eval.calibrate.CalibrationResult`. When
        ``None`` (default), a "(not calibrated)" marker is rendered instead
        of a calibration block.

    Returns
    -------
    str
        A non-empty plain-text report string.
    """
    lines: list = []

    title = f"FACET Evaluation Report -- {provenance.cohort_id}"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append(f"Cohort size: {provenance.cohort_size}")
    lines.append(f"Config version: {provenance.config_version}")
    lines.append(f"Build date: {provenance.build_date}")
    lines.append("")

    lines.append("Overall metrics:")
    lines.append(f"  False positive rate (FPR) on GT: {_fmt_metric(metrics.false_positive_rate)}")
    lines.append(f"  Sensitivity (overall):           {_fmt_metric(metrics.sensitivity)}")
    lines.append(f"  Specificity:                     {_fmt_metric(metrics.specificity)}")
    lines.append("")

    lines.append("Sensitivity per failure mode:")
    if metrics.per_mode:
        for mode in metrics.per_mode:
            if mode.failure_mode_name is not None:
                mode_label = mode.failure_mode_name
            elif mode.failure_mode is not None:
                mode_label = f"mode {mode.failure_mode}"
            else:
                mode_label = "(unspecified)"
            lines.append(
                f"  {mode_label}: n_cases={mode.n_cases}, "
                f"caught_by_designated_rule={mode.n_caught_by_designated_rule}, "
                f"sensitivity={_fmt_metric(mode.sensitivity)}"
            )
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Correlations:")
    dvf = metrics.dice_vs_flag
    fvf = metrics.feature_divergence_vs_flag
    lines.append(
        f"  DICE vs flag ({dvf.method}): coefficient={_fmt_metric(dvf.coefficient)}, n={dvf.n}"
    )
    lines.append(
        f"  Feature divergence vs flag ({fvf.method}): "
        f"coefficient={_fmt_metric(fvf.coefficient)}, n={fvf.n}"
    )
    lines.append("")

    lines.append("Calibration:")
    if calibration is None:
        lines.append("  (not calibrated)")
    else:
        lines.append(f"  Status: {calibration.status}")
        lines.append(
            f"  Objective sensitivity floor: {_fmt_metric(calibration.objective.sensitivity_floor)}"
        )
        best = calibration.best
        if best is None:
            lines.append("  Chosen assignment: (none -- no feasible setting)")
        else:
            assignment_txt = ", ".join(
                f"{key}={value}" for key, value in sorted(best.assignment.items())
            )
            lines.append(f"  Chosen assignment: {assignment_txt}")
            lines.append(f"  Achieved FPR: {_fmt_metric(best.metrics.false_positive_rate)}")
            lines.append(f"  Achieved sensitivity: {_fmt_metric(best.metrics.sensitivity)}")
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# record_calibrated_config
# --------------------------------------------------------------------------- #


def record_calibrated_config(
    base_config: "HeuristicConfig",
    calibration_result: "CalibrationResult",
    axes: "Sequence[ThresholdAxis]",
    path: Union[str, "os.PathLike"],
) -> Path:
    """Apply *calibration_result*'s chosen assignment onto *base_config* and
    write it as a byte-reproducible YAML file at *path*.

    Parameters
    ----------
    base_config:
        The config the chosen assignment is applied onto. Not mutated.
    calibration_result:
        The :class:`~segfacet.eval.calibrate.CalibrationResult` whose ``best``
        candidate's assignment is applied.
    axes:
        The :class:`~segfacet.eval.calibrate.ThresholdAxis` sequence whose
        ``(rule_id, param_path)`` addressing resolves the assignment (the
        same ``axes`` passed to ``apply_assignment``). Not mutated.
    path:
        Destination path for the written YAML config. This is the **only**
        path ever written -- the bundled ``default_config.yaml`` is never
        touched.

    Returns
    -------
    Path
        *path*, after the file has been written.

    Raises
    ------
    segfacet.io.FacetInputError
        If ``calibration_result.best is None`` (no feasible setting) --
        raised before any file is written, rather than applying a ``None``
        assignment or writing a degenerate config.
    """
    if calibration_result.best is None:
        raise FacetInputError(
            "record_calibrated_config: calibration_result.best is None "
            f"(status={calibration_result.status!r}); there is no feasible "
            "calibrated setting to record."
        )

    import yaml  # lazy import: only needed when actually recording

    applied = apply_assignment(base_config, calibration_result.best.assignment, axes)

    mapping = {
        "schema_version": applied.schema_version,
        "min_foreground_voxels": applied.min_foreground_voxels,
        "min_label_count": applied.min_label_count,
        "min_fragment_voxels": applied.min_fragment_voxels,
        "rules": applied.rules,
        "verdict": applied.verdict,
        "reference": applied.reference,
    }

    text = yaml.safe_dump(mapping, sort_keys=True, default_flow_style=False)
    text = text.rstrip("\n") + "\n"

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(text.encode("utf-8"))
    return out_path
