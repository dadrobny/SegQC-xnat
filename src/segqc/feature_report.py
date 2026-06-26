"""Features-block assembly & JSON serialisation (item 016).

This module is a **pure serialisation / assembly layer**. It does *not* compute
geometry — the Stage 2 extractors (items 011–015) already produce frozen
dataclasses. Here we convert each dataclass to a JSON-ready ``dict`` and
assemble them into a single ``features`` block that embeds in the v0 report
(see :mod:`segqc.report`) and validates against the extended
``report_schema_v0.json``.

Public API
----------
``build_features_block(...) -> dict``
    Assemble the ``features`` block from already-computed per-label dataclasses
    plus the case-level relationships and overlaps.

The per-dataclass converters (``geometry_to_dict``, ``components_to_dict``,
``centroid_to_dict``, ``overlap_to_dict``, ``relationships_to_dict``) are also
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
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from segqc.features.centroids import LabelCentroid
    from segqc.features.components import ComponentsInfo
    from segqc.features.geometry import BBox, LabelGeometry
    from segqc.features.overlap import OverlapPair
    from segqc.features.relationships import SpineRelationships

__all__ = [
    "geometry_to_dict",
    "components_to_dict",
    "centroid_to_dict",
    "overlap_to_dict",
    "relationships_to_dict",
    "build_features_block",
    "FEATURES_VERSION",
]

# Version discriminator for the features block, independent of the top-level
# report ``schema_version``. Stage 3 (item 022) bumps this when it extends the
# block with deviation features.
FEATURES_VERSION = "0.1"


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
# Assembler
# --------------------------------------------------------------------------- #


def build_features_block(
    *,
    geometry: Mapping[int, "LabelGeometry"],
    components: Mapping[int, "ComponentsInfo"],
    centroids: Mapping[int, "LabelCentroid"],
    relationships: Optional["SpineRelationships"],
    overlaps: Iterable["OverlapPair"],
    features_version: str = FEATURES_VERSION,
) -> dict:
    """Assemble the ``features`` block from pre-computed Stage 2 dataclasses.

    This is the consolidation layer: it does not re-derive any geometry, it
    merges already-computed per-label dataclasses into one ``per_label`` entry
    per label and attaches the case-level ``relationships`` and ``overlaps``.

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
    features_version:
        Version discriminator embedded in the block; defaults to
        :data:`FEATURES_VERSION`.

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

    return {
        "features_version": features_version,
        "per_label": per_label,
        "relationships": relationships_to_dict(relationships),
        "overlaps": overlap_dicts,
    }
