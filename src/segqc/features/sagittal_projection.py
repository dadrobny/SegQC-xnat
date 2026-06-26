"""Sagittal projection of vertebra centroids and fitted spline (item 021).

Renders an optional 2-D sagittal projection (x–z plane, left–right vs.
superior–inferior) of the vertebra centroids and the parametric spline fit
(item 017) for inclusion in the human-readable report (item 010).

Matplotlib is an **optional soft dependency**: all imports are guarded inside
the function body so that ``import segqc`` never fails on headless servers
without a display.  When matplotlib is not available, or when the Agg backend
cannot be initialised, the function returns ``None`` without raising.

Public API
----------
``render_sagittal_projection(centroids, spline_fit, output_path, *, n_spline_points=200, dpi=150)``
    Render a 2-D sagittal projection of centroids and the spline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np

from segqc.features.centroids import LabelCentroid
from segqc.features.spline import SplineFit, evaluate_spline

__all__ = ["render_sagittal_projection"]


def render_sagittal_projection(
    centroids: Sequence[LabelCentroid],
    spline_fit: SplineFit,
    output_path: Union[str, Path],
    *,
    n_spline_points: int = 200,
    dpi: int = 150,
) -> Optional[Path]:
    """Render a 2-D sagittal projection of centroids and the spline.

    Projects each centroid onto the sagittal plane (x–z view, where x is the
    left–right axis and z is the superior–inferior axis, both in mm).  The
    fitted spline is sampled at ``n_spline_points`` and overlaid as a curve.
    Each centroid is annotated with its ``level_name`` (e.g. ``"T8"``).

    The figure is saved as a PNG to ``output_path`` using the Agg (headless)
    backend.  The y-axis is inverted so that superior (smaller z in NIfTI
    convention) appears at the top of the plot.

    Axis convention
    ---------------
    * Horizontal axis: x (mm) — left–right.
    * Vertical axis: z (mm), *inverted* — superior up, inferior down.

    Single-centroid behaviour
    -------------------------
    A sequence of exactly one centroid raises ``ValueError`` because a single
    point cannot define a curve.  Guard against this upstream.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects (item 013).
    spline_fit:
        Fitted spline through the centroids (item 017).
    output_path:
        Destination file path for the PNG image.  The parent directory must
        already exist.  The file is overwritten if it already exists.
    n_spline_points:
        Number of parameter values at which to sample the spline for the
        curve overlay (default 200).
    dpi:
        Resolution of the saved figure in dots per inch (default 150).

    Returns
    -------
    Path
        Absolute path of the written PNG file, as a :class:`pathlib.Path`.
    None
        When matplotlib is unavailable or the backend cannot be initialised;
        the function returns ``None`` without raising.

    Raises
    ------
    ValueError
        When ``centroids`` is empty, or when ``centroids`` contains exactly one
        centroid (a single point cannot define a spinal curve).
    """
    # Validate inputs *before* attempting any matplotlib import so that
    # programmer errors always raise immediately — regardless of backend status.
    n = len(centroids)
    if n == 0:
        raise ValueError(
            "render_sagittal_projection requires at least 2 centroids, "
            "but received an empty sequence. "
            "Supply at least 2 LabelCentroid objects."
        )
    if n == 1:
        raise ValueError(
            "render_sagittal_projection requires at least 2 centroids to "
            "define a spinal curve, but received exactly 1 centroid "
            f"({centroids[0].level_name!r}). "
            "Supply at least 2 LabelCentroid objects."
        )

    # Guard all matplotlib imports inside a try/except so that a missing or
    # broken matplotlib installation returns None instead of crashing.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    output_path = Path(output_path)

    try:
        # Extract sagittal-plane coordinates (x=index 0, z=index 2) from
        # each centroid; do not mutate the input list.
        x_pts = np.array([float(c.centroid_mm[0]) for c in centroids], dtype=np.float64)
        z_pts = np.array([float(c.centroid_mm[2]) for c in centroids], dtype=np.float64)

        # Sample the spline for the smooth curve overlay.
        u_vals = np.linspace(0.0, 1.0, n_spline_points)
        spline_coords = evaluate_spline(spline_fit, u_vals)  # (n_spline_points, 3)
        x_spline = spline_coords[:, 0]
        z_spline = spline_coords[:, 2]

        fig, ax = plt.subplots(figsize=(6, 8))

        # Draw the smooth spline curve.
        ax.plot(x_spline, z_spline, color="steelblue", linewidth=1.5,
                label="Spline fit", zorder=1)

        # Scatter centroid markers.
        ax.scatter(x_pts, z_pts, color="crimson", s=40, zorder=2,
                   label="Centroids")

        # Annotate each centroid with its level name.
        for c, x_mm, z_mm in zip(centroids, x_pts, z_pts):
            ax.annotate(
                c.level_name,
                xy=(x_mm, z_mm),
                xytext=(4, 0),
                textcoords="offset points",
                fontsize=7,
                va="center",
            )

        # Invert y-axis so superior (smaller z in NIfTI convention) is at top.
        ax.invert_yaxis()

        ax.set_xlabel("x (mm) — left–right")
        ax.set_ylabel("z (mm) — superior–inferior (inverted: superior up)")
        ax.set_title("Sagittal projection of vertebra centroids and spline")
        ax.legend(fontsize=8)

        plt.tight_layout()
        plt.savefig(output_path, dpi=dpi, format="png")
        plt.close(fig)

    except Exception:
        # Any rendering or save failure is treated as a graceful degradation —
        # close the figure if it was created, then return None.
        try:
            plt.close("all")
        except Exception:
            pass
        return None

    return output_path
