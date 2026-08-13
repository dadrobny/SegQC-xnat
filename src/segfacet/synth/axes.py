"""Affine-derived anatomical axis resolution, shared by every ``synth/``
operator that targets a named face or must avoid the stacking axis (item
116).

Item 108 made :mod:`segfacet.features.geometry` read the array-axis ->
anatomical-face mapping from a volume's own affine (via
``nibabel.aff2axcodes``) rather than assuming a fixed axis order. This module
is the ``synth/``-side mirror of that mapping: it lets an operator ask "which
array axis, and which end, is the 'superior' face on *this* volume's own
affine?" (:func:`resolve_face`), or "which array axis carries S/I on this
volume?" (:func:`si_axis`), instead of hardcoding an axis index. Every
operator that names a face or must stay off the stacking axis
(``CropAtBorderPerturbation``, ``ForceOverlapPerturbation``,
``FragmentPerturbation``, ``DisplacePerturbation``) resolves through this one
module rather than repeating the ``aff2axcodes`` logic locally.

Deliberately independent of :mod:`segfacet.features.geometry` (not imported
from it): that module is owned by item 108 and not modified here, and the
``synth/`` package's established convention (see e.g.
``coverage_border_overlap.py``'s module docstring) is to reimplement small
shared idioms locally rather than reach across package boundaries, so the two
packages can evolve independently. Both derive the same six-face mapping from
``nibabel.aff2axcodes`` by construction.
"""

from __future__ import annotations

from typing import Tuple

import nibabel as nib

from segfacet.io import FacetInputError

__all__ = [
    "FACE_NAMES",
    "resolve_face",
    "si_axis",
    "non_stacking_axes",
]

#: The six recognised anatomical face names (eager-validatable without an
#: affine -- an operator can check a face string is known at construction
#: time, before the affine that resolves it to an axis is available).
FACE_NAMES = frozenset(
    {"inferior", "superior", "left", "right", "anterior", "posterior"}
)

# Anatomical axcode letter -> (flag name for the axis' *low*-index face, flag
# name for its *high*-index face). ``aff2axcodes`` reports, per array axis,
# which direction *increasing* index points toward; the low face is
# therefore the opposite end of that pair, the high face the named end.
# Mirrors segfacet.features.geometry._AXCODE_TO_FACES (item 108).
_AXCODE_TO_FACES = {
    "R": ("left", "right"),
    "L": ("right", "left"),
    "A": ("posterior", "anterior"),
    "P": ("anterior", "posterior"),
    "S": ("inferior", "superior"),
    "I": ("superior", "inferior"),
}


def _face_axis_map(affine) -> Tuple[Tuple[str, str], Tuple[str, str], Tuple[str, str]]:
    """Derive the per-array-axis (low_face, high_face) name triple from *affine*.

    Raises
    ------
    segfacet.io.FacetInputError
        If *affine* is ``None``, or ``nibabel.aff2axcodes`` cannot resolve
        one of the three array axes to a distinct anatomical direction (a
        singular/rank-deficient affine).
    """
    if affine is None:
        raise FacetInputError(
            "segfacet.synth.axes requires a non-None affine to resolve "
            "anatomical faces/axes."
        )
    axcodes = nib.aff2axcodes(affine)
    if len(axcodes) != 3 or any(code is None for code in axcodes):
        raise FacetInputError(
            "segfacet.synth.axes cannot resolve anatomical faces/axes from a "
            f"degenerate affine (nib.aff2axcodes resolved to {axcodes!r}, not "
            "three distinct anatomical directions)."
        )
    return tuple(_AXCODE_TO_FACES[code] for code in axcodes)  # type: ignore[return-value]


def resolve_face(affine, face: str) -> Tuple[int, str]:
    """Return ``(axis, side)`` for *face*, resolved from *affine*.

    ``side`` is ``"low"`` (index 0 end of that axis) or ``"high"`` (index
    ``shape[axis]-1`` end).

    Raises
    ------
    segfacet.io.FacetInputError
        If *face* is not one of :data:`FACE_NAMES`, or *affine* cannot be
        resolved (see :func:`_face_axis_map`).
    """
    if face not in FACE_NAMES:
        raise FacetInputError(
            f"Unknown face {face!r}. Known faces: {sorted(FACE_NAMES)!r}."
        )
    faces = _face_axis_map(affine)
    for axis, (low, high) in enumerate(faces):
        if face == low:
            return axis, "low"
        if face == high:
            return axis, "high"
    raise FacetInputError(  # pragma: no cover -- unreachable given FACE_NAMES
        f"Face {face!r} did not match any axis in the affine-derived face map."
    )


def si_axis(affine) -> int:
    """Return the array axis whose affine-derived direction is S/I.

    This is the stacking axis for every fixture built by
    :func:`segfacet.synth.clean_gt.build_clean_spine` (AC1), so operators
    that must move *along* or *off* the stacking axis resolve it here rather
    than hardcoding an index.

    Raises
    ------
    segfacet.io.FacetInputError
        If *affine* cannot be resolved (see :func:`_face_axis_map`).
    """
    faces = _face_axis_map(affine)
    for axis, (low, high) in enumerate(faces):
        if {low, high} == {"inferior", "superior"}:
            return axis
    raise FacetInputError(  # pragma: no cover -- unreachable, every axcode maps somewhere
        "segfacet.synth.axes.si_axis: no array axis resolved to the "
        "superior/inferior direction."
    )


def non_stacking_axes(affine) -> Tuple[int, int]:
    """Return the two array axes (ascending order) that are NOT the S/I axis.

    Used by operators (e.g. ``DisplacePerturbation``) that must move a body
    off the spinal curve without perturbing its position along the stacking
    axis itself.
    """
    stacking = si_axis(affine)
    axes = tuple(axis for axis in range(3) if axis != stacking)
    return axes  # type: ignore[return-value]
