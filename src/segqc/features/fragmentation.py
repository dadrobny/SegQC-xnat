"""Fragmentation index per label (item 025).

The **fragmentation index** for a label is the fraction of the label's voxels
that belong to its single largest connected component:

    fragmentation_index = component_sizes[0] / sum(component_sizes)

Range: ``0 < fragmentation_index <= 1.0``.

* ``1.0`` → single intact body (no fragmentation).
* ``< 1.0`` → progressively split label (lower = more fragmented).

This is a thin wrapper over :func:`segqc.features.components.compute_components`,
which already computes the equivalent ``ComponentsInfo.largest_component_fraction``.
Item 025 exposes it under the public name ``fragmentation_index`` with its own
named, discoverable API used by the JSON serialisation layer.

Public API
----------
``compute_fragmentation_index(seg_img, label, config) -> float``
    Return the fragmentation index for a single label.
"""

from __future__ import annotations

import nibabel as nib

__all__ = ["compute_fragmentation_index"]


def compute_fragmentation_index(
    seg_img: "nib.Nifti1Image",
    label: int,
    config,
) -> float:
    """Compute the fragmentation index for a single integer label.

    The fragmentation index equals ``component_sizes[0] / sum(component_sizes)``,
    i.e. the fraction of label voxels in the largest connected component.  The
    value is in ``(0.0, 1.0]``: it equals ``1.0`` for a fully-connected label and
    approaches ``0.0`` for a highly fragmented label.

    This function is a thin wrapper over
    :func:`segqc.features.components.compute_components`; it does not duplicate
    the component analysis.  The input image is never mutated.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer label map.
    label:
        The integer label value to analyse.
    config:
        A :class:`~segqc.config.HeuristicConfig` instance (forwarded to
        :func:`~segqc.features.components.compute_components`).

    Returns
    -------
    float
        The fragmentation index in ``(0.0, 1.0]``.

    Raises
    ------
    ValueError
        If ``label`` is not present in ``seg_img`` (no voxels carry that value).
    """
    from segqc.features.components import compute_components  # lazy import

    result = compute_components(seg_img, label, config)
    return result.largest_component_fraction
