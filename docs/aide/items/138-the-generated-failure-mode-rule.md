# Item 138 — The generated failure-mode ↔ rule ↔ feature traceability matrix

> **Created:** 2026-09-02 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 20 — Failure-Mode ↔ Feature ↔ Rule Traceability & Specificity Harness
> **Queue:** [`../queue/queue-019.md`](../queue/queue-019.md) · Item 138
> **Objectives:** G2 (every mode has a rule and every rule a mode, stated and enforced), G7 (honest reporting — an evidence rung per mode rather than an unqualified tick)
> **Suggested branch:** `aide/138-the-generated-failure-mode-rule`

---

## Description

Build Stage 20's central artifact: a **generated** traceability matrix over the
eight §6 failure modes, the ten registered rules, and the feature paths each
rule actually consumes. Generated, not hand-maintained — assembled from item
103's catalogue (`segfacet.catalogue.build_catalogue`), the rule registry
(`segfacet.heuristics.iter_rules`), items 136/137's `RuleModeDeclaration`s, the
corpus-derived `rule_id → §6 mode` map
(`segfacet.catalogue.scan_synth_rule_mode_map`) and the committed corpus
manifest — so that no cell of it can go stale without the generator saying so.

**Three directions, scored separately** (roadmap Stage 20's 2026-08-11
clarification), because they do not mean the same thing:

| Direction | Complete? | A hole means |
| --- | --- | --- |
| **mode → rule** | yes, always | a catalogued §6 mode nothing can detect — a defect |
| **rule → mode** | yes, always | a registered rule targeting no catalogued mode — the mode catalogue is short a mode, or the rule is speculative |
| **feature → rule** | **no — by design** | *nothing.* The feature record is an over-broad vector rules select from; a path no rule reads is **inventory, not a gap** |

The artifact must carry that third qualifier **where it reports the count**, in
both the JSON and the Markdown, so a future reader cannot mistake it for a
shortfall.

**Every mode row carries its evidence rung** — the closed three-value
vocabulary the roadmap fixes: `synthetic-demonstrable` ·
`needs-real-data` (the roadmap's *"needs real data, or a corpus the fixtures
cannot express"*) · `structurally-unobservable` (its *"structurally unobservable
in the supported input format"*). Beside the authored rung sits a **derived**
`pipeline_detected` flag read from `tests/corpus/manifest.json`'s `detection`
field, and the two are cross-checked, so a rung that goes stale against the
corpus fails rather than reads well. This is the roadmap's *"'a rule covers this
mode' and 'we have demonstrated it end-to-end' are different claims and each
mode's row carries both."*

Three rungs are fixed by evidence already recorded and are not reopened here:

- **Mode 8 — `structurally-unobservable`.** This is D4's remaining half.
  `progress.md`'s Stage 20 deliverable carries *"⚠️ Superseded in part,
  2026-08-27"*: modes 1 and 4 were one defect (the interpolating spline fit),
  owned and closed by Stage 28, leaving **mode 8 as this stage's to record**. A
  single-channel integer label map cannot assign two labels to one voxel, so
  `overlaps[]` populates only on a map deliberately corrupted to violate that
  invariant, which no real segmenter output can be. The `overlap` rule and the
  six paths it reads are correct and fully wired. `mode8_force_overlap`
  therefore **stays** `detection="reconstructed_record"` in the manifest, with
  the mechanism recorded — it is not to be "fixed", and this item changes no
  corpus case.
- **Modes 1 and 4 — `synthetic-demonstrable`**, as of items 120 and 132
  (verified by item 135's replay). Recorded, not re-litigated. A rung is a
  property of the **mode** — whether its failure has been demonstrated
  end-to-end on the corpus — not of which rules happen to declare it, so
  `reference_delta` joining mode 1 on 2026-09-02 (`b1c593c`) changes mode 1's
  rule list and leaves its rung and `pipeline_detected` untouched
  (`mode1_displace`, `detection == "pipeline"`).
- **Mode 7 — `needs-real-data`**, with its own cap as the mechanism:
  `rank(v) == v - 1` under the TPTBox default admits a single rank descent, so
  §6.7's own `L1 → T12 → L2 → L5` two-descent example is not representable at
  rung 1. Its corpus case *is* pipeline-detected (a single-descent break), which
  is why the rung and `pipeline_detected` are separate fields rather than one.

**The attribution distinction item 137 deferred here.** Item 137's Assumption A7
records that the generated catalogue's `§6 mode(s)` column cannot tell an
*analytic* attribution from a *corpus-corroborated* one, and defers that
distinction to this item's evidence rungs. This matrix carries it per **edge**:
every (mode, rule) pair is tagged `corpus` when the corpus-derived map
designates that rule for that mode, and `analytic` when only the rule's own
declaration claims it. Today exactly **three** edges are analytic —
`(1, reference_delta)`, `(2, bounds)` and `(2, reference_delta)`, item 137's
disposition as corrected by commit `b1c593c` (2026-09-02) — and the six
corpus-corroborated rules' eight edges are `corpus`, for eleven edges in total.
The tag is derived from the **corpus map**, not by inspecting the declaration's
free-form `evidence` tuple; see Assumptions A6 for why, and for this item's
explicit disposition of the three open item-136 review findings.

**Mode → feature is rule-granular, and says so** (A13). A mode's feature-path
list (AC24) is the union of its declaring rules' *whole* consumed sets, so it
inherits item 136's rule-granularity: bookkeeping paths such as
`reference_delta.lower_pct`, `reference_delta.{label}.label` and
`reference_delta.{label}.level_name` carry their rule's modes in the generated
catalogue, and therefore appear in this matrix's mode rows too. This item
**inherits and reports** that granularity rather than working around it — the
mode's feature list is labelled `granularity: "rule"` and carries a qualifier
saying a path's presence in a mode row means *a rule that targets this mode
reads this path*, not *this path alone evidences this mode* (AC33). Narrowing
it would require a per-path mechanism claim no shipped declaration carries;
the finding itself stays with item 136 as its carrier.

**Measured 2026-09-02 on this tree** (the numbers the first generation should
reproduce; the tests assert the derivation, not these literals — A9):

- 10 registered rules, all declared, none pending; 8 modes, every one with ≥1
  declaring rule — so both required directions are complete on the day the
  matrix is born, and the adversarial tests are what prove the holes would be
  reported.
- mode → rule: 1→`mislabel`, `reference_delta` · 2→`bounds`, `fragmentation`,
  `reference_delta` · 3→`fragmentation` · 4→`mislabel` · 5→`coverage` ·
  6→`border` · 7→`sequence` · 8→`overlap`. Eleven edges: eight `corpus`, three
  `analytic`.
- mode → feature (union of the mode's rules' consumed paths plus its anchors,
  AC24), sizes: 1→19 · 2→21 · 3→7 · 4→10 · 5→4 · 6→9 · 7→6 · 8→6.
- feature → rule: 138 catalogued paths, **50** read by ≥1 rule, **88** read by
  no rule, of which **30** carry the derived status `unwired` (the other 58 are
  read by a non-rule consumer or carry a Stage-19 `retune`/`retire` override).
  Per rule: `border` 9 · `bounds` 6 · `coverage` 4 · `fragmentation` 7 ·
  `intensity` 5 · `intensity_reference_delta` 8 · `mislabel` 9 · `overlap` 6 ·
  `reference_delta` 11 · `sequence` 5. Commit `b1c593c` moved no number in this
  bullet: it changed `failure_modes`, never `consuming_rules`.

**What this item is NOT.** It is not the per-rule / per-operator **exercise**
report — which rules fire on which committed corpus cases, across both
manifests — that is item 139, extending this same module and artifact. It does
not adopt the specificity ratchet (item 140), does not touch
`eval/severity_ladder.py` (item 141), and does not tick a `progress.md`
acceptance box (item 142). It adds no corpus case, designates no `Expectation`,
changes no rule, threshold, extractor, verdict, report schema or CLI behaviour,
and regenerates neither catalogue artifact. It does not edit `vision.md` or
`roadmap.md`: §6 stays at eight modes, read and pinned rather than changed.

## Acceptance Criteria

- [ ] **AC1: The generator is a module with a stable public surface.**
  `segfacet.traceability` exposes `build_matrix`, `matrix_to_dict`,
  `render_markdown` and `main` in its `__all__`, each callable, and
  `build_matrix()` takes no required argument.

- [ ] **AC2: Regeneration is zero-argument, and redirectable.**
  `segfacet.traceability`'s default output paths are
  `docs/aide/traceability_matrix.generated.json` and
  `docs/aide/traceability_matrix.generated.md`; `main(["--json", <tmp>, "--md",
  <tmp>])` writes exactly those two files and leaves both committed artifacts
  byte-unchanged.

- [ ] **AC3: The artifacts are byte-reproducible run-to-run.** Two
  `main([...])` runs into different temporary paths in one session produce
  byte-equal JSON and byte-equal Markdown.

- [ ] **AC4: The committed JSON is a fresh build.** The committed
  `docs/aide/traceability_matrix.generated.json` parses to a payload equal to
  `matrix_to_dict(build_matrix())`.

- [ ] **AC5: The committed Markdown agrees with the committed JSON.** For every
  mode in the JSON's mode direction and every rule in its rule direction, the
  committed `.md` carries a table row whose cells contain that record's mode
  number (or `rule_id`), its rules (or declared modes), and its evidence rung
  (or declaration state).

- [ ] **AC6: Both artifacts are written as LF bytes with one trailing
  newline.** Neither committed file contains a `\r` byte, and each ends with
  exactly one `\n`.

- [ ] **AC7: Both new paths are pinned `text eol=lf`.** `.gitattributes`
  contains a line covering `docs/aide/traceability_matrix.generated.json` and a
  line covering `docs/aide/traceability_matrix.generated.md`, each with
  `eol=lf`.

- [ ] **AC8: The mode set is §6's, taken from code.** The JSON's mode direction
  holds exactly one record per key of `segfacet.feature_docs.MODE_ANCHOR_PATHS`
  (`{1, …, 8}`), no more and no fewer.

- [ ] **AC9: Mode titles are transcribed from `vision.md` §6, not invented.**
  For each mode *m*, the matrix's title for *m* equals the text of the *m*-th
  numbered item under `docs/aide/vision.md`'s `## 6. Segmentation Failure
  Modes` heading, after stripping the `"m. "` prefix and any trailing `.` and
  collapsing internal whitespace.

- [ ] **AC10: mode → rule is complete and reported complete.** Every mode
  record lists ≥1 rule; the JSON's `mode_to_rule` direction reports
  `complete: true` with an empty holes list.

- [ ] **AC11: Each mode's rules are derived from the shipped declarations.**
  For every mode *m*, the mode record's rule list equals the sorted `rule_id`s
  of registered rules whose `RuleModeDeclaration.modes` contains *m*.

- [ ] **AC12: Every mode row carries a rung from the closed vocabulary.** Each
  mode record's rung is a member of exactly `("synthetic-demonstrable",
  "needs-real-data", "structurally-unobservable")`, and every mode has exactly
  one. (The mechanism string beside it is held to AC31, which is a content
  check, not a length floor.)

- [ ] **AC13: Mode 8's rung names the single-channel mechanism.** Mode 8's rung
  is `"structurally-unobservable"` and its mechanism contains both
  `"single-channel"` and `"label map"`.

- [ ] **AC14: Mode 8 is recorded as not pipeline-detected, from the manifest.**
  Mode 8's record has `pipeline_detected` false and names
  `mode8_force_overlap` with `detection == "reconstructed_record"`, and that
  value is the one `tests/corpus/manifest.json` actually carries for that case.

- [ ] **AC15: Rung and corpus detection are cross-checked.** For every mode
  record: rung `"synthetic-demonstrable"` implies `pipeline_detected` is true,
  and rung `"structurally-unobservable"` implies it is false.

- [ ] **AC16: Modes 1 and 4 are recorded synthetic-demonstrable.** Both mode 1
  and mode 4 carry rung `"synthetic-demonstrable"` and `pipeline_detected`
  true, and each names its corpus case (`mode1_displace`, `mode4_relabel_swap`)
  with the `detection` value `tests/corpus/manifest.json` actually carries for
  it. The rung is a claim about the **mode**, independent of how many rules
  declare it — mode 1 gaining `reference_delta` (`b1c593c`) does not move it.

- [ ] **AC17: Mode 7's rung records its own cap.** Mode 7's rung is
  `"needs-real-data"` and its mechanism contains `"rank(v) == v - 1"` and
  `"L1 → T12 → L2 → L5"`.

- [ ] **AC18: rule → mode is complete and reported complete.** The JSON's rule
  direction holds exactly one record per `rule_id` yielded by
  `segfacet.heuristics.iter_rules()`; each record carries either ≥1 mode or a
  non-empty mode-less reason (never both, never neither); and the direction
  reports `complete: true` with an empty holes list.

- [ ] **AC19: Every mode → rule edge is attributed corpus or analytic, derived
  from the corpus map.** Each (mode, rule) edge carries an attribution that is
  exactly `"corpus"` or `"analytic"`, and it is `"corpus"` if and only if that
  mode appears in `segfacet.catalogue.scan_synth_rule_mode_map()[rule_id]`.

- [ ] **AC20: The analytic edges are exactly the edges of the rules the corpus
  map never designates.** The set of edges attributed `"analytic"` equals
  `{(m, rule_id) for every registered rule absent from
  scan_synth_rule_mode_map() and every m in its declaration's modes}`; on this
  tree that set is `{(1, "reference_delta"), (2, "bounds"), (2,
  "reference_delta")}` — three edges over two rules — and the remaining eight
  edges are `"corpus"`. The literal is a witness of the 2026-09-02 tree; the
  derived equality is what the test asserts. It additionally states that no
  rule today mixes attributions; a future rule that legitimately declares one
  corpus-designated mode and one analytic mode is a deliberate revisit of this
  criterion, not a silent pass.

- [ ] **AC21: The feature direction reports its counts against the live
  catalogue.** In one fresh `build_catalogue(strict=True)`: the matrix's total
  path count equals `len(cat.entries)`, its read-by-a-rule count equals the
  number of entries with a non-empty `consuming_rules`, its read-by-no-rule
  count equals the complement, and its `unwired` count equals the number of
  entries whose `status == "unwired"`.

- [ ] **AC22: The "inventory, not a gap" qualifier sits with the count.** The
  JSON object that carries the read-by-no-rule count also carries, in the same
  mapping, a `required: false` flag and a qualifier string containing both
  `"inventory"` and `"not a gap"`; the committed `.md` prints that qualifier in
  the same section as that count.

- [ ] **AC23: Per-rule feature sets are derived from the catalogue.** For every
  registered rule, its record's feature-path list equals the sorted catalogue
  paths whose `consuming_rules` include that `rule_id`.

- [ ] **AC24: Per-mode feature sets are the union of the mode's rules' paths
  plus its anchors.** For every mode *m*, its record's feature-path list equals
  the sorted union of the feature paths of the rules listed for *m* together
  with `MODE_ANCHOR_PATHS[m]`.

- [ ] **AC25: A corpus-designated rule id that no rule registers is reported.**
  The matrix carries a list of `rule_id`s appearing in
  `scan_synth_rule_mode_map()` that `iter_rules()` does not register; it is
  empty on this tree, and with the scanned map monkeypatched to designate
  `"boundary"` for mode 6 the list names `"boundary"` and the mode → rule
  direction reports `complete: false`.

- [ ] **AC26: An undeclared registered rule makes rule → mode fail loudly.**
  With a stub rule registered carrying no `mode_declaration` (registry
  snapshot/restore), `build_matrix()`'s rule direction reports
  `complete: false` with a hole naming that `rule_id`.

- [ ] **AC27: A malformed `evidence` renders as one cell, not one per
  character.** With a registered rule's declaration replaced by one whose
  `evidence` is the bare string `"corpus-derived"`, the rendered Markdown row
  for that rule contains `corpus-derived` as a single contiguous cell value and
  no per-character split (no `c, o, r` sequence).

- [ ] **AC28: The artifacts carry nothing environment-dependent.** Neither
  committed artifact contains a float leaf, a `YYYY-MM-DD` date, an
  absolute-path-shaped string, a drive-letter prefix, or this machine's
  hostname.

- [ ] **AC29: The committed-artifact guard stays clean and unextended.**
  `committed_artifact_guard.iter_violations(tests/)` is empty,
  `committed_artifact_guard.GROUNDS` still has exactly its five members, and no
  `ALLOWLIST` entry names either new artifact path.

- [ ] **AC30: The matrix is inert at evaluation time.** Importing
  `segfacet.traceability` and calling `build_matrix()` leaves
  `segfacet.heuristics.run_rules(record, config)` returning an equal list of
  `Finding`s for a fixed fixture record, and mutates no importable module
  state (a second `build_matrix()` returns an equal matrix).

- [ ] **AC31: Every mode's mechanism names an identifier that resolves against
  live state — no length floor anywhere.** For each mode *m*, the mechanism
  string contains at least one token drawn from live state and re-derived by
  the test: an entry of `feature_docs.MODE_ANCHOR_PATHS[m]`, or the `case_id`
  of a `tests/corpus/manifest.json` case whose `failure_mode` is *m*, or a
  `rule_id` the matrix lists for *m*. No test in this item's module asserts a
  character-count threshold on any mechanism, rung label or qualifier string
  (A14).

- [ ] **AC32: Mode 1's rule list contains every rule a feature-level derivation
  requires.** For each registered rule, map the reference-delta tracked
  vocabulary it consumes onto record leaf paths — `spline_offset_mm` →
  `stage3.per_label_offsets[].offset_mm`, every other name in
  `segfacet.reference.delta.INGESTED_FEATURES` →
  `per_label.{label}.geometry.<name>` — and require that any mode whose
  `MODE_ANCHOR_PATHS` entry is among them appears in that rule's row *and* that
  the rule appears in that mode's row. On this tree that requires
  `reference_delta` in mode 1's rule list, so re-narrowing its declaration to
  `(2,)` fails this criterion at the matrix level.

- [ ] **AC33: The mode → feature list declares its rule granularity.** Each
  mode record's feature-path list is accompanied, in the same mapping, by
  `granularity: "rule"` and a qualifier string containing `"a rule that targets
  this mode reads this path"`; the committed `.md` prints that qualifier in the
  same section as the mode table. A path's presence in a mode row is therefore
  never readable as a per-path mode claim (A13).

## Assumptions

- **A1 (module and artifact naming):** the generator is a new top-level module
  `src/segfacet/traceability.py` and its artifacts are
  `docs/aide/traceability_matrix.generated.{json,md}`, following the house
  shape set by `segfacet.catalogue` and `segfacet.golden_evidence`
  (`build_*` / `*_to_dict` / `render_*` / `main`, `json.dumps(..., indent=2,
  sort_keys=True, ensure_ascii=False)` plus one trailing newline, written with
  `write_bytes`). Item 139 extends **this** module and **these** artifacts
  rather than adding a second pair.
- **A2 (the artifacts live under `docs/aide/`, deliberately):**
  `tests/test_105_golden_decision_table.py`'s AC3 walks `tests/` for non-`.py`
  files, asserts the count is 20, and requires each to be documented in the
  human-signed `docs/aide/golden-decision-table.md`. Putting the matrix under
  `tests/` would need a human signature on that document for a generated
  artifact that is not a test fixture; `docs/aide/` is where the other two
  generated artifacts already live.
- **A3 (the rungs are authored in code, their consistency derived):** the rung
  vocabulary and each mode's rung + mechanism sentence are module-level
  constants in `traceability.py` — a judgement, like
  `feature_docs.STATUS_OVERRIDES`, not something derivable. What is *derived*
  is completeness (AC12: every mode has exactly one), membership of the closed
  vocabulary, the corpus cross-check (AC15), and the mechanism's resolvable
  token (AC31) — so a rung *or* a mechanism that drifts from live state fails.
  The generated half of the deliverable is the matrix; a rung cannot be
  generated, only enforced.
- **A4 (`pipeline_detected` comes from `tests/corpus/manifest.json`'s
  `detection` field):** a mode is pipeline-detected when at least one case with
  that `failure_mode` carries `detection == "pipeline"`. Measured 2026-09-02:
  modes 1–7 true, mode 8 false (`reconstructed_record`). This item reads the
  geometric manifest only; `tests/corpus/intensity/manifest.json` carries no
  `failure_mode` field and belongs to item 139's exercise report.
- **A5 (rung and detection are separate fields, and the cross-check is
  one-directional):** mode 7 is pipeline-detected *and* `needs-real-data` — its
  case demonstrates a single-descent break while §6.7's own two-descent example
  is not representable at rung 1. So AC15 constrains only the two outer rungs;
  `needs-real-data` is compatible with either detection state, which is exactly
  the roadmap's "a rule covers this mode" vs "we have demonstrated it
  end-to-end" split.
- **A6 (this item does not depend on any of the three open item-136 review
  findings, and says why):**
  - the `"corpus"` **exact-element** weakness in
    `catalogue.rule_declaration_conflicts()` (`insights.md`, 2026-09-02) is not
    load-bearing here: AC19 derives the corpus/analytic attribution from
    `scan_synth_rule_mode_map()` itself, never by testing membership of the
    declaration's `evidence` tuple. A declaration mis-tagged
    `"corpus:CropAtBorder…"` would still be attributed correctly by this
    matrix.
  - the **bare-string `evidence`** weakness in
    `RuleModeDeclaration.__post_init__` is likewise not scored on — but its
    *rendering* symptom reaches this artifact, so AC27 defends against it
    locally (render a `str` evidence as one cell). Fixing the dataclass is a
    `src/segfacet/heuristics/rule.py` edit, outside this item's authorised
    paths and outside every queue-019 item's; the insight stays open.
  - the **unregistered designated `rule_id`** blind spot is the one this item
    does act on, inside its own surface only: AC25 reports such an id in the
    matrix and fails the mode → rule direction on it. `rule_declaration_conflicts()`
    is left unchanged, so the insight stays open for its own carrier.
- **A7 (no byte-exact fresh-vs-committed comparison; parsed comparison
  instead):** `tests/committed_artifact_guard.py` (item 127) flags a byte-exact
  comparison against a committed artifact unless its path is allowlisted under
  one of five `GROUNDS`, and `tests/test_134_decision_table_evidence_companion.py`'s
  AC16 pins that vocabulary at exactly five members. None of the five describes
  a float-free derived artifact, so this item takes item 134's precedent: AC4
  compares **parsed** payloads, AC5 compares the Markdown against the committed
  JSON structurally, and byte-equality is asserted only between two freshly
  generated files (AC3), which is a determinism check. No `ALLOWLIST` or
  `GROUNDS` edit (AC29).
- **A8 (`.gitattributes` pins, not `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES`):** the
  two new committed text artifacts are pinned `text eol=lf` per CLAUDE.md's
  Gotchas (AC7), and the pin is asserted by this item's own test rather than by
  extending `tests/test_111_golden_guard.py`'s family list — item 134's
  companion set that precedent, and extending a Stage-29 test file is scope this
  item does not need.
- **A9 (measured counts are provenance, not assertions):** the Description's
  138 / 50 / 88 / 30, the per-rule counts, the per-mode union sizes and the
  eleven-edge split are the 2026-09-02 measurement. Every count AC (AC21, AC23,
  AC24) asserts agreement with a freshly built catalogue, never a literal,
  because a future feature-adding item legitimately moves all of them — and
  commit `b1c593c`, landed between this spec's first draft and its correction,
  is the worked example: it moved the mode → rule figures and the per-mode
  union sizes within a day, while every derived AC stayed true as written.
- **A10 (`catalogue.py`, `feature_docs.py` and every rule module are read-only
  here):** the matrix needs nothing new from them —
  `build_catalogue`, `scan_synth_rule_mode_map`, `MODE_ANCHOR_PATHS`,
  `iter_rules`, `iter_rule_declarations` and `declaration_for` are already
  public. Neither committed catalogue artifact is regenerated by this item, so
  no catalogue-comparing test moves.
- **A11 (no human gate):** every input is committed state on this tree and every
  judgement recorded here is an engineering one grounded in code, the corpus
  manifest, or a stage decision already recorded in `roadmap.md` /
  `progress.md`. Nothing needs a person's decision or an out-of-band
  prerequisite, so no row is added to `progress.md`'s `## Human gates` table.
- **A12 (engine 1.37.0):** `aide check`'s `.gitattributes` lint resolves a
  fixture path through the test's AST and warns when nothing in
  `.gitattributes` covers it; AC7's two pins are what keeps it silent for the
  new paths.
- **A13 (the mode → feature direction inherits item 136's rule granularity, and
  reports it rather than working around it):** item 136 attributes §6 modes to
  a catalogue entry at **rule** granularity — every leaf path a declaring rule
  consumes gains that rule's modes — so bookkeeping paths carry them too.
  Witness on this tree after `b1c593c`: `reference_delta.lower_pct`,
  `reference_delta.{label}.label` and `reference_delta.{label}.level_name` each
  carry `failure_modes == (1, 2)`. AC24's union inherits exactly that. The two
  alternatives were rejected: *working around it* (filtering bookkeeping paths
  out of mode rows) would need a per-path mechanism claim no shipped
  `RuleModeDeclaration` carries, so the filter would be this item's own
  invented judgement dressed as derivation; *silently inheriting it* would let
  a reader take a mode row's path list for a per-path mode claim. So the matrix
  inherits and **labels** it (AC33). The granularity finding belongs to item
  136's design, not to this reporting layer; it is captured in
  `docs/aide/insights.md` (2026-09-02) and stays open for its own carrier.
- **A14 (a string that asserts a fact is held to that fact, never to a length
  floor):** `docs/aide/insights.md`'s 2026-09-02 entry records why —
  `reference_delta`'s evidence sentence shipped a false claim about the
  committed reference artifacts because item 137's AC4 only checked
  `len(evidence) >= 40`. This item writes eight authored mechanism strings, the
  same failure surface, so AC31 checks *content against live state* (an anchor
  path, a manifest `case_id`, or a listed `rule_id`, each re-derived by the
  test) and this item's tests assert no character-count threshold anywhere. A
  mechanism that names `mode8_force_overlap` fails the day that case is renamed
  or removed, which is the whole point.

## Implementation Steps

1. **`src/segfacet/traceability.py` — module skeleton.** Docstring naming item
   138, Stage 20, the three directions and their completeness contract, and the
   scope fence (this module *reports*; it decides no disposition and changes no
   rule). `__all__ = ["build_matrix", "matrix_to_dict", "render_markdown",
   "main"]`, `SCHEMA_VERSION = "1.0"`, `_REPO_ROOT = Path(__file__).resolve().parents[2]`,
   `JSON_PATH` / `MD_PATH` under `docs/aide/`, and a `_NOTE` string naming
   `python -m segfacet.traceability` as the regenerator and "do not hand-edit".
2. **Authored constants** (A3): `RUNGS = ("synthetic-demonstrable",
   "needs-real-data", "structurally-unobservable")`; `RUNG_LABELS` mapping each
   to the roadmap's full phrase; `MODE_TITLES: Dict[int, str]` transcribed from
   `vision.md` §6 (AC9); `MODE_RUNGS: Dict[int, ModeRung]` — a small frozen
   dataclass `(rung, mechanism)` — with modes 1–6 `synthetic-demonstrable`
   (1 and 4 citing items 120/132), mode 7 `needs-real-data` citing the
   `rank(v) == v - 1` cap and §6.7's `L1 → T12 → L2 → L5` example, and mode 8
   `structurally-unobservable` citing the single-channel integer label map,
   `overlaps[]`, and that `mode8_force_overlap` stays a reconstructed record.
   **Every one of the eight mechanisms must name a token AC31 can re-derive**
   — that mode's anchor path, its corpus `case_id`, or one of its listed
   `rule_id`s — spelled exactly as live state spells it. Write no sentence
   whose only defence is its length (A14), and assert no factual claim about
   another artifact's contents without measuring it in this same change.
3. **`build_matrix()` — gather.** Deferred imports in the function body (the
   house rule): `build_catalogue(strict=True)`, `scan_synth_rule_mode_map()`,
   `iter_rules()` / `iter_rule_declarations()`, `feature_docs.MODE_ANCHOR_PATHS`,
   and `synth.corpus.load_manifest()`. Build: `paths_by_rule` (from each
   entry's `consuming_rules`), `declared_modes_by_rule`, `mode_less_by_rule`,
   `cases_by_mode` (case_id + detection, from the manifest), and
   `unregistered_designated = sorted(scanned) - set(registered)` (AC25).
4. **`build_matrix()` — the mode direction.** Per mode key of
   `MODE_ANCHOR_PATHS`: title, rung + rung label + mechanism, the sorted
   declaring rules, per-edge `attribution` (`"corpus"` iff the mode is in the
   scanned map for that rule, else `"analytic"` — AC19), corpus cases with
   their `detection`, `pipeline_detected`, `anchor_paths`, and `feature_paths`
   (union over the mode's rules plus the anchors — AC24) carried in a mapping
   that also holds `granularity: "rule"` and the granularity qualifier (AC33,
   A13). A mode with no rule, or an unregistered designated id, becomes a hole
   in `mode_to_rule`.
5. **`build_matrix()` — the rule direction.** Per registered `rule_id` in
   ascending order: declared `modes`, `declaration_state` (one of `"declared"`,
   `"mode_less"`, `"pending"`, `"undeclared"`), `mode_less_reason`,
   `evidence` normalised through a helper that wraps a bare `str` into a
   one-element tuple (AC27), `feature_paths` and their count. A rule that is
   neither `declared` nor `mode_less` becomes a hole in `rule_to_mode`
   (AC26).
6. **`build_matrix()` — the feature direction.** `total_paths`,
   `read_by_rule`, `read_by_no_rule`, `unwired`, `by_rule` counts, plus
   `required: False` and the qualifier sentence — *"a leaf path no rule reads
   is inventory, not a gap: the feature record is a deliberately over-broad
   vector rules select from, and full consumption is never an expected end
   state"* — in the **same mapping** as the count (AC22).
7. **`matrix_to_dict` / `render_markdown`.** JSON: `schema_version`, `note`,
   `modes`, `rules`, `features`, `directions`, `corpus_designated_unregistered_rule_ids`.
   Markdown: a preamble naming the regeneration command, then one section per
   direction — mode table (`Mode | §6 title | Rules (attribution) | Evidence
   rung | Pipeline-detected | Feature paths`) followed immediately by the
   rule-granularity qualifier (AC33), rule table (`Rule | Declared modes |
   State | Evidence | Feature paths`), and the feature section printing the
   counts **followed immediately by the qualifier sentence**. No date, no
   absolute path, no float anywhere (AC28).
8. **`main(argv)`** with `--json` / `--md` defaulting to the committed paths;
   `write_bytes(text.encode("utf-8"))` for both (never `write_text` — Python
   3.9 cannot set `newline=`).
9. **Generate and commit both artifacts** — `.venv/bin/python -m segfacet.traceability`
   — and confirm the counts against the Description's 2026-09-02 measurement,
   investigating (not silencing) any divergence.
10. **Pin both new paths in `.gitattributes`** as `text eol=lf`, in a short
    commented block naming item 138 and pointing at CLAUDE.md's Gotchas.

## Authorised paths

**May change:**

- `src/segfacet/traceability.py` — the generator; new file (AC1–AC5, AC10–AC27, AC31–AC33).
- `docs/aide/traceability_matrix.generated.json` — the generated matrix; new committed artifact (AC4, AC6, AC28, AC33).
- `docs/aide/traceability_matrix.generated.md` — its rendered form; new committed artifact (AC5, AC6, AC22, AC28, AC33).
- `.gitattributes` — two `text eol=lf` pins for the paths above (AC7).
- `tests/test_138_traceability_matrix.py` — this item's test module.

**Asserts against:**

- `docs/aide/vision.md` — AC9 pins §6's eight numbered mode titles as the source of the transcribed titles; §6 is read, never edited.
- `src/segfacet/feature_docs.py` — `MODE_ANCHOR_PATHS`, the in-code §6 mode set and per-mode anchor paths AC8 and AC24 read; unchanged.
- `src/segfacet/catalogue.py` — `build_catalogue`, `scan_synth_rule_mode_map` and the `CatalogueEntry` fields (`consuming_rules`, `status`) AC19, AC21, AC23 and AC25 read; unchanged, and neither catalogue artifact is regenerated.
- `src/segfacet/heuristics/*.py` — the ten `RuleModeDeclaration`s items 136/137 landed, as corrected by commit `b1c593c` (`reference_delta` at `modes=(1, 2)`), which AC11, AC18, AC20 and AC32 read; no rule module is edited.
- `src/segfacet/reference/delta.py` — `INGESTED_FEATURES`, the tracked-feature vocabulary AC32's derivation maps onto record leaf paths; read-only, and the mirror of the same derivation `tests/test_137_mode_less_rule_disposition.py::test_adv_reference_delta_declared_modes_cover_every_tracked_mode_anchor_feature` runs at the declaration level.
- `src/segfacet/synth/*.py` — the `Expectation(failure_mode=…, expected_rule_ids=…)` literals the scanned corpus map is derived from; no corpus case is added or changed.
- `tests/corpus/manifest.json` — AC14 and A4 read its `failure_mode` / `detection` fields; `mode8_force_overlap` stays `reconstructed_record`, read-only.
- `tests/committed_artifact_guard.py` — AC29 pins `GROUNDS` at its five members and the absence of an `ALLOWLIST` entry for either new artifact; read-only.

## Testing Strategy

New module: **`tests/test_138_traceability_matrix.py`**, one focused test per
AC (AC12/AC15 parametrised over the eight modes, AC18/AC23 over the ten rules),
plus:

- **Adversarial — mode → rule hole.** Inside a registry snapshot/restore
  fixture (the house pattern from `tests/test_026_rule_engine_core.py`),
  monkeypatch the live declaration of `overlap` to a mode-less one and confirm
  mode 8 becomes a hole naming the mode, with `complete: false`.
- **Adversarial — rule → mode hole (AC26).** Register a stub rule with no
  `mode_declaration`; the rule direction fails loudly and names its `rule_id`.
  This is the failure mode items 139/142 rely on staying loud.
- **Adversarial — unregistered designated id (AC25).** Monkeypatch
  `traceability`'s call site of `scan_synth_rule_mode_map` to return a map with
  `"boundary": (6,)` and confirm the id is reported and the direction fails —
  the blind spot the item-136 review found in `rule_declaration_conflicts()`,
  closed inside this artifact only (A6).
- **Adversarial — a stale rung (AC15).** Monkeypatch `MODE_RUNGS[8]` to
  `synthetic-demonstrable` and confirm the cross-check fails; monkeypatch a
  rung to a string outside `RUNGS` and confirm AC12's vocabulary check fails.
- **Adversarial — bare-string evidence (AC27).** A declaration whose `evidence`
  is `"corpus-derived"` renders as one cell.
- **Adversarial — a mis-tagged `"corpus"` evidence changes no attribution
  (A6).** Replacing `bounds`' evidence with `("corpus",)` leaves the `(2,
  bounds)` edge attributed `"analytic"`, because the attribution reads the
  corpus map, not the tag.
- **Adversarial — a re-narrowed `reference_delta` declaration (AC32).**
  Monkeypatch `ReferenceDeltaRule.mode_declaration` back to `modes=(2,)` — the
  false-premised shape commit `b1c593c` corrected — and confirm the matrix
  reports mode 1 as missing a rule its tracked features require, from the
  `INGESTED_FEATURES` × `MODE_ANCHOR_PATHS` derivation rather than from any
  literal.
- **Adversarial — a stale mechanism (AC31).** Monkeypatch mode 8's mechanism to
  a long sentence naming no live identifier (and separately, one naming
  `"mode8_force_overlaps"`, one character off the real `case_id`) and confirm
  the content check fails in both cases — the length-floor failure A14 records
  would pass both.
- **Determinism / immutability.** `build_matrix()` twice in one session returns
  equal matrices; the artifacts regenerate byte-identically (AC3); the matrix
  and its records refuse in-place mutation (frozen dataclasses or tuples);
  `run_rules` on a fixed fixture record is unchanged after a build (AC30).
- **Edge cases.** A mode whose declaring-rule set is a singleton still renders a
  well-formed row; a rule consuming zero catalogued paths renders an empty
  feature list rather than raising; the qualifier check (AC22) asserts the
  qualifier's *presence beside the count*, not merely somewhere in the file.
- **Portability.** No absolute path literals; committed artifacts addressed from
  `Path(__file__).resolve().parent.parent`; every regeneration writes into
  `tmp_path`, never over a committed copy; no test compares a committed file's
  bytes or text against a freshly computed value (A7) — the guard in
  `tests/committed_artifact_guard.py` is asserted clean by AC29, and this module
  must not be what breaks it.

**Existing tests to reconcile — none requires editing**, but three constrain
what this item's tests may do, and were checked against this tree on
2026-09-02:

- `tests/test_134_decision_table_evidence_companion.py::test_ac16_committed_artifact_guard_clean_and_vocabulary_unextended`
  — runs the guard over all of `tests/` and pins `GROUNDS` at five members. A
  byte-exact committed comparison in the new module would turn this red; A7's
  parsed-comparison scheme is what keeps it green.
- `tests/test_105_golden_decision_table.py::test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions`
  (and its `== 20` count) — walks `tests/` for non-`.py` files. This item adds
  none: both artifacts live under `docs/aide/` (A2). Verify, do not edit.
- `tests/test_111_golden_guard.py`'s `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` pin
  test — unchanged by design (A8); AC7 asserts the two new pins locally
  instead.
- `tests/test_137_mode_less_rule_disposition.py` — reconciled by commit
  `01280fa` to `reference_delta`'s corrected `modes=(1, 2)`; its
  `test_ac2_ac3_analytic_rule_declares_its_expected_modes` and
  `test_adv_reference_delta_declared_modes_cover_every_tracked_mode_anchor_feature`
  pin the declaration this item only reads. AC32 mirrors that derivation one
  layer up, at the matrix. Verify, do not edit.
- `tests/test_102_stage18_validation.py::test_ac24_src_tree_is_byte_identical_across_the_test_run`
  hashes `src/segfacet/**` at collection time only, so a **new** module changes
  nothing it compares; likewise `tests/test_104_feature_catalogue_drift.py` and
  every catalogue-comparing test stay green because no catalogue artifact is
  regenerated here (A10). Verify, do not edit.

## Validation

Beyond the suite, observe the artifact directly (no `[validation]` profile
needed — CPU-only, no optional dependency):

1. `.venv/bin/python -m segfacet.traceability` — regenerates both artifacts in
   place; a clean `git diff` afterwards is the byte-reproducibility claim
   observed rather than asserted.
2. `git diff --stat docs/aide/traceability_matrix.generated.json docs/aide/traceability_matrix.generated.md`
   — expect no change on a re-run of step 1.
3. Read `docs/aide/traceability_matrix.generated.md` end to end and confirm by
   eye: eight mode rows each with a rung; mode 8's row reading
   `structurally-unobservable` with the single-channel mechanism; mode 1's row
   listing both `mislabel` and `reference_delta`; ten rule rows with the three
   `analytic` edges — `(1, reference_delta)`, `(2, bounds)`,
   `(2, reference_delta)` — visibly distinguished from the eight `corpus` ones
   (the distinction item 137's A7 deferred here); the mode table immediately
   followed by its rule-granularity qualifier; and the feature section's count
   immediately followed by its "inventory, not a gap" qualifier.
4. `.venv/bin/python -c "import json;d=json.load(open('docs/aide/traceability_matrix.generated.json'));print(d['directions'])"`
   — expect both required directions `complete: true` with empty holes, and the
   feature direction `required: false` with its qualifier.
5. `python .aide/scripts/aide.py check` — expect no `.gitattributes` warning
   naming either new artifact.

## Dependencies

- **Item 136** — the `RuleModeDeclaration` seam (`modes` / `evidence` /
  `mode_less_reason` / `pending_reason`), `declaration_for`,
  `iter_rule_declarations` and the corpus-derived map exposed as
  `scan_synth_rule_mode_map`. The rule → mode direction is nothing but a read
  of that seam.
- **Item 137** — the disposition of the last four rules, without which the rule
  → mode direction could not report `complete: true`: `bounds` declaring §6
  mode 2 and `reference_delta` declaring §6 modes 1 and 2, both on **analytic**
  evidence (`reference_delta` corrected from `(2,)` to `(1, 2)` by commit
  `b1c593c`, 2026-09-02, after a post-merge review measured the committed
  reference artifacts); `intensity` and `intensity_reference_delta` mode-less
  with reasons. Item 137's Assumption A7 names this item as the carrier for the
  analytic-vs-corpus distinction, and AC19/AC20 are that carrier.
- **Item 103** — the generated feature catalogue whose `consuming_rules` and
  `status` fields supply the whole feature direction.

**Downstream:** item 139 extends this module and these artifacts with the
per-rule and per-operator corpus-exercise columns (and is where
`tests/corpus/intensity/manifest.json` enters); item 140's specificity ratchet
and item 142's stage validation both read this artifact — item 142 regenerates
it from a clean tree and quotes its counts as the honest end-to-end statement.

## Decisions & Trade-offs

To be updated during implementation.

### Correction (2026-09-02, before implementation)

This spec was authored against a tree where `reference_delta` declared
`modes=(2,)`. Commit `b1c593c` corrected that declaration to `modes=(1, 2)`
after a post-merge review of item 137 measured the premise its evidence
sentence rested on and found it false: both committed reference artifacts carry
21 per-label features, `compute_reference_delta` scores every tracked one, and
`spline_offset_mm` among them is read from
`stage3.per_label_offsets[].offset_mm` — `feature_docs.MODE_ANCHOR_PATHS[1]`
itself. The original reasoning above is left standing; what it got wrong is
recorded here.

- **What moved.** mode 1's declaring rules `{mislabel}` → `{mislabel,
  reference_delta}`; the analytic edge set `{(2, bounds), (2, reference_delta)}`
  → `{(1, reference_delta), (2, bounds), (2, reference_delta)}`, two edges → three,
  total edges ten → eleven; mode 1's AC24 feature union 10 → 19 paths. `bounds`
  still declares mode 2 alone — its sentence was checked against the same
  premise and found accurate, because it describes what the rule reads from the
  case record, not what the reference artifact carries.
- **What did not move, and why.** The feature-direction counts (138 / 50 / 88 /
  30 and every per-rule count): `b1c593c` changed catalogue entries'
  `failure_modes`, never their `consuming_rules`. The evidence rungs, including
  AC16's for modes 1 and 4: a rung records whether a mode's failure has been
  demonstrated end-to-end on the corpus, which is a property of the mode, not
  of how many rules declare it — `mode1_displace` is still `detection ==
  "pipeline"`. Every derived AC (AC10, AC11, AC19, AC21, AC23, AC24) stayed
  true as written, which is A9's claim observed rather than argued.
- **AC20 was the one criterion that had to change**, because it pinned a
  literal edge set. It is now stated as a derivation — the analytic edges are
  the edges of rules the corpus map never designates — with the three-edge
  literal kept only as a dated witness.
- **AC31 / A14 — the correction's own lesson, applied here.** The defect
  survived because item 137's AC4 checked `len(evidence) >= 40` rather than the
  sentence's content (`docs/aide/insights.md`, 2026-09-02). This item authors
  eight mechanism strings on the same footing, so AC12's original "≥ 60
  characters" floor is gone: AC31 requires each mechanism to name a token the
  test re-derives from live state, and forbids any character-count threshold in
  this item's tests.
- **AC32 — a second, feature-level guard.** Attribution alone would not have
  caught the original defect, since a rule's declared modes are taken as given.
  AC32 derives mode 1's required rules from
  `reference.delta.INGESTED_FEATURES` × `MODE_ANCHOR_PATHS`, mirroring at the
  matrix the check `tests/test_137_mode_less_rule_disposition.py::test_adv_reference_delta_declared_modes_cover_every_tracked_mode_anchor_feature`
  now runs at the declaration, so a re-narrowing fails in two places.
- **AC33 / A13 — the inherited granularity, reported not hidden.** The same
  review observed that item 136's rule-granular mode attribution paints
  bookkeeping paths (`reference_delta.lower_pct`, `.{label}.label`,
  `.level_name`, all now carrying `(1, 2)`) with their rule's modes. This
  item's mode → feature direction inherits that by construction. Filtering it
  was rejected as an invented judgement no declaration supports; silent
  inheritance was rejected as misreadable. The matrix labels the list
  `granularity: "rule"` and prints the qualifier, and the underlying finding
  stays with item 136 via `insights.md`.
