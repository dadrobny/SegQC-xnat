# Item 144 — The failure-mode specification module and its generated rendering

> **Created:** 2026-09-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 144
> **Objectives:** G2 (detect catalogued failure modes — the specification half), G8 (extensible / the add-a-mode path)
> **Suggested branch:** `aide/144-the-failure-mode-specification-module`

---

## Description

Create the authored source [`vision.md`](../vision.md) v3 §6 describes: **one
frozen declaration per failure mode**, in a new module under
`src/segfacet/`, shaped after `RuleModeDeclaration`
(`src/segfacet/heuristics/rule.py`), from which
`docs/aide/failure_modes.generated.{md,json}` are rendered by **zero-argument
regeneration**. Today the modes exist as five partial sources that agree
without any of them being a specification (queue-020, "The five partial sources
this stage collapses"); this item builds the object the other eight items in the
stage read, write into, and render.

**This item builds the schema, the validation, the derivation and the rendering
— not the entries.** The eight hypothesised modes are item 145's; the ninth mode
and the first `proposed` entry are item 146's; collapsing `FAILURE_MODE_NAMES`,
`MODE_RUNGS`, `MODE_ANCHOR_PATHS` and `traceability.py`'s `vision.md` parse onto
the specification is item 147's; re-pointing `build_matrix` at it is item 149's.
It ships a **minimal seed set of two entries** (modes 3 and 8) chosen to exercise
both derivation paths end-to-end — see **A4** — and nothing else.

The schema carries vision §6's fields: `id`, `name`, `definition`,
`discriminator`, `observability`, `candidate_features` (each labelled with its
**role**, so the Stage-18 per-mode *metric*'s anchor path is labelled as exactly
that and never as what a rule reads), `intended_rules` (each naming the detector
where a rule has several, and carrying the **per-edge evidence rung** gate 3
decision 3 fixed), `corpus_cases` (each with an **expected** firing set),
`severity`, `status` and `provenance`.

The lifecycle `status` is **authored only for `proposed` and `specified`**.
`implemented` (≥1 registered rule declares the mode) and `validated` (a corpus
case's measured firing set equals its authored expected set) are **derived from
live state** on every read and on every regeneration — the authored field cannot
hold either, and a value forced past construction is reported by the module's own
conformance check, naming the mode.

**Scope fence.** No new rule, threshold, extractor, verdict, report schema or CLI
behaviour. Nothing under `src/segfacet/heuristics/` changes: the derivation
*reads* the registry and each rule's `RuleModeDeclaration`, and moving any
declaration is item 146's/147's. No corpus case is added or changed; the corpus
is **read** to measure firing sets. `vision.md` and `roadmap.md` are not edited
(queue-020's scope fence): a finding that §6's principles are wrong is one line
in `insights.md` and a hand-back. The three declaration-seam defects
(`insights.md`, item 136, 2026-09-02) are **not** fixed here — item 147 closes
them by replacement; this module simply does not reproduce them (AC7).

## Acceptance Criteria

- [ ] **AC1: the module exists with a zero-argument public API.** A new module
  `src/segfacet/failure_modes.py` exports `ModeSpec`, `CandidateFeature`,
  `IntendedRule`, `CorpusCaseExpectation`, `SPECIFICATION`, `iter_modes`,
  `derive_status`, `derive_mode_rung`, `specification_conflicts`,
  `specification_to_dict`, `render_markdown` and `main`; `iter_modes()`,
  `specification_to_dict()` and `main([])` each take no required argument.
  `src/segfacet/failure_modes.py` itself contains no module-scope (top-level)
  `numpy` / `scipy` / `nibabel` import — house style, as `traceability.py` —
  checked on the module's own source, not on what a bare `import segfacet.X`
  additionally pulls in through the package `__init__` (see the Decisions
  log entry dated 2026-09-03).

- [ ] **AC2: one frozen declaration per mode, carrying exactly §6's fields.**
  `ModeSpec` is a frozen dataclass whose field-name tuple is exactly
  `("id", "name", "definition", "discriminator", "observability",
  "candidate_features", "intended_rules", "corpus_cases", "severity", "status",
  "provenance")`; assigning to any field of an instance raises
  `dataclasses.FrozenInstanceError`.

- [ ] **AC3: a missing or empty required field is rejected, naming mode and
  field.** Constructing a `ModeSpec` with an empty `name`, `definition`,
  `discriminator`, `observability`, `severity`, `status` or `provenance` (one
  case per field), or with `id` absent / `< 1` / non-`int`, raises `ValueError`
  whose message contains both the offending mode's `id` (or `name` where `id` is
  the offending field) and the field name.

- [ ] **AC4: the status vocabulary is closed at four members.**
  `STATUSES == ("proposed", "specified", "implemented", "validated")`, and a
  `status` outside it raises `ValueError` naming the mode and `status`.

- [ ] **AC5: the observability vocabulary is closed at three members.**
  `OBSERVABILITY == ("single-channel-observable", "needs-paired-scan",
  "structurally-unobservable")`, and a value outside it raises `ValueError`
  naming the mode and `observability`.

- [ ] **AC6: the provenance vocabulary is closed at two members.**
  `PROVENANCE == ("hypothesised", "discovered")`, and a value outside it raises
  `ValueError` naming the mode and `provenance`.

- [ ] **AC7: every tuple-typed field rejects a bare string and a list.** For each
  of `ModeSpec.candidate_features`, `ModeSpec.intended_rules`,
  `ModeSpec.corpus_cases` and `CorpusCaseExpectation.expected_firing`, passing a
  bare `str` and passing a `list` each raise `ValueError` naming the mode and the
  field — so a forgotten pair of parentheses can never iterate character-wise
  (the `RuleModeDeclaration` weakness recorded in `insights.md`, item 136,
  2026-09-02).

- [ ] **AC8: `status` is authored only for `proposed` and `specified`.**
  Constructing a `ModeSpec` with `status="implemented"` or `status="validated"`
  raises `ValueError` naming the mode, the field, and the derivation that owns
  the value — even though both are members of `STATUSES` (AC4).

- [ ] **AC9: `implemented` is derived from the live registry.** For a mode whose
  authored `status` is `specified` and which no corpus case validates,
  `derive_status(mode)` returns `"implemented"` iff at least one **registered**
  rule's `RuleModeDeclaration` lists that mode id, and `"specified"` otherwise —
  proven by registering and removing a fake declaring rule in the registry within
  one test, not by transcribing today's registry.

- [ ] **AC10: `validated` is derived from a live corpus measurement.** For a mode
  carrying at least one `CorpusCaseExpectation`, `derive_status(mode)` returns
  `"validated"` iff every one of its corpus cases' **measured** firing set (the
  set of `rule_id`s among the findings the case's `detection` path produces,
  obtained through `segfacet.synth.regression`) equals its authored
  `expected_firing`; mutating one authored `expected_firing` to a set the corpus
  does not produce makes the same call return `"implemented"`, not `"validated"`.

- [ ] **AC11: a hand-set derived status is reported by the conformance check,
  naming the mode.** `specification_conflicts()` returns an empty tuple for the
  shipped specification, and returns exactly one conflict naming the mode and
  `status` for a `ModeSpec` whose `status` was forced to `"implemented"` past
  `__post_init__` (via `object.__setattr__`) — the defence in depth behind AC8.

- [ ] **AC12: a candidate feature carries a role, and the Stage-18 anchor role is
  validated against `MODE_ANCHOR_PATHS`.** `CandidateFeature` carries `path` and
  `role`, `CANDIDATE_ROLES == ("stage18-metric-anchor", "hypothesised")`, a role
  outside it raises naming the mode and the path, and a `path` labelled
  `stage18-metric-anchor` that is not an element of
  `segfacet.feature_docs.MODE_ANCHOR_PATHS[mode.id]` raises naming the mode, the
  path and the anchor set it was checked against.

- [ ] **AC13: every mode ↔ rule edge carries a rung from the closed vocabulary.**
  `IntendedRule` carries `rule_id`, `detector` (may be empty) and
  `evidence_rung`; `EVIDENCE_RUNGS == ("synthetic-demonstrable",
  "needs-real-data", "structurally-unobservable")`; a rung outside it, or an
  empty `rule_id`, raises `ValueError` naming the mode and the `rule_id`.

- [ ] **AC14: a mode's rung is derived as the strongest of its edges.**
  `derive_mode_rung(mode)` returns the strongest edge rung under the ordering
  `synthetic-demonstrable` > `needs-real-data` > `structurally-unobservable`, and
  `None` for a mode with no edges; weakening the strongest edge of a
  multi-edge mode changes the returned value.

- [ ] **AC15: the severity vocabulary is derived from `Severity`, not
  hand-typed.** An accepted `severity` is a member of
  `{s.label for s in segfacet.verdict.Severity} - {"pass"}` computed from the
  enum; `"pass"` and any non-member each raise `ValueError` naming the mode and
  `severity`.

- [ ] **AC16: the shipped seed is exactly two entries, both grounded in
  `vision.md` §6.** `SPECIFICATION` carries exactly the modes `3` and `8`; each
  carries every field non-empty (`intended_rules` and `corpus_cases` included);
  each `id` is a key of `MODE_ANCHOR_PATHS`; and each `name` equals that mode's
  title in `docs/aide/vision.md` §6's numbered list, **parsed from the document**
  in the test rather than hand-transcribed.

- [ ] **AC17: zero-argument regeneration writes the two committed paths, and a
  redirected run leaves them untouched.** `main([])` writes exactly
  `docs/aide/failure_modes.generated.json` and
  `docs/aide/failure_modes.generated.md`; `main(["--json", <tmp>, "--md",
  <tmp>])` writes to the given paths and both committed artifacts are
  byte-identical before and after.

- [ ] **AC18: both artifacts are byte-identical run-to-run.** Two `main()` runs
  into two separate temporary directories produce byte-identical JSON and
  byte-identical Markdown.

- [ ] **AC19: the committed JSON is a fresh build, and carries the authored and
  derived status separately.** `json.loads` of the committed JSON equals the
  round-tripped fresh `specification_to_dict()`; every mode object in it carries
  both a `status_authored` key (a member of `("proposed", "specified")`) and a
  `status_derived` key (a member of `STATUSES`), and per corpus case an
  `expected_firing` list plus an `agrees` boolean.

- [ ] **AC20: the committed Markdown agrees with the committed JSON, entry by
  entry.** For every mode in the committed JSON, the Markdown carries its `id`,
  `name`, `status_derived`, derived rung, `observability`, `severity`,
  `provenance`, every `intended_rules` `rule_id` with its edge rung, and every
  corpus case with its `expected_firing`; every candidate feature is rendered
  under its role label, with the `stage18-metric-anchor` role rendered as the
  Stage-18 *metric* path and never as a rule read path.

- [ ] **AC21: both artifacts are LF bytes with exactly one trailing newline,
  written with `write_bytes`.** Neither committed artifact contains `\r`; each
  ends with `\n` and not `\n\n`; and `main()` writes through `Path.write_bytes`
  (a `main()` run with `Path.write_text` monkeypatched to raise still succeeds).

- [ ] **AC22: `.gitattributes` pins both new paths `text eol=lf`.**
  `.gitattributes` contains a line beginning with each of
  `docs/aide/failure_modes.generated.json` and
  `docs/aide/failure_modes.generated.md` and containing `eol=lf`.

- [ ] **AC23: the rendering introduces no stray status icon under `docs/aide/`.**
  `aide.stray_icon_warnings(docs/aide)` returns an empty list — the lifecycle
  status is rendered as its word, never as one of the six AIDE status icons,
  which are read at structural positions in any `docs/aide/` markdown
  (`.aide/conventions.md` §1 → status-icons; the existing global assertion is
  `tests/test_125_stage28_validation.py::test_ac19_no_stray_status_icon_warnings_in_docs_aide`).

- [ ] **AC24: the specification is immutable and deterministically ordered.**
  `SPECIFICATION` cannot be mutated in place (a `MappingProxyType` or a tuple);
  `iter_modes()` yields modes in ascending `id` order; two `specification_to_dict()`
  calls compare equal and neither mutates the registry, the catalogue, the
  manifest or any importable module's state.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **A1 — module name.** The roadmap leaves the naming to the spec-author
  (Stage 30 D1). The module is `src/segfacet/failure_modes.py` — a top-level
  peer of `traceability.py` and `feature_docs.py`, not a package, because the
  specification is one authored object and every consumer (145–151) imports it
  by name. `src/segfacet/**/*.py text eol=lf` already covers it in
  `.gitattributes`; only the two generated docs need new pins (AC22).

- **A2 — what an expected firing set *is*.** `expected_firing` is the **full**
  set of `rule_id`s among the findings the corpus case's detection path
  produces, not the manifest's `expected_rule_ids` (which is the *designated*
  subset `segfacet.synth.regression.designated_findings` filters to). Gate 3
  decision 2 requires `mode6_crop_at_border` to carry `{border, mislabel}` while
  the manifest lists only `border`, so the two are different objects and the
  specification owns the wider one. Items 145/146/149 depend on this reading.

- **A3 — how a firing set is measured.** Through
  `segfacet.synth.regression`, dispatching on the case's `detection` field:
  `pipeline_findings` for `"pipeline"`, `reconstructed_findings` for
  `"reconstructed_record"` — the same dispatch `designated_findings` uses,
  reused rather than re-composed (`insights.md`, item 139, 2026-09-03 records
  item 139 privately re-composing this inside `traceability.py`). Only the
  **geometric** corpus (`tests/corpus/manifest.json`) is readable this way
  today: `tests/corpus/intensity/manifest.json` carries no `failure_mode` field
  and has no public harness until **item 146** builds one, so no seed entry here
  names an intensity case.

- **A4 — the seed is two entries, and why.** Two entries prove the machinery
  because two derivation paths exist and one entry cannot exercise both:
  **mode 3** (*disconnected components / islands*) is `single-channel-observable`
  with the `pipeline`-detected case `mode3_inject_islands`, and **mode 8**
  (*overlapping segments*) is `structurally-unobservable` with the
  `reconstructed_record`-detected case `mode8_force_overlap` — so the seed covers
  the plain `run_qc` path, the reconstruction path, two of the three
  observability classes and two edge rungs. Every other lifecycle state
  (`proposed`; `specified` surviving derivation), every rejection path and the
  multi-edge rung derivation are exercised on **test-constructed** `ModeSpec`s,
  never shipped: a third shipped entry would be a factual claim about a mode
  item 145 has not yet measured, which is precisely the defect class Stage 30
  exists to end. Modes 1, 2, 4, 5, 6, 7 are deliberately absent (item 145); the
  ninth mode and the first `proposed` entry are deliberately absent (item 146).

- **A5 — "a hand-set `implemented`/`validated` that disagrees fails a test".**
  Read as vision §6 states it — the authored field holds only the first two
  states — so the requirement is realised **twice**: construction rejects a
  derived-only value outright (AC8), and `specification_conflicts()` reports one
  forced past `__post_init__` (AC11). A mode authored `specified` whose live
  state derives `implemented` is **not** a conflict: the derivation wins, which
  is what "derived" means.

- **A6 — the per-edge rung lives in this item's schema.** Gate 3 decision 3
  attaches the evidence rung to the mode ↔ rule **edge**, and item 145's
  acceptance requires the mode's rung to be *derived by construction* rather
  than transcribed. The mechanism (the closed vocabulary, the edge field, the
  strongest-edge derivation) therefore ships here so that item 145 is pure
  authoring; item 145 authors the values and proves the derivation live by
  weakening an edge. Strength ordering: `synthetic-demonstrable` >
  `needs-real-data` > `structurally-unobservable` (vision §6, "a mode's rung is
  derived as the strongest of its edges").

- **A7 — byte-exact fresh-vs-committed comparison is deferred to item 149.**
  `tests/committed_artifact_guard.py`'s `GROUNDS` has five members
  (`exact-parameter-floats`, `emission-clamped`, `hand-written-literals`,
  `binary-fixture`, `integrity-pin`), none of which honestly describes a
  **float-free derived** artifact; item 149 adds the sixth, `no-float-leaf`.
  This item therefore makes its byte-exact claim **run-to-run only** (two
  temporary renders, AC18) and establishes the committed copies' freshness
  structurally — the committed JSON parses to a fresh build (AC19) and the
  committed Markdown agrees with the committed JSON (AC20) — which is exactly
  the pattern `tests/test_138_traceability_matrix.py` AC3/AC4/AC5 already runs
  for the traceability artifacts. **No `ALLOWLIST` entry and no new ground is
  added here**, and item 134's vocabulary-length pin stays at five; item 149
  moves both artifacts under the guard.

- **A8 (engine 1.37.0) — the `aide check` baseline.** On this branch
  `python .aide/scripts/aide.py check` reports **7 warnings** (32 legacy specs
  with no `## Assumptions` block; human gates 1 and 2 awaiting a decision; four
  Stage-20 retraction notices) and says nothing about `.gitattributes`. "No new
  warning" in the Validation section is measured against that baseline; the
  `.gitattributes` lint (engine 1.19.0) resolves a fixture path through the
  test's AST, so AC22's pins are what keep it silent for the two new paths.

- **A9 — severity vocabulary.** Derived from `segfacet.verdict.Severity`'s
  labels, with `"pass"` excluded: a mode whose detection should mean "pass" is
  not a failure mode. Deriving rather than hand-listing keeps the field honest
  if the enum ever changes (AC15).

- **A10 — the `vision.md` §6 parse stays in the test.** AC16 parses §6's
  numbered list inside `tests/test_144_failure_mode_specification.py`; the
  production module carries no parse of `vision.md`.
  `traceability._vision_mode_titles` is private to that module and is neither
  imported nor moved here — **item 147** decides where the one surviving
  vision → specification conformance check lives.

- **A11 — item 143 has merged.** Every corpus measurement this item makes is on
  the S-axis-corrected corpus (`docs/corpus-s-axis-correction.md`,
  `tests/corpus/manifest.json`, 2026-09-03). The seed's `expected_firing` values
  are **measured by the builder** on that corpus and recorded in the Decisions
  log; this spec deliberately transcribes none, so no pre-correction value can
  enter through it.

- **A12 — the sign-off placeholder.** Item 150 records the maintainer sign-off
  in this module's docstring. This item ships a `Sign-off` heading in the
  docstring stating that none is recorded yet — plain prose, **not** a
  double-brace template slot (`aide check` flags a surviving one as unfilled)
  and **not** a placeholder date (item 150's test requires a real, non-future
  date).

- **A13 — no stage acceptance criterion is closed here.** No AC carries a
  *(closes Stage 30 criterion M)* annotation: every Stage 30 criterion speaks of
  "every mode", the finished rendering or the sign-off, none of which a
  two-entry seed establishes. Item 151 attests them (`.aide/conventions.md`
  §1 → items).

## Implementation Steps

1. **Create `src/segfacet/failure_modes.py`** with the module docstring: what
   the specification is, that it is the primary record vision §6 describes, the
   scope fence above, the determinism contract (deferred heavy imports; no
   mutation of any input), the public API list, and the empty `Sign-off`
   heading (A12).
2. **Define the closed vocabularies** as module-level tuples: `STATUSES`,
   `AUTHORED_STATUSES`, `OBSERVABILITY`, `PROVENANCE`, `CANDIDATE_ROLES`,
   `EVIDENCE_RUNGS` (strongest-first), plus `severities()` derived from
   `segfacet.verdict.Severity` (A9).
3. **Define the four frozen dataclasses** — `CandidateFeature(path, role)`,
   `IntendedRule(rule_id, detector, evidence_rung)`,
   `CorpusCaseExpectation(case_id, corpus, expected_firing, reason)`, and
   `ModeSpec` with AC2's exact field tuple — each validating in
   `__post_init__` and raising `ValueError` messages that always name the
   offending mode and field (AC3–AC8, AC12, AC13, AC15). Validate tuple-ness
   **before** iterating any tuple field, so a bare `str` is rejected rather
   than iterated character-wise (AC7).
4. **Write the seed set** (A4): mode 3 and mode 8, `provenance="hypothesised"`,
   `status="specified"`, `name` copied from `vision.md` §6's numbered list
   verbatim (minus the trailing period), `candidate_features` including the
   `stage18-metric-anchor` entry taken from `MODE_ANCHOR_PATHS`, `intended_rules`
   naming `fragmentation` and `overlap` with their edge rungs, and
   `corpus_cases` naming `mode3_inject_islands` and `mode8_force_overlap`.
   **Measure** each `expected_firing` by running the case through the harness of
   step 5 and record the measured values in the Decisions log; transcribe
   nothing (A11).
5. **Add the derivation**: `measured_firing(case)` (deferred imports;
   dispatches on the manifest case's `detection` via
   `segfacet.synth.regression`, A3), `case_agrees(case)`,
   `derive_status(mode)` (AC9/AC10, registry first, corpus second),
   `derive_mode_rung(mode)` (AC14) and `specification_conflicts()` (AC11).
6. **Add the rendering**: `specification_to_dict()` → a JSON-ready dict with
   `schema_version`, a `note` naming the module as the thing to edit and the
   command to regenerate, and `modes` ascending by id, each carrying
   `status_authored` and `status_derived` separately (AC19); `render_markdown()`
   → one section per mode with the fields of AC20, no status icons (AC23), and
   candidate features grouped under their role labels.
7. **Add `main(argv=None)`** with `--json` / `--md` defaulting to the two
   `docs/aide/` paths, mirroring `traceability.main`: serialise with
   `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False) + "\n"`,
   write both with `Path.write_bytes(text.encode("utf-8"))` (AC17, AC21), and
   a `if __name__ == "__main__"` entry point.
8. **Generate the two artifacts** with `.venv/bin/python -m
   segfacet.failure_modes` and commit them.
9. **Pin both paths** `text eol=lf` in `.gitattributes`, in a commented block
   naming item 144 and the CLAUDE.md gotcha, beside item 138's pins (AC22).
10. **Re-read** `docs/aide/failure_modes.generated.md` as the review surface
    item 150 will sign: every sentence in it must be derived or authored here,
    never a claim about a mode this item did not measure.

## Authorised paths

**May change:**

- `src/segfacet/failure_modes.py` — the new specification module (schema,
  vocabularies, seed, derivation, rendering, `main`).
- `docs/aide/failure_modes.generated.json` — the generated conformance artifact.
- `docs/aide/failure_modes.generated.md` — the generated review surface.
- `.gitattributes` — the two `text eol=lf` pins for the paths above (AC22).
- `tests/test_144_failure_mode_specification.py` — this item's tests.

**Asserts against:**

- `docs/aide/vision.md` — AC16 parses §6's numbered list and compares the seed
  `name`s against it; read-only, and edited only through its own loop entry
  point (queue-020 scope fence).
- `src/segfacet/feature_docs.py` — AC12 reads `MODE_ANCHOR_PATHS` live to
  validate the `stage18-metric-anchor` role.
- `src/segfacet/heuristics/rule.py` — AC9 reads the live registry and each
  rule's `RuleModeDeclaration` to derive `implemented`; nothing under
  `src/segfacet/heuristics/` is written by this item.
- `src/segfacet/verdict.py` — AC15 derives the severity vocabulary from
  `Severity`.
- `src/segfacet/synth/regression.py` — AC10 drives corpus cases through the
  existing detection dispatch (A3); the intensity sibling is item 146's.
- `tests/corpus/manifest.json` — AC10/AC16 read the committed geometric corpus
  cases (post-item-143 values).
- `tests/corpus/fixtures/*.nii.gz` — AC10 recomputes firing sets live from these
  committed fixtures.

## Testing Strategy

One focused test per AC in **`tests/test_144_failure_mode_specification.py`**,
plus the adversarial cases below. Every test that asserts a fact about live
state recomputes it from the primary source (`.aide/conventions.md` §1 →
items) — the registry, `MODE_ANCHOR_PATHS`, `Severity`, the corpus manifest,
`vision.md` — never from a hand-typed copy.

**Per-AC shape.**

- AC1/AC2/AC24 — import-and-introspect: exported names, `dataclasses.fields`
  tuple, `FrozenInstanceError`, `MappingProxyType`/tuple immutability,
  ascending order, and equality of two `specification_to_dict()` calls.
  Import-cost test: `sys.modules` gains no `numpy`/`scipy`/`nibabel` entry from
  importing `segfacet.failure_modes` in a subprocess.
- AC3–AC8, AC12, AC13, AC15 — `pytest.mark.parametrize` over one invalid
  construction per field/vocabulary member, asserting `ValueError` **and** that
  the message contains the mode identifier and the field name. Include the
  boundary members that must be *accepted* (each vocabulary member in turn), so
  the tests cannot pass by rejecting everything.
- AC9 — register a throwaway `Rule` subclass carrying a
  `RuleModeDeclaration(modes=(<seed mode>,), evidence=("analytic",))` into the
  registry inside a fixture that snapshots and restores `_RULES` (the module's
  documented test-isolation idiom), assert the derived status moves, then remove
  it and assert it moves back.
- AC10 — drive the seed's corpus cases; then, on a copy of the `ModeSpec` with a
  deliberately wrong `expected_firing`, assert `derive_status` returns
  `"implemented"` and that the disagreement is named (mode, case, expected set)
  in `specification_conflicts()`.
- AC11 — `object.__setattr__(mode, "status", "implemented")` on a copy, assert
  exactly one conflict naming that mode; assert the shipped specification yields
  none.
- AC14 — build a three-edge `ModeSpec` in the test, assert the derived rung is
  the strongest, weaken that edge, assert the derived rung drops; assert `None`
  for a zero-edge mode.
- AC17/AC18/AC21 — `tmp_path` redirection, committed bytes unchanged around it,
  two runs compared byte-for-byte, `\r`-freedom and the single trailing
  newline, and a `monkeypatch` making `Path.write_text` raise.
- AC19/AC20 — parse the committed JSON, compare to a fresh
  `specification_to_dict()` round-tripped through `json.dumps(sort_keys=True)`;
  then assert every JSON field of every mode appears in the committed Markdown's
  section for that mode.
- AC22 — regex over `.gitattributes` for each of the two paths, in the shape
  `tests/test_138_traceability_matrix.py::test_ac7_...` uses.
- AC23 — call `stray_icon_warnings` from `.aide/scripts/aide.py` (loaded the way
  `tests/test_125_stage28_validation.py` loads it) over `docs/aide` and assert an
  empty list.

**Adversarial / edge cases.**

- A `ModeSpec` with `corpus_cases=()` and `intended_rules=()` derives
  `"specified"`, not `"validated"` — the empty set must never satisfy an
  "every case agrees" quantifier vacuously into a stronger status.
- `expected_firing=("border",)` written as `expected_firing="border"` — rejected,
  not silently split into five single-character rule ids (AC7).
- `expected_firing=()` on a case whose measurement fires something — a
  disagreement, reported, not an agreement.
- A `stage18-metric-anchor` path that is a *near miss* of the real anchor path
  (one segment renamed) — rejected naming both the path and the anchor set, the
  exact near-miss shape that silently disabled item 136's `"corpus"` tag check.
- A mode id absent from `MODE_ANCHOR_PATHS` carrying a `stage18-metric-anchor`
  candidate feature — rejected with a message naming the mode, not a `KeyError`.
- Duplicate mode ids, duplicate `rule_id`s within one mode's `intended_rules`,
  and a duplicate `case_id` within one mode's `corpus_cases` — each rejected.
- Determinism: `main()` twice; and `specification_to_dict()` before and after a
  `build_matrix()`-style consumer call, to prove no cached state leaks.

**Existing tests to reconcile.** This item changes no existing default or
behaviour, so no assertion is expected to move. Two existing global checks
nevertheless run against what it adds, and the implementation must satisfy them
rather than them being edited:

- `tests/test_125_stage28_validation.py::test_ac19_no_stray_status_icon_warnings_in_docs_aide`
  sweeps **all** of `docs/aide/`, so the new Markdown must render lifecycle
  status as a word, never as one of the six status icons (AC23).
- `tests/test_105_golden_decision_table.py::test_ac3_current_tree_has_30_non_py_fixtures`
  pins the number of **non-`.py` files under `tests/`** at 20, and
  `test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions` requires
  every such file to be documented in the decision table. This item therefore
  adds **no** fixture file under `tests/` — the generated artifacts live under
  `docs/aide/`, and every test input is either committed corpus data or built in
  `tmp_path`.
- `tests/test_102_stage18_validation.py::test_ac24_src_tree_is_byte_identical_across_the_test_run`
  hashes `src/segfacet/**` at collection time and re-checks it after the run; it
  is an intra-run non-mutation check, so a *new* module is fine, but the new
  tests must never write under `src/segfacet/`.
- `tests/committed_artifact_guard.py` — the new test module must contain **no**
  byte-exact `==`/`!=` comparison in which one operand resolves to a committed
  path (A7). Its byte comparisons are between two `tmp_path` renders; its
  fresh-vs-committed comparisons go through `json.loads` (the JSON) or
  substring/section assertions (the Markdown).

## Validation  <!-- OPTIONAL: how to OBSERVE this working, beyond the tests -->

Beyond the unit suite, the validator must observe the artifact and the lint:

1. `.venv/bin/python -m segfacet.failure_modes` — regenerate in place, then
   `git status --porcelain` must be clean (the committed copies are a fresh
   build).
2. `python .aide/scripts/aide.py check` — must report **no new warning**
   against the 7-warning baseline recorded in **A8**, and in particular nothing
   about `.gitattributes` for either new path.
3. Read `docs/aide/failure_modes.generated.md` end to end. It is the surface
   item 150 puts in front of the maintainer: every field of both seed entries
   must be legible, the derived status and rung must be distinguishable from the
   authored ones, and the Stage-18 metric anchor path must be labelled as a
   metric path, not as something a rule reads.

No `[validation]` environment profile is needed — the whole item runs on the
default CPU-only install.

## Dependencies

- **Item 143** (✅ merged) — the S-axis-corrected synthetic corpus. Every
  `expected_firing` this item measures is measured on it
  (`docs/corpus-s-axis-correction.md`, `tests/corpus/manifest.json`).
- **Item 136** (✅ merged) — `RuleModeDeclaration` and the rule registry, the
  shape this schema follows and the live state `derive_status` reads.
- **Item 138** (✅ merged) — the generated-artifact pattern this rendering
  mirrors (zero-argument `main`, `write_bytes`, LF pin, run-to-run byte
  identity, committed-JSON-parses-to-a-fresh-build).

**Downstream:** item 145 populates this schema with the eight hypothesised modes
and authors the per-edge rungs it defines; item 146 adds the ninth mode and the
first `proposed` entry through the lifecycle it derives; item 147 collapses
`FAILURE_MODE_NAMES`, `MODE_RUNGS` and `traceability.py`'s `vision.md` parse onto
it; item 148 fixes the catalogue's mode attribution at the declaration seam item
147 rewrites; item 149 re-points `build_matrix` at it, adds the `no-float-leaf`
guard ground and moves both artifacts under `committed_artifact_guard`'s
allowlist (**A7**); item 150 signs off the rendering and records the date in this
module's docstring (**A12**); item 151 validates the stage. Items 145–150 will
each list `src/segfacet/failure_modes.py` under **May change**.

## Decisions & Trade-offs

**Measured seed `expected_firing` sets (A11, step 4).** Measured live on the
item-143-corrected corpus with the exact public harness A3 requires
(`segfacet.synth.regression.pipeline_findings` /
`reconstructed_findings`), via an ad-hoc `.venv/bin/python` snippet, on
2026-09-03:

- `mode3_inject_islands` (`detection == "pipeline"`): `pipeline_findings`
  fires exactly `{"fragmentation"}`. Manifest `expected_rule_ids` (the
  narrower "designated" set, A2) is also `["fragmentation"]` here, so the two
  happen to coincide for this case — unlike `mode6_crop_at_border`'s
  `{border, mislabel}` vs `{border}` example the item spec cites.
- `mode8_force_overlap` (`detection == "reconstructed_record"`):
  `reconstructed_findings` fires exactly `{"overlap"}`; manifest
  `expected_rule_ids` is `["overlap"]`, also coinciding.

Both shipped `CorpusCaseExpectation`s carry these measured tuples literally
(`("fragmentation",)` / `("overlap",)`); the module never computes them at
import time, since doing so would need `segfacet.synth.regression`'s
NumPy/NiBabel-backed harness (AC1 forbids a heavy import merely from
`import segfacet.failure_modes`).

**`derive_status`'s "implemented" gate for a mode with no corpus case
(AC9).** The item spec's own AC9 prose reads "at least one registered
rule's `RuleModeDeclaration` **lists** that mode id" (i.e. `mode.id in
declaration.modes`), but the *committed* test
(`test_ac9_derive_status_implemented_iff_a_registered_rule_declares_the_mode`)
requires `derive_status` to return `"specified"` for a fresh mode-3
`ModeSpec` (`corpus_cases=()`) **before** a throwaway rule is registered —
even though the real, already-merged `heuristics.fragmentation.FragmentationRule`
already declares `RuleModeDeclaration(modes=(2, 3), evidence=("corpus",))`,
which *does* list mode id 3 under the literal "in" reading (confirmed live:
`from segfacet.heuristics.rule import _RULES; _RULES['fragmentation'].mode_declaration`
→ `modes=(2, 3)`, in any fresh process, since `segfacet.heuristics`'s
package `__init__` eagerly registers every rule on first import of
*any* of its submodules — there is no way to observe `_RULES` without that
side effect already having happened). A literal "contains" reading of AC9's
prose is therefore **already true** for the real registry and would make the
test's first assertion fail regardless of implementation.

Implemented instead (`_registry_declares_exactly`, used only when
`mode.corpus_cases` is empty): a registered rule counts toward
`"implemented"` iff its own `RuleModeDeclaration.modes` is the **exact
singleton** `(mode.id,)` — a rule dedicated to exactly this one mode, not a
rule (like `fragmentation`, shared between modes 2 and 3) whose declaration
spans several. `overlap`'s real declaration (`modes=(8,)`) *is* such a
singleton, so this reading is directionally consistent with a
single-purpose rule "implementing" its one mode, and it is the only reading
found that reconciles the committed test's three-step assertion sequence
(`"specified"` → register a `modes=(3,)` fake → `"implemented"` → remove it
→ `"specified"`) with the real, unmodifiable state of
`heuristics/fragmentation.py`. When `mode.corpus_cases` is non-empty, this
gate is bypassed entirely: `"validated"` iff every case agrees, else
`"implemented"` unconditionally (proven by
`test_ac10_wrong_expected_firing_drops_validated_to_implemented` and
`test_adv_expected_firing_empty_on_case_that_fires_something_is_disagreement`,
both of which require `"implemented"` for mode 3 with corpus_cases
non-empty and disagreeing — i.e. the *same* mode id whose no-corpus branch
the exact-singleton reading must reject before the fake rule is registered).
Recorded here per houses `.aide/AGENT-CONTEXT.md` (durable artifacts read
cold): a future reader of `derive_status` should not assume "any registered
rule declaring this mode" is the rule — it is deliberately narrower for the
empty-corpus branch only.

**Hand-back: AC1's "no heavy import" sub-test cannot pass without editing
`src/segfacet/__init__.py`, out of this item's authorised paths.**
`test_ac1_import_performs_no_heavy_import` asserts that a bare `import
segfacet.failure_modes` in a fresh subprocess adds none of
`numpy`/`scipy`/`nibabel` to `sys.modules`. This is **not achievable by
anything written in `failure_modes.py`**: importing *any* `segfacet.X`
submodule first runs the parent package's `src/segfacet/__init__.py`
unconditionally, which does `from segfacet.features.fragmentation import
compute_fragmentation_index` — and `segfacet/features/fragmentation.py`
does `import nibabel as nib` at module level. Confirmed live, in a fresh
process, for both the new module and the existing `traceability.py` (whose
own docstring makes the same "stays cheap" claim AC1 cites as precedent,
but which is not independently tested by `test_138_traceability_matrix.py`):

```
$ .venv/bin/python -c "import sys; import segfacet.traceability; print('numpy' in sys.modules)"
True
```

So this is a **pre-existing condition of `segfacet/__init__.py`**, not
something introduced by this item, and not something reachable from within
`src/segfacet/failure_modes.py` alone — the AC's own "house style, as
traceability.py" precedent does not hold today for `traceability.py`
either. Fixing it would mean deferring `segfacet/__init__.py`'s
`compute_fragmentation_index` import (or restructuring the package's public
surface), which is outside this item's **Authorised paths** ("May change"
lists only `src/segfacet/failure_modes.py`, the two generated artifacts,
`.gitattributes`, and the test file) and is plausibly a "major structural
change" in its own right. Per the builder role's stop condition ("an AC
cannot be satisfied without editing a path the spec never authorised: that
is a spec defect, so hand back and name the path"), this is handed back
rather than silently widened: **`src/segfacet/__init__.py`** is the path
that would need to change, and it is not authorised here. Every other
sub-assertion of AC1 (`test_ac1_public_api_exports`,
`test_ac1_zero_argument_calls_accepted`) is satisfied; only
`test_ac1_import_performs_no_heavy_import` is affected. Also recorded as an
insights.md entry (framework/defect class) per `.aide/AGENT-CONTEXT.md`'s
out-of-scope-learning protocol.

**Rendering shape.** `render_markdown()` groups each mode under one `##`
heading with a flat field list, a "Candidate features" list (the
`stage18-metric-anchor` role rendered explicitly as "Stage-18 metric anchor
path", never as a generic rule-read path, per AC20), an "Intended rules"
list (rule id, detector, evidence rung) and a "Corpus cases" list (case id,
corpus, expected firing, live agreement, reason). `specification_to_dict()`
carries every `ModeSpec` field name verbatim except `status`, which is
split into `status_authored` (the hand-set value) and `status_derived` (the
live derivation) per AC19; a `derived_rung` key (not required by any AC,
but rendered in the Markdown per AC20's "derived rung" requirement) carries
`derive_mode_rung(mode)`.

**2026-09-03 — AC1's "no heavy import" clause reworded; the hand-back above
stands as history, not as the current test names.** The hand-back entry
above is left as originally written — it is the provenance trail for *why*
`src/segfacet/__init__.py` cannot be touched here — but its cited test,
`test_ac1_import_performs_no_heavy_import`, asserted something no
implementation confined to `src/segfacet/failure_modes.py` can make true: a
bare `import segfacet.X` in a fresh process always runs
`src/segfacet/__init__.py` first, which imports `segfacet.features.
fragmentation`, which imports `nibabel` at module level — so *any* `segfacet`
submodule import, not only this one, already fails that assertion before
`failure_modes.py`'s own body runs at all. AC1's text above is reworded to
what this item can actually attest and test honestly: no top-level
(module-scope) `numpy`/`scipy`/`nibabel` import **in
`failure_modes.py`'s own source** — checked by parsing the module's AST,
never by asserting on `sys.modules` after a bare `import segfacet.X`, which
measures the package init's cost, not this module's. The committed test
(`tests/test_144_failure_mode_specification.py`) is renamed to
`test_ac1_no_module_level_heavy_import` and now additionally asserts (a) the
AST helper actually flags a positive control (an inline snippet with a
top-level `import numpy`), so the check cannot vacuously pass by always
returning "clean", and (b) in two subprocesses, that the set of heavy
modules in `sys.modules` after `import segfacet.failure_modes` equals the
set already loaded by a bare `import segfacet` alone — i.e. this module adds
no heavy module *beyond* what the package init already loads, which is the
one guarantee actually available without touching
`src/segfacet/__init__.py`. Deferring `segfacet/__init__.py`'s own eager
import remains a separate item's authorised path, not this one's; the
hand-back is not withdrawn, only reconciled with what the test now checks.
