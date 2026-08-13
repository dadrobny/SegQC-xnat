# Item 116 — Make the synthetic corpus RAS-native

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 116
> **Objectives:** G2, G7
> **Suggested branch:** `aide/116-ras-native-synthetic-corpus`

---

## Description

Migrate `src/segfacet/synth/` from the repo's legacy **array-axis convention** to
the **affine as the single source of orientation truth**, so the synthetic corpus
and the (item 108) affine-derived face mapping describe the same anatomy.

`synth/clean_gt.py`'s module docstring states its convention explicitly — *"Axis
convention (matching `segfacet.features.geometry`): image axis 0 is
superior-inferior (the stacking axis), axis 1 is left-right, axis 2 is
anterior-posterior. Bodies are stacked along axis 0."* That contract was correct
while `geometry.py` hardcoded the same mapping. It is not a stray comment: the
whole `synth/` package, and the tests built on it, encode it. Meanwhile
`_affine_from_spacing` emits a plain positive diagonal affine, which resolves to
RAS axcodes in which **axis 0 is left-right** — so the fixtures' affines have
always contradicted their own arrays. Nothing noticed, because every consumer
read the array convention and no consumer read the affine.

Item 108 makes `geometry.py` read the affine. That is correct for real data and
is not in question here — but it leaves `synth/` implementing the opposite
contract, which is why 14 tests across six pre-existing modules fail on item
108's branch: `CropAtBorderPerturbation` selects its crop axis by array
convention, so "crop toward anterior" no longer sets `touches_anterior`; three
Stage-7/14 acceptance tests lose `crop_at_border` sensitivity entirely; and two
golden-verdict snapshots still embed the old reason text.

This item completes that migration. **The end state:** bodies stack along **axis
2**, the plain diagonal affine becomes truthful (axis 2 = S), no reorientation
happens on load, and a spine in the synthetic corpus runs head-to-foot exactly as
it does in real RAS data.

**In scope.** `synth/`'s stacking axis and every operator that picks an axis by
anatomical intent; regenerating the corpus fixtures and goldens; updating the
tests that assert the legacy convention; the `clean_gt.py` docstring contract.

**Not in scope.** `features/geometry.py`'s mapping (item 108 owns it, and this
branch is stacked on top of that work). Any rule threshold. Any change to which
§6 mode a case targets, or to a case's intended severity — a case that was
designed to trip `border` must still trip `border`.

## Acceptance Criteria

- [ ] **AC1: bodies stack along the superior-inferior axis.** `build_clean_spine`
  stacks vertebral bodies along array axis 2, and the emitted affine resolves to
  axcodes in which axis 2 carries S/I.
- [ ] **AC2: the affine tells the truth.** For every fixture the generator emits,
  the anatomical axis derived from the affine matches the axis the array actually
  varies along — asserted directly, not by inspection.
- [ ] **AC3: no reorientation on load.** Loading a generated fixture through
  `segfacet.io` is an array-identity operation (the RAS reorientation is a
  no-op), so in-memory and loaded views agree.
- [ ] **AC4: the docstring states the new contract.** `clean_gt.py`'s axis
  convention paragraph describes the affine as the source of truth and no longer
  claims axis 0 is superior-inferior.
- [ ] **AC5: operators select axes by anatomical intent.**
  `CropAtBorderPerturbation` and every sibling operator that targets a named face
  resolve the axis through the affine, not through a hardcoded index.
- [ ] **AC6: crop-at-border names the face it cropped.** Cropping toward a named
  anatomical face sets that face's `touches_*` flag — for all six faces.
- [ ] **AC7: every §6 mode still fires its designated rule.** Each corpus case
  trips the same `rule_id` on the same offending labels as before the migration;
  no case's designated finding disappears.
- [ ] **AC8: mode-6 sensitivity is restored.** The `crop_at_border` cases in the
  Stage-7 and Stage-14 acceptance suites report the sensitivity they did before
  item 108's branch, not 0.0.
- [ ] **AC9: the degenerate-spacing path does not raise.** A `(0.0, 1.0, 1.0)`
  spacing through the eval harness produces the documented zeroed physical volume
  rather than propagating a `ValueError` from affine resolution.
- [ ] **AC10: fixtures and goldens are regenerated together.** Every committed
  corpus fixture and golden is regenerated from the migrated generator, and
  regenerating twice is byte-identical.
- [ ] **AC11: the manifest still round-trips.** `tests/corpus/manifest.json`
  regenerates byte-identically and still describes every case.
- [ ] **AC12: the whole suite is green**, including the 14 tests failing on item
  108's branch and the two golden-verdict snapshots in
  `test_098_stray_components.py` / `test_102_stage18_validation.py`.
- [ ] **AC13: item 108's acceptance still holds.** `tests/test_108_affine_faces.py`
  passes unchanged — this migration must satisfy it, not weaken it.

## Assumptions

- **Stacked on item 108's branch, by the maintainer's decision (2026-08-12)** to
  split the migration into its own item without creating a broken intermediate.
  Migrating fixtures *under* the pre-108 hardcoded mapping would break the same
  tests in mirror image and would name cranio-caudal faces "anterior" for one
  item's duration, churning the same tests twice. Item 116 therefore branches
  from `aide/108-ras-correct-touches-face-mapping`, and the two merge into
  `aide/queue-016` together as two reviewable items.
- **Stacking along axis 2 rather than re-labelling the affine.** The alternative
  — keep arrays on axis 0 and emit an affine saying axis 0 is S — is rejected:
  `segfacet.io` would then permute every array on load, so the in-memory fixture
  and the loaded fixture would disagree, and every voxel-space feature would
  shift. Axis 2 is the RAS-native choice and makes load a no-op.
- **Test updates express anatomical intent, not face names**, wherever the
  assertion allows it, so a future orientation change does not churn them again.
- **Case identity is preserved.** Regenerating fixtures changes voxel geometry,
  so numeric feature values in the goldens will move. What must NOT move is which
  rule fires on which labels for which case (AC7).
- **`eval/harness.py` may need a guard** for the degenerate-spacing case (AC9).
  That file is authorised here only for that guard.

## Implementation Steps

1. Read `clean_gt.py` end to end and inventory every axis-0 assumption: stacking,
   per-body size ordering, the inter-body gap, the lateral-offset curve, and the
   scan-texture ramp.
2. Move the stacking axis to 2 and reorder the per-axis size/gap constants to
   match, keeping physical (mm) body dimensions unchanged so cases stay
   comparable.
3. Update the module docstring's axis-convention paragraph (AC4).
4. Rework `CropAtBorderPerturbation` and any sibling operator that names a face
   so the axis is resolved from the affine (AC5). Share one helper rather than
   repeating the resolution per operator.
5. Add the `eval/harness.py` guard for degenerate spacing (AC9).
6. Regenerate fixtures, manifest and goldens; verify twice-regeneration is
   byte-identical.
7. Update the failing tests to the new convention, preferring intent-based
   assertions.
8. Run the full suite and confirm green, including `tests/test_108_affine_faces.py`.

## Testing Strategy

New module `tests/test_116_ras_native_corpus.py` for the migration's own
invariants, plus updates to the tests that encode the legacy convention
(`test_038_coverage_border_overlap_perturbations.py`,
`test_053_eval_harness.py`, `test_057_acceptance_stage7.py`,
`test_091_stage14_acceptance.py`, `test_098_stray_components.py`,
`test_102_stage18_validation.py`):

- AC1/AC2: assert the stacking axis and that the affine-derived S/I axis matches
  the axis along which body centroids actually vary.
- AC3: load a generated fixture and assert the array is unchanged by the load.
- AC5/AC6: one test per face — crop toward it, assert that face's flag.
- AC7: per corpus case, assert `(rule_id, labels)` matches the pre-migration
  expectation, sourced from the merge-base goldens rather than retyped.
- AC9: the zero-spacing harness case.
- AC10/AC11: regenerate twice, compare bytes, for fixtures, manifest and goldens.

Adversarial: a single-body spine; a spine with one level missing; anisotropic
spacing; a fixture whose affine is deliberately made untruthful (AC2 must fail
for it).

## Validation

Run `segfacet run` on a regenerated `mode6_crop_at_border` fixture and confirm the
`border` finding names a **cranio-caudal** face, and that the human report reads
as anatomically sensible end to end. Record the output. Confirm
`python scripts/check_item_scope.py docs/aide/items/116-ras-native-synthetic-corpus.md --base aide/108-ras-correct-touches-face-mapping`
exits 0.

## Dependencies

Item 108 — this branch is stacked on it and completes the convention migration it
began. Item 107 supplied the scope checker used above.

## Authorised paths

- `src/segfacet/synth/**`
- `src/segfacet/eval/harness.py`
- `tests/corpus/**`
- `tests/test_116_ras_native_corpus.py`
- `tests/test_038_coverage_border_overlap_perturbations.py`
- `tests/test_053_eval_harness.py`
- `tests/test_057_acceptance_stage7.py`
- `tests/test_091_stage14_acceptance.py`
- `tests/test_098_stray_components.py`
- `tests/test_102_stage18_validation.py`
- `docs/aide/queue/queue-016.md`
- `docs/aide/items/116-ras-native-synthetic-corpus.md`

## Decisions & Trade-offs

- **The legacy convention was documented, not accidental.** `clean_gt.py` names
  `segfacet.features.geometry` as the convention it matches. This item is
  therefore a convention migration, not a bug fix, and the fixtures' contradictory
  affines are the reason it went unnoticed for so long — nothing read them.

To be updated during implementation.
