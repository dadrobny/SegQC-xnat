# Item 063 — Extend reference distributions with per-level intensity features

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features (Phase 2)
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 063
> **Objectives:** G3 (reference-grounded — teach the Stage-6 reference machinery to
> carry per-level *intensity* distributions so item 064's delta rule grounds
> intensity judgements in VerSe-derived expectations, not hand-guessed HU
> constants), G7 (evaluable & regression-testable — the extended artifact stays
> pure, deterministic, and byte-reproducible).
> **Suggested branch:** `aide/063-extend-reference-distributions-with-per`

---

## Description

Extend the **Stage-6 reference-distribution machinery**
(`src/segqc/reference/*`) so it **also** tracks **per-level first-order intensity
feature distributions** (mean / std / percentiles / … of HU per vertebra level),
alongside the geometric distributions it already carries
(`physical_volume_mm3`, `extent_x/y/z_mm`, `spline_offset_mm`). This realises
Stage-8 deliverable 3's first half: the *extended reference artifact* that item
064's level-aware delta-to-reference **intensity** rule will consume.

The Stage-6 aggregation core is **already generic**: item 043 designed
`FeatureRecord.features` as an open `Mapping[str, float]` and
`aggregate_reference` derives its tracked-feature set as the sorted union of the
keys present across records (`aggregate.py` `_resolve_features`), storing
per-`(level, stratum, feature)` summary stats regardless of feature name (see
item 043 Description "Deliberately decoupled design" and Decisions log). So
**the aggregation math needs no change** — this item's work is almost entirely
on the **ingestion** side plus a schema-version bump and an artifact rebuild:

1. **Ingestion (`src/segqc/reference/ingest.py`)** — teach `ingest_subject` /
   `ingest_cohort` to (opt-in) load the **sibling scan** that is already
   discovered but currently unread (its docstring calls `scan_path` "threaded
   through for a future feature that needs it" — this is that feature) and, using
   item 059's `compute_intensity_features` / `compute_label_intensity`, compute
   per-label first-order intensity statistics and fold them into each recognised
   level's `FeatureRecord.features` under a documented `intensity_`-prefixed
   vocabulary. Guarded so it degrades to geometry-only when no scan is present
   (backward-tolerant) and never inserts a non-finite/`None` value.

2. **Tracked-feature vocabulary** — add a **new companion constant**
   `INGESTED_INTENSITY_FEATURES` for the intensity names; leave the existing
   geometric `INGESTED_FEATURES` **unchanged** (see the *critical coupling* note
   under Assumptions — widening `INGESTED_FEATURES` would silently break
   `delta.py`'s `_GEOMETRY_FEATURES` derivation and prematurely activate item
   064's work).

3. **Schema version bump (`src/segqc/reference/schema.py`)** — bump
   `SCHEMA_VERSION` (re-exported by `artifact.py` as `ARTIFACT_SCHEMA_VERSION`)
   to signal the extended reference vocabulary; the loader's strict
   version-equality check then admits only the new version.

4. **Artifact rebuild (`src/segqc/reference/artifact.py`)** — thread a
   `with_intensity` flag through `build_reference` (default **on**), have
   `build_default_cohort` **also paint and write** a co-registered scan per
   subject via item 058's `paint_clean_scan`, and **regenerate + commit** the
   bundled `reference_default.json` so it now carries per-level intensity
   distributions. The artifact stays byte-reproducible and remains pinned in
   `.gitattributes` (already present — no new pin needed).

### Scope boundary — what this item is **not**

- **No delta metric and no rule.** Item 063 does **not** add or modify any
  delta-to-reference scoring for intensity: it does **not** touch
  `src/segqc/reference/delta.py` or `src/segqc/heuristics/reference_delta.py`.
  The level-aware intensity delta rule is **item 064**. An AC below asserts the
  existing delta computation stays **inert** on the new intensity reference
  features (case values carry no intensity, so `delta.py` skips them).
- **No `segqc run` / CLI wiring.** Computing intensity features during a normal
  `segqc run` case (fusion is item 061, already merged) and adding a CLI knob to
  enable the intensity path end-to-end is **item 065**. This item only extends
  the **reference-building** pipeline and the committed artifact.
- **No new intensity extractor.** It **reuses** item 059's
  `segqc.features.intensity` unchanged; it computes no new statistics.
- **No aggregation-math change.** `aggregate.py` is not edited — its generic
  per-feature machinery already handles the intensity features (an AC verifies
  this by asserting intensity stats appear with no core change).
- **No full VerSe-scale rebuild required.** Correctness is provable over a small
  painted synthetic GT+scan cohort (leaning on item 058's HU painter); the
  mounted-real-VerSe path remains a documented, reproducible option, exactly as
  the Stage-6 mounted-VerSe path is.

---

## Public interface (the surface item 064 / 065 consume)

```python
# src/segqc/reference/ingest.py  (additive; existing names/behaviour preserved)

# Existing geometric vocabulary — UNCHANGED (delta.py derives _GEOMETRY_FEATURES
# from this; must NOT be widened).
INGESTED_FEATURES: Tuple[str, ...] = (
    "physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm",
    "spline_offset_mm",
)

# NEW: the per-level intensity vocabulary this item adds (intensity_-prefixed
# LabelIntensity statistics; see Assumptions for the pinned name set).
INGESTED_INTENSITY_FEATURES: Tuple[str, ...] = (
    "intensity_mean", "intensity_median", "intensity_std",
    "intensity_min", "intensity_max",
    "intensity_p05", "intensity_p25", "intensity_p50",
    "intensity_p75", "intensity_p95",
    "intensity_range", "intensity_iqr", "intensity_entropy",
)

def ingest_subject(seg_path, *, config, convention=None, scan_path=None,
                   subject_id=None, with_size_proxy=True,
                   with_intensity: bool = False) -> SubjectIngest: ...
def ingest_cohort(cohort_dir, *, config=None, convention=None,
                  seg_suffix=DEFAULT_SEG_SUFFIX, with_size_proxy=True,
                  with_intensity: bool = False) -> CohortIngest: ...
```
```python
# src/segqc/reference/schema.py
SCHEMA_VERSION = "1.1"     # bumped from "1.0" (additive intensity vocabulary)

# src/segqc/reference/artifact.py
ARTIFACT_SCHEMA_VERSION = SCHEMA_VERSION   # auto-follows the bump ("1.1")

def build_reference(cohort_dir, *, source, build_date, config=None,
                    convention=None, seg_suffix=DEFAULT_SEG_SUFFIX,
                    size_strata_edges=None, stratum_labels=None,
                    with_intensity: bool = True) -> ReferenceDistribution: ...
```

Feature names are stored as record `features` keys; a level's intensity stats are
present iff a grid-aligned scan was supplied **and** that label's
`LabelIntensity` is a populated (non-sentinel) record.

---

## Acceptance Criteria

_One test per criterion, atomic and observable. "The default cohort" is the fixed
`_DEFAULT_COHORT_RECIPE` under `build_default_cohort`. "A painted case" is a seg
from `build_clean_spine(...)` plus `paint_clean_scan(seg_img)` (item 058). "The
extractor" is `segqc.features.intensity.compute_label_intensity`. "The bundled
reference" is `bundled_default_reference()`._

### A. Intensity vocabulary & ingestion

- [ ] **AC1: New intensity vocabulary constant; geometry vocabulary unchanged.**
      `segqc.reference.ingest.INGESTED_INTENSITY_FEATURES` equals the documented
      13 `intensity_`-prefixed names (see Assumptions) as an ordered tuple, and
      `INGESTED_FEATURES` still equals its original geometric 5-tuple
      (`physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`,
      `spline_offset_mm`) — no intensity name leaks into it.

- [ ] **AC2: Intensity is opt-in; default ingestion is geometry-only.** Calling
      `ingest_subject`/`ingest_cohort` with defaults (`with_intensity=False`) on a
      subject that **has** a sibling `_scan.nii.gz` produces records whose
      `features` keys contain **no** `intensity_*` key (only the existing
      geometric keys) — existing item-044 behaviour is preserved bit-for-bit.

- [ ] **AC3: `with_intensity=True` + aligned scan folds in per-label intensity
      stats.** For a painted case ingested with `with_intensity=True`, each
      recognised level's record `features["intensity_<stat>"]` equals the
      corresponding field of `compute_label_intensity(scan_img, seg_img, label)`
      for that level's integer label, for every intensity name whose extractor
      field is non-`None` (e.g. `features["intensity_mean"] == LabelIntensity.mean`).

- [ ] **AC4: `with_intensity=True` with no scan degrades to geometry-only.**
      Ingesting a subject that has a `_seg.nii.gz` but **no** sibling scan, with
      `with_intensity=True`, does not raise and yields geometric-only records (no
      `intensity_*` keys) — backward-tolerant.

- [ ] **AC5: Sentinel intensity contributes no key (never a `None` value).** For a
      label whose `LabelIntensity` is the all-`None` sentinel (e.g. a scan whose
      voxels under that label are all NaN/inf), that record carries **no**
      `intensity_*` key for the sentinel stats — `None` is never inserted into a
      `features` mapping (so downstream `float(value)` in `aggregate_reference`
      never sees `None`).

- [ ] **AC6: A grid-misaligned scan raises, not silently mis-sampled.** With
      `with_intensity=True` and a scan whose shape/affine mismatches the seg beyond
      the extractor's tolerance, `ingest_subject` raises `ValueError` (surfaced from
      `compute_intensity_features`), rather than producing wrong intensity stats.

- [ ] **AC7: Ingestion stays deterministic and read-only.** Two
      `ingest_cohort(..., with_intensity=True)` runs over the same painted cohort
      produce equal records (including every `intensity_*` value); the call mutates
      neither `config`/`convention` nor the cohort directory contents.

### B. Aggregation (generic core, no edit) & schema version

- [ ] **AC8: `aggregate_reference` tracks intensity features with no core change.**
      Aggregating the intensity-bearing records of a small painted cohort (via
      `aggregate_reference(records, ...)` with `features=None`) yields a
      `ReferenceDistribution` whose `features` tuple includes every geometric name
      **and** every `intensity_*` name present in the records, and whose per-level
      `feature_stats` carry `FeatureStats` for the intensity features with
      hand/extractor-verifiable `count`/`mean`/percentiles — and `aggregate.py` is
      unmodified in the diff.

- [ ] **AC9: Schema version bumped and enforced.** `schema.SCHEMA_VERSION` and the
      re-exported `artifact.ARTIFACT_SCHEMA_VERSION` equal `"1.1"` (bumped from
      `"1.0"`); `load_artifact` loads an artifact stamped `"1.1"` without raising
      and rejects one stamped any other version (e.g. `"1.0"`) with
      `ReferenceArtifactError`.

### C. Build pipeline & bundled artifact

- [ ] **AC10: `build_reference` threads `with_intensity` (default on).**
      `build_reference(cohort_dir, source=..., build_date=..., with_intensity=True)`
      over a scan-bearing cohort returns a reference whose `features` include the
      `intensity_*` names; the same call with `with_intensity=False` returns a
      geometric-only reference (no `intensity_*` names).

- [ ] **AC11: `build_default_cohort` writes a painted, aligned scan per subject.**
      After `build_default_cohort(dest)`, every subject has both a
      `<subject_id>_seg.nii.gz` and a `<subject_id>_scan.nii.gz`; the scan loads,
      is grid-aligned with the seg (`load_case` succeeds), and its int16 array is
      byte-reproducible across two `build_default_cohort` runs.

- [ ] **AC12: The regenerated bundled artifact carries per-level intensity
      distributions.** `bundled_default_reference()` loads a reference with
      `schema_version == "1.1"` whose `features` include the `intensity_*` names,
      and every lumbar level present in the default cohort (L1–L5) has
      `feature_stats` entries for the tracked intensity features.

- [ ] **AC13: Enabling intensity does not alter geometric stats.** For the default
      cohort, the geometric `feature_stats` (the `INGESTED_FEATURES` names) produced
      with `with_intensity=True` are **equal** to those produced with
      `with_intensity=False` — intensity distributions are purely additive and do
      not perturb any geometric distribution.

- [ ] **AC14: The existing delta computation stays inert on intensity.** Running
      `segqc.reference.delta.compute_reference_delta(features_block, bundled)` for a
      geometric feature block against the **extended** bundled reference produces
      **no** `intensity_*` name in any label's `features` or `out_of_range_features`
      (the case carries no intensity values, so the intensity reference features are
      skipped) — the geometric delta output is unchanged by this item.

### D. Reproducibility & backward-tolerance

- [ ] **AC15: The bundled artifact regenerates byte-identically.** Two successive
      `build_and_write_default(<tmp>)` calls write byte-for-byte identical
      `reference_default.json`, and the regenerated bytes equal the committed
      `default_artifact_path()` file; `.gitattributes` still pins
      `src/segqc/reference/reference_default.json text eol=lf`.

- [ ] **AC16: Intensity and geometry-only references both round-trip.**
      `from_dict(to_dict(dist))` equals `dist` for an intensity-bearing reference,
      and `write_artifact` → `load_artifact` returns an equal model; a
      geometric-only reference built under the new `"1.1"` schema
      (`with_intensity=False`) likewise writes and loads without error (backward
      tolerance).

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume`. Defaults taken to turn the one-line queue entry into a
concrete contract; several **pin an interface** a later item (064/065) must honour
— hand back if reality diverged.

- **CRITICAL COUPLING — add a *new* intensity vocabulary constant; do NOT widen
  `INGESTED_FEATURES`.** `src/segqc/reference/delta.py` derives its geometry set as
  `_GEOMETRY_FEATURES = tuple(name for name in INGESTED_FEATURES if name !=
  "spline_offset_mm")`. Appending intensity names to `INGESTED_FEATURES` would
  silently reclassify them as "geometry" in `delta.py` and couple 063 into item
  064's rule. The queue's "extend the tracked-feature vocabulary constant" is
  therefore satisfied by a **companion** constant `INGESTED_INTENSITY_FEATURES`,
  leaving `INGESTED_FEATURES` byte-identical and `delta.py` untouched.

- **Pinned intensity vocabulary (13 `intensity_`-prefixed names).**
  `intensity_mean, intensity_median, intensity_std, intensity_min, intensity_max,
  intensity_p05, intensity_p25, intensity_p50, intensity_p75, intensity_p95,
  intensity_range, intensity_iqr, intensity_entropy` — the statistical fields of
  item 059's `LabelIntensity`. The bookkeeping fields `voxel_count` and
  `n_nonfinite_excluded` are **not** tracked as reference distributions (they are
  counts, not HU statistics, and `voxel_count` duplicates geometric volume up to
  spacing). Names are prefixed `intensity_` to keep the vocabulary
  self-describing and collision-free with the geometric names. If item 064 wants a
  different subset it can filter this constant — hand back only if the *prefix
  convention* is wrong.

- **Intensity is opt-in at the ingest layer (`with_intensity=False` default),
  opt-in-by-default at the build layer (`build_reference` default `True`).** This
  preserves every existing `ingest_subject`/`ingest_cohort` caller — notably item
  044's tests, which write `_scan.nii.gz` siblings (`spine.scan_img`, a trivial
  ramp) and would otherwise start receiving intensity keys. `build_reference`
  (the artifact builder, and the `segqc build-reference` mounted-VerSe path) opts
  in so the produced reference carries intensity where scans exist.

- **Schema bump is a minor `"1.0"` → `"1.1"`.** The change is purely additive
  (more tracked features; identical nested structure), so a minor bump is the
  defensible signal. The loader's strict version-equality means the sole committed
  `"1.0"` artifact must be **regenerated** (it is, in this item) — no other
  artifact of the old version exists. Existing tests reference the version
  **symbolically** (`SCHEMA_VERSION` / `ARTIFACT_SCHEMA_VERSION` imports), so the
  bump does not break them; the only literal (`"9.9"` in test_045's rejection test)
  is unaffected. If a reviewer prefers `"2.0"`, it is a one-constant change.

- **The bundled default cohort gains painted scans via item 058's
  `paint_clean_scan`.** `build_default_cohort` currently writes seg only; to get
  intensity distributions into the committed default artifact it must also
  `paint_clean_scan(spine.seg_img, seed=0)` and `nib.save` a
  `<subject_id>_scan.nii.gz` alongside each seg. `paint_clean_scan` is
  deterministic (seed=0, int16, byte-reproducible per item 058) so the aggregated
  intensity stats — and hence `reference_default.json` — stay byte-reproducible.
  The painted scans live only in the builder's temp dir; only the JSON artifact is
  committed.

- **Grid-misalignment surfaces as `ValueError`.** Item 059's extractor raises on
  shape/affine mismatch (a caller error). Ingestion propagates it (does not
  swallow it) when `with_intensity=True` — a scan not co-registered with its seg
  is a genuine cohort error, mirroring `segqc.io.load_case`'s alignment check. The
  painted synthetic scans are always aligned; the real-VerSe path relies on the
  operator supplying co-registered scan/seg.

- **`aggregate.py` needs no change.** Confirmed against item 043's Description
  ("generic `features: Mapping[str, float]`"), its Decisions log, and the current
  `aggregate.py` (`_resolve_features` = sorted union; per-feature stats built for
  every feature key seen). With `features=None`, `build_reference` picks up the
  intensity names automatically. An AC guards that the file is unmodified.

- **Pinned upstream interfaces (hand back if reality diverged):**
  - **Item 059** — `segqc.features.intensity.compute_label_intensity(scan_img,
    seg_img, label) -> LabelIntensity` and `compute_intensity_features(scan_img,
    seg_img) -> Dict[int, LabelIntensity]`; `LabelIntensity` stat fields
    `mean, median, std, min, max, p05, p25, p50, p75, p95, range, iqr, entropy`
    are `Optional[float]` (all-`None` sentinel for empty/all-nonfinite labels);
    raises `ValueError` on grid misalignment.
  - **Item 058** — `segqc.synth.paint_clean_scan(seg_img, *, seed=0,
    model=DEFAULT_HU_MODEL) -> Nifti1Image` (deterministic, int16, grid-aligned
    with `seg_img`, byte-reproducible).
  - **Item 043/044/045** — the generic `aggregate_reference`; `FeatureRecord`
    (`features: Mapping[str, float]`); `ingest.py`'s already-threaded `scan_path`
    discovery (`DEFAULT_SCAN_SUFFIX = "_scan.nii.gz"`); `artifact.py`'s
    `build_reference` / `build_default_cohort` / `build_and_write_default` /
    `write_artifact` / `load_artifact` / `bundled_default_reference` /
    `default_artifact_path`, and the strict `schema_version` check in
    `load_artifact`.
  - **`.gitattributes`** already pins `src/segqc/reference/reference_default.json
    text eol=lf` — **no** new pin needed; the builder only regenerates the file's
    bytes.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): edit
`reference/ingest.py`, `reference/schema.py`, `reference/artifact.py`, and
regenerate `reference/reference_default.json`. **Do not** edit `reference/delta.py`,
`reference/aggregate.py`, `heuristics/reference_delta.py`, `config.py`,
`report.py`, or any `features/*` module; **do not** add a `.gitattributes` line.

1. **`reference/schema.py`:** change `SCHEMA_VERSION = "1.0"` to
   `SCHEMA_VERSION = "1.1"`. No other edit (structure is unchanged; `from_dict`
   already tolerates any version). `artifact.ARTIFACT_SCHEMA_VERSION` re-exports it
   automatically.

2. **`reference/ingest.py` — vocabulary:** add
   `INGESTED_INTENSITY_FEATURES: Tuple[str, ...]` with the 13 pinned names, and add
   it to `__all__`. Leave `INGESTED_FEATURES` untouched. Optionally add a private
   helper `_intensity_features_dict(li: "LabelIntensity") -> Dict[str, float]` that
   maps each non-`None` `LabelIntensity` stat field to its
   `intensity_<field>` key (skipping `None`, `voxel_count`, `n_nonfinite_excluded`).

3. **`reference/ingest.py` — `ingest_subject`:** add `with_intensity: bool = False`.
   When `True` **and** `scan_path` is not `None`, `nib.load(scan_path)` and call
   `compute_intensity_features(scan_img, seg_img)` (import lazily from
   `segqc.features.intensity`, mirroring the existing lazy imports) once, building
   `{label_value: LabelIntensity}`. In the per-label collection loop, after the
   geometry `features` dict is built for a recognised level, merge in
   `_intensity_features_dict(intensity_by_label[label_value])` when present. Let a
   `ValueError` from the extractor propagate (AC6). When `with_intensity=False` or
   `scan_path is None`, behave exactly as today.

4. **`reference/ingest.py` — `ingest_cohort`:** add `with_intensity: bool = False`
   and forward it to each `ingest_subject(...)` call. Sibling-scan discovery already
   exists (the `scan_path` computed per subject); no discovery change needed.

5. **`reference/artifact.py` — `build_reference`:** add `with_intensity: bool =
   True`; forward it to `ingest_cohort(..., with_intensity=with_intensity)`. No
   provenance change (intensity does not add a size proxy).

6. **`reference/artifact.py` — `build_default_cohort`:** for each recipe entry,
   after `nib.save(spine.seg_img, seg_path)`, also
   `scan_img = paint_clean_scan(spine.seg_img, seed=0)` and
   `nib.save(scan_img, dest/f"{entry['subject_id']}{DEFAULT_SCAN_SUFFIX}")`. Import
   `paint_clean_scan` lazily from `segqc.synth.intensity` (submodule import to avoid
   a circular import through `segqc.synth`). `build_and_write_default` is unchanged
   (it calls `build_reference`, now `with_intensity=True` by default), so it
   ingests the painted scans and produces an intensity-bearing artifact.

7. **Regenerate + commit the bundled artifact:** run
   `.venv/Scripts/python -m segqc.reference.artifact` to rewrite
   `src/segqc/reference/reference_default.json` (version `"1.1"`, now with per-level
   intensity distributions) and commit it with the code. Confirm
   `.gitattributes` already pins it (it does) — no edit there.

8. **Do not** modify `aggregate.py`, `delta.py`, `reference_delta.py`, the config,
   the report, or any existing test; do not add CLI knobs (item 065). Keep every
   change additive and behaviour-preserving for `with_intensity=False`.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_063_reference_intensity.py`, in
  the style of `tests/test_044_reference_ingestion.py` /
  `tests/test_045_reference_artifact.py` (import `build_clean_spine`,
  `paint_clean_scan`, `ingest_subject`/`ingest_cohort`, `aggregate_reference`,
  `build_reference`, `build_default_cohort`, `build_and_write_default`,
  `bundled_default_reference`, `load_artifact`, `compute_label_intensity`).
- **Helpers:** a `_painted_case(tmp, subject_id, levels=...)` that writes
  `<id>_seg.nii.gz` (from `build_clean_spine`) and `<id>_scan.nii.gz` (from
  `paint_clean_scan(seg_img)`); a `_geom_stats(dist)` filter selecting the
  `INGESTED_FEATURES` subset of a level's `feature_stats`.
- **Group A — vocabulary & ingestion (AC1–AC7):** constant contents + geometry
  vocabulary unchanged (AC1); default geometry-only despite a present scan (AC2);
  `with_intensity=True` intensity values match the extractor per label (AC3);
  scan-absent degrade (AC4); NaN-scan sentinel omits keys (AC5) — build a scan
  filled with NaN under the target label; misaligned scan raises `ValueError`
  (AC6) — a scan with a mismatched shape/affine; determinism + read-only (AC7).
- **Group B — aggregation & version (AC8–AC9):** aggregate painted-cohort records,
  assert intensity names in `dist.features` and hand-verifiable intensity
  `FeatureStats` (AC8), plus a guard that `aggregate.py` was not edited (assert via
  a marker such as unchanged public behaviour on a geometry-only record set);
  `SCHEMA_VERSION`/`ARTIFACT_SCHEMA_VERSION == "1.1"` and loader accept/reject
  (AC9).
- **Group C — build & bundled artifact (AC10–AC14):** `build_reference` on/off
  intensity (AC10); `build_default_cohort` writes aligned reproducible scans
  (AC11); `bundled_default_reference()` carries `"1.1"` + per-level intensity
  distributions for L1–L5 (AC12); geometric stats identical on/off intensity
  (AC13) — compare `_geom_stats` of `build_reference(..., with_intensity=True)`
  vs `False` over the default cohort; delta stays inert (AC14) — build a geometric
  `features_block` (via the Stage-2/3 pipeline on a clean seg) and assert
  `compute_reference_delta(block, bundled)` yields no `intensity_*` name anywhere.
- **Group D — reproducibility & round-trip (AC15–AC16):** double
  `build_and_write_default` byte-identity + equality with the committed file and
  the `.gitattributes` pin present (AC15); `from_dict(to_dict(dist))` and
  `write_artifact`→`load_artifact` round-trips for both an intensity-bearing and a
  geometric-only (`with_intensity=False`) reference (AC16).
- **Adversarial / edge cases:**
  - A cohort mixing a scan-bearing subject and a scan-less subject under
    `with_intensity=True` yields intensity features for the former only (no crash).
  - A subject whose scan is a NaN-filled volume under one label: that label's
    record omits intensity keys while its siblings keep them (per-label sentinel).
  - `with_intensity=True` over a scan-less cohort produces a geometric-only
    reference that still loads under `"1.1"` (backward tolerance).
  - Re-running `python -m segqc.reference.artifact` over the committed file
    reproduces identical bytes (idempotent regeneration).
  - Existing suites (`test_043`–`test_049`, `test_044`) stay green: the version
    bump is symbolic, `INGESTED_FEATURES` is unchanged, and default ingestion is
    geometry-only.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 043** — `segqc.reference.schema` / `aggregate` (`FeatureRecord`,
    generic `features: Mapping[str, float]`, `aggregate_reference`,
    `SCHEMA_VERSION`, `to_dict`/`from_dict`) — the generic core this item extends
    without editing.
  - **Item 044** — `segqc.reference.ingest` (`ingest_subject`/`ingest_cohort`,
    `INGESTED_FEATURES`, the already-threaded `scan_path` discovery) — the
    ingestion driver this item teaches to read the scan.
  - **Item 045** — `segqc.reference.artifact` (`build_reference`,
    `build_default_cohort`, `build_and_write_default`, `write_artifact`/
    `load_artifact`, `bundled_default_reference`, `ARTIFACT_SCHEMA_VERSION`, the
    committed `reference_default.json` + its `.gitattributes` pin).
  - **Item 058** — `segqc.synth.paint_clean_scan` / `DEFAULT_HU_MODEL` — the
    deterministic HU painter that gives `build_default_cohort` its scans and the
    tests their painted fixtures.
  - **Item 059** — `segqc.features.intensity.compute_label_intensity` /
    `compute_intensity_features` / `LabelIntensity` — the per-label first-order
    extractor whose outputs this item folds into records.
- **Downstream (depend on this item):**
  - **Item 064** — the level-aware delta-to-reference **intensity** rule consumes
    this item's extended reference artifact and the `INGESTED_INTENSITY_FEATURES`
    vocabulary.
  - **Item 065** — Stage-8 integration & acceptance wires the intensity path into
    `segqc run` and documents the mounted-VerSe intensity-reference rebuild.
- **Not dependencies:** items 060 (PyRadiomics), 061 (fusion), 062 (heuristic) are
  parallel Stage-8 items this one does not call into.

## Decisions & Trade-offs

To be updated during implementation.
