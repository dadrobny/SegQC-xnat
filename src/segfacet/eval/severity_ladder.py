"""Severity-ladder monotonicity & cross-mode specificity harness (item 100).

Item 099 proved *isolation on nine fixed corpus cases*: each of its eight
per-mode metrics (:mod:`segfacet.eval.per_mode`) attains its largest
deviation from baseline on its own §6 mode's single case. That is a
**one-point** result. This module builds the strictly stronger, **graded**
counterpart Stage 18's G2 acceptance actually asks for: for each of the
eight §6 failure modes, a **severity ladder** -- an ordered sequence of
rungs, rung 0 the untouched clean control and each later rung applying the
mode's perturbation operator at a strictly greater severity -- run through
item 099's :func:`~segfacet.eval.per_mode.compute_per_mode_metrics` at
*every* rung of *every* ladder (the full ladder x metric response surface,
not just the diagonal), then scored for:

* **monotonicity** -- is the designated metric non-decreasing/non-increasing
  (per its declared :class:`~segfacet.eval.per_mode.MetricSpec.direction`)
  and does it strictly change at every rung transition (a plateau, which a
  purely-directional check would pass, is treated as a failure);
* **cross-mode specificity** -- how large is the designated metric's
  response to *this* ladder's severity relative to every *foreign* metric's
  response to the *same* ladder.

The eight ladders
------------------
====  ========================  ==============  ======================  ==================
mode  metric (item 099)         operator        severity knob           kind
====  ========================  ==============  ======================  ==================
1     unanchored_foreground_fraction (up)   displace         displacement_mm         continuous
2     min_dominant_component_fraction (down) fragment         n_pieces                continuous
3     rogue_island_count (up)               inject_islands   n_islands               continuous
4     mislabelled_volume_fraction (up)      relabel_swap     n_affected_labels       affected-label-count
5     missing_level_count (up)              remove_level     n_affected_labels       affected-label-count
6     fov_clipped_label_count (up)          crop_at_border   n_affected_labels       affected-label-count
7     out_of_order_label_count (up)         sequence_break   --                      degenerate (2-rung)
8     overlapping_voxel_count (up)          force_overlap    overlap_depth           continuous
====  ========================  ==============  ======================  ==================

Plus one **supplementary** ladder, outside the eight and outside the
cross-mode matrix: mode 2's *fused* half via cumulative ``fuse`` steps (see
below).

Why three modes have no continuous knob
----------------------------------------
``relabel_swap``, ``sequence_break`` and ``remove_level`` take only
target-label selectors (no continuous physical parameter). Two of the three
get a genuine ladder from the *count of affected labels*; the third cannot:

* **Mode 4** (``relabel_swap``) -- 3 rungs. Each disjoint adjacent swap
  mislabels two whole bodies (``n_affected_labels`` steps 0 -> 2 -> 4 on the
  five-level base), so ``mislabelled_volume_fraction`` steps
  0.0 -> 0.4 -> 0.8. Only two disjoint adjacent pairs exist among five
  labels, so the ladder is 3 rungs, not 4 -- recorded, not hidden.
* **Mode 5** (``remove_level``) -- 4 rungs. The three interior levels
  (21, 22, 23) are removed one at a time; ``missing_level_count`` steps
  0 -> 1 -> 2 -> 3.
* **Mode 6** (``crop_at_border``) -- *its* metric (``fov_clipped_label_count``)
  is a **count of labels**, invariant to clip depth; ``crop_depth`` is
  therefore pinned at the corpus's ``5`` and the severity axis sweeps the
  *number of clipped labels* (20, then +21, then +22) instead.
* **Mode 7** (``sequence_break``) -- **degenerate**, 2 rungs, not merely
  inconvenient. Under the default (TPTBox, item 093) convention
  ``rank(v) == v - 1`` for every value 1-24, so no in-block relabel can
  produce a rank descent; the one transitional label that can (28 == T13,
  rank 19) always sorts last, contributing at most one descent.
  ``out_of_order_label_count`` is capped at ``1.0`` on this base -- a second
  break cannot add a second out-of-order label. Declared via
  :data:`DEGENERATE_LADDER_MODES`, never presented as graded.

The specificity bar
--------------------
For metric ``f`` on ladder ``L`` (rung 0 included)::

    span_f(L) = max_r v_f(r) - min_r v_f(r)

-- the *range* the ladder drives the metric through (its response to a
*change* in severity, not a deviation from baseline: a metric that jumps to
a fixed offset on a foreign ladder and then ignores that ladder's severity
*is* insensitive to that mode in the sense Stage 18 means). Then::

    response(m, f) = span_f(L_m) / span_f(L_f)     response(m, m) == 1.0
    margin(m)      = 1.0 / max_{f != m} response(m, f)   (inf when the max is 0)

A ladder is **strictly specific** when ``margin(m) > 1.0``. Pairs with
``response(m, f) >= COUPLING_THRESHOLD`` are **recorded couplings** --
measured, named, caused, frozen in :data:`KNOWN_CROSS_MODE_COUPLINGS` -- so a
real cross-mode leak is published rather than buried in a pass/fail bit.
:data:`RECORDED_MARGINS` freezes every mode's measured margin. Both tables
act as a *ratchet*: a future rule retune or feature change that flattens a
metric, or makes it more responsive to a foreign mode, must fail
(``measured_response <= recorded * 1.05``, ``measured_margin >= recorded *
0.95``) rather than quietly eroding the stage's claim.

Purity & determinism contract
------------------------------
Every function here is pure: no file I/O, no clock, no mutation of the base
image/array any rung is derived from. All randomness is banned by
construction -- every ladder step passes explicit target labels, so no
operator ever consults ``seeded_rng`` for a choice; :data:`LADDER_SEED` is
still threaded through every ``apply()`` call to honour the
``Perturbation`` signature. Every ``to_dict()`` returns a plain-JSON
structure that round-trips through ``json.dumps``/``json.loads`` unchanged.

Scope fence
-----------
This module does **not**:

* change any metric -- :mod:`segfacet.eval.per_mode` is untouched; the only
  route to a metric value is a call to
  :func:`~segfacet.eval.per_mode.compute_per_mode_metrics`;
* change any operator or the corpus -- :mod:`segfacet.synth` and
  ``tests/corpus/**`` are untouched; no new perturbation is registered; the
  missing ``fuse`` corpus case (item 099's insight) is not added here, it is
  measured in-memory via :data:`SUPPLEMENTARY_LADDERS` instead;
* change any rule, threshold, schema or CLI surface;
* aggregate over a real cohort or read a manifest (item 101's job);
* make a real-data claim -- every ladder here is synthetic.

Public API
----------
``LadderRungSpec``, ``LadderSpec``, ``LadderPoint``, ``LadderResult``,
``HarnessResult``, ``LadderVerdict``, ``HarnessVerdict``,
``CrossModeCoupling`` (all frozen dataclasses); ``SEVERITY_LADDERS``,
``SUPPLEMENTARY_LADDERS``, ``DEGENERATE_LADDER_MODES``,
``KNOWN_CROSS_MODE_COUPLINGS``, ``RECORDED_MARGINS``, ``COUPLING_THRESHOLD``,
``LADDER_SEED``; ``evaluate_ladder``, ``run_severity_harness``,
``score_harness``.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Tuple

import numpy as np

from segfacet.config import bundled_default_config
from segfacet.eval.per_mode import PER_MODE_METRIC_SPECS, PerModeMetrics, compute_per_mode_metrics
from segfacet.feature_report import overlap_to_dict
from segfacet.features.overlap import detect_overlaps
from segfacet.io import FacetInputError
from segfacet.pipeline import extract_feature_record
from segfacet.synth.clean_gt import DEFAULT_LEVELS, build_clean_spine
from segfacet.synth.perturbation import FAILURE_MODE_NAMES, get_perturbation

__all__ = [
    "LadderRungSpec",
    "LadderSpec",
    "LadderPoint",
    "LadderResult",
    "HarnessResult",
    "LadderVerdict",
    "HarnessVerdict",
    "CrossModeCoupling",
    "SEVERITY_LADDERS",
    "SUPPLEMENTARY_LADDERS",
    "DEGENERATE_LADDER_MODES",
    "KNOWN_CROSS_MODE_COUPLINGS",
    "RECORDED_MARGINS",
    "COUPLING_THRESHOLD",
    "LADDER_SEED",
    "evaluate_ladder",
    "run_severity_harness",
    "score_harness",
]


# --------------------------------------------------------------------------- #
# Module constants
# --------------------------------------------------------------------------- #

#: Every ladder step passes explicit target labels, so no operator ever
#: consults ``seeded_rng`` for a choice -- this seed only honours the
#: ``Perturbation.apply(labelmap, seed)`` signature, matching the committed
#: corpus recipe's seed (item 040).
LADDER_SEED: int = 0

#: A foreign metric's response to a ladder counts as a *recorded coupling*
#: once its span-ratio reaches this fraction of the metric's own full swing.
COUPLING_THRESHOLD: float = 0.25

#: The one §6 mode whose ladder is structurally incapable of more than two
#: rungs (see the module docstring's "why three modes have no continuous
#: knob" section, mode 7).
DEGENERATE_LADDER_MODES = frozenset({7})

#: The base :func:`~segfacet.synth.clean_gt.build_clean_spine` parameters
#: every ladder's rung 0 -- and every later rung's fresh copy -- derives
#: from. Identical to the committed corpus's ``_DEFAULT_BASE_PARAMS``
#: (``synth/corpus.py``), so item 099's measured baselines carry over
#: unchanged and the mode-8 ladder's AC19 cross-check against the corpus's
#: ``1950.0`` holds.
_BASE_PARAMS: Mapping[str, Any] = MappingProxyType(
    {
        "levels": tuple(DEFAULT_LEVELS),
        "spacing": (1.0, 1.0, 1.0),
        "curve_amplitude_mm": 6.0,
    }
)


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LadderRungSpec:
    """One rung of a severity ladder: an ordered list of perturbation steps.

    Attributes
    ----------
    index:
        Rung position, ``0`` for the clean control.
    severity:
        The rung's severity value on the ladder's declared axis. ``0.0`` for
        rung 0; strictly increasing thereafter.
    label:
        Human-readable label for this rung (e.g. ``"displacement_mm=8.0"``).
    steps:
        ``((operator_name, kwargs), ...)`` applied in order to a **fresh
        copy** of the ladder's base image. Empty for rung 0.
    """

    index: int
    severity: float
    label: str
    steps: Tuple[Tuple[str, Mapping[str, Any]], ...]

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "severity": self.severity,
            "label": self.label,
            "steps": [[name, dict(kwargs)] for name, kwargs in self.steps],
        }


@dataclass(frozen=True)
class LadderSpec:
    """Static declaration of one §6 mode's severity ladder.

    Attributes
    ----------
    failure_mode:
        The §6 mode key (``1``-``8``; the supplementary ``fuse`` ladder also
        carries ``2``, but is excluded from :data:`SEVERITY_LADDERS`).
    failure_mode_name:
        Verbatim from :data:`~segfacet.synth.perturbation.FAILURE_MODE_NAMES`.
    operator:
        The perturbation registry name every rung's step(s) use.
    severity_parameter:
        The operator constructor keyword (or ``"n_affected_labels"``) the
        severity axis represents.
    severity_kind:
        One of ``"continuous"``, ``"affected-label-count"``, ``"degenerate"``.
    rungs:
        The ordered :class:`LadderRungSpec` sequence, rung 0 first.
    rationale:
        Free-text rationale; non-empty and names the transitional-label cap
        (contains ``"28"``) for the degenerate mode-7 ladder.
    overlap_reconstruction:
        ``(target_label, neighbour_label)`` when this ladder needs the
        reconstructed ``overlaps`` block (mode 8 only); ``None`` otherwise.
    """

    failure_mode: int
    failure_mode_name: str
    operator: str
    severity_parameter: str
    severity_kind: str
    rungs: Tuple[LadderRungSpec, ...]
    rationale: str
    overlap_reconstruction: Optional[Tuple[int, int]]

    def to_dict(self) -> dict:
        return {
            "failure_mode": self.failure_mode,
            "failure_mode_name": self.failure_mode_name,
            "operator": self.operator,
            "severity_parameter": self.severity_parameter,
            "severity_kind": self.severity_kind,
            "rungs": [r.to_dict() for r in self.rungs],
            "rationale": self.rationale,
            "overlap_reconstruction": (
                list(self.overlap_reconstruction)
                if self.overlap_reconstruction is not None
                else None
            ),
            "degenerate": self.severity_kind == "degenerate",
        }


@dataclass(frozen=True)
class LadderPoint:
    """One rung's measured result: all eight per-mode metrics at that rung."""

    index: int
    severity: float
    label: str
    metrics: PerModeMetrics

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "severity": self.severity,
            "label": self.label,
            "metrics": self.metrics.to_dict(),
        }


@dataclass(frozen=True)
class LadderResult:
    """Raw per-rung measurements for one ladder -- no spans, no verdict."""

    spec: LadderSpec
    points: Tuple[LadderPoint, ...]

    def to_dict(self) -> dict:
        return {
            "spec": self.spec.to_dict(),
            "points": [p.to_dict() for p in self.points],
        }


@dataclass(frozen=True)
class HarnessResult:
    """The full ladder x metric response surface: all eight ladders plus the
    supplementary ``fuse`` ladder."""

    ladders: Tuple[LadderResult, ...]
    supplementary: Tuple[LadderResult, ...]
    base_params: Mapping[str, Any]

    def to_dict(self) -> dict:
        return {
            "ladders": [lr.to_dict() for lr in self.ladders],
            "supplementary": [lr.to_dict() for lr in self.supplementary],
            "base_params": _tuples_to_lists(dict(self.base_params)),
        }

    def by_mode(self, failure_mode: int) -> LadderResult:
        """Return the primary ladder result for *failure_mode* (``1``-``8``).

        Raises
        ------
        KeyError
            If no ladder in :attr:`ladders` has that ``failure_mode``.
        """
        for lr in self.ladders:
            if lr.spec.failure_mode == failure_mode:
                return lr
        raise KeyError(failure_mode)


@dataclass(frozen=True)
class CrossModeCoupling:
    """One measured, named, frozen cross-mode coupling entry.

    Attributes
    ----------
    ladder_mode:
        The ladder driving the foreign metric.
    foreign_mode:
        The metric mode being driven (``!= ladder_mode``).
    recorded_response:
        The measured ``response(ladder_mode, foreign_mode)``, rounded *up* to
        4 significant figures.
    cause:
        Non-empty free-text naming the operator artefact responsible.
    """

    ladder_mode: int
    foreign_mode: int
    recorded_response: float
    cause: str


@dataclass(frozen=True)
class LadderVerdict:
    """The scored verdict for one ladder.

    Attributes
    ----------
    failure_mode:
        This ladder's mode.
    status:
        ``"strict"`` (uncoupled, ``margin > 1.0``) or ``"coupled"`` (carries
        a :data:`KNOWN_CROSS_MODE_COUPLINGS` entry).
    responses:
        ``{metric_mode: response(failure_mode, metric_mode)}`` over all eight
        metrics; ``responses[failure_mode] == 1.0``.
    margin:
        ``1.0 / max_{f != failure_mode} responses[f]`` (``math.inf`` if that
        max is ``0.0``).
    coupled_modes:
        Foreign modes this ladder is recorded as coupled to (empty when
        ``status == "strict"``).
    failures:
        Human-readable failure reasons; empty iff this ladder passed.
    monotone:
        Whether the designated metric moved monotonically in its declared
        direction.
    strictly_changed:
        Whether the designated metric changed strictly at every rung
        transition.
    """

    failure_mode: int
    status: str
    responses: Mapping[int, float]
    margin: float
    coupled_modes: Tuple[int, ...]
    failures: Tuple[str, ...]
    monotone: bool
    strictly_changed: bool

    def to_dict(self) -> dict:
        return {
            "failure_mode": self.failure_mode,
            "status": self.status,
            "responses": {str(k): v for k, v in self.responses.items()},
            "margin": self.margin,
            "coupled_modes": list(self.coupled_modes),
            "failures": list(self.failures),
            "monotone": self.monotone,
            "strictly_changed": self.strictly_changed,
        }


@dataclass(frozen=True)
class HarnessVerdict:
    """The full scored verdict over every primary ladder.

    Attributes
    ----------
    passed:
        ``False`` iff any ladder is non-monotone, plateaus, or violates its
        recorded coupling/margin ratchet. A *recorded* coupling is a fact,
        not a failure.
    per_ladder:
        ``{failure_mode: LadderVerdict}``.
    """

    passed: bool
    per_ladder: Mapping[int, LadderVerdict]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "per_ladder": {str(k): v.to_dict() for k, v in self.per_ladder.items()},
        }

    def summary(self) -> str:
        """A one-page, human-readable summary naming every coupled and every
        degenerate ladder -- the Stage-18 G2 claim in one page."""
        lines = [f"Severity-ladder harness verdict: passed={self.passed}"]
        for mode in sorted(self.per_ladder):
            lv = self.per_ladder[mode]
            if lv.status == "coupled":
                foreign = ", ".join(str(f) for f in lv.coupled_modes)
                lines.append(
                    f"  ladder {mode}: COUPLED with mode(s) {foreign} "
                    f"(margin={lv.margin:.4g})"
                )
            else:
                lines.append(f"  ladder {mode}: strict (margin={lv.margin:.4g})")
            if mode in DEGENERATE_LADDER_MODES:
                rationale = SEVERITY_LADDERS[mode].rationale if mode in SEVERITY_LADDERS else ""
                lines.append(f"    DEGENERATE ladder (2 rungs): {rationale}")
            for f in lv.failures:
                lines.append(f"    FAILURE: {f}")
        return "\n".join(lines)


def _tuples_to_lists(obj: Any) -> Any:
    """Recursively coerce any ``tuple`` in *obj* to a ``list``.

    Duplicated from :mod:`segfacet.eval.per_mode` (itself duplicated from
    ``segfacet.eval.metrics`` -- see that module for the rationale):
    ``dataclasses.asdict`` preserves tuple-typed fields as Python tuples,
    which do not compare equal to their own post ``json.dumps``/``json.loads``
    round-trip counterpart (always a list).
    """
    if isinstance(obj, tuple):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, list):
        return [_tuples_to_lists(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _tuples_to_lists(v) for k, v in obj.items()}
    return obj


# --------------------------------------------------------------------------- #
# The ladder registry -- the declarative table
# --------------------------------------------------------------------------- #


def _rung0(label: str = "clean control") -> LadderRungSpec:
    return LadderRungSpec(index=0, severity=0.0, label=label, steps=())


def _rung(index: int, severity: float, label: str, steps) -> LadderRungSpec:
    return LadderRungSpec(index=index, severity=float(severity), label=label, steps=tuple(steps))


def _mode1_ladder() -> LadderSpec:
    rungs = [_rung0()]
    for i, s in enumerate((4.0, 8.0, 12.0, 16.0), start=1):
        rungs.append(
            _rung(
                i,
                s,
                f"displacement_mm={s}",
                [("displace", {"target_label": 22, "displacement_mm": s})],
            )
        )
    return LadderSpec(
        failure_mode=1,
        failure_mode_name=FAILURE_MODE_NAMES[1],
        operator="displace",
        severity_parameter="displacement_mm",
        severity_kind="continuous",
        rungs=tuple(rungs),
        rationale="",
        overlap_reconstruction=None,
    )


def _mode2_ladder() -> LadderSpec:
    rungs = [_rung0()]
    for i, s in enumerate((2.0, 3.0, 4.0, 5.0), start=1):
        rungs.append(
            _rung(
                i,
                s,
                f"n_pieces={int(s)}",
                [("fragment", {"target_label": 22, "n_pieces": int(s)})],
            )
        )
    return LadderSpec(
        failure_mode=2,
        failure_mode_name=FAILURE_MODE_NAMES[2],
        operator="fragment",
        severity_parameter="n_pieces",
        severity_kind="continuous",
        rungs=tuple(rungs),
        rationale="",
        overlap_reconstruction=None,
    )


def _mode3_ladder() -> LadderSpec:
    rungs = [_rung0()]
    for i, s in enumerate((1.0, 2.0, 3.0, 4.0), start=1):
        rungs.append(
            _rung(
                i,
                s,
                f"n_islands={int(s)}",
                [
                    (
                        "inject_islands",
                        {"target_label": 22, "n_islands": int(s), "island_voxels": 27},
                    )
                ],
            )
        )
    return LadderSpec(
        failure_mode=3,
        failure_mode_name=FAILURE_MODE_NAMES[3],
        operator="inject_islands",
        severity_parameter="n_islands",
        severity_kind="continuous",
        rungs=tuple(rungs),
        rationale="",
        overlap_reconstruction=None,
    )


def _mode4_ladder() -> LadderSpec:
    # Two disjoint adjacent swaps: (20, 21) then (22, 23); label 24 untouched.
    # Five labels admit only two disjoint adjacent pairs -- 3 rungs, not 4.
    swap1 = ("relabel_swap", {"target_label": 20, "neighbour_label": 21})
    swap2 = ("relabel_swap", {"target_label": 22, "neighbour_label": 23})
    rungs = [
        _rung0(),
        _rung(1, 2.0, "n_affected_labels=2", [swap1]),
        _rung(2, 4.0, "n_affected_labels=4", [swap1, swap2]),
    ]
    return LadderSpec(
        failure_mode=4,
        failure_mode_name=FAILURE_MODE_NAMES[4],
        operator="relabel_swap",
        severity_parameter="n_affected_labels",
        severity_kind="affected-label-count",
        rungs=tuple(rungs),
        rationale=(
            "Only 2 disjoint adjacent label pairs exist among the 5-level "
            "base, so this ladder is 3 rungs (not 4)."
        ),
        overlap_reconstruction=None,
    )


def _mode5_ladder() -> LadderSpec:
    # Cumulative interior removals: 21, then +22, then +23.
    rem21 = ("remove_level", {"target_label": 21})
    rem22 = ("remove_level", {"target_label": 22})
    rem23 = ("remove_level", {"target_label": 23})
    rungs = [
        _rung0(),
        _rung(1, 1.0, "n_affected_labels=1", [rem21]),
        _rung(2, 2.0, "n_affected_labels=2", [rem21, rem22]),
        _rung(3, 3.0, "n_affected_labels=3", [rem21, rem22, rem23]),
    ]
    return LadderSpec(
        failure_mode=5,
        failure_mode_name=FAILURE_MODE_NAMES[5],
        operator="remove_level",
        severity_parameter="n_affected_labels",
        severity_kind="affected-label-count",
        rungs=tuple(rungs),
        rationale="Removes the 3 interior levels (21, 22, 23) one at a time.",
        overlap_reconstruction=None,
    )


def _mode6_ladder() -> LadderSpec:
    # Cumulative crops (anterior face, crop_depth pinned at the corpus's 5):
    # 20, then +21, then +22 -- fov_clipped_label_count is a count of labels,
    # invariant to crop_depth, so the severity axis is the number cropped.
    crop20 = ("crop_at_border", {"target_label": 20, "face": "anterior", "crop_depth": 5})
    crop21 = ("crop_at_border", {"target_label": 21, "face": "anterior", "crop_depth": 5})
    crop22 = ("crop_at_border", {"target_label": 22, "face": "anterior", "crop_depth": 5})
    rungs = [
        _rung0(),
        _rung(1, 1.0, "n_affected_labels=1", [crop20]),
        _rung(2, 2.0, "n_affected_labels=2", [crop20, crop21]),
        _rung(3, 3.0, "n_affected_labels=3", [crop20, crop21, crop22]),
    ]
    return LadderSpec(
        failure_mode=6,
        failure_mode_name=FAILURE_MODE_NAMES[6],
        operator="crop_at_border",
        severity_parameter="n_affected_labels",
        severity_kind="affected-label-count",
        rungs=tuple(rungs),
        rationale=(
            "fov_clipped_label_count is a count of labels, invariant to "
            "crop_depth (pinned at the corpus's 5); the severity axis is "
            "the number of clipped labels instead."
        ),
        overlap_reconstruction=None,
    )


def _mode7_ladder() -> LadderSpec:
    # Degenerate: out_of_order_label_count is capped at 1.0 on this base --
    # 28 (T13) is the only value whose canonical rank (19) falls below its
    # integer position, and it always sorts last, contributing at most one
    # descent. A second break cannot add a second out-of-order label.
    rungs = [
        _rung0(),
        _rung(1, 1.0, "sequence_break", [("sequence_break", {})]),
    ]
    return LadderSpec(
        failure_mode=7,
        failure_mode_name=FAILURE_MODE_NAMES[7],
        operator="sequence_break",
        severity_parameter="n/a",
        severity_kind="degenerate",
        rungs=tuple(rungs),
        rationale=(
            "Structurally capped at 1 rung of severity: under the default "
            "(TPTBox) convention, rank(v) == v - 1 for every value 1-24, so "
            "no in-block relabel produces a rank descent. The one label "
            "that can -- 28 (T13), rank 19 -- always sorts last and "
            "contributes at most one descent, so out_of_order_label_count "
            "is capped at 1.0 and a second break cannot add a second "
            "out-of-order label."
        ),
        overlap_reconstruction=None,
    )


def _mode8_ladder() -> LadderSpec:
    rungs = [_rung0()]
    for i, s in enumerate((1.0, 2.0, 3.0, 4.0), start=1):
        rungs.append(
            _rung(
                i,
                s,
                f"overlap_depth={int(s)}",
                [
                    (
                        "force_overlap",
                        {"target_label": 20, "neighbour_label": 21, "overlap_depth": int(s)},
                    )
                ],
            )
        )
    return LadderSpec(
        failure_mode=8,
        failure_mode_name=FAILURE_MODE_NAMES[8],
        operator="force_overlap",
        severity_parameter="overlap_depth",
        severity_kind="continuous",
        rungs=tuple(rungs),
        rationale="",
        overlap_reconstruction=(20, 21),
    )


def _fuse_ladder() -> LadderSpec:
    # Cumulative fuse absorptions: 21 into 20, then +22, then +23 -- the
    # fused half of §6 mode 2 (fragment covers the fragmented half), measured
    # in memory rather than as a tenth corpus recipe entry (see the item's
    # Assumptions).
    fuse21 = ("fuse", {"target_label": 20, "neighbour_label": 21})
    fuse22 = ("fuse", {"target_label": 20, "neighbour_label": 22})
    fuse23 = ("fuse", {"target_label": 20, "neighbour_label": 23})
    rungs = [
        _rung0(),
        _rung(1, 1.0, "n_fused_neighbours=1", [fuse21]),
        _rung(2, 2.0, "n_fused_neighbours=2", [fuse21, fuse22]),
        _rung(3, 3.0, "n_fused_neighbours=3", [fuse21, fuse22, fuse23]),
    ]
    return LadderSpec(
        failure_mode=2,
        failure_mode_name=FAILURE_MODE_NAMES[2],
        operator="fuse",
        severity_parameter="n_fused_neighbours",
        severity_kind="affected-label-count",
        rungs=tuple(rungs),
        rationale=(
            "Supplementary: closes mode 2's fused half (fragment covers the "
            "fragmented half). Excluded from the eight-ladder cross-mode "
            "matrix so that matrix stays a square 8x8."
        ),
        overlap_reconstruction=None,
    )


#: The eight §6-mode severity ladders, keyed 1-8. ``CLEAN_CONTROL_MODE`` (0)
#: is deliberately not a key.
SEVERITY_LADDERS: Mapping[int, LadderSpec] = MappingProxyType(
    {
        1: _mode1_ladder(),
        2: _mode2_ladder(),
        3: _mode3_ladder(),
        4: _mode4_ladder(),
        5: _mode5_ladder(),
        6: _mode6_ladder(),
        7: _mode7_ladder(),
        8: _mode8_ladder(),
    }
)

#: The supplementary ``fuse`` ladder closing mode 2's fused half -- outside
#: the eight-ladder cross-mode matrix (``score_harness`` ignores it entirely).
SUPPLEMENTARY_LADDERS: Tuple[LadderSpec, ...] = (_fuse_ladder(),)


# --------------------------------------------------------------------------- #
# Case construction & per-rung measurement
# --------------------------------------------------------------------------- #


def _apply_steps(base_img, steps: Tuple[Tuple[str, Mapping[str, Any]], ...]):
    """Apply *steps* in order to a fresh derivation of *base_img*.

    Never mutates *base_img* -- every registered operator already copies its
    input array before writing, and this function itself never writes to
    ``base_img``'s array.

    Raises
    ------
    KeyError
        If a step names an unregistered operator (propagated from
        :func:`~segfacet.synth.perturbation.get_perturbation`).
    segfacet.io.FacetInputError
        If any operator rejects its parameters/state (e.g. an
        out-of-FOV displacement) -- propagates immediately, never truncating
        the ladder.
    """
    current = base_img
    for name, kwargs in steps:
        operator_cls = get_perturbation(name)
        operator = operator_cls(**dict(kwargs))
        result = operator.apply(current, LADDER_SEED)
        current = result.labelmap
    return current


def _measure(
    base_arr: np.ndarray,
    perturbed_img,
    spec: LadderSpec,
    rung: LadderRungSpec,
    config,
) -> LadderPoint:
    """Build the :class:`LadderPoint` for one already-perturbed rung."""
    perturbed_arr = np.asanyarray(perturbed_img.dataobj)
    record = extract_feature_record(perturbed_img, config)

    if spec.overlap_reconstruction is not None:
        target, neighbour = spec.overlap_reconstruction
        stack = np.stack([perturbed_arr == target, base_arr == neighbour])
        pairs = detect_overlaps(stack, np.array([target, neighbour]))
        record = dict(record)
        record["overlaps"] = [overlap_to_dict(p) for p in pairs]

    spacing = tuple(float(z) for z in perturbed_img.header.get_zooms()[:3])
    metrics = compute_per_mode_metrics(
        record,
        candidate=perturbed_arr,
        gt=base_arr,
        spacing=spacing,
    )
    return LadderPoint(index=rung.index, severity=rung.severity, label=rung.label, metrics=metrics)


# --------------------------------------------------------------------------- #
# evaluate_ladder
# --------------------------------------------------------------------------- #


def evaluate_ladder(spec: LadderSpec, *, base=None, config=None) -> LadderResult:
    """Run every rung of *spec* and return the raw per-rung measurements.

    Parameters
    ----------
    spec:
        The :class:`LadderSpec` to evaluate.
    base:
        A :class:`~segfacet.synth.clean_gt.CleanSpine` to derive every rung
        from. Defaults to ``build_clean_spine(**_BASE_PARAMS)`` -- the same
        default L1-L5 base the committed corpus uses.
    config:
        A :class:`~segfacet.config.HeuristicConfig`. Defaults to
        :func:`~segfacet.config.bundled_default_config`.

    Returns
    -------
    LadderResult
        Carries raw data only: no spans, no responses, no verdict --
        scoring is a pure function of the result (see :func:`score_harness`).

    Raises
    ------
    KeyError
        If a rung names an unregistered operator.
    segfacet.io.FacetInputError
        If any rung's operator rejects its parameters/state.
    """
    if base is None:
        base = build_clean_spine(**_BASE_PARAMS)
    if config is None:
        config = bundled_default_config()

    base_seg = base.seg_img
    base_arr = np.array(np.asanyarray(base_seg.dataobj), copy=True)

    points: List[LadderPoint] = []
    for rung in spec.rungs:
        perturbed_img = _apply_steps(base_seg, rung.steps)
        points.append(_measure(base_arr, perturbed_img, spec, rung, config))
    return LadderResult(spec=spec, points=tuple(points))


# --------------------------------------------------------------------------- #
# run_severity_harness
# --------------------------------------------------------------------------- #


def run_severity_harness(*, base=None, config=None) -> HarnessResult:
    """Evaluate the eight §6-mode ladders plus the supplementary one.

    Parameters
    ----------
    base, config:
        As in :func:`evaluate_ladder`.

    Returns
    -------
    HarnessResult
    """
    if base is None:
        base = build_clean_spine(**_BASE_PARAMS)
    if config is None:
        config = bundled_default_config()

    base_seg = base.seg_img
    base_arr = np.array(np.asanyarray(base_seg.dataobj), copy=True)
    spacing = tuple(float(z) for z in base_seg.header.get_zooms()[:3])

    # Rung 0 is the same clean base for every ladder (its reconstructed
    # overlaps block is empty regardless), so it is computed once and shared
    # -- see the item spec's Implementation Steps.
    shared_rung0_record = extract_feature_record(base_seg, config)
    shared_rung0_metrics = compute_per_mode_metrics(
        shared_rung0_record,
        candidate=base_arr,
        gt=base_arr,
        spacing=spacing,
    )
    shared_rung0 = LadderPoint(
        index=0, severity=0.0, label="clean control", metrics=shared_rung0_metrics
    )

    def _build(spec: LadderSpec) -> LadderResult:
        points: List[LadderPoint] = [shared_rung0]
        for rung in spec.rungs[1:]:
            perturbed_img = _apply_steps(base_seg, rung.steps)
            points.append(_measure(base_arr, perturbed_img, spec, rung, config))
        return LadderResult(spec=spec, points=tuple(points))

    ladders = tuple(_build(SEVERITY_LADDERS[mode]) for mode in sorted(SEVERITY_LADDERS))
    supplementary = tuple(_build(spec) for spec in SUPPLEMENTARY_LADDERS)

    return HarnessResult(
        ladders=ladders,
        supplementary=supplementary,
        base_params=dict(_BASE_PARAMS),
    )


# --------------------------------------------------------------------------- #
# score_harness
# --------------------------------------------------------------------------- #


def _span(values: List[float]) -> float:
    return max(values) - min(values)


def score_harness(harness: HarnessResult, *, assignment: Optional[Mapping[int, int]] = None) -> HarnessVerdict:
    """Score *harness*'s response surface: monotonicity, specificity, ratchets.

    Parameters
    ----------
    harness:
        A :class:`HarnessResult`, typically from :func:`run_severity_harness`.
        Only :attr:`HarnessResult.ladders` is read -- ``supplementary`` is
        ignored entirely (AC21).
    assignment:
        ``{ladder_mode: metric_mode}``, defaulting to the identity read from
        :data:`~segfacet.eval.per_mode.PER_MODE_METRIC_SPECS`'s keys. Maps
        each ladder to the metric scored as its "designated" one for
        monotonicity/strict-change purposes; the response/margin surface
        itself is assignment-independent (a ladder's response to every
        metric is always reported).

    Returns
    -------
    HarnessVerdict

    Raises
    ------
    segfacet.io.FacetInputError
        If *assignment* maps a ladder to a metric mode outside ``1..8``.
    KeyError
        If *assignment* is missing an entry for a ladder present in
        *harness*.
    """
    if assignment is None:
        assignment = {mode: mode for mode in PER_MODE_METRIC_SPECS}

    ladders = harness.ladders
    if not ladders:
        return HarnessVerdict(passed=True, per_ladder=MappingProxyType({}))

    # Spans over every (ladder_mode, metric_mode) pair -- assignment-independent.
    spans: Dict[int, Dict[int, float]] = {}
    for lr in ladders:
        m = lr.spec.failure_mode
        spans[m] = {}
        for f in range(1, 9):
            values = [pt.metrics.by_mode(f).value for pt in lr.points]
            spans[m][f] = _span(values)

    per_ladder: Dict[int, LadderVerdict] = {}
    for lr in ladders:
        m = lr.spec.failure_mode
        designated = assignment[m]
        if designated not in PER_MODE_METRIC_SPECS:
            raise FacetInputError(
                f"score_harness: assignment[{m}]={designated!r} is not a "
                "valid metric mode (1..8)."
            )

        responses: Dict[int, float] = {}
        for f in range(1, 9):
            if f not in spans:
                responses[f] = math.inf
                continue
            denom = spans[f][f]
            responses[f] = math.inf if denom == 0.0 else spans[m][f] / denom

        others = [responses[f] for f in range(1, 9) if f != m]
        mx = max(others) if others else 0.0
        margin = math.inf if mx == 0.0 else 1.0 / mx

        failures: List[str] = []
        n_points = len(lr.points)
        if n_points < 2:
            failures.append(
                f"ladder {m}: only {n_points} rung(s) -- cannot assess "
                "monotonicity or strict change (zero-span guard, not a "
                "division by zero)."
            )
            monotone = True
            strictly_changed = False
        else:
            direction = PER_MODE_METRIC_SPECS[designated].direction
            values = [pt.metrics.by_mode(designated).value for pt in lr.points]
            if direction == "increases":
                monotone = all(a <= b for a, b in zip(values, values[1:]))
            else:
                monotone = all(a >= b for a, b in zip(values, values[1:]))
            strictly_changed = all(abs(b - a) > 1e-9 for a, b in zip(values, values[1:]))

            if not monotone:
                failures.append(
                    f"ladder {m} scored against metric {designated} "
                    f"({PER_MODE_METRIC_SPECS[designated].metric_name}): not "
                    f"monotone in the declared direction ({direction}): {values!r}."
                )
            if not strictly_changed:
                failures.append(
                    f"ladder {m} scored against metric {designated} "
                    f"({PER_MODE_METRIC_SPECS[designated].metric_name}): "
                    f"plateaus somewhere across rungs: {values!r}."
                )

            # A designated metric can happen to move monotonically and
            # non-trivially on the WRONG ladder too (a small, real,
            # deterministic side-effect) without that ladder actually being
            # the metric's best/most-specific driver. Require this ladder's
            # response to the designated metric to be at least as large as
            # the response the metric's own true ladder achieves for itself
            # (which is exactly 1.0) -- true by construction for an honest
            # (identity) assignment, and the criterion a mis-assignment
            # (AC18's negative control) must fail.
            own_response = responses.get(designated, math.inf)
            if own_response < 1.0 - 1e-9:
                failures.append(
                    f"ladder {m} scored against metric {designated} "
                    f"({PER_MODE_METRIC_SPECS[designated].metric_name}): "
                    f"this ladder is not that metric's best/most-specific "
                    f"driver (response={own_response!r} < 1.0, the response "
                    f"metric {designated}'s own true ladder achieves for "
                    "itself)."
                )

        coupling_entries = [c for c in KNOWN_CROSS_MODE_COUPLINGS if c.ladder_mode == m]
        if coupling_entries:
            status = "coupled"
            coupled_modes = tuple(sorted(c.foreign_mode for c in coupling_entries))
            for c in coupling_entries:
                measured = responses.get(c.foreign_mode, math.inf)
                if measured > c.recorded_response * 1.05:
                    failures.append(
                        f"ladder {m}: coupling ratchet violated for foreign "
                        f"mode {c.foreign_mode}: measured response "
                        f"{measured!r} exceeds recorded "
                        f"{c.recorded_response!r} * 1.05."
                    )
        else:
            status = "strict"
            coupled_modes = ()

        recorded_margin = RECORDED_MARGINS.get(m)
        if recorded_margin is not None and not (margin >= recorded_margin * 0.95):
            failures.append(
                f"ladder {m}: margin ratchet violated: measured margin "
                f"{margin!r} is below recorded {recorded_margin!r} * 0.95."
            )

        per_ladder[m] = LadderVerdict(
            failure_mode=m,
            status=status,
            responses=MappingProxyType(responses),
            margin=margin,
            coupled_modes=coupled_modes,
            failures=tuple(failures),
            monotone=monotone,
            strictly_changed=strictly_changed,
        )

    passed = all(len(lv.failures) == 0 for lv in per_ladder.values())
    return HarnessVerdict(passed=passed, per_ladder=MappingProxyType(per_ladder))


# --------------------------------------------------------------------------- #
# Frozen ratchet constants -- filled by running the harness once and
# transcribing the measured values (recorded responses rounded UP, recorded
# margins rounded DOWN, both to 4 significant figures, so the ratchet has no
# float-equality knife edge). See the item's Decisions log for the measured
# run this was transcribed from.
# --------------------------------------------------------------------------- #

#: Two measured cross-mode couplings. Mode 6 -> metric 1 was anticipated by
#: item 099 (see the module docstring and the item's Assumptions):
#: ``crop_at_border``, ``displace`` and ``force_overlap`` all translate a
#: body rigidly, so all three put candidate foreground over GT background --
#: and mode 1's own ladder is FOV-capped (~19.8 mm max ``displacement_mm`` on
#: this base) while mode 6's scales linearly with the number of cropped
#: labels, so it *exceeds* the strict bar (response > 1.0), exactly as
#: predicted. Mode 8 -> metric 1 was **not** anticipated by item 099 (whose
#: Assumptions named only ``{(6, 1)}``) and is recorded here per the item's
#: instruction to call out any additional measured coupling in the Decisions
#: log: ``force_overlap`` shifts the whole target body by ``gap +
#: overlap_depth`` voxels along the stacking axis, and the constant 15 mm
#: inter-body gap dominates that shift, so most of mode 8's
#: ``unanchored_foreground_fraction`` response is a rigid-translation
#: artefact largely independent of ``overlap_depth`` -- its span nearly
#: matches mode 1's own full swing (measured response 0.9629, margin only
#: ~1.039), even though mode 8's own designated metric
#: (``overlapping_voxel_count``) remains a clean, strictly specific isolator.
KNOWN_CROSS_MODE_COUPLINGS: Tuple[CrossModeCoupling, ...] = (
    CrossModeCoupling(
        ladder_mode=6,
        foreign_mode=1,
        recorded_response=2.79,
        cause=(
            "crop_at_border rigidly translates each cropped body toward the "
            "FOV face (like displace/force_overlap), placing candidate "
            "foreground over GT background; mode 6's n_affected_labels axis "
            "scales this linearly across 3 rungs while mode 1's own ladder "
            "is capped by the FOV (~19.8mm max displacement_mm on this base)."
        ),
    ),
    CrossModeCoupling(
        ladder_mode=8,
        foreign_mode=1,
        recorded_response=0.9629,
        cause=(
            "force_overlap shifts the whole target body by gap + "
            "overlap_depth voxels along the stacking axis; the constant "
            "15mm inter-body gap dominates that shift, so most of the "
            "unanchored-foreground signal is a rigid-translation artefact "
            "largely independent of overlap_depth, nearly matching mode 1's "
            "own full swing."
        ),
    ),
)

#: Every mode's measured margin (``1.0 / max_{f != m} response(m, f)``),
#: rounded down to 4 significant figures (``math.inf`` kept as-is where the
#: measured max foreign response is exactly ``0.0``).
RECORDED_MARGINS: Mapping[int, float] = MappingProxyType(
    {
        1: math.inf,
        2: math.inf,
        3: 112.0,
        4: math.inf,
        5: math.inf,
        6: 0.3585,
        7: math.inf,
        8: 1.038,
    }
)
