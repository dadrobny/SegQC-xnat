"""Heuristic rule-engine core for the ``segqc`` package (item 026).

This package provides the explainable rule-engine foundation that every Stage 4
rule family (items 027–035) plugs into.  It ships **only the engine core** — the
finding data model, the rule abstraction, the registry, and the config-driven
runner.  No concrete rule family (bounds, fragmentation, coverage, sequence,
border, overlap, or mislabel) is present here; those are added by items 027–033.

Public API
----------
``Finding``
    Frozen dataclass: one quality-control finding emitted by a rule.  Carries
    ``rule_id``, ``severity`` (``Severity`` from ``segqc.verdict``), ``reason``
    (non-empty string), and ``labels`` (frozenset of offending vertebra label
    integers).  Supports lossless ``to_dict`` / ``from_dict`` round-tripping.

``Rule``
    Abstract base class.  Concrete families subclass it, set the class
    attribute ``rule_id``, and implement
    ``evaluate(record, config) -> list[Finding]``.

``register_rule``
    Decorator / function that instantiates and registers a ``Rule`` subclass in
    the module-level registry.  Raises ``ValueError`` on duplicate ``rule_id``.

``get_rule(rule_id)``
    Retrieve a registered rule instance by id; raises ``KeyError`` if absent.

``iter_rules()``
    Iterate over all registered rules in ascending ``rule_id`` order.

``run_rules(record, config, rules=None)``
    Config-driven runner: selects enabled rules (from the registry by default
    or from an explicit list), executes them deterministically, and returns the
    aggregated ``list[Finding]``.

Config plumbing lives in ``segqc.config.HeuristicConfig``:

- ``rule_enabled(rule_id, default=True) -> bool``
- ``rule_param(rule_id, key, default) -> Any``
- ``rule_params(rule_id) -> Mapping[str, Any]``

Usage example::

    from segqc.heuristics import Finding, Rule, register_rule, run_rules
    from segqc.verdict import Severity
    from segqc.config import default_config

    @register_rule
    class MyRule(Rule):
        rule_id = "my_rule"

        def evaluate(self, record, config):
            threshold = config.rule_param(self.rule_id, "threshold", default=100)
            findings = []
            for label, info in record.get("per_label", {}).items():
                if info.get("volume_mm3", 0) > threshold:
                    findings.append(Finding(
                        rule_id=self.rule_id,
                        severity=Severity.FLAG,
                        reason=f"Label {label}: volume exceeds {threshold} mm³",
                        labels=frozenset({label}),
                    ))
            return findings

    cfg = default_config()
    findings = run_rules(feature_record, cfg)
"""

from segqc.heuristics.finding import Finding
from segqc.heuristics.rule import Rule, get_rule, iter_rules, register_rule
from segqc.heuristics.runner import run_rules
from segqc.heuristics import bounds  # noqa: F401 — registers BoundsRule (item 027)
from segqc.heuristics import fragmentation  # noqa: F401 — registers FragmentationRule (item 028)
from segqc.heuristics import coverage  # noqa: F401 — registers CoverageRule (item 029)
from segqc.heuristics import sequence  # noqa: F401 — registers SequenceRule (item 030)

__all__ = [
    "Finding",
    "Rule",
    "register_rule",
    "get_rule",
    "iter_rules",
    "run_rules",
]
