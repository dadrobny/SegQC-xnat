"""Rule abstraction and registry for the heuristic rule engine (item 026).

Provides:

- :class:`Rule` — abstract base class that every concrete rule family
  (items 027–033) must subclass and implement.
- :func:`register_rule` — function / decorator to register a ``Rule`` subclass
  in the module-level registry.
- :func:`get_rule` — look up a registered rule instance by ``rule_id``.
- :func:`iter_rules` — iterate over all registered rules in deterministic
  (ascending ``rule_id``) order.

The registry (``_RULES``) is a plain module-level dict exposed for test
isolation: tests snapshot / restore it to prevent cross-test leakage without
needing a dependency-injection framework.

Design decisions:
- Rules are **stateless** and **zero-argument**: ``register_rule`` instantiates
  each rule class once at registration time; thresholds are read from ``config``
  in ``evaluate``, not stored on the instance.
- Duplicate ``rule_id`` registration is rejected immediately (``ValueError``)
  to prevent silent shadowing.
- ``iter_rules()`` sorts by ``rule_id`` so the runner is always deterministic
  regardless of import / registration order.
"""

from __future__ import annotations

import abc
from typing import Dict, Iterator, List, Type

from segfacet.heuristics.finding import Finding

__all__ = ["Rule", "register_rule", "get_rule", "iter_rules"]

# Module-level registry: rule_id → Rule instance.
# Deliberately exposed (not name-mangled) so tests can snapshot/restore it.
_RULES: Dict[str, "Rule"] = {}


class Rule(abc.ABC):
    """Abstract base class for all heuristic QC rules.

    Concrete rule families (items 027–033) subclass :class:`Rule`, set the
    class attribute :attr:`rule_id`, and implement :meth:`evaluate`.

    Class attributes
    ----------------
    rule_id:
        A non-empty, stable string identifier for this rule (e.g.
        ``"bounds"``).  Used as the registry key and embedded in every
        :class:`~segfacet.heuristics.Finding` the rule emits.

    Methods
    -------
    evaluate(record, config) -> list[Finding]:
        Inspect *record* (the per-case feature dict produced by
        ``build_features_block``) using thresholds from *config*, and return
        zero or more :class:`~segfacet.heuristics.Finding` objects.  An empty
        list means the rule found nothing to flag.

    Rules must be **stateless**: all thresholds are obtained from *config*
    inside ``evaluate``; nothing is cached on ``self``.
    """

    rule_id: str  # class attribute — must be set by every concrete subclass

    @abc.abstractmethod
    def evaluate(self, record, config) -> List[Finding]:
        """Evaluate this rule against a per-case feature record.

        Parameters
        ----------
        record:
            The per-case feature dict (a JSON-ready ``Mapping[str, Any]``
            with ``per_label``, ``relationships``, ``overlaps``, and an
            optional ``stage3`` sub-block).  Treat as **read-only**.
        config:
            A :class:`~segfacet.config.HeuristicConfig` instance.  Use
            ``config.rule_param(self.rule_id, key, default=…)`` to read
            thresholds; ``config.rule_enabled`` is handled by the runner
            before ``evaluate`` is called.

        Returns
        -------
        list[Finding]
            Zero or more findings.  May be an empty list.
        """


# --------------------------------------------------------------------------- #
# Registry helpers
# --------------------------------------------------------------------------- #


def register_rule(cls: Type[Rule]) -> Type[Rule]:
    """Register *cls* in the global rule registry and return *cls*.

    Can be used as a decorator or called as a plain function::

        @register_rule
        class BoundsRule(Rule):
            rule_id = "bounds"
            def evaluate(self, record, config): ...

        # or:
        register_rule(BoundsRule)

    Parameters
    ----------
    cls:
        A concrete :class:`Rule` subclass with a non-empty ``rule_id``.

    Returns
    -------
    type[Rule]
        *cls* unchanged (for decorator use).

    Raises
    ------
    ValueError
        If ``cls.rule_id`` is absent, empty, or already in the registry.
    """
    rule_id = getattr(cls, "rule_id", None)
    if not rule_id:
        raise ValueError(
            f"Rule class {cls.__name__!r} must define a non-empty 'rule_id' "
            "class attribute before being registered."
        )
    if rule_id in _RULES:
        raise ValueError(
            f"A rule with rule_id={rule_id!r} is already registered "
            f"(existing: {type(_RULES[rule_id]).__name__!r}, "
            f"attempting: {cls.__name__!r}). "
            "Each rule_id must be unique across the registry."
        )
    _RULES[rule_id] = cls()
    return cls


def get_rule(rule_id: str) -> Rule:
    """Return the registered rule instance for *rule_id*.

    Parameters
    ----------
    rule_id:
        The identifier string of the rule to look up.

    Returns
    -------
    Rule
        The registered rule instance.

    Raises
    ------
    KeyError
        If *rule_id* is not in the registry.
    """
    if rule_id not in _RULES:
        raise KeyError(
            f"No rule registered with rule_id={rule_id!r}. "
            f"Registered ids: {sorted(_RULES.keys())}."
        )
    return _RULES[rule_id]


def iter_rules() -> Iterator[Rule]:
    """Iterate over all registered rules in ascending ``rule_id`` order.

    Yields
    ------
    Rule
        Each registered rule instance, sorted by ``rule_id`` string.
    """
    for rule_id in sorted(_RULES.keys()):
        yield _RULES[rule_id]
