"""Hand-written, feature-value-free report-format fixture (item 126).

Item 126 retired the two committed whole-record report snapshots this
package's ``016_``/``022_`` items (016, 022) used to compare against, one
per module, that used to pin ``serialize_report_json``'s output shape --
key order, key set, and float rendering. Both snapshots were built from
real extractor output, so every regeneration risked two unrelated failure
modes: a ~1-ULP float drift from a numeric change, or invalidation by a
feature retune. Neither failure mode says anything about the thing the
snapshot was actually meant to guard: the *serialisation format*.

This module is their replacement, and is the one and only source of the
committed ``tests/golden/report_format_contract.json`` fixture. Every value
below is a **literal** -- never computed from a NIfTI fixture or an
extractor -- so the fixture text can drift only if ``serialize_report``'s
key order, key set, or float rendering actually changes.

``format_contract_inputs()`` returns a hand-written verdict, case_id,
config and Stage-2+3 features block (schema-valid against
``report_schema_v0.json``'s ``features``/``stage3`` definitions) plus a
findings list, exercising both ``test_016_features_json.py`` and
``test_022_stage3_serialisation.py``'s surface with one shared fixture.
``format_contract_text()`` serialises those inputs the same way
``serialize_report_json`` does for any other report.

Regenerate the committed fixture (never from a test -- see item 111's
write-and-skip prohibition, carried forward by item 126 AC11) with:

    .venv/bin/python -m tests.report_format_fixture

which writes ``tests/golden/report_format_contract.json`` via
``write_bytes`` so line endings are exactly ``\\n`` (pinned ``eol=lf`` in
``.gitattributes``).
"""

from __future__ import annotations

from pathlib import Path

from segfacet.config import default_config
from segfacet.report import serialize_report_json
from segfacet.verdict import Reason, Severity, Verdict

__all__ = ["format_contract_inputs", "format_contract_text"]

#: Where the committed fixture lives, relative to this module's directory.
GOLDEN_PATH = Path(__file__).parent / "golden" / "report_format_contract.json"

#: Float literals chosen to exercise every JSON-number rendering shape:
#: an integral value, a long non-terminating decimal, a negative value, and
#: a near-zero exponent-form value. Deliberately distinct from any value a
#: real extractor would plausibly emit (see item 126's "floats don't leak
#: into a fresh report" adversarial test).
_INTEGRAL_FLOAT = 1.0
_LONG_DECIMAL_FLOAT = 106.98418277680141
_NEGATIVE_FLOAT = -2.5
_NEAR_ZERO_FLOAT = 1e-12


def format_contract_inputs() -> dict:
    """Hand-written, schema-valid inputs to ``serialize_report_json``.

    Returns a dict with keys ``verdict``, ``case_id``, ``config``,
    ``features`` and ``findings`` -- every value a literal. The ``features``
    block carries one ``per_label`` entry (geometry/components/centroid),
    one overlap pair, a ``relationships`` block, and a full ``stage3``
    sub-block (one offset entry, one orientation entry, curvature,
    spacing_consistency, monotonic_consistency) so it exercises both
    ``test_016`` (Stage 2 shape) and ``test_022`` (Stage 3 shape).
    """
    verdict = Verdict.build(
        reasons=[
            Reason(message="format-contract case-level reason", severity=Severity.PASS, labels=frozenset()),
        ],
        per_label={
            7: [
                Reason(
                    message="format-contract per-label reason",
                    severity=Severity.FLAG,
                    labels=frozenset({7}),
                ),
            ],
        },
    )

    geometry = {
        "voxel_count": 42,
        "physical_volume_mm3": _LONG_DECIMAL_FLOAT,
        "extent_x_mm": _INTEGRAL_FLOAT,
        "extent_y_mm": _NEGATIVE_FLOAT,
        "extent_z_mm": _NEAR_ZERO_FLOAT,
        "bbox_voxel": {
            "x_min": 0.0, "x_max": 6.0,
            "y_min": 0.0, "y_max": 6.0,
            "z_min": 0.0, "z_max": 6.0,
        },
        "bbox_physical": {
            "x_min": 0.0, "x_max": 12.0,
            "y_min": 0.0, "y_max": 12.0,
            "z_min": 0.0, "z_max": 12.0,
        },
        "touches_inferior": False,
        "touches_superior": True,
        "touches_left": False,
        "touches_right": False,
        "touches_anterior": False,
        "touches_posterior": False,
    }
    components = {
        "component_count": 1,
        "component_sizes": [42],
        "component_volumes_mm3": [_LONG_DECIMAL_FLOAT],
        "largest_component_fraction": _INTEGRAL_FLOAT,
        "small_fragments": [],
        "fragmentation_index": _INTEGRAL_FLOAT,
        "stray_component_count": 0,
        "stray_component_sizes": [],
        "stray_volume_mm3": 0.0,
        "stray_volume_fraction": 0.0,
    }
    centroid = {
        "centroid_voxel": [3.0, 3.0, 3.0],
        "centroid_mm": [6.0, 6.0, _NEAR_ZERO_FLOAT],
    }

    features = {
        "features_version": "0.2",
        "per_label": {
            "7": {
                "label": 7,
                "level_name": "L3",
                "geometry": geometry,
                "components": components,
                "centroid": centroid,
            },
        },
        "overlaps": [
            {
                "label_a": 6,
                "label_b": 7,
                "name_a": "L4",
                "name_b": "L3",
                "overlap_voxels": 3,
            },
        ],
        "relationships": {
            "present_levels": ["L4", "L3"],
            "missing_levels": [],
            "neighbour_spacings_mm": [_LONG_DECIMAL_FLOAT],
            "is_continuous": True,
            "out_of_order_labels": [],
        },
        "stage3": {
            "per_label_offsets": [
                {
                    "label": 7,
                    "level_name": "L3",
                    "closest_u": 0.5,
                    "offset_mm": 2.5,  # offset_mm is schema-constrained to >= 0
                    "offset_voxel": _INTEGRAL_FLOAT,
                    "dx_mm": _NEGATIVE_FLOAT,
                    "dy_mm": _NEAR_ZERO_FLOAT,
                    "dz_mm": _LONG_DECIMAL_FLOAT,
                },
            ],
            "per_label_orientations": [
                {
                    "label": 7,
                    "level_name": "L3",
                    "principal_axis": [0.0, 0.0, _INTEGRAL_FLOAT],
                    "eigenvalue_ratio": _LONG_DECIMAL_FLOAT,
                },
            ],
            "curvature": {
                "tangent_angles_deg": [_NEAR_ZERO_FLOAT],
                "inter_tangent_angles_deg": [],
                "total_curvature_deg": _INTEGRAL_FLOAT,
                "coronal_tangent_angles_deg": [_NEGATIVE_FLOAT],
                "sagittal_tangent_angles_deg": [_LONG_DECIMAL_FLOAT],
                "coronal_curvature_deg": _INTEGRAL_FLOAT,
                "sagittal_curvature_deg": 0.0,
                "curvature_plane": "coronal",
            },
            "spacing_consistency": {
                "mean_spacing_mm": _LONG_DECIMAL_FLOAT,
                "cv_spacing": 0.0,
                "spacings_mm": [_LONG_DECIMAL_FLOAT],
                "deviations_mm": [_NEGATIVE_FLOAT],
                "outlier_pairs": [],
            },
            "monotonic_consistency": {
                "is_monotonic": True,
                "non_monotonic_pairs": [],
                "u_values": [0.0, 0.5, _INTEGRAL_FLOAT],
            },
        },
    }

    findings = [
        {
            "rule_id": "format_contract",
            "severity": "flagged-for-review",
            "reason": "format-contract synthetic finding",
            "labels": [7],
        },
    ]

    return {
        "verdict": verdict,
        "case_id": "report-format-contract",
        "config": default_config(),
        "features": features,
        "findings": findings,
    }


def format_contract_text() -> str:
    """``serialize_report_json`` output for :func:`format_contract_inputs`.

    This is exactly the text ``tests/golden/report_format_contract.json``
    commits -- the sole thing that reproduces it is this function.
    """
    inputs = format_contract_inputs()
    return serialize_report_json(
        inputs["verdict"],
        inputs["case_id"],
        inputs["config"],
        features=inputs["features"],
        findings=inputs["findings"],
    )


if __name__ == "__main__":
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_bytes(format_contract_text().encode("utf-8"))
    print(f"Wrote {GOLDEN_PATH}")
