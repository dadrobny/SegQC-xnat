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
> shortfall named rather than smoothed over; and, per the maintainer's
> **2026-07-27 amendment**, *judged* here as well — the steering review's real
> keep/retune/retire calls are recorded in `STATUS_OVERRIDES` by this item)
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

### The honest shortfalls this item must record, not paper over

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
- **~~`STATUS_OVERRIDES` ships and stays empty…~~ — SUPERSEDED by the
  2026-07-27 amendment.** As originally authored, this item left item 103's
  empty override map untouched, so the judgment half of the four-value
  vocabulary would have shipped **unexercised**. The maintainer overturned that:
  *"Populate now — fold real judgments into item 106."* Stage 19 must leave
  behind not only the mechanism (catalogue + drift test + decision table) but a
  genuinely **reviewed** feature set. The override map is now in scope — see
  *The steering review's output* below and **Block F (AC25–AC31)**. The residual
  honest shortfall is narrower and different in kind: **the review's coverage is
  as good as one live walkthrough of the generated catalogue, and no more**, and
  if the maintainer's call is that everything stays at its derived status then
  `STATUS_OVERRIDES` legitimately stays empty — that outcome is a *result*, not
  a skipped step, and AC25 makes the difference between the two visible.

### The steering review's output — the 2026-07-27 amendment

**Maintainer's ruling, settled, do not re-litigate:** *"Populate now — fold real
judgments into item 106."* Stage 19's whole point is the human steering review;
the override map **is that review's output artifact**, not incidental code. A
stage that shipped the mechanism and deferred every judgment to a hypothetical
follow-up item would have reviewed nothing.

**The scope fence is therefore widened by exactly one file and one name.** This
item may edit **`src/segfacet/feature_docs.py`, and within it only the
`STATUS_OVERRIDES` mapping** (plus that mapping's own adjacent comment or
docstring), writing real `(status, rationale)` entries. **This is the one and
only exception to the "no production code" rule a stage-validation item would
normally carry**, and it is justified on exactly one ground: `feature_docs.py`
is item 103's *authored-data* module — pure, stdlib-only, imports nothing from
`segfacet` (item 103 AC2) — and `STATUS_OVERRIDES` is the slot item 103
deliberately left empty *for this review to fill* (item 103's Assumptions:
*"item 105/106's review populates the map"*). Writing into it is recording a
human judgment in the place the design put for it; it is not implementing
behaviour. Everything else in `src/segfacet/**` and everything in `scripts/**`
remains **hard out of bounds** (AC31), and the widening does **not** extend to
`FeatureDoc`, `FEATURE_DOCS`, `BLOCK_OWNERS`, `PATH_ALIASES`,
`MODE_ANCHOR_PATHS`, the module's imports, or any other module.

Two consequences follow mechanically and are specified in Block F: the two
committed artifacts must be **regenerated and committed** after the edit so item
103's AC19 byte-reproducibility holds at the new content (AC30), and item 104's
drift check must still be green — **an override may not create drift**, because
it changes a status, never a path set (AC30).

**Which features get overridden is decided at execution, not here.** The
judgments require a human reading `docs/aide/feature_catalogue.generated.md` line
by line, and that has not happened. This spec therefore pins the *procedure*
(Validation step 4b: a live walkthrough with the maintainer, their calls
recorded verbatim) and **fabricates no disposition**. A spec-author-invented
`retune`/`retire` list would be precisely the self-granted judgment the rest of
this item exists to prevent.

**How this interacts with G8's acceptance bar.** G8's mechanical bar is
**unchanged**: *"every feature carries a status and a named failure mode, or is
marked `unwired`"*, measured on the committed artifact by AC17/AC18. The
overrides are **additive value beyond that minimum**, not a new hurdle. Three
reasons. (a) Making the tick conditional on "at least one feature was judged
`retune`/`retire`" would make the honest outcome — a reviewer who correctly
concludes nothing needs retuning — the *failing* one, the exact inversion this
spec already refuses in the AC3/AC12 sign-off design; the honest outcome must
never be the failing one. (b) The number of overrides is a property of the
feature set's *health*, not of its *documentedness*, and G8 measures the latter.
(c) The load-bearing fact — that a human actually looked — is not lost by
leaving the bar alone, because the **evidentiary** bar is raised instead:
checkbox 2's annotation must now state how many entries were presented and what
the review returned (AC19(c) as amended), so a tick can never be read as "nobody
reviewed this". Bar unchanged, evidence strengthened.

**This is not item 105's review, and item 105's scope does not move.** The two
share a pattern — a human judgment recorded where the loop can see it — and
nothing else. Item 105 judges **golden files** (keep/retire per committed
snapshot), writes `docs/aide/golden-decision-table.md`, and ticks `progress.md`'s
Stage-19 **checkbox 3**, which is about that table and is entirely unrelated to
`STATUS_OVERRIDES`. This item judges **features** (retune/retire per catalogue
path) and writes `feature_docs.py`. Different objects, different documents,
different attestations. In particular: item 105 remains **golden-only**, still
adds nothing under `src/segfacet/`, and still owns checkbox 3 alone; this item
still never writes checkbox 3 (AC2, unchanged), and the feature review gets **no
sign-off checkbox of its own** — its attestation is AC25's transcript plus
checkbox 2's annotation. Conflating the two — e.g. treating checkbox 3's
sign-off as covering the feature judgments, or gating the overrides on it — is a
spec error.

### What this item is NOT

- **Not new production code, with exactly one named exception.**
  `scripts/**` is untouched, and `src/segfacet/**` is untouched **except** for
  `feature_docs.py`'s `STATUS_OVERRIDES` mapping (AC23/AC31, and the amendment
  section above). Otherwise this item adds one test module, edits `progress.md`,
  and commits the regenerated catalogue artifacts. Item 097 (the Stage-17
  closer) did end up changing production code because one of its ACs could not
  otherwise pass; **that** remains a **hand-back signal** here — the widening
  authorises one mapping, not a precedent for widening again.
- **Not the sign-off.** It reads box 3; it never writes it (AC2).
- **Not acting on item 105's retire decisions.** No golden file is deleted,
  regenerated, moved or replaced, and no test that consumes one is edited.
  **Stage 19 decides; Stage 21 executes** (`roadmap.md`'s Stage-21 deliverable
  *"Act on Stage 19's golden decision"*, mirrored by `progress.md`'s Stage-21
  bullet). AC22 makes this mechanical, following item 102's precedent of being
  careful that a stage-closing edit cannot be read as claiming a later stage's
  work is done.
- **Not a fix for the shortfalls above**, and not Stage 20's traceability /
  specificity harness. In particular, recording a `retune`/`retire` judgment is
  **not** acting on it: no threshold is retuned, no extractor is deleted, no
  feature stops being computed. The override records the call; Stage 20/21
  execute it, exactly as Stage 19 decides and Stage 21 executes for the goldens.
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
  plus the count of entries whose status is `retune` and the count whose status
  is `retire`, are written verbatim into this item's Decisions log and into
  checkbox 2's annotation. **Amended 2026-07-27:** those last two counts are no
  longer expected to be `0`; their sum must equal `len(STATUS_OVERRIDES)`
  exactly (AC26 restricts overrides to those two values, so nothing else can
  produce them), and the `keep` bucket is correspondingly reduced. A
  `retune`/`retire` count that disagrees with `len(STATUS_OVERRIDES)` means the
  committed artifact was not regenerated after the override edit — see AC29.

- [ ] **AC19: checkbox 2, if ticked, carries the honest partition.** If
  `progress.md`'s Stage-19 acceptance item containing `Every feature carries a
  status` is `- [x]`, its italic annotation states, in this order: (a) every one
  of the `N` entries carries a status from the four-value vocabulary; (b) the
  three bucket counts from AC18, naming bucket (iii) **explicitly as a shortfall
  against the criterion's literal wording** whenever its count is `> 0`, with
  `mode_evidence == ("rule_unmapped",)` as its cause and Stage 20 as its closer;
  (c) **[amended 2026-07-27]** the steering review's outcome — how many `keep`
  and `unwired` entries were presented to the maintainer at Validation step 4b,
  and either the `retune` and `retire` counts now carried by
  `STATUS_OVERRIDES` **or**, when that map is empty, the explicit statement that
  the walkthrough was performed and the maintainer's call was that every entry
  stays at its derived status (never silence; and the pre-amendment wording
  *"the judgment half of the vocabulary is unexercised"* may be used **only** if
  the walkthrough genuinely did not happen, with the reason); (d) that all
  of it is measured on in-package synthetic driver records and the committed
  artifact, not on real data — and that a `retune`/`retire` status **records** a
  judgment rather than executing it (Stage 20/21 execute). (Written as
  tick-implies-evidence so it composes with AC3 rather than becoming a landmine
  on an unticked tree.)

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
  naming Stage 21 as the closer of the retire dispositions. **[Amendment note,
  2026-07-27 — the fence itself is unchanged; only its wording is disambiguated:]**
  that sentence is about the **golden-file** retire dispositions item 105
  recorded, which is what `roadmap.md`'s Stage-21 deliverable names. Any
  **feature** `retire` this item records in `STATUS_OVERRIDES` must **not** be
  attributed to Stage 21 in the same breath — no document assigns it a closer
  yet, and inventing one would be exactly the "claiming a later stage's work is
  done" failure this AC exists to prevent. If both are mentioned, they are
  mentioned as two distinct dispositions with two distinct (one absent) closers.

- [ ] **AC23: the scope fence holds — one new test module, one named production
  mapping, nothing else.** *(File list widened by the 2026-07-27 amendment; the
  narrowing clauses are unchanged.)* `git diff --name-only <merge-base>..HEAD`
  lists **only** these paths:
  1. `docs/aide/items/106-validate-stage19.md`
  2. `tests/test_106_stage19_validation.py`
  3. `docs/aide/progress.md`
  4. **`src/segfacet/feature_docs.py`** — *the one production file, restricted
     to `STATUS_OVERRIDES` by AC31.* Absent from the diff **iff** the review
     recorded no override (AC25's honest-empty branch).
  5. **`docs/aide/feature_catalogue.generated.json`** and
     **`docs/aide/feature_catalogue.generated.md`** — the regenerated artifacts
     (AC30). Present **iff** (4) is present; a diff carrying (4) without these,
     or these without (4), is a fail.
  6. optionally `docs/aide/insights.md`
  7. optionally, and **only** if item 105's AC14 shipped a whole-tree
     `src/segfacet/**` digest that (4) invalidates: the single pinned-digest
     constant in `tests/test_105_golden_decision_table.py` — see the Testing
     Strategy's "existing tests to reconcile" entry and Assumptions. No other
     line of that module may move, and the re-pin must carry a comment naming
     item 106's authorisation, following the `_PRE_100_HASHES` precedent
     (`tests/test_100_severity_ladder.py:947-949`).

  **Nothing else.** In particular: no other file under `src/segfacet/**`,
  nothing under `scripts/**`, no other file under `tests/**`, nothing under
  `tests/corpus/**`, and none of `docs/aide/golden-decision-table.md`,
  `docs/aide/roadmap.md`, `docs/aide/vision.md`, `.github/**`, `.gitattributes`.
  Verified by the validator from that diff, **not** by a byte-hash pytest — see
  Decisions & Trade-offs.

- [ ] **AC24: closing Stage 19 moves no objective and no outcome row.**
  `progress.md`'s Objective-coverage rows for **G7** (`🚧`) and **G8** (`📋`)
  are byte-identical to their pre-106 state; the entire Outcome-targets table is
  byte-identical; the "Real automatic-segmentation failure corpus" row still
  reads `❓ Unverified` and still names Stage 16 as its closer; and no sentence
  this item adds anywhere in `progress.md` asserts real-data coverage for
  anything Stage 19 delivers.

### Block F — the steering review's judgments (added by the 2026-07-27 amendment)

> Block F is what turns Stage 19 from "the mechanism shipped" into "the feature
> set was reviewed". It is the only part of this item authorised to touch
> production code, and the authorisation is exactly one mapping (AC31).
> **No minimum number of overrides is required** — see AC25.

- [ ] **AC25: the steering review is performed live and transcribed at its true
  strength.** This spec's Decisions & Trade-offs section contains a heading
  `### Stage-19 steering review` under which is recorded: the date; the number
  of committed-catalogue entries presented to the maintainer, split `keep` /
  `unwired`; and **either** (a) one line per recorded override — the catalogue
  `path`, the chosen status (`retune` or `retire`), and the rationale string
  verbatim — **or** (b) the literal words `no override recorded`, together with
  the maintainer's stated reason (e.g. every entry's derived status was
  confirmed correct). A test asserts the heading exists and that, when
  `STATUS_OVERRIDES` is non-empty, the text below it contains **every** override
  key verbatim; and when `STATUS_OVERRIDES` is empty, that it contains the
  literal `no override recorded`. **No minimum override count is imposed:** a
  review that legitimately concludes everything stays `keep`/`unwired` passes
  this AC, because making a non-empty map mandatory would reward inventing a
  judgment. What fails this AC is skipping the walkthrough, or recording a
  disposition the maintainer did not make — the same discipline AC16 applies to
  the drift rehearsal.

- [ ] **AC26: every override is well-formed and carries a real rationale.** For
  every `(path, value)` in `segfacet.feature_docs.STATUS_OVERRIDES`: `value` is a
  2-tuple `(status, rationale)`; `status` is exactly `"retune"` or `"retire"` —
  **never** `"keep"`, **never** `"unwired"`, never any other string; `rationale`
  is a `str` whose `.strip()` is non-empty and at least 20 characters, and which
  is not merely a restatement of the status (it does not equal `status`, and it
  is not one of `"retune"`, `"retire"`, `"n/a"`, `"TBD"`, `"see review"`).
  Restricting the vocabulary to the two *judgment* values is load-bearing, not
  fussiness: an `unwired` override would break item 103's AC8 biconditional
  outright (*`status == "unwired"` **iff** no consuming rules, no consumers
  **and** no override* — an override forces the right-hand side false while the
  left stays true), and a `keep` override is at best a no-op and at worst masks
  the derived `unwired` signal that Stage 20 exists to act on. Both are
  therefore forbidden rather than merely discouraged.

- [ ] **AC27: every override key names a real catalogue path.** Every key of
  `STATUS_OVERRIDES` is present in `FEATURE_DOCS`, and appears as the `path` of
  **exactly one** entry of `build_catalogue()` **and** of exactly one entry of
  the committed `docs/aide/feature_catalogue.generated.json`. A key matching no
  entry fails this AC naming that key, rather than silently applying to nothing.
  (Item 103's AC17 guards `FEATURE_DOCS` against staleness in both directions;
  nothing in item 103 guards `STATUS_OVERRIDES`, so this item does — otherwise a
  path renamed by a later item would quietly discard a human judgment.)

- [ ] **AC28: an override changes `status` and nothing else — derived facts stay
  derived.** Demonstrated hermetically, with `STATUS_OVERRIDES` monkeypatched (a
  `MappingProxyType` over a test-local dict; the shipped mapping is never
  mutated) to `{p: ("retire", "<test-only probe rationale, ≥20 chars>")}` for
  two separately-parametrised choices of `p` — one path whose committed status is
  `keep` and one whose committed status is `unwired`. In each case
  `build_catalogue()`'s entry for `p` has `status == "retire"` while **every
  other field** of that entry — `consuming_rules`, `rule_evidence`,
  `failure_modes`, `mode_evidence`, `consumers`, `origin`, `documented`, and all
  four `FeatureDoc` prose fields — is **equal to the un-overridden build's**, and
  **every other entry in the catalogue** is equal to its un-overridden
  counterpart field-for-field. `consuming_rules`, `failure_modes` and the
  evidence tuples are *measurements*; `status` (with its rationale) is the
  *human judgment*. An override that rewrote a measurement would make the
  catalogue lie about what the code does, which is the one thing item 103's whole
  derivation exists to prevent.

- [ ] **AC29: the mechanism is demonstrably live, whether or not the review
  produced an override.** AC28's injection runs **unconditionally** — it is the
  proof that `build_catalogue()` actually reads `STATUS_OVERRIDES`, and it must
  fail if the map is ignored, so the mechanism is exercised in the suite even on
  the honest-empty branch of AC25. **Additionally**, if `STATUS_OVERRIDES` is
  non-empty on the committed tree, then for every key: the entry for that path
  in the **committed** `feature_catalogue.generated.json` carries exactly the
  override's status, and the corresponding row's `status` column in the committed
  `.md` reads the same — proving the shipped artifacts were regenerated *after*
  the edit rather than left stale.

- [ ] **AC30: the artifacts are regenerated after the override edit, and neither
  reproducibility nor drift-freedom regresses.** After the `feature_docs.py`
  edit, `python -m segfacet.catalogue` is run and both regenerated artifacts are
  committed. On the resulting tree: **AC5, AC6 and AC7 hold** (item 103's AC19
  byte-reproducibility re-established at the new content — the *committed*
  artifacts equal a fresh regeneration and a live `build_catalogue()`); **AC11
  holds** — all four of item 104's drift directions report `None` and
  `strict_build_message(functools.partial(build_catalogue, strict=True))`
  returns `None`, because an override changes a status and never a path set, so
  **an override that creates drift is a bug, not an expected cost**; `AC8`'s
  entry count `N` is **unchanged** by the override edit; and
  `git status --short docs/aide/` is empty when the item finishes.

- [ ] **AC31: the production-code widening is exactly one mapping, and the
  validator proves it.** From `git diff <merge-base>..HEAD --
  src/segfacet/feature_docs.py`: every hunk falls inside the `STATUS_OVERRIDES`
  assignment or its immediately adjacent comment/docstring; the source text of
  `FeatureDoc`, `FEATURE_DOCS`, `BLOCK_OWNERS`, `PATH_ALIASES` and
  `MODE_ANCHOR_PATHS` is byte-unchanged; the module's import statements are
  unchanged, so item 103's AC2 stdlib-only contract still holds (re-asserted in
  this item's suite by the same AST import scan item 103 uses); and
  `STATUS_OVERRIDES` is still wrapped in `types.MappingProxyType`. No other file
  under `src/segfacet/**` and no file under `scripts/**` appears in the diff at
  all. A git-diff obligation on the validator, **not** a byte-hash pytest — for
  the reason in Decisions & Trade-offs, which this very amendment demonstrates
  once more.

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
- *[103 Assumptions]* **`STATUS_OVERRIDES` ships empty** from item 103 — but
  **[amended 2026-07-27]** this item is now the one that fills it, so
  `retune`/`retire` counts are **not** expected to be `0`; they equal
  `len(STATUS_OVERRIDES)` after the steering review (AC18/AC26), which may
  legitimately still be `0` if the maintainer's call is that nothing needs
  retuning. Item 103's own wording anticipates this exactly (*"item 105/106's
  review populates the map"*), so filling it is completing item 103's design,
  not overriding it. Also **a large `unwired` tail is the correct
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
  Stage 19's planned work ships and is verified; the residual shortfall is in the
  *measured outcome* for one entry class (bucket (iii), the mode-unmapped rules)
  and in the review's coverage being one live walkthrough and no more.
  **[Amended 2026-07-27:]** the second shortfall as originally written — *"an
  unexercised half of the vocabulary"* — no longer applies, because the judgment
  half is now exercised by a real review (AC25) and by the unconditional
  mechanism test (AC28/AC29). This tracker's "Two kinds of done" rule (`progress.md:58-77`) says
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

**Settled by the maintainer on 2026-07-27 — the one question this spec flagged,
now answered:** *may the Stage-19 steering review populate `STATUS_OVERRIDES`?*
**Yes — "Populate now — fold real judgments into item 106."** The maintainer's
stated reasoning: Stage 19 should leave behind not just the mechanism
(catalogue + drift test + decision table) but a genuinely reviewed feature set —
real keep/retune/retire judgments, not an empty override map deferred to a
hypothetical follow-up item. The pre-amendment answer (*no; route judgments to
`insights.md`; a new item if the maintainer wants otherwise*) is **superseded and
must not be reinstated by a downstream agent reading a stale copy.**

Consequences, all now specified rather than assumed:

- The scope fence is widened by **exactly one file and one name** —
  `src/segfacet/feature_docs.py`'s `STATUS_OVERRIDES` (AC23 item 4, AC31). It is
  the single exception to a stage-validation item's normal "no production code"
  rule, justified because that mapping is the review's *output artifact*, not
  incidental code, and item 103 left it empty expressly for this review.
- **Which** paths get overridden is **not decided in this spec** and must not be.
  It is an execution-time step: Validation step 4b walks the committed
  catalogue's `keep` and `unwired` entries with the maintainer live (via
  `AskUserQuestion` or equivalent) and records their calls verbatim (AC25). A
  spec-author-invented disposition list would be a fabricated human judgment.
- **G8's mechanical acceptance bar is unchanged**; the overrides are additive
  value and the *evidentiary* bar on checkbox 2 is raised instead (AC19(c)).
  Reasoning in Description § *The steering review's output*, and in Decisions.
- **Item 105's scope does not move.** Golden files vs. features; different
  objects, same review pattern. Checkbox 3 remains item 105's alone and remains
  unrelated to `STATUS_OVERRIDES`; this item still never writes it (AC2).
- **Item 105's AC14 fence may need one re-pin.** Item 105's AC14 asserts pinned
  digests over the **`src/segfacet/**` tree**. If it lands as a whole-tree
  digest, this item's authorised `feature_docs.py` edit breaks it — the third
  recurrence of the pattern `insights.md`'s standing entry describes (*"breaks by
  design the moment a later item is legitimately authorised to touch that same
  file"*), and one item 104's own Decisions section predicted by name. The
  resolution, following the in-repo `_PRE_100_HASHES` precedent, is a **narrow,
  commented re-pin of that one constant** (AC23 item 7) — never a silent edit,
  never a deletion of the test, and never a widening of this item's production
  fence to "un-break" it. If item 105 instead lands a per-file or exclusionary
  digest that survives the edit, no re-pin is needed and `tests/**` stays at one
  new file. Confirm which at execution; do not assume.
- The other `_PRE_NNN_*` fences (items 099/100/101) hash `eval/`, `heuristics/`,
  `features/`, `synth/`, `tests/corpus/` and a short named-file list — **none of
  which includes `feature_docs.py`**, a module that did not exist when they were
  pinned. Verified at authoring time (2026-07-27) by reading their constants;
  they are expected to stay green unmodified. Re-confirm, do not assume.

## Implementation Steps

**[Amended 2026-07-27.]** Exactly **one** change under
`source_dir = src/segfacet` is authorised — `feature_docs.py`'s
`STATUS_OVERRIDES` mapping, and nothing else in that file or that package
(AC31). The rest of the work is one new test module, the two regenerated
catalogue artifacts, and `docs/aide/progress.md`.

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
   - **Block F (AC25–AC31):** the override well-formedness and key-liveness
     checks (AC26/AC27), the unconditional hermetic injection proving the
     mechanism is live and touches only `status` (AC28/AC29), the
     committed-artifact agreement (AC29), the post-regeneration
     reproducibility + drift re-check (AC30, reusing Block B/C's fixtures), and
     the `### Stage-19 steering review` transcript check (AC25).

2. **The steering review and the `STATUS_OVERRIDES` edit** *(added by the
   2026-07-27 amendment)* — done at Validation
   step 4b, *before* the `progress.md` edit, and only after step 0 passed:
   - Walk the committed `docs/aide/feature_catalogue.generated.md`'s `keep` and
     `unwired` entries with the maintainer and record their calls (Validation
     step 4b). **Record only what they say.**
   - For each `retune`/`retire` call, add one `STATUS_OVERRIDES` entry —
     `"<catalogue path>": ("retune"|"retire", "<rationale ≥20 chars>")` — keeping
     the mapping's existing `MappingProxyType` wrapper and key ordering
     convention. **Touch nothing else in `feature_docs.py`** (AC31). If the
     review produces no call, leave the mapping empty and say so in the
     transcript (AC25's branch (b)); do **not** invent an entry to exercise the
     mechanism — AC28's hermetic injection already does that.
   - Regenerate and stage both artifacts (AC30):
     `.venv/bin/python -m segfacet.catalogue`, then confirm
     `git status --short docs/aide/` shows exactly the two generated files
     changed (or nothing at all, if the map stayed empty).
   - Re-run `tests/test_103_feature_catalogue.py` and
     `tests/test_104_feature_catalogue_drift.py` — both must be green
     **unmodified**; a drift failure here means the override changed a path set,
     which it cannot legitimately do (AC30).
   - If item 105's AC14 whole-tree digest now fails, re-pin **only** that one
     constant with a comment naming item 106's authorisation (AC23 item 7) — see
     Assumptions. Anything larger is a hand-back, not a fix.

3. **`docs/aide/progress.md`** — the last edit, made only after step 0 passed
   and after step 2's review is recorded:
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

4. **Record the measurements in this spec's Decisions & Trade-offs** as they are
   observed: `N` (AC8), the three bucket counts and the `retune`/`retire` counts
   (AC18), the `aide env --profile pyradiomics` result (AC21), the
   `### Real-source drift rehearsal` transcript (AC16), and the
   `### Stage-19 steering review` transcript (AC25).

5. **Do NOT touch** — *(list narrowed by the 2026-07-27 amendment only where
   AC23 explicitly widens it; everything below is unchanged and hard)*
   `scripts/**`, **any file under `src/segfacet/**` other than
   `feature_docs.py`**, **any part of `feature_docs.py` other than the
   `STATUS_OVERRIDES` mapping** (AC31), any file under `tests/**` other than the
   new module and — conditionally, per AC23 item 7 — item 105's single pinned
   digest constant, `tests/corpus/**`,
   `docs/aide/golden-decision-table.md`, `docs/aide/roadmap.md`,
   `docs/aide/vision.md`, `.github/**`, `.gitattributes` (AC23). In particular:
   do not delete, regenerate, move or replace any golden; do not retune a
   threshold or delete an extractor because a review said `retune`/`retire`
   (recording the call is this item's job, executing it is Stage 20/21's); and
   do not hand-edit `docs/aide/feature_catalogue.generated.*` — they are only
   ever rewritten by `python -m segfacet.catalogue` (AC7/AC30).

## Testing Strategy

- **Framework:** `pytest`. One new module,
  `tests/test_106_stage19_validation.py`. **No existing test module is
  modified** — `tests/test_103_feature_catalogue.py`,
  `tests/test_104_feature_catalogue_drift.py` and
  `tests/test_105_golden_decision_table.py` must all stay green **unmodified**;
  an edit to any of them is a red flag for the validator, since this item
  changes no *behaviour*. **[Amended 2026-07-27 — the one exception:]** item
  105's AC14 pinned-digest constant may be re-pinned if, and only if, it shipped
  as a whole-tree `src/segfacet/**` digest that this item's authorised
  `feature_docs.py` edit invalidates (AC23 item 7). That is a **constant
  re-pin with an explanatory comment**, not a change to any assertion; no other
  line of that module moves, and it is the *only* circumstance in which an
  existing test module may be touched.

- **One focused test per AC**, AC1–AC31. The load-bearing ones:
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
  - **AC28/AC29 — the hermetic override injection.** This is Block F's
    equivalent of AC13/AC14: the proof that the override *mechanism* is live,
    written so it **does not depend on what the live review decided**. Shape it
    exactly so:
    - `monkeypatch.setattr(segfacet.feature_docs, "STATUS_OVERRIDES",
      types.MappingProxyType({p: ("retire", "<≥20-char probe rationale>")}))`,
      and — because `catalogue.py` may have bound the name at import — also
      patch `segfacet.catalogue.STATUS_OVERRIDES` if the module re-exports it.
      **Read how `build_catalogue` resolves the mapping before writing this**,
      the same discipline AC13 applies to item 103's AC16 seam; if it is inlined
      with no patchable seam, that is a **hand-back to item 103**, not a licence
      to widen this item's production edit.
    - Parametrise `p` over **two** paths taken from the *un-overridden* build at
      runtime — the first `keep` entry and the first `unwired` entry in
      catalogue order — never a hard-coded path literal, which would rot the
      moment the feature surface changes.
    - Assert three things, in this order: (i) the target entry's `status`
      becomes `"retire"` — **this is the assertion that fails if
      `build_catalogue` ignores the map**, and it is the whole point of the
      test; (ii) every *other* field of that entry equals the un-overridden
      build's; (iii) every other entry compares equal field-for-field. (ii) and
      (iii) are what pin "derived facts stay derived".
    - Snapshot `dict(STATUS_OVERRIDES)` before and compare after teardown, as
      AC15 does for `FEATURE_DOCS` — a leaked override would silently
      contaminate every later assertion in the session, including AC17/AC18's
      partition counts.
    - **This test runs unconditionally.** It must not be skipped, xfailed or
      made conditional on `STATUS_OVERRIDES` being non-empty; the honest-empty
      review outcome (AC25 branch (b)) is exactly the case in which it is the
      only evidence the mechanism works at all.
  - **AC26/AC27 — the well-formedness checks.** Both iterate the *shipped*
    `STATUS_OVERRIDES` and are **vacuously true on an empty map**. That is
    correct and deliberate: no minimum count is required. Write them as plain
    loops over `STATUS_OVERRIDES.items()`, never with an `assert
    STATUS_OVERRIDES` precondition, which would turn a legitimate all-`keep`
    review into a red suite.
  - **AC30 — the post-edit re-check.** Reuse Block B's and Block C's fixtures
    rather than duplicating them; the point is that AC5/AC6/AC7/AC11 are
    *re-evaluated on the post-override tree*, not that new equivalents are
    written. If they are duplicated, a later divergence between the two copies
    is invisible.

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
  - **Block F's adversarial set** (each fed to the AC26/AC27/AC28 checks as a
    *synthetic* override map, never written into the shipped one):
    - An override whose status is `"unwired"` → AC26 fails naming the path. This
      is the case that would break item 103's AC8 biconditional, so it must be
      caught by AC26 rather than surfacing as a confusing AC8 failure in item
      103's own module.
    - An override whose status is `"keep"` → AC26 fails. (A no-op at best; at
      worst it masks a derived `unwired` that Stage 20 needs to see.)
    - An override whose rationale is `""`, `"   "`, `"retire"`, `"TBD"`, or a
      19-character string → AC26 fails naming the path and the offending value.
    - An override value that is a bare string rather than a 2-tuple, or a
      3-tuple → AC26 fails with a message naming the path, never a `ValueError`
      from tuple unpacking escaping the test.
    - An override key naming a path absent from `FEATURE_DOCS`, and one naming a
      path present in `FEATURE_DOCS` but absent from the committed JSON → AC27
      fails naming the key in both directions, rather than silently applying to
      nothing.
    - **An empty `STATUS_OVERRIDES`** → AC26 and AC27 pass vacuously, AC28/AC29's
      injection still passes, and AC25 requires the literal `no override
      recorded` in the transcript. This is the honest-review branch and must be
      **green end to end**; a suite that goes red when the reviewer changes
      nothing has inverted the incentive the whole item is built around.
    - The same override applied twice in one session, and `build_catalogue()`
      called twice under it → identical entries both times (idempotence; catches
      an override applied cumulatively or a cached catalogue).
    - An override on a path whose entry is `keep` **with** non-empty
      `consuming_rules` → AC28 still shows `consuming_rules` unchanged. The
      judgment "retire this feature" must not erase the record that a rule
      currently reads it — that record is precisely what makes the retirement
      actionable in Stage 20/21.

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
  invalidate). **[Materially amended 2026-07-27.]** As originally authored this
  sweep was expected to be inert, because the item edited only `progress.md`.
  It is **no longer inert**: this item now edits `src/segfacet/feature_docs.py`
  and rewrites both committed catalogue artifacts, so **any test that pins
  either is live**. Run `grep -rn "STATUS_OVERRIDES\|feature_docs\|
  feature_catalogue.generated" tests/` **before** making the override edit, and
  reconcile before rather than after — a stale assertion here costs a guaranteed
  extra validation round:
  - **`tests/test_105_golden_decision_table.py` — the one genuinely at risk.**
    Its AC14 asserts *"pinned digests … of the `tests/corpus/**` and
    `src/segfacet/**` trees"*. If that lands as a **whole-tree** digest, this
    item's authorised `feature_docs.py` edit breaks it by construction — the
    third recurrence of the pattern `insights.md`'s standing entry describes,
    and one item 104's own Decisions section predicted **by name** (*"exactly
    what item 105/106 will do to `feature_docs.py`'s `STATUS_OVERRIDES`"*). The
    sanctioned resolution is the narrow commented re-pin of AC23 item 7,
    following `tests/test_100_severity_ladder.py:947-949`'s in-repo precedent
    where item 101 re-pinned item 100's `cli.py` hash with a comment naming its
    own authorisation. **Not** sanctioned: deleting the test, weakening its
    assertion, or abandoning the override edit to keep a hash green.
  - **`tests/test_103_feature_catalogue.py` — recheck four ACs specifically.**
    Its **AC7** (every entry's status is in the four-value vocabulary) and
    **AC8** (`unwired` **iff** no consuming rules, no consumers **and** no
    override) are the two the override edit touches. AC8 is a biconditional that
    a `keep`- or `unwired`-valued override would break — which is exactly why
    AC26 restricts overrides to `retune`/`retire`; confirm AC8's realised
    implementation matches its spec's wording before relying on that. Its
    **AC17** (`FEATURE_DOCS`'s key set equals the realised set) and **AC19**
    (committed artifacts equal a fresh regeneration) must both be green after
    the regeneration — AC17 is unaffected (overrides are a separate mapping),
    AC19 is re-established by AC30.
  - **`tests/test_104_feature_catalogue_drift.py`** — its module-level helpers
    are **imported** here, not copied; confirm they are module-level functions
    (not fixtures) and that importing has no side effects (a second copy of
    `drift_report` would be exactly the drift item 103's spec warns about).
    **Additionally now:** it must be green *after* the override edit and
    regeneration, unmodified. An override changes a status, never a path set, so
    a drift failure there is a real bug — investigate it, do not re-pin it.
  - **`scripts/aide_status_report.py`'s consumers** —
    `tests/test_aide_status_report.py` renders from the committed catalogue
    JSON, whose content this item changes. Confirm nothing there asserts a
    literal status string, a `keep`/`unwired` count, or a specific entry's
    rendered text; if it does, that assertion moves with the override edit and
    must be reconciled first.
  - Everything below was surveyed at authoring time and is expected to stay
    green **unmodified** — confirm, do not assume:
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
  - `tests/test_103_feature_catalogue.py` — *(also listed above; the four ACs
    the override edit touches are named there)* — owns the generator AC-by-AC;
    this item replays AC19/AC21/AC23/AC24 at artifact level and imports its AC16
    injection seam read-only.
  - `tests/test_105_golden_decision_table.py` — *(also listed above as the one
    module genuinely at risk)* — its AC12 three-branch test on the sign-off
    checkbox and this item's AC1/AC3 read the same lines from opposite sides.
    Both must be green simultaneously in the signed-off state, and this item's
    override edit must not disturb any assertion of that module **other than**
    AC14's pinned digest, and then only per AC23 item 7.
  - `tests/test_042_golden_determinism.py`, `tests/test_089_*`,
    `tests/test_090_*`, `tests/test_094_*`, `tests/test_098_*` — the nine
    goldens' consumers. AC22 asserts the goldens still exist; nothing here may
    require an edit to any of them.
  - `tests/test_099_per_mode_metrics.py`, `tests/test_100_severity_ladder.py`,
    `tests/test_101_*.py`, `tests/test_102_stage18_validation.py` — each carries
    a `_PRE_NNN_*` scope fence over parts of `src/segfacet/**`. **[Rechecked
    2026-07-27 under the amendment.]** Those fences hash `eval/`, `heuristics/`,
    `features/`, `synth/`, `tests/corpus/` and a short named-file list
    (`cli.py`, `report_schema_v0.json`, the two eval schemas) — **none of them
    covers `feature_docs.py`**, a top-level module that did not exist when they
    were pinned. So all of them are still expected to match, and a failure there
    still means this item went out of scope. This is confirmed by reading their
    constants, **not** assumed: re-verify at execution, because the standing
    `insights.md` entry about these fences breaking when a later item is
    *legitimately* authorised to edit a pinned file **now does apply to this
    item** — just to item 105's whole-tree fence rather than to these five.
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

> **[Amended 2026-07-27 — ordering.]** This step runs **before** the steering
> review, on the *pre-override* tree, and its "no output" expectation is
> unconditional here. The override edit at step 4c then *legitimately* produces
> a diff, which that step regenerates and commits; step 6a re-runs this exact
> check on the post-override tree, where "no output" is required again (AC30).
> The distinction matters: a diff at **step 1** means the tree was already
> inconsistent and is item 103's problem; a diff at **step 6a** means the
> artifacts were not regenerated after the override and is this item's problem.

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

**4a. Reading the rendered catalogue — the agent's own pass, which *prepares*
the walkthrough rather than substituting for it.** Regenerate the status report
and read it:

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
healthy; record that as a finding rather than as a pass.

> **[Amended 2026-07-27.]** The step's last sentence as originally written —
> *"any keep/retune/retire judgment this reading produces goes to `insights.md`
> … not into `STATUS_OVERRIDES`"* — is **superseded**. Step 4a is the agent's
> own read, which prepares the walkthrough; step 4b is where the judgments are
> made, by the maintainer, and they go into `STATUS_OVERRIDES`. `insights.md`
> remains the right home only for findings that are **not** a feature status —
> e.g. "the attribution looks over-matching", or a defect noticed in passing.

**4b. The steering review proper — the live walkthrough. This is the human
checkpoint Stage 19 exists for, and the agent does not have standing to skip it
or to answer for the maintainer.** Present the committed
`docs/aide/feature_catalogue.generated.md`'s entries to the maintainer — via
`AskUserQuestion` or equivalent, in batches small enough to answer (group by
catalogue group, not one 60-way question) — covering **every** `keep` entry and
**every** `unwired` entry. For each, show the path, its derived status, its
`consuming_rules` and its `§6 mode(s)`, and ask whether it stays as derived or
should be marked `retune` or `retire`.

Rules for this step, all load-bearing:

- **Record only what the maintainer says.** A `retune`/`retire` disposition the
  agent inferred, extrapolated, or thought obvious is a fabricated human
  judgment — the same failure mode the sign-off gate exists to prevent (AC25).
- **Ask for a rationale with every non-derived call**, in the maintainer's own
  words, ≥20 characters (AC26). "Looks wrong" is not a rationale; *"z-scored
  against a 12-case reference, so the threshold is noise-dominated"* is.
- **No minimum, and no nudging toward one.** *"Everything stays as derived"* is
  a complete and valid answer, and the agent must not press for an override to
  make the stage look better-reviewed. Record it as AC25 branch (b), literally
  `no override recorded`, with the maintainer's reason.
- **If the maintainer is unavailable**, this step cannot be faked. Record
  `no override recorded` with the reason *"maintainer unavailable at execution;
  walkthrough not performed"*, say exactly that on checkbox 2 (AC19(c)'s
  never-upgrade clause), and hand back for a decision on whether to close the
  stage on that basis — the same discipline AC16 applies to an unexecuted drift
  rehearsal.

Then write the recorded calls into `src/segfacet/feature_docs.py`'s
`STATUS_OVERRIDES` — that mapping and nothing else in that file (AC31) — and
transcribe the whole step into this spec's `### Stage-19 steering review`
heading: date, counts presented (split `keep` / `unwired`), and one line per
override or the literal `no override recorded` (AC25).

**4c. Regenerate and re-verify after the override edit.**

```
.venv/bin/python -m segfacet.catalogue
```
```
git status --short docs/aide/
```

Expected: **exactly** `docs/aide/feature_catalogue.generated.json` and
`docs/aide/feature_catalogue.generated.md` modified — and **nothing** if the
review recorded no override. Any third file here is out of scope. Commit both
alongside the `feature_docs.py` edit (AC30; AC23 items 4–5 require them to
appear together — one without the other is a fail). Then:

```
.venv/bin/python -m pytest tests/test_103_feature_catalogue.py tests/test_104_feature_catalogue_drift.py -ra
```

Expected: green, **unmodified**. Item 104 going red here means the override
changed a path set, which it cannot legitimately do — that is a bug to
investigate, never a hash to re-pin (AC30). Item 103's AC8 going red means an
override used `keep` or `unwired`, which AC26 forbids for exactly this reason.
Finally, confirm the override actually reached the artifacts:

```
grep -n "retune\|retire" docs/aide/feature_catalogue.generated.md
```

Expected: one row per `STATUS_OVERRIDES` entry, and no rows at all when the map
is empty (AC29).

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

**6a. Byte-reproducibility re-established on the post-override tree** (AC30 —
step 1 repeated, now with the override in place):

```
.venv/bin/python -m segfacet.catalogue
```
```
git status --short
```

Expected: **no output** — the committed artifacts match a fresh regeneration
again, item 103's AC19 restored at the new content, and the whole tree clean.
Unlike step 1, a diff here is **this item's** defect: the override edit landed
without its regeneration.

**6b. The checkbox-2 annotation carries the review, not just the counts**
(AC19(c)). Re-read the annotation just written and confirm it states, in the
maintainer's terms rather than the agent's: how many entries were presented
(split `keep` / `unwired`), how many `retune` and how many `retire` calls were
recorded, and — when none were — that the walkthrough happened and returned
nothing rather than that it was skipped. **G8's mechanical bar is unchanged by
the amendment; this annotation is where the strengthened evidentiary bar lives**,
so an annotation that reports counts but not whether a human looked fails AC19.

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
  AC12, AC17, AC18. **[Amended 2026-07-27:]** `STATUS_OVERRIDES` is now a
  **write** target of this item, not only a read one — it also blocks
  AC25–AC31. Two of item 103's realised details become load-bearing here and
  must be **read, not assumed**, at execution: (a) how `build_catalogue`
  resolves the mapping (a module global that `monkeypatch.setattr` can reach, or
  an inlined read with no seam — the latter is a hand-back to item 103, since
  AC28 cannot otherwise be written); and (b) whether `CatalogueEntry` /
  `catalogue_to_dict` / `render_markdown` surface the override's **rationale**
  anywhere. Item 103's AC24 fixes the Markdown columns as exactly nine, with no
  rationale column, and none of its ACs require the rationale in the JSON — so
  the likely realised answer is **no**, and the rationale then lives only in
  `feature_docs.py`'s source. That is acceptable (it is the authored-data module,
  which is where authored prose belongs by item 103's design) and AC26 asserts it
  there. If it *is* surfaced, AC26 additionally checks it round-trips. Either
  way, record which at execution, and if it is not surfaced append one
  `insights.md` line — a human judgment readable only by opening a source file
  is weaker than one printed in the generated catalogue, and closing that gap is
  a Stage-20-shaped follow-on, **not** a licence to widen this item's edit
  beyond `STATUS_OVERRIDES`.
- **Item 104** (`tests/test_104_feature_catalogue_drift.py`'s module-level
  helpers `covered_paths` / `drift_report` / `strict_build_message` /
  `load_committed_catalogue` / `iter_committed_entries`) — must be ✅. Blocks
  AC11, AC13–AC15, and AC30's post-override drift re-check.
- **Item 105** (`docs/aide/golden-decision-table.md` and, decisively, the
  Stage-19 sign-off checkbox it ticks on explicit human approval) — must be ✅,
  **and its sign-off must be recorded**. A merged-but-unsigned item 105 is
  precisely the state in which this item halts (Implementation Step 0).
  **[Amended 2026-07-27:]** a second, purely mechanical coupling now exists —
  item 105's AC14 pinned digest over the `src/segfacet/**` tree, which this
  item's authorised `feature_docs.py` edit may invalidate (AC23 item 7). This
  changes **nothing** about item 105's own scope: it remains golden-only, adds
  nothing under `src/segfacet/`, and still owns checkbox 3 alone — a checkbox
  about the golden decision table that has no relationship to
  `STATUS_OVERRIDES`. Do not conflate the two reviews.
- **Item 102** (the Stage-18 closer whose structure, honest-shortfall
  annotation style, verification-row discipline and CI-observation strength rule
  this item follows) — ✅.

**Downstream:** Stage 20's traceability/specificity harness inherits this item's
measured `unwired` count and its bucket-(iii) mode-unmapped count as its
starting backlog, and — **new under the 2026-07-27 amendment** — inherits the
recorded `retune`/`retire` judgments as a second, sharper backlog: a feature the
maintainer marked `retire` with a stated reason is a stronger Stage-20 input
than an `unwired` count, because a human has already agreed it should go. Stage
21 (`roadmap.md`'s *"Act on Stage 19's golden decision"*) is what actually
executes the `retire` dispositions item 105 recorded **for goldens**; the
*feature* `retire` dispositions this item records have no assigned executor yet
and must not be assumed to be Stage 21's — name that gap on checkbox 2 rather
than implying a closer that no document commits to. Neither blocks this item.

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
- **~~`STATUS_OVERRIDES` is left empty…~~ — OVERTURNED by the maintainer,
  2026-07-27.** The original decision was that populating the map is a
  production-code edit and that the honest reading of item 103's spec makes the
  override map a *mechanism* Stage 19 delivers rather than a map Stage 19 must
  fill; judgments were routed to `insights.md` and a follow-up item was flagged.
  The maintainer's ruling, verbatim: **"Populate now — fold real judgments into
  item 106."** Their stated reasoning: *Stage 19 should leave behind not just the
  mechanism (catalogue + drift test + decision table) but a genuinely reviewed
  feature set — real keep/retune/retire judgments, not just an empty override map
  deferred to a hypothetical follow-up item.* Recorded here in full because a
  downstream agent reading a stale summary must be able to see that the
  restrictive framing was considered, decided against, and by whom.

- **The scope fence is widened by exactly one file and one name, and the
  justification is narrow on purpose.** A stage-validation item touching
  production code is normally a hand-back signal (this spec still says so for
  every other case, following item 097's precedent). The exception holds only
  because `src/segfacet/feature_docs.py` is item 103's **authored-data** module —
  pure, stdlib-only, importing nothing from `segfacet` (item 103 AC2) — and
  `STATUS_OVERRIDES` is the slot item 103 deliberately shipped empty *for this
  review to fill* (*"item 105/106's review populates the map"*). Writing a
  judgment into it is **recording a human decision in the place the design made
  for it**, not implementing behaviour: no extractor, rule, threshold, schema,
  report or CLI path changes, and AC28 proves mechanically that an override
  moves `status` and nothing else. The alternatives were both worse: a separate
  follow-up item would have shipped Stage 19 with its central deliverable —
  the review — unperformed; and a non-code home for the judgments (a fourth
  Markdown document) would have put them where neither `build_catalogue()` nor
  the drift test can see them, guaranteeing they rot. AC31 keeps the widening
  auditable at one mapping, verified from the diff.

- **G8's mechanical bar is left unchanged; the evidentiary bar is raised
  instead.** The alternative considered and rejected: redefine checkbox 2 as
  *"every feature carries a status **and**, where a human judged retune/retire,
  that judgment is captured with rationale"*. Three reasons for leaving it
  alone. (a) It would make the honest outcome the failing one — a reviewer who
  correctly concludes nothing needs retuning would be unable to tick the box —
  which is the exact inversion this spec refuses everywhere else (the AC3/AC12
  sign-off design is built on "the honest outcome must never be the failing
  one"). (b) The override count measures the feature set's *health*; G8 measures
  its *documentedness*. Folding one into the other would make a future clean
  review indistinguishable from a skipped one. (c) The thing genuinely worth
  guaranteeing — that a human actually looked — is captured without touching the
  bar, by AC25's transcript and AC19(c)'s annotation requirement. So: overrides
  are **additive value beyond the minimum**, the tick still means what it meant,
  and the tick can no longer be read as "nobody reviewed this". A future
  maintainer who wants the stronger bar can raise it in the roadmap; this item
  does not raise it unilaterally at the moment it becomes convenient.

- **No minimum override count, deliberately.** Requiring `len(STATUS_OVERRIDES)
  > 0` would create a standing incentive to manufacture a judgment to close a
  stage — the precise failure this item's whole design (AC1–AC4, AC16, AC25) is
  built to prevent. AC26/AC27 are therefore written to pass vacuously on an
  empty map, and the mechanism is instead proven by AC28's **unconditional**
  hermetic injection, which does not depend on what the live review decided.
  Mechanism exercised in CI; judgment left to the human.

- **This review and item 105's are kept structurally separate.** Same pattern
  (a human judgment recorded where the loop can see it), different objects:
  item 105 judges **golden files** into `golden-decision-table.md` and attests
  via checkbox 3; this item judges **features** into `STATUS_OVERRIDES` and
  attests via AC25's transcript plus checkbox 2. The feature review deliberately
  gets **no checkbox of its own** — inventing a fourth acceptance box would
  change Stage 19's roadmap-defined acceptance list, which a stage-*validation*
  item has no standing to do. Item 105's scope is untouched by this amendment;
  the only coupling is the mechanical one at AC23 item 7.

### Stage-19 steering review

To be recorded during Validation step 4b. Required content: the date; the number
of committed-catalogue entries presented to the maintainer, split `keep` /
`unwired`; and **either** one line per recorded override —
`` `<path>` · `retune`|`retire` · "<rationale verbatim>" `` — **or** the literal
words `no override recorded` with the maintainer's stated reason. **Do not write
a predicted or plausible-looking review here.** An invented disposition is a
fabricated human judgment and fails AC25; an honest `no override recorded`
passes it.

### Real-source drift rehearsal

To be recorded during Validation step 3 — either the observed transcript
(failing test ids, the verbatim first failure line containing
`zzz_drift_probe`, and confirmation that `git status --short` was clean after
the revert) or the literal words `not executed` with the reason. **Do not write
a predicted transcript here.**
