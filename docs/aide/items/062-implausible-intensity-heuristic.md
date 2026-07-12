# Item 062 — Implausible-intensity heuristic (intensity-based rule)

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 062 *(the heuristic half of Stage-8 deliverable 2; consumes 059's/061's already-computed `image_features` block; feeds 065's `segqc run` wiring + Stage-8 acceptance suite)*
> **Objectives:** G2 (adds the stage's required **≥1 intensity-based heuristic** — a config-driven, explainable rule that flags a vertebra whose intensity is anatomically implausible for bone, the first QC judgement grounded in scan voxel intensities), G8 (a new failure mode added along the documented Stage-4 rule-extension path), and G7 (deterministic, config-driven, regression-testable firing **and** non-firing). Realises the roadmap Stage-8 deliverable "Feature fusion into the report + ≥1 intensity-based heuristic (e.g. implausible-intensity flag)" and the vision's §5.2 image-based feature family feeding an explainable rule.
> **Suggested branch:** `aide/062-implausible-intensity-heuristic-intensity-based`

---

## Description

Add the **≥1 intensity-based heuristic** Stage 8 requires (deliverable 2, the
heuristic half): a **config-driven rule** in the Stage 4 heuristic engine that
flags a labelled region whose **first-order intensity statistics are implausible
for a vertebra**. It is a peer of the existing Stage 4 rules (`bounds`,
`fragmentation`, `coverage`, `sequence`, `border`, `overlap`, `mislabel`,
`reference_delta`): it subclasses `segqc.heuristics.rule.Rule`, is registered via
`@register_rule` with `rule_id = "intensity"`, and implements the standard
`evaluate(record, config) -> list[Finding]` contract. Its findings flow through
the existing runner (`segqc.heuristics.run_rules`, item 026) and verdict
aggregation (`segqc.aggregate.build_case_result` / `aggregate_verdict`, item 034)
with **no change** to either.

Deliver a new module `src/segqc/heuristics/intensity.py`, registered by a one-line
import in `src/segqc/heuristics/__init__.py`, mirroring items 027–033/047.

### How the rule reads the intensity features — the record seam

Every Stage 4 rule receives only `(record, config)`. Item 061 assembles the
per-label first-order intensity statistics (item 059's `LabelIntensity`) into a
top-level **`image_features` block** — a report sibling of `features` /
`findings` / `reference_delta`, produced by
`segqc.feature_report.build_image_features_block`. This rule therefore reads that
same dict shape from **`record.get("image_features")`**, exactly as
`reference_delta` (item 047) reads `record.get("reference_delta")`. It
**recomputes nothing**: item 059 already computed every statistic, item 061
already serialised the block; this rule only *thresholds* the already-computed
numbers. It imports nothing from `segqc.features.intensity`, `segqc.feature_report`,
or `segqc.synth`, samples no voxel, and is stateless / I/O-free like its siblings.

Item **065** owns the `segqc run` wiring that computes the block and injects it
into the record fed to `run_rules` (the exact analogue of item 049 for
`reference_delta`). Until 065 lands, `record.get("image_features")` is absent by
default, so this rule is silently a no-op and existing pipeline output (including
the item-042 golden snapshots) is byte-identical at 062 merge.

### The `image_features` block shape consumed (item 061 — read, never written)

```json
{
  "image_features_version": "1.0",
  "available": true,
  "radiomics_available": false,
  "backend": "builtin",
  "per_label": {
    "22": {
      "label": 22,
      "first_order": {
        "voxel_count": 812, "n_nonfinite_excluded": 0,
        "mean": 251.4, "median": 232.0, "std": 143.7,
        "min": -12.0, "max": 903.0,
        "p05": 41.0, "p25": 168.0, "p50": 232.0, "p75": 322.0, "p95": 631.0,
        "range": 915.0, "iqr": 154.0, "entropy": 4.31
      },
      "extended": {}
    }
  }
}
```

When intensity was attempted but unavailable (no scan / no backend), item 061
emits the explicit sentinel `{"available": false, ..., "per_label": {}}`; the rule
treats that (and an absent / non-mapping block) as silence. A per-label
`first_order` statistic may be `None` (item 059's sentinel for an absent/empty
label or an all-non-finite region) — the rule skips a condition whose input
statistic is `None`.

### What the rule fires on

For each label in the block's `per_label`, the rule applies up to three
**independently config-toggleable** firing conditions over that label's
`first_order` statistics, each emitting one `Finding` (`rule_id="intensity"`,
config-driven severity, offending label, explainable reason):

1. **Implausibly-low median (soft-tissue / air mislabel).** Fires when
   `median is not None and median < min_plausible_hu` (default `100.0`). A region
   whose central intensity is soft-tissue-/air-low is not bone.
2. **Implausibly-high median (metal / implant / bright artifact).** Fires when
   `median is not None and median > max_plausible_hu` (default `2000.0`). A region
   in the metal-artifact HU range is not native bone.
3. **Degenerate / uniform distribution.** Fires when
   `std is not None and std <= max_degenerate_std` (default `1.0`, i.e. std ≈ 0).
   A suspiciously flat (constant-fill) intensity distribution under a mask is
   implausible for real cancellous+cortical bone.

Conditions 1 and 2 are the two ends of one **level-agnostic bone-plausibility
band** `(min_plausible_hu, max_plausible_hu)`; band membership is judged on the
robust **median**. The band is inclusive: a median exactly equal to a bound does
**not** fire (mirrors `bounds`' inclusive `[min, max]`); only strictly `< min` or
`> max` fires. Condition 3 is inclusive (`std <= max_degenerate_std`) so a truly
constant region (`std == 0.0`) always fires. A single fired condition is enough to
flag the vertebra.

### Scope boundary — what this item is **not**

- **Not the intensity feature extraction.** The per-label first-order statistics
  (mean/median/std/percentiles/entropy) are **item 059** (merged); their report
  fusion into the `image_features` block is **item 061** (merged). This item adds
  no statistic and no serialiser — it thresholds the numbers 059/061 produced.
- **Not the `segqc run` / pipeline wiring.** Loading the scan, computing intensity
  features in the pipeline, and **injecting the `image_features` block into the
  record** passed to `run_rules` (plus the Stage-8 end-to-end acceptance suite) are
  **item 065**. This item defines the record seam the rule reads and fires
  correctly when the block is present, but does **not** change `segqc.pipeline` or
  `segqc.cli`.
- **Not the reference-grounded intensity rule.** The level-aware
  delta-to-reference intensity rule (intensity vs a VerSe-derived per-level
  distribution) is **item 064**, on the extended reference artifact (item 063).
  This item is the *level-agnostic, hand-set-band* rule only.
- **Not a radiomics consumer.** The optional PyRadiomics `extended` features
  (item 060) are ignored here; the rule reads only `first_order`.
- **Not a `default_config.yaml` edit.** Mirroring item 047, to avoid regressing
  `tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids` (which
  asserts the bundled YAML declares *exactly* the seven pre-existing rule ids) and
  the item-042 golden snapshots, this item leaves `src/segqc/default_config.yaml`
  untouched. Thresholds are read from `config.rule_param("intensity", …,
  default=…)` with code-side defaults, and the rule is enabled-by-default (an
  absent config section ⇒ `rule_enabled` returns `True`). Documenting the
  `intensity` section in the bundled YAML and updating the item-035 id-set is
  deferred to item **065** (the run-wiring item, which owns the pipeline and is
  scoped to touch config with the test-writer).
- **Not a report-schema or serialiser change.** Item 061 already added the
  `image_features` block + schema property. This rule's findings serialise through
  the **existing** Stage 4 findings machinery (item 035); no `report.py` /
  `report_schema_v0.json` change is needed.

---

## Public interface (the contract 065 builds on)

New module `src/segqc/heuristics/intensity.py`, registered in
`src/segqc/heuristics/__init__.py`. Private helpers are the builder's choice; the
surface below is the contract.

```python
# rule_id string (registry key, embedded in every Finding this rule emits)
#   "intensity"

# Config defaults (read via config.rule_param("intensity", key, default)):
DEFAULT_MIN_PLAUSIBLE_HU: float = 100.0      # median < this fires "too low"
DEFAULT_MAX_PLAUSIBLE_HU: float = 2000.0     # median > this fires "too high"
DEFAULT_MAX_DEGENERATE_STD: float = 1.0      # std <= this fires "degenerate/uniform"
# flag_low / flag_high / flag_degenerate: bool, default True each
# severity: str, default "flagged-for-review"

# Stable start-of-reason markers (tests assert on these prefixes):
_LOW_TAG        = "Implausible intensity (too low):"
_HIGH_TAG       = "Implausible intensity (too high):"
_DEGENERATE_TAG = "Implausible intensity (degenerate/uniform):"

@register_rule
class IntensityRule(Rule):
    rule_id = "intensity"
    def evaluate(self, record, config) -> list[Finding]:
        """Read record["image_features"] (the build_image_features_block shape,
        item 061) and emit a Finding per fired condition. Returns [] when the
        block is absent/non-mapping, available is False, per_label is empty, or
        every label is intensity-plausible. Pure; never mutates record; raises
        ValueError only for an unrecognised `severity` config string."""
```

**Finding emission order (deterministic).** Labels ascending by integer `label`;
within a label, in fixed condition order — (1) low, then (2) high, then (3)
degenerate. Each finding is `Finding(rule_id="intensity", severity=<config>,
reason=<tagged, human-readable>, labels=frozenset({label}))`.

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. Except the corpus ACs
(AC21–AC24), tests hand-build a minimal `record` carrying a top-level
`image_features` block (the item-061 `build_image_features_block` shape) plus a
`HeuristicConfig` (via `segqc.config.default_config()` or a crafted
`rules.intensity.params` mapping), so every firing decision is hand-checkable.
"Intensity-plausible" means a label whose `median` is inside
`[min_plausible_hu, max_plausible_hu]` **and** whose `std > max_degenerate_std`._

- [ ] **AC1: the rule is registered and discoverable.**
      `segqc.heuristics.get_rule("intensity")` returns a `Rule` instance whose
      `rule_id == "intensity"`, and `iter_rules()` yields exactly one rule with
      that id.

- [ ] **AC2: an intensity-plausible vertebra produces no finding.** For a record
      whose `image_features.per_label` holds one label with `median` inside the
      band and `std > max_degenerate_std`, `evaluate` returns `[]`.

- [ ] **AC3: an implausibly-low median fires a low finding.** For a label whose
      `first_order.median < min_plausible_hu` (with `flag_low` at its default
      `True`, `std > max_degenerate_std` isolating the condition), `evaluate`
      returns exactly one `Finding` whose `rule_id == "intensity"`,
      `labels == frozenset({label})`, and whose `reason` starts with
      `"Implausible intensity (too low):"`.

- [ ] **AC4: an implausibly-high median fires a high finding.** For a label whose
      `first_order.median > max_plausible_hu` (with `std > max_degenerate_std`
      isolating the condition), `evaluate` returns exactly one `Finding` for that
      label whose `reason` starts with `"Implausible intensity (too high):"`.

- [ ] **AC5: a degenerate (std ≈ 0) distribution fires a degenerate finding.** For
      a label whose `first_order.std <= max_degenerate_std` but whose `median` is
      inside the band (isolating the condition), `evaluate` returns exactly one
      `Finding` for that label whose `reason` starts with
      `"Implausible intensity (degenerate/uniform):"`.

- [ ] **AC6: the low-band threshold is read from config.** A label whose `median`
      is (say) `50.0` fires the low condition at the default `min_plausible_hu`;
      the same record with `rules.intensity.params.min_plausible_hu = 0.0`
      produces **no** low finding, while `min_plausible_hu = 200.0` fires — the
      threshold comes from `config.rule_param`, not a hard-coded constant.

- [ ] **AC7: the high-band threshold is read from config.** A label whose `median`
      is (say) `3000.0` fires the high condition at the default; with
      `rules.intensity.params.max_plausible_hu = 5000.0` it does not, while
      `= 1000.0` it does.

- [ ] **AC8: the degenerate-std threshold is read from config.** A label whose
      `std` is (say) `0.0` fires the degenerate condition at the default; with
      `rules.intensity.params.max_degenerate_std = -1.0` (nothing can be ≤ it) it
      does not, while `= 5.0` a label with `std == 3.0` fires.

- [ ] **AC9: `flag_low: false` disables the low condition.** With
      `rules.intensity.params.flag_low = False`, a label whose only anomaly is a
      below-band median produces **no** finding, while the high and degenerate
      conditions (left enabled) still fire on labels that trigger them.

- [ ] **AC10: `flag_high: false` disables the high condition.** With
      `flag_high = False`, a label whose only anomaly is an above-band median
      produces no finding, while the other two conditions still fire when
      triggered.

- [ ] **AC11: `flag_degenerate: false` disables the degenerate condition.** With
      `flag_degenerate = False`, a label whose only anomaly is `std ≈ 0` produces
      no finding, while the other two conditions still fire when triggered.

- [ ] **AC12: severity is configurable.** With
      `rules.intensity.params.severity = "fail"`, every emitted `Finding` has
      `severity == segqc.verdict.Severity.FAIL`; with the default it is
      `Severity.FLAG` (`"flagged-for-review"`).

- [ ] **AC13: an unrecognised severity string raises `ValueError`.** `evaluate`
      with `rules.intensity.params.severity = "not-a-severity"` raises `ValueError`
      (before/independently of emitting findings), mirroring the other rules'
      severity-validation contract.

- [ ] **AC14: an absent / non-mapping `image_features` block is silent, not an
      error.** For a record with **no** `image_features` key (the current pipeline
      default), and for a record whose `image_features` is `None` / a non-mapping,
      `evaluate` returns `[]` without raising.

- [ ] **AC15: an unavailable block is silent.** For a record whose
      `image_features` is the item-061 unavailable sentinel
      (`{"available": false, ..., "per_label": {}}`), `evaluate` returns `[]`.

- [ ] **AC16: `None`-valued statistics are skipped, not crashed.** For a label
      whose `first_order` carries `median: null` and `std: null` (item 059's
      absent/empty-label sentinel, `voxel_count == 0`), `evaluate` returns no
      finding for that label and does not raise; a plausibility-violating,
      non-`None` label in the same block still fires.

- [ ] **AC17: the reason is explainable — measured value vs threshold/band.** A
      low finding's `reason` (a non-empty, non-whitespace string) names the
      offending integer `label`, the measured `median`, and the crossed
      `min_plausible_hu` (and, for context, the plausibility band); analogously the
      high and degenerate reasons name their measured statistic and threshold —
      satisfying the queue's "human-readable reason and the offending label(s)."

- [ ] **AC18: findings flow through `run_rules` and verdict aggregation.** For a
      firing record, `segqc.heuristics.run_rules(record, config)` includes the
      rule's `Finding`(s), and
      `segqc.aggregate.build_case_result(run_rules(record, config), config).verdict`
      resolves `overall` to at least the finding severity (e.g. `Severity.FLAG`
      under defaults) with the offending integer label present in the verdict's
      per-label reasons — the rule composes with the existing engine unchanged.

- [ ] **AC19: computation is deterministic and non-mutating.** Two `evaluate`
      calls on the same `record` + `config` return **equal** finding lists (equal
      `Finding`s in the same order), and a deep before/after comparison of `record`
      shows it is unchanged (the `image_features` block is read, never written).

- [ ] **AC20: findings are emitted in a deterministic order.** For a record whose
      block fires across two labels (e.g. label 20 too-low, label 23 too-high and
      degenerate), the returned findings appear ascending by integer label and,
      within a label, in the fixed condition order (low → high → degenerate) —
      independent of `per_label` dict insertion order.

- [ ] **AC21: the clean HU-painted corpus case does not fire.** Building the
      `image_features` block from item 058's committed `clean_hu` case (load
      scan+seg via `segqc.io`/nibabel, compute with
      `segqc.features.intensity.compute_intensity_features`, assemble with
      `segqc.feature_report.build_image_features_block`) and evaluating under
      `default_config()` yields **no** `intensity` finding on any label.

- [ ] **AC22: the metal implausible variant fires "too high" on the target label.**
      For item 058's committed `implausible_metal` case (L3 filled to metal HU,
      `target_label == 22`), the rule emits an `intensity` finding tagged
      `"Implausible intensity (too high):"` whose `labels` include `22`.

- [ ] **AC23: the soft-tissue implausible variant fires "too low" on the target
      label.** For item 058's committed `implausible_soft_tissue` case, the rule
      emits an `intensity` finding tagged `"Implausible intensity (too low):"`
      whose `labels` include `22`.

- [ ] **AC24: the degenerate-uniform variant fires the degenerate condition on the
      target label.** For item 058's committed `degenerate_uniform` case (L3 filled
      with a single constant HU, `std == 0`), the rule emits an `intensity` finding
      tagged `"Implausible intensity (degenerate/uniform):"` whose `labels`
      include `22`.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete rule is recorded here for audit; several
**pin an interface** item 065 must honour (hand back if reality diverges).

- **The rule reads intensity features from `record["image_features"]` (the top-level
  block produced by item 061's `build_image_features_block`).** The fixed
  `Rule.evaluate(record, config)` signature is the only channel a rule has, and
  item 061 produced the intensity features as a *top-level* report block
  (`image_features`, sibling of `features`/`findings`/`reference_delta`), keyed
  `per_label[str(label)]` → `{"label", "first_order": {…}, "extended": {…}}`. The
  rule reads `record.get("image_features")` and its `per_label[*]["first_order"]`
  `median`/`std`. **Pinned for 065:** the run-wiring item must inject
  `record["image_features"] = build_image_features_block(compute_intensity_features(...))`
  into the record fed to `run_rules` (the analogue of item 049 for
  `reference_delta`). If 065 nests the block elsewhere or changes the
  `per_label → first_order → {median, std}` shape, hand back — that is this rule's
  read path. Reading (not recomputing) keeps the rule stateless and I/O-free like
  every sibling, and silent-by-default until 065 wires the block (so no existing
  pipeline/golden output changes at 062 merge).

- **`rule_id = "intensity"`, module `src/segqc/heuristics/intensity.py`.** Matches
  the queue's suggested name; distinct from the eight existing ids. Registered via
  the standard `@register_rule` + an import line in `segqc/heuristics/__init__.py`,
  exactly as items 027–033/047 register their rules.

- **Three independent, config-toggleable firing conditions — implausibly-low
  median, implausibly-high median, degenerate/uniform std.** These are the queue's
  enumerated signals ("median HU far outside a documented bone-plausible band, or
  metal-artifact-range HU, or a suspiciously degenerate/uniform intensity
  distribution (std ≈ 0)"). **"Metal-artifact-range HU" is folded into the
  high-median condition** (a single upper band bound), not a fourth condition: a
  metal-range median is exactly an above-band median, so a separate metal lever
  would double-fire the same signal (mirrors item 047 folding percentile into
  out-of-range). Each condition has its own boolean toggle (`flag_low` /
  `flag_high` / `flag_degenerate`, default `True`) and threshold
  (`min_plausible_hu` / `max_plausible_hu` / `max_degenerate_std`), read via
  `config.rule_param`.

- **Judgement is on the robust `median`, not `mean`.** The queue names "median HU"
  first; median is robust to the cortical-rim outliers in a vertebra mask
  (item 059 exposes both). A configurable `statistic` switch is out of scope
  (documented here); the rule reads `first_order.median`. Degeneracy is judged on
  `first_order.std` (item 059's population std, `ddof=0`), which is exactly `0.0`
  for a constant-fill region (item 058's `degenerate_uniform` variant).

- **The plausibility band `(100.0, 2000.0)` HU and `max_degenerate_std = 1.0` are
  documented, conservative placeholders — chosen independently of the generator's
  HU constants.** Item 058's `segqc/synth/intensity.py` explicitly states its HU
  fills are *generator ground truth, not QC thresholds*, and defers the QC
  thresholds to this item. `100.0` sits above soft-tissue/fat/air (item 058's
  `soft_tissue` fill ≈ 40 HU, `degenerate_uniform` fill = 0 HU) and below the
  clean cancellous/cortical median (item 058 paints cancellous ≈ 200 HU, cortical
  ≈ 600 HU, so the clean per-label median lands well inside the band). `2000.0`
  sits above dense native cortical bone (~1900 HU) and below metal-implant HU
  (item 058's `metal` fill ≈ 3000 HU). `max_degenerate_std = 1.0` (≈ 0) separates a
  constant fill (`std == 0`) from the clean painted regions (`std` in the tens–
  hundreds). Like `bounds`' shipped defaults, these are levers the tests move
  (AC6–AC8), not validated clinical cut-points; Stage-7-style calibration (and the
  reference-grounded item 064) refine them.

- **Firing boundaries: band inclusive, degenerate inclusive.** `median` strictly
  `< min_plausible_hu` or strictly `> max_plausible_hu` fires (a median exactly on
  a bound passes — mirrors `bounds`' inclusive `[min, max]`). `std <=
  max_degenerate_std` fires (inclusive) so a truly constant region (`std == 0.0`)
  always fires. Both `flag_low` and `flag_high` are provided (not one band toggle)
  so each end is independently testable/disable-able, mirroring item 047's
  independent per-condition toggles.

- **`severity` param, default `"flagged-for-review"` (→ `Severity.FLAG`); an
  unknown string raises `ValueError`.** Reuses the exact `_LABEL_TO_SEVERITY` /
  `_severity_from_param` pattern every Stage 4 rule uses (`bounds`, `mislabel`,
  `reference_delta`, …), read once up front so a bad string fails fast (AC13). All
  conditions of one evaluation share the one configured severity.

- **A `None` statistic, an absent/`available: false`/empty block, and malformed
  sub-entries are silent (return `[]` / skip, never raise).** Item 059 emits
  `None` for absent/empty/all-non-finite labels; item 061 emits `available: false`
  + `per_label == {}` when intensity is unavailable. The rule skips a condition
  whose input statistic is `None`, and returns `[]` for an absent / non-mapping /
  unavailable block — realising "a case with no intensity features produces no
  spurious intensity finding." Malformed sub-entries (non-dict label entry, missing
  `first_order`) are tolerated defensively (skipped, not crashed), consistent with
  `reference_delta`'s / `bounds`' defensive `isinstance`/`.get` reads. The
  `extended` (radiomics) sub-dict is ignored — first-order only.

- **`default_config.yaml` is deliberately not edited (see Scope boundary).** The
  rule works from `rule_param` code-side defaults and is enabled-by-default via the
  absent-section `rule_enabled` fallback. This avoids regressing
  `tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids` (which
  asserts exactly the seven pre-existing YAML rule ids — item 047 likewise left
  `reference_delta` out of the YAML) and the item-042 golden snapshots (the rule is
  silent without a block, so full-pipeline output is byte-identical at 062 merge).
  Registering a 9th rule is safe: no test asserts the registry's exact size — the
  sibling tests use `any(r.rule_id == … for r in iter_rules())`. **Pinned for 065:**
  the run-wiring item owns adding the documented `intensity` YAML section and
  updating that item-035 id-set expectation (with the test-writer) when it enables
  the block in the pipeline.

- **Dependencies 058, 059, 061 are `✅` (merged).** The rule consumes item 061's
  `build_image_features_block` output shape
  (`per_label[str(label)]["first_order"]["median"/"std"]`, verified in
  `src/segqc/feature_report.py`), item 059's `LabelIntensity` fields
  (`median`/`std`, verified in `src/segqc/features/intensity.py`), item 058's
  committed corpus (`tests/corpus/intensity/manifest.json` + fixtures, `target_label
  == 22`, three implausible variants + one clean, verified in
  `src/segqc/synth/intensity.py`), and the item-026/034 engine/aggregation surface
  (`Rule`, `register_rule`, `get_rule`, `iter_rules`, `run_rules`, `Finding`,
  `build_case_result`, `Severity`). If any of these shapes diverged, hand back.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): a new
`src/segqc/heuristics/intensity.py`, plus a one-line registering import in
`src/segqc/heuristics/__init__.py`. **No** edits to `segqc.features.*`,
`segqc.feature_report`, `segqc.synth.*`, `segqc.pipeline`, `segqc.cli`,
`segqc.config`, `default_config.yaml`, `segqc.report`, `report_schema_v0.json`,
`segqc.aggregate`, or any other rule module.

1. **Create `src/segqc/heuristics/intensity.py`:**
   - Module docstring stating scope (a Stage 4 rule that thresholds item 061's
     `image_features` block read from `record["image_features"]`; three
     config-toggleable conditions over `first_order` median/std; no feature
     computation, no radiomics, no run wiring, no `default_config.yaml` edit) and
     the determinism/non-mutation contract.
   - Constants `DEFAULT_MIN_PLAUSIBLE_HU = 100.0`, `DEFAULT_MAX_PLAUSIBLE_HU =
     2000.0`, `DEFAULT_MAX_DEGENERATE_STD = 1.0`, and the three reason-tag string
     constants (`_LOW_TAG`, `_HIGH_TAG`, `_DEGENERATE_TAG`).
   - Reuse the standard severity helper: module-level
     `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}` and a
     `_severity_from_param(label) -> Severity` raising `ValueError` on an unknown
     string (copy the `reference_delta`/`bounds` pattern verbatim, with an
     `intensity`-specific message).

2. **Implement `@register_rule class IntensityRule(Rule)` with
   `rule_id = "intensity"` and `evaluate(self, record, config)`:**
   1. Read `severity` once via `config.rule_param(self.rule_id, "severity",
      default="flagged-for-review")` → `_severity_from_param` (raises on bad
      string, AC12/AC13).
   2. Read the three toggles (`flag_low`, `flag_high`, `flag_degenerate`, each
      `bool(...)`, default `True`) and three thresholds (`min_plausible_hu`,
      `max_plausible_hu`, `max_degenerate_std`, each `float(...)`, defaults as
      above) via `config.rule_param`.
   3. `block = record.get("image_features")`; if `block` is not a `dict` or
      `block.get("available")` is falsy, return `[]` (AC14/AC15).
   4. `per_label = block.get("per_label")`; if not a dict, return `[]`. Iterate its
      entries **sorted by integer label** (defensively derive the int label from
      the entry's `"label"`, falling back to the dict key). Skip a non-dict entry;
      read `first_order = entry.get("first_order")`, skip if not a dict.
   5. For each label, in fixed order, append findings:
      - **low:** if `flag_low` and `median is not None` and `median <
        min_plausible_hu`, append a `Finding` tagged `_LOW_TAG` (reason names label,
        `median`, `min_plausible_hu`, band), `labels=frozenset({label})`.
      - **high:** if `flag_high` and `median is not None` and `median >
        max_plausible_hu`, append a `Finding` tagged `_HIGH_TAG`.
      - **degenerate:** if `flag_degenerate` and `std is not None` and `std <=
        max_degenerate_std`, append a `Finding` tagged `_DEGENERATE_TAG` (reason
        names label, `std`, `max_degenerate_std`).
   6. Return the accumulated list (already in the deterministic order of steps
      4–5, AC20). Never mutate `record`.

3. **Register in `src/segqc/heuristics/__init__.py`:** add
   `from segqc.heuristics import intensity  # noqa: F401 — registers IntensityRule
   (item 062)` after the `reference_delta` import line. (No change to `__all__` —
   the sibling rule modules are not re-exported either.)

4. **Do not** touch the feature/report/synth/pipeline/CLI/config layers,
   `default_config.yaml`, the report/schema, `aggregate.py`, or write `tests/`
   fixtures — those are item 065's and the test-writer's remit.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_062_intensity_rule.py` (naming
  matches the `test_0NN_<rule>` siblings, e.g. `test_047_reference_delta_rule.py`).
  Add a `_RULES` snapshot/restore fixture exactly like the sibling rule tests so
  registry mutations don't leak across tests.
- **Hand-built inputs (AC1–AC20):** a helper builds a `record` with a top-level
  `image_features` block (the item-061 shape: `available: true`, `per_label[str(l)]
  = {"label": l, "first_order": {"median": …, "std": …, …}, "extended": {}}`) with
  chosen `median`/`std` per label so every firing decision is hand-checkable; and a
  `HeuristicConfig` via `default_config()` or `HeuristicConfig(**{..., "rules":
  {"intensity": {"params": {...}}}})`. Each condition is isolated (e.g. a low test
  keeps `std` well above `max_degenerate_std` and `median` inside on the high side).
- **Corpus-driven inputs (AC21–AC24):** load each item-058 committed case from
  `segqc.synth.intensity.load_intensity_manifest()` /
  `INTENSITY_CORPUS_DIR` (scan + shared seg via `nibabel`/`segqc.io`), compute
  `compute_intensity_features(scan_img, seg_img)`, assemble the block via
  `build_image_features_block(...)`, wrap as `record = {"image_features": block}`,
  and evaluate under `default_config()`. Assert the clean case is silent and each
  implausible variant fires the expected-tagged finding on label `22`.
- **One focused test per AC (AC1–AC24)**, each asserting a single observable fact
  (registration, one condition firing/not, one toggle, one threshold move,
  severity, ValueError, silence, `None`-skip, ordering, determinism/immutability,
  and the four corpus cases).
- **Adversarial / edge cases (beyond the ACs):**
  - **Boundary values** — `median == min_plausible_hu` and `median ==
    max_plausible_hu` do **not** fire (inclusive band); `std == max_degenerate_std`
    **does** fire (inclusive degeneracy).
  - **Empty block** — `image_features` present, `available: true`, `per_label ==
    {}` ⇒ `[]`.
  - **Malformed entries** — a non-dict label entry, an entry missing `first_order`,
    or a `first_order` missing `median`/`std` keys are tolerated (skipped, no
    crash).
  - **Multiple conditions on one label** — a label with `median > max_plausible_hu`
    **and** `std <= max_degenerate_std` emits high then degenerate in that fixed
    order (AC20 within a single label).
  - **Determinism / non-mutation** — deep-copy `record` before the call and assert
    equality afterward; assert equal finding lists across two calls (AC19).
  - **Runner + aggregation integration** — `run_rules(record, default_config())`
    includes the finding and `build_case_result(...).verdict.overall` escalates,
    with the label in the per-label reasons (AC18); and a disabled rule
    (`rules.intensity.enabled = False`) is skipped by the runner (silent).
  - **Golden safety** — a record with **no** `image_features` key run through the
    full default registry yields the same findings as before this rule existed (the
    rule contributes nothing), confirming the 062-merge no-op on existing pipeline
    output.

## Dependencies

- **Item 061 (✅ merged) — REQUIRED.** Provides the `image_features` block shape
  (`build_image_features_block`) this rule reads from `record["image_features"]`:
  `available`, `per_label[str(label)]["first_order"]["median"/"std"]`. The rule
  consumes these numbers; it does not import `segqc.feature_report`.
- **Item 059 (✅ merged) — REQUIRED (transitive, and for the corpus ACs).** Defines
  `LabelIntensity` (`median`/`std`, `None` sentinels) and
  `compute_intensity_features`, used in AC21–AC24 to build the block from the
  fixtures. The rule does not import `segqc.features.intensity` in production.
- **Item 058 (✅ merged) — REQUIRED (corpus ACs).** Provides the committed
  intensity corpus (`tests/corpus/intensity/`: one clean HU case + metal /
  soft_tissue / degenerate_uniform variants on `target_label == 22`) the rule fires
  against in AC21–AC24.
- **Item 026 (✅ merged) — REQUIRED.** Provides the rule engine: `Rule`,
  `register_rule`, `get_rule`, `iter_rules`, `run_rules`, and `Finding`. This rule
  is a standard `@register_rule` subclass.
- **Item 034 (✅ merged) — used, not modified.** `segqc.aggregate.build_case_result`
  / `aggregate_verdict` fold this rule's findings into the case `Verdict` with no
  change (AC18).
- **Items 027–033, 047 (✅ merged) — pattern source, not modified.** The concrete
  rule families whose severity helper, config-param reads, defensive record access,
  and deterministic ordering this rule mirrors (esp. `bounds` and `reference_delta`).
- **Downstream (this item feeds them):** **065** wires
  `record["image_features"] = build_image_features_block(compute_intensity_features(...))`
  into `segqc run`, renders intensity findings into the human report, adds the
  documented `intensity` section to `default_config.yaml` (updating the item-035
  id-set expectation), and asserts the Stage-8 acceptance suite (fires on the
  implausible variant, silent on clean GT). **064** (reference-grounded intensity
  delta rule) is the level-aware complement and is independent of this rule.

## Decisions & Trade-offs

To be updated during implementation.
