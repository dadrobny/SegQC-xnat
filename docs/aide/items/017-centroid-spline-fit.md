# Item 017 — Centroid Spline Fit (Robust to Missing Levels)

> **Status:** 🚧 In Progress · **Created:** 2026-06-26
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 017
> **Objectives:** Continuous spinal-curve representation for downstream deviation
> features (018–022)
> **Suggested branch:** `aide/017-centroid-spline-fit`

---

## Description

Fit a smooth parametric spline (cubic B-spline via `scipy.interpolate`) through
the **ordered** vertebra centroids produced by item 014, producing a continuous
spinal-curve representation that:

- Can be **sampled at arbitrary parameter values** along the curve.
- Supports **arc-length parameterisation** (approximate: sufficient for the
  deviation and consistency features in items 018–020).
- Is **robust to a deliberately missing level** — when one centroid is removed
  from an otherwise complete sequence the fit must not crash and must produce a
  sensible interpolation through the remaining points.
- Handles **as few as 2 or 3 centroids** without error.
- Exhibits **graceful, documented behaviour for degenerate inputs**: a single
  centroid and collinear points are edge cases that the function handles without
  raising uncaught errors; callers are informed (via a documented return value or
  a `ValueError` with a clear message) when the spline cannot be meaningfully fit.

### Public API

Expose the result as a `SplineFit` dataclass and a
`fit_centroid_spline(centroids, degree=3) -> SplineFit` function in
`segqc/features/spline.py`.

```python
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
        spline.
    degree:
        Polynomial degree used (default 3 for cubic).
    n_points:
        Number of input centroids used to fit the spline.
    """
    tck: tuple        # (t, c, k) from scipy splprep
    u: tuple          # parameter values for input points, length == n_points
    degree: int
    n_points: int


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
        mm-coordinates (``centroid_mm``) are used for the fit.
    degree:
        Polynomial degree (default 3, cubic).  Clamped to
        ``min(degree, n_points - 1)`` when the sequence is short.

    Returns
    -------
    SplineFit
        Fitted spline representation.

    Raises
    ------
    ValueError
        When fewer than 2 distinct centroids are provided (a single point or
        zero points cannot define a curve).
    """
```

A helper `evaluate_spline(fit: SplineFit, u_values) -> np.ndarray` evaluates
the spline at the supplied parameter values and returns an `(N, 3)` float array
of (x, y, z) mm-coordinates.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Per-vertebra offset from the spline | Item 018 |
| Orientation / curvature | Item 019 |
| Neighbour-consistency | Item 020 |
| Sagittal projection | Item 021 |
| Stage 3 JSON serialisation | Item 022 |

---

## Acceptance Criteria

- [ ] **AC1: Spline fits within tolerance of input centroids on GT fixtures**:
      evaluating the fitted spline at the parameter values `u` of each input
      centroid returns (x, y, z) coordinates within **0.5 mm** of the original
      `centroid_mm` values.

- [ ] **AC2: Robustness when one level is deliberately removed**: fitting on a
      sequence with one centroid deliberately removed (a "missing level") must
      not raise any exception; the returned `SplineFit` must be a valid object
      that can be evaluated at arbitrary `u` without error.

- [ ] **AC3: Degree is clamped for short sequences**: when `n_points < degree +
      1`, the effective polynomial degree is reduced to `n_points - 1` (i.e.
      `degree=3` with 2 or 3 points falls back to linear or quadratic); no
      exception is raised.

- [ ] **AC4: Determinism — repeated fits with identical inputs produce identical
      `SplineFit` objects** (same `tck`, same `u` values).

- [ ] **AC5: Graceful handling of degenerate inputs** — 1 centroid (or 0)
      raises `ValueError` with a non-empty, human-readable message (no raw
      internal SciPy traceback in the message); collinear points are accepted
      without error and produce a valid spline.

- [ ] **AC6: `evaluate_spline` returns an `(N, 3)` float array** for any valid
      `u_values` sequence of length N within [0, 1]; no NaN or Inf values for
      well-conditioned inputs.

---

## Implementation Steps

1. **Create `src/segqc/features/spline.py`**:
   - `SplineFit` — frozen dataclass with `tck`, `u`, `degree`, `n_points`.
   - `fit_centroid_spline(centroids, degree=3) -> SplineFit`:
     - Extract `centroid_mm` from each `LabelCentroid`.
     - Validate: raise `ValueError` if `len(centroids) < 2`.
     - Clamp `degree` to `min(degree, n_points - 1)`.
     - Build coordinate arrays `x, y, z` for `scipy.interpolate.splprep`.
     - Call `tck, u = scipy.interpolate.splprep([x, y, z], k=effective_degree, s=0)`.
     - Return `SplineFit(tck=tck, u=tuple(u), degree=effective_degree, n_points=n_points)`.
   - `evaluate_spline(fit: SplineFit, u_values) -> np.ndarray`:
     - Call `scipy.interpolate.splev(u_values, fit.tck)`.
     - Return as `(N, 3)` float64 array (columns: x, y, z).

2. **Export** from `segqc/features/__init__.py` (optional, consistent with siblings).

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Unit tests** (`tests/test_017_centroid_spline_fit.py`): all six ACs;
  adversarial inputs (single centroid, zero centroids, 2 centroids, 3 centroids,
  collinear, missing-level, highly anisotropic spacing); immutability;
  determinism; error-type and message quality; import contract.
- **Fixtures**: `LabelCentroid` objects constructed inline (no NIfTI needed for
  the spline tests, since `centroid_mm` values are plain tuples); use
  `labelled_blocks_case()` + `compute_centroid` only if a full round-trip test
  is warranted.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 013 (`LabelCentroid` — `centroid_mm` is the input)
  - Item 014 (`SpineRelationships` — provides the ordered sequence)
  - SciPy (`scipy.interpolate.splprep`, `splev`) — already in dependencies
- **Downstream:** Item 018 (per-vertebra offset); Item 019 (orientation/
  curvature); Item 020 (neighbour-consistency); Item 021 (sagittal projection);
  Item 022 (Stage 3 serialisation).

---

## Decisions & Trade-offs

1. **`scipy.interpolate.splprep` (parametric B-spline)** — accepts a list of
   coordinate arrays and returns a `(t, c, k)` representation. Standard choice
   for open-curve fitting; the `s=0` smoothing factor forces the spline through
   every input point, which satisfies AC1 (within-tolerance pass-through).

2. **Degree clamping** — SciPy raises an error when `k >= n_points`; clamping
   to `min(degree, n_points - 1)` silently makes the fit work for 2–3 points
   without forcing callers to pre-check (AC3). The effective degree is recorded
   in `SplineFit.degree`.

3. **`ValueError` for < 2 distinct points** — consistent with item 013's
   `ValueError` on absent label. The message mentions the point count and the
   requirement. We do not silently return a degenerate object; callers must guard
   or catch.

4. **`u` stored as a `tuple`** — makes `SplineFit` cheaply comparable / hashable;
   avoids carrying mutable NumPy arrays in a frozen dataclass.

5. **`tck` stored as-is from SciPy** — `tck` is a Python tuple `(t_array,
   c_list_of_arrays, k_int)`; freezing the dataclass does not deep-freeze the
   inner arrays. Callers must not mutate `tck` internals. This is a pragmatic
   trade-off: deep-copying the arrays on every fit would be wasteful for a
   read-only pipeline.

6. **No arc-length re-parameterisation in this item** — arc-length sampling is
   approximated by evaluating at closely spaced `u` values; the full
   arc-length re-parameterisation (if needed) belongs to item 022 or a later
   helper.

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

- `pytest tests/test_017_centroid_spline_fit.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–016.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Spline fit through ordered vertebra centroids"** deliverable
  from 📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/017-centroid-spline-fit`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
