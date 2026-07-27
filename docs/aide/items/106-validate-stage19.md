# Item 106 — Validate stage 19: Generated Feature & Rule Catalogue + Steering Review

> **Created:** 2026-07-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8)
> **Queue:** [`../queue/queue-015.md`](../queue/queue-015.md) · Item 106
> *(fourth and last; stage-closing per `aide-create-queue`'s convention — runs
> after 103/104/105 are all merged. Item 103 built the generated catalogue,
> item 104 guards it in CI, item 105 produced the golden-file decision table and
> — on explicit human approval — recorded the sign-off this item is gated on)*
> **Objectives:** G7 (the feature set and the fixtures that pin it must be
> *reviewable and verifiable*, demonstrated by replay rather than asserted),
> G8 (every feature carries a status and a named §6 failure mode, or is
> explicitly `unwired` — measured here on the committed artifact, with the
> shortfall named rather than smoothed over)
> **Suggested branch:** `aide/106-validate-stage19`

---

## Description

Replay Stage 19's use cases end to end and close the stage's three roadmap
acceptance criteria **honestly** — ticking each against what was *actually
exercised* and naming, in `progress.md`, every place the measured result falls
short of the criterion's wording. This is the same shape as item 102 (the
Stage-18 closer) with one decisive difference: **this stage carries a human
steering checkpoint, and this item is gated on it.**

### The gate — the single most load-bearing thing in this spec

`progress.md`'s Stage-19 acceptance list has **three** boxes. This item ticks
**boxes 1 and 2 only**. Box 3 — *"The golden decision table is complete and
signed off by the human reviewer"* — is **item 105's** to tick, and item 105
ticks it only on an explicit human statement of approval at its own Validation
step (item 105 Assumptions, "Item 105 ticks the box, only on explicit
approval"). That ordering is deliberate: it is the only arrangement under which
this item's "confirm sign-off before proceeding" is not circular.

Therefore, **step 0 of executing this item is to read box 3's state.** If it is
not `- [x]` with an italic evidence note naming `golden-decision-table.md`,
this item **stops immediately and hands back**, reporting *"Stage 19 not ready
to close: golden-decision-table sign-off pending"*. It does not tick box 3. It
does not tick boxes 1 or 2. It does not flip the stage to ✅. It does not
"proceed with the parts that don't depend on sign-off". It does not infer
approval from item 105's table being complete, from the suite being green, from
a maintainer's silence, or from anything other than the recorded checkbox. A
fabricated or self-granted tick is the one failure mode Stage 19 exists to
prevent, and AC1–AC3 make the prohibition mechanical rather than hortatory.

The biconditional the module encodes (AC3) outlives this item: it keeps the
stage's ✅ and boxes 1/2 permanently coupled to box 3's state, so a later hand
edit that unticks the sign-off while leaving the stage closed is a red test, not
a silent inconsistency.

### What is replayed, and at what level

Four things shipped in this stage; each is verified here at a level above the
item that built it.

1. **Item 103 built the generator.** Its own suite proves the generator's parts.
   Verified here as the **documented use case**: run the zero-argument command
   `python -m segfacet.catalogue`, confirm the working tree does not move
   (AC5), confirm the committed artifacts equal a live `build_catalogue()`
   rather than having been hand-touched after generation (AC7), and confirm the
   existing HTML status report renders them **with no manual post-editing**
   (AC9) and degrades to its placeholder when the artifact is hidden (AC10).
2. **Item 104 built the drift test.** Its own suite proves the check fires on
   *injected copies of sets*. Verified here as the queue's actual sentence —
   *"CI fails on an undocumented feature"* — by injecting a real extra field
   into a real driver record through the seam item 103's AC16 test uses, and
   showing both item 104's reporter (AC13) and the shipped `strict=True`
   mechanism (AC14) fail while **naming the exact path**, then showing the
   revert restores green (AC15). The hermetic rehearsal is complemented by a
   **real-source** rehearsal executed at the Validation step and transcribed
   into this spec (AC16) — that is the only version that literally demonstrates
   "CI fails", and it is recorded at exactly its true strength.
3. **Item 105 produced the decision table and the sign-off.** Verified here only
   as a **gate** (AC1–AC4). This item re-checks nothing about the table's
   content — item 105's own module owns that — and changes nothing in it.
4. **G8's status/mode discipline.** Measured here on the **committed artifact**
   (AC17/AC18), partitioned three ways, with the counts written into both this
   item's Decisions log and `progress.md`'s checkbox-2 annotation.

### The two honest shortfalls this item must record, not paper over

Both follow from item 103's own committed spec, and both are *expected*
outcomes of a correctly-built Stage 19 — not defects introduced here:

- **G8's criterion has a third state its wording does not name.** The roadmap
  and `progress.md` say *"Every feature carries a status and a named failure
  mode, or is marked `unwired`."* Item 103's AC15 defines a real entry class
  that is neither: a path consumed by a rule that carries **no** §6 mode
  mapping (`bounds`, `intensity`, `reference_delta`,
  `intensity_reference_delta`) and no item-099 anchor gets `status == "keep"`,
  `failure_modes == ()` and `mode_evidence == ("rule_unmapped",)`. It is
  statused, it is not `unwired`, and it names no mode. AC18 measures how many
  entries fall there and AC19 requires the count to be stated on the checkbox
  rather than absorbed. Recording it is the point; closing it is Stage 20's job
  (the traceability matrix is exactly the mechanism that would map those rules
  to modes).
- **`STATUS_OVERRIDES` ships and stays empty, so no feature carries `retune` or
  `retire`.** Item 103 deliberately ships an empty override map (its
  Assumptions: *"`retune` and `retire` are judgments, and Stage 19's whole point
  is that a human makes them at the checkpoint"*), so every wired path is `keep`
  and every unread path is `unwired` — both derived, both honest, and the
  judgment half of the four-value vocabulary is **unexercised**. Populating it
  means editing `src/segfacet/feature_docs.py`, which is production code this
  item may not touch (AC23). The steering review still happens — it is
  Validation step 4, reading the rendered catalogue — but its output here is a
  recorded observation and, where warranted, an `insights.md` line, not an
  override map. AC19 requires this to be stated on checkbox 2.

### What this item is NOT

- **Not new production code.** `src/segfacet/**` and `scripts/**` are untouched.
  This item adds one test module and edits `progress.md` (AC23). Item 097 (the
  Stage-17 closer) did end up changing production code because one of its ACs
  could not otherwise pass; here that would be a **hand-back signal**, not a
  licence to widen scope.
- **Not the sign-off.** It reads box 3; it never writes it (AC2).
- **Not acting on item 105's retire decisions.** No golden file is deleted,
  regenerated, moved or replaced, and no test that consumes one is edited.
  **Stage 19 decides; Stage 21 executes** (`roadmap.md`'s Stage-21 deliverable
  *"Act on Stage 19's golden decision"*, mirrored by `progress.md`'s Stage-21
  bullet). AC22 makes this mechanical, following item 102's precedent of being
  careful that a stage-closing edit cannot be read as claiming a later stage's
  work is done.
- **Not a fix for the two shortfalls above**, and not Stage 20's traceability /
  specificity harness.
- **Not a real-data claim.** Every path set, catalogue entry, status and mode
  attribution in Stage 19 is derived from **in-package synthetic driver
  records** and from committed artifacts. Nothing here touches the "Real
  automatic-segmentation failure corpus" verification row or the Outcome-targets
  table, and no sentence this item writes into `progress.md` may imply otherwise
  (AC24).

## Acceptance Criteria

### Block A — the sign-off gate

- [ ] **AC1: the sign-off state is parsed from `progress.md`, never assumed.**
  The module exposes `stage19_signoff_state() -> str` returning exactly
  `"signed-off"` or `"pending"`. It locates, under the Stage-19
  `**Acceptance.**` list, the checkbox item whose text contains
  `golden decision table is complete and signed off`, and returns
  `"signed-off"` **iff** that item is `- [x]` (case-insensitive on the `x`)
  **and** the item's text — including wrapped continuation lines up to the next
  list item or blank line — contains an italic `*(…)*` note naming
  `golden-decision-table.md`. Every other state, including a bare `- [x]` with
  no such note, returns `"pending"`. If no such checkbox item exists the helper
  fails with a message naming the heading it searched under and listing the
  acceptance items it did find.

- [ ] **AC2: this item never writes the sign-off checkbox or the decision
  table.** The `progress.md` line(s) matched by AC1 are character-for-character
  identical before and after this item's changes, and
  `docs/aide/golden-decision-table.md` is unmodified. Verified by the validator
  from `git diff <merge-base>..HEAD -- docs/aide/progress.md
  docs/aide/golden-decision-table.md`: no hunk may touch that acceptance item,
  and the decision table must not appear in the diff at all. **Not** asserted by
  a byte-hash pytest — see Decisions & Trade-offs.

- [ ] **AC3: the stage cannot close while sign-off is pending — asserted as a
  biconditional that is valid in both states.** In `docs/aide/progress.md`,
  `stage19_signoff_state() == "signed-off"` **iff** all four of the following
  hold: the Stage-19 section heading ends `— ✅`; the stage-summary table's row
  `19` reads `✅`; the first Stage-19 acceptance item (text contains
  `The catalogue is generated, not hand-written`) is `- [x]`; the second (text
  contains `Every feature carries a status`) is `- [x]`. The test passes when
  all five are true and when all five are false, and fails on any mixed state.
  Its failure message names which of the four disagree with the sign-off state.

- [ ] **AC4: a stage does not close over an unfinished deliverable.** If
  `stage19_signoff_state() == "signed-off"`, each of the Stage-19 deliverable
  bullets naming *(Item 103)*, *(Item 104)* and *(Item 105)* begins with `✅`.
  (In the `pending` branch this item does not execute at all — see AC3 and
  Implementation Step 0.)

### Block B — regeneration replay (checkbox 1, first half: *generated, not hand-written*)

- [ ] **AC5: the documented zero-argument regeneration moves nothing.** Calling
  `segfacet.catalogue.main([])` leaves `docs/aide/feature_catalogue.generated.json`
  and `docs/aide/feature_catalogue.generated.md` byte-identical to their
  pre-call contents (`Path.read_bytes()` comparison). The test captures both
  files' bytes first and restores them in a `finally` block, so a *failing* run
  can never leave the working tree dirty.

- [ ] **AC6: the explicit-argument regeneration reproduces the same bytes.**
  `segfacet.catalogue.main(["--json", <tmp>/c.json, "--md", <tmp>/c.md])`
  returns `0` and writes two files whose bytes equal the committed artifacts'.
  (Same claim as AC5 through the other entry path, so a *defaults* regression
  and a *generator* regression are distinguishable rather than conflated.)

- [ ] **AC7: the committed artifacts equal a live build — nothing was hand-edited
  after generation.** `catalogue_to_dict(build_catalogue())` compares equal to
  `json.loads(<committed .json>)`, and `render_markdown(build_catalogue())`
  compares equal to the committed `.md`'s decoded text.

- [ ] **AC8: one entry count, agreed by four independent surfaces.** The count
  stated in the committed `.md`'s header, the number of table rows in that
  document, the number of entries yielded by
  `iter_committed_entries(<committed .json>)`, and `len(build_catalogue().entries)`
  are all the same integer `N`, and `N > 0`. `N` is written verbatim into this
  item's Decisions log and into checkbox 1's annotation.

- [ ] **AC9: the status report renders the generated catalogue with no manual
  post-editing.** Loading `scripts/aide_status_report.py` by path (the
  `importlib.util.spec_from_file_location` pattern
  `tests/test_aide_status_report.py:18-20` already uses),
  `load_feature_catalog(FEATURE_CATALOGUE_PATH)` returns a non-empty tuple whose
  entries total `N` (AC8); `_render_feature_catalog_section()` returns markup
  containing one `<div class="feature-group">` per catalogue group and
  containing **every** catalogue entry path verbatim; and a full `render_html(...)`
  over the real docs completes without raising and contains that section.

- [ ] **AC10: hiding the artifact degrades to the placeholder, live.** With
  `FEATURE_CATALOGUE_PATH` monkeypatched to a non-existent path (the committed
  file itself is never deleted or moved), `load_feature_catalog(...)` returns an
  empty tuple, `_render_feature_catalog_section()` returns a placeholder naming
  the expected path and the regeneration command, and `render_html(...)`
  completes without raising. Undoing the monkeypatch restores the populated
  section.

### Block C — drift replay (checkbox 1, second half: *fails on a deliberately undocumented feature*)

- [ ] **AC11: item 104's check is green on the current tree, through item 104's
  own helpers.** Importing `covered_paths`, `documented_paths`, `drift_report`,
  `strict_build_message`, `load_committed_catalogue` and
  `iter_committed_entries` from `test_104_feature_catalogue_drift` (flat import,
  the style `tests/test_102_stage18_validation.py:49` already uses — **never**
  reimplemented here), all four of item 104's directions report `None` and
  `strict_build_message(functools.partial(build_catalogue, strict=True))`
  returns `None`.

- [ ] **AC12: the covered path set is invariant to the radiomics backend.**
  `normalise_leaf_path` maps every `image_features.per_label.<int>.extended.<name>`
  input to the single path
  `image_features.per_label.{label}.extended.{radiomic}`, asserted over at least
  three distinct `<name>` values chosen to span backends — a builtin
  first-order name, a PyRadiomics-style `original_firstorder_*` name, and an
  arbitrary name matching neither — and over at least two distinct integer label
  keys. The catalogue's covered set therefore cannot change when PyRadiomics is
  installed or removed, which is the mechanical basis of AC21.

- [ ] **AC13: a deliberately undocumented realised feature fails the drift
  report, naming exactly that path.** With one extra key injected into one
  driver record through **the same seam `tests/test_103_feature_catalogue.py`'s
  AC16 test uses** (read that test and reuse its seam; do not invent a second
  one — see Assumptions), the realised set gains exactly one member,
  `per_label.{label}.geometry.zzz_stage19_probe`, and
  `drift_report(realised=<injected set>, documented=frozenset(FEATURE_DOCS), …)`
  returns a non-`None` message that contains that path verbatim, contains the
  literals `src/segfacet/feature_docs.py` and `python -m segfacet.catalogue`,
  and names **no other** path under its realised-but-undocumented heading.

- [ ] **AC14: the same injection makes the shipped strict mechanism fail, as a
  named message rather than an escaping exception.** Under that same injection,
  `strict_build_message(functools.partial(build_catalogue, strict=True))`
  returns a non-`None` message containing `FeatureDocMissing` and
  `per_label.{label}.geometry.zzz_stage19_probe`. No `CatalogueError` propagates
  out of any test or fixture in this module.

- [ ] **AC15: the injection reverts cleanly and green is restored.** After the
  seam is undone, `covered_paths()` equals the frozenset captured before the
  injection, and all five checks of AC11 return `None` again. A `copy.deepcopy`
  snapshot of `dict(FEATURE_DOCS)` and of the parsed committed catalogue, taken
  before the injection, still compare equal afterwards; nothing shipped is
  mutated at any point.

- [ ] **AC16: the real-source rehearsal is executed and transcribed at its true
  strength.** This spec's Decisions & Trade-offs section contains a heading
  `### Real-source drift rehearsal` under which is recorded **either** (a) the
  observed outcome of item 104's Validation step 2 — the probe key inserted into
  `src/segfacet/feature_report.py`, the ids of the tests that failed, the
  verbatim first line of a failure message containing `zzz_drift_probe`, and the
  confirmation that `git checkout -- src/segfacet/feature_report.py` left
  `git status --short` clean and the module green again — **or** (b) the literal
  words `not executed`, with the reason. A test asserts the heading is present
  and that the text below it contains either `zzz_drift_probe` or
  `not executed`. Inventing a transcript fails this AC; recording an honest
  non-execution passes it, and checkbox 1's annotation must then say so.

### Block D — G8 measurement (checkbox 2)

- [ ] **AC17: every committed catalogue entry carries a status from the fixed
  vocabulary.** Every entry yielded by `iter_committed_entries(<committed .json>)`
  has a `status` that is one of `"keep"`, `"retune"`, `"retire"`, `"unwired"` —
  never empty, never `None`, never another string — and the entry count equals
  `N` (AC8).

- [ ] **AC18: the status/mode partition is exhaustive, disjoint and measured.**
  Every committed entry falls into exactly one of three buckets: **(i) moded** —
  `status != "unwired"` and `failure_modes` non-empty; **(ii) unwired** —
  `status == "unwired"`; **(iii) statused-but-mode-unmapped** —
  `status != "unwired"` and `failure_modes` empty. The three counts are
  non-negative, sum to `N`, and no entry matches two buckets. All three counts,
  plus the count of entries whose status is `retune` or `retire` (expected `0`
  while `STATUS_OVERRIDES` is empty), are written verbatim into this item's
  Decisions log and into checkbox 2's annotation.

- [ ] **AC19: checkbox 2, if ticked, carries the honest partition.** If
  `progress.md`'s Stage-19 acceptance item containing `Every feature carries a
  status` is `- [x]`, its italic annotation states, in this order: (a) every one
  of the `N` entries carries a status from the four-value vocabulary; (b) the
  three bucket counts from AC18, naming bucket (iii) **explicitly as a shortfall
  against the criterion's literal wording** whenever its count is `> 0`, with
  `mode_evidence == ("rule_unmapped",)` as its cause and Stage 20 as its closer;
  (c) that `STATUS_OVERRIDES` is empty, so no feature carries `retune` or
  `retire` and the judgment half of the vocabulary is unexercised; (d) that all
  of it is measured on in-package synthetic driver records and the committed
  artifact, not on real data. (Written as tick-implies-evidence so it composes
  with AC3 rather than becoming a landmine on an unticked tree.)

- [ ] **AC20: checkbox 1, if ticked, carries the generated-and-can-fail
  evidence.** If the Stage-19 acceptance item containing `The catalogue is
  generated, not hand-written` is `- [x]`, its italic annotation names: the
  zero-argument regeneration leaving both committed artifacts byte-identical
  (AC5); the agreed entry count `N` (AC8); that `scripts/aide_status_report.py`
  renders from the generated JSON with `FEATURE_CATALOG`/`UNWIRED_EXTRACTORS`
  deleted (AC9); and the drift rehearsal outcome — the hermetic injection
  (AC13/AC14) **and** the real-source rehearsal's recorded result (AC16) at
  exactly the strength AC16 recorded it, never upgraded.

### Block E — the fences

- [ ] **AC21: Stage 19 introduces no environment-gated capability, and that
  table does not move.** `progress.md`'s Environment-Gated Capability
  Verification table has the same number of rows as before this item, and every
  row's Status cell is unchanged. This item's Decisions log records the observed
  result of `python .aide/scripts/aide.py env --profile pyradiomics` and states
  that no row is added because (a) the catalogue is generated from in-package
  synthetic drivers with no optional dependency, external tool or real dataset,
  and (b) the covered path set is backend-invariant (AC12).

- [ ] **AC22: Stage 21's job is left visibly undone.** Exactly nine files match
  `tests/corpus/golden/*.json` and their stems equal the nine corpus `case_id`s
  from `tests/corpus/manifest.json`; `progress.md`'s Stage-21 deliverable bullet
  whose text contains `Stage 19's golden decision acted on` still begins `📋`;
  and every annotation this item writes into `progress.md`'s Stage-19 section
  contains a sentence stating that **Stage 19 decides and Stage 21 executes**,
  naming Stage 21 as the closer of the retire dispositions.

- [ ] **AC23: the scope fence holds — no production code, one new test module.**
  `git diff --name-only <merge-base>..HEAD` lists only
  `docs/aide/items/106-validate-stage19.md`,
  `tests/test_106_stage19_validation.py`, `docs/aide/progress.md`, and
  optionally `docs/aide/insights.md` — nothing under `src/segfacet/**`,
  `scripts/**`, any other file under `tests/**`, `tests/corpus/**`,
  `docs/aide/feature_catalogue.generated.*`, `docs/aide/golden-decision-table.md`,
  `docs/aide/roadmap.md`, `docs/aide/vision.md`, `.github/**` or
  `.gitattributes`. Verified by the validator from that diff, **not** by a
  byte-hash pytest — see Decisions & Trade-offs.

- [ ] **AC24: closing Stage 19 moves no objective and no outcome row.**
  `progress.md`'s Objective-coverage rows for **G7** (`🚧`) and **G8** (`📋`)
  are byte-identical to their pre-106 state; the entire Outcome-targets table is
  byte-identical; the "Real automatic-segmentation failure corpus" row still
  reads `❓ Unverified` and still names Stage 16 as its closer; and no sentence
  this item adds anywhere in `progress.md` asserts real-data coverage for
  anything Stage 19 delivers.

## Assumptions

Clarify mode for this item was **`interactive`** (Stage 19 carries the human
steering checkpoint, and `/aide-spec-queue` forces `interactive` for this
queue). **No question was put to the maintainer during authoring**: the queue's
own item-106 text, item 102's precedent, and — decisively — item 105's
maintainer-settled Assumptions block ("Item 105 ticks the box, only on explicit
approval") between them fixed every load-bearing question this item could have
asked. Everything below is either a fact taken from a committed sibling spec
(marked *[103]* / *[104]* / *[105]*) or a spec-author default. The one decision
worth the maintainer's attention before execution is flagged at the end.

**Taken as settled from the sibling specs — do not re-litigate:**

- *[105 Assumptions, maintainer-confirmed]* **Item 105 ticks `progress.md`'s
  Stage-19 third acceptance checkbox, within its own execution, only on an
  explicit human statement of approval — and if approval is withheld the item
  still lands with the box `- [ ]` and reports "sign-off pending".** This item
  therefore *reads* that box as a precondition and never writes it (AC1/AC2),
  and halts on `pending` (Implementation Step 0). Any other arrangement makes
  the guard circular.
- *[105 AC11/AC12]* **The attestation lives in exactly one place** — that
  checkbox — and `docs/aide/golden-decision-table.md` deliberately carries no
  sign-off field of its own. So this item must not look for a signature block in
  the table, and must not treat the table's completeness as approval.
- *[103 AC19/AC24, Decisions]* **`python -m segfacet.catalogue` with zero
  arguments defaults to the two committed `docs/aide/` paths**, writes with
  `write_bytes` and `\n`, and is byte-reproducible; both artifacts are LF-pinned
  in `.gitattributes` (item 103 AC20). AC5 depends on all three.
- *[103 AC1/AC7/AC15]* **`segfacet.catalogue` exports `normalise_leaf_path`,
  `iter_leaf_paths`, `iter_driver_records`, `build_catalogue`,
  `catalogue_to_dict`, `render_markdown`, `CatalogueError`, `FeatureDocMissing`;**
  every entry carries a status from `{keep, retune, retire, unwired}`; and an
  entry consumed only by mode-unmapped rules has `failure_modes == ()` with
  `mode_evidence == ("rule_unmapped",)`. AC17/AC18's three-bucket partition is a
  direct consequence and is not an invention of this item.
- *[103 Assumptions]* **`STATUS_OVERRIDES` ships empty**, so `retune`/`retire`
  counts are expected to be `0`; and **a large `unwired` tail is the correct
  output of this stage** (~34 of 67 record-tier paths on item 103's prototype).
  A near-empty `unwired` bucket at execution time means the attribution is
  over-matching, not that the feature surface is healthy — say so rather than
  recording a number you do not believe.
- *[103 AC21/AC23]* **`scripts/aide_status_report.py` no longer defines
  `FEATURE_CATALOG`/`UNWIRED_EXTRACTORS`, defines `load_feature_catalog(path)`
  and `FEATURE_CATALOGUE_PATH`, imports nothing from `segfacet`, and degrades to
  a placeholder when the JSON is missing or unparseable.** AC9/AC10 replay
  exactly that surface.
- *[104 Implementation Steps 4]* **`tests/test_104_feature_catalogue_drift.py`
  exposes `covered_paths()`, `documented_paths()`, `drift_report(*, realised,
  documented, realised_label, documented_label)`, `strict_build_message(build_fn)`,
  `load_committed_catalogue()` and `iter_committed_entries(doc)` at module
  level**, and every drift message contains `src/segfacet/feature_docs.py` and
  `python -m segfacet.catalogue` (its AC11). AC11/AC13 import those helpers flat
  (`from test_104_feature_catalogue_drift import …`) — the cross-module test
  import style this suite already uses (`tests/test_102_stage18_validation.py:49`).
- *[104 AC22 / Decisions]* **A byte-hash scope fence is the wrong instrument in
  this repo** — items 099–101 each shipped one and each produced a Windows-only
  CI break invisible to every gate in this loop (`insights.md`, three entries),
  and item 101 additionally showed the pattern self-contradicts as soon as a
  later item is legitimately authorised to touch a pinned file. AC2 and AC23 are
  therefore git-diff obligations on the validator, not pytests.

**Spec-author defaults:**

- **This item halts rather than partially executing when sign-off is pending.**
  The alternative — land the test module and the replay evidence but leave the
  stage open — was considered and rejected: it would mark item 106 done while
  its actual deliverable (a closed, honestly-annotated stage) does not exist, and
  it would leave a `progress.md` in a state AC3 has to special-case. Halting at
  step 0 keeps the item's completion and the stage's closure the same event. The
  cost is that the AC3 biconditional only ever lands on the signed-off branch —
  which is why its *test* is written to pass in both states (so a later untick
  is caught rather than crashing the suite).
- **This item adds one test module, `tests/test_106_stage19_validation.py`,
  following item 102's precedent** (`tests/test_102_stage18_validation.py`). A
  stage validation whose only artefact is prose in `progress.md` cannot be
  re-run, so the replay is encoded as tests wherever it can be, and only the
  irreducibly-manual parts (reading the rendered catalogue; the real-source
  rehearsal) live in Validation.
- **The "prove it can fail" rehearsal is done twice, at two strengths, and the
  spec says which is which.** (i) **Hermetic, in-suite** (AC13/AC14/AC15):
  inject one extra key into one real driver record, assert both item 104's
  reporter and the shipped strict mechanism name the path, assert the revert
  restores green. This is repeatable and CI-visible. (ii) **Real-source, manual**
  (AC16 + Validation step 3): edit `src/segfacet/feature_report.py`, run
  pytest, transcribe the observed failure, `git checkout --`, confirm the tree
  is clean. This is the only version that literally demonstrates "CI fails on an
  undocumented feature", and it cannot be a test because a test that edits
  tracked source and reverts it is a tree-corrupting hazard on a failure path.
  Neither substitutes for the other; AC20 requires both to be reported at their
  own strength.
- **The injection seam is item 103's, read at execution time, not guessed here.**
  Item 103 AC16 requires a way to build a driver record carrying a synthetic
  extra field, and its Testing Strategy says to do so "via `monkeypatch`/local
  copies, never by editing the shipped modules". The most likely realised seam is
  a monkeypatch of `segfacet.catalogue.iter_driver_records` (which
  `build_catalogue` resolves as a module global). **The test-writer must open
  `tests/test_103_feature_catalogue.py`'s AC16 test and reuse whatever seam it
  actually uses**, rather than inventing a second one; if `build_catalogue`
  turns out to inline its driver construction with no patchable seam at all, that
  is a **hand-back to item 103**, not a licence to edit production code here.
- **Stage 19 introduces no Environment-Gated Capability Verification row.** That
  table's own rule scopes it to "an optional package, external tool, **or**
  real-world dataset / environment". Stage 19's deliverables need none: item
  103's augmented tier is realised through converters from placeholder
  dataclasses precisely so PyRadiomics is not required, item 104's module is
  ungated by its own AC1, and item 105's is pure document parsing plus
  `segfacet.catalogue`. The one plausible candidate — "does the catalogue still
  cover the record when the real PyRadiomics backend is installed?" — is
  answered structurally by AC12: `extended.<anything>` collapses to a single
  path, so the covered set is backend-invariant. A human reviewer is not an
  environment, and the human checkpoint is already recorded by checkbox 3. AC21
  pins the table unchanged rather than adding a decorative row.
- **Boxes 1 and 2 are ticked *with* their qualifications rather than left open.**
  Stage 19's planned work ships and is verified; the shortfalls are in the
  *measured outcome* for one entry class and in an unexercised half of a
  vocabulary. This tracker's "Two kinds of done" rule (`progress.md:58-77`) says
  a stage's ✅ is a claim about code, with unmet outcomes recorded rather than
  blocking the stage. **G7 stays 🚧 and G8 stays 📋 regardless** (AC24), so
  nothing is over-claimed by ticking a box with the shortfall written on the
  same line.
- **Items 103, 104 and 105 are all ✅ merged before this item starts.** This is
  the explicit stage-closing item; it has no meaning earlier, and AC4 makes the
  precondition mechanical. Every interface this spec names is taken from a
  *committed spec* of an item that is **not yet built** at authoring time
  (2026-07-27) — so if any of them differs at execution, the correct response is
  a hand-back to the owning item, not a silent adaptation here.

**Flagged for the maintainer, resolvable at execution rather than now:** whether
the Stage-19 steering review (Validation step 4 — reading the rendered catalogue
and sanity-checking the `unwired` tail) should be permitted to produce
`STATUS_OVERRIDES` entries. This spec says **no** — that edit is production code
outside this item's fence — and routes any resulting judgment to `insights.md`
for queue-boundary triage. If the maintainer wants the review's output captured
as actual `retune`/`retire` statuses, that is a **new item**, and this item's
checkbox-2 annotation should name it.

## Implementation Steps

No changes under `source_dir = src/segfacet`. The work is one new test module
plus `docs/aide/progress.md`.

0. **Read the gate before doing anything else.** Open `docs/aide/progress.md`,
   find the Stage-19 acceptance item containing *"golden decision table is
   complete and signed off"*, and read its state. **If it is not `- [x]` with an
   italic evidence note naming `golden-decision-table.md`: stop.** Write no
   file, commit nothing, and hand back with *"Stage 19 not ready to close:
   golden-decision-table sign-off pending — item 105 records the sign-off; it
   has not been granted."* Do not tick it, do not tick boxes 1 or 2, do not flip
   the stage, and do not proceed with "the parts that don't depend on it".
   Also confirm items 103/104/105's deliverable bullets are `✅` (AC4); if any
   is not, hand back the same way.

1. **New test module `tests/test_106_stage19_validation.py`**, structured in the
   five blocks of the Acceptance Criteria, with module-scoped fixtures so the
   expensive work happens once:
   - **Shared fixtures:** the parsed `progress.md` (read once, split into its
     Stage-19 section, the stage-summary table, the Environment-Gated table and
     the Objective-coverage table); the committed catalogue JSON parsed via item
     104's `load_committed_catalogue()`; the committed `.md` text; one
     `build_catalogue()` result; the pre-injection `covered_paths()` frozenset.
   - **Path constants:** `_TESTS_DIR = Path(__file__).resolve().parent`,
     `_REPO_ROOT = _TESTS_DIR.parent`. **No absolute path literal anywhere** —
     `insights.md`'s item-099 entry documents exactly this bug class going
     undetected through the whole loop.
   - **Block A (AC1–AC4):** `stage19_signoff_state()` plus the biconditional.
     Write AC3 as an explicit both-branches test (compute the five booleans, then
     `assert len({signed_off, *four_flags}) == 1` with a message naming the
     disagreeing flags), never as `if signed_off: assert …`, which silently
     no-ops on the other branch.
   - **Block B (AC5–AC10):** the two regenerations, the live-build comparison,
     the four-way count agreement, and the status-report render + placeholder.
     AC5 **must** snapshot bytes and restore in `finally`.
   - **Block C (AC11–AC16):** item 104's helpers imported flat; the hermetic
     injection through item 103's AC16 seam; the revert; the Decisions-log
     transcript check.
   - **Block D (AC17–AC20):** the partition over the committed artifact, and the
     two tick-implies-evidence annotation checks.
   - **Block E (AC21–AC24):** the tables-unchanged checks (row counts, Status
     cells, the Stage-21 bullet, the nine goldens' presence, the G7/G8 rows).

2. **`docs/aide/progress.md`** — the only non-test edit, made only after step 0
   passed:
   - Stage 19 section heading → `— ✅` (AC3).
   - Item 106's deliverable bullet `📋` → `✅` (the validator reconciles this via
     `python .aide/scripts/aide.py progress set 106 done`; do not hand-edit it if
     the CLI covers it).
   - Stage-summary table row `19` → `✅` (AC3).
   - Tick acceptance box **1** with the AC20 annotation and box **2** with the
     AC19 annotation. **Do not touch box 3** (AC2).
   - Include, in one of those two annotations, the "Stage 19 decides, Stage 21
     executes" sentence (AC22).
   - **Do not** touch the Environment-Gated table (AC21), the Outcome-targets
     table, the Objective-coverage table, or the Stage-21 section (AC22/AC24).

3. **Record the measurements in this spec's Decisions & Trade-offs** as they are
   observed: `N` (AC8), the three bucket counts and the `retune`/`retire` count
   (AC18), the `aide env --profile pyradiomics` result (AC21), and the
   `### Real-source drift rehearsal` transcript (AC16).

4. **Do NOT touch** `src/segfacet/**`, `scripts/**`, any other file under
   `tests/**`, `tests/corpus/**`, `docs/aide/feature_catalogue.generated.*`,
   `docs/aide/golden-decision-table.md`, `docs/aide/roadmap.md`,
   `docs/aide/vision.md`, `.github/**`, `.gitattributes` (AC23). In particular:
   do not delete, regenerate, move or replace any golden, and do not populate
   `STATUS_OVERRIDES`.

## Testing Strategy

- **Framework:** `pytest`. One new module,
  `tests/test_106_stage19_validation.py`. **No existing test module is
  modified** — `tests/test_103_feature_catalogue.py`,
  `tests/test_104_feature_catalogue_drift.py` and
  `tests/test_105_golden_decision_table.py` must all stay green **unmodified**;
  an edit to any of them is a red flag for the validator, since this item
  changes no behaviour.

- **One focused test per AC**, AC1–AC24. The load-bearing ones:
  - **AC3** — the biconditional. If written as `if signed_off: assert …` it
    silently passes on the branch it exists to guard. It must compute all five
    booleans and assert they agree, with a message naming the disagreement.
  - **AC13/AC14/AC15** — the injection triple. This is the whole "prove it can
    fail, not just pass" mandate. If AC13 is written over a synthetic set rather
    than a real driver record, it degenerates into a restatement of item 104's
    AC19 and demonstrates nothing new; if AC15 is omitted, a leaked monkeypatch
    can leave the rest of the session's assertions meaningless.
  - **AC5** — the `finally`-restore. Without it, a genuine drift regression turns
    a red test into a *dirty working tree* that the merge step then commits.
  - **AC18** — the partition. Bucket (iii) is the honest shortfall; a test that
    only asserts "every entry has a status" (AC17) would let it disappear.

- **Adversarial / edge cases:**
  - `stage19_signoff_state()` against synthetic `progress.md` fragments: box
    absent → explicit failure naming the heading searched; `- [ ]` with an
    evidence note → `"pending"`; `- [x]` with **no** note → `"pending"` (a bare
    tick is not a sign-off); `- [X]` uppercase with a note → `"signed-off"`;
    the note on a *wrapped continuation line* → `"signed-off"`; a note naming a
    different document → `"pending"`.
  - AC3 fed a synthetic tracker in each mixed state (stage ✅ but box 3 pending;
    box 3 signed but stage 📋; box 1 ticked and box 2 not) → fails, naming the
    disagreeing flag. Fed the two consistent states → passes.
  - `iter_committed_entries` on an entry missing `status` or `failure_modes` →
    AC17/AC18 fail naming that entry's `path`, never a `KeyError`.
  - An entry with `status == "unwired"` **and** a non-empty `failure_modes` →
    AC18 fails (buckets must be disjoint; this combination would mean the
    attribution disagrees with itself).
  - `N == 0` (an empty catalogue) → AC8 fails on the `N > 0` floor rather than
    every downstream check passing vacuously.
  - AC9 with a catalogue group whose title contains HTML-special characters →
    the rendered section escapes it and still contains the entry path
    (`tests/test_aide_status_report.py::test_render_escapes_untrusted_titles` is
    the existing precedent to follow).
  - The injection applied twice in one session, and the drift check run twice
    after the revert → identical results both times (idempotence; catches a
    driver-record cache that survives the monkeypatch teardown).
  - A non-`CatalogueError` exception raised by a stub build function → must
    propagate out of `strict_build_message`, not be swallowed into a tidy drift
    message (item 104's contract; re-asserted here because AC14 depends on it).
  - `normalise_leaf_path` given an `extended` key that is itself a bare integer,
    and given a path with **both** an integer `per_label` key and an `extended`
    key → AC12's collapse still yields exactly one path, with no bare-integer
    segment.

- **Determinism / platform hygiene.** This module performs **no** byte-hash
  scope fence and hard-codes **no** absolute path. The only `read_bytes()` in it
  are AC5/AC6/AC7's comparisons of the two generated artifacts against
  themselves — both LF-pinned by item 103's AC20 — and the AC5 snapshot/restore.
  Before writing any file-content assertion, read the three `insights.md`
  entries from items 099–101: the hard-coded `/mnt/data/...` sandbox path, the
  missing `.gitattributes` LF pins, and the `str(path.relative_to(base))` vs
  `as_posix()` separator bug. Each was Linux-green, Windows-red, and invisible to
  every gate in this loop; two of the three reached `main`.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate). This item changes no default, threshold or behaviour, and edits
  only `progress.md`, so the sweep is expected to be inert — but **confirm
  rather than assume**, since a stale assertion here costs a guaranteed extra
  validation round:
  - **Any test that parses or asserts on `docs/aide/progress.md`.** This is the
    one file this item edits, and it is the highest-risk sweep. `grep -rn
    "progress.md" tests/` — at authoring time
    `tests/test_aide_status_report.py` parses the real `progress.md`
    (`test_build_report_model_on_real_docs`, `test_parse_progress_extracts_stages_and_statuses`,
    `test_parse_phases_maps_stages_to_phases`) via a status/emoji parser. Ticking
    two acceptance boxes, flipping a stage heading to ✅ and a summary row to ✅
    must leave every one of those green **unmodified**; if any asserts a *count*
    of stages in a given status, it will move and must be reconciled **before**
    the edit, not after. Item 105's AC12 also reads that same Stage-19
    acceptance list — this item must not disturb the line it reads (AC2).
  - `tests/test_103_feature_catalogue.py` — owns the generator AC-by-AC; this
    item replays AC19/AC21/AC23/AC24 at artifact level and imports its AC16
    injection seam read-only.
  - `tests/test_104_feature_catalogue_drift.py` — its module-level helpers are
    **imported** here, not copied. Confirm they are module-level functions (not
    fixtures) and that importing the module has no side effects; a second copy
    of `drift_report` would be exactly the drift item 103's spec warns about.
  - `tests/test_105_golden_decision_table.py` — its AC12 three-branch test on
    the sign-off checkbox and this item's AC1/AC3 read the same lines from
    opposite sides. Both must be green simultaneously in the signed-off state.
  - `tests/test_042_golden_determinism.py`, `tests/test_089_*`,
    `tests/test_090_*`, `tests/test_094_*`, `tests/test_098_*` — the nine
    goldens' consumers. AC22 asserts the goldens still exist; nothing here may
    require an edit to any of them.
  - `tests/test_099_per_mode_metrics.py`, `tests/test_100_severity_ladder.py`,
    `tests/test_101_*.py`, `tests/test_102_stage18_validation.py` — each carries
    a `_PRE_NNN_*` scope fence over `src/segfacet/**`. Because AC23 asserts no
    production file is touched, **all** of them must continue to match; a
    failure there means this item went out of scope. (The standing
    `insights.md` entry about these fences breaking when a later item is
    *legitimately* authorised to edit a pinned file does not apply here — this
    item is authorised to edit nothing under `src/segfacet/**`.)
  - `tests/test_aide_status_report.py` — AC9/AC10 exercise the same by-path
    module load and `render_html`; no change expected there.

## Validation

The point of a stage validation is **observed** behaviour, so the validator must
execute this section rather than only re-run the suite. From the repo root with
the venv bootstrapped (`python .aide/scripts/aide.py env --bootstrap` if not —
never record a step as unverified because the venv was missing).

**0. The gate. Do this first, before anything else.** Open
`docs/aide/progress.md`, read the Stage-19 acceptance item containing *"golden
decision table is complete and signed off"*, and read
`docs/aide/golden-decision-table.md`. If the box is not `- [x]` with an italic
evidence note naming that document: **stop here**, hand back *"Stage 19 not
ready to close: golden-decision-table sign-off pending"*, and do nothing else.
Approval is the recorded checkbox and nothing else — not the table's
completeness, not a green suite, not a maintainer's silence, and not this
agent's judgment that the dispositions look right.

**1. Regeneration moves nothing.**

```
.venv/bin/python -m segfacet.catalogue
```
```
git status --short docs/aide/
```

Expected: no output from the second command — the committed artifacts already
match a fresh regeneration (AC5 in its live form). Any diff here means the
committed artifacts and the code disagree and the stage is not closeable;
regenerating and committing the difference is **item 103's** business, not a
tidy-up to do inside this item.

**2. The three sibling modules are green with zero skips.**

```
.venv/bin/python -m pytest tests/test_103_feature_catalogue.py tests/test_104_feature_catalogue_drift.py tests/test_105_golden_decision_table.py -ra
```

Expected: all pass, summary reports **0 skipped** (item 104 AC1's ungatedness in
its live form).

**3. The real-source drift rehearsal — the only step that literally shows CI
failing.** Insert one key into the per-label geometry dict built by
`src/segfacet/feature_report.py` (item 104's Validation step 2 names the exact
shape: `"zzz_drift_probe": 0.0`), then:

```
.venv/bin/python -m pytest tests/test_104_feature_catalogue_drift.py -ra
```

Expected: the direction-1 test **and** the strict-mechanism test both fail, and
both failure texts contain `per_label.{label}.geometry.zzz_drift_probe`, the
literal `src/segfacet/feature_docs.py`, and the literal
`python -m segfacet.catalogue`. **Transcribe the failing test ids and the
verbatim first failure line into this spec's `### Real-source drift rehearsal`
heading** (AC16). Then:

```
git checkout -- src/segfacet/feature_report.py
```
```
git status --short
```

Expected: clean, and step 2 green again. **A validation run that leaves a probe
in the tree is a failed validation.** If for any reason the rehearsal cannot be
executed, record the literal words `not executed` under that heading with the
reason, and say so on checkbox 1 — never upgrade an unexecuted rehearsal to an
observed one.

**4. The steering review itself.** Regenerate the status report and read it:

```
.venv/bin/python scripts/aide_status_report.py --out <tmp>/status.html
```

Open the Feature Catalogue section and confirm by inspection: every entry shows
a status; every `keep` entry names at least one consuming rule or non-rule
consumer; every `unwired` entry names none; the §6-mode column is populated for
the paths item 099's eight metrics anchor. Then read
`docs/aide/feature_catalogue.generated.md`'s `unwired` block specifically and
sanity-check that each entry really is unread — this is the Stage-19 human
review in its final form, and the measured expectation is a **substantial**
unwired tail (~34 of 67 record-tier paths on item 103's prototype). A near-empty
unwired list means the attribution is over-matching, not that the feature set is
healthy; record that as a finding rather than as a pass. Any keep/retune/retire
judgment this reading produces goes to `docs/aide/insights.md` for
queue-boundary triage — **not** into `STATUS_OVERRIDES`, which is production
code outside this item's fence.

**5. The environment observation.**

```
python .aide/scripts/aide.py env --profile pyradiomics
```

Record the exit status and message in the Decisions log either way. **No
`[validation]` profile is required for this item** — every step above runs on
the plain CPU venv with no optional dependency, so nothing here may be recorded
`❓ Unverified` for environment reasons. The profile is consulted only to
strengthen AC12's structural argument: **if** it is satisfied, additionally
re-run step 2 with PyRadiomics importable and confirm item 104's module is still
green, which upgrades "the covered set is backend-invariant" from argued to
observed. If it is not satisfied, the structural argument stands on AC12 alone
and no verification row is added (AC21).

**6. Full suite and tracker check.**

```
.venv/bin/python -m pytest
```
```
python .aide/scripts/aide.py check
```

Expected: green, and a consistent tracker after the `progress.md` edits — in
particular no objective rolled up to ✅ over an unmet outcome target (G7 and G8
must remain 🚧 and 📋 respectively).

**CI observation.** If a live GitHub Actions run can be observed for this
stage's merged tree, record it naming the **observation channel** and the
commits covered, exactly as item 102's AC23 requires (job/check-run conclusions
via the unauthenticated REST API are *not* raw pytest logs, and must not be
reported as if they were). If re-observation is impossible from the execution
environment — item 102's actual outcome — record that honestly instead. In
neither case is a green CI run asserted without a named channel.

## Dependencies

- **Item 103** (`src/segfacet/catalogue.py`'s `normalise_leaf_path` /
  `iter_leaf_paths` / `iter_driver_records` / `build_catalogue` /
  `catalogue_to_dict` / `render_markdown` / `main`, `src/segfacet/feature_docs.py`'s
  `FEATURE_DOCS` and `STATUS_OVERRIDES`, the two committed
  `docs/aide/feature_catalogue.generated.*` artifacts, and the rewritten
  `scripts/aide_status_report.py` render path) — must be ✅. Blocks AC5–AC10,
  AC12, AC17, AC18.
- **Item 104** (`tests/test_104_feature_catalogue_drift.py`'s module-level
  helpers `covered_paths` / `drift_report` / `strict_build_message` /
  `load_committed_catalogue` / `iter_committed_entries`) — must be ✅. Blocks
  AC11, AC13–AC15.
- **Item 105** (`docs/aide/golden-decision-table.md` and, decisively, the
  Stage-19 sign-off checkbox it ticks on explicit human approval) — must be ✅,
  **and its sign-off must be recorded**. A merged-but-unsigned item 105 is
  precisely the state in which this item halts (Implementation Step 0).
- **Item 102** (the Stage-18 closer whose structure, honest-shortfall
  annotation style, verification-row discipline and CI-observation strength rule
  this item follows) — ✅.

**Downstream:** Stage 20's traceability/specificity harness inherits this item's
measured `unwired` count and its bucket-(iii) mode-unmapped count as its
starting backlog, and is the stage that would close both. Stage 21
(`roadmap.md`'s *"Act on Stage 19's golden decision"*) is what actually executes
the `retire` dispositions item 105 recorded. Neither blocks this item.

## Decisions & Trade-offs

To be updated during implementation. Recorded by the spec author where the queue
or a sibling spec left the choice open:

- **The gate is a biconditional, not a precondition check.** A one-way "if
  pending, stop" lives only in the agent's behaviour and evaporates the moment
  the item finishes. Writing it as *"stage ✅ and boxes 1/2 ticked **iff** box 3
  signed off"* (AC3) puts the coupling in CI permanently, so a later hand edit
  that unticks the sign-off while leaving Stage 19 closed is a red test rather
  than a silent inconsistency nobody re-reads. It also makes the honest outcome
  (everything unticked) a *passing* state, which is the property item 105's AC12
  established for the same checkbox and which this spec deliberately preserves:
  the honest outcome must never be the failing one.
- **Halt at step 0 rather than land a partial stage validation.** See
  Assumptions. The alternative marks item 106 done while its deliverable — a
  closed, honestly-annotated stage — does not exist.
- **Two rehearsals at two strengths, and the spec refuses to conflate them.**
  The hermetic injection (AC13–AC15) is repeatable and CI-visible but patches a
  seam; the real-source rehearsal (AC16 + Validation step 3) is the literal
  demonstration but cannot be a test, because a test that edits tracked source
  and reverts it corrupts the working tree on its own failure path. AC20
  requires both to be reported, each at its own strength — the same discipline
  item 102's AC23 applied to its CI-observation claim.
- **No byte-hash scope fence** (AC2, AC23 are git-diff obligations). Items
  099–101 shipped three of these and produced three Windows-only CI breaks that
  passed every gate in this loop and were found only by a human reading the
  Actions tab; item 104's spec rejected the pattern outright for the same
  reason. A git-diff check is cheaper, exact, and cannot rot.
- **The catalogue's `unwired` tail and the mode-unmapped bucket are reported as
  findings, not smoothed away.** Item 103's spec is explicit that ~half the
  feature surface being `unwired` is the *correct* output of this stage and
  precisely the signal Stage 20 exists to act on. The temptation at a
  stage-closing item is to present a clean number; AC18/AC19 make the untidy
  partition mandatory instead.
- **No Environment-Gated row is added.** Argued structurally (AC12: the
  `extended.{radiomic}` collapse makes the covered set backend-invariant) and
  observed opportunistically (Validation step 5). Adding a decorative
  `❓ Unverified` row for a capability the stage does not actually gate on would
  dilute a table whose value is that every row means something.
- **`STATUS_OVERRIDES` is left empty and the review's judgments go to
  `insights.md`.** Populating it is a production-code edit, and the honest
  reading of item 103's spec is that the override map is a *mechanism* Stage 19
  delivers rather than a map Stage 19 must fill. Flagged in Assumptions for the
  maintainer to overturn with a follow-up item if they want the judgments
  captured as statuses.

### Real-source drift rehearsal

To be recorded during Validation step 3 — either the observed transcript
(failing test ids, the verbatim first failure line containing
`zzz_drift_probe`, and confirmation that `git status --short` was clean after
the revert) or the literal words `not executed` with the reason. **Do not write
a predicted transcript here.**
