"""Per-label first-order intensity features (item 059).

Given a scan (intensity) NIfTI image and a co-registered instance label map,
compute the standard radiomics "first-order" statistics of the scan voxels
lying under a target label's mask: central tendency (mean, median), spread
(std, min, max, range, IQR, percentiles), and intensity entropy.

This is the first feature family in ``segfacet`` to read scan **intensities**
(every prior feature — Stage 2/3 ``geometry``, ``neighbourhood`` — consumed
only the label map). It follows the same convention: a frozen, JSON-friendly
per-label result dataclass and a pure ``compute_*`` function; read-only
inputs; deterministic; NumPy/SciPy only, no file I/O, no PyRadiomics.

Tracked feature set
--------------------
``voxel_count``
    Number of **finite** scan voxels sampled under the label mask (after
    excluding NaN/inf).
``n_nonfinite_excluded``
    Number of masked voxels excluded because they were NaN or +/-inf.
``mean``, ``median``, ``std``, ``min``, ``max``
    Standard location/spread statistics over the finite voxel values.
    ``std`` is the **population** standard deviation (``ddof=0``), matching
    the ``neighbourhood._safe_std`` convention used elsewhere in this
    codebase.
``p05``, ``p25``, ``p50``, ``p75``, ``p95``
    Percentiles of the finite voxel values via ``numpy.percentile`` with its
    default linear interpolation. ``p50`` always equals ``median`` exactly
    (same statistic, same interpolation).
``range``
    ``max - min``.
``iqr``
    ``p75 - p25``.
``entropy``
    Shannon entropy (base 2, in bits) of the finite voxel values over a
    **fixed 32-bin histogram spanning [min, max]**. A uniform/constant region
    (``min == max``) is a degenerate single-bin histogram and its entropy is
    defined as ``0.0``.

Sentinel & non-finite policy
-----------------------------
Unlike :func:`segfacet.features.geometry.compute_label_geometry`, which raises
on an absent label, this extractor never raises for a per-label data
condition: an absent/empty label, or a label whose voxels are all
non-finite, yields a well-formed sentinel record with ``voxel_count == 0``
and every statistic field set to ``None`` (not ``float('nan')`` — ``None``
is JSON-null-friendly and compares equal across repeated calls, whereas
``NaN != NaN`` would break determinism checks). NaN/inf voxels *within* an
otherwise-valid mask are simply excluded from the statistics and counted in
``n_nonfinite_excluded``.

A structural scan<->label grid misalignment (mismatched array shape or
incompatible affine) **does** raise a ``ValueError`` — that is a caller
error, not a per-label data condition. The affine tolerance mirrors
``segfacet.io.load_case`` (``rtol=1e-5, atol=1e-4``); shape must match exactly.

Public API
----------
``LabelIntensity``
    All first-order intensity statistics for a single label.
``compute_label_intensity(scan_img, seg_img, label) -> LabelIntensity``
    Extract first-order intensity features for ``label``.
``compute_intensity_features(scan_img, seg_img) -> Dict[int, LabelIntensity]``
    Convenience mapping every present non-zero label to its
    :class:`LabelIntensity`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import nibabel as nib

__all__ = [
    "LabelIntensity",
    "compute_label_intensity",
    "compute_intensity_features",
]

# Affine-tolerance for the grid-alignment guard, matching segfacet.io.load_case.
_AFFINE_ATOL = 1e-4
_AFFINE_RTOL = 1e-5

# Fixed-bin entropy histogram: 32 bins, base-2 (bits), spanning [min, max] of
# the finite masked values. Documented per the item spec; adjustable so long
# as AC7 (correct entropy) and AC8 (uniform region -> 0.0) hold.
_ENTROPY_BINS = 32

_PERCENTILES = (5, 25, 50, 75, 95)


@dataclass(frozen=True)
class LabelIntensity:
    """First-order intensity statistics for a single integer label.

    All fields are populated by :func:`compute_label_intensity`; the
    dataclass is frozen (immutable), carries no NiBabel objects, and is
    comparable with ``==``, so it is cheaply serialisable.

    Attributes
    ----------
    voxel_count:
        Number of finite scan voxels sampled under the label mask.
    n_nonfinite_excluded:
        Number of masked voxels excluded because they were NaN/inf.
    mean, median, std, min, max:
        Standard location/spread statistics over the finite voxel values.
        ``std`` is the population standard deviation (``ddof=0``).
    p05, p25, p50, p75, p95:
        Percentiles (linear interpolation); ``p50 == median``.
    range:
        ``max - min``.
    iqr:
        ``p75 - p25``.
    entropy:
        Shannon entropy (base 2) over a fixed 32-bin histogram of the finite
        voxel values spanning ``[min, max]``; ``0.0`` for a uniform region.

    All statistic fields are ``None`` when the label is absent/empty or every
    selected voxel is non-finite (see module docstring "Sentinel & non-finite
    policy").
    """

    voxel_count: int
    n_nonfinite_excluded: int
    mean: Optional[float]
    median: Optional[float]
    std: Optional[float]
    min: Optional[float]
    max: Optional[float]
    p05: Optional[float]
    p25: Optional[float]
    p50: Optional[float]
    p75: Optional[float]
    p95: Optional[float]
    range: Optional[float]
    iqr: Optional[float]
    entropy: Optional[float]


def _sentinel(n_nonfinite_excluded: int) -> LabelIntensity:
    """A well-formed all-``None`` statistics record (AC12/AC14)."""
    return LabelIntensity(
        voxel_count=0,
        n_nonfinite_excluded=n_nonfinite_excluded,
        mean=None,
        median=None,
        std=None,
        min=None,
        max=None,
        p05=None,
        p25=None,
        p50=None,
        p75=None,
        p95=None,
        range=None,
        iqr=None,
        entropy=None,
    )


def _check_alignment(scan_img: nib.Nifti1Image, seg_img: nib.Nifti1Image) -> None:
    """Raise ``ValueError`` if scan and seg images are not grid-aligned.

    Mirrors ``segfacet.io.load_case``'s shape/affine checks and message style.
    """
    scan_shape = scan_img.shape
    seg_shape = seg_img.shape
    if tuple(scan_shape) != tuple(seg_shape):
        raise ValueError(
            "Scan and segmentation have mismatched shapes: "
            f"scan {tuple(scan_shape)} vs segmentation {tuple(seg_shape)}."
        )

    scan_affine = np.asarray(scan_img.affine, dtype=float)
    seg_affine = np.asarray(seg_img.affine, dtype=float)
    if not np.allclose(scan_affine, seg_affine, rtol=_AFFINE_RTOL, atol=_AFFINE_ATOL):
        raise ValueError(
            "Scan and segmentation have incompatible affines (beyond tolerance "
            f"rtol={_AFFINE_RTOL}, atol={_AFFINE_ATOL}):\n"
            f"  scan affine:\n{scan_affine}\n"
            f"  segmentation affine:\n{seg_affine}"
        )


def _entropy(values: np.ndarray) -> float:
    """Shannon entropy (base 2) of ``values`` over a fixed-bin histogram.

    Spans ``[min, max]`` with :data:`_ENTROPY_BINS` bins. A degenerate
    (single-valued) region has zero spread and is defined to have entropy
    ``0.0``.
    """
    vmin = float(values.min())
    vmax = float(values.max())
    if vmin == vmax:
        return 0.0
    hist, _ = np.histogram(values, bins=_ENTROPY_BINS, range=(vmin, vmax))
    counts = hist[hist > 0].astype(np.float64)
    probs = counts / counts.sum()
    return float(-(probs * np.log2(probs)).sum())


def compute_label_intensity(
    scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
    label: int,
) -> LabelIntensity:
    """Compute first-order intensity statistics for a single label.

    The function is **read-only** — neither input image is modified. It is
    **deterministic**: identical inputs always produce identical outputs.

    Parameters
    ----------
    scan_img:
        A NiBabel ``Nifti1Image`` carrying scan intensity data.
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map,
        grid-aligned with ``scan_img`` (same shape, compatible affine).
    label:
        The integer label value to sample scan intensities for.

    Returns
    -------
    LabelIntensity
        Populated statistics, or the ``None``-filled sentinel if the label is
        absent/empty or every selected voxel is non-finite.

    Raises
    ------
    ValueError
        If ``scan_img`` and ``seg_img`` have mismatched shapes or
        incompatible affines (beyond tolerance) — a structural caller error,
        checked before any per-label computation.
    """
    _check_alignment(scan_img, seg_img)

    seg_data = np.asanyarray(seg_img.dataobj)
    scan_data = np.asanyarray(scan_img.dataobj)

    mask = seg_data == label
    selected = np.asarray(scan_data[mask], dtype=np.float64)

    if selected.size == 0:
        return _sentinel(n_nonfinite_excluded=0)

    finite_mask = np.isfinite(selected)
    finite_values = selected[finite_mask]
    n_nonfinite_excluded = int(selected.size - finite_values.size)

    if finite_values.size == 0:
        return _sentinel(n_nonfinite_excluded=n_nonfinite_excluded)

    mean = float(np.mean(finite_values))
    median = float(np.median(finite_values))
    std = float(np.std(finite_values, ddof=0))
    vmin = float(np.min(finite_values))
    vmax = float(np.max(finite_values))
    value_range = vmax - vmin

    percentiles = {
        pct: float(np.percentile(finite_values, pct)) for pct in _PERCENTILES
    }
    iqr = percentiles[75] - percentiles[25]
    entropy = _entropy(finite_values)

    return LabelIntensity(
        voxel_count=int(finite_values.size),
        n_nonfinite_excluded=n_nonfinite_excluded,
        mean=mean,
        median=median,
        std=std,
        min=vmin,
        max=vmax,
        p05=percentiles[5],
        p25=percentiles[25],
        p50=percentiles[50],
        p75=percentiles[75],
        p95=percentiles[95],
        range=value_range,
        iqr=iqr,
        entropy=entropy,
    )


def compute_intensity_features(
    scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
) -> Dict[int, LabelIntensity]:
    """Compute :class:`LabelIntensity` for every present non-zero label.

    Parameters
    ----------
    scan_img:
        A NiBabel ``Nifti1Image`` carrying scan intensity data.
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map,
        grid-aligned with ``scan_img``.

    Returns
    -------
    Dict[int, LabelIntensity]
        Mapping ``{label: LabelIntensity}`` over present non-zero labels
        (background ``0`` excluded); each value equals the result of calling
        :func:`compute_label_intensity` for that label individually.

    Raises
    ------
    ValueError
        If ``scan_img`` and ``seg_img`` have mismatched shapes or
        incompatible affines (beyond tolerance).
    """
    _check_alignment(scan_img, seg_img)

    seg_data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)

    return {label: compute_label_intensity(scan_img, seg_img, label) for label in labels}
