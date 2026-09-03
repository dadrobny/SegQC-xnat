"""Intensity-bearing synthetic scan fixtures (item 058).

Extends the Stage-5 synthetic generator (:mod:`segfacet.synth.clean_gt`,
:mod:`segfacet.synth.corpus`) with the tool's first use of scan **voxel
intensities**: a bone-plausible Hounsfield-unit (HU) painter co-registered
with the clean-GT label map, an implausible-intensity variant generator, and
a new, **parallel** committed corpus (``tests/corpus/intensity/``) that never
touches the existing Stage-5 geometric corpus (``tests/corpus/``, items
040-042).

Two pure painters (no disk I/O):

* :func:`paint_clean_scan` -- a bone-plausible HU scan: a cortical rim
  (brighter) enclosing a cancellous interior (moderate HU) per vertebra, over
  a soft-tissue background, with seeded per-voxel Gaussian variation. Same
  shape/affine as the input label map; ``int16``.
* :func:`paint_implausible_variant` -- overwrites a single target label's
  voxels in a clean scan with an implausible fill (``metal`` /
  ``soft_tissue`` / ``degenerate_uniform``); the label map and every other
  voxel are untouched.

And the committed-corpus surface (mirrors :mod:`segfacet.synth.corpus`, item
040): :func:`build_intensity_corpus`, :func:`write_intensity_corpus`,
:func:`load_intensity_manifest`, and a ``python -m segfacet.synth.intensity
[--out DIR]`` CLI entry point (:func:`main`).

The HU constants pinned below (:data:`DEFAULT_HU_MODEL`,
:data:`IMPLAUSIBLE_FILLS`) are defensible **representative CT values** used
to *paint* these fixtures -- they are generator ground truth, not QC
judgement thresholds (item 062 sets those independently; see the item spec's
Assumptions).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import nibabel as nib
import numpy as np
from scipy.ndimage import binary_erosion

from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.perturbation import seeded_rng

__all__ = [
    "HUModel",
    "DEFAULT_HU_MODEL",
    "ImplausibleFill",
    "IMPLAUSIBLE_FILLS",
    "BONE_PLAUSIBLE_BAND",
    "paint_clean_scan",
    "paint_implausible_variant",
    "INTENSITY_CORPUS_DIR",
    "INTENSITY_MANIFEST_PATH",
    "INTENSITY_FIXTURES_DIRNAME",
    "INTENSITY_MANIFEST_VERSION",
    "INTENSITY_DETECTION",
    "IntensityCase",
    "CASE_RECIPE",
    "build_intensity_corpus",
    "write_intensity_corpus",
    "load_intensity_manifest",
    "main",
]

# --------------------------------------------------------------------------- #
# HU model & implausible fills (see item 058 spec's Assumptions for the
# rationale behind each pinned constant)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HUModel:
    """A per-tissue Gaussian HU model used to paint the clean scan."""

    background_mean: float
    background_std: float
    cancellous_mean: float
    cancellous_std: float
    cortical_mean: float
    cortical_std: float
    dtype: str = "int16"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "background_mean": self.background_mean,
            "background_std": self.background_std,
            "cancellous_mean": self.cancellous_mean,
            "cancellous_std": self.cancellous_std,
            "cortical_mean": self.cortical_mean,
            "cortical_std": self.cortical_std,
            "dtype": self.dtype,
        }


#: Pinned defaults -- soft-tissue background, trabecular interior, cortical
#: rim (brighter). Representative CT values, not QC thresholds.
DEFAULT_HU_MODEL = HUModel(
    background_mean=40,
    background_std=10,
    cancellous_mean=200,
    cancellous_std=40,
    cortical_mean=600,
    cortical_std=120,
    dtype="int16",
)

#: The documented bone-plausible per-label median HU band (generator ground
#: truth -- see AC2/AC17).
BONE_PLAUSIBLE_BAND = (100, 1500)


@dataclass(frozen=True)
class ImplausibleFill:
    """A named implausible HU fill. ``std == 0.0`` means a single constant
    value (degenerate-uniform)."""

    name: str
    mean: float
    std: float

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "mean": self.mean, "std": self.std}


#: The three canonical implausible fills (item 058 spec's Assumptions).
IMPLAUSIBLE_FILLS: Dict[str, ImplausibleFill] = {
    "metal": ImplausibleFill(name="metal", mean=3000, std=100),
    "soft_tissue": ImplausibleFill(name="soft_tissue", mean=40, std=10),
    "degenerate_uniform": ImplausibleFill(name="degenerate_uniform", mean=0, std=0),
}

_INT16_MIN, _INT16_MAX = -32768, 32767


def _clip_round_int16(data: np.ndarray) -> np.ndarray:
    """Round to nearest integer, clip to the int16 range, cast to int16."""
    rounded = np.rint(data)
    clipped = np.clip(rounded, _INT16_MIN, _INT16_MAX)
    return clipped.astype(np.int16)


# --------------------------------------------------------------------------- #
# paint_clean_scan
# --------------------------------------------------------------------------- #


def paint_clean_scan(
    seg_img: nib.Nifti1Image, *, seed: int = 0, model: HUModel = DEFAULT_HU_MODEL
) -> nib.Nifti1Image:
    """Paint a bone-plausible HU scan onto ``seg_img``'s labels.

    Each present non-zero label gets a cortical rim (mask minus its
    one-voxel :func:`scipy.ndimage.binary_erosion`, brighter) enclosing a
    cancellous interior (the eroded mask, moderate HU); background voxels get
    soft-tissue-low HU. All variation is seeded Gaussian noise, drawn solely
    from :func:`~segfacet.synth.perturbation.seeded_rng` (never the global
    NumPy RNG), in a fixed (background, then ascending-label) order so the
    result is deterministic for a fixed ``(seed, model)``.

    Same shape/affine as ``seg_img``; array dtype ``int16``. Does not mutate
    ``seg_img``.
    """
    seg_data = np.asanyarray(seg_img.dataobj)
    shape = seg_data.shape
    rng = seeded_rng(seed)

    scan = rng.normal(model.background_mean, model.background_std, size=shape)

    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    for label in labels:
        mask = seg_data == label
        interior = binary_erosion(mask)
        rim = mask & ~interior

        if interior.any():
            scan[interior] = rng.normal(
                model.cancellous_mean, model.cancellous_std, size=int(interior.sum())
            )
            if rim.any():
                scan[rim] = rng.normal(
                    model.cortical_mean, model.cortical_std, size=int(rim.sum())
                )
        else:
            # Degenerate/thin body: no non-empty interior survives a
            # one-voxel erosion -- fall back to treating the whole mask as
            # cancellous (documented fallback; see item 058 spec's
            # Assumptions). Does not occur for the default clean spine.
            scan[mask] = rng.normal(
                model.cancellous_mean, model.cancellous_std, size=int(mask.sum())
            )

    data = _clip_round_int16(scan)
    affine = np.array(seg_img.affine)
    return nib.Nifti1Image(data, affine)


# --------------------------------------------------------------------------- #
# paint_implausible_variant
# --------------------------------------------------------------------------- #


def paint_implausible_variant(
    clean_scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
    *,
    target_label: int,
    fill: ImplausibleFill,
    seed: int = 0,
) -> nib.Nifti1Image:
    """Return a scan equal to ``clean_scan_img`` except that
    ``target_label``'s voxels are overwritten with ``fill`` HU (seeded).

    The label map (``seg_img``) is never touched, and every voxel outside
    ``target_label``'s mask is byte-identical to ``clean_scan_img``. If
    ``target_label`` is absent from ``seg_img``, this is a no-op. Same
    shape/affine as ``seg_img``; deterministic for a fixed
    ``(target_label, fill, seed)``.
    """
    clean_data = np.array(np.asanyarray(clean_scan_img.dataobj), copy=True).astype(
        np.float64
    )
    seg_data = np.asanyarray(seg_img.dataobj)
    mask = seg_data == target_label

    if mask.any():
        n = int(mask.sum())
        if fill.std == 0.0:
            values = np.full(n, float(fill.mean))
        else:
            rng = seeded_rng(seed)
            values = rng.normal(fill.mean, fill.std, size=n)
        clean_data[mask] = values

    data = _clip_round_int16(clean_data)
    affine = np.array(seg_img.affine)
    return nib.Nifti1Image(data, affine)


# --------------------------------------------------------------------------- #
# Module constants -- committed intensity corpus
# --------------------------------------------------------------------------- #

#: The committed intensity corpus directory: <repo>/tests/corpus/intensity.
INTENSITY_CORPUS_DIR: Path = (
    Path(__file__).resolve().parents[3] / "tests" / "corpus" / "intensity"
)

#: The committed intensity manifest file.
INTENSITY_MANIFEST_PATH: Path = INTENSITY_CORPUS_DIR / "manifest.json"

#: Name of the fixtures subdirectory under an intensity corpus directory.
INTENSITY_FIXTURES_DIRNAME: str = "fixtures"

#: Intensity manifest schema version (bump on any incompatible schema change).
INTENSITY_MANIFEST_VERSION: int = 1

#: Name of the shared label-map fixture (byte-identical across every case --
#: only intensities vary).
_SEG_FIXTURE_NAME: str = "clean_spine_seg.nii.gz"

#: The default clean-spine build parameters used by every case's base.
_DEFAULT_BASE_PARAMS: Dict[str, Any] = {
    "levels": ["L1", "L2", "L3", "L4", "L5"],
    "spacing": [1.0, 1.0, 1.0],
    "curve_amplitude_mm": 6.0,
}

#: Target label for every implausible variant (L3, the middle body --
#: matches the Stage-5 corpus's mode-case convention).
_TARGET_LABEL: int = 22


# --------------------------------------------------------------------------- #
# The recipe -- the single declarative source of the intensity corpus cases
# --------------------------------------------------------------------------- #


#: The one legal value of an intensity manifest case's ``detection`` field
#: (item 146): the intensity corpus is driven end-to-end through
#: ``segfacet.synth.regression.intensity_pipeline_findings``. It mirrors the
#: geometric manifest's ``detection`` discriminator, and an unrecognised value
#: must raise rather than be silently skipped.
INTENSITY_DETECTION: str = "intensity_pipeline"

#: The clean control's failure-mode number, matching the geometric manifest's
#: ``clean_control`` convention (``segfacet.synth.perturbation.CLEAN_CONTROL_MODE``).
_CLEAN_MODE_ID: int = 0
_CLEAN_MODE_NAME: str = "clean control (no failure)"

#: The ninth failure mode (item 146), authored in
#: ``segfacet.failure_modes.SPECIFICATION[9]``. Written here as a literal, not
#: imported: this generator is the corpus's declared ground truth and must not
#: acquire a dependency on the specification module it feeds. AC23 pins the two
#: against each other.
_IMPLAUSIBLE_TISSUE_MODE_ID: int = 9
_IMPLAUSIBLE_TISSUE_MODE_NAME: str = "Implausible tissue under a label"


@dataclass(frozen=True)
class _RecipeEntry:
    case_id: str
    variant: str
    plausible: bool
    target_label: Optional[int]
    fill_name: Optional[str]
    #: Declared ground truth, exactly as ``expected_label_hu_bands`` is: which
    #: catalogued failure mode this case exhibits, its name, and the full set
    #: of ``rule_id``s the intensity pipeline raises on it -- measured through
    #: ``segfacet.synth.regression.intensity_pipeline_findings`` and recorded
    #: literally (item 146's Decisions log carries the measurement transcript).
    failure_mode: int
    failure_mode_name: str
    expected_firing: Tuple[str, ...]
    seed: int = 0
    base: Dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_BASE_PARAMS))


#: One clean case + >=2 implausible cases (AC13), a plain list so more
#: variants/targets can be appended later without a schema change.
CASE_RECIPE: List[_RecipeEntry] = [
    _RecipeEntry(
        case_id="clean_hu",
        variant="clean",
        plausible=True,
        target_label=None,
        fill_name=None,
        failure_mode=_CLEAN_MODE_ID,
        failure_mode_name=_CLEAN_MODE_NAME,
        expected_firing=(),
    ),
    _RecipeEntry(
        case_id="implausible_metal",
        variant="metal",
        plausible=False,
        target_label=_TARGET_LABEL,
        fill_name="metal",
        failure_mode=_IMPLAUSIBLE_TISSUE_MODE_ID,
        failure_mode_name=_IMPLAUSIBLE_TISSUE_MODE_NAME,
        expected_firing=("intensity",),
    ),
    _RecipeEntry(
        case_id="implausible_soft_tissue",
        variant="soft_tissue",
        plausible=False,
        target_label=_TARGET_LABEL,
        fill_name="soft_tissue",
        failure_mode=_IMPLAUSIBLE_TISSUE_MODE_ID,
        failure_mode_name=_IMPLAUSIBLE_TISSUE_MODE_NAME,
        expected_firing=("intensity",),
    ),
    _RecipeEntry(
        case_id="degenerate_uniform",
        variant="degenerate_uniform",
        plausible=False,
        target_label=_TARGET_LABEL,
        fill_name="degenerate_uniform",
        failure_mode=_IMPLAUSIBLE_TISSUE_MODE_ID,
        failure_mode_name=_IMPLAUSIBLE_TISSUE_MODE_NAME,
        expected_firing=("intensity",),
    ),
]


# --------------------------------------------------------------------------- #
# IntensityCase -- in-memory representation of a built case
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class IntensityCase:
    """One fully-built intensity-corpus case: metadata + images. No disk I/O
    has happened yet."""

    case_id: str
    variant: str
    plausible: bool
    target_label: Optional[int]
    fill: Optional[ImplausibleFill]
    seed: int
    base: Dict[str, Any]
    seg_img: nib.Nifti1Image
    scan_img: nib.Nifti1Image
    expected_label_hu_bands: Dict[str, List[float]]
    failure_mode: int = _CLEAN_MODE_ID
    failure_mode_name: str = _CLEAN_MODE_NAME
    expected_firing: Tuple[str, ...] = ()


def _clean_case_bands(seg_data: np.ndarray) -> Dict[str, List[float]]:
    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)
    return {str(label): [BONE_PLAUSIBLE_BAND[0], BONE_PLAUSIBLE_BAND[1]] for label in labels}


def _implausible_case_band(fill_name: str) -> List[float]:
    if fill_name == "metal":
        return [2500, _INT16_MAX]
    if fill_name == "soft_tissue":
        return [-200, 100]
    if fill_name == "degenerate_uniform":
        return [0, 0]
    raise KeyError(f"Unknown fill name {fill_name!r} for expected_label_hu_bands.")


# --------------------------------------------------------------------------- #
# build_intensity_corpus
# --------------------------------------------------------------------------- #


def build_intensity_corpus() -> List[IntensityCase]:
    """Build every intensity-corpus case in memory (no disk I/O).

    Builds the shared clean spine once, paints the clean scan, derives each
    implausible variant from it, and attaches the model-derived
    ``expected_label_hu_bands`` (generator ground truth -- copied verbatim
    from the painter/model so the manifest can never drift, AC17).
    """
    clean = build_clean_spine(**_DEFAULT_BASE_PARAMS)
    seg_img = clean.seg_img
    seg_data = np.asanyarray(seg_img.dataobj)

    clean_scan_img = paint_clean_scan(seg_img, seed=0)
    clean_bands = _clean_case_bands(seg_data)

    cases: List[IntensityCase] = []
    for entry in CASE_RECIPE:
        if entry.plausible:
            cases.append(
                IntensityCase(
                    case_id=entry.case_id,
                    variant=entry.variant,
                    plausible=True,
                    target_label=None,
                    fill=None,
                    seed=entry.seed,
                    base=dict(entry.base),
                    seg_img=seg_img,
                    scan_img=clean_scan_img,
                    expected_label_hu_bands=clean_bands,
                    failure_mode=entry.failure_mode,
                    failure_mode_name=entry.failure_mode_name,
                    expected_firing=tuple(entry.expected_firing),
                )
            )
        else:
            fill = IMPLAUSIBLE_FILLS[entry.fill_name]
            variant_img = paint_implausible_variant(
                clean_scan_img,
                seg_img,
                target_label=entry.target_label,
                fill=fill,
                seed=entry.seed,
            )
            band = _implausible_case_band(entry.fill_name)
            cases.append(
                IntensityCase(
                    case_id=entry.case_id,
                    variant=entry.variant,
                    plausible=False,
                    target_label=entry.target_label,
                    fill=fill,
                    seed=entry.seed,
                    base=dict(entry.base),
                    seg_img=seg_img,
                    scan_img=variant_img,
                    expected_label_hu_bands={str(entry.target_label): band},
                    failure_mode=entry.failure_mode,
                    failure_mode_name=entry.failure_mode_name,
                    expected_firing=tuple(entry.expected_firing),
                )
            )
    return cases


# --------------------------------------------------------------------------- #
# write_intensity_corpus
# --------------------------------------------------------------------------- #


def _save_deterministic(img: nib.Nifti1Image, path: Path) -> None:
    """Save *img* to *path* deterministically -- see
    ``segfacet.synth.corpus._save_deterministic`` (nibabel 5.3.3's gzip writer
    already yields byte-identical output across successive calls for
    identical content)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(path))


def write_intensity_corpus(dest: Path) -> Path:
    """Materialise the intensity corpus under *dest*.

    Writes one shared ``fixtures/clean_spine_seg.nii.gz`` (the label map is
    byte-identical across every case -- only intensities vary) and one
    ``fixtures/<case_id>_scan.nii.gz`` per case, plus ``dest/manifest.json``
    (fixture paths relative to *dest*). Deterministic: two successive calls
    (even into different directories) produce byte-identical output for
    identical content.

    Returns
    -------
    Path
        The written manifest path (``dest/manifest.json``).
    """
    dest = Path(dest)
    fixtures_dir = dest / INTENSITY_FIXTURES_DIRNAME
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    cases = build_intensity_corpus()

    seg_fixture_path = fixtures_dir / _SEG_FIXTURE_NAME
    _save_deterministic(cases[0].seg_img, seg_fixture_path)

    manifest_cases: List[Dict[str, Any]] = []
    for case in cases:
        scan_fixture_name = f"{case.case_id}_scan.nii.gz"
        scan_path = fixtures_dir / scan_fixture_name
        _save_deterministic(case.scan_img, scan_path)

        manifest_case = {
            "case_id": case.case_id,
            "variant": case.variant,
            "plausible": case.plausible,
            "target_label": case.target_label,
            "fill": case.fill.to_dict() if case.fill is not None else None,
            "seed": case.seed,
            "base": case.base,
            "scan_fixture": f"{INTENSITY_FIXTURES_DIRNAME}/{scan_fixture_name}",
            "seg_fixture": f"{INTENSITY_FIXTURES_DIRNAME}/{_SEG_FIXTURE_NAME}",
            "expected_label_hu_bands": case.expected_label_hu_bands,
            "failure_mode": case.failure_mode,
            "failure_mode_name": case.failure_mode_name,
            "detection": INTENSITY_DETECTION,
            "expected_firing": sorted(case.expected_firing),
        }
        manifest_cases.append(manifest_case)

    manifest = {
        "manifest_version": INTENSITY_MANIFEST_VERSION,
        "generator": "segfacet.synth.intensity",
        "hu_model": DEFAULT_HU_MODEL.to_dict(),
        "cases": manifest_cases,
    }

    manifest_path = dest / "manifest.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    # Write raw bytes (not Path.write_text) so line endings are exactly "\n"
    # regardless of platform/Python version -- required for byte-identical
    # regeneration (AC19); Path.write_text's newline= kwarg needs Python
    # >= 3.10 (this project targets 3.9+).
    manifest_path.write_bytes(manifest_text.encode("utf-8"))

    return manifest_path


# --------------------------------------------------------------------------- #
# load_intensity_manifest
# --------------------------------------------------------------------------- #


def load_intensity_manifest(path: Path = INTENSITY_MANIFEST_PATH) -> dict:
    """Parse and return the intensity manifest dict at *path* (default: the
    committed ``tests/corpus/intensity/manifest.json``)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m segfacet.synth.intensity [--out DIR]`` -- regenerate the
    committed intensity corpus.

    Regenerates the fixtures + manifest under ``--out`` (default:
    :data:`INTENSITY_CORPUS_DIR`). Returns ``0`` on success.
    """
    parser = argparse.ArgumentParser(
        prog="segfacet.synth.intensity",
        description="Regenerate the committed intensity-bearing synthetic fixture corpus.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(INTENSITY_CORPUS_DIR),
        help="Destination directory (default: the committed tests/corpus/intensity).",
    )
    args = parser.parse_args(argv)

    manifest_path = write_intensity_corpus(Path(args.out))
    print(f"Wrote intensity corpus manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
