"""Parametric spline fit through ordered vertebra centroids (item 017).

Fits a smooth parametric B-spline through the mm-coordinates of an ordered
centroid sequence (as produced by item 014), exposing a continuous spinal-curve
representation that:

* Can be **sampled at arbitrary parameter values** along the curve (0..1).
* Supports approximate **arc-length parameterisation** — sufficient for the
  deviation and consistency features in items 018–020.
* Is **robust to a missing level** — removing one centroid from an otherwise
  complete sequence does not crash.
* Handles **as few as 2 centroids** without error (degree clamped to 1).

Public API
----------
``SplineFit``
    Frozen dataclass carrying the fitted spline result.
``fit_centroid_spline(centroids, degree=3, *, smoothing=None) -> SplineFit``
    Fit a parametric B-spline through the ordered centroid mm-coordinates.
``evaluate_spline(fit, u_values) -> np.ndarray``
    Evaluate the spline at the supplied parameter values; returns ``(N, 3)``
    float64 array of (x, y, z) mm-coordinates.
``evaluate_spline_derivative(fit, u_values, nu=1) -> np.ndarray``
    Evaluate the spline's ``nu``-th derivative at the supplied parameter
    values; returns ``(N, 3)`` float64 array.
``find_coincident_centroid_pair(centroids) -> CoincidentCentroidPair | None``
    Return the first pair of exactly-coincident centroid mm-coordinates, or
    ``None`` when every coordinate is pairwise distinct (item 129). Used by
    ``fit_centroid_spline`` to build its coincidence ``ValueError``, and by
    ``pipeline.extract_feature_record`` to pre-check and degrade gracefully
    instead of letting that error propagate.
``ClosestPointOnCurve``
    Frozen dataclass carrying a closest-point search result: the minimising
    parameter, the point on the curve, and the distance to it.
``find_closest_point(point_mm, curve, *, n_scan=500, xatol=1e-6, backend=None) -> ClosestPointOnCurve``
    The one closest-point search (item 130): coarse-scan the curve over
    ``n_scan`` uniformly-spaced parameter values, then refine with a bounded
    ``scipy.optimize.minimize_scalar`` at tolerance ``xatol``. Accepts either
    a :class:`SplineFit` or a bare ``evaluate(u_values) -> (N, 3)`` callable,
    so a caller with no ``SplineFit`` (``scripts/compare_curve_candidates.py``'s
    polynomial and axis-wise candidates) needs no copy of the algorithm. The
    single owner of the search that used to be written out separately in
    ``features/spline_offset.py``, ``features/consistency.py`` and
    ``scripts/compare_curve_candidates.py``; ``closest_u`` is the value item
    132 reuses for its monotonicity judgement.

Deliberate CPU fallback (item 072)
-----------------------------------
``fit_centroid_spline``, ``evaluate_spline`` and ``evaluate_spline_derivative``
all accept a ``backend`` keyword for signature uniformity with the other
Stage-2/3 feature functions, but their numeric work always runs on CPU:
``make_splprep`` operates on tiny centroid arrays (at most a few dozen points)
with no reliable CuPy equivalent, so this is a documented, known
partial-GPU-coverage limitation -- even under an explicit GPU backend, inputs
are marshalled to host NumPy, the fit/evaluate runs on SciPy/CPU, and host
NumPy results are returned.

Curve formulation (item 119)
-----------------------------
The fit is a smoothing spline built with ``scipy.interpolate.make_splprep``
at ``s = n_points`` by default (overridable via ``smoothing``; ``s = 0``
reproduces the legacy interpolating fit), per the decision recorded in
``docs/spinal-curve-model.md``. ``make_splprep`` returns a ``(BSpline, u)``
pair rather than the legacy FITPACK ``(tck, u)``, so ``SplineFit`` carries a
``scipy.interpolate.BSpline`` instance (``spline``) instead of a ``tck``
tuple; the underlying ``t``/``c``/``k`` are reachable as ``spline.t`` /
``spline.c`` / ``spline.k``.

Held-out evaluation support (item 120)
----------------------------------------
``fit_centroid_spline`` accepts two keyword-only parameters used by
:func:`segfacet.features.spline_offset.compute_leave_one_out_spline_offsets`
to withhold a level from the curve it is judged against, without shrinking
the curve's parameter domain: ``u`` supplies an explicit parameterisation
(instead of letting ``make_splprep`` compute chord-length ``u`` from the
supplied points), so a refit can reuse the parameterisation of a reference
fit through *all* present centroids even when some of those centroids are
down-weighted; ``weights`` supplies a strictly-positive per-point weight
(forwarded to ``make_splprep``'s ``w=``), so a withheld level stays in the
knot placement but cannot pull the fit toward itself. Both default to
today's behaviour (chord-length ``u``, uniform weights) when omitted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy.interpolate import BSpline, make_splprep
from scipy.optimize import minimize_scalar

import segfacet.backend as _backend_mod
from segfacet.backend import Backend
from segfacet.features.centroids import LabelCentroid

__all__ = [
    "SplineFit",
    "CoincidentCentroidPair",
    "find_coincident_centroid_pair",
    "fit_centroid_spline",
    "evaluate_spline",
    "evaluate_spline_derivative",
    "ClosestPointOnCurve",
    "find_closest_point",
]

# Closest-point search (item 130): coarse-scan resolution. 500 gives sub-mm
# resolution for typical whole-spine extents (~400 mm total arc length).
_CLOSEST_POINT_N_SCAN: int = 500

# Closest-point search (item 130): refinement tolerance passed to
# scipy.optimize.minimize_scalar's ``xatol`` option.
_CLOSEST_POINT_XATOL: float = 1e-6


# --------------------------------------------------------------------------- #
# SplineFit dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SplineFit:
    """Parametric smoothing spline through ordered vertebra centroids.

    Attributes
    ----------
    spline:
        The ``scipy.interpolate.BSpline`` returned by ``make_splprep``. Its
        knot vector, coefficients and degree are reachable as ``spline.t``,
        ``spline.c`` and ``spline.k`` respectively.
    smoothing:
        The smoothing factor ``s`` actually used to build ``spline`` (see
        :func:`fit_centroid_spline`).
    u:
        Parameter values (0..1) at which the input centroids lie on the fitted
        spline, stored as a tuple of floats.  Length equals ``n_points``.
    degree:
        Polynomial degree used for the fit (may be less than the requested
        degree when the sequence is short — see :func:`fit_centroid_spline`).
    n_points:
        Number of input centroids used to fit the spline.
    """

    spline: BSpline
    smoothing: float
    u: tuple          # parameter values for input points, length == n_points
    degree: int
    n_points: int


# --------------------------------------------------------------------------- #
# Core fitting function
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CoincidentCentroidPair:
    """The first pair of exactly-coincident centroid mm-coordinates found by
    :func:`find_coincident_centroid_pair` (item 129).

    Attributes
    ----------
    coordinate_mm:
        The shared mm-coordinate, as a 3-tuple of floats.
    level_a, level_b:
        The two coincident levels' names, in the order the input sequence
        presented them.
    label_a, label_b:
        The two coincident levels' integer labels, in the same order.
    """

    coordinate_mm: tuple
    level_a: str
    level_b: str
    label_a: int
    label_b: int


def find_coincident_centroid_pair(
    centroids: Sequence[LabelCentroid],
) -> Optional[CoincidentCentroidPair]:
    """Return the first pair of exactly-coincident centroids in *centroids*.

    Two centroids are "coincident" when their ``centroid_mm`` values compare
    exactly equal as a 3-tuple of floats -- no tolerance, so two centroids
    that differ by even ``1e-9`` mm are reported as distinct (item 129, AC3).

    Parameters
    ----------
    centroids:
        Sequence of :class:`~segfacet.features.centroids.LabelCentroid`
        objects, in the order to search. The input is never mutated.

    Returns
    -------
    CoincidentCentroidPair or None
        The **first** coincident pair, in the order *centroids* was given
        (item 129, AC2) -- i.e. the first centroid whose coordinate has
        already been seen, paired with the earlier centroid that shares it.
        ``None`` when every mm-coordinate is pairwise distinct (AC3).
        Deterministic: two calls on the same input return equal results.
    """
    seen: dict = {}
    for c in centroids:
        coord = tuple(float(v) for v in c.centroid_mm)
        if coord in seen:
            earlier = seen[coord]
            return CoincidentCentroidPair(
                coordinate_mm=coord,
                level_a=earlier.level_name,
                level_b=c.level_name,
                label_a=earlier.label,
                label_b=c.label,
            )
        seen[coord] = c
    return None


def _validate_weights(weights: Sequence[float], n_points: int) -> np.ndarray:
    """Validate *weights* for :func:`fit_centroid_spline` (item 120, AC2).

    Requires exactly ``n_points`` values, every one finite and strictly
    positive (``make_splprep`` rejects a zero weight, and a negative or NaN
    weight has no meaning here). Raises ``ValueError`` naming the offending
    length or value in a readable, single-line message -- never SciPy's raw
    FITPACK failure text.
    """
    w = np.asarray(weights, dtype=np.float64)
    if w.ndim != 1 or w.shape[0] != n_points:
        raise ValueError(
            f"fit_centroid_spline: weights must have length {n_points} "
            f"(one per centroid), but received length {w.shape[0] if w.ndim == 1 else w.shape}."
        )
    for idx, value in enumerate(w):
        if not math.isfinite(value):
            raise ValueError(
                f"fit_centroid_spline: weights[{idx}] = {value!r} is not "
                f"finite; every weight must be a finite, strictly positive "
                f"number."
            )
        if value <= 0.0:
            raise ValueError(
                f"fit_centroid_spline: weights[{idx}] = {value!r} is not "
                f"strictly positive; every weight must be > 0 "
                f"(make_splprep rejects zero weights)."
            )
    return w


def fit_centroid_spline(
    centroids: Sequence[LabelCentroid],
    degree: int = 3,
    *,
    smoothing: Optional[float] = None,
    u: Optional[Sequence[float]] = None,
    weights: Optional[Sequence[float]] = None,
    backend: Optional[Backend] = None,
) -> SplineFit:
    """Fit a parametric smoothing B-spline through ordered centroid mm-coordinates.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of
        :class:`~segfacet.features.centroids.LabelCentroid` objects.  Physical
        mm-coordinates (``centroid_mm``) are used for the fit.  The input
        sequence is never mutated.
    degree:
        Polynomial degree (default 3, cubic).  Clamped to
        ``min(degree, n_points - 1)`` when the sequence is short so that
        SciPy's ``make_splprep`` always receives a valid ``k`` argument
        (requires ``k < n_points``).  The effective degree is recorded in
        :attr:`SplineFit.degree`.
    smoothing:
        Smoothing factor ``s`` passed to ``make_splprep``.  ``None`` (the
        default) resolves to ``float(n_points)``, per the formulation
        ``docs/spinal-curve-model.md`` records.  ``0.0`` reproduces an
        interpolating fit that passes exactly through every centroid — used
        by ``scripts/compare_curve_candidates.py`` to keep an honest
        interpolating baseline.  The value actually used is recorded in
        :attr:`SplineFit.smoothing`.
    u:
        Optional explicit parameter values (one per centroid) forwarded to
        ``make_splprep(..., u=...)`` instead of letting it compute
        chord-length parameterisation from *centroids* itself. ``None`` (the
        default) reproduces today's chord-length behaviour (item 120,
        AC1). Stored verbatim on the returned :class:`SplineFit`.
    weights:
        Optional per-point weights, forwarded to ``make_splprep(..., w=...)``.
        Must have length ``n_points`` with every value finite and strictly
        positive; validated up front with a readable ``ValueError`` rather
        than SciPy's raw FITPACK message (item 120, AC2). ``None`` (the
        default) reproduces today's uniform-weight behaviour.
    backend:
        Optional :class:`~segfacet.backend.Backend` handle. Accepted for
        signature uniformity and to resolve the auto-detect default (see
        AC3), but the fit itself always runs on host NumPy/SciPy -- see the
        module docstring's "Deliberate CPU fallback" section.

    Returns
    -------
    SplineFit
        Fitted spline representation.

    Raises
    ------
    ValueError
        When fewer than 2 centroids are provided — a single point or zero
        points cannot define a curve. Also raised when two centroids share
        an exactly-coincident mm-coordinate, naming the duplicated
        coordinate and the offending ``level_name``s — ``make_splprep``'s
        own failure on such input is an unreadable multi-line FITPACK
        message (item 119, AC16). Also raised when *weights* has the wrong
        length or contains a non-finite or non-positive value (item 120,
        AC2).
    """
    backend = backend or _backend_mod.get_backend()

    n_points = len(centroids)

    if n_points < 2:
        raise ValueError(
            f"fit_centroid_spline requires at least 2 centroids to define a "
            f"curve, but received {n_points}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    coincident = find_coincident_centroid_pair(centroids)
    if coincident is not None:
        raise ValueError(
            f"fit_centroid_spline received two centroids with exactly the "
            f"same mm-coordinate {coincident.coordinate_mm}: levels "
            f"{coincident.level_a!r} and {coincident.level_b!r}. "
            f"A spline fit requires distinct centroid positions; check the "
            f"input segmentation for duplicated/collapsed labels."
        )

    w = None if weights is None else _validate_weights(weights, n_points)

    # Clamp degree so that k < n_points, as required by make_splprep.
    effective_degree = min(degree, n_points - 1)

    s = float(n_points) if smoothing is None else float(smoothing)

    # Extract mm-coordinates; do not mutate the input sequence.
    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)

    make_splprep_kwargs: dict = {"k": effective_degree, "s": s}
    if u is not None:
        make_splprep_kwargs["u"] = np.asarray([float(v) for v in u], dtype=np.float64)
    if w is not None:
        make_splprep_kwargs["w"] = w

    # Fit the parametric smoothing B-spline. s=0 forces the spline through
    # every input point (interpolating fit); the default s=n_points allows
    # it to smooth over noise/outliers, per docs/spinal-curve-model.md.
    try:
        spl, u_out = make_splprep([x, y, z], **make_splprep_kwargs)
    except ValueError:
        # A defensive fallback for any residual FITPACK failure the pre-check
        # above did not catch (e.g. near-degenerate configurations this
        # module's coincidence check does not enumerate). Re-raise with the
        # same descriptive style rather than swallowing the failure.
        raise ValueError(
            f"fit_centroid_spline failed to fit a spline through {n_points} "
            f"centroids (degree={effective_degree}, smoothing={s}). This "
            f"usually indicates degenerate or duplicated centroid positions."
        )

    return SplineFit(
        spline=spl,
        smoothing=s,
        u=tuple(float(v) for v in u_out),
        degree=effective_degree,
        n_points=n_points,
    )


# --------------------------------------------------------------------------- #
# Evaluation helpers
# --------------------------------------------------------------------------- #


def _marshal_u_values(u_values) -> np.ndarray:
    """Marshal a possibly-device ``u_values`` to host NumPy: prefer a
    CuPy-style ``.get()`` transfer, then fall back to ``np.asarray`` (which
    honours ``__array__`` for any array-like, including plain sequences)."""
    getter = getattr(u_values, "get", None)
    if callable(getter):
        return getter()
    return np.asarray(u_values)


def evaluate_spline(
    fit: SplineFit,
    u_values: Sequence[float],
    *,
    backend: Optional[Backend] = None,
) -> np.ndarray:
    """Evaluate the spline at the supplied parameter values.

    Parameters
    ----------
    fit:
        A :class:`SplineFit` as returned by :func:`fit_centroid_spline`.
    u_values:
        Sequence of parameter values in [0, 1].  Any length N >= 1.  May be a
        host sequence/array, or a device-array-like object (exposing
        ``.get()`` and/or ``__array__``) -- either is marshalled to host
        NumPy before evaluation.
    backend:
        Optional :class:`~segfacet.backend.Backend` handle. Accepted for
        signature uniformity and to resolve the auto-detect default (see
        AC3), but evaluation always runs on host NumPy/SciPy -- see the
        module docstring's "Deliberate CPU fallback" section.

    Returns
    -------
    np.ndarray
        Float64 array of shape ``(N, 3)``.  Column order is (x, y, z) in mm.
        For well-conditioned inputs (parameter values inside [0, 1]) the output
        contains no NaN or Inf values.
    """
    backend = backend or _backend_mod.get_backend()

    host_u_values = _marshal_u_values(u_values)

    # fit.spline is a vector-valued BSpline over 3 output components; calling
    # it returns shape (3, N) -- transpose to this module's (N, 3) contract.
    coords = np.asarray(fit.spline(host_u_values), dtype=np.float64)
    return coords.T


def evaluate_spline_derivative(
    fit: SplineFit,
    u_values: Sequence[float],
    nu: int = 1,
    *,
    backend: Optional[Backend] = None,
) -> np.ndarray:
    """Evaluate the spline's ``nu``-th derivative at the supplied parameter values.

    Parameters
    ----------
    fit:
        A :class:`SplineFit` as returned by :func:`fit_centroid_spline`.
    u_values:
        Sequence of parameter values in [0, 1].  Any length N >= 1.  May be a
        host sequence/array, or a device-array-like object (exposing
        ``.get()`` and/or ``__array__``) -- either is marshalled to host
        NumPy before evaluation.
    nu:
        Order of the derivative (default 1, the tangent).
    backend:
        Optional :class:`~segfacet.backend.Backend` handle. Accepted for
        signature uniformity and to resolve the auto-detect default (see
        AC3), but evaluation always runs on host NumPy/SciPy -- see the
        module docstring's "Deliberate CPU fallback" section.

    Returns
    -------
    np.ndarray
        Float64 array of shape ``(N, 3)``.  Column order is (dx/du, dy/du,
        dz/du) (or higher-order derivatives when ``nu > 1``).
    """
    backend = backend or _backend_mod.get_backend()

    host_u_values = _marshal_u_values(u_values)

    # Same (3, N) -> (N, 3) transpose as evaluate_spline; see its comment.
    derivs = np.asarray(fit.spline(host_u_values, nu=nu), dtype=np.float64)
    return derivs.T


# --------------------------------------------------------------------------- #
# Closest-point search (item 130)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ClosestPointOnCurve:
    """Result of :func:`find_closest_point`.

    Attributes
    ----------
    closest_u:
        The curve parameter, in the closed interval ``[0, 1]``, that
        minimises the distance to the query point.
    point_mm:
        The curve evaluated at ``closest_u``, as a 3-tuple of floats
        ``(x, y, z)`` in mm.
    distance_mm:
        The Euclidean distance (mm) from the query point to ``point_mm``.
        Derived by evaluating the curve at ``closest_u`` rather than read
        from the optimiser's own objective value, so the three fields are
        consistent with each other by construction.
    """

    closest_u: float
    point_mm: tuple
    distance_mm: float


def find_closest_point(
    point_mm,
    curve,
    *,
    n_scan: int = _CLOSEST_POINT_N_SCAN,
    xatol: float = _CLOSEST_POINT_XATOL,
    backend: Optional[Backend] = None,
) -> ClosestPointOnCurve:
    """Find the closest point on *curve* to *point_mm* (item 130).

    The one closest-point search shared by every caller that used to write
    its own copy: :func:`~segfacet.features.spline_offset.compute_spline_offsets`,
    :func:`~segfacet.features.consistency.compute_monotonic_consistency`, and
    ``scripts/compare_curve_candidates.py``.

    Strategy: coarse-scan the curve over ``n_scan`` uniformly-spaced
    parameter values in ``[0, 1]`` to locate an approximate minimum, then
    refine with a bounded ``scipy.optimize.minimize_scalar`` in a bracket one
    coarse step either side of the coarse minimum (clamped to ``[0, 1]``; the
    bracket cannot be degenerate for any ``n_scan >= 2``, but the guard is
    kept for defensiveness). The returned ``point_mm``/``distance_mm`` are
    derived by evaluating *curve* once more at the final, clipped parameter
    -- never read from the optimiser's own objective value -- so the three
    returned fields are mutually consistent by construction.

    Parameters
    ----------
    point_mm:
        The query point, as an array-like of 3 mm-coordinates.
    curve:
        Either a :class:`SplineFit` (evaluated via :func:`evaluate_spline`),
        or a bare callable ``evaluate(u_values) -> (N, 3)`` mapping an array
        of parameter values to mm-coordinates -- the shape every candidate in
        ``scripts/compare_curve_candidates.py`` already exposes, so no
        second copy of the algorithm is needed there.
    n_scan:
        Number of uniformly-spaced parameter values in the coarse scan.
        Must be >= 2. Defaults to :data:`_CLOSEST_POINT_N_SCAN` (500).
    xatol:
        Absolute tolerance passed to ``minimize_scalar``'s ``options``. Must
        be > 0. Defaults to :data:`_CLOSEST_POINT_XATOL` (1e-6).
    backend:
        Optional :class:`~segfacet.backend.Backend` handle, accepted for
        signature uniformity with the other Stage-2/3 feature functions (item
        072). Only used when *curve* is a :class:`SplineFit` (forwarded to
        :func:`evaluate_spline`); the numeric work always runs on host
        NumPy/SciPy regardless -- see the module docstring's "Deliberate CPU
        fallback" section.

    Returns
    -------
    ClosestPointOnCurve
        ``closest_u`` is always in the closed interval ``[0, 1]``.
        Deterministic: two calls with the same *point_mm* and *curve* return
        equal results. Non-mutating: neither *point_mm* nor any array *curve*
        closes over is modified.

    Raises
    ------
    ValueError
        When ``n_scan < 2`` or ``xatol <= 0``, naming the offending
        parameter and its value.
    """
    if n_scan < 2:
        raise ValueError(
            f"find_closest_point: n_scan must be >= 2 (a coarse scan needs at "
            f"least 2 parameter values), but received n_scan={n_scan!r}."
        )
    if xatol <= 0:
        raise ValueError(
            f"find_closest_point: xatol must be > 0, but received xatol={xatol!r}."
        )

    backend = backend or _backend_mod.get_backend()

    if isinstance(curve, SplineFit):
        fit = curve

        def evaluate(u_values):
            return evaluate_spline(fit, u_values, backend=backend)

    else:
        evaluate = curve

    pt = np.asarray(point_mm, dtype=np.float64)

    u_scan = np.linspace(0.0, 1.0, n_scan)
    scan_pts = np.asarray(evaluate(u_scan), dtype=np.float64)
    diffs = scan_pts - pt
    sq_dists = np.einsum("ij,ij->i", diffs, diffs)
    best_idx = int(np.argmin(sq_dists))
    u_coarse = float(u_scan[best_idx])

    # Bracket for refinement: one coarse step each side (clamped to [0, 1]).
    step = 1.0 / (n_scan - 1)
    lo = max(0.0, u_coarse - step)
    hi = min(1.0, u_coarse + step)

    if lo >= hi:
        # Degenerate bracket -- cannot fire for any n_scan >= 2 (see
        # docstring); kept for defensiveness, unchanged from the three prior
        # copies of this algorithm (item 130).
        u_final = u_coarse
    else:

        def _sq_distance(u_scalar: float) -> float:
            eval_pt = np.asarray(evaluate([float(u_scalar)]), dtype=np.float64)[0]
            diff = pt - eval_pt
            return float(np.dot(diff, diff))

        result = minimize_scalar(
            _sq_distance,
            bounds=(lo, hi),
            method="bounded",
            options={"xatol": xatol},
        )
        u_final = float(np.clip(result.x, 0.0, 1.0))

    final_pt = np.asarray(evaluate([u_final]), dtype=np.float64)[0]
    diff = pt - final_pt
    distance = float(math.sqrt(float(np.dot(diff, diff))))

    return ClosestPointOnCurve(
        closest_u=u_final,
        point_mm=(float(final_pt[0]), float(final_pt[1]), float(final_pt[2])),
        distance_mm=distance,
    )
