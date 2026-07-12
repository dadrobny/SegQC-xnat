# Item 058 — Intensity-bearing synthetic scan fixtures (HU-painted GT + implausible variants)

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features (Phase 2)
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 058 *(the Stage-8 fixture foundation; gates 059–065)*
> **Objectives:** G7 (evaluable & regression-testable — reproducible, committed
> intensity-bearing fixtures that make Stage-8 image features locally testable
> under `pytest` with no external CT), enabling the Stage-8 image-based extension
> of G2/G3 (intensity heuristics grounded on plausible/implausible HU inputs).
> **Suggested branch:** `aide/058-intensity-bearing-synthetic-scan-fixtures`

---

## Description

Every prior stage consumed only the **label map**; `segqc.io.load_case` loads a
scan alongside it but the scan's **voxel intensities have never been read**, so the
repo ships **no intensity-bearing scan fixtures** (the Stage-5 corpus commits a
single trivial `base_scan.nii.gz` — a plain axis-0 ramp with no anatomical HU
meaning). Stage 8 introduces the tool's first use of scan intensities, so it must
**start** by giving every downstream Stage-8 item (059–065) deterministic,
locally-generated scan inputs whose intensities plausibly (and, deliberately,
implausibly) model CT Hounsfield units under each vertebra label.

This item extends the Stage-5 synthetic generator (`src/segqc/synth/*`) with a new
module `src/segqc/synth/intensity.py` that:

1. **Paints a bone-plausible HU scan** co-registered with a clean-GT label map:
   each vertebra body gets a **cortical rim** (brighter) enclosing a **cancellous
   interior** (moderate HU), over a **soft-tissue background**, with mild seeded
   per-voxel variation — on the **same grid, spacing and affine** as the label map.

2. **Derives implausible-intensity variants** from that clean scan: a chosen
   vertebra's voxels are overwritten with **metal-bright**, **soft-tissue-low**, or
   **degenerate-uniform** HU. Each variant differs from the clean scan **only
   inside the targeted label's mask**; the **label map is byte-identical to the
   clean GT** (the corruption is purely an intensity phenomenon — the segmentation
   is unchanged). These are the inputs item 062's implausible-intensity heuristic
   and item 065's acceptance suite will exercise.

3. **Materialises a small committed intensity corpus** — a versioned
   `tests/corpus/intensity/manifest.json` plus per-case `.nii.gz` fixtures under
   `tests/corpus/intensity/fixtures/` — via a one-command regeneration entry point
   (`python -m segqc.synth.intensity`), mirroring the Stage-5 corpus builder
   (item 040). The manifest records, per case, the fixture paths, the HU model
   used, the target label, and the **expected per-label HU bands** so downstream
   items have a single, drift-proof source of ground-truth expectations.

### Scope boundary — what this item is **not**

- **No feature extraction.** The per-label first-order intensity extractor is
  item 059; this item computes **no** intensity features (its tests may *sample*
  arrays under a mask to assert HU ranges, but ship no reusable extractor).
- **No heuristics / rules / config.** The implausible-intensity rule is item 062;
  bone-plausibility *thresholds for judgement* are item 062's concern. The HU
  bands recorded here are **generator ground truth** (what was painted), not
  QC decision thresholds.
- **No report / schema / reference changes.** Items 061 (fusion) and 063/064
  (reference intensity) own those. No edit to `report.py`, `config.py`,
  `heuristics/*`, `features/*`, or `reference/*`.
- **Does not modify the existing Stage-5 geometric corpus.** `tests/corpus/`'s
  `base_scan.nii.gz`, per-mode seg fixtures, `manifest.json`, and
  `golden/*.json` (items 040–042) stay **byte-identical** — the intensity corpus
  is a **new, parallel** directory (`tests/corpus/intensity/`). It must **not**
  edit `clean_gt.py`, `perturbation.py`, `corpus.py`, `golden.py`, or the
  operator modules, and must leave items 040–042's tests green.

---

## Public interface (the surface items 059–065 consume)

New module `src/segqc/synth/intensity.py`, additively re-exported from
`segqc.synth` (`__init__.py` gains import lines + `__all__` entries).

```python
# --- HU model (documented, tunable defaults) --------------------------------
@dataclass(frozen=True)
class HUModel:
    background_mean: float; background_std: float     # soft-tissue background
    cancellous_mean: float; cancellous_std: float     # trabecular interior
    cortical_mean:   float; cortical_std:   float      # cortical rim (brighter)
    dtype: str = "int16"                               # CT-like signed 16-bit

DEFAULT_HU_MODEL: HUModel   # see Assumptions for the pinned constants

@dataclass(frozen=True)
class ImplausibleFill:
    name: str        # "metal" | "soft_tissue" | "degenerate_uniform"
    mean: float
    std:  float      # std == 0.0 => a single constant value (degenerate)

IMPLAUSIBLE_FILLS: dict[str, ImplausibleFill]   # the three canonical fills

# --- pure painters (arrays/images in, scan Nifti1Image out; no disk I/O) ----
def paint_clean_scan(seg_img, *, seed=0, model=DEFAULT_HU_MODEL) -> Nifti1Image:
    """Paint a bone-plausible HU scan onto seg_img's labels: cortical rim
    (eroded-boundary shell) + cancellous interior per label, over a soft-tissue
    background, with seeded per-voxel Gaussian variation. Same shape/affine as
    seg_img; dtype int16. Non-mutating; deterministic for a fixed (seed, model)."""

def paint_implausible_variant(clean_scan_img, seg_img, *, target_label,
                              fill, seed=0) -> Nifti1Image:
    """Return a scan equal to clean_scan_img except that target_label's voxels
    are overwritten with `fill` HU (seeded). Label map is NOT touched. Same
    shape/affine; deterministic."""

# --- committed intensity corpus (mirrors segqc.synth.corpus, item 040) ------
INTENSITY_CORPUS_DIR: Path        # .../tests/corpus/intensity
INTENSITY_MANIFEST_PATH: Path     # .../tests/corpus/intensity/manifest.json
INTENSITY_FIXTURES_DIRNAME: str = "fixtures"
INTENSITY_MANIFEST_VERSION: int = 1

def build_intensity_corpus() -> list["IntensityCase"]:  # in-memory recipe -> cases
def write_intensity_corpus(dest: Path) -> Path:         # materialise; byte-stable
def load_intensity_manifest(path=INTENSITY_MANIFEST_PATH) -> dict:
def main(argv=None) -> int:  # `python -m segqc.synth.intensity [--out DIR]`
```

### Intensity manifest schema (`tests/corpus/intensity/manifest.json`, versioned)

```json
{
  "manifest_version": 1,
  "generator": "segqc.synth.intensity",
  "hu_model": {"background_mean": 40, "background_std": 10,
               "cancellous_mean": 200, "cancellous_std": 40,
               "cortical_mean": 600, "cortical_std": 120, "dtype": "int16"},
  "cases": [
    {
      "case_id": "clean_hu",
      "variant": "clean",
      "plausible": true,
      "target_label": null,
      "fill": null,
      "seed": 0,
      "base": {"levels": ["L1","L2","L3","L4","L5"],
               "spacing": [1.0,1.0,1.0], "curve_amplitude_mm": 6.0},
      "scan_fixture": "fixtures/clean_hu_scan.nii.gz",
      "seg_fixture":  "fixtures/clean_spine_seg.nii.gz",
      "expected_label_hu_bands": {"20": [100,1500], "21": [100,1500],
               "22": [100,1500], "23": [100,1500], "24": [100,1500]}
    },
    {
      "case_id": "implausible_metal",
      "variant": "metal", "plausible": false, "target_label": 22,
      "fill": {"name": "metal", "mean": 3000, "std": 100},
      "seed": 0, "base": { ... },
      "scan_fixture": "fixtures/implausible_metal_scan.nii.gz",
      "seg_fixture":  "fixtures/clean_spine_seg.nii.gz",
      "expected_label_hu_bands": {"22": [2500, 32767]}
    }
    // ... implausible_soft_tissue (label 22 -> [-200,100]),
    //     degenerate_uniform     (label 22 -> a single constant)
  ]
}
```

- All cases share **one** `seg_fixture` (`clean_spine_seg.nii.gz` — the default
  `build_clean_spine()` seg; the label map is identical across every case).
- `expected_label_hu_bands` is the **generator ground truth**: for the clean case,
  every present label's painted-median band; for an implausible case, the
  **target** label's corrupted band. Copied verbatim from the painter's model so
  the manifest can never drift from what was painted.
- Fixture paths are **relative to the manifest directory** (relocatable corpus).

---

## Acceptance Criteria

_One test per criterion. "Under label L" means the voxels of the loaded seg where
`seg.data == L`. "The clean scan" is `paint_clean_scan(seg_img)` with defaults;
"a loaded case" is `segqc.io.load_case(scan_path, seg_path)` on a case's resolved
fixture paths. HU constants referenced are `DEFAULT_HU_MODEL` /
`IMPLAUSIBLE_FILLS` values (see Assumptions)._

### A. Clean HU painter

- [ ] **AC1: The clean scan is grid-aligned with the label map.**
      `paint_clean_scan(seg_img)` returns a `Nifti1Image` whose array shape equals
      `seg_img`'s, whose affine is `np.array_equal` to `seg_img.affine`, and whose
      array dtype is `int16`.

- [ ] **AC2: Each vertebra is painted in a bone-plausible HU band.** For every
      present label `L`, the **median** HU of the clean scan under `L` lies within
      the documented bone-plausible band `[100, 1500]` HU (inclusive).

- [ ] **AC3: Cortical rim is brighter than cancellous interior.** For every present
      label `L`, the **mean** HU over the rim voxels (mask minus its one-voxel
      binary erosion) exceeds the mean HU over the interior voxels (the eroded
      mask) by a strictly positive documented margin.

- [ ] **AC4: Background is soft-tissue-low and separable from bone.** The median HU
      over **non-labelled** (background) voxels lies within
      `background_mean ± 3·background_std`, and is strictly below the minimum
      per-label median across all vertebrae (bone and background do not overlap).

- [ ] **AC5: The painter does not mutate its input.** The `seg_img` array is
      `np.array_equal` before and after `paint_clean_scan(seg_img)` (a defensive
      copy of the seg array taken before the call still matches after).

- [ ] **AC6: The clean painter is deterministic and seeded.** Two
      `paint_clean_scan(seg_img, seed=0)` calls return `np.array_equal` arrays;
      `paint_clean_scan(seg_img, seed=1)` differs from the `seed=0` array while
      still satisfying AC2 (all randomness derives from `seeded_rng`, never the
      global RNG).

### B. Implausible-intensity variants

- [ ] **AC7: A variant differs from the clean scan only inside the target mask.**
      For the metal variant with `target_label=22`, the variant array equals the
      clean array (`np.array_equal`) at all voxels where `seg.data != 22`, and is
      **not** equal at some voxel where `seg.data == 22`; the seg array passed in
      is unchanged (label map untouched).

- [ ] **AC8: The metal variant paints implausibly bright HU on the target.** The
      median HU under the target label in the metal variant is `>= 2500` HU
      (far above the bone-plausible band's upper bound of 1500).

- [ ] **AC9: The soft-tissue variant paints implausibly low HU on the target.** The
      median HU under the target label in the soft-tissue variant is `<= 100` HU
      (below the bone-plausible band's lower bound), i.e. within a soft-tissue band.

- [ ] **AC10: The degenerate-uniform variant is constant on the target.** In the
      degenerate-uniform variant, the set of distinct HU values under the target
      label has size exactly 1 (zero variance).

- [ ] **AC11: Variants preserve geometry and are deterministic.**
      `paint_implausible_variant(...)` returns a scan whose shape equals and whose
      affine is `np.array_equal` to `seg_img`'s; two calls with the same
      `(target_label, fill, seed)` return `np.array_equal` arrays.

### C. Committed intensity corpus & manifest

- [ ] **AC12: The intensity manifest loads and is versioned.**
      `load_intensity_manifest()` returns a `dict` with
      `manifest_version == INTENSITY_MANIFEST_VERSION` (`== 1`) and a non-empty
      `cases` list; the committed `manifest.json` parses via `json.loads` and the
      whole dict round-trips through `json.dumps`/`json.loads` unchanged.

- [ ] **AC13: The corpus has one clean case and ≥2 implausible cases.** Exactly one
      case has `plausible == true` with `target_label is None`, and at least two
      cases have `plausible == false` with a non-null integer `target_label`; all
      `case_id` values are distinct and match `^[a-z0-9_]+$`, and every case's
      `scan_fixture` path is distinct.

- [ ] **AC14: Every referenced fixture exists and loads via the Stage-0 loader.**
      For every case, the resolved `scan_fixture` and `seg_fixture` exist, and
      `load_case(scan, seg)` returns a `Case` without raising, with
      `scan.data.shape == seg.data.shape` and a non-empty `label_inventory`.

- [ ] **AC15: Every case's label map is the clean GT.** For every case, the loaded
      seg's `label_inventory` keys are exactly `{20, 21, 22, 23, 24}`, each with a
      voxel count equal to `build_clean_spine().voxel_counts` for that label (the
      label map is byte-identical across all cases — only intensities vary).

- [ ] **AC16: Committed implausible fixtures differ from the clean fixture only in
      the target mask.** For every `plausible == false` case, the loaded scan array
      equals the loaded clean-case scan array (`np.array_equal`) at all voxels where
      `seg.data != case["target_label"]`, and differs at ≥1 voxel where
      `seg.data == case["target_label"]`.

- [ ] **AC17: Manifest expected bands equal the painter ground truth.** For every
      case, `case["expected_label_hu_bands"]` equals what the painter/model
      produces for that case (the clean case's per-label bands and each implausible
      case's target band are the model-derived values, copied verbatim — no drift),
      and the manifest's top-level `hu_model` equals `DEFAULT_HU_MODEL` as a dict.

### D. Reproducibility & `.gitattributes` pinning

- [ ] **AC18: Regeneration reproduces every committed fixture's content.**
      `write_intensity_corpus(tmp)` into a fresh temp dir yields, for every case, a
      scan and seg whose loaded arrays and affines are `np.array_equal` to the
      committed fixtures (loaded via `load_case`).

- [ ] **AC19: Regeneration is byte-identical.** Two successive
      `write_intensity_corpus` calls into two fresh temp dirs produce
      byte-for-byte identical fixture files and byte-identical `manifest.json`, and
      each regenerated file is byte-for-byte identical to its committed counterpart
      under `INTENSITY_CORPUS_DIR`.

- [ ] **AC20: The one-command regeneration entry point runs.**
      `segqc.synth.intensity.main(["--out", <tmp>])` returns `0` and writes a
      `manifest.json` that `load_intensity_manifest(<tmp>/manifest.json)` parses to
      a dict with the same set of `case_id`s as the committed manifest.

- [ ] **AC21: New byte-reproducible fixtures are pinned in `.gitattributes`.**
      `.gitattributes` contains a rule pinning `tests/corpus/intensity/manifest.json`
      to `text eol=lf` and a rule marking `tests/corpus/intensity/fixtures/*.nii.gz`
      as `binary` (so a fresh checkout stays byte-stable under `core.autocrlf`, per
      the CLAUDE.md gotcha).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **A new parallel `tests/corpus/intensity/` corpus — the existing Stage-5 corpus
  is left byte-identical.** The queue says "wire these into the committed fixture
  set / corpus builder." The literal reading (extend `tests/corpus/`'s shared
  `base_scan.nii.gz` / `corpus.py`) would change committed bytes that items 040–042
  assert byte-identical (e.g. item 040's "`base_scan.nii.gz` is byte-identical to a
  freshly written `build_clean_spine().scan_img`" adversarial test and the
  `golden/*.json` snapshots, all of which are geometric-only and never read scan
  intensity). To avoid regressing a green Phase-1 suite, this item adds a **new,
  parallel** intensity corpus (`segqc/synth/intensity.py` +
  `tests/corpus/intensity/`) and does not touch `corpus.py`, `golden.py`, the
  operator modules, or any existing committed fixture. The validator should confirm
  items 040–042 stay green.

- **Pinned HU model constants (`DEFAULT_HU_MODEL`, int16), chosen as defensible
  representative CT values — not QC thresholds.** background_mean=40, background_std=10
  (soft tissue); cancellous_mean=200, cancellous_std=40 (trabecular interior);
  cortical_mean=600, cortical_std=120 (cortical rim). Implausible fills:
  `metal` mean=3000, std=100; `soft_tissue` mean=40, std=10; `degenerate_uniform`
  mean=0, std=0 (a single constant). These give a clean per-label median ≈ 200 HU
  (interior-dominated), comfortably inside the documented bone-plausible band
  `[100, 1500]` and well above background; the metal target ≈ 3000 (≥ 2500 band)
  and soft-tissue target ≈ 40 (≤ 100 band) are cleanly separable. They are the
  **generator's** painted values; item 062 sets its own judgement thresholds
  independently. If a reviewer prefers an air background (−1000) the change is a
  single constant.

- **Soft-tissue (not air) background.** Vertebrae are anatomically surrounded by
  soft tissue; a soft-tissue background makes the `soft_tissue` implausible variant
  realistic (a "vertebra" indistinguishable from its surroundings) and keeps
  bone↔background clearly separable (AC4). An air background is a one-constant swap.

- **Cortical rim = mask minus its one-voxel binary erosion (SciPy).** The rim/
  interior split is computed with `scipy.ndimage.binary_erosion` (SciPy is already
  a hard dependency, `pyproject.toml`). The default clean bodies are 25×30×25 vox
  at 1 mm spacing, so a one-voxel erosion always leaves a non-empty interior; if a
  future thin body erodes to an empty interior, the painter treats the whole mask
  as cancellous (documented fallback) — AC3 asserts rim>interior only where both
  are non-empty, which holds for the default spine.

- **Target label 22 (L3, the middle body) for implausible variants**, matching the
  Stage-5 corpus's mode-case convention (which targets label 22). The recipe is a
  plain list, so more variants/targets can be appended later without a schema
  change.

- **int16 scan dtype avoids the nibabel int64 constructor error** documented in
  item 040's Decisions (nibabel ≥5.0 rejects `Nifti1Image(int64_array, affine)`
  without an explicit `dtype`). The painter builds int16 arrays fresh and never
  round-trips a `load_case`-loaded (int64) seg back into a `Nifti1Image`, so it
  never hits that path. Test helpers must likewise sample the `load_case`-loaded
  arrays directly rather than reconstruct a seg `Nifti1Image`.

- **`.nii.gz` fixtures are byte-reproducible** under the installed nibabel 5.3.3
  (`DeterministicGzipFile`, mtime=0 — verified in item 040), and the manifest is
  written via `write_bytes` with `\n` newlines (Python 3.9 cannot set `newline=` on
  `Path.write_text`). New fixtures are pinned in `.gitattributes` (AC21). AC18
  (loaded-content equality) is the version-robust backstop if a future nibabel
  writes non-deterministically.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `segqc.synth.clean_gt.build_clean_spine(*, levels, spacing, convention,
  curve_amplitude_mm) -> CleanSpine` with `.seg_img` / `.voxel_counts` (uint16 seg,
  default labels 20–24); `segqc.synth.perturbation.seeded_rng(seed) ->
  np.random.Generator`; `segqc.io.load_case(scan_path, seg_path) -> Case` with
  `.scan` / `.seg` (int64 labels) / `.label_inventory` and its scan↔seg
  shape/affine compatibility check; `segqc.synth.corpus`'s constants/pattern
  (`CORPUS_DIR`, deterministic `nib.save`, `write_bytes` manifest) as the template
  for the intensity corpus. If any diverged, the builder/validator hands back.

## Implementation Steps

Intended code path: new `src/segqc/synth/intensity.py` + an additive re-export in
`src/segqc/synth/__init__.py`; committed data under `tests/corpus/intensity/`; one
line-group added to `.gitattributes`. **No** edits to existing operator / corpus /
golden / rule / extractor / config / report / reference modules.

1. **Create `src/segqc/synth/intensity.py`** importing `dataclasses`, `json`,
   `argparse`, `pathlib`, `numpy`, `nibabel`, `scipy.ndimage.binary_erosion`;
   `build_clean_spine` from `segqc.synth.clean_gt`; `seeded_rng` from
   `segqc.synth.perturbation`. Import from submodules (not the `segqc.synth`
   package) to avoid a circular import once `__init__` re-exports this module.

2. **Define the HU model & fills:** the `HUModel` dataclass, `DEFAULT_HU_MODEL`
   with the pinned constants (see Assumptions), the `ImplausibleFill` dataclass,
   and `IMPLAUSIBLE_FILLS = {"metal": ..., "soft_tissue": ..., "degenerate_uniform": ...}`.

3. **`paint_clean_scan(seg_img, *, seed=0, model=DEFAULT_HU_MODEL) -> Nifti1Image`:**
   read the seg array (do not mutate it); start an int16 array filled with seeded
   background noise (`background_mean` + `background_std`·N(0,1)); for each present
   non-zero label, compute its mask, its one-voxel `binary_erosion` (interior) and
   the rim (`mask & ~interior`); write seeded cancellous HU into the interior and
   seeded cortical HU into the rim (whole mask cancellous if the interior is
   empty); round, clip to the int16 range, and cast to int16; build a
   `Nifti1Image(data, np.array(seg_img.affine))`.

4. **`paint_implausible_variant(clean_scan_img, seg_img, *, target_label, fill,
   seed=0) -> Nifti1Image`:** copy the clean scan array; overwrite the
   `seg.data == target_label` voxels with seeded `fill` HU (a single constant when
   `fill.std == 0`); round/clip/cast to int16; return a fresh `Nifti1Image` with
   the seg's affine. Never touch the seg array.

5. **Corpus recipe & builders (mirror `segqc.synth.corpus`, item 040):** an
   `IntensityCase` dataclass and a declarative `CASE_RECIPE`
   (`clean_hu`, `implausible_metal`, `implausible_soft_tissue`,
   `degenerate_uniform`); `build_intensity_corpus()` builds the shared clean spine
   once, paints the clean scan, derives each variant, and attaches the
   model-derived `expected_label_hu_bands`; `write_intensity_corpus(dest)` writes
   the shared `fixtures/clean_spine_seg.nii.gz`, one `fixtures/<case_id>_scan.nii.gz`
   per case (deterministic `nib.save`), and `dest/manifest.json` via
   `write_bytes(json.dumps(..., indent=2, sort_keys=True) + "\n")` with
   fixture paths relative to `dest`.

6. **Module constants:** `INTENSITY_CORPUS_DIR` (repo `tests/corpus/intensity`),
   `INTENSITY_MANIFEST_PATH`, `INTENSITY_FIXTURES_DIRNAME`,
   `INTENSITY_MANIFEST_VERSION = 1`, resolved from `Path(__file__)`.
   `load_intensity_manifest(path=INTENSITY_MANIFEST_PATH)` → `json.loads(...)`.

7. **`main(argv=None) -> int`:** `argparse` `--out` defaulting to
   `INTENSITY_CORPUS_DIR`; call `write_intensity_corpus(Path(out))`; return 0.
   Add `if __name__ == "__main__": raise SystemExit(main())`.

8. **Re-export** the public names from `src/segqc/synth/__init__.py` (additive
   import line + `__all__` entries) — do not remove or reorder existing exports.

9. **Regenerate + commit the data:** run
   `.venv/Scripts/python -m segqc.synth.intensity` to materialise
   `tests/corpus/intensity/manifest.json` + `tests/corpus/intensity/fixtures/*.nii.gz`,
   and commit them alongside the module.

10. **Pin the new fixtures in `.gitattributes`:** add
    `tests/corpus/intensity/manifest.json text eol=lf` and
    `tests/corpus/intensity/fixtures/*.nii.gz binary`.

11. **Do not** edit any existing corpus/operator/golden/rule/extractor/config/
    report/reference module, and do not change the existing `tests/corpus/`
    fixtures or golden snapshots.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_058_intensity_fixtures.py`, in
  the style of `tests/test_040_synthetic_corpus.py` (import `segqc.synth`,
  `paint_clean_scan`, `paint_implausible_variant`, `load_intensity_manifest`,
  `load_case`, `build_clean_spine`).
- **Helpers:** a `_seg()` fixture (`build_clean_spine().seg_img`); a `_manifest()`
  fixture (`load_intensity_manifest()`); a `_resolve(case, key)` helper
  (`INTENSITY_CORPUS_DIR / case[key]`); a `_loaded(case)` helper returning
  `load_case(scan, seg)`; a `_under(arr, seg_data, label)` helper returning
  `arr[seg_data == label]`.
- **Group A — clean painter (AC1–AC6):** shape/affine/dtype (AC1); per-label
  median ∈ [100,1500] (AC2); rim-mean > interior-mean via `binary_erosion`
  (AC3); background median ∈ band and < min per-label median (AC4); input-seg
  immutability (AC5); seeded determinism + seed-sensitivity (AC6).
- **Group B — variants (AC7–AC11):** metal variant differs only in target mask +
  seg untouched (AC7); metal target median ≥ 2500 (AC8); soft-tissue target
  median ≤ 100 (AC9); degenerate target has one distinct value (AC10); shape/
  affine preserved + determinism (AC11).
- **Group C — committed corpus (AC12–AC17):** manifest parse/version/round-trip
  (AC12); one clean + ≥2 implausible, distinct ids/paths, id regex (AC13);
  fixtures exist + `load_case` succeeds (AC14); label inventory == {20..24} with
  `build_clean_spine` counts (AC15); committed implausible vs clean differ only in
  target mask (AC16); manifest bands == painter ground truth + `hu_model` ==
  `DEFAULT_HU_MODEL` (AC17).
- **Group D — reproducibility & pinning (AC18–AC21):** `write_intensity_corpus`
  content equality (AC18); byte-identical double-write + equality with committed
  (AC19); `main(["--out", tmp])` → 0 + matching id set (AC20); `.gitattributes`
  contains the two intensity rules (AC21).
- **Adversarial / edge cases:**
  - An all-background (label-free) input to `paint_clean_scan` yields a
    background-only int16 scan with no crash (empty label set).
  - A `target_label` absent from the seg makes `paint_implausible_variant` a
    no-op equal to the clean scan (no spurious change, no crash).
  - The degenerate-uniform variant's target constant is within the int16 range
    (no overflow/clip surprise).
  - Metal HU clips cleanly to the int16 max where the seeded draw would exceed it
    (deterministic, no wraparound).
  - Re-running `write_intensity_corpus` over an existing directory reproduces
    identical bytes (idempotent regeneration).
  - `load_intensity_manifest` on the committed file and on a fresh
    `write_intensity_corpus` output produce equal `cases` (relocatable,
    path-relative).

## Dependencies

- **Upstream (all merged ✅ — Phase 1 complete):**
  - **Item 036** — `segqc.synth.clean_gt.build_clean_spine` / `CleanSpine`
    (`.seg_img` uint16, `.voxel_counts`, default labels 20–24) — the shared clean
    label map every intensity case is painted onto; and
    `segqc.synth.perturbation.seeded_rng` (the enforced reproducible-RNG helper).
  - **Item 040** — `segqc.synth.corpus` as the corpus-builder template
    (deterministic `nib.save`, `write_bytes` manifest, relative fixture paths,
    `main(--out)` regeneration) this item mirrors for the intensity corpus. This
    item must **not** modify item 040's corpus or its byte-identical fixtures.
  - **Item 003** — `segqc.io.load_case` / `load_volume` (the Stage-0 loader AC14
    drives) and its scan↔seg shape/affine compatibility check.
  - **Item 004** — `segqc.labels` (default convention L1–L5 = 20–24) via
    `build_clean_spine`.
- **Downstream (depend on this item):**
  - **Item 059** (per-label first-order intensity extractor) — tested against the
    clean HU fixture's hand-computable per-label stats.
  - **Item 062** (implausible-intensity heuristic) — silent on `clean_hu`, fires
    on the implausible variants' target label.
  - **Item 065** (Stage-8 integration & acceptance) — drives the clean + variant
    fixtures end-to-end through `segqc run`.
  - **Items 061/063/064** consume the intensity-bearing fixtures indirectly via
    the extractor/reference paths.
- **Not dependencies:** nothing else in queue-007 precedes 058 (it is the first,
  foundation item).

## Decisions & Trade-offs

- **`IMPLAUSIBLE_FILLS` key/name is `"degenerate_uniform"`, not `"degenerate"`.**
  The committed tests (`tests/test_058_intensity_fixtures.py`) consistently use
  `IMPLAUSIBLE_FILLS["degenerate_uniform"]` and the interface section's public
  surface likewise documents `"metal" | "soft_tissue" | "degenerate_uniform"` on
  `ImplausibleFill.name`; only one prose sentence in the Description shortens it
  to "degenerate". Implemented as `"degenerate_uniform"` throughout (fill name,
  case_id, variant) to match the authoritative test interface.

- **Manifest field name is `expected_label_hu_bands`** (as specified) holding a
  `{str(label): [lo, hi]}` mapping; the clean case's bands are the fixed
  documented bone-plausible band `[100, 1500]` per present label (this is what
  AC17's test literally asserts), not a per-run computed band from the actual
  painted array — the band is generator *ground truth* about what the model is
  designed to paint, not a post-hoc measurement.

- **Implausible-case bands are fixed per fill type**, matching the manifest
  schema example in the spec: `metal -> [2500, 32767]` (int16 max),
  `soft_tissue -> [-200, 100]`, `degenerate_uniform -> [0, 0]` (the fill's
  constant value). These are copied verbatim by `build_intensity_corpus()`
  rather than derived from a sampled run, keeping the manifest a fixed,
  drift-proof contract tied only to `DEFAULT_HU_MODEL`/`IMPLAUSIBLE_FILLS`.

- **Corpus case ids**: `clean_hu`, `implausible_metal`, `implausible_soft_tissue`,
  `degenerate_uniform` (four cases total: one clean + three implausible,
  satisfying AC13's "at least two implausible" with headroom). All target label
  22 (L3), matching the Stage-5 corpus's mode-case convention.

- **Shared seg fixture name**: `fixtures/clean_spine_seg.nii.gz`, written once
  from the first built case and reused by every case's `seg_fixture` manifest
  entry (mirrors `segqc.synth.corpus`'s shared `base_scan.nii.gz` dedup
  pattern, but for the label map instead of the scan, since here the *scan*
  is what varies across cases).

- **RNG draw ordering in `paint_clean_scan`**: background noise is drawn for
  the *entire* array first (`size=shape`), then per-label interior/rim regions
  are overwritten in ascending label order. This keeps the result deterministic
  for a fixed seed regardless of how many/which labels are present, satisfying
  AC6's determinism requirement and the all-background adversarial case (no
  labels to iterate, purely the initial background draw).

- **Verified no regression**: regenerating the existing Stage-5 corpus via
  `python -m segqc.synth.corpus --out <scratch dir>` still succeeds unchanged;
  no existing module (`clean_gt.py`, `corpus.py`, `perturbation.py`,
  `golden.py`, operator modules) was edited, only the additive re-export in
  `src/segqc/synth/__init__.py`.
