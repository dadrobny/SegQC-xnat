"""Identity, ordering & alignment perturbations: displace, relabel_swap,
sequence_break (item 039).

The third and final Stage 5 operator family: three seeded
:class:`~segfacet.synth.perturbation.Perturbation` subclasses that inject
label-identity / ordering / spatial-alignment failures onto the item-036
clean-GT positive control (:func:`segfacet.synth.clean_gt.build_clean_spine`),
each returning a well-formed :class:`~segfacet.synth.perturbation.Expectation`
naming the induced §6 failure mode and the offending label(s):

* :class:`DisplacePerturbation` (``"displace"``) -- translates a target
  vertebra's whole mask off the fitted spinal curve (along the two array axes
  that are NOT the stacking axis, resolved from the target volume's own
  affine -- item 116) while keeping its label. Targets the misalignment
  detector of
  :class:`~segfacet.heuristics.mislabel.MislabelRule` (item 033, Detector A,
  §6 mode 1). Because the real pipeline refits a *single smoothing* spline
  through **all** present centroids in ascending-label order every time
  (item 119, ``make_splprep(..., s=n_points)``), the displaced centroid is
  absorbed back onto the refit and plain ``run_qc`` cannot surface this -- it is asserted
  via a **reconstructed** ``per_label_offsets`` record (the target's
  leave-one-out offset) fed to ``MislabelRule`` directly, the same pattern
  item 038's ``force_overlap`` used for ``OverlapRule``.
* :class:`RelabelSwapPerturbation` (``"relabel_swap"``) -- exchanges two
  adjacent vertebra bodies' integer labels, so each label sits at the
  other's anatomical position while the present-label set is unchanged.
  Targets the ordering-inconsistency detector of ``MislabelRule`` (Detector
  B, §6 mode 4). Same structural limitation as ``displace`` (the pipeline
  reorders by ascending label before refitting, so ``non_monotonic_pairs``
  is always empty through ``run_qc``); asserted via a reconstructed
  ``monotonic_consistency`` record (the spline fit through centroids in
  **true spatial order**, evaluated against the ascending-label sequence).
* :class:`SequenceBreakPerturbation` (``"sequence_break"``) -- relabels the
  tail vertebra to a transitional label (T13 = 28) whose canonical rank
  contradicts its integer value, producing a genuine non-monotonic label
  sequence that :class:`~segfacet.heuristics.sequence.SequenceRule` (item 030,
  §6 mode 7) catches directly through the real ``run_qc`` pipeline -- unlike
  the other two operators in this file.

Implemented strictly against the unchanged item-036 contract
(``Perturbation``, ``Expectation``, ``PerturbationResult``,
``register_perturbation``, ``seeded_rng``); ``synth/perturbation.py``,
``synth/clean_gt.py``, ``synth/component_shape.py``, and
``synth/coverage_border_overlap.py`` are not modified (the shared-helper
idioms below are reimplemented locally to keep this file merge-safe
alongside the parallel 037/038 work). Every operator is
seeded/deterministic, non-mutating of the caller's input, and preserves
dtype/shape/affine/spacing.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np
import nibabel as nib

from segfacet.io import FacetInputError
from segfacet.synth.axes import non_stacking_axes
from segfacet.synth.perturbation import (
    Expectation,
    FAILURE_MODE_NAMES,
    Perturbation,
    PerturbationResult,
    register_perturbation,
    seeded_rng,
)

__all__ = [
    "DisplacePerturbation",
    "RelabelSwapPerturbation",
    "SequenceBreakPerturbation",
]

# Default translation magnitude (mm) for `displace`, split across the two
# in-plane axes -- comfortably clears the default 15.0 mm mislabel threshold
# for the item-036 clean GT (verified: isotropic ~18.9 mm, anisotropic
# (1,1,3) ~16.4 mm; see the item spec's Assumptions).
_DEFAULT_DISPLACEMENT_MM: float = 18.0

# Default replacement label for `sequence_break` -- T13 (label 28), whose
# canonical rank (19, below L1) diverges from its integer value (see
# segfacet.labels.DEFAULT_LABEL_MAP / CANONICAL_ORDER).
_DEFAULT_NEW_LABEL: int = 28


# --------------------------------------------------------------------------- #
# Shared module-private helpers (reimplemented locally -- see module docstring)
# --------------------------------------------------------------------------- #


def _present_labels(labelmap: nib.Nifti1Image) -> List[int]:
    """Sorted non-zero unique voxel values present in *labelmap*."""
    data = np.asanyarray(labelmap.dataobj)
    return sorted(int(v) for v in np.unique(data) if v != 0)


def _choose_label(labels: Sequence[int], seed: int) -> int:
    """Deterministically pick one label from *labels* using ``seeded_rng``."""
    rng = seeded_rng(seed)
    idx = int(rng.integers(0, len(labels)))
    return labels[idx]


def _choose_adjacent_pair(labels_sorted: Sequence[int], seed: int) -> Tuple[int, int]:
    """Deterministically pick a consecutive-in-sorted-order pair.

    Returns ``(target, neighbour)`` with ``target`` the lower-index member.
    """
    rng = seeded_rng(seed)
    idx = int(rng.integers(0, len(labels_sorted) - 1))
    return labels_sorted[idx], labels_sorted[idx + 1]


def _new_image(data: np.ndarray, labelmap: nib.Nifti1Image) -> nib.Nifti1Image:
    """Build a fresh image with *data* and the input's affine.

    Never mutates the caller's array; *data* must already be a private copy.
    """
    affine = np.array(labelmap.affine, copy=True)
    return nib.Nifti1Image(data, affine)


def _label_bbox(data: np.ndarray, label: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return ``(mins, maxs)`` voxel-index bounding box for *label* in *data*."""
    coords = np.argwhere(data == label)
    return coords.min(axis=0), coords.max(axis=0)


def _require_present(label: int, labels: Sequence[int], *, what: str) -> None:
    if label not in labels:
        raise FacetInputError(
            f"{what} {label!r} is not present in the segmentation image. "
            f"Available non-zero labels: {list(labels)}."
        )


# --------------------------------------------------------------------------- #
# DisplacePerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class DisplacePerturbation(Perturbation):
    """Translate a target vertebra's whole mask off the fitted spinal curve.

    Registered under ``"displace"``. Translates the target body diagonally
    toward the higher-index end of the two array axes that are NOT the
    stacking (superior-inferior) axis -- resolved from the target volume's
    own affine at ``apply()`` time (item 116, via
    :func:`segfacet.synth.axes.non_stacking_axes`), not a hardcoded index --
    by ``displacement_mm`` (split evenly across the two axes, spacing-aware),
    keeping the body >= 1 voxel inset from every face so it stays a single
    solid block with no bounds / fragmentation / border side-effect (§6 mode
    1). Because the real
    pipeline's interpolating spline refit absorbs the displaced centroid
    (see the module docstring), the misalignment finding is asserted via a
    reconstructed leave-one-out ``per_label_offsets`` record fed to
    ``MislabelRule`` directly, not through plain ``run_qc``. Rejects an
    explicit target not present, or a ``displacement_mm`` too large to fit
    inside the field of view with the required margin.
    """

    name = "displace"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        displacement_mm: float = _DEFAULT_DISPLACEMENT_MM,
    ):
        if displacement_mm <= 0:
            raise FacetInputError(
                f"DisplacePerturbation requires displacement_mm > 0, got "
                f"{displacement_mm!r}."
            )
        self._target_label = target_label
        self._displacement_mm = float(displacement_mm)

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if not labels:
            raise FacetInputError(
                "DisplacePerturbation requires at least one present label; "
                "the input segmentation has none."
            )

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            target = self._target_label
        else:
            target = _choose_label(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        shape = data.shape
        zooms = labelmap.header.get_zooms()[:3]
        axis_a, axis_b = non_stacking_axes(labelmap.affine)
        spacing_a = float(zooms[axis_a])
        spacing_b = float(zooms[axis_b])

        mask = data == target
        _mins, maxs = _label_bbox(data, target)

        per_axis_mm = self._displacement_mm / math.sqrt(2.0)
        da_vox = max(1, int(round(per_axis_mm / spacing_a))) if spacing_a > 0 else 1
        db_vox = max(1, int(round(per_axis_mm / spacing_b))) if spacing_b > 0 else 1

        # Keep >= 1 voxel inset from the higher-index faces of the two
        # non-stacking axes after the shift.
        new_end_a = int(maxs[axis_a]) + da_vox
        new_end_b = int(maxs[axis_b]) + db_vox
        if new_end_a > shape[axis_a] - 2 or new_end_b > shape[axis_b] - 2:
            raise FacetInputError(
                f"DisplacePerturbation: displacement_mm="
                f"{self._displacement_mm!r} is too large for target label "
                f"{target!r} to fit inside the field of view with a "
                "1-voxel margin from every face; reduce displacement_mm."
            )

        coords = np.argwhere(mask)
        new_coords = coords.copy()
        new_coords[:, axis_a] += da_vox
        new_coords[:, axis_b] += db_vox

        data[mask] = 0
        data[new_coords[:, 0], new_coords[:, 1], new_coords[:, 2]] = target
        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=1,
            failure_mode_name=FAILURE_MODE_NAMES[1],
            expected_rule_ids=frozenset({"mislabel"}),
            expected_labels=frozenset({target}),
            expected_verdict="flagged-for-review",
            detail=(
                f"displace: translated label {target} by ({da_vox}, "
                f"{db_vox}) voxels along (array axis {axis_a}, array axis "
                f"{axis_b}) -- the two non-stacking axes -- off the spinal "
                "curve defined by the remaining vertebrae. Not surfaced by "
                "plain run_qc (the interpolating spline refit absorbs the "
                "displaced centroid) -- asserted via a reconstructed "
                "leave-one-out offset fed to MislabelRule directly (see "
                "item 039 Assumptions)."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# RelabelSwapPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class RelabelSwapPerturbation(Perturbation):
    """Exchange two adjacent vertebra bodies' integer-label identities.

    Registered under ``"relabel_swap"``. Swaps the voxel labels of an
    **adjacent** (consecutive-in-sorted-present-label-order) pair, so each
    label now occupies the other's anatomical position while the
    present-label set is unchanged (§6 mode 4). Because the real pipeline
    reorders centroids by ascending label before refitting the spline (see
    the module docstring), the ordering-inconsistency finding is asserted
    via a reconstructed ``monotonic_consistency`` record fed to
    ``MislabelRule`` directly, not through plain ``run_qc``. Rejects a map
    with fewer than 2 present labels, or an explicit non-adjacent pair.
    """

    name = "relabel_swap"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        neighbour_label: Optional[int] = None,
    ):
        self._target_label = target_label
        self._neighbour_label = neighbour_label

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if len(labels) < 2:
            raise FacetInputError(
                "RelabelSwapPerturbation requires at least 2 present labels "
                f"to swap an adjacent pair; found {labels!r}."
            )

        if self._target_label is not None or self._neighbour_label is not None:
            if self._target_label is None or self._neighbour_label is None:
                raise FacetInputError(
                    "RelabelSwapPerturbation requires both target_label and "
                    "neighbour_label when either is given explicitly."
                )
            _require_present(self._target_label, labels, what="target_label")
            _require_present(
                self._neighbour_label, labels, what="neighbour_label"
            )
            idx_t = labels.index(self._target_label)
            idx_n = labels.index(self._neighbour_label)
            if abs(idx_t - idx_n) != 1:
                raise FacetInputError(
                    f"RelabelSwapPerturbation: target_label="
                    f"{self._target_label!r} and neighbour_label="
                    f"{self._neighbour_label!r} are not adjacent in the "
                    f"sorted present-label order {labels!r}."
                )
            target, neighbour = self._target_label, self._neighbour_label
        else:
            target, neighbour = _choose_adjacent_pair(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)

        # Swap via a temporary sentinel value guaranteed to be outside the
        # present-label set (strictly greater than every present label), so
        # the two reassignments never clobber each other.
        sentinel = int(data.max()) + 1
        data[data == target] = sentinel
        data[data == neighbour] = target
        data[data == sentinel] = neighbour

        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=4,
            failure_mode_name=FAILURE_MODE_NAMES[4],
            expected_rule_ids=frozenset({"mislabel"}),
            expected_labels=frozenset({target, neighbour}),
            expected_verdict="flagged-for-review",
            detail=(
                f"relabel_swap: exchanged the voxel identities of adjacent "
                f"labels {target} and {neighbour}. Not surfaced by plain "
                "run_qc (the ascending-label refit yields a monotonic "
                "spline parameter) -- asserted via a reconstructed "
                "monotonic-consistency record fed to MislabelRule directly "
                "(see item 039 Assumptions)."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# SequenceBreakPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class SequenceBreakPerturbation(Perturbation):
    """Relabel a vertebra to a transitional label, breaking value/rank order.

    Registered under ``"sequence_break"``. Relabels the target (default: the
    **tail**, the max present label) to ``new_label`` (default 28 == T13),
    a transitional label whose canonical rank (19, below L1) diverges from
    its integer value under the default convention. Relabelling the tail of
    a contiguous lumbar span produces a genuine non-monotonic label sequence
    that :class:`~segfacet.heuristics.sequence.SequenceRule` catches directly
    through the real ``run_qc`` pipeline (§6 mode 7) -- unlike ``displace``
    and ``relabel_swap`` in this module. Rejects a map with fewer than 2
    present labels (no ordering to break), an explicit target not present,
    or a ``new_label`` already present in the map.
    """

    name = "sequence_break"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        new_label: int = _DEFAULT_NEW_LABEL,
    ):
        self._target_label = target_label
        self._new_label = int(new_label)

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if len(labels) < 2:
            raise FacetInputError(
                "SequenceBreakPerturbation requires at least 2 present "
                f"labels (a single label has no ordering to break); found "
                f"{labels!r}."
            )

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            target = self._target_label
        else:
            # Deterministic default: the tail (max present label). seed is
            # accepted for interface compliance but does not vary this
            # choice -- only the tail->T13 relabel keeps the surviving span
            # canonically contiguous (see item 039 Assumptions).
            target = max(labels)

        if self._new_label in labels:
            raise FacetInputError(
                f"SequenceBreakPerturbation: new_label={self._new_label!r} "
                f"is already present in the segmentation image {labels!r}; "
                "choose a new_label not already in use."
            )

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        data[data == target] = self._new_label
        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=7,
            failure_mode_name=FAILURE_MODE_NAMES[7],
            expected_rule_ids=frozenset({"sequence"}),
            expected_labels=frozenset({self._new_label}),
            expected_verdict="flagged-for-review",
            detail=(
                f"sequence_break: relabelled {target} to {self._new_label} "
                "(a transitional label whose canonical rank diverges from "
                "its integer value), producing a genuine non-continuous "
                "label sequence caught directly by run_qc's sequence rule."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)
