"""Level-aware intensity delta-to-reference rule family (item 064).

A Stage 4 rule that thresholds item 064's per-vertebra **intensity**
delta-to-reference metrics, read from ``record["intensity_reference_delta"]``
(the ``segfacet.reference.reference_delta_to_dict`` shape, produced by
``compute_intensity_reference_delta``). It fires a ``Finding`` when a
vertebra's intensity is a statistical outlier relative to its **own
anatomical level's** VerSe-derived reference distribution -- the
level-aware, reference-relative counterpart to item 062's absolute,
global-band ``IntensityRule``.

Scope
-----
This module computes **no** statistic itself -- z-score, robust-z,
percentile-rank, out-of-range, and distribution-distance are all already
computed and serialised by item 064's compute half. This rule only
*thresholds* those already-computed numbers. It imports nothing from
``segfacet.reference``, loads no reference artifact, and is stateless / I/O-free,
exactly like its Stage 4 siblings (``bounds``, ``fragmentation``,
``coverage``, ``sequence``, ``border``, ``overlap``, ``mislabel``,
``reference_delta``, ``intensity``).

It does **not** touch ``segfacet.pipeline``, ``segfacet.cli``, ``segfacet.config``,
``default_config.yaml``, ``segfacet.report``, or ``segfacet.aggregate`` -- wiring
the ``intensity_reference_delta`` block into the record fed to ``run_rules``
is item 065's remit. Until that wiring lands,
``record.get("intensity_reference_delta")`` is absent by default, so this
rule is silently a no-op and existing pipeline output is unaffected by its
addition.

Three independent, config-toggleable firing conditions per available label:

1. **Distribution-distance outlier** (label-level) -- fires when
   ``distribution_distance >= max_distribution_distance`` (default ``3.0``).
2. **Out-of-range feature** (per feature) -- fires for each feature name in
   the block's ``out_of_range_features`` list.
3. **Robust-z outlier** (per feature) -- fires for each feature whose
   ``abs(robust_z) >= max_robust_z`` (default ``3.5``).

A label whose entry is ``available: false`` (or an absent/non-mapping
``intensity_reference_delta`` block) contributes no findings -- reference-
grounded judgement is silent where there is no reference.

Determinism / non-mutation contract: ``evaluate`` never mutates ``record``,
and two calls with the same ``(record, config)`` return equal finding lists
in the same order. Findings are emitted ascending by integer label; within a
label, in fixed condition order (distribution-distance -> out-of-range ->
robust-z), with per-feature findings in ascending feature-name order.

Reason tags are distinct from item 047's geometric ``"Reference ..."`` tags
so a reader can tell the two reference-delta families apart.

§6 mode 9 (item 146): the reference-relative form of "intensity"'s tissue-
plausibility judgement. Dispositioned mode-less by item 137 because §6's
eight numbered modes name no such failure; item 146 entered mode 9
("Implausible tissue under a label") into
``segfacet.failure_modes.SPECIFICATION`` and moved this declaration onto it
-- see ``IntensityReferenceDeltaRule.mode_declaration``. No threshold,
condition, severity or ``evaluate`` line changed with it.
"""

from __future__ import annotations

from typing import Dict, List

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import (
    ConsumedPath,
    Rule,
    RuleModeDeclaration,
    register_rule,
)
from segfacet.verdict import Severity

__all__ = ["IntensityReferenceDeltaRule"]


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_MAX_ROBUST_Z = 3.5
DEFAULT_MAX_DISTRIBUTION_DISTANCE = 3.0

_OUT_OF_RANGE_TAG = "Level-aware intensity out-of-range:"
_ROBUST_Z_TAG = "Level-aware intensity robust-z outlier:"
_DISTANCE_TAG = "Level-aware intensity distribution-distance outlier:"


# --------------------------------------------------------------------------- #
# Severity helper (mirrors reference_delta.py)
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
            f"Unknown severity label {label!r} in intensity_reference_delta rule "
            f"config. Known labels: {known}."
        )
    return sev


# --------------------------------------------------------------------------- #
# IntensityReferenceDeltaRule
# --------------------------------------------------------------------------- #


@register_rule
class IntensityReferenceDeltaRule(Rule):
    """Level-aware intensity delta-to-reference rule (item 064).

    Reads ``record["intensity_reference_delta"]`` (item 064's
    ``reference_delta_to_dict`` shape, over the intensity feature family) and
    emits a ``Finding`` per fired condition. Returns ``[]`` when the block is
    absent/non-mapping or every available label is in-distribution.
    """

    rule_id = "intensity_reference_delta"

    # §6 disposition (item 146, superseding item 137's mode-less
    # disposition): mode 9, for the same reason as "intensity" -- it is the
    # reference-relative form of the same tissue-plausibility judgement.
    mode_declaration = RuleModeDeclaration(
        modes=(9,),
        evidence=(
            "intensity-corpus-manifest",
            "This rule is the reference-relative form of the intensity "
            "rule's tissue-plausibility judgement: it thresholds how far a "
            "labelled region's intensity statistics deviate from a "
            "level-aware VerSe-derived reference distribution, which is the "
            "same claim mode 9 (implausible tissue under a label) names, "
            "measured against a cohort instead of against a fixed HU band. "
            "It shares mode 9's corpus, tests/corpus/intensity/manifest.json, "
            "but fires on none of its four cases: that corpus is built "
            "against no reference distribution and the item-146 harness "
            "attaches none, so this rule's mode-9 edge sits at the "
            "needs-real-data rung -- the same analytic-only shape item 137 "
            "recorded for reference_delta. The reserved 'corpus' evidence "
            "tag is deliberately NOT bound (item 146 A6): it is checked "
            "against the GEOMETRIC corpus scan only, so tagging it here "
            "would report a false conflict."
        ),
        consumed_paths=(
            ConsumedPath(
                path="per_label",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: this rule "
                    "reads record['intensity_reference_delta'], never the "
                    "top-level record['per_label']"
                ),
            ),
            ConsumedPath(
                path="reference_delta.lower_pct",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: the rule "
                    "reads "
                    "record['intensity_reference_delta']['lower_pct'], a "
                    "block no driver realises, so it has no catalogued "
                    "leaf path of its own"
                ),
            ),
            ConsumedPath(
                path="reference_delta.upper_pct",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: the rule "
                    "reads "
                    "record['intensity_reference_delta']['upper_pct'], not "
                    "record['reference_delta']"
                ),
            ),
            ConsumedPath(
                path="reference_delta.{label}.distribution_distance",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: read from "
                    "the intensity_reference_delta block, not from "
                    "reference_delta"
                ),
            ),
            ConsumedPath(
                path="reference_delta.{label}.features.physical_volume_mm3.percentile_rank",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: "
                    "'percentile_rank' is read under the "
                    "intensity_reference_delta block's own per-feature "
                    "entries"
                ),
            ),
            ConsumedPath(
                path="reference_delta.{label}.features.physical_volume_mm3.robust_z",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: 'robust_z' "
                    "is read under the intensity_reference_delta block, "
                    "never under reference_delta"
                ),
            ),
            ConsumedPath(
                path="reference_delta.{label}.features.physical_volume_mm3.value",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: 'value' is "
                    "read under the intensity_reference_delta block"
                ),
            ),
            ConsumedPath(
                path="reference_delta.{label}.out_of_range_features[]",
                role="not-read",
                reason=(
                    "mechanism B last-path-segment match only: read from "
                    "the intensity_reference_delta block, not from "
                    "reference_delta"
                ),
            ),
        ),
    )

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate level-aware intensity delta-to-reference signals for
        *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["intensity_reference_delta"]``.
        config:
            HeuristicConfig instance. Reads
            ``rules.intensity_reference_delta.params``.

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
            If ``rules.intensity_reference_delta.params.severity`` is an
            unrecognised string (raised before any per-record processing).
        """
        # Read severity once up-front; raises immediately on a bad string,
        # independently of whether the block is even present.
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

        block = record.get("intensity_reference_delta")
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
