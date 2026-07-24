"""Config-driven rule runner for the heuristic rule engine (item 026).

The runner is the execution entry point: it selects enabled rules, calls each
one's ``evaluate`` method in a deterministic order, and aggregates the findings
into a single flat list.

Design decisions:
- Default to ``iter_rules()`` (all registered rules, sorted by ``rule_id``)
  when no explicit ``rules`` list is given, so callers need not enumerate rules
  by hand; the registry is the authoritative source.
- Respect ``config.rule_enabled(rule.rule_id)`` before calling a rule so that
  the operator can disable individual rules without touching code.
- Never mutate the ``record`` mapping: pass it to each rule as-is (read-only
  by convention; the core does not deep-copy it, relying on well-behaved rules
  and the immutability contract documented in the spec).
- Return a plain ``list`` (never ``None``) — callers can always iterate the
  result without a None-guard.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import Rule, iter_rules

__all__ = ["run_rules"]


def run_rules(
    record: Mapping[str, Any],
    config: Any,
    rules: Optional[Iterable[Rule]] = None,
) -> List[Finding]:
    """Run all enabled rules against *record* and return the aggregated findings.

    Parameters
    ----------
    record:
        The per-case feature dict (a read-only ``Mapping[str, Any]`` as
        produced by ``segfacet.feature_report.build_features_block``).  The
        runner never mutates this mapping.
    config:
        A :class:`~segfacet.config.HeuristicConfig` instance.  Each rule's
        enabled state is queried via ``config.rule_enabled(rule.rule_id)``.
    rules:
        An optional iterable of :class:`~segfacet.heuristics.Rule` instances to
        run.  When ``None`` (the default), all rules currently in the registry
        are used via :func:`~segfacet.heuristics.rule.iter_rules` (sorted
        ascending by ``rule_id``).  Pass an empty list to run nothing.

    Returns
    -------
    list[Finding]
        Findings from all enabled rules, in ascending ``rule_id`` order.
        Within a single rule's output, findings appear in the order the rule
        returned them.  Always a list; never ``None``.
    """
    effective_rules: Iterable[Rule] = iter_rules() if rules is None else rules

    aggregated: List[Finding] = []
    for rule in effective_rules:
        if not config.rule_enabled(rule.rule_id):
            continue
        findings = rule.evaluate(record, config)
        aggregated.extend(findings)

    return aggregated
