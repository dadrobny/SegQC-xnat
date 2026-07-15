# Item 081 — Expand the reference feature vocabulary: geometric-morphology family

> **Created:** 2026-07-15 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7)
> **Queue:** [`../queue/queue-010.md`](../queue/queue-010.md) · Item 081 *(opens Stage 12; independent of VerSe data access — runs entirely against the synthetic cohort)*
> **Objectives:** G3 (reference-grounded — widen the per-level reference
> distributions from today's geometry+intensity slice to also carry the
> discriminative *morphology* scalars the Stage-2/3 engine already computes, so
> the delta-to-reference machinery can judge fragmentation/orientation against
> VerSe-derived expectations) and G7 (evaluable & regression-testable — the
> extended artifact stays pure, deterministic, and cross-platform reproducible).
> **Suggested branch:** `aide/081-expand-reference-feature-vocabulary`

---

## Description

Widen the Stage-6 reference-distribution machinery (`src/segqc/reference/*`) to
track a **new, third per-level feature family — geometric morphology** —
alongside the two families it already carries:

- **geometry** — `INGESTED_FEATURES` (`physical_volume_mm3`, `extent_x/y/z_mm`,
  `spline_offset_mm`), and
- **intensity** — `INGESTED_INTENSITY_FEATURES` (the 13 `intensity_*` scalars,
  item 063).

The morphology family adds exactly **three** per-level scalars the Stage-2/3
engine (`extract_feature_record`) **already emits**, drawn straight from the
per-label `components` block (item 012) and the Stage-3 `per_label_orientations`
block (item 019):

| Reference feature name        | Source in the features block                                   | Type  |
|-------------------------------|----------------------------------------------------------------|-------|
| `largest_component_fraction`  | `per_label[str(L)]["components"]["largest_component_fraction"]` | float |
| `component_count`             | `per_label[str(L)]["components"]["component_count"]`            | int→float |
| `eigenvalue_ratio`            | `stage3["per_label_orientations"][i]["eigenvalue_ratio"]` (matched by `label`) | float |

The work threads this family through the whole **reference path**: a new
companion vocabulary constant + ingestion read path
(`segqc.reference.ingest`), the generic aggregation core (unchanged), a new
delta-to-reference **read path** (`segqc.reference.delta`), switchable
out-of-range bounds on that delta, a `SCHEMA_VERSION` bump, and a regenerated,
committed synthetic `reference_default.json`. It follows the item-063 intensity
precedent almost exactly — a *separate* family constant with its own ingest and
delta read path, so the three families stay cleanly split.

This item is **independent of VerSe data access**: it runs entirely against the
synthetic default cohort (`build_default_cohort`), so when real VerSe is
ingested later (items 082–084) the richer distributions come for free.

### What it is — precise scope

- **The morphology family = exactly 3 features:** `largest_component_fraction`,
  `component_count`, `eigenvalue_ratio`.
- **A new, disjoint vocabulary constant** `INGESTED_MORPHOLOGY_FEATURES`, with
  its **own** ingest read path (components + orientation blocks) and its **own**
  delta read path (`compute_morphology_reference_delta`) — never routed through
  the geometry path (`_GEOMETRY_FEATURES` / `entry["geometry"]`) nor the
  intensity path (`intensity_` prefix).
- **Regenerate + commit** the synthetic `reference_default.json` so it carries
  the new family (schema `"1.2"`).
- **Switch the reference-artifact regeneration byte-identity checks to numeric
  tolerance** (item-078 `reports_close`), because `eigenvalue_ratio` is a
  platform-sensitive PCA float (see Assumptions).

### What it is NOT — deferred / out of scope

- **NOT `fragmentation_index`.** The Stage-2 `components` block exposes
  `fragmentation_index` as an **exact alias** of `largest_component_fraction`
  (`feature_report.components_to_dict`: `"fragmentation_index":
  float(c.largest_component_fraction)`). Tracking both would **double-weight**
  the same signal in the delta's distribution-distance RMS. Only
  `largest_component_fraction` is tracked; `fragmentation_index` is
  deliberately **dropped** from the reference vocabulary.
- **NOT `principal_axis`.** The orientation family contributes only the scalar
  `eigenvalue_ratio`; the `principal_axis` unit-vector is not a per-level scalar
  and is not aggregated.
- **NOT centroid-depth (EDT, item 023) and NOT spacing/neighbour-consistency
  deviation (item 024).** These are **deferred to a follow-up item** because the
  Stage-2/3 engine does **not** currently emit them as clean per-level scalars
  keyed by label: `extract_feature_record` does not call the item-023 EDT
  centroid-depth path at all, and item-024 spacing/monotonic consistency is
  emitted **case-level / pairwise** (`stage3.spacing_consistency.deviations_mm`
  is an ordered list over gaps, not a per-label scalar). Adding them therefore
  **first requires widening the Stage-2/3 engine** to emit per-level scalars —
  explicitly a separate, follow-up work item. This item touches **no**
  `src/segqc/features/**` and does not widen the engine.
- **NOT a firing heuristic rule and NOT new pipeline verdict wiring.** This item
  provides the morphology delta **computation** (`compute_morphology_reference_delta`,
  tested directly) but does **not** add a `MorphologyReferenceDeltaRule`, does
  **not** attach a `morphology_reference_delta` block inside `run_qc_*`, and does
  **not** edit `default_config.yaml`. This exactly mirrors how item 063 shipped
  the intensity reference-readiness and left the firing rule + pipeline wiring to
  item 064. A morphology firing rule + verdict wiring is a **deferred follow-up**.
  Keeping verdicts untouched is what protects the Stage-6 acceptance suite
  (048/049) and every committed golden (see AC19/AC20).

---

## Public interface (the surface this item adds / touches)

```python
# src/segqc/reference/ingest.py  (additive; existing names/behaviour preserved)

# Existing families — UNCHANGED (must NOT be widened; delta.py derives
# _GEOMETRY_FEATURES from INGESTED_FEATURES, and the intensity delta filters
# by the intensity_ prefix).
INGESTED_FEATURES: Tuple[str, ...]            # 5 geometry names — unchanged
INGESTED_INTENSITY_FEATURES: Tuple[str, ...]  # 13 intensity_* names — unchanged

# NEW: the per-level geometric-morphology vocabulary this item adds.
INGESTED_MORPHOLOGY_FEATURES: Tuple[str, ...] = (
    "largest_component_fraction",
    "component_count",
    "eigenvalue_ratio",
)

def ingest_subject(seg_path, *, config, convention=None, scan_path=None,
                   subject_id=None, with_size_proxy=True,
                   with_intensity=False,
                   with_morphology: bool = False) -> SubjectIngest: ...
def ingest_cohort(cohort_dir, *, config=None, convention=None,
                  seg_suffix=DEFAULT_SEG_SUFFIX, with_size_proxy=True,
                  with_intensity=False,
                  with_morphology: bool = False) -> CohortIngest: ...
```
```python
# src/segqc/reference/schema.py
SCHEMA_VERSION = "1.2"     # bumped from "1.1" (additive morphology vocabulary)

# src/segqc/reference/artifact.py
ARTIFACT_SCHEMA_VERSION = SCHEMA_VERSION   # auto-follows the bump ("1.2")

def build_reference(cohort_dir, *, source, build_date, config=None,
                    convention=None, seg_suffix=DEFAULT_SEG_SUFFIX,
                    size_strata_edges=None, stratum_labels=None,
                    with_intensity=True,
                    with_morphology: bool = True) -> ReferenceDistribution: ...
```
```python
# src/segqc/reference/delta.py  (additive; the geometry & intensity deltas untouched)

MORPHOLOGY_FEATURES: Tuple[str, ...]   # == INGESTED_MORPHOLOGY_FEATURES (the tracked set)

def compute_morphology_reference_delta(
    features_block: Mapping,
    reference: ReferenceDistribution,
    *,
    stratum: str = ALL_STRATUM,
    lower_pct: int = DEFAULT_LOWER_PCT,   # switchable out-of-range bound
    upper_pct: int = DEFAULT_UPPER_PCT,   # switchable out-of-range bound
) -> ReferenceDelta: ...
```

`compute_morphology_reference_delta` mirrors `compute_intensity_reference_delta`
(item 064) but scores the **morphology** subset of `reference.features` (the
names in `MORPHOLOGY_FEATURES`), reading each label's case values from its **own
read path**: `largest_component_fraction` / `component_count` from
`entry["components"]`, and `eigenvalue_ratio` from
`features_block["stage3"]["per_label_orientations"]` matched by label (exactly
as `compute_reference_delta` reads `spline_offset_mm` from
`stage3.per_label_offsets`). It reuses the shared `_feature_delta` machinery
(z / robust-z / percentile-rank / out-of-range / distribution-distance).

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. "The default cohort"
is `build_default_cohort`'s fixed `_DEFAULT_COHORT_RECIPE`. "The bundled
reference" is `bundled_default_reference()`. A "morphology-bearing" record set
is produced by ingesting the synthetic cohort with `with_morphology=True`._

### A. Family vocabulary & the 3-family split

- [ ] **AC1: The morphology vocabulary constant exists with exactly the 3
      features.** `segqc.reference.ingest.INGESTED_MORPHOLOGY_FEATURES` equals
      the ordered tuple `("largest_component_fraction", "component_count",
      "eigenvalue_ratio")` and is listed in the module's `__all__`.

- [ ] **AC2: The geometry / intensity / morphology 3-family split is
      preserved.** `INGESTED_FEATURES` still equals its original geometric
      5-tuple and `INGESTED_INTENSITY_FEATURES` still equals its 13-name tuple
      (neither widened); the three constants are **pairwise disjoint** (no name
      appears in more than one family), so no morphology name leaks into
      `INGESTED_FEATURES`.

- [ ] **AC3: `fragmentation_index` is NOT tracked.** `"fragmentation_index"`
      appears in **none** of the three family constants and in **no**
      `feature_stats` key of the rebuilt bundled reference.

### B. Ingestion read path

- [ ] **AC4: Morphology is opt-in; default ingestion is unchanged.** Calling
      `ingest_subject` / `ingest_cohort` with defaults (`with_morphology=False`)
      produces records whose `features` carry **no** morphology key
      (`largest_component_fraction` / `component_count` / `eigenvalue_ratio`) —
      existing item-044 behaviour is preserved bit-for-bit.

- [ ] **AC5: `with_morphology=True` folds in per-level morphology values from
      their own read path.** For a **multi-level** subject ingested with
      `with_morphology=True`, each recognised level's record has
      `features["largest_component_fraction"]` equal to that label's
      `components.largest_component_fraction`,
      `features["component_count"]` equal to `float(components.component_count)`,
      and `features["eigenvalue_ratio"]` equal to that label's
      `stage3.per_label_orientations` `eigenvalue_ratio` — read from the
      `components` / orientation blocks, never from `entry["geometry"]`.

- [ ] **AC6: A single-label subject degrades gracefully.** For a subject with
      exactly one recognised level (no Stage 3, so no orientations), a
      `with_morphology=True` record carries `largest_component_fraction` and
      `component_count` but **no** `eigenvalue_ratio` key (no `None` is ever
      inserted into a `features` mapping), and ingestion does not raise.

- [ ] **AC7: Morphology ingestion stays deterministic and read-only.** Two
      `ingest_cohort(..., with_morphology=True)` runs over the same cohort
      produce equal records (including every morphology value); the call mutates
      neither `config`/`convention` nor the cohort directory.

### C. Aggregation (generic core, no edit) & schema version

- [ ] **AC8: `aggregate_reference` tracks the morphology features with no core
      change.** Aggregating morphology-bearing records (via `aggregate_reference(
      records, features=None)`) yields a `ReferenceDistribution` whose `features`
      tuple includes all three morphology names, with per-level `FeatureStats`
      carrying hand/source-verifiable `count`/`mean`/percentiles — and
      `src/segqc/reference/aggregate.py` is **unmodified** in the diff.

- [ ] **AC9: Schema version bumped to `"1.2"` and enforced.**
      `schema.SCHEMA_VERSION` and the re-exported `artifact.ARTIFACT_SCHEMA_VERSION`
      equal `"1.2"` (bumped from `"1.1"`); `load_artifact` loads an artifact
      stamped `"1.2"` without raising and rejects one stamped any other version
      (e.g. `"1.1"`) with the artifact loader's version error.

### D. Build pipeline & regenerated bundled artifact

- [ ] **AC10: `build_reference` threads `with_morphology` (default on).**
      `build_reference(..., with_morphology=True)` over the default cohort
      returns a reference whose `features` include the three morphology names;
      the same call with `with_morphology=False` returns a reference with
      **none** of them.

- [ ] **AC11: The regenerated bundled artifact carries per-level morphology
      distributions.** `bundled_default_reference()` loads a reference with
      `schema_version == "1.2"` whose `features` include the three morphology
      names, and **every** lumbar level present in the default cohort (L1–L5) has
      `feature_stats` entries for `largest_component_fraction`,
      `component_count`, and `eigenvalue_ratio`, each with a well-formed
      `FeatureStats` (finite `count`/`mean`/`min`/`max`/percentiles).

- [ ] **AC12: Enabling morphology does not alter the geometric or intensity
      stats.** For the default cohort, the geometric (`INGESTED_FEATURES`) and
      intensity (`INGESTED_INTENSITY_FEATURES`) `feature_stats` produced with
      `with_morphology=True` are **equal** to those produced with
      `with_morphology=False` — the morphology family is purely additive.

### E. Delta-to-reference read path (morphology, its own path)

- [ ] **AC13: `compute_morphology_reference_delta` scores the morphology family
      via its own read path.** For a case whose features block is scored against
      the extended bundled reference, each **available** label's `LabelDelta`
      carries `FeatureDelta`s for exactly the morphology names present for that
      label (values sourced from the `components` / orientation blocks), with the
      standard z / robust-z / percentile-rank / out-of-range fields populated —
      and the geometry block (`entry["geometry"]`) is **not** its value source.

- [ ] **AC14: Out-of-range bounds are switchable on the morphology delta.**
      `compute_morphology_reference_delta` honours non-default `lower_pct` /
      `upper_pct` (e.g. `(5, 95)`): a morphology value between the `p1`/`p99`
      band but outside the `p5`/`p95` band is flagged `out_of_range` under the
      tighter pair and not under the default pair (mirroring items 046/064).

- [ ] **AC15: The geometry delta stays inert on morphology.** Running
      `segqc.reference.delta.compute_reference_delta(features_block, bundled)`
      against the **extended** bundled reference produces **no** morphology name
      in any label's `features` or `out_of_range_features` — the geometry delta
      output is unchanged by this item (`compute_reference_delta` and
      `compute_intensity_reference_delta` are byte-inert on the new features).

- [ ] **AC16: The intensity delta stays inert on morphology.**
      `compute_intensity_reference_delta(features_block, image_features, bundled)`
      against the extended bundled reference produces **no** morphology name in
      any label's `features` or `out_of_range_features` (morphology names lack
      the `intensity_` prefix and are excluded from the intensity read path).

### F. Reproducibility, tolerance switch, and scope guards

- [ ] **AC17: The regenerated artifact is deterministic (intra-platform) and
      matches the committed file within numeric tolerance.** Two successive
      `build_and_write_default(<tmp>)` calls write **byte-identical**
      `reference_default.json` (intra-platform determinism), and the regenerated
      parsed JSON equals the committed `default_artifact_path()` parsed JSON
      **within numeric tolerance** via `segqc.synth.golden.reports_close`
      (item-078 style).

- [ ] **AC18: The reference-artifact regeneration byte-identity checks switch to
      numeric tolerance.** `tests/test_045_reference_artifact.py::
      test_ac10_regenerating_reproduces_committed_bytes` and
      `tests/test_063_reference_intensity.py::
      test_ac15_bundled_artifact_regenerates_byte_identically` compare the
      **regenerated-vs-committed** artifact by parsing both and asserting
      `reports_close` (not raw `read_bytes()` equality); the intra-platform
      **two-regeneration** determinism assertion (`dest1 == dest2`) stays
      byte-exact, and both tests pass.

- [ ] **AC19: The `"1.2"` version bump keeps the suite green.** Every test that
      asserts the reference schema version now agrees with `"1.2"` — the literal
      `"1.1"` assertions in `tests/test_063_reference_intensity.py` and the
      schema-version fixture in `tests/test_aide_status_report.py` are updated to
      `"1.2"` — and the Stage-6 integration & acceptance suites
      (`tests/test_048_*`, `tests/test_049_*`) still pass unchanged (their
      geometry-only records carry no morphology block, so no verdict changes).

- [ ] **AC20: No Stage-2/3 engine or golden changes (scope guard).** The diff
      touches **no** file under `src/segqc/features/**`, does not modify
      `extract_feature_record` in `src/segqc/pipeline.py`, does not modify
      `src/segqc/reference/aggregate.py`, and leaves every committed golden under
      `tests/corpus/golden/**` and `tests/corpus/manifest.json` byte-unchanged;
      `.gitattributes` still pins `src/segqc/reference/reference_default.json
      text eol=lf` (no new pin needed — the filename is unchanged).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume`. The queue one-liner was resolved by three confirmed
human decisions (below); remaining defaults taken to reach a concrete contract
are recorded here for audit. Several **pin an interface** the builder must honour
— hand back if reality diverged.

- **Confirmed decision Q1 (engine scope = reference path only).** Item 081 is
  scoped to the reference path (ingest → aggregate → delta → config → regenerate
  default) and includes only per-level scalars `extract_feature_record` already
  emits: `largest_component_fraction`, `component_count`, `eigenvalue_ratio`.
  **Centroid-depth (EDT, item 023) and spacing/neighbour-consistency deviation
  (item 024) are deferred to a follow-up item** that must first widen the
  Stage-2/3 engine to emit them as per-level scalars (see "What it is NOT").
  **A follow-up item is needed** and should be raised for the queue-planner.

- **Confirmed decision Q2 (orientation scalar + tolerance switch).** The
  orientation contribution is the scalar `eigenvalue_ratio`; the
  `principal_axis` unit-vector is dropped (not a per-level scalar). Because
  `eigenvalue_ratio` is a **platform-sensitive PCA float** (its aggregated
  mean/std/percentiles differ in the last ~ULP across BLAS/SIMD/libm, exactly
  the item-078 phenomenon), the **regenerated-vs-committed** artifact byte-identity
  regeneration checks are switched to the **numeric-tolerance** comparison item
  078 introduced (`segqc.synth.golden.reports_close`). Intra-platform
  determinism (`dest1 == dest2`) stays byte-exact.

- **Confirmed decision Q3 (family design).** A **new companion constant**
  `INGESTED_MORPHOLOGY_FEATURES` with its **own** ingest read path and delta read
  path — a clean 3-family split (geometry / intensity / morphology) — rather than
  extending `INGESTED_FEATURES`. `fragmentation_index` is **dropped** (exact
  alias of `largest_component_fraction`; tracking both double-weights the
  distribution-distance RMS). Final feature list: `largest_component_fraction`,
  `component_count`, `eigenvalue_ratio`.

- **Morphology is opt-in at the ingest layer (`with_morphology=False` default),
  opt-in-by-default at the build layer (`build_reference` default `True`)** —
  mirroring item 063's `with_intensity`. Although morphology is always
  computable from the seg alone (no scan needed), defaulting the ingest flag to
  `False` preserves every existing `ingest_subject`/`ingest_cohort` caller
  (notably item-044 tests that assert exact feature-key sets) bit-for-bit;
  `build_reference` opts in so the produced artifact carries morphology.

- **`component_count` is tracked as a float distribution.** It is an integer in
  the `components` block; ingestion casts it `float(...)` before it enters a
  `FeatureRecord.features` value (which is `Mapping[str, float]`). For the clean
  synthetic cohort it is `1` for every vertebra, so its aggregated stats are a
  degenerate-but-well-formed distribution (`std == 0.0`, every percentile
  `== 1.0`) — finite and JSON-valid, exactly as item 043's single-value handling
  specifies.

- **`eigenvalue_ratio` is read per label from `stage3.per_label_orientations`,
  matched by integer `label`** — the same mechanism `compute_reference_delta`
  and item-044 ingestion already use for `spline_offset_mm` via
  `stage3.per_label_offsets`. It is present only when the subject has ≥ 2
  recognised levels (Stage 3 runs); for a single-level subject the key is simply
  omitted (AC6).

- **Schema bump is a minor `"1.1"` → `"1.2"`.** The change is purely additive
  (more tracked features; identical nested structure), so a minor bump is the
  defensible signal; the loader's strict version-equality then admits only the
  regenerated `"1.2"` artifact and would loudly reject a stale `"1.1"` one. The
  bump is a **shared-constant** change: sibling tests that assert the version by
  **literal** (`tests/test_063_reference_intensity.py`, and the fixture in
  `tests/test_aide_status_report.py`) are updated from `"1.1"` to `"1.2"` (AC19);
  tests that reference it **symbolically** (`SCHEMA_VERSION` /
  `ARTIFACT_SCHEMA_VERSION` imports, e.g. test_045) are unaffected, and the sole
  literal in test_045's rejection test (`"9.9"`) is unaffected. If a reviewer
  prefers `"2.0"`, it is a one-constant change.

- **The delta read path is provided, but no firing rule / pipeline verdict
  wiring is added** (see "What it is NOT"). `compute_morphology_reference_delta`
  is a pure computation tested directly; it is **not** wired into `run_qc_*` and
  no `MorphologyReferenceDeltaRule` is registered, so verdicts — and hence the
  Stage-6 acceptance suite (048/049) and every committed golden — are untouched.
  Config switchability is delivered via the delta function's `lower_pct` /
  `upper_pct` params (AC14); **no `default_config.yaml` edit** is made, keeping
  `config_hash` and the Stage-5 goldens byte-stable. Wiring a firing rule + the
  `morphology_reference_delta` block into the pipeline is a deferred follow-up
  (analogous to how item 064 followed item 063).

- **Pinned upstream interfaces (hand back if reality diverged):**
  - **Item 012** — `feature_report.components_to_dict` emits `component_count`
    (int) and `largest_component_fraction` (float) under
    `per_label[str(L)]["components"]`, plus the `fragmentation_index` alias this
    item deliberately ignores.
  - **Item 019** — `feature_report.orientation_to_dict` emits `eigenvalue_ratio`
    (float) and `label` per entry under `stage3["per_label_orientations"]`.
  - **Items 043/044/045** — the generic `aggregate_reference`; `FeatureRecord`
    (`features: Mapping[str, float]`); `ingest.py`'s per-label geometry read
    loop and `stage3.per_label_offsets` join; `artifact.py`'s `build_reference`
    / `build_default_cohort` / `build_and_write_default` / `write_artifact` /
    `load_artifact` / `bundled_default_reference` / `default_artifact_path`, and
    the strict `schema_version` check.
  - **Items 046/064** — `delta.py`'s `_feature_delta`, `ReferenceDelta` /
    `LabelDelta` / `FeatureDelta`, `reference_delta_to_dict`, and the
    `compute_intensity_reference_delta` template this item mirrors;
    `_GEOMETRY_FEATURES` and the `intensity_` prefix filtering that keep the two
    existing deltas inert on the new names.
  - **Item 063** — the current `INGESTED_INTENSITY_FEATURES`, the `"1.1"` schema,
    and the intensity-bearing `reference_default.json` this item regenerates to
    `"1.2"`.
  - **Item 078** — `segqc.synth.golden.reports_close(a, b, *, rel_tol, abs_tol)`
    (recursive parse-and-tolerance comparison; numeric leaves via
    `math.isclose`, everything else exact) — reused for the regeneration
    tolerance check.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): edit
`reference/schema.py`, `reference/ingest.py`, `reference/artifact.py`,
`reference/delta.py`, and regenerate `reference/reference_default.json`. **Do not**
edit `reference/aggregate.py`, `heuristics/**`, `config.py`,
`default_config.yaml`, `pipeline.py`'s `extract_feature_record`, `report.py`, or
any `features/*` module; **do not** add a `.gitattributes` line.

1. **`reference/schema.py`:** change `SCHEMA_VERSION = "1.1"` to
   `SCHEMA_VERSION = "1.2"`. No other edit (structure unchanged; `from_dict`
   already tolerates any version). `artifact.ARTIFACT_SCHEMA_VERSION` re-exports
   it automatically.

2. **`reference/ingest.py` — vocabulary:** add
   `INGESTED_MORPHOLOGY_FEATURES: Tuple[str, ...] = ("largest_component_fraction",
   "component_count", "eigenvalue_ratio")` and add it to `__all__`. Leave
   `INGESTED_FEATURES` and `INGESTED_INTENSITY_FEATURES` untouched.

3. **`reference/ingest.py` — `ingest_subject`:** add `with_morphology: bool =
   False`. When `True`: (a) build `orientations_by_label = {int(e["label"]):
   e["eigenvalue_ratio"] for e in (block.get("stage3") or {}).get(
   "per_label_orientations", [])}` (mirroring the existing `offsets_by_label`);
   (b) in the per-label collection loop, after the geometry `features` dict is
   built for a recognised level, add `features["largest_component_fraction"] =
   float(entry["components"]["largest_component_fraction"])` and
   `features["component_count"] = float(entry["components"]["component_count"])`,
   and, when `label_value in orientations_by_label`, add
   `features["eigenvalue_ratio"] = float(orientations_by_label[label_value])`.
   When `with_morphology=False`, behave exactly as today. Note: the size-proxy
   mean is computed over `physical_volume_mm3` and must stay unchanged.

4. **`reference/ingest.py` — `ingest_cohort`:** add `with_morphology: bool =
   False` and forward it to each `ingest_subject(...)` call.

5. **`reference/artifact.py` — `build_reference`:** add `with_morphology: bool =
   True`; forward it to `ingest_cohort(..., with_morphology=with_morphology)`.
   `build_default_cohort` needs **no** change (morphology derives from the seg,
   already written); `build_and_write_default` is unchanged (it calls
   `build_reference`, now `with_morphology=True` by default).

6. **`reference/delta.py` — morphology delta read path:** add
   `MORPHOLOGY_FEATURES` (import/alias `INGESTED_MORPHOLOGY_FEATURES`) and a
   private `_morphology_case_values(entry, orientations_by_label, label)` that
   returns the tracked morphology values present for one label:
   `largest_component_fraction` / `component_count` from `entry.get("components",
   {})` (cast `component_count` to `float`), and `eigenvalue_ratio` from
   `orientations_by_label` when present. Add `compute_morphology_reference_delta`
   mirroring `compute_intensity_reference_delta`: build `orientations_by_label`
   from `features_block["stage3"]["per_label_orientations"]`, filter
   `reference.features` to the `MORPHOLOGY_FEATURES` subset, and score via the
   shared `_feature_delta`. Export it in `__all__` and re-export from
   `reference/__init__.py`. **Do not** modify `compute_reference_delta` or
   `compute_intensity_reference_delta`.

7. **Regenerate + commit the bundled artifact:** run
   `.venv/Scripts/python -m segqc.reference.artifact` to rewrite
   `src/segqc/reference/reference_default.json` (version `"1.2"`, now carrying
   per-level morphology distributions) and commit it with the code. Confirm
   `.gitattributes` already pins it — no edit there.

8. **Keep every change additive** and behaviour-preserving for
   `with_morphology=False`; make no `aggregate.py` / heuristics / config / golden
   change.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_081_reference_morphology.py`,
  in the style of `tests/test_063_reference_intensity.py` (import
  `build_clean_spine`, `ingest_subject`/`ingest_cohort`, `aggregate_reference`,
  `build_reference`, `build_default_cohort`, `build_and_write_default`,
  `bundled_default_reference`, `load_artifact`, `compute_reference_delta`,
  `compute_intensity_reference_delta`, `compute_morphology_reference_delta`,
  `INGESTED_MORPHOLOGY_FEATURES`, and `segqc.synth.golden.reports_close`).
- **Helpers:** a `_extract(seg_img)` wrapper over `extract_feature_record` to
  read the authoritative `components` / `per_label_orientations` values a record
  must match; a `_geom_intensity_stats(dist)` filter selecting the
  `INGESTED_FEATURES ∪ INGESTED_INTENSITY_FEATURES` subset of a level's
  `feature_stats` for the additivity check (AC12).
- **Group A — vocabulary & split (AC1–AC3):** constant contents (AC1);
  three-family disjointness + geometry/intensity unchanged (AC2);
  `fragmentation_index` absent everywhere including a rebuilt-artifact
  `feature_stats` scan (AC3).
- **Group B — ingestion (AC4–AC7):** default geometry-only (AC4); morphology
  values match the extractor per label for a multi-level subject, sourced from
  components/orientation not geometry (AC5); single-label subject omits
  `eigenvalue_ratio`, no crash, no `None` (AC6); determinism + read-only (AC7).
- **Group C — aggregation & version (AC8–AC9):** aggregate morphology-bearing
  records, assert names in `dist.features` + hand-verifiable `FeatureStats`, and
  guard `aggregate.py` unmodified (AC8); `SCHEMA_VERSION` /
  `ARTIFACT_SCHEMA_VERSION == "1.2"`, loader accept/reject (AC9).
- **Group D — build & bundled artifact (AC10–AC12):** `build_reference` on/off
  (AC10); `bundled_default_reference()` carries `"1.2"` + per-level morphology
  `feature_stats` for L1–L5 (AC11); geometric+intensity stats identical on/off
  morphology (AC12).
- **Group E — delta read path (AC13–AC16):** `compute_morphology_reference_delta`
  over a clean case scored against the extended bundled reference yields
  per-label morphology `FeatureDelta`s sourced from the right blocks (AC13);
  a hand-built case value between `p1/p99` but outside `p5/p95` flips
  `out_of_range` under the tighter bound pair (AC14); `compute_reference_delta`
  and `compute_intensity_reference_delta` produce no morphology name anywhere
  (AC15/AC16).
- **Group F — reproducibility, tolerance switch, scope guards (AC17–AC20):**
  double `build_and_write_default` byte-identity + `reports_close` vs the
  committed file (AC17); **edit** `test_045`'s `test_ac10_...` and `test_063`'s
  `test_ac15_...` to compare regenerated-vs-committed via parsed `reports_close`
  while keeping the two-regeneration `dest1 == dest2` byte-exact, and confirm
  both pass (AC18); update the `"1.1"` literal version assertions in `test_063`
  and the `test_aide_status_report.py` fixture to `"1.2"`, and confirm
  `test_048_*` / `test_049_*` still pass (AC19); a diff-scope guard asserting no
  `src/segqc/features/**`, no `aggregate.py`, no `extract_feature_record`, and no
  `tests/corpus/golden/**` change, with the `.gitattributes` pin present (AC20).
- **Adversarial / edge cases (beyond the ACs):**
  - A cohort mixing a multi-level and a single-level subject under
    `with_morphology=True` yields `eigenvalue_ratio` for the former's levels only
    (no crash).
  - A **fragmented** synthetic case (component_count > 1, largest fraction < 1)
    produces distinct, finite morphology values and a non-trivial delta —
    exercising the discriminative signal, not just the degenerate clean case.
  - `from_dict(to_dict(dist))` round-trips a morphology-bearing reference; a
    `with_morphology=False` reference still writes and loads under `"1.2"`
    (backward tolerance).
  - Re-running `python -m segqc.reference.artifact` over the committed file
    reproduces bytes identical to a fresh regeneration on the same platform
    (idempotent, intra-platform).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 012** — `components` block (`component_count`,
    `largest_component_fraction`, and the `fragmentation_index` alias this item
    drops).
  - **Item 019** — `stage3.per_label_orientations` (`eigenvalue_ratio`,
    `principal_axis`, `label`).
  - **Item 025** — `fragmentation_index` alias (the redundancy this item avoids
    double-counting).
  - **Items 043/044/045** — the reference schema + generic `aggregate_reference`,
    the ingestion driver (`INGESTED_FEATURES`, the geometry/`stage3` join), and
    the artifact builder/loader + committed `reference_default.json`.
  - **Items 046/047** — the delta computation (`compute_reference_delta`,
    `_feature_delta`, `ReferenceDelta`/`LabelDelta`/`FeatureDelta`,
    `reference_delta_to_dict`) and the delta rule family (context for the
    deferred firing-rule follow-up).
  - **Item 048** — the reference-derived bounds switch (context: this item makes
    no `default_config.yaml` change; switchability is via the delta's
    `lower_pct`/`upper_pct`).
  - **Item 049** — the Stage-6 integration & acceptance suite that must stay green
    (AC19).
  - **Items 063/064** — the intensity family (`INGESTED_INTENSITY_FEATURES`, the
    `"1.1"` schema, `compute_intensity_reference_delta`, the intensity-bearing
    `reference_default.json`) — the precedent this item mirrors and the current
    artifact/schema state it advances to `"1.2"`.
  - **Item 078** — `segqc.synth.golden.reports_close`, reused for the
    regeneration numeric-tolerance comparison.
- **Downstream (this item enables):** items 082/083/084 (real-VerSe grounding)
  inherit the richer distributions for free; a **deferred follow-up** widens the
  Stage-2/3 engine for centroid-depth + spacing/neighbour deviation and adds the
  morphology firing rule + pipeline verdict wiring.

## Decisions & Trade-offs

Implementation followed the spec's Implementation Steps and Assumptions
exactly; no divergence from the pinned upstream interfaces was found. Notes:

- `schema.SCHEMA_VERSION` bumped `"1.1"` -> `"1.2"`; `artifact.ARTIFACT_SCHEMA_VERSION`
  re-exports it automatically (no separate edit needed there beyond the
  existing `= SCHEMA_VERSION` assignment).
- `ingest.py`: added `INGESTED_MORPHOLOGY_FEATURES` (added to `__all__`),
  `with_morphology: bool = False` on both `ingest_subject` and
  `ingest_cohort` (forwarded), and an `orientations_by_label` map built
  alongside the existing `offsets_by_label` map from `stage3.per_label_orientations`.
  In the per-label collection loop, when `with_morphology=True`,
  `largest_component_fraction` / `component_count` are read from
  `entry["components"]` unconditionally (that block is always present per
  label in `extract_feature_record`'s output) and `eigenvalue_ratio` is
  added only `if label_value in orientations_by_label` (single-level
  subjects have no Stage 3, hence no orientations, hence the key is simply
  omitted -- never `None`).
- `artifact.py`: `build_reference` gained `with_morphology: bool = True`
  (opt-in by default at this layer, mirroring item 063's `with_intensity`),
  forwarded to `ingest_cohort`. `build_default_cohort` needed no change
  (morphology derives from the seg alone, already written by
  `build_clean_spine`).
- `delta.py`: added `MORPHOLOGY_FEATURES` (alias of
  `INGESTED_MORPHOLOGY_FEATURES`), a private `_morphology_case_values`
  helper mirroring `_intensity_case_values`'s shape (reads
  `entry["components"]` and an `orientations_by_label` map built from
  `features_block["stage3"]["per_label_orientations"]`; never reads
  `entry["geometry"]`), and `compute_morphology_reference_delta` mirroring
  `compute_intensity_reference_delta`'s structure exactly (same
  available/unavailable label handling, same `_feature_delta`/
  `_distribution_distance` reuse, same `lower_pct`/`upper_pct` percentile
  validation). `compute_reference_delta` and `compute_intensity_reference_delta`
  were left byte-for-byte unmodified. `aggregate.py` was not touched (the
  generic aggregation core needed no change, per AC8/AC20).
- Re-exported `INGESTED_MORPHOLOGY_FEATURES`, `INGESTED_INTENSITY_FEATURES`
  (previously not re-exported at the package level; added while touching
  this block for consistency with the sibling geometry/morphology
  constants), `MORPHOLOGY_FEATURES`, and `compute_morphology_reference_delta`
  from `segqc/reference/__init__.py`, matching the pattern already used for
  the geometry/intensity siblings.
- Regenerated `src/segqc/reference/reference_default.json` via
  `python -m segqc.reference.artifact`. The diff is purely additive: a new
  `schema_version: "1.2"`, three new `features` entries, and new
  `component_count` / `eigenvalue_ratio` / `largest_component_fraction`
  `feature_stats` blocks under every level/stratum -- every existing
  geometric/intensity `feature_stats` value is byte-unchanged (confirmed by
  inspecting the diff: the only removed line is the old `schema_version`
  literal). No `.gitattributes` edit was needed -- the existing
  `src/segqc/reference/reference_default.json text eol=lf` pin already
  covers the regenerated file (same filename).
- No CLI (`segqc build-reference`) change was made; it calls `build_reference`
  without an explicit `with_morphology` argument, so it now opts into
  morphology by the new default, consistent with `with_intensity`'s existing
  default-`True` behaviour at that layer.
