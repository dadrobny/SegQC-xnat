# Seg-QC-xnat — Work Queue 002

> **Status:** Draft v1 · **Created:** 2026-06-26
> Step 4 of the AIDE workflow. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-001.md`](queue-001.md) (items 001–010).

---

## Scope of this queue

Completes roadmap **Stage 2 — Geometric & Topological Feature Extraction** and
delivers **Stage 3 — Spinal Curve: Spline Fit & Geometric Deviation Features**
in full.

**Milestone delivered:** the spinal-geometry feature engine is finished — the
remaining Stage 2 features (inter-vertebra relationships, features serialised
into the JSON report) plus the entire Stage 3 centroid-spline layer (spline fit,
per-vertebra spline offset, orientation/curvature, neighbour-consistency,
sagittal projection). On completion the pipeline emits a complete, validated
`features` block whose deviation features are near-zero for ground truth and
large for displaced/mislabelled/missing-level cases — exactly the signal the
Stage 4 heuristic rule engine consumes.

**Prioritisation rationale.** The roadmap graph is linear through Stage 3
(`… → 2 → 3 → 4`). Items 011–013 and 015 already landed; only two Stage 2
deliverables remain (inter-vertebra relationships, features-to-JSON), and Stage 3
depends directly on them (the spline needs the *ordered* centroid sequence).
Finishing Stage 2 and building Stage 3 as a single batch keeps the geometry work
in one coherent milestone before the heuristic engine begins.

### Numbering note — read before picking an item

This queue **fills reserved gaps** rather than starting at the next free integer,
to honour cross-references already committed in the item specs
(see [`../items/013-centroids.md`](../items/013-centroids.md): *"Inter-vertebra
relationships → Item 014"*, *"JSON serialisation → Item 016"*, *"Items 017–020
(Stage 3 spline)"*):

- **Item 014** (inter-vertebra relationships) and **Item 016** (features-to-JSON)
  were earmarked but never created — they are the two outstanding Stage 2
  deliverables and are queued here.
- **Item 015** (overlap detection) is **already complete** — it was executed out
  of order and is *not* in this queue.
- Stage 3 continues at **017–022**.

So the queue is not strictly monotonic on the page (014, 016, 017…); that is
intentional. Numbers 011–013 and 015 are done; this queue uses 014, 016–022.

**Estimated size:** ~1 week (8 items). Each item is independently testable
locally with `pytest` against the synthetic fixtures from item 002.

**Sequencing note.** Original critical path 014 → 017 → 018 is done. Remaining
path: 019 → 020 → 022. Item 023 (EDT centroid) is a Stage 2 enhancement that
runs independently and feeds into item 024 and Stage 4 heuristics. Item 024
(neighbourhood comparison) depends on 017 and 020. Items 021 (sagittal
projection) and 023 are largely independent and can be picked up in parallel
with 019/020.

---

## Work items

### Item 014: Inter-vertebra relationships — ordered sequence, neighbour spacing, continuity *(completes Stage 2 feature set)*
Build on the per-label centroids (013) to compute inter-vertebra relationships:
order the present vertebra centroids along the spine (superior→inferior), compute
Euclidean **neighbour spacing** between consecutive centroids in both voxel and
mm space, and assess **label-sequence continuity** — detecting gaps, reversals,
or non-anatomical jumps (e.g. L1→T12→L2→L5) against the expected ordered level
sequence from the label convention (004). Emit a structured, deterministic
per-case relationship record (ordered labels, neighbour distances, continuity
findings with offending labels).
*Testable:* unit tests over labelled-block and anisotropic fixtures assert
correct ordering, neighbour-spacing values vs hand-computed expectations, and
that out-of-order / gapped / duplicated label sets are correctly identified;
deterministic output; missing or single-label maps handled without crashing.

### Item 016: Features-block JSON serialisation & per-case feature table *(completes Stage 2)*
Consolidate all Stage 2 features — per-label geometry (011), connected-components
(012), centroids (013), inter-vertebra relationships (014), overlap (015), EDT-
based centroid variants and centroid depth (023) — into the versioned JSON report
under a `features` block, and render a per-case **human-readable feature table**.
Include the **fragmentation index** (largest component / total volume ratio,
derived from item 012 data) as a per-label scalar in the features block. Extend
the report schema (009) to cover the features block with validation, and record
the config/schema version.
*Testable:* serialised reports validate against the extended schema; golden-
snapshot tests confirm deterministic output; an anisotropic fixture round-trips
correct physical volumes/extents; tests assert every feature family (including
fragmentation index, centroid depth, EDT centroid variants) appears in the JSON.
Satisfies the Stage 2 acceptance criteria.

### Item 017: Centroid spline fit (robust to missing levels)
Fit a smooth spline (parametric cubic / B-spline via SciPy) through the **ordered**
vertebra centroids from item 014, producing a continuous spinal-curve
representation that can be sampled at arbitrary parameter values and arc-length.
Must be robust to a deliberately missing level (no crash, sensible interpolation)
and to as few as 2–3 centroids, with graceful, documented behaviour for
degenerate inputs (1 centroid, collinear points).
*Testable:* unit tests fit on GT fixtures and assert the curve passes within
tolerance of the input centroids, remains stable when a level is removed, and is
deterministic; degenerate inputs handled without raising uncaught errors.

### Item 018: Per-vertebra offset from the spline
Compute each vertebra centroid's **perpendicular offset** from the fitted spline
(017) — distance plus signed components — in voxel and mm space. Offsets are
near-zero for centroids lying on a smooth curve and large for displaced or
mislabelled vertebrae.
*Testable:* unit tests assert near-zero offsets for GT fixtures and large offsets
for a synthetically displaced centroid; anisotropic spacing applied correctly;
deterministic.

### Item 019: Vertebra orientation/rotation & global curvature descriptors
Estimate per-vertebra **orientation/rotation** (principal-axis direction of each
label's voxel cloud via PCA) and **global curvature descriptors** along the
spline (local tangent angles, total curvature / Cobb-like angle proxy).
*Testable:* unit tests assert the recovered principal axis for a deliberately
elongated/rotated synthetic block, and sensible curvature values distinguishing a
straight from a curved synthetic centroid arrangement; deterministic and
spacing-aware.

### Item 020: Neighbour-consistency metrics (spacing regularity & monotonic progression)
Derive **neighbour-consistency** metrics from the ordered sequence (014) and the
spline (017): spacing-regularity scoring (variation / outliers in inter-centroid
distances) and **monotonic progression** along the curve (spline parameter
increases consistently with anatomical order; detect swapped / non-monotonic
levels). Emit per-vertebra and per-case findings with offending labels.
*Testable:* unit tests assert regular GT spacing scores within tolerance, flag an
injected spacing outlier, and detect a swapped / non-monotonic ordering;
deterministic.

### Item 021: Sagittal projection of centroids & spline (human-report visual)
Render an optional 2-D **sagittal projection** of the vertebra centroids and the
fitted spline (017) for the human-readable report (matplotlib figure or
lightweight image written to the output directory), with a graceful no-op when
the plotting backend is unavailable so the pipeline never hard-requires it.
*Testable:* unit tests confirm an image artifact with the expected centroid /
spline markers is produced for a fixture, the output path is recorded in the
report, and the function degrades gracefully (no crash) when the optional backend
is absent.

### Item 022: Stage 3 feature serialisation & GT-vs-perturbed regression tests *(completes Stage 3 — spline features)*
Serialise the Stage 3 deviation features — spline offset (018), orientation /
curvature (019), neighbour-consistency (020) — into the JSON `features` block
(extending 016), and add regression tests over **GT plus perturbed** cases.
*Testable:* end-to-end tests assert the new features appear in validated JSON;
offsets / consistency scores are within tolerance for GT fixtures and clearly
out-of-range for displaced, mislabelled, and missing-level perturbations; golden
snapshots are deterministic.

### Item 023: EDT-based centroid variants & centroid depth *(Stage 2 enhancement)*
Extend `segqc/features/centroids.py` with two additional centroid computation
methods alongside the existing CoM baseline: **smooth centre** (centre of mass of
the EDT-thresholded mask, threshold configurable at e.g. 50 % or 75 % of the max
EDT value) and **strict centre** (peak of the Gaussian-smoothed EDT — the single
deepest interior point). Add **centroid depth** as a per-label scalar: the EDT
value at the chosen centroid position, quantifying how far inside the label the
centroid lies (low values flag near-surface or outside-label centroids). C1 and
C2 are flagged as anatomically special (no classic vertebral body) and their
centroid-depth interpretation documented. Results stored in an extended
`LabelCentroid` record (or a companion `CentroidFeatures` dataclass). Note: item
017 is already merged using simple CoM centroids; 023 improves the centroid
quality and downstream items (024, Stage 4 heuristics) can consume the better
values.
*Testable:* unit tests assert smooth-centre and strict-centre lie closer to the
geometric interior than CoM for a hollow/concave synthetic label; centroid depth
is positive for a well-placed centroid and near-zero for one on the surface;
C1/C2 flags set correctly; deterministic.

### Item 024: Local vertebra neighbourhood comparison *(completes Stage 3)*
Using the ordered centroid sequence (014), spline offset per vertebra (018), and
per-label geometry (011), compute **local neighbourhood features** via a sliding
window of configurable width n (default n=3, i.e. ±1 neighbour on each side):
for each vertebra, the mean/median and deviation of centroid spacing, spline
offset, and label volume within its local window. Emit a **per-vertebra
neighbourhood deviation score** and flag vertebrae whose local deviation exceeds a
configurable threshold as anatomical outliers. This catches isolated failures
(displaced or mislabelled single vertebra within an otherwise-consistent spine
segment) that global-mean comparisons miss.
*Testable:* unit tests assert near-zero deviation for a regular GT fixture;
a single injected outlier (displaced centroid, abnormal volume) is flagged while
its neighbours are not; window boundary cases (first/last vertebra) handled
without crash; deterministic; window width configurable.

---

## Current state (updated 2026-06-26)

Items 014, 016, 017, 018 are merged to `main`. Item 019
(orientation/curvature) is in progress on `aide/019-vertebra-orientation-curvature`.

**Remaining in this queue:** 019 (in progress), 020, 021, 022, 023, 024.

## Next Step

With 019 in progress, the next items to claim from this queue are:
- **Item 023** (EDT centroid + centroid depth) — Stage 2 enhancement; best
  done before the spline features consume the centroid values further downstream.
- **Item 020** (neighbour-consistency) — can run in parallel with 023 once 019 merges.
- **Items 021, 022, 024** follow naturally from 020 and the spline layer.

Open a **new chat session** and run `/speckit-aide-create-item` with the chosen
item's description to produce a detailed spec under `docs/aide/items/NNN-*.md`.
Per the team workflow in `CLAUDE.md`: `git fetch --all --prune` and check
`aide/*` branches first, then branch per item and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit.
