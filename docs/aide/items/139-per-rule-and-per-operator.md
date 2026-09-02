# Item 139 — Per-rule and per-operator corpus-exercise reporting

> **Created:** 2026-09-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness
> **Queue:** [`../queue/queue-019.md`](../queue/queue-019.md) · Item 139
> **Objectives:** G2 (every registered rule exercised by ≥1 case or recorded unexercised with its mechanism), G7 (honest reporting — a measured exercise count, not a transcribed one)
> **Suggested branch:** `aide/139-per-rule-and-per-operator`

---

## Description

Add the two **exercise** directions to item 138's generated traceability
artifact, so that neither *"6 of 10 rules fire on zero cases"* nor *"the
registered `fuse` operator generates no corpus case at all"* can recur
unnoticed. **Per rule:** exercised by ≥1 committed corpus case, or recorded
unexercised **with its mechanism**. **Per operator:** every registered
`Perturbation` generates ≥1 corpus case, or is recorded unused with a reason.
This closes Stage 20's *"every registered rule is exercised by ≥1 case or
recorded as unexercised with a reason"* acceptance.

### This item **extends** item 138's module and artifacts — and why

Three candidate shapes were considered; the queue and item 138 both point the
same way, and the reasoning holds on its own:

- **Extend** (chosen). `src/segfacet/traceability.py` gains an `exercise`
  section in `docs/aide/traceability_matrix.generated.{json,md}`. Item 138's
  spec names this item as the carrier in three places (its A1, its *"What this
  item is NOT"*, and its Downstream note), and the queue says *"extend item
  138's generated artifact"* and *"the extended artifact regenerates
  byte-identically"*.
- **A second artifact** (rejected). It would duplicate the rule-registry read,
  need its own `.gitattributes` pins, and hand item 142 two files to reconcile
  where the stage's acceptance reads as one claim.
- **Feed item 138** (rejected). The exercise state is only meaningful *beside*
  the direction rows: `overlap` unexercised through plain `run_qc` means one
  thing next to mode 8's `structurally-unobservable` rung and something else
  next to a `synthetic-demonstrable` one. Splitting producer from consumer
  would put the two halves of one judgement in two documents.

### Measured on this tree, 2026-09-02 — not transcribed from the queue

Every number below was measured while specifying this item, through the
public entry points the generator will use. The tests assert the
**derivation**, never these literals (A6).

**The `fuse` claim, verified.** `perturbation_names()` returns ten operators;
`segfacet.synth.corpus.CASE_RECIPE`'s nine entries use nine of them. The
tenth, `"fuse"` (`FusePerturbation`, `synth/component_shape.py`), generates no
corpus case. **The progress.md deliverable's claim is exactly true as
written.** Probed live —
`get_perturbation("fuse")().apply(build_clean_spine().seg_img, 0)` — the
operator declares `failure_mode=2`, `expected_rule_ids={"fragmentation"}`,
`expected_labels={23}`, `expected_verdict="flagged-for-review"`. Running that
probed label map through plain `run_qc` fires exactly `{"fragmentation"}` with
verdict `flagged-for-review` — matching the operator's own expectation, and
firing **no** `bounds` finding, which *measures* rather than repeats
`FusePerturbation`'s docstring claim that *"the shipped default lumbar
`bounds` cannot fire on a two-label fuse"*. §6 mode 2 already has a committed
case, `mode2_fragment`, on which `fragmentation` is measured to fire
end-to-end. So the corpus loses no mode coverage and no rule coverage by
omitting `fuse` — which is the record, not a reason to add a case.

**Per rule, across both committed corpora.**

| Rule | State | Where |
| --- | --- | --- |
| `border` | exercised | geometric, `mode6_crop_at_border`, pipeline |
| `coverage` | exercised | geometric, `mode5_remove_level`, pipeline |
| `fragmentation` | exercised | geometric, `mode2_fragment` + `mode3_inject_islands`, pipeline |
| `mislabel` | exercised | geometric, `mode1_displace` + `mode4_relabel_swap` + `mode6_crop_at_border`, pipeline |
| `sequence` | exercised | geometric, `mode7_sequence_break`, pipeline |
| `overlap` | exercised | geometric, `mode8_force_overlap`, **reconstruction** |
| `intensity` | exercised | intensity, `implausible_metal` + `implausible_soft_tissue` + `degenerate_uniform` |
| `bounds` | **unexercised** | input present on every case, tripped by none |
| `reference_delta` | **unexercised** | input absent from both harness records |
| `intensity_reference_delta` | **unexercised** | input absent from both harness records |

So **7 of 10** registered rules are exercised across both committed corpora,
and three are not. Three refinements the queue's own framing needs, all
measured:

- **The queue's "five rules fire" is the *geometric pipeline* figure, and it
  reproduces exactly**: `{border, coverage, fragmentation, mislabel,
  sequence}` through `segfacet.synth.regression.pipeline_findings` over the
  nine cases; `mode8_force_overlap` fires nothing and `mode6_crop_at_border`
  fires `mislabel` beside its designated `border` (item 140's to adjudicate,
  not this item's).
- **`overlap` is exercised, through the reconstruction path.**
  `reconstructed_findings(mode8_force_overlap)` drives `OverlapRule` and
  returns an `overlap` finding. A report counting only plain `run_qc` would
  call `overlap` unexercised and be wrong in the same way as one reading only
  the geometric manifest.
- **`intensity` is exercised, so the queue's "three harness-limited rules" is
  a per-corpus statement, not an overall one.** On the geometric record
  `intensity` has zero of its five catalogued consumed leaf paths available;
  on the intensity record it has four of five and fires on three of the four
  cases. The report therefore records availability **per corpus** and the
  exercise state **overall**, and the two never contradict each other.

**The mechanism for an unexercised rule is derived, not asserted.** For each
rule, the generator measures how many of its catalogued consumed leaf paths
(`build_catalogue().entries[*].consuming_rules`) appear in
`catalogue.iter_leaf_paths(record)` for the record each harness actually feeds
`run_rules`. Measured 2026-09-02:

| Rule | geometric record | intensity record |
| --- | --- | --- |
| `border` | 8/9 | 8/9 |
| `bounds` | 5/6 | 5/6 |
| `coverage` | 2/4 | 2/4 |
| `fragmentation` | 6/7 | 6/7 |
| `intensity` | **0/5** | 4/5 |
| `intensity_reference_delta` | **0/8** | **0/8** |
| `mislabel` | 8/9 | 8/9 |
| `overlap` | 1/6 | 1/6 |
| `reference_delta` | **0/11** | **0/11** |
| `sequence` | 3/5 | 3/5 |

That splits "unexercised" into two states the report keeps apart, both
derived from the table above rather than authored:

- **`input-absent`** — zero consumed leaf paths available on every harness
  record, so the rule *could not have fired whatever the fixtures contain*.
  `reference_delta` and `intensity_reference_delta` are here.
  `segfacet.synth.regression.pipeline_findings` calls `run_qc` with the
  segmentation alone (attaching neither `reference` nor `image_features`), and
  the intensity harness calls `run_qc_with_intensity(..., reference=None)`.
  **This is a property of the harness, not of the rule** —
  `segfacet.reference.artifact.bundled_default_reference()` ships a reference
  the repo could pass, and CLAUDE.md's Gotchas record that a real-VerSe19 run
  on `clean_control` reports ~40 `bounds`/`reference_delta` findings. Attaching
  one changes the baseline item 140 ratchets and is out of scope here.
- **`input-present-never-fired`** — ≥1 consumed leaf path available and no case
  trips it. `bounds` is here (5/6 on every case), so recording it as a harness
  limitation would misattribute; recording it as "no case" without the
  availability figure would under-state.

### What this item is NOT

It adds **no corpus case** to either corpus and edits neither manifest — the
deliverable is the report and its reasons, not a bigger corpus. It attaches no
reference to any harness path. It does not adopt the specificity ratchet or
adjudicate the `(mode6_crop_at_border, mislabel)` co-detection (item 140), does
not touch `eval/severity_ladder.py` (item 141), and ticks no `progress.md`
acceptance box (item 142). It changes no rule, threshold, extractor, verdict,
report schema or CLI behaviour, regenerates neither catalogue artifact, and
edits neither `vision.md` nor `roadmap.md`.

### Open insights reviewed before scoping — three are load-bearing

`aide insights list --open` was read in full. Three entries bear on this item
and are recorded here so a later reader need not re-derive the check:

- **2026-09-02, item 137 (the length-floor defect)** — *load-bearing, and this
  item's central discipline.* A `RuleModeDeclaration.evidence` string shipped a
  false claim about a committed artifact because the test checked
  `len(evidence) >= 40` rather than content. This item authors five judgement
  strings on the same footing (three unexercised mechanisms, one unused-operator
  reason, and the granularity-free qualifiers), so AC20 holds each to a token
  the test **re-derives from live state** and AC21 forbids any character-count
  threshold in this item's test module.
- **2026-09-02, item 137 (§6 names no tissue-plausibility mode)** —
  *load-bearing, and this item measures one clause of it more precisely.* That
  entry says `tests/corpus/intensity/manifest.json`'s four cases "drive them",
  meaning `intensity` **and** `intensity_reference_delta`. Measured here: the
  four cases drive `intensity` (three of them fire it; `clean_hu` is the
  negative control and correctly fires nothing), and drive
  `intensity_reference_delta` **not at all**, because no harness path attaches
  a reference. `IntensityRule.mode_declaration`'s own sentence claims only that
  the four cases drive *it*, and that claim holds. The insight's looser plural
  is the sort of prose this item's report replaces with a measurement; the
  entry stays open for its own carrier (a §6 edit through
  `/aide-create-vision`), and nothing here rewrites it.
- **2026-09-02, item 138 (`GROUNDS` has no float-free ground)** —
  *load-bearing as a constraint.* This item takes the same route item 138 took:
  no byte-exact fresh-vs-committed comparison anywhere in its tests (A5), so
  `tests/committed_artifact_guard.py` stays clean and unextended.

Not load-bearing: the two `catalogue.rule_declaration_conflicts()` weaknesses
(2026-09-02, item 136) — this item reads neither that function nor a
declaration's `evidence` tuple; the unregistered-designated-`rule_id` blind
spot (item 136), already reported inside the artifact by item 138's AC25 and
inherited unchanged; the rule-granular mode attribution (item 138) — this
item's directions are keyed by `rule_id` and operator `name`, never by feature
path; the roadmap forward-supersession gap and the stale 72-of-111 figure,
both root-document/item-142 matters; the CI constraints and `--calibrate` cost
entries, unrelated.

## Acceptance Criteria

- [ ] **AC1: The artifact carries an `exercise` section with a fixed shape.**
  `SCHEMA_VERSION == "1.1"`, and the JSON payload's top-level `exercise` key is
  a mapping whose keys are exactly `("corpora", "rules", "operators")`.

- [ ] **AC2: The public surface is unchanged.** `segfacet.traceability.__all__`
  is still exactly `["build_matrix", "matrix_to_dict", "render_markdown",
  "main"]`, each callable, and `build_matrix()` still takes no required
  argument.

- [ ] **AC3: The committed JSON is a fresh build including the exercise
  section.** The committed
  `docs/aide/traceability_matrix.generated.json` parses to a payload equal to
  `matrix_to_dict(build_matrix())`, and that payload's `exercise` section is
  non-empty.

- [ ] **AC4: The grown artifacts are byte-reproducible run-to-run.** Two
  `main(["--json", …, "--md", …])` runs into different temporary paths in one
  session produce byte-equal JSON and byte-equal Markdown.

- [ ] **AC5: The exercise tables render after the rule-declaration table, and
  the declaration row stays the first match for a `rule_id`.** In the committed
  Markdown, the `## Rules -> section 6 modes` heading precedes both exercise
  headings; and for every registered `rule_id`, the **first** table row whose
  first cell equals that `rule_id` is the row carrying that rule's
  `declaration_state`. (This is the invariant
  `tests/test_138_traceability_matrix.py::test_ac5_markdown_rows_agree_with_json_for_every_mode_and_rule`
  depends on — see A9.)

- [ ] **AC6: The Markdown agrees with the JSON for both exercise directions.**
  For every rule in `exercise.rules` and every operator in
  `exercise.operators`, the committed Markdown carries a row in the matching
  exercise section whose cells contain that record's key, its state, and either
  its exercising `case_id`s or its recorded reason.

- [ ] **AC7: One exercise record per registered rule.**
  `sorted(exercise["rules"])` equals `sorted(r.rule_id for r in
  segfacet.heuristics.iter_rules())` — no more, no fewer.

- [ ] **AC8: Every rule is exercised or carries a mechanism, never both and
  never neither.** Each rule record has `state == "exercised"` with a non-empty
  `exercised_by` and an empty `mechanism`, **or** `state == "unexercised"` with
  an empty `exercised_by` and a non-empty `mechanism`; and
  `directions.rule_exercise` reports `complete: true` with an empty holes list.

- [ ] **AC9: The exercising cases are re-derived, never transcribed.** For
  every rule, its `exercised_by` set of `(corpus, case_id, path)` triples
  equals the set the test computes independently, in the same session, by
  driving both committed corpora through the public entry points
  (`synth.regression.pipeline_findings`, `synth.regression.reconstructed_findings`,
  and `pipeline.run_qc_with_intensity(..., reference=None,
  enable_pyradiomics=False)`).

- [ ] **AC10: Both committed corpora are spanned, with live case counts.**
  `exercise["corpora"]` has exactly the keys `("geometric", "intensity")`,
  naming `tests/corpus/manifest.json` and `tests/corpus/intensity/manifest.json`,
  and each record's case count equals `len(cases)` in the corresponding
  committed manifest as parsed in the test.

- [ ] **AC11: The report reads the intensity manifest live.** With the
  intensity manifest's `implausible_metal` case removed from what the generator
  loads (monkeypatched loader), `intensity`'s `exercised_by` no longer names
  `implausible_metal` and its exercised-case count falls by exactly one.

- [ ] **AC12: Removing every firing intensity case flips `intensity` to
  unexercised.** With `implausible_metal`, `implausible_soft_tissue` and
  `degenerate_uniform` all removed from the loaded intensity manifest,
  `intensity`'s state becomes `"unexercised"` — the failure a report reading
  only `tests/corpus/manifest.json` would have shipped silently.

- [ ] **AC13: The reconstruction path counts as exercise, and says so.**
  `overlap`'s state is `"exercised"`, its only `exercised_by` entry is
  `("geometric", "mode8_force_overlap", "reconstruction")`, and that case's
  `detection` in the committed geometric manifest is `"reconstructed_record"`.

- [ ] **AC14: The geometric pipeline exercise set equals a fresh measurement.**
  The set of rule ids carrying ≥1 `("geometric", *, "pipeline")` entry equals
  the union of `{f.rule_id for f in pipeline_findings(case)}` over the
  committed geometric manifest's cases, computed by the test. (2026-09-02
  witness: `{border, coverage, fragmentation, mislabel, sequence}` — a dated
  witness, not the assertion.)

- [ ] **AC15: Every unexercised rule carries a class from a closed
  vocabulary.** For each `state == "unexercised"` record, `unexercised_class`
  is a member of exactly `("input-absent", "input-present-never-fired")`; for
  each `state == "exercised"` record it is `None`.

- [ ] **AC16: The class is derived from measured input availability.** For each
  unexercised rule, `unexercised_class == "input-absent"` if and only if the
  rule's available consumed-leaf-path count is `0` on **every** corpus record,
  where those counts are recomputed by the test from a fresh
  `build_catalogue(strict=True)` and `catalogue.iter_leaf_paths`. (2026-09-02
  witness: `reference_delta` and `intensity_reference_delta` `input-absent`,
  `bounds` `input-present-never-fired`.)

- [ ] **AC17: No exercised rule is ever classified `input-absent`.** For every
  rule with a non-empty `exercised_by`, its recorded availability on at least
  one corpus is greater than zero — the self-consistency guard that makes a
  wrong availability derivation fail rather than read plausibly.

- [ ] **AC18: The availability figures are measured, not transcribed.** For
  every rule and every corpus, the recorded `(available, consumed)` integer
  pair equals the pair the test computes from a fresh catalogue and a fresh
  harness record.

- [ ] **AC19: Availability is recorded per corpus, so `intensity`'s split is
  visible.** `intensity`'s recorded availability is `0` of its consumed paths
  on the `geometric` corpus and greater than `0` on the `intensity` corpus,
  each re-derived by the test — the measurement that makes "three
  harness-limited rules" readable as the per-corpus statement it is.

- [ ] **AC20: Every unexercised mechanism names a token that resolves against
  live state.** For each unexercised rule, its `mechanism` contains, at word
  boundaries, at least one token the test resolves in that session from a
  closed set of kinds: a dotted `segfacet.…` attribute that imports and
  resolves to a callable or object; a `case_id` present in either committed
  manifest; a catalogued feature path in a fresh `build_catalogue()`; or a
  registered `rule_id`.

- [ ] **AC21: No character-count threshold anywhere in this item's test
  module.** `tests/test_139_corpus_exercise_report.py` inspects its own source
  and contains no `len(...) >= N` / `> N` / `<= N` / `< N` comparison against a
  literal, for a mechanism, reason, qualifier, or anything else (A8).

- [ ] **AC22: A stale or near-miss mechanism is detectable.** With an
  unexercised rule's mechanism monkeypatched to (a) a long sentence naming no
  live identifier and (b) a sentence naming `reference_deltas` — one character
  off a registered `rule_id` — AC20's resolvable-token check fails in both
  cases.

- [ ] **AC23: A rule with neither a case nor a mechanism fails loudly.** With a
  stub rule registered (registry snapshot/restore) that fires on no case and
  carries no mechanism, `directions.rule_exercise` reports `complete: false`
  with a hole naming that `rule_id`.

- [ ] **AC24: One exercise record per registered operator.**
  `sorted(exercise["operators"])` equals
  `segfacet.synth.perturbation.perturbation_names()` — no more, no fewer.

- [ ] **AC25: Every operator is used or carries a reason, never both and never
  neither.** Each operator record has `state == "used"` with a non-empty
  `cases` list and an empty `reason`, **or** `state == "unused"` with an empty
  `cases` list and a non-empty `reason`; and `directions.operator_exercise`
  reports `complete: true` with an empty holes list.

- [ ] **AC26: The used/unused split is derived from `CASE_RECIPE`.** For every
  operator, its `cases` list equals the sorted `case_id`s of
  `segfacet.synth.corpus.CASE_RECIPE` entries whose `perturbation` equals that
  operator's name, and `state == "unused"` exactly when that list is empty.
  (2026-09-02 witness: `fuse` alone is unused.)

- [ ] **AC27: The unused operator's target is probed from a live
  `Expectation`, not transcribed.** For each unused operator, the record's
  `probe.failure_mode` and `probe.expected_rule_ids` equal those of the
  `Expectation` returned by the test's own fresh
  `get_perturbation(name)().apply(build_clean_spine().seg_img, 0)`, and
  `probe.pipeline_rule_ids` equals the sorted rule ids that fire when the test
  runs that probed label map through `run_qc`.

- [ ] **AC28: The probe is reproducible and carries no float leaf.** Two
  `build_matrix()` calls in one session yield equal `probe` mappings, and no
  value anywhere under `exercise` is a float.

- [ ] **AC29: The unused-operator reason is held to live state in three
  independent ways.** For each unused operator, its `reason` names, at word
  boundaries: a §6 mode key present in
  `segfacet.synth.perturbation.FAILURE_MODE_NAMES`; a `case_id` in the
  committed geometric manifest whose `failure_mode` equals the probed mode; and
  a `rule_id` that the exercise report itself records as firing on that case —
  each of the three re-derived by the test. (2026-09-02 witness for `fuse`:
  mode 2, `mode2_fragment`, `fragmentation`.)

- [ ] **AC30: `mode_already_covered_by` is derived from the manifest.** For an
  unused operator, it equals the sorted `case_id`s of committed geometric cases
  whose `failure_mode` equals the probed `failure_mode`, and is empty when no
  such case exists (checked by monkeypatching the probed mode to one no case
  carries).

- [ ] **AC31: An operator with neither a case nor a reason fails loudly.** With
  a stub `Perturbation` registered (registry snapshot/restore) that no
  `CASE_RECIPE` entry uses and that carries no reason,
  `directions.operator_exercise` reports `complete: false` with a hole naming
  that operator name.

- [ ] **AC32: A probe that raises is recorded deterministically, never as a
  traceback.** With an unused operator's `apply` monkeypatched to raise, its
  record carries `probe.failed` true and the exception's **class name only**
  (no message, no traceback, no file path), the operator stays `"unused"`, and
  the direction still requires its reason.

- [ ] **AC33: Neither artifact names a radiomics backend.** The strings
  `"pyradiomics"` and `"builtin"` appear in neither committed artifact — the
  exercise report records rule ids, case ids and integers, so its content
  cannot depend on whether PyRadiomics is installed (A4).

## Assumptions

- **A1 (this item extends item 138's module and artifacts):** the generator
  stays `src/segfacet/traceability.py` and the artifacts stay
  `docs/aide/traceability_matrix.generated.{json,md}`. Item 138's spec names
  this item as the carrier (its A1, its "What this item is NOT", its
  Downstream note) and the queue says the same. No new committed artifact and
  no new `.gitattributes` pin: the two existing pins (`.gitattributes` lines
  54–55, item 138 AC7) already cover the paths, so `aide check`'s lint stays
  silent with no edit.
- **A2 (the exercise state is derived; only the mechanism sentences are
  authored):** everything countable — which cases fire which rules, which
  operators `CASE_RECIPE` uses, the per-corpus input-availability integers, the
  probed `Expectation`, the `unexercised_class` — is measured at build time
  from live state. The **five** authored strings are the three unexercised-rule
  mechanisms, the `fuse` reason, and the section qualifiers. Each is held to
  content that resolves (AC20, AC29), never to a length floor (AC21). This is
  the same split item 138 used for `MODE_RUNGS`, and it is deliberate: a rung
  or a mechanism is a judgement and cannot be generated, but everything checked
  *about* it can be.
- **A3 (the harness paths this item drives are the committed ones, unchanged):**
  the geometric corpus is driven by `segfacet.synth.regression.pipeline_findings`
  and `reconstructed_findings` (which is why `overlap` counts as exercised); the
  intensity corpus by `segfacet.pipeline.run_qc_with_intensity(seg, scan,
  config, reference=None, enable_pyradiomics=False)`, whose rule-evaluation
  record this item reconstructs from the returned tuple exactly as
  `pipeline.py` composes it (`{**features_block, "image_features":
  image_features_block}`). No reference is attached to any path — doing so would
  move the baseline item 140 ratchets, and is out of scope.
- **A4 (`enable_pyradiomics=False`, and the artifact is backend-free):** the
  intensity drive pins the builtin first-order backend so the artifact is
  identical on every machine. Measured 2026-09-02: `intensity` fires on
  `implausible_metal`, `implausible_soft_tissue` and `degenerate_uniform` and
  not on `clean_hu`, **identically** with `enable_pyradiomics` True and False,
  so the pin costs no coverage. AC33 makes the independence structural rather
  than merely measured — the artifact records no backend name at all, so this
  item introduces **no** new environment-gated capability and no
  `progress.md` Environment-Gated row.
- **A5 (no byte-exact fresh-vs-committed comparison — item 138's A7,
  inherited):** `tests/committed_artifact_guard.py`'s five `GROUNDS` still
  describe no float-free derived artifact and
  `tests/test_134_decision_table_evidence_companion.py`'s AC16 pins that count.
  So AC3 compares **parsed** payloads, AC6 compares Markdown against the
  committed JSON structurally, and byte-equality is asserted only between two
  freshly generated files (AC4) — a determinism check. No `ALLOWLIST` or
  `GROUNDS` edit; the open insight (2026-09-02, item 138) stays open for its
  own carrier.
- **A6 (measured counts are provenance, not assertions):** the Description's
  7-of-10, the per-rule availability table, the five-rule geometric set, and
  the `fuse` probe values are the 2026-09-02 measurement on this tree. Every
  count AC (AC9, AC14, AC16, AC18, AC26, AC27) asserts agreement with a fresh
  measurement, never a literal, because item 140 (an allowlisted co-detection),
  item 141 (a widened ladder base) and any future corpus item legitimately move
  them. Item 138's A9 records the worked example: commit `b1c593c` moved that
  item's figures within a day while every derived AC stayed true as written.
- **A7 (availability is measured over *leaf* paths, and container paths never
  count):** `catalogue.iter_leaf_paths` yields leaves only, so a catalogued
  container path such as the bare `per_label` never appears in a record's leaf
  set and is excluded from both sides of the availability fraction. Measured
  2026-09-02: this is why `bounds` reads 5/6 rather than 6/6 and
  `reference_delta` reads 0/11 even though its consumed set contains
  `per_label`. No registered rule's consumed set is *entirely* containers
  today, so no rule reads a spurious `0`; AC17 is the guard that makes such a
  future rule fail rather than be silently misclassified.
- **A8 (a string that asserts a fact is held to that fact, never to a length
  floor):** `docs/aide/insights.md`'s 2026-09-02 entry records the defect this
  discipline exists for. AC20/AC29 check content against live state and AC21
  forbids any character-count threshold in this item's tests — the same
  contract item 138's AC31 adopted, extended here to the operator reason and
  its three independent tokens.
- **A9 (item 138's `_row_for_rule` scans the whole document, so section order
  is load-bearing):** `tests/test_138_traceability_matrix.py::_row_for_rule`
  returns the **first** Markdown table row whose first cell equals the
  `rule_id`. A per-rule exercise table rendered *before* the
  `## Rules -> section 6 modes` table would silently hand that helper the wrong
  row and turn item 138's AC5 red. AC5 pins the ordering and the invariant from
  this item's side so the constraint is enforced, not remembered.
- **A10 (`build_matrix()` gets slower, measurably, and no cache is
  introduced):** measured 2026-09-02, `build_matrix()` costs ~0.6 s today; the
  exercise work adds ~1.7 s (nine geometric cases plus one reconstruction),
  ~0.8 s (four intensity cases) and ~0.01 s (the `fuse` probe), for ~3.1 s per
  build. `tests/test_138_traceability_matrix.py` calls `build_matrix()` 42
  times without a shared fixture, so that module grows by roughly 105 s. A
  module-level cache was **rejected**: item 138's and this item's adversarial
  tests monkeypatch the registry, the manifests and `MODE_RUNGS` and require
  re-derivation, and a cache would silently defeat exactly the tests that prove
  the report is live. A `build_matrix(*, exercise=False)` default was also
  rejected — it would make item 138's AC4 ("the committed JSON is a fresh
  build") false and force an edit to another item's test. This item's own tests
  use a module-scoped fixture; the unfixtured 42 calls in item 138's module are
  recorded in `docs/aide/insights.md` for a later carrier, not fixed here.
- **A11 (no human gate):** every input is committed state on this tree and
  every judgement recorded here is an engineering one grounded in code, a
  committed manifest, or a stage decision already recorded in `roadmap.md` /
  `progress.md`. Nothing needs a person's decision or an out-of-band
  prerequisite, so no row is added to `progress.md`'s `## Human gates` table.
- **A12 (engine 1.37.0):** `aide check`'s `.gitattributes` lint resolves a
  fixture path through the test's AST; both artifact paths are already pinned
  (A1), so it stays silent for this item with no `.gitattributes` edit.
- **A13 (control cases are labelled, not judged):** the geometric
  `clean_control` (`failure_mode == 0`) and the intensity `clean_hu`
  (`plausible == true`) fire nothing, correctly. The report labels them
  `is_control`, derived from those live manifest fields, and the exercise
  directions' completeness is scored over **rules and operators**, never over
  cases — asserting that a control fires nothing is the specificity ceiling,
  which is item 140's, not this item's.

## Implementation Steps

1. **Extend `src/segfacet/traceability.py`'s docstring** with the two exercise
   directions, their completeness contract (both complete, always — a hole in
   either is a defect), the scope fence (this module reports; it adds no corpus
   case and attaches no reference), and the section-order constraint A9 names.
   Bump `SCHEMA_VERSION` to `"1.1"` (additive).
2. **Authored constants.** `UNEXERCISED_CLASSES = ("input-absent",
   "input-present-never-fired")`; `RULE_MECHANISMS: Dict[str, str]` for the
   unexercised rules; `OPERATOR_REASONS: Dict[str, str]` for the unused
   operators; and two qualifier strings for the new Markdown sections. **Every
   authored string must name a token AC20/AC29 can re-derive** — a dotted
   `segfacet.…` attribute, a manifest `case_id`, a catalogued feature path, a
   registered `rule_id`, or a `FAILURE_MODE_NAMES` key — spelled exactly as
   live state spells it, and **must contain no date** (item 138's AC28 forbids
   a `YYYY-MM-DD` anywhere in either artifact). Write no sentence whose only
   defence is its length, and **assert no factual claim about another module,
   docstring or artifact without measuring it in this same change** — the
   `fuse` reason's `bounds` clause is the worked example: measure it with the
   counterfactual probe (step 6) rather than repeating the docstring.
3. **Frozen record dataclasses**, matching the module's existing style:
   `CorpusRecord(name, manifest_path, case_count, control_case_ids)`,
   `RuleExerciseRecord(rule_id, state, exercised_by, exercised_case_count,
   availability, unexercised_class, mechanism)`,
   `OperatorProbe(failure_mode, expected_rule_ids, expected_verdict,
   pipeline_rule_ids, failed, error_type)`,
   `OperatorExerciseRecord(name, class_name, state, cases, probe,
   mode_already_covered_by, reason)`, and an `ExerciseReport` holding the three
   mappings plus two `DirectionReport`s.
4. **`_build_rule_exercise()` — the geometric corpus.** Deferred imports.
   For each case of `synth.corpus.load_manifest()`: build the record via
   `synth.regression.loaded_seg_image` + `pipeline.extract_feature_record`
   (so availability and firing are measured on the *same* record), run
   `heuristics.run_rules` over it, and record `("geometric", case_id,
   "pipeline")` for every fired `rule_id`. For a case whose `detection` is
   `"reconstructed_record"`, additionally call
   `synth.regression.reconstructed_findings` and record `("geometric",
   case_id, "reconstruction")`.
5. **`_build_rule_exercise()` — the intensity corpus.** For each case of
   `synth.intensity.load_intensity_manifest()`: `io.load_case` the fixture
   pair, then `pipeline.run_qc_with_intensity(seg, scan, config,
   reference=None, enable_pyradiomics=False)`; reconstruct the rule record as
   `{**features_block, "image_features": image_features_block}` for the
   availability measurement, and record `("intensity", case_id, "pipeline")`
   for every fired `rule_id`. Load the manifests through the module's own
   private accessors so AC11/AC12 can monkeypatch them.
6. **Availability and classification.** Per corpus, take one representative
   record's `catalogue.iter_leaf_paths` (they are shape-identical across a
   corpus's cases — assert it rather than assume it) and intersect with each
   rule's catalogued consumed paths. Classify each unexercised rule
   `input-absent` when every corpus's available count is `0`, else
   `input-present-never-fired`. A rule that is unexercised and carries no entry
   in `RULE_MECHANISMS` is a hole in `rule_exercise` (AC23).
7. **`_build_operator_exercise()`.** For each `perturbation_names()` entry:
   collect its `CASE_RECIPE` case ids. If empty, probe — construct with
   defaults, apply to `synth.clean_gt.build_clean_spine()` with `seed=0`, read
   the returned `Expectation`, and run the probed label map through
   `pipeline.run_qc` to record `pipeline_rule_ids`; wrap both in a guard that,
   on any exception, records `failed=True` and `type(exc).__name__` only — never
   the message, which could carry a path (AC32, item 138's AC28). Derive
   `mode_already_covered_by` from the geometric manifest. An unused operator
   with no `OPERATOR_REASONS` entry is a hole in `operator_exercise` (AC31).
8. **`matrix_to_dict`** gains the `exercise` block (corpora / rules /
   operators, each keyed by name, sorted) and `directions` gains
   `rule_exercise` and `operator_exercise`. Integers and strings only — no
   float leaf, no date, no absolute path (AC28, AC33, and item 138's AC28).
9. **`render_markdown`** gains two sections **after** `## Features -> rules`
   (never before `## Rules -> section 6 modes` — A9): `## Rule corpus
   exercise` (`Rule | State | Exercised by | Availability | Class | Mechanism`)
   followed immediately by its qualifier, and `## Operator corpus exercise`
   (`Operator | State | Cases | Probed mode | Probed rules | Reason`) followed
   immediately by its qualifier.
10. **Regenerate and commit both artifacts** —
    `.venv/bin/python -m segfacet.traceability` — and confirm the result
    against the Description's 2026-09-02 measurement, investigating (not
    silencing) any divergence. No `.gitattributes` edit is needed (A1).

## Authorised paths

**May change:**

- `src/segfacet/traceability.py` — the generator gains the two exercise directions (AC1–AC33).
- `docs/aide/traceability_matrix.generated.json` — the regenerated matrix, now carrying `exercise` (AC1, AC3, AC4, AC33).
- `docs/aide/traceability_matrix.generated.md` — its rendered form, now carrying the two exercise sections (AC4, AC5, AC6, AC33).
- `tests/test_139_corpus_exercise_report.py` — this item's test module.

**Asserts against:**

- `tests/corpus/manifest.json` — the nine geometric cases; AC10, AC13, AC14, AC29 and AC30 read its `case_id` / `failure_mode` / `detection` fields. Read-only: no case is added, removed or edited.
- `tests/corpus/intensity/manifest.json` — the four intensity cases; AC10, AC11, AC12 and AC19 read it. Read-only — AC11/AC12 remove cases from what the *generator loads*, via a monkeypatched loader, never from the committed file.
- `src/segfacet/synth/corpus.py` — `CASE_RECIPE` and `load_manifest`, the source of AC26's used/unused split; unchanged.
- `src/segfacet/synth/perturbation.py` — the operator registry (`perturbation_names`, `get_perturbation`) and `FAILURE_MODE_NAMES`, which AC24, AC27 and AC29 read; unchanged.
- `src/segfacet/synth/component_shape.py` — `FusePerturbation`, the one unused operator AC26/AC27 probe; unchanged, and no case is added for it.
- `src/segfacet/synth/regression.py` — `pipeline_findings`, `reconstructed_findings` and `loaded_seg_image`, the committed geometric harness AC9/AC13/AC14 drive. Unchanged: an intensity sibling of `pipeline_findings` arguably belongs here, but item 140 edits `verify_case` in this same file, so this item keeps its intensity drive private to `traceability.py` (recorded in `docs/aide/insights.md` for a later carrier).
- `src/segfacet/synth/intensity.py` — `load_intensity_manifest` and `INTENSITY_CORPUS_DIR`; unchanged.
- `src/segfacet/pipeline.py` — `extract_feature_record`, `run_qc` and `run_qc_with_intensity`'s five-tuple return shape, which A3 and step 5 depend on; unchanged.
- `src/segfacet/catalogue.py` — `build_catalogue` and `iter_leaf_paths`, the whole availability derivation (AC16, AC18, AC19); unchanged, and neither catalogue artifact is regenerated.
- `src/segfacet/heuristics/*.py` — the ten registered rules and `run_rules`; AC7, AC20 and AC23 read the registry, and no rule, threshold or declaration is edited.
- `src/segfacet/reference/artifact.py` — `bundled_default_reference`, named in the `input-absent` mechanisms as the reference the repo ships but no harness passes; AC20 resolves it as a live dotted attribute. Read-only, and nothing attaches it.
- `tests/test_138_traceability_matrix.py` — not edited; AC5 pins the whole-document `_row_for_rule` invariant it depends on (A9), and its AC4/AC6/AC28/AC29 tests re-run against the grown artifacts as the standing guard for schema hygiene.
- `tests/committed_artifact_guard.py` — A5 keeps `GROUNDS` at five members with no `ALLOWLIST` entry for either artifact; read-only.

## Testing Strategy

New module: **`tests/test_139_corpus_exercise_report.py`**, one focused test per
AC (AC7/AC8/AC15/AC17/AC18 parametrised over the ten rules, AC24/AC25/AC26 over
the ten operators), building the matrix once through a **module-scoped fixture**
(A10) and re-deriving every asserted value in-session rather than comparing to a
literal. Plus:

- **Adversarial — the intensity corpus is genuinely read (AC11, AC12).**
  Monkeypatch the generator's intensity-manifest accessor to drop one case, then
  all three firing cases, and confirm the report moves both times. This is the
  defect the queue names explicitly: a report reading only
  `tests/corpus/manifest.json` would call `intensity` unexercised and be wrong.
- **Adversarial — a rule hole (AC23).** Register a stub rule (registry
  snapshot/restore, the house pattern from `tests/test_026_rule_engine_core.py`)
  that fires nowhere and carries no mechanism; `rule_exercise` reports
  `complete: false` naming it.
- **Adversarial — an operator hole (AC31).** Register a stub `Perturbation`
  used by no `CASE_RECIPE` entry and carrying no reason; `operator_exercise`
  reports `complete: false` naming it.
- **Adversarial — a stale mechanism (AC22).** Monkeypatch an unexercised rule's
  mechanism to (a) a long sentence naming nothing live and (b) one naming
  `reference_deltas`, one character off a real `rule_id`; the resolvable-token
  check fails both. A length floor would pass both — that is the point (A8).
- **Adversarial — a wrong availability derivation (AC17).** Monkeypatch the
  availability of an *exercised* rule to zero and confirm the self-consistency
  guard fails: a rule that fired cannot have had no input.
- **Adversarial — a probe that raises (AC32).** Monkeypatch the unused
  operator's `apply` to raise; the record carries the exception class name and
  no message, path or traceback, and the operator still needs its reason.
- **Adversarial — a probed mode nothing covers (AC30).** Monkeypatch the probe
  to report a `failure_mode` no committed case carries and confirm
  `mode_already_covered_by` is empty rather than silently reused.
- **Adversarial — section order (AC5).** Assert directly that
  `## Rules -> section 6 modes` precedes both exercise headings and that the
  first `rule_id`-first-cell row is the declaration row, so the ordering
  constraint fails here rather than in item 138's module (A9).
- **Determinism / immutability.** Two `build_matrix()` calls in one session
  return equal exercise reports (AC28); the artifacts regenerate byte-identically
  (AC4); the exercise records are frozen dataclasses/tuples and refuse in-place
  mutation; `matrix_to_dict` returns a fresh tree each call.
- **Edge cases.** A rule consuming zero catalogued paths yields an availability
  of `0/0` rather than raising; an operator whose `cases` list is a singleton
  renders a well-formed row; a corpus whose loaded manifest has zero cases
  yields a case count of `0` rather than a division or an index error.
- **Portability.** No absolute path literals; committed artifacts addressed from
  `Path(__file__).resolve().parent.parent`; every regeneration writes into
  `tmp_path`, never over a committed copy; **no test compares a committed
  file's bytes or text against a freshly computed value** (A5) — this module
  must not be what turns `tests/committed_artifact_guard.py` red.

**Existing tests to reconcile — none requires editing**, but five constrain what
this item may do and were checked against this tree on 2026-09-02:

- `tests/test_138_traceability_matrix.py::test_ac5_markdown_rows_agree_with_json_for_every_mode_and_rule`
  — its `_row_for_rule` helper scans the **whole** document for the first row
  whose first cell is the `rule_id`. Rendering the per-rule exercise table before
  the declaration table turns it red. AC5 is the guard (A9). **Verify, do not
  edit.**
- `tests/test_138_traceability_matrix.py::test_ac4_committed_json_parses_to_a_fresh_build`
  — requires the committed JSON to equal `matrix_to_dict(build_matrix())`, which
  is why A10 rejects an `exercise=False` default. Regenerating both artifacts in
  step 10 keeps it green. **Verify, do not edit.**
- `tests/test_138_traceability_matrix.py::test_ac28_committed_artifacts_carry_nothing_environment_dependent`
  — forbids any float leaf, any `YYYY-MM-DD`, the repo root, a drive-letter
  prefix and this machine's hostname in either artifact. The new section is
  integers and strings only, and no authored string may carry a date (step 2).
  **Verify, do not edit.**
- `tests/test_134_decision_table_evidence_companion.py::test_ac16_committed_artifact_guard_clean_and_vocabulary_unextended`
  — runs the guard over all of `tests/` and pins `GROUNDS` at five members. A5's
  parsed-comparison scheme is what keeps it green. **Verify, do not edit.**
- `tests/test_105_golden_decision_table.py::test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions`
  (and its `== 20` count) — walks `tests/` for non-`.py` files. This item adds
  none: both artifacts live under `docs/aide/`. **Verify, do not edit.**

No test anywhere pins the geometric corpus's per-rule firing set, the operator
registry's used/unused split, or `SCHEMA_VERSION`'s value, so nothing else
changes behaviour under this item. Two suite-timing notes for the validator:
`tests/test_138_traceability_matrix.py` will run measurably slower (A10), and
that is expected, not a regression.

## Validation

Beyond the suite, observe the report directly (no `[validation]` profile needed
— CPU-only, and A4's `enable_pyradiomics=False` pin means the `pyradiomics`
profile is deliberately irrelevant here):

1. `.venv/bin/python -m segfacet.traceability` — regenerates both artifacts in
   place; a clean `git diff` afterwards is the byte-reproducibility claim
   observed rather than asserted.
2. `git diff --stat docs/aide/traceability_matrix.generated.json docs/aide/traceability_matrix.generated.md`
   — expect no change on a re-run of step 1.
3. Read `## Rule corpus exercise` in
   `docs/aide/traceability_matrix.generated.md` end to end and confirm by eye:
   ten rule rows; seven `exercised`; `overlap` exercised via
   `mode8_force_overlap` on the **reconstruction** path; `intensity` exercised
   by three intensity-corpus cases; `bounds` unexercised as
   `input-present-never-fired`; `reference_delta` and
   `intensity_reference_delta` unexercised as `input-absent` with mechanisms
   naming `run_qc` / `run_qc_with_intensity` and `bundled_default_reference`.
4. Read `## Operator corpus exercise` and confirm: ten operator rows; nine
   `used`; `fuse` `unused`, its probed mode `2`, its probed rules
   `fragmentation`, and its reason naming `mode2_fragment`.
5. `.venv/bin/python -c "import json;d=json.load(open('docs/aide/traceability_matrix.generated.json'));print(d['directions']['rule_exercise'],d['directions']['operator_exercise'])"`
   — expect both `complete: true` with empty holes.
6. `python .aide/scripts/aide.py check` — expect no new warning, and in
   particular no `.gitattributes` warning (both paths are already pinned).

## Dependencies

- **Item 138** — the generator module, the two committed artifacts, their
  `.gitattributes` pins, the `DirectionReport` shape, the JSON/Markdown
  serialisation contract, and the parsed-comparison scheme this item extends
  rather than re-invents.
- **Item 136** — the `RuleModeDeclaration` seam and `iter_rule_declarations`,
  which item 138's rule direction reads and beside which the exercise state is
  rendered.
- **Item 137** — the disposition of the four mode-less rules, without which the
  rule rows this item adds columns to would carry a `pending` state.

**Downstream:** item 142 (Stage 20 validation) regenerates this artifact from a
clean tree and quotes its exercise counts as the honest end-to-end statement
(**G7**); item 140's specificity ratchet reads the same per-case firing sets
this item measures, and will adjudicate the `(mode6_crop_at_border, mislabel)`
co-detection this item only records.

## Decisions & Trade-offs

To be updated during implementation.
