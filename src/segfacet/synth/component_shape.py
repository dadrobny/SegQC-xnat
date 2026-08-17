"""Component & shape perturbations: fragment, fuse, inject_islands (item 037).

The first Stage 5 operator family: three seeded :class:`~segfacet.synth.
perturbation.Perturbation` subclasses that inject connected-component /
mask-topology failures onto the item-036 clean-GT positive control
(:func:`segfacet.synth.clean_gt.build_clean_spine`), each returning a
well-formed :class:`~segfacet.synth.perturbation.Expectation` naming the induced
§6 failure mode and the offending label(s):

* :class:`FragmentPerturbation` (``"fragment"``) -- splits one label's body
  into >= 2 comparable disconnected pieces via a thin interior slab cut
  perpendicular to the stacking axis -- resolved from the target volume's own
  affine (item 116), not a hardcoded index -- preserving the label's
  bounding box. Drives the fragmentation-kind ``"fragmentation"`` finding.
* :class:`FusePerturbation` (``"fuse"``) -- merges an adjacent label pair:
  the neighbour's voxels are re-labelled onto the target, leaving the target
  spanning two disconnected bodies. Drives the same fragmentation-kind
  finding on the surviving label (see the item spec's Assumptions for why
  the shipped default lumbar ``bounds`` cannot fire on a two-label fuse).
* :class:`InjectIslandsPerturbation` (``"inject_islands"``) -- adds one or
  more tiny (default 27-voxel, 3x3x3) disconnected components to a target
  label in verified-empty space, inset from every FOV face and separated
  from every label (including the target) by >= 1 empty voxel. Drives the
  island-kind ``"Rogue island(s):"`` finding while the target's dominant
  body stays above the fragmentation-index threshold.

Implemented strictly against the unchanged item-036 contract (``Perturbation``,
``Expectation``, ``PerturbationResult``, ``register_perturbation``,
``seeded_rng``); ``synth/perturbation.py`` and ``synth/clean_gt.py`` are not
modified. Every operator is seeded/deterministic, non-mutating of the
caller's input, and preserves dtype/shape/affine/spacing.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np
import nibabel as nib

from segfacet.io import FacetInputError
from segfacet.synth.axes import si_axis
from segfacet.synth.perturbation import (
    Expectation,
    FAILURE_MODE_NAMES,
    Perturbation,
    PerturbationResult,
    register_perturbation,
    seeded_rng,
)

__all__ = [
    "FragmentPerturbation",
    "FusePerturbation",
    "InjectIslandsPerturbation",
]


# --------------------------------------------------------------------------- #
# Shared module-private helpers
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
    Spacing/affine are read only from *labelmap* (matching
    :class:`~segfacet.synth.perturbation.IdentityPerturbation`'s pattern).
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
# FragmentPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class FragmentPerturbation(Perturbation):
    """Split one label's body into >= 2 comparable disconnected pieces.

    Registered under ``"fragment"``. Carves ``n_pieces - 1`` thin (1-voxel)
    interior slabs through the target label, perpendicular to the stacking
    axis -- resolved from the target volume's own affine at ``apply()`` time
    (item 116, via :func:`segfacet.synth.axes.si_axis`) rather than a
    hardcoded index -- so the label becomes ``n_pieces`` disconnected
    components while its bounding box (and therefore ``bounds`` findings)
    stays unchanged (§6 mode 2).
    """

    name = "fragment"

    def __init__(self, *, target_label: Optional[int] = None, n_pieces: int = 2):
        if n_pieces < 2:
            raise FacetInputError(
                f"FragmentPerturbation requires n_pieces >= 2, got {n_pieces!r}."
            )
        self._target_label = target_label
        self._n_pieces = int(n_pieces)

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if not labels:
            raise FacetInputError(
                "FragmentPerturbation requires at least one present label; the "
                "input segmentation has none."
            )

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            target = self._target_label
        else:
            target = _choose_label(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        mask = data == target
        axis = si_axis(labelmap.affine)
        mins, maxs = _label_bbox(data, target)
        axis_min, axis_max = int(mins[axis]), int(maxs[axis])
        span = axis_max - axis_min

        if span < self._n_pieces:
            raise FacetInputError(
                f"FragmentPerturbation: target label {target!r} spans only "
                f"{span + 1} voxels along the stacking axis (array axis "
                f"{axis}), too thin to carve {self._n_pieces} disconnected "
                "pieces."
            )

        # Evenly spaced interior split planes (strictly between
        # axis_min/axis_max so the union bounding box -- and thus
        # extent_x/y/z_mm -- is preserved, keeping the "bounds" rule silent).
        splits = sorted(
            {
                axis_min + max(1, min(span - 1, round(i * span / self._n_pieces)))
                for i in range(1, self._n_pieces)
            }
        )

        for split_idx in splits:
            idx = tuple(split_idx if a == axis else slice(None) for a in range(3))
            slab = mask[idx]
            view = data[idx]
            view[slab] = 0

        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=2,
            failure_mode_name=FAILURE_MODE_NAMES[2],
            expected_rule_ids=frozenset({"fragmentation"}),
            expected_labels=frozenset({target}),
            expected_verdict="flagged-for-review",
            detail=(
                f"fragment: split label {target} into {self._n_pieces} pieces "
                f"via interior slab cut(s) at stacking-axis (array axis "
                f"{axis}) index(es) {splits}."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# FusePerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class FusePerturbation(Perturbation):
    """Merge an adjacent label pair into a single, two-body label.

    Registered under ``"fuse"``. The neighbour's voxels are re-labelled onto
    the target (unbridged -- the physical gap is not filled), leaving the
    target spanning two disconnected vertebra bodies. Drives the
    fragmentation-kind finding on the surviving label (§6 mode 2; see the
    item spec's Assumptions for why not ``bounds``).
    """

    name = "fuse"

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
                "FusePerturbation requires at least two present labels to fuse "
                f"an adjacent pair; found {labels!r}."
            )

        if self._target_label is not None or self._neighbour_label is not None:
            if self._target_label is None or self._neighbour_label is None:
                raise FacetInputError(
                    "FusePerturbation requires both target_label and "
                    "neighbour_label when either is given explicitly."
                )
            _require_present(self._target_label, labels, what="target_label")
            _require_present(self._neighbour_label, labels, what="neighbour_label")
            idx_t = labels.index(self._target_label)
            idx_n = labels.index(self._neighbour_label)
            if abs(idx_t - idx_n) != 1:
                raise FacetInputError(
                    f"FusePerturbation: target_label={self._target_label!r} and "
                    f"neighbour_label={self._neighbour_label!r} are not adjacent "
                    f"in the sorted present-label order {labels!r}."
                )
            target, neighbour = self._target_label, self._neighbour_label
        else:
            target, neighbour = _choose_adjacent_pair(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        data[data == neighbour] = target
        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=2,
            failure_mode_name=FAILURE_MODE_NAMES[2],
            expected_rule_ids=frozenset({"fragmentation"}),
            expected_labels=frozenset({target}),
            expected_verdict="flagged-for-review",
            detail=(
                f"fuse: absorbed neighbour label {neighbour} into target "
                f"label {target}; {neighbour} is no longer present."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)


# --------------------------------------------------------------------------- #
# InjectIslandsPerturbation
# --------------------------------------------------------------------------- #


@register_perturbation
class InjectIslandsPerturbation(Perturbation):
    """Add one or more tiny rogue disconnected components to a label.

    Registered under ``"inject_islands"``. Each island is a small solid
    block (a cube when ``island_voxels`` is a perfect cube, else a 1-voxel-
    wide line of ``island_voxels`` length) placed in confirmed-empty voxels
    adjacent to the target body along array axis 1 (the clean GT's margin
    space on that axis): >= 1 empty voxel from the body (disconnected under
    6-connectivity) and >= 1 voxel from every FOV face (§6 mode 3). This
    placement is purely geometric (internal margin space, not a named
    anatomical face), so it is unaffected by which array axis carries which
    anatomical direction -- see the module/item-116 note on ``fragment``
    for the one operator in this file that does resolve an axis from the
    affine.
    """

    name = "inject_islands"

    def __init__(
        self,
        *,
        target_label: Optional[int] = None,
        n_islands: int = 1,
        island_voxels: int = 27,
    ):
        if n_islands < 1:
            raise FacetInputError(
                f"InjectIslandsPerturbation requires n_islands >= 1, got {n_islands!r}."
            )
        if island_voxels < 1:
            raise FacetInputError(
                "InjectIslandsPerturbation requires island_voxels >= 1, got "
                f"{island_voxels!r}."
            )
        self._target_label = target_label
        self._n_islands = int(n_islands)
        self._island_voxels = int(island_voxels)

    def _block_dims(self) -> Tuple[int, int, int]:
        """Voxel-index shape of a single island block."""
        n = self._island_voxels
        side = round(n ** (1.0 / 3.0))
        if side >= 1 and side * side * side == n:
            return side, side, side
        # Not a perfect cube: fall back to a 1-voxel-wide line along axis 2
        # (trivially connected, exactly n voxels).
        return 1, 1, n

    def apply(self, labelmap: nib.Nifti1Image, seed: int) -> PerturbationResult:
        labels = _present_labels(labelmap)
        if not labels:
            raise FacetInputError(
                "InjectIslandsPerturbation requires at least one present "
                "label; the input segmentation has none."
            )

        if self._target_label is not None:
            _require_present(self._target_label, labels, what="target_label")
            target = self._target_label
        else:
            target = _choose_label(labels, seed)

        data = np.array(np.asanyarray(labelmap.dataobj), copy=True)
        shape = data.shape
        mins, maxs = _label_bbox(data, target)
        x0, y0, z0 = (int(v) for v in mins)
        x1, y1, z1 = (int(v) for v in maxs)

        bx, by, bz = self._block_dims()

        placed = 0
        # Space successive islands along axis 0 within the body's own x-span
        # (with a 1-voxel gap between islands) so multiple islands don't
        # collide with each other.
        x_max_start = max(x0, x1 - bx + 1)
        x_cursor = x0
        for _ in range(self._n_islands):
            if x_cursor > x_max_start:
                x_cursor = x0  # wrap; blocks are tiny relative to body span
            x_start = min(x_cursor, x_max_start)
            z_start = z0 + max(0, (z1 - z0 + 1 - bz) // 2)

            region = self._find_empty_band(
                data=data,
                shape=shape,
                axis1_low=y0,
                axis1_high=y1,
                block_dims=(bx, by, bz),
                x_start=x_start,
                z_start=z_start,
            )
            if region is None:
                raise FacetInputError(
                    "InjectIslandsPerturbation: no valid empty placement found "
                    f"for label {target!r} (island {placed + 1}/{self._n_islands}); "
                    "the target body's margin is too small for the requested "
                    "island_voxels."
                )
            xs, ys, zs = region
            data[xs, ys, zs] = target
            placed += 1
            x_cursor += bx + 1

        out_img = _new_image(data, labelmap)

        expectation = Expectation(
            failure_mode=3,
            failure_mode_name=FAILURE_MODE_NAMES[3],
            expected_rule_ids=frozenset({"fragmentation"}),
            expected_labels=frozenset({target}),
            expected_verdict="flagged-for-review",
            detail=(
                f"inject_islands: added {self._n_islands} tiny island(s) of "
                f"{self._island_voxels} voxel(s) each to label {target}."
            ),
        )
        return PerturbationResult(labelmap=out_img, expectation=expectation)

    @staticmethod
    def _find_empty_band(
        *,
        data: np.ndarray,
        shape: Tuple[int, int, int],
        axis1_low: int,
        axis1_high: int,
        block_dims: Tuple[int, int, int],
        x_start: int,
        z_start: int,
    ):
        """Find a confirmed-empty block placement below/above the body along axis 1.

        Returns a ``(xs, ys, zs)`` fancy-index tuple (each an ndarray) for the
        block's voxels, or ``None`` if no valid placement exists in either
        direction.
        """
        bx, by, bz = block_dims

        # Candidate 1: strictly below the body along axis 1 (with a 1-voxel
        # gap), inset by >= 1 voxel from the y=0 face.
        y_end = axis1_low - 2  # last row of the block; axis1_low - 1 stays empty
        y_start = y_end - by + 1
        candidates = []
        if y_start >= 1:
            candidates.append((y_start, y_end))

        # Candidate 2: strictly above the body along axis 1 (with a 1-voxel
        # gap), inset by >= 1 voxel from the y=shape[1]-1 face.
        y_start2 = axis1_high + 2
        y_end2 = y_start2 + by - 1
        if y_end2 <= shape[1] - 2:
            candidates.append((y_start2, y_end2))

        x_end = x_start + bx - 1
        z_end = z_start + bz - 1

        if x_start < 1 or x_end > shape[0] - 2:
            return None
        if z_start < 1 or z_end > shape[2] - 2:
            return None

        for y_start_c, y_end_c in candidates:
            block = data[x_start : x_end + 1, y_start_c : y_end_c + 1, z_start : z_end + 1]
            if np.all(block == 0):
                xs, ys, zs = np.meshgrid(
                    np.arange(x_start, x_end + 1),
                    np.arange(y_start_c, y_end_c + 1),
                    np.arange(z_start, z_end + 1),
                    indexing="ij",
                )
                return xs.ravel(), ys.ravel(), zs.ravel()

        return None
