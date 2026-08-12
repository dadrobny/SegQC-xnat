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
  that recreates the same problem one rung up.

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
dispositions if Stage 21 has not already.

**Validation / acceptance.** The taxonomy is documented with its rationale and every
deviation from the starting proposal justified, and is signed off by the maintainer before
migration (**G8**); every feature is addressable under it and no identity field is stored
more than once; the regenerated catalogue and the drift test agree; no rule's behaviour
changes on the corpus except where a retune is explicitly authorised.

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
- **Scaling the per-mode metrics that are not bounded 0..1** *(2026-08-12)*. The eight metrics
  do not share units, and they do not share a remedy either — the choice is per metric, and
  the deciding question is **scope**, not whether the metric happens to be a count:
  - **A faithful ratio exists where numerator and denominator share scope.**
    `missing_level_count` is scan-level on both sides — GT levels absent, over GT levels
    expected — so `missing / expected` is a genuine fraction of the scan's own anatomy.
  - **A ratio is wrong where scope differs.** `rogue_island_count` is a *maximum over
    per-label entries*; dividing it by a scan-level count converts a per-level worst case
    into a scan-level density, which is a different quantity (possibly a useful feature in
    its own right — but not a scaling of the original).
  - **A declared threshold fits where the clean expectation is a known constant.** For rogue
    islands the expectation is *none*, so a small declared count is defensible as the scale
    without inventing a "full-blown failure" magnitude. The value is **TBC** and deliberately
    unset by item 109, which ships only the mechanism.
  - **Neighbourhood-relative comparison is the fallback**, reached for when neither a
    same-scope denominator nor a defensible global constant exists: compare a vertebra's value
    against its own neighbours rather than against anything global. Item 110's generalised
    neighbourhood API (arbitrary named features, selectable scored subset) is the mechanism;
    coupling `eval/` to a `features/` refactor was deliberately kept out of Stage 26. A
    natural fit for **Stage 27**, which is already generalising `reference_delta` off its
    single hardcoded tracked feature.
