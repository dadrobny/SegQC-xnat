"""JSON report serializer for the segfacet QC verdict model (item 009).

Converts a :class:`~segfacet.verdict.Verdict` plus case metadata and heuristic
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
    from segfacet.config import HeuristicConfig
    from segfacet.verdict import Reason, Verdict

__all__ = ["serialize_report", "serialize_report_json"]

# --------------------------------------------------------------------------- #
# Module-level schema cache
# --------------------------------------------------------------------------- #

# Load and parse the JSON schema once at import time. The schema file lives
# alongside this module inside the segfacet package, accessed via importlib.resources.
def _load_schema() -> dict:
    import segfacet as _segfacet_pkg  # local import to avoid circular deps at module level
    ref = _pkg_resources.files(_segfacet_pkg).joinpath("report_schema_v0.json")
    return json.loads(ref.read_text(encoding="utf-8"))


_SCHEMA: dict = _load_schema()

# Report schema version discriminator — always "0.1" for v0.
_REPORT_SCHEMA_VERSION = "0.1"


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _serialize_reason(reason: "Reason") -> dict:
    """Convert a single :class:`~segfacet.verdict.Reason` to a serializable dict.

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
    findings: "list | None" = None,
    reference_delta: "dict | None" = None,
    image_features: "dict | None" = None,
    run_manifest: "dict | None" = None,
) -> dict:
    """Serialize a :class:`~segfacet.verdict.Verdict` to a v0 report dict.

    Builds the full report dict, validates it against the v0 JSON schema, and
    returns it. Raises :exc:`ValueError` if ``case_id`` is empty.

    Parameters
    ----------
    verdict:
        The QC verdict to serialize.
    case_id:
        Non-empty string identifier for the case (scan).
    config:
        The :class:`~segfacet.config.HeuristicConfig` whose ``schema_version``
        is embedded in the report as ``config_version`` for reproducibility.
    features:
        Optional Stage 2 ``features`` block (see
        :func:`segfacet.feature_report.build_features_block`). When non-``None`` it
        is embedded under the report's ``features`` key and validated together
        with the rest of the report. When ``None`` (default) no ``features`` key
        is emitted and the report is exactly the item-009 shape, preserving
        backward compatibility.
    findings:
        Optional Stage 4 ``findings`` list (item 035) -- a list of dicts as
        produced by ``segfacet.heuristics.finding.Finding.to_dict()``. When
        non-``None`` (including an empty list) it is embedded verbatim under
        the report's ``findings`` key and validated together with the rest of
        the report. When ``None`` (default) no ``findings`` key is emitted,
        preserving the item-009/016 report shape.
    reference_delta:
        Optional Stage 6 ``reference_delta`` block (item 046), as produced by
        ``segfacet.reference.reference_delta_to_dict``. When non-``None`` it is
        embedded verbatim under the report's ``reference_delta`` key and
        validated together with the rest of the report. When ``None``
        (default) no ``reference_delta`` key is emitted, preserving every
        prior report shape (including the Stage 5 golden snapshots).
    image_features:
        Optional Stage 8 ``image_features`` block (item 061), as produced by
        ``segfacet.feature_report.build_image_features_block``. When non-``None``
        it is embedded verbatim under the report's ``image_features`` key and
        validated together with the rest of the report. When ``None``
        (default) no ``image_features`` key is emitted, preserving every
        prior report shape (including the item-042 golden snapshots).
    run_manifest:
        Optional run-manifest provenance block (item 096), as produced by
        ``segfacet.run_manifest.build_run_manifest(...).to_dict()``. When
        non-``None`` it is embedded verbatim under the report's
        ``run_manifest`` key and validated together with the rest of the
        report. When ``None`` (default) no ``run_manifest`` key is emitted,
        preserving every prior report shape.

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

    # Optional Stage 4 findings block (item 035) — added before validation for
    # the same reason. Omitting it (None) keeps the prior report shape intact.
    if findings is not None:
        report["findings"] = findings

    # Optional Stage 6 reference_delta block (item 046) -- added before
    # validation for the same reason. Omitting it (None) keeps the prior
    # report shape intact.
    if reference_delta is not None:
        report["reference_delta"] = reference_delta

    # Optional Stage 8 image_features block (item 061) -- added before
    # validation for the same reason. Omitting it (None) keeps the prior
    # report shape intact.
    if image_features is not None:
        report["image_features"] = image_features

    # Optional Stage 17 run_manifest block (item 096) -- added before
    # validation for the same reason. Omitting it (None) keeps the prior
    # report shape intact.
    if run_manifest is not None:
        report["run_manifest"] = run_manifest

    jsonschema.validate(report, _SCHEMA)
    return report


def serialize_report_json(
    verdict: "Verdict",
    case_id: str,
    config: "HeuristicConfig",
    indent: int = 2,
    features: "dict | None" = None,
    findings: "list | None" = None,
    reference_delta: "dict | None" = None,
    image_features: "dict | None" = None,
    run_manifest: "dict | None" = None,
) -> str:
    """Serialize a :class:`~segfacet.verdict.Verdict` to a JSON string.

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
        The :class:`~segfacet.config.HeuristicConfig` to embed as ``config_version``.
    indent:
        JSON indentation width (default ``2``). Pass ``0`` for compact output.
    features:
        Optional Stage 2 ``features`` block, forwarded to
        :func:`serialize_report`.
    findings:
        Optional Stage 4 ``findings`` list (item 035), forwarded to
        :func:`serialize_report`.
    reference_delta:
        Optional Stage 6 ``reference_delta`` block (item 046), forwarded to
        :func:`serialize_report`.
    image_features:
        Optional Stage 8 ``image_features`` block (item 061), forwarded to
        :func:`serialize_report`.
    run_manifest:
        Optional run-manifest provenance block (item 096), forwarded to
        :func:`serialize_report`.

    Returns
    -------
    str
        Serialized JSON string.
    """
    report = serialize_report(
        verdict,
        case_id,
        config,
        features=features,
        findings=findings,
        reference_delta=reference_delta,
        image_features=image_features,
        run_manifest=run_manifest,
    )
    return json.dumps(report, indent=indent)
