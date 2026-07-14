"""Optional PyRadiomics adapter, behind a capability/adapter boundary (item 060).

This module sits *alongside* item 059's hand-rolled first-order extractor
(:mod:`segqc.features.intensity`). PyRadiomics (PyPI package ``pyradiomics``,
import name ``radiomics``) is a heavy, install-finicky optional dependency
(it transitively pulls SimpleITK) — it is **never required**. The
``import radiomics`` is wrapped in a ``try/except ImportError`` at module
scope so that :mod:`segqc.features.radiomics` itself always imports cleanly,
regardless of whether PyRadiomics happens to be installed.

Normalised result shape
------------------------
:class:`LabelRadiomics` is a frozen, JSON-friendly dataclass with exactly:

``first_order``
    The item-059 :class:`~segqc.features.intensity.LabelIntensity` block.
``extended``
    A flat ``Dict[str, float]`` of higher-order features (``{}`` when
    PyRadiomics is unavailable/disabled/skipped). Flat rather than a nested
    dataclass because the higher-order feature set is backend-defined.
``backend``
    Provenance marker for ``extended`` — ``"builtin"`` (none) or
    ``"pyradiomics"``. See :data:`RADIOMICS_BACKEND_BUILTIN` /
    :data:`RADIOMICS_BACKEND_PYRADIOMICS`.
``radiomics_available``
    Whether PyRadiomics actually produced ``extended`` for this call.

First-order stays authoritative (pin)
--------------------------------------
Even when PyRadiomics is present and enabled, the canonical ``first_order``
block is always produced by item 059's deterministic
``compute_label_intensity`` — never by PyRadiomics. Downstream heuristics
(items 062/064) consume first-order features and must not silently change
behaviour depending on whether an optional library happens to be installed.
PyRadiomics therefore only contributes *additional* higher-order families
into ``extended``; if PyRadiomics' own first-order values were ever wanted
they would be namespaced inside ``extended``, never used to populate
``first_order``.

Documented enabled feature classes (present path)
---------------------------------------------------
When PyRadiomics is present and enabled, the extractor is configured with
**only** the ``glcm`` (Gray Level Co-occurrence Matrix texture) and
``shape`` feature classes enabled (first-order is deliberately left
disabled on the PyRadiomics side — item 059 already owns first-order).
Resulting ``extended`` keys are PyRadiomics' own dotted names, e.g.
``"original_glcm_Contrast"``, ``"original_shape_Sphericity"``, etc. (the
``original_`` prefix is PyRadiomics' image-type prefix since no filters are
applied). Only finite float values are kept.

Pinned deterministic extractor settings (present path)
---------------------------------------------------------
To keep present-path output reproducible (AC14), the extractor is built with
fixed settings declared as module constants:

- ``binWidth`` fixed at :data:`_PYRADIOMICS_BIN_WIDTH` (no auto binCount).
- No resampling/interpolation (``resampledPixelSpacing`` left unset /
  ``interpolator`` unused) — PyRadiomics operates directly on the native
  scan/mask grid.
- ``label`` set to the requested integer label so PyRadiomics restricts
  itself to that mask value.
- Scan/mask arrays are handed to PyRadiomics as SimpleITK images built from
  the NumPy scan/mask with the label's voxel spacing (derived from the
  ``Nifti1Image`` affine); no randomness is introduced anywhere in the path.

Empty/absent label & alignment guards
----------------------------------------
The scan<->label grid-alignment guard (mismatched shape, or incompatible
affine beyond tolerance) is inherited transitively from item 059: computing
``first_order`` via ``compute_label_intensity`` performs that check *before*
any PyRadiomics work is attempted, so both the builtin and present paths
raise identically and before touching PyRadiomics (AC9). Likewise, when
``first_order.voxel_count == 0`` (absent/empty label, or an all-non-finite
mask), the PyRadiomics wrapper is **not** invoked at all — PyRadiomics would
error on an empty mask — and ``extended`` is simply ``{}`` (AC10). A
**non-empty but too-small/degenerate** mask (e.g. a single-voxel label, or a
paper-thin sliver) that PyRadiomics' own geometry validation rejects with a
``ValueError`` is likewise degraded to the builtin result rather than
propagating that exception (item 076) — so the "degrade cleanly" philosophy
now covers both the empty and the degenerate-but-nonempty case.

Public API
----------
``pyradiomics_available() -> bool``
    Capability probe; never raises.
``LabelRadiomics``
    The normalised per-label result dataclass.
``compute_label_radiomics(scan_img, seg_img, label, *, enable_pyradiomics=True) -> LabelRadiomics``
    Extract the normalised result for a single label.
``compute_radiomics_features(scan_img, seg_img, *, enable_pyradiomics=True) -> Dict[int, LabelRadiomics]``
    Convenience mapping over every present non-zero label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import nibabel as nib

from segqc.features.intensity import (
    LabelIntensity,
    compute_label_intensity,
    _check_alignment,
)

__all__ = [
    "pyradiomics_available",
    "LabelRadiomics",
    "compute_label_radiomics",
    "compute_radiomics_features",
    "RADIOMICS_BACKEND_BUILTIN",
    "RADIOMICS_BACKEND_PYRADIOMICS",
]

# Backend/provenance markers for LabelRadiomics.backend.
RADIOMICS_BACKEND_BUILTIN = "builtin"
RADIOMICS_BACKEND_PYRADIOMICS = "pyradiomics"

# Pinned, deterministic PyRadiomics extractor settings (present path only).
_PYRADIOMICS_BIN_WIDTH = 25.0
_PYRADIOMICS_ENABLED_FEATURE_CLASSES = ("glcm", "shape")

# Guarded optional import: segqc.features.radiomics must import cleanly even
# when PyRadiomics (import name `radiomics`) is not installed.
try:
    import radiomics  # noqa: F401
    from radiomics.featureextractor import RadiomicsFeatureExtractor

    _PYRADIOMICS_IMPORT_OK = True
except ImportError:  # pragma: no cover - exercised only when absent
    radiomics = None
    RadiomicsFeatureExtractor = None
    _PYRADIOMICS_IMPORT_OK = False


def pyradiomics_available() -> bool:
    """Return whether the PyRadiomics library (``radiomics``) is importable.

    Never raises.
    """
    return bool(_PYRADIOMICS_IMPORT_OK)


@dataclass(frozen=True)
class LabelRadiomics:
    """Normalised per-label radiomics result.

    Attributes
    ----------
    first_order:
        The item-059 :class:`~segqc.features.intensity.LabelIntensity`
        block; always authoritative and backend-independent.
    extended:
        Flat mapping of higher-order (PyRadiomics-derived) feature name to
        finite ``float`` value; ``{}`` when PyRadiomics is
        unavailable/disabled, or the label is empty/absent.
    backend:
        Provenance marker for ``extended``: :data:`RADIOMICS_BACKEND_BUILTIN`
        or :data:`RADIOMICS_BACKEND_PYRADIOMICS`.
    radiomics_available:
        Whether PyRadiomics actually produced ``extended`` for this call.
    """

    first_order: LabelIntensity
    extended: Dict[str, float]
    backend: str
    radiomics_available: bool


def _builtin_result(first_order: LabelIntensity) -> LabelRadiomics:
    return LabelRadiomics(
        first_order=first_order,
        extended={},
        backend=RADIOMICS_BACKEND_BUILTIN,
        radiomics_available=False,
    )


def _extract_with_pyradiomics(
    scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
    label: int,
) -> Dict[str, float]:
    """Run the pinned-settings PyRadiomics extractor for a single label.

    Assumes the caller has already verified grid alignment and that the
    label's mask is non-empty. Builds SimpleITK images from the NumPy
    scan/mask with the label's voxel spacing, restricted to ``label``.
    """
    import SimpleITK as sitk  # local import: only reached on the present path

    scan_data = np.asanyarray(scan_img.dataobj, dtype=np.float64)
    seg_data = np.asanyarray(seg_img.dataobj)

    spacing = tuple(float(s) for s in scan_img.header.get_zooms()[:3])

    # SimpleITK expects array axes in (z, y, x) order relative to spacing
    # (x, y, z); NumPy/NiBabel arrays here are (x, y, z), so transpose.
    scan_sitk = sitk.GetImageFromArray(np.transpose(scan_data, (2, 1, 0)))
    scan_sitk.SetSpacing(spacing)

    mask_data = (seg_data == label).astype(np.uint8)
    mask_sitk = sitk.GetImageFromArray(np.transpose(mask_data, (2, 1, 0)))
    mask_sitk.SetSpacing(spacing)

    settings = {
        "binWidth": _PYRADIOMICS_BIN_WIDTH,
        "label": 1,
        "interpolator": None,
        "resampledPixelSpacing": None,
        "normalize": False,
    }
    extractor = RadiomicsFeatureExtractor(**settings)
    extractor.disableAllFeatures()
    for feature_class in _PYRADIOMICS_ENABLED_FEATURE_CLASSES:
        extractor.enableFeatureClassByName(feature_class)

    raw = extractor.execute(scan_sitk, mask_sitk)

    extended: Dict[str, float] = {}
    for key, value in raw.items():
        if key.startswith("diagnostics_"):
            continue
        try:
            fvalue = float(value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(fvalue):
            continue
        extended[str(key)] = fvalue
    return extended


def compute_label_radiomics(
    scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
    label: int,
    *,
    enable_pyradiomics: bool = True,
) -> LabelRadiomics:
    """Compute the normalised radiomics result for a single label.

    Parameters
    ----------
    scan_img:
        A NiBabel ``Nifti1Image`` carrying scan intensity data.
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map,
        grid-aligned with ``scan_img``.
    label:
        The integer label value to extract features for.
    enable_pyradiomics:
        When ``False``, forces the builtin (first-order-only) path even if
        PyRadiomics happens to be installed (deterministic disable seam for
        item 065's config knob).

    Returns
    -------
    LabelRadiomics
        ``first_order`` always populated via item 059's
        ``compute_label_intensity`` (which also performs the grid-alignment
        guard). ``extended``/``backend``/``radiomics_available`` reflect
        whichever path ran.

    Raises
    ------
    ValueError
        If ``scan_img`` and ``seg_img`` have mismatched shapes or
        incompatible affines (beyond tolerance) — raised before any
        PyRadiomics work is attempted, on both paths.
    """
    first_order = compute_label_intensity(scan_img, seg_img, label)

    if not (enable_pyradiomics and pyradiomics_available()):
        return _builtin_result(first_order)

    if first_order.voxel_count == 0:
        # Empty/absent label or all-non-finite mask: never hand PyRadiomics
        # an empty mask (it would error). Degrade to the builtin markers.
        return _builtin_result(first_order)

    try:
        extended = _extract_with_pyradiomics(scan_img, seg_img, label)
    except ValueError:
        # Non-empty but too-small/degenerate mask: PyRadiomics' own geometry
        # validation may reject it (ValueError), e.g. a single-voxel label or
        # a paper-thin sliver. Degrade to the builtin markers, exactly like
        # the empty-mask case above -- never let PyRadiomics' rejection
        # propagate.
        return _builtin_result(first_order)

    return LabelRadiomics(
        first_order=first_order,
        extended=extended,
        backend=RADIOMICS_BACKEND_PYRADIOMICS,
        radiomics_available=True,
    )


def compute_radiomics_features(
    scan_img: nib.Nifti1Image,
    seg_img: nib.Nifti1Image,
    *,
    enable_pyradiomics: bool = True,
) -> Dict[int, LabelRadiomics]:
    """Compute :class:`LabelRadiomics` for every present non-zero label.

    Parameters
    ----------
    scan_img:
        A NiBabel ``Nifti1Image`` carrying scan intensity data.
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map,
        grid-aligned with ``scan_img``.
    enable_pyradiomics:
        See :func:`compute_label_radiomics`.

    Returns
    -------
    Dict[int, LabelRadiomics]
        Mapping ``{label: LabelRadiomics}`` over present non-zero labels
        (background ``0`` excluded); each value equals the result of calling
        :func:`compute_label_radiomics` for that label individually.

    Raises
    ------
    ValueError
        If ``scan_img`` and ``seg_img`` have mismatched shapes or
        incompatible affines (beyond tolerance).
    """
    _check_alignment(scan_img, seg_img)

    seg_data = np.asanyarray(seg_img.dataobj)
    labels = sorted(int(v) for v in np.unique(seg_data) if v != 0)

    return {
        label: compute_label_radiomics(
            scan_img, seg_img, label, enable_pyradiomics=enable_pyradiomics
        )
        for label in labels
    }
