"""Heuristic rule-engine core for the ``segfacet`` package (item 026).

This package provides the explainable rule-engine foundation that every Stage 4
rule family (items 027–035) plugs into.  It ships **only the engine core** — the
finding data model, the rule abstraction, the registry, and the config-driven
runner.  No concrete rule family (bounds, fragmentation, coverage, sequence,
border, overlap, or mislabel) is present here; those are added by items 027–033.

Public API
----------
``Finding``
    Frozen dataclass: one quality-control finding emitted by a rule.  Carries
    ``rule_id``, ``severity`` (``Severity`` from ``segfacet.verdict``), ``reason``
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

``RuleModeDeclaration``
    Frozen dataclass (item 136): a rule's own class-attribute statement of the
    §6 failure mode(s) it targets — or that it targets none, or that its
    disposition is pending a named downstream item. Metadata only; never read
    during ``evaluate``.

``declaration_for(rule_or_id)`` / ``iter_rule_declarations()``
    Look up a registered rule's ``RuleModeDeclaration`` (item 136), by
    instance or ``rule_id``, or iterate ``(rule_id, declaration)`` pairs in
    ascending ``rule_id`` order.

Config plumbing lives in ``segfacet.config.HeuristicConfig``:

- ``rule_enabled(rule_id, default=True) -> bool``
- ``rule_param(rule_id, key, default) -> Any``
- ``rule_params(rule_id) -> Mapping[str, Any]``

Usage example::

    from segfacet.heuristics import Finding, Rule, register_rule, run_rules
    from segfacet.verdict import Severity
    from segfacet.config import default_config

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

from segfacet.heuristics.finding import Finding
from segfacet.heuristics.rule import (
    Rule,
    RuleModeDeclaration,
    declaration_for,
    get_rule,
    iter_rule_declarations,
    iter_rules,
    register_rule,
)
from segfacet.heuristics.runner import run_rules
from segfacet.heuristics import bounds  # noqa: F401 — registers BoundsRule (item 027)
from segfacet.heuristics import fragmentation  # noqa: F401 — registers FragmentationRule (item 028)
from segfacet.heuristics import coverage  # noqa: F401 — registers CoverageRule (item 029)
from segfacet.heuristics import sequence  # noqa: F401 — registers SequenceRule (item 030)
from segfacet.heuristics import border  # noqa: F401 — registers BorderRule (item 031)
from segfacet.heuristics import overlap  # noqa: F401 — registers OverlapRule (item 032)
from segfacet.heuristics import mislabel  # noqa: F401 — registers MislabelRule (item 033)
from segfacet.heuristics import reference_delta  # noqa: F401 — registers ReferenceDeltaRule (item 047)
from segfacet.heuristics import intensity  # noqa: F401 — registers IntensityRule (item 062)
from segfacet.heuristics import intensity_reference_delta  # noqa: F401 — registers IntensityReferenceDeltaRule (item 064)

__all__ = [
    "Finding",
    "Rule",
    "register_rule",
    "get_rule",
    "iter_rules",
    "run_rules",
    "RuleModeDeclaration",
    "declaration_for",
    "iter_rule_declarations",
]
