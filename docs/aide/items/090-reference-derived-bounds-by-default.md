# Item 090 — Reference-derived bounds by default, grounded on real VerSe distributions

> **Created:** 2026-07-18 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7)
> **Queue:** [`../queue/queue-012.md`](../queue/queue-012.md) · Item 090 *(second of
> three; the distribution-grounded defaults, shipped **after** item 089 fixed the
> FOV rule semantics so a threshold is not tuned to fit a mis-specified rule, and
> **before** item 091 runs the calibration + held-out measurement)*
> **Objectives:** G3 (distinguish failure from legitimate variation — the
> per-level spread and small legit fragments of **real** GT are variation, not
> defects) and G7 (evaluable / regression-testable — proven on committed
> synthetic fixtures + the committed real reference artifact, no raw scans needed)
> **Suggested branch:** `aide/090-reference-derived-bounds-by-default`

---

## Description

Ship the **reference-derived** heuristic path as the shipped **default**, grounded
on the committed **real** reference artifact
[`src/segqc/reference/reference_verse_v1.json`](../../../src/segqc/reference/reference_verse_v1.json)
(`provenance.source == "verse-v1"`, 25 levels C1…S, 80 VerSe19 **training**
subjects). Item 048 already built the config switch that lets the `bounds` rule
source its per-level `min`/`max` from a loaded `ReferenceDistribution`; item 049
wired reference attachment into `segqc run`. But the **shipped default is still
the synthetic-calibrated hand-set constants** — `bounds` `source` code-defaults to
`hand-set`, reference mode is OFF by default, and when on it loads the **synthetic**
`reference_default.json`. On the first real held-out VerSe19 measurement
(2026-07-17) those hand-set constants flagged **4/6** of the false-positive cases
via `bounds` and **3/6** via `fragmentation`. Real GT is not defective: it has a
much **wider per-level volume/extent spread** than the synthetic spine (so the
narrow hand-set bands fire), and it contains **small legitimately-disconnected
fragments** at up to ~4–7 components per level (so the hand-set `island_min_voxels`
floor fires). This item re-grounds both rules on the real per-level percentiles the
artifact already records.

Two rules are re-grounded, both **percentile-based from the artifact**:

- **`bounds`** — flip the code-side `source` default from `hand-set` to
  `reference`, so a default run compares each label's volume/extent against its
  **level's** stored `[p{lower}, p{upper}]` band (the item-048 machinery, now the
  default) instead of the coarse per-*group* hand-set constants. Real GT's wide
  per-level spread lives **inside** those bands; a gross synthetic over/under-
  segmentation still falls **outside** them.

- **`fragmentation`** — this rule has **no reference path yet** (it ships only the
  global hand-set constants `fragmentation_index_threshold = 0.75` /
  `island_min_voxels = 50`). Add one, mirroring item 048's bounds design: a
  `source: hand-set | reference` switch (code-default `reference`) that, in
  reference mode, derives **per-level** tolerances from the artifact's stored
  percentiles for the two fragmentation features the reference already tracks —
  `largest_component_fraction` (the fragmentation index) and `component_count`.

The default production reference the run path attaches becomes **verse-v1**, while
`reference_default.json` stays the **untouched synthetic Plane-1 baseline** (see
"The three planes" below).

### How the two rules reach the reference (unchanged plumbing)

Both rules read the already-loaded reference from `record["reference"]` — the key
`run_qc_with_reference` already attaches (item 049 step 3:
`rule_record = {**features_block, "reference": reference, "reference_delta": …}`).
`bounds` consumes it today; `fragmentation` will read the same key. **No pipeline
change** is needed to feed `fragmentation` the reference — this item only flips
which artifact the default run loads, flips reference mode on by default, and adds
`fragmentation`'s reference-derived derivation + evaluation path.

### The fragmentation re-derivation (the new design work)

The reference records, per level/stratum, a `FeatureStats` for
`largest_component_fraction` and for `component_count` (verified present in both
committed artifacts). Reference mode derives, per covered level:

```
reference_fragmentation_for_level(reference, level_name, *, lower_pct, upper_pct, stratum)
    -> { "fragmentation_index_threshold": lcf.percentiles[f"p{lower_pct}"],   # floor
         "max_component_count":           cc.percentiles[f"p{upper_pct}"] }    # ceiling
    or None                                                                    # uncovered
```

Note the **two features pull opposite percentile directions**: the fragmentation
index is a *floor* (real values sit near 1.0; fire strictly **below** the lower
percentile), the component count is a *ceiling* (real values sit at 1–~7; fire
strictly **above** the upper percentile). In reference mode, for a **covered**
level, the rule's two checks become:

- **Index check (§6 mode 2 — split into comparable pieces):** fire when the
  per-case `components.fragmentation_index` (alias `largest_component_fraction`) is
  **strictly below** the level's reference `largest_component_fraction`
  `p{lower_pct}` (default `p1`), replacing the hand-set `0.75`.
- **Excess-fragment check (§6 mode 3 — rogue islands):** fire when the per-case
  `components.component_count` is **strictly above** the level's reference
  `component_count` `p{upper_pct}` (default `p99`). This **replaces** the absolute
  `island_min_voxels` voxel floor for covered levels — precisely because that floor
  is the false-positive source (real GT has legit sub-50-voxel fragments), and the
  reference records **no per-island voxel distribution** to re-derive a voxel floor
  from. "How many disconnected pieces is normal at this level" is the real-grounded
  signal the artifact *does* carry.

For an **uncovered** level (or a covered level missing one of the two stats), that
check falls back to the hand-set constant — never crashes (requirement 3).

### The three planes stay separate (the sensitivity resolution)

The queue's anti-gaming constraint is explicit: FPR and sensitivity are a single
acceptance pair; a real-grounded threshold must not silently un-flag a synthetic
defect. Re-grounding fragmentation on real per-level variation creates a genuine
tension for the **single-tiny-island** sub-mode: real GT is *more* fragmented than
a synthetic clean body with one 27-voxel island added, so against the **real**
distribution that island is legitimately within tolerance. The three-planes
separation resolves this and it is what "reference_default.json stays the untouched
synthetic baseline" buys us:

- **Plane 1 (synthetic code/function testing).** The Stage-5 corpus is a synthetic
  clean spine perturbed. Its own cohort baseline is `reference_default.json`
  (`largest_component_fraction p1 == 1.0`, `component_count p99 == 1.0` for L1–L5 —
  verified). Evaluated against **that** synthetic reference, `mode2_fragment`
  (index ≈ 0.5 < 1.0) and `mode3_inject_islands` (count == 2 > 1) both still fire.
  Plane-1 sensitivity is preserved and reproducible.
- **Plane 2 (real-GT knowledge base).** verse-v1's wide real bands are what the
  **shipped default** grounds on, so real GT stops flagging.
- **Plane 3 (scoring new segmentations).** Stage 16, out of scope.

The Stage-5 **goldens** (`tests/corpus/golden/*.json`) are generated by the
golden harness via plain `run_qc` — which attaches **no** reference — so both rules
degrade to hand-set there (reference absent ⇒ fallback, item 048 AC9) and every
golden stays **byte-identical** after this item (AC). The default-source flip only
manifests once a reference is attached (a default `segqc run`, or an explicit
`run_qc_with_reference`).

### What this item is **not**

- **Not the recalibration run or the held-out measurement.** Grid-searching the
  percentile pair / tolerances against real FPR-vs-sensitivity, and reporting the
  held-out number, is **item 091**. This item ships defensible *defaults*
  (`p1`/`p99`, matching item 048's bounds convention) and the mechanism; 091 tunes
  and measures them and closes G3.
- **Not the executable anti-gaming sensitivity guard.** That gate (Stage-5 corpus
  **and** Stage-5 perturbations on **real** GT, per-mode sensitivity ≥ item 057's
  baseline) is **item 091**. This item only asserts, on committed fixtures, that
  its own default does not regress the synthetic corpus (AC).
- **Not a change to `reference_default.json`.** The synthetic artifact is
  byte-untouched and `bundled_default_reference()` still returns it — it stays the
  pinned Plane-1 baseline. Only the *production* default artifact accessor points
  at verse-v1 (AC).
- **Not a change to the FOV rules, the report schema, the reference schema, the
  reference builder, `config_hash`'s canonical field list, or
  `SUPPORTED_SCHEMA_VERSION`.** Item 089 owns the FOV semantics. This item flips
  code-side defaults (source, reference-enabled, default artifact) and adds one
  rule path; `default_config.yaml` documents the flip as **comments only** so
  `load_config(default_config_path()) == default_config()` and `config_hash` stay
  byte-stable (items 048/049/065 precedent).
- **Not a new feature extractor.** `components.component_count` /
  `fragmentation_index` / `largest_component_fraction` are already in the per-case
  record (item 028) and the two matching stats are already in the reference
  (items 043/045).

### Config surface (defaults flipped code-side; YAML documents only)

```yaml
rules:
  bounds:
    params:
      # source code-default flips hand-set -> reference (item 090). Documented
      # here as a COMMENT; no active key (keeps load_config(default) == default
      # and config_hash byte-stable). reference_lower_pct/upper_pct/stratum
      # unchanged (1 / 99 / all).
      # source: reference
  fragmentation:
    params:
      # NEW source switch, code-default reference (item 090). reference mode:
      #   fragmentation_index_threshold <- largest_component_fraction p{lower}
      #   max_component_count           <- component_count p{upper}
      # Uncovered level/metric -> hand-set fragmentation_index_threshold / island_min_voxels.
      # source: reference
      # reference_lower_pct: 1
      # reference_upper_pct: 99
      # reference_stratum: all
      fragmentation_index_threshold: 0.75   # hand-set fallback (unchanged)
      island_min_voxels: 50                 # hand-set fallback (unchanged)

reference:
  # enabled code-default flips false -> true; artifact_path default resolves to
  # the bundled verse-v1 production artifact (item 090). Documented as COMMENTS;
  # a new --no-reference CLI flag disables it. reference section is excluded from
  # config_hash's canonical field list, so this changes no artifact provenance.
  # enabled: true
  # artifact_path: null   # null -> bundled_production_reference() (verse-v1)
```

---

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each. Tests
construct/load a `ReferenceDistribution` (verse-v1 via the new production
accessor, or a hand-built one with chosen percentiles) and hand-build per-case
records with `per_label[str(label)] = {"label", "level_name", "geometry": {…},
"components": {"fragmentation_index"/"largest_component_fraction",
"component_count", "component_sizes"}}`, mirroring items 028/048. "Reference
attached" means `record["reference"] = <ReferenceDistribution>`._

### Default resolves to reference-derived, grounded on verse-v1

- [ ] **AC1: the production default reference is verse-v1.** A new accessor
      `segqc.reference.bundled_production_reference()` (and its
      `…_path()` sibling) loads a `ReferenceDistribution` whose
      `provenance.source == "verse-v1"` covering 25 levels (C1…C7, T1…T12, L1…L5,
      S), loadable via the existing `load_artifact`.

- [ ] **AC2: `bounds` code-defaults to `source: reference`.** Under
      `default_config()` (no `rules.bounds.params.source` key) **with a covering
      reference attached**, `BoundsRule.evaluate` sources its bounds from the
      reference — a value outside the level's `[p1, p99]` band fires a finding whose
      reason names the reference percentile ("… reference minimum … (p1) for level
      …"), *not* the hand-set "… for {group} group" text. (Confirms the code
      default returns `"reference"`, superseding item 048's `"hand-set"` default.)

- [ ] **AC3: `fragmentation` code-defaults to `source: reference`.** Under
      `default_config()` (no `rules.fragmentation.params.source` key) **with a
      covering reference attached**, `FragmentationRule.evaluate` uses the
      reference-derived per-level tolerances (AC5/AC6 semantics), not the hand-set
      `0.75` / `50` — proven by a case that passes the hand-set thresholds but
      fires (or vice-versa) under the reference-derived ones.

- [ ] **AC4: reference mode is ON by default in the run path, pointing at
      verse-v1.** A default `segqc run` (no `--reference` flag, bundled default
      config) attaches the verse-v1 reference and writes a top-level
      `reference_delta` block whose report validates against `report_schema_v0.json`;
      a new `--no-reference` flag disables reference mode and restores the
      reference-less report shape. (This deliberately supersedes item 049 AC6's
      "OFF by default"; see Assumptions.)

### Reference-derived `fragmentation` derivation (percentile-based)

- [ ] **AC5: the index threshold is the level's `largest_component_fraction`
      lower percentile.** `reference_fragmentation_for_level(reference, level, *,
      lower_pct, upper_pct, stratum)` returns a dict whose
      `fragmentation_index_threshold` equals the level's stored
      `largest_component_fraction.percentiles[f"p{lower_pct}"]`, and in reference
      mode a per-case `fragmentation_index` **strictly below** that value fires
      exactly one `rule_id == "fragmentation"` index finding (`"Fragmentation:"`
      tag); a value equal to or above it does not.

- [ ] **AC6: the excess-fragment ceiling is the level's `component_count` upper
      percentile.** The same helper's `max_component_count` equals the level's
      stored `component_count.percentiles[f"p{upper_pct}"]`, and in reference mode
      a per-case `component_count` **strictly above** that value fires exactly one
      `rule_id == "fragmentation"` rogue-island/excess finding; a count equal to or
      below it does not. (The absolute `island_min_voxels` floor is **not** applied
      for a covered level.)

- [ ] **AC7: the derived tolerances track the configured percentile pair.** The
      `fragmentation_index_threshold` / `max_component_count` compared against (and
      quoted in the reason) change accordingly when `reference_lower_pct` /
      `reference_upper_pct` are set to a different stored pair (e.g. `p5` / `p95`) —
      they are read from the artifact, not hard-coded.

- [ ] **AC8: reference-mode fragmentation reasons are explainable and distinct.**
      A reference-mode fragmentation finding's `reason` names the offending label,
      its level, the measured value, and the reference tolerance with its
      percentile — distinguishable from the hand-set reason (which quotes the fixed
      `0.75` / `island_min_voxels`).

- [ ] **AC9: pure, `None` for uncovered.** `reference_fragmentation_for_level`
      returns `None` for a level (or stratum) absent from the reference and for a
      covered level lacking **both** tracked stats; it never mutates `reference` and
      reads no file/clock. A partial return (one stat present, one absent) carries
      only the present key.

### Clean degradation for levels absent from the reference (requirement 3)

- [ ] **AC10: `bounds` falls back to hand-set for an uncovered level.** In
      reference mode, a label whose `level_name` is **absent** from verse-v1 (e.g.
      a transitional `T13` / `L6`, or `Cocygis`) is evaluated against the hand-set
      group bounds (fires iff it would under hand-set), never crashing — item 048
      AC5's behaviour, re-asserted under the new default.

- [ ] **AC11: `fragmentation` falls back to hand-set for an uncovered level.** In
      reference mode, a label whose `level_name` is absent from the reference (or a
      covered level whose reference lacks a needed stat) is evaluated against the
      hand-set `fragmentation_index_threshold` (0.75) and `island_min_voxels` (50),
      never crashing — including the absolute island-voxel floor for that
      uncovered level.

### Plane-1 preserved: synthetic baseline untouched, corpus verdicts hold, goldens stable (requirements 4 & 5)

- [ ] **AC12: `reference_default.json` is byte-untouched and still the synthetic
      baseline.** The committed `src/segqc/reference/reference_default.json` is
      byte-identical to its pre-item version, and `bundled_default_reference()`
      still returns a `ReferenceDistribution` with
      `provenance.source == "synthetic-verse-cohort"` covering exactly L1–L5 (the
      synthetic Plane-1 pointer is unchanged — only the *production* accessor is
      new).

- [ ] **AC13: synthetic fragmentation sensitivity holds against the synthetic
      baseline.** Running the Stage-5 corpus `mode2_fragment` and
      `mode3_inject_islands` cases (both target label 22 = L3) through the pipeline
      under `default_config()` with **`reference_default.json`** attached still
      produces the expected `rule_id == "fragmentation"` finding on label 22 for
      each — the reference-derived derivation, evaluated against the data's own
      cohort baseline, does not un-flag a synthetic split or injected island.

- [ ] **AC14: real-grounded `bounds` still catches a gross synthetic size defect.**
      Running the Stage-5 corpus `mode6_crop_at_border` case (target label 22 = L3,
      a gross under-segmentation) through the pipeline under `default_config()` with
      the **verse-v1** reference attached still fires ≥1 `rule_id == "bounds"`
      finding on label 22 (its volume/extent falls **below** real L3's `p1`) — a
      real-grounded band does not un-flag a gross over/under-segmentation
      (requirement 5's parenthetical).

- [ ] **AC15: the Stage-5 goldens remain byte-identical.** The item-042 golden
      harness (`segqc.synth.golden.write_goldens` → plain `run_qc`, no reference)
      reproduces every committed `tests/corpus/golden/<case_id>.json`
      byte-for-byte; `check_case_golden` is `True` for all nine cases. The
      default-source flip does not leak into the reference-less path (both rules
      fall back to hand-set when no reference is attached).

### Config & determinism stability

- [ ] **AC16: parsed default config and `config_hash` are byte-stable.**
      `load_config(default_config_path()) == default_config()` still holds
      (`default_config.yaml` documents the flips as **comments only**, no active
      keys), `schema_version` is still `"0.1"`, and
      `reference.config_hash(bundled_default_config())` equals a pre-item snapshot —
      the reference-derived defaults live in code, and `config_hash`'s canonical
      field list excludes the `reference` section.

- [ ] **AC17: reference-mode `fragmentation` is deterministic and non-mutating.**
      Two `FragmentationRule.evaluate` calls (and two `run_rules`) on the same
      `(record, config)` with a reference attached return equal finding lists in
      the same order (ascending integer label, index finding before excess-fragment
      finding); neither `record`, `record["reference"]`, nor `config` is mutated
      (deep before/after equality) — the item-028/048 contract holds after the
      refactor.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete, testable design is recorded here for the
validator to surface at the queue boundary.

- **"Ship the reference-derived path as the default" = flip three coupled
  **code-side** defaults, keeping `default_config.yaml` documentation-only.**
  (a) `bounds.source` code-default `hand-set` → `reference`; (b) a **new**
  `fragmentation.source` code-default `reference`; (c) `reference.enabled`
  code-default `false` → `true` **and** the default production artifact →
  verse-v1. Doing this in **code** (the `rule_param(..., default=…)` call sites and
  the CLI reference resolution) rather than as active YAML keys keeps the parsed
  `rules` dict identical, so `load_config(default_config_path()) ==
  default_config()`, `config_hash`, and the Stage-5 goldens stay byte-stable —
  exactly the pattern items 048/049/065 established for behaviour-changing defaults
  that must not churn provenance. If a reviewer prefers the flip expressed as
  active YAML (accepting the `config_hash`/golden regeneration), the
  builder/validator hands back.

- **Reference mode ON-by-default deliberately supersedes item 049 AC6, and adds a
  `--no-reference` escape hatch.** Item 049 shipped reference mode OFF by default so
  the report shape and item-042 goldens were untouched; item 090's mandate is to
  make the reference-derived path *the default*, which requires the default run to
  attach the reference. The default `segqc run` report therefore now carries a
  `reference_delta` block, and the reference-grounded rules (`bounds` reference
  mode, `fragmentation` reference mode, and — a consequence of `reference.enabled`
  — item 047's `reference_delta` rule) become active by default. A new
  `--no-reference` flag restores the reference-less path; the builder reconciles
  item 049's "OFF by default" assertion to drive the off-path via `--no-reference`
  (behaviour preserved, not deleted). The **Stage-5 goldens are unaffected** because
  the golden harness uses plain `run_qc`, which attaches no reference. The
  validator should surface this default-behaviour change explicitly.

- **`fragmentation`'s reference path mirrors `bounds`' item-048 design exactly.**
  Same `source: hand-set | reference` switch read via `config.rule_param`; same
  `record["reference"]` attribute-access-only consumption (no file I/O, type-only
  `TYPE_CHECKING` import of `ReferenceDistribution`); same per-level/per-metric
  **fallback to the hand-set constant**; same default percentile pair `(1, 99)` and
  stratum `"all"`; same inclusive-band firing (strictly outside fires, equal
  passes). An unrecognised `source` raises `ValueError` before per-label
  processing, and a `reference_lower_pct`/`upper_pct` absent from
  `reference.percentiles` raises `ValueError`, mirroring `bounds` AC10/AC11.

- **The island / rogue-fragment check is re-expressed in reference mode as an
  excess-`component_count` check, because the reference carries no per-island
  voxel distribution.** The artifact records `component_count` and
  `largest_component_fraction` per level, not the sizes of individual non-dominant
  components. The real-grounded signal for "too many disconnected pieces" is
  therefore the per-level `component_count` upper percentile; a covered level's
  absolute `island_min_voxels` floor is **replaced** (not ANDed) by that check —
  and it is precisely that floor (firing on legit sub-50-voxel real fragments) that
  drove the `fragmentation` false positives. The absolute floor is retained only as
  the **hand-set fallback** for uncovered levels (AC11). Recorded as a trade-off
  (see Decisions): against the **real** distribution a lone tiny synthetic island
  is within tolerance; Plane-1 sensitivity for that mode is preserved by evaluating
  the synthetic corpus against the **synthetic** reference (AC13), per the
  three-planes separation the queue mandates.

- **The synthetic corpus's own cohort baseline is `reference_default.json`.** The
  Stage-5 corpus is a synthetic clean spine (L1–L5) perturbed; its matching
  reference is the synthetic artifact (`largest_component_fraction p1 == 1.0`,
  `component_count p99 == 1.0` for L1–L5 — verified in the committed file), against
  which `mode2_fragment` (index ≈ 0.5) and `mode3_inject_islands` (count == 2) fire
  (AC13). The **shipped production default** grounds on verse-v1 (real). This split
  is the concrete meaning of "reference_default.json remains the untouched
  synthetic test baseline" while "only the default config's bounds source changes".

- **Default percentiles `(1, 99)` and stratum `"all"` are shipped, not tuned.**
  These match item 048's bounds convention (`delta.DEFAULT_LOWER_PCT` /
  `DEFAULT_UPPER_PCT`, `schema.ALL_STRATUM`). They are the *mechanism's* defaults;
  item 091's calibration grid-searches the percentile pair / tolerances against
  real held-out FPR-vs-sensitivity and may revise them. A per-level `component_count`
  `p99` ceiling admits ~1% of real per-level training variation by construction —
  an accepted, documented starting point 091 refines (it could instead use `max`).

- **verse-v1 covers C1…C7, T1…T12, L1…L5, S — not the transitional levels
  (`T13`, `L6`, `Cocygis`) `bounds`/`labels` recognise.** A label at a
  reference-absent level exercises the fallback path (AC10/AC11); this is expected,
  not a defect. The reference's 25 covered levels are enumerated from the committed
  artifact, not assumed.

- **Dependencies 048, 049, 043/045, 028, 027, 089 are `✅` (merged).** The bounds
  reference switch, the `run_qc_with_reference` attachment of `record["reference"]`,
  the `ReferenceDistribution` model + `load_artifact`, the fragmentation rule, the
  hand-set bounds, and the FOV rule semantics all exist in the merged tree. This
  item consumes their shapes and modifies `bounds.py` (one default), `fragmentation.py`
  (new path), `reference/artifact.py` (new accessor), `cli.py` (default flip +
  `--no-reference`), and `default_config.yaml` (comments). If any pinned interface
  diverged (e.g. `run_qc_with_reference` no longer attaches `record["reference"]`),
  the builder/validator hands back.

## Implementation Steps

Intended code path — all under `source_dir = src/segqc`. No change to the report
schema, the reference schema, the reference builder, `config.py`'s `config_hash`,
the FOV rules, or `SUPPORTED_SCHEMA_VERSION`.

1. **`src/segqc/reference/artifact.py`** — add the production-artifact accessors
   alongside the existing synthetic ones (leave `DEFAULT_ARTIFACT_NAME` /
   `default_artifact_path` / `bundled_default_reference` **unchanged**):
   - `PRODUCTION_ARTIFACT_NAME = "reference_verse_v1.json"`.
   - `bundled_production_reference_path() -> Path` (mirrors
     `default_artifact_path`, via `importlib.resources`).
   - `bundled_production_reference() -> ReferenceDistribution`
     (`load_artifact(bundled_production_reference_path())`).
   - Export both from `segqc/reference/__init__.py`'s `__all__`.

2. **`src/segqc/heuristics/bounds.py`** — flip the code-side source default:
   introduce `DEFAULT_SOURCE = _SOURCE_REFERENCE` and read
   `source = config.rule_param(self.rule_id, "source", default=DEFAULT_SOURCE)`
   (was `default=_SOURCE_HAND_SET`). No other bounds change — the reference-mode
   evaluation, per-metric fallback, reason text, `ValueError` paths, ordering, and
   non-mutation are all item 048's and stay intact.

3. **`src/segqc/heuristics/fragmentation.py`** — add the reference path, mirroring
   `bounds.py`:
   - Module constants: `_SOURCE_HAND_SET = "hand-set"`, `_SOURCE_REFERENCE =
     "reference"`, `_VALID_SOURCES`, `DEFAULT_SOURCE = _SOURCE_REFERENCE`,
     `DEFAULT_REFERENCE_LOWER_PCT = 1`, `DEFAULT_REFERENCE_UPPER_PCT = 99`,
     `DEFAULT_REFERENCE_STRATUM = "all"`. Type-only `TYPE_CHECKING` import of
     `ReferenceDistribution`. Add new public names to `__all__`.
   - Pure helper `reference_fragmentation_for_level(reference, level_name, *,
     lower_pct, upper_pct, stratum="all") -> Optional[Dict[str, float]]`: validate
     `lower_pct`/`upper_pct` ∈ `reference.percentiles` (else `ValueError` naming the
     offender); look up `reference.levels.get(level_name)` then `.get(stratum)`
     (`None` if either absent); read
     `feature_stats["largest_component_fraction"].percentiles[f"p{lower_pct}"]`
     into `fragmentation_index_threshold` and
     `feature_stats["component_count"].percentiles[f"p{upper_pct}"]` into
     `max_component_count` (each present only if its stat exists); return the
     (possibly partial) dict, or `None` when neither stat is present. Attribute
     access only; never mutate `reference`.
   - In `evaluate`: read `source` (validate up-front, before the per-label loop —
     `ValueError` on an unknown value, matching bounds AC10); when `reference`,
     read `reference_lower_pct` / `reference_upper_pct` / `reference_stratum` and
     `reference = record.get("reference")`.
   - Per label, resolve the effective tolerances: start from the hand-set
     `frag_threshold` / `island_min`; in reference mode with a reference attached,
     call `reference_fragmentation_for_level(...)` for the label's level and, when
     it returns a dict, use its `fragmentation_index_threshold` for the index check
     and its `max_component_count` for a **component-count ceiling** check
     (`component_count > max_component_count` fires), **bypassing** the
     `island_min_voxels` floor for that covered level. When the helper returns
     `None`, or for the metric it did not supply, fall back to the hand-set check
     (index vs `0.75`; island vs `island_min_voxels`) for that label — never crash.
   - Reason text: reference-mode findings quote the level, the measured value, and
     the reference tolerance + percentile ("… fragmentation_index={v} is below
     reference floor {lo} (p{lower}) for level {L}" / "… component_count={n}
     exceeds reference maximum {hi} (p{upper}) for level {L}"); hand-set findings
     keep today's text (AC8). Preserve the fixed within-label order (index finding
     before excess/island finding), ascending integer-label iteration, per-`(label)`
     granularity, and record/reference/config immutability (AC17).

4. **`src/segqc/cli.py` `_handle_run`** — flip reference-on-by-default and add the
   escape hatch:
   - `reference_enabled = (bool(args.reference) or bool(cfg.reference_param(
     "enabled", True))) and not bool(args.no_reference)` (code default now
     **True**; `--no-reference` forces off).
   - When enabled and no `--reference-artifact` / `reference.artifact_path`, load
     `bundled_production_reference()` (verse-v1) instead of
     `bundled_default_reference()`. Keep the load-error → stderr + `return 1`
     wrapping (item 049).
   - Add the `--no-reference` `store_true` argument to the `run` subparser.

5. **`src/segqc/default_config.yaml`** — update the existing **commented**
   `rules.bounds.params` / `reference:` blocks and add a commented
   `rules.fragmentation.params` source block, documenting the new code-side
   defaults (`source: reference`, `reference.enabled: true`, artifact → verse-v1)
   and the fragmentation percentile derivation. **No active keys** — the file must
   still parse to a dict equal to `default_config()` (AC16).

6. **Do not** touch `config.py`'s `config_hash`, `run_qc` / `run_qc_with_reference`
   bodies (the attachment already exists), the report/schema, the extractors, the
   FOV rules, or `heuristics/__init__.py`'s registration block. The only new import
   edges are `fragmentation.py → segqc.reference.schema` (type-only) and the new
   artifact accessor.

## Testing Strategy

- **Framework:** `pytest`. New module
  `tests/test_090_reference_derived_defaults.py` (naming matches the `test_0NN_*`
  siblings). Use the item-026 registry snapshot/restore fixture (save/restore
  `segqc.heuristics.rule._RULES`) as the bounds/fragmentation test modules do.
- **Hand-built records + references:** a small helper assembles a per-case record
  with `per_label[str(label)] = {"label", "level_name", "geometry": {…},
  "components": {"fragmentation_index", "component_count", "component_sizes"}}`.
  References come from three sources: `bundled_production_reference()` (verse-v1,
  real), `bundled_default_reference()` (synthetic), and a hand-built
  `schema.ReferenceDistribution` with chosen percentiles for one or two levels
  (for AC5–AC9, isolating the derivation from real numbers).
- **One focused test per AC (AC1–AC17):**
  - Defaults: production accessor + provenance (AC1); bounds default source via
    reference-mode reason (AC2); fragmentation default source via a
    hand-set-passes/reference-fires case (AC3); CLI default-on `reference_delta`
    block + `--no-reference` restores shape, via `cli.main(["run", …])` into a tmp
    `--out` and `jsonschema.validate` (AC4).
  - Fragmentation derivation: helper returns index floor from
    `largest_component_fraction p{lower}` and fires strictly-below (AC5); ceiling
    from `component_count p{upper}` and fires strictly-above (AC6); tolerances track
    a `p5`/`p95` reconfiguration (AC7); reason substrings (AC8); `None` for
    uncovered level/stratum, partial dict for one-stat-present, non-mutation (AC9).
  - Fallback: bounds uncovered-level → hand-set (AC10); fragmentation
    uncovered-level → hand-set floor + island_min_voxels (AC11).
  - Plane-1: `reference_default.json` byte-identity + `bundled_default_reference`
    provenance/levels (AC12); corpus `mode2_fragment` / `mode3_inject_islands`
    fire against the synthetic reference (AC13); corpus `mode6_crop_at_border`
    fires `bounds` against verse-v1 (AC14); item-042 goldens byte-identical via the
    existing `check_case_golden` path (AC15).
  - Config/determinism: `load_config(default_config_path()) == default_config()`,
    `schema_version`, `config_hash` snapshot (AC16); two evaluate/`run_rules` calls
    equal + deep non-mutation (AC17).
- **Adversarial / edge cases (beyond the ACs):**
  - **Covered level missing exactly one of the two fragmentation stats** — the
    present stat uses the reference tolerance, the absent one falls back to its
    hand-set constant (per-metric fallback; complements AC9/AC11).
  - **`source: reference` with `record["reference"]` absent** — both rules degrade
    to hand-set (no crash), matching item 048 AC9; this is the golden-harness path.
  - **Unknown `source` string** and **percentile absent from
    `reference.percentiles`** — `ValueError` from `fragmentation.evaluate`
    (mirrors bounds AC10/AC11), raised before per-label processing.
  - **A real verse-v1 label at its exact `p1` / `p99` bound** — inclusive band:
    does not fire (parity with bounds' inclusive semantics).
  - **`--no-reference` with `reference.enabled: true` in a YAML config** — the flag
    wins (forces off), confirming the escape hatch overrides config.
  - **Determinism of the CLI default run** — two runs produce byte-identical
    `segqc_report.json` (reference attachment is deterministic).

## Dependencies

- **Item 048 (✅ merged) — extended.** The `bounds` reference-mode switch,
  `reference_bounds_for_level`, and per-metric fallback; this item flips its
  code-side `source` default to `reference` and re-asserts its fallback (AC2, AC10).
- **Item 049 (✅ merged) — extended.** `run_qc_with_reference` (which already
  attaches `record["reference"]`) and the `--reference` / `--reference-artifact`
  CLI wiring + `reference.enabled` config resolution; this item flips the
  enabled/artifact defaults and adds `--no-reference` (AC4). Deliberately supersedes
  its AC6 "OFF by default".
- **Item 028 (✅ merged) — MODIFIED.** The `fragmentation` rule; this item adds its
  reference-derived per-level path and preserves the hand-set path as fallback
  (AC3, AC5–AC9, AC11, AC17).
- **Item 027 (✅ merged) — consumed.** `DEFAULT_BOUNDS` / `_METRICS` / group
  resolution — the hand-set fallback target for uncovered levels.
- **Items 043 / 045 (✅ merged) — consumed.** `ReferenceDistribution` +
  `load_artifact` and the committed artifacts; this item adds the production
  accessor for `reference_verse_v1.json` and keeps `bundled_default_reference`
  (synthetic) as the Plane-1 baseline (AC1, AC12).
- **Items 040 / 041 / 042 (✅ merged) — regression target.** The Stage-5 synthetic
  corpus + manifest, `synth.regression` loader, and the golden harness; this item
  asserts corpus verdicts hold (AC13, AC14) and the goldens stay byte-identical
  (AC15).
- **Item 089 (✅ merged) — sequenced before.** FOV-aware `coverage` / `border`
  semantics must be fixed before thresholds are re-grounded, so a partial FOV is a
  non-defect and no mis-specified rule is laundered into a calibrated constant.
- **Item 057 (✅ merged) — sensitivity reference.** Its 5/8-pipeline-detectable-
  modes-at-1.0 baseline is the bar item 091's guard enforces; this item must not
  regress the synthetic corpus fragmentation/bounds detections (AC13, AC14).
- **Downstream:** **091** runs the calibration grid-search fitted on the training
  subset, measures held-out real FPR against this item's shipped default, adds the
  executable anti-gaming sensitivity guard, and closes G3.

## Decisions & Trade-offs

To be updated during implementation.
