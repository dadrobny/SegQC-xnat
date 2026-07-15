"""segqc.reference.ingest — VerSe GT ingestion: cohort loader & feature-
extraction driver (Stage 6, item 044).

Turns a directory of ground-truth (GT) label maps into the per-case,
per-level ``FeatureRecord``s that the item-043 aggregation core
(``segqc.reference.aggregate_reference``) consumes.

Scope
-----
This module is **ingestion only**:

* It does **not** compute means / percentiles / distributions (that is
  ``segqc.reference.aggregate.aggregate_reference``, item 043) — it produces
  the *records* that function consumes.
* It does **not** write any reference artifact to disk, version it, or stamp
  build-time provenance (``source`` / ``config_hash`` / ``build_date``) —
  that is item 045's builder/loader.
* It does **not** change the feature engine — it calls
  ``segqc.pipeline.extract_feature_record`` unchanged and reads geometry /
  spline-offset values out of its return value.
* It is deterministic and read-only: no wall-clock reads, no mutation of the
  caller's ``config``/``convention``, no writes to the cohort directory.

Discovery convention
---------------------
A "subject" is any file in the cohort directory whose name ends with
``seg_suffix`` (default ``DEFAULT_SEG_SUFFIX = "_seg.nii.gz"``). The
``subject_id`` is the filename stem with that suffix stripped. This mirrors
the Stage 5 corpus convention (``segqc.synth.corpus.write_corpus``), so a
synthetic cohort written that way is a conforming directory out of the box.
An optional sibling scan (``<subject_id><DEFAULT_SCAN_SUFFIX>``) is discovered
per subject; it is read only when the caller opts in via ``with_intensity=
True`` (item 063), in which case per-label first-order intensity statistics
(item 059's ``compute_label_intensity``) are folded into that level's
``features``. With the default ``with_intensity=False``, the scan is
discovered but not read, exactly as before item 063.

Vocabulary
----------
``INGESTED_FEATURES`` is the pinned per-level *geometric* feature
vocabulary: the four ``LabelGeometry`` scalars plus ``spline_offset_mm``
(present only for subjects with >= 2 recognised levels, since Stage 3 is only
computed then). ``INGESTED_INTENSITY_FEATURES`` is the separate,
``intensity_``-prefixed per-label *intensity* vocabulary (item 063), folded
in only when ``with_intensity=True`` and a grid-aligned sibling scan is
present.

Size proxy
----------
``SIZE_PROXY_NAME = "mean_vertebra_volume_mm3"`` — the mean
``physical_volume_mm3`` across a subject's recognised, present levels.
Stamped identically on every record for that subject when
``with_size_proxy=True`` (the default); ``None`` when disabled.

Labels
------
Integer labels are normalised to canonical anatomical names via
``segqc.labels.LabelConvention``. Background (value 0) is never a subject
level. Any present integer with no mapping in the convention is skipped —
never turned into a fabricated level — and recorded in
``SubjectIngest.skipped_labels``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple

from .schema import FeatureRecord

if TYPE_CHECKING:  # pragma: no cover - typing only
    from segqc.config import HeuristicConfig
    from segqc.labels import LabelConvention

__all__ = [
    "DEFAULT_SEG_SUFFIX",
    "DEFAULT_SCAN_SUFFIX",
    "SIZE_PROXY_NAME",
    "INGESTED_FEATURES",
    "INGESTED_INTENSITY_FEATURES",
    "INGESTED_MORPHOLOGY_FEATURES",
    "SubjectIngest",
    "CohortIngest",
    "ingest_subject",
    "ingest_cohort",
]

# Label-map filename suffix used to discover subjects (Stage 5 corpus
# convention: ``<case_id>_seg.nii.gz``).
DEFAULT_SEG_SUFFIX: str = "_seg.nii.gz"
# Optional matching scan filename suffix (same subject stem). Currently
# unused by the Stage 2/3 geometry features this driver reads; threaded
# through for a future feature that needs the scan.
DEFAULT_SCAN_SUFFIX: str = "_scan.nii.gz"
# Documented identity of the per-subject size proxy this driver computes.
SIZE_PROXY_NAME: str = "mean_vertebra_volume_mm3"

# The feature-name vocabulary emitted per (subject, level) record — aligned
# with the 043 Assumptions "pinned vocabulary" and the Stage 2/3 dataclass
# field names.
INGESTED_FEATURES: Tuple[str, ...] = (
    "physical_volume_mm3",
    "extent_x_mm",
    "extent_y_mm",
    "extent_z_mm",
    "spline_offset_mm",
)

# The per-level *intensity* feature-name vocabulary (item 063) -- a
# deliberately SEPARATE, companion constant. ``INGESTED_FEATURES`` above is
# NOT widened: ``segqc.reference.delta``'s ``_GEOMETRY_FEATURES`` derives
# from it, and appending intensity names there would silently reclassify
# them as "geometry" and prematurely couple this item into item 064's scope
# (see item 063 spec's Assumptions, "CRITICAL COUPLING"). Mirrors the
# statistical fields of item 059's ``LabelIntensity`` (excluding the
# bookkeeping fields ``voxel_count`` / ``n_nonfinite_excluded``, which are
# counts, not HU statistics), prefixed ``intensity_`` for a self-describing,
# collision-free vocabulary.
INGESTED_INTENSITY_FEATURES: Tuple[str, ...] = (
    "intensity_mean",
    "intensity_median",
    "intensity_std",
    "intensity_min",
    "intensity_max",
    "intensity_p05",
    "intensity_p25",
    "intensity_p50",
    "intensity_p75",
    "intensity_p95",
    "intensity_range",
    "intensity_iqr",
    "intensity_entropy",
)

# The per-level *geometric-morphology* feature-name vocabulary (item 081) --
# a deliberately SEPARATE, companion constant, never routed through the
# geometry path (``INGESTED_FEATURES`` / ``entry["geometry"]``) nor the
# intensity path (the ``intensity_`` prefix). Drawn straight from the
# per-label ``components`` block (item 012) and the Stage 3
# ``per_label_orientations`` block (item 019). Deliberately excludes
# ``fragmentation_index`` (an exact alias of ``largest_component_fraction``
# that would double-weight the same signal) and ``principal_axis`` (a
# unit-vector, not a per-level scalar).
INGESTED_MORPHOLOGY_FEATURES: Tuple[str, ...] = (
    "largest_component_fraction",
    "component_count",
    "eigenvalue_ratio",
)

# The ``LabelIntensity`` statistical field names, in the same order as
# ``INGESTED_INTENSITY_FEATURES`` (each prefixed with ``intensity_`` to
# produce the corresponding vocabulary name).
_INTENSITY_STAT_FIELDS: Tuple[str, ...] = (
    "mean",
    "median",
    "std",
    "min",
    "max",
    "p05",
    "p25",
    "p50",
    "p75",
    "p95",
    "range",
    "iqr",
    "entropy",
)


def _intensity_features_dict(label_intensity) -> dict:
    """Map a populated (non-sentinel) ``LabelIntensity``'s non-``None``
    statistical fields to their ``intensity_<field>`` keys.

    A field whose value is ``None`` (including every field of the all-``None``
    sentinel) contributes **no** key -- ``None`` is never inserted into a
    ``features`` mapping (a downstream ``float(value)`` in
    ``aggregate_reference`` must never see ``None``).
    """
    features = {}
    for field_name in _INTENSITY_STAT_FIELDS:
        value = getattr(label_intensity, field_name)
        if value is not None:
            features[f"intensity_{field_name}"] = float(value)
    return features


@dataclass(frozen=True)
class SubjectIngest:
    """One discovered subject and the records extracted from it."""

    subject_id: str
    seg_path: str
    records: Tuple[FeatureRecord, ...]
    skipped_labels: Tuple[int, ...]


@dataclass(frozen=True)
class CohortIngest:
    """The whole-cohort ingestion result."""

    subjects: Tuple[SubjectIngest, ...]
    records: Tuple[FeatureRecord, ...]
    size_proxy_name: Optional[str]


def _canonical_rank(level_name: str) -> Tuple[int, str]:
    """Deterministic sort key: ``CANONICAL_ORDER`` rank, then name.

    Names outside ``CANONICAL_ORDER`` (not expected here, since unmapped
    labels are skipped before a record is built) sort after every canonical
    name, keeping the key total.
    """
    from segqc.labels import CANONICAL_ORDER

    try:
        rank = CANONICAL_ORDER.index(level_name)
    except ValueError:
        rank = len(CANONICAL_ORDER)
    return (rank, level_name)


def ingest_subject(
    seg_path,
    *,
    config: "HeuristicConfig",
    convention: "Optional[LabelConvention]" = None,
    scan_path=None,
    subject_id: Optional[str] = None,
    with_size_proxy: bool = True,
    with_intensity: bool = False,
    with_morphology: bool = False,
) -> SubjectIngest:
    """Load one GT label map, run the feature engine, and emit one
    ``FeatureRecord`` per recognised, present level.

    Read-only and deterministic: never mutates ``config``/``convention``,
    reads no wall clock, writes nothing.

    Parameters
    ----------
    seg_path:
        Path to the label-map NIfTI file.
    config:
        A :class:`~segqc.config.HeuristicConfig`, threaded into
        ``extract_feature_record`` unchanged.
    convention:
        The :class:`~segqc.labels.LabelConvention` used to normalise integer
        labels to canonical names. Defaults to
        :meth:`~segqc.labels.LabelConvention.default`.
    scan_path:
        Optional path to a matching scan. Read only when ``with_intensity``
        is ``True``; otherwise accepted for interface symmetry with
        ``ingest_cohort`` but unused.
    subject_id:
        Explicit subject id; defaults to the filename stem with
        ``DEFAULT_SEG_SUFFIX`` stripped.
    with_size_proxy:
        When ``True`` (default), stamp each record with the subject's mean
        ``physical_volume_mm3`` across its recognised levels
        (``SIZE_PROXY_NAME``); when ``False``, every record's ``size_proxy``
        is ``None``.
    with_intensity:
        When ``True`` (default ``False``, preserving existing callers) and
        ``scan_path`` is not ``None``, load the scan and fold each
        recognised level's per-label first-order intensity statistics
        (item 059's ``compute_label_intensity``) into that level's
        ``features`` under ``intensity_*`` keys. A sentinel (all-``None``)
        ``LabelIntensity`` contributes no keys. When ``True`` but
        ``scan_path`` is ``None``, degrades silently to geometry-only. A
        grid-misaligned scan raises ``ValueError`` (propagated from the
        extractor).
    with_morphology:
        When ``True`` (default ``False``, preserving existing callers), fold
        each recognised level's geometric-morphology values --
        ``largest_component_fraction`` / ``component_count`` from that
        level's ``components`` block, and (when the subject has >= 2
        recognised levels, so Stage 3 ran) ``eigenvalue_ratio`` from its
        Stage 3 orientation entry -- into that level's ``features`` under
        their own (unprefixed) keys. Read from the ``components`` /
        orientation blocks, never from ``entry["geometry"]``. A single-label
        subject (no Stage 3) omits ``eigenvalue_ratio`` entirely -- ``None``
        is never inserted into a ``features`` mapping.

    Returns
    -------
    SubjectIngest
    """
    import nibabel as nib

    from segqc.labels import LabelConvention
    from segqc.pipeline import extract_feature_record

    if convention is None:
        convention = LabelConvention.default()

    seg_path_str = str(seg_path)
    if subject_id is None:
        stem = os.path.basename(seg_path_str)
        if stem.endswith(DEFAULT_SEG_SUFFIX):
            stem = stem[: -len(DEFAULT_SEG_SUFFIX)]
        subject_id = stem

    seg_img = nib.load(seg_path_str)

    block = extract_feature_record(seg_img, config)

    offsets_by_label = {}
    orientations_by_label = {}
    stage3 = block.get("stage3")
    if stage3 is not None:
        for entry in stage3.get("per_label_offsets", []):
            offsets_by_label[int(entry["label"])] = entry["offset_mm"]
        for entry in stage3.get("per_label_orientations", []):
            orientations_by_label[int(entry["label"])] = entry["eigenvalue_ratio"]

    intensity_by_label = {}
    if with_intensity and scan_path is not None:
        from segqc.features.intensity import compute_intensity_features

        scan_img = nib.load(str(scan_path))
        intensity_by_label = compute_intensity_features(scan_img, seg_img)

    skipped_labels = []
    # (level_name, features_dict) pairs for recognised, present levels, built
    # in the per_label block's ascending-integer-label order; the driver
    # re-sorts by canonical rank before returning.
    collected = []
    for label_str, entry in block["per_label"].items():
        label_value = int(entry["label"])
        level_name = convention.name_of(label_value)
        if not convention.is_known(label_value):
            skipped_labels.append(label_value)
            continue

        geometry = entry["geometry"]
        features = {
            "physical_volume_mm3": float(geometry["physical_volume_mm3"]),
            "extent_x_mm": float(geometry["extent_x_mm"]),
            "extent_y_mm": float(geometry["extent_y_mm"]),
            "extent_z_mm": float(geometry["extent_z_mm"]),
        }
        if label_value in offsets_by_label:
            features["spline_offset_mm"] = float(offsets_by_label[label_value])

        if label_value in intensity_by_label:
            features.update(_intensity_features_dict(intensity_by_label[label_value]))

        if with_morphology:
            components = entry["components"]
            features["largest_component_fraction"] = float(
                components["largest_component_fraction"]
            )
            features["component_count"] = float(components["component_count"])
            if label_value in orientations_by_label:
                features["eigenvalue_ratio"] = float(
                    orientations_by_label[label_value]
                )

        collected.append((level_name, features))

    size_proxy = None
    if with_size_proxy and collected:
        size_proxy = sum(
            features["physical_volume_mm3"] for _name, features in collected
        ) / len(collected)

    collected.sort(key=lambda pair: _canonical_rank(pair[0]))

    records = tuple(
        FeatureRecord(
            subject_id=subject_id,
            level_name=level_name,
            features=features,
            size_proxy=size_proxy,
        )
        for level_name, features in collected
    )

    return SubjectIngest(
        subject_id=subject_id,
        seg_path=seg_path_str,
        records=records,
        skipped_labels=tuple(sorted(skipped_labels)),
    )


def ingest_cohort(
    cohort_dir,
    *,
    config: "Optional[HeuristicConfig]" = None,
    convention: "Optional[LabelConvention]" = None,
    seg_suffix: str = DEFAULT_SEG_SUFFIX,
    with_size_proxy: bool = True,
    with_intensity: bool = False,
    with_morphology: bool = False,
) -> CohortIngest:
    """Walk ``cohort_dir`` for label maps matching ``seg_suffix``, ingest
    each subject in ascending ``subject_id`` order, and return the
    flattened, deterministic record set.

    Tolerates missing levels, partial FOV, and transitional labels without
    raising (an unrecognised subject file that fails to load is not
    swallowed, however — a genuinely malformed cohort directory should
    surface). Read-only and deterministic: no wall-clock reads, no mutation
    of ``config``/``convention``, no writes to ``cohort_dir``.

    Parameters
    ----------
    cohort_dir:
        Directory to walk for ``*<seg_suffix>`` files. Must exist.
    config:
        Defaults to :func:`segqc.config.bundled_default_config`.
    convention:
        Defaults to :meth:`segqc.labels.LabelConvention.default`.
    seg_suffix:
        Filename suffix identifying a subject's label map.
    with_size_proxy:
        Forwarded to :func:`ingest_subject` for every discovered subject.
    with_intensity:
        Forwarded to :func:`ingest_subject` for every discovered subject
        (default ``False``, preserving existing callers).
    with_morphology:
        Forwarded to :func:`ingest_subject` for every discovered subject
        (default ``False``, preserving existing callers).

    Returns
    -------
    CohortIngest
    """
    from segqc.config import bundled_default_config
    from segqc.labels import LabelConvention

    if config is None:
        config = bundled_default_config()
    if convention is None:
        convention = LabelConvention.default()

    entries = os.listdir(cohort_dir)

    discovered = []
    for name in entries:
        if not name.endswith(seg_suffix):
            continue
        subject_id = name[: -len(seg_suffix)]
        seg_path = os.path.join(str(cohort_dir), name)
        scan_path = os.path.join(str(cohort_dir), f"{subject_id}{DEFAULT_SCAN_SUFFIX}")
        if not os.path.exists(scan_path):
            scan_path = None
        discovered.append((subject_id, seg_path, scan_path))

    discovered.sort(key=lambda item: item[0])

    subjects = tuple(
        ingest_subject(
            seg_path,
            config=config,
            convention=convention,
            scan_path=scan_path,
            subject_id=subject_id,
            with_size_proxy=with_size_proxy,
            with_intensity=with_intensity,
            with_morphology=with_morphology,
        )
        for subject_id, seg_path, scan_path in discovered
    )

    records = tuple(
        record
        for subject in subjects
        for record in subject.records
    )

    return CohortIngest(
        subjects=subjects,
        records=records,
        size_proxy_name=SIZE_PROXY_NAME if with_size_proxy else None,
    )
