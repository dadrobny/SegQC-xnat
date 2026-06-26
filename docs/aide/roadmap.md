# Seg-QC-xnat — Development Roadmap

> **Status:** Draft v1 · **Created:** 2026-06-24
> Step 2 of the AIDE workflow. Derived from [`vision.md`](vision.md). Breaks the
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
| G3 Distinguish failure from variation | Stages 6, 7 |
| G4 Per-case QC report (JSON + human) | Stage 1 (extended by 2–4) |
| G7 Evaluable & regression-testable | Stages 5, 7 |
| *(deferred)* G5 Deploy on XNAT | Stage 9 |
| *(deferred)* G6 Portable / GPU | Stage 10 |
| *(deferred)* G8 Extensible / classification | Stage 11 |

### Stage dependency graph

```
0 ─► 1 ─► 2 ─► 3 ─► 4 ─► 5 ─► 7        (Phase 1: complete MVP pipeline)
              └────────► 6 ─┘
                                
Phase 2 (after 7):  8 (img features) · 9 (XNAT) · 10 (GPU) · 11 (extensibility)
```

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

## Next Step

Review this roadmap. When you're happy with it, start a **new chat session** and
run `/speckit-aide-create-progress` to create the progress-tracking file.
