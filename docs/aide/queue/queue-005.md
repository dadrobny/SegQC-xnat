# Seg-QC-xnat — Work Queue 005

> **Status:** ✅ Completed — superseded by queue-006 (2026-07-11).
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-004.md`](queue-004.md) (items 036–042).

---

## Scope of this queue

Delivers roadmap **Stage 6 — VerSe Reference Distributions & Delta-to-Reference
Rules (G3)** in full.

**Milestone delivered:** the QC gate stops depending on hand-guessed constants and
starts grounding its judgements in **reference feature distributions built from
ground truth**. A statistical core aggregates per-case, per-vertebra features into
per-level **reference distributions** (mean / std / percentiles), optionally
stratified by a subject-size proxy; a VerSe-style ingestion driver turns a
directory of ground-truth label maps into the feature records that core consumes;
a builder script bakes the distributions into a **versioned, byte-reproducible
reference-data artifact** (a committed default plus a documented rebuild-from-VerSe
path). On top of that artifact, a new **delta-to-reference** feature layer scores
each vertebra against its level's distribution (robust z-score, percentile rank,
out-of-range, distribution distance), a new **rule family** flags out-of-
distribution vertebrae with explainable reasons, and the existing level-aware
bounds rule gains a **config switch** to source its min/max from the reference
percentiles instead of the shipped hand-set defaults. On completion, GT sits
inside the reference ranges (passes) while perturbed cases fall outside (flagged)
— the reference-grounded half of distinguishing *failure* from *legitimate
variation* (**G3**), and the substrate Stage 7 (evaluation & calibration) tunes
against.

**Prioritisation rationale.** The roadmap graph reaches Stage 6 off the completed
Stage 2–4 feature/heuristic core (`… → 4 → 6`), parallel to the now-complete
Stage 5 corpus. Every dependency is merged: the geometric/topological feature
engine (Stages 2–3), the config-driven rule engine with its level-aware bounds
rule whose own docstring notes it is "superseded by reference-derived bounds in
Stage 6" (Stage 4), and the seeded synthetic-corpus + regression harness (Stage 5)
that supplies both a clean-GT positive control and out-of-distribution perturbed
cases for the acceptance test. Stage 6 is the single next coherent milestone and
the only remaining prerequisite (with Stage 5) for the Stage 7 evaluation loop.

**Local-testability note (key design decision).** Full VerSe is a large external
dataset and is **not** committed to this repo. So ingestion (044) is written to
operate on **any** conforming directory of GT label maps, and every item is tested
locally against a **small synthetic VerSe-format cohort** produced by the Stage 5
clean-GT builder (`segqc/synth/clean_gt.py`) with per-subject variation; the
**committed default reference artifact** (045) is built from that synthetic cohort,
while building from a mounted **real VerSe** directory is a documented, reproducible
path. This keeps the whole stage locally runnable and deterministic under `pytest`
without shipping VerSe, consistent with the roadmap's "committed **or mounted**"
artifact wording.

### Numbering note — read before picking an item

Items 001–042 are complete (Stages 0–5, all ✅ in `progress.md`). This queue
continues at the next free integer and is strictly monotonic: **043–049**.

**Estimated size:** ~1 week (7 items). Each item is independently testable locally
with `pytest`: the statistics/ingestion/artifact items assert distributions and
artifacts against hand-computed values and byte-reproducibility on a synthetic
cohort; the delta/rule/config items assert firing-and-non-firing against in-range
GT and out-of-range perturbed inputs.

**Sequencing note.** Critical path: **043** (reference-distribution schema +
aggregation core) gates everything — it defines the per-case feature-record
contract and the versioned distribution data model every later item consumes.
**044** (VerSe ingestion driver) produces records for that core and can be built
alongside 043 once the record shape is fixed. **045** (artifact + builder + loader)
chains 044 → 043 into a committed, versioned artifact and gates the consumers.
**046** (delta-to-reference feature computation) depends on 045's loader; **047**
(delta rule family) depends on 046. **048** (config switch for bounds source) is
parallelisable once 045's loader exists. **049** (integration + acceptance) depends
on 046/047/048 and closes the stage. Recommended order: 043 → 044 → 045 →
(046 → 047, and 048 in parallel) → 049.

### Stage-6 deliverable → item coverage

| Stage-6 deliverable | Delivered by item(s) |
|---------------------|----------------------|
| VerSe GT ingestion → per-level reference distributions (mean/percentiles), stratified by level (+ subject-size proxy) | 043 (aggregation core + schema + size proxy), 044 (VerSe ingestion driver) |
| Versioned reference-data artifact (committed or mounted) + builder script | 045 |
| Delta-to-reference rules: per-vertebra distribution distance / out-of-range vs reference | 046 (feature computation), 047 (rule family) |
| Heuristic config switches from hand-set bounds to reference-derived bounds | 048 |
| *(acceptance closure)* GT in-range / perturbations out-of-range (**G3**); reference loading + delta rules tested | 049 (integration + acceptance suite) |

Every deliverable is realised by ≥1 item; item 049 wires the pieces into
`segqc run` and asserts the stage's **G3** acceptance criterion end-to-end.

---

## Work items

### Item 043: Reference-distribution schema & per-level aggregation core
Establish the statistical foundation and versioned data model the rest of Stage 6
builds on. Create a reference module (e.g. `segqc/reference/`) providing: (a) a
**versioned reference-distribution schema** — a dataclass / JSON shape carrying,
per anatomical level (and optionally per subject-size stratum), summary statistics
for each heuristic-relevant feature (physical volume, extents x/y/z, centroid
spacing, spline offset, …): `count`, `mean`, `std`, percentiles
(e.g. p1/p5/p25/p50/p75/p95/p99) and min/max — plus a `schema_version` and
provenance fields (source, config hash, build date); and (b) a **pure aggregation
function** that consumes a collection of per-case, per-level feature records and
produces those distributions, including an optional **subject-size proxy**
(e.g. total spine extent or mean vertebra volume) used to stratify/normalise.
No file I/O and no VerSe coupling — records in, distributions out.
*Testable:* unit tests feed hand-built per-case records and assert the aggregate
`mean` / percentiles / `count` match hand-computed values; a level present in only
some cases aggregates over exactly those cases; the subject-size proxy buckets
deterministically; empty input yields an empty-but-well-formed distribution; the
same records produce byte-identical serialised output (determinism).

### Item 044: VerSe GT ingestion — cohort loader & feature-extraction driver
Add the ingestion path that turns a directory of ground-truth label maps into the
per-case, per-level feature records the aggregation core (043) consumes. Provide a
**cohort driver** (e.g. `segqc/reference/ingest.py`) that walks a VerSe-style
dataset directory of NIfTI instance label maps (plus scan where needed), normalises
integer labels via the Stage 0 convention (`segqc/labels.py`), runs the existing
Stage 2–3 feature engine per subject, and emits one 043-schema record per
subject/level with provenance (which subject/level each value came from). Must
tolerate real VerSe quirks — transitional anatomy (T13 / L6), partial FOV, subjects
missing levels — without crashing. Because full VerSe is not committed, ingestion
operates on **any** conforming directory and is tested locally against a **small
synthetic VerSe-format cohort** built with `segqc/synth/clean_gt.py` (per-subject
variation).
*Testable:* running the driver over a small synthetic cohort produces one record
per subject/level with the expected features; a subject with a deliberately missing
interior level ingests without error and simply contributes no record for that
level; labels are normalised to canonical level names; ingestion is deterministic
over a fixed cohort.

### Item 045: Versioned reference-data artifact + builder script
Chain ingestion (044) → aggregation (043) into a reproducible, versioned
**reference-data artifact** and the script that builds it. Provide a **builder**
(e.g. a `segqc build-reference` CLI subcommand or `scripts/build_reference.py`) that
reads a cohort directory, produces the per-level (and size-stratified) distributions,
and writes them to a versioned JSON artifact carrying `schema_version`,
source/provenance, and a content/config hash; plus an **artifact loader** that reads
it back into the 043 data model with schema-version validation. Ship a small
**committed default artifact** built from the synthetic cohort (bundled like
`default_config.yaml` via `importlib.resources`), and document a one-command path to
rebuild from a mounted real-VerSe directory. The artifact must be **byte-reproducible**
from a fixed cohort — pin it in `.gitattributes` with `text eol=lf` and write bytes
with `\n` per the CLAUDE.md determinism gotcha (items 040/042 set the precedent).
*Testable:* the builder writes a byte-identical artifact across two runs from the same
cohort; the loader round-trips it into the data model and rejects a mismatched
`schema_version`; the bundled default artifact loads via the package resource path;
regenerating from the committed cohort reproduces the committed bytes.

### Item 046: Delta-to-reference feature computation
Add the per-vertebra **delta-to-reference** feature layer that compares a case's
features against a loaded reference artifact (045). For each present label — given
its level (and size stratum where applicable) — compute distribution-relative
metrics: a **robust z-score** (reference median/IQR) and/or standard z-score, a
**percentile rank**, an **out-of-range flag** against configurable reference bounds
(e.g. below p1 / above p99), and an aggregate **distribution-distance** score across
the tracked features. Serialise these into the JSON report as a `reference_delta`
block per label alongside the existing features (extend and validate the report
schema). Gracefully handle a level absent from the reference (no reference ⇒ delta
reported as *unavailable*, not an error).
*Testable:* a value equal to the reference median yields ≈zero z, a mid percentile,
and in-range; a value far in the reference tail yields a large z, an extreme
percentile, and out-of-range; a level with no reference entry yields an explicit
"no-reference" result rather than a crash; the block validates against the extended
schema; deterministic.

### Item 047: Delta-to-reference rule family (heuristic layer)
Add a new **config-driven rule family** to the Stage 4 engine (e.g.
`segqc/heuristics/reference_delta.py`, registered via `@register_rule`) that consumes
the delta-to-reference features (046) and fires when a vertebra is
**out-of-distribution vs the reference** — its robust-z / percentile /
distribution-distance exceeds configured thresholds, or it falls outside the
reference range. Each finding carries a human-readable reason (measured value vs
reference range / percentile), the offending label, and a config-driven severity, and
flows through the existing verdict aggregation (`segqc/aggregate.py`). This is the
heuristic realisation of the vision's "delta to reference" rule family (§5.4) and
directly supports **G3**.
*Testable:* with a reference loaded, an in-distribution GT vertebra produces no
finding while an out-of-distribution vertebra (perturbed or synthetic-extreme) fires
with the correct offending label and a reason; thresholds are read from config; the
rule is silent (not erroring) when no reference is available for a level; both firing
and non-firing are asserted; deterministic.

### Item 048: Heuristic config switch — reference-derived vs hand-set bounds
Let the level-aware bounds rule (item 027, `segqc/heuristics/bounds.py`) source its
min/max from the reference artifact (045) instead of the hand-set `DEFAULT_BOUNDS`,
selectable via the versioned heuristic config (`segqc/config.py`,
`default_config.yaml`). Add a documented config switch (e.g.
`bounds.params.source: hand-set | reference` with a reference percentile pair such as
p1/p99) so a rule derives its per-level bounds from the loaded distributions, with
**graceful fallback** to the hand-set defaults for any level the reference does not
cover. Keep `hand-set` the default so existing behaviour and the Stage 5 golden
snapshots are unchanged until reference mode is explicitly enabled.
*Testable:* with `source: hand-set` the bounds rule fires identically to today
(defaults unchanged); with `source: reference` the effective bounds for a level come
from the artifact's percentiles (a value inside the reference range passes, one
outside fires), and a level absent from the reference falls back to hand-set bounds;
the switch round-trips through config load and is documented/versioned; deterministic.

### Item 049: Stage 6 integration & reference-vs-perturbation acceptance tests *(completes Stage 6)*
Close Stage 6 by wiring the reference artifact and delta rules into `segqc run`
end-to-end (load the bundled default artifact by default, overridable by flag/config;
render the `reference_delta` block and any reference findings into the JSON and human
reports) and adding the stage's **acceptance suite**: build a reference from the
synthetic GT cohort, then assert that **clean-GT fixtures fall within the reference
ranges** (pass, low false-positive) while the **Stage 5 perturbed corpus cases fall
outside** and are flagged by the delta rules (**G3**). Document the reproducible
reference-build + evaluation path.
*Testable:* the acceptance suite is green — GT cases sit inside the reference ranges
with no reference-delta findings, and out-of-distribution perturbed cases produce
reference-delta findings / out-of-range verdicts with the expected offending labels;
reference loading and the delta rules are covered; `segqc run` emits the reference
block; the extended JSON validates against the schema; deterministic / golden-stable.

---

## Current state (2026-07-11)

✅ **Stage 6 complete.** All items **043–049 are done** (✅ in `progress.md`): the
reference-distribution schema + per-level aggregation core (043), the VerSe GT
ingestion cohort driver (044), the versioned reference-data artifact + builder +
loader (045), the delta-to-reference feature computation (046), the delta-to-
reference rule family (047), the reference-vs-hand-set bounds config switch (048),
and the Stage-6 integration + reference-vs-perturbation acceptance suite (049) are
all merged. GT fixtures fall within the reference ranges (pass) while perturbed
cases fall outside (flagged) — the reference-grounded half of **G3**. Superseded by
[`queue-006.md`](queue-006.md), which delivers Stage 7 (evaluation, calibration &
metrics) on top of this reference substrate and closes Phase 1.

## Next Step

Per `CLAUDE.md`: `git fetch --all --prune` and check `aide/*` branches first, then
branch per item (`aide/NNN-short-name`) and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit. Stage 6 is complete — proceed
to [`queue-006.md`](queue-006.md).
