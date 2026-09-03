# Item 145 — The eight hypothesised modes, specified with discriminators and per-edge rungs

> **Created:** 2026-09-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 145
> **Objectives:** G2 (detect catalogued failure modes — the specification half), G7 (measured on the corrected corpus), G8 (extensible / the add-a-mode path)
> **Suggested branch:** `aide/145-the-eight-hypothesised-modes-specified`

---

## Description

Enter **every one of [`vision.md`](../vision.md) §6's eight hypothesised modes**
into item 144's specification module (`src/segfacet/failure_modes.py`) with every
schema field populated. Item 144 shipped the schema, the vocabularies, the live
derivations (`derive_status`, `derive_mode_rung`, `measured_firing`,
`case_agrees`, `specification_conflicts`) and the rendering, seeded with **two**
entries (modes 3 and 8) chosen to exercise both detection paths. This item is
**pure authoring through that schema**: six new entries, two re-authored ones,
and the regenerated artifacts. It builds no mechanism.

What it authors, and what makes each authored claim checkable:

- **Discriminators that name nearest neighbours.** Mode 6 has a border-touching
  face and mode 1 has none; modes 2 and 3 differ in whether the dominant body is
  intact; modes 1 and 4 differ in whether the label's *identity* or its
  *position* is wrong. Each of those three claims is a **fact about the committed
  corpus**, so each is pinned by a live measurement (AC16–AC18) rather than by a
  token in a sentence — the check queue-019's three defects could not express.
- **Per-edge evidence rungs** (gate 3, decision 3). Every mode ↔ rule edge
  carries a rung; the mode's rung is **derived** as its strongest edge by item
  144's `derive_mode_rung`. The analytic-only edges — `reference_delta` on modes
  1 and 2, `bounds` on mode 2 — sit at `needs-real-data` and are pinned as
  analytic by the fact that their `rule_id` appears in **no** corpus case's
  measured firing set (AC9).
- **`expected_firing` measured on the item-143-corrected corpus**, per corpus
  case, through `measured_firing()` — never transcribed from a queue-019
  document, and never from a pre-correction number.
- **Gate 3's decisions as data.** `mode6_crop_at_border` carries
  `expected_firing = ("border", "mislabel")` with its recorded reason and a
  **freshly measured** centroid displacement (AC14, AC15). `mislabel` is
  deliberately **not** one of mode 6's `intended_rules`: the co-detection is
  recorded in the case's expected set, and the edge set stays exactly what the
  live registry declares (AC5).
- **Mode 8** stays `structurally-unobservable`, its reason naming the
  single-channel mechanism — a voxel in an integer label map holds exactly one
  label, so `overlaps[]` populates only on a record deliberately corrupted to
  violate that invariant. The claim is pinned live: the committed fixture
  through the plain pipeline fires no `overlap` finding, while the reconstructed
  record fires exactly `("overlap",)` (AC11).
- **Mode 7** stays `needs-real-data`, its reason recording the single-rank-descent
  cap (`rank(v) == v - 1` under the TPTBox default, so §6.7's own
  `L1 → T12 → L2 → L5` two-descent example is not representable at rung 1) —
  even though its corpus case *is* pipeline-detected. That divergence is the one
  place where "the rule is driven end-to-end by a fixture" and "the mode is
  expressible in hand-crafted geometry" disagree, and it is authored visibly
  rather than hidden (AC10a, AC10b, and **D2** in Decisions & Trade-offs).

**What this item is NOT.** It writes **no rule** and changes **no threshold** —
nothing under `src/segfacet/heuristics/` is written. It adds **no corpus case**
and changes no committed corpus value: `tests/corpus/` is read. It does not edit
[`vision.md`](../vision.md) or [`roadmap.md`](../roadmap.md) (queue-020's scope
fence): a finding that §6's principles are wrong is one line in `insights.md` and
a hand-back. It does not build the ninth mode or the first `proposed` entry (item
146), does not collapse `FAILURE_MODE_NAMES` / `MODE_RUNGS` / the `vision.md`
parse onto the specification (item 147), does not touch the catalogue's
attribution granularity (item 148), and does not re-point `build_matrix` (item
149). The **one** mechanism change it may make is the minimal `derive_status`
correction described in **A1** — and only if the concurrent review of item 144
has not already landed it.

**Stage acceptance.** This item annotates **no** *(closes Stage 30 criterion N)*
on any AC, so by `.aide/conventions.md` §1 → `items.md` it closes none. Stage 30
criteria 1–3 are established across many of the ACs below **plus** item 146's
ninth mode and both corpora; item 151 attests them, naming the checks.

## Acceptance Criteria

- [ ] **AC1: all eight §6 modes are present.**
  `tuple(mode.id for mode in segfacet.failure_modes.iter_modes())` equals
  `(1, 2, 3, 4, 5, 6, 7, 8)`.

- [ ] **AC2: every schema field is populated for every one of the eight.** For
  each mode, no `dataclasses.fields(mode)` value is `""`, `()` or `None`, and
  `candidate_features`, `intended_rules` and `corpus_cases` are each non-empty.

- [ ] **AC3: the eight names equal `vision.md` §6's list, derived from the
  document.** For each mode, `mode.name` equals the title parsed live from
  `docs/aide/vision.md` §6's numbered list at that mode's index (trailing period
  stripped, whitespace collapsed) — recomputed from the document at test time,
  never compared against a hand-written list in the test.

- [ ] **AC4: the Stage-18 metric anchor path is carried, and only as that.** For
  each mode, the set of `path` values of its `candidate_features` whose `role`
  is `"stage18-metric-anchor"` equals `set(feature_docs.MODE_ANCHOR_PATHS[mode.id])`,
  read live. (Additional `role="hypothesised"` entries are permitted; a rule's
  measured read path is **not** authored here — it is derived, and is items
  148/149's separately-labelled column.)

- [ ] **AC5: the edge set equals what the live registry declares.** For each
  mode, `{edge.rule_id for edge in mode.intended_rules}` equals
  `{rule_id for rule_id, declaration in iter_rule_declarations() if declaration
  is not None and mode.id in declaration.modes}`, recomputed from the registry.
  In particular mode 6's edge set is `{"border"}` — `mislabel` is a recorded
  co-detection, not a declared edge.

- [ ] **AC6: every mode's rung is the strongest of its own edges.** For each
  mode, `derive_mode_rung(mode)` equals the `EVIDENCE_RUNGS` member with the
  smallest index among `{edge.evidence_rung for edge in mode.intended_rules}`,
  recomputed from the entry's own edges rather than compared to a transcribed
  literal.

- [ ] **AC7: a deliberately weakened edge rung changes the derived mode rung.**
  For a mode whose derived rung comes from a single strongest edge, a copy of
  that mode (via `dataclasses.replace`, in the test only) whose strongest edge is
  re-authored one rung weaker derives the weaker rung — proving the derivation is
  live and not a stored field.

- [ ] **AC8: every `synthetic-demonstrable` edge is actually demonstrated.** For
  every edge authored `"synthetic-demonstrable"`, that edge's `rule_id` appears in
  `measured_firing(case)` for at least one of the mode's corpus cases whose
  manifest `detection` is `"pipeline"`.

- [ ] **AC9: the three analytic-only edges are authored `needs-real-data` and
  demonstrated by nothing.** The edges `reference_delta` on mode 1,
  `reference_delta` on mode 2 and `bounds` on mode 2 each carry
  `evidence_rung == "needs-real-data"`, and none of those `rule_id`s appears in
  `measured_firing(case)` for any corpus case of the mode that carries the edge.

- [ ] **AC10a: mode 7's rung is `needs-real-data` while its case measurably
  fires.** Mode 7's sole edge (`sequence`) carries
  `evidence_rung == "needs-real-data"`, `derive_mode_rung(mode 7)` is
  `"needs-real-data"`, and `measured_firing` for `mode7_sequence_break` contains
  `"sequence"` — the divergence is asserted, not hidden.

- [ ] **AC10b: mode 7 records the single-rank-descent cap.** Mode 7's corpus
  case reason states the `rank(v) == v - 1` cap under the TPTBox default and
  names §6.7's `L1 → T12 → L2 → L5` example as the two-descent input it makes
  unrepresentable at rung 1.

- [ ] **AC11: mode 8's structural unobservability holds live.**
  `derive_mode_rung(mode 8)` is `"structurally-unobservable"`; the committed
  `mode8_force_overlap` fixture driven through the plain pipeline
  (`synth.regression.pipeline_findings`) yields no finding with
  `rule_id == "overlap"`, while `synth.regression.reconstructed_findings` on the
  same case yields exactly `("overlap",)`; and the case's manifest `detection` is
  `"reconstructed_record"`.

- [ ] **AC12: mode 8 records the single-channel mechanism.** Mode 8's corpus case
  reason states that a voxel in a single-channel integer label map holds exactly
  one label, so `overlaps[]` populates only on a record deliberately corrupted to
  violate that invariant.

- [ ] **AC13: every expected firing set equals a fresh measurement.** For every
  one of the eight modes and every corpus case it carries,
  `set(case.expected_firing) == set(measured_firing(case))` (i.e. `case_agrees`
  is `True`), and `derive_status(mode)` is `"validated"` for all eight.

- [ ] **AC14: `mode6_crop_at_border` expects `{border, mislabel}` with a
  reason.** That case's `expected_firing` is exactly `("border", "mislabel")`,
  its `reason` is non-empty and states that cropping the vertebra at the image
  border displaces its centroid off the fitted spinal curve, and `"mislabel"` is
  absent from mode 6's `intended_rules` rule ids.

- [ ] **AC15: mode 6's displacement is a fresh measurement, not a transcription.**
  The numeric millimetre value recorded in `mode6_crop_at_border`'s `reason`
  (recorded to at least one decimal place, in the form `<value> mm`) equals,
  within 0.05 mm, the `offset_mm` measured live from the committed fixture's
  feature record — the non-terminal `stage3.per_label_offsets[]` entry for the
  label the case's `border` finding names.

- [ ] **AC16: the mode-1 / mode-6 discriminator holds on the corpus.** On
  `mode6_crop_at_border`'s committed fixture at least one label's
  `per_label.{label}.geometry.touches_*` face flag is true; on `mode1_displace`'s
  committed fixture no label's is.

- [ ] **AC17: the mode-2 / mode-3 discriminator holds on the corpus.** On
  `mode3_inject_islands`, the perturbed label's largest connected component holds
  at least 0.9 of that label's voxels (the dominant body is intact); on
  `mode2_fragment` it holds no more than 0.6 (it is not).

- [ ] **AC18: the mode-1 / mode-4 discriminator holds on the corpus.** The
  `mislabel` finding measured on `mode1_displace` and the one measured on
  `mode4_relabel_swap` carry **different** leading reason tags — the misalignment
  (position) tag and the ordering (identity) tag respectively — so the two modes
  are separated by which detector fires, not by prose.

- [ ] **AC19: every discriminator names at least one sibling mode.** Each of the
  eight `discriminator` strings references at least one other mode present in the
  specification, by id; mode 1's names mode 4, mode 2's names mode 3, mode 3's
  names mode 2, mode 4's names mode 1 and mode 6's names mode 1.

- [ ] **AC20: `detector` names the detector that actually fired.** For every edge
  whose `rule_id` appears in `measured_firing(case)` for one of the mode's corpus
  cases, `edge.detector` is non-empty and at least one measured finding on that
  case with that `rule_id` has `reason.startswith(edge.detector)`. Every edge
  whose `rule_id` appears in no corpus case's measured firing carries
  `detector == ""`.

- [ ] **AC21: `severity` is grounded in what the mode's case measurably
  produces.** For each mode, `mode.severity` equals the `severity` label of at
  least one measured finding on one of its corpus cases whose `rule_id` is one of
  the mode's `intended_rules`.

- [ ] **AC22: `implemented` derives on "a registered rule whose `modes`
  contains the id".** For each of the eight modes, `derive_status` applied to a
  copy of that mode with `corpus_cases=()` returns `"implemented"`, because at
  least one registered rule's `RuleModeDeclaration.modes` contains the mode id
  (recomputed from the live registry — under the exact-singleton reading item
  144 shipped, modes 1, 2, 3 and 4 would return `"specified"`; see **A1**).

- [ ] **AC23: both generated artifacts carry the eight modes and are
  byte-reproducible.** `python -m segfacet.failure_modes` writing to a temporary
  directory produces byte-identical output on two consecutive runs in one
  session, both files match their committed copies byte for byte, and each
  contains all eight mode ids.

- [ ] **AC24: `aide check` stays at seven warnings.** `python
  .aide/scripts/aide.py check` exits OK reporting **7** warnings — the same seven
  present at this item's base — with no new `.gitattributes`, unfilled-slot or
  missing-Assumptions warning introduced by this item.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (`aide.toml`), so each ambiguity below is resolved to
the most defensible default and recorded here for audit at the queue boundary.

- **A1 (engine 1.37.0): `derive_status` must derive `implemented` on "a
  registered rule whose `modes` *contains* the id", and item 144 shipped a
  narrower reading.** [`vision.md`](../vision.md) §6 and
  [`../queue/queue-020.md`](../queue/queue-020.md) both define `implemented` as
  "at least one registered rule declares the mode". Item 144's
  `_registry_declares_exactly` (`src/segfacet/failure_modes.py`, the
  `derive_status` helper) instead requires
  `RuleModeDeclaration.modes == (mode_id,)` — an **exact singleton** — a
  narrowing its own Decisions log records as forced by a committed AC9 test
  rather than chosen. Under it, modes 1, 2, 3 and 4 are not `implemented` by any
  rule (`mislabel` declares `(1, 4)`, `fragmentation` `(2, 3)`,
  `reference_delta` `(1, 2)`), so AC22 cannot hold. **A code review of item 144
  is running concurrently on the branch `review/144-findings` and may land this
  fix into `aide/queue-020` before this item merges.** The builder therefore:
  (i) checks whether the corrected derivation is already present on the item
  branch after `aide sync` / the queue-branch merge, and if so touches nothing;
  (ii) only if it has not landed, makes the **minimal** change — the containment
  test in place of the equality test — and nothing else in that function.
  Either way the observable contract this item pins is AC22's, not a particular
  diff.
- **A2 (engine 1.37.0): item 144's committed AC9 test must be reconciled with
  A1, in the same edit.**
  `tests/test_144_failure_mode_specification.py::test_ac9_derive_status_implemented_iff_a_registered_rule_declares_the_mode`
  builds a **mode-3** probe with `corpus_cases=()` and asserts `"specified"`
  *before* a throwaway `modes=(3,)` rule is registered — which the real,
  already-merged `heuristics/fragmentation.py` (`modes=(2, 3)`) makes false under
  the containment reading. The reconciliation is to build the probe on a mode id
  **no registered rule declares** (with a `role="hypothesised"` candidate feature,
  since `MODE_ANCHOR_PATHS` has no entry for such an id), keeping the test's
  three-step register / observe / unregister sequence intact. This is a test
  correction, not a weakening: the sequence still proves the derivation is live.
- **A3: the corpus firing sets and the mode-6 displacement are measured by the
  builder, and nothing pre-item-143 is carried forward.** Item 143's review
  established that every corpus case now advances caudally and that signed
  per-axis quantities flipped sign, while the per-case firing sets themselves did
  not move (`progress.md`, item 143 validator round 3, via
  `tests/test_098_stray_components.py::_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`).
  That is a **cross-check**, not a source: every `expected_firing` tuple authored
  here comes from a `measured_firing()` run recorded in Decisions & Trade-offs,
  and a divergence from the cross-check is a finding for `insights.md` and a
  hand-back, never a value forced to agree. The pre-correction **17.5 mm**
  displacement carried in `heuristics/mislabel.py`'s docstring and in item 138's
  matrix prose is explicitly **not** transcribed; AC15 pins a fresh measurement.
  If the fresh measurement differs from that docstring's `17.507445` mm, the
  docstring is stale — record it in `insights.md` and hand back the observation;
  `src/segfacet/heuristics/` is not writable by this item.
- **A4: the rung is a claim about the mode's expressibility, not merely about
  whether some fixture drives the rule — and mode 7 is where the two readings
  diverge.** [`vision.md`](../vision.md) §6 names mode 7's two-descent
  `L1 → T12 → L2 → L5` example as *the* `needs-real-data` exemplar, and
  `traceability.py::MODE_RUNGS[7]` records the mechanism: `rank(v) == v - 1`
  under the TPTBox default admits a single rank descent, so the committed
  `mode7_sequence_break` fixture is a *degraded, single-descent* instance that
  the pipeline does detect. Mode 7's edge is therefore authored `needs-real-data`
  even though AC8's universal ("`synthetic-demonstrable` ⇒ demonstrated") would
  have permitted the stronger rung. AC8 is one-directional for exactly this
  reason; AC10a asserts the divergence explicitly so it is visible in the review
  surface item 150 signs.
- **A5: an edge's rung rationale is carried in the mode's corpus-case `reason`,
  because item 144's `IntendedRule` has no free-text field.** `IntendedRule` is
  `(rule_id, detector, evidence_rung)`. Mode 7's cap sentence (AC10b) and mode
  8's single-channel mechanism (AC12) are therefore authored in the reason of the
  corpus case each mode carries, alongside the observability statement in the
  mode's `discriminator`. Extending the schema with a per-edge rationale field is
  **not** done here — it is a change to item 144's deliverable, and if the
  maintainer's review (item 150) wants one it is that item's finding.
- **A6: `detector` is authored as the rule's stable leading reason tag.** Vision
  §6 asks for "`intended_rules`, naming the detector where a rule has several",
  and the codebase has no detector registry — the only machine-checkable detector
  identity a rule exposes is the constant prefix of the `reason` it emits
  (`"Rogue island(s):"`, `"Vertebra misaligned from spinal curve:"`,
  `"Vertebra ordering inconsistent with label:"`, `"Fragmentation:"`,
  `"Partial vertebra clipped by FOV:"`, `"Missing interior level(s):"`,
  `"Non-continuous label sequence:"`, `"Overlapping segments:"`). Authoring the
  tag makes AC20 a measured equality against the finding the case actually
  produces rather than a token-presence check; the tags are already pinned by
  `tests/test_098_stray_components.py`, so this adds no new fragility. Edges that
  fire on no case (the analytic ones) carry `detector == ""`, which item 144's
  schema permits.
- **A7: `severity` is authored as what the mode's own demonstrating case
  measurably produces today** — `flagged-for-review` throughout, since every
  registered rule emits `Severity.FLAG`. §6 defines `severity` as *what a
  detection should mean for the verdict*, which is a judgement; absent a
  maintainer call the defensible default is the grounded value rather than an
  invented one, and AC21 pins it to live measurement. Item 150's entry-by-entry
  sign-off is the place to call a different severity for a mode; if the
  maintainer does, AC21's test is the named reconciliation point, and any change
  to what a rule *emits* is a rule change outside both this item and this stage.
- **A8: modes 4 and 7 keep an anchor path no rule reads, deliberately.** Gate 3,
  decision 1 (`../failure-mode-taxonomy-handover.md` §12.3) settled that
  `MODE_ANCHOR_PATHS` stays as the **Stage-18 per-mode metric's** read path, with
  the rule's read path a separate, separately-labelled column that items 148/149
  *derive*. So mode 4's `stage3.monotonic_consistency.is_monotonic` and mode 7's
  `relationships.is_continuous` are authored as `stage18-metric-anchor` candidate
  features here even though `mislabel`'s Detector B reads
  `non_monotonic_pairs[]` and `sequence` reads the sequence detail. This item
  does **not** re-anchor them and does **not** author a rule read path under any
  role.
- **A9: `expected_firing` tuples are authored in ascending order.**
  `case_agrees` compares sets, so order is semantically free, but
  `measured_firing` returns a sorted tuple and the rendering prints the tuple in
  order — authoring ascending keeps the review surface and the JSON stable.

## Implementation Steps

The code path is `src/segfacet/failure_modes.py` (`aide.toml` →
`project.source_dir = src/segfacet`). Nothing else in `source_dir` is written.

1. **Land and sync.** `python .aide/scripts/aide.py sync --item 145`. Confirm
   item 144's module is present and that
   `docs/aide/failure_modes.generated.{md,json}` carry the two seed entries.
2. **Check for the review fix (A1).** Look at `derive_status` /
   `_registry_declares_exactly` on the branch as it now stands. If the
   containment reading has already landed (via `review/144-findings` merged into
   `aide/queue-020`), leave it alone. If not, change the exact-singleton test to
   a containment test — that one expression, nothing else — and reconcile item
   144's committed AC9 test per **A2**.
3. **Measure, before authoring anything.** With `.venv/bin/python`, drive every
   geometric corpus case through `segfacet.failure_modes.measured_firing`
   (which dispatches on the manifest's `detection` field) and record, in
   Decisions & Trade-offs, the measured `rule_id` set per case, the leading
   `reason` tag per finding, the `severity` label per finding, and — for
   `mode6_crop_at_border` — the `offset_mm` of the non-terminal
   `stage3.per_label_offsets[]` entry for the label its `border` finding names.
   Compare each firing set against the item-143 cross-check in **A3**; a
   divergence is a finding, not a value to force.
4. **Author the six new entries and re-author the two seeds** as module-level
   `ModeSpec` constants in ascending id order, each with: the `name` copied from
   `vision.md` §6 (trailing period stripped); a `definition` in
   clinical/geometric terms; a `discriminator` naming its nearest neighbours by
   id (AC19, and the three pairs AC16–AC18 pin); the `stage18-metric-anchor`
   candidate feature(s) from `MODE_ANCHOR_PATHS` (A8); the edges the live
   registry declares, each with its rung and its detector tag (A6); the mode's
   corpus case with the **measured** `expected_firing` (ascending, A9) and a
   reason that carries the case's mechanism — plus, for mode 7, the cap sentence
   (AC10b) and, for mode 8, the single-channel invariant (AC12); the measured
   `severity` (A7); `status="specified"`; `provenance="hypothesised"`. The
   structural facts each entry must match, all read from live state:

   | Mode | Anchor path (`MODE_ANCHOR_PATHS`) | Edges (`rule_id` → rung) | Corpus case | `detection` |
   |---|---|---|---|---|
   | 1 | `stage3.per_label_offsets[].offset_mm` | `mislabel` → synthetic-demonstrable; `reference_delta` → needs-real-data | `mode1_displace` | pipeline |
   | 2 | `per_label.{label}.components.fragmentation_index` | `fragmentation` → synthetic-demonstrable; `bounds` → needs-real-data; `reference_delta` → needs-real-data | `mode2_fragment` | pipeline |
   | 3 | `per_label.{label}.components.stray_component_sizes[]` | `fragmentation` → synthetic-demonstrable | `mode3_inject_islands` | pipeline |
   | 4 | `stage3.monotonic_consistency.is_monotonic` | `mislabel` → synthetic-demonstrable | `mode4_relabel_swap` | pipeline |
   | 5 | `relationships.present_levels[]` | `coverage` → synthetic-demonstrable | `mode5_remove_level` | pipeline |
   | 6 | `per_label.{label}.geometry.touches_left` | `border` → synthetic-demonstrable | `mode6_crop_at_border` | pipeline |
   | 7 | `relationships.is_continuous` | `sequence` → needs-real-data | `mode7_sequence_break` | pipeline |
   | 8 | `overlaps[].overlap_voxels` | `overlap` → structurally-unobservable | `mode8_force_overlap` | reconstructed_record |

   The edge column is what the registry declares **today**; AC5 recomputes it, so
   the table is a starting point to be verified, not a literal to trust. Mode 1's
   and mode 4's `mislabel` edges carry **different** detector tags (position vs
   identity); mode 2's and mode 3's `fragmentation` edges likewise.
5. **Extend `SPECIFICATION`** to the eight entries, keeping its
   `MappingProxyType`, ascending-by-id construction and `iter_modes()` contract
   exactly as item 144 shipped them. Update the module docstring's "ships a
   minimal seed set of two entries" paragraph to say the eight §6 modes are now
   entered and that the ninth mode and the first `proposed` entry remain item
   146's. Leave the "Sign-off" paragraph for item 150.
6. **Regenerate both artifacts**: `.venv/bin/python -m segfacet.failure_modes`
   (zero-argument; it writes the two committed paths via `write_bytes`). Both
   paths are already pinned `text eol=lf` in `.gitattributes` by item 144, so no
   new pin is needed and `aide check`'s lint has nothing new to say.
7. **Reconcile item 144's stale pins** (see Testing Strategy): the seed-set
   assertion `ids == (3, 8)` and the two `@pytest.mark.parametrize("mode_id",
   [3, 8])` lists, plus the AC9 probe from **A2**.
8. **Verify scope**: `python .aide/scripts/aide.py scope` shows no write outside
   the Authorised paths below — in particular nothing under
   `src/segfacet/heuristics/`, nothing under `tests/corpus/`, and neither root
   document.

## Authorised paths

**May change:**

- `src/segfacet/failure_modes.py` — the eight `ModeSpec` entries, the
  `SPECIFICATION` mapping, the docstring paragraph naming what is now entered,
  and (only under **A1**, if the review fix has not landed) the minimal
  containment correction inside `derive_status`'s registry helper.
- `docs/aide/failure_modes.generated.json` — regenerated conformance artifact.
- `docs/aide/failure_modes.generated.md` — regenerated review surface (item
  150's).
- `tests/test_145_eight_hypothesised_modes.py` — this item's tests.
- `tests/test_144_failure_mode_specification.py` — the three pins item 144 wrote
  against a two-entry seed and a singleton derivation (A2, and Testing Strategy
  "existing tests to reconcile"); no other assertion in that module is touched.

**Asserts against:**

- `docs/aide/vision.md` — AC3 parses §6's numbered list live and compares the
  eight names against it; read-only, and changed only through its own loop entry
  point (queue-020 scope fence).
- `src/segfacet/feature_docs.py` — AC4 reads `MODE_ANCHOR_PATHS` live.
- `src/segfacet/heuristics/*.py` — AC5 reads the live registry and every
  `RuleModeDeclaration`; AC18/AC20 pin the leading `reason` tags the rules emit.
  Nothing under `src/segfacet/heuristics/` is written by this item.
- `src/segfacet/verdict.py` — AC21's severity labels come from `Severity`.
- `src/segfacet/pipeline.py` — AC15/AC16/AC17 recompute feature records from the
  committed fixtures.
- `src/segfacet/synth/regression.py` — AC8/AC11/AC13 drive cases through
  `pipeline_findings` / `reconstructed_findings`.
- `src/segfacet/synth/corpus.py` — `measured_firing` resolves each case through
  `load_manifest`.
- `src/segfacet/traceability.py` — AC3 may reuse that module's existing
  `vision.md` §6 title parse rather than writing a second parser; item 147
  re-points it, and that item's spec lists this test file under **May change**.
- `tests/corpus/manifest.json` — the eight cases and their `detection` fields,
  read at post-item-143 values; no case is added or changed.
- `tests/corpus/fixtures/*.nii.gz` — AC13/AC15/AC16/AC17 recompute firing sets,
  displacements, face flags and component fractions live from these committed
  fixtures.
- `tests/test_098_stray_components.py` — the item-143 cross-check named in **A3**
  (`_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`); read as corroboration only, never as
  the source of an authored value, and not modified.

## Testing Strategy

One focused test per AC in a new module **`tests/test_145_eight_hypothesised_modes.py`**.
Every factual AC recomputes its fact from the primary source — the live registry,
`MODE_ANCHOR_PATHS`, the parsed `vision.md`, or a fresh drive of the committed
fixture — and compares; no AC is met by a length floor, a token-presence check or
a flag derived from the declarations themselves (the three defects
[`../queue/queue-020.md`](../queue/queue-020.md) names).

Structure:

- **Parametrised over the eight mode ids** for AC1–AC6, AC19 and AC22, so a
  missing or malformed entry fails naming the mode.
- **Corpus-driven tests** (AC8–AC18, AC20, AC21) share **one module-scoped
  fixture** that drives each committed case through `measured_firing` /
  `pipeline_findings` / `reconstructed_findings` **once** and caches the findings
  per case id. The corpus drive is the expensive part of this module, and item
  149 is already settling the call-count discipline for
  `test_138_traceability_matrix.py` for exactly this reason
  (`insights.md`, item 139, 2026-09-03) — set it here from the start. Do **not**
  cache inside the production module: that would defeat AC7's and AC13's live
  derivation.
- **AC7** mutates only in-test copies (`dataclasses.replace`); the shipped
  `SPECIFICATION` is never mutated, and a follow-up assertion confirms the
  shipped mode's derived rung is unchanged afterwards.

Adversarial and edge cases:

- An expected firing set deliberately altered (an extra `rule_id`, a missing one,
  the empty tuple on a case that fires) drops `derive_status` from `"validated"`
  to `"implemented"` and is reported — the disagreement is visible, not silent.
- An edge rung outside `EVIDENCE_RUNGS` is rejected at construction, naming the
  mode and the rule (item 144's guard, re-exercised on a mode-1 shaped entry).
- A `discriminator` that names no sibling mode fails AC19 naming the mode.
- A `detector` that does not prefix the finding the case produces fails AC20
  naming the mode, the rule and the case — including the near-miss shape (a tag
  with the trailing colon dropped), so a substring accident cannot pass.
- Determinism/immutability: `specification_to_dict()` and `render_markdown()`
  called twice compare equal, mutating the first result does not affect the
  second, and two consecutive regenerations into a temporary directory are byte
  identical (AC23).
- `iter_modes()` remains ascending and `SPECIFICATION` remains a read-only
  mapping after the extension.

**Existing tests to reconcile** (they pin the *old* two-entry seed and the
exact-singleton derivation; leaving them is a red suite on stale assumptions, not
on new code) — all in `tests/test_144_failure_mode_specification.py`:

1. `test_ac16_specification_carries_exactly_modes_three_and_eight` asserts
   `ids == (3, 8)` → becomes `(1, 2, 3, 4, 5, 6, 7, 8)`; rename it to what it now
   pins.
2. `test_ac16_every_field_non_empty` and
   `test_ac16_each_id_is_a_key_of_mode_anchor_paths` are parametrised
   `[3, 8]` → widen to all eight (item 146 widens again).
3. `test_ac9_derive_status_implemented_iff_a_registered_rule_declares_the_mode`
   builds its probe on mode 3 and asserts `"specified"` before registering a
   throwaway rule → rebuild the probe on a mode id no registered rule declares,
   per **A2**.

A sweep of `tests/` found no other assertion that pins the seed size, the
generated artifacts' content, or `MODE_RUNGS` in a way this item moves: the
`failure_modes` hits elsewhere are the feature catalogue's `failure_modes`
column, which this item does not touch (no declaration changes), and item 143's
`test_098` cross-check, which is read-only here.

## Validation  <!-- OPTIONAL: how to OBSERVE this working, beyond the tests -->

The review surface item 150 signs is a document a person reads, so it is
inspected, not merely regenerated. No `[validation]` profile is needed — the
whole item runs on the default CPU-only install.

1. `.venv/bin/python -m segfacet.failure_modes`
2. `git diff --stat docs/aide/failure_modes.generated.md docs/aide/failure_modes.generated.json`
   — the only changed paths are those two.
3. Read `docs/aide/failure_modes.generated.md` end to end and confirm, per
   entry: all eight modes present in ascending order; the three discriminator
   pairs legible as prose a maintainer can accept or reject; the
   `reference_delta` and `bounds` edges rendered at `needs-real-data` beside
   demonstrated edges at `synthetic-demonstrable`; mode 6's expected firing
   showing both `border` and `mislabel` with the measured displacement in its
   reason; mode 7's cap sentence; mode 8's single-channel sentence; every
   `Status, derived (live)` reading `validated`.
4. `python .aide/scripts/aide.py check` — OK at **7** warnings (AC24).
5. `python .aide/scripts/aide.py scope` — no path outside **May change**.

## Dependencies

- **Item 143** — merged. Corrected the synthetic corpus's S-axis stacking and
  regenerated every committed corpus value; every `expected_firing` and the mode-6
  displacement authored here are measured on that corrected corpus (**G7**).
- **Item 144** — merged. Provides `src/segfacet/failure_modes.py`: the `ModeSpec`
  / `CandidateFeature` / `IntendedRule` / `CorpusCaseExpectation` schema, the
  closed vocabularies, `derive_status`, `derive_mode_rung`, `measured_firing`,
  `case_agrees`, `specification_conflicts`, `specification_to_dict`,
  `render_markdown`, `main`, and the two `.gitattributes`-pinned artifact paths.
  This item authors **through** that schema and extends it in no way (**A5**).
  The one exception is the `derive_status` correction in **A1**, which the
  concurrent review on `review/144-findings` may land first.

**Downstream:** item 146 adds the ninth mode and the first `proposed` entry
through the same lifecycle and widens the parametrised pins again; item 147
collapses `FAILURE_MODE_NAMES`, `MODE_RUNGS`, the `vision.md` §6 parse and the
`Expectation` / `RuleModeDeclaration` claims onto this populated specification
and re-points AC3's parse; item 149 re-points `build_matrix` at these entries as
its primary source and renders expected beside measured; item 150 takes the
maintainer through this rendering entry by entry and raises the sign-off gate;
item 151 replays the stage and attests its acceptance criteria.

## Decisions & Trade-offs

To be updated during implementation.
