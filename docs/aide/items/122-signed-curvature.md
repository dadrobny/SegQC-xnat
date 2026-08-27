# Item 122 — Signed curvature

> **Created:** 2026-08-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 122
> **Objectives:** G7 (evaluable & regression-testable — a descriptor that
> measures what it is documented to measure); G2 indirectly (the descriptor is
> a candidate rule input that today cannot separate a normal spine from a
> straight one)
> **Suggested branch:** `aide/122-signed-curvature`

---

## Description

`stage3.curvature.total_curvature_deg` is documented as a "Cobb-angle-like
global curvature proxy" and computed as `max − min` of `tangent_angles_deg`,
which is the **unsigned** angle `acos(t_S)` between each unit tangent and the
cranio-caudal axis. Because the angle carries no sign, opposing curvature
cancels:

- On `clean_control` the descriptor reports **5.7017°** where the true L1→L5
  tangent sweep is **11.4034°** — the sum of `inter_tangent_angles_deg`, which
  the same function already computes correctly. It halves every C-curve.
- On a **balanced double curve** — the shape a normal spine actually has — it
  collapses entirely. Measured on a 4-level symmetric S fixture (20 mm
  amplitude, 170 mm span, sampled at the odd eighths of one sine period), the
  current descriptor reads **0.0900°**, which is *below* item 019 AC5's
  straight-spine pass bound of `1.0°`. A genuine S-curve is therefore
  indistinguishable from a straight column, which is precisely the claim the
  "Cobb-like proxy" documentation makes and cannot honour.

This item gives the descriptor a **sign convention** and a **stated plane**, so
opposing curvature no longer cancels and every number says which anatomical
plane it refers to. The two planes are separated because they carry different
signal: on `mode6_crop_at_border` the sagittal sweep is **70.78°** against a
coronal **11.75°**, while the single unsigned aggregate reports **35.67°** and
attributes it to nothing.

The descriptor is replaced rather than duplicated, and the artifacts it
invalidates are regenerated **here** — both decisions are argued from measured
consequences in [Decisions & Trade-offs](#decisions--trade-offs).

**Independent of the human gate.** [`progress.md`](../progress.md)'s
`## Human gates` table names item 122 as explicitly *released* from the spinal
curve model gate: the defect is in how tangents are reduced to a scalar, not in
the fit. This item changes **no** spline fit, **no** `HeuristicConfig`
threshold, **no** rule, and **neither** reference artifact — none of them read
`stage3.curvature` (verified: a `curvature` grep over
`src/segfacet/reference/`, `src/segfacet/heuristics/` and
`src/segfacet/human_report.py` returns nothing).

**What this item is NOT.** It does not touch `VertebralOrientation`,
`compute_vertebra_orientations`, or `stage3.per_label_orientations[]` — Part A
of `features/orientation.py`. That is a separate deliverable and this item must
leave it byte-unchanged. It does not decompose `tangent_angles_deg[]` or
`inter_tangent_angles_deg[]`, which keep their present meaning and values. It
does not recalibrate any threshold, rebuild `reference_default.json` /
`reference_verse_v1.json`, or wire the descriptor into a rule.

### The replacement descriptor

Given the ordered unit tangents `t` already computed by
`compute_spine_curvature`, and the RAS axis identity guaranteed by
`io.load_volume` (axis 0 = **R**ight, 1 = **A**nterior, 2 = **S**uperior):

1. **Direction normalisation.** If the sequence's net advance is caudal
   (`centroid_mm[-1][2] - centroid_mm[0][2] < 0`), negate every tangent. The
   descriptor then measures tilt relative to the *cranio-caudal* axis
   regardless of whether the caller supplied the sequence cranial-first or
   caudal-first.
2. **Signed in-plane angles**, per centroid, in degrees:
   - coronal (the **R–S** plane): `degrees(atan2(t_R, t_S))` — positive means
     the tangent tilts toward the patient's **right** as the spine advances
     cranially,
   - sagittal (the **A–S** plane): `degrees(atan2(t_A, t_S))` — positive means
     it tilts **anterior**.
3. **Unwrap** each angle sequence along the spine (`np.unwrap` on radians)
   before it is stored, so a tangent crossing the −S direction does not produce
   a ±360° discontinuity. This matters on real inputs:
   `mode4_relabel_swap`'s curve doubles back, and its raw wrapped coronal sweep
   reads `180.8804°` against an unwrapped `355.3172°` — the latter is the
   honest accumulated turning.
4. **Per-plane sweep** = `max − min` of that plane's unwrapped angle array.
5. **`total_curvature_deg`** is redefined as
   `max(coronal_curvature_deg, sagittal_curvature_deg)` — the sweep in the
   plane the spine turns in most — and `curvature_plane` names which one.

## Acceptance Criteria

- [ ] **AC1: Signed coronal angle array exists, one entry per centroid.**
  `SpineCurvature.coronal_tangent_angles_deg` is a `Tuple[float, ...]` whose
  length equals the number of input centroids, holding the unwrapped signed
  angle `degrees(atan2(t_R, t_S))` per centroid after direction normalisation.
  On a coronal-plane C-curve its first entry is strictly positive and its last
  strictly negative (measured: `+43.8537` … `−43.8537`).

- [ ] **AC2: Signed sagittal angle array exists, one entry per centroid.**
  `SpineCurvature.sagittal_tangent_angles_deg` is a `Tuple[float, ...]` of the
  same length, holding the unwrapped signed angle `degrees(atan2(t_A, t_S))`.
  On a sagittal-plane C-curve its first entry is strictly positive and its last
  strictly negative.

- [ ] **AC3: `coronal_curvature_deg` is the coronal array's range.** For every
  fixture exercised, `coronal_curvature_deg` equals
  `max(coronal_tangent_angles_deg) - min(coronal_tangent_angles_deg)` within
  `1e-9`.

- [ ] **AC4: `sagittal_curvature_deg` is the sagittal array's range.** The same
  identity holds for the sagittal pair, within `1e-9`.

- [ ] **AC5: A C-curve's reported curvature equals its tangent sweep.** For a
  C-curve confined to the coronal plane, `coronal_curvature_deg` equals
  `sum(inter_tangent_angles_deg)` within `1e-6` degrees (measured: `87.7073`
  for both). The retired descriptor reports `43.8537` on the same fixture —
  half.

- [ ] **AC6: A coronal-plane curve reports zero sagittal curvature.** For a
  C-curve whose centroids vary only in R and S, `sagittal_curvature_deg` is
  `0.0` within `1e-9` and `coronal_curvature_deg` exceeds `20.0`.

- [ ] **AC7: A sagittal-plane curve reports zero coronal curvature.** For a
  C-curve whose centroids vary only in A and S, `coronal_curvature_deg` is
  `0.0` within `1e-9` and `sagittal_curvature_deg` exceeds `20.0` (measured:
  `0.0` and `87.7073`).

- [ ] **AC8: A symmetric S-curve is separated from a straight spine.** On the
  balanced-S fixture defined in [Testing Strategy](#testing-strategy),
  `total_curvature_deg` is at least `20.0` (measured: `53.7979`), where the
  straight fixture reports `0.0`.

- [ ] **AC9: A straight spine still reports zero.** On a straight
  cranio-caudal fixture, `total_curvature_deg` is `0.0` within `1e-9`, and so
  are both per-plane sweeps.

- [ ] **AC10: The retired formula is pinned as a regression witness.** On the
  same balanced-S fixture, the retired formula recomputed inside the test from
  the still-present unsigned array — `max(tangent_angles_deg) -
  min(tangent_angles_deg)` — is below `1.0` (measured: `0.0900`), i.e. below
  item 019 AC5's straight-spine bound, while `total_curvature_deg` on that
  fixture is above `20.0`. The test asserts both in one place so the
  cancellation defect cannot silently return.

- [ ] **AC11: `total_curvature_deg` is the larger of the two plane sweeps.**
  `total_curvature_deg` equals
  `max(coronal_curvature_deg, sagittal_curvature_deg)` within `1e-9` on every
  fixture exercised.

- [ ] **AC12: `curvature_plane` names the plane the total came from.**
  `SpineCurvature.curvature_plane` is the string `"coronal"` when
  `coronal_curvature_deg >= sagittal_curvature_deg` and `"sagittal"`
  otherwise — so an exact tie, including a straight spine's `0.0`/`0.0`,
  resolves deterministically to `"coronal"`. Asserted on a coronal C-curve
  (`"coronal"`), a sagittal C-curve (`"sagittal"`), and a straight spine
  (`"coronal"`).

- [ ] **AC13: The descriptor is invariant to traversal direction.** Reversing
  the centroid sequence leaves `coronal_curvature_deg`,
  `sagittal_curvature_deg` and `total_curvature_deg` unchanged within `1e-9`
  (verified against all nine corpus cases while specifying this item).

- [ ] **AC14: The five new keys are serialised with JSON-native types.**
  `feature_report.curvature_to_dict` emits `coronal_tangent_angles_deg` and
  `sagittal_tangent_angles_deg` as a `list` of `float`,
  `coronal_curvature_deg` and `sagittal_curvature_deg` as `float`, and
  `curvature_plane` as `str`.

- [ ] **AC15: The serialised values equal the dataclass values.** For a curved
  fixture, each of the five serialised values equals its `SpineCurvature`
  attribute exactly (lists compared element-wise), and so does
  `total_curvature_deg`.

- [ ] **AC16: The report schema admits and requires the new keys.**
  `report_schema_v0.json`'s `stage3Curvature` definition (which sets
  `additionalProperties: false`) lists all five new keys in `properties` and in
  `required`, and a Stage-3 report built by `build_features_block` validates
  against the schema without error.

- [ ] **AC17: The plane and sign convention are documented at the record
  level.** `feature_docs.FEATURE_DOCS` carries an entry for each of the five
  new leaf paths, and each entry's text names its anatomical plane
  (`"coronal"` / `"sagittal"`) and states the RAS precondition — that
  `io.load_volume` reorients every volume to `("R", "A", "S")`, which is what
  makes the axis identity, and therefore the plane statement, true.

- [ ] **AC18: The amended `total_curvature_deg` documentation no longer states
  the retired formula.** Its `FEATURE_DOCS` `computation` text names the
  per-plane maximum and no longer says `max(tangent_angles_deg) -
  min(tangent_angles_deg)`; the same holds for the key's `description` in
  `report_schema_v0.json` and for the `SpineCurvature` attribute docstring.

- [ ] **AC19: The generated feature catalogue is regenerated and drift-clean.**
  `build_catalogue(strict=True)` raises nothing, and the committed
  `docs/aide/feature_catalogue.generated.json` and `.md` contain the five new
  leaf paths, so item 104's drift test is clean in both directions.

- [ ] **AC20: Every corpus golden is regenerated and agrees with a fresh
  build.** For all nine `tests/corpus/golden/*.json`,
  `synth.golden.check_case_golden(case)` is `True` (the item-078
  numeric-tolerance comparison), and two successive `write_goldens` runs into
  different directories are byte-identical to each other.

- [ ] **AC21: The Stage-3 report golden is regenerated.**
  `tests/golden/022_stage3_report.json` matches
  `serialize_report_json(...)`'s output exactly, so
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` is green
  without that test being modified.

- [ ] **AC22: The golden regeneration is narrow.** In the ten regenerated
  files, every changed JSON leaf lies inside the `stage3.curvature` object —
  no verdict, finding, threshold, geometry, offset or intensity value moves.
  *Verified by the [Validation](#validation) section's diff command, not by
  pytest.*

## Assumptions

- **Field and key names.** The queue names the deliverable ("signed
  curvature", "state which plane each number refers to") but not the record
  shape. Assumed: `coronal_tangent_angles_deg`, `sagittal_tangent_angles_deg`,
  `coronal_curvature_deg`, `sagittal_curvature_deg`, `curvature_plane`, all
  under `stage3.curvature`, mirroring the existing `*_deg` suffix convention in
  that block.
- **Two planes, not three.** Coronal (R–S) and sagittal (A–S) only. An axial
  (R–A) tangent angle is ill-conditioned for a curve that runs nearly parallel
  to S — its `atan2` arguments are two small components whose ratio swings on
  noise — and clinical curvature is reported in the coronal and sagittal
  planes. Recorded here rather than silently omitted.
- **`total_curvature_deg` is redefined in place rather than renamed.** Nothing
  outside the record reads it (no rule, no human report, neither reference
  artifact), and the key's schema constraint `minimum: 0` still holds because a
  max of two ranges is non-negative. Keeping the key means the three existing
  item-019 assertions on it (AC5 `< 1.0` for straight, AC6 `>= 20.0` for a
  C-curve, and non-negativity) survive unmodified — see Decisions.
- **`features_version` is not bumped.** It stays `"0.2"`. Precedent: item 110
  added the whole `stage3.per_label_neighbourhood[]` block without bumping, and
  `test_022_stage3_serialisation.py` AC9 pins `"0.2"`. If the maintainer wants
  a bump it is a separate, deliberate change with its own test reconciliation.
- **`STATUS_OVERRIDES` is left untouched.** Its
  `stage3.curvature.total_curvature_deg` entry reads *"Should be expressed per
  axis component (three values) rather than as one aggregate scalar"* — a
  concern this item partly addresses. That mapping is a verbatim transcript of
  a maintainer walkthrough (item 106, 2026-07-28); rewriting a recorded human
  call from inside an item is not this item's to do. Left as-is and captured in
  `insights.md` for triage.
- **Unwrapping assumes adjacent tangents turn by less than 180°.** True of any
  anatomy and of every corpus fixture; on a pathological input it degrades to a
  different-but-finite reading, never to an error. Stated because it is the one
  place the descriptor's value depends on sampling density.
- **RAS axis identity is a precondition, not a check.** `compute_centroid`
  computes `centroid_voxel * spacing` with no affine, so the plane statement
  holds only because `io.load_volume` reorients to `("R", "A", "S")`. A caller
  that hand-builds `LabelCentroid`s (as unit tests do) is responsible for
  supplying RAS-ordered mm coordinates. The descriptor does not, and cannot,
  verify this — it is documented at the function and at the catalogue entry.
- **No human gate is raised and none blocks this item.** `progress.md`'s
  `## Human gates` table already records item 122 as released from the spinal
  curve model gate. This item adds no gate row and edits no part of
  `progress.md`.

## Implementation Steps

1. **`src/segfacet/features/orientation.py` — Part B only.**
   1. Extend `SpineCurvature` with the five new fields, appended after the
      existing three so no positional construction breaks (the only
      construction site in the repo is `compute_spine_curvature` itself, which
      already uses keywords). Document each attribute with its plane, its sign,
      its unwrapping, and the RAS precondition.
   2. In `compute_spine_curvature`, after `unit_tangents` is computed and
      before the existing angle block: derive the traversal direction from the
      first and last `centroid_mm[2]` and negate `unit_tangents` when the net
      advance is caudal. Use the normalised tangents **only** for the new
      signed arrays — `tangent_angles_deg` and `inter_tangent_angles_deg` keep
      their current values, both of which are invariant to a global sign flip
      anyway; assert that in the tests rather than assuming it.
   3. Add a private helper `_signed_plane_angles_deg(unit_tangents, axis)`
      returning the unwrapped `degrees(atan2(t[:, axis], t[:, 2]))` array, and
      a private `_sweep(angles)` returning `max - min` (`0.0` for a
      single-element array).
   4. Replace the `total_curvature_deg` line with the per-plane maximum, and
      set `curvature_plane` with the documented `>=` tie-break.
   5. Update the module docstring's "Part B" paragraph, which currently
      describes "a Cobb-like total curvature scalar".
2. **`src/segfacet/feature_report.py`** — extend `curvature_to_dict` with the
   five keys (lists for the arrays, `float()`/`str()` for the scalars) and
   update its docstring.
3. **`src/segfacet/report_schema_v0.json`** — add the five keys to
   `stage3Curvature.properties` and `stage3Curvature.required`, with
   descriptions naming the plane and the sign, and amend
   `total_curvature_deg`'s description. `additionalProperties: false` means
   skipping this step fails every schema-validating test in the suite, not just
   the curvature ones.
4. **`src/segfacet/feature_docs.py`** — add a `FeatureDoc` for each of the five
   new leaf paths and amend `stage3.curvature.total_curvature_deg`'s. Each new
   entry names its plane and the RAS precondition (AC17).
5. **Regenerate the generated catalogue**:
   `.venv/bin/python -m segfacet.catalogue` (writes
   `docs/aide/feature_catalogue.generated.json` and `.md`; both are already
   pinned `text eol=lf` in `.gitattributes`).
6. **Regenerate the corpus goldens**:
   `.venv/bin/python -m segfacet.synth.golden` (the one-command path; it writes
   canonical JSON bytes with `write_bytes`, so the LF pin on
   `tests/corpus/golden/*.json` holds).
7. **Regenerate `tests/golden/022_stage3_report.json`** by writing the
   `produced` text from `test_ac8_golden_snapshot` to that path — the test
   deliberately no longer self-heals (item 111). Write bytes with `\n`, never
   `write_text`.
8. **Run the diff audit** in [Validation](#validation) before committing.

## Authorised paths

**May change:**

- `src/segfacet/features/orientation.py` — the descriptor itself. Part B only
  (`SpineCurvature`, `compute_spine_curvature`, their helpers and the module
  docstring's Part B paragraph); Part A (`VertebralOrientation`,
  `compute_vertebra_orientations`, `_pca_principal_axis`) must not change.
- `src/segfacet/feature_report.py` — `curvature_to_dict` only.
- `src/segfacet/report_schema_v0.json` — the `stage3Curvature` definition only.
- `src/segfacet/feature_docs.py` — `FEATURE_DOCS` entries for the five new
  paths and the amended `total_curvature_deg` entry. `STATUS_OVERRIDES`,
  `MODE_ANCHOR_PATHS` and every other mapping must not change.
- `docs/aide/feature_catalogue.generated.json` — regenerated, never hand-edited.
- `docs/aide/feature_catalogue.generated.md` — regenerated, never hand-edited.
- `tests/corpus/golden/*.json` — the nine goldens, regenerated via
  `python -m segfacet.synth.golden`, never hand-edited.
- `tests/golden/022_stage3_report.json` — regenerated from the test's
  `produced` text, never hand-edited.
- `tests/test_122_signed_curvature.py` — the new test module.
- `tests/test_103_feature_catalogue.py` — the hardcoded `clean_control`
  leaf-path count, a direct mechanical consequence of adding five new leaves
  under `stage3.curvature` (84 → 89).
- `docs/aide/golden-decision-table.md` — the nine Group-A rows' measured
  `N/M leaf paths unwired` evidence cells and the narrative sentence quoting
  them, a direct mechanical consequence of the same leaf-count change; no
  judgement column (disposition, rationale, replacement guarantee) may change.
- `docs/aide/items/122-signed-curvature.md` — this spec.
- `docs/aide/insights.md` — one-line out-of-scope captures only.

**Asserts against:**

- `tests/test_019_vertebra_orientation_curvature.py` — must stay green
  **unmodified**. Its AC5 (`total_curvature_deg < 1.0` for a straight spine),
  AC6 (`>= 20.0` for a C-curve) and `test_adv_total_curvature_non_negative` all
  survive the redefinition; a builder that needs to weaken any of them has
  built the wrong thing and must hand back.
- `tests/test_022_stage3_serialisation.py` — must stay green **unmodified**.
  Its curvature key checks are `in`-style and additive-safe, its AC9 pins
  `features_version == "0.2"`, and its AC8 golden test is satisfied by
  regenerating the golden file, not by editing the test.
- `tests/test_042_golden_determinism.py` — pins the nine regenerated corpus
  goldens against fresh builds (AC20).
- `tests/test_104_feature_catalogue_drift.py` — pins the regenerated catalogue
  against the realised record shape and `FEATURE_DOCS` (AC19).
- `tests/test_111_golden_guard.py` — pins the `.gitattributes` LF coverage of
  both golden sets; regeneration must not disturb it.
- `.gitattributes` — read, not changed: every file this item regenerates is
  already pinned (`tests/corpus/golden/*.json`, `tests/golden/*.json`,
  `docs/aide/feature_catalogue.generated.{json,md}`, `src/segfacet/**/*.json`).
- `src/segfacet/reference/reference_default.json` and
  `src/segfacet/reference/reference_verse_v1.json` — pinned unchanged. Neither
  carries any `stage3.curvature` key; if either moves, this item has exceeded
  its scope.

## Testing Strategy

New module: **`tests/test_122_signed_curvature.py`**, one focused test per AC,
built on hand-constructed `LabelCentroid` sequences in the style of
`tests/test_019_vertebra_orientation_curvature.py` (RAS-ordered mm coordinates
supplied directly — see Assumptions).

**Fixtures, with the values measured while specifying this item** (all
deterministic, using `fit_centroid_spline`'s defaults):

| Fixture | Recipe | Retired `total` | New coronal | New sagittal |
|---|---|---|---|---|
| straight | 5 centroids, `(0, 0, 10·i)` | `0.0000` | `0.0000` | `0.0000` |
| coronal C | 7 centroids, `(30·sin(π·i/6), 0, 15·i)` | `43.8537` | `87.7073` | `0.0000` |
| sagittal C | 7 centroids, `(0, 30·sin(π·i/6), 15·i)` | `43.8537` | `0.0000` | `87.7073` |
| balanced S | 4 centroids at `f = (2i+1)/8`: `(20·sin(2πf), 0, 170·f)` | `0.0900` | `53.7979` | `0.0000` |

The balanced-S recipe is chosen deliberately: it is the case where the retired
formula reads `0.0900°`, *below* item 019 AC5's `1.0°` straight-spine bound, so
AC8 and AC10 together demonstrate the defect and its fix on one input rather
than asserting a merely-different number.

**Adversarial and edge cases:**

- Two centroids (the documented minimum) — both arrays length 2, both sweeps
  finite, no exception.
- Fewer than two centroids — the existing `ValueError` is unchanged.
- All centroids coincident (zero chord length) — finite values, no
  `ZeroDivisionError`, no NaN.
- A degenerate near-zero tangent — exercises the existing `norm < 1e-12` guard;
  the signed angles must be finite.
- A doubling-back sequence in the shape of `mode4_relabel_swap` — asserts the
  unwrap branch: the sweep is finite and non-negative, and is **not** clipped at
  180° (the unwrapped coronal reading for that case is `355.3172°` against a
  wrapped `180.8804°`).
- Anisotropic mm spacing (large z step) on a straight spine — sweeps still
  `0.0`.
- Determinism: two calls on the same input return equal values for all six
  numeric fields and the plane string.
- Immutability: `SpineCurvature` stays frozen; assigning any new field raises.
- Invariance of the retained arrays: `tangent_angles_deg` and
  `inter_tangent_angles_deg` are unchanged by the direction normalisation
  (assert them equal to the values computed without it, on a caudal-first
  sequence).
- Schema round-trip: a full Stage-3 features block serialises and validates
  (AC16), and a block with one new key removed fails validation — proving
  `required` is load-bearing.

**Existing tests to reconcile** (swept 2026-08-27; each verified against the
proposed descriptor before this spec was written):

| Test | Verdict |
|---|---|
| `test_019::test_ac5_*` (3 tests, `total < 1.0` for straight) | **Green unchanged** — the straight fixture reports `0.0`. |
| `test_019::test_ac6_*` (3 tests, `total >= 20.0` for a C-curve) | **Green unchanged** — the C-curve value *rises* from `43.8537` to `87.7073`. |
| `test_019::test_adv_total_curvature_non_negative` | **Green unchanged** — a max of two ranges is non-negative, and the fixtures it uses are straight and C-curve. |
| `test_019::test_spine_curvature_has_required_fields`, `test_spine_curvature_is_frozen`, the determinism, finite and anisotropic adversarial tests | **Green unchanged** — `hasattr`/`in`-style, additive-safe. |
| `test_022::test_ac2_curvature_has_required_keys` | **Green unchanged** — iterates three named keys, does not compare key sets. |
| `test_022::test_adv_total_curvature_non_negative` | **Green unchanged** — straight-spine fixture, and the value is non-negative by construction. |
| `test_022::test_ac9_features_version_is_02_*` | **Green unchanged** — `features_version` is deliberately not bumped. |
| `test_022::test_ac8_golden_snapshot` | **Red until step 7** — strict text equality against `tests/golden/022_stage3_report.json`. Fixed by regenerating the golden, never by editing the test. |
| `test_042` golden suite (nine cases) | **Red until step 6** — `reports_close` compares key **sets** exactly, so this fails on the added keys alone, independently of the redefined value. |
| `test_104` catalogue drift | **Red until steps 4–5** — new realised paths are undocumented and absent from the committed artifact. |
| Every schema-validating module (33 test modules reach `serialize_report`) | **Red until step 3** — `stage3Curvature` sets `additionalProperties: false`. |
| `test_042`'s near-zero tolerance test (a literal `{"total_curvature_deg": ...}` dict) | **Green unchanged** — a tolerance unit test, not a descriptor call. |

## Validation

Beyond the suite, two observations are required — the second is AC22's only
verification and the validator must **execute** it, not infer it.

1. **The plane split is visible in a real report.** Regenerate into a scratch
   directory:

   ```
   .venv/bin/python -m segfacet.synth.golden --out out/goldens-122
   ```

   then inspect `out/goldens-122/mode6_crop_at_border.json` at
   `features.stage3.curvature`: `sagittal_curvature_deg` ≈ `70.78`,
   `coronal_curvature_deg` ≈ `11.75`, `curvature_plane == "sagittal"`,
   `total_curvature_deg` ≈ `70.78` — where the retired descriptor reported
   `35.6720` and named no plane. Confirm `clean_control.json` reports
   `coronal_curvature_deg` ≈ `11.4034`, equal to that case's
   `sum(inter_tangent_angles_deg)`, against the retired `5.7017`.

2. **The regeneration is narrow (AC22).** With the work committed on the item
   branch:

   ```
   git diff aide/queue-017 -- tests/corpus/golden tests/golden
   ```

   Every changed hunk must fall inside the `"curvature"` object of
   `features.stage3`. Any changed line naming a verdict, a finding, a
   threshold, `per_label`, `overlaps`, `relationships`, `per_label_offsets`,
   `per_label_orientations`, `spacing_consistency`, `monotonic_consistency`,
   `per_label_neighbourhood` or an intensity key means this item has moved
   something it does not own — hand back rather than committing it. Also
   confirm `git diff aide/queue-017 --stat` lists no file outside the **May
   change** list above.

No `[validation]` environment profile is required: both checks run on the
committed corpus with the default CPU install.

## Dependencies

- **Item 019** (✅) — provides `SpineCurvature`, `compute_spine_curvature` and
  the `tangent_angles_deg` / `inter_tangent_angles_deg` arrays this item keeps
  and measures against.
- **Item 022** (✅) — provides `curvature_to_dict`, the `stage3` block and the
  `report_schema_v0.json` `stage3Curvature` definition.
- **Item 042** and **item 078** (✅) — provide `write_goldens`,
  `check_case_golden` and the numeric-tolerance comparison the regeneration is
  judged by.
- **Item 103** and **item 104** (✅) — provide `FEATURE_DOCS`, the generated
  catalogue and its drift test.
- **Item 111** (✅) — removed `test_ac8_golden_snapshot`'s self-heal, which is
  why step 7 is a deliberate manual regeneration.
- **Item 116** (✅) — the RAS-native synthetic corpus, which is what makes the
  plane statement true of the committed fixtures.

**Downstream:** item 119 replaces the spline fit and will change these same
curvature values again; item 121 extends the *other* half of
`features/orientation.py` (per-vertebra orientation) and shares the file, so
whichever lands second merges over the first; item 123 regenerates the same
goldens after the fit change and will find them already carrying this item's
keys; item 124's observed-range column will pick up the five new leaf paths
automatically; item 125 replays the stage end-to-end.

## Decisions & Trade-offs

Two questions determine this item's blast radius. Both are settled here rather
than left to the builder, and the reasoning is recorded because the obvious
answer is wrong in each case.

### Replace the descriptor, or add a signed one alongside it?

**Decision: replace.** `total_curvature_deg` keeps its key and gains a correct
definition; the two per-plane sweeps and their signed arrays are added as the
evidence behind it.

The argument for adding alongside is that it avoids invalidating the ten
committed goldens. **It does not.** `synth.golden.reports_close` compares
dictionaries by exact key-set equality, and `tests/golden/022_stage3_report.json`
is compared as exact text. Adding five keys therefore invalidates all ten
artifacts exactly as replacing does — the supposed saving does not exist, and
it was worth measuring rather than assuming.

With that gone, replacing wins on every remaining count:

- The three existing assertions on the key all survive unmodified. Item 019
  AC5 (`< 1.0` for a straight spine) holds because the straight fixture reports
  `0.0`; AC6 (`>= 20.0` for a C-curve) holds because the value *rises* from
  `43.8537` to `87.7073`; and the serialisation module's non-negativity check
  holds because a max of two ranges is non-negative — a signed *range* is still
  non-negative, which is why the intuition that "signed" and "non-negative"
  conflict is wrong here. That check also uses a straight-spine fixture, so it
  was never at risk either way.
- Keeping a known-wrong "Cobb-angle-like proxy" in the record costs more than
  it saves. Stage 20 runs next and audits rule↔mode↔feature traceability, and
  item 124 adds an observed-range column to the catalogue. Both would inherit
  an extra row that reads healthy and measures nothing — the precise failure
  this stage exists to end.
- `stage3.curvature.total_curvature_deg` carries a recorded maintainer status
  of `retune` with the reason *"Should be expressed per axis component … rather
  than one aggregate scalar"*. Adding a parallel descriptor and leaving the
  scalar as-is contradicts that recorded call; redefining it moves toward it.

**Consequence accepted:** the key's meaning changes for anyone reading a
historical report. Nothing in the repo reads it (no rule, no human report,
neither reference artifact), so the cost is confined to the ten regenerated
artifacts and to a comparison of a pre-122 report against a post-122 one. The
schema description, the catalogue entry and the attribute docstring are all
amended in this same item so no statement of the retired formula survives
(AC18).

### Who regenerates the goldens this item invalidates?

**Decision: item 122 regenerates them, here, and merges on a green suite.**

[`queue-017.md`](../queue/queue-017.md) assigns artifact regeneration to item
123, and item 119 is told to leave the corpus red for 123 to clear. That
instruction is about the **fit** change: item 123's remit is "everything the
curve change invalidates" — `mislabel`'s `max_offset_mm`, the goldens,
`reference_default.json` and `reference_verse_v1.json` — and it is blocked on
the spinal curve model human gate because it depends on item 119. This item
depends on neither: it changes how tangents are reduced to a scalar, and
`progress.md`'s gate row names item 122 as released for exactly that reason.

Deferring the regeneration would defeat that release. Under this repo's
`[git] mode = "auto-merge"` the validator runs the full suite before merging,
so an item that leaves ten golden tests, the catalogue drift test and every
schema-validating module red cannot merge — item 122 would sit behind the gate
in practice while being formally released from it. Regenerating here is also
the *narrower* change: item 122's delta is confined to `stage3.curvature`,
fully determined by this item alone, and auditable by a single diff (AC22 and
the Validation section). It pre-empts nothing — item 123 regenerates the same
files again after item 119 and will simply find them already carrying these
keys.

The two reference artifacts stay untouched: neither carries any
`stage3.curvature` key, so item 123's headline deliverable — a
`spline_offset_mm` distribution rebuilt from real GT — is unaffected by this
item.

### Why unwrap, and why normalise the traversal direction

Both are consequences of choosing a *signed* angle, and neither is optional.

`atan2` returns a wrapped value in `(−180, 180]`, so a curve whose tangent
crosses the −S direction produces a discontinuity: `mode4_relabel_swap`'s
wrapped coronal sweep reads `180.8804°` where the unwrapped accumulated turning
is `355.3172°`. Since the centroid sequence is ordered, unwrapping along it is
well defined, and it keeps the descriptor continuous in its input — which
matters for a value a rule may eventually threshold.

Direction normalisation exists because the sign is measured against `+S`. A
sequence supplied cranial-first advances caudally, every tangent points at
`−S`, and every angle would sit near `±180°` — a latent trap for real data,
since the corpus fixtures happen to advance superiorly and would never have
exposed it. Negating the tangents when the net advance is caudal makes the
sweep invariant to traversal direction (AC13, verified against all nine corpus
cases) and leaves the retained unsigned arrays untouched.

### Remaining record-level inconsistency, deliberately not fixed here

`tangent_angles_deg[]` stays unsigned and stays measured against `+S` without
direction normalisation, so on a caudal-first sequence it reads near `175°`
while the new coronal array reads near `5°`. Reconciling the two arrays means
redefining `tangent_angles_deg`, which is item 121's and Stage 20's territory —
this item's scope fence is `SpineCurvature`'s scalar reduction. Captured in
`insights.md` rather than acted on.

### Authorised paths under-scoped the leaf-count blast radius

The original **Authorised paths** list omitted `tests/test_103_feature_catalogue.py`
and `docs/aide/golden-decision-table.md`. Both hardcode the `clean_control`
leaf-path count (84, and the derived `17/84` unwired fraction across the nine
Group-A golden rows), and adding five new leaves under `stage3.curvature`
moves both numbers (84 → 89, 17/84 → 22/89) whether or not this item's scope
fence says so — the count is measured off `segfacet.catalogue.build_catalogue()`
and the regenerated goldens, not chosen by the builder. A follow-up item could
not land the fix first: the true count only exists once this item's leaves
exist, so pairing the refresh with a later item would leave both documents
red for the entire gap. Both are added to **May change** here, restricted to
exactly the mechanical consequence (a count in one, and measured evidence
cells plus their narrative sentence in the other) — no judgement column in
the golden-decision-table (disposition, rationale, replacement guarantee) is
authorised to change from inside this item.

### Implementation notes (builder)

- Direction normalisation compares `centroids[-1].centroid_mm[2]` against
  `centroids[0].centroid_mm[2]` (the raw input sequence's first/last S, not
  `fit.u`-reordered values), matching the spec's step 2. The normalised
  tangent array feeds only `_signed_plane_angles_deg`; `tangent_angles_deg`
  and `inter_tangent_angles_deg` are computed from the original
  `unit_tangents` exactly as before, unaffected by the sign flip.
- `_signed_plane_angles_deg(unit_tangents, axis)` takes `axis=0` (R) for
  coronal and `axis=1` (A) for sagittal, always against `t[:, 2]` (S); it
  wraps `np.unwrap` around `np.arctan2`. `_sweep` returns `0.0` for arrays of
  length < 2 (the two-centroid minimum still produces a finite, if trivial,
  sweep).
- Artifact regeneration matched the spec's measured values exactly:
  `clean_control` coronal `11.4034°` (vs retired `5.7017°`),
  `mode6_crop_at_border` sagittal `70.7815°` / coronal `11.7501°` /
  `curvature_plane == "sagittal"` (vs retired `35.6720°`, unattributed), and
  `mode4_relabel_swap`'s coronal sweep `355.3172°` unwrapped. The regenerated
  `tests/corpus/golden/*.json` and `tests/golden/022_stage3_report.json` diffs
  against `aide/queue-017` are confined entirely to the `stage3.curvature`
  object in every file (AC22), confirmed via `git diff aide/queue-017 --
  tests/corpus/golden tests/golden`; `aide scope` reports all 19 changed
  files authorised.
