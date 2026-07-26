# FACET — Progress Tracker

> **Status:** Draft v2 · **Created:** 2026-06-24 · **Re-issued:** 2026-07-02
> (structure per `.aide/templates/progress.md`; all statuses carried over)
> Step 3 of the AIDE loop. Derived from [`vision.md`](vision.md) and
> [`roadmap.md`](roadmap.md). **Single source of truth for implementation
> status** per stage, deliverable, and acceptance criterion — machine-parsed per
> `.aide/conventions.md` §1 and edited via `python .aide/scripts/aide.py progress set`. Update **incrementally** — never reset a non-planned status back to 📋.

---

## Status legend

| Icon | Meaning     |
| ---- | ----------- |
| 📋   | Planned     |
| 🚧   | In Progress |
| ✅   | Complete    |
| ⏸️ | Deferred    |
| ❌   | Excluded    |

## Stage summary

| Stage | Title                                                                   | Objectives      | Status |
| ----- | ----------------------------------------------------------------------- | --------------- | ------ |
| 0     | Project Scaffolding & I/O Foundation                                    | (foundation)    | ✅     |
| 1     | End-to-End Thin Slice: Empty Detection + Report                         | G1, G4          | ✅     |
| 2     | Geometric & Topological Feature Extraction                              | (feature core)  | ✅     |
| 3     | Spinal Curve: Spline Fit & Deviation Features                           | (feature core)  | ✅     |
| 4     | Heuristic Rule Engine over Failure Modes                                | G2              | ✅     |
| 5     | Synthetic Failure Corpus & Regression Suite                             | G7, G2          | ✅     |
| 6     | VerSe Reference Distributions & Delta Rules                             | G3              | ✅     |
| 7     | Evaluation, Calibration & Metrics*(Phase 1 complete)*                 | G3, G7          | ✅     |
| 8     | Image-Based / Radiomics Features                                        | (Phase 2)       | ✅     |
| 9     | Containerisation & XNAT Command                                         | G5              | ✅     |
| 10    | Portable Compute: GPU Acceleration Path                                 | G6              | ✅     |
| 11    | Extensibility & Abnormality Classification Arm                          | G8              | ⏸️   |
| 12    | Real-VerSe Grounding & Reference Feature Expansion                      | G3, G7          | ✅     |
| 13    | Dataset Ingestion Adapters & Harmonization Schema                       | (G3/G7 enabler) | ✅     |
| 14    | Real-Data Grounding & Heuristic Recalibration                           | G3, G7          | ✅     |
| 15    | Real-XNAT Deployment Validation                                         | G5              | ❌     |
| 16    | Real Failure Corpus & Sensitivity Validation*(retargeted to SPINEPS)* | G2, G7          | 📋     |
| 17    | Foreign-Convention Interop & Orientation-Safe Image Layer               | G2, G6          | 🚧     |
| 18    | Failure-Mode-Specific Metric Surface                                    | G2, G7          | 📋     |
| 19    | Generated Feature & Rule Catalogue + Steering Review                    | G7, G8          | 📋     |
| 20    | Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness      | G2, G7          | 📋     |
| 21    | Real-GT Perturbation Corpus                                             | G3, G7          | 📋     |
| 22    | *(placeholder)* Unified `(scan, seg)` Extraction                    | —              | 📋     |
| 23    | *(placeholder)* Multivariate Normative Model                          | G3              | 📋     |
| 24    | *(placeholder)* Failure-Mode Discovery & Typed Reference Set          | G8              | 📋     |
| 25    | *(placeholder)* Segmenter-Native Perturbations                        | G2              | 📋     |

> **Supersession 2026-07-25.** Stages 0–14 are history and are not reopened. Stage 15 is
> `❌ Excluded` (deployment left scope — see [`vision.md`](vision.md) §0). Stages 17–21
> are the live work; 22–25 are placeholders authored at the full re-vision. Item
> numbering continues from **093** — never restart, `*(Item NNN)*` references are global.

## Two kinds of "done" — implementation vs. validation

This tracker separates two claims that are easy to conflate:

1. **A stage is ✅ when its *code* is built and verified** — against synthetic
   fixtures, golden files, and unit/integration tests. That is evidence about the
   code, not about the world.
2. **An objective is ✅ only when its *measurable outcome*
   ([`vision.md`](vision.md) §2) is demonstrated — on real data wherever the
   outcome says "real".** Building the machinery that *can* measure an outcome is
   not the same as having measured it, and measuring it is not the same as
   *achieving* it.

**Objective status is therefore not derived from stage status.** 🚧 never means
the code is missing — only that the real-world outcome is not yet *demonstrated*.
An objective stays 🚧 for either reason: a **planned** validating stage still
open, or a **shipped** one whose measured goal is not met. Both are captured in
the two tables below — real-run evidence in **Environment-Gated Capability
Verification**, measured-outcome bars in **Outcome targets** — and the `aide`
rollup caps an objective below ✅ while any linked outcome target is not `✅ Met`.

## Objective coverage

_Status = the objective's **measurable outcome** is achieved (not "the code
shipped"). See "Two kinds of done" above._

| Objective                                    | Delivered by                                             | Status |
| -------------------------------------------- | -------------------------------------------------------- | ------ |
| G1 Detect empty / trivially-failed           | Stage 1                                                  | ✅     |
| G2 Detect catalogued failure modes (§6)     | Stages 4, 5*(synthetic only; real failures: Stage 16)* | 🚧     |
| G3 Distinguish failure from variation        | Stages 6, 7, 12*(real grounding: Stage 14)*            | 🚧     |
| G4 Per-case QC report (JSON + human)         | Stage 1 (ext. 2–4)                                      | ✅     |
| G5 Deploy on XNAT*(deferred)*              | Stage 9*(real session data: Stage 15)*                 | 🚧     |
| G6 Portable / GPU*(deferred)*              | Stage 10                                                 | ✅     |
| G7 Evaluable & regression-testable           | Stages 5, 7*(real data: Stages 14, 16)*                | 🚧     |
| G8 Extensible / classification*(deferred)* | Stage 11                                                 | 📋     |

**Why each 🚧 objective is not yet ✅** _(one line each — the detail lives in the
linked row/stage, not here):_

- **G2** — real-world per-mode sensitivity is unmeasured; no real failure corpus
  has ever run. → [Outcome targets](#outcome-targets) (❓) · Stage 16.
- **G3** — the held-out real-GT **FPR ≤ 0.10** target is **❌ Not met**. →
  [Outcome targets](#outcome-targets) · Stage 14.
- **G5** — never installed/run on a real XNAT server (a binary check, not a
  measured bar, so it is verification rather than an outcome target). → the
  "XNAT … real server" verification row · Stage 15.
- **G7** — the real-GT **sensitivity** target is **❌ Not met**, *and* the curated
  challenging-case corpus is unbuilt. → [Outcome targets](#outcome-targets) ·
  Stages 14 (sensitivity) / 16 (corpus).

## Environment-Gated Capability Verification

_One row per capability gated behind an optional package, external tool, **or
real-world dataset / environment**. Status is `❓ Unverified` until the gated path
has actually been exercised with the real dependency/data present (a skip-clean
pytest run, or a synthetic stand-in, does not count as verification — see
`.aide/conventions.md`'s "Environment-gated capabilities" rule), then
`✅ Verified (date, host/CI)`. This table is separate from stage completion
above: a stage reaches ✅ on its graceful-fallback / synthetic-stand-in path
alone; this tracks whether the real dependency/data has ever been exercised._

_`✅ Verified` means the gated path **ran for real** — not that the objective's
outcome was **achieved**; that is the [Outcome targets](#outcome-targets) table's
job. The "Real VerSe GT" row is ✅ because the real cohort ran end-to-end, yet its
G3 FPR target is ❌ Not met. Absence of a row is not verification. Keep the
**Evidence / references** column to one line — a pointer to the CI job, stage,
item, or doc where the detail already lives, not a prose copy of it._

| Capability                                      | Package / Tool / Data                                                                    | Introduced by                                                                                                                     | Status                                                                                       | Evidence / references                                                                                                                                                                                                                                                                                                                  |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Real VerSe GT reference distributions           | VerSe ground-truth cohort (external dataset)                                             | Stage 6*(Items 044, 045)*; closed by Stage 12 *(Item 084)* + Stage 13 adapter; recalibration by Stage 14 *(Items 089–092)* | ✅ Verified (2026-07-19, real VerSe19 via`segqc.datasets` adapter, no manual staging)      | 80 real VerSe19 training subjects →`src/segqc/reference/reference_verse_v1.json`. This row attests only that the real cohort **ran** end-to-end; the measured FPR/sensitivity **outcome** (❌ Not met) and the deferred `reference_delta` rework live in [Outcome targets](#outcome-targets) and the Stage 14 section. |
| Radiomics feature extraction                    | `pyradiomics` (extra: `segqc[radiomics]`)                                            | Stage 8*(Item 060)*                                                                                                             | ✅ Verified (2026-07-14, GitHub Actions CI)                                                  | CI`verify-environment-gated` (`ci.yml`) installs the extra and runs the radiomics tests, failing on any skip (`assert_no_skips.py`). First real run found + fixed a degenerate-mask bug (item 076); green since PR #33.                                                                                                          |
| Containerised pipeline (Docker build + run)     | Docker (external tool, no pip dependency)                                                | Stage 9*(Items 066, 069, 070)*                                                                                                  | ✅ Verified (2026-07-14, GitHub Actions CI)                                                  | Same CI job does a real`docker build` + `docker run` smoke test (`test_066/069/070`); item 080 gated it to a Linux daemon (skip, not error, on Windows-container hosts).                                                                                                                                                         |
| XNAT Container Service command on a real server | XNAT server + Container Service (external environment)                                   | Stage 9*(Items 067, 068, 070)*; **Stage 15 ❌ Excluded**                                                                  | ⏸️ Out of scope (2026-07-25)                                                               | The container itself is verified (Docker row). Installing`command.json` on a real XNAT server never happened and now never will *here*: deployment left scope in [`vision.md`](vision.md) §0 and G5 was removed. Row retained so the artefacts' unverified status stays on the record rather than vanishing with the stage.      |
| Real automatic-segmentation failure corpus      | **SPINEPS** (primary) / TotalSegmentator outputs on real CT (external tool + data) | Stages 5, 7*(Items 041, 053, 057)*; to be closed by Stage 16                                                                    | ❓ Unverified                                                                                | §6 modes are detected only on synthetically perturbed GT; no real-failure output has run, so item 057's per-mode sensitivities are synthetic-only. Curated challenging cases ([`vision.md`](vision.md) §8) unbuilt. → Stage 16 (rung 3), which now depends on Stage 21 (rung 2).                                                   |
| GPU-accelerated feature extraction              | `cupy` (extra: `segqc[gpu]`)                                                         | Stage 10*(Items 071–075)*; closed by *(Item 085)*                                                                            | ✅ Verified (2026-07-16, Quadro P6000 sm_61, CuPy`cupy-cuda12x` 14.1.1, driver 580.159.04) | Verified on a Pascal sm_61 workstation (2× P6000) with the CPU/GPU equivalence tests executing; first CuPy run found + fixed a NEP-50 regression (item 085). Install`cupy-cuda12x` (**not** `cupy-cuda13x` — drops Pascal). No CI GPU coverage — see [`docs/gpu-verification.md`](../gpu-verification.md).               |

## Outcome targets

_One row per **measured outcome** the roadmap commits to — an empirical result
(an error rate, a sensitivity floor) that shipped work *enables* but cannot
*guarantee* by construction. Distinct from the Environment-Gated table above,
which asks "did the real path ever run?"; this asks "did the number meet the
bar?" The two are orthogonal: the "Real VerSe GT" row there is `✅ Verified`
(it ran and returned a number) while the G3 target here is `❌ Not met` (that
number missed the bar). Per `.aide/conventions.md` §1, a target **never blocks
its stage** — a stage's ✅ means its planned work shipped — it gates the
**Objective coverage** rows: an objective linked to a target that is not
`✅ Met` cannot roll up to ✅, and `aide check` errors on an objective claimed ✅
over a `❌ Not met` target. `aide status` prints every target not yet Met._

| Target                                                                                                                                                 | Objective | Attempted by                                                        | Status        | Evidence / follow-up                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------- | ------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ≥1 heuristic detects each §6 failure mode on a**real** automatic-segmentation failure corpus (no per-mode sensitivity regression vs synthetic) | G2        | Stage 16                                                            | ❓ Unverified | No real failure corpus has ever run, so real per-mode sensitivity is unmeasured (item 057's numbers are synthetic-only). Measured when Stage 16 builds/runs the corpus — see the "Real failure corpus" verification row.                                                                                                                                               |
| Held-out real VerSe19 GT (validation + test, disjoint from calibration) yields**FPR ≤ 0.10**                                                    | G3        | Stage 14*(Items 089–092)*; **carried forward to Stage 23** | ❌ Not met    | **0.90** (validation) / **0.95** (test) after a training-fitted `reference_delta` calibration — far from ≤ 0.10, and a threshold-only fix breaks the G7 target below. Diagnosis: the Stage 14 section. The rework is now **Stage 23** (multivariate normative model), which absorbs the `reference_delta` percentile-derived-threshold insight. |
| No real-GT sensitivity regression vs item 057's synthetic baseline (5/8 pipeline-detectable modes at 1.0)                                              | G7        | Stage 14*(Item 091)*; **carried forward to Stage 23**       | ❌ Not met    | Synthetic corpus: no regression; but real-GT perturbations drop`fragment` to **0.90** and `sequence_break` to **0.8125** (below the 1.0 floor). Closes with the FPR target when Stage 23 reworks the rule mechanism.                                                                                                                                    |

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

- [X] `segqc run` on a fixture loads both volumes, prints labelled inventory, writes a stub JSON. *(Items 006, 010; `test_cli_run.py`, `test_010_pipeline.py`)*
- [X] Unit tests for loader and label mapping pass. *(`test_io.py`, `test_labels.py`)*
- [X] Runs CPU-only on Windows, macOS, and Linux. *(NumPy/SciPy CPU-only deps; suite green on Windows)*

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

- [X] 100% of empty / near-empty fixtures flagged `fail` with explicit reason (**G1**). *(`test_007_empty_detection.py`)*
- [X] A non-empty fixture passes the empty check. *(`test_007_empty_detection.py`)*
- [X] JSON validates against schema; human report generated (**G4**). *(`test_009_json_report.py`, `test_010_human_report.py`)*
- [X] Tests cover empty-detection thresholds. *(`test_007_empty_detection.py`)*

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

- [X] Features computed deterministically; values verified against hand-computed expectations.
- [X] Anisotropic-spacing fixture yields correct physical volumes/extents.
- [X] `features` block emitted in JSON; tests cover each feature.
- [X] EDT-based centroid variants computed; centroid depth available per label. *(Item 023)*
- [X] Fragmentation index computed per label and serialised in JSON features block. *(Item 025)*

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

- [X] Spline fits cleanly on GT fixtures; offsets near-zero for GT, large for displaced/mislabelled.
- [X] Robust to a deliberately missing level (no crash, sensible fit).
- [X] Orientation / curvature features in JSON; tests pass. *(Item 019)*
- [X] Neighbour-consistency and neighbourhood-comparison features in JSON. *(Items 020, 024)*
- [X] Regression tests over GT + perturbed cases pass. *(Item 022)*

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

- [X] Each of the 8 §6 failure modes has ≥1 heuristic firing on a crafted example (**G2**).
- [X] Every flag carries a reason + offending labels; thresholds live in config.
- [X] Tests assert correct firing **and** non-firing per rule.

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
- ✅ Cross-platform golden comparison: fresh-vs-committed via numeric tolerance (item 042's byte-identity of asymmetric-geometry floats was only reproducible on the goldens' origin platform; found via CI). *(Item 078)*

**Acceptance.**

- [X] Every §6 failure mode has ≥1 synthetic case and is detected (**G7**, **G2**).
- [X] Full-pipeline regression suite green; golden JSON stable across repeated runs.

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

**Acceptance.** *(Assessed against a 5-subject **synthetic** VerSe-shaped stand-in
— `reference_default.json`, `provenance.source == "synthetic-verse-cohort"` — as
recorded in Stage 12's goal. Real VerSe grounding arrived with Stages 12/13.)*

- [X] Reference artifact builds reproducibly from VerSe and is versioned. *(Synthetic stand-in at the time; since 2026-07-17 also from **real** VerSe19 training — `reference_verse_v1.json`, 25 per-level distributions C1…S. See Stage 13 and the verification table.)*
- [X] GT fixtures fall within reference ranges; perturbed cases fall outside (**G3**) — **on synthetic fixtures**. ⚠️ **Does not hold for real GT:** real VerSe19 GT falls *outside* these ranges often enough to yield a 0.925 FPR, which is the gap Stage 14 closes.
- [X] Tests cover reference loading + delta rules.

---

## Stage 7 — Evaluation, Calibration & Metrics (G3, G7) — ✅ *(Phase 1 complete)* — ✅

**Goal.** Quantify performance and calibrate thresholds against VerSe GT,
TotalSegmentator output, and the synthetic corpus.

**Deliverables.**

- ✅ Segmentation-overlap metrics — per-label & aggregate DICE / Jaccard vs GT. *(Item 050)*
- ✅ Feature-set match / divergence by vertebra label. *(Item 051)*
- ✅ QC-verdict comparison & per-case outcome classification. *(Item 052)*
- ✅ Evaluation harness *accepts* VerSe GT (positive control), TotalSegmentator outputs, and synthetic failures through one cohort-manifest shape — exercised in tests over the **synthetic corpus only**; item 053 scoped itself to require "no VerSe/TotalSegmentator download", and no TotalSegmentator output has ever been run through it (see the verification table). *(Item 053)*
- ✅ Metrics: FPR on GT, sensitivity per failure mode, DICE-vs-flag correlation. *(Item 054)*
- ✅ Threshold-calibration loop; chosen thresholds + metrics recorded here / evaluation report. *(Items 055, 056)*
- ✅ Stage-7 integration into a reproducible `segqc evaluate` entry point + acceptance suite
  (GT low-FPR, injected failures caught, DICE-vs-flag correlation) closing Phase 1;
  calibrated thresholds + metrics recorded. *(Item 057)*

**Acceptance.** *(All three were assessed against the **synthetic** corpus — the
only data available when this stage closed. The boxes stay ticked because the
stage's code and its synthetic validation are genuinely complete; the two marked
**superseded** are claims real data has since overturned or left open. Objective
status now lives in the Objective coverage table, not here.)*

- [X] GT passes at a high rate (low FPR) (**G3**) — **on the synthetic
  `clean_control` GT: FPR 0.0.** ⚠️ **Superseded on real data (2026-07-17):** the
  same thresholds flag real held-out VerSe19 GT at **0.925 / 0.975**. This box
  records what Stage 7 verified; it does **not** evidence G3, which is now 🚧
  pending Stage 14.
- [X] Injected failures caught; flag rate / feature divergence correlates with DICE (**G7**) — **on synthetic injected failures** (5/8 modes detectable through the plain pipeline) and a **synthetic** graded-quality cohort (DICE-vs-flag **-0.943**). ⚠️ **Not yet shown on real failures or real graded data** — see Stage 16.
- [X] Calibrated thresholds + metrics recorded; evaluation reproducible. *(Genuinely met — the harness is reproducible and is exactly what made the real-data measurement possible.)*

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

## Stage 8 — Image-Based / Radiomics Features — ✅

**Goal.** Intensity/radiomics features to strengthen heuristics and seed abnormality detection.

**Deliverables.**

- ✅ Intensity features over each labelled region (+ original scan); optional PyRadiomics integration. *(Items 059, 060)*
- ✅ Feature fusion into the report + ≥1 intensity-based heuristic (e.g. implausible-intensity flag). *(Items 061, 062)*
- ✅ Reference distributions extended with intensity features. *(Items 063, 064)*
- ✅ Intensity-bearing synthetic scan fixtures (HU-painted GT + implausible-intensity variants) enabling local testing of image features. *(Item 058)*
- ✅ Stage 8 integration into `segqc run` + acceptance suite (image features on fixtures; ≥1 intensity heuristic fires; tests pass). *(Item 065)*
- ✅ PyRadiomics present-path robustness: graceful degrade (not a raw exception) when PyRadiomics itself rejects a mask as too small/degenerate for shape/GLCM extraction. *(Item 076)*

**Acceptance.**

- [X] Image features computed on fixtures; ≥1 intensity-based heuristic fires appropriately; tests pass. *(Item 065)*

---

## Stage 9 — Containerisation & XNAT Container Service Command (G5) — ✅

**Goal.** Package the completed pipeline as a Docker image with an XNAT command.

**Deliverables.**

- ✅ Dockerfile (CPU-only base), pinned deps, bundled/mounted reference data. *(Item 066)*
- ✅ XNAT Container Service `command.json` (inputs: session/scan + segmentation; outputs: report resources). *(Item 067)*
- ✅ Entry script mapping XNAT inputs → CLI → output resources. *(Item 068)*
- ✅ Local container smoke test + deployment docs. *(Items 069, 070)*

**Acceptance.** *(Both met as written — but note what they do **not** say: neither
requires an XNAT server. G5's outcome ("runs … on real session data") is
therefore **not** evidenced here — see the XNAT row in the verification table and
Stage 15.)*

- [X] Container runs the pipeline on a mounted case, producing JSON + human report. *(Item 070; `docker build` + `docker run` verified for real in CI — on a **local mounted case**, not an XNAT session.)*
- [X] `command.json` validates; install steps documented (**G5**). *(Item 070; the command definition validates and the install procedure is documented, but has **never been executed against a live XNAT server**.)*

---

## Stage 10 — Portable Compute: GPU Acceleration Path (G6) — ✅

**Goal.** Optional GPU acceleration equivalent to the CPU path; GPU never required.

**Deliverables.**

- ✅ Runtime backend selection (CuPy/cuCIM when present, NumPy/SciPy fallback). *(Item 071)*
- ✅ Backend-aware feature extraction (Stage 2/3 geometric/topological compute routed through the abstraction). *(Item 072)*
- ✅ Equivalence tests: CPU vs GPU produce identical verdicts. *(Item 073)*
- ✅ Performance benchmark. *(Item 074)*
- ✅ CLI/pipeline integration + Stage-10 acceptance closure. *(Item 075)*
- ✅ GPU-present-host verification hardening: fixed the CuPy/NumPy-2.5 (NEP-50) regression in `compute_edt_centroids` (the GPU path passed a Python `int` to `cupy.unravel_index`, which `numpy.can_cast` now rejects — `centroids.py:339`), and guarded the inverse-condition GPU tests to self-skip cleanly on a CuPy-**present** host (mirroring the siblings using `if cupy_available(): pytest.skip(...)`), so the Stage-10 GPU-gated suite runs green on a GPU-enabled host with the CPU/GPU equivalence tests actually **executing** (verified on a Quadro P6000, sm_61). Closes the "GPU-accelerated feature extraction" verification row and corrects `docs/gpu-verification.md`. *(Item 085)*

**Acceptance.**

- [X] GPU path optional + auto-detected; CPU/GPU verdict-equivalence tests pass. *(Item 075)*
- [X] The tool runs fully CPU-only (**G6**). *(Item 075)*
- [X] On a CuPy-present GPU host the GPU-gated suite is green: the CPU/GPU equivalence tests execute (not skip) and pass; the inverse-condition tests skip cleanly and are allow-listed by `assert_no_skips.py`. *(Item 085; verified 2026-07-16 on a Quadro P6000 sm_61 — 155 passed, 16 allow-listed skips, 0 failed)*

---

## Stage 11 — Extensibility & Abnormality Classification Arm (G8) — ⏸️ Deferred — 📋

> **Deferred 2026-07-17** (explicit user instruction): prioritise the Phase-3
> real-data validation arm (Stages 14+) ahead of the deferred G8 extensibility
> objective. Not blocked technically — Stage 7 is its only dependency — simply
> not queued. Revisit after Stage 14 (and as needed 15/16) close.

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

## Stage 12 — Real-VerSe Grounding & Reference Feature Expansion (G3, G7) — ✅

**Goal.** Finish Stages 6/7 against reality: widen the reference distributions
to the full discriminative per-level feature set the engine already computes,
ground them in real VerSe GT, and quantify the false-positive rate on real GT.
Stages 6/7 shipped on a synthetic VerSe stand-in (see the "Real VerSe GT" row in
the Environment-Gated Capability Verification table).

**Deliverables.**

- ✅ Expanded reference feature vocabulary — add fragmentation index, largest-component
  fraction, component count, centroid depth, orientation, and spacing/neighbour-consistency
  deviations through ingest → aggregation → delta rules → config; regenerate the synthetic default. *(Item 081)*
- ✅ Real-VerSe acquisition & versioned artifact build recipe (derived artifact committed, raw scans never). *(Item 082)*
- ✅ One-command reference-refresh wrapper (rebuild + re-evaluate) that degrades gracefully when the uncommitted VerSe cohort is absent. *(Item 083)*
- ✅ Real-VerSe evaluation quantifying the G3 false-positive rate; verification-table closure. *(Item 084)*

**Acceptance.**

- [X] Expanded features appear in the rebuilt reference artifact and are consumed by the delta-to-reference rules; existing synthetic tests stay green.
- [X] The real-VerSe artifact builds reproducibly from a mounted cohort; the refresh wrapper skips the real-VerSe steps cleanly when the cohort is absent.
- [X] The pipeline's false-positive rate on real VerSe GT is quantified and recorded (**G3**, **G7**); the "Real VerSe GT" verification-table row reads Verified. *(Item 084)*

---

## Stage 13 — Dataset Ingestion Adapters & Harmonization Schema (G3/G7 enabler) — ✅

**Goal.** Decouple the pipeline from any single dataset's on-disk layout, naming,
and label scheme via a dataset-agnostic `Cohort`/`Case` interface + declarative
per-dataset adapters, so real cohorts in varied layouts (VerSe19/20,
TotalSegmentator / SPINEPS outputs) are ingested through one interface with no
manual staging. Prerequisite for doing Stage 12's real-VerSe build/evaluation
through a clean interface. Scoped + built 2026-07-16 (queue-011, items 086–088).

**Deliverables.**

- ✅ Dataset-agnostic `Cohort`/`Case` interface (framework side): `Case` =
  `case_id`, `seg_path`, `scan_path|None`, `role` (`gt`|`candidate`),
  `label_convention`, metadata; `Cohort` = ordered, deterministic collection. *(Item 086)*
- ✅ Declarative per-dataset descriptor (data_root, recursive seg/scan globs,
  case-id extraction incl. split subjects, label convention, role, optional
  adapter-only `subsets` = folder/CSV/id-list/glob). *(Item 086)*
- ✅ Resolver (`segqc.datasets.resolve`) materialising a `Cohort`; `ingest_cohort`
  gains a `Cohort`-driven sibling (`ingest_dataset_cohort`) +
  `build_reference_from_cohort`, alongside the retained flat path. *(Item 087)*
- ✅ CLI: `run`/`build-reference`/`evaluate` accept
  `--dataset-schema`/`--data-root`/`--subset` (run = batch mode). *(Item 087)*
- ✅ First committed descriptor: `src/segqc/datasets/verse19.yaml`, validated
  against the mounted cohort (resolved real VerSe19 train 80 / val 40 / test 40,
  split-subjects handled). *(Item 088)*

**Acceptance.**

- [X] The VerSe19 descriptor resolves a mounted cohort to the expected
  `(case_id, seg, scan)` triples (incl. split subjects), deterministically, with
  no manual staging. *(Item 088; verified 2026-07-16 on real VerSe19)*
- [X] `build-reference`/`evaluate`/`run` accept `--dataset-schema`/`--data-root`/
  `--subset` and produce correct output over the nested dataset. *(Item 087)*
- [X] The framework operates only on `Cohort`/`Case`; two disjoint adapter subsets
  (VerSe19 train vs validation) drive a held-out build-vs-evaluate flow the
  framework treats as two plain cohorts.
- [X] Existing synthetic tests stay green (flat ingestion path retained).

---

## Stage 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7) — ✅

**Goal.** Close the G3 gap the first real-data run exposed: recalibrate and
reshape the heuristics against **real** VerSe-derived distributions so real GT
passes at a high rate, **without** buying that specificity by blinding the rules.
Scoped 2026-07-17. The stage's **measured goal** — **held-out real-GT FPR ≤ 0.10
with no sensitivity regression** against item 057's recorded synthetic baseline —
is an outcome the shipped work aims at but cannot guarantee; it is tracked as two
rows in the [Outcome targets](#outcome-targets) table (both **❌ Not met**), not
as this stage's acceptance. The stage is ✅ because **its planned work shipped and
is verified**; the objectives it feeds (G3, G7) stay 🚧, held there by those unmet
targets. See "Why the goal is not met" below.

**Deliverables.**

- ✅ Default config switches from hand-set to **reference-derived bounds** grounded
  on `reference_verse_v1.json` (the switch exists — item 048 — but the shipped
  default is still the synthetic-calibrated hand-set one). *(Item 090)*
- ✅ **FOV-aware `coverage` / `border` rules** — the largest single contributor.
  Real scans are legitimately partial (cervical-only, lumbar-only): a level
  outside the field of view is *not* a missing level, and a vertebra cut by the
  FOV edge is *not* a border defect. Distinguish "absent though inside FOV"
  (a real failure) from "outside FOV" (normal). *(Item 089)*
- ✅ **`fragmentation` / `bounds` tolerance re-derived from real per-level
  variation** rather than synthetic-clean geometry. *(Item 090)*
- ✅ **Recalibration run** via the Stage-7 `calibrate.py` grid search fitted on the
  VerSe19 **training** subset only, then measured on the **held-out**
  validation/test subsets through the Stage-13 adapter (disjoint cohorts — no
  circularity). *(Item 091)*
- ✅ **Anti-gaming sensitivity guard**: re-run the Stage-5 synthetic corpus **and**
  Stage-5 perturbations applied to **real** VerSe GT, asserting per-mode
  sensitivity does not regress below item 057's baseline. FPR alone is trivially
  driven to 0.0 by loosening rules; the FPR/sensitivity **pair** is the bar.
  *(Item 091)*
- ✅ **Evaluation-harness reference wiring** (found + fixed while executing this
  stage's own held-out measurement): `eval.harness.evaluate_case`/
  `evaluate_cohort` and `eval.calibrate.calibrate_thresholds` called plain
  `run_qc` unconditionally, so items 089/090's reference-derived rules and the
  `reference_delta` rule never engaged when FPR was measured via `segqc evaluate` — only single-case `segqc run` attached a reference. Every
  historical "Real VerSe GT" FPR (item 084's, and this stage's own first
  measurement) was computed against the wrong config. Fixed with an opt-in
  `reference=` parameter (default `None`, byte-identical for every existing
  caller) + `segqc evaluate --reference/--reference-artifact` CLI wiring.
  *(Item 092)*
- ✅ Recorded metrics + the G3 target: **target NOT met** (see below); recorded
  honestly rather than committed as achieved.

**Acceptance.** _(Checks of the built thing — all met. The two **measured
outcomes** this stage aimed at, FPR ≤ 0.10 and no sensitivity regression, are
not acceptance boxes; they live in the [Outcome targets](#outcome-targets)
table, both ❌ Not met, and gate G3/G7 rather than this stage.)_

- [X] The recalibration + held-out measurement pipeline runs end-to-end
  (training-fitted grid search on the VerSe19 training subset, measured on the
  disjoint held-out validation/test subsets through the Stage-13 adapter) and
  records held-out FPR + per-mode sensitivity **honestly**, rather than
  committing a target as achieved.
- [X] The item-092 harness fix (opt-in `reference=`) is in place, so the
  reference-derived rules and `reference_delta` actually engage under `segqc evaluate`/`calibrate_thresholds` — every earlier "Real VerSe GT" FPR had been
  measured against the wrong, reference-less config.
- [X] Every flag on a real case still carries a reason + offending labels
  (explainability is not traded away for specificity — every rule still emits a
  reason + labels).
- [X] The "Real VerSe GT" verification row is updated with the
  post-recalibration number (2026-07-19).

**Why the goal is not met, and what would close the targets.** The stage's
deliverables all shipped (so it is ✅), but its measured G3/G7 targets are not
met and are deliberately held open. Threshold-loosening alone cannot clear the
FPR bar without breaking the sensitivity target: the
`reference_delta` rule compares a per-feature z-score (`robust_z`, computed
against the reference's median/IQR) to a single fixed constant across all
levels/features; real per-level distributions have a heavy tail (median
`robust_z` ≈ 0.7, p90 ≈ 1.5, but max ≈ 25 on an 8-case sample), so a threshold
loose enough to admit the tail is also loose enough to admit a genuinely
fragmented or reordered real level. The grid search used here (a handful of
hand-picked candidate thresholds) is a coarser tool than the percentile-derived
approach `bounds`/`fragmentation` already use (item 090: read the threshold
directly off the training distribution's own percentile grid). Deriving
`reference_delta`'s threshold the same way — directly from the training
cohort's own `robust_z`/`distribution_distance` distribution, rather than
grid-searching guessed constants — is the natural next step. It is **not one of
this stage's deliverables** (it is newly-identified follow-on work), so it is
captured as a `gap` in [`insights.md`](insights.md) for the feedback loop to
plan into a future queue, rather than retro-added to a closed stage's
deliverable list. The two Outcome targets close when that rework lands and the
held-out FPR/sensitivity are re-measured against the bar.

---

## Stage 15 — Real-XNAT Deployment Validation (G5) — ❌ Excluded — 📋

> **❌ Excluded (2026-07-25). Reason:** deployment left this project's scope in the
> [`vision.md`](vision.md) §0 supersession — FACET is a library and CLI, not a deployed
> service, and G5 was **removed from scope**, not deferred. No work was ever started, so
> nothing is lost; the Stage 9 artefacts (`command.json`, `docker/`,
> `docs/deployment.md`) are retained as legacy pending relocation out of this repo.
> **Not reopened.** The deliverables below are the original text, kept as provenance.

**Goal.** Execute what Stage 9 documented: install the container's `command.json`
on a **real XNAT server** and run it on **real session data**, which is what G5's
measurable outcome actually requires. Scoped 2026-07-17 by the over-claim audit.

**Deliverables.**

- 📋 A reachable XNAT instance with the Container Service enabled (test/staging
  acceptable) — **an external prerequisite this project does not currently have**.
- 📋 `command.json` installed + enabled on that server; image pushed/loaded to a
  registry it can pull from.
- 📋 One real XNAT session (scan + segmentation resource) run end-to-end, with QC
  reports landing back as session resources.
- 📋 Deployment doc corrected against whatever the real install actually required
  (Stage 9's steps are written from the XNAT docs, never executed).
- 📋 Verification row flipped with server version + date.

**Acceptance.**

- [ ] The command is installed on a real XNAT server and runs on a real session,
  producing JSON + human reports as session resources (**G5**).
- [ ] The documented install steps match what was actually done (drift corrected).
- [ ] The "XNAT Container Service command on a real server" verification row reads
  ✅ Verified.

---

## Stage 16 — Real Failure Corpus & Sensitivity Validation (G2, G7) — 📋

**Goal.** Establish that the heuristics catch failures **that a real segmenter
actually makes**, and build the curated challenging-case corpus
[`vision.md`](vision.md) §8 has always specified but that has never existed.
Scoped 2026-07-17 by the over-claim audit. Depends on Stage 14 (calibrate first,
then measure sensitivity against the calibrated rules).

**Deliverables.**

- 📋 Run **TotalSegmentator** (the vision's reference segmenter) and/or **SPINEPS**
  over real VerSe CT to produce a **real candidate-vs-GT cohort**, ingested as
  `role: candidate` through the Stage-13 adapter.
- 📋 Real per-mode **sensitivity** + **DICE-vs-flag correlation** measured on that
  cohort, replacing the synthetic-only figures in Stage 7's metrics block.
- 📋 **Curated challenging-case corpus** — real pathology / post-op / atypical
  anatomy (`VerSe_fracture_grading.xlsx` is a natural seed), with expected
  verdicts, to test failure-vs-variation on the cases that actually matter.
- 📋 A documented account of which §6 modes real segmenters produce, and at what
  rate — the synthetic corpus asserts all 8 are *possible*, not that they occur.
- 📋 Verification row flipped with tool version + cohort + date.

**Acceptance.**

- [ ] ≥1 heuristic fires on a **real** instance of each §6 failure mode that the
  real cohort actually contains; modes absent from real data are recorded as such
  rather than silently credited (**G2**).
- [ ] Real DICE-vs-flag correlation is measured and correctly signed (**G7**,
  Success Criterion 6).
- [ ] Curated challenging cases run through the pipeline with recorded outcomes;
  legitimate variation is not flagged at the Stage-14 FPR bar.
- [ ] The "Real automatic-segmentation failure corpus" verification row reads
  ✅ Verified.

---

## Stage 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6) — 🚧

**Goal.** Read another tool's output correctly. `segfacet.labels` currently defines
**25 = `S`, 26 = `Cocygis`, 29 = `L6`**; the TPTBox convention SPINEPS emits reads
**25 = `L6`, 26 = `S1`, 29 = `S2`**. Only 28 (`T13`) agrees, so ingesting SPINEPS output
with today's defaults **silently misreads the sacrum as L6** — no error, plausible
numbers, wrong. Must land before any real-segmenter number is computed.

**Deliverables.**

- ✅ Adopt the TPTBox vertebra standard as the default (`DEFAULT_LABEL_MAP`,
  `CANONICAL_ORDER`); retire the legacy table; keep `LabelConvention` overridable. *(Item 093)*
- ✅ Back `segfacet.io`'s `Volume`/`Case` with TPTBox `NII` (orientation-safe load,
  `reorient`, `rescale`/`resample_from_to`, mm-space, `zoom`/`affine`), replacing the
  hand-rolled `_spacing_from_affine` and keeping the public shape stable. *(Item 094)*
- ✅ Environment migration: `requires-python = ">=3.11"`, numpy as a **range**
  (`>=1.26,<3`), regenerated `constraints.txt`, CI leg per numpy major. *(Item 095)*
- ✅ Run-manifest schema (segmenter version/SHA, weights hash, post-processing toggles,
  seed, dataset id, resolved `numpy`/`TPTBox` versions). *(Item 096)*
- 📋 Stage 17 end-to-end validation: real-segmenter round-trip check + verification-row
  closure. *(Item 097)*

**Acceptance.**

- [ ] A regression test asserts labels 25/26/29 match the TPTBox table (**G2**).
- [ ] `reference_verse_v1.json` (keyed by vertebra **name**) loads and scores unchanged —
  no re-fit of the 80-subject VerSe19 distribution was required.
- [ ] The suite is green on both numpy majors (**G6**).
- [ ] A real segmenter output round-trips with correct level names.

---

## Stage 18 — Failure-Mode-Specific Metric Surface (G2, G7) — 📋

**Goal.** Measure per failure mode. "Foreground beyond the main connected component" is
currently recomputed privately inside `heuristics/fragmentation.py` rather than existing
as a named field, so nothing else can read it.

**Deliverables.**

- 📋 Promote stray-component metrics to first-class fields in `features/components.py`
  (stray volume mm³, count, fraction); fragmentation rule reads rather than recomputes.
- 📋 Per-mode metric API, reusing `eval/overlap.py::compute_overlap` for Dice/Jaccard and
  its aggregates — no new overlap code.
- 📋 Cohort-level per-mode report supporting run-vs-run comparison of a segmentation tool.

**Acceptance.**

- [ ] Each §6 mode has ≥1 named metric moving monotonically with injected severity of that
  mode, and comparatively insensitive to the others (**G2**).
- [ ] The fragmentation rule's behaviour is unchanged by the refactor (**G7**).

---

## Stage 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8) — 📋

**Goal.** Make the feature set reviewable, then review it. `FEATURE_CATALOG` in
`scripts/aide_status_report.py` is hand-maintained (9 groups / 41 entries, commented
*"keep in sync by hand"*) while a realised record has **185 distinct leaf paths**. Nothing
verifies they agree, and no document records which failure mode each feature serves.

**Deliverables.**

- 📋 Catalogue **generated** from the realised record shape + extractor docstrings, with
  columns for computation, units, scale sensitivity, targeted §6 mode, consuming rules,
  and a keep / retune / retire / unwired status.
- 📋 Drift test: every leaf path covered; CI fails on an undocumented feature.
- 📋 Golden-file decision table — one row per committed golden: what it asserts, keep or
  retire, what replaces it. Working assumption **retire most** (whole-record snapshots of
  a corpus Stage 21 replaces). Byte reproducibility is guarded by the independent
  intra-run `dest1 == dest2` determinism assertions, not by the goldens.

**Acceptance.**

- [ ] The catalogue is generated, not hand-written; the drift test fails on a deliberately
  undocumented feature (**G7**).
- [ ] Every feature carries a status and a named failure mode, or is marked `unwired`
  (**G8**).
- [ ] The golden decision table is complete and signed off by the human reviewer.

---

## Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness (G2, G7) — 📋

**Goal.** Close the gap between "the suite is green" and "the rules are specific".
Measured 2026-07-25 on the committed corpus: **10 rules registered and enabled, 4 ever
fire**; `bounds`, `mislabel`, `overlap`, `intensity`, `reference_delta` and
`intensity_reference_delta` fire on **zero** cases. **3 of 9 cases fire nothing at all**
through `run_qc` — their intended rule is reachable only via a hand-reconstructed record
(item 040's documented limitation), so **3 of 8 failure modes are not detected
end-to-end** while the corpus reads as covering all eight. Separately, `verify_case`
never asserts that *no other* rule fires; cross-talk is 0/9 today, so the assertion is
free to adopt now and expensive later.

**Deliverables.**

- 📋 Traceability matrix: 8 failure modes × features × 10 rules, gaps visible.
- 📋 Specificity assertion — no unintended rule may fire — adopted as a ratchet.
- 📋 Reachability hole closed: modes 1/4/8 made pipeline-detectable, or recorded
  explicitly as not detected end-to-end. Not both silent.
- 📋 Per-rule corpus-exercise reporting.

**Acceptance.**

- [ ] Every registered rule is exercised by ≥1 case or recorded as unexercised with a
  reason (**G2**).
- [ ] The specificity assertion is enforced for every corpus case.
- [ ] The end-to-end detection count is stated honestly here rather than implied (**G7**).

---

## Stage 21 — Real-GT Perturbation Corpus (G3, G7) — 📋

**Goal.** Move calibration off hand-crafted geometry. The corpus is built from synthetic
fixtures (five stacked lumbar blocks, 1 mm isotropic); thresholds fitted to it are fitted
to a shape no real spine has, and as the rule set grows, hand-crafted cases increasingly
trip rules they were never meant to exercise. Three rungs of realism, no longer conflated:
**1** hand-crafted fixtures (unit-test scaffolding only) · **2** real GT + scripted
perturbation (*this stage* — calibration, regression, sensitivity) · **3** real segmenter
failures (Stage 16 — validation).

**Deliverables.**

- 📋 Existing `Perturbation` operators re-sourced from **real VerSe GT**, with a manifest
  of subject IDs, seeds and operator parameters so the corpus reproduces without
  committing bulk data.
- 📋 A real clean-control baseline — a *cohort* false-positive rate, not one synthetic
  pass case.
- 📋 Threshold calibration and all sensitivity claims moved to rung 2.
- 📋 Stage 19's golden decision acted on: retire corpus-snapshot goldens as their cases
  are superseded; do **not** regenerate the nine snapshots against the new corpus.

**Acceptance.**

- [ ] Every threshold-bearing rule is calibrated against rung 2, not rung 1 (**G3**).
- [ ] Stage 20's specificity assertion holds on the new corpus, or each violation is
  recorded with a reason (**G7**).
- [ ] The corpus regenerates reproducibly from its manifest.

---

# Placeholders — authored at the full re-vision

> Stages 22–25 are recorded so numbering stays stable and dependencies can be named.
> **Deliberately not specified** — each depends on measurements that do not exist yet,
> and a stage written before its evidence would be speculation.

---

## Stage 22 — Unified `(scan, seg)` Extraction — 📋

**Goal.** One entry point over the paired scan and segmentation, replacing the current
split between the label-map-only and intensity-aware paths.

**Deliverables.** 📋 *Deliberately unspecified until Stages 17–21 land.*

---

## Stage 23 — Multivariate Normative Model (G3) — 📋

**Goal.** Replace the univariate per-level percentile z-scores aggregated by RMS with a
model that accounts for covariance between features.

**Carries forward** the two `❌ Not met` Outcome targets (held-out real-GT FPR ≤ 0.10; no
real-GT sensitivity regression) and absorbs the open insight that `reference_delta`'s
threshold should derive from the training cohort's own percentiles rather than a hand-set
constant — the fixed-constant mechanism is what cannot clear the FPR target without
sacrificing sensitivity.

**Deliverables.** 📋 *Deliberately unspecified until real-segmenter measurements exist.*

---

## Stage 24 — Failure-Mode Discovery & Typed Reference Set (G8) — 📋

**Goal.** Cluster the feature space to surface failure modes absent from the §6 catalogue;
curate per-class exemplars a new case can be assigned against.

**Deliverables.** 📋 *Deliberately unspecified until Stage 21's corpus exists.*

---

## Stage 25 — Segmenter-Native Perturbations (G2) — 📋

**Goal.** Rung 3's generator — perturbations derived from what a real segmenter actually
does wrong, rather than from a catalogue written in advance.

**Deliverables.** 📋 *Deliberately unspecified until Stage 16 has characterised real
failures.*
