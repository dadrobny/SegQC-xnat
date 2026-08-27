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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np
from scipy.interpolate import BSpline, make_splprep

import segfacet.backend as _backend_mod
from segfacet.backend import Backend
from segfacet.features.centroids import LabelCentroid

__all__ = [
    "SplineFit",
    "fit_centroid_spline",
    "evaluate_spline",
    "evaluate_spline_derivative",
]


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


def _find_coincident_pair(centroids: Sequence[LabelCentroid]):
    """Return ``(coord, level_a, level_b)`` for the first pair of exactly
    coincident mm-coordinates in *centroids*, or ``None`` if none exist."""
    seen = {}
    for c in centroids:
        coord = tuple(float(v) for v in c.centroid_mm)
        if coord in seen:
            return coord, seen[coord], c.level_name
        seen[coord] = c.level_name
    return None


def fit_centroid_spline(
    centroids: Sequence[LabelCentroid],
    degree: int = 3,
    *,
    smoothing: Optional[float] = None,
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
        message (item 119, AC16).
    """
    backend = backend or _backend_mod.get_backend()

    n_points = len(centroids)

    if n_points < 2:
        raise ValueError(
            f"fit_centroid_spline requires at least 2 centroids to define a "
            f"curve, but received {n_points}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    coincident = _find_coincident_pair(centroids)
    if coincident is not None:
        coord, level_a, level_b = coincident
        raise ValueError(
            f"fit_centroid_spline received two centroids with exactly the "
            f"same mm-coordinate {coord}: levels {level_a!r} and {level_b!r}. "
            f"A spline fit requires distinct centroid positions; check the "
            f"input segmentation for duplicated/collapsed labels."
        )

    # Clamp degree so that k < n_points, as required by make_splprep.
    effective_degree = min(degree, n_points - 1)

    s = float(n_points) if smoothing is None else float(smoothing)

    # Extract mm-coordinates; do not mutate the input sequence.
    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)

    # Fit the parametric smoothing B-spline. s=0 forces the spline through
    # every input point (interpolating fit); the default s=n_points allows
    # it to smooth over noise/outliers, per docs/spinal-curve-model.md.
    try:
        spl, u = make_splprep([x, y, z], k=effective_degree, s=s)
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
        u=tuple(float(v) for v in u),
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
