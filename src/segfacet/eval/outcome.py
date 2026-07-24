"""QC-verdict comparison & per-case outcome classification (item 052).

This is the §8 **level-1** evaluation primitive -- the coarsest of the three
comparison levels (`1. QC pass/fail verdict; 2. segmentation overlap / DICE;
3. feature-set match`). Given an **expected** side (a `pass` expectation for a
clean ground-truth case, or a known synthetic/curated failure carrying its
expected verdict, §6 failure mode, designated Stage-4 rule id(s), and expected
offending labels -- exactly the shape of
``segfacet.synth.perturbation.Expectation.to_dict()`` / a ``tests/corpus``
manifest-case entry, or a hand-built dict for a human-provided expectation)
and an **actual** side (the pipeline's ``segfacet.aggregate.CaseResult``, whose
``Verdict`` plus ordered ``Finding`` list carries each finding's ``rule_id``
and offending ``labels``), :func:`classify_outcome` returns a single frozen
:class:`CaseOutcome` classifying that one case into the four confusion-matrix
cells -- TP / FP / TN / FN.

Pure and reuse-only: performs no pipeline execution, no rule evaluation, no
label-map or file I/O, and no cross-case aggregation. Item 053's harness
calls this once per case; item 054 aggregates the returned ``CaseOutcome``s
into FPR-on-GT and per-mode sensitivity.

Ternary -> binary reduction
----------------------------
The three-level verdict (``pass`` / ``flagged-for-review`` / ``fail``) is
reduced to a binary "did this side raise a concern?" signal at a threshold
severity, ``positive_severity`` (default :data:`segfacet.verdict.Severity.FLAG`):

    actual_flagged   := actual.verdict.overall  >= positive_severity
    expected_failure := severity_of(expected_verdict) >= positive_severity

The **same** threshold is applied to both sides, so raising it to
``Severity.FAIL`` reclassifies flag-only cases as negative symmetrically.
The exact ``pass``/``flagged-for-review``/``fail`` strings are preserved
verbatim in ``expected_verdict`` / ``actual_verdict`` for downstream
reporting; only the binary reduction drives ``outcome``.

``caught`` vs ``caught_by_designated_rule``
--------------------------------------------
- ``caught`` is defined only for failure cases (``expected_failure is True``)
  and equals ``actual_flagged`` -- the coarse "was the failure raised at
  all" signal. ``None`` for clean-expected cases (nothing to catch).
- ``designated_rule_fired`` is ``True`` when the union of
  ``expected_rule_ids`` intersects the actual ``fired_rule_ids``.
- ``caught_by_designated_rule`` is ``True`` when some actual finding has
  ``rule_id in expected_rule_ids`` **and** either ``expected_labels`` is
  empty (a case-level expected finding -- rule-id match alone suffices) or
  that finding's ``labels`` intersect ``expected_labels`` on >= 1 label
  (partial match counts; the designated rule firing on the wrong label does
  not count). This is the per-mode sensitivity substrate 054 aggregates and
  is intentionally stricter than ``caught``: a case can be TP / ``caught is
  True`` yet ``caught_by_designated_rule is False`` when an incidental rule
  raised the flag.

The ``expected`` mapping is consumed duck-typed (only ``expected_verdict`` is
required; ``expected_rule_ids``, ``expected_labels``, ``failure_mode``, and
``failure_mode_name`` default when absent). The ``actual`` object is likewise
duck-typed -- any object exposing ``.verdict.overall: Severity`` and an
iterable ``.findings`` of objects with ``.rule_id`` / ``.labels`` works;
``segfacet.aggregate.CaseResult`` is the reference type.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from segfacet.io import FacetInputError
from segfacet.verdict import Severity

__all__ = ["classify_outcome", "Outcome", "CaseOutcome"]


# --------------------------------------------------------------------------- #
# Outcome enum
# --------------------------------------------------------------------------- #


class Outcome(enum.Enum):
    """The four confusion-matrix cells for a single case's QC verdict.

    Attributes
    ----------
    TRUE_POSITIVE:
        Expected failure, actually flagged/failed.
    FALSE_POSITIVE:
        Expected pass, actually flagged/failed.
    TRUE_NEGATIVE:
        Expected pass, actually passed.
    FALSE_NEGATIVE:
        Expected failure, actually passed.
    """

    TRUE_POSITIVE = "TRUE_POSITIVE"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    TRUE_NEGATIVE = "TRUE_NEGATIVE"
    FALSE_NEGATIVE = "FALSE_NEGATIVE"

    @property
    def label(self) -> str:
        """Return the short confusion-matrix label for this outcome.

        Returns
        -------
        str
            ``"TP"``, ``"FP"``, ``"TN"``, or ``"FN"``.
        """
        _labels = {
            Outcome.TRUE_POSITIVE: "TP",
            Outcome.FALSE_POSITIVE: "FP",
            Outcome.TRUE_NEGATIVE: "TN",
            Outcome.FALSE_NEGATIVE: "FN",
        }
        return _labels[self]

    @classmethod
    def from_flags(cls, expected_failure: bool, actual_flagged: bool) -> "Outcome":
        """Return the confusion-matrix cell for a pair of binary flags.

        Parameters
        ----------
        expected_failure:
            Whether the expected side is a positive (failure) case.
        actual_flagged:
            Whether the actual side raised a concern.

        Returns
        -------
        Outcome
        """
        if expected_failure and actual_flagged:
            return cls.TRUE_POSITIVE
        if not expected_failure and actual_flagged:
            return cls.FALSE_POSITIVE
        if not expected_failure and not actual_flagged:
            return cls.TRUE_NEGATIVE
        return cls.FALSE_NEGATIVE


# --------------------------------------------------------------------------- #
# CaseOutcome dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CaseOutcome:
    """The classified §8 level-1 outcome for a single case.

    Attributes
    ----------
    outcome:
        The confusion-matrix cell (TP / FP / TN / FN).
    expected_verdict:
        The expected side's verdict string, preserved verbatim
        (``"pass"`` / ``"flagged-for-review"`` / ``"fail"``).
    actual_verdict:
        The actual side's ``Verdict.overall.label``, preserved verbatim.
    expected_failure:
        The expected side reduced to binary at ``positive_severity``.
    actual_flagged:
        The actual side reduced to binary at ``positive_severity``.
    caught:
        For failure cases (``expected_failure is True``), equals
        ``actual_flagged``; ``None`` for clean-expected cases (nothing to
        catch).
    failure_mode:
        The §6 failure-mode key, or ``None`` if not supplied.
    failure_mode_name:
        The §6 failure-mode name, or ``None`` if not supplied.
    expected_rule_ids:
        Sorted, deduplicated tuple of the designated Stage-4 rule id(s).
    expected_labels:
        Sorted, deduplicated tuple of the expected offending label(s).
    fired_rule_ids:
        Sorted, deduplicated tuple of the actual findings' rule ids.
    designated_rule_fired:
        Whether any designated rule id fired at all (regardless of label).
    caught_by_designated_rule:
        Whether a designated rule fired on >= 1 expected label (or, absent
        expected labels, fired at all) -- the strict per-mode sensitivity
        signal.
    """

    outcome: Outcome
    expected_verdict: str
    actual_verdict: str
    expected_failure: bool
    actual_flagged: bool
    caught: Optional[bool]
    failure_mode: Optional[int]
    failure_mode_name: Optional[str]
    expected_rule_ids: Tuple[str, ...]
    expected_labels: Tuple[int, ...]
    fired_rule_ids: Tuple[str, ...]
    designated_rule_fired: bool
    caught_by_designated_rule: bool


# --------------------------------------------------------------------------- #
# Severity-label lookup
# --------------------------------------------------------------------------- #


_LABEL_TO_SEVERITY: Dict[str, Severity] = {sev.label: sev for sev in Severity}


def _severity_of(verdict_label: str) -> Severity:
    """Map a verdict string to its :class:`Severity`, or raise on unrecognised input."""
    sev = _LABEL_TO_SEVERITY.get(verdict_label)
    if sev is None:
        known = list(_LABEL_TO_SEVERITY.keys())
        raise FacetInputError(
            f"classify_outcome: unrecognised expected_verdict {verdict_label!r}; "
            f"expected one of {known!r}."
        )
    return sev


# --------------------------------------------------------------------------- #
# Expected-side validation + extraction
# --------------------------------------------------------------------------- #


def _extract_expected(
    expected: Any,
) -> Tuple[str, Tuple[str, ...], Tuple[int, ...], Optional[int], Optional[str]]:
    """Validate and extract the expected-side mapping's fields.

    Returns
    -------
    (expected_verdict, expected_rule_ids, expected_labels, failure_mode,
    failure_mode_name)

    Raises
    ------
    segfacet.io.FacetInputError
        If ``expected`` is not a mapping, lacks ``expected_verdict``, or
        carries an unrecognised ``expected_verdict``.
    """
    if not isinstance(expected, Mapping):
        raise FacetInputError(
            f"classify_outcome: expected must be a mapping; got "
            f"{type(expected).__name__!r}."
        )
    if "expected_verdict" not in expected:
        raise FacetInputError(
            "classify_outcome: expected mapping is missing required key "
            "'expected_verdict'."
        )
    expected_verdict = expected["expected_verdict"]
    _severity_of(expected_verdict)  # validates; raises FacetInputError if unknown

    rule_ids = tuple(sorted(set(expected.get("expected_rule_ids") or ())))
    labels = tuple(sorted(set(expected.get("expected_labels") or ())))
    failure_mode = expected.get("failure_mode")
    failure_mode_name = expected.get("failure_mode_name")

    return expected_verdict, rule_ids, labels, failure_mode, failure_mode_name


# --------------------------------------------------------------------------- #
# Actual-side validation + extraction
# --------------------------------------------------------------------------- #


def _extract_actual(actual: Any) -> Tuple[Severity, Tuple[str, ...], Tuple[Any, ...]]:
    """Validate and extract the actual side's overall severity, fired rule ids,
    and finding tuple.

    Returns
    -------
    (overall_severity, fired_rule_ids, findings_tuple)

    Raises
    ------
    segfacet.io.FacetInputError
        If ``actual`` does not expose a ``.verdict.overall`` that is a
        :class:`Severity` and an iterable ``.findings`` whose items each
        expose ``.rule_id``.
    """
    verdict = getattr(actual, "verdict", None)
    if verdict is None:
        raise FacetInputError(
            f"classify_outcome: actual must expose a 'verdict' attribute "
            f"with an 'overall' Severity; got {type(actual).__name__!r}."
        )
    overall = getattr(verdict, "overall", None)
    if not isinstance(overall, Severity):
        raise FacetInputError(
            "classify_outcome: actual.verdict.overall must be a Severity; "
            f"got {type(overall).__name__!r}."
        )
    findings = getattr(actual, "findings", None)
    if findings is None:
        raise FacetInputError(
            "classify_outcome: actual must expose an iterable 'findings' "
            "attribute."
        )
    try:
        findings_tuple = tuple(findings)
    except TypeError as exc:
        raise FacetInputError(
            f"classify_outcome: actual.findings must be iterable; got "
            f"{type(findings).__name__!r}."
        ) from exc
    try:
        fired_rule_ids = tuple(sorted({f.rule_id for f in findings_tuple}))
    except AttributeError as exc:
        raise FacetInputError(
            "classify_outcome: every item in actual.findings must expose a "
            "'rule_id' attribute."
        ) from exc

    return overall, fired_rule_ids, findings_tuple


# --------------------------------------------------------------------------- #
# classify_outcome
# --------------------------------------------------------------------------- #


def classify_outcome(
    expected: Mapping[str, Any],
    actual: Any,
    *,
    positive_severity: Severity = Severity.FLAG,
) -> CaseOutcome:
    """Classify a single case's actual QC verdict against its expected truth.

    Parameters
    ----------
    expected:
        A mapping in the ``Expectation.to_dict()`` / ``tests/corpus``
        manifest-case shape. Only ``expected_verdict`` is required;
        ``expected_rule_ids``, ``expected_labels``, ``failure_mode``, and
        ``failure_mode_name`` default when absent. Not mutated.
    actual:
        The pipeline's actual result for the case -- duck-typed as any
        object exposing ``.verdict.overall: Severity`` and an iterable
        ``.findings`` of objects with ``.rule_id`` (and ``.labels``, read
        only when checking the designated-rule/label match). Not mutated.
        ``segfacet.aggregate.CaseResult`` is the reference type.
    positive_severity:
        The threshold severity at which the ternary verdict (``pass`` /
        ``flagged-for-review`` / ``fail``) is reduced to a binary "raised a
        concern" signal, applied identically to both sides. Defaults to
        :data:`Severity.FLAG` (flag-or-worse counts as positive).

    Returns
    -------
    CaseOutcome

    Raises
    ------
    segfacet.io.FacetInputError
        If ``expected`` is not a mapping, lacks/misuses ``expected_verdict``,
        or ``actual`` does not expose the required ``verdict``/``findings``
        shape.
    """
    (
        expected_verdict,
        expected_rule_ids,
        expected_labels,
        failure_mode,
        failure_mode_name,
    ) = _extract_expected(expected)
    overall_severity, fired_rule_ids, findings_tuple = _extract_actual(actual)

    expected_failure = _severity_of(expected_verdict) >= positive_severity
    actual_flagged = overall_severity >= positive_severity
    outcome = Outcome.from_flags(expected_failure, actual_flagged)
    caught: Optional[bool] = actual_flagged if expected_failure else None

    expected_rule_id_set = set(expected_rule_ids)
    designated_rule_fired = bool(expected_rule_id_set & set(fired_rule_ids))

    expected_label_set = set(expected_labels)
    caught_by_designated_rule = any(
        f.rule_id in expected_rule_id_set
        and (not expected_label_set or set(f.labels) & expected_label_set)
        for f in findings_tuple
    )

    return CaseOutcome(
        outcome=outcome,
        expected_verdict=expected_verdict,
        actual_verdict=overall_severity.label,
        expected_failure=expected_failure,
        actual_flagged=actual_flagged,
        caught=caught,
        failure_mode=failure_mode,
        failure_mode_name=failure_mode_name,
        expected_rule_ids=expected_rule_ids,
        expected_labels=expected_labels,
        fired_rule_ids=fired_rule_ids,
        designated_rule_fired=designated_rule_fired,
        caught_by_designated_rule=caught_by_designated_rule,
    )
