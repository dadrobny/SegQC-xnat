# Item 012 — Connected-Components Analysis per Label

> **Status:** 🚧 In Progress · **Created:** 2026-06-25
> **Stage:** 2 — Geometric & Topological Feature Extraction
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 012
> **Objectives:** Topological feature engine — fragment detection (failure mode 3)
> **Suggested branch:** `aide/012-connected-components`

---

## Description

For each vertebra label in the instance label map, run **connected-components**
analysis (scipy `ndimage.label` or scikit-image `measure.label`) and compute:

- **component_count** — number of distinct connected components for that label.
- **component_sizes** — list of voxel counts for each component, sorted
  descending (largest first).
- **component_volumes_mm3** — list of physical volumes (mm³) for each
  component, in the same order as `component_sizes`.
- **largest_component_fraction** — `component_sizes[0] / sum(component_sizes)`,
  i.e. the fraction of label voxels that belong to the largest component.
  Equals `1.0` when the label is a single connected piece.
- **small_fragments** — a list (or set) of component sizes (in voxels) for
  components strictly below the configurable `min_fragment_voxels` threshold
  read from `HeuristicConfig`.  When `min_fragment_voxels == 0`, no component
  is below the threshold; when the threshold exceeds every component, every
  component is in `small_fragments`.

Expose all properties via a `ComponentsInfo` frozen dataclass and a
`compute_components(seg_img, label, config) -> ComponentsInfo` function in
`segqc/features/components.py`.  The `HeuristicConfig` dataclass must be
extended with a `min_fragment_voxels: int` field (default `0`).

### Connectivity convention

Use **6-connectivity** (face-neighbours only, the default for
`scipy.ndimage.label`) as the baseline. The choice must be explicit and
documented in the module; the public API should allow callers to query which
connectivity was used.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| NIfTI loading / spacing extraction | Item 003 / NiBabel header |
| Volume / extent geometry | Item 011 |
| Centroids | Item 013 |
| JSON serialisation | Item 016 |
| Heuristic rules (fragment alarm) | Stage 4 |

---

## Acceptance Criteria

- [ ] **AC1: Compact label → component_count=1, fraction=1.0**
      A label with no gaps or islands yields `component_count == 1`,
      `component_sizes == [voxel_count]`, and
      `largest_component_fraction == 1.0`.

- [ ] **AC2: Fragmented label → correct count, sizes, fraction**
      A label split into a main body (large) and an isolated island (small)
      yields `component_count == 2`, `component_sizes` sorted descending and
      summing to the total voxel count, and `largest_component_fraction ==
      large_count / total_count` (strictly less than 1.0).

- [ ] **AC3: Threshold config controls the small-fragment set**
      - Components strictly below `min_fragment_voxels` appear in
        `small_fragments`; components at or above the threshold do not.
      - `min_fragment_voxels == 0` → `small_fragments` is empty for any label.
      - `min_fragment_voxels` larger than all components → every component is
        in `small_fragments`.

- [ ] **AC4: Physical volume correct under anisotropic spacing**
      For a label with known voxel count and anisotropic spacing, each entry
      in `component_volumes_mm3` equals the corresponding voxel count ×
      product of voxel spacings.

---

## Implementation Steps

1. **Extend `src/segqc/config.py`**:
   - Add `min_fragment_voxels: int` to `HeuristicConfig` (default `0` in
     `_DEFAULTS`).

2. **Create `src/segqc/features/components.py`**:
   - `ComponentsInfo` — frozen dataclass with all documented fields.
   - `compute_components(seg_img, label, config) -> ComponentsInfo`:
     - Extract spacing from `seg_img.header.get_zooms()`.
     - Build a boolean mask `data == label`; raise `ValueError` if no voxels.
     - Run 6-connectivity connected-components via
       `scipy.ndimage.label(mask)` (or equivalent).
     - Sort components by voxel count descending.
     - Compute physical volumes from component sizes × voxel volume.
     - Compute `largest_component_fraction`.
     - Compute `small_fragments` from `config.min_fragment_voxels`.
     - Never mutate the input image.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Unit tests** (`tests/test_012_connected_components.py`): all four ACs;
  adversarial inputs (single-voxel label, all-disconnected voxels, threshold
  edges, anisotropic spacing, connectivity); immutability; determinism;
  error-message quality; import contract.
- **Fixtures**: `make_labelmap()` from `synthetic.py` for ad-hoc cases with
  controlled fragmentation geometry; `anisotropic_case()` for AC4.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 003 (NIfTI header, spacing convention)
  - Item 005 (`HeuristicConfig` — extended here with `min_fragment_voxels`)
  - Item 011 (`LabelGeometry` structure as reference)
- **Downstream:** Items 013–016 (rest of Stage 2); Stage 4 heuristics.

---

## Decisions & Trade-offs

1. **scipy.ndimage.label with default structuring element** — The default 3-D
   cross-shaped structuring element implements 6-connectivity (face-neighbours
   only) exactly as required. No explicit `structure` argument is needed,
   keeping the call simple and avoiding ambiguity. A public `CONNECTIVITY = 6`
   constant documents the choice for callers.

2. **np.bincount for component-size counting** — After `ndimage.label`, voxel
   counts per component are extracted with `np.bincount(labelled.ravel())`,
   which is O(n_voxels) and avoids repeated boolean masking per component.
   Component 0 (background) is sliced off (`counts[1:]`), and the result is
   sorted descending via `np.sort(...)[:: -1]`.

3. **Lazy scipy import** — `scipy.ndimage.label` is imported inside
   `compute_components` (same pattern as other lazy imports in this codebase)
   to avoid a hard startup cost when the module is merely imported.

4. **`small_fragments` as a `List[int]`** — A list (not a set) preserves
   duplicate sizes (two components of the same sub-threshold size both appear),
   matching the test assertions for `len(result.small_fragments) == 5` on
   all-disconnected fixtures. Order is determined by `component_sizes` order
   (descending), which is deterministic.

5. **`HeuristicConfig` extended with `min_fragment_voxels: int = 0`** —
   Added to both `_DEFAULTS` and the dataclass with a default of `0` (no
   fragment flagging by default). The field is appended last in the dataclass
   with a default value so that it does not break existing construction calls
   that pass positional arguments for the earlier three fields.

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

- `pytest tests/test_012_connected_components.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–011.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"Connected-components"** deliverable from 🚧 → ✅.
- Per `CLAUDE.md`: work on branch `aide/012-connected-components`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's
  rows, and direct-merge (no PR required) once green.
