# Item 092 — Evaluation-harness reference wiring + Stage-14 real recalibration measurement

> **Created:** 2026-07-19 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7)
> **Queue:** ad hoc (found and fixed while executing Stage 14's own held-out
> measurement on real VerSe19 data, not queue-012 — items 089-091 were already
> merged when this was discovered)
> **Branch:** `aide/092-eval-harness-reference-wiring`

---

## Description

While running Stage 14's real held-out FPR measurement on the mounted VerSe19
cohort (training/validation/test, via the Stage-13 adapter), the measured FPR
was found to be byte-identical to item 084's pre-Stage-14 number (0.925/0.975),
despite items 089 (FOV-aware `coverage`/`border`) and 090 (reference-derived
`bounds`/`fragmentation` defaults) having merged in between. Investigation
found the cause: `segqc.eval.harness.evaluate_case`/`evaluate_cohort` — the
machinery behind `segqc evaluate` and `segqc.eval.calibrate.
calibrate_thresholds`, i.e. **every** Stage 7/12/14 FPR/calibration measurement
— called `segqc.pipeline.run_qc` unconditionally. Only `run_qc_with_reference`
attaches a `ReferenceDistribution` to the record fed to the rule engine, and
only `cli.py::_handle_run` (the single-case `segqc run` command) ever called
it. Item 090's reference-derived `bounds`/`fragmentation` sources, and the
`reference_delta` rule (item 047) entirely, silently degrade to their
hand-set/no-op fallback whenever a reference is absent (by design — see item
090's own module docstring) — which was **always**, for the evaluation
harness. Every historical "Real VerSe GT" FPR figure, including Stage 14's own
first held-out measurement, was therefore computed against the wrong config.

This item (a) fixes the harness so a reference can actually be threaded
through evaluation/calibration, (b) re-measures Stage 14's real recalibration
correctly with that fix in place, and (c) records the (still negative) honest
outcome.

## What this item is not

- **Not a change to the shipped default config.** No `default_config.yaml`,
  `reference_verse_v1.json`, or rule-code edit. The bug is purely in the
  measurement path (`eval/harness.py`, `eval/calibrate.py`, `cli.py`'s
  `evaluate` subcommand).
- **Not a redesign of the `reference_delta` rule's z-score mechanism.** The
  real measurement this item enables shows threshold-loosening alone cannot
  clear the FPR bar without breaking the sensitivity guard (see Decisions).
  Deriving the rule's threshold directly from the training distribution's own
  percentiles (mirroring how `bounds`/`fragmentation` already work) is the
  natural next step but was explicitly deferred per steering ("keep it simple
  for now, defer a more elaborate rule-making scheme").
- **Not run through the full spec-author → test-writer → builder → validator
  pipeline.** This was executed directly in one sitting (implementation +
  tests + real-data measurement) given its shape (a scoped bug found mid-task,
  analogous to items 076/085's "real run exposed a bug" precedent) rather than
  queued as a fresh work item. Documented here after the fact for the same
  traceability every other item gets.

## Acceptance Criteria

- [x] **AC1.** `evaluate_case`/`evaluate_cohort` accept an optional
  `reference` (+ `stratum`/`lower_pct`/`upper_pct`) parameter; `reference=None`
  (the default) is byte-identical to the pre-092 behaviour for every existing
  caller (Stage-5 golden harness, every pre-092 eval/calibrate test).
- [x] **AC2.** A given `reference` routes the subject through
  `run_qc_with_reference` instead of plain `run_qc`, so `reference_delta` and
  the reference-derived `bounds`/`fragmentation` sources actually engage.
- [x] **AC3.** `calibrate_thresholds` forwards `reference`/`stratum`/
  `lower_pct`/`upper_pct` unchanged to every grid candidate's `evaluate_cohort`
  call.
- [x] **AC4.** `segqc evaluate` gains `--reference`/`--reference-artifact`,
  opt-in (not inherited from `config.reference_param("enabled")`, unlike
  `segqc run` — an unmatched reference would silently score a cohort against
  the wrong distribution, the three-planes discipline item 090 established).
- [x] **AC5.** No regression: the full test suite (3710 tests) passes
  unchanged; `tests/test_055_calibrate.py`'s `evaluate_cohort` stub was widened
  to accept (and ignore) the new kwargs.
- [x] **AC6.** New regression tests (`tests/test_092_eval_reference_wiring.py`,
  12 tests) cover: reference-none-is-unchanged, reference_delta only fires
  with an attached reference, cohort-level forwarding, non-mutation,
  stratum/percentile threading, calibrate-forwards-reference, and the CLI
  flags (including the nonexistent-artifact error path).
- [x] **AC7.** The real Stage-14 recalibration is re-measured with the fix in
  place: reference-aware default config FPR on held-out validation/test;
  training-fitted `calibrate_thresholds` over the `reference_delta` axes;
  held-out measurement of the calibrated config; the anti-gaming sensitivity
  guard (Stage-5 synthetic corpus + Stage-5 perturbations on real training GT)
  against that calibrated config. All four ran to completion on the mounted
  VerSe19 cohort (`SEGQC_VERSE_COHORT`).
- [x] **AC8.** `progress.md`'s Stage 14 section, G3 objective-coverage note,
  and the "Real VerSe GT" verification row are reconciled with the corrected
  numbers; G3 stays 🚧 (neither the FPR bar nor the sensitivity guard is met).

## Real-data results (2026-07-19, VerSe19 via `SEGQC_VERSE_COHORT`)

| Measurement | Validation (40) | Test (40) |
|---|---|---|
| Reference-**blind** (pre-092 harness bug, = item 084's number) | 0.925 | 0.975 |
| Reference-**aware**, shipped default (items 089/090, uncalibrated) | 0.975 | 1.000 |
| Reference-aware, **calibrated** (`max_robust_z=15`, `max_distribution_distance=8`) | 0.900 | 0.950 |

Calibration (`calibrate_thresholds`, fitted on the 80-subject training split,
6-point grid over `reference_delta.max_robust_z ∈ {5,10,15}` ×
`max_distribution_distance ∈ {5,8}`) picked the grid's loosest corner
(training FPR 0.90) — the objective has no sensitivity floor to respect here
(a GT-only cohort has no failure cases), so it simply minimises FPR
monotonically toward whichever end of the grid is loosest.

**Anti-gaming sensitivity guard** (item 091's baseline: `{2,3,5,6,7} → 1.0`),
evaluated against the calibrated config:

- Stage-5 synthetic corpus: `{2:1.0, 3:1.0, 5:1.0, 6:1.0, 7:1.0}` — **no
  regression**.
- Stage-5 perturbation operators applied to real VerSe19 **training** GT (397
  perturbed cases): `{2:0.90, 3:1.0, 5:1.0, 6:1.0, 7:0.8125}` — **regressed**
  (`fragment` and `sequence_break` both drop below the 1.0 floor).

The guard is doing its job: the same loosening that helps FPR on real GT also
lets a genuinely fragmented or reordered real vertebra slip through more often
than on the (less variable) synthetic corpus. **G3 cannot be flipped** —
`may_flip_g3` is `False` (FPR far above the 0.10 target, and
`sensitivity_ok=False`).

## Root cause (why loosening doesn't work here)

The `reference_delta` rule computes a per-feature `robust_z` against the
reference's median/IQR and flags a label if any tracked feature's `|robust_z|`
exceeds a single fixed threshold (`max_robust_z`, hand-set at 3.5 by item 047,
never fit to data). An 8-case sample of real training GT shows this
distribution is heavy-tailed: median `robust_z ≈ 0.74`, p90 `≈ 1.5`, max
`≈ 24.7`. A threshold loose enough to admit the tail (which the grid search
confirms doesn't fully happen even at 15) is also loose enough to admit a
level that has actually been perturbed. This is a mechanism problem, not a
threshold problem: a single global z-score cutoff can't separate "unusual but
real" from "actually wrong" when the real distribution's tail is this heavy.
The fix that would work is the same one `bounds`/`fragmentation` already use —
derive the cutoff directly from the training cohort's own empirical percentile
(e.g. the training set's own p99 of `robust_z`) instead of grid-searching
hand-picked constants — but that is a real rule-mechanism change, deferred per
explicit steering.

## Dependencies

- **Items 089/090/091 (✅ merged) — the rules this item's fix lets actually
  measure correctly.**
- **Item 084 — precedent** for recording a possibly-negative real-data finding
  honestly rather than as a failure to complete.
- **Downstream:** the deferred `reference_delta` threshold rework (percentile-
  derived, not grid-searched) is the next concrete step toward closing G3;
  Stage 16 (real failure corpus) still depends on Stage 14 landing first.

## Decisions & Trade-offs

- **Calibration grid was hand-picked, not derived from the training
  distribution.** A one-off diagnostic (`robust_z`/`distribution_distance` on
  an 8-case training sample) was available before the grid search ran and
  could have set the axis values directly from percentiles instead of guessed
  candidates; this was raised explicitly and the decision (steered by the
  user) was to keep the grid-search approach for now and defer the more
  principled percentile-derived threshold scheme to follow-on work.
- **The grid search is expensive** (~3s/case × 80 training cases × 6 grid
  points ≈ 2 hours) because each candidate re-runs the full pipeline over the
  whole training cohort; a percentile-derived threshold would cost one pass
  instead of six and was noted as the more efficient path for the deferred
  follow-on.
- **No production config change shipped.** Per item 091's own precedent (A8),
  this item measures and records; it does not adopt the calibration-selected
  thresholds as a new shipped default, both because the measured setting fails
  the sensitivity guard and because that would regenerate `config_hash`/the
  item-042 goldens — a decision for whoever designs the actual fix.
