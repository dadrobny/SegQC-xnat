"""Full-pipeline regression harness over the committed corpus (item 041).

Turns one manifest case dict (from :func:`segfacet.synth.corpus.load_manifest`)
into the observable facts the parametrised regression suite
(``tests/test_041_regression_suite.py``) asserts on: it loads the case's
committed seg fixture via the Stage 0 loader (:func:`segfacet.io.load_case`),
runs the real pipeline (:func:`segfacet.pipeline.run_qc`), and exposes pure
predicates that dispatch on the case's ``detection`` discriminator (item 040):

* ``detection == "pipeline"`` -- the failure mode is directly observable by
  the plain pipeline; assert straight against ``run_qc``'s output.
* ``detection == "reconstructed_record"`` -- the failure mode is structurally
  invisible to plain ``run_qc`` (item 040's documented limitation for modes
  1/4/8); assert instead via the same reconstruction technique items 038/039
  used in their own tests, feeding a reconstructed feature record directly to
  the designated rule (:class:`~segfacet.heuristics.mislabel.MislabelRule` /
  :class:`~segfacet.heuristics.overlap.OverlapRule`).

This module is a small, importable verification library -- **not** a pytest
module itself -- so the parametrised suite and any future drift/meta-tests
call exactly the same comparison logic (DRY).

Public surface
--------------
``loaded_seg_image``, ``pipeline_findings``, ``pipeline_verdict_label``,
``reconstructed_findings``, ``designated_findings``, ``designated_rule_fired``,
``offending_labels_match``, ``pipeline_hides_designated_rule``, ``verify_case``,
and the ``RECONSTRUCTIONS`` technique registry. Additively re-exported from
``segfacet.synth``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import nibabel as nib
import numpy as np

from segfacet.config import bundled_default_config
from segfacet.features.centroids import compute_centroid
from segfacet.features.consistency import compute_monotonic_consistency
from segfacet.features.overlap import detect_overlaps
from segfacet.features.spline import fit_centroid_spline
from segfacet.features.spline_offset import compute_spline_offsets
from segfacet.feature_report import overlap_to_dict
from segfacet.heuristics.mislabel import MislabelRule
from segfacet.heuristics.overlap import OverlapRule
from segfacet.io import load_case
from segfacet.pipeline import extract_feature_record, run_qc
from segfacet.synth.clean_gt import build_clean_spine
from segfacet.synth.corpus import CORPUS_DIR

__all__ = [
    "RECONSTRUCTIONS",
    "loaded_seg_image",
    "pipeline_findings",
    "pipeline_verdict_label",
    "reconstructed_findings",
    "designated_findings",
    "designated_rule_fired",
    "offending_labels_match",
    "pipeline_hides_designated_rule",
    "verify_case",
]


# --------------------------------------------------------------------------- #
# Loading -- the Stage 0 path, same as ``segfacet run``
# --------------------------------------------------------------------------- #


def loaded_seg_image(case: dict, corpus_dir: Path = CORPUS_DIR) -> "nib.Nifti1Image":
    """Load *case*'s committed seg fixture via :func:`segfacet.io.load_case` and
    rebuild a fresh ``Nifti1Image`` from its loaded data/affine, suitable for
    ``run_qc`` / feature extraction.

    The explicit ``dtype=`` is mandatory: ``load_case`` returns an ``int64``
    label array and nibabel 5.3.3 hard-errors on
    ``Nifti1Image(int64_array, affine)`` without it (item 040's Decisions
    log).
    """
    corpus_dir = Path(corpus_dir)
    scan_path = corpus_dir / case["scan_fixture"]
    seg_path = corpus_dir / case["seg_fixture"]
    loaded = load_case(scan_path, seg_path)
    seg = loaded.seg
    return nib.Nifti1Image(seg.data, seg.affine, dtype=seg.data.dtype)


# --------------------------------------------------------------------------- #
# Plain-pipeline path
# --------------------------------------------------------------------------- #


def pipeline_findings(case: dict, config=None) -> Tuple:
    """``run_qc(loaded_seg_image(case), config).findings``."""
    config = config or bundled_default_config()
    case_result, _block = run_qc(loaded_seg_image(case), config)
    return case_result.findings


def pipeline_verdict_label(case: dict, config=None) -> str:
    """``run_qc(...).verdict.overall.label`` for a case's committed fixture."""
    config = config or bundled_default_config()
    case_result, _block = run_qc(loaded_seg_image(case), config)
    return case_result.verdict.overall.label


# --------------------------------------------------------------------------- #
# Reconstruction handlers -- verbatim technique from items 038/039's tests
# --------------------------------------------------------------------------- #


def _recon_leave_one_out_offset(case: dict, config) -> List:
    """Mode 1 (``displace``): fit the spline through every OTHER present
    label's centroid, measure the target's spacing-aware offset to that fit,
    overwrite that label's entry in the record's ``per_label_offsets``, and
    feed the record to :class:`MislabelRule`."""
    seg_img = loaded_seg_image(case)
    target = case["perturbation_params"]["target_label"]

    data = np.asanyarray(seg_img.dataobj)
    present = sorted(int(v) for v in np.unique(data) if v != 0)
    others = [label for label in present if label != target]
    other_centroids = [compute_centroid(seg_img, label) for label in others]
    fit = fit_centroid_spline(other_centroids)
    target_centroid = compute_centroid(seg_img, target)
    spacing = tuple(float(z) for z in seg_img.header.get_zooms()[:3])
    offsets = compute_spline_offsets([target_centroid], fit, spacing_mm=spacing)
    loo_offset = offsets[0].offset_mm

    record = extract_feature_record(seg_img, config)
    for entry in record["stage3"]["per_label_offsets"]:
        if entry["label"] == target:
            entry["offset_mm"] = loo_offset

    return MislabelRule().evaluate(record, config)


def _recon_monotonic_true_spatial_order(case: dict, config) -> List:
    """Mode 4 (``relabel_swap``): fit the spline through the perturbed
    centroids ordered by TRUE spatial (axis-0 voxel) position, assess the
    ascending-label centroid sequence's monotonicity against that fit,
    overwrite the record's ``monotonic_consistency`` accordingly, and feed
    the record to :class:`MislabelRule`."""
    seg_img = loaded_seg_image(case)

    data = np.asanyarray(seg_img.dataobj)
    present = sorted(int(v) for v in np.unique(data) if v != 0)
    ascending_centroids = [compute_centroid(seg_img, label) for label in present]
    spatial_centroids = sorted(
        ascending_centroids, key=lambda c: c.centroid_voxel[0]
    )
    fit = fit_centroid_spline(spatial_centroids)
    mono = compute_monotonic_consistency(ascending_centroids, fit)

    record = extract_feature_record(seg_img, config)
    record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"] = [
        list(pair) for pair in mono.non_monotonic_pairs
    ]
    record["stage3"]["monotonic_consistency"]["is_monotonic"] = False

    return MislabelRule().evaluate(record, config)


def _recon_overlap_mask_stack(case: dict, config) -> List:
    """Mode 8 (``force_overlap``): rebuild the clean base spine, build a
    two-channel one-hot stack ``[perturbed == target, clean_base ==
    neighbour]``, run ``detect_overlaps``, wrap as an ``{"overlaps": [...]}``
    record, and feed it to :class:`OverlapRule`."""
    seg_img = loaded_seg_image(case)
    target = case["perturbation_params"]["target_label"]
    neighbour = case["perturbation_params"]["neighbour_label"]

    clean = build_clean_spine(**case["base"])
    clean_data = np.asanyarray(clean.seg_img.dataobj)
    data = np.asanyarray(seg_img.dataobj)

    stack = np.stack([data == target, clean_data == neighbour])
    pairs = detect_overlaps(stack, np.array([target, neighbour]))
    record = {"overlaps": [overlap_to_dict(pair) for pair in pairs]}

    return OverlapRule().evaluate(record, config)


RECONSTRUCTIONS: Dict[str, Callable] = {
    "leave_one_out_offset": _recon_leave_one_out_offset,
    "monotonic_true_spatial_order": _recon_monotonic_true_spatial_order,
    "overlap_mask_stack": _recon_overlap_mask_stack,
}


def reconstructed_findings(case: dict, config=None) -> List:
    """Dispatch on ``case["reconstruction"]`` to the matching technique in
    :data:`RECONSTRUCTIONS`, feed the reconstructed record to the designated
    rule, and return its findings.

    Raises
    ------
    ValueError
        If ``case["reconstruction"]`` names no known technique -- a future
        reconstructed case without a handler must fail loudly, never be
        silently skipped (AC12).
    """
    config = config or bundled_default_config()
    technique = case["reconstruction"]
    handler = RECONSTRUCTIONS.get(technique)
    if handler is None:
        raise ValueError(
            f"reconstructed_findings: unrecognised reconstruction technique "
            f"{technique!r} for case {case.get('case_id')!r}; known "
            f"techniques are {sorted(RECONSTRUCTIONS)}."
        )
    return handler(case, config)


# --------------------------------------------------------------------------- #
# Dispatch on detection + shared predicates
# --------------------------------------------------------------------------- #


def designated_findings(case: dict, config=None) -> List:
    """Findings whose ``rule_id`` is in ``case["expected_rule_ids"]``, taken
    from the ``run_qc`` path for ``"pipeline"`` cases and from
    :func:`reconstructed_findings` for ``"reconstructed_record"`` cases."""
    config = config or bundled_default_config()
    expected_rule_ids = set(case["expected_rule_ids"])

    if case["detection"] == "pipeline":
        findings = pipeline_findings(case, config)
    elif case["detection"] == "reconstructed_record":
        findings = reconstructed_findings(case, config)
    else:
        raise ValueError(
            f"designated_findings: unrecognised detection {case['detection']!r} "
            f"for case {case.get('case_id')!r}."
        )

    return [f for f in findings if f.rule_id in expected_rule_ids]


def designated_rule_fired(case: dict, config=None) -> bool:
    """``True`` iff :func:`designated_findings` is non-empty."""
    return len(designated_findings(case, config)) > 0


def offending_labels_match(case: dict, config=None) -> bool:
    """``True`` iff the union of :func:`designated_findings`' ``labels``
    equals ``set(case["expected_labels"])``."""
    findings = designated_findings(case, config)
    union: set = set()
    for f in findings:
        union |= set(f.labels)
    return union == set(case["expected_labels"])


def pipeline_hides_designated_rule(case: dict, config=None) -> bool:
    """``True`` iff plain ``run_qc`` emits NO finding whose ``rule_id`` is in
    ``expected_rule_ids`` (the documented limitation for
    ``reconstructed_record`` cases)."""
    config = config or bundled_default_config()
    expected_rule_ids = set(case["expected_rule_ids"])
    findings = pipeline_findings(case, config)
    return not any(f.rule_id in expected_rule_ids for f in findings)


def verify_case(case: dict, config=None) -> bool:
    """The whole per-case check, dispatched on ``detection``:

    * ``pipeline``: verdict label matches, and (clean case -> no findings) or
      (non-clean case -> designated rule fires and offending labels match).
    * ``reconstructed_record``: plain pipeline hides the designated rule,
      the reconstruction fires it, and the offending labels match.
    """
    config = config or bundled_default_config()

    if case["detection"] == "pipeline":
        if pipeline_verdict_label(case, config) != case["expected_verdict"]:
            return False
        if case.get("failure_mode") == 0:
            return pipeline_findings(case, config) == ()
        return designated_rule_fired(case, config) and offending_labels_match(
            case, config
        )

    if case["detection"] == "reconstructed_record":
        return (
            pipeline_hides_designated_rule(case, config)
            and designated_rule_fired(case, config)
            and offending_labels_match(case, config)
        )

    raise ValueError(
        f"verify_case: unrecognised detection {case['detection']!r} for case "
        f"{case.get('case_id')!r}."
    )
