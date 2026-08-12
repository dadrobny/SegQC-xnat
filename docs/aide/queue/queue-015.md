# FACET — Work Queue 015
> **Status:** ✅ Completed — superseded by queue-016 (2026-08-12).

> **Created:** 2026-07-27
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 19**; supersedes the completed [`queue-014.md`](queue-014.md)
> (Stage 18, closed 2026-07-27).

---

## Scope of this queue

Delivers roadmap **Stage 19 — Generated Feature & Rule Catalogue + Steering
Review** (G7, G8) in full. Stage 19 has **no dependencies** — the roadmap
(`roadmap.md:757-759`) notes it is independent of Stage 18 and could in
principle have run alongside it, but queue-014 deliberately left it for its
own queue because it **carries the human steering checkpoint**: `aide.toml`
sets `clarify = "assume"` project-wide, but this stage's whole point is a
human-reviewed catalogue and a signed-off golden-file decision, so it must be
front-loaded through `/aide-spec-queue`'s forced `interactive` clarify mode
rather than executed unattended.

The premise is measurable in the code today: `FEATURE_CATALOG` in
`scripts/aide_status_report.py:845` is hand-maintained (9 groups / 41 entries,
commented *"Not derived from a filesystem scan: keep in sync by hand"*), while
a realised `extract_feature_record` output has **185 distinct leaf paths** —
those count different things (an entry like `touches_*` covers six fields), so
the gap is not a straight drift figure, but nothing verifies the two agree,
and no document records which of the 8 §6 failure modes each feature targets
or which of the 10 registered rules (`heuristics/rule.py` registry) consume
it.

**Why this queue is scoped to exactly one stage.** Stage 19 comes to four
items — three deliverables plus the stage validation — well under half of
`loop.queue_cap = 10`. Stage 20 depends on this stage's catalogue
(`roadmap.md:795`) and is its own audit with a different shape of work
(traceability/specificity harness vs. cataloguing/review), so it stays out of
this batch per the stage-boundary convention.

**Prioritisation.** Item 103 (the generated catalogue) is the foundation —
104 and 105 both consume it. Item 104 (the drift test) and item 105 (the
golden-file decision table) are independent of each other and may run in
parallel once 103 lands, but 104 first is the safer order: a failing drift
test on day one is a cheap, mechanical thing to fix, whereas 105 is a
judgment call (the human-reviewed keep/retire table) best made once the
catalogue's coverage is already known to be complete. Item 106 closes the
stage and must run last, and is also where the human sign-off on 105's
decision table is recorded. Recommended order: **103 → 104 → 105 → 106**.

**Numbering.** Continues at the next free integer: **103–106**.

### Stage-19 deliverable → item coverage

| Stage-19 deliverable | Delivered by item |
|---|---|
| Generated feature/rule catalogue (computation, units, scale sensitivity, targeted §6 mode, consuming rules, keep/retune/retire/unwired status) | 103 |
| Drift test: every leaf path in a reference record is covered; CI fails on an undocumented feature | 104 |
| Golden-file decision table (one row per committed golden: what it asserts, keep or retire, what replaces it) + human sign-off | 105 |
| Stage validation + verification-row closure | 106 |

---

## Work items

### Item 103: Generated feature & rule catalogue

Replace the hand-maintained `FEATURE_CATALOG` in
`scripts/aide_status_report.py:845` with a catalogue **generated** from the
realised feature-record shape (`pipeline.extract_feature_record`'s output,
185 leaf paths today) plus the extractor modules' own docstrings, rather than
hand-typed group/item literals. For every leaf path, record: the feature name
and path, its owning module/item (from the module docstring's stage/item
annotation — see `CLAUDE.md`'s Architecture section for the convention),
what it measures, **how it is computed**, units, spacing/scale sensitivity
(does it scale with voxel spacing, is it dimensionless, etc.), the §6
failure mode(s) it targets (`synth/perturbation.py::FAILURE_MODE_NAMES`,
lines 62-72), which of the 10 registered rules
(`heuristics/rule.py`'s module-level registry, `iter_rules()`) consume it,
and a status of `keep` / `retune` / `retire` / `unwired`. Decide and record
where the generator sources the failure-mode/rule mapping from — item 099's
per-mode metric API already names one metric per mode and is a natural
anchor, but most of the 185 leaf paths are not covered by it, so the
spec-author must define how the remaining mapping is derived or explicitly
marked `unwired`. The catalogue output format (module producing a data
structure the existing HTML status report renders, vs. a standalone
generated document) is also the spec-author's call to pin down and record.
*Testable:* every leaf path present in a reference record produced by
`extract_feature_record` on a real corpus case appears in the generated
catalogue exactly once; every catalogue entry carries a non-empty status
value; regenerating the catalogue twice from the same inputs is
byte-identical; a feature added to an extractor module without a
corresponding docstring/annotation is either surfaced as `unwired` or fails
generation loudly rather than being silently dropped.

### Item 104: Feature-catalogue drift test

Add a test that fails CI whenever the generated catalogue (item 103) and the
realised feature-record shape disagree: build a reference record (reusing an
existing corpus fixture or `tests/synthetic.py` happy-path fixture), walk it
to the same leaf-path granularity the catalogue uses, and assert set equality
against the catalogue's covered paths in both directions — an
undocumented realised feature, and a catalogued feature no longer produced,
must both fail the test with a message naming the offending path(s) rather
than a bare assertion failure. *Testable:* the test passes against the
current catalogue+record; deliberately adding a new field to a features/
dataclass without updating the catalogue makes the test fail, naming that
field; deliberately removing a catalogued entry's corresponding real field
also fails, naming that entry; the test runs in the default `pytest`
invocation with no environment gating (this is a structural check, not one
needing PyRadiomics/Docker/GPU).

### Item 105: Golden-file decision table + human sign-off

Produce a decision table with one row per committed golden — the nine
`tests/corpus/golden/*.json` whole-record snapshots
(`clean_control.json`, `mode1_displace.json` … `mode8_force_overlap.json`)
plus any other committed golden fixture the repo relies on for exact-match
comparison (survey `tests/` for `reports_close`/byte-identity assertions
beyond the corpus goldens, e.g. report-formatting or schema goldens) —
recording: what each golden asserts today, a **keep** or **retire**
disposition, and (for `retire`) what replaces its guarantee. The roadmap's
working assumption (`roadmap.md:748-755`) is **retire most**: the nine
corpus goldens are whole-record snapshots of a corpus Stage 21 replaces, and
every feature retune Stage 19/20 authorises forces a wholesale
regeneration, after which the golden diff can no longer distinguish an
intended change from a regression — note explicitly that this is **not**
about byte-level reproducibility, which is guarded by the separate,
independent intra-run `dest1 == dest2` determinism assertion
(`synth/golden.py`) and is unaffected either way. Report-formatting and
schema goldens are called out in the roadmap as the likely survivors — the
spec-author confirms this per-golden rather than assuming it. This item's
distinguishing deliverable is the **human sign-off**: the table is drafted,
then reviewed and explicitly approved by the user before item 106 can
record the stage's acceptance as met — this is the load-bearing reason
Stage 19 runs through `/aide-spec-queue`'s interactive clarify mode rather
than unattended. *Testable:* the table enumerates every committed golden
fixture found in `tests/` with no omissions; every row has a disposition and
(for `retire`) a named replacement guarantee; the table file records the
sign-off (who/when) once granted.

### Item 106: Validate stage 19: Generated Feature & Rule Catalogue + Steering Review

Replay Stage 19's use cases end-to-end. Regenerate the catalogue (item 103)
from a live `extract_feature_record` run and confirm it renders into the
existing status report / documentation surface without manual
post-editing; run the drift test (item 104) against the current record
shape and confirm it is green, then deliberately introduce and revert an
undocumented field to confirm the test actually fails (proving it can
fail, not just pass); confirm the golden-file decision table (item 105)
carries the human sign-off recorded before this item proceeds — if sign-off
is still pending, this item must stop and report that rather than
fabricating approval. Then update `progress.md`: tick Stage 19's three
acceptance criteria (G7: catalogue generated + drift test fails on a
deliberately undocumented feature; G8: every feature carries a status and a
named failure mode or `unwired`; golden decision table complete and signed
off) against what was actually exercised, and flip any Environment-Gated
Capability Verification row this stage introduces to ✅ Verified where the
environment allows (`python .aide/scripts/aide.py env --profile <name>`),
otherwise record why it stays ❓ Unverified. Note explicitly that acting on
item 105's retire decisions (actually deleting/replacing golden files) is
**Stage 21's job** (`roadmap.md:829` — "Act on Stage 19's golden decision"),
not this item's — Stage 19 decides, Stage 21 executes.
*Testable:* the regenerated catalogue matches item 103's output exactly;
the drift test passes on the current tree and is shown to fail on a
deliberately introduced undocumented feature; the decision table's sign-off
is present (or the item honestly reports it is not, and does not mark the
stage done); `progress.md`'s Stage 19 section and the Environment-Gated
Capability Verification table reflect what was actually exercised.

---

## Current state (2026-07-27)

Generated on completion of [`queue-014.md`](queue-014.md), which delivered
**Stage 18 — Failure-Mode-Specific Metric Surface** (items 098–102, all ✅).
Opens **Stage 19 — Generated Feature & Rule Catalogue + Steering Review**,
which has no dependencies and was deliberately deferred to its own queue for
the human steering checkpoint. Stage 20 depends on this stage's catalogue
and remains blocked until it lands. Stage 16 (real failure corpus) and Stage
21 (real-GT perturbation corpus) remain blocked behind that chain. Stage 11
stays ⏸️ Deferred and Stage 15 ❌ Excluded.
