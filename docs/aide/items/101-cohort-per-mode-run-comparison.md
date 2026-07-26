# Item 101 — Cohort-level per-mode report with run-vs-run comparison

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 18 — Failure-Mode-Specific Metric Surface (G2, G7)
> **Queue:** [`../queue/queue-014.md`](../queue/queue-014.md) · Item 101
> *(fourth of five; item 098 named the stray-component population, item 099
> built the eight per-case magnitude metrics, item 100 proved they move
> monotonically with their own mode's severity — this item aggregates them
> over a cohort and diffs two cohorts; item 102 replays the whole thing
> through the CLI as the stage validation)*
> **Objectives:** G2 (a change in a segmenter's behaviour must be attributable
> to a specific §6 failure mode, not washed into an aggregate Dice number), G7
> (the attribution is a reproducible, schema-validated artifact, not a
> narrative)
> **Suggested branch:** `aide/101-cohort-level-per-mode-report`

---

## Description

Items 099 and 100 built and validated a **per-case** magnitude surface: eight
named scalar metrics, one per §6 failure mode, each proven monotone in its own
mode's severity and comparatively insensitive to the others. Nothing yet
aggregates them over a cohort, and nothing compares two cohorts.

This item closes Stage 18's third deliverable — the reason the metric surface
was built at all. The use case, stated in the roadmap
(`roadmap.md:717-719`): **two runs of the same segmentation tool over the same
cases, differing in one behaviour** (a post-processing step on vs. off, or two
segmenter versions), and the question *"what actually changed?"*. Aggregate
Dice answers that badly — stripping every stray island might move `mean_dice`
by 0.001 while eliminating the entire §6 mode-3 population. A per-mode delta
report answers it directly: **which mode moved, by how much, in which
direction**.

The item delivers three layers, each built on what already exists:

1. **An opt-in per-mode hook on the Stage-7 harness.** `evaluate_case`
   (`harness.py:312`) already computes everything item 099 needs — the
   subject's feature record (`subject_block`), the candidate array, the GT
   array, the GT spacing — and throws all four away. A keyword-only
   `per_mode=False` parameter turns on one `compute_per_mode_metrics` call per
   case, attaching a `PerModeMetrics` to the existing `CaseEvaluation` record.
   No second pipeline run, no second cohort walk.

2. **A cohort aggregator + run comparator** — a new pure module,
   `src/segfacet/eval/per_mode_cohort.py`, which folds a cohort's per-case
   `PerModeMetrics` into one `RunPerModeSummary` per run and diffs two
   summaries into a `RunComparison`. It reads item 054's
   `PerModeSensitivity` **verbatim** for the detection-rate column and
   recomputes none of it, so the report shows *"did we catch it"* (item 054)
   and *"how much of it was there"* (item 099) side by side, exactly as item
   099's docstring promised.

3. **Reporting + CLI reach**, on the Stage-7 surface rather than beside it:
   an additive `per_mode_magnitude` block in `eval_report_schema_v0.json`, a
   new schema-validated comparison artifact, a plain-text renderer, a
   `--per-mode` flag on `segfacet evaluate`, and a new `segfacet compare-runs`
   subcommand. A report nobody can reach is not a deliverable, and item 102's
   validation explicitly replays this **through the CLI**.

### The comparison arithmetic

Per-mode metrics are not commensurable — `rogue_island_count` is a count,
`mislabelled_volume_fraction` is a fraction, `overlapping_voxel_count` runs to
thousands. "Which mode moved most" therefore needs a dimensionless reading.
For mode `m`, with `baseline` taken from `PER_MODE_METRIC_SPECS[m].baseline`:

```
value_a  = mean over run A's cases whose mode-m value is not None
value_b  = mean over run B's cases whose mode-m value is not None
delta    = value_b - value_a
scale    = max(|value_a - baseline|, |value_b - baseline|)
normalised_delta = delta / scale        (0.0 when scale == 0.0)
```

`normalised_delta` is *the fraction of the mode's own observed excursion from
its clean baseline that the change accounts for*. A mode driven from 1.0 rogue
islands per case to 0.0 reads `-1.0` — the whole population removed. A mode
that drifts from 4.0 to 5.0 reads `+0.2`. A mode that does not move reads
`0.0`. That makes `attributed_mode = argmax |normalised_delta|` well defined,
and makes the stage's thesis a printable number: *the implicated mode moved
through 100% of its excursion while `mean_dice` moved 0.001*.

`worsened` records **direction-aware** interpretation: the metric moving *away*
from `baseline` in the mode's declared `direction` is worse. Mode 2's
`min_dominant_component_fraction` `decreases` with severity, so a negative
delta there is a regression while a negative delta on the other seven is an
improvement. A comparison must never report mode 2 backwards.

**What this item is NOT:**

- **Not a new metric.** `eval/per_mode.py` is untouched; every magnitude comes
  from `compute_per_mode_metrics`, every detection rate from
  `CohortMetrics.per_mode`, every Dice aggregate from the
  `PerModeMetrics` context item 099 already carries out of its single
  `compute_overlap` call. No Dice/Jaccard arithmetic is written here.
- **Not a change to `eval/metrics.py`.** `PerModeSensitivity` and
  `CohortMetrics` are read, never modified, never duplicated — this item adds
  the *magnitude* column beside them, not a second detection-rate computation.
- **Not a change to the per-case QC report.** `report_schema_v0.json`,
  `segfacet.report`, `segfacet.human_report` and `segfacet run` are untouched;
  this is a cohort artifact.
- **Not a rule, threshold or verdict change.** Nothing here fires a finding or
  changes a verdict. `heuristics/**`, `features/**` and `synth/**` are
  untouched.
- **Not a severity-ladder change.** `eval/severity_ladder.py` is untouched.
  Item 100 noted this item *may* cite its recorded margins in provenance;
  it deliberately does not (see Assumptions) — that is a Stage-20 concern.
- **Not a real-data claim.** Every fixture is synthetic. Stage 16/21 own real
  corpora; item 102 must not read this item as closing a real-data row.
- **Not a calibration or statistics upgrade.** No significance testing, no
  confidence intervals, no per-case ranking. Means and deltas only.

## Acceptance Criteria

- [ ] **AC1: the module and its public surface exist.**
  `segfacet.eval.per_mode_cohort` defines and exports, via `__all__`:
  `ModeAggregate`, `RunPerModeSummary`, `ModeDelta`, `RunComparison`,
  `summarise_run_per_mode`, `compare_runs`. Every one of those names is also
  importable from `segfacet.eval` (added to `eval/__init__.py`'s import block
  and `__all__`). All four dataclasses are `@dataclass(frozen=True)`.

- [ ] **AC2: the harness's per-mode hook is opt-in and off by default.**
  `evaluate_case` and `evaluate_cohort` each accept a keyword-only
  `per_mode: bool = False`; `CaseEvaluation` has a `per_mode:
  Optional[PerModeMetrics] = None` field. With the parameter omitted, every
  record's `per_mode` is `None`, and `CaseEvaluation.to_dict()["per_mode"]` is
  `None`.

- [ ] **AC3: the per-mode hook, when enabled, produces item 099's values
  unchanged.** For a case with both a candidate and a GT,
  `evaluate_case(case, cfg, per_mode=True).per_mode.to_dict()` equals
  `compute_per_mode_metrics(record, candidate=cand_arr, gt=gt_arr,
  spacing=gt_spacing).to_dict()` computed independently in the test from the
  same inputs — this module derives no metric of its own.

- [ ] **AC4: the hook adds no second pipeline pass.** With `per_mode=True`,
  spies confirm `segfacet.pipeline.run_qc` is called exactly once per case and
  `compute_per_mode_metrics` exactly once per case — the record, candidate
  array, GT array and spacing are the ones `evaluate_case` already computed,
  not a re-derivation.

- [ ] **AC5: a candidate-less case degrades explicitly, never raises.** For an
  `EvaluationCase` with `candidate=None` and `per_mode=True`, `per_mode` is a
  populated `PerModeMetrics` whose modes 1, 4 and 5 have `value is None` with a
  non-empty `detail`, whose modes 2, 3, 6, 7, 8 have `float` values computed
  from the GT-as-subject record, and whose `mean_dice` is `None`.

- [ ] **AC6: `summarise_run_per_mode` returns exactly eight aggregates in mode
  order.** For any cohort — including an empty one —
  `RunPerModeSummary.per_mode` is a tuple of length 8 whose `failure_mode`
  values are `(1, 2, 3, 4, 5, 6, 7, 8)`, and for each entry `metric_name`,
  `direction` and `baseline` equal `PER_MODE_METRIC_SPECS[k]`'s fields
  character-for-character / exactly.

- [ ] **AC7: the aggregate statistics are the documented arithmetic.** For each
  mode, `n_with_value` is the count of cases whose value is not `None`; `mean`
  is the arithmetic mean, `minimum`/`maximum` the extrema and `total` the sum
  over exactly those cases; all four are `None` (`total` included) when
  `n_with_value == 0`. Verified against hand-computed values on a fixture with
  a deliberate mix of present and `None` values.

- [ ] **AC8: detection rates are read verbatim from item 054, never
  recomputed.** When a `CohortMetrics` is passed, each `ModeAggregate`'s
  `detection_rate` and `n_detection_cases` equal the matching
  `PerModeSensitivity`'s `sensitivity` and `n_cases`, and are `None`/`0` for a
  mode with no `PerModeSensitivity` entry. With `metrics=None` (the default)
  every `detection_rate` is `None` and every `n_detection_cases` is `0`.

- [ ] **AC9: the aggregate Dice context comes from item 099's carried
  fields.** `RunPerModeSummary.mean_dice` and `.volume_weighted_dice` are the
  means over cases of `PerModeMetrics.mean_dice` / `.volume_weighted_dice`
  (skipping `None`), and `None` when no case carried one. `per_mode_cohort.py`
  contains no Dice or Jaccard formula and never calls `compute_overlap` —
  asserted by reading the module source (the drift guard, mirroring item 099's
  AC18 and item 100's AC4).

- [ ] **AC10: `compare_runs` returns exactly eight deltas in mode order with
  the documented delta arithmetic.** `RunComparison.per_mode` has length 8 with
  `failure_mode` values `(1..8)`; each `ModeDelta` carries `value_a`/`value_b`
  copied from the two summaries and `delta == value_b - value_a`, or
  `delta is None` when either side is `None`.

- [ ] **AC11: `scale` and `normalised_delta` follow the stated formula.** For
  every mode, `scale == max(abs(value_a - baseline), abs(value_b - baseline))`
  and `normalised_delta == delta / scale`, except that `normalised_delta` is
  exactly `0.0` when `scale == 0.0` and `None` when `delta is None` — never a
  `ZeroDivisionError`, `nan` or `inf`.

- [ ] **AC12: `worsened` is direction-aware and mode 2 is not reported
  backwards.** `worsened` is `None` iff `delta is None`; otherwise it is `True`
  iff the metric moved away from `baseline` in its `direction` (positive
  `delta` for an `"increases"` metric, negative `delta` for a `"decreases"`
  metric) and `False` otherwise, including `delta == 0.0`. Asserted explicitly
  on mode 2 (`min_dominant_component_fraction`, `direction == "decreases"`): a
  drop from `1.0` to `0.5` yields `worsened is True` while a rise yields
  `False`.

- [ ] **AC13: `attributed_mode` is the largest normalised move, ties to the
  lowest mode.** `attributed_mode` is the `failure_mode` with the greatest
  `abs(normalised_delta)`; on an exact tie the numerically lowest mode wins;
  it is `None` when every mode's `normalised_delta` is `None` or `0.0`.
  `attributed_mode_name` and `attributed_metric_name` agree with
  `PER_MODE_METRIC_SPECS[attributed_mode]` (both `None` when the mode is).

- [ ] **AC14: comparing a run against itself is an all-zero report.**
  `compare_runs(s, s)` yields, for every mode, `delta == 0.0`,
  `normalised_delta == 0.0` and `worsened is False`; `mean_dice_delta == 0.0`;
  `volume_weighted_dice_delta == 0.0`; and `attributed_mode is None`. No mode
  is spuriously implicated.

- [ ] **AC15: mismatched cohorts are rejected, never silently diffed.**
  `compare_runs` raises `segfacet.io.FacetInputError` when the two summaries'
  `case_ids` sets differ, with a message naming at least one id present on
  only one side. Identical id sets in a **different order** compare
  successfully (order is not identity).

- [ ] **AC16: the demonstrator — a mode-specific change is attributed to that
  mode while aggregate Dice barely moves.** Two runs over the same cohort,
  differing only by an injected post-processing step that removes stray islands
  from every candidate, produce a comparison with `attributed_mode == 3`
  (`rogue_island_count`), `by_mode(3).worsened is False` (islands removed is an
  improvement), and `abs(by_mode(3).normalised_delta) >
  abs(comparison.mean_dice_delta)`. This is Stage 18's thesis, asserted.

- [ ] **AC17: both records round-trip through JSON and back into dataclasses.**
  `RunPerModeSummary.to_dict()` and `RunComparison.to_dict()` satisfy
  `json.loads(json.dumps(d)) == d`, and
  `RunPerModeSummary.from_dict(summary.to_dict()) == summary` reconstructs an
  equal dataclass — the path `segfacet compare-runs` uses to rehydrate a
  summary out of a written evaluation report.

- [ ] **AC18: both `to_dict()`s are plain JSON, with no numpy leakage.** A
  recursive walk of each finds only `dict` / `list` / `str` / `float` / `int` /
  `bool` / `None`, with `str` mapping keys only — no tuples, dataclasses,
  numpy scalars or non-string keys. Every metric value is a plain `float` or
  `None`, never `numpy.float64`.

- [ ] **AC19: the evaluation report gains an optional additive block; v0 stays
  v0.** `build_evaluation_report` accepts a keyword-only
  `per_mode_summary=None`; when given, the report carries
  `report["per_mode_magnitude"] == per_mode_summary.to_dict()` and still
  validates against `eval_report_schema_v0.json`; when omitted, the report
  carries **no** `per_mode_magnitude` key and is byte-identical to the pre-101
  output for the same inputs. `EVAL_REPORT_SCHEMA_VERSION` and the schema's
  `schema_version.const` both remain `"0.1"`, and `per_mode_magnitude` is
  **not** in the schema's `required` list.

- [ ] **AC20: the comparison artifact has its own bundled, versioned schema.**
  `segfacet.eval.report` exports `PER_MODE_COMPARISON_SCHEMA_VERSION == "0.1"`
  and `build_run_comparison_report(comparison, provenance_a, provenance_b)`,
  which returns a dict validating against a bundled
  `src/segfacet/eval/per_mode_comparison_schema_v0.json` loaded via
  `importlib.resources` (the `_load_eval_schema` pattern). The schema's root
  has `additionalProperties: false` and requires `schema_version`,
  `run_a`, `run_b` and `comparison`; a report with a required key deleted fails
  validation.

- [ ] **AC21: both artifacts are byte-reproducible within a session.** Writing
  the same comparison report twice via `write_evaluation_report` to two
  destinations yields `dest1.read_bytes() == dest2.read_bytes()`, each ending
  in exactly one `b"\n"`; likewise for an evaluation report carrying a
  `per_mode_magnitude` block. No clock is read anywhere in the build path.

- [ ] **AC22: the human rendering names the implicated mode in words.**
  `render_run_comparison(comparison)` returns a non-empty plain-text string
  containing the attributed mode's `failure_mode_name` verbatim (e.g.
  `"disconnected components / rogue islands"`), its `metric_name`, both run
  ids, and the aggregate `mean_dice` delta; every `None` renders as `"n/a"` and
  the literal string `"None"` never appears. On an all-zero comparison it says
  so explicitly instead of naming a mode.

- [ ] **AC23: `segfacet evaluate --per-mode` wires the block end to end.** The
  flag exists with `action="store_true"` and default `False`; with it, the
  written `<out>/eval_report.json` carries a `per_mode_magnitude` block with
  eight entries and `<out>/eval_report.txt` carries a per-mode magnitude
  section; without it, neither file mentions per-mode magnitudes and the
  written JSON is byte-identical to the pre-101 output. A `--run-id` flag
  stamps `per_mode_magnitude.run_id`, defaulting to the report's `cohort_id`.

- [ ] **AC24: `segfacet compare-runs` produces the comparison from two written
  reports.** `main(["compare-runs", "--run-a", A, "--run-b", B, "--out", D])`
  returns `0`, writes `D/per_mode_comparison.json` (schema-valid) and
  `D/per_mode_comparison.txt` (non-empty), and prints a one-line summary naming
  the attributed mode. `A` and `B` are real `eval_report.json` files written by
  `segfacet evaluate --per-mode` in the same test.

- [ ] **AC25: every `compare-runs` failure is a clean exit 1, never a
  traceback.** Each of — a `--run-a` path that does not exist; a report file
  that is not valid JSON; a report with no `per_mode_magnitude` block; two
  reports whose cohorts differ — returns `1` and prints a message starting
  `Error:` on stderr, writing no output file. No exception escapes `main`.

- [ ] **AC26: the aggregation and comparison are pure and idempotent.**
  `summarise_run_per_mode` and `compare_runs` open no file, read no clock, and
  do not mutate the `CohortEvaluation`, `CohortMetrics` or summaries passed to
  them (checked against pre-call `to_dict()` snapshots); calling either twice
  on the same inputs returns equal results.

- [ ] **AC27: the scope fence holds.** `src/segfacet/eval/per_mode.py`,
  `src/segfacet/eval/metrics.py`, `src/segfacet/eval/overlap.py`,
  `src/segfacet/eval/severity_ladder.py`, `src/segfacet/eval/calibrate.py`,
  `src/segfacet/heuristics/**`, `src/segfacet/features/**`,
  `src/segfacet/synth/**`, `src/segfacet/report_schema_v0.json` and
  `tests/corpus/**` are byte-identical to their pre-101 state. The only
  production files this item adds or edits are
  `src/segfacet/eval/per_mode_cohort.py` (new),
  `src/segfacet/eval/per_mode_comparison_schema_v0.json` (new),
  `src/segfacet/eval/harness.py`, `src/segfacet/eval/report.py`,
  `src/segfacet/eval/eval_report_schema_v0.json`,
  `src/segfacet/eval/__init__.py` and `src/segfacet/cli.py`.

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`). Each default below was
chosen against the merged 099/100 modules and the Stage-7 sources; the
reasoning is recorded so the validator can audit it at the queue boundary.

- **CLI wiring is in scope, unlike items 099 and 100.** Both predecessors were
  deliberately library-only. This item is not: the queue says outright
  *"Surface it on the CLI as either a new subcommand or a flag on `evaluate`"*,
  and item 102's validation requires *"the run-vs-run comparison (item 101)
  through the **CLI** on two runs of the same cohort"*. Deferring the CLI would
  block the stage-closing item.

- **Both CLI shapes, each where it belongs.** `--per-mode` is a **flag on
  `evaluate`** because the per-mode magnitudes describe *one* run and belong in
  that run's own report; `compare-runs` is a **new subcommand** because a
  comparison takes *two* reports and has no single `--cohort`. Bolting a
  `--compare-to` onto `evaluate` would have made a two-run operation
  masquerade as a one-run one.

- **`--per-mode` is opt-in, not always-on.** Always-on would change every
  existing `eval_report.json`'s bytes and pay one extra `compute_overlap` per
  case for callers who never look at the block. Opt-in keeps every pre-101
  caller byte-identical (AC19/AC23) at the cost of item 102 having to pass the
  flag, which its spec already anticipates.

- **The extra `compute_overlap` call is accepted, not optimised away.**
  `evaluate_case` already calls `compute_overlap` for its `overlap` field, and
  `compute_per_mode_metrics` calls it again internally.
  Widening item 099's signature to accept a precomputed `OverlapResult` would
  edit `per_mode.py`, which AC27 fences off, and would complicate the API that
  items 099/100 froze for one avoidable pass over a label map. Recorded as a
  known, bounded cost rather than hidden.

- **The per-mode hook lives on the existing harness rather than in a parallel
  cohort walk.** The alternative — a standalone function that re-resolves each
  `EvaluationCase`'s seg sources and re-runs `extract_feature_record` — would
  double the pipeline cost and duplicate the driving loop, violating the
  queue's *"Build on the existing Stage-7 reporting surface rather than a
  parallel one"* and the same no-duplication discipline items 099/100 followed.
  `evaluate_case` already holds all four inputs in local variables; the hook is
  four lines there and free.

- **`CaseEvaluation` gains an optional trailing field, which is additive.** The
  new field is defaulted (`= None`) and appended after `metadata`, so every
  existing positional and keyword construction still works, and `to_dict()`
  grows one key whose value is `None` unless the hook was enabled. The sweep
  below found no test asserting an exhaustive `CaseEvaluation.to_dict()` key
  set (`test_053_eval_harness.py:517-525` uses `in` membership) and none
  asserting an exhaustive `eval` `__all__` (`test_053:100` uses `>=`).

- **The aggregate statistic is the arithmetic mean, with min/max/total carried
  alongside.** The median was rejected: on the count-valued metrics (modes 3,
  5, 6, 7, 8) over a small cohort the median is very often exactly `0`, which
  would hide precisely the shift the report exists to show. Mean over the cases
  that *have* a value (with `n_with_value` published so the reader sees the
  denominator) is the honest reading, and it is the statistic that makes
  `delta` a mean-difference rather than an artefact of a rank statistic.

- **`normalised_delta` is normalised by the observed excursion from baseline,
  not by run A alone.** Dividing by `|value_a - baseline|` alone would be
  undefined exactly in the most interesting case — a mode absent in the "off"
  run and present in the "on" run (or vice versa). Using
  `max(|value_a - baseline|, |value_b - baseline|)` is symmetric under swapping
  the runs (it negates, never explodes), is bounded in `[-1, 1]` whenever both
  values sit on the same side of the baseline, and reads as *"what fraction of
  the mode's observed excursion did this change account for"*. `scale == 0.0`
  means neither run departed from baseline, so `0.0` is the correct delta, not
  a division.

- **`attributed_mode` compares normalised per-mode moves to each other, and the
  report prints the aggregate Dice delta beside it rather than ranking them
  together.** A normalised excursion fraction and an absolute Dice difference
  are not the same kind of number, and the report does not pretend they are —
  AC16 asserts the *contrast* (`|normalised_delta| > |mean_dice_delta|`), which
  is the stage's rhetorical point, and the human rendering prints both with
  their own labels.

- **Cohort identity is the set of `case_id`s, not their order and not a
  content hash.** `case_id` is already the harness's uniqueness key
  (`evaluate_cohort` rejects duplicates, `harness.py:466-473`) and the cohort
  manifest's required field. A content hash of the underlying NIfTIs would be
  stronger but would require the comparison to re-read the label maps, which
  a report-level diff must not do. Set (not sequence) equality so a reordered
  manifest still compares; recorded because it is a deliberate loosening.

- **The evaluation report gets an additive optional property; the comparison
  gets a new schema.** The queue asked for this decision explicitly. The
  per-run magnitude block is a *new optional facet of the same document*, so
  it follows item 096's `run_manifest` precedent exactly — a new optional
  property plus a definition, no `schema_version` bump, every pre-101 report
  still valid. The comparison is a *different document* (two runs, deltas, an
  attribution) and gets its own bundled `per_mode_comparison_schema_v0.json` at
  its own version `"0.1"`, rather than being crammed in as a third optional
  block of a schema whose title is "FACET Evaluation Report".

- **`write_evaluation_report` is reused for the comparison artifact rather than
  cloned.** It is already generic over `report: dict` (`report.py:248`) and
  carries the repo's `Path.write_bytes` + single-trailing-`\n` byte-
  reproducibility discipline. Adding a second, identical writer would
  duplicate exactly the convention this repo has a gotcha section about.

- **No new committed fixture, so no `.gitattributes` entry is needed.** Every
  test artifact is written under `tmp_path`. Should the builder find a reason
  to commit a text fixture, `CLAUDE.md`'s LF-pin rule applies and the
  `.gitattributes` entry is mandatory — but the spec's intent is that none is
  committed. Likewise no `pyproject.toml` change: the hatch wheel target
  packages the whole `src/segfacet` tree (`pyproject.toml:84-85`), so the new
  bundled schema ships automatically.

- **Item 100's recorded margins are deliberately *not* cited in the report's
  provenance.** Item 100's Downstream note offered this as optional. Rejected:
  the margins describe the *metrics'* specificity on a synthetic ladder, not
  anything about the two cohorts being compared, and importing
  `severity_ladder` into the report path would couple a cohort artifact to a
  33-case synthetic harness. Stage 20 owns specificity reporting.

- **The run manifests (item 096) identify the two runs; `run_id` is a
  human label.** `EvaluationProvenance` and the report's `run_manifest` block
  already carry segmenter version / SHA / seed / `postproc_toggles` — the
  fields that actually distinguish "post-processing on" from "off". The
  comparison report embeds both runs' `run_manifest` blocks verbatim when
  present (`None` when absent, never fabricated), and `run_id` is a free-text
  label defaulting to the cohort id, exactly as `EvaluationProvenance.cohort_id`
  is free text.

- **The `compare-runs` subcommand takes no `--backend` flag.** It performs no
  array computation — it reads two JSON documents and does float arithmetic.
  `test_075_cli_backend.py`'s `SUBCOMMANDS` list is a fixed three-element
  literal (`test_075:50`), so a fourth subcommand does not break it; the
  omission is deliberate and should be stated in the subcommand's help text.

## Implementation Steps

All production changes are under `source_dir = src/segfacet`.

1. **`src/segfacet/eval/harness.py` — the opt-in hook.**
   - Add `per_mode: Optional["PerModeMetrics"] = None` as the last field of
     `CaseEvaluation`, and a `"per_mode": (None if self.per_mode is None else
     self.per_mode.to_dict())` entry to its `to_dict()`.
   - Add keyword-only `per_mode: bool = False` to `evaluate_case`. Inside the
     existing `if candidate_present:` block (which already has `candidate_arr`,
     `gt_arr`, `gt_spacing`), and in the `else` path for a candidate-less case,
     call `compute_per_mode_metrics(subject_block, candidate=candidate_arr,
     gt=gt_arr, spacing=gt_spacing)` — passing `candidate=None, gt=None` when
     no candidate exists, and `spacing` from `gt_img.header.get_zooms()[:3]`.
     Import it lazily in the function body, matching the module's existing
     deferred-import style.
   - Add the same keyword-only `per_mode: bool = False` to `evaluate_cohort`
     and forward it unchanged to every `evaluate_case` call.
   - Extend both docstrings and the module docstring's `Public API` block.

2. **Create `src/segfacet/eval/per_mode_cohort.py`** with a module docstring in
   the package's house style: what it is (Stage 18's cohort-level per-mode
   surface + run-vs-run comparator, item 101), how it relates to item 099
   (aggregates its per-case magnitudes) and item 054 (reads its detection
   rates verbatim, duplicates none of them), the `scale`/`normalised_delta`/
   `worsened`/`attributed_mode` definitions in full, the purity contract, a
   **Scope fence**, and a `Public API` block.

3. **The four frozen dataclasses**, each with the fields the ACs name:
   - `ModeAggregate` — `failure_mode`, `failure_mode_name`, `metric_name`,
     `direction`, `baseline`, `n_cases`, `n_with_value`, `mean`, `minimum`,
     `maximum`, `total`, `detection_rate`, `n_detection_cases`.
   - `RunPerModeSummary` — `run_id`, `case_ids: Tuple[str, ...]`, `n_cases`,
     `per_mode: Tuple[ModeAggregate, ...]`, `mean_dice`,
     `volume_weighted_dice`, `run_manifest: Optional[dict]`; with `to_dict()`
     (`_tuples_to_lists(dataclasses.asdict(self))`, the local helper copied
     from `per_mode.py` rather than imported from `eval.metrics`, per AC27),
     `by_mode(k)` raising `KeyError` for an unknown mode, and a
     `from_dict(cls, d)` classmethod rebuilding the dataclass (raising
     `FacetInputError` on a malformed/missing block — this is the path
     `compare-runs` uses on caller-supplied JSON).
   - `ModeDelta` — the spec fields plus `value_a`, `value_b`, `delta`, `scale`,
     `normalised_delta`, `worsened`, `detection_rate_a`, `detection_rate_b`,
     `detection_rate_delta`.
   - `RunComparison` — `run_a_id`, `run_b_id`, `n_cases`, `case_ids`,
     `per_mode: Tuple[ModeDelta, ...]`, `mean_dice_a/_b/_delta`,
     `volume_weighted_dice_a/_b/_delta`, `attributed_mode`,
     `attributed_mode_name`, `attributed_metric_name`, `run_manifest_a`,
     `run_manifest_b`; with `to_dict()`, `by_mode(k)` and `summary() -> str`.

4. **`summarise_run_per_mode(cohort, *, run_id, metrics=None,
   run_manifest=None) -> RunPerModeSummary`** — iterate `cohort.cases`,
   collecting each record's `per_mode` (skipping records whose `per_mode` is
   `None`, and raising `FacetInputError` if **every** record is `None` while
   the cohort is non-empty, so a caller who forgot `per_mode=True` gets a clear
   message instead of eight empty aggregates). Build the eight `ModeAggregate`s
   by iterating `PER_MODE_METRIC_SPECS` in mode order and folding the per-case
   values; fold the detection column from `metrics.per_mode` keyed by
   `failure_mode`. Compute the two Dice aggregates from the per-case
   `PerModeMetrics.mean_dice` / `.volume_weighted_dice`.

5. **`compare_runs(run_a, run_b) -> RunComparison`** — validate the `case_ids`
   sets first (raise `FacetInputError` naming a differing id before computing
   anything), then build the eight `ModeDelta`s per the arithmetic above,
   then the aggregate deltas, then `attributed_mode` (`max` over
   `abs(normalised_delta)` with `None`/`0.0` excluded, ties to the lowest
   mode). `n_cases`/`case_ids` come from the (now-agreed) shared set, sorted.

6. **`src/segfacet/eval/eval_report_schema_v0.json`** — add a
   `perModeMagnitude` definition (mirroring `RunPerModeSummary.to_dict()`'s
   shape) and a `per_mode_magnitude` entry in `properties` referencing it.
   Do **not** add it to `required`; do **not** change `schema_version.const`.

7. **Create `src/segfacet/eval/per_mode_comparison_schema_v0.json`** — draft-07,
   `additionalProperties: false`, `required: [schema_version, run_a, run_b,
   comparison]`, `schema_version.const == "0.1"`, with `run_a`/`run_b` holding
   each side's provenance + optional run manifest and `comparison` holding
   `RunComparison.to_dict()`'s shape.

8. **`src/segfacet/eval/report.py`** —
   - `build_evaluation_report(..., per_mode_summary=None)`: embed
     `per_mode_summary.to_dict()` under `per_mode_magnitude` when given, before
     the existing `jsonschema.validate` call.
   - `render_evaluation_report(..., per_mode_summary=None)`: append a
     "Per-mode magnitudes" section (one line per mode: name, metric, mean,
     `n_with_value`, detection rate) using the existing `_fmt_metric` helper,
     and nothing at all when `None`.
   - New `PER_MODE_COMPARISON_SCHEMA_VERSION`, `_load_comparison_schema()`
     (the `_load_eval_schema` pattern, module-level cache),
     `build_run_comparison_report(comparison, provenance_a, provenance_b)` and
     `render_run_comparison(comparison)`. Extend `__all__` and the module
     docstring.

9. **`src/segfacet/eval/__init__.py`** — add a
   `from .per_mode_cohort import (...)` block (alphabetically, after
   `.per_mode`), the three new `.report` names, append every new name to
   `__all__`, and extend the package docstring's running sentence with the
   cohort-level per-mode surface and its item number (101).

10. **`src/segfacet/cli.py`** —
    - `evaluate_parser`: add `--per-mode` (`action="store_true"`, default
      `False`) and `--run-id` (default `None`).
    - `_handle_evaluate`: pass `per_mode=args.per_mode` to `evaluate_cohort`;
      when set, build the summary via `summarise_run_per_mode(cohort,
      run_id=args.run_id or cohort_id, metrics=metrics,
      run_manifest=run_manifest)` and thread it into both
      `build_evaluation_report` and `render_evaluation_report`.
    - New `compare-runs` subparser (`--run-a`, `--run-b`, `--out` required;
      `--run-a-id`, `--run-b-id`, `--build-date`, `--log-level` optional) and a
      `_handle_compare_runs` handler that reads both JSONs, rehydrates via
      `RunPerModeSummary.from_dict(report["per_mode_magnitude"])`, calls
      `compare_runs`, writes `<out>/per_mode_comparison.json` (via
      `write_evaluation_report`) and `<out>/per_mode_comparison.txt`, prints a
      one-line summary, and returns `0`; every `FacetInputError`, `OSError`,
      `json.JSONDecodeError` and missing-block case is caught and turned into
      `print(f"Error: {exc}", file=sys.stderr); return 1`. Heavy imports go
      inside the handler body, per the module's convention.

11. **Do NOT touch** `eval/per_mode.py`, `eval/metrics.py`, `eval/overlap.py`,
    `eval/severity_ladder.py`, `eval/calibrate.py`, `eval/cohort.py`,
    `heuristics/**`, `features/**`, `synth/**`, `report_schema_v0.json`,
    `pyproject.toml`, or `tests/corpus/**` (AC27).

## Testing Strategy

- **Framework:** `pytest`. Two new modules —
  `tests/test_101_per_mode_cohort.py` (the library: AC1-AC22, AC26-AC27) and
  `tests/test_101_compare_runs_cli.py` (AC23-AC25). No existing test module is
  modified.

- **Cost control.** Driving `evaluate_cohort` with `per_mode=True` runs the
  full Stage-2/3 pipeline per case. Build the two cohort evaluations **once**
  in a `@pytest.fixture(scope="module")` and assert every library AC against
  the cached result; construct `RunPerModeSummary`/`ModeDelta` objects
  **directly** (they are plain frozen dataclasses) for the pure-arithmetic ACs
  (AC7, AC10-AC15, AC17, AC18) so those tests never touch a label map. Keep the
  fixture cohort small — 3-4 cases from `tests/corpus` plus a
  `build_clean_spine()` control — not the full nine.

- **The AC16 demonstrator fixture (the load-bearing one).** Run A: candidates
  are `mode3_inject_islands`-style label maps (clean base + injected islands).
  Run B: the *same* candidates with every stray connected component stripped —
  the injected "post-processing step". Same `case_id`s, same GT, same config,
  same `expected`. Assert `attributed_mode == 3`, the direction, and the
  `|normalised_delta| > |mean_dice_delta|` contrast. Also assert the *negative*
  half explicitly: `mean_dice_delta` is small in absolute terms (a stated
  bound), so the test demonstrates the aggregate genuinely fails to attribute
  what the per-mode delta attributes.

- **AC1-AC2, AC6, AC19-AC20, AC27 (declarative surface)** — introspection:
  `__all__` contents and `segfacet.eval` re-export; `dataclasses.fields` and
  `FrozenInstanceError` on attempted assignment; the eight-entry mode-ordered
  tuple and its agreement with `PER_MODE_METRIC_SPECS`; both schemas' root
  keys, `const` versions, `required` lists and `additionalProperties`; and
  AC27's byte-identity hashes of the fenced files. **AC27's file list must be
  resolved relative to the test file** (`Path(__file__).resolve().parents[1]`),
  never as a literal absolute path — the exact defect item 099 shipped and had
  to hotfix on `main` (`insights.md`, 2026-07-26), which passed every local
  gate and failed all four CI legs.

- **AC9's drift guard** reads
  `Path(segfacet.eval.per_mode_cohort.__file__).read_text()` and asserts the
  absence of `compute_overlap`, of any `2 *` / `/ (a + b)`-shaped Dice
  expression, and of any re-derivation of a per-mode metric name.

- **AC3-AC5 (the harness hook)** — one test asserting the default-off
  behaviour, one asserting equality against an independently computed
  `compute_per_mode_metrics(...)`, one `monkeypatch`-based spy test counting
  `run_qc` and `compute_per_mode_metrics` invocations, and one candidate-less
  case asserting the exact `None`/non-`None` split across the eight modes.

- **AC7, AC10-AC15 (the arithmetic — the load-bearing tests)** — built on
  hand-constructed `ModeAggregate`/`RunPerModeSummary` objects with known
  numbers, so the assertions check arithmetic rather than the fixture. AC11
  parametrises the `scale == 0.0`, `value_a is None`, `value_b is None` and
  both-`None` branches. AC12 parametrises all four `(direction, sign)`
  combinations plus `delta == 0.0`. AC13 includes a deliberate exact tie
  between two modes and asserts the lower one wins. AC15 asserts both the
  raise-on-different-sets direction and the succeed-on-reordered-same-set
  direction.

- **AC17, AC18, AC21, AC26 (round-trip, JSON shape, bytes, purity)** —
  `json.loads(json.dumps(d)) == d` plus a recursive type walk (JSON-native
  types and `str` keys only, with an explicit `not isinstance(v, np.generic)`
  check); `from_dict(to_dict())` equality; two writes to two destinations
  compared with `read_bytes()`; pre/post `to_dict()` snapshots of every input
  to prove non-mutation; `monkeypatch`-based assertions that no `open`,
  `Path.write_bytes`, `time` or `datetime` is reached inside
  `summarise_run_per_mode`/`compare_runs`.

- **AC22-AC25 (rendering + CLI)** — AC22 asserts the mode name substring, the
  absence of the literal `"None"`, and the distinct all-zero wording. AC23-AC25
  drive `segfacet.cli.main(argv)` in-process with `tmp_path` outputs and
  `capsys`: the `--per-mode` on/off pair (including the byte-identity of the
  off-case JSON against a pre-101-shaped expectation), the full
  evaluate→evaluate→compare-runs chain, and each of the four error paths
  parametrised, asserting exit `1`, an `Error:`-prefixed stderr line, and that
  **no** output file was created.

- **Adversarial / edge cases:**
  - An **empty cohort** — `summarise_run_per_mode` returns eight aggregates
    with `n_cases == 0`, every statistic `None`, and `compare_runs` on two
    empty summaries returns `attributed_mode is None` with `passed`-shaped
    zero deltas, not an exception (so item 102 can call it defensively).
  - A cohort where **every** record's `per_mode` is `None` (the caller forgot
    the flag) — `FacetInputError` with a message naming `per_mode=True`, not
    eight silently empty aggregates.
  - A mode whose value is `None` in run A but a float in run B (a case gained a
    candidate) — `delta is None`, `normalised_delta is None`, `worsened is
    None`; the mode is excluded from `attributed_mode`, never treated as `0.0`.
  - `float("inf")`/`nan` never appear: assert `math.isfinite` on every non-
    `None` numeric in both `to_dict()`s.
  - `by_mode(0)` and `by_mode(9)` raise `KeyError` — mode `0`
    (`CLEAN_CONTROL_MODE`) is not a key of this surface, matching item 099.
  - `RunPerModeSummary.from_dict` on a truncated block (six entries), a block
    with a non-`str` `run_id`, and a block missing `case_ids` — each raises
    `FacetInputError`, never a bare `KeyError`/`TypeError`.
  - A comparison whose two runs have **identical** `run_id`s (comparing a
    cohort against itself under a different config) is allowed, not rejected.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate — **all are expected to stay green unmodified**; an edit to any of
  them is a red flag for the validator, because this item's every change is
  additive and default-off):
  - `tests/test_053_eval_harness.py` — the harness's own contract. Line 100
    asserts `set(harness_mod.__all__) >= {...}` (membership, so AC1's growth is
    free) and `test_ac12_to_dict_is_json_serialisable_and_deterministic`
    (line 482) checks `to_dict()` keys with `in` membership and explicit
    `is None` checks on `overlap`/`feature_match` — **not** an exhaustive key
    set, so the new `"per_mode": None` key does not break it. Re-verify at
    implementation time before assuming the field is free.
  - `tests/test_056_eval_report.py` — the eval report/schema. Line 271 pins
    `schema["properties"]["schema_version"]["const"] == "0.1"` and line 272
    uses `set(schema["required"]) >= {...}`; line 451 parametrises required-key
    deletion over exactly `["schema_version", "provenance", "metrics"]`. AC19's
    optional additive property leaves all three untouched — but if any
    assertion there has to move, the schema change is wrong, not the test.
  - `tests/test_057_evaluate_cli.py` — asserts `<out>/eval_report.json` exists
    and is schema-loadable (lines 255-380), including a byte-identity check
    between two `--out` directories (lines 379-380). With `--per-mode` off by
    default those bytes must not move; this is the sharpest regression signal
    in the suite for AC19/AC23 and must stay green untouched.
  - `tests/test_054_metrics.py`, `tests/test_050_overlap.py`,
    `tests/test_099_per_mode_metrics.py`, `tests/test_100_severity_ladder.py`
    — `eval/metrics.py`, `eval/overlap.py`, `eval/per_mode.py` and
    `eval/severity_ladder.py` are untouched (AC27). Item 100's AC26 already
    pins several of these files byte-for-byte; this item must not break that.
  - `tests/test_092_eval_reference_wiring.py`, `tests/test_055_calibrate.py`,
    `tests/test_087_dataset_cli.py`, `tests/test_088_stage13_acceptance.py` —
    all call `evaluate_case`/`evaluate_cohort` without the new keyword; the
    default `per_mode=False` must keep every one of them bit-for-bit identical.
  - `tests/test_075_cli_backend.py` — `SUBCOMMANDS` is a fixed three-element
    literal (line 50), so the fourth subcommand is out of its scope by
    construction. Confirm no other test enumerates the subcommand list
    exhaustively before landing `compare-runs`.
  - `tests/test_096_run_manifest.py` — the `run_manifest` block whose optional-
    additive-property precedent AC19 follows; line 129's exhaustive
    `set(d.keys()) ==` is on `RunManifest.to_dict()`, which this item does not
    change.
  - `tests/test_smoke.py` — `segfacet --help` must still exit 0 and mention
    `run`; a new subparser must not break parser construction.

## Validation

Beyond the unit suite, the point of this item is **a report a human reads that
attributes a behavioural change to a named failure mode**. Item 102 replays
this end to end; the builder/validator should observe it here first. From the
repo root with the venv bootstrapped, using any two directories of candidate
segmentations over the same cohort (the synthetic corpus is sufficient — build
a two-case manifest where run B's candidates are run A's with stray components
stripped):

```
.venv/bin/python -m segfacet.cli evaluate --cohort runA_cohort.json --out out/runA --per-mode --run-id runA --postproc-toggles {"strip_islands":false}
```
```
.venv/bin/python -m segfacet.cli evaluate --cohort runB_cohort.json --out out/runB --per-mode --run-id runB --postproc-toggles {"strip_islands":true}
```
```
.venv/bin/python -m segfacet.cli compare-runs --run-a out/runA/eval_report.json --run-b out/runB/eval_report.json --out out/compare
```

Confirm by inspection of `out/compare/per_mode_comparison.txt` that:

1. All eight §6 modes appear by **name**, each with its metric name, run-A
   mean, run-B mean, delta and normalised delta — no mode silently omitted.
2. The **attributed mode is named in words** and is the mode the injected
   change actually targets (mode 3 for island stripping), not "aggregate Dice"
   and not a mode nothing touched.
3. The aggregate `mean_dice` delta is printed **beside** it and is visibly
   small — this is the stage's thesis on one line, and the whole reason the
   report exists.
4. Mode 2 (`min_dominant_component_fraction`, the one `decreases` metric) is
   labelled improved/worsened the right way round. This is the single easiest
   thing to get backwards and the easiest to check by eye.
5. Both runs' `run_manifest` blocks appear in
   `out/compare/per_mode_comparison.json`, so the two sides are identified by
   their `postproc_toggles` rather than by filename.

Then confirm the guard rails by hand: rerun `compare-runs` with `--run-b`
pointing at a report built from a **different** cohort, and with `--run-b`
pointing at an `eval_report.json` written **without** `--per-mode`. Both must
exit `1` with a clear `Error:` line and write nothing.

No `[validation]` profile is required: this runs on the plain CPU venv with no
optional dependency. If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified.

## Dependencies

- **Item 050** (`eval/overlap.py::compute_overlap` and `OverlapResult`'s
  `mean_dice`/`volume_weighted_dice` aggregates, reached only indirectly
  through item 099's carried context) — ✅.
- **Item 053** (`eval/harness.py` — `EvaluationCase`, `CaseEvaluation`,
  `evaluate_case`, `evaluate_cohort`; the record this item extends and the
  cohort walk it hooks into) — ✅.
- **Item 054** (`eval/metrics.py` — `CohortMetrics` and `PerModeSensitivity`,
  the detection-rate column this item reads verbatim and does not duplicate) —
  ✅.
- **Item 056** (`eval/report.py` — `build_evaluation_report`,
  `serialize_evaluation_report_json`, `write_evaluation_report`,
  `render_evaluation_report`, `EvaluationProvenance` and
  `eval_report_schema_v0.json`; the reporting surface this item extends) — ✅.
- **Item 057** (`eval/cohort.py`'s manifest loader and the `segfacet evaluate`
  CLI handler this item adds `--per-mode` to) — ✅.
- **Item 096** (`segfacet.run_manifest` — the run-manifest provenance block
  that identifies each side of the comparison by segmenter version / SHA /
  `postproc_toggles`, and whose optional-additive-schema-property landing is
  the precedent AC19 follows) — ✅.
- **Item 098** (`stray_component_sizes` / `stray_component_count`, read
  indirectly through mode 3's metric — the metric the AC16 demonstrator
  exercises) — ✅.
- **Item 099** (`eval/per_mode.py` — `compute_per_mode_metrics`,
  `PerModeMetrics`, `PER_MODE_METRIC_SPECS`, the eight metric names,
  directions and baselines, and the per-case `mean_dice`/
  `volume_weighted_dice` context this item aggregates) — ✅.
- **Item 100** (`eval/severity_ladder.py` — the evidence that each metric moves
  monotonically with its own mode's severity, which is what makes a per-mode
  *delta* interpretable at all, plus the two recorded cross-mode couplings a
  reader of this report should know about) — ✅.

**Downstream:** item 102 (Stage 18 validation) replays this item's
`compare-runs` subcommand end to end on two runs of the same cohort and ticks
Stage 18's acceptance against it. It does not block this item.

## Decisions & Trade-offs

To be updated during implementation.
