# Item 023 — EDT-Based Centroid Variants & Centroid Depth

> **Status:** ✅ Complete · **Created:** 2026-06-27
> **Stage:** 2 — Geometric & Topological Feature Extraction (enhancement)
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 023
> **Objectives:** Improve centroid quality for downstream spline/heuristic consumers
> **Suggested branch:** `aide/023-edt-centroid-depth`

---

## Description

Extend `segqc/features/centroids.py` with two additional centroid computation
methods alongside the existing CoM baseline, and add a **centroid depth** scalar
per label.

### Smooth centre

Centre of mass computed on the EDT-thresholded mask: only voxels whose EDT value
is at or above a configurable fraction of the label's maximum EDT value
(`threshold` parameter, e.g. 0.50 for 50 % or 0.75 for 75 %) are included in the
CoM. This pulls the centroid away from concave bays and surface protrusions into
the label's robust interior core.

### Strict centre

The voxel-coordinate of the peak of a Gaussian-smoothed EDT — the single deepest
interior point, in the sense of the maximum of the smoothed distance field. For
a convex label this is near the centre of the inscribed sphere; for a concave
label it is within the widest interior region. `sigma` (default 1.0 voxels) is
configurable.

### Centroid depth

The EDT value at the chosen centroid position (integer-rounded to the nearest
voxel). This is a per-label scalar quantifying how far inside the label the
centroid lies:

- High depth → centroid is well inside the label interior.
- Near-zero (< 1 voxel) → centroid lies on or very close to the label surface.
- A CoM centroid on a concave/hollow label may land outside the label or on its
  surface; depth will be 0 or very low in that case.

### C1 / C2 anatomical flag

C1 (atlas) and C2 (axis) vertebrae have no classic vertebral body; their EDT
profile is therefore different from C3–S. The result record includes a boolean
`is_atlas_axis` flag when the label's level name is `"C1"` or `"C2"`. No special
geometric treatment is applied — the flag is informational only, for downstream
consumers (Stage 4 heuristics) that want to exclude C1/C2 from body-depth rules.

### Result dataclass

Results are stored in a `CentroidFeatures` frozen dataclass (new) exported from
`segqc/features/centroids.py`:

| Field | Type | Description |
|-------|------|-------------|
| `label` | `int` | Integer label value |
| `level_name` | `str` | Anatomical name from `LabelConvention` |
| `is_atlas_axis` | `bool` | True for C1 and C2 |
| `smooth_centre_voxel` | `tuple[float,float,float]` | Smooth-centre in voxel space |
| `smooth_centre_mm` | `tuple[float,float,float]` | Smooth-centre in mm |
| `strict_centre_voxel` | `tuple[float,float,float]` | Strict-centre in voxel space |
| `strict_centre_mm` | `tuple[float,float,float]` | Strict-centre in mm |
| `centroid_depth_smooth` | `float` | EDT value at smooth-centre voxel |
| `centroid_depth_strict` | `float` | EDT value at strict-centre voxel |
| `smooth_threshold` | `float` | Threshold fraction used (0–1) |
| `strict_sigma` | `float` | Gaussian sigma used (voxels) |

The function signature:

```python
def compute_edt_centroids(
    seg_img: nib.Nifti1Image,
    label: int,
    *,
    smooth_threshold: float = 0.50,
    strict_sigma: float = 1.0,
    convention: Optional[LabelConvention] = None,
) -> CentroidFeatures:
    ...
```

Raises `ValueError` (non-empty message) if the label is absent from the image.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| CoM centroid baseline | Item 013 (`compute_centroid`) |
| NIfTI loading / spacing | Item 003 / NiBabel |
| Spline fitting | Item 017 |
| JSON serialisation of depth features | Item 024 / Stage 4 |
| EDT computation | `scipy.ndimage.distance_transform_edt` |

---

## Acceptance Criteria

- [ ] **AC1: `CentroidFeatures` dataclass is exported from
      `segqc.features.centroids`** with at minimum the fields
      `label`, `level_name`, `is_atlas_axis`, `smooth_centre_voxel`,
      `smooth_centre_mm`, `strict_centre_voxel`, `strict_centre_mm`,
      `centroid_depth_smooth`, `centroid_depth_strict`.

- [ ] **AC2: `compute_edt_centroids` is exported from
      `segqc.features.centroids`** and is callable with signature
      `(seg_img, label, *, smooth_threshold, strict_sigma, convention)`.

- [ ] **AC3: Smooth centre lies strictly closer to the geometric interior than
      the plain CoM for a hollow or concave synthetic label.** The test
      constructs a shell/hollow label (voxels only on the outer shell of a cube,
      interior empty) and asserts that `smooth_centre_voxel` is closer to the
      geometric centre of the shell than `LabelCentroid.centroid_voxel` (plain
      CoM), measured by Euclidean distance from the known interior point.

- [ ] **AC4: Strict centre lies strictly closer to the geometric interior than
      the plain CoM for a hollow or concave synthetic label.** Same hollow-label
      fixture; `strict_centre_voxel` is closer to the geometric interior than
      the plain CoM.

- [ ] **AC5: `centroid_depth_smooth` is positive for a solid (convex) label.**
      For a compact rectangular block label, the smooth centre lands inside the
      label and `centroid_depth_smooth` > 0.

- [ ] **AC6: `centroid_depth_strict` is positive for a solid (convex) label.**
      For a compact rectangular block label, `centroid_depth_strict` > 0.

- [ ] **AC7: `centroid_depth_smooth` is near-zero (< 1) for a label whose smooth
      centre lands on or very close to the surface.** Demonstrated on a
      single-voxel label or a thin-shell label.

- [ ] **AC8: `is_atlas_axis` is `True` for labels whose `level_name` is `"C1"`
      or `"C2"`, and `False` for all other anatomical levels.**

- [ ] **AC9: Anisotropic spacing is correctly propagated.** At (1,1,3) mm
      spacing, `smooth_centre_mm[2]` = `smooth_centre_voxel[2] * 3.0` and
      likewise for `strict_centre_mm`.

- [ ] **AC10: `compute_edt_centroids` is deterministic** — two calls with
      identical inputs return identical `CentroidFeatures` instances.

- [ ] **AC11: Raises `ValueError` with a non-empty message for a label absent
      from the image.**

---

## Implementation Steps

1. **Add imports** to `segqc/features/centroids.py`:
   `from scipy.ndimage import distance_transform_edt, gaussian_filter`.

2. **Define `CentroidFeatures`** frozen dataclass with all fields documented
   above.

3. **Implement `_compute_edt(mask)`** helper: returns
   `distance_transform_edt(mask)` (a float64 array, same shape as mask).

4. **Implement `compute_edt_centroids`**:
   - Extract data array (read-only view) and spacing.
   - Locate label voxels; raise `ValueError` if absent.
   - Build binary mask; compute EDT.
   - **Smooth centre**: threshold mask at `smooth_threshold * edt.max()`; compute
     CoM of thresholded mask (fall back to full EDT CoM if threshold wipes all
     voxels). Convert to mm with spacing.
   - **Strict centre**: Gaussian-smooth the EDT with `sigma=strict_sigma`;
     argmax gives the peak voxel. Convert to mm.
   - **Centroid depth**: sample EDT at integer-rounded centroid voxel for each
     variant.
   - **`is_atlas_axis`**: true when `level_name in {"C1", "C2"}`.
   - Return `CentroidFeatures`.

5. **Export** `CentroidFeatures` and `compute_edt_centroids` via `__all__`.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Unit tests** (`tests/test_023_edt_centroid_depth.py`): all eleven ACs;
  adversarial inputs: hollow label, single-voxel, empty label, anisotropic
  spacing, threshold boundary (0.0, 1.0), sigma=0, immutability, determinism,
  error-message quality, import contract.
- **Fixtures**: `make_labelmap()` with ad-hoc block and shell layouts.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 003 (NIfTI header / spacing)
  - Item 004 (label convention — `LabelConvention`, `UNKNOWN`)
  - Item 013 (`LabelCentroid`, `compute_centroid`)
- **New dependency:** `scipy.ndimage.distance_transform_edt`,
  `scipy.ndimage.gaussian_filter` (SciPy is already a project dependency).
- **Downstream:** Items 024, Stage 4 heuristics.

---

## Decisions & Trade-offs

- **Depth definition: `max(0, EDT − 0.5)`, not the raw EDT value.** The spec
  text and AC7 require a surface-adjacent centroid to read as "near-zero
  (< 1 voxel)". `scipy.ndimage.distance_transform_edt` assigns a foreground
  voxel adjacent to background a value of exactly **1.0** (distance to the
  nearest background voxel *centre*). The label *surface* lies halfway between
  those two centres, so the physically meaningful depth is `EDT − 0.5`: a
  single-voxel label or a 1-voxel-thick slab then has depth 0.5 (< 1, satisfies
  AC7), while a solid block keeps a comfortably positive depth (satisfies
  AC5/AC6). Clamped at 0 for safety, though the smooth/strict centres always
  land in foreground (EDT ≥ 1).

- **AC3/AC4 fixture changed from a symmetric U to an asymmetric "block + thin
  flap".** The smooth centre is itself a centre of mass, so on any shape with a
  mirror symmetry it lands on the symmetry axis — exactly where the plain CoM
  already sits — and can never be *strictly* closer to the interior. The
  original U-label was symmetric about y=9.5, making AC3 unsatisfiable for any
  correct CoM-based smooth centre (the implementation returned 9.5, identical to
  the CoM). The replacement fixture is asymmetric: a deep solid block plus a
  thin (low-EDT) flap that drags the plain CoM toward the flap while
  EDT-thresholding keeps the smooth centre in the deep block. Both smooth and
  strict centres are then strictly closer to the block interior than the CoM.

- **`smooth_threshold=0.0` keeps the whole label.** The thresholded mask is
  `(EDT ≥ threshold·EDTmax) & mask`; ANDing with `mask` prevents background
  (EDT = 0) voxels from being included when the threshold is 0, so the smooth
  centre degenerates to the plain CoM rather than the CoM of the entire grid.

- **`strict_sigma=0.0` is supported** — `gaussian_filter` with sigma 0 returns
  the EDT unchanged, so the strict centre becomes the raw EDT argmax.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + SciPy + NiBabel.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_023_edt_centroid_depth.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"EDT centroid depth"** deliverable from 📋 → ✅.
- Per `CLAUDE.md`: branch `aide/023-edt-centroid-depth`, `git pull --rebase`
  before editing `progress.md`, keep edits scoped to this item's rows, and
  direct-merge (no PR required) once green.
