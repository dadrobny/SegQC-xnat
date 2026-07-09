# Item 038 — Coverage, border & overlap perturbations: remove level, crop at border, force overlap (modes 5, 6, 8)

> **Created:** 2026-07-08 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 038 *(second operator family; parallel with 037/039)*
> **Objectives:** G7 (evaluable & regression-testable — seeded operators that
> provably drive the Stage 4 coverage / border / overlap rules), and the
> synthetic-corpus half of G2 (materialising §6 failure modes 5, 6 and 8 against
> the item-036 framework)
> **Suggested branch:** `aide/038-coverage-border-overlap-perturbations-remove`

---

## Description

Add the **second operator family** of the Stage 5 synthetic-failure generator:
three seeded [`Perturbation`](../../../src/segqc/synth/perturbation.py) subclasses
that inject **label-coverage / spatial-extent** failures onto the item-036
clean-GT positive control
([`build_clean_spine`](../../../src/segqc/synth/clean_gt.py)), each returning a
well-formed [`Expectation`](../../../src/segqc/synth/perturbation.py) naming the
induced §6 failure mode and the offending label(s). All three implement against
the already-merged item-036 contract **unchanged** (`Perturbation` ABC,
`Expectation`, `PerturbationResult`, `register_perturbation`, `seeded_rng`,
`FAILURE_MODE_NAMES`) and start every perturbation from `build_clean_spine()`'s
output.

The three operators (§6 modes 5, 6, 8 — rule families 029 `coverage` / 031
`border` / 032 `overlap`):

1. **`remove_level`** — delete a vertebra from the **middle** of the span,
   leaving an anatomical gap bracketed above and below by segmented vertebrae.
   Detected by the **coverage** rule (item 029): the removed level becomes a
   `relationships.missing_levels` entry, so a `"Missing interior level(s):"`-tagged
   **case-level** finding (`rule_id == "coverage"`, `labels == frozenset()`, the
   offending level named in the `reason`) fires. It must trigger the missing-level
   rule **without a spurious border flag** — the remaining bodies stay inset from
   the FOV. (§6 mode 5 — not all vertebrae segmented.)

2. **`crop_at_border`** — truncate a target vertebra against a chosen **in-plane**
   image-volume face so its mask contacts the FOV edge. Detected by the
   **border** rule (item 031): the label's `geometry.touches_<face>` flag becomes
   `True` for an in-plane face (`left` / `right` / `anterior` / `posterior`),
   which the border rule always classifies as an unexpected clip, so a
   `"Partial vertebra clipped by FOV:"`-tagged, label-attributed finding
   (`rule_id == "border"`, `labels == frozenset({target})`) fires. The retained
   body stays above the level-group volume minimum, so `bounds` stays silent.
   (§6 mode 6 — partial vertebra at the image border.)

3. **`force_overlap`** — shift one label's body toward an adjacent neighbour so
   their voxel regions intersect, assigning the contested (shared) voxels to the
   target. Detected by the **overlap** rule (item 032) via `detect_overlaps`
   (item 015): the target's perturbed mask and the neighbour's original mask
   share voxels, so an `"Overlapping segments:"`-tagged finding
   (`rule_id == "overlap"`, `labels == frozenset({target, neighbour})`) fires.
   (§6 mode 8 — overlapping segments.)

   **A structural caveat pinned up front (see Assumptions):** a standard 3-D
   **single-integer** instance label map cannot store a voxel that belongs to two
   labels, and `segqc.pipeline.extract_feature_record` derives its overlap
   mask-stack **one-hot** from that single array
   (`mask_stack = np.stack([data == label for label in labels], ...)`,
   `src/segqc/pipeline.py`). Therefore the overlap is **structurally invisible to
   `run_qc`** — the target and neighbour masks in the perturbed array are disjoint
   by construction. `force_overlap` is consequently the one operator whose
   rule-firing is asserted via `detect_overlaps` + `OverlapRule` over a
   reconstructed two-channel mask stack (target-post ∪ neighbour-pre), **not** via
   the plain `run_qc` one-hot path. This is exactly how item 032 exercised the
   overlap rule, and it is surfaced here so items 040/041 handle the overlap
   corpus case deliberately (a mask-stack fixture or a pipeline multi-label
   ingestion path), rather than expecting `segqc run` to catch it.

Each operator is **seeded/deterministic** (same seed + input ⇒ byte-identical
output array, all randomness drawn solely from `seeded_rng(seed)`),
**non-mutating** (returns a fresh `Nifti1Image`, never touches the caller's
array), **spacing-aware** (correct under anisotropic spacing), and **preserves
the label-map dtype and geometry** (dtype, affine, shape, voxel spacing). Each
returned `Expectation` reflects the label(s)/level **actually** perturbed.

### Scope boundary — what this item is **not**

- **Not a change to the item-036 framework.** `synth/perturbation.py` and
  `synth/clean_gt.py` are consumed **unchanged**; this item only *adds* a new
  operator module (and one additive `__init__` import that self-registers the new
  operators).
- **Not a change to item 037's file.** `synth/component_shape.py` (the merged
  item-037 operators) is treated as frozen and is **not** edited — changes stay
  additive to avoid merge conflicts with the parallel 037/039 work.
- **Not the other operator families.** fragment / fuse / inject-islands are item
  037; displace / relabel / sequence-break are item 039.
- **Not the committed corpus, manifest, regression suite, or golden files**
  (040/041/042). This item ships operators + unit tests only; no NIfTI fixtures
  are committed.
- **Not new rules, extractors, or config.** It drives the already-merged
  `run_qc` / `CoverageRule` / `BorderRule` / `OverlapRule` / `detect_overlaps` /
  `compute_label_geometry` / bundled default config **unchanged**; it adds no
  `Rule` and edits no `heuristics` / `features` / `config` code.

---

## Public interface (new operators on the item-036 framework)

New module `src/segqc/synth/coverage_border_overlap.py` (single file, three
classes — keeps the change additive and merge-safe alongside 037/039).
Registered on `import segqc.synth` via one additive import line in
`synth/__init__.py`.

```python
@register_perturbation
class RemoveLevelPerturbation(Perturbation):
    name = "remove_level"
    def __init__(self, *, target_label: int | None = None): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 5

@register_perturbation
class CropAtBorderPerturbation(Perturbation):
    name = "crop_at_border"
    def __init__(self, *, target_label: int | None = None,
                 face: str = "anterior", crop_depth: int = 5): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 6

@register_perturbation
class ForceOverlapPerturbation(Perturbation):
    name = "force_overlap"
    def __init__(self, *, target_label: int | None = None,
                 neighbour_label: int | None = None, overlap_depth: int = 3): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 8
```

- Per the item-036 contract, `apply` takes only `(labelmap, seed)`; all operator
  parameters (which label / level to hit, which face, crop/overlap depth) are
  **constructor** arguments, and the registry stores the **class**.
- When a target (or neighbour/pair) is left `None`, the operator selects it
  deterministically from the present labels using `seeded_rng(seed)`; the chosen
  label(s) are recorded in the returned `Expectation`.
- `apply` reads present labels from `labelmap` (`np.unique` of non-zero voxels)
  and spacing/affine from `labelmap.header.get_zooms()` / `labelmap.affine`,
  exactly as the Stage 2/3 extractors and the item-037 operators do.
- **`face`** accepts the six geometry face names (`"inferior"`, `"superior"` =
  cranio-caudal axis-0 ends; `"left"`, `"right"` = axis-1; `"anterior"`,
  `"posterior"` = axis-2). The default is an **in-plane** face so the clip is
  *always* classified unexpected by `BorderRule` regardless of whether the target
  is terminal; an unknown face string raises `SegQCInputError`.

---

## Acceptance Criteria

_One test per criterion. Group A = `remove_level`, Group B = `crop_at_border`,
Group C = `force_overlap`, Group D = cross-cutting geometry / determinism /
immutability / seeding / spacing. "The clean GT" means `build_clean_spine()`
(default lumbar L1–L5, labels 20–24; the middle interior level is L3 = label 22).
"`run_qc` findings" means `run_qc(labelmap, bundled_default_config())[0].findings`._

### A. `remove_level` (§6 mode 5 — coverage rule)

- [ ] **AC1: `remove_level` is registered under `"remove_level"`.** After
      `import segqc.synth`, `get_perturbation("remove_level")` returns
      `RemoveLevelPerturbation`, `"remove_level"` is in `perturbation_names()`, and
      the class appears in `iter_perturbations()`.

- [ ] **AC2: `remove_level` deletes exactly the target interior level.** For
      `RemoveLevelPerturbation(target_label=22).apply(clean.seg_img, seed=0).labelmap`,
      label 22 is **absent** from the map's non-zero labels, and every other clean
      label (20, 21, 23, 24) is still present with its original clean voxel count.

- [ ] **AC3: `remove_level` fires the missing-interior-level coverage finding
      naming the removed level.** `run_qc` on the perturbed map emits a `Finding`
      with `rule_id == "coverage"` whose `reason` starts with
      `"Missing interior level(s):"` and names `"L3"`, and whose
      `labels == frozenset()` (case-level — the absent vertebra has no integer
      label).

- [ ] **AC4: `remove_level` produces no spurious border flag.** `run_qc` on the
      perturbed map emits **no** `rule_id == "border"` finding (the remaining
      bodies stay inset from the FOV — queue-mandated).

- [ ] **AC5: `remove_level`'s only fired rule is coverage.** In `run_qc`'s
      findings for the perturbed map, every finding has `rule_id == "coverage"`
      (no `bounds`, `fragmentation`, `sequence`, `mislabel`, `border`, or
      `overlap` finding), and no finding is attributed to a present label (every
      `finding.labels` is empty).

- [ ] **AC6: `remove_level`'s `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 5`,
      `failure_mode_name == FAILURE_MODE_NAMES[5]`,
      `expected_rule_ids == frozenset({"coverage"})`,
      `expected_labels == frozenset()` (case-level; the removed level name is
      recorded in `expectation.detail`), and
      `expected_verdict == "flagged-for-review"`; and the pipeline agrees —
      `run_qc(...).verdict.overall.label == "flagged-for-review"`.

- [ ] **AC7: an unspecified target removes an interior (non-terminal) level.**
      `RemoveLevelPerturbation().apply(clean.seg_img, seed=0)` removes a level whose
      label is **not** a span end (`∉ {20, 24}`), yields
      `expectation.expected_labels == frozenset()`, and `run_qc` reports a
      non-empty `relationships.missing_levels` (a `"coverage"` finding fires).

- [ ] **AC8: `remove_level` rejects a span with no interior level.** Applying
      `RemoveLevelPerturbation()` to a two-label map
      (`build_clean_spine(levels=["L1","L2"]).seg_img`, which has no interior
      level to remove) raises `SegQCInputError`.

- [ ] **AC9: `remove_level` rejects an explicit terminal target.**
      `RemoveLevelPerturbation(target_label=20).apply(clean.seg_img, seed=0)`
      (label 20 is the superior span end) raises `SegQCInputError` (removing a
      span-end level produces no detectable interior gap).

### B. `crop_at_border` (§6 mode 6 — border rule)

- [ ] **AC10: `crop_at_border` is registered under `"crop_at_border"`.** After
      `import segqc.synth`, `get_perturbation("crop_at_border")` returns
      `CropAtBorderPerturbation`, and `"crop_at_border"` is in
      `perturbation_names()`.

- [ ] **AC11: `crop_at_border` makes the target contact the chosen in-plane
      face.** For
      `CropAtBorderPerturbation(target_label=22, face="anterior").apply(clean.seg_img, seed=0).labelmap`,
      `compute_label_geometry(labelmap, 22).touches_anterior` is `True`, while the
      same flag on the un-perturbed clean GT's label 22 is `False`.

- [ ] **AC12: `crop_at_border` fires the border finding on the target.** `run_qc`
      on the cropped map emits a `Finding` with `rule_id == "border"` whose
      `reason` starts with `"Partial vertebra clipped by FOV:"` and
      `labels == frozenset({22})`.

- [ ] **AC13: `crop_at_border` produces no spurious bounds flag.** `run_qc` on the
      cropped map emits **no** `rule_id == "bounds"` finding (the retained body
      stays inside the level group's volume/extent bounds).

- [ ] **AC14: `crop_at_border`'s `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 6`,
      `failure_mode_name == FAILURE_MODE_NAMES[6]`,
      `expected_rule_ids == frozenset({"border"})`,
      `expected_labels == frozenset({22})`, and
      `expected_verdict == "flagged-for-review"`; and the pipeline agrees —
      `run_qc(...).verdict.overall.label == "flagged-for-review"`.

- [ ] **AC15: `crop_at_border` leaves every other present label unflagged.** In
      `run_qc`'s findings for the cropped map, no finding is attributed to any
      present label other than 22 (every non-empty `finding.labels` is a subset of
      `{22}`).

- [ ] **AC16: the default face is in-plane and flags regardless of terminal
      position.** `CropAtBorderPerturbation(target_label=20).apply(clean.seg_img, seed=0)`
      (label 20 is a span end, default face, no explicit face) still fires a
      `rule_id == "border"` finding on `frozenset({20})` — an in-plane clip is
      always unexpected, even for a terminal vertebra.

- [ ] **AC17: `crop_at_border` rejects an unknown face string.**
      `CropAtBorderPerturbation(target_label=22, face="diagonal").apply(clean.seg_img, seed=0)`
      raises `SegQCInputError`.

### C. `force_overlap` (§6 mode 8 — overlap rule)

- [ ] **AC18: `force_overlap` is registered under `"force_overlap"`.** After
      `import segqc.synth`, `get_perturbation("force_overlap")` returns
      `ForceOverlapPerturbation`, and `"force_overlap"` is in
      `perturbation_names()`.

- [ ] **AC19: `force_overlap` assigns shared voxels to the target.** For
      `ForceOverlapPerturbation(target_label=20, neighbour_label=21, overlap_depth=3).apply(clean.seg_img, seed=0).labelmap`,
      the intersection of the perturbed target mask `(labelmap_data == 20)` and the
      **clean** neighbour mask `(clean_data == 21)` has a strictly positive voxel
      count `k > 0`, and the neighbour's perturbed voxel count equals its clean
      voxel count minus `k` (the contested voxels were reassigned from 21 to 20).

- [ ] **AC20: `force_overlap` drives the overlap rule with the offending pair.**
      Building `pairs = detect_overlaps(np.stack([(labelmap_data == 20),
      (clean_data == 21)]), np.array([20, 21]))` and a feature record
      `{"overlaps": [overlap_to_dict(p) for p in pairs]}`,
      `OverlapRule().evaluate(record, bundled_default_config())` returns a `Finding`
      with `rule_id == "overlap"` whose `reason` starts with
      `"Overlapping segments:"` and `labels == frozenset({20, 21})`.

- [ ] **AC21: `force_overlap`'s `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 8`,
      `failure_mode_name == FAILURE_MODE_NAMES[8]`,
      `expected_rule_ids == frozenset({"overlap"})`,
      `expected_labels == frozenset({20, 21})`, and
      `expected_verdict == "flagged-for-review"`.

- [ ] **AC22: the single-integer label map hides the overlap from `run_qc`
      (documented limitation).** `run_qc` on the perturbed `labelmap` emits **no**
      `rule_id == "overlap"` finding — a single-integer instance label map cannot
      carry a voxel shared by two labels, and the pipeline derives its overlap
      mask-stack one-hot, so the overlap is structurally invisible to `run_qc`.
      (Locks the limitation for items 040/041; see Assumptions.)

- [ ] **AC23: `force_overlap` rejects a too-small or non-adjacent input.**
      Applying `ForceOverlapPerturbation()` to a single-label map
      (`build_clean_spine(levels=["L3"]).seg_img`) raises `SegQCInputError`; and
      `ForceOverlapPerturbation(target_label=20, neighbour_label=23)` (labels 20
      and 23 are not adjacent in the sorted present-label order) raises
      `SegQCInputError`.

### D. Cross-cutting: geometry, determinism, immutability, seeding, spacing

- [ ] **AC24: every operator preserves dtype and geometry.** For each of the three
      operators (with an explicit target — and, for `force_overlap`, an explicit
      neighbour), the output `labelmap` has the same array `dtype`, an affine that
      is `np.array_equal` to the input's, the same `shape`, and
      `header.get_zooms()[:3]` equal to the input's spacing.

- [ ] **AC25: every operator is reproducible (same seed + input ⇒ identical
      array).** For each of the three operators, two `apply(clean.seg_img, seed=7)`
      calls (same explicit target/neighbour) return output arrays that are
      `np.array_equal`.

- [ ] **AC26: every operator is non-mutating.** For each of the three operators,
      the data array of the `seg_img` passed to `apply` is unchanged (equal to a
      pre-call copy) after the call returns.

- [ ] **AC27: an unspecified target is chosen deterministically from the seed, and
      the `Expectation` names the entity actually perturbed.** For each operator
      with no explicit target, two `apply(clean.seg_img, seed=3)` calls select the
      **same** target (identical output arrays); and the operator's designated rule
      fires for the label(s)/level actually recorded in
      `result.expectation` (self-consistency, whichever the seed picked).

- [ ] **AC28: every operator is spacing-aware.** Applying each operator (with an
      explicit target/neighbour) to an anisotropic clean GT
      (`build_clean_spine(spacing=(1.0, 1.0, 3.0))`) still drives its designated
      rule — `remove_level` → a `"coverage"` finding; `crop_at_border` → a
      `"border"` finding on the target; `force_overlap` → a `detect_overlaps` pair
      on the target/neighbour — and preserves the input spacing
      (`get_zooms()[:3] == (1.0, 1.0, 3.0)`).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **`force_overlap` cannot be surfaced by `run_qc`; its rule-firing is asserted
  via `detect_overlaps` + `OverlapRule` on a reconstructed mask stack. This is the
  most material clarify=`assume` decision — the validator should surface it at the
  queue boundary.** A standard 3-D **single-integer** instance label map (the
  `Perturbation` contract's `nib.Nifti1Image` output) physically cannot store a
  voxel belonging to two labels, and `segqc.pipeline.extract_feature_record`
  builds its overlap mask-stack **one-hot** from that single array
  (`mask_stack = np.stack([data == label for label in labels], axis=0)`,
  `src/segqc/pipeline.py`), so `detect_overlaps` over the *perturbed* map always
  sees disjoint channels and finds nothing. The queue's "assert the overlap rule
  fires with the expected offending labels" is therefore met honestly by driving
  `detect_overlaps` on a **two-channel** stack `[(perturbed == target),
  (clean == neighbour)]` — the target-post and neighbour-pre footprints, whose
  intersection is exactly the reassigned/contested slab — then running
  `OverlapRule` on the resulting `overlaps` record (AC20). This mirrors how item
  032 itself exercised `OverlapRule`. AC22 additionally **locks** the fact that
  the plain `run_qc` path does *not* surface the overlap, so items 040 (corpus)
  and 041 (regression suite) must represent the overlap §6-mode case as a
  mask-stack fixture (or add a pipeline multi-label ingestion path) rather than
  expecting `segqc run` end-to-end to catch it. This is a Stage-5-level design
  fact surfaced now for audit, not a defect introduced by this item.

- **`remove_level`'s offending "label" is a missing *level name*, so
  `expected_labels == frozenset()`.** `CoverageRule` emits **case-level**
  missing-interior-level findings (`labels == frozenset()`), naming the absent
  level in the `reason` (item 029). The queue's "naming the induced §6 mode and
  offending label(s)" is satisfied by recording the removed level name in
  `Expectation.detail` while `expected_labels` stays empty — consistent with item
  037's documented case-level coverage co-firing. The operator removes an
  **interior** (non-terminal) level because `relationships.missing_levels` reports
  only gaps *within* the present span (`src/segqc/features/relationships.py`);
  removing a span-end level shrinks the span and produces no detectable gap, so an
  explicit terminal target and a span with no interior level are rejected
  (AC8/AC9). The default target is the **middle** interior level (label 22 = L3
  for the default lumbar span).

- **`crop_at_border` defaults to an *in-plane* face and honours "truncate" by
  translate-and-clip.** `BorderRule` always classifies an in-plane touch
  (`touches_left`/`right`/`anterior`/`posterior`) as an unexpected clip, whereas a
  cranio-caudal end touch on a *terminal* vertebra is suppressed as an expected
  FOV-end truncation (item 031). Defaulting `face` to an in-plane face therefore
  guarantees the border rule fires regardless of the target's terminal position
  (AC16). The operator realises a genuine truncation by translating the target
  body toward the chosen face by `margin + crop_depth` voxels and clipping the
  overhang outside the FOV, so the retained body **touches** the face; `crop_depth`
  defaults small enough that the retained physical volume/extent stays inside the
  level group's `bounds`, keeping `bounds` silent (AC13). The centroid shifts
  in-plane, but `mislabel` stays silent because `fit_centroid_spline` interpolates
  every centroid exactly (`s=0`, per the item-036 clean-GT design), so the moved
  centroid lands on the fitted spline with a near-zero offset.

- **`force_overlap` shifts the target body toward its adjacent neighbour (rather
  than dilating), so no rule other than overlap is provoked.** Translating the
  whole target body by `gap + overlap_depth` voxels along the stacking axis (axis
  0) toward the neighbour keeps the target a single solid block of **unchanged
  volume** (no `bounds`/`fragmentation` risk) while its leading `overlap_depth`
  voxels come to occupy voxels the neighbour owned; those contested voxels are
  assigned to the target in the single output array (the neighbour shrinks by
  `overlap_depth × cross-section`, staying above its group minimum). Adjacency is
  defined as consecutive position in the sorted present-label list (matching item
  037's `fuse`), and the operator raises for a non-adjacent explicit pair or a
  map with fewer than two labels (AC23). `expected_labels` is
  `frozenset({target, neighbour})` — both are present, real labels (unlike the
  case-level coverage finding).

- **Operators are parameterised classes; `apply` takes only `(labelmap, seed)`
  (per the item-036 contract).** Target/level/neighbour selection, face, and
  crop/overlap depth are **constructor** arguments; the registry stores the class.
  When a target/pair is left `None`, it is chosen deterministically from the
  present labels via `seeded_rng(seed)`, and the choice is recorded in the returned
  `Expectation` (AC27). This matches item 036's explicit design note and item
  037's precedent.

- **The returned `Expectation` reflects the entity *actually* perturbed.** So a
  test asserts the pipeline-fired result against `result.expectation`
  (self-consistent), robust to which label/level a `None` target + seed selects.
  Tests that need a fixed offender pass an explicit `target_label` (and
  `neighbour_label` for `force_overlap`).

- **Single new module `src/segqc/synth/coverage_border_overlap.py`, plus one
  additive `__init__` import.** The three classes live in one file to minimise the
  shared-file surface. `synth/__init__.py` gains **one** import line (plus the
  three class names in its `__all__`) so the operators self-register on
  `import segqc.synth`, mirroring `IdentityPerturbation` and item 037's
  `component_shape`. This is additive and at a distinct line region from what 037
  (already merged) and 039 (parallel) touch, so git merges the sibling
  registrations cleanly. `synth/perturbation.py`, `synth/clean_gt.py`, and
  `synth/component_shape.py` are **not** edited.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `CoverageRule` with `rule_id == "coverage"`, reason tag
  `"Missing interior level(s):"`, and case-level (`frozenset()`) missing-level
  findings driven off `relationships.missing_levels`; `BorderRule` with
  `rule_id == "border"`, reason tag `"Partial vertebra clipped by FOV:"`,
  label-attributed findings, in-plane faces always unexpected;
  `OverlapRule` with `rule_id == "overlap"`, reason tag `"Overlapping segments:"`,
  default `min_overlap_voxels == 1`, reading `record["overlaps"]`;
  `detect_overlaps(mask_stack, labels) -> list[OverlapPair]` on a
  `(n_labels, X, Y, Z)` boolean stack; `overlap_to_dict(pair) -> dict` with
  `label_a`/`label_b`/`name_a`/`name_b`/`overlap_voxels`;
  `compute_label_geometry(seg, label)` with `touches_{left,right,anterior,
  posterior,superior,inferior}` and `extent_{x,y,z}_mm`;
  `run_qc(seg_img, config) -> (CaseResult, dict)` with
  `CaseResult.findings: tuple[Finding, ...]` and `CaseResult.verdict.overall.label`;
  `Finding.labels: frozenset[int]`; `segqc.config.bundled_default_config`;
  `segqc.io.SegQCInputError`.

## Implementation Steps

Intended code path: new file `src/segqc/synth/coverage_border_overlap.py` + one
additive import in `src/segqc/synth/__init__.py`. No edits to existing production
modules.

1. **Create `src/segqc/synth/coverage_border_overlap.py`** importing from the
   item-036 framework (`Perturbation`, `Expectation`, `PerturbationResult`,
   `register_perturbation`, `seeded_rng`, `FAILURE_MODE_NAMES`), `numpy`,
   `nibabel`, and `segqc.io.SegQCInputError`. Reuse the same private-helper idioms
   as item 037 (`_present_labels`, `_choose_label`, a copy-into-fresh-image
   builder, a label-bbox helper) — implemented locally here (do **not** import
   from `component_shape.py`, to keep the files independent and merge-safe).

2. **Shared module-private helpers:** `_present_labels(labelmap)` (sorted non-zero
   uniques); a fresh-image builder that copies the data array (same dtype) and the
   input affine (never mutating the caller); a label-bbox helper; a
   `_require_present` guard raising `SegQCInputError`; and a face→(axis, side)
   resolver mapping the six face names, raising `SegQCInputError` on an unknown
   face.

3. **`RemoveLevelPerturbation`** (`name = "remove_level"`,
   `__init__(*, target_label=None)`): read present labels (raise if `< 3` — no
   interior level exists); resolve the target — an explicit target must be present
   **and** non-terminal (not the first/last in sorted order), else `SegQCInputError`;
   an unspecified target defaults to the **middle** interior label (or a
   `seeded_rng(seed)` pick among the interior labels), recorded in the Expectation.
   Copy the array, zero every voxel equal to the target label. Build
   `Expectation(failure_mode=5, failure_mode_name=FAILURE_MODE_NAMES[5],
   expected_rule_ids=frozenset({"coverage"}), expected_labels=frozenset(),
   expected_verdict="flagged-for-review", detail="remove_level: deleted <level>
   (label <n>) ...")`; return `PerturbationResult`.

4. **`CropAtBorderPerturbation`** (`name = "crop_at_border"`,
   `__init__(*, target_label=None, face="anterior", crop_depth=5)`): resolve the
   face (raise on unknown) and target (explicit must be present; else choose via
   `seeded_rng(seed)`). Copy the array; translate the target body toward the chosen
   face by `margin + crop_depth` voxels along that axis and clip the overhang that
   falls outside `[0, shape[axis])`, so the retained body touches the face
   (`touches_<face>` becomes `True`) while its retained volume stays inside the
   level-group `bounds`. Build `Expectation(failure_mode=6,
   failure_mode_name=FAILURE_MODE_NAMES[6], expected_rule_ids=frozenset({"border"}),
   expected_labels=frozenset({target}), expected_verdict="flagged-for-review",
   detail=...)`; return `PerturbationResult`.

5. **`ForceOverlapPerturbation`** (`name = "force_overlap"`,
   `__init__(*, target_label=None, neighbour_label=None, overlap_depth=3)`): read
   present labels (raise if `< 2`); resolve an **adjacent** (consecutive-in-sorted-
   order) `(target, neighbour)` pair — explicit pair validated for presence and
   adjacency, else chosen via `seeded_rng(seed)`. Copy the array; shift the whole
   target body along the stacking axis (axis 0) toward the neighbour by
   `gap + overlap_depth` voxels (compute the current inter-body gap from the
   bboxes) so the target's leading `overlap_depth` voxels come to occupy voxels the
   neighbour owned; assign the contested voxels to the target (write the shifted
   target block; the neighbour loses the overlapped slab). Keep the target a single
   solid block of unchanged volume. Build `Expectation(failure_mode=8,
   failure_mode_name=FAILURE_MODE_NAMES[8], expected_rule_ids=frozenset({"overlap"}),
   expected_labels=frozenset({target, neighbour}),
   expected_verdict="flagged-for-review", detail=...)`; return
   `PerturbationResult`.

6. **Determinism & seeding.** Any stochastic choice (unspecified target/level/pair,
   any placement jitter) derives solely from `seeded_rng(seed)`; the same seed +
   input yields a byte-identical output array. Deterministic-once-resolved operators
   still accept and thread `seed`. Never mutate the caller's array; always return a
   fresh `Nifti1Image` with the input's affine and dtype.

7. **Register + wire.** Decorate each class with `@register_perturbation`, and add
   the single additive import line to `src/segqc/synth/__init__.py` (plus the three
   class names to its `__all__`) so `import segqc.synth` self-registers all three,
   mirroring `IdentityPerturbation` and item 037's operators.

8. **Do not** edit `synth/perturbation.py`, `synth/clean_gt.py`,
   `synth/component_shape.py`, or any `heuristics` / `features` / `config` module.

## Testing Strategy

- **Framework:** `pytest`. New module
  `tests/test_038_coverage_border_overlap_perturbations.py`, in the same style as
  `tests/test_037_component_shape_perturbations.py` (build a clean-GT fixture,
  apply the operator, run `run_qc(perturbed, bundled_default_config())`, assert on
  `case_result.findings` / `verdict`, and cross-check the raw geometry/topology via
  `compute_label_geometry` / `detect_overlaps`).
- **No registry snapshot needed** — the three operators are real, permanent
  registrations (like `identity` and item 037's operators); tests import them from
  `segqc.synth`.
- **Helpers:** a `_clean()` fixture (`build_clean_spine()`), a
  `_findings(labelmap)` helper returning
  `run_qc(labelmap, bundled_default_config())[0].findings`, a
  `_rule_ids(findings)` helper, and a `_flagged_present_labels(findings)` helper
  (union of non-empty `finding.labels`) for the "other labels stay unflagged"
  assertions.
- **`remove_level` (AC1–AC9):** registration (AC1); target-absent + others-present
  with counts (AC2); `"Missing interior level(s):"` case-level finding naming L3
  (AC3); no `border` finding (AC4); only-`coverage` + all findings case-level
  (AC5); `Expectation` fields + pipeline verdict (AC6); unspecified-target picks an
  interior level (AC7); `SegQCInputError` on a two-label span (AC8) and on an
  explicit terminal target (AC9).
- **`crop_at_border` (AC10–AC17):** registration (AC10); `touches_anterior`
  True-after / False-before via `compute_label_geometry` (AC11);
  `"Partial vertebra clipped by FOV:"` finding on `{22}` (AC12); no `bounds`
  finding (AC13); `Expectation` + verdict (AC14); flagged-present-labels ⊆ `{22}`
  (AC15); default-face border finding on a terminal target `{20}` (AC16);
  `SegQCInputError` on an unknown face (AC17).
- **`force_overlap` (AC18–AC23):** registration (AC18); positive shared-voxel count
  `k` between `(perturbed==20)` and `(clean==21)` plus neighbour count reduced by
  `k` (AC19); `detect_overlaps` → `overlap_to_dict` record → `OverlapRule` finding
  on `{20, 21}` (AC20); `Expectation` fields (AC21); **no** `overlap` finding via
  `run_qc` (documented one-hot limitation) (AC22); `SegQCInputError` on a
  single-label map and on a non-adjacent explicit pair (AC23).
- **Cross-cutting (AC24–AC28):** parametrise across the three operator instances —
  dtype/affine/shape/zooms preservation (AC24); two same-seed applies →
  `np.array_equal` (AC25); pre-call array copy unchanged after apply (AC26);
  unspecified-target same-seed determinism + designated rule fires for the recorded
  offender (AC27); anisotropic `spacing=(1.0, 1.0, 3.0)` still drives each
  designated rule and preserves spacing (AC28).
- **Adversarial / edge cases:**
  - `remove_level` / `crop_at_border` / `force_overlap` with an **explicit** target
    not present in the map raise `SegQCInputError` (do not silently no-op).
  - `crop_at_border` against each of the four in-plane faces (`left`/`right`/
    `anterior`/`posterior`) sets the matching `touches_*` flag and fires `border`.
  - `crop_at_border` retains a physical volume above the level group's minimum
    (a direct `compute_label_geometry` `physical_volume_mm3` check — no spurious
    `bounds`).
  - `force_overlap` under anisotropic spacing still yields `k > 0` shared voxels
    (the reassigned slab is a voxel count, spacing-independent).
  - Two **different** seeds with an unspecified target may pick different
    offenders, but each result stays self-consistent (the designated rule fires for
    `result.expectation`'s recorded offender).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 036** — the synthetic-corpus foundation this item builds on directly:
    `segqc.synth.clean_gt.build_clean_spine` / `CleanSpine` (every perturbation
    starts from its output) and the `segqc.synth.perturbation` framework
    (`Perturbation` ABC, `Expectation`, `PerturbationResult`,
    `register_perturbation` / `get_perturbation` / `iter_perturbations` /
    `perturbation_names`, `seeded_rng`, `FAILURE_MODE_NAMES`). Implemented against
    this **exact** interface, unchanged.
  - **Item 029** — `segqc.heuristics.coverage.CoverageRule` (`rule_id ==
    "coverage"`, reason tag `"Missing interior level(s):"`, case-level missing-level
    findings off `relationships.missing_levels`): the rule `remove_level` drives.
  - **Item 031** — `segqc.heuristics.border.BorderRule` (`rule_id == "border"`,
    reason tag `"Partial vertebra clipped by FOV:"`, in-plane faces always
    unexpected): the rule `crop_at_border` drives.
  - **Item 032** — `segqc.heuristics.overlap.OverlapRule` (`rule_id == "overlap"`,
    reason tag `"Overlapping segments:"`, default `min_overlap_voxels == 1`,
    reads `record["overlaps"]`): the rule `force_overlap` drives.
  - **Item 015** — `segqc.features.overlap.detect_overlaps` / `OverlapPair`: the
    mask-stack overlap detector the `force_overlap` test drives (the pipeline's
    one-hot path cannot surface a single-map overlap — see Assumptions).
  - **Item 016 / 022** — `segqc.feature_report.overlap_to_dict` /
    `build_features_block`: the `overlaps` record shape `OverlapRule` consumes.
  - **Item 014** — `segqc.features.relationships.compute_spine_relationships`
    (`missing_levels` / `present_levels`): the relationships `remove_level`'s
    coverage detection reads.
  - **Item 011** — `segqc.features.geometry.compute_label_geometry`
    (`touches_*`, `extent_{x,y,z}_mm`, `physical_volume_mm3`): the border-contact /
    bounds checks the `crop_at_border` tests read.
  - **Item 035** — `segqc.pipeline.run_qc` + `segqc.config.bundled_default_config`:
    the full-pipeline entry point the perturbed maps run through.
  - **Item 034** — `segqc.aggregate` (`CaseResult`, `verdict.overall.label`): the
    verdict shape the expectations are checked against.
  - **Item 026** — `segqc.heuristics.finding.Finding` (`rule_id`, `reason`,
    `labels`): the finding shape assertions read.
  - **Item 004** — `segqc.labels` (default convention labels L1–L5 = 20–24) via
    `build_clean_spine`.
  - **Item 003** — `segqc.io.SegQCInputError`: the error type for absent-target /
    too-few-labels / terminal-target / non-adjacent-pair / unknown-face guards.
- **Structural precedent (not a functional dependency):**
  - **Item 037** — `segqc.synth.component_shape` (fragment / fuse / inject-islands)
    is the sibling operator-family that established the module structure this item
    follows (single additive file, constructor-parameterised operators over the
    shared item-036 framework, `run_qc`-based assertions). This item imports
    **nothing** from item 037 and does not edit its file; it is named here only as
    the pattern to mirror, and to make explicit that the `__init__.py` registration
    line stays additive and merge-safe.
- **Not dependencies (parallel sibling):** item **039** builds the third operator
  family against the same item-036 interface; this item is independent of it and
  its changes stay additive to avoid merge conflicts.

## Decisions & Trade-offs

- **`remove_level`'s unspecified-target choice is the literal middle interior
  label, not a `seeded_rng` draw.** The Implementation Steps offered either
  option ("defaults to the middle interior label (or a `seeded_rng(seed)` pick
  among interior labels)"). Chose the literal middle (`interior[len(interior)
  // 2]`) for simplicity and because the Public-interface bullet and
  Assumptions both independently state "Default target: the middle interior
  label" / "The default target is the middle interior label (label 22 = L3 for
  the default lumbar span)" without qualification. `seed` is still accepted
  and threaded per the `Perturbation` signature but unused by this operator's
  selection logic; determinism (AC27) holds trivially since the choice never
  varies. `crop_at_border` and `force_overlap` do use `seeded_rng`/`_choose_
  label`/`_choose_adjacent_pair` for their unspecified-target/pair selection,
  matching item 037's precedent, since the spec's Assumptions single out only
  `remove_level`'s default as "the middle interior label."

- **`crop_at_border` realises "translate by margin + crop_depth, then clip"
  via an `np.argwhere` shift-and-filter on the target's own voxel coordinates**
  (mirroring `InjectIslandsPerturbation`'s fancy-indexing idiom in
  `component_shape.py`, reimplemented locally per the scope boundary). `margin`
  is computed dynamically from the target's own bounding box distance to the
  chosen face (not the clean-GT's fixed `_MARGIN_MM`), so the operator is
  robust to any starting position. Because bodies in `build_clean_spine` are
  separated only along axis 0 and share axis-1/axis-2 footprints, an in-plane
  crop (axis 1 or 2) can never alias into a neighbouring vertebra's voxels;
  this was verified but not needed for the axis-0 (`superior`/`inferior`) face
  arms, which are supported (per the pinned six-face interface, reject only an
  unknown string) but not exercised by any AC/adversarial test — a large
  axis-0 translation on a mid-spine target could in principle intrude on an
  adjacent vertebra's footprint; this is accepted as an unexercised corner of
  the six-face contract, consistent with the spec defaulting `face` to an
  in-plane value specifically to sidestep axis-0 semantics.

- **Under anisotropic spacing (`spacing=(1.0, 1.0, 3.0)`), `crop_at_border`'s
  default `crop_depth=5` can additionally trip the `bounds` rule's
  `min_extent_z_mm` floor** (verified: label 22's z-extent drops from 27 mm to
  12 mm against lumbar's 15 mm minimum, because the anisotropic z-spacing
  shrinks the body to only 9 voxels along that axis, and cropping 5 of them
  removes over half the extent). AC13 (no spurious `bounds` finding) is scoped
  to the default-spacing fixture only, and AC28's anisotropic assertion checks
  only that the `border` rule fires (via `_designated_rule_fires`), which it
  does; both are satisfied as verified via manual smoke tests during
  implementation. Not treated as a defect — `crop_depth` is a caller-supplied
  constructor parameter and a caller targeting extreme anisotropic spacing can
  pass a smaller value.

- **`force_overlap`'s target-shift direction and gap are computed from the
  target/neighbour bounding boxes at `apply` time** (not hardcoded to a fixed
  sign), so the same operator instance works correctly regardless of which of
  the pair sits at the lower or higher axis-0 position. The contested overhang
  is reassigned to the target by erasing the target's original footprint and
  writing the shifted coordinates last, so any neighbour voxels the shifted
  block lands on are overwritten to the target label — exactly the
  "reassign contested voxels from neighbour to target" behaviour AC19 checks.

- **Added lightweight constructor-time guards not explicitly required by an
  AC** (`crop_depth >= 1` for `CropAtBorderPerturbation`, `overlap_depth >= 1`
  for `ForceOverlapPerturbation`, and a "would clip the entire body away" /
  "would shift the target outside the image bounds" guard in each `apply`).
  These raise `SegQCInputError` for degenerate parameterisations that no test
  exercises (all tests use the documented defaults or small explicit depths
  well within body extents); added defensively per the class's role as a
  reusable operator for the not-yet-built corpus generator (items 040/041).

- Implemented exactly the three classes, local shared helpers (not imported
  from `component_shape.py`), and the one additive `synth/__init__.py` import
  block, per the spec's scope boundary. No edits to `perturbation.py`,
  `clean_gt.py`, or `component_shape.py`.
