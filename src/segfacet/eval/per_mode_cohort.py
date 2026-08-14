"""Cohort-level per-mode magnitude surface & run-vs-run comparator (item 101).

Items 099/100 built and validated a **per-case** magnitude surface: eight
named scalar metrics, one per Section 6 failure mode
(:data:`segfacet.eval.per_mode.PER_MODE_METRIC_SPECS`), each proven monotone
in its own mode's severity (item 100). Nothing before this module aggregated
those metrics over a cohort, and nothing diffed two cohorts. This module
closes that gap with two entry points:

``summarise_run_per_mode``
    Folds a :class:`~segfacet.eval.harness.CohortEvaluation` whose records
    carry a populated ``per_mode`` field (:func:`segfacet.eval.harness.
    evaluate_cohort`'s opt-in ``per_mode=True`` hook) into one
    :class:`RunPerModeSummary` -- eight :class:`ModeAggregate`\\ s (mean,
    min, max, total, ``n_with_value``) plus, when a
    :class:`segfacet.eval.metrics.CohortMetrics` is supplied, item 054's
    detection-rate column read **verbatim** and never recomputed.
``compare_runs``
    Diffs two :class:`RunPerModeSummary`\\ s (the same cohort, two runs of a
    segmenter) into a :class:`RunComparison`: eight :class:`ModeDelta`\\ s
    plus an ``attributed_mode`` -- the mode whose value moved the largest
    *normalised* amount.

The comparison arithmetic (item 109)
-------------------------------------
Per-mode metrics are not commensurable -- ``rogue_island_count`` is a count,
``mislabelled_volume_fraction`` is a fraction. For mode ``m``, with
``baseline`` taken from ``PER_MODE_METRIC_SPECS[m].baseline``::

    value_a           = mean over run A's cases whose mode-m value is not None
    value_b           = mean over run B's cases whose mode-m value is not None
    delta             = value_b - value_a

Item 109 replaced the original per-comparison ``scale = max(abs(value_a -
baseline), abs(value_b - baseline))``: that adaptive divisor saturated to
exactly ``+/-1.0`` whenever *either* run sat on its metric's baseline --
seven of the eight baselines are ``0.0`` -- so any comparison in which two or
more modes returned to baseline tied at 1.0, and ``attributed_mode`` fell
through to the lowest-mode tie-break instead of reflecting which mode moved
further. ``scale`` is now a **fixed property of the metric's own
classification**, declared once in the module-local ``MODE_SCALE_SPECS``
table and never recomputed from ``value_a``/``value_b``:

- **Bounded metrics** (a mode whose ``ModeScaleSpec.full_swing`` is not
  ``None`` -- today modes 1/2/4, the three ``*_fraction`` metrics) scale by
  their derivable **full swing**: the distance from ``baseline`` to the far
  end of the metric's own ``0..1`` range, a constant with no free parameter
  and no supervision dependency.
- **Reviewed-threshold metrics** (``ModeScaleSpec.reference_excursion`` set)
  scale by that declared constant. No shipped spec sets one today (AC4) --
  the field exists as a mechanism for a future, explicitly human-reviewed
  declaration, never a default.
- **Everything else is raw**: ``scale`` and ``normalised_delta`` are both
  ``None``, and the raw ``delta`` remains available on the same
  :class:`ModeDelta`. Today that is every count metric (modes 3/5/6/7/8):
  ``rogue_island_count`` is a *maximum over per-label entries*, so a
  scan-level denominator would change the quantity rather than scale it;
  ``missing_level_count``'s only natural denominator -- the levels the scan
  was expected to contain -- is ground-truth-derived and therefore barred
  from ever appearing in a divisor (no normalisation factor may introduce a
  supervision dependency, even for a metric whose own ``source`` is
  ``candidate_vs_gt``).

``normalised_delta = delta / scale`` when ``scale`` is known (``0.0`` exactly
when ``scale == 0.0``), else ``None``; it never divides by zero, ``nan`` or
``inf``. ``worsened`` is direction-aware and computed from ``delta`` alone,
independently of ``scale``: the metric moving *away* from ``baseline`` in the
mode's declared ``direction`` (``"increases"``/``"decreases"``, mirrored from
``PER_MODE_METRIC_SPECS``) is worse -- mode 2's
``min_dominant_component_fraction`` decreases with severity, so a *negative*
delta there is a regression, the opposite sign of every other mode.

``attributed_mode`` ranks only :class:`ModeDelta` entries carrying a
non-``None``, non-zero ``normalised_delta`` -- unnormalisable modes (raw
``delta`` but no ``scale``) are never silently dropped from view: they are
named in :attr:`RunComparison.excluded_modes`. Among the ranked entries,
``attributed_mode`` is the one with the greatest ``abs(normalised_delta)``;
the lowest-mode tie-break applies **only** on an exact equality of that
magnitude, never as a fallback for "nothing was comparable". When no entry
carries a normalised delta at all (or every one of them is exactly ``0.0``),
``attributed_mode`` is ``None`` and :attr:`RunComparison.unattributable_reason`
states why -- distinguishing "no metric here is normalisable" from "every
normalisable metric agreed nothing moved".

Purity contract
-----------------
Both entry points open no file, read no clock, and never mutate their inputs
(a ``CohortEvaluation``, a ``CohortMetrics``, or a prior ``RunPerModeSummary``);
both are idempotent -- calling either twice on the same inputs returns equal
results.

Scope fence
-----------
This module does **not**:

- implement any new Dice/Jaccard/overlap arithmetic, and never calls
  :func:`segfacet.eval.overlap.compute_overlap` -- every magnitude comes from
  :func:`segfacet.eval.per_mode.compute_per_mode_metrics` (already attached
  to each case by the harness hook), and the aggregate Dice context is the
  mean of the per-case ``PerModeMetrics.mean_dice`` /
  ``.volume_weighted_dice`` fields item 099 already carries;
- read, import, or recompute anything from :mod:`segfacet.eval.metrics` --
  detection rates are read verbatim from a caller-supplied
  ``CohortMetrics.per_mode`` (item 054), never duplicated;
- register a rule, add a threshold, or change a verdict;
- read a manifest, drive the pipeline, or write a file -- this module is
  pure aggregation/comparison over already-computed records.

Public API
----------
``ModeAggregate``
    Frozen dataclass: one mode's cohort-aggregated statistics plus the
    verbatim detection-rate column.
``RunPerModeSummary``
    Frozen dataclass: one run's eight :class:`ModeAggregate`\\ s plus the
    aggregate Dice context; has ``to_dict()``, ``by_mode()``, ``from_dict()``.
``ModeDelta``
    Frozen dataclass: one mode's run-vs-run delta arithmetic.
``RunComparison``
    Frozen dataclass: two runs' full per-mode diff plus ``attributed_mode``;
    has ``to_dict()``, ``by_mode()``, ``summary()``.
``summarise_run_per_mode(cohort, *, run_id, metrics=None, run_manifest=None)
-> RunPerModeSummary``
    Aggregate a cohort's per-case ``per_mode`` records into one summary.
``compare_runs(run_a, run_b) -> RunComparison``
    Diff two same-cohort summaries into a comparison.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from segfacet.eval.per_mode import PER_MODE_METRIC_SPECS
from segfacet.io import FacetInputError

__all__ = [
    "ModeAggregate",
    "RunPerModeSummary",
    "ModeDelta",
    "RunComparison",
    "ModeScaleSpec",
    "MODE_SCALE_SPECS",
    "summarise_run_per_mode",
    "compare_runs",
]


# --------------------------------------------------------------------------- #
# JSON-shape helper (duplicated from segfacet.eval.per_mode -- see that
# module's docstring for the rationale; this module may not import it)
# --------------------------------------------------------------------------- #


def _tuples_to_lists(obj: Any) -> Any:
    """Recursively coerce any ``tuple`` in *obj* to a ``list``."""
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- #
# Per-mode scale classification (item 109)
#
# Additive and local to this module -- deliberately NOT a field on
# ``segfacet.eval.per_mode.MetricSpec``. That file is item 112's authorised
# territory this stage; the per-metric classification a normalisation rule
# needs lives here instead, next to the code that applies the supervision and
# review rules, without contesting that ownership. See the module docstring's
# "The comparison arithmetic" section for the rules this table encodes.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModeScaleSpec:
    """One failure mode's ``normalised_delta`` scale classification.

    Attributes
    ----------
    full_swing:
        The metric's derivable full swing -- the distance from its
        ``PER_MODE_METRIC_SPECS[mode].baseline`` to the far end of its own
        bounded range -- when the metric is bounded by construction (today,
        the three ``*_fraction`` metrics: modes 1/2/4, always ``1.0`` since
        every such metric's range is ``0..1``). ``None`` for every unbounded
        metric (a count with no derivable, supervision-free denominator).
        Fixed at classification time; never recomputed from a comparison's
        actual values.
    reference_excursion:
        An optional declared scale for an otherwise-unbounded metric.
        **Setting this field is a human-review decision, not a tuning
        knob**: project policy (item 109) requires an explicit, recorded
        rationale before any unbounded metric is assigned a divisor, because
        the sole disqualifying failure mode -- a denominator that quietly
        imports a ground-truth-derived quantity -- is not mechanically
        detectable from the number alone. Every metric shipped by this item
        leaves this field unset (``None``); it exists as a mechanism for a
        future reviewed declaration (see the module Decisions log for the
        standing candidate, ``rogue_island_count``, and why its value is
        still TBC).
    """

    full_swing: Optional[float]
    reference_excursion: Optional[float] = None


#: ``{1..8: ModeScaleSpec}`` -- one entry per ``PER_MODE_METRIC_SPECS`` mode.
#: Bounded metrics (1/2/4) declare their fixed ``full_swing``; every other
#: mode declares ``full_swing=None`` and an unset ``reference_excursion``
#: (AC4 -- no threshold is set by this item).
MODE_SCALE_SPECS: Dict[int, ModeScaleSpec] = {
    1: ModeScaleSpec(full_swing=1.0),  # unanchored_foreground_fraction: 0.0 -> 1.0
    2: ModeScaleSpec(full_swing=1.0),  # min_dominant_component_fraction: 1.0 -> 0.0
    3: ModeScaleSpec(full_swing=None),  # rogue_island_count: raw (per-label max)
    4: ModeScaleSpec(full_swing=1.0),  # mislabelled_volume_fraction: 0.0 -> 1.0
    5: ModeScaleSpec(full_swing=None),  # missing_level_count: raw (GT-derived denom barred)
    6: ModeScaleSpec(full_swing=None),  # fov_clipped_label_count: raw
    7: ModeScaleSpec(full_swing=None),  # out_of_order_label_count: raw
    8: ModeScaleSpec(full_swing=None),  # overlapping_voxel_count: raw
}


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ModeAggregate:
    """One Section 6 failure mode's cohort-aggregated magnitude statistics.

    Attributes
    ----------
    failure_mode, failure_mode_name, metric_name, direction, baseline:
        Copied verbatim from ``PER_MODE_METRIC_SPECS[failure_mode]``.
    n_cases:
        Number of cases contributing to this summary overall (cases whose
        ``per_mode`` field was populated), the same for every mode.
    n_with_value:
        Number of those cases whose mode-specific value is not ``None``.
    mean, minimum, maximum, total:
        The arithmetic mean/min/max/sum over exactly the ``n_with_value``
        non-``None`` values; all ``None`` (``total`` included) when
        ``n_with_value == 0``.
    detection_rate, n_detection_cases:
        The matching :class:`segfacet.eval.metrics.PerModeSensitivity`'s
        ``sensitivity``/``n_cases``, read verbatim; ``None``/``0`` when no
        ``CohortMetrics`` was supplied or the mode is absent from it.
    """

    failure_mode: int
    failure_mode_name: str
    metric_name: str
    direction: str
    baseline: float
    n_cases: int
    n_with_value: int
    mean: Optional[float]
    minimum: Optional[float]
    maximum: Optional[float]
    total: Optional[float]
    detection_rate: Optional[float]
    n_detection_cases: int


@dataclass(frozen=True)
class RunPerModeSummary:
    """One run's cohort-level per-mode magnitude surface.

    Attributes
    ----------
    run_id:
        Free-text label identifying this run.
    case_ids:
        The ``case_id``\\ s (in cohort order) whose ``per_mode`` field was
        populated and folded into this summary.
    n_cases:
        ``len(case_ids)``.
    per_mode:
        Exactly eight :class:`ModeAggregate`\\ s, in ascending
        ``failure_mode`` order (``1..8``).
    mean_dice, volume_weighted_dice:
        The mean, over cases carrying a non-``None`` value, of item 099's
        per-case aggregate overlap context; ``None`` when no case carried
        one.
    run_manifest:
        Optional Stage 17 run-manifest block (item 096), embedded verbatim;
        ``None`` when not supplied.
    """

    run_id: str
    case_ids: Tuple[str, ...]
    n_cases: int
    per_mode: Tuple[ModeAggregate, ...]
    mean_dice: Optional[float]
    volume_weighted_dice: Optional[float]
    run_manifest: Optional[dict] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this summary."""
        return _tuples_to_lists(dataclasses.asdict(self))

    def by_mode(self, failure_mode: int) -> ModeAggregate:
        """Return the entry for *failure_mode* (``1..8``) by key, not position.

        Raises
        ------
        KeyError
            If no entry has that ``failure_mode``.
        """
        for entry in self.per_mode:
            if entry.failure_mode == failure_mode:
                return entry
        raise KeyError(failure_mode)

    @classmethod
    def from_dict(cls, d: Any) -> "RunPerModeSummary":
        """Rebuild a :class:`RunPerModeSummary` from :meth:`to_dict`'s output.

        This is the path ``segfacet compare-runs`` uses to rehydrate a
        summary out of a caller-supplied ``eval_report.json``'s
        ``per_mode_magnitude`` block -- untrusted input, so every failure
        mode raises :class:`segfacet.io.FacetInputError`, never a bare
        ``KeyError``/``TypeError``.
        """
        if not isinstance(d, Mapping):
            raise FacetInputError(
                "RunPerModeSummary.from_dict: expected a JSON object (mapping), "
                f"got {type(d).__name__}."
            )
        try:
            run_id = d["run_id"]
            case_ids = d["case_ids"]
            n_cases = d["n_cases"]
            per_mode_raw = d["per_mode"]
            dice_mean = d["mean_dice"]
            vwd_mean = d["volume_weighted_dice"]
        except KeyError as exc:
            raise FacetInputError(
                f"RunPerModeSummary.from_dict: missing required key {exc}."
            ) from exc
        run_manifest = d.get("run_manifest")

        if not isinstance(run_id, str):
            raise FacetInputError(
                f"RunPerModeSummary.from_dict: run_id must be a string, got "
                f"{type(run_id).__name__}."
            )
        if not isinstance(case_ids, (list, tuple)):
            raise FacetInputError(
                "RunPerModeSummary.from_dict: case_ids must be a list, got "
                f"{type(case_ids).__name__}."
            )
        if not isinstance(per_mode_raw, (list, tuple)) or len(per_mode_raw) != 8:
            raise FacetInputError(
                "RunPerModeSummary.from_dict: per_mode must be a list of "
                f"exactly 8 entries, got {per_mode_raw!r}."
            )

        try:
            per_mode = tuple(ModeAggregate(**entry) for entry in per_mode_raw)
        except TypeError as exc:
            raise FacetInputError(
                f"RunPerModeSummary.from_dict: malformed per_mode entry: {exc}"
            ) from exc

        return cls(
            run_id=run_id,
            case_ids=tuple(case_ids),
            n_cases=n_cases,
            per_mode=per_mode,
            mean_dice=dice_mean,
            volume_weighted_dice=vwd_mean,
            run_manifest=run_manifest,
        )


@dataclass(frozen=True)
class ModeDelta:
    """One Section 6 failure mode's run-vs-run delta.

    Attributes
    ----------
    failure_mode, failure_mode_name, metric_name, direction, baseline:
        Copied verbatim from ``PER_MODE_METRIC_SPECS[failure_mode]``.
    value_a, value_b:
        The two runs' ``ModeAggregate.mean`` values.
    delta:
        ``value_b - value_a``, or ``None`` when either side is ``None``.
    scale:
        The mode's fixed ``MODE_SCALE_SPECS[failure_mode].full_swing`` (or,
        if set, ``.reference_excursion``); ``None`` when the metric is
        unbounded and no reviewed threshold is declared, or when ``delta``
        is ``None``. Never derived from ``value_a``/``value_b`` (item 109).
    normalised_delta:
        ``delta / scale``; exactly ``0.0`` when ``scale == 0.0``; ``None``
        when ``delta`` is ``None`` or ``scale`` is ``None`` (the metric is
        not normalisable for this comparison).
    worsened:
        ``None`` iff ``delta`` is ``None``; otherwise ``True`` iff the metric
        moved away from ``baseline`` in its declared ``direction``, ``False``
        otherwise (including ``delta == 0.0``).
    detection_rate_a, detection_rate_b, detection_rate_delta:
        The two runs' ``ModeAggregate.detection_rate`` values and their
        difference (``None`` when either side is ``None``).
    """

    failure_mode: int
    failure_mode_name: str
    metric_name: str
    direction: str
    baseline: float
    value_a: Optional[float]
    value_b: Optional[float]
    delta: Optional[float]
    scale: Optional[float]
    normalised_delta: Optional[float]
    worsened: Optional[bool]
    detection_rate_a: Optional[float]
    detection_rate_b: Optional[float]
    detection_rate_delta: Optional[float]


@dataclass(frozen=True)
class RunComparison:
    """A full run-vs-run per-mode comparison of two same-cohort summaries.

    Attributes
    ----------
    run_a_id, run_b_id:
        The two summaries' ``run_id``\\ s (may be identical -- comparing a
        cohort against itself under a different config is allowed).
    n_cases, case_ids:
        The shared cohort's size and sorted ``case_id`` set.
    per_mode:
        Exactly eight :class:`ModeDelta`\\ s, in ascending ``failure_mode``
        order.
    mean_dice_a, mean_dice_b, mean_dice_delta:
        The two runs' aggregate Dice and their difference.
    volume_weighted_dice_a, volume_weighted_dice_b, volume_weighted_dice_delta:
        As above, for the volume-weighted aggregate Dice.
    attributed_mode, attributed_mode_name, attributed_metric_name:
        The mode with the greatest ``abs(normalised_delta)`` among entries
        that carry a non-``None``, non-zero ``normalised_delta`` (ties
        broken to the lowest mode number, and reached **only** on an exact
        tie -- never as a fallback for "nothing was normalisable"); ``None``
        when no entry qualifies -- see ``unattributable_reason``.
    run_manifest_a, run_manifest_b:
        The two runs' ``run_manifest`` blocks, embedded verbatim.

    Properties
    ----------
    excluded_modes:
        Item 109 (AC8/AC8b): the ``failure_mode``\\ s, in ascending order,
        that carry a real (non-``None``) ``delta`` but no
        ``normalised_delta`` -- i.e. modes that had data to compare but are
        not normalisable, so they are visibly excluded from the attribution
        ranking rather than silently dropped. A mode with no data at all on
        either side (``delta is None``) is not "excluded" -- there was
        nothing to rank. Computed on access, not stored as a dataclass
        field -- but :meth:`to_dict` copies its value (as a ``list``) into
        the serialised dict under the same key, so a reader of the JSON
        report finds it there too, not only on the live object.
    unattributable_reason:
        Item 109 (AC9/AC8b): ``None`` whenever ``attributed_mode`` is not
        ``None``; otherwise a non-empty, human-readable string distinguishing
        "no mode here is normalisable" from "every normalisable mode agreed
        nothing moved". Computed on access, not stored as a dataclass field
        -- but :meth:`to_dict` copies its value into the serialised dict
        under the same key, exactly like ``excluded_modes`` above.
    """

    run_a_id: str
    run_b_id: str
    n_cases: int
    case_ids: Tuple[str, ...]
    per_mode: Tuple[ModeDelta, ...]
    mean_dice_a: Optional[float]
    mean_dice_b: Optional[float]
    mean_dice_delta: Optional[float]
    volume_weighted_dice_a: Optional[float]
    volume_weighted_dice_b: Optional[float]
    volume_weighted_dice_delta: Optional[float]
    attributed_mode: Optional[int]
    attributed_mode_name: Optional[str]
    attributed_metric_name: Optional[str]
    run_manifest_a: Optional[dict] = None
    run_manifest_b: Optional[dict] = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable nested dict for this comparison.

        Item 109 (AC8b): in addition to every stored dataclass field, the
        dict carries ``excluded_modes`` (a ``list`` of ``failure_mode`` ints,
        possibly empty) and ``unattributable_reason`` (a string or ``None``)
        -- the same values :attr:`excluded_modes`/:attr:`unattributable_reason`
        compute on access. Both are additive keys layered onto
        ``dataclasses.asdict(self)``'s output, not stored fields, so a
        reader of the serialised JSON report can see which modes were
        excluded from attribution and why without inferring it by filtering
        ``per_mode`` entries for ``delta is not None and normalised_delta is
        None``.
        """
        d = _tuples_to_lists(dataclasses.asdict(self))
        d["excluded_modes"] = list(self.excluded_modes)
        d["unattributable_reason"] = self.unattributable_reason
        return d

    def by_mode(self, failure_mode: int) -> ModeDelta:
        """Return the entry for *failure_mode* (``1..8``) by key, not position.

        Raises
        ------
        KeyError
            If no entry has that ``failure_mode``.
        """
        for entry in self.per_mode:
            if entry.failure_mode == failure_mode:
                return entry
        raise KeyError(failure_mode)

    @property
    def excluded_modes(self) -> Tuple[int, ...]:
        """``failure_mode``\\ s with real data but no ``normalised_delta``.

        See the class docstring's "Properties" section. Computed on every
        access from ``self.per_mode`` rather than stored as a dataclass field,
        but :meth:`to_dict` layers it onto the serialised output explicitly
        (item 109 AC8b): a reader of the JSON must be able to *read* which
        modes were excluded, not infer it from a null ``normalised_delta``.
        """
        return tuple(
            entry.failure_mode
            for entry in self.per_mode
            if entry.delta is not None and entry.normalised_delta is None
        )

    @property
    def unattributable_reason(self) -> Optional[str]:
        """Why ``attributed_mode is None``, or ``None`` when it is not.

        See the class docstring's "Properties" section. Computed on every
        access rather than stored as a dataclass field, but :meth:`to_dict`
        layers it onto the serialised output explicitly (item 109 AC8b) --
        this branch is exactly where the reason string is non-null and most
        needed, so it must survive serialisation.
        """
        if self.attributed_mode is not None:
            return None
        normalisable = [
            entry for entry in self.per_mode if entry.normalised_delta is not None
        ]
        if not normalisable:
            return (
                "no mode is attributable: every candidate metric in this "
                "comparison is not normalisable (raw count metrics carry no "
                "declared scale) -- see excluded_modes for which ones."
            )
        return (
            "no mode is attributable: every normalisable mode's "
            "normalised_delta is exactly 0.0 -- nothing moved."
        )

    def summary(self) -> str:
        """Return a single-line free-text summary naming the attributed mode."""
        if self.attributed_mode is None:
            return (
                f"compare-runs {self.run_a_id!r} vs {self.run_b_id!r}: "
                "no mode moved (every mode's normalised delta is zero or unavailable)."
            )
        top = self.by_mode(self.attributed_mode)
        return (
            f"compare-runs {self.run_a_id!r} vs {self.run_b_id!r}: "
            f"attributed to mode {self.attributed_mode} "
            f"({self.attributed_mode_name}, {self.attributed_metric_name}), "
            f"normalised_delta={top.normalised_delta:+.3f}"
        )


# --------------------------------------------------------------------------- #
# summarise_run_per_mode
# --------------------------------------------------------------------------- #


def summarise_run_per_mode(
    cohort: Any,
    *,
    run_id: str,
    metrics: Optional[Any] = None,
    run_manifest: Optional[dict] = None,
) -> RunPerModeSummary:
    """Fold a cohort's per-case ``per_mode`` records into one run summary.

    Parameters
    ----------
    cohort:
        Any object exposing ``.cases`` -- an iterable of records each
        carrying a ``case_id`` and a ``per_mode``
        (:class:`segfacet.eval.per_mode.PerModeMetrics` or ``None``)
        attribute. Typically a
        :class:`~segfacet.eval.harness.CohortEvaluation` produced with
        ``evaluate_cohort(..., per_mode=True)``. Never mutated.
    run_id:
        Free-text label for this run, carried onto the returned summary.
    metrics:
        Optional :class:`segfacet.eval.metrics.CohortMetrics` (item 054).
        When given, each mode's ``detection_rate``/``n_detection_cases`` is
        read verbatim from the matching ``PerModeSensitivity`` entry; never
        recomputed. ``None`` (default) leaves every detection column
        ``None``/``0``.
    run_manifest:
        Optional Stage 17 run-manifest block (item 096), embedded verbatim.

    Returns
    -------
    RunPerModeSummary

    Raises
    ------
    segfacet.io.FacetInputError
        If *cohort* is non-empty and **every** record's ``per_mode`` is
        ``None`` -- almost always a caller forgetting
        ``evaluate_cohort(..., per_mode=True)`` -- rather than silently
        returning eight empty aggregates.
    """
    all_records = list(cohort.cases)
    valid_records = [c for c in all_records if c.per_mode is not None]

    if all_records and not valid_records:
        raise FacetInputError(
            "summarise_run_per_mode: every case's per_mode is None -- did "
            "you forget evaluate_cohort(..., per_mode=True)? A cohort with "
            "no per-mode data cannot be summarised."
        )

    case_ids = tuple(c.case_id for c in valid_records)
    n_cases = len(case_ids)

    detection_by_mode: Dict[int, Any] = {}
    if metrics is not None:
        for entry in metrics.per_mode:
            if entry.failure_mode is not None:
                detection_by_mode[entry.failure_mode] = entry

    aggregates: List[ModeAggregate] = []
    dice_values: List[float] = []
    vwd_values: List[float] = []
    for record in valid_records:
        if record.per_mode.mean_dice is not None:
            dice_values.append(record.per_mode.mean_dice)
        if record.per_mode.volume_weighted_dice is not None:
            vwd_values.append(record.per_mode.volume_weighted_dice)

    for mode in range(1, 9):
        spec = PER_MODE_METRIC_SPECS[mode]
        values = [
            r.per_mode.by_mode(mode).value
            for r in valid_records
            if r.per_mode.by_mode(mode).value is not None
        ]
        n_with_value = len(values)
        if n_with_value == 0:
            mode_mean = mode_min = mode_max = mode_total = None
        else:
            mode_total = float(sum(values))
            mode_mean = mode_total / n_with_value
            mode_min = float(min(values))
            mode_max = float(max(values))

        sens_entry = detection_by_mode.get(mode)
        if sens_entry is None:
            detection_rate = None
            n_detection_cases = 0
        else:
            detection_rate = sens_entry.sensitivity
            n_detection_cases = sens_entry.n_cases

        aggregates.append(
            ModeAggregate(
                failure_mode=spec.failure_mode,
                failure_mode_name=spec.failure_mode_name,
                metric_name=spec.metric_name,
                direction=spec.direction,
                baseline=spec.baseline,
                n_cases=n_cases,
                n_with_value=n_with_value,
                mean=mode_mean,
                minimum=mode_min,
                maximum=mode_max,
                total=mode_total,
                detection_rate=detection_rate,
                n_detection_cases=n_detection_cases,
            )
        )

    run_dice_mean = float(sum(dice_values)) / len(dice_values) if dice_values else None
    run_vwd_mean = float(sum(vwd_values)) / len(vwd_values) if vwd_values else None

    return RunPerModeSummary(
        run_id=run_id,
        case_ids=case_ids,
        n_cases=n_cases,
        per_mode=tuple(aggregates),
        mean_dice=run_dice_mean,
        volume_weighted_dice=run_vwd_mean,
        run_manifest=run_manifest,
    )


# --------------------------------------------------------------------------- #
# compare_runs
# --------------------------------------------------------------------------- #


def _delta_pair(
    value_a: Optional[float], value_b: Optional[float]
) -> Optional[float]:
    """Return ``value_b - value_a``, or ``None`` when either side is ``None``."""
    if value_a is None or value_b is None:
        return None
    return value_b - value_a


def compare_runs(run_a: RunPerModeSummary, run_b: RunPerModeSummary) -> RunComparison:
    """Diff two same-cohort :class:`RunPerModeSummary`\\ s into a :class:`RunComparison`.

    Parameters
    ----------
    run_a, run_b:
        The two summaries to compare. Never mutated.

    Returns
    -------
    RunComparison

    Raises
    ------
    segfacet.io.FacetInputError
        If ``run_a.case_ids`` and ``run_b.case_ids``, taken as sets, differ --
        naming at least one differing id. Identical sets in a different
        order compare successfully (order is not identity).
    """
    set_a = set(run_a.case_ids)
    set_b = set(run_b.case_ids)
    if set_a != set_b:
        differing = sorted(set_a.symmetric_difference(set_b))
        raise FacetInputError(
            "compare_runs: run_a and run_b do not cover the same cohort -- "
            f"case id(s) present on only one side: {differing!r}."
        )
    case_ids = tuple(sorted(set_a))
    n_cases = len(case_ids)

    per_mode: List[ModeDelta] = []
    for mode in range(1, 9):
        spec = PER_MODE_METRIC_SPECS[mode]
        scale_spec = MODE_SCALE_SPECS[mode]
        agg_a = run_a.by_mode(mode)
        agg_b = run_b.by_mode(mode)
        value_a = agg_a.mean
        value_b = agg_b.mean

        delta = _delta_pair(value_a, value_b)
        if delta is None:
            scale = None
            normalised_delta = None
            worsened = None
        else:
            # item 109: scale is a fixed property of the metric's own
            # classification (MODE_SCALE_SPECS), never adaptively recomputed
            # from value_a/value_b -- that adaptive form is exactly what
            # saturated to +/-1.0 whenever either run sat on baseline.
            if scale_spec.full_swing is not None:
                scale = scale_spec.full_swing
            elif scale_spec.reference_excursion is not None:
                scale = scale_spec.reference_excursion
            else:
                scale = None
            normalised_delta = (
                None if scale is None else (0.0 if scale == 0.0 else delta / scale)
            )
            if delta == 0.0:
                worsened = False
            elif spec.direction == "increases":
                worsened = delta > 0.0
            else:
                worsened = delta < 0.0

        per_mode.append(
            ModeDelta(
                failure_mode=spec.failure_mode,
                failure_mode_name=spec.failure_mode_name,
                metric_name=spec.metric_name,
                direction=spec.direction,
                baseline=spec.baseline,
                value_a=value_a,
                value_b=value_b,
                delta=delta,
                scale=scale,
                normalised_delta=normalised_delta,
                worsened=worsened,
                detection_rate_a=agg_a.detection_rate,
                detection_rate_b=agg_b.detection_rate,
                detection_rate_delta=_delta_pair(
                    agg_a.detection_rate, agg_b.detection_rate
                ),
            )
        )

    dice_a = run_a.mean_dice
    dice_b = run_b.mean_dice
    vwd_a = run_a.volume_weighted_dice
    vwd_b = run_b.volume_weighted_dice

    best_mode: Optional[int] = None
    best_abs: Optional[float] = None
    for entry in per_mode:
        nd = entry.normalised_delta
        if nd is None or nd == 0.0:
            continue
        magnitude = abs(nd)
        if best_abs is None or magnitude > best_abs:
            best_mode = entry.failure_mode
            best_abs = magnitude

    if best_mode is None:
        attributed_name = None
        attributed_metric = None
    else:
        attributed_spec = PER_MODE_METRIC_SPECS[best_mode]
        attributed_name = attributed_spec.failure_mode_name
        attributed_metric = attributed_spec.metric_name

    return RunComparison(
        run_a_id=run_a.run_id,
        run_b_id=run_b.run_id,
        n_cases=n_cases,
        case_ids=case_ids,
        per_mode=tuple(per_mode),
        mean_dice_a=dice_a,
        mean_dice_b=dice_b,
        mean_dice_delta=_delta_pair(dice_a, dice_b),
        volume_weighted_dice_a=vwd_a,
        volume_weighted_dice_b=vwd_b,
        volume_weighted_dice_delta=_delta_pair(vwd_a, vwd_b),
        attributed_mode=best_mode,
        attributed_mode_name=attributed_name,
        attributed_metric_name=attributed_metric,
        run_manifest_a=run_a.run_manifest,
        run_manifest_b=run_b.run_manifest,
    )
