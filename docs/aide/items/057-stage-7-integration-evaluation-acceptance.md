# Item 057 — Stage 7 integration & evaluation acceptance suite

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (G3, G7) *(completes Stage 7 & Phase 1)*
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 057 *(final item of queue-006)*
> **Objectives:** G3 (distinguish failure from legitimate variation — the
> quantified/calibrated half), G7 (evaluable / regression-testable — the
> end-to-end evaluation half)
> **Suggested branch:** `aide/057-stage-7-integration-evaluation-acceptance`

---

## Description

Close **Stage 7 — and Phase 1** — by wiring the already-merged Stage-7
evaluation building blocks (items 050–056) into **one reproducible entry point**
and proving the roadmap's literal Stage-7 acceptance bar end-to-end.

Items 050–056 built every component but left them **unreachable from the
command line**: there is no way to point `segqc` at a cohort of cases and get a
metrics report out. Concretely, the following are all merged and pure/importable
but never assembled into a runnable evaluation:

- item 050 `segqc.eval.overlap.compute_overlap` — DICE/Jaccard vs GT;
- item 051 `segqc.eval.feature_match.compute_feature_match` — feature divergence;
- item 052 `segqc.eval.outcome.classify_outcome` — TP/FP/TN/FN classification;
- item 053 `segqc.eval.harness.{EvaluationCase, evaluate_case, evaluate_cohort}`
  — assembles 050–052 per case against the real `run_qc` pipeline;
- item 054 `segqc.eval.metrics.compute_cohort_metrics` — FPR / per-mode
  sensitivity / DICE-vs-flag & divergence-vs-flag correlations;
- item 055 `segqc.eval.calibrate.{calibrate_thresholds, default_calibration_axes,
  ThresholdAxis, apply_assignment}` — the threshold-calibration loop;
- item 056 `segqc.eval.report.{build_evaluation_report,
  serialize_evaluation_report_json, write_evaluation_report,
  render_evaluation_report, record_calibrated_config, EvaluationProvenance}`
  — the versioned JSON+human report and calibrated-config recorder.

**What this item does.**

1. **A cohort-spec loader** (new module `segqc/eval/cohort.py`,
   synth-independent): `load_cohort_manifest(path) -> list[EvaluationCase]`
   reads an **evaluation-cohort manifest JSON** describing a set of
   `(GT, optional candidate, expectation)` cases — a directory of GT/candidate
   NIfTI pairs plus an expectations manifest — resolves the seg paths relative to
   the manifest file, and constructs `EvaluationCase`s. This is the general,
   dataset-agnostic ingestion path so the same entry point drives a **mounted
   VerSe GT / TotalSegmentator-vs-GT** cohort, not only the synthetic corpus.

2. **A `segqc evaluate` CLI subcommand** (in `segqc/cli.py`, mirroring the
   `segqc run` / `segqc build-reference` handler pattern) that: loads the config,
   loads the cohort via `load_cohort_manifest`, drives
   `evaluate_cohort → compute_cohort_metrics`, **optionally** runs
   `calibrate_thresholds` (`--calibrate`), builds the JSON + human evaluation
   report via item 056, writes them to `--out`, and — when calibrating —
   records the chosen calibrated config to `--out`.

3. **The Stage-7 acceptance suite** (`tests/test_057_acceptance_stage7.py`)
   asserting the roadmap's three Stage-7 acceptance criteria end-to-end over the
   committed Stage-5 synthetic corpus (`tests/corpus/`):
   - **G3 — GT passes at a high rate (low FPR):** the clean control classifies
     as a true negative and the cohort false-positive rate is `0.0`.
   - **G7 — injected failures caught; flag rate / feature divergence correlates
     with DICE:** every pipeline-detectable §6 failure mode is caught at
     per-mode sensitivity `1.0`, and over a graded-quality cohort the
     DICE-vs-flag correlation has the expected (negative) sign while the
     feature-divergence-vs-flag correlation has the expected (positive) sign.
   - **Calibrated thresholds + metrics recorded; evaluation reproducible:** a
     calibration records a config that round-trips through `load_config` and
     whose achieved metrics appear in the report; repeated evaluation is
     deterministic (byte-identical report / equal metrics).

4. **Document** the reproducible evaluation path (the `segqc evaluate` command
   and the mounted-VerSe/TotalSegmentator cohort-manifest shape) in the CLI
   help + the acceptance-test module docstring.

**Not in scope (do NOT):**
- change `run_qc`'s signature/return, or any item 050–056 module's public API
  beyond importing them and adding `cohort.py` to `segqc.eval.__init__`;
- regenerate or alter the item-042 goldens, `tests/corpus/**`, the manifest, or
  the committed `reference_default.json`;
- edit `progress.md` (validator reconciles via the CLI) or `roadmap.md` (a
  PR-gated framework/process file) — see **Progress reconciliation** below;
- add radiomics / image-intensity features, containerisation, or any Phase-2
  work — Stage 7 is the last Phase-1 stage and stops at the phase boundary;
- claim that the three reconstructed-record §6 modes (1/4/8) are caught by the
  plain pipeline (they are documented as structurally invisible — see
  Assumptions), i.e. do **not** over-claim the acceptance bar.

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test per AC. CLI /
cohort-spec ACs: `tests/test_057_evaluate_cli.py`. Acceptance-suite ACs:
`tests/test_057_acceptance_stage7.py` (see Testing Strategy)._

- [ ] **AC1: cohort-manifest loader builds `EvaluationCase`s.**
  `segqc.eval.cohort.load_cohort_manifest(path)` parses a valid
  evaluation-cohort manifest (shape pinned in Assumptions) and returns a
  `list[EvaluationCase]` — one per manifest case, in manifest order — with each
  case's `case_id`, `gt` path, optional `candidate` path (both resolved relative
  to the manifest file's directory), `expected` mapping, and optional
  `spacing`/`metadata` populated. A case with no `candidate` key yields
  `EvaluationCase.candidate is None`.

- [ ] **AC2: the loader rejects malformed cohort manifests cleanly.**
  `load_cohort_manifest` raises `segqc.io.SegQCInputError` (not a bare traceback)
  for each of: a manifest missing the `cases` array; a case missing `case_id`,
  `gt`, or `expected`; an `expected` mapping lacking `expected_verdict`; a
  duplicate `case_id`; and a `gt`/`candidate` path that does not exist on disk.

- [ ] **AC3: `segqc evaluate` runs end-to-end and writes both reports.**
  `segqc evaluate --cohort <manifest.json> --out <dir>` (via `cli.main([...])`)
  loads the cohort, drives `evaluate_cohort → compute_cohort_metrics → build/render`,
  writes `<out>/eval_report.json` and `<out>/eval_report.txt`, and returns
  exit code `0`.

- [ ] **AC4: the written JSON report is schema-valid and carries the metrics.**
  `<out>/eval_report.json` validates against the bundled evaluation-report schema
  (`segqc/eval/eval_report_schema_v0.json`, via item 056's
  `build_evaluation_report`) and contains the `provenance` block plus a `metrics`
  block carrying `false_positive_rate`, per-mode sensitivity entries, and the
  `dice_vs_flag` and `feature_divergence_vs_flag` correlations.

- [ ] **AC5: `--calibrate` records a round-tripping calibrated config and a
  report calibration block.** With `--calibrate`, `segqc evaluate` additionally
  writes `<out>/calibrated_config.yaml` (only when a feasible setting exists)
  such that `segqc.config.load_config(<that path>)` succeeds and returns a
  `HeuristicConfig` carrying the chosen thresholds, and the written
  `eval_report.json` contains a `calibration` block. Without `--calibrate`, no
  `calibrated_config.yaml` is written and the report has no `calibration` key.

- [ ] **AC6: `segqc evaluate` is reproducible.** Two invocations with identical
  arguments (same cohort, same `--config`, same `--cohort-id`, same
  `--build-date`) over the same inputs write **byte-identical**
  `eval_report.json` files (no wall-clock or other volatile field leaks in).

- [ ] **AC7: caller-input errors exit 1 cleanly.** `segqc evaluate` with a
  nonexistent `--cohort` path, and with a malformed/nonexistent `--config`,
  each returns exit code `1` with a message on stderr and **no** Python
  traceback.

- [ ] **AC8: G3 — clean GT passes; FPR is zero.** Building the acceptance cohort
  from the committed §6 corpus (GT = the `clean_control` seg fixture; candidate =
  each case's perturbed seg fixture; `expected` = the manifest case), then
  running `evaluate_cohort → compute_cohort_metrics`, the `clean_control` record
  classifies as `Outcome.TRUE_NEGATIVE` and `metrics.false_positive_rate == 0.0`.

- [ ] **AC9: G7 — pipeline-detectable failures are caught at sensitivity 1.0.**
  For every pipeline-detectable §6 mode present in the corpus cohort
  (`mode2_fragment`, `mode3_inject_islands`, `mode5_remove_level`,
  `mode6_crop_at_border`, `mode7_sequence_break`), the corresponding
  `PerModeSensitivity.sensitivity == 1.0` (the designated Stage-4 rule fired on
  the expected offending label) in `compute_cohort_metrics`' `per_mode` output.

- [ ] **AC10: G7 — DICE-vs-flag correlation has the expected (negative) sign.**
  Over a graded-quality cohort (a clean-GT positive control plus degraded
  candidates of monotonically decreasing DICE-vs-GT that the pipeline flags —
  construction pinned in Assumptions), `metrics.dice_vs_flag.coefficient` is
  **not `None`** and **< 0** (lower DICE ⇔ more likely flagged).

- [ ] **AC11: G7 — feature-divergence-vs-flag correlation has the expected
  (positive) sign.** Over the same graded-quality cohort,
  `metrics.feature_divergence_vs_flag.coefficient` is **not `None`** and **> 0**
  (higher feature divergence ⇔ more likely flagged).

- [ ] **AC12: evaluation is deterministic.** Running
  `evaluate_cohort → compute_cohort_metrics` over the corpus cohort twice yields
  equal `CohortMetrics` (`metrics.to_dict()` compares equal), and
  `serialize_evaluation_report_json(build_evaluation_report(...))` is identical
  across the two runs for identical provenance.

- [ ] **AC13: calibrated thresholds + achieved metrics are recorded.** Running
  `calibrate_thresholds` over the corpus cohort with a small explicit axis grid
  yields a feasible best candidate; `record_calibrated_config(base_config,
  result, axes, <path>)` writes a YAML that `load_config` reads back with the
  chosen thresholds applied, and `build_evaluation_report(metrics, provenance,
  calibration=result)`'s `calibration.best.metrics` block carries the achieved
  FPR / per-mode sensitivity numbers.

## Assumptions  <!-- MANDATORY -->

- **Evaluation-cohort manifest shape (clarify `assume`; pins the CLI's input
  contract).** The queue one-liner says the entry point "takes a cohort spec
  (e.g. a directory of GT/candidate NIfTI pairs + an expectations manifest,
  similar in spirit to the Stage-5 corpus manifest)" but does not fix a format.
  This spec pins a **new, minimal, synth-independent JSON manifest**:
  ```json
  {
    "manifest_version": 1,
    "cases": [
      {
        "case_id": "sub-001",
        "gt": "fixtures/sub-001_gt.nii.gz",
        "candidate": "fixtures/sub-001_cand.nii.gz",
        "spacing": [1.0, 1.0, 1.0],
        "expected": {
          "expected_verdict": "pass",
          "expected_rule_ids": [],
          "expected_labels": [],
          "failure_mode": 0,
          "failure_mode_name": "clean control (no failure)"
        },
        "metadata": {}
      }
    ]
  }
  ```
  `case_id`, `gt`, and `expected` (with `expected_verdict`) are **required** per
  case; `candidate`, `spacing`, and `metadata` are **optional**. `gt`/`candidate`
  are resolved **relative to the manifest file's directory** (like the Stage-5
  corpus manifest's `seg_fixture`). The `expected` block is the exact shape item
  052's `classify_outcome` consumes (`Expectation.to_dict()` / a `tests/corpus`
  manifest case). This is an **input** artifact (not a byte-reproducible output),
  so it is validated in code with clear `SegQCInputError` messages rather than a
  bundled JSON-schema file; unknown `manifest_version` values are accepted with a
  logged note (forward-compatible), only structural violations raise. If the
  reviewer wants the CLI to instead consume the Stage-5 corpus manifest verbatim,
  that is a follow-up — the acceptance suite already covers the corpus path via
  the in-memory builder (below).

- **Acceptance corpus cohort: GT = `clean_control` seg, candidate = each
  perturbed seg.** Every committed corpus case shares one base clean spine
  (`CASE_RECIPE` uses `_DEFAULT_BASE_PARAMS` for all; `clean_control` is the
  `identity` perturbation, so its committed seg **is** the shared base spine).
  So for each perturbed case the acceptance cohort uses `gt =
  loaded_seg_image(clean_control_case)` and `candidate =
  loaded_seg_image(perturbed_case)` (item 041's
  `segqc.synth.regression.loaded_seg_image`); `clean_control` itself uses
  `gt == candidate` (DICE `1.0`, expected `pass`). The subject under QC is the
  candidate (item 053's `evaluate_case` contract), so `run_qc` sees exactly the
  perturbed seg — identical to item 041's regression path — keeping outcomes
  consistent with the merged suites.

- **Reconstructed-record modes (1/4/8) are NOT plain-pipeline-detectable — and
  the suite must not over-claim (mirrors item 049).** Items 040/049 document
  `mode1_displace`, `mode4_relabel_swap`, and `mode8_force_overlap` as
  structurally invisible to plain `run_qc` (`detection ==
  "reconstructed_record"`). In this item's cohort the plain pipeline runs on the
  candidate and does **not** fire their designated rules, so those three cases
  classify as `FALSE_NEGATIVE`. AC9 therefore asserts per-mode sensitivity
  `1.0` only for the five **pipeline**-detectable modes (2/3/5/6/7); the suite
  does not assert the reconstructed modes are caught. Overall cohort sensitivity
  is consequently `5/8`, not `1.0` — this is correct and honest, matching item
  049's decision to scope its detection AC to the robustly-detectable modes.

- **DICE-vs-flag on the *full* §6 corpus is not cleanly signed → the
  correlation-sign ACs use a purpose-built graded-quality cohort.** Some
  flagged corpus modes barely move DICE (`mode2_fragment` conserves voxels →
  DICE ≈ 1.0; `mode3_inject_islands` adds a handful of voxels → DICE ≈ 1.0)
  while some unflagged reconstructed modes move it a lot (`mode4_relabel_swap`
  swaps two labels' voxels → low DICE, flag 0). The full 9-case cohort therefore
  yields an ambiguous DICE-vs-flag sign, so AC10/AC11 assert the sign over a
  **graded-quality cohort** designed to exhibit the roadmap relationship: a clean
  GT positive control (DICE `1.0`, unflagged) plus several degraded candidates
  of the **same** GT whose DICE-vs-GT decreases monotonically with severity and
  which the pipeline flags. **Recommended construction:** apply one
  size-distorting operator (`crop_at_border` at increasing crop depth, and/or
  `inject_islands` at increasing island count/size) to `build_clean_spine(...)`
  at graded severities; each degraded candidate is one `EvaluationCase` (GT = the
  clean spine, candidate = the degraded seg, `expected_verdict =
  "flagged-for-review"`). The test-writer **verifies the monotone DICE and the
  resulting non-`None`, correctly-signed coefficients empirically** and tunes the
  severities if a chosen series lands on a degenerate (zero-variance) DICE or
  flag column (same latitude item 049 gave for widening its bracketing cohort).

- **Reproducibility requires caller-supplied provenance (no wall clock).** Item
  056's report module performs no system-time lookup; byte-reproducibility (AC6)
  holds only if `cohort_id` and `build_date` are caller-supplied. The CLI takes
  `--cohort-id` (default: the cohort manifest filename stem) and `--build-date`
  (default: a **fixed literal**, e.g. `"2026-07-12"`, mirroring
  `build-reference`'s fixed-date precedent — never "today"). `cohort_size` is
  set to `metrics.n_cases`; `config_version` to `cfg.schema_version`.

- **`failure_modes` taxonomy for `compute_cohort_metrics`.** The CLI defaults
  `failure_modes=None` (report one `PerModeSensitivity` per observed mode, names
  taken from each record's `failure_mode_name`), keeping the CLI
  synth-independent and dataset-agnostic. The acceptance suite may pass
  `segqc.synth.perturbation.FAILURE_MODE_NAMES` explicitly when it wants every
  §6 mode represented; for the committed corpus each mode 1–8 has exactly one
  case, so `None` suffices for AC9.

- **Calibration cost is bounded in tests.** `default_calibration_axes()` is a
  5×5×5 = 125-point grid; each grid point re-runs `evaluate_cohort` (one
  `run_qc` per case). The `segqc evaluate --calibrate` end-to-end test (AC5) runs
  over a **small cohort** (clean control + 1–2 perturbed cases) and AC13 uses a
  **small explicit axis grid** (a few values on one or two axes) so both stay
  fast and deterministic. `calibrate_thresholds` never mutates the passed config
  and `record_calibrated_config` writes **only** the caller-supplied path — the
  bundled `default_config.yaml` is never touched.

- **`run_qc`, the goldens, and `tests/corpus/**` are untouched.** This item adds
  `cohort.py` + a CLI subcommand + tests only. It imports items 050–056 and the
  Stage-5 corpus/synth helpers unchanged; it does not alter `run_qc`, regenerate
  any item-042 golden, or modify the committed corpus/manifest. The full
  pre-existing suite (test_035–056) stays green.

- **Phase-1 / roadmap / progress reconciliation is downstream, not this item's
  code.** Completing Stage 7 completes Phase 1, but the living-document
  transcription is a queue/stage-boundary concern (see **Progress
  reconciliation**): the validator reconciles `progress.md` statuses via
  `python .aide/scripts/aide.py progress …`, the free-text
  **"Calibrated metrics (to be filled at completion)"** placeholders in
  `progress.md` (FPR / per-§6-mode sensitivity / DICE-vs-flag correlation) are
  transcribed from this item's emitted `eval_report.json`, and any `roadmap.md`
  edit (its Stage-7 narrative / Phase-1-complete status) is **PR-gated** per
  CLAUDE.md. Item 057's code/tests must not edit either document.

## Implementation Steps

Code paths in `src/segqc/` (`eval/cohort.py`, `eval/__init__.py`, `cli.py`) plus
the two test modules and a doc snippet.

1. **`segqc/eval/cohort.py`** (new module; synth-independent):
   1. `EVAL_COHORT_MANIFEST_VERSION = 1`.
   2. `load_cohort_manifest(path) -> list[EvaluationCase]`:
      - read + `json.loads` the manifest file; require a top-level `cases`
        array (else `SegQCInputError`);
      - for each case: require `case_id`, `gt`, and `expected` (a mapping with
        `expected_verdict`); resolve `gt` and optional `candidate` **relative to
        the manifest file's parent directory** and assert each resolved path
        exists (else `SegQCInputError`); read optional `spacing`
        (`tuple(float,…)`) and `metadata`;
      - reject duplicate `case_id`s (`SegQCInputError`);
      - construct `EvaluationCase(case_id=…, gt=<resolved str path>,
        candidate=<resolved str path or None>, expected=<mapping>,
        spacing=…, metadata=…)` (the harness's `_resolve_seg` loads path-like
        sources via `nib.load`).
      - Add to `segqc.eval.__init__`'s imports + `__all__`.
2. **`cli.py` — `evaluate` subparser** (mirror `run`/`build-reference`):
   - args: `--cohort <json>` (required), `--out <dir>` (required),
     `--config <yaml>` (optional), `--calibrate` (`store_true`),
     `--cohort-id <label>` (optional; default = cohort filename stem),
     `--build-date <YYYY-MM-DD>` (default fixed literal),
     `--log-level` (as `run`). Set `handler=_handle_evaluate`.
3. **`cli._handle_evaluate(args)`** (deferred heavy imports, as `_handle_run`):
   1. `setup_logging`; load config (`bundled_default_config()` or
      `load_config(args.config)`, wrapping `SegQCConfigError` → stderr + `return 1`).
   2. `cases = load_cohort_manifest(args.cohort)` inside a `try/except
      (SegQCInputError, OSError)` → stderr + `return 1` (AC7).
   3. `cohort = evaluate_cohort(cases, cfg)`;
      `metrics = compute_cohort_metrics(cohort)`.
   4. If `args.calibrate`: `axes = default_calibration_axes()`;
      `calibration = calibrate_thresholds(cases, cfg, axes)`; else
      `calibration = None`, `axes = None`.
   5. `provenance = EvaluationProvenance(cohort_id=args.cohort_id or <stem>,
      cohort_size=metrics.n_cases, config_version=cfg.schema_version,
      build_date=args.build_date)`.
   6. `report = build_evaluation_report(metrics, provenance,
      calibration=calibration)`;
      `write_evaluation_report(report, out/"eval_report.json")`;
      `(out/"eval_report.txt").write_text(render_evaluation_report(metrics,
      provenance, calibration=calibration), encoding="utf-8")`.
   7. If `args.calibrate` and `calibration.best is not None`:
      `record_calibrated_config(cfg, calibration, axes,
      out/"calibrated_config.yaml")`.
   8. Print a one-line summary (FPR, n_cases, calibration status); `return 0`.
4. **Test modules** — see Testing Strategy.
5. **Documentation** — a "Running an evaluation" note in the `evaluate`
   subparser `description`/help and in the acceptance-test module docstring: the
   `segqc evaluate --cohort <manifest.json> --out <dir> [--calibrate]` command
   and the mounted-VerSe/TotalSegmentator manifest shape (Assumptions), so a real
   cohort can be evaluated by writing a manifest of GT/candidate pairs.

## Testing Strategy

Two focused modules (one test per AC plus edge/adversarial cases). Do **not**
run `pytest` (spec author); the test-writer authors these, the builder
implements, the validator runs the suite.

**`tests/test_057_evaluate_cli.py`** (CLI + cohort-spec wiring):
- **AC1** — write a tiny cohort manifest to `tmp_path` referencing two committed
  corpus seg fixtures as `gt`/`candidate`; assert `load_cohort_manifest` returns
  `EvaluationCase`s in order with resolved paths, mapped `expected`, and
  `candidate is None` when the key is omitted.
- **AC2** — parametrize over each documented malformation (missing `cases`,
  missing `case_id`/`gt`/`expected`, missing `expected_verdict`, duplicate
  `case_id`, nonexistent `gt`/`candidate` path); assert `SegQCInputError`.
- **AC3/AC4** — write a small corpus-backed cohort manifest; drive
  `cli.main(["evaluate", "--cohort", …, "--out", str(tmp), "--build-date",
  "2026-07-12", "--cohort-id", "test"])`; assert exit 0, both files exist, and
  `jsonschema.validate(json.load(eval_report.json),
  <eval_report_schema_v0.json>)` passes with `metrics`/`provenance` present.
- **AC5** — run once with `--calibrate` (small 2–3-case cohort) and once
  without; assert `calibrated_config.yaml` exists + `load_config` reads it back
  and the report has a `calibration` key in the first case, and neither exists
  in the second.
- **AC6** — run `segqc evaluate` twice into two out-dirs with identical args;
  assert the two `eval_report.json` byte contents are equal.
- **AC7** — `--cohort` at a nonexistent path, and `--config` at a bad path;
  assert `cli.main(...)` returns `1` and (capsys) stderr is non-empty with no
  traceback.

**`tests/test_057_acceptance_stage7.py`** (Stage-7 G3/G7 acceptance):
- Helper: build the corpus cohort from `load_manifest()` — `gt =
  loaded_seg_image(clean_control)`, `candidate = loaded_seg_image(case)`,
  `expected = <manifest case>` for each case; `clean_control` uses
  `candidate = gt`. Drive `evaluate_cohort(cases, bundled_default_config())` then
  `compute_cohort_metrics(cohort, failure_modes=FAILURE_MODE_NAMES)`.
- **AC8** — assert the `clean_control` record's `outcome.outcome is
  Outcome.TRUE_NEGATIVE` and `metrics.false_positive_rate == 0.0`.
- **AC9** — for each of `{2,3,5,6,7}`, find its `PerModeSensitivity` and assert
  `sensitivity == 1.0`.
- **AC10/AC11** — build the graded-quality cohort (Assumptions): a clean GT
  control + degraded candidates of monotonically decreasing DICE (verify the
  DICE ordering as a precondition assertion), run the harness+metrics, and assert
  `metrics.dice_vs_flag.coefficient is not None and < 0` (AC10) and
  `metrics.feature_divergence_vs_flag.coefficient is not None and > 0` (AC11).
- **AC12** — evaluate the corpus cohort twice; assert
  `m1.to_dict() == m2.to_dict()` and equal
  `serialize_evaluation_report_json(build_evaluation_report(m, prov))` for a
  fixed `EvaluationProvenance`.
- **AC13** — `calibrate_thresholds(cases, cfg, <small axes>)` → assert
  `result.best is not None`; `record_calibrated_config(cfg, result, axes,
  tmp/"cfg.yaml")` then `load_config(tmp/"cfg.yaml")` returns the chosen
  thresholds; assert the report built with `calibration=result` has a non-`None`
  `calibration.best.metrics`.
- **Adversarial / edge cases:** an empty cohort (`evaluate_cohort([], cfg)`)
  yields `n_cases == 0` and `false_positive_rate is None` (no crash); a
  candidate-less GT-only case yields `overlap is None` / DICE series contributes
  no pair (correlation `n` unaffected by the missing pair); a cohort with two
  duplicate `case_id`s raised by `evaluate_cohort` surfaces as `SegQCInputError`.

## Dependencies

- **Item 050 (✅)** — `compute_overlap` (DICE/Jaccard): the level-2 signal the
  DICE-vs-flag correlation reads.
- **Item 051 (✅)** — `compute_feature_match` (divergence): the level-3 signal
  the divergence-vs-flag correlation reads.
- **Item 052 (✅)** — `classify_outcome` / `Outcome` / `CaseOutcome`: the
  TP/FP/TN/FN classification behind FPR + per-mode sensitivity.
- **Item 053 (✅)** — `EvaluationCase` / `evaluate_cohort` (accepts path-like
  seg sources via `_resolve_seg`): the cohort the loader constructs and the CLI
  drives.
- **Item 054 (✅)** — `compute_cohort_metrics` / `CohortMetrics` /
  `PerModeSensitivity` / `CorrelationResult`: the metrics the report and ACs
  assert on.
- **Item 055 (✅)** — `calibrate_thresholds` / `default_calibration_axes` /
  `ThresholdAxis` / `apply_assignment`: the `--calibrate` loop.
- **Item 056 (✅)** — `build_evaluation_report` / `serialize_evaluation_report_json`
  / `write_evaluation_report` / `render_evaluation_report` /
  `record_calibrated_config` / `EvaluationProvenance` + the bundled
  `eval_report_schema_v0.json`: the report render/write + calibrated-config record.
- **Item 035 (✅)** — `pipeline.run_qc`, `cli._handle_run`/`_build_parser`,
  `config.{load_config, bundled_default_config}`: the CLI/pipeline/config
  surfaces extended here.
- **Items 040/041/042 (✅)** — the committed synthetic corpus + manifest,
  `synth.corpus.load_manifest`, `synth.regression.loaded_seg_image`, and the
  golden byte-stability contract: the acceptance cohort's inputs, untouched.
- **Items 036–039 (✅)** — `synth.clean_gt.build_clean_spine` + the registered
  perturbation operators (`crop_at_border` / `inject_islands` / …) and
  `synth.perturbation.FAILURE_MODE_NAMES`: used to build the graded-quality
  correlation cohort and to name §6 modes in the acceptance suite.

## Progress reconciliation (for the validator — not edited by spec-author)

Item 057 completes **Stage 7 and Phase 1**. On validated merge, the validator
(via `python .aide/scripts/aide.py progress …`, plus the free-text/PR steps
noted) should reconcile in `progress.md`:

- the final Stage-7 deliverable bullet — "Stage-7 integration into a reproducible
  `segqc evaluate` entry point + acceptance suite …" — from 📋 to ✅ *(item 057)*;
- the three Stage-7 **Acceptance** checkboxes: "GT passes at a high rate (low
  FPR) (**G3**)", "Injected failures caught; flag rate / feature divergence
  correlates with DICE (**G7**)", and "Calibrated thresholds + metrics recorded;
  evaluation reproducible";
- the **Stage 7** summary-row status 🚧 → ✅ (and its "*(Phase 1 complete)*"
  marker), and the **G3** / **G7** objective-coverage rows 🚧 → ✅;
- the **"Calibrated metrics (to be filled at completion)"** block — FPR on GT,
  sensitivity per §6 failure mode, DICE-vs-flag correlation — transcribed from
  the numbers this item's acceptance run emits into `eval_report.json`
  (`metrics.false_positive_rate`, `metrics.per_mode[*].sensitivity`,
  `metrics.dice_vs_flag.coefficient`).

Any edit to **`roadmap.md`** (its Stage-7 narrative or the Phase-1-complete
status) is a **PR-gated** framework/process change per CLAUDE.md and is **not**
part of item 057's direct-merge work.

## Decisions & Trade-offs

To be updated during implementation.
