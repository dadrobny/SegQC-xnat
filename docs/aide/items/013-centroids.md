# Item 013 — Centroid / Centre-of-Mass per Label (Level-Aware)

> **Status:** 🚧 In Progress · **Created:** 2026-06-25
> **Stage:** 2 — Geometric & Topological Feature Extraction
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 013
> **Objectives:** Per-vertebra centroid for spline and heuristic downstream modules
> **Suggested branch:** `aide/013-centroids`

---

## Description

Compute the **centre of mass** (voxel and physical / mm coordinates) for each
vertebra label in an instance label map.

- **centroid_voxel** — (x, y, z) tuple of floating-point voxel indices
  representing the centre of mass of all voxels carrying that label.
- **centroid_mm** — physical coordinate derived from `centroid_voxel` by
  element-wise multiplication with the voxel spacings: each axis
  `centroid_mm[i] = centroid_voxel[i] * spacing[i]`. Correct under anisotropic
  spacing.
- **level_name** — the anatomical vertebra name (e.g. `"C1"`, `"L3"`, `"S"`)
  looked up from the `LabelConvention` for that label integer. Must be a
  non-empty string for every present label; use `labels.UNKNOWN` when the
  integer has no mapping.

### Level-aware handling notes

- **C1 (atlas) and C2 (axis)** — their centroid positions may deviate from the
  main sequence pattern in downstream modules; this item only needs to ensure
  their `level_name` values are `"C1"` and `"C2"` respectively, and that their
  centroid coordinates are computed identically to all other labels (no special
  geometric treatment).
- **Sacrum (S / S1)** — the sacrum may be treated as a compound structure by
  downstream modules; for this item, compute a single centre-of-mass over all
  sacral voxels and attach `level_name = "S"` (or whatever the convention maps
  the sacrum label to). No decomposition is required here.

Expose the result as a `LabelCentroid` frozen dataclass and a
`compute_centroid(seg_img, label, convention=None) -> LabelCentroid` function
in `segqc/features/centroids.py`.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| NIfTI loading / spacing extraction | Item 003 / NiBabel header |
| Per-label volume / extent / bbox | Item 011 |
| Connected-components analysis | Item 012 |
| Inter-vertebra relationships / spline | Items 014, 017 |
| JSON serialisation | Item 016 |
| Heuristic rules | Stage 4 |

---

## Acceptance Criteria

- [ ] **AC1: Centroids for synthetic fixtures match hand-computed expectations
      in voxel and mm space**: `compute_centroid` returns correct
      `centroid_voxel` and `centroid_mm` for rectangular block labels whose
      centres are analytically known.

- [ ] **AC2: Anisotropic spacing is correctly applied**:
      `centroid_mm[i] = centroid_voxel[i] * spacing[i]` for all axes; physical
      coordinates differ from voxel coordinates when spacing ≠ 1.

- [ ] **AC3: Level-aware metadata (anatomical level name) is attached to each
      centroid record**: `result.level_name` is a non-empty string for every
      label present in the fixture; it equals the name returned by the default
      `LabelConvention` for a mapped integer, or `UNKNOWN` for an unmapped one.

- [ ] **AC4: Functions are deterministic**: two calls with identical inputs
      produce identical `LabelCentroid` instances.

---

## Implementation Steps

1. **Create `src/segqc/features/centroids.py`**:
   - `LabelCentroid` — frozen dataclass with:
     - `label: int` — the integer label value.
     - `level_name: str` — anatomical name from `LabelConvention`.
     - `centroid_voxel: tuple[float, float, float]` — (x, y, z) centre of mass
       in voxel index space.
     - `centroid_mm: tuple[float, float, float]` — (x, y, z) centre of mass in
       mm, derived by element-wise multiplication with spacing.
   - `compute_centroid(seg_img, label, convention=None) -> LabelCentroid`:
     - Extract spacing from `seg_img.header.get_zooms()`.
     - Locate voxels: `np.argwhere(data == label)`.
     - Raise `ValueError` with a non-empty message if the label is absent.
     - Compute centroid as the mean of voxel coordinates along axis 0.
     - Compute physical centroid as element-wise `centroid_voxel * spacing`.
     - Look up `level_name` via `LabelConvention.default()` (or the supplied
       `convention`); fall back to `segqc.labels.UNKNOWN` if unmapped.
     - Never mutate the input image.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Unit tests** (`tests/test_013_centroids.py`): all four ACs; adversarial
  inputs (single-voxel label, label spanning full axis, anisotropic spacing,
  missing label, unmapped label integer, level_name contract); immutability;
  determinism; error-message quality; import contract.
- **Fixtures**: `labelled_blocks_case()`, `anisotropic_case()`, and ad-hoc
  `make_labelmap()` calls from `synthetic.py`.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures — `make_labelmap`, `labelled_blocks_case`,
    `anisotropic_case`)
  - Item 003 (NIfTI header, spacing convention)
  - Item 004 (label-convention module — `LabelConvention`, `DEFAULT_LABEL_MAP`,
    `UNKNOWN`)
  - Item 011 (`segqc.features` subpackage marker, `_get_spacing` pattern)
- **Downstream:** Items 014–016 (rest of Stage 2); Items 017–020 (Stage 3
  spline); Stage 4 heuristics.

---

## Decisions & Trade-offs

To be updated during implementation.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + NiBabel; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_013_centroids.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–012.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"Centroids"** deliverable from 🚧 → ✅.
- Per `CLAUDE.md`: work on branch `aide/013-centroids`, `git pull --rebase`
  before editing `progress.md`, keep edits scoped to this item's rows, and
  direct-merge (no PR required) once green.
