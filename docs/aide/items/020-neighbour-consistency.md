# Item 020 — Neighbour-Consistency Metrics (Spacing Regularity & Monotonic Progression)

> **Status:** 📋 Planned · **Created:** 2026-06-26
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 020
> **Objectives:** Derive neighbour-consistency metrics from the ordered centroid
> sequence (014) and the spline (017); feeds the heuristic rule engine (Stage 4).
> **Suggested branch:** `aide/020-neighbour-consistency`

---

## Description

Given:

1. An ordered sequence of `LabelCentroid` objects produced by item 014
   (`SpineRelationships.present_levels` order).
2. A `SplineFit` produced by `fit_centroid_spline` (item 017).

Compute two families of **neighbour-consistency** metrics:

### A. Spacing regularity

From the ordered centroid sequence, derive:

- **Mean inter-centroid spacing** (mm): the mean of the `n-1` pairwise
  Euclidean distances between consecutive centroids in anatomical order.
- **Spacing coefficient of variation (CV)**: `std(spacings) / mean(spacings)`.
  A small CV (near 0) indicates regular spacing; a large CV indicates outliers
  or pathological variation.
- **Per-vertebra spacing deviation** (one value per *pair*, so `n-1` values):
  signed difference from the mean spacing for each adjacent pair, in mm.
- **Spacing outlier flags** (per pair): a boolean flag that is `True` when the
  spacing deviation exceeds a configurable threshold (default: `>= 2 * mean
  spacing` or `<= 0.3 * mean spacing` — i.e. unusually large or unusually small
  gaps). The pair is identified by `(level_a, level_b)`.

### B. Monotonic progression along the spline

Using the spline parameter values `u` at which each centroid's closest point
lies (i.e. the `closest_u` from item 018, or recomputed here via the same
closest-point search), assess whether the anatomical order is **consistent with
monotonically increasing spline parameter**:

- **`is_monotonic`** (`bool`): `True` when `u` values increase (or stay equal)
  at every consecutive pair in anatomical order.
- **Non-monotonic pairs** (`list[tuple[str, str]]`): the `(level_a, level_b)`
  pairs where `u[level_a] >= u[level_b]` (i.e. the parameter did not advance,
  indicating a swapped or stacked level).

### Public API

Expose the results as two dataclasses and two entry-point functions in
`segqc/features/consistency.py`:

```python
@dataclass(frozen=True)
class SpacingConsistency:
    """Spacing-regularity metrics for the ordered centroid sequence.

    Attributes
    ----------
    mean_spacing_mm : float
        Mean inter-centroid Euclidean spacing (mm).
    cv_spacing : float
        Coefficient of variation of inter-centroid spacings (0 = perfectly regular).
    spacings_mm : tuple[float, ...]
        Per-adjacent-pair spacings in anatomical order (length == n_centroids - 1).
    deviations_mm : tuple[float, ...]
        Signed deviation of each spacing from the mean (same length as spacings_mm).
    outlier_pairs : tuple[tuple[str, str], ...]
        (level_a, level_b) pairs whose spacing is flagged as an outlier.
    """
    mean_spacing_mm: float
    cv_spacing: float
    spacings_mm: tuple
    deviations_mm: tuple
    outlier_pairs: tuple


@dataclass(frozen=True)
class MonotonicConsistency:
    """Monotonic-progression metrics for the spline parameter sequence.

    Attributes
    ----------
    is_monotonic : bool
        True iff u values increase (non-decreasingly) along the anatomical order.
    non_monotonic_pairs : tuple[tuple[str, str], ...]
        (level_a, level_b) pairs where u[a] >= u[b] (spline parameter did not advance).
    u_values : tuple[float, ...]
        Per-centroid spline parameter values used for the assessment (length == n_centroids).
    """
    is_monotonic: bool
    non_monotonic_pairs: tuple
    u_values: tuple


def compute_spacing_consistency(
    centroids: Sequence[LabelCentroid],
    outlier_threshold_high: float = 2.0,
    outlier_threshold_low: float = 0.3,
) -> SpacingConsistency:
    """Compute spacing-regularity metrics for an ordered centroid sequence.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of LabelCentroid objects.
        Must have >= 2 entries; raises ValueError for 0 or 1 centroid.
    outlier_threshold_high:
        A spacing >= this factor * mean_spacing is flagged as an outlier
        (default 2.0 — double the mean).
    outlier_threshold_low:
        A spacing <= this factor * mean_spacing is flagged as an outlier
        (default 0.3 — less than 30 % of the mean).

    Returns
    -------
    SpacingConsistency
    """


def compute_monotonic_consistency(
    centroids: Sequence[LabelCentroid],
    fit: SplineFit,
) -> MonotonicConsistency:
    """Assess whether the anatomical order is consistent with monotonically
    increasing spline parameter values.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical order) sequence of LabelCentroid objects.
        Must have >= 2 entries; raises ValueError for 0 or 1 centroid.
    fit:
        SplineFit produced by fit_centroid_spline (item 017).

    Returns
    -------
    MonotonicConsistency
    """
```

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Spline fitting | Item 017 (`fit_centroid_spline`, `SplineFit`) |
| Per-vertebra offset | Item 018 (`compute_spline_offsets`) |
| Orientation / curvature | Item 019 |
| Stage 3 JSON serialisation | Item 022 |

---

## Acceptance Criteria

### AC1: Regular GT spacing scores within tolerance

Given an ordered sequence of centroids with **equal inter-centroid spacing**
(e.g. all consecutive pairs exactly 10 mm apart), `SpacingConsistency.cv_spacing`
must be **< 0.05** (near-zero coefficient of variation) and
`SpacingConsistency.outlier_pairs` must be **empty**.

### AC2: Spacing outlier is flagged

Given an ordered centroid sequence where one inter-centroid gap is injected to
be ≥ 2× the mean of the remaining gaps, `SpacingConsistency.outlier_pairs`
must contain exactly the `(level_a, level_b)` pair corresponding to that
injected large gap.

### AC3: Monotonic progression detected for GT

Given an ordered centroid sequence that maps to strictly increasing spline
parameter values (the canonical head-to-tail anatomical order), `is_monotonic`
must be `True` and `non_monotonic_pairs` must be **empty**.

### AC4: Swapped / non-monotonic ordering detected

Given a centroid sequence in which two adjacent levels are swapped (their
positions are exchanged relative to the fitted spline), `is_monotonic` must be
`False` and `non_monotonic_pairs` must contain the swapped pair.

### AC5: Determinism

Calling `compute_spacing_consistency` or `compute_monotonic_consistency` twice
with identical inputs must return **equal** result objects (field-by-field
identical).

### AC6: Return type and structure

`compute_spacing_consistency` returns a `SpacingConsistency` frozen dataclass
with the required fields: `mean_spacing_mm`, `cv_spacing`, `spacings_mm`,
`deviations_mm`, `outlier_pairs`.

`compute_monotonic_consistency` returns a `MonotonicConsistency` frozen
dataclass with the required fields: `is_monotonic`, `non_monotonic_pairs`,
`u_values`.

### AC7: Per-vertebra and per-case findings emitted with offending labels

`outlier_pairs` contains only `(level_name_a, level_name_b)` string pairs
(not integer labels). `non_monotonic_pairs` likewise contains level-name string
pairs. The caller can use these to produce per-vertebra findings.

### AC8: ValueError for insufficient centroids

`compute_spacing_consistency(centroids)` with fewer than 2 centroids raises
`ValueError` with a non-empty, human-readable message.

`compute_monotonic_consistency(centroids, fit)` with fewer than 2 centroids
raises `ValueError` with a non-empty, human-readable message.

---

## Implementation Steps

1. **Create `src/segqc/features/consistency.py`**:
   - `SpacingConsistency` — frozen dataclass with `mean_spacing_mm`, `cv_spacing`,
     `spacings_mm`, `deviations_mm`, `outlier_pairs`.
   - `MonotonicConsistency` — frozen dataclass with `is_monotonic`,
     `non_monotonic_pairs`, `u_values`.
   - `compute_spacing_consistency(centroids, outlier_threshold_high=2.0, outlier_threshold_low=0.3)`:
     - Validate: raise `ValueError` if `len(centroids) < 2`.
     - Compute pairwise Euclidean distances from `centroid_mm` values.
     - Compute `mean_spacing_mm` and `cv_spacing = std / mean` (use population std).
     - Compute `deviations_mm = spacings - mean`.
     - Flag pairs where `spacing >= outlier_threshold_high * mean` or
       `spacing <= outlier_threshold_low * mean`.
     - Return `SpacingConsistency`.
   - `compute_monotonic_consistency(centroids, fit)`:
     - Validate: raise `ValueError` if `len(centroids) < 2`.
     - For each centroid, find its closest spline parameter `u` (coarse scan +
       optional refinement, same approach as item 018).
     - Assess monotonicity: `u[i] < u[i+1]` for all consecutive pairs.
     - Collect non-monotonic pairs `(centroid[i].level_name, centroid[i+1].level_name)`
       where `u[i] >= u[i+1]`.
     - Return `MonotonicConsistency`.

2. **Export** from `segqc/features/__init__.py` (consistent with siblings).

---

## Testing Strategy

- **Framework:** `pytest` (no external services).
- **Unit tests** (`tests/test_020_neighbour_consistency.py`): all eight ACs;
  adversarial inputs (single centroid, two centroids, equal spacing, injected
  outlier, swapped pair, all-swapped ordering, collinear centroids, determinism,
  error type and message, immutability, frozen dataclass).
- **Fixtures**: `LabelCentroid` and `SplineFit` objects constructed inline
  (same helper pattern as items 017–019 tests).

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 013 (`LabelCentroid`)
  - Item 014 (`SpineRelationships` — ordered centroid sequence)
  - Item 017 (`SplineFit`, `fit_centroid_spline`)
  - NumPy, SciPy
- **Downstream:** Item 022 (Stage 3 serialisation).

---

## Decisions & Trade-offs

1. **Two separate functions** — `compute_spacing_consistency` (pure geometry,
   no spline needed) and `compute_monotonic_consistency` (requires the spline)
   — keeps each function testable in isolation and allows callers to invoke
   only the spacing check when no spline is available.

2. **Outlier thresholds default to 2× high / 0.3× low** — a gap ≥ 2× the mean
   is a clear jump (e.g. a missing level), and a gap ≤ 30 % of the mean suggests
   an overlap or near-coincident centroids. Both are configurable.

3. **CV as the regularity score** — coefficient of variation is unit-free and
   scale-invariant, making it valid across different vertebral levels and patient
   sizes without needing per-level reference data.

4. **Tuple fields in frozen dataclasses** — same pattern as `SplineFit.u`:
   tuples are cheaply comparable and make the dataclass naturally hashable.

5. **Closest-u search** — re-implemented in `consistency.py` using the same
   coarse-scan approach as item 018, rather than importing
   `compute_spline_offsets` (to avoid a circular dependency and because
   `compute_spline_offsets` returns full offset records, not just `u` values).

6. **Monotonicity defined as strictly increasing** — `u[i] >= u[i+1]` is
   flagged (not just `>`), so two anatomically ordered levels that map to
   the same spline parameter are also considered non-monotonic.

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

- `pytest tests/test_020_neighbour_consistency.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–019.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Neighbour-consistency metrics"** deliverable from 📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/020-neighbour-consistency`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
