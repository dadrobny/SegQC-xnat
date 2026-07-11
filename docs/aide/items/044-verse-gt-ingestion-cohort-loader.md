# Item 044 — VerSe GT ingestion — cohort loader & feature-extraction driver

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 044 *(the second item in queue-005; consumes 043's `FeatureRecord` contract; feeds 045's artifact builder)*
> **Objectives:** G3 (distinguish failure from legitimate variation — this item
> supplies the *ground-truth-derived* records the reference distributions are built
> from) and G7 (evaluable / regression-testable — ingestion is deterministic over a
> fixed cohort and runs entirely under `pytest`). Realises the vision's
> "Reference-grounded" principle and §5.3 "Reference feature set" ingestion path.

---

## Description

Add the **ingestion path** that turns a directory of ground-truth (GT) label maps
into the per-case, per-level `FeatureRecord`s that the item-043 aggregation core
(`segqc.reference.aggregate_reference`) consumes. Provide a **cohort driver**
(`src/segqc/reference/ingest.py`) that:

1. **Walks a VerSe-style dataset directory** of NIfTI instance label maps (with a
   matching scan where the feature engine needs one), discovering one **subject**
   per label-map file under a documented, deterministic naming convention.
2. **Normalises integer labels to canonical level names** via the Stage 0
   convention (`segqc.labels.LabelConvention` / `CANONICAL_ORDER`).
3. **Runs the existing Stage 2–3 feature engine per subject** via
   `segqc.pipeline.extract_feature_record(seg_img, config)` — the exact same
   per-case features block the Stage 4 rules already consume — and reads the
   per-label geometry / spline-offset / centroid-spacing values out of it.
4. **Emits one 043-schema `FeatureRecord` per (subject, level)** carrying a
   generic `features: Mapping[str, float]` keyed by the 043-pinned vocabulary,
   plus a per-subject **size proxy** stamped on every record, and **provenance**
   (which subject and which level each record came from — `subject_id` +
   `level_name` on the record itself).
5. **Tolerates real VerSe quirks** — transitional anatomy (`T13` / `L6`), partial
   field-of-view (FOV), and subjects missing interior levels — **without
   crashing**: an unmapped/unknown integer label is skipped (never fabricated into
   a level), a missing level simply contributes no record, and a subject that fails
   to load or has too few labels for a given feature is handled gracefully.

Because full VerSe is a large external dataset **not committed** to this repo,
ingestion is written to operate on **any conforming directory** of GT label maps
and is tested locally against a **small synthetic VerSe-format cohort** built with
the Stage 5 clean-GT builder (`segqc.synth.clean_gt.build_clean_spine`) with
per-subject variation, written to a temp directory as NIfTI files.

### Scope boundary — what this item is **not**

- **Not the aggregation core.** It does not compute means / percentiles /
  distributions; it produces the *records* that `aggregate_reference` (043)
  consumes. It imports the 043 schema (`FeatureRecord`) but not the aggregator's
  statistics.
- **Not the artifact / builder / loader.** Writing a versioned reference `.json`
  to disk, its `.gitattributes` LF pin, the `segqc build-reference` CLI, the
  committed default artifact, and schema-version validation are **item 045**. This
  item does no reference-artifact file I/O; it returns Python objects
  (`FeatureRecord`s and a small cohort-ingest result).
- **Not a change to the feature engine.** It *calls* `extract_feature_record`
  unchanged; it adds no geometry and does not modify `segqc.features.*`,
  `segqc.pipeline`, or `segqc.feature_report`.
- **Not delta scoring, rules, or config switches.** Those are items 046 / 047 /
  048.
- **Not a change to `segqc.synth.clean_gt`.** It *consumes* `build_clean_spine`
  output as fixtures; per-subject variation is achieved via that builder's existing
  parameters (`spacing`, `levels`, `curve_amplitude_mm`), not by editing it.

---

## Public interface (the contract 045 builds on)

New module `src/segqc/reference/ingest.py`, re-exported from
`src/segqc/reference/__init__.py`. Exact private helpers are the builder's choice;
the **exported surface** below is the contract.

```python
DEFAULT_SEG_SUFFIX: str = "_seg.nii.gz"     # label-map filename suffix used to discover subjects
DEFAULT_SCAN_SUFFIX: str = "_scan.nii.gz"   # optional matching scan suffix (same subject stem)
SIZE_PROXY_NAME: str = "mean_vertebra_volume_mm3"  # documented per-subject size-proxy identity

# The feature-name vocabulary emitted per (subject, level) record — aligned with the
# 043 Assumptions "pinned vocabulary" and the Stage 2/3 dataclass field names.
INGESTED_FEATURES: tuple[str, ...] = (
    "physical_volume_mm3",   # LabelGeometry.physical_volume_mm3
    "extent_x_mm",           # LabelGeometry.extent_x_mm
    "extent_y_mm",           # LabelGeometry.extent_y_mm
    "extent_z_mm",           # LabelGeometry.extent_z_mm
    "spline_offset_mm",      # stage3.per_label_offsets[*].offset_mm  (absent for <2-label subjects)
)

@dataclass(frozen=True)
class SubjectIngest:
    """One discovered subject and the records extracted from it."""
    subject_id: str                       # deterministic id derived from the seg filename stem
    seg_path: str                         # the label-map path ingested
    records: tuple[FeatureRecord, ...]    # one FeatureRecord per recognised, present level
    skipped_labels: tuple[int, ...]       # unknown/unmapped integer labels present but not ingested

@dataclass(frozen=True)
class CohortIngest:
    """The whole-cohort ingestion result."""
    subjects: tuple[SubjectIngest, ...]   # in ascending subject_id order
    records: tuple[FeatureRecord, ...]    # flattened, deterministic order (subject_id, then CANONICAL_ORDER rank)
    size_proxy_name: str                  # SIZE_PROXY_NAME (or None if size proxy disabled)

def ingest_subject(
    seg_path: str | os.PathLike,
    *,
    config: "HeuristicConfig",
    convention: "LabelConvention | None" = None,
    scan_path: str | os.PathLike | None = None,
    subject_id: str | None = None,
    with_size_proxy: bool = True,
) -> SubjectIngest:
    """Load one GT label map, run the feature engine, and emit one FeatureRecord
    per recognised present level. Never mutates inputs; deterministic."""

def ingest_cohort(
    cohort_dir: str | os.PathLike,
    *,
    config: "HeuristicConfig | None" = None,
    convention: "LabelConvention | None" = None,
    seg_suffix: str = DEFAULT_SEG_SUFFIX,
    with_size_proxy: bool = True,
) -> CohortIngest:
    """Walk cohort_dir for label maps matching seg_suffix, ingest each subject in
    ascending subject-id order, and return the flattened, deterministic record set.
    Tolerates missing levels / partial FOV / transitional labels without raising."""
```

The flattened `CohortIngest.records` is exactly what a caller feeds to
`aggregate_reference(records, provenance=…, size_strata_edges=…)` — item 045 does
that wiring.

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. The synthetic cohort is
built by writing `build_clean_spine(...)` output for several subjects (with
per-subject parameter variation) to a temp directory as `<subject>_seg.nii.gz`
(+ `<subject>_scan.nii.gz`) files, then running the driver over that directory._

- [ ] **AC1: one record per (subject, present-level) over a cohort.** Running
      `ingest_cohort` over a synthetic cohort of `N` subjects each with the same
      `L` present lumbar levels produces exactly `N × L` `FeatureRecord`s, and for
      each subject there is exactly one record per present level name.

- [ ] **AC2: emitted features match the extracted geometry.** For a chosen
      (subject, level), the record's `features["physical_volume_mm3"]` /
      `extent_x_mm` / `extent_y_mm` / `extent_z_mm` equal the corresponding
      `geometry` values that `extract_feature_record(seg_img, config)` produces for
      that level's label (byte/`float`-equal), confirming the driver reads the real
      feature engine, not a re-implementation.

- [ ] **AC3: `spline_offset_mm` is populated for a ≥2-level subject.** For a
      subject with ≥2 present levels, each record carries a finite
      `features["spline_offset_mm"]` equal to that label's
      `stage3.per_label_offsets[*].offset_mm` from the extracted block.

- [ ] **AC4: labels are normalised to canonical level names.** Every emitted
      record's `level_name` is a member of `segqc.labels.CANONICAL_ORDER`
      (e.g. `"L1"`, not the integer `20`), resolved through the supplied
      `LabelConvention`.

- [ ] **AC5: a subject with a deliberately missing interior level ingests without
      error and contributes no record for that level.** Given a cohort where one
      subject omits an interior level present in the others, `ingest_cohort` does
      **not** raise, that subject yields records only for the levels actually
      present in its label map, and no record for the omitted level carries that
      subject's `subject_id`.

- [ ] **AC6: unknown / unmapped integer labels are skipped, not turned into
      levels.** A subject label map containing an integer with no mapping in the
      convention (e.g. a value outside `DEFAULT_LABEL_MAP`) ingests without raising,
      emits no record for that label, and records the value in
      `SubjectIngest.skipped_labels`.

- [ ] **AC7: transitional anatomy (T13 / L6) is ingested as its canonical name.**
      A subject whose label map includes a transitional vertebra label (value `28`
      → `"T13"` or `29` → `"L6"`) yields a record whose `level_name` is exactly
      `"T13"` / `"L6"` and does **not** crash on the non-contiguous canonical
      ordering.

- [ ] **AC8: a per-subject size proxy is stamped on every record for that
      subject.** With `with_size_proxy=True`, every record from a given subject
      carries the **same** non-`None` `size_proxy` value (the subject's
      `mean_vertebra_volume_mm3` = mean of its present levels' physical volumes),
      and `CohortIngest.size_proxy_name == SIZE_PROXY_NAME`.

- [ ] **AC9: the flattened records feed the 043 aggregator unchanged.** Passing
      `ingest_cohort(...).records` to
      `aggregate_reference(records, provenance=…)` returns a
      `ReferenceDistribution` whose `subject_count` equals the number of subjects in
      the cohort and whose `levels` cover exactly the union of present level names —
      i.e. the two items compose without adaptation.

- [ ] **AC10: subject-level stratification round-trips through the proxy.** Passing
      the flattened records plus `size_strata_edges` (chosen to split the cohort's
      size proxies into ≥2 buckets) to `aggregate_reference` produces a distribution
      with >1 stratum present, confirming the ingested `size_proxy` drives 043's
      bucketing.

- [ ] **AC11: discovery is deterministic and complete.** `ingest_cohort` discovers
      **every** `*<seg_suffix>` file under the cohort directory (and only those),
      and `CohortIngest.subjects` is ordered by ascending `subject_id`; a file not
      matching the suffix (e.g. a stray `README.txt` or a `*_scan.nii.gz`) is not
      treated as a subject.

- [ ] **AC12: ingestion is deterministic over a fixed cohort.** Two independent
      `ingest_cohort` calls over the same directory produce **equal**
      `CohortIngest` results — identical subject order, identical record order, and
      identical feature values (a field-by-field comparison is unchanged).

- [ ] **AC13: an empty or record-less cohort yields a well-formed empty result.**
      `ingest_cohort` over a directory with no matching label maps returns a
      `CohortIngest` with `subjects == ()` and `records == ()` (no raise), and
      feeding those empty records to `aggregate_reference` yields the 043
      empty-but-well-formed distribution (`subject_count == 0`, `levels == {}`).

- [ ] **AC14: inputs are not mutated and no wall clock is read.** `ingest_subject`
      / `ingest_cohort` do not mutate the passed `config` or `convention`, read no
      `datetime`/clock, and write nothing to the cohort directory (a before/after
      comparison of the directory contents and the config object is unchanged) —
      so provenance/build-date stays item 045's caller-supplied concern.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete contract is recorded here for audit; several
**pin an interface** item 045 must honour (hand back if reality diverges).

- **Subject discovery is by label-map filename suffix.** A VerSe-style directory
  is not pinned to the BIDS `sub-XXX/` folder layout here; instead any file whose
  name ends with `seg_suffix` (default `"_seg.nii.gz"`) is one subject, and its
  `subject_id` is the filename stem with the suffix stripped. This mirrors the
  Stage 5 corpus convention (`<case_id>_seg.nii.gz` in
  `segqc.synth.corpus.write_corpus`) so the synthetic cohort the tests write is a
  conforming directory out of the box. **Pinned for 045:** the builder walks the
  same suffix convention (overridable via `seg_suffix`). A different real-VerSe
  layout is accommodated by pointing the driver at a directory whose files carry
  that suffix, or by a thin future adapter — not by changing this contract.

- **The feature engine is called via `segqc.pipeline.extract_feature_record`.**
  Rather than re-implementing geometry, the driver loads the seg image
  (`segqc.io.load_volume(path, integer_labels=True)` → the `Nifti1Image`, or
  `nibabel.load`) and calls `extract_feature_record(seg_img, config)`, then reads
  the per-label `geometry` block and (when present) the `stage3.per_label_offsets`
  entries out of the returned dict. This guarantees the records are byte-consistent
  with what the Stage 4 rules see (AC2/AC3). A scan is **not required** for the
  Stage 2/3 geometry features the reference set tracks; `scan_path` is optional and
  currently unused by `extract_feature_record` (which takes only the seg image), so
  the driver works on a seg-only directory. If a later feature needs the scan, the
  `scan_path` parameter is already threaded for it.

- **The config defaults to the bundled default config.** `ingest_cohort(config=None)`
  uses `segqc.config.bundled_default_config()` so ingestion runs with no caller
  setup, matching how the pipeline is driven elsewhere. A caller may pass an
  explicit `HeuristicConfig` (item 045 will, to stamp its `config_hash` provenance).
  `config` is threaded into `extract_feature_record` only for
  `min_fragment_voxels` in component computation; it does not affect the geometry
  values the records carry.

- **The pinned feature vocabulary is `INGESTED_FEATURES`** — the four
  `LabelGeometry` scalars plus `spline_offset_mm` — chosen to match the item-043
  Assumptions "pinned vocabulary" and the Stage 2/3 dataclass field names exactly,
  so `aggregate_reference` groups them with no renaming (AC9). `spline_offset_mm`
  is present only for subjects with ≥2 present levels (the pipeline computes Stage 3
  only then); for a 0/1-level subject that feature key is simply **absent** from the
  record's `features` mapping, and 043's aggregator (which unions keys and counts
  per-feature contributions) handles the gap without a null entry. `centroid_spacing_mm`
  (a neighbour-spacing feature mentioned in 043's vocabulary) is **out of scope for
  this item** — it is a between-level relationship, not a per-level scalar, and
  mapping it onto a single `level_name` record is deferred; the driver emits only
  the five per-level scalars above. Adding it later needs no schema change (generic
  `features` map).

- **The size proxy is `mean_vertebra_volume_mm3` per subject.** The 043 contract
  wants "one size proxy per subject stamped on every record"; this item computes it
  as the mean of the subject's present levels' `physical_volume_mm3`. It is a
  per-subject scalar (identical on all that subject's records), enabling 043's
  size-stratified aggregation (AC8/AC10). "Total spine extent" was the other
  candidate from the queue text; mean vertebra volume is chosen because it is
  well-defined even under partial FOV (it does not depend on the full spine being
  present) and is directly derivable from the already-extracted geometry. Disabled
  via `with_size_proxy=False` (records then carry `size_proxy=None`), for callers
  who aggregate unstratified.

- **Unknown/unmapped labels are skipped, background is ignored.** Background
  (value `0`) is never a subject level; any present integer with no name in the
  convention (`LabelConvention.is_known(value)` is `False`) is skipped and recorded
  in `SubjectIngest.skipped_labels` (AC6) rather than raising or fabricating a
  level. This is what makes partial FOV / unexpected labels tolerable (AC5/AC6).

- **Missing / partial levels are represented by absence, never by a placeholder
  record.** A subject that lacks an interior level simply produces no record for it
  (AC5); the reference distribution for that level is then aggregated over exactly
  the subjects that *have* it — consistent with 043's AC5 ("a level present in only
  some subjects aggregates over exactly those records"). No imputation, no NaN.

- **Per-subject variation in the synthetic cohort comes from `build_clean_spine`
  parameters, not RNG.** The test cohort varies subjects deterministically via the
  builder's existing knobs — different `spacing`, `levels` spans, and
  `curve_amplitude_mm` — so the cohort is fixed and reproducible (AC12) with no seed
  management, and `clean_gt.py` is not modified. A "missing interior level" subject
  is produced by building a shorter/gapped span or by removing one label's voxels
  from a built map before writing (the test-writer's choice); the driver's tolerance
  (AC5) is what is under test, not the fixture mechanism.

- **Discovery order is by `subject_id` ascending; record order is
  `(subject_id, CANONICAL_ORDER-rank)`.** Both are total, deterministic orders with
  no reliance on filesystem enumeration order (which is not stable across
  platforms), satisfying the determinism ACs (AC11/AC12). The driver sorts
  explicitly rather than trusting `os.listdir` / `Path.glob` order.

- **Ingestion reads no wall clock and writes nothing.** Provenance (`source`,
  `config_hash`, `build_date`) is **not** this item's concern — it is stamped by
  item 045 when it aggregates and serialises. The driver's "provenance" is only the
  `subject_id` + `level_name` carried on each `FeatureRecord` (which subject/level a
  value came from), per the queue text. This keeps the whole reference build
  byte-reproducible (the Stage-6 milestone and the CLAUDE.md determinism precedent).

- **Dependency 043 is `✅` (merged).** Its exported `FeatureRecord` (frozen
  dataclass: `subject_id`, `level_name`, `features: Mapping[str, float]`,
  `size_proxy: Optional[float]`) and `aggregate_reference` are imported from
  `segqc.reference`; verified against the merged `src/segqc/reference/schema.py`.
  If that surface changed, hand back.

## Implementation Steps

Intended code path (all new, under `source_dir = src/segqc`): a new
`src/segqc/reference/ingest.py`, plus a one-line re-export addition to the existing
`src/segqc/reference/__init__.py`. No edits to any other existing module.

1. **Create `src/segqc/reference/ingest.py`:**
   - Module docstring stating scope (ingestion → 043 records; no artifact I/O, no
     stats, no feature-engine changes) and the discovery/vocabulary/size-proxy
     conventions above.
   - Define the constants `DEFAULT_SEG_SUFFIX = "_seg.nii.gz"`,
     `DEFAULT_SCAN_SUFFIX = "_scan.nii.gz"`, `SIZE_PROXY_NAME =
     "mean_vertebra_volume_mm3"`, and `INGESTED_FEATURES` (the 5-tuple above).
   - Define the frozen dataclasses `SubjectIngest` and `CohortIngest` per the
     interface block.
   - Defer heavy imports (`nibabel`/`numpy`, `segqc.pipeline`,
     `segqc.feature_report`) inside the functions, matching the pipeline/CLI
     deferred-import style, so `import segqc.reference.ingest` stays cheap. Import
     `FeatureRecord` from `segqc.reference.schema` (or `segqc.reference`) at module
     level (it is light).

2. **Implement `ingest_subject(seg_path, *, config, convention=None, scan_path=None,
   subject_id=None, with_size_proxy=True)`:**
   1. Resolve `convention = convention or LabelConvention.default()` and
      `subject_id = subject_id or <stem of seg_path with seg_suffix stripped>`.
   2. Load the label map: `seg_img = nibabel.load(str(seg_path))` (or
      `segqc.io.load_volume(seg_path, integer_labels=True)` then its image) — read
      only.
   3. `block = extract_feature_record(seg_img, config)` — the Stage 2/3 features
      dict.
   4. For each `per_label` entry (keyed by str label), read the integer `label` and
      its `level_name` from the block. **Re-normalise** the level name through the
      supplied `convention` (`convention.name_of(int(label))`); if it is `UNKNOWN`
      (or `convention.is_known(label)` is `False`), append the integer to
      `skipped_labels` and continue — no record.
   5. Build the record's `features` dict from the entry's `geometry` block
      (`physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`) as plain
      `float`s. If the block carries `stage3.per_label_offsets`, look up this
      label's `offset_mm` and add `features["spline_offset_mm"]`; otherwise omit it.
   6. Compute the per-subject size proxy (mean of the collected
      `physical_volume_mm3` across recognised levels) once all levels are gathered,
      when `with_size_proxy`; else `None`. Stamp the same value on every record.
   7. Return `SubjectIngest(subject_id, str(seg_path), tuple(records sorted by
      CANONICAL_ORDER rank of level_name), tuple(sorted skipped_labels))`.
   8. Never mutate `config`/`convention`; read no clock; write nothing.

3. **Implement `ingest_cohort(cohort_dir, *, config=None, convention=None,
   seg_suffix=DEFAULT_SEG_SUFFIX, with_size_proxy=True)`:**
   1. `config = config or bundled_default_config()`;
      `convention = convention or LabelConvention.default()`.
   2. Discover subjects: list files in `cohort_dir` whose name ends with
      `seg_suffix` (deterministic — sort the matched paths), derive each
      `subject_id`, and locate an optional sibling scan
      (`<subject_id><DEFAULT_SCAN_SUFFIX>`) if present.
   3. Call `ingest_subject` for each in ascending `subject_id` order, collecting
      `SubjectIngest`s.
   4. Flatten all `records` in `(subject_id, CANONICAL_ORDER-rank)` order.
   5. Return `CohortIngest(tuple(subjects), tuple(flattened records),
      SIZE_PROXY_NAME if with_size_proxy else None)`.
   6. Empty directory / no matches ⇒ `subjects == ()`, `records == ()` (no raise).

4. **Re-export from `src/segqc/reference/__init__.py`:** add
   `ingest_subject`, `ingest_cohort`, `SubjectIngest`, `CohortIngest`,
   `INGESTED_FEATURES`, `SIZE_PROXY_NAME`, `DEFAULT_SEG_SUFFIX` to the package's
   `__all__` and imports, following the existing 043 re-export style (import from
   the submodule to avoid a circular import).

5. **Do not** write any reference artifact, `.gitattributes` entry, CLI subcommand,
   loader, provenance stamping, or `tests/` fixtures — those are item 045 and the
   test-writer's remit. Add no dependency on `segqc.synth` in production code (the
   synthetic cohort is a *test* fixture; `ingest.py` operates on any directory).

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_044_reference_ingestion.py`
  (naming matches the `test_04x_*` siblings). Cohorts are written to `tmp_path` by
  saving `build_clean_spine(...)` output as `<subject>_seg.nii.gz` (+ optional
  `_scan.nii.gz`) via `nibabel.save`, exactly the Stage 5 corpus fixture idiom.
- **A small reusable cohort fixture:** a helper that writes `N` subjects with
  deterministic per-subject variation (different `spacing`, `levels` span, and
  `curve_amplitude_mm`) to a temp dir and returns the dir — reused across ACs.
- **One focused test per AC** (AC1–AC14 above), each asserting a single observable
  fact against values re-derived from `extract_feature_record` on the same image
  (so AC2/AC3 cross-check the driver against the real engine rather than a
  hand-copied constant).
- **Adversarial / edge cases (beyond the ACs):**
  - **Single-level subject** — no `stage3`; records carry the four geometry
    features but **no** `spline_offset_mm`, and ingest does not raise.
  - **Missing interior level** — a subject built with a gapped/short span (or a
    label's voxels zeroed before writing) yields records only for present levels;
    the omitted level appears for other subjects but never for this one (AC5).
  - **Unknown label** — a map with an out-of-convention integer (e.g. `99`)
    surfaces it in `skipped_labels` and emits no record for it (AC6).
  - **Transitional label** — a map including value `28`/`29` yields a `"T13"`/`"L6"`
    record (AC7), verifying the non-contiguous canonical ordering does not break the
    sort key.
  - **Empty directory** and **directory with only non-matching files**
    (`README.txt`, a stray `_scan.nii.gz`) — `subjects == () / records == ()` and no
    raise (AC11/AC13).
  - **Determinism** — two `ingest_cohort` calls over the same dir produce equal
    results field-by-field, including record order under a deliberately
    non-alphabetical filesystem write order (AC12).
  - **Non-mutation / no writes** — snapshot the directory listing + a deep copy of
    the config before the call and assert both unchanged afterward (AC14).
  - **Composition with 043** — feed `records` straight into `aggregate_reference`
    and assert `subject_count` / `levels` (AC9) and, with `size_strata_edges`, >1
    stratum present (AC10).

## Dependencies

- **Item 043 (✅ merged) — REQUIRED.** Provides the `FeatureRecord` schema this
  item emits and the `aggregate_reference` function the AC9/AC10 composition tests
  feed. Imported from `segqc.reference`.
- **Stage 0 labels (item 004, ✅) — used, not re-implemented.**
  `segqc.labels.LabelConvention` / `CANONICAL_ORDER` / `UNKNOWN` normalise integer
  labels to canonical level names (AC4/AC7) and identify skips (AC6).
- **Stage 2/3 feature engine + pipeline (items 011–022, 035, ✅) — used, not
  modified.** `segqc.pipeline.extract_feature_record` computes the per-case features
  block the records are read from (AC2/AC3); `segqc.io` / `nibabel` load the label
  maps; `segqc.config.bundled_default_config` supplies the default config.
- **Stage 5 clean-GT builder (item 036, ✅) — a TEST fixture only.**
  `segqc.synth.clean_gt.build_clean_spine` produces the synthetic VerSe-format
  cohort the tests write; production `ingest.py` does not import `segqc.synth`.
- **Downstream (this item feeds them):** **045** (chains `ingest_cohort` →
  `aggregate_reference` into a versioned, byte-reproducible artifact + builder +
  loader), then **046–049** consume that artifact.

## Decisions & Trade-offs

Implementation notes (added by the builder; the Assumptions block above
already pinned the interface — these are the concrete choices made while
writing `src/segqc/reference/ingest.py`):

- **Re-normalisation ignores `extract_feature_record`'s own `level_name`.**
  `extract_feature_record` → `feature_report.build_features_block` sources
  each `per_label[*]["level_name"]` from `compute_centroid`, which is called
  by `pipeline.py` with no `convention` argument — i.e. it is **always** the
  default `LabelConvention`, never the one `ingest_subject`/`ingest_cohort`
  received. Per the spec's Implementation Steps, the driver therefore
  discards that string and re-derives `level_name` from `entry["label"]`
  (the integer) via the **caller-supplied** `convention.name_of(...)` /
  `convention.is_known(...)`, so a custom convention passed to
  `ingest_subject` is actually honoured for skip/normalise decisions, even
  though the underlying pipeline call is convention-blind. This matches
  AC2/AC3 (which compare against the block's `geometry`/`offset_mm` values,
  not its `level_name` string) and keeps AC4/AC6/AC7 correct for a custom
  convention.
- **`ingest_subject` loads the seg image via `nibabel.load` directly**
  (not `segqc.io.load_volume`), since `extract_feature_record` only needs a
  `Nifti1Image`-like object exposing `.dataobj`/`.affine`/`.header` and the
  driver does no additional validation beyond what the feature engine
  already performs; this keeps the read path minimal and matches the
  Assumptions' "or `nibabel.load`" alternative.
- **`scan_path` is accepted but unread**, exactly as the Assumptions
  describe — `extract_feature_record` takes only the seg image today, so
  the parameter is pure interface-forward-compatibility, threaded through
  `ingest_cohort` (which locates a sibling `<subject_id>_scan.nii.gz` when
  present) down to `ingest_subject`.
- **`skipped_labels` and the per-subject size proxy are computed before the
  final canonical-rank sort**, then the collected `(level_name, features)`
  pairs are sorted once by `(CANONICAL_ORDER index, level_name)` — giving a
  single, total, deterministic ordering (AC11/AC12) with no reliance on
  `per_label` dict iteration order (which is already ascending-integer-label
  per `build_features_block`, but the driver does not depend on that).
- **A nonexistent `cohort_dir` is not special-cased** — `ingest_cohort` calls
  `os.listdir(cohort_dir)` directly, so a missing directory raises the
  stdlib `FileNotFoundError` naturally, matching the adversarial test's
  expectation (`pytest.raises((FileNotFoundError, OSError))`) without extra
  code.
