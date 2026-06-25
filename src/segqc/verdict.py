"""QC verdict data model (item 008).

Central data structure carrying every quality-control decision made on a single
scan. Expresses a per-case verdict of ``pass`` / ``flagged-for-review`` / ``fail``
and records the individual reasons that drove the verdict, with per-vertebra
attribution so that downstream consumers (JSON serialiser, human-readable
renderer, XNAT integrations) can display exactly which vertebra triggered each
flag.

Public API
----------
``Severity``
    Three-level ordered enum: ``PASS < FLAG < FAIL``. Each member has a
    ``.label`` property returning its output string (``"pass"``,
    ``"flagged-for-review"``, ``"fail"``).
``Reason``
    A frozen dataclass capturing a single human-readable message, a
    ``Severity``, and an optional ``frozenset`` of offending integer labels.
``Verdict``
    Per-case result. Constructed via :meth:`Verdict.build`; stores case-level
    reasons in ``reasons``, per-vertebra reasons in ``per_label``, and the
    maximum severity across all contained reasons in ``overall``.

No runtime dependencies beyond the Python standard library — no NumPy, NiBabel,
SciPy, or any other third-party package.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

__all__ = ["Severity", "Reason", "Verdict"]


# --------------------------------------------------------------------------- #
# Severity enum
# --------------------------------------------------------------------------- #


class Severity(enum.IntEnum):
    """Three ordered severity levels for a QC verdict.

    Using :class:`enum.IntEnum` gives a total ordering for free
    (``PASS < FLAG < FAIL``) and makes ``max()`` / ``min()`` work directly on
    enum members without extra ``functools.total_ordering`` boilerplate.

    Attributes
    ----------
    PASS:
        The case (or reason) did not trigger any quality concern.
    FLAG:
        The case (or reason) warrants human review but is not outright failed.
    FAIL:
        The case (or reason) failed the quality check.
    """

    PASS = 0
    FLAG = 1
    FAIL = 2

    @property
    def label(self) -> str:
        """Return the output string label for this severity level.

        Returns
        -------
        str
            ``"pass"`` for PASS, ``"flagged-for-review"`` for FLAG,
            ``"fail"`` for FAIL.
        """
        _labels = {
            Severity.PASS: "pass",
            Severity.FLAG: "flagged-for-review",
            Severity.FAIL: "fail",
        }
        return _labels[self]


# --------------------------------------------------------------------------- #
# Reason dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Reason:
    """A single human-readable quality-control finding.

    A frozen dataclass so reasons are hashable, comparable, and safe to store
    in sets or as dict values without accidental mutation.

    Attributes
    ----------
    message:
        A non-empty, human-readable description of the finding. Must contain no
        raw library internals (e.g. no ``"Severity.FAIL"`` or module paths).
    severity:
        The severity level of this finding.
    labels:
        Optional frozenset of integer label values that contributed to this
        finding (per-vertebra attribution). Empty by default (case-level
        finding with no specific label attribution).
    """

    message: str
    severity: Severity
    labels: frozenset = field(default_factory=frozenset)


# --------------------------------------------------------------------------- #
# Verdict dataclass
# --------------------------------------------------------------------------- #


@dataclass
class Verdict:
    """Per-case QC verdict.

    Carries the aggregated quality-control result for a single scan:
    the ``overall`` severity (the maximum across all contributing reasons),
    case-level reasons (not tied to any specific label), and per-vertebra
    reasons keyed by integer label value.

    Construction is via the :meth:`build` class method, which computes
    ``overall`` at construction time and stores reasons as immutable tuples so
    that later mutation of the caller's original lists/dicts cannot invalidate
    the stored state (AC-8).

    Attributes
    ----------
    overall:
        The maximum :class:`Severity` across all case-level and per-label
        reasons. An empty reason set yields ``Severity.PASS``.
    reasons:
        Immutable sequence of case-level :class:`Reason` objects (not tied to
        a specific label). Order is preserved from the input.
    per_label:
        Mapping from integer label value to an immutable sequence of
        :class:`Reason` objects attributed to that label. Order of reasons
        under each key is preserved from the input.
    """

    overall: Severity
    reasons: Tuple[Reason, ...]
    per_label: Dict[int, Tuple[Reason, ...]]

    @classmethod
    def build(
        cls,
        reasons: Sequence[Reason],
        per_label: Dict[int, List[Reason]],
    ) -> "Verdict":
        """Construct a :class:`Verdict` from case-level and per-label reasons.

        Computes ``overall`` as the maximum :class:`Severity` across *all*
        supplied reasons (case-level + per-label).  An empty reason set yields
        ``Severity.PASS``.

        Reasons are copied into immutable tuples so that later mutation of the
        caller's original ``reasons`` list or ``per_label`` dict does not
        change the stored state.

        Parameters
        ----------
        reasons:
            Case-level :class:`Reason` objects (not tied to any specific
            label).  May be empty.
        per_label:
            ``{label_value: [Reason, ...]}`` mapping reasons to specific
            integer label values (per-vertebra attribution).  May be empty,
            and individual value lists may be empty.

        Returns
        -------
        Verdict
        """
        # Freeze case-level reasons into a tuple (immutable copy).
        frozen_reasons: Tuple[Reason, ...] = tuple(reasons)

        # Freeze per-label reasons: copy the outer dict and convert each value
        # list to a tuple so neither the outer dict nor the inner sequences can
        # be mutated by the caller after construction.
        frozen_per_label: Dict[int, Tuple[Reason, ...]] = {
            label: tuple(label_reasons)
            for label, label_reasons in per_label.items()
        }

        # Compute overall as the maximum severity across all reasons.
        # Seed with PASS so an empty reason set returns PASS.
        overall: Severity = Severity.PASS

        for reason in frozen_reasons:
            if reason.severity > overall:
                overall = reason.severity

        for label_reasons in frozen_per_label.values():
            for reason in label_reasons:
                if reason.severity > overall:
                    overall = reason.severity

        return cls(
            overall=overall,
            reasons=frozen_reasons,
            per_label=frozen_per_label,
        )
