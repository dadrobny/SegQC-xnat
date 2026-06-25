"""Connected-components analysis per label (item 012).

For a given integer label in a NIfTI instance label map, this module runs a
**6-connectivity** connected-components analysis (face-neighbours only, not
diagonal or edge neighbours) and computes:

* **component_count** — number of distinct connected components.
* **component_sizes** — voxel count per component, sorted descending.
* **component_volumes_mm3** — physical volume (mm³) per component, in the same
  order as ``component_sizes``.
* **largest_component_fraction** — ``component_sizes[0] / sum(component_sizes)``;
  equals ``1.0`` when the label is a single connected piece.
* **small_fragments** — list of component sizes (voxel counts) for components
  strictly below the ``min_fragment_voxels`` threshold from
  :class:`~segqc.config.HeuristicConfig`. Empty when the threshold is ``0``.

Connectivity
------------
**6-connectivity** is the only connectivity used here: two voxels are
connected if and only if they share a face (±x, ±y, or ±z neighbour).
Voxels sharing only an edge or a corner are *not* connected. This is the
default ``structure`` for ``scipy.ndimage.label`` (the 3-D cross-shaped
structuring element), so no explicit structuring element is needed.

Public API
----------
``ComponentsInfo``
    Frozen dataclass carrying all per-label connected-components results.
``compute_components(seg_img, label, config) -> ComponentsInfo``
    Compute connected-components for a single label in a NiBabel image.
``CONNECTIVITY``
    Integer constant (``6``) documenting the connectivity used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np
import nibabel as nib

__all__ = [
    "ComponentsInfo",
    "compute_components",
    "CONNECTIVITY",
]

# Documented connectivity constant so callers can query it.
CONNECTIVITY: int = 6


# --------------------------------------------------------------------------- #
# ComponentsInfo dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ComponentsInfo:
    """All connected-components properties for a single integer label.

    All fields are populated by :func:`compute_components`. The dataclass is
    frozen (immutable) and carries no NiBabel objects, so it is cheaply
    serialisable and safe to compare with ``==``.

    Attributes
    ----------
    component_count:
        Number of distinct connected components found for this label.
        Always >= 1 (a label with at least one voxel has at least one
        component).
    component_sizes:
        Voxel count for each component, sorted **descending** (largest
        component first). Length equals ``component_count``.
    component_volumes_mm3:
        Physical volume in mm³ for each component, in the same order as
        ``component_sizes``. Computed as voxel_count × product(spacings).
    largest_component_fraction:
        ``component_sizes[0] / sum(component_sizes)`` — the fraction of
        label voxels that belong to the single largest component. Equals
        ``1.0`` when the label is a single connected piece. Always in
        ``[0.0, 1.0]``.
    small_fragments:
        List of component sizes (voxel counts) for every component whose
        size is **strictly below** the ``min_fragment_voxels`` threshold.
        Empty when ``min_fragment_voxels == 0`` (threshold of 0 means
        nothing is strictly below it). Contains one entry per fragment —
        if two components have the same sub-threshold size, both appear.
    """

    component_count: int
    component_sizes: List[int]
    component_volumes_mm3: List[float]
    largest_component_fraction: float
    small_fragments: List[int]


# --------------------------------------------------------------------------- #
# Core compute function
# --------------------------------------------------------------------------- #


def compute_components(
    seg_img: nib.Nifti1Image,
    label: int,
    config,
) -> ComponentsInfo:
    """Compute connected-components analysis for a single integer label.

    The function is **read-only** — the input image is never modified. It is
    **deterministic**: identical inputs always produce identical outputs.

    6-connectivity is used (face-neighbours only). See :data:`CONNECTIVITY`.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer label map. The header's
        voxel dimensions (``get_zooms()``) are used for physical-volume
        calculations.
    label:
        The integer label value to analyse.
    config:
        A :class:`~segqc.config.HeuristicConfig` instance. The
        ``min_fragment_voxels`` field controls the small-fragment threshold.

    Returns
    -------
    ComponentsInfo
        All connected-components properties for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    # Read data without copying — we never write to it.
    data = np.asanyarray(seg_img.dataobj)

    # Build boolean mask for the requested label (does not mutate data).
    mask = data == label  # new boolean array, not a view of data

    if not mask.any():
        available = sorted(int(v) for v in np.unique(data) if v != 0)
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). Available non-zero labels: {available}"
        )

    # Run 6-connectivity labelling via scipy.ndimage.label.
    # The default structuring element for scipy.ndimage.label is the
    # 3-D cross (face-neighbours only), which implements 6-connectivity.
    from scipy.ndimage import label as ndimage_label  # lazy import

    labelled, n_components = ndimage_label(mask)
    # labelled: integer array (0=background, 1..n_components=component ids)

    # Count voxels per component and sort descending.
    # np.bincount is fast and deterministic; index 0 is the background count.
    counts = np.bincount(labelled.ravel())
    # Slice off index 0 (background), get component counts for ids 1..n.
    component_counts = counts[1:n_components + 1]
    # Sort descending.
    component_sizes_arr = np.sort(component_counts)[::-1]
    component_sizes: List[int] = [int(s) for s in component_sizes_arr]

    # Voxel volume from the image header.
    zooms = seg_img.header.get_zooms()
    voxel_vol = float(zooms[0]) * float(zooms[1]) * float(zooms[2])

    # Physical volumes in the same order as component_sizes.
    component_volumes_mm3: List[float] = [
        float(s) * voxel_vol for s in component_sizes
    ]

    # Largest-component fraction.
    total_voxels = sum(component_sizes)
    largest_component_fraction = float(component_sizes[0]) / float(total_voxels)

    # Small-fragment detection: strictly below threshold.
    min_frag = int(config.min_fragment_voxels)
    small_fragments: List[int] = [s for s in component_sizes if s < min_frag]

    return ComponentsInfo(
        component_count=n_components,
        component_sizes=component_sizes,
        component_volumes_mm3=component_volumes_mm3,
        largest_component_fraction=largest_component_fraction,
        small_fragments=small_fragments,
    )
