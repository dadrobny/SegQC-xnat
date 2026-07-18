"""segqc.reference.artifact — versioned reference-data artifact + builder
(Stage 6, item 045).

Chains item 044's cohort ingestion (``segqc.reference.ingest.ingest_cohort``)
and item 043's aggregation core (``segqc.reference.aggregate_reference``)
into a single **reproducible, versioned reference-data artifact**, plus the
plumbing to build it, ship a default copy, and load it back:

* :func:`build_reference` — ``cohort_dir`` -> :class:`~segqc.reference.schema.ReferenceDistribution`,
  stamping a deterministic :class:`~segqc.reference.schema.Provenance`
  (``source``, ``config_hash``, caller-supplied ``build_date``,
  ``size_proxy_name``).
* :func:`write_artifact` / :func:`load_artifact` — the byte-reproducible
  serialiser/loader pair. ``write_artifact`` writes
  ``to_json_text(dist)`` as raw UTF-8 bytes via ``Path.write_bytes`` (never
  ``write_text``, whose ``newline=`` kwarg is 3.10+ and which rewrites line
  endings on Windows), so the artifact is byte-identical across platforms and
  runs. ``load_artifact`` strictly validates ``schema_version`` and raises
  the typed :class:`ReferenceArtifactError` on any malformed/missing/
  incompatible input.
* :func:`build_default_cohort` / :func:`build_and_write_default` — the fixed,
  deterministic synthetic cohort (via
  :func:`segqc.synth.clean_gt.build_clean_spine` for the label maps and item
  058's :func:`segqc.synth.intensity.paint_clean_scan` for a co-registered
  painted scan per subject, both seeded/no-wall-clock) that produces the
  bundled default artifact
  (``src/segqc/reference/reference_default.json``), loadable via
  :func:`bundled_default_reference` / :func:`default_artifact_path`
  (``importlib.resources``, mirroring
  ``segqc.config.default_config_path``/``bundled_default_config``).
* :func:`main` — ``python -m segqc.reference.artifact [--out JSON]``
  regenerates the committed default artifact in place.

Determinism contract
---------------------
Every artifact write goes through :func:`write_artifact`
(``Path.write_bytes`` on a ``"\\n"``-terminated UTF-8 string); the committed
default artifact is pinned ``text eol=lf`` in ``.gitattributes`` so a fresh
checkout under Windows ``core.autocrlf=true`` stays byte-clean. ``build_date``
is always caller-supplied (never ``date.today()``); the committed default
bakes the fixed constant :data:`DEFAULT_BUILD_DATE`.

Two rebuild commands
---------------------
Rebuild the artifact from a mounted real VerSe directory, writing a
**separately versioned** file (``reference_verse_vN.json``,
``provenance.source == "verse-vN"``) that never overwrites the bundled
default::

    segqc build-reference --cohort /mnt/verse \\
        --out src/segqc/reference/reference_verse_v1.json \\
        --source verse-v1 --build-date YYYY-MM-DD \\
        --seg-suffix <the real VerSe vertebra-mask suffix>

(see :doc:`/reference-build` for the exact staged-cohort ``--seg-suffix``
value and the operator staging steps it depends on)

Regenerate the committed bundled default from the fixed synthetic cohort::

    python -m segqc.reference.artifact

See :doc:`/reference-build` (``docs/reference-build.md``, item 082) for the
full storage/versioning policy, real-VerSe acquisition + cohort-staging
notes, and the deployment-selection mechanism (``segqc run
--reference-artifact`` / ``reference.artifact_path``).

Scope boundary: this module does not compute delta metrics, add rules, touch
the bounds config, or wire the artifact into ``segqc run`` (items 046-049);
it only produces, ships, and loads the artifact those items consume.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Union

from .ingest import DEFAULT_SCAN_SUFFIX, DEFAULT_SEG_SUFFIX, SIZE_PROXY_NAME
from .schema import SCHEMA_VERSION, Provenance, ReferenceDistribution, from_dict, to_json_text

if TYPE_CHECKING:  # pragma: no cover - typing only
    from segqc.config import HeuristicConfig
    from segqc.labels import LabelConvention

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "DEFAULT_ARTIFACT_NAME",
    "DEFAULT_SOURCE",
    "DEFAULT_BUILD_DATE",
    "PRODUCTION_ARTIFACT_NAME",
    "ReferenceArtifactError",
    "config_hash",
    "build_reference",
    "write_artifact",
    "load_artifact",
    "default_artifact_path",
    "bundled_default_reference",
    "bundled_production_reference_path",
    "bundled_production_reference",
    "build_default_cohort",
    "build_and_write_default",
    "main",
]

#: Re-export of item 043's ``SCHEMA_VERSION`` -- the version the loader accepts.
ARTIFACT_SCHEMA_VERSION: str = SCHEMA_VERSION

#: Bundled package-data filename for the committed default artifact.
DEFAULT_ARTIFACT_NAME: str = "reference_default.json"

#: ``provenance.source`` for the bundled default artifact.
DEFAULT_SOURCE: str = "synthetic-verse-cohort"

#: Fixed ``build_date`` baked into the committed default artifact --
#: deterministic regardless of when ``python -m segqc.reference.artifact``
#: is actually run.
DEFAULT_BUILD_DATE: str = "2026-07-11"

#: Bundled package-data filename for the committed **production** artifact
#: (item 090) -- the real, held-out-training VerSe19 distribution that the
#: run path attaches by default, distinct from the synthetic
#: :data:`DEFAULT_ARTIFACT_NAME` Plane-1 baseline.
PRODUCTION_ARTIFACT_NAME: str = "reference_verse_v1.json"


class ReferenceArtifactError(Exception):
    """Raised when an artifact file is missing, malformed, or carries an
    incompatible ``schema_version`` (mirrors ``segqc.config.SegQCConfigError``)."""


# --------------------------------------------------------------------------- #
# config_hash
# --------------------------------------------------------------------------- #


def config_hash(config: "HeuristicConfig") -> str:
    """A stable, deterministic hex digest of *config*, so an artifact is
    traceable to the config that built it.

    SHA-256 over the canonical (sorted-key) JSON encoding of the config's
    public, extraction-affecting fields. Reads no wall clock; pure.
    """
    canonical = {
        "schema_version": config.schema_version,
        "min_foreground_voxels": config.min_foreground_voxels,
        "min_label_count": config.min_label_count,
        "min_fragment_voxels": config.min_fragment_voxels,
        "rules": config.rules,
        "verdict": config.verdict,
    }
    text = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# build_reference
# --------------------------------------------------------------------------- #


def build_reference(
    cohort_dir: Union[str, "os.PathLike"],
    *,
    source: str,
    build_date: str,
    config: "Optional[HeuristicConfig]" = None,
    convention: "Optional[LabelConvention]" = None,
    seg_suffix: str = DEFAULT_SEG_SUFFIX,
    size_strata_edges: "Optional[Sequence[float]]" = None,
    stratum_labels: "Optional[Sequence[str]]" = None,
    with_intensity: bool = True,
    with_morphology: bool = True,
) -> ReferenceDistribution:
    """Chain ``ingest_cohort`` -> ``aggregate_reference`` into a
    :class:`~segqc.reference.schema.ReferenceDistribution`, stamping a
    deterministic :class:`~segqc.reference.schema.Provenance`.

    Parameters
    ----------
    cohort_dir:
        Directory to walk for label maps (forwarded to ``ingest_cohort``).
    source:
        Free-text provenance label for the cohort (e.g. ``"verse-v1"``).
    build_date:
        Caller-supplied ISO ``"YYYY-MM-DD"`` string. **Not** ``date.today()``
        -- this function reads no wall clock, so the same arguments always
        yield byte-identical output.
    config:
        Defaults to :func:`segqc.config.bundled_default_config`.
    convention:
        Defaults to :meth:`segqc.labels.LabelConvention.default`.
    seg_suffix:
        Forwarded to ``ingest_cohort``.
    size_strata_edges, stratum_labels:
        Forwarded to ``aggregate_reference``. When ``size_strata_edges`` is
        given, the cohort is ingested with ``with_size_proxy=True`` and
        ``provenance.size_proxy_name`` is set to ``SIZE_PROXY_NAME``;
        otherwise no size proxy is computed and ``size_proxy_name`` is
        ``None``.
    with_intensity:
        Forwarded to ``ingest_cohort`` (default ``True``, opt-in at this
        layer, item 063). When ``True``, per-level intensity statistics are
        folded into the ingested records for any subject with a grid-aligned
        sibling scan; subjects with no scan degrade to geometry-only.
        Purely additive -- the geometric ``feature_stats`` produced are
        identical regardless of this flag.
    with_morphology:
        Forwarded to ``ingest_cohort`` (default ``True``, opt-in-by-default
        at this layer, item 081). When ``True``, per-level geometric-
        morphology values (``largest_component_fraction``, ``component_count``,
        ``eigenvalue_ratio``) are folded into the ingested records. Purely
        additive -- the geometric and intensity ``feature_stats`` produced
        are identical regardless of this flag.

    Returns
    -------
    ReferenceDistribution

    Never mutates ``cohort_dir`` or its contents; reads no wall clock.
    """
    from segqc.config import bundled_default_config

    from .ingest import ingest_cohort

    if config is None:
        config = bundled_default_config()

    stratifying = size_strata_edges is not None

    cohort = ingest_cohort(
        cohort_dir,
        config=config,
        convention=convention,
        seg_suffix=seg_suffix,
        with_size_proxy=stratifying,
        with_intensity=with_intensity,
        with_morphology=with_morphology,
    )

    return _aggregate_ingested(
        cohort,
        source=source,
        build_date=build_date,
        config=config,
        size_strata_edges=size_strata_edges,
        stratum_labels=stratum_labels,
    )


def _aggregate_ingested(
    cohort_ingest,
    *,
    source: str,
    build_date: str,
    config,
    size_strata_edges,
    stratum_labels,
) -> ReferenceDistribution:
    """Shared tail of the reference builders: stamp deterministic provenance and
    aggregate an already-ingested cohort. Used by both :func:`build_reference`
    (flat directory) and :func:`build_reference_from_cohort` (dataset adapter)."""
    from .aggregate import aggregate_reference

    stratifying = size_strata_edges is not None
    provenance = Provenance(
        source=source,
        config_hash=config_hash(config),
        build_date=build_date,
        size_proxy_name=(SIZE_PROXY_NAME if stratifying else None),
    )
    return aggregate_reference(
        cohort_ingest.records,
        provenance=provenance,
        size_strata_edges=size_strata_edges,
        stratum_labels=stratum_labels,
    )


def build_reference_from_cohort(
    cohort,
    *,
    source: str,
    build_date: str,
    config: "Optional[HeuristicConfig]" = None,
    size_strata_edges: "Optional[Sequence[float]]" = None,
    stratum_labels: "Optional[Sequence[str]]" = None,
    with_intensity: bool = True,
    with_morphology: bool = True,
) -> ReferenceDistribution:
    """Build a reference artifact from a resolved :class:`segqc.datasets.Cohort`
    (Stage 13, item 087) — the dataset-agnostic analogue of
    :func:`build_reference`.

    Ingests the adapter-resolved cohort via
    :func:`segqc.reference.ingest.ingest_dataset_cohort` (each case's own
    ``seg_path`` / ``scan_path`` / ``label_convention``), then shares
    :func:`build_reference`'s deterministic provenance + aggregation tail. Reads
    no wall clock; same output shape as :func:`build_reference`.
    """
    from segqc.config import bundled_default_config

    from .ingest import ingest_dataset_cohort

    if config is None:
        config = bundled_default_config()

    ingested = ingest_dataset_cohort(
        cohort,
        config=config,
        with_size_proxy=size_strata_edges is not None,
        with_intensity=with_intensity,
        with_morphology=with_morphology,
    )
    return _aggregate_ingested(
        ingested,
        source=source,
        build_date=build_date,
        config=config,
        size_strata_edges=size_strata_edges,
        stratum_labels=stratum_labels,
    )


# --------------------------------------------------------------------------- #
# write_artifact / load_artifact
# --------------------------------------------------------------------------- #


def write_artifact(dist: ReferenceDistribution, path: Union[str, "os.PathLike"]) -> Path:
    """Write ``to_json_text(dist)`` to *path* as UTF-8 bytes ending in exactly
    one ``"\\n"`` (``Path.write_bytes``, **not** ``write_text``).

    Creates parent directories as needed. Returns the written path.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = to_json_text(dist)
    out_path.write_bytes(text.encode("utf-8"))
    return out_path


def load_artifact(path: Union[str, "os.PathLike"]) -> ReferenceDistribution:
    """Read *path*, parse JSON, and rebuild the 043 data model.

    Raises
    ------
    ReferenceArtifactError
        If the file does not exist, is not valid JSON, is missing
        ``schema_version``, or carries a ``schema_version`` other than
        :data:`ARTIFACT_SCHEMA_VERSION`. Also raised (wrapping the
        underlying error) if the JSON is otherwise structurally incomplete
        for :func:`~segqc.reference.schema.from_dict`.
    """
    in_path = Path(path)

    try:
        raw = in_path.read_bytes()
    except FileNotFoundError as exc:
        raise ReferenceArtifactError(
            f"Reference artifact file not found: {in_path}"
        ) from exc

    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReferenceArtifactError(
            f"Reference artifact file is not valid JSON: {in_path}\n{exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ReferenceArtifactError(
            f"Reference artifact must be a JSON object (got "
            f"{type(data).__name__!r}): {in_path}"
        )

    version = data.get("schema_version")
    if version is None:
        raise ReferenceArtifactError(
            f"Reference artifact is missing required field 'schema_version': "
            f"{in_path}"
        )
    if version != ARTIFACT_SCHEMA_VERSION:
        raise ReferenceArtifactError(
            f"Unsupported reference artifact schema_version {version!r} in "
            f"{in_path}. This version of segqc supports "
            f"schema_version={ARTIFACT_SCHEMA_VERSION!r}."
        )

    try:
        return from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceArtifactError(
            f"Reference artifact is structurally invalid: {in_path}\n{exc}"
        ) from exc


# --------------------------------------------------------------------------- #
# Bundled default artifact accessors
# --------------------------------------------------------------------------- #


def default_artifact_path() -> Path:
    """Absolute path to the bundled ``reference_default.json`` (via
    ``importlib.resources``), mirroring
    :func:`segqc.config.default_config_path`.
    """
    import importlib.resources as _pkg_resources

    import segqc.reference as _reference_pkg

    ref = _pkg_resources.files(_reference_pkg).joinpath(DEFAULT_ARTIFACT_NAME)
    return Path(str(ref))


def bundled_default_reference() -> ReferenceDistribution:
    """``load_artifact(default_artifact_path())`` -- the default artifact
    loaded into the 043 data model."""
    return load_artifact(default_artifact_path())


# --------------------------------------------------------------------------- #
# Bundled production artifact accessors (item 090)
# --------------------------------------------------------------------------- #


def bundled_production_reference_path() -> Path:
    """Absolute path to the bundled ``reference_verse_v1.json`` (via
    ``importlib.resources``), mirroring :func:`default_artifact_path`.

    This is the **production** reference artifact -- built from real VerSe19
    training-split subjects (``provenance.source == "verse-v1"``) -- that the
    run path attaches by default (item 090), distinct from the synthetic
    Plane-1 baseline :func:`default_artifact_path` still points at.
    """
    import importlib.resources as _pkg_resources

    import segqc.reference as _reference_pkg

    ref = _pkg_resources.files(_reference_pkg).joinpath(PRODUCTION_ARTIFACT_NAME)
    return Path(str(ref))


def bundled_production_reference() -> ReferenceDistribution:
    """``load_artifact(bundled_production_reference_path())`` -- the
    committed real VerSe19 (``verse-v1``) reference artifact loaded into the
    043 data model. This is the shipped **default** production reference
    (item 090); :func:`bundled_default_reference` remains the untouched
    synthetic Plane-1 baseline."""
    return load_artifact(bundled_production_reference_path())


# --------------------------------------------------------------------------- #
# Fixed default cohort
# --------------------------------------------------------------------------- #

#: Fixed, literal recipe for the default synthetic cohort -- deterministic
#: ``build_clean_spine`` parameters only (no RNG, no wall clock). Each entry
#: uses a canonically-contiguous lumbar level span (per ``clean_gt``'s
#: "transitional-vertebra trap" note) so no coverage finding is triggered.
_DEFAULT_COHORT_RECIPE = (
    {
        "subject_id": "default-sub-000",
        "levels": ("L1", "L2", "L3", "L4", "L5"),
        "spacing": (1.0, 1.0, 1.0),
        "curve_amplitude_mm": 6.0,
    },
    {
        "subject_id": "default-sub-001",
        "levels": ("L1", "L2", "L3", "L4"),
        "spacing": (1.0, 1.0, 1.2),
        "curve_amplitude_mm": 4.0,
    },
    {
        "subject_id": "default-sub-002",
        "levels": ("L2", "L3", "L4", "L5"),
        "spacing": (0.9, 0.9, 1.0),
        "curve_amplitude_mm": 8.0,
    },
    {
        "subject_id": "default-sub-003",
        "levels": ("L1", "L2", "L3"),
        "spacing": (1.1, 1.1, 1.1),
        "curve_amplitude_mm": 5.0,
    },
    {
        "subject_id": "default-sub-004",
        "levels": ("L1", "L2", "L3", "L4", "L5"),
        "spacing": (1.0, 1.0, 0.8),
        "curve_amplitude_mm": 3.0,
    },
)


def build_default_cohort(dest: Union[str, "os.PathLike"]) -> Path:
    """Write the FIXED synthetic default cohort as
    ``<subject_id>{DEFAULT_SEG_SUFFIX}`` + ``<subject_id>{DEFAULT_SCAN_SUFFIX}``
    file pairs under *dest*.

    Built from :func:`segqc.synth.clean_gt.build_clean_spine` under the
    pinned per-subject parameters in ``_DEFAULT_COHORT_RECIPE``. Each
    subject's seg is paired with a painted, grid-aligned scan via item 058's
    :func:`segqc.synth.intensity.paint_clean_scan` (fixed ``seed=0``, the
    default HU model), so the default cohort is intensity-bearing (item
    063). No RNG beyond the painter's seeded RNG, no wall clock;
    deterministic across calls/directories -- both the seg and scan bytes
    are byte-reproducible. Returns *dest*.
    """
    import nibabel as nib

    from segqc.synth.clean_gt import build_clean_spine
    from segqc.synth.intensity import paint_clean_scan

    dest_path = Path(dest)
    dest_path.mkdir(parents=True, exist_ok=True)

    for entry in _DEFAULT_COHORT_RECIPE:
        spine = build_clean_spine(
            levels=entry["levels"],
            spacing=entry["spacing"],
            curve_amplitude_mm=entry["curve_amplitude_mm"],
        )
        seg_path = dest_path / f"{entry['subject_id']}{DEFAULT_SEG_SUFFIX}"
        nib.save(spine.seg_img, str(seg_path))

        scan_img = paint_clean_scan(spine.seg_img, seed=0)
        scan_path = dest_path / f"{entry['subject_id']}{DEFAULT_SCAN_SUFFIX}"
        nib.save(scan_img, str(scan_path))

    return dest_path


def build_and_write_default(dest_json: "Optional[Union[str, os.PathLike]]" = None) -> Path:
    """Build the fixed default cohort in a temp dir, run :func:`build_reference`
    over it with :data:`DEFAULT_SOURCE` / :data:`DEFAULT_BUILD_DATE`, and
    :func:`write_artifact` to *dest_json* (default: the committed
    :func:`default_artifact_path`). Returns the written path.
    """
    import tempfile

    if dest_json is None:
        dest_json = default_artifact_path()

    with tempfile.TemporaryDirectory() as tmp_dir:
        build_default_cohort(tmp_dir)
        dist = build_reference(
            tmp_dir, source=DEFAULT_SOURCE, build_date=DEFAULT_BUILD_DATE
        )
        return write_artifact(dist, dest_json)


# --------------------------------------------------------------------------- #
# CLI entry point (module-level regeneration script)
# --------------------------------------------------------------------------- #


def main(argv: "Optional[Sequence[str]]" = None) -> int:
    """``python -m segqc.reference.artifact [--out JSON]`` -- regenerate the
    committed default artifact from the fixed synthetic cohort.

    Returns ``0`` on success.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="segqc.reference.artifact",
        description=(
            "Regenerate the committed default reference-data artifact from "
            "the fixed synthetic cohort."
        ),
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help=(
            "Destination JSON path (default: the committed "
            "reference_default.json)."
        ),
    )
    args = parser.parse_args(argv)

    out_path = build_and_write_default(args.out)
    print(f"Wrote reference artifact to {out_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
