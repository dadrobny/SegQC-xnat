# Item 024 — Local Vertebra Neighbourhood Comparison

> **Status:** 📋 Planned · **Created:** 2026-06-27
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 024
> **Objectives:** Compute local neighbourhood features via a sliding window for
> each vertebra; flag outlier vertebrae whose deviation exceeds a threshold.
> Completes Stage 3.
> **Suggested branch:** `aide/024-neighbourhood-comparison`

---

## Description

Using:

1. The ordered centroid sequence from item 014 (`LabelCentroid` objects in
   anatomical order, with `centroid_mm` and `level_name`).
2. Per-vertebra spline offsets from item 018 (`VertebralSplineOffset`).
3. Per-label geometry from item 011 (`LabelGeometry` — `physical_volume_mm3`
   and `voxel_count`).

Compute **local neighbourhood features** via a sliding window of configurable
width `n` (default `n=3`, i.e. ±1 neighbour on each side):

For each vertebra `v` with window of `n` centroids centred on `v` (clamped at
boundaries so first/last vertebrae use smaller, one-sided windows):

- **Mean and median of centroid spacing** within the window (inter-centroid
  Euclidean distances between consecutive window members, in mm).
- **Mean and median of spline offset** (`offset_mm`) within the window.
- **Mean and median of label volume** (`physical_volume_mm3`) within the window.
- **Standard deviation** (or MAD) of each metric within the window —
  quantifying local variation.
- **Per-vertebra neighbourhood deviation score**: a scalar summarising how
  much the focal vertebra differs from its neighbours (e.g. the maximum
  normalised deviation across the three metrics, or a weighted combination).
- **Outlier flag**: `True` when the deviation score exceeds a configurable
  threshold.

### Window definition

A window of width `n` centred at position `i` (0-indexed) spans indices
`max(0, i - n//2)` to `min(len-1, i + n//2)` inclusive. At the boundaries the
window is asymmetric (smaller), but the focal vertebra is always included.

### Public API

Expose the results as a `VertebralNeighbourhood` dataclass (one per vertebra)
and two entry-point functions in `segqc/features/neighbourhood.py`:

```python
@dataclass(frozen=True)
class VertebralNeighbourhood:
    """Per-vertebra local neighbourhood statistics.

    Attributes
    ----------
    label : int
        Integer label value of the focal vertebra.
    level_name : str
        Anatomical name of the focal vertebra.
    window_labels : tuple[int, ...]
        Integer label values of all vertebrae in the window (including focal).
    mean_spacing_mm : float
        Mean inter-centroid spacing (mm) within the window.
    median_spacing_mm : float
        Median inter-centroid spacing (mm) within the window.
    std_spacing_mm : float
        Standard deviation of inter-centroid spacings within the window.
    mean_offset_mm : float
        Mean spline offset (mm) within the window.
    median_offset_mm : float
        Median spline offset (mm) within the window.
    std_offset_mm : float
        Standard deviation of spline offsets within the window.
    mean_volume_mm3 : float
        Mean label volume (mm³) within the window.
    median_volume_mm3 : float
        Median label volume (mm³) within the window.
    std_volume_mm3 : float
        Standard deviation of label volumes within the window.
    deviation_score : float
        Per-vertebra scalar summarising how anomalous the focal vertebra is
        relative to its neighbours (non-negative; 0 = perfectly consistent).
    is_outlier : bool
        True when deviation_score exceeds the configured threshold.
    """
    label: int
    level_name: str
    window_labels: tuple
    mean_spacing_mm: float
    median_spacing_mm: float
    std_spacing_mm: float
    mean_offset_mm: float
    median_offset_mm: float
    std_offset_mm: float
    mean_volume_mm3: float
    median_volume_mm3: float
    std_volume_mm3: float
    deviation_score: float
    is_outlier: bool


def compute_neighbourhood_features(
    centroids: Sequence[LabelCentroid],
    offsets: Sequence[VertebralSplineOffset],
    geometries: Mapping[int, LabelGeometry],
    window_n: int = 3,
    outlier_threshold: float = 2.0,
) -> List[VertebralNeighbourhood]:
    """Compute local neighbourhood statistics for each vertebra.

    Parameters
    ----------
    centroids:
        Ordered (head-to-tail anatomical) sequence of LabelCentroid objects.
        Must have >= 1 entry; raises ValueError when empty.
    offsets:
        Per-vertebra spline offsets from compute_spline_offsets (item 018).
        Must be in the same order as centroids and have the same length.
    geometries:
        Mapping from integer label to LabelGeometry (item 011).
        Must contain an entry for every label in centroids.
    window_n:
        Total window width (must be >= 1 and odd). Default 3 (= focal + 1 on
        each side). Raises ValueError when window_n < 1.
    outlier_threshold:
        Deviation score threshold above which a vertebra is flagged as an
        outlier. Default 2.0.

    Returns
    -------
    List[VertebralNeighbourhood]
        One record per centroid, in the same order as the input sequence.

    Raises
    ------
    ValueError
        When centroids is empty or window_n < 1.
    """
```

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Spline offsets | Item 018 (`VertebralSplineOffset`) |
| Per-label geometry / volume | Item 011 (`LabelGeometry`) |
| Spline fitting | Item 017 |
| Stage 3 JSON serialisation | Item 022 (extends if needed) |

---

## Acceptance Criteria

- [ ] **AC1: Near-zero deviation for a regular GT fixture**: given an ordered
      centroid sequence with equal inter-centroid spacing, near-equal spline
      offsets (all < 1 mm), and near-equal label volumes, every
      `VertebralNeighbourhood.deviation_score` is **< 0.5** and
      `is_outlier` is **`False`** for all vertebrae (with the default threshold).

- [ ] **AC2: Single injected outlier is flagged while neighbours are not**:
      given a regular spine where one vertebra has its centroid displaced by
      >= 10 mm (producing a large spline offset) or its volume multiplied by
      3× relative to neighbours, the focal vertebra's `is_outlier` is `True`
      and **none of its immediate neighbours** have `is_outlier = True`.

- [ ] **AC3: Window boundary cases handled without crash**: the first and last
      vertebrae (boundary positions) each produce a valid `VertebralNeighbourhood`
      record without raising an exception; `window_labels` contains at least
      the focal vertebra and one neighbour.

- [ ] **AC4: Configurable window width**: calling
      `compute_neighbourhood_features(centroids, offsets, geometries, window_n=5)`
      (± 2 neighbours) returns valid records for all centroids; the central
      vertebrae's `window_labels` contain 5 entries.

- [ ] **AC5: Determinism**: two calls with identical inputs return an equal
      list of `VertebralNeighbourhood` objects (field-by-field identical).

- [ ] **AC6: Return type and structure**: the function returns a `list` of
      `VertebralNeighbourhood` frozen dataclass instances, one per centroid,
      in the same order as the input sequence, exposing all documented fields.

- [ ] **AC7: Output length matches input length**: `len(result) == len(centroids)`
      for any valid (non-empty) input.

- [ ] **AC8: ValueError for empty centroids**: calling
      `compute_neighbourhood_features([], ...)` raises `ValueError` with a
      non-empty, human-readable message.

- [ ] **AC9: ValueError for window_n < 1**: calling with `window_n=0` or
      `window_n=-1` raises `ValueError` with a non-empty, human-readable message.

- [ ] **AC10: deviation_score is non-negative**: for all returned records,
      `deviation_score >= 0.0`.

---

## Implementation Steps

1. **Create `src/segqc/features/neighbourhood.py`**:
   - `VertebralNeighbourhood` — frozen dataclass with all documented fields.
   - `compute_neighbourhood_features(centroids, offsets, geometries, window_n=3, outlier_threshold=2.0)`:
     - Validate: raise `ValueError` if `centroids` is empty or `window_n < 1`.
     - Build parallel arrays: centroid spacings (pairwise mm), spline offsets,
       volumes — one value per vertebra (use NaN or 0 for the first spacing).
     - For each focal vertebra `i`:
       - Determine window indices `[max(0, i - window_n//2), min(n-1, i + window_n//2)]`.
       - Compute window spacing values from the *pairs within the window*
         (not from the focal vertebra alone): the `k-1` pairwise distances
         between the `k` consecutive window members.
       - Compute window means/medians/stds for spacing, offset, volume.
       - Compute deviation score: how much the focal vertebra's offset and
         volume deviate from the window mean, normalised by window std (or a
         fixed reference when std is near zero).
       - Set `is_outlier = deviation_score >= outlier_threshold`.
     - Return the list in input order.

2. **Export** from `segqc/features/__init__.py`.

---

## Testing Strategy

- **Framework:** `pytest` (no external services).
- **Unit tests** (`tests/test_024_neighbourhood_comparison.py`): all ten ACs;
  adversarial inputs (single vertebra, two vertebrae, regular GT fixture,
  injected single outlier, window boundaries, configurable window width,
  determinism, ValueError cases, deviation score non-negative, frozen
  dataclass immutability, input not mutated).
- **Fixtures**: `LabelCentroid`, `VertebralSplineOffset`, and `LabelGeometry`
  objects constructed inline (same helper pattern as items 018–020 tests).

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 011 (`LabelGeometry`, `compute_label_geometry`)
  - Item 013 (`LabelCentroid`)
  - Item 014 (`SpineRelationships` — ordered centroid sequence)
  - Item 017 (`SplineFit`, `fit_centroid_spline`)
  - Item 018 (`VertebralSplineOffset`, `compute_spline_offsets`)
  - NumPy
- **Downstream:** Stage 4 heuristic rule engine.

---

## Decisions & Trade-offs

1. **Window definition**: symmetric where possible, asymmetric (one-sided) at
   boundaries — the focal vertebra is always the centre conceptually, but the
   window is clamped. This avoids edge-case crashes while keeping window
   statistics local.

2. **deviation_score formula**: the primary signal is how far the focal
   vertebra's spline offset and volume deviate from the local window. A
   combined score (max of normalised deviations, or sum of absolute
   z-scores within the window) is implementation-defined; the spec guarantees
   it is >= 0 and that it is large for clearly anomalous vertebrae.

3. **spacing_mm in window**: inter-centroid spacings are *pair* quantities
   (between consecutive vertebrae), not *per-vertebra* quantities. For a
   window [i-1, i, i+1] the spacings are [d(i-1,i), d(i,i+1)], giving 2
   values from 3 vertebrae. At a left boundary [0, 1] the only spacing is
   d(0,1). When the window contains only 1 vertebra (single-vertebra input)
   spacing statistics are defined as 0.

4. **window_n must be >= 1**: a window of width 0 is meaningless; even width
   values (e.g. 2, 4) are allowed but produce slightly asymmetric windows.

5. **Empty-centroids ValueError**: consistent with item 018 / 020 conventions.

6. **No NIfTI dependency**: the function operates on pre-computed dataclass
   records; it never reads a NIfTI file directly.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_024_neighbourhood_comparison.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–023.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Local neighbourhood comparison"** deliverable from
  📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/024-neighbourhood-comparison`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
