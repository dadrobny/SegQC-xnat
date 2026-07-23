# Seg-QC-xnat — Work Queue 006

> **Status:** ✅ Completed — superseded by queue-007 (2026-07-12).
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-005.md`](queue-005.md) (items 043–049).

---

## Scope of this queue

Delivers roadmap **Stage 7 — Evaluation, Calibration & Metrics (G3, G7)** in
full. Stage 7 is the **last stage of Phase 1**, so completing this queue closes
out **"Phase 1 — Complete MVP Pipeline"**: the tool stops being a pipeline that
merely *emits* verdicts and becomes one whose verdicts are **quantified and
calibrated** against ground truth.

**Milestone delivered:** an automated **evaluation harness** that runs the full
`segqc` pipeline over a cohort of labelled cases and compares, at the **three
levels of §8**, (1) the QC pass/fail **verdict** against each case's known truth,
(2) **DICE vs GT** between a candidate segmentation and its ground truth, and
(3) the **feature-set match** by vertebra label. From the per-case records the
harness computes the Stage-7 **metrics** — false-positive rate on GT, sensitivity
per §6 failure mode, and the DICE-vs-flag correlation — then a **threshold-
calibration loop** sweeps the versioned heuristic thresholds (the Stage 4
level-aware bounds and the Stage 6 delta-to-reference thresholds) over the cohort
and selects the setting that meets a documented objective (low FPR on GT while
catching the injected failures). The chosen thresholds and headline metrics are
rendered into a versioned **evaluation report** (JSON + human) and recorded into
the heuristic config and `progress.md`. On completion GT passes at a high rate
(low FPR, **G3**), injected failures are caught with flag-rate / feature
divergence tracking DICE (**G7**), and the whole evaluation is reproducible —
marking the MVP pipeline complete.

**Prioritisation rationale.** The roadmap graph is linear into Stage 7
(`… → 5 → 7` with `6 → 7`), and both prerequisites are merged: Stage 5 supplies
the seeded synthetic-failure corpus + regression harness (the labelled positive
control and out-of-distribution cases the harness scores), and Stage 6 supplies
the reference distributions + delta-to-reference rules whose thresholds the
calibration loop tunes. Stage 7 is the single remaining Phase-1 milestone and the
prerequisite for **every** Phase-2 stage (containerisation Stage 9, GPU Stage 10,
extensibility Stage 11 all depend on a *stable, calibrated* pipeline), so it is
the highest-leverage next unit. The queue is scoped to exactly Stage 7 and stops
at the stage/phase boundary — Phase 2 (Stage 8 image features onward) is a fresh
batch behind the human-reviewed queue PR.

**Local-testability note (key design decision).** Full VerSe and live
TotalSegmentator output are large/external and are **not** committed to this repo
(consistent with queue-005's decision). So the evaluation harness (053) is written
to operate on **any** conforming cohort of `(GT, optional candidate, expectation)`
cases, and every item is tested locally against a **synthetic evaluation cohort**
assembled from the Stage 5 generator (`segqc/synth/`): clean-GT cases as the
positive control, and the Stage 5 **perturbed corpus** cases used both as
known-failure examples *and* as the "candidate vs GT" pair for DICE / feature
divergence (a perturbation of a clean GT is a controlled stand-in for a divergent
segmentation with a known DICE relationship). Running the harness on **mounted
real VerSe GT** and **TotalSegmentator outputs** is a documented, reproducible
path (mirroring the mounted-VerSe path from Stage 6). This keeps the whole stage
deterministic under `pytest` without shipping external datasets, while satisfying
the roadmap's "runs on VerSe GT / TotalSegmentator / synthetic" wording.

### Numbering note — read before picking an item

Items 001–049 are complete (Stages 0–6, all ✅ in `progress.md`). This queue
continues at the next free integer and is strictly monotonic: **050–057**.

**Estimated size:** ~1 week (8 items, within `loop.queue_cap = 10`). Each item is
independently testable locally with `pytest`: the comparison-primitive items
(050–052) assert per-label DICE / feature divergence / verdict-outcome against
hand-computed values on tiny fixtures; the harness/metrics/calibration items assert
records and derived rates against a synthetic cohort with known properties; the
report and integration items assert schema-valid reproducible output and the G3/G7
acceptance criteria end-to-end.

**Sequencing note.** Critical path: the three **comparison primitives 050
(DICE / overlap), 051 (feature-set match), 052 (verdict-outcome classification)**
are mutually independent — the three §8 comparison levels — and can be built in
parallel. **053** (cohort model + harness driver) depends on all three: it runs
`segqc run` per case and assembles their outputs into a per-case evaluation record.
**054** (metrics aggregation) depends on 053's record shape. **055** (calibration
loop) depends on 053 + 054 (it re-runs the harness under varied thresholds and
reads back metrics), and **056** (evaluation report + recorded results) depends on
054 (+055). **057** (integration + acceptance) depends on everything and closes
Stage 7 / Phase 1. Recommended order: (050 ‖ 051 ‖ 052) → 053 → 054 →
(055 → 056) → 057.

### Stage-7 deliverable → item coverage

| Stage-7 deliverable | Delivered by item(s) |
|---------------------|----------------------|
| Evaluation harness comparing at three levels — QC **verdict**; **DICE** vs GT; **feature-set match** by label | 050 (DICE / overlap, level 2), 051 (feature-set match, level 3), 052 (verdict-outcome classification, level 1) |
| Runs on VerSe GT (positive control), TotalSegmentator outputs, synthetic failures | 053 (cohort model + harness driver over **any** conforming source; assembles 050–052 per case) |
| Metrics: FPR on GT, sensitivity per failure mode, DICE-vs-flag correlation | 054 |
| Threshold-calibration loop; chosen thresholds + metrics recorded | 055 (calibration loop), 056 (evaluation report + recorded results) |
| *(integration & acceptance closure)* GT low-FPR / injected failures caught / DICE-vs-flag correlation (**G3**, **G7**); reproducible; **Phase 1 complete** | 057 |

Every deliverable is realised by ≥1 item. Item 053 is the harness that assembles
the three comparison levels (050–052) per case; item 057 wires the harness →
metrics → calibration → report into a reproducible entry point and asserts the
stage's **G3/G7** acceptance criteria end-to-end.

---

## Work items

### Item 050: Segmentation-overlap metrics — per-label & aggregate DICE vs GT
Provide the **DICE vs GT** comparison layer (§8 level 2): a pure, spacing-aware
module (e.g. `segqc/eval/overlap.py`) that, given a candidate instance label map
and a ground-truth label map, matches labels by anatomical level via the Stage 0
convention (`segqc/labels.py`) and computes **per-label DICE** (and Jaccard) plus
**aggregate** scores (unweighted mean and physical-volume-weighted mean over
matched labels). Handle real-world asymmetry explicitly: a label present in one map
but absent in the other scores DICE 0 with an explicit "unmatched" marker (not a
crash); empty inputs yield a well-formed empty result. No file I/O — arrays in,
scores out.
*Testable:* unit tests on tiny hand-built masks assert identical maps → DICE 1.0
per label, disjoint masks → 0.0, and a half-overlap case matches the hand-computed
DICE; a label present in only one map is reported as unmatched/0 rather than
erroring; anisotropic spacing leaves the (ratio-based) DICE unchanged while the
volume-weighted aggregate uses physical volume correctly; deterministic.

### Item 051: Feature-set match / divergence by vertebra label
Provide the **feature-set match** comparison layer (§8 level 3): a module (e.g.
`segqc/eval/feature_match.py`) that compares the Stage 2–3 feature sets of a
candidate vs its GT, matched by anatomical label, and emits a **per-label,
per-feature** difference (absolute and relative), an aggregate **per-label
divergence score**, and a **case-level** divergence score across a documented set
of tracked features (physical volume, extents, centroid spacing, spline offset, …).
Reuse the existing feature-engine outputs rather than recomputing geometry. Handle
labels present on only one side explicitly (reported as unmatched, not silently
dropped).
*Testable:* identical feature sets → zero divergence everywhere; perturbing one
label's features yields non-zero divergence localised to that label with the
expected sign/magnitude on the affected feature; a label missing on one side is
flagged unmatched; the case-level score aggregates per-label scores as documented;
deterministic.

### Item 052: QC-verdict comparison & per-case outcome classification
Provide the **verdict** comparison layer (§8 level 1): a pure function (e.g.
`segqc/eval/outcome.py`) that, given a case's **expected truth** (a clean GT ⇒
expected `pass`; a known synthetic/curated failure ⇒ expected flag/fail plus its §6
failure mode and expected offending labels) and the pipeline's **actual** verdict +
findings, classifies the case outcome into **TP / FP / TN / FN**, and — for failure
cases — records per-§6-mode **caught / missed** and whether the *designated* rule
fired on the *expected* offending label(s). This is the substrate FPR and
per-mode sensitivity are computed from. No pipeline execution here — records in,
classified outcome out.
*Testable:* a GT case that passes → TN; a GT case wrongly flagged → FP; a
known-failure case caught by its designated rule on the expected label → TP with
that §6 mode marked caught; a known-failure case that passes → FN with the mode
marked missed; ambiguous/partial matches resolve by the documented rule;
deterministic.

### Item 053: Evaluation cohort model & harness driver
Tie the three comparison primitives together into the **evaluation harness**.
Define a **cohort model** — a labelled set of evaluation cases, each carrying a GT
label map, an *optional* candidate/comparison label map (e.g. a segmenter output to
score against GT), and a **ground-truth expectation** (`pass`, or a §6 failure mode
+ expected offending labels) — and a **driver** (e.g. `segqc/eval/harness.py`) that
runs the full `segqc run` pipeline per case and assembles a serialisable per-case
**evaluation record** combining the verdict outcome (052), DICE vs GT (050, when a
candidate is present), and feature-set divergence (051). The cohort abstraction
operates on **any** conforming source so it can consume VerSe GT (positive
control), TotalSegmentator-vs-GT pairs, and the Stage 5 synthetic corpus; it is
tested locally against a synthetic cohort (clean GT + perturbed corpus per the
local-testability note). No metric interpretation yet — the driver only produces
stable records.
*Testable:* driving a small synthetic cohort yields exactly one well-formed record
per case with verdict-outcome always populated and DICE / feature-divergence
populated whenever a candidate is present; a clean-GT case and a perturbed case
produce distinguishable records (pass/TN + high DICE vs flagged + lower DICE);
missing candidate ⇒ overlap/feature fields marked unavailable, not errored;
records serialise deterministically (stable across repeated runs).

### Item 054: Metrics aggregation — FPR, per-failure-mode sensitivity, DICE-vs-flag correlation
Consume the harness records (053) and compute the Stage-7 **metrics** (e.g.
`segqc/eval/metrics.py`): the **false-positive rate on GT** (fraction of clean-GT
cases wrongly flagged), **sensitivity per §6 failure mode** (fraction of each
mode's cases caught by its designated rule), and the **DICE-vs-flag correlation**
(correlation between DICE — or feature divergence — and the flag/verdict signal
across cases). Emit a metrics object carrying the underlying counts (TP/FP/TN/FN,
per-mode caught/missed), the derived rates, and the correlation coefficient with
its sample size. Pure aggregation over records — no pipeline execution.
*Testable:* hand-built record sets yield hand-computed FPR and per-mode
sensitivity; a monotone DICE↔flag relationship yields a correlation of the
expected sign and magnitude; degenerate inputs (no GT cases, a mode with no cases,
zero-variance DICE) yield explicit sentinel values rather than a divide-by-zero
crash; deterministic.

### Item 055: Threshold-calibration loop
Add the **threshold-calibration loop** (e.g. `segqc/eval/calibrate.py`): a
reproducible routine that sweeps candidate heuristic thresholds — the Stage 4
level-aware bounds (`segqc/heuristics/bounds.py`) and the Stage 6
delta-to-reference thresholds (`segqc/heuristics/reference_delta.py`), read from the
versioned config (`segqc/config.py`) — over a documented search grid, re-runs the
harness (053) + metrics (054) at each setting, and **selects** the threshold set
optimising a documented objective (e.g. minimise FPR on GT subject to a
per-mode-sensitivity floor / catching all §6 modes). Deterministic given a fixed
cohort + grid; emits the chosen thresholds together with the metrics achieved. It
**proposes and records** — it does not silently mutate the shipped config
(wiring the chosen values in is 056/057), and it reports "no feasible setting"
rather than crashing when the objective cannot be met.
*Testable:* on a synthetic cohort with a known separating threshold, the loop
selects a threshold in the expected range that satisfies the objective; the search
is deterministic (same cohort + grid ⇒ same choice + metrics); an infeasible
objective is reported explicitly; the chosen-threshold output is well-formed and
consumable by the config-recording step.

### Item 056: Evaluation report (JSON + human) & recorded calibrated results
Render the metrics (054) and chosen thresholds (055) into a versioned
**evaluation report** — a schema-versioned machine-readable **JSON** plus a
**human-readable** summary — and provide the mechanism to **persist the calibrated
results**: write the chosen thresholds into the versioned heuristic config and the
headline metrics into `progress.md`'s "Calibrated metrics" block. The report
captures provenance (cohort identity/size, config + reference artifact versions,
build date) for reproducibility, and is byte-reproducible from fixed inputs (pin
any committed report fixture in `.gitattributes` with `text eol=lf` per the
CLAUDE.md determinism gotcha).
*Testable:* the report serialises deterministically and validates against its
schema; it contains FPR, per-mode sensitivity, the DICE-vs-flag correlation, and
the chosen thresholds with provenance; the human summary renders the same numbers;
the recording mechanism writes calibrated thresholds into the config artifact and
round-trips (load → same values); regenerating from fixed inputs reproduces
identical bytes.

### Item 057: Stage 7 integration & evaluation acceptance suite *(completes Stage 7 & Phase 1)*
Close Stage 7 — and Phase 1 — by wiring the harness → metrics → calibration →
report into a reproducible entry point (a `segqc evaluate` CLI subcommand and/or
`scripts/evaluate.py`) that builds the evaluation cohort (synthetic clean GT +
Stage 5 perturbed corpus, with a documented mounted-VerSe / TotalSegmentator path),
runs the full evaluation, writes the report, and records the calibrated results.
Add the Stage 7 **acceptance suite** asserting the roadmap criteria: GT passes at a
high rate / **low FPR** (**G3**); injected failures are **caught** and the
flag-rate / feature divergence **correlates with DICE** (**G7**); the calibrated
thresholds + metrics are **recorded** and the evaluation is **reproducible**.
Record the final calibrated numbers in `progress.md`'s "Calibrated metrics" block
and mark Phase 1 complete.
*Testable:* the acceptance suite is green — the synthetic-GT cohort yields a low
FPR with no/low false flags, the perturbed corpus is caught at the expected per-mode
sensitivity, and DICE-vs-flag correlation has the expected sign; `segqc evaluate`
runs end-to-end and writes a schema-valid evaluation report reproducibly (two runs
identical modulo normalised volatile fields); the recorded calibrated metrics appear
in the config/`progress.md` output; deterministic / golden-stable.

---

## Current state (2026-07-12)

**Completed — all items ✅ done** (verified against `progress.md` Stage 7, which
is ✅ *Phase 1 complete*): **050** (DICE / overlap), **051** (feature-set match),
**052** (verdict-outcome classification), **053** (cohort model + harness driver),
**054** (metrics), **055** (calibration loop), **056** (evaluation report +
recorded results), and **057** (integration + acceptance) — the latter wiring the
harness into `segqc evaluate` and closing Stage 7 / **Phase 1**. The calibrated
headline metrics (FPR 0.0 on GT, per-mode sensitivities, DICE-vs-flag correlation
-0.943) are recorded in `progress.md`'s Stage-7 "Calibrated metrics" block.
Superseded by [`queue-007.md`](queue-007.md), which opens **Phase 2 (Stage 8 —
Image-Based / Radiomics Features)** behind a human-reviewed queue PR.
