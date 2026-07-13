# Item 064 — Level-aware delta-to-reference intensity rule

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features (Phase 2)
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 064 *(the rule half of Stage-8 deliverable 3; consumes 063's intensity-extended reference artifact + 061's `image_features` block; feeds 065's `segqc run` wiring + Stage-8 acceptance suite)*
> **Objectives:** G3 (distinguish failure from legitimate variation — grounds an
> intensity judgement in each vertebra's **own level's** VerSe-derived reference
> distribution rather than a hand-guessed global HU band, so a value that is
> normal for one level but statistically anomalous for another is flagged
> level-awarely), G2 (a §6-style failure surfaces as a config-driven,
> label-attributed, human-readable finding that flows into the per-case verdict),
> and G7 (deterministic, config-driven, regression-testable firing **and**
> non-firing). Advances the roadmap Stage-8 deliverable "Reference distributions
> extended with intensity features" (its rule half) and the vision's §5.4
> "delta to reference" rule input, extended to the image-based feature family.
> **Suggested branch:** `aide/064-level-aware-delta-to-reference`

---

## Description

Complete Stage-8 deliverable 3's **reference grounding**: teach the Stage-6
delta-to-reference machinery to score the **intensity** feature family against
the intensity-extended reference artifact that item 063 built, and add a **new
Stage-4 rule** that fires when a vertebra's intensity is a statistical outlier
**relative to its own anatomical level's** reference distribution.

This is the *level-aware, reference-relative* counterpart to item 062's
*absolute, level-agnostic* implausible-intensity rule. Item 062 fires on a fixed
global HU band (`< 100 HU` ⇒ soft-tissue/air, `> 2000 HU` ⇒ metal); item 064
instead asks "is this vertebra's `intensity_median` far from what VerSe says is
normal **for an L3** (or T12, or C7…)?" — a large per-level robust-z or an
out-of-percentile-band value against `reference.levels[level_name]`. The two are
complementary and both ship in Stage 8.

The work has two additive halves, mirroring the item 046 (compute) → item 047
(rule) split that already exists for the geometric delta:

1. **Compute (`src/segqc/reference/delta.py`)** — add a **sibling** function
   `compute_intensity_reference_delta(features_block, image_features, reference,
   …)` that computes, per label and per tracked `intensity_*` feature, the same
   z / robust-z / percentile-rank / out-of-range / distribution-distance metrics
   item 046 computes for geometry — but drawing the feature **values** from item
   061's `image_features` block (`per_label[str(label)]["first_order"]`) and the
   feature **distributions** from item 063's per-level intensity `feature_stats`.
   It reuses item 046's existing private helpers (`_feature_delta`,
   `_percentile_rank`, `_distribution_distance`) and dataclasses (`FeatureDelta`,
   `LabelDelta`, `ReferenceDelta`), and serialises through the existing
   `reference_delta_to_dict`. **`compute_reference_delta` (geometry) is not
   modified** — it stays byte-identical and intensity-inert (item 063 AC14).

2. **Rule (`src/segqc/heuristics/intensity_reference_delta.py`)** — add a new
   `@register_rule class IntensityReferenceDeltaRule` (`rule_id =
   "intensity_reference_delta"`) that reads the computed block from
   **`record["intensity_reference_delta"]`** and emits a `Finding` per fired
   condition (distribution-distance / out-of-range / robust-z), mirroring item
   047's `ReferenceDeltaRule` mechanics but with intensity-specific reason tags.
   It imports nothing from `segqc.reference`, computes no statistic, is
   stateless/I-O-free, and is **inert** (returns `[]`) when the block is absent
   (the current pipeline default until item 065 wires it) or when the loaded
   reference carried no intensity distributions (so the block's intensity
   feature lists are empty — backward compatibility).

### Architecture decision — a *separate* block + rule, not an extension of the geometric ones

Item 064 adds a **distinct** compute function, a **distinct** record key
(`intensity_reference_delta`), and a **distinct** rule (`rule_id =
"intensity_reference_delta"`) rather than folding intensity into item 046's
`compute_reference_delta` / item 047's `ReferenceDeltaRule` / the
`reference_delta` block. Rationale (see Assumptions for the full argument): it
keeps the geometric delta computation and rule **byte-identical** (protecting
item 042/047/049 golden output and item 063 AC14), gives intensity its **own**
config namespace, thresholds, and reference-citing reasons, and mirrors the
established Stage-8 precedent — item 062 added a **separate** `IntensityRule`
(`rule_id = "intensity"`) rather than extending an existing rule.

### Scope boundary — what this item is **not**

- **No `segqc run` / CLI wiring.** Loading the reference, calling
  `compute_intensity_reference_delta(...)`, and injecting
  `record["intensity_reference_delta"]` into the record fed to `run_rules`
  (plus documenting the mounted-VerSe intensity path) are **item 065**, exactly
  as item 047 deferred its wiring to item 049. This item defines the record seam
  the rule reads and fires correctly when the block is present; it does **not**
  change `segqc.pipeline` or `segqc.cli`.
- **No `default_config.yaml` edit.** To avoid regressing
  `tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids`
  (which asserts the bundled YAML declares *exactly* the pre-existing rule ids)
  and item 042's golden snapshots, this item leaves
  `src/segqc/default_config.yaml` untouched. The rule reads its thresholds via
  `config.rule_param("intensity_reference_delta", …, default=…)` with code-side
  defaults and is enabled-by-default via the absent-section `rule_enabled`
  fallback. Documenting the section in the YAML and updating the item-035 id-set
  is deferred to item 065 (the run-wiring item), exactly as item 047 deferred
  to item 049 and item 062 deferred to item 065.
- **No new statistic and no new extractor.** It reuses item 046's delta helpers
  and item 059's already-computed intensity statistics (surfaced by item 061);
  it computes no new HU statistic and samples no voxel.
- **No reference-building change.** Item 063 already built the intensity-extended
  artifact; this item only *reads* it.
- **Not item 062's rule.** The absolute/global-band implausible-intensity rule
  (`rule_id = "intensity"`) is item 062, merged; this item neither modifies nor
  duplicates it.

---

## Public interface (the contract item 065 builds on)

```python
# src/segqc/reference/delta.py  (additive; compute_reference_delta UNCHANGED)

INTENSITY_FEATURE_PREFIX = "intensity_"   # tracked-intensity vocabulary marker

def compute_intensity_reference_delta(
    features_block: Mapping,        # item 016/022 features block: label -> level_name join
    image_features: Mapping,        # item 061 build_image_features_block shape: intensity values
    reference: ReferenceDistribution,
    *,
    stratum: str = ALL_STRATUM,
    lower_pct: int = DEFAULT_LOWER_PCT,   # 1
    upper_pct: int = DEFAULT_UPPER_PCT,   # 99
) -> ReferenceDelta: ...
# Serialised with the EXISTING reference_delta_to_dict(delta) (same dataclass shape).
```

```python
# src/segqc/heuristics/intensity_reference_delta.py  (new module, registered in __init__)

DEFAULT_MAX_ROBUST_Z: float = 3.5              # |robust_z| >= this fires (per feature)
DEFAULT_MAX_DISTRIBUTION_DISTANCE: float = 3.0 # distribution_distance >= this fires (per label)
# flag_out_of_range / flag_robust_z / flag_distribution_distance: bool, default True each
# severity: str, default "flagged-for-review"

_OUT_OF_RANGE_TAG = "Level-aware intensity out-of-range:"
_ROBUST_Z_TAG     = "Level-aware intensity robust-z outlier:"
_DISTANCE_TAG     = "Level-aware intensity distribution-distance outlier:"

@register_rule
class IntensityReferenceDeltaRule(Rule):
    rule_id = "intensity_reference_delta"
    def evaluate(self, record, config) -> list[Finding]:
        """Read record["intensity_reference_delta"] (the reference_delta_to_dict
        shape produced by compute_intensity_reference_delta) and emit a Finding
        per fired condition. Returns [] when the block is absent/non-mapping or
        every available label is in its level's intensity distribution. Pure;
        never mutates record; raises ValueError only for an unrecognised
        `severity` config string."""
```

**How the intensity value reaches the compute function.** Item 061's
`build_image_features_block` keys per-label first-order stats as
`per_label[str(label)]["first_order"][<stat>]` with `<stat>` in
`{mean, median, std, min, max, p05, p25, p50, p75, p95, range, iqr, entropy}`.
Item 063 stores the matching reference distributions under the
`intensity_<stat>` names (`INGESTED_INTENSITY_FEATURES`). The compute function
therefore tracks the `intensity_`-prefixed subset of `reference.features` and,
for feature `intensity_<stat>`, reads the case value from
`first_order[<stat>]` (prefix stripped), skipping any `None`/absent value —
exactly as item 046 skips a geometry feature not present for a label. The
label → `level_name` join (needed to pick the correct per-level distribution)
comes from the geometric `features_block["per_label"][…]["level_name"]`, since
item 061's `image_features` entries carry `label` but no `level_name`.

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. Group A tests
`compute_intensity_reference_delta` against a hand-built `image_features` block +
geometric `features_block` + a small hand-built `ReferenceDistribution` (or the
bundled 063 reference) so each metric is hand-checkable. Group B tests
`IntensityReferenceDeltaRule.evaluate` against a hand-built record carrying a
top-level `intensity_reference_delta` block (the `reference_delta_to_dict` shape).
"In its level's distribution" means an `available: true` label with no
out-of-range feature, every `abs(robust_z) < max_robust_z`, and
`distribution_distance < max_distribution_distance`._

### A. Intensity delta computation (`src/segqc/reference/delta.py`)

- [ ] **AC1: `compute_reference_delta` (geometry) is unchanged and intensity-inert.**
      `compute_reference_delta(features_block, reference)` for a geometric
      `features_block` against the intensity-extended bundled reference produces
      **no** `intensity_*` feature in any label's `features` or
      `out_of_range_features` (its behaviour is byte-identical to before this
      item), and `delta.py`'s `compute_reference_delta` source is not modified.

- [ ] **AC2: `compute_intensity_reference_delta` scores each label's intensity
      value against its own level.** For a `features_block` mapping label→level and
      an `image_features` block whose `first_order` values match a level's
      reference intensity distribution, the returned `ReferenceDelta.per_label`
      entry for that label is `available: true` and carries one `FeatureDelta` per
      tracked `intensity_*` feature present, each with `out_of_range == False` and
      a small `robust_z`.

- [ ] **AC3: the feature value equals the `image_features` first-order value.**
      For a tracked feature `intensity_median`, the emitted `FeatureDelta.value`
      equals `image_features["per_label"][str(label)]["first_order"]["median"]`
      for that label (the `intensity_` prefix is stripped to index `first_order`).

- [ ] **AC4: the lookup is level-aware.** A given intensity value that lies
      **inside** level A's reference band but **outside** level B's band produces
      `out_of_range == False` when the label is assigned level A and
      `out_of_range == True` when the same value is assigned level B — i.e. the
      per-level distribution (`reference.levels[level_name]`), not a global band,
      decides.

- [ ] **AC5: an out-of-band intensity value flags out-of-range.** For a label
      whose `intensity_<stat>` value falls below its level's `p{lower_pct}` (or
      above its `p{upper_pct}`), that feature's `FeatureDelta.out_of_range` is
      `True` and the feature name appears in the label's `out_of_range_features`
      (sorted).

- [ ] **AC6: a large deviation yields a large robust-z and RMS distribution
      distance.** For a label with an intensity value many robust-sigma from its
      level's `p50`, the feature's `robust_z` has the expected sign and magnitude
      (`(value - p50) / (IQR / IQR_TO_SIGMA)`), and the label's
      `distribution_distance` equals the RMS of its features' defined `robust_z`
      values.

- [ ] **AC7: a label whose level (or stratum) is absent from the reference is
      `available: false`.** A label whose `level_name` has no entry in
      `reference.levels` (or no `stratum`) yields a `LabelDelta` with
      `available == False`, empty `features`, `distribution_distance is None`, and
      empty `out_of_range_features` — never a raise.

- [ ] **AC8: a reference with no intensity distributions yields empty intensity
      features.** `compute_intensity_reference_delta` against a geometry-only
      reference (no `intensity_*` in `reference.features`) returns a
      `ReferenceDelta` whose every `available: true` label carries **zero**
      `FeatureDelta`s (nothing to score) and `distribution_distance is None` —
      the backward-compatibility path.

- [ ] **AC9: a missing/`None` first-order value contributes no feature.** For a
      label whose `first_order` lacks a tracked stat or holds `None` for it (item
      061 emits `None` for a sentinel `LabelIntensity`), the corresponding
      `intensity_<stat>` feature is **absent** from that label's `features`
      (never scored as `None`), while its other intensity features are still
      scored.

- [ ] **AC10: an unavailable `image_features` block yields no intensity scores.**
      When `image_features` is absent, non-mapping, or `available: false`, every
      label in the result carries zero intensity `FeatureDelta`s (the function
      does not raise), so the block is a well-formed no-op.

- [ ] **AC11: `compute_intensity_reference_delta` is deterministic and
      non-mutating.** Two calls on the same inputs produce equal `ReferenceDelta`s
      and byte-identical `json.dumps(reference_delta_to_dict(delta),
      sort_keys=True)`; neither `features_block`, `image_features`, nor
      `reference` is mutated. (Pure: no file I/O, no wall clock, no NumPy import —
      the module's existing contract is preserved.)

### B. Intensity delta rule (`src/segqc/heuristics/intensity_reference_delta.py`)

- [ ] **AC12: the rule is registered and discoverable.**
      `segqc.heuristics.get_rule("intensity_reference_delta")` returns a `Rule`
      instance whose `rule_id == "intensity_reference_delta"`, and `iter_rules()`
      yields exactly one rule with that id.

- [ ] **AC13: an in-distribution intensity produces no finding.** For a record
      whose `intensity_reference_delta.per_label` holds one `available: true`
      label with `out_of_range_features == []`, every feature
      `abs(robust_z) < max_robust_z`, and `distribution_distance <
      max_distribution_distance`, `evaluate` returns `[]`.

- [ ] **AC14: an out-of-range intensity feature fires an out-of-range finding.**
      For a label whose block lists an `intensity_*` feature in
      `out_of_range_features` (with `flag_out_of_range` at its default `True`),
      `evaluate` returns exactly one `Finding` whose `rule_id ==
      "intensity_reference_delta"`, `labels == frozenset({label})`, and whose
      `reason` starts with `"Level-aware intensity out-of-range:"`.

- [ ] **AC15: a large robust-z fires a robust-z finding.** For a label with an
      `intensity_*` feature whose `abs(robust_z) >= max_robust_z` (default `3.5`)
      but `out_of_range == false` and `distribution_distance <
      max_distribution_distance` (isolating the condition), `evaluate` returns
      exactly one `Finding` for that label whose `reason` starts with
      `"Level-aware intensity robust-z outlier:"` and names the offending feature.

- [ ] **AC16: a large distribution-distance fires a label-level finding.** For a
      label whose `distribution_distance >= max_distribution_distance` (default
      `3.0`) — with no out-of-range feature and every `abs(robust_z) <
      max_robust_z` isolating the condition — `evaluate` returns exactly one
      `Finding` attributed to that label whose `reason` starts with
      `"Level-aware intensity distribution-distance outlier:"`.

- [ ] **AC17: the robust-z threshold is read from config.** A feature whose
      `abs(robust_z)` is `4.0` fires with the default `max_robust_z`; the same
      record with `rules.intensity_reference_delta.params.max_robust_z = 10.0`
      produces **no** robust-z finding, while `= 1.0` fires — the threshold comes
      from `config.rule_param`, not a hard-coded literal.

- [ ] **AC18: the distribution-distance threshold is read from config.** A label
      whose `distribution_distance` is `4.0` fires the distance condition at the
      default; with `rules.intensity_reference_delta.params.max_distribution_
      distance = 10.0` it does not, while `= 1.0` it does.

- [ ] **AC19: each firing condition is independently toggleable.** With
      `flag_out_of_range = False` a label whose only anomaly is an out-of-range
      feature produces no finding; with `flag_robust_z = False` a label whose only
      anomaly is a large `robust_z` produces none; with
      `flag_distribution_distance = False` a label whose only anomaly is a large
      distance produces none — and in each case the other two conditions still
      fire on a label that triggers them.

- [ ] **AC20: severity is configurable and an unknown string raises.** With
      `rules.intensity_reference_delta.params.severity = "fail"` every emitted
      `Finding` has `severity == Severity.FAIL`; with the default it is
      `Severity.FLAG`; and `severity = "not-a-severity"` raises `ValueError`
      before/independently of emitting findings.

- [ ] **AC21: an absent/non-mapping block is silent, and an `available: false`
      label produces no finding.** For a record with no `intensity_reference_delta`
      key (the current pipeline default) or a non-mapping value, `evaluate`
      returns `[]` without raising; and a block whose label entry has
      `available: false` yields no finding for that label even when another
      `available: true` label in the same block fires.

- [ ] **AC22: a reference lacking intensity distributions makes the rule inert.**
      For a block computed from a geometry-only reference (every `available: true`
      label carries **empty** `features` / empty `out_of_range_features` / `null`
      `distribution_distance` — the AC8 output), `evaluate` returns `[]` — no
      crash, no spurious flag (the queue's "inert when the loaded reference
      carries no intensity distributions").

- [ ] **AC23: the reason cites the reference and is explainable.** An out-of-range
      `Finding`'s `reason` (a non-empty, non-whitespace string) names the
      offending integer label and its `level_name`, the `intensity_*` feature
      name, the measured `value`, and the reference context (its
      `percentile_rank` and the `(lower_pct, upper_pct)` band) — a
      reference-citing reason mirroring item 047's geometric rule.

- [ ] **AC24: the rule is deterministic, non-mutating, and orders findings
      deterministically.** Two `evaluate` calls on the same `(record, config)`
      return equal finding lists in the same order; a deep before/after comparison
      of `record` shows it unchanged; and for a block firing multiple conditions
      across two labels, findings appear ascending by integer label and, within a
      label, in the fixed order (distribution-distance → out-of-range → robust-z)
      with per-feature findings ascending by feature name — independent of
      `per_label` insertion order.

### C. Engine integration & golden safety

- [ ] **AC25: findings flow through `run_rules` and verdict aggregation.** For a
      firing record, `segqc.heuristics.run_rules(record, config)` includes the
      rule's `Finding`(s), and
      `build_case_result(run_rules(record, config), config).verdict` resolves
      `overall` to at least the finding severity with the offending integer label
      present in the verdict's per-label reasons.

- [ ] **AC26: adding the rule does not perturb existing pipeline output.** A
      record with **no** `intensity_reference_delta` key run through the full
      default registry yields the same findings as before this rule existed (the
      rule contributes nothing), and `src/segqc/default_config.yaml` is unchanged
      by this item so `tests/test_035_default_config.py` and item 042's golden
      snapshots remain green.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete contract is recorded here for audit;
several **pin an interface** item 065 must honour (hand back if reality diverged).

- **ARCHITECTURE — a separate compute function, a separate record key, and a
  separate rule (not an extension of item 046/047's geometric ones).** The queue
  text says "extend the delta-to-reference rule … so intensity features
  participate", but the item **title** is "Level-aware delta-to-reference
  intensity *rule*", and folding intensity into the existing
  `compute_reference_delta` / `ReferenceDeltaRule` / `reference_delta` block would
  (a) change the geometric rule's `distribution_distance` RMS (it would then mix
  geometry + intensity), perturbing item 042/047/049 golden output and violating
  item 063 AC14; (b) force one shared config namespace, threshold set, and reason
  wording across two semantically different judgements; and (c) contradict the
  established Stage-8 precedent — item 062 added a **separate** `IntensityRule`
  rather than extending a sibling. So this item adds
  `compute_intensity_reference_delta` (sibling of `compute_reference_delta`, same
  `delta.py`, reusing its private helpers + dataclasses), a distinct record key
  `intensity_reference_delta`, and a distinct rule `IntensityReferenceDeltaRule`
  (`rule_id = "intensity_reference_delta"`). If a reviewer prefers a single fused
  block/rule, hand back — it is a structural pivot, not a tweak.

- **The rule reads `record["intensity_reference_delta"]`; item 065 injects it.**
  The fixed `Rule.evaluate(record, config)` signature is a rule's only channel.
  **Pinned for 065:** inject
  `record["intensity_reference_delta"] =
  reference_delta_to_dict(compute_intensity_reference_delta(features_block,
  image_features, reference, …))` into the record fed to `run_rules`, **before**
  `run_rules`. Until then the key is absent, so the rule is silently a no-op and
  existing pipeline/golden output is byte-identical at 064 merge (mirrors item
  047's silent-until-049 contract). If 065 nests the block elsewhere or passes
  the reference by another channel, hand back — the rule's read path is this key.

- **Intensity values come from item 061's `image_features` block; the level join
  comes from the geometric `features_block`.** `image_features["per_label"]
  [str(label)]["first_order"][<stat>]` supplies the value; `features_block
  ["per_label"][str(label)]["level_name"]` supplies the level (item 061's
  `image_features` entries carry `label` but no `level_name`, confirmed against
  `build_image_features_block`). `compute_intensity_reference_delta` iterates
  `features_block["per_label"]` (authoritative label→level source, exactly as
  `compute_reference_delta` does) and joins the intensity values in by integer
  label. **Pinned for 065:** the record passed to `run_rules` must already carry
  both a geometric `features_block` and an `image_features` block for a case run
  with a scan (the normal `segqc run` computes the geometric block always; item
  061 adds `image_features`).

- **Tracked-intensity vocabulary = the `intensity_`-prefixed subset of
  `reference.features`; value key = the name with the prefix stripped.** This
  reuses item 063's `INGESTED_INTENSITY_FEATURES` prefix convention
  (`intensity_mean` … `intensity_entropy`, 13 names) without importing the
  constant, keeping the vocabulary self-describing and the coupling one-directional
  (delta reads whatever intensity distributions the reference happens to carry).
  The value for `intensity_<stat>` is `first_order[<stat>]`; the count fields
  (`voxel_count`, `n_nonfinite_excluded`) carry no `intensity_` reference feature,
  so they are never scored. If item 063's prefix convention changed, hand back.

- **Reuse item 046's dataclasses, helpers, and serialiser — no new serialiser.**
  `compute_intensity_reference_delta` returns the existing `ReferenceDelta`
  (with `FeatureDelta` / `LabelDelta`) and is serialised by the existing
  `reference_delta_to_dict`; the block shape is therefore identical to the
  geometric one, and the rule reuses item 047's defensive-read parsing verbatim.
  The `reference_delta_version` field stays `"1.0"` (the two blocks are told
  apart by record key, not by version) — a distinct version marker is unnecessary
  and would be a new constant. If item 065 wants a version discriminator it can
  add one then; not scoped here.

- **Thresholds config-driven with code-side defaults; `default_config.yaml` is
  NOT edited.** `max_robust_z = 3.5`, `max_distribution_distance = 3.0`, three
  `flag_*` toggles default `True`, `severity` default `"flagged-for-review"` —
  all read via `config.rule_param("intensity_reference_delta", …, default=…)`,
  reusing item 047's exact defaults and `_severity_from_param` pattern. Leaving
  the YAML untouched keeps `tests/test_035_default_config.py::
  test_ac2_no_extra_or_missing_rule_ids` and item 042's golden snapshots green
  (the rule is enabled-by-default via the absent-section `rule_enabled` fallback
  and silent without a block). **Pinned for 065:** the run-wiring item owns adding
  the documented `intensity_reference_delta` YAML section and bumping the item-035
  id-set expectation (with the test-writer), exactly as item 049 did for
  `reference_delta` and item 065 does for `intensity`.

- **The rule is inert when the reference carried no intensity distributions.**
  With a geometry-only reference, `compute_intensity_reference_delta` produces a
  block whose available labels have empty intensity `features`, empty
  `out_of_range_features`, and `null` `distribution_distance` (AC8), so the rule
  emits nothing (AC22) with no special-casing — the empty lists simply produce no
  findings. This realises the queue's "inert when the loaded reference carries no
  intensity distributions (backward compatibility)".

- **`rule_id = "intensity_reference_delta"`; new module registered like its
  siblings.** New file `src/segqc/heuristics/intensity_reference_delta.py`,
  registered by a one-line `from segqc.heuristics import intensity_reference_delta
  # noqa: F401` in `src/segqc/heuristics/__init__.py` after the `intensity` import
  line, exactly as items 027–033/047/062 register. The id is distinct from the
  nine existing ids (`bounds`, `fragmentation`, `coverage`, `sequence`, `border`,
  `overlap`, `mislabel`, `reference_delta`, `intensity`); no test asserts the
  registry's exact size, so registering a tenth rule is safe.

- **Reason tags are intensity-specific.** `"Level-aware intensity out-of-range:"`
  / `"Level-aware intensity robust-z outlier:"` / `"Level-aware intensity
  distribution-distance outlier:"` — distinct from item 047's `"Reference …"`
  tags so a reader (and the tests) can tell the two reference-delta families
  apart. The out-of-range reason additionally names value, percentile-rank, and
  the `(lower_pct, upper_pct)` band (AC23), mirroring item 047.

- **Pinned upstream interfaces (hand back if reality diverged):**
  - **Item 063 (✅)** — the intensity-extended reference: `bundled_default_
    reference()` loads `schema_version == "1.1"` with `intensity_*` in
    `reference.features` and per-level `feature_stats["intensity_<stat>"]`
    (`FeatureStats` with `count/mean/std/min/max/percentiles`), plus the
    `INGESTED_INTENSITY_FEATURES` vocabulary/prefix.
  - **Item 061 (✅)** — `build_image_features_block(...)` → `{"available": bool,
    "per_label": {str(label): {"label": int, "first_order": {mean, median, std,
    min, max, p05, p25, p50, p75, p95, range, iqr, entropy}, "extended": {…}}}}`;
    a sentinel stat is `None`.
  - **Item 046 (✅)** — `delta.py`'s `ReferenceDelta` / `LabelDelta` /
    `FeatureDelta`, `_feature_delta`, `_percentile_rank`, `_distribution_distance`,
    `_percentile`-grid handling, `reference_delta_to_dict`, `REFERENCE_DELTA_
    VERSION`, `DEFAULT_LOWER_PCT`/`DEFAULT_UPPER_PCT`, `IQR_TO_SIGMA`, `ALL_STRATUM`;
    and the pure/no-mutation/no-NumPy module contract.
  - **Item 047 (✅)** — the `ReferenceDeltaRule` pattern this rule mirrors
    (severity helper `_LABEL_TO_SEVERITY` / `_severity_from_param`, config-param
    reads, defensive `isinstance`/`.get`, deterministic ordering).
  - **Items 026/034 (✅)** — `Rule`, `register_rule`, `get_rule`, `iter_rules`,
    `run_rules`, `Finding`, `build_case_result`, `Severity`.

## Implementation Steps

Intended code path (all under `source_dir = src/segqc`): edit
`reference/delta.py` (additive: new function + one constant), add new
`heuristics/intensity_reference_delta.py`, and add one registering import to
`heuristics/__init__.py`. **Do not** edit `reference/delta.py`'s existing
`compute_reference_delta`, `reference/schema.py`, `reference/ingest.py`,
`reference/aggregate.py`, `reference/artifact.py`, `heuristics/reference_delta.py`,
`heuristics/intensity.py`, `config.py`, `default_config.yaml`, `report.py`,
`pipeline.py`, or `cli.py`; **do not** touch any committed artifact or fixture.

1. **`reference/delta.py` — compute function.**
   1. Add `INTENSITY_FEATURE_PREFIX = "intensity_"` and export it + the new
      function in `__all__`.
   2. Add a private helper `_intensity_case_values(image_entry, tracked_intensity)`
      that, given one label's `image_features` per-label entry and the tracked
      `intensity_*` names, returns `{name: first_order[name[len(prefix):]]}` for
      each tracked name whose `first_order` value is present and not `None`
      (skips missing/`None`; never inserts `None`).
   3. Add `compute_intensity_reference_delta(features_block, image_features,
      reference, *, stratum=ALL_STRATUM, lower_pct=DEFAULT_LOWER_PCT,
      upper_pct=DEFAULT_UPPER_PCT) -> ReferenceDelta`:
      - Validate `lower_pct`/`upper_pct` against `reference.percentiles` (raise
        `ValueError` as `compute_reference_delta` does).
      - `tracked_intensity = tuple(sorted(n for n in reference.features if
        n.startswith(INTENSITY_FEATURE_PREFIX)))`.
      - Build `image_by_label = {int(label): first_order}` from
        `image_features["per_label"]` **only when** `image_features` is a mapping
        with `available` truthy and a mapping `per_label`; else `{}` (AC10).
      - Iterate `features_block["per_label"]` (label + `level_name`), exactly as
        `compute_reference_delta` does: absent level/stratum ⇒ `available=False`
        `LabelDelta` (AC7). Otherwise build `case_values =
        _intensity_case_values(image_by_label.get(label, {}), tracked_intensity)`
        and, for each tracked intensity feature present in both `case_values` and
        the level's `feature_stats`, append a `_feature_delta(...)` (reusing the
        item-046 helper) — giving `robust_z`, `out_of_range`, `percentile_rank`,
        `distribution_distance` for free.
      - Assemble the `ReferenceDelta` exactly as `compute_reference_delta` does
        (same `reference_delta_version`, `stratum`, `lower_pct`, `upper_pct`,
        `per_label`).
   4. **Leave `compute_reference_delta` byte-identical** (AC1).

2. **`heuristics/intensity_reference_delta.py` — new rule module.** Copy the
   structure of `heuristics/reference_delta.py` (item 047) and change: `rule_id
   = "intensity_reference_delta"`, the three reason tags to the `"Level-aware
   intensity …"` strings, the record key read to `record.get("intensity_
   reference_delta")`, and the severity-error message to name this rule. Keep the
   three config-toggleable conditions (distribution-distance → out-of-range →
   robust-z), the up-front severity read/validate, the defensive parsing, the
   ascending-label / fixed-condition / ascending-feature ordering, and the
   `DEFAULT_MAX_ROBUST_Z = 3.5` / `DEFAULT_MAX_DISTRIBUTION_DISTANCE = 3.0`
   defaults. Never mutate `record`.

3. **`heuristics/__init__.py` — register.** Add `from segqc.heuristics import
   intensity_reference_delta  # noqa: F401 — registers IntensityReferenceDeltaRule
   (item 064)` after the `intensity` import line. No `__all__` change (sibling rule
   modules are not re-exported).

4. **Do not** wire the block into `segqc run`, add a CLI knob, or edit
   `default_config.yaml` (all item 065); keep every change additive and
   behaviour-preserving when the record has no `intensity_reference_delta` key.

## Testing Strategy

- **Framework:** `pytest`. Two new modules:
  `tests/test_064_intensity_reference_delta_compute.py` (Group A, in the style of
  `tests/test_046_*`) and `tests/test_064_intensity_reference_delta_rule.py`
  (Group B/C, in the style of `tests/test_047_reference_delta_rule.py`, including
  the `_RULES` snapshot/restore registry fixture so registration does not leak).
- **Group A inputs** are hand-built: a tiny `ReferenceDistribution` (or the
  bundled 063 reference) with two levels carrying divergent `intensity_median`
  distributions; a geometric `features_block` mapping labels→levels; and an
  `image_features` block (the `build_image_features_block` shape) with chosen
  `first_order` values, so every metric is hand-checkable. One test may build the
  block for real via `build_image_features_block(compute_intensity_features(...))`
  on an item-058 painted fixture to confirm the genuine 061 shape is consumed.
- **Group B inputs** are hand-built records carrying a top-level
  `intensity_reference_delta` block (the `reference_delta_to_dict` shape) with
  chosen `available` / `distribution_distance` / `out_of_range_features` /
  `features[name] = {value, robust_z, percentile_rank, out_of_range, z_score}`,
  plus a `HeuristicConfig` via `default_config()` or crafted
  `rules.intensity_reference_delta.params`.
- **One focused test per AC (AC1–AC26).**
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty block** — `intensity_reference_delta` present with `per_label == {}`
    ⇒ `[]`.
  - **Malformed sub-entries** — a non-dict label entry, an entry missing
    `features`, a non-list `out_of_range_features`, a feature whose `robust_z` is
    `null` — all tolerated (skipped, no crash), matching item 047.
  - **Value exactly on threshold** — `abs(robust_z) == max_robust_z` fires
    (inclusive `>=`); `distribution_distance == max_distribution_distance` fires.
  - **Level-aware isolation** — the same numeric value scored against two levels
    gives opposite out-of-range verdicts (AC4 positive+negative in one test).
  - **Sentinel intensity** — a `first_order` with `median: null` omits the
    `intensity_median` feature but scores its siblings (AC9).
  - **Mixed availability** — an `available: false` label alongside a firing
    `available: true` label emits only the latter's findings (AC21 positive
    control).
  - **All three conditions on one label** — emits distance, then out-of-range,
    then robust-z in that fixed order (AC24 within a label).
  - **Determinism / non-mutation** — deep-copy the record and the compute inputs
    before the call and assert equality afterward; assert byte-identical
    `reference_delta_to_dict` JSON across two compute calls (AC11) and equal
    finding lists across two `evaluate` calls (AC24).
  - **Golden safety** — a record with no `intensity_reference_delta` key run
    through the full default registry yields the pre-existing findings (AC26);
    confirm `default_config.yaml` is unmodified in the diff.
  - **Existing suites** (`test_042` golden, `test_046`, `test_047`, `test_063`)
    stay green: `compute_reference_delta` is untouched, no artifact/fixture/config
    changes, and the rule is silent without a block.

## Dependencies

- **Item 063 (✅ merged) — REQUIRED.** The intensity-extended reference artifact
  this rule grounds against: `bundled_default_reference()` carrying
  `schema_version "1.1"`, `intensity_*` in `reference.features`, and per-level
  `feature_stats` for the tracked intensity features (`INGESTED_INTENSITY_
  FEATURES`). This item only *reads* it.
- **Item 061 (✅ merged) — REQUIRED.** The `image_features` block
  (`build_image_features_block` shape, `per_label[str].first_order`) from which
  `compute_intensity_reference_delta` draws the intensity values.
- **Item 046 (✅ merged) — REQUIRED.** `segqc.reference.delta`'s `ReferenceDelta`
  / `LabelDelta` / `FeatureDelta` dataclasses, the `_feature_delta` /
  `_percentile_rank` / `_distribution_distance` helpers, `reference_delta_to_dict`,
  and the module's pure/no-mutation contract — all reused by the new sibling
  compute function.
- **Item 047 (✅ merged) — pattern source, not modified.** The `ReferenceDeltaRule`
  whose structure (severity helper, config-param reads, defensive parsing,
  deterministic ordering, silent-until-wired contract) this rule mirrors.
- **Items 026 / 034 (✅ merged) — used, not modified.** The rule engine (`Rule`,
  `register_rule`, `get_rule`, `iter_rules`, `run_rules`, `Finding`) and verdict
  aggregation (`build_case_result`, `Severity`).
- **Item 062 (✅ merged) — sibling, not called.** The absolute/global-band
  `IntensityRule`; item 064 is its level-aware/reference-relative complement and
  neither imports nor modifies it.
- **Downstream (this item feeds it):** **Item 065** wires
  `record["intensity_reference_delta"] = reference_delta_to_dict(compute_
  intensity_reference_delta(...))` into `segqc run`, adds the documented
  `intensity_reference_delta` section to `default_config.yaml` (updating the
  item-035 id-set expectation), documents the mounted-VerSe intensity-reference
  path, and closes the Stage-8 acceptance suite.

## Decisions & Trade-offs

Implementation followed the spec's Public Interface and Implementation Steps
without deviation. Notes:

- `compute_intensity_reference_delta` was inserted directly after
  `compute_reference_delta` in `src/segqc/reference/delta.py` (before the
  `_feature_delta_to_dict`/`reference_delta_to_dict` serialisers), and its
  private helper `_intensity_case_values` was inserted directly after
  `_distribution_distance`, keeping every existing line of
  `compute_reference_delta` and its neighbouring helpers byte-identical
  (AC1). Used `collections.abc.Mapping` (aliased `MappingABC`) for the
  `isinstance` mapping checks needed to validate `image_features` (the
  module already imports `typing.Mapping` only for annotations).
- `INTENSITY_FEATURE_PREFIX` and `compute_intensity_reference_delta` are
  exported from both `segqc.reference.delta.__all__` and
  `segqc.reference.__all__` (re-exported at the package level), mirroring
  how `compute_reference_delta` is already re-exported; the tests import
  `compute_intensity_reference_delta`/`INTENSITY_FEATURE_PREFIX` from
  `segqc.reference.delta` directly, so the package-level re-export is an
  additive convenience, not load-bearing for the committed tests.
- `image_by_label` is built by reading each `image_features["per_label"]`
  entry's own `"label"` field (falling back to the dict key) exactly as
  `compute_reference_delta` does for the geometric `features_block`,
  keeping the two compute functions' label-parsing defensiveness
  consistent.
- `heuristics/intensity_reference_delta.py` is a structural copy of
  `heuristics/reference_delta.py` (item 047) with the `rule_id`, the three
  reason tags, the record key (`intensity_reference_delta`), and the
  severity-error message renamed; no other behavioural change. Registered
  via one import line in `src/segqc/heuristics/__init__.py` immediately
  after item 062's `intensity` import.
- `src/segqc/default_config.yaml` was left untouched, as scoped; verified
  via `bundled_default_config()`/rule-registry smoke import that the rule
  registers as the tenth rule id and is enabled by the absent-section
  `rule_enabled` fallback.
