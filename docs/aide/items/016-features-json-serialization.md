# Item 016 — Features-block JSON Serialisation & Per-Case Feature Table

> **Status:** 📋 Planned · **Created:** 2026-06-26
> **Stage:** 2 — Geometric & Topological Feature Extraction *(completes Stage 2)*
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 016
> **Objectives:** G4 — Per-case QC report (JSON + human-readable); completes the
> Stage 2 acceptance criterion *"`features` block emitted in JSON; tests cover
> each feature."*
> **Suggested branch:** `aide/016-features-json-serialization`

---

## Description

Consolidate **all Stage 2 features** — per-label geometry (011),
connected-components (012), centroids (013), inter-vertebra relationships (014),
and overlap (015) — into the versioned JSON report under a new **`features`
block**, and render a per-case **human-readable feature table**. Extend the v0
report schema ([`src/segqc/report_schema_v0.json`](../../../src/segqc/report_schema_v0.json))
to describe and validate the features block, and carry an internal
`features_version` so Stage 3 (item 022) can extend it without a breaking change.

This item is a **pure serialisation / assembly layer**. It does *not* re-derive
geometry — the compute functions already exist (011–015). It takes their output
objects, converts each to JSON-ready dicts, assembles them into one `features`
block, embeds that block in the report, validates against the extended schema,
and renders the same data as a readable table.

### What gets serialised

The `features` block has this shape (illustrative values):

```json
"features": {
  "features_version": "0.1",
  "per_label": {
    "23": {
      "label": 23,
      "level_name": "L3",
      "geometry": {
        "voxel_count": 512,
        "physical_volume_mm3": 1024.0,
        "extent_x_mm": 8.0, "extent_y_mm": 8.0, "extent_z_mm": 16.0,
        "bbox_voxel": {"x_min": 4, "x_max": 11, "y_min": 4, "y_max": 11, "z_min": 8, "z_max": 15},
        "bbox_physical": {"x_min": 8.0, "x_max": 22.0, "y_min": 8.0, "y_max": 22.0, "z_min": 16.0, "z_max": 30.0},
        "touches_inferior": false, "touches_superior": false,
        "touches_left": false, "touches_right": false,
        "touches_anterior": false, "touches_posterior": false
      },
      "components": {
        "component_count": 1,
        "component_sizes": [512],
        "component_volumes_mm3": [1024.0],
        "largest_component_fraction": 1.0,
        "small_fragments": []
      },
      "centroid": {
        "centroid_voxel": [7.5, 7.5, 11.5],
        "centroid_mm": [15.0, 15.0, 23.0]
      }
    }
  },
  "relationships": {
    "ordered_labels": [22, 23, 24],
    "neighbour_spacing_voxel": [12.0, 12.5],
    "neighbour_spacing_mm": [24.0, 25.0],
    "continuity_findings": [
      {"kind": "gap", "message": "...", "labels": [23, 24]}
    ]
  },
  "overlaps": [
    {"label_a": 23, "label_b": 24, "name_a": "L3", "name_b": "L4", "overlap_voxels": 10}
  ]
}
```

Field origins (each maps directly to an existing dataclass):

| `features` sub-block | Source (module · type) |
|---|---|
| `per_label[*].geometry` | item 011 · `segqc.features.geometry.LabelGeometry` (incl. `BBox`) |
| `per_label[*].components` | item 012 · `segqc.features.components.ComponentsInfo` |
| `per_label[*].centroid` + `label` + `level_name` | item 013 · `segqc.features.centroids.LabelCentroid` |
| `relationships` | item 014 · inter-vertebra relationship record *(see Dependencies)* |
| `overlaps` | item 015 · `segqc.features.overlap.OverlapPair` |

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| Computing geometry / components / centroids / overlaps | Items 011–013, 015 | consumed here (objects passed in) |
| Computing inter-vertebra relationships | Item 014 | consumed here (record passed in) |
| v0 report schema + `serialize_report` | Item 009 | **extended** here (add optional `features`) |
| Human-readable verdict report (`render_human_report`) | Item 010 | **extended** here (add `render_feature_table`) |
| Stage 3 deviation features (spline offset, orientation, consistency) | Item 022 | bumps `features_version`; not here |
| Per-label iteration / CLI wiring of the whole pipeline | Future CLI item | not here — assembler takes pre-computed objects |

---

## Acceptance Criteria

- [ ] **AC1 — `features` block round-trips into a validated report.** Given the
      computed feature objects for a fixture, `serialize_report(verdict, case_id,
      config, features=<block>)` returns a dict containing a top-level `features`
      key, and the dict passes `jsonschema.validate` against the extended v0
      schema without raising.

- [ ] **AC2 — Every feature family appears in the JSON.** For a multi-label
      fixture, the serialised `features.per_label[<label>]` object contains all
      three of `geometry`, `components`, and `centroid`; the block contains a
      `relationships` object and an `overlaps` array. No feature family is
      silently dropped.

- [ ] **AC3 — Anisotropic fixture round-trips correct physical volumes/extents.**
      For the anisotropic fixture, the serialised
      `geometry.physical_volume_mm3` and `geometry.extent_{x,y,z}_mm` and
      `centroid.centroid_mm` exactly equal the values returned by the source
      compute functions (within float equality), i.e. spacing is faithfully
      preserved through serialisation.

- [ ] **AC4 — Schema extension is backward-compatible.** A report produced by the
      item-009 `serialize_report` **without** features (i.e. no `features` key)
      still validates against the extended schema. The top-level
      `schema_version` remains `"0.1"`; `features` is an *optional* property.

- [ ] **AC5 — Deterministic output / golden snapshot.** Serialising the same
      inputs twice yields equal dicts; `serialize_report_json(...)` for a fixture
      equals a committed golden JSON string (stable key ordering: `per_label`
      assembled in ascending integer-label order, `overlaps` sorted by
      `(label_a, label_b)`, list fields preserved from their source order).

- [ ] **AC6 — Per-case human-readable feature table.** `render_feature_table(features_block)`
      returns a non-empty `str` that lists, per label, the level name, voxel
      count, physical volume, component count, and centroid; plus a section for
      overlaps and relationships. Output contains **no** raw Python class names,
      `repr()`, tuples, or `frozenset` text. Deterministic (sorted label order).

- [ ] **AC7 — Empty / single-label maps handled.** Assembling features for a map
      with one label produces a valid block (`overlaps == []`, `relationships`
      either an object with a single ordered label or `null`); a map with zero
      labels produces an empty `per_label`, empty `overlaps`, and a `null`/empty
      `relationships` — and still validates and renders without raising.

- [ ] **AC8 — Pure / immutable / import-clean.** The assembler and converters do
      not mutate their inputs and are deterministic. `import segqc.feature_report`
      pulls in no heavy third-party package at module level beyond what
      `report.py` already needs (`jsonschema` lazily); the converters operate on
      plain dataclasses and need neither NumPy nor NiBabel at import time.

---

## Implementation Steps

1. **Extend the schema — `src/segqc/report_schema_v0.json`:**
   - Add `features` to top-level `properties` (it stays **out** of `required`, so
     reports without it remain valid). Keep top-level `additionalProperties:
     false` (adding the property is what permits the new key).
   - Define a `#/definitions/features` object: `features_version` (string,
     required), `per_label` (object whose `additionalProperties` is a
     `#/definitions/labelFeatures`), `overlaps` (array of
     `#/definitions/overlapPair`), `relationships`
     (`#/definitions/relationships` **or** `null`).
   - Define `#/definitions/bbox` (`x_min`…`z_max`, all numbers),
     `#/definitions/labelFeatures` (`label`, `level_name`, `geometry`,
     `components`, `centroid`), `#/definitions/geometry`,
     `#/definitions/components`, `#/definitions/centroid`,
     `#/definitions/overlapPair`, `#/definitions/relationships`. Use
     `additionalProperties: false` on each so drift is caught in tests.
   - The schema `description` already says *"Extended by Stage 2 with a 'features'
     block"* — this realises it.

2. **Create `src/segqc/feature_report.py`** (the assembly/serialisation layer):
   - Converters (pure functions, dataclass → dict):
     - `_bbox_dict(bbox: BBox) -> dict`
     - `geometry_to_dict(g: LabelGeometry) -> dict`
     - `components_to_dict(c: ComponentsInfo) -> dict`
     - `centroid_to_dict(c: LabelCentroid) -> dict` → `{"centroid_voxel": [...],
       "centroid_mm": [...]}` (tuples → lists)
     - `overlap_to_dict(o: OverlapPair) -> dict`
     - `relationships_to_dict(rel) -> dict | None` (consumes the item-014 record;
       see Dependencies for the field reconciliation note)
   - `build_features_block(*, geometry, components, centroids, relationships,
     overlaps, features_version="0.1") -> dict` where `geometry`,
     `components`, `centroids` are `Mapping[int, <dataclass>]` keyed by label,
     `relationships` is the item-014 record or `None`, and `overlaps` is an
     iterable of `OverlapPair`. Assembles `per_label` in **ascending label
     order**, merging the three per-label dataclasses under one entry with
     `label` and `level_name` (taken from the centroid record); sorts `overlaps`
     by `(label_a, label_b)`; returns the `features` dict.

3. **Extend `src/segqc/report.py`:**
   - Add an optional `features: dict | None = None` parameter to
     `serialize_report(...)` and `serialize_report_json(...)`. When non-`None`,
     include it under the `features` key **before** the `jsonschema.validate`
     call (so the features block is validated too). When `None`, behave exactly
     as item 009 (no `features` key) — preserving all existing 009/010 tests.

4. **Extend `src/segqc/human_report.py`:**
   - Add `render_feature_table(features_block: dict) -> str` — a stdlib-only,
     deterministic renderer producing a per-label table plus overlaps /
     relationships sections. Export it in `__all__`. Do **not** change the
     signature of `render_human_report` (item 010 stays green); the CLI will
     concatenate the two when it wires features in.

5. **Export from `src/segqc/__init__.py`:** add `build_features_block` and
   `render_feature_table` to the public surface and `__all__`.

6. **Add the golden fixture** under `tests/` (e.g.
   `tests/golden/016_features_report.json`) for the snapshot AC.

7. **Write `tests/test_016_features_json.py`** covering every AC (see Testing).

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness); fixtures from
  [`tests`/`synthetic.py`](../../../tests) — `labelled_blocks_case()`,
  `anisotropic_case()`, ad-hoc `make_labelmap()`.
- **Test module:** `tests/test_016_features_json.py`.
- **Approach:** compute the real feature objects from a fixture
  (`compute_label_geometry`, `compute_components`, `compute_centroid`,
  `detect_overlaps`, and the item-014 relationship function), pass them to
  `build_features_block`, then to `serialize_report` — exercising the full
  consolidation path against actual data rather than mocks.
- **Coverage / adversarial cases:**
  - schema validity of feature-bearing **and** feature-free reports (AC1, AC4);
  - every family present (AC2);
  - anisotropic physical-value fidelity (AC3);
  - determinism + golden snapshot, including stable key ordering (AC5);
  - human table content + absence of `repr`/class-name/tuple/`frozenset` leakage
    (AC6);
  - single-label and zero-label maps, empty overlaps, `null` relationships
    (AC7);
  - input objects unmutated; import-time cleanliness (AC8);
  - intentionally malformed feature dict rejected by direct `jsonschema.validate`.
- **No external services, no network, no GPU.**

---

## Dependencies

- **Upstream (merged):**
  - Item 009 — `serialize_report`, `report_schema_v0.json` (the extension point).
  - Item 010 — `render_human_report` / `human_report.py`.
  - Item 011 — `LabelGeometry`, `BBox`, `compute_label_geometry`.
  - Item 012 — `ComponentsInfo`, `compute_components`.
  - Item 013 — `LabelCentroid`, `compute_centroid`.
  - Item 015 — `OverlapPair`, `detect_overlaps`.
- **Upstream (in flight — HARD dependency): Item 014 — inter-vertebra
  relationships.** At spec-writing time item 014 is claimed and in progress on
  `aide/014-inter-vertebra-relationships` and is **not yet merged**.
  **`execute-item 016` must rebase onto `main` after 014 has merged.** The exact
  field names of 014's relationship record (e.g. `ordered_labels`,
  `neighbour_spacing_voxel/_mm`, continuity findings) are **owned by 014**;
  `relationships_to_dict` and the schema's `#/definitions/relationships` must be
  reconciled against 014's actual public type when this item is executed — record
  the reconciliation in *Decisions & Trade-offs*. The shapes shown above are the
  queue-002 description's intent, not a contract 016 may impose on 014.
- **Downstream:**
  - Item 022 — serialises Stage 3 deviation features by extending this block
    (bumps `features_version`).
  - Future CLI item — calls `build_features_block` + `render_feature_table` and
    writes both report formats to disk.

---

## Decisions & Trade-offs

To be updated during implementation. Initial decisions:

1. **Additive, backward-compatible schema extension — no version bump.**
   `features` is added as an *optional* top-level property and top-level
   `schema_version` stays `"0.1"`. This keeps every item-009/010 report valid and
   their tests green (the v0 schema already advertised this extension). The
   `features` block carries its own `features_version` (`"0.1"`) so Stage 3
   (item 022) can extend it independently; a future *breaking* change to the
   report shape would bump the top-level `schema_version` / introduce a `v1`
   schema file.

2. **016 is a serialisation/assembly layer, not a compute layer.**
   `build_features_block` accepts already-computed dataclass objects keyed by
   label rather than calling the `compute_*` functions itself. This keeps the
   item pure and trivially testable, avoids duplicating per-label iteration
   logic, and leaves "iterate every present label and run all extractors" to the
   CLI/pipeline wiring item. Trade-off: the caller assembles the per-label maps;
   accepted because the tests do exactly that against fixtures.

3. **Optional `features=None` param on the existing serializer** rather than a
   new `serialize_report_v2`. One serializer, one schema, one validation call —
   features-free callers are unaffected, features-bearing callers pass the block.

4. **Separate `render_feature_table` instead of changing `render_human_report`.**
   Keeps item 010's signature and tests intact; the CLI concatenates the verdict
   report and the feature table. `human_report.py` stays stdlib-only (consumes a
   plain dict).

5. **Deterministic ordering baked in.** `per_label` assembled in ascending
   integer-label order; `overlaps` sorted by `(label_a, label_b)` (015 already
   sorts, re-sorted defensively); list fields (`component_sizes`, etc.) preserve
   their source order (already sorted by the producing module). This makes the
   golden-snapshot test stable across platforms and dict-insertion orders.

6. **Tuples → JSON arrays.** `centroid_voxel` / `centroid_mm` (Python tuples)
   serialise to JSON arrays `[x, y, z]`; `BBox` serialises to an object with the
   named `x_min`…`z_max` keys.

7. **Item-014 relationship shape is reconciled at execution time** (see
   Dependencies) — 016 does not freeze 014's API.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + NiBabel + SciPy (for component compute in tests)
+ `jsonschema`; no external services, databases, or network.

### Environment Configuration

- **Python:** 3.9+ in the project-root `.venv`.
- **Install:** `pip install -e .[dev]` (`jsonschema` already a dependency from
  item 009).
- **Environment variables / secrets:** none.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Env current:** `.venv/Scripts/python -c "import segqc"` succeeds
      (Windows Git Bash) / `.venv/bin/python -c "import segqc"` (macOS/Linux);
      rebuild via the `CLAUDE.md` bootstrap if it fails.
- [ ] **Build succeeds:** `pip install -e .[dev]` exits 0.
- [ ] **Tests pass:** `.venv/Scripts/python -m pytest tests/test_016_features_json.py`
      is green.
- [ ] **Full suite green:** `.venv/Scripts/python -m pytest` — no regressions in
      items 001–015.
- [ ] **Import check:**
      `.venv/Scripts/python -c "from segqc import build_features_block, render_feature_table; print('ok')"`
      prints `ok`.
- [ ] **Schema still valid JSON:**
      `.venv/Scripts/python -c "import json,pathlib; json.loads(pathlib.Path('src/segqc/report_schema_v0.json').read_text()); print('schema ok')"`
      prints `schema ok`.

### Expected Outcomes

- A feature-bearing report validates against the extended v0 schema; a
  feature-free (item-009) report still validates (backward compatible).
- All three per-label families + `relationships` + `overlaps` appear in the JSON.
- Anisotropic physical volumes/extents/centroid-mm round-trip exactly.
- `serialize_report_json` matches the committed golden snapshot byte-for-byte.
- `render_feature_table` produces a clean, deterministic per-case table.
- `pytest` (full suite) reports 0 failures.

### Validation Results

- [ ] Service started: N/A (no external services)
- [ ] Application started successfully: `segqc` import + pytest run
- [ ] Database tables verified: N/A
- [ ] Seed data verified: N/A
- [ ] API endpoints verified: N/A
- [ ] Schema validation verified: feature-bearing **and** feature-free reports
- [ ] Golden snapshot verified: `tests/golden/016_features_report.json`
- [ ] Screenshots captured: N/A (no UI)

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 2 **"Features serialised into JSON (`features` block) + per-case
  feature table"** deliverable from 📋 → ✅ (mark 🚧 while in progress).
- This is the **last** outstanding Stage 2 deliverable — once it and item 014 are
  ✅, tick the Stage 2 acceptance row *"`features` block emitted in JSON; tests
  cover each feature"* and flip the Stage 2 summary status from 🚧 → ✅.
- Per `CLAUDE.md`: work on branch `aide/016-features-json-serialization`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.

---

## Next Step

Ensure item 014 has merged to `main`, then start a **new chat session** and run
`/speckit-aide-execute-item 016` to implement this work item (rebase onto `main`
first so 014's relationship API is available).
