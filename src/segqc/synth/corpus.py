"""Committed synthetic fixture corpus spanning every §6 failure mode plus the
clean-GT positive control, and its versioned manifest (item 040).

Materialises the **nine canonical cases** (one per §6 failure mode 1-8, plus
the mode-0 clean control) documented in the item 040 spec's case table, using
the merged Stage 5 generators (items 036-039): :func:`build_clean_spine`
(item 036) as the shared base, and the registered operators from item 037
(``fragment``), item 038 (``remove_level``, ``crop_at_border``,
``force_overlap``), and item 039 (``displace``, ``relabel_swap``,
``sequence_break``).

Two public surfaces:

* An **in-memory API** -- :func:`build_corpus` (the recipe -> per-case
  ``CorpusCase`` objects, no disk I/O) and :func:`write_corpus` (materialise
  fixtures + manifest to disk, deterministically).
* A **CLI entry point** -- ``python -m segqc.synth.corpus [--out DIR]``
  (:func:`main`), regenerating the committed corpus under
  ``tests/corpus/`` by default.

Three of the nine cases (modes 1, 4, 8 -- ``displace``, ``relabel_swap``,
``force_overlap``) are documented by items 038/039 as **structurally
invisible** to the plain ``run_qc`` pipeline (a single-integer label map
cannot encode an overlap; the interpolating/ascending-label spline refit
absorbs the displacement/swap). This module faithfully represents that fact:
each such case's manifest entry carries ``detection == "reconstructed_record"``
and a ``reconstruction`` technique key, rather than pretending ``run_qc``
would catch it. See the item 040 spec's Assumptions for the full rationale.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import nibabel as nib
import numpy as np

from segqc.synth.clean_gt import build_clean_spine
from segqc.synth.perturbation import Expectation, get_perturbation

# Import the operator-family modules so every operator self-registers before
# get_perturbation() is used below. Imported from submodules (not the
# segqc.synth package) to avoid a circular import, since segqc/synth/__init__
# additively re-exports this module too.
import segqc.synth.component_shape  # noqa: F401
import segqc.synth.coverage_border_overlap  # noqa: F401
import segqc.synth.identity_ordering_alignment  # noqa: F401

__all__ = [
    "CORPUS_DIR",
    "MANIFEST_PATH",
    "FIXTURES_DIRNAME",
    "MANIFEST_VERSION",
    "CorpusCase",
    "CASE_RECIPE",
    "build_corpus",
    "write_corpus",
    "load_manifest",
    "main",
]

# --------------------------------------------------------------------------- #
# Module constants
# --------------------------------------------------------------------------- #

#: The committed corpus directory: <repo>/tests/corpus.
CORPUS_DIR: Path = Path(__file__).resolve().parents[3] / "tests" / "corpus"

#: The committed manifest file.
MANIFEST_PATH: Path = CORPUS_DIR / "manifest.json"

#: Name of the fixtures subdirectory under a corpus directory.
FIXTURES_DIRNAME: str = "fixtures"

#: Manifest schema version (bump on any incompatible schema change).
MANIFEST_VERSION: int = 1

#: Name of the shared base-scan fixture (every case derives from the same
#: default clean spine and operators preserve shape/affine -- see the item
#: spec's "all nine canonical cases share one base scan" Assumption).
_BASE_SCAN_FIXTURE_NAME: str = "base_scan.nii.gz"

#: The default clean-spine build parameters used by every case's base.
_DEFAULT_BASE_PARAMS: Dict[str, Any] = {
    "levels": ["L1", "L2", "L3", "L4", "L5"],
    "spacing": [1.0, 1.0, 1.0],
    "curve_amplitude_mm": 6.0,
}


# --------------------------------------------------------------------------- #
# The recipe -- the single declarative source of the nine canonical cases
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _RecipeEntry:
    """One row of the case table: which operator, params, seed, and base."""

    case_id: str
    perturbation: str
    perturbation_params: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    base: Dict[str, Any] = field(default_factory=lambda: dict(_DEFAULT_BASE_PARAMS))
    detection: str = "pipeline"
    reconstruction: Optional[str] = None


#: The nine canonical cases (item 040 spec's case table), in table order.
CASE_RECIPE: List[_RecipeEntry] = [
    _RecipeEntry(
        case_id="clean_control",
        perturbation="identity",
        perturbation_params={},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode1_displace",
        perturbation="displace",
        perturbation_params={"target_label": 22},
        detection="reconstructed_record",
        reconstruction="leave_one_out_offset",
    ),
    _RecipeEntry(
        case_id="mode2_fragment",
        perturbation="fragment",
        perturbation_params={"target_label": 22},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode3_inject_islands",
        perturbation="inject_islands",
        perturbation_params={"target_label": 22},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode4_relabel_swap",
        perturbation="relabel_swap",
        perturbation_params={"target_label": 21, "neighbour_label": 22},
        detection="reconstructed_record",
        reconstruction="monotonic_true_spatial_order",
    ),
    _RecipeEntry(
        case_id="mode5_remove_level",
        perturbation="remove_level",
        perturbation_params={"target_label": 22},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode6_crop_at_border",
        perturbation="crop_at_border",
        perturbation_params={"target_label": 22, "face": "anterior"},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode7_sequence_break",
        perturbation="sequence_break",
        perturbation_params={},
        detection="pipeline",
    ),
    _RecipeEntry(
        case_id="mode8_force_overlap",
        perturbation="force_overlap",
        perturbation_params={"target_label": 20, "neighbour_label": 21},
        detection="reconstructed_record",
        reconstruction="overlap_mask_stack",
    ),
]


# --------------------------------------------------------------------------- #
# CorpusCase -- in-memory representation of a built case
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CorpusCase:
    """One fully-built corpus case: metadata + images + the operator's
    Expectation. No disk I/O has happened yet."""

    case_id: str
    perturbation: str
    perturbation_params: Dict[str, Any]
    seed: int
    base: Dict[str, Any]
    detection: str
    reconstruction: Optional[str]
    scan_img: nib.Nifti1Image
    seg_img: nib.Nifti1Image
    expectation: Expectation


# --------------------------------------------------------------------------- #
# build_corpus
# --------------------------------------------------------------------------- #


def build_corpus() -> List[CorpusCase]:
    """Build every canonical case in memory (no disk I/O).

    For each recipe entry: build the base clean spine, instantiate the
    registered operator with its explicit params, apply it (seeded) to the
    base segmentation, and assemble a :class:`CorpusCase` carrying the base
    scan, the perturbed segmentation, and the operator's ``Expectation`` --
    the single source of truth for the manifest's expected_* fields (AC17).
    """
    cases: List[CorpusCase] = []
    for entry in CASE_RECIPE:
        clean = build_clean_spine(**entry.base)
        operator_cls = get_perturbation(entry.perturbation)
        operator = operator_cls(**entry.perturbation_params)
        result = operator.apply(clean.seg_img, entry.seed)

        cases.append(
            CorpusCase(
                case_id=entry.case_id,
                perturbation=entry.perturbation,
                perturbation_params=dict(entry.perturbation_params),
                seed=entry.seed,
                base=dict(entry.base),
                detection=entry.detection,
                reconstruction=entry.reconstruction,
                scan_img=clean.scan_img,
                seg_img=result.labelmap,
                expectation=result.expectation,
            )
        )
    return cases


# --------------------------------------------------------------------------- #
# write_corpus
# --------------------------------------------------------------------------- #


def _save_deterministic(img: nib.Nifti1Image, path: Path) -> None:
    """Save *img* to *path* deterministically (byte-stable across runs).

    nibabel (verified: 5.3.3) writes gzip via a deterministic gzip wrapper
    (``mtime=0``), so plain ``nib.save`` already yields byte-identical output
    across successive calls for identical content -- see the item spec's
    Assumptions. Header fields that could vary by wall-clock time (e.g.
    ``regular``) are not touched by nibabel's writer, so no extra
    normalisation is required here.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(path))


def write_corpus(dest: Path) -> Path:
    """Materialise the corpus under *dest*.

    Writes one shared ``fixtures/base_scan.nii.gz`` (every canonical case
    derives from the same default clean spine; asserts the base scans are
    array-equal across cases before deduping) and one
    ``fixtures/<case_id>_seg.nii.gz`` per case, plus ``dest/manifest.json``
    (fixture paths relative to *dest*). Deterministic: two successive calls
    (even into different directories) produce byte-identical output for
    identical content.

    Returns
    -------
    Path
        The written manifest path (``dest/manifest.json``).
    """
    dest = Path(dest)
    fixtures_dir = dest / FIXTURES_DIRNAME
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    cases = build_corpus()

    # Dedup contract: every case shares the same base scan (perturbations
    # preserve shape/affine). Assert this before writing just one copy.
    base_data = np.asanyarray(cases[0].scan_img.dataobj)
    base_affine = np.asarray(cases[0].scan_img.affine)
    for case in cases[1:]:
        if not np.array_equal(np.asanyarray(case.scan_img.dataobj), base_data) or not np.array_equal(
            np.asarray(case.scan_img.affine), base_affine
        ):
            raise AssertionError(
                f"write_corpus: case {case.case_id!r}'s base scan diverges "
                "from the shared base scan -- the one-base-scan dedup "
                "contract (item 040 Assumptions) is violated."
            )

    base_scan_path = fixtures_dir / _BASE_SCAN_FIXTURE_NAME
    _save_deterministic(cases[0].scan_img, base_scan_path)

    manifest_cases: List[Dict[str, Any]] = []
    for case in cases:
        seg_fixture_name = f"{case.case_id}_seg.nii.gz"
        seg_path = fixtures_dir / seg_fixture_name
        _save_deterministic(case.seg_img, seg_path)

        expectation_dict = case.expectation.to_dict()

        manifest_case = {
            "case_id": case.case_id,
            "failure_mode": expectation_dict["failure_mode"],
            "failure_mode_name": expectation_dict["failure_mode_name"],
            "detection": case.detection,
            "reconstruction": case.reconstruction,
            "perturbation": case.perturbation,
            "perturbation_params": case.perturbation_params,
            "seed": case.seed,
            "base": case.base,
            "scan_fixture": f"{FIXTURES_DIRNAME}/{_BASE_SCAN_FIXTURE_NAME}",
            "seg_fixture": f"{FIXTURES_DIRNAME}/{seg_fixture_name}",
            "expected_rule_ids": expectation_dict["expected_rule_ids"],
            "expected_labels": expectation_dict["expected_labels"],
            "expected_verdict": expectation_dict["expected_verdict"],
            "detail": expectation_dict["detail"],
        }
        manifest_cases.append(manifest_case)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generator": "segqc.synth.corpus",
        "cases": manifest_cases,
    }

    manifest_path = dest / "manifest.json"
    manifest_text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    # Write raw bytes (rather than Path.write_text) so line endings are
    # exactly "\n" regardless of platform/Python version -- required for
    # byte-identical regeneration (AC16) on Windows, and Path.write_text's
    # newline= kwarg is only available on Python >= 3.10 (this project
    # targets 3.9+).
    manifest_path.write_bytes(manifest_text.encode("utf-8"))

    return manifest_path


# --------------------------------------------------------------------------- #
# load_manifest
# --------------------------------------------------------------------------- #


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    """Parse and return the manifest dict at *path* (default: the committed
    ``tests/corpus/manifest.json``)."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m segqc.synth.corpus [--out DIR]`` -- regenerate the corpus.

    Regenerates the fixtures + manifest under ``--out`` (default:
    :data:`CORPUS_DIR`). Returns ``0`` on success.
    """
    parser = argparse.ArgumentParser(
        prog="segqc.synth.corpus",
        description="Regenerate the committed synthetic fixture corpus.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=str(CORPUS_DIR),
        help="Destination directory (default: the committed tests/corpus).",
    )
    args = parser.parse_args(argv)

    manifest_path = write_corpus(Path(args.out))
    print(f"Wrote corpus manifest to {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
