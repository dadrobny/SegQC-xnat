"""Per-vertebra orientation (PCA) and global spinal curvature descriptors (item 019).

Two related descriptors contribute to spinal geometry:

**Part A — Per-Vertebra Orientation**
    For each label in the instance segmentation map, estimate the principal axis
    direction via PCA of the voxel cloud in mm-space (spacing-aware).  Exposed as
    :class:`VertebralOrientation` and :func:`compute_vertebra_orientations`.

**Part B — Global Curvature Descriptors**
    Given a fitted :class:`~segfacet.features.spline.SplineFit`, compute tangent
    angles along the spline, inter-tangent angles between consecutive centroids,
    and signed, plane-stated curvature sweeps (item 122): a coronal (R-S plane)
    and a sagittal (A-S plane) unwrapped signed tangent-angle array, each
    reduced to a per-plane ``max - min`` sweep, with ``total_curvature_deg``
    the larger of the two and ``curvature_plane`` naming which one.  Both
    signed arrays are computed against tangents normalised to a consistent
    cranial-to-caudal traversal direction, so the sweep is invariant to
    whether the caller supplied centroids cranial-first or caudal-first.  The
    plane statement holds only when centroids are RAS-ordered mm coordinates
    (axis 0 = Right, 1 = Anterior, 2 = Superior), which is guaranteed for any
    volume loaded via :func:`segfacet.io.load_volume`.  Exposed as
    :class:`SpineCurvature` and :func:`compute_spine_curvature`.

Public API
----------
``VertebralOrientation``
    Frozen dataclass for per-vertebra PCA orientation.
``SpineCurvature``
    Frozen dataclass for global curvature descriptors.
``compute_vertebra_orientations(seg_img, labels, convention=None)``
    Compute per-vertebra orientation for a list of labels.
``compute_spine_curvature(fit, centroids)``
    Compute global curvature descriptors along the fitted spline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np
import nibabel as nib
from scipy.interpolate import splev

from segfacet.features.centroids import LabelCentroid
from segfacet.features.spline import SplineFit
from segfacet.labels import LabelConvention

__all__ = [
    "VertebralOrientation",
    "SpineCurvature",
    "compute_vertebra_orientations",
    "compute_spine_curvature",
]


# --------------------------------------------------------------------------- #
# VertebralOrientation dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class VertebralOrientation:
    """Per-vertebra orientation from PCA of the voxel cloud.

    The principal axis is computed in mm-space (voxel coordinates scaled by
    voxel spacing before PCA) so that anisotropic spacings are handled correctly.

    Attributes
    ----------
    label : int
        The integer label value.
    level_name : str
        Anatomical vertebra name from the :class:`~segfacet.labels.LabelConvention`
        (e.g. ``"T8"``, ``"L1"``), or :data:`~segfacet.labels.UNKNOWN` when the
        integer has no mapping.
    principal_axis : Tuple[float, float, float]
        Unit vector (in mm-space) of the first principal component.
        All-zeros ``(0.0, 0.0, 0.0)`` when the label has only a single voxel
        (degenerate — no spatial extent to compute a meaningful axis from).
    eigenvalue_ratio : float
        Ratio of the largest to the second-largest eigenvalue.  High values
        indicate a strongly elongated shape along the principal axis.
        Returns ``0.0`` for degenerate single-voxel labels and ``1.0`` when
        all eigenvalues are equal (spherical blob).
    """

    label: int
    level_name: str
    principal_axis: Tuple[float, float, float]
    eigenvalue_ratio: float


# --------------------------------------------------------------------------- #
# SpineCurvature dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SpineCurvature:
    """Global curvature descriptors along the spinal spline.

    Attributes
    ----------
    tangent_angles_deg : Tuple[float, ...]
        Angle (degrees) of the spline tangent at each input centroid's u value,
        relative to the z-axis (superior-inferior axis).  Length matches the
        number of centroids.
    inter_tangent_angles_deg : Tuple[float, ...]
        Angle (degrees) between consecutive tangent vectors.  Length is
        ``n_centroids - 1``.  Always non-negative.
    total_curvature_deg : float
        The larger of ``coronal_curvature_deg`` and ``sagittal_curvature_deg``
        — the sweep in the anatomical plane the spine turns in most.  ``0.0``
        for a perfectly straight spine.  See ``curvature_plane`` for which
        plane it came from.
    coronal_tangent_angles_deg : Tuple[float, ...]
        Signed tangent angle in the coronal (R-S) plane at each centroid:
        ``degrees(atan2(t_R, t_S))``, unwrapped along the ordered centroid
        sequence and computed from tangents normalised to a cranial-to-caudal
        traversal direction (item 122). Positive means the tangent tilts
        toward the patient's right as the spine advances cranially. Requires
        RAS-ordered mm centroids (axis 0 = Right, 1 = Anterior, 2 = Superior),
        guaranteed by :func:`segfacet.io.load_volume`. Length matches the
        number of centroids.
    sagittal_tangent_angles_deg : Tuple[float, ...]
        Signed tangent angle in the sagittal (A-S) plane at each centroid:
        ``degrees(atan2(t_A, t_S))``, unwrapped and direction-normalised the
        same way as ``coronal_tangent_angles_deg``. Positive means the
        tangent tilts anterior. Same RAS precondition. Length matches the
        number of centroids.
    coronal_curvature_deg : float
        ``max - min`` of ``coronal_tangent_angles_deg`` — the coronal-plane
        sweep. ``0.0`` for a curve confined to the sagittal plane.
    sagittal_curvature_deg : float
        ``max - min`` of ``sagittal_tangent_angles_deg`` — the sagittal-plane
        sweep. ``0.0`` for a curve confined to the coronal plane.
    curvature_plane : str
        ``"coronal"`` when ``coronal_curvature_deg >= sagittal_curvature_deg``,
        else ``"sagittal"``. An exact tie (including a straight spine's
        ``0.0``/``0.0``) resolves to ``"coronal"``.
    """

    tangent_angles_deg: Tuple[float, ...]
    inter_tangent_angles_deg: Tuple[float, ...]
    total_curvature_deg: float
    coronal_tangent_angles_deg: Tuple[float, ...]
    sagittal_tangent_angles_deg: Tuple[float, ...]
    coronal_curvature_deg: float
    sagittal_curvature_deg: float
    curvature_plane: str


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _get_spacing(seg_img: nib.Nifti1Image) -> Tuple[float, float, float]:
    """Extract (sx, sy, sz) voxel spacings in mm from a NiBabel image."""
    zooms = seg_img.header.get_zooms()
    return float(zooms[0]), float(zooms[1]), float(zooms[2])


def _pca_principal_axis(
    coords_mm: np.ndarray,
) -> Tuple[Tuple[float, float, float], float]:
    """Compute the first principal component and eigenvalue ratio for a point cloud.

    Parameters
    ----------
    coords_mm:
        Array of shape ``(N, 3)`` of mm-space coordinates, already centred at
        the mean.  N must be >= 2.

    Returns
    -------
    principal_axis:
        Unit vector (3-tuple) of the first principal component (eigenvector with
        the largest eigenvalue).
    eigenvalue_ratio:
        Ratio of the largest to the second-largest eigenvalue.
    """
    # 3×3 covariance matrix; rowvar=False treats each row as an observation.
    cov = np.cov(coords_mm, rowvar=False)  # shape (3, 3)

    # np.linalg.eigh returns eigenvalues in *ascending* order.
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # The principal axis is the eigenvector with the *largest* eigenvalue (last).
    axis = eigenvectors[:, -1]  # shape (3,)

    # Normalise to a unit vector (eigh already returns orthonormal eigenvectors,
    # but clamp numerical noise).
    norm = float(np.linalg.norm(axis))
    if norm > 1e-12:
        axis = axis / norm

    # eigenvalue_ratio: largest / second-largest.
    ev_sorted = eigenvalues  # ascending order from eigh
    lambda_max = float(ev_sorted[-1])
    lambda_second = float(ev_sorted[-2])

    if lambda_second > 1e-12:
        ratio = float(lambda_max / lambda_second)
    elif lambda_max > 1e-12:
        # Second eigenvalue is zero but largest is not — degenerate flat cloud.
        ratio = float("inf")
    else:
        ratio = 0.0

    axis_tuple: Tuple[float, float, float] = (
        float(axis[0]),
        float(axis[1]),
        float(axis[2]),
    )
    return axis_tuple, ratio


def _angle_to_z_axis_deg(tangent: np.ndarray) -> float:
    """Angle in degrees between *tangent* (a 3-D vector) and the z-axis (0,0,1).

    Returns a value in [0, 180].  For a zero-length tangent returns 0.0.
    """
    norm = float(np.linalg.norm(tangent))
    if norm < 1e-12:
        return 0.0
    t_unit = tangent / norm
    # Dot with (0, 0, 1) is just the z-component.
    cos_theta = float(np.clip(t_unit[2], -1.0, 1.0))
    return math.degrees(math.acos(cos_theta))


def _angle_between_unit_vectors_deg(a: np.ndarray, b: np.ndarray) -> float:
    """Angle in degrees between two 3-D unit vectors a and b.

    Always non-negative; handles near-zero norms gracefully.
    """
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    cos_theta = float(np.clip(np.dot(a / na, b / nb), -1.0, 1.0))
    return math.degrees(math.acos(cos_theta))


def _signed_plane_angles_deg(unit_tangents: np.ndarray, axis: int) -> np.ndarray:
    """Unwrapped signed in-plane tangent angle (degrees), one per row.

    ``axis`` selects the in-plane component (0 = R for coronal, 1 = A for
    sagittal); axis 2 (S) is always the reference. Returns
    ``degrees(atan2(t[:, axis], t[:, 2]))``, unwrapped along the row order so
    a tangent crossing the −S direction does not produce a ±360° discontinuity
    (item 122).
    """
    raw = np.arctan2(unit_tangents[:, axis], unit_tangents[:, 2])
    return np.degrees(np.unwrap(raw))


def _sweep(angles: np.ndarray) -> float:
    """``max - min`` of *angles*; ``0.0`` for a single-element (or empty) array."""
    if len(angles) < 2:
        return 0.0
    return float(np.max(angles) - np.min(angles))


# --------------------------------------------------------------------------- #
# Public compute functions
# --------------------------------------------------------------------------- #


def compute_vertebra_orientations(
    seg_img: nib.Nifti1Image,
    labels: Sequence[int],
    convention: Optional[LabelConvention] = None,
) -> List[VertebralOrientation]:
    """Compute per-vertebra orientation for each label in *labels*.

    PCA is performed in mm-space (voxel coordinates scaled by voxel spacing)
    to handle anisotropic spacings correctly.

    Parameters
    ----------
    seg_img:
        A NiBabel ``Nifti1Image`` carrying an integer instance label map.  The
        header's voxel dimensions (``get_zooms()``) are used for mm-space scaling.
    labels:
        Sequence of integer label values to process.  The returned list is in
        the same order as *labels*.  Must be non-empty.
    convention:
        Optional :class:`~segfacet.labels.LabelConvention` for anatomical level
        names.  Defaults to :meth:`LabelConvention.default()`.

    Returns
    -------
    List[VertebralOrientation]
        One record per label, in the same order as *labels*.

    Raises
    ------
    ValueError
        If *labels* is empty.
    """
    if len(labels) == 0:
        raise ValueError(
            "compute_vertebra_orientations requires at least one label, "
            "but received an empty sequence."
        )

    if convention is None:
        convention = LabelConvention.default()

    # Read data without copying — we never write to it.
    data = np.asanyarray(seg_img.dataobj)
    sx, sy, sz = _get_spacing(seg_img)

    results: List[VertebralOrientation] = []

    for label in labels:
        level_name: str = convention.name_of(int(label))

        # All voxel coordinates for this label; shape (N, 3).
        coords = np.argwhere(data == label).astype(np.float64)
        n_voxels = coords.shape[0]

        if n_voxels <= 1:
            # Degenerate: single voxel (or label absent) — return zero sentinel.
            results.append(
                VertebralOrientation(
                    label=int(label),
                    level_name=level_name,
                    principal_axis=(0.0, 0.0, 0.0),
                    eigenvalue_ratio=0.0,
                )
            )
            continue

        # Scale to mm-space.
        coords[:, 0] *= sx
        coords[:, 1] *= sy
        coords[:, 2] *= sz

        # Centre the cloud at its mean.
        coords -= coords.mean(axis=0)

        # PCA via covariance + eigh.
        axis_tuple, ratio = _pca_principal_axis(coords)

        results.append(
            VertebralOrientation(
                label=int(label),
                level_name=level_name,
                principal_axis=axis_tuple,
                eigenvalue_ratio=float(ratio),
            )
        )

    return results


def compute_spine_curvature(
    fit: SplineFit,
    centroids: Sequence[LabelCentroid],
) -> SpineCurvature:
    """Compute global curvature descriptors along the fitted spline.

    The spline is evaluated at each centroid's stored parameter value (*u*) using
    ``scipy.interpolate.splev`` with ``der=1`` to obtain tangent vectors.

    Parameters
    ----------
    fit:
        The fitted spline (from :func:`~segfacet.features.spline.fit_centroid_spline`).
    centroids:
        Ordered centroids; their parameter values come from ``fit.u``.  Must
        contain at least 2 entries.

    Returns
    -------
    SpineCurvature

    Raises
    ------
    ValueError
        If *centroids* has fewer than 2 entries.
    """
    n = len(centroids)
    if n < 2:
        raise ValueError(
            f"compute_spine_curvature requires at least 2 centroids to compute "
            f"inter-tangent angles, but received {n}. "
            f"Supply at least 2 LabelCentroid objects."
        )

    # Use the parameter values stored in the SplineFit — one per input centroid.
    # fit.u has the same length as the centroids used to build the spline.
    # We evaluate at those same u values regardless of the centroid count passed
    # here; if centroids is a subset we need their individual u positions.
    # Strategy: use the index of each centroid in the original sequence to look
    # up the stored u value, falling back to evaluating at evenly-spaced u values
    # if the centroid count differs from fit.n_points.
    if n == fit.n_points:
        u_vals = list(fit.u)
    else:
        # Centroids is a different-length sequence (e.g. a subset call from tests).
        # Re-parameterise by chord-length to obtain a sensible set of u values.
        pts = np.array(
            [[float(c.centroid_mm[0]), float(c.centroid_mm[1]), float(c.centroid_mm[2])]
             for c in centroids],
            dtype=np.float64,
        )
        diffs = np.diff(pts, axis=0)
        chord_lengths = np.linalg.norm(diffs, axis=1)
        cumulative = np.concatenate([[0.0], np.cumsum(chord_lengths)])
        total = cumulative[-1]
        if total < 1e-12:
            # All points coincide — use evenly-spaced u.
            u_vals = list(np.linspace(0.0, 1.0, n))
        else:
            u_vals = list(cumulative / total)

    # Evaluate first derivative (tangent) at each u value.
    u_array = np.asarray(u_vals, dtype=np.float64)
    derivs = splev(u_array, fit.tck, der=1)
    # derivs is [dx/du_array, dy/du_array, dz/du_array], each of length n.
    tangents = np.column_stack(
        [np.asarray(derivs[0]), np.asarray(derivs[1]), np.asarray(derivs[2])]
    ).astype(np.float64)  # shape (n, 3)

    # Normalise each tangent vector.
    norms = np.linalg.norm(tangents, axis=1, keepdims=True)  # (n, 1)
    # Avoid division by zero for any degenerate tangents.
    norms = np.where(norms < 1e-12, 1.0, norms)
    unit_tangents = tangents / norms  # (n, 3)

    # Angle of each tangent relative to the z-axis.
    tangent_angles_deg: Tuple[float, ...] = tuple(
        _angle_to_z_axis_deg(unit_tangents[i]) for i in range(n)
    )

    # Inter-tangent angles between consecutive tangent vectors.
    inter_tangent_angles_deg: Tuple[float, ...] = tuple(
        _angle_between_unit_vectors_deg(unit_tangents[i], unit_tangents[i + 1])
        for i in range(n - 1)
    )

    # Direction normalisation (item 122): the signed angles below are measured
    # against +S, so a cranial-first (caudally-advancing) sequence would read
    # every tangent near +/-180 degrees. Negate tangents when the net advance
    # (last centroid's S minus first's) is caudal, so the descriptor measures
    # tilt relative to the cranio-caudal axis regardless of traversal order.
    # This normalised copy feeds only the new signed arrays below;
    # tangent_angles_deg and inter_tangent_angles_deg above are unaffected
    # (both are already invariant to a global tangent sign flip).
    net_advance_s = float(centroids[-1].centroid_mm[2]) - float(centroids[0].centroid_mm[2])
    if net_advance_s < 0:
        normalised_tangents = -unit_tangents
    else:
        normalised_tangents = unit_tangents

    coronal_tangent_angles = _signed_plane_angles_deg(normalised_tangents, axis=0)
    sagittal_tangent_angles = _signed_plane_angles_deg(normalised_tangents, axis=1)

    coronal_tangent_angles_deg: Tuple[float, ...] = tuple(
        float(v) for v in coronal_tangent_angles
    )
    sagittal_tangent_angles_deg: Tuple[float, ...] = tuple(
        float(v) for v in sagittal_tangent_angles
    )

    coronal_curvature_deg = _sweep(coronal_tangent_angles)
    sagittal_curvature_deg = _sweep(sagittal_tangent_angles)

    total_curvature_deg = max(coronal_curvature_deg, sagittal_curvature_deg)
    curvature_plane = "coronal" if coronal_curvature_deg >= sagittal_curvature_deg else "sagittal"

    return SpineCurvature(
        tangent_angles_deg=tangent_angles_deg,
        inter_tangent_angles_deg=inter_tangent_angles_deg,
        total_curvature_deg=total_curvature_deg,
        coronal_tangent_angles_deg=coronal_tangent_angles_deg,
        sagittal_tangent_angles_deg=sagittal_tangent_angles_deg,
        coronal_curvature_deg=coronal_curvature_deg,
        sagittal_curvature_deg=sagittal_curvature_deg,
        curvature_plane=curvature_plane,
    )
