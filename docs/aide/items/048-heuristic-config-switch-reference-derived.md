# Item 048 — Heuristic config switch: reference-derived vs hand-set bounds

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 048
> **Objectives:** G3 (distinguish failure from legitimate variation), G2 (bounds
> failure-mode detection, now reference-grounded)
> **Suggested branch:** `aide/048-heuristic-config-switch-reference-derived`

---

## Description

Give the level-aware bounds rule (item 027,
[`src/segqc/heuristics/bounds.py`](../../../src/segqc/heuristics/bounds.py)) a
**config switch** that selects where its per-metric `min`/`max` thresholds come
from:

- **`hand-set`** (default) — today's behaviour, exactly: coarse per-*group*
  (cervical / thoracic / lumbar) `DEFAULT_BOUNDS`, overridable per key via
  `rules.bounds.params.<group>`.
- **`reference`** — per-*level* bounds derived from a loaded item-045
  `ReferenceDistribution`: for each tracked geometry feature, the effective
  `min`/`max` are the level's stored **percentiles** (a configurable pair,
  default `p1`/`p99`), with **graceful fallback to the hand-set group bounds for
  any level the reference does not cover** (and for any tracked metric the
  reference lacks for a covered level).

The reference model is the one item 045 already ships and loads
(`segqc.reference.schema.ReferenceDistribution`, tracked features
`physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`,
`spline_offset_mm`; the bounds rule uses the first four — the same four in
`bounds._METRICS`). The percentile grid `p1/p5/p25/p50/p75/p95/p99` is the item
043/045 default.

**How the rule reaches the reference.** Following the item-047 precedent exactly
(the `reference_delta` rule reads a per-case block the pipeline attaches, and
"wiring … into the record fed to `run_rules` is item 049's remit"), the bounds
rule reads the loaded reference from the per-case record under a new key
`record["reference"]`. Item 049 attaches it during `segqc run`; until then (and
in every existing test/pipeline path) the key is **absent**, so `reference`
mode degrades to hand-set and existing output is byte-unchanged. This item makes
the bounds rule *ready to consume* a reference and provides the pure derivation
helper; it is tested by constructing/loading a `ReferenceDistribution` and
attaching it to a hand-built record directly.

**In scope:** the `source` switch + reference-percentile params in
`rules.bounds.params`; a pure `reference` → per-level bounds-dict derivation
helper in `bounds.py`; the reference-mode evaluation path with graceful
per-level (and per-metric) fallback; commented documentation of the switch in
`default_config.yaml`.

**Out of scope (do NOT):** wiring `record["reference"]` into `segqc run` /
`extract_feature_record` (item 049); loading the artifact from disk inside the
rule (the rule performs **no** file I/O — it reads the already-loaded object);
changing the hand-set defaults, `DEFAULT_BOUNDS`, `SUPPORTED_SCHEMA_VERSION`, or
the committed `reference_default.json`; adding **active** keys to
`default_config.yaml` (see AC7 — documentation is comments only, to keep
`config_hash` and the Stage 5 goldens byte-stable).

## Acceptance Criteria

_Each criterion is atomic and directly testable; test module
`tests/test_heuristics_bounds_source.py`._

- [ ] **AC1: hand-set is the default and is byte-unchanged.** With no `source`
  param (or `source: hand-set`), `BoundsRule.evaluate` returns findings
  identical (same count, order, reasons, severities, labels) to the item-027
  behaviour on the same record — including when `record["reference"]` is present
  but `source` is unset/`hand-set` (the reference is ignored in hand-set mode).

- [ ] **AC2: reference mode fires on an out-of-reference value.** With
  `source: reference` and a `ReferenceDistribution` attached at
  `record["reference"]` covering the label's level, a metric value **strictly
  below** the level's `p{lower_pct}` (or **strictly above** `p{upper_pct}`)
  produces exactly one bounds `Finding` for that (label, metric).

- [ ] **AC3: reference mode passes an in-reference value.** With
  `source: reference` and a covering reference, a metric value within the
  inclusive `[p{lower_pct}, p{upper_pct}]` band (including exactly equal to
  either bound) produces **no** finding for that (label, metric).

- [ ] **AC4: effective bounds come from the configured percentiles.** In
  reference mode the `min`/`max` compared against, and quoted in the finding
  reason, equal the level's stored `p{lower_pct}`/`p{upper_pct}` values from the
  artifact — and change accordingly when `reference_lower_pct`/
  `reference_upper_pct` are set to a different stored pair (e.g. `p5`/`p95`).

- [ ] **AC5: per-level fallback to hand-set for uncovered levels.** In reference
  mode, a label whose `level_name` is **absent** from the reference (or absent
  for the requested `reference_stratum`) is evaluated against the hand-set group
  bounds instead (fires iff it would fire under hand-set), never crashing.

- [ ] **AC6: reference-mode reasons are explainable and distinct.** A
  reference-mode finding's `reason` names the offending label, its level, the
  measured value, and the reference bound with its percentile (e.g. "below
  reference minimum … (p1) for level L3") — distinguishable from the hand-set
  reason ("… for cervical group").

- [ ] **AC7: the switch is documented in comments only; parsed config is
  unchanged.** `default_config.yaml` documents `source`/`reference_lower_pct`/
  `reference_upper_pct`/`reference_stratum` under `rules.bounds.params` as
  **commented** lines; `load_config(default_config_path())` still equals
  `default_config()` (unchanged `rules` dict), so `config_hash` and the Stage 5
  golden snapshots are unaffected.

- [ ] **AC8: the switch round-trips through config load.** A YAML config with
  `rules.bounds.params.source: reference` (and a percentile pair) loads via
  `load_config` and `config.rule_param("bounds", "source", …)` returns
  `"reference"` (and the configured percentiles), with `schema_version` still
  `"0.1"`.

- [ ] **AC9: graceful degradation when no reference is attached.** With
  `source: reference` but `record["reference"]` **absent**, `evaluate` behaves
  exactly as hand-set (no crash, no error) — matching item 047's "silent where
  there is no reference".

- [ ] **AC10: unrecognised `source` raises `ValueError`.** A `source` value
  other than `hand-set`/`reference` raises `ValueError` from `evaluate` (mirrors
  the existing `severity` validation), before any per-label processing.

- [ ] **AC11: unknown percentile raises `ValueError`.** In reference mode, a
  `reference_lower_pct`/`reference_upper_pct` not present in
  `reference.percentiles` raises `ValueError` (mirrors
  `delta.compute_reference_delta`), naming the offending percentile.

- [ ] **AC12: pure derivation helper.** The public helper
  `reference_bounds_for_level(reference, level_name, *, lower_pct, upper_pct,
  stratum)` returns the bounds-dict (keys matching `bounds._METRICS`:
  `min_volume_mm3`/`max_volume_mm3`/`min_extent_{x,y,z}_mm`/
  `max_extent_{x,y,z}_mm`) for a covered level, or `None` for an uncovered
  level/stratum; it never mutates `reference` and reads no file/clock.

- [ ] **AC13: determinism and non-mutation.** Two `evaluate` calls in reference
  mode on the same `(record, config)` return equal finding lists in the same
  order (ascending integer label, then the fixed `_METRICS` order); neither
  `record`, `record["reference"]`, nor `config` is mutated.

## Assumptions  <!-- MANDATORY -->

- **Record-attachment interface (pins item 049).** The rule reads the loaded
  reference from `record["reference"]` as a
  `segqc.reference.schema.ReferenceDistribution` instance (accessed by attribute
  — `.levels[level_name][stratum].feature_stats[feature].percentiles["pN"]`,
  `.percentiles`, `.features`). Item 049 must attach it under exactly this key
  during `segqc run`. If 049 chooses a different key/shape, the builder/validator
  hand back. Until 049 lands the key is absent, so nothing changes (AC9).
- **`config.py` needs no code change.** `source`, `reference_lower_pct`,
  `reference_upper_pct`, `reference_stratum` live in the free-form
  `rules.bounds.params` dict, already read generically by
  `HeuristicConfig.rule_param`. No new dataclass field and **no**
  `SUPPORTED_SCHEMA_VERSION` bump — existing configs stay valid and the default
  stays behaviourally identical (queue one-liner mentions `config.py`, but the
  generic param mechanism already supports the switch).
- **Documentation is comments-only in `default_config.yaml`.** Adding an
  *active* `source` key would change `config.rules`, hence `config_hash`
  (item 045 provenance) and potentially the Stage 5 goldens; committing the
  switch as commented YAML keeps every downstream hash/snapshot byte-stable
  while still documenting it (AC7). The code default `hand-set` is supplied via
  `rule_param(..., default="hand-set")`.
- **Percentile-pair default `(1, 99)` and stratum default `"all"`** — matching
  `delta.DEFAULT_LOWER_PCT`/`DEFAULT_UPPER_PCT` and `schema.ALL_STRATUM`, the
  established Stage-6 conventions.
- **Reference-band comparison is inclusive** (a value equal to `p{lower_pct}` or
  `p{upper_pct}` does **not** fire), matching item 027's inclusive hand-set
  bounds so the two modes share firing semantics.
- **Per-metric fallback within a covered level.** If a covered level's reference
  lacks a tracked metric's stats, that single metric falls back to the hand-set
  group bound (when the level has a group), rather than being skipped silently —
  keeping coverage no worse than hand-set.
- **The four bounds metrics only.** Reference mode derives bounds for exactly the
  four features in `_METRICS` (volume + three extents); `spline_offset_mm` is not
  a bounds metric and is ignored here.

## Implementation Steps

Code path in `src/segqc/heuristics/bounds.py` (+ documentation in
`src/segqc/default_config.yaml`):

1. **Feature ↔ bounds-key map.** Add a module-level constant mapping each of the
   four bounds features to its `(min_key, max_key)` (derived from / kept in step
   with `_METRICS`): `physical_volume_mm3 → (min_volume_mm3, max_volume_mm3)`,
   `extent_x_mm → (min_extent_x_mm, max_extent_x_mm)`, likewise y and z.
2. **Pure derivation helper** `reference_bounds_for_level(reference, level_name,
   *, lower_pct, upper_pct, stratum="all")`: validate `lower_pct`/`upper_pct`
   are in `reference.percentiles` (else `ValueError`); look up
   `reference.levels.get(level_name)` then `.get(stratum)` (return `None` if
   either absent); for each of the four features present in that
   `LevelDistribution.feature_stats`, read `percentiles[f"p{lower_pct}"]` /
   `percentiles[f"p{upper_pct}"]` into the bounds-dict `min_*`/`max_*` keys;
   return the dict (possibly partial). Attribute access only — no import of
   `segqc.reference` at runtime (type-only import under `TYPE_CHECKING`).
   Add to `__all__`.
3. **Read the switch in `evaluate`.** Read
   `source = config.rule_param("bounds", "source", default="hand-set")`; if not
   in `{"hand-set", "reference"}` raise `ValueError` (mirror
   `_severity_from_param`), before the per-label loop. When `reference`, read
   `reference_lower_pct` (default 1), `reference_upper_pct` (default 99),
   `reference_stratum` (default `"all"`), and `reference = record.get("reference")`.
4. **Per-label bound resolution.** Keep today's hand-set path untouched. When
   `source == "reference"` and a reference is attached, per label: call
   `reference_bounds_for_level(...)`; merge it *over* the resolved hand-set group
   bounds (`{**group_defaults, **config_group, **reference_bounds}`) so covered
   metrics use reference values and any metric/level the reference lacks falls
   back to hand-set (per-metric/per-level fallback, AC5/AC12). A label whose
   level has no group and no reference coverage is skipped, as today. When no
   reference is attached, use the hand-set path unchanged (AC9).
5. **Reason text.** When a fired bound came from the reference, phrase the reason
   as "… is below reference minimum {lo} (p{lower_pct}) for level {level}" /
   "… exceeds reference maximum {hi} (p{upper_pct}) for level {level}" (AC6);
   otherwise keep the existing "… for {group} group" text. Preserve the existing
   per-`(label, metric)` finding granularity and `_METRICS` ordering.
6. **Document in `default_config.yaml`.** Under `rules.bounds.params`, add a
   **commented** block describing `source: hand-set | reference` (default
   `hand-set`), `reference_lower_pct: 1`, `reference_upper_pct: 99`,
   `reference_stratum: all`, and the fallback behaviour. No active keys.
7. **Non-mutation.** Build merged bounds into new dicts; never write back into
   `record`, `record["reference"]`, or `config`.

## Testing Strategy

New module `tests/test_heuristics_bounds_source.py` (register/restore the rule
registry per the existing bounds-test convention if instantiating the rule
directly). One focused test per AC plus edge cases. Build a small
`ReferenceDistribution` via the item-043/045 model (either construct
`schema.ReferenceDistribution` directly with hand-chosen percentiles for one or
two levels, or load `bundled_default_reference()` and target its lumbar levels)
and hand-build records with `per_label[str(label)] = {"label", "level_name",
"geometry": {...}}`.

- **AC1** — same record, hand-set vs item-027 expectation: identical findings;
  also assert a present-but-ignored `record["reference"]` in hand-set mode
  changes nothing.
- **AC2/AC3/AC4** — one level with known percentiles; values just below
  `p{lower}`, just above `p{upper}`, exactly on each bound, and mid-band; repeat
  with `reference_lower_pct/upper_pct` = 5/95 to prove the bounds track config.
- **AC5** — a label at a level not in the reference falls back to hand-set (craft
  it to fire, and separately to pass, under hand-set).
- **AC6** — assert the reference-mode reason substring (percentile + "level") and
  that it differs from the hand-set "group" reason.
- **AC7** — `load_config(default_config_path()) == default_config()` (or their
  `rules` dicts equal); optionally assert `config_hash` unchanged vs a snapshot.
- **AC8** — round-trip a temp YAML with `source: reference` + percentiles.
- **AC9** — `source: reference`, no `record["reference"]`: equals hand-set.
- **AC10/AC11** — `pytest.raises(ValueError)` for a bad `source` and for a
  percentile absent from `reference.percentiles`.
- **AC12** — `reference_bounds_for_level` returns the expected dict for a covered
  level, `None` for an uncovered level and an uncovered stratum; assert the
  input `ReferenceDistribution` is not mutated.
- **AC13** — call `evaluate` twice, assert equal outputs; deep-compare `record`
  and `config` before/after to prove non-mutation.
- **Edge cases** — covered level missing one tracked metric (per-metric
  fallback); empty `per_label`; a label with an unbounded/unknown level in
  reference mode (skipped, no crash); `std`/degenerate percentiles do not apply
  here (bounds compares raw percentile values, not z-scores).

## Dependencies

- **Item 045 (✅)** — `ReferenceDistribution` model + `load_artifact` /
  `bundled_default_reference`: the loaded reference this rule consumes, and the
  percentile grid the bounds derive from.
- **Item 043 (✅)** — `segqc.reference.schema` (`ReferenceDistribution`,
  `LevelDistribution`, `FeatureStats`, `ALL_STRATUM`, `DEFAULT_PERCENTILES`): the
  data model the derivation reads.
- **Item 027 (✅)** — `BoundsRule` / `DEFAULT_BOUNDS` / `_METRICS`: the rule and
  hand-set defaults being extended (and the fallback target).
- **Item 035 (✅)** — `default_config.yaml` + `load_config`: where the switch is
  documented and round-trips.
- **Downstream (not a dependency): Item 049** consumes this by attaching
  `record["reference"]` in `segqc run` and asserting the G3 acceptance suite.

## Decisions & Trade-offs

To be updated during implementation.
