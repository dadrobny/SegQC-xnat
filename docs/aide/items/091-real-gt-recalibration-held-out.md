# Item 091 — Real-GT recalibration, held-out measurement + sensitivity guard (completes Stage 14)

> **Created:** 2026-07-18 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7)
> **Queue:** [`../queue/queue-012.md`](../queue/queue-012.md) · Item 091 *(third and
> final Stage-14 item — the recalibration run + held-out measurement + anti-gaming
> sensitivity guard + stage closure, sequenced **after** 089 fixed the FOV rule
> semantics and 090 shipped the reference-derived defaults, so calibration measures
> already-correct rules rather than tuning a mis-specified one to fit real data)*
> **Objectives:** G3 (distinguish failure from legitimate variation — measure,
> on **held-out real** VerSe GT, whether the recalibrated rules pass real GT at a
> low false-positive rate) and G7 (evaluable / regression-testable — the
> calibrate → held-out-evaluate path and the sensitivity guard are proven on
> committed synthetic fixtures in CI; the real-cohort clause is a genuine skip)
> **Suggested branch:** `aide/091-real-gt-recalibration-held-out`

---

## Description

Close **Stage 14** by (a) running the Stage-7 threshold calibration
([`segqc.eval.calibrate`](../../../src/segqc/eval/calibrate.py), item 055) **fitted
on the VerSe19 training subset only** and **measuring the result on the disjoint
held-out** validation/test subsets; (b) adding an **executable anti-gaming
sensitivity guard** that re-runs the Stage-5 synthetic corpus **and** Stage-5
perturbations applied to **real** VerSe GT and asserts per-mode sensitivity does
not regress below item 057's recorded baseline; and (c) reconciling the honest
outcome — recording the achieved FPR/sensitivity **pair** in `progress.md`,
updating the **"Real VerSe GT"** verification row, and flipping **G3 → ✅ only if**
the held-out real FPR ≤ 0.10 **and** the sensitivity guard passes, otherwise
recording the achieved numbers honestly and leaving G3 🚧 with the trade-off curve.

**The held-out design — no circularity, no "split" concept in the framework.**
Item 090 already made the shipped default reference-derived, grounded on the
committed real `reference_verse_v1.json` (25 levels C1…S, 80 VerSe19 **training**
subjects). Calibration fits on the **same** training population that grounded the
reference and is *measured* on the **held-out** validation/test subjects the
reference never saw. The two cohorts are produced by the Stage-13 adapter as two
**disjoint subsets** (`segqc.datasets.resolve(descriptor, subset="training")` vs
`subset="validation"`/`"test"`), so the framework only ever sees "calibration
cohort" and "eval cohort" — two plain `Cohort`s — and no train/val/test split
concept leaks into `calibrate`/`evaluate` (the Stage-13 boundary, item 086's
module docstring). The two-step flow over the **existing** surfaces is: (1)
`calibrate_thresholds(training_cases, base_config, axes)` → a feasible `best`
assignment; (2) `apply_assignment(base_config, best.assignment, axes)` → the
calibrated config; (3) `evaluate_cohort(held_out_cases, calibrated_config)` +
`compute_cohort_metrics(...)` → the **held-out** FPR. No production code is added
(see scope fence): `segqc evaluate --calibrate` (item 057) and `--dataset-schema
verse19.yaml --subset <name>` (item 087) already exist; this item supplies the
Stage-14 acceptance test module (which exercises the flow over a synthetic
stand-in in CI and gates the real clause), the importable **sensitivity guard**,
the **G3 recalibration-evidence record + conditional-flip guard**, and the
**validator-at-merge closure**.

**The anti-gaming constraint is the crux — FPR and sensitivity are one pair.**
The queue is explicit: FPR is trivially driven to 0.0 by loosening or disabling
rules, so **no** improvement in real-GT FPR counts unless per-mode sensitivity is
shown not to have regressed below item 057's baseline — **5/8 pipeline-detectable
§6 modes at sensitivity 1.0** (modes 2/3/5/6/7; modes 1/4/8 are structurally
invisible to the plain pipeline and are **not** claimed — item 057's Assumptions).
Item 091 makes that guard **executable**: an importable helper computes per-mode
sensitivity for a given `(cohort, config)` and a pure predicate decides whether it
regressed against the baseline; a **negative test proves the guard fails loudly on
a deliberately over-loosened config** (one that would drive FPR → 0 by blinding
the rules), so the acceptance bar cannot be gamed.

**The real numeric outcome is NOT knowable at spec-authoring time.** No real VerSe
cohort is mounted on this dev machine (the queue's "Key constraint"), so whether
the 089/090-recalibrated defaults (or a calibration-selected setting) actually
reach FPR ≤ 0.10 on held-out real GT with sensitivity intact **cannot** be decided
here. This item therefore defines **both** outcomes as valid completions and its
own tests **must not assume a specific FPR**, mirroring item 084 exactly (which
recorded a real FPR of 0.925/0.975 as a genuine finding, not a failure to complete
the item):

- **If** a data-holding host (a gated CI job / a human with the cohort mounted)
  runs the gated clause and observes **held-out FPR ≤ 0.10 with the sensitivity
  guard passing**, the validator flips **G3 → ✅** and the "Real VerSe GT" row to
  the post-recalibration number.
- **If not**, the achieved numbers are recorded honestly, **G3 stays 🚧** with the
  FPR-vs-sensitivity trade-off curve and documented next steps.

On this data-absent host the gated clause **skips cleanly** (a genuine
`pytest.mark.skipif` on `real_verse_cohort_dir()`, never `xfail`, never a vacuous
pass — items 069/084/088), the synthetic stand-in flow + the synthetic half of the
sensitivity guard run unconditionally, and the emitted evidence record self-reports
`g3_met == False` (real cohort absent).

### Public surface (test-side helpers this item adds)

All in the acceptance module `tests/test_091_stage14_acceptance.py` — importable
helpers (mirroring items 075/084's importable acceptance helpers), **no production
code**:

```python
def real_verse_cohort_dir() -> "Optional[pathlib.Path]":
    """The real VerSe19 root from SEGQC_VERSE_COHORT iff set AND a directory,
    else None. The single runtime gate for the real-VerSe clause (identical
    contract to test_084 / test_088's detector — items 069/080's cupy/docker
    analogue for a dataset)."""

def build_standin_splits(tmp_dir) -> "Tuple[list, list]":
    """Build two DISJOINT synthetic VerSe-shaped stand-in cohorts — a
    'calibration' cohort and a 'held-out' cohort — as evaluate-shape
    EvaluationCase lists (GT-as-expected-pass, candidate == gt). Their case_id
    sets are provably disjoint. Used to exercise the calibrate -> held-out
    -evaluate machinery in CI without real data."""

def calibrate_then_measure(calibration_cases, held_out_cases, base_config, axes
                           ) -> "Tuple[CalibrationResult, CohortMetrics]":
    """Fit calibrate_thresholds on calibration_cases only, apply the selected
    best assignment onto base_config, then evaluate_cohort + compute_cohort_
    metrics on held_out_cases. Returns (calibration_result, held_out_metrics).
    The calibration fit never receives held_out_cases (the no-circularity flow)."""

def per_mode_sensitivity(cases, config, *, failure_modes) -> "Dict[int, float]":
    """{mode_key: sensitivity} for each observed §6 mode with n_cases > 0, via
    evaluate_cohort -> compute_cohort_metrics. The guard's measurement primitive,
    used for both the Stage-5 synthetic corpus and Stage-5 perturbations on GT."""

def sensitivity_baseline() -> "Dict[int, float]":
    """Item 057's recorded baseline: {2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}
    (the 5 pipeline-detectable §6 modes). Does NOT include modes 1/4/8
    (structurally invisible — never claimed)."""

def sensitivity_regressed(achieved, baseline) -> bool:
    """The guard predicate: True iff ANY baseline mode's achieved sensitivity is
    below its baseline floor (a missing/None achieved mode counts as regressed).
    False iff every baseline mode meets or exceeds its floor. Pure."""

def g3_recalibration_record(*, real_cohort_present, cohort_id, build_date,
                            held_out_fpr, sensitivity_ok,
                            fpr_target=0.10) -> dict:
    """A JSON-native evidence record:
       {"real_cohort_present": bool, "cohort_id": str|None,
        "build_date": str|None, "held_out_fpr": float|None,
        "fpr_target": float, "sensitivity_ok": bool, "g3_met": bool}
    where g3_met is True ONLY when real_cohort_present AND held_out_fpr is not
    None AND held_out_fpr <= fpr_target AND sensitivity_ok (see may_flip_g3)."""

def may_flip_g3(record: dict) -> bool:
    """The closure guard: True iff record["real_cohort_present"] AND a numeric
    record["held_out_fpr"] <= record["fpr_target"] AND record["sensitivity_ok"].
    Any synthetic-only record, any FPR above target, or any sensitivity
    regression -> False, so G3 can never be flipped ✅ from a synthetic run, an
    unmet FPR, or a gamed (sensitivity-regressed) config."""
```

### What this item is **not** (scope fence)

- **NOT a new `segqc` subcommand, new `scripts/` tool, or any `src/segqc/**`
  change.** The calibration loop (item 055), the `segqc evaluate --calibrate`
  entry point (item 057), the `--dataset-schema`/`--subset` adapter wiring (item
  087), the disjoint-subset resolver (item 088), and the reference-derived shipped
  defaults (item 090) all already exist. This item adds only its acceptance test
  module (+ the validator's at-merge `progress.md` edit). No new production code,
  no new dependency.
- **NOT the shipping of a recalibration-selected production config as the new
  default.** Item 090 already shipped the reference-derived defaults. Item 091
  **measures** whether they (or a calibration-selected setting) clear the held-out
  bar and **records/recommends** the winning assignment in the evidence record /
  the `progress.md` metrics note; **actually adopting** a calibration-selected
  config as a shipped default (which would regenerate `config_hash` / goldens) is
  a **follow-on** contingent on a data-holding host confirming FPR ≤ 0.10 with
  sensitivity intact — deliberately kept out so this direct-merge diff is
  test-only and **outcome-independent** (Assumptions). If the reviewer wants the
  chosen thresholds shipped in this item, the builder/validator hands back.
- **NOT an assumption about the real FPR outcome.** No test asserts a specific
  held-out real FPR value or that FPR ≤ 0.10 is achieved (the number is unknowable
  here — see Description). CI asserts only the synthetic stand-in's
  well-formedness + its documented clean bound, the guard's correctness, and the
  genuine skip of the real clause.
- **NOT a change to `reference_verse_v1.json`, `reference_default.json`, the
  Stage-5 corpus / manifest / goldens, the report/reference schema, or the FOV /
  bounds / fragmentation rule code.** Items 089/090 own the rule semantics and
  defaults; this item consumes their merged behaviour and measures it.
- **NOT a `progress.md` edit by the item's direct-merge work, and NOT a
  `roadmap.md` / `vision.md` edit at all.** Recording the FPR/sensitivity pair,
  updating the "Real VerSe GT" row, reconciling the Stage-14 deliverables /
  acceptance checkboxes / stage-summary, and the conditional G3 flip are the
  **validator's at-merge action** via the `aide` CLI (Assumptions A7), mirroring
  items 049/057/065/070/075/084. Committing the numeric G3 target into
  `vision.md` §2 (the queue/roadmap already state FPR ≤ 0.10) is a **PR-gated**
  framework change, out of scope for this direct-merge item.

---

## Acceptance Criteria

_Each criterion is atomic, observable, and directly testable — one focused test
per AC. AC1–AC10 and AC12–AC16 run and pass unconditionally on this data-absent
host; AC11 concerns the genuine skip of the real-VerSe clause (which skips here).
The synthetic stand-in cohorts are tiny (2–3 subject) VerSe-shaped sets built in a
`tmp_path` from `segqc.synth.clean_gt.build_clean_spine` (multi-level L1–L5) +
`segqc.synth.intensity.paint_clean_scan` sibling scans, or hand-built
`EvaluationCase`s over the committed Stage-5 corpus; no real VerSe data. Metrics
come from `segqc.eval.harness.evaluate_cohort` → `segqc.eval.metrics.compute_
cohort_metrics`. "Well-formed FPR" = a `float` in `[0.0, 1.0]`._

### A. Calibrate → held-out-evaluate over a synthetic stand-in (CI, unconditional)

- [ ] **AC1: the Stage-14 acceptance module exists with its importable helpers.**
      `tests/test_091_stage14_acceptance.py` exists and exposes callable
      `real_verse_cohort_dir`, `build_standin_splits`, `calibrate_then_measure`,
      `per_mode_sensitivity`, `sensitivity_baseline`, `sensitivity_regressed`,
      `g3_recalibration_record`, and `may_flip_g3`.

- [ ] **AC2: the calibration and held-out stand-in cohorts are provably
      disjoint.** `build_standin_splits(tmp_path)` returns two non-empty
      `EvaluationCase` lists whose `case_id` sets are **disjoint**
      (`set(cal_ids).isdisjoint(set(held_ids))`, both non-empty) — the concrete
      "no circularity" proof that calibration fit and held-out measurement never
      share a subject.

- [ ] **AC3: the calibrate → held-out-evaluate flow runs end-to-end and yields
      well-formed held-out metrics.** `calibrate_then_measure(cal_cases,
      held_cases, base_config, axes)` (a small explicit axis grid) returns a
      `CalibrationResult` with `best is not None` (a feasible setting exists on
      the clean stand-in) and a held-out `CohortMetrics` whose
      `false_positive_rate` is a well-formed FPR (a `float` in `[0.0, 1.0]`) and
      whose `n_cases == len(held_cases)` — the machinery produces a measurable
      held-out number.

- [ ] **AC4: the calibration fit never receives the held-out cohort.** In
      `calibrate_then_measure`, the cases passed to `calibrate_thresholds` are
      exactly `cal_cases` (their `case_id` set equals `set(cal_ids)` and is
      disjoint from the held-out set) — asserted by capturing/inspecting the
      cases the fit was driven over (e.g. via a spy/wrapper or by asserting the
      helper forwards `cal_cases` unchanged), proving the held-out measurement is
      genuinely out-of-fit.

- [ ] **AC5: a clean self-consistent stand-in held-out cohort measures FPR 0.0.**
      For the clean stand-in held-out cohort (GT-as-candidate, `expected_verdict
      == "pass"`) evaluated under the calibrated config **with its matching
      cohort baseline** (the synthetic `reference_default.json`, per the
      three-planes discipline — pinned in Assumptions), `metrics.false_positive_
      rate == 0.0` — the flow actually measures a clean cohort as clean (the
      documented CI bound; distinct from any real-data FPR, which is not asserted).

### B. The executable anti-gaming sensitivity guard (CI, unconditional)

- [ ] **AC6: `sensitivity_baseline` encodes item 057's recorded baseline.**
      `sensitivity_baseline()` returns `{2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}`
      — exactly the 5 pipeline-detectable §6 modes at 1.0 — and contains **none**
      of the structurally-invisible modes `{1, 4, 8}` (never over-claimed).

- [ ] **AC7: the shipped default reproduces the baseline on the Stage-5 synthetic
      corpus.** `per_mode_sensitivity(<corpus cohort>, bundled_default_config(),
      failure_modes=FAILURE_MODE_NAMES)` yields sensitivity `1.0` for **every**
      baseline mode `{2, 3, 5, 6, 7}` — the 089/090-recalibrated shipped default
      does not regress the synthetic corpus (the guard's positive case, "re-run
      the Stage-5 synthetic corpus"). *The corpus cohort is built exactly as item
      057: GT = `clean_control` seg, candidate = each perturbed seg.*

- [ ] **AC8: `sensitivity_regressed` is a correct guard predicate.**
      `sensitivity_regressed(achieved, baseline)` returns `False` when every
      baseline mode's achieved sensitivity meets/exceeds its floor, and `True`
      when **any** baseline mode's achieved value is below its floor **or** is
      missing/`None` in `achieved` (parametrised over: an exact match, one mode
      lowered to 0.5, one mode at 0.0, and one mode absent) — pure, no I/O.

- [ ] **AC9: the guard fails loudly on a deliberately over-loosened config.**
      Under an over-loosened config that would drive FPR toward 0 by blinding the
      §6-detecting rules (e.g. the `bounds`/`fragmentation`/`coverage`/`border`
      rules disabled via `config.rule_enabled(...) == False`, or their thresholds
      widened so nothing fires), `per_mode_sensitivity(<corpus cohort>, <loosened
      config>, …)` drops at least one baseline mode below `1.0` and
      `sensitivity_regressed(<that>, sensitivity_baseline()) is True` — the guard
      **rejects** the gamed config, proving the FPR bar cannot be met by loosening.

- [ ] **AC10: `per_mode_sensitivity` and the guard are deterministic and
      non-mutating.** Two `per_mode_sensitivity` calls on the same `(cases,
      config)` return equal dicts; neither `cases`, its cases, nor `config` is
      mutated (deep before/after equality); `sensitivity_regressed` returns the
      same result on repeat calls and mutates neither argument.

### C. Stage-5 perturbations applied to GT — machinery in CI, real cohort gated

- [ ] **AC11: applying Stage-5 operators to a stand-in GT fires the expected §6
      rule per pipeline-detectable mode.** For a synthetic stand-in GT
      (`build_clean_spine`), applying each pipeline-detectable-mode Stage-5
      perturbation operator (`segqc.synth.perturbation` family, `apply(labelmap,
      seed)`) and running the perturbed labelmap through the pipeline fires the
      operator's designated `rule_id` — i.e. `per_mode_sensitivity` over the
      perturb-a-given-GT cohort returns `1.0` for each of `{2, 3, 5, 6, 7}`. This
      is the **CI-runnable analogue** of "Stage-5 perturbations on real VerSe GT":
      it proves the perturb-arbitrary-GT → measure-sensitivity code path (the
      exact path the gated real clause runs) on data that is always present.

- [ ] **AC12: the real-VerSe perturbation-sensitivity clause is a GENUINE skip
      when no real cohort is configured.** The test that would apply Stage-5
      perturbations to **real** VerSe GT and assert non-regression is gated by a
      real `pytest.mark.skipif` whose `mark.name == "skipif"` and whose condition
      `mark.args[0]` is a `bool` that is `True` on this host (no
      `SEGQC_VERSE_COHORT` / no mounted data) — never `xfail`, never an
      unconditional pass — mirroring `tests/test_069_container_smoke.py` /
      `tests/test_084_stage12_acceptance.py` / `tests/test_088_stage13_
      acceptance.py`.

- [ ] **AC13: `real_verse_cohort_dir()` returns `None` when the dataset is
      absent.** With `SEGQC_VERSE_COHORT` unset it returns `None`; with
      `SEGQC_VERSE_COHORT` set to a **nonexistent** path it also returns `None`
      (a bad/absent path is "no cohort", not a crash) — verified with
      `monkeypatch.setenv`/`delenv`.

### D. G3 recalibration-evidence record + the conditional-flip guard

- [ ] **AC14: `g3_recalibration_record` returns a JSON-native record with the
      required keys.** It returns a `dict` with exactly the keys
      `real_cohort_present` (`bool`), `cohort_id` (`str` or `None`), `build_date`
      (`str` or `None`), `held_out_fpr` (`float` or `None`), `fpr_target`
      (`float`), `sensitivity_ok` (`bool`), and `g3_met` (`bool`), all
      JSON-serialisable (round-trips through `json.dumps`/`json.loads`).

- [ ] **AC15: `may_flip_g3` / `g3_met` is `True` only with a real cohort AND an
      FPR at/under target AND sensitivity intact.** `may_flip_g3(record)` returns
      `True` for a record with `real_cohort_present is True`, a numeric
      `held_out_fpr <= fpr_target`, and `sensitivity_ok is True`; and returns
      `False` whenever `real_cohort_present is False`, **or** `held_out_fpr` is
      `None`/`> fpr_target`, **or** `sensitivity_ok is False` (parametrised over
      each falsifying case) — and `g3_recalibration_record(...)["g3_met"]` equals
      `may_flip_g3` of that record. G3 can never be flipped ✅ from a synthetic
      run, an unmet FPR, or a gamed (sensitivity-regressed) config.

- [ ] **AC16: a synthetic-only acceptance run yields a non-flipping record and
      self-reports it.** Building the record from the CI stand-in run
      (`real_cohort_present=False`) yields `real_cohort_present is False`,
      `g3_met is False`, and `may_flip_g3(record) is False`; the record is
      `print`ed to captured test output (runtime evidence, **not** a committed
      note — mirroring item 084 AC9 / item 075 A8), so the run's own output states
      plainly that G3 was **not** closed on this data-absent host.

### E. Scope / regression guard

- [ ] **AC17: the item adds no production code and no new dependency.** The diff
      introduces only `tests/test_091_stage14_acceptance.py` (plus the validator's
      at-merge `progress.md` edit): `src/segqc/**` and `scripts/**` are unchanged,
      `pyproject.toml`'s `[project].dependencies` gains nothing, and the
      pre-existing calibrate/evaluate/eval-harness test suite passes unchanged
      (this item is a test-side acceptance + validator-at-merge closure — the
      calibration + evaluate + adapter machinery is items 055/057/087/088/090,
      not new here).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete, testable design is recorded here for the
validator to surface at the queue boundary. Several **pin an interface**; the
builder/validator **hand back if reality diverged**.

- **A1 — item 091 adds no `src/segqc/**` change; it is a test-side acceptance +
  validator-at-merge closure, exactly like item 084.** The recalibration is
  *run* by the already-merged surfaces: `segqc evaluate --calibrate
  --dataset-schema verse19.yaml --subset training` (fit) records a
  `calibrated_config.yaml` (item 057 AC5), then `segqc evaluate --config
  calibrated_config.yaml --dataset-schema verse19.yaml --subset validation`
  (measure) quantifies the held-out FPR; equivalently the two-step Python flow
  `calibrate_thresholds` → `apply_assignment` → `evaluate_cohort` +
  `compute_cohort_metrics` that `calibrate_then_measure` wraps (item 057 AC13's
  precedent). Item 091 owns: the Stage-14 G3 **acceptance test** (synthetic path
  in CI; real path gated), the **sensitivity guard** helpers, the **G3
  recalibration-evidence record + flip guard**, and the **validator-at-merge
  closure**. If a reviewer requires a new `segqc recalibrate` subcommand, the
  builder/validator hands back.

- **A2 — the held-out flow fits on training and measures on validation/test as two
  disjoint adapter subsets; "split" is never a framework concept.** The Stage-13
  resolver (`segqc.datasets.resolve`) yields `subset="training"` and
  `subset="validation"`/`"test"` cohorts with disjoint `case_id`s (verified in
  `tests/test_088_stage13_acceptance.py`); the framework sees two plain `Cohort`s.
  `calibrate_thresholds` fits **and** selects `best` on the cohort it is passed
  (it evaluates every grid candidate on *that* cohort and picks the best-scoring),
  so train-fit / held-out-measure is the deliberate two-step flow — fit on
  training, then evaluate the *selected* config on the never-seen held-out cohort
  — not a single `--calibrate` call on a mixed cohort. This is the "no
  circularity" story made concrete (A2's disjointness is AC2/AC4).

- **A3 — the sensitivity baseline is item 057's recorded `{2,3,5,6,7} → 1.0`.**
  Item 057 recorded the 5 pipeline-detectable §6 modes at sensitivity 1.0 and the
  3 reconstructed-record modes (1 displace, 4 relabel-swap, 8 force-overlap) at
  0.0 (structurally invisible to plain `run_qc`, `detection ==
  "reconstructed_record"`). The guard enforces only the 5 detectable modes at
  1.0 — it must **not** demand the invisible modes fire (that would be a false
  bar item 057/049 explicitly disclaimed). `FAILURE_MODE_NAMES` (keys 0..8) names
  each mode; the baseline mode keys are `{2,3,5,6,7}`.

- **A4 — "does not regress below the baseline" means every baseline mode's
  achieved sensitivity ≥ its 1.0 floor.** Since every baseline mode is at 1.0,
  "no regression" == every one stays at 1.0. A missing/`None` achieved mode
  counts as **regressed** (conservative: a mode that produced no measurement is
  not silently credited). The guard is a `>=`-per-mode check, not an aggregate —
  a single dropped mode fails it, which is what makes it un-gameable (AC9).

- **A5 — the guard's two halves: the committed Stage-5 corpus (CI) + Stage-5
  perturbations on GT (CI stand-in unconditional, real cohort gated).** "Re-run
  the Stage-5 synthetic corpus" is AC7 (the committed `tests/corpus` cohort, GT =
  `clean_control`, candidate = each perturbed seg — item 057's construction).
  "Stage-5 perturbations applied to real VerSe GT" is realised as one
  perturb-a-given-GT → measure-sensitivity primitive (`per_mode_sensitivity` over
  cases built as GT = a seg, candidate = `operator.apply(seg, seed)`): proven in
  CI on a synthetic stand-in GT (AC11) and, on a data-holding host, applied to
  **real** GT (the `@requires_verse`-gated clause, AC12). The perturbation
  operators pick/require their target label per their own contract (item 037–039);
  on real GT the gated clause applies each operator to GTs where its target is
  present and asserts the mode fires there — its precise numeric bar is a
  data-holder concern, the machinery is CI-proven by AC11.

- **A6 — real-cohort detection via `SEGQC_VERSE_COHORT` [settled, reuse the
  established detector].** `real_verse_cohort_dir()` reads `SEGQC_VERSE_COHORT`
  and returns the path iff set **and** the dir exists, else `None` — byte-for-byte
  the contract items 084/088 already ship. The real clause is
  `@pytest.mark.skipif(real_verse_cohort_dir() is None, …)`; on CI/dev it skips
  cleanly (AC12), a nonexistent path is treated as absent (AC13). Re-declared in
  this module (each acceptance module carries its own detector — the item-084
  house style) rather than imported cross-module, so the module is
  self-contained; if the builder prefers importing a single shared detector, that
  is an acceptable equivalent.

- **A7 — `progress.md` reconciliation (incl. the verification-row update and the
  conditional G3 flip) is a validator-at-merge action, NOT a pytest AC
  [049/057/065/070/075/084 precedent].** At merge the validator, via the `aide`
  CLI + the noted free-text steps, updates `docs/aide/progress.md`'s Stage-14
  section — the two remaining 📋 deliverables (the recalibration run, the
  sensitivity guard) → ✅ *(item 091)*, the four Stage-14 acceptance checkboxes as
  warranted, the Stage-14 stage-summary row, and the G3/G7 objective-coverage rows
  — and records the achieved **FPR/sensitivity pair** plus updates the **"Real
  VerSe GT"** row. Following item 084 A6 / item 075 A9 exactly: those are flipped
  to the closed/✅ state **only if** item 091's gated real clause actually ran on
  the merging host (real cohort present; held-out FPR ≤ 0.10 quantified with a
  recorded cohort-id + date; the sensitivity guard passing — `may_flip_g3` True);
  on any host where the clause skipped (this CI/dev environment), the numbers are
  recorded as achieved-so-far and **G3 stays 🚧** with the trade-off curve. This
  bookkeeping is deliberately **not** an AC (a spec cannot pytest-assert its own
  progress-doc edits). **`roadmap.md`** and **`vision.md`** (PR-gated framework
  files) are **not** edited by this item — committing the numeric G3 target into
  `vision.md` §2 is a separate PR-gated step (the target is already stated in the
  roadmap's Stage-14 acceptance and in `progress.md`).

- **A8 — the item ships no recalibration-selected production config.** Item 090
  shipped the reference-derived defaults; item 091 measures them (and any
  calibration-selected setting) against the held-out bar and records/recommends
  the winning assignment in the evidence record + the `progress.md` metrics note.
  Adopting a calibration-selected config as a *shipped default* — which would
  regenerate `config_hash` and the item-042 goldens — is a follow-on contingent on
  a data-holding host confirming FPR ≤ 0.10 with sensitivity intact, kept out so
  this direct-merge diff is test-only and **outcome-independent** (the queue's
  "both outcomes are valid completions" constraint). Hand back if a reviewer wants
  the thresholds shipped here.

- **A9 — the clean stand-in is evaluated against its matching cohort baseline
  (three-planes discipline, item 090).** To make the CI stand-in flow measure a
  clean cohort as clean (AC5's FPR 0.0), the synthetic stand-in is evaluated
  against the **synthetic** `reference_default.json` (its own cohort baseline) or
  reference-off, **not** the verse-v1 production reference (whose real per-level
  bands a synthetic L1–L5 spine need not sit inside). This mirrors item 090
  AC13's separation of Plane 1 (synthetic code-testing, synthetic reference) from
  Plane 2 (real-GT grounding, verse-v1). The stand-in flow proves the
  *machinery*; the real held-out FPR (Plane 2) is measured only on the gated real
  cohort against verse-v1.

- **A10 — no test assumes a specific real FPR; the acceptance is outcome-neutral.**
  Every CI assertion is over well-formedness (float in `[0,1]`, disjoint cohorts,
  n_cases), the guard's correctness, the genuine skip, and the record/guard shape
  — none asserts the real held-out FPR equals or beats any value (unknowable
  here). The real number is *computed and recorded* on a data-holding host and
  *guarded* by `may_flip_g3`, mirroring item 084 A3's "quantify, don't threshold
  in CI".

- **A11 — pinned upstream interfaces (merged ✅; hand back if diverged):**
  - **Item 055** — `segqc.eval.calibrate.{calibrate_thresholds, apply_assignment,
    ThresholdAxis, default_calibration_axes, CalibrationObjective,
    CalibrationResult, CandidateResult}`: `calibrate_thresholds(cases,
    base_config, axes, *, objective=…)` fits+selects `best` on the passed cohort;
    `apply_assignment(base_config, best.assignment, axes)` re-applies the chosen
    values onto a copy — the fit/measure split rests on these being pure and not
    mutating `base_config`/`cases`.
  - **Item 057** — `segqc evaluate --calibrate --cohort/--out/--cohort-id/
    --build-date` writing `calibrated_config.yaml` + `eval_report.json`
    (`metrics.false_positive_rate`, `metrics.per_mode`), the `segqc.eval.cohort`
    manifest shape, and `segqc.eval.harness.{EvaluationCase, evaluate_cohort}` +
    `segqc.eval.metrics.{compute_cohort_metrics, CohortMetrics,
    PerModeSensitivity}` (`failure_modes=FAILURE_MODE_NAMES` names every §6 mode;
    `PerModeSensitivity.sensitivity` is `None` for `n_cases == 0`). The recorded
    5/8 baseline is item 057's.
  - **Items 086/087/088** — `segqc.datasets.{resolve, load_descriptor,
    bundled_descriptor_path}` + the committed `verse19.yaml` descriptor with
    `subsets: {training, validation, test}` (root overrides), the
    `--dataset-schema`/`--data-root`/`--subset` CLI wiring, and the
    `real_verse_cohort_dir()` detector contract. `resolve(subset="training")` /
    `resolve(subset="validation")` yield disjoint cohorts.
  - **Items 089/090** — the FOV-aware `coverage`/`border` semantics and the
    reference-derived `bounds`/`fragmentation` shipped defaults grounded on
    `reference_verse_v1.json`; the guard measures **these** merged rules. If
    090's default flip diverged (e.g. reference not on by default), the stand-in
    reference choice (A9) and AC7's baseline reproduction may need the matching
    reference attached explicitly — the builder notes the pin.
  - **Items 036/058** — `segqc.synth.clean_gt.build_clean_spine` +
    `segqc.synth.intensity.paint_clean_scan`: the stand-in GT/scan builders.
  - **Items 037–039** — the registered Stage-5 perturbation operators
    (`segqc.synth.perturbation`: `Perturbation.apply(labelmap, seed) ->
    PerturbationResult`, `FAILURE_MODE_NAMES`, `get_perturbation`/
    `iter_perturbations`) applied to a given GT (AC11 / the gated real clause).
  - **Items 040/041/042** — the committed Stage-5 corpus + manifest,
    `synth.corpus.load_manifest`, `synth.regression.loaded_seg_image`: the
    synthetic-half cohort of the guard (AC7), untouched.
  - **Item 069** — `tests/test_069_container_smoke.py`'s genuine-skip proof — the
    precedent AC12 mirrors for the `SEGQC_VERSE_COHORT`-gated marker.
  - **Item 084** — the honest, possibly-negative real-data closure precedent (it
    recorded FPR 0.925/0.975 as a finding, not a failure) whose acceptance-module
    + validator-at-merge shape, `real_verse_cohort_dir` detector, and
    evidence-record/guard pattern this item follows exactly.

## Implementation Steps

Intended path: a **single new test module** `tests/test_091_stage14_acceptance.py`.
**No** change to `src/segqc/**`, no new `scripts/` tool, no committed artifact,
no config/golden regeneration. (The only non-test edit for the whole item is the
**validator's** at-merge `progress.md` reconciliation — A7 — which the
builder/test-writer do not make.)

1. **Module skeleton + importable helpers** (mirror item 084's acceptance module):
   - `real_verse_cohort_dir()` — read `SEGQC_VERSE_COHORT`, return an existing dir
     else `None` (A6).
   - `build_standin_splits(tmp_dir)` — build two disjoint tiny VerSe-shaped
     stand-in cohorts (`build_clean_spine` L1–L5 + `paint_clean_scan`), returned
     as `EvaluationCase` lists (GT-as-candidate, `expected_verdict == "pass"`),
     with **disjoint** `case_id`s (e.g. `cal-00N` vs `held-00N`).
   - `calibrate_then_measure(cal_cases, held_cases, base_config, axes)` —
     `res = calibrate_thresholds(cal_cases, base_config, axes)`;
     `cfg = apply_assignment(base_config, res.best.assignment, axes)` (guard
     `res.best is not None`); `metrics = compute_cohort_metrics(evaluate_cohort(
     held_cases, cfg))`; return `(res, metrics)`. Forward `cal_cases` unchanged so
     AC4 can assert the fit's input (a light spy/wrapper around
     `calibrate_thresholds`, or asserting the helper never concatenates the two
     lists).
   - `per_mode_sensitivity(cases, config, *, failure_modes)` —
     `compute_cohort_metrics(evaluate_cohort(cases, config),
     failure_modes=failure_modes)`, project to `{mode.mode_key: mode.sensitivity
     for mode in metrics.per_mode if mode.n_cases > 0}` (mode-key/name mapping per
     item 054's `PerModeSensitivity`).
   - `sensitivity_baseline()` — `{2: 1.0, 3: 1.0, 5: 1.0, 6: 1.0, 7: 1.0}` (A3).
   - `sensitivity_regressed(achieved, baseline)` — `any(achieved.get(k) is None or
     achieved[k] < v for k, v in baseline.items())` (A4).
   - `g3_recalibration_record(*, real_cohort_present, cohort_id, build_date,
     held_out_fpr, sensitivity_ok, fpr_target=0.10)` — assemble the JSON-native
     record, computing `g3_met` via `may_flip_g3`.
   - `may_flip_g3(record)` — `bool(record["real_cohort_present"]) and
     isinstance(record["held_out_fpr"], (int, float)) and record["held_out_fpr"]
     <= record["fpr_target"] and bool(record["sensitivity_ok"])`.
2. **Synthetic calibrate → held-out flow (AC2–AC5):** build the two disjoint
   stand-in cohorts; assert disjointness (AC2); run `calibrate_then_measure` with
   a **small explicit axis grid** (a few values on one or two axes, bounded like
   item 057 AC13, so the sweep stays fast/deterministic) and assert `best is not
   None`, well-formed FPR, `n_cases` (AC3); assert the fit saw only `cal_cases`
   (AC4); assert the clean held-out cohort measures FPR `0.0` against its matching
   synthetic reference / reference-off (AC5, A9).
3. **Sensitivity guard (AC6–AC10):** `sensitivity_baseline()` shape (AC6);
   `per_mode_sensitivity` over the committed corpus cohort under
   `bundled_default_config()` reproduces `{2,3,5,6,7} → 1.0` (AC7); the
   `sensitivity_regressed` truth-table parametrised (AC8); the over-loosened
   config drops a baseline mode and the guard returns `True` (AC9 — construct the
   loosened config by disabling the §6-detecting rules or widening thresholds);
   determinism + non-mutation (AC10).
4. **Perturb-a-given-GT machinery + gated real clause (AC11–AC13):** apply each
   pipeline-detectable Stage-5 operator to a stand-in GT and assert
   `per_mode_sensitivity` returns `1.0` for `{2,3,5,6,7}` (AC11); define
   `requires_verse = pytest.mark.skipif(real_verse_cohort_dir() is None, reason=
   "real VerSe GT cohort not mounted (set SEGQC_VERSE_COHORT)")`; a
   `@requires_verse` test that, on a data-holding host, resolves the real cohort
   via `resolve(load_descriptor(bundled_descriptor_path("verse19.yaml")),
   data_root=real_verse_cohort_dir(), subset=<name>)`, runs the calibrate→held-out
   flow **and** applies Stage-5 perturbations to real GT, asserts a well-formed
   held-out FPR and `sensitivity_regressed(...) is False`, builds the record with
   `real_cohort_present=True`, and asserts `may_flip_g3` matches the measured
   outcome — skips cleanly on CI/dev. Add the AC12 structural proof
   (`requires_verse.mark.name == "skipif"`, `isinstance(mark.args[0], bool)`,
   `is True` here) and the AC13 env-behaviour test.
5. **Record + guard tests (AC14–AC16):** record key/type shape + JSON round-trip
   (AC14); `may_flip_g3` / `g3_met` truth-table parametrised over each falsifying
   case (AC15); the synthetic-only record is non-flipping and `print`ed (AC16).
6. **Scope guard (AC17):** assert (via a light diff/source/path check) no
   `src/segqc/**` or `scripts/**` file is added/modified by this item and
   `pyproject.toml` `[project].dependencies` is unchanged; rely on the validator's
   full-suite run for "existing calibrate/evaluate tests pass unchanged".
7. **No `progress.md` / `roadmap.md` / `vision.md` edits here** (A7) — the
   validator reconciles `progress.md` Stage 14 at merge via the `aide` CLI,
   recording the FPR/sensitivity pair, updating the "Real VerSe GT" row, and
   flipping **G3 → ✅ only if** the gated real clause actually ran on the merging
   host with `may_flip_g3` True (else numbers recorded, G3 left 🚧 with the
   trade-off curve).

## Testing Strategy

_The spec-author does not run `pytest`. The test-writer authors
`tests/test_091_stage14_acceptance.py`; the builder makes **no** production edit;
the validator runs the full suite and reconciles `progress.md`._ One module, one
focused test per AC, mirroring the `test_0NN_*.py` convention (and item 084's
acceptance-module shape). All real-VerSe behaviour is `SEGQC_VERSE_COHORT`-gated
and skips cleanly on this data-absent host. Use the item-026 registry
snapshot/restore fixture (save/restore `segqc.heuristics.rule._RULES`) since the
guard drives `run_qc`/`evaluate_cohort` over the live rule registry. Use
`monkeypatch.setenv`/`delenv` for hermetic env handling; drive everything
in-process (not subprocesses) into `tmp_path`.

- **AC1** — import the module; assert the eight helpers are callable.
- **AC2** — `build_standin_splits(tmp_path)`; assert both lists non-empty and
  `set(cal_ids).isdisjoint(set(held_ids))`.
- **AC3** — `calibrate_then_measure` with a 2–3-point axis grid; assert
  `res.best is not None`, `isinstance(fpr, float)`, `0.0 <= fpr <= 1.0`,
  `metrics.n_cases == len(held_cases)`.
- **AC4** — spy/wrap `calibrate_thresholds` (or assert via the helper's
  forwarded argument) that the fit's `cases` `case_id` set equals `set(cal_ids)`
  and is disjoint from `held_ids`.
- **AC5** — evaluate the clean held-out stand-in against the synthetic reference
  (or reference-off, A9); assert `metrics.false_positive_rate == 0.0`.
- **AC6** — `sensitivity_baseline() == {2:1.0,3:1.0,5:1.0,6:1.0,7:1.0}` and
  `set(baseline).isdisjoint({1,4,8})`.
- **AC7** — build the committed-corpus cohort (item 057 helper); assert
  `per_mode_sensitivity(...)[k] == 1.0` for each `k in {2,3,5,6,7}`.
- **AC8** — parametrised truth-table over `(achieved, expected_regressed)`:
  exact match → `False`; a mode at 0.5 → `True`; a mode at 0.0 → `True`; a mode
  absent → `True`.
- **AC9** — build an over-loosened config (disable the four §6-detecting rules or
  widen thresholds); assert `per_mode_sensitivity(corpus, loosened)` has a
  baseline mode `< 1.0` and `sensitivity_regressed(that, baseline) is True`.
- **AC10** — two `per_mode_sensitivity` calls equal; deep before/after equality
  of `cases`/`config`; `sensitivity_regressed` repeat-call equal + args
  unmutated.
- **AC11** — for each pipeline-detectable operator, apply to a stand-in GT and
  assert `per_mode_sensitivity(<perturbed cohort>)[mode] == 1.0`.
- **AC12** — structural: `requires_verse.mark.name == "skipif"`,
  `isinstance(requires_verse.mark.args[0], bool)`, `... is True` on this host.
- **AC13** — `monkeypatch.delenv("SEGQC_VERSE_COHORT", raising=False)` →
  `None`; `monkeypatch.setenv` to a nonexistent path → still `None`.
- **AC14** — build a record; assert the exact key set + value types and a
  `json.dumps`/`json.loads` round-trip equal to the original.
- **AC15** — parametrised: `may_flip_g3` `True` only for `(present=True,
  fpr<=target, sens_ok=True)`; `False` for `present=False`, for `fpr None`, for
  `fpr > target`, and for `sens_ok=False`; assert `record["g3_met"] ==
  may_flip_g3(record)`.
- **AC16** — build the record with `real_cohort_present=False`; assert
  `real_cohort_present is False`, `g3_met is False`, `may_flip_g3(...) is False`;
  capture stdout and assert the record was printed.
- **AC17** — assert (git/diff or path check) the item adds only
  `tests/test_091_stage14_acceptance.py` under `src/segqc/**` + `scripts/**`
  scope, and parse `pyproject.toml` to assert `[project].dependencies` gained
  nothing.

**Adversarial / edge cases to include (beyond the ACs):**
- **No feasible calibration setting** — if a chosen stand-in + axis grid yields
  `res.best is None` (`status == "no-feasible-setting"`), `calibrate_then_measure`
  surfaces that explicitly (a clear error / a sentinel), never an
  `AttributeError` on `None.assignment`; the AC3 grid is chosen so a feasible
  setting exists, but the no-feasible branch is covered directly.
- **Guard non-vacuity** — `sensitivity_regressed({}, baseline) is True` (an empty
  achieved dict is a regression, not a vacuous pass), guarding against a
  silently-empty measurement flipping the guard green.
- **Over-loosened config still drives FPR down** — optionally assert the loosened
  config's FPR on a would-be-flagging cohort is lower than the shipped default's,
  making explicit *why* the guard is needed (loosening buys FPR at sensitivity's
  expense).
- **Nonexistent / empty `SEGQC_VERSE_COHORT`** — a set-but-nonexistent path
  returns `None` (AC13); an existing-but-empty real root resolves to an **empty**
  cohort without a traceback (the gated clause then treats it as "no evaluable
  GT").
- **Determinism of the stand-in flow** — two `calibrate_then_measure` runs over
  the same inputs yield equal held-out `metrics.to_dict()` (calibration +
  evaluation are deterministic).
- **Env hygiene** — `SEGQC_VERSE_COHORT` is not left mutated in `os.environ` after
  any test (monkeypatch teardown), asserted for at least one case.
- **Registry hygiene** — `segqc.heuristics.rule._RULES` is restored after tests
  that toggle rule enablement for the over-loosened config (item-026 fixture).

## Dependencies

- **Item 089 (✅ merged) — sequenced before / consumed.** FOV-aware
  `coverage`/`border` semantics: the guard measures these fixed rules, and modes
  5/6/7 still firing on genuine failures (item 089 AC5/AC6/AC13/AC14) is what
  keeps AC7/AC11 green.
- **Item 090 (✅ merged) — sequenced before / consumed.** The reference-derived
  `bounds`/`fragmentation` shipped defaults grounded on `reference_verse_v1.json`;
  the held-out measurement is *of* these defaults (and any calibration refinement
  of them). Item 090's three-planes discipline (synthetic corpus vs synthetic
  reference; real GT vs verse-v1) is the basis for A9/AC5.
- **Item 055 (✅ merged) — consumed.** `calibrate_thresholds` / `apply_assignment`
  / `ThresholdAxis` / `default_calibration_axes` — the fit half of the flow;
  their purity (no mutation of `base_config`/`cases`) is what the two-step
  fit/measure relies on (A11).
- **Item 057 (✅ merged) — consumed + baseline source.** The `segqc evaluate
  --calibrate` entry point + `evaluate_cohort` / `compute_cohort_metrics` /
  `PerModeSensitivity` and the committed-corpus cohort construction; the recorded
  **5/8** per-mode baseline the guard enforces (A3).
- **Items 086/087/088 (✅ merged) — consumed.** The dataset-agnostic
  `Cohort`/`Case` resolver, the `--dataset-schema`/`--subset` wiring, the
  committed `verse19.yaml` descriptor (disjoint `training`/`validation`/`test`
  subsets), and the `real_verse_cohort_dir()` detector — the held-out cohorts and
  the real-clause gate.
- **Items 036/058 (✅ merged) — consumed.** `build_clean_spine` /
  `paint_clean_scan` — the stand-in GT/scan builders.
- **Items 037–039 (✅ merged) — consumed.** The registered Stage-5 perturbation
  operators applied to a given GT (AC11 / the gated real clause).
- **Items 040/041/042 (✅ merged) — regression target.** The committed Stage-5
  corpus/manifest + loaders — the synthetic half of the guard (AC7), untouched.
- **Item 084 (✅ merged) — precedent.** The honest possibly-negative real-data
  closure pattern (recorded FPR as a finding, not a completion failure), the
  acceptance-module + validator-at-merge shape, the `real_verse_cohort_dir`
  detector, and the evidence-record/flip-guard idiom this item follows.
- **Item 069 (✅ merged) — precedent.** The genuine-`skipif` proof AC12 mirrors.
- **Items 049/057/065/070/075 (✅ merged) — precedent.** The stage-closer
  `progress.md`-reconciliation-at-merge (incl. env-gated row flips) and
  no-`roadmap.md`/`vision.md`-edit convention this item follows (A7).
- **Downstream:** **Stage 16** (real failure corpus, G2/G7) depends on Stage 14
  landing — real-tool sensitivity is only meaningful against the recalibrated
  rules this item measures; it is scoped but **not queued** (blocked on
  TotalSegmentator/SPINEPS outputs over real CT).

## Environment / Hardware Dependencies

- **Real VerSe GT cohort** — an **external dataset** (not a pip dependency; large
  / licensed, never committed). Required fallback when absent (the common case,
  including all CI): the real-VerSe recalibration/held-out and the
  perturbations-on-real-GT clauses **skip cleanly** — a genuine
  `pytest.mark.skipif` gated on `real_verse_cohort_dir()` (the `SEGQC_VERSE_COHORT`
  env var), never a failure, never a vacuous pass (AC12); the synthetic stand-in
  calibrate→held-out flow (AC2–AC5), the synthetic half of the sensitivity guard
  (AC6–AC11), and the record/guard tests (AC14–AC16) always run. Every automated
  test runs against synthetic data and never requires the real dataset.
  **Real-host runbook (for a data-holding CI job / human):** fit —
  `segqc evaluate --calibrate --dataset-schema src/segqc/datasets/verse19.yaml
  --data-root <VerSe19-root> --subset training --out <dir> --cohort-id
  verse19-train`; measure — `segqc evaluate --config <dir>/calibrated_config.yaml
  --dataset-schema … --subset validation` (and `test`) → read
  `metrics.false_positive_rate`; then run the `@requires_verse` guard clause to
  confirm sensitivity did not regress on real-GT perturbations.
  **Full-capability verification:** the actual recalibration + held-out
  measurement + real-GT sensitivity guard over a mounted real VerSe cohort — the
  numbers that decide the G3 flip — is **not** exercised in CI and a green
  stand-in run does **not** count as verification. This item **updates** the
  existing **"Real VerSe GT"** row in `progress.md`'s Environment-Gated Capability
  Verification table: the validator records the post-recalibration held-out
  FPR/sensitivity pair and flips **G3 → ✅** (and the row to the recalibrated
  number) **only** when a human / CI runner with real VerSe data actually ran the
  gated clause with `may_flip_g3` True (held-out FPR ≤ 0.10, sensitivity guard
  passing, recorded cohort-id + date); on a data-absent host the numbers are
  recorded as achieved-so-far and **G3 stays 🚧** with the trade-off curve (the
  two statuses are decoupled — see A7 and the table's header note).

## Decisions & Trade-offs

To be updated during implementation.
