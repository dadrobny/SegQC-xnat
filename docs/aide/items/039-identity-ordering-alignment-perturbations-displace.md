# Item 039 — Identity, ordering & alignment perturbations: displace, relabel/swap, sequence-break (modes 1, 4, 7)

> **Created:** 2026-07-09 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 039 *(third operator family; parallel with 037/038)*
> **Objectives:** G7 (evaluable & regression-testable — seeded operators that
> provably drive the Stage 4 mislabel / misalignment / sequence-continuity
> rules), and the synthetic-corpus half of G2 (materialising §6 failure modes
> 1, 4 and 7 against the item-036 framework)
> **Suggested branch:** `aide/039-identity-ordering-alignment-perturbations-displace`

---

## Description

Add the **third and final operator family** of the Stage 5 synthetic-failure
generator: three seeded [`Perturbation`](../../../src/segqc/synth/perturbation.py)
subclasses that inject **label-identity / ordering / spatial-alignment** failures
onto the item-036 clean-GT positive control
([`build_clean_spine`](../../../src/segqc/synth/clean_gt.py)), each returning a
well-formed [`Expectation`](../../../src/segqc/synth/perturbation.py) naming the
induced §6 failure mode and the offending label(s). All three implement against
the already-merged item-036 contract **unchanged** (`Perturbation` ABC,
`Expectation`, `PerturbationResult`, `register_perturbation`, `seeded_rng`,
`FAILURE_MODE_NAMES`) and start every perturbation from `build_clean_spine()`'s
output.

The three operators (§6 modes 1, 4, 7 — rule families 033 `mislabel` / 030
`sequence`):

1. **`displace`** — translate one vertebra's whole mask off the fitted spinal
   curve while keeping its label. Targets the **misalignment** detector of the
   [`MislabelRule`](../../../src/segqc/heuristics/mislabel.py) (item 033,
   Detector A, `rule_id == "mislabel"`, reason tag
   `"Vertebra misaligned from spinal curve:"`): the displaced centroid's
   perpendicular offset from the curve defined by the **other** vertebrae exceeds
   the default `max_offset_mm = 15.0`. (§6 mode 1 — label not aligned with the
   vertebra it names.)

   **A structural caveat pinned up front (see Assumptions):** the real pipeline
   (`segqc.pipeline.extract_feature_record`, item 035) fits the spinal spline
   through **all present centroids** with `scipy...splprep(..., s=0)` — an
   *interpolating* fit that passes through every centroid exactly (item 017), so
   `compute_spline_offsets` reports **every** offset as ≈ 0, including the
   displaced one (verified: all offsets `0.0`). A single displaced vertebra is
   therefore **structurally invisible to `run_qc`**. `displace`'s rule-firing is
   asserted the way item 038's `force_overlap` asserted the overlap rule: via a
   **reconstructed** `per_label_offsets` record whose target offset is the
   *leave-one-out* offset (the displaced centroid measured against the spline fit
   through the remaining vertebrae) fed to `MislabelRule` directly. An AC
   additionally **locks** that plain `run_qc` does not surface the displacement,
   for items 040/041 to handle deliberately.

2. **`relabel_swap`** — exchange the integer labels ("identities") of **two
   adjacent** vertebra bodies, so each label now sits at the other's anatomical
   position while the present-label **set is unchanged**. Targets the
   **ordering-inconsistency** detector of the `MislabelRule` (item 033, Detector
   B, `rule_id == "mislabel"`, reason tag
   `"Vertebra ordering inconsistent with label:"`), driven by
   `stage3.monotonic_consistency.non_monotonic_pairs` (item 020). (§6 mode 4 —
   semantic mislabelling / wrong identification.)

   **The same structural caveat applies (see Assumptions):** because the pipeline
   orders centroids by **ascending integer label** and refits the interpolating
   spline through *that* order, the spline parameter `u` is monotonic by
   construction and `non_monotonic_pairs` is **always empty** through `run_qc`
   (verified: a swap produces zero findings). `relabel_swap`'s rule-firing is
   asserted via a **reconstructed** `monotonic_consistency` record — the spline
   fit through the centroids in **true spatial (axis-0) order** and the
   ascending-label centroids evaluated against it, exposing the reversal — fed to
   `MislabelRule` directly. An AC locks that `run_qc` does not surface the swap.

3. **`sequence_break`** — relabel one vertebra to a **transitional** label whose
   integer value contradicts its anatomical rank, producing a value-ordered label
   sequence that is non-monotonic in canonical rank. Targets the
   [`SequenceRule`](../../../src/segqc/heuristics/sequence.py) (item 030,
   `rule_id == "sequence"`, reason tag `"Non-continuous label sequence:"`), driven
   by `relationships.out_of_order_labels` (item 014). Unlike the other two, this
   operator **fires through the real `run_qc` pipeline directly** (§6 mode 7 —
   non-continuous label sequence).

   The lever is the default convention's deliberate value/rank divergence
   (`src/segqc/labels.py`): **T13 = integer label 28** but **canonical rank 19**
   (below L1). Relabelling the **tail** vertebra of the default lumbar span
   (L5 = 24) to **T13 = 28** makes 28 sort *last* by value yet rank *first* by
   anatomy → `out_of_order_labels == ["T13"]`, while the surviving span
   `T13, L1, L2, L3, L4` stays canonically contiguous so **no missing-level
   coverage finding co-fires** (verified: the only finding is `sequence`,
   `labels == {28}`).

Each operator is **seeded/deterministic** (same seed + input ⇒ byte-identical
output array, all randomness drawn solely from `seeded_rng(seed)`),
**non-mutating** (returns a fresh `Nifti1Image`, never touches the caller's
array), **spacing-aware** (correct under anisotropic spacing), and **preserves
the label-map dtype and geometry** (dtype, affine, shape, voxel spacing). Each
returned `Expectation` reflects the label(s) **actually** perturbed.

### Scope boundary — what this item is **not**

- **Not a change to the item-036 framework.** `synth/perturbation.py` and
  `synth/clean_gt.py` are consumed **unchanged**; this item only *adds* a new
  operator module (and one additive `__init__` import that self-registers the new
  operators).
- **Not a change to items 037/038's files.** `synth/component_shape.py` and
  `synth/coverage_border_overlap.py` (the merged item-037/038 operators) are
  treated as **frozen** and are **not** edited — changes stay additive so git
  merges the sibling registrations cleanly.
- **Not the other operator families.** fragment / fuse / inject-islands are item
  037; remove-level / crop / overlap are item 038.
- **Not the committed corpus, manifest, regression suite, or golden files**
  (040/041/042). This item ships operators + unit tests only; no NIfTI fixtures
  are committed.
- **Not new rules, extractors, or config.** It drives the already-merged
  `run_qc` / `MislabelRule` / `SequenceRule` / `compute_spline_offsets` /
  `compute_monotonic_consistency` / `compute_spine_relationships` / bundled
  default config **unchanged**; it adds no `Rule` and edits no `heuristics` /
  `features` / `config` code.

---

## Public interface (new operators on the item-036 framework)

New module `src/segqc/synth/identity_ordering_alignment.py` (single file, three
classes — keeps the change additive and merge-safe alongside 037/038).
Registered on `import segqc.synth` via one additive import line in
`synth/__init__.py`.

```python
@register_perturbation
class DisplacePerturbation(Perturbation):
    name = "displace"
    def __init__(self, *, target_label: int | None = None,
                 displacement_mm: float = 18.0): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 1

@register_perturbation
class RelabelSwapPerturbation(Perturbation):
    name = "relabel_swap"
    def __init__(self, *, target_label: int | None = None,
                 neighbour_label: int | None = None): ...
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 4

@register_perturbation
class SequenceBreakPerturbation(Perturbation):
    name = "sequence_break"
    def __init__(self, *, target_label: int | None = None,
                 new_label: int = 28): ...                        # 28 == T13
    def apply(self, labelmap, seed) -> PerturbationResult: ...   # §6 mode 7
```

- Per the item-036 contract, `apply` takes only `(labelmap, seed)`; all operator
  parameters (which label/pair to hit, displacement magnitude, replacement label)
  are **constructor** arguments, and the registry stores the **class**.
- When a target (or pair) is left `None`, the operator selects it
  deterministically from the present labels using `seeded_rng(seed)`, and the
  choice is recorded in the returned `Expectation`. `sequence_break`'s default
  target is the **tail** (max present label) — a deterministic choice (`seed`
  accepted for interface compliance; see the Decisions log), because only the
  tail→T13 relabel keeps the span contiguous (no coverage co-fire).
- `apply` reads present labels from `labelmap` (`np.unique` of non-zero voxels)
  and spacing/affine from `labelmap.header.get_zooms()` / `labelmap.affine`,
  exactly as the Stage 2/3 extractors and the item-037/038 operators do.

---

## Acceptance Criteria

_One test per criterion. Group A = `displace`, Group B = `relabel_swap`, Group C
= `sequence_break`, Group D = cross-cutting geometry / determinism / immutability
/ seeding / spacing. "The clean GT" means `build_clean_spine()` (default lumbar
L1–L5, labels 20–24; centroids stacked in ascending order along image axis 0).
"`run_qc` findings" means `run_qc(labelmap, bundled_default_config())[0].findings`.
"The leave-one-out offset of label L" means: fit the spline through the centroids
of every present label **except** L (`fit_centroid_spline`), then measure L's
centroid offset to that fit (`compute_spline_offsets`, `spacing_mm` = the map
spacing)._

### A. `displace` (§6 mode 1 — mislabel / misalignment, Detector A)

- [ ] **AC1: `displace` is registered under `"displace"`.** After
      `import segqc.synth`, `get_perturbation("displace")` returns
      `DisplacePerturbation`, `"displace"` is in `perturbation_names()`, and the
      class appears in `iter_perturbations()`.

- [ ] **AC2: `displace` moves the target off the neighbour-defined curve by ≥ the
      mislabel threshold.** For
      `DisplacePerturbation(target_label=22).apply(clean.seg_img, seed=0).labelmap`,
      the leave-one-out offset of label 22 is `>= 15.0` mm (the default
      `max_offset_mm`).

- [ ] **AC3: `displace` translates the body wholesale (bounds / fragmentation /
      border stay silent).** For the same perturbed map,
      `compute_components(labelmap, 22, cfg).component_count == 1`; label 22's
      voxel count equals the clean GT's `voxel_counts[22]`; and `run_qc` emits
      **no** `rule_id in {"bounds", "fragmentation", "border"}` finding (the body
      keeps its shape/volume and stays inset from every FOV face).

- [ ] **AC4: `displace` fires the misalignment finding via the reconstructed
      offsets.** Take `record = extract_feature_record(labelmap, cfg)` and replace
      the target entry's `offset_mm` in `record["stage3"]["per_label_offsets"]`
      with the leave-one-out offset of label 22; then
      `MislabelRule().evaluate(record, bundled_default_config())` returns a
      `Finding` with `rule_id == "mislabel"` whose `reason` starts with
      `"Vertebra misaligned from spinal curve:"` and
      `labels == frozenset({22})`.

- [ ] **AC5: plain `run_qc` does NOT surface the displacement (documented
      limitation).** `run_qc` on the displaced map emits **no**
      `rule_id == "mislabel"` finding — the interpolating spline (`s=0`) is refit
      through all present centroids, so every `stage3.per_label_offsets[*].offset_mm`
      is ≈ 0 and the displaced centroid sits on the refitted curve. (Locks the
      limitation for items 040/041; see Assumptions.)

- [ ] **AC6: `displace`'s `Expectation` is well-formed.** The result's
      `expectation` has `failure_mode == 1`,
      `failure_mode_name == FAILURE_MODE_NAMES[1]`,
      `expected_rule_ids == frozenset({"mislabel"})`,
      `expected_labels == frozenset({22})`, and
      `expected_verdict == "flagged-for-review"`.

### B. `relabel_swap` (§6 mode 4 — mislabel / ordering, Detector B)

- [ ] **AC7: `relabel_swap` is registered under `"relabel_swap"`.** After
      `import segqc.synth`, `get_perturbation("relabel_swap")` returns
      `RelabelSwapPerturbation`, and `"relabel_swap"` is in `perturbation_names()`.

- [ ] **AC8: `relabel_swap` exchanges two adjacent bodies' identities, preserving
      the label set.** For
      `RelabelSwapPerturbation(target_label=21, neighbour_label=22).apply(clean.seg_img, seed=0).labelmap`,
      the set of present non-zero labels equals the clean GT's `{20, 21, 22, 23,
      24}`; label 21's centroid axis-0 (voxel) position equals the clean GT's
      label-22 centroid position and vice-versa (identities swapped); and each
      label's voxel count is preserved.

- [ ] **AC9: the swap makes the by-label centroid order non-monotonic on the true
      spatial curve.** Fit the spline through the perturbed map's centroids ordered
      by **axis-0 spatial position**, then
      `compute_monotonic_consistency(<centroids in ascending-label order>, fit)`
      returns a non-empty `non_monotonic_pairs` that includes the `("L2", "L3")`
      pair (labels 21 and 22).

- [ ] **AC10: `relabel_swap` fires the ordering-inconsistency finding via the
      reconstructed monotonic record.** Take `record =
      extract_feature_record(labelmap, cfg)`, replace
      `record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"]` with the
      reconstructed pairs from AC9 (and set `is_monotonic` to `False`); then
      `MislabelRule().evaluate(record, bundled_default_config())` returns a
      `Finding` with `rule_id == "mislabel"` whose `reason` starts with
      `"Vertebra ordering inconsistent with label:"` and
      `labels == frozenset({21, 22})`.

- [ ] **AC11: plain `run_qc` does NOT surface the swap (documented limitation).**
      `run_qc` on the swapped map emits **no** finding at all (empty `findings`,
      verdict `pass`) — the present-label set and the ascending-label level-name
      order are unchanged, and the interpolating spline refit through the
      ascending-label centroids yields a monotonic `u`, so
      `monotonic_consistency.non_monotonic_pairs` is empty. (Locks the limitation
      for items 040/041; see Assumptions.)

- [ ] **AC12: `relabel_swap`'s `Expectation` is well-formed.** The result's
      `expectation` has `failure_mode == 4`,
      `failure_mode_name == FAILURE_MODE_NAMES[4]`,
      `expected_rule_ids == frozenset({"mislabel"})`,
      `expected_labels == frozenset({21, 22})`, and
      `expected_verdict == "flagged-for-review"`.

- [ ] **AC13: `relabel_swap` rejects a too-small or non-adjacent input.** Applying
      `RelabelSwapPerturbation()` to a single-label map
      (`build_clean_spine(levels=["L3"]).seg_img`) raises `SegQCInputError`; and
      `RelabelSwapPerturbation(target_label=20, neighbour_label=23)` (labels 20 and
      23 are not consecutive in the sorted present-label order) raises
      `SegQCInputError`.

### C. `sequence_break` (§6 mode 7 — sequence-continuity)

- [ ] **AC14: `sequence_break` is registered under `"sequence_break"`.** After
      `import segqc.synth`, `get_perturbation("sequence_break")` returns
      `SequenceBreakPerturbation`, and `"sequence_break"` is in
      `perturbation_names()`.

- [ ] **AC15: `sequence_break` relabels the tail vertebra to the transitional
      label.** For `SequenceBreakPerturbation().apply(clean.seg_img, seed=0).labelmap`
      (default: tail L5 = 24 → T13 = 28), label 24 is **absent** from the map's
      non-zero labels, label 28 is present with the clean GT's label-24 voxel
      count, and every other clean label (20, 21, 22, 23) is unchanged.

- [ ] **AC16: `sequence_break` fires the continuity finding via `run_qc`.** `run_qc`
      on the perturbed map emits a `Finding` with `rule_id == "sequence"` whose
      `reason` starts with `"Non-continuous label sequence:"` and names `"T13"`,
      and `labels == frozenset({28})`.

- [ ] **AC17: `sequence_break`'s only fired rule is `sequence` (no spurious
      coverage/other flag).** In `run_qc`'s findings for the perturbed map, every
      finding has `rule_id == "sequence"` — in particular **no**
      `rule_id == "coverage"` finding (the surviving span `T13, L1, L2, L3, L4` is
      canonically contiguous, so `relationships.missing_levels` is empty).

- [ ] **AC18: `sequence_break`'s `Expectation` is well-formed and truthful.** The
      result's `expectation` has `failure_mode == 7`,
      `failure_mode_name == FAILURE_MODE_NAMES[7]`,
      `expected_rule_ids == frozenset({"sequence"})`,
      `expected_labels == frozenset({28})`, and
      `expected_verdict == "flagged-for-review"`; and the pipeline agrees —
      `run_qc(...).verdict.overall.label == "flagged-for-review"`.

- [ ] **AC19: `sequence_break` rejects a degenerate input.** Applying
      `SequenceBreakPerturbation()` to a single-label map
      (`build_clean_spine(levels=["L3"]).seg_img`, which has no ordering to break)
      raises `SegQCInputError`; and
      `SequenceBreakPerturbation(target_label=24, new_label=22)` (a `new_label`
      already present in the map) raises `SegQCInputError`.

### D. Cross-cutting: geometry, determinism, immutability, seeding, spacing

- [ ] **AC20: every operator preserves dtype and geometry.** For each of the three
      operators (with an explicit target — and, for `relabel_swap`, an explicit
      neighbour), the output `labelmap` has the same array `dtype`, an affine that
      is `np.array_equal` to the input's, the same `shape`, and
      `header.get_zooms()[:3]` equal to the input's spacing.

- [ ] **AC21: every operator is reproducible (same seed + input ⇒ identical
      array).** For each of the three operators, two `apply(clean.seg_img, seed=7)`
      calls (same explicit target/neighbour) return output arrays that are
      `np.array_equal`.

- [ ] **AC22: every operator is non-mutating.** For each of the three operators,
      the data array of the `seg_img` passed to `apply` is unchanged (equal to a
      pre-call copy) after the call returns.

- [ ] **AC23: an unspecified target is chosen deterministically from the seed, and
      the `Expectation` names the entity actually perturbed.** For `displace` and
      `relabel_swap` with no explicit target, two `apply(clean.seg_img, seed=3)`
      calls select the **same** target (identical output arrays), and the
      operator's designated rule fires (via the reconstructed record of AC4 / AC10)
      for exactly the label(s) recorded in `result.expectation.expected_labels`
      (self-consistency, whichever the seed picked).

- [ ] **AC24: every operator is spacing-aware.** Applying each operator (with an
      explicit target/neighbour) to an anisotropic clean GT
      (`build_clean_spine(spacing=(1.0, 1.0, 3.0))`) still drives its designated
      rule — `displace` → a leave-one-out offset `>= 15.0` mm; `relabel_swap` → a
      non-empty reconstructed `non_monotonic_pairs`; `sequence_break` → a
      `rule_id == "sequence"` finding via `run_qc` — and preserves the input
      spacing (`get_zooms()[:3] == (1.0, 1.0, 3.0)`).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **`displace` and `relabel_swap` cannot be surfaced by plain `run_qc`; their
  rule-firing is asserted via reconstructed feature records fed to `MislabelRule`
  directly. This is the most material clarify=`assume` decision — the validator
  should surface it at the queue boundary.** The real pipeline
  (`segqc.pipeline.extract_feature_record`, item 035) computes the Stage 3
  spline features from an **interpolating** spline
  (`fit_centroid_spline` → `scipy...splprep(..., s=0)`, item 017) refit through
  **all present centroids in ascending-integer-label order**. Two consequences,
  both verified empirically against the real pipeline during spec authoring:
  (a) every `compute_spline_offsets` offset is ≈ 0 because each centroid lies
  *exactly* on the refitted curve — so a single displaced vertebra has offset ≈ 0
  and `MislabelRule` Detector A never fires via `run_qc`; and (b) the spline
  parameter `u` increases monotonically in the (label-sorted) input order by
  construction — so `compute_monotonic_consistency.non_monotonic_pairs` is always
  empty and `MislabelRule` Detector B never fires via `run_qc` on a reordering.
  This is the *same class* of structural limitation item 038 documented for
  `force_overlap` (which a single-integer label map likewise cannot surface
  through the one-hot `run_qc` path), and it is handled the *same way*:
  - `displace` is asserted by reconstructing `per_label_offsets` with the target's
    **leave-one-out** offset (its centroid measured against the spline fit through
    the *remaining* vertebrae — a genuine, large perpendicular offset) and feeding
    the record to `MislabelRule` (AC4). AC5 locks that `run_qc` does not surface it.
  - `relabel_swap` is asserted by reconstructing `monotonic_consistency` from the
    spline fit through the centroids in **true spatial (axis-0) order** evaluated
    against the ascending-label centroids (exposing the reversal) and feeding the
    record to `MislabelRule` (AC10). AC11 locks that `run_qc` does not surface it.
  Items 040 (corpus) and 041 (regression suite) must therefore represent the
  §6-mode-1 and §6-mode-4 cases via the reconstructed-record path (or a future
  robust-spline / mislabel-rule enhancement), **not** by expecting `segqc run`
  end-to-end to catch them. This is a Stage-5-level design fact surfaced now for
  audit, not a defect introduced by this item.

- **`sequence_break` fires the real `sequence` rule via `run_qc` by exploiting the
  default convention's value/rank divergence.** `SequenceRule` (item 030) fires on
  `relationships.out_of_order_labels`, computed from the level-name sequence in
  **ascending-integer-label order** vs `CANONICAL_ORDER` rank (item 014). Because
  the pipeline always sorts by integer label, a mere *swap* of two lumbar labels
  leaves the value-sorted name sequence monotonic (L1..L5) and does **not** fire
  `sequence` — this is why `relabel_swap` (a swap) targets `mislabel`, not
  `sequence`. To fire `sequence` through `run_qc` the value order must contradict
  the canonical rank order, which requires a **transitional** label whose integer
  value and canonical rank diverge: the default convention assigns **T13 = 28**
  (rank 19, below L1) and **L6 = 29** (rank 25). Relabelling the **tail** of the
  default lumbar span (L5 = 24) to **T13 = 28** makes 28 sort last by value yet
  rank first, yielding `out_of_order_labels == ["T13"]` while the surviving span
  `T13, L1, L2, L3, L4` stays canonically contiguous (no missing level → no
  coverage co-fire). The queue's illustrative "L1 → T12 → L2 → L5" reordering
  does **not** fire the rule under the value-sorting pipeline (`19, 20, 21, 24` is
  rank-monotonic); the transitional-label mechanism is the faithful realisation.
  The default target is therefore the **tail**, and the default `new_label` is
  **28 (T13)**. A non-tail target (or a thoracic/cervical span, where T13 sits
  *above* the span) still fires `sequence` but may **co-fire** a case-level
  `coverage` finding (a missing level) — documented, and analogous to item 037's
  `fuse` coverage co-fire; the committed ACs use the clean default (tail lumbar).

- **`relabel_swap` swaps two *adjacent* bodies (single inversion), so the
  offending labels are exactly the swapped pair.** Adjacency is defined as
  consecutive position in the sorted present-label list (matching item 037's
  `fuse` and item 038's `force_overlap`). Swapping the adjacent bodies at labels
  L (target) and L' (neighbour) produces a single non-monotonic pair whose level
  names resolve back to `{target, neighbour}`, so `expected_labels ==
  frozenset({target, neighbour})`. A non-adjacent swap drags an intervening level
  into the offender set; the operator rejects an explicit non-adjacent pair
  (AC13). The swap keeps the present-label **set** intact, so — unlike
  `sequence_break` — it provokes **no** coverage side-effect.

- **`displace` translates the whole target body diagonally in-plane so the offset
  clears the 15 mm threshold without touching the FOV border.** The clean GT
  (item 036) insets every body by a 15 mm margin; a pure single-axis in-plane
  translation large enough to reach a 15 mm offset would push the body flush to a
  face (tripping `border`), and the arc lies on axis 1 (so an axis-1 shift partly
  follows the curve, shrinking the perpendicular offset). Translating the body
  diagonally toward the higher-index axis-1 **and** axis-2 faces — by
  `displacement_mm` split across the two axes, staying ≥ 1 voxel inset from every
  face — yields a perpendicular (leave-one-out) offset comfortably above 15 mm
  with no border contact (verified: default lumbar isotropic ≈ 18.9 mm, anisotropic
  `(1,1,3)` ≈ 16.4 mm, both with zero `run_qc` findings). The body is translated
  wholesale (unchanged volume, still one component, still inside `bounds`), so
  only `mislabel` is the intended rule. The default `displacement_mm = 18.0`; the
  operator raises `SegQCInputError` if the requested displacement cannot fit
  inside the FOV margins for the target.

- **`displace` and `relabel_swap` do not assert `run_qc`'s verdict against their
  `Expectation`.** Since `run_qc` cannot surface these two modes (above), their
  `Expectation` records the *conceptual* outcome (`expected_rule_ids ==
  {"mislabel"}`, `expected_verdict == "flagged-for-review"`) that the reconstructed
  `MislabelRule` assertion demonstrates, exactly as item 038's `force_overlap`
  `Expectation` did — the ACs assert the rule fires on the reconstructed record and
  that `run_qc` stays silent, rather than asserting `run_qc(...).verdict` equals
  `expected_verdict`. `sequence_break`, which *does* fire via `run_qc`, asserts the
  pipeline verdict directly (AC18).

- **Operators are parameterised classes; `apply` takes only `(labelmap, seed)`
  (per the item-036 contract).** Target/pair selection, displacement magnitude,
  and replacement label are **constructor** arguments; the registry stores the
  class. When a target/pair is left `None`, it is chosen deterministically from the
  present labels via `seeded_rng(seed)` (matching items 037/038), and the choice is
  recorded in the returned `Expectation` (AC23). `sequence_break`'s default target
  is the deterministic tail (max label); `seed` is accepted for interface
  compliance but does not vary that choice (mirroring item 038's `remove_level`).

- **The returned `Expectation` reflects the entity *actually* perturbed.** So a
  test asserts the fired result against `result.expectation` (self-consistent),
  robust to which label/pair a `None` target + seed selects. Tests that need a
  fixed offender pass an explicit `target_label` (and `neighbour_label` for
  `relabel_swap`).

- **Single new module `src/segqc/synth/identity_ordering_alignment.py`, plus one
  additive `__init__` import.** The three classes live in one file to minimise the
  shared-file surface. `synth/__init__.py` gains **one** import line (plus the
  three class names in its `__all__`) so the operators self-register on
  `import segqc.synth`, mirroring `IdentityPerturbation` and items 037/038. This is
  additive and at a distinct line region from what 037/038 (already merged) touch,
  so git merges the sibling registrations cleanly. `synth/perturbation.py`,
  `synth/clean_gt.py`, `synth/component_shape.py`, and
  `synth/coverage_border_overlap.py` are **not** edited; the shared-helper idioms
  (`_present_labels`, `_choose_label`, `_choose_adjacent_pair`, a copy-into-fresh-
  image builder, a label-bbox helper) are reimplemented locally to keep the file
  independent and merge-safe.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `MislabelRule` with `rule_id == "mislabel"`, reason tags
  `"Vertebra misaligned from spinal curve:"` (Detector A, fires on
  `stage3.per_label_offsets[*].offset_mm >= max_offset_mm`, default `15.0`,
  label-attributed) and `"Vertebra ordering inconsistent with label:"` (Detector
  B, fires per `stage3.monotonic_consistency.non_monotonic_pairs`, resolving level
  names to labels via `per_label`); `SequenceRule` with `rule_id == "sequence"`,
  reason tag `"Non-continuous label sequence:"`, label-attributed findings driven
  off `relationships.out_of_order_labels`; `fit_centroid_spline(centroids)` /
  `compute_spline_offsets(centroids, fit, spacing_mm=...)` (`.offset_mm`) /
  `compute_monotonic_consistency(centroids, fit)` (`.non_monotonic_pairs`);
  `compute_centroid(seg_img, label)` (`.centroid_voxel`, `.level_name`);
  `extract_feature_record(seg_img, config) -> dict` with `record["stage3"]
  ["per_label_offsets"]` (list of dicts with `label`/`level_name`/`offset_mm`) and
  `record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"]`;
  `run_qc(seg_img, config) -> (CaseResult, dict)` with
  `CaseResult.findings: tuple[Finding, ...]` and `CaseResult.verdict.overall.label`;
  `Finding.labels: frozenset[int]`; `segqc.labels` default convention with
  `T13 == 28` (rank 19) / `L6 == 29` and `CANONICAL_ORDER`;
  `segqc.config.bundled_default_config`; `segqc.io.SegQCInputError`.

## Implementation Steps

Intended code path: new file `src/segqc/synth/identity_ordering_alignment.py` +
one additive import in `src/segqc/synth/__init__.py`. No edits to existing
production modules.

1. **Create `src/segqc/synth/identity_ordering_alignment.py`** importing from the
   item-036 framework (`Perturbation`, `Expectation`, `PerturbationResult`,
   `register_perturbation`, `seeded_rng`, `FAILURE_MODE_NAMES`), `numpy`,
   `nibabel`, and `segqc.io.SegQCInputError`. Reuse the item-037/038 private-helper
   idioms — implemented **locally** here (do **not** import from the sibling
   operator modules): `_present_labels`, `_choose_label`, `_choose_adjacent_pair`,
   a copy-into-fresh-image builder (`_new_image`), a `_label_bbox` helper, and a
   `_require_present` guard.

2. **`DisplacePerturbation`** (`name = "displace"`,
   `__init__(*, target_label=None, displacement_mm=18.0)`): resolve/choose the
   target (raise `SegQCInputError` if an explicit target is absent). Copy the
   array; compute the target's bbox and the axis-1 / axis-2 room to the higher-
   index faces; translate the whole target body diagonally toward those faces by a
   per-axis voxel amount (derived from `displacement_mm` and spacing) that keeps
   the body ≥ 1 voxel inset from every face — raising `SegQCInputError` if the
   requested displacement cannot fit. Build
   `Expectation(failure_mode=1, failure_mode_name=FAILURE_MODE_NAMES[1],
   expected_rule_ids=frozenset({"mislabel"}), expected_labels=frozenset({target}),
   expected_verdict="flagged-for-review", detail=...)`; return `PerturbationResult`.

3. **`RelabelSwapPerturbation`** (`name = "relabel_swap"`,
   `__init__(*, target_label=None, neighbour_label=None)`): read present labels
   (raise if `< 2`); resolve an **adjacent** (consecutive-in-sorted-order)
   `(target, neighbour)` pair — an explicit pair validated for presence and
   adjacency, else chosen via `seeded_rng(seed)`. Copy the array and swap the two
   labels' voxels (`data[data == target], data[data == neighbour]` exchanged via a
   temporary sentinel to avoid clobbering). Build
   `Expectation(failure_mode=4, failure_mode_name=FAILURE_MODE_NAMES[4],
   expected_rule_ids=frozenset({"mislabel"}),
   expected_labels=frozenset({target, neighbour}),
   expected_verdict="flagged-for-review", detail=...)`; return `PerturbationResult`.

4. **`SequenceBreakPerturbation`** (`name = "sequence_break"`,
   `__init__(*, target_label=None, new_label=28)`): read present labels (raise if
   `< 2` — no ordering to break); resolve the target — an explicit target must be
   present; an unspecified target defaults to the **tail** (max present label).
   Validate `new_label` is absent from the map (raise `SegQCInputError` otherwise).
   Copy the array and relabel every target voxel to `new_label`. Build
   `Expectation(failure_mode=7, failure_mode_name=FAILURE_MODE_NAMES[7],
   expected_rule_ids=frozenset({"sequence"}), expected_labels=frozenset({new_label}),
   expected_verdict="flagged-for-review", detail=...)`; return `PerturbationResult`.

5. **Determinism & seeding.** Any stochastic choice (unspecified target/pair) derives
   solely from `seeded_rng(seed)`; the same seed + input yields a byte-identical
   output array. Deterministic-once-resolved operators still accept and thread
   `seed`. Never mutate the caller's array; always return a fresh `Nifti1Image` with
   the input's affine and dtype.

6. **Register + wire.** Decorate each class with `@register_perturbation`, and add
   the single additive import line to `src/segqc/synth/__init__.py` (plus the three
   class names to its `__all__`) so `import segqc.synth` self-registers all three,
   mirroring `IdentityPerturbation` and items 037/038.

7. **Do not** edit `synth/perturbation.py`, `synth/clean_gt.py`,
   `synth/component_shape.py`, `synth/coverage_border_overlap.py`, or any
   `heuristics` / `features` / `config` module.

## Testing Strategy

- **Framework:** `pytest`. New module
  `tests/test_039_identity_ordering_alignment_perturbations.py`, in the same style
  as `tests/test_038_coverage_border_overlap_perturbations.py` (build a clean-GT
  fixture, apply the operator, run `run_qc(perturbed, bundled_default_config())`,
  assert on `case_result.findings` / `verdict`, and cross-check the raw Stage 3
  features via `fit_centroid_spline` / `compute_spline_offsets` /
  `compute_monotonic_consistency` / `compute_centroid`).
- **No registry snapshot needed** — the three operators are real, permanent
  registrations (like `identity` and items 037/038's operators); tests import them
  from `segqc.synth`.
- **Helpers:** a `_clean()` fixture (`build_clean_spine()`); a `_findings(labelmap)`
  helper returning `run_qc(labelmap, bundled_default_config())[0].findings`; a
  `_rule_ids(findings)` helper; a `_loo_offset(labelmap, label)` helper (fit the
  spline through the other present labels' centroids, return `label`'s offset to
  it); and a `_reconstruct_mono_pairs(labelmap)` helper (spline through
  spatial-order centroids, `compute_monotonic_consistency` of the ascending-label
  centroids).
- **`displace` (AC1–AC6):** registration (AC1); `_loo_offset >= 15.0` (AC2);
  single component + preserved voxel count + no `bounds`/`fragmentation`/`border`
  finding (AC3); reconstructed-offset record → `MislabelRule` misalign finding on
  `{22}` (AC4); no `mislabel` finding via `run_qc` (AC5); `Expectation` fields (AC6).
- **`relabel_swap` (AC7–AC13):** registration (AC7); label-set preserved +
  centroids swapped + counts preserved (AC8); reconstructed `non_monotonic_pairs`
  includes `("L2","L3")` (AC9); reconstructed-mono record → `MislabelRule` ordering
  finding on `{21,22}` (AC10); empty `run_qc` findings / `pass` (AC11);
  `Expectation` fields (AC12); `SegQCInputError` on a single-label map and on a
  non-adjacent explicit pair (AC13).
- **`sequence_break` (AC14–AC19):** registration (AC14); tail 24 absent + 28 present
  with the right count + others unchanged (AC15); `"Non-continuous label sequence:"`
  finding naming `"T13"` on `{28}` (AC16); only-`sequence` / no `coverage` (AC17);
  `Expectation` fields + pipeline verdict (AC18); `SegQCInputError` on a single-label
  map and on a `new_label` already present (AC19).
- **Cross-cutting (AC20–AC24):** parametrise across the three operator instances —
  dtype/affine/shape/zooms preservation (AC20); two same-seed applies →
  `np.array_equal` (AC21); pre-call array copy unchanged after apply (AC22);
  unspecified-target same-seed determinism + designated rule fires for the recorded
  offender, for `displace`/`relabel_swap` (AC23); anisotropic `spacing=(1.0,1.0,3.0)`
  still drives each designated rule and preserves spacing (AC24).
- **Adversarial / edge cases:**
  - `displace` / `sequence_break` with an **explicit** target not present raise
    `SegQCInputError` (do not silently no-op).
  - `displace` with a `displacement_mm` too large to fit the FOV margins raises
    `SegQCInputError` (does not silently clip the body and shrink it into a
    `bounds`/`border` violation).
  - `relabel_swap` swapping a **different** adjacent pair (e.g. 23↔24) still fires
    the ordering finding on exactly that pair via the reconstruction.
  - Two **different** seeds with an unspecified target may pick different offenders,
    but each result stays self-consistent (the designated rule fires for
    `result.expectation`'s recorded offender).
  - `sequence_break` with an explicit **interior** target (e.g. `target_label=22`)
    still fires `sequence` but is expected to co-fire a case-level `coverage`
    finding (documented) — a direct check that the divergence is understood.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 036** — the synthetic-corpus foundation this item builds on directly:
    `segqc.synth.clean_gt.build_clean_spine` / `CleanSpine` (every perturbation
    starts from its output) and the `segqc.synth.perturbation` framework
    (`Perturbation` ABC, `Expectation`, `PerturbationResult`,
    `register_perturbation` / `get_perturbation` / `iter_perturbations` /
    `perturbation_names`, `seeded_rng`, `FAILURE_MODE_NAMES`). Implemented against
    this **exact** interface, unchanged.
  - **Item 033** — `segqc.heuristics.mislabel.MislabelRule` (`rule_id ==
    "mislabel"`; Detector A tag `"Vertebra misaligned from spinal curve:"`,
    `max_offset_mm` default `15.0`; Detector B tag
    `"Vertebra ordering inconsistent with label:"` off
    `monotonic_consistency.non_monotonic_pairs`): the rule `displace` and
    `relabel_swap` drive (via reconstructed records).
  - **Item 030** — `segqc.heuristics.sequence.SequenceRule` (`rule_id ==
    "sequence"`, reason tag `"Non-continuous label sequence:"`, label-attributed
    findings off `relationships.out_of_order_labels`): the rule `sequence_break`
    drives (via `run_qc`). Note: `SequenceRule` is **label-attributed** (its
    findings carry real integer labels), in contrast to item 029's case-level
    `CoverageRule`.
  - **Item 017 / 018 / 020** — `segqc.features.spline.fit_centroid_spline`,
    `segqc.features.spline_offset.compute_spline_offsets`,
    `segqc.features.consistency.compute_monotonic_consistency`: the spline / offset
    / monotonic extractors the reconstructions call directly, and whose `s=0`
    interpolation is the reason `run_qc` cannot surface modes 1 and 4.
  - **Item 014** — `segqc.features.relationships.compute_spine_relationships`
    (`out_of_order_labels`, `missing_levels`): the relationships `sequence_break`'s
    detection reads.
  - **Item 013** — `segqc.features.centroids.compute_centroid` (`centroid_voxel`,
    `level_name`): the centroids the reconstructions and swap-position checks read.
  - **Item 035** — `segqc.pipeline.run_qc` / `extract_feature_record` +
    `segqc.config.bundled_default_config`: the full-pipeline entry point and record
    shape the operators run through / reconstruct from.
  - **Item 034** — `segqc.aggregate` (`CaseResult`, `verdict.overall.label`): the
    verdict shape the `sequence_break` expectation is checked against.
  - **Item 026** — `segqc.heuristics.finding.Finding` (`rule_id`, `reason`,
    `labels`): the finding shape the assertions read.
  - **Item 004** — `segqc.labels` (default convention: L1–L5 = 20–24, **T13 = 28**
    at canonical rank 19, `CANONICAL_ORDER`): the value/rank divergence
    `sequence_break` exploits, resolved via `build_clean_spine`.
  - **Item 003** — `segqc.io.SegQCInputError`: the error type for absent-target /
    too-few-labels / non-adjacent-pair / label-already-present /
    displacement-too-large guards.
- **Structural precedent (not a functional dependency):**
  - **Item 038** — `segqc.synth.coverage_border_overlap` established the exact
    pattern this item follows for its two non-`run_qc`-surfaceable operators: an
    operator produces a real single-integer label map, and its designated rule is
    asserted via a **reconstructed** feature record fed to the rule directly (item
    038's `force_overlap` → `detect_overlaps` + `OverlapRule`; here `displace`
    /`relabel_swap` → reconstructed offsets / monotonic record + `MislabelRule`),
    with an AC locking that plain `run_qc` does not surface it.
  - **Item 037** — `segqc.synth.component_shape` established the module structure
    (single additive file, constructor-parameterised operators over the shared
    item-036 framework, adjacency-as-list-position for pair selection). This item
    imports **nothing** from items 037/038 and does not edit their files; they are
    named only as the pattern to mirror and to make explicit that the
    `__init__.py` registration line stays additive and merge-safe.
- **Not dependencies (parallel siblings, both merged):** items **037** and **038**
  build the other operator families against the same item-036 interface; this item
  is independent of them and its changes stay additive.

## Decisions & Trade-offs

To be updated during implementation.
