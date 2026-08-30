# Item 121 — Tangent-based vertebra orientation

> **Created:** 2026-08-29 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 121
> **Objectives:** G7 (evaluable & regression-testable — a per-vertebra feature
> that actually varies per vertebra); G2 indirectly (a candidate rule input
> where today's `principal_axis` is a constant and can never discriminate)
> **Suggested branch:** `aide/121-tangent-based-vertebra-orientation`

---

## Description

`stage3.per_label_orientations[].principal_axis` is the first principal
component of each vertebra's voxel cloud. Measured across all nine committed
corpus goldens (2026-08-29, under the shipped item-119 fit):

- In **seven** of the nine cases — `clean_control`, `mode1_displace`,
  `mode2_fragment`, `mode4_relabel_swap`, `mode5_remove_level`,
  `mode6_crop_at_border`, `mode7_sequence_break` — *every* vertebra returns
  exactly `(1.0, 0.0, 0.0)`.
- In the remaining two the only departures are
  `(-0.9999188793338074, -0.012737140645483555, -4.376250944919758e-18)`
  (`mode3_inject_islands`) and
  `(-0.9966086608330377, 2.2204460492503136e-16, 0.08228716274473975)`
  (`mode8_force_overlap`) — the same left-right axis, differing by an
  eigenvector sign and a small perturbation from the injected islands /
  forced overlap.

So `|principal_axis · (1, 0, 0)| >= 0.996` for **every** vertebra record in the
whole corpus. The fixture body is a 30×25×25 box and PCA returns its widest
side; on a real vertebra the widest side is also left-right. The feature tracks
no tilt, varies with no level, and no rule reads it.

Both ingredients for a per-vertebra orientation estimate that *does* vary
already exist in this codebase and are never joined: `closest_u` — the spline
parameter of the centroid's closest point on the curve, computed by
`features/spline_offset.py` — and `evaluate_spline_derivative(fit, u, nu=1)`,
the curve tangent, which `features/orientation.py` evaluates at `fit.u` and
immediately collapses to a scalar angle for the *global* curvature descriptor.
This item joins them: for each vertebra, the tangent of the fitted spinal
curve **at that centroid's closest point on it**.

Measured on `clean_control` under the shipped fit, the estimate varies where
PCA does not — coronal tilt `+8.1644°, +4.0746°, 0.0000°, −4.0746°, −8.1644°`
across L1–L5, a spread of `16.3287°`, against a `principal_axis` that is
bit-identical on all five levels.

**This is an orientation *proxy*, not a vertebral coordinate system.** It says
which way the spinal curve runs at this vertebra; it says nothing about the
vertebra's own anatomical frame (superior endplate normal, pedicle axis, and
so on). Several `STATUS_OVERRIDES` entries record the maintainer's standing
call that a real VCS is the eventual replacement for the raw-image-axis
features. This item does not deliver that and must say so where the feature is
defined.

`eigenvalue_ratio` is **retained unchanged**: unlike `principal_axis` it
carries genuine spread on real GT (`reference_verse_v1.json`, measured
2026-08-29: L1 mean `2.1522`, range `1.5609`–`2.6754`, CoV `0.133` over 59
subjects; T8 mean `2.1803`, CoV `0.163`), and it also responds to shape damage
on the synthetic corpus (`1.3831` on `mode2_fragment`'s fragmented label,
`1.4769` on `mode8_force_overlap`'s, against the `1.4407051282051282` every
undamaged fixture vertebra returns).

`principal_axis` is **demoted, not deleted**: the key, its computation and its
schema entry are untouched, and the demotion is carried entirely by
documentation that records the measured constancy and points at the tangent
estimate as the per-vertebra orientation to prefer.

**What this item is NOT.** It does not touch Part B of
`features/orientation.py` (`SpineCurvature`, `compute_spine_curvature`) —
item 122's territory, landed and unchanged here. It does not change
`VertebralOrientation`, `compute_vertebra_orientations` or `_pca_principal_axis`
in any way. It does not change the spline fit (item 119), the offset
evaluation (item 120), any `HeuristicConfig` threshold, any rule, or either
reference artifact. It wires no rule to the new feature: the estimate is
shipped as recorded inventory with catalogue status `unwired`.

### The estimate

Given the fitted `SplineFit` the pipeline already builds for curvature and
monotonic consistency, and the same ordered centroid sequence:

1. **Closest point.** For each centroid, `closest_u` = the spline parameter of
   its closest point on that fit, obtained from the existing public
   `compute_spline_offsets(centroids, fit)`.
2. **Tangent.** `evaluate_spline_derivative(fit, [closest_u], nu=1)[0]`,
   normalised to unit length.
3. **Direction normalisation.** If the sequence's net advance is caudal
   (`centroids[-1].centroid_mm[2] - centroids[0].centroid_mm[2] < 0`), negate
   every tangent — the same global rule item 122 applies, so the estimate is
   invariant to whether the caller supplied the sequence cranial-first or
   caudal-first.
4. **Two readable in-plane angles**, per vertebra, in degrees, **wrapped** to
   `(−180, 180]` and deliberately *not* unwrapped (see
   [Decisions](#decisions--trade-offs)):
   - coronal (**R–S** plane): `degrees(atan2(t_R, t_S))` — positive means the
     curve tilts toward the patient's right as it advances cranially,
   - sagittal (**A–S** plane): `degrees(atan2(t_A, t_S))` — positive means it
     tilts anterior.

   The plane statement holds only because `io.load_volume` reorients every
   volume to axis codes `("R", "A", "S")` and `compute_centroid` derives
   `centroid_mm` as `centroid_voxel * spacing` with no affine of its own — the
   same precondition items 120 and 122 record.

Serialised into the existing `stage3.per_label_orientations[]` entries, beside
the demoted `principal_axis`, as `spline_closest_u`, `spline_tangent`,
`spline_tangent_coronal_deg` and `spline_tangent_sagittal_deg`.

## Acceptance Criteria

- [ ] **AC1: The tangent record exists, one entry per centroid, in input
  order.** `compute_vertebra_tangent_orientations(fit, centroids)` returns a
  list of `VertebralTangentOrientation` whose length equals `len(centroids)`,
  with each entry's `label` and `level_name` copied from the `LabelCentroid`
  at the same index.

- [ ] **AC2: The tangent is a unit vector.** For every returned record,
  `sqrt(tx² + ty² + tz²)` equals `1.0` within `1e-9` on every fixture
  exercised.

- [ ] **AC3: `closest_u` is the closest point on the supplied fit.** For every
  record, `closest_u` equals
  `compute_spline_offsets(centroids, fit)[i].closest_u` exactly, and lies in
  `[0.0, 1.0]`.

- [ ] **AC4: The tangent is the curve derivative at that `closest_u`.** For
  every record, `tangent` equals the unit-normalised
  `evaluate_spline_derivative(fit, [record.closest_u], nu=1)[0]`, up to the
  AC6 direction normalisation, within `1e-12` per component.

- [ ] **AC5: The estimate varies across levels on a curved spine.** On
  `clean_control`'s five centroids under the shipped fit,
  `spline_tangent_coronal_deg` is
  `[+8.1644, +4.0746, 0.0000, −4.0746, −8.1644]` within `1e-3` degrees, so its
  `max − min` spread is `16.3287°` (± `1e-3`) — against a `principal_axis`
  that is identical on all five levels (AC10).

- [ ] **AC6: The estimate is invariant to traversal direction.** Reversing the
  input centroid sequence leaves each label's `tangent`,
  `spline_tangent_coronal_deg` and `spline_tangent_sagittal_deg` unchanged when
  matched by label, within `1e-9` (measured max difference `1.3e-13` on a
  7-level coronal C-curve).

- [ ] **AC7: The estimate is near-constant on a straight spine.** On a
  straight 5-centroid cranio-caudal fixture, every
  `spline_tangent_coronal_deg` and `spline_tangent_sagittal_deg` is `0.0`
  within `1e-9`, so both spreads are `0.0`.

- [ ] **AC8: `spline_tangent_coronal_deg` is the signed R–S angle.** On a
  7-centroid C-curve confined to the R–S plane, the coronal angles are
  `[+57.9714, +40.3384, +21.3043, 0.0000, −21.3043, −40.3384, −57.9714]`
  within `1e-3` degrees, and every `spline_tangent_sagittal_deg` is `0.0`
  within `1e-9`.

- [ ] **AC9: `spline_tangent_sagittal_deg` is the signed A–S angle.** On the
  mirrored 7-centroid C-curve confined to the A–S plane, the sagittal angles
  take those same seven values within `1e-3` degrees, and every
  `spline_tangent_coronal_deg` is `0.0` within `1e-9`.

- [ ] **AC10: PCA's constancy across the committed corpus is pinned.** For all
  nine `tests/corpus/golden/*.json`, every `per_label_orientations[]` entry
  satisfies `abs(dot(principal_axis, (1, 0, 0))) >= 0.996`; and for the seven
  cases other than `mode3_inject_islands` and `mode8_force_overlap`, every
  entry's `principal_axis` is exactly `[1.0, 0.0, 0.0]`. The demotion is
  evidenced by a test, not asserted in prose.

- [ ] **AC11: `VertebralOrientation` is unchanged.** Its field names are
  exactly `("label", "level_name", "principal_axis", "eigenvalue_ratio")` in
  that order, and `compute_vertebra_orientations`'s call signature is
  unchanged (`seg_img, labels, convention=None`).

- [ ] **AC12: `eigenvalue_ratio` and `principal_axis` values are unchanged.**
  For all nine committed goldens, each entry's `eigenvalue_ratio` and
  `principal_axis` equal a freshly computed `compute_vertebra_orientations`
  value **exactly** (no tolerance), so regeneration moved neither.

- [ ] **AC13: The four new keys are serialised with JSON-native types.**
  `feature_report.orientation_to_dict(o, tangent=t)` emits `spline_closest_u`,
  `spline_tangent_coronal_deg` and `spline_tangent_sagittal_deg` as `float`,
  and `spline_tangent` as a 3-element `list` of `float`.

- [ ] **AC14: The serialised values equal the dataclass values.** For a curved
  fixture, each of the four serialised values equals its
  `VertebralTangentOrientation` attribute exactly (the list compared
  element-wise).

- [ ] **AC15: `build_features_block` merges tangents into the orientation
  entries by label.** Given `orientations` and `tangent_orientations` covering
  the same labels but supplied in different orders, every
  `stage3.per_label_orientations[]` entry carries all eight keys with the
  tangent values taken from the record whose `label` matches — not from the
  record at the same index.

- [ ] **AC16: A label-set mismatch is rejected.** `build_features_block`
  raises `ValueError` whose message names the offending label(s) when
  `tangent_orientations`'s label set differs from `orientations`'.

- [ ] **AC17: Omitting `tangent_orientations` stays backward-compatible.**
  `build_features_block` called with `orientations` but no
  `tangent_orientations` produces entries carrying exactly the four original
  keys, and the resulting report still validates against
  `report_schema_v0.json`.

- [ ] **AC18: The schema admits the four new keys.**
  `report_schema_v0.json`'s `stage3OrientationEntry` definition (which sets
  `additionalProperties: false`) lists all four in `properties`, with
  `spline_tangent` constrained to a 3-element numeric array; a Stage-3 report
  carrying them validates without error, and one carrying a misspelt fifth key
  fails validation.

- [ ] **AC19: A pipeline-produced report carries the estimate for every
  label.** For each of the nine committed corpus cases,
  `synth.golden.build_report_for_case(case)`'s
  `features.stage3.per_label_orientations` has all four new keys present on
  every entry, with `spline_tangent` a 3-element list of floats.

- [ ] **AC20: Every new leaf path is documented.** `feature_docs.FEATURE_DOCS`
  carries an entry for each of the four new normalised leaf paths
  (`stage3.per_label_orientations[].spline_closest_u`,
  `…[].spline_tangent[]`, `…[].spline_tangent_coronal_deg`,
  `…[].spline_tangent_sagittal_deg`).

- [ ] **AC21: The proxy status is stated where the feature is defined.** The
  `VertebralTangentOrientation` docstring states that the estimate is an
  orientation **proxy** and **not** a vertebral coordinate system, and names
  the RAS precondition (`io.load_volume` reorients to `("R", "A", "S")`); the
  same two statements appear in the `FEATURE_DOCS` text of the two angle leaf
  paths.

- [ ] **AC22: `principal_axis`'s catalogue entry records its demotion with the
  measured evidence.** Its `FeatureDoc` text names the measured constancy —
  every committed-corpus vertebra within `0.996` of the left-right axis, exact
  `(1, 0, 0)` on seven of the nine cases — and points at
  `spline_tangent_coronal_deg` / `spline_tangent_sagittal_deg` as the
  per-vertebra orientation to prefer. Its `STATUS_OVERRIDES` entry, its schema
  entry and its computation are unchanged.

- [ ] **AC23: The generated feature catalogue is regenerated and
  drift-clean.** `build_catalogue(strict=True)` raises nothing, the committed
  `docs/aide/feature_catalogue.generated.json` and `.md` contain the four new
  leaf paths with status `unwired`, and item 104's drift test is clean in both
  directions.

- [ ] **AC24: Every corpus golden is regenerated and agrees with a fresh
  build.** For all nine `tests/corpus/golden/*.json`,
  `synth.golden.check_case_golden(case)` is `True`, and two successive
  `write_goldens` runs into different directories are byte-identical to each
  other.

- [ ] **AC25: The leaf-count constants match the regenerated catalogue.**
  `tests/test_103_feature_catalogue.py`'s hardcoded `clean_control` leaf count
  equals `len(iter_leaf_paths(record))` (89 → **93**), and every
  `N/M leaf paths unwired` cell in
  `docs/aide/golden-decision-table.md`'s nine Group-A rows equals the value
  `tests/test_105_golden_decision_table.py`'s AC7 recomputes live
  (`22/89` → **`26/93`**).

- [ ] **AC26: The regeneration is narrow.** In the nine regenerated goldens,
  the only changed JSON leaves are the four new keys added inside
  `features.stage3.per_label_orientations[]` — no verdict, finding, threshold,
  geometry, offset, curvature or intensity value moves, and
  `tests/golden/022_stage3_report.json` and both reference artifacts are
  byte-unchanged. *Verified by the [Validation](#validation) section's diff
  commands, not by pytest.*

## Assumptions

- **Record shape and key names.** The queue names the deliverable but not the
  record shape. Assumed: a new frozen dataclass
  `VertebralTangentOrientation(label, level_name, closest_u, tangent,
  coronal_deg, sagittal_deg)` in `features/orientation.py`, serialised into the
  existing `stage3.per_label_orientations[]` entries as `spline_closest_u`,
  `spline_tangent`, `spline_tangent_coronal_deg`,
  `spline_tangent_sagittal_deg`. The `spline_` prefix is deliberate: the record
  already carries `stage3.per_label_offsets[].closest_u`, which since item 120
  is measured against a **held-out refit**, while this one is measured against
  the shared in-sample fit. Two same-named parameters with different meanings
  in one record would be a trap; the names distinguish them and the docs state
  the difference.
- **Evaluated against the shared in-sample fit, not item 120's held-out
  refits.** The pipeline passes the same `SplineFit` it already builds for
  `compute_spine_curvature` and `compute_monotonic_consistency`. Orientation
  describes where along the spine's curve a vertebra sits; detecting that a
  vertebra is displaced is `offset_mm`'s job and item 120 already made it
  held-out. Using n held-out refits here would give n mutually inconsistent
  "spinal curves" within one case, one per vertebra.
- **Two planes, not three.** Coronal (R–S) and sagittal (A–S) only, mirroring
  item 122. An axial (R–A) angle is ill-conditioned for a curve running nearly
  parallel to S — its `atan2` arguments are two small components whose ratio
  swings on noise.
- **Angles are wrapped, not unwrapped.** See [Decisions](#decisions--trade-offs).
  Stated here because it is the one place this item deliberately diverges from
  item 122's convention for the same `atan2` quantity.
- **The four new keys are schema-*optional* but always emitted by the
  pipeline.** They are added to `stage3OrientationEntry.properties` and **not**
  to its `required` list, so the many existing tests that call
  `build_features_block` with `orientations` and no tangents stay green
  unmodified. The real guarantee is AC19: every pipeline-produced report
  carries them on every entry. `additionalProperties: false` still rejects a
  typo'd key.
- **`VertebralOrientation` is not extended.** Adding required fields to it
  would break the ~12 direct `VertebralOrientation(...)` constructions in
  `tests/test_022_stage3_serialisation.py` and
  `tests/test_122_signed_curvature.py`; adding optional ones would put `null`s
  in the schema. A second dataclass merged at the serialisation seam costs
  neither, and keeps AC11/AC12's "unchanged" claims provable.
- **`STATUS_OVERRIDES` is left untouched.** Its
  `stage3.per_label_orientations[].principal_axis[]` entry is a verbatim
  transcript of a maintainer walkthrough (item 106, 2026-07-28) and already
  flags the path for replacement by a VCS. Rewriting a recorded human call from
  inside an item is not this item's to do — the same call item 122 made. The
  demotion is carried by `FEATURE_DOCS` prose instead (AC22).
- **`features_version` is not bumped.** It stays `"0.2"`. Precedent: items 110
  and 122 both added leaf paths without bumping, and
  `test_022_stage3_serialisation.py` AC9 pins `"0.2"`.
- **The queue's quoted tangent values are pre-item-119.**
  [`queue-017.md`](../queue/queue-017.md) records `+5.7°, +5.0°, 0°, −5.0°,
  −5.7°` for `clean_control`, measured 2026-08-27 against the then-current
  interpolating fit. Under the shipped smoothing fit the same measurement is
  `+8.1644°, +4.0746°, 0.0000°, −4.0746°, −8.1644°` (2026-08-29). Every number
  in this spec is the post-119 measurement; the queue's are not errata to fix,
  they simply predate the fit change item 119 landed.
- **`principal_axis` is not *exactly* constant everywhere.** The queue says it
  returns "exactly `(1.000, 0.000, 0.000)` for every vertebra of the default
  fixture", which is true of the default fixture and of six other cases, but
  `mode3_inject_islands` and `mode8_force_overlap` perturb it (still within
  `0.996` of the same axis). AC10 states the precise version so the test can be
  written without discovering the exception at implementation time.
- **RAS axis identity is a precondition, not a check.** A caller that
  hand-builds `LabelCentroid`s (as the unit tests do) is responsible for
  supplying RAS-ordered mm coordinates. The feature does not, and cannot,
  verify this.
- **No human gate blocks this item, and none is raised.**
  [`progress.md`](../progress.md)'s `## Human gates` table records the spinal
  curve model gate as **✅ Approved (2026-08-27)** with `Blocks: 119, 120, 121,
  123, 125`. It is resolved, so item 121 is released. This item adds no gate row
  and makes no edit to `progress.md`.

## Implementation Steps

1. **`src/segfacet/features/orientation.py`** — add a third part alongside
   Part A (PCA) and Part B (curvature); neither existing part changes.
   1. Add the frozen dataclass `VertebralTangentOrientation` with fields
      `label`, `level_name`, `closest_u`, `tangent`, `coronal_deg`,
      `sagittal_deg`. Its docstring states the proxy status, the not-a-VCS
      scope fence, the sign convention per plane, and the RAS precondition
      (AC21).
   2. Add `compute_vertebra_tangent_orientations(fit, centroids,
      spacing_mm=None, *, backend=None) -> List[VertebralTangentOrientation]`:
      call the public `compute_spline_offsets(centroids, fit, backend=backend)`
      for each centroid's `closest_u`; evaluate
      `evaluate_spline_derivative(fit, closest_us, nu=1)`; normalise to unit
      length reusing the existing `norm < 1e-12` guard idiom; apply the global
      cranial direction normalisation; then `degrees(atan2(t[0], t[2]))` and
      `degrees(atan2(t[1], t[2]))` per record, **without** `np.unwrap`. Raise
      `ValueError` on an empty centroid sequence, matching the module's other
      entry points.
   3. Extend the module docstring's Public API list and add the new part's
      paragraph.
2. **`src/segfacet/feature_report.py`**
   1. `orientation_to_dict(o, tangent=None)` — when `tangent` is given, emit
      the four extra keys (`float()` for the scalars, a list of `float` for
      `spline_tangent`); when `None`, emit exactly today's four keys.
   2. `build_features_block(..., tangent_orientations=None, ...)` — when
      supplied, index the tangent records by `label`, validate that the label
      set matches `orientations`' (raise `ValueError` naming the offenders
      otherwise, AC16), and pass the matching record into
      `orientation_to_dict` while keeping the existing ascending-label sort.
      Do not mutate either input sequence.
3. **`src/segfacet/report_schema_v0.json`** — add the four keys to
   `stage3OrientationEntry.properties` (leaving `required` alone), with
   descriptions naming the plane and the sign. `additionalProperties: false`
   means skipping this step fails every schema-validating test in the suite.
4. **`src/segfacet/pipeline.py`** — in the `len(labels) >= 2` branch, add
   `"tangent_orientations": compute_vertebra_tangent_orientations(fit,
   ordered_centroids)` to `stage3_kwargs`, importing it beside the existing
   `compute_vertebra_orientations` import. This is the only pipeline change.
5. **`src/segfacet/feature_docs.py`** — add a `FeatureDoc` for each of the four
   new leaf paths (AC20/AC21), amend the `principal_axis[]` entry's text for
   the demotion (AC22), and extend the `"Orientation & Curvature"` block
   description, which currently says only "Per-vertebra orientation (PCA of the
   mean-centred, spacing-scaled voxel cloud) …". `STATUS_OVERRIDES`,
   `MODE_ANCHOR_PATHS`, `BLOCK_OWNERS` and `PATH_ALIASES` are not touched.
6. **Regenerate the generated catalogue**:
   `.venv/bin/python -m segfacet.catalogue`.
7. **Regenerate the corpus goldens**:
   `.venv/bin/python -m segfacet.synth.golden`.
8. **Update the two hardcoded leaf counts** (AC25): the constant in
   `tests/test_103_feature_catalogue.py`, and the nine `22/89 leaf paths
   unwired` cells in `docs/aide/golden-decision-table.md`, plus a new dated
   paragraph in that file recording the re-measurement — appended after the
   item-122 paragraph, never overwriting it.
9. **Run the [Validation](#validation) diffs** before committing.

## Authorised paths

**May change:**

- `src/segfacet/features/orientation.py` — the new dataclass, the new compute
  function, and the module docstring. Part A (`VertebralOrientation`,
  `compute_vertebra_orientations`, `_pca_principal_axis`) and Part B
  (`SpineCurvature`, `compute_spine_curvature`, `_signed_plane_angles_deg`,
  `_sweep`) must not change.
- `src/segfacet/feature_report.py` — `orientation_to_dict` and
  `build_features_block`'s orientation branch only.
- `src/segfacet/report_schema_v0.json` — the `stage3OrientationEntry`
  definition only.
- `src/segfacet/pipeline.py` — the one added `stage3_kwargs` entry and its
  import.
- `src/segfacet/feature_docs.py` — `FEATURE_DOCS` entries for the four new
  paths, the amended `principal_axis[]` entry, and the "Orientation &
  Curvature" block description. `STATUS_OVERRIDES`, `MODE_ANCHOR_PATHS`,
  `BLOCK_OWNERS` and `PATH_ALIASES` must not change.
- `docs/aide/feature_catalogue.generated.json` — regenerated, never
  hand-edited.
- `docs/aide/feature_catalogue.generated.md` — regenerated, never hand-edited.
- `tests/corpus/golden/*.json` — the nine goldens, regenerated via
  `python -m segfacet.synth.golden`, never hand-edited. Listed here rather than
  under **Asserts against** even though AC10 and AC12 read their
  `principal_axis` and `eigenvalue_ratio` values: this item rewrites the files,
  so the "those two values did not move" requirement is carried by AC12's
  fresh-vs-committed equality and by the [Validation](#validation) diff, not by
  a read-only pin the same item contradicts.
- `tests/test_103_feature_catalogue.py` — the hardcoded `clean_control`
  leaf-path count only, a direct mechanical consequence of adding four leaves.
- `docs/aide/golden-decision-table.md` — the nine Group-A rows'
  `N/M leaf paths unwired` evidence cells and a new dated re-measurement
  paragraph. No judgement column (disposition, rationale, replacement
  guarantee) and no earlier dated paragraph may change.
- `tests/test_121_tangent_orientation.py` — the new test module.
- `tests/corpus/119_pre_119_digests.json` — the
  `catalogue_leaf_path_set_sha256` value only, bumped to the post-121
  leaf-path set. See [Decisions](#decisions--trade-offs).
- `docs/aide/items/121-tangent-based-vertebra-orientation.md` — this spec.
- `docs/aide/insights.md` — one-line out-of-scope captures only.

**Asserts against:**

- `src/segfacet/features/spline_offset.py` — read, not changed. AC3 pins
  `compute_spline_offsets`'s `closest_u` as this item's source of the closest
  point; item 120's held-out estimator is not used and not touched.
- `src/segfacet/features/spline.py` — read, not changed. AC4 pins
  `evaluate_spline_derivative`'s `nu=1` output as the tangent.
- `tests/golden/022_stage3_report.json` — pinned **byte-unchanged**. It is
  produced by `test_022`'s `_full_block_for_spine`, which passes no
  `tangent_orientations`; if it moves, `build_features_block`'s new parameter
  is not optional as AC17 requires.
- `src/segfacet/reference/reference_default.json` and
  `src/segfacet/reference/reference_verse_v1.json` — pinned byte-unchanged.
  `reference/ingest.py` reads only `eigenvalue_ratio` out of the orientation
  block, which AC12 pins unmoved; if either artifact moves, this item has
  exceeded its scope.
- `src/segfacet/reference/ingest.py` and `src/segfacet/reference/delta.py` —
  read, not changed; they name `eigenvalue_ratio` explicitly and must remain
  blind to the new keys.
- `tests/test_019_vertebra_orientation_curvature.py` — must stay green
  **unmodified** (AC11: Part A is untouched).
- `tests/test_022_stage3_serialisation.py` — must stay green **unmodified**
  (AC17: the new `build_features_block` parameter is optional).
- `tests/test_122_signed_curvature.py` — must stay green **unmodified**
  (Part B is untouched).
- `tests/test_120_leave_one_out_offset.py` — must stay green **unmodified**
  (`spline_offset.py` is untouched).
- `tests/test_042_golden_determinism.py`,
  `tests/test_089_fov_aware_coverage_border.py`,
  `tests/test_090_reference_derived_defaults.py`,
  `tests/test_094_tptbox_image_layer.py`,
  `tests/test_098_stray_components.py` — pin the nine regenerated goldens
  against fresh builds (AC24).
- `tests/test_104_feature_catalogue_drift.py` — pins the regenerated catalogue
  against the realised record shape and `FEATURE_DOCS` (AC23).
- `tests/test_105_golden_decision_table.py` — its AC7 recomputes the
  `N/M leaf paths unwired` fraction live and pins the updated cells (AC25).
- `tests/test_111_golden_guard.py` — pins the `.gitattributes` LF coverage of
  both golden sets; regeneration must not disturb it.
- `.gitattributes` — read, not changed: every file this item regenerates is
  already pinned (`tests/corpus/golden/*.json`,
  `docs/aide/feature_catalogue.generated.{json,md}`,
  `docs/aide/golden-decision-table.md`, `src/segfacet/**/*.json`).

## Testing Strategy

New module: **`tests/test_121_tangent_orientation.py`**, one focused test per
AC, built on hand-constructed `LabelCentroid` sequences in the style of
`tests/test_019_vertebra_orientation_curvature.py` and
`tests/test_122_signed_curvature.py` (RAS-ordered mm coordinates supplied
directly — see Assumptions), plus the committed corpus for AC5, AC10, AC12,
AC19 and AC24.

**Fixtures, with the values measured while specifying this item** (2026-08-29,
under the shipped item-119 fit, `fit_centroid_spline` defaults):

| Fixture | Recipe | coronal angles (deg) | sagittal angles (deg) |
|---|---|---|---|
| straight | 5 centroids, `(0, 0, 10·i)` | all `0.0` | all `0.0` |
| coronal C | 7 centroids, `(30·sin(π·i/6), 0, 15·i)` | `+57.9714 … −57.9714` (spread `115.9428`) | all `0.0` |
| sagittal C | 7 centroids, `(0, 30·sin(π·i/6), 15·i)` | all `0.0` | `+57.9714 … −57.9714` |
| two-centroid | `(0,0,0)`, `(5,0,20)` | both `+14.0362` | both `0.0` |
| `clean_control` (corpus) | committed fixture | `+8.1644, +4.0746, 0.0000, −4.0746, −8.1644` | all `0.0` |

**Adversarial and edge cases:**

- Two centroids (the minimum `fit_centroid_spline` accepts) — two records, both
  finite, no exception; measured `+14.0362°` coronal at both.
- Empty centroid sequence — `ValueError`, matching the module's other entry
  points.
- A doubling-back sequence in the shape of `mode4_relabel_swap`, whose curve
  reverses direction: every angle stays inside `(−180, 180]` (measured
  `+3.2953, −177.6783, −92.5552, −1.5354, −20.3216` coronal), no exception, no
  NaN. Contrast asserted against `stage3.curvature.coronal_tangent_angles_deg`
  for the same case, which is unwrapped and leaves that range — the two
  conventions are deliberately different and the test says so.
- A degenerate near-zero tangent — exercises the `norm < 1e-12` guard; the
  angles must be finite.
- All centroids coincident — the `ValueError`
  `fit_centroid_spline` already raises for an exactly-coincident pair
  propagates unchanged; no `ZeroDivisionError` and no NaN reaches the caller.
- Anisotropic mm spacing (large z step) on a straight spine — both angle
  arrays still `0.0`.
- Determinism: two calls on the same input return equal values for every
  numeric field.
- Immutability: `VertebralTangentOrientation` is frozen; assignment raises.
  `build_features_block` does not mutate the `tangent_orientations` sequence it
  is given (mirrors `test_022`'s AC10 pattern).
- Merge robustness: `tangent_orientations` supplied in descending-label order
  still merges correctly (AC15); a missing or extra label raises (AC16).
- Schema: a report carrying the four keys validates; one carrying a fifth,
  misspelt key fails — proving `additionalProperties: false` is load-bearing
  (AC18).

**Existing tests to reconcile** (swept 2026-08-29; each verdict checked against
the design above before this spec was written):

| Test | Verdict |
|---|---|
| `test_019_vertebra_orientation_curvature.py` (whole module) | **Green unchanged** — Part A's dataclass, signature and values are untouched (AC11). |
| `test_022_stage3_serialisation.py` (whole module) | **Green unchanged** — its ~12 direct `VertebralOrientation(...)` constructions keep their 4 keyword args; its AC2 orientation-key checks are `in`-style and additive-safe; `_full_block_for_spine` passes no tangents, so its AC8 golden is byte-unchanged. |
| `test_122_signed_curvature.py` | **Green unchanged** — Part B untouched; its own `VertebralOrientation(...)` construction is unaffected. |
| `test_120_leave_one_out_offset.py` | **Green unchanged** — `spline_offset.py` is untouched. |
| `test_042_golden_determinism.py` (nine cases) | **Red until step 7** — `reports_close` compares key **sets** exactly, so it fails on the four added keys alone. |
| `test_089`, `test_090` (AC15), `test_094` (AC7), `test_098` (AC14–AC16) | **Red until step 7** — all compare a fresh build against the committed goldens. |
| `test_103_feature_catalogue.py` AC4 (`len(paths) == 89`) | **Red until step 8** — becomes `93`. |
| `test_104_feature_catalogue_drift.py` | **Red until steps 5–6** — the four new realised paths are undocumented and absent from the committed artifact. |
| `test_105_golden_decision_table.py` AC7 | **Red until step 8** — it recomputes `N/M leaf paths unwired` live; `22/89` becomes `26/93`. |
| Every schema-validating module (33 modules reach `serialize_report`) | **Red until step 3** — `stage3OrientationEntry` sets `additionalProperties: false`. |
| `test_111_golden_guard.py` | **Green unchanged** — every regenerated path is already pinned in `.gitattributes`. |
| `test_063_reference_intensity.py`, `test_081_*`, `test_082_verse_build_recipe.py` | **Green unchanged** — they compare rebuilt reference artifacts against the committed ones, and `ingest.py` reads only `eigenvalue_ratio`, which AC12 pins unmoved. |

## Validation

Beyond the suite, three observations. The second and third are AC26's only
verification and the validator must **execute** them, not infer them.

1. **The estimate varies where PCA does not, in a real report.** Regenerate
   into a scratch directory:

   ```
   .venv/bin/python -m segfacet.synth.golden --out out/goldens-121
   ```

   then inspect `out/goldens-121/clean_control.json` at
   `features.stage3.per_label_orientations`: all five entries carry
   `principal_axis` `[1.0, 0.0, 0.0]` and `eigenvalue_ratio`
   `1.4407051282051282`, while `spline_tangent_coronal_deg` reads
   `+8.1644, +4.0746, 0.0000, −4.0746, −8.1644` and
   `spline_tangent_sagittal_deg` is `0.0` throughout — the constant feature and
   its varying replacement, side by side in one block.

2. **The regeneration is narrow (AC26).** With the work committed on the item
   branch:

   ```
   git diff aide/queue-017 -- tests/corpus/golden
   ```

   Every changed hunk must be an *addition* of one of the four new keys inside
   a `per_label_orientations` entry. Any changed line naming a verdict, a
   finding, a threshold, `principal_axis`, `eigenvalue_ratio`, `per_label`,
   `overlaps`, `relationships`, `per_label_offsets`, `curvature`,
   `spacing_consistency`, `monotonic_consistency`, `per_label_neighbourhood` or
   an intensity key means this item has moved something it does not own — hand
   back rather than committing it.

3. **Nothing outside the declared scope moved.**

   ```
   git diff aide/queue-017 --stat
   ```

   must list no file outside the **May change** list, and in particular no
   path under `src/segfacet/reference/`, no `tests/golden/022_stage3_report.json`,
   and no `src/segfacet/features/spline_offset.py`.

No `[validation]` environment profile is required: all three checks run on the
committed corpus with the default CPU install.

## Dependencies

- **Item 018** (✅) — provides `compute_spline_offsets` and its `closest_u`,
  the closest-point half of this estimate.
- **Item 019** (✅) — provides `VertebralOrientation`,
  `compute_vertebra_orientations` and the PCA `principal_axis` this item
  demotes and pins.
- **Item 022** (✅) — provides `orientation_to_dict`,
  `build_features_block`'s `orientations` parameter, the `stage3` block and the
  `report_schema_v0.json` `stage3OrientationEntry` definition.
- **Item 042** and **item 078** (✅) — provide `write_goldens`,
  `check_case_golden` and the numeric-tolerance comparison the regeneration is
  judged by.
- **Item 103**, **item 104** and **item 105** (✅) — provide `FEATURE_DOCS`,
  the generated catalogue, its drift test, and the golden-decision-table's
  live-recomputed leaf-count evidence.
- **Item 116** (✅) — the RAS-native synthetic corpus, which is what makes the
  coronal/sagittal plane statement true of the committed fixtures.
- **Item 119** (✅) — the shipped smoothing fit. Every measured value in this
  spec is taken against it; under the retired interpolating fit the numbers
  differ (see Assumptions).
- **Item 120** (✅) — established the RAS axis contract for direction
  components and the held-out offset. This item deliberately does **not** use
  the held-out refits (see Assumptions) and leaves `spline_offset.py`
  untouched.
- **Item 122** (✅) — established the signed-angle convention, the direction
  normalisation rule and the RAS plane statement this item reuses, and shares
  `features/orientation.py`.

**Downstream:** item 123 regenerates the same goldens after its recalibration
and will find them already carrying these keys; item 124's observed-range
column picks up the four new leaf paths automatically and is the instrument
that would have caught `principal_axis`'s constancy; item 125 replays the stage
end-to-end.

## Decisions & Trade-offs

Three questions determine this item's shape. All three are settled here rather
than left to the builder, because the obvious answer is wrong in each case.

### Where does the closest point come from?

**Decision: call the public `compute_spline_offsets(centroids, fit)` and read
its `closest_u`.**

The obvious alternative is to promote `spline_offset._find_closest_u` to a
public helper and call that directly, which avoids computing offsets this item
discards. It was rejected: the dominant cost either way is the same coarse scan
plus `minimize_scalar` refinement, so the saving is a handful of subtractions;
and promoting a private name means editing `spline_offset.py`, which item 120
has just reworked. Keeping that file in **Asserts against** rather than **May
change** makes "item 120's estimator is untouched" provable from the diff
instead of arguable from a review. The discarded offset values are the price of
that proof and it is a low one.

### Wrapped angles here, unwrapped angles in `stage3.curvature`

**Decision: this item's angles are wrapped to `(−180, 180]`; item 122's stay
unwrapped.** The same `atan2` quantity, two conventions, deliberately.

Item 122 unwraps because its arrays are reduced to a **sweep** (`max − min`)
along the ordered sequence, and a sweep is only meaningful on a continuous
accumulation — `mode4_relabel_swap`'s coronal sweep reads `180.8804°` wrapped
against `355.3172°` unwrapped, and the latter is the honest accumulated
turning.

This item's angles are read **one vertebra at a time**. An unwrapped `+355°`
tilt is not an orientation any consumer can use: it is a statement about the
path taken to reach that vertebra, which is exactly what a per-vertebra
descriptor must not depend on. Unwrapping would also make each vertebra's value
depend on every preceding vertebra's, defeating AC6's traversal invariance in
the only cases where it matters. The two conventions are documented against
each other in `FEATURE_DOCS` so a reader comparing
`spline_tangent_coronal_deg` with `curvature.coronal_tangent_angles_deg` on the
same case is not surprised by the difference.

### Demote, do not delete — and demote in prose, not in `STATUS_OVERRIDES`

**Decision: `principal_axis` keeps its key, its computation and its schema
entry; only its documentation changes.**

Deleting it was never on the table — the queue says demote — but the reason is
worth recording: it is not *wrong*, it is *uninformative on this corpus*. It
genuinely reports the voxel cloud's widest axis, and on real GT that axis is
genuinely left-right. What it cannot do is discriminate between vertebrae,
which is what a per-vertebra feature is for. `eigenvalue_ratio`, computed from
the same PCA, is the counter-example that proves the distinction is about the
feature and not about PCA: it carries CoV `0.133` at L1 across 59 real subjects
and moves under fragmentation and overlap on the synthetic corpus, so it is
retained untouched.

The demotion goes in `FEATURE_DOCS` and not in `STATUS_OVERRIDES` because that
mapping is a verbatim transcript of a maintainer walkthrough (item 106,
2026-07-28) — the same call item 122 made about the same file. Its existing
`principal_axis[]` entry already flags the path for replacement by a vertebral
coordinate system, and this item's estimate is explicitly **not** a VCS
(AC21), so it does not discharge that entry and must not edit it.

### Who regenerates the goldens this item invalidates?

**Decision: item 121 regenerates them, here, and merges on a green suite.**

[`queue-017.md`](../queue/queue-017.md) assigns artifact regeneration to item
123, and item 119 was told to leave the corpus red for 123 to clear. That
instruction was about the **fit** change, whose blast radius spans thresholds
and both reference artifacts. This item's delta is four added keys inside one
block, fully determined by this item alone. Under this repo's
`[git] mode = "auto-merge"` the validator runs the full suite before merging,
so an item that leaves nine golden tests, the catalogue drift test, the
decision-table test and every schema-validating module red cannot merge at all.
Item 120 already regenerated the goldens within this queue on the same
reasoning. It pre-empts nothing: item 123 regenerates the same files again and
will simply find them already carrying these keys.

### The pre-119 leaf-path digest is not exempt from a leaf-count change

**Decision: bump `tests/corpus/119_pre_119_digests.json`'s
`catalogue_leaf_path_set_sha256` from the pre-121 133-leaf set to the post-121
137-leaf set, here, in this item.**

`test_119_curve_formulation.py::test_ac27_catalogue_leaf_path_set_unchanged_from_pre_119`
and `test_120_leave_one_out_offset.py::test_ac12_catalogue_leaf_path_set_unchanged_from_pre_119`
both hash the catalogue's sorted leaf-`path` set and compare it against this
one committed digest — a discriminator written to prove items 119 and 120 add
and remove no feature path. This item's Testing Strategy table (row
`test_120_leave_one_out_offset.py`, "**Green unchanged** — `spline_offset.py`
is untouched") missed that these two tests do not exercise
`spline_offset.py` at all: they read the live catalogue and compare it to a
static fixture, so any later item that legitimately grows the leaf-path count
— as this one does, by four (133 leaves pre-121, 137 post-121) — turns both
tests red with no code defect involved. The fixture is not a golden of
*this* item's output; it is a trip-wire calibrated once, upstream of every
item that can move the catalogue. Any item that adds or removes a leaf path
must recompute and commit this digest alongside its own change, the same way
it regenerates `feature_catalogue.generated.json`. Recomputation is
mechanical: rerun `segfacet.catalogue.main`, take the sorted leaf `path`
values, sha256 the newline-joined list.

### Implementation note (2026-08-29)

Implemented per the spec's three Decisions with no deviations: `closest_u`
comes from the public `compute_spline_offsets(centroids, fit)` (`spline_offset.py`
untouched), angles are wrapped via plain `atan2`→`degrees` with no `np.unwrap`,
and `principal_axis`'s demotion is carried entirely by its `FEATURE_DOCS` text
(`STATUS_OVERRIDES` untouched). All measured values matched the spec's
Testing Strategy table exactly on first computation, including the AC5
`clean_control` spread (`16.3287°`), AC8/AC9's C-curve angles, and the
regenerated goldens' `26/93 leaf paths unwired` (AC25).
