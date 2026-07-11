# Item 047 — Delta-to-reference rule family (heuristic layer)

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 047 *(the fifth item in queue-005; consumes 046's `reference_delta` block; feeds 049's `segqc run` wiring + acceptance suite)*
> **Objectives:** G3 (distinguish failure from legitimate variation — this item
> turns 046's computed reference-relative metrics into an *explainable rule* that
> flags out-of-distribution vertebrae, the heuristic realisation of the vision's
> §5.4 "delta to reference" rule input) and G2/G4 (a §6 failure surfaces as a
> config-driven, label-attributed, human-readable finding that flows into the
> per-case QC verdict/report). Advances the roadmap Stage-6 deliverable
> "Delta-to-reference rules: per-vertebra distribution distance / out-of-range vs
> reference."
> **Suggested branch:** `aide/047-delta-to-reference-rule-family`

---

## Description

Add a new **config-driven rule family** to the Stage 4 heuristic engine that
consumes item 046's per-vertebra **delta-to-reference** metrics and **fires a
`Finding`** when a vertebra is *out-of-distribution vs the reference*. The rule
is a peer of the existing Stage 4 rules (`bounds`, `fragmentation`, `coverage`,
`sequence`, `border`, `overlap`, `mislabel`): it subclasses
`segqc.heuristics.rule.Rule`, is registered via `@register_rule` with
`rule_id = "reference_delta"`, and implements the standard
`evaluate(record, config) -> list[Finding]` contract. Its findings flow through
the existing runner (`segqc.heuristics.run_rules`, item 026) and verdict
aggregation (`segqc.aggregate.build_case_result` / `aggregate_verdict`, item 034)
with **no change** to either.

Deliver a new module `src/segqc/heuristics/reference_delta.py` (registered by an
import line in `src/segqc/heuristics/__init__.py`, mirroring items 027–033).

### How the rule reads the delta metrics — the record seam

Every Stage 4 rule receives only `(record, config)`, where `record` is the
per-case feature dict. Item 046 computes the delta metrics as a **top-level
`reference_delta` block** (the dict produced by
`segqc.reference.reference_delta_to_dict`, sibling of `features`/`findings` in the
*report*). This rule therefore reads that same dict shape from
**`record.get("reference_delta")`**: item 049's `segqc run` wiring computes the
block (`compute_reference_delta(...)` → `reference_delta_to_dict(...)`) and places
it under the record's `reference_delta` key before calling `run_rules`. When the
key is **absent** — no reference loaded, run not yet wired (the current default),
or a non-mapping value — the rule returns `[]` (silent, never raises). This keeps
the rule **stateless, pure, and I/O-free** exactly like its siblings: it imports
nothing from `segqc.reference`, loads no artifact, and recomputes no statistic —
it only reads already-computed numbers out of the record.

### What the rule fires on

For each label in the block's `per_label` whose entry is `available: true`, the
rule applies up to three **independently config-toggleable** firing conditions,
each emitting one or more `Finding`s (`rule_id="reference_delta"`, config-driven
severity, offending label, explainable reason):

1. **Distribution-distance outlier (label-level).** Fires when
   `distribution_distance is not None and distribution_distance >=
   max_distribution_distance`. One finding per label.
2. **Out-of-range feature.** Fires for each feature the block already flagged
   `out_of_range` (i.e. outside the reference's `(lower_pct, upper_pct)` band,
   default p1/p99). One finding per (label, feature), read from the block's
   `out_of_range_features` list. Realises "falls outside the reference range."
3. **Robust-z outlier (per feature).** Fires for each feature whose
   `robust_z is not None and abs(robust_z) >= max_robust_z`. One finding per
   (label, feature).

A label whose entry is `available: false` (level or stratum absent from the
reference — item 046 AC9/AC13) contributes **no** findings: reference-grounded
judgement is silent where there is no reference, per the queue's "silent (not
erroring) when no reference is available for a level."

### Scope boundary — what this item is **not**

- **Not the delta computation.** The metrics (z / robust-z / percentile-rank /
  out-of-range / distribution-distance) and their serialisation are **item 046**
  (merged). This item adds no statistic; it only thresholds the numbers 046
  produced. It does not import or modify `segqc.reference.delta`.
- **Not the `segqc run` / pipeline wiring.** Loading the bundled reference,
  calling `compute_reference_delta`, and **injecting the `reference_delta` block
  into the record** passed to `run_rules` (plus rendering reference findings into
  the human report and the GT-in-range / perturbation-out-of-range acceptance
  suite) are **item 049**. This item defines the record seam the rule reads and
  fires correctly when the block is present, but does **not** change
  `segqc.pipeline` or `segqc.cli`.
- **Not the bounds config switch.** Sourcing the `bounds` rule's min/max from the
  reference percentiles is **item 048**. This item does not touch
  `segqc.heuristics.bounds` or `segqc.config`.
- **Not a `default_config.yaml` edit.** To avoid regressing item 035's
  `tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids` (which
  asserts the bundled YAML declares *exactly* the seven pre-existing rule ids),
  this item leaves `src/segqc/default_config.yaml` untouched. The rule's
  thresholds are read from `config.rule_param("reference_delta", …, default=…)`
  with code-side defaults, and the rule is enabled-by-default (an absent config
  section ⇒ `rule_enabled` returns `True`). Documenting the rule's thresholds in
  the bundled YAML and updating that item-035 id-set is deferred to item 049 (the
  run-wiring item, which owns the pipeline and is scoped to touch config + the
  item-035 expectation with the test-writer).
- **Not a report-schema or serialiser change.** Item 046 already added the
  `reference_delta` report block + `serialize_report(reference_delta=…)`. This
  rule's findings serialise through the **existing** Stage 4 findings machinery
  (item 035); no `report.py` / `report_schema_v0.json` change is needed.

---

## Public interface (the contract 049 builds on)

New module `src/segqc/heuristics/reference_delta.py`, registered in
`src/segqc/heuristics/__init__.py`. Private helpers are the builder's choice; the
surface below is the contract.

```python
# rule_id string (registry key, embedded in every Finding this rule emits)
#   "reference_delta"

# Config defaults (read via config.rule_param("reference_delta", key, default)):
DEFAULT_MAX_ROBUST_Z: float = 3.5             # |robust_z| >= this fires (per feature)
DEFAULT_MAX_DISTRIBUTION_DISTANCE: float = 3.0  # distribution_distance >= this fires (per label)
# flag_out_of_range / flag_robust_z / flag_distribution_distance: bool, default True each
# severity: str, default "flagged-for-review"

# Stable start-of-reason markers (tests assert on these prefixes):
_OUT_OF_RANGE_TAG = "Reference out-of-range:"
_ROBUST_Z_TAG     = "Reference robust-z outlier:"
_DISTANCE_TAG     = "Reference distribution-distance outlier:"

@register_rule
class ReferenceDeltaRule(Rule):
    rule_id = "reference_delta"
    def evaluate(self, record, config) -> list[Finding]:
        """Read record["reference_delta"] (the reference_delta_to_dict shape,
        item 046) and emit a Finding per fired condition. Returns [] when the
        block is absent/non-mapping or every available label is in-distribution.
        Pure; never mutates record; raises ValueError only for an unrecognised
        `severity` config string."""
```

**Record seam consumed** (the `reference_delta_to_dict` shape, item 046 — read,
never written, by this rule):

```json
{
  "reference_delta_version": "1.0",
  "stratum": "all", "lower_pct": 1, "upper_pct": 99,
  "per_label": {
    "20": {
      "label": 20, "level_name": "L1", "available": true,
      "distribution_distance": 4.2,
      "out_of_range_features": ["physical_volume_mm3"],
      "features": {
        "physical_volume_mm3": {
          "value": 250000.0, "z_score": 8.1, "robust_z": 6.4,
          "percentile_rank": 100.0, "out_of_range": true
        }
      }
    },
    "99": { "label": 99, "level_name": "UNKNOWN", "available": false,
            "distribution_distance": null, "out_of_range_features": [], "features": {} }
  }
}
```

**Finding emission order (deterministic).** Labels ascending by integer `label`;
within a label, in fixed condition order — (1) distribution-distance (label-level),
then (2) out-of-range findings for each feature in `out_of_range_features`
(already sorted by name in the block), then (3) robust-z findings for each feature
with `abs(robust_z) >= max_robust_z` in ascending feature-name order. Each finding
is `Finding(rule_id="reference_delta", severity=<config>, reason=<tagged,
human-readable>, labels=frozenset({label}))`.

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. Tests hand-build a
minimal `record` carrying a top-level `reference_delta` block (the item-046
`reference_delta_to_dict` shape) plus a `HeuristicConfig` (via
`segqc.config.default_config()` or a crafted `rules.reference_delta.params`
mapping), so every firing decision is hand-checkable. "In-distribution" means an
`available: true` label with no out-of-range feature, every `abs(robust_z) <
max_robust_z`, and `distribution_distance < max_distribution_distance`._

- [ ] **AC1: the rule is registered and discoverable.**
      `segqc.heuristics.get_rule("reference_delta")` returns a `Rule` instance
      whose `rule_id == "reference_delta"`, and `iter_rules()` yields exactly one
      rule with that id.

- [ ] **AC2: an in-distribution vertebra produces no finding.** For a record
      whose `reference_delta.per_label` holds one `available: true` label with
      `out_of_range_features == []`, every feature `abs(robust_z) < max_robust_z`,
      and `distribution_distance < max_distribution_distance`, `evaluate` returns
      `[]`.

- [ ] **AC3: an out-of-range feature fires an out-of-range finding.** For a label
      whose block lists a feature in `out_of_range_features` (with
      `flag_out_of_range` at its default `True`), `evaluate` returns exactly one
      out-of-range `Finding` whose `rule_id == "reference_delta"`,
      `labels == frozenset({label})`, and whose `reason` starts with
      `"Reference out-of-range:"`.

- [ ] **AC4: a large robust-z fires a robust-z finding.** For a label with a
      feature whose `abs(robust_z) >= max_robust_z` (default `3.5`) but
      `out_of_range == false` and `distribution_distance < max_distribution_distance`
      (isolating the condition), `evaluate` returns exactly one `Finding` for that
      label whose `reason` starts with `"Reference robust-z outlier:"` and names
      the offending feature.

- [ ] **AC5: a large distribution-distance fires a label-level finding.** For a
      label whose `distribution_distance >= max_distribution_distance` (default
      `3.0`) — with no out-of-range feature and every `abs(robust_z) <
      max_robust_z` isolating the condition — `evaluate` returns exactly one
      `Finding` attributed to that label whose `reason` starts with
      `"Reference distribution-distance outlier:"`.

- [ ] **AC6: the robust-z threshold is read from config.** A feature whose
      `abs(robust_z)` is (say) `4.0` fires with the default `max_robust_z`; the
      same record with `rules.reference_delta.params.max_robust_z = 10.0` produces
      **no** robust-z finding, while `max_robust_z = 1.0` fires — i.e. the
      threshold is taken from `config.rule_param`, not hard-coded.

- [ ] **AC7: the distribution-distance threshold is read from config.** A label
      whose `distribution_distance` is (say) `4.0` fires the distance condition at
      the default; with `rules.reference_delta.params.max_distribution_distance =
      10.0` it does not, while `= 1.0` it does — the threshold comes from config.

- [ ] **AC8: `flag_out_of_range: false` disables the out-of-range condition.**
      With `rules.reference_delta.params.flag_out_of_range = False`, a label whose
      only anomaly is an out-of-range feature produces **no** finding, while the
      robust-z and distribution-distance conditions (left enabled) still fire on a
      label that triggers them.

- [ ] **AC9: `flag_robust_z: false` disables the robust-z condition.** With
      `flag_robust_z = False`, a label whose only anomaly is a large `robust_z`
      produces no finding, while the other two conditions still fire when
      triggered.

- [ ] **AC10: `flag_distribution_distance: false` disables the distance
      condition.** With `flag_distribution_distance = False`, a label whose only
      anomaly is a large `distribution_distance` produces no finding, while the
      other two conditions still fire when triggered.

- [ ] **AC11: severity is configurable.** With
      `rules.reference_delta.params.severity = "fail"`, every emitted `Finding`
      has `severity == segqc.verdict.Severity.FAIL`; with the default it is
      `Severity.FLAG` (`"flagged-for-review"`).

- [ ] **AC12: an unrecognised severity string raises `ValueError`.**
      `evaluate` with `rules.reference_delta.params.severity = "not-a-severity"`
      raises `ValueError` (before/independently of emitting findings), mirroring
      the other rules' severity-validation contract.

- [ ] **AC13: an absent `reference_delta` block is silent, not an error.** For a
      record with **no** `reference_delta` key (the current pipeline default), and
      also for a record whose `reference_delta` is a non-mapping/`None`, `evaluate`
      returns `[]` without raising.

- [ ] **AC14: an `available: false` label produces no finding.** A block whose
      label entry has `available: false` (empty `features`, `null`
      `distribution_distance`, empty `out_of_range_features`) yields no finding for
      that label — reference-grounded judgement is silent where the reference has
      no entry — even when other `available: true` labels in the same block fire.

- [ ] **AC15: findings flow through `run_rules` and verdict aggregation.** For a
      firing record, `segqc.heuristics.run_rules(record, config)` includes the
      rule's `Finding`(s), and
      `segqc.aggregate.build_case_result(run_rules(record, config), config).verdict`
      resolves `overall` to at least the finding severity (e.g. `Severity.FLAG`
      under defaults) with the offending integer label present in the verdict's
      per-label reasons — the rule composes with the existing engine unchanged.

- [ ] **AC16: the reason is explainable — measured value vs reference context.**
      An out-of-range `Finding`'s `reason` (a non-empty, non-whitespace string)
      names the offending integer label and level, the feature name, the measured
      `value`, and the reference context (its `percentile_rank` and the
      `(lower_pct, upper_pct)` band) — satisfying the queue's "human-readable
      reason (measured value vs reference range / percentile)."

- [ ] **AC17: computation is deterministic and non-mutating.** Two `evaluate`
      calls on the same `record` + `config` return **equal** finding lists
      (equal `Finding`s in the same order), and a deep before/after comparison of
      `record` shows it is unchanged (the `reference_delta` block is read, never
      written).

- [ ] **AC18: findings are emitted in a deterministic order.** For a record whose
      block fires multiple conditions across two labels (e.g. label 20 with an
      out-of-range feature and a large-distance, label 23 with a large robust-z),
      the returned findings appear ascending by integer label and, within a label,
      in the fixed condition order (distribution-distance → out-of-range →
      robust-z) with per-feature findings in ascending feature-name order —
      independent of `per_label` dict insertion order.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete rule is recorded here for audit; several
**pin an interface** item 049 must honour (hand back if reality diverges).

- **The rule reads the delta from `record["reference_delta"]` (a top-level record
  key holding the `reference_delta_to_dict` shape).** The fixed
  `Rule.evaluate(record, config)` signature is the only channel a rule has, and
  item 046 deliberately produced the delta as a *top-level* block (its own AC/
  Assumptions: sibling of `features`/`findings`, not nested in `per_label`). So the
  rule reads `record.get("reference_delta")` and item 049's run wiring must place
  the computed block there **before** `run_rules`. **Pinned for 049:** inject
  `record["reference_delta"] = reference_delta_to_dict(compute_reference_delta(...))`
  into the record fed to `run_rules`. If 049 instead nests the block elsewhere or
  passes the reference by another channel, hand back — the rule's read path is this
  key. Reading the metrics from the record (not recomputing them) keeps the rule
  stateless and I/O-free like every sibling, and makes it silent-by-default until
  049 wires the block (so no existing pipeline/golden output changes at 047 merge).

- **`rule_id = "reference_delta"`.** Matches the module name and the item-046
  block name; distinct from the seven existing ids. Registered via the standard
  `@register_rule` + an import line in `segqc/heuristics/__init__.py`, exactly as
  items 027–033 register their rules.

- **Three independent, config-toggleable firing conditions: distribution-distance
  (label-level), out-of-range (per feature), robust-z (per feature).** These are
  the queue's enumerated signals ("robust-z / percentile / distribution-distance …
  or falls outside the reference range"). Each has its own boolean toggle
  (`flag_distribution_distance` / `flag_out_of_range` / `flag_robust_z`, default
  `True`) and — where numeric — its own threshold (`max_distribution_distance`
  default `3.0`, `max_robust_z` default `3.5`), read via `config.rule_param`. Both
  robust-z and out-of-range can fire on the same (label, feature) (a tail value is
  usually both) — accepted for explainability (each carries a distinct reason),
  mirroring `mislabel`'s two independent OR'd detectors. A single fired condition
  is enough to flag the vertebra, satisfying "fires when out-of-distribution."

- **Percentile-rank is *not* a separate firing condition; it enriches the
  out-of-range reason.** The queue lists "percentile" among the signals, but a
  percentile-tail crossing is exactly what the reference's own `(lower_pct,
  upper_pct)` out-of-range flag already encodes (item 046 computed `out_of_range`
  from those percentile bounds). Adding a separate percentile-band firing lever
  would double-fire on the same tail signal. So `percentile_rank` is surfaced in
  the out-of-range finding's **reason** (AC16) rather than as a fourth condition —
  keeping conditions non-redundant while still honouring "percentile."

- **Firing thresholds are inclusive (`>=`) and compared on magnitude for robust-z
  (`abs(robust_z)`).** `max_robust_z`/`max_distribution_distance` fire at-or-above
  the threshold (mirrors `mislabel`'s inclusive `offset_mm >= max_offset_mm`).
  Robust-z uses absolute value so a far *lower*-tail vertebra (large negative
  robust-z, item 046 AC4) fires as readily as an upper-tail one. `distribution_
  distance` is an RMS (item 046 AC8) and thus already non-negative — compared
  directly. Default thresholds (`3.5` σ-equivalent robust-z, `3.0` RMS distance)
  are deliberately conservative placeholders (like `bounds`' shipped defaults) that
  Stage 7 calibration will tune; the value only needs to be a lever the tests can
  move (AC6/AC7), not a validated cut-point.

- **Out-of-range findings are per (label, feature), driven by the block's
  `out_of_range_features` list.** Item 046 already computed and *sorted* that list;
  the rule iterates it and pulls each feature's `value`/`percentile_rank` from the
  block's `features[name]` for the reason. One finding per feature (not one
  aggregate per label) mirrors `bounds`' one-finding-per-(label, metric) design for
  maximal explainability.

- **`severity` param, default `"flagged-for-review"` (→ `Severity.FLAG`); an
  unknown string raises `ValueError`.** Reuses the exact `_LABEL_TO_SEVERITY` /
  `_severity_from_param` pattern every Stage 4 rule uses (`bounds`, `mislabel`,
  …), read once up front so a bad string fails fast (AC12). All conditions of one
  evaluation share the one configured severity.

- **A label is judged only when `available: true`; `available: false` and an
  absent/malformed block are silent (return `[]`, never raise).** Directly
  realises the queue's "silent (not erroring) when no reference is available for a
  level" and item 046's `available` contract. Malformed sub-entries (non-dict
  label entry, missing `features`, non-list `out_of_range_features`) are tolerated
  defensively — skipped, not crashed — consistent with `mislabel`'s / `bounds`'
  defensive `isinstance`/`.get` reads.

- **The rule imports nothing from `segqc.reference`.** Everything it needs (`z_
  score`, `robust_z`, `percentile_rank`, `out_of_range`, `distribution_distance`,
  `out_of_range_features`, `available`, `level_name`, `lower_pct`, `upper_pct`) is
  already in the `reference_delta` block. The rule depends only on
  `segqc.heuristics.{rule,finding}` and `segqc.verdict.Severity` — the same import
  surface as the other rules — so it stays light and cannot circular-import the
  reference layer.

- **`default_config.yaml` is deliberately not edited (see Scope boundary).** The
  rule works from `rule_param` code-side defaults and is enabled-by-default via the
  absent-section `rule_enabled` fallback. This avoids regressing
  `tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids`
  (asserts exactly seven YAML rule ids) and item 042's golden snapshots (the rule
  is silent without a block, so full-pipeline output is byte-identical at 047
  merge). Registering an 8th rule is safe: no test asserts the registry's exact
  size — the sibling tests use `any(r.rule_id == … for r in iter_rules())`.
  **Pinned for 049:** the run-wiring item owns adding the documented
  `reference_delta` YAML section and bumping that item-035 id-set expectation
  (with the test-writer), when it enables the block in the pipeline.

- **Dependencies 043–046 are `✅` (merged).** The rule consumes only the item-046
  `reference_delta_to_dict` block shape (verified in
  `src/segqc/reference/delta.py`) and the item-026/034 engine/aggregation surface
  (`Rule`, `register_rule`, `get_rule`, `iter_rules`, `run_rules`, `Finding`,
  `build_case_result`, `Severity`), all confirmed present in the merged tree. If
  the block shape (`per_label[str(label)]` → `available` / `distribution_distance`
  / `out_of_range_features` / `features[name]` → `value`/`robust_z`/`out_of_range`)
  changed, hand back.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): a new
`src/segqc/heuristics/reference_delta.py`, plus a one-line registering import in
`src/segqc/heuristics/__init__.py`. **No** edits to `segqc.reference.*`,
`segqc.pipeline`, `segqc.cli`, `segqc.config`, `default_config.yaml`,
`segqc.report`, `report_schema_v0.json`, `segqc.aggregate`, or any other rule
module.

1. **Create `src/segqc/heuristics/reference_delta.py`:**
   - Module docstring stating scope (a Stage 4 rule that thresholds item 046's
     `reference_delta` block read from `record["reference_delta"]`; three
     config-toggleable conditions; no delta computation, no reference import, no
     run wiring, no `default_config.yaml` edit) and the determinism/non-mutation
     contract.
   - Constants `DEFAULT_MAX_ROBUST_Z = 3.5`, `DEFAULT_MAX_DISTRIBUTION_DISTANCE =
     3.0`, and the three reason-tag string constants (`_OUT_OF_RANGE_TAG`,
     `_ROBUST_Z_TAG`, `_DISTANCE_TAG`).
   - Reuse the standard severity helper: module-level
     `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}` and a
     `_severity_from_param(label) -> Severity` raising `ValueError` on an unknown
     string (copy the `mislabel`/`bounds` pattern verbatim, with a
     `reference_delta`-specific message).

2. **Implement `@register_rule class ReferenceDeltaRule(Rule)` with
   `rule_id = "reference_delta"` and `evaluate(self, record, config)`:**
   1. Read `severity` once via `config.rule_param(self.rule_id, "severity",
      default="flagged-for-review")` → `_severity_from_param` (raises on bad
      string, AC12/AC11).
   2. Read the three toggles (`flag_out_of_range`, `flag_robust_z`,
      `flag_distribution_distance`, each `bool(...)`, default `True`) and two
      thresholds (`max_robust_z` → `float`, default `DEFAULT_MAX_ROBUST_Z`;
      `max_distribution_distance` → `float`, default
      `DEFAULT_MAX_DISTRIBUTION_DISTANCE`) via `config.rule_param`.
   3. `block = record.get("reference_delta")`; if `block` is not a `dict`, return
      `[]` (AC13). Read `lower_pct`/`upper_pct` for the reason (with `.get`).
   4. `per_label = block.get("per_label", {})`; if not a dict, return `[]`.
      Iterate its entries **sorted by integer label** (`sorted(..., key=lambda kv:
      int(kv[1].get("label", kv[0])))` — defensively derive the int label). Skip a
      non-dict entry or one with `available` not truthy (AC14).
   5. For each available label, in fixed order, append findings:
      - **distribution-distance:** if `flag_distribution_distance` and
        `distribution_distance is not None` and `>= max_distribution_distance`,
        append a `Finding` tagged `_DISTANCE_TAG` (reason names label, level,
        value, threshold), `labels=frozenset({label})`.
      - **out-of-range:** if `flag_out_of_range`, for each feature name in the
        entry's `out_of_range_features` (a list; iterate as given — 046 already
        sorted it, but sort defensively), append a `Finding` tagged
        `_OUT_OF_RANGE_TAG` whose reason names label, level, feature, the feature's
        `value` + `percentile_rank` (from `features[name]`), and the `(lower_pct,
        upper_pct)` band (AC16).
      - **robust-z:** if `flag_robust_z`, for each feature name in
        `sorted(features)` whose `robust_z is not None` and `abs(robust_z) >=
        max_robust_z`, append a `Finding` tagged `_ROBUST_Z_TAG` (reason names
        label, level, feature, `robust_z`, threshold).
   6. Return the accumulated list (already in the deterministic order of steps
      4–5, AC18). Never mutate `record`.

3. **Register in `src/segqc/heuristics/__init__.py`:** add
   `from segqc.heuristics import reference_delta  # noqa: F401 — registers
   ReferenceDeltaRule (item 047)` after the `mislabel` import line. (No change to
   `__all__` — the sibling rule modules are not re-exported either.)

4. **Do not** touch `segqc.reference.*`, the pipeline/CLI, config,
   `default_config.yaml`, the report/schema, `aggregate.py`, or write `tests/`
   fixtures — those are items 048/049 and the test-writer's remit.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_047_reference_delta_rule.py`
  (naming matches the `test_04x_*` / `test_0NN_<rule>` siblings, e.g.
  `test_033_mislabel.py`). Add a `_RULES` snapshot/restore fixture exactly like the
  sibling rule tests (`test_033_mislabel.py` lines 152–157) so registry mutations
  don't leak across tests.
- **Inputs are hand-built:** a helper builds a `record` with a top-level
  `reference_delta` block (the item-046 `reference_delta_to_dict` shape) with
  chosen `available`, `distribution_distance`, `out_of_range_features`, and
  `features[name] = {value, z_score, robust_z, percentile_rank, out_of_range}`
  values so every firing decision is hand-checkable; and a `HeuristicConfig` via
  `default_config()` or `HeuristicConfig(**{..., "rules": {"reference_delta":
  {"params": {...}}}})`. One or two tests may build the block for real via
  `reference_delta_to_dict(compute_reference_delta(features_block, reference))` to
  confirm the rule reads the genuine 046 shape.
- **One focused test per AC (AC1–AC18)**, each asserting a single observable fact
  (registration, one condition firing/not, one toggle, one threshold move,
  severity, ValueError, silence, ordering, determinism/immutability).
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty block** — `reference_delta` present with `per_label == {}` ⇒ `[]`.
  - **Malformed entries** — a non-dict label entry, an entry missing `features`,
    an `out_of_range_features` that is not a list, or a feature whose `robust_z is
    null` (never fires robust-z) are all tolerated (skipped, no crash).
  - **Value exactly on the threshold** — `abs(robust_z) == max_robust_z` fires
    (inclusive `>=`); `distribution_distance == max_distribution_distance` fires.
  - **`available: false` mixed with `available: true`** — only the available,
    anomalous label(s) fire (AC14 with a positive control in the same block).
  - **All three conditions on one label** — emits distance, then out-of-range,
    then robust-z findings in that fixed order (AC18 within a single label).
  - **Determinism / non-mutation** — deep-copy `record` before the call and assert
    equality afterward; assert equal finding lists across two calls (AC17).
  - **Runner + aggregation integration** — `run_rules(record, default_config())`
    includes the finding and `build_case_result(...).verdict.overall` escalates,
    with the label in the per-label reasons (AC15); and a disabled rule
    (`rules.reference_delta.enabled = False`) is skipped by the runner (silent).
  - **Golden safety** — a record with **no** `reference_delta` key run through the
    full default registry yields the same findings as before this rule existed
    (the rule contributes nothing), confirming the 047-merge no-op on existing
    pipeline output.

## Dependencies

- **Item 046 (✅ merged) — REQUIRED.** Provides the `reference_delta` block shape
  (`reference_delta_to_dict` / `compute_reference_delta`) this rule reads from
  `record["reference_delta"]`: per-label `available` / `distribution_distance` /
  `out_of_range_features` / `features[name]` → `value`/`robust_z`/`percentile_rank`
  /`out_of_range`, plus top-level `lower_pct`/`upper_pct`. The rule consumes these
  numbers; it does not import `segqc.reference`.
- **Item 026 (✅ merged) — REQUIRED.** Provides the rule engine: `Rule`,
  `register_rule`, `get_rule`, `iter_rules`, `run_rules`, and `Finding`. This rule
  is a standard `@register_rule` subclass.
- **Item 034 (✅ merged) — used, not modified.** `segqc.aggregate.build_case_result`
  / `aggregate_verdict` fold this rule's findings into the case `Verdict` with no
  change (AC15).
- **Items 027–033 (✅ merged) — pattern source, not modified.** The concrete rule
  families whose severity helper, config-param reads, defensive record access, and
  deterministic ordering this rule mirrors (esp. `bounds` and `mislabel`).
- **Item 043/044/045 (✅ merged) — transitive only.** Needed to *build* a real
  reference and hence a real block in the one optional end-to-end test; the rule
  itself has no direct dependency on them.
- **Downstream (this item feeds them):** **049** wires
  `record["reference_delta"] = reference_delta_to_dict(compute_reference_delta(...))`
  into `segqc run`, renders reference findings into the human report, adds the
  documented `reference_delta` section to `default_config.yaml` (updating the
  item-035 id-set expectation), and asserts the GT-in-range / perturbation-out-of-
  range acceptance suite (**G3**). **048** (bounds source switch) is independent.

## Decisions & Trade-offs

To be updated during implementation.
