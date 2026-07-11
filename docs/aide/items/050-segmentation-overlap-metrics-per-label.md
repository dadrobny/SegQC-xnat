# Item 050 — Segmentation-overlap metrics: per-label & aggregate DICE vs GT

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (G3, G7)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 050
> **Objectives:** G7 (evaluable / regression-testable — supplies the §8 level-2
> **DICE vs GT** metric primitive); supports G3 (quantifies segmentation
> divergence, the proxy the Stage-7 calibration correlates flags against)
> **Suggested branch:** `aide/050-segmentation-overlap-metrics-per-label`

---

## Description

Provide the **DICE vs GT** comparison layer — level 2 of the vision's §8 three-level
evaluation (QC verdict; **segmentation overlap**; feature-set match). Deliver a
**pure, spacing-aware** module `segqc/eval/overlap.py` that, given a **candidate**
instance label map and a **ground-truth (GT)** instance label map (numpy integer
arrays), matches labels by anatomical level via the Stage-0 convention
(`segqc/labels.py`) and computes:

- **per-label DICE** (Sørensen–Dice coefficient) **and Jaccard** index, and
- **aggregate** scores over the **matched** labels: an **unweighted mean** and a
  **physical-volume-weighted mean** (weight = GT physical volume of the label).

Real-world asymmetry is handled explicitly: a label present in one map but absent
in the other is reported as an **unmatched** entry with DICE/Jaccard `0.0` (never a
crash), and is **excluded** from the aggregate means (the aggregates are "over
matched labels" per the queue). Empty inputs (no non-zero labels) yield a
well-formed empty result with `None` aggregate sentinels — no divide-by-zero.

This is the **first module of Stage 7** and therefore creates the new
`segqc/eval/` package. It is one of three independent comparison primitives
(050 DICE / overlap, 051 feature-set match, 052 verdict-outcome) that item 053's
evaluation harness will assemble per case.

**In scope:** the new `segqc/eval/__init__.py`; `segqc/eval/overlap.py` containing
the `LabelOverlap` and `OverlapResult` frozen dataclasses and the
`compute_overlap(...)` function; and `tests/test_050_overlap.py`.

**Out of scope (do NOT):** file/NIfTI I/O or loading (the caller passes
`case.seg.data` and `case.seg.spacing` — arrays in, scores out); recomputing or
touching the existing **`segqc/features/overlap.py`** (item 015 — that detects
self-overlap *within a single* boolean mask stack; it is a different concern and is
not modified); any cohort/harness/metrics/correlation logic (items 053/054 —
this module produces per-case overlap numbers only, no cross-case aggregation and
no verdict/flag interpretation); feature-set divergence (item 051); mutating any
Stage 0–6 module; changing the CLI, config, or report schema.

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each in
`tests/test_050_overlap.py` (see Testing Strategy)._

- [ ] **AC1: module & public API exist.** `segqc.eval.overlap` exposes
  `compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0), *, convention=None)
  -> OverlapResult`, plus frozen dataclasses `LabelOverlap` and `OverlapResult`;
  all three are listed in the module `__all__` and importable both as
  `from segqc.eval.overlap import compute_overlap, LabelOverlap, OverlapResult`
  and (re-exported) `from segqc.eval import compute_overlap`. `LabelOverlap`
  carries fields `value: int`, `name: str`, `matched: bool`, `dice: float`,
  `jaccard: float`, `candidate_voxels: int`, `gt_voxels: int`,
  `intersection_voxels: int`, `physical_volume_mm3: float`. `OverlapResult`
  carries `per_label: Tuple[LabelOverlap, ...]`, `mean_dice: Optional[float]`,
  `volume_weighted_dice: Optional[float]`, `mean_jaccard: Optional[float]`,
  `n_matched: int`, `n_unmatched: int`.

- [ ] **AC2: identical maps → DICE 1.0 per label.** When `candidate` and `gt` are
  equal arrays with ≥1 non-zero label, every `per_label` entry has
  `matched is True`, `dice == 1.0`, `jaccard == 1.0`, and
  `intersection_voxels == candidate_voxels == gt_voxels`; and `mean_dice == 1.0`,
  `mean_jaccard == 1.0`, `volume_weighted_dice == 1.0`.

- [ ] **AC3: disjoint masks → DICE 0.0.** For a label value present in **both**
  maps but occupying **disjoint** voxel regions (no shared voxel), its
  `LabelOverlap` has `matched is True`, `intersection_voxels == 0`, `dice == 0.0`,
  `jaccard == 0.0`; with that as the only label, `mean_dice == 0.0`.

- [ ] **AC4: half-overlap matches the hand-computed DICE/Jaccard.** For a label
  with candidate voxel count `a`, GT count `b`, and intersection `i` chosen so the
  overlap is partial, `dice == 2*i / (a + b)` and `jaccard == i / (a + b - i)`
  to floating-point tolerance, matching the values computed by hand for the
  fixture.

- [ ] **AC5: a label present in only one map is unmatched, not an error.** A label
  value present in `candidate` but absent from `gt` (and, symmetrically, present in
  `gt` but absent from `candidate`) produces a `LabelOverlap` with
  `matched is False`, `dice == 0.0`, `jaccard == 0.0`, and the absent side's voxel
  count `0`; `compute_overlap` raises **no** exception. Such entries are counted in
  `n_unmatched` and **excluded** from `mean_dice`/`mean_jaccard`/
  `volume_weighted_dice`.

- [ ] **AC6: unweighted aggregates are the mean over matched labels only.** With a
  mix of matched and unmatched labels, `mean_dice` equals the arithmetic mean of
  the matched entries' `dice` (unmatched entries excluded), `mean_jaccard`
  likewise over `jaccard`, and `n_matched` / `n_unmatched` equal the respective
  counts.

- [ ] **AC7: volume-weighted aggregate uses GT physical volume.** For every entry,
  `physical_volume_mm3 == gt_voxels * sx * sy * sz` (spacing `(sx, sy, sz)`); and
  `volume_weighted_dice == sum(e.dice * e.physical_volume_mm3) /
  sum(e.physical_volume_mm3)` over the **matched** entries (hand-computed for the
  fixture). With matched labels of **unequal** physical volume and differing DICE,
  `volume_weighted_dice != mean_dice`.

- [ ] **AC8: per-label DICE/Jaccard are spacing-invariant (ratio-based).** For the
  same `candidate`/`gt` arrays computed once with isotropic spacing
  `(1.0, 1.0, 1.0)` and once with anisotropic spacing (e.g. `(0.5, 1.0, 3.0)`),
  every entry's `dice`, `jaccard`, and the `mean_dice`/`mean_jaccard` aggregates
  are **identical**; only `physical_volume_mm3` (and hence the weighting inside
  `volume_weighted_dice`) reflects the spacing.

- [ ] **AC9: empty inputs yield a well-formed empty result.** When both arrays have
  no non-zero labels (all background), the result has `per_label == ()`,
  `n_matched == 0`, `n_unmatched == 0`, and `mean_dice`, `mean_jaccard`,
  `volume_weighted_dice` all `None` — no exception, no divide-by-zero.

- [ ] **AC10: labels are named and ordered via the Stage-0 convention.** Each
  `LabelOverlap.name` equals `convention.name_of(value)` (default convention: value
  `20` → `"L1"`, value `22` → `"L3"`); `per_label` is ordered head-to-tail by
  `segqc.labels.CANONICAL_ORDER` for recognised labels, with unrecognised labels
  placed after them ordered by ascending integer `value`.

- [ ] **AC11: unmapped labels match by value and are not collapsed.** Two distinct
  integer labels with **no** mapping in the convention (each `name == segqc.labels.
  UNKNOWN`), present in both maps, produce **two separate** `LabelOverlap` entries
  with independent DICE keyed on their integer `value` — never merged into one
  "unknown" bucket. (Matching is by integer label value; the convention supplies
  only the display name and ordering.)

- [ ] **AC12: mismatched array shapes raise `SegQCInputError`.** Calling
  `compute_overlap` with `candidate` and `gt` of different `shape` raises
  `segqc.io.SegQCInputError` (a clear input error), not a raw numpy broadcasting
  `ValueError`.

- [ ] **AC13: pure, deterministic, and non-mutating.** Two `compute_overlap` calls
  on the same inputs return equal `OverlapResult`s (equal `per_label` ordering and
  values, equal aggregates); the `candidate` and `gt` arrays are byte-for-byte
  unchanged after the call; the function performs no file I/O.

## Assumptions  <!-- MANDATORY: clarify mode = assume -->

- **Match key is the integer label value; the convention supplies name + order
  (clarify `assume`).** The queue says "matches labels by anatomical level via the
  Stage-0 convention." Both candidate and GT are vertebra **instance** label maps
  under the *same* integer→anatomy scheme (vision §10 assumption; `labels.py`'s
  `DEFAULT_LABEL_MAP` is bijective on known labels), so "label 22 in candidate vs
  label 22 in GT" *is* "L3 vs L3". This spec therefore **matches by integer label
  value** and uses `LabelConvention` only to attach the anatomical `name` and to
  order results. Rationale: matching by *name* would collapse **all** unmapped
  labels into the single `UNKNOWN` sentinel and silently merge distinct vertebrae
  (see AC11) — matching by value is robust to that. A **single** `convention`
  parameter (default `LabelConvention.default()`) applies to both maps; distinct
  per-map conventions (a segmenter with its own numbering vs VerSe GT) are **out of
  scope** for this primitive — the harness (053) can pre-map labels if ever needed.

- **Background label `0` is excluded.** Only non-zero labels are compared,
  consistent with `Case.label_inventory` (item 003) which excludes background. The
  candidate label set is `set(np.unique(candidate)) | set(np.unique(gt))` minus
  `{0}`.

- **The volume weight is the GT physical volume.** `volume_weighted_dice` weights
  each matched label by `gt_voxels * sx * sy * sz` — the **ground-truth** vertebra
  volume, i.e. how large the true structure is. (Alternatives were the candidate
  volume or the mean of the two; GT is chosen as the reference truth and is always
  well-defined for a matched label.) The per-label `physical_volume_mm3` field
  records exactly this GT-based volume.

- **Aggregates are computed over MATCHED labels only; empty ⇒ `None` sentinel.**
  Per the queue wording ("aggregate … over matched labels"), `mean_dice`,
  `mean_jaccard`, and `volume_weighted_dice` average only entries with
  `matched is True`. Unmatched labels are still reported in `per_label` (with
  `dice == jaccard == 0.0`) for visibility but excluded from the aggregates. When
  there are **no** matched labels (including the empty-input case), each aggregate
  is `None` (an explicit "not applicable" sentinel), never `0.0` and never a
  divide-by-zero. Downstream metrics (054) may choose to treat unmatched labels as
  0 themselves; this primitive does not bake that policy in.

- **Inputs are numpy integer label arrays of identical shape plus a spacing
  triple.** `spacing` defaults to isotropic `(1.0, 1.0, 1.0)`. The two arrays must
  have equal `shape`; a mismatch is a caller input error → `SegQCInputError`
  (AC12). No `Volume`/`Case`/file arguments and no I/O — a caller with a `Case`
  passes `case.seg.data` and `case.seg.spacing` (spacing derived from the affine by
  the item-003 loader). Arrays are read-only inputs (never mutated).

- **Interface pins (dependencies already ✅).** From item 004 `segqc.labels`:
  `LabelConvention` (`.default()`, `.name_of(value) -> str`), `CANONICAL_ORDER`,
  and `UNKNOWN` — used for naming/ordering exactly as `summarise_inventory`
  already does. From item 003 `segqc.io`: `SegQCInputError` — reused as the single
  input-error type (consistent with the loader and `labels.from_mapping`). If
  either interface has diverged from this description, the builder/validator should
  hand back.

- **Both DICE and Jaccard are reported** (queue: "per-label DICE (and Jaccard)").
  Jaccard `= i / (a + b - i)`; DICE `= 2i / (a + b)`. For any label present in ≥1
  map, `a + b > 0`, so no per-label divide-by-zero can occur; the guard is only for
  the (never-iterated) both-absent case.

## Implementation Steps

Code path in `src/segqc/` (`aide.toml` `source_dir = src/segqc`).

1. **Create the `segqc/eval/` package.** Add `src/segqc/eval/__init__.py` with a
   short module docstring naming it the Stage-7 evaluation package, and re-export
   the public overlap API (`from .overlap import compute_overlap, LabelOverlap,
   OverlapResult`) with a matching `__all__`.

2. **`src/segqc/eval/overlap.py` — module docstring + imports.** Docstring stating:
   §8 level-2 DICE-vs-GT overlap; pure, spacing-aware, no I/O; matches by integer
   label value, names/orders via `segqc.labels`; DICE/Jaccard definitions; the
   distinction from `segqc.features.overlap` (self-overlap within one map). Import
   `numpy`, `dataclasses.dataclass`, typing helpers, `LabelConvention`,
   `CANONICAL_ORDER`, `UNKNOWN` from `segqc.labels`, and `SegQCInputError` from
   `segqc.io`. Declare `__all__`.

3. **`LabelOverlap` frozen dataclass** with the fields listed in AC1.

4. **`OverlapResult` frozen dataclass** with the fields listed in AC1.

5. **Ordering helper.** A private `_order_key(value, name)` returning
   `(rank, value)` where `rank` is the index in `CANONICAL_ORDER` for a recognised
   `name` and `len(CANONICAL_ORDER)` otherwise — so recognised labels sort
   head-to-tail and unrecognised ones sort after by ascending value (mirroring
   `labels._order_key`).

6. **`compute_overlap(candidate, gt, spacing=(1.0, 1.0, 1.0), *, convention=None)`.**
   1. `convention = convention or LabelConvention.default()`.
   2. Coerce `candidate`/`gt` via `np.asarray`; if
      `candidate.shape != gt.shape`, raise `SegQCInputError` with a clear message.
   3. `voxel_volume = float(spacing[0]) * float(spacing[1]) * float(spacing[2])`.
   4. `labels = sorted({int(v) for v in np.unique(candidate)} |
      {int(v) for v in np.unique(gt)} - {0})`; iterate in `_order_key` order.
   5. For each label value `v`: `A = candidate == v`, `B = gt == v`;
      `a = int(A.sum())`, `b = int(B.sum())`, `i = int((A & B).sum())`;
      `matched = a > 0 and b > 0`;
      `dice = (2.0 * i / (a + b)) if (a + b) > 0 else 0.0`;
      `jaccard = (i / (a + b - i)) if (a + b - i) > 0 else 0.0`;
      `phys = b * voxel_volume`. Append a `LabelOverlap(value=v,
      name=convention.name_of(v), matched=matched, dice=dice, jaccard=jaccard,
      candidate_voxels=a, gt_voxels=b, intersection_voxels=i,
      physical_volume_mm3=phys)`.
   6. Compute aggregates over `matched` entries only: `mean_dice`/`mean_jaccard`
      as arithmetic means, `volume_weighted_dice` as
      `sum(e.dice * e.physical_volume_mm3) / sum(e.physical_volume_mm3)`; each is
      `None` when there are no matched entries (or, for the weighted mean, when the
      weight sum is `0`).
   7. Return `OverlapResult(per_label=tuple(entries), mean_dice=…,
      volume_weighted_dice=…, mean_jaccard=…, n_matched=…, n_unmatched=…)`.

7. **Never mutate inputs.** Use only read-only numpy operations on `candidate`/
   `gt`; do not write back. No file access anywhere in the module.

## Testing Strategy

One focused test per AC in **`tests/test_050_overlap.py`**, built on tiny
hand-constructed integer arrays (e.g. 1-D or small 3-D `np.zeros(..., dtype=int)`
with slices assigned label values) so every expected DICE/Jaccard is hand-computed
and exact. No fixtures on disk, no loader — arrays are built inline.

- **AC1** — import the three names from both `segqc.eval.overlap` and
  `segqc.eval`; assert dataclasses are frozen and expose the documented fields.
- **AC2** — `candidate == gt` with two labels; assert all `dice/jaccard == 1.0`
  and all three aggregates `== 1.0`.
- **AC3** — one label value on disjoint index ranges in the two arrays; assert
  `intersection_voxels == 0`, `dice == jaccard == 0.0`, `mean_dice == 0.0`.
- **AC4** — construct `a`, `b`, `i` (e.g. `a=10`, `b=8`, `i=4`); assert
  `dice == 2*4/18` and `jaccard == 4/(18-4)` via `pytest.approx`.
- **AC5** — a label only in candidate **and** a label only in GT; assert each is
  `matched is False`, `dice == jaccard == 0.0`, the absent-side count `0`, no
  raise, and both are excluded from the aggregates / counted in `n_unmatched`.
- **AC6** — mix matched + unmatched labels; assert `mean_dice`/`mean_jaccard`
  equal the hand mean over matched only and `n_matched`/`n_unmatched` are correct.
- **AC7** — two matched labels of unequal voxel counts with different DICE and a
  known spacing; assert each `physical_volume_mm3 == gt_voxels*sx*sy*sz`,
  `volume_weighted_dice` equals the hand weighted mean, and `!= mean_dice`.
- **AC8** — same arrays, spacing `(1,1,1)` vs `(0.5,1,3)`; assert per-label
  `dice`/`jaccard` and `mean_dice`/`mean_jaccard` identical across the two calls,
  while `physical_volume_mm3` scales with spacing.
- **AC9** — two all-zero arrays; assert `per_label == ()`, counts `0`, and all
  three aggregates `is None`.
- **AC10** — labels `20` and `22`; assert names `"L1"`, `"L3"` and that a fixture
  with an out-of-canonical-order label set still returns `per_label` sorted by
  `CANONICAL_ORDER` (recognised) then value (unrecognised).
- **AC11** — two unmapped integer labels (e.g. `900`, `901`) present in both maps;
  assert two separate entries, each `name == UNKNOWN`, with independent DICE.
- **AC12** — arrays of different shape; `pytest.raises(SegQCInputError)`.
- **AC13** — call twice, assert equal results; snapshot the input arrays
  (`.copy()`) and assert unchanged after the call.

Adversarial / edge cases folded in: a single-voxel label; a label whose voxels are
fully contained in the other (asymmetric sizes, DICE < 1); a label present in
candidate with zero intersection but non-zero GT (matched, DICE 0); a negative or
very large unmapped integer label (named `UNKNOWN`, still computed); zero spacing
component making `physical_volume_mm3 == 0` while ratio DICE is unaffected
(volume-weighted mean falls back to `None` only if *all* weights are 0).

## Dependencies

- **Item 004 (✅)** — `segqc.labels`: `LabelConvention.default()` / `.name_of`,
  `CANONICAL_ORDER`, `UNKNOWN` for naming and anatomical ordering.
- **Item 003 (✅)** — `segqc.io`: `SegQCInputError` (reused input-error type); and
  the `Case`/`Volume` model whose `.seg.data` / `.seg.spacing` a caller feeds in
  (this module takes arrays + spacing, not the `Case` itself).
- No dependency on the sibling Stage-7 primitives 051 / 052; item **053** (harness)
  depends on this module, not the reverse.

## Decisions & Trade-offs

To be updated during implementation.
