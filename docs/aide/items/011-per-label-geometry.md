# Item 011 — Per-label Geometric Features

> **Status:** 🚧 In Progress · **Created:** 2026-06-25
> **Stage:** 2 — Geometric & Topological Feature Extraction
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 011
> **Objectives:** Feature engine foundation (inputs to G2 heuristics)
> **Suggested branch:** `aide/011-per-label-geometry`

---

## Description

Compute the following geometric properties for each vertebra label in an
instance label map:

- **voxel_count** — number of voxels with that integer label value.
- **physical_volume_mm3** — `voxel_count * product(voxel_spacings)` in mm³,
  using voxel dimensions from the NiBabel header (`get_zooms()`).
- **extent_x/y/z_mm** — physical span of the label along each image axis in mm,
  defined as `(max_voxel_index - min_voxel_index + 1) * spacing` (inclusive
  voxel count times spacing).
- **bbox_voxel** — axis-aligned bounding box in integer voxel indices (inclusive
  at both ends), exposed as a `BBox` dataclass with `x_min`, `x_max`, `y_min`,
  `y_max`, `z_min`, `z_max`.
- **bbox_physical** — same bounding box in mm (voxel-centre convention:
  `voxel_index * spacing`), also a `BBox`.
- **border-contact flags** — six booleans indicating whether the label touches
  each face of the image volume:
  - `touches_inferior` (x = 0)
  - `touches_superior` (x = shape[0]-1)
  - `touches_left`     (y = 0)
  - `touches_right`    (y = shape[1]-1)
  - `touches_anterior` (z = 0)
  - `touches_posterior`(z = shape[2]-1)

Expose all properties via a `LabelGeometry` frozen dataclass and a
`compute_label_geometry(seg_img, label)` function in
`segqc/features/geometry.py`.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| NIfTI loading / spacing extraction | Item 003 / NiBabel header |
| Connected-components analysis | Item 012 |
| Centroids | Item 013 |
| JSON serialisation | Item 016 |
| Heuristic rules (border-partial flag) | Stage 4 |

---

## Acceptance Criteria

- [ ] **AC-1 Physical volume and extent verified against hand-computed
      expectations**: `compute_label_geometry` returns correct `voxel_count`,
      `physical_volume_mm3`, and `extent_x/y/z_mm` for the `labelled_blocks_case`
      and `anisotropic_case` fixtures, matching hand-computed values.
- [ ] **AC-2 Anisotropic-spacing fixture yields correct physical values**:
      label 1 in `anisotropic_case` (spacing (1,1,3)mm, 4×4×3-voxel block)
      has `physical_volume_mm3 == 144.0` and `extent_z_mm == 9.0`.
- [ ] **AC-3 Border-contact flags correct for labels at/away from image faces**:
      - A fully-interior label has all six flags `False`.
      - A label touching any image face has the corresponding flag `True`.
      - A label filling the entire volume has all six flags `True`.
- [ ] **AC-4 Functions are deterministic**: two calls with identical inputs
      produce identical `LabelGeometry` instances.

---

## Implementation Steps

1. **Create `src/segqc/features/__init__.py`** — empty subpackage marker with a
   brief docstring.
2. **Create `src/segqc/features/geometry.py`**:
   - `BBox` — frozen dataclass with `x_min`, `x_max`, `y_min`, `y_max`,
     `z_min`, `z_max` (float fields; for voxel bboxes the values are integers
     stored as float or int — tests accept either).
   - `LabelGeometry` — frozen dataclass with all documented fields.
   - `compute_label_geometry(seg_img, label) -> LabelGeometry`:
     - Extract spacing from `seg_img.header.get_zooms()`.
     - Locate voxels: `np.argwhere(data == label)`.
     - Raise `ValueError` with a non-empty message if the label is absent.
     - Compute all fields from the voxel coordinate array; never mutate the
       input image.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Unit tests** (`tests/test_011_geometry.py`): all four ACs; adversarial
  inputs (single-voxel label, corner voxel, label spanning full axes, missing
  label); immutability; dataclass field contract; `BBox` ordering.
- **Fixtures**: `labelled_blocks_case()`, `anisotropic_case()`, and ad-hoc
  `make_labelmap()` calls for face-contact cases — all from `synthetic.py`.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures — `make_labelmap`, `labelled_blocks_case`,
    `anisotropic_case`)
  - Item 003 (NIfTI header, spacing convention)
- **Downstream:** Items 012–016 (the rest of Stage 2); Stage 4 heuristics.

---

## Decisions & Trade-offs

1. **`segqc.features` subpackage**: Stage 2/3 each introduce multiple feature
   modules; grouping them under `segqc/features/` avoids polluting the top-level
   package namespace and mirrors the roadmap's stage structure.

2. **`BBox` as a named dataclass**: attribute access (`bb.x_min`, `bb.z_max`)
   is more readable and introspectable than a plain tuple. Kept frozen for
   immutability and cheap equality comparison.

3. **Extent = (max - min + 1) * spacing**: the inclusive voxel count is the
   physically intuitive span (a 4-voxel-wide block occupies 4 mm at 1mm
   isotropic). This matches the test expectations.

4. **Physical bbox uses voxel-centre convention**: `physical_coord = voxel_index
   * spacing` (no 0.5-voxel offset). The affine in all current fixtures is a
   pure diagonal (origin at zero), making voxel-centre and voxel-corner
   conventions equivalent — tests assert with `abs=1.0` tolerance.

5. **Border-contact via bounding-box min/max**: checking `x_min == 0` and
   `x_max == shape[0]-1` is equivalent to scanning all voxels and is O(1) after
   the argwhere call. The face-to-name mapping (x=inferior/superior, etc.) is a
   pragmatic convention documented in the module docstring; callers with a
   reliable RAS header can remap.

6. **Missing label raises `ValueError`**: an absent label most likely indicates a
   caller bug (wrong label integer) and returning a zero-count sentinel would
   propagate silently. A clear ValueError surfaces the mistake immediately. Tests
   accept `ValueError`, `KeyError`, or `LookupError`.

7. **No top-level `segqc.__init__` export**: `LabelGeometry` is an internal
   feature type consumed by the Stage 2 pipeline, not a primary public API
   symbol. It stays under `segqc.features.geometry` and is not re-exported from
   `segqc.__init__`.

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

- `pytest tests/test_011_geometry.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–010.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"Per-label features"** deliverable from 🚧 → ✅.
- Per `CLAUDE.md`: work on branch `aide/011-per-label-geometry`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's rows,
  and direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 012` to
implement the next Stage 2 item (connected-components analysis per label).
