"""Verdict-aggregation layer (item 034).

Folds the ``Finding`` objects produced by the Stage 4 rule families
(items 027-033), run through the item-026 ``run_rules`` engine, into the
existing Stage 1 QC verdict model (:mod:`segqc.verdict`: ``Severity``
``PASS < FLAG < FAIL``, ``Reason``, ``Verdict``).

This module is the join point between the rule engine (heuristics) and the
report model (item 035). It is pure, deterministic data transformation over
already-computed findings: it never runs a rule, never touches a label map,
spline, or feature extractor, and never performs I/O.

Severity policy
----------------
**Default -- severity dominance.** With no ``verdict`` config section (or an
empty one), the per-case verdict is the maximum finding severity: any
``fail``-severity finding -> ``fail``; otherwise one or more ``review``-severity
(``FLAG``) findings -> ``flagged-for-review``; otherwise -> ``pass``. This is
exactly the ``max``-severity rule ``Verdict.build`` already computes.

**Config knob -- ``flag_escalation_count``** (int, default ``0`` = disabled).
When ``flag_escalation_count > 0`` and the dominance verdict is
``flagged-for-review`` (>= 1 ``FLAG`` finding and no ``FAIL`` finding anywhere),
and the number of ``FLAG``-severity findings is ``>= flag_escalation_count``,
a synthetic case-level ``FAIL`` ``Reason`` documenting the escalation is
appended, which makes ``overall`` resolve to ``fail``. Escalation never fires
on an already-``fail`` dominance result, never touches a ``pass``, and adds no
reason otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from segqc.heuristics.finding import Finding
from segqc.verdict import Reason, Severity, Verdict

__all__ = ["finding_to_reason", "aggregate_verdict", "build_case_result", "CaseResult"]


def _escalation_message(n_flag: int, threshold: int) -> str:
    """Return the human-readable message for a synthetic escalation reason."""
    return (
        f"{n_flag} review-level findings meet the escalation threshold "
        f"({threshold}); verdict escalated to fail."
    )


def finding_to_reason(finding: Finding) -> Reason:
    """Map a single :class:`Finding` to a :class:`segqc.verdict.Reason`.

    ``message`` is the finding's ``reason`` string carried verbatim (no
    reformatting, no ``rule_id`` prefix), ``severity`` is the finding's
    severity, and ``labels`` is the finding's full offending label set.

    Parameters
    ----------
    finding:
        The source finding.

    Returns
    -------
    Reason
    """
    return Reason(message=finding.reason, severity=finding.severity, labels=finding.labels)


def aggregate_verdict(
    findings: Sequence[Finding],
    config: Any,
    *,
    base_reasons: Sequence[Reason] = (),
    base_per_label: Optional[Mapping[int, Sequence[Reason]]] = None,
) -> Verdict:
    """Fold a list of findings (plus optional Stage-1 base reasons) into a Verdict.

    Parameters
    ----------
    findings:
        The findings to aggregate, in order. Not mutated.
    config:
        A :class:`segqc.config.HeuristicConfig` (or compatible object exposing
        ``policy_param``) providing the ``verdict.flag_escalation_count``
        policy knob.
    base_reasons:
        Optional pre-existing case-level reasons (e.g. the Stage 1
        empty/near-empty check). Merged in ahead of finding-derived case-level
        reasons, preserving input order. Not mutated.
    base_per_label:
        Optional pre-existing per-vertebra reasons, keyed by integer label.
        Merged in ahead of finding-derived reasons for the same label,
        preserving input order. Not mutated.

    Returns
    -------
    Verdict
    """
    # Fresh copies -- never mutate the caller's containers (AC19).
    case_reasons: List[Reason] = list(base_reasons)
    per_label: Dict[int, List[Reason]] = {
        int(label): list(reasons) for label, reasons in (base_per_label or {}).items()
    }

    for finding in findings:
        reason = finding_to_reason(finding)
        if not finding.labels:
            case_reasons.append(reason)
        else:
            for label in sorted(finding.labels):
                per_label.setdefault(label, []).append(reason)

    # Dominance flags, computed over the base + finding-derived reasons so
    # escalation correctly never fires when a FAIL reason exists anywhere
    # (including a base reason).
    has_fail = any(r.severity == Severity.FAIL for r in case_reasons) or any(
        r.severity == Severity.FAIL for reasons in per_label.values() for r in reasons
    )
    n_flag = sum(1 for f in findings if f.severity == Severity.FLAG)
    dominance_is_flag = n_flag > 0 and not has_fail

    threshold = int(config.policy_param("flag_escalation_count", 0))
    if threshold > 0 and dominance_is_flag and n_flag >= threshold:
        case_reasons.append(
            Reason(
                message=_escalation_message(n_flag, threshold),
                severity=Severity.FAIL,
            )
        )

    return Verdict.build(reasons=case_reasons, per_label=per_label)


@dataclass(frozen=True)
class CaseResult:
    """Bundles the derived per-case verdict with the full finding list.

    Attributes
    ----------
    verdict:
        The aggregated :class:`segqc.verdict.Verdict`.
    findings:
        The full, ordered tuple of :class:`Finding` objects the verdict was
        derived from -- preserved so the report layer (item 035) can render
        each finding's ``rule_id``, which the flattened ``Reason`` objects
        drop.
    """

    verdict: Verdict
    findings: Tuple[Finding, ...]


def build_case_result(
    findings: Sequence[Finding],
    config: Any,
    *,
    base_reasons: Sequence[Reason] = (),
    base_per_label: Optional[Mapping[int, Sequence[Reason]]] = None,
) -> CaseResult:
    """Aggregate *findings* into a verdict and bundle it with the finding list.

    Parameters
    ----------
    findings:
        The findings to aggregate, in order. Not mutated.
    config:
        A :class:`segqc.config.HeuristicConfig` (or compatible) providing the
        severity policy.
    base_reasons:
        Optional pre-existing case-level reasons; see :func:`aggregate_verdict`.
    base_per_label:
        Optional pre-existing per-vertebra reasons; see
        :func:`aggregate_verdict`.

    Returns
    -------
    CaseResult
    """
    verdict = aggregate_verdict(
        findings, config, base_reasons=base_reasons, base_per_label=base_per_label
    )
    return CaseResult(verdict=verdict, findings=tuple(findings))
