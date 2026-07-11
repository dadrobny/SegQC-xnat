# Item 043 — Reference-distribution schema & per-level aggregation core

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 043 *(the first item in queue-005; gates 044–049; opens Stage 6)*
> **Objectives:** G3 (distinguish failure from legitimate variation — this item
> builds the *reference-grounded* substrate the delta rules judge against) and G7
> (evaluable / regression-testable — the aggregation is pure and its serialised
> output is byte-deterministic). Realises the vision's "Reference-grounded"
> guiding principle and §5.3 "Reference feature set".

---

## Description

Establish the **statistical foundation and versioned data model** that the rest of
Stage 6 builds on. Create a new **reference module** (`src/segqc/reference/`) that
provides two things and nothing more:

1. A **versioned reference-distribution schema** — a small set of frozen
   dataclasses (plus a `SCHEMA_VERSION` constant and pure `to_dict` / `from_dict` /
   `to_json_text` serialisation helpers) describing, **per anatomical level** and
   **per optional subject-size stratum**, summary statistics (`count`, `mean`,
   `std`, a percentile set, `min`, `max`) for each heuristic-relevant feature, plus
   caller-supplied **provenance** (source, config hash, build date) and a computed
   `subject_count`.

2. A **pure aggregation function** — `aggregate_reference(records, …)` — that
   consumes a collection of per-case, per-level **feature records** and produces
   those distributions, including an optional **subject-size proxy** used to
   deterministically stratify the records into size buckets.

**This item is the gate for the whole stage:** it fixes (a) the per-case
feature-record contract (`FeatureRecord`) that item 044's VerSe ingestion driver
must emit, and (b) the versioned distribution data model that item 045's artifact
builder/loader serialises and items 046–048 consume. Getting the contract right
here is why this is the first item.

**Deliberately decoupled design.** `FeatureRecord` carries a **generic**
`features: Mapping[str, float]` (feature-name → value) rather than a fixed field
set, so the aggregation core stays independent of the exact Stage 2/3 feature
catalogue — the tracked feature list is either passed in or derived as the sorted
union of keys seen. `level_name` is an **opaque grouping key** (a string); the core
makes no anatomical judgement. This keeps the module `records in → distributions
out` with **no file I/O and no VerSe/NiBabel coupling** (NumPy is the only heavy
dependency, used solely to compute the statistics, with results stored as builtin
`float`).

### Scope boundary — what this item is **not**

- **No file I/O.** Serialisation produces a canonical **string** (`to_json_text`);
  writing the bytes to a versioned artifact on disk (with the `.gitattributes` LF
  pin) is **item 045**. `aggregate_reference` reads no wall clock — `build_date`
  and all provenance are caller-supplied precisely so the output is
  byte-reproducible.
- **No ingestion / no VerSe coupling.** Turning a directory of GT label maps into
  `FeatureRecord`s (walking NIfTI, running the feature engine, normalising labels)
  is **item 044**. This item only consumes already-built records.
- **No feature-extraction changes.** It imports **no** `segqc.features.*`,
  `segqc.io`, or `nibabel`; it does not compute geometry.
- **No delta scoring and no rules.** Robust z-score / percentile-rank /
  out-of-range scoring is **item 046**; the rule family is **item 047**; the bounds
  config switch is **item 048**. This item ships only the schema + aggregator.
- **No committed artifact.** The bundled default `.json` reference artifact is
  **item 045**.

---

## Public interface (the contract 044–048 build on)

New package `src/segqc/reference/` with, at minimum, `schema.py` (data model +
serialisation) and `aggregate.py` (the pure function), re-exported from
`src/segqc/reference/__init__.py`. Exact private layout is the builder's choice;
the **exported surface** below is the contract.

```python
SCHEMA_VERSION: str = "1.0"                     # reference-distribution schema version
DEFAULT_PERCENTILES: tuple[int, ...] = (1, 5, 25, 50, 75, 95, 99)
ALL_STRATUM: str = "all"                        # the single stratum key when unstratified

@dataclass(frozen=True)
class FeatureRecord:                            # INPUT contract (item 044 emits these)
    subject_id: str                            # distinct-subject identity (for subject_count)
    level_name: str                            # opaque grouping key (e.g. a CANONICAL_ORDER name)
    features: Mapping[str, float]              # feature_name -> value (generic; finite floats)
    size_proxy: float | None = None            # per-subject size proxy; required iff stratifying

@dataclass(frozen=True)
class Provenance:                              # caller-supplied metadata (deterministic; no wall clock)
    source: str                                # free-text cohort id, e.g. "synthetic-verse-cohort"
    config_hash: str                           # hash of the extraction config used (item 045 fills)
    build_date: str                            # ISO "YYYY-MM-DD" (caller-supplied, NOT date.today())
    size_proxy_name: str | None = None         # name of the size proxy, or None when unstratified

@dataclass(frozen=True)
class FeatureStats:                            # per (level, stratum, feature) summary
    count: int                                 # number of contributing (non-missing) values
    mean: float
    std: float                                 # sample std (ddof=1); 0.0 when count == 1
    min: float
    max: float
    percentiles: Mapping[str, float]           # {"p1":…, "p5":…, "p25":…, "p50":…, "p75":…, "p95":…, "p99":…}

@dataclass(frozen=True)
class LevelDistribution:                       # per (level, stratum)
    level_name: str
    stratum: str                               # "all" when unstratified, else a bucket label
    record_count: int                          # number of records aggregated for this (level, stratum)
    feature_stats: Mapping[str, FeatureStats]  # feature_name -> stats (features with count 0 omitted)

@dataclass(frozen=True)
class ReferenceDistribution:                   # the versioned artifact data model
    schema_version: str                        # == SCHEMA_VERSION
    provenance: Provenance
    features: tuple[str, ...]                   # tracked feature names, sorted
    percentiles: tuple[int, ...]               # percentile levels used
    subject_count: int                         # count of distinct subject_ids aggregated
    strata: tuple[str, ...]                     # ("all",) unstratified, else the bucket labels in order
    levels: Mapping[str, Mapping[str, LevelDistribution]]  # level_name -> stratum -> distribution

def aggregate_reference(
    records: Iterable[FeatureRecord],
    *,
    provenance: Provenance,
    features: Sequence[str] | None = None,      # None => sorted union of feature keys across records
    percentiles: Sequence[int] = DEFAULT_PERCENTILES,
    size_strata_edges: Sequence[float] | None = None,  # None => single "all" stratum
    stratum_labels: Sequence[str] | None = None,       # len must be len(edges)+1; default ("s0","s1",…)
) -> ReferenceDistribution:
    """Pure: group records by (level_name, size-stratum), compute per-feature stats,
    return a ReferenceDistribution. No file I/O, no wall clock, inputs never mutated."""

def to_dict(dist: ReferenceDistribution) -> dict: ...      # JSON-ready nested dict (pure)
def from_dict(data: Mapping) -> ReferenceDistribution: ... # inverse of to_dict (pure)
def to_json_text(dist: ReferenceDistribution) -> str: ...  # canonical text (see AC9); pure, no I/O
```

**Canonical JSON shape** produced by `to_dict` (what item 045 will write to disk):

```json
{
  "schema_version": "1.0",
  "provenance": {"source": "…", "config_hash": "…", "build_date": "YYYY-MM-DD", "size_proxy_name": null},
  "features": ["extent_x_mm", "physical_volume_mm3", "…"],
  "percentiles": [1, 5, 25, 50, 75, 95, 99],
  "subject_count": 12,
  "strata": ["all"],
  "levels": {
    "L1": {
      "all": {
        "level_name": "L1",
        "stratum": "all",
        "record_count": 10,
        "feature_stats": {
          "physical_volume_mm3": {
            "count": 10, "mean": 30000.0, "std": 1200.0, "min": 28000.0, "max": 32000.0,
            "percentiles": {"p1": …, "p5": …, "p25": …, "p50": …, "p75": …, "p95": …, "p99": …}
          }
        }
      }
    }
  }
}
```

## Acceptance Criteria

_One test per criterion, atomic and directly observable. "Records" are hand-built
`FeatureRecord`s with known values so every statistic is hand-checkable. A "level"
means a `level_name` grouping; a "stratum" means a size bucket. All ACs run with a
fixed caller-supplied `Provenance` so output is deterministic._

- [ ] **AC1: `mean` matches the hand-computed arithmetic mean.** For a level whose
      records carry known values for a feature, the produced
      `FeatureStats.mean` equals the arithmetic mean of those values.

- [ ] **AC2: `std` is the sample standard deviation (ddof=1), and 0.0 for a single
      value.** For a feature with ≥2 contributing values, `FeatureStats.std` equals
      the sample std (`ddof=1`); for a feature with exactly one contributing value,
      `std == 0.0` (no NaN, no warning).

- [ ] **AC3: percentiles match the linear-interpolation percentiles and `p50` is the
      median.** For the default set `(1,5,25,50,75,95,99)`,
      `FeatureStats.percentiles["pN"]` equals `numpy.percentile(values, N)` (default
      linear interpolation) for each N, and `percentiles["p50"]` equals the median.

- [ ] **AC4: `min`/`max`/`count` are correct.** `FeatureStats.min`/`max` equal the
      smallest/largest contributing values, `FeatureStats.count` equals the number
      of records that carried that feature, and the `LevelDistribution.record_count`
      equals the number of records for that level.

- [ ] **AC5: a level present in only some subjects aggregates over exactly those
      records.** Given records where level `A` appears for 3 subjects and level `B`
      for 1 subject, `levels["A"]["all"].record_count == 3` and
      `levels["B"]["all"].record_count == 1`, and `B`'s stats depend only on that
      single record (changing an `A` record does not alter `B`'s stats).

- [ ] **AC6: unstratified default puts every record under the single `"all"`
      stratum.** With `size_strata_edges=None`, `dist.strata == ("all",)` and every
      level's distributions are keyed solely by `"all"`, aggregating all of that
      level's records.

- [ ] **AC7: the subject-size proxy buckets records deterministically.** With
      `size_strata_edges` supplied, each record is assigned to the stratum determined
      by its `size_proxy` under the documented half-open rule (`bisect_right` on
      sorted edges; N edges ⇒ N+1 buckets `s0…sN`); records land in the expected
      strata, and re-running `aggregate_reference` on the same records yields the
      identical stratum assignment.

- [ ] **AC8: each stratum's stats use only that stratum's records.** With
      stratification, a feature value belonging to one stratum does not affect the
      stats of any other stratum (per-stratum stats are independent).

- [ ] **AC9: empty input yields a well-formed empty distribution.**
      `aggregate_reference([], provenance=…)` returns a `ReferenceDistribution` with
      `levels == {}`, `subject_count == 0`, `schema_version == SCHEMA_VERSION`, the
      passed `provenance`, and `to_json_text(dist)` returns valid JSON (parses
      without error).

- [ ] **AC10: serialisation is byte-deterministic.** Two independent
      `aggregate_reference` calls on the same records with the same `Provenance`
      produce **byte-identical** `to_json_text` output, and that text is
      `json.dumps(sort_keys=True, indent=2, ensure_ascii=False)` plus a single
      trailing `"\n"`.

- [ ] **AC11: the data model round-trips through `to_dict`/`from_dict`.**
      `from_dict(to_dict(dist))` equals `dist`, and
      `to_dict(from_dict(to_dict(dist))) == to_dict(dist)` (dict round-trip is a
      fixed point).

- [ ] **AC12: schema version and provenance surface in the serialised form.**
      `to_dict(dist)["schema_version"] == SCHEMA_VERSION`; the serialised
      `provenance` carries exactly the caller's `source`, `config_hash`,
      `build_date`, and `size_proxy_name`; and `dist.subject_count` equals the number
      of **distinct** `subject_id`s across the input records (a subject contributing
      several levels is counted once).

- [ ] **AC13: `build_date` is taken verbatim from the caller (no wall clock).** For
      a `Provenance` with an arbitrary fixed `build_date` (e.g. `"2000-01-01"`), the
      serialised `provenance.build_date` equals that exact string — aggregation reads
      no system clock.

- [ ] **AC14: explicit `features=` restricts the tracked feature set.** When
      `features=["physical_volume_mm3"]` is passed, `feature_stats` contains only
      `physical_volume_mm3` even if records also carry other feature keys, and a
      tracked feature absent from every record is **omitted** (no zero-count/`null`
      stats entry); `dist.features` equals the sorted tracked list.

- [ ] **AC15: inputs are never mutated.** `aggregate_reference` mutates neither the
      passed record sequence nor any `FeatureRecord.features` mapping (a
      before/after deep comparison of the inputs is unchanged).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete contract is recorded here for audit; several
**pin an interface** a later item must honour (hand back if reality diverges).

- **Generic feature mapping, not fixed fields.** `FeatureRecord.features` is a
  `Mapping[str, float]` so the aggregator is decoupled from the exact feature
  catalogue and new features need no schema change. **Pinned vocabulary for item
  044:** the canonical feature-name keys align with the existing Stage 2/3 dataclass
  field names — `physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`
  (from `segqc.features.geometry.LabelGeometry`) plus level-relative geometry such as
  `spline_offset_mm` (`segqc.features.spline_offset.VertebralSplineOffset.offset_mm`)
  and `centroid_spacing_mm` (`segqc.features.relationships` neighbour spacings). Item
  043 does **not** import these modules; it only fixes the naming convention 044 must
  emit. If 044 needs different keys, the aggregator still works (generic) — this note
  just documents the intended vocabulary.

- **`level_name` is an opaque grouping string.** Aggregation does not validate
  anatomy or ordering; it groups by exact string equality. Transitional levels
  (`T13`, `L6`) and any custom name aggregate like any other. Callers are expected to
  pass names from `segqc.labels.CANONICAL_ORDER`, but that is a convention, not an
  enforced import.

- **The size proxy is a per-record field (a duplicated subject attribute).** Item
  044 computes one size proxy per subject (e.g. total spine extent or mean vertebra
  volume) and stamps it on every record for that subject. When
  `size_strata_edges` is supplied, **every record must carry a non-`None`
  `size_proxy`**; a `None` proxy under stratification raises `ValueError` (a
  stratified build with an unmeasurable subject is a caller error). When
  unstratified, `size_proxy` is ignored.

- **Bucketing rule (deterministic).** `size_strata_edges` is sorted ascending;
  buckets are half-open `[e_{i-1}, e_i)` assigned by `bisect.bisect_right(edges, p)`,
  so N edges ⇒ N+1 buckets. Default `stratum_labels` are `("s0", "s1", …, "sN")`;
  a caller may pass their own labels (length must be `len(edges)+1`, else
  `ValueError`). A value exactly on an edge falls into the **upper** bucket
  (right-half-open lower bound). `dist.strata` lists only the labels actually
  present, in bucket order.

- **`std` = sample standard deviation (`ddof=1`), 0.0 for a single value.** Chosen
  over population std because downstream standard z-scores (item 046) assume a sample
  estimate; the `count == 1` case is defined as `0.0` (rather than NaN) so the
  serialised artifact is always finite and JSON-valid. Robust statistics (median,
  IQR) needed by 046 are derivable from `p50` and `p75 − p25`, which the schema
  already carries.

- **Percentiles use NumPy's default (linear) interpolation.** `DEFAULT_PERCENTILES`
  is `(1, 5, 25, 50, 75, 95, 99)`, serialised as keys `p1…p99`. Tests hand-verify
  against `numpy.percentile(values, N)` (no `method=`/`interpolation=` kwarg, so the
  default holds across the pinned NumPy on Python 3.9+).

- **Features with zero contributing values in a (level, stratum) are omitted** from
  that level's `feature_stats` (no `null`/zero-count entries), keeping every emitted
  `FeatureStats` fully defined. `dist.features` still lists the whole tracked set.

- **Provenance and `build_date` are caller-supplied; aggregation reads no clock.**
  This is what makes the output **byte-reproducible** (the Stage-6 milestone and the
  CLAUDE.md determinism precedent). `aggregate_reference` computes `subject_count`
  from the records but takes `source`/`config_hash`/`build_date`/`size_proxy_name`
  verbatim from the passed `Provenance`. Item 045 supplies real provenance and writes
  the bytes to disk with the `.gitattributes` LF pin.

- **Canonical serialisation is a pure string.** `to_json_text` returns
  `json.dumps(to_dict(dist), sort_keys=True, indent=2, ensure_ascii=False) + "\n"`
  and performs **no file I/O**. Item 045 encodes it UTF-8 and writes via
  `Path.write_bytes` (the 3.9-safe `\n` pattern from items 040/042). Storing NumPy
  results as builtin `float` (via `float(...)`) before serialisation guarantees clean
  JSON and stable `repr`.

- **`SCHEMA_VERSION = "1.0"`.** The reference-distribution schema is versioned
  independently of the report schema (`"0.1"`) and the config schema (`"0.1"`).
  `from_dict` reads whatever `schema_version` the dict carries; the **strict**
  version-mismatch rejection lives in item 045's artifact loader, not here (this item
  only defines the model and round-trip).

- **Dependencies are code-free.** Every Stage 0–5 item is merged (✅), but item 043
  imports none of them at module level beyond NumPy. It is the first Stage-6 item and
  has no `🚧`/`✅` item it must call into.

## Implementation Steps

Intended code path (all new, under `source_dir = src/segqc`): a new
`src/segqc/reference/` package. No edits to any existing module.

1. **Create `src/segqc/reference/__init__.py`** re-exporting the public surface
   (the names in the interface block), following the existing `features` /
   `heuristics` / `synth` `__all__` re-export style. Import concrete names from the
   submodules to avoid a circular import through `__init__`.

2. **Create `src/segqc/reference/schema.py`:**
   - Define `SCHEMA_VERSION = "1.0"`, `DEFAULT_PERCENTILES = (1, 5, 25, 50, 75, 95,
     99)`, `ALL_STRATUM = "all"`.
   - Define the frozen dataclasses `FeatureRecord`, `Provenance`, `FeatureStats`,
     `LevelDistribution`, `ReferenceDistribution` exactly per the interface block.
   - Implement `to_dict(dist)` producing the nested JSON shape (percentile dict keys
     `p{N}`; features/levels/strata emitted in sorted/bucket order; all values plain
     `float`/`int`/`str`), `from_dict(data)` as its inverse (rebuilding the
     dataclasses, tolerating any `schema_version` value), and `to_json_text(dist)` =
     `json.dumps(to_dict(dist), sort_keys=True, indent=2, ensure_ascii=False) + "\n"`.
     No NumPy import here — `schema.py` handles only builtin types.

3. **Create `src/segqc/reference/aggregate.py`:**
   - `import bisect`, `import numpy as np`; import the dataclasses/constants from
     `.schema`.
   - `aggregate_reference(records, *, provenance, features=None, percentiles=DEFAULT_PERCENTILES,
     size_strata_edges=None, stratum_labels=None)`:
     1. Materialise `records` once into a list (never mutate the caller's sequence).
     2. Resolve the tracked `features`: if `None`, the sorted union of all
        `record.features` keys; else the given sequence (kept as `dist.features`
        sorted).
     3. Resolve strata: if `size_strata_edges is None`, single stratum `ALL_STRATUM`;
        else validate ascending edges, derive `stratum_labels` (default `s0…sN`,
        validate length), and for each record compute its stratum via
        `bisect.bisect_right(sorted_edges, record.size_proxy)` — raising `ValueError`
        if `size_proxy is None`.
     4. Group values by `(level_name, stratum, feature_name)`; collect the contributing
        float values.
     5. For each `(level, stratum)` with ≥1 record, build a `LevelDistribution` whose
        `feature_stats` has, for each feature with ≥1 value, a `FeatureStats` with
        `count`, `mean = float(np.mean(v))`, `std = float(np.std(v, ddof=1))` (or
        `0.0` when `len(v) == 1`), `min`/`max = float(np.min/np.max(v))`, and
        `percentiles = {f"p{n}": float(np.percentile(v, n)) for n in percentiles}`.
        Omit features with no values.
     6. Compute `subject_count = len({r.subject_id for r in records})`.
     7. Return `ReferenceDistribution(SCHEMA_VERSION, provenance, tuple(sorted(features)),
        tuple(percentiles), subject_count, tuple(present strata in order), levels)`.

4. **Determinism hygiene:** convert every NumPy scalar to builtin `float` before it
   enters a dataclass; sort feature/level keys in `to_dict`; rely on
   `json.dumps(sort_keys=True)` for final key order. Do not read `datetime`/clock
   anywhere in `aggregate.py` or `schema.py`.

5. **Do not** create the on-disk artifact, a loader with version enforcement, any
   CLI wiring, or any test fixtures under `tests/` — those are items 044/045 and the
   test-writer's remit. Add no `.gitattributes` entry (no file is written here).

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_043_reference_aggregation.py`
  (naming matches `test_04x_*` siblings). No NIfTI fixtures, no I/O — every input is
  a hand-built `FeatureRecord` list with known values, and a fixed `Provenance`
  (e.g. `Provenance("test-cohort", "cfg-hash", "2000-01-01", None)`).
- **One focused test per AC** (AC1–AC15 above), each asserting a single observable
  fact against hand-computed expectations. Where percentiles are asserted (AC3),
  also cross-check against `numpy.percentile` on the same values so the expectation
  is not itself hand-mis-computed.
- **Adversarial / edge cases (beyond the ACs):**
  - **Boundary value on a stratum edge** — a record whose `size_proxy` exactly equals
    an edge lands in the upper (right) bucket, per the documented `bisect_right` rule.
  - **Single-subject, single-record level** — `record_count == 1`, `std == 0.0`,
    every percentile equals the lone value, `min == max == mean`.
  - **Missing feature in some records** — a feature present in 2 of 3 records for a
    level has `count == 2` while the level's `record_count == 3`.
  - **Stratification with a `None` size_proxy** raises `ValueError`.
  - **Wrong-length `stratum_labels`** raises `ValueError`.
  - **Duplicate `subject_id` across levels** counts once in `subject_count`.
  - **Determinism** — `to_json_text` from two separate aggregations is byte-equal,
    and the text ends in exactly one `"\n"` with sorted keys (a hand-permuted input
    record order yields identical serialised bytes).
  - **Empty tracked feature / empty records** — `aggregate_reference([], …)` and a
    non-empty records list with `features=[]` both serialise to valid JSON with
    `levels`/empty `feature_stats` respectively.
  - **Non-mutation** — deep-copy the inputs before the call and assert equality
    afterward (AC15).
  - **Round-trip stability** — `from_dict(to_dict(dist))` for both a stratified and
    an unstratified distribution equals the original (AC11).

## Dependencies

- **None (code-level).** Item 043 is the first Stage-6 item and imports no prior
  work-item module (only NumPy from the venv). Every Stage 0–5 item is merged (✅ in
  `progress.md`); this item does not call into any of them.
- **Conceptual alignment (not an import):** the feature-name vocabulary it aggregates
  matches the Stage 2/3 feature dataclass field names (see Assumptions), so item 044
  can populate matching keys.
- **Downstream (this item gates them):** **044** (emits `FeatureRecord`s for this
  aggregator), **045** (serialises a `ReferenceDistribution` to a versioned artifact +
  loader with strict `schema_version` validation), **046** (computes delta-to-reference
  metrics from a loaded `ReferenceDistribution`), **047** (delta rule family), **048**
  (bounds config switch reads reference percentiles), **049** (integration + acceptance).

## Decisions & Trade-offs

- **Package layout matches the Implementation Steps exactly:** `src/segqc/reference/{__init__.py,schema.py,aggregate.py}`.
  `schema.py` imports only `json`/`dataclasses`/`typing` (no NumPy); `aggregate.py` imports `bisect`, `numpy as np`, and
  the dataclasses/constants from `.schema`. `__init__.py` re-exports the full public surface with an explicit `__all__`.
- **`FeatureRecord.size_proxy` and `Provenance.size_proxy_name` are typed `Optional[...] = None`** (the interface block's
  `float | None` / `str | None` syntax is Python 3.10+; this project targets 3.9+, so `typing.Optional` is used instead —
  behaviourally identical).
- **`present strata order`** in `ReferenceDistribution.strata` is derived by filtering the caller's/default `stratum_labels`
  bucket order down to labels that have at least one `(level, stratum)` group actually present in the aggregated records —
  satisfies "`dist.strata` lists only the labels actually present, in bucket order" (empty input therefore yields
  `strata == ()`, which is consistent with "well-formed empty distribution" though AC9 does not assert on `strata`
  directly).
- **Per-record grouping key is `(level_name, stratum)`** with a `record_count` incremented unconditionally per record
  (independent of which of that record's feature keys are in the tracked set), so `features=[]` still yields a
  `LevelDistribution` with the correct `record_count` and an empty `feature_stats` dict, matching AC14's "omitted, not
  null" requirement and the adversarial empty-tracked-features case.
- **Stratum-label length validation runs before per-record `None`-proxy validation** inside `_resolve_strata`, so a
  wrong-length `stratum_labels` raises `ValueError` immediately regardless of whether any record's `size_proxy` is `None`
  — both are documented failure modes and the tests only assert `pytest.raises(ValueError)` without requiring a
  particular precedence when both conditions could apply simultaneously.
- No deviations from the spec's pinned interface, JSON shape, or Assumptions were needed; the committed tests
  (`tests/test_043_reference_aggregation.py`) exercise exactly the public surface described above with no conflicts
  found.
