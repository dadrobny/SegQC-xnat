"""Observed-range column for the generated feature catalogue (item 124).

For every catalogue leaf path, computes an :class:`ObservedRange` carrying
two independent populations plus a derived verdict:

- **corpus** -- the numeric values realised across
  :func:`segfacet.catalogue.iter_driver_records`, the in-package synthetic
  driver set. It never accuses a feature of being dead: a flat corpus range
  is reported as ``"constant-synthetic"``, never ``"degenerate"`` (the
  corpus's nine fixtures share one base geometry, so a flat corpus range says
  as much about the fixture as about the feature).
- **reference** -- the aggregated ``min``/``max`` of the matching feature in
  the committed real-GT reference distribution
  (:func:`segfacet.reference.artifact.bundled_production_reference`, or an
  injected artifact). Only this population can produce the ``"degenerate"``
  verdict.

Why two populations, and what the magnitude floor is calibrated against, is
in the item spec's Description --
``docs/aide/items/124-observed-range-column-in-the-catalogue.md``.

**Coverage limitation.** Only the 21 feature names carried by the reference
distribution's vocabulary can ever resolve onto a leaf path and therefore
ever read ``"degenerate"``; the remaining numeric paths get their corpus
numbers reported and no verdict stronger than ``"constant-synthetic"``.

Scope fence
-----------
This module adds no extractor, no rule, no threshold. It never mutates the
``status`` field or ``feature_docs.STATUS_OVERRIDES``, and never recomputes
anything from the VerSe19 cohort -- the reference population is read from the
committed artifact only, so generation stays hermetic on a machine with no
dataset. Heavy imports (``segfacet.catalogue``, ``segfacet.reference.*``) are
deferred into function bodies so importing this module alone stays cheap and
no import cycle forms with ``catalogue.py``.

Public API
----------
``NEGLIGIBLE_MAGNITUDE``
    The unit-agnostic magnitude floor (``1e-3``) below which a population is
    not ``informative``.
``PopulationRange``, ``ObservedRange``
    Frozen dataclasses.
``iter_leaf_values(record) -> dict[str, list]``
    A value-collecting sibling of ``catalogue._walk_leaf_paths``.
``resolve_reference_features(leaf_paths) -> dict[str, str]``
    ``{reference_feature_name: leaf_path}``, three ordered resolution rules.
``build_observed_ranges(*, driver_records=None, reference=None) -> dict[str, ObservedRange]``
    The whole computation, one entry per realised/reference-resolved path.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

__all__ = [
    "NEGLIGIBLE_MAGNITUDE",
    "PopulationRange",
    "ObservedRange",
    "iter_leaf_values",
    "resolve_reference_features",
    "build_observed_ranges",
]

#: Magnitude floor below which a population is not "informative" -- one
#: micron, three orders of magnitude below the finest achievable CT voxel
#: spacing, and equally negligible read as HU, as a count, or as a
#: dimensionless ratio. See the item spec's Assumptions for the calibration.
NEGLIGIBLE_MAGNITUDE: float = 1e-3

#: The two augmented drivers (``iter_driver_records``'s "Two augmented
#: drivers" block) -- hand-constructed placeholder dataclass instances, never
#: real feature-record data. A path realised by no other driver is a
#: hand-typed placeholder, not a genuinely varying feature (AC7/AC8).
_PLACEHOLDER_DRIVER_IDS: Tuple[str, ...] = ("image_features", "reference_delta")

_VERDICTS = frozenset(
    {"varies", "degenerate", "constant-synthetic", "placeholder", "non-numeric", "unobserved"}
)


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PopulationRange:
    """One population's observed numeric range for one leaf path."""

    population: str
    source: Tuple[str, ...]
    covered: bool
    count: Optional[int]
    minimum: Optional[float]
    maximum: Optional[float]
    span: Optional[float]
    magnitude: Optional[float]
    informative: bool


@dataclass(frozen=True)
class ObservedRange:
    """One leaf path's whole observed-range verdict: both populations plus
    the derived, closed-vocabulary verdict (see module docstring)."""

    numeric: Optional[bool]
    corpus: PopulationRange
    reference: PopulationRange
    verdict: str


def _empty_population(population: str, source: Tuple[str, ...] = ()) -> PopulationRange:
    return PopulationRange(
        population=population,
        source=source,
        covered=False,
        count=None,
        minimum=None,
        maximum=None,
        span=None,
        magnitude=None,
        informative=False,
    )


def _population_from_values(
    population: str, source: Tuple[str, ...], values: Sequence[float]
) -> PopulationRange:
    if not values:
        return _empty_population(population, source)
    minimum = min(values)
    maximum = max(values)
    magnitude = max(abs(minimum), abs(maximum))
    return PopulationRange(
        population=population,
        source=source,
        covered=True,
        count=len(values),
        minimum=minimum,
        maximum=maximum,
        span=maximum - minimum,
        magnitude=magnitude,
        informative=magnitude > NEGLIGIBLE_MAGNITUDE,
    )


# =========================================================================== #
# iter_leaf_values -- a value-collecting sibling of catalogue._walk_leaf_paths
# =========================================================================== #


def _append_leaf_value(bucket: List[Any], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, bool):
        # bool is never numeric -- checked before the numeric test, so a
        # boolean leaf is excluded from its path's value list even though
        # the path itself is still recorded (with an empty list) by the
        # caller. This keeps a bool-only path classifiable as "non-numeric"
        # rather than silently aggregated as 0/1.
        return
    bucket.append(value)


def _walk_leaf_values(value: Any, path: str, sink: Dict[str, List[Any]]) -> None:
    if isinstance(value, dict):
        if not value:
            if path:
                sink.setdefault(path, [])
            return
        for key, sub in value.items():
            sub_path = f"{path}.{key}" if path else str(key)
            _walk_leaf_values(sub, sub_path, sink)
        return

    if isinstance(value, list):
        if value and all(isinstance(el, dict) for el in value):
            container_path = f"{path}[]" if path else "[]"
            for el in value:
                _walk_leaf_values(el, container_path, sink)
            return
        # Empty list, or a scalar (non-dict-element) list -> a single leaf,
        # collecting every element's value (not just the path).
        leaf_path = f"{path}[]" if path else "[]"
        bucket = sink.setdefault(leaf_path, [])
        for el in value:
            _append_leaf_value(bucket, el)
        return

    # Scalar leaf (str / int / float / bool / None).
    if path:
        bucket = sink.setdefault(path, [])
        _append_leaf_value(bucket, value)


def iter_leaf_values(record: Mapping[str, Any]) -> Dict[str, List[Any]]:
    """Walk *record* to ``{normalised_leaf_path: [value, ...]}``.

    Every leaf path the same walk in ``catalogue._walk_leaf_paths`` would
    discover gets a key here too -- even one whose only value is ``None`` or
    a ``bool`` (both excluded from the value list itself, per the module
    docstring), or an empty dict/list. A scalar list is collected
    element-wise: every element's value lands in the shared path's list, not
    just the path. Pure -- never mutates *record*. ``iter_leaf_values({})``
    returns ``{}``.
    """
    from segfacet.catalogue import normalise_leaf_path

    raw: Dict[str, List[Any]] = {}
    _walk_leaf_values(dict(record) if record else {}, "", raw)

    result: Dict[str, List[Any]] = {}
    for raw_path, values in raw.items():
        norm = normalise_leaf_path(raw_path)
        result.setdefault(norm, []).extend(values)
    return result


# =========================================================================== #
# Reference-name resolution (three ordered rules; AC2/AC23)
# =========================================================================== #


def _last_segment(path: str) -> str:
    return path.rstrip("[]").rsplit(".", 1)[-1]


def resolve_reference_features(leaf_paths: Set[str]) -> Dict[str, str]:
    """``{reference_feature_name: leaf_path}`` for every name resolvable
    against *leaf_paths*, by three ordered rules (first match wins):

    1. The inverse of ``feature_docs.PATH_ALIASES``.
    2. A name in ``reference.ingest.INGESTED_INTENSITY_FEATURES``, whose
       ``intensity_`` prefix stripped gives the last segment of a path under
       ``image_features.per_label.{label}.first_order``.
    3. Otherwise, the unique leaf path whose last segment equals the name --
       an ambiguous last-segment match (more than one candidate) resolves to
       none of them (AC23), mirroring item 110's AC11b discipline.
    """
    from segfacet import feature_docs as _feature_docs_module
    from segfacet.reference.ingest import INGESTED_INTENSITY_FEATURES

    leaf_set = set(leaf_paths)
    resolved: Dict[str, str] = {}

    # Rule 1: PATH_ALIASES.
    for name, path in _feature_docs_module.PATH_ALIASES.items():
        if path in leaf_set:
            resolved[name] = path

    # Rule 2: INGESTED_INTENSITY_FEATURES -> image_features first_order.
    for name in INGESTED_INTENSITY_FEATURES:
        if name in resolved or not name.startswith("intensity_"):
            continue
        segment = name[len("intensity_") :]
        target = f"image_features.per_label.{{label}}.first_order.{segment}"
        if target in leaf_set:
            resolved[name] = target

    # Rule 3: unique last-segment match among the remaining leaf paths.
    by_last_segment: Dict[str, List[str]] = defaultdict(list)
    for path in leaf_set:
        by_last_segment[_last_segment(path)].append(path)

    for name, candidates in by_last_segment.items():
        if name in resolved:
            continue
        if len(candidates) == 1:
            resolved[name] = candidates[0]
        # len > 1: ambiguous -- contributes no resolution for this name.

    return resolved


# =========================================================================== #
# Reference-artifact loading (degrade, never raise; AC21/AC22)
# =========================================================================== #


def _load_reference_distribution(reference: Any) -> Optional[Any]:
    """Resolve *reference* into a ``ReferenceDistribution``, or ``None`` on
    any failure -- missing file, directory, malformed JSON, or an
    unrecognised ``schema_version`` (AC21). Never raises."""
    from segfacet.reference.schema import ReferenceDistribution

    if reference is None:
        try:
            from segfacet.reference.artifact import bundled_production_reference

            return bundled_production_reference()
        except Exception:
            return None

    if isinstance(reference, ReferenceDistribution):
        return reference

    # Anything else is treated as a path to an artifact on disk (str, Path,
    # or any os.PathLike).
    try:
        from segfacet.reference.artifact import load_artifact

        return load_artifact(reference)
    except Exception:
        return None


def _aggregate_reference_stats(
    reference_dist: Any, resolved: Mapping[str, str]
) -> Dict[str, PopulationRange]:
    """``{leaf_path: PopulationRange}`` aggregating, for each resolved
    feature name, ``min``/``max``/``count`` across every ``(level,
    stratum)`` whose ``feature_stats`` carry that feature (AC3)."""
    result: Dict[str, PopulationRange] = {}
    if reference_dist is None:
        return result

    for feature_name, path in resolved.items():
        minimums: List[float] = []
        maximums: List[float] = []
        count = 0
        found = False
        for strata in reference_dist.levels.values():
            for level_dist in strata.values():
                stats = level_dist.feature_stats.get(feature_name)
                if stats is None:
                    continue
                found = True
                minimums.append(stats.min)
                maximums.append(stats.max)
                count += stats.count
        if not found:
            continue
        minimum = min(minimums)
        maximum = max(maximums)
        magnitude = max(abs(minimum), abs(maximum))
        result[path] = PopulationRange(
            population="reference",
            source=(feature_name,),
            covered=True,
            count=count,
            minimum=minimum,
            maximum=maximum,
            span=maximum - minimum,
            magnitude=magnitude,
            informative=magnitude > NEGLIGIBLE_MAGNITUDE,
        )

    return result


# =========================================================================== #
# build_observed_ranges
# =========================================================================== #


def build_observed_ranges(
    *,
    driver_records: Optional[Sequence[Tuple[str, Mapping[str, Any]]]] = None,
    reference: Any = None,
) -> Dict[str, ObservedRange]:
    """Compute ``{leaf_path: ObservedRange}`` over the corpus and reference
    populations.

    Parameters
    ----------
    driver_records:
        ``(driver_id, record)`` pairs. Defaults to
        ``catalogue.iter_driver_records()``. Never mutated.
    reference:
        ``None`` (the bundled production reference), a
        ``ReferenceDistribution`` instance, or a path to a reference artifact
        on disk. A missing/malformed/mis-versioned artifact degrades to an
        uncovered reference population for every path -- never raises
        (AC21).

    Deterministic: two calls with equal inputs return equal results.
    """
    if driver_records is None:
        from segfacet.catalogue import iter_driver_records

        driver_records = list(iter_driver_records())
    else:
        driver_records = list(driver_records)

    # Corpus population: numeric values, and the driver ids that structurally
    # realised each path (any value of any type), per path.
    numeric_values: Dict[str, List[float]] = defaultdict(list)
    realising_driver_ids: Dict[str, Set[str]] = defaultdict(set)

    for driver_id, record in driver_records:
        values_by_path = iter_leaf_values(record)
        for path, values in values_by_path.items():
            realising_driver_ids[path].add(driver_id)
            for v in values:
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    numeric_values[path].append(float(v))

    leaf_union: Set[str] = set(realising_driver_ids.keys())

    reference_dist = _load_reference_distribution(reference)
    resolved = resolve_reference_features(leaf_union) if leaf_union else {}
    reference_ranges = _aggregate_reference_stats(reference_dist, resolved)

    all_paths = leaf_union | set(reference_ranges.keys())

    result: Dict[str, ObservedRange] = {}
    for path in all_paths:
        driver_ids = tuple(sorted(realising_driver_ids.get(path, ())))
        corpus = _population_from_values("corpus", driver_ids, numeric_values.get(path, []))

        reference_range = reference_ranges.get(path)
        if reference_range is None:
            reference_range = _empty_population("reference")

        if path in leaf_union:
            numeric_flag: Optional[bool] = corpus.covered
        else:
            numeric_flag = None

        verdict = _derive_verdict(
            has_any_value=path in leaf_union,
            numeric_flag=numeric_flag,
            corpus=corpus,
            reference_range=reference_range,
            driver_ids=driver_ids,
        )

        result[path] = ObservedRange(
            numeric=numeric_flag,
            corpus=corpus,
            reference=reference_range,
            verdict=verdict,
        )

    return result


def _derive_verdict(
    *,
    has_any_value: bool,
    numeric_flag: Optional[bool],
    corpus: PopulationRange,
    reference_range: PopulationRange,
    driver_ids: Tuple[str, ...],
) -> str:
    """Ordered verdict rules, first match wins (item spec, Implementation
    Step 6). Order is load-bearing twice: "degenerate" must precede "varies"
    so real-GT death wins over synthetic spread, and "placeholder" must
    precede "varies" so a hand-typed placeholder constant is never reported
    as varying."""
    if not has_any_value and not reference_range.covered:
        return "unobserved"

    if has_any_value and not corpus.covered and not reference_range.covered:
        return "non-numeric"

    if reference_range.covered and not reference_range.informative:
        return "degenerate"

    if (
        not reference_range.covered
        and driver_ids
        and all(d in _PLACEHOLDER_DRIVER_IDS for d in driver_ids)
    ):
        return "placeholder"

    if corpus.informative or reference_range.informative:
        return "varies"

    return "constant-synthetic"
