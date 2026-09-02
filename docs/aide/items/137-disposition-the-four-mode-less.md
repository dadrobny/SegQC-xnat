# Item 137 — Disposition the four mode-less rules

> **Created:** 2026-09-02 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness
> **Queue:** [`../queue/queue-019.md`](../queue/queue-019.md) · Item 137
> **Objectives:** G2 (every rule names a mode, stated not implied), G7 (honest reporting of what is and is not established), G8 (Stage 19's statused-but-mode-unmapped shortfall, closed at its root)
> **Suggested branch:** `aide/137-disposition-the-four-mode-less`

---

## Description

Fill item 136's declaration seam for the four registered rules that map to no
§6 failure mode — `bounds`, `intensity`, `reference_delta` and
`intensity_reference_delta` — each of which carries a `pending_reason` naming
this item. Roadmap Stage 20's **rule → mode** direction must be complete, and
its acceptance takes either answer: a mapping to one or more §6 modes with the
evidence behind it, **or** a recorded mode-less declaration with the reason. A
*silent* row is the only unacceptable outcome.

The disposition this item records, and the reasoning each rests on:

- **`bounds` → §6 mode 2** (over-/under-segmentation — fused or fragmented
  vertebra segments), on **analytic** grounds, no corpus case. The rule
  compares per-label physical volume and x/y/z extent against level-aware
  plausible ranges: a fused pair reads over-max, an under-segmented or
  partially-labelled vertebra reads under-min. That magnitude signal *is*
  mode 2's definition. Modes 3, 5 and 6 were considered and rejected — see
  Assumptions A2.
- **`reference_delta` → §6 mode 2**, same grounds. It is the distributional
  form of the same magnitude judgement: the only per-label feature the
  committed reference artifact carries is `physical_volume_mm3` (z-score,
  robust-z, percentile rank, out-of-range, plus the label-level
  `distribution_distance` computed over it), so "out of distribution" here
  means "implausible volume" measured against a cohort instead of against
  hand-set bounds.
- **`intensity` → mode-less, with the reason recorded**, and the finding
  captured: §6's eight modes are geometric/topological/semantic and none of
  them names *tissue plausibility*. The rule thresholds whether a labelled
  region's HU distribution is bone-like — implausibly low median (soft tissue
  / air), implausibly high median (metal / implant), near-zero std
  (degenerate / uniform). It is demonstrably useful and demonstrably exercised:
  `tests/corpus/intensity/manifest.json`'s four cases (`clean_hu`,
  `implausible_metal`, `implausible_soft_tissue`, `degenerate_uniform`) drive
  it, and that manifest carries **no `failure_mode` field at all** — the same
  gap, expressed in the corpus.
- **`intensity_reference_delta` → mode-less**, for the same reason: it is the
  reference-relative form of the same intensity judgement.

Where the evidence says the **mode catalogue is short a mode** rather than the
rule being speculative, the queue's scope fence is explicit: record the finding
and stop. [`../vision.md`](../vision.md) §6 is a root document that changes only
through its own loop entry point and a reviewed PR, and every acceptance
criterion below is satisfiable by *recording* a disposition with its reason. So
the catalogue-gap finding is captured as one line in
[`../insights.md`](../insights.md) (AC16), and §6 is left at eight modes (AC17).

`catalogue.py` gains one thing: a `"rule_mode_less"` evidence tag, so a path
consumed only by a rule that has *declared* itself mode-less stops reporting
`mode_evidence == ("rule_unmapped",)`. That is the substantive close of Stage
19's G8 third state — *statused but mode-unmapped, with the consuming mode-less
rule named* — because after this item, `"rule_unmapped"` means only what it
should: a consuming rule that has said nothing.

**Expected artifact movement** (simulated against the committed catalogue,
2026-09-02, with the proposed declarations in place). Of 138 entries:

- **14 gain `failure_modes = [2]`** — four `bounds` geometry paths
  (`per_label.{label}.geometry.extent_x_mm` / `_y_` / `_z_`,
  `…physical_volume_mm3`) and ten `reference_delta.*` paths. Entries carrying
  mode 2 rise from **7 to 21**.
- **19 move `mode_evidence`**, and **0 remain `("rule_unmapped",)`** (was 18).
  The post-item distribution is: 86 `()` · 25 `("rule_mode_map",
  "rule_declaration")` · 7 `("rule_declaration",)` · 7 `("rule_declaration",
  "rule_mode_less")` · 6 `("per_mode_metric", "rule_mode_map",
  "rule_declaration")` · 4 `("rule_mode_less",)` · 2 `("per_mode_metric",)` ·
  1 `("rule_mode_map", "rule_declaration", "rule_mode_less")` (the `per_label`
  container, consumed by every rule).
- **`feature_catalogue.generated.md` moves this time** — unlike item 136, whose
  change was confined to `mode_evidence`. `render_markdown` emits a `§6 mode(s)`
  column from `failure_modes`, so exactly those 14 rows change.

**What this item is NOT.** It is not the traceability matrix (item 138), not the
exercise report (item 139), not the specificity ratchet (item 140). It changes no
threshold, no extractor, no rule verdict, no report schema and no CLI behaviour
— the declaration stays inert at evaluation time (AC18). It adds no corpus case
and designates no new `Expectation`. It does not edit `vision.md` or
`roadmap.md`, and it does not add a ninth §6 mode.

## Acceptance Criteria

- [ ] **AC1: No shipped rule is undeclared or still pending.** Every rule
  yielded by `segfacet.heuristics.iter_rules()` (ten) has a
  `mode_declaration` that is a `RuleModeDeclaration` instance whose
  `pending_reason == ""`.

- [ ] **AC2: `bounds` declares §6 mode 2 and nothing else.**
  `declaration_for("bounds").modes == (2,)`, with `mode_less_reason == ""` and
  `pending_reason == ""`.

- [ ] **AC3: `reference_delta` declares §6 mode 2 and nothing else.**
  `declaration_for("reference_delta").modes == (2,)`, with
  `mode_less_reason == ""` and `pending_reason == ""`.

- [ ] **AC4: Both mode-2 declarations are analytic, not corpus-corroborated.**
  For `bounds` and `reference_delta`: `"analytic" in evidence`,
  `"corpus" not in evidence`, and at least one `evidence` element other than
  `"analytic"` is a string of ≥ 40 characters naming the mechanism.

- [ ] **AC5: `intensity` and `intensity_reference_delta` are mode-less, not
  pending.** Each declares `modes == ()`, `pending_reason == ""`, and a
  non-empty `mode_less_reason`.

- [ ] **AC6: Both mode-less reasons are substantive.** Each
  `mode_less_reason` is ≥ 120 characters long and contains the string `"§6"` —
  it says which catalogue it targets no mode of, not merely that it targets
  none.

- [ ] **AC7: `intensity`'s reason cites the corpus that exercises it.**
  `declaration_for("intensity").mode_less_reason` contains the substring
  `"tests/corpus/intensity/manifest.json"`.

- [ ] **AC8: The evidence AC7 cites actually holds.** Every case entry in
  `tests/corpus/intensity/manifest.json` lacks a `failure_mode` key, and the
  manifest names exactly the four cases `clean_hu`, `implausible_metal`,
  `implausible_soft_tissue`, `degenerate_uniform`.

- [ ] **AC9: Declarations and the corpus-derived map still agree.**
  `segfacet.catalogue.rule_declaration_conflicts()` returns an empty tuple —
  the two analytic declarations claim no corpus corroboration and name only
  modes inside `segfacet.feature_docs.MODE_ANCHOR_PATHS`'s key set.

- [ ] **AC10: The catalogue records a mode-less consuming rule as its own
  evidence tag.** In a fresh `build_catalogue(strict=True)`, an entry's
  `mode_evidence` contains `"rule_mode_less"` **if and only if** at least one
  of its `consuming_rules` carries a declaration with a non-empty
  `mode_less_reason`.

- [ ] **AC11: `mode_evidence` keeps a canonical order.** For every entry of a
  fresh `build_catalogue(strict=True)`, `mode_evidence` is either exactly
  `("rule_unmapped",)` or a subsequence of `("per_mode_metric",
  "rule_mode_map", "rule_declaration", "rule_mode_less")`.

- [ ] **AC12: Nothing on this tree still reports `rule_unmapped`.** No entry of
  a fresh `build_catalogue(strict=True)` has `"rule_unmapped"` in its
  `mode_evidence` — the G8 bucket is closed by disposition, not by relabelling.

- [ ] **AC13: The declared mode reaches the `failure_modes` column.** Every
  entry of a fresh `build_catalogue(strict=True)` whose `consuming_rules`
  include `"bounds"` or `"reference_delta"` has `2 in failure_modes`.

- [ ] **AC14: Intensity-only paths are honestly mode-less, not unmapped.**
  Every entry whose `consuming_rules` is a non-empty subset of
  `{"intensity", "intensity_reference_delta"}` and whose path is not a
  `MODE_ANCHOR_PATHS` member has `failure_modes == ()` and
  `mode_evidence == ("rule_mode_less",)`.

- [ ] **AC15: Both committed catalogue artifacts regenerate byte-identically.**
  `segfacet.catalogue.main(["--json", <tmp>, "--md", <tmp>])` writes files
  byte-equal to the committed `docs/aide/feature_catalogue.generated.json` and
  `docs/aide/feature_catalogue.generated.md`, and the JSON's `schema_version`
  is still `"1.1"`.

- [ ] **AC16: The catalogue-gap finding is captured durably.**
  `docs/aide/insights.md` **or** one of `docs/aide/insights/archive-*.md`
  contains a single line matching `^- \[[ x]\] gap ` that contains
  `"intensity"`, `"§6"`, and the provenance marker `"item 137"` with a date —
  the finding that §6 carries no tissue-plausibility mode, recorded where the
  queue boundary triages it.

- [ ] **AC17: §6 was recorded against, not grown.** `docs/aide/vision.md`'s
  `## 6. Segmentation Failure Modes` section still enumerates exactly eight
  top-level numbered modes, and `segfacet.feature_docs.MODE_ANCHOR_PATHS`'s key
  set is still `{1, …, 8}`.

- [ ] **AC18: The disposition is metadata only.** Replacing the
  `mode_declaration` of any of the four dispositioned rules (with any
  well-formed `RuleModeDeclaration`) leaves
  `segfacet.heuristics.run_rules(record, config)` returning an equal list of
  `Finding`s for a fixed fixture record.

## Assumptions

- **A1 (`bounds` and `reference_delta` target mode 2, on analytic grounds):**
  neither rule is designated by any committed corpus case, so no corpus
  corroboration is available and none is claimed — `evidence` carries
  `"analytic"` plus a mechanism sentence, never `"corpus"`. Item 136's A4
  reserved exactly this route: a declaration without the `"corpus"` tag is
  bound only by the corpus → declaration direction of
  `rule_declaration_conflicts()`, which is silent for a rule the corpus
  designates for nothing. Should a future item add a corpus case designating
  either rule for a mode, that direction fires and the declaration must widen.
- **A2 (modes 3, 5 and 6 were considered for `bounds` and rejected):**
  **mode 5** ("not all vertebrae in the image are segmented") is structurally
  out of reach — `BoundsRule.evaluate` iterates the labels *present* in
  `record["per_label"]` and can never observe an absent one; `coverage` owns
  mode 5. **Mode 3** (disconnected components / tiny islands) is a
  component-count signal, not a magnitude one, and `fragmentation` owns it
  (declared `(2, 3)`). **Mode 6** (partial vertebra at the border) does depress
  a cropped label's volume, but it is detected by its own designated feature
  and rule (`border`, declared `(6,)`); declaring it here would make the
  matrix's mode → rule direction read as better covered than the rule set
  actually makes it. The minimal defensible declaration is `(2,)`.
- **A3 (`intensity` / `intensity_reference_delta` are mode-less because the
  catalogue is short a mode, not because the rules are speculative):** the
  disposition records that judgement and captures the finding (AC16); adding a
  ninth §6 mode is a `vision.md` edit that needs `/aide-create-vision` and a
  reviewed PR, and §6's own growth contract ("a mode arrives with the rule(s)
  that detect it") is already satisfiable here — the rules exist — so the
  captured finding is actionable by whoever authors that change.
- **A4 (new evidence tag `"rule_mode_less"`, ordered last):** `mode_evidence`
  is a list of the sources that spoke about an entry's modes; a declared
  mode-less consuming rule is a source that spoke and said "no mode", which is
  categorically different from `"rule_unmapped"` ("nobody has said"). It sorts
  **after** `"rule_declaration"` in the canonical order because it contributes
  no mode. This breaks item 136's AC11 "the `rule_declaration` tag is last"
  test, which was true only while no fourth tag existed — see the Testing
  Strategy's reconciliation list.
- **A5 (`"rule_unmapped"` narrows, and stays reachable):** an entry still
  reports `("rule_unmapped",)` when a consuming rule carries **no** declaration
  or a `pending` one. On this tree no such rule ships (AC1), so AC12 holds; the
  branch is kept and is driven by an adversarial test registering an undeclared
  stub rule, because items 138/139 depend on that failure mode staying loud.
- **A6 (`failure_modes` may be moved by an analytic declaration):** item 136's
  Decisions log flagged that `build_catalogue`'s `all_modes` union of declared
  modes was safe only while *declared ⊆ corpus*. This item deliberately breaks
  that containment — mode 2 reaches 14 entries from a declaration alone — and
  that is the point: G8's shortfall is closed by attributing the paths, with
  `mode_evidence` recording that the attribution is declaration-derived rather
  than corpus-corroborated. Item 136's AC10 and AC12 tests encode the pre-137
  containment and are this item's to update (Dependencies).
- **A7 (the `.md` mode column does not distinguish evidence sources):**
  `render_markdown` emits `§6 mode(s)` with no `mode_evidence` column, so a
  human reading the Markdown cannot tell an analytic attribution from a
  corpus-corroborated one. That distinction is item 138's remit — its matrix
  carries the evidence rungs and must "say so where it reports that count" —
  and is deliberately not patched into the catalogue's `note` field here, which
  would churn both artifacts for a statement item 138 is about to make properly.
- **A8 (`rule.py` is untouched):** `"analytic"` is a convention this item adopts,
  not a new validated field, so the seam item 136 owns needs no change. The
  convention is documented where it is enforced — `catalogue.py`'s
  `rule_declaration_conflicts` docstring, which already explains the reserved
  `"corpus"` tag — and in the two rule modules' comments.
- **A9 (no human gate):** the disposition is an engineering judgement grounded
  in the rules' own code and the committed corpora; nothing here needs a
  person's decision or an out-of-band prerequisite. The one judgement a person
  must eventually make — whether §6 grows a tissue-plausibility mode — is
  deferred to the captured finding and its own entry point, and blocks nothing
  in this queue.
- **A10 (engine 1.37.0):** `aide check`'s `.gitattributes` lint needs nothing
  new — both catalogue artifacts are already pinned `text eol=lf`, and this
  item commits no new byte-reproducible fixture.

## Implementation Steps

1. **`src/segfacet/heuristics/bounds.py`** — replace `BoundsRule`'s pending
   declaration with
   `RuleModeDeclaration(modes=(2,), evidence=("analytic", "<mechanism sentence>"))`.
   The mechanism sentence states that per-label volume/extent above the
   level-aware max reads as a fused segment and below the min as an
   under-segmented one, i.e. §6 mode 2's own definition. Add a short comment
   recording that modes 3, 5 and 6 were considered and rejected (A2), and one
   line to the module docstring naming the targeted mode.
2. **`src/segfacet/heuristics/reference_delta.py`** — same shape: `modes=(2,)`,
   `evidence=("analytic", "<mechanism sentence>")`, the sentence naming
   `physical_volume_mm3` as the only per-label reference feature the committed
   artifact carries, so an out-of-distribution verdict here *is* an implausible
   volume. Docstring line as above.
3. **`src/segfacet/heuristics/intensity.py`** — replace the pending declaration
   with `RuleModeDeclaration(mode_less_reason="…")`. The reason states: the
   rule judges tissue plausibility (low median = soft tissue/air, high median =
   metal/implant, near-zero std = degenerate/uniform); §6's eight modes are
   geometric/topological/semantic and name no such failure; the rule is
   exercised by `tests/corpus/intensity/manifest.json`'s four cases, whose
   manifest carries no `failure_mode` field at all; and the catalogue gap is
   recorded in `docs/aide/insights.md` rather than fixed here, because §6 is a
   root document. ≥ 120 characters and containing `"§6"` (AC6) and that
   manifest path (AC7).
4. **`src/segfacet/heuristics/intensity_reference_delta.py`** — the same
   disposition, worded for the reference-relative form of the judgement:
   deviation of a labelled region's intensity statistics from a level-aware
   reference distribution is still a tissue-plausibility claim, and §6 names no
   mode for it. ≥ 120 characters and containing `"§6"`.
5. **`src/segfacet/catalogue.py`**:
   - in `build_catalogue`, collect `mode_less_by_rule` from
     `iter_rule_declarations()` (rule ids whose declaration has a non-empty
     `mode_less_reason`) alongside the existing `declared_modes_by_rule`;
   - per path, track `had_mode_less_rule`, and narrow `had_unmapped_rule` to a
     consuming rule with **neither** corpus-derived modes, **nor** declared
     modes, **nor** a mode-less reason;
   - append `"rule_mode_less"` to `mode_evidence_parts` **last**, after
     `"rule_declaration"`, when `had_mode_less_rule`;
   - restructure the final branch so a path with no modes but a non-empty
     parts list keeps those parts: `if all_modes:` → parts; `elif
     mode_evidence_parts:` → parts (the mode-less-only case); `elif rule_ids
     and had_unmapped_rule:` → `("rule_unmapped",)`; else `()`;
   - update the module docstring's derivation-mechanisms section with the new
     tag and what `"rule_unmapped"` now means (A5), and extend
     `rule_declaration_conflicts`'s docstring with the `"analytic"` convention
     (A8). Do **not** change the checker's logic.
6. **Regenerate the committed catalogue**: `.venv/bin/python -m segfacet.catalogue`,
   then confirm by `git diff` that exactly 14 entries gained mode 2, 19 moved
   `mode_evidence`, none still says `rule_unmapped`, and the `.md` moved only
   in its `§6 mode(s)` column on those 14 rows.
7. **Capture the finding** — append one line to `docs/aide/insights.md`
   (a plain append; never `tick`, never a reword of an existing entry):
   type `gap`, naming `intensity`/`intensity_reference_delta`, the missing
   tissue-plausibility mode, the intensity manifest's absent `failure_mode`
   field as corroboration, and that adding a §6 mode needs the create-vision
   entry point plus a reviewed PR. Provenance `*(item 137, 2026-09-02, engine
   1.37.0)*`.
8. **Reconcile the two pre-137 test premises** (see Testing Strategy) —
   `tests/test_136_rule_mode_declarations.py` and
   `tests/test_103_feature_catalogue.py`. Update the assertion to the post-137
   invariant with the reason recorded in the test's docstring; do not delete a
   test to make it pass.

## Authorised paths

**May change:**

- `src/segfacet/heuristics/bounds.py` — mode-2 analytic declaration (AC2, AC4).
- `src/segfacet/heuristics/reference_delta.py` — mode-2 analytic declaration (AC3, AC4).
- `src/segfacet/heuristics/intensity.py` — mode-less declaration with its reason (AC5–AC7).
- `src/segfacet/heuristics/intensity_reference_delta.py` — mode-less declaration with its reason (AC5, AC6).
- `src/segfacet/catalogue.py` — the `"rule_mode_less"` evidence tag, the narrowed `rule_unmapped` branch, docstrings (AC10–AC14).
- `docs/aide/feature_catalogue.generated.json` — regenerated; 14 entries gain mode 2, 19 move `mode_evidence`, 0 keep `rule_unmapped` (AC12–AC15).
- `docs/aide/feature_catalogue.generated.md` — regenerated by the same command; 14 rows move in the `§6 mode(s)` column (AC15).
- `docs/aide/insights.md` — the captured catalogue-gap finding, one appended line (AC16).
- `tests/test_137_mode_less_rule_disposition.py` — this item's test module.
- `tests/test_136_rule_mode_declarations.py` — its AC5 (four rules pending), AC10 (declared ⊆ corpus), AC11-last-tag, AC12 (`failure_modes` recomputed without the declaration source) and the movement-count test encode pre-137 premises **by design**; item 136's spec names this item as their carrier.
- `tests/test_103_feature_catalogue.py` — `test_ac15_unmapped_rule_only_entry_is_honestly_unmapped` asserts `mode_evidence == ("rule_unmapped",)` for entries consumed only by the four rules this item dispositions; item 136's spec names this item as its carrier.

**Asserts against:**

- `docs/aide/vision.md` — AC17 reads §6 and pins it at eight numbered modes; the item records its finding without editing the root document (`aide scope` proves the same claim against the diff).
- `src/segfacet/feature_docs.py` — `MODE_ANCHOR_PATHS`, the in-code §6 mode catalogue AC9, AC14 and AC17 read; unchanged here.
- `src/segfacet/synth/*.py` — the `Expectation(failure_mode=…, expected_rule_ids=…)` literals AC9 reads through `catalogue`'s AST scan; this item designates no new corpus case.
- `tests/corpus/intensity/manifest.json` — AC8 pins its four case names and the absence of a `failure_mode` key, the evidence `intensity`'s mode-less reason cites; read only.
- `tests/committed_artifact_guard.py` — the `ALLOWLIST` entries that make AC15's byte-exact fresh-vs-committed comparison legitimate; read only, no new entry needed.

## Testing Strategy

New module: **`tests/test_137_mode_less_rule_disposition.py`**, one focused test
per AC (AC5 and AC6 parametrised over the two mode-less rules, AC2–AC4 over the
two analytic ones), plus:

- **Adversarial: `rule_unmapped` is narrowed, not removed** (A5) — inside a
  snapshot/restore registry fixture (the house pattern from
  `tests/test_026_rule_engine_core.py`), register a stub rule with no
  declaration and confirm `rule_declaration_conflicts()` names it; and, with a
  registered rule's declaration monkeypatched back to a `pending` one, confirm
  a path consumed only by it reports `("rule_unmapped",)` again. The branch
  items 138/139 rely on must stay reachable and loud.
- **Adversarial: a future corpus case still binds an analytic declaration** —
  monkeypatch `catalogue`'s scanned map so the corpus designates `bounds` for a
  mode it does not declare, and assert `rule_declaration_conflicts()` reports it
  naming both. The analytic route must not become an escape hatch from the
  corpus → declaration direction.
- **Adversarial: a `"corpus"`-tagged analytic declaration fails** — replacing
  `bounds`' evidence with `("corpus",)` makes `rule_declaration_conflicts()`
  non-empty, since no case designates it. This pins AC4's "not corpus" as
  load-bearing rather than cosmetic.
- **Measured movement counts** — one test asserting this item's own figures on
  a fresh `build_catalogue(strict=True)`: 138 entries; 21 carry mode 2; the
  `mode_evidence` distribution is 86 `()` · 25 · 7 · 7 · 6 · 4 · 2 · 1 as listed
  in the Description; 0 `("rule_unmapped",)`. The analogue of item 136's
  `test_adv_expected_artifact_movement_counts_from_spec`.
- **Determinism / immutability** — `build_catalogue()` twice in one session
  returns equal `mode_evidence` and `failure_modes` for every path;
  `rule_declaration_conflicts()` twice returns equal tuples; each live
  declaration object refuses in-place mutation (frozen).
- **Edge cases** — an entry with no `consuming_rules` gains neither
  `"rule_declaration"` nor `"rule_mode_less"` (AC10's "only if" half); an entry
  consumed by both a mode-2 declarer and a mode-less declarer carries both tags
  in canonical order and keeps `failure_modes == (2,)` (the seven shared
  `reference_delta.*` paths); the `per_label` container keeps its
  corpus-derived modes and gains `"rule_mode_less"` last.
- **Portability** — no absolute path literals; committed artifacts addressed
  from `Path(__file__).resolve().parent.parent`; regeneration writes into
  `tmp_path`, never over the committed copies; the insights search (AC16) globs
  `docs/aide/insights/archive-*.md` as well as the live inbox, because
  `aide insights archive` legitimately moves a closed entry out (CLAUDE.md's
  Gotchas; `tests/test_117_scope_verb_swap.py` is the worked example).

**Existing tests to reconcile** — these encode pre-137 premises and are this
item's to update, with the post-137 invariant and its reason recorded in each
test's docstring:

- `tests/test_136_rule_mode_declarations.py::test_ac5_contested_rule_is_pending_naming_item_137`
  — inverts: the four rules are now dispositioned, none pending. Keep the test
  as the roll call of the four, asserting the *dispositioned* shape.
- `…::test_ac10_declared_modes_subset_of_corpus_map_for_every_rule` — no longer
  holds by design (A6). Narrow it to declarations tagged `"corpus"`, which is
  the containment that still must hold.
- `…::test_ac11_rule_declaration_tag_is_last_when_present` — `"rule_mode_less"`
  now sorts after it (A4). Re-express as the canonical-order subsequence check
  (this item's AC11) rather than deleting it.
- `…::test_ac12_failure_modes_recomputed_independently_matches` — the
  independent recomputation must now include declared modes as a third term.
- `…::test_adv_expected_artifact_movement_counts_from_spec` — item 136's
  32/18/86/2 figures are superseded by this item's; update them and keep the
  test's provenance sentence naming both measurements.
- `tests/test_103_feature_catalogue.py::test_ac15_unmapped_rule_only_entry_is_honestly_unmapped`
  — its `unmapped_rules` set is exactly the four this item dispositions.
  Re-express as "an entry consumed only by declared-mode-less rules is honestly
  `("rule_mode_less",)`, and an entry consumed only by an undeclared rule is
  `("rule_unmapped",)`" so the honesty claim survives the disposition.
- `tests/test_103_feature_catalogue.py` (byte-exact fresh-vs-committed),
  `tests/test_105_golden_decision_table.py`, `tests/test_106_stage19_validation.py`,
  `tests/test_120_leave_one_out_offset.py`, `tests/test_129_coincident_centroids_and_held_out_floor.py`,
  `tests/test_131_tangent_direction_normalisation.py`,
  `tests/test_132_monotonicity_against_traversal_order.py` — each compares
  a fresh catalogue against the committed one; all go red until step 6's
  regeneration lands and green afterwards. None needs editing.
- `tests/test_106_stage19_validation.py::test_ac18_status_mode_partition_exhaustive_disjoint_and_measured`
  — pins no counts, so the shrinking statused-but-mode-unmapped bucket (to the
  four intensity-only paths) leaves it green. Verify, do not edit.

## Validation

Beyond the suite, observe the disposition and the artifact movement directly (no
`[validation]` profile needed — CPU-only, no optional dependency):

1. `.venv/bin/python -c "print([(r.rule_id, r.mode_declaration) for r in __import__('segfacet.heuristics', fromlist=['x']).iter_rules()])"`
   — the ten-rule roll call: six corpus-corroborated, two analytic mode-2, two
   mode-less with reasons, none pending. The human-legible form of AC1–AC7.
2. `.venv/bin/python -c "print(__import__('segfacet.catalogue', fromlist=['x']).rule_declaration_conflicts())"`
   — expect `()`.
3. `.venv/bin/python -m segfacet.catalogue` — regenerates both artifacts in place.
4. `git diff --stat docs/aide/feature_catalogue.generated.json docs/aide/feature_catalogue.generated.md`
   — expect **both** files changed (unlike item 136, where the `.md` did not move).
5. `git diff -U0 docs/aide/feature_catalogue.generated.json | grep -c rule_unmapped`
   — expect 18 removed lines and no added one.
6. `.venv/bin/python -c "import json,collections;d=json.load(open('docs/aide/feature_catalogue.generated.json'));e=[x for g in d['groups'] for x in g['entries']];print(collections.Counter(tuple(x['mode_evidence']) for x in e))"`
   — expect the eight-way distribution recorded in the Description.

## Dependencies

Item 136 — provides the `RuleModeDeclaration` seam this item fills, the
`pending` state it replaces, `rule_declaration_conflicts()`, and the
`"rule_declaration"` evidence tag beside which `"rule_mode_less"` is added.
Item 136's own spec names this item as the carrier for the pre-137 premises in
`tests/test_136_rule_mode_declarations.py`.

**Downstream:** item 138 (traceability matrix) reads these declarations for its
rule → mode direction and owns the evidence rungs that distinguish an analytic
attribution from a corpus-corroborated one (A7); item 139 (exercise report)
records that `intensity` is exercised by the second committed corpus; item 142
(stage validation) replays the G8 close and quotes the re-measured counts.

## Decisions & Trade-offs

- Implemented exactly the disposition the spec prescribes: `bounds` and
  `reference_delta` declare `modes=(2,)` with `evidence=("analytic", "<mechanism
  sentence>")`; `intensity` and `intensity_reference_delta` declare
  `mode_less_reason=…` (≥120 chars, containing `"§6"`; `intensity`'s additionally
  cites `tests/corpus/intensity/manifest.json`). Each rule module gained a short
  comment recording the A2 rejection of modes 3/5/6 for `bounds` (or the
  mode-less/reference-relative rationale for its sibling), plus one module
  docstring line naming the disposition.
- `catalogue.py`: added `mode_less_by_rule` (rule_ids with a non-empty
  `mode_less_reason`) alongside `declared_modes_by_rule`; narrowed
  `had_unmapped_rule` to fire only when a consuming rule has neither
  corpus-derived modes, nor declared modes, nor a mode-less reason; appended
  `"rule_mode_less"` to `mode_evidence_parts` last (after `"rule_declaration"`).
  Restructured the final branch to `if all_modes: … elif mode_evidence_parts:
  … elif rule_ids and had_unmapped_rule: ("rule_unmapped",) … else: ()` so the
  mode-less-only case (a path consumed solely by a mode-less-declaring rule)
  reports `("rule_mode_less",)` honestly instead of falling through to
  `("rule_unmapped",)`. Extended the module docstring's derivation-mechanisms
  section and `rule_declaration_conflicts`'s docstring with the `"analytic"`
  evidence convention (A8), per the Implementation Steps.
- Regenerated both committed catalogue artifacts via
  `.venv/bin/python -m segfacet.catalogue`; measured movement matches the
  spec's Description exactly: 138 entries, 21 carry mode 2 (14 gained),
  `mode_evidence` distribution 86 `()` · 25 `("rule_mode_map",
  "rule_declaration")` · 7 `("rule_declaration",)` · 7 `("rule_declaration",
  "rule_mode_less")` · 6 `("per_mode_metric", "rule_mode_map",
  "rule_declaration")` · 4 `("rule_mode_less",)` · 2 `("per_mode_metric",)` · 1
  `("rule_mode_map", "rule_declaration", "rule_mode_less")`, 0
  `("rule_unmapped",)`. `rule_declaration_conflicts()` returns `()`.
- Appended the AC16 catalogue-gap finding to `docs/aide/insights.md` as a
  plain append (never a tick, never a reword of an existing line), naming
  `intensity`/`intensity_reference_delta`, the missing tissue-plausibility
  mode, the intensity manifest's absent `failure_mode` field as
  corroboration, and that a ninth §6 mode needs `/aide-create-vision` plus a
  reviewed PR — provenance `*(item 137, 2026-09-02, engine 1.37.0)*`.
- The two pre-137 test premises named in Authorised paths
  (`tests/test_136_rule_mode_declarations.py`,
  `tests/test_103_feature_catalogue.py`) were already reconciled by the
  test-writer's commit (`tests: 137 mode-less rule disposition`), which this
  item's builder pass did not need to touch further.
- `vision.md`/`feature_docs.MODE_ANCHOR_PATHS` were read only, never edited
  (AC17); no rule's `evaluate()` logic, threshold, or return shape changed
  (AC18) — the disposition is metadata-only, exactly as scoped.
