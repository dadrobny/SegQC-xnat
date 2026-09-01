# Item 131 — Normalise `tangent_angles_deg[]` for traversal direction

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 131
> **Objectives:** G7
> **Suggested branch:** `aide/131-normalise-tangent-angles-deg-for`

---

## Description

Stage 29 deliverable **D7**. `SpineCurvature.tangent_angles_deg[]` is the
*unsigned* angle between each spline tangent and `+S`, taken from the raw
tangents with no traversal-direction normalisation. Item 122 added a direction
convention — negate every tangent once, per case, when the ordered centroids'
net advance in `+S` is negative — but applied it only to the signed per-plane
arrays it introduced, deliberately leaving the two retained unsigned arrays
alone (`features/orientation.py:474-475`, and item 122's Decisions log,
"Remaining record-level inconsistency, deliberately not fixed here"). The
record therefore carries **two** tangent-angle conventions side by side. This
item collapses them to one.

### The defect, measured

Reproduced 2026-08-31 on the real committed fixture
`tests/corpus/fixtures/clean_control_seg.nii.gz`, by taking its own ordered
centroid sequence and a reversed copy through `fit_centroid_spline` +
`compute_spine_curvature` (a standalone snippet, not a pytest run):

| sequence | `tangent_angles_deg` |
|---|---|
| as stored (advances superiorly) | `[8.1652, 4.0730, 0.0000, 4.0730, 8.1652]` |
| reversed copy (advances caudally) | `[171.8348, 175.9270, 180.0000, 175.9270, 171.8348]` |

The same physical spine, two readings — `~5°` per level one way and `~175°`
the other — and no consumer can tell which it got. The reversed array is
exactly `180 − a` element-wise: on a straight spine the discrepancy is exactly
`180.000000000°`, and reversing back gives a post-fix residual of
`8.882e-15°` on `clean_control`, `7.816e-14°` on a 7-point coronal C-curve,
`0.0` on a straight spine, and `6.563e-03°` on a doubling-back
`mode4_relabel_swap`-shaped fixture (the last is spline-fit asymmetry, not
convention).

`inter_tangent_angles_deg[]` does **not** inherit the sensitivity, measured on
the same four fixtures: it is the angle *between* consecutive tangents, and
`angle_between(-a, -b) == angle_between(a, b)` bit-for-bit (negation flips a
sign bit; the dot products and norms are summed in the same order). Reversing
`clean_control` reverses the array and changes no value —
`max |forward − reversed(reversed-input)| = 0.000000000°`. It is therefore
already correct under the one convention, and this item changes no value in it;
it only documents it under that convention and asserts the invariance.

### Why it has stayed latent, and where it stops being latent

Every in-repo driver advances superiorly. All nine corpus fixtures report a net
`+S` advance of `+160 mm` (`mode8_force_overlap`: `+142 mm`), and every
`catalogue.iter_driver_records()` driver likewise `+160 mm` — so item 122's
normalisation rule is a no-op across the whole committed surface and no
committed value moves.

That is a property of the synthetic corpus, not of the world. `build_clean_spine`
stacks ascending labels along ascending axis 2, so `clean_control` places `L1`
at `S = 27 mm` and `L5` at `S = 187 mm` — inverted relative to real anatomy.
Real data ordered the way `pipeline.extract_feature_record` orders it (ascending
label, which item 093 pins as head-to-tail: `20 = L1 … 24 = L5`) advances
*caudally*, so on real VerSe input today's code returns the `~175°` reading. The
values that move under this fix are exactly the ones no committed artifact holds.

### What this item is NOT

It does not decompose either array into per-axis components (both are
`retune`-dispositioned in `feature_docs.STATUS_OVERRIDES` for exactly that, and
that signed text is not touched here). It does not fold angles per element into
`[0, 90]` — see AC4; that would destroy real signal and move committed values.
It does not change `total_curvature_deg`, the signed per-plane arrays, or item
121's `VertebralTangentOrientation` values. It does not rebuild
`reference_default.json` or `reference_verse_v1.json`, recalibrate any
threshold, wire either array into a rule, or correct the synthetic corpus's
inverted `S` stacking (captured in `insights.md`, not acted on here).

## Acceptance Criteria

- [ ] **AC1: `tangent_angles_deg` is computed from direction-normalised
  tangents.** In `compute_spine_curvature`, the array is derived from the same
  `normalised_tangents` array the signed per-plane arrays use — the unit
  tangents negated exactly when
  `centroids[-1].centroid_mm[2] - centroids[0].centroid_mm[2] < 0` — not from
  the raw `unit_tangents`. Asserted behaviourally: on a cranial-first straight
  spine (5 centroids, 10 mm apart, supplied head-first) every entry is
  `pytest.approx(0.0, abs=1e-9)`, where the pre-item code returns `180.0`.

- [ ] **AC2: `tangent_angles_deg` is reversal-equivariant on well-conditioned
  fixtures.** For each of a straight spine (n=5), a coronal C-curve (n=7) and
  `clean_control`'s own centroid sequence, `curvature(seq).tangent_angles_deg`
  equals `tuple(reversed(curvature(list(reversed(seq))).tangent_angles_deg))`
  within `abs=1e-9` (measured post-fix residuals: `0.0`, `7.816e-14`,
  `8.882e-15` degrees).

- [ ] **AC3: `tangent_angles_deg` is reversal-equivariant on a doubling-back
  fixture.** The same equality holds for a `mode4_relabel_swap`-shaped
  sequence within `abs=1e-2` — the residual is spline-fit asymmetry on a
  curve that reverses in `S` (measured `6.563e-03` degrees), not a convention
  difference. The looser tolerance is asserted with the measured value named in
  the failure message.

- [ ] **AC4: the normalisation is one global sign decision, never a per-element
  fold.** `mode4_relabel_swap`'s array, taken through
  `extract_feature_record`, is
  `[3.2953, 177.6490, 175.2184, 1.4658, 22.0118]` within `abs=1e-3` — a case
  that carries both near-`0°` and near-`180°` entries at once, because two of
  its tangents genuinely reverse. A per-element fold (`min(a, 180 - a)`) would
  read `[3.2953, 2.3510, 4.7816, 1.4658, 22.0118]`; this AC fails on that
  implementation.

- [ ] **AC5: no committed corpus case's `tangent_angles_deg` moves.** For all
  nine cases in `tests/corpus/manifest.json`, the array from
  `extract_feature_record` matches its pre-item value within `abs=1e-3`,
  pinned as a literal table in the test module (measured 2026-08-31 —
  `clean_control`/`mode2_fragment`/`mode7_sequence_break`
  `[8.1652, 4.0730, 0.0, 4.0730, 8.1652]`; `mode1_displace`
  `[25.5042, 27.8238, 0.0, 27.8238, 25.5042]`; `mode3_inject_islands`
  `[8.1498, 4.0650, 0.0, 4.0650, 8.1498]`; `mode4_relabel_swap` per AC4;
  `mode5_remove_level` `[7.6323, 3.7952, 3.7952, 7.6323]`;
  `mode6_crop_at_border` `[28.8047, 24.3476, 0.0, 24.3476, 28.8047]`;
  `mode8_force_overlap` `[13.2111, 6.9636, 0.6253, 4.9247, 5.7262]`).

- [ ] **AC6: every corpus case's net `+S` advance is positive.** For all nine
  cases, `centroid_mm[2]` of the highest-numbered label minus that of the
  lowest is `> 0` (measured `+160.0 mm`, and `+142.0 mm` for
  `mode8_force_overlap`) — the fact that makes AC5 true rather than a
  coincidence, asserted so a future corpus change that inverts a case fails
  here and names the reason instead of silently moving AC5's table.

- [ ] **AC7: `inter_tangent_angles_deg` is reversal-equivariant and unmoved.**
  For the four AC2/AC3 fixtures the array equals the reverse of its reversed
  input's array within `abs=1e-2` (exactly `0.0` residual on the three
  well-conditioned ones), and for all nine corpus cases it matches its
  pre-item literal table within `abs=1e-3`.

- [ ] **AC8: one canonical convention statement exists in code.**
  `features/orientation.py` defines a module-level string constant naming the
  convention, exported in `__all__`, whose text states both the trigger (the
  ordered centroids' net advance in `+S` being negative) and the result (every
  tangent negated once, globally, so the sequence is read as advancing
  superiorly), and states that the negation is per-case and never per-element.

- [ ] **AC9: the `SpineCurvature` docstring states the convention for both
  unsigned arrays.** `SpineCurvature.__doc__`'s `tangent_angles_deg` and
  `inter_tangent_angles_deg` attribute blocks each contain the canonical key
  phrase `normalised so the sequence advances superiorly`.

- [ ] **AC10: `FEATURE_DOCS` states the convention for both unsigned leaf
  paths.** The combined `measures + " " + computation` text of
  `stage3.curvature.tangent_angles_deg[]` and
  `stage3.curvature.inter_tangent_angles_deg[]` each contains the same
  canonical key phrase.

- [ ] **AC11: `report_schema_v0.json` states the convention for both unsigned
  keys.** The `stage3Curvature` definition's `tangent_angles_deg` and
  `inter_tangent_angles_deg` `description` strings each contain the canonical
  key phrase.

- [ ] **AC12: the backwards phrase is gone repo-wide.** The literal string
  `cranial-to-caudal traversal` appears nowhere under `src/segfacet/` — it
  names the opposite of what the code does (the normalised tangents advance
  *superiorly*, i.e. caudal-to-cranial), and it currently sits at five sites:
  `features/orientation.py:18` and `:548`, `feature_docs.py:1469` and `:1475`,
  and `report_schema_v0.json:519`. Each is replaced by the canonical phrasing.

- [ ] **AC13: the superseded note is gone.** No text in
  `features/orientation.py` states that `tangent_angles_deg` or
  `inter_tangent_angles_deg` is unaffected by, or excluded from, the direction
  normalisation (the comment currently at `:474-475`).

- [ ] **AC14: item 122's plane and RAS statements survive the reword.** Each of
  `stage3.curvature.{coronal,sagittal}_tangent_angles_deg[]` and
  `stage3.curvature.{coronal,sagittal}_curvature_deg` still names its
  anatomical plane and still states the RAS precondition —
  `tests/test_122_signed_curvature.py::test_ac17_new_leaf_docs_name_their_plane_and_ras_precondition`
  passes unchanged.

- [ ] **AC15: the catalogue regenerates byte-identically from the tree.** A
  fresh `segfacet.catalogue.main(["--json", …, "--md", …])` matches the
  committed `docs/aide/feature_catalogue.generated.json` and `.md`
  byte-for-byte, and `build_catalogue(strict=True)` raises nothing. Both paths
  are already allowlisted for byte-exact fresh-vs-committed comparison in
  `tests/committed_artifact_guard.py` under ground `emission-clamped`; this
  item adds no allowlist entry and follows
  `test_130_one_closest_point_search.py::test_ac22_…`'s shape.

- [ ] **AC16: the catalogue's leaf-path set is unchanged.** This item adds and
  removes no feature path: the sorted set of `path` values in the regenerated
  catalogue equals the set in the pre-item committed artifact, asserted against
  a literal count and the six `stage3.curvature.*` paths by name.

- [ ] **AC17: the observed-range cells for both unsigned paths are unchanged.**
  In the regenerated catalogue, `stage3.curvature.tangent_angles_deg[]` still
  reports corpus range `0–8.1652` and `stage3.curvature.inter_tangent_angles_deg[]`
  still `3.83716–7.59031`, with both verdicts unchanged (`varies` / `retune`
  status). Follows from AC5/AC7 plus every driver record advancing superiorly,
  and is asserted directly so a regression in either shows up as a range move.

- [ ] **AC18: item 104's drift test is clean in both directions.**
  `tests/test_104_feature_catalogue_drift.py` passes: no realised path is
  undocumented and no documented path is no longer produced.

- [ ] **AC19: no corpus case changes its findings.** For every case in
  `tests/corpus/manifest.json`, `run_qc(seg_img, bundled_default_config())`
  yields the same `{(rule_id, tuple(sorted(labels)))}` set as
  `tests/test_129_coincident_centroids_and_held_out_floor.py`'s
  `_PRE_129_FINDINGS` table.

- [ ] **AC20: no reference artifact moves.**
  `tests/test_128_reference_verse_v1_integrity.py`'s sha256 pin on
  `src/segfacet/reference/reference_verse_v1.json` still passes, and a fresh
  `build_and_write_default` output still matches the committed
  `reference_default.json` through
  `committed_artifact_guard.assert_matches_committed_artifact` (never
  byte-compared — item 127's exclusion).

- [ ] **AC21: the other curvature fields are unmoved.** For all nine corpus
  cases, `total_curvature_deg`, `coronal_curvature_deg`,
  `sagittal_curvature_deg`, `curvature_plane` and both signed per-centroid
  arrays match their pre-item values within `abs=1e-6` (strings compared
  exactly) — this item touches only the two unsigned arrays' derivation.

- [ ] **AC22: item 121's per-vertebra tangent orientations are unmoved.**
  `tests/test_121_tangent_orientation.py` passes unchanged; Part C was already
  direction-normalised and its values do not move.

- [ ] **AC23: `STATUS_OVERRIDES` is untouched.** The `retune` disposition and
  verbatim reasoning for `stage3.curvature.tangent_angles_deg[]` and
  `stage3.curvature.inter_tangent_angles_deg[]` in
  `feature_docs.STATUS_OVERRIDES` are byte-identical to their pre-item text
  (signed maintainer transcript, item 106 — queue-018's scope fence).

- [ ] **AC24: the tie at exactly zero net advance is deterministic and
  documented.** A sequence whose first and last centroid share an `S`
  coordinate takes no negation (item 122's strict `< 0`); two calls on such a
  sequence return equal arrays, every entry is finite, and the canonical
  constant's text names the tie-break. Reversal-equivariance is **not**
  asserted here — it does not hold for a non-flat zero-net-advance path, and
  saying so is the point.

- [ ] **AC25: the committed-artifact guard reports no new violation.**
  `committed_artifact_guard.iter_violations` over `tests/` reports no violation
  attributable to this item's test module.

- [ ] **AC26: the regression test fails before the fix.** On the commit
  immediately preceding the implementation commit, this item's AC1 and AC2
  tests fail. Demonstrated by the Validation section's replay, not by a
  self-referential assertion.

## Assumptions

- **The convention adopted is item 122's, unchanged.** One global negation of
  the unit tangents, triggered by
  `centroids[-1].centroid_mm[2] - centroids[0].centroid_mm[2] < 0`, applied
  before any angle is taken. The alternative reading of "normalise" — folding
  each angle into `[0, 90]` — is rejected because `mode4_relabel_swap` carries
  genuinely reversing tangents (`177.6490°`, `175.2184°`) that a fold would
  silently collapse to `2.3510°`/`4.7816°`, moving a committed value and
  deleting the signal item 132 is about to depend on. AC4 exists to make that
  choice load-bearing rather than implicit.

- **`inter_tangent_angles_deg` needs no code change.** Measured invariant
  under the negation (bit-identical: negation is a sign-bit flip, and the dot
  product and norms sum in the same order). The builder may compute it from
  either `unit_tangents` or `normalised_tangents` — the two are provably equal
  — but AC7's values must not move either way. The queue's "if it inherits the
  same sensitivity" is answered: it does not.

- **Correcting `cranial-to-caudal traversal` (AC12) is in scope.** The phrase
  names the opposite of what the code does, and this item's whole deliverable
  is that the record carries **one** convention, stated once. Leaving one array
  described backwards would defeat it. The correction is prose-only, moves no
  value, and reaches two item-122 leaf docs and one item-121 docstring — the
  catalogue diff it produces is the mechanical consequence, not a scope
  expansion. `STATUS_OVERRIDES` and `golden-decision-table.md` are untouched
  (AC23).

- **The canonical key phrase is `normalised so the sequence advances
  superiorly`.** Chosen because it is short, exact and directionally
  unambiguous, so AC9–AC11 can assert an exact substring rather than paraphrase
  matching. If the builder prefers different wording, it must change in one
  place (the AC8 constant) and the tests read it from there.

- **The catalogue's driver set, not the corpus, determines the observed-range
  cells.** `catalogue.iter_driver_records()` builds from
  `synth.clean_gt.build_clean_spine` + `synth.perturbation`, not from
  `tests/corpus/fixtures/`. Measured 2026-08-31: all five stage-3-carrying
  drivers advance `+160 mm`, so AC17's ranges hold for the same reason AC5
  does.

- **Nothing consumes either array.** Confirmed by grep over `src/segfacet/`:
  no rule under `heuristics/`, nothing under `reference/`, nothing under
  `eval/` and no script reads `tangent_angles_deg` or
  `inter_tangent_angles_deg`; the only readers are `feature_report.py`'s
  serialiser and the docs/schema. This is why the item needs no reference
  rebuild, no threshold recalibration and no `test_128` digest change even
  though it changes a feature's meaning on real input.

- **`aide check --queue 018`'s cross-spec errors involving this item are
  adjudicated, not outstanding.** The check compares specs pairwise with no
  notion of landing order, and items 126–130 are all ✅ merged, so every error
  naming one of them as the *changer* and item 131 as the *pinner* is history
  (`tests/test_121_tangent_orientation.py` ← item 126;
  `tests/committed_artifact_guard.py` ← item 127;
  `src/segfacet/reference/reference_default.json` and
  `tests/test_129_…py` ← item 129). Of the four errors naming item 131 as the
  changer, each was checked against what the landed spec actually pins:
  item 126 pins `report_schema_v0.json` as "the validation contract AC3/AC6
  check fresh reports against" — this item changes only `description` strings,
  so validation semantics are untouched; item 130 pins
  `features/orientation.py` for "AC19/AC20 … still receive the pipeline's
  single fit and … `closest_u` values agree", neither of which this item
  touches, and pins `feature_docs.py` only for the
  `stage3.per_label_offsets[].closest_u` entry's text, which this item does not
  edit; items 129 and 130 pin the two catalogue artifacts byte-for-byte against
  a fresh regeneration, which stays green because step 7 regenerates them in
  the same commit (recorded in the reconciliation table). No pin needs widening
  and no edit needs narrowing.

- **Items 126–130 have landed.** In particular the whole-record snapshot
  goldens are gone (`tests/corpus/golden/` no longer exists), so no snapshot
  regenerates; item 127's guard and allowlist are in place; and item 130's
  single in-sample fit is bound in `pipeline.py` and passed to
  `compute_spine_curvature`, so this item's change is made once per case.

## Implementation Steps

1. **`features/orientation.py` — move the normalisation above the angle
   block.** The `net_advance_s` computation and the
   `normalised_tangents = -unit_tangents if net_advance_s < 0 else unit_tangents`
   assignment currently sit *after* `tangent_angles_deg` and
   `inter_tangent_angles_deg` are built (`:469-484`). Move that block up, so it
   runs immediately after `unit_tangents` is formed, and leave the signed
   per-plane calls reading the same array they read today (no value change
   there).

2. **Derive `tangent_angles_deg` from `normalised_tangents`.** Change the
   comprehension at `:459-461` to `_angle_to_z_axis_deg(normalised_tangents[i])`.
   Nothing else in the function changes; the return value's shape, types and
   ordering are untouched.

3. **Decide `inter_tangent_angles_deg`'s source.** Either leave it on
   `unit_tangents` or move it to `normalised_tangents` — the results are
   bit-identical. Whichever is chosen, add a one-line comment naming the
   identity `angle_between(-a, -b) == angle_between(a, b)` so a later reader
   does not "fix" an apparent inconsistency.

4. **Add the canonical constant (AC8).** A module-level string in
   `features/orientation.py` — a name that reads as the convention, added to
   `__all__` — carrying the trigger, the result, the "global, never
   per-element" rule and the zero-net-advance tie-break. Delete the superseded
   comment at `:474-475` (AC13).

5. **Restate the convention at the definition sites.** The two unsigned
   attribute blocks in `SpineCurvature.__doc__` (AC9); the module docstring's
   Part B paragraph, which currently says only the *signed* arrays are
   normalised; the two `FEATURE_DOCS` entries (AC10); the two
   `report_schema_v0.json` descriptions (AC11). Each carries the canonical key
   phrase.

6. **Replace `cranial-to-caudal traversal` at all five sites (AC12)** —
   `orientation.py:18` (module docstring Part B) and `:548` (Part C's
   `spline_tangent` docstring), `feature_docs.py:1469` and `:1475` (the coronal
   and sagittal `computation` texts), `report_schema_v0.json:519` (the coronal
   description). Keep each site's plane word and RAS marker intact (AC14).

7. **Regenerate the catalogue.**
   `.venv/bin/python -m segfacet.catalogue --json docs/aide/feature_catalogue.generated.json --md docs/aide/feature_catalogue.generated.md`
   (or the module's documented entry point). Only the `computation`/`measures`
   cells of the four affected `stage3.curvature.*` rows should change; the
   observed-range cells must not (AC17), and no row is added or removed
   (AC16).

8. **Reconcile `tests/test_122_signed_curvature.py`'s prose (docstrings and the
   section header only — no assertion changes).** The section header "the
   retained unsigned arrays are unchanged by normalisation" and
   `test_adv_tangent_angles_deg_length_and_finiteness_on_cranial_first_input`'s
   docstring ("keeps its present (unsigned, un-normalised) meaning … that is
   item 121's territory") both become false statements once this item lands.
   Correct them to name item 131 and what the tests now demonstrate.
   `test_adv_retained_arrays_invariant_to_direction_normalisation`'s
   assertions stay exactly as they are — they concern
   `inter_tangent_angles_deg`, which is genuinely invariant — but its docstring
   should stop implying the claim extends to `tangent_angles_deg`.

## Authorised paths

**May change:**

- `src/segfacet/features/orientation.py` — the normalisation move, the
  canonical constant, and every docstring site (AC1, AC8, AC9, AC12, AC13,
  AC24).
- `src/segfacet/feature_docs.py` — `FEATURE_DOCS` prose for the four affected
  `stage3.curvature.*` entries only (AC10, AC12, AC14). `STATUS_OVERRIDES` is
  explicitly out of bounds (AC23).
- `src/segfacet/report_schema_v0.json` — the `stage3Curvature` `description`
  strings for `tangent_angles_deg`, `inter_tangent_angles_deg` and
  `coronal_tangent_angles_deg` only (AC11, AC12). No change to `type`,
  `required`, `properties` membership or `additionalProperties`.
- `docs/aide/feature_catalogue.generated.json` — regenerated (AC15–AC17).
- `docs/aide/feature_catalogue.generated.md` — regenerated, same.
- `tests/test_131_tangent_direction_normalisation.py` — this item's tests.
- `tests/test_122_signed_curvature.py` — docstring and section-header prose
  only, per step 8. No assertion, fixture, parametrisation or import changes.
- `docs/aide/items/131-normalise-tangent-angles-for-traversal-direction.md` —
  this spec.

**Asserts against:**

- `tests/corpus/fixtures/*_seg.nii.gz` — AC4/AC5/AC6/AC7/AC19/AC21 read every
  case through `extract_feature_record` / `run_qc` and pin the resulting
  values; the fixtures themselves are not modified.
- `tests/corpus/manifest.json` — AC5/AC19 enumerate cases from it.
- `src/segfacet/reference/reference_verse_v1.json` — AC20, via
  `tests/test_128_reference_verse_v1_integrity.py`'s sha256 pin. Not modified.
- `src/segfacet/reference/reference_default.json` — AC20, compared through
  `committed_artifact_guard.assert_matches_committed_artifact` (numeric
  tolerance), never byte-compared. Not modified.
- `tests/committed_artifact_guard.py` — AC15 relies on its existing
  `emission-clamped` allowlist entries for the two catalogue paths; AC25 calls
  `iter_violations`. Not modified, and no allowlist entry is added.
- `tests/test_129_coincident_centroids_and_held_out_floor.py` — AC19 imports
  its `_PRE_129_FINDINGS` table rather than restating it (the idiom
  `test_129` itself uses for `test_128`'s digest). Not modified.
- `tests/test_121_tangent_orientation.py` — AC22 requires it green unchanged.
  Not modified.
- `src/segfacet/synth/clean_gt.py` — AC17 depends on every catalogue driver
  advancing superiorly, which this module's stacking loop determines. Read for
  the reason, not modified; correcting the inverted `S` stacking is out of
  scope and captured in `insights.md`.

## Testing Strategy

New module `tests/test_131_tangent_direction_normalisation.py`, one focused
test per AC. Fixture builders mirror
`tests/test_122_signed_curvature.py`'s (`_straight_spine`, `_coronal_c_curve`,
`_cranial_first_straight`, `_cranial_first_c_curve`,
`_mode4_relabel_swap_shape`) so the two modules exercise the same shapes;
copy them rather than importing, per the module-independence convention this
repo's item tests follow.

**Per-AC coverage.** AC1 the cranial-first straight spine reading `0.0`, not
`180.0`; AC2 three-fixture reversal equivariance at `1e-9`; AC3 the
doubling-back fixture at `1e-2`; AC4 `mode4_relabel_swap`'s literal array,
with the per-element-fold alternative spelled out in the failure message; AC5
and AC7 the nine-case literal tables; AC6 the net-advance sign; AC8 the
constant's existence, `__all__` membership and required substrings; AC9–AC11
the six doc-site substring checks; AC12 a source sweep for the retired phrase
over `src/segfacet/**`; AC13 a source sweep of `orientation.py`; AC14
delegates to `test_122`'s existing test staying green; AC15–AC18 the catalogue
regeneration, path set, observed ranges and drift; AC19–AC22 the
no-movement pins; AC23 the `STATUS_OVERRIDES` text; AC24 the zero-net-advance
tie; AC25 the guard sweep.

**Adversarial and edge cases.**

- **Two centroids only** (the minimum `compute_spine_curvature` accepts),
  supplied both ways: arrays are length 2 and 1, finite, and equivariant.
- **Fewer than two centroids** still raises `ValueError` with the existing
  message — the guard is not disturbed by the reordering in step 1.
- **A purely horizontal pair** (both centroids at the same `S`, differing in
  `R`): net advance is exactly `0.0`, no negation, both readings `90°`,
  deterministic across two calls (AC24).
- **A zero-net-advance non-flat path** (up then back to the same `S`): two
  calls agree and all entries are finite; equivariance is deliberately not
  asserted, and the test says why in its docstring.
- **Near-coincident centroids** (`1e-6` mm apart, item 122's substituted
  fixture): finite, no crash, no `nan`.
- **Anisotropic spacing** on a straight spine: still `0.0` both ways.
- **Determinism:** two `compute_spine_curvature` calls on one input return
  equal tuples for both arrays.
- **Immutability:** `SpineCurvature` stays frozen; the input centroid sequence
  is not mutated by the call (compare `centroid_mm` before and after).
- **Range:** every `tangent_angles_deg` entry stays in `[0, 180]` and every
  `inter_tangent_angles_deg` entry in `[0, 180]` and non-negative, on all
  fixtures both ways — the schema's `type: number` and `test_019`'s
  non-negativity assertions stay true.

**Existing tests to reconcile** (swept 2026-08-31 over every `tests/` hit for
`tangent_angles_deg`; each verdict checked against the proposed change before
this spec was written):

| Test | Verdict |
|---|---|
| `test_122::test_adv_tangent_angles_deg_length_and_finiteness_on_cranial_first_input` | **Green, docstring false.** Asserts only length and finiteness, both still true. Its docstring claims the array "keeps its present (unsigned, un-normalised) meaning" — corrected by step 8, assertions untouched. |
| `test_122::test_adv_retained_arrays_invariant_to_direction_normalisation` | **Green unchanged** — it tests `inter_tangent_angles_deg`, which is genuinely invariant (measured `0.0` residual). Section header and docstring reworded so they no longer imply the claim covers `tangent_angles_deg`. |
| `test_122::test_ac5_coronal_c_curve_equals_inter_tangent_sum` | **Green unchanged** — `inter_tangent_angles_deg` does not move, and the coronal array does not either. |
| `test_122::_retired_formula` helper (`max - min` of `tangent_angles_deg`) and `test_ac5_retired_formula_is_half_on_same_fixture` | **Green unchanged** — the fixture (`_coronal_c_curve`) advances superiorly, so the array is byte-identical post-fix. |
| `test_122::test_ac17_new_leaf_docs_name_their_plane_and_ras_precondition` | **Green if the reword keeps the plane word and a `_RAS_MARKERS` entry** — AC14 makes this explicit. |
| `test_122::test_ac18_*` (three tests: the retired `max/min(tangent_angles_deg)` formula is gone from docs, schema and docstring) | **Green unchanged** — the new prose must not reintroduce the literal substrings `max(tangent_angles_deg)` / `min(tangent_angles_deg)`. Called out because step 5 rewrites exactly those three texts. |
| `test_122::test_ac19_generated_catalogue_{json,md}_contains_new_paths` | **Green unchanged** — path membership only; AC16 keeps the path set fixed. |
| `test_019` (lengths, finiteness, non-negativity, determinism, `total_curvature_deg` bounds) | **Green unchanged** — every fixture advances superiorly and no assertion pins a value that moves. |
| `test_022::test_ac2_*` (curvature key set and array lengths), `test_022`'s serialisation type checks | **Green unchanged** — additive-safe, key-based. |
| `test_119::test_ac26_orientation_curvature_note_no_longer_names_splev` | **Green if the reword does not reintroduce `splev`** in `FEATURE_DOCS["stage3.curvature.tangent_angles_deg[]"].computation` or `GROUP_INTROS["Orientation & Curvature"]`. Step 5 edits that exact text. |
| `test_119::test_ac27_catalogue_regeneration_matches_committed_artifacts` | **Green after step 7** — it compares fresh against committed, so it passes once the catalogue is regenerated in the same commit. Red if step 7 is skipped. |
| `test_121` (per-vertebra tangent orientation values) | **Green unchanged** — Part C is already normalised; AC22. |
| `test_124::test_adv_scalar_list_collected_element_wise` (`tangent_angles_deg[]` corpus count > 1) | **Green unchanged** — a count, not a value. |
| `test_124`'s observed-range assertions generally | **Green unchanged** — AC17 pins the two ranges explicitly. |
| `test_104` catalogue drift (both directions) | **Green after step 7** — no path added or removed, so drift is clean once the artifact is regenerated. |
| `test_129::test_ac20_catalogue_regeneration_matches_committed_artifacts`, `test_130::test_ac22_…` | **Green after step 7** — same fresh-vs-committed comparison in two other modules; both go red until the catalogue is regenerated. This is the mechanical-survey case item 127's standing rule names: found by `grep -rn "feature_catalogue.generated" tests/`, not by hand-listing. |
| `test_129::test_ac29_no_corpus_case_changes_findings` | **Green unchanged** — AC19 asserts the same table for the same reason. |
| `test_111_golden_guard`, `test_127_committed_artifact_tolerance` | **Green unchanged** — no new byte-exact comparison outside the allowlist (AC25). |
| `tests/report_format_fixture.py`, `tests/golden/report_format_contract.json` | **Green unchanged** — hand-written literals serialised straight through; no extractor runs. |

## Validation

Beyond the suite, three things must be *observed*:

1. **The two readings, before and after.** Run a standalone snippet (not a
   pytest run) that takes `clean_control`'s ordered centroids and a reversed
   copy through `fit_centroid_spline` + `compute_spine_curvature` and prints
   both `tangent_angles_deg` arrays. Pre-fix it prints
   `[8.1652, 4.0730, 0.0, 4.0730, 8.1652]` and
   `[171.8348, 175.9270, 180.0, 175.9270, 171.8348]`; post-fix both print the
   first array (the second reversed). Record both outputs.

2. **Fails before the fix (AC26).** `git switch --detach` to the commit
   immediately preceding the implementation commit, copy in
   `tests/test_131_tangent_direction_normalisation.py`, and confirm the AC1 and
   AC2 tests **fail** there; then return to the branch tip and confirm they
   pass. Record the failing assertion text. This is the check item 135 replays
   for every Stage 29 defect.

3. **The CLI still produces a `stage3` block.** Run
   `.venv/bin/python -m segfacet run --scan tests/corpus/fixtures/base_scan.nii.gz --seg tests/corpus/fixtures/clean_control_seg.nii.gz --out <tmp> --no-reference`
   and confirm the emitted report validates, carries
   `features.stage3.curvature.tangent_angles_deg`, and that its values match
   AC5's `clean_control` row. `--scan` is required alongside `--seg`
   (`cli.py`'s `_handle_run`) and `--no-reference` avoids the item-090 default
   reference firing ~40 findings on a synthetic fixture — both recorded in
   `insights.md` and `CLAUDE.md`'s Gotchas.

No `[validation]` environment profile is needed: everything above runs on the
default CPU-only install with no optional dependency.

## Dependencies

- **Item 121** (✅) — Part C's `VertebralTangentOrientation`, already
  direction-normalised; AC22 pins it unmoved.
- **Item 122** (✅) — establishes the direction convention and the
  `normalised_tangents` computation this item reuses; supplies the fixture
  shapes and the two tests reconciled in step 8.
- **Item 126** (✅) — the whole-record snapshot goldens are retired, so no
  snapshot regenerates when a feature's documented meaning changes.
- **Item 127** (✅) — the committed-artifact guard and its `emission-clamped`
  allowlist entries for the two catalogue paths (AC15, AC25), and the
  `assert_matches_committed_artifact` helper AC20 uses.
- **Item 129** (✅) — supplies `_PRE_129_FINDINGS` (AC19) and the
  allowlisted catalogue-comparison shape AC15 follows.
- **Item 130** (✅) — `pipeline.py` binds one in-sample fit and passes it to
  `compute_spine_curvature`, so this item's change applies once per case.

**Downstream:** item 132 depends on `mode4_relabel_swap`'s doubling-back
tangent signal surviving intact (AC4); item 135 replays AC26's
fails-before-the-fix check as part of the Stage 29 validation.

## Decisions & Trade-offs

- **Implementation followed the spec's step 1-8 shape exactly.** In
  `compute_spine_curvature`, the `net_advance_s` / `normalised_tangents`
  block was moved above the angle computations; `tangent_angles_deg` is now
  `_angle_to_z_axis_deg(normalised_tangents[i])`; `inter_tangent_angles_deg`
  stays on `unit_tangents` (bit-identical to `normalised_tangents` per the
  proven `angle_between(-a, -b) == angle_between(a, b)` identity), with a
  one-line comment naming that identity so a later reader does not "fix" an
  apparent inconsistency.

- **The AC8 canonical constant is `TANGENT_DIRECTION_CONVENTION`**, a
  module-level string in `features/orientation.py`, added to `__all__`. Its
  text states the trigger (net `+S` advance negative), the result (every
  tangent negated once, globally, so the sequence is read as advancing
  superiorly), the "global, never per-element" rule, and the zero-net-advance
  tie-break (no negation applied), and it embeds the exact canonical key
  phrase `normalised so the sequence advances superiorly` (the Assumptions
  section's chosen wording) — one string, one place to change the wording,
  satisfying `test_ac8_*`/`test_ac24_canonical_constant_names_the_tie_break`.

- **`cranial-to-caudal traversal` replaced at all five pinned sites** —
  `features/orientation.py:18` (module docstring Part B) and the
  `VertebralTangentOrientation.tangent` attribute doc (item 121, prose-only,
  values unmoved per AC22), `feature_docs.py`'s coronal/sagittal
  `computation` texts, and `report_schema_v0.json`'s coronal `description` —
  each replaced with the canonical phrasing while preserving its plane word
  and RAS marker (AC14). Two other `orientation.py` sites use the
  differently-worded "cranial-to-caudal direction" (no "traversal"), which is
  not the retired phrase AC12 targets, so those were left as-is; the
  `coronal_tangent_angles_deg`/`sagittal_tangent_angles_deg` docstring block
  and `SpineCurvature` module docstring were also reworded for consistency
  even though they weren't literal AC12 hits.

- **`report_schema_v0.json` edits stayed inside the three keys the spec
  authorises** (`tangent_angles_deg`, `inter_tangent_angles_deg`,
  `coronal_tangent_angles_deg`) — `sagittal_tangent_angles_deg`'s
  description never carried the retired phrase, so it was left untouched
  rather than widening the authorised-paths list.

- **Catalogue regenerated in the same commit** via
  `python -m segfacet.catalogue --json docs/aide/feature_catalogue.generated.json
  --md docs/aide/feature_catalogue.generated.md`. Diff confirmed limited to
  the four `stage3.curvature.*` `computation` cells; leaf-path count stayed
  at 138, the eight `stage3.curvature.*` paths unchanged, and the two
  observed-range cells (`0–8.1652`, `3.83716–7.59031`) with `varies`/`retune`
  verdicts unchanged — matching AC15-AC17.

- **Verified by direct (non-pytest) replay**, per the spec's Validation
  section: `clean_control`'s ordered and reversed centroid sequences through
  `fit_centroid_spline` + `compute_spine_curvature` now both read
  `[8.1652, 4.0730, 0.0, 4.0730, 8.1652]` (pre-fix the reversed reading was
  `[171.8348, 175.9270, 180.0, 175.9270, 171.8348]`); `mode4_relabel_swap`'s
  `tangent_angles_deg` through `extract_feature_record` reads
  `[3.2953, 177.649, 175.2184, 1.4658, 22.0118]`, matching AC4/AC5's pinned
  tables; the `segfacet run --no-reference` CLI replay on
  `clean_control_seg.nii.gz` emits `features.stage3.curvature.tangent_angles_deg
  == [8.1652..., 4.0730..., 0.0, 4.0730..., 8.1652...]`, matching AC5's row.
