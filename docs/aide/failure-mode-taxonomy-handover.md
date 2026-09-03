# Handover: the §6 failure-mode catalogue needs a specification

> **Status:** 🔍 Consumed by `/aide-feedback-loop` on 2026-09-03 — §12 records the
> disposition; the §10 decisions await gate 3 · **Created:** 2026-09-03
> Records why queue-019 was cut short after item 138, what the eight §6 failure
> modes actually are today (five partial sources, no specification), the measured
> ground truth as of 2026-09-03, and a proposed shape for a per-mode
> specification that lets the catalogue grow iteratively.
> No roadmap or vision edit is performed by this document; it exists to be
> consumed by `/aide-feedback-loop` and the create-vision / create-roadmap entry
> points.

---

## 1. Why this document exists

Queue-019 ("Stage 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity
Harness") produced **three defects of one class in four items**: a factual claim
authored as prose, shipped into a committed artifact, and accepted by a check
that tested the claim's *shape* rather than its *truth*.

| Item | The false claim | What the check tested | Found by |
|---|---|---|---|
| 137 | `reference_delta`'s evidence: "the only per-label feature the committed reference artifact carries is `physical_volume_mm3`" — it carries 21, including `spline_offset_mm`, §6 mode 1's own anchor | `len(evidence) >= 40` | post-merge review, corrected in `b1c593c` |
| 138 | four of eight `MODE_RUNGS` mechanism sentences (modes 1, 2, 4, 5, 6) | AC31: the sentence must name a token resolving against live state | post-merge review, corrected in `0db0fca` |
| 138 | `rule_to_mode: complete: true` for a rule declaring a mode outside `MODE_ANCHOR_PATHS` | completeness derived from declaration *state*, never from the modes themselves | same review, corrected in `0db0fca` |

Each fix made the *next* check stronger, and each next check was still bypassed.
Commit `b090822` replaced AC31's token check with two real ones — a named feature
path must be consumed by one of the mode's declared rules, and a measured-firing
claim must equal the live pipeline firing set. Those hold. But two of the five
corrected sentences (**modes 5 and 6**) are provably **not** catchable by any such
check, because both named a real, rule-consumed path of the correctly-named rule;
the error was about *which of two genuinely-read sibling fields drives detection
for that corpus case*. `coverage` reads both `missing_levels[]` and
`present_levels[]`; `border` reads all four in-plane faces.

**The root cause is not the checks.** It is that no document defines the modes,
so there is no ground truth for a check to consult. Every reviewer had to
re-derive the truth from source each time. The prose sentence *is* the
specification, which is why plausible prose kept passing.

---

## 2. What the eight modes are today: five partial sources, no specification

| Source | What it holds | Authored / derived |
|---|---|---|
| [`vision.md`](vision.md) §6 (lines 279–286) | eight one-line prose descriptions | authored — **the root** |
| [`src/segfacet/synth/perturbation.py`](../../src/segfacet/synth/perturbation.py) `FAILURE_MODE_NAMES` | eight short names keyed 0–8 (0 = clean control), **worded differently from §6** | authored, duplicated |
| [`src/segfacet/feature_docs.py`](../../src/segfacet/feature_docs.py) `MODE_ANCHOR_PATHS` | one nominated "anchor" feature path per mode | authored; documented as deliberately **not** the path the rule reads |
| `src/segfacet/synth/*.py` `Expectation(failure_mode=N, expected_rule_ids=…)` | which synthetic operator produces the mode, which rules should fire | authored, operational |
| [`src/segfacet/traceability.py`](../../src/segfacet/traceability.py) `MODE_RUNGS` | evidence rung + mechanism prose per mode | authored (items 138 + `0db0fca`) |

None of these states what **distinguishes** one mode from its neighbours, what
evidence constitutes a detection, what severity a mode carries, or what a
positive and a negative example look like. There is no `docs/` document
specifying a failure mode anywhere in the repo.

`vision.md` §6 already says the catalogue is **open and grows in tandem** — "a
mode is added together with the rule(s) that detect it … never a mode alone,
never a rule that targets no mode". That principle is sound and should survive.
What is missing is the per-mode substance the principle is meant to govern.

---

## 3. Measured ground truth (2026-09-03)

Every column below is read from live state or measured by running each committed
corpus case through `run_qc`; none is taken from prose. Reproduce with the
sources named in the column notes.

| Mode | Rung | Anchor path | Anchor read by a declared rule? | Declared rules | Corpus designates | Measured firing |
|---|---|---|---|---|---|---|
| 1 | synthetic-demonstrable | `stage3.per_label_offsets[].offset_mm` | ✅ mislabel | mislabel, **reference_delta** | mislabel | `['mislabel']` |
| 2 | synthetic-demonstrable | `per_label.{label}.components.fragmentation_index` | ✅ fragmentation | **bounds**, fragmentation, **reference_delta** | fragmentation | `['fragmentation']` |
| 3 | synthetic-demonstrable | `per_label.{label}.components.stray_component_sizes[]` | ✅ fragmentation | fragmentation | fragmentation | `['fragmentation']` |
| 4 | synthetic-demonstrable | `stage3.monotonic_consistency.is_monotonic` | ❌ **none** | mislabel | mislabel | `['mislabel']` |
| 5 | synthetic-demonstrable | `relationships.present_levels[]` | ✅ coverage | coverage | coverage | `['coverage']` |
| 6 | synthetic-demonstrable | `per_label.{label}.geometry.touches_left` | ✅ border | border | border | **`['border', 'mislabel']`** |
| 7 | needs-real-data | `relationships.is_continuous` | ❌ **none** | sequence | sequence | `['sequence']` |
| 8 | structurally-unobservable | `overlaps[].overlap_voxels` | ✅ overlap | overlap | overlap | `[]` (reconstructed record only) |

**Column provenance.** *Anchor path* — `feature_docs.MODE_ANCHOR_PATHS`.
*Anchor read by a declared rule?* — derived: does any rule declaring this mode
consume that path per `catalogue.build_catalogue().consuming_rules`. *Declared
rules* — `RuleModeDeclaration.modes` (items 136/137). *Corpus designates* — the
`Expectation` literals. *Measured firing* — `synth.regression.pipeline_findings`
over each committed corpus case.

The last three columns are **three independent opinions about the same
relationship**. The generated matrix
([`traceability_matrix.generated.json`](traceability_matrix.generated.json), item
138) cross-checks them against each other — but since none of them is a
specification, their agreement does not establish correctness. Mode 6 is the
proof: all three sources agree on `border`, and the measurement shows `border`
**and** `mislabel`.

---

## 4. Three structural findings the measurement surfaced

**4.1 — Modes 4 and 7 are anchored on fields no rule reads.** `is_monotonic` and
`is_continuous` are summary booleans; `mislabel` reads
`stage3.monotonic_consistency.non_monotonic_pairs[]` and `sequence` reads the
sequence detail. `feature_docs.py` documents this as deliberate. The consequence
is that for these two modes the anchor cannot serve as evidence of detection —
and it is exactly why item 138's mode-4 sentence was false and passed its check.
**Decide:** re-anchor to the read field, or carry anchor and read-path as
separate, separately-labelled columns.

**4.2 — Mode 6's corpus case fires an undeclared rule.** Cropping L3's anterior
face shifts its centroid off the fitted spline, so `mislabel`'s Detector A fires
alongside `border`. Nothing in the matrix records this. It is either a legitimate
true positive (a crop *does* displace the label) or cross-talk — and that
judgement is precisely what item 140's specificity ratchet was to be built on.
**Decide:** true positive to be recorded, or defect to be fixed.

**4.3 — Modes 1 and 2 declare rules no corpus case demonstrates.** The analytic
edges — `reference_delta` on modes 1 and 2, `bounds` on mode 2 — were declared on
code reading, not on a demonstrated detection (see item 137 and its
`b1c593c` correction). They are real consumers of the relevant features, but no
corpus case shows them detecting that mode. **Decide:** whether an evidence rung
attaches to the mode (today) or to each mode↔rule edge, so an analytic-only claim
is visibly weaker than a demonstrated one.

---

## 5. What items 136–138 built, and why it survives

The machinery is sound and is **not** invalidated by this handover; it becomes
the conformance check once a specification exists.

- **Item 136** — `RuleModeDeclaration` in
  [`src/segfacet/heuristics/rule.py`](../../src/segfacet/heuristics/rule.py): a
  three-state seam (modes + evidence / mode-less reason / pending reason) with
  `declaration_for`, `iter_rule_declarations`, and
  `catalogue.rule_declaration_conflicts()`.
- **Item 137** — every registered rule dispositioned; no catalogue entry reports
  `("rule_unmapped",)`.
- **Item 138** — [`src/segfacet/traceability.py`](../../src/segfacet/traceability.py)
  generating the matrix in all three directions with per-mode evidence rungs, and
  a test module that now verifies path-consumption and measured-firing claims
  against live state (`b090822`).

What that machinery cannot do is decide *what a mode is*. It reports agreement
between sources; it cannot adjudicate them.

---

## 6. Proposed shape for a failure-mode specification

One authored source per mode, from which the generated matrix becomes a
**conformance report** rather than the primary record. Each entry carries:

| Field | Purpose |
|---|---|
| `id`, `name` | stable identity; replaces the two divergent name lists (§2) |
| `definition` | what the failure *is*, in clinical/geometric terms |
| `discriminator` | what separates it from its nearest neighbours — the field whose absence let modes 1/4 and 2/3 blur |
| `observability` | single-channel-observable · needs paired scan · structurally unobservable |
| `evidence_rung` | synthetic-demonstrable · needs-real-data · structurally-unobservable (per mode **and/or** per edge — see §4.3) |
| `candidate_features` | feature paths that could evidence it, **hypothesised**, not yet a consumption claim |
| `intended_rules` | rules meant to detect it, with the detector/branch named where a rule has several |
| `corpus_cases` | cases demonstrating it, with the expected *and* measured firing sets |
| `severity` | what a detection should mean for the verdict |
| `status` | lifecycle — see §7 |
| `provenance` | hypothesised from literature/experience vs discovered by clustering (Stage 24) |

`candidate_features` and `intended_rules` are the fields that let a mode be
recorded before it is built — the point being that pointing at a feature or rule
is a *design intent*, not an implementation claim, and the matrix must render the
two differently.

---

## 7. Lifecycle: how the catalogue grows without everything being built

A per-mode `status` is what allows a long list of modes with only some
implemented, and end-to-end delivery for a subset now:

- **`proposed`** — named and defined; no features, rules or corpus yet. Appears
  in the catalogue and the matrix, reported as unimplemented. **Does not** breach
  vision §6's "never a mode alone" rule, because that rule governs a mode being
  *claimed as covered*, not a mode being *listed as known*. §6's wording should
  be revisited to make that distinction explicit.
- **`specified`** — definition, discriminator, observability and candidate
  features settled; rules named but not written.
- **`implemented`** — ≥1 rule registered and declaring the mode.
- **`validated`** — a corpus case demonstrates detection end-to-end, and the
  specificity assertion holds for it.

The existing evidence rung is orthogonal to this and should stay: a mode can be
`validated` at rung `needs-real-data` (mode 7 is exactly that today).

---

## 8. Relationship to Stage 24

[`roadmap.md`](roadmap.md) Stage 24 ("Failure-mode discovery & typed reference
set") clusters the feature space to surface modes **not** in the §6 catalogue.
The eight modes here are the opposite: hypothesised in advance, with features and
rules nominated by hand. The `provenance` field in §6's schema keeps the two
distinguishable, so a discovered mode is never silently merged into a
hypothesised one, and a hypothesised mode that clustering fails to corroborate is
visibly still hypothesised.

---

## 9. What was cut from queue-019, and what each cut item assumed

Items 136, 137 and 138 are ✅ merged (plus the post-merge corrections `b1c593c`,
`0db0fca`, `b090822`). The remainder were **not** executed, because each rests on
a mode definition that does not exist:

- **Item 139 — per-rule and per-operator corpus-exercise reporting.** Its spec
  was authored and is preserved at
  [`items/139-per-rule-and-per-operator.md`](items/139-per-rule-and-per-operator.md);
  it is **not** superseded in substance and carries measurements worth keeping —
  in particular that the `fuse` operator genuinely generates no corpus case, that
  **7 of 10** rules are exercised across both corpora (not 5), and that
  `intensity_reference_delta` is driven by nothing because no harness attaches a
  reference. Its "unexercised, with reason" records are the part that needs a
  mode specification.
- **Item 140 — the specificity ratchet.** Cannot be adopted before §4.2 is
  decided: the ratchet's first real case is mode 6 firing `mislabel`.
- **Item 141 — widen the mode-1 severity-ladder base so mode 6 clears on its
  own.** Turns directly on mode-1-vs-mode-6 semantics, i.e. §4.1's discriminator
  field.
- **Item 142 — validate Stage 20.** The honest-count item; it would have to state
  a mode↔rule story that is not yet defined.

---

## 10. Decisions required from a human before re-planning

1. **§4.1** — re-anchor modes 4 and 7 to the fields their rules read, or keep the
   summary-boolean anchors and carry the read path as a separate column?
2. **§4.2** — is mode 6's `mislabel` firing a true positive to record, or
   cross-talk for the ratchet to forbid?
3. **§4.3** — does the evidence rung attach to the mode, to each mode↔rule edge,
   or both?
4. **§6/§7** — adopt the proposed per-mode schema and four-state lifecycle, or a
   different shape?
5. **Scope** — does the mode taxonomy become a new stage upstream of Stage 20, or
   a rescope of Stage 20 itself? A new stage preserves items 136–138's delivered
   machinery without rewriting a stage that has three merged items against it.
6. **§6 of `vision.md`** — the "never a mode alone" wording needs revisiting so a
   `proposed` mode is not a contract breach. That is a root-document edit and
   goes through the create-vision entry point behind a reviewed PR.

---

## 11. Related captured insights

Open entries in [`insights.md`](insights.md) bearing directly on this re-plan:

- the AC31 token-presence check passing four false mechanisms (item 138,
  2026-09-03) — the defect class this document is the response to;
- `RuleModeDeclaration.evidence` shipping a false factual claim past a length
  floor (item 137, 2026-09-02);
- item 136's mode attribution being **rule-granular**, so bookkeeping paths
  inherit a rule's full mode tuple (item 138, 2026-09-02) — a per-path or
  per-detector attribution is one of the things a mode specification would let
  the declaration seam express;
- the roadmap recording supersession only forward, so Stage 20 read top-down
  still yields the stale plan (queue-019, 2026-09-02).

---

## 12. Feedback-loop disposition (2026-09-03, engine 1.37.0)

`/aide-feedback-loop` consumed §1–§11 after PR #70 merged queue-019 into
`main`. This section records the scheduling answer, the re-reading of Stage
20's acceptance, a recommended answer for each §10 decision, and the order of
the root-document work. The §10 decisions stay the human's — gate 3 in
[`progress.md`](progress.md) is resolved only by `aide gate approve 3`; what
follows is the proposal a single approval can adopt or amend.

### 12.1 Scheduling: a new Stage 30, run before the remainder of Stage 20

Three shapes were weighed.

| Shape | Why not / why |
|---|---|
| **Add the specification items to Stage 20** | Stage 20 is an *audit* stage by its own scope fence ("not a rule-writing stage … records the finding and hands back"), and it is 🚧 with three merged items and two ticked criteria against it. A stage in progress is immutable in the roadmap, and authoring the thing being audited inside the stage that audits it is the shape that produced the defect class in §1: the same item writes the claim and the check. |
| **Move items 139–142 into the new stage and close Stage 20** | Items 136–138 built the conformance machinery (§5), and items 139–142 are more of the same — exercise reporting, the specificity ceiling, the honest count. They are the *harness*, and the harness is what Stage 20 is. Moving them empties Stage 20's acceptance of anything that could satisfy criteria 3–5 and rewrites a stage with merged work against it. |
| **New Stage 30, runs next; Stage 20 stays open and resumes after** *(recommended)* | Same construction as Stages 26, 28 and 29: numbered for stability, run before Stage 20 because it changes what Stage 20 audits. Stage 30 authors the specification; Stage 20 then measures conformance to it. Items 136–138 stay delivered, criteria 1–2 stay attested, items 139–142 are re-specced against the specification and re-queued. |

**Stage 30 — Failure-Mode Specification (the §6 catalogue as an authored
source).** Proposed scope, for the create-roadmap entry point to refine:

- One authored source per mode with the §6 schema (`id`, `name`,
  `definition`, `discriminator`, `observability`, `evidence_rung`,
  `candidate_features`, `intended_rules`, `corpus_cases` with expected firing
  sets, `severity`, `status`, `provenance`), and the §7 lifecycle
  (`proposed` → `specified` → `implemented` → `validated`). A Python module of
  frozen declarations in the shape of `RuleModeDeclaration`, with a generated
  human-readable rendering as the review surface, keeps it in the repo's
  existing idiom and importable by the conformance generator.
- The five partial sources in §2 collapsed onto it: `FAILURE_MODE_NAMES` and
  `MODE_RUNGS` retired or derived from the specification; `MODE_ANCHOR_PATHS`
  kept only as what it actually is — the Stage-18 per-mode *metric*'s read
  path (`feature_docs.py:350`), rendered under that label beside the rule's
  read path (§12.3, decision 1). `Expectation` and `RuleModeDeclaration`
  stay as the two operational claims the specification is checked against.
- Item 138's matrix re-pointed at the specification as its primary record,
  so it becomes the conformance report §6 describes: a mode whose expected
  firing set differs from the measured one fails, which is the check that no
  shape test in §1 could express.
- The tissue-plausibility mode that `insights.md` entry 51 records as missing
  (the `intensity` / `intensity_reference_delta` rules and the four-case
  intensity corpus already exist for it) added as the first mode to enter
  through the lifecycle — it arrives at `implemented`, or `validated` once
  its corpus cases carry expected firing sets, and demonstrates that the
  lifecycle admits a mode the eight-mode list did not.
- A **human sign-off of the specification** as the stage's checkpoint, in the
  sense Stages 19 and 27 use: the definitions and discriminators are the
  ground truth every later check consults, so they are read by a person
  before anything is measured against them.

**Queues.** Stage 30 is one queue (about five items, under the cap of 10).
The remainder of Stage 20 — items 139, 140, 141, 142, re-specced — is the
queue after it, not the same one: running the harness against a
specification nobody has signed off repeats §1 one level up. Item 139 is the
least specification-dependent of the four (its "unexercised, with reason"
records are measured facts about harness inputs, not about modes) and can
open that queue. Whether item 141 belongs in Stage 20 at all is decided at
that queue's planning: it is a Stage 18 metric-surface fix, and it stays only
if the mode-1 / mode-6 discriminator makes "mode 6 clears on its own" a
meaningful claim.

**Run order from here: 30 → 20 (remainder) → 27 → 21 → 16.** Stage 24
(discovery) is unaffected; the `provenance` field is what keeps a discovered
mode distinguishable from a hypothesised one (§8).

### 12.2 Stage 20's acceptance, re-read

None of the five criteria is rewritten. Criteria 1 and 2 are attested and
immutable; criteria 3–5 carry retraction trails, and the engine's guard
refuses `progress reword` on a trail-bearing box. What changes is the
*reading*, recorded in the roadmap's Stage 20 section as a backward
supersession marker (the edit `insights.md` entry 46 already asks for) and in
Stage 30's own acceptance:

| # | Criterion | Reading after Stage 30 |
|---|---|---|
| 1 | every §6 mode has ≥1 rule and a recorded evidence rung | Holds as attested on the eight modes. Under the lifecycle it is scoped to modes at `implemented` or above; a `proposed` mode has no rule by definition and is not silent, because the specification says so. The rung moves to the mode↔rule edge (decision 3) and the mode's rung is derived from its edges. |
| 2 | every registered rule maps to ≥1 mode or is recorded mode-less with a reason | Holds as attested. Unchanged in substance. |
| 3 | every registered rule is exercised by ≥1 case or recorded unexercised with a reason | Unchanged. Item 139's spec stands; "reason" means a harness-input mechanism or a specification-recorded absence. |
| 4 | the specificity assertion is enforced for every corpus case | Unchanged wording; "unintended" is now defined by the specification's per-case expected firing set, not by the assertion's own allowlist. Item 140's adjudication of mode 6 becomes a specification entry (decision 2), and the allowlist is derived from the specification rather than authored beside it. |
| 5 | the end-to-end detection count is stated honestly | Unchanged. The count is stated per lifecycle status and per rung (n `validated` at `synthetic-demonstrable`, m at `needs-real-data`, …), never as one number over a list that mixes hypothesised and demonstrated modes. |

### 12.3 Recommended answers to the six §10 decisions

1. **§4.1, modes 4 and 7 anchors** — carry both, separately labelled.
   `MODE_ANCHOR_PATHS` is documented as the *Stage-18 metric's* read path,
   not the rule's, so "re-anchor to the read field" would erase a real
   distinction. The specification's `candidate_features` names the metric
   path; the rule's read paths derive from `RuleModeDeclaration` and the
   catalogue's `consuming_rules`; the matrix renders "metric path" and "rule
   reads" as two columns. Item 138's mode-4 sentence was false because prose
   had one column; two columns leave nothing to transcribe.
2. **§4.2, mode 6 firing `mislabel`** — a true co-detection, recorded, not
   suppressed. Cropping L3's anterior face moves the label's centroid by a
   measured 17.5 mm (`heuristics/mislabel.py:81`), which is a real
   displacement of the label relative to the curve. The specification
   records `expected_firing = {border, mislabel}` for `mode6_crop_at_border`
   with that reason, and the *discriminator* between modes 1 and 6 is written
   down at the same time: mode 6 has a border-touching face, mode 1 has none.
   Whether a later rule should let mode 6 explain away the mode-1 reading is a
   rule change, out of scope for both stages, and is recorded as such.
3. **§4.3, where the rung attaches** — to the mode↔rule edge, authored; the
   mode's rung is derived as the strongest of its edges. That makes the
   analytic-only edges of §4.3 (`reference_delta` on modes 1 and 2, `bounds`
   on mode 2) visibly weaker than the demonstrated ones without inventing a
   fourth rung.
4. **§6/§7, schema and lifecycle** — adopt as proposed, with two additions:
   `corpus_cases` carries `expected_firing` per case (the measured set is
   never authored, only compared), and `status` is derived where it can be —
   `implemented` from a registered rule declaring the mode, `validated` from a
   corpus case whose measured firing equals its expected firing — so only
   `proposed` and `specified` are ever set by hand.
5. **Scope** — new Stage 30, run before the remainder of Stage 20 (§12.1).
6. **`vision.md` §6 wording** — yes, and as part of a re-issued vision rather
   than a point edit (§12.4). The growth contract survives as "a mode is
   *claimed covered* only with the rule(s) that detect it"; listing a mode as
   `proposed` is not a claim of coverage.

### 12.4 The re-vision: now, scoped, not the full one

[`vision.md`](vision.md) §0 defers the full re-vision until real segmenter
failures have been measured. That condition is Stage 16, which sits behind
gates 1 and 2 with no date, so the deferral has no horizon. Meanwhile the
document's body still describes an XNAT QC gate, its §6 must change now for
decision 6, and every queue since 2026-07-25 has been derived from a
superseded body read through an override header. Re-issuing the vision now is
the smaller cost: §6 is the root of the defect class in §1, and editing it
inside a provenance trail is worse than editing it in a document that is
current.

What the re-issue does and does not do:

- **Does:** rewrite §1–§12 to describe FACET (the failure-analysis toolkit
  §0 already defines), keep the G-numbers and their retyped targets, restate
  §6 as the *principles* of the catalogue — the growth contract, the lifecycle,
  the evidence rungs, the observability classes — and point at the authored
  specification Stage 30 owns for the catalogue itself, so the vision never
  again carries a per-mode list that drifts from code.
- **Does not:** specify Stages 22–25. Their content still depends on
  measurements that do not exist; they stay placeholders, and the deferral
  narrows from "the whole document" to "those four stages".

Order of work, each in a fresh session per the entry points' own hand-offs:

1. Approve or amend gate 3 (`aide gate approve 3 --evidence "…"`), citing
   this section or the decisions that differ from it.
2. `/aide-create-vision` — interactive; produces vision v3 as a draft.
3. `/aide-create-roadmap` — incremental update: Stage 30 added; Stage 20's
   section gains the backward supersession markers (`insights.md` 46) and
   the §12.2 reading; a "run order" statement placed once, at the top, so
   the roadmap reads top-down again.
4. `/aide-create-progress` — Stage 30 section and summary row.
5. Both root documents in one reviewed PR, then `/aide-create-queue` for
   queue-020 (Stage 30).

### 12.5 Process findings outside the taxonomy

Two systemic points, for the next framework hand-over rather than this
repo:

- **A stage criterion was ticked by position.** Item 137's validator mapped
  its item ACs onto Stage 20's criteria by index and ticked four boxes the
  item had not established (`insights.md` entries 52–55). `aide progress
  accept --criterion N` is positional by design; the fix is that an item
  ticks a stage criterion only when its spec names that criterion explicitly,
  which is a spec-template and validator-prose change in `aide-loop`.
- **An acceptance criterion that asserts a fact about code must be a measured
  equality against live state, never a shape check** — a length floor
  (item 137), a token-presence check (item 138) and a declaration-state
  completeness flag (item 138) each passed a false claim. `REVIEW.md` names
  the class; the spec-author and test-writer prose do not yet forbid it at
  authoring time.
