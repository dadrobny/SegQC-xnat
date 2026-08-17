"""Coverage, border & overlap perturbations: remove_level, crop_at_border,
force_overlap (item 038).

The second Stage 5 operator family: three seeded :class:`~segfacet.synth.
perturbation.Perturbation` subclasses that inject label-coverage /
spatial-extent failures onto the item-036 clean-GT positive control
(:func:`segfacet.synth.clean_gt.build_clean_spine`), each returning a
well-formed :class:`~segfacet.synth.perturbation.Expectation` naming the induced
§6 failure mode and the offending label(s):

* :class:`RemoveLevelPerturbation` (``"remove_level"``) -- deletes an
  interior (non-terminal) vertebra from the span, leaving an anatomical gap
  that :class:`~segfacet.heuristics.coverage.CoverageRule` (item 029) detects as
  a case-level ``"Missing interior level(s):"`` finding (§6 mode 5).
* :class:`CropAtBorderPerturbation` (``"crop_at_border"``) -- translates a
  target vertebra toward a chosen **in-plane** FOV face and clips the
  overhang, so ``touches_<face>`` becomes ``True`` and
  :class:`~segfacet.heuristics.border.BorderRule` (item 031) fires a
  label-attributed ``"Partial vertebra clipped by FOV:"`` finding (§6 mode
  6).
* :class:`ForceOverlapPerturbation` (``"force_overlap"``) -- shifts an
  entire target body along the stacking (superior-inferior) axis -- resolved
  from the target volume's own affine (item 116), not a hardcoded index --
  toward an adjacent neighbour, reassigning the contested overhang voxels
  from the neighbour to the target. Because a single-integer label map cannot store a voxel
  belonging to two labels, this overlap is **not** visible through the
  normal ``run_qc`` one-hot pipeline -- it is asserted via a reconstructed
  two-channel mask stack fed to :func:`segfacet.features.overlap.detect_overlaps`
  / :class:`~segfacet.heuristics.overlap.OverlapRule` directly (§6 mode 8; see
  the item spec's Assumptions for the full rationale).

Implemented strictly against the unchanged item-036 contract (``Perturbation``,
``Expectation``, ``PerturbationResult``, ``register_perturbation``,
``seeded_rng``); ``synth/perturbation.py``, ``synth/clean_gt.py``, and
``synth/component_shape.py`` are not modified (the shared-helper idioms
below are reimplemented locally to keep this file merge-safe alongside the
parallel 037/039 work). Every operator is seeded/deterministic, non-mutating
of the caller's input, and preserves dtype/shape/affine/spacing.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import nibabel as nib

from segfacet.io import FacetInputError
from segfacet.labels import LabelConvention
from segfacet.synth.axes import FACE_NAMES, resolve_face, si_axis
from segfacet.synth.perturbation import (
    Expectation,
    FAILURE_MODE_NAMES,
    Perturbation,
    PerturbationResult,
    register_perturbation,
    seeded_rng,
)

__all__ = [
    "RemoveLevelPerturbation",
    "CropAtBorderPerturbation",
    "ForceOverlapPerturbation",
]


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


def _level_name(label: int) -> str:
    """Best-effort anatomical name for *label* under the default convention."""
    return LabelConvention.default().name_of(label)


# --------------------------------------------------------------------------- #
# Face -> (axis, side) resolution -- delegated to segfacet.synth.axes
# (item 116, AC5): the axis is resolved from each fixture's own affine via
# nibabel.aff2axcodes, not a hardcoded index, so this operator behaves
# identically regardless of a fixture's array-axis order.
# --------------------------------------------------------------------------- #

_IN_PLANE_FACES = frozenset({"left", "right", "anterior", "posterior"})


def _validate_face_name(face: str) -> None:
    """Eagerly validate *face* is a known face name (no affine needed yet).

    Raises
    ------
    FacetInputError
        If *face* is not one of the six recognised geometry face names.
    """
    if face not in FACE_NAMES:
        raise FacetInputError(
            f"Unknown face {face!r}. Known faces: {sorted(FACE_NAMES)!r}."
        )


# --------------------------------------------------------------------------- #
# RemoveLevelPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class RemoveLevelPerturbation(Perturbation):
    """Delete an interior (non-terminal) vertebra, leaving a coverage gap.

    Registered under ``"remove_level"``. Zeroes every voxel of the target
    label, leaving a level-sequence gap that
    :class:`~segfacet.heuristics.coverage.CoverageRule` detects via
    ``relationships.missing_levels`` as a case-level
    ``"Missing interior level(s):"`` finding (§6 mode 5). Rejects a span with
    fewer than 3 present labels (no interior level exists) or an explicit
    terminal (span-end) target.
    """

    name = "remove_level"

    def __init__(self, *, target_label: Optional[int] = None):
        self._target_label = target_label

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if len(labels) < 3:
            raise FacetInputError(
                "RemoveLevelPerturbation requires at least 3 present labels "
                f"(an interior level to remove); found {labels!r}."
            )

        interior = labels[1:-1]

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            if self._target_label not in interior:
                raise FacetInputError(
                    f"RemoveLevelPerturbation: target_label={self._target_label!r} "
                    f"is a span-end (terminal) level in {labels!r}; removing a "
                    "terminal level shrinks the span instead of producing a "
                    "detectable interior gap. Choose an interior label."
                )
            target = self._target_label
        else:
            # Deterministic default: the middle interior label (seed accepted
            # for interface compliance but unused -- this operator's choice
            # is not stochastic; see the item's Decisions log).
            target = interior[len(interior) // 2]

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        data[data == target] = 0
        out_img = _new_image(data, labelmap)

        level_name = _level_name(target)
        expectation = Expectation(
            failure_mode=5,
            failure_mode_name=FAILURE_MODE_NAMES[5],
            expected_rule_ids=frozenset({"coverage"}),
            expected_labels=frozenset(),
            expected_verdict="flagged-for-review",
            detail=(
                f"remove_level: deleted interior level {level_name} "
                f"(label {target}) from the span {labels!r}."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# CropAtBorderPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class CropAtBorderPerturbation(Perturbation):
    """Truncate a target vertebra against a chosen in-plane FOV face.

    Registered under ``"crop_at_border"``. Translates the target body toward
    the chosen face by ``margin + crop_depth`` voxels along that axis and
    clips the overhang outside ``[0, shape[axis))``, so the retained body
    touches the face (driving :class:`~segfacet.heuristics.border.BorderRule`,
    §6 mode 6) while its retained volume stays inside the level group's
    ``bounds``. The axis/side for the requested face is resolved from the
    target volume's own affine at ``apply()`` time (item 116, AC5) via
    :func:`segfacet.synth.axes.resolve_face` -- not a hardcoded index.
    Defaults to an in-plane face (``"anterior"``) so the clip is always
    classified unexpected regardless of the target's terminal position.
    Rejects an unknown face string.
    """

    name = "crop_at_border"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        face: str = "anterior",
        crop_depth: int = 5,
    ):
        # Validate the face name eagerly (a bad string raises at
        # construction time too); the axis it resolves to is not known until
        # apply() has the target volume's affine.
        _validate_face_name(face)
        if crop_depth < 1:
            raise FacetInputError(
                f"CropAtBorderPerturbation requires crop_depth >= 1, got "
                f"{crop_depth!r}."
            )
        self._target_label = target_label
        self._face = face
        self._crop_depth = int(crop_depth)

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        axis, side = resolve_face(labelmap.affine, self._face)

        labels = _present_labels(labelmap)
        if not labels:
            raise FacetInputError(
                "CropAtBorderPerturbation requires at least one present "
                "label; the input segmentation has none."
            )

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            target = self._target_label
        else:
            target = _choose_label(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        shape = data.shape
        mask = data == target
        coords = np.argwhere(mask)
        axis_vals = coords[:, axis]

        if side == "low":
            margin = int(axis_vals.min())
            shift = -(margin + self._crop_depth)
        else:
            margin = int(shape[axis] - 1 - axis_vals.max())
            shift = margin + self._crop_depth

        data[mask] = 0
        new_coords = coords.copy()
        new_coords[:, axis] += shift
        valid = (new_coords[:, axis] >= 0) & (new_coords[:, axis] < shape[axis])
        new_coords = new_coords[valid]
        if new_coords.shape[0] == 0:
            raise FacetInputError(
                f"CropAtBorderPerturbation: crop_depth={self._crop_depth!r} is "
                f"too large for target label {target!r} -- the entire body "
                "would be clipped away."
            )
        data[new_coords[:, 0], new_coords[:, 1], new_coords[:, 2]] = target

        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=6,
            failure_mode_name=FAILURE_MODE_NAMES[6],
            expected_rule_ids=frozenset({"border"}),
            expected_labels=frozenset({target}),
            expected_verdict="flagged-for-review",
            detail=(
                f"crop_at_border: translated label {target} toward the "
                f"{self._face!r} face by {self._crop_depth} voxel(s) beyond "
                "touching, clipping the overhang."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# ForceOverlapPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class ForceOverlapPerturbation(Perturbation):
    """Shift a target body toward an adjacent neighbour to force overlap.

    Registered under ``"force_overlap"``. Shifts the whole target body along
    the stacking (superior-inferior) axis -- resolved from the target
    volume's own affine at ``apply()`` time (item 116) via
    :func:`segfacet.synth.axes.si_axis`, not a hardcoded index -- toward an
    adjacent neighbour by ``gap + overlap_depth`` voxels; the contested
    overhang voxels are
    reassigned from the neighbour to the target in the single-integer output
    array (the target stays a single solid block of unchanged volume). This
    overlap is *not* visible through the normal ``run_qc`` one-hot pipeline
    (see the module/item docstring); it is asserted via a reconstructed
    two-channel mask stack fed to
    :func:`segfacet.features.overlap.detect_overlaps` /
    :class:`~segfacet.heuristics.overlap.OverlapRule` directly (§6 mode 8).
    Rejects a map with fewer than 2 labels or an explicit non-adjacent pair.
    """

    name = "force_overlap"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        neighbour_label: Optional[int] = None,
        overlap_depth: int = 3,
    ):
        if overlap_depth < 1:
            raise FacetInputError(
                f"ForceOverlapPerturbation requires overlap_depth >= 1, got "
                f"{overlap_depth!r}."
            )
        self._target_label = target_label
        self._neighbour_label = neighbour_label
        self._overlap_depth = int(overlap_depth)

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if len(labels) < 2:
            raise FacetInputError(
                "ForceOverlapPerturbation requires at least two present "
                f"labels to force an overlap between an adjacent pair; "
                f"found {labels!r}."
            )

        if self._target_label is not None or self._neighbour_label is not None:
            if self._target_label is None or self._neighbour_label is None:
                raise FacetInputError(
                    "ForceOverlapPerturbation requires both target_label and "
                    "neighbour_label when either is given explicitly."
                )
            _require_present(self._target_label, labels, what="target_label")
            _require_present(self._neighbour_label, labels, what="neighbour_label")
            idx_t = labels.index(self._target_label)
            idx_n = labels.index(self._neighbour_label)
            if abs(idx_t - idx_n) != 1:
                raise FacetInputError(
                    f"ForceOverlapPerturbation: target_label="
                    f"{self._target_label!r} and neighbour_label="
                    f"{self._neighbour_label!r} are not adjacent in the "
                    f"sorted present-label order {labels!r}."
                )
            target, neighbour = self._target_label, self._neighbour_label
        else:
            target, neighbour = _choose_adjacent_pair(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        shape = data.shape
        axis = si_axis(labelmap.affine)

        t_mins, t_maxs = _label_bbox(data, target)
        n_mins, n_maxs = _label_bbox(data, neighbour)

        # Direction along the stacking axis from target toward neighbour,
        # and the current inter-body gap along that axis.
        if n_mins[axis] > t_maxs[axis]:
            direction = 1
            gap = int(n_mins[axis]) - int(t_maxs[axis]) - 1
        else:
            direction = -1
            gap = int(t_mins[axis]) - int(n_maxs[axis]) - 1
        gap = max(0, gap)

        shift = direction * (gap + self._overlap_depth)

        target_coords = np.argwhere(data == target)
        new_coords = target_coords.copy()
        new_coords[:, axis] += shift
        valid = (new_coords[:, axis] >= 0) & (new_coords[:, axis] < shape[axis])
        new_coords = new_coords[valid]
        if new_coords.shape[0] != target_coords.shape[0]:
            raise FacetInputError(
                f"ForceOverlapPerturbation: overlap_depth={self._overlap_depth!r} "
                f"shifts target label {target!r} outside the image bounds; "
                "reduce overlap_depth."
            )

        # Erase the target's original footprint, then write the shifted
        # block. Writing after erasing lets the shifted target block claim
        # any neighbour voxels it now overlaps (reassigning the contested
        # overhang from the neighbour to the target), while voxels the
        # target no longer occupies revert to background.
        data[data == target] = 0
        data[new_coords[:, 0], new_coords[:, 1], new_coords[:, 2]] = target

        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=8,
            failure_mode_name=FAILURE_MODE_NAMES[8],
            expected_rule_ids=frozenset({"overlap"}),
            expected_labels=frozenset({target, neighbour}),
            expected_verdict="flagged-for-review",
            detail=(
                f"force_overlap: shifted label {target} by {shift} voxel(s) "
                f"along the stacking axis (array axis {axis}) toward "
                f"neighbour label {neighbour}, reassigning the contested "
                f"overhang from {neighbour} to {target}."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)
