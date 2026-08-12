# Item 108 — Affine-driven anatomical face mapping

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 108
> **Objectives:** G2
> **Suggested branch:** `aide/108-affine-driven-faces`

---

## Description

Make the six `touches_*` flags in `src/segfacet/features/geometry.py` name the
anatomical face they actually describe, by **deriving the axis→face mapping
from the volume's affine** rather than assuming a fixed axis order.

Today the extractor hardcodes `x == 0 → touches_inferior`,
`y == 0 → touches_left`, `z == 0 → touches_anterior`
(`geometry.py:251-256`). Its docstring defends this as "a pragmatic convention
for tools that work in any orientation without a reliable RAS header." That
premise stopped being true at item 094: `segfacet.io` now reorients every
loaded volume to `("R", "A", "S")` (`io.py:166`), so array axis 0 runs
left→right, axis 1 posterior→anterior and axis 2 inferior→superior. The header
*is* reliable and the layout *is* normalised, so every flag is systematically
mis-named and every `border` / `fov` finding on real data names the wrong face.

Deriving from the affine fixes both populations at once: volumes loaded through
`segfacet.io` (already RAS) and hand-built in-memory arrays from
`tests/synthetic.py` / `synth/clean_gt.py` (spine along axis 0, never
round-tripped). It removes the class of bug rather than re-pinning it to a
newer convention, and needs no fixture migration.

**In scope.** The mapping in `geometry.py`, its docstring, and an audit of the
two consuming rules (`heuristics/border.py`, `heuristics/fov.py`) for any
assumption that the inferior/superior pair is the spine's long axis.
Regenerating committed goldens whose `touches_*` values change.

**Not in scope.** Changing what `border` / `fov` *decide* — only which face
names they receive. No threshold moves. No change to the `touches_*` field
names themselves (the record schema keeps its six keys; only their assignment
becomes correct).

## Acceptance Criteria

- [ ] **AC1: the mapping is derived, not assumed.** `compute_geometry` (or its
  caller) determines which array axis carries which anatomical direction from
  the volume's affine, and no `touches_*` assignment references a hardcoded
  axis index.
- [ ] **AC2: RAS volumes are named correctly.** For a volume whose affine is
  RAS, `touches_superior` / `touches_inferior` are set from the axis carrying
  S/I, `touches_left` / `touches_right` from the L/R axis, and
  `touches_anterior` / `touches_posterior` from the A/P axis.
- [ ] **AC3: orientation-invariance.** The same anatomical volume stored in two
  different axis orders (e.g. RAS and PIL) yields **identical** `touches_*`
  flags after loading.
- [ ] **AC4: hand-built arrays are correct too.** A fixture built with the
  spine along array axis 0 and an affine that says so reports the cranio-caudal
  faces as `touches_superior` / `touches_inferior`, not as left/right.
- [ ] **AC5: the pre-fix mapping is pinned as wrong.** A regression test
  asserts the corrected flags for a case where old and new disagree, and is
  demonstrated to fail against the pre-fix implementation.
- [ ] **AC6: `border` findings name the right face.** A case cropped at a known
  anatomical face produces a `border` finding naming that face.
- [ ] **AC7: `fov` findings name the right face.** Same, through
  `heuristics/fov.py`'s coverage derivation.
- [ ] **AC8: rule decisions are unchanged where naming is unchanged.** On the
  committed corpus, every `border` / `fov` finding's *presence* and offending
  labels are identical to pre-fix; only face names in the payload may differ.
- [ ] **AC9: a degenerate affine is handled explicitly.** A volume whose affine
  is missing, singular, or non-axis-aligned produces a documented, deterministic
  outcome (documented fallback or a clear error) rather than a silent
  mis-assignment.
- [ ] **AC10: the docstring states the new contract.** `geometry.py`'s module
  docstring describes the affine-derived mapping and no longer claims an
  any-orientation convention.
- [ ] **AC11: goldens regenerate consistently.** Any committed golden whose
  `touches_*` values change is regenerated, and regenerating twice is
  byte-identical.

## Assumptions

- **Affine-derived, per the maintainer's decision (2026-08-12)**, rather than
  hard-coding RAS and migrating fixtures, or hard-coding RAS and documenting
  the fixtures as a known-wrong exception. Both alternatives leave a convention
  that a future non-RAS input can violate again.
- **`nibabel.aff2axcodes` (or TPTBox's equivalent) is available and is the
  mechanism** for turning an affine into an axis→direction triple. `segfacet.io`
  already depends on this layer.
- **The six field names stay.** Renaming them is a schema change and belongs to
  Stage 27, not here.
- **`LabelGeometry` may need the affine (or an axcode triple) threaded to it.**
  If `compute_geometry`'s current signature does not carry orientation, adding a
  parameter is authorised by this item; changing its *return* shape is not.
- **The corpus fixtures' affines are truthful.** If any committed fixture has an
  affine that does not describe how its array was built, that is a fixture
  defect this item surfaces and reports rather than silently compensates for.

## Implementation Steps

1. Read `geometry.py`'s current mapping and every caller of `compute_geometry`;
   determine where the affine is available and what must be threaded.
2. Add an orientation resolution helper: affine → `{axis_index: (negative_face,
   positive_face)}`, covering all six anatomical names.
3. Replace the six hardcoded assignments with lookups through that helper.
4. Handle the degenerate-affine case per AC9 and document the choice.
5. Audit `heuristics/border.py` and `heuristics/fov.py` for long-axis
   assumptions; fix any found, without changing thresholds or verdicts.
6. Update `geometry.py`'s module docstring (AC10).
7. Run the corpus; diff findings against pre-fix output; confirm only face
   names moved (AC8). Regenerate affected goldens.

## Testing Strategy

New module `tests/test_108_affine_faces.py`:

- AC1: assert no hardcoded axis constant remains in the assignment path.
- AC2/AC3: build one anatomical volume, store it under several axis orders,
  assert identical flags after loading.
- AC4: in-memory fixture, spine along axis 0 with a matching affine.
- AC5: the explicit before/after case, with a comment naming the pre-fix values.
- AC6/AC7: crop a fixture at a known face; assert the finding's named face.
- AC8: run the corpus and compare finding presence + offending labels against
  the committed goldens.
- AC9: missing / singular / oblique affines.
- AC11: regenerate twice, compare bytes.

Adversarial: single-voxel labels touching several faces; an anisotropic volume;
a volume where two axes have equal extent; a flipped (negative-determinant)
affine.

## Validation

Run `segfacet run` on a fixture deliberately cropped at the superior face and
inspect the human report: the `border` finding must say *superior*. Repeat with
the same volume stored in a non-RAS order and confirm the report is identical.
Record both outputs in Decisions.

## Dependencies

None blocking. Item 107 (if it lands first) removes the byte-hash fences this
item would otherwise have to re-pin; if 107 has not landed, re-pin the
`features/**`, `heuristics/**`, `src/segfacet/**` and corpus digests named in
[`../queue/queue-016.md`](../queue/queue-016.md).

## Authorised paths

- `src/segfacet/features/geometry.py`
- `src/segfacet/heuristics/border.py`
- `src/segfacet/heuristics/fov.py`
- `src/segfacet/pipeline.py`
- `src/segfacet/feature_report.py`
- `tests/test_108_affine_faces.py`
- `tests/corpus/golden/*.json`
- `docs/aide/items/108-affine-driven-face-mapping.md`

## Decisions & Trade-offs

- **Affine-derived over convention-pinned** (maintainer, 2026-08-12). The
  alternative — assume RAS everywhere and migrate the synthetic fixtures — was
  rejected because it fixes today's instance while leaving the same failure
  available to any future input path that does not pass through `segfacet.io`.

To be updated during implementation.
