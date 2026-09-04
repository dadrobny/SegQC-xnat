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
import dataclasses
from typing import Dict, Iterator, List, Optional, Tuple, Type, Union

from segfacet.heuristics.finding import Finding

__all__ = [
    "Rule",
    "register_rule",
    "get_rule",
    "iter_rules",
    "RuleModeDeclaration",
    "declaration_for",
    "iter_rule_declarations",
]

# Module-level registry: rule_id → Rule instance.
# Deliberately exposed (not name-mangled) so tests can snapshot/restore it.
_RULES: Dict[str, "Rule"] = {}


@dataclasses.dataclass(frozen=True)
class RuleModeDeclaration:
    """A rule's own statement of the §6 failure mode(s) it targets (item 136).

    Exactly one of three states must be realised:

    - **Targeted**: ``modes`` is a non-empty, strictly ascending tuple of
      ``int`` mode numbers (``>= 1``, no duplicates), with non-empty
      ``evidence`` — a tuple of non-empty strings carrying **free-form
      provenance**: which manifest and which case corroborate this
      declaration, or on what analytic grounds it is made. Item 147 retired
      the reserved ``"corpus"`` tag it used to carry: an exact-element
      membership test over an unvalidated tuple is not where an evidence
      claim belongs, and the mode ↔ rule evidence claim is data now — the
      per-edge ``evidence_rung`` on each ``IntendedRule`` in
      ``segfacet.failure_modes.SPECIFICATION``. Nothing in
      ``src/segfacet/`` reads an element of ``evidence`` for meaning::

          RuleModeDeclaration(
              modes=(6,),
              evidence=("corpus-manifest", "tests/corpus/manifest.json's mode6_crop_at_border ..."),
          )

    - **Mode-less**: the rule deliberately targets no §6 mode, with the
      reason recorded in ``mode_less_reason``::

          RuleModeDeclaration(mode_less_reason="structural sanity check, not a failure-mode detector")

    - **Pending**: the disposition is deferred to a named downstream item, in
      ``pending_reason``::

          RuleModeDeclaration(pending_reason="disposition deferred to item 137: ...")

    All four fields default to empty; constructing a declaration that
    realises none of the three states (or more than one at once) raises
    ``ValueError``. Frozen: an existing instance cannot be mutated in place.
    """

    modes: Tuple[int, ...] = ()
    evidence: Tuple[str, ...] = ()
    mode_less_reason: str = ""
    pending_reason: str = ""

    def __post_init__(self) -> None:
        # Outer type checks first (item 147): a bare ``str`` is itself an
        # iterable of non-empty strings, so ``evidence="corpus-derived"``
        # used to pass every check below and then bind a tag by substring
        # accident and render per-character downstream; a ``list`` stayed
        # mutable in place on a frozen dataclass. Both are rejected here,
        # naming the field and saying a tuple is required, before the
        # element loops (which still enforce element types).
        for field_name in ("modes", "evidence"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                raise ValueError(
                    f"RuleModeDeclaration: {field_name!r} must be a tuple, got "
                    f"{type(value).__name__} ({value!r}) -- a bare str or a list "
                    f"is not accepted."
                )

        states_realised = sum(
            1
            for realised in (bool(self.modes), bool(self.mode_less_reason), bool(self.pending_reason))
            if realised
        )
        if states_realised == 0:
            raise ValueError(
                "RuleModeDeclaration: exactly one of 'modes', 'mode_less_reason' or "
                "'pending_reason' must be non-empty; all three are empty."
            )
        if states_realised > 1:
            raise ValueError(
                "RuleModeDeclaration: at most one of 'modes', 'mode_less_reason' and "
                "'pending_reason' may be non-empty at once; more than one is set."
            )

        if self.modes:
            if not self.evidence:
                raise ValueError(
                    "RuleModeDeclaration: 'evidence' must be non-empty when 'modes' is set."
                )
            for mode in self.modes:
                if isinstance(mode, bool) or not isinstance(mode, int):
                    raise ValueError(
                        f"RuleModeDeclaration: 'modes' elements must be int, got {mode!r}."
                    )
                if mode < 1:
                    raise ValueError(
                        f"RuleModeDeclaration: 'modes' elements must be >= 1, got {mode!r}."
                    )
            if len(set(self.modes)) != len(self.modes):
                raise ValueError(
                    f"RuleModeDeclaration: 'modes' must not contain duplicates, got {self.modes!r}."
                )
            if list(self.modes) != sorted(self.modes):
                raise ValueError(
                    f"RuleModeDeclaration: 'modes' must be strictly ascending, got {self.modes!r}."
                )

        for element in self.evidence:
            if not isinstance(element, str) or not element:
                raise ValueError(
                    f"RuleModeDeclaration: 'evidence' elements must be non-empty str, got {element!r}."
                )


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

    mode_declaration: Optional["RuleModeDeclaration"] = None
    """Every concrete rule must set this (item 136): a class-attribute
    ``RuleModeDeclaration`` stating the §6 failure mode(s) this rule targets,
    that it targets none (with a reason), or that its disposition is
    pending (naming the carrier item). Registration does **not** enforce
    this (A3) — ``segfacet.catalogue.rule_declaration_conflicts()`` and the
    test suite over the shipped registry do. Read-only metadata: no rule may
    read its own ``mode_declaration`` inside ``evaluate``."""

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


def declaration_for(rule_or_id: Union[str, Rule]) -> Optional[RuleModeDeclaration]:
    """Return the ``RuleModeDeclaration`` for a registered rule, or ``None``.

    Accepts either a ``rule_id`` string or a ``Rule`` instance. Returns
    ``None`` when the id is unknown, or when the rule is registered but
    carries no declaration (A3).
    """
    if isinstance(rule_or_id, Rule):
        return rule_or_id.mode_declaration
    rule = _RULES.get(rule_or_id)
    if rule is None:
        return None
    return rule.mode_declaration


def iter_rule_declarations() -> Iterator[Tuple[str, Optional[RuleModeDeclaration]]]:
    """Iterate ``(rule_id, declaration)`` pairs in ascending ``rule_id`` order.

    ``declaration`` is ``None`` for a registered rule that sets none (A3).
    """
    for rule_id in sorted(_RULES.keys()):
        yield rule_id, _RULES[rule_id].mode_declaration
