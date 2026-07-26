# Item 099 — Per-mode metric API: one named metric per §6 failure mode

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 18 — Failure-Mode-Specific Metric Surface (G2, G7)
> **Queue:** [`../queue/queue-014.md`](../queue/queue-014.md) · Item 099
> *(second of five; item 098 named the stray-component population this item's
> mode-3 metric is built on, item 100 exercises this API's metrics on severity
> ladders, item 101 reports them cohort-wide)*
> **Objectives:** G2 (each of the eight §6 failure modes needs ≥1 *named* metric
> that isolates it — today the pipeline emits a verdict and findings, but no
> continuous quantity attributable to a specific mode), G7 (the mapping is
> evaluable and regression-testable rather than asserted)
> **Suggested branch:** `aide/099-per-mode-metric-api-one`

---

## Description

Stage 18's premise is that you cannot improve what you cannot measure per mode.
Item 098 named §6 mode 3's quantity; this item builds the **measurement
surface** for all eight: a new pure module, `src/segfacet/eval/per_mode.py`,
that maps **each of the eight §6 failure modes** named in
`synth/perturbation.py::FAILURE_MODE_NAMES` (lines 62-72) to **exactly one
named scalar metric** that isolates it, and computes all eight in one call.

The API is deliberately **complementary to `PerModeSensitivity`**
(`eval/metrics.py:112-144`), which reports, per mode, *the fraction of cases
whose designated rule fired* — a **detection rate**. This item reports *how much
of the mode is present in one case* — a **magnitude**. Both land side by side in
item 101's cohort report, answering "did we catch it" and "how much of it was
there". Nothing in `eval/metrics.py` changes.

### The mapping

Two input routes are sanctioned by the queue: a per-case **feature record** (the
dict `pipeline.extract_feature_record` returns) and a **candidate-vs-GT**
comparison. Each metric declares which it needs.

| §6 mode | Metric name | Source | Direction | Clean baseline |
|---|---|---|---|---|
| 1 — label not aligned with the vertebra it names | `unanchored_foreground_fraction` | `candidate_vs_gt` | increases | `0.0` |
| 2 — over-/under-segmentation (fused / fragmented) | `min_dominant_component_fraction` | `record` | **decreases** | `1.0` |
| 3 — disconnected components / rogue islands | `rogue_island_count` | `record` | increases | `0.0` |
| 4 — semantic mislabelling (wrong identification) | `mislabelled_volume_fraction` | `candidate_vs_gt` | increases | `0.0` |
| 5 — not all vertebrae segmented (missing levels) | `missing_level_count` | `candidate_vs_gt` | increases | `0.0` |
| 6 — partial vertebra at the image border | `fov_clipped_label_count` | `record` | increases | `0.0` |
| 7 — non-continuous label sequence | `out_of_order_label_count` | `record` | increases | `0.0` |
| 8 — overlapping segments | `overlapping_voxel_count` | `record` | increases | `0.0` |

Each metric's inputs already exist in the codebase — this item writes **no new
feature extractor and no new overlap code**:

1. **`unanchored_foreground_fraction`** — `|{cand ≠ 0 ∧ gt = 0}| / |{gt ≠ 0}|`:
   candidate foreground sitting where the GT has no vertebra at all. This is the
   operational reading of vision §6.1 ("label not aligned with the anatomical
   vertebra it names") *as distinct from* §6.4: a displaced mask lands on
   **background**, a mislabelled mask lands on **another real vertebra**.
2. **`min_dominant_component_fraction`** — `min` over `per_label` of
   `components.fragmentation_index` (item 025's public alias of
   `largest_component_fraction`, `feature_report.py:167`), falling back to
   `components.largest_component_fraction` when the alias key is absent.
3. **`rogue_island_count`** — `max` over `per_label` of the number of entries in
   `components.stray_component_sizes` (item 098) strictly below
   `island_size_ratio × components.component_sizes[0]`, with `island_size_ratio`
   an explicit keyword argument defaulting to `0.10`. Falls back to
   `components.component_sizes[1:]` when the item-098 key is absent.
4. **`mislabelled_volume_fraction`** — the fraction of GT foreground voxels
   whose candidate label is non-zero, **different** from the GT label, **and
   itself present in the GT label set**. The last clause is load-bearing: it is
   what separates a genuine identity confusion between two real levels (§6.4)
   from a relabel onto a level the GT never had (§6.7 — see Assumptions).
5. **`missing_level_count`** — the number of `LabelOverlap` entries from
   `eval.overlap.compute_overlap(candidate, gt, spacing).per_label` with
   `gt_voxels > 0 and candidate_voxels == 0`, restricted to those whose GT
   region is **majority background** in the candidate
   (`(candidate[gt == value] == 0).mean() > 0.5`). The restriction excludes a
   level that was merely *renamed* (mode 7), which is otherwise
   indistinguishable from one that was *removed*.
6. **`fov_clipped_label_count`** — the number of `per_label` entries touching an
   image face that the `border` rule would classify **unexpected**: any in-plane
   face (`touches_left/right/anterior/posterior`), or a cranio-caudal face
   (`touches_superior/inferior`) on a level that is **not** the corresponding
   FOV-span end. Resolved through the shared, never-raising
   `heuristics.fov.derive_fov_coverage(record)` (item 089, `fov.py:152`) so the
   metric and the rule can never disagree about which end is terminal.
7. **`out_of_order_label_count`** — `len(relationships.out_of_order_labels)`
   (`features/relationships.py:65`).
8. **`overlapping_voxel_count`** — the sum of `overlap_voxels` over
   `record["overlaps"]`, the block `features/overlap.py::detect_overlaps`
   populates (`feature_report.py:188-196`).

Alongside the eight metrics the result bundle carries the **aggregate overlap
context** — `mean_dice`, `volume_weighted_dice`, `n_matched`, `n_unmatched`,
taken verbatim from the same `compute_overlap` call — so item 101 can put the
per-mode magnitudes next to the aggregate Dice and demonstrate the stage's
thesis (the per-mode delta is informative where the aggregate is not).

**What this item is NOT:**

- **Not a new overlap primitive.** Dice/Jaccard and their aggregates come from
  `eval/overlap.py::compute_overlap` (`overlap.py:167-273`) only; this module
  contains no `2*i/(a+b)` and no `i/(a+b-i)`.
- **Not a change to `PerModeSensitivity` or `CohortMetrics`.**
  `eval/metrics.py` is untouched.
- **Not a new rule, threshold, feature, or report-schema change.** No rule fires
  on these metrics, `report_schema_v0.json` is untouched, and the CLI is
  untouched. This is a measurement surface for items 100 and 101.
- **Not the severity-ladder monotonicity / cross-mode specificity harness**
  (item 100). This item asserts isolation **per corpus case**; item 100 asserts
  monotonicity **across a graded ladder**.
- **Not the cohort report** (item 101). Nothing here aggregates over cases,
  reads a manifest, or writes a file.

## Acceptance Criteria

- [ ] **AC1: the module and its public surface exist.**
  `segfacet.eval.per_mode` defines and exports `MetricSpec`, `PerModeMetric`,
  `PerModeMetrics`, `PER_MODE_METRIC_SPECS`, `compute_per_mode_metrics` via
  `__all__`, and every one of those five names is also importable from
  `segfacet.eval` (re-exported in `eval/__init__.py`'s import block and
  `__all__`, following the pattern of the six modules already listed there).
  `PerModeMetric` and `PerModeMetrics` are `@dataclass(frozen=True)`.

- [ ] **AC2: the spec registry covers exactly the eight §6 modes.**
  `PER_MODE_METRIC_SPECS` is a mapping whose key set is exactly `{1, 2, 3, 4, 5,
  6, 7, 8}` — `CLEAN_CONTROL_MODE` (`0`) is **not** a key — and for every key
  `k`, `PER_MODE_METRIC_SPECS[k].failure_mode == k` and
  `PER_MODE_METRIC_SPECS[k].failure_mode_name ==
  segfacet.synth.perturbation.FAILURE_MODE_NAMES[k]` (character-for-character).

- [ ] **AC3: metric names are unique and carry their unit in the name.** The
  eight `metric_name` values are pairwise distinct, and every one ends in either
  `_fraction` or `_count` — the repo's existing unit-in-the-name convention
  (`stray_volume_fraction`, `component_count`). Every `direction` is one of
  `"increases"` / `"decreases"`; every `source` is one of `"record"` /
  `"candidate_vs_gt"`.

- [ ] **AC4: the result always carries all eight entries, in mode order.** For
  *any* input — including an empty record `{}` and no candidate/GT —
  `compute_per_mode_metrics(...).per_mode` is a tuple of length 8 whose
  `failure_mode` values are `(1, 2, 3, 4, 5, 6, 7, 8)` in that order. An entry
  is never dropped, reordered, or replaced by `None`.

- [ ] **AC5: `value` is uniformly `float` or `None`.** For every entry of every
  result, `entry.value` is either `None` or an instance of `float` — never
  `int`, `numpy.float64`, `numpy.int64`, or `bool` — so `to_dict()` has one
  stable JSON shape and item 100 can compare across modes without coercion.

- [ ] **AC6: mode 1 — `unanchored_foreground_fraction`.** Given
  `candidate`/`gt`, the mode-1 value equals
  `float(np.count_nonzero((candidate != 0) & (gt == 0))) /
  float(np.count_nonzero(gt != 0))`. On the corpus's `mode1_displace_seg` vs
  `clean_control_seg` it is `> 0.14`; on `clean_control_seg` vs itself it is
  `0.0`. When the GT has no foreground at all the value is `None`, not a
  `ZeroDivisionError` or `nan`.

- [ ] **AC7: mode 2 — `min_dominant_component_fraction`.** The mode-2 value
  equals the minimum of `components.fragmentation_index` over every `per_label`
  entry (falling back to `components.largest_component_fraction` when
  `fragmentation_index` is absent from that entry). On the corpus's
  `mode2_fragment` record it is `0.5` (± `1e-9`); on `clean_control` it is
  `1.0`.

- [ ] **AC8: mode 3 — `rogue_island_count` and its ratio parameter.** The mode-3
  value equals the maximum, over `per_label` entries, of the number of
  `components.stray_component_sizes` entries strictly below
  `island_size_ratio * components.component_sizes[0]`. `island_size_ratio` is a
  keyword-only argument of `compute_per_mode_metrics` defaulting to `0.10`. On
  the corpus, at the default ratio, `mode3_inject_islands` yields `1.0` (its
  stray component is 27 of 18750 voxels) while `mode2_fragment` yields `0.0`
  (its stray component is 9000 of 9000) — the two modes are separated by the
  ratio test even though both have `stray_component_count == 1`. Raising the
  ratio to `1.0` makes `mode2_fragment` yield `1.0` too, proving the parameter
  is live.

- [ ] **AC9: mode 4 — `mislabelled_volume_fraction`.** Given `candidate`/`gt`,
  the mode-4 value equals the fraction of GT-foreground voxels `v` with
  `candidate[v] != 0`, `candidate[v] != gt[v]`, **and** `candidate[v]` present in
  the GT's non-zero label set. On `mode4_relabel_swap` it is `0.4` (± `1e-9`);
  on `mode7_sequence_break` it is exactly `0.0` — because the relabel target
  (`28`/T13) is absent from the GT — whereas dropping the "present in GT" clause
  would give `0.2` there. On `clean_control` it is `0.0`.

- [ ] **AC10: mode 5 — `missing_level_count`, computed through
  `compute_overlap`.** The mode-5 value equals the number of
  `compute_overlap(candidate, gt, spacing).per_label` entries with
  `gt_voxels > 0 and candidate_voxels == 0` whose GT region is strictly more
  than 50% background in the candidate. On `mode5_remove_level` it is `1.0`; on
  `mode7_sequence_break` it is `0.0` (label 24's GT region is fully covered by
  candidate label 28); on `clean_control` it is `0.0`.

- [ ] **AC11: mode 6 — `fov_clipped_label_count`.** The mode-6 value equals the
  number of `per_label` entries with at least one true `touches_*` flag that are
  **not** an expected FOV-end truncation: an entry counts when it touches any of
  `touches_left/right/anterior/posterior`, or touches `touches_superior`
  (resp. `touches_inferior`) while its `level_name` differs from
  `derive_fov_coverage(record).superior_end_level` (resp.
  `inferior_end_level`). On `mode6_crop_at_border` it is `1.0`; on
  `clean_control` and every other corpus case it is `0.0`.

- [ ] **AC12: mode 6 agrees with the `border` rule.** For each of the nine
  corpus records, the mode-6 value equals the number of **distinct labels** named
  across the findings `segfacet.heuristics.border.BorderRule().evaluate(record,
  bundled_default_config())` emits whose `reason` starts with the rule's
  unexpected-clip tag (`"Partial vertebra clipped by FOV:"`). Neither
  `border.py` nor `fov.py` is modified to make this hold.

- [ ] **AC13: mode 7 — `out_of_order_label_count`.** The mode-7 value equals
  `float(len(record["relationships"]["out_of_order_labels"]))`. On
  `mode7_sequence_break` it is `1.0`; on `clean_control` and every other corpus
  case it is `0.0`.

- [ ] **AC14: mode 8 — `overlapping_voxel_count`.** The mode-8 value equals the
  sum of `entry["overlap_voxels"]` over `record["overlaps"]`. On a plain
  `extract_feature_record` for any corpus case it is `0.0` (a single-integer
  label map cannot encode an overlap — the structural fact item 040 documents);
  on a record whose `overlaps` block was produced by the corpus's committed
  `overlap_mask_stack` reconstruction
  (`synth/regression.py:167-184`) for `mode8_force_overlap` it is `1950.0`.
  An **absent** `overlaps` key yields `None`; a **present-but-empty** list
  yields `0.0`.

- [ ] **AC15: every metric attains its maximum deviation from baseline on its
  own mode's corpus case.** Build the 8 × 9 matrix of metric values over the
  nine corpus cases (record from `extract_feature_record` with
  `bundled_default_config()`; GT `clean_control_seg.nii.gz`; the mode-8 column
  using the reconstructed `overlaps` block). For each mode `m`,
  `abs(value[m][case_m] - baseline[m])` is **strictly greater** than
  `abs(value[m][case_j] - baseline[m])` for every other case `j` — i.e. each
  metric peaks on the mode it is designated for. This is the per-case form of
  "isolates it"; item 100 owns the ladder form.

- [ ] **AC16: the clean control is at baseline for all eight metrics.** For the
  `clean_control` corpus case (record + `clean_control_seg` as both candidate
  and GT), every entry's `value` equals its `MetricSpec.baseline` exactly
  (`1.0` for mode 2, `0.0` for the other seven), and no entry is `None`.

- [ ] **AC17: the aggregate overlap context is attached from `compute_overlap`.**
  When `candidate` and `gt` are supplied, `PerModeMetrics` carries `mean_dice`,
  `volume_weighted_dice`, `n_matched` and `n_unmatched` whose values are `==` the
  corresponding attributes of `compute_overlap(candidate, gt, spacing,
  convention=convention)`'s `OverlapResult`. When either is `None`, all four are
  `None` / `None` / `0` / `0`.

- [ ] **AC18: no new overlap code.** `per_mode.py`'s source contains no Dice or
  Jaccard arithmetic: the literal substrings `2.0 *`, `2 *`, `jaccard =` and
  `dice =` do not appear in an assignment computing an overlap coefficient, and
  the module's only route to per-label overlap bookkeeping is a call to
  `segfacet.eval.overlap.compute_overlap`. (Asserted by reading the module
  source in the test, as the drift guard the roadmap deliverable asks for.)

- [ ] **AC19: `to_dict()` round-trips through JSON unchanged.**
  `PerModeMetrics.to_dict()` returns a plain-JSON structure (dicts, lists,
  `str`, `float`, `int`, `bool`, `None` only — no tuples, no dataclasses, no
  numpy scalars) for which `json.loads(json.dumps(d)) == d`, following
  `CohortMetrics.to_dict`'s `_tuples_to_lists(dataclasses.asdict(self))`
  approach (`metrics.py:206-215`).

- [ ] **AC20: the API never mutates its inputs.** After
  `compute_per_mode_metrics(record, candidate=c, gt=g)`, a `copy.deepcopy`
  snapshot of `record` taken beforehand still compares equal, and `c` and `g`
  are element-wise unchanged (`np.array_equal` against pre-call copies). No
  file is opened and no clock is read.

- [ ] **AC21: the API is idempotent.** Two successive calls with identical
  inputs return results that compare `==` (dataclass equality) and whose
  `to_dict()` outputs are equal.

- [ ] **AC22: a record missing an optional block degrades to `None`, not an
  exception.** `compute_per_mode_metrics({})` returns eight entries with
  `value is None` for modes 2, 3, 6, 7 and 8, each carrying a non-empty `detail`
  naming the missing block; and a record for a 0-label map (`per_label == {}`,
  `relationships is None`, `overlaps == []`, **no** `stage3` key) likewise
  raises nothing and yields `None` for modes 2, 3, 6, 7 and `0.0` for mode 8.

- [ ] **AC23: a missing candidate/GT pair degrades to `None`, not an
  exception.** With `candidate=None` and/or `gt=None`, modes 1, 4 and 5 have
  `value is None` and a `detail` naming which input was absent, while the five
  record-sourced modes still resolve normally from the record.

- [ ] **AC24: a candidate/GT shape mismatch propagates
  `FacetInputError`.** `compute_per_mode_metrics(record, candidate=a, gt=b)`
  with `a.shape != b.shape` raises `segfacet.io.FacetInputError` (from
  `compute_overlap`, `overlap.py:205-209`) rather than silently returning
  `None` — a caller error is not a degradation.

- [ ] **AC25: the scope fence holds.** `eval/metrics.py` is byte-identical to
  its pre-099 state (`PerModeSensitivity` and `CohortMetrics` unchanged);
  `per_mode.py` does not import `segfacet.eval.metrics`; and
  `src/segfacet/report_schema_v0.json`, `src/segfacet/cli.py`,
  `src/segfacet/heuristics/**` and `tests/corpus/golden/*.json` are all
  unchanged by this item.

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`). Defaults taken, each
with the reasoning the queue asks the spec author to record:

- **The record is the only interface for mode 8 — no `mask_stack` parameter.**
  The queue points at `features/overlap.py::detect_overlaps` (`overlap.py:77`)
  for mode 8's shared-voxel volume. Rather than add array parameters to the API,
  the metric reads `record["overlaps"]`, which *is* `detect_overlaps`' output
  (`feature_report.py:398`). The corpus's committed `overlap_mask_stack`
  reconstruction (`synth/regression.py:167-184`) already builds exactly such a
  record — `{"overlaps": [overlap_to_dict(pair) for pair in pairs]}` — so the
  mode-8 signal is reachable today by merging that block into an
  `extract_feature_record` record. This keeps the API to two inputs (record +
  optional candidate/GT pair) and writes no new overlap code.

- **Modes 1 and 4 use the candidate-vs-GT route, not the record.** The queue
  suggested per-label spline offset for mode 1 and per-label Dice for mode 4.
  Measured against the committed goldens, the *pipeline record* is
  **structurally blind** to both: `mode1_displace`'s
  `stage3.per_label_offsets` are all `0.0` and `mode4_relabel_swap`'s
  `monotonic_consistency.is_monotonic` is `True` — both records are
  feature-identical to `clean_control` (item 040 documents why: the
  interpolating spline refits through the moved/swapped centroids). A
  record-sourced metric for these two would be a metric that never moves on its
  own mode. All nine corpus cases derive from **one shared clean base**
  (`corpus.py:88-92`, `_DEFAULT_BASE_PARAMS`, identical across every recipe
  entry), so `clean_control_seg.nii.gz` is a valid GT for every other case and
  the paired route needs no new fixture.

- **Mode 4's "candidate label must be present in the GT" clause is the mode-4 /
  mode-7 separator.** `sequence_break` relabels a level to a value the GT never
  had (24 → 28), so an unrestricted "GT foreground carrying a different
  candidate label" fraction reads `0.2` on `mode7_sequence_break` — a direct
  collision with `mode4_relabel_swap`'s `0.4`. Restricting the wrong label to
  one that exists elsewhere in the GT (a genuine confusion between two real
  levels) drives mode 7 to exactly `0.0`, measured.

- **Mode 5's "majority background" clause is the mode-5 / mode-7 separator.**
  A bare GT-present / candidate-absent count (the queue's
  `OverlapResult.n_unmatched` suggestion) reads `1` on **both**
  `mode5_remove_level` and `mode7_sequence_break`, since a renamed level is
  absent under its old value. Requiring the GT region to be majority background
  in the candidate drives mode 7 to `0.0`, measured, while leaving mode 5 at
  `1.0`.

- **Mode 2 uses `min_dominant_component_fraction`, not "per-label Dice drop".**
  A per-label Dice drop is the *least* specific quantity available: modes 1, 4,
  5, 6 and 8 all crush per-label Dice. `fragmentation_index` reads exactly `1.0`
  on seven of the nine corpus cases, `0.9986` on `mode3_inject_islands` and
  `0.5` on `mode2_fragment` — the sharpest separator in the record. It also
  covers **both halves** of §6 mode 2: the registered but un-corpused `fuse`
  operator (`synth/component_shape.py:209`) relabels a neighbour onto the target
  *unbridged*, "leaving the target spanning two disconnected vertebra bodies",
  so it drives `largest_component_fraction` down exactly as `fragment` does.
  The corpus's mode-2 case only exercises `fragment`, so the fused half of the
  mode is unmeasured today — flagged for item 100's ladder design and recorded
  in `insights.md`.

- **Modes 2 and 3 need a size-ratio test, because item 098's stray fields alone
  do not separate them.** Measured on the committed goldens,
  `stray_component_count == 1` for **both** `mode2_fragment` (`[9000, 9000]`)
  and `mode3_inject_islands` (`[18750, 27]`), and both ladders (`n_pieces`,
  `n_islands`) drive it identically. The distinguishing property is the
  *relative size* of the stray pieces — vision §6.3 says "especially **tiny**
  rogue segments" — so mode 3 counts only stray components below
  `island_size_ratio` of the dominant one. A **relative** floor is chosen over
  `HeuristicConfig.island_min_voxels`' absolute voxel floor
  (`heuristics/fragmentation.py`) so the metric is spacing- and
  body-size-independent and needs no `HeuristicConfig`; `0.10` is the default,
  and it is an explicit keyword argument so item 100 can sweep it.
  `components.small_fragments` is not used: it is driven by
  `HeuristicConfig.min_fragment_voxels`, which defaults to `0`
  (`config.py:79,149`), so it is empty in every committed golden.

- **Mode 6 mirrors item 089's FOV-aware classification rather than counting raw
  `touches_*`.** The queue names the `touches_*` flags; a raw count is correct
  on the synthetic corpus (whose clean spine touches no face) but wrong on real
  data, where the terminal levels legitimately touch the cranio-caudal FOV ends —
  the exact case `heuristics/border.py` (`_END_FACES` / `_IN_PLANE_FACES`,
  lines 56-61) and `heuristics/fov.py::derive_fov_coverage` (item 089) were
  built to suppress. The metric reuses `derive_fov_coverage` and reimplements
  the same six-line `expected` predicate locally; AC12 pins the two together by
  asserting agreement with the rule's own findings rather than by refactoring
  the rule (which would be a behaviour-changing edit to a shipped heuristic,
  out of scope here).

- **The three anticipated cross-mode collisions are recorded, not hidden.**
  Measured off-diagonal, non-baseline cells in the 8 × 9 matrix — everything
  else is exactly at baseline:
  - `unanchored_foreground_fraction` reads `0.120` on `mode6_crop_at_border`
    and `0.123` on `mode8_force_overlap` (vs `0.146` on its own case). All
    three operators translate a body rigidly, so all three put candidate
    foreground over GT background. Modes 6 and 8 have clean isolators of their
    own, so the collision is one-directional.
  - `mislabelled_volume_fraction` reads `0.021` on `mode8_force_overlap` (vs
    `0.400` on its own case) — force_overlap reassigns the contested overhang
    from the neighbour to the target, which *is* a local mislabelling.
  - `min_dominant_component_fraction` reads `0.9986` on `mode3_inject_islands`
    (vs `0.5` on its own case) — an injected island is, technically, a second
    component.
  Item 100 inherits this as a written hypothesis to measure, not a guess.

- **`PerModeMetric` carries no `labels` field.** Attributing an extremum to a
  label is useful for item 101's report, but defining it well differs per metric
  (a max-over-labels metric has one label; a volume-fraction metric has a set),
  and Stage 18's promise is attribution to a **mode**, not to a level. Deferred
  rather than half-specified; item 101 may add it if the report needs it.

- **`value` is uniformly `Optional[float]`,** even for the four count-shaped
  metrics, so `to_dict()` has one JSON shape and item 100's monotonicity
  comparison needs no per-metric type handling. The counts are exact in IEEE-754
  double at every magnitude these metrics reach.

- **`MetricSpec.baseline` is the documented *clean-control* baseline for the
  synthetic corpus,** which the queue asks for ("the clean control yields the
  documented mode-free baseline value for every metric"). It is a
  declared constant per mode, not a value recomputed from data. On real
  cohorts a metric may sit off this baseline for benign reasons; that is Stage
  16/21's territory, not this item's.

- **The module reads no `HeuristicConfig`.** Every threshold it needs is an
  explicit keyword argument (`island_size_ratio`, `spacing`, `convention`), so
  the metric surface cannot drift when a rule is recalibrated. This is
  deliberate: item 100's ladders must measure the *data*, not the current
  threshold set.

## Implementation Steps

All production changes are under `source_dir = src/segfacet`.

1. **Create `src/segfacet/eval/per_mode.py`** with a module docstring in the
   package's house style: what it is, how it differs from
   `PerModeSensitivity` (detection rate vs magnitude), the mode → metric table
   above, the two input routes, the purity contract, a **Scope fence** naming
   what it is not, and a `Public API` block listing the five exported names.

2. **`MetricSpec`** — `@dataclass(frozen=True)` with `failure_mode: int`,
   `failure_mode_name: str`, `metric_name: str`, `direction: str`,
   `baseline: float`, `source: str`, `description: str`. Then
   `PER_MODE_METRIC_SPECS: Mapping[int, MetricSpec]` — a module-level, immutable
   (`types.MappingProxyType`) registry with one entry per mode 1-8, built by
   reading `failure_mode_name` from
   `segfacet.synth.perturbation.FAILURE_MODE_NAMES` so the names cannot drift
   (AC2). Import it at module top level — `synth.perturbation` is stdlib +
   numpy/nibabel only and `eval/` already imports from `segfacet.synth` in
   sibling modules.

3. **`PerModeMetric`** — `@dataclass(frozen=True)` with `failure_mode: int`,
   `failure_mode_name: str`, `metric_name: str`, `value: Optional[float]`,
   `direction: str`, `baseline: float`, `source: str`, `detail: str`. A private
   constructor helper builds one from a `MetricSpec` plus a
   `(value, detail)` pair so the seven spec-derived fields are never
   hand-copied at eight call sites.

4. **`PerModeMetrics`** — `@dataclass(frozen=True)` with
   `per_mode: Tuple[PerModeMetric, ...]`, `mean_dice: Optional[float]`,
   `volume_weighted_dice: Optional[float]`, `mean_jaccard: Optional[float]`,
   `n_matched: int`, `n_unmatched: int`, plus:
   - `to_dict()` — `_tuples_to_lists(dataclasses.asdict(self))`, mirroring
     `CohortMetrics.to_dict` (`metrics.py:206-215`). Either import
     `segfacet.eval.metrics._tuples_to_lists` **or** copy the six-line helper —
     prefer the copy, since AC25 forbids importing `eval.metrics`; note the
     duplication in the docstring.
   - `by_mode(failure_mode) -> PerModeMetric` — a small keyed accessor so items
     100/101 do not index into the tuple positionally.

5. **Eight private metric functions**, one per mode, each returning
   `Tuple[Optional[float], str]` (value, detail) and each guarding its own input
   block. Record-sourced ones take `(record, ...)`; paired ones take
   `(candidate, gt, spacing, overlap_result)`. Every one is total: it returns
   `(None, "<reason>")` rather than raising on a missing/degenerate block.
   Follow `heuristics/fov.py`'s defensive `record.get(...) or {}` /
   `isinstance(..., dict)` discipline throughout — the record may legitimately
   carry `relationships: None` (0-label map, `feature_report.py:208-209`).

6. **`compute_per_mode_metrics`** — the single public entry point:

   ```
   def compute_per_mode_metrics(
       record: Mapping[str, Any],
       *,
       candidate: Optional[np.ndarray] = None,
       gt: Optional[np.ndarray] = None,
       spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
       island_size_ratio: float = 0.10,
       convention: Optional[LabelConvention] = None,
   ) -> PerModeMetrics
   ```

   Call `compute_overlap(candidate, gt, spacing, convention=convention)` **once**
   when both arrays are given (letting its `FacetInputError` propagate, AC24),
   reuse that single `OverlapResult` for mode 5 and for the four aggregate
   fields (AC17), then build the eight entries in ascending mode order from
   `PER_MODE_METRIC_SPECS` (AC4). Never mutate `record`, `candidate` or `gt`
   (AC20) — read via `np.asarray` and index, never assign.

7. **`src/segfacet/eval/__init__.py`** — add a `from .per_mode import (...)`
   block (alphabetically between `.overlap` and `.report`) and append the five
   names to `__all__`; extend the package docstring's running sentence with the
   per-mode magnitude surface and its item number (099), naming it as
   complementary to item 054's per-mode *sensitivity*.

8. **Do NOT touch** `eval/metrics.py`, `eval/report.py`, `eval/harness.py`,
   `heuristics/**`, `features/**`, `synth/**`, `cli.py`,
   `report_schema_v0.json`, `eval_report_schema_v0.json`, or
   `tests/corpus/**`.

## Testing Strategy

- **Framework:** `pytest`. One new module, `tests/test_099_per_mode_metrics.py`.
  No existing test module is modified.

- **Shared fixtures** (module-scoped, built once): the nine corpus records via
  `synth.regression.loaded_seg_image(case)` + `pipeline.extract_feature_record(
  seg_img, bundled_default_config())` (the exact pairing
  `tests/test_041_regression_suite.py` uses), the nine candidate arrays, the GT
  array from `clean_control_seg.nii.gz`, and one mode-8 record whose `overlaps`
  block is replaced by the output of the committed
  `overlap_mask_stack` reconstruction technique
  (`synth.regression.RECONSTRUCTIONS`). Loading the corpus once and
  parametrising over it keeps the module well under the suite's per-file cost.

- **AC1-AC5 (surface & shape)** — introspection tests: `__all__` contents,
  `dataclasses.fields`, `frozen=True` via an attempted attribute assignment
  raising `FrozenInstanceError`, `PER_MODE_METRIC_SPECS` key set and name
  agreement with `FAILURE_MODE_NAMES`, metric-name uniqueness and suffix regex
  (`_(fraction|count)$`), and `type(v) is float` (not just `isinstance`, to
  exclude `bool` and `numpy.float64`) swept over all eight entries of a real
  result.

- **AC6-AC14 (the eight metrics)** — one focused test per mode, each asserting
  (a) the value on its own corpus case against a **hand-computed** expected
  value derived from the fixture's construction (voxel counts read from the
  manifest's `detail` strings and the committed goldens), not from the
  implementation's own output, and (b) the value on `clean_control`. Plus the
  three named separator tests, which are the load-bearing ones:
  - mode 4 on `mode7_sequence_break` is `0.0` (and a hand-built pair proves the
    unrestricted variant would give `0.2`);
  - mode 5 on `mode7_sequence_break` is `0.0` while `n_unmatched` from the same
    `OverlapResult` is `2` (the naive metric would fire);
  - mode 3 on `mode2_fragment` is `0.0` at `island_size_ratio=0.10` and `1.0` at
    `island_size_ratio=1.0`.

- **AC15 (the isolation matrix — the load-bearing test)** — compute the full
  8 × 9 matrix once and assert diagonal dominance of `abs(value - baseline)`
  per metric, with the matrix itself asserted against a frozen literal table
  embedded in the test module (so a later change that quietly flattens a metric
  is caught, not just a change that breaks the ordering). Numeric comparisons
  use `pytest.approx` with an explicit tolerance; counts are compared exactly.
  Include a **negative control**: deliberately assign mode 3's metric to mode
  2's column and assert the dominance check fails — proving the assertion can
  actually fail.

- **AC12 (border-rule agreement)** — parametrised over the nine corpus records,
  comparing the metric against `BorderRule().evaluate(record,
  bundled_default_config())`'s unexpected-clip findings. Also assert the metric
  is `0.0` for a hand-built record whose only border touch is
  `touches_superior` on the level `derive_fov_coverage` reports as
  `superior_end_level` — the real-data case the synthetic corpus never
  exercises.

- **AC18 (no new overlap code)** — read
  `Path(segfacet.eval.per_mode.__file__).read_text()` and assert the absence of
  Dice/Jaccard arithmetic and the presence of a `compute_overlap(` call; assert
  `"segfacet.eval.metrics"` does not appear in the module's imports (AC25's
  half).

- **AC19-AC21 (JSON, purity, idempotence)** — `json.loads(json.dumps(d)) == d`
  plus a recursive type walk asserting only JSON-native types appear;
  `copy.deepcopy` snapshot equality of the record and `np.array_equal` on the
  two arrays before/after; two calls compared with `==` and via `to_dict()`.

- **Adversarial / edge cases:**
  - `compute_per_mode_metrics({})` — eight entries, five `None`s, no exception
    (AC22).
  - A 0-label record (built by running `extract_feature_record` on an all-zero
    label map): `per_label == {}`, `relationships is None`, **no** `stage3` key.
    Confirms the queue's "missing optional block degrades to `None`" case, and
    that mode 8 reads `0.0` from a present-and-empty `overlaps`.
  - A 1-label record (no `stage3` either, since Stage 3 needs ≥2 labels):
    modes 2/3/6 resolve from the single entry; mode 7 reads `0.0`.
  - Candidate/GT both all-zero → mode 1 is `None` (empty GT denominator), not
    `nan`; modes 4/5 are `0.0` / `0.0`.
  - `candidate is gt` (same object) → every paired metric at baseline,
    `mean_dice == 1.0`.
  - Shape mismatch → `FacetInputError` (AC24).
  - `island_size_ratio=0.0` → `rogue_island_count` is `0.0` for every corpus
    case (nothing is strictly below zero); `island_size_ratio` above `1.0` →
    every stray component counts. Boundary: a stray component exactly at
    `ratio * dominant` does **not** count (strictly below).
  - A malformed record whose `per_label` is a list, or whose `components` is a
    string → `None` with a detail, never a `TypeError` (mirrors the
    defensive-read contract `heuristics/fov.py:172-192` already keeps).
  - Non-isotropic spacing (e.g. `(0.5, 1.0, 2.0)`) → mode 5's count and the
    aggregate `volume_weighted_dice` change appropriately while the seven
    voxel-ratio metrics are spacing-invariant.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate — all expected to stay green **unmodified**; an edit to any of them
  is a red flag for the validator, since this item adds a module and changes no
  behaviour):
  - `tests/test_054_cohort_metrics.py` — pins `PerModeSensitivity` /
    `CohortMetrics`. AC25 forbids touching `eval/metrics.py`, so these must not
    move.
  - `tests/test_050_overlap_dice.py` — pins `compute_overlap` /
    `OverlapResult`. This item is a pure consumer.
  - `tests/test_089_fov_aware_coverage_border.py` and the `border`-rule tests
    (`tests/test_030_*`/`tests/test_035_*`, whichever pin the unexpected-clip
    `reason` strings) — AC12 asserts *agreement* with those strings; if a test
    there pins the tag text, the metric test must read the same constant rather
    than a second copy of the literal.
  - `tests/test_041_regression_suite.py` and `tests/test_040_synthetic_corpus.py`
    — this item reuses `loaded_seg_image` / `RECONSTRUCTIONS` read-only.
  - `tests/test_098_stray_components.py` — pins the item-098 fields the mode-3
    metric reads; unchanged.
  - Any test asserting `segfacet.eval.__all__` exhaustively (grep for
    `__all__` under `tests/`) — AC1 grows it by five names, so an exhaustive
    `==` assertion there would need updating; check before assuming.

## Validation

Beyond the unit suite, observe the metric surface separating the modes on the
committed corpus — the stage's whole thesis in one run. From the repo root with
the venv bootstrapped:

```
.venv/bin/python -c "import segfacet.eval as e; print(sorted(n for n in e.__all__ if 'per_mode' in n.lower() or 'PerMode' in n))"
```

Then run the isolation matrix by hand and read it:

```
.venv/bin/python -m pytest tests/test_099_per_mode_metrics.py -k isolation_matrix -v
```

and confirm by inspection of the printed 8 × 9 table that:

1. Each row's largest deviation from baseline sits on its own mode's column
   (the diagonal), for all eight rows.
2. `mode2_fragment` and `mode3_inject_islands` are separated —
   `min_dominant_component_fraction` `0.5` vs `0.9986`, `rogue_island_count`
   `0` vs `1` — despite both having `stray_component_count == 1`. This is the
   concrete thing item 098's fields alone could not do.
3. `mode4_relabel_swap` and `mode7_sequence_break` are separated —
   `mislabelled_volume_fraction` `0.4` vs `0.0`, `missing_level_count` `0` vs
   `0`, `out_of_order_label_count` `0` vs `1`.
4. The aggregate `mean_dice` column does **not** separate them nearly as
   cleanly as the per-mode columns do — which is the argument item 101's
   run-vs-run report is built on.

No `[validation]` profile is required: this runs on the plain CPU venv with no
optional dependency. If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified.

## Dependencies

- **Item 012** (`ComponentsInfo` / `compute_components` — `component_sizes`,
  `largest_component_fraction`) — ✅.
- **Item 025** (`fragmentation_index`, the public alias mode 2 reads, and the
  primary-key/fallback-alias discipline modes 2 and 3 mirror) — ✅.
- **Item 040** (the nine-case synthetic corpus, its manifest, and the shared
  clean base that makes `clean_control_seg.nii.gz` a valid GT for every other
  case) — ✅.
- **Item 041** (`synth/regression.py`'s `loaded_seg_image`, `RECONSTRUCTIONS`
  and the committed `overlap_mask_stack` technique mode 8's record comes from)
  — ✅.
- **Item 050** (`eval/overlap.py::compute_overlap`, `LabelOverlap`,
  `OverlapResult` — the mandated overlap reuse) — ✅.
- **Item 054** (`eval/metrics.py`'s `PerModeSensitivity` / `CohortMetrics`
  dataclass + `to_dict()` pattern this module's shape follows, and the surface
  it must complement rather than duplicate) — ✅.
- **Item 089** (`heuristics/fov.py::derive_fov_coverage` and the border rule's
  expected-FOV-end classification mode 6 mirrors) — ✅.
- **Item 098** (the `stray_component_sizes` / `stray_component_count` fields
  mode 3 reads, and their serialisation in `components_to_dict`) — ✅.

**Downstream:** item 100 builds severity ladders against these eight metrics and
inherits this spec's recorded cross-mode collision hypotheses; item 101 puts the
metrics and the aggregate overlap context into the cohort run-vs-run report;
item 102 replays the isolation matrix as part of the stage validation. None of
these block this item.

## Decisions & Trade-offs

To be updated during implementation.
