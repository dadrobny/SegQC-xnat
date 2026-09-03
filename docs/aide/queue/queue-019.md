# FACET — Work Queue 019
> **Status:** ✅ Closed — superseded by queue-020 (2026-09-03). **Cut after item
> 138.** Items 136, 137 and 138 merged. Items 139, 140, 141 and 142 are ⏸️
> Deferred in [`../progress.md`](../progress.md): each rested on a definition of
> the §6 failure modes that did not exist, so they are re-specified against
> Stage 30's specification and re-queued after its maintainer sign-off (roadmap
> Stage 20's 2026-09-03 annotation;
> [`../failure-mode-taxonomy-handover.md`](../failure-mode-taxonomy-handover.md)
> §9, §12.1). Their numbers are kept.

> **Created:** 2026-09-02
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 20**; supersedes the completed [`queue-018.md`](queue-018.md)
> (Stage 29, closed 2026-08-31).

---

## Scope of this queue

Delivers roadmap **Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability &
Specificity Harness** (G2, G7): seven items covering the stage's live
deliverables plus the stage validation, under `loop.queue_cap = 10`. The queue
stops at the stage boundary — Stage 27 is next in the pinned run order and is
not drawn on here.

Stage 20 is an **audit stage**: it makes the relationships between failure
modes, rules and features visible and enforceable, and it fixes one recorded
metric-surface shortfall. It is not a rule-writing stage. An item that
discovers a rule is wrong records the finding and hands back rather than
rewriting the rule.

**Why the stage runs now.** Roadmap Stages 26, 28 and 29 each recorded that
they must land *before* Stage 20, because they change the surfaces it audits
and the specificity baseline it pins. All three are ✅, so the baseline this
queue freezes is the post-Stage-28 rule behaviour rather than a snapshot about
to move.

### What Stages 28 and 29 already delivered — not re-queued

Stage 20's D4 ("close the reachability hole for modes 1/4/8") is **superseded
in part**. Modes 1 and 4 were one defect — the interpolating spline fit
(`splprep(..., s=0)`) — owned by Stage 28 and closed: item 120's held-out
per-label offset made mode 1 pipeline-detectable, item 132's smoothed-fit
monotonicity made mode 4 pipeline-detectable, and item 135's replay verified
both. **The FOV-headroom remedy D4 proposed for mode 1 is superseded with
them** — no field of view produces a non-zero offset while `s = 0` holds, so
that remedy could not have worked. None of it is re-queued. What remains of D4
is **mode 8's mechanism**, carried by item 138's evidence-rung column.

D6 — widening item 100's mode-1 **severity-ladder base** — is a different
thing and is **not** superseded. It concerns Stage 18's metric surface
(`eval/severity_ladder.py`'s `unanchored_foreground_fraction` ladders), not
Stage 28's offset feature, and its measured shortfall is unchanged. It is
item 141.

### Re-measured 2026-09-02 while scoping this queue

The roadmap's Stage 20 goal paragraph states the position as of 2026-07-25.
Three of its numbers have since moved, so items start from the current state:

- **5 of 10 registered rules fire** on the nine-case corpus through plain
  `run_qc` — `border`, `coverage`, `fragmentation`, `mislabel`, `sequence`.
  The roadmap says 4; `mislabel` moved in at Stage 28. Firing on zero cases:
  `bounds`, `intensity`, `intensity_reference_delta`, `overlap`,
  `reference_delta`.
- **1 of 9 cases fires nothing at all** through the pipeline
  (`mode8_force_overlap`), not 3 of 9. The pipeline-detected mode count is
  **7 of 8**, agreeing with `tests/corpus/manifest.json`.
- **Cross-talk is no longer 0/9.** `mode6_crop_at_border` fires `mislabel` in
  addition to its designated `border`. The roadmap's stated reason for
  adopting the specificity assertion now — *"cross-talk today is 0/9, so the
  assertion is free to adopt"* — no longer holds, and item 140 must adjudicate
  that pair before it can enforce anything.

Three further facts shape the item boundaries:

- **The rule → mode map is derived, never declared.**
  `catalogue.py::_scan_synth_rule_mode_map` AST-scans `src/segfacet/synth/*.py`
  for `Expectation(failure_mode=…, expected_rule_ids=…)` literal pairs, so a
  rule is attributed to a §6 mode **only if a corpus case designates it**. Six
  rules map that way (`border`→6, `coverage`→5, `fragmentation`→2,3,
  `mislabel`→1,4, `overlap`→8, `sequence`→7); the four the stage is asked to
  disposition map to nothing **by construction**, whatever the truth about
  them.
- **There are two committed corpora, with different manifest schemas.**
  `tests/corpus/manifest.json` (nine cases) carries `failure_mode` and
  `expected_rule_ids`; `tests/corpus/intensity/manifest.json` (four cases —
  `clean_hu`, `implausible_metal`, `implausible_soft_tissue`,
  `degenerate_uniform`) carries neither. So `intensity` **is** exercised by a
  committed corpus while deriving no mode, and an exercise report reading only
  the first manifest would call it unexercised and be wrong.
- **`fuse` is registered and generates no case.** `FusePerturbation`
  (`synth/component_shape.py`, registered `"fuse"`) is the tenth operator; the
  nine `CASE_RECIPE` entries use the other nine.
- **Mode 6's specificity margin is 0.3585 and mode 8's is 1.038**
  (`eval/severity_ladder.py::RECORDED_MARGINS`), both attributed by
  `KNOWN_CROSS_MODE_COUPLINGS` to mode 1's ladder being FOV-capped at
  ~19.8 mm max `displacement_mm`.
- **`verify_case` asserts a floor, not a ceiling.**
  `synth/regression.py:246` checks that the designated rule fires and the
  offending labels match; nothing checks that no *other* rule fires.

### Scope fence for the whole queue

**Root documents are not edited from inside an item.** Item 137 may conclude
that the mode catalogue is short a mode rather than that a rule is
speculative; if it does, it **records the finding and stops**.
[`../vision.md`](../vision.md) §6 and [`../roadmap.md`](../roadmap.md) change
only through their own loop entry point and a reviewed PR, and no acceptance
criterion in this stage requires either to change — every one of them is
satisfiable by *recording* a disposition with its reason.

**Nothing here is gated.** The two ⏳ Awaiting human gates in
[`../progress.md`](../progress.md) (real segmenter output handed over; access
to the curated challenging-case data) block **Stage 16 only**. No Stage 16
work is in this queue and no item below depends on either decision.

**Prioritisation.** Items 136 → 137 → 138 → 139 are one critical path: the
declaration seam must exist (136) before a judgement can be recorded through
it (137), the matrix reads those declarations (138), and the exercise columns
extend the same generated artifact (139). Items **140** (the specificity
ratchet) and **141** (the severity-ladder base) are independent of that chain
and of each other — `aide claim` may offer them in any order, and nothing
breaks if it does. Item 142 closes the stage and must be last.

**Numbering.** Continues at the next free integer: **136–142**.

---

## Work items

### Item 136: Declare each rule's targeted §6 failure modes at the rule layer

Give the `rule_id → §6 mode` relationship a place to be **stated**, because
today it can only be **inferred**. `catalogue.py::_scan_synth_rule_mode_map`
derives the whole mapping by AST-scanning `src/segfacet/synth/*.py` for
`Expectation(failure_mode=…, expected_rule_ids=…)` literal pairs, so a rule is
attributed to a mode only when a corpus case designates it for that mode. The
consequence is structural, not incidental: the four rules Stage 20 is asked to
disposition are mode-less *by construction*, no judgement about them can be
recorded through the existing mechanism, and the matrix's **rule → mode**
direction — one of the two the stage requires to be complete — has nowhere to
live. Add a declaration seam owned by the rule layer: every registered rule
states the §6 mode(s) it targets, or states that it targets none together with
the reason. The corpus-derived map becomes *corroborating evidence* rather
than the source of truth, and disagreement between the two is a test failure
in **both** directions — a declared mode no corpus case supports, and a case
designating a rule for a mode the rule does not declare. Populate the seam in
this item only for the six rules the corpus already corroborates (`border`→6,
`coverage`→5, `fragmentation`→2,3, `mislabel`→1,4, `overlap`→8,
`sequence`→7); the four contested ones are item 137's, and this item must not
pre-empt them. `catalogue.py`'s `failure_modes` / `mode_evidence` derivation
gains the declaration as a source alongside `per_mode_metric` and
`rule_mode_map`, and must keep agreeing with item 104's drift test. *Testable:*
every registered rule carries a declaration; the six corroborated declarations
equal the corpus-derived map exactly; a deliberately wrong declaration fails
the agreement test with a message naming the rule and the mode, in each
direction; the regenerated feature catalogue's `failure_modes` column is
unchanged for every path (this item adds a source, it does not yet move an
attribution) and the catalogue regenerates byte-identically.

### Item 137: Disposition the four mode-less rules

Fill item 136's seam for the four registered rules that map to no §6 failure
mode — `bounds`, `intensity`, `reference_delta` and
`intensity_reference_delta` — closing at its root the G8 shortfall Stage 19
recorded and could not close (the 72-entry *statused-but-mode-unmapped*
bucket, `mode_evidence == ("rule_unmapped",)`). Each rule gets either a
mapping to one or more §6 modes with the evidence behind it, or a recorded
mode-less declaration with the reason — roadmap Stage 20's acceptance accepts
both, and a **silent** row is the only unacceptable outcome. Three measured
facts constrain the judgement. `intensity` is demonstrably useful yet names no
catalogued mode: it is exercised by `tests/corpus/intensity/manifest.json`'s
four cases, whose manifest carries no `failure_mode` field at all, and
implausible HU is not among vision.md §6's eight modes. `reference_delta` and
`intensity_reference_delta` are *mechanisms* — deviation from a normative
distribution — rather than mode-specific detectors, so they may legitimately
map to several modes or to none, and the disposition should say which and why
rather than picking the tidier answer. `bounds` reads per-label geometric
extent against plausible ranges, which overlaps modes 2 and 5 in substance
while no corpus case designates it. Where the evidence says the **mode
catalogue is short a mode** rather than the rule being speculative, record that
finding and stop: `vision.md` §6 is a root document, changed only through its
own entry point and a reviewed PR, and editing it is explicitly out of this
item's scope. *Testable:* all ten registered rules carry a declaration; each of
the four carries either ≥1 mode with named evidence or a non-empty mode-less
reason; no catalogue path still reports `mode_evidence == ("rule_unmapped",)`
while its consuming rule carries a declaration; `aide scope` confirms neither
`vision.md` nor `roadmap.md` was modified by the item.

### Item 138: The generated failure-mode ↔ rule ↔ feature traceability matrix

Build the stage's central artifact, **generated** rather than hand-maintained:
eight §6 failure modes × the ten registered rules × the features each rule
actually consumes, assembled from item 103's catalogue, the rule registry,
items 136/137's declarations and a corpus run. Score the three directions
**separately**, per roadmap Stage 20's 2026-08-11 clarification, because they
do not mean the same thing: **mode → rule** and **rule → mode** must be
complete and a hole in either is a defect, while **feature → rule is
deliberately incomplete** — a leaf path no rule reads is inventory
(`unwired`), never a gap. The artifact must say so *where it reports that
count*, so a future reader cannot mistake it for a shortfall. Every mode row
carries its **evidence rung**: `synthetic-demonstrable`, `needs real data (or
a corpus the fixtures cannot express)`, or `structurally unobservable in the
supported input format`. That last rung is D4's remaining half — **mode 8**: a
single-channel integer label map cannot assign two labels to one voxel, so
`overlaps[]` populates only on a map deliberately corrupted to violate that
invariant, which no real segmenter output can be. The `overlap` rule and the
six fields it reads are correct and fully wired; mode 8 therefore **stays**
`detection="reconstructed_record"` in `tests/corpus/manifest.json` with its
mechanism recorded, and is not to be "fixed". Mode 7's rung records its own
cap (`rank(v) == v - 1` under the TPTBox default admits a single rank descent,
so §6.7's own `L1 → T12 → L2 → L5` example is not representable at rung 1);
modes 1 and 4 are `synthetic-demonstrable` as of items 120/132 and are not
reopened here. Generated like the feature catalogue — zero-argument
regeneration, byte-reproducible run-to-run, written with `\n` bytes and pinned
`text eol=lf` in `.gitattributes` (see CLAUDE.md's Gotchas; the pin is not
optional for a committed byte-reproducible text fixture). *Testable:* the
artifact regenerates byte-identically run-to-run and from a clean tree; every
one of the eight modes has ≥1 rule and a non-empty evidence rung, and mode 8's
rung names the single-channel mechanism; every registered rule appears in the
rule → mode direction; the feature → rule count is reported with its
"inventory, not a gap" qualifier asserted, not merely written; a deliberately
un-declared rule makes the rule → mode direction fail loudly; `aide check`'s
`.gitattributes` lint is clean for the new path.

### Item 139: Per-rule and per-operator corpus-exercise reporting

Extend item 138's generated artifact with the two exercise directions, so that
neither "6 of 10 rules fire on zero cases" nor "the registered `fuse` operator
generates no corpus case at all" can recur unnoticed. **Per rule:** exercised
by ≥1 committed corpus case, or recorded unexercised **with its mechanism** —
and the report must span **both** committed corpora, because
`tests/corpus/intensity/manifest.json`'s four cases exercise `intensity` while
carrying no `failure_mode` / `expected_rule_ids` fields, so a report reading
only `tests/corpus/manifest.json` would call `intensity` unexercised and be
wrong. Measured 2026-09-02 through plain `run_qc` on the nine geometric cases,
five rules fire (`border`, `coverage`, `fragmentation`, `mislabel`,
`sequence`) and five do not — and three of those five have a *mechanism*
rather than an absence of fixtures: `synth/regression.py::pipeline_findings`
calls `run_qc` with the segmentation alone, attaching neither `image_features`
nor `reference`, so `intensity`, `reference_delta` and
`intensity_reference_delta` cannot fire on that path whatever the fixtures
contain. Record that per rule; a bare count would misattribute a harness
limitation to the rule. **Per operator:** every registered `Perturbation`
generates ≥1 corpus case or is recorded unused with a reason —
`FusePerturbation` is the one that does not, and its own module docstring
already notes that the shipped default lumbar `bounds` cannot fire on a
two-label fuse, which is evidence for the record rather than a reason to add a
case here. This item closes Stage 20's "every registered rule is exercised by
≥1 case or recorded as unexercised with a reason" acceptance. Adding corpus
cases is **out of scope**: the deliverable is the report and its reasons, not
a bigger corpus. *Testable:* the extended artifact regenerates byte-identically;
every registered rule and every registered operator appears exactly once with
either an exercising case or a non-empty reason; the report spans both
manifests (deleting a case from the intensity manifest changes the report);
the three harness-limited rules carry the `run_qc`-inputs mechanism rather
than a bare "no case"; a newly registered dummy rule or operator with neither
a case nor a reason fails the report's completeness test.

### Item 140: Adopt the specificity ratchet — no unintended rule may fire

`verify_case` (`synth/regression.py:246`) asserts that the designated rule
fires and that the offending labels match; it has never asserted that **no
other** rule fires, and Stage 20 plans to adopt that ceiling as a ratchet. The
roadmap's stated reason for adopting it now — *"cross-talk today is 0/9, so
the assertion is free to adopt"* — **no longer holds**: measured 2026-09-02,
`mode6_crop_at_border` fires `mislabel` alongside its designated `border`, so
1 of 9 cases carries cross-talk. The item has two halves, in order. **First,
adjudicate that pair.** A vertebra cropped at the FOV face has genuinely moved
off the curve the remaining vertebrae define, so item 120's held-out offset
may be reporting a true co-detection rather than a false positive — decide,
against the measurement, whether `(mode6_crop_at_border, mislabel)` is a
declared allowed co-detection carrying its reason or a specificity defect in
`mislabel`, and record which and why. **Second, enforce the assertion for
every corpus case**, with an explicit allowlist of declared co-detections that
an entry must carry a reason to join — a ratchet, so the allowlist can shrink
but never silently grow, and a new unintended firing fails rather than being
absorbed. `tests/corpus/manifest.json`'s `expected_rule_ids` is the existing
statement of what each case *should* fire and the assertion must agree with it
rather than duplicate it. **Do not weaken the assertion to make the mode-6
case pass**, and do not retune `mislabel`'s threshold to suppress the firing —
if the adjudication says defect, the finding is recorded and handed back, not
fixed here. *Testable:* the assertion runs for all nine cases; the mode-6
co-detection is either allowlisted with a recorded reason or recorded as a
defect, never silently tolerated; a deliberately added unintended firing (a
temporarily loosened threshold on a scratch branch) fails the assertion naming
the case and the unexpected rule; an allowlist entry with no reason fails its
own shape test; removing an allowlist entry that is still needed fails, so the
ratchet direction is itself tested.

### Item 141: Widen the mode-1 severity-ladder base so mode 6 clears on its own

Stage 18 shipped with one unmet specificity bar and a root cause recorded
**outside** the mode that failed it. Mode 6's margin is **0.3585** against the
strict `> 1.0` bar, because its ladder drives mode 1's
`unanchored_foreground_fraction` 2.79× harder than mode 1's *own* ladder
does — and mode 1's ladder is capped by the fixture's field of view at
~19.8 mm max `displacement_mm`
(`eval/severity_ladder.py::KNOWN_CROSS_MODE_COUPLINGS`, `RECORDED_MARGINS`).
Widen item 100's mode-1 ladder base — a larger FOV, or a base with headroom
for a 30–40 mm displacement — so mode 1's own metric swing is set by the
perturbation rather than by the fixture's walls, then re-measure the full
cross-mode response matrix. Mode 6 should clear **without touching mode 6**,
which is the entire point of the change. The same cause caps mode 8, whose
margin is **1.038** — clearing the bar by about 4% — with its recorded
coupling attributing most of its `unanchored_foreground_fraction` response to
a rigid-translation artefact "nearly matching mode 1's own full swing"; so
re-measure and re-record **both** couplings, retiring a
`KNOWN_CROSS_MODE_COUPLINGS` entry only if the new measurement retires it, and
never by deleting an entry to make a bar pass. This is Stage 18's *metric
surface*, not Stage 28's offset feature — nothing here is superseded by the
spline work, and `features/spline_offset.py` is not in scope. Record the
outcome against Stage 18's acceptance box as a **dated amendment**
(`aide progress amend`), never by rewriting the attestation, which is
immutable. *Testable:* the widened base admits a 30–40 mm displacement without
FOV clipping, shown by the ladder's own top rung no longer saturating; mode 6's
re-measured margin clears `> 1.0` with mode 6's ladder definition unchanged
(diffed to prove it); mode 8's re-measured margin is recorded whichever way it
moves; `RECORDED_MARGINS` and `KNOWN_CROSS_MODE_COUPLINGS` are regenerated
from the measurement and every transcription rule they document (responses
rounded up, margins rounded down, 4 significant figures) still holds; item
100's and item 102's existing ladder tests pass against the new base or are
updated with the reason recorded.

### Item 142: Validate stage 20: Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness

Replay Stage 20's acceptance end-to-end rather than re-running the unit suite.
Regenerate the traceability artifact from a clean tree and confirm every §6
failure mode has ≥1 rule **and** a non-empty evidence rung, with mode 8's
naming the single-channel mechanism (**G2**). Confirm every registered rule
maps to ≥1 mode or carries a mode-less reason, and that every rule is
exercised by ≥1 case across **both** committed corpora or carries an
unexercised reason with its mechanism (**G2**). Drive the specificity
assertion over all nine corpus cases and confirm it is enforced, that each
allowlisted co-detection carries a reason, and that a deliberately introduced
unintended firing fails it on a scratch branch which is then discarded.
Re-measure the cross-mode margins after item 141 and confirm mode 6 clears
without mode 6's ladder having changed. Then **state the end-to-end detection
count honestly in `progress.md`** (**G7**) — currently 7 of 8 modes
pipeline-detected, mode 8 excepted with its mechanism, and 5 of 10 rules
firing on the geometric corpus — as a recorded number with what it was
measured on, not an implication. Finally update `progress.md`: tick Stage 20's
five acceptance criteria against what was actually exercised via
`aide progress accept`, leaving honestly unticked any criterion the replay
does not establish and recording why, and flip any Environment-Gated
Capability Verification row this stage affects to ✅ Verified where the
environment allows (`python .aide/scripts/aide.py env --profile <name>`),
otherwise recording why it stays ❓ Unverified. *Testable:* each acceptance
criterion is ticked or left unticked with a recorded evidence sentence naming
what was run; the generated artifacts regenerate byte-identically from a clean
tree; the full suite is green; `aide check` reports no new warnings.

---

## Current state (2026-09-02)

Generated on completion of [`queue-018.md`](queue-018.md), which delivered
**Stage 29 — Golden Retirement & Test-Artifact Hygiene** (items 126–135, all
✅; two of three acceptance criteria ticked, the third left honestly unticked
on its four-level clause alone, with the other two clauses of that box
verified). Opens **Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability &
Specificity Harness**, whose two prerequisite stages (28 and 29) have both
landed, so the specificity baseline it pins is the current rule behaviour.

Run order from here: **20 → 27 → 21 → 16**. Stage 27 (feature schema taxonomy
and coordinate system) follows this stage and is where the *feature*
`retune`/`retire` calls Stage 19 recorded find their carrier. Stage 16 remains
held by two human gates awaiting a decision — real segmenter output handed
over to this repo, and access to the curated challenging-case source data;
neither blocks anything in this queue. Stage 11 stays ⏸️ Deferred and Stage 15
❌ Excluded.
