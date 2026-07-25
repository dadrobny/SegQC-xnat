"""Perturbation framework: abstraction, registry, and the identity operator
(item 036).

Pins the precise contract the three Stage 5 operator-family items (037, 038,
039) implement against:

* :class:`Perturbation` -- an abstract base with a class-attribute ``name``
  (the registry key) and an ``apply(labelmap, seed) -> PerturbationResult``
  contract.
* :class:`Expectation` -- what the perturbed case is expected to look like
  once run back through the real Stage 4 pipeline: the intended §6 failure
  mode, the Stage 4 rule id(s) expected to fire, the expected offending
  labels, and the expected verdict.
* :class:`PerturbationResult` -- the ``(labelmap, expectation)`` pair
  ``apply`` returns, as both an unpackable tuple and named attributes.
* A small module-level registry (mirroring ``segfacet.heuristics.rule``'s
  ``_RULES`` idiom) that stores registered **classes** (not instances) --
  operators are parameterised via their constructor, so ``apply`` itself
  takes only ``(labelmap, seed)``.
* :class:`IdentityPerturbation` -- the reference no-op operator, registered
  under ``"identity"``: a clean-control positive-control pass-through.

Every perturbation MUST be seeded and reproducible: the same operator with
the same seed and input produces a byte-identical output array, derived
solely from ``numpy.random.default_rng(seed)`` (never the global RNG -- see
:func:`seeded_rng`). ``apply`` must never mutate the caller's input
image/array.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterator, NamedTuple, Type

import numpy as np
import nibabel as nib

__all__ = [
    "CLEAN_CONTROL_MODE",
    "FAILURE_MODE_NAMES",
    "Expectation",
    "PerturbationResult",
    "Perturbation",
    "register_perturbation",
    "get_perturbation",
    "iter_perturbations",
    "perturbation_names",
    "seeded_rng",
    "IdentityPerturbation",
]

# --------------------------------------------------------------------------- #
# §6 failure-mode taxonomy
# --------------------------------------------------------------------------- #

#: Sentinel §6 "mode" for the clean control (no injected failure).
CLEAN_CONTROL_MODE: int = 0

#: Canonical §6 failure-mode names, keyed 0..8 (0 == clean control). Shared so
#: every operator (037-039) names its mode identically.
FAILURE_MODE_NAMES: Dict[int, str] = {
    0: "clean control (no failure)",
    1: "label not aligned with the vertebra it names",
    2: "over-/under-segmentation (fused / fragmented)",
    3: "disconnected components / rogue islands",
    4: "semantic mislabelling (wrong identification)",
    5: "not all vertebrae segmented (missing levels)",
    6: "partial vertebra at the image border",
    7: "non-continuous label sequence",
    8: "overlapping segments",
}


# --------------------------------------------------------------------------- #
# Expectation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Expectation:
    """The predicted outcome of running a perturbed case through Stage 4.

    Attributes
    ----------
    failure_mode:
        The §6 failure-mode key (0..8; 0 == :data:`CLEAN_CONTROL_MODE`).
    failure_mode_name:
        Human-readable name, usually ``FAILURE_MODE_NAMES[failure_mode]``.
    expected_rule_ids:
        The Stage 4 ``rule_id`` string(s) expected among the fired findings.
        Empty for the clean control.
    expected_labels:
        The expected offending integer labels. Empty for case-level findings
        or the clean control.
    expected_verdict:
        One of ``"pass"`` / ``"flagged-for-review"`` / ``"fail"`` -- not
        validated here (the manifest/regression items validate it against
        real :class:`~segfacet.verdict.Severity` labels).
    detail:
        Optional free-text note.
    """

    failure_mode: int
    failure_mode_name: str
    expected_rule_ids: FrozenSet[str]
    expected_labels: FrozenSet[int]
    expected_verdict: str
    detail: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-ready dict (``rule_ids``/``labels`` as sorted lists)."""
        return {
            "failure_mode": self.failure_mode,
            "failure_mode_name": self.failure_mode_name,
            "expected_rule_ids": sorted(self.expected_rule_ids),
            "expected_labels": sorted(self.expected_labels),
            "expected_verdict": self.expected_verdict,
            "detail": self.detail,
        }


# --------------------------------------------------------------------------- #
# PerturbationResult
# --------------------------------------------------------------------------- #


class PerturbationResult(NamedTuple):
    """The ``(labelmap, expectation)`` pair returned by ``apply``.

    Both an unpackable 2-tuple (``lm, ex = result``) and named-attribute
    access (``result.labelmap`` / ``result.expectation``).
    """

    labelmap: nib.Nifti1Image
    expectation: Expectation


# --------------------------------------------------------------------------- #
# Perturbation abstraction
# --------------------------------------------------------------------------- #


class Perturbation(abc.ABC):
    """Abstract base for every synthetic-corpus failure-injection operator.

    Concrete subclasses (the reference :class:`IdentityPerturbation` here,
    and the operator families in items 037-039) declare a unique
    class-attribute ``name`` (the registry key) and implement :meth:`apply`.

    ``apply`` must be:

    * **Seeded & reproducible** -- all randomness derived solely from
      ``numpy.random.default_rng(seed)`` (see :func:`seeded_rng`); the same
      seed + input yields a byte-identical output array.
    * **Non-mutating** -- the caller's input image/array is never modified;
      a fresh :class:`nibabel.Nifti1Image` is always returned.
    """

    name: str  # class attribute -- must be set by every concrete subclass

    @abc.abstractmethod
    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        """Apply this perturbation to *labelmap* and return the result.

        Parameters
        ----------
        labelmap:
            A NiBabel ``Nifti1Image`` carrying an integer instance label map.
            Spacing/affine are read via ``labelmap.header.get_zooms()[:3]``
            and ``labelmap.affine`` (as the Stage 2/3 extractors already do).
            Never mutated.
        seed:
            Integer seed for any stochastic behaviour. Deterministic
            operators (e.g. :class:`IdentityPerturbation`) still accept it to
            honour the signature.

        Returns
        -------
        PerturbationResult
        """


# --------------------------------------------------------------------------- #
# Registry (mirrors segfacet.heuristics.rule's _RULES idiom)
# --------------------------------------------------------------------------- #

# Module-level registry: name -> Perturbation CLASS (not instance) --
# operators are parameterised via their constructor, so apply takes only
# (labelmap, seed). Deliberately exposed (not name-mangled) so tests can
# snapshot/restore it.
_PERTURBATIONS: Dict[str, Type[Perturbation]] = {}


def register_perturbation(cls: Type[Perturbation]) -> Type[Perturbation]:
    """Register *cls* in the global perturbation registry and return *cls*.

    Can be used as a decorator or called as a plain function.

    Raises
    ------
    ValueError
        If ``cls.name`` is absent, empty, or already registered.
    """
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError(
            f"Perturbation class {cls.__name__!r} must define a non-empty "
            "'name' class attribute before being registered."
        )
    if name in _PERTURBATIONS:
        raise ValueError(
            f"A perturbation with name={name!r} is already registered "
            f"(existing: {_PERTURBATIONS[name].__name__!r}, "
            f"attempting: {cls.__name__!r}). "
            "Each perturbation name must be unique across the registry."
        )
    _PERTURBATIONS[name] = cls
    return cls


def get_perturbation(name: str) -> Type[Perturbation]:
    """Return the registered :class:`Perturbation` subclass for *name*.

    Raises
    ------
    KeyError
        If *name* is not in the registry.
    """
    if name not in _PERTURBATIONS:
        raise KeyError(
            f"No perturbation registered with name={name!r}. "
            f"Registered names: {sorted(_PERTURBATIONS.keys())}."
        )
    return _PERTURBATIONS[name]


def iter_perturbations() -> Iterator[Type[Perturbation]]:
    """Iterate over all registered perturbation classes, sorted by ``name``."""
    for name in sorted(_PERTURBATIONS.keys()):
        yield _PERTURBATIONS[name]


def perturbation_names() -> list:
    """Return all registered perturbation names, sorted."""
    return sorted(_PERTURBATIONS.keys())


# --------------------------------------------------------------------------- #
# Seeded-RNG helper
# --------------------------------------------------------------------------- #


def seeded_rng(seed: int) -> np.random.Generator:
    """Return a fresh, seeded ``numpy.random.Generator``.

    The single, obvious, enforced way for every perturbation to obtain
    reproducible randomness -- never the global NumPy RNG.
    """
    return np.random.default_rng(seed)


# --------------------------------------------------------------------------- #
# IdentityPerturbation -- the reference no-op / clean-control operator
# --------------------------------------------------------------------------- #


@register_perturbation
class IdentityPerturbation(Perturbation):
    """Reference no-op perturbation: returns the input unchanged.

    Registered under ``"identity"``. Ignores ``seed`` (trivially
    deterministic) but still accepts it to honour the :class:`Perturbation`
    signature. The returned :class:`Expectation` is the clean-control /
    positive-control pass expectation.
    """

    name = "identity"

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        # Copy the array so the caller's input is never mutated and the
        # output is a distinct-but-equal array (AC19/AC23).
        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        affine = np.array(labelmap.affine, copy=True)
        out_img = nib.Nifti1Image(data, affine)

        expectation = Expectation(
            failure_mode=CLEAN_CONTROL_MODE,
            failure_mode_name=FAILURE_MODE_NAMES[CLEAN_CONTROL_MODE],
            expected_rule_ids=frozenset(),
            expected_labels=frozenset(),
            expected_verdict="pass",
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)
