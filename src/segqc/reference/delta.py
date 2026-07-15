"""segqc.reference.delta -- per-vertebra delta-to-reference metrics
(Stage 6, item 046).

Scores a case's already-extracted per-label features (the ``features_block``
produced by :func:`segqc.pipeline.extract_feature_record`) against a loaded
045 :class:`~segqc.reference.schema.ReferenceDistribution`, computing for each
present label and each tracked feature:

* a **standard z-score** ``(value - mean) / std`` (``None`` when
  ``std == 0``);
* a **robust z-score** ``(value - p50) / (IQR / IQR_TO_SIGMA)`` where
  ``IQR = p75 - p25`` (``None`` when ``IQR == 0``);
* a **percentile rank** in ``[0, 100]`` via piecewise-linear interpolation
  over the stored percentile grid, anchored at ``min``/``max``;
* an **out-of-range flag** against a configurable percentile-bound pair
  (default ``(p1, p99)``);

and, per label, an aggregate **distribution-distance** -- the RMS of the
defined robust-z values across its tracked-and-present features.

Scope
-----
This module is **not a rule**: it computes and reports numbers only (item 047
adds the rule family that fires on them). It does **not** perform new
feature extraction (it reads values already computed by the Stage 2/3 feature
engine) and does **not** touch ``segqc.heuristics``/``segqc.config``.

Determinism contract
---------------------
Pure: given the same ``features_block`` and ``reference``, two calls to
:func:`compute_reference_delta` produce equal results and byte-identical
``json.dumps(reference_delta_to_dict(delta), sort_keys=True)`` output.
Neither input is mutated. No file I/O, no wall-clock reads. No NumPy/NiBabel
import -- only ``math``/builtins are used for the statistics.
"""

from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from .ingest import INGESTED_FEATURES, INGESTED_MORPHOLOGY_FEATURES
from .schema import ALL_STRATUM, FeatureStats, ReferenceDistribution

__all__ = [
    "REFERENCE_DELTA_VERSION",
    "DEFAULT_LOWER_PCT",
    "DEFAULT_UPPER_PCT",
    "IQR_TO_SIGMA",
    "INTENSITY_FEATURE_PREFIX",
    "MORPHOLOGY_FEATURES",
    "FeatureDelta",
    "LabelDelta",
    "ReferenceDelta",
    "compute_reference_delta",
    "compute_intensity_reference_delta",
    "compute_morphology_reference_delta",
    "reference_delta_to_dict",
]

# Version discriminator for the reference_delta report block, independent of
# the report schema_version and the reference schema_version.
REFERENCE_DELTA_VERSION: str = "1.0"

# Default out-of-range bound percentiles.
DEFAULT_LOWER_PCT: int = 1
DEFAULT_UPPER_PCT: int = 99

# IQR/1.349 ~ sigma for a normal distribution (2 * 0.6745): rescales the IQR
# to a standard-deviation-comparable robust-z scale.
IQR_TO_SIGMA: float = 1.349

# The geometry-scalar subset of INGESTED_FEATURES (everything except the
# Stage 3 spline offset, which is read from a different sub-block).
_GEOMETRY_FEATURES: Tuple[str, ...] = tuple(
    name for name in INGESTED_FEATURES if name != "spline_offset_mm"
)
_SPLINE_OFFSET_FEATURE = "spline_offset_mm"

# Prefix marking the tracked-intensity feature vocabulary in a reference's
# ``features`` tuple (item 063's ``INGESTED_INTENSITY_FEATURES`` convention),
# e.g. ``"intensity_median"`` -> case value at ``first_order["median"]``
# (item 064).
INTENSITY_FEATURE_PREFIX = "intensity_"

# The tracked geometric-morphology feature vocabulary (item 081) -- an alias
# of ``INGESTED_MORPHOLOGY_FEATURES``, scored via its own read path
# (``components`` / Stage 3 orientation blocks), never through
# ``_GEOMETRY_FEATURES`` / ``entry["geometry"]`` nor the ``intensity_``
# prefix.
MORPHOLOGY_FEATURES: Tuple[str, ...] = INGESTED_MORPHOLOGY_FEATURES


@dataclass(frozen=True)
class FeatureDelta:
    """One tracked feature's delta-to-reference result for one label."""

    feature: str
    value: float
    z_score: Optional[float]
    robust_z: Optional[float]
    percentile_rank: float
    out_of_range: bool


@dataclass(frozen=True)
class LabelDelta:
    """One label's delta-to-reference result."""

    label: int
    level_name: str
    stratum: str
    available: bool
    features: Tuple[FeatureDelta, ...]
    distribution_distance: Optional[float]
    out_of_range_features: Tuple[str, ...]


@dataclass(frozen=True)
class ReferenceDelta:
    """The whole-case delta-to-reference result."""

    reference_delta_version: str
    reference_schema_version: str
    reference_source: str
    stratum: str
    lower_pct: int
    upper_pct: int
    per_label: Mapping[int, LabelDelta]


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _percentile_rank(value: float, stats: FeatureStats, percentile_order: Tuple[int, ...]) -> float:
    """Piecewise-linear percentile rank of ``value`` over ``stats``'s grid.

    Anchors are ``(min, 0.0)``, one per stored percentile in ``percentile_order``
    (ascending), and ``(max, 100.0)``. Clamped to ``[0, 100]``. When two
    consecutive anchors share the same value (a flat segment), the value is
    resolved to the *lower* (earlier-encountered) rank -- achieved here by
    returning on the first bracketing pair found while scanning left to right.
    """

    anchors = [(stats.min, 0.0)]
    for pct in percentile_order:
        anchors.append((stats.percentiles[f"p{pct}"], float(pct)))
    anchors.append((stats.max, 100.0))

    if value <= anchors[0][0]:
        return 0.0
    if value >= anchors[-1][0]:
        return 100.0

    for i in range(len(anchors) - 1):
        v0, r0 = anchors[i]
        v1, r1 = anchors[i + 1]
        if v0 <= value <= v1:
            if v1 == v0:
                return r0
            fraction = (value - v0) / (v1 - v0)
            return r0 + fraction * (r1 - r0)

    # Unreachable given the clamping above and a non-decreasing anchor list.
    return 100.0  # pragma: no cover


def _feature_delta(
    feature_name: str,
    value: float,
    stats: FeatureStats,
    *,
    lower_pct: int,
    upper_pct: int,
    percentile_order: Tuple[int, ...],
) -> FeatureDelta:
    z_score = None if stats.std == 0 else (value - stats.mean) / stats.std

    p25 = stats.percentiles["p25"]
    p50 = stats.percentiles["p50"]
    p75 = stats.percentiles["p75"]
    iqr = p75 - p25
    robust_z = None if iqr == 0 else (value - p50) / (iqr / IQR_TO_SIGMA)

    percentile_rank = _percentile_rank(value, stats, percentile_order)

    lower = stats.percentiles[f"p{lower_pct}"]
    upper = stats.percentiles[f"p{upper_pct}"]
    out_of_range = value < lower or value > upper

    return FeatureDelta(
        feature=feature_name,
        value=value,
        z_score=z_score,
        robust_z=robust_z,
        percentile_rank=percentile_rank,
        out_of_range=out_of_range,
    )


def _case_features_for_label(entry: Mapping, offsets_by_label: Mapping[int, float], label: int) -> dict:
    """Extract the tracked feature values present for one case label entry.

    Reads the geometry scalars from ``entry["geometry"]`` (whichever of
    ``_GEOMETRY_FEATURES`` are present) and, when available, the matching
    Stage 3 spline offset. Never mutates ``entry``.
    """

    geometry = entry.get("geometry", {})
    values = {
        name: geometry[name] for name in _GEOMETRY_FEATURES if name in geometry
    }
    if label in offsets_by_label:
        values[_SPLINE_OFFSET_FEATURE] = offsets_by_label[label]
    return values


def _distribution_distance(feature_deltas: Tuple[FeatureDelta, ...]) -> Optional[float]:
    robust_zs = [fd.robust_z for fd in feature_deltas if fd.robust_z is not None]
    if not robust_zs:
        return None
    return math.sqrt(sum(rz * rz for rz in robust_zs) / len(robust_zs))


def _intensity_case_values(image_entry: Mapping, tracked_intensity: Tuple[str, ...]) -> dict:
    """Extract the tracked ``intensity_*`` values present for one label's
    ``image_features`` per-label entry (item 064).

    Reads ``image_entry["first_order"]`` and, for each ``tracked_intensity``
    name (``"intensity_<stat>"``), looks up ``first_order["<stat>"]`` (the
    ``intensity_`` prefix stripped). A missing or ``None`` value is skipped —
    never inserted as ``None``. Never mutates ``image_entry``.
    """

    if not isinstance(image_entry, MappingABC):
        return {}
    first_order = image_entry.get("first_order")
    if not isinstance(first_order, MappingABC):
        return {}

    values = {}
    for feature_name in tracked_intensity:
        stat = feature_name[len(INTENSITY_FEATURE_PREFIX):]
        value = first_order.get(stat)
        if value is not None:
            values[feature_name] = value
    return values


def _morphology_case_values(
    entry: Mapping, orientations_by_label: Mapping[int, float], label: int
) -> dict:
    """Extract the tracked morphology values present for one case label
    entry (item 081).

    Reads ``largest_component_fraction`` / ``component_count`` from
    ``entry["components"]`` (cast ``component_count`` to ``float``) and, when
    available, the matching Stage 3 ``eigenvalue_ratio``. Never reads
    ``entry["geometry"]``. Never mutates ``entry``.
    """

    components = entry.get("components")
    values = {}
    if isinstance(components, MappingABC):
        if "largest_component_fraction" in components:
            values["largest_component_fraction"] = float(
                components["largest_component_fraction"]
            )
        if "component_count" in components:
            values["component_count"] = float(components["component_count"])
    if label in orientations_by_label:
        values["eigenvalue_ratio"] = float(orientations_by_label[label])
    return values


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def compute_reference_delta(
    features_block: Mapping,
    reference: ReferenceDistribution,
    *,
    stratum: str = ALL_STRATUM,
    lower_pct: int = DEFAULT_LOWER_PCT,
    upper_pct: int = DEFAULT_UPPER_PCT,
) -> ReferenceDelta:
    """Compute per-label delta-to-reference metrics.

    For each label in ``features_block["per_label"]``, looks up its level's
    ``FeatureStats`` in ``reference`` (for ``stratum``) and computes
    per-feature deltas over the features ``reference`` tracks that are also
    present for that label. A label whose level (or requested stratum) is
    absent from ``reference`` yields an ``available=False`` :class:`LabelDelta`
    rather than raising.

    Pure: no file I/O, no wall-clock reads, neither ``features_block`` nor
    ``reference`` is mutated.

    Raises
    ------
    ValueError
        If ``lower_pct`` or ``upper_pct`` is not a percentile stored in
        ``reference.percentiles``.
    """

    if lower_pct not in reference.percentiles:
        raise ValueError(
            f"lower_pct={lower_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )
    if upper_pct not in reference.percentiles:
        raise ValueError(
            f"upper_pct={upper_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )

    percentile_order = tuple(sorted(reference.percentiles))
    tracked_features = tuple(sorted(reference.features))

    offsets_by_label = {}
    stage3 = features_block.get("stage3")
    if stage3 is not None:
        for offset_entry in stage3.get("per_label_offsets", []):
            offsets_by_label[int(offset_entry["label"])] = offset_entry["offset_mm"]

    per_label = {}
    for _label_str, entry in features_block.get("per_label", {}).items():
        label = int(entry["label"])
        level_name = entry["level_name"]

        level_strata = reference.levels.get(level_name)
        if level_strata is None or stratum not in level_strata:
            per_label[label] = LabelDelta(
                label=label,
                level_name=level_name,
                stratum=stratum,
                available=False,
                features=(),
                distribution_distance=None,
                out_of_range_features=(),
            )
            continue

        level_dist = level_strata[stratum]
        case_values = _case_features_for_label(entry, offsets_by_label, label)

        feature_deltas = []
        for feature_name in tracked_features:
            if feature_name not in case_values:
                continue
            stats = level_dist.feature_stats.get(feature_name)
            if stats is None:
                continue
            feature_deltas.append(
                _feature_delta(
                    feature_name,
                    case_values[feature_name],
                    stats,
                    lower_pct=lower_pct,
                    upper_pct=upper_pct,
                    percentile_order=percentile_order,
                )
            )
        feature_deltas = tuple(feature_deltas)

        out_of_range_features = tuple(
            sorted(fd.feature for fd in feature_deltas if fd.out_of_range)
        )

        per_label[label] = LabelDelta(
            label=label,
            level_name=level_name,
            stratum=stratum,
            available=True,
            features=feature_deltas,
            distribution_distance=_distribution_distance(feature_deltas),
            out_of_range_features=out_of_range_features,
        )

    return ReferenceDelta(
        reference_delta_version=REFERENCE_DELTA_VERSION,
        reference_schema_version=reference.schema_version,
        reference_source=reference.provenance.source,
        stratum=stratum,
        lower_pct=lower_pct,
        upper_pct=upper_pct,
        per_label=per_label,
    )


def compute_intensity_reference_delta(
    features_block: Mapping,
    image_features: Mapping,
    reference: ReferenceDistribution,
    *,
    stratum: str = ALL_STRATUM,
    lower_pct: int = DEFAULT_LOWER_PCT,
    upper_pct: int = DEFAULT_UPPER_PCT,
) -> ReferenceDelta:
    """Compute per-label delta-to-reference metrics for the intensity feature
    family (item 064) -- a sibling of :func:`compute_reference_delta`.

    For each label in ``features_block["per_label"]`` (the geometric block,
    used purely as the authoritative label -> ``level_name`` join surface),
    looks up its level's ``FeatureStats`` in ``reference`` (for ``stratum``)
    and scores the case's intensity values -- drawn from
    ``image_features["per_label"][str(label)]["first_order"]`` (item 061's
    shape) -- against the ``intensity_``-prefixed subset of
    ``reference.features``. Reuses :func:`_feature_delta` (and hence the
    same z / robust-z / percentile-rank / out-of-range / distribution-distance
    mechanics item 046 uses for geometry).

    A label whose level (or requested stratum) is absent from ``reference``
    yields an ``available=False`` :class:`LabelDelta` rather than raising. A
    reference carrying no ``intensity_*`` distributions yields zero
    ``FeatureDelta``s for every available label (backward compatibility with
    pre-063 references). An absent, non-mapping, or ``available: false``
    ``image_features`` block yields zero intensity scores for every label,
    without raising. A missing/``None`` first-order value simply omits that
    feature (never scored as ``None``).

    This function does not modify :func:`compute_reference_delta`, which
    stays intensity-inert and byte-identical.

    Pure: no file I/O, no wall-clock reads; none of ``features_block``,
    ``image_features``, or ``reference`` is mutated.

    Raises
    ------
    ValueError
        If ``lower_pct`` or ``upper_pct`` is not a percentile stored in
        ``reference.percentiles``.
    """

    if lower_pct not in reference.percentiles:
        raise ValueError(
            f"lower_pct={lower_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )
    if upper_pct not in reference.percentiles:
        raise ValueError(
            f"upper_pct={upper_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )

    percentile_order = tuple(sorted(reference.percentiles))
    tracked_intensity = tuple(
        sorted(name for name in reference.features if name.startswith(INTENSITY_FEATURE_PREFIX))
    )

    image_by_label: dict = {}
    if (
        isinstance(image_features, MappingABC)
        and image_features.get("available")
        and isinstance(image_features.get("per_label"), MappingABC)
    ):
        for label_key, image_entry in image_features["per_label"].items():
            if not isinstance(image_entry, MappingABC):
                continue
            try:
                image_label = int(image_entry.get("label", label_key))
            except (TypeError, ValueError):
                continue
            image_by_label[image_label] = image_entry

    per_label = {}
    for _label_str, entry in features_block.get("per_label", {}).items():
        label = int(entry["label"])
        level_name = entry["level_name"]

        level_strata = reference.levels.get(level_name)
        if level_strata is None or stratum not in level_strata:
            per_label[label] = LabelDelta(
                label=label,
                level_name=level_name,
                stratum=stratum,
                available=False,
                features=(),
                distribution_distance=None,
                out_of_range_features=(),
            )
            continue

        level_dist = level_strata[stratum]
        case_values = _intensity_case_values(image_by_label.get(label, {}), tracked_intensity)

        feature_deltas = []
        for feature_name in tracked_intensity:
            if feature_name not in case_values:
                continue
            stats = level_dist.feature_stats.get(feature_name)
            if stats is None:
                continue
            feature_deltas.append(
                _feature_delta(
                    feature_name,
                    case_values[feature_name],
                    stats,
                    lower_pct=lower_pct,
                    upper_pct=upper_pct,
                    percentile_order=percentile_order,
                )
            )
        feature_deltas = tuple(feature_deltas)

        out_of_range_features = tuple(
            sorted(fd.feature for fd in feature_deltas if fd.out_of_range)
        )

        per_label[label] = LabelDelta(
            label=label,
            level_name=level_name,
            stratum=stratum,
            available=True,
            features=feature_deltas,
            distribution_distance=_distribution_distance(feature_deltas),
            out_of_range_features=out_of_range_features,
        )

    return ReferenceDelta(
        reference_delta_version=REFERENCE_DELTA_VERSION,
        reference_schema_version=reference.schema_version,
        reference_source=reference.provenance.source,
        stratum=stratum,
        lower_pct=lower_pct,
        upper_pct=upper_pct,
        per_label=per_label,
    )


def compute_morphology_reference_delta(
    features_block: Mapping,
    reference: ReferenceDistribution,
    *,
    stratum: str = ALL_STRATUM,
    lower_pct: int = DEFAULT_LOWER_PCT,
    upper_pct: int = DEFAULT_UPPER_PCT,
) -> ReferenceDelta:
    """Compute per-label delta-to-reference metrics for the geometric-
    morphology feature family (item 081) -- a sibling of
    :func:`compute_reference_delta` and :func:`compute_intensity_reference_delta`.

    For each label in ``features_block["per_label"]`` (used purely as the
    authoritative label -> ``level_name`` join surface), looks up its level's
    ``FeatureStats`` in ``reference`` (for ``stratum``) and scores the case's
    morphology values -- ``largest_component_fraction`` / ``component_count``
    from that label's ``components`` block, and ``eigenvalue_ratio`` from
    ``features_block["stage3"]["per_label_orientations"]`` matched by label --
    against the :data:`MORPHOLOGY_FEATURES` subset of ``reference.features``.
    Reuses :func:`_feature_delta` (the same z / robust-z / percentile-rank /
    out-of-range / distribution-distance mechanics the other two deltas use).
    Never reads ``entry["geometry"]``.

    A label whose level (or requested stratum) is absent from ``reference``
    yields an ``available=False`` :class:`LabelDelta` rather than raising. A
    reference carrying no morphology distributions yields zero
    ``FeatureDelta``s for every available label (backward compatibility with
    pre-081 references). A missing/``None`` value simply omits that feature
    (never scored as ``None``).

    This function does not modify :func:`compute_reference_delta` or
    :func:`compute_intensity_reference_delta`, which stay morphology-inert
    and byte-identical.

    Pure: no file I/O, no wall-clock reads; neither ``features_block`` nor
    ``reference`` is mutated.

    Raises
    ------
    ValueError
        If ``lower_pct`` or ``upper_pct`` is not a percentile stored in
        ``reference.percentiles``.
    """

    if lower_pct not in reference.percentiles:
        raise ValueError(
            f"lower_pct={lower_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )
    if upper_pct not in reference.percentiles:
        raise ValueError(
            f"upper_pct={upper_pct!r} is not in reference.percentiles={reference.percentiles!r}"
        )

    percentile_order = tuple(sorted(reference.percentiles))
    tracked_morphology = tuple(
        sorted(name for name in reference.features if name in MORPHOLOGY_FEATURES)
    )

    orientations_by_label = {}
    stage3 = features_block.get("stage3")
    if stage3 is not None:
        for orientation_entry in stage3.get("per_label_orientations", []):
            orientations_by_label[int(orientation_entry["label"])] = orientation_entry[
                "eigenvalue_ratio"
            ]

    per_label = {}
    for _label_str, entry in features_block.get("per_label", {}).items():
        label = int(entry["label"])
        level_name = entry["level_name"]

        level_strata = reference.levels.get(level_name)
        if level_strata is None or stratum not in level_strata:
            per_label[label] = LabelDelta(
                label=label,
                level_name=level_name,
                stratum=stratum,
                available=False,
                features=(),
                distribution_distance=None,
                out_of_range_features=(),
            )
            continue

        level_dist = level_strata[stratum]
        case_values = _morphology_case_values(entry, orientations_by_label, label)

        feature_deltas = []
        for feature_name in tracked_morphology:
            if feature_name not in case_values:
                continue
            stats = level_dist.feature_stats.get(feature_name)
            if stats is None:
                continue
            feature_deltas.append(
                _feature_delta(
                    feature_name,
                    case_values[feature_name],
                    stats,
                    lower_pct=lower_pct,
                    upper_pct=upper_pct,
                    percentile_order=percentile_order,
                )
            )
        feature_deltas = tuple(feature_deltas)

        out_of_range_features = tuple(
            sorted(fd.feature for fd in feature_deltas if fd.out_of_range)
        )

        per_label[label] = LabelDelta(
            label=label,
            level_name=level_name,
            stratum=stratum,
            available=True,
            features=feature_deltas,
            distribution_distance=_distribution_distance(feature_deltas),
            out_of_range_features=out_of_range_features,
        )

    return ReferenceDelta(
        reference_delta_version=REFERENCE_DELTA_VERSION,
        reference_schema_version=reference.schema_version,
        reference_source=reference.provenance.source,
        stratum=stratum,
        lower_pct=lower_pct,
        upper_pct=upper_pct,
        per_label=per_label,
    )


def _feature_delta_to_dict(fd: FeatureDelta) -> dict:
    return {
        "value": fd.value,
        "z_score": fd.z_score,
        "robust_z": fd.robust_z,
        "percentile_rank": fd.percentile_rank,
        "out_of_range": fd.out_of_range,
    }


def _label_delta_to_dict(ld: LabelDelta) -> dict:
    return {
        "label": ld.label,
        "level_name": ld.level_name,
        "available": ld.available,
        "distribution_distance": ld.distribution_distance,
        "out_of_range_features": list(ld.out_of_range_features),
        "features": {
            fd.feature: _feature_delta_to_dict(fd) for fd in ld.features
        },
    }


def reference_delta_to_dict(delta: ReferenceDelta) -> dict:
    """JSON-ready ``reference_delta`` report block for ``delta``. Pure."""

    return {
        "reference_delta_version": delta.reference_delta_version,
        "reference_schema_version": delta.reference_schema_version,
        "reference_source": delta.reference_source,
        "stratum": delta.stratum,
        "lower_pct": delta.lower_pct,
        "upper_pct": delta.upper_pct,
        "per_label": {
            str(label): _label_delta_to_dict(label_delta)
            for label, label_delta in delta.per_label.items()
        },
    }
