# Item 051 — Feature-set match / divergence by vertebra label

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (G3, G7)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 051
> **Objectives:** G7 (evaluable / regression-testable — supplies the §8 level-3
> **feature-set match** primitive); supports G3 (quantifies per-label geometric
> divergence, the feature-similarity proxy Stage-7 correlates against DICE)
> **Suggested branch:** `aide/051-feature-set-match-divergence-by`

---

## Description

Provide the **feature-set match** comparison layer — level 3 of the vision's §8
three-level evaluation (QC verdict; segmentation overlap / DICE; **feature-set
match by vertebra label**). Deliver a **pure** module `segqc/eval/feature_match.py`
that compares the **already-extracted Stage 2–3 feature blocks** of a **candidate**
case and its **ground-truth (GT)** case, matched by anatomical (integer) label, and
emits:

- a **per-label, per-feature difference** — both **absolute** (candidate − GT, in
  the feature's own units, sign preserved) and **relative** (absolute ÷ GT value)
  — across a documented, ordered set of **tracked scalar features**
  (`physical_volume_mm3`, `extent_x_mm`, `extent_y_mm`, `extent_z_mm`, and the
  Stage-3 `spline_offset_mm`);
- a per-label **centroid displacement** (`centroid_distance_mm`) — the Euclidean
  distance between the candidate and GT `centroid_mm` vectors;
- an aggregate **per-label divergence score** (the mean absolute *relative*
  difference over the tracked scalar features available on both sides); and
- a **case-level divergence score** (the mean of the per-label divergence scores
  over matched labels).

The module **reuses the existing feature-engine output** — the `features` block
dict produced by `segqc.pipeline.extract_feature_record` /
`segqc.feature_report.build_features_block` — and never recomputes geometry from
label maps. Matching is by **integer label value**; a label present on only one
side is reported as an **unmatched** entry (never silently dropped, never a crash),
and is excluded from the aggregate scores.

This is one of three independent Stage-7 comparison primitives — 050 (DICE /
overlap, level 2), **051 (feature-set match, level 3)**, 052 (verdict-outcome,
level 1) — that item 053's evaluation harness assembles per case. It follows the
sibling 050's style: a pure module in `segqc/eval/`, frozen dataclasses,
`SegQCInputError` for malformed input, and `segqc.labels` for naming/ordering.

**In scope:** `segqc/eval/feature_match.py` containing the frozen dataclasses
`FeatureDifference`, `LabelFeatureDivergence`, `FeatureMatchResult`, the ordered
`TRACKED_FEATURES` constant, and the `compute_feature_match(...)` function; a
re-export from `segqc/eval/__init__.py`; and `tests/test_051_feature_match.py`.

**Out of scope (do NOT):** any file / NIfTI I/O or label-map loading (the caller
passes two already-built `features` block dicts — blocks in, scores out);
recomputing geometry / extents / centroids / spline offsets from arrays (that is
the Stage 2–3 feature engine's job — reuse its output verbatim); voxel-overlap /
DICE (item 050 — a *different* comparison that operates on label maps, not feature
values); verdict-outcome classification (item 052); any cohort, harness, metrics,
correlation, or calibration logic (items 053–055 — this primitive produces
per-case, per-label divergence numbers only, with no cross-case aggregation and no
flag/verdict interpretation); mutating any Stage 0–6 module, the CLI, the config,
or the report schema.

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each in
`tests/test_051_feature_match.py` (see Testing Strategy)._

- [ ] **AC1: module & public API exist.** `segqc.eval.feature_match` exposes
  `compute_feature_match(candidate, gt) -> FeatureMatchResult`, the ordered
  constant `TRACKED_FEATURES`, and frozen dataclasses `FeatureDifference`,
  `LabelFeatureDivergence`, `FeatureMatchResult`; all are listed in the module
  `__all__` and importable both as `from segqc.eval.feature_match import
  compute_feature_match, FeatureDifference, LabelFeatureDivergence,
  FeatureMatchResult, TRACKED_FEATURES` and (re-exported) `from segqc.eval import
  compute_feature_match`. `FeatureDifference` carries fields `feature: str`,
  `candidate_value: Optional[float]`, `gt_value: Optional[float]`,
  `absolute: Optional[float]`, `relative: Optional[float]`, `available: bool`.
  `LabelFeatureDivergence` carries `value: int`, `name: str`, `matched: bool`,
  `differences: Tuple[FeatureDifference, ...]`,
  `centroid_distance_mm: Optional[float]`, `divergence_score: Optional[float]`.
  `FeatureMatchResult` carries `per_label: Tuple[LabelFeatureDivergence, ...]`,
  `case_divergence: Optional[float]`,
  `mean_centroid_distance_mm: Optional[float]`, `n_matched: int`,
  `n_unmatched: int`.

- [ ] **AC2: `TRACKED_FEATURES` is the documented ordered set.**
  `TRACKED_FEATURES == ("physical_volume_mm3", "extent_x_mm", "extent_y_mm",
  "extent_z_mm", "spline_offset_mm")`, and for every matched label the
  `differences` tuple has exactly one `FeatureDifference` per name, in that order,
  with each `.feature` equal to the corresponding name.

- [ ] **AC3: identical feature sets → zero divergence everywhere.** When
  `candidate` and `gt` are the *same* feature block (deep-equal), every matched
  label is `matched is True` with every `FeatureDifference.absolute == 0.0`,
  `relative == 0.0` (where defined), `available is True`; every
  `centroid_distance_mm == 0.0`; every `divergence_score == 0.0`; and
  `case_divergence == 0.0`, `mean_centroid_distance_mm == 0.0`.

- [ ] **AC4: a scalar feature difference is signed and matches the hand value.**
  For a label whose candidate `physical_volume_mm3` is `vc` and GT is `vg`
  (`vc != vg`, `vg != 0`), that label's `physical_volume_mm3`
  `FeatureDifference` has `absolute == vc - vg` (correct **sign**) and
  `relative == (vc - vg) / vg`, to floating-point tolerance; a candidate value
  **larger** than GT gives a **positive** `absolute`/`relative`, a smaller one a
  **negative** value.

- [ ] **AC5: perturbing one label localises the divergence to that label.** Given
  two blocks equal except that a **single** label's `physical_volume_mm3` differs,
  only that label has `divergence_score > 0` (and a non-zero
  `physical_volume_mm3` difference); every **other** matched label has
  `divergence_score == 0.0` and all-zero differences.

- [ ] **AC6: centroid displacement is the Euclidean distance of `centroid_mm`.**
  For a matched label whose candidate `centroid_mm` and GT `centroid_mm` differ by
  a known vector `(dx, dy, dz)`, `centroid_distance_mm == sqrt(dx**2 + dy**2 +
  dz**2)` to tolerance; when the two centroids are equal, `centroid_distance_mm
  == 0.0`. Centroid displacement is **not** folded into `divergence_score`
  (which is over the tracked scalar features only).

- [ ] **AC7: per-label divergence score is the mean absolute relative difference
  over available tracked features.** For a matched label,
  `divergence_score == mean(abs(d.relative) for d in differences if d.available
  and d.relative is not None)`, hand-computed for the fixture; if **no** tracked
  feature has a defined `relative` for that label, `divergence_score is None`.

- [ ] **AC8: case-level divergence aggregates the per-label scores.**
  `case_divergence == mean(l.divergence_score for l in per_label if l.matched and
  l.divergence_score is not None)`, hand-computed for the fixture; and
  `mean_centroid_distance_mm == mean(l.centroid_distance_mm for l in per_label if
  l.matched and l.centroid_distance_mm is not None)`. With **no** qualifying
  matched labels, both are `None` (no divide-by-zero).

- [ ] **AC9: a label present on only one side is unmatched, not an error.** A
  label present in `candidate.per_label` but absent from `gt.per_label` (and,
  symmetrically, present in `gt` but absent from `candidate`) produces a
  `LabelFeatureDivergence` with `matched is False`, `differences == ()`,
  `centroid_distance_mm is None`, `divergence_score is None`; `compute_feature_match`
  raises **no** exception. Such entries are counted in `n_unmatched` and
  **excluded** from `case_divergence` / `mean_centroid_distance_mm`.

- [ ] **AC10: a tracked feature unavailable on one side is marked, not fabricated.**
  For a matched label where a tracked feature is present on one side but absent on
  the other (e.g. the Stage-3 `spline_offset_mm` exists in one block's `stage3`
  but not the other's), that feature's `FeatureDifference` has `available is
  False`, `absolute is None`, `relative is None`, and the present side's
  `candidate_value` / `gt_value` populated (the absent side `None`); it is
  **excluded** from `divergence_score`. No exception is raised.

- [ ] **AC11: a zero GT value yields `relative is None` but a defined `absolute`.**
  For a matched label whose GT value for a tracked feature is `0.0` and whose
  candidate value is non-zero, that `FeatureDifference` has
  `absolute == candidate_value` (defined) and `relative is None` (no
  divide-by-zero); it is excluded from `divergence_score` (which uses defined
  relatives only).

- [ ] **AC12: entries are named and ordered via the Stage-0 convention.** Each
  `LabelFeatureDivergence.name` equals the label's `level_name` as carried in the
  feature block (GT side authoritative for matched labels; the present side for
  unmatched), and `per_label` is ordered head-to-tail by
  `segqc.labels.CANONICAL_ORDER` for recognised names, with unrecognised names
  (`segqc.labels.UNKNOWN`) placed after them ordered by ascending integer `value`
  — never merged into a single bucket.

- [ ] **AC13: malformed input raises `SegQCInputError`.** Calling
  `compute_feature_match` when either argument is not a mapping, or lacks a
  `per_label` mapping (e.g. `per_label` missing or not a dict), raises
  `segqc.io.SegQCInputError` with a clear message — not a raw `KeyError`,
  `TypeError`, or `AttributeError`.

- [ ] **AC14: pure, deterministic, and non-mutating.** Two `compute_feature_match`
  calls on the same inputs return equal `FeatureMatchResult`s (equal `per_label`
  ordering and values, equal aggregates); the `candidate` and `gt` block dicts
  (and their nested dicts) are unchanged after the call; the function performs no
  file I/O.

## Assumptions  <!-- MANDATORY: clarify mode = assume -->

- **Inputs are two `features` block dicts, not label maps or `Case`s (clarify
  `assume`).** The queue says "compares the Stage 2–3 feature sets … Reuse the
  existing feature-engine outputs rather than recomputing geometry." So
  `compute_feature_match(candidate, gt)` takes exactly the dict returned by
  `segqc.pipeline.extract_feature_record` / `feature_report.build_features_block`
  — with a top-level `per_label` mapping (keyed by `str(label)`, each entry
  carrying `label`, `level_name`, `geometry`, `centroid`, …) and an optional
  `stage3.per_label_offsets` list. No arrays, no NIfTI, no I/O. A caller with two
  `Case`s runs the pipeline on each first and passes the two blocks; item 053's
  harness does exactly this.

- **Match key is the integer label value; the name comes from the block (clarify
  `assume`).** Mirroring item 050's decision: both blocks use the *same*
  integer→anatomy scheme (vision §10), so label `22` in candidate is compared with
  label `22` in GT. Matching is by `int` of the `per_label` key (equivalently the
  entry's `label` field); the anatomical `name` is read from the entry's
  `level_name` (GT side authoritative for a matched label — GT is the reference
  truth). This avoids collapsing distinct unmapped labels into one `UNKNOWN`
  bucket. `CANONICAL_ORDER` / `UNKNOWN` from `segqc.labels` supply only ordering
  and the unknown-name sentinel; no `LabelConvention` parameter is needed because
  the blocks already carry `level_name`.

- **Tracked features are the documented ordered set
  `("physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm",
  "spline_offset_mm")` (clarify `assume`).** The queue lists "physical volume,
  extents, centroid spacing, spline offset, …". The first four are per-label
  **scalar** geometry read from `entry["geometry"][name]`. `spline_offset_mm` is
  the Stage-3 per-label perpendicular offset read from the block's
  `stage3["per_label_offsets"]` list (the entry whose `label` matches), field
  `offset_mm`; it is legitimately **absent** for Stage-2-only blocks or maps with
  < 2 labels — handled as an *unavailable* feature (AC10), never an error.
  "Centroid spacing" is handled as the standalone `centroid_distance_mm` (below),
  not as a scalar tracked-feature difference. The set is deliberately a small,
  documented constant so downstream (054) is stable; it is not
  caller-configurable in this primitive.

- **Per-feature difference is signed; the divergence score uses magnitudes
  (clarify `assume`).** `absolute = candidate_value − gt_value` and
  `relative = absolute / gt_value` are **signed** (so the queue's "expected
  sign/magnitude" is observable at the feature level). The per-label
  `divergence_score` is the **mean of `abs(relative)`** over tracked features that
  are `available` on both sides *and* have a defined (non-`None`) `relative`
  (i.e. `gt_value != 0`). Rationale: relative differences are dimensionless and
  therefore mean-able across features of different units (mm³ vs mm); using
  magnitudes makes the score a non-negative "how far apart" measure.

- **Centroid displacement is reported separately, not folded into the score
  (clarify `assume`).** `centroid_distance_mm` is the Euclidean distance between
  the two `centroid_mm` vectors — a mm displacement with **no** natural
  dimensionless denominator, so folding it into the mean-of-relatives score would
  either dimension the score or require an arbitrary length scale. It is therefore
  surfaced as its own per-label field (and a case-level
  `mean_centroid_distance_mm`) so downstream metrics/calibration (054/055) can
  weight displacement explicitly if desired. This is the one deliberate
  interpretation of the queue's "centroid spacing" among the tracked features.

- **Aggregates are over MATCHED labels only; empty ⇒ `None` sentinel.**
  `case_divergence` and `mean_centroid_distance_mm` average only entries with
  `matched is True` and a defined value; unmatched labels are still reported in
  `per_label` (with empty `differences`, `None` scores) for visibility but
  excluded from the aggregates. With no qualifying matched labels — including the
  empty-block case (`per_label == {}` on both sides) — each aggregate is `None`
  (an explicit "not applicable" sentinel), never `0.0` and never a
  divide-by-zero.

- **Background label `0` never appears** — the feature blocks are already
  built from non-zero labels only (`extract_feature_record` derives labels as
  `sorted(v for v in np.unique(data) if v != 0)`), so no background handling is
  needed here.

- **Interface pins (dependencies already ✅).** From item 004 `segqc.labels`:
  `CANONICAL_ORDER` and `UNKNOWN` — used for ordering exactly as item 050's
  `overlap.py` does. From item 003 `segqc.io`: `SegQCInputError` — reused as the
  single malformed-input error type. From items 011/013/018 via item 016/022
  `feature_report.build_features_block`: the `features` block shape this module
  reads — `per_label[str(label)]` → `{label, level_name, geometry:
  {physical_volume_mm3, extent_x_mm, extent_y_mm, extent_z_mm, …}, centroid:
  {centroid_mm: [x,y,z], …}, …}` and `stage3.per_label_offsets` →
  `[{label, offset_mm, …}, …]`. If any of these interfaces has diverged from this
  description, the builder/validator should hand back.

## Implementation Steps

Code path in `src/segqc/` (`aide.toml` `source_dir = src/segqc`).

1. **`src/segqc/eval/feature_match.py` — module docstring + imports.** Docstring
   stating: §8 level-3 feature-set match; pure, no I/O; reuses feature-engine
   output (no geometry recompute); matches by integer label value; names/orders
   via `segqc.labels`; the tracked-feature set and the divergence-score /
   centroid-distance definitions; the distinction from item 050 (voxel-overlap
   DICE on label maps). Import `math`, `dataclasses.dataclass`, typing helpers,
   `CANONICAL_ORDER` and `UNKNOWN` from `segqc.labels`, and `SegQCInputError` from
   `segqc.io`. Declare `__all__` and the module-level constant `TRACKED_FEATURES`.
   Add the `_CANONICAL_RANK` / `_UNRECOGNISED_RANK` ordering helpers as in
   `overlap.py`.

2. **`TRACKED_FEATURES` constant** — the ordered tuple
   `("physical_volume_mm3", "extent_x_mm", "extent_y_mm", "extent_z_mm",
   "spline_offset_mm")`.

3. **`FeatureDifference` frozen dataclass** with the fields in AC1.

4. **`LabelFeatureDivergence` frozen dataclass** with the fields in AC1.

5. **`FeatureMatchResult` frozen dataclass** with the fields in AC1.

6. **Input validation + accessors.** A private `_require_block(obj, side)` that
   raises `SegQCInputError` when `obj` is not a `Mapping` or its `per_label` is
   missing / not a `Mapping`. A private `_offset_map(block) -> Dict[int, float]`
   that reads `block.get("stage3", {}).get("per_label_offsets", [])` and builds
   `{int(o["label"]): float(o["offset_mm"])}` (empty when absent). A private
   `_scalar_value(entry, offset_map, label, feature) -> Optional[float]` returning
   `entry["geometry"][feature]` for the four geometry features and
   `offset_map.get(label)` for `spline_offset_mm` (`None` when the geometry key or
   the offset is absent).

7. **`compute_feature_match(candidate, gt)`.**
   1. `_require_block(candidate, "candidate")`, `_require_block(gt, "gt")`.
   2. Build `cand_pl = candidate["per_label"]`, `gt_pl = gt["per_label"]`, and the
      two offset maps.
   3. `label_values = sorted({int(k) for k in cand_pl} | {int(k) for k in gt_pl})`.
   4. For each label value `v`: fetch the candidate/GT entries (`None` if absent);
      `matched = both present`. Determine `name` from GT entry's `level_name` when
      present else candidate's, defaulting to `UNKNOWN`.
   5. If **not** `matched`: append `LabelFeatureDivergence(value=v, name=name,
      matched=False, differences=(), centroid_distance_mm=None,
      divergence_score=None)`.
   6. If `matched`: for each `feature` in `TRACKED_FEATURES`, read
      `cv = _scalar_value(cand_entry, cand_off, v, feature)` and
      `gv = _scalar_value(gt_entry, gt_off, v, feature)`;
      `available = cv is not None and gv is not None`;
      `absolute = (cv - gv) if available else None`;
      `relative = (absolute / gv) if (available and gv != 0) else None`; append a
      `FeatureDifference(feature, cv, gv, absolute, relative, available)`.
   7. Compute `centroid_distance_mm` from the two entries' `centroid["centroid_mm"]`
      vectors as `math.sqrt(sum((a-b)**2))`; `None` if either centroid is missing.
   8. `rels = [abs(d.relative) for d in differences if d.available and d.relative
      is not None]`; `divergence_score = (sum(rels)/len(rels)) if rels else None`.
   9. Append the matched `LabelFeatureDivergence`.
   10. **Sort** `per_label` by `(_CANONICAL_RANK.get(name, _UNRECOGNISED_RANK),
      value)` (recognised head-to-tail, unrecognised after by ascending value).
   11. Compute case aggregates over matched entries with defined values:
      `case_divergence` = mean of their `divergence_score`; `mean_centroid_distance_mm`
      = mean of their `centroid_distance_mm`; each `None` when no qualifying entry.
      `n_matched` / `n_unmatched` from the entries.
   12. Return `FeatureMatchResult(per_label=tuple(entries), case_divergence=…,
      mean_centroid_distance_mm=…, n_matched=…, n_unmatched=…)`.

8. **Never mutate inputs.** Read only from the block dicts; build fresh dataclasses
   and tuples. No file access anywhere in the module.

9. **`src/segqc/eval/__init__.py` — re-export.** Add `from .feature_match import
   compute_feature_match, FeatureDifference, LabelFeatureDivergence,
   FeatureMatchResult, TRACKED_FEATURES` and extend `__all__`; update the package
   docstring to mention the level-3 feature-match primitive alongside level-2.

## Testing Strategy

One focused test per AC in **`tests/test_051_feature_match.py`**. Build tiny
`features` block dicts **by hand** as Python literals (a small helper that returns
a minimal but schema-shaped block: `{"features_version": "0.2", "per_label":
{...}, "stage3": {"per_label_offsets": [...]}}`, each `per_label` entry carrying
`label`, `level_name`, `geometry` with the four tracked scalars, and `centroid`
with `centroid_mm`). No loader, no NIfTI, no disk fixtures — every expected
difference / score is hand-computed and exact. Perturbations are produced by
`copy.deepcopy` + editing one field so the "identical except one label" property is
guaranteed.

- **AC1** — import all five names from both `segqc.eval.feature_match` and (the
  function) `segqc.eval`; assert dataclasses are frozen and expose the documented
  fields.
- **AC2** — assert `TRACKED_FEATURES` equals the documented tuple and a matched
  label's `differences` has one entry per name in order.
- **AC3** — pass the same block as both args; assert all differences `0.0`, all
  `centroid_distance_mm == 0.0`, all `divergence_score == 0.0`, and both case
  aggregates `== 0.0`.
- **AC4** — one label with candidate volume larger than GT (then a second case
  smaller); assert `absolute`/`relative` sign and magnitude via `pytest.approx`.
- **AC5** — deepcopy a two-label block, bump one label's `physical_volume_mm3`;
  assert only that label has `divergence_score > 0` and the other is `0.0`.
- **AC6** — shift one label's candidate `centroid_mm` by `(3, 4, 0)`; assert
  `centroid_distance_mm == 5.0` and that `divergence_score` is unaffected by the
  centroid shift.
- **AC7** — a label with two features differing by known relatives; assert
  `divergence_score == mean(abs(relative))`; a label whose only differing features
  have `gt_value == 0` (or no available feature) → `divergence_score is None`.
- **AC8** — a multi-label block with per-label scores hand-set; assert
  `case_divergence` and `mean_centroid_distance_mm` equal the hand means over
  matched labels; a block with zero matched labels → both `None`.
- **AC9** — a label only in candidate **and** a label only in GT; assert each is
  `matched is False`, `differences == ()`, `centroid_distance_mm is None`,
  `divergence_score is None`, counted in `n_unmatched`, no raise, excluded from
  aggregates.
- **AC10** — candidate block has `stage3.per_label_offsets` for a label, GT block
  omits it; assert that label's `spline_offset_mm` difference is `available is
  False`, `absolute`/`relative` `None`, present side populated, excluded from the
  score; no raise.
- **AC11** — a label whose GT `physical_volume_mm3 == 0.0` and candidate non-zero;
  assert `absolute == candidate_value`, `relative is None`, excluded from score.
- **AC12** — labels named out of anatomical order (e.g. `"L3"` before `"L1"`) plus
  two unmapped labels (`level_name == UNKNOWN`, values `900`/`901`) present on both
  sides; assert `per_label` is sorted by `CANONICAL_ORDER` then value and the two
  unknowns stay distinct.
- **AC13** — `compute_feature_match(None, block)`, `compute_feature_match({}, block)`
  (no `per_label`), and a block whose `per_label` is a list → each
  `pytest.raises(SegQCInputError)`.
- **AC14** — call twice, assert equal results; deepcopy-snapshot both inputs and
  assert unchanged after the call.

Adversarial / edge cases folded in: empty blocks on both sides (`per_label == {}`)
→ `per_label == ()`, counts `0`, aggregates `None`; a matched label with a
negative volume difference (candidate < GT) → negative `absolute`/`relative`; a
label with all tracked features unavailable → `divergence_score is None` but still
`matched is True`; a matched label missing `centroid` entirely →
`centroid_distance_mm is None` without crashing; a Stage-2-only block (no
`stage3`) on both sides → `spline_offset_mm` unavailable everywhere, other
features still compared.

## Dependencies

- **Item 004 (✅)** — `segqc.labels`: `CANONICAL_ORDER`, `UNKNOWN` for anatomical
  ordering and the unknown-name sentinel.
- **Item 003 (✅)** — `segqc.io`: `SegQCInputError` (reused malformed-input type).
- **Items 011 / 013 / 018 + 016 / 022 (✅)** — the `features` block shape produced
  by `feature_report.build_features_block` (`per_label` geometry/centroid entries,
  `stage3.per_label_offsets`) that this module reads. Consumes the *output shape*,
  not the compute code.
- No dependency on the sibling Stage-7 primitives 050 / 052; item **053** (harness)
  depends on this module, not the reverse.

## Decisions & Trade-offs

- Implemented exactly per the Assumptions/Implementation Steps with no
  deviations. `_require_block` checks `isinstance(obj, Mapping)` (from
  `typing`, matching runtime `collections.abc.Mapping` semantics for plain
  dicts) and that `per_label` is itself a `Mapping`, raising
  `SegQCInputError` before any attribute access — matches AC13's "not a raw
  `KeyError`/`TypeError`/`AttributeError`" requirement.
- `LabelFeatureDivergence.name` resolution: GT entry's `level_name` is used
  when present (even for the trivial single-sided case within an unmatched
  entry, since only one side's entry exists there); falls back to the
  candidate entry's `level_name`; defaults to `segqc.labels.UNKNOWN` only if
  neither side supplies a name. This satisfies both AC9 (unmatched — present
  side's name) and AC12 (matched — GT authoritative) with one code path.
  Verified against the test fixtures — `_entry()` in the test helper always
  supplies `level_name`, so the `UNKNOWN` fallback branch is exercised only
  by entries explicitly built with `level_name=UNKNOWN`.
- `_offset_map` and `_scalar_value` read defensively with `.get(...)` and
  `or {}`/`or []` at each hop so a missing `stage3`, missing
  `per_label_offsets`, missing `geometry`, or missing `centroid` block never
  raises — only the top-level `candidate`/`gt` mapping and `per_label`
  mapping are validated per AC13; everything nested is treated as
  optionally-shaped feature-engine output (mirrors AC10's "unavailable, not
  fabricated" contract).
- No new dependencies added; reused `segqc.io.SegQCInputError` and
  `segqc.labels.CANONICAL_ORDER`/`UNKNOWN` exactly as pinned. No divergence
  from the spec's Assumptions was found — item 050's sibling style
  (`overlap.py`) was followed for the `_order_key`/`_CANONICAL_RANK`
  ordering helpers and the frozen-dataclass/`__all__` package shape.
