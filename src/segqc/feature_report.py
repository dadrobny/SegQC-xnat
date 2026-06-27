"""Features-block assembly & JSON serialisation (items 016, 022).

This module is a **pure serialisation / assembly layer**. It does *not* compute
geometry — the Stage 2 extractors (items 011–015) and Stage 3 extractors
(items 018–020) already produce frozen dataclasses. Here we convert each
dataclass to a JSON-ready ``dict`` and assemble them into a single ``features``
block that embeds in the v0 report (see :mod:`segqc.report`) and validates
against the extended ``report_schema_v0.json``.

Public API
----------
``build_features_block(...) -> dict``
    Assemble the ``features`` block from already-computed per-label dataclasses
    plus the case-level relationships, overlaps, and optional Stage 3 objects.

The per-dataclass converters (``geometry_to_dict``, ``components_to_dict``,
``centroid_to_dict``, ``overlap_to_dict``, ``relationships_to_dict``,
``spline_offset_to_dict``, ``orientation_to_dict``, ``curvature_to_dict``,
``spacing_consistency_to_dict``, ``monotonic_consistency_to_dict``) are also
exported for callers that need finer-grained control.

Design decisions (item 016)
----------------------------
1. **Serialisation only, not compute.** ``build_features_block`` accepts
   already-computed dataclasses keyed by label rather than calling the
   ``compute_*`` functions itself, keeping the layer pure and trivially
   testable and leaving per-label iteration to the CLI/pipeline wiring item.
2. **No heavy imports at module level.** The converters operate on plain
   dataclasses and need neither NumPy nor NiBabel at import time; the dataclass
   types are only imported under ``TYPE_CHECKING`` for annotations.
3. **Deterministic ordering baked in.** ``per_label`` is assembled in ascending
   integer-label order; ``overlaps`` are sorted by ``(label_a, label_b)``; list
   fields preserve their source order (already sorted by the producing module).
4. **Tuples → JSON arrays.** ``centroid_voxel`` / ``centroid_mm`` (Python
   tuples) serialise to ``[x, y, z]`` arrays; ``BBox`` serialises to an object
   with the named ``x_min``…``z_max`` keys.
5. **Inputs are never mutated.** Every converter builds and returns a fresh
   dict; the source dataclasses are frozen and only read.

Design decisions (item 022)
----------------------------
1. **``"stage3"`` as a sub-object, not flat fields.** Grouping Stage 3 fields
   under a single ``"stage3"`` key isolates them from Stage 2 fields and keeps
   the schema modular. Future stages follow the same pattern.
2. **``features_version`` bumped only when Stage 3 is present.** A
   Stage-2-only call keeps ``"0.1"``; a Stage-3-enriched call emits ``"0.2"``.
3. **All Stage 3 args optional (default ``None``).** Any non-``None`` Stage 3
   argument triggers the ``"stage3"`` block; missing args are simply absent from
   the sub-dict.
4. **Tuples → lists in JSON.** ``principal_axis``, ``tangent_angles_deg``, etc.
   are Python tuples in the dataclasses; converters emit lists for JSON compat.
5. **``outlier_pairs`` / ``non_monotonic_pairs``** become list-of-two-element-lists
   ``[[level_a, level_b], ...]`` for compact JSON representation.
6. **Sorting within Stage 3 lists.** ``per_label_offsets`` and
   ``per_label_orientations`` are sorted ascending by ``label`` (integer),
   matching the ``per_label`` ordering convention from item 016.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Mapping, Optional, Sequence

if TYPE_CHECKING:
    from segqc.features.centroids import LabelCentroid
    from segqc.features.components import ComponentsInfo
    from segqc.features.consistency import MonotonicConsistency, SpacingConsistency
    from segqc.features.geometry import BBox, LabelGeometry
    from segqc.features.orientation import SpineCurvature, VertebralOrientation
    from segqc.features.overlap import OverlapPair
    from segqc.features.relationships import SpineRelationships
    from segqc.features.spline_offset import VertebralSplineOffset

__all__ = [
    "geometry_to_dict",
    "components_to_dict",
    "centroid_to_dict",
    "overlap_to_dict",
    "relationships_to_dict",
    "spline_offset_to_dict",
    "orientation_to_dict",
    "curvature_to_dict",
    "spacing_consistency_to_dict",
    "monotonic_consistency_to_dict",
    "build_features_block",
    "FEATURES_VERSION",
    "FEATURES_VERSION_STAGE3",
]

# Version discriminator for the features block, independent of the top-level
# report ``schema_version``.
FEATURES_VERSION = "0.1"

# Bumped version when Stage 3 deviation features are included.
FEATURES_VERSION_STAGE3 = "0.2"


# --------------------------------------------------------------------------- #
# Per-dataclass converters (pure: dataclass -> JSON-ready dict)
# --------------------------------------------------------------------------- #


def _bbox_dict(bbox: "BBox") -> dict:
    """Convert a :class:`~segqc.features.geometry.BBox` to a named-key dict."""
    return {
        "x_min": bbox.x_min,
        "x_max": bbox.x_max,
        "y_min": bbox.y_min,
        "y_max": bbox.y_max,
        "z_min": bbox.z_min,
        "z_max": bbox.z_max,
    }


def geometry_to_dict(g: "LabelGeometry") -> dict:
    """Convert a :class:`~segqc.features.geometry.LabelGeometry` to a dict.

    The two :class:`~segqc.features.geometry.BBox` fields become nested objects
    with named ``x_min``…``z_max`` keys; all scalar fields are copied verbatim.
    """
    return {
        "voxel_count": g.voxel_count,
        "physical_volume_mm3": g.physical_volume_mm3,
        "extent_x_mm": g.extent_x_mm,
        "extent_y_mm": g.extent_y_mm,
        "extent_z_mm": g.extent_z_mm,
        "bbox_voxel": _bbox_dict(g.bbox_voxel),
        "bbox_physical": _bbox_dict(g.bbox_physical),
        "touches_inferior": g.touches_inferior,
        "touches_superior": g.touches_superior,
        "touches_left": g.touches_left,
        "touches_right": g.touches_right,
        "touches_anterior": g.touches_anterior,
        "touches_posterior": g.touches_posterior,
    }


def components_to_dict(c: "ComponentsInfo") -> dict:
    """Convert a :class:`~segqc.features.components.ComponentsInfo` to a dict.

    List fields are shallow-copied so the returned dict never aliases the
    source dataclass's lists (the source is frozen, but callers may mutate the
    returned dict).
    """
    return {
        "component_count": c.component_count,
        "component_sizes": list(c.component_sizes),
        "component_volumes_mm3": list(c.component_volumes_mm3),
        "largest_component_fraction": c.largest_component_fraction,
        "small_fragments": list(c.small_fragments),
    }


def centroid_to_dict(c: "LabelCentroid") -> dict:
    """Convert a :class:`~segqc.features.centroids.LabelCentroid` centroid to a dict.

    Only the centroid coordinates are emitted here (``label`` and ``level_name``
    are promoted to the enclosing ``labelFeatures`` entry by
    :func:`build_features_block`). The ``(x, y, z)`` tuples become JSON arrays.
    """
    return {
        "centroid_voxel": list(c.centroid_voxel),
        "centroid_mm": list(c.centroid_mm),
    }


def overlap_to_dict(o: "OverlapPair") -> dict:
    """Convert an :class:`~segqc.features.overlap.OverlapPair` to a dict."""
    return {
        "label_a": o.label_a,
        "label_b": o.label_b,
        "name_a": o.name_a,
        "name_b": o.name_b,
        "overlap_voxels": o.overlap_voxels,
    }


def relationships_to_dict(
    rel: Optional["SpineRelationships"],
) -> Optional[dict]:
    """Convert a :class:`~segqc.features.relationships.SpineRelationships`.

    Returns ``None`` (JSON ``null``) when ``rel`` is ``None`` — e.g. for a
    zero-label map where no relationships are computed. Otherwise returns a dict
    with the merged item-014 field names; list fields are shallow-copied.
    """
    if rel is None:
        return None
    return {
        "present_levels": list(rel.present_levels),
        "missing_levels": list(rel.missing_levels),
        "neighbour_spacings_mm": list(rel.neighbour_spacings_mm),
        "is_continuous": rel.is_continuous,
        "out_of_order_labels": list(rel.out_of_order_labels),
    }


# --------------------------------------------------------------------------- #
# Stage 3 per-dataclass converters (item 022)
# --------------------------------------------------------------------------- #


def spline_offset_to_dict(o: "VertebralSplineOffset") -> dict:
    """Convert a :class:`~segqc.features.spline_offset.VertebralSplineOffset` to a dict.

    All eight fields are serialised verbatim. The source dataclass is frozen
    and never mutated.
    """
    return {
        "label": o.label,
        "level_name": o.level_name,
        "closest_u": o.closest_u,
        "offset_mm": o.offset_mm,
        "offset_voxel": o.offset_voxel,
        "dx_mm": o.dx_mm,
        "dy_mm": o.dy_mm,
        "dz_mm": o.dz_mm,
    }


def orientation_to_dict(o: "VertebralOrientation") -> dict:
    """Convert a :class:`~segqc.features.orientation.VertebralOrientation` to a dict.

    ``principal_axis`` is emitted as a 3-element list (the source stores a
    Python tuple; lists are required for JSON compatibility).
    """
    return {
        "label": o.label,
        "level_name": o.level_name,
        "principal_axis": list(o.principal_axis),
        "eigenvalue_ratio": o.eigenvalue_ratio,
    }


def curvature_to_dict(c: "SpineCurvature") -> dict:
    """Convert a :class:`~segqc.features.orientation.SpineCurvature` to a dict.

    Tuple fields ``tangent_angles_deg`` and ``inter_tangent_angles_deg`` become
    lists. ``total_curvature_deg`` is emitted as a float.
    """
    return {
        "tangent_angles_deg": list(c.tangent_angles_deg),
        "inter_tangent_angles_deg": list(c.inter_tangent_angles_deg),
        "total_curvature_deg": float(c.total_curvature_deg),
    }


def spacing_consistency_to_dict(s: "SpacingConsistency") -> dict:
    """Convert a :class:`~segqc.features.consistency.SpacingConsistency` to a dict.

    ``spacings_mm`` and ``deviations_mm`` become lists. ``outlier_pairs`` —
    a tuple of ``(level_a, level_b)`` string-tuples — becomes a list of
    two-element lists ``[[level_a, level_b], ...]`` for compact JSON.
    """
    return {
        "mean_spacing_mm": s.mean_spacing_mm,
        "cv_spacing": s.cv_spacing,
        "spacings_mm": list(s.spacings_mm),
        "deviations_mm": list(s.deviations_mm),
        "outlier_pairs": [list(pair) for pair in s.outlier_pairs],
    }


def monotonic_consistency_to_dict(m: "MonotonicConsistency") -> dict:
    """Convert a :class:`~segqc.features.consistency.MonotonicConsistency` to a dict.

    ``u_values`` becomes a list. ``non_monotonic_pairs`` — a tuple of
    ``(level_a, level_b)`` string-tuples — becomes a list of two-element lists
    ``[[level_a, level_b], ...]``. ``is_monotonic`` is emitted as a bool.
    """
    return {
        "is_monotonic": bool(m.is_monotonic),
        "non_monotonic_pairs": [list(pair) for pair in m.non_monotonic_pairs],
        "u_values": list(m.u_values),
    }


# --------------------------------------------------------------------------- #
# Assembler
# --------------------------------------------------------------------------- #


def build_features_block(
    *,
    geometry: Mapping[int, "LabelGeometry"],
    components: Mapping[int, "ComponentsInfo"],
    centroids: Mapping[int, "LabelCentroid"],
    relationships: Optional["SpineRelationships"],
    overlaps: Iterable["OverlapPair"],
    # --- Stage 3 (all optional, item 022) ---
    spline_offsets: "Optional[Sequence[VertebralSplineOffset]]" = None,
    orientations: "Optional[Sequence[VertebralOrientation]]" = None,
    curvature: "Optional[SpineCurvature]" = None,
    spacing_consistency: "Optional[SpacingConsistency]" = None,
    monotonic_consistency: "Optional[MonotonicConsistency]" = None,
    features_version: str = FEATURES_VERSION,
) -> dict:
    """Assemble the ``features`` block from pre-computed Stage 2 (and optional
    Stage 3) dataclasses.

    This is the consolidation layer: it does not re-derive any geometry, it
    merges already-computed per-label dataclasses into one ``per_label`` entry
    per label and attaches the case-level ``relationships`` and ``overlaps``.
    When any Stage 3 argument is non-``None``, a ``"stage3"`` sub-block is
    appended and ``features_version`` is promoted to ``"0.2"``.

    Parameters
    ----------
    geometry:
        Mapping ``label -> LabelGeometry`` (item 011).
    components:
        Mapping ``label -> ComponentsInfo`` (item 012).
    centroids:
        Mapping ``label -> LabelCentroid`` (item 013). The centroid record is
        also the source of each entry's ``label`` and ``level_name``.
    relationships:
        The case :class:`~segqc.features.relationships.SpineRelationships`
        (item 014), or ``None`` when not computed (e.g. zero labels).
    overlaps:
        Iterable of :class:`~segqc.features.overlap.OverlapPair` (item 015).
        Re-sorted defensively by ``(label_a, label_b)``.
    spline_offsets:
        Optional sequence of
        :class:`~segqc.features.spline_offset.VertebralSplineOffset` (item 018).
        When non-``None``, serialised as ``stage3.per_label_offsets`` sorted by
        label.
    orientations:
        Optional sequence of
        :class:`~segqc.features.orientation.VertebralOrientation` (item 019).
        When non-``None``, serialised as ``stage3.per_label_orientations`` sorted
        by label.
    curvature:
        Optional :class:`~segqc.features.orientation.SpineCurvature` (item 019).
        When non-``None``, serialised as ``stage3.curvature``.
    spacing_consistency:
        Optional :class:`~segqc.features.consistency.SpacingConsistency`
        (item 020). When non-``None``, serialised as
        ``stage3.spacing_consistency``.
    monotonic_consistency:
        Optional :class:`~segqc.features.consistency.MonotonicConsistency`
        (item 020). When non-``None``, serialised as
        ``stage3.monotonic_consistency``.
    features_version:
        Version discriminator embedded in the block; defaults to
        :data:`FEATURES_VERSION`. Overridden to :data:`FEATURES_VERSION_STAGE3`
        when any Stage 3 argument is non-``None``.

    Returns
    -------
    dict
        A fresh, JSON-ready ``features`` block. Inputs are never mutated.

    Raises
    ------
    KeyError
        If a label present in ``geometry`` or ``components`` has no
        corresponding ``centroids`` entry (the centroid supplies ``label`` and
        ``level_name``, so the three per-label maps must share their keys).
    """
    # Union of labels across the three per-label maps, assembled in ascending
    # integer-label order for deterministic output.
    all_labels = set(geometry) | set(components) | set(centroids)

    per_label: dict = {}
    for label in sorted(all_labels):
        centroid_rec = centroids[label]  # source of label + level_name
        per_label[str(label)] = {
            "label": centroid_rec.label,
            "level_name": centroid_rec.level_name,
            "geometry": geometry_to_dict(geometry[label]),
            "components": components_to_dict(components[label]),
            "centroid": centroid_to_dict(centroid_rec),
        }

    # Defensive re-sort: item 015 already sorts, but the assembler must not rely
    # on the caller's ordering for a stable golden snapshot.
    overlap_dicts = [overlap_to_dict(o) for o in overlaps]
    overlap_dicts.sort(key=lambda d: (d["label_a"], d["label_b"]))

    # Determine whether any Stage 3 data was supplied.
    has_stage3 = any(
        arg is not None
        for arg in (spline_offsets, orientations, curvature,
                    spacing_consistency, monotonic_consistency)
    )

    # Promote features_version to "0.2" when Stage 3 data is present, unless
    # the caller explicitly overrode the version.
    effective_version = features_version
    if has_stage3 and features_version == FEATURES_VERSION:
        effective_version = FEATURES_VERSION_STAGE3

    block: dict = {
        "features_version": effective_version,
        "per_label": per_label,
        "relationships": relationships_to_dict(relationships),
        "overlaps": overlap_dicts,
    }

    if has_stage3:
        stage3: dict = {}

        if spline_offsets is not None:
            stage3["per_label_offsets"] = [
                spline_offset_to_dict(o)
                for o in sorted(spline_offsets, key=lambda o: o.label)
            ]

        if orientations is not None:
            stage3["per_label_orientations"] = [
                orientation_to_dict(o)
                for o in sorted(orientations, key=lambda o: o.label)
            ]

        if curvature is not None:
            stage3["curvature"] = curvature_to_dict(curvature)

        if spacing_consistency is not None:
            stage3["spacing_consistency"] = spacing_consistency_to_dict(
                spacing_consistency
            )

        if monotonic_consistency is not None:
            stage3["monotonic_consistency"] = monotonic_consistency_to_dict(
                monotonic_consistency
            )

        block["stage3"] = stage3

    return block
