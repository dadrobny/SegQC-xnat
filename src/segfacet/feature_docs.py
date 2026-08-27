"""Authored feature documentation & structural mappings (item 103; Stage 19).

Pure, stdlib-only data joined by :mod:`segfacet.catalogue`'s generator into the
committed feature & rule catalogue. This module imports nothing from
``segfacet`` and nothing outside the standard library, so it stays importable
with no NumPy/SciPy/NiBabel present (AC2) -- an AST scan of its own import
statements is part of the item's test suite.

Contents
--------
``FeatureDoc``
    Frozen dataclass: the authored prose for one normalised leaf path
    (``measures`` / ``computation`` / ``units`` / ``scale_sensitivity``).
``FEATURE_DOCS``
    ``{normalised_leaf_path: FeatureDoc}`` -- one entry per path the committed
    driver-record set realises (``segfacet.catalogue.iter_driver_records`` +
    ``iter_leaf_paths``). Kept in lock-step by
    ``segfacet.catalogue.build_catalogue(strict=True)``: an undocumented
    realised path or a stale key both raise (AC16/AC17), so this dict can
    never silently drift from the record shape it documents.
``BLOCK_OWNERS``
    Ordered ``(path_prefix, group_title, stage_label, module)`` rows; the
    generator matches each leaf path against the *longest* matching prefix
    (irrespective of authored order -- the generator does its own descending-
    length sort) to assign a group/stage/module, reproducing the pre-103
    hand-typed ``FEATURE_CATALOG`` grouping.
``GROUP_INTROS``
    ``{group_title: intro_prose}`` -- the per-group summary sentence(s) the
    pre-103 hand-typed ``FEATURE_CATALOG`` carried on each ``FeatureGroupSpec``
    (e.g. "For every present integer label, computed directly from the voxel
    mask..."). Looked up by ``group_title`` (the second element of the
    matched ``BLOCK_OWNERS`` row) when a ``CatalogueGroup`` is assembled;
    ``""`` for a title with no authored intro (never raises).
``PATH_ALIASES``
    ``{vocabulary_name: leaf_path}`` for mechanism D's declared-vocabulary
    matching, only where the vocabulary name is not itself the leaf path's
    last segment (``spline_offset_mm`` is tracked under the record field name
    ``offset_mm``, nested under ``stage3.per_label_offsets[]``).
``MODE_ANCHOR_PATHS``
    ``{1..8: (leaf_path, ...)}`` -- the record leaf path(s) item 099's eight
    per-mode metrics read (or, for the three candidate-vs-GT metrics with no
    record path of their own -- modes 1, 4, 5 -- the record path their *rule*
    counterpart reads instead; see item 099's spec table "The mapping" and
    this module's per-mode notes below). Every path here anchors that mode
    onto the matching catalogue entry with ``mode_evidence`` containing
    ``"per_mode_metric"`` (AC14).
``STATUS_OVERRIDES``
    ``{leaf_path: (status, rationale)}`` -- ships **empty**. ``retune``/
    ``retire`` are human judgments; Stage 19's checkpoint (items 105/106)
    populates this map after reading the generated catalogue. Every wired
    path starts at ``"keep"`` and every unread path at ``"unwired"`` -- both
    derived, both honest -- until that review lands.

Mode-anchor notes (modes 1, 4, 5 have no record path of their own)
--------------------------------------------------------------------
- **Mode 1** (``unanchored_foreground_fraction``, candidate-vs-GT) is
  anchored on ``stage3.per_label_offsets[].offset_mm`` -- the record path
  ``heuristics.mislabel.MislabelRule``'s Detector A (§6 mode 1) reads.
- **Mode 4** (``mislabelled_volume_fraction``, candidate-vs-GT) is anchored
  on ``stage3.monotonic_consistency.is_monotonic`` -- the same
  ``monotonic_consistency`` sub-block ``MislabelRule``'s Detector B (§6 mode
  4) reads its ``non_monotonic_pairs`` signal from. ``is_monotonic`` itself
  (rather than ``non_monotonic_pairs[]``) is deliberately the anchor so
  ``non_monotonic_pairs[]`` -- the field Detector B actually reads and the
  *only* leaf path exclusively consumed by ``mislabel`` -- stays a plain,
  code-derived (mechanism A) attribution rather than being absorbed into the
  anchor set; item 103's AC13 test asserts such an exclusively-consumed,
  non-anchor witness exists per mapped rule.
- **Mode 5** (``missing_level_count``, candidate-vs-GT) is anchored on
  ``relationships.present_levels[]`` -- the present-level span
  ``heuristics.coverage.CoverageRule`` resolves its missing-level checks
  against. ``relationships.missing_levels[]`` itself -- the field the rule
  actually reads and coverage's only exclusively-consumed leaf path -- is
  deliberately left as a plain attribution for the same reason as mode 4
  above.
- **Mode 7** (``out_of_order_label_count``) is anchored on
  ``relationships.is_continuous`` -- the companion continuity flag in the
  same ``relationships`` sub-block ``heuristics.sequence.SequenceRule``
  reads its ``out_of_order_labels`` signal from, for the same reason:
  ``relationships.out_of_order_labels[]`` is ``sequence``'s only
  exclusively-consumed leaf path and is left as a plain attribution.

``MetricSpec`` (``segfacet.eval.per_mode``) carries no record-path field, so
this transcription cannot be read off it mechanically; a future item that adds
one should replace this hand-transcription by reading it instead (see the
item 103 spec's Assumptions).
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Tuple

__all__ = [
    "FeatureDoc",
    "FEATURE_DOCS",
    "BLOCK_OWNERS",
    "GROUP_INTROS",
    "PATH_ALIASES",
    "MODE_ANCHOR_PATHS",
    "STATUS_OVERRIDES",
]


@dataclass(frozen=True)
class FeatureDoc:
    """Authored prose for one normalised leaf path.

    Attributes
    ----------
    measures:
        What the feature measures, one sentence.
    computation:
        How it is computed, one or two sentences.
    units:
        Physical unit, or ``""`` for a dimensionless / boolean / identifier
        field.
    scale_sensitivity:
        One of ``"scales with spacing"``, ``"dimensionless"``,
        ``"voxel count"``, ``"boolean"``, ``"identifier"``, ``"categorical"``.
    """

    measures: str
    computation: str
    units: str
    scale_sensitivity: str


# --------------------------------------------------------------------------- #
# BLOCK_OWNERS -- structural grouping (longest-prefix wins)
# --------------------------------------------------------------------------- #

BLOCK_OWNERS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "per_label.{label}.geometry",
        "Per-Label Geometry",
        "Stage 2 · item 011",
        "segfacet.features.geometry",
    ),
    (
        "per_label.{label}.components",
        "Connected Components & Fragmentation",
        "Stage 2 · items 012, 025, 098",
        "segfacet.features.components",
    ),
    (
        "per_label.{label}.centroid",
        "Centroid & Identity",
        "Stage 2 · item 013",
        "segfacet.features.centroids",
    ),
    (
        "per_label.{label}",
        "Centroid & Identity",
        "Stage 2 · item 013",
        "segfacet.features.centroids",
    ),
    (
        "relationships",
        "Case-Level Relationships",
        "Stage 2 · item 014",
        "segfacet.features.relationships",
    ),
    (
        "overlaps",
        "Voxel Overlap",
        "Stage 2 · item 015",
        "segfacet.features.overlap",
    ),
    (
        "stage3.per_label_offsets",
        "Spline Offset",
        "Stage 3 · item 018",
        "segfacet.features.spline_offset",
    ),
    (
        "stage3.per_label_orientations",
        "Orientation & Curvature",
        "Stage 3 · item 019",
        "segfacet.features.orientation",
    ),
    (
        "stage3.curvature",
        "Orientation & Curvature",
        "Stage 3 · item 019",
        "segfacet.features.orientation",
    ),
    (
        "stage3.spacing_consistency",
        "Spacing & Monotonic Consistency",
        "Stage 3 · item 020",
        "segfacet.features.consistency",
    ),
    (
        "stage3.monotonic_consistency",
        "Spacing & Monotonic Consistency",
        "Stage 3 · item 020",
        "segfacet.features.consistency",
    ),
    (
        "stage3.per_label_neighbourhood",
        "Local Neighbourhood Comparison",
        "Stage 3 · items 024, 110",
        "segfacet.features.neighbourhood",
    ),
    (
        "image_features.per_label.{label}.first_order",
        "Intensity — First-Order",
        "Stage 8 · item 059",
        "segfacet.features.intensity",
    ),
    (
        "image_features.per_label.{label}.extended",
        "Intensity — Extended Radiomics",
        "Stage 8 · item 060",
        "segfacet.features.radiomics",
    ),
    (
        "image_features",
        "Intensity — First-Order",
        "Stage 8 · items 059, 061",
        "segfacet.feature_report",
    ),
    (
        "reference_delta",
        "Reference-Distribution Deltas",
        "Stage 6/8 · items 046, 064",
        "segfacet.reference.delta",
    ),
    (
        "",
        "Record Envelope",
        "Stage 2 · item 016",
        "segfacet.feature_report",
    ),
)


# --------------------------------------------------------------------------- #
# GROUP_INTROS -- per-group summary prose, keyed by BLOCK_OWNERS's group_title
# --------------------------------------------------------------------------- #

GROUP_INTROS: Mapping[str, str] = MappingProxyType(
    {
        "Per-Label Geometry": (
            "For every present integer label, computed directly from the voxel "
            "mask (NumPy/CuPy) with spacing read from the NIfTI header."
        ),
        "Connected Components & Fragmentation": (
            "6-connectivity (face-neighbour only) connected-components analysis "
            "of each label's voxel mask via scipy.ndimage.label (or the CuPy "
            "equivalent on GPU); item 098 promotes the non-dominant ('stray') "
            "component population to first-class fields alongside the original "
            "item 012/025 measures."
        ),
        "Centroid & Identity": (
            "Centre of mass of each label's voxel mask, plus the integer "
            "label/anatomical level_name identity pair every other per-label "
            "block below re-carries."
        ),
        "Case-Level Relationships": (
            "Computed once per case from the full ordered set of centroids "
            "(ascending integer-label order)."
        ),
        "Voxel Overlap": (
            "Requires a boolean per-label mask stack (a single integer label "
            "map cannot represent a voxel claimed by two labels at once)."
        ),
        "Spline Offset": (
            "A cubic (degree clamped to n_points-1 when the sequence is short) "
            "B-spline is fit through the ordered centroids' mm-coordinates "
            "(scipy.interpolate.splprep, s=0 -> passes exactly through every "
            "centroid); this spline underlies the per-vertebra offset measured "
            "here and the orientation/curvature/consistency families below."
        ),
        "Orientation & Curvature": (
            "Per-vertebra orientation (PCA of the mean-centred, spacing-scaled "
            "voxel cloud) and case-level curvature summaries derived from the "
            "same fitted spline's local tangent at each vertebra."
        ),
        "Spacing & Monotonic Consistency": (
            "Inter-vertebra centroid spacing regularity and whether each "
            "vertebra's closest-spline-parameter u increases along the "
            "anatomical order, both derived from the same fitted spline."
        ),
        "Local Neighbourhood Comparison": (
            "Sliding-window leave-one-out comparison of each vertebra against "
            "its immediate neighbours in the anatomical order, for a "
            "caller-named feature set (item 110 generalised item 024's "
            "hardcoded three-feature mechanism); computed and serialised for "
            "every case with >= 2 labels, but consumed by no rule yet -- "
            "status unwired."
        ),
        "Intensity — First-Order": (
            "The first feature family to read scan intensities rather than "
            "only the label map; computed over the finite (non-NaN/inf) scan "
            "voxels under each label's mask."
        ),
        "Intensity — Extended Radiomics": (
            "Populated only when the optional PyRadiomics dependency is "
            "installed and enabled; degrades to an empty dict otherwise "
            "without failing the pipeline."
        ),
        "Reference-Distribution Deltas": (
            "Not new extraction -- scores a case's already-computed per-label "
            "features against a versioned cohort ReferenceDistribution (item "
            "045), for the tracked geometric/morphology/intensity vocabulary."
        ),
        "Record Envelope": (
            "The top-level report scaffolding -- the schema-version "
            "discriminator and the per-label container every block above "
            "nests under."
        ),
    }
)


# --------------------------------------------------------------------------- #
# PATH_ALIASES -- declared-vocabulary name -> leaf path (mechanism D)
# --------------------------------------------------------------------------- #

PATH_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "spline_offset_mm": "stage3.per_label_offsets[].offset_mm",
    }
)


# --------------------------------------------------------------------------- #
# MODE_ANCHOR_PATHS -- item 099's eight per-mode metrics -> record leaf path(s)
# --------------------------------------------------------------------------- #

MODE_ANCHOR_PATHS: Mapping[int, Tuple[str, ...]] = MappingProxyType(
    {
        1: ("stage3.per_label_offsets[].offset_mm",),
        2: ("per_label.{label}.components.fragmentation_index",),
        3: ("per_label.{label}.components.stray_component_sizes[]",),
        4: ("stage3.monotonic_consistency.is_monotonic",),
        5: ("relationships.present_levels[]",),
        6: ("per_label.{label}.geometry.touches_left",),
        7: ("relationships.is_continuous",),
        8: ("overlaps[].overlap_voxels",),
    }
)


# --------------------------------------------------------------------------- #
# STATUS_OVERRIDES -- the Stage-19 steering review's output (item 106,
# 2026-07-28 live walkthrough with the maintainer). 74 entries (8 retire, 66
# retune), transcribed verbatim from the maintainer's recorded calls; see this
# item's spec, "### Stage-19 steering review" in Decisions & Trade-offs, for
# the full transcript. Ordered by catalogue order for readability.
# --------------------------------------------------------------------------- #

STATUS_OVERRIDES: Mapping[str, Tuple[str, str]] = MappingProxyType(
    {
        "per_label.{label}.geometry.bbox_physical.x_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_physical.x_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_physical.y_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_physical.y_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_physical.z_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_physical.z_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.x_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.x_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.y_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.y_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.z_max": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.bbox_voxel.z_min": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.extent_x_mm": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.extent_y_mm": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.geometry.extent_z_mm": (
            "retune",
            "Computed in raw image-axis coordinates, not anatomically "
            "meaningful since it depends on patient/scanner orientation "
            "rather than vertebra anatomy; should instead be expressed in a "
            "vertebra coordinate system (VCS) -- an anatomical per-vertebra "
            "frame not yet defined in this codebase."
        ),
        "per_label.{label}.components.component_volumes_mm3[]": (
            "retire",
            "Redundant with per-component voxel counts (component_sizes[]) "
            "and the label's known voxel spacing; physical volume per "
            "component is trivially derivable if ever needed, not worth "
            "carrying as a stored field."
        ),
        "per_label.{label}.components.fragmentation_index": (
            "retire",
            "Pure alias of largest_component_fraction under its item-025 "
            "public name; carrying both is unnecessary duplication -- the "
            "fragmentation rule should read largest_component_fraction "
            "directly instead."
        ),
        "per_label.{label}.components.small_fragments[]": (
            "retire",
            "An absolute-voxel-count list of fragments below a noise "
            "threshold is less useful than a relative measure of stray "
            "volume; superseded in spirit by stray_volume_fraction."
        ),
        "per_label.{label}.components.stray_component_count": (
            "retune",
            "Should be read directly by the fragmentation rule where the "
            "equivalent quantity is needed, instead of being recomputed "
            "privately from stray_component_sizes each time."
        ),
        "per_label.{label}.components.stray_volume_fraction": (
            "retune",
            "Should be read directly by the fragmentation rule where the "
            "equivalent quantity is needed, instead of being recomputed "
            "privately from stray_component_sizes each time."
        ),
        "per_label.{label}.components.stray_volume_mm3": (
            "retune",
            "Should be read directly by the fragmentation rule where the "
            "equivalent quantity is needed, instead of being recomputed "
            "privately from stray_component_sizes each time."
        ),
        "per_label.{label}.centroid.centroid_voxel[]": (
            "retire",
            "Fully derivable from centroid_mm plus the image affine if ever "
            "needed again; not worth carrying as a stored duplicate of "
            "centroid_mm."
        ),
        "stage3.per_label_offsets[].closest_u": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].dx_mm": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].dy_mm": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].dz_mm": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].label": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].level_name": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].offset_mm": (
            "retune",
            "Should be nested under the existing per_label.{label}.* "
            "structure rather than living in a separate "
            "stage3.per_label_offsets[] array; label/level_name here "
            "duplicate the identity fields already carried at the top level "
            "of per_label."
        ),
        "stage3.per_label_offsets[].offset_voxel": (
            "retire",
            "An anisotropic-voxel-unit duplicate of offset_mm with no "
            "demonstrated need; irrelevant unless a concrete use case proves "
            "otherwise."
        ),
        "stage3.curvature.inter_tangent_angles_deg[]": (
            "retune",
            "Should likewise be decomposed into three per-axis components per "
            "neighbouring vertebra pair, rather than one scalar angle."
        ),
        "stage3.curvature.tangent_angles_deg[]": (
            "retune",
            "Should be decomposed into three per-axis components -- the "
            "tangent vector's angle projected along each scan dimension -- "
            "rather than one scalar relative to the superior-inferior axis "
            "alone."
        ),
        "stage3.curvature.total_curvature_deg": (
            "retune",
            "Should be expressed per axis component (three values) rather "
            "than as one aggregate scalar, consistent with the tangent-angle "
            "decomposition."
        ),
        "stage3.per_label_orientations[].label": (
            "retune",
            "Should be nested under per_label.{label}.* rather than a "
            "separate stage3.per_label_orientations[] array; duplicates "
            "identity fields already carried at the top level of per_label."
        ),
        "stage3.per_label_orientations[].level_name": (
            "retune",
            "Should be nested under per_label.{label}.* rather than a "
            "separate stage3.per_label_orientations[] array; duplicates "
            "identity fields already carried at the top level of per_label."
        ),
        "stage3.per_label_orientations[].principal_axis[]": (
            "retune",
            "Current PCA-eigenvector computation is accurate as documented "
            "(captures the vertebra's AP axis) and should remain described "
            "as-is for now, but is flagged for replacement by a proper "
            "vertebra coordinate system (VCS) estimation once VCS is defined."
        ),
        "stage3.monotonic_consistency.is_monotonic": (
            "retune",
            "Should be wired into the sequence rule directly; "
            "sequence-related checks should typically verify order along the "
            "spline parameter, not only label order."
        ),
        "stage3.monotonic_consistency.u_values[]": (
            "retune",
            "Suspected to already be computed internally to produce "
            "non_monotonic_pairs[]; should be exposed and reused as the "
            "actual intermediate rather than silently recomputed."
        ),
        "stage3.spacing_consistency.cv_spacing": (
            "retune",
            "Computation is sound as-is; needs to be wired into a rule that "
            "detects irregular inter-vertebra spacing, which does not "
            "currently exist."
        ),
        "stage3.spacing_consistency.deviations_mm[]": (
            "retune",
            "Computation is sound as-is; needs to be wired into a rule that "
            "detects irregular inter-vertebra spacing, which does not "
            "currently exist."
        ),
        "stage3.spacing_consistency.mean_spacing_mm": (
            "retune",
            "Computation is sound as-is; needs to be wired into a rule that "
            "detects irregular inter-vertebra spacing, which does not "
            "currently exist."
        ),
        "stage3.spacing_consistency.outlier_pairs[]": (
            "retune",
            "Computation is sound as-is; needs to be wired into a rule that "
            "detects irregular inter-vertebra spacing, which does not "
            "currently exist."
        ),
        "stage3.spacing_consistency.spacings_mm[]": (
            "retune",
            "Computation is sound as-is; needs to be wired into a rule that "
            "detects irregular inter-vertebra spacing, which does not "
            "currently exist."
        ),
        "image_features.per_label.{label}.first_order.entropy": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.iqr": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.max": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.mean": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.median": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.min": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.n_nonfinite_excluded": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.p05": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.p25": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.p50": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.p75": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.p95": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.range": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.std": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.per_label.{label}.first_order.voxel_count": (
            "retune",
            "Should be restructured to nest under the main "
            "per_label.{label}.* pattern rather than a separate "
            "image_features.per_label.{label}.* container; the individual "
            "values are useful to keep as an available catalogue so future "
            "rules can explore and select from them."
        ),
        "image_features.available": (
            "retune",
            "Should be derived directly from whether the corresponding "
            "feature block is non-empty, rather than carried as a separate "
            "boolean flag."
        ),
        "image_features.image_features_version": (
            "retire",
            "A schema-shape discriminator, not real dependency-version "
            "provenance -- actual package versions are already tracked by "
            "item 096's run-manifest provenance block; this field is "
            "redundant with that mechanism."
        ),
        "image_features.per_label.{label}.label": (
            "retune",
            "Should be nested under the main per_label.{label}.* structure "
            "rather than a separate image_features.per_label container; "
            "duplicates identity fields already carried elsewhere."
        ),
        "image_features.radiomics_available": (
            "retune",
            "Should likewise be derived directly from whether extended "
            "radiomics features are actually present, rather than a separate "
            "boolean flag."
        ),
        "reference_delta.reference_delta_version": (
            "retire",
            "Same reasoning as image_features_version: a schema-shape "
            "discriminator redundant with item 096's real package-version "
            "provenance, not needed within the feature record itself."
        ),
        "reference_delta.reference_schema_version": (
            "retire",
            "Same reasoning as reference_delta_version and "
            "image_features_version: schema-shape discriminator, not real "
            "provenance, redundant with item 096's run-manifest."
        ),
        "reference_delta.{label}.available": (
            "retune",
            "Part of the reference-delta comparison machinery, which should "
            "be generalised to compute for any requested tracked feature "
            "rather than being hardcoded around a single example."
        ),
        "reference_delta.{label}.distribution_distance": (
            "retune",
            "Part of the reference-delta comparison machinery, which should "
            "be generalised to compute for any requested tracked feature "
            "rather than being hardcoded around a single example."
        ),
        "reference_delta.{label}.features.physical_volume_mm3.out_of_range": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
        "reference_delta.{label}.features.physical_volume_mm3.percentile_rank": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
        "reference_delta.{label}.features.physical_volume_mm3.robust_z": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
        "reference_delta.{label}.features.physical_volume_mm3.value": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
        "reference_delta.{label}.features.physical_volume_mm3.z_score": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
        "reference_delta.{label}.label": (
            "retune",
            "Should be nested under the main per_label.{label}.* structure; "
            "duplicates identity fields carried elsewhere across multiple "
            "blocks."
        ),
        "reference_delta.{label}.level_name": (
            "retune",
            "Should be nested under the main per_label.{label}.* structure; "
            "duplicates identity fields carried elsewhere across multiple "
            "blocks."
        ),
        "reference_delta.{label}.out_of_range_features[]": (
            "retune",
            "The delta-comparison machinery should be generalised into "
            "general-purpose per-feature machinery, computed for any "
            "requested feature rather than hardcoded to physical_volume_mm3 "
            "alone, so per-feature out-of-distribution behaviour can be "
            "investigated for any tracked feature."
        ),
    }
)


# --------------------------------------------------------------------------- #
# FEATURE_DOCS -- one entry per realised leaf path
# --------------------------------------------------------------------------- #

FEATURE_DOCS: Mapping[str, FeatureDoc] = MappingProxyType(
    {
        'features_version': FeatureDoc(
            measures='Schema-version discriminator for this features block.',
            computation='Literal "0.1" (Stage-2-only) or "0.2" (Stage 3 present), stamped by build_features_block.',
            units='',
            scale_sensitivity='categorical',
        ),
        'image_features.available': FeatureDoc(
            measures='Whether intensity/radiomics features were attempted and succeeded for this case.',
            computation='False only when intensity extraction could not run at all (no scan / no backend); per_label is empty in that case.',
            units='',
            scale_sensitivity='boolean',
        ),
        'image_features.backend': FeatureDoc(
            measures='Which backend computed the extended radiomics features.',
            computation='"builtin" (first-order only) or "pyradiomics".',
            units='',
            scale_sensitivity='categorical',
        ),
        'image_features.image_features_version': FeatureDoc(
            measures='Schema-version discriminator for the image_features block.',
            computation='Literal "1.0" (item 061), independent of features_version.',
            units='',
            scale_sensitivity='categorical',
        ),
        'image_features.per_label.{label}.extended.{radiomic}': FeatureDoc(
            measures="PyRadiomics' own GLCM texture and shape feature families.",
            computation="binWidth fixed at 25.0, no resampling; keyed under PyRadiomics' own dotted names (e.g. original_glcm_Contrast).",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.entropy': FeatureDoc(
            measures='Shannon entropy of the intensity distribution.',
            computation='Fixed 32-bin histogram spanning [min, max], base-2 (bits); a uniform/constant region is defined as entropy 0.0.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.iqr': FeatureDoc(
            measures='Spread summary: interquartile range.',
            computation='p75 - p25 of the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.max': FeatureDoc(
            measures='Maximum scan intensity under the label mask.',
            computation='Maximum of the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.mean': FeatureDoc(
            measures='Mean scan intensity under the label mask.',
            computation='Arithmetic mean over the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.median': FeatureDoc(
            measures='Median scan intensity under the label mask.',
            computation='50th percentile of the finite voxel values; equals p50 exactly.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.min': FeatureDoc(
            measures='Minimum scan intensity under the label mask.',
            computation='Minimum of the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.n_nonfinite_excluded': FeatureDoc(
            measures='Count of masked voxels dropped for being NaN/+-inf.',
            computation='Bookkeeping only -- excluded voxels never enter any statistic.',
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'image_features.per_label.{label}.first_order.p05': FeatureDoc(
            measures='5th percentile of scan intensity under the label mask.',
            computation="NumPy's default linear interpolation.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.p25': FeatureDoc(
            measures='25th percentile of scan intensity under the label mask.',
            computation="NumPy's default linear interpolation.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.p50': FeatureDoc(
            measures='50th percentile of scan intensity under the label mask.',
            computation="NumPy's default linear interpolation; equals median exactly.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.p75': FeatureDoc(
            measures='75th percentile of scan intensity under the label mask.',
            computation="NumPy's default linear interpolation.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.p95': FeatureDoc(
            measures='95th percentile of scan intensity under the label mask.',
            computation="NumPy's default linear interpolation.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.range': FeatureDoc(
            measures='Spread summary: max - min.',
            computation='max - min of the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.std': FeatureDoc(
            measures='Spread of scan intensity under the label mask.',
            computation='Population (ddof=0) standard deviation of the finite voxel values.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'image_features.per_label.{label}.first_order.voxel_count': FeatureDoc(
            measures='Number of finite scan voxels sampled under the label mask.',
            computation='Count after excluding NaN/inf scan voxels.',
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'image_features.per_label.{label}.label': FeatureDoc(
            measures='The integer label this image_features entry describes.',
            computation="Copied verbatim from the intensity extraction's label key.",
            units='',
            scale_sensitivity='identifier',
        ),
        'image_features.radiomics_available': FeatureDoc(
            measures='Whether the PyRadiomics backend produced any extended features.',
            computation='True only when PyRadiomics is installed, enabled, and ran without error for at least one label.',
            units='',
            scale_sensitivity='boolean',
        ),
        'overlaps[]': FeatureDoc(
            measures='The list of overlapping label pairs for this case.',
            computation="Empty when no two labels' voxel masks share a voxel; feature_report.build_features_block sorts non-empty entries by (label_a, label_b).",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'overlaps[].label_a': FeatureDoc(
            measures='The lower integer label of an overlapping pair.',
            computation='features.overlap.detect_overlaps enforces label_a < label_b.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'overlaps[].label_b': FeatureDoc(
            measures='The higher integer label of an overlapping pair.',
            computation='features.overlap.detect_overlaps enforces label_a < label_b.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'overlaps[].name_a': FeatureDoc(
            measures='Anatomical vertebra name for label_a.',
            computation='Looked up via the active LabelConvention; "unknown" for an unmapped integer.',
            units='',
            scale_sensitivity='categorical',
        ),
        'overlaps[].name_b': FeatureDoc(
            measures='Anatomical vertebra name for label_b.',
            computation='Looked up via the active LabelConvention; "unknown" for an unmapped integer.',
            units='',
            scale_sensitivity='categorical',
        ),
        'overlaps[].overlap_voxels': FeatureDoc(
            measures='Number of voxels claimed by both labels of the pair.',
            computation="Bitwise AND of the two labels' boolean mask channels, counted with count_nonzero.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label': FeatureDoc(
            measures='The per-label feature map, keyed by integer label.',
            computation='Empty for a 0-label map -- present as a leaf in that degenerate case, not silently dropped.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.centroid.centroid_mm[]': FeatureDoc(
            measures='Physical-space centroid.',
            computation='centroid_voxel[i] x spacing[i] per axis -- correct under anisotropic spacing.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.centroid.centroid_voxel[]': FeatureDoc(
            measures="Mean (x, y, z) voxel-index position of the label's voxels.",
            computation="np.mean(coords, axis=0) over the label's voxel-coordinate array.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.component_count': FeatureDoc(
            measures='Number of distinct connected pieces the label is split into.',
            computation="Direct output of scipy.ndimage.label's component count (6-connectivity).",
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'per_label.{label}.components.component_sizes[]': FeatureDoc(
            measures='Voxel count of each connected component, largest first.',
            computation='np.bincount over the labelled array, sorted descending.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.component_volumes_mm3[]': FeatureDoc(
            measures='Physical volume of each connected component.',
            computation='component_sizes[i] x product of voxel spacings, same order as component_sizes.',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.components.fragmentation_index': FeatureDoc(
            measures='Alias of largest_component_fraction, exposed under its item-025 public name.',
            computation='Same value as largest_component_fraction, always present so callers need not know the alias history.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.largest_component_fraction': FeatureDoc(
            measures="Fraction of the label's voxels belonging to its single largest piece.",
            computation='component_sizes[0] / sum(component_sizes); range (0, 1].',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.small_fragments[]': FeatureDoc(
            measures='Sizes of components below the configured noise threshold.',
            computation='Every component_sizes entry strictly below HeuristicConfig.min_fragment_voxels.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.stray_component_count': FeatureDoc(
            measures='Number of non-dominant (item-098 "stray") components.',
            computation='len(component_sizes) - 1, i.e. every component except the dominant one.',
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'per_label.{label}.components.stray_component_sizes[]': FeatureDoc(
            measures='Voxel sizes of every non-dominant component.',
            computation='component_sizes[1:], the item-098 stray population fragmentation/rogue-island checks read.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.stray_volume_fraction': FeatureDoc(
            measures="Fraction of the label's total volume that is non-dominant.",
            computation='stray_volume_mm3 / total physical_volume_mm3.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.components.stray_volume_mm3': FeatureDoc(
            measures='Total physical volume of every non-dominant component.',
            computation='sum(component_volumes_mm3[1:]).',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.geometry.bbox_physical.x_max': FeatureDoc(
            measures='Axis-aligned bounding box in mm, x maximum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_physical.x_min': FeatureDoc(
            measures='Axis-aligned bounding box in mm, x minimum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_physical.y_max': FeatureDoc(
            measures='Axis-aligned bounding box in mm, y maximum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_physical.y_min': FeatureDoc(
            measures='Axis-aligned bounding box in mm, y minimum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_physical.z_max': FeatureDoc(
            measures='Axis-aligned bounding box in mm, z maximum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_physical.z_min': FeatureDoc(
            measures='Axis-aligned bounding box in mm, z minimum.',
            computation='bbox_voxel index x spacing, voxel-centre convention (diagonal affine assumed).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.x_max': FeatureDoc(
            measures='Axis-aligned bounding-box maximum voxel index, x.',
            computation="Maximum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.x_min': FeatureDoc(
            measures='Axis-aligned bounding-box minimum voxel index, x.',
            computation="Minimum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.y_max': FeatureDoc(
            measures='Axis-aligned bounding-box maximum voxel index, y.',
            computation="Maximum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.y_min': FeatureDoc(
            measures='Axis-aligned bounding-box minimum voxel index, y.',
            computation="Minimum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.z_max': FeatureDoc(
            measures='Axis-aligned bounding-box maximum voxel index, z.',
            computation="Maximum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.bbox_voxel.z_min': FeatureDoc(
            measures='Axis-aligned bounding-box minimum voxel index, z.',
            computation="Minimum voxel-coordinate index over the label's voxel array, inclusive.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'per_label.{label}.geometry.extent_x_mm': FeatureDoc(
            measures='Physical span of the label along image axis x.',
            computation='(max_voxel_index - min_voxel_index + 1) x spacing for that axis.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.geometry.extent_y_mm': FeatureDoc(
            measures='Physical span of the label along image axis y.',
            computation='(max_voxel_index - min_voxel_index + 1) x spacing for that axis.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.geometry.extent_z_mm': FeatureDoc(
            measures='Physical span of the label along image axis z.',
            computation='(max_voxel_index - min_voxel_index + 1) x spacing for that axis.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.geometry.physical_volume_mm3': FeatureDoc(
            measures='Physical volume of the label.',
            computation='voxel_count x (sx . sy . sz), the product of the three header voxel spacings.',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'per_label.{label}.geometry.touches_anterior': FeatureDoc(
            measures='Whether the label touches the anterior image face.',
            computation="True when bbox_voxel's index equals 0 on the anterior-mapped axis (z=0).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.touches_inferior': FeatureDoc(
            measures='Whether the label touches the inferior image face.',
            computation="True when bbox_voxel's index equals 0 on the inferior-mapped axis (x=0).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.touches_left': FeatureDoc(
            measures='Whether the label touches the left image face.',
            computation="True when bbox_voxel's index equals 0 on the left-mapped axis (y=0).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.touches_posterior': FeatureDoc(
            measures='Whether the label touches the posterior image face.',
            computation="True when bbox_voxel's index equals shape[axis]-1 on the posterior-mapped axis (z=max).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.touches_right': FeatureDoc(
            measures='Whether the label touches the right image face.',
            computation="True when bbox_voxel's index equals shape[axis]-1 on the right-mapped axis (y=max).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.touches_superior': FeatureDoc(
            measures='Whether the label touches the superior image face.',
            computation="True when bbox_voxel's index equals shape[axis]-1 on the superior-mapped axis (x=max).",
            units='',
            scale_sensitivity='boolean',
        ),
        'per_label.{label}.geometry.voxel_count': FeatureDoc(
            measures='Number of voxels carrying the label value.',
            computation='len(argwhere(data == label)) -- a direct voxel count.',
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'per_label.{label}.label': FeatureDoc(
            measures='The integer vertebra label this per_label entry describes.',
            computation="Promoted from the label's LabelCentroid record.",
            units='',
            scale_sensitivity='identifier',
        ),
        'per_label.{label}.level_name': FeatureDoc(
            measures='Anatomical vertebra name, e.g. "T8", "L3".',
            computation='Looked up from the integer label via the active LabelConvention; an unmapped integer falls back to "unknown".',
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.lower_pct': FeatureDoc(
            measures='The lower percentile bound defining the reference in-range band.',
            computation='Default 1 (segfacet.reference.delta.DEFAULT_LOWER_PCT).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.reference_delta_version': FeatureDoc(
            measures='Schema-version discriminator for the reference_delta block.',
            computation='Literal "1.0" (item 046), independent of the reference artifact\'s own schema_version.',
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.reference_schema_version': FeatureDoc(
            measures="The reference artifact's own schema version, echoed for provenance.",
            computation='Copied verbatim from the loaded ReferenceDistribution.',
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.reference_source': FeatureDoc(
            measures='Provenance string naming the reference cohort/build.',
            computation="Copied verbatim from the loaded ReferenceDistribution's provenance.source.",
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.stratum': FeatureDoc(
            measures='Which reference stratum this delta was scored against.',
            computation='e.g. "all" (segfacet.reference.schema.ALL_STRATUM).',
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.upper_pct': FeatureDoc(
            measures='The upper percentile bound defining the reference in-range band.',
            computation='Default 99 (segfacet.reference.delta.DEFAULT_UPPER_PCT).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.available': FeatureDoc(
            measures="Whether this label's level (and stratum) is covered by the reference.",
            computation='False when the level or requested stratum is absent from the loaded ReferenceDistribution.',
            units='',
            scale_sensitivity='boolean',
        ),
        'reference_delta.{label}.distribution_distance': FeatureDoc(
            measures='Per-label aggregate anomaly score against the reference.',
            computation="RMS of the defined robust_z values across that label's tracked-and-present features.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.features.physical_volume_mm3.out_of_range': FeatureDoc(
            measures='Whether the value falls outside the configured percentile band.',
            computation='value < percentiles[p{lower_pct}] or value > percentiles[p{upper_pct}].',
            units='',
            scale_sensitivity='boolean',
        ),
        'reference_delta.{label}.features.physical_volume_mm3.percentile_rank': FeatureDoc(
            measures="Where the case's value falls in the reference's percentile grid.",
            computation="Piecewise-linear interpolation over the reference's stored percentile grid, anchored at min/max.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.features.physical_volume_mm3.robust_z': FeatureDoc(
            measures='Outlier-resistant z-score against the reference.',
            computation='(value - p50) / (IQR / 1.349), IQR = p75 - p25 from the reference; None when the reference IQR is 0.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.features.physical_volume_mm3.value': FeatureDoc(
            measures="The case's own value for this tracked feature.",
            computation="Read directly from the case's features_block for this label.",
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.features.physical_volume_mm3.z_score': FeatureDoc(
            measures='Standard z-score against the reference.',
            computation='(value - mean) / std; None when the reference std is 0 for this feature/level.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'reference_delta.{label}.label': FeatureDoc(
            measures='The integer label this reference-delta entry describes.',
            computation='Copied from the source LabelDelta dataclass.',
            units='',
            scale_sensitivity='identifier',
        ),
        'reference_delta.{label}.level_name': FeatureDoc(
            measures='Anatomical vertebra name for this reference-delta entry.',
            computation='Copied from the source LabelDelta dataclass.',
            units='',
            scale_sensitivity='categorical',
        ),
        'reference_delta.{label}.out_of_range_features[]': FeatureDoc(
            measures="Feature names whose case value falls outside the reference's percentile band.",
            computation='Every FeatureDelta with out_of_range True, sorted by feature name.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'relationships': FeatureDoc(
            measures='Case-level spine relationships, or null for a 0-label map.',
            computation='None when no labels are present; otherwise a nested object (see the individual relationships.* fields).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'relationships.is_continuous': FeatureDoc(
            measures='Whether the levels were labelled in a head-to-tail-consistent order.',
            computation="True iff each level's canonical rank is >= the previous one, walking the labels in their input order.",
            units='',
            scale_sensitivity='boolean',
        ),
        'relationships.missing_levels[]': FeatureDoc(
            measures='Canonical levels absent within the observed present-level span.',
            computation='Set difference between the canonical-order slice [first_present..last_present] and the present-levels set.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'relationships.neighbour_spacings_mm[]': FeatureDoc(
            measures='Centroid-to-centroid distance between anatomically adjacent levels.',
            computation='Euclidean distance (mm) between each consecutive pair in canonical order.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'relationships.out_of_order_labels[]': FeatureDoc(
            measures='Level names that broke the monotonic canonical-rank check.',
            computation='Every level, in input order, whose canonical rank is lower than the running maximum.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'relationships.present_levels[]': FeatureDoc(
            measures='Recognised anatomical levels, in canonical head-to-tail order.',
            computation='Every centroid whose level_name is in the canonical vocabulary, sorted by canonical rank.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.inter_tangent_angles_deg[]': FeatureDoc(
            measures="Angle between consecutive vertebrae's tangent vectors.",
            computation='Angle between each pair of adjacent unit tangent vectors along the spine.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.tangent_angles_deg[]': FeatureDoc(
            measures="Angle between the spline's local tangent and the superior-inferior axis, per vertebra.",
            computation="Evaluated at each vertebra's stored u via the spline's first derivative (splev, der=1).",
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.total_curvature_deg': FeatureDoc(
            measures='Global curvature magnitude: the larger of the coronal and sagittal per-plane sweeps.',
            computation='max(coronal_curvature_deg, sagittal_curvature_deg); 0 for a perfectly straight column. curvature_plane names which plane it came from.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.coronal_tangent_angles_deg[]': FeatureDoc(
            measures="Signed tangent angle in the coronal (R-S) plane at each centroid; positive tilts toward the patient's right as the spine advances cranially.",
            computation='degrees(atan2(t_R, t_S)) per centroid, unwrapped along the ordered sequence, computed from tangents normalised to a cranial-to-caudal traversal direction. Requires RAS-ordered mm centroids (axis 0 = Right, 1 = Anterior, 2 = Superior), guaranteed by io.load_volume.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.sagittal_tangent_angles_deg[]': FeatureDoc(
            measures='Signed tangent angle in the sagittal (A-S) plane at each centroid; positive tilts anterior.',
            computation='degrees(atan2(t_A, t_S)) per centroid, unwrapped along the ordered sequence, computed from tangents normalised to a cranial-to-caudal traversal direction. Requires RAS-ordered mm centroids (axis 0 = Right, 1 = Anterior, 2 = Superior), guaranteed by io.load_volume.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.coronal_curvature_deg': FeatureDoc(
            measures='Coronal-plane (R-S) curvature sweep.',
            computation='max - min of coronal_tangent_angles_deg. 0.0 for a curve confined to the sagittal plane. Requires RAS-ordered mm centroids, guaranteed by io.load_volume.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.sagittal_curvature_deg': FeatureDoc(
            measures='Sagittal-plane (A-S) curvature sweep.',
            computation='max - min of sagittal_tangent_angles_deg. 0.0 for a curve confined to the coronal plane. Requires RAS-ordered mm centroids, guaranteed by io.load_volume.',
            units='degrees',
            scale_sensitivity='dimensionless',
        ),
        'stage3.curvature.curvature_plane': FeatureDoc(
            measures='Which anatomical plane (coronal or sagittal) total_curvature_deg came from.',
            computation='"coronal" when coronal_curvature_deg >= sagittal_curvature_deg, else "sagittal". An exact tie, including a straight spine\'s 0.0/0.0, resolves to "coronal".',
            units='',
            scale_sensitivity='categorical',
        ),
        'stage3.monotonic_consistency.is_monotonic': FeatureDoc(
            measures="Whether every vertebra's closest-spline-parameter u increases along the anatomical order.",
            computation='False as soon as u[i] >= u[i+1] anywhere in the ordered sequence.',
            units='',
            scale_sensitivity='boolean',
        ),
        'stage3.monotonic_consistency.non_monotonic_pairs[]': FeatureDoc(
            measures='Level-name pairs whose spline parameter does not advance.',
            computation='Consecutive (level_a, level_b) pairs where u[i] >= u[i+1]; equal u values count as a violation too.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.monotonic_consistency.u_values[]': FeatureDoc(
            measures="Each vertebra's closest-spline-parameter u, in input order.",
            computation='The closest_u value computed for every vertebra in the ordered centroid sequence.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_neighbourhood[].deviation_score': FeatureDoc(
            measures="How anomalous the focal vertebra's scored features are relative to its sliding-window neighbours.",
            computation='max() of the leave-one-out z-scores (per scored feature) of the focal vertebra against the other window members.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_neighbourhood[].is_outlier': FeatureDoc(
            measures='Whether the focal vertebra is flagged as a local neighbourhood outlier.',
            computation='deviation_score >= the configured outlier_threshold (default 2.0).',
            units='',
            scale_sensitivity='boolean',
        ),
        'stage3.per_label_neighbourhood[].label': FeatureDoc(
            measures='Integer label of the focal vertebra in this neighbourhood entry.',
            computation='Copied verbatim from the focal centroid.',
            units='',
            scale_sensitivity='identifier',
        ),
        'stage3.per_label_neighbourhood[].level_name': FeatureDoc(
            measures='Anatomical level name of the focal vertebra in this neighbourhood entry.',
            computation='Copied verbatim from the focal centroid.',
            units='',
            scale_sensitivity='identifier',
        ),
        'stage3.per_label_neighbourhood[].stats.offset_mm.mean': FeatureDoc(
            measures='Mean spline offset (mm) over the sliding window (including the focal vertebra).',
            computation='Mean of per_label_offsets[].offset_mm over the window indices.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.offset_mm.median': FeatureDoc(
            measures='Median spline offset (mm) over the sliding window (including the focal vertebra).',
            computation='Median of per_label_offsets[].offset_mm over the window indices.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.offset_mm.std': FeatureDoc(
            measures='Standard deviation of spline offset (mm) over the sliding window (including the focal vertebra).',
            computation='Population std (ddof=0) of per_label_offsets[].offset_mm over the window indices.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.offset_mm.z_score': FeatureDoc(
            measures="The focal vertebra's spline offset expressed as a leave-one-out z-score against its window neighbours.",
            computation='abs(focal offset_mm - mean of neighbour offset_mm) / max(std of neighbour offset_mm, _MIN_STD).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_neighbourhood[].stats.spacing_mm.mean': FeatureDoc(
            measures='Mean per-element inter-centroid spacing (mm) over the sliding window (including the focal vertebra).',
            computation='Mean, over the window, of a caller-supplied per-element spacing value: the distance to the next vertebra in the ordered sequence (the last vertebra reuses the distance to its previous neighbour).',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.spacing_mm.median': FeatureDoc(
            measures='Median per-element inter-centroid spacing (mm) over the sliding window (including the focal vertebra).',
            computation='Median, over the window, of the same per-element spacing value used for the mean.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.spacing_mm.std': FeatureDoc(
            measures='Standard deviation of per-element inter-centroid spacing (mm) over the sliding window (including the focal vertebra).',
            computation='Population std (ddof=0), over the window, of the same per-element spacing value used for the mean.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.spacing_mm.z_score': FeatureDoc(
            measures="The focal vertebra's per-element spacing expressed as a leave-one-out z-score against its window neighbours. Reported but deliberately unscored by default -- see UNSCORED_RATIONALE in segfacet.features.neighbourhood.",
            computation='abs(focal spacing_mm - mean of neighbour spacing_mm) / max(std of neighbour spacing_mm, _MIN_STD).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_neighbourhood[].stats.volume_mm3.mean': FeatureDoc(
            measures='Mean per-label physical volume (mm3) over the sliding window (including the focal vertebra).',
            computation='Mean of per_label.{label}.geometry.physical_volume_mm3 over the window indices.',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.volume_mm3.median': FeatureDoc(
            measures='Median per-label physical volume (mm3) over the sliding window (including the focal vertebra).',
            computation='Median of per_label.{label}.geometry.physical_volume_mm3 over the window indices.',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.volume_mm3.std': FeatureDoc(
            measures='Standard deviation of per-label physical volume (mm3) over the sliding window (including the focal vertebra).',
            computation='Population std (ddof=0) of per_label.{label}.geometry.physical_volume_mm3 over the window indices.',
            units='mm3',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_neighbourhood[].stats.volume_mm3.z_score': FeatureDoc(
            measures="The focal vertebra's physical volume expressed as a leave-one-out z-score against its window neighbours.",
            computation='abs(focal volume_mm3 - mean of neighbour volume_mm3) / max(std of neighbour volume_mm3, _MIN_STD).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_neighbourhood[].window_labels[]': FeatureDoc(
            measures='Integer labels of every vertebra in the focal vertebra\'s sliding window (including itself).',
            computation='Labels of the elements at window indices max(0, i - window_n//2) .. min(n-1, i + window_n//2).',
            units='',
            scale_sensitivity='identifier',
        ),
        'stage3.per_label_offsets[].closest_u': FeatureDoc(
            measures="Spline parameter (0-1) of the point on the curve nearest this vertebra's centroid.",
            computation='Coarse 500-point scan over u, refined with a bounded scipy.optimize.minimize_scalar (xatol 1e-6).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_offsets[].dx_mm': FeatureDoc(
            measures='Signed x-axis displacement from the fitted spline.',
            computation='centroid_mm - closest spline point, x component.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_offsets[].dy_mm': FeatureDoc(
            measures='Signed y-axis displacement from the fitted spline.',
            computation='centroid_mm - closest spline point, y component.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_offsets[].dz_mm': FeatureDoc(
            measures='Signed z-axis displacement from the fitted spline.',
            computation='centroid_mm - closest spline point, z component.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_offsets[].label': FeatureDoc(
            measures='The integer label this spline-offset entry describes.',
            computation='Copied from the source VertebralSplineOffset dataclass.',
            units='',
            scale_sensitivity='identifier',
        ),
        'stage3.per_label_offsets[].level_name': FeatureDoc(
            measures='Anatomical vertebra name for this spline-offset entry.',
            computation='Copied from the source VertebralSplineOffset dataclass.',
            units='',
            scale_sensitivity='categorical',
        ),
        'stage3.per_label_offsets[].offset_mm': FeatureDoc(
            measures="Perpendicular distance from the vertebra's centroid to the fitted spline.",
            computation='Euclidean distance (mm) to the closest spline point at closest_u.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.per_label_offsets[].offset_voxel': FeatureDoc(
            measures='Anisotropic-aware perpendicular offset.',
            computation='Same as offset_mm but with each axis scaled by 1/spacing before taking the norm.',
            units='voxels',
            scale_sensitivity='voxel count',
        ),
        'stage3.per_label_orientations[].eigenvalue_ratio': FeatureDoc(
            measures='Anisotropy of the per-vertebra voxel cloud.',
            computation='lambda_max / lambda_second of the PCA covariance; infinite for a degenerate flat cloud, 0 for a single-voxel label.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.per_label_orientations[].label': FeatureDoc(
            measures='The integer label this orientation entry describes.',
            computation='Copied from the source VertebralOrientation dataclass.',
            units='',
            scale_sensitivity='identifier',
        ),
        'stage3.per_label_orientations[].level_name': FeatureDoc(
            measures='Anatomical vertebra name for this orientation entry.',
            computation='Copied from the source VertebralOrientation dataclass.',
            units='',
            scale_sensitivity='categorical',
        ),
        'stage3.per_label_orientations[].principal_axis[]': FeatureDoc(
            measures='Per-vertebra orientation via PCA of its voxel cloud.',
            computation='Eigenvector of the largest eigenvalue of the 3x3 covariance of the mean-centred, spacing-scaled voxel coordinates.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.spacing_consistency.cv_spacing': FeatureDoc(
            measures='Regularity of inter-vertebra spacing.',
            computation='population-std(spacings) / mean(spacings); 0.0 when there is only one spacing.',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.spacing_consistency.deviations_mm[]': FeatureDoc(
            measures="Per-pair spacing's signed deviation from the mean.",
            computation='spacings_mm[i] - mean_spacing_mm.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.spacing_consistency.mean_spacing_mm': FeatureDoc(
            measures='Mean inter-vertebra centroid spacing.',
            computation='Arithmetic mean of the neighbour-to-neighbour centroid distances.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
        'stage3.spacing_consistency.outlier_pairs[]': FeatureDoc(
            measures='Level-name pairs whose spacing is an outlier.',
            computation='A pair is an outlier when its spacing is >= 2.0x or <= 0.3x the mean spacing (both thresholds configurable).',
            units='',
            scale_sensitivity='dimensionless',
        ),
        'stage3.spacing_consistency.spacings_mm[]': FeatureDoc(
            measures='Per-pair inter-vertebra centroid spacing.',
            computation='Euclidean centroid-to-centroid distance for each adjacent pair, in input order.',
            units='mm',
            scale_sensitivity='scales with spacing',
        ),
    }
)
