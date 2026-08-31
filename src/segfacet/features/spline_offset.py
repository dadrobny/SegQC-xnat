"""Per-vertebra perpendicular offset from the fitted spline (item 018).

For each vertebra centroid in the ordered sequence, compute its closest-approach
distance to the parametric spline produced by :func:`segfacet.features.spline.fit_centroid_spline`.

The closest point on the spline is found by
:func:`segfacet.features.spline.find_closest_point` (item 130) -- the one
shared coarse-scan-then-refine search this module used to write out for
itself: a coarse scan over uniformly-spaced ``u`` values locates the
approximate minimum, then ``scipy.optimize.minimize_scalar`` refines it,
bracketed around the coarse minimum, for sub-mm accuracy.

The result is a :class:`VertebralSplineOffset` per centroid capturing the
Euclidean distance in mm and in voxel units (anisotropic-aware), the raw
signed-component displacement vector (dx_mm, dy_mm, dz_mm), and the spline
parameter value of the closest point.

Public API
----------
``VertebralSplineOffset``
    Frozen dataclass with per-centroid offset data.
``compute_spline_offsets(centroids, fit, spacing_mm=None) -> List[VertebralSplineOffset]``
    Compute one offset record per centroid, **in-sample**: the level under
    test shaped the curve it is measured against.
``compute_leave_one_out_spline_offsets(centroids, spacing_mm=None, *, backend=None) -> List[VertebralSplineOffset]``
    Compute one offset record per centroid, **held out** (item 120): the
    level under test does not shape the curve it is judged against.

Deliberate CPU fallback (item 072)
-----------------------------------
``compute_spline_offsets`` and ``compute_leave_one_out_spline_offsets`` both
accept a ``backend`` keyword for signature uniformity with the other Stage-2/3
feature functions, but their numeric work always runs on CPU: the coarse ``u``
scan, ``scipy.optimize.minimize_scalar`` refinement, and the leave-one-out
refits operate on tiny centroid arrays with no reliable CuPy equivalent, so
this is a documented, known partial-GPU-coverage limitation -- even under an
explicit GPU backend, the optimisation runs on SciPy/CPU with host arrays and
returns host results.

Held-out evaluation (item 120)
--------------------------------
``compute_spline_offsets`` is *in-sample*: the fit it is evaluated against was
shaped by every centroid it measures, including the one under test, so a
displaced vertebra pulls the smoothing spline (item 119) toward itself and its
own offset reads far below the applied displacement -- the circularity item
118 diagnosed. ``compute_leave_one_out_spline_offsets`` corrects this by
measuring each level against a curve it did not shape:

1. Fit once through all present centroids at equal weight (the "reference
   fit"), and identify the single most-deviant level under that fit -- the
   **dominant outlier**, chosen as the largest in-sample ``offset_mm``, ties
   broken by **ascending label**.
2. For each level in turn, refit through **the same chord-length
   parameterisation** (``u``) as the reference fit, but with that level's own
   weight and the dominant outlier's weight both driven to a negligible
   constant. Withholding by **down-weighting instead of dropping** keeps
   every level in the curve's parameter domain -- terminal levels are still
   measured against curve interior, not against a truncated endpoint -- while
   a negligible weight keeps the withheld level from pulling the fit toward
   itself. Withholding the case's dominant outlier too prevents one broken
   vertebra from bending its neighbours' held-out curves (outlier
   cross-talk).
3. Below **five** levels the held-out path falls back to the in-sample
   measurement (item 129, D5). The floor is five, not four, for a reason
   specific to this fit: at exactly four points the spline is a **cubic**
   (``k=3``) with exactly four coefficients, so it **interpolates** all four
   points **regardless of the weights** -- down-weighting a level to
   ``_WITHHELD_WEIGHT`` still leaves it, and every other point, exactly on
   the curve. The "held-out" curve at four points is therefore numerically
   the in-sample curve (the two agree to ~1e-13 mm on the corpus's one
   four-level case), and a floor of four silently claimed a held-out
   measurement it never made.

**Documented limitation: the four-level blind spot.** At exactly four
levels, an interior level displaced by a full **15 mm** still reads a
held-out ``offset_mm`` below **0.001 mm** -- both the held-out and in-sample
paths read essentially zero, so a four-level field of view cannot raise a
``mislabel`` offset finding under any threshold. Measured 2026-08-31 (item
129); asserted, not only documented, by
``tests/test_129_coincident_centroids_and_held_out_floor.py``'s
four-level-blind-spot tests. Closing this gap needs a change to the fit's
**degree** at small ``n`` (clamping it below ``n - 1`` so a cubic cannot
interpolate four points) -- a change to the curve formulation the
2026-08-27 "Spinal curve model -- the deformity envelope" **human gate**
approved, and therefore not this module's (or any agent's) call to make.

**Documented limitation.** A displaced *terminal* level on a short spine is
not reliably separable: withholding a terminal level and the dominant outlier
leaves only three points to constrain a cubic at five levels (the committed
corpus's level count), so the held-out offset under-reports the true
displacement there. Real fields of view carry far more than five levels, and
this is measurably resolved by level count alone -- not worked around here.

**Documented limitation: only the single dominant outlier is withheld.**
Step 1 identifies and withholds one outlier per refit. With **two or more**
genuinely displaced levels, every un-withheld displaced level still pulls
every *other* level's held-out curve toward itself, which can both under-report
a real displacement and over-report a clean level as displaced. Measured on
the adversarial two-opposite-displacements case (two levels displaced in
opposite directions): a genuinely **clean** level reads **31.96 mm** while one
of the **displaced** levels reads only **19.31 mm** -- the clean level can be
named an offender ahead of an actual one. This is accepted as a known, shipped
limitation (not fixed by this item); the natural follow-up is withholding
every level above some outlier cutoff, not just the single dominant one, and
is left to future work.

Terminal-vertebra exclusion (item 123, 2026-08-29 human decision)
------------------------------------------------------------------
Every :class:`VertebralSplineOffset` carries ``is_terminal``: ``True`` for
the first and last entry of the ordered centroid sequence it was measured
in (and for **every** entry when the sequence has one or two points, so
there is no interior at all), ``False`` otherwise. It is sequence-relative,
not label-relative -- reversing the input order still marks the same two
anatomical ends, matched by which end they occupy, not by list index.

This exists because the held-out estimator's refit must **extrapolate**
past the end of its own parameter domain at a sequence terminus: withholding
a terminal level's own point still fits the curve through every interior
point, but the terminal level's closest-approach search runs past the last
interior control point rather than between two of them, which can read an
implausibly large offset for a vertebra that is not actually displaced.
Measured on the real VerSe19 cohort while calibrating this module's
``mislabel`` threshold (item 123): the caudal-terminal level (`L5` in most
of the cohort) reached a `p99` of `21.209` mm against an *interior* maximum
of `1.00` mm at the same level -- a purely positional artefact, not
deformity. `heuristics/mislabel.py`, `reference/ingest.py` and
`reference/delta.py` all read this flag and exclude a terminal entry from
their respective offset judgements (never Detector B's ordering check, which
does not use per-vertebra offsets at all). This is a stop-gap accepted
knowingly, not a model of the true uncertainty: a genuinely displaced
terminal vertebra is not detected by this rule at all until a smarter
treatment (a separate terminal-aware calibration, an extrapolation-aware
estimator, or a curvature model that does not need both neighbours) replaces
it.

RAS axis contract for the direction components (item 120)
-------------------------------------------------------------
``dx_mm``, ``dy_mm`` and ``dz_mm`` are anatomically readable -- array axis 0
is left-right, axis 1 is anterior-posterior, axis 2 is cranio-caudal -- **only
because** two facts hold elsewhere in this codebase: ``segfacet.io.
load_volume`` reorients every volume to axis codes ``("R", "A", "S")``
(``io.py``'s ``_TARGET_AXCODES``) before any feature is computed, and
:func:`segfacet.features.centroids.compute_centroid` derives ``centroid_mm``
as ``centroid_voxel * spacing`` with no affine of its own. If either fact
changed, the direction components would still be well-defined numbers but
would no longer mean "left-right" / "anterior-posterior" / "cranio-caudal".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import List, Optional, Sequence, Tuple

import numpy as np

import segfacet.backend as _backend_mod
from segfacet.backend import Backend
from segfacet.features.centroids import LabelCentroid
from segfacet.features.spline import SplineFit, find_closest_point, fit_centroid_spline

__all__ = [
    "VertebralSplineOffset",
    "compute_spline_offsets",
    "compute_leave_one_out_spline_offsets",
]

# Weight assigned to a withheld level's own point (and the case's dominant
# outlier) in a leave-one-out refit (item 120). Small enough to be
# negligible relative to the uniform 1.0 weight on every other point, but
# strictly positive -- make_splprep rejects a zero weight.
_WITHHELD_WEIGHT: float = 1e-6

# Below this many levels, the held-out refit cannot mean anything -- fall
# back to the in-sample measurement (item 120, AC7). Five, not four (item
# 129, D5): at four points the fit is a cubic (k=3) with exactly four
# coefficients, so it interpolates all four points regardless of the
# weights -- the "held-out" curve is numerically the in-sample curve. See
# the module docstring's "Held-out evaluation" step 3 for the full argument
# and the measured four-level blind spot.
_MIN_LEVELS_FOR_HELD_OUT: int = 5


# --------------------------------------------------------------------------- #
# VertebralSplineOffset dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VertebralSplineOffset:
    """Per-vertebra perpendicular offset from the fitted spline.

    Attributes
    ----------
    label : int
        The integer label value.
    level_name : str
        Anatomical vertebra name (from the source LabelCentroid).
    closest_u : float
        Spline parameter value (0..1) of the closest point on the curve.
    offset_mm : float
        Euclidean distance (mm) from the centroid to the closest spline point.
        Near-zero for on-curve centroids; large for displaced vertebrae.
    offset_voxel : float
        Same distance expressed in voxel units.  Equal to offset_mm when
        spacing_mm is isotropic 1 mm; differs under anisotropic spacing.
    dx_mm : float
        x-component of the displacement vector (centroid_mm[0] - spline_x),
        in mm.
    dy_mm : float
        y-component of the displacement vector, in mm.
    dz_mm : float
        z-component of the displacement vector, in mm.
    is_terminal : bool
        ``True`` when this centroid is the first or last of the **ordered
        sequence it was measured in** (or the sequence has 1-2 points, so
        every entry is an end) -- item 123's terminality flag. Sequence-
        relative, not label-relative: reversing the input order still marks
        the same two anatomical ends (see the module docstring's
        "Terminal-vertebra exclusion" section). Defaults to ``False`` so
        existing hand-built records (an entry with no key, or ``None``) read
        as interior -- item 123's ``mislabel``/reference consumers rely on
        this default.
    """

    label: int
    level_name: str
    closest_u: float
    offset_mm: float
    offset_voxel: float
    dx_mm: float
    dy_mm: float
    dz_mm: float
    is_terminal: bool = False


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Public compute function
# --------------------------------------------------------------------------- #


def compute_spline_offsets(
    centroids: Sequence[LabelCentroid],
    fit: SplineFit,
    spacing_mm: Optional[Tuple[float, float, float]] = None,
    *,
    backend: Optional[Backend] = None,
) -> List[VertebralSplineOffset]:
    """Compute the perpendicular offset of each centroid from the fitted spline.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects.  Must be the same sequence
        (or a subset) used to produce ``fit``.
    fit:
        The SplineFit produced by fit_centroid_spline.
    spacing_mm:
        Voxel spacings (sx, sy, sz) in mm used to convert offset_mm to
        offset_voxel.  When None, isotropic 1 mm spacing is assumed (so
        offset_voxel == offset_mm).
    backend:
        Optional :class:`~segfacet.backend.Backend` handle, forwarded to
        :func:`~segfacet.features.spline.find_closest_point`. When ``None``
        (the default), resolved via :func:`segfacet.backend.get_backend`; the
        optimisation itself always runs on host NumPy/SciPy regardless (see
        the module docstring's "Deliberate CPU fallback" section).

    Returns
    -------
    List[VertebralSplineOffset]
        One record per centroid, in the same order as the input sequence.
        The list is never empty when centroids is non-empty.

    Raises
    ------
    ValueError
        When centroids is empty or fit has fewer than 2 points.
    """
    backend = backend or _backend_mod.get_backend()

    if len(centroids) == 0:
        raise ValueError(
            "compute_spline_offsets requires at least one centroid, "
            "but received an empty sequence."
        )

    # Determine per-axis voxel spacings (default: isotropic 1 mm).
    if spacing_mm is None:
        sx, sy, sz = 1.0, 1.0, 1.0
    else:
        sx, sy, sz = float(spacing_mm[0]), float(spacing_mm[1]), float(spacing_mm[2])

    records: List[VertebralSplineOffset] = []
    n_points = len(centroids)

    for idx, c in enumerate(centroids):
        is_terminal = n_points <= 2 or idx == 0 or idx == n_points - 1

        pt = np.array(
            [float(c.centroid_mm[0]), float(c.centroid_mm[1]), float(c.centroid_mm[2])],
            dtype=np.float64,
        )

        closest = find_closest_point(pt, fit, backend=backend)
        u_star = closest.closest_u

        # Displacement vector: centroid - closest spline point.
        spline_pt = np.asarray(closest.point_mm, dtype=np.float64)  # shape (3,)
        diff = pt - spline_pt  # (dx_mm, dy_mm, dz_mm)

        dx_mm = float(diff[0])
        dy_mm = float(diff[1])
        dz_mm = float(diff[2])

        # Euclidean distance in mm.
        offset_mm = float(math.sqrt(dx_mm ** 2 + dy_mm ** 2 + dz_mm ** 2))

        # Voxel-space distance: anisotropic-correct sqrt of scaled components.
        offset_voxel = float(
            math.sqrt((dx_mm / sx) ** 2 + (dy_mm / sy) ** 2 + (dz_mm / sz) ** 2)
        )

        records.append(
            VertebralSplineOffset(
                label=c.label,
                level_name=c.level_name,
                closest_u=u_star,
                offset_mm=offset_mm,
                offset_voxel=offset_voxel,
                dx_mm=dx_mm,
                dy_mm=dy_mm,
                dz_mm=dz_mm,
                is_terminal=is_terminal,
            )
        )

    return records


# --------------------------------------------------------------------------- #
# Held-out (leave-one-out) evaluation (item 120)
# --------------------------------------------------------------------------- #


def compute_leave_one_out_spline_offsets(
    centroids: Sequence[LabelCentroid],
    spacing_mm: Optional[Tuple[float, float, float]] = None,
    *,
    fit: Optional[SplineFit] = None,
    backend: Optional[Backend] = None,
) -> List[VertebralSplineOffset]:
    """Compute each centroid's offset from a spline it did not shape.

    See the module docstring's "Held-out evaluation (item 120)" section for
    the full definition. In short: a reference fit through all centroids at
    equal weight identifies the case's dominant outlier (the largest
    in-sample ``offset_mm``, ties broken by **ascending label**); then, for
    each level, a refit through the reference fit's own chord-length ``u``
    down-weights that level and the dominant outlier to a negligible
    constant (never zero -- ``make_splprep`` rejects that), so the level
    under test cannot pull the curve toward itself while the curve's
    parameter domain never shrinks.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects.
    spacing_mm:
        Voxel spacings (sx, sy, sz) in mm, forwarded to
        :func:`compute_spline_offsets` for the ``offset_voxel`` conversion.
    fit:
        Optional externally-supplied in-sample :class:`SplineFit` to use as
        the reference fit (item 130), sparing a caller that already fit the
        same curve (``pipeline.extract_feature_record``, for curvature /
        tangent orientations / monotonic consistency) a second, redundant
        fit. When supplied, this function makes **no** ``fit_centroid_spline``
        call of its own for the reference fit -- the per-level held-out
        refits are unaffected and still happen here. The caller is
        responsible for supplying the in-sample fit through *these exact*
        centroids, fit at this module's own defaults (chord-length ``u``,
        uniform weights, default degree/smoothing) -- ``fit`` is validated
        only on centroid count (below), not on geometry: re-deriving it to
        verify would reinstate the second fit this parameter exists to
        remove. ``None`` (the default) reproduces today's behaviour: fit
        internally.
    backend:
        Optional :class:`~segfacet.backend.Backend` handle, forwarded to the
        fit/evaluate calls this function makes. The refits themselves always
        run on host NumPy/SciPy regardless -- see the module docstring's
        "Deliberate CPU fallback" section.

    Returns
    -------
    List[VertebralSplineOffset]
        One record per input centroid, in input order, with the same field
        set :func:`compute_spline_offsets` returns.

    Raises
    ------
    ValueError
        Propagated from :func:`~segfacet.features.spline.fit_centroid_spline`
        or :func:`compute_spline_offsets` (e.g. fewer than 2 centroids, or
        two centroids sharing an exactly-coincident mm-coordinate). Also
        raised when *fit* is supplied and its ``n_points`` does not equal
        ``len(centroids)``, naming both counts -- checked before any other
        validation, including the single-centroid early return below.
    """
    backend = backend or _backend_mod.get_backend()

    n_points = len(centroids)

    if fit is not None and fit.n_points != n_points:
        raise ValueError(
            f"compute_leave_one_out_spline_offsets received a fit with "
            f"n_points={fit.n_points}, but centroids has length {n_points}. "
            f"The supplied fit must be the in-sample fit through exactly "
            f"these centroids."
        )

    if n_points == 1:
        # No curve can be fit through a single point (fit_centroid_spline
        # requires >= 2), so this must be handled before any fit is
        # attempted -- unlike n_points == 2/3, which fit_centroid_spline
        # tolerates and which fall through to the branch below. AC37 (item
        # 123) requires every entry of a 1-2 point sequence to read
        # is_terminal=True; offset_mm=0.0 is the defensible reading for a
        # single point -- there is nothing to be offset from.
        c = centroids[0]
        return [
            VertebralSplineOffset(
                label=c.label,
                level_name=c.level_name,
                closest_u=0.0,
                offset_mm=0.0,
                offset_voxel=0.0,
                dx_mm=0.0,
                dy_mm=0.0,
                dz_mm=0.0,
                is_terminal=True,
            )
        ]

    reference_fit = fit if fit is not None else fit_centroid_spline(centroids, backend=backend)

    if n_points < _MIN_LEVELS_FOR_HELD_OUT:
        return compute_spline_offsets(
            centroids, reference_fit, spacing_mm=spacing_mm, backend=backend
        )

    in_sample = compute_spline_offsets(
        centroids, reference_fit, spacing_mm=spacing_mm, backend=backend
    )

    # Dominant outlier: largest in-sample offset_mm, ties broken by
    # ascending label.
    worst_idx = min(
        range(n_points),
        key=lambda i: (-in_sample[i].offset_mm, centroids[i].label),
    )

    records: List[Optional[VertebralSplineOffset]] = [None] * n_points
    for i in range(n_points):
        weights = [1.0] * n_points
        weights[i] = _WITHHELD_WEIGHT
        weights[worst_idx] = _WITHHELD_WEIGHT

        refit = fit_centroid_spline(
            centroids, u=reference_fit.u, weights=weights, backend=backend
        )
        record = compute_spline_offsets(
            [centroids[i]], refit, spacing_mm=spacing_mm, backend=backend
        )[0]
        # compute_spline_offsets always reads is_terminal from the length-1
        # list it was just given (so it always reports True there) -- the
        # terminality that actually matters is the position in the OUTER
        # (full-cohort) sequence this function was given, so it is recomputed
        # here and substituted onto the returned record.
        is_terminal = n_points <= 2 or i == 0 or i == n_points - 1
        if record.is_terminal != is_terminal:
            record = replace(record, is_terminal=is_terminal)
        records[i] = record

    return records  # type: ignore[return-value]
