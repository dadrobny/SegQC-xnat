# Seg-QC-xnat — Development Roadmap

> **Status:** Draft v2 · **Created:** 2026-06-24 · **Re-issued:** 2026-07-02
> (structure per `.aide/templates/roadmap.md`; content carried over unchanged)
> Step 2 of the AIDE loop. Derived from [`vision.md`](vision.md). Breaks the
> vision into incremental, demonstrable, locally-deployable stages (~1 week each).

---

## Strategy

Per the agreed steering:

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

| Objective | Delivered by |
|-----------|--------------|
| G1 Detect empty / trivially-failed | Stage 1 |
| G2 Detect catalogued failure modes (§6) | Stages 4, 5 |
| G3 Distinguish failure from variation | Stages 6, 7 (real-VerSe grounding: Stage 12) |
| G4 Per-case QC report (JSON + human) | Stage 1 (extended by 2–4) |
| G7 Evaluable & regression-testable | Stages 5, 7 (real-VerSe evaluation: Stage 12) |
| *(deferred)* G5 Deploy on XNAT | Stage 9 |
| *(deferred)* G6 Portable / GPU | Stage 10 |
| *(deferred)* G8 Extensible / classification | Stage 11 |

### Stage dependency graph

```
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 7        (Phase 1: complete MVP pipeline)
              └────────► 6 ─┘
                                
Phase 2 (after 7):  8 (img features) · 9 (XNAT) · 10 (GPU) · 11 (extensibility)
                    12 (real-VerSe grounding & reference feature expansion)
                    13 (dataset ingestion adapters & harmonization schema)
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
  **versioned** reference artifact (`reference_verse_vN.json`, `provenance.source
  == "verse-vN"`); commit the *derived distributions artifact*, never the raw
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
- **Resolver** (`segqc.datasets`): `resolve(descriptor, *, data_root, subset, role)
  -> Cohort`, deterministic ordering; the existing flat `ingest_cohort` /
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

## Next Step

Review this roadmap. When you're happy with it, start a **new chat session** and
run `/aide-create-progress` to create the progress-tracking file.
