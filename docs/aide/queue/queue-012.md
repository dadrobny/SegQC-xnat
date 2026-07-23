# Seg-QC-xnat — Work Queue 012

> **Status:** Live · **Created:** 2026-07-17
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Opens **Stage 14**; supersedes the completed [`queue-011.md`](queue-011.md)
> (Stage 13, closed 2026-07-17).

---

## Scope of this queue

Delivers roadmap **Stage 14 — Real-Data Grounding & Heuristic Recalibration**
(G3) in full: re-ground the heuristics in the **real** VerSe-derived
distributions now available, so real ground truth passes QC — **without** buying
that specificity by blinding the rules.

**Why this exists (2026-07-17).** Stages 6/7 calibrated the heuristics against a
5-subject *synthetic* VerSe stand-in and recorded a false-positive rate of
**0.0**. Stage 13's adapter made the real cohort readable with no manual staging,
and the first real measurement — build on VerSe19 **training** (80 subjects,
→ `reference_verse_v1.json`, 25 levels C1…S), evaluate on the **disjoint**
held-out splits — put the real FPR at **0.925** (validation, 40) / **0.975**
(test, 40). The rules are conflating legitimate real-world variation with
failure. This is the gap between "the code works" and "the tool works", and it is
the single reason objective **G3 is 🚧** (see [`../progress.md`](../progress.md)'s
"Two kinds of done").

**The diagnosis is specific, not a mystery.** Contributing rules on the held-out
run: `bounds` (4/6 of flagged cases), `fragmentation` (3/6), `coverage` (3/6 —
partial-FOV scans read as "missing levels"), `border` (2/6). One real case passed
entirely clean, which rules out a systematic bug and points squarely at
calibration + rule semantics.

**Design principle — the three planes stay separate** (carried over from queue-011).
Plane 1 (code/function testing on synthetic fixtures) must stay green and
reproducible: `reference_default.json` remains the seeded synthetic test baseline
and the goldens must not move except where a rule's semantics deliberately
change. Plane 2 (building the real-GT knowledge base) is what this queue
recalibrates against. Plane 3 (scoring new automatic segmentations) is Stage 16.

**The anti-gaming constraint — read this before touching a threshold.** FPR is
trivially driven to 0.0 by loosening or disabling rules. **FPR and sensitivity are
a single acceptance pair**: no item here may improve the real-GT FPR without
demonstrating that per-mode sensitivity has not regressed below item 057's
recorded baseline (5/8 pipeline-detectable modes at 1.0). Item 091 makes that
guard executable; items 089/090 must keep the existing Stage-5 regression suite
green on their own.

**Prioritisation & sequencing.** **Rule semantics first** (089 — FOV-awareness),
because a partial-FOV scan is not a defective one and no amount of threshold
tuning can express that; a mis-specified rule tuned to fit real data would just
launder the error into a threshold. Then the distribution-grounded defaults (090),
which the item-048 switch already supports. Finally the calibration run +
held-out measurement + sensitivity guard + stage closure (091), which is
environment-gated on the mounted VerSe cohort. Recommended order: **089 → 090 →
091**.

**Key constraint — real VerSe data is not committed.** Items 089/090 are fully
testable on **synthetic fixtures** (cropped-FOV and real-distribution-shaped) plus
the committed `reference_verse_v1.json` (a derived artifact — no raw scans).
Item 091's real-cohort clause is gated on a mounted-cohort detector and **skips
cleanly when absent** (mirroring items 069/084/088).

### Numbering note

Items 001–088 are complete (Stages 0–13 ✅). This queue continues at the next free
integer: **089–091**.

**Estimated size:** ~1 week (3 items, within `loop.queue_cap = 10`).

### Stage-14 deliverable → item coverage

| Stage-14 deliverable | Delivered by item |
|---|---|
| FOV-aware `coverage` / `border` rules | 089 |
| Reference-derived bounds by default; `fragmentation`/`bounds` tolerances re-derived from real per-level variation | 090 |
| Recalibration run (train-fit / held-out-measured), anti-gaming sensitivity guard, recorded metrics + G3 closure | 091 |

---

## Work items

### Item 089: FOV-aware `coverage` and `border` rules
Teach the `coverage` and `border` rules the difference between **absence** and
**absence of evidence**. Real scans are legitimately partial (cervical-only,
lumbar-only, thoraco-lumbar): today a level outside the scan's field of view is
reported as a *missing level*, and a vertebra clipped by the FOV boundary is
reported as a *border defect* — together 5/6 of the held-out false positives.
Derive the FOV-covered level span from the label map + image geometry (the
extremal segmented levels and their proximity to the volume bounds), and restrict
`coverage`'s expected-sequence check to levels **expected inside the FOV**;
similarly, a label touching an image border **at the ends of the covered span** is
normal, whereas one touching a lateral/anterior border, or an interior label
touching any border, remains suspicious. Keep the existing failure semantics
intact for genuinely missing interior levels (§6 mode 5) and genuine border
truncation (mode 6). *Testable:* synthetic fixtures cropped to cervical-only /
lumbar-only / mid-thoracic FOV do **not** fire `coverage`/`border`, while a
fixture with an interior level removed still fires `coverage` and one truncated
mid-span still fires `border`; the Stage-5 regression suite and its golden
snapshots stay green except where a deliberately changed semantic is re-recorded
with justification.

### Item 090: Reference-derived bounds by default, grounded on real VerSe distributions
Ship the reference-derived path as the **default**. Item 048 already built the
config switch from hand-set to reference-derived bounds, but the shipped default
is still the synthetic-calibrated hand-set constants that flag 4/6 of held-out
real GT via `bounds` and 3/6 via `fragmentation`. Point the default heuristic
config at the committed `reference_verse_v1.json` (real, 25 levels C1…S, 80
training subjects) and re-derive the `bounds` and `fragmentation` tolerances from
**real per-level variation** (percentile-based) rather than synthetic-clean
geometry — real GT contains small legitimately-disconnected fragments and a much
wider per-level volume/extent spread than the synthetic spine. Levels absent from
the reference must degrade to the current hand-set behaviour, not crash.
*Testable:* the default config resolves to reference-derived bounds sourced from
`provenance.source == "verse-v1"`; per-level tolerances match the artifact's
recorded percentiles; a level absent from the reference falls back cleanly; the
synthetic corpus's expected verdicts still hold (a real-grounded bound must not
un-flag a synthetic over/under-segmentation); `reference_default.json` remains the
untouched synthetic test baseline.

### Item 091: Real-GT recalibration, held-out measurement + sensitivity guard *(completes Stage 14)*
Run the Stage-7 `calibrate.py` grid search **fitted on the VerSe19 training subset
only**, then measure the result on the **held-out** validation/test subsets,
resolved as disjoint adapter subsets so the framework only ever sees "calibration
cohort" and "eval cohort" (no circularity, no split concept in the framework).
Add the **anti-gaming sensitivity guard** as an executable gate: re-run the
Stage-5 synthetic corpus **and** Stage-5 perturbations applied to **real** VerSe
GT, asserting per-mode sensitivity does not regress below item 057's baseline.
Record the resulting FPR/sensitivity pair in `progress.md`, update the "Real VerSe
GT" verification row, and flip **G3 → ✅ only if** held-out FPR ≤ 0.10 **and** the
sensitivity guard passes — otherwise record the achieved numbers honestly and
leave G3 🚧 with the trade-off curve. `roadmap.md`/`vision.md` are PR-gated and not
edited by this direct-merge item. *Testable:* the calibrate → held-out-evaluate
path runs end-to-end over a **synthetic stand-in** in CI (well-formed metrics, the
fit cohort provably disjoint from the eval cohort); the sensitivity guard fails
loudly on a deliberately over-loosened config (proving it can't be gamed); the
real-cohort clause is a genuine `skipif` that skips cleanly on a data-absent host.

---

## Current state (2026-07-17)

Generated after the Stage-13 adapter landed and the **first real-data processing**
of the project (2026-07-16/17), whose results falsified G3's synthetic-backed ✅
and prompted an over-claim audit across all stages. Opens **Stage 14 — Real-Data
Grounding & Heuristic Recalibration** and supersedes the completed
[`queue-011.md`](queue-011.md).

Stage 14 is the **actionable** third of the new real-data validation arm. Its two
siblings are scoped in the roadmap but deliberately **not queued**, as both are
blocked on resources the project does not yet have rather than on engineering:
**Stage 15** (real-XNAT deployment validation, G5) needs a reachable XNAT server
with the Container Service enabled; **Stage 16** (real failure corpus, G2/G7)
needs TotalSegmentator/SPINEPS outputs over real CT and depends on Stage 14
landing first — sensitivity is only meaningful against the rules we intend to
ship. Queue them when the prerequisite exists.
