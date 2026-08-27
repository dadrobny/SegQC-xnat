# FACET — Work Queue 017

> **Created:** 2026-08-27
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 20**; supersedes the completed [`queue-016.md`](queue-016.md)
> (Stage 26, closed 2026-08-12).

---

## Scope of this queue

Delivers roadmap **Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability &
Specificity Harness** (G2, G7) in full: seven items, six deliverables plus the
stage validation, under `loop.queue_cap = 10`. The stage closes the gap between
"the suite is green" and "the rules are specific" — measured on the committed
corpus, **10 rules are registered and enabled but only 4 ever fire**
(`fragmentation`, `coverage`, `border`, `sequence`), and **3 of 9 cases fire
nothing at all** through `run_qc`, so 3 of the 8 §6 failure modes are not
detected end-to-end while the corpus reads as covering all eight.

**The stage's own dependency is now clear.** The roadmap gated Stage 20 behind
Stage 26 — items 108 (face mapping), 109 (per-mode attribution) and 110
(`neighbourhood.py` wiring) all change surfaces this audit measures, and
auditing first would have recorded findings that were about to move. Stage 26 is
✅ (queue 016, items 107–116), so that gate is released.

**What the matrix must prove.** Read in three directions, only two of which must
ever be complete (roadmap, clarified 2026-08-11): **mode → rule** complete
always, **rule → mode** complete always, **feature → rule deliberately
incomplete** — a leaf path no rule reads is inventory (`unwired`), not a gap, and
34 of item 103's 111 catalogued paths sit there as an expected steady state. Any
item in this queue that starts treating an unwired feature as a defect has
misread the stage and should hand back.

**Prioritisation.** The order is set by one constraint: **three items change what
the audit would measure, so the audit is generated last.** Item 118 adopts the
specificity ratchet first, while cross-talk is 0/9 and the assertion is free —
once items 120 and 121 make more modes fire end-to-end, introducing it
retroactively means arbitrating real violations instead of pinning a clean
baseline. Item 119 then supplies the rule → mode direction the matrix needs and
that no code path derives today. Items 120 and 121 close the reachability holes
(and 121's FOV headroom is the recorded root cause of mode 6's Stage-18
specificity shortfall, which should clear without touching mode 6). Item 122
measures per-rule and per-operator exercise, and item 123 joins all of it into
the generated matrix. Items 120 and 121 are independent of each other and may be
claimed in either order.

**Numbering.** Continues at the next free integer: **118–124**. Item 117 was
authored outside any queue (loop-infrastructure maintenance, riding the engine
1.14.0 PR) and is ✅.

---

## Work items

### Item 118: Specificity ratchet — assert that no unintended rule fires

`verify_case` (`synth/regression.py:272`) asserts the designated rule fires and
that the offending labels match; it never asserts that *no other* rule fires.
Add that assertion as a ratchet over every corpus case, in both `detection`
branches (`pipeline` and `reconstructed_record`) and for the clean control.
Cross-talk is 0/9 on today's corpus, so the ratchet pins a clean baseline rather
than arbitrating existing violations — which is precisely why it lands before
the two items that widen end-to-end detection. Where a case legitimately fires
more than its designated rule, the allowance must be **declared per case** with a
reason, not accommodated by weakening the assertion; a bare "expected" set that
any new firing can be quietly added to defeats the ratchet. *Testable:* the full
corpus verifies with the ratchet on; a scratch mutation that makes a second rule
fire on one case turns that case red; a case with a declared allowance passes and
one whose actual firings drift from its declaration fails.

### Item 119: Declare each rule's §6 failure modes at the rule

The catalogue derives `rule_id → §6 mode` by AST-scanning `synth/*.py` for
`Expectation(failure_mode=N, expected_rule_ids=frozenset({…}))` (mechanism C,
`catalogue.py`). That makes attribution a side effect of which operators happen
to exist, so the four rules no operator expects — `bounds`, `intensity`,
`reference_delta`, `intensity_reference_delta` — map to no mode at all, which is
Stage 19's G8 shortfall at its root. Give every registered rule a declared mode
attribution owned by the rule itself: the modes it targets, or an explicit
mode-less declaration carrying a reason (the rule targets a cross-cutting
plausibility bound rather than a catalogued mode; the mode it would target is not
yet in §6; the rule is speculative). The declaration must be **single-source** —
a second hand-typed rule-id table alongside mechanism C is exactly the drift
item 103 was built to eliminate, so the derived and declared attributions must
either be one surface or be cross-checked against each other by a test.
*Testable:* every `rule_id` from `iter_rules()` resolves to either ≥1 §6 mode or
a mode-less declaration with a non-empty reason; a new rule registered without an
attribution fails the test; the declared attribution agrees with what mechanism C
derives wherever both speak.

### Item 120: Mode 4 end-to-end reachability — close it or record the mechanism

`mode4_relabel_swap` is `detection="reconstructed_record"`: plain `run_qc` fires
nothing, and `mislabel` is reached only by feeding a hand-built
`monotonic_consistency` record straight to the rule. The mechanism is already
named at the operator (`synth/identity_ordering_alignment.py:255`) — the pipeline
sorts centroids by ascending label before fitting the spline, so the spline
parameter `u` is monotonic by construction and `features/consistency.py`'s
`compute_monotonic_consistency` can never observe the swap. Decide the stage's
call and act on it: make the check compare label order against an
independently-derived spatial order (so the ordering evidence does not come from
the ordering being asserted), or record mode 4's evidence rung as *needs a corpus
the fixtures cannot express* with the mechanism stated. Silent is not an option.
If the check changes, the corpus case moves to `detection="pipeline"` and the
committed goldens are regenerated. *Testable:* the mode-4 case either fires
`mislabel` through plain `run_qc` with the correct offending labels, or its
evidence rung and mechanism are recorded and asserted; the clean control still
fires nothing; item 118's ratchet holds either way.

### Item 121: FOV headroom for the displacement base

Mode 1's severity ladder is capped at ~19.8 mm `displacement_mm` by the fixed
15 mm margin `synth/clean_gt.py` puts on all six faces (`_MARGIN_MM`), so mode
1's metric swing is set by the fixture's walls rather than by the perturbation.
That cap is the recorded root cause of mode 6's Stage-18 cross-mode coupling
(`KNOWN_CROSS_MODE_COUPLINGS`, recorded response 2.79): `crop_at_border`,
`displace` and `force_overlap` all rigidly translate a body, and mode 6's
`n_affected_labels` axis scales linearly across three rungs while mode 1's own
ladder cannot. Give `build_clean_spine` opt-in headroom (a margin or
field-of-view parameter) and move item 100's ladder base onto it, so a 30–40 mm
displacement fits. **The default must not move**: `synth/corpus.py`'s
`_DEFAULT_BASE_PARAMS` feeds every committed corpus fixture and every golden, and
a changed default silently rewrites them. Re-measure the coupling and update its
recorded response and cause to what the widened base actually yields — including
the case where it does not clear, which is a finding, not a failure. Note that
the FOV cap is not the whole of mode 1's end-to-end reachability: the pipeline's
interpolating spline refit also absorbs the displaced centroid, so headroom alone
may not make `mode1_displace` pipeline-detectable, and that second mechanism must
be recorded as mode 1's evidence rung if it survives. *Testable:* a ladder built
on the widened base reaches ≥30 mm displacement; `tests/corpus/` regenerates
byte-identically against its committed copy (the default is untouched); mode 6's
coupling is re-measured and its recorded value matches the new measurement.

### Item 122: Per-rule and per-operator corpus-exercise report

Two blind spots of the same shape went unnoticed until a manual count found them:
6 of 10 registered rules fire on zero corpus cases, and the registered `fuse`
operator (`synth/component_shape.py:207`) generates no corpus case at all —
`CASE_RECIPE` uses 9 of the 10 registered perturbations. Generate an exercise
report over a corpus run: for each registered `rule_id`, the cases it fired on;
for each registered perturbation name, the cases it built. Every rule and every
operator must be exercised by ≥1 case or carry a recorded reason for not being
(mode-less by declaration per item 119; requires an input the corpus cannot
produce; awaiting real data). Like the feature catalogue, the report is
*generated* from the registries and a run, never hand-maintained, so a newly
registered rule or operator appears in it unexercised rather than invisibly.
*Testable:* the report names all 10 rules and all 10 operators; registering a
scratch rule or operator with no case makes it appear as unexercised with no
reason and fails the check; the report is byte-reproducible run-to-run within one
session.

### Item 123: The generated traceability matrix

Join item 103's feature catalogue, the rule registry, item 119's mode attribution
and item 122's exercise report into the stage's headline artifact: 8 failure
modes × rules × the features each rule actually consumes, generated rather than
hand-maintained, committed as JSON + Markdown alongside
`feature_catalogue.generated.*`, and guarded by a drift test in the shape of item
104's. Score the three directions **separately and explicitly**: mode → rule and
rule → mode must both be complete, and a hole in either is a reported defect;
feature → rule is reported as inventory, and unwired paths must be rendered as a
designed state, never as a shortfall. Every mode row carries its evidence rung —
*synthetic-demonstrable*, *needs real data (or a corpus the fixtures cannot
express)*, or *structurally unobservable in the supported input format*. Mode 8
is the third: a single-channel integer label map cannot assign two labels to one
voxel, so `overlaps[]` populates only on a map deliberately corrupted to violate
that invariant, which no real segmenter output can be — the `overlap` rule and
all six fields it reads are correct and fully wired, and the mode becomes
testable only under multichannel or probabilistic input, which no stage plans. A
silent row is the one unacceptable outcome. *Testable:* the matrix regenerates
byte-identically from a clean tree; every §6 mode has ≥1 rule and a non-empty
evidence rung; every rule has ≥1 mode or a mode-less reason; the drift test fails
when a rule is added, removed or re-attributed without regenerating.

### Item 124: Validate stage 20: Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness

Replay Stage 20's use cases end-to-end rather than re-running the unit suite.
Regenerate the traceability matrix from a clean tree and read it as a human
would: confirm every §6 mode row names ≥1 rule and an evidence rung, every rule
row names ≥1 mode or a mode-less reason, and no row is silent (**G2**). Confirm
the feature → rule direction is presented as inventory — spot-check that the
unwired paths (34 of 111 at item 103's count, whatever it now reads) are rendered
as a designed state and that nothing in the artifact or its tests treats them as
a defect. Exercise the specificity ratchet live: on a scratch branch, loosen one
rule threshold so a second rule fires on a corpus case, observe the red, restore.
Confirm the exercise report's counts against a hand count of a real
`segfacet run` over the corpus, and state the **end-to-end** detection count
honestly in `progress.md` — how many of the 8 modes fire through plain `run_qc`
after items 120 and 121, not how many have a rule (**G7**). Confirm
`tests/corpus/` and the goldens are consistent with whatever items 120/121
regenerated, on a **fresh clone in a different directory**. Then update
`progress.md`: tick Stage 20's five acceptance criteria against what was actually
exercised, flip any Environment-Gated Capability Verification row this stage
affects to ✅ Verified where the environment allows (`python
.aide/scripts/aide.py env --profile <name>`), otherwise record why it stays ❓
Unverified. *Testable:* each acceptance criterion is ticked with a recorded
evidence sentence naming what was run; the ratchet's red-then-green replay is
recorded; the fresh-clone suite is green; `aide check` reports no new warnings.

---

## Current state (2026-08-27)

Generated on completion of [`queue-016.md`](queue-016.md), which delivered
**Stage 26 — Carried-Defect Remediation (pre-real-data)** (items 107–116, all
✅). Opens **Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability &
Specificity Harness**, whose Stage-26 dependency is now released. Stage 27
(feature schema taxonomy and coordinate system) follows this queue; Stages 16
and 21 remain behind that chain, and Stage 16 is additionally held by two human
gates awaiting a decision — real segmenter output handed over to this repo, and
access to the curated challenging-case source data. Stage 11 stays ⏸️ Deferred
and Stage 15 ❌ Excluded.
