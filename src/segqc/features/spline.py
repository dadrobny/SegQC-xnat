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
``fit_centroid_spline(centroids, degree=3) -> SplineFit``
    Fit a parametric B-spline through the ordered centroid mm-coordinates.
``evaluate_spline(fit, u_values) -> np.ndarray``
    Evaluate the spline at the supplied parameter values; returns ``(N, 3)``
    float64 array of (x, y, z) mm-coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

import numpy as np
from scipy.interpolate import splev, splprep

from segqc.features.centroids import LabelCentroid

__all__ = [
    "SplineFit",
    "fit_centroid_spline",
    "evaluate_spline",
]


# --------------------------------------------------------------------------- #
# SplineFit dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SplineFit:
    """Parametric spline through ordered vertebra centroids.

    Attributes
    ----------
    tck:
        The SciPy ``(t, c, k)`` B-spline representation as returned by
        ``scipy.interpolate.splprep``.  ``t`` — knot vector, ``c`` — B-spline
        coefficients, ``k`` — degree.
    u:
        Parameter values (0..1) at which the input centroids lie on the fitted
        spline, stored as a tuple of floats.  Length equals ``n_points``.
    degree:
        Polynomial degree used for the fit (may be less than the requested
        degree when the sequence is short — see :func:`fit_centroid_spline`).
    n_points:
        Number of input centroids used to fit the spline.
    """

    tck: tuple        # (t, c, k) from scipy splprep
    u: tuple          # parameter values for input points, length == n_points
    degree: int
    n_points: int


# --------------------------------------------------------------------------- #
# Core fitting function
# --------------------------------------------------------------------------- #


def fit_centroid_spline(
    centroids: Sequence[LabelCentroid],
    degree: int = 3,
) -> SplineFit:
    """Fit a parametric B-spline through the ordered centroid mm-coordinates.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of
        :class:`~segqc.features.centroids.LabelCentroid` objects.  Physical
        mm-coordinates (``centroid_mm``) are used for the fit.  The input
        sequence is never mutated.
    degree:
        Polynomial degree (default 3, cubic).  Clamped to
        ``min(degree, n_points - 1)`` when the sequence is short so that SciPy's
        ``splprep`` always receives a valid ``k`` argument (requires
        ``k < n_points``).  The effective degree is recorded in
        :attr:`SplineFit.degree`.

    Returns
    -------
    SplineFit
        Fitted spline representation.

    Raises
    ------
    ValueError
        When fewer than 2 centroids are provided — a single point or zero points
        cannot define a curve.  The message states the received count and the
        minimum requirement.
    """
    n_points = len(centroids)

    if n_points < 2:
        raise ValueError(
            f"fit_centroid_spline requires at least 2 centroids to define a "
            f"curve, but received {n_points}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    # Clamp degree so that k < n_points, as required by splprep.
    effective_degree = min(degree, n_points - 1)

    # Extract mm-coordinates; do not mutate the input sequence.
    x = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
    y = np.array([float(c.centroid_mm[1]) for c in centroids], dtype=np.float64)
    z = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)

    # Fit the parametric B-spline.  s=0 forces the spline through every input
    # point (interpolating spline), satisfying AC1 (within-tolerance pass-through).
    tck, u = splprep([x, y, z], k=effective_degree, s=0)

    return SplineFit(
        tck=tck,
        u=tuple(float(v) for v in u),
        degree=effective_degree,
        n_points=n_points,
    )


# --------------------------------------------------------------------------- #
# Evaluation helper
# --------------------------------------------------------------------------- #


def evaluate_spline(fit: SplineFit, u_values: Sequence[float]) -> np.ndarray:
    """Evaluate the spline at the supplied parameter values.

    Parameters
    ----------
    fit:
        A :class:`SplineFit` as returned by :func:`fit_centroid_spline`.
    u_values:
        Sequence of parameter values in [0, 1].  Any length N >= 1.

    Returns
    -------
    np.ndarray
        Float64 array of shape ``(N, 3)``.  Column order is (x, y, z) in mm.
        For well-conditioned inputs (parameter values inside [0, 1]) the output
        contains no NaN or Inf values.
    """
    coords = splev(u_values, fit.tck)
    # splev returns a list of three arrays [x_arr, y_arr, z_arr]; stack to (N, 3)
    return np.column_stack([np.asarray(c, dtype=np.float64) for c in coords])
