"""Label-sequence continuity rule (item 030).

Implements a **sequence-continuity rule** targeting §6 failure mode 7 — a
non-continuous label sequence: a set of present vertebrae whose anatomical
ordering does not progress monotonically along the spine (reversals and
non-anatomical jumps, e.g. ``L1 -> T12 -> L2 -> L5``). It consumes the
pre-computed ``relationships`` sub-block (item 014, exposed via
``relationships_to_dict``, item 016) and does not recompute continuity
itself.

Design decisions (recorded per item 030 spec):
- The rule fires on ``relationships.out_of_order_labels`` being non-empty —
  the field that carries the concrete offenders to name/attribute — rather
  than on ``is_continuous`` directly. A malformed record with
  ``is_continuous == False`` but an empty ``out_of_order_labels`` therefore
  emits no finding (no concrete offender to name).
- Findings are **label-attributed** (non-empty ``labels``), in contrast to
  item 029's case-level missing-level findings: out-of-order vertebrae are
  present in the segmentation and carry real integer labels.
- One finding per case, naming all offenders in ``out_of_order_labels``
  order; the offending names are additionally resolved to integer labels via
  ``per_label`` (matching ``level_name``), omitting an unmappable name from
  ``labels`` while still naming it in the ``reason``.
- Unrecognised severity string raises ValueError before any per-record
  processing.
- The caller's record is never mutated.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, register_rule
from segqc.verdict import Severity

__all__ = ["SequenceRule"]


# --------------------------------------------------------------------------- #
# Reason tag constant — stable, testable start-of-reason marker
# --------------------------------------------------------------------------- #

_DISCONTINUITY_TAG = "Non-continuous label sequence:"


# --------------------------------------------------------------------------- #
# Severity helper (mirrors bounds.py / coverage.py)
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
            f"Unknown severity label {label!r} in sequence rule config. "
            f"Known labels: {known}."
        )
    return sev


def _label_for_level(per_label: dict, level_name: str) -> Optional[int]:
    """Locate the integer label for *level_name* by scanning ``per_label``.

    ``per_label`` is keyed by integer label, not level name, so a direct key
    lookup is not possible (mirrors coverage.py's
    ``_find_entry_by_level_name``). Returns ``None`` if no entry matches or
    *per_label* is not a mapping.
    """
    if not isinstance(per_label, dict):
        return None
    for entry in per_label.values():
        if isinstance(entry, dict) and entry.get("level_name") == level_name:
            return int(entry["label"])
    return None


# --------------------------------------------------------------------------- #
# SequenceRule
# --------------------------------------------------------------------------- #


@register_rule
class SequenceRule(Rule):
    """Label-sequence continuity rule (item 030).

    Emits at most one finding per case, naming all level names in
    ``relationships.out_of_order_labels`` (in that order) and attributing the
    offenders' integer labels via ``per_label``.
    """

    rule_id = "sequence"

    def evaluate(self, record, config) -> List[Finding]:  # type: ignore[override]
        """Evaluate sequence continuity for *record*.

        Parameters
        ----------
        record:
            Per-case feature dict (read-only). Reads
            ``record["relationships"]`` and ``record["per_label"]``.
        config:
            HeuristicConfig instance. Reads ``rules.sequence.params``.

        Returns
        -------
        list[Finding]
            Zero or one finding.

        Raises
        ------
        ValueError
            If ``rules.sequence.params.severity`` is an unrecognised string
            (raised before any per-record processing, AC12).
        """
        # Read severity once up-front; raises immediately on a bad string (AC12).
        sev_label: str = config.rule_param(
            self.rule_id, "severity", default="flagged-for-review"
        )
        severity = _severity_from_param(sev_label)

        rel = record.get("relationships")
        if not isinstance(rel, dict):
            # Absent / None / not-a-mapping relationships (AC9) — tolerate.
            return []

        out_of_order: List[str] = list(rel.get("out_of_order_labels") or [])
        if not out_of_order:
            # Continuous, or a malformed is_continuous == False with no
            # concrete offender — the conservative "no finding" choice.
            return []

        per_label: dict = record.get("per_label") or {}
        resolved_labels = frozenset(
            label
            for name in out_of_order
            for label in (_label_for_level(per_label, name),)
            if label is not None
        )

        finding = Finding(
            rule_id=self.rule_id,
            severity=severity,
            reason=(
                f"{_DISCONTINUITY_TAG} {', '.join(out_of_order)} "
                f"out of anatomical order."
            ),
            labels=resolved_labels,
        )
        return [finding]
