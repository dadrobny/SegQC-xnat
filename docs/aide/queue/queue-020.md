# FACET — Work Queue 020

> **Created:** 2026-09-03
> Step 4 of the AIDE loop · derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md) ·
> each item below is specced into [`../items/`](../items/) and tracked in
> `../progress.md` (queue state is derived there, never declared here).
> Opens **Stage 30**; supersedes [`queue-019.md`](queue-019.md) (Stage 20, cut
> after item 138 on 2026-09-03).

---

## Scope of this queue

Delivers roadmap **Stage 30 — Failure-Mode Specification: the §6 catalogue as an
authored source** (G2, G7, G8): nine items covering the stage's eight
deliverables D0–D7 plus the stage validation, under `loop.queue_cap = 10`. The
queue stops at the stage boundary — the remainder of Stage 20 is next in the
pinned run order (**30 → 20 (remainder) → 27 → 21 → 16**) and is not drawn on
here.

Stage 30 is an **authoring stage with a human checkpoint**, in the sense Stages
19 and 27 are. It writes the specification every later check consults, so a
person reads it before anything is measured against it. It writes **no new
rules** and adds no corpus cases beyond what the ninth mode needs; an item that
finds a rule wrong records the finding and hands back.

**Why the stage runs now.** Queue-019 produced three defects of one class in
four items: a factual claim about the failure modes authored as prose, shipped
into a committed artifact, and accepted by a check that tested the claim's
*shape* rather than its *truth* — item 137's evidence sentence past a
`len(...) >= 40` floor, four of eight `MODE_RUNGS` mechanism sentences past a
token-presence check, and a `rule_to_mode: complete` flag derived from
declaration state. Two of the five corrected sentences were provably not
catchable by any such check, because the error was about *which of two
genuinely-read sibling fields* drives detection. The root cause is that no
document defines the modes. This stage authors that document.

### The five partial sources this stage collapses

Verified in the tree at `aide/queue-020`'s base (2026-09-03), so items start
from resolvable locations rather than from the roadmap's prose:

- [`../vision.md`](../vision.md) §6's eight-item list — now explicitly the
  **interim record and the seed**, per vision v3.
- `FAILURE_MODE_NAMES` — `src/segfacet/synth/perturbation.py:62`, re-exported
  through `synth/__init__.py` and read by `eval/per_mode.py`,
  `eval/severity_ladder.py` and four `synth/` operator modules.
- `MODE_ANCHOR_PATHS` — `src/segfacet/feature_docs.py:353`, the Stage-18
  per-mode *metric*'s read path, consumed by `catalogue.py:880` and
  `traceability.py:364` and used there as the closed key set of valid modes.
- The `Expectation(failure_mode=…, expected_rule_ids=…)` literals in
  `src/segfacet/synth/*.py`, AST-scanned by
  `catalogue.py::_scan_synth_rule_mode_map`.
- `MODE_RUNGS` — `src/segfacet/traceability.py:146`, plus that module's parse of
  `docs/aide/vision.md` §6's titles at `traceability.py:303-319`.

Item 138's generated matrix cross-checks these five without being able to
**adjudicate** them. Mode 6 is the proof: all three operational sources agree on
`border`, and the measurement shows `border` **and** `mislabel`.

### What human gate 3 already decided — encoded as data, not re-litigated

Gate 3 was approved 2026-09-03 (`../progress.md`, Human gates) and adopted
[`../failure-mode-taxonomy-handover.md`](../failure-mode-taxonomy-handover.md)
§12 in full. No item below re-opens any of it; each encodes its half:

1. Modes 4 and 7 keep the Stage-18 metric path as anchor, and the rule's read
   path is a **separate, separately-labelled column** — item 148 renders it,
   item 151 checks it.
2. `mode6_crop_at_border` fires `mislabel` as a **true co-detection**:
   `expected_firing = {border, mislabel}`, with the mode-1 / mode-6
   discriminator (a border-touching face) written into the specification —
   item 145.
3. The evidence rung attaches to each **mode ↔ rule edge**, authored; the
   mode's rung is derived as its strongest edge — item 145.
4. The §6 schema and four-state lifecycle are adopted, with `expected_firing`
   authored per corpus case and `implemented` / `validated` **derived** from
   live state — items 144, 145.
5. Items 139–142 stay held until D6's sign-off is recorded — item 150.

### Scope fence for the whole queue

**Root documents are not edited from inside an item.**
[`../vision.md`](../vision.md) and [`../roadmap.md`](../roadmap.md) change only
through their own loop entry point and a reviewed PR. Vision v3 §6 already
carries the principles this stage implements, and no acceptance criterion in
Stage 30 requires either document to change — a finding that the principles are
wrong is recorded in `insights.md` and handed back.

**No new rules, and no new corpus cases beyond the ninth mode's.** The one
corpus change sanctioned here is `tests/corpus/intensity/manifest.json` gaining
the `failure_mode` and expected-firing fields the geometric manifest already
carries (item 146). Item 143's regeneration changes committed corpus *values*,
not the case list.

**A rule whose firing moves under item 143 is a finding, recorded and handed
back** — never a rule change made to keep a green suite green.

**Nothing here is gated by the two ⏳ human gates.** Gates 1 and 2 (real
segmenter output handed over; access to the curated challenging-case data)
block **Stage 16 only**. No Stage 16 work is in this queue. Gate 3 is
✅ Approved and is an input above, not a blocker. Item 150 **raises a new gate**
— that is its deliverable — and only a person resolves it.

**Byte-reproducible committed artifacts.** Items 144 and 149 write generated
text fixtures. Both must write bytes with `\n` (`write_bytes`, not
`write_text`) and be pinned `text eol=lf` in
[`../../../.gitattributes`](../../../.gitattributes) — see CLAUDE.md's Gotchas;
the pin is not optional, and `aide check`'s `.gitattributes` lint must be clean
for each new path.

**Prioritisation.** Item **143** lands first and alone: every expected firing
set authored afterwards must be measured on the corrected corpus, so no item
below may author one before it merges. Items **144 → 145 → 146 → 147 → 148 → 149
→ 150** are then one critical path, in that order — the schema must exist (144)
before the eight modes are entered through it (145), the ninth mode tests the
lifecycle the eight established (146), the five partial sources can only be
collapsed onto a populated specification (147), the catalogue's attribution
granularity is fixed at the seam 147 rewrites (148), the matrix re-points at the
finished specification (149), and the sign-off reads the rendering 149
completes (150). Item **151** closes the stage and must be last.

**Numbering.** Continues at the next free integer: **143–151**. Items 139–142
keep their numbers and are ⏸️ Deferred, re-specified against this stage's
specification and re-queued after item 150's sign-off.

---

## Work items

### Item 143: Correct the synthetic corpus's S-axis stacking before anything is measured

`synth/clean_gt.py::build_clean_spine` stacks ascending labels along **ascending
axis 2**, so every in-repo synthetic driver advances **superiorly** while real
VerSe input advances **caudally**. That inversion hid item 131's
traversal-direction defect for nine items and flips the sign of any future
feature measured against +S (carried defect, recorded 2026-08-31, item 131's
spec). Correct the stacking so the synthetic fixtures advance caudally like real
VerSe input, then regenerate every committed value the change moves: the
geometric corpus (`tests/corpus/manifest.json` and its fixtures), the intensity
corpus (`tests/corpus/intensity/`), and both reference artifacts
(`src/segfacet/reference/reference_default.json`, built from `build_clean_spine`
and `paint_clean_scan`, and `reference_verse_v1.json`, built from real VerSe19).
For each committed artifact record **whether the correction moved it and by how
much** — a real-cohort artifact that does not move is the expected result and is
evidence, not an omission. This is a **corpus-value change, not a rule change**:
a rule whose firing set moves under it is a finding recorded in `insights.md`
and handed back, and no threshold is retuned here to keep a case passing. This
item lands first and alone precisely so the expected firing sets items 145 and
146 author, and the specificity baseline Stage 20's ratchet later pins, are
measured on the corrected corpus. *Testable:* `build_clean_spine`'s label order
advances caudally along +S, asserted directly on the built array rather than on
a downstream feature; every regenerated committed artifact regenerates
byte-identically run-to-run and matches its committed copy through the item-127
comparison helper; the per-artifact moved/unmoved record is present and each
entry names what was compared; the full suite is green, with every test whose
expected value moved updated to the regenerated value and no test disabled;
`aide scope` confirms no `heuristics/` threshold was changed.

### Item 144: The failure-mode specification module and its generated rendering

Create the authored source vision v3 §6 describes: one **frozen declaration per
mode** in a module under `src/segfacet/`, shaped after `RuleModeDeclaration`
(`heuristics/rule.py`), carrying §6's fields — `id`, `name`, `definition`,
`discriminator`, `observability` (`single-channel-observable` ·
`needs-paired-scan` · `structurally-unobservable`), `candidate_features`
(hypothesised feature paths, with the Stage-18 per-mode *metric*'s anchor path
labelled as exactly that and never as what a rule reads), `intended_rules`
(naming the detector where a rule has several), `corpus_cases` each with an
**expected** firing set, `severity`, `status`, and `provenance` (`hypothesised` ·
`discovered`). The lifecycle `status` is **authored only for `proposed` and
`specified`**; `implemented` (≥1 registered rule declares the mode) and
`validated` (a corpus case's measured firing equals its expected firing) are
**derived from live state**, and a hand-set value that disagrees is a test
failure naming the mode. This item builds the schema, the validation and the
rendering — not the eight entries, which are item 145's; ship it with whatever
minimal seed set proves the machinery and let 145 populate it. Render to
`docs/aide/failure_modes.generated.{md,json}` by zero-argument regeneration; the
markdown is the review surface item 150 signs. *Testable:* the declaration
rejects a missing or empty required field, a status outside the four-state
vocabulary, an observability class outside the three, and a provenance outside
the two, each with a message naming the offending mode and field; `evidence`-
style tuple fields reject a bare string and a list, so a forgotten pair of
parentheses cannot iterate character-wise; a hand-set `implemented` or
`validated` that disagrees with the registry or the corpus fails a test naming
the mode; both artifacts regenerate byte-identically run-to-run and from a clean
tree, are written with `\n` bytes, and `aide check`'s `.gitattributes` lint is
clean for both paths.

### Item 145: The eight hypothesised modes, specified with discriminators and per-edge rungs

Enter every one of vision §6's eight modes into item 144's specification with
every field populated. Each `discriminator` names its **nearest neighbours** and
what separates them: mode 6 has a border-touching face and mode 1 has none;
modes 2 and 3 differ in whether the dominant body is intact; modes 1 and 4
differ in whether the label's *identity* or its *position* is wrong. Gate 3's
decisions are encoded as **data, not prose**: `mode6_crop_at_border` carries
`expected_firing = {border, mislabel}` with its recorded reason (the crop
displaces the centroid off the curve — re-measure the displacement on item 143's
corrected corpus and record the measured value, do not carry forward the
pre-correction 17.5 mm); the evidence rung is authored **per mode ↔ rule edge**
(`synthetic-demonstrable` · `needs-real-data` · `structurally-unobservable`) and
each mode's rung is **derived as its strongest edge**, so the analytic-only
edges — `reference_delta` on modes 1 and 2, `bounds` on mode 2, which no corpus
case demonstrates — are visibly weaker than the demonstrated ones; mode 8 stays
`structurally-unobservable` with its single-channel mechanism (a voxel in an
integer label map holds exactly one label, so `overlaps[]` populates only on a
record deliberately corrupted to violate that invariant); mode 7's rung records
its single-rank-descent cap (`rank(v) == v - 1` under the TPTBox default, so
§6.7's own `L1 → T12 → L2 → L5` example is not representable at rung 1). Every
expected firing set is **measured on the post-item-143 corpus**, never
transcribed from a queue-019 document. *Testable:* all eight modes carry every
schema field; every mode ↔ rule edge carries a rung from the closed vocabulary
and every mode's rung equals the strongest of its edges, checked by construction
rather than by transcription; `mode6_crop_at_border`'s expected set is
`{border, mislabel}` with a non-empty reason and the recorded displacement
matches a fresh measurement; mode 8's rung and mechanism name the single-channel
invariant; mode 7's rung names the single-descent cap; the eight `name` values
equal `vision.md` §6's list, derived from the document rather than
hand-transcribed; a deliberately weakened edge rung changes the derived mode
rung, so the derivation is proven live.

### Item 146: The ninth mode enters through the lifecycle, and the first `proposed` entry

Add **implausible tissue under a label** (soft tissue or air, metal or implant, a
degenerate uniform region) as a specification entry with
`observability = needs-paired-scan` and a stated modality (CT) — the mode
`insights.md` recorded as missing on 2026-09-02 and the mode the `intensity` and
`intensity_reference_delta` rules already serve. Move those two rules'
`RuleModeDeclaration`s from mode-less to declaring it, and give
`tests/corpus/intensity/manifest.json`'s four cases (`clean_hu`,
`implausible_metal`, `implausible_soft_tissue`, `degenerate_uniform`) the
`failure_mode` and expected-firing fields the geometric manifest already
carries. It is expected to land at `implemented` or `validated` on live state,
and it is **the test of vision §6's claim that a mode can be added without
everything being rebuilt** — so record what had to change to add it. Driving
those four cases needs the intensity sibling of
`synth/regression.py::pipeline_findings` that has never existed
(`insights.md`, item 139, 2026-09-03 — item 139 re-composed it privately inside
`traceability.py`); **build it in `synth/regression.py`**, where the geometric
one lives, so the second committed corpus finally has a public harness. Alongside
it, add the catalogue's first **`proposed`** entry — *collapsed or duplicated
label set*, the silent case where two labels share an exact centroid, Stage 3
degrades, every `stage3`-reading rule short-circuits and no finding of any kind
is raised (carried defect, item 129, 2026-08-31) — with
`candidate_features = (features.stage3_unavailable,)`, no `intended_rules`, and
no corpus case, so the conformance report shows a listed, unimplemented mode for
the first time. **The rule for it is not this stage's**, and adding one here is
out of scope. *Testable:* the ninth mode is present with every schema field and
derives to `implemented` or `validated` from live state, never a hand-set value;
both intensity rules declare it and the declaration↔specification check passes
in both directions; each of the four intensity cases carries a `failure_mode` and
an expected firing set whose measured counterpart equals it, driven through the
new public `synth/regression.py` harness rather than through `traceability.py`;
the `proposed` entry renders as unimplemented — not silent, not a hole — in the
rendering, asserted on the rendered output; a `proposed` entry that acquires a
declaring rule without its status being re-derived fails a test.

### Item 147: Collapse the five partial sources onto the specification

Make the specification the single record the operational claims are checked
against, and close by replacement the three located defects in the mechanism it
supersedes. `FAILURE_MODE_NAMES`
(`synth/perturbation.py:62`) is derived from the specification or retired;
`MODE_RUNGS` (`traceability.py:146`) is retired in favour of item 145's per-edge
rungs; `MODE_ANCHOR_PATHS` (`feature_docs.py:353`) **stays**, documented as the
Stage-18 per-mode metric's read path, referenced from `candidate_features`, and
never presented as what a rule reads; `traceability.py`'s parse of `vision.md`
§6 (`traceability.py:303-319`) and the tests that hand-transcribe that list
re-point at the specification as primary, with **one** conformance check kept in
the other direction — the eight seed entries' names equal `vision.md` §6's list
— so the vision stays the seed and the specification the truth. `Expectation`
and `RuleModeDeclaration` remain the two operational claims, now checked against
the specification in **both** directions: a declared mode the specification does
not list; a specification `intended_rule` that declares no such mode; a corpus
case the specification does not carry, or that carries a different expected set.
Three defects close here because the specification replaces the mechanism they
sit in (`insights.md`, item 136, 2026-09-02, all three): the `"corpus"` evidence
tag is an **exact-element membership test** over an unvalidated tuple
(`catalogue.py:1046`), so a near-miss such as `evidence=("corpus:Crop…",)`
silently disables the declaration-to-corpus check and reports agreement;
`RuleModeDeclaration.__post_init__` (`heuristics/rule.py:113-118`) never checks
that `evidence` and `modes` are **tuples**, so a bare string binds the reserved
tag by substring accident and a list-valued `modes` stays mutable in place; and
the corpus-to-declaration direction (`catalogue.py:1027-1035`) iterates the
**registered rules**, so a corpus case designating a `rule_id` no rule registers
is never consulted and never reported. With per-edge rungs in the specification
the free-form `"corpus"` tag is **retired rather than hardened**. *Testable:* no
production module reads a mode name, rung or anchor set from any source other
than the specification, except `MODE_ANCHOR_PATHS` under its documented metric
label, asserted mechanically rather than by hand-listing; the eight seed names
still equal `vision.md` §6's list; each of the four disagreement shapes above
fails with a message naming the rule or case and the mode; a corpus case
designating an unregistered `rule_id` is reported, in the direction that was
previously blind; a bare-string or list-valued field is rejected at
construction; the whole `"corpus"` tag is gone from the tree.

### Item 148: Per-detector mode attribution, so the catalogue stops painting bookkeeping paths

Item 136's §6 mode attribution is **rule-granular**: every leaf path a declaring
rule consumes inherits that rule's full mode tuple, so
`docs/aide/feature_catalogue.generated.md` paints pure bookkeeping paths with
failure modes they cannot evidence — `reference_delta.lower_pct`,
`reference_delta.{label}.label` and `reference_delta.{label}.level_name` each
carry `failure_modes == (1, 2)`, and a reader cannot tell them apart from
`reference_delta.{label}.features.physical_volume_mm3.robust_z`, which genuinely
carries the mode-2 signal (`insights.md`, item 138, 2026-09-02). Item 138's
mode → feature direction inherits it and reports the granularity beside the list
rather than filtering, because narrowing needed a per-path mechanism claim no
shipped declaration carried. Fix it at the declaration seam item 147 rewrote:
`intended_rules` names the **detector**, and the declaration gains a
per-detector or per-path attribution the catalogue can render, so a bookkeeping
path is either excluded from the mode columns or rendered under an explicit
`bookkeeping` classification. Whichever of the two shapes is chosen, it is a
**declared** classification, not a heuristic over path names — an unclassified
path is a test failure, not a silent default. *Testable:* the three named
`reference_delta` bookkeeping paths no longer carry `failure_modes == (1, 2)` in
the regenerated catalogue, while
`reference_delta.{label}.features.physical_volume_mm3.robust_z` still does;
every consumed leaf path of every declaring rule carries an explicit
classification and an unclassified one fails a test naming the path and the
rule; the regenerated `feature_catalogue.generated.md` regenerates
byte-identically and its diff against the committed copy is exactly the
attribution change, with no other column moving; item 104's drift test still
passes.

### Item 149: The traceability matrix becomes the conformance report

Re-point item 138's `build_matrix` (`src/segfacet/traceability.py`) at the
specification as its **primary source**, so the generated matrix becomes the
conformance report vision §6 describes rather than a cross-check of five
sources. Per mode it renders the **derived** status, the per-edge rungs, and —
per corpus case, across **both** committed corpora — the **expected** firing set
beside the **measured** set with **agreement scored**. A disagreement is a
failure, which is the check none of queue-019's shape tests could express. The
Stage-18 metric anchor path and the rule's read paths render as **two separately
labelled columns**, never conflated (gate 3, decision 1). The per-rule and
per-operator **exercise columns** item 139 specified are **not** built here —
they stay Stage 20's, re-specified against this output. Two test-hygiene entries
are settled while the builder is open rather than after a third extension:
`tests/test_138_traceability_matrix.py` calls `build_matrix()` 42 times with no
shared fixture and every extension multiplies across the module (`insights.md`,
item 139, 2026-09-03) — set the call-count discipline now as **one fixture per
monkeypatch group**, never a cache inside the generator, which would defeat
exactly the adversarial tests that prove the report is live; and
`tests/committed_artifact_guard.py`'s closed `GROUNDS` vocabulary (five members
today) has no member for a **float-free** derived artifact (`insights.md`, item
138, 2026-09-02), which is what item 144's rendering and this matrix are — add a
sixth ground, `no-float-leaf`, discharged by the artifact's own no-float-leaf
test, so both make the byte-exact claim **under** the guard instead of beside it.
*Testable:* the matrix names the specification as its primary source and no
longer reads `MODE_RUNGS`; for every corpus case in both manifests the measured
firing set is compared to the specification's expected set and a deliberately
altered expected set fails, naming the case, the expected set and the measured
set; the anchor column and the read-path column are separately labelled and a
mode whose two differ renders both; the matrix regenerates byte-identically
run-to-run and from a clean tree; `test_138_traceability_matrix.py`'s
`build_matrix()` call count is bounded by a fixture-per-patch-group and asserted,
with every adversarial monkeypatch test still re-deriving; the `no-float-leaf`
ground is a sixth member of `GROUNDS`, both artifacts are allowlisted under it
with a reason, each carries a passing no-float-leaf test, and item 134's
vocabulary-length pin is updated to six with the reason recorded.

### Item 150: Maintainer sign-off of the failure-mode specification

The stage's human checkpoint, in the sense Stage 19's item-106 steering review
was one. Prepare `docs/aide/failure_modes.generated.md` as the review surface
and take the maintainer through it **entry by entry** — definition,
discriminator, expected firing sets, severities, observability, per-edge rungs,
lifecycle status and provenance for each of the ten entries (eight seed, the
ninth `implemented`/`validated`, the first `proposed`) — then record the date and
the outcome in the specification module's **own docstring**, the way Stage 19's
steering review was recorded in `feature_docs.py::STATUS_OVERRIDES`. Raise the
sign-off as a **human gate** in `../progress.md` via `aide gate` and leave it for
a person: no agent may approve or decline it, and **until the sign-off is
recorded, the remainder of Stage 20 is not queued** — items 139–142 stay ⏸️
Deferred. Where the maintainer's reading changes an entry, the change is made
here and the rendering regenerated before the gate is resolved; where it raises
something outside this stage, it is one line in `insights.md`. *Testable:* the
gate exists in `../progress.md` and is resolved only through `aide gate`, never
by a hand edit; the specification module's docstring carries the sign-off date
and outcome, and a test asserts a non-empty sign-off record naming a date that
is not in the future; every entry the review changed regenerates into both
artifacts byte-identically; `aide check` reports the gate's state without
warning about an unfilled slot; item 139's, 140's, 141's and 142's progress
bullets are still ⏸️ at the point the gate is raised.

### Item 151: Validate stage 30: Failure-Mode Specification — the §6 catalogue as an authored source

Replay Stage 30's acceptance end-to-end rather than re-running the unit suite.
Regenerate `docs/aide/failure_modes.generated.{md,json}`, the traceability
matrix and `feature_catalogue.generated.md` **from a clean tree** and confirm
each is byte-identical and names the specification as its primary source
(**G8**). Drive **every corpus case across both committed corpora** and confirm
the measured firing set equals the specification's expected set, with
`mode6_crop_at_border` at `{border, mislabel}` carrying its recorded reason
(**G2**). Confirm every mode ↔ rule edge carries an authored rung, every mode's
rung is derived from its edges, the analytic-only edges render as such, and mode
8's rung names the single-channel mechanism (**G2**). Confirm the derived
statuses against live state by hand-setting one to a disagreeing value on a
scratch branch, observing the failure, and discarding the branch. Confirm the
ninth mode is present at `implemented` or `validated` with both intensity rules
declaring it, that `FAILURE_MODE_NAMES` and `MODE_RUNGS` are derived from or
replaced by the specification, and that the eight seed names equal
[`../vision.md`](../vision.md) §6's list (**G8**). Confirm `build_clean_spine`
stacks caudally along +S, that every committed corpus value and both reference
artifacts were regenerated after the correction, and that **no expected firing
set in the specification predates it** (**G7**). Confirm item 150's sign-off is
recorded in the module with its date (**G8**). Then record in
[`../progress.md`](../progress.md) the resulting **per-status and per-rung
counts** as measured numbers with what they were measured on — never one number
over a list that mixes hypothesised and demonstrated modes. Finally tick Stage
30's seven acceptance criteria via `aide progress accept` against what was
actually exercised, leaving honestly unticked any criterion the replay does not
establish and recording why, and flip any Environment-Gated Capability
Verification row this stage affects to ✅ Verified where the environment allows
(`python .aide/scripts/aide.py env --profile <name>`), otherwise recording why it
stays ❓ Unverified. *Testable:* each acceptance criterion is ticked or left
unticked with a recorded evidence sentence naming what was run; every generated
artifact regenerates byte-identically from a clean tree; the per-status and
per-rung counts in `progress.md` match a fresh derivation from the specification;
the full suite is green; `aide check` reports no new warnings.

---

## Current state (2026-09-03)

Generated at the queue-019 boundary. Queue-019 was **cut after item 138**:
items 136, 137 and 138 merged (the rule-layer declaration seam, the disposition
of the four mode-less rules, and the generated traceability matrix), and items
139, 140, 141 and 142 are ⏸️ Deferred because each rested on a definition of the
§6 failure modes that existed in five partial sources and no specification. They
keep their numbers and are re-specified against this stage's specification in the
queue after item 150's sign-off.

Stage 20 stays **🚧 In Progress** — its goal, deliverables and acceptance are
immutable and stand as written, with the backward supersession record carried in
the 2026-09-03 annotation at the head of its roadmap section. Criteria 1 and 2
stay attested; criteria 3, 4 and 5 carry retraction trails from 2026-09-02.

Run order from here: **30 → 20 (remainder) → 27 → 21 → 16**. Stage 27 (feature
schema taxonomy and coordinate system) follows the remainder of Stage 20 and is
where the *feature* `retune` / `retire` calls Stage 19 recorded find their
carrier. Stage 16 remains held by two human gates awaiting a decision — real
segmenter output handed over to this repo, and access to the curated
challenging-case source data; neither blocks anything in this queue. Stage 11
stays ⏸️ Deferred and Stage 15 ❌ Excluded.
