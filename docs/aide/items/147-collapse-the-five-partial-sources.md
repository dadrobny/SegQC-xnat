# Item 147 — Collapse the five partial sources onto the specification

> **Created:** 2026-09-04 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 147
> **Objectives:** G2 (detect catalogued failure modes), G7 (evaluable and
> regression-testable), G8 (extensible — the generated artifacts become
> conformance reports over one record)
> **Suggested branch:** `aide/147-collapse-the-five-partial-sources`

---

## Description

Stage 30 D4. Items 144–146 built the failure-mode specification
(`src/segfacet/failure_modes.py`) and populated it: eight seed modes, the ninth
mode entered through the lifecycle, and the first `proposed` entry — ten
entries, per-edge evidence rungs, per-corpus-case expected firing sets, derived
`implemented`/`validated`. **The specification exists but is not yet the single
record**: the five partial sources queue-020 names still stand beside it, and
three located defects (`insights.md`, item 136, 2026-09-02) still sit in the
seam that checks them.

This item makes the specification the record every operational claim is checked
against, and closes those three defects **by replacement** — the mechanism they
live in is retired, not hardened.

Per source:

1. **`FAILURE_MODE_NAMES`** (`synth/perturbation.py:62`) is **derived from the
   specification**, not retired: the map's values are the paraphrases the two
   committed corpus manifests already carry, and a corpus-value change is out of
   this queue's scope. `ModeSpec` gains an authored `short_name` field carrying
   each paraphrase verbatim; `FAILURE_MODE_NAMES` becomes
   `{0: CLEAN_CONTROL_NAME} | {id: short_name}` derived over `SPECIFICATION`, so
   the key-0 clean control stays explicit and every other key follows the
   specification (keys 9 and 10 appear for the first time).
2. **`MODE_RUNGS`** (`traceability.py:146`), with `ModeRung` and the duplicate
   `RUNGS` vocabulary, is **retired**. `build_matrix` reads each mode's rung
   from `failure_modes.derive_mode_rung()` (item 145's per-edge rungs) and its
   mechanism sentence from a new authored `ModeSpec.mechanism` field, so modes 9
   and 10 stop rendering the empty rung item 146 had to guard for.
   `RUNG_LABELS` moves to `failure_modes.py` unchanged, beside the vocabulary it
   labels.
3. **`MODE_ANCHOR_PATHS`** (`feature_docs.py:353`) **stays**, documented as the
   Stage-18 per-mode *metric*'s read path, referenced from the specification's
   `stage18-metric-anchor` candidate-feature role, and never presented as what a
   rule reads. It is the one declared exception to "the specification is the only
   source".
4. **The `vision.md` §6 parse** (`traceability.py:303-319`) moves into
   `failure_modes.py` as a public `vision_seed_titles()` and feeds exactly **one**
   conformance check in that direction — the eight seed entries' names equal
   §6's list. The matrix's mode titles come from `SPECIFICATION[mode].name`
   instead, and the tests that hand-roll their own parse for that comparison
   re-point at the specification.
5. **The `Expectation` / `RuleModeDeclaration` operational claims** stay, now
   checked against the specification in **both** directions: a declared mode the
   specification does not list; a specification `intended_rule` whose rule
   declares no such mode; a corpus case the specification does not carry; a
   corpus case whose manifest expectation disagrees with the specification's
   expected firing set. A corpus case designating an **unregistered** `rule_id`
   is reported for the first time.

The three defects close with that seam:

- the `"corpus"` **evidence tag** is retired rather than hardened — the per-edge
  rungs carry the "demonstrated end-to-end" claim as data now (item 145's AC8
  check already proves every `synthetic-demonstrable` edge is demonstrated), so
  the exact-element membership test over an unvalidated tuple
  (`catalogue.py:1105`) goes away with the branch it gated;
- `RuleModeDeclaration.__post_init__` (`heuristics/rule.py:113-118`) gains
  **tuple checks** on `evidence` and `modes`, so a bare string can no longer
  bind a tag by substring accident nor iterate character-wise, and a list-valued
  `modes` can no longer stay mutable in place;
- the corpus-to-declaration direction (`catalogue.py:1027-1035`) stops iterating
  only the **registered** rules, so a corpus case designating a `rule_id` no rule
  registers is consulted and reported.

Mode 7's rung rationale is settled here as **one correct sentence** in the
specification (`insights.md`, item 145, 2026-09-03): the claim
`rank(v) == v - 1` is false across exactly the lumbar range §6.7's example uses,
that example is a **single** rank descent, and the single-relabel cap belongs to
the fixture generator, not to `heuristics/sequence.py`. The sentence lands in
`SPECIFICATION[7].mechanism` — its only home once `MODE_RUNGS` is gone — and is
measured against `segfacet.labels.CANONICAL_ORDER` rather than token-pinned.

**What this item is NOT.** It changes **no rule logic**: no threshold,
condition, severity, `evaluate` body or registration order moves, and the only
edits under `heuristics/` are `rule.py`'s two validation checks and six rules'
`mode_declaration` **literals** (their `evidence` tuples), exactly the shape item
146 used for the two intensity rules. It adds, removes or re-values **no corpus
case** — both manifests are read, never written. It does **not** edit
`vision.md` or `roadmap.md` (queue-020 scope fence). It does **not** do item
148's per-detector/per-path mode attribution, and it does **not** do item 149's
full matrix re-point: this item moves the matrix's **title source** and **rung
source** only, leaving `TraceabilityMatrix`'s record shape otherwise untouched
so 149's expected-vs-measured scoring and two-column anchor/read-path rendering
rebase cleanly onto it.

## Acceptance Criteria

- [ ] **AC1: one source for mode names in production code.** An AST walk over
  every `.py` file under `src/segfacet/` collects every string literal; the set
  of files containing a literal equal to any live `SPECIFICATION` entry's `name`
  or `short_name` is exactly `{src/segfacet/failure_modes.py,
  src/segfacet/synth/intensity.py}` — the second being item 146's deliberately
  independent corpus generator, pinned against the specification by
  `tests/test_146_ninth_mode_and_first_proposed.py`. The expected set is compared
  as a whole, so a new hand-typed mode name anywhere else fails, naming the file.
- [ ] **AC2: one source for the rung vocabulary.** The same AST walk finds no
  string literal equal to a member of `failure_modes.EVIDENCE_RUNGS` in any
  `src/segfacet/` file other than `failure_modes.py`; `segfacet.traceability` has
  no `MODE_RUNGS`, `ModeRung`, `RUNGS` or `RUNG_LABELS` attribute.
- [ ] **AC3: `MODE_ANCHOR_PATHS` stays, under its metric label.**
  `feature_docs.MODE_ANCHOR_PATHS`'s key set is exactly `{1,…,8}`; every
  `SPECIFICATION` candidate feature with `role == "stage18-metric-anchor"`
  resolves against `MODE_ANCHOR_PATHS[mode.id]`; the set of `src/segfacet/`
  modules **referencing** the name `MODE_ANCHOR_PATHS` — an AST `Name`,
  `Attribute` or `ImportFrom` use of it, never a comment or docstring mention
  — is exactly `{feature_docs.py, catalogue.py, traceability.py,
  failure_modes.py}`; and the matrix renders it under a column whose header
  names it an **anchor** path, distinct from the rule read-path column item
  149 adds.
- [ ] **AC4: the vision §6 parse has one home.** `failure_modes.vision_seed_titles()`
  returns the parsed §6 titles, and `docs/aide/vision.md` is read by no other
  module under `src/segfacet/` — an AST scan over the tree for a non-docstring
  string constant containing `vision.md` (a docstring or comment mentioning
  the file's name, without reading it, does not count).
- [ ] **AC5: the eight seed names still equal vision §6's list.** For each of
  modes 1–8, `SPECIFICATION[id].name` equals `vision_seed_titles()[id]`,
  recomputed live from `docs/aide/vision.md` — the one kept conformance check in
  that direction. Modes 9 and 10 are absent from the parse and are not compared.
  *(closes the "eight seed names equal `vision.md` §6's list" clause of Stage 30
  acceptance criterion 5.)*
- [ ] **AC6: the matrix's mode titles come from the specification.** For every
  mode in a freshly built matrix, `ModeRecord.title == SPECIFICATION[mode].name`,
  including modes 9 and 10, which rendered an empty title before this item.
- [ ] **AC7: `MODE_RUNGS` is retired and the matrix's rungs are derived.** For
  every mode in a freshly built matrix, `ModeRecord.rung` equals
  `failure_modes.derive_mode_rung(SPECIFICATION[mode])` (empty string where that
  is `None`), and mode 9's rendered rung is non-empty.
  *(closes the "`MODE_RUNGS` … replaced by the specification" clause of Stage 30
  acceptance criterion 5.)*
- [ ] **AC8: mode 10's absent rung renders explicitly.** Mode 10 has no
  `intended_rules`, so `derive_mode_rung` returns `None`; the rendered markdown
  row and the JSON record show that absence explicitly (`(none)` / `null`), not
  as a blank indistinguishable from a failed lookup.
- [ ] **AC9: every mode's mechanism sentence names something that resolves
  live.** For each of the ten modes, `ModeSpec.mechanism` is non-empty and
  contains at least one token that resolves against live state — an element of
  that mode's `MODE_ANCHOR_PATHS` entry, a `path` of one of its
  `candidate_features` (Implementation step 2's mode-10 route, since
  `MODE_ANCHOR_PATHS` has no entry for a `proposed` mode), a `case_id` of one
  of its `corpus_cases`, or a `rule_id` of one of its `intended_rules` —
  recomputed per mode, never a length floor. (Item 138's AC31 check, carried
  across the retirement of `MODE_RUNGS` rather than dropped with it.)
- [ ] **AC10: mode 7's corrected sentence, measured.** `SPECIFICATION[7].mechanism`
  is the only place in `src/segfacet/` carrying the mode-7 rung rationale, and
  the literal `rank(v) == v - 1` appears nowhere under the sources this item
  collapses onto the specification — `src/segfacet/failure_modes.py`,
  `src/segfacet/traceability.py`, `src/segfacet/heuristics/` and
  `src/segfacet/synth/perturbation.py` — the same claim the pre-existing
  `src/segfacet/eval/severity_ladder.py` (item 141, Stage 21) still carries and
  is out of this item's authorised paths (`insights.md`, item 147, 2026-09-04).
  The sentence's claims are recomputed in the test from
  `segfacet.labels.CANONICAL_ORDER` and `segfacet.labels.DEFAULT_LABEL_MAP`:
  every lumbar label `L1`–`L5` has canonical rank equal to its integer value,
  `T12` has rank equal to its value minus one, and the rank sequence of §6.7's
  `L1 → T12 → L2 → L5` example contains exactly **one** descent.
- [ ] **AC11: the sequence rule caps nothing, measured.** `SequenceRule`
  evaluated on a record with one out-of-order pair and on a record with two
  produces a finding in both cases, driven by `relationships.out_of_order_labels`
  being non-empty rather than by a descent count — so the single-relabel cap is
  correctly attributed in AC10's sentence to
  `synth/identity_ordering_alignment.py::SequenceBreakPerturbation`, which
  relabels exactly one vertebra.
- [ ] **AC12: a declared mode the specification does not list is reported.** With
  a registered rule's `mode_declaration` monkeypatched to declare a mode absent
  from `SPECIFICATION`, the conformance check returns a message naming both the
  `rule_id` and the mode; retracting the patch retracts the message.
- [ ] **AC13: a specification `intended_rule` whose rule declares no such mode is
  reported.** With one `IntendedRule` edge redirected to a registered rule that
  does not declare that mode (and, as a second case, to a `rule_id` no rule
  registers), the check returns a message naming the `rule_id` and the mode.
- [ ] **AC14: a corpus case the specification does not carry is reported.** With
  a manifest case's `failure_mode` pointed at a mode whose `corpus_cases` do not
  carry that `case_id`, the check returns a message naming the `case_id` and the
  mode; both committed manifests are covered by the same check.
- [ ] **AC15: a corpus case whose manifest expectation disagrees with the
  specification is reported.** For a geometric case, a manifest
  `expected_rule_ids` element absent from the specification's `expected_firing`
  is reported; for an intensity case, a manifest `expected_firing` unequal to the
  specification's is reported. Each message names the `case_id`, the mode and
  both sets.
- [ ] **AC16: a corpus case designating an unregistered `rule_id` is reported.**
  With the corpus-derived map carrying a `rule_id` no rule registers,
  `catalogue.rule_declaration_conflicts()` returns a message naming that
  `rule_id` — the direction that was previously blind because the check iterated
  the registered rules.
- [ ] **AC17: both checks are clean on the shipped tree.**
  `failure_modes.specification_conflicts()` and
  `catalogue.rule_declaration_conflicts()` each return `()` on the shipped
  registry, specification and committed corpora, and both are deterministic
  across two calls.
- [ ] **AC18: `RuleModeDeclaration` rejects a bare string.** Constructing with
  `evidence="corpus-derived"` (and, separately, with a `str`-valued `modes`)
  raises `ValueError` whose message names the offending field and says a tuple is
  required.
- [ ] **AC19: `RuleModeDeclaration` rejects a list.** Constructing with
  `evidence=["a"]` or `modes=[1]` raises `ValueError` naming the offending field;
  a valid tuple construction is unaffected.
- [ ] **AC20: the reserved `"corpus"` evidence tag is gone from the tree.** No
  `RuleModeDeclaration(...)` call in `src/segfacet/` or `tests/` passes
  `"corpus"` as an element of `evidence` (AST scan over both trees), and no
  module under `src/segfacet/` tests membership of the literal `"corpus"` in an
  `evidence` value. The test declares the retained, unrelated uses it does not
  claim — `ModeRecord.rule_attribution`'s `"corpus"`/`"analytic"` values (derived
  from the corpus map, never from `evidence`), `CorpusCaseExpectation.corpus`,
  `observed_range`/`benchmark`'s `"corpus"` population name, and corpus directory
  path segments — as an explicit allowlist, so a re-introduction elsewhere fails.
- [ ] **AC21: `FAILURE_MODE_NAMES` is derived from the specification.**
  `set(synth.perturbation.FAILURE_MODE_NAMES) - {0} == set(SPECIFICATION)`;
  `FAILURE_MODE_NAMES[0]` is the explicit clean-control entry; and for every mode
  id, `FAILURE_MODE_NAMES[id] == SPECIFICATION[id].short_name`. Key sets are
  compared, never the strings against `SPECIFICATION[id].name` — the values are
  paraphrases, not vision titles.
  *(closes the "`FAILURE_MODE_NAMES` … derived from the specification" clause of
  Stage 30 acceptance criterion 5.)*
- [ ] **AC22: the committed corpora do not move.** Every case in
  `tests/corpus/manifest.json` and `tests/corpus/intensity/manifest.json`
  satisfies `case["failure_mode_name"] == FAILURE_MODE_NAMES[case["failure_mode"]]`
  against the derived map, and both manifests' committed bytes are unchanged by
  this item.
- [ ] **AC23: the specification's new fields reach both artifacts.** Every mode's
  `short_name` and `mechanism` appear in `docs/aide/failure_modes.generated.json`
  and in the rendered `.md`, and the JSON's mode records carry both keys for all
  ten entries.
- [ ] **AC24: all three generated artifact pairs regenerate byte-identically.**
  `failure_modes.generated.{md,json}`, `feature_catalogue.generated.{md,json}`
  and `traceability_matrix.generated.{md,json}` each regenerate byte-identically
  run-to-run in one session, are LF-only with exactly one trailing newline, and
  match their committed copies through
  `segfacet.synth.golden.assert_matches_committed_artifact`.
- [ ] **AC25: the matrix no longer advertises a retired constant.** The matrix's
  `note` field names the specification (`src/segfacet/failure_modes.py`) as the
  source to edit and mentions neither `MODE_RUNGS` nor the `"corpus"` evidence
  tag, asserted on the regenerated artifacts.
- [ ] **AC26: no rule firing moves.** Every corpus case across both committed
  manifests still measures the firing set the specification authors
  (`failure_modes.case_agrees` true for all ten modes' cases), modes 1–9 derive
  `validated` and mode 10 derives `proposed`, all recomputed live.
- [ ] **AC27 (engine 1.37.0): `aide check` stays at 7 warnings.**
  `python .aide/scripts/aide.py check` reports exactly 7 warnings, none of them a
  `.gitattributes` lint (this item adds no committed fixture path).

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (`aide.toml`), so no question was put to the caller;
each defensible default taken is recorded here for the queue-boundary audit.

- **A1 — `FAILURE_MODE_NAMES` is derived, not retired.** The queue allows either.
  Deriving is chosen because the map's *values* are paraphrases the two committed
  corpus manifests carry in `failure_mode_name`, and re-pointing consumers at the
  specification's `name` field would change those values — a corpus-value change,
  which queue-020's scope fence forbids outside item 143. Retiring the *name*
  would additionally touch ~15 test modules and six production modules for no
  change in what is true. The binding stays at
  `src/segfacet/synth/perturbation.py`, derived, so every consumer is unchanged.
- **A2 — `ModeSpec` gains two authored fields, `short_name` and `mechanism`.**
  The retired constants carried data that has to land somewhere: the paraphrase
  names (`FAILURE_MODE_NAMES`) and the rung mechanism sentences (`MODE_RUNGS`).
  Both are authored per mode, both default to `""` at the dataclass level so the
  many `ModeSpec(...)` constructions in tests 144/145/146 keep working, and the
  invariant "every shipped entry carries both, non-empty" is asserted over
  `SPECIFICATION` (AC9, AC21) rather than enforced in `__post_init__`.
- **A3 — `SCHEMA_VERSION` stays `"1.0"`.** The change is purely additive, which
  is the precedent item 146 set for `INTENSITY_MANIFEST_VERSION` when the
  intensity manifest gained four fields.
- **A4 — mode 9's `short_name` equals its `name`** ("Implausible tissue under a
  label"), so `synth/intensity.py`'s deliberately independent generator literal
  and its item-146 pin stay green, and the derived `FAILURE_MODE_NAMES[9]` agrees
  with the intensity manifest's `failure_mode_name`.
- **A5 — six rules' `mode_declaration` literals are edited.** The queue's
  "the whole `"corpus"` tag is gone from the tree" cannot hold while
  `border`, `sequence`, `fragmentation`, `overlap`, `mislabel` and `coverage`
  carry `evidence=("corpus",)`. The edit is the **literal only** — the exact
  shape item 146 used for `intensity` / `intensity_reference_delta` — and no
  threshold, condition, severity or `evaluate` line changes; `run_rules`' output
  on a fixed record is unchanged because the declaration is metadata the engine
  never reads. Replacement evidence is free-form provenance naming the manifest
  and case that corroborate the declaration, in the shape item 146 used.
- **A6 — the `"corpus"`/`"analytic"` *attribution* values stay.**
  `ModeRecord.rule_attribution` derives them from
  `catalogue.scan_synth_rule_mode_map()`, never from a declaration's `evidence`
  (item 137's A7 closed that). They are a different object from the retired
  evidence tag and are explicitly allowlisted by AC20's test.
- **A7 — the `"analytic"` evidence tag stays.** Only the reserved `"corpus"`
  gate is retired; `bounds` and `reference_delta` keep their `"analytic"` tag and
  mechanism sentence, and `tests/test_137_mode_less_rule_disposition.py`'s AC4
  assertions on them are untouched.
- **A8 — the declaration → corpus direction is replaced, not merely deleted.**
  Retiring the `"corpus"`-gated branch removes the only check that a declared
  mode is corroborated by a corpus case. Its force is carried by item 145's
  `test_ac8_every_synthetic_demonstrable_edge_is_demonstrated` (every
  `synthetic-demonstrable` edge is demonstrated on a committed case) plus AC13
  here (every `intended_rule` edge is declared by the rule it names). No claim
  becomes uncheckable.
- **A9 — the two manifests express expectation differently.** The geometric
  manifest carries `expected_rule_ids` (the narrow set expected *among* the fired
  findings); the intensity manifest carries `expected_firing` (the full set).
  AC15 therefore compares by **subset** for the geometric corpus and by
  **equality** for the intensity corpus, and the message says which relation it
  applied.
- **A10 — mode 10's rung is legitimately absent.** "Modes 9/10 no longer render
  an empty rung" is met for mode 9 by derivation from its two authored edges, and
  for mode 10 — a `proposed` entry with no edges by design — by rendering the
  absence explicitly (AC8), not by inventing a rung.
- **A11 — `RUNG_LABELS` moves unchanged.** The three human-readable rung labels
  move from `traceability.py` to `failure_modes.py` verbatim, so the matrix's
  rendered `rung_label` column does not move for modes 1–8; the diff in that
  column is confined to modes 9 and 10 gaining one.
- **A12 — item 149's interface.** This item leaves `TraceabilityMatrix`,
  `ModeRecord`, `RuleRecord` and `FeatureDirection` field sets unchanged (only the
  *source* of `title`, `rung`, `rung_label` and `mechanism` moves), so item 149's
  expected-vs-measured scoring and its two separately-labelled anchor / read-path
  columns are additive on top. If item 149 has not yet landed when this is read,
  that is the interface it should assume.
- **A13 — `vision.md` §6 carries the same mode-7 inaccuracy** ("mode 7's
  two-descent `L1 → T12 → L2 → L5` example"). It is a root document and is not
  edited from inside an item (queue-020 scope fence); one line is appended to
  `docs/aide/insights.md` instead, and the specification's corrected sentence
  states the measurement rather than repeating §6's parenthetical.
- **A14 (engine 1.37.0) — the `aide check` baseline is 7 warnings** on this
  branch's base (measured 2026-09-04): 1 missing-Assumptions roll-up, 2 pending
  human gates, 4 Stage-20 retraction notices. AC27 pins that number under this
  engine.

## Implementation Steps

The code path, in order. Every step is inside `src/segfacet/` unless it names a
document.

1. **`failure_modes.py` — schema.** Add `short_name: str = ""` and
   `mechanism: str = ""` to `ModeSpec`, after `name` and after `discriminator`
   respectively (field order is pinned by a test; pick the order and update that
   pin once). Validate as `str` when non-empty; do **not** make them required at
   construction (**A2**).
2. **`failure_modes.py` — authored values.** Give all ten entries a
   `short_name`: modes 1–8 take the current `FAILURE_MODE_NAMES[1..8]` values
   **verbatim** (they are what both committed manifests carry); mode 9 takes
   `"Implausible tissue under a label"` (**A4**); mode 10 takes a paraphrase in
   the same register. Give all ten a `mechanism`: modes 1–6 and 8 carry their
   `traceability.MODE_RUNGS[id].mechanism` sentence **verbatim** (those were
   corrected and re-verified in items 137/138); mode 7 gets the corrected
   sentence (step 3); modes 9 and 10 get new sentences naming a token that
   resolves (AC9) — mode 9 an intensity `case_id`, mode 10 its candidate feature
   `features.stage3_unavailable` and why no rule exists yet.
3. **`failure_modes.py` — mode 7's one sentence.** Author
   `SPECIFICATION[7].mechanism` as: `CANONICAL_ORDER` inserts `T13` at index 19,
   so a lumbar label's canonical rank equals its integer value (`L1` = 20 → rank
   20 … `L5` = 24 → rank 24) while a thoracic label's rank is its value minus one
   (`T12` = 19 → rank 18); §6.7's own `L1 → T12 → L2 → L5` example is therefore a
   **single** rank descent (20, 18, 21, 24); `heuristics/sequence.py` caps
   nothing — it emits one finding whenever `relationships.out_of_order_labels` is
   non-empty; the single-relabel cap belongs to
   `synth/identity_ordering_alignment.py::SequenceBreakPerturbation`, which
   relabels exactly one vertebra (the tail → `T13`), so the committed corpus can
   express only a single-relabel break and a multi-relabel scramble needs real
   data — hence this edge's `needs-real-data` rung despite `mode7_sequence_break`
   being pipeline-detected. Trim the same claim out of mode 7's `corpus_cases[0].reason`,
   leaving the measured detection fact there and the rationale in `mechanism`
   (one home, AC10).
4. **`failure_modes.py` — the vision parse.** Move `_vision_mode_titles` here as
   public `vision_seed_titles()`, docstring naming it the **seed**, not the
   record; add it to `__all__`.
5. **`failure_modes.py` — the derived name map.** Add `CLEAN_CONTROL_NAME`
   (`"clean control (no failure)"`, the current `FAILURE_MODE_NAMES[0]` value
   verbatim) and `failure_mode_names() -> Mapping[int, str]` returning a
   `MappingProxyType` of `{0: CLEAN_CONTROL_NAME}` plus each mode's
   `short_name`, ascending by key.
6. **`failure_modes.py` — `RUNG_LABELS`.** Move the three labels here verbatim
   (**A11**) and export them.
7. **`failure_modes.py` — the conformance checks.** Extend
   `specification_conflicts()` with the three specification-side shapes: each
   `IntendedRule` edge whose named rule is unregistered or does not declare that
   mode (AC13); each committed corpus case (both manifests, via
   `synth.corpus.load_manifest` and `synth.intensity.load_intensity_manifest`)
   whose `failure_mode` names a mode that does not carry that `case_id` (AC14);
   and each case the specification does carry whose manifest expectation
   disagrees — subset for the geometric corpus, equality for the intensity corpus
   (AC15, **A9**). Messages name the rule or case **and** the mode; the returned
   tuple stays sorted and deterministic. Keep the JSON/manifest reads out of
   module scope (deferred imports, house style).
8. **`catalogue.py` — the two direction fixes.** Delete the
   `if "corpus" in decl.evidence:` branch and its docstring paragraph; rewrite the
   corpus → declaration direction to iterate the **corpus map's** `rule_id`s
   rather than the registered rules, so a designated-but-unregistered `rule_id`
   is reported with its own message (AC16) while the existing
   "corpus designates mode M but the declaration does not include it" message is
   unchanged in wording for registered rules (`traceability.py` regex-matches the
   sibling "outside … SPECIFICATION's key set" message — leave that one's wording
   alone).
9. **`heuristics/rule.py` — tuple checks.** In `__post_init__`, before the
   existing element loops, reject a non-`tuple` `evidence` and a non-`tuple`
   `modes` with a `ValueError` naming the field and the received type (AC18,
   AC19). Update the class docstring's `evidence` paragraph: the `"corpus"` tag
   is retired; `evidence` is free-form provenance, and the mode ↔ rule evidence
   *claim* lives in the specification's per-edge rungs.
10. **The six declaration literals.** In `heuristics/border.py`, `sequence.py`,
    `fragmentation.py`, `overlap.py`, `mislabel.py` and `coverage.py`, replace
    `evidence=("corpus",)` with free-form provenance naming the manifest and the
    corroborating case(s) (**A5**). Nothing else in those files changes.
11. **`traceability.py` — the retirement.** Delete `MODE_RUNGS`, `ModeRung`,
    `RUNGS` and `RUNG_LABELS` (the last moved in step 6). In `build_matrix`,
    source `title` from `SPECIFICATION[mode].name`, `rung` from
    `derive_mode_rung`, `rung_label` from the moved `RUNG_LABELS`, and
    `mechanism` from `SPECIFICATION[mode].mechanism`; drop the
    `_vision_mode_titles()` call and the mode-9/10 guard item 146 added. Update
    `_NOTE` to name `src/segfacet/failure_modes.py` (AC25) and the module
    docstring's "authored constants" paragraph.
12. **`synth/perturbation.py` — the derived binding.** Replace the
    `FAILURE_MODE_NAMES` literal with
    `FAILURE_MODE_NAMES = failure_mode_names()` from
    `segfacet.failure_modes` (a module-level import is safe: `failure_modes`
    imports only `feature_docs` and `verdict`, neither of which imports `synth`).
    Keep `CLEAN_CONTROL_MODE` where it is; update the comment to say the map is
    derived and where the values are authored.
13. **Regenerate the three artifact pairs** with their zero-argument entry
    points (`python -m segfacet.failure_modes`, the catalogue's and the matrix's),
    writing `\n` bytes, and confirm each matches run-to-run.
14. **Insights.** The `vision.md` §6 "two-descent" finding (**A13**) is already
    captured — `docs/aide/insights.md`, item 147, 2026-09-04, appended while this
    spec was written; do not append it a second time. Once the corrected sentence
    lands, tick the 2026-09-03 mode-7 entry (item 145) with
    `python .aide/scripts/aide.py insights tick N --pointer "item 147: SPECIFICATION[7].mechanism"`.

## Authorised paths

**May change:**

- `src/segfacet/failure_modes.py` — the two new fields, the ten entries'
  `short_name` / `mechanism`, mode 7's corrected sentence, `vision_seed_titles`,
  `failure_mode_names`, `CLEAN_CONTROL_NAME`, `RUNG_LABELS`, the extended
  `specification_conflicts`, the rendering of the new fields, and the docstring
  record.
- `src/segfacet/traceability.py` — the retirement of `MODE_RUNGS` / `ModeRung` /
  `RUNGS` / `RUNG_LABELS` and `_vision_mode_titles`, `build_matrix`'s title /
  rung / rung_label / mechanism sources, `_NOTE`, and the docstring. No other
  function's behaviour changes; the matrix's record shape is unchanged (**A12**).
- `src/segfacet/catalogue.py` — `rule_declaration_conflicts` only: the deleted
  `"corpus"`-tag branch and the corpus → declaration direction's iteration
  source, plus the docstring paragraphs describing both. No other function.
- `src/segfacet/heuristics/rule.py` — `RuleModeDeclaration.__post_init__`'s two
  tuple checks and the class docstring's `evidence` paragraph.
- `src/segfacet/heuristics/border.py` — the `mode_declaration` literal's
  `evidence` tuple only (**A5**).
- `src/segfacet/heuristics/sequence.py` — the same.
- `src/segfacet/heuristics/fragmentation.py` — the same.
- `src/segfacet/heuristics/overlap.py` — the same.
- `src/segfacet/heuristics/mislabel.py` — the same.
- `src/segfacet/heuristics/coverage.py` — the same.
- `src/segfacet/synth/perturbation.py` — `FAILURE_MODE_NAMES`' binding becomes
  derived; the import and the comment above it. Nothing else.
- `docs/aide/failure_modes.generated.json` — regenerated: the two new fields.
- `docs/aide/failure_modes.generated.md` — regenerated: the same, plus mode 7's
  corrected sentence.
- `docs/aide/traceability_matrix.generated.json` — regenerated: modes 9/10 gain
  a title and (mode 9) a rung; the `note` changes; mechanism sentences move
  source.
- `docs/aide/traceability_matrix.generated.md` — the same.
- `docs/aide/feature_catalogue.generated.json` — regenerated only if the
  declaration-evidence change moves a rendered evidence cell; expected diff is
  the six rules' evidence strings and nothing else.
- `docs/aide/feature_catalogue.generated.md` — the same.
- `docs/aide/insights.md` — one appended line (**A13**) and the `tick` of the
  2026-09-03 mode-7 entry; nothing reworded.
- `tests/test_147_specification_is_the_record.py` — this item's tests.
- `tests/test_136_rule_mode_declarations.py` — reconciliation only:
  `test_ac4_corroborated_rule_declares_corpus_modes`' `"corpus" in decl.evidence`
  assertion, `test_ac10_corpus_tagged_declared_modes_subset_of_corpus_map` and
  `test_adv_corpus_tag_plus_other_tag_still_binds_ac8_direction` (both premised
  on the retired tag), and the module docstring's two mentions of it.
- `tests/test_137_mode_less_rule_disposition.py` — reconciliation only:
  `test_adv_corpus_tagged_analytic_declaration_is_rejected` (its premise is the
  retired branch) and the docstring's two mentions. AC4's `"analytic"`
  assertions are untouched (**A7**).
- `tests/test_138_traceability_matrix.py` — reconciliation only: the local
  `_vision_mode_titles()` helper and the title comparisons that use it, the
  `_patched_mode_rungs` helper and every `MODE_RUNGS` monkeypatch test,
  `test_ac27_bare_string_evidence_renders_as_one_cell_not_per_character` (the
  construction now raises — force the malformed value past `__post_init__` with
  `object.__setattr__` so `_normalise_evidence`'s defence in depth stays
  covered), `test_adv_ac20_mistagged_corpus_evidence_changes_no_attribution` (use
  a non-reserved evidence string; the assertion is unchanged), and the mode-9/10
  empty-rung expectation near line 1364.
- `tests/test_144_failure_mode_specification.py` — reconciliation only:
  `test_ac2_field_names_are_exactly_section_six_fields`' field tuple, and the
  local `_vision_mode_titles()` helper if it is re-pointed at
  `failure_modes.vision_seed_titles`. `test_ac16_names_match_vision_section_six_parsed_titles`
  is the **kept** conformance check (AC5) and is not weakened.
- `tests/test_145_eight_hypothesised_modes.py` — reconciliation only: the
  `traceability._vision_mode_titles()` call at line 227, and
  `test_ac10b_mode7_records_the_single_rank_descent_cap`, whose token pin
  (`rank(v)`, `v - 1`) asserts the wording this item corrects — it becomes an
  assertion over the corrected `mechanism` sentence, with the measurement moving
  to AC10's test.
- `tests/test_146_ninth_mode_and_first_proposed.py` — reconciliation only: any
  assertion that mode 9 or 10 renders an **empty** rung or title in the matrix.

**Asserts against:**

- `docs/aide/vision.md` — AC4/AC5 parse §6's list live; read-only, and changed
  only through its own loop entry point (queue-020 scope fence).
- `src/segfacet/feature_docs.py` — AC3 reads `MODE_ANCHOR_PATHS` live; its key
  set stays exactly 1–8 and this item writes nothing here.
- `src/segfacet/labels.py` — AC10 recomputes canonical ranks from
  `CANONICAL_ORDER` and label values from `DEFAULT_LABEL_MAP`.
- `src/segfacet/synth/identity_ordering_alignment.py` — AC11 pins
  `SequenceBreakPerturbation` as the single-relabel cap's owner; unchanged here.
- `src/segfacet/synth/intensity.py` — AC1's declared exception: the generator's
  two mode-name literals stay hand-typed and independent (item 146's decision),
  pinned against the specification by that item's tests.
- `src/segfacet/heuristics/runner.py` — AC26 drives `run_rules`.
- `src/segfacet/synth/regression.py` — AC26 measures both corpora through
  `pipeline_findings` / `intensity_pipeline_findings`.
- `src/segfacet/synth/corpus.py` — manifest loading for AC14/AC15/AC26.
- `src/segfacet/synth/golden.py` — AC24's committed-artifact comparison helper.

`src/segfacet/heuristics/sequence.py` is listed under **May change** (its
declaration literal). It is deliberately not pinned here, but AC11's measurement
reads its `evaluate` body, which this item does not change — a change to that
body is a finding, not a fix.
- `tests/corpus/manifest.json` — AC14/AC15/AC22/AC26 read it; no case is added,
  removed or re-valued.
- `tests/corpus/intensity/manifest.json` — the same.
- `tests/corpus/fixtures/*.nii.gz` — AC26's geometric measurements read these.
- `tests/corpus/intensity/fixtures/*.nii.gz` — AC26's intensity measurements.
- `tests/committed_artifact_guard.py` — all three artifact pairs are already
  allowlisted; read as the guard AC24's byte-exactness claims run under. The
  sixth `no-float-leaf` ground is item 149's.
- `.gitattributes` — AC27 reads the existing `text eol=lf` pins; this item adds
  no new fixture path and therefore no line.
- `.aide/VERSION` — **A14**'s engine marker.

## Testing Strategy

New module: **`tests/test_147_specification_is_the_record.py`**, one focused test
per AC in AC order, with the module docstring carrying the AC → test map (house
style, items 144–146).

**Cost and fixtures.** AC26 drives both corpora; every measurement goes through
one module-scoped fixture cache keyed by `case_id`, wrapping
`failure_modes.measured_firing`, as items 145/146 do. A cache inside production
code stays forbidden — it would defeat the adversarial tests that prove the
checks are live. The AST sweeps (AC1, AC2, AC20) parse each `src/segfacet/`
file once into a module-scoped fixture and are reused across those tests.

**Per AC.**

- AC1/AC2 — one AST walk collecting `ast.Constant` string values per file;
  compare the *set of files* carrying a specification name, `short_name` or rung
  vocabulary member against the declared expected set, so the failure names the
  offending file.
- AC3 — `MODE_ANCHOR_PATHS` key set; every `stage18-metric-anchor` candidate
  feature resolved against it; the referencing-module set; the rendered anchor
  column header.
- AC4/AC5 — `vision_seed_titles()` against `SPECIFICATION[1..8].name`, plus a
  grep that no other `src/segfacet/` module mentions `vision.md`.
- AC6/AC7/AC8 — one `build_matrix()` fixture shared by all three; per-mode
  equality against the specification and `derive_mode_rung`, plus mode 10's
  explicit-absence rendering read off the markdown and the dict.
- AC9 — per mode, the resolvable-token check recomputed from that mode's anchors,
  case ids and rule ids.
- AC10 — the recomputation from `CANONICAL_ORDER` / `DEFAULT_LABEL_MAP`, the
  one-descent count over the §6.7 example, and the tree-wide absence of
  `rank(v) == v - 1`.
- AC11 — two synthetic records (one and two out-of-order pairs) through
  `SequenceRule.evaluate`, asserting a finding in both.
- AC12–AC16 — one adversarial test each, monkeypatching a single declaration,
  `IntendedRule` edge, manifest case or corpus map entry, asserting the message
  names the subject **and** the mode, and asserting the conflict retracts when
  the patch is retracted (so the check is live, not a constant).
- AC17 — both checkers empty and deterministic across two calls.
- AC18/AC19 — parametrised over `evidence` and `modes`, `pytest.raises` with the
  field name in the message; plus a valid tuple construction as the control.
- AC20 — AST scan of both trees for `RuleModeDeclaration` calls; grep for the
  membership test; the explicit allowlist of retained unrelated uses.
- AC21/AC22 — key-set equality (never string equality) and the manifests'
  `failure_mode_name` values against the derived map.
- AC23/AC24/AC25 — regeneration into `tmp_path`, run-to-run byte equality,
  committed comparison through `assert_matches_committed_artifact`, LF and
  single-trailing-newline checks, and the `note` assertions.
- AC26 — `case_agrees` over every case; `derive_status` over all ten modes.
- AC27 — `aide check` invoked as a subprocess with the repo's encoding
  convention, its warning count parsed.

**Existing tests to reconcile** (each already listed under May change, with what
moves):

- `tests/test_136_rule_mode_declarations.py` — three tests premised on the
  `"corpus"` tag: the corroborated-rule tag assertion, the corpus-tagged-subset
  test (its `checked` guard now finds nothing), and the "corpus plus another
  tag" adversarial test (the direction it exercises is retired). Rewrite the
  first to assert non-empty free-form evidence; delete the other two's premise
  by re-pointing them at the specification checks (AC12/AC13) or removing them
  with the reason recorded in the module docstring.
- `tests/test_137_mode_less_rule_disposition.py` —
  `test_adv_corpus_tagged_analytic_declaration_is_rejected` asserts the retired
  branch fires; it becomes an assertion that a `bounds` declaration claiming a
  mode the specification does not list **is** reported (AC12's shape).
- `tests/test_138_traceability_matrix.py` — the `MODE_RUNGS` monkeypatch group
  (patch `SPECIFICATION` edges instead, or the moved `RUNG_LABELS`), the local
  vision-title parse and its title comparisons (compare to the specification),
  the bare-string evidence test (construction now raises — keep the
  defence-in-depth coverage by forcing the value past `__post_init__`), the
  mistagged-evidence attribution test (use a non-reserved string), and the
  mode-9/10 empty-rung expectation.
- `tests/test_144_failure_mode_specification.py` — the exact `ModeSpec` field
  tuple (two fields added).
- `tests/test_145_eight_hypothesised_modes.py` — the
  `traceability._vision_mode_titles()` call, and AC10b's token pin on mode 7's
  wording, which pins the sentence this item corrects.
- `tests/test_146_ninth_mode_and_first_proposed.py` — any expectation that mode
  9 or 10 renders an empty rung or title.

**Reconciled during implementation** (2026-09-04), beyond the list above —
each is in an already-authorised test module, each is reconciliation only,
and each is recorded here because it was not foreseen when this section was
written:

- `tests/test_136_rule_mode_declarations.py::test_ac8_surplus_declared_mode_is_reported_naming_both`
  constructed `RuleModeDeclaration(modes=…, evidence=("corpus",))` and relied
  on exactly the `if "corpus" in decl.evidence:` branch step 8 deletes. It is
  re-pointed at the surviving surplus-mode direction — a declared mode
  outside `failure_modes.SPECIFICATION`'s key set — which is the same force
  from a live source, and its evidence tuple is free-form (AC20). The
  complementary direction is this item's AC13.
- `tests/test_138_traceability_matrix.py::test_ac17_mode7_rung_records_its_own_cap`
  asserted `"rank(v) == v - 1" in mode7["mechanism"]` — the false claim AC10
  corrects and forbids tree-wide. It now asserts the literal's **absence**
  plus the corrected sentence's live tokens (`CANONICAL_ORDER`, `T13`) and
  keeps its `L1 → T12 → L2 → L5` assertion unchanged; the measurement of the
  corrected claim is AC10's own test.
- `tests/test_138_traceability_matrix.py::test_ac5_markdown_rows_agree_with_json_for_every_mode_and_rule`
  compared `record["rung"] in row`, which raises `TypeError` once mode 10's
  JSON rung is `null` (AC8). It compares `record["rung"] or "(none)"` now —
  the same JSON↔markdown agreement claim, over the pair of tokens the
  explicit-absence rendering actually writes.

No test that asserts a rule's firing, threshold or severity is touched; if one
moves, that is a finding to record and hand back, not a test to update.

## Validation

Beyond the suite, the collapse should be **observed on the artifacts a reader
sees**. No special environment is needed (no `[validation]` profile applies):

1. `python .aide/scripts/aide.py check` — expect `OK (7 warning(s))`.
2. `.venv/bin/python -m segfacet.failure_modes` then `git diff --stat
   docs/aide/failure_modes.generated.md` — the diff is mode 7's corrected
   sentence plus the two new fields on ten entries, and nothing else.
3. Regenerate the traceability matrix and read `docs/aide/traceability_matrix.generated.md`:
   modes 9 and 10 now carry a title, mode 9 carries a derived rung, mode 10 shows
   its rung absence explicitly, and the note names `failure_modes.py`.
4. `grep -rn 'MODE_RUNGS' src/ tests/` — no hits.

## Dependencies

- **Item 143** — the corrected corpus every expected firing set was measured on.
  ✅ merged.
- **Item 144** — the `ModeSpec` schema, `SPECIFICATION`, `derive_status`,
  `derive_mode_rung`, `specification_conflicts`, the rendering and the two
  committed artifacts this item extends. ✅ merged.
- **Item 145** — the eight seed entries, the per-edge rungs this item makes the
  matrix's rung source, and the mode-7 sentence this item corrects. ✅ merged.
- **Item 146** — the ninth and tenth entries, `measured_firing`'s corpus
  dispatch, `synth/regression.py`'s intensity harness, and the move of
  `catalogue.rule_declaration_conflicts`' known-mode set onto `SPECIFICATION`
  that this item completes. ✅ merged.

**Downstream:** item 148 fixes the rule-granular mode attribution at the
declaration seam this item rewrites; item 149 re-points `build_matrix` fully
(expected-vs-measured scoring, the two labelled anchor / read-path columns) on
top of the title and rung sources moved here; item 150's sign-off reads the
rendering; item 151 validates the stage.

## Decisions & Trade-offs

**D1 — `ModeSpec`'s two new fields default, and so does everything after
them.** The pinned field order puts `short_name` third and `mechanism` sixth,
ahead of fields that have no default (`definition`, `severity`, …). Python
3.9 has no `kw_only`, so a defaulted field cannot precede a non-defaulted
one: every field from `short_name` onward now carries a default (`""` /
`()`). Required-ness is unchanged in practice — `__post_init__` already
rejects an empty `definition`/`observability`/`severity`/`status`/
`provenance` and a non-tuple `candidate_features`/`intended_rules`/
`corpus_cases`, so the only fields that may actually be omitted are the two
new ones (**A2**). `short_name` and `mechanism` are validated as `str` and
may be empty; the "every shipped entry carries both, non-empty" invariant is
asserted over `SPECIFICATION` by the suite, not enforced at construction.

**D2 — measured for AC10 (2026-09-04, `segfacet.labels`).**
`CANONICAL_ORDER.index("T13") == 19`. Values vs canonical ranks:
`T11` 18→17, `T12` 19→18, `L1` 20→**20**, `L2` 21→21, `L3` 22→22, `L4`
23→23, `L5` 24→24. So `rank(v) == v - 1` holds only up to `T12` and is false
across the whole lumbar block §6.7's example uses. The example's rank
sequence is `(20, 18, 21, 24)` — **one** descent; its value sequence is
`(20, 19, 21, 24)` — also one descent. The corrected sentence is
`SPECIFICATION[7].mechanism` and nowhere else in `src/segfacet/`; mode 7's
`corpus_cases[0].reason` keeps only the measured detection fact and points
at `mechanism` for the rationale.

**D3 — measured for AC11 (2026-09-04, `SequenceRule.evaluate` +
`default_config()`).** On a record whose `relationships.out_of_order_labels`
is `[]` → 0 findings; `["T12"]` → 1; `["T12", "L6"]` → 1; `["T12", "L6",
"L2"]` → 1. The rule is driven by the list being non-empty and emits exactly
one finding naming every out-of-order label, so it caps nothing. The
single-relabel limitation is the fixture generator's:
`synth/identity_ordering_alignment.py::SequenceBreakPerturbation` relabels
one vertebra (default: the tail, to `28 == T13`) and rejects a map with
fewer than two present labels. AC10's sentence attributes it there.

**D4 — `specification_conflicts()`'s corpus direction is scoped to the modes
it is passed.** The new AC14/AC15 checks read both committed manifests, but
a caller may pass any subset of the specification (item 144's adversarial
probes pass a single hand-built `ModeSpec`). A manifest case whose
`failure_mode` is not among the passed modes is therefore skipped rather
than reported — otherwise a one-mode probe returns eleven conflicts and
buries the one it is asking about. Cases with `failure_mode == 0` (the clean
controls) are skipped in every call: the clean control is not a failure mode
and has no `ModeSpec`.

**D5 — the mechanism sentence renders after the candidate-feature list.**
A mechanism names the paths it reasons about, so rendering it above the
bullets made the *first* occurrence of an anchor path in
`failure_modes.generated.md` a sentence that merely mentions the path rather
than the bullet that labels it a Stage-18 metric anchor — which item 144's
`test_ac20_stage18_anchor_role_rendered_as_metric_path_not_rule_read`
(a ±200-character window around the first occurrence) reads as a
regression. Moving the sentence below the list preserves that item's claim
without weakening it.

**D6 — the matrix's mode table gains a Stage-18 anchor-path column.** AC3
requires the anchor paths to render under a header naming them an *anchor*,
distinct from the rule read-path column item 149 adds. The column is
additive: `ModeRecord.anchor_paths` already existed and is unchanged, and an
empty entry (modes 9 and 10 have no `MODE_ANCHOR_PATHS` key) renders
`(none)`.

**D7 — an absent rung is `null` / `(none)`, never `""`.** `ModeRecord.rung`
stays a `str` (`""`), because the frozen record's field type is unchanged
(**A12**), but `matrix_to_dict` writes `None` and the markdown writes
`(none)` (AC8), so neither serialisation can be mistaken for a failed
lookup.

**D8 — no rule logic moved.** The only `heuristics/` edits are
`rule.py`'s two outer tuple checks plus its `evidence` docstring paragraph,
and six `mode_declaration` **literals** whose `evidence` tuples became
free-form provenance naming `tests/corpus/manifest.json` and the
corroborating case(s). No threshold, condition, severity, `evaluate` body or
registration order changed; `docs/aide/feature_catalogue.generated.{md,json}`
regenerated **byte-identically**, confirming the declaration change reaches
no rendered catalogue cell.

**D9 — the three artifact pairs.** All three regenerate byte-identically
run-to-run and match their committed copies. The catalogue pair is unchanged
by this item (see D8); `failure_modes.generated.*` gains `short_name` and
`mechanism` on all ten entries plus mode 7's corrected sentence;
`traceability_matrix.generated.*` gains titles for modes 9/10, a derived
rung for mode 9, mode 10's explicit rung absence, the anchor-path column,
and a `note` naming `src/segfacet/failure_modes.py`.

**D10 — four checks in this item's own test module do not pass, and the
reason is not the implementation.** Recorded in full in
[`../insights.md`](../insights.md) (item 147, 2026-09-04) and summarised
here so the next reader does not re-derive it:
`test_ac3_mode_anchor_paths_stays_under_its_own_metric_label` and
`test_ac4_vision_parse_has_one_home` grep for a *mention* of
`MODE_ANCHOR_PATHS` / `vision.md` and hit three comment-and-docstring
occurrences in `src/segfacet/heuristics/reference_delta.py`,
`src/segfacet/__init__.py` and `src/segfacet/heuristics/intensity.py` —
none of which reads either thing, and none of which is an authorised path
for this item. `test_ac10_mode7_corrected_sentence_is_measured`'s tree-wide
scan for the literal `rank(v) == v - 1` hits
`src/segfacet/eval/severity_ladder.py` (item 141), which carries the same
false claim in its docstring and in the mode-7 ladder's `rationale` —
also unauthorised, and correcting it is a Stage-21 question because the
degeneracy conclusion it supports may or may not survive the corrected
premise. `test_ac9_every_mechanism_names_a_token_that_resolves_live[10]` is
unsatisfiable by construction: it builds mode 10's candidate-token set from
`MODE_ANCHOR_PATHS[10]` (absent by AC3), `corpus_cases` (empty by design)
and `intended_rules` (empty by design), omitting the `candidate_features`
path that Implementation step 2 tells this item to name. Every other check
in the module passes.

**D11 — the four checks D10 named are a test-writer/spec call, resolved by
narrowing the AC wording rather than the implementation (2026-09-04).**
Reviewed against D10's own diagnosis, each of the four is the test
over-reaching what its AC actually requires, not a shipped defect:

- AC3/AC4 asked for a bare substring grep over file text, which cannot tell a
  real reference from a comment or docstring naming the same identifier. Both
  are amended to name what they always meant — an actual code reference
  (`MODE_ANCHOR_PATHS`: an AST `Name`/`Attribute`/`ImportFrom` use; `vision.md`:
  a non-docstring string constant) — so `heuristics/reference_delta.py`'s
  comment and `__init__.py` / `heuristics/intensity.py`'s docstring/comment
  mentions stop being false positives, while the real references
  (`feature_docs.py`'s assignment, `catalogue.py`'s and `traceability.py`'s
  attribute reads, `failure_modes.py`'s `vision_seed_titles()` read) still
  resolve, and a planted real reference is still caught (each test keeps a
  positive control proving the narrower walker is not vacuous).
- AC10's sweep is narrowed to the sources this item collapses onto the
  specification (`failure_modes.py`, `traceability.py`, `heuristics/`,
  `synth/perturbation.py`) rather than all of `src/segfacet/`.
  `eval/severity_ladder.py`'s copy of the same false claim (item 141, Stage
  21 — already recorded in `insights.md`, item 147, 2026-09-04) is a real,
  separate latent defect, but correcting it is outside this item's authorised
  paths and is a Stage-21 question per that entry, not this item's AC10 to
  absorb by over-scoping its own tree-wide check.
- AC9's resolving-token set is completed rather than narrowed: Implementation
  step 2 already told this item that mode 10's mechanism names its
  `candidate_features` path (`stage3_unavailable.reason`, since a `proposed`
  mode has no `MODE_ANCHOR_PATHS` entry, no `corpus_cases` and no
  `intended_rules`), but the AC's resolving-token list omitted
  `candidate_features` paths. Adding them (for every mode, matching item
  138's AC31 precedent of resolving anchor paths by substring) is the fix;
  mode 10's mechanism already names the token verbatim.

No implementation changes; `tests/test_147_specification_is_the_record.py` is
amended to match, per the AC wording above.
