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
  :class:`~segfacet.config.HeuristicConfig`. Empty when the threshold is ``0``.
* **stray_component_count** — number of components other than the dominant one
  (item 098); ``component_count - 1``.
* **stray_component_sizes** — ``component_sizes[1:]`` — every component's voxel
  count except the (largest, index-0) dominant one, same descending order, as
  a non-aliasing copy (item 098).
* **stray_volume_mm3** — ``sum(component_volumes_mm3[1:])``, the summed
  physical volume of the stray population, reusing the already-computed
  per-component volumes rather than a second ``voxel_volume`` multiply (item
  098).
* **stray_volume_fraction** — ``1.0 - largest_component_fraction``, the
  arithmetic complement of that field so the two are always consistent by
  construction rather than by a second, independently-rounded computation
  (item 098).

"Stray" means **every connected component of a label other than its single
largest (dominant) one** — the exact ``component_sizes[1:]`` population. A
single-component label reports the stray-population zero case:
``stray_component_count == 0``, ``stray_component_sizes == []``,
``stray_volume_mm3 == 0.0``, ``stray_volume_fraction == 0.0``.

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
from typing import List, Optional

import numpy as np
import nibabel as nib

import segfacet.backend as _backend_mod
from segfacet.backend import Backend

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
    stray_component_count:
        Number of components other than the dominant one — always
        ``component_count - 1`` (item 098). ``0`` for a single-component
        label.
    stray_component_sizes:
        ``component_sizes[1:]`` — every component's voxel count except the
        dominant (index-0) one, in the same descending order, as a
        non-aliasing copy (item 098). ``[]`` for a single-component label.
    stray_volume_mm3:
        ``sum(component_volumes_mm3[1:])`` — the summed physical volume of
        the stray components, derived from the already-computed
        per-component volumes rather than a second ``voxel_volume``
        multiplication (item 098). ``0.0`` (a ``float``) for a
        single-component label.
    stray_volume_fraction:
        ``1.0 - largest_component_fraction`` — the arithmetic complement of
        ``largest_component_fraction``, so the two always sum to ``1.0``
        by construction (item 098). ``0.0`` for a single-component label.
    """

    component_count: int
    component_sizes: List[int]
    component_volumes_mm3: List[float]
    largest_component_fraction: float
    small_fragments: List[int]
    stray_component_count: int
    stray_component_sizes: List[int]
    stray_volume_mm3: float
    stray_volume_fraction: float


# --------------------------------------------------------------------------- #
# Core compute function
# --------------------------------------------------------------------------- #


def compute_components(
    seg_img: nib.Nifti1Image,
    label: int,
    config,
    *,
    backend: Optional[Backend] = None,
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
        A :class:`~segfacet.config.HeuristicConfig` instance. The
        ``min_fragment_voxels`` field controls the small-fragment threshold.
    backend:
        Optional :class:`~segfacet.backend.Backend` handle routing the array/
        ndimage operations through ``numpy``/``scipy.ndimage`` (CPU) or
        ``cupy``/``cupyx.scipy.ndimage`` (GPU). When ``None`` (the default),
        resolved via :func:`segfacet.backend.get_backend`.

    Returns
    -------
    ComponentsInfo
        All connected-components properties for the requested label.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    backend = backend or _backend_mod.get_backend()
    xp = backend.xp

    # Read data without copying — we never write to it.
    data = xp.asarray(np.asanyarray(seg_img.dataobj))

    # Build boolean mask for the requested label (does not mutate data).
    mask = data == label  # new boolean array, not a view of data

    if not mask.any():
        available = sorted(
            int(v) for v in np.unique(np.asanyarray(seg_img.dataobj)) if v != 0
        )
        raise ValueError(
            f"Label {label!r} is not present in the segmentation image "
            f"(no voxels found). Available non-zero labels: {available}"
        )

    # Run 6-connectivity labelling via backend.ndimage.label (scipy.ndimage
    # for CPU, cupyx.scipy.ndimage for GPU).
    # The default structuring element for ndimage.label is the 3-D cross
    # (face-neighbours only), which implements 6-connectivity.
    labelled, n_components = backend.ndimage.label(mask)
    # labelled: integer array (0=background, 1..n_components=component ids)

    # Count voxels per component and sort descending.
    # xp.bincount is fast and deterministic; index 0 is the background count.
    counts = xp.bincount(labelled.ravel())
    # Slice off index 0 (background), get component counts for ids 1..n.
    component_counts = counts[1:n_components + 1]
    # Sort descending.
    component_sizes_arr = xp.sort(component_counts)[::-1]
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

    # Stray-component metrics (item 098): every component other than the
    # dominant (index-0) one.
    stray_component_sizes: List[int] = list(component_sizes[1:])
    stray_component_count: int = len(stray_component_sizes)
    stray_volume_mm3: float = float(sum(component_volumes_mm3[1:]))
    stray_volume_fraction: float = 1.0 - largest_component_fraction

    return ComponentsInfo(
        component_count=n_components,
        component_sizes=component_sizes,
        component_volumes_mm3=component_volumes_mm3,
        largest_component_fraction=largest_component_fraction,
        small_fragments=small_fragments,
        stray_component_count=stray_component_count,
        stray_component_sizes=stray_component_sizes,
        stray_volume_mm3=stray_volume_mm3,
        stray_volume_fraction=stray_volume_fraction,
    )
