"""Delta-to-reference rule family (item 047).

A Stage 4 rule that thresholds item 046's per-vertebra **delta-to-reference**
metrics, read from ``record["reference_delta"]`` (the
``segfacet.reference.reference_delta_to_dict`` shape). It fires a ``Finding``
when a vertebra is out-of-distribution vs the bundled VerSe reference,
realising the vision's §5.4 "delta to reference" rule input.

Scope
-----
This module computes **no** statistic itself — z-score, robust-z,
percentile-rank, out-of-range, and distribution-distance are all already
computed and serialised by item 046. This rule only *thresholds* those
already-computed numbers. It imports nothing from ``segfacet.reference``, loads
no reference artifact, and is stateless / I/O-free, exactly like its Stage 4
siblings (``bounds``, ``fragmentation``, ``coverage``, ``sequence``,
``border``, ``overlap``, ``mislabel``).

It does **not** touch ``segfacet.pipeline``, ``segfacet.cli``, ``segfacet.config``,
``default_config.yaml``, ``segfacet.report``, or ``segfacet.aggregate`` — wiring
the ``reference_delta`` block into the record fed to ``run_rules`` is item
049's remit. Until that wiring lands, ``record.get("reference_delta")`` is
absent by default, so this rule is silently a no-op and existing pipeline
output is unaffected by its addition.

Three independent, config-toggleable firing conditions per available label:

1. **Distribution-distance outlier** (label-level) — fires when
   ``distribution_distance >= max_distribution_distance`` (default ``3.0``).
2. **Out-of-range feature** (per feature) — fires for each feature name in
   the block's ``out_of_range_features`` list.
3. **Robust-z outlier** (per feature) — fires for each feature whose
   ``abs(robust_z) >= max_robust_z`` (default ``3.5``).

A label whose entry is ``available: false`` (or an absent/non-mapping
``reference_delta`` block) contributes no findings — reference-grounded
judgement is silent where there is no reference.

Determinism / non-mutation contract: ``evaluate`` never mutates ``record``,
and two calls with the same ``(record, config)`` return equal finding lists
in the same order. Findings are emitted ascending by integer label; within a
label, in fixed condition order (distribution-distance -> out-of-range ->
robust-z), with per-feature findings in ascending feature-name order.

Targets §6 modes 1 and 2 (spline-offset displacement, and over-/under-
segmentation), declared on analytic grounds (item 137, corrected 2026-09-02)
-- see ``ReferenceDeltaRule.mode_declaration``.
"""

from __future__ import annotations

from typing import Dict, List

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import Rule, RuleModeDeclaration, register_rule
from segfacet.verdict import Severity

__all__ = ["ReferenceDeltaRule"]


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_MAX_ROBUST_Z = 3.5
DEFAULT_MAX_DISTRIBUTION_DISTANCE = 3.0

_OUT_OF_RANGE_TAG = "Reference out-of-range:"
_ROBUST_Z_TAG = "Reference robust-z outlier:"
_DISTANCE_TAG = "Reference distribution-distance outlier:"


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / mislabel.py)
# --------------------------------------------------------------------------- #

_LABEL_TO_SEVERITY: Dict[str, Severity] = {sev.label: sev for sev in Severity}


def _severity_from_param(label: str) -> Severity:
    """Map a severity label string to its ``Severity`` member.

    Raises
    ------
    ValueError
        If *label* is not a recognised ``Severity`` label string.
    """
    sev = _LABEL_TO_SEVERITY.get(label)
    if sev is None:
        known = list(_LABEL_TO_SEVERITY.keys())
        raise ValueError(
            f"Unknown severity label {label!r} in reference_delta rule config. "
            f"Known labels: {known}."
        )
    return sev


# --------------------------------------------------------------------------- #
# ReferenceDeltaRule
# --------------------------------------------------------------------------- #


@register_rule
class ReferenceDeltaRule(Rule):
    """Delta-to-reference rule (item 047).

    Reads ``record["reference_delta"]`` (item 046's
    ``reference_delta_to_dict`` shape) and emits a ``Finding`` per fired
    condition. Returns ``[]`` when the block is absent/non-mapping or every
    available label is in-distribution.
    """

    rule_id = "reference_delta"

    # §6 disposition (item 137, corrected 2026-09-02): declares modes 1 and 2
    # on analytic grounds -- no committed corpus case designates
    # "reference_delta" for any mode, so evidence carries "analytic" plus the
    # mechanism sentence, never "corpus". compute_reference_delta scores
    # every feature the reference artifact tracks
    # (`tracked_features = tuple(sorted(reference.features))`,
    # segfacet/reference/delta.py), not physical_volume_mm3 alone: both
    # committed reference artifacts (reference_verse_v1.json,
    # reference_default.json) track 21 per-label features. That set spans
    # physical_volume_mm3 and extent_{x,y,z}_mm -- the same magnitude
    # features "bounds" targets verbatim (§6 mode 2), here measured against a
    # cohort instead of hand-set bounds -- and also spline_offset_mm, read
    # from stage3.per_label_offsets[].offset_mm, which is §6 mode 1's own
    # anchor path (feature_docs.MODE_ANCHOR_PATHS[1]). A displaced-but-
    # plausibly-sized label can therefore fire this rule on spline_offset_mm
    # alone, a mode-1 detection, so mode 1 is declared alongside mode 2.
    mode_declaration = RuleModeDeclaration(
        modes=(1, 2),
        evidence=(
            "analytic",
            "compute_reference_delta scores every feature the reference "
            "artifact tracks, not a single feature: both committed reference "
            "artifacts carry 21 per-label features, spanning "
            "physical_volume_mm3 and extent_{x,y,z}_mm -- the same §6 mode 2 "
            "magnitude signal 'bounds' targets, measured against a cohort "
            "instead of hand-set bounds -- and spline_offset_mm (from "
            "stage3.per_label_offsets[].offset_mm), which is §6 mode 1's own "
            "anchor feature, so an out-of-distribution verdict on that "
            "feature alone is a mode 1 detection.",
        ),
    )

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate delta-to-reference signals for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["reference_delta"]``.
        config:
            HeuristicConfig instance. Reads ``rules.reference_delta.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings, ascending by integer label; within a
            label, in fixed condition order (distribution-distance ->
            out-of-range -> robust-z), with per-feature findings ascending
            by feature name.

        Raises
        ------
        ValueError
            If ``rules.reference_delta.params.severity`` is an unrecognised
            string (raised before any per-record processing, AC12).
        """
        # Read severity once up-front; raises immediately on a bad string,
        # independently of whether the block is even present (AC12).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        flag_out_of_range = bool(
            config.rule_param(self.rule_id, "flag_out_of_range", default=True)
        )
        flag_robust_z = bool(
            config.rule_param(self.rule_id, "flag_robust_z", default=True)
        )
        flag_distribution_distance = bool(
            config.rule_param(
                self.rule_id, "flag_distribution_distance", default=True
            )
        )
        max_robust_z = float(
            config.rule_param(
                self.rule_id, "max_robust_z", default=DEFAULT_MAX_ROBUST_Z
            )
        )
        max_distribution_distance = float(
            config.rule_param(
                self.rule_id,
                "max_distribution_distance",
                default=DEFAULT_MAX_DISTRIBUTION_DISTANCE,
            )
        )

        block = record.get("reference_delta")
        if not isinstance(block, dict):
            return []

        lower_pct = block.get("lower_pct")
        upper_pct = block.get("upper_pct")

        per_label = block.get("per_label")
        if not isinstance(per_label, dict):
            return []

        normalised = []
        for key, entry in per_label.items():
            if not isinstance(entry, dict):
                continue
            if not entry.get("available"):
                continue
            try:
                label = int(entry.get("label", key))
            except (TypeError, ValueError):
                continue
            normalised.append((label, entry))
        normalised.sort(key=lambda t: t[0])

        findings: List[Finding] = []
        for label, entry in normalised:
            level_name = entry.get("level_name")
            features = entry.get("features")
            if not isinstance(features, dict):
                features = {}

            if flag_distribution_distance:
                distance = entry.get("distribution_distance")
                if distance is not None and distance >= max_distribution_distance:
                    findings.append(
                        Finding(
                            rule_id=self.rule_id,
                            severity=severity,
                            reason=(
                                f"{_DISTANCE_TAG} label {label} ({level_name}) "
                                f"distribution distance {distance:.2f} exceeds "
                                f"threshold {max_distribution_distance:.2f}."
                            ),
                            labels=frozenset({label}),
                        )
                    )

            if flag_out_of_range:
                out_of_range_features = entry.get("out_of_range_features")
                if isinstance(out_of_range_features, list):
                    for name in sorted(out_of_range_features):
                        feat = features.get(name)
                        if not isinstance(feat, dict):
                            feat = {}
                        value = feat.get("value")
                        percentile_rank = feat.get("percentile_rank")
                        findings.append(
                            Finding(
                                rule_id=self.rule_id,
                                severity=severity,
                                reason=(
                                    f"{_OUT_OF_RANGE_TAG} label {label} "
                                    f"({level_name}) feature {name!r} value "
                                    f"{value} falls outside the reference "
                                    f"range (percentile_rank={percentile_rank}, "
                                    f"band=({lower_pct}, {upper_pct}))."
                                ),
                                labels=frozenset({label}),
                            )
                        )

            if flag_robust_z:
                for name in sorted(features):
                    feat = features.get(name)
                    if not isinstance(feat, dict):
                        continue
                    robust_z = feat.get("robust_z")
                    if robust_z is None:
                        continue
                    if abs(robust_z) >= max_robust_z:
                        findings.append(
                            Finding(
                                rule_id=self.rule_id,
                                severity=severity,
                                reason=(
                                    f"{_ROBUST_Z_TAG} label {label} "
                                    f"({level_name}) feature {name!r} "
                                    f"robust_z={robust_z:.2f} exceeds "
                                    f"threshold {max_robust_z:.2f}."
                                ),
                                labels=frozenset({label}),
                            )
                        )

        return findings
