# Item 053 — Evaluation cohort model & harness driver

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (Phase 1 complete)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 053
> **Objectives:** G3 (distinguish failure from variation), G7 (evaluable & regression-testable)
> **Suggested branch:** `aide/053-evaluation-cohort-model-harness-driver`

---

## Description

Tie the three now-merged Stage-7 comparison primitives together into the
**evaluation harness**. This item defines a **cohort model** — a labelled set of
evaluation cases — and a **driver** that, per case, runs the real `segqc`
pipeline and assembles the three §8 comparison levels into one serialisable
**per-case evaluation record**.

Concretely, add `src/segqc/eval/harness.py` exposing:

- **`EvaluationCase`** — the per-case *input* spec: a `case_id`, a **ground-truth
  (GT)** segmentation source, an **optional candidate** segmentation source (a
  segmenter output to score against GT), a **ground-truth expectation** mapping
  (in the `Expectation.to_dict()` / `tests/corpus` manifest-case shape consumed by
  item 052), and optional `spacing` / `metadata`.
- **`CaseEvaluation`** — the per-case *output* record: the verdict-outcome
  (`CaseOutcome`, item 052, always populated), the DICE-vs-GT `OverlapResult`
  (item 050, populated only when a candidate is present), the feature-set
  `FeatureMatchResult` (item 051, populated only when a candidate is present),
  availability flags, and a deterministic `to_dict()`.
- **`CohortEvaluation`** — the collection of `CaseEvaluation` records plus a
  deterministic `to_dict()`.
- **`evaluate_case(case, config, *, positive_severity=Severity.FLAG)`** — drive
  one case.
- **`evaluate_cohort(cases, config, *, positive_severity=Severity.FLAG)`** — drive
  many.

**Subject under QC.** Each case's *segmentation-under-QC* is the **candidate when
present, otherwise the GT**. The clean-GT positive control therefore has no
candidate (QC runs on the GT itself, expected `pass`); a failure case carries the
candidate as the thing being scored and the GT as the reference (DICE / feature
divergence are computed candidate-vs-GT).

The cohort abstraction is **source-agnostic**: it consumes any conforming
`(GT, optional candidate, expectation)` triple, so it works for VerSe GT
(positive control), TotalSegmentator-vs-GT pairs, and the Stage-5 synthetic
corpus. Per the queue's local-testability note it is **tested locally against a
synthetic cohort** assembled from the Stage-5 generator (clean-GT control +
perturbed corpus cases, with the perturbed labelmap as candidate and its clean
base spine as GT), requiring **no VerSe/TotalSegmentator download**.

**What this item is NOT.** No metric interpretation or cross-case aggregation
(FPR / per-mode sensitivity / DICE-vs-flag correlation) — that is item 054. No
threshold calibration (055), no evaluation report (056), and no `segqc evaluate`
CLI / entry point (057). The driver only produces **stable per-case records**. It
does not re-implement any comparison maths — it calls the merged primitives
(050/051/052) and the merged pipeline (`run_qc`, item 035/049) unchanged. It does
not use the Stage-5 test-only *reconstruction* machinery (`segqc.synth.regression`):
the harness runs the **plain** pipeline, exactly as an external cohort would.

## Acceptance Criteria

- [ ] **AC1: Module & public API.** `segqc.eval.harness` exists and exports
  `EvaluationCase`, `CaseEvaluation`, `CohortEvaluation`, `evaluate_case`, and
  `evaluate_cohort`; each is also re-exported from `segqc.eval` (added to
  `segqc/eval/__init__.py`'s imports and `__all__`).

- [ ] **AC2: EvaluationCase model.** `EvaluationCase` constructs with a required
  `case_id: str`, a required `gt` seg source, an optional `candidate` seg source
  (default `None`), a required `expected` mapping, and optional `spacing` /
  `metadata` (default `None`); it is a frozen dataclass and does not mutate the
  arguments passed in.

- [ ] **AC3: Seg-source resolution.** A case whose `gt` (and/or `candidate`) is
  given as an in-memory `nibabel.Nifti1Image`, and one given as a NumPy
  `ndarray`, both resolve to a usable segmentation and yield a well-formed
  `CaseEvaluation` (arrays are wrapped with an affine derived from the case's
  `spacing`, defaulting to isotropic `(1.0, 1.0, 1.0)`).

- [ ] **AC4: Outcome always populated.** `evaluate_case(case, config)` returns a
  `CaseEvaluation` whose `outcome` equals
  `classify_outcome(case.expected, run_qc(subject, config)[0], positive_severity=...)`
  where `subject` is the resolved subject-under-QC image — i.e. the level-1
  verdict comparison is present for **every** case, candidate or not.

- [ ] **AC5: Subject-under-QC selection.** The pipeline verdict is produced by
  running `run_qc` on the **candidate** when a candidate is present, and on the
  **GT** when it is absent. (Observable via a case whose candidate and GT would
  give different verdicts: the recorded `outcome.actual_verdict` matches the
  candidate's.)

- [ ] **AC6: Overlap populated & correct with a candidate.** When `case.candidate`
  is present, `CaseEvaluation.overlap` is an `OverlapResult` equal to
  `compute_overlap(candidate_array, gt_array, gt_spacing)`, where `gt_spacing` is
  taken from the resolved GT image's voxel zooms.

- [ ] **AC7: Feature-match populated & correct with a candidate.** When
  `case.candidate` is present, `CaseEvaluation.feature_match` is a
  `FeatureMatchResult` equal to
  `compute_feature_match(candidate_features_block, extract_feature_record(gt, config))`,
  where `candidate_features_block` is the block already returned by the
  candidate's `run_qc` call (reused, not recomputed).

- [ ] **AC8: Missing candidate ⇒ unavailable, not errored.** When
  `case.candidate is None`, `CaseEvaluation.overlap is None`,
  `feature_match is None`, `candidate_present is False`, `outcome` is still
  populated, and no exception is raised.

- [ ] **AC9: One record per case, order preserved.** `evaluate_cohort(cases, config)`
  returns a `CohortEvaluation` whose records number exactly `len(cases)`, one per
  input case, in the same order, each carrying its case's `case_id`.

- [ ] **AC10: Perturbed candidate is distinguishable.** For a pipeline-detectable
  perturbed synthetic case (candidate = perturbed seg, GT = its clean base spine,
  expected = a flag/fail), the record's `outcome` is a positive
  (`TRUE_POSITIVE`/`FALSE_NEGATIVE` per actual firing) with
  `outcome.expected_failure is True`, and `overlap.mean_dice < 1.0`.

- [ ] **AC11: Identical candidate scores perfect DICE & passes.** For a case whose
  candidate array equals its GT array with a clean (`expected_verdict == "pass"`)
  expectation, `overlap.mean_dice == 1.0` and `outcome.outcome` is
  `Outcome.TRUE_NEGATIVE`.

- [ ] **AC12: Deterministic serialisation.** `CaseEvaluation.to_dict()` and
  `CohortEvaluation.to_dict()` return JSON-serialisable nested dicts (the
  `Outcome` enum reduced to its string value; the primitives' dataclasses reduced
  to plain dicts) that include the outcome, overlap, and feature-match content;
  and `json.dumps(cohort.to_dict(), sort_keys=True)` is **byte-identical** across
  two independent `evaluate_cohort` runs on the same cohort.

- [ ] **AC13: Non-mutation.** `evaluate_case` / `evaluate_cohort` do not mutate the
  `EvaluationCase`, the `config`, or the supplied GT/candidate images or arrays
  (verified by equality of the inputs before and after).

- [ ] **AC14: Shape-mismatch raises clearly.** A case whose candidate and GT
  arrays have different shapes raises `segqc.io.SegQCInputError` (propagated from
  `compute_overlap`) rather than producing a malformed record.

- [ ] **AC15: Empty cohort.** `evaluate_cohort([], config)` returns a
  `CohortEvaluation` with zero records and does not raise.

- [ ] **AC16: Duplicate case ids rejected.** `evaluate_cohort` over two cases that
  share a `case_id` raises `segqc.io.SegQCInputError` (so downstream item 054 can
  safely key records by `case_id`).

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume`; the queued one-liner left the record/model shape and
input conventions open. Defensible defaults taken (each is a hand-back point for
the builder/validator if a merged interface diverged from what is pinned here):

- **Subject-under-QC = candidate-if-present-else-GT.** The queue says the driver
  "runs the full `segqc run` pipeline per case" and computes DICE/features "vs GT
  … when a candidate is present". The most defensible reading is that the QC
  verdict is about the segmentation being scored: the candidate when there is one
  (a segmenter output whose quality we assess), the GT otherwise (the clean
  positive control). AC5/AC11 pin this.
- **Plain `run_qc` (item 035), not `run_qc_with_reference`.** Reference-delta
  evaluation (item 049's `run_qc_with_reference`) is out of scope for 053; the
  harness calls `run_qc(seg_img, config)` and takes `(CaseResult, features_block)`.
  A reference-aware harness path is a possible future extension (noted for 055/057),
  not required here.
- **Merged primitive signatures (pinned):** `compute_overlap(candidate, gt,
  spacing=(1,1,1), *, convention=None) -> OverlapResult`;
  `compute_feature_match(candidate, gt) -> FeatureMatchResult` (both args are
  `features` block dicts as returned by `extract_feature_record`);
  `classify_outcome(expected, actual, *, positive_severity=Severity.FLAG) ->
  CaseOutcome` (`expected` = mapping with `expected_verdict` required;
  `actual` = a `CaseResult`). These are the item 050/051/052 APIs read from the
  merged modules; the harness treats them as fixed.
- **`spacing` for overlap comes from the GT image** (`header.get_zooms()[:3]`),
  matching item 050's GT-referenced `physical_volume_mm3` weighting. The
  candidate is assumed co-registered / same grid as the GT (DICE is voxel-wise);
  a shape mismatch is a cohort-construction error and fails loud (AC14).
- **Feature divergence uses candidate-vs-GT feature blocks with the same
  `config`.** The candidate block is reused from its `run_qc` call; the GT block
  is `extract_feature_record(gt, config)`. When there is no candidate, feature
  divergence is *unavailable* (not a trivial self-comparison) so `overlap` and
  `feature_match` share the same "candidate required" semantics (AC8).
- **Seg-source resolution accepts `Nifti1Image`, `ndarray`, and a path.**
  In-memory images/arrays are the tested path (the synthetic corpus produces
  `Nifti1Image`s in memory, no disk needed). A path-like source is accepted for
  external cohorts (VerSe / TotalSegmentator) by loading a single seg NIfTI
  (integer labels preserved, mirroring the Stage-0 loader convention); the
  external-dataset path is documented but not exercised by committed tests, per
  the queue's local-testability note. `ndarray` sources get a diagonal affine
  from `spacing` (default isotropic).
- **`evaluate_case` fails loud on input errors; `evaluate_cohort` does not
  swallow them.** A malformed case (shape mismatch, bad expected mapping) raises
  rather than being recorded as a degraded record — consistent with the codebase's
  `SegQCInputError` philosophy. Only the *absence of a candidate* is a normal
  recorded condition (AC8).
- **`case_id`s are required unique within a cohort** (AC16) so item 054 can key
  the records; duplicates raise.

## Implementation Steps

Intended code path in `src/segqc` (see `aide.toml`):

1. **New module `src/segqc/eval/harness.py`.** Module docstring stating it is the
   §8 harness that assembles the level-1/2/3 primitives per case, produces stable
   records only, and does no aggregation/calibration/reporting.
2. **`EvaluationCase`** frozen dataclass: `case_id: str`, `gt`,
   `candidate=None`, `expected: Mapping`, `spacing: Optional[tuple]=None`,
   `metadata: Optional[Mapping]=None`. (A seg source is `Nifti1Image | ndarray |
   os.PathLike | str`.)
3. **Seg-source resolver** `_resolve_seg(source, spacing) -> nib.Nifti1Image`:
   pass an `Nifti1Image` through; wrap an `ndarray` with a diagonal affine from
   `spacing` (default `(1,1,1)`), mirroring `segqc.synth.regression.loaded_seg_image`'s
   `Nifti1Image(data, affine, dtype=…)` int-safe rebuild; for a path, load the
   seg NIfTI (integer labels, per the Stage-0 loader convention). Never mutate the
   source.
4. **`CaseEvaluation`** frozen dataclass: `case_id: str`,
   `outcome: CaseOutcome`, `overlap: Optional[OverlapResult]`,
   `feature_match: Optional[FeatureMatchResult]`, `candidate_present: bool`,
   `subject: str` (`"candidate"`/`"gt"`), `metadata`. Add `to_dict()` reducing the
   `Outcome` enum to `.value`/`.label`, and the primitive dataclasses to nested
   dicts (`dataclasses.asdict`, with enum handling), `None` for unavailable
   fields.
5. **`CohortEvaluation`** frozen dataclass: `cases: Tuple[CaseEvaluation, ...]`
   (+ convenience `n_cases`), with `to_dict()` → `{"cases": [c.to_dict() …]}`.
6. **`evaluate_case(case, config, *, positive_severity=Severity.FLAG)`:**
   resolve GT and (if present) candidate; pick `subject = candidate or gt`; call
   `case_result, subject_block = run_qc(subject, config)`; `outcome =
   classify_outcome(case.expected, case_result, positive_severity=…)`; if a
   candidate is present, `overlap = compute_overlap(cand_arr, gt_arr, gt_spacing)`
   and `feature_match = compute_feature_match(subject_block,
   extract_feature_record(gt, config))`; else both `None`. Assemble and return the
   `CaseEvaluation`.
7. **`evaluate_cohort(cases, config, *, positive_severity=Severity.FLAG)`:**
   validate unique `case_id`s (raise `SegQCInputError` on a duplicate); map
   `evaluate_case` over the input order; return `CohortEvaluation`. Empty input →
   empty cohort.
8. **Update `src/segqc/eval/__init__.py`:** import and add the five public names
   to `__all__`; extend the package docstring to mention the item-053 harness.
9. Keep imports of NumPy / `nibabel` / the pipeline deferred-or-cheap consistent
   with the existing `segqc.eval` and `segqc.pipeline` style; no new dependencies.

## Testing Strategy

New test module `tests/test_053_eval_harness.py` (test-writer's scope). One
focused test per AC, plus adversarial/edge cases. Build the synthetic cohort
in-memory from the Stage-5 generator (`segqc.synth.clean_gt.build_clean_spine`,
`segqc.synth.corpus.build_corpus` / `CASE_RECIPE`) — no disk, no external
datasets — using `segqc.config.bundled_default_config()` as `config`:

- **AC1** — import the five names from `segqc.eval.harness` and from
  `segqc.eval`.
- **AC2** — construct an `EvaluationCase`; assert fields and frozen-ness; assert
  the passed mapping/array is unchanged.
- **AC3** — one case with `Nifti1Image` sources, one with `ndarray` sources; both
  yield a well-formed `CaseEvaluation`.
- **AC4** — assert `evaluate_case(...).outcome` equals a directly-computed
  `classify_outcome(expected, run_qc(subject, config)[0])`.
- **AC5** — a case whose candidate differs from GT such that the two would give
  different verdicts (e.g. candidate = a `remove_level`/`fragment` perturbed seg,
  GT = clean base): assert `outcome.actual_verdict` matches the candidate's
  `run_qc` verdict, not the GT's.
- **AC6** — candidate present: assert `overlap == compute_overlap(cand, gt,
  gt_spacing)`.
- **AC7** — candidate present: assert `feature_match ==
  compute_feature_match(candidate_block, extract_feature_record(gt, config))`.
- **AC8** — clean-control case with `candidate=None`: `overlap is None`,
  `feature_match is None`, `candidate_present is False`, `outcome` populated, no
  raise.
- **AC9** — `evaluate_cohort` over a 3+-case cohort: assert count, order, and
  per-record `case_id`.
- **AC10** — a `detection == "pipeline"` perturbed case (e.g. `mode2_fragment`,
  `mode5_remove_level`, `mode6_crop_at_border`, or `mode7_sequence_break`):
  assert `outcome.expected_failure is True`, the outcome is positive, and
  `overlap.mean_dice < 1.0`. **Note (documented, not a bug):** the
  `reconstructed_record` modes 1/4/8 (`displace`, `relabel_swap`,
  `force_overlap`) are structurally invisible to plain `run_qc` (per items
  040/041), so the harness will legitimately record them as `FALSE_NEGATIVE`;
  tests must use a `pipeline`-detectable mode for the "caught" assertion.
- **AC11** — candidate array `==` GT array, `expected_verdict == "pass"`:
  `overlap.mean_dice == 1.0` and `outcome.outcome is Outcome.TRUE_NEGATIVE`.
- **AC12** — run `evaluate_cohort` twice on the same cohort; assert
  `json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(),
  sort_keys=True)`; assert the dict is JSON round-trippable and contains
  outcome/overlap/feature-match keys.
- **AC13** — snapshot input arrays/mapping (deep copies); run the driver; assert
  inputs are unchanged (`np.array_equal`, dict equality).
- **AC14** — candidate and GT of different shapes → `pytest.raises(SegQCInputError)`.
- **AC15** — `evaluate_cohort([], config)` → zero records, no raise.
- **AC16** — two cases with the same `case_id` → `pytest.raises(SegQCInputError)`.
- **Edge/determinism extras:** a 0-/1-label GT (feature block has no `stage3`) is
  handled without raising; a candidate label absent from GT surfaces as an
  unmatched entry in `overlap`/`feature_match` (delegated to 050/051, asserted
  present in the record).

## Dependencies

- **Item 050** ✅ — `segqc.eval.overlap.compute_overlap` (DICE/Jaccard vs GT).
- **Item 051** ✅ — `segqc.eval.feature_match.compute_feature_match` (feature
  divergence).
- **Item 052** ✅ — `segqc.eval.outcome.classify_outcome` / `CaseOutcome` /
  `Outcome` (verdict-outcome classification).
- **Item 035** ✅ — `segqc.pipeline.run_qc` / `extract_feature_record` (the real
  pipeline producing `CaseResult` + features block).
- **Item 034** ✅ — `segqc.aggregate.CaseResult` (the `actual` shape 052 consumes).
- **Stage 5 (items 036–042)** ✅ — `segqc.synth` (`build_clean_spine`,
  `build_corpus`, `CASE_RECIPE`, `Expectation.to_dict()`) — used **only by the
  tests** to assemble the local synthetic cohort; the harness itself has no
  `segqc.synth` dependency.
- **Item 032/…** — `segqc.io.SegQCInputError` (raised on shape mismatch /
  duplicate ids). Gates items **054–057**.

## Decisions & Trade-offs

Implemented as specified; no divergence from the pinned Assumptions/
Implementation Steps was needed. Notes on choices made while translating the
spec into code:

- **`CaseEvaluation.to_dict()` reduction.** Used `dataclasses.asdict` with a
  custom `dict_factory` that maps an `Outcome` enum member to its `.value`
  string wherever it appears (only inside the nested `outcome` dict, on the
  `CaseOutcome.outcome` field) rather than a bespoke recursive walker;
  `dataclasses.asdict` already recurses through nested dataclasses/tuples, so
  this keeps `OverlapResult`/`FeatureMatchResult`/`CaseOutcome` reduction to a
  single one-line hook instead of three separate serialisers.
- **Feature-match GT block is recomputed via `extract_feature_record(gt_img,
  config)`, not reused from anywhere else** — there is no prior call that
  produces it (the GT is not separately run through `run_qc` when a candidate
  is present), matching the Assumptions' explicit "GT block is
  `extract_feature_record(gt, config)`" pin. Only the *candidate* side reuses
  the block already computed by its `run_qc` call (`subject_block`), as
  specified.
- **Path-like seg-source resolution** (`_resolve_seg` on a `str`/`os.PathLike`)
  uses a plain `nib.load(...)`, matching the Stage-0 loader's integer-label
  preservation convention. This path is implemented per the Assumptions but,
  per the queue's local-testability note, is not exercised by the committed
  tests (no VerSe/TotalSegmentator fixtures in-repo).
- **`_resolve_seg` never copies array data unnecessarily.** For an
  `ndarray` source it passes the array straight to `nib.Nifti1Image(...,
  dtype=source.dtype)` (mirroring `segqc.synth.regression.loaded_seg_image`'s
  int-safe rebuild) rather than defensively copying; NiBabel/`run_qc` never
  mutate their input, so this stays non-mutating (AC13) without extra
  allocation.
- **`CaseEvaluation.metadata`** is carried through from `EvaluationCase.metadata`
  unchanged (not deep-copied) since it is read-only in this module; `to_dict()`
  wraps it in a plain `dict(...)` only for the JSON-serialisable output, not to
  guard against mutation elsewhere.
