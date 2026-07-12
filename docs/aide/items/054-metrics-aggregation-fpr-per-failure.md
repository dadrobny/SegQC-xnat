# Item 054 — Metrics aggregation: FPR, per-failure-mode sensitivity, DICE-vs-flag correlation

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (G3, G7)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 054
> **Objectives:** G3 (FPR-on-GT quantifies the "GT passes at a high rate / low
> FPR" acceptance); G7 (per-§6-mode sensitivity quantifies "injected failures are
> caught", and the DICE-vs-flag correlation quantifies "flag rate / feature
> divergence correlates with DICE")
> **Suggested branch:** `aide/054-metrics-aggregation-fpr-per-failure`

---

## Description

Consume the per-case evaluation records produced by item **053**'s harness (a
`CohortEvaluation` — a tuple of `CaseEvaluation` records, each bundling the
level-1 verdict `outcome` from item 052, the level-2 DICE `overlap` from item
050, and the level-3 `feature_match` divergence from item 051) and aggregate them
into the Stage-7 **cohort-level metrics**. This item is **pure aggregation over
already-computed records** — it runs no pipeline, loads no label maps, and does no
file I/O.

Deliver a pure module `segqc/eval/metrics.py` computing the three roadmap metrics:

1. **False-positive rate (FPR) on GT** — of the cases the ground truth expected to
   **pass** (the clean-GT / negative cases: `expected_failure is False`, i.e. the
   `TN + FP` set), the fraction the pipeline **wrongly flagged** (`FP`). This
   quantifies the roadmap's "GT passes at a high rate (low FPR)" (**G3**).

2. **Sensitivity per §6 failure mode** — for each catalogued failure mode present
   among the expected-failure cases, the fraction of that mode's cases the pipeline
   **caught by its designated rule** (`outcome.caught_by_designated_rule`), i.e.
   the per-mode recall of the *designated* Stage-4 rule; a coarse
   caught-at-all rate (`outcome.caught`) is reported alongside. This quantifies
   "injected failures are caught" per §6 mode (**G7**).

3. **DICE-vs-flag correlation** — a correlation coefficient across the cohort
   between each case's **DICE** (the level-2 `overlap` aggregate, when a candidate
   was present) and its **flag signal** (whether the case was flagged), plus a
   parallel **feature-divergence-vs-flag** correlation between the level-3
   case-level `feature_match.case_divergence` and the same flag signal. This
   quantifies "flag rate / feature divergence correlates with DICE" (**G7**).

The module emits a single serialisable `CohortMetrics` object carrying the
underlying **confusion counts** (`TP/FP/TN/FN`), the derived **rates** (FPR and
convenience overall recall / specificity), the **per-mode** breakdown (per-mode
`n_cases`, caught counts, and sensitivity), and the two **correlation results**
(each with its coefficient, method, sample size `n`, and the named variables).
All degenerate inputs (empty cohort, no negative cases, a requested mode with no
cases, zero-variance correlation inputs, cases without a candidate) resolve to
explicit sentinels (`None`) rather than a divide-by-zero or a crash.

**In scope:** `segqc/eval/metrics.py` containing the frozen result dataclasses
(`ConfusionCounts`, `PerModeSensitivity`, `CorrelationResult`, `CohortMetrics`)
and the `compute_cohort_metrics(...)` function; a re-export from
`segqc/eval/__init__.py`; and `tests/test_054_metrics.py`.

**Out of scope (do NOT):** run the pipeline, any rule, or any label-map / file
I/O (records arrive already computed from 053); classify a single case (item 052)
or compute per-case DICE / feature divergence (items 050 / 051) — this item only
*aggregates* the fields those already produced; sweep or select thresholds (item
055); render a JSON/human evaluation report or persist calibrated numbers into the
config / `progress.md` (item 056); add a `segqc evaluate` CLI or the Stage-7
acceptance suite (item 057); define or change the §6 failure-mode taxonomy, the
`Expectation`/manifest schema, the `CaseEvaluation`/`CaseOutcome`/`OverlapResult`/
`FeatureMatchResult` models, or any config (all consumed as-is from merged items).

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each in
`tests/test_054_metrics.py` (see Testing Strategy). Hand-built `CaseEvaluation` /
`CohortEvaluation` record sets with known properties supply every expected number._

- [ ] **AC1: module & public API exist.** `segqc.eval.metrics` exposes
  `compute_cohort_metrics(cohort, *, correlation_method="pearson",
  dice_metric="mean_dice", failure_modes=None) -> CohortMetrics` and the four
  frozen dataclasses `ConfusionCounts`, `PerModeSensitivity`, `CorrelationResult`,
  `CohortMetrics`; all five names are in the module `__all__` and importable both
  as `from segqc.eval.metrics import compute_cohort_metrics, CohortMetrics, ...`
  and (re-exported) `from segqc.eval import compute_cohort_metrics`. The
  dataclasses carry the fields documented in Assumptions (`ConfusionCounts`:
  `tp, fp, tn, fn`; `PerModeSensitivity`: `failure_mode, failure_mode_name,
  n_cases, n_caught, n_caught_by_designated_rule, sensitivity, caught_rate`;
  `CorrelationResult`: `coefficient, n, method, x_variable, y_variable`;
  `CohortMetrics`: `counts, false_positive_rate, sensitivity, specificity,
  per_mode, dice_vs_flag, feature_divergence_vs_flag, n_cases`) and are frozen.

- [ ] **AC2: confusion counts are aggregated correctly.** For a hand-built cohort
  containing a known mix of `Outcome.TRUE_POSITIVE` / `FALSE_POSITIVE` /
  `TRUE_NEGATIVE` / `FALSE_NEGATIVE` records, `result.counts` has the exact `tp`,
  `fp`, `tn`, `fn` counts, and `result.n_cases` equals the number of records.

- [ ] **AC3: FPR on GT is `FP / (FP + TN)`.** For a cohort whose expected-pass
  (negative) cases are `k` `TN` plus `m` `FP` records (and any number of
  expected-failure records), `result.false_positive_rate == m / (m + k)` (e.g. 1
  FP among 5 expected-pass cases → `0.2`), computed over the negative set only
  (expected-failure records do not affect it).

- [ ] **AC4: FPR sentinel when there are no expected-pass cases.** For a cohort
  containing only expected-failure records (no `TN`/`FP`, denominator `0`),
  `result.false_positive_rate is None` — an explicit sentinel, not a
  divide-by-zero error and not `0.0`.

- [ ] **AC5: per-mode sensitivity uses the designated-rule catch.** For a failure
  mode `m` with `n` expected-failure records of which `j` have
  `outcome.caught_by_designated_rule is True` and `c` have `outcome.caught is
  True`, that mode's `PerModeSensitivity` has `n_cases == n`,
  `n_caught_by_designated_rule == j`, `n_caught == c`, `sensitivity == j / n`
  (the primary per-mode metric, "caught by its designated rule"), and
  `caught_rate == c / n` (the coarse caught-at-all rate).

- [ ] **AC6: per-mode sentinel for a requested mode with no cases.** When
  `failure_modes` names a mode that appears in **no** record of the cohort, that
  mode's `PerModeSensitivity` has `n_cases == 0`, `n_caught == 0`,
  `n_caught_by_designated_rule == 0`, `sensitivity is None`, and `caught_rate is
  None` — no divide-by-zero.

- [ ] **AC7: per-mode grouping over observed modes when `failure_modes` is
  omitted.** With `failure_modes=None`, `result.per_mode` contains exactly one
  `PerModeSensitivity` per distinct `failure_mode` observed among the
  expected-failure records, ordered ascending by `failure_mode` (any expected-
  failure records whose `failure_mode is None` group into a single trailing entry
  with `failure_mode is None`); each entry's `failure_mode_name` is taken from the
  records of that mode; expected-pass records contribute to no per-mode entry.

- [ ] **AC8: DICE-vs-flag correlation has the expected (negative) sign and
  magnitude.** For a cohort where each case carries an `overlap` with a
  `mean_dice`, and lower DICE co-occurs with flagged and higher DICE with
  not-flagged (a monotone anti-correlation), `result.dice_vs_flag.coefficient` is
  negative and matches the hand-computed Pearson coefficient (to a documented
  tolerance); `result.dice_vs_flag.n` equals the number of contributing cases and
  `result.dice_vs_flag.method == "pearson"`, `x_variable == "mean_dice"`,
  `y_variable == "flagged"`.

- [ ] **AC9: correlation excludes cases without a usable DICE.** Cases whose
  `overlap is None` (no candidate present) or whose selected DICE value is `None`
  are omitted from the DICE-vs-flag correlation: `result.dice_vs_flag.n` counts
  only the usable pairs and the coefficient is computed over exactly those — a
  missing candidate is skipped, never an error.

- [ ] **AC10: correlation sentinel on degenerate input.** When fewer than two
  usable pairs exist, or the DICE values have zero variance (all equal), or the
  flag signal has zero variance (all flagged or all not flagged),
  `result.dice_vs_flag.coefficient is None` (with `n` still recorded) — no
  divide-by-zero and no `NaN`.

- [ ] **AC11: feature-divergence-vs-flag correlation has the expected (positive)
  sign.** For a cohort where higher `feature_match.case_divergence` co-occurs with
  flagged, `result.feature_divergence_vs_flag.coefficient` is positive and matches
  the hand-computed value; its `x_variable == "case_divergence"`,
  `y_variable == "flagged"`, and cases with `feature_match is None` or
  `case_divergence is None` are excluded from its `n`.

- [ ] **AC12: Spearman option computes a rank correlation.** With
  `correlation_method="spearman"`, both correlations are computed on
  average-ranked inputs; for a strictly monotone but non-linear DICE↔flag-adjacent
  relationship the Spearman coefficient reaches ±1 where the Pearson coefficient
  is strictly between 0 and ±1, and `result.dice_vs_flag.method == "spearman"`.
  `"pearson"` remains the default.

- [ ] **AC13: `dice_metric` selects which overlap aggregate is correlated.** With
  `dice_metric="volume_weighted_dice"`, the DICE-vs-flag correlation reads each
  case's `overlap.volume_weighted_dice` (not `mean_dice`) and
  `result.dice_vs_flag.x_variable == "volume_weighted_dice"`.

- [ ] **AC14: overall derived rates.** `result.sensitivity` equals the overall
  recall `TP / (TP + FN)` (over all expected-failure cases) and
  `result.specificity` equals `TN / (TN + FP)`; `specificity == 1 -
  false_positive_rate` when both are defined; each is `None` when its denominator
  is `0`.

- [ ] **AC15: empty cohort yields well-formed all-sentinel metrics.** For an empty
  `CohortEvaluation`, `result.n_cases == 0`, `counts` is all-zero,
  `false_positive_rate`/`sensitivity`/`specificity` are all `None`, `per_mode` is
  empty (or all-sentinel entries when `failure_modes` is supplied), and both
  correlation results have `coefficient is None` and `n == 0` — no crash.

- [ ] **AC16: `to_dict()` is JSON-serialisable and deterministic.**
  `CohortMetrics.to_dict()` returns a nested structure of plain JSON types (no
  tuples, enums, or dataclasses; `Outcome` reduced to its string, `None`
  sentinels preserved as JSON `null`) that round-trips through `json.dumps` /
  `json.loads`; two `compute_cohort_metrics` calls on the same cohort produce
  equal `CohortMetrics` and byte-identical `json.dumps(..., sort_keys=True)`
  output.

- [ ] **AC17: malformed arguments raise `SegQCInputError`.** An unrecognised
  `correlation_method` (not `"pearson"`/`"spearman"`) or an unrecognised
  `dice_metric` (not `"mean_dice"`/`"volume_weighted_dice"`) raises
  `segqc.io.SegQCInputError` with a clear message — not a raw `KeyError` /
  `ValueError` / `AttributeError`.

- [ ] **AC18: pure, deterministic, non-mutating.** `compute_cohort_metrics`
  performs no file I/O; the input `CohortEvaluation` and its `CaseEvaluation`
  records are unchanged after the call (identity/equality preserved); repeated
  calls return equal results.

## Assumptions  <!-- MANDATORY: clarify mode = assume -->

- **Input is a `CohortEvaluation` (item 053), consumed read-only and duck-typed
  (clarify `assume`).** The queue says "consume the harness records (053)". The
  function takes a `CohortEvaluation` (its `.cases` tuple of `CaseEvaluation`
  records is the aggregation domain); it reads only, via the already-merged record
  fields, and is duck-typed on `.cases` so a plain sequence of `CaseEvaluation`-
  shaped records also works (eases testing). Each record's read fields are:
  `outcome.outcome: Outcome`, `outcome.expected_failure: bool`,
  `outcome.actual_flagged: bool`, `outcome.caught: Optional[bool]`,
  `outcome.caught_by_designated_rule: bool`, `outcome.failure_mode: Optional[int]`,
  `outcome.failure_mode_name: Optional[str]`; `overlap: Optional[OverlapResult]`
  with `.mean_dice` / `.volume_weighted_dice`; `feature_match:
  Optional[FeatureMatchResult]` with `.case_divergence`. If any of these field
  names/types has diverged from the merged 050/051/052/053 code, the
  builder/validator should hand back.

- **"Clean-GT / negative" ≡ `expected_failure is False`; FPR = `FP / (FP + TN)`
  (clarify `assume`).** The roadmap phrase "GT passes at a high rate (low FPR)"
  defines the FPR denominator as the cases the ground truth expected to pass — the
  negative set. Using `outcome.expected_failure` (item 052's authoritative binary,
  already reduced at the harness's `positive_severity`) rather than re-deriving
  from `failure_mode` keeps the definition consistent with 052's classification
  and correct even for a plain VerSe pass expectation that carries no §6 mode. FPR
  is `None` when there are no negative cases (AC4).

- **Per-mode sensitivity is "caught **by the designated rule**"; coarse
  caught-at-all is reported alongside (clarify `assume`).** The queue says
  "fraction of each mode's cases caught by its designated rule", so the primary
  `sensitivity = n_caught_by_designated_rule / n_cases` uses item 052's strict
  `outcome.caught_by_designated_rule`. Because that signal is meaningful only for
  failure cases, per-mode aggregation is taken over **expected-failure** records
  only (`expected_failure is True`); expected-pass records never enter a per-mode
  denominator. The coarser `caught_rate = n_caught / n_cases` (using
  `outcome.caught`, "was the failure raised at all") is reported too, since it is a
  useful, cheap secondary that the report (056) may surface. A mode with
  `n_cases == 0` yields `sensitivity`/`caught_rate == None` (AC6).

- **Per-mode grouping key + the `failure_modes` parameter (clarify `assume`).**
  Grouping is by `outcome.failure_mode` (the §6 integer key, `1..8`; `0` is the
  clean control which is an expected-pass case and so never a per-mode positive).
  To avoid coupling `segqc.eval` to `segqc.synth` (mirroring the 050/051/052
  decoupling — `outcome.failure_mode` is already carried through as plain
  metadata), the taxonomy is **not** imported here. When `failure_modes` is
  `None` (default) the result reports one entry per distinct mode **observed**
  among the expected-failure records, ordered ascending by mode key (a trailing
  `None`-mode entry collects expected-failure records with no §6 metadata). When
  `failure_modes` is supplied — a sequence of ints, or a mapping `{int:
  name}` — the result reports exactly one entry per requested mode in the given
  order (a sentinel entry for a requested mode absent from the cohort, AC6),
  letting item 057 pass the full §6 catalogue
  (`segqc.synth.perturbation.FAILURE_MODE_NAMES`) to force all 8 modes to appear
  without this module depending on it.

- **DICE-vs-flag correlation: continuous DICE vs a binary flag indicator; Pearson
  default (clarify `assume`).** The x-variable is the case's overlap DICE
  aggregate selected by `dice_metric` (default `"mean_dice"`; `"volume_weighted_
  dice"` also accepted). The y-variable ("whether … it was flagged") is a binary
  indicator `1.0 if outcome.actual_flagged else 0.0` — a Pearson correlation of a
  continuous variable with a 0/1 indicator is the point-biserial correlation,
  which directly measures "flag rate tracks DICE". Only cases with a usable DICE
  (`overlap is not None` **and** the selected value is not `None`) contribute; the
  paired flag comes from the same record. A **parallel** correlation,
  `feature_divergence_vs_flag`, uses `feature_match.case_divergence` as its
  x-variable against the same binary flag, covering the roadmap's "feature
  divergence correlates with DICE" arm (higher divergence ⇒ more likely flagged ⇒
  positive coefficient). A graded/severity-weighted flag signal is deliberately
  out of scope for this item.

- **Correlation is computed in-module with explicit sentinels; no `NaN` escapes
  (clarify `assume`).** Pearson is computed directly (covariance over the product
  of standard deviations) using `numpy` (already a core dependency, used by the
  sibling primitives); Spearman is the same computation applied to average-ranked
  inputs (ties share the mean rank). The coefficient is `None` (the sentinel) when
  fewer than two usable pairs exist **or** either variable has zero variance
  (all-equal DICE, or all/none flagged) — this is checked explicitly so no
  divide-by-zero and no `NaN` is ever returned (AC10). `scipy.stats.pearsonr`/
  `spearmanr` are intentionally **not** used, to keep the sentinel behaviour
  under this module's control and avoid their p-value / constant-input warnings.

- **`CorrelationResult` records `n` and the named variables; `CohortMetrics`
  also carries convenience overall rates.** Each correlation reports its sample
  size `n`, `method`, and the `x_variable`/`y_variable` names for provenance in
  the report (056). Beyond the three roadmap metrics, `CohortMetrics` carries the
  overall recall (`sensitivity = TP/(TP+FN)`) and `specificity = TN/(TN+FP)` as
  convenience derived rates (`specificity == 1 − FPR`); these are cheap, standard,
  and useful to the report, and each is `None` when its denominator is `0`.

- **Interface pins (dependencies already ✅).** From item 053
  `segqc.eval.harness`: `CohortEvaluation` (`.cases: Tuple[CaseEvaluation, ...]`)
  and `CaseEvaluation` (`.outcome`, `.overlap`, `.feature_match`,
  `.candidate_present`). From item 052 `segqc.eval.outcome`: `CaseOutcome`
  (`.outcome`, `.expected_failure`, `.actual_flagged`, `.caught`,
  `.caught_by_designated_rule`, `.failure_mode`, `.failure_mode_name`) and
  `Outcome` (`TRUE_POSITIVE`/`FALSE_POSITIVE`/`TRUE_NEGATIVE`/`FALSE_NEGATIVE`,
  `.label`). From item 050 `segqc.eval.overlap`: `OverlapResult` (`.mean_dice`,
  `.volume_weighted_dice`, both `Optional[float]`). From item 051
  `segqc.eval.feature_match`: `FeatureMatchResult` (`.case_divergence:
  Optional[float]`). From item 003 `segqc.io`: `SegQCInputError` (reused
  malformed-input error type, as in 050/051/052/053). The §6 mode integers
  (`0` = clean control, `1..8` = failure modes) come from item 036
  `FAILURE_MODE_NAMES` but are consumed only as plain ints carried on
  `CaseOutcome.failure_mode` — not imported. If any of these has diverged, hand
  back.

## Implementation Steps

Code path in `src/segqc/` (`aide.toml` `source_dir = src/segqc`).

1. **`src/segqc/eval/metrics.py` — module docstring + imports.** Docstring
   stating: Stage-7 cohort-level aggregation of item 053 records; pure, no
   pipeline/no I/O; the three metrics (FPR on GT, per-§6-mode sensitivity,
   DICE-vs-flag + feature-divergence-vs-flag correlation) plus counts and
   convenience rates; sentinel (`None`) semantics for all degenerate inputs;
   decoupling from `segqc.synth` (mode keys consumed as plain ints). Import
   `dataclasses`, `enum`/typing helpers, `numpy`, `Outcome` from
   `segqc.eval.outcome`, and `SegQCInputError` from `segqc.io`. Declare
   `__all__ = ["compute_cohort_metrics", "ConfusionCounts",
   "PerModeSensitivity", "CorrelationResult", "CohortMetrics"]`.

2. **`ConfusionCounts` frozen dataclass** — `tp, fp, tn, fn: int`; optional
   convenience properties (`n_total`, `n_expected_pass = tn + fp`,
   `n_expected_fail = tp + fn`).

3. **`PerModeSensitivity` frozen dataclass** — `failure_mode: Optional[int]`,
   `failure_mode_name: Optional[str]`, `n_cases: int`, `n_caught: int`,
   `n_caught_by_designated_rule: int`, `sensitivity: Optional[float]`,
   `caught_rate: Optional[float]`.

4. **`CorrelationResult` frozen dataclass** — `coefficient: Optional[float]`,
   `n: int`, `method: str`, `x_variable: str`, `y_variable: str`.

5. **`CohortMetrics` frozen dataclass** — `counts: ConfusionCounts`,
   `false_positive_rate: Optional[float]`, `sensitivity: Optional[float]`,
   `specificity: Optional[float]`, `per_mode: Tuple[PerModeSensitivity, ...]`,
   `dice_vs_flag: CorrelationResult`,
   `feature_divergence_vs_flag: CorrelationResult`, `n_cases: int`; plus a
   `to_dict()` returning nested plain-JSON types (reduce each dataclass with
   `dataclasses.asdict`, coerce tuples→lists, preserve `None`; mirror
   `harness._tuples_to_lists`'s approach for JSON-round-trip stability).

6. **Confusion counting.** A helper that walks the records once and tallies
   `tp/fp/tn/fn` by `record.outcome.outcome` (`Outcome` member), building
   `ConfusionCounts`.

7. **FPR + overall rates.** `false_positive_rate = fp / (fp + tn)` if
   `(fp + tn) > 0` else `None`; `sensitivity = tp / (tp + fn)` if `(tp + fn) > 0`
   else `None`; `specificity = tn / (tn + fp)` if `(tn + fp) > 0` else `None`.

8. **Per-mode aggregation.** Collect expected-failure records
   (`record.outcome.expected_failure is True`) grouped by
   `record.outcome.failure_mode`. Determine the reported mode set: from
   `failure_modes` (sequence of ints or `{int: name}` mapping) in given order, or,
   when `None`, the distinct observed keys sorted ascending (a `None` key sorts
   last). For each reported mode: `n_cases` = records of that mode,
   `n_caught` = those with `outcome.caught is True`,
   `n_caught_by_designated_rule` = those with
   `outcome.caught_by_designated_rule is True`,
   `sensitivity = n_caught_by_designated_rule / n_cases` (or `None` if
   `n_cases == 0`), `caught_rate = n_caught / n_cases` (or `None`);
   `failure_mode_name` from the mapping if supplied, else from a record of that
   mode, else `None`.

9. **Correlation helper `_correlate(xs, ys, method, x_name, y_name)
   -> CorrelationResult`.** Drop index-aligned pairs where `x is None`; require
   `len >= 2`; for `"spearman"` replace `xs`/`ys` with average ranks; compute
   Pearson `cov / (std_x * std_y)` via `numpy`; return `coefficient=None` when
   `n < 2` or `std_x == 0` or `std_y == 0`; else the float coefficient. Record
   `n` = number of usable pairs, `method`, `x_variable`, `y_variable`.

10. **Build the two correlations.** For each record compute the flag indicator
    `1.0 if record.outcome.actual_flagged else 0.0`. DICE series: the selected
    `overlap.<dice_metric>` (`None` when `overlap is None`). Feature series:
    `feature_match.case_divergence` (`None` when `feature_match is None`). Call
    `_correlate` for each (x_variable = the dice metric name / `"case_divergence"`,
    y_variable = `"flagged"`).

11. **`compute_cohort_metrics(cohort, *, correlation_method="pearson",
    dice_metric="mean_dice", failure_modes=None)`.** Validate
    `correlation_method ∈ {"pearson", "spearman"}` and `dice_metric ∈
    {"mean_dice", "volume_weighted_dice"}`, raising `SegQCInputError` otherwise.
    Read `records = tuple(cohort.cases)` (duck-typed). Run steps 6–10 and assemble
    the `CohortMetrics` (`n_cases = len(records)`). Never mutate the inputs; no
    file access anywhere in the module.

12. **`src/segqc/eval/__init__.py` — re-export.** Add
    `from .metrics import (compute_cohort_metrics, ConfusionCounts,
    PerModeSensitivity, CorrelationResult, CohortMetrics)`, extend `__all__`, and
    update the package docstring to mention the cohort-metrics aggregation
    alongside the primitives and the harness.

## Testing Strategy

One focused test per AC in **`tests/test_054_metrics.py`**. Build inputs bottom-up
from real merged dataclasses with a tiny in-test factory, with **no** pipeline,
loader, NIfTI, or disk fixtures:

- a `_case(outcome_kwargs, dice=None, divergence=None)` helper that constructs a
  `segqc.eval.outcome.CaseOutcome` (all fields set explicitly), wraps a
  `segqc.eval.overlap.OverlapResult` (only the `mean_dice`/`volume_weighted_dice`
  fields matter — `per_label=()`, counts `0`) when `dice is not None`, wraps a
  `segqc.eval.feature_match.FeatureMatchResult` (`case_divergence=divergence`,
  `per_label=()`) when `divergence is not None`, and returns a
  `segqc.eval.harness.CaseEvaluation`; and a `_cohort(cases)` making a
  `CohortEvaluation`. Every expected count/rate/coefficient is hand-computed.

- **AC1** — import the five names from `segqc.eval.metrics` and (the function)
  from `segqc.eval`; assert each dataclass is frozen and exposes the documented
  fields.
- **AC2** — a cohort with a known TP/FP/TN/FN mix; assert `counts` and `n_cases`.
- **AC3** — 5 expected-pass cases (4 TN + 1 FP) plus some failures; assert
  `false_positive_rate == 0.2`.
- **AC4** — cohort of only expected-failure cases; assert `false_positive_rate is
  None`.
- **AC5** — a mode with `n=4`, `j=3` designated-caught, `c=4` caught-at-all;
  assert `sensitivity == 0.75`, `caught_rate == 1.0`, and the three counts.
- **AC6** — `failure_modes=[7]` with no mode-7 records; assert that entry has
  `n_cases == 0`, `sensitivity is None`, `caught_rate is None`.
- **AC7** — records across modes `{1, 2, None}` with `failure_modes=None`; assert
  one entry per mode, ordered `1, 2, None` (None last), correct partitioned
  counts, and expected-pass records excluded.
- **AC8** — 4 cases: `(dice=0.2, flagged), (0.3, flagged), (0.9, not), (0.95,
  not)`; assert `dice_vs_flag.coefficient` < 0, matches the hand-computed Pearson
  value (abs tol `1e-9`), `n == 4`, `method == "pearson"`, `x_variable ==
  "mean_dice"`, `y_variable == "flagged"`.
- **AC9** — the AC8 cohort plus two cases with `overlap is None`; assert
  `dice_vs_flag.n == 4` (the None-overlap cases skipped) and the coefficient
  unchanged.
- **AC10** — (a) a single usable pair → `coefficient is None`, `n == 1`; (b) all
  DICE equal → `None`; (c) all cases flagged (zero-variance flag) → `None`.
- **AC11** — cases with rising `case_divergence` co-occurring with flagged; assert
  `feature_divergence_vs_flag.coefficient` > 0, `x_variable == "case_divergence"`,
  and a `feature_match is None` case is excluded from its `n`.
- **AC12** — a strictly-monotone-but-non-linear DICE↔flag arrangement; assert
  `spearman` coefficient magnitude `== 1.0` (± tol) while `pearson` on the same
  data is strictly < 1 in magnitude; `method == "spearman"`.
- **AC13** — `dice_metric="volume_weighted_dice"` with cases whose two DICE
  aggregates differ; assert the correlation uses the volume-weighted values and
  `x_variable == "volume_weighted_dice"`.
- **AC14** — a mix giving known `TP/FN` and `TN/FP`; assert `sensitivity ==
  TP/(TP+FN)`, `specificity == TN/(TN+FP)`, and `specificity == 1 - fpr`; a cohort
  with no failures → `sensitivity is None`.
- **AC15** — empty cohort; assert all-zero counts, `None` rates, empty `per_mode`,
  both correlations `coefficient is None` / `n == 0`, `n_cases == 0`.
- **AC16** — `to_dict()` contains only plain types; `json.loads(json.dumps(d)) ==
  d`; two runs give equal metrics and identical `json.dumps(..., sort_keys=True)`.
- **AC17** — `compute_cohort_metrics(cohort, correlation_method="kendall")` and
  `compute_cohort_metrics(cohort, dice_metric="jaccard")` each
  `pytest.raises(SegQCInputError)`.
- **AC18** — deep-copy/snapshot the cohort, call, assert the cohort and its
  records are unchanged (equality) and a second call returns an equal result.

Adversarial / edge cases folded in: a mode where all cases were caught by an
*incidental* rule (`caught is True` but `caught_by_designated_rule is False`) →
`caught_rate == 1.0` but `sensitivity == 0.0` (the designated-rule strictness is
visible); an expected-failure record with `failure_mode is None` → grouped into
the trailing `None` entry and still counted in overall recall; a cohort with
candidates but every DICE identical → DICE correlation `None` while feature
correlation may still be defined; negative/`>1` sentinel DICE never occurs
(records come from 050, bounded `[0, 1]`), so no clamping needed.

## Dependencies

- **Item 053 (✅)** — `segqc.eval.harness`: `CohortEvaluation` / `CaseEvaluation`
  — the record container and per-case record this item aggregates.
- **Item 052 (✅)** — `segqc.eval.outcome`: `CaseOutcome` (`.outcome`,
  `.expected_failure`, `.actual_flagged`, `.caught`, `.caught_by_designated_rule`,
  `.failure_mode`, `.failure_mode_name`) and `Outcome` — the per-case
  verdict-outcome substrate for counts / FPR / per-mode sensitivity.
- **Item 050 (✅)** — `segqc.eval.overlap`: `OverlapResult` (`.mean_dice`,
  `.volume_weighted_dice`) — the DICE aggregate for the DICE-vs-flag correlation.
- **Item 051 (✅)** — `segqc.eval.feature_match`: `FeatureMatchResult`
  (`.case_divergence`) — the case-level divergence for the
  feature-divergence-vs-flag correlation.
- **Item 003 (✅)** — `segqc.io`: `SegQCInputError` (reused malformed-input type).
- **Item 036 (✅)** — the §6 failure-mode integer keys (`FAILURE_MODE_NAMES`,
  `0` = clean control, `1..8` = modes) are the values carried on
  `CaseOutcome.failure_mode`; consumed as plain ints, **not** imported (item 057
  may pass the catalogue in via `failure_modes`).
- Items **055 / 056 / 057** depend on this module (calibration reads back these
  metrics; the report renders them; integration asserts them) — not the reverse.

## Decisions & Trade-offs

To be updated during implementation.
