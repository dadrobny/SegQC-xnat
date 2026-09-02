# Item 118 — Decide the spinal curve formulation

> **Created:** 2026-08-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 118
> **Objectives:** G2 (detect catalogued failure modes), G7 (evaluable &
> regression-testable); the deformity-envelope proposal serves G3
> **Suggested branch:** `aide/118-decide-the-spinal-curve-formulation`

---

## Description

Stage 28 exists because `features/spline.py` fits an **interpolating** spline
(`splprep(..., s=0)`), so the curve passes exactly through every centroid it
exists to judge. `stage3.per_label_offsets[].offset_mm` is therefore zero on all
nine committed goldens (max `6.8e-04` mm against `mislabel`'s
`max_offset_mm = 15.0`) and on real VerSe19 GT (`reference_verse_v1.json`: mean
`2.9e-05` mm), and `stage3.monotonic_consistency.is_monotonic` is `True` on every
case including `mode4_relabel_swap`.

This item is the **deliberation that chooses the replacement formulation**, not
the replacement itself. It resolves a modelling question with a clinical prior —
the curve must be flexible enough for real spinal shape (cervical lordosis,
thoracic kyphosis, lumbar lordosis give a sagittal S; scoliosis adds a coronal
curve) yet too stiff to follow a segmentation error, and a curve fit *from* the
centroids then used to judge a centroid is circular unless something breaks the
circle.

**This item produces no production code.** Its two deliverables are:

1. **A decision document** — [`docs/spinal-curve-model.md`](../../spinal-curve-model.md)
   — stating a choice, its consequence, and the measurement supporting it for
   each of five questions: **family**, **degrees of freedom and how they
   scale**, **parameterisation**, **how circularity is broken**, and **the
   deformity envelope**.
2. **A candidate-comparison script** — `scripts/compare_curve_candidates.py` —
   an AIDE *project tool* (the shape of `scripts/refresh_reference.py`, not part
   of the shipped `segfacet` package) that reproduces **every number the
   document quotes**, so item 125 can re-run it and confirm the measurements
   still hold against the shipped formulation.

**What this item is NOT.**

- It does **not** change anything under `src/segfacet/` — not `features/spline.py`,
  not `spline_offset.py`, `consistency.py`, `orientation.py`, `neighbourhood.py`,
  not `default_config.yaml`'s `max_offset_mm`. Implementing the chosen
  formulation is **item 119**; the features that only become measurable once it
  lands are items 120 and 121; the recalibration and artifact regeneration are
  item 123. An item 118 that edits a feature module has misread the stage.
- It does **not** regenerate the goldens or either reference artifact (item 123).
- It does **not** correct `docs/aide/dataset-verse19.md`'s documented nested
  `dataset-verse19training/dataset-verse19training/` layout, which the local
  symlink deliberately skips. That correction is **item 123**. This item's
  script sidesteps the question by discovering masks with a recursive glob
  (AC19), so it works under either layout without asserting which is right.
- It does **not** resolve the human gate. Only a person does that, via
  `aide gate approve`.

**The human gate does not block this item.** `progress.md`'s Human gates table
carries the spinal-curve-model gate — the deformity envelope, and the accepted
false-negative cost of a stiffer fit — with `Blocks: 119, 120, 121, 123, 125`.
Item 118 is deliberately **released**, because gating it would block the work
that feeds the gate: this item's output *is* the evidence a person reads when
deciding it. So no acceptance criterion here requires the gate to be resolved,
and the deformity-envelope section of the document is written as a **proposal
pending sign-off**, not as a settled decision (AC3).

**Judgement is measured, not argued.** Every candidate is scored on the five
criteria queue-017 names, and the document's choices cite those measurements:

| Criterion | Measured as |
|---|---|
| Clean GT stays inside item 017's bound | max pass-through distance ≤ **0.5 mm** across level counts and spacings |
| A displaced vertebra separates | displaced offset − clean maximum, in mm, at several displacement magnitudes |
| A real scoliotic curve is not flagged | the most coronally-deviated VerSe19 GT cases stay below the proposed threshold |
| Degenerate inputs survive | a 2-level input and a truncated-FOV input raise nothing and fail no non-degeneracy check |
| The fit is reproducible | two fits of identical input evaluate bitwise-identically |

## Acceptance Criteria

### The decision document

- [ ] **AC1: The decision document exists with its five decision sections.**
      `docs/spinal-curve-model.md` exists and contains a `## Decision` section
      holding exactly five subsections, in this order and with these headings:
      `### Family`, `### Degrees of freedom`, `### Parameterisation`,
      `### Breaking circularity`, `### Deformity envelope`.

- [ ] **AC2: Every decision section states choice, consequence and evidence.**
      Each of the five subsections in AC1 contains a `**Choice:**` line, a
      `**Consequence:**` line and an `**Evidence:**` line, each with non-empty
      text after the label.

- [ ] **AC3: The deformity envelope is recorded as a gated proposal, not a
      settled decision.** The `### Deformity envelope` subsection contains the
      literal marker `PROPOSED — pending human gate` and a link to
      `progress.md`'s Human gates table, and no line anywhere in the document
      asserts that the gate has been approved, resolved or signed off.

- [ ] **AC4: The measurements table is well-formed.** The document contains a
      `## Measurements` section holding one Markdown table with the columns
      `Key`, `Value`, `Units`, `Source`. Every row has all four cells non-empty,
      and every `Key` is a dotted path (two or more dot-separated segments).

- [ ] **AC5: Every quoted number is in the measurements table.** Every numeric
      literal appearing on an `**Evidence:**` line in the `## Decision` section
      appears as the `Value` of some row of the `## Measurements` table.

- [ ] **AC6: Every measurement key reproduces from a fresh run.** For a
      `curve_candidates.json` generated fresh by the script, every `Key` in the
      `## Measurements` table resolves to a present value, and that value equals
      the row's quoted `Value` within the tolerance the document states (AC7).
      Rows whose `Source` names the VerSe19 population are checked only when the
      cohort is reachable; when it is not, they are skipped with a recorded
      reason rather than passed.

- [ ] **AC7: The document says how to reproduce itself.** The document contains
      a `## Reproducing these numbers` section giving (a) the exact command line
      that regenerates the artifact, (b) the artifact path the `Key` column
      indexes into, and (c) the numeric tolerance under which a re-run counts as
      reproducing — enough for item 125 to re-run without reading this spec.

### The human gate

- [ ] **AC8: The gate is raised with the right reach.** `docs/aide/progress.md`'s
      `## Human gates` table contains a row whose subject is the spinal curve
      model's deformity envelope, whose `Blocks` cell names items 119, 120, 121,
      123 and 125, and which does **not** name item 118.

### The candidate-comparison script

- [ ] **AC9: The script runs standalone and writes its artifact.**
      `scripts/compare_curve_candidates.py` exposes a callable
      `main(argv) -> int`; invoked with only `--out <dir>` and no cohort, it
      returns `0` and writes `<dir>/curve_candidates.json` containing valid JSON.

- [ ] **AC10: Every candidate family is accounted for.** The artifact's
      `candidates` object contains the keys `interpolating_cubic`,
      `smoothing_spline`, `lsq_bspline_fixed_knots`, `polynomial_per_plane` and
      `robust_downweighted`. Each entry carries a `status` of `"evaluated"` or
      `"excluded"`, and every `"excluded"` entry carries a non-empty `reason`.

- [ ] **AC11: Every evaluated candidate carries all five judgement
      measurements.** Each `"evaluated"` candidate entry contains the keys
      `clean_pass_through`, `separation`, `verse_scoliotic`, `degenerate_inputs`
      and `determinism`.

- [ ] **AC12: The clean-GT sweep spans level counts and spacings.** The
      artifact's `sweep` block records the grid actually used: at least three
      distinct level counts including **2**, and at least three distinct
      spacings including at least one anisotropic spacing. Each evaluated
      candidate's `clean_pass_through` reports a `max_mm` over that whole grid.

- [ ] **AC13: Separation is measured at several displacement magnitudes.** Each
      evaluated candidate's `separation` block reports at least three distinct
      displacement magnitudes, each recording `clean_max_mm`,
      `displaced_offset_mm` and their difference `margin_mm`.

- [ ] **AC14: Both circularity modes are measured.** Each evaluated candidate
      records its `clean_pass_through` and `separation` results under both an
      `in_sample` key and a `leave_one_out` key, so the cost and benefit of
      excluding the point under test is visible per family rather than argued.

- [ ] **AC15: Degenerate inputs are exercised, not assumed.** Each evaluated
      candidate's `degenerate_inputs` block records, for a 2-level input and a
      truncated-FOV input, a boolean `raised` (false when the fit completed) and
      a boolean `degenerate` from the non-degeneracy check the document defines.

- [ ] **AC16: Fit determinism is established by comparison.** Each evaluated
      candidate's `determinism.identical` is `true` only when two independent
      fits of the same input, evaluated at the same parameter values, produce
      bitwise-identical coordinate arrays; the number of compared samples is
      recorded alongside it.

- [ ] **AC17: The tool itself is deterministic.** Two `main` invocations into two
      different `--out` directories produce `curve_candidates.json` files whose
      `candidates` and `sweep` blocks compare equal. Run-varying values
      (timestamps, host, cohort path) appear only inside a `provenance` block,
      which is excluded from that comparison.

- [ ] **AC18: The cohort path is machine-local configuration, never hard-coded.**
      The cohort root resolves from `--verse-cohort` if given, else the
      `SEGFACET_VERSE_COHORT` environment variable, else "not found"; the script
      source contains no literal dataset path. When the resolved root is missing
      or contains no masks, every VerSe-derived measurement is recorded with
      `status: "skipped"` and a non-empty `reason`, and `main` still returns `0`
      without a traceback.

- [ ] **AC19: Cohort discovery is layout-agnostic.** Masks are located by a
      recursive glob for `*_seg-vert_msk.nii.gz` beneath the cohort root, so a
      root containing the masks nested one extra directory deep and a root
      containing them directly both yield the same case list.

- [ ] **AC20: Scoliotic-case selection is objective and recorded.** The
      artifact's `verse_scoliotic` block records the cohort cases ranked by the
      coronal-deviation measure the document defines, together with the
      selection rule applied. When no case exceeds the document's stated
      curvature threshold, the block records that as a finding
      (`selected: []` with a non-empty `finding`) rather than omitting the
      measurement.

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume` (`aide.toml`), so each ambiguity below was resolved with
the most defensible default and recorded here for audit at the queue boundary.

- **Decision document path: `docs/spinal-curve-model.md`.** `docs/` already holds
  the project's durable technical documents (`reference-build.md`,
  `gpu-verification.md`, `deployment.md`); `docs/aide/` holds AIDE living
  documents and item specs, which this is not. Item 119's module docstring is
  expected to point at this path, and item 125 re-reads it.
- **Comparison script path: `scripts/compare_curve_candidates.py`, in the shape
  of `scripts/refresh_reference.py`.** A path-loaded AIDE project tool with
  `main(argv) -> int`, `--out`, a structured JSON summary, and optional external
  data degrading to a genuine structured skip — never part of the shipped
  `segfacet` package, never importing `tests`.
- **Artifact name and invocation.** `<out>/curve_candidates.json`, produced by
  `.venv/bin/python scripts/compare_curve_candidates.py --out out/curve-candidates`
  (add `--verse-cohort dataset-verse19training` for the real-GT half). The
  artifact is **not committed** — it is regenerated on demand, so it needs no
  `.gitattributes` LF pin and adds no byte-reproducible committed fixture.
- **The `Key` column is the reproduction contract.** Making every quoted number
  addressable by a dotted path into the artifact is what turns item 125's
  "confirm the quoted measurements still reproduce" from a reading exercise into
  a mechanical check. If a better mechanism is found, the document must still
  make every quoted number machine-resolvable.
- **Candidate identifiers are fixed strings** (`interpolating_cubic`,
  `smoothing_spline`, `lsq_bspline_fixed_knots`, `polynomial_per_plane`,
  `robust_downweighted`) because item 125 addresses them by name. They cover the
  four families queue-017 names plus today's baseline.
- **`robust_downweighted` may be excluded rather than implemented**, provided the
  artifact records a non-empty `reason` (AC10) and the document's `### Family`
  section cites it. No new runtime dependency may be added for it: SciPy, NumPy
  and NiBabel only, matching what `segfacet` already installs.
- **Cohort resolution reuses `SEGFACET_VERSE_COHORT`**, the variable
  `tests/test_084_stage12_acceptance.py` and `tests/test_091_stage14_acceptance.py`
  already use, and which `aide.toml`'s `[validation]` comment names as the place
  machine-varying cohort inputs belong. There is deliberately **no** repo-root
  fallback path, so AC18's "no hard-coded path" holds literally.
- **Default non-degeneracy check** (the document may state a better one, but must
  state whichever it uses): a fit is degenerate if any evaluated coordinate is
  NaN or infinite, or if the fitted curve's sampled arc length differs from the
  centroid polyline length by more than a factor the document states.
- **Default coronal-deviation measure for the scoliosis ranking** (likewise
  overridable but must be stated): the maximum perpendicular distance, in mm, of
  any centroid from the straight line joining the most cranial and most caudal
  centroid, measured in the left-right / cranio-caudal plane of the RAS-reoriented
  volume that `io.load_volume` guarantees.
- **`docs/aide/dataset-verse19.md`'s nested layout is known wrong here** — the
  local symlink at `dataset-verse19training` points straight at the dataset root,
  skipping the zip-extraction wrapper. This item does not correct the document
  (item 123 does) and does not depend on it: AC19's recursive glob works either
  way.
- **Write scope needs a permission grant.** `.claude/settings.json` pre-approves
  writes to `src/segfacet/**`, `tests/**` and `docs/aide/items/**` only. This
  item writes `docs/spinal-curve-model.md` and
  `scripts/compare_curve_candidates.py`, so an unattended builder will hit a
  permission prompt on both. Captured in `docs/aide/insights.md`.
- **The gate row already exists**, added 2026-08-27 with `Blocks: 119, 120, 121,
  123, 125`. AC8 therefore *verifies* the raised gate rather than adding one; no
  edit to `progress.md` is required or permitted by this item.

## Implementation Steps

There is **no code path in `source_dir`** — `src/segfacet/` is read for context
and left untouched. The work lands in `scripts/` and `docs/`.

1. **Build the harness skeleton.** Create `scripts/compare_curve_candidates.py`
   following `scripts/refresh_reference.py`'s shape: module docstring naming
   item 118, `REPO_ROOT`, an `argparse` parser (`--out`, `--verse-cohort`,
   `--max-verse-cases`), `main(argv) -> int`, and a structured summary written to
   `<out>/curve_candidates.json` *and* returned from a testable `run_comparison`
   helper. Import only `segfacet.*` production modules — never `tests`.
2. **Define the candidate interface.** One callable per candidate id taking the
   ordered `LabelCentroid` sequence and returning an object exposing "evaluate at
   these parameter values" and "closest point to this centroid", so every
   candidate is scored by the same measurement code. `interpolating_cubic` is
   today's `fit_centroid_spline` used unchanged, as the baseline the other four
   are read against.
3. **Implement the measurement passes**, each writing into the artifact under
   the keys AC11–AC16 name: the clean pass-through sweep over the level-count ×
   spacing grid (from `segfacet.synth.clean_gt.build_clean_spine`); the
   separation pass at several displacement magnitudes (from
   `segfacet.synth.identity_ordering_alignment.DisplacePerturbation`); the
   degenerate-input pass (a 2-level spine, and a truncated FOV); and the
   determinism pass. Run each of these in both circularity modes — `in_sample`,
   and `leave_one_out` following the technique already in
   `synth/regression.py`'s `_recon_leave_one_out_offset` (fit through every
   *other* centroid, then measure the excluded one).
4. **Implement the VerSe pass.** Resolve the cohort root per AC18, discover
   masks per AC19, compute per-case centroids and the coronal-deviation ranking
   per AC20, and record the pass-through and offset distributions of clean real
   GT for each candidate. Every VerSe-derived key degrades to
   `status: "skipped"` with a reason when the cohort is unreachable.
5. **Run it on this machine with the cohort mounted** and read the numbers.
6. **Write `docs/spinal-curve-model.md`** against those numbers: the five
   decision sections (AC1/AC2), the deformity envelope marked as a gated
   proposal (AC3), the `## Measurements` table whose `Key` column indexes the
   artifact (AC4–AC6), and `## Reproducing these numbers` (AC7). State the
   non-degeneracy check and the coronal-deviation measure the script implements,
   so the definitions live with the decision rather than only in code.
7. **Cross-check** that every number in an `**Evidence:**` line is a row of the
   measurements table before committing — that is the property AC5 tests and the
   one that decays fastest during editing.

## Authorised paths

**May change:**

- `docs/spinal-curve-model.md` — the decision document; the item's first
  deliverable (Stage 28 D1). New file.
- `scripts/compare_curve_candidates.py` — the candidate-comparison tool that
  reproduces every quoted number; the item's second deliverable. New file.
- `tests/test_118_curve_formulation_decision.py` — the tests for AC1–AC20. New
  file.
- `docs/aide/items/118-decide-the-spinal-curve-formulation.md` — this spec.

**Asserts against:**

- `src/segfacet/features/spline.py` — the `interpolating_cubic` candidate is
  today's `fit_centroid_spline` invoked unchanged, so the artifact's baseline
  numbers are a live measurement of the shipped code. Read and pinned by
  AC10–AC16; **not** modified (that is item 119).
- `src/segfacet/features/spline_offset.py` — read for the measurement
  definitions the candidates must reproduce (`closest_u`, the `_find_closest_u`
  scan/refine strategy, the monotonic-`u` test). Read only.
- `src/segfacet/features/consistency.py` — read for the same measurement
  definitions as `spline_offset.py` above. Read only.
- `src/segfacet/features/orientation.py` — read for the same measurement
  definitions as `spline_offset.py` above. Read only.
- `src/segfacet/features/neighbourhood.py` — read for the same measurement
  definitions as `spline_offset.py` above. Read only.
- `src/segfacet/synth/clean_gt.py` — the fixture builders the script reuses.
  Read only.
- `src/segfacet/synth/identity_ordering_alignment.py` — the `displace` operator
  the script reuses. Read only.
- `src/segfacet/synth/regression.py` — the leave-one-out technique the script
  reuses. Read only.

**Explicitly out of scope** (an edit here means the item has overrun):
`src/segfacet/**` of any kind, `src/segfacet/default_config.yaml`'s
`max_offset_mm`, `tests/corpus/**`, `src/segfacet/data/reference_*.json`,
`docs/aide/dataset-verse19.md`, `.gitignore`, `aide.toml`.

## Testing Strategy

One module: **`tests/test_118_curve_formulation_decision.py`**. It loads the
script by path (`importlib.util.spec_from_file_location`, the pattern
`tests/test_083_refresh_reference.py` and `tests/test_aide_status_report.py`
already use) rather than importing it as a package.

**One focused test per AC**, named for it:

- AC1–AC5, AC7 — parse `docs/spinal-curve-model.md` as text: section presence
  and order; the three labelled lines per subsection; the `PROPOSED — pending
  human gate` marker and the absence of any approval claim; the measurements
  table's shape; the evidence-numbers ⊆ table-values containment; the
  reproduction section's three required facts.
- AC6 — run the script into `tmp_path`, resolve each table `Key` against the
  fresh artifact, compare within the document's stated tolerance. VerSe-sourced
  rows use a `pytest.mark.skipif` on cohort reachability, in the shape of
  `tests/test_084_stage12_acceptance.py`'s cohort fixture, so an absent cohort is
  a recorded skip and never a vacuous pass.
- AC8 — parse `docs/aide/progress.md`'s Human gates table; assert the row's
  `Blocks` cell contains 119, 120, 121, 123, 125 and does not contain 118.
- AC9–AC17 — one test each over the artifact from a single synthetic-only run
  (`--out tmp_path`, no cohort), plus a second run into a second `tmp_path` for
  AC17.
- AC18 — three tests' worth of behaviour split across the AC: no literal dataset
  path in the script source; resolution order `--verse-cohort` → env → not found
  (via `monkeypatch.setenv`/`delenv`); and a missing/empty root yielding
  `status: "skipped"` with a reason and exit 0.
- AC19 — build two throwaway roots under `tmp_path` from the same tiny synthetic
  masks, one nested one flat, and assert the discovered case lists match.
- AC20 — assert the ranking and selection rule are recorded; and, with a
  stand-in cohort of deliberately straight spines, assert the no-qualifying-case
  path records a `finding` rather than omitting the block.

**Adversarial / edge cases:**

- `--out` pointing at a not-yet-existing nested parent — created with parents.
- Re-running into the same `--out` — overwrites cleanly, artifact compares equal.
- A cohort root that exists but holds no matching masks — a genuine skip, exit 0,
  no traceback (distinct from a missing root).
- A cohort mask with a single label, and one with two labels — neither crashes
  the VerSe pass; both are recorded as skipped-with-reason or measured, never
  silently dropped.
- The 2-level degenerate case at every candidate: a cubic family must clamp its
  degree (today's `min(degree, n_points - 1)`), and a fixed-knot family must
  reduce its knot count rather than raise.
- Env hygiene: `SEGFACET_VERSE_COHORT` is restored after any `monkeypatch`
  teardown, asserted explicitly as tests 084/091 do.
- Determinism is asserted by comparison, never by a hash of another file's bytes
  ([`.aide/conventions.md`](../../../.aide/conventions.md) §1) — scope is proved
  by the diff against the Authorised paths above.

**Existing tests to reconcile: none.** This item changes no production behaviour
and no shipped default, so nothing in `tests/` pins an old behaviour it moves.
Checked specifically: `tests/test_017_*` pins the shipped `s=0` fit's 0.5 mm
pass-through and stays green because `features/spline.py` is untouched; no test
globs `docs/*.md` or `scripts/*.py`, so adding two files breaks no inventory
assertion. Item **119** is the one that will make `test_017_*` and the corpus
goldens move.

## Validation

Beyond the unit suite, the validator must **run the tool on the real cohort and
read the document as a person deciding the gate would**:

1. `.venv/bin/python scripts/compare_curve_candidates.py --out out/curve-candidates --verse-cohort dataset-verse19training`
   — exits 0, and `out/curve-candidates/curve_candidates.json` has **no**
   VerSe-derived measurement in `status: "skipped"`.
2. Open `docs/spinal-curve-model.md` and confirm a reader who has never seen this
   session can answer, for each of the five decision sections, *what was chosen*,
   *what it costs*, and *which number says so* — and can find that number in the
   `## Measurements` table.
3. Confirm the chosen candidate's `clean_pass_through.max_mm` is ≤ 0.5 mm over
   the whole sweep grid, and that its smallest recorded `margin_mm` is positive
   and matches the margin the document states item 119 must meet.
4. Confirm the document does **not** claim the gate is resolved.

**Environment.** The real-GT half needs the VerSe19 cohort (80 CT/GT pairs,
reachable on this machine through the gitignored symlink at
`dataset-verse19training`). There is no `[validation]` profile for it — cohort
presence is an environment variable, not a capability probe — so the honest
downgrade is: if the cohort cannot be reached, **hand back rather than ship**.
A decision document whose real-GT evidence rows all read `skipped` does not
answer the question the gate asks, and shipping one would put an unevidenced
proposal in front of the person deciding it. The queue records the cohort as
available, so an unreachable cohort is a machine problem to report, not a
degradation to absorb.

## Dependencies

None. Item 118 is unblocked: the spinal-curve-model human gate is recorded in
`progress.md` as **not** blocking it, precisely because this item produces the
evidence the gate is decided on.

**Downstream:** item 119 implements the formulation this item chooses and is held
by the human gate; items 120, 121, 123 and 125 follow 119. Item 125 re-runs this
item's comparison script to confirm the quoted measurements still reproduce
against the shipped formulation, and confirms a person resolved the gate before
119 landed. Items 122 and 124 are independent of both this item and the gate.

## Decisions & Trade-offs

- **Family: `smoothing_spline`** (SciPy `splprep` with `s = n_points` instead
  of `0`, same `k = min(3, n_points - 1)` degree clamp as today). Rejected
  `lsq_bspline_fixed_knots` and `polynomial_per_plane` despite both showing a
  *larger* synthetic in-sample separation margin, because both fail badly on
  real VerSe19 anatomy (in-sample max pass-through on the cohort's most
  coronally-deviated cases: `17.68` mm and `27.86` mm respectively, against
  `smoothing_spline`'s `2.10` mm) — they would falsely flag real scoliotic
  curvature. `robust_downweighted` was excluded outright: an
  iteratively-reweighted robust regression needs functionality SciPy/NumPy do
  not ship, and adding it means a new runtime dependency, which this item's
  Assumptions forbid.
- **Degrees of freedom: `s = n_points`**, SciPy's own documented starting
  point (`s` in `(m - sqrt(2m), m + sqrt(2m))`), so smoothing capacity scales
  with cohort size automatically rather than via a fixed, separately-tuned
  knot count. Measured trade-off: at small level counts (the sweep's
  smallest multi-level grid point) there is no spare freedom to smooth with,
  so `smoothing_spline` provably degenerates to the same fit as the
  fixed-knot alternative there (both `0.552139` mm) — the real
  differentiation only shows up at the larger vertebra counts VerSe19
  provides.
- **Parameterisation: chord-length**, unchanged from today's `u` (the value
  `splprep` already computes), shared by `interpolating_cubic`,
  `smoothing_spline` and `lsq_bspline_fixed_knots`. `polynomial_per_plane`'s
  own-domain (cranio-caudal-coordinate) reparameterisation is one further,
  independent reason it was not chosen: adopting it would mean redefining
  what "the spline parameter" means for every Stage 3 consumer
  (`closest_u`, `_find_closest_u`, the monotonic-`u` check).
- **Breaking circularity: leave-one-out**, matching the technique
  `synth/regression.py`'s `_recon_leave_one_out_offset` already uses for the
  mislabel reconstruction path. Measured to matter *more* than the family
  choice: every evaluated family separates a 5 mm synthetic displacement
  almost identically well once the excluded point never gets to bend the
  fit toward itself (smallest leave-one-out margin `4.999144`–`4.999936` mm
  across families, vs. `-0.244683`–`0.140882` mm in-sample). Item 119 should
  make leave-one-out the actual `stage3.per_label_offsets` computation, not
  only a synthetic-test technique.
- **Deformity envelope: PROPOSED, not decided here.** A proposed
  `max_offset_mm` of `25.0` mm (up from today's `15.0`, tuned against an
  always-zero interpolating offset) is recorded as evidence for the human
  gate in `docs/spinal-curve-model.md`'s `### Deformity envelope` section —
  set above the highest leave-one-out offset observed on any real VerSe19 GT
  case (`21.073357` mm) so a genuinely scoliotic but undisplaced spine is not
  falsely flagged, at the accepted cost of missing a smaller genuine
  displacement. This item does not resolve the gate (AC3/AC8); a person must
  decide via `aide gate approve` before item 119 lands.
- **Script structure**: `scripts/compare_curve_candidates.py` builds every
  candidate's centroid-mm coordinates via a shared `evaluate(u) -> (N, 3)`
  interface (`u` in `[0, 1]`) so one coarse-scan-then-refine closest-point
  search (mirroring `features/spline_offset._find_closest_u`) works
  unmodified across all four evaluated families, including
  `polynomial_per_plane` (whose own domain is linearly remapped onto `u`).
  Leave-one-out in the clean-GT sweep excludes only *interior* centroid
  indices, not endpoints — excluding an endpoint turns the measurement into a
  pure extrapolation-beyond-the-fit-domain question dominated by
  inter-vertebra spacing for every family alike, not a genuine
  family-differentiating signal.
- **Real-cohort run**: the VerSe19 cohort was reachable on the implementation
  machine (`dataset-verse19training`, 80 masks via recursive glob). Every
  number quoted in `docs/spinal-curve-model.md`, including every
  VerSe-sourced row, came from an actual
  `scripts/compare_curve_candidates.py --out out/curve-candidates
  --verse-cohort dataset-verse19training` run — none were invented, and none
  had to be recorded as skipped.
- **Spec correction: `docs/aide/progress.md` removed from `## Authorised
  paths` → `Asserts against`.** The original bullet pinned it "read only;
  this item makes no edit to `progress.md`", but the mandatory
  `aide progress set NNN in-progress` workflow step (which every item,
  including this one, must run) always changes `progress.md`'s status
  column — so the bullet as written made `aide scope` fail on the routine
  status flip alone, independent of whether AC8's asserted content (the
  Human gates row's `Blocks` cell) ever changed. `progress.md` is already
  covered by the framework's own always-authorised path list for exactly
  that routine flip, so the extra "Asserts against" pin was redundant for
  the file-level scope check and only added a false-positive failure mode.
  AC8 itself is unaffected: it is a read-only text assertion against
  `docs/aide/progress.md`'s content, not a scope-tool declaration, and this
  item still makes no edit to the Human gates table.
