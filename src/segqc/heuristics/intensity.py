"""Implausible-intensity rule family (item 062).

A Stage 4 rule that thresholds item 059's/061's already-computed **first-order
intensity statistics**, read from ``record["image_features"]`` (the
``segqc.feature_report.build_image_features_block`` shape). It fires a
``Finding`` when a labelled region's median/std HU statistics are implausible
for a vertebra, realising the vision's §5.2 image-based feature family feeding
an explainable rule (the Stage 8 "implausible-intensity flag" deliverable).

Scope
-----
This module computes **no** statistic itself — mean/median/std/percentiles are
already computed by item 059 and serialised into the ``image_features`` block
by item 061. This rule only *thresholds* those already-computed numbers. It
imports nothing from ``segqc.features.intensity``, ``segqc.feature_report``, or
``segqc.synth``, samples no voxel, and is stateless / I/O-free, exactly like its
Stage 4 siblings (``bounds``, ``fragmentation``, ``coverage``, ``sequence``,
``border``, ``overlap``, ``mislabel``, ``reference_delta``).

It does **not** touch ``segqc.pipeline``, ``segqc.cli``, ``segqc.config``,
``default_config.yaml``, ``segqc.report``, or ``segqc.aggregate`` — wiring the
``image_features`` block into the record fed to ``run_rules`` is item 065's
remit. Until that wiring lands, ``record.get("image_features")`` is absent by
default, so this rule is silently a no-op and existing pipeline output
(including the item-042 golden snapshots) is byte-identical at 062 merge.

Three independent, config-toggleable firing conditions per label:

1. **Implausibly-low median** (soft-tissue / air mislabel) — fires when
   ``median is not None and median < min_plausible_hu`` (default ``100.0``).
2. **Implausibly-high median** (metal / implant / bright artifact) — fires
   when ``median is not None and median > max_plausible_hu`` (default
   ``2000.0``). Folds in metal-artifact detection: a metal-range median is
   exactly an above-band median, so there is no separate metal lever.
3. **Degenerate / uniform distribution** — fires when
   ``std is not None and std <= max_degenerate_std`` (default ``1.0``), i.e.
   ``std`` at or near zero. Inclusive, so a truly constant region
   (``std == 0.0``) always fires.

Conditions 1 and 2 are the two ends of one level-agnostic bone-plausibility
band ``(min_plausible_hu, max_plausible_hu)``, judged on the robust
**median**; the band is inclusive (a median exactly on a bound does **not**
fire, mirroring ``bounds``' inclusive ``[min, max]``). Condition 3 is
inclusive (``std <= max_degenerate_std``).

A ``None``-valued statistic, an absent/non-mapping/unavailable block, an empty
``per_label``, and malformed sub-entries are all silent (skip the condition or
return ``[]``), never raised — the only raised error is an unrecognised
``severity`` config string.

Determinism / non-mutation contract: ``evaluate`` never mutates ``record``,
and two calls with the same ``(record, config)`` return equal finding lists in
the same order. Findings are emitted ascending by integer label; within a
label, in fixed condition order (low -> high -> degenerate).
"""

from __future__ import annotations

from typing import Dict, List

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, register_rule
from segqc.verdict import Severity

__all__ = ["IntensityRule"]


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DEFAULT_MIN_PLAUSIBLE_HU = 100.0
DEFAULT_MAX_PLAUSIBLE_HU = 2000.0
DEFAULT_MAX_DEGENERATE_STD = 1.0

_LOW_TAG = "Implausible intensity (too low):"
_HIGH_TAG = "Implausible intensity (too high):"
_DEGENERATE_TAG = "Implausible intensity (degenerate/uniform):"


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / reference_delta.py)
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
            f"Unknown severity label {label!r} in intensity rule config. "
            f"Known labels: {known}."
        )
    return sev


# --------------------------------------------------------------------------- #
# IntensityRule
# --------------------------------------------------------------------------- #


@register_rule
class IntensityRule(Rule):
    """Implausible-intensity rule (item 062).

    Reads ``record["image_features"]`` (item 061's
    ``build_image_features_block`` shape) and emits a ``Finding`` per fired
    condition. Returns ``[]`` when the block is absent/non-mapping,
    ``available`` is falsy, ``per_label`` is empty, or every label is
    intensity-plausible.
    """

    rule_id = "intensity"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate implausible-intensity signals for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["image_features"]``.
        config:
            HeuristicConfig instance. Reads ``rules.intensity.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings, ascending by integer label; within a
            label, in fixed condition order (low -> high -> degenerate).

        Raises
        ------
        ValueError
            If ``rules.intensity.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC13).
        """
        # Read severity once up-front; raises immediately on a bad string,
        # independently of whether the block is even present (AC13).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        flag_low = bool(config.rule_param(self.rule_id, "flag_low", default=True))
        flag_high = bool(config.rule_param(self.rule_id, "flag_high", default=True))
        flag_degenerate = bool(
            config.rule_param(self.rule_id, "flag_degenerate", default=True)
        )
        min_plausible_hu = float(
            config.rule_param(
                self.rule_id, "min_plausible_hu", default=DEFAULT_MIN_PLAUSIBLE_HU
            )
        )
        max_plausible_hu = float(
            config.rule_param(
                self.rule_id, "max_plausible_hu", default=DEFAULT_MAX_PLAUSIBLE_HU
            )
        )
        max_degenerate_std = float(
            config.rule_param(
                self.rule_id,
                "max_degenerate_std",
                default=DEFAULT_MAX_DEGENERATE_STD,
            )
        )

        block = record.get("image_features")
        if not isinstance(block, dict) or not block.get("available"):
            return []

        per_label = block.get("per_label")
        if not isinstance(per_label, dict):
            return []

        normalised = []
        for key, entry in per_label.items():
            if not isinstance(entry, dict):
                continue
            try:
                label = int(entry.get("label", key))
            except (TypeError, ValueError):
                continue
            first_order = entry.get("first_order")
            if not isinstance(first_order, dict):
                continue
            normalised.append((label, first_order))
        normalised.sort(key=lambda t: t[0])

        findings: List[Finding] = []
        for label, first_order in normalised:
            median = first_order.get("median")
            std = first_order.get("std")

            if flag_low and median is not None and median < min_plausible_hu:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_LOW_TAG} label {label} median {median:.2f} HU is "
                            f"below the plausible bone band "
                            f"({min_plausible_hu:.2f}, {max_plausible_hu:.2f}) "
                            f"HU (threshold min_plausible_hu="
                            f"{min_plausible_hu:.2f})."
                        ),
                        labels=frozenset({label}),
                    )
                )

            if flag_high and median is not None and median > max_plausible_hu:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_HIGH_TAG} label {label} median {median:.2f} HU is "
                            f"above the plausible bone band "
                            f"({min_plausible_hu:.2f}, {max_plausible_hu:.2f}) "
                            f"HU (threshold max_plausible_hu="
                            f"{max_plausible_hu:.2f})."
                        ),
                        labels=frozenset({label}),
                    )
                )

            if flag_degenerate and std is not None and std <= max_degenerate_std:
                findings.append(
                    Finding(
                        rule_id=self.rule_id,
                        severity=severity,
                        reason=(
                            f"{_DEGENERATE_TAG} label {label} std {std:.2f} HU is "
                            f"at or below the degenerate-uniform threshold "
                            f"max_degenerate_std={max_degenerate_std:.2f} HU."
                        ),
                        labels=frozenset({label}),
                    )
                )

        return findings
