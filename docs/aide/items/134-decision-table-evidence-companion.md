# Item 134 — Generate the decision table's measured counts into a companion artifact

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 134
> **Objectives:** G7
> **Suggested branch:** `aide/134-generate-the-decision-table-s`

---

## Description

[`golden-decision-table.md`](../golden-decision-table.md) is a human-signed
document (dispositions decided row by row by the maintainer, 2026-07-28, item
105). Nine of its Section-1 rows carry an `evidence` cell of the shape
`26/94 leaf paths unwired` — a **live measurement**, not a judgement:
`tests/test_105_golden_decision_table.py::test_ac7_golden_row_evidence_is_measured_not_transcribed`
re-derives `N/M` from `segfacet.catalogue.build_catalogue()` and
`iter_leaf_paths()` over `build_report_for_case(case)` and asserts the
document agrees.

The consequence is that **every feature-adding item has to edit a signed
document to keep a number current**. Measured from `git log` on the file: five
amendments (`8e66b6f` item 106, `d50748a` item 110, `aa59a83` item 122 —
titled "refresh stale leaf-path counts" — `12ce93c` item 121, `861a4ce` item
123) each moved `N/M` while their own prose had to assert that no
`disposition`, `rationale` or `replacement guarantee` cell changed. That
assertion has held every time, which is precisely the point: the column is
mechanical, it lives in the wrong document, and each refresh is an
unnecessary write to signed text.

This item moves the measurement out and leaves a pointer behind.

**Deliverables.**

1. A new generator, `src/segfacet/golden_evidence.py`, run as
   `python -m segfacet.golden_evidence`, mirroring the house pattern
   `src/segfacet/catalogue.py` already sets for a committed
   `docs/aide/*.generated.*` artifact (a `main()` writing `write_bytes` of
   `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False)` plus a
   trailing newline).
2. The committed companion `docs/aide/golden_evidence.generated.json`:
   per corpus case, the total and unwired leaf-path counts. Byte-reproducible
   run-to-run, `\n` bytes, `text eol=lf` in `.gitattributes`.
3. `test_105`'s drift assertion re-pointed: it compares the **companion**
   against a measurement it re-derives itself, and reads no number from the
   signed document.
4. The nine signed rows' `evidence` cells replaced by one stable pointer
   string, recorded as a dated amendment paragraph in the same series as the
   five mechanical amendments above it (item 126's precedent: record the
   execution, never rewrite the judgement).
5. The two item-126 tests that pin the old shape reconciled — its AC18
   four-column digest fence narrowed to the three *judgement* columns, and
   its AC22 `26/94` pin re-pointed at the companion.

**Not in scope.** No `disposition`, `rationale`, `replacement guarantee` or
`what it asserts today` cell changes. No Section-1 or Section-2 row is added,
removed or reordered. No golden, corpus fixture or reference artifact is
regenerated. `tests/committed_artifact_guard.py`'s five-member `GROUNDS`
vocabulary is **not** extended and its `ALLOWLIST` gains no entry (see
Decisions). No feature, rule or catalogue *content* changes: the measurement
is 26/94 on every one of the nine cases before this item and must still be
26/94 after it (verified on this branch, 2026-08-31).

## Acceptance Criteria

- [ ] **AC1: the generator module exists and runs as a module.**
  `src/segfacet/golden_evidence.py` defines `build_evidence()`,
  `render_json(payload)` and `main(argv=None) -> int`, exports them in
  `__all__`, and `python -m segfacet.golden_evidence` exits 0 and writes the
  companion.

- [ ] **AC2: the companion's shape.** `docs/aide/golden_evidence.generated.json`
  parses as JSON and holds a `cases` object with exactly one entry per case
  id in `segfacet.synth.corpus.load_manifest()["cases"]`, each entry having
  integer `total_leaf_paths` and `unwired_leaf_paths` keys and no others.

- [ ] **AC3: byte-reproducible run-to-run.** Two successive `main()` runs
  writing to two distinct destinations under `tmp_path` produce byte-identical
  files.

- [ ] **AC4: the committed companion equals a fresh build.**
  `json.loads(<committed companion text>)` equals `build_evidence()` — the
  whole payload, not just the counts — so a hand-edited value, a missing case
  or an added case fails.

- [ ] **AC5: written with `\n` bytes.** The committed companion's bytes
  contain no `\r` and end with exactly one `\n`.

- [ ] **AC6: the line-ending pin exists and is effective.** `.gitattributes`
  covers `docs/aide/golden_evidence.generated.json` with an `eol=lf` rule,
  asserted by resolved pattern coverage (the pattern that matches the path),
  not by a literal substring search of the file.

- [ ] **AC7: `aide check` is clean for the new paths.**
  `python .aide/scripts/aide.py check` emits no warning naming
  `docs/aide/golden_evidence.generated.json` or
  `src/segfacet/golden_evidence.py`.

- [ ] **AC8: `test_105`'s drift assertion compares the companion, not the
  table.** `tests/test_105_golden_decision_table.py::test_ac7_golden_row_evidence_is_measured_not_transcribed`
  keeps its name, reads `N`/`M` from the companion, and asserts them equal to
  a measurement it computes in its own body from
  `catalogue.build_catalogue()` / `catalogue.iter_leaf_paths()` over
  `segfacet.synth.golden.build_report_for_case(case)`. Its body contains no
  call into `segfacet.golden_evidence` (the oracle must be independent of the
  generator) and reads no cell of `golden-decision-table.md`.

- [ ] **AC9: the signed cells carry a stable pointer, not a number.** The nine
  Section-1 rows whose fixture path ends `/<case_id>.json` for the nine corpus
  case ids all carry byte-identical `evidence` cells; that cell names
  `docs/aide/golden_evidence.generated.json` and contains no digit.

- [ ] **AC10: the judgement columns are byte-unchanged.** For all eleven
  retired Section-1 rows, `what it asserts today`, `disposition` and
  `replacement guarantee` are byte-identical to the document as it stood at
  this branch's merge base.

- [ ] **AC11: item 126's AC18 fence is narrowed, not re-baselined.**
  `tests/test_126_golden_retirement.py`'s `_row_cell_digest` digests exactly
  `what it asserts today`, `disposition` and `replacement guarantee`;
  `_AC18_PRE_ITEM_ROW_DIGESTS` still holds eleven entries, recomputed for the
  narrowed tuple, and its comment names item 134's authorised `evidence`
  substitution alongside the sentence it already carries for `asserted by`.

- [ ] **AC12: item 126's `26/94` pin survives, re-pointed.**
  `tests/test_126_golden_retirement.py::test_ac22_documented_2694_evidence_still_verifies_unchanged`
  reads the pinned `(26, 94)` from the companion instead of the signed row,
  still cross-checks it against a live `build_report_for_case` measurement,
  and passes for all nine case ids.

- [ ] **AC13: the amendment is recorded, dated, and structural headings are
  untouched.** `golden-decision-table.md` gains exactly one new preamble
  paragraph, opening `**Evidence cells re-pointed 2026-08-31 (item 134).**`,
  stating that only the `evidence` column moved and that no judgement column
  changed; the five mandated `## ` headings remain in order, `## Retirement
  execution log` still follows `## Divergences from the roadmap's working
  assumption`, and no line matches `test_105`'s sign-off-field pattern.

- [ ] **AC14: Section 2 is not extended.** Section 2 still holds exactly the
  seven fixtures in `test_105`'s `_SECTION2_EXPECTED_FIXTURES`, and that
  constant is unchanged — the companion is deliberately not listed there (see
  Decisions).

- [ ] **AC15: a stale companion fails the drift check.** Feeding the drift
  comparison a companion payload whose `unwired_leaf_paths` (or
  `total_leaf_paths`) for one case is off by one fails with a message naming
  that case id and both the recorded and the measured number; that same test
  leaves `docs/aide/golden-decision-table.md` byte-unchanged.

- [ ] **AC16: the item-127 guard stays clean.**
  `committed_artifact_guard.iter_violations()` over `tests/` reports no
  violation; `committed_artifact_guard.GROUNDS` still has exactly its five
  members and `ALLOWLIST` gains no entry.

- [ ] **AC17: the companion carries nothing environment-dependent.** Every
  numeric leaf in the committed companion is an `int` (no `float`), and its
  text carries no date, no absolute path, no drive-letter prefix and no
  hostname.

- [ ] **AC18: item 126's inventory and execution-log tests stay green.**
  `tests/test_126_golden_retirement.py` passes in full, and
  `tests/test_105_golden_decision_table.py::test_ac3_current_tree_has_30_non_py_fixtures`
  still counts 20 — the companion lives outside `tests/`, so the inventory
  does not move.

## Assumptions

Resolved under `loop.clarify = "assume"` — each is the most defensible
default, recorded here for audit rather than blocking on a question.

- **The companion is one JSON file, not the catalogue's JSON+Markdown pair.**
  `catalogue.py` emits both because its Markdown is a browsable ~100-entry
  reference document for humans. This artifact is nine two-integer records; a
  second rendered form would be a redundant surface with no reader. Pins one
  path: `docs/aide/golden_evidence.generated.json`.

- **The generator is a package module, not a `scripts/` file.** Assumed the
  house pattern (`segfacet.catalogue`) governs: the artifact is regenerated by
  `python -m <module>`, the module is importable by its tests, and it inherits
  the `src/segfacet/**/*.py text eol=lf` pin. It is a new module rather than a
  third output of `segfacet.catalogue.main()` because it needs the committed
  synth corpus (`load_manifest` + `build_report_for_case`) that
  `build_catalogue()` deliberately does not.

- **`evidence` is not a judgement column.** Assumed from the document's own
  five amendment paragraphs, each of which states that no `disposition`,
  `rationale` or `replacement guarantee` cell was touched while the `evidence`
  numbers moved — the document has always treated `evidence` as the mechanical
  column. This item makes that separation structural.

- **No `aide gate` is raised for the signed-document edit.** See Validation
  for the reasoning; the queue's reviewed-PR checkpoint is the human's look.

- **The measurement does not move.** Measured on this branch 2026-08-31: all
  nine cases read `26/94`. The committed companion must therefore record
  `26/94` for every case at landing. If the builder measures anything else,
  something upstream changed and the item hands back rather than committing a
  different number — a count change is not this item's business.

- **`aide check`'s `.gitattributes` lint will not resolve the companion.**
  Assumed from the lint's implementation (`gitattributes_eol_pin_warnings`
  feeding `_byte_exact_reads`, `.aide/scripts/aide.py`): it fires only on a
  read sitting directly inside an `==`/`!=` comparison, and nothing here
  byte-compares the committed companion. AC7 is therefore an honestly-vacuous
  pass and **AC6 is the real enforcement** — the same point item 128 recorded
  about carrying a pin across a helper-function boundary.

## Implementation Steps

1. **Write `src/segfacet/golden_evidence.py`.** Module docstring naming item
   134, the document it serves, and the scope fence (it measures; it decides
   nothing). Defer the heavy imports (`catalogue`, `synth.corpus`,
   `synth.golden`) into the function bodies, per this repo's CLI convention.
   - `EVIDENCE_PATH = _REPO_ROOT / "docs" / "aide" / "golden_evidence.generated.json"`,
     with `_REPO_ROOT = Path(__file__).resolve().parents[2]` — the shape
     `catalogue.py` uses.
   - `SCHEMA_VERSION = "1.0"` and a module-level `_NOTE` constant: one fixed
     sentence naming the regeneration command
     (`python -m segfacet.golden_evidence`), stating "do not hand-edit", and
     naming `docs/aide/golden-decision-table.md` as the consumer. No date, no
     count, nothing that drifts.
   - `build_evidence()` — build the catalogue once (`build_catalogue()`), fold
     `entry.path` to `entry.status` once, then for each case in
     `load_manifest()["cases"]` compute
     `leaf_paths = iter_leaf_paths(build_report_for_case(case)["features"])`,
     `total_leaf_paths = len(leaf_paths)` and `unwired_leaf_paths` as the count
     of paths whose status is `"unwired"`. Return
     `{"schema_version": ..., "note": ..., "cases": {...}}`. Every value an
     `int` or a `str`, never a `float`.
   - `render_json(payload)` — `json.dumps(payload, indent=2, sort_keys=True,
     ensure_ascii=False)` plus a trailing newline.
   - `main(argv=None)` — `argparse` with `--out` defaulting to
     `EVIDENCE_PATH`, `mkdir(parents=True, exist_ok=True)`, then
     `write_bytes(render_json(build_evidence()).encode("utf-8"))`, return 0.
     Guard the module tail with the usual `__main__` block calling
     `sys.exit(main())`.
2. **Generate and commit the companion** by running
   `.venv/bin/python -m segfacet.golden_evidence`. Do not hand-write it.
3. **Pin it.** Add to `.gitattributes`, beside the item-103 catalogue pins, a
   comment naming item 134 and the line
   `docs/aide/golden_evidence.generated.json text eol=lf`.
4. **Re-point the nine signed cells.** In
   `docs/aide/golden-decision-table.md`, replace each of the nine
   `26/94 leaf paths unwired` cells with the identical pointer string
   `measured in docs/aide/golden_evidence.generated.json` (path in backticks).
   Change nothing else on those rows.
5. **Record the amendment.** Add one paragraph to the preamble series (after
   the item-123 paragraph, before `## Section 1`), opening
   `**Evidence cells re-pointed 2026-08-31 (item 134).**`, saying: the nine
   Group-A `evidence` cells now point at the generated companion rather than
   carrying a number; the measurement did not move (26/94 before and after);
   no `disposition`, `rationale`, `replacement guarantee` or `what it asserts
   today` cell was touched; and this is the last such amendment, because the
   count no longer lives here. Write with `\n` bytes and no line that could
   read as a sign-off field.
6. **Re-point `test_105`'s AC7.** Keep the function name. Read the companion
   through a literal path constant in the test module (never through
   `segfacet.golden_evidence`), pull `cases[case_id]`, and compare against the
   measurement the function already computes in its own body. Add a sibling
   test for AC9's pointer shape on the nine rows. Delete `_EVIDENCE_RE` and
   `test_adv_ac7_malformed_evidence_cell_fails_format_before_arithmetic` —
   nothing parses the `N/M` cell format any more. Leave
   `_SECTION2_EXPECTED_FIXTURES` and every other AC alone.
7. **Reconcile `tests/test_126_golden_retirement.py`.** Narrow
   `_row_cell_digest` to the three judgement columns; recompute the eleven
   `_AC18_PRE_ITEM_ROW_DIGESTS` values against the pre-item document
   (`git show <merge-base>:docs/aide/golden-decision-table.md`); extend the
   constant's comment with a sentence naming item 134 as the authorised
   reconciler of `evidence`, matching the sentence already there for
   `asserted by`. In `test_ac22_documented_2694_evidence_still_verifies_unchanged`,
   read `(documented_n, documented_m)` from the companion instead of the row
   regex, keeping both the `(26, 94)` pin and the live cross-check.
8. **Write `tests/test_134_decision_table_evidence_companion.py`** per the
   Testing Strategy below.
9. **Verify** with the Validation section's commands before committing.

## Authorised paths

**May change:**

- `src/segfacet/golden_evidence.py` — the new generator (step 1).
- `docs/aide/golden_evidence.generated.json` — the new committed companion
  (step 2). Generated only; never hand-edited.
- `.gitattributes` — the `text eol=lf` pin for the new committed text
  artifact (step 3). In scope here precisely because this item *adds* a
  committed generated text file, unlike items 127/128 where the file was
  read-only.
- `docs/aide/golden-decision-table.md` — nine `evidence` cells and one dated
  preamble paragraph (steps 4–5). Judgement columns untouched.
- `tests/test_105_golden_decision_table.py` — AC7 re-pointed, the AC9 pointer
  test added, the dead `N/M` parser removed (step 6).
- `tests/test_126_golden_retirement.py` — AC18 digest narrowed and AC22
  re-pointed (step 7).
- `tests/test_134_decision_table_evidence_companion.py` — new test module.

**Asserts against:**

- `src/segfacet/catalogue.py` — `build_catalogue()` / `iter_leaf_paths()` are
  the measurement oracle for AC4/AC8/AC12/AC15, recomputed live from committed
  state; read, never changed.
- `src/segfacet/synth/golden.py` (`build_report_for_case`) and
  `src/segfacet/synth/corpus.py` (`load_manifest`) — the per-case records the
  measurement walks; read, never changed.
- `tests/corpus/manifest.json` and `tests/corpus/fixtures/*.nii.gz` — the
  corpus the nine measurements derive from; unchanged, and no golden or
  reference artifact is regenerated.
- `tests/committed_artifact_guard.py` — AC16 pins its five-member `GROUNDS`
  and its `ALLOWLIST` as unchanged.
- `tests/test_127_committed_artifact_tolerance.py`,
  `tests/test_111_golden_guard.py`, `scripts/aide_status_report.py` —
  unchanged and still green.

`docs/aide/progress.md` is deliberately absent from both lists: this item's
tests neither read nor write it, and listing it under "Asserts against" makes
`aide scope` FAIL by construction, since every item's mandatory
`aide progress set` commits a real change to it.

## Testing Strategy

New module `tests/test_134_decision_table_evidence_companion.py`, plus the two
reconciliations in steps 6–7. One focused test per AC:

- **AC1–AC2** — import the generator, call `build_evidence()`, assert the key
  set of `cases` equals the manifest's case ids and each entry has exactly the
  two integer keys.
- **AC3** — `main(["--out", str(tmp_path / "a.json")])` then
  `main(["--out", str(tmp_path / "b.json")])`, and compare the two files'
  bytes. Fresh-vs-fresh: no committed operand, so neither the item-127 guard
  nor the framework lint sees it.
- **AC4** — parse the committed companion and compare the parsed payload with
  `build_evidence()`.
- **AC5** — assert `b"\r" not in raw`, `raw.endswith(b"\n")` and
  `not raw.endswith(b"\n\n")`. Membership and `endswith`, deliberately not an
  equality against a committed read.
- **AC6** — resolve the `.gitattributes` patterns and assert one covers the
  companion path, mirroring
  `tests/test_127_committed_artifact_tolerance.py::test_ac14_every_allowlisted_path_is_line_ending_pinned`'s
  effective-coverage approach rather than a `startswith` on the raw text.
- **AC7** — run `python .aide/scripts/aide.py check` as a subprocess (the CLI
  is stdlib-only, so no venv is needed) and assert neither new path appears in
  its output.
- **AC9** — parse Section 1, select the nine rows by `/<case_id>.json` suffix
  (never by a literal retired-directory path — item 126 AC17), assert their
  `evidence` cells are all equal, name the companion, and contain no digit.
- **AC10** — read the pre-item document via
  `git show <merge-base>:docs/aide/golden-decision-table.md` in a subprocess
  and compare the three judgement cells of all eleven retired rows against the
  current document, row by row. This is the item's own scope fence and does
  not lean on item 126's constant.
- **AC13** — assert the amendment paragraph appears exactly once, the five
  mandated headings are present in order, `## Retirement execution log`
  follows `## Divergences from the roadmap's working assumption`, and
  `test_105`'s sign-off pattern still matches nothing.
- **AC14** — import `test_105`, assert `_SECTION2_EXPECTED_FIXTURES` has seven
  members and that the parsed Section 2 fixture set equals it.
- **AC15** — factor the drift comparison into a helper taking a payload, so
  the adversarial case feeds a mutated in-memory copy and the committed
  companion is never rewritten. Assert the failure message names the case id
  and both numbers, and that `golden-decision-table.md`'s bytes before and
  after the test are equal.
- **AC16** — `committed_artifact_guard.iter_violations()` over `tests/` is
  empty; `set(GROUNDS)` still equals the five-member set; the `ALLOWLIST` path
  set is unchanged.
- **AC17** — walk the parsed companion recursively asserting no leaf is a
  `float`; assert the raw text matches no `\d{4}-\d{2}-\d{2}`, no
  drive-letter prefix, and contains no `/`-rooted path segment.
- **AC18** — assert `test_ac3_current_tree_has_30_non_py_fixtures`'s walk
  still yields 20 paths; the rest of AC18 is demonstrated by the validator
  running `tests/test_126_golden_retirement.py` in full.

Adversarial / edge cases beyond AC15: `build_evidence()` called twice in one
session returns equal payloads and mutates nothing importable (idempotence);
`main()` creates a missing parent directory; a companion missing a case id
fails AC2 naming the id rather than raising `KeyError`; a companion whose
counts are strings rather than ints fails AC2 on type, not on value; the
pointer assertion rejects a cell that merely *mentions* the companion while
still carrying a number.

**Existing tests to reconcile** (swept 2026-08-31; each pins the pre-item
shape and fails without the named change — reconciling them here is what keeps
the first validation round about the new code rather than stale assertions):

- `tests/test_105_golden_decision_table.py::test_ac7_golden_row_evidence_is_measured_not_transcribed`
  — parses `26/94` out of the signed row. Re-pointed at the companion (AC8).
- `tests/test_105_golden_decision_table.py::test_adv_ac7_malformed_evidence_cell_fails_format_before_arithmetic`
  and `_EVIDENCE_RE` — the cell format they guard no longer exists anywhere.
  Removed.
- `tests/test_126_golden_retirement.py::test_ac18_retired_row_cells_are_byte_unchanged`
  — its digest spans four cells including `evidence`. Narrowed to the three
  judgement columns and recomputed (AC11).
- `tests/test_126_golden_retirement.py::test_ac22_documented_2694_evidence_still_verifies_unchanged`
  — regex-parses the signed row for `26/94`. Re-pointed at the companion
  (AC12).
- `tests/test_126_golden_retirement.py::test_ac22_test105_evidence_test_reads_fresh_output_not_committed_file`
  — asserts `test_105`'s AC7 body still contains `build_report_for_case` and
  no `tests/corpus/golden` / `GOLDEN_DIR` reference. **This constrains the
  design**: the re-pointed AC7 must keep computing its own measurement inline
  (AC8) rather than delegating to the generator. No change needed if AC8 is
  honoured — but a builder who "tidies" AC7 into a generator call breaks it.
- `tests/test_127_committed_artifact_tolerance.py::test_ac12_ground_vocabulary_is_closed_at_five_members`
  — would fail if a sixth `GROUNDS` member were added. This item adds none
  (AC16), so the test is pinned unchanged rather than reconciled.

## Validation

Beyond the unit suite, three observations the validator must execute:

1. **The committed companion is exactly what the generator emits** — the
   strongest form of "never hand-maintained", observable without any
   test-side byte comparison against a committed artifact:

   ```
   .venv/bin/python -m segfacet.golden_evidence
   git diff --exit-code docs/aide/golden_evidence.generated.json
   ```

   Must exit 0. Run it twice; still 0.

2. **The signed diff is exactly nine cells and one paragraph.**
   `git diff <merge-base> -- docs/aide/golden-decision-table.md` must show
   only the nine `evidence` cell substitutions and the added amendment
   paragraph. Any hunk touching a `disposition`, `rationale`, `replacement
   guarantee` or `what it asserts today` cell fails the item.

3. **The loop's own checks are clean:** `python .aide/scripts/aide.py check`
   reports no new warning, and `python .aide/scripts/aide.py scope --item 134`
   passes against the Authorised paths above.

**On the signed-text rule, and why no `aide gate` is raised.** This item edits
a human-signed document once. That is authorised, and the authorisation is
recorded rather than assumed:

- The edit is confined to the `evidence` column, which the document's own five
  amendment paragraphs (items 106, 110, 121, 122, 123) already treat as
  mechanical — each states that no `disposition`, `rationale` or `replacement
  guarantee` cell was touched. This item touches none either, and AC10 proves
  it against the pre-item bytes.
- `queue-018.md`'s scope fence names this item as the owner of exactly this
  move: *"a live count moves out of the signed document rather than being
  refreshed inside it (item 134)"*. The move is the authorisation.
- Item 126 set the recording precedent: execution against a signed row goes in
  a dated note, never a rewrite of the judgement. AC13's amendment paragraph
  is that note.
- A gate exists for a decision that is not derivable from the work. Nothing
  here is such a decision — the substituted text is mechanical and the numbers
  do not change. The human's look is the queue's reviewed PR, which is where
  the Stage-29 branch lands (`CLAUDE.md`'s stacked queue-branch shape), and
  Validation step 2 makes that diff trivially auditable. Raising a gate is
  always safe and a reviewer may add one; this spec does not require it, and
  under `loop.clarify = "assume"` the run does not block for it.

No `[validation]` profile applies — the item introduces no optional dependency
and needs no special environment.

## Dependencies

- **Item 126** (✅) — executed the retirement, so the companion describes the
  post-retirement rows; its AC18 digest fence and AC22 count pin are the two
  surfaces this item reconciles.
- **Item 127** (✅) — the committed-artifact guard whose five-member `GROUNDS`
  vocabulary this item deliberately does not extend (AC16).

**Downstream:** item 135 (the Stage 29 validation) replays this item's
regenerate-and-`git diff` check as part of the stage audit.

## Decisions & Trade-offs

Recorded at spec time; the builder appends to this section as it goes.

- **One JSON file, not a JSON+Markdown pair.** See Assumptions. Trade-off: no
  rendered human view. Accepted — nine two-integer records read fine as JSON,
  and the signed table's pointer names the path directly.

- **No byte-exact fresh-vs-committed comparison, so no `ALLOWLIST` entry and
  no sixth `GROUNDS` member.** The obvious mirror of
  `tests/test_103_feature_catalogue.py`'s committed-vs-fresh byte assertion
  would byte-compare the committed companion against a fresh regeneration —
  which item 127's guard flags unless the path is allowlisted, and no existing
  ground fits an artifact with *zero* float leaves (`exact-parameter-floats`,
  `emission-clamped` and `hand-written-literals` all describe float handling;
  `binary-fixture` and `integrity-pin` describe other shapes). Adding a sixth
  ground would also force renaming
  `test_ac12_ground_vocabulary_is_closed_at_five_members`, reopening a
  vocabulary item 127 closed on purpose, for an artifact whose entire failure
  mode — cross-platform float drift — cannot occur. Instead: AC4 compares the
  parsed payload, AC3 compares fresh-vs-fresh bytes, and Validation step 1
  observes committed-vs-fresh byte identity through `git diff`, which needs no
  comparison inside a test at all. **Trade-off:** a whitespace-only hand edit
  to the committed file would pass AC4 and fail only Validation step 1.
  Accepted — the values, the case set and the note are all pinned, and the
  artifact is one command away from being regenerated. *For the record, had an
  allowlist entry been required, the honest ground would have been a new sixth
  member covering an artifact whose numeric leaves are integer set
  cardinalities — not one of the five existing float grounds.*

- **The companion is not added to Section 2.** Section 2 surveys *adjacent*
  exact-match artifacts that would make the table misleading if omitted. This
  artifact is the table's own appendix: every number in it is described by the
  very rows that point at it, so omitting it hides nothing. Adding a row would
  also mean writing a `disposition` — a judgement column — into a signed
  document, which is the one thing this item must not do, and would cascade
  into `_SECTION2_EXPECTED_FIXTURES` and a test whose name pins the count at
  seven. AC14 locks this in so a builder does not drift into it.

- **`test_126`'s AC18 digest is narrowed, not re-baselined.** Recomputing the
  four-column digests over the new pointer text would keep the fence's width
  but destroy its meaning — a scope fence re-baselined by whoever trips it
  proves nothing. Narrowing it to the three judgement columns makes it assert
  what item 126 actually claimed (the *judgement* is untouched) and stops it
  re-firing on every future mechanical amendment. The constant's own comment
  already carries exactly this treatment for the `asserted by` column, so this
  follows a precedent set inside the fence itself.

- **The drift oracle stays independent of the generator.** `test_105`'s AC7
  must not call `segfacet.golden_evidence`, or it would compare the generator
  against itself and pass on any self-consistent bug. It re-derives the
  measurement from `build_catalogue()` in its own body — which also satisfies
  item 126's AC22 source assertion for free.
