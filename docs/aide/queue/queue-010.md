# Seg-QC-xnat — Work Queue 010

> **Status:** Completed (all 4 items 081–084 merged 2026-07-16; Stage 12
> closed) · **Created:** 2026-07-15
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Prioritised ahead of [`queue-009.md`](queue-009.md) (Stage 10 GPU, now
> `Planned`/deferred) per the 2026-07-15 feedback-loop decision.

---

## Scope of this queue

Delivers roadmap **Stage 12 — Real-VerSe Grounding & Reference Feature
Expansion (G3, G7)** in full. Stages 6 and 7 shipped their machinery
(reference-distribution ingestion/aggregation, delta-to-reference rules,
evaluation harness) against a **synthetic** 5-subject VerSe-shaped cohort
(`src/segqc/reference/reference_default.json` →
`provenance.source == "synthetic-verse-cohort"`). This queue closes the gap
between *"the pipeline can be grounded in VerSe"* and *"the pipeline has been
grounded in, and evaluated on, real VerSe"* — and, along the way, widens the
reference feature set from its current narrow slice to the full set of
discriminative per-level scalars the engine already computes.

**Why this exists (feedback-loop finding, 2026-07-15).** The status summary
surfaced that `reference_default.json` aggregates only **5 geometric + 13
intensity = 18 features**, while the Stage-2/3 engine computes many more
per-label scalars (fragmentation index, largest-component fraction, component
count, centroid depth, orientation, spacing/neighbour-consistency deviations)
that never made it into the reference distributions — and that the bundled
artifact is a synthetic stand-in, not real VerSe. Both are tracked: the latter
as the "Real VerSe GT" row in `progress.md`'s Environment-Gated Capability
Verification table.

**Prioritisation & sequencing.** **Feature expansion first** (item 081) — it is
independent of data access and doable immediately against the synthetic cohort,
so that when real VerSe is ingested the richer distributions come for free.
Then the real-VerSe build recipe (082) and the refresh wrapper (083) — 083
depends on 081/082's final CLI/artifact shape. The real-VerSe evaluation +
verification (084) closes the stage and depends on everything. Recommended
order: **081 → 082 → 083 → 084**.

**Key constraint — real VerSe data is not committed.** VerSe raw scans are
large and licensed, so they are never committed; only the *derived*
distributions artifact is. Every item that would touch real VerSe (082's build,
083's refresh, 084's evaluation) **must degrade gracefully when the VerSe
cohort is absent** — skip cleanly, never fail — exactly mirroring the
environment-gated-capability pattern (items 060/069/077–080). Only item 081
(feature expansion against the synthetic cohort) runs unconditionally
everywhere.

### Numbering note

Items 001–080 are complete or specced (Stages 0–9 ✅; Stage 10 items 071–075
specced in queue-009, deferred). This queue continues at the next free integer:
**081–084**.

**Estimated size:** ~1–1.5 weeks (4 items, within `loop.queue_cap = 10`).

### Stage-12 deliverable → item coverage

| Stage-12 deliverable | Delivered by item |
|---|---|
| Expanded reference feature vocabulary | 081 |
| Real-VerSe acquisition & versioned artifact build recipe | 082 |
| One-command refresh wrapper (graceful without VerSe data) | 083 |
| Real-VerSe evaluation & verification-table closure | 084 |

---

## Work items

### Item 081: Expand the reference feature vocabulary to the full discriminative scalar set
Widen the ingested/aggregated per-level feature set beyond today's 5 geometric
(`physical_volume_mm3`, `extent_x/y/z_mm`, `spline_offset_mm`) + 13 intensity
scalars to add the discriminative Stage-2/3 scalars the engine **already
computes** but the reference ignores: `fragmentation_index`,
`largest_component_fraction`, `component_count`, centroid depth (EDT, item 023),
per-label orientation (item 019/024), and spacing/neighbour-consistency
deviation (item 024). Thread each new feature through the whole reference path —
`INGESTED_FEATURES` in `segqc.reference.ingest`, the aggregation core
(`aggregate`), the delta-to-reference rules (`delta`, items 046/047/064), and
the switchable heuristic config — preserving the existing geometric/intensity
vocabulary split. Regenerate the committed synthetic `reference_default.json`
(via `python -m segqc.reference.artifact`) so it carries the expanded set.
*Testable:* the rebuilt synthetic artifact contains the new feature keys with
well-formed per-level stats; the delta rules read them; the existing Stage-6
integration + acceptance tests (items 048/049) still pass; a determinism/
byte-identity check on the regenerated default holds within the item-078
tolerance. No real VerSe data required — this item runs entirely against the
synthetic cohort.

### Item 082: Real-VerSe acquisition & versioned artifact build recipe
Document and script the process to mount a **real VerSe GT** cohort and build a
separately **versioned** reference artifact (`reference_verse_vN.json`,
`provenance.source == "verse-vN"`) via `segqc build-reference --cohort
/mnt/verse --out … --source verse-vN --build-date …`. Define the project
storage strategy explicitly: commit the *derived distributions artifact* only,
**never** the raw VerSe scans (large / licensed); keep the synthetic default as
the test/determinism baseline; document how a deployment selects the real-VerSe
artifact (bundle-swap or `--reference-artifact` mount). Add acquisition/mount
notes (where VerSe comes from, expected directory/`_seg.nii.gz` layout).
*Testable:* the build recipe is exercised against a **tiny synthetic
VerSe-shaped fixture cohort** standing in for real VerSe (a real cohort is not
committed), asserting a well-formed versioned artifact with the correct
`provenance.source`/`build_date`; a documentation-presence check confirms the
acquisition + storage-policy notes exist; when no cohort directory is present
the build errors clearly (non-zero, no partial artifact), not with a traceback.

### Item 083: One-command reference-refresh wrapper (graceful without VerSe data)
Add a re-runnable script/target (e.g. `scripts/refresh_reference.py` or a
`segqc`-adjacent entry point) that, in one invocation: (a) rebuilds the
synthetic default reference artifact; (b) **if** a real VerSe cohort path is
provided/mounted, rebuilds the versioned real-VerSe artifact too; and (c)
re-runs the Stage-7 `segqc evaluate` over the available cohort(s), so "we added
a feature / changed config → refresh everything" is a single command usable in
CI. **The real-VerSe steps must degrade gracefully when the cohort is absent**
(the common case, since VerSe is not committed): skip cleanly with a clear
message, never fail, and still complete the synthetic rebuild + evaluation —
mirroring the environment-gated-capability pattern (items 069/077–080). *Testable:*
unit/integration tests drive the wrapper with (i) no VerSe path → synthetic
rebuild + evaluation succeed and the real-VerSe steps report a clean skip
(asserted structurally, not a silent no-op), and (ii) a tiny synthetic
stand-in cohort supplied as the "VerSe" path → the versioned artifact is
produced; the wrapper is deterministic and writes into a caller-specified
output dir.

### Item 084: Real-VerSe evaluation & verification-table closure *(completes Stage 12)*
Run the Stage-7 evaluation (`segqc evaluate`) over a **real VerSe GT** cohort to
quantify objective **G3** (GT segmentations pass QC at a high rate / low
false-positive rate) and record the metrics (FPR on GT, per-mode sensitivity
where applicable) in the evaluation report and `progress.md`. Reconcile
`progress.md`: flip the **"Real VerSe GT" row** in the Environment-Gated
Capability Verification table from `❓ Unverified` to `✅ Verified (date,
cohort/host)`, and close the Stage-12 section — `roadmap.md` is PR-gated and is
**not** edited by this direct-merge item (mirror items 049/057/065/070/075).
Because real VerSe is not committed, this item's automated portion must **skip
cleanly** when the cohort is absent and record that it remains unverified; the
verification-table flip happens only when a human/CI runner with real VerSe data
actually runs it. *Testable:* the evaluation path is exercised end-to-end
against the synthetic stand-in cohort in CI (asserting a well-formed
`eval_report.json` with an FPR metric), and the real-VerSe closure is
structurally gated (skips cleanly without the cohort); a check asserts the
verification-table row is only marked Verified when accompanied by a recorded
cohort id + date.

---

## Current state (2026-07-15)

Freshly generated from the 2026-07-15 feedback-loop plan; this is the **Live**
queue, prioritised ahead of the now-`Planned` [`queue-009.md`](queue-009.md)
(Stage 10 GPU). It opens **Stage 12 — Real-VerSe Grounding & Reference Feature
Expansion**. No Stage 12 items claimed yet. **081** (feature expansion) is
independent of data access and should land first; **082** (real-VerSe build
recipe) and **083** (refresh wrapper) follow; **084** (real-VerSe evaluation)
closes the stage. Every real-VerSe-touching item degrades gracefully when the
(uncommitted) VerSe cohort is absent. This queue lands together with the Stage-12
roadmap addition via a single human-reviewed PR (roadmap is PR-gated).
