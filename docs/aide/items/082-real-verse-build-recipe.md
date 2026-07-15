# Item 082 — Real-VerSe acquisition & versioned artifact build recipe

> **Created:** 2026-07-15 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7)
> **Queue:** [`../queue/queue-010.md`](../queue/queue-010.md) · Item 082 *(second Stage-12 item; touches real VerSe — must degrade gracefully when the uncommitted cohort is absent)*
> **Objectives:** G3 (reference-grounded — turn the synthetic-only reference story
> into a documented, tested, *versioned* real-VerSe build so the delta-to-reference
> machinery can be grounded in real GT) and G7 (evaluable & reproducible — a
> deterministic, caller-dated build with an explicit storage/versioning policy).
> **Suggested branch:** `aide/082-real-verse-build-recipe` *(batch-specced on `aide/specs-queue-010`; execution branch created at claim time)*

---

## Description

Formalise, document, and **test** the end-to-end recipe for building a
separately **versioned** real-VerSe reference-data artifact
(`reference_verse_vN.json`, `provenance.source == "verse-vN"`) from a mounted
real VerSe GT cohort, and pin the project's reference-artifact **storage /
versioning / deployment-selection policy**.

The machinery already exists: `segqc build-reference`
(`src/segqc/cli.py::_handle_build_reference`) chains `ingest_cohort` →
`aggregate_reference` → `write_artifact` (item 045) and already exposes
`--cohort / --out / --source / --build-date / --config / --seg-suffix /
--size-strata-edges`; deployment already selects a non-default artifact via
`segqc run --reference-artifact <json>` (or `reference.artifact_path` config).
This item does **not** re-implement any of that. It delivers:

1. **A recipe / policy document** — `docs/reference-build.md` — covering: the
   two-artifact storage strategy (committed synthetic default **plus** the
   separately versioned real-VerSe artifact), the never-commit-raw-scans policy,
   the VerSe acquisition + cohort-staging notes (filename/layout adapter), the
   exact `segqc build-reference` invocation, and how a deployment selects the
   real-VerSe artifact.
2. **An automated test** that exercises the documented build invocation against a
   **tiny synthetic VerSe-shaped stand-in cohort** (a real cohort is never
   committed), asserting a well-formed versioned artifact with the correct
   provenance and feature families, plus the graceful-absence behaviour.

### What it is NOT — fenced scope

- **NOT the one-command refresh wrapper.** The re-runnable orchestration
  script (rebuild synthetic + optionally real + re-evaluate, in one invocation)
  is **item 083**. Item 082 adds **no** wrapper/entry-point script and must not
  duplicate 083 — it documents + tests the *manual* invocation of the existing
  `segqc build-reference` CLI.
- **NOT the real-VerSe evaluation or verification-table closure.** Quantifying
  the G3 false-positive rate on real VerSe GT and flipping the "Real VerSe GT"
  row to ✅ Verified is **item 084**. Item 082 does **not** add or flip that row.
- **NOT a committed real-VerSe artifact.** No real VerSe cohort is available in
  this repo / CI, so this item commits **no** `reference_verse_vN.json`; it
  documents + tests the *recipe*. A real artifact is produced and committed later
  by a data-holding human/CI runner, following this recipe.
- **NOT a new production filename/layout adapter.** VerSe's mask suffix and
  nested layout are handled by the existing `--seg-suffix` flag plus a documented
  operator staging step (see Assumptions) — no code is added to
  `ingest_cohort`/`build_reference`, and item 044's flat-directory ingestion
  convention is unchanged.
- **NOT a schema, ingest, aggregate, or delta change.** Those are item 081's.
  Item 082 consumes 081's output shape (schema `"1.2"`, morphology family).

---

## Acceptance Criteria

_One test per criterion, atomic and directly observable. The "stand-in cohort"
is a tiny (2–3 subject) synthetic VerSe-shaped cohort built in a temp dir from
`segqc.synth.clean_gt.build_clean_spine` (multi-level L1–L5 per subject, so
Stage 3 runs and `eigenvalue_ratio` is present) with painted
`segqc.synth.intensity.paint_clean_scan` sibling scans, written as
`<id>_seg-vert_msk.nii.gz` + `<id>_scan.nii.gz` pairs — no real VerSe data. The
"documented invocation" is `segqc build-reference --cohort <stand-in> --out
<json> --source verse-test-v1 --build-date 2026-07-15 --seg-suffix
_seg-vert_msk.nii.gz`, driven through `segqc.cli.main`._

### A. The versioned build recipe (exercised against a stand-in cohort)

- [ ] **AC1: A well-formed versioned artifact is produced.** Running the
      documented invocation exits `0` and writes a JSON file at `--out` that
      `segqc.reference.load_artifact` parses without raising into a
      `ReferenceDistribution` with at least one per-level `feature_stats` entry.

- [ ] **AC2: Provenance carries the caller-supplied `source` and `build_date`.**
      The artifact from AC1 has `provenance.source == "verse-test-v1"` and
      `provenance.build_date == "2026-07-15"` — the caller-supplied values,
      **not** `date.today()` (re-running on any date yields the same stamps).

- [ ] **AC3: VerSe filenames are handled by `--seg-suffix`, no code adapter.**
      With `--seg-suffix _seg-vert_msk.nii.gz` (the real VerSe vertebra-mask
      suffix), every subject in the built artifact has `subject_id` equal to the
      stand-in filename with that suffix stripped (e.g. `sub-verse004` from
      `sub-verse004_seg-vert_msk.nii.gz`); `src/segqc/reference/ingest.py` and
      `artifact.py` are **unmodified** in the diff.

### B. Feature families & schema version carried (item-081 dependency)

- [ ] **AC4: The artifact is schema `"1.2"` and carries the morphology family.**
      The artifact from AC1 has `schema_version == "1.2"` and its `features`
      include all three item-081 morphology names
      (`largest_component_fraction`, `component_count`, `eigenvalue_ratio`).

- [ ] **AC5: The artifact carries the geometry family.** The same artifact's
      `features` include every `segqc.reference.ingest.INGESTED_FEATURES`
      geometry name.

- [ ] **AC6: The artifact carries the intensity family when scans are staged.**
      Because the stand-in cohort provides `<id>_scan.nii.gz` siblings, the same
      artifact's `features` include the
      `segqc.reference.ingest.INGESTED_INTENSITY_FEATURES` intensity names —
      i.e. a real-VerSe-shaped build (seg + CT sibling) carries all three
      families at schema `"1.2"`.

### C. Graceful degradation when the cohort is absent

- [ ] **AC7: An absent cohort errors cleanly, writing no partial artifact.**
      `segqc build-reference --cohort <nonexistent-dir> --out <json> …` exits
      **non-zero**, no file exists at `--out` afterwards, and a clear
      `Error:`-prefixed message is written to stderr.

- [ ] **AC8: An absent cohort produces no traceback.** The combined
      stdout+stderr of the AC7 invocation contains **no** Python traceback
      (no `Traceback (most recent call last)` line) — a reported caller error,
      not an uncaught exception.

### D. Documentation: storage policy, acquisition & selection

- [ ] **AC9: The recipe document exists.** `docs/reference-build.md` exists and
      is non-empty.

- [ ] **AC10: The never-commit-raw-scans storage policy is documented.**
      `docs/reference-build.md` states that raw VerSe scans are **never**
      committed (large / licensed) and that **only the derived distributions
      artifact** is committed, and it identifies the committed synthetic
      `reference_default.json` as the retained test/determinism baseline that the
      real build does **not** replace.

- [ ] **AC11: The versioning + deployment-selection policy is documented.**
      `docs/reference-build.md` names the versioned artifact convention
      (`reference_verse_vN.json`, `provenance.source == "verse-vN"`) and
      documents that a deployment selects it via
      `segqc run --reference-artifact <json>` (or the `reference.artifact_path`
      config key).

- [ ] **AC12: VerSe acquisition + cohort-staging (the adapter) is documented.**
      `docs/reference-build.md` documents where real VerSe comes from
      (source/DOI, cross-referencing [`dataset-verse19.md`](../dataset-verse19.md))
      and the staging needed for ingestion: the real mask suffix
      `_seg-vert_msk.nii.gz` passed via `--seg-suffix`, flattening the nested
      `derivatives/sub-verseNNN/…` layout into one directory, and providing each
      CT as a `<id>_scan.nii.gz` sibling (renamed/linked from `_ct.nii.gz`) so
      intensity is folded in.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode was **interactive (forced)**. The three likely design questions were
resolvable with strong grounding (the queue text, the existing code, and the
stated 082/083 boundary) without guessing, so they are **settled and recorded
here** rather than blocked. Several **pin an interface**; the builder/validator
hand back if reality diverged.

- **Q1 — storage & deployment selection: settled as option (b), a separate
  committed versioned file.** The real-VerSe artifact is a **separate**
  `reference_verse_vN.json` (`provenance.source == "verse-vN"`) that does **not**
  replace the bundled synthetic `reference_default.json`; a deployment selects it
  via the already-existing `segqc run --reference-artifact <json>` flag (or
  `reference.artifact_path` config). Rationale: the queue explicitly names
  `reference_verse_vN.json` and mandates "keep the synthetic default as the
  test/determinism baseline", which rules out option (a) bundle-swap (it would
  destroy the reproducible baseline that Stage-6/8 determinism tests depend on).
  Bundle-swap is documented as a discouraged alternative, not the recommendation.
  When actually built by a data-holder, the versioned file is committed under
  `src/segqc/reference/` as package data (so it also ships selectable by path),
  and should be pinned `text eol=lf` in `.gitattributes` for CRLF hygiene — but
  **no** such file is committed by *this* item.

- **Q2 — the 082/083 boundary: confirmed.** Item 082 = recipe document + storage
  policy + acquisition/staging notes + a stand-in-cohort build test. It adds **no**
  wrapper/entry-point script. The one-command refresh orchestration
  (`scripts/refresh_reference.py`-style, rebuild + re-evaluate, graceful without
  VerSe) is **item 083**; the real-VerSe evaluation + verification-table closure
  is **item 084**. 082 does not duplicate either.

- **Q3 — VerSe filename/layout adapter: settled as documented staging +
  `--seg-suffix`, no production code.** Real VerSe does **not** conform to item
  044's flat `_seg.nii.gz` convention: masks are
  `sub-verseNNN_seg-vert_msk.nii.gz`, nested under `derivatives/sub-verseNNN/`,
  and `ingest_cohort` uses a flat, **non-recursive** `os.listdir` matching
  `--seg-suffix` (scan siblings are hardcoded to `_scan.nii.gz`; there is no
  `--scan-suffix` flag). Resolution: the operator **stages** the cohort — flatten
  the per-subject `derivatives/**/…_seg-vert_msk.nii.gz` masks into one directory
  and link/rename each CT `_ct.nii.gz` → `<id>_scan.nii.gz` — then invokes
  `build-reference --seg-suffix _seg-vert_msk.nii.gz`. This is documented in the
  recipe and validated by the stand-in test (which uses the real suffix). **No**
  recursive walker or renaming adapter is added to `ingest_cohort`/`build_reference`
  (that would exceed the 082/083 boundary and touch item-044 code).

- **Stand-in-cohort testing (real VerSe is not committed).** Every AC is exercised
  against a synthetic VerSe-shaped stand-in cohort built in a temp dir; no real,
  large, or licensed data is downloaded or committed, and no
  `reference_verse_vN.json` is committed. The test proves the *recipe* works; a
  real build is an operator step outside CI (tracked via item 084's verification).

- **Doc location `docs/reference-build.md`.** Chosen to match the project-doc
  convention (`docs/deployment.md`, `docs/gpu-verification.md` live at
  `docs/` top level, outside `docs/aide/`). If a reviewer prefers another path it
  is a one-line move + the AC9–12 path.

- **Pinned upstream interface — item 081 (specced, NOT yet merged; hand back if
  the realised shape diverged):**
  - `segqc.reference.schema.SCHEMA_VERSION == "1.2"` (re-exported as
    `artifact.ARTIFACT_SCHEMA_VERSION`), so a build after 081 stamps `"1.2"`.
  - `segqc.reference.build_reference` defaults `with_morphology=True` (and 063's
    `with_intensity=True`), and `_handle_build_reference` calls `build_reference`
    **without** overriding those flags — so `segqc build-reference` auto-produces
    a `"1.2"` artifact carrying geometry + intensity + morphology with **no CLI
    change**. If 081 instead gated morphology behind an explicit CLI flag or chose
    a different schema string, the builder hands back (AC4/AC6 would fail) so this
    spec's AC can be re-pinned.
  - `segqc.reference.ingest.INGESTED_MORPHOLOGY_FEATURES ==
    ("largest_component_fraction", "component_count", "eigenvalue_ratio")` and the
    unchanged `INGESTED_FEATURES` / `INGESTED_INTENSITY_FEATURES` constants.

- **Pinned upstream interfaces — items 044/045/063 (merged ✅):** `ingest_cohort`
  strips `--seg-suffix` to form `subject_id` and discovers a `<id>_scan.nii.gz`
  sibling; `build_reference` / `write_artifact` / `load_artifact` /
  `bundled_default_reference` / `default_artifact_path`; the strict
  `schema_version` loader check; and `_handle_build_reference` catching
  `(OSError, ReferenceArtifactError)` to return `1` with an `Error:` message and
  **no** `--out` write on an absent/bad cohort (the graceful-absence behaviour
  AC7/AC8 rely on — already present, asserted here, not newly implemented).

## Implementation Steps

Intended paths: a new project doc `docs/reference-build.md`, and a light,
behaviour-preserving docstring extension in `src/segqc/reference/artifact.py`.
**No** other production code changes; **no** wrapper script; **no** committed
real artifact.

1. **Author `docs/reference-build.md`** with these sections:
   - **Overview** — two reference artifacts: the committed synthetic
     `reference_default.json` (test/determinism baseline, rebuilt via
     `python -m segqc.reference.artifact`) and the separately versioned
     real-VerSe `reference_verse_vN.json`.
   - **Storage & versioning policy** — raw VerSe scans are **never** committed
     (large / licensed); only the derived distributions artifact is; the
     synthetic default is retained, **not** replaced (AC10); versioned naming
     `reference_verse_vN.json` / `provenance.source == "verse-vN"`, committed
     under `src/segqc/reference/` as package data and pinned `text eol=lf` when a
     real one is added (AC11).
   - **Acquisition** — where VerSe comes from (source/DOI), cross-linking
     [`dataset-verse19.md`](../dataset-verse19.md) (AC12).
   - **Staging the cohort for ingestion** — flatten the nested
     `derivatives/sub-verseNNN/…_seg-vert_msk.nii.gz` masks into one directory;
     link/rename each CT `_ct.nii.gz` → `<id>_scan.nii.gz` sibling; note the flat,
     non-recursive `os.listdir` walker and the hardcoded `_scan.nii.gz` scan
     discovery (AC12).
   - **Build invocation** — the exact command, e.g. `segqc build-reference
     --cohort <staged-dir> --out src/segqc/reference/reference_verse_v1.json
     --source verse-v1 --build-date YYYY-MM-DD --seg-suffix _seg-vert_msk.nii.gz`
     (AC1–AC3); note the `"1.2"` schema + all-three-families output (item 081).
   - **Deployment selection** — `segqc run --reference-artifact <json>` or
     `reference.artifact_path` config; bundle-swap noted as a discouraged
     alternative (AC11).
   - **Reproducibility & automation** — `build_date` is caller-supplied for
     determinism; `eigenvalue_ratio` is a platform-sensitive float (item 078/081
     tolerance), and the real artifact is committed once (not regenerated in CI),
     so no cross-platform byte-determinism test runs against it; point to **item
     083** for the one-command refresh wrapper.
2. **Extend the `src/segqc/reference/artifact.py` module docstring** ("Two rebuild
   commands" section) to (a) name the versioned real-VerSe output convention
   (`reference_verse_vN.json`, `--source verse-vN`) and (b) point to
   `docs/reference-build.md`. Behaviour-preserving doc-only edit.
3. **Add nothing else to production code.** `build-reference`, `build_reference`,
   `--seg-suffix`, and the graceful-absence try/except already exist and are
   sufficient; do **not** add a wrapper (083), a recursive walker, or a real
   artifact file.
4. **(Optional, hygiene)** add a `.gitattributes` pattern
   `src/segqc/reference/reference_verse_*.json text eol=lf` so a future committed
   real artifact stays CRLF-clean — harmless no-op today (no file matches).

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_082_verse_build_recipe.py`.
- **Stand-in cohort fixture:** a helper building a tiny (2–3 subject) VerSe-shaped
  cohort in a `tmp_path` dir via `segqc.synth.clean_gt.build_clean_spine`
  (multi-level L1–L5, so Stage 3 runs → `eigenvalue_ratio` present) paired with
  `segqc.synth.intensity.paint_clean_scan`, written as `<id>_seg-vert_msk.nii.gz`
  + `<id>_scan.nii.gz` file pairs (mirroring `build_default_cohort` but with the
  real VerSe mask suffix). No real data, no network.
- **Driver:** invoke the recipe end-to-end through `segqc.cli.main([...])` so the
  test exercises the *documented* CLI surface (exit code + `--out` file), not just
  the library function.
- **Per-AC tests:**
  - AC1/AC2 — build over the stand-in, assert exit 0, `load_artifact` succeeds,
    and `provenance.source` / `provenance.build_date` match the passed values.
  - AC3 — assert `subject_id`s equal the `_seg-vert_msk.nii.gz`-stripped stems;
    a diff-scope guard asserting `ingest.py` / `artifact.py` are not modified for
    adapter logic (assert via the absence of a new suffix-mapping symbol / or a
    focused source check — keep light).
  - AC4/AC5/AC6 — assert `schema_version == "1.2"` and that `features` ⊇ the
    morphology, geometry, and intensity name sets respectively.
  - AC7/AC8 — build with a `--cohort` path that does not exist; assert non-zero
    exit, `--out` file absent, `Error:` in stderr, and no `Traceback` substring.
  - AC9–AC12 — read `docs/reference-build.md` and assert the required content
    substrings for each policy/acquisition/selection clause.
- **Adversarial / edge cases (beyond the ACs):**
  - **Empty-but-present cohort** (dir exists, no `*_seg-vert_msk.nii.gz` files):
    build handles it without a traceback (clean error or empty-distribution
    artifact — assert whichever the machinery does, and that no traceback leaks).
  - **Wrong `--seg-suffix`** (no files match a mistyped suffix): same clean-error
    guarantee, no traceback.
  - **Determinism:** two builds over the same stand-in with identical args produce
    equal parsed artifacts (byte-identical intra-platform, or `reports_close`
    given the `eigenvalue_ratio` float, mirroring item 081/078).
  - **Scope guards:** assert no 082 test modifies the committed
    `src/segqc/reference/reference_default.json`, and that the repo tree contains
    **no** committed `reference_verse_*.json` (this item commits no real artifact).

## Dependencies

- **Item 081 (🚧 specced ahead in this batch, must be built + merged before a
  real 082 build yields a `"1.2"` artifact):** the morphology family, the schema
  `"1.1"`→`"1.2"` bump, and `build_reference`'s default-on `with_morphology`.
  Pinned in Assumptions; AC4/AC6 fail loudly (builder hands back) if 081's realised
  interface diverged.
- **Items 044 / 045 (✅):** `ingest_cohort` (flat walk, `--seg-suffix` stripping,
  `_scan.nii.gz` sibling discovery), `build_reference` / `write_artifact` /
  `load_artifact`, and the `segqc build-reference` CLI handler with its
  graceful-absence try/except — the build machinery this recipe drives.
- **Item 063 (✅):** the intensity family + `build_reference` default-on
  `with_intensity`, so a seg+scan stand-in build carries intensity (AC6).
- **Item 049 (✅) / item 057 (✅):** context — reference mode and evaluation the
  built artifact ultimately serves.
- **[`docs/aide/dataset-verse19.md`](../dataset-verse19.md) (existing living
  doc):** the source of the real VerSe layout/naming facts the recipe documents.
- **Downstream (this item enables):** item 083 (the one-command refresh wrapper
  automates this recipe) and item 084 (real-VerSe evaluation + "Real VerSe GT"
  verification-table closure).

## Environment / Hardware Dependencies

- **Real VerSe GT cohort** — an **external dataset** (not a pip dependency;
  large / licensed, never committed). Required fallback when absent (the common
  case, including all CI): `segqc build-reference` errors cleanly — non-zero exit,
  no partial `--out` artifact, a reported `Error:` message, and **no** traceback
  (AC7/AC8); every automated test runs against the synthetic stand-in cohort and
  never requires the real data. **Full-capability verification:** an actual
  real-VerSe `reference_verse_vN.json` built from a mounted cohort is **not**
  exercised here. This item does **not** add or flip a verification-table row —
  the existing **"Real VerSe GT"** row in `progress.md`'s Environment-Gated
  Capability Verification table remains `❓ Unverified` and is closed by **item
  084** when a human / CI runner with real VerSe data runs the build + evaluation.
  A green stand-in test does **not** count as verification.

## Decisions & Trade-offs

- **Doc authored at `docs/reference-build.md`** as anticipated in Assumptions,
  covering Overview, Storage & versioning policy, Acquisition, Staging, Build
  invocation, Deployment selection, and Reproducibility & automation — one
  section per Implementation Step, each carrying the exact substrings the
  AC9-AC12 tests assert on (verified against the test file before writing).
- **`artifact.py`'s "Two rebuild commands" docstring section extended**
  (doc-only) to name the `reference_verse_vN.json` / `--source verse-vN`
  convention and cross-link `docs/reference-build.md`. One deviation from a
  literal reading of the Implementation Steps: the example command in the
  docstring intentionally does **not** spell out the literal real VerSe mask
  suffix (`_seg-vert_msk.nii.gz`) — AC3's scope guard (mirrored in
  `test_ac3_scope_guard_no_new_suffix_mapping_symbol_in_ingest_or_artifact`)
  asserts the substring `"seg-vert_msk"` is **absent** from `artifact.py`
  (guarding against a code adapter creeping in), and that string check does
  not distinguish "adapter code" from "docstring prose". The docstring
  instead points readers to `docs/reference-build.md` for the concrete
  `--seg-suffix` value and full staging steps, which is where the AC12 tests
  assert that literal string. No behavioural/logic change either way.
- **No code changes** to `ingest.py` or `build_reference`/CLI handler —
  confirmed by reading both; the existing `--seg-suffix` flag and
  `(OSError, ReferenceArtifactError)` graceful-absence handling already
  satisfy AC1-AC8 with zero new production code.
- **`.gitattributes` hygiene line added**: `src/segqc/reference/reference_verse_*.json
  text eol=lf`, a no-op today (no matching file committed), per the optional
  Implementation Step 4.
- **No real `reference_verse_vN.json` committed**, per the fenced scope —
  confirmed no such file exists under `src/segqc/reference/`.
