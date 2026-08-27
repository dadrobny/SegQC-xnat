# FACET — Work Queue 017

> **Created:** 2026-08-27
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 28**; supersedes the completed [`queue-016.md`](queue-016.md)
> (Stage 26, closed 2026-08-12).

---

## Scope of this queue

Delivers roadmap **Stage 28 — Spinal Curve Model: Formulation, Offset &
Orientation** (G2, G7) in full: eight items, seven deliverables plus the stage
validation, under `loop.queue_cap = 10`.

`features/spline.py` fits an **interpolating** spline (`splprep(..., s=0)`), so
the curve passes exactly through every centroid it exists to judge. Measured
2026-08-27, two features are therefore structurally incapable of carrying signal:

- `stage3.per_label_offsets[].offset_mm` is zero on all nine committed goldens —
  maximum `6.8e-04` mm against `mislabel`'s `max_offset_mm = 15.0` — and zero on
  real VerSe19 GT (`reference_verse_v1.json`: mean `2.9e-05` mm, CoV 1.3).
- `stage3.monotonic_consistency.is_monotonic` is `True` on every case, including
  `mode4_relabel_swap`, because the spline is fit through the centroids in
  ascending label order and detours through the swapped pair.

Eight leaf paths are affected: `offset_mm`, `offset_voxel`, `dx/dy/dz_mm`, and
all three `per_label_neighbourhood[].stats.offset_mm.*` — so item 110's wiring
aggregates zeros. `MislabelRule` cannot fire through `run_qc` on any input, which
is most of why 6 of 10 registered rules fire on zero corpus cases.

**Why this stage runs before Stage 20.** Stage 20 audits rule↔mode↔feature
traceability and adopts a specificity ratchet. This stage changes which rules
fire on which cases, so auditing first would record a matrix about to move and
pin a specificity baseline against a corpus where `mislabel` cannot fire — the
same reasoning that put Stage 26 ahead of Stage 20, applied more directly. It
also supersedes part of Stage 20's reachability deliverable: modes 1 and 4 are
**one** defect, and the FOV-headroom remedy Stage 20 proposed for mode 1 is
measurably not the cause.

**Prioritisation.** Item 118 is a deliberation and produces no code — it decides
the formulation and raises a human gate, because the deformity envelope the model
must represent is a clinical judgement the corpus cannot supply (the fixtures
carry one fixed 6 mm curve amplitude and no pathology). Everything else waits on
it: 119 implements what 118 decided, 120 and 121 build the two features that only
become measurable once 119 lands, and 123 regenerates the artifacts they all
change. Item 122 (signed curvature) and item 124 (the catalogue's observed-range
column) are independent of the gate and may be claimed in any order alongside the
rest — 124 in particular is worth landing early, since it is the instrument that
would have caught this defect and it makes 123's regeneration auditable.

**Scope fence for the whole queue.** The rethink is **bounded to the spline
layer**. A sweep of every numeric leaf path across both the goldens and the
real-GT reference found no other degenerate feature: the reference's 21 features
all carry genuine spread (CoV 0.06–3.6) except `spline_offset_mm`. The 153 paths
constant across the goldens are constant because all nine fixtures are the same
box built from one base — Stage 21's premise, not a feature defect. An item that
starts redesigning a feature outside the spline layer on that evidence has
misread the stage and should hand back.

**Numbering.** Continues at the next free integer: **118–125**.

---

## Work items

### Item 118: Decide the spinal curve formulation

A recorded design decision, evidenced against real GT, producing **no production
code**. The output is a document plus the measurements behind it, and a human
gate raised for sign-off before item 119 implements anything.

The tension the decision must resolve: the model has to be flexible enough to
represent real spinal shape — cervical lordosis, thoracic kyphosis and lumbar
lordosis give a sagittal S; scoliosis adds a coronal curve, single or double —
while being **too stiff to follow a segmentation error**. A curve fit *from* the
centroids and then used to judge a centroid is circular unless something breaks
the circle.

What must be weighed and written down, each with its consequence stated:

- **Family.** Smoothing spline (today's `splprep` with `s`), fixed-knot
  least-squares B-spline (DoF set explicitly by knot count, which answers "how
  many degrees of freedom" directly rather than through a residual budget),
  per-plane low-order polynomial, or a robust / principal-curve fit that
  down-weights outliers by construction.
- **Degrees of freedom, and how they scale.** A field of view may show five
  lumbar levels or a whole spine, so a fixed knot count cannot serve both. State
  the minimum DoF that represents a normal spine over the levels present, and
  the maximum beyond which the fit starts absorbing a displaced vertebra.
  Note that `splprep`'s `s` is an **absolute** sum-of-squared-residuals bound in
  mm², so it scales with both point count and coordinate magnitude and cannot be
  a literal constant — whatever family is chosen, the parameter must be
  expressed scale-free.
- **Parameterisation.** Arc length / chord length versus treating the curve as a
  function of the cranio-caudal coordinate. The latter is simpler and monotonic
  **by construction** — which would destroy the mode-4 ordering signal this stage
  exists to restore. Record the choice and why.
- **How circularity is broken.** Leave-one-out fitting (the point under test is
  excluded), robust down-weighting, or an external prior from the reference
  distribution. These have different costs — leave-one-out is *n* fits per case;
  robust fitting changes the curve for every consumer; a reference prior needs a
  reference that is itself sound.
- **The deformity envelope.** How much curvature is normal anatomy the model must
  follow versus deviation it must report. This is the gated question.

Judged against criteria measurable now, not argued in the abstract: clean GT
stays inside item 017's 0.5 mm pass-through bound across level counts and
spacings; a displaced vertebra separates from the clean distribution by a stated
margin; a real scoliotic curve in the VerSe cohort is not flagged; 2-level and
truncated-FOV inputs neither crash nor degenerate; the fit is deterministic
run-to-run. The VerSe19 cohort is available locally (80 CT/GT pairs) for all of
these. *Testable:* the decision document states a choice for each bullet with its
consequence and the measurement supporting it; a candidate-comparison script
reproduces every quoted number; the human gate is raised and recorded in
`progress.md`.

### Item 119: Implement the chosen curve formulation

Replace `splprep(..., s=0)` in `features/spline.py` with what item 118 decided,
with the smoothing / degrees-of-freedom parameter in the scale-free form that
item's measurements support. Blocked on the human gate. `SplineFit` may gain
fields but its existing consumers — `spline_offset.py`, `consistency.py`,
`orientation.py`, `neighbourhood.py` — must keep working, and item 017's AC1
(0.5 mm pass-through **on GT fixtures**) still holds: it was never the defect,
`s=0` merely over-satisfied it in a way that held on broken input too. Expect the
committed goldens to change; regenerating them is item 123's job, so this item
should leave the corpus tests red in a way item 123 clears rather than adjusting
fixtures to hide the change. *Testable:* a clean spine's maximum offset stays
under 0.5 mm across level counts and spacings; a displaced vertebra's offset
exceeds the clean maximum by the margin item 118 stated; two fits of the same
input are identical; a 2-level input and a truncated-FOV input both fit without
error.

### Item 120: Per-vertebra offset that separates, with its direction components

Make `stage3.per_label_offsets[]` carry signal, and wire the per-direction
components that already exist. `dx_mm/dy_mm/dz_mm` are computed and catalogued
today but read by no rule — only `offset_mm`, `label` and `level_name` reach
`mislabel`. Their anatomical meaning holds because `io.load_volume` reorients
every volume to RAS, while `compute_centroid` itself does `centroid_voxel *
spacing` with no affine; state that contract where the feature is defined rather
than leaving it implicit.

If item 118 chose leave-one-out, promote it from the test harness into the
pipeline: `_recon_leave_one_out_offset` (`synth/regression.py:116`) already
implements it and a leave-one-out fit tracks displacement roughly 1:1 (measured
5 → 6.2 mm, 10 → 10.4 mm, 15 → 16.0 mm, 19 → 18.9 mm). Doing so retires mode 1's
`reconstructed_record` workaround rather than working around it, and the corpus
case moves to `detection="pipeline"`. *Testable:* `mislabel` fires through plain
`run_qc` on the mode-1 case naming the displaced label, and the clean control
still fires nothing; `mode1_displace` no longer needs a reconstruction; the
recalibrated `max_offset_mm` sits between the clean and displaced distributions
with both margins recorded; a rule reads the direction components, or they are
explicitly recorded as inventory.

### Item 121: Tangent-based vertebra orientation

PCA's `principal_axis` returns exactly `(1.000, 0.000, 0.000)` for **every**
vertebra of the default fixture, with identical `eigenvalue_ratio` 1.441: the
voxel cloud is a 30×25×25 box and PCA finds its widest side, which is left-right
on a real vertebra too. It tracks no tilt, varies with no level, and no rule
reads it.

Add the estimate item 118's curve makes available: the closest point of the
centroid on the spline, and the curve tangent there. Both ingredients exist and
are never joined — `closest_u` in `spline_offset.py`, and `splev(..., der=1)` in
`orientation.py`, which evaluates at `fit.u` rather than at the centroid's
closest point and collapses the result to a scalar angle. Measured on the clean
fixture, the tangent estimate varies sensibly where PCA does not: +5.7°, +5.0°,
0°, −5.0°, −5.7° across L1–L5, tracking the 6 mm curve amplitude. This is a
per-vertebra orientation **proxy**, not a vertebral coordinate system, and should
say so where it is defined. Retain `eigenvalue_ratio` — it carries real variance
on real GT (VerSe L1 mean 2.15, range 1.56–2.68), unlike the synthetic constant.
Demote `principal_axis` to a documented-questionable status rather than deleting
it. *Testable:* the tangent estimate varies across levels on a curved spine and
is near-constant on a straight one; PCA's constancy across the fixture is pinned
by a test so its demotion is evidenced; `eigenvalue_ratio` is unchanged.

### Item 122: Signed curvature

`total_curvature_deg` is `max − min` of the **unsigned** angle between each
tangent and the cranio-caudal axis. On the clean fixture it reports **5.702°**
where the true L1→L5 tangent sweep is **11.4°** — the sum of
`inter_tangent_angles_deg`, which the same function already computes correctly.
It halves a C-curve and cancels a symmetric S-curve, which is the shape a normal
spine actually has, so the "Cobb-angle-like proxy" it is documented as cannot
distinguish a straight spine from a balanced double curve. Give the descriptor a
sign convention so opposing curvature does not cancel, and state which plane each
number refers to. Independent of the human gate — the defect is in how tangents
are reduced to a scalar, not in the fit. *Testable:* a symmetric S-curve fixture
and a straight fixture produce different values; a C-curve's reported curvature
matches its tangent sweep; the descriptor's plane and sign convention are
documented and asserted.

### Item 123: Recalibrate and regenerate every downstream artifact

Everything the curve change invalidates, in one item so the regeneration is
auditable rather than scattered: `mislabel`'s `max_offset_mm`, the nine committed
goldens, `reference_default.json`, and `reference_verse_v1.json`. The last is
the one that matters most — it currently commits a per-level distribution for
`spline_offset_mm` built from real GT whose mean is `2.9e-05` mm, i.e. a
distribution of noise about zero.

The VerSe19 cohort **is** available on this machine: 80 CT/GT pairs, reachable
through a gitignored symlink at the root path `dataset-verse19training`, with
`sub-verseNNN_seg-vert_msk.nii.gz` matching `refresh_reference.py`'s default
`--verse-seg-suffix`. Two corrections belong with the rebuild:
[`dataset-verse19.md`](../dataset-verse19.md) documents a nested
`dataset-verse19training/dataset-verse19training/` layout (the zip-extraction
wrapper) that the symlink deliberately skips; and `.gitignore`'s entry needs no
trailing slash, because a trailing slash matches directories only and let the
symlink show as an untracked, committable file. Record the cohort path as
machine-local configuration rather than re-asserting a fixed path contract.
*Testable:* every golden regenerates byte-identically run-to-run within a
session; both reference artifacts rebuild from real GT and `spline_offset_mm`
shows real spread; the recalibrated threshold is justified by the recorded clean
and displaced distributions; the symlink is ignored by `git status`.

### Item 124: Observed-range column in the generated feature catalogue

The catalogue is current — item 104's drift test is green and the `computation`
column is accurate everywhere — but it has no column for what a feature *does*.
`offset_mm`'s row reads perfectly healthy while the value is a constant zero, and
its `status` is `retune`, shared with 65 of 128 rows, so it discriminates nothing.
Record each numeric leaf path's observed range across two populations: the corpus
run, and the reference cohort. This is the instrument that would have caught this
defect at item 018 instead of after a reference build on 59 real cases, and it
makes item 123's regeneration auditable at a glance.

It must distinguish the two reasons a value can be constant, or it will cry wolf:
153 golden paths are constant because all nine fixtures are the same box from one
base (Stage 21's premise), not because anything is broken — only the real-GT
population separates that from a genuinely dead feature. Generated like the rest
of the catalogue, never hand-maintained. Independent of the human gate. *Testable:*
the column is populated for every numeric path from both populations; a
deliberately zeroed feature is flagged; a legitimately-constant synthetic path is
not flagged on the strength of the corpus alone; the artifact stays
byte-reproducible and the drift test still agrees.

### Item 125: Validate stage 28: Spinal Curve Model

Replay Stage 28's use cases end-to-end rather than re-running the unit suite.
Confirm the human gate was resolved by a person before item 119 landed, and that
the decision document's quoted measurements still reproduce against the shipped
formulation. Run a full case through `segfacet run` on a fixture with one
displaced vertebra and confirm `mislabel` fires end-to-end naming that label, and
on the clean control confirming it fires nothing (**G2**); run the mode-4 case
and confirm `is_monotonic` is `False` with the swapped pair named (**G2**). Take
a genuinely scoliotic case from the VerSe cohort and confirm its curve is not
reported as an offset outlier (**G3**) — if no such case can be identified,
record that as the finding rather than skipping the criterion. Confirm the
before/after detection count honestly in `progress.md`: how many of the 8 modes
fire through plain `run_qc` now versus the 5 that did. Confirm both reference
artifacts were rebuilt from real GT rather than edited, and that every golden is
byte-reproducible on a **fresh clone in a different directory**. Then update
`progress.md`: tick Stage 28's five acceptance criteria against what was actually
exercised, and flip any Environment-Gated Capability Verification row this stage
affects to ✅ Verified where the environment allows (`python
.aide/scripts/aide.py env --profile <name>`), otherwise record why it stays ❓
Unverified. *Testable:* each acceptance criterion is ticked with a recorded
evidence sentence naming what was run; the fresh-clone suite is green; `aide
check` reports no new warnings.

---

## Current state (2026-08-27)

Generated on completion of [`queue-016.md`](queue-016.md), which delivered
**Stage 26 — Carried-Defect Remediation (pre-real-data)** (items 107–116, all
✅). Opens **Stage 28 — Spinal Curve Model**, scoped 2026-08-27 after measuring
that `offset_mm` and `is_monotonic` carry no signal on either the synthetic
corpus or real VerSe19 GT. Run order from here: **28 → 20 → 27 → 21 → 16**.
Stage 20 (traceability matrix + specificity ratchet) is authored as a queue only
after this stage lands, because two of its planned deliverables are superseded
here. Stage 16 remains held by two human gates awaiting a decision — real
segmenter output handed over to this repo, and access to the curated
challenging-case source data. Stage 11 stays ⏸️ Deferred and Stage 15 ❌ Excluded.
