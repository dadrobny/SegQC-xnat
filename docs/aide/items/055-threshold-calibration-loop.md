# Item 055 — Threshold-calibration loop

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (*Phase 1 complete*)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 055
> **Objectives:** G3 (distinguish failure from variation — low FPR on GT), G7 (evaluable / regression-testable)
> **Suggested branch:** `aide/055-threshold-calibration-loop`

---

## Description

Add the **threshold-calibration loop** as a new pure module
`src/segqc/eval/calibrate.py`. It is a reproducible routine that, given a fixed
evaluation cohort and a documented sweep over one or more heuristic thresholds,
re-runs the already-merged harness (item 053, `evaluate_cohort`) + metrics
(item 054, `compute_cohort_metrics`) at **each** candidate threshold setting,
scores each setting against an explicit **calibration objective**, and
**selects** the setting that best satisfies that objective.

This is a *calibration loop*, not a bare sweep utility. It must:

1. **Define a sweepable threshold/config-parameter space** — a `ThresholdAxis`
   naming a config parameter (a rule's `params` path) and its candidate values,
   with pure application onto an immutable `HeuristicConfig`.
2. **Enumerate the grid** — the deterministic Cartesian product of the axes.
3. **For each grid point**, build a modified config, run `evaluate_cohort` then
   `compute_cohort_metrics`.
4. **Score** each candidate against a documented objective (default: *minimise
   FPR on GT subject to a per-mode-sensitivity floor* — i.e. catch every §6
   failure mode present in the cohort while keeping ground-truth false positives
   as low as possible).
5. **Select and report** the best feasible candidate together with the metrics
   it achieved, or report **"no feasible setting"** when the objective cannot be
   met — never crash.

The parameters swept are the Stage-4 level-aware bounds
(`segqc.heuristics.bounds`, e.g. `rules.bounds.params.<group>.<min|max>_*`) and
the Stage-6 delta-to-reference thresholds (`segqc.heuristics.reference_delta`,
e.g. `rules.reference_delta.params.max_robust_z` /
`max_distribution_distance`), all read from the versioned
`HeuristicConfig` (`segqc.config`). A documented default grid over both rule
families is provided (`default_calibration_axes()`), but the loop is generic
over any caller-supplied axes.

**This item PROPOSES and RECORDS — it does not persist.** It returns the chosen
thresholds (as a re-applyable assignment) and their metrics; it does **not**
mutate the shipped `default_config.yaml`, the base config passed in, or
`progress.md`. Writing the chosen values into the config and rendering the
report is item **056**; the `segqc evaluate` entry point is item **057**.

**Out of scope (fenced):** no new metrics maths (reuse 054), no pipeline or
rule changes, no file I/O / label-map loading of its own beyond what 053 does
per case, no report rendering, no CLI, no config persistence, no `progress.md`
edits.

## Acceptance Criteria

- [ ] **AC1: `ThresholdAxis` defines a sweepable parameter.** A frozen
  `ThresholdAxis` carries a display `name`, a target `rule_id`, a `param_path`
  (tuple of nested keys within that rule's `params` dict), and an ordered
  non-empty tuple of candidate `values`. Constructing one with an empty
  `param_path` or empty `values` raises `segqc.io.SegQCInputError`.

- [ ] **AC2: Applying an axis produces a new config with the nested param set.**
  A helper (e.g. `apply_assignment(base_config, assignment)`) returns a
  `HeuristicConfig` in which each axis's `rules[rule_id]["params"][*param_path]`
  equals the assigned candidate value (creating intermediate `rules`/`params`/
  nested dicts as needed), while every other config field is preserved. For a
  bounds axis with `param_path=("lumbar", "max_volume_mm3")`, the resulting
  config, when read via `config.rule_param("bounds", "lumbar", {})`, yields a
  group dict whose `max_volume_mm3` is the assigned value.

- [ ] **AC3: Application never mutates the base config.** `apply_assignment`
  leaves the input `base_config` and its `rules` dict unchanged (deep) — the
  returned config is a distinct object; repeated application with different
  values off the same base yields independent configs (no shared nested state).

- [ ] **AC4: The grid is the deterministic Cartesian product of the axes.** For
  N axes with `k_i` values each, enumeration yields exactly `∏ k_i` candidate
  assignments, in a documented deterministic order (axes in given order,
  values in each axis's given order, last axis varying fastest). An empty axis
  sequence yields exactly one candidate: the empty assignment (the base config
  unchanged).

- [ ] **AC5: Each candidate is evaluated via 053 + 054.** For every grid point,
  `calibrate_thresholds` builds the modified config, calls
  `evaluate_cohort(cases, modified_config, ...)` then
  `compute_cohort_metrics(...)`, and records a `CandidateResult` carrying the
  assignment, the resulting `CohortMetrics`, its feasibility flag, and its
  objective score. `result.candidates` has one entry per grid point in grid
  order.

- [ ] **AC6: The objective classifies feasibility.** With the default objective
  (minimise FPR subject to `sensitivity_floor` on every per-mode sensitivity
  that has cases), a candidate whose every reported per-mode sensitivity
  (for modes with `n_cases > 0`) is `>= sensitivity_floor` is marked
  `feasible=True`; a candidate that misses the floor on any such mode is marked
  `feasible=False`.

- [ ] **AC7: Selection recovers a known separating threshold.** On a synthetic
  cohort constructed so that only a bounded sub-range of an axis's values both
  catches the injected failure(s) and passes the clean-GT case(s),
  `calibrate_thresholds` selects a `best` candidate whose assignment lies in
  that expected range and whose metrics satisfy the objective (feasible, minimal
  FPR).

- [ ] **AC8: Among feasible candidates the minimum-FPR one is chosen.** When
  more than one candidate is feasible, `result.best` is the feasible candidate
  with the lowest `false_positive_rate` (treating `None` FPR — no expected-pass
  cases — per the documented rule in Assumptions).

- [ ] **AC9: Ties break deterministically.** When two feasible candidates tie on
  FPR, `best` is chosen by a documented, stable secondary key (higher overall
  `sensitivity`, then earliest grid order), so the choice is reproducible.

- [ ] **AC10: Infeasible objective is reported, not crashed.** When no candidate
  meets the objective, `calibrate_thresholds` returns a result with
  `best is None` and `feasible is False` and an explicit machine-readable
  `status`/reason string (e.g. `"no-feasible-setting"`), without raising.

- [ ] **AC11: The loop is deterministic.** Two calls with the same cohort,
  axes, objective, and options return equal results — same `best.assignment`,
  same selected metrics, and byte-identical `to_dict()` JSON serialisation
  across repeated runs.

- [ ] **AC12: The result is well-formed and consumable by the recording step.**
  `CalibrationResult.to_dict()` returns a JSON-serialisable nested dict that
  round-trips byte-identically through `json.dumps`/`json.loads` (no enum,
  tuple, or dataclass survives), and `result.best.assignment` re-applied via
  `apply_assignment(base_config, ...)` reproduces the exact config that
  produced `result.best.metrics` (round-trip: chosen assignment → config →
  metrics equal to the recorded metrics).

- [ ] **AC13: A documented default grid over both rule families is provided.**
  `default_calibration_axes()` returns a tuple of `ThresholdAxis` covering at
  least one Stage-6 `reference_delta` threshold (`max_robust_z` and/or
  `max_distribution_distance`) and at least one Stage-4 `bounds` threshold,
  each with documented candidate values; the returned axes are valid inputs to
  `calibrate_thresholds` (grid enumerates and evaluates without error on a
  cohort).

- [ ] **AC14: A grid-size guard prevents runaway sweeps.** `calibrate_thresholds`
  accepts a `max_grid_size` (documented default) and raises
  `segqc.io.SegQCInputError` when `∏ k_i` exceeds it, before running any
  evaluation.

- [ ] **AC15: The shipped config and inputs are not persisted or mutated.**
  Running `calibrate_thresholds` does not write to disk, does not modify
  `default_config.yaml`, and does not mutate the passed-in `base_config`,
  `cases`, or `axes` (verified by equality before/after).

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume` (per `aide.toml`); the queued one-liner left several
design points open. Defaults taken (validator to surface):

- **Objective = minimise FPR subject to a per-mode-sensitivity floor.** The
  roadmap Stage-7 acceptance wording is "GT passes at a high rate (low FPR)"
  (G3) *and* "injected failures are caught" (G7); queue-006 item 055 gives the
  example objective "minimise FPR on GT subject to a per-mode-sensitivity floor
  / catching all §6 modes." Default `sensitivity_floor = 1.0` (catch every mode
  present). The objective is a documented `CalibrationObjective` dataclass
  (fields: `sensitivity_floor: float`, and the direction "minimise FPR"), passed
  as a parameter with this default, so item 057 can tune it without code change.
- **Sensitivity used for the floor is the strict per-mode
  `sensitivity`** (`n_caught_by_designated_rule / n_cases`, item 054's
  `PerModeSensitivity.sensitivity`), not the coarse `caught_rate`. Modes with
  `n_cases == 0` (`sensitivity is None`) are **excluded** from the floor check
  (a mode with no cases cannot be missed).
- **`None` FPR handling in selection.** A candidate whose cohort has no
  expected-pass cases has `false_positive_rate is None` (item 054). For
  ordering, `None` FPR sorts as **best/lowest** (there were no GT cases to
  falsely flag); documented so tests are unambiguous. Cohorts used to exercise
  selection (AC7/AC8) include ≥1 expected-pass case so FPR is a real number.
- **Config-parameter addressing.** A `ThresholdAxis` targets a rule's `params`
  via `(rule_id, param_path)`, matching how the rules read config:
  `bounds` reads a per-group dict via `config.rule_param("bounds", group, {})`
  then `[min|max]_*` keys, so `param_path=(group, key)`;
  `reference_delta` reads flat keys via
  `config.rule_param("reference_delta", key, ...)`, so `param_path=(key,)`.
  This is verified against the merged `bounds.py`/`reference_delta.py` at build
  time; the builder/validator hand back if those readers diverged.
- **Modified config built with `dataclasses.replace`.** `HeuristicConfig` is a
  frozen dataclass whose `rules` is a plain dict; the modified config is
  `dataclasses.replace(base_config, rules=deep_copied_and_updated_rules)`, all
  other fields carried through unchanged. No new fields added to
  `HeuristicConfig`.
- **Metrics options pass-through.** `calibrate_thresholds` accepts and forwards
  `positive_severity` (to `evaluate_cohort`) and `correlation_method`,
  `dice_metric`, `failure_modes` (to `compute_cohort_metrics`) with the same
  defaults those functions declare, so calibration scores the same numbers the
  rest of Stage 7 reports.
- **`default_calibration_axes()` values are placeholders, documented as such.**
  They give a runnable, documented default grid; the concrete production grid is
  the caller's (item 057) concern. Exact candidate values are a builder
  decision recorded in Decisions & Trade-offs.
- **`CandidateResult.assignment` is a plain JSON-friendly mapping** of axis
  `name → value`; `CandidateResult` also stores each axis's `(rule_id,
  param_path)` (or the axes are re-passed) so the assignment is re-applyable by
  `apply_assignment`. No live `HeuristicConfig` object is stored on the
  serialisable result.

## Implementation Steps

Code path: **`src/segqc/eval/calibrate.py`** (new module), exported from
`src/segqc/eval/__init__.py`.

1. **Module docstring** in the style of `harness.py`/`metrics.py`: state it is
   the Stage-7 calibration loop over 053+054, that it proposes-not-persists,
   and its dependencies (053, 054, config, bounds, reference_delta).
2. **`ThresholdAxis`** — frozen dataclass `(name: str, rule_id: str,
   param_path: Tuple[str, ...], values: Tuple[Any, ...])`. Validate non-empty
   `param_path` and `values` in `__post_init__`, raising `SegQCInputError`
   (coerce list inputs to tuples for immutability/hashing).
3. **`apply_assignment(base_config, assignment, axes)`** (or fold axis metadata
   into the assignment) → deep-copy `base_config.rules`, and for each
   `(axis, value)` descend/create `rules[rule_id]["params"][param_path...]` and
   set the leaf; return `dataclasses.replace(base_config, rules=new_rules)`.
   Pure; never mutate inputs.
4. **`_enumerate_grid(axes)`** → deterministic Cartesian product
   (`itertools.product` over `axis.values` in axis order) yielding ordered
   assignment mappings; empty axes → single empty assignment.
5. **`CalibrationObjective`** — frozen dataclass `(sensitivity_floor: float =
   1.0)` with a method `evaluate(metrics) -> (feasible: bool, score: float)`
   implementing "feasible iff every per-mode `sensitivity` with `n_cases>0`
   `>= floor`; score = `false_positive_rate` (None→ -inf sentinel for
   ordering)". Keep the score/ordering rule documented and centralised.
6. **`CandidateResult`** — frozen dataclass `(assignment, metrics: CohortMetrics,
   feasible: bool, score, ...axis addressing...)` with `to_dict()` reusing the
   `_tuples_to_lists` pattern and `metrics.to_dict()`.
7. **`CalibrationResult`** — frozen dataclass `(candidates: Tuple[...],
   best: Optional[CandidateResult], feasible: bool, status: str,
   objective, n_candidates)` with a JSON-serialisable `to_dict()`.
8. **`calibrate_thresholds(cases, base_config, axes, *, objective=..., max_grid_size=...,
   positive_severity=..., correlation_method=..., dice_metric=..., failure_modes=...)`**:
   validate `∏ k_i <= max_grid_size` (else `SegQCInputError`); enumerate grid;
   per candidate build config (step 3), `evaluate_cohort` → `compute_cohort_metrics`,
   score via objective; collect `CandidateResult`s; select `best` = min-score
   feasible candidate with the documented tie-break; set `status`
   (`"ok"` / `"no-feasible-setting"`).
9. **`default_calibration_axes()`** → tuple of documented axes over
   `reference_delta` (`max_robust_z`, `max_distribution_distance`) and `bounds`
   (a representative `[min|max]_*` per group), values documented inline.
10. **Export** the public names from `segqc/eval/__init__.py` and extend its
    `__all__` + module docstring, mirroring how 053/054 were added.

## Testing Strategy

New test module: **`tests/test_055_calibrate.py`** (mirrors
`tests/test_053_eval_harness.py` / `tests/test_054_metrics.py`). One focused
test per AC plus adversarial/edge cases. Prefer tiny synthetic cohorts built
from bare `ndarray` seg maps (the harness `_resolve_seg` accepts `ndarray` +
`spacing`), or, where the loop logic is what's under test, a fake/stub cohort
object exposing `.cases` so `compute_cohort_metrics` runs without invoking the
full pipeline per grid point.

- **AC1/AC2/AC3:** construct axes; assert nested-param placement via
  `config.rule_param`; assert `SegQCInputError` on empty `param_path`/`values`;
  assert base config and its `rules` dict are unchanged after apply
  (deep-equality) and returned configs are independent.
- **AC4:** assert candidate count `== ∏ k_i` and exact ordering (last axis
  fastest) for a 2×3 grid; assert empty-axes → single empty assignment
  (config unchanged).
- **AC5:** run on a small real synthetic cohort; assert one `CandidateResult`
  per grid point, each carrying a `CohortMetrics`, in grid order.
- **AC6:** hand-crafted cohort/stub where one candidate meets the floor and
  another misses it; assert `feasible` flags.
- **AC7 (separating threshold):** build a cohort where a clean-GT case passes
  only when a threshold is loose enough and an injected-failure case is caught
  only when it is tight enough, so a bounded value sub-range is uniquely
  feasible; assert `best.assignment` lands in that range.
- **AC8:** multiple feasible candidates with differing FPR → assert min-FPR
  chosen.
- **AC9:** two feasible candidates tied on FPR, differing overall sensitivity →
  assert the documented secondary key wins; a further exact tie → earliest grid
  order wins.
- **AC10:** objective with an unreachable `sensitivity_floor` (or a cohort where
  no candidate catches a mode) → `best is None`, `feasible is False`,
  `status == "no-feasible-setting"`, no exception.
- **AC11 (determinism):** run twice; assert equal `best` and byte-identical
  `json.dumps(result.to_dict(), sort_keys=True)`.
- **AC12 (consumable round-trip):** `json.loads(json.dumps(result.to_dict()))
  == result.to_dict()`; re-apply `best.assignment` and assert the rebuilt
  config's metrics equal `best.metrics`.
- **AC13:** `default_calibration_axes()` returns axes over both rule families;
  feed them to `calibrate_thresholds` on a cohort and assert it enumerates and
  evaluates without error.
- **AC14:** axes whose product exceeds `max_grid_size` → `SegQCInputError`
  raised before any evaluation (assert via a spy/short-circuit or by timing/no
  side effects).
- **AC15 (immutability):** snapshot `base_config`, `cases`, `axes` (deep) before
  the call; assert unchanged after; assert no file written (the module does no
  I/O of its own).
- **Adversarial/edge:** empty cohort (`cases=[]`) → metrics degenerate but no
  crash, result well-formed; single-axis single-value grid; a mode with zero
  cases excluded from the floor; `None` FPR ordering.

## Dependencies

- **Item 053 — `segqc.eval.harness`** (✅, merged): `EvaluationCase`,
  `evaluate_cohort`, `CohortEvaluation`. The loop re-runs `evaluate_cohort`
  under each candidate config.
- **Item 054 — `segqc.eval.metrics`** (✅, merged): `compute_cohort_metrics`,
  `CohortMetrics`, `PerModeSensitivity` (per-mode `sensitivity`), the FPR and
  correlation fields the objective scores against.
- **Item 052 — `segqc.eval.outcome`** (✅, merged, transitively via 053/054):
  `CaseOutcome` fields the metrics read.
- **Item 005/035 — `segqc.config`** (✅, merged): `HeuristicConfig` (frozen,
  `rules` dict, `rule_param`); the object the loop clones per candidate.
- **Item 027/048 — `segqc.heuristics.bounds`** (✅, merged): the Stage-4
  level-aware bounds config shape swept (`rules.bounds.params.<group>.*`).
- **Item 047 — `segqc.heuristics.reference_delta`** (✅, merged): the Stage-6
  delta-to-reference thresholds swept (`max_robust_z`,
  `max_distribution_distance`).
- **`segqc.io.SegQCInputError`** (✅): the raised error type, consistent with
  053/054.

Consumers (not this item): **056** (renders/persists the chosen thresholds +
metrics), **057** (`segqc evaluate` entry point + Stage-7 acceptance).

## Decisions & Trade-offs

To be updated during implementation.
