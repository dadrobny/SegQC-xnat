# Item 025 — Fragmentation Index per Label

> **Status:** 🚧 In Progress · **Created:** 2026-06-27
> **Stage:** 2 — Geometric & Topological Feature Extraction *(enhancement)*
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 025
> **Objectives:** Topological feature engine — fragment detection (failure mode 3)
> **Suggested branch:** `aide/025-fragmentation-index`

---

## Description

Add a **fragmentation index** scalar per label — the ratio of the largest
connected component's voxel count to the total label voxel count:

```
fragmentation_index = component_sizes[0] / sum(component_sizes)
```

Range: **0 < fragmentation_index ≤ 1.0**

- Value of **1.0** → single intact body (no fragmentation).
- Values **< 1.0** → progressively split label (lower = more fragmented).

The `ComponentsInfo` dataclass (item 012) already computes
`largest_component_fraction` which equals this definition. Item 025 exposes this
value under the public name `fragmentation_index` per label:

1. **Add `compute_fragmentation_index(seg_img, label, config) -> float`** in
   `segqc/features/fragmentation.py` (or re-export from components) — a thin
   wrapper that calls `compute_components` and returns
   `result.largest_component_fraction`. This isolates the concept and provides a
   named, discoverable API used by the JSON layer.
2. **Extend the `features` JSON block** (item 016, `feature_report.py`) to
   include `fragmentation_index` per label. It sits in the existing `components`
   sub-block, aliasing `largest_component_fraction` under the new public name, so
   the JSON schema definition for `components` gains one optional/required field:
   `fragmentation_index` (number, `[0, 1]`).
3. **Extend the human-readable feature table** (`render_feature_table` in
   `human_report.py`) to display `fragmentation_index` alongside the component
   count column.
4. **Update the JSON schema** (`report_schema_v0.json`) so the `components`
   definition adds `fragmentation_index` as a required `number` in `[0, 1]`.

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Connected-components compute | Item 012 (`components.py`) |
| Centroid / geometry | Items 011, 013 |
| JSON serialisation wiring | Item 016 (`feature_report.py`) — **extended here** |
| Human report | Item 010 (`human_report.py`) — **extended here** |
| Heuristic rule using fragmentation to flag failure | Stage 4 |

---

## Acceptance Criteria

- [ ] **AC1: `compute_fragmentation_index` returns 1.0 for a single-component
      label.**
      A solid, fully-connected label with no gaps yields
      `compute_fragmentation_index(...) == 1.0`.

- [ ] **AC2: `compute_fragmentation_index` returns the correct ratio for a
      two-component label.**
      A label split into a large piece (A voxels) and a small island (B voxels)
      yields `compute_fragmentation_index(...) == A / (A + B)`, strictly less
      than 1.0.

- [ ] **AC3: `compute_fragmentation_index` returns a near-zero value for a
      highly fragmented label.**
      When a label consists of many small isolated pieces (e.g. 100 single-voxel
      components), `compute_fragmentation_index(...) ≈ 1 / total_voxel_count` —
      i.e. near zero, not zero (the largest component is a single voxel).

- [ ] **AC4: `fragmentation_index` appears in the serialised `components`
      sub-block of the JSON `features` block.**
      The dict produced by `components_to_dict(...)` contains a
      `fragmentation_index` key whose value equals
      `largest_component_fraction` for the same `ComponentsInfo` object.
      The value is a float in `[0.0, 1.0]`.

- [ ] **AC5: The extended JSON schema validates reports containing
      `fragmentation_index`.**
      A report assembled via `build_features_block` + `serialize_report` passes
      `jsonschema.validate` against the updated `report_schema_v0.json`; a
      `components` sub-block without `fragmentation_index` fails validation
      (the field is `required`).

- [ ] **AC6: The human-readable feature table includes `fragmentation_index`.**
      `render_feature_table(features_block)` returns a string that contains the
      text `fragmentation_index` or `frag` (case-insensitive) and the computed
      value for at least one label. No raw Python repr or class names appear.

- [ ] **AC7: Deterministic output.**
      Two calls to `compute_fragmentation_index` with the same inputs return
      identical values; two calls to `build_features_block` with the same inputs
      produce identical dicts (the `fragmentation_index` field is stable).

- [ ] **AC8: `compute_fragmentation_index` does not mutate its input.**
      The `seg_img` array is unchanged after the call.

---

## Implementation Steps

1. **Create `src/segqc/features/fragmentation.py`:**
   - `compute_fragmentation_index(seg_img, label, config) -> float`:
     calls `compute_components` and returns
     `result.largest_component_fraction`.
   - Export via `segqc.features.__init__` or directly from the module.

2. **Extend `components_to_dict` in `src/segqc/feature_report.py`:**
   - Add `"fragmentation_index": c.largest_component_fraction` to the dict.
   - This is a backward-compatible addition visible in all future
     `build_features_block` calls.

3. **Update `src/segqc/report_schema_v0.json`:**
   - In the `"components"` definition, add `"fragmentation_index"` to both
     `"required"` and `"properties"` (type `"number"`, `minimum: 0`,
     `maximum: 1`).

4. **Extend `render_feature_table` in `src/segqc/human_report.py`:**
   - Add `fragmentation_index` to the per-label table row (alongside
     `component_count` and `voxel_count`). Read from
     `entry["components"]["fragmentation_index"]`.

5. **Export `compute_fragmentation_index` from `src/segqc/__init__.py`**
   (add to `__all__`).

6. **Write `tests/test_025_fragmentation_index.py`** covering all ACs plus
   adversarial inputs (see Testing Strategy).

---

## Testing Strategy

- **Framework:** `pytest`.
- **Test module:** `tests/test_025_fragmentation_index.py`.
- **Fixtures:** `make_labelmap()`, `labelled_blocks_case()`,
  `anisotropic_case()` from `synthetic.py`.
- **Coverage:**
  - AC1: single-component label → index = 1.0.
  - AC2: two-component label with known A, B → exact ratio.
  - AC3: highly fragmented label (many 1-voxel components) → near-zero.
  - AC4: `components_to_dict` includes `fragmentation_index` key.
  - AC5: schema validates with the new field; schema rejects missing field.
  - AC6: `render_feature_table` output contains the value.
  - AC7: determinism (two calls, identical result).
  - AC8: immutability (input image not mutated).
  - Edge cases: single-voxel label (index = 1.0); anisotropic spacing
    (index computed from voxel counts, not volumes — should still equal 1.0
    for a compact label); label not in image raises a clear error.

---

## Dependencies

- **Upstream (all merged):**
  - Item 012 — `ComponentsInfo`, `compute_components`
    (provides `largest_component_fraction`)
  - Item 016 — `build_features_block`, `components_to_dict`,
    `report_schema_v0.json`, `render_feature_table`
- **Downstream:**
  - Stage 4 heuristics — consume `fragmentation_index` to flag fragmented labels.

---

## Decisions & Trade-offs

1. **Re-use `largest_component_fraction` from `ComponentsInfo`** — This value
   is already computed as part of item 012; item 025 exposes it under the public
   name `fragmentation_index` without re-running the component analysis.
   Avoids duplicate computation and keeps the two values in sync.

2. **`fragmentation_index` in the `components` sub-block, not as a top-level
   per-label field** — It is semantically derived from connected-components data
   and logically belongs alongside `component_count` and `component_sizes`. This
   keeps the JSON schema modular and groups related fields.

3. **`fragmentation_index` added to `required` in the schema** — Since every
   call to `build_features_block` passes a `ComponentsInfo` (which always has
   `largest_component_fraction`), the field is always present; making it
   `required` catches serialisation bugs early.

4. **`compute_fragmentation_index` is a thin wrapper in a dedicated module**
   (`src/segqc/features/fragmentation.py`) — A separate module gives the concept
   a clean, discoverable public API (importable as `segqc.features.fragmentation`)
   and keeps the connected-components logic entirely in `components.py`. The lazy
   import of `compute_components` prevents circular-import issues.

5. **`fragmentation_index` stored as `float(...)` in `components_to_dict`** —
   Explicit `float()` cast ensures the JSON value is always a Python float (not a
   numpy scalar), which serialises correctly with `json.dumps`.

6. **`frag_idx` column added to `render_feature_table` header as `frag_idx`** —
   Short enough to fit a fixed-width column while still containing the string
   `"frag"` (case-insensitive match satisfies AC6). Displayed per-label row
   alongside `Comps` before the centroid column.

7. **Golden snapshot for item 016 regenerated** — Adding `fragmentation_index`
   to `components_to_dict` changes the serialised output for any report with
   per-label data. The golden file `tests/golden/016_features_report.json` was
   regenerated programmatically to reflect the new field. The item 022 golden
   snapshot is unaffected (its `per_label` block is empty).

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

### Manual Validation Checklist

- [ ] **Env current:** `.venv/Scripts/python -c "import segqc"` succeeds.
- [ ] **Tests pass:** `.venv/Scripts/python -m pytest tests/test_025_fragmentation_index.py`
- [ ] **Full suite green:** `.venv/Scripts/python -m pytest`

### Expected Outcomes

- `compute_fragmentation_index` returns 1.0 for compact labels and correct
  ratios for fragmented labels.
- `components_to_dict` includes `fragmentation_index` in its output dict.
- `jsonschema.validate` passes on reports including the new field.
- `render_feature_table` text contains the fragmentation index value.
- Full pytest suite reports 0 failures.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"Fragmentation index"** deliverable from 📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/025-fragmentation-index`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's
  rows, and direct-merge (no PR required) once green.
