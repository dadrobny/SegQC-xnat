# Item 059 — Per-label first-order intensity feature extractor

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 059
> **Objectives:** G2 (supplies the intensity feature the Stage-8 implausible-intensity heuristic consumes), G7 (deterministic, regression-testable) — enables G3/G8 downstream
> **Suggested branch:** `aide/059-per-label-first-order-intensity`

---

## Description

Add the core **image-based feature family** for Stage 8 (deliverable 1): a pure,
grid-alignment-guarded module `src/segqc/features/intensity.py` that samples the
**scan** voxels lying under each vertebra **label mask** and computes **per-label
first-order intensity statistics** — the standard radiomics "first-order" family
(mean, median, std, min, max, a documented percentile set, range, IQR, and
intensity entropy). This is the tool's first extractor to read scan voxel
*intensities* (every prior feature consumed only the label map); it is tested
against the intensity-bearing synthetic fixtures item 058 committed under
`tests/corpus/intensity/`.

The module follows the established Stage-2/3 feature convention (see
`src/segqc/features/geometry.py`, `neighbourhood.py`): a frozen, JSON-friendly
per-label result dataclass and a `compute_*` function; read-only inputs;
deterministic; pure NumPy/SciPy with no file I/O.

**In scope:** arrays/images in → per-label first-order intensity features out;
an explicit scan↔label grid-alignment guard; robust sentinel handling for
empty/all-background labels and non-finite (NaN/inf) voxels; a per-case
convenience that maps every present non-zero label to its features.

**Explicitly NOT in scope** (later Stage-8 items, which *consume* this output):
PyRadiomics / higher-order texture/shape features (060); fusion into the JSON
`features` block, the feature table, or the human report (061); any heuristic /
rule firing on intensities (062); reference distributions or the delta-to-
reference intensity rule (063/064); `segqc run` CLI wiring (065). No thresholds
or plausibility judgements are made here — this item only *measures*.

## Acceptance Criteria

- [ ] **AC1: Module & pure public API.** `src/segqc/features/intensity.py` exists
  and exposes a frozen result dataclass `LabelIntensity` and
  `compute_label_intensity(scan_img, seg_img, label) -> LabelIntensity`; the
  module imports only NumPy/SciPy (+ nibabel typing), performs no file I/O, and
  does not import PyRadiomics.

- [ ] **AC2: Documented tracked-feature set.** `LabelIntensity` carries exactly
  the documented first-order fields — `voxel_count` (finite voxels sampled,
  int), `n_nonfinite_excluded` (int), and the statistics `mean`, `median`,
  `std`, `min`, `max`, `p05`, `p25`, `p50`, `p75`, `p95`, `range`, `iqr`,
  `entropy` — each a JSON-friendly scalar (`Optional[float]`), no nibabel objects,
  comparable with `==`.

- [ ] **AC3: Mean & median correct.** On a hand-built scan+mask with known voxel
  values, `mean` and `median` equal the hand-computed values.

- [ ] **AC4: Std correct.** `std` equals the hand-computed **population** standard
  deviation (`ddof=0`, matching the existing `_safe_std` convention).

- [ ] **AC5: Min, max & range correct.** `min` and `max` equal the hand-computed
  extrema and `range == max - min`.

- [ ] **AC6: Percentiles, median identity & IQR correct.** `p05/p25/p50/p75/p95`
  equal the hand-computed percentiles under the documented interpolation
  (`numpy.percentile` linear default), `p50 == median`, and `iqr == p75 - p25`.

- [ ] **AC7: Intensity entropy correct & documented.** `entropy` is the Shannon
  entropy of the masked voxels over a documented fixed-bin histogram (bin count
  and log base documented in the module); it matches the hand-computed value on a
  small multi-valued region.

- [ ] **AC8: Uniform region.** A label covering a uniform-intensity region yields
  that constant for `mean`, `median`, `min`, `max`, and every percentile, with
  `std == 0.0`, `range == 0.0`, `iqr == 0.0`, and `entropy == 0.0`.

- [ ] **AC9: Spacing invariance.** For identical scan and label **arrays**, an
  anisotropic affine/spacing produces first-order statistics identical to an
  isotropic one (voxels are counted once each; stats are not voxel-volume
  weighted).

- [ ] **AC10: Grid-alignment guard — shape.** A scan and segmentation with
  mismatched array shapes raise a clear `ValueError` naming both shapes; no
  silent mis-sampling occurs.

- [ ] **AC11: Grid-alignment guard — affine.** A scan and segmentation with
  incompatible affines (beyond the documented tolerance) raise a clear
  `ValueError`; matching-shape/matching-affine inputs do not.

- [ ] **AC12: Empty / absent-label sentinel.** A label that is absent from the
  segmentation, or whose mask selects no scan voxels, returns a well-formed
  `LabelIntensity` with `voxel_count == 0` and every statistic field set to the
  documented sentinel `None` — it never raises.

- [ ] **AC13: Non-finite voxels excluded.** A masked region containing some
  NaN/inf voxels computes all statistics over the **finite** voxels only and
  reports `n_nonfinite_excluded` equal to the count of excluded voxels (> 0),
  never raising.

- [ ] **AC14: All-non-finite sentinel.** A masked region whose voxels are all
  non-finite yields the sentinel record (`voxel_count == 0`, statistics `None`,
  `n_nonfinite_excluded` equal to the masked voxel count), never raising.

- [ ] **AC15: Per-case convenience.** `compute_intensity_features(scan_img,
  seg_img) -> Dict[int, LabelIntensity]` returns one entry per present non-zero
  label (background `0` excluded), each equal to the corresponding
  `compute_label_intensity` result.

- [ ] **AC16: Purity / immutability.** A call does not mutate the scan or
  segmentation image data (arrays are byte-identical before and after).

- [ ] **AC17: Determinism.** Repeated calls on identical inputs produce
  `LabelIntensity` values that compare equal (`==`).

- [ ] **AC18: Clean-fixture sanity.** On the committed clean intensity fixture
  (`tests/corpus/intensity/`, item 058), each vertebra label's `median` falls
  within that case's `expected_label_hu_bands` from the intensity manifest.

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): no blocking
  questions were asked; each ambiguity below is resolved with the most defensible
  default and pinned here for validator audit.
- **Input types (pin).** The primary functions take **`nibabel.Nifti1Image`**
  objects (`scan_img`, `seg_img`) plus an `int` label, matching the existing
  feature family (`compute_label_geometry(seg_img, label)`) and giving the
  alignment guard access to `.shape` and `.affine`. Spacing/affine come from the
  image headers (as in `geometry._get_spacing` / `io._spacing_from_affine`). If
  the builder finds an array-based signature materially cleaner for item 061's
  fusion, an equivalent array+affine overload is acceptable **provided** all ACs
  still hold on `Nifti1Image` inputs.
- **Sentinel value = `None` (pin).** Empty/all-non-finite statistics are `None`,
  **not** `float('nan')`. Rationale: `None` is JSON-null-friendly for item 061 and
  compares equal across calls (`NaN != NaN` would break AC17). Fields are typed
  `Optional[float]`.
- **Empty label → sentinel, not `ValueError` (pin).** Unlike
  `compute_label_geometry`, which raises on an absent label, this extractor
  returns a sentinel record for empty/all-background labels (per the queue's
  "well-formed sentinels rather than crashes"), so item 061's per-label fusion
  never crashes on a zero-voxel label. A structural scan↔label *misalignment*
  (AC10/AC11) still raises, because that is a caller error, not a per-label data
  condition.
- **Non-finite handling = exclude-then-compute (pin).** NaN/inf voxels inside a
  mask are dropped before statistics are computed (radiomics practice); the count
  is recorded in `n_nonfinite_excluded`. If no finite voxels remain, the label
  falls back to the AC12/AC14 sentinel.
- **Percentile set & interpolation (pin).** Tracked percentiles are
  `{5, 25, 50, 75, 95}` via `numpy.percentile` default (linear) interpolation;
  `median == p50`, `iqr == p75 - p25`, `range == max - min`.
- **Std convention (pin).** Population std, `ddof=0` (consistent with
  `neighbourhood._safe_std`).
- **Entropy definition (pin, documented in module).** Shannon entropy over a
  fixed-count histogram of the masked finite voxels; **default 32 bins**, log
  base **2 (bits)**, spanning the region's `[min, max]`; a single-valued region
  gives entropy `0.0`. Exact default is documented in the module docstring and may
  be adjusted by the builder as long as AC7/AC8 hold and the choice is documented.
- **Affine-tolerance (pin).** The alignment guard treats affines as compatible
  within the same tolerance `io.load_case` uses (`rtol=1e-5, atol=1e-4`); shape
  must match exactly.
- **Dependency 058 is ✅ (verified).** The committed intensity corpus and the
  `expected_label_hu_bands` manifest field exist at `tests/corpus/intensity/`
  (`src/segqc/synth/intensity.py`); AC18 relies on that interface. If it diverges,
  hand back.

## Implementation Steps

_Intended code path under `src/segqc` (`aide.toml` `source_dir = "src/segqc"`)._

1. Create `src/segqc/features/intensity.py` with a module docstring documenting
   the tracked-feature set, the sentinel (`None`) and non-finite policy, and the
   entropy definition (bins/base). Set `__all__ = ["LabelIntensity",
   "compute_label_intensity", "compute_intensity_features"]`.
2. Define the frozen dataclass `LabelIntensity` with the AC2 fields
   (`voxel_count: int`, `n_nonfinite_excluded: int`, and the `Optional[float]`
   statistics).
3. Add an alignment guard helper: compare `scan_img` and `seg_img` array shapes
   (exact) and affines (`np.allclose`, `rtol=1e-5, atol=1e-4`); raise a clear
   `ValueError` naming the mismatch (mirror `io.load_case`'s message style).
4. Implement `compute_label_intensity(scan_img, seg_img, label)`: read arrays
   read-only (`np.asanyarray`), build the boolean mask `seg == label`, gather the
   scan values under the mask, split finite vs non-finite, record
   `n_nonfinite_excluded`. If no finite voxels → return the `None`-filled
   sentinel with `voxel_count == 0`. Otherwise compute mean/median/std/min/max,
   the percentile vector, range, IQR, and entropy over the finite values; return a
   populated `LabelIntensity`.
5. Implement `compute_intensity_features(scan_img, seg_img)`: enumerate present
   non-zero labels (as `io._label_inventory` / `geometry` do) and return
   `{label: compute_label_intensity(...)}`.
6. Keep all math NumPy/SciPy, no I/O, no PyRadiomics, no mutation of inputs.
   Do **not** touch `features/__init__.py`, `report.py`, `feature_report.py`,
   `heuristics/*`, `config.py`, or the CLI (those are items 061/062/065).

## Testing Strategy

_One focused test per AC plus adversarial/edge cases; new module
`tests/test_features_intensity.py`._

- **Hand-built fixtures.** Construct tiny `Nifti1Image` scan+seg pairs in-memory
  (small arrays with known voxel values and diagonal affines) so mean/median/std/
  min/max/percentiles/range/IQR/entropy are hand-verifiable — cover AC3–AC8.
- **Spacing invariance (AC9).** Same arrays, two affines (isotropic vs
  anisotropic zooms); assert statistics are identical.
- **Alignment guards (AC10/AC11).** Mismatched-shape and mismatched-affine pairs
  raise `ValueError` with an informative message; a compatible pair does not.
- **Sentinels (AC12/AC14).** Absent label and all-background mask → `voxel_count
  == 0`, all stats `None`; an all-NaN masked region → sentinel with
  `n_nonfinite_excluded == mask voxel count`. Assert no exception.
- **Non-finite mix (AC13).** A region with a few NaN/inf voxels among finite ones
  → stats over the finite subset, `n_nonfinite_excluded` correct.
- **Per-case map (AC15).** `compute_intensity_features` keys == present non-zero
  labels; each value equals the single-label call.
- **Purity & determinism (AC16/AC17).** Snapshot input arrays (`.copy()`) and
  assert byte-equality post-call; call twice and assert `==`.
- **Corpus sanity (AC18).** Load the committed clean case from
  `tests/corpus/intensity/` (via `segqc.synth.intensity.load_intensity_manifest`
  / `segqc.io.load_case`); assert each label's `median` is within
  `expected_label_hu_bands`.
- **Adversarial extras.** Single-voxel label (std/range/iqr/entropy all `0.0`);
  negative HU values (soft-tissue/air) handled; label present but only one finite
  voxel.

## Dependencies

- **Item 058 — Intensity-bearing synthetic scan fixtures (✅).** Provides the
  committed `tests/corpus/intensity/` scan+label fixtures and the
  `expected_label_hu_bands` manifest field this extractor is tested against
  (AC18) — `src/segqc/synth/intensity.py`.
- **Item 003 — I/O & volume model (✅).** `segqc.io` (`load_case`, spacing/affine
  conventions, `SegQCInputError`) informs the alignment-guard tolerances and the
  fixture-loading path in tests.
- **Stage-2/3 feature family (✅).** `src/segqc/features/geometry.py`,
  `neighbourhood.py` — the frozen-dataclass + `compute_*` convention this module
  matches (no new item dependency; pattern reference only).

Gates (do not implement here): 060, 061, 062, 063 all depend on this extractor.

## Decisions & Trade-offs

To be updated during implementation.
