# Item 022 — Stage 3 Feature Serialisation & GT-vs-Perturbed Regression Tests

> **Status:** 🚧 In Progress · **Created:** 2026-06-27
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features *(completes Stage 3)*
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 022
> **Objectives:** Serialise Stage 3 deviation features — spline offset (018),
> orientation/curvature (019), neighbour-consistency (020) — into the JSON
> `features` block, extend the schema, and add regression tests over GT plus
> perturbed (displaced, mislabelled, missing-level) cases.
> **Suggested branch:** `aide/022-stage3-feature-serialisation`

---

## Description

Items 018, 019, and 020 compute the Stage 3 deviation features that power the
heuristic rule engine (Stage 4):

- **`VertebralSplineOffset`** (`segqc.features.spline_offset`) — per-vertebra
  closest-approach distance from the fitted spline plus a signed `(dx, dy, dz)`
  displacement vector, in both mm and voxel units.
- **`VertebralOrientation`** (`segqc.features.orientation`) — per-vertebra PCA
  principal axis (unit vector in mm-space) and eigenvalue ratio.
- **`SpineCurvature`** (`segqc.features.orientation`) — global curvature:
  per-centroid tangent angles, inter-tangent angles, and a Cobb-like total
  curvature scalar.
- **`SpacingConsistency`** (`segqc.features.consistency`) — spacing CV, mean,
  per-pair spacings/deviations, outlier pair flags.
- **`MonotonicConsistency`** (`segqc.features.consistency`) — `is_monotonic`,
  non-monotonic pairs, per-centroid spline-parameter `u` values.

This item:

1. **Extends the JSON schema** (`report_schema_v0.json`) to add a `stage3`
   sub-object inside the `features` block, with definitions for each Stage 3
   dataclass. Bumps `features_version` to `"0.2"` in the schema definition and
   in `feature_report.FEATURES_VERSION`.

2. **Adds converters** in `segqc/feature_report.py`:
   - `spline_offset_to_dict(o: VertebralSplineOffset) -> dict`
   - `orientation_to_dict(o: VertebralOrientation) -> dict`
   - `curvature_to_dict(c: SpineCurvature) -> dict`
   - `spacing_consistency_to_dict(s: SpacingConsistency) -> dict`
   - `monotonic_consistency_to_dict(m: MonotonicConsistency) -> dict`

3. **Extends `build_features_block`** to accept optional Stage 3 arguments:
   ```python
   def build_features_block(
       *,
       geometry, components, centroids,
       relationships, overlaps,
       # --- Stage 3 (all optional) ---
       spline_offsets=None,         # Sequence[VertebralSplineOffset] | None
       orientations=None,           # Sequence[VertebralOrientation]  | None
       curvature=None,              # SpineCurvature | None
       spacing_consistency=None,    # SpacingConsistency | None
       monotonic_consistency=None,  # MonotonicConsistency | None
       features_version=FEATURES_VERSION,
   ) -> dict:
   ```
   When any Stage 3 argument is non-`None`, the block gains a `"stage3"` key:
   ```json
   "stage3": {
     "per_label_offsets": [
       {"label": 1, "level_name": "L3", "closest_u": 0.42,
        "offset_mm": 0.12, "offset_voxel": 0.12,
        "dx_mm": 0.05, "dy_mm": -0.08, "dz_mm": 0.07}
     ],
     "per_label_orientations": [
       {"label": 1, "level_name": "L3",
        "principal_axis": [0.0, 0.0, 1.0], "eigenvalue_ratio": 4.5}
     ],
     "curvature": {
       "tangent_angles_deg": [2.1, 3.4, 1.8],
       "inter_tangent_angles_deg": [1.3, 1.6],
       "total_curvature_deg": 1.6
     },
     "spacing_consistency": {
       "mean_spacing_mm": 10.0, "cv_spacing": 0.02,
       "spacings_mm": [10.0, 10.0], "deviations_mm": [0.0, 0.0],
       "outlier_pairs": []
     },
     "monotonic_consistency": {
       "is_monotonic": true,
       "non_monotonic_pairs": [],
       "u_values": [0.0, 0.5, 1.0]
     }
   }
   ```
   When all Stage 3 arguments are `None`, `"stage3"` is absent and the block is
   identical to a Stage 2 (016) block — backward-compatible.

4. **Adds regression tests** (`tests/test_022_stage3_serialisation.py`) covering
   every AC plus GT-vs-perturbed scenarios:
   - **GT case**: spline offsets near-zero, `cv_spacing` low, `is_monotonic` True.
   - **Displaced centroid**: the displaced vertebra's `offset_mm` is large;
     neighbouring vertebrae remain small.
   - **Mislabelled (wrong-level)** case: spacing outlier flags the mislabelled pair.
   - **Missing-level** case: gap in present_levels, spacing outlier for the
     enlarged gap.
   - **Schema validation** of the full Stage 3 block.
   - **Deterministic golden snapshot** of the serialised JSON.

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| Computing spline offsets | Item 018 | consumed here |
| Computing orientation / curvature | Item 019 | consumed here |
| Computing spacing / monotonic consistency | Item 020 | consumed here |
| Stage 2 serialisation (`build_features_block`) | Item 016 | **extended** here |
| JSON schema (v0, `features` block) | Items 009 / 016 | **extended** here |
| Stage 4 heuristic engine | Future item | not here |

---

## Acceptance Criteria

- [ ] **AC1 — Stage 3 block appears in the validated report.** Given all five
      Stage 3 objects for a fixture, `build_features_block(..., spline_offsets=...,
      orientations=..., curvature=..., spacing_consistency=...,
      monotonic_consistency=...)` returns a dict containing a `"stage3"` key, and
      the dict passes `jsonschema.validate` against the extended schema without
      raising.

- [ ] **AC2 — Every Stage 3 sub-block is present and correctly shaped.** For a
      multi-label fixture, `features["stage3"]` contains:
      - `"per_label_offsets"` — a list of objects with `label`, `level_name`,
        `closest_u`, `offset_mm`, `offset_voxel`, `dx_mm`, `dy_mm`, `dz_mm`.
      - `"per_label_orientations"` — a list of objects with `label`, `level_name`,
        `principal_axis` (3-element array), `eigenvalue_ratio`.
      - `"curvature"` — an object with `tangent_angles_deg`,
        `inter_tangent_angles_deg`, `total_curvature_deg`.
      - `"spacing_consistency"` — an object with `mean_spacing_mm`, `cv_spacing`,
        `spacings_mm`, `deviations_mm`, `outlier_pairs`.
      - `"monotonic_consistency"` — an object with `is_monotonic`,
        `non_monotonic_pairs`, `u_values`.

- [ ] **AC3 — GT case: offsets near-zero, spacing regular, monotonic.** For a
      set of centroids that lie on a smooth synthetic spline (GT), the serialised
      `stage3.per_label_offsets[*].offset_mm` values are all < 1.0 mm,
      `stage3.spacing_consistency.cv_spacing` < 0.05, and
      `stage3.monotonic_consistency.is_monotonic == True`.

- [ ] **AC4 — Displaced centroid: offset large, others small.** When one
      centroid is displaced by ≥ 10 mm from the spline, the serialised
      `offset_mm` for the displaced vertebra is ≥ 8.0 mm; the remaining
      vertebrae have `offset_mm` < 2.0 mm.

- [ ] **AC5 — Mislabelled / spacing outlier case: outlier pair flagged.** When
      one inter-centroid gap is injected at ≥ 2× the mean (simulating a
      mislabelled or displaced vertebra that creates an abnormal gap),
      `stage3.spacing_consistency.outlier_pairs` contains at least one entry.

- [ ] **AC6 — Missing level case: gap detected in relationships.** When a
      centroid is removed from a GT sequence (simulating a missing segmentation
      level), `features.relationships.missing_levels` is non-empty and
      `stage3.spacing_consistency.outlier_pairs` flags the enlarged gap.

- [ ] **AC7 — Backward-compatible: Stage 3 absent when not supplied.** Calling
      `build_features_block` without Stage 3 arguments (all `None`) produces a
      block with no `"stage3"` key and still passes schema validation — exactly
      as per item 016.

- [ ] **AC8 — Deterministic golden snapshot.** Serialising the same Stage 3
      inputs twice yields equal dicts; `serialize_report_json(...)` for a fixture
      matches a committed golden JSON string (stable ordering within all list/dict
      fields).

- [ ] **AC9 — `features_version` bumped to `"0.2"` in the Stage 3 block.**
      When Stage 3 arguments are supplied, `features["features_version"] == "0.2"`;
      when they are absent it remains `"0.1"`.

- [ ] **AC10 — Immutability: inputs not mutated.** The converters and
      `build_features_block` do not mutate any of the Stage 3 dataclass inputs.

---

## Implementation Steps

1. **Bump `FEATURES_VERSION`** in `src/segqc/feature_report.py` from `"0.1"` to
   `"0.2"` (only when Stage 3 data is present — the function can keep `"0.1"` as
   the Stage-2-only default and use `"0.2"` when Stage 3 args are non-`None`).

2. **Add converters** in `feature_report.py`:
   - `spline_offset_to_dict(o: VertebralSplineOffset) -> dict` — serialises all
     eight fields (`label`, `level_name`, `closest_u`, `offset_mm`,
     `offset_voxel`, `dx_mm`, `dy_mm`, `dz_mm`).
   - `orientation_to_dict(o: VertebralOrientation) -> dict` — `label`,
     `level_name`, `principal_axis` (list of 3 floats from the tuple), `eigenvalue_ratio`.
   - `curvature_to_dict(c: SpineCurvature) -> dict` — `tangent_angles_deg`
     (list), `inter_tangent_angles_deg` (list), `total_curvature_deg` (float).
   - `spacing_consistency_to_dict(s: SpacingConsistency) -> dict` — all five
     fields; `outlier_pairs` becomes a list-of-two-element-lists (JSON-safe).
   - `monotonic_consistency_to_dict(m: MonotonicConsistency) -> dict` — all
     three fields; `non_monotonic_pairs` and `u_values` become lists.

3. **Extend `build_features_block`** to accept the five optional Stage 3
   arguments and, when any is non-`None`, assemble a `"stage3"` sub-dict using
   the converters above. The sub-dict has five keys:
   `per_label_offsets`, `per_label_orientations`, `curvature`,
   `spacing_consistency`, `monotonic_consistency`.
   - `per_label_offsets`: sorted ascending by `label` (same determinism rule as
     `per_label`).
   - `per_label_orientations`: sorted ascending by `label`.
   - `curvature`, `spacing_consistency`, `monotonic_consistency`: single objects
     (not per-label).

4. **Extend `report_schema_v0.json`**:
   - Add `"stage3"` as an optional property inside `#/definitions/features`.
   - Define `#/definitions/stage3` with `additionalProperties: false` and all
     five sub-definitions (`stage3OffsetEntry`, `stage3OrientationEntry`,
     `stage3Curvature`, `stage3SpacingConsistency`, `stage3MonotonicConsistency`).

5. **Write `tests/test_022_stage3_serialisation.py`** covering every AC (see
   Testing Strategy).

---

## Testing Strategy

- **Framework:** `pytest` (no external services).
- **Test module:** `tests/test_022_stage3_serialisation.py`.
- **Approach:** build Stage 3 dataclasses inline (same style as 018–020 tests:
  `LabelCentroid` objects + `fit_centroid_spline`) and feed them to the extended
  `build_features_block` and `serialize_report` — exercising the full Stage 3
  serialisation path.
- **Coverage:**
  - AC1: schema validation of Stage 3 block.
  - AC2: shape/key checks for every Stage 3 sub-block.
  - AC3: GT spline offsets < 1 mm, CV < 0.05, is_monotonic True.
  - AC4: displaced centroid offset ≥ 8 mm, others < 2 mm.
  - AC5: injected spacing outlier pair appears in the serialised block.
  - AC6: missing-level case detected in relationships and spacing outlier.
  - AC7: backward-compatible Stage 2-only block.
  - AC8: determinism + golden snapshot.
  - AC9: features_version "0.2" when Stage 3 present, "0.1" when absent.
  - AC10: input dataclasses not mutated.
  - Adversarial: single-label fixture, empty spline-offset list, None curvature,
    JSON text round-trip, malformed Stage 3 dict rejected by schema.

---

## Dependencies

- **Upstream (all merged):**
  - Item 009 — `serialize_report`, schema, `_SCHEMA`.
  - Item 016 — `build_features_block`, `feature_report.py`.
  - Item 018 — `VertebralSplineOffset`, `compute_spline_offsets`.
  - Item 019 — `VertebralOrientation`, `SpineCurvature`,
    `compute_vertebra_orientations`, `compute_spine_curvature`.
  - Item 020 — `SpacingConsistency`, `MonotonicConsistency`,
    `compute_spacing_consistency`, `compute_monotonic_consistency`.
  - NumPy, SciPy (via the existing compute functions).

---

## Decisions & Trade-offs

1. **`"stage3"` as a sub-object, not flat fields.** Grouping Stage 3 fields
   under a single `"stage3"` key isolates them from Stage 2 fields and keeps the
   schema modular. Future stages follow the same pattern.

2. **`features_version` bumped only when Stage 3 is present.** A
   Stage-2-only call keeps `"0.1"`, a Stage-3-enriched call emits `"0.2"`.
   Downstream consumers can check the version to know which keys to expect.

3. **All Stage 3 args optional (default `None`).** Callers that only have a
   subset of Stage 3 features available are not forced to compute everything.
   The schema marks `"stage3"` as optional inside `"features"`.

4. **Tuples → lists in JSON.** `principal_axis`, `tangent_angles_deg`,
   `inter_tangent_angles_deg`, `spacings_mm`, `deviations_mm`, `outlier_pairs`,
   `non_monotonic_pairs`, `u_values` are all stored as Python tuples in the
   dataclasses; the converters emit lists for JSON compatibility.

5. **`outlier_pairs` and `non_monotonic_pairs`** — list-of-two-element-lists
   `[[level_a, level_b], ...]` rather than list-of-objects, to keep the schema
   compact. The schema uses `"items": {"type": "array", "items": {"type": "string"},
   "minItems": 2, "maxItems": 2}`.

6. **Sorting within Stage 3 lists.** `per_label_offsets` and
   `per_label_orientations` are sorted ascending by `label` (integer), matching
   the `per_label` ordering convention from item 016.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + SciPy + NiBabel + `jsonschema`; no external
services, databases, or network.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- A Stage-3-bearing report validates against the extended schema.
- A Stage-2-only report still validates (backward compatible).
- GT offsets < 1 mm; displaced offsets ≥ 8 mm.
- `pytest tests/test_022_stage3_serialisation.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–021.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Stage 3 features serialised into JSON; regression tests
  GT vs perturbed"** deliverable from 📋 → ✅.
- This is the **last** Stage 3 deliverable — once it is ✅, flip the Stage 3
  summary status from 🚧 → ✅.
- Per `CLAUDE.md`: work on branch `aide/022-stage3-feature-serialisation`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
