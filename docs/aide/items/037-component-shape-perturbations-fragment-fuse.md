# Item 037 — Component & shape perturbations: fragment, fuse, inject islands (modes 2, 3)

> **Created:** 2026-07-08 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 037 *(first operator family; parallel with 038/039)*
> **Objectives:** G7 (evaluable & regression-testable — seeded operators that
> provably drive the Stage 4 topology rules), and the synthetic-corpus half of
> G2 (materialising §6 failure modes 2 and 3 against the item-036 framework)
> **Suggested branch:** `aide/037-component-shape-perturbations-fragment-fuse`

---

## Description

Add the **first operator family** of the Stage 5 synthetic-failure generator:
three seeded [`Perturbation`](../../../src/segqc/synth/perturbation.py) subclasses
that inject **connected-component / mask-topology** failures onto the item-036
clean-GT positive control, each returning a well-formed
[`Expectation`](../../../src/segqc/synth/perturbation.py) naming the induced §6
failure mode and the offending label(s). All three implement against the
already-merged item-036 contract **unchanged** (`Perturbation` ABC,
`Expectation`, `PerturbationResult`, `register_perturbation`, `seeded_rng`) and
start every perturbation from `build_clean_spine()`'s output.

The three operators (§6 modes 2 and 3, rule families 027 `bounds` / 028
`fragmentation`):

1. **`fragment`** — split **one** label's body into two-or-more comparable
   **disconnected** pieces. Detected by the **fragmentation** rule (item 028):
   the label's `fragmentation_index` drops below the default 0.75 threshold, so
   a `"Fragmentation:"`-tagged finding fires on that label. (§6 mode 2 —
   fragmented / over-segmentation.)

2. **`fuse`** — merge two **adjacent** labels into a single label: the
   neighbour's voxels are re-labelled onto the target, leaving the target as a
   single label spanning **two disconnected vertebra bodies**. Detected by the
   **fragmentation** rule on the surviving label (`fragmentation_index ≈ 0.5`),
   the reliable, label-attributed signature of under-segmentation in this
   pipeline (see Assumptions for why *not* `bounds`). (§6 mode 2 — fused /
   under-segmentation.)

3. **`inject_islands`** — add one or more **tiny rogue disconnected components**
   (each strictly below the default `island_min_voxels = 50`) to a label,
   placed in empty voxels adjacent to its body. Detected by the **island** check
   of the fragmentation rule: a `"Rogue island(s):"`-tagged finding fires on the
   target while its `fragmentation_index` stays above threshold (the dominant
   body still dominates). (§6 mode 3 — disconnected components / rogue islands.)

Each operator is **seeded/deterministic** (same seed + input ⇒ byte-identical
output array, randomness drawn solely from `seeded_rng(seed)`), **non-mutating**
(returns a fresh `Nifti1Image`, never touches the caller's array), and
**preserves the label-map dtype and geometry** (dtype, affine, shape, voxel
spacing). Each returned `Expectation` reflects the label(s) **actually**
perturbed, so a test can assert the pipeline flags exactly
`result.expectation.expected_labels` regardless of which label the seed selected.

### Scope boundary — what this item is **not**

- **Not a change to the item-036 framework.** `synth/perturbation.py` and
  `synth/clean_gt.py` are consumed **unchanged**; this item only *adds* new
  operator classes (and the one additive `__init__` import that self-registers
  them). Runs in parallel with 038/039, which add sibling operator files against
  the same interface — changes must stay additive to avoid merge conflicts.
- **Not the other operator families.** remove-level / crop / overlap are item
  038; displace / relabel / sequence-break are item 039.
- **Not the committed corpus, manifest, regression suite, or golden files**
  (040/041/042). This item ships operators + unit tests only; no NIfTI fixtures
  are committed.
- **Not new rules, extractors, or config.** It drives the already-merged
  `run_qc` / `FragmentationRule` / `compute_components` / bundled default config
  unchanged; it adds no `Rule` and edits no `heuristics`/`features`/`config`
  code.

---

## Public interface (new operators on the item-036 framework)

New module `src/segqc/synth/component_shape.py` (single file, three classes —
keeps the change additive and merge-safe alongside 038/039). Registered on
`import segqc.synth` via one additive import line in `synth/__init__.py`.

```python
@register_perturbation
class FragmentPerturbation(Perturbation):
    name = "fragment"
    def __init__(self, *, target_label: int | None = None, n_pieces: int = 2): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 2

@register_perturbation
class FusePerturbation(Perturbation):
    name = "fuse"
    def __init__(self, *, target_label: int | None = None,
                 neighbour_label: int | None = None): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 2

@register_perturbation
class InjectIslandsPerturbation(Perturbation):
    name = "inject_islands"
    def __init__(self, *, target_label: int | None = None,
                 n_islands: int = 1, island_voxels: int = 27): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 3
```

- Per the item-036 contract, `apply` takes only `(labelmap, seed)`; all operator
  parameters (which label to hit, how many pieces/islands, island size) are
  **constructor** arguments, and the registry stores the **class**.
- When a target/neighbour is left `None`, the operator selects it deterministically
  from the present labels using `seeded_rng(seed)`; the chosen label is recorded
  in the returned `Expectation.expected_labels`.
- `apply` reads present labels from `labelmap` (`np.unique` of non-zero voxels)
  and spacing/affine from `labelmap.header.get_zooms()` / `labelmap.affine`,
  exactly as the Stage 2/3 extractors do.

---

## Acceptance Criteria

_One test per criterion. Group A = `fragment`, Group B = `fuse`, Group C =
`inject_islands`, Group D = cross-cutting reproducibility/immutability. "The
clean GT" means `build_clean_spine()` (default lumbar L1–L5, labels 20–24).
"The designated finding fires with labels L" means: running the perturbed
labelmap through `run_qc(labelmap, bundled_default_config())`, at least one
`Finding` with the stated `rule_id` and reason-tag has `labels == frozenset(L)`._

### A. `fragment` (§6 mode 2 — fragmentation rule)

- [ ] **AC1: `fragment` is registered under `"fragment"`.** After
      `import segqc.synth`, `get_perturbation("fragment")` returns
      `FragmentPerturbation`, `"fragment"` is in `perturbation_names()`, and the
      class appears in `iter_perturbations()`.

- [ ] **AC2: `fragment` splits the target into ≥2 comparable disconnected
      pieces.** For `FragmentPerturbation(target_label=22).apply(clean.seg_img,
      seed=0).labelmap`, `compute_components(labelmap, 22, cfg)` reports
      `component_count >= 2`, `largest_component_fraction`
      (`== fragmentation_index`) strictly below
      `DEFAULT_FRAGMENTATION_INDEX_THRESHOLD` (0.75), and every non-dominant
      component size is `>= DEFAULT_ISLAND_MIN_VOXELS` (a genuine fragment, not
      an island).

- [ ] **AC3: `fragment` preserves the target's bounding box (bounds stays
      silent).** `compute_label_geometry(fragmented, 22)` reports
      `extent_x_mm` / `extent_y_mm` / `extent_z_mm` **equal** to those of the
      un-fragmented clean GT's label 22, and `run_qc` on the fragmented map
      emits **no** `rule_id == "bounds"` finding.

- [ ] **AC4: `fragment` fires the fragmentation-kind finding on the target.**
      `run_qc` on the fragmented map emits a `Finding` with
      `rule_id == "fragmentation"` whose `reason` starts with `"Fragmentation:"`
      and `labels == frozenset({22})`.

- [ ] **AC5: `fragment`'s `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 2`,
      `failure_mode_name == FAILURE_MODE_NAMES[2]`,
      `expected_rule_ids == frozenset({"fragmentation"})`,
      `expected_labels == frozenset({22})`, and
      `expected_verdict == "flagged-for-review"`; and the pipeline agrees —
      `run_qc(...).verdict.overall.label == "flagged-for-review"`.

- [ ] **AC6: `fragment` leaves every un-perturbed present label unflagged.** In
      `run_qc`'s findings for the fragmented map, no finding is attributed to any
      present label other than 22 (for every finding, `finding.labels` is a
      subset of `{22}`).

### B. `fuse` (§6 mode 2 — fragmentation rule on the surviving label)

- [ ] **AC7: `fuse` is registered under `"fuse"`.** After `import segqc.synth`,
      `get_perturbation("fuse")` returns `FusePerturbation`, and `"fuse"` is in
      `perturbation_names()`.

- [ ] **AC8: `fuse` absorbs an adjacent neighbour into the target.** For
      `FusePerturbation(target_label=20, neighbour_label=21).apply(clean.seg_img,
      seed=0).labelmap`, label 21 is **absent** from the fused map's non-zero
      labels, and label 20's voxel count equals the sum of the clean GT's
      label-20 and label-21 voxel counts.

- [ ] **AC9: the fused surviving label fires the fragmentation-kind finding.**
      `compute_components(fused, 20, cfg)` reports `component_count >= 2` and
      `fragmentation_index < 0.75`; and `run_qc` emits a `Finding` with
      `rule_id == "fragmentation"`, `reason` starting `"Fragmentation:"`, and
      `labels == frozenset({20})`.

- [ ] **AC10: `fuse`'s `Expectation` is well-formed and truthful.** The result's
      `expectation` has `failure_mode == 2`,
      `failure_mode_name == FAILURE_MODE_NAMES[2]`, `"fragmentation"` in
      `expected_rule_ids`, `expected_labels == frozenset({20})`, and
      `expected_verdict == "flagged-for-review"`; the pipeline agrees
      (`verdict.overall.label == "flagged-for-review"`).

- [ ] **AC11: `fuse` leaves the un-perturbed present labels unflagged.** In
      `run_qc`'s findings for the fused map, no finding is attributed to any
      present label other than the surviving fused label 20 (every
      `finding.labels` is a subset of `{20}`; the case-level coverage finding for
      the now-missing level carries `labels == frozenset()` — see Assumptions).

- [ ] **AC12: `fuse` rejects an input with fewer than two labels.** Applying
      `FusePerturbation()` to a single-label map (e.g.
      `build_clean_spine(levels=["L3"]).seg_img`) raises `SegQCInputError`.

### C. `inject_islands` (§6 mode 3 — island check)

- [ ] **AC13: `inject_islands` is registered under `"inject_islands"`.** After
      `import segqc.synth`, `get_perturbation("inject_islands")` returns
      `InjectIslandsPerturbation`, and `"inject_islands"` is in
      `perturbation_names()`.

- [ ] **AC14: `inject_islands` adds a tiny disconnected component to the
      target.** For
      `InjectIslandsPerturbation(target_label=22).apply(clean.seg_img,
      seed=0).labelmap`, `compute_components(labelmap, 22, cfg)` reports
      `component_count >= 2` and at least one non-dominant component size
      strictly below `DEFAULT_ISLAND_MIN_VOXELS` (50).

- [ ] **AC15: the injected island does not read as fragmentation.** For the same
      map, `compute_components(labelmap, 22, cfg).largest_component_fraction`
      is `>= DEFAULT_FRAGMENTATION_INDEX_THRESHOLD` (0.75), and `run_qc` emits
      **no** `"Fragmentation:"`-tagged finding attributed to label 22.

- [ ] **AC16: `inject_islands` fires the island-kind finding on the target.**
      `run_qc` on the map emits a `Finding` with `rule_id == "fragmentation"`
      whose `reason` starts with `"Rogue island(s):"` and
      `labels == frozenset({22})`.

- [ ] **AC17: `inject_islands`' `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 3`,
      `failure_mode_name == FAILURE_MODE_NAMES[3]`,
      `expected_rule_ids == frozenset({"fragmentation"})`,
      `expected_labels == frozenset({22})`, and
      `expected_verdict == "flagged-for-review"`; the pipeline agrees
      (`verdict.overall.label == "flagged-for-review"`).

- [ ] **AC18: injected islands neither touch the border, overlap a neighbour,
      nor flag any other label.** `run_qc` on the injected map emits **no**
      `rule_id == "border"` and **no** `rule_id == "overlap"` finding, and no
      finding is attributed to any present label other than 22.

### D. Cross-cutting: geometry, determinism, immutability, seeding

- [ ] **AC19: every operator preserves dtype and geometry.** For each of the
      three operators (with an explicit target), the output `labelmap` has the
      same array `dtype`, an affine that is `np.array_equal` to the input's, the
      same `shape`, and `header.get_zooms()[:3]` equal to the input's spacing.

- [ ] **AC20: every operator is reproducible (same seed + input ⇒ identical
      array).** For each of the three operators, two `apply(clean.seg_img,
      seed=7)` calls (with the same explicit target) return output arrays that
      are `np.array_equal`.

- [ ] **AC21: every operator is non-mutating.** For each of the three operators,
      the data array of the `seg_img` passed to `apply` is unchanged (equal to a
      pre-call copy) after the call returns.

- [ ] **AC22: an unspecified target is chosen deterministically from the seed,
      and the `Expectation` names the label(s) actually perturbed.** For each
      operator with no explicit target, two `apply(clean.seg_img, seed=3)` calls
      select the **same** target (identical output arrays), and running the
      perturbed map through `run_qc` flags exactly the label set carried in
      `result.expectation.expected_labels` (self-consistency, whichever label the
      seed picked).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **`fuse` targets the `fragmentation` rule, not `bounds` — a deliberate
  divergence from the queue's "drives the bounds / over-segmentation rules"
  phrasing.** The shipped `DEFAULT_BOUNDS` (item 027) for the lumbar group are
  `volume ∈ [8000, 120000] mm³` and `extent ≤ 120 mm`. A fused pair of two
  clean-GT bodies is ≈ 37 500 mm³ with a stacking extent ≈ 65 mm — comfortably
  **inside** every bound, so `bounds` **cannot** fire on a two-label fuse without
  fusing ≥ 4 bodies (which the queue's "two adjacent labels" precludes). The
  reliable, **label-attributed** under-segmentation signature in this pipeline is
  a single label spanning two disconnected vertebra bodies:
  `fragmentation_index ≈ 0.5 < 0.75` ⇒ `FragmentationRule` fires on the surviving
  label. This is the most material clarify=`assume` decision; the validator
  should surface it at the queue boundary. (Both operators in this item therefore
  drive the same `rule_id == "fragmentation"` but via genuinely different failure
  mechanisms — an intra-vertebra split vs. an inter-vertebra merge — and are
  distinguished in tests by the reason tag and the offending-label story.)

- **`fuse` also (correctly) co-fires the case-level `coverage` rule, which does
  not flag any present label.** Because the absorbed neighbour label disappears,
  its anatomical level becomes a missing interior level, so `CoverageRule` (item
  029) emits a **case-level** missing-level finding (`labels == frozenset()`,
  offending level named in the `reason`). This is a correct secondary detection
  (a fused pair genuinely lacks a level) and does **not** violate AC11's
  "un-perturbed present labels stay unflagged", since the finding attributes to
  no present label. `fuse`'s `Expectation.expected_rule_ids` pins `{"fragmentation"}`
  as the item-037-family rule; whether the item-041 regression suite additionally
  asserts `coverage` is that item's call (the co-firing is documented here so it
  is not a surprise downstream).

- **Operators are parameterised classes; `apply` takes only `(labelmap, seed)`
  (per the item-036 contract).** Target selection, piece/island counts, and
  island size are **constructor** arguments; the registry stores the class. When
  a target is left `None`, it is chosen deterministically from the present labels
  via `seeded_rng(seed)`. This matches item 036's explicit design note that
  operators express e.g. `FragmentPerturbation(target_label=22).apply(seg, seed)`.

- **The returned `Expectation` reflects the label(s) *actually* perturbed.** So a
  test asserts `pipeline-fired labels == result.expectation.expected_labels`
  (self-consistent), which is robust to which label a `None` target + seed
  selects (AC22). Tests that need a fixed offending label pass an explicit
  `target_label`.

- **`fragment` carves a thin interior gap perpendicular to the stacking axis
  (axis 0), preserving the label's bounding box.** Splitting by removing a
  ~1-voxel-thick slab through the middle leaves two comparable stacked pieces
  whose **union** bounding box still spans the original extent on every axis
  (piece 1 supplies the min, piece 2 the max), so `compute_label_geometry`'s
  extents are unchanged and `bounds` stays silent (AC3). The pieces stay well
  above `island_min_voxels`, so they read as a fragmentation, not islands (AC2).
  This deliberately keeps `fragment`'s signature to the single `fragmentation`
  rule.

- **`inject_islands` places each tiny cube in verified-empty voxels adjacent to
  the target body, inside the FOV margins.** The clean GT insets every body by a
  15 mm margin and separates bodies by a 15 mm gap, so there is empty space next
  to each body. Each island is placed with ≥ 1 empty voxel separating it from the
  body (disconnected under 6-connectivity — matching `compute_components`'
  connectivity), ≥ 1 voxel from every FOV face (no `border`), and in voxels
  confirmed empty (value 0) so it intersects no other label (no `overlap`)
  (AC18). Default island size is 27 voxels (a 3×3×3 cube), strictly below the
  default `island_min_voxels = 50`; the threshold is a **voxel count**, so this
  holds independent of spacing.

- **Severity / verdict pinning.** `FragmentationRule`'s default severity is
  `"flagged-for-review"` (item 028), and a single FLAG finding yields an overall
  `flagged-for-review` verdict (item 034), so every operator's
  `expected_verdict` is `"flagged-for-review"`, asserted against
  `run_qc(...).verdict.overall.label`.

- **Single new module `src/segqc/synth/component_shape.py`, plus one additive
  `__init__` import.** The three classes live in one file (rather than three) to
  minimise the shared-file surface. `synth/__init__.py` gains **one** import line
  (`from segqc.synth import component_shape  # noqa: F401` — or a re-export of the
  three classes) so the operators self-register on `import segqc.synth`, mirroring
  how `IdentityPerturbation` self-registers. This is additive and at a different
  line region from what 038/039 add, so git merges the sibling registrations
  cleanly. `synth/perturbation.py` and `synth/clean_gt.py` are **not** edited.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `compute_components(seg, label, cfg) -> ComponentsInfo` with
  `.component_count` / `.component_sizes` (descending) /
  `.largest_component_fraction`; `FragmentationRule` with `rule_id ==
  "fragmentation"`, reason tags `"Fragmentation:"` / `"Rogue island(s):"`, and
  constants `DEFAULT_FRAGMENTATION_INDEX_THRESHOLD == 0.75` /
  `DEFAULT_ISLAND_MIN_VOXELS == 50`; `compute_label_geometry(seg, label)` with
  `extent_{x,y,z}_mm` and `touches_*`; `run_qc(seg_img, config) -> (CaseResult,
  dict)` with `CaseResult.findings: tuple[Finding, ...]` and
  `CaseResult.verdict.overall.label`; `Finding.labels: frozenset[int]`;
  `segqc.io.SegQCInputError`.

## Implementation Steps

Intended code path: new file `src/segqc/synth/component_shape.py` + one additive
import in `src/segqc/synth/__init__.py`. No edits to existing production modules.

1. **Create `src/segqc/synth/component_shape.py`** importing from the item-036
   framework (`Perturbation`, `Expectation`, `PerturbationResult`,
   `register_perturbation`, `seeded_rng`, `FAILURE_MODE_NAMES`), `numpy`,
   `nibabel`, and `segqc.io.SegQCInputError`.

2. **Shared helpers (module-private):**
   - `_present_labels(labelmap) -> list[int]` — sorted non-zero unique voxel
     values (via `np.asanyarray(labelmap.dataobj)`), for target selection and
     validation.
   - `_choose_label(labels, seed) -> int` — deterministic pick via
     `seeded_rng(seed)` when no explicit target is given.
   - `_new_image(data, labelmap) -> nib.Nifti1Image` — build a fresh image with
     a **copied** array of the **same dtype** and the input's affine (never
     mutate the caller's array). Read spacing/affine only from the input.
   - A tiny helper to compute a label's bounding box (argwhere on the mask) for
     the fragment split and island placement.

3. **`FragmentPerturbation`** (`name = "fragment"`, `__init__(*, target_label,
   n_pieces=2)`): resolve/choose the target (raise `SegQCInputError` if an
   explicit target is absent from the map); copy the array; carve a thin
   (~1-voxel) empty slab (or `n_pieces - 1` slabs) through the target body
   perpendicular to axis 0 so the target becomes `n_pieces` comparable
   disconnected components with the union bounding box preserved; build the
   `Expectation(failure_mode=2, failure_mode_name=FAILURE_MODE_NAMES[2],
   expected_rule_ids=frozenset({"fragmentation"}),
   expected_labels=frozenset({target}), expected_verdict="flagged-for-review")`;
   return `PerturbationResult`.

4. **`FusePerturbation`** (`name = "fuse"`, `__init__(*, target_label,
   neighbour_label)`): read present labels; raise `SegQCInputError` if fewer than
   two; choose an **adjacent** (consecutive-in-sorted-order) pair (target = lower,
   neighbour = next) — or use the explicit pair, validating adjacency/presence;
   copy the array and re-label all neighbour voxels to the target (unbridged — do
   **not** fill the gap, so the target is left as two disconnected bodies); build
   the `Expectation(failure_mode=2, ..., expected_rule_ids ⊇ {"fragmentation"},
   expected_labels=frozenset({target}), expected_verdict="flagged-for-review")`;
   return `PerturbationResult`.

5. **`InjectIslandsPerturbation`** (`name = "inject_islands"`, `__init__(*,
   target_label, n_islands=1, island_voxels=27)`): resolve/choose the target;
   copy the array; compute the target body bbox; place `n_islands` small cubes
   (each `island_voxels` voxels, < `island_min`) into confirmed-empty voxels
   adjacent to the body — ≥ 1 empty voxel from the body (disconnected under
   6-connectivity) and ≥ 1 voxel from every FOV face (no border), raising a clear
   error if no valid empty placement exists; build the
   `Expectation(failure_mode=3, failure_mode_name=FAILURE_MODE_NAMES[3],
   expected_rule_ids=frozenset({"fragmentation"}),
   expected_labels=frozenset({target}), expected_verdict="flagged-for-review")`;
   return `PerturbationResult`.

6. **Determinism & seeding.** Any stochastic choice (unspecified target, island
   placement jitter) derives solely from `seeded_rng(seed)`; the same seed +
   input yields byte-identical output. Deterministic operators still accept and
   thread `seed`.

7. **Register + wire.** Decorate each class with `@register_perturbation`, and
   add the single additive import line to `src/segqc/synth/__init__.py` (plus the
   three class names to its `__all__`) so `import segqc.synth` self-registers all
   three, mirroring `IdentityPerturbation`.

8. **Do not** edit `synth/perturbation.py`, `synth/clean_gt.py`, or any
   `heuristics` / `features` / `config` module.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_037_component_shape_perturbations.py`,
  in the same style as `tests/test_036_perturbation_framework.py` /
  `tests/test_036_clean_gt.py` (build a clean-GT fixture, apply the operator, run
  `run_qc(perturbed, bundled_default_config())`, assert on `case_result.findings`
  / `verdict`, and cross-check the raw topology via `compute_components` /
  `compute_label_geometry`).
- **No registry snapshot needed** — the three operators are real, permanent
  registrations (like `identity`); tests import them from `segqc.synth`.
- **Helpers:** a `_clean()` fixture (`build_clean_spine()`), a
  `_findings(labelmap)` helper returning `run_qc(labelmap,
  bundled_default_config())[0].findings`, and a `_flagged_present_labels(findings)`
  helper (union of non-empty `finding.labels`) for the "un-perturbed labels stay
  unflagged" assertions.
- **`fragment` (AC1–AC6):** registration (AC1); `compute_components` for
  `component_count >= 2` + `fragmentation_index < 0.75` + non-dominant ≥ island_min
  (AC2); `compute_label_geometry` extent-equality + no-`bounds`-finding (AC3);
  a `"Fragmentation:"`-tagged finding on `{22}` (AC4); `Expectation` fields +
  pipeline verdict (AC5); flagged-present-labels ⊆ `{22}` (AC6).
- **`fuse` (AC7–AC12):** registration (AC7); neighbour absent + voxel-count sum
  (AC8); `compute_components` + `"Fragmentation:"` finding on `{20}` (AC9);
  `Expectation` + verdict (AC10); flagged-present-labels ⊆ `{20}` (coverage
  finding is case-level, `labels == frozenset()`) (AC11); `SegQCInputError` on a
  single-label map (AC12).
- **`inject_islands` (AC13–AC18):** registration (AC13); `compute_components`
  showing a sub-50 non-dominant component (AC14); `fragmentation_index >= 0.75`
  and no `"Fragmentation:"` finding for 22 (AC15); a `"Rogue island(s):"`-tagged
  finding on `{22}` (AC16); `Expectation` + verdict (AC17); no `border`/`overlap`
  finding and flagged-present-labels ⊆ `{22}` (AC18).
- **Cross-cutting (AC19–AC22):** parametrise across the three operator instances
  — dtype/affine/shape/zooms preservation (AC19); two same-seed applies →
  `np.array_equal` (AC20); pre-call array copy unchanged after apply (AC21);
  unspecified-target same-seed determinism + pipeline flags exactly
  `expectation.expected_labels` (AC22).
- **Adversarial / edge cases:**
  - `fragment` / `inject_islands` with an **explicit** target not present in the
    map raise a clear error (do not silently no-op).
  - `fuse` with an explicit non-adjacent pair raises (adjacency is required).
  - Applying each operator to an **anisotropic** clean GT
    (`build_clean_spine(spacing=(1,1,3))`) still fires the designated rule and
    preserves spacing (voxel-count-based island threshold is spacing-independent).
  - Two **different** seeds with an unspecified target may pick different labels,
    but each result stays self-consistent (pipeline flags exactly
    `expectation.expected_labels`).
  - The injected island's small volume does not push the target below the
    `bounds` `min_volume` / drop any extent below the min (no spurious `bounds`
    finding) — a direct `compute_label_geometry` check.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 036** — the synthetic-corpus foundation this item builds on directly:
    `segqc.synth.clean_gt.build_clean_spine` / `CleanSpine` (every perturbation
    starts from its output) and the `segqc.synth.perturbation` framework
    (`Perturbation` ABC, `Expectation`, `PerturbationResult`,
    `register_perturbation` / `get_perturbation` / `iter_perturbations` /
    `perturbation_names`, `seeded_rng`, `FAILURE_MODE_NAMES`,
    `CLEAN_CONTROL_MODE`). Implemented against this **exact** interface, unchanged.
  - **Item 028** — `segqc.heuristics.fragmentation.FragmentationRule`
    (`rule_id == "fragmentation"`, reason tags `"Fragmentation:"` /
    `"Rogue island(s):"`, `DEFAULT_FRAGMENTATION_INDEX_THRESHOLD == 0.75`,
    `DEFAULT_ISLAND_MIN_VOXELS == 50`): the rule `fragment`/`fuse`/`inject_islands`
    must drive.
  - **Item 027** — `segqc.heuristics.bounds` (`DEFAULT_BOUNDS`): the wide bounds
    that `fragment`/`fuse` must **not** trip, asserted silent in AC3.
  - **Item 012** — `segqc.features.components.compute_components` (`ComponentsInfo`):
    the topology the tests read directly.
  - **Item 011** — `segqc.features.geometry.compute_label_geometry`
    (`extent_{x,y,z}_mm`, `touches_*`): bounding-box / border checks.
  - **Item 035** — `segqc.pipeline.run_qc` + `segqc.config.bundled_default_config`:
    the full-pipeline entry point the perturbed maps run through.
  - **Item 034** — `segqc.aggregate` (`CaseResult`, `verdict.overall.label`): the
    verdict shape the expectations are checked against.
  - **Item 026** — `segqc.heuristics.finding.Finding` (`rule_id`, `reason`,
    `labels`): the finding shape assertions read.
  - **Item 004** — `segqc.labels` (default convention labels L1–L5 = 20–24) via
    `build_clean_spine`.
  - **Item 003** — `segqc.io.SegQCInputError`: the error type for absent-target /
    too-few-labels / non-adjacent-pair guards.
- **Not dependencies (parallel siblings):** items **038** and **039** build
  other operator families against the same item-036 interface; this item is
  independent of them and its changes stay additive to avoid merge conflicts.

## Decisions & Trade-offs

- **`fragment` split mechanics.** Carves `n_pieces - 1` interior 1-voxel-thick
  slabs along axis 0, spaced evenly across the target's bounding-box span via
  `round(i * span / n_pieces)`, clamped strictly inside `(x_min, x_max)`. Only
  the slab's masked voxels are zeroed (`data[split_x][mask[split_x]] = 0`), not
  the entire y/z plane, so the operation is safe even if a label's cross-section
  is non-rectangular. For the default `n_pieces=2` on the clean GT's 25-voxel
  bodies this yields two ~9000-voxel pieces (`fragmentation_index == 0.5`),
  comfortably satisfying AC2's `>= island_min_voxels` floor. Raises
  `SegQCInputError` if the target's axis-0 span is too thin for the requested
  `n_pieces` (defensive; not exercised by the clean-GT-sized fixtures in the
  committed tests).

- **`fuse` adjacency is defined as consecutive position in the sorted
  present-label list**, not `neighbour == target + 1` by integer value. These
  coincide for the default lumbar convention (labels 20-24, contiguous), but
  the list-index definition is the more general/defensible one and is what the
  adversarial non-adjacent test (`target=20, neighbour=23`) exercises.

- **`inject_islands` placement axis.** Islands are placed along image axis 1
  (left-right) rather than axis 0 or axis 2: measured against the actual
  `build_clean_spine()` output, axis-1 margin below/above each body is >= 15
  voxels regardless of spacing (`sy` is untouched by the anisotropic
  `spacing=(1,1,3)` fixture used in the adversarial test), while axis-2 margin
  shrinks to 5 voxels under that same anisotropic spacing — too tight to
  reliably fit a 3x3x3 block plus gap plus inset. Verified empty-space checks
  (`np.all(block == 0)`) still guard correctness generically; the axis-1
  choice is a placement heuristic tuned to the item-036 geometry, not a
  hard-coded offset.

- **Island block shape.** A perfect-cube `island_voxels` (e.g. the default 27)
  is placed as a solid cube; a non-cube count falls back to a 1-voxel-wide
  line along axis 2 (trivially 6-connected, exact voxel count). Only the cube
  path is exercised by the committed tests (default `island_voxels=27`).

- **No `Rule`/heuristics/config edits.** Verified by smoke-running all three
  operators (fragment/fuse/inject_islands, including the anisotropic-spacing
  and unspecified-target/seed-3 self-consistency cases) against the real
  `run_qc(labelmap, bundled_default_config())` pipeline unchanged — every
  operator drives the existing `FragmentationRule` exactly as the spec
  predicts, with no spurious `bounds`/`border`/`overlap` findings.

- **No stochastic behaviour beyond target/pair selection.** Once a target (or
  target/neighbour pair) is resolved, all three operators are fully
  determined by body geometry — no further `seeded_rng` draws are needed for
  the split-plane position, the fuse merge, or the island placement. This
  keeps AC20/AC21 (same-seed reproducibility, non-mutation) trivially true for
  the explicit-target case while AC22's unspecified-target determinism still
  flows solely from `seeded_rng(seed)` via `_choose_label` /
  `_choose_adjacent_pair`.
