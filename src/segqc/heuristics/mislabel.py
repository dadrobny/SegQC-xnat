"""Mislabel / misalignment rule (item 033).

Implements a **mislabel / misalignment rule** targeting two related §6 failure
modes:

- **Mode 1 — label not aligned with the vertebra it names (misalignment).**
  Detector A flags a vertebra whose centroid is a large outlier from the
  fitted spinal curve, via the per-vertebra perpendicular spline offset
  (``stage3.per_label_offsets[*].offset_mm``, item 018).
- **Mode 4 — semantic mislabelling / wrong vertebra identification.**
  Detector B flags a vertebra whose physical position is inconsistent with
  its anatomical label's expected ordering relative to neighbours, via the
  monotonic-progression metric
  (``stage3.monotonic_consistency.non_monotonic_pairs``, item 020).

It consumes three already-serialised sub-blocks of the per-case feature
record — ``stage3.per_label_offsets`` (item 018), ``stage3.
monotonic_consistency`` (item 020), and ``per_label`` (item 016) — and never
recomputes any geometry, offset, spline, or ordering itself.

Design decisions (recorded per item 033 spec):
- Two independent, config-gated detectors, combined with OR: a record may
  produce findings from either or both.
- Detector A fires on ``offset_mm >= max_offset_mm`` (default ``15.0``,
  inclusive) and is label-attributed (single offending label).
- Detector B fires on each ``non_monotonic_pairs`` entry, resolving both
  level names to integer labels via ``per_label``; an unresolvable name is
  omitted from ``labels`` but still named in the ``reason``.
- Offset findings are emitted first (ascending label), then order findings
  (ascending ``(level_a, level_b)`` name-pair order); both detectors re-sort
  defensively so output never depends on the input list order.
- Unrecognised severity string raises ValueError before any per-record
  processing.
- The caller's record is never mutated.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, register_rule
from segqc.verdict import Severity

__all__ = ["MislabelRule"]


# --------------------------------------------------------------------------- #
# Reason tag constants — stable, testable start-of-reason markers
# --------------------------------------------------------------------------- #

_MISALIGN_TAG = "Vertebra misaligned from spinal curve:"
_MISLABEL_TAG = "Vertebra ordering inconsistent with label:"

_DEFAULT_MAX_OFFSET_MM = 15.0


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / sequence.py / border.py / overlap.py)
# --------------------------------------------------------------------------- #

_LABEL_TO_SEVERITY: Dict[str, Severity] = {sev.label: sev for sev in Severity}


def _severity_from_param(label: str) -> Severity:
    """Map a severity label string to its Severity member.

    Raises
    ------
    ValueError
        If *label* is not a recognised Severity label string.
    """
    sev = _LABEL_TO_SEVERITY.get(label)
    if sev is None:
        known = list(_LABEL_TO_SEVERITY.keys())
        raise ValueError(
            f"Unknown severity label {label!r} in mislabel rule config. "
            f"Known labels: {known}."
        )
    return sev


def _label_for_level(per_label: dict, level_name: str) -> Optional[int]:
    """Locate the integer label for *level_name* by scanning ``per_label``.

    ``per_label`` is keyed by integer label, not level name, so a direct key
    lookup is not possible (mirrors sequence.py's ``_label_for_level``).
    Returns ``None`` if no entry matches or *per_label* is not a mapping.
    """
    if not isinstance(per_label, dict):
        return None
    for entry in per_label.values():
        if isinstance(entry, dict) and entry.get("level_name") == level_name:
            return int(entry["label"])
    return None


# --------------------------------------------------------------------------- #
# MislabelRule
# --------------------------------------------------------------------------- #


@register_rule
class MislabelRule(Rule):
    """Mislabel / misalignment rule (item 033).

    Runs two independent, config-gated detectors and returns their combined
    findings: spline-offset outliers (Detector A, §6 mode 1) first in
    ascending label order, then monotonic-progression inconsistencies
    (Detector B, §6 mode 4) in ascending name-pair order.
    """

    rule_id = "mislabel"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate mislabel / misalignment signals for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["stage3"]["per_label_offsets"]``,
            ``record["stage3"]["monotonic_consistency"]``, and
            ``record["per_label"]``.
        config:
            HeuristicConfig instance. Reads ``rules.mislabel.params``.

        Returns
        -------
        list[Finding]
            Zero or more findings: offset findings first (ascending label),
            then order findings (ascending name-pair order).

        Raises
        ------
        ValueError
            If ``rules.mislabel.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC16).
        """
        # Read severity once up-front; raises immediately on a bad string.
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        max_offset = float(
            config.rule_param(
                self.rule_id, "max_offset_mm", default=_DEFAULT_MAX_OFFSET_MM
            )
        )
        flag_offset = bool(
            config.rule_param(self.rule_id, "flag_offset_outliers", default=True)
        )
        flag_order = bool(
            config.rule_param(
                self.rule_id, "flag_order_inconsistency", default=True
            )
        )

        stage3 = record.get("stage3")
        if not isinstance(stage3, dict):
            stage3 = {}

        offset_findings: List[Finding] = []
        order_findings: List[Finding] = []

        if flag_offset:
            offset_findings = self._detect_offset_outliers(
                stage3, severity, max_offset
            )

        if flag_order:
            order_findings = self._detect_order_inconsistency(
                stage3, record, severity
            )

        return offset_findings + order_findings

    @staticmethod
    def _detect_offset_outliers(
        stage3: dict, severity: Severity, max_offset: float
    ) -> List[Finding]:
        """Detector A: spline-offset outliers (misalignment, §6 mode 1)."""
        offsets = stage3.get("per_label_offsets")
        if not isinstance(offsets, list):
            return []

        normalised = []
        for entry in offsets:
            if not isinstance(entry, dict) or "label" not in entry:
                continue
            try:
                label = int(entry["label"])
            except (TypeError, ValueError):
                continue
            offset = float(entry.get("offset_mm", 0.0) or 0.0)
            name = entry.get("level_name")
            normalised.append((label, name, offset))

        normalised.sort(key=lambda t: t[0])

        findings: List[Finding] = []
        for label, name, offset in normalised:
            if offset >= max_offset:
                findings.append(
                    Finding(
                        rule_id="mislabel",
                        severity=severity,
                        reason=(
                            f"{_MISALIGN_TAG} label {label} ({name}) centroid "
                            f"lies {offset:.1f} mm off the fitted spinal curve "
                            f"(threshold {max_offset:.1f} mm)."
                        ),
                        labels=frozenset({label}),
                    )
                )
        return findings

    @staticmethod
    def _detect_order_inconsistency(
        stage3: dict, record: dict, severity: Severity
    ) -> List[Finding]:
        """Detector B: monotonic-progression inconsistency (mislabelling,
        §6 mode 4)."""
        mono = stage3.get("monotonic_consistency")
        if not isinstance(mono, dict):
            mono = {}

        pairs = mono.get("non_monotonic_pairs")
        if not isinstance(pairs, list):
            return []

        per_label = record.get("per_label")
        if not isinstance(per_label, dict):
            per_label = {}

        normalised = []
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            level_a, level_b = pair[0], pair[1]
            la = _label_for_level(per_label, level_a)
            lb = _label_for_level(per_label, level_b)
            normalised.append((level_a, level_b, la, lb))

        normalised.sort(key=lambda t: (t[0], t[1]))

        findings: List[Finding] = []
        for level_a, level_b, la, lb in normalised:
            findings.append(
                Finding(
                    rule_id="mislabel",
                    severity=severity,
                    reason=(
                        f"{_MISLABEL_TAG} labels {la} ({level_a}) and "
                        f"{lb} ({level_b}) are out of expected order along "
                        f"the spine (spline parameter does not advance)."
                    ),
                    labels=frozenset(
                        {x for x in (la, lb) if x is not None}
                    ),
                )
            )
        return findings
