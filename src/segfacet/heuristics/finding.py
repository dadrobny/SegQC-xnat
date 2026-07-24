"""Finding data model for the heuristic rule engine (item 026).

A ``Finding`` is the atomic output unit of a :class:`segfacet.heuristics.Rule`.
It carries the rule that produced it, the severity of the finding, a
human-readable explanation, and optional per-vertebra label attribution.

Design decisions:
- Frozen dataclass so findings are hashable, comparable, and safe to aggregate.
- Reuses ``segfacet.verdict.Severity`` (PASS < FLAG < FAIL) so findings can flow
  directly into the Stage 1 ``Verdict`` model in item 034 without translation.
- ``to_dict`` / ``from_dict`` enable lossless JSON round-tripping: severity is
  rendered as its string label (e.g. ``"flagged-for-review"``), labels as a
  sorted list of plain ints.
- ``labels`` accepts any iterable of ints and is coerced to a ``frozenset``,
  so callers may pass lists, sets, or generators — deduplication is automatic.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Union

from segfacet.verdict import Severity

__all__ = ["Finding"]

# Build a reverse lookup from string label → Severity member once at import time.
_LABEL_TO_SEVERITY: Dict[str, Severity] = {sev.label: sev for sev in Severity}


@dataclass(frozen=True)
class Finding:
    """A single quality-control finding emitted by a :class:`Rule`.

    Attributes
    ----------
    rule_id:
        Non-empty identifier of the rule that produced this finding (e.g.
        ``"bounds"``).  Matches the rule's ``Rule.rule_id`` class attribute.
    severity:
        The severity level of this finding.  Reuses ``segfacet.verdict.Severity``
        so findings can be aggregated directly into the Stage 1 ``Verdict``.
    reason:
        A non-empty, human-readable explanation of why this finding was raised.
        Must not be blank or whitespace-only.
    labels:
        The offending vertebra label values (integer label ids as used in the
        segmentation map).  Empty ``frozenset`` for a case-level finding with
        no specific label attribution.  Any iterable is coerced to a
        ``frozenset``; duplicates are silently deduplicated.
    """

    rule_id: str
    severity: Severity
    reason: str
    labels: FrozenSet[int] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Validate non-empty rule_id.
        if not self.rule_id:
            raise ValueError(
                "Finding.rule_id must be a non-empty string; got an empty string."
            )
        # Validate non-empty (non-whitespace) reason.
        if not self.reason.strip():
            raise ValueError(
                "Finding.reason must be a non-empty, non-whitespace string; "
                f"got {self.reason!r}."
            )
        # Coerce labels to frozenset (handles list, set, or any other iterable).
        if not isinstance(self.labels, frozenset):
            object.__setattr__(self, "labels", frozenset(self.labels))

    # ------------------------------------------------------------------ #
    # Serialisation helpers
    # ------------------------------------------------------------------ #

    def to_dict(self) -> Dict[str, Any]:
        """Serialise this finding to a JSON-ready dict.

        The returned mapping is JSON-serialisable:

        - ``severity`` is rendered as its string label (e.g.
          ``"flagged-for-review"``), not as a Python enum repr.
        - ``labels`` is a sorted ``list`` of plain ``int`` values.

        Returns
        -------
        dict
            ``{"rule_id": str, "severity": str, "reason": str,
            "labels": list[int]}``
        """
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.label,
            "reason": self.reason,
            "labels": sorted(self.labels),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Finding":
        """Reconstruct a :class:`Finding` from a :meth:`to_dict` output.

        Parameters
        ----------
        d:
            Dict as returned by :meth:`to_dict`.

        Returns
        -------
        Finding

        Raises
        ------
        ValueError
            If the ``severity`` string is not a recognised label.
        """
        severity_label: str = d["severity"]
        severity = _LABEL_TO_SEVERITY.get(severity_label)
        if severity is None:
            known = list(_LABEL_TO_SEVERITY.keys())
            raise ValueError(
                f"Unknown severity label {severity_label!r}. "
                f"Known labels: {known}."
            )
        return cls(
            rule_id=d["rule_id"],
            severity=severity,
            reason=d["reason"],
            labels=frozenset(d.get("labels", [])),
        )
