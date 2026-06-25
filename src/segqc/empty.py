"""Empty and near-empty segmentation detection for ``segqc`` (item 007).

Provides a single public function, :func:`check_empty`, which inspects a
NiBabel ``Nifti1Image`` instance label map and returns a :class:`CheckResult`
summarising whether the map is empty or near-empty based on configurable
thresholds from :class:`~segqc.config.HeuristicConfig`.

Three independent conditions are checked; any one that fires sets
``is_empty=True``:

1. **No labels present** — the label map is all-zero (foreground voxel count
   is 0 and distinct label count is 0).
2. **Total foreground below N voxels** — the total count of all non-zero
   voxels is below ``config.min_foreground_voxels`` (only checked when
   ``min_foreground_voxels > 0`` and the map is not completely empty).
3. **Fewer than K distinct labels** — the number of distinct non-zero label
   values is below ``config.min_label_count`` (only checked when
   ``min_label_count > 0``).

Default threshold values (``min_foreground_voxels=0``, ``min_label_count=0``)
mean "no threshold applied", so the only automatic failure is a completely
empty label map.

Typical usage::

    import nibabel as nib
    from segqc.config import default_config
    from segqc.empty import check_empty

    seg_img = nib.load("seg.nii.gz")
    cfg = default_config()
    result = check_empty(seg_img, cfg)
    if result.is_empty:
        for reason in result.reasons:
            print(reason)

Design decisions (item 007)
----------------------------
1. **No runtime imports beyond stdlib, NumPy, and NiBabel**: ``scipy``,
   ``skimage``, and ``segqc.verdict`` are deliberately excluded; this module
   returns plain strings rather than ``Reason`` objects so that item 010 can
   wire them into the verdict model without a circular dependency.
2. **``CheckResult`` is a frozen dataclass**: immutable after construction,
   consistent with the ``@dataclass(frozen=True)`` style used elsewhere in
   ``segqc``.
3. **``reasons`` is a ``tuple[str, ...]``** not a ``list``: tuples are
   immutable and round-trip cleanly through ``==`` comparisons, which is
   useful in the tests and consistent with the frozen dataclass contract.
4. **Array extracted via ``np.asanyarray``**: avoids an unnecessary copy of
   the underlying data for memory-mapped images.
5. **label_count=0 when foreground is absent**: avoids calling ``np.unique``
   on an empty slice, and gives a well-defined zero rather than potentially
   raising or returning an unexpected value.
6. **Threshold check for foreground is an ``else if``**: when the map is
   completely empty the "no foreground" reason already fires; the
   ``min_foreground_voxels`` condition is therefore only evaluated for
   non-empty maps (a completely empty map with ``min_foreground_voxels=5``
   would be doubly-flagged, which is noisy and confusing).  The
   ``min_label_count`` condition is independent and evaluated for all maps
   (including empty ones) so that ``min_label_count=1`` fires on an empty map.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import nibabel as nib
    from segqc.config import HeuristicConfig

__all__ = ["CheckResult", "check_empty"]


@dataclasses.dataclass(frozen=True)
class CheckResult:
    """Immutable result returned by :func:`check_empty`.

    Attributes
    ----------
    is_empty:
        ``True`` if any empty-detection condition fired; ``False`` otherwise.
    reasons:
        Human-readable description of each fired condition.  Empty tuple when
        no condition fired.
    foreground_voxels:
        Total count of non-zero voxels in the label map.  Always computed,
        regardless of whether any condition fired.
    label_count:
        Count of distinct non-zero label values in the label map.  Always
        computed, regardless of whether any condition fired.
    """

    is_empty: bool
    reasons: tuple
    foreground_voxels: int
    label_count: int


def check_empty(
    seg_img: "nib.Nifti1Image",
    config: "HeuristicConfig",
) -> CheckResult:
    """Check whether a segmentation label map is empty or near-empty.

    Parameters
    ----------
    seg_img:
        NiBabel ``Nifti1Image`` containing the instance label map.  Non-zero
        voxels are treated as foreground.  The data array is not modified.
    config:
        :class:`~segqc.config.HeuristicConfig` supplying the threshold
        parameters ``min_foreground_voxels`` and ``min_label_count``.

    Returns
    -------
    CheckResult
        An immutable result with ``is_empty``, ``reasons``,
        ``foreground_voxels``, and ``label_count`` fields.
    """
    import nibabel as nib  # lazy import: not needed at module import time

    arr = np.asanyarray(seg_img.dataobj)

    foreground_mask = arr != 0
    foreground_voxels = int(foreground_mask.sum())

    if foreground_voxels > 0:
        label_count = int(np.unique(arr[foreground_mask]).size)
    else:
        label_count = 0

    reasons: list[str] = []

    # Condition 1: completely empty map.
    if foreground_voxels == 0:
        reasons.append("No foreground voxels found (empty label map).")
    # Condition 2: foreground voxel count below threshold (only when map is
    # non-empty; an all-zero map is already covered by condition 1 above).
    elif config.min_foreground_voxels > 0 and foreground_voxels < config.min_foreground_voxels:
        reasons.append(
            f"Foreground voxel count {foreground_voxels} is below the"
            f" minimum {config.min_foreground_voxels}."
        )

    # Condition 3: distinct label count below threshold (checked independently
    # of whether the map is empty so that min_label_count=1 fires on an empty
    # map just as min_foreground_voxels=1 would).
    if config.min_label_count > 0 and label_count < config.min_label_count:
        reasons.append(
            f"Distinct label count {label_count} is below the"
            f" minimum {config.min_label_count}."
        )

    return CheckResult(
        is_empty=bool(reasons),
        reasons=tuple(reasons),
        foreground_voxels=foreground_voxels,
        label_count=label_count,
    )
