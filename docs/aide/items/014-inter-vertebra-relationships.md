# Item 014: Inter-vertebra relationships — ordered sequence, neighbour spacing, continuity

**Status:** ✅ Complete
**Branch:** `aide/014-inter-vertebra-relationships`
**Queue:** queue-002.md

---

## Description

Using the ordered centroid sequence (sorted by anatomical level using the
label-convention module), compute:

- **Ordered label sequence** — which anatomical levels are present, listed in
  head-to-tail anatomical order (using `CANONICAL_ORDER` from `segqc.labels`).
- **Expected vs. actual presence** — which levels are missing relative to the
  expected C–T–L–S sequence. "Expected" is the full contiguous run of levels
  spanning from the lowest to the highest level present; gaps within that span
  are missing levels.
- **Neighbour spacing** — Euclidean distance (mm) between adjacent centroids
  in the ordered sequence (i.e. `||centroid_mm[i+1] - centroid_mm[i]||₂`).
- **Label-sequence continuity** — whether the anatomical order is monotonically
  non-decreasing according to `CANONICAL_ORDER`. Any label that is out of order
  relative to its predecessor (e.g. L1→T12→L2→L5) is flagged; the result is a
  boolean `is_continuous` and a list of the out-of-order labels.

Store results in a `SpineRelationships` record (frozen dataclass) in
`segqc/features/relationships.py`. Expose a single entry-point:

```python
compute_spine_relationships(
    centroids: Sequence[LabelCentroid],
    convention: LabelConvention | None = None,
) -> SpineRelationships
```

The function is the input for:
- Non-continuity heuristic (failure mode 7) — `is_continuous` / `out_of_order_labels`
- Missing-levels heuristic (failure mode 5) — `missing_levels`

---

## Acceptance Criteria

### AC1: Ordered label sequence is correct for a well-ordered fixture

Given a list of `LabelCentroid` records whose `level_name` values are a
well-ordered subset of `CANONICAL_ORDER`, `SpineRelationships.present_levels`
must contain exactly those level names, in anatomical order (head-to-tail,
matching `CANONICAL_ORDER`), regardless of the order the caller supplied them.

### AC2: Missing-level detection is correct

`SpineRelationships.missing_levels` contains exactly the levels that fall within
the anatomical span [min_present .. max_present] but are absent from the
centroid list. A fixture with no gap yields an empty `missing_levels`. A fixture
with a gap (e.g. T1, T3 present but T2 absent) yields `["T2"]` in
`missing_levels`.

### AC3: Neighbour spacings are correct Euclidean distances

`SpineRelationships.neighbour_spacings_mm` is a list of `len(present_levels) - 1`
floats. Each entry is the Euclidean distance `||centroid_mm[i+1] - centroid_mm[i]||₂`
between consecutive centroids in anatomical order. The list is empty when fewer
than 2 levels are present.

### AC4: Label-sequence continuity detection is correct

`SpineRelationships.is_continuous` is `True` when all supplied `level_name`
values are already in non-decreasing anatomical order, and `False` when any
label is out of order. `SpineRelationships.out_of_order_labels` is empty when
`is_continuous` is `True`, and contains the offending label names (in the order
they appear in the input) when `is_continuous` is `False`.

### AC5: SpineRelationships is a frozen dataclass with the required fields

`SpineRelationships` must expose exactly the following attributes:
- `present_levels: list[str]` — anatomical names in canonical order
- `missing_levels: list[str]` — absent levels within the observed span
- `neighbour_spacings_mm: list[float]` — per-adjacent-pair Euclidean distances
- `is_continuous: bool` — True iff all supplied levels are in anatomical order
- `out_of_order_labels: list[str]` — offending labels (empty when continuous)

---

## Decisions & Trade-offs

1. **Span definition for missing levels.** "Expected" levels are defined as the
   contiguous run in `CANONICAL_ORDER` from the lowest present level to the
   highest present level. Levels outside that span (e.g. C1–C7 absent when only
   thoracic/lumbar levels are present) are not reported as missing.

2. **Continuity vs. ordering.** Continuity is assessed against the order in
   which centroids are supplied to the function (the caller's order), not the
   canonical order. If the caller supplies a correctly sorted list the function
   confirms it; if the caller supplies an unsorted list the non-monotone entries
   are flagged. This mirrors real-world use where the caller might not sort.

3. **Unknown labels.** Centroids whose `level_name` is `UNKNOWN` are silently
   skipped in all computations (they cannot be placed in `CANONICAL_ORDER`).
   They do not appear in `present_levels`, `missing_levels`,
   `neighbour_spacings_mm`, `out_of_order_labels`, or affect `is_continuous`.

4. **Degenerate inputs.** Zero centroids: all lists empty, `is_continuous=True`.
   One centroid: `present_levels` has one entry, all other lists empty,
   `is_continuous=True`. Two centroids: one spacing, continuity checked.

5. **Module location.** `segqc/features/relationships.py` — consistent with the
   `geometry.py`, `components.py`, `centroids.py`, `overlap.py` siblings.

6. **No NIfTI dependency.** The function operates on `LabelCentroid` records
   (already extracted from the image); it never reads a NIfTI file directly.
