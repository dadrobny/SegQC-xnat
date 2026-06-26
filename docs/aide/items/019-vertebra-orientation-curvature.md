# Item 019 — Vertebra Orientation/Rotation & Global Curvature Descriptors

> **Status:** 📋 Planned · **Created:** 2026-06-26
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 019
> **Objectives:** Per-vertebra orientation (PCA of label voxel cloud) + global
> curvature descriptors along the spline (local tangent angles, total curvature /
> Cobb-like angle proxy); feeds the heuristic rule engine (Stage 4).
> **Suggested branch:** `aide/019-vertebra-orientation-curvature`

---

## Description

Two related descriptors contribute to spinal geometry:

### Part A — Per-Vertebra Orientation

For each label in the instance segmentation map, estimate the **principal axis
direction** of the vertebra's voxel cloud via **Principal Component Analysis (PCA)**:

1. Collect all voxel coordinates for the label.
2. Subtract the centroid to centre the cloud.
3. Compute the covariance matrix (or use SVD on the centred coordinate matrix).
4. The **first principal component** (eigenvector with largest eigenvalue) is the
   principal axis direction.

The principal axis is returned as a **unit vector** in mm-space (multiply voxel
coordinate differences by the voxel spacing before PCA so that anisotropic
spacings are accounted for correctly).

**Sign ambiguity**: eigenvectors are defined up to sign; the implementation should
orient the principal axis consistently (e.g., always point in the positive z
direction, or return both eigenvectors and document the convention), and tests must
account for the ±1 sign ambiguity when asserting angular tolerance.

**Degenerate inputs**: a single-voxel label has no spatial extent — the covariance
matrix is all-zeros. In this case the function should return a zero vector (or an
`(0, 0, 0)` axis) and document this degenerate behaviour; it must not crash.

### Part B — Global Curvature Descriptors

Given a fitted `SplineFit` (item 017) compute curvature descriptors along the
spinal curve:

- **Local tangent angle at each input centroid**: the angle (in degrees) of the
  spline tangent vector at each centroid's parameter value `u` relative to a fixed
  reference direction (e.g. the superior-inferior / z axis).
- **Total curvature** (Cobb-like proxy): the maximum difference in tangent angle
  between any two centroids along the spine — a scalar (degrees) that is 0° for a
  perfectly straight spine and grows with curvature.
- **Inter-tangent angles**: the angle (in degrees) between consecutive tangent
  vectors along the curve.

### Public API

Expose results as two dataclasses and two compute functions in
`segqc/features/orientation.py`:

```python
@dataclass(frozen=True)
class VertebralOrientation:
    """Per-vertebra orientation from PCA of the voxel cloud.

    Attributes
    ----------
    label : int
    level_name : str
    principal_axis : Tuple[float, float, float]
        Unit vector (in mm-space) of the first principal component.
        All-zeros when the label has only a single voxel.
    eigenvalue_ratio : float
        Ratio of largest to second-largest eigenvalue (or 0.0 for degenerate).
        High ratio → strongly elongated along the principal axis.
    """
    label: int
    level_name: str
    principal_axis: Tuple[float, float, float]
    eigenvalue_ratio: float


def compute_vertebra_orientations(
    seg_img: nib.Nifti1Image,
    labels: Sequence[int],
    convention: Optional[LabelConvention] = None,
) -> List[VertebralOrientation]:
    """Compute per-vertebra orientation for each label in labels.

    Returns one VertebralOrientation per label, in the same order as labels.

    Raises
    ------
    ValueError
        If labels is empty.
    """


@dataclass(frozen=True)
class SpineCurvature:
    """Global curvature descriptors along the spinal spline.

    Attributes
    ----------
    tangent_angles_deg : Tuple[float, ...]
        Angle (degrees) of the spline tangent at each input centroid's u value,
        relative to the z-axis (or a reference direction).  Length matches the
        number of centroids.
    inter_tangent_angles_deg : Tuple[float, ...]
        Angle (degrees) between consecutive tangent vectors.  Length is
        n_centroids - 1.
    total_curvature_deg : float
        Maximum tangent-angle difference along the spine (Cobb-like proxy).
        0.0 for a straight spine.
    """
    tangent_angles_deg: Tuple[float, ...]
    inter_tangent_angles_deg: Tuple[float, ...]
    total_curvature_deg: float


def compute_spine_curvature(
    fit: SplineFit,
    centroids: Sequence[LabelCentroid],
) -> SpineCurvature:
    """Compute global curvature descriptors along the fitted spline.

    Parameters
    ----------
    fit : SplineFit
        The fitted spline (from item 017).
    centroids : Sequence[LabelCentroid]
        Ordered centroids; their SplineFit.u parameter values are used to
        evaluate tangent directions.

    Returns
    -------
    SpineCurvature

    Raises
    ------
    ValueError
        If centroids has fewer than 2 entries (cannot compute inter-tangent angles).
    """
```

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Spline fitting | Item 017 (`fit_centroid_spline`, `SplineFit`) |
| Per-vertebra offset from spline | Item 018 |
| Neighbour-consistency | Item 020 |
| Stage 3 JSON serialisation | Item 022 |

---

## Acceptance Criteria

- [ ] **AC1: Correct principal axis for an elongated, axis-aligned block**: for a
      synthetic label that is elongated along the z-axis (e.g. 1×1×20 voxels),
      `principal_axis` is parallel (within **5°**) to the z unit vector `(0,0,1)`,
      accounting for ±1 sign ambiguity (i.e. the absolute-value dot product with
      `(0,0,1)` is ≥ cos(5°) ≈ 0.9962).

- [ ] **AC2: Correct principal axis for a rotated elongated block**: for a synthetic
      label elongated along a known diagonal direction (e.g. a block where voxels
      lie along the x+z diagonal), the recovered principal axis is within **10°**
      of the expected direction (accounting for sign ambiguity).

- [ ] **AC3: Spacing-awareness**: when voxel spacing is anisotropic (e.g. `(1, 1, 3)` mm),
      the principal axis is computed in **mm-space** (spacing applied before PCA),
      so a block that is elongated in voxel space by 10 voxels in z but only 4 in x
      has its principal axis accurately reflecting the physical mm extent.

- [ ] **AC4: Degenerate single-voxel label does not crash**: calling
      `compute_vertebra_orientations` on a label with exactly one voxel returns a
      `VertebralOrientation` with `principal_axis == (0.0, 0.0, 0.0)` (or clearly
      documented degenerate sentinel) and does not raise any exception.

- [ ] **AC5: Total curvature is 0° for a straight spine**: for centroids that lie
      exactly on a straight line (zero curvature), `total_curvature_deg < 1.0°`.

- [ ] **AC6: Total curvature is large for a clearly curved spine**: for centroids
      arranged in a pronounced curve (e.g. C-curve spanning 30° of tangent rotation),
      `total_curvature_deg ≥ 20.0°`.

- [ ] **AC7: `inter_tangent_angles_deg` length is `n_centroids − 1`**: the number
      of inter-tangent angles equals the number of centroids minus one.

- [ ] **AC8: Determinism**: calling both `compute_vertebra_orientations` and
      `compute_spine_curvature` twice with identical inputs returns equal results.

- [ ] **AC9: Empty labels raises ValueError**: `compute_vertebra_orientations` with
      an empty labels sequence raises `ValueError` with a non-empty message.

- [ ] **AC10: Too-few centroids raises ValueError**: `compute_spine_curvature` with
      fewer than 2 centroids raises `ValueError` with a non-empty message.

---

## Implementation Steps

1. **Create `src/segqc/features/orientation.py`**:
   - `VertebralOrientation` — frozen dataclass with four fields above.
   - `compute_vertebra_orientations(seg_img, labels, convention=None)`:
     - Validate: raise `ValueError` if `labels` is empty.
     - For each label:
       - Extract voxel coordinates with `np.argwhere(data == label)`.
       - If only 1 voxel, return degenerate sentinel `(0, 0, 0)` with
         `eigenvalue_ratio=0.0`.
       - Subtract centroid, scale by spacing (mm-space), compute SVD or
         covariance + `np.linalg.eigh`.
       - Record the first principal component (largest eigenvalue's eigenvector).
       - Compute `eigenvalue_ratio = eigenvalues[-1] / eigenvalues[-2]` (or 0.0
         if degenerate).
     - Return list in same order as `labels`.
   - `SpineCurvature` — frozen dataclass with three fields above.
   - `compute_spine_curvature(fit, centroids)`:
     - Validate: raise `ValueError` if fewer than 2 centroids.
     - Evaluate spline first-derivative at each centroid's `u` value
       (`scipy.interpolate.splev(u, tck, der=1)`).
     - Normalise each tangent vector.
     - Compute angle vs reference direction (z-axis) for each tangent.
     - Compute inter-tangent angles between consecutive tangents.
     - `total_curvature_deg` = max tangent angle minus min tangent angle
       (or max pairwise tangent difference).
     - Return `SpineCurvature`.

2. **Export** from `segqc/features/__init__.py` (consistent with siblings).

---

## Testing Strategy

- **Framework:** `pytest` (no external services).
- **Unit tests** (`tests/test_019_vertebra_orientation_curvature.py`): all ten ACs;
  adversarial inputs (single-voxel label, spherical blob, anisotropic spacing,
  elongated blocks along each axis and diagonals, straight vs curved centroids,
  sign-ambiguity assertion pattern, determinism, degenerate errors).
- **Fixtures**: NiBabel `Nifti1Image` built inline from synthetic label arrays
  (same style as item 011 geometry tests); `SplineFit` / `LabelCentroid` objects
  constructed inline (same style as items 017/018).

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 013 (`LabelCentroid`)
  - Item 014 (`SpineRelationships` — ordered centroid sequence)
  - Item 017 (`SplineFit`, `fit_centroid_spline`, `evaluate_spline`)
  - NumPy (`np.linalg.eigh` / SVD)
  - SciPy (`scipy.interpolate.splev` with `der=1` for tangent evaluation)
  - NiBabel
- **Downstream:** Item 022 (Stage 3 serialisation).

---

## Decisions & Trade-offs

1. **PCA in mm-space**: voxel coordinates are scaled by voxel spacing before
   PCA so that anisotropic spacings are handled correctly (AC3). This is the
   right approach for any physically meaningful orientation estimate.

2. **SVD vs covariance `eigh`**: both are equivalent for centred clouds.
   `np.linalg.svd` on the `(N, 3)` centred array is numerically well-behaved;
   `np.linalg.eigh` on the `3×3` covariance matrix is faster for small N. Either
   is acceptable; the spec does not constrain the choice.

3. **Sign ambiguity**: eigenvectors are defined up to sign. The implementation
   should pick a canonical orientation (e.g. flip so that the axis always points
   toward positive z), or simply document the ambiguity. Tests use
   `abs(dot(axis, reference)) >= threshold` to avoid false failures.

4. **Degenerate single-voxel**: returning `(0, 0, 0)` is the safest sentinel
   (no undefined behaviour, obvious to downstream consumers). `eigenvalue_ratio`
   is set to `0.0`.

5. **Curvature reference direction**: z-axis `(0, 0, 1)` is the natural
   superior-inferior axis in standard NIfTI orientation. `tangent_angles_deg`
   is the angle between the spline tangent and this axis.

6. **`total_curvature_deg`**: defined as max–min of tangent angles (i.e. the
   range of the tangent angle array). This is a Cobb-like proxy — not identical
   to the clinical Cobb angle but serves as a continuous, differentiable
   curvature measure for the heuristic engine.

7. **`inter_tangent_angles_deg`**: angle between successive tangent vectors
   (cosine formula), in degrees. Always non-negative.

8. **Implementation choice — `np.linalg.eigh` on 3×3 covariance**: The
   covariance matrix is assembled via `np.cov(coords_mm, rowvar=False)` on the
   centred, mm-scaled voxel coordinate array.  `eigh` (symmetric-matrix
   specialisation of `eig`) returns eigenvalues in ascending order, so the
   principal axis is `eigenvectors[:, -1]` and the eigenvalue ratio is
   `eigenvalues[-1] / eigenvalues[-2]`.  When the second eigenvalue is ≤ 1e-12
   but the largest is positive (flat/line degenerate) the ratio is returned as
   `inf`; when all eigenvalues are near-zero (single-voxel guard is earlier, so
   this rarely fires) it falls back to `0.0`.

9. **`u` values for curvature evaluation**: `SplineFit.u` stores one parameter
   value per input centroid.  When `len(centroids) == fit.n_points` the stored
   values are used directly.  When a subset is passed (test-only scenario where
   `compute_spine_curvature` is called with fewer centroids than were used to fit
   the spline), chord-length re-parameterisation is applied to the subset to
   derive sensible `u` values — so `tangent_angles_deg` still reflects the
   physical curve geometry rather than an arbitrary grid.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + SciPy + NiBabel; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_019_vertebra_orientation_curvature.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–018.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Orientation / rotation estimate per vertebra + global
  curvature descriptors"** deliverable from 📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/019-vertebra-orientation-curvature`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
