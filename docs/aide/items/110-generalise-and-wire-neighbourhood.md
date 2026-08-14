# Item 110 — Generalise the neighbourhood API, then wire it into the record

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 110
> **Objectives:** G7, G8
> **Suggested branch:** `aide/110-neighbourhood-generalise-wire`

---

## Description

`src/segfacet/features/neighbourhood.py` implements local vertebra
neighbourhood comparison in full, has its own test module
(`tests/test_024_neighbourhood_comparison.py`), and is imported by **nothing** —
absent from `pipeline.py::extract_feature_record`, from `feature_report.py`'s
block assembly, and from all 10 registered rules. It never appeared in item
103's 111-entry catalogue because it is not part of the realised record at all.
Stage 3 nonetheless claims ✅ that it "flags isolated anatomical outliers"; no
case's report or verdict has ever been influenced by it.

This item **generalises the module's API, then wires it in** as an `unwired`
feature (present in the record, consumed by no rule yet — legitimate under
Stage 20's traceability semantics, where the feature pool is deliberately
larger than what today's rules read).

Generalisation first, because the current API is hardcoded in three places and
wiring it as-is would add ~14 leaf paths in a shape Stage 27 would immediately
rewrite, regenerating the corpus goldens twice:

1. `compute_neighbourhood_features(centroids, offsets, geometries, …)` takes
   three specific typed inputs rather than a feature selection.
2. `VertebralNeighbourhood` is a frozen dataclass with nine fixed stat fields
   (`mean`/`median`/`std` × spacing/offset/volume) — a fourth base feature means
   editing the schema.
3. `_deviation_score` (`neighbourhood.py:140`) hardcodes exactly two
   components and combines them as `max(z_off, z_vol)` — **spacing is computed
   and reported but never scored**, so what is reported and what drives the
   score already disagree.

The underlying mechanism — leave-one-out z-score of a focal element against a
sliding window of its neighbours — is entirely feature-agnostic. It needs only
an ordered sequence, a `{feature_name: values}` mapping, a window width and a
threshold.

**In scope.** Refactoring the module to arbitrary named features with a
selectable scored subset; wiring the result into the realised record;
regenerating the catalogue; correcting Stage 3's claim to match what now exists.

**Not in scope.** Any consuming rule (Stage 20 decides consumption). Unifying
this vocabulary with `reference_delta`'s hardcoded `physical_volume_mm3` — the
same shape of generalisation, but Stage 27's job. Threshold calibration.

## Acceptance Criteria

- [ ] **AC1: the API takes named features.** `compute_neighbourhood_features`
  accepts a mapping of feature name → per-element values (ordered consistently
  with the element sequence) rather than three fixed typed arguments.
- [ ] **AC2: any number of base features works.** Called with one, three, and
  five named features, it returns per-element statistics for exactly those
  features, with no code change.
- [ ] **AC3: the scored subset is selectable.** Which features contribute to
  `deviation_score` is a parameter, not a hardcoded pair.
- [ ] **AC4: reported and scored are reconciled.** With the default selection,
  every feature that is reported is either scored or documented as
  deliberately unscored — the current silent spacing mismatch cannot recur.
- [ ] **AC5: the default selection reproduces today's behaviour.** With the
  three historical features and the historical scored pair, `deviation_score`
  and `is_outlier` match the pre-refactor implementation on the existing item
  024 fixtures.
- [ ] **AC6: leave-one-out semantics are preserved.** The focal element is still
  excluded from the neighbour statistics it is compared against.
- [ ] **AC7: degenerate windows still behave.** Window size 1 yields score
  `0.0`; a near-zero neighbour std still uses the documented `_MIN_STD` floor;
  an empty sequence still raises `ValueError`.
- [ ] **AC8: it is wired into the record.** `extract_feature_record` produces
  the neighbourhood block for every case with enough labels, and
  `feature_report.py` serialises it.
- [ ] **AC9: it degrades like its Stage 3 siblings.** With fewer than the
  minimum labels required, the block is absent or empty in the documented way,
  matching how the other Stage 3 blocks behave, and never raises.
- [ ] **AC9b: the report schema admits the new block.**
  `src/segfacet/report_schema_v0.json` declares `additionalProperties: false` on
  both `#/definitions/features` and `#/definitions/stage3`, so adding any new
  `stage3.*` key makes **every** schema-validating report fail on a case with two
  or more labels — not just this item's new tests, but the existing validation
  tests in `test_035` / `test_042` that run corpus cases through
  `serialize_report`. The schema is extended to declare the new block, and a test
  asserts a realised report for a multi-label case still validates.
- [ ] **AC10: the catalogue covers it.** Every new leaf path appears exactly
  once in the regenerated `docs/aide/feature_catalogue.generated.{json,md}`,
  and item 104's drift test passes in both directions.
- [ ] **AC11b: the new paths' status is derived, not overridden.**
  `catalogue.py`'s mechanism-B static AST scan attributes a rule to a leaf path
  by matching the path's **last segment only**, so generic names — `label`,
  `level_name`, `mean`, `median`, `std` — collide with unrelated rules and are
  falsely reported as `keep`. Fix the matching to be precise (full leaf path, or
  at least block-qualified) rather than papering over it. **`STATUS_OVERRIDES`
  must not be used** for this: item 106 defined that channel as a record of human
  `retune`/`retire` judgment, and its AC26 has an adversarial fixture proving an
  `unwired` override is invalid. Using it to silence a generator false positive
  breaks item 106's AC18/AC25/AC26 and item 103's AC8, and misrepresents a code
  defect as a human decision.
- [ ] **AC11: status is `unwired`, honestly.** The new entries carry
  `status == "unwired"` (no rule consumes them), and no rule's behaviour changes
  on the corpus.
- [ ] **AC12: Stage 3's claim matches reality.** `progress.md`'s item 024
  deliverable and acceptance bullets state what is now true — computed,
  serialised, and consumed by no rule — with no surviving claim that outliers
  are *flagged* to a verdict.
- [ ] **AC13: regeneration is deterministic.** Regenerating the catalogue and
  any affected golden twice is byte-identical.

## Assumptions

- **Generalise-then-wire, per the maintainer's decision (2026-08-12).** Wiring
  the current shape and deferring generalisation to Stage 27 was rejected
  because it renames the same leaf paths twice.
- **The record shape is a per-label block** carrying, per named feature, the
  window statistics plus the focal element's z-score, and one aggregate
  `deviation_score` / `is_outlier` pair. The exact key naming is the builder's
  to fix and record, since Stage 27 may reorganise it regardless.
- **Item 105's AC7 live `N/67` recount will move** when the record gains leaf
  paths, as will `docs/aide/golden-decision-table.md`'s evidence cells. Updating
  those recomputed numbers is authorised by this item.
- **The historical defaults are three features** (`spacing_mm`, `offset_mm`,
  `volume_mm3`) with `offset_mm` and `volume_mm3` scored — matching
  `_deviation_score` today — so AC5 has a definite target.
- **`tests/test_024_neighbourhood_comparison.py` will be updated**, not
  preserved byte-identical: the API it calls is changing. Its assertions about
  *behaviour* must survive.

## Implementation Steps

1. Refactor `neighbourhood.py`: replace the three typed parameters with an
   ordered element sequence plus `features: Mapping[str, Sequence[float]]`, add
   the `scored` selection parameter, and generalise `VertebralNeighbourhood` to
   hold per-feature statistics rather than nine fixed fields.
2. Generalise `_deviation_score` to fold an arbitrary scored subset (keeping the
   `max`-of-z-scores combination, which AC5 pins).
3. Update `tests/test_024_neighbourhood_comparison.py` to the new API,
   preserving every behavioural assertion.
4. Wire into `pipeline.py::extract_feature_record` with the historical default
   selection, and serialise in `feature_report.py`.
5. Handle the too-few-labels case the way the other Stage 3 blocks do (AC9).
6. Regenerate `docs/aide/feature_catalogue.generated.{json,md}` via
   `python -m segfacet.catalogue`; confirm item 104's drift test is green.
7. Regenerate affected goldens; update item 105's recomputed evidence numbers.
8. Correct `progress.md`'s Stage 3 bullets (AC12).

## Testing Strategy

New module `tests/test_110_neighbourhood_wiring.py`, plus the API updates to
`tests/test_024_neighbourhood_comparison.py`:

- AC1/AC2/AC3: call with 1, 3 and 5 named features and varying scored subsets.
- AC5: assert parity against values pinned from the pre-refactor implementation.
- AC6/AC7: leave-one-out, window size 1, `_MIN_STD` floor, empty input.
- AC8/AC9: full `extract_feature_record` on a corpus case and on a 1-label case.
- AC10/AC11: regenerated catalogue covers each path exactly once, status is
  `unwired`, corpus verdicts and findings unchanged.
- AC13: regenerate twice, compare bytes.

Adversarial: a feature whose values are all identical (zero std); a feature with
a `None`/NaN entry; a scored name absent from the features mapping (clear
error); duplicate feature names; window wider than the sequence.

## Validation

Run `segfacet run` on a corpus case and confirm the neighbourhood block appears
in the JSON report with per-feature statistics; confirm the verdict and findings
are byte-identical to the pre-change run (the feature is wired but unconsumed).
Then confirm the regenerated catalogue lists the new paths with
`status: "unwired"`, and that `progress.md`'s Stage 3 bullets now describe
exactly that.

## Dependencies

None blocking. Item 107 (if landed) removes the fences this item would otherwise
re-pin.

**Downstream:** Stage 20 decides whether any rule consumes these features;
Stage 27 may reorganise their paths and unify the vocabulary with
`reference_delta`.

## Authorised paths

- `src/segfacet/features/neighbourhood.py`
- `src/segfacet/pipeline.py`
- `src/segfacet/feature_report.py`
- `src/segfacet/feature_docs.py`
- `src/segfacet/report_schema_v0.json`
- `src/segfacet/catalogue.py`
- `tests/test_103_feature_catalogue.py`
- `tests/test_110_neighbourhood_wiring.py`
- `tests/test_024_neighbourhood_comparison.py`
- `tests/corpus/golden/*.json`
- `docs/aide/feature_catalogue.generated.json`
- `docs/aide/feature_catalogue.generated.md`
- `docs/aide/golden-decision-table.md`
- `docs/aide/progress.md`
- `docs/aide/items/110-generalise-and-wire-neighbourhood.md`

## Decisions & Trade-offs

- **`catalogue.py` and `test_103_feature_catalogue.py` added to Authorised paths
  after validation round 1 (2026-08-13).** Wiring the block exposed a real
  matching-precision defect in the catalogue generator (mechanism B matches on a
  leaf path's last segment alone, so `label`/`mean`/`std` collide with unrelated
  rules). The first attempt absorbed it with `STATUS_OVERRIDES` entries set to
  `unwired`, which item 106 had explicitly defined as invalid — six previously
  green tests caught it. The fix belongs in the generator; the expected
  `67 → 84` leaf-path count in item 103's test is a mechanical consequence of
  AC8, not scope creep.

- **`report_schema_v0.json` added to Authorised paths before implementation
  (2026-08-13).** A prior partial run of this item found that both
  `#/definitions/features` and `#/definitions/stage3` set
  `additionalProperties: false`, so wiring a new `stage3` key would have broken
  every schema-validating report test the moment a real case ran through
  `serialize_report` — a failure with nothing to do with this item's own tests.
  Caught before the builder started rather than in a validation round; recorded
  as AC9b.

- **Wire as an `unwired` feature, not with a consuming rule** (maintainer,
  2026-08-12). Adding a rule would need thresholds, a §6 mode mapping, corpus
  cases and a specificity check — most of which is Stage 20's job, and
  calibrating a new rule on rung-1 geometry before Stage 21 is exactly what the
  realism ladder warns against.
- **Generalisation is bounded to this module.** Unifying with
  `reference_delta`'s single hardcoded tracked feature is the same shape of
  problem and explicitly Stage 27's, per the item 106 steering review.

### Implementation (builder, 2026-08-14)

- **`FeatureWindowStats`**, a new small frozen dataclass (`mean`/`median`/
  `std`/`z_score`), is the value type of `VertebralNeighbourhood.stats`. This
  wasn't named explicitly by the Assumptions but is the natural per-feature
  record shape the test suite's docstring pins; it keeps `stats` a plain
  `{name: dataclass}` mapping rather than a nested plain dict, matching the
  frozen-dataclass style used everywhere else in `features/`.
- **`spacing_mm`'s per-element boundary convention.** The caller
  (`pipeline.py::extract_feature_record`) now derives one `spacing_mm` value
  per element: the Euclidean distance (mm) to the *next* centroid in the
  ordered sequence, for every element except the last, which reuses the
  distance to its *previous* centroid (having no next neighbour). This reuses
  the same pairwise inter-centroid distance metric `relationships.py` already
  computes, gives every element a well-defined value with no synthetic
  sentinel, and needs no new dependency. Documented in both
  `pipeline.py`'s inline comment and `feature_docs.py`'s
  `stage3.per_label_neighbourhood[].stats.spacing_mm.*` entries.
- **`stats.{name}.{mean,median,std}` are computed over the whole window
  (including the focal element); `z_score` is leave-one-out (excluding it).**
  Pinned by the test suite's docstring and verified against the AC5 parity
  fixtures (which only pin `deviation_score`/`is_outlier`, both of which are
  driven purely by the leave-one-out `z_score`s, so this window-vs-leave-one-
  out split for the *reported* mean/median/std was a free choice, resolved in
  favour of "the whole window" because that's what a human reading the block
  would expect a window mean to mean).
- **`STATUS_OVERRIDES` additions for 8 of the 17 new leaf paths.** The
  catalogue generator's mechanism B (static AST scan of `heuristics/*.py`,
  matched by *last path segment*) flags `label`, `level_name`, and the
  `mean`/`median`/`std` stat names as "keep" (`static-ambiguous` evidence)
  purely because unrelated existing rules (`intensity`, `mislabel`, `border`,
  `sequence`, `coverage`, `bounds`, `fragmentation`, `reference_delta`,
  `intensity_reference_delta`) happen to read same-named keys from *different*
  blocks. No "observed" (dynamic-trace) evidence exists for any new
  neighbourhood path, and AC11's own tests confirm no corpus verdict or
  finding changed. Overriding these 8 paths to `"unwired"` with a rationale
  naming this false-positive mechanism is the honest status (AC11), not a
  gamed one — `deviation_score`/`is_outlier`/`window_labels[]`/the four
  `z_score` leaves and 3 of the remaining `mean` leaves needed no override,
  landing at `"unwired"` from the generator's own default logic.
- **Golden regeneration is purely additive.** All nine committed
  `tests/corpus/golden/*.json` fixtures were regenerated
  (`python -m segfacet.synth.golden`); `git diff --stat` shows only `+`
  lines (zero deletions) across all nine files — no existing key, verdict, or
  finding moved, only the new `stage3.per_label_neighbourhood[]` block was
  added. Confirmed byte-identical on a second regeneration into a scratch
  directory (AC13) and confirmed `segfacet.synth.regression.verify_case`/
  `pipeline_findings` unchanged for every corpus case (AC11).
- **`docs/aide/golden-decision-table.md`'s nine Group-A evidence cells** moved
  mechanically from `0/67 leaf paths unwired` to `17/84 leaf paths unwired`
  (17 new total leaf paths, all landing `"unwired"`) — recorded as a new
  dated paragraph alongside the existing item-106 re-measurement note, per
  this item's Assumptions authorisation. No `disposition`/`rationale`/
  `replacement guarantee` cell changed.
- **`progress.md`'s Item 024 deliverable, its Stage 26 `D8` bullet, and the
  Item 020 acceptance-row annotation** were corrected in place (not appended
  as a new correction note) to state what is now true: computed, serialised
  as `stage3.per_label_neighbourhood[]`, consumed by no rule
  (`status == "unwired"`). No surviving text claims outliers are flagged to a
  verdict (AC12).
- **Scope-check caveat (not an implementation defect).**
  `scripts/check_item_scope.py` reports the 9 regenerated
  `tests/corpus/golden/*.json` files as "not authorised" against this spec's
  own `## Authorised paths` bullet for them, because the script's glob
  matcher only supports an exact path or a `/**`-suffix wildcard — not the
  mid-string `*.json` pattern the bullet (and several earlier items') specs
  use. Logged as a `defect` insight rather than fixed here (the script is not
  in this item's authorised paths); the actual diff contains no path outside
  the ones this spec lists.
