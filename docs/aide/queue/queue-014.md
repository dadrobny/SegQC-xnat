# FACET — Work Queue 014
> **Status:** ✅ Completed — superseded by queue-015 (2026-07-27).

> **Created:** 2026-07-26
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 18**; supersedes the completed [`queue-013.md`](queue-013.md)
> (Stage 17, closed 2026-07-26).

---

## Scope of this queue

Delivers roadmap **Stage 18 — Failure-Mode-Specific Metric Surface** (G2, G7)
in full. Stage 17 landed the prerequisite ("level names must be right before
per-level metrics mean anything") and is ✅ across all five of its deliverables,
so Stage 18 is unblocked.

The stage's premise is measurable in the code today: the quantity that isolates
§6 mode 3 — foreground beyond the dominant connected component — has **no name**
anywhere in the feature record. `ComponentsInfo`
(`features/components.py:61-98`) exposes `component_count`,
`component_sizes`, `component_volumes_mm3`, `largest_component_fraction` and
`small_fragments`, and the fragmentation rule reconstructs the stray population
privately from `component_sizes[1:]` at `heuristics/fragmentation.py:442-443`
against its own `island_min_voxels` param — a fact its own module docstring
records as a design decision (`fragmentation.py:45-47`: *"Does not rely on
`components.small_fragments` — that list is recomputed from `component_sizes`
using the rule's own `island_min_voxels` param"*). Nothing outside that rule can
read "how much stray volume is there", so no per-mode metric can be built on it.

**Why this queue is scoped to exactly one stage.** Stage 18 comes to five items
— three deliverables, the G2 monotonicity/specificity acceptance (substantial
enough to stand alone), and the stage validation — half of `loop.queue_cap = 10`.
The roadmap's post-supersession preamble (`roadmap.md:655-659`) notes that
Stages 19 and 20 are pure audit and "should run alongside 17/18", which is a
statement about *independence*, not an instruction to batch them: Stage 19
explicitly **carries the human checkpoint** (`roadmap.md:757-759` — "run it
through `/aide-spec-queue`") and Stage 20 depends on Stage 19's catalogue. Both
are separate review units with a different shape of work (auditing what exists
vs. adding a measurement surface), and the create-queue convention is to stop at
the stage boundary rather than pad. Stage 19 gets its own queue.

**Prioritisation & sequencing.** Item 098 is the foundation — it names the stray
quantity, and both 099 and 100 read it — so it goes first, and it is also the
only item in the batch that changes the persisted feature-record shape (schema +
nine goldens), which is cheapest to land before anything else depends on the new
fields. Item 099 defines the per-mode metric API that 100 exercises and 101
reports. Items 100 and 101 are independent of each other and may run in parallel,
but 100 first is the safer order: if a metric fails the monotonicity bar, it is
better to learn that before it is wired into a shipped report. Item 102 closes
the stage and must run last. Recommended order: **098 → 099 → 100 → 101 → 102**.

**Key constraint — item 098 is a persisted-schema change, not just a dataclass
change.** `components_to_dict` (`feature_report.py:145-163`) is the single
serialisation site, and the JSON report schema pins that block with
`"additionalProperties": false` plus an exhaustive `required` list
(`report_schema_v0.json:237-271`). Adding a field therefore (a) fails schema
validation until the schema is updated, and (b) changes all **nine** committed
whole-record goldens under `tests/corpus/golden/` — `reports_close`
(`synth/golden.py:176`) is numerically tolerant but compares structure and keys
**exactly**, so they must be regenerated via `write_goldens`
(`synth/golden.py:268`). That is expected, planned work for item 098, not a
surprise for a later item to absorb.

**Key constraint — the new fields must NOT enter the reference vocabulary.**
`INGESTED_MORPHOLOGY_FEATURES` (`reference/ingest.py:146-150`) currently tracks
`largest_component_fraction`, `component_count`, `eigenvalue_ratio`. Adding a
stray metric there would invalidate the committed `reference_verse_v1.json` and
force a re-fit of the 80-subject VerSe19 distribution — out of scope for this
stage and explicitly fenced off. Stage 23 owns the normative-model rework.

**Key constraint — `PerModeSensitivity` already exists and is a different
thing.** `eval/metrics.py:112-144` reports, per §6 mode, *the fraction of cases
whose designated rule fired* — a detection rate. Stage 18's per-mode metric API
reports *the magnitude of the mode present in a case* — a continuous quantity.
Item 099 must complement that surface, not duplicate or replace it; both end up
in the same cohort report (item 101), answering "did we catch it" and "how much
of it was there" side by side.

**Numbering.** Continues at the next free integer: **098–102**.

### Stage-18 deliverable → item coverage

| Stage-18 deliverable | Delivered by item |
|---|---|
| Promote stray-component metrics to first-class `components` fields; fragmentation rule reads rather than recomputes | 098 |
| Per-mode metric API mapping each §6 mode to the metric that isolates it, reusing `eval/overlap.py::compute_overlap` | 099 |
| G2 acceptance: severity-ladder monotonicity + cross-mode insensitivity harness | 100 |
| Cohort-level per-mode report supporting run-vs-run comparison | 101 |
| Stage validation + verification-row closure | 102 |

---

## Work items

### Item 098: Promote stray-component metrics to first-class `components` fields

Add named stray-component fields — stray volume in mm³, stray component count,
and stray volume fraction — to `ComponentsInfo`
(`features/components.py:61-98`), populate them in `compute_components`
alongside the existing `component_volumes_mm3` / `largest_component_fraction`
computation (`components.py:181-196`), serialise them in `components_to_dict`
(`feature_report.py:145-163`), and admit them in the report schema's
`components` definition (`report_schema_v0.json:237-271` — `additionalProperties`
is `false` and `required` is exhaustive, so both lists must be extended).
"Stray" means every component other than the dominant one (`component_sizes[1:]`
— the same population the fragmentation rule reconstructs privately today), so
the fraction is the exact complement of `largest_component_fraction` and must be
derived consistently with it rather than recomputed by a second route. Then
refactor `heuristics/fragmentation.py`'s hand-set island branch
(`fragmentation.py:438-464`) to read the new fields instead of rebuilding
`non_dominant`/`tiny_islands` from `sizes[1:]` at lines 442-443, updating the
module docstring's now-stale design note (`fragmentation.py:45-47`). The rule's
**behaviour must not change** (roadmap G7 acceptance): the `island_min_voxels`
voxel-floor semantics, the reference-derived `max_component_count` branch
(`fragmentation.py:413-437`), the finding order and the reason strings all stay
exactly as they are. Regenerate the nine `tests/corpus/golden/*.json` via
`synth/golden.py::write_goldens` (`golden.py:268`) — they are whole-record
snapshots and `reports_close` compares keys exactly. **Scope fence:** do not add
the new names to `INGESTED_MORPHOLOGY_FEATURES` (`reference/ingest.py:146-150`);
that would force a re-fit of the committed `reference_verse_v1.json`.
*Testable:* the three new fields equal hand-computed values on a multi-component
fixture, and are `0`/`0.0`/`0.0` on a single-component label; `stray_volume_fraction
+ largest_component_fraction == 1.0` within float tolerance for every corpus
case; the fragmentation rule emits byte-identical findings (count, order,
`rule_id`, `severity`, `labels`, `reason` strings) before and after the refactor
across all nine corpus cases and in both `hand-set` and `reference` source modes;
`segfacet run` output validates against the updated `report_schema_v0.json`; the
nine regenerated goldens still satisfy the intra-run `dest1 == dest2`
determinism assertion.

### Item 099: Per-mode metric API — one named metric per §6 failure mode

Add a per-mode metric API (a new `eval/` module) mapping each of the eight §6
failure modes named in `synth/perturbation.py::FAILURE_MODE_NAMES` (lines 62-72)
to at least one **named scalar metric** that isolates it, computed either from a
per-case feature record (`pipeline.extract_feature_record`) or from a
candidate-vs-GT comparison. **Reuse `eval/overlap.py::compute_overlap`
(`overlap.py:167-273`) and its `OverlapResult` aggregates — `dice`, `jaccard`,
`mean_dice`, `volume_weighted_dice`, `n_matched`, `n_unmatched`
(`overlap.py:112-145`) — for anything overlap-shaped; write no new overlap
code.** The obvious candidate sources per mode (the spec-author fixes the final
mapping and records the reasoning): mode 1 alignment → per-label spline offset
(`features/spline_offset.py:154`); mode 2 fused/fragmented →
`fragmentation_index` plus per-label Dice drop; mode 3 islands → item 098's
stray-volume fields; mode 4 mislabelling → per-label Dice at matched label
values; mode 5 missing levels → `OverlapResult.n_unmatched` / GT-present,
candidate-absent count; mode 6 border → the `touches_*` border-contact fields
from `features/geometry.py`; mode 7 sequence → the gap/monotonicity signals from
`features/consistency.py:167,236`; mode 8 overlap → shared-voxel volume from
`features/overlap.py::detect_overlaps` (`overlap.py:77`). Follow the module's
neighbours in shape: a frozen dataclass carrying `failure_mode`,
`failure_mode_name`, the metric name and value, plus a JSON-ready `to_dict()`
(the `PerModeSensitivity`/`CohortMetrics` pattern at `eval/metrics.py:112-215`),
pure — no file I/O, no clock, no mutation of the input record. This API is
**complementary to, not a replacement for**, `PerModeSensitivity`
(`eval/metrics.py:112-144`), which measures detection rate rather than magnitude.
*Testable:* every one of the eight modes returns a named, non-`None` metric when
given the corresponding `tests/corpus` case; the clean control
(`CLEAN_CONTROL_MODE`, `perturbation.py:58`) yields the documented mode-free
baseline value for every metric; the result round-trips through
`to_dict()`/`json.dumps`/`json.loads` unchanged; calling the API twice on the
same record returns equal values and never mutates it; a record missing an
optional block (e.g. no `stage3`) degrades to an explicit `None` sentinel rather
than raising.

### Item 100: Severity-ladder monotonicity & cross-mode specificity harness

Build the harness that proves Stage 18's G2 acceptance: for each §6 mode, a
graded severity ladder of at least three rungs whose own metric (item 099) moves
**monotonically** with injected severity, while every *other* mode's metric stays
comparatively flat. The ladders come from the existing perturbation operators'
constructor parameters — the abstraction already supports this
(`perturbation.py:188-192`: *"operators are parameterised via their
constructor"*). **Five of the eight modes have a continuous knob:**
`displace(displacement_mm=…)` (`synth/identity_ordering_alignment.py:161-173`),
`fragment(n_pieces=…)` (`synth/component_shape.py:128`),
`inject_islands(n_islands=…, island_voxels=…)` (`component_shape.py:285-303`),
`crop_at_border(crop_depth=…)` (`synth/coverage_border_overlap.py:245-262`) and
`force_overlap(overlap_depth=…)` (`coverage_border_overlap.py:347-361`). **Three
do not:** `relabel_swap` (`identity_ordering_alignment.py:262-269`),
`sequence_break` (`identity_ordering_alignment.py:355-362`) and `remove_level`
(`coverage_border_overlap.py:176`) take only target-label selectors, so their
ladder must be built from the **number of affected labels** (repeated
application), or the mode explicitly recorded as carrying a two-rung
(absent/present) ladder with the reason written down — never silently reported
as monotone over a degenerate ladder. Express the "comparatively insensitive"
bar as a stated numeric margin (e.g. the mode's own metric changes by a factor
strictly greater than every foreign metric's change across the same ladder) and
record the observed margins, so the bar is a ratchet a future rule retune cannot
quietly loosen. Seeded and deterministic throughout (`perturbation.py:254`'s
`seeded_rng`); reuse `synth/clean_gt.py` as the rung-zero base.
*Testable:* for each of the eight modes, its designated metric is monotone
(non-decreasing or non-increasing, direction declared per metric) across the
ladder, strictly changing between the first and last rung; for each ladder, the
designated metric's relative change exceeds every other mode's metric's relative
change by the recorded margin; the clean control is the zero rung for every
ladder; re-running the whole harness with the same seed reproduces identical
values; a deliberately mis-assigned metric (asserted against the wrong mode's
ladder) fails the harness, proving it can actually fail.

### Item 101: Cohort-level per-mode report with run-vs-run comparison

Add the cohort-level per-mode report and the run-vs-run comparison it exists for:
given two cohort evaluations over the **same** cohort — the canonical case being
one segmentation tool run twice with a post-processing step on vs. off — emit
per-mode metric aggregates for each side plus their deltas, so a behavioural
change is attributable to a specific §6 failure mode instead of being hidden
inside an aggregate Dice number. Build on the existing Stage-7 reporting surface
rather than a parallel one: `build_evaluation_report`
(`eval/report.py:178`), `serialize_evaluation_report_json` (`report.py:240`),
`write_evaluation_report` (`report.py:248`), `render_evaluation_report`
(`report.py:276`), the versioned `eval/eval_report_schema_v0.json`, and
`EvaluationProvenance` (`report.py:104`); carry item 096's run manifest on each
side so the two runs are identified by segmenter version / SHA / toggle rather
than by filename. Include both per-mode surfaces side by side — item 099's
magnitude metrics and the existing `PerModeSensitivity` detection rates
(`eval/metrics.py:112-144`) — plus the aggregate `mean_dice` /
`volume_weighted_dice`, so the report itself demonstrates the stage's thesis
(the per-mode delta is informative where the aggregate is not). Decide and record
whether this is an additive block in the v0 schema or a new schema version.
Surface it on the CLI as either a new subcommand or a flag on `evaluate`
(`cli.py:399-520`), following the deferred-heavy-import convention the other
handlers use. Writes bytes via `Path.write_bytes` per the repo's
byte-reproducibility convention, and any new committed text fixture is pinned
`text eol=lf` in `.gitattributes`.
*Testable:* two runs differing only in an injected post-processing behaviour
produce a comparison whose largest per-mode delta is on the affected mode, while
the aggregate `mean_dice` delta is smaller; comparing a run against itself
produces an all-zero-delta report with no spurious findings; comparing two runs
over *different* cohorts is rejected with a clear error rather than silently
diffing mismatched cases; the report validates against its JSON schema, and two
serialisations in one session are byte-identical (`dest1 == dest2`); the rendered
human form names the implicated mode in words.

### Item 102: Validate stage 18: Failure-Mode-Specific Metric Surface

Replay Stage 18's use cases end-to-end, not just the unit suite. Run a full
`segfacet run` on a corpus case and confirm the new stray-component fields
(item 098) appear in the JSON report and validate against
`report_schema_v0.json`; run a full cohort evaluation and the run-vs-run
comparison (item 101) through the **CLI** on two runs of the same cohort,
confirming the per-mode attribution reads correctly end-to-end rather than only
at the API level; confirm the fragmentation rule's end-to-end verdicts across all
nine corpus cases are unchanged from the pre-098 goldens (the G7 acceptance,
verified at report level rather than at the rule's unit level); and confirm the
item-100 harness reports a monotone, comparatively-specific metric for each of
the eight §6 modes, recording the observed margins and naming explicitly any mode
whose ladder is degenerate (two-rung) because its operator has no continuous
severity knob. Then update `progress.md`: tick Stage 18's two acceptance
criteria against what was actually exercised, and flip any Environment-Gated
Capability Verification row this stage introduces to ✅ Verified where the
environment allows (`python .aide/scripts/aide.py env --profile <name>`),
otherwise record why it stays ❓ Unverified — note that Stage 18's metrics are
exercised on the **synthetic** corpus only, so nothing here closes the existing
"Real automatic-segmentation failure corpus" row (that is Stage 16's job) and
this item must not imply otherwise.
*Testable:* the end-to-end `segfacet run` produces a schema-valid JSON + human
report carrying the stray fields; the CLI run-vs-run comparison produces a
per-mode attributed report on two real invocations; the nine corpus cases'
verdicts and findings match their pre-098 values; the monotonicity/specificity
harness passes for all eight modes with margins recorded; `progress.md`'s Stage
18 section and the Environment-Gated Capability Verification table reflect what
was actually exercised, with any unverified row carrying its reason.

---

## Current state (2026-07-26)

Generated on completion of [`queue-013.md`](queue-013.md), which delivered
**Stage 17 — Foreign-Convention Interop & Orientation-Safe Image Layer**
(items 093–097, all ✅). Opens **Stage 18 — Failure-Mode-Specific Metric
Surface**, whose only dependency was Stage 17. Stage 19 (generated feature/rule
catalogue) is independent and unblocked but is deliberately left for its own
queue: it carries the human steering checkpoint and should be front-loaded
through `/aide-spec-queue`. Stage 20 depends on Stage 19's catalogue. Stage 16
(real failure corpus) and Stage 21 (real-GT perturbation corpus) remain blocked
behind that chain. Stage 11 stays ⏸️ Deferred and Stage 15 ❌ Excluded.
