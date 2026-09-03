"""Parametric clean-GT (positive-control) spine builder (item 036).

Builds a multi-vertebra **instance label map** -- ordered, plausibly-spaced,
single-component vertebra bodies stacked along a smooth spinal curve -- such
that the real Stage 4 pipeline (:func:`segfacet.pipeline.run_qc`, under the
bundled default config) judges it ``pass`` with zero findings. This is the
positive-control base every Stage 5 perturbation (items 037-039) starts from.

Axis convention (item 116): the **affine is the source of truth**, not a
fixed axis order. ``_affine_from_spacing`` emits a plain positive diagonal
affine, which ``nibabel.aff2axcodes`` resolves to RAS axcodes -- array axis 0
runs left->right, axis 1 posterior->anterior, axis 2 inferior->superior. This
generator places bodies to match that affine's own claim (rather than
contradicting it, as the pre-116 axis-0-stacking layout did): bodies are
stacked along **axis 2** (superior-inferior), axis 0 is left-right, axis 1 is
anterior-posterior. Loading a generated fixture through :mod:`segfacet.io`
(which reorients every volume to RAS) is therefore an array-identity
operation -- the fixture is already RAS-native.

Stacking direction (item 143): ascending labels advance caudally
(descending S), matching real VerSe input read through :mod:`segfacet.io`.
The ``i``-th ascending label occupies slot ``n - 1 - i`` along axis 2, not
slot ``i`` -- so ``labels[0]`` (the most cranial anatomical level, e.g. L1)
sits at the *highest* S and ``labels[-1]`` (e.g. L5) at the *lowest*. The
label order and the array-axis-2 slot order run opposite each other.

Design (see the item 036 spec's Implementation Steps for the full rationale):

* Each body is a solid rectangular block sized in **physical mm**, converted
  to voxel counts via ``spacing`` -- so the body's volume/extents land inside
  every level group's default ``bounds`` regardless of spacing (AC4/AC6).
* Bodies are separated by a fixed gap along axis 2 (the stacking axis;
  disjoint -> no overlap, single component each -- AC7/AC9) and inset from
  all six faces by a margin (no border contact -- AC8).
* Centroids follow a smooth, gently-curved path (a shallow non-negative hump
  in the left-right plane as a function of axis-2 (superior-inferior)
  position); the fitted
  spline (item 017) passes through the centroids exactly (``s=0``
  interpolation), so every offset stays near-zero, well under the default
  15 mm ``mislabel`` threshold (AC11), and the path is centroid-order
  monotonic.
* Content is purely computed (no RNG) -- deterministic (AC24).

The default level span is lumbar L1-L5 (labels 20-24): a canonically-
contiguous run with no interior transitional vertebra, so
``relationships.missing_levels`` stays empty and ``coverage`` stays silent
(see the "transitional-vertebra trap" in the item spec). Any configured
``levels`` must likewise be a contiguous run within a single anatomical group
-- crossing the T12->L1 or L5->S junction interleaves the transitional
vertebrae T13/L6 in :data:`segfacet.labels.CANONICAL_ORDER` and would (correctly)
trip the missing-interior-level coverage check; :func:`build_clean_spine`
raises :class:`~segfacet.io.FacetInputError` for such a span rather than silently
emitting a coverage-flagging map.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import nibabel as nib

from segfacet.io import FacetInputError
from segfacet.labels import CANONICAL_ORDER, LabelConvention

__all__ = [
    "DEFAULT_LEVELS",
    "CleanSpine",
    "build_clean_spine",
]

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

#: Default level span -- lumbar L1-L5 (labels 20-24 under the default
#: convention): a canonically-contiguous run with no interior transitional
#: vertebra (see the module docstring's "transitional-vertebra trap" note).
DEFAULT_LEVELS: Tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5")

# Per-body physical size in mm, named by anatomical direction (not by array
# axis -- see the module docstring: array axis 0 is left-right, axis 1
# anterior-posterior, axis 2 superior-inferior). Chosen to sit comfortably inside
# every level group's DEFAULT_BOUNDS (cervical/thoracic/lumbar)
# simultaneously: volume 25*30*25 = 18750 mm^3 (cervical [3000,35000],
# thoracic [5000,70000], lumbar [8000,120000]); each extent axis is likewise
# inside every group's per-axis range.
_BODY_SIZE_SI_MM: float = 25.0
_BODY_SIZE_LR_MM: float = 30.0
_BODY_SIZE_AP_MM: float = 25.0

# Inter-body gap along the stacking (superior-inferior) axis (mm) -- keeps
# bodies disjoint (no overlap, one component each) with headroom.
_GAP_MM: float = 15.0

# Margin from every one of the six FOV faces (mm) -- keeps every body's
# bounding box strictly inside the volume (no border contact).
_MARGIN_MM: float = 15.0

# Gentle default lateral arc amplitude (mm); small enough that the curve
# never threatens the margin, comfortably below the 15 mm mislabel threshold.
_DEFAULT_CURVE_AMPLITUDE_MM: float = 6.0


# --------------------------------------------------------------------------- #
# CleanSpine dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CleanSpine:
    """A synthesised positive-control spine: a scan + instance label map pair.

    Attributes
    ----------
    scan_img:
        A matching deterministic intensity volume (same shape/affine as
        ``seg_img``), so the pair can be driven through ``segfacet run`` (item
        035/010) end-to-end.
    seg_img:
        The instance label map (integer dtype) -- the actual positive
        control every Stage 4 rule must judge clean.
    labels:
        Present integer labels, ascending.
    level_names:
        Anatomical names, parallel to ``labels``.
    spacing:
        Voxel spacing (sx, sy, sz) in mm.
    shape:
        Voxel-grid shape (nx, ny, nz).
    voxel_counts:
        ``{label: n_voxels}`` for every present label.
    """

    scan_img: nib.Nifti1Image
    seg_img: nib.Nifti1Image
    labels: Tuple[int, ...]
    level_names: Tuple[str, ...]
    spacing: Tuple[float, float, float]
    shape: Tuple[int, int, int]
    voxel_counts: Dict[int, int]


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _affine_from_spacing(spacing: Tuple[float, float, float]) -> np.ndarray:
    """A minimal diagonal RAS-ish affine with ``spacing`` on the diagonal."""
    sx, sy, sz = (float(s) for s in spacing)
    return np.diag([sx, sy, sz, 1.0]).astype(np.float64)


def _validate_span(levels: Sequence[str], convention: LabelConvention) -> Tuple[Tuple[int, ...], Tuple[str, ...]]:
    """Resolve ``levels`` to (labels, level_names), validating the span.

    Raises
    ------
    FacetInputError
        If a level name is unrecognised, or the span is not a canonically
        contiguous run (i.e. it would interleave a transitional vertebra or
        otherwise skip an entry of ``CANONICAL_ORDER``).
    """
    if not levels:
        raise FacetInputError(
            "build_clean_spine requires at least one level name; received an "
            "empty 'levels' sequence."
        )

    rank_of = {name: i for i, name in enumerate(CANONICAL_ORDER)}

    ranks = []
    for name in levels:
        rank = rank_of.get(str(name).strip().upper())
        if rank is None:
            raise FacetInputError(
                f"Unrecognised level name {name!r} in build_clean_spine(levels=...). "
                f"Known canonical level names: {list(CANONICAL_ORDER)}."
            )
        ranks.append(rank)

    for prev, cur in zip(ranks, ranks[1:]):
        if cur != prev + 1:
            raise FacetInputError(
                "build_clean_spine(levels=...) must be a canonically-contiguous "
                f"run with no gaps -- {levels!r} skips over "
                f"{CANONICAL_ORDER[prev + 1:cur]!r} in CANONICAL_ORDER (this "
                "would interleave a transitional vertebra or otherwise "
                "produce an incorrect 'missing interior level' coverage "
                "finding). Use a pure cervical, thoracic, or lumbar run."
            )

    labels = []
    level_names = []
    for name in levels:
        canonical_name = CANONICAL_ORDER[rank_of[str(name).strip().upper()]]
        value = convention.value_of(canonical_name)
        if value is None:
            raise FacetInputError(
                f"Level {canonical_name!r} (requested as {name!r}) has no "
                "integer label in the supplied LabelConvention."
            )
        labels.append(value)
        level_names.append(canonical_name)

    return tuple(labels), tuple(level_names)


# --------------------------------------------------------------------------- #
# Builder
# --------------------------------------------------------------------------- #


def build_clean_spine(
    *,
    levels: Sequence[str] = DEFAULT_LEVELS,
    spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
    convention: Optional[LabelConvention] = None,
    curve_amplitude_mm: float = _DEFAULT_CURVE_AMPLITUDE_MM,
) -> CleanSpine:
    """Build a deterministic, plausibly-spaced positive-control spine.

    Item 143: ascending labels advance caudally (descending S) along the
    stacking axis (axis 2), matching real VerSe input read through
    :mod:`segfacet.io` -- the label order and the array-axis-2 slot order
    run opposite each other.

    Parameters
    ----------
    levels:
        Anatomical level names in head-to-tail order, e.g.
        ``("L1", ..., "L5")``. Must be a canonically-contiguous run within a
        single anatomical group (pure cervical / thoracic / lumbar) -- see
        the module docstring's "transitional-vertebra trap" note.
    spacing:
        Voxel spacing (sx, sy, sz) in mm. Body sizing accounts for spacing so
        the physical volume/extents stay inside the default rule bounds
        regardless of (an)isotropy.
    convention:
        The :class:`~segfacet.labels.LabelConvention` to resolve level names to
        integer labels. Defaults to :meth:`LabelConvention.default`.
    curve_amplitude_mm:
        Peak lateral (left-right) displacement of the smooth centroid arc, in
        mm. ``0.0`` yields a straight line.

    Returns
    -------
    CleanSpine

    Raises
    ------
    segfacet.io.FacetInputError
        If a level name is unrecognised or the span is not canonically
        contiguous within one anatomical group.
    """
    if convention is None:
        convention = LabelConvention.default()

    labels, level_names = _validate_span(levels, convention)
    n = len(labels)

    # sx/sy/sz are per-array-axis spacings (axis 0/1/2 respectively -- the
    # order header.get_zooms() and the affine diagonal both use). Per the
    # module docstring's RAS-native convention: axis 0 = left-right, axis 1 =
    # anterior-posterior, axis 2 = superior-inferior (the stacking axis).
    sx, sy, sz = (float(s) for s in spacing)

    body_vox_lr = max(1, math.ceil(_BODY_SIZE_LR_MM / sx))
    body_vox_ap = max(1, math.ceil(_BODY_SIZE_AP_MM / sy))
    body_vox_si = max(1, math.ceil(_BODY_SIZE_SI_MM / sz))

    gap_vox_si = max(1, math.ceil(_GAP_MM / sz))
    margin_vox_lr = max(1, math.ceil(_MARGIN_MM / sx))
    margin_vox_ap = max(1, math.ceil(_MARGIN_MM / sy))
    margin_vox_si = max(1, math.ceil(_MARGIN_MM / sz))

    amplitude = max(0.0, float(curve_amplitude_mm))
    amplitude_vox_lr = math.ceil(amplitude / sx) if amplitude > 0.0 else 0

    shape0 = 2 * margin_vox_lr + body_vox_lr + amplitude_vox_lr
    shape1 = 2 * margin_vox_ap + body_vox_ap
    shape2 = 2 * margin_vox_si + n * body_vox_si + max(0, n - 1) * gap_vox_si
    shape = (int(shape0), int(shape1), int(shape2))

    seg_data = np.zeros(shape, dtype=np.uint16)

    voxel_counts: Dict[int, int] = {}
    for i, label in enumerate(labels):
        # Ascending labels advance caudally (descending S): the i-th
        # ascending label occupies slot n - 1 - i along the stacking axis,
        # not slot i (item 143). The hump stays keyed on i (A2): it is
        # symmetric in i, so this reassignment reverses only which label
        # sits at which S -- the emitted geometry is bit-identical.
        slot = n - 1 - i
        start2 = margin_vox_si + slot * (body_vox_si + gap_vox_si)
        end2 = start2 + body_vox_si

        # Smooth, non-negative lateral hump: 0 at the ends, peaking at the
        # middle body -- always >= 0, so a fixed one-sided margin suffices.
        frac = (i / (n - 1)) if n > 1 else 0.0
        shift_mm = amplitude * math.sin(math.pi * frac)
        shift_vox_lr = int(round(shift_mm / sx)) if sx > 0 else 0
        shift_vox_lr = max(0, min(shift_vox_lr, amplitude_vox_lr))

        start0 = margin_vox_lr + shift_vox_lr
        end0 = start0 + body_vox_lr

        start1 = margin_vox_ap
        end1 = start1 + body_vox_ap

        seg_data[start0:end0, start1:end1, start2:end2] = label
        voxel_counts[label] = int(body_vox_lr * body_vox_ap * body_vox_si)

    affine = _affine_from_spacing(spacing)
    seg_img = nib.Nifti1Image(seg_data, affine)

    # A deterministic, non-constant scan texture (a simple ramp along axis 2,
    # the stacking/superior-inferior axis), mirroring tests/synthetic.py's
    # make_scan(gradient=True) idiom.
    ramp = np.arange(shape[2], dtype=np.int64).reshape(1, 1, shape[2])
    scan_data = np.ascontiguousarray(np.broadcast_to(ramp, shape).astype(np.int16))
    scan_img = nib.Nifti1Image(scan_data, affine)

    return CleanSpine(
        scan_img=scan_img,
        seg_img=seg_img,
        labels=labels,
        level_names=level_names,
        spacing=(sx, sy, sz),
        shape=shape,
        voxel_counts=voxel_counts,
    )
