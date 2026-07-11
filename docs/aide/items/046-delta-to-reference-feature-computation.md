# Item 046 — Delta-to-reference feature computation

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 046 *(the fourth item in queue-005; consumes 045's loaded `ReferenceDistribution`; feeds 047's delta rule family)*
> **Objectives:** G3 (distinguish failure from legitimate variation — this item
> computes the *reference-relative* metrics that quantify how far a vertebra sits
> from its level's ground-truth distribution) and G7 (evaluable /
> regression-testable — the computation is pure and its serialised block is
> byte-deterministic and schema-validated). Realises the vision's
> "Reference-grounded" principle and the §5.4 "delta to reference (e.g. spline
> offset, distribution distance)" rule input.

---

## Description

Add the per-vertebra **delta-to-reference** feature layer that scores a case's
extracted features against a loaded reference artifact (item 045's
`ReferenceDistribution`). For each present label — given its level name (and the
selected size stratum) — compute distribution-relative metrics from that level's
`FeatureStats`:

- a **standard z-score** `(value − mean) / std` (reported as `null` when the
  reference `std == 0`, never `NaN`/`inf`);
- a **robust z-score** `(value − p50) / (IQR / 1.349)` where `IQR = p75 − p25`
  (reported as `null` when `IQR == 0`);
- a **percentile rank** (0–100) by piecewise-linear interpolation over the stored
  percentile grid anchored at `min`/`max`;
- an **out-of-range flag** against a configurable reference-percentile bound pair
  (default below `p1` / above `p99`);
- and an aggregate **distribution-distance** score per label — the RMS of the
  per-feature robust-z values over the features that have a defined robust-z.

Serialise these into the JSON report as a top-level **`reference_delta` block**
(a sibling of the existing `features`/`findings` blocks), keyed per label, and
extend the report schema (`report_schema_v0.json`) so the block validates.
Gracefully handle a level absent from the reference: the label's entry is marked
`available: false` with empty per-feature deltas and a `null`
distribution-distance — **never an error**.

Deliver a new module `src/segqc/reference/delta.py` (re-exported from
`src/segqc/reference/__init__.py`) providing a **pure computation** (case features
block + `ReferenceDistribution` in → per-label deltas out, no file I/O, no wall
clock) plus a JSON-ready serialiser, and extend `segqc.report.serialize_report`
with an optional `reference_delta` parameter exactly as `features`/`findings` were
added.

### Scope boundary — what this item is **not**

- **Not a rule / heuristic.** It computes and reports numbers; the config-driven
  **rule family** that *fires* when a vertebra is out-of-distribution (thresholds,
  severity, findings, verdict flow) is **item 047**. This item adds no rule, no
  `@register_rule`, and does not touch `segqc.aggregate`/verdict.
- **Not the bounds config switch.** Sourcing the level-aware bounds rule's min/max
  from the reference percentiles is **item 048**. This item does not modify
  `segqc.heuristics.bounds` or `segqc.config`/`default_config.yaml`.
- **Not the `segqc run` wiring or acceptance suite.** Loading the bundled default
  artifact into the pipeline, rendering the block into the human report, and the
  GT-in-range / perturbation-out-of-range acceptance suite are **item 049**. This
  item extends `serialize_report` (the seam) but does **not** wire the CLI/pipeline
  to actually populate it.
- **Not a change to the reference model, ingestion, or artifact.** It *consumes*
  043's `ReferenceDistribution`/`FeatureStats` and 045's loader/`ALL_STRATUM`
  unchanged and adds no statistics of its own beyond the delta metrics above.
- **Not new feature extraction.** It reads feature values out of the already-built
  `features` block (`extract_feature_record`'s output); it computes no geometry and
  imports no `segqc.features.*`.

---

## Public interface (the contract 047/049 build on)

New module `src/segqc/reference/delta.py`, re-exported from
`src/segqc/reference/__init__.py`. Exact private helpers are the builder's choice;
the **exported surface** below is the contract.

```python
REFERENCE_DELTA_VERSION: str = "1.0"       # version discriminator for the reference_delta block
DEFAULT_LOWER_PCT: int = 1                 # default lower out-of-range percentile
DEFAULT_UPPER_PCT: int = 99                # default upper out-of-range percentile
IQR_TO_SIGMA: float = 1.349               # IQR/1.349 ≈ sigma for a normal dist (robust-z scaling)

@dataclass(frozen=True)
class FeatureDelta:                        # one tracked feature's delta for one label
    feature: str                           # feature name (e.g. "physical_volume_mm3")
    value: float                           # the case's value for this (label, feature)
    z_score: Optional[float]               # (value - mean) / std; None when std == 0
    robust_z: Optional[float]              # (value - p50) / (IQR / IQR_TO_SIGMA); None when IQR == 0
    percentile_rank: float                 # 0..100, interpolated over the percentile grid
    out_of_range: bool                     # value < p{lower_pct} or value > p{upper_pct}

@dataclass(frozen=True)
class LabelDelta:                          # one label's delta result
    label: int
    level_name: str
    stratum: str                           # the stratum looked up (e.g. "all")
    available: bool                        # False when (level_name, stratum) absent from the reference
    features: Tuple[FeatureDelta, ...]     # one per tracked+present feature, sorted by name; empty when unavailable
    distribution_distance: Optional[float] # RMS of defined robust_z across features; None when unavailable / none defined
    out_of_range_features: Tuple[str, ...] # names flagged out_of_range, sorted

@dataclass(frozen=True)
class ReferenceDelta:                      # the whole-case delta result
    reference_delta_version: str           # == REFERENCE_DELTA_VERSION
    reference_schema_version: str          # the reference.schema_version used
    reference_source: str                  # reference.provenance.source (traceability)
    stratum: str                           # the requested stratum
    lower_pct: int
    upper_pct: int
    per_label: Mapping[int, LabelDelta]    # int label -> LabelDelta (all present case labels)

def compute_reference_delta(
    features_block: Mapping,               # the dict from segqc.pipeline.extract_feature_record
    reference: ReferenceDistribution,      # a loaded 045 artifact
    *,
    stratum: str = ALL_STRATUM,            # which stratum to look up (default "all")
    lower_pct: int = DEFAULT_LOWER_PCT,
    upper_pct: int = DEFAULT_UPPER_PCT,
) -> ReferenceDelta:
    """Pure: for each label in features_block["per_label"], look up its level's
    FeatureStats in `reference` (for `stratum`) and compute per-feature deltas over
    the features the reference tracks that are present for that label. A level (or
    stratum) absent from the reference yields an `available=False` LabelDelta. No
    file I/O, no wall clock, inputs never mutated. Raises ValueError only if
    lower_pct/upper_pct is not a percentile the reference stores."""

def reference_delta_to_dict(delta: ReferenceDelta) -> dict:
    """JSON-ready `reference_delta` block (see the canonical shape below). Pure."""
```

**Canonical JSON shape** produced by `reference_delta_to_dict` (the top-level
`reference_delta` block item 049 embeds in the report):

```json
{
  "reference_delta_version": "1.0",
  "reference_schema_version": "1.0",
  "reference_source": "synthetic-verse-cohort",
  "stratum": "all",
  "lower_pct": 1,
  "upper_pct": 99,
  "per_label": {
    "20": {
      "label": 20,
      "level_name": "L1",
      "available": true,
      "distribution_distance": 0.34,
      "out_of_range_features": [],
      "features": {
        "physical_volume_mm3": {
          "value": 30000.0,
          "z_score": 0.12,
          "robust_z": 0.08,
          "percentile_rank": 53.2,
          "out_of_range": false
        }
      }
    },
    "99": {
      "label": 99,
      "level_name": "UNKNOWN",
      "available": false,
      "distribution_distance": null,
      "out_of_range_features": [],
      "features": {}
    }
  }
}
```

`z_score` / `robust_z` / `distribution_distance` serialise to JSON `null` when
undefined; `percentile_rank` and `out_of_range` are always present for an available
feature. The block is added to `report_schema_v0.json` as a top-level optional
property (the top-level object is `additionalProperties: false`, so the property
must be declared).

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. Tests hand-build a small
`ReferenceDistribution` (via 043's dataclasses or `aggregate_reference` over
hand-built `FeatureRecord`s with known values) and a minimal `features_block`
(either from `extract_feature_record` on a fixture, or a hand-built dict with the
`per_label[str(label)] = {"label", "level_name", "geometry": {...}}` shape) so
every metric is hand-checkable. A "level" is a `level_name`; a "stratum" is a size
bucket (default `"all"`)._

- [ ] **AC1: a value equal to the reference mean yields `z_score == 0.0` and
      in-range.** For a tracked feature whose reference `std > 0`, a case value
      exactly equal to the feature's reference `mean` produces
      `FeatureDelta.z_score == 0.0` and `out_of_range == False`.

- [ ] **AC2: a value equal to the reference median yields `robust_z == 0.0` and
      `percentile_rank == 50.0`.** For a tracked feature whose reference
      `IQR = p75 − p25 > 0`, a case value exactly equal to the feature's reference
      `p50` produces `FeatureDelta.robust_z == 0.0` and
      `percentile_rank == 50.0`.

- [ ] **AC3: a far upper-tail value yields a large positive z, top percentile, and
      out-of-range.** A case value far above the reference `p99` (and above `max`)
      produces a large positive `z_score` (and `robust_z`), `percentile_rank ==
      100.0`, and `out_of_range == True` under the default `(p1, p99)` bounds.

- [ ] **AC4: a far lower-tail value yields a large negative z, bottom percentile,
      and out-of-range.** A case value far below the reference `p1` (and below
      `min`) produces a large negative `z_score`, `percentile_rank == 0.0`, and
      `out_of_range == True`.

- [ ] **AC5: `percentile_rank` interpolates over the stored grid.** A case value
      exactly equal to a stored percentile anchor returns that percentile
      (e.g. `value == p25` ⇒ `percentile_rank == 25.0`), and a value strictly
      between two adjacent anchors returns a rank strictly between their percentile
      levels (piecewise-linear, monotonic non-decreasing in value).

- [ ] **AC6: a degenerate reference (`std == 0` / `IQR == 0`) yields `null` z, not
      `NaN`/`inf`.** For a feature whose reference `std == 0`,
      `FeatureDelta.z_score is None`; for a feature whose reference `IQR == 0`,
      `FeatureDelta.robust_z is None`; and the serialised block carries JSON `null`
      for those fields (no `NaN`/`Infinity` token).

- [ ] **AC7: `out_of_range` honours the configurable bound percentiles.** With the
      default `lower_pct=1, upper_pct=99`, a value between `p1` and `p99` is
      in-range; with `lower_pct=25, upper_pct=75` a value between `p25` and `p75` is
      in-range while a value just below `p25` is `out_of_range == True` — i.e. the
      bound percentiles are read from the arguments.

- [ ] **AC8: `distribution_distance` is the RMS of the defined robust-z values.**
      For a label with ≥2 tracked features that each have a defined `robust_z`,
      `LabelDelta.distribution_distance` equals
      `sqrt(mean(robust_z_i ** 2))` over exactly those features (hand-computed),
      and features whose `robust_z is None` are excluded from the aggregate.

- [ ] **AC9: a level absent from the reference yields an `available == False`
      result, not a crash.** For a case label whose `level_name` is not a key in
      `reference.levels` (e.g. an `UNKNOWN` or a level the reference never saw),
      `compute_reference_delta` does **not** raise, that label's `LabelDelta` has
      `available == False`, `features == ()`, `distribution_distance is None`, and
      `out_of_range_features == ()`.

- [ ] **AC10: a tracked feature absent from the case block is omitted, not
      fabricated.** When the reference tracks `spline_offset_mm` but the case
      `features_block` carries no `stage3.per_label_offsets` entry for a label
      (e.g. a single-level case), that label's `LabelDelta.features` contains no
      `spline_offset_mm` `FeatureDelta` (and no crash); features the case *does*
      carry are still scored.

- [ ] **AC11: the serialised block validates against the extended report schema.**
      `segqc.report.serialize_report(verdict, case_id, config,
      reference_delta=reference_delta_to_dict(delta))` returns without raising a
      `jsonschema.ValidationError`, and the returned report carries the
      `reference_delta` block verbatim under the top-level `reference_delta` key.

- [ ] **AC12: the block metadata carries reference provenance.**
      `reference_delta_to_dict(delta)` has `reference_delta_version ==
      REFERENCE_DELTA_VERSION`, `reference_schema_version == reference.schema_version`,
      `reference_source == reference.provenance.source`, and the `stratum` /
      `lower_pct` / `upper_pct` used.

- [ ] **AC13: a stratum absent for a level yields `available == False`.** Requesting
      a `stratum` that a level does not carry (e.g. `stratum="s1"` for a level only
      present under `"all"`) yields that label's `LabelDelta.available == False`
      (unavailable, not an error), while the default `stratum="all"` resolves
      against an unstratified reference.

- [ ] **AC14: an out-of-grid bound percentile raises `ValueError`.**
      `compute_reference_delta(..., lower_pct=2)` (a percentile the reference's
      grid does not store) raises `ValueError` (a caller error is reported, not a
      `KeyError`), while the default `(1, 99)` — present in
      `DEFAULT_PERCENTILES` — is accepted.

- [ ] **AC15: computation is deterministic and non-mutating.** Two
      `compute_reference_delta` calls on the same `features_block` + `reference`
      produce **equal** `ReferenceDelta` results and byte-identical
      `json.dumps(reference_delta_to_dict(delta), sort_keys=True)` output, and
      neither the `features_block` nor the `reference` is mutated (a before/after
      deep comparison of both inputs is unchanged).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete contract is recorded here for audit; several
**pin an interface** items 047/049 must honour (hand back if reality diverges).

- **Block placement: a top-level `reference_delta` block, sibling of `features` /
  `findings`.** The queue text says "a `reference_delta` block per label alongside
  the existing features". "Alongside" is read as a **sibling top-level key** (not a
  nested `features.per_label[*].reference_delta` field), because (a) it keeps this
  item decoupled from `feature_report.build_features_block` and the frozen
  `labelFeatures` schema (which is `additionalProperties: false` with a fixed
  required set), and (b) it mirrors exactly how the Stage 2 `features` and Stage 4
  `findings` optional blocks were added (a top-level property + a `serialize_report`
  parameter, items 016/035). The block is itself keyed per label under its own
  `per_label`, satisfying "per label". **Pinned for 049:** the run wiring passes the
  computed block to `serialize_report(reference_delta=...)`.

- **Feature-value source and vocabulary = item 044's `INGESTED_FEATURES`.** The
  case values are read from the `features_block` produced by
  `extract_feature_record`: the four `LabelGeometry` scalars
  (`physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`) from
  `per_label[str(label)]["geometry"]`, and `spline_offset_mm` from
  `features_block["stage3"]["per_label_offsets"][*]["offset_mm"]` matched by
  `label`. Only the features the **reference actually tracks** (`reference.features`)
  are scored; a tracked feature not present for a label (e.g. `spline_offset_mm` for
  a single-level case with no `stage3`) is simply omitted (AC10), exactly as 044's
  ingestion omits an absent feature key. `delta.py` imports `INGESTED_FEATURES` from
  `segqc.reference.ingest` to name the geometry-vs-offset extraction, so the case
  side and the reference side share one vocabulary.

- **`level_name` for lookup is taken from the `features_block` per-label entry as
  is (default convention).** `extract_feature_record` labels each vertebra via the
  default `LabelConvention` (item 044's Decisions note the pipeline is
  convention-blind), and 045's committed reference was built through that same
  default convention, so the block's `level_name` string matches the reference's
  level keys directly. This item therefore does **not** take a `convention`
  parameter; a case QC'd under a non-default convention is out of scope here (and
  would be a 049 concern). An `UNKNOWN` / unmapped label simply misses the reference
  and is reported `available: false` (AC9).

- **Standard z-score = `(value − mean) / std`; `null` when `std == 0`.** Uses the
  reference's sample `std` (043 stores `ddof=1`, `0.0` for a single-value level).
  A zero `std` (constant or single-subject reference level) makes z undefined, so it
  is reported as `None`/JSON `null` rather than `inf`/`NaN` — keeping the artifact
  finite and JSON-valid (AC6), the same finiteness discipline 043/045 keep.

- **Robust z-score = `(value − p50) / (IQR / 1.349)`, `IQR = p75 − p25`; `null`
  when `IQR == 0`.** The `1.349` constant (`2 × 0.6745`) rescales the IQR to an
  approximate standard deviation for a normal distribution, so `robust_z` is
  comparable in magnitude to `z_score` but resistant to tail outliers — the
  reference-median/IQR robustness the queue text calls for. Exposed as the module
  constant `IQR_TO_SIGMA` so item 047's thresholds can reference the same scale. A
  zero IQR yields `None` (AC6).

- **`percentile_rank` is piecewise-linear over the stored percentile grid, anchored
  at `min`/`max`.** Anchor points are `{(min, 0), (p1, 1), (p5, 5), (p25, 25),
  (p50, 50), (p75, 75), (p95, 95), (p99, 99), (max, 100)}` (value → rank), which is
  monotonic non-decreasing in value since `min ≤ p1 ≤ … ≤ p99 ≤ max`. The rank of a
  case value is the linear interpolation of *rank as a function of value* between
  its bracketing anchors, **clamped to `[0, 100]`** (`value ≤ min ⇒ 0.0`,
  `value ≥ max ⇒ 100.0`). When consecutive anchors share a value (a flat segment)
  the **lower** rank is returned, so the mapping is single-valued and deterministic.
  This gives exact ranks at stored anchors (AC5) using only the percentiles the
  043 schema already carries — no re-access to raw samples.

- **Out-of-range uses a configurable percentile-bound pair, default `(p1, p99)`.**
  `out_of_range` is `value < reference[f"p{lower_pct}"]` **or**
  `value > reference[f"p{upper_pct}"]`, with `lower_pct`/`upper_pct` defaulting to
  `1`/`99`. The requested percentiles must be members of the reference's stored grid
  (`reference.percentiles`); a percentile not in the grid raises `ValueError`
  (AC14) rather than silently interpolating a bound — keeping the bound exact and
  the failure explicit. The default `(1, 99)` are always in `DEFAULT_PERCENTILES`.

- **`distribution_distance` = RMS of the defined per-feature `robust_z`.**
  `sqrt(mean(robust_z_i ** 2))` over exactly the tracked-and-present features whose
  `robust_z` is defined (`IQR > 0`); `None` when the label is unavailable or no
  feature has a defined `robust_z` (AC8). RMS-of-robust-z is chosen (over a
  Mahalanobis distance) because the 043 reference stores per-feature marginals, not
  a covariance matrix — a diagonal, robust, hand-computable aggregate that still
  grows with multi-feature divergence. Item 047's distribution-distance threshold
  reads this same scalar.

- **Stratum selection is an explicit argument, default `ALL_STRATUM` ("all").**
  The bundled default reference (045) is unstratified, so `compute_reference_delta`
  defaults to looking up `reference.levels[level_name]["all"]`. A caller may request
  a different `stratum`; a level (or stratum) missing from the reference yields
  `available: false` for that label (AC9/AC13). Choosing a stratum from a case's own
  size proxy at run time (mapping the case onto a size bucket) is deferred to the
  evaluation/wiring caller (item 049); this item only looks up the stratum it is
  told to.

- **`serialize_report` gains an optional `reference_delta` parameter, default
  `None`.** Mirrors the `features`/`findings` additions (items 016/035): when
  non-`None` the dict is embedded under the top-level `reference_delta` key and
  validated with the rest of the report; when `None` (default) no key is emitted,
  so every existing report (including the Stage 5 golden snapshots) is unchanged.
  `serialize_report_json` forwards the same parameter. The report `schema_version`
  stays `"0.1"`; the `reference_delta` block carries its own
  `reference_delta_version` discriminator (`"1.0"`), independent of the report and
  reference schema versions, matching the `features_version` precedent.

- **Report-schema extension only adds an optional property.** `report_schema_v0.json`
  gains a top-level optional `reference_delta` property (with new `referenceDelta` /
  `referenceLabelDelta` / `referenceFeatureDelta` definitions); the existing
  `required` list and every other block are untouched, so old reports still
  validate. Editing this shared package-data JSON is within `source_dir`
  (`src/segqc/`) and is the direct analogue of the Stage 2/4 schema extensions
  already made for `features`/`findings`.

- **Dependencies 043/044/045 are `✅` (merged).** `delta.py` imports
  `ReferenceDistribution`, `FeatureStats`, `ALL_STRATUM` (043) and `INGESTED_FEATURES`
  (044) from `segqc.reference`; tests may use `aggregate_reference` (043) /
  `bundled_default_reference` (045) to build inputs. All verified present in the
  merged tree (`src/segqc/reference/{schema,ingest,artifact}.py`,
  `src/segqc/reference/__init__.py`). If any of those surfaces changed, hand back.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): a new
`src/segqc/reference/delta.py`, a re-export line in
`src/segqc/reference/__init__.py`, a top-level property + three definitions in
`src/segqc/report_schema_v0.json`, and an optional parameter added to
`serialize_report` / `serialize_report_json` in `src/segqc/report.py`. No edits to
043/044/045 modules, the feature engine, `feature_report.py`, or `config.py`.

1. **Create `src/segqc/reference/delta.py`:**
   - Module docstring stating scope (per-vertebra delta-to-reference metrics from a
     loaded 045 artifact; a top-level `reference_delta` report block; no rules, no
     bounds switch, no run wiring), the metric definitions (standard z, robust z,
     percentile rank, out-of-range, distribution distance) and the determinism
     contract (pure, no wall clock, inputs unmutated).
   - Define constants `REFERENCE_DELTA_VERSION = "1.0"`, `DEFAULT_LOWER_PCT = 1`,
     `DEFAULT_UPPER_PCT = 99`, `IQR_TO_SIGMA = 1.349`.
   - Define the frozen dataclasses `FeatureDelta`, `LabelDelta`, `ReferenceDelta`
     per the interface block. Import `ReferenceDistribution`, `FeatureStats`,
     `ALL_STRATUM` from `segqc.reference.schema` and `INGESTED_FEATURES` from
     `segqc.reference.ingest` (both light — no NumPy/NiBabel; use `math`/builtins
     for the stats so the module has no heavy import).

2. **Implement the per-feature helper** `_feature_delta(value, stats, *, lower_pct,
   upper_pct)`:
   - `mean/std` → `z_score = (value − mean) / std if std != 0 else None`.
   - `p50 = stats.percentiles["p50"]`, `iqr = stats.percentiles["p75"] −
     stats.percentiles["p25"]` → `robust_z = (value − p50) / (iqr / IQR_TO_SIGMA)
     if iqr != 0 else None`.
   - `percentile_rank` via the anchor-interpolation rule above (build the sorted
     `(value, rank)` anchor list from `min`, the stored percentiles, `max`; clamp
     to `[0, 100]`; lower-rank tie-break on flat segments).
   - `lower = stats.percentiles[f"p{lower_pct}"]`, `upper =
     stats.percentiles[f"p{upper_pct}"]` (raise `ValueError` if the key is missing);
     `out_of_range = value < lower or value > upper`.
   - Return a `FeatureDelta`.

3. **Implement `compute_reference_delta(features_block, reference, *,
   stratum=ALL_STRATUM, lower_pct=DEFAULT_LOWER_PCT, upper_pct=DEFAULT_UPPER_PCT)`:**
   1. Validate `lower_pct`/`upper_pct` are in `reference.percentiles` once up front
      (`ValueError` otherwise), so an out-of-grid bound fails fast (AC14).
   2. Build a per-label view of the case: for each `str(label)` entry in
      `features_block["per_label"]`, read the int `label`, `level_name`, and the
      present tracked values — geometry scalars from `entry["geometry"]`, and
      `spline_offset_mm` from the matching `stage3.per_label_offsets` entry when
      present.
   3. For each label: resolve `level = reference.levels.get(level_name)`; if `None`
      or `stratum not in level`, emit an `available=False` `LabelDelta`
      (empty `features`, `distribution_distance=None`). Else, for each feature name
      in `reference.features` that the case carries **and** that the level's
      `feature_stats` carries, compute a `FeatureDelta` (sorted by feature name);
      set `out_of_range_features` from those flagged; set
      `distribution_distance` = RMS of the defined `robust_z` values (or `None`).
   4. Return `ReferenceDelta(REFERENCE_DELTA_VERSION, reference.schema_version,
      reference.provenance.source, stratum, lower_pct, upper_pct, per_label)`.
   5. Never mutate `features_block` or `reference`; read no clock.

4. **Implement `reference_delta_to_dict(delta)`** — produce the canonical JSON block
   (per-label dict keyed by `str(label)`, features as a name→dict mapping, `None` →
   JSON `null`, all numbers plain `float`/`int`). Pure; deterministic key order via
   the dataclass field order and sorted feature names.

5. **Extend `src/segqc/report_schema_v0.json`:** add a top-level optional
   `reference_delta` property referencing a new `#/definitions/referenceDelta`
   (object, `additionalProperties: false`, required `reference_delta_version` /
   `reference_schema_version` / `reference_source` / `stratum` / `lower_pct` /
   `upper_pct` / `per_label`); `per_label` values reference `referenceLabelDelta`
   (with `available`, `distribution_distance` as `["number","null"]`,
   `out_of_range_features`, and `features` → `referenceFeatureDelta` map);
   `referenceFeatureDelta` carries `value` (number), `z_score`/`robust_z`
   (`["number","null"]`), `percentile_rank` (number), `out_of_range` (boolean). Do
   **not** change the top-level `required` array.

6. **Extend `src/segqc/report.py`:** add an optional `reference_delta: dict | None
   = None` parameter to `serialize_report` (embed under `report["reference_delta"]`
   before `jsonschema.validate` when non-`None`) and forward it from
   `serialize_report_json`, mirroring the existing `features`/`findings` handling
   exactly.

7. **Re-export from `src/segqc/reference/__init__.py`** — add `FeatureDelta`,
   `LabelDelta`, `ReferenceDelta`, `compute_reference_delta`,
   `reference_delta_to_dict`, `REFERENCE_DELTA_VERSION` to the imports and
   `__all__` (import from the `.delta` submodule to avoid a circular import).

8. **Do not** add a rule / `@register_rule`, touch `segqc.heuristics.bounds` /
   `config.py` / `default_config.yaml`, wire the block into `segqc run` / the human
   report, or write `tests/` fixtures — those are items 047/048/049 and the
   test-writer's remit.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_046_reference_delta.py` (naming
  matches the `test_04x_*` siblings). Inputs are hand-built: a small
  `ReferenceDistribution` with known `FeatureStats` (built directly via the 043
  dataclasses, or via `aggregate_reference` over hand-built `FeatureRecord`s so the
  stats are hand-verifiable), and a minimal `features_block` dict with the
  `per_label[str(label)] = {"label": L, "level_name": "L1", "geometry": {...}}`
  shape (and, where `spline_offset_mm` is exercised, a `stage3.per_label_offsets`
  entry). Some ACs may instead drive `extract_feature_record` on a
  `build_clean_spine` fixture to confirm real-block compatibility.
- **One focused test per AC** (AC1–AC15 above), each asserting a single observable
  fact against hand-computed expectations. Where z/percentile values are asserted,
  cross-check the formula against the hand-built stats rather than a copied
  constant.
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty case** — a `features_block` with `per_label == {}` yields a
    `ReferenceDelta` with `per_label == {}` and serialises to a valid block.
  - **Value exactly on a bound** — `value == p1` is **in-range** (strict `<`/`>`
    comparison), while `value` one ulp below `p1` is out-of-range.
  - **All-features-degenerate label** — a level whose every tracked feature has
    `std == 0` and `IQR == 0` yields `z_score`/`robust_z` all `None` and
    `distribution_distance is None`, but `percentile_rank`/`out_of_range` still
    defined; no `NaN`/`Infinity` appears in `json.dumps(...,
    allow_nan=False)` output.
  - **Feature tracked by reference but stats absent for one level** — a level whose
    `feature_stats` omits a feature the reference lists in `.features` skips that
    feature for that label without error.
  - **Determinism / non-mutation** — deep-copy both inputs before the call and
    assert equality afterward; assert byte-identical `json.dumps(sort_keys=True)`
    across two calls (AC15).
  - **Schema round-trip** — the serialised block both validates in-report (AC11)
    and survives `json.dumps`/`json.loads` unchanged; a block with a `null`
    `z_score` still validates (the `["number","null"]` union).
  - **Bundled default** — `compute_reference_delta(extract_feature_record(seg_img,
    cfg), bundled_default_reference())` over a `build_clean_spine` case runs without
    error and marks present lumbar levels `available: true` (a light integration
    smoke test that the 045 default and this layer compose).

## Dependencies

- **Item 043 (✅ merged) — REQUIRED.** Provides `ReferenceDistribution`,
  `FeatureStats`, `LevelDistribution`, and `ALL_STRATUM` — the loaded data model and
  per-(level, stratum) stats this item scores against. Imported from
  `segqc.reference`.
- **Item 044 (✅ merged) — REQUIRED.** Provides `INGESTED_FEATURES` — the shared
  feature-name vocabulary this item extracts from the case block and matches against
  `reference.features`. Imported from `segqc.reference`.
- **Item 045 (✅ merged) — REQUIRED.** Provides `load_artifact` /
  `bundled_default_reference` — how a caller (and the tests) obtain a loaded
  `ReferenceDistribution`. This item computes deltas against whatever loaded
  reference it is handed.
- **Stage 2/3 feature engine + pipeline (items 011–022, 035, ✅) — used, not
  modified.** `segqc.pipeline.extract_feature_record` produces the `features_block`
  whose per-label `geometry` / `stage3.per_label_offsets` values this item reads.
- **Report serialiser + schema (items 009/016/035, ✅) — extended, not rewritten.**
  `segqc.report.serialize_report` gains an optional `reference_delta` parameter and
  `report_schema_v0.json` gains one optional top-level property, exactly as
  `features`/`findings` were added.
- **Downstream (this item feeds them):** **047** (the delta rule family reads these
  per-label metrics — `robust_z` / `percentile_rank` / `distribution_distance` /
  `out_of_range` — and fires against configured thresholds), and **049** (wires the
  computed block into `segqc run`'s report and asserts GT-in-range /
  perturbation-out-of-range).

## Decisions & Trade-offs

To be updated during implementation.
