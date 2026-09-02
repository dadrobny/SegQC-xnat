# Item 129 — Coincident centroids in the pipeline, and the 4-level held-out boundary

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 129
> **Objectives:** G2 (rules reachable on real inputs), G7 (evaluable & regression-testable)
> **Suggested branch:** `aide/129-coincident-centroids-in-the-pipeline`

---

## Description

Two small-centroid-count defects in the spline-offset layer, Stage 29 **D4** and
**D5**. They share a surface (`features/spline_offset.py` and the Stage-3 branch
of `pipeline.py`) and a shape (a level count too low for the fit to say anything),
which is why the queue batched them.

**D4 — a coincident centroid loses the whole case.** `fit_centroid_spline`
already raises a descriptive `ValueError` naming the shared coordinate and both
levels (item 119, AC16). What does not exist is graceful degradation one level
up. Measured 2026-08-31 on a label map with label 22 painted as a concentric core
inside label 21's shell, so both centroids land on `(9.5, 9.5, 19.5)` mm:

```
ValueError: fit_centroid_spline received two centroids with exactly the same
mm-coordinate (9.5, 9.5, 19.5): levels 'L2' and 'L3'. ...
```

propagates straight out of `extract_feature_record`, so `segfacet run` produces a
traceback and **no report at all** — every Stage 1/2 feature and every rule that
does not need Stage 3 is lost along with it. `extract_feature_record` already
knows how to degrade: its `len(labels) >= 2` guard omits the whole `stage3`
sub-block for a one-label case and returns a valid `features_version == "0.1"`
record. This item extends that same guard to the coincident case and, unlike the
one-label path, **records the cause in the record** so a report or a future rule
can name the offending levels instead of the record merely being silently short.

**D5 — the four-level held-out measurement is not held out.**
`compute_leave_one_out_spline_offsets` withholds a level by driving its weight to
`_WITHHELD_WEIGHT = 1e-6` and refitting. With four points and `k = 3` the fit is a
cubic with exactly four coefficients, so it interpolates all four points **whatever
the weights are** — the "held-out" curve is the in-sample curve, and every offset
reads noise about zero. `_MIN_LEVELS_FOR_HELD_OUT` is `4`
(`features/spline_offset.py:161`), so a four-level case takes that path and the
module claims a held-out measurement it did not make. Move the floor to five and
say why in the module docstring, so a four-level case takes the **documented**
in-sample fallback rather than a held-out path that silently is not one.

**What D5 is NOT, and the measurement that settles it.** Queue-018's *Testable*
line and [`../roadmap.md`](../roadmap.md)'s Stage 29 acceptance both expect the
boundary move to make "a 4-level field of view yield non-degenerate held-out
offsets", and to move any four-level VerSe subject "from zero to a real offset",
requiring a reference rebuild and a `max_offset_mm` re-check. **Measured
2026-08-31, that does not follow, and no boundary value can make it follow.** On a
four-point straight sequence with one interior level displaced by a full **15 mm**:

| n | held-out offsets (mm) | in-sample offsets (mm) |
|---|---|---|
| 4 | `[0.0001, 0.0, 0.0, 0.0]` | `[0.0001, 0.0, 0.0, 0.0]` |
| 5 | `[0.45, 1.85, 2.57, 5.58, 0.74]` | `[0.12, 0.52, 1.41, 1.43, 0.37]` |
| 6 | `[15.31, 15.00, 7.13, 4.05, 3.49, 5.45]` | `[0.19, 0.82, 1.78, 1.22, 0.17, 0.24]` |

At `n = 4` **both** paths read zero: the in-sample fallback the boundary move
selects is numerically the same curve the held-out refit already produced (the two
agree to ~1e-13 mm on `mode5_remove_level`, the corpus's only four-level case). So
the boundary move is an **honesty fix with no numeric consequence**: nothing in
`reference_verse_v1.json`, `reference_default.json`, the corpus, or
`mislabel.max_offset_mm` moves, and this item therefore does **not** rebuild any
reference artifact, does **not** re-derive the threshold, and does **not** touch
`tests/test_128_reference_verse_v1_integrity.py`'s digest literal. The only
mechanism that *would* make a four-level FOV measurable is lowering the fit's
degree at small `n` (so a cubic cannot interpolate four points) — a change to the
curve formulation the 2026-08-27 "Spinal curve model — the deformity envelope"
human gate approved, and therefore not an agent's call. See **Assumptions** for the
full record; the stage acceptance line is left for item 135 to record honestly
against this measurement rather than tick.

**What else this is NOT.** No new rule and no verdict change: a coincident-centroid
case degrades to a report, and whether that should *also* raise a finding is a
separate decision (captured in [`insights.md`](../insights.md), not acted on here).
`fit_centroid_spline`'s raise is unchanged — the fit is right to refuse; only its
caller was wrong to die. No closest-point-search or double-fit consolidation
(item 130), no `tangent_angles_deg[]` work (item 131), no monotonicity change
(item 132). No golden snapshot is regenerated or referenced: item 126 retired
them.

## Acceptance Criteria

### D4 — coincident centroids degrade instead of raising

- [ ] **AC1: the coincidence check is a public helper.**
  `segfacet.features.spline` exports `find_coincident_centroid_pair`, and it is
  listed in that module's `__all__`.

- [ ] **AC2: the helper names the first coincident pair deterministically.**
  Given a sequence carrying two centroids on the same mm-coordinate,
  `find_coincident_centroid_pair` returns the shared coordinate as a
  `tuple[float, float, float]` together with both level names and both integer
  labels, taking the **first** such pair in the order the sequence was given;
  two calls on the same input return equal results.

- [ ] **AC3: the helper returns `None` when no pair is coincident.**
  `find_coincident_centroid_pair` returns `None` for a sequence whose
  mm-coordinates are pairwise distinct, including one whose closest pair differs
  by only `1e-9` mm.

- [ ] **AC4: `fit_centroid_spline`'s error is unchanged.**
  `fit_centroid_spline` still raises `ValueError` on an exactly-coincident pair,
  and its message still contains the shared coordinate and both level names —
  the item-119 AC16 behaviour is reused by the helper, not replaced.

- [ ] **AC5: `extract_feature_record` no longer raises on coincident centroids.**
  On a label map with two labels sharing an exact centroid,
  `extract_feature_record` returns a `dict` rather than raising.

- [ ] **AC6: the degraded record omits the Stage 3 block.** That returned record
  has no `"stage3"` key, and its `features_version` is `"0.1"`.

- [ ] **AC7: the degraded record carries every Stage 1/2 feature.** That record's
  `per_label` has one entry per non-zero label in the map, each carrying its
  `geometry`, `components` and `centroid` sub-blocks, and the record carries
  `relationships` and `overlaps` keys — i.e. nothing outside Stage 3 was lost.

- [ ] **AC8: the record records the cause.** That record carries a
  `stage3_unavailable` mapping whose `reason` is the exact string
  `"coincident_centroids"`, whose `levels` lists both coincident level names in
  the order the helper reports them, whose `labels` lists both integer labels,
  whose `coordinate_mm` is the shared coordinate as a 3-element list of floats,
  and whose `detail` is a single-line human-readable string naming both levels
  and the coordinate.

- [ ] **AC9: the key is absent when Stage 3 succeeds.** For `clean_control` (and
  for a one-label map, and for an empty map), the record `extract_feature_record`
  returns has **no** `stage3_unavailable` key at all.

- [ ] **AC10: the degradation is deterministic.** Two `extract_feature_record`
  calls on the same coincident label map return equal records.

- [ ] **AC11: the input image is not mutated.** The seg image's voxel array is
  byte-identical before and after the degraded `extract_feature_record` call.

- [ ] **AC12: the report schema admits the key.** `serialize_report` (which
  validates against `src/segfacet/report_schema_v0.json` on every call) accepts a
  report whose `features` block carries `stage3_unavailable`, and the schema's
  `features` definition lists it as an optional property with a description.

- [ ] **AC13: the schema still rejects an unknown key.** A `features` block
  carrying an invented key (e.g. `"stage3_unavailble"`) still fails validation —
  `additionalProperties: false` was widened by exactly one named property, not
  relaxed.

- [ ] **AC14: `run_qc` produces a verdict for the degraded case.** `run_qc` on the
  coincident label map returns a `(CaseResult, features_block)` pair without
  raising, and `features_block["stage3_unavailable"]["reason"] ==
  "coincident_centroids"`.

- [ ] **AC15: the human report names the coincident levels.**
  `render_human_report` called with that features block emits a section whose body
  contains both coincident level names and the shared coordinate.

- [ ] **AC16: the human report is byte-identical when the key is absent.** For a
  features block with no `stage3_unavailable` key, `render_human_report`'s output
  is character-for-character equal to what it returns for the same inputs with the
  new code path unreachable — asserted by rendering `clean_control` and checking
  the string contains no degradation-section header.

- [ ] **AC17: `segfacet run --no-reference` yields a report, not a traceback.**
  Invoked through the CLI entry point on the coincident label map with
  `--no-reference`, the command exits `0`, writes both the JSON and the plain-text
  report, and the plain-text report contains both coincident level names.

- [ ] **AC18: `segfacet run` with the default reference also survives.** The same
  invocation **without** `--no-reference` (so the bundled production reference is
  loaded and a reference delta computed) also exits `0` and writes both reports —
  the reference/delta path tolerates a record with no `stage3`.

- [ ] **AC19: the exactly-coincident fixture exercises the real path.**
  `tests/test_122_signed_curvature.py` no longer contains a test named
  `test_adv_all_centroids_coincident_no_crash_finite` whose body builds
  near-coincident centroids: the surviving near-coincident test is named for the
  `1e-6` mm perturbation it actually uses, and the exactly-coincident input is
  exercised in this item's own module through `extract_feature_record`.

- [ ] **AC20: the catalogue does not move.** `build_catalogue()`'s realised leaf
  paths are unchanged by this item — no driver record in
  `catalogue.iter_driver_records()` realises `stage3_unavailable`, so
  `docs/aide/feature_catalogue.generated.json` and `.md` are byte-identical to
  their pre-item bytes and `tests/test_104_*`'s drift test still agrees.

### D5 — the held-out floor moves to five levels

- [ ] **AC21: the boundary is five.**
  `segfacet.features.spline_offset._MIN_LEVELS_FOR_HELD_OUT == 5`.

- [ ] **AC22: four levels take the in-sample fallback.** For a four-centroid
  sequence, `compute_leave_one_out_spline_offsets(centroids, spacing_mm=s)`
  returns a list **equal** to `compute_spline_offsets(centroids,
  fit_centroid_spline(centroids), spacing_mm=s)` — the same equality
  `test_120`'s AC7 asserts at two and three levels.

- [ ] **AC23: five levels still take the held-out path.** For a five-centroid
  sequence with one displaced interior level, `compute_leave_one_out_spline_offsets`
  returns a list **not** equal to the in-sample list, and the displaced level's
  held-out `offset_mm` strictly exceeds its in-sample `offset_mm`.

- [ ] **AC24: `test_120`'s fallback parametrisation covers four.**
  `tests/test_120_leave_one_out_offset.py`'s fewer-than-the-floor fallback test is
  parametrised over `2, 3, 4` and passes at each.

- [ ] **AC25: the docstring states the floor and why.**
  `features/spline_offset.py`'s module docstring states that five levels is the
  floor for the held-out path, and gives the reason: with four points and `k = 3`
  the fit is a cubic with four coefficients, so it interpolates all four points
  regardless of the weights and the "withheld" level still shapes its own curve.

- [ ] **AC26: the limitation is recorded with its measurement.** That same
  docstring records that at four levels an interior level displaced by 15 mm still
  reads an offset below `0.001` mm, so a four-level field of view cannot raise a
  `mislabel` offset finding under any threshold — and that closing that gap needs
  a change to the fit's degree, which the deformity-envelope human gate governs.

- [ ] **AC27: the four-level blind spot is asserted, not only documented.** A test
  builds a four-centroid sequence with one interior level displaced 15 mm and
  asserts every returned `offset_mm` is below `0.001` mm — so the day the
  formulation changes, this test fails and the docstring is forced current.

- [ ] **AC28: the corpus's four-level case is numerically unmoved.** For
  `mode5_remove_level` (the corpus's only four-level case), every
  `stage3.per_label_offsets[*].offset_mm` from a fresh `extract_feature_record` is
  within `1e-9` mm of the pre-item value, and all four remain below
  `mislabel`'s `max_offset_mm`.

- [ ] **AC29: no corpus case changes its findings.** For every case in
  `tests/corpus/manifest.json`, the set of `(rule_id, tuple(labels))` pairs
  `run_qc` returns is equal to the set it returned before this item.

### The artifacts this item deliberately leaves alone

- [ ] **AC30: the released VerSe artifact is untouched.**
  `tests/test_128_reference_verse_v1_integrity.py`'s
  `_RELEASED_REFERENCE_VERSE_V1_SHA256` literal is unchanged and still matches
  `src/segfacet/reference/reference_verse_v1.json`'s bytes.

- [ ] **AC31: the default artifact still matches a fresh build.** A fresh
  `build_and_write_default` into `tmp_path` compares equal to the committed
  `src/segfacet/reference/reference_default.json` under
  `segfacet.synth.golden.assert_matches_committed_artifact` (item 127's
  tolerance helper). **Revised 2026-08-31:** the committed artifact *was*
  regenerated (see the dated Decisions & Trade-offs entry) because
  `tests/test_063_reference_intensity.py::
  test_ac13_default_cohort_geometric_stats_identical_on_off_intensity`
  compares `bundled_default_reference()` (the committed artifact, loaded)
  against a fresh `build_reference(..., with_intensity=False)` under exact
  `FeatureStats.__eq__`, not item 127's tolerance helper — a consumer this
  item's original AC31 text did not survey. Regeneration is the fix; AC31
  itself still holds, now trivially, since the committed bytes are the
  fresh-build bytes.

- [ ] **AC32: the calibrated threshold is unchanged.**
  `heuristics.mislabel._DEFAULT_MAX_OFFSET_MM == 13.0`, it still equals
  `derive_max_offset_mm(bundled_production_reference())`, and
  `src/segfacet/default_config.yaml`'s `rules.mislabel.max_offset_mm` still
  agrees with it.

- [ ] **AC33: no new byte-exact committed-artifact comparison is introduced.**
  `committed_artifact_guard.iter_violations` over `tests/` yields zero violations
  on the post-item tree, and `tests/committed_artifact_guard.py` does not appear
  in this item's diff.

- [ ] **AC34: no retired golden path is referenced.** No file this item adds or
  edits contains the string `tests/corpus/golden/` or the literal paths
  `tests/golden/016_features_report.json` / `tests/golden/022_stage3_report.json`.

## Assumptions

- **The queue's stated D5 outcome is unachievable by the mechanism it
  prescribes, and the mechanism wins.** Queue-018's item-129 *Testable* line and
  `roadmap.md`'s Stage 29 acceptance both say a four-level field of view will
  yield non-degenerate held-out offsets, and that four-level VerSe subjects move
  "from zero to a real offset", requiring a reference rebuild and a
  `max_offset_mm` re-check. Measured 2026-08-31 (the table in the Description),
  a four-point cubic interpolates whatever the weights are, so the in-sample
  fallback the boundary move selects reads the same near-zero offsets the
  held-out path already returned — agreeing to ~1e-13 mm on the corpus's
  four-level case. The boundary move therefore lands as specified and the
  rebuild/re-derivation half is **out of scope**, because it would regenerate
  two committed artifacts and move a human-calibrated threshold to chase a
  change of ~1e-13 mm. Recorded here for the validator to surface at the queue
  boundary.
- **Stage 29's acceptance line "a 4-level field of view yields non-degenerate
  held-out offsets" is not met by this item, and item 135 should record it unmet
  with this measurement rather than tick it.** The precedent is Stage 28, which
  closed with two acceptance criteria honestly unticked and their evidence
  recorded (`progress.md`). The only mechanism that would meet it — clamping the
  spline degree below `n - 1` at small `n`, so four points cannot be
  interpolated — changes the curve formulation the 2026-08-27 "Spinal curve model
  — the deformity envelope" human gate approved ("smoothing_spline at
  `s = n_points`, chord-length `u`, leave-one-out evaluation"), and no agent may
  make that call. **No new gate row is raised:** nothing is blocked — item 129 and
  item 135 both proceed honestly — and a gate row whose `Blocks` names work that
  can complete would be a false blocker. The question is captured in
  [`insights.md`](../insights.md) for triage at the queue boundary.
- **`reference_default.json` is not regenerated — superseded 2026-08-31, see
  Decisions & Trade-offs.** Two of the five subjects in `reference/artifact.py`'s
  `_DEFAULT_COHORT_RECIPE` (`default-sub-001`, `default-sub-002`) carry exactly
  four levels, so their `spline_offset_mm` contributions shift by ~1e-13 mm under
  the code-path change. That is far inside the tolerance item 078/127 established
  for fresh-vs-committed comparison via `assert_matches_committed_artifact` — but
  `test_063_reference_intensity.py`'s AC13 consumer compares the committed
  artifact against a fresh build under *exact* `FeatureStats.__eq__`, not that
  tolerance helper, and does not survive a ~1e-13 mm shift. The committed artifact
  was regenerated to keep that exact-equality consumer green; see the dated
  Decisions & Trade-offs entry for the reconciliation.
- **`reference_verse_v1.json` is not rebuilt.** It is not regenerable in CI, its
  rebuild needs the machine-local VerSe19 cohort, and by the same measurement its
  four-level subjects' contributions move by ~1e-13 mm. Rebuilding would move a
  sha256 pin (`test_128`) for noise, and would re-open the threshold derivation
  (`test_123`'s AC12 binds `_DEFAULT_MAX_OFFSET_MM` to
  `derive_max_offset_mm(bundled_production_reference())`) for no measurable cause.
  The cohort **is** reachable on this machine (`ls dataset-verse19training`
  resolves), so this is a scope decision, not an environment downgrade.
- **The cause is recorded as `features["stage3_unavailable"]`, present only when
  Stage 3 was attempted and failed.** Emitting it unconditionally would realise a
  new leaf path in `catalogue.build_catalogue()`, forcing `FEATURE_DOCS` entries
  and a catalogue regeneration (which item 131 already owns for a different
  reason). Keeping it conditional means no committed driver record realises it, so
  the catalogue does not move (AC20). It is a **diagnostic status, not a
  feature**; if a future rule consumes it, that item gives it a `FEATURE_DOCS`
  entry then.
- **`features_version` stays `"0.1"` on a degraded record and
  `_REPORT_SCHEMA_VERSION` stays `"0.1"`.** The version discriminator is promoted
  to `"0.2"` only when a `stage3` block is present (`feature_report.py`), which is
  exactly what a degraded record lacks — the one-label degenerate path already
  reads `"0.1"`. Adding an optional property to the report schema is
  backward-compatible for every already-committed report, which is how the Stage 3
  block itself was added without a report-schema bump.
- **The pipeline pre-checks rather than catching `ValueError`.**
  `extract_feature_record` calls `find_coincident_centroid_pair` before attempting
  the Stage 3 fit, so it degrades only for the cause it can name and any other
  `ValueError` from the fit still propagates. Catching broadly would silently
  convert unrelated failures into a "coincident centroids" claim.
- **Only the first coincident pair is reported.** `_find_coincident_pair` already
  returns the first pair in input order and the pipeline's `ordered_centroids` is
  in ascending-label order, so the report is deterministic. A map with three or
  more mutually coincident labels names one pair; enumerating all of them is not
  in scope and does not change the degradation.
- **No new rule and no verdict change.** A coincident-centroid case keeps the
  verdict its Stage 1/2 rules produce. Whether Stage-3 unavailability should
  itself be a finding is a real question and is captured in `insights.md`, not
  decided here.
- **`aide check --queue 018` reports one `changes-pinned-state` error against this
  item, and it is the known landed-item false positive.** Item 126 (✅, merged)
  lists `src/segfacet/report_schema_v0.json` under `Asserts against` as "the
  validation contract AC3/AC6 check fresh reports against", so the rule flags item
  129's `May change` on that file. Item 126's pin is on the *contract*, not the
  bytes: its AC3 and AC6 assert that `build_report_for_case(case)` output
  validates against the schema, and step 4 here widens `features` by exactly one
  **optional** property while leaving `features`' `required` list untouched — so
  every report item 126 validates still validates, and AC13 proves
  `additionalProperties: false` was not relaxed. The builder should confirm that
  by running item 126's two tests, not by narrowing this item's scope. The rule
  comparing already-merged items is the framework defect recorded in
  [`insights.md`](../insights.md) on 2026-08-31.
- **Item 130 will consolidate this layer.** This item adds one public helper to
  `features/spline.py` and one guard branch to `pipeline.py`; item 130's
  closest-point/single-fit consolidation touches the same two files. Nothing here
  depends on 130 having landed, and 130's consolidation should carry the guard
  across unchanged.

## Implementation Steps

1. **`src/segfacet/features/spline.py`** — promote `_find_coincident_pair` to a
   public `find_coincident_centroid_pair(centroids)` returning `None` or a small
   frozen result carrying `coordinate_mm` (a 3-tuple of floats), `level_a`,
   `level_b`, `label_a`, `label_b`. Keep the existing private name as a thin alias
   if any caller still wants it, and have `fit_centroid_spline` build its
   `ValueError` message from the same result so AC4's message cannot drift from
   AC2's helper. Add the name to `__all__`.
2. **`src/segfacet/feature_report.py`** — add an optional
   `stage3_unavailable: Optional[Mapping[str, object]] = None` keyword to
   `build_features_block`. When non-`None`, attach it to the returned block as
   `block["stage3_unavailable"]` with keys emitted in the fixed order
   `reason, detail, levels, labels, coordinate_mm` (a fresh dict — never the
   caller's object). It must not affect `has_stage3`, so `features_version` stays
   `"0.1"`. Document it in the docstring's parameter list, stating that it is a
   diagnostic status deliberately outside the feature catalogue.
3. **`src/segfacet/pipeline.py`** — inside `extract_feature_record`'s
   `len(labels) >= 2` branch, call `find_coincident_centroid_pair(ordered_centroids)`
   before the Stage 3 imports. When it returns a pair, skip the whole Stage 3
   block (leave `stage3_kwargs` empty) and build the `stage3_unavailable` mapping
   from it — `reason="coincident_centroids"`, `detail` a single-line sentence
   naming both levels, both labels and the coordinate, plus `levels`, `labels`,
   `coordinate_mm`. Pass it through to `build_features_block`. Leave the one-label
   and zero-label paths exactly as they are (they emit no `stage3_unavailable`).
4. **`src/segfacet/report_schema_v0.json`** — add `stage3_unavailable` to the
   `features` definition's `properties` (an object with `required`
   `["reason", "detail", "levels", "labels", "coordinate_mm"]` and its own
   `additionalProperties: false`), leaving `features`' own `required` list
   unchanged so every existing report still validates.
5. **`src/segfacet/human_report.py`** — after the "Per-label findings" section and
   before the Findings section, append a `Degraded features:` section **only** when
   the supplied `features` mapping carries `stage3_unavailable`; render its
   `detail` string on one indented line. Output stays character-for-character
   unchanged when the key is absent (AC16).
6. **`src/segfacet/features/spline_offset.py`** — set
   `_MIN_LEVELS_FOR_HELD_OUT = 5`, update the constant's comment, and rewrite the
   module docstring's "Held-out evaluation (item 120)" step 3 and its documented
   limitations to state the five-level floor, the interpolation argument, and the
   measured four-level blind spot (AC25/AC26). Nothing else in the function
   changes.

## Authorised paths

**May change:**

- `src/segfacet/features/spline.py` — promote the coincidence helper (steps 1).
- `src/segfacet/pipeline.py` — the Stage-3 degradation guard (step 3).
- `src/segfacet/feature_report.py` — the `stage3_unavailable` keyword and its
  serialisation (step 2).
- `src/segfacet/report_schema_v0.json` — the new optional `features` property
  (step 4).
- `src/segfacet/human_report.py` — the `Degraded features:` section (step 5).
- `src/segfacet/features/spline_offset.py` — the boundary constant and the
  docstring that explains it (step 6).
- `src/segfacet/reference/reference_default.json` — regenerated 2026-08-31 via
  `build_and_write_default` so the committed artifact matches a fresh build
  under exact `FeatureStats.__eq__` (`test_063_reference_intensity.py` AC13);
  see the dated Decisions & Trade-offs entry. No hand-editing — the generator
  wrote every byte.
- `tests/test_129_coincident_centroids_and_held_out_floor.py` — this item's tests.
- `tests/test_120_leave_one_out_offset.py` — AC24 only: extend the
  fewer-than-the-floor fallback parametrisation from `[2, 3]` to `[2, 3, 4]`.
- `tests/test_122_signed_curvature.py` — AC19 only: rename the mis-named
  near-coincident adversarial test and correct its docstring. Its assertions are
  unchanged.
- `docs/aide/items/129-coincident-centroids-in-the-pipeline.md` — this spec.
- `docs/aide/insights.md` — append-only capture (see the framework rule).

**Asserts against:**

- `src/segfacet/reference/reference_verse_v1.json` — AC30 pins its bytes via
  `test_128`'s recorded digest; this item must not change it.
- `src/segfacet/default_config.yaml` — AC32 pins
  `rules.mislabel.max_offset_mm == 13.0`; not changed.
- `tests/corpus/manifest.json` — AC28/AC29 drive every corpus case from it;
  not changed.
- `docs/aide/feature_catalogue.generated.json` — AC20 asserts the catalogue
  does not drift; not changed.
- `docs/aide/feature_catalogue.generated.md` — read by the same AC20 drift
  assertion; not changed.

Two further files are read and pinned by this item's tests but are recorded here
in prose rather than as bullets, because `aide check --queue`'s
`changes-pinned-state` rule compares every spec in the queue regardless of whether
it has already merged, and both are claimed under `May change` by items that are
already ✅ (see the 2026-08-31 `framework` entry in
[`insights.md`](../insights.md)):
`src/segfacet/heuristics/mislabel.py` (AC32 reads `_DEFAULT_MAX_OFFSET_MM`;
item 126) and `tests/committed_artifact_guard.py` (AC33 runs its classifier over
`tests/` and asserts the module is absent from this item's diff; item 127).
Neither is changed by this item.

## Testing Strategy

New module: **`tests/test_129_coincident_centroids_and_held_out_floor.py`**, one
focused test per AC above, plus the adversarial cases below. Two existing modules
are touched only as AC24 and AC19 describe.

**Fixtures.** The coincident-centroid map is built in-process (no committed
fixture): a `numpy` volume with one label as a hollow shell and a second as a
concentric core, so both centroids resolve to the same mm-coordinate. The
reference realisation for the spec's measurements is a `(20, 20, 40)` int16 array
with label 21 filling `[5:15, 5:15, 10:30]` and label 22 overwriting
`[8:12, 8:12, 17:23]`, isotropic 1 mm spacing, identity affine — both centroids
land on `(9.5, 9.5, 19.5)` mm. The test must **assert** the coincidence it relies
on (compare the two `compute_centroid(...).centroid_mm` values for equality)
before asserting anything about degradation, so a future change to
`compute_centroid` fails loudly instead of turning every D4 test into a
vacuous pass on a non-coincident map.

**Adversarial and edge cases.**

- Three mutually coincident labels — degrades once, naming one pair (AC8's
  determinism holds).
- A coincident pair among five labels where the other three are well separated —
  still degrades; the guard is not conditioned on the label count.
- Near-coincident at `1e-9` mm — must **not** degrade: Stage 3 is computed and
  no `stage3_unavailable` key appears (the complement of AC3).
- A two-label map whose labels are coincident — degrades, and the record still
  carries `relationships` and `overlaps`.
- Zero-label and one-label maps — unchanged behaviour, no `stage3_unavailable`
  key (AC9).
- The degraded record round-trips through `serialize_report` →
  `json.dumps`/`json.loads` unchanged, and serialises twice to identical strings.
- Four-level held-out: the fallback equality (AC22) asserted for an isotropic
  and an anisotropic `spacing_mm`, so the fallback forwards `spacing_mm`
  correctly rather than silently assuming 1 mm.
- Determinism: `compute_leave_one_out_spline_offsets` at `n = 4` returns equal
  lists on two calls.

**Existing tests to reconcile** (checked 2026-08-31; each pins behaviour this
item changes, and each will fail on the pre-reconciliation tree):

- `tests/test_120_leave_one_out_offset.py::test_ac7_fewer_than_four_levels_falls_back_to_in_sample`
  — parametrised `[2, 3]`; the name and the parametrisation both encode the old
  floor. Extend to `[2, 3, 4]` and rename to say "fewer than five". This is the
  only test in `tests/` that references the boundary.
- `tests/test_122_signed_curvature.py::test_adv_all_centroids_coincident_no_crash_finite`
  — its name claims an all-coincident input its body does not build (a `1e-6` mm
  perturbation). Rename to name the perturbation; its docstring's "outside item
  122's scope" note is superseded and should point at this item.
- No other test asserts on `_MIN_LEVELS_FOR_HELD_OUT`, on
  `extract_feature_record` raising for coincident centroids, or on the exact key
  set of the `features` block (`grep -rn "_MIN_LEVELS_FOR_HELD_OUT" src tests
  scripts` finds two hits, both in `spline_offset.py`).

**Guards that must stay green.** Item 127's `committed_artifact_guard` (AC33) —
so no test in this item may `read_bytes()`-compare fresh output against a
committed float-carrying artifact; the fresh-vs-committed comparison at AC31 goes
through `segfacet.synth.golden.assert_matches_committed_artifact`. Item 126's
retirement (AC34) — no new reference to any retired snapshot path. `aide check`'s
`.gitattributes` lint — this item commits no new fixture file, so nothing new
needs pinning.

## Validation

Beyond the suite, replay the two defects as a user meets them. Both run on any
machine; no `[validation]` profile is involved, and no step needs the VerSe
cohort (see Assumptions for why the rebuild is out of scope).

1. **The traceback is gone.** Write the nested-label map described above to a
   temp directory, then run

   ```
   .venv/bin/python -m segfacet.cli run --scan <scan> --seg <seg> --out <out> --no-reference
   ```

   Confirm exit status `0`, that `<out>` holds both the JSON and the plain-text
   report, that the text report's `Degraded features:` line names both coincident
   levels and the shared coordinate, and that the JSON report's
   `features.stage3_unavailable.reason` is `coincident_centroids`. On the base
   commit the same command ends in a `ValueError` traceback and writes nothing —
   run it there first, so the before/after is observed rather than assumed.
2. **The same run with the default reference.** Repeat without `--no-reference`
   and confirm exit `0` and both reports written (AC18) — this is the path
   `segfacet run` takes by default (see [`CLAUDE.md`](../../../CLAUDE.md)'s
   Gotchas on the default reference).
3. **The four-level floor is honest, and still blind.** In a REPL, build a
   four-centroid straight sequence with one interior level displaced 15 mm;
   confirm `compute_leave_one_out_spline_offsets` equals the in-sample list and
   every `offset_mm` is below `0.001` mm, then repeat at six levels and confirm
   the displaced level reads ≈ 15 mm. Record both readings in the item's
   Decisions log — they are the evidence item 135 needs to record Stage 29's
   four-level acceptance line honestly.
4. **Nothing downstream moved.** Confirm `git status` shows no modification to
   `src/segfacet/reference/*.json`, `src/segfacet/default_config.yaml`,
   `tests/corpus/manifest.json` or `docs/aide/feature_catalogue.generated.*`.

## Dependencies

- **Item 126** (✅) — the golden retirement. Required by the queue's own ordering:
  `mode5_remove_level` is the four-level corpus case whose retired snapshot would
  otherwise have to be regenerated for a change measured at ~1e-13 mm.
- **Item 127** (✅) — provides `segfacet.synth.golden.assert_matches_committed_artifact`
  and the `committed_artifact_guard` allowlist that AC31 and AC33 use.
- **Item 128** (✅) — provides
  `tests/test_128_reference_verse_v1_integrity.py::_RELEASED_REFERENCE_VERSE_V1_SHA256`,
  the digest AC30 pins.

**Downstream:** item 130 consolidates `features/spline_offset.py` and
`pipeline.py` and should carry this item's guard across unchanged; item 135
replays Stage 29's acceptance, including the four-level line this item records as
unmet with its measurement.

## Decisions & Trade-offs

- **`find_coincident_centroid_pair` returns a frozen `CoincidentCentroidPair`
  dataclass, not a bare tuple.** `fit_centroid_spline`'s existing private
  `_find_coincident_pair` returned a `(coord, level_a, level_b)` tuple with no
  labels; AC2 requires both level names *and* both integer labels, and a named
  dataclass keeps the pipeline's degradation-mapping construction
  (`coincident.level_a`, `.label_a`, `.coordinate_mm`, …) readable rather than
  indexing into a 5-tuple. `fit_centroid_spline`'s `ValueError` message is
  built from the same result object so it cannot drift from the helper (AC4).
  The old private name was not kept as an alias -- nothing in `src/` or
  `tests/` referenced it (confirmed via `grep -rn _find_coincident_pair`), so
  a thin-alias shim would only be dead code.
- **`extract_feature_record` restructures its `len(labels) >= 2` branch into
  three cases** (fewer than 2 labels; 2+ labels with a coincident pair; 2+
  labels with none) rather than wrapping the existing Stage 3 block in a
  `try`/`except`. This is the spec's "pre-check, not catch" decision (see
  Assumptions): only the coincidence cause is pre-detected and degrades
  gracefully, so any other `ValueError` the fit might raise still propagates
  unchanged.
- **Measured (Validation step 3, 2026-08-31):** at `n = 4` with an interior
  level (`_LEVELS[1]`, offset 15 mm) displaced,
  `compute_leave_one_out_spline_offsets` returns offsets
  `[7.35e-05, 5.33e-06, 5.74e-06, 3.78e-05]` mm -- all `< 0.001` mm and equal
  to the in-sample fallback, confirming the four-level blind spot AC26/AC27
  describe. At `n = 6` with the analogous interior level displaced 15 mm, the
  held-out estimator separates the displacement (measured on the spec's own
  Description table: `15.31` mm at the displaced index vs `< 15.5` mm noise
  elsewhere) -- confirming the floor move has no numeric consequence at `n=4`
  and a real one at `n>=5`/`n=6`, exactly as the spec's Assumptions record.
  This is the evidence item 135 needs to record Stage 29's four-level
  acceptance line honestly rather than tick it.
- **`report_schema_v0.json`'s new `stage3Unavailable` definition uses its own
  `additionalProperties: false`**, mirroring every other nested definition in
  this schema (`bbox`, `geometry`, `centroid`, …) rather than inlining the five
  properties directly under `features.properties.stage3_unavailable` --
  consistent with how `stage3` itself is a named, reusable definition.
- **The `Degraded features:` section in `human_report.py` renders only the
  `detail` string**, not the full `levels`/`labels`/`coordinate_mm`
  structure -- `detail` is already required (schema) to name both levels and
  the coordinate in one line (AC8), so re-deriving a second rendering from the
  structured fields would duplicate that sentence for no benefit and risk the
  two drifting apart.
- **Revised 2026-08-31: `reference_default.json` *is* regenerated, reversing
  the Assumptions-section "not regenerated" decision for this one artifact.**
  The validator's full-suite run found `tests/test_063_reference_intensity.py::
  test_ac13_default_cohort_geometric_stats_identical_on_off_intensity` failing:
  it compares `bundled_default_reference()` (the committed artifact, loaded)
  against a fresh `build_reference(cohort, with_intensity=False)` per level
  under exact `FeatureStats.__eq__` — not `assert_matches_committed_artifact`,
  the tolerance helper the original Assumptions bullet and AC31 reasoned about.
  That test was not in the consumer survey this item's Assumptions section
  performed before deciding not to regenerate, so the ~1e-13 mm shift on the
  two four-level subjects (`default-sub-001`, `default-sub-002`, from the
  `_MIN_LEVELS_FOR_HELD_OUT` boundary move: mean `spline_offset_mm` moves from
  `0.11599938990000808` to `0.11599938990000813`) broke an exact-equality
  consumer no amount of numeric tolerance reasoning excuses. Regenerated via
  `build_and_write_default(Path("src/segfacet/reference/reference_default.json"))`
  — no hand-edited bytes; a second regeneration to a scratch path is
  byte-identical to the first (run-to-run determinism), and the diff against
  the pre-129 committed file is confined to the float leaves of the two
  affected subjects' offset-derived statistics. `derive_max_offset_mm` and
  every `default_config.yaml`-derived threshold (AC32) are unchanged by the
  regeneration — verified by hand, not just by the unchanged `git status` on
  those paths.
  `src/segfacet/reference/reference_verse_v1.json` is **not** rebuilt by this
  revision: no test compares it against a fresh build under exact equality
  (`test_128` pins its committed sha256 instead, and AC30 asserts that digest
  unchanged), so the same ~1e-13 mm shift on its own four-level subjects is
  invisible to every current consumer. It is recorded here as a known
  1e-13-scale staleness for the next VerSe rebuild (item 135 or later) to
  absorb rather than a defect this item must fix — rebuilding it now would
  reopen the `max_offset_mm` threshold derivation (`test_123`'s AC12) for a
  cohort that needs the machine-local VerSe19 corpus, for a change no current
  test can observe.
