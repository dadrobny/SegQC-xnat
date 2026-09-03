# FACET — Progress Tracker

> **Status:** v3 · **Created:** 2026-06-24 · **Re-issued:** 2026-09-03 against
> [`roadmap.md`](roadmap.md) v3 (incremental: Stage 30 added, summary rows for Stages
> 28–30 added, every existing status and attestation carried over unchanged)
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
| 🔍   | In Review   |
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
| 17    | Foreign-Convention Interop & Orientation-Safe Image Layer               | G2, G6          | ✅     |
| 18    | Failure-Mode-Specific Metric Surface                                    | G2, G7          | ✅     |
| 19    | Generated Feature & Rule Catalogue + Steering Review                    | G7, G8          | ✅     |
| 20    | Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness      | G2, G7          | ✅     |
| 21    | Real-GT Perturbation Corpus                                             | G3, G7          | 📋     |
| 22    | *(placeholder)* Unified `(scan, seg)` Extraction                    | —              | 📋     |
| 23    | *(placeholder)* Multivariate Normative Model                          | G3              | 📋     |
| 24    | *(placeholder)* Failure-Mode Discovery & Typed Reference Set          | G8              | 📋     |
| 25    | *(placeholder)* Segmenter-Native Perturbations                        | G2              | 📋     |
| 26    | Carried-Defect Remediation (pre-real-data)*(runs next)*               | G2, G7          | ✅     |
| 27    | Feature Schema Taxonomy & Coordinate System                             | G8              | 📋     |
| 28    | Spinal Curve Model: Formulation, Offset & Orientation                   | G2, G7          | ✅     |
| 29    | Golden Retirement & Test-Artifact Hygiene                               | G2, G7          | ✅     |
| 30    | Failure-Mode Specification: the §6 catalogue as an authored source *(runs next)* | G2, G7, G8 | 🚧     |

> **Supersession 2026-07-25.** Stages 0–14 are history and are not reopened. Stage 15 is
> `❌ Excluded` (deployment left scope — see [`vision.md`](vision.md) §0). Stages 17–21
> are the live work; 22–25 are placeholders authored at the full re-vision. Item
> numbering continues from **093** — never restart, `*(Item NNN)*` references are global.

> **Feedback loop 2026-08-11.** Stages **26** and **27** were scoped from triaged
> [`insights.md`](insights.md) entries that had accumulated no owner. They are numbered
> after the placeholders so numbering stays stable, but **run earlier than their numbers
> suggest**: Stage 26 runs **next, ahead of Stage 20** (it fixes surfaces Stage 20 audits),
> and Stage 27 runs after Stage 20 and before Stages 23/24. The same loop reworded Stage
> 19's G8 criterion and clarified what Stage 20's traceability matrix must prove — see
> [`roadmap.md`](roadmap.md).

> **Stage 28 scoped 2026-08-27.** Numbered after Stage 27 so numbering stays stable, but
> **runs before Stage 20** — it changes which rules fire on which cases, and Stage 20 both
> audits that and pins a specificity baseline against it. It also supersedes part of Stage
> 20's reachability deliverable: modes 1 and 4 are one defect (the interpolating spline
> fit), not two, and the FOV-headroom remedy Stage 20 proposed for mode 1 is measurably
> not the cause. Run order from here: **28 → 20 → 27 → 21 → 16**.

> **Stage 29 scoped 2026-08-30** (queue-017 boundary triage), the same construction as
> Stages 26–28: numbered for stability, **runs next, ahead of Stage 20**. It executes the
> maintainer-signed golden retirement (pulled forward from Stages 21/27), makes
> committed-artifact comparisons tolerance-by-construction, and sweeps the located defects
> queue 017 recorded — including `consistency.py`'s mode-4 monotonicity, which closes
> Stage 28's one unticked non-adjudication acceptance half. Run order from here:
> **29 → 20 → 27 → 21 → 16**.

> **Stage 30 scoped 2026-09-03** (queue-019 boundary feedback loop; human gate 3), the
> same construction as Stages 26–29: numbered for stability, **runs next, ahead of the
> remainder of Stage 20**. Queue-019 was cut after item 138 because its remaining items
> each rested on a definition of the §6 failure modes that existed in five partial sources
> and no specification. Stage 30 authors that specification per [`vision.md`](vision.md)
> v3 §6 and re-points the generated matrix at it as a conformance report; Stage 20's
> items 139–142 are re-specified against it and re-queued after its maintainer sign-off.
> Full statement in [`roadmap.md`](roadmap.md), which also states the run order once at
> its top: **30 → 20 (remainder) → 27 → 21 → 16**.

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
| G2 Detect catalogued failure modes (§6)     | Stages 4, 5, 18, 28*(specification: Stage 30; traceability and specificity: Stage 20; synthetic only — real failures: Stage 16)* | 🚧     |
| G3 Distinguish failure from variation        | Stages 6, 7, 12*(real grounding: Stage 14)*            | 🚧     |
| G4 Per-case and cohort reports               | Stage 1 (ext. 2–4); cohort characterisation: Stage 18   | ✅     |
| G5 Deploy on XNAT*(deferred)*              | Stage 9*(real session data: Stage 15)*                 | 🚧     |
| G6 Portable / GPU*(deferred)*              | Stage 10                                                 | ✅     |
| G7 Evaluable & regression-testable           | Stages 5, 7, 29*(real data: Stages 14, 16)*            | 🚧     |
| G8 Extensible / classification               | Stages 19, 27, 30 (the add-a-mode path); classification arm: Stage 11*(deferred)* | 🚧     |

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
- **G8** — the catalogue is generated (Stage 19 ✅), but the add-a-mode path — an
  authored specification a new mode enters through, with the conformance artifacts
  regenerated — is Stage 30's, and the schema taxonomy is Stage 27's; neither has
  shipped. The classification arm (Stage 11) stays deferred and is not what holds
  this at 🚧.

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
| Real SPINEPS-output label-convention round-trip | Real SPINEPS-produced label map (external tool + data), via `SEGFACET_SPINEPS_FIXTURE` | Stage 17 (Item 097)                                                                                                                | ❓ Unverified                                                                                | No committed real-SPINEPS fixture; requires `SEGFACET_SPINEPS_FIXTURE` pointing at a directory of real SPINEPS output. Narrower than the "Real automatic-segmentation failure corpus" row above (Stage 16 sensitivity/DICE scope) — this row is level-**naming** correctness only. Mechanics unconditionally covered by a committed synthetic TPTBox-labeled fixture (`tests/test_097_stage17_validation.py::test_ac4_*`); the real-data path (`test_ac6_real_spineps_fixture_level_names_correct`) is a genuine, cleanly-skipping `skipif` not yet exercised for real. |
| Real segmentation-tool run-vs-run per-mode comparison | Two real runs of a real segmenter over the same cohort (e.g. a post-processing step on vs. off), external tool + data | Stage 18 *(Items 101, 102)*                                                                                                       | ❓ Unverified                                                                                | Only ever exercised on the synthetic corpus and on in-memory perturbed clean spines (item 101's API tests, item 102's CLI replay); no two real segmenter runs exist in this repo. Narrower than the "Real automatic-segmentation failure corpus" row above (that row is Stage 16's per-mode **sensitivity** scope; this row is run-vs-run **attribution** scope). |

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

## Human gates

_One row per decision only a person can make, blocking work until they make it.
Not an acceptance box (those are observable checks of the built thing) and not
an Environment-Gated row (that asks "did the real path ever run?", after the
fact). This asks "may the work start yet?", and the answer is out-of-band._

_Both rows below are the same **kind** of gate: an external-data prerequisite
this repo cannot satisfy from inside itself. Per the 2026-07-25 pivot, the GPU
/ SPINEPS / GSTT half of the programme lives in a separate private repo — so
every real-segmenter and real-clinical input arrives here as a hand-off, on
someone's decision, not as something a loop can go and fetch._

_Resolved only by a person, only via `aide gate approve <n> --evidence "…"`
(or `gate decline`). A decline **keeps blocking** — re-plan instead. No agent
may resolve one._

| Gate | Blocks | Status | Decision / evidence |
|------|--------|--------|---------------------|
| Real segmenter output on real CT handed over to this repo — SPINEPS (primary) and/or TotalSegmentator label maps + manifest, produced in the programme repo, sufficient to build the real candidate-vs-GT cohort | stage 16 | ⏳ Awaiting | Blocks the whole of Stage 16, and transitively Stage 25, whose deliverables are "deliberately unspecified until Stage 16 has characterised real failures". Closes the "Real automatic-segmentation failure corpus" Environment-Gated row and the G2 Outcome target. Not the same prerequisite as the Stage 21 rung-2 corpus, which needs only real VerSe GT — already ✅ Verified and **not** gated. |
| Access approved for the curated challenging-case source data — real pathology / post-op / atypical anatomy ([`vision.md`](vision.md) §8), `VerSe_fracture_grading.xlsx` a natural seed, plus any clinical cohort requiring an ethics/data-sharing sign-off | stage 16 | ⏳ Awaiting | Independent of the row above: real *segmenter output* does not supply the *challenging cases*, and either arriving alone leaves a Stage 16 deliverable unbuildable. Kept a separate row so approving one does not silently read as approving both. |
| §6 failure-mode taxonomy — the modes need a specification before the rest of Stage 20 can be built. Six decisions are owed, listed in [`failure-mode-taxonomy-handover.md`](failure-mode-taxonomy-handover.md) §10: the anchor semantics for modes 4 and 7, whether mode 6's `mislabel` firing is a true positive or cross-talk, whether the evidence rung attaches to the mode or the edge, the per-mode schema and lifecycle, whether this becomes a new stage or a Stage 20 rescope, and the `vision.md` §6 wording that currently forbids a `proposed` mode | 139, 140, 141, 142 | ✅ Approved (2026-09-03) | Adopted failure-mode-taxonomy-handover.md section 12 (2026-09-03) in full. (1) Modes 4 and 7 keep the Stage-18 metric path as anchor and the rule's read path as a separate, separately-labelled column. (2) Mode 6 firing mislabel is a true co-detection: expected_firing = {border, mislabel} for mode6_crop_at_border, with the mode-1 / mode-6 discriminator (a border-touching face) written into the specification. (3) The evidence rung attaches to each mode-to-rule edge, authored; the mode's rung is derived as the strongest edge. (4) The section 6 schema and four-state lifecycle are adopted, with expected_firing authored per corpus case and implemented / validated derived from live state. (5) A new Stage 30 authors the specification and runs before the remainder of Stage 20; items 139-142 are re-specced against it in the queue after Stage 30's. (6) vision.md section 6 is reworded as part of a re-issued vision v3 now, not a point edit: a mode is claimed covered only with the rule(s) that detect it, and a proposed mode is not a claim of coverage. Items 139-142 remain held until Stage 30's specification is signed off. |
| Spinal curve model — the deformity envelope the fit must represent without flagging it. How much scoliotic / kyphotic curvature is normal anatomy the model must follow, versus deviation it must report; and the accepted false-negative cost of a stiffer fit | 119, 120, 121, 123, 125 | ✅ Approved (2026-08-27) | Adopt item 118's proposal: smoothing_spline at s = n_points, chord-length u, leave-one-out evaluation, and max_offset_mm raised 15.0 -> 25.0. Envelope set above the 21.073357 mm leave-one-out ceiling measured across VerSe19 GT including the most coronally-deviated cases, and below the ~5 mm leave-one-out separation a small displacement produces. Accepted cost: a genuine displacement smaller than the envelope may be missed. Expected to be revised into separate normal and scoliotic envelopes later -- see docs/spinal-curve-model.md. *(Superseded 2026-08-29 by a second human decision during item 123: terminal vertebrae (first/last of each subject's ordered sequence) are excluded from the mislabel rule and threshold derivation, and the shipped threshold is `max_offset_mm = 13.0` (interior-only p99 12.91 mm at T10, real 80-subject VerSe19 cohort). Full record in `docs/reference-build.md`'s rebuild records and item 123's spec Decisions log.)* |

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
- ✅ Local vertebra neighbourhood comparison (sliding window, n=3–5): per-vertebra deviation from neighbourhood mean/median of centroid spacing, spline offset, and volume, plus a deviation score and outlier flag. *(Item 024)* ⚠️ **Correction, 2026-08-11:** the module (`features/neighbourhood.py`) was implemented in full but **wired into nothing** — absent from `pipeline.py`, `feature_report.py` and all 10 rules, which is why it never appeared in item 103's 111-entry catalogue. ✅ **Wired, 2026-08-14 (Item 110):** the module was generalised to an arbitrary named-feature API and wired into `extract_feature_record`/`feature_report.py` as `stage3.per_label_neighbourhood[]` (computed and serialised for every case with ≥ 2 labels). It is **consumed by no rule** — `status == "unwired"` in the regenerated feature catalogue, confirmed by Item 110's AC11 (every corpus case's verdict and findings are unchanged by the wiring). No outlier this module computes is ever flagged to a verdict; that remains Stage 20's call, same as any other unwired feature. *(Item 024)*

**Acceptance.**

- [X] Spline fits cleanly on GT fixtures; offsets near-zero for GT, large for displaced/mislabelled.
- [X] Robust to a deliberately missing level (no crash, sensible fit).
- [X] Orientation / curvature features in JSON; tests pass. *(Item 019)*
- [X] Neighbour-consistency features in JSON. *(Item 020)* *(Item 024: neighbourhood-comparison module generalised and wired into pipeline as of Item 110 — `stage3.per_label_neighbourhood[]` is computed and serialised for every ≥2-label case, but consumed by no rule; status "unwired" in the feature catalogue.)*
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
  framework (item 036); component/shape perturbations — fragment, fuse,
  inject islands (item 037); coverage/border/overlap perturbations — remove
  level, crop at border, force overlap (item 038); identity/ordering/
  alignment perturbations — displace, relabel/swap, sequence-break (item 039).
  *(Items 036–039)*
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

## Stage 7 — Evaluation, Calibration & Metrics (G3, G7) *(Phase 1 complete)* — ✅

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

## Stage 11 — Extensibility & Abnormality Classification Arm (G8) — Deferred — ⏸️

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

## Stage 15 — Real-XNAT Deployment Validation (G5) — Excluded — ❌

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

## Stage 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6) — ✅

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
- ✅ Stage 17 end-to-end validation: real-segmenter round-trip check + verification-row
  closure. *(Item 097)*

**Acceptance.**

- [x] A regression test asserts labels 25/26/29 match the TPTBox table (**G2**).
  *(Item 093 unit-level; re-confirmed end-to-end via a full `segfacet run` by
  item 097's AC1.)*
- [x] `reference_verse_v1.json` (keyed by vertebra **name**) loads and scores unchanged —
  no re-fit of the 80-subject VerSe19 distribution was required.
  *(Item 093 AC5/AC7; re-confirmed by item 097's AC2.)*
- [x] The suite is green on both numpy majors (**G6**).
  *(Item 095's `test-numpy-majors` CI job runs both legs on every push/PR
  including this item's changes; not independently re-observed by a live CI
  run from this execution environment — no `gh` CLI / CI access available
  here. See item 097's Decisions log.)*
- [ ] A real segmenter output round-trips with correct level names. *(Unticked
  because no real SPINEPS output is available in this execution environment
  — `SEGFACET_SPINEPS_FIXTURE` is unset. The round-trip **mechanics** are
  unconditionally verified via a committed synthetic TPTBox-labeled fixture
  (item 097 AC4); the real-SPINEPS check is a genuine, cleanly-skipping
  `skipif` (item 097 AC5) that has not yet run for real. See the "Real
  SPINEPS-output label-convention round-trip" row in [Environment-Gated
  Capability Verification](#environment-gated-capability-verification).)*

---

## Stage 18 — Failure-Mode-Specific Metric Surface (G2, G7) — ✅

**Goal.** Measure per failure mode. "Foreground beyond the main connected component" is
currently recomputed privately inside `heuristics/fragmentation.py` rather than existing
as a named field, so nothing else can read it.

**Deliverables.**

- ✅ Promote stray-component metrics to first-class fields in `features/components.py`
  (stray volume mm³, count, fraction); fragmentation rule reads rather than recomputes. *(Item 098)*
- ✅ Per-mode metric API, reusing `eval/overlap.py::compute_overlap` for Dice/Jaccard and
  its aggregates — no new overlap code. *(Item 099)*
- ✅ Severity-ladder monotonicity + cross-mode specificity harness (the **G2** acceptance):
  graded ladders per §6 mode from the existing perturbation-operator constructor knobs. *(Item 100)*
- ✅ Cohort-level per-mode report supporting run-vs-run comparison of a segmentation tool. *(Item 101)*
- ✅ Stage 18 end-to-end validation: CLI-level replay + verification-row closure. *(Item 102)*

**Acceptance.**

- [x] Each §6 mode has ≥1 named metric moving monotonically with injected severity of that
  mode, and comparatively insensitive to the others (**G2**). *(a) All eight modes have a
  named metric that is monotone and strictly changing across its own ladder (item 100,
  replayed by item 102). (b) Seven of eight ladders clear the strict-specificity bar
  (`margin > 1.0`); **mode 6** does not — measured margin `0.3585`, its ladder driving
  mode 1's `unanchored_foreground_fraction` `2.79×` harder than mode 1's own FOV-capped
  ladder, recorded in `KNOWN_CROSS_MODE_COUPLINGS`. (c) **Mode 7** carries a declared
  two-rung degenerate ladder (metric structurally capped at 1 by the label convention).
  (d) All of it is measured on synthetic ladders only.*
- [x] The fragmentation rule's behaviour is unchanged by the refactor (**G7**). *Evidenced
  at report level by item 102's AC5: nine CLI `segfacet run --no-reference` invocations
  whose `verdict` + `findings` equal the frozen pre-098 snapshot — above item 098's
  rule-level regression.*

---

## Stage 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8) — ✅

**Goal.** Make the feature set reviewable, then review it. `FEATURE_CATALOG` in
`scripts/aide_status_report.py` is hand-maintained (9 groups / 41 entries, commented
*"keep in sync by hand"*) while a realised record has **185 distinct leaf paths**. Nothing
verifies they agree, and no document records which failure mode each feature serves.

**Deliverables.**

- ✅ Catalogue **generated** from the realised record shape + extractor docstrings, with
  columns for computation, units, scale sensitivity, targeted §6 mode, consuming rules,
  and a keep / retune / retire / unwired status. *(Item 103)*
- ✅ Drift test: every leaf path covered; CI fails on an undocumented feature.
  *(Item 104)*
- ✅ Golden-file decision table — one row per committed golden: what it asserts, keep or
  retire, what replaces it. Working assumption **retire most** (whole-record snapshots of
  a corpus Stage 21 replaces). Byte reproducibility is guarded by the independent
  intra-run `dest1 == dest2` determinism assertions, not by the goldens. *(Item 105)*
- ✅ Stage validation + verification-row closure. *(Item 106)*

**Acceptance.**

- [x] The catalogue is generated, not hand-written; the drift test fails on a deliberately
  undocumented feature (**G7**). *(The zero-argument `python -m segfacet.catalogue`
  regeneration leaves both committed artifacts byte-identical to their pre-call
  content. The count agreed by four independent surfaces is `N = 111`. The
  status report (`scripts/aide_status_report.py`, with `FEATURE_CATALOG` /
  `UNWIRED_EXTRACTORS` deleted per item 103) renders the generated catalogue
  with no manual post-editing and degrades to a placeholder when the artifact
  is hidden. Drift rehearsed at two strengths: (i) hermetic, in-suite —
  injecting one extra key into a real driver record through item 103's AC16
  seam makes both item 104's reporter and the shipped `strict=True` mechanism
  fail, naming the exact undocumented path, and the revert restores green; (ii)
  real-source, manual (item 106 Validation step 3, 2026-08-11) — inserting
  `"zzz_drift_probe": 0.0` into `feature_report.py`'s `geometry_to_dict()` made
  `test_ac8_direction1_clean_on_current_tree`,
  `test_ac12_real_strict_build_succeeds_on_current_tree` and
  `test_ac15_direction3_clean_on_current_tree` fail, naming
  `per_label.{label}.geometry.zzz_drift_probe`; `git checkout --` restored a
  clean, green tree. See item 106's spec, "### Real-source drift rehearsal".)*
- [x] Every feature carries a status and a named failure mode, or is marked `unwired`
  - **2026-09-03** → Re-measured 2026-09-03 on the committed docs/aide/feature_catalogue.generated.json after items 136-138: the artifact now holds 138 entries (not 111), and the 72-entry statused-but-mode-unmapped bucket (mode_evidence == rule_unmapped) is empty - 0 entries. Split: 86 entries carry no mode evidence, 52 carry some (48 name at least one failure mode); 12 are attributed through a rule's recorded mode-less declaration (rule_mode_less: intensity, intensity_reference_delta). Status split: 66 retune, 34 keep, 30 unwired, 8 retire. The bucket shrank first because items 110/120/124/131/132 added leaf paths and moved attributions (138 entries, 18 rule_unmapped measured 2026-09-02 while specifying item 136), then closed because item 137 dispositioned the four mode-less rules. Stage 20's honest-count item should quote this split, not the attestation's.
  (**G8**). *(Measured on the committed artifact, `N = 111`: every entry
  carries a status from `{keep, retune, retire, unwired}`. Three-way partition:
  **35 moded** (statused, `failure_modes` non-empty), **4 unwired**, **72
  statused-but-mode-unmapped** — this last bucket is a real shortfall against
  the criterion's literal wording (a path consumed only by a rule carrying no
  §6 mode mapping — `bounds`, `intensity`, `reference_delta`,
  `intensity_reference_delta` — gets `status == "keep"`, `failure_modes ==
  ()`, `mode_evidence == ("rule_unmapped",)`: statused, not `unwired`, names no
  mode), closed by Stage 20's traceability matrix. **Steering review (2026-07-28,
  item 106):** all 111 `keep`/`unwired` entries (54 `keep`, 57 `unwired` at the
  pre-override build) presented to the maintainer across a 12-group live
  walkthrough; result recorded in `src/segfacet/feature_docs.py::STATUS_OVERRIDES`
  — **66 `retune`, 8 `retire`** (the `keep` bucket is reduced to 33 and
  `unwired` to 4 accordingly; 37 entries confirmed to stay at derived status).
  A `retune`/`retire` status **records** the maintainer's judgment; it does not
  execute it — no threshold moved, no extractor deleted, no feature stopped
  being computed. **Stage 19 decides, Stage 21 executes** — this is item 105's
  golden-file retire dispositions (the 11 rows of `golden-decision-table.md`);
  the *feature* `retire`/`retune` calls this item recorded have no assigned
  executor yet and are not implied to be Stage 21's. All of the above is
  measured on in-package synthetic driver records and the committed artifact,
  never on real data. See item 106's spec, "### Stage-19 steering review".)*
  **Criterion reworded 2026-08-11:** the roadmap's G8 sentence now
  names this third state explicitly — *statused but mode-unmapped, with the
  consuming mode-less rule named* — so it is no longer unsatisfiable-as-written by
  the mechanism this stage shipped, and the 72-entry bucket is a recorded state
  rather than a shortfall. The substantive close stays **Stage 20**'s: map
  `bounds` / `intensity` / `reference_delta` / `intensity_reference_delta` to §6
  modes, or record that they target none. Note the *feature* `retune`/`retire`
  calls recorded above now have an assigned carrier: **Stage 27** (schema
  taxonomy) for the structural two-thirds of them.
- [x] The golden decision table is complete and signed off by the human reviewer.
  *(Signed off 2026-07-28: all 36 rows of `docs/aide/golden-decision-table.md`
  reviewed individually — 11 retire (the 9 corpus-golden whole-record
  snapshots plus, overturning the initial draft, the two report-formatting
  goldens `tests/golden/016_features_report.json`/`022_stage3_report.json`),
  25 keep. See item 105.)*

---

## Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness (G2, G7) — ✅

**Goal.** Close the gap between "the suite is green" and "the rules are specific".
Measured 2026-07-25 on the committed corpus: **10 rules registered and enabled, 4 ever
fire**; `bounds`, `mislabel`, `overlap`, `intensity`, `reference_delta` and
`intensity_reference_delta` fire on **zero** cases. **3 of 9 cases fire nothing at all**
through `run_qc` — their intended rule is reachable only via a hand-reconstructed record
(item 040's documented limitation), so **3 of 8 failure modes are not detected
end-to-end** while the corpus reads as covering all eight. Separately, `verify_case`
never asserts that *no other* rule fires; cross-talk is 0/9 today, so the assertion is
free to adopt now and expensive later.

**Scope clarified 2026-08-11** (full statement in
[`roadmap.md`](roadmap.md)). The matrix is read in three directions and only two must ever
be complete: **mode → rule** (complete, always — an uncovered §6 mode is a defect) and
**rule → mode** (complete, always — a rule targeting no catalogued mode is itself a
finding; four rules sit there today). **Feature → rule is deliberately incomplete**: the
record is an over-broad vector rules *select from*, so a leaf path no rule reads is
inventory (`unwired`), not a gap — 34 of 111 catalogued paths, and that is an expected
steady state, not a shortfall. Each mode also carries an **evidence rung**:
synthetic-demonstrable · needs real data · structurally unobservable in single-channel
input (mode 8). Modes, rules and features grow **in tandem** — a new mode arrives with its
rule(s) and any features they need; features may be added alone, modes and rules may not.

**Deliverables.**

- ✅ Traceability matrix, *generated* (not hand-maintained): 8 failure modes × 10 rules ×
  the features each rule consumes, scored in all three directions, every mode row carrying
  its evidence rung. *(Item 138)*
- ✅ Rule-layer declaration seam: every registered rule carries a `RuleModeDeclaration`
  stating its targeted §6 modes, its mode-less reason, or a pending reason. Six rules
  declared from corpus evidence; the four contested ones are **pending**, their disposition
  deliberately left to item 137. Does not itself close Stage 19's G8 shortfall. *(Item 136)*
- ✅ The four mode-less rules (`bounds`, `intensity`, `reference_delta`,
  `intensity_reference_delta`) mapped to §6 modes, or recorded as targeting none with a
  reason — the root close of Stage 19's G8 shortfall. *(Item 137)*
- ⏸️ Specificity assertion — no unintended rule may fire — adopted as a ratchet.
  ⚠️ **Deferred, 2026-09-03:** queue-019 was cut short after item 138. The ratchet's first
  real case is mode 6's corpus case firing `mislabel` alongside `border` (measured
  2026-09-03), and whether that is a true positive or cross-talk is not decidable before
  the §6 modes carry a definition and a discriminator. See
  [`failure-mode-taxonomy-handover.md`](failure-mode-taxonomy-handover.md) §4.2. *(Item 140)*
- ✅ Reachability hole closed *with its mechanism named per mode*: mode 8 is
  single-channel-unobservable, mode 1's ladder is FOV-capped, mode 4's cause TBD. Made
  detectable where the mechanism allows, recorded where it does not. Not both silent.
  ⚠️ **Superseded in part, 2026-08-27:** modes 1 and 4 are **one** defect, the interpolating
  spline fit (`splprep(..., s=0)`), and are owned by **Stage 28**. `offset_mm` is zero on
  every committed golden (max `6.8e-04` mm vs a 15.0 mm threshold) and on real VerSe GT
  (mean `2.9e-05` mm), so no field of view produces a non-zero offset and the FOV-headroom
  remedy named here could not have worked. Mode 8 stays this stage's to record. *(Item 138)*
- ⏸️ Per-rule **and per-operator** corpus-exercise reporting (the registered `fuse` operator
  generates no corpus case at all).
  ⚠️ **Deferred, 2026-09-03:** queue-019 was cut short after item 138. The item's spec was
  authored and is preserved at [`items/139-per-rule-and-per-operator.md`](items/139-per-rule-and-per-operator.md),
  including its measurements: the `fuse` claim above holds, 7 of 10 rules are exercised
  across both corpora, and `intensity_reference_delta` is driven by nothing because no
  harness attaches a reference. Its "unexercised, with reason" records need a mode
  specification first. See
  [`failure-mode-taxonomy-handover.md`](failure-mode-taxonomy-handover.md) §9. *(Item 139)*
- ⏸️ The mode-1 severity-ladder base (`tests/test_100_severity_ladder.py`, Stage 18)
  widened so mode 1's metric swing is set by the
  perturbation rather than the fixture's FOV walls — the recorded root cause of mode 6's
  Stage-18 specificity shortfall.
  ⚠️ **Deferred, 2026-09-03:** queue-019 was cut short after item 138. This turns on
  mode-1-vs-mode-6 semantics, which is the discriminator field the §6 modes do not yet
  carry. See
  [`failure-mode-taxonomy-handover.md`](failure-mode-taxonomy-handover.md) §4.1. *(Item 141)*
- ⏸️ Stage 20 end-to-end validation: traceability artifact regenerated from a clean tree,
  the specificity assertion driven over every corpus case, the cross-mode margins
  re-measured, and the end-to-end detection count stated honestly here.
  ⚠️ **Deferred, 2026-09-03:** queue-019 was cut short after item 138. Stating the
  detection count honestly requires a mode↔rule story that is not yet defined. See
  [`failure-mode-taxonomy-handover.md`](failure-mode-taxonomy-handover.md). *(Item 142)*

> **Why those four now read ⏸️ rather than 📋** *(queue-020 boundary,
> 2026-09-03)*. Their prose had said Deferred since 2026-09-03 while their status
> icon still said Planned, so queue-019 stayed derived-open and
> `aide claim --dry-run` offered item 139 — the very item held pending Stage 30's
> sign-off. The icon now agrees with the prose. **Items 139–142 keep their
> numbers**; they are re-specified against Stage 30's specification and return to
> 📋 in the queue that follows item 150's sign-off. Stage 20 itself stays 🚧.
>
> **The flip adds one expected `aide check` warning**: *"stage 20: all
> deliverables ✅ but summary shows in-progress — … close the stage"*.
> `rollup_status` counts ⏸️ as terminal alongside ✅ and ❌, so a stage paused
> mid-flight reads as shipped. **Do not act on that advice** — Stage 20 is not
> complete, and its summary row stays 🚧. Captured as a `framework` insight
> (`insights.md`, queue-020, 2026-09-03) for hand-over to `aide-loop`; it is
> part of the warning baseline from this date, not a new finding for an item to
> chase.

**Acceptance.**

- [x] Every §6 failure mode has ≥1 rule **and** a recorded evidence rung — never silent *(Full suite run 2026-09-02 (.venv/bin/python -m pytest -q): 6900 passed, 60 skipped (all pre-known env-gated), 0 failed; test_ac1_all_ten_rules_declared_and_not_pending passed)* *(Validation round 2, 2026-09-02: .venv/bin/python -m pytest -q -> 7006 passed, 60 skipped (all pre-known env-gated), 0 failed. Verified mode->rule direction directly: json.load(traceability_matrix.generated.json)['directions']['mode_to_rule'] == {complete: True, holes: []}; every one of the 8 mode rows in the generated markdown carries a rung (synthetic-demonstrable x6, structurally-unobservable for mode 8). Covered by test_ac10_mode_to_rule_direction_complete_and_every_mode_has_a_rule, test_ac11_mode_rule_lists_are_derived_from_shipped_declarations, test_ac12_mode_rung_is_member_of_closed_vocabulary, test_ac13_mode8_rung_and_mechanism_name_the_single_channel_mechanism, test_ac14_mode8_not_pipeline_detected_names_reconstructed_case, test_ac15_rung_and_pipeline_detected_cross_check, test_ac16_modes_one_and_four_are_synthetic_demonstrable, test_ac17_mode7_rung_records_its_own_cap (item 138).)*
  - **2026-09-02** → retracted: Retracting an attestation-mapping error: this criterion (every mode has >=1 rule and a recorded evidence rung) requires the mode->rule direction with evidence rungs, which is Item 138's traceability-matrix deliverable (still open, marked pending in this stage's Deliverables); item 137 only disposed the four previously-undeclared rules, it did not build the evidence-rung matrix.
  - **2026-09-03** → Correction (code review): the rung enumeration omitted mode 7's needs-real-data rung from the 8-mode accounting -- it read 8 modes as (synthetic-demonstrable x6, structurally-unobservable for mode 8) = 7 accounted, not 8. Corrected reading: synthetic-demonstrable x6 (modes 1-6), needs-real-data x1 (mode 7), structurally-unobservable x1 (mode 8) = 8. The underlying claim (every mode has >=1 rule and a recorded evidence rung) is unaffected and remains true; only the evidence note's own arithmetic was wrong.
  (**G2**).
- [x] Every registered rule maps to ≥1 §6 mode or is recorded as mode-less with a reason. *(Full suite run 2026-09-02: test_ac2_ac3_analytic_rule_declares_mode_two_only[bounds] passed)*
  - **2026-09-02** → Full suite run 2026-09-02 (.venv/bin/python -m pytest -q): 6900 passed, 0 failed. Combined with item 136's six corpus-derived declarations, item 137 disposes the remaining four rules (bounds, reference_delta -> mode 2 analytic; intensity, intensity_reference_delta -> mode-less with recorded reason), verified by test_ac1_all_ten_rules_declared_and_not_pending, test_ac2_ac3_analytic_rule_declares_mode_two_only[bounds/reference_delta], and test_ac5_mode_less_rule_declares_no_modes_not_pending[intensity/intensity_reference_delta] — every registered rule now maps to >=1 mode or is recorded mode-less with a reason.
- [ ] Every registered rule is exercised by ≥1 case or recorded as unexercised with a *(Full suite run 2026-09-02: test_ac2_ac3_analytic_rule_declares_mode_two_only[reference_delta] passed)*
  - **2026-09-02** → retracted: Retracting an attestation-mapping error: this criterion (every registered rule exercised by >=1 case or recorded unexercised with reason) was mistakenly ticked by positional mismapping to item 137's AC3 test; per-rule corpus-exercise reporting is Item 139's future deliverable, not verified by item 137's tests.
  reason (**G2**).
- [ ] The specificity assertion is enforced for every corpus case. *(Full suite run 2026-09-02: test_ac4_mode_two_declaration_is_analytic_with_named_mechanism passed for both rules)*
  - **2026-09-02** → retracted: Retracting an attestation-mapping error: this criterion (specificity assertion enforced for every corpus case) was mistakenly ticked by positional mismapping to item 137's AC4 test; the specificity assertion is Item 140's future deliverable, not yet built, so this criterion does not hold.
- [ ] The end-to-end detection count is stated honestly here rather than implied (**G7**). *(Full suite run 2026-09-02: test_ac5_mode_less_rule_declares_no_modes_not_pending passed for both rules)*
  - **2026-09-02** → retracted: Retracting an attestation-mapping error: this criterion (end-to-end detection count stated honestly) was mistakenly ticked using item 137's AC5 test as evidence by positional mismapping; that test verifies mode-less declarations, not this stage-level claim, which remains open (Item 142).

> **Not required:** feature→rule completeness. Unwired features are a designed state.

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

---

# Stages scoped 2026-08-11

> Numbered after the placeholders so numbering stays stable; both run earlier than their
> numbers suggest. Full statements in [`roadmap.md`](roadmap.md).

---

## Stage 26 — Carried-Defect Remediation (pre-real-data) (G2, G7) — ✅

**Goal.** Clear the defects Stages 17–19 recorded but were (correctly) forbidden from
fixing in scope, **before** Stage 20 audits those surfaces and before Stage 21 produces
real-data numbers. Every deliverable is a diagnosed defect with a named location — no
discovery.

**Deliverables.**

- ✅ **D1** `normalised_delta` saturates to ±1.0 whenever one run sits on baseline (7 of 8
  metric baselines are `0.0`), so Stage 18's run-vs-run attribution is decided by the
  lowest-mode tie-break rather than by magnitude. `eval/per_mode_cohort.py`. *(Item 109)*
- ✅ **D2** `touches_*` face mapping is anatomically wrong under RAS since item 094
  (`x == 0 → touches_inferior` names the left-right axis) — every `border`/`fov` finding on
  data read through `segfacet.io` is mislabelled. Must land before real data. *(Item 108)*
- ✅ **D3** Golden-fixture test hygiene: `tests/golden/*.json` unpinned in `.gitattributes`
  (latent Windows-CI break); `test_022_stage3_serialisation.py::test_ac8_golden_snapshot`
  writes its own golden and skips when missing, so deleting the file makes it pass.
  *(Item 111)*
- ✅ **D4** `compute_per_mode_metrics` gains an optional `overlap_result=` (halves the
  overlap work of a cohort-scale per-mode run). *(Item 112)*
- ✅ **D5** `test-numpy-majors` scoped off the Docker/PyRadiomics-gated modules. *(Item 113)*
- ✅ **D6** `heuristics/bounds.py` comments still name the retired `S` / `Cocygis` labels.
  *(Item 114)*
- ✅ **D7** Stage 17's acceptance box contradicts its own annotation — maintainer's call
  between untick / reword / third state. *(Item 114)*
- ✅ **D8** `features/neighbourhood.py` is dead wiring: implemented in full, referenced by
  nothing, yet Stage 3 claims it "flags isolated anatomical outliers" ✅. Wire it or retire
  it and correct the claim. Generalised to a named-feature API and wired into
  `extract_feature_record`/`feature_report.py` as `stage3.per_label_neighbourhood[]`
  (status "unwired" — computed and serialised, consumed by no rule); the Stage 3 claim is
  corrected above. *(Item 110)*
- ✅ **D9** The `_PRE_NNN_*` byte-hash scope fences (items 099/100/101/103/105, plus item
  106's `progress.md` row digests) encode a diff-time property as a permanent runtime
  invariant: six documented failures, no recorded true positive, and a re-pin toll on every
  later item that edits source. Retire them and land the deterministic diff-based scope
  check they were reaching for. *(Item 107)*
- ✅ **D10** `synth/` implements a documented array-axis convention (axis 0 = superior-
  inferior) that D2's affine-derived mapping replaces; migrate the synthetic corpus
  RAS-native (bodies along axis 2, truthful affine, load as array-identity) and
  regenerate fixtures, manifest and goldens. *(Item 116)*
- ✅ Stage 26 end-to-end validation: per-defect red-then-green replay, fresh-clone suite
  run, fence-retirement audit, and verification-row closure. *(Item 115)*

**Acceptance.**

- [x] Each defect has a regression test that fails before its fix (**G7**).
  *(Item 115: the pinning test for each of items 107-114/116 is named in a
  table in item 115's Decisions log; red-then-green was directly observed in
  a scratch tree, then reverted, for items 108/109/111 — the three
  cheapest-to-stage defects per the item's Assumptions — and items
  107/110/112/113/114/116 were verified by inspection of their own committed
  tests, per the same Assumptions' documented trade-off.)*
- [x] `border`/`fov` findings carry anatomically correct face names under RAS (**G2**).
  *(Item 115: a real `segfacet run` on `tests/corpus/fixtures/mode6_crop_at_border_seg.nii.gz`
  emitted "Partial vertebra clipped by FOV: label 22 (L3) touches image
  face(s): anterior", matching the perturbation's actual crop face.)*
- [x] Per-mode attribution distinguishes a large move from a small one on a fixture built
  to have both.
  *(Item 115: a real `compare_runs()` call with mode 1 = 0.1 / mode 4 = 0.9
  attributed mode 4; reversing to mode 1 = 0.9 / mode 4 = 0.1 attributed
  mode 1 — attribution followed magnitude both ways, not mode number.)*
- [x] `neighbourhood.py` is reachable from `extract_feature_record` and present in the
  regenerated catalogue, or removed with Stage 3's deliverable reworded.
  *(Item 115: `extract_feature_record` populates `stage3.per_label_neighbourhood`
  and `catalogue.build_catalogue()` lists those entries with `status: "unwired"`,
  confirmed by `tests/test_115_stage26_validation.py`'s AC7 tests, 4/4 passing.)*
- [ ] No `_PRE_NNN_*` byte-hash fence remains, and the diff-based scope check that replaces
  it flags a deliberately out-of-scope edit on a scratch branch (**G7**).
  *(Unticked because one `_PRE_NNN_*`-named byte-hash fence still remains --
  `tests/test_098_stray_components.py`'s `_PRE_098_REFERENCE_VERSE_V1_SHA256`,
  outside this item's authorised paths to retire -- even though the diff-based
  checker's out-of-scope-detection half is independently verified live on a
  scratch branch (AC10). See item 115's Decisions log for the full AC8 audit
  and why this box is left honestly unticked rather than ticked around.)*
  *(2026-09-01, from insights.md's item-128 entry of 2026-08-31: the box's `_PRE_NNN_*`
  naming-pattern wording is no longer a faithful key — item 128 renamed
  `_PRE_098_REFERENCE_VERSE_V1_SHA256` to `_RELEASED_REFERENCE_VERSE_V1_SHA256`, so no
  `_PRE_NNN_*`-shaped name survives in `tests/` while the digest-literal fence itself is
  intact. The box is judged by the mechanism —
  `tests/test_115_stage26_validation.py::test_ac8_no_hardcoded_literal_fence_remains`
  classifies by AST shape and still reports one fence, legitimate because
  `reference_verse_v1.json` is not regenerable in CI and its digest is the only guard — and
  stays unticked on that reading, not on the name.)*

---

## Stage 27 — Feature Schema Taxonomy & Coordinate System (G8) — 📋

**Goal.** Give the feature record a deliberately designed structure instead of the current
grouping by *which extractor module happened to compute a field* — the single recurring
theme behind roughly two-thirds of item 106's 111-entry steering review verdicts. **This
stage designs the taxonomy rather than inheriting one**: the maintainer's scope × kind
framing is the starting proposal and the quality bar, and deviation is allowed where it is
justified in writing.

**Deliverables.**

- 📋 The taxonomy, written down with rationale, alternatives considered, and every deviation
  from the starting proposal justified — reviewed with the maintainer before migration (a
  human-checkpoint stage in the same sense Stage 19 was).
- 📋 The migration applied, the feature catalogue
  (`docs/aide/feature_catalogue.generated.md`) regenerated, its drift test
  (`tests/test_104_feature_catalogue_drift.py`) as the safety net.
- 📋 Answers for the known instances: duplicated `label`/`level_name` identity fields across
  four containers; `stage3.*` / `image_features.*` parallel to `per_label.{label}.*`;
  image-axis-relative shape features (bbox/extent, `principal_axis`) awaiting a vertebra
  coordinate system; reference-delta hardcoded to `physical_volume_mm3`.

**Acceptance.**

- [ ] The taxonomy is documented with its rationale and every deviation justified, and is
  signed off by the maintainer before migration (**G8**).
- [ ] Every feature is addressable under it; no identity field is stored more than once.
- [ ] The regenerated catalogue and the drift test agree; no rule's behaviour changes on the
  corpus except where a retune is explicitly authorised.

---

## Stage 28 — Spinal Curve Model: Formulation, Offset & Orientation (G2, G7) — ✅

**Goal.** `features/spline.py` fits an **interpolating** spline (`splprep(..., s=0)`), so
the curve passes exactly through every centroid it is meant to judge. Measured 2026-08-27:
`stage3.per_label_offsets[].offset_mm` is zero on all nine committed goldens (max
`6.8e-04` mm against `mislabel`'s `max_offset_mm = 15.0`) **and** on real VerSe19 GT
(`reference_verse_v1.json`: mean `2.9e-05` mm, CoV 1.3), and
`stage3.monotonic_consistency.is_monotonic` is `True` on every case including
`mode4_relabel_swap`. Eight leaf paths are affected — `offset_mm`, `offset_voxel`,
`dx/dy/dz_mm`, and all three `per_label_neighbourhood[].stats.offset_mm.*`, so item 110's
wiring aggregates zeros. `MislabelRule` cannot fire through `run_qc` on any input.

**Modes 1 and 4 are one defect.** Stage 20 records them as separate reachability holes with
an FOV-headroom remedy for mode 1; no field of view yields a non-zero offset while `s=0`
holds, and a smoothed fit detects the mode-4 swap directly. That part of Stage 20 is
superseded here.

**The deliberation is the first deliverable, not a preamble.** The model must be flexible
enough for real spinal shape (sagittal S; a coronal curve under scoliosis) yet too stiff to
follow a segmentation error — and a curve fit *from* the centroids then used to judge one is
circular unless something breaks the circle. That is a modelling decision with a clinical
prior, so it is recorded and gated before any calculation changes.

**Deliverables.**

- ✅ **D1** The spline formulation decision, recorded before implementation: family,
  degrees of freedom and how they scale with the number of levels present, arc-length vs
  cranio-caudal parameterisation (the latter is monotonic by construction and would destroy
  the mode-4 signal), how circularity is broken, and the deformity envelope a scoliotic
  spine must express without being flagged. Judged against measurable criteria on real GT.
  **Raises a human gate.** *(Item 118)*
- ✅ **D2** The formulation implemented, replacing `s=0`, with its smoothing/DoF parameter
  in a scale-free form (`splprep`'s `s` is an absolute mm² residual bound and cannot be a
  literal constant across level counts or spacings). *(Item 119)*
- ✅ **D3** Per-vertebra offset that separates, including the per-direction components
  (`dx/dy/dz_mm`) that are computed and catalogued but read by no rule. A leave-one-out fit
  tracks displacement ~1:1 (measured 5 → 6.2, 10 → 10.4, 15 → 16.0 mm) and already exists as
  `_recon_leave_one_out_offset` inside the test harness; promoting it retires mode 1's
  `reconstructed_record` workaround. *(Item 120)*
- ✅ **D4** Tangent-based vertebra orientation. PCA's `principal_axis` is `(1, 0, 0)` for
  every vertebra of the default fixture — a box's widest side, left-right on real anatomy
  too. `closest_u` and `splev(..., der=1)` both exist but are never joined. Retain
  `eigenvalue_ratio` (real-GT CoV 0.155); demote `principal_axis`. *(Item 121)*
- ✅ **D5** Signed curvature: `total_curvature_deg` is `max − min` of an *unsigned* angle,
  reporting 5.702° where the true tangent sweep is 11.4° — it halves a C-curve and cancels
  the symmetric S a normal spine has. *(Item 122)*
- ✅ **D6** Recalibration and regeneration: `max_offset_mm`, the nine goldens,
  `reference_default.json`, `reference_verse_v1.json`. The VerSe19 cohort is available
  locally (80 CT/GT pairs, gitignored symlink at the documented root), so the real artifact
  is rebuildable; `dataset-verse19.md`'s documented nested layout needs correcting to match.
  *(Item 123)*
- ✅ **D7** An observed-range column in the generated feature catalogue — the check that
  would have caught this at item 018. The catalogue is current and its `computation` column
  accurate, but nothing records what a feature *does*: `offset_mm` reads healthy and its
  `status` is `retune`, shared with 65 of 128 rows. *(Item 124)*
- ✅ Stage 28 end-to-end validation: gate-before-implementation check, red-then-green replay
  of modes 1 and 4 through `segfacet run`, a real scoliotic case not flagged, honest
  before/after detection count, and a fresh-clone byte-reproducibility run. *(Item 125)*

**Scope fence.** Bounded to the spline layer. A sweep of every numeric leaf path found no
other degenerate feature — the real-GT reference's 21 features all carry genuine spread
(CoV 0.06–3.6) except `spline_offset_mm`. The 153 paths constant across the goldens are
constant because all nine fixtures are one box from one base (Stage 21's premise), and the
corpus alone cannot separate that from a broken feature. Do not widen on that evidence.

**Acceptance.**

- [x] The formulation decision is recorded with its measurements and signed off at its human
  gate before D2 lands (**G8**). *(Item 125's 2026-08-30 replay: the gate row above reads
  ✅ Approved (2026-08-27) at commit 82d4b7f (17:36 local); item 119's first implementation
  commit (4947d59, "feat(119): implement the smoothing-spline curve formulation") is dated
  the same day at 19:53, after the approval — ordering held. Re-running
  `scripts/compare_curve_candidates.py --verse-cohort dataset-verse19training` reproduced
  15 of the 16 documented `docs/spinal-curve-model.md` measurements within the stated
  0.001 mm tolerance (10 non-VerSe rows exactly, 4 of 5 VerSe rows); one VerSe leave-one-out
  figure diverged by 0.39 mm — logged to insights.md rather than treated as a reproduction
  of every quoted number.)*
- [x] A clean GT spine stays within a **1.0 mm** pass-through bound across level counts
  and spacings, while a displaced vertebra separates by a stated margin (**G2**).
  *(Raised from 0.5 mm on 2026-08-28. The original line reused item 017's AC1 — a unit
  tolerance on that item's own fixtures — across a far wider sweep, which the approved
  smoothing formulation does not satisfy: `0.19198` mm on item 017's fixtures versus
  `0.552139` mm at the sweep's worst grid point. Rationale in `roadmap.md`'s Stage 28
  acceptance note. Item 017's AC1 is unchanged. Item 125's 2026-08-30 replay: re-measured peak is
  `0.552139` mm at level count 5, spacing (0.8, 0.8, 1.0) mm, level L3 — comfortably under
  the 1.0 mm bound; `mode1_displace`'s max offset (`18.7186` mm) separates from
  `clean_control`'s (`0.6733` mm) by an ~18 mm margin, both clear of the shipped `13.0` mm
  threshold on opposite sides.)*
- [x] `mislabel` fires through plain `run_qc` on the mode-1 case and `is_monotonic` is
  `False` on the mode-4 case, with the clean control still firing nothing (**G2**).
  *(Item 125's 2026-08-30 replay established the `mislabel`/clean-control halves: `mislabel`
  fires on `mode1_displace` naming label 22 (L3) both through plain `run_qc` and through a
  real `segfacet run --no-reference` CLI invocation, and `clean_control` fires nothing
  through either path. Item 132 changed `consistency.py` to judge monotonicity against the
  smoothed, traversal-ordered reference fit rather than the in-sample fit alone, moving
  `mode4_relabel_swap` from `detection="reconstructed_record"` to `detection="pipeline"` in
  `tests/corpus/manifest.json`. Item 135's 2026-08-31 replay closes this box on that change:
  `mode4_relabel_swap` reads `is_monotonic == False` with
  `non_monotonic_pairs == [["L2", "L3"]]` through both `extract_feature_record` and a real
  `segfacet run --no-reference` CLI invocation (which also emits a `mislabel` finding
  naming labels 21/22), and `clean_control` still reads `is_monotonic == True` with empty
  `non_monotonic_pairs` and fires zero findings through both paths.)*
- [ ] A real scoliotic curve in the VerSe cohort is not flagged as an offset outlier
  (**G3**). *(Unticked — item 125's 2026-08-30 replay: of the 17 real VerSe19 subjects the decision
  document's scoliosis-selection rule selects (`coronal_deviation_mm >= 8.0` mm, 17 of 80
  discovered — reproduced), 1 fires a genuine `mislabel` finding through the shipped
  `run_qc` with `bundled_default_config()`: `sub-verse406_split-verse261`, label 17 (T10),
  `offset_mm = 18.51028` mm against the shipped `13.0` mm threshold — the same
  subject/level item 123 already identified as the value that calibrated that threshold.
  Logged to insights.md; not remediated here.)*
- [x] Both reference artifacts are rebuilt from real GT and `spline_offset_mm` shows real
  spread; every regenerated golden is byte-reproducible run-to-run (**G7**). *(Item 125's
  2026-08-30 replay: `reference_verse_v1.json`'s `subject_count` is `80` and every level's
  `spline_offset_mm` mean clears a 1e-3 mm non-degeneracy floor by 2-3 orders of magnitude
  (e.g. `T10` mean `1.505` mm, max `18.510` mm); `reference_default.json` likewise shows
  real spread. Two successive in-session regenerations of all nine corpus goldens and
  `tests/golden/022_stage3_report.json` are byte-identical to each other and to the
  committed files.)*

## Stage 29 — Golden Retirement & Test-Artifact Hygiene (G2, G7) — ✅

**Goal.** Execute the maintainer-signed retirement of the 11 whole-record snapshot goldens
(`golden-decision-table.md`, dispositioned *retire* 2026-07-28, execution pulled forward
from Stages 21/27), make committed-artifact comparisons reach for numeric tolerance by
construction, and sweep the located defects the queue-017 triage routed to
[`roadmap.md`](roadmap.md)'s Stage 29 — see there for the full deliverable list and
per-deliverable provenance.

**Deliverables.**

- ✅ **D1** The golden retirement executed: nine `tests/corpus/golden/*.json` and two
  `tests/golden/` snapshots gone, the four per-row replacements in place, nothing
  regenerated on the way out. *(Item 126)*
- ✅ **D2** Tolerance by construction: shared committed-artifact comparison helper plus an
  enforcing guard extending `tests/test_111_golden_guard.py`'s byte-exact allowlist.
  *(Item 127)*
- ✅ **D3** The `reference_verse_v1` integrity pin relocated to a test named for the
  artifact (its `.gitattributes` pin carried across) and the `test_102` fence header
  renamed to say what it checks. *(Item 128)*
- ✅ **D4 + D5** Coincident centroids degrade to a report instead of a traceback at the
  pipeline level (the fit's descriptive error already exists — item 119 AC16), and the
  4-centroid held-out fallback boundary moves to `< 5` with the affected reference
  distributions rebuilt. *(Item 129)*
- ✅ **D6** Spline plumbing consolidation: one closest-point search, one in-sample fit per
  case. *(Item 130)*
- ✅ **D7** `tangent_angles_deg[]` traversal-direction normalisation to item 122's
  convention. *(Item 131)*
- ✅ **D8** `consistency.py` monotonicity judged against the smoothed fit so mode 4 fires.
  *(Item 132)*
- ✅ **D9 + D10** The `tptbox` ≥ 0.7.6 pin (non-AGPL metadata), and
  `refresh_reference.py --verse-cohort` delegated to `rebuild_verse_reference.py` or
  retired. *(Item 133)*
- ✅ **D11** The decision table's live `N/M leaf paths unwired` counts split into a
  generated, byte-reproducible companion the signed document references. *(Item 134)*
- ✅ Stage 29 end-to-end validation: retirement audit, guard replay on a scratch branch,
  mode-4 replay closing Stage 28's unticked acceptance half, fails-before-the-fix
  verification per defect, fresh-clone suite. *(Item 135)*

**Acceptance.**

- [x] All 11 retired snapshots are gone with their named replacements in place, and no
  snapshot was regenerated on the way out; the guard fails a deliberately added byte-exact
  comparison against a committed float-carrying artifact (**G7**). *(Item 135's 2026-08-31
  replay: all eleven paths — nine `tests/corpus/golden/{clean_control,mode1_displace,
  mode2_fragment,mode3_inject_islands,mode4_relabel_swap,mode5_remove_level,
  mode6_crop_at_border,mode7_sequence_break,mode8_force_overlap}.json` plus
  `tests/golden/016_features_report.json` and `tests/golden/022_stage3_report.json` — are
  absent from the tree, and `git log --follow --name-status` over `69e5cf5..HEAD` shows
  each path's most recent history entry is a single `D` at commit `cafd4cc`, with no later
  `A`/`M`. The four named replacements resolve to live code: intra-run determinism in
  `test_042`/`test_098`/`test_016`/`test_022` (none reads a `tests/corpus/golden` path);
  `test_126_golden_retirement.py::test_ac3_fresh_report_validates_against_schema`;
  `test_098_stray_components.py::test_ac15_golden_verdict_and_findings_unchanged`; and the
  shared `tests/golden/report_format_contract.json` built by `tests/report_format_fixture.py`,
  the sole survivor under `tests/golden/`. On a scratch branch in a throwaway clone,
  deleting that fixture made `test_016_features_json.py::test_ac5_golden_snapshot` fail
  with a `FileNotFoundError` naming the missing file rather than self-healing; on the same
  scratch branch, adding a real `dest.read_bytes() == Path("src/segfacet/reference/
  reference_default.json").read_bytes()` comparison under `tests/` made
  `test_127_committed_artifact_tolerance.py::test_ac15_classifier_reports_zero_violations_on_tests_tree`
  fail, its message naming `assert_matches_committed_artifact`; the scratch branch was
  discarded afterward and the working checkout was never touched. Committed whole-record
  snapshot inventory: 11 → 0, with one shared, feature-value-free format fixture surviving
  under `tests/golden/`.)*
- [x] `mode4_relabel_swap` yields `is_monotonic == False` through `extract_feature_record`,
  closing Stage 28's unticked mode-4 acceptance half (**G2**). *(Item 135's 2026-08-31
  replay: `extract_feature_record` on the committed `mode4_relabel_swap` fixture reads
  `stage3.monotonic_consistency.is_monotonic == False` with
  `non_monotonic_pairs == [["L2", "L3"]]`; a real `segfacet run --scan
  tests/corpus/fixtures/base_scan.nii.gz --seg
  tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz --out <scratch> --no-reference` exits
  `0` and its `segfacet_report.json` carries the same reading plus a `mislabel` finding
  naming labels 21/22. `clean_control` reads `is_monotonic == True` with empty
  `non_monotonic_pairs` and fires zero findings through both paths, so the tick is not
  bought at the clean control's expense. `tests/corpus/manifest.json`'s pipeline-detected
  mode count is now **7 of 8** (mode 4 moved in at item 132; mode 8 remains
  `reconstructed_record`), agreeing with `test_040`'s and `test_057`'s mode-set constants —
  up from 6 of 8 at Stage 28's close.)*
- [ ] A 4-level field of view yields non-degenerate held-out offsets; `pip show tptbox`
  reports a non-AGPL licence; each fixed defect carries a regression test that fails
  before the fix (**G7**). *(Unticked — item 135's 2026-08-31 replay: the `pip show tptbox`
  clause and the fails-before-the-fix clause are both **verified**, and this box is
  unticked **solely** on the four-level clause below, not on either of those two. `pip show
  tptbox` in the project venv reports `Version: 0.7.6` and `License: Apache License Version
  2.0, January 2004` (neither `agpl` nor `affero`), matching both `pyproject.toml`'s and
  `constraints.txt`'s `tptbox==0.7.6` pins. In a throwaway clone, all eight designated
  regression-test nodes for items 129/131/132/133 fail at each implementation commit's
  immediate parent (`1466b8b`←`021f0bc`, `8b94e62`←`5efd27d`, `628f673`←`cc22bfd`,
  `26b5cf5`←`8586772`) — confirmed by execution, not assumed. The four-level clause itself
  is re-measured and remains **unmeetable**: a synthetic 4-level curve with an interior
  level displaced 15 mm reproduces item 129's exact degenerate array `[7.348609152784843e-05,
  5.330684370393181e-06, 5.740531122353952e-06, 3.782179445898854e-05]` mm (all `< 0.001`
  mm), while the same displacement at 5 and 6 levels separates well above that floor — at
  exactly four points a cubic (`k = 3`) spline has exactly four coefficients and
  interpolates all four points regardless of weights, so the "held-out" curve is
  numerically the in-sample curve. Closing this needs the fit's degree clamped below
  `n − 1` at small `n`, which changes the formulation the 2026-08-27 "Spinal curve model —
  the deformity envelope" human gate approved (`✅ Approved`, blocking nothing today); see
  `docs/aide/items/129-coincident-centroids-in-the-pipeline.md`'s Decisions log and
  `src/segfacet/features/spline_offset.py`'s docstring limitation block for the standing
  evidence. No agent resolves that gate.)*

---

# Stage scoped 2026-09-03 (queue-019 boundary feedback loop)

> Same construction as Stages 26–29: numbered for stability, **runs next, ahead of the
> remainder of Stage 20**. Full statement in [`roadmap.md`](roadmap.md).

---

## Stage 30 — Failure-Mode Specification: the §6 catalogue as an authored source (G2, G7, G8) — 🚧

**Goal.** Queue-019 produced three defects of one class in four items — a factual claim
about the failure modes authored as prose, shipped into a committed artifact, and accepted
by a check that tested the claim's shape rather than its truth — because no document
defines the modes: they exist as five partial sources (`vision.md` §6's list,
`FAILURE_MODE_NAMES`, `MODE_ANCHOR_PATHS`, the `Expectation` literals, `MODE_RUNGS`) that
the generated matrix cross-checks without being able to adjudicate. This stage authors the
specification [`vision.md`](vision.md) v3 §6 describes — one authored source per mode,
from which every generated artifact becomes a conformance report — collapses the five
sources onto it, and closes with a maintainer sign-off that gates the remainder of Stage
20. It writes no new rules and adds no corpus cases beyond what the ninth mode needs.

**Deliverables.**

- 🔍 **D0** Synthetic corpus S-axis stacking corrected before anything is measured
  (`build_clean_spine` advances caudally like real VerSe input), every committed corpus
  value and both reference artifacts regenerated, expected firing sets recorded only
  after it. Carried defect recorded 2026-08-31 (spec 131). *(Item 143)*
- 📋 **D1** The specification module (one frozen declaration per mode with vision §6's
  fields; `implemented`/`validated` derived, `proposed`/`specified` authored) and its
  byte-reproducible, LF-pinned rendering `docs/aide/failure_modes.generated.{md,json}`.
  *(Item 144)*
- 📋 **D2** The eight hypothesised modes specified with discriminators; gate 3's decisions
  encoded as data — `mode6_crop_at_border` expects `{border, mislabel}` with reason,
  evidence rungs authored per mode ↔ rule edge with the mode's rung derived, mode 8
  structurally-unobservable, mode 7's single-descent cap recorded. *(Item 145)*
- 📋 **D3** The ninth mode, implausible tissue under a label, entered through the lifecycle
  (`intensity` / `intensity_reference_delta` declare it; the intensity manifest gains
  `failure_mode` and expected firing fields; the intensity sibling of
  `pipeline_findings` built in `synth/regression.py`), plus the catalogue's first
  `proposed` entry — collapsed or duplicated label set, candidate feature
  `stage3_unavailable`, no rule (carried defect, spec 129). *(Item 146)*
- 📋 **D4** The five partial sources collapsed onto the specification; `Expectation` and
  `RuleModeDeclaration` checked against it in both directions; the three declaration-seam
  defects (the `"corpus"` tag membership test, the untyped `evidence`/`modes`, the
  corpus-to-declaration blindness; `insights.md`, spec 136) closed by replacement, and
  the rule-granular attribution (`insights.md`, spec 138) given a per-detector or
  per-path form the catalogue renders. *(Items 147, 148)*
- 📋 **D5** The traceability `build_matrix` (spec 138) re-pointed at the specification as primary: derived
  status, per-edge rungs, expected beside measured firing per corpus case with agreement
  scored, metric anchor path and rule read paths as two labelled columns; the
  `build_matrix` fixture discipline set and the `no-float-leaf` guard ground added. The
  exercise columns stay Stage 20's. *(Item 149)*
- 📋 **D6** Maintainer sign-off of `failure_modes.generated.md`, entry by entry, with date
  and outcome recorded in the specification module's docstring. Until recorded, the
  remainder of Stage 20 is not queued. *(Item 150)*
- 📋 **D7** Stage validation: both artifacts regenerated from a clean tree, every corpus
  case across both corpora driven and expected equals measured confirmed, derived
  statuses checked against live state, the per-status / per-rung count recorded here as a
  measured number. *(Item 151)*

**Acceptance.**

- [ ] Every mode in the specification carries every schema field, a status from the
  four-state vocabulary and a provenance; `implemented` and `validated` are derived from
  live state, and a hand-set status that disagrees with the registry or the corpus fails
  a test naming the mode (**G8**).
- [ ] For every corpus case across both committed corpora, the measured firing set equals
  the specification's expected firing set, and `mode6_crop_at_border` expects
  `{border, mislabel}` with a recorded reason (**G2**).
- [ ] Every mode ↔ rule edge carries an authored evidence rung and every mode's rung is
  derived from its edges; the analytic-only edges are rendered as such, and mode 8's rung
  names the single-channel mechanism (**G2**).
- [ ] `failure_modes.generated.{md,json}` and the traceability matrix regenerate
  byte-identically from a clean tree, name the specification as their primary source, and
  render the metric anchor path and the rule's read paths as separately labelled columns.
- [ ] The ninth mode (implausible tissue) is present at `implemented` or `validated`, with
  `intensity` and `intensity_reference_delta` declaring it and the intensity corpus cases
  carrying expected firing sets; `FAILURE_MODE_NAMES` and `MODE_RUNGS` are derived from or
  replaced by the specification, and the eight seed names equal `vision.md` §6's list
  (**G8**).
- [ ] The specification's rendering is signed off by the maintainer, with the date and
  outcome recorded in the module (**G8**).
- [ ] `build_clean_spine` stacks labels caudally along +S like real VerSe input, every
  committed corpus value and both reference artifacts were regenerated after the
  correction, and no expected firing set in the specification predates it (**G7**).
