# FACET — Development Roadmap

> **Status:** Draft v2 · **Created:** 2026-06-24 · **Re-issued:** 2026-07-02
> **Partially superseded 2026-07-25** — see [`vision.md`](vision.md) §0. Stages 0–14
> are history and are not reopened; Stage 15 is `❌ Excluded`; Stage 16 was retargeted
> in place; Stages 17–21 are the live work; Stages 22–25 are placeholders authored at
> the full re-vision.
> (structure per `.aide/templates/roadmap.md`; content carried over unchanged)
> Step 2 of the AIDE loop. Derived from [`vision.md`](vision.md). Breaks the
> vision into incremental, demonstrable, locally-deployable stages (~1 week each).

---

## Strategy

1. **MVP first, complete the pipeline, then extend.** Phase 1 builds a thin
   end-to-end slice and grows it into the *complete local QC pipeline*
   (I/O → features → heuristics → verdict → report → evaluation). Phase 2 only
   begins once that pipeline is complete and calibrated.
2. **Initial focus = image processing + simple heuristics.** The feature-
   extraction core (geometric/topological processing of the label maps) and the
   explainable rule engine are the heart of Phase 1.
3. **Containerisation comes after** the pipeline is complete — XNAT/Docker (G5),
   GPU acceleration (G6), and the extensibility/classification arm (G8) are
   **Phase 2** extensions.
4. **Prioritised objectives: G1, G2, G3, G4, G7.** Phase 1 delivers all five.

> **Scope decision (confirmed 2026-06-24):** "image processing" in Phase 1 means
> the **geometric/topological feature engine** (volumes, components, centroids,
> spline) that the §6 failure-mode heuristics actually need. **Richer image-based
> / radiomics intensity features** are a Phase 2 enhancement (Stage 8), since the
> catalogued failure modes are predominantly geometric and the MVP stays minimal.

### Objective → stage coverage

| Objective                                       | Delivered by                                                                                                             |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| G1 Detect empty / trivially-failed              | Stage 1                                                                                                                  |
| G2 Detect catalogued failure modes (§6)        | Stages 4, 5 (real failures:**Stage 16**)                                                                           |
| G3 Distinguish failure from variation           | Stages 6, 7 (real-VerSe grounding: Stage 12;**recalibration: Stage 14**)                                           |
| G4 Per-case QC report (JSON + human)            | Stage 1 (extended by 2–4)                                                                                               |
| G7 Evaluable & regression-testable              | Stages 5, 7 (real-VerSe evaluation: Stage 12;**real data: Stages 14, 16**; corpus rework: **Stages 19–21**) |
| *(out of scope 2026-07-25)* G5 Deploy on XNAT | Stage 9 shipped the artefacts;**Stage 15 `❌ Excluded`** — see `vision.md` §0                                |
| *(deferred)* G6 Portable / GPU                | Stage 10                                                                                                                 |
| *(deferred)* G8 Extensible / classification   | Stage 11                                                                                                                 |

> **Stages 14–16 exist because building ≠ validating.** Stages 0–13 deliver and
> synthetically verify the whole pipeline, but several objectives' measurable
> outcomes name **real** data or environments — real VerSe GT (G3, G7), real
> session data (G5), real segmentation failures (G2) — and are demonstrated only
> where real data has judged them. On real held-out VerSe GT the pipeline's
> false-positive rate is **0.925** (against a synthetic 0.0), so G3 is not yet
> met. Stages 14/15/16 are the real-data validation arm for G3, G5, and G2/G7
> respectively — see [`progress.md`](progress.md)'s "Two kinds of done" section.
> These stages do not reopen any earlier stage's code; they validate outcomes the
> earlier stages' synthetic tests could not.

### Stage dependency graph

```
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 7        (Phase 1: complete MVP pipeline)
              └────────► 6 ─┘
                              
Phase 2 (after 7):  8 (img features) · 9 (XNAT) · 10 (GPU) · 11 (extensibility)
                    12 (real-VerSe grounding & reference feature expansion)
                    13 (dataset ingestion adapters & harmonization schema)

Phase 3 — real-data validation (the outcome arm; needs real data/environments):
                    12 ─► 13 ─► 14 (recalibrate on real GT)  ─► 16 (real failures)
                                 9 ─► 15 (real XNAT server)
```

> **Stage 12** deepens Stages 6/7 (G3, G7): it was scoped after those stages
> shipped on a *synthetic* VerSe stand-in. It depends only on Stage 7 and is
> independent of Stages 8–11, so it may be prioritised ahead of the GPU (10) /
> extensibility (11) extensions.

> **Stage 13** generalises dataset ingestion behind a dataset-agnostic
> `Cohort`/`Case` interface plus declarative per-dataset adapters, so real
> cohorts in varied on-disk layouts / naming conventions (VerSe19/20,
> TotalSegmentator or SPINEPS outputs, …) are ingested through one interface
> rather than hand-staged. It depends on Stages 6/7 and **unblocks the
> real-data half of Stage 12** (building `reference_verse_vN` from real GT and
> evaluating held-out real GT through the clean interface). Scoped 2026-07-16
> after Stage 10 was verified on real GPU hardware and real VerSe data was
> mounted.

---

# Phase 1 — Complete MVP Pipeline (priority: G1–G4, G7)

## Stage 0 — Project Scaffolding & I/O Foundation

**Goal.** A runnable, cross-platform Python package + CLI that loads a scan and an
instance label map, normalises labels via a documented convention, and exits
cleanly. Establishes the skeleton every later stage plugs into.

**Deliverables.**

- Python package `segqc/` targeting **Python 3.9+**; `pyproject.toml` with pinned
  core deps (NumPy, SciPy, scikit-image, NiBabel and/or SimpleITK).
- CLI entry point: `segqc run --scan <nii> --seg <nii> --out <dir>`.
- NIfTI loader for scan + label map, preserving spacing/affine and handling
  anisotropy.
- **Label convention module**: integer label ↔ anatomical vertebra
  (C1–C7, T1–T12(+T13), L1–L5(+L6), S…), configurable, with a default
  TotalSegmentator/VerSe mapping.
- Structured logging and a versioned **heuristic config** scaffold (YAML/JSON).
- `pytest` harness + a couple of tiny synthetic NIfTI fixtures.

**Dependencies.** None.

**Validation / acceptance.**

- `segqc run` on a fixture loads both volumes, prints the label inventory with
  anatomical names, and writes a stub JSON.
- Unit tests for the loader and label mapping pass.
- Runs CPU-only on Windows, macOS, and Linux.

---

## Stage 1 — End-to-End Thin Slice: Empty Detection + Report (G1, G4)

**Goal.** The smallest *complete* pipeline — input → verdict → report — that
detects empty / trivially-failed segmentations. Proves the full data flow before
any heavy feature work.

**Deliverables.**

- Empty / near-empty detection: no labels, total foreground < N voxels, or
  < K distinct labels — all configurable.
- **QC verdict model**: `pass` / `flagged-for-review` / `fail`, carrying per-case
  and per-vertebra reasons.
- **JSON report schema v0** (machine-readable, versioned).
- **Human-readable report** (Markdown/plain text) rendered from the same model.
- CLI wires loader → empty-check → verdict → both report formats.

**Dependencies.** Stage 0.

**Validation / acceptance.**

- 100% of empty / near-empty fixtures flagged `fail` with an explicit reason
  (**G1**).
- A non-empty fixture passes the empty check.
- JSON validates against the schema; human report generated (**G4**).
- Tests cover the empty-detection thresholds.

---

## Stage 2 — Geometric & Topological Feature Extraction (image-processing core)

**Goal.** Build the feature engine the heuristics depend on — the core
"image processing" focus of the MVP.

**Deliverables.**

- Per-label features: voxel & physical **volume**; **extent** (x/y/z); **bounding
  box**; image-border-contact flags.
- **Connected-components** per label: component count + sizes (inputs for
  fragmentation / island detection).
- **Fragmentation index** per label: ratio of largest connected component to
  total label volume — a scalar summarising how split the label is.
- **Vertebra centroid** per label, with level-aware special handling (C1, C2, S):
  - Simple CoM (baseline).
  - EDT-based *smooth centre* (CoM of EDT-thresholded mask) and *strict centre*
    (smoothed EDT peak) for more robust localisation within the vertebral body.
- **Centroid depth**: distance from the chosen centroid to the nearest label
  surface (reuses the EDT from the centroid step).
- **Inter-vertebra relationships**: ordered centroid sequence, neighbour spacing,
  label-sequence continuity.
- **Overlap detection** between labels.
- Features serialised into the JSON report (`features` block) + a per-case
  feature table.

**Dependencies.** Stage 0 (extends Stage 1 report model).

**Validation / acceptance.**

- Features computed deterministically on fixtures; values verified against
  hand-computed expectations.
- An anisotropic-spacing fixture yields correct physical volumes/extents.
- `features` block emitted in JSON; tests cover each feature.

---

## Stage 3 — Spinal Curve: Spline Fit & Geometric Deviation Features

**Goal.** Add the centroid-spline and deviation features that power alignment,
ordering, and mislabelling heuristics.

**Deliverables.**

- **Spline fit** through the ordered vertebra centroids, robust to missing levels.
- Per-vertebra **offset from the spline**.
- **Orientation / rotation** estimate per vertebra + global curvature descriptors.
- **Neighbour-consistency** metrics (spacing regularity, monotonic progression
  along the curve).
- **Local neighbourhood comparison** (sliding window, n=3–5 vertebrae): for each
  vertebra compute its deviation from the local neighbourhood mean/median of
  centroid spacing, spline offset, volume, and other per-label features; emit a
  per-vertebra deviation score and flag anatomical outliers within an otherwise-
  consistent spine segment.
- Optional sagittal projection of centroids + spline for the human report.

**Dependencies.** Stage 2.

**Validation / acceptance.**

- Spline fits cleanly on GT fixtures; offsets near-zero for GT, large for
  displaced/mislabelled fixtures.
- Robust to a deliberately missing level (no crash, sensible fit).
- New features in JSON; tests over GT + perturbed cases.

---

## Stage 4 — Heuristic Rule Engine over the Failure Modes (G2)

**Goal.** An explainable, configurable rule engine that detects each §6 failure
mode — the "simple heuristics" focus of the MVP.

**Deliverables.**

- Config-driven **rule engine**: each rule emits a flag + human-readable reason +
  offending labels.
- Rule families covering §6:
  - **min/max bounds** (volume, extent), level-aware;
  - **connected-components** → fragmentation / island flags;
  - **incomplete coverage / missing levels** (count vs expected sequence);
  - **label-sequence continuity** (e.g. L1→T12→L2→L5);
  - **border-partial-vertebra** flag;
  - **overlap** flag;
  - **mislabel / misalignment** (centroid vs expected level ordering / spline).
- **Verdict aggregation**: combine flags → pass / flag / fail with severity.
- Heuristic thresholds in a documented, versioned config file.

**Dependencies.** Stages 2, 3.

**Validation / acceptance.**

- Each of the 8 failure modes in §6 has ≥1 heuristic that fires on a crafted
  example (**G2**).
- Every flag carries a reason + offending labels; thresholds live in config.
- Tests assert correct firing **and** non-firing per rule.

---

## Stage 5 — Synthetic Failure Corpus & Regression Suite (G7)

**Goal.** A reproducible corpus and automated tests covering every failure mode.

**Deliverables.**

- **Synthetic-failure generator** that perturbs a GT label map: relabel,
  remove/add segment, inject islands, fuse/fragment, swap order, crop at border,
  overlap.
- Small committed **fixture set** spanning all 8 failure modes.
- **Regression suite**: runs the full pipeline and asserts the expected verdict +
  which heuristic fired per case.
- **Golden-file JSON snapshots** for stability/determinism.

**Dependencies.** Stage 4.

**Validation / acceptance.**

- Every §6 failure mode has ≥1 synthetic case and is detected (**G7**, **G2**).
- Full-pipeline regression suite green; golden JSON stable across repeated runs.

---

## Stage 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)

**Goal.** Ground the heuristics in VerSe-derived expected distributions rather
than hand-guessed constants.

**Deliverables.**

- VerSe GT ingestion → per-level feature aggregation into **reference
  distributions** (mean/percentiles), stratified by level (and a subject-size
  proxy where feasible).
- **Versioned reference-data artifact** (committed or mounted) + a builder script.
- **Delta-to-reference rules**: per-vertebra distribution distance / out-of-range
  vs reference.
- Heuristic config can switch from hand-set bounds to reference-derived bounds
  where available.

**Dependencies.** Stages 2–4 (parallelisable with Stage 5).

**Validation / acceptance.**

- Reference artifact builds reproducibly from VerSe and is versioned.
- GT fixtures fall within reference ranges; perturbed cases fall outside (**G3**).
- Tests cover reference loading + delta rules.

---

## Stage 7 — Evaluation, Calibration & Metrics (G3, G7) — *Phase 1 complete*

**Goal.** Quantify performance and calibrate thresholds against VerSe GT,
TotalSegmentator output, and the synthetic corpus. Marks the MVP pipeline as
complete.

**Deliverables.**

- **Evaluation harness** comparing at three levels: QC verdict; DICE vs GT;
  feature-set match by vertebra label.
- Runs on: VerSe GT (positive control), TotalSegmentator outputs, synthetic
  failures.
- **Metrics**: FPR on GT, sensitivity per failure mode, DICE-vs-flag correlation.
- **Threshold calibration loop**; chosen thresholds + metrics recorded in the
  evaluation report / `progress.md`.

**Dependencies.** Stages 5, 6.

**Validation / acceptance.**

- GT passes at a high rate (low FPR) (**G3**).
- Injected failures are caught; flag rate / feature divergence correlates with
  DICE (**G7**).
- Calibrated thresholds + metrics recorded; evaluation is reproducible.

---

# Phase 2 — Extensions (after the pipeline is complete)

## Stage 8 — Image-Based / Radiomics Features

**Goal.** Add intensity/radiomics features over labelled regions to strengthen
heuristics and seed abnormality detection.

**Deliverables.**

- Intensity features over each labelled region (+ original scan); optional
  **PyRadiomics** integration.
- Feature fusion into the report + at least one intensity-based heuristic
  (e.g. implausible-intensity flag).
- Reference distributions extended with intensity features.

**Dependencies.** Stages 2, 6.

**Validation / acceptance.** Image features computed on fixtures; ≥1 intensity-
based heuristic fires appropriately; tests pass.

---

## Stage 9 — Containerisation & XNAT Container Service Command (G5)

**Goal.** Package the completed pipeline as a Docker image with an XNAT command.

**Deliverables.**

- **Dockerfile** (CPU-only base), pinned deps, bundled/mounted reference data.
- XNAT Container Service **`command.json`** (inputs: session/scan + segmentation;
  outputs: report resources), per
  [XNAT guidance](https://wiki.xnat.org/container-service/building-docker-images-for-container-service).
- Entry script mapping XNAT inputs → CLI → output resources.
- Local container smoke test + deployment docs.

**Dependencies.** Stage 7 (stable, calibrated pipeline).

**Validation / acceptance.** Container runs the pipeline on a mounted case,
producing JSON + human report; `command.json` validates; install steps
documented (**G5**).

---

## Stage 10 — Portable Compute: GPU Acceleration Path (G6)

**Goal.** Optional GPU acceleration that yields results equivalent to the CPU
path; GPU never required.

**Deliverables.**

- Runtime backend selection (CuPy/cuCIM when present, NumPy/SciPy fallback).
- **Equivalence tests**: CPU vs GPU produce identical verdicts.
- Performance benchmark.

**Dependencies.** Stage 7.

**Validation / acceptance.** GPU path is optional + auto-detected; CPU/GPU
verdict-equivalence tests pass; the tool runs fully CPU-only (**G6**).

---

## Stage 11 — Extensibility & Abnormality Classification Arm (G8)

**Goal.** A documented extension path plus an optional classification arm so
handled abnormalities are accounted for rather than naively flagged.

**Deliverables.**

- Plugin/registration API for new heuristics + abnormality classes.
- Ingestion of human abnormality labels (post-op, fracture, implant); a
  classification arm that informs the heuristics.
- Developer docs: add a heuristic / abnormality class end-to-end.

**Dependencies.** Stage 7 (and Stage 8 for image features).

**Validation / acceptance.** A new heuristic + abnormality class can be added via
the documented path in a test; explicitly-handled abnormalities are not naively
flagged (Vision Success Criterion 4) (**G8**).

---

## Stage 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7)

**Goal.** Finish what Stages 6/7 started against a *synthetic* stand-in: widen
the reference distributions to the full set of discriminative per-level
features the engine already computes, ground them in **real VerSe** ground
truth, and quantify the pipeline's false-positive rate on real GT. Stages 6/7
shipped their machinery on a 5-subject synthetic VerSe-shaped cohort
(`reference_default.json` → `provenance.source == "synthetic-verse-cohort"`);
this stage closes the gap between "the pipeline can do this" and "the pipeline
has been grounded in and evaluated on real VerSe."

**Deliverables.**

- **Expanded reference feature vocabulary.** Widen the ingested/aggregated
  per-level feature set beyond the current 5 geometric + 13 intensity scalars
  to include the discriminative Stage-2/3 scalars the engine already computes
  but the reference ignores — fragmentation index, largest-component fraction,
  component count, centroid depth (EDT), per-label orientation, and
  spacing/neighbour-consistency deviations — threaded through ingest →
  aggregation → the delta-to-reference rules → the switchable config.
- **Real-VerSe acquisition & versioned artifact build recipe.** Documented,
  scripted process to mount a real VerSe GT cohort and produce a separately
  **versioned** reference artifact (`reference_verse_vN.json`, `provenance.source == "verse-vN"`); commit the *derived distributions artifact*, never the raw
  VerSe scans (large / licensed). Keep the synthetic default for reproducible
  tests.
- **One-command refresh wrapper.** A re-runnable script/target that rebuilds
  the reference artifact and re-runs the Stage-7 evaluation, so "we added a
  feature / changed config → refresh everything" is a single invocation. It
  must **degrade gracefully when real VerSe data is absent** (not committed):
  rebuild the synthetic default and evaluate the synthetic corpus, and clearly
  skip — never fail — the real-VerSe steps, mirroring the environment-gated
  capability pattern.
- **Real-VerSe evaluation & verification.** Run `segqc evaluate` over real
  VerSe GT to quantify the G3 target (GT passes QC at a high rate / low FPR);
  record the metrics and flip the "Real VerSe GT" row in `progress.md`'s
  Environment-Gated Capability Verification table to ✅ Verified.

**Dependencies.** Stages 6, 7 (✅). Independent of Stages 8–11; may be
prioritised ahead of them.

**Validation / acceptance.**

- The expanded features appear in a rebuilt reference artifact and are consumed
  by the delta-to-reference rules; existing synthetic tests stay green.
- The real-VerSe artifact builds reproducibly from a mounted VerSe cohort
  (verified where data is available); the refresh wrapper skips the real-VerSe
  steps cleanly when the cohort is absent.
- The pipeline's false-positive rate on real VerSe GT is quantified and
  recorded (**G3**, **G7**); the verification-table row reads Verified.

---

## Stage 13 — Dataset Ingestion Adapters & Harmonization Schema (G3, G7 enabler)

**Goal.** Decouple the pipeline from any single dataset's on-disk layout, naming
convention, and label scheme by introducing a **dataset-agnostic `Cohort`/`Case`
interface** plus **declarative, per-dataset adapters** that map arbitrary datasets
onto it. Today ingestion (`segqc.reference.ingest.ingest_cohort`) is flat,
non-recursive, and hardcodes a `<id>_scan.nii.gz` sibling, so a nested/varied real
dataset (e.g. VerSe's `derivatives/…_seg-vert_msk.nii.gz` + `rawdata/…_ct.nii.gz`)
can't be read without manual copy/symlink staging. This stage removes that friction
so real cohorts are ingested directly and uniformly — and it is the prerequisite for
doing Stage 12's real-VerSe build/evaluation through a clean interface rather than a
throwaway staging hack.

**Design principle — keep the framework dataset-agnostic.** The framework's three
operations (`run` a case, `build-reference` from a GT cohort, `evaluate` a cohort or
a build+held-out pair) consume **only** a `Cohort` (an ordered, deterministic
iterable of `Case`s). Everything dataset-specific — folder structure, filename
conventions, label mapping, and *how a subset of cases is selected* — lives in the
adapter. A train/val/test "split" is just **one kind of subset** an adapter can
produce; the framework must **not** expect or rely on pre-split datasets (another
dataset might select a subset via a CSV / id-list / glob). This preserves the clean
separation between (1) code/function testing on synthetic fixtures, (2) building a
real-GT reference/heuristic knowledge base, and (3) applying the tool to score new
automatic segmentations (TotalSegmentator, SPINEPS, …).

**Deliverables.**

- **`Cohort` / `Case` interface** (framework side, dataset-agnostic): `Case`
  carries `case_id`, `seg_path`, `scan_path | None`, `role` (`gt` | `candidate`),
  resolved `label_convention`, and optional metadata; `Cohort` is an ordered,
  deterministic collection of `Case`s.
- **Declarative per-dataset descriptor** (YAML/JSON): configurable `data_root`;
  recursive `seg` glob; `scan` template/glob (or none); `case_id` extraction
  (incl. split-subject infixes); `label_convention`; `role`; and optional named
  **`subsets`** (folder / CSV / id-list / glob) — adapter-only, never a framework
  concept.
- **Resolver** (`segqc.datasets`): `resolve(descriptor, *, data_root, subset, role) -> Cohort`, deterministic ordering; the existing flat `ingest_cohort` /
  `build_gt_pass_manifest` gain a `Cohort`-driven discovery path **alongside** the
  flat one (retained for the synthetic determinism fixtures).
- **CLI surface:** `run` / `build-reference` / `evaluate` accept
  `--dataset-schema <descriptor> [--data-root <dir>] [--subset <name|csv>]`, so a
  nested dataset is ingested with **no manual staging**.
- **First committed descriptor:** a **VerSe19** descriptor validated against a
  mounted cohort, reconciling the documented layout/naming drift (nested
  `derivatives/`+`rawdata/` root; `_seg-vb_ctd.json`).

**Dependencies.** Stages 6, 7 (✅ — ingestion + evaluation surfaces exist).
Independent of Stages 8–11. **Unblocks the real-data half of Stage 12.**

**Validation / acceptance.**

- The VerSe19 descriptor resolves a mounted cohort to the expected
  `(case_id, seg_path, scan_path)` triples — including split subjects — with **no
  manual staging**; ordering is deterministic.
- `segqc build-reference` / `evaluate` / `run` accept `--dataset-schema` /
  `--data-root` / `--subset` and produce correct output over a nested dataset.
- The framework operates only on `Cohort`/`Case`; no dataset-specific concept leaks
  into it, and asking the adapter for two disjoint subsets (e.g. VerSe19 train vs
  validation) drives a held-out build-vs-evaluate flow the framework treats as two
  plain cohorts.
- Existing synthetic tests stay green (the flat ingestion path is retained).

---

# Phase 3 — Real-Data Validation (the outcome arm)

> Stages 0–13 answer *"did we build it correctly?"* — on synthetic fixtures,
> goldens, and unit tests. Phase 3 answers *"does it work on reality?"*, which
> is what [`vision.md`](vision.md) §2's measurable outcomes actually ask. These
> stages are gated on **real data and real environments**, not on more code, and
> each one closes a specific objective that is currently 🚧.

## Stage 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7)

**Goal.** Make real ground truth pass. Stages 6/7 calibrated the heuristics
against a synthetic stand-in and recorded an FPR of 0.0; the first real
measurement (2026-07-17, through the Stage-13 adapter) put the **held-out real
VerSe19 FPR at 0.925 (validation) / 0.975 (test)**. The rules are conflating
legitimate real-world variation with failure. This stage re-grounds them in the
real per-level distributions now available in `reference_verse_v1.json` (25
levels, C1…S, from 80 real training subjects).

**The failure is diagnosed, not mysterious.** The four contributing rules, from
the held-out run: `bounds` (4/6 of flagged cases), `fragmentation` (3/6),
`coverage` (3/6 — partial-FOV scans read as "missing levels"), `border` (2/6).
One real case passed entirely clean, which is what rules out a systematic bug and
points at calibration.

**Deliverables.**

- **Reference-derived bounds by default.** Item 048 already built the config
  switch from hand-set to reference-derived bounds; the shipped default is still
  the synthetic-calibrated hand-set one. Ground it on `reference_verse_v1.json`.
- **FOV-aware `coverage` / `border` rules.** The key conceptual fix: real scans
  are legitimately partial (cervical-only, lumbar-only). A level *outside* the
  field of view is not a missing level; a vertebra clipped by the FOV boundary is
  not a border defect. Only levels *expected inside the FOV* may be reported
  missing.
- **`fragmentation` / `bounds` tolerances re-derived** from real per-level
  variation instead of synthetic-clean geometry.
- **Recalibration run** using the Stage-7 `calibrate.py` grid search, fitted on
  the VerSe19 **training** subset and measured on the **held-out**
  validation/test subsets, resolved as disjoint adapter subsets (no circularity —
  the framework sees only "calibration cohort" and "eval cohort").
- **Anti-gaming sensitivity guard.** Re-run the Stage-5 synthetic corpus *and*
  Stage-5 perturbations applied to **real** VerSe GT, asserting per-mode
  sensitivity does not regress below item 057's baseline.
- **Committed G3 target** in `vision.md` §2 + recorded metrics in `progress.md`.

**Dependencies.** Stages 12, 13 (✅ — the real artifact and the adapter exist).

**Validation / acceptance.**

- Held-out real VerSe19 GT yields **FPR ≤ 0.10** (**G3**).
- Per-mode sensitivity ≥ item 057's synthetic baseline (5/8 pipeline-detectable
  modes at 1.0), and those modes still fire on perturbed **real** GT (**G7**).
  *FPR and sensitivity are acceptance criteria as a **pair**: FPR alone is
  trivially driven to 0.0 by loosening or disabling rules.*
- Flags on real cases still carry reasons + offending labels (explainability is
  not traded for specificity).

---

## Stage 15 — Real-XNAT Deployment Validation (G5) — ❌ Excluded

> **❌ Excluded (2026-07-25). Reason:** deployment left this project's scope in the
> `vision.md` §0 supersession — FACET is a library and CLI, not a deployed service, and
> G5 was removed from scope rather than deferred. Nothing here was attempted, so no work
> is lost; the Stage 9 artefacts (`command.json`, `docker/`, `docs/deployment.md`) are
> retained as legacy pending relocation out of this repo. **This stage is not reopened.**
> Everything below is the original text, kept as the provenance trail.

**Goal.** Do what Stage 9 documented. G5's measurable outcome is *"Runs as an
XNAT Container Service command on **real session data**"*; Stage 9 shipped a
validating `command.json`, an entry script, deployment docs, and a CI-verified
`docker build`/`docker run` — but nothing has ever touched an XNAT server. The
install steps were written from the XNAT documentation and never executed.

**Deliverables.**

- A reachable XNAT instance with the Container Service enabled (test/staging is
  fine). **This is an external prerequisite the project does not currently
  have** — the stage is blocked on access, not on engineering.
- Image published where that server can pull it; `command.json` installed +
  enabled.
- One real session (scan + segmentation resource) run end-to-end, reports landing
  back as session resources.
- Deployment docs reconciled with what the real install actually required.

**Dependencies.** Stage 9 (✅). Blocked on XNAT server access.

**Validation / acceptance.** The command runs on a real XNAT session producing
JSON + human reports as resources (**G5**); documented steps match reality; the
verification row flips to ✅.

---

## Stage 16 — Real Failure Corpus & Sensitivity Validation (G2, G7)

**Goal.** Show the heuristics catch the failures a **real segmenter actually
makes**, and build the curated challenging-case corpus §8 of the vision has
always required but which has never existed. Today every §6 failure mode is
detected only on *synthetically perturbed* GT: the corpus proves each mode is
*detectable in principle*, not that real tools produce it or that we catch it
when they do.

> **Retargeted in place 2026-07-25** (this stage was `📋`, never started). **SPINEPS**
> is now the primary reference segmenter rather than TotalSegmentator, and this stage is
> **rung 3** of the realism ladder introduced in Stage 21 — the *validation* corpus of
> real segmenter failures, distinct from Stage 21's rung 2 (real GT + scripted
> perturbation, used for calibration). Depends on Stage 21, which supplies the
> per-mode metrics and the specificity harness this stage's sensitivity claims rest on.

**Deliverables.**

- **Real candidate cohort**: run **SPINEPS** (primary; TotalSegmentator optional as a
  second opinion) over real VerSe CT, ingested as `role: candidate` through the
  Stage-13 adapter and scored against real GT.
- **Real per-mode sensitivity + DICE-vs-flag correlation**, superseding the
  synthetic-only figures in Stage 7's metrics block (Success Criterion 6).
- **Curated challenging-case corpus** — real pathology / post-op / atypical
  anatomy, with expected verdicts (`VerSe_fracture_grading.xlsx` is a natural
  seed) — the direct test of failure-vs-variation on cases that matter.
- **A recorded account of which §6 modes real segmenters actually produce**, and
  at what rate; modes absent from real data are recorded as untested rather than
  silently credited.

**Dependencies.** Stages 13, 14 (calibrate first — sensitivity is only meaningful
against the rules we intend to ship). Feeds Stage 11's abnormality arm.

**Validation / acceptance.** ≥1 heuristic fires on a **real** instance of each §6
mode present in the cohort (**G2**); real DICE-vs-flag correlation measured and
correctly signed (**G7**); curated cases run with recorded outcomes and
legitimate variation is not flagged at Stage 14's FPR bar.

---

# Post-supersession stages (2026-07-25)

> Stages 17–21 are the live work following [`vision.md`](vision.md) §0. Stages 17 and 18
> unblock work on real segmenter output; 19–21 audit what was built while the framework
> itself was the priority. **19 and 20 are pure audit — they touch no production
> behaviour and should run alongside 17/18**, because every later stage that adds or
> retunes a rule is safer once the catalogue and the specificity ratchet exist.

---

## Stage 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6)

**Goal.** Make FACET read another tool's output correctly. Today `segfacet.labels`
defines its own vertebra numbering in which **25 = `S`, 26 = `Cocygis`, 29 = `L6`**,
while the TPTBox convention that SPINEPS emits reads **25 = `L6`, 26 = `S1`, 29 = `S2`**.
Only 28 (`T13`) agrees. Feeding SPINEPS output in with the current defaults **silently
misreads the sacrum as L6** — no error, plausible-looking numbers, wrong. Every
downstream measurement would be quietly invalid, so this stage must land before any
real-segmenter number is computed.

**Deliverables.**

- **Adopt the TPTBox vertebra standard as the default** (`DEFAULT_LABEL_MAP`,
  `CANONICAL_ORDER`), retiring the legacy table. `LabelConvention` stays overridable for
  genuinely foreign inputs. Note TPTBox's `v_idx2name` also carries subregion names from
  `Location` (≥ 40, plus `0: Unknown`) — the 1–33 vertebra range is clean, but filter
  rather than consume the mapping wholesale.
- **TPTBox-backed image layer**: back `segfacet.io`'s `Volume`/`Case` with TPTBox `NII` —
  orientation-safe load, `reorient`, `rescale`/`resample_from_to`, mm-space conversion,
  `zoom`/`affine` — replacing the hand-rolled `_spacing_from_affine`. Keep `Volume`/`Case`
  as the public shape so the ~22 modules importing nibabel migrate behind one seam.
- **Environment migration**: `requires-python = ">=3.11"`, a numpy **range**
  (`>=1.26,<3`) rather than a pin, regenerated `constraints.txt`, and a CI leg on each
  numpy major so the library stays major-agnostic.
- **Run-manifest schema** — the provenance record carried alongside every number:
  segmenter version/SHA, weights hash, post-processing toggles, seed, dataset id, and
  the resolved `numpy`/`TPTBox` versions.

**Dependencies.** None blocking; supersedes nothing.

**Validation / acceptance.** A regression test asserts 25/26/29 now match the TPTBox
table; the reference artifact (`reference_verse_v1.json`, keyed by vertebra **name**)
loads and scores unchanged, proving no re-fit was needed; the suite is green on both
numpy majors (**G6**); a real segmenter output round-trips with correct level names
(**G2**).

---

## Stage 18 — Failure-Mode-Specific Metric Surface (G2, G7)

**Goal.** You cannot improve what you cannot measure per mode. Today the pipeline emits
a verdict and findings, but the quantities that *isolate* a specific failure mode are
either unexposed or recomputed privately inside a rule — e.g. "foreground beyond the main
connected component" is calculated inside `heuristics/fragmentation.py` rather than
existing as a named field anything else can read.

**Deliverables.**

- **Promote stray-component metrics to first-class fields** in `features/components.py`
  (stray volume mm³, count, fraction) and have the fragmentation rule *read* them instead
  of recomputing.
- **A per-mode metric API** mapping each §6 failure mode to the metric that isolates it,
  reusing `eval/overlap.py::compute_overlap` for Dice/Jaccard and its
  `mean_dice`/`volume_weighted_dice` aggregates — no new overlap code.
- **A cohort-level, per-mode report** suitable for comparing two runs of a segmentation
  tool against each other (e.g. with a post-processing step on vs off), so a change in
  behaviour is attributable to a specific failure mode rather than to aggregate Dice.

**Dependencies.** Stage 17 (level names must be right before per-level metrics mean
anything).

**Validation / acceptance.** Each §6 mode has ≥1 named metric that moves monotonically
with injected severity of that mode and is comparatively insensitive to the others
(**G2**); the fragmentation rule's behaviour is unchanged by the refactor (**G7**).

---

## Stage 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8)

**Goal.** Make the feature set reviewable, then review it. `FEATURE_CATALOG` in
`scripts/aide_status_report.py` documents 9 groups / 41 entries and says in a comment
*"Not derived from a filesystem scan: keep in sync by hand"*; a single realised feature
record has **185 distinct leaf paths**. Those count different things (an entry such as
`touches_*` covers six fields), so the gap is not a straight drift figure — but nothing
verifies the two agree, and no document records *which failure mode each feature is for*.

**Deliverables.**

- **A generated catalogue** — realised record shape from `extract_feature_record` plus
  extractor docstrings — replacing the hand-maintained table. Columns: feature ·
  module/item · what it measures · **how it is computed** · units · spacing/scale
  sensitivity · **§6 failure mode(s) targeted** · **rules that consume it** ·
  **status: keep / retune / retire / unwired**.
- **A drift test**: every leaf path in a reference record must be covered; CI fails when
  a feature lands undocumented.
- **A golden-file decision table** — one row per committed golden: what it asserts,
  keep or retire, and what replaces it. Working assumption is **retire most**: the nine
  `tests/corpus/golden/*.json` are whole-record snapshots (~185 leaf paths) of a corpus
  Stage 21 replaces, and every feature retune this stage authorises forces a wholesale
  regeneration, after which the golden diff can no longer distinguish an intended change
  from a regression. Byte-level reproducibility is **not** what they guard — that is the
  separate intra-run `dest1 == dest2` determinism assertion, which is independent of the
  goldens and stays. Report-formatting and schema goldens are the likely survivors.

**Dependencies.** None. **This stage carries the human checkpoint** — `aide.toml` sets
`clarify = "assume"`, so run it through `/aide-spec-queue`, which front-loads the review
so execution can then proceed unattended.

**Validation / acceptance.** The catalogue is generated, not hand-written; the drift test
fails on a deliberately undocumented feature (**G7**); every feature carries a status and
**one of**: a named failure mode · the marker `unwired` · or *statused but mode-unmapped,
with the consuming mode-less rule named* (**G8**); the golden decision table is complete
and signed off.

> **G8 wording amended 2026-08-11.** The original sentence named only two
> states and was unsatisfiable as written by the mechanism this stage shipped: a path
> consumed solely by a rule that carries no §6 mapping (`bounds`, `intensity`,
> `reference_delta`, `intensity_reference_delta`) is statused `keep` with empty
> `failure_modes` and `mode_evidence == ("rule_unmapped",)` — statused, not `unwired`, and
> naming no mode. 72 of 111 entries sit there. The third state is now named explicitly, and
> the *substantive* close is **Stage 20**'s job: map those four rules to §6 modes or record
> that they target none. A rule that consumes features but targets no catalogued failure
> mode is itself the finding.

---

## Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness (G2, G7)

**Goal.** Close the gap between "the suite is green" and "the rules are specific".
Measured on the committed corpus: **10 rules are registered and enabled, but only 4 ever
fire** (`fragmentation`, `coverage`, `border`, `sequence`) — `bounds`, `mislabel`,
`overlap`, `intensity`, `reference_delta` and `intensity_reference_delta` fire on **zero**
cases. **Three of nine cases fire nothing at all** through `run_qc`
(`mode1_displace`, `mode4_relabel_swap`, `mode8_force_overlap`); their intended rule is
reached only by feeding a hand-reconstructed record straight to the rule. That is
documented as item 040's limitation, but the effect is that **three of eight failure modes
are not detected end-to-end while the corpus still reads as covering all eight**.

Separately, `verify_case` asserts the designated rule fires and the offending labels
match — it **never asserts that no other rule fires**. Cross-talk today is 0/9, so the
assertion is free to adopt *now*; once cases become realistic it is expensive to
introduce retroactively.

### What the matrix is — and what it is not *(clarified 2026-08-11)*

The matrix is read in **three directions, only two of which must ever be complete**. This
is the load-bearing distinction of the stage, and Stage 19's G8 sentence originally implied
the opposite:

| Direction | Complete? | A hole means |
| --- | --- | --- |
| **mode → rule** | **Yes, always** | a catalogued §6 failure mode nothing can detect. A defect, and this stage's primary finding. Restates [`vision.md`](vision.md) §6: *"at least one heuristic must detect each"* |
| **rule → mode** | **Yes, always** | a registered rule targeting no catalogued mode — so either the mode catalogue is short a mode, or the rule is speculative. Four rules sit here today (`bounds`, `intensity`, `reference_delta`, `intensity_reference_delta`) |
| **feature → rule** | **No — by design** | *nothing.* The feature record is a deliberately over-broad vector that rules **select from**. A leaf path no rule reads is inventory (`unwired`), not a gap; 34 of item 103's 111 catalogued paths are read by nothing today, and full consumption is never an expected end state |

**Evidence rungs.** *"A rule covers this mode"* and *"we have demonstrated it end-to-end"*
are different claims and each mode's row carries **both**. Three legitimate evidence
states, drawn from Stage 21's realism ladder:

- **synthetic-demonstrable** — a rung-1 fixture drives the rule end-to-end today.
- **needs real data (or a corpus the fixtures cannot express)** — the rule exists but the
  hand-crafted geometry cannot produce the input. Mode 7 is structurally capped at a
  **single** rank descent by the label convention (`rank(v) == v - 1` under the TPTBox
  default), so §6.7's own two-descent example — `L1 → T12 → L2 → L5` — is not representable
  at rung 1 at all; mode 1's severity ladder is FOV-capped by the five-level fixture.
- **structurally unobservable in the supported input format** — the *feature* the mode
  targets cannot occur. Mode 8 (overlap) is exactly this: a **single-channel integer label
  map cannot assign two labels to one voxel**, so `overlaps[]` populates only on a map
  deliberately corrupted to violate that invariant, which no real segmenter output can be.
  The `overlap` rule and all six fields it reads are correct and fully wired — the mode
  becomes meaningfully testable only if multichannel / probabilistic segmentation input is
  ever supported, which no stage currently plans.

A row recording *needs real data* or *structurally unobservable* is an acceptable outcome.
A row that is **silent** is not.

**Growth contract.** The catalogue of modes, the rule set and the feature pool grow
**together, and usually in tandem**: a new §6 mode arrives with the rule(s) that detect it,
plus any new feature(s) those rules need when the existing pool does not suffice. The
matrix is what makes that enforceable — a mode with no rule row, or a rule with no mode
row, fails the same way item 104's drift test fails an undocumented feature. **Features may
be added alone** (an unwired feature awaiting a future rule is legitimate and expected); a
mode or a rule may not.

**Deliverables.**

- The **traceability matrix**, *generated* from item 103's catalogue + the rule registry +
  a corpus run rather than hand-maintained: 8 failure modes × rules × the features each
  rule actually consumes, with the three directions above scored separately, and every mode
  row carrying its evidence rung.
- **Map the four mode-less rules** (`bounds`, `intensity`, `reference_delta`,
  `intensity_reference_delta`) to §6 modes, or record that they target none and why —
  closing Stage 19's G8 shortfall at its root.
- **The specificity assertion** — no unintended rule may fire — adopted as a ratchet.
- **Close the reachability hole for modes 1/4/8** by naming the *mechanism* per mode, not
  just the symptom: mode 8 is single-channel-unobservable (above), mode 1's ladder is
  FOV-capped, mode 4's cause is to be determined by the stage. Made pipeline-detectable
  where the mechanism allows, recorded with its mechanism where it does not. Not both
  silent.
- **Per-rule *and per-operator* corpus-exercise reporting**, so neither "6 of 10 rules fire
  on zero cases" nor "the registered `fuse` operator generates no corpus case at all"
  (`synth/component_shape.py:209` vs `synth/corpus.py`'s `CASE_RECIPE`) can recur unnoticed.
- **Widen item 100's mode-1 ladder base** (a larger FOV, or a base with headroom for a
  30–40 mm displacement) so mode 1's own metric swing is set by the perturbation rather than
  the fixture's walls — the recorded root cause of mode 6's Stage-18 specificity shortfall,
  which should then clear without touching mode 6.

**Dependencies.** Stage 19 (the catalogue supplies the feature↔mode column). ⚠️ Several
Stage-26 remediation defects touch the same surfaces this stage audits (`normalised_delta`
attribution, the RAS `touches_*` face mapping, `neighbourhood.py`'s dead wiring) — auditing
before they are fixed records findings that are about to change.

**Validation / acceptance.** Every §6 failure mode has ≥1 rule **and** a recorded evidence
rung, never silent (**G2**); every registered rule maps to ≥1 §6 mode or is recorded as
mode-less with a reason; every registered rule is exercised by ≥1 case or recorded as
unexercised with a reason (**G2**); the specificity assertion is enforced for every case;
the end-to-end detection count is stated honestly in `progress.md` (**G7**).
**Explicitly not required:** feature→rule completeness — unwired features are a designed
state, not a defect.

---

## Stage 21 — Real-GT Perturbation Corpus (G3, G7)

**Goal.** Move calibration off hand-crafted geometry. The current corpus is built from
synthetic fixtures (`synth/clean_gt.py`) — five stacked lumbar blocks at 1 mm isotropic.
Thresholds fitted against that geometry are fitted against a shape no real spine has, and
as the rule set grows, hand-crafted cases increasingly trip rules they were never meant
to exercise. Real ground truth is the natural base: the perturbation operators already
take label maps, so the change is largely one of input sourcing.

Make the **three rungs of realism** explicit, and stop conflating them:

| Rung | Corpus                                                                | Role                                           |
| ---- | --------------------------------------------------------------------- | ---------------------------------------------- |
| 1    | hand-crafted fixtures (`synth/clean_gt.py`, `tests/synthetic.py`) | fast unit-test scaffolding**only**       |
| 2    | **real GT + scripted perturbation** *(this stage)*            | threshold calibration, regression, sensitivity |
| 3    | real segmenter failures (**Stage 16**)                          | validation                                     |

**Deliverables.**

- The existing `Perturbation` operators re-sourced from **real VerSe GT**, with a manifest
  recording subject IDs, seeds and operator parameters so the corpus is reproducible
  without committing bulk data.
- **A real clean-control baseline** — a *cohort* false-positive rate rather than a single
  synthetic pass case, which is the only honest baseline for G3.
- Threshold calibration and every sensitivity claim moved to rung 2; rung 1 retained for
  fast unit tests only.
- **Act on Stage 19's golden decision** — retire the corpus-snapshot goldens as their
  cases are superseded. Do **not** regenerate the nine snapshots against the new corpus;
  that recreates the same problem one rung up. *(Pulled forward into Stage 29 D1 on
  2026-08-30 — by the time this stage runs, the retirement should already be executed.)*

**Dependencies.** Stages 13 (VerSe adapter), 19 (golden decision), 20 (specificity
harness — the new corpus is exactly what the ratchet is there to police).

**Validation / acceptance.** Every threshold-bearing rule is calibrated against rung 2,
not rung 1 (**G3**); the specificity assertion from Stage 20 holds on the new corpus, or
each violation is recorded with a reason (**G7**); the corpus regenerates reproducibly
from the manifest.

---

## Stages 22–25 — placeholders (authored at the full re-vision)

> Recorded so numbering is stable and dependencies can be named. **Deliberately not
> specified**: each depends on measurements that do not exist yet, and a stage written
> before its evidence would be speculation.

- **Stage 22 — Unified `(scan, seg)` extraction.** One entry point over the paired scan
  and segmentation, replacing the current split between label-map-only and
  intensity-aware paths.
- **Stage 23 — Multivariate normative model.** Replaces the univariate per-level
  percentile z-scores aggregated by RMS. **Carries forward the two `❌ Not met` Outcome
  targets** (held-out real-GT FPR ≤ 0.10; no real-GT sensitivity regression), and absorbs
  the open insight that `reference_delta`'s threshold should derive from the training
  cohort's own percentiles rather than a hand-set constant — the fixed-constant mechanism
  is what cannot clear the FPR target without sacrificing sensitivity.
- **Stage 24 — Failure-mode discovery & typed reference set.** Cluster the feature space
  to surface modes not in the §6 catalogue; curate per-class exemplars.
- **Stage 25 — Segmenter-native perturbations.** Rung 3's generator: perturbations derived
  from what a real segmenter actually does wrong, rather than from a catalogue written in
  advance.

---

# Stages scoped 2026-08-11 (after Stage 19)

> Numbered after the placeholders so numbering stays stable; **both run earlier than their
> numbers suggest** — see each stage's Dependencies. Scoped from triaged
> [`insights.md`](insights.md) entries that had accumulated no owner.

---

## Stage 26 — Carried-Defect Remediation (pre-real-data) (G2, G7)

**Goal.** Clear the defects that Stages 17–19 recorded but were forbidden (correctly) from
fixing in scope, **before** Stage 20 audits the surfaces they sit on and before Stage 21
starts producing numbers from real data. Every item here is a known, diagnosed defect with
a named location — this stage does no discovery.

**Deliverables** (each a candidate item; D1–D3 and D8 are the load-bearing ones):

- **D1 — `normalised_delta` saturation** (`eval/per_mode_cohort.py`). `delta / max(|a −
  baseline|, |b − baseline|)` saturates to exactly ±1.0 whenever one run sits on baseline —
  and 7 of 8 `PER_MODE_METRIC_SPECS` baselines are `0.0`, so any two modes that both return
  to baseline tie at 1.0 and AC13's lowest-mode tie-break decides attribution, blind to
  actual magnitude. Stage 18's run-vs-run **attribution** deliverable does not work as
  specified today; two of its own tests demonstrate the trap.
- **D2 — RAS `touches_*` face mapping** (`features/geometry.py:251-256`, consumed by
  `heuristics/border.py` and `heuristics/fov.py`). Item 094 now reorients every loaded
  volume to RAS, so `x == 0 → touches_inferior` names the **left-right** axis: every
  `border`/`fov` finding on data read through `segfacet.io` is anatomically mislabelled.
  Must land before real data, or Stage 21's findings inherit the error.
- **D3 — golden-fixture test hygiene.** `tests/golden/*.json` is the only committed
  byte-reproducible text fixture family absent from `.gitattributes` (latent Windows-CI
  break, three prior instances documented); and
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` **writes its own golden and
  skips** when the file is missing, so deleting the golden makes the check pass. Both
  goldens are dispositioned *retire* by item 105, so "fix or retire" — whichever comes
  first.
- **D4 —** `eval/per_mode.py::compute_per_mode_metrics` gains an optional
  `overlap_result=` so the Stage-7 harness stops paying for a second full overlap pass per
  case.
- **D5 —** scope `test-numpy-majors` (`.github/workflows/ci.yml`) off the Docker- and
  PyRadiomics-gated modules; it exists to test numpy-major agnosticism and currently
  doubles the repo's exposure to Docker Hub rate-limiting for no verification value.
- **D6 —** refresh `heuristics/bounds.py`'s comments, which still name the retired `S` /
  `Cocygis` labels (behaviour is correct; the comment is not).
- **D7 —** resolve `progress.md`'s Stage 17 acceptance box, whose `- [x]` contradicts its
  own annotation (*"Not ticked: no real SPINEPS output is available…"*). Maintainer's call
  between untick / reword / a third state.
- **D8 — `features/neighbourhood.py` is dead wiring.** Stage 3's ✅ deliverable claims local
  vertebra-neighbourhood comparison "flags isolated anatomical outliers"; the module is
  implemented in full and referenced by **nothing** — not `pipeline.py`, not
  `feature_report.py`, not any of the 10 rules — so it never reached item 103's catalogue
  and no verdict has ever been influenced by it. Wire it (deciding whether it needs a
  consuming rule, and reconciling its mean/std deviation score with the percentile-based
  `robust_z` machinery), or retire it and correct the Stage 3 claim.
- **D9 — the byte-hash scope fences are the wrong instrument, and are now a tax on every
  item in this stage.** Five items (099, 100, 101, 103, 105) pin SHA-256 digests of
  committed source as "untouched" fences, and item 106 extends the pattern to individual
  `progress.md` rows. A fence encodes a **diff-time** property (*"item N did not modify file
  X"*) as a **permanent runtime invariant** (*"X equals these bytes forever"*) — a different
  and false claim as soon as a later item is legitimately authorised to edit X, which is the
  normal case. Record to date: **six documented failures** — three Windows-CI-only and
  invisible to every local gate, one where the pinned digest was never reproducible even on
  an unchanged tree (`rglob("*")` swept `__pycache__`), two collisions with a later item's
  authorised edit — and **no recorded true positive**. Item 104's Decisions log already
  reached this verdict and made its equivalents "git-diff obligations on the validator, not
  pytests"; 104 and 106 use that pattern, the rest are legacy. Retire the fences and land
  the deterministic check they were reaching for: a spec-declared authorised-path list
  diffed against `git diff --name-only $(git merge-base main HEAD)`. **The check belongs to
  the branch, never to pytest** — a diff-scope assertion has nothing to assert once merged,
  and forgetting that is what produced the fences. Preserve what is *not* a fence: intra-run
  determinism assertions, item 104's drift test, item 098's expected-value baselines. The
  durable home for the check is the framework (`aide-loop`); this stage prototypes it here
  so the upstream change is a port of something proven rather than a design sketch.

**Dependencies.** None. **Runs next, ahead of Stage 20** — D1/D2/D8 change surfaces Stage
20 audits, so auditing first records findings that are about to move. D2 is additionally a
prerequisite for any real-data claim (Stages 16/21).

**Validation / acceptance.** Each defect has a regression test that fails before the fix
(**G7**); `border`/`fov` findings carry anatomically correct face names under RAS (**G2**);
per-mode attribution distinguishes a large move from a small one on a fixture built to have
both; `neighbourhood.py` is either reachable from `extract_feature_record` and present in
the regenerated catalogue, or removed with the Stage 3 deliverable reworded; no
`_PRE_NNN_*` byte-hash fence remains, and the diff-based scope check that replaces it flags
a deliberately out-of-scope edit on a scratch branch (**G7**).

---

## Stage 27 — Feature Schema Taxonomy & Coordinate System (G8)

**Goal.** Give the feature record a **deliberately designed structure** in place of the
current one, which groups fields by *which extractor module happened to compute them*.
Item 106's full 111-entry steering review found this to be the single recurring theme behind
roughly two-thirds of its per-field `retune` verdicts: those verdicts are symptoms of one
structural problem, and executing them one field at a time would entrench the same shape.

**This stage designs the taxonomy; it does not inherit one.** The maintainer's framing —
group by **scope** (`per_label` / `per_neighbour-pair` / `per_scan`-or-case-level) crossed
with **kind** (shape/geometry · intensity · label-identity · …) — is the **starting
proposal and the standard of quality**, not a specification to implement literally. The
stage is expected to evaluate it against the real 111-entry record, and **may deviate where
it has a recorded reason to**: a different axis, an extra dimension, or a flat scheme for
part of the record are all acceptable outcomes *provided the deviation and its rationale are
written down* alongside the design. What is not acceptable is another grouping that happens
to fall out of module provenance.

**Deliverables.**

- **The taxonomy itself**, written down as a design with its rationale, the alternatives
  considered, and every deviation from the scope×kind starting proposal justified — reviewed
  with the maintainer before migration begins. This is a human-checkpoint stage in the same
  sense Stage 19 was.
- **The migration**, applied to the record shape, with item 104's drift test as the safety
  net and item 103's catalogue regenerated against the new schema.
- **Known instances the design must have an answer for** (evidence, not a to-do list):
  identity fields (`label` / `level_name`) independently duplicated across
  `stage3.per_label_offsets[]`, `stage3.per_label_orientations[]`, `image_features.per_label`
  and `reference_delta.{label}`; `stage3.*` / `image_features.*` sitting as top-level
  containers parallel to the `per_label.{label}.*` structure that already holds
  geometry/components/centroid; image-axis-relative shape features (axis-aligned
  bbox/extent, `principal_axis`) flagged for re-expression in a **vertebra coordinate
  system** that does not yet exist — the same axis-semantics problem Stage 26's D2 fixes for
  `touches_*`; and the reference-delta machinery being hardcoded to one tracked feature
  (`physical_volume_mm3`) when it should take any requested feature — which only becomes
  coherent once the record is organised well enough to *select a feature set* from.

**Dependencies.** Stages 19 (the catalogue is the map of what moves) and 20 (the matrix says
which features are load-bearing before any of them are renamed). Should land **before**
Stages 23/24, which both consume the feature vector as a vector. This stage renames leaf
paths wholesale, so it is the natural moment to execute item 105's golden retire
dispositions if Stage 21 has not already. *(Superseded 2026-08-30: Stage 29 D1 owns the
retirement and runs before both.)*

**Validation / acceptance.** The taxonomy is documented with its rationale and every
deviation from the starting proposal justified, and is signed off by the maintainer before
migration (**G8**); every feature is addressable under it and no identity field is stored
more than once; the regenerated catalogue and the drift test agree; no rule's behaviour
changes on the corpus except where a retune is explicitly authorised.

---

## Stage 28 — Spinal Curve Model: Formulation, Offset & Orientation (G2, G7)

**Goal.** The spinal curve is fit with an **interpolating** spline
(`features/spline.py`, `splprep(..., s=0)`), so it passes exactly through every centroid it
is meant to judge. Two features derived from it are therefore structurally incapable of
carrying signal, and one downstream rule can never fire:

- `stage3.per_label_offsets[].offset_mm` is **zero on every case**. Across the nine
  committed goldens its maximum is `6.8e-04` mm against `mislabel`'s `max_offset_mm = 15.0`
  — four orders of magnitude short. It is not synthetic-only: `reference_verse_v1.json`,
  built from real VerSe19 GT, records `spline_offset_mm` with mean `2.9e-05` mm and
  CoV 1.3, i.e. noise about zero. A per-level reference distribution has been committed for
  a feature that measures nothing.
- `stage3.monotonic_consistency.is_monotonic` is **`True` on every case**, including
  `mode4_relabel_swap`. The interpolating spline is fit through the centroids in ascending
  label order, so it detours through the swapped pair and its own parameter increases along
  the detour. Monotonicity is true by construction, never observed.

Eight leaf paths are affected in total — `offset_mm`, `offset_voxel`, `dx_mm`, `dy_mm`,
`dz_mm`, and all three `per_label_neighbourhood[].stats.offset_mm.*`, meaning item 110's
neighbourhood wiring computes mean/median/std of zeros. `MislabelRule` is unreachable
through `run_qc` on any input, which is why 6 of 10 registered rules fire on zero corpus
cases.

**This is one defect, not two.** Stage 20's roadmap entry treats mode 1 (FOV-capped
displacement) and mode 4 (cause "to be determined") as separate reachability holes. Both
are the interpolating fit. A smoothed fit detects the mode-4 swap directly
(`non_monotonic_pairs=(('L2','L3'),)`, clean control unaffected), and no field of view
produces a non-zero offset while `s=0` holds — so Stage 20's proposed FOV-headroom remedy
could not have worked.

**The deliberation comes first.** The formulation is a modelling decision with a clinical
prior, not a parameter to tune until the corpus goes green: the model must be flexible
enough to represent real spinal shape (cervical lordosis / thoracic kyphosis / lumbar
lordosis — an S in the sagittal plane; a coronal curve under scoliosis, single or double)
while being **too stiff to follow a segmentation error**. Those two requirements pull
against each other, and the tension is the whole problem — a curve fit from the centroids
and then used to judge a centroid is circular unless something breaks the circle. So the
stage opens with a recorded design decision, evidenced against real GT, before any
calculation changes.

**Deliverables.**

- **D1 — the spline formulation decision, recorded before implementation.** What family
  (smoothing spline, fixed-knot least-squares B-spline, per-plane low-order polynomial,
  robust/principal-curve fit); how degrees of freedom are set and how they scale with the
  number of levels present, since a field of view may show five lumbar levels or a whole
  spine and a fixed knot count cannot serve both; whether the curve is parameterised by arc
  length or treated as a function of the cranio-caudal coordinate — noting that the latter
  is monotonic by construction and would destroy the mode-4 signal this stage exists to
  restore; how the circularity is broken (leave-one-out, robust down-weighting, or an
  external reference prior); and what a scoliotic spine must be able to express without
  being flagged. Judged against measurable criteria on GT, not argued in the abstract.
  **Raises a human gate** — the deformity envelope the model must represent is a clinical
  judgement, not derivable from the corpus.
- **D2 — the formulation implemented**, replacing `s=0`, with the smoothing/DoF parameter
  expressed in a scale-free form. `splprep`'s `s` is an absolute sum-of-squared-residuals
  bound in mm², so a literal constant cannot survive a change of level count or spacing.
- **D3 — per-vertebra offset that separates.** Including its per-direction components
  (`dx/dy/dz_mm`), which are computed and catalogued today but read by no rule. A
  leave-one-out fit tracks displacement roughly 1:1 (measured: 5 → 6.2 mm, 10 → 10.4 mm,
  15 → 16.0 mm) and is already implemented inside the test harness as
  `_recon_leave_one_out_offset`; promoting it into the pipeline retires mode 1's
  `reconstructed_record` workaround rather than working around it.
- **D4 — tangent-based vertebra orientation.** PCA's `principal_axis` returns exactly
  `(1, 0, 0)` for every vertebra of the default fixture with identical `eigenvalue_ratio`:
  the voxel cloud is a box and PCA finds its widest side, which is left-right on a real
  vertebra too. It carries no per-vertebra information. Both ingredients for the
  replacement already exist — `closest_u` in `spline_offset.py` and `splev(..., der=1)` in
  `orientation.py` — but are never joined: the tangent is evaluated at `fit.u`, not at the
  centroid's closest point, and is collapsed to a scalar angle. Retain `eigenvalue_ratio`
  (real-GT CoV 0.155, genuinely informative); demote `principal_axis`.
- **D5 — signed curvature.** `total_curvature_deg` is `max − min` of the *unsigned* angle to
  the cranio-caudal axis, so it reports 5.702° on the clean fixture whose true tangent sweep
  is 11.4°: it halves a C-curve and cancels a symmetric S-curve — the shape a normal spine
  actually has.
- **D6 — recalibration and regeneration.** `max_offset_mm`, the nine goldens,
  `reference_default.json` and `reference_verse_v1.json`. The VerSe19 cohort is available
  locally (80 CT/GT pairs) and reachable via a gitignored symlink at the documented root, so
  the real artifact is rebuildable rather than stale — see `dataset-verse19.md`, whose
  documented nested layout needs correcting to match.
- **D7 — an observed-range column in the generated feature catalogue.** The catalogue is
  current and its `computation` column is accurate, but it has no column for what a feature
  *does*: `offset_mm`'s row reads healthy while the value is a constant zero, and its
  `status` is `retune`, shared with 65 of 128 rows. Recording each numeric path's observed
  range across the corpus and the reference cohort is the check that would have caught this
  at item 018 instead of after a reference build on real data.

**Scope fence.** The rethink is **bounded to the spline layer**. A sweep of every numeric
leaf path across both populations found no other degenerate feature: the 21 features in the
real-GT reference all carry genuine spread (CoV 0.06–3.6) except `spline_offset_mm`. The
153 paths that are constant across the committed goldens are constant because all nine
fixtures are the same box built from one base — Stage 21's premise, not a feature defect —
and the corpus cannot by itself distinguish the two cases. Do not widen this stage on that
evidence.

**Dependencies.** Stage 26 (✅). **Runs before Stage 20**, for the same reason Stage 26 did
and more directly: Stage 20 audits rule↔mode↔feature traceability and adopts a specificity
ratchet, and this stage changes which rules fire on which cases. Auditing first would
record a matrix that is about to move, and would pin a specificity baseline against a
corpus where `mislabel` cannot fire.

**Validation / acceptance.** The formulation decision is recorded with its measurements and
signed off at its human gate before D2 lands (**G8**); a clean GT spine stays within a
**1.0 mm** pass-through bound across level counts and spacings, while a displaced vertebra
separates from the clean distribution by a stated margin (**G2**); `mislabel` fires through
plain `run_qc` on the mode-1 case and `is_monotonic` is `False` on the mode-4 case, with the
clean control still firing nothing (**G2**); a real scoliotic curve in the VerSe cohort is
not flagged as an offset outlier (**G3**); both reference artifacts are rebuilt from real GT
and `spline_offset_mm` shows real spread; every regenerated golden is byte-reproducible
run-to-run (**G7**).

**The pass-through bound was raised 0.5 mm → 1.0 mm on 2026-08-28.** This acceptance line
originally reused item 017's AC1 tolerance, which is a *unit* tolerance measured on that
item's own GT-like fixtures, and stretched it over a much wider domain — `build_clean_spine`
at every level count and spacing. The approved smoothing formulation (item 118's gate,
approved 2026-08-27) does not satisfy the stretched version: measured under it, item 017's
fixtures peak at `0.19198` mm while the sweep peaks at `0.552139` mm at 5 levels ×
`(0.8, 0.8, 1.0)` spacing. That is a property of the decision, not a defect — an
interpolating spline passed through every centroid by construction and so satisfied any
bound at all, including on broken input, which is the behaviour item 118 set out to retire.
1.0 mm is sub-voxel at every spacing on the grid and leaves ~1.8× headroom over the measured
peak. Item 017's AC1 keeps its own 0.5 mm tolerance on its own fixtures — it is unaffected
and was not weakened.

---

# Stage scoped 2026-08-30 (queue-017 boundary triage)

> Same construction as Stages 26–28: numbered after the placeholders so numbering stays
> stable, **runs earlier than its number suggests**. Scoped from the carried defects the
> queue-017 triage routed to this file plus the two surviving 2026-08-25 entries — every
> deliverable is a known, located defect or an already-signed decision awaiting execution;
> this stage does no discovery.

## Stage 29 — Golden Retirement & Test-Artifact Hygiene (G2, G7)

**Goal.** Execute the maintainer-signed retirement of the whole-record snapshot goldens and
make "comparing against a committed artifact" reach for numeric tolerance by construction —
then sweep the small located defects that queue 017 recorded but was (correctly) forbidden
from fixing in scope. The motivating cost is measured, not speculative: items 119/120/123
each regenerated nine snapshot goldens plus both reference artifacts and touched ~8 pinning
test files, and three of those items' test-writing passes reintroduced byte-exact
comparisons against committed float-carrying artifacts that only PR #56's CI matrix caught
(~1 ULP float drift across numpy versions and platforms).

**Deliverables** (each a candidate item; D1–D2 are the load-bearing ones, D3–D5 batch
naturally, and D1 should land first so D5/D7/D8's regeneration surface is already smaller):

- **D1 — execute the golden retirement.** All 11 snapshot rows of
  [`golden-decision-table.md`](golden-decision-table.md) (the nine `tests/corpus/golden/*.json`
  whole-record reports and the two `tests/golden/` snapshots, items 016/022) are
  maintainer-dispositioned **retire** (signed 2026-07-28, item 106), with the four
  replacements specified per row: (i) intra-run determinism survives via the existing
  run-to-run tests; (ii) schema validity re-points at a freshly built report; (iii) the
  load-bearing "verdict/findings unchanged" use moves to a narrow verdict+findings shape
  expectation that pins no feature values and so survives a feature retune; (iv) Stage 21's
  real-GT corpus takes over the snapshot role. Execution was assigned to Stage 21 (or 27,
  whichever first) and is pulled forward here — it needs no new corpus, and every queue
  meanwhile pays the regeneration cascade. Do **not** regenerate the snapshots on the way
  out; that is the exact move the disposition forbids.
- **D2 — tolerance by construction.** A shared comparison helper whose name makes
  "fresh output vs committed artifact" go through `reports_close`-style numeric tolerance,
  plus a guard test extending `tests/test_111_golden_guard.py`'s hand-surveyed
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` into an enforced allowlist: a new byte-exact
  comparison of freshly generated output against a committed float-carrying artifact fails
  with a message naming the helper. The spec carries item 124's emission-clamp rule for
  what legitimately stays byte-compared: an artifact reporting a raw float measurement
  alongside its own "meaningfully nonzero" threshold must clamp sub-threshold noise to a
  fixed sentinel at the serialisation boundary (`segfacet.observed_range.emission_range`
  is the shipped example — quantisation cannot stabilise cancellation-scale noise), and
  a spec that changes a feature the reference artifact aggregates must survey every
  consumer mechanically (`grep -l build_and_write_default tests/`), not by hand-listing.
- **D3 — relocate the surviving artifact-integrity pin, rename the mislabelled fence.**
  `tests/test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged` pins
  `reference_verse_v1.json`'s bytes under an item-098 scope-fence name; the invariant is
  legitimate (a released production artifact must not change silently) but belongs in a
  test named for the artifact beside `reference/artifact.py` — carrying its
  `.gitattributes` pin across deliberately, since engine 1.19.0's lint cannot see a path
  reached through a helper function. And `tests/test_102_stage18_validation.py`'s
  `# AC24: the scope fence` header sits over a legitimate intra-run determinism assertion —
  renaming the header to say what it checks is the whole fix. *(Both routed 2026-08-25.)*
- **D4 — `fit_centroid_spline` degenerate input.** `features/spline.py` propagates SciPy's
  bare `ValueError: Invalid inputs.` when all supplied centroids are exactly coincident;
  degrade gracefully or raise a descriptive error naming the cause, and let item 122's
  substituted 1e-6 mm adversarial fixture become the real all-coincident case.
- **D5 — the 4-centroid silent zero.** `compute_leave_one_out_spline_offsets`'s `< 4`
  in-sample fallback boundary is one too low: at `k = 3` with four points the held-out
  refit interpolates and every offset reads exactly `0.0` (measured on real
  `sub-verse065`), so a 4-level field of view cannot raise a `mislabel` offset finding.
  Move the boundary to `< 5` and regenerate the affected reference distributions.
- **D6 — spline plumbing consolidation.** The coarse-scan-plus-`minimize_scalar`
  closest-point search exists three times (`features/spline_offset.py`,
  `features/consistency.py`, `scripts/compare_curve_candidates.py`) with no link between
  them, and the pipeline fits the identical in-sample spline twice per case (`pipeline.py`'s
  curvature fit and `spline_offset.py`'s internal reference refit). One implementation,
  one fit.
- **D7 — `tangent_angles_deg[]` traversal-direction normalisation.** The unsigned angle to
  `+S` reads ~175° per level on a cranial-first centroid sequence and ~5° on a caudal-first
  one — same spine, two readings, latent only because every committed fixture happens to
  advance superiorly. Normalise to the convention item 122 already established for its
  signed per-plane arrays, so the record carries one tangent-angle convention.
- **D8 — give the mode-4 acceptance an owner.** Stage 28 asserts a smoothed fit detects
  the mode-4 swap via `is_monotonic == False`, but no queue-017 item owned
  `features/consistency.py`, and the criterion is measured unmet (item 125's replay pins
  `is_monotonic == True` on `mode4_relabel_swap`). Make the monotonicity check judge the
  smoothed fit so the swap fires, closing Stage 28's unticked mode-4 acceptance half.
- **D9 — bump `tptbox` to ≥ 0.7.6.** The 0.7.5 wheel's published metadata declares AGPL
  v3.0 while TPTBox's `LICENSE` is Apache-2.0; upstream fixed the metadata in v0.7.6
  (TPTBox PR #119). A dependency bump's regression surface is the golden corpus — smaller
  after D1, which is why this sits here and not in a drive-by edit.
- **D10 — `scripts/refresh_reference.py --verse-cohort` has never worked.** It hands the
  cohort root to `ingest_cohort`, which lists one directory non-recursively and hardcodes
  `_scan.nii.gz` siblings — incompatible with VerSe's layout, so the wrapper records
  `verse-build: failed` by construction. Delegate to item 123's
  `scripts/rebuild_verse_reference.py` or retire the mode.
- **D11 — split the decision table's live counts from its signed judgement.**
  `golden-decision-table.md`'s `N/M leaf paths unwired` cells are live values off
  `build_catalogue()`, so every feature-adding item (106, 110, 122) edits a human-signed
  document to refresh a count while asserting no judgement moved. Generate the measured
  counts into a small companion artifact the signed document references, so a count
  refresh never touches signed text.

**Dependencies.** None. **Runs next, ahead of Stage 20** — D1/D7/D8 change the surfaces
Stage 20 audits and the specificity baseline it pins, and D8 closes a Stage 28 acceptance
line Stage 20 would otherwise re-record as a reachability hole. The Stage 21 deliverable
"Act on Stage 19's golden decision" and Stage 27's "natural moment to execute item 105's
golden retire dispositions" are both superseded by D1.

**Validation / acceptance.** The nine corpus snapshot goldens and both `tests/golden/`
snapshots are gone with all four named replacements in place, and no snapshot was
regenerated on the way out; the D2 guard fails a deliberately added byte-exact comparison
against a committed float-carrying artifact on a scratch branch (**G7**);
`mode4_relabel_swap` yields `is_monotonic == False` through `extract_feature_record` and
Stage 28's mode-4 acceptance half is closed (**G2**); a 4-level field of view yields
non-degenerate held-out offsets; `pip show tptbox` reports a non-AGPL licence; each fixed
defect carries a regression test that fails before the fix (**G7**).

---

# Backlog — unowned ideas

> Recorded so they are not lost. **No stage owns these**; each was raised deliberately as
> "consider later, not now". Promote to a stage when its evidence exists.

- **Leave-one-out / counterfactual sensitivity feature** *(maintainer, 2026-07-28)*. For a
  given vertebra, measure how much a scan-level shape metric (e.g. spline
  smoothness/curvature) changes under a hypothetical modification of that vertebra —
  dropping its label, or merging it into its largest bordering neighbour — as a measure of
  that vertebra's structural influence on the whole spine. Distinct from both the population
  reference (`reference_delta`) and the local-neighbourhood comparison (Stage 26 D8): this
  is an *ablation*, not a static comparison. Closest neighbours are Stages 20 (specificity,
  not a new feature), 21 (perturbation corpus, not a counterfactual) and 23 (normative
  model, framed around thresholds).
- **How should the synthetic fallback reference be generated at all?** *(maintainer,
  2026-07-28)*. `reference_default.json` is built from a 5-subject **synthetic** cohort
  (`build_clean_spine` + `paint_clean_scan(seed=0)`); it is no longer the CLI default
  (`reference_verse_v1.json`, 80 real VerSe19 subjects, has been since item 090) and is kept
  as a fixed fallback / synthetic-regression fixture. Open question: derive it from
  published anatomical value ranges instead of synthesised geometry, and/or adopt a
  realistic synthetic-data toolkit. *(The narrower, actionable half — a plausibility check
  that its ranges have not drifted relative to the real artifact — is a Stage 21
  deliverable, not backlog.)*
- **Multichannel / probabilistic segmentation input.** Not planned. Recorded because it is
  the precondition that would make §6 mode 8 (overlap) observable on real data at all — see
  Stage 20's evidence rungs.
- **Feature and metric normalisation policy** *(2026-08-12)*. Two rules govern every scaling
  decision, and they are project-wide rather than specific to any one metric:
  1. **A normalisation factor must never introduce a supervision dependency.** Anything
     derived from ground truth — "the levels this scan *should* have", a GT label count, a
     reference annotation — is supervision, not a feature. Scaling by it produces a number
     that cannot be computed on real segmenter output, which is the setting FACET exists to
     analyse, and quietly mixes supervision into the feature space. This holds even for
     metrics that are themselves defined as a candidate-vs-GT comparison: that a metric
     *needs* GT does not license its **scale** to import further GT-derived quantities.
  2. **Normalisation is human-reviewed, or it does not happen.** The exception is a scaling
     that is intrinsic by construction — a metric already dimensionless, or bounded 0..1 with
     a derivable full swing, where the denominator comes from the metric's own definition and
     no judgement is exercised. Everything else needs an explicitly reviewed and recorded
     constant or threshold, in the manner of item 106's steering review. **The default, absent
     review, is no normalisation**: report the raw value.

  Applied to the per-mode metrics: the fraction-valued ones scale intrinsically;
  `rogue_island_count` (a *maximum over per-label entries*, so a scan-level denominator would
  change the quantity anyway) and `missing_level_count` (whose only natural denominator is
  GT-derived, barred by rule 1) both stay **raw** until a reviewed threshold exists. For rogue
  islands the clean expectation is *none*, so a small declared threshold is the plausible
  candidate — value **TBC**, and item 109 ships the mechanism without setting it.

  Where no reviewable global constant is defensible at all, the fallback is
  **neighbourhood-relative** comparison — a vertebra measured against its own neighbours
  rather than against anything global or supervised. Item 110's generalised neighbourhood API
  (arbitrary named features, selectable scored subset) is the mechanism; coupling `eval/` to a
  `features/` refactor was deliberately kept out of Stage 26. A natural fit for **Stage 27**,
  which is already generalising `reference_delta` off its single hardcoded tracked feature.

- **Does the Stage 18 thesis have any real-data demonstrator left?** *(2026-08-14)*. Item
  109's AC16 demonstrator turned out to rest on the very saturation bug that item fixed:
  stripping stray islands from `mode3_inject_islands` reconstructs the candidate to exactly
  GT, so modes 1/2/3 all land on their own baseline and every one saturates to
  `abs(normalised_delta) == 1.0` under the pre-109 formula. The "large fraction of its
  excursion" that made the demonstrator look convincing was an artefact, not a signal: under
  the fix, mode 2's genuine movement on that real fixture is ~0.0007, single-voxel scale.
  The headline claim — a *real* corpus case where an unbounded per-mode metric's magnitude
  dramatically beats aggregate Dice — currently has only a hand-built synthetic fixture
  behind it. Demonstrating it on real data again needs a corpus case designed for genuinely
  large per-case magnitude, which makes this a natural rider on **Stage 21**'s perturbation
  corpus rather than an idea in its own right.

- **`feature_docs.STATUS_OVERRIDES` has no sanctioned retirement path** *(insights.md,
  item 122, 2026-08-27)*. The overrides are a verbatim transcript of the item-106
  maintainer walkthrough, so an item that *fixes* a recorded concern (item 122 split
  `total_curvature_deg` per plane, partly delivering its override's ask) cannot rewrite
  the recorded human call from inside an item. Needs either a dated append-trail
  convention like `insights.md`'s, or a queue-boundary review pass that re-asks the
  maintainer. Same signed-text-vs-live-state family as Stage 29 D11 (the decision table's
  measured counts), but unlike a count refresh this one needs the maintainer's judgement,
  so it stays a decision rather than a deliverable.
- **Is a scoliosis-vs-normal envelope FACET's to build at all?** *(insights.md, item 118,
  2026-08-27)*. Stage 28's deformity envelope is one threshold over all anatomy; the
  anticipated refinement — separate normal and scoliotic envelopes — is **pathology
  differentiation**, a different objective from deciding whether a *segmentation* is
  wrong. Recorded in `docs/spinal-curve-model.md` §"The deformity envelope is expected to
  be revised"; whether it belongs in FACET is a `vision.md` question to answer there
  before any item implements it.
- **Held-out offset estimator: two known blind spots, deferred by owner decision**
  *(insights.md, items 120/123, 2026-08-28/29)*. (i) Only the single dominant outlier is
  withheld per refit, so with ≥2 genuinely displaced levels a clean vertebra can outread
  an actual offender (measured: clean 31.96 mm vs displaced 19.31 mm on the two-opposite-
  displacements adversarial case) — natural follow-up is withholding every level above an
  outlier cutoff. (ii) Sequence-terminal vertebrae are excluded outright (item 123), so a
  genuinely displaced terminal vertebra is not looked at — yet terminals are 41/45 of the
  ≥6 mm VerSe19 outliers. Real treatments: a separately calibrated terminal threshold, an
  extrapolation-aware estimator, or a curvature model not needing both neighbours.
- **Adjudicate `sub-verse406_split-verse261` T10 before treating `max_offset_mm = 13.0`
  as settled — it currently holds Stage 28's G3 box open** *(insights.md, items 123/125,
  2026-08-29/30)*. Its interior T10 reads 18.51 mm held-out offset — the single value that
  set the calibrated 13.0 mm threshold, and, measured end-to-end on 2026-08-30, the one
  real scoliotic subject (of the 17 the selection rule picks) that trips `mislabel`
  through the shipped pipeline. Whether that reading is genuine anatomy the envelope must
  accommodate or a GT labelling artefact decides both whether 13.0 mm is calibrated on
  signal and whether Stage 28's "no real scoliotic curve flagged as offset outlier"
  acceptance can tick. Needs a person looking at the case, not more measurement.

# Carried defects — no stage owns them yet

> Distinct from the ideas above: each is a **known, located defect** that survived its
> originating item because the file it lives in was outside that item's authorised paths.
> Stage 26 was the vehicle for this class and has closed ✅. Routed here from
> `insights.md` at triage (2026-08-25, then ten more on 2026-08-30) so the next
> `/aide-create-queue` sees them. **Stage 29 was scoped from this section on 2026-08-30**
> and took ownership of everything routed here except the entry below, whose remedy is a
> process decision rather than code — see Stage 29's deliverables for the moved entries
> (each names its originating `insights.md` date).

- **The `scope-check` CI job matches nothing under this repo's git mode.**
  `.github/workflows/ci.yml`'s job resolves its item number from an `aide/NNN-` head ref,
  but `[git] mode = "auto-merge"` means an item branch is merged and deleted locally and
  never becomes a PR, and a queue PR's head is `aide/queue-NNN`, which the anchored `sed`
  deliberately declines. Every PR this repo actually opens therefore skips while reporting
  SUCCESS — a gate that decayed as the branching model changed, not one that never worked.
  Per-item scope is still enforced by `validator.md` step 3 running `aide scope` in-loop, on
  one machine and one platform, which is the conventions §7 blind spot exactly. Three
  options are recorded in the insight: retire the job and state that the validator is the
  gate; give the queue PR a job that enumerates the items merged into the queue branch and
  runs `aide scope NNN --base <queue base>` for each (what engine 1.8.0's `--base` enables,
  and the real answer for the queue-PR model); or add `workflow_dispatch` as a manual
  stopgap. The framework half is answered — engine 1.18.1's `conventions.md` §4 now states
  per mode what CI gate is possible — leaving this half project-owned and open.

  **Engine 1.20.0 changed the cost comparison between those three options**, in favour of
  switching `[git] mode` to `pr`. That route previously carried a branch-deleting footgun
  independent of the CI question, and 1.20.0 removed both halves of it: `✅` used to mean
  "merged" under `auto-merge` but only "pushed and awaiting review" under `pr`, and `aide
  gc`'s `✅` ground deleted a branch locally *and* on the remote without asking git whether
  the work had landed — so under `pr` the queue-exhaustion sweep offered to delete the head
  branch of an open PR, with the approval line reading like confirmation. `✅` now means
  merged in every mode, written by `aide merge` when the merge happens, with `🔍 In Review`
  as the state between; and `gc` now asks `git merge-tree` whether merging the branch would
  change its base, skipping any `✅` item whose branch still carries unlanded content. So
  option (a) — switch to `pr`, which makes the existing job work as designed with no
  workflow changes at all — is now a straight trade of one human PR-open per item against
  an independent second-platform scope signal, with none of the collateral risk it used to
  carry. *(insights.md 2026-08-20, item 117; re-assessed against engine 1.20.0 on
  2026-08-25)*
- **Mechanically verify the golden decision table's `asserted by` column in both
  directions, including indirect consumers** *(insights.md, item 126, 2026-08-30/31)*.
  `tests/test_105_golden_decision_table.py` AC6 checks that every named test exists;
  nothing checks that every consuming test is named — an AST sweep on 2026-08-30 found
  twelve consuming modules against the six listed, so item 126's blast radius was three
  times the queue's estimate, and even that sweep missed consumers reaching a golden through
  another module's `GOLDEN_PATH` attribute (test_119/120/123 piggybacking on test_022).
  Candidate item: a completeness check in the other direction (or a generated column, as
  item 134 did for the evidence counts) whose sweep also matches shared-attribute idioms
  (`\.GOLDEN_PATH\b`) across the whole tree.
- **`test_082_verse_build_recipe.py::test_adv_determinism_two_builds_produce_equal_parsed_artifacts`
  compares two same-platform builds with numeric tolerance** *(insights.md, item 127,
  2026-08-31)*. Every sibling regeneration test (test_063/081/120/123) asserts byte-identity
  for two fresh in-process builds and drops to tolerance only fresh-vs-committed; as written,
  a run-to-run nondeterminism in the `segfacet build-reference` CLI path passes unnoticed.
  Candidate item: tighten it to byte-identity.
- **A collapsed or duplicated label set can pass silently once Stage 3 degrades on
  coincident centroids** *(insights.md, item 129, 2026-08-31)*. Two labels sharing an exact
  centroid make Stage 3 absent (`features.stage3_unavailable` records why), every
  `stage3`-reading rule short-circuits, and `detect_overlaps` sees no overlapping voxels — so
  no finding of any kind. Candidate item: a rule consuming `stage3_unavailable`, which also
  gives that key its `FEATURE_DOCS` catalogue entry.
- **`features/sagittal_projection.py` (item 021) is reachable from nothing** *(insights.md,
  item 130, 2026-08-31)*. Not `pipeline.py`, `feature_report.py`, `cli.py`, any rule or
  `scripts/` — only its own test. The dead-wiring shape Stage 26 D8 raised for
  `neighbourhood.py`, except that it renders a PNG rather than record leaves, so "wire it
  in" may mean a CLI flag. Decide: wire or retire — no roadmap deliverable owns it.
- **The synthetic fixture corpus is anatomically inverted along S** *(insights.md, item
  131, 2026-08-31)*. `synth/clean_gt.py::build_clean_spine` stacks ascending labels along
  ascending axis 2, so `clean_control_seg.nii.gz` puts L1 at S = 27 mm and L5 at S = 187 mm;
  every in-repo driver therefore advances superiorly while real VerSe input advances
  caudally — the inversion that hid item 131's traversal-direction defect for nine items,
  and which silently flips the sign of any future feature measured against +S. Correcting
  the stacking moves committed values across the suite and both reference artifacts, so it
  needs its own item — and Stage 20's specificity baseline should be pinned after it, not
  before.
- **Maintainer pass over `feature_docs.STATUS_OVERRIDES`' `monotonic_consistency` notes**
  *(insights.md, item 132, 2026-08-31)*. The `is_monotonic` note says it "should be wired
  into the sequence rule directly"; `MislabelRule`'s Detector B has consumed
  `non_monotonic_pairs` since item 033 and fires end-to-end since item 132, so the note
  reads as an open action that is closed. It is maintainer-signed text no item may rewrite
  from inside — either a maintainer pass, or the Stage 29 D11 treatment (separate what is
  measured from what is signed).
- **Nine pre-existing test files capture subprocess output with `text=True` and no
  `encoding=`** *(insights.md, queue-018, 2026-09-01)*. `tests/conftest.py` (2),
  `test_066`, `test_069`, `test_070`, `test_074`, `test_111`, `test_113`, `test_117`,
  `test_123` (2). All capture ASCII today, which is why none has fired; the identical
  pattern broke `test_134` on `windows-latest` (PR #58) the first time a capture carried an
  em dash. `tests/run_process.py::run_utf8` is the drop-in replacement. Candidate item:
  convert all nine in one mechanical sweep, closing the class in the suite.
- **Shorten CI wall-clock — the `windows-latest` leg is the critical path at 21 min**
  *(2026-09-01 feedback loop)*. Measured on the last green run of queue-018 (PR #58,
  run 33483503854): `test (windows-latest)` 21.0 min, `test (ubuntu-latest)` 13.7 min,
  `test (numpy 1.26.4)` 13.2 min, `test (numpy 2.0.2)` 10.0 min, gated 1.5 min, scope
  check 4 s — five near-full suite runs per PR, the slowest gating the whole run. Two
  measured facts point at the fix: (i) the suite is **parallel-safe** — `pytest -n 4`
  (pytest-xdist, four workers, the vCPU count of a GitHub-hosted runner) passed 6690/6690
  locally in **4 m 51 s against 15 m 00 s serial** on 2026-09-01, so adding `pytest-xdist`
  to `[project.optional-dependencies] dev` and `-n 4` to every `python -m pytest` step in
  `.github/workflows/ci.yml` should bring ubuntu to ~5 min and windows to ~8 min with no
  coverage change; (ii) four tests dominate the serial tail and set the parallel floor —
  `test_128_relocation_checks.py::test_ac13_test115_fence_cap_still_passes_and_points_at_new_module`
  (103 s), `test_057_evaluate_cli.py::test_ac5_calibrate_writes_config_and_calibration_block`
  (76 s), and `test_115_stage26_validation.py`'s two `test_ac8_*` AST sweeps (~50 s each) —
  ~4.7 min of serial time, and the 103 s test alone caps what `-n 4` can reach. Also worth
  taking: `actions/setup-python`'s `cache: pip` (five installs per run). aide-loop's own
  Windows work (issue #74, branch `ci/74-windows-defender-and-shards`) measured that the
  runner image already ships Defender real-time scanning off, so the Windows cost is
  per-subprocess spawn overhead (~55–70 ms each), not scanning — sharding the Windows leg
  into parallel jobs is the fallback if xdist proves flaky there, not a first move.
  Candidate item: xdist + pip cache in one workflow PR, then profile the four outliers.
