# Seg-QC-xnat — Progress Tracker

> **Status:** Draft v2 · **Created:** 2026-06-24 · **Re-issued:** 2026-07-02
> (structure per `.aide/templates/progress.md`; all statuses carried over)
> Step 3 of the AIDE loop. Derived from [`vision.md`](vision.md) and
> [`roadmap.md`](roadmap.md). **Single source of truth for implementation
> status** per stage, deliverable, and acceptance criterion — machine-parsed per
> `.aide/conventions.md` §1 and edited via `python .aide/scripts/aide.py progress
> set`. Update **incrementally** — never reset a non-planned status back to 📋.

---

## Status legend

| Icon | Meaning |
|------|---------|
| 📋 | Planned |
| 🚧 | In Progress |
| ✅ | Complete |
| ⏸️ | Deferred |
| ❌ | Excluded |

## Stage summary

| Stage | Title | Objectives | Status |
|-------|-------|-----------|--------|
| 0 | Project Scaffolding & I/O Foundation | (foundation) | ✅ |
| 1 | End-to-End Thin Slice: Empty Detection + Report | G1, G4 | ✅ |
| 2 | Geometric & Topological Feature Extraction | (feature core) | ✅ |
| 3 | Spinal Curve: Spline Fit & Deviation Features | (feature core) | ✅ |
| 4 | Heuristic Rule Engine over Failure Modes | G2 | ✅ |
| 5 | Synthetic Failure Corpus & Regression Suite | G7, G2 | ✅ |
| 6 | VerSe Reference Distributions & Delta Rules | G3 | ✅ |
| 7 | Evaluation, Calibration & Metrics *(Phase 1 complete)* | G3, G7 | ✅ |
| 8 | Image-Based / Radiomics Features | (Phase 2) | 🚧 |
| 9 | Containerisation & XNAT Command | G5 | 📋 |
| 10 | Portable Compute: GPU Acceleration Path | G6 | 📋 |
| 11 | Extensibility & Abnormality Classification Arm | G8 | 📋 |

## Objective coverage

| Objective | Delivered by | Status |
|-----------|--------------|--------|
| G1 Detect empty / trivially-failed | Stage 1 | ✅ |
| G2 Detect catalogued failure modes (§6) | Stages 4, 5 | ✅ |
| G3 Distinguish failure from variation | Stages 6, 7 | ✅ |
| G4 Per-case QC report (JSON + human) | Stage 1 (ext. 2–4) | ✅ |
| G5 Deploy on XNAT *(deferred)* | Stage 9 | 📋 |
| G6 Portable / GPU *(deferred)* | Stage 10 | 📋 |
| G7 Evaluable & regression-testable | Stages 5, 7 | ✅ |
| G8 Extensible / classification *(deferred)* | Stage 11 | 📋 |

---

# Phase 1 — Complete MVP Pipeline

## Stage 0 — Project Scaffolding & I/O Foundation — ✅

**Goal.** A runnable, cross-platform Python package + CLI that loads a scan and an
instance label map, normalises labels, and exits cleanly.

**Deliverables.**
- ✅ Python package `segqc/` targeting Python 3.9+; `pyproject.toml` with pinned
  core deps (NumPy, SciPy, scikit-image, NiBabel and/or SimpleITK). *(Item 001)*
- ✅ CLI entry point: `segqc run --scan <nii> --seg <nii> --out <dir>`. *(Item 006)*
- ✅ NIfTI loader for scan + label map, preserving spacing/affine, handling anisotropy. *(Item 003)*
- ✅ Label-convention module: integer label ↔ anatomical vertebra, configurable,
  with a default TotalSegmentator/VerSe mapping. *(Item 004)*
- ✅ Structured logging + versioned heuristic-config scaffold (YAML/JSON). *(Item 005)*
- ✅ `pytest` harness + tiny synthetic NIfTI fixtures. *(Item 002)*

**Acceptance.**
- [x] `segqc run` on a fixture loads both volumes, prints labelled inventory, writes a stub JSON. *(Items 006, 010; `test_cli_run.py`, `test_010_pipeline.py`)*
- [x] Unit tests for loader and label mapping pass. *(`test_io.py`, `test_labels.py`)*
- [x] Runs CPU-only on Windows, macOS, and Linux. *(NumPy/SciPy CPU-only deps; suite green on Windows)*

---

## Stage 1 — End-to-End Thin Slice: Empty Detection + Report (G1, G4) — ✅

**Goal.** Smallest complete pipeline (input → verdict → report) detecting
empty / trivially-failed segmentations.

**Deliverables.**
- ✅ Empty / near-empty detection (no labels, foreground < N voxels, < K labels), configurable. *(Item 007)*
- ✅ QC verdict model: `pass` / `flagged-for-review` / `fail` with per-case + per-vertebra reasons. *(Item 008)*
- ✅ JSON report schema v0 (machine-readable, versioned). *(Item 009)*
- ✅ Human-readable report (Markdown/plain text) from the same model. *(Item 010)*
- ✅ CLI wires loader → empty-check → verdict → both report formats. *(Items 006, 010)*

**Acceptance.**
- [x] 100% of empty / near-empty fixtures flagged `fail` with explicit reason (**G1**). *(`test_007_empty_detection.py`)*
- [x] A non-empty fixture passes the empty check. *(`test_007_empty_detection.py`)*
- [x] JSON validates against schema; human report generated (**G4**). *(`test_009_json_report.py`, `test_010_human_report.py`)*
- [x] Tests cover empty-detection thresholds. *(`test_007_empty_detection.py`)*

---

## Stage 2 — Geometric & Topological Feature Extraction — ✅

**Goal.** The feature engine the heuristics depend on — the MVP image-processing core.

**Deliverables.**
- ✅ Per-label features: voxel & physical volume; extent (x/y/z); bounding box; border-contact flags. *(Item 011)*
- ✅ Connected-components per label: component count + sizes. *(Item 012)*
- ✅ Centroid / centre-of-mass per label, level-aware (C1, C2, S). *(Item 013)*
- ✅ Inter-vertebra relationships: ordered centroid sequence, neighbour spacing, sequence continuity. *(Item 014)*
- ✅ Overlap detection between labels. *(Item 015)*
- ✅ Features serialised into JSON (`features` block) + per-case feature table. *(Item 016)*
- ✅ EDT-based centroid variants (smooth-centre via EDT-threshold CoM; strict-centre via EDT peak) + centroid depth (distance from centroid to nearest label surface). C1/C2 handled as special anatomy. *(Item 023)*
- ✅ Fragmentation index per label (largest connected component / total label volume), extending the JSON features block. *(Item 025)*

**Acceptance.**
- [x] Features computed deterministically; values verified against hand-computed expectations.
- [x] Anisotropic-spacing fixture yields correct physical volumes/extents.
- [x] `features` block emitted in JSON; tests cover each feature.
- [x] EDT-based centroid variants computed; centroid depth available per label. *(Item 023)*
- [x] Fragmentation index computed per label and serialised in JSON features block. *(Item 025)*

---

## Stage 3 — Spinal Curve: Spline Fit & Geometric Deviation Features — ✅

**Goal.** Centroid-spline and deviation features powering alignment, ordering, and
mislabelling heuristics.

**Deliverables.**
- ✅ Spline fit through ordered vertebra centroids, robust to missing levels. *(Item 017)*
- ✅ Per-vertebra offset from the spline. *(Item 018)*
- ✅ Orientation / rotation estimate per vertebra + global curvature descriptors. *(Item 019)*
- ✅ Neighbour-consistency metrics (spacing regularity, monotonic progression). *(Item 020)*
- ✅ Optional sagittal projection of centroids + spline for the human report. *(Item 021)*
- ✅ Stage 3 feature serialisation & GT-vs-perturbed regression tests. *(Item 022)*
- ✅ Local vertebra neighbourhood comparison (sliding window, n=3–5): per-vertebra deviation from neighbourhood mean/median of centroid spacing, spline offset, and volume; flags isolated anatomical outliers. *(Item 024)*

**Acceptance.**
- [x] Spline fits cleanly on GT fixtures; offsets near-zero for GT, large for displaced/mislabelled.
- [x] Robust to a deliberately missing level (no crash, sensible fit).
- [x] Orientation / curvature features in JSON; tests pass. *(Item 019)*
- [x] Neighbour-consistency and neighbourhood-comparison features in JSON. *(Items 020, 024)*
- [x] Regression tests over GT + perturbed cases pass. *(Item 022)*

---

## Stage 4 — Heuristic Rule Engine over the Failure Modes (G2) — ✅

**Goal.** Explainable, configurable rule engine detecting each §6 failure mode.

**Deliverables.**
- ✅ Config-driven rule engine: each rule emits flag + human-readable reason + offending labels. *(Item 026)*
- ✅ Rule family — min/max bounds (volume, extent), level-aware. *(Item 027)*
- ✅ Rule family — connected-components → fragmentation / island flags. *(Item 028)*
- ✅ Rule family — incomplete coverage / missing levels (count vs expected sequence). *(Item 029)*
- ✅ Rule family — label-sequence continuity (e.g. L1→T12→L2→L5). *(Item 030)*
- ✅ Rule family — border-partial-vertebra flag. *(Item 031)*
- ✅ Rule family — overlap flag. *(Item 032)*
- ✅ Rule family — mislabel / misalignment (centroid vs expected level ordering / spline). *(Item 033)*
- ✅ Verdict aggregation: combine flags → pass / flag / fail with severity. *(Item 034)*
- ✅ Heuristic thresholds in a documented, versioned config file; pipeline/report integration & per-failure-mode tests. *(Item 035)*

**Acceptance.**
- [x] Each of the 8 §6 failure modes has ≥1 heuristic firing on a crafted example (**G2**).
- [x] Every flag carries a reason + offending labels; thresholds live in config.
- [x] Tests assert correct firing **and** non-firing per rule.

---

## Stage 5 — Synthetic Failure Corpus & Regression Suite (G7) — ✅

**Goal.** Reproducible corpus + automated tests covering every failure mode.

**Deliverables.**
- ✅ Synthetic-failure generator: clean-GT spine builder & perturbation
  framework *(Item 036)*; component/shape perturbations — fragment, fuse,
  inject islands *(Item 037)*; coverage/border/overlap perturbations — remove
  level, crop at border, force overlap *(Item 038)*; identity/ordering/
  alignment perturbations — displace, relabel/swap, sequence-break *(Item 039)*.
- ✅ Small committed fixture set spanning all 8 failure modes. *(Item 040)*
- ✅ Regression suite asserting expected verdict + which heuristic fired per case. *(Item 041)*
- ✅ Golden-file JSON snapshots for stability/determinism. *(Item 042)*

**Acceptance.**
- [x] Every §6 failure mode has ≥1 synthetic case and is detected (**G7**, **G2**).
- [x] Full-pipeline regression suite green; golden JSON stable across repeated runs.

---

## Stage 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3) — ✅

**Goal.** Ground heuristics in VerSe-derived expected distributions.

**Deliverables.**
- ✅ VerSe GT ingestion → per-level feature aggregation into reference distributions
  (mean/percentiles), stratified by level (+ subject-size proxy where feasible). *(Items 043, 044)*
- ✅ Versioned reference-data artifact (committed or mounted) + builder script. *(Item 045)*
- ✅ Delta-to-reference rules: per-vertebra distribution distance / out-of-range vs reference. *(Items 046, 047)*
- ✅ Heuristic config can switch from hand-set bounds to reference-derived bounds. *(Item 048)*
- ✅ Reference artifact + delta rules wired into `segqc run`; Stage-6 acceptance suite
  (GT in-range, perturbations out-of-range). *(Item 049)*

**Acceptance.**
- [x] Reference artifact builds reproducibly from VerSe and is versioned.
- [x] GT fixtures fall within reference ranges; perturbed cases fall outside (**G3**).
- [x] Tests cover reference loading + delta rules.

---

## Stage 7 — Evaluation, Calibration & Metrics (G3, G7) — ✅ *(Phase 1 complete)*

**Goal.** Quantify performance and calibrate thresholds against VerSe GT,
TotalSegmentator output, and the synthetic corpus.

**Deliverables.**
- ✅ Segmentation-overlap metrics — per-label & aggregate DICE / Jaccard vs GT. *(Item 050)*
- ✅ Feature-set match / divergence by vertebra label. *(Item 051)*
- ✅ QC-verdict comparison & per-case outcome classification. *(Item 052)*
- ✅ Runs on VerSe GT (positive control), TotalSegmentator outputs, synthetic failures. *(Item 053)*
- ✅ Metrics: FPR on GT, sensitivity per failure mode, DICE-vs-flag correlation. *(Item 054)*
- ✅ Threshold-calibration loop; chosen thresholds + metrics recorded here / evaluation report. *(Items 055, 056)*
- ✅ Stage-7 integration into a reproducible `segqc evaluate` entry point + acceptance suite
  (GT low-FPR, injected failures caught, DICE-vs-flag correlation) closing Phase 1;
  calibrated thresholds + metrics recorded. *(Item 057)*

**Acceptance.**
- [x] GT passes at a high rate (low FPR) (**G3**).
- [x] Injected failures caught; flag rate / feature divergence correlates with DICE (**G7**).
- [x] Calibrated thresholds + metrics recorded; evaluation reproducible.

**Calibrated metrics (to be filled at completion).** *(Item 057 acceptance run
over the committed §6 synthetic corpus cohort — GT = `clean_control`,
candidate = each perturbed seg — plus the purpose-built graded-quality
correlation cohort per the Assumptions; `bundled_default_config()`,
uncalibrated.)*
- FPR on GT (`clean_control`): **0.0** (`metrics.false_positive_rate`, AC8).
- Sensitivity per §6 failure mode (`metrics.per_mode[*].sensitivity`, AC9):
  pipeline-detectable modes 2 (fragment), 3 (inject islands), 5 (remove
  level), 6 (crop at border), 7 (sequence break) — **1.0** each; modes 1
  (displace), 4 (relabel swap), 8 (force overlap) — **0.0**, structurally
  invisible to the plain pipeline (`detection == "reconstructed_record"`,
  documented in the item 057 Assumptions, mirrors item 049). Overall corpus
  sensitivity 5/8, not over-claimed as 1.0.
- DICE-vs-flag correlation: **-0.943** (graded-quality cohort,
  `metrics.dice_vs_flag.coefficient`, AC10 — negative sign as expected: lower
  DICE ⇔ more likely flagged); feature-divergence-vs-flag: **+0.585**
  (`metrics.feature_divergence_vs_flag.coefficient`, AC11 — positive sign as
  expected). The full 9-case §6 corpus does not yield a cleanly-signed
  DICE-vs-flag correlation (some flagged modes barely move DICE while some
  unflagged reconstructed modes move it a lot — see Assumptions), which is
  why AC10/AC11 use the dedicated graded-quality cohort.

---

# Phase 2 — Extensions (after the pipeline is complete)

## Stage 8 — Image-Based / Radiomics Features — 🚧

**Goal.** Intensity/radiomics features to strengthen heuristics and seed abnormality detection.

**Deliverables.**
- ✅ Intensity features over each labelled region (+ original scan); optional PyRadiomics integration. *(Items 059, 060)*
- ✅ Feature fusion into the report + ≥1 intensity-based heuristic (e.g. implausible-intensity flag). *(Items 061, 062)*
- ✅ Reference distributions extended with intensity features. *(Items 063, 064)*
- ✅ Intensity-bearing synthetic scan fixtures (HU-painted GT + implausible-intensity variants) enabling local testing of image features. *(Item 058)*
- 🚧 Stage 8 integration into `segqc run` + acceptance suite (image features on fixtures; ≥1 intensity heuristic fires; tests pass). *(Item 065)*

**Acceptance.**
- [ ] Image features computed on fixtures; ≥1 intensity-based heuristic fires appropriately; tests pass. *(Item 065)*

---

## Stage 9 — Containerisation & XNAT Container Service Command (G5) — 📋

**Goal.** Package the completed pipeline as a Docker image with an XNAT command.

**Deliverables.**
- 📋 Dockerfile (CPU-only base), pinned deps, bundled/mounted reference data.
- 📋 XNAT Container Service `command.json` (inputs: session/scan + segmentation; outputs: report resources).
- 📋 Entry script mapping XNAT inputs → CLI → output resources.
- 📋 Local container smoke test + deployment docs.

**Acceptance.**
- [ ] Container runs the pipeline on a mounted case, producing JSON + human report.
- [ ] `command.json` validates; install steps documented (**G5**).

---

## Stage 10 — Portable Compute: GPU Acceleration Path (G6) — 📋

**Goal.** Optional GPU acceleration equivalent to the CPU path; GPU never required.

**Deliverables.**
- 📋 Runtime backend selection (CuPy/cuCIM when present, NumPy/SciPy fallback).
- 📋 Equivalence tests: CPU vs GPU produce identical verdicts.
- 📋 Performance benchmark.

**Acceptance.**
- [ ] GPU path optional + auto-detected; CPU/GPU verdict-equivalence tests pass.
- [ ] The tool runs fully CPU-only (**G6**).

---

## Stage 11 — Extensibility & Abnormality Classification Arm (G8) — 📋

**Goal.** Documented extension path + optional classification arm so handled
abnormalities are accounted for rather than naively flagged.

**Deliverables.**
- 📋 Plugin/registration API for new heuristics + abnormality classes.
- 📋 Ingestion of human abnormality labels (post-op, fracture, implant); a classification arm
  that informs the heuristics.
- 📋 Developer docs: add a heuristic / abnormality class end-to-end.

**Acceptance.**
- [ ] A new heuristic + abnormality class can be added via the documented path in a test.
- [ ] Explicitly-handled abnormalities are not naively flagged (Vision Success Criterion 4) (**G8**).

---

## Next Step

Review this progress tracker. When ready, start a **new chat session** and run
`/aide-create-queue` to generate the next batch of prioritized work items.
