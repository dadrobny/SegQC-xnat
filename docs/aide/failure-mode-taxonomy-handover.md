# Handover: the §6 failure-mode catalogue needs a specification

> **Status:** 📋 Open — input to a feedback-loop re-plan · **Created:** 2026-09-03
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
