"""Stage-7 cohort-level metrics aggregation over item 053's per-case records
(item 054).

Given an already-computed :class:`~segfacet.eval.harness.CohortEvaluation` (a
tuple of :class:`~segfacet.eval.harness.CaseEvaluation` records, each bundling
the level-1 verdict ``outcome`` (item 052), the level-2 DICE ``overlap``
(item 050), and the level-3 ``feature_match`` divergence (item 051)),
:func:`compute_cohort_metrics` aggregates the three Stage-7 roadmap metrics:

1. **False-positive rate (FPR) on GT** -- of the expected-pass (clean-GT /
   negative, ``expected_failure is False``) cases, the fraction wrongly
   flagged: ``FP / (FP + TN)`` (roadmap **G3**).
2. **Sensitivity per §6 failure mode** -- for each failure mode present among
   the expected-failure cases, the fraction caught by its **designated**
   Stage-4 rule (``outcome.caught_by_designated_rule``), with a coarser
   caught-at-all rate (``outcome.caught``) reported alongside (roadmap
   **G7**).
3. **DICE-vs-flag correlation** -- a correlation coefficient between each
   case's DICE (the level-2 overlap aggregate) and its flag signal, plus a
   parallel feature-divergence-vs-flag correlation using the level-3
   ``feature_match.case_divergence`` (roadmap **G7**).

This module is **pure aggregation over already-computed records**: it runs no
pipeline, no rule, and does no label-map / file I/O. It is deliberately
decoupled from ``segfacet.synth`` -- the §6 failure-mode integer keys are
consumed only as plain ints/metadata carried on ``CaseOutcome.failure_mode``,
never imported from the taxonomy module (item 057 may pass the full
catalogue in via the ``failure_modes`` parameter).

All degenerate inputs (empty cohort, no negative cases, a requested mode with
no cases, zero-variance correlation inputs, cases without a candidate)
resolve to explicit ``None`` sentinels rather than a divide-by-zero or a
crash -- see :func:`_correlate` and the per-rate helpers below.

Public API
----------
``ConfusionCounts``
    Frozen dataclass carrying the aggregated ``tp/fp/tn/fn`` counts.
``PerModeSensitivity``
    Frozen dataclass carrying one §6 failure mode's per-mode breakdown.
``CorrelationResult``
    Frozen dataclass carrying one correlation's coefficient, sample size,
    method, and named variables.
``CohortMetrics``
    Frozen dataclass carrying the full cohort-level metrics bundle, with a
    JSON-serialisable ``to_dict()``.
``compute_cohort_metrics(cohort, *, correlation_method="pearson",
dice_metric="mean_dice", failure_modes=None) -> CohortMetrics``
    Aggregate a ``CohortEvaluation`` (or any object exposing ``.cases``) into
    a :class:`CohortMetrics`.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

from segfacet.eval.outcome import Outcome
from segfacet.io import FacetInputError

__all__ = [
    "compute_cohort_metrics",
    "ConfusionCounts",
    "PerModeSensitivity",
    "CorrelationResult",
    "CohortMetrics",
]

_VALID_CORRELATION_METHODS = ("pearson", "spearman")
_VALID_DICE_METRICS = ("mean_dice", "volume_weighted_dice")


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConfusionCounts:
    """The aggregated TP/FP/TN/FN confusion-matrix counts for a cohort.

    Attributes
    ----------
    tp, fp, tn, fn:
        Case counts for each of the four confusion-matrix cells.
    """

    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def n_total(self) -> int:
        """Return the total number of cases (``tp + fp + tn + fn``)."""
        return self.tp + self.fp + self.tn + self.fn

    @property
    def n_expected_pass(self) -> int:
        """Return the number of expected-pass (negative) cases (``tn + fp``)."""
        return self.tn + self.fp

    @property
    def n_expected_fail(self) -> int:
        """Return the number of expected-failure (positive) cases (``tp + fn``)."""
        return self.tp + self.fn


@dataclass(frozen=True)
class PerModeSensitivity:
    """One §6 failure mode's per-mode sensitivity/caught-rate breakdown.

    Attributes
    ----------
    failure_mode:
        The §6 mode integer key, or ``None`` for the trailing "no mode
        metadata" bucket.
    failure_mode_name:
        The mode's display name, or ``None`` if unavailable.
    n_cases:
        Number of expected-failure records of this mode.
    n_caught:
        Number of those records with ``outcome.caught is True`` (coarse
        caught-at-all).
    n_caught_by_designated_rule:
        Number of those records with ``outcome.caught_by_designated_rule is
        True`` (the strict, primary per-mode metric).
    sensitivity:
        ``n_caught_by_designated_rule / n_cases``, or ``None`` if
        ``n_cases == 0``.
    caught_rate:
        ``n_caught / n_cases``, or ``None`` if ``n_cases == 0``.
    """

    failure_mode: Optional[int]
    failure_mode_name: Optional[str]
    n_cases: int
    n_caught: int
    n_caught_by_designated_rule: int
    sensitivity: Optional[float]
    caught_rate: Optional[float]


@dataclass(frozen=True)
class CorrelationResult:
    """One correlation coefficient plus its provenance.

    Attributes
    ----------
    coefficient:
        The correlation coefficient, or ``None`` if fewer than two usable
        pairs exist or either variable has zero variance.
    n:
        Number of usable (non-``None``-``x``) pairs.
    method:
        ``"pearson"`` or ``"spearman"``.
    x_variable, y_variable:
        Display names of the correlated variables.
    """

    coefficient: Optional[float]
    n: int
    method: str
    x_variable: str
    y_variable: str


@dataclass(frozen=True)
class CohortMetrics:
    """The full cohort-level Stage-7 metrics bundle.

    Attributes
    ----------
    counts:
        The aggregated confusion counts.
    false_positive_rate:
        ``FP / (FP + TN)`` over the expected-pass set; ``None`` if that set
        is empty.
    sensitivity:
        Overall recall ``TP / (TP + FN)``; ``None`` if the expected-failure
        set is empty.
    specificity:
        ``TN / (TN + FP)``; ``None`` if the expected-pass set is empty.
    per_mode:
        One :class:`PerModeSensitivity` per reported §6 failure mode.
    dice_vs_flag:
        The DICE-vs-flag correlation.
    feature_divergence_vs_flag:
        The feature-divergence-vs-flag correlation.
    n_cases:
        Total number of records aggregated.
    """

    counts: ConfusionCounts
    false_positive_rate: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    per_mode: Tuple[PerModeSensitivity, ...]
    dice_vs_flag: CorrelationResult
    feature_divergence_vs_flag: CorrelationResult
    n_cases: int

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this record.

        Mirrors ``segfacet.eval.harness``'s ``_tuples_to_lists`` approach: every
        nested dataclass is reduced via ``dataclasses.asdict`` and every
        tuple coerced to a list, so the result is already in plain-JSON
        shape (round-trips byte-identically through ``json.dumps`` /
        ``json.loads``, no ``Outcome``/tuple/dataclass survives).
        """
        return _tuples_to_lists(dataclasses.asdict(self))


# --------------------------------------------------------------------------- #
# JSON-shape helper (mirrors segfacet.eval.harness._tuples_to_lists)
# --------------------------------------------------------------------------- #


def _tuples_to_lists(obj: Any) -> Any:
    """Recursively coerce any ``tuple`` in *obj* to a ``list``.

    ``dataclasses.asdict`` preserves tuple-typed fields (e.g.
    ``CohortMetrics.per_mode``) as Python tuples, which do not compare equal
    to their own post ``json.dumps``/``json.loads`` round-trip counterpart
    (always a list). Applying this pass up front makes the dict already
    "plain JSON" shaped.
    """
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- #
# Confusion counting
# --------------------------------------------------------------------------- #


def _count_confusion(records: Sequence[Any]) -> ConfusionCounts:
    """Tally ``tp/fp/tn/fn`` by ``record.outcome.outcome`` in a single pass."""
    tp = fp = tn = fn = 0
    for record in records:
        cell = record.outcome.outcome
        if cell is Outcome.TRUE_POSITIVE:
            tp += 1
        elif cell is Outcome.FALSE_POSITIVE:
            fp += 1
        elif cell is Outcome.TRUE_NEGATIVE:
            tn += 1
        elif cell is Outcome.FALSE_NEGATIVE:
            fn += 1
    return ConfusionCounts(tp=tp, fp=fp, tn=tn, fn=fn)


def _safe_rate(numerator: int, denominator: int) -> Optional[float]:
    """Return ``numerator / denominator``, or ``None`` if ``denominator == 0``."""
    return (numerator / denominator) if denominator > 0 else None


# --------------------------------------------------------------------------- #
# Per-mode aggregation
# --------------------------------------------------------------------------- #


def _requested_modes(
    failure_modes: Optional[Union[Sequence[int], Mapping[int, str]]],
    observed: Mapping[Optional[int], List[Any]],
) -> List[Tuple[Optional[int], Optional[str]]]:
    """Determine the ordered ``(mode, requested_name)`` list to report.

    When ``failure_modes`` is ``None``, report one entry per distinct
    observed mode key, ascending, with a ``None`` key trailing. Otherwise
    report exactly one entry per requested mode, in the given order (a
    mapping supplies the display name; a bare sequence leaves the name to be
    resolved from an observed record, if any).
    """
    if failure_modes is None:
        keys = [k for k in observed if k is not None]
        keys.sort()
        if None in observed:
            keys.append(None)
        return [(k, None) for k in keys]

    if isinstance(failure_modes, Mapping):
        return [(mode, name) for mode, name in failure_modes.items()]

    return [(mode, None) for mode in failure_modes]


def _per_mode_entry(
    mode: Optional[int],
    requested_name: Optional[str],
    records: List[Any],
) -> PerModeSensitivity:
    """Build one :class:`PerModeSensitivity` from a mode key's grouped records."""
    n_cases = len(records)
    n_caught = sum(1 for r in records if r.outcome.caught is True)
    n_caught_by_designated_rule = sum(
        1 for r in records if r.outcome.caught_by_designated_rule is True
    )
    sensitivity = _safe_rate(n_caught_by_designated_rule, n_cases)
    caught_rate = _safe_rate(n_caught, n_cases)

    if requested_name is not None:
        failure_mode_name = requested_name
    elif records:
        failure_mode_name = records[0].outcome.failure_mode_name
    else:
        failure_mode_name = None

    return PerModeSensitivity(
        failure_mode=mode,
        failure_mode_name=failure_mode_name,
        n_cases=n_cases,
        n_caught=n_caught,
        n_caught_by_designated_rule=n_caught_by_designated_rule,
        sensitivity=sensitivity,
        caught_rate=caught_rate,
    )


def _compute_per_mode(
    records: Sequence[Any],
    failure_modes: Optional[Union[Sequence[int], Mapping[int, str]]],
) -> Tuple[PerModeSensitivity, ...]:
    """Group expected-failure records by ``outcome.failure_mode`` and build
    the reported per-mode breakdown (see step 8 of the item spec)."""
    observed: Dict[Optional[int], List[Any]] = {}
    for record in records:
        if record.outcome.expected_failure is not True:
            continue
        observed.setdefault(record.outcome.failure_mode, []).append(record)

    reported = _requested_modes(failure_modes, observed)
    entries = [
        _per_mode_entry(mode, name, observed.get(mode, []))
        for mode, name in reported
    ]
    return tuple(entries)


# --------------------------------------------------------------------------- #
# Correlation
# --------------------------------------------------------------------------- #


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Return average ranks (1-based, ties share the mean rank) for ``values``."""
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=float)

    i = 0
    n = len(values)
    while i < n:
        j = i
        while j + 1 < n and sorted_values[j + 1] == sorted_values[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg_rank
        i = j + 1
    return ranks


def _correlate(
    xs: Sequence[Optional[float]],
    ys: Sequence[float],
    method: str,
    x_name: str,
    y_name: str,
) -> CorrelationResult:
    """Compute a Pearson/Spearman correlation with explicit sentinels.

    Pairs where ``x is None`` are dropped first. ``coefficient`` is ``None``
    when fewer than two usable pairs remain, or either variable has zero
    variance -- never a divide-by-zero or ``NaN``.
    """
    usable_x = []
    usable_y = []
    for x, y in zip(xs, ys):
        if x is None:
            continue
        usable_x.append(x)
        usable_y.append(y)

    n = len(usable_x)
    if n < 2:
        return CorrelationResult(
            coefficient=None, n=n, method=method, x_variable=x_name, y_variable=y_name
        )

    x_arr = np.asarray(usable_x, dtype=float)
    y_arr = np.asarray(usable_y, dtype=float)

    if method == "spearman":
        x_arr = _average_ranks(x_arr)
        y_arr = _average_ranks(y_arr)

    std_x = float(np.std(x_arr))
    std_y = float(np.std(y_arr))
    if std_x == 0.0 or std_y == 0.0:
        coefficient: Optional[float] = None
    else:
        cov = float(np.mean((x_arr - x_arr.mean()) * (y_arr - y_arr.mean())))
        coefficient = cov / (std_x * std_y)

    return CorrelationResult(
        coefficient=coefficient, n=n, method=method, x_variable=x_name, y_variable=y_name
    )


def _dice_series(records: Sequence[Any], dice_metric: str) -> List[Optional[float]]:
    """Return the selected DICE aggregate for each record (``None`` if absent)."""
    values: List[Optional[float]] = []
    for record in records:
        overlap = record.overlap
        values.append(None if overlap is None else getattr(overlap, dice_metric))
    return values


def _divergence_series(records: Sequence[Any]) -> List[Optional[float]]:
    """Return each record's ``feature_match.case_divergence`` (``None`` if absent)."""
    values: List[Optional[float]] = []
    for record in records:
        feature_match = record.feature_match
        values.append(None if feature_match is None else feature_match.case_divergence)
    return values


def _flag_series(records: Sequence[Any]) -> List[float]:
    """Return each record's binary flag indicator (``1.0``/``0.0``)."""
    return [1.0 if record.outcome.actual_flagged else 0.0 for record in records]


# --------------------------------------------------------------------------- #
# compute_cohort_metrics
# --------------------------------------------------------------------------- #


def compute_cohort_metrics(
    cohort: Any,
    *,
    correlation_method: str = "pearson",
    dice_metric: str = "mean_dice",
    failure_modes: Optional[Union[Sequence[int], Mapping[int, str]]] = None,
) -> CohortMetrics:
    """Aggregate a cohort's per-case evaluation records into cohort metrics.

    Parameters
    ----------
    cohort:
        A :class:`~segfacet.eval.harness.CohortEvaluation`, or any object
        duck-typed on ``.cases`` (an iterable of
        :class:`~segfacet.eval.harness.CaseEvaluation`-shaped records). Read
        only, never mutated.
    correlation_method:
        ``"pearson"`` (default) or ``"spearman"``.
    dice_metric:
        Which ``OverlapResult`` aggregate to correlate against the flag
        signal: ``"mean_dice"`` (default) or ``"volume_weighted_dice"``.
    failure_modes:
        ``None`` (default, report one entry per distinct observed mode), a
        sequence of mode ints, or a ``{int: name}`` mapping (report exactly
        one entry per requested mode, in order, including a sentinel entry
        for a mode absent from the cohort).

    Returns
    -------
    CohortMetrics

    Raises
    ------
    segfacet.io.FacetInputError
        If ``correlation_method`` is not ``"pearson"``/``"spearman"``, or
        ``dice_metric`` is not ``"mean_dice"``/``"volume_weighted_dice"``.
    """
    if correlation_method not in _VALID_CORRELATION_METHODS:
        raise FacetInputError(
            f"compute_cohort_metrics: unrecognised correlation_method "
            f"{correlation_method!r}; expected one of "
            f"{_VALID_CORRELATION_METHODS!r}."
        )
    if dice_metric not in _VALID_DICE_METRICS:
        raise FacetInputError(
            f"compute_cohort_metrics: unrecognised dice_metric {dice_metric!r}; "
            f"expected one of {_VALID_DICE_METRICS!r}."
        )

    records = tuple(cohort.cases)

    counts = _count_confusion(records)
    false_positive_rate = _safe_rate(counts.fp, counts.fp + counts.tn)
    sensitivity = _safe_rate(counts.tp, counts.tp + counts.fn)
    specificity = _safe_rate(counts.tn, counts.tn + counts.fp)

    per_mode = _compute_per_mode(records, failure_modes)

    flags = _flag_series(records)
    dice_vs_flag = _correlate(
        _dice_series(records, dice_metric), flags, correlation_method, dice_metric, "flagged"
    )
    feature_divergence_vs_flag = _correlate(
        _divergence_series(records),
        flags,
        correlation_method,
        "case_divergence",
        "flagged",
    )

    return CohortMetrics(
        counts=counts,
        false_positive_rate=false_positive_rate,
        sensitivity=sensitivity,
        specificity=specificity,
        per_mode=per_mode,
        dice_vs_flag=dice_vs_flag,
        feature_divergence_vs_flag=feature_divergence_vs_flag,
        n_cases=len(records),
    )
