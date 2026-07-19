"""Stage-7 threshold-calibration loop over item 053's harness + item 054's
metrics (item 055).

This module is a reproducible **calibration loop**, not a bare sweep utility.
Given a fixed evaluation cohort and one or more :class:`ThresholdAxis`
(each naming a config-parameter path within a rule's ``params`` block and an
ordered tuple of candidate values), :func:`calibrate_thresholds` enumerates
the deterministic Cartesian product of the axes, builds a modified
:class:`~segqc.config.HeuristicConfig` per grid point via
:func:`apply_assignment`, re-runs :func:`~segqc.eval.harness.evaluate_cohort`
(item 053) and :func:`~segqc.eval.metrics.compute_cohort_metrics` (item 054)
at that setting, scores the result against a :class:`CalibrationObjective`
(default: minimise the false-positive rate on GT subject to a per-mode-
sensitivity floor), and selects the best feasible candidate -- or reports
"no feasible setting" explicitly, never crashing.

**This module PROPOSES and RECORDS -- it does not persist.** It returns the
chosen thresholds as a re-applyable assignment plus the metrics they
achieved; it never mutates the passed-in ``base_config``, ``cases``, or
``axes``, and performs no file I/O of its own (writing the chosen values into
the shipped config and rendering a report is item 056; the ``segqc
evaluate`` CLI entry point is item 057).

Dependencies
------------
- :mod:`segqc.eval.harness` (item 053) -- ``evaluate_cohort``.
- :mod:`segqc.eval.metrics` (item 054) -- ``compute_cohort_metrics``,
  ``CohortMetrics``, ``PerModeSensitivity``.
- :mod:`segqc.config` (items 005/035) -- ``HeuristicConfig``, ``rule_param``.
- :mod:`segqc.heuristics.bounds` (items 027/048) -- the swept
  ``rules.bounds.params.<group>.[min|max]_*`` shape.
- :mod:`segqc.heuristics.reference_delta` (item 047) -- the swept
  ``rules.reference_delta.params.max_robust_z`` /
  ``max_distribution_distance`` shape.

Public API
----------
``ThresholdAxis``
    Frozen dataclass: a sweepable config-parameter axis (``name``,
    ``rule_id``, ``param_path``, ``values``).
``apply_assignment(base_config, assignment, axes) -> HeuristicConfig``
    Pure function: apply an ``{axis.name: value}`` assignment onto a copy of
    ``base_config``.
``CalibrationObjective``
    Frozen dataclass: the feasibility/scoring policy (default: minimise FPR
    subject to a per-mode-sensitivity floor).
``CandidateResult``
    Frozen dataclass: one grid point's assignment, resulting metrics,
    feasibility, and score.
``CalibrationResult``
    Frozen dataclass: every candidate plus the selected ``best`` (or
    ``None``), with a JSON-serialisable ``to_dict()``.
``calibrate_thresholds(cases, base_config, axes, *, objective=..., max_grid_size=...,
positive_severity=..., correlation_method=..., dice_metric=..., failure_modes=...) ->
CalibrationResult``
    Sweep the grid, evaluate every candidate, score it, and select the best
    feasible one.
``default_calibration_axes() -> Tuple[ThresholdAxis, ...]``
    A documented default grid over both the Stage-6 ``reference_delta`` and
    Stage-4 ``bounds`` rule families.
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Sequence, Tuple

from segqc.config import HeuristicConfig
from segqc.eval.harness import EvaluationCase, evaluate_cohort
from segqc.eval.metrics import CohortMetrics, compute_cohort_metrics
from segqc.io import SegQCInputError
from segqc.verdict import Severity

if TYPE_CHECKING:
    from segqc.reference.schema import ReferenceDistribution

__all__ = [
    "ThresholdAxis",
    "apply_assignment",
    "CalibrationObjective",
    "CandidateResult",
    "CalibrationResult",
    "calibrate_thresholds",
    "default_calibration_axes",
]

# Default grid-size guard: a caller must opt into a larger sweep explicitly.
_DEFAULT_MAX_GRID_SIZE = 512


# --------------------------------------------------------------------------- #
# ThresholdAxis
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ThresholdAxis:
    """A single sweepable config-parameter axis.

    Attributes
    ----------
    name:
        A display name for this axis; also the key under which its assigned
        value is reported in a candidate's ``assignment`` mapping. Should be
        unique within a set of axes swept together (the last-applied axis of
        a repeated name wins in ``apply_assignment``).
    rule_id:
        The target rule's identifier (e.g. ``"bounds"``,
        ``"reference_delta"``), matching ``HeuristicConfig.rules`` keys.
    param_path:
        A non-empty tuple of nested keys within that rule's ``params`` dict,
        e.g. ``("lumbar", "max_volume_mm3")`` for
        ``rules["bounds"]["params"]["lumbar"]["max_volume_mm3"]``, or
        ``("max_robust_z",)`` for a flat
        ``rules["reference_delta"]["params"]["max_robust_z"]``. List inputs
        are coerced to tuples.
    values:
        A non-empty, ordered tuple of candidate values to sweep for this
        axis. List inputs are coerced to tuples.

    Raises
    ------
    segqc.io.SegQCInputError
        If ``param_path`` or ``values`` is empty.
    """

    name: str
    rule_id: str
    param_path: Tuple[str, ...]
    values: Tuple[Any, ...]

    def __post_init__(self) -> None:
        param_path = tuple(self.param_path)
        values = tuple(self.values)
        object.__setattr__(self, "param_path", param_path)
        object.__setattr__(self, "values", values)

        if len(param_path) == 0:
            raise SegQCInputError(
                f"ThresholdAxis {self.name!r}: param_path must be non-empty."
            )
        if len(values) == 0:
            raise SegQCInputError(
                f"ThresholdAxis {self.name!r}: values must be non-empty."
            )


# --------------------------------------------------------------------------- #
# apply_assignment
# --------------------------------------------------------------------------- #


def apply_assignment(
    base_config: HeuristicConfig,
    assignment: Mapping[str, Any],
    axes: Sequence[ThresholdAxis],
) -> HeuristicConfig:
    """Return a new :class:`HeuristicConfig` with each axis's value applied.

    For every ``axis`` in *axes* whose ``axis.name`` is present in
    *assignment*, descends/creates
    ``rules[axis.rule_id]["params"][*axis.param_path]`` and sets the leaf to
    ``assignment[axis.name]``. Every other config field (including untouched
    rule sections) is preserved unchanged.

    Pure: neither *base_config* (nor its nested ``rules`` dict) nor
    *assignment* nor *axes* is mutated; the returned config shares no nested
    mutable state with *base_config*.

    Parameters
    ----------
    base_config:
        The config to clone. Not mutated.
    assignment:
        A ``{axis.name: value}`` mapping (a subset of *axes* is fine; axes
        absent from *assignment* are left untouched).
    axes:
        The axes whose ``(rule_id, param_path)`` addressing resolves each
        ``assignment`` key.

    Returns
    -------
    HeuristicConfig
    """
    new_rules: Dict[str, Any] = copy.deepcopy(dict(base_config.rules))

    for axis in axes:
        if axis.name not in assignment:
            continue
        value = assignment[axis.name]

        rule_section = new_rules.setdefault(axis.rule_id, {})
        params = rule_section.setdefault("params", {})

        cursor = params
        for key in axis.param_path[:-1]:
            cursor = cursor.setdefault(key, {})
        cursor[axis.param_path[-1]] = value

    return dataclasses.replace(base_config, rules=new_rules)


# --------------------------------------------------------------------------- #
# Grid enumeration
# --------------------------------------------------------------------------- #


def _grid_size(axes: Sequence[ThresholdAxis]) -> int:
    """Return the Cartesian-product size ``prod(len(axis.values))``."""
    size = 1
    for axis in axes:
        size *= len(axis.values)
    return size


def _enumerate_grid(axes: Sequence[ThresholdAxis]) -> Tuple[Dict[str, Any], ...]:
    """Return the deterministic Cartesian product of *axes* as assignments.

    Axes are varied in the given order, values in each axis's given order,
    with the **last axis varying fastest**. An empty axis sequence yields
    exactly one candidate: the empty assignment.
    """
    if not axes:
        return ({},)

    combos = itertools.product(*(axis.values for axis in axes))
    return tuple(
        {axis.name: value for axis, value in zip(axes, combo)} for combo in combos
    )


# --------------------------------------------------------------------------- #
# CalibrationObjective
# --------------------------------------------------------------------------- #

# Sentinel used to order a None false_positive_rate as best/lowest.
_NEG_INF = float("-inf")


@dataclass(frozen=True)
class CalibrationObjective:
    """The calibration objective: minimise FPR subject to a sensitivity floor.

    Attributes
    ----------
    sensitivity_floor:
        Every per-mode :class:`~segqc.eval.metrics.PerModeSensitivity` with
        ``n_cases > 0`` must have ``sensitivity >= sensitivity_floor`` for a
        candidate to be feasible. Default ``1.0`` (catch every §6 failure
        mode present in the cohort). Modes with ``n_cases == 0``
        (``sensitivity is None``) are excluded from the check -- a mode with
        no cases cannot be missed.
    """

    sensitivity_floor: float = 1.0

    def evaluate(self, metrics: CohortMetrics) -> Tuple[bool, float]:
        """Classify *metrics* as feasible/infeasible and compute its score.

        Returns
        -------
        (feasible, score):
            ``feasible`` is ``True`` iff every reported per-mode sensitivity
            for a mode with ``n_cases > 0`` is ``>= sensitivity_floor``.
            ``score`` is ``metrics.false_positive_rate`` -- lower is
            better -- with ``None`` (no expected-pass cases) mapped to
            ``-inf`` so it always sorts as best/lowest.
        """
        feasible = all(
            mode.sensitivity >= self.sensitivity_floor
            for mode in metrics.per_mode
            if mode.n_cases > 0
        )
        fpr = metrics.false_positive_rate
        score = _NEG_INF if fpr is None else fpr
        return feasible, score


# --------------------------------------------------------------------------- #
# CandidateResult / CalibrationResult
# --------------------------------------------------------------------------- #


def _tuples_to_lists(obj: Any) -> Any:
    """Recursively coerce any ``tuple`` in *obj* to a ``list`` (mirrors
    ``segqc.eval.harness``/``segqc.eval.metrics``'s identical helper)."""
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


@dataclass(frozen=True)
class CandidateResult:
    """One grid point's assignment, resulting metrics, feasibility, and score.

    Attributes
    ----------
    assignment:
        A plain ``{axis.name: value}`` mapping, JSON-friendly, re-applyable
        via ``apply_assignment(base_config, assignment, axes)``.
    metrics:
        The :class:`~segqc.eval.metrics.CohortMetrics` produced by evaluating
        this candidate's config over the cohort.
    feasible:
        Whether this candidate meets the objective's sensitivity floor.
    score:
        The objective's scalar score for this candidate (lower is better;
        see :meth:`CalibrationObjective.evaluate`).
    grid_index:
        This candidate's 0-based position in grid order -- the tie-break of
        last resort.
    """

    assignment: Dict[str, Any]
    metrics: CohortMetrics
    feasible: bool
    score: float
    grid_index: int

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this candidate."""
        return {
            "assignment": _tuples_to_lists(dict(self.assignment)),
            "metrics": self.metrics.to_dict(),
            "feasible": self.feasible,
            "score": (None if self.score == _NEG_INF else self.score),
            "grid_index": self.grid_index,
        }


@dataclass(frozen=True)
class CalibrationResult:
    """The full calibration-loop outcome: every candidate plus the selection.

    Attributes
    ----------
    candidates:
        One :class:`CandidateResult` per grid point, in grid order.
    best:
        The selected best feasible candidate, or ``None`` if no candidate
        was feasible.
    feasible:
        Whether ``best is not None`` (a convenience mirror of
        ``best is not None``).
    status:
        A machine-readable status string: ``"ok"`` when a best candidate was
        selected, ``"no-feasible-setting"`` otherwise.
    objective:
        The :class:`CalibrationObjective` used to score every candidate.
    n_candidates:
        ``len(candidates)``.
    """

    candidates: Tuple[CandidateResult, ...]
    best: Optional[CandidateResult]
    feasible: bool
    status: str
    objective: CalibrationObjective
    n_candidates: int

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this result.

        Round-trips byte-identically through ``json.dumps``/``json.loads``:
        no enum, tuple, or dataclass survives.
        """
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "best": (None if self.best is None else self.best.to_dict()),
            "feasible": self.feasible,
            "status": self.status,
            "objective": {"sensitivity_floor": self.objective.sensitivity_floor},
            "n_candidates": self.n_candidates,
        }


# --------------------------------------------------------------------------- #
# calibrate_thresholds
# --------------------------------------------------------------------------- #


def calibrate_thresholds(
    cases: Sequence[EvaluationCase],
    base_config: HeuristicConfig,
    axes: Sequence[ThresholdAxis],
    *,
    objective: CalibrationObjective = CalibrationObjective(),
    max_grid_size: int = _DEFAULT_MAX_GRID_SIZE,
    positive_severity: Severity = Severity.FLAG,
    correlation_method: str = "pearson",
    dice_metric: str = "mean_dice",
    failure_modes: Optional[Any] = None,
    reference: "Optional[ReferenceDistribution]" = None,
    stratum: str = "all",
    lower_pct: float = 1,
    upper_pct: float = 99,
) -> CalibrationResult:
    """Sweep *axes*' grid, evaluate every candidate, and select the best.

    For every grid point (the deterministic Cartesian product of *axes*,
    last axis fastest -- see :func:`_enumerate_grid`), builds a modified
    config via :func:`apply_assignment`, calls
    :func:`~segqc.eval.harness.evaluate_cohort` then
    :func:`~segqc.eval.metrics.compute_cohort_metrics`, and scores the
    result via *objective*. Selects ``best`` = the feasible candidate with
    the lowest score (``false_positive_rate``, ``None`` sorting as
    best/lowest), tie-broken by higher overall ``metrics.sensitivity``, then
    earliest grid order. Never mutates *cases*, *base_config*, or *axes*;
    performs no file I/O.

    Parameters
    ----------
    cases:
        The evaluation cohort, forwarded unchanged to ``evaluate_cohort`` for
        every candidate.
    base_config:
        The config each candidate's assignment is applied onto. Not mutated.
    axes:
        The axes defining the sweep grid. Not mutated.
    objective:
        The feasibility/scoring policy (default: floor
        ``sensitivity_floor=1.0``, minimise FPR).
    max_grid_size:
        The grid-size guard (default 512): raises before any evaluation
        when the Cartesian-product size exceeds this.
    positive_severity, correlation_method, dice_metric, failure_modes:
        Forwarded to ``evaluate_cohort``/``compute_cohort_metrics``
        respectively, with the same defaults those functions declare.
    reference, stratum, lower_pct, upper_pct:
        Forwarded unchanged to ``evaluate_cohort`` for every candidate (item
        092). ``reference=None`` (the default) preserves the original
        reference-blind behaviour.

    Returns
    -------
    CalibrationResult

    Raises
    ------
    segqc.io.SegQCInputError
        If the grid size exceeds *max_grid_size*, raised before any
        candidate is evaluated.
    """
    size = _grid_size(axes)
    if size > max_grid_size:
        raise SegQCInputError(
            f"calibrate_thresholds: grid size {size} exceeds max_grid_size "
            f"{max_grid_size}; narrow the axes or raise max_grid_size explicitly."
        )

    grid = _enumerate_grid(axes)

    candidates = []
    for index, assignment in enumerate(grid):
        candidate_config = apply_assignment(base_config, assignment, axes)
        cohort = evaluate_cohort(
            cases,
            candidate_config,
            positive_severity=positive_severity,
            reference=reference,
            stratum=stratum,
            lower_pct=lower_pct,
            upper_pct=upper_pct,
        )
        metrics = compute_cohort_metrics(
            cohort,
            correlation_method=correlation_method,
            dice_metric=dice_metric,
            failure_modes=failure_modes,
        )
        feasible, score = objective.evaluate(metrics)
        candidates.append(
            CandidateResult(
                assignment=dict(assignment),
                metrics=metrics,
                feasible=feasible,
                score=score,
                grid_index=index,
            )
        )

    def _sort_key(candidate: CandidateResult) -> Tuple[float, float, int]:
        overall_sensitivity = candidate.metrics.sensitivity
        # Higher sensitivity is better -> negate for ascending sort.
        neg_sensitivity = (
            -overall_sensitivity if overall_sensitivity is not None else 0.0
        )
        return (candidate.score, neg_sensitivity, candidate.grid_index)

    feasible_candidates = [c for c in candidates if c.feasible]
    if feasible_candidates:
        best = min(feasible_candidates, key=_sort_key)
        status = "ok"
        result_feasible = True
    else:
        best = None
        status = "no-feasible-setting"
        result_feasible = False

    return CalibrationResult(
        candidates=tuple(candidates),
        best=best,
        feasible=result_feasible,
        status=status,
        objective=objective,
        n_candidates=len(candidates),
    )


# --------------------------------------------------------------------------- #
# default_calibration_axes
# --------------------------------------------------------------------------- #


def default_calibration_axes() -> Tuple[ThresholdAxis, ...]:
    """Return a documented default grid over both swept rule families.

    These candidate values are **placeholders**: a runnable, documented
    default grid for exercising the calibration loop. The concrete
    production grid used for the shipped config is item 057's concern.

    Covers:

    - Stage-6 ``reference_delta`` (item 047): ``max_robust_z`` (a spread
      around the shipped default of ``3.5``) and
      ``max_distribution_distance`` (a spread around the shipped default of
      ``3.0``).
    - Stage-4 ``bounds`` (items 027/048): one representative
      ``max_volume_mm3`` sweep for the ``lumbar`` level group (a spread
      around the shipped default of ``120_000.0``).

    Returns
    -------
    Tuple[ThresholdAxis, ...]
    """
    return (
        ThresholdAxis(
            name="reference_delta.max_robust_z",
            rule_id="reference_delta",
            param_path=("max_robust_z",),
            values=(2.5, 3.0, 3.5, 4.0, 4.5),
        ),
        ThresholdAxis(
            name="reference_delta.max_distribution_distance",
            rule_id="reference_delta",
            param_path=("max_distribution_distance",),
            values=(2.0, 2.5, 3.0, 3.5, 4.0),
        ),
        ThresholdAxis(
            name="bounds.lumbar.max_volume_mm3",
            rule_id="bounds",
            param_path=("lumbar", "max_volume_mm3"),
            values=(90_000.0, 105_000.0, 120_000.0, 135_000.0, 150_000.0),
        ),
    )
