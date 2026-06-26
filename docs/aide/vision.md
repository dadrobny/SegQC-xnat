# Seg-QC-xnat — Project Vision

> **Status:** Draft v1 · **Created:** 2026-06-24
> Step 1 of the AIDE workflow. This document is the single source of truth from
> which the roadmap, progress tracker, and all work items are derived.

---

## 1. Project Overview

**Seg-QC-xnat** is an automated quality-control (QC) tool for **vertebra instance
segmentations** of spine CT (and potentially MR) imaging. It runs (or consumes the
output of) a deep-learning spine segmentation, extracts a wide range of
geometric, topological, and image-based features, applies a heuristic rule set to
judge **anatomical plausibility**, and produces a human-readable report that
flags suspect segmentations for review.

The tool is designed to be **segmentation-tool agnostic** — it works on the label
maps produced by any DL segmentation pipeline — with **TotalSegmentator** used as
the reference/primary tool for this project. It is packaged as a **Docker
container** for deployment as an **XNAT Container Service** command on an existing
XNAT server.

### Why this matters

Automatic spine segmentation tools fail in characteristic, often silent ways
(mislabelled vertebrae, fragmented or fused labels, rogue islands, missing
levels). Downstream research and clinical pipelines either trust these outputs
blindly or require slow manual review of every case. Seg-QC-xnat provides an
automated, explainable **QC gate** that catches the common failure modes,
distinguishes them from genuine anatomical/pathological variation, and surfaces
only the cases that truly need human eyes — making large-scale segmentation
usable at population scale.

### Guiding principles

- **Explainable over opaque.** Heuristics and feature thresholds must be
  inspectable and justifiable; a flag should always come with a reason. This is
  preferred over a black-box classifier (at least initially).
- **Tool-agnostic input.** Operate on standard label-map formats (NIfTI) and a
  documented label convention, not on any one segmenter's internals.
- **Variation-aware.** Distinguish *failure* from legitimate variation (vertebra
  level, subject size, spine curvature, pathology, post-operative state).
- **Reference-grounded.** Build expected feature distributions from trusted
  ground truth (VerSe) rather than hand-guessed constants where possible.
- **Portable compute.** Run on CPU-only hosts, optionally accelerate with GPU
  libraries; never *require* a GPU.
- **Extensible.** Be a foundation that human-labelled abnormalities can extend,
  not a fixed rule set.

---

## 2. Goals & Objectives

| # | Objective | Measurable outcome |
|---|-----------|--------------------|
| G1 | Detect empty / trivially-failed segmentations | 100% of empty or near-empty label maps flagged |
| G2 | Detect the catalogued failure modes (§6) | Each failure mode has ≥1 heuristic with documented detection on the test corpus |
| G3 | Distinguish failure from legitimate variation | Ground-truth (VerSe) segmentations pass QC at a high rate (target: low false-positive rate, to be quantified) |
| G4 | Produce a clear per-case QC report | Machine-readable (JSON) + human-readable report emitted per scan |
| G5 | Deploy on XNAT | Runs as an XNAT Container Service command on real session data |
| G6 | Portable execution | Identical results CPU-only; optional GPU acceleration path |
| G7 | Be evaluable & regression-testable | Automated test suite over VerSe GT + synthetic failures + curated cases |
| G8 | Be extensible | Documented path to add new abnormality classes and heuristics |

These objectives are **directional**; concrete numeric thresholds (sensitivity,
specificity, FPR) are to be calibrated during the evaluation stage against the
VerSe reference set and recorded in the roadmap/progress documents.

---

## 3. Target Users

- **Imaging researchers / dataset curators** building curated spine datasets
  (Use Case C) who need to keep only successful segmentations meeting FOV /
  level / count / pathology criteria.
- **Pipeline engineers** running multi-stage processing who need a QC gate to
  block likely-failed segmentations from downstream tools (Use Case D).
- **Clinical/research reviewers** who triage flagged cases, accept/reject them,
  and feed corrections back to refine the heuristics (Use Case A).
- **Annotators / method developers** who label new abnormality classes (post-op,
  pathology) to extend the QC pipeline's coverage (Use Case B).
- **XNAT administrators** who install and run the container on a shared server.

---

## 4. Use Cases

The tool is designed to serve four distinct (and increasingly ambitious) use
cases. Early stages target A/C/D; B is the extensibility horizon.

### Use Case A — Refinement of decision making
Use the current heuristics to flag cases; a human accepts or rejects each flag;
the feedback tunes thresholds/rules. **Does not** cover abnormalities not yet
modelled.

### Use Case B — Build classification annotations to extend the QC pipeline
Automatically process segmentations, manually assess flagged cases, and **label
new abnormalities** (e.g. post-operative changes) not yet in the heuristics. Use
those labels to (a) extend heuristics to account for that population and (b) add
a classification arm that informs the heuristics.

### Use Case C — Build a curated research dataset
Determine which segmentations are successful and meet additional requirements
(FOV coverage, spinal segment, number of vertebrae, presence/absence of
abnormality) to assemble a clean dataset.

### Use Case D — QC gate in a downstream pipeline
Determine likely failures and **block** failed segmentations from being passed to
the next tool in an automated data flow.

---

## 5. Core Features

### 5.1 Segmentation input & label handling
- Consume vertebra **instance** segmentations (one label per vertebra) as NIfTI
  label maps + the original scan.
- Tool-agnostic: a documented label convention mapping integer labels →
  anatomical vertebra (C1…C7, T1…T12(+T13), L1…L5(+L6), S, etc.).
- Optionally **run** the segmentation (TotalSegmentator as reference) or accept a
  precomputed label map.
- Handle real-world quirks: anisotropic spacing, varying FOV, partial vertebrae
  at image borders, transitional anatomy.

### 5.2 Feature extraction
**Segmentation-based (geometric / topological):**
- Volume per label; extent (x, y, z); bounding box.
- Connected-components analysis per label (count, sizes → fragmentation/islands).
- **Fragmentation index**: ratio of largest connected component to total label
  volume — distinguishes a single dominant body with noise fragments from a
  truly split label.
- **Vertebra centroid** with three computation tiers (level-aware; C1 and C2
  handled specially due to atypical anatomy — no vertebral body in the same
  sense as thoracic/lumbar):
  - *Simple CoM* — mean voxel position; fast but can lie in the spinal canal.
  - *Smooth centre* — centre of mass restricted to the EDT-thresholded mask
    (e.g. ≥50 % or ≥75 % of max distance), giving a more anatomically central
    point for intact vertebrae; may drift for fragmented labels.
  - *Strict centre* — peak of the (smoothed) Euclidean Distance Transform;
    guaranteed inside the label and most robust to fragmentation / abnormal
    shape, but noisier than CoM on normal vertebrae.
- **Centroid depth**: distance from the chosen centroid to the nearest label
  surface, extracted from the same EDT; centroids near the surface or outside
  the label are unexpected and flagged.
- **Spline fit** through the centroid sequence (spinal curve).
- Per-vertebra **offset from the spline**.
- Orientation / rotation estimate of centroids/vertebrae.
- Inter-vertebra relationships (spacing, ordering, neighbour consistency).
- **Local neighbourhood comparison**: per-vertebra feature deviations from a
  sliding window of n anatomical neighbours (centroid spacing, spline offset,
  volume, other per-label features); isolates vertebrae that are outliers
  within an otherwise-consistent local spine context.

**Image-based:**
- Radiomics and intensity features over the labelled regions (and optionally the
  original scan) to inform heuristics and abnormality detection.

### 5.3 Reference feature set
- Build **reference distributions** of features from ground-truth (VerSe)
  segmentations, stratified by the variation factors in §5.4.

### 5.4 Decision making / heuristics
Apply an explainable rule set that accounts for **expected variation**:
- spine segment / vertebra level
- subject size
- spine shape (normal lordosis / kyphosis)
- pathology (fracture / compression)
- post-operative state (implants, resections)

Rule families:
- **min/max bounds** (volume, extent, etc.), level-aware.
- **consistency with neighbouring vertebrae.**
- **delta to reference** (e.g. spline offset, distribution distance).

Optional **classification arm**: when abnormality labels are provided, classify
specific abnormalities (resection, fracture, implant, …) and adjust heuristics
accordingly.

### 5.5 Reporting
- Per-case **QC verdict** (pass / fail / flagged-for-review) with per-vertebra
  detail and **explicit reasons** for each flag.
- Machine-readable output (JSON) for pipeline gating (Use Case D) and dataset
  curation (Use Case C).
- Human-readable report (and ideally visual overlays) for reviewers (Use Case A/B).

### 5.6 XNAT integration
- Docker image with an XNAT Container Service **command definition** (inputs:
  session/scan + segmentation; outputs: report resources).
- Conforms to XNAT container-build guidance
  (https://wiki.xnat.org/container-service/building-docker-images-for-container-service).

---

## 6. Segmentation Failure Modes (to be detected)

The heuristics must catch these characteristic failures of automatic spine
segmentation:

1. Label not aligned with the anatomical vertebra it names.
2. Over-/under-segmentation — fused or fragmented vertebra segments.
3. Disconnected components / islands, especially tiny rogue segments.
4. Semantic mislabelling (wrong vertebra identification).
5. Not all vertebrae in the image are segmented.
6. Partial vertebra at the image border whose appearance changes.
7. Non-continuous label sequence (e.g. L1 → T12 → L2 → L5).
8. Overlapping segments.

Each failure mode is a **test target**: the evaluation corpus (§8) must include
examples (real or synthetic) and at least one heuristic must detect each.

---

## 7. Technical Architecture

### 7.1 Language & runtime
- **Python 3.9+** (broad compatibility; 3.9 is the floor).
- Modular, library-first design with a CLI entry point so it is testable
  independently of XNAT.

### 7.2 Image-processing stack (CPU/GPU dual path)
- Core: NumPy, SciPy, scikit-image, NiBabel / SimpleITK for I/O and geometry;
  a radiomics library (e.g. PyRadiomics) for image features.
- **Optional GPU acceleration** via CuPy, cuCIM, etc. — selected at runtime when
  available, with a CPU fallback that produces equivalent results. GPU must
  never be a hard requirement.
- Segmentation backend (reference): **TotalSegmentator** (optional/pluggable).

### 7.3 Packaging & deployment
- **Docker** image, built per the XNAT Container Service guidance, exposing an
  XNAT command. Designed to run unattended on the XNAT server.
- Reference data (VerSe-derived distributions) bundled or mounted as needed.

### 7.4 Data formats
- Input: NIfTI scans + NIfTI instance label maps; documented label convention.
- Output: JSON QC report (primary, machine-readable) + human-readable
  report/visuals.

### 7.5 Architectural shape (initial)
```
scan + segmentation
        │
        ▼
 [ I/O & label normalisation ]
        │
        ▼
 [ feature extraction ]  ──(CPU | GPU)
        │
        ▼
 [ reference comparison + heuristics ]  ◀── reference feature set (VerSe)
        │                                ◀── (optional) abnormality classifier
        ▼
 [ QC verdict + report ]  ──► JSON  +  human report
```

---

## 8. Evaluation & Testing Strategy

Automated testing runs QC on both a **target segmentation tool's output** and
**ground truth**, comparing at three levels:
1. **QC pass/fail** verdict.
2. **Segmentation output** (e.g. DICE vs. reference).
3. **Feature sets**, matched by vertebra label.

Test corpora and expectations:

- **VerSe ground truth** — used to build the reference feature set and as the
  positive control: GT segmentations/features should **pass** QC.
- **DICE as a divergence proxy** — lower DICE / bigger disagreement against GT
  indicates a wrong segmentation and **should be flagged**; feature-set
  similarity should correlate (somewhat) with DICE.
- **Manually modified ground truth** — deliberately introduce known failures
  (changed labels, modified/removed/added segmentation, islands, fusions) to
  cover **every failure mode in §6**.
- **Curated challenging cases** — real cases with known pathology, post-op
  changes, atypical anatomy, border effects.

Success at this stage: GT passes, injected failures are caught, and QC verdicts
track segmentation quality. Concrete metrics (sensitivity/specificity per failure
mode, FPR on GT) are calibrated and recorded here.

---

## 9. Non-Functional Requirements

- **Portability:** runs CPU-only on a standard XNAT host; optional GPU path.
- **Determinism:** CPU and GPU paths produce equivalent QC verdicts.
- **Explainability:** every flag carries a human-readable reason; thresholds are
  documented and inspectable.
- **Robustness:** tolerant of varying FOV, spacing, anisotropy, partial/border
  vertebrae, and missing levels without crashing.
- **Performance:** per-case runtime acceptable for batch/population processing on
  the XNAT server (target to be set during evaluation).
- **Reproducibility:** pinned dependencies, versioned reference data, versioned
  heuristic configuration; results traceable to tool + config + reference
  version.
- **Extensibility:** new heuristics and abnormality classes can be added without
  re-architecting; configuration-driven thresholds.
- **Maintainability:** library-first, tested, documented; runs on Windows/macOS/
  Linux for development (container for deployment).

---

## 10. Constraints & Assumptions

**Constraints**
- Must target **Python 3.9+** (minimum supported version).
- Must deploy as a **Docker / XNAT Container Service** command on an *existing*
  XNAT server (no control over the server stack).
- Must not *require* a GPU.

**Assumptions**
- Input segmentations are **vertebra instance** label maps with a known/
  derivable label→anatomy convention.
- The original scan is available alongside the segmentation when image-based
  features are needed.
- **VerSe** is available and suitable as ground truth for building reference
  distributions and as the evaluation positive control.
- Modality is primarily spine **CT** (the project does not commit to MR support
  initially; see Out of Scope).
- Reviewers are available to provide feedback (Use Case A) and abnormality
  labels (Use Case B) over time.

---

## 11. Out of Scope (initially)

- **Correcting/editing** segmentations — Seg-QC-xnat *assesses*, it does not fix.
- **Training a new segmentation model** — segmentation is consumed, not developed
  (TotalSegmentator is used as-is).
- **A fully supervised abnormality classifier from day one** — the classification
  arm (Use Case B) is an extensibility goal layered on the heuristic core, not
  the initial deliverable.
- **Non-spine anatomy** and non-vertebra structures.
- **Guaranteed MR support** — CT is the primary target; MR may be considered
  later if the feature/heuristic design generalises.
- **A bespoke reviewer GUI** — reporting targets XNAT + standard formats;
  interactive review tooling beyond reports is not an initial commitment.
- **Real-time / clinical-decision use** — this is a research/QC tool, not a
  certified clinical device.

These exclusions keep the initial scope focused on an explainable,
reference-grounded heuristic QC gate that is deployable on XNAT and rigorously
testable, while leaving clear extension points for classification and broader
modality/anatomy support.

---

## 12. Success Criteria

The project is successful when the tool can **automatically**:

1. **Detect empty segmentation.**
2. **Highlight wrong segmentation labels** (mislabelled / misaligned vertebrae).
3. **Highlight out-of-distribution labels** — including cases not currently
   handled (post-operative changes, pathologies), providing a basis to extend
   classification with manual labels.
4. **Be robust to explicitly-handled abnormalities** — pathologies (fractures,
   compression, scoliosis) and implants (pedicle screws, rods, IVD cages) are
   accounted for rather than naively flagged.
5. **Pass ground truth** — VerSe GT segmentations pass QC at a high rate.
6. **Track segmentation quality** — flag rate / feature divergence correlates
   with DICE against GT.
7. **Catch all catalogued failure modes** (§6) on the synthetic/curated corpus.
8. **Deploy and run on XNAT** as a container, producing JSON + human reports.
9. **Run CPU-only** with an optional GPU-accelerated path.

---

## Next Step

Review this vision, then start a **new chat session** and run
`/speckit-aide-create-roadmap` to generate a staged development roadmap.
