# Item 149 — The traceability matrix becomes the conformance report

> **Created:** 2026-09-04 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 149
> **Objectives:** G2 (detect catalogued failure modes), G7 (evaluable and
> regression-testable), G8 (extensible — the generated artifacts become
> conformance reports over one authored record)
> **Suggested branch:** `aide/149-the-traceability-matrix-becomes-the`

---

## Description

Stage 30 **D5**. Item 138's `build_matrix` (`src/segfacet/traceability.py`) was
built as a **cross-check of five partial sources**: it could report that the
sources disagreed but could not adjudicate, because no document defined the
modes. Items 144–148 authored that document
(`src/segfacet/failure_modes.SPECIFICATION`) and collapsed the five sources onto
it. This item re-points the matrix at the specification as its **primary
source**, turning the generated artifact into the **conformance report**
[`vision.md`](../vision.md) §6 describes: per mode the *derived* lifecycle
status and the *authored* per-edge evidence rungs, and — per corpus case, across
**both** committed corpora — the **expected** firing set beside the **measured**
firing set, with agreement scored. A disagreement is a failure that names the
case, the expected set and the measured set. That is the check none of
queue-019's shape tests could express: a length floor and a resolvable-token
floor both test a claim's *shape*; running the case and comparing the sets tests
its *truth*.

Four concrete defects recorded against the current artifact are closed here,
each measured on `aide/queue-020` at this item's base (2026-09-04):

1. **The two path columns are conflated.** `ModeRecord.feature_paths` is the
   union of the Stage-18 metric anchor paths with *every* leaf path every
   declaring rule consumes, so gate 3 decision 1 ("the metric anchor path and
   the rule's read path are two separate, separately-labelled columns") holds
   only for the anchor half. Item 148 shipped the missing per-path claim —
   `RuleModeDeclaration.consumed_paths`, each pair classified `signal` /
   `bookkeeping` / `not-read` — so the read-path column is now derivable from
   the **signal-classified** paths per rule, and nothing else.
2. **`cases` and `pipeline_detected` scan the geometric corpus only.**
   `build_matrix` derives both from `synth.corpus.load_manifest()` alone, so
   mode 9 renders `pipeline_detected: false` and `cases: []` while
   `docs/aide/failure_modes.generated.md` records the same mode `validated`
   with three agreeing intensity-corpus cases — two committed conformance
   artifacts disagreeing about one mode, at the artifact item 150 signs off
   (`insights.md`, item 146, 2026-09-04).
3. **The rule-attribution column is geometric-only for the same reason.**
   Attribution is derived from `catalogue.scan_synth_rule_mode_map()`, an AST
   scan matching `Expectation(...)` literals with an int-literal
   `failure_mode=`; the intensity corpus's cases are `_RecipeEntry(...)`
   literals, so mode 9 renders `intensity (analytic)` directly beside a
   `synthetic-demonstrable` rung stating that three committed intensity cases
   drive `intensity` end-to-end (`insights.md`, item 148, 2026-09-04). With the
   specification primary, attribution is derived from its `corpus_cases`, which
   span both corpora.
4. **The committed-artifact guard is blind to the modules that compare these
   artifacts.** `tests/committed_artifact_guard.py` resolves a module root only
   from a literal `Path(__file__)….parent.parent` chain, so the equally common
   `Path(__file__).resolve().parents[1]` idiom (and test_143's two-hop
   `_TESTS_DIR` → `_REPO_ROOT`) resolves to nothing and every committed path
   built from it is skipped **in silence** (`insights.md`, items 143 and 144).
   `tests/test_143_s_axis_correction.py`'s AC15 byte-compares
   `traceability_matrix.generated.md` against its committed copy today with no
   allowlist entry and no guard visibility at all.

Two test-hygiene items the queue settles here rather than after a third
extension. `build_matrix` becomes materially more expensive — it now drives 13
corpus cases through the pipeline — and
`tests/test_138_traceability_matrix.py` calls it **47 times with no shared
fixture** (measured 2026-09-04; the insight recorded 42 before item 147's
extension), so the call-count discipline is set now as **one fixture per
monkeypatch group**, asserted, and explicitly **never** a cache inside the
generator, which would defeat exactly the adversarial tests that prove the
report is live. And `committed_artifact_guard.GROUNDS` gains its sixth member,
`no-float-leaf` — the one artifact shape whose byte-exact fresh-vs-committed
comparison is unconditionally safe was the shape that could not be allowlisted,
so item 134 and item 138 both routed around it by comparing `json.loads`
payloads. Both generated failure-mode artifacts are float-free (measured
2026-09-04: **0 float leaves** in `traceability_matrix.generated.json` and 0 in
`failure_modes.generated.json`), so both make the byte-exact claim **under** the
guard instead of beside it.

**This item is not.** It builds **no** per-rule and **no** per-operator
**exercise columns** — item 139's deliverable stays Stage 20's, re-specified
against this output (AC33 makes the fence observable). It adopts no specificity
ratchet (item 140) and touches no `eval/` module (item 141). It changes no rule,
threshold, extractor, verdict, report schema or CLI behaviour, authors no mode
fact of its own, and adds no corpus case. It does **not** re-classify any
`ConsumedPath`: the `stage3.per_label_offsets[].{dx,dy,dz}_mm` `signal` vs
`bookkeeping` question recorded at `insights.md` (item 148, 2026-09-04) is an
authored-claim change that moves `feature_catalogue.generated.*`, and it is left
for the maintainer reading the rendering at item 150 (**A9**).

## Acceptance Criteria

- [ ] **AC1: the specification is named as the primary source.**
      `matrix_to_dict(build_matrix())` carries a top-level
      `"primary_source"` whose value is the string
      `"src/segfacet/failure_modes.py"`, the module `_NOTE` names the authored
      specification as the matrix's primary source, and both rendered artifacts
      carry that name.
- [ ] **AC2: the schema version is bumped.** `traceability.SCHEMA_VERSION ==
      "1.1"` and the JSON payload's `"schema_version"` equals it. (No consumer
      pins the old value — measured 2026-09-04: no occurrence of the matrix's
      `schema_version` outside the module and its own artifacts.)
- [ ] **AC3: no retired rung constant is read.** `src/segfacet/traceability.py`
      binds none of `MODE_RUNGS`, `ModeRung`, `RUNGS` or `RUNG_LABELS` as a
      module-level name and contains no dict literal keyed by int mode number
      carrying a rung string; the names may appear only inside the retirement
      comment. Every rung the matrix renders is read from
      `segfacet.failure_modes`.
- [ ] **AC4: every mode row carries its derived status.** Each mode record's
      `status` equals `failure_modes.derive_status(SPECIFICATION[mode])` and is
      a member of `failure_modes.STATUSES`; the value is rendered in both
      artifacts.
- [ ] **AC5: the authored status is rendered beside the derived one.** Each
      mode record also carries `authored_status` equal to
      `SPECIFICATION[mode].status`, so a reader can see the two independently;
      the mode-8 / mode-10 rows show the two values a reader must be able to
      tell apart (`specified` / `proposed` authored, versus what live state
      derives).
- [ ] **AC6: per-edge rungs are rendered per mode.** Each mode record carries
      one `edge_rungs` entry per `IntendedRule` in
      `SPECIFICATION[mode].intended_rules`, in that tuple's order, each entry
      carrying `(rule_id, detector, evidence_rung)`; the rendered set equals the
      specification's edges for that mode exactly — no edge added, none dropped.
- [ ] **AC7: the derived mode rung stays a separate, explicit field.** Each mode
      record's `rung` equals `failure_modes.derive_mode_rung(SPECIFICATION[mode])
      or ""`, is serialised as JSON `null` when absent (mode 10) and rendered as
      an explicit `(none)` in the markdown — never as a blank cell
      indistinguishable from a failed lookup.
- [ ] **AC8: the anchor column and the read-path column are separate and
      separately labelled.** The mode record carries `anchor_paths` and
      `read_paths` as two distinct fields; the markdown mode table carries the
      two headers verbatim — `Stage-18 metric anchor paths` and `Rule signal
      read paths` — and **no** field or column unions the two. `feature_paths`
      (the conflated union) is gone from the record and from both artifacts.
- [ ] **AC9: a mode whose two columns differ renders both.** For mode 4,
      `anchor_paths == ("stage3.monotonic_consistency.is_monotonic",)` while
      `read_paths` contains `stage3.monotonic_consistency.non_monotonic_pairs[]`
      and does **not** contain the anchor path; for mode 7,
      `anchor_paths == ("relationships.is_continuous",)` while `read_paths ==
      ("relationships.out_of_order_labels[]",)`. Both rows render both cells.
- [ ] **AC10: the read-path column is derived from signal-classified paths per
      rule.** `read_paths` for a mode equals the sorted union, over the rules
      whose `RuleModeDeclaration.modes` contains that mode, of the leaf paths
      that rule classifies `"signal"` (`CatalogueEntry.mode_roles`). Nothing
      classified `bookkeeping` or `not-read`, and no unclassified path, reaches
      the column: mode 1's `read_paths` contains
      `reference_delta.{label}.features.physical_volume_mm3.robust_z` and does
      **not** contain `reference_delta.{label}.level_name` or
      `reference_delta.lower_pct`.
- [ ] **AC11: the granularity qualifier no longer claims rule-granularity.**
      The mode record's `granularity` is `"signal"` and its qualifier states
      that a path's presence means a rule declaring this mode classifies that
      path `signal`, and that the Stage-18 metric anchor is a separate column
      that is never merged in; the qualifier renders immediately after the mode
      table in the markdown and in the JSON, and the retired rule-granular
      sentence appears in neither artifact.
- [ ] **AC12: an unclassified consumed path is reported, not silently dropped.**
      The matrix folds `catalogue.path_classification_conflicts()` into a
      `classification_conflicts` field rather than re-deriving it; with a
      declaration monkeypatched to drop one `ConsumedPath`, the field names both
      the rule and the path and the matrix's `conformant` flag is `False`.
- [ ] **AC13: one conformance row per manifest case, across both corpora.** The
      matrix carries a `conformance.cases` entry for **every** case in
      `tests/corpus/manifest.json` **and** every case in
      `tests/corpus/intensity/manifest.json` (13 today: 9 geometric, 4
      intensity), each carrying `corpus`, `case_id`, `mode`, `expected_firing`,
      `measured_firing`, `agrees` and `expected_source`.
- [ ] **AC14: an unspecified mode-carrying case is a named hole.** A manifest
      case whose `failure_mode >= 1` that no `ModeSpec.corpus_cases` entry
      covers renders with `expected_source == "unspecified"`, `agrees == False`,
      and is named (corpus + case_id) in `conformance.unspecified_cases`;
      demonstrated adversarially by monkeypatching a mode's `corpus_cases` to
      `()`. On the committed tree `unspecified_cases` is empty.
- [ ] **AC15: the clean controls are scored, with their source labelled.** The
      two `failure_mode == 0` cases (`clean_control`, `clean_hu`) render with
      `expected_source == "manifest-clean-control"`, `expected_firing == ()`
      and a measured set; the label distinguishes them from a specification-
      sourced expectation, since §6 defines no mode 0.
- [ ] **AC16: agreement is scored and the committed tree is conformant.**
      `conformance` carries `agree_count`, `disagree_count` and a `conformant`
      boolean; on the committed tree `disagree_count == 0`, `agree_count == 13`
      and `conformant is True`.
- [ ] **AC17: a deliberately altered expected set fails, naming case, expected
      and measured.** With `SPECIFICATION[3]`'s corpus case monkeypatched to
      `expected_firing=("coverage",)`, `conformance.disagreements` carries one
      entry naming `mode3_inject_islands`, the expected set `("coverage",)` and
      the measured set `("fragmentation",)`; `conformant` is `False`, and the
      test that asserts conformance over the live tree fails with all three in
      its message.
- [ ] **AC18: `cases` and `pipeline_detected` are derived across both corpora.**
      Mode 9's `cases` lists `implausible_metal`, `implausible_soft_tissue` and
      `degenerate_uniform`, each with `detection == "intensity_pipeline"`, and
      its `pipeline_detected` is `True`; mode 8 stays `False` (its only case is
      `detection == "reconstructed_record"`); no geometric mode's `cases` tuple
      changes from the base artifact.
- [ ] **AC19: attribution is derived from the specification's corpus cases,
      across both corpora.** A `(mode, rule)` edge is attributed `"corpus"` iff
      at least one of that mode's `corpus_cases` lists the rule in its
      `expected_firing`, and `"analytic"` otherwise; `scan_synth_rule_mode_map`
      no longer decides the column. Mode 9's `intensity` renders `corpus` and
      its `intensity_reference_delta` renders `analytic`; every mode 1–8
      attribution is byte-identical to the base artifact's (measured
      2026-09-04 — exactly one row moves).
- [ ] **AC20: both artifacts regenerate byte-identically.** Two consecutive
      `main()` runs into `tmp_path` produce byte-identical JSON and markdown,
      and each matches its committed copy byte-for-byte.
- [ ] **AC21: neither artifact carries a float leaf.** Walking the fresh
      `matrix_to_dict()` tree and the committed JSON payload yields zero
      `float` instances; the same holds for `failure_modes.specification_to_dict()`
      and `docs/aide/failure_modes.generated.json`. These two tests are what
      discharge the new `no-float-leaf` ground.
- [ ] **AC22: the LF pin holds for all four generated paths.** Neither
      artifact's bytes contain `\r`, and `.gitattributes` pins
      `docs/aide/traceability_matrix.generated.{json,md}` and
      `docs/aide/failure_modes.generated.{json,md}` `text eol=lf`.
      `python .aide/scripts/aide.py check` reports no `.gitattributes` warning
      for any path this item touches.
- [ ] **AC23: `GROUNDS` gains a sixth member.** `committed_artifact_guard.GROUNDS`
      has exactly six members, the sixth being `"no-float-leaf"`, and the
      module docstring records what discharges it (the artifact's own
      no-float-leaf test) and why a float-free derived artifact is
      unconditionally byte-safe.
- [ ] **AC24: both artifacts are allowlisted under it, with reasons.**
      `ALLOWLIST` carries four entries — `docs/aide/traceability_matrix.generated.json`,
      `….md`, `docs/aide/failure_modes.generated.json`, `….md` — each with
      `ground == "no-float-leaf"` and a non-empty single-line reason naming the
      discharging test.
- [ ] **AC25: the guard actually sees those comparisons (non-vacuity).** With
      `guard.ALLOWLIST` monkeypatched to drop the four new entries,
      `iter_violations(tests/)` reports at least one violation naming
      `docs/aide/traceability_matrix.generated.md` and at least one naming
      `docs/aide/failure_modes.generated.md`. Before this item's root-idiom
      normalisation the same run reports neither (the blind spot recorded at
      `insights.md`, items 143 and 144).
- [ ] **AC26: the guard is clean as shipped.** With the allowlist as committed,
      `iter_violations(_REPO_ROOT / "tests")` returns an empty list.
- [ ] **AC27: every vocabulary-length pin is updated to six with the reason
      recorded.** `tests/test_134_decision_table_evidence_companion.py` and
      `tests/test_127_committed_artifact_tolerance.py` pin the six-member
      vocabulary (including `no-float-leaf`), `tests/test_138_traceability_matrix.py`'s
      AC29 pin is updated from five to six, its assertion that no allowlist
      entry mentions `traceability_matrix` is inverted to require the entry,
      and each of the three carries a one-line reason naming item 149.
- [ ] **AC28: no `build_matrix()` call sits in a test body.** An AST
      self-inspection test over `tests/test_138_traceability_matrix.py` and
      `tests/test_149_conformance_report.py` asserts that every
      `build_matrix()` call site is lexically inside a function decorated
      `@pytest.fixture`.
- [ ] **AC29: the call-site count is bounded and asserted.** Each of the two
      modules defines a module-level `_BUILD_MATRIX_CALL_SITE_BUDGET`; a test
      asserts the AST call-site count equals it and that it is `<= 20` —
      strictly fewer than the **47** call sites measured in
      `tests/test_138_traceability_matrix.py` at this item's base (2026-09-04).
- [ ] **AC30: the generator holds no cache.** Two `build_matrix()` calls with
      `SPECIFICATION` monkeypatched between them return different matrices, and
      `src/segfacet/traceability.py` contains no `lru_cache`, `functools.cache`
      or module-level memo dict assigned from a `build_matrix` result (AST/source
      scan).
- [ ] **AC31: every adversarial monkeypatch fixture re-derives.** Parametrised
      over the module's patch groups, each patched fixture's matrix differs
      from the shared unpatched fixture's matrix in the patched field — so the
      shared fixture cannot have leaked into a patched test.
- [ ] **AC32: `build_matrix` stays inert at evaluation time.** `run_rules` over
      a clean record returns equal findings before and after a `build_matrix()`
      call, two calls return equal matrices, and mutating a `matrix_to_dict`
      result never leaks into a later call — still true now that the builder
      drives 13 corpus cases through the pipeline.
- [ ] **AC33: no exercise columns are built (scope fence).** Neither artifact
      carries a field or markdown header reporting a per-rule or per-operator
      corpus-**exercise** count, and `src/segfacet/traceability.py` defines no
      such derivation; item 139's deliverable is observably absent.

## Assumptions

- **A1 — "per corpus case, across both committed corpora" means every case in
  both manifests, not only the eleven the specification authors.** Under
  clarify mode `assume`, the wider reading is taken: 9 geometric + 4 intensity =
  13 rows, which makes the clean controls' specificity claim visible and makes a
  manifest case the specification forgot a **named hole** (AC14) rather than an
  invisible omission. The two clean controls carry `failure_mode == 0`, which is
  `failure_modes.CLEAN_CONTROL_NAME` and not a §6 mode, so their expected set is
  sourced from the manifest and labelled `manifest-clean-control` (AC15) rather
  than fabricated into the specification.
- **A2 — the expected-firing source is `SPECIFICATION[mode].corpus_cases`, not
  the manifest's `expected_rule_ids` / `expected_firing`.** Item 145 authored
  the former as the *full* set the case's detection path produces (mode 6
  expects `{border, mislabel}` where the geometric manifest's narrower
  `expected_rule_ids` is `["border"]`). The manifest fields are read only to
  enumerate cases and to source a clean control's empty expectation.
- **A3 — measured firing is obtained through
  `failure_modes.measured_firing(CorpusCaseExpectation)`,** which item 146
  already dispatches on `corpus` then on the manifest case's own `detection`
  (`pipeline` / `reconstructed_record` / `intensity_pipeline`) via
  `synth.regression`. This item composes no private pipeline call of its own —
  the insight warning that item 139 would do so describes a spec that never
  merged (`insights.md`, item 146, 2026-09-03).
- **A4 — committing measured firing sets does not make the artifact
  platform-sensitive.** The corpus defects are gross and far from any threshold,
  and the same sets are already pinned live by `tests/test_041_regression_suite.py`
  and by item 145/146's `case_agrees` tests. The artifact stays float-free
  (AC21), which is the ground the byte comparison rests on.
- **A5 — `build_matrix` becomes materially slower.** It drives 13 cases through
  the pipeline: the insight measured +1.7 s for the geometric corpus and +0.8 s
  for the intensity corpus against a ~0.6 s base (`insights.md`, item 139,
  2026-09-03), so ~3 s per call is the working figure. AC28/AC29's fixture
  discipline is what keeps the two test modules bounded; if the measured cost
  lands materially higher, the budget is lowered, never the discipline dropped.
- **A6 — the `no-float-leaf` ground is discharged by a test, not by an
  assertion in the reason string.** The allowlist reason *names* the discharging
  test; the guard itself performs no float walk (it is a static AST classifier).
  This mirrors how `emission-clamped` names the clamp rather than checking it.
- **A7 (engine 1.37.0) — `aide check`'s `.gitattributes` lint is silent for
  both artifacts today and must stay silent.** All four generated paths are
  already pinned `text eol=lf`; the lint reports nothing for a fixture read with
  `read_text()` + `json.loads` (§6's immune shape), so a clean `aide check` is a
  necessary, not a sufficient, signal — AC22 asserts the pins directly as well.
- **A8 — the root-idiom normalisation is `Path(__file__).resolve().parent.parent`,
  not a change to the guard's classifier.** Teaching `_is_file_root_chain` the
  `parents[N]` subscript shape would be the broader fix and is deliberately not
  taken here: it changes what the guard resolves across **every** test module at
  once, which is a larger blast radius than this item's scope. The insight
  (`insights.md`, item 144, 2026-09-03) stays open for that.
- **A9 — no `ConsumedPath` classification is changed.** `read_paths` renders
  what item 148 authored. The `stage3.per_label_offsets[].{dx,dy,dz}_mm`
  question (`insights.md`, item 148, 2026-09-04) is left for item 150's
  maintainer reading; this item's AC10 example paths are chosen so none of them
  turns on that decision.
- **A10 — no human gate is raised by this item.** Stage 30's gate is item 150's
  deliverable. Gate 3 is ✅ Approved and is an input here, not a blocker.

## Implementation Steps

**The order of steps 1 and 6 is load-bearing** — see **Decisions D1**.

1. **Normalise the repo-root idiom first, before any guard change.** In
   `tests/test_138_traceability_matrix.py`, `tests/test_143_s_axis_correction.py`,
   `tests/test_144_failure_mode_specification.py`,
   `tests/test_145_eight_hypothesised_modes.py`,
   `tests/test_146_ninth_mode_and_first_proposed.py` and
   `tests/test_147_specification_is_the_record.py`, replace
   `Path(__file__).resolve().parents[1]` (and test_143's `_TESTS_DIR` →
   `_REPO_ROOT` two hop) with `Path(__file__).resolve().parent.parent`, the
   only shape `committed_artifact_guard._is_file_root_chain` resolves. Change
   nothing else in those modules at this step.
2. **Run the guard and record what became visible.** With the roots resolvable
   and the allowlist still five-ground, `iter_violations(tests/)` now reports
   the previously-invisible comparisons — expected: test_143's AC15
   (`traceability_matrix.generated.md`) and test_144's AC23
   (`failure_modes.generated.md`). Record the exact list in **Decisions**; it is
   the evidence AC25 is non-vacuous.
3. **Re-point `build_matrix` at the specification.** Add
   `primary_source`, bump `SCHEMA_VERSION` to `"1.1"`, and rewrite `_NOTE` to
   name `src/segfacet/failure_modes.py` as the primary source. Per mode, read
   `derive_status` (→ `status`), `ModeSpec.status` (→ `authored_status`),
   `intended_rules` (→ `edge_rungs`), and keep `derive_mode_rung` (→ `rung`).
   All of it through the module object, never bound by name at import, so a
   test can substitute either and see the matrix follow.
4. **Split the path columns.** Replace `ModeRecord.feature_paths` with
   `read_paths`, derived from `CatalogueEntry.mode_roles`: the sorted union,
   over the mode's declaring rules, of paths that rule classifies `"signal"`.
   Keep `anchor_paths` untouched. Replace `_GRANULARITY_QUALIFIER` with the
   signal-classification qualifier and set `granularity = "signal"`. Fold
   `catalogue.path_classification_conflicts()` into `classification_conflicts`.
5. **Build the conformance direction.** Enumerate both manifests
   (`synth.corpus.load_manifest`, `synth.intensity.load_intensity_manifest`),
   join each case to the specification's `CorpusCaseExpectation` by
   `(corpus, case_id)`, call `failure_modes.measured_firing` for the measured
   set, and emit `conformance` = `cases` (with `expected_source`), `agree_count`,
   `disagree_count`, `disagreements` (each naming case, expected and measured),
   `unspecified_cases`, and a `conformant` flag folding in
   `classification_conflicts`. Re-derive `cases` / `pipeline_detected` per mode
   from **both** manifests, and derive `rule_attribution` from the
   specification's `corpus_cases` instead of `scan_synth_rule_mode_map`
   (which stays read only for `corpus_designated_unregistered_rule_ids`).
6. **Extend `matrix_to_dict` and `render_markdown`.** Mode-table column order:
   `Mode | §6 title | Status (derived) | Status (authored) | Rules (attribution)
   | Per-edge rungs | Evidence rung (derived) | Pipeline-detected | Stage-18
   metric anchor paths | Rule signal read paths`. Add a
   `## Conformance — expected vs measured firing` section with columns
   `Corpus | Case | Mode | Expected firing | Measured firing | Agrees | Source`,
   the counts line, and the disagreement / unspecified / classification-conflict
   lists rendered as explicit `none` when empty.
7. **Regenerate the committed artifacts** with `python -m segfacet.traceability`
   (zero-argument defaults), then verify byte-identity on a second run.
8. **Only now extend the guard**: add `"no-float-leaf"` to `GROUNDS` (sixth
   member) with the docstring paragraph recording what discharges it, and the
   four `ALLOWLIST` entries naming the discharging tests.
9. **Reconcile the pins**: `tests/test_134_….py` and `tests/test_127_….py`
   (five → six, with the reason), and `tests/test_138_….py`'s AC29 (length pin
   and the inverted `traceability_matrix` assertion).
10. **Apply the fixture discipline** to `tests/test_138_traceability_matrix.py`:
    one module-scoped unpatched fixture for every non-patching test, one
    function-scoped fixture per monkeypatch group, the
    `_BUILD_MATRIX_CALL_SITE_BUDGET` constant, and the AST self-inspection test.
11. **Append any out-of-scope finding** as one line in `docs/aide/insights.md`
    and carry on; act on none of it here.

## Authorised paths

**May change:**

- `src/segfacet/traceability.py` — the whole re-point: `SCHEMA_VERSION`,
  `_NOTE`, the qualifier constants, `ModeRecord`, the new conformance
  dataclasses, `build_matrix`, `matrix_to_dict`, `render_markdown` and the
  module docstring. No other module's behaviour changes.
- `docs/aide/traceability_matrix.generated.json` — regenerated (step 7).
- `docs/aide/traceability_matrix.generated.md` — regenerated (step 7).
- `tests/test_149_conformance_report.py` — this item's tests.
- `tests/committed_artifact_guard.py` — the sixth `GROUNDS` member, the four
  `ALLOWLIST` entries and the docstring paragraph. No classifier change (**A8**).
- `tests/test_138_traceability_matrix.py` — root idiom, fixture discipline and
  reconciliation to the new record shape, per **Testing Strategy**.
- `tests/test_143_s_axis_correction.py` — root idiom (step 1) and the stale
  comment that says no allowlist ground exists; nothing else.
- `tests/test_144_failure_mode_specification.py` — root idiom and its stale
  "item 149 adds `no-float-leaf`" comment; nothing else.
- `tests/test_145_eight_hypothesised_modes.py` — the same.
- `tests/test_146_ninth_mode_and_first_proposed.py` — the same, plus
  reconciliation if its AC33 structural comparison is affected.
- `tests/test_147_specification_is_the_record.py` — root idiom only.
- `tests/test_134_decision_table_evidence_companion.py` — the five → six
  vocabulary pin and its reason; reconciliation only.
- `tests/test_127_committed_artifact_tolerance.py` — the `GROUNDS` set pin and
  the `…closed_at_five_members` test name; reconciliation only.
- `docs/aide/insights.md` — appended lines only (step 11); nothing reworded,
  nothing reordered, nothing deleted.

**Asserts against:**

- `src/segfacet/failure_modes.py` — the primary source: AC1/AC4–AC7/AC10 and the
  whole conformance direction read `SPECIFICATION`, `derive_status`,
  `derive_mode_rung` and `measured_firing` live. This item writes nothing here.
- `src/segfacet/feature_docs.py` — `MODE_ANCHOR_PATHS` is the anchor column
  (AC9); deliberately unfiltered and unchanged.
- `src/segfacet/catalogue.py` — `CatalogueEntry.mode_roles` and
  `path_classification_conflicts()` are read live (AC10, AC12); unchanged.
- `src/segfacet/heuristics/rule.py` — `PATH_ROLES` / `consumed_paths` classify
  the read-path column (AC10); unchanged, and no `ConsumedPath` is re-classified
  (**A9**).
- `tests/corpus/manifest.json` — AC13/AC15/AC18 enumerate and drive its nine
  cases; unchanged.
- `tests/corpus/intensity/manifest.json` — the same for its four cases;
  unchanged.
- `docs/aide/failure_modes.generated.json` — AC21's no-float-leaf test reads it
  and AC24 allowlists it; **not** regenerated by this item.
- `docs/aide/failure_modes.generated.md` — AC25's non-vacuity check names it;
  not regenerated by this item.
- `.gitattributes` — AC22 asserts the four `text eol=lf` pins; all four already
  exist and none is added or edited.

## Testing Strategy

New module `tests/test_149_conformance_report.py`, one focused test per AC, with
the same fixture discipline it imposes on test_138 (AC28/AC29 cover both
modules). Heavy work goes through fixtures: **one** module-scoped unpatched
`matrix` fixture, and **one function-scoped fixture per monkeypatch group**.

**Adversarial and edge cases (each must be a live re-derivation, never a
comparison against the committed artifact):**

- *A deliberately altered expected set* — `SPECIFICATION[3]`'s corpus case
  patched to `("coverage",)`: the disagreement names the case and both sets
  (AC17). This is the item's headline check and must fail loudly, not silently
  score 12/13.
- *A mode's `corpus_cases` emptied* — its manifest case becomes an
  `unspecified_cases` hole (AC14), proving the enumeration is manifest-driven
  and not specification-driven.
- *A `ConsumedPath` dropped from a declaration* — `classification_conflicts`
  names rule and path and `conformant` goes `False` (AC12).
- *`derive_status` / `SPECIFICATION` patched* — the rendered status and title
  follow (AC4/AC30), proving no cache.
- *A rule's declaration re-narrowed* — the mode's `read_paths` and
  `rule_attribution` both shrink (AC10/AC19).
- *Determinism / immutability* — two `main()` runs byte-identical; two
  `build_matrix()` calls equal; mutating a `matrix_to_dict` result does not leak
  (AC20/AC32).
- *Degenerate rows* — mode 10 (`proposed`: no edges, no rules, no cases) renders
  `null` rung, `(none)` cells and an empty `edge_rungs`, and does **not** raise
  (AC7); mode 8's `reconstructed_record` case keeps `pipeline_detected False`
  (AC18).
- *Guard non-vacuity* — `ALLOWLIST` patched to drop the four new entries must
  make violations appear (AC25). A test that only asserts the guard is clean is
  an attestation over a blind spot; this is what makes it a check.

**Existing tests to reconcile** (each fails as a direct, mechanical consequence
of this item's own ACs — reconcile, never disable):

- `tests/test_138_traceability_matrix.py` — the largest surface. Every test
  reading `feature_paths` on a mode record (AC8 removes the field), the
  `granularity == "rule"` and rule-granular qualifier pins (AC11), the mode-9
  `pipeline_detected is False` / `cases == []` expectations (AC18), the mode-9
  attribution `analytic` pin (AC19), `test_ac29_committed_artifact_guard_clean_and_grounds_unextended`'s
  `len(guard.GROUNDS) == 5` and its `"traceability_matrix" not in entry.path`
  loop (AC23/AC24/AC27), the markdown header-row pins (AC8), and all 47
  `build_matrix()` call sites (AC28/AC29). Its AC31 mechanism checks and AC2
  unchanged-fence tests stay as they are.
- `tests/test_134_decision_table_evidence_companion.py` —
  `test_ac16_committed_artifact_guard_clean_and_vocabulary_unextended`'s
  `set(guard.GROUNDS)` and `len(...) == 5`, plus the module docstring's "five-member
  `GROUNDS`" sentence.
- `tests/test_127_committed_artifact_tolerance.py` —
  `test_ac12_ground_vocabulary_is_closed_at_five_members` (set literal and name).
- `tests/test_143_s_axis_correction.py` — the comment block explaining that no
  allowlist ground exists for the matrix and that the guard is silent about
  AC15's comparison; both halves are false after this item.
- `tests/test_144_failure_mode_specification.py` — the module docstring's "no new
  `GROUNDS`" claim and `test_ac23_…`'s docstring saying item 149 has not yet
  added the ground.
- `tests/test_145_eight_hypothesised_modes.py` /
  `tests/test_146_ninth_mode_and_first_proposed.py` — the same class of stale
  comment (both name item 149 explicitly), plus test_146's AC33 structural
  comparison if the root normalisation makes it guard-visible.
- Anything the builder finds by running the guard at step 2 — that list is
  authoritative over this hand-written one; the precedent is `insights.md`
  (item 148, 2026-09-04), where a hand-enumerated reconciliation list was a
  strict subset of what the shape change touched. **Sweep every changed test
  module for pinned literals, not only the bullets above.**

## Validation

Beyond the suite — the artifact is the deliverable item 150's maintainer reads,
so it must be observed, not only asserted:

1. `.venv/bin/python -m segfacet.traceability --json /tmp/tm.json --md /tmp/tm.md`
   then `diff /tmp/tm.md docs/aide/traceability_matrix.generated.md` — expect no
   output (byte-identical), and a second run identical to the first.
2. Read the regenerated `docs/aide/traceability_matrix.generated.md`'s
   **Conformance** section: 13 rows, `Agrees` true on every one, the two clean
   controls labelled `manifest-clean-control`, and mode 9's three intensity
   cases present in the mode table with `Pipeline-detected: True`.
3. Confirm the mode-4 and mode-7 rows show **different** values in the
   `Stage-18 metric anchor paths` and `Rule signal read paths` cells — the
   visible form of gate 3, decision 1.
4. `python .aide/scripts/aide.py check` — no `.gitattributes` warning for any
   path this item touches.

No `[validation]` profile is required: everything above runs on the default
CPU-only environment with the committed corpora.

## Dependencies

- **Item 143** (✅) — the corrected S-axis corpus every measured firing set here
  is measured on.
- **Item 144** (✅) — the specification module, its schema and its generated
  rendering (the second artifact allowlisted here).
- **Item 145** (✅) — the eight modes with per-edge `evidence_rung`s and authored
  `expected_firing` per corpus case.
- **Item 146** (✅) — the ninth mode, the intensity manifest's `failure_mode` /
  expected-firing fields, `synth/regression.py`'s intensity sibling, and
  `measured_firing`'s two-corpus dispatch.
- **Item 147** (✅) — `MODE_RUNGS` retired; title, rung and mechanism already read
  live from the specification.
- **Item 148** (✅) — `RuleModeDeclaration.consumed_paths`,
  `CatalogueEntry.mode_roles` and `path_classification_conflicts()`, without
  which the read-path column cannot be derived from signal-classified paths.

**Downstream:** item 150 (maintainer sign-off) reads the rendering this item
completes; item 151 (stage validation) re-runs both artifacts from a clean tree;
items 139–142 are re-specified against this output, and their per-rule /
per-operator exercise columns are deliberately not built here (AC33).

## Decisions & Trade-offs

**D1 — recorded at spec time, binding on the builder: the root-idiom
normalisation lands before the new ground.** `committed_artifact_guard`'s
classifier resolves a module root only from a literal `Path(__file__)….parent.parent`
chain, so while `tests/test_138`, `143`, `144`, `145`, `146` and `147` use
`parents[1]` (or a two-hop `_TESTS_DIR` → `_REPO_ROOT`), every committed path
they build is skipped **in silence** (`insights.md`, items 143 and 144,
2026-09-03). Adding `no-float-leaf` and four `ALLOWLIST` entries while the
blind spot stands would allowlist comparisons the guard cannot see: the new
ground's enforcement would be vacuous, and AC26's "guard is clean" would remain
an attestation over a blind spot rather than a check. Hence Implementation Steps
1–2 precede step 8, and AC25 is written as a non-vacuity proof rather than a
cleanliness assertion.

**D2 — attribution moves from the corpus AST scan to the specification.** The
`"corpus"` / `"analytic"` column was derived from
`catalogue.scan_synth_rule_mode_map()`, which matches only geometric
`Expectation(...)` literals, so mode 9's `intensity` rendered `analytic` beside a
rung asserting three committed intensity cases drive it end-to-end
(`insights.md`, item 148, 2026-09-04). Deriving the column from the
specification's `corpus_cases` — which span both corpora by construction — is
the "primary source" move applied to one more field. Measured 2026-09-04: under
the new definition **exactly one** cell moves (mode 9's `intensity`,
`analytic` → `corpus`); every mode 1–8 attribution is unchanged, which is what
makes the change auditable rather than a re-derivation of unknown blast radius.
The scan is still read, for `corpus_designated_unregistered_rule_ids` only.

**D3 — the remaining entries are updated during implementation.** To be updated
during implementation.
