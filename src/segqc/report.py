"""JSON report serializer for the segqc QC verdict model (item 009).

Converts a :class:`~segqc.verdict.Verdict` plus case metadata and heuristic
config into a versioned, schema-validated JSON report dict.

Public API
----------
``serialize_report(verdict, case_id, config) -> dict``
    Build and validate the v0 report dict.
``serialize_report_json(verdict, case_id, config, indent=2) -> str``
    Convenience wrapper returning the report as a JSON string.

The JSON schema is loaded once at import time from the package data file
``report_schema_v0.json`` and cached in the module-level ``_SCHEMA`` constant.

Design decisions (item 009)
----------------------------
1. **Schema loaded via ``importlib.resources``** (Python 3.9+) so the path is
   correct both when running from the source tree and after installation.
2. **Schema validation on every ``serialize_report`` call** — catches any
   implementation drift immediately. A future ``validate=False`` flag can skip
   this for hot paths.
3. **``per_label`` keys are strings** — JSON objects only support string keys;
   integer label values are converted via ``str(label_int)``.
4. **``labels`` lists are sorted** — ``frozenset`` iteration order is
   unspecified, so sorted output ensures determinism across runs.
5. **No heavy imports at module level** — ``jsonschema`` is the only
   third-party import; NumPy, NiBabel, SciPy, etc. are not imported.
"""

from __future__ import annotations

import importlib.resources as _pkg_resources
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from segqc.config import HeuristicConfig
    from segqc.verdict import Reason, Verdict

__all__ = ["serialize_report", "serialize_report_json"]

# --------------------------------------------------------------------------- #
# Module-level schema cache
# --------------------------------------------------------------------------- #

# Load and parse the JSON schema once at import time. The schema file lives
# alongside this module inside the segqc package, accessed via importlib.resources.
def _load_schema() -> dict:
    import segqc as _segqc_pkg  # local import to avoid circular deps at module level
    ref = _pkg_resources.files(_segqc_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA: dict = _load_schema()

# Report schema version discriminator — always "0.1" for v0.
_REPORT_SCHEMA_VERSION = "0.1"


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _serialize_reason(reason: "Reason") -> dict:
    """Convert a single :class:`~segqc.verdict.Reason` to a serializable dict.

    Parameters
    ----------
    reason:
        The reason to serialize.

    Returns
    -------
    dict
        ``{"message": str, "severity": str, "labels": list[int]}``.
        ``labels`` is sorted in ascending order.
    """
    return {
        "message": reason.message,
        "severity": reason.severity.label,
        "labels": sorted(reason.labels),
    }


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def serialize_report(
    verdict: "Verdict",
    case_id: str,
    config: "HeuristicConfig",
    features: "dict | None" = None,
) -> dict:
    """Serialize a :class:`~segqc.verdict.Verdict` to a v0 report dict.

    Builds the full report dict, validates it against the v0 JSON schema, and
    returns it. Raises :exc:`ValueError` if ``case_id`` is empty.

    Parameters
    ----------
    verdict:
        The QC verdict to serialize.
    case_id:
        Non-empty string identifier for the case (scan).
    config:
        The :class:`~segqc.config.HeuristicConfig` whose ``schema_version``
        is embedded in the report as ``config_version`` for reproducibility.
    features:
        Optional Stage 2 ``features`` block (see
        :func:`segqc.feature_report.build_features_block`). When non-``None`` it
        is embedded under the report's ``features`` key and validated together
        with the rest of the report. When ``None`` (default) no ``features`` key
        is emitted and the report is exactly the item-009 shape, preserving
        backward compatibility.

    Returns
    -------
    dict
        A plain Python dict conforming to the v0 report schema. The dict is a
        fresh object on every call — mutating it does not affect ``verdict`` or
        subsequent calls.

    Raises
    ------
    ValueError
        If ``case_id`` is an empty string.
    jsonschema.ValidationError
        If the produced report dict does not conform to the v0 schema. This
        should never happen in normal use and indicates a serializer bug.
    """
    import jsonschema  # lazy: only imported when actually serializing

    if not case_id:
        raise ValueError("case_id must be a non-empty string")

    report = {
        "schema_version": _REPORT_SCHEMA_VERSION,
        "config_version": config.schema_version,
        "case_id": case_id,
        "verdict": verdict.overall.label,
        "reasons": [_serialize_reason(r) for r in verdict.reasons],
        "per_label": {
            str(label): [_serialize_reason(r) for r in reasons]
            for label, reasons in verdict.per_label.items()
        },
    }

    # Optional Stage 2 features block — added before validation so it is
    # schema-checked too. Omitting it keeps the item-009 report shape intact.
    if features is not None:
        report["features"] = features

    jsonschema.validate(report, _SCHEMA)
    return report


def serialize_report_json(
    verdict: "Verdict",
    case_id: str,
    config: "HeuristicConfig",
    indent: int = 2,
    features: "dict | None" = None,
) -> str:
    """Serialize a :class:`~segqc.verdict.Verdict` to a JSON string.

    Convenience wrapper around :func:`serialize_report`. The returned string
    is parseable with :func:`json.loads` and equal (after parsing) to the dict
    returned by :func:`serialize_report` for the same inputs.

    Parameters
    ----------
    verdict:
        The QC verdict to serialize.
    case_id:
        Non-empty string identifier for the case (scan).
    config:
        The :class:`~segqc.config.HeuristicConfig` to embed as ``config_version``.
    indent:
        JSON indentation width (default ``2``). Pass ``0`` for compact output.
    features:
        Optional Stage 2 ``features`` block, forwarded to
        :func:`serialize_report`.

    Returns
    -------
    str
        Serialized JSON string.
    """
    report = serialize_report(verdict, case_id, config, features=features)
    return json.dumps(report, indent=indent)
