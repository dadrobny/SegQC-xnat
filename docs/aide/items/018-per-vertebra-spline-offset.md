# Item 018 — Per-Vertebra Offset from the Spline

> **Status:** 📋 Planned · **Created:** 2026-06-26
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 018
> **Objectives:** Compute perpendicular offset of each vertebra centroid from the
> fitted spline — distance + signed components — in voxel and mm space; feeds
> the heuristic rule engine (Stage 4).
> **Suggested branch:** `aide/018-per-vertebra-spline-offset`

---

## Description

Given:

1. An ordered sequence of `LabelCentroid` objects (item 013/014).
2. A `SplineFit` produced by `fit_centroid_spline` (item 017).

Compute for each centroid its **perpendicular offset** from the fitted spline —
i.e. the closest-approach distance from the centroid to the curve — together
with a **signed decomposition** (anterior-posterior and left-right components
expressed in the same coordinate frame as the mm-coordinates).

Offsets should be:

- **Near-zero** for centroids that lie on the fitted spline (ground-truth
  aligned spines).
- **Large** for a centroid that has been synthetically displaced away from the
  curve.

### What "perpendicular offset" means here

Because the spline is defined parametrically in 3-D mm-space, the true
perpendicular offset of a point P is:

```
offset_mm = min_{u ∈ [0,1]}  ||P - S(u)||₂
```

where S(u) is the spline evaluated at parameter u.  The closest point on the
spline can be found by scanning a dense set of u values and refining with a
local minimisation (e.g. `scipy.optimize.minimize_scalar`).

The **signed components** are defined relative to the closest-point tangent:

- Let T̂ = normalised tangent vector of the spline at the closest u.
- Let D = P − S(u*) (the offset vector).
- The component perpendicular to T̂ in the coronal plane (L-R) and the
  component perpendicular to T̂ in the sagittal plane (A-P) can be reported
  directly from the (x, y, z) components of D after projection.

For item 018 a simpler but sufficient signed decomposition is acceptable: report
the raw `(dx, dy, dz)` vector from closest spline point to centroid, along with
the scalar Euclidean distance. The distinction between "perpendicular" and "raw
difference vector" matters only for non-straight spines; for the QC use-case
the Euclidean distance magnitude is the primary signal.

### Public API

Expose the result as a `VertebralSplineOffset` dataclass and a
`compute_spline_offsets(centroids, fit, spacing_mm=None)` function in
`segqc/features/spline_offset.py`.

```python
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
        x-component of the displacement vector (centroid_mm[0] − spline_x),
        in mm.
    dy_mm : float
        y-component of the displacement vector, in mm.
    dz_mm : float
        z-component of the displacement vector, in mm.
    """
    label: int
    level_name: str
    closest_u: float
    offset_mm: float
    offset_voxel: float
    dx_mm: float
    dy_mm: float
    dz_mm: float


def compute_spline_offsets(
    centroids: Sequence[LabelCentroid],
    fit: SplineFit,
    spacing_mm: Optional[Tuple[float, float, float]] = None,
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
```

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Spline fitting | Item 017 (`fit_centroid_spline`, `SplineFit`) |
| Orientation / curvature | Item 019 |
| Neighbour-consistency | Item 020 |
| Stage 3 JSON serialisation | Item 022 |

---

## Acceptance Criteria

- [ ] **AC1: Near-zero offsets for GT centroids lying on the spline**: for
      centroids constructed to lie exactly on a smooth curve (the same points
      used to fit the spline), `offset_mm` is less than **1.0 mm** for every
      vertebra.

- [ ] **AC2: Large offset for a synthetically displaced centroid**: when one
      centroid is displaced by ≥ 10 mm perpendicular to the spline, its
      `offset_mm` is ≥ **8.0 mm** (a conservative lower bound accounting for
      closest-point tolerance); the other centroids' offsets remain small
      (< 2.0 mm).

- [ ] **AC3: Correct application of anisotropic spacing**:
      `offset_voxel` equals `offset_mm / effective_spacing` (approximately,
      within a small tolerance reflecting the mixed-spacing nature of a 3-D
      offset).  Specifically, for a purely z-axis displacement and voxel spacing
      `(1, 1, sz)`, `offset_voxel` ≈ `offset_mm / sz`.

- [ ] **AC4: Signed components sum to the Euclidean distance**: for each
      record, `sqrt(dx_mm² + dy_mm² + dz_mm²) ≈ offset_mm` (within 0.1 mm
      floating-point tolerance).

- [ ] **AC5: Determinism** — calling `compute_spline_offsets` twice with
      identical inputs returns an equal list of `VertebralSplineOffset` objects.

- [ ] **AC6: Return type and structure** — the function returns a non-empty
      `list` of `VertebralSplineOffset` instances when centroids is non-empty;
      each instance is a frozen dataclass exposing `label`, `level_name`,
      `closest_u`, `offset_mm`, `offset_voxel`, `dx_mm`, `dy_mm`, `dz_mm`.

- [ ] **AC7: closest_u in [0, 1]** — for every returned record,
      `0.0 ≤ closest_u ≤ 1.0`.

- [ ] **AC8: Empty centroids raises ValueError** — calling
      `compute_spline_offsets([], fit)` raises `ValueError` with a non-empty,
      human-readable message.

---

## Implementation Steps

1. **Create `src/segqc/features/spline_offset.py`**:
   - `VertebralSplineOffset` — frozen dataclass with the eight fields above.
   - `compute_spline_offsets(centroids, fit, spacing_mm=None)`:
     - Validate: raise `ValueError` if `centroids` is empty.
     - For each centroid:
       - Sample the spline at N_SCAN (e.g. 500) linearly-spaced u values to
         find a coarse closest u.
       - Optionally refine with `scipy.optimize.minimize_scalar` in the
         bracket around the coarse closest u.
       - Compute D = centroid_mm − S(u*) (the displacement vector).
       - `offset_mm` = `||D||₂`.
       - Convert to voxel units: use the mean spacing `(sx + sy + sz) / 3` as
         a scalar divisor, or compute the voxel-space Euclidean distance
         directly: `sqrt((dx/sx)² + (dy/sy)² + (dz/sz)²)` when `spacing_mm`
         is provided. This gives an anisotropic-correct `offset_voxel`.
       - Record `closest_u`, `offset_mm`, `offset_voxel`, `dx_mm`, `dy_mm`,
         `dz_mm`.
     - Return the list in the same order as the input.

2. **Export** from `segqc/features/__init__.py` (consistent with siblings).

---

## Testing Strategy

- **Framework:** `pytest` (no external services).
- **Unit tests** (`tests/test_018_per_vertebra_spline_offset.py`): all eight ACs;
  adversarial inputs (near-zero offsets on GT curve, large offset for a displaced
  centroid, anisotropic spacing, signed-component Euclidean consistency,
  determinism, degenerate empty input, `closest_u` bounds, `offset_voxel ≈
  offset_mm` for isotropic spacing).
- **Fixtures**: `LabelCentroid` and `SplineFit` objects constructed inline (same
  helper pattern as item 017 tests).

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 013 (`LabelCentroid`)
  - Item 014 (`SpineRelationships` — ordered centroid sequence)
  - Item 017 (`SplineFit`, `fit_centroid_spline`, `evaluate_spline`)
  - SciPy (`scipy.optimize.minimize_scalar`) — already in dependencies
  - NumPy
- **Downstream:** Item 022 (Stage 3 serialisation).

---

## Decisions & Trade-offs

1. **Closest-point search strategy**: coarse scan over 500 u values followed by
   optional `minimize_scalar` refinement gives sub-mm accuracy for typical spinal
   geometries without being expensive.

2. **`offset_voxel` computation**: for anisotropic spacings the voxel-space
   Euclidean distance `sqrt((dx/sx)² + (dy/sy)² + (dz/sz)²)` is the most
   correct metric. When `spacing_mm` is `None`, isotropic 1 mm is assumed
   (`offset_voxel = offset_mm`).

3. **Signed components**: raw `(dx, dy, dz)` displacement vector is sufficient
   for item 018; a full tangent-frame decomposition (anterior-posterior vs
   left-right) is deferred to item 019 orientation work.

4. **Empty-centroids ValueError**: consistent with item 017's `ValueError` for
   < 2 points — callers must supply at least one centroid.

5. **Return order**: the output list preserves the input centroid order, matching
   the convention of all other `compute_*` functions in `segqc/features/`.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + SciPy; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_018_per_vertebra_spline_offset.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–017.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Per-vertebra offset from the spline"** deliverable from
  📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/018-per-vertebra-spline-offset`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
