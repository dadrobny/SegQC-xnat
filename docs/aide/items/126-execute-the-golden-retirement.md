# Item 126 — Execute the golden retirement

> **Created:** 2026-08-30 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene (deliverable **D1**)
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 126
> **Objectives:** G7 (evaluable & regression-testable — what the suite actually
> guarantees, and what it merely pins)
> **Suggested branch:** `aide/126-execute-the-golden-retirement`

---

## Description

Eleven committed whole-record report snapshots were dispositioned **retire** by
the human maintainer on 2026-07-28 (item 106's row-by-row review, recorded in
[`../golden-decision-table.md`](../golden-decision-table.md) Section 1 and
attested by `progress.md`'s Stage-19 acceptance list). This item executes that
disposition: it **deletes** the eleven files and lands the four replacements the
signed rows name. It is the first item of Stage 29 because every queue since has
paid the regeneration cascade — items 119, 120 and 123 each regenerated all nine
corpus snapshots plus both reference artifacts and touched ~8 pinning test
modules, and three of those items' test-writing passes reintroduced byte-exact
comparisons against committed float-carrying artifacts that only PR #56's CI
matrix caught.

**The eleven files.**

- `tests/corpus/golden/{clean_control,mode1_displace,mode2_fragment,mode3_inject_islands,mode4_relabel_swap,mode5_remove_level,mode6_crop_at_border,mode7_sequence_break,mode8_force_overlap}.json`
  — the nine per-case `segfacet run` reports (item 042).
- `tests/golden/016_features_report.json` and `tests/golden/022_stage3_report.json`
  — the two report-serialisation snapshots (items 016 / 022).

**The four replacements**, verbatim from the signed rows:

1. **Intra-run determinism** stays covered by the existing run-to-run tests,
   none of which needs a committed file:
   `test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical`,
   `::test_ac12_main_regenerates_matching_goldens`,
   `test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism`,
   plus `test_016_features_json.py::test_ac5_deterministic_repeated_serialisation`
   and `test_022_stage3_serialisation.py::test_ac8_determinism_two_calls_equal` /
   `::test_ac8_determinism_report_level`.
2. **Schema validity** re-points at a *freshly built* report:
   `test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates`
   validates `build_report_for_case(case)` output against `report_schema_v0.json`.
3. **"Verdict/findings unchanged"** — the one load-bearing use of the snapshots
   — moves to the narrow verdict+findings shape expectation already in the tree,
   `test_098_stray_components._PRE_098_GOLDEN_VERDICT_AND_FINDINGS`, compared
   against freshly built output. It pins no feature value, so it survives a
   feature retune. `test_102_stage18_validation.py` already consumes it exactly
   this way against CLI output; this item extends the same pattern to the
   in-process consumers.
4. **Report-*format* guarantees** (key order, key set, float rendering) move out
   of the two `tests/golden/` snapshots into **one** small, hand-constructed,
   feature-value-free fixture shared by `test_016` and `test_022`. Because every
   number in it is a literal rather than an extractor output, it cannot drift by
   ~1 ULP and cannot be invalidated by a feature retune — the two failure modes
   that retired its predecessors.

**Nothing is regenerated on the way out.** Regenerating a snapshot "so the
diff is clean" is the exact move the disposition forbids; `git log` for each
retired path must end in a deletion.

**What stays.** The corpus itself — `tests/corpus/manifest.json` and the ten
`tests/corpus/fixtures/*.nii.gz` — is untouched, as is the harness in
`src/segfacet/synth/golden.py` that regenerates reports into a caller-supplied
directory. Only the *committed whole-record report snapshots* go. The harness
loses its ability to write to the retired location (see AC14/AC15/AC16), so the
retirement cannot be silently undone by running the update path.

**The consumer surface is three times what the table records.** The decision
table's "asserted by" column names six modules (`test_042`, `test_089`,
`test_090`, `test_094`, `test_098`, `test_102`; `test_102` reads the constant,
not a file). A mechanical sweep on 2026-08-30 (AST walk over `tests/` for
`GOLDEN_DIR` / `load_golden` / `read_golden_text` / `check_case_golden` /
`golden_path`) found **twelve** modules and ~40 test functions — the table's
column has gone stale with every item since 105. The full inventory and a
per-function disposition are in Testing Strategy; reconciling all of it is in
scope, because half of those consumers **fail silently** rather than loudly when
the files vanish: nine functions iterate `GOLDEN_DIR.glob("*.json")`, which over
an empty directory is a vacuous green test.

**What this item is NOT.** It changes no extractor, no rule, no threshold and no
report schema; it moves no number. It does not build Stage 21's real-GT corpus
(replacement (iv) of the signed rows names it, and it remains Stage 21's work —
the retirement does not wait on it). It does not touch
`docs/aide/progress.md`, and it does not rewrite one word of the maintainer's
signed disposition, rationale or replacement text: execution is recorded as a
dated line per row in a **new** log section appended after the document's
existing five sections. It does not build item 127's enforced allowlist or its
shared tolerance helper (that item lands next, against this item's
post-retirement inventory). Two documents that will name retired paths after
this item — `CLAUDE.md`'s "Note what the golden tests actually assert" paragraph
and `.aide/conventions.md` — are process/framework files, PR-gated and out of an
item's scope; both are captured in `insights.md` instead.

## Acceptance Criteria

- [ ] **AC1: The nine corpus snapshots are gone.** No file matching
  `tests/corpus/golden/*.json` exists in the working tree.

- [ ] **AC2: The two serialisation snapshots are gone.**
  `tests/golden/016_features_report.json` and
  `tests/golden/022_stage3_report.json` do not exist.

- [ ] **AC3: The corpus survives intact.** Every case in
  `tests/corpus/manifest.json` still resolves to an existing
  `tests/corpus/fixtures/*_seg.nii.gz`, and `build_report_for_case(case)`
  returns a report that validates against `report_schema_v0.json` for all nine.

- [ ] **AC4: No retired path was regenerated on the way out.** For each of the
  eleven paths, the most recent commit in `git log --follow`'s history for that
  path is a deletion (`--diff-filter=D`); no add/modify commit for it exists
  after the branch point. (Skips cleanly only when `git` is unavailable to the
  runner; AC1/AC2 still hold in that environment.)

- [ ] **AC5: Replacement (i) — the determinism assertions survive and are
  golden-free.** Each of the six determinism tests named in the Description
  exists, passes, and its source contains none of `GOLDEN_DIR`, `load_golden`,
  `read_golden_text`, `check_case_golden`.

- [ ] **AC6: Replacement (ii) — schema validity reads fresh output.**
  `test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates`
  validates `build_report_for_case(case)` against `report_schema_v0.json` for
  every manifest case and reads no file under `tests/corpus/golden`.

- [ ] **AC7: Replacement (iii) — verdict+findings is pinned against fresh
  output.** For every manifest case, the freshly built report's `verdict` and
  its findings summary (`rule_id`, `severity`, sorted `labels`, and `reason`
  except for the face-name-sensitive case) equal
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`'s entry — asserted by the re-pointed
  `test_098_stray_components.py::test_ac15_golden_verdict_and_findings_unchanged`.
  The constant itself is unchanged and still importable by `test_102`.

- [ ] **AC8: Replacement (iv) — one shared format fixture, two consumers.**
  `tests/golden/report_format_contract.json` exists and is the sole committed
  file both `test_016_features_json.py::test_ac5_golden_snapshot` and
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` compare their
  `serialize_report_json` output against.

- [ ] **AC9: The format fixture is feature-value-free.** Every value in the
  report it pins comes from the hand-written literals in
  `tests/report_format_fixture.py`; the fixture's text is reproduced by that
  module alone, with no import of `segfacet.features`, `segfacet.pipeline`,
  `segfacet.synth` or any extractor, and no NIfTI fixture read.

- [ ] **AC10: The format guarantees are asserted explicitly, not only by text
  equality.** A test asserts, against freshly serialised output, the report's
  top-level key order, its exact key set, and the rendering of the fixture's
  float values (integral, long-decimal, negative and exponent-form), so a
  failure names which of the three moved.

- [ ] **AC11: The write-and-skip defect is not inherited.** With the format
  fixture's path monkeypatched to a nonexistent file, each of the two consuming
  tests raises, does not `pytest.skip`, does not pass, and its message names the
  missing filename; neither function's source contains `pytest.skip` or a write
  call. (Item 111 fixed this on the retired `022` snapshot — AC5 there; the
  replacement must arrive already holding that property.)

- [ ] **AC12: Every discharged fence is deleted, not left vacuous.** None of the
  fourteen fence functions listed in Testing Strategy's disposition table under
  *delete* is defined anywhere in `tests/`, and no test function in `tests/`
  iterates a glob of the retired directory.

- [ ] **AC13: Every re-pointed consumer survives golden-free.** Each of the
  functions listed under *re-point* is still defined in its module, and its
  source contains none of `GOLDEN_DIR`, `load_golden`, `read_golden_text`,
  `check_case_golden`, `tests/corpus/golden`.

- [ ] **AC14: `write_goldens` cannot default to the retired location.**
  `write_goldens()` called with no destination raises `TypeError`; called with
  an explicit directory it still writes one canonical-JSON file per manifest
  case.

- [ ] **AC15: The one-command update path cannot recreate the snapshots.**
  `segfacet.synth.golden.main([])` exits non-zero (argparse's missing-required
  exit) and creates no `tests/corpus/golden` directory; `main(["--out", tmp])`
  still returns 0 and writes nine files.

- [ ] **AC16: The retired location is no longer a public constant.**
  `GOLDEN_DIR` and `GOLDEN_DIRNAME` are absent from
  `segfacet.synth.golden.__all__`, from `segfacet.synth.__all__`, and from both
  modules' namespaces.

- [ ] **AC17: No live reference to a retired path remains.** The literal
  `tests/corpus/golden` appears under `src/`, `tests/` and in `.gitattributes`
  only in the allowlisted places — `tests/test_116_ras_native_corpus.py` (which
  reads the snapshots out of git history at a merge-base commit, not from the
  tree) and this item's own test module — and the same holds for
  `tests/golden/016_features_report.json` and `022_stage3_report.json`. The
  allowlist check is proved reachable by a synthetic offending string.

- [ ] **AC18: The signed rows are untouched.** All eleven Section-1 rows still
  read `retire` in `disposition`, their `what it asserts today`, `evidence` and
  `replacement guarantee` cells are byte-unchanged from the pre-item document,
  and no cell of any Section-1 or Section-2 row contains a retirement-execution
  note.

- [ ] **AC19: Execution is recorded as a dated per-row log.**
  `golden-decision-table.md` carries a final `## Retirement execution log`
  section, placed after `## Divergences from the roadmap's working assumption`,
  holding exactly one line per retired fixture path — each naming the path, the
  date `2026-08-30` and `item 126` — and the set of paths logged equals exactly
  the set of Section-1 rows whose fixture is absent from disk (both directions).

- [ ] **AC20: `test_105`'s inventory check is reconciled.** Its on-disk fixture
  count constant equals the post-retirement inventory (**20**: the 30 surveyed
  on 2026-08-30, minus 11, plus the new format fixture), every on-disk fixture
  has exactly one Section-1 row, no Section-1 fixture path is duplicated, and a
  Section-1 row whose path is absent is accepted only when AC19's log names it.

- [ ] **AC21: The new fixture is documented like every other.**
  `tests/golden/report_format_contract.json` has exactly one Section-1 row with
  disposition `keep` and `—` in the replacement cell, and is named in the
  Divergences section (so `test_105`'s AC5 and AC13 both hold).

- [ ] **AC22: The evidence cells are measured from fresh output.**
  `test_105_golden_decision_table.py::test_ac7_golden_row_evidence_is_measured_not_transcribed`
  derives each row's leaf-path fraction from `build_report_for_case(case)`
  rather than from a committed file, and the nine documented `26/94` values
  still verify unchanged.

- [ ] **AC23: `.gitattributes` is reconciled.** It no longer carries a
  `tests/corpus/golden/*.json` pin, still carries `tests/golden/*.json text
  eol=lf`, and `git check-attr text eol -- tests/golden/report_format_contract.json`
  reports `eol: lf`.

- [ ] **AC24: `test_111`'s hand-surveyed family list matches the tree.**
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` no longer names
  `tests/corpus/golden/*.json`, every family it does name has an `eol=lf` pin in
  `.gitattributes`, and every family names a path pattern that matches at least
  one file on disk.

## Assumptions

Clarify mode is `assume` (`aide.toml`), so each ambiguity below was resolved to
the most defensible default and recorded here for audit rather than blocking.

- **The replacement format fixture gets a `keep` Section-1 row without a new
  maintainer signature (AC21).** `test_105`'s AC3 requires every non-`.py` file
  under `tests/` to have exactly one row, so the fixture cannot exist
  undocumented. Assigning it `keep` is read as bookkeeping rather than new
  judgement: the maintainer's signed replacement text for both retired rows
  *mandates* this fixture ("report-format guarantees move to a small,
  hand-constructed, feature-value-free fixture"), so the row records a decision
  already taken. Contrast the row added by human decision on 2026-08-28
  (`119_pre_119_digests.json`), which introduced a fixture the signed text did
  not call for. If the maintainer disagrees, overturning the row is a one-line
  edit and nothing else in this item depends on it.

- **Execution is logged in a new final section, not in the rows.** The table's
  six columns are pinned exactly by `test_105`'s AC2/AC9, so a seventh
  "executed" column is not available, and writing into an existing cell would
  edit signed text. A `## Retirement execution log` section placed *after*
  `## Divergences…` keeps every mandated heading in order (AC1 there) and leaves
  the Divergences body — which AC13 there parses — exactly as it is.

- **`test_105`'s completeness check is relaxed in one direction only.** After
  this item, "documented ⊇ on-disk" still holds exactly; "on-disk ⊇ documented"
  is relaxed *only* for rows the execution log names. A row naming a
  nonexistent file with no log line still fails, so the table cannot quietly
  accumulate ghosts.

- **`GOLDEN_DIR`/`GOLDEN_DIRNAME` are removed rather than left pointing at a
  path that no longer exists (AC16).** Every one of the module's functions
  already takes an explicit directory, every surviving call site passes one, and
  a public constant naming the retired store is an invitation to resurrect it.
  No test pins `segfacet.synth.__all__`, so the removal breaks nothing outside
  the consumer modules this item already edits.

- **The harness itself is kept, not retired.** `build_report_for_case`,
  `canonical_json`, `write_goldens`, `check_case_golden` and `reports_close`
  remain: they are what the surviving determinism, schema-validity and
  fresh-output replacements are built on. Only the committed store and the
  defaults pointing at it go.

- **`tests/test_116_ras_native_corpus.py` is left untouched.** Its AC7
  case-identity fence reads the snapshots via `git show <merge-base>:…`, so it
  is unaffected by a working-tree deletion and still passes on this branch.
  Once the retirement reaches `main` and the merge base advances past it,
  `_merge_base_sha()` will find no candidate and the fence will degrade to a
  skip. That is a real future decay, but it is not caused by an edit this item
  makes and fixing it needs a decision (pin a historical commit, or delete the
  fence) that belongs with whoever owns Stage 20's baseline; captured in
  `insights.md`.

- **The `022_stage3_report.json` row's "logged, unfixed defect" clause is
  stale.** Item 111 fixed the write-and-skip behaviour on 2026-08-14 —
  `test_111_golden_guard.py::test_ac5_no_self_healing_branch_in_test_ac8`
  enforces it. The signed cell cannot be corrected in place, so AC11 carries the
  requirement forward on the replacement and the execution log records the
  correction; also captured in `insights.md`.

- **Dependency interfaces pinned as they stand on `aide/queue-018` at
  2026-08-30**: `serialize_report`/`serialize_report_json` validate against
  `report_schema_v0.json` (so the hand-built block must be schema-valid: a
  `features` object requires `features_version`, `per_label`, `overlaps`,
  `relationships`, with `stage3` optional and `additionalProperties: false`);
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` derives its two threshold clauses from
  the live `_DEFAULT_MAX_OFFSET_MM` (item 123's `13.0`); the nine documented
  evidence fractions read `26/94`. If any diverged before this item lands, hand
  back rather than adjusting a signed cell.

## Implementation Steps

The work splits cleanly by scope. The **test-writer** owns everything under
`tests/` (the new module, the shared fixture builder, the committed fixture, and
the re-pointing/deletion of the ~40 consumer functions). The **builder** owns
`src/`, `.gitattributes`, the decision table, and the deletion of the eleven
files. Land the consumer re-pointing *before* the deletion so no intermediate
commit has a red suite for a reason unrelated to the item.

1. **Build the shared format fixture.** Add `tests/report_format_fixture.py`
   exposing `format_contract_inputs()` (a hand-written verdict, `case_id`,
   config and features block — literals only, schema-valid, carrying a `stage3`
   sub-block so one fixture covers both consumers' surface) and
   `format_contract_text()` returning `serialize_report_json(...)` for them.
   Choose float literals that exercise rendering: an integral `1.0`, a
   long-decimal `106.98418277680141`, a negative `-2.5`, a near-zero
   `1e-12`. Give the module a `if __name__ == "__main__":` regeneration entry
   point that writes the fixture with `write_bytes` (LF, never from a test).
   Generate `tests/golden/report_format_contract.json` with it and commit it.
2. **Re-point `test_016` and `test_022`.** Both snapshot tests compare
   `format_contract_text()` against the shared fixture read through a module-level
   `GOLDEN_PATH` (kept, so `test_111`'s monkeypatching still works); neither
   writes, neither skips. Their computed-feature assertions (016's AC1–AC4,
   AC6–AC8; 022's AC1–AC7, AC9–AC10) are untouched — those are what actually
   cover feature correctness.
3. **Re-point `test_111`** at the new fixture path throughout (AC1–AC3, AC5–AC9
   and the three adversarial cases), and drop `tests/corpus/golden/*.json` from
   `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES`.
4. **Re-point and delete the consumers** exactly as the disposition table in
   Testing Strategy prescribes, module by module, updating each module's
   docstring where it describes a committed golden. Where a re-pointed test
   needs the narrow verdict+findings shape, import
   `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` from `test_098_stray_components` the
   way `test_102` already does — do not copy it, and do not move it (Section 3
   of the decision table pins where it lives).
5. **Harden the harness** (`src/segfacet/synth/golden.py`): make `dest` a
   required parameter of `write_goldens`; make `--out` a required argument of
   `main`; delete `GOLDEN_DIR`/`GOLDEN_DIRNAME` and the `golden_dir=GOLDEN_DIR`
   / `dest=GOLDEN_DIR` defaults, making the directory explicit on
   `golden_path`, `read_golden_text`, `load_golden` and `check_case_golden`;
   rewrite the module docstring so it describes a regeneration harness over a
   caller-supplied directory and records that the committed store was retired by
   this item. Drop both names from `src/segfacet/synth/__init__.py`'s imports
   and `__all__`.
6. **Correct the one prose reference in production code**:
   `src/segfacet/heuristics/mislabel.py`'s calibration note cites
   `tests/corpus/golden/*.json` as the source of its corpus margins — re-word it
   to name the corpus manifest and a freshly built report. Values unchanged.
7. **Delete the eleven files** in a single commit that changes nothing else, so
   `git log` for each path ends in a pure deletion.
8. **Reconcile `.gitattributes`**: remove the `tests/corpus/golden/*.json` pin
   (with a one-line comment recording that item 126 retired the family); leave
   `tests/golden/*.json text eol=lf`, which already covers the new fixture.
9. **Update the decision table**: append the `## Retirement execution log`
   section (one dated line per retired path, naming item 126, plus a short
   preamble stating that the rows above are the signed disposition and this
   section only records its execution — including the correction that item 111
   had already fixed the `022` row's write-and-skip defect); add the Section-1
   `keep` row and Divergences bullet for
   `tests/golden/report_format_contract.json`; reconcile the stale "asserted by"
   cells that name deleted functions, the same mechanical way item 107 did on
   2026-08-12. Write the file with `\n` bytes (its own AC1 in `test_105`).
10. **Write `tests/test_126_golden_retirement.py`** covering AC1–AC24.

## Authorised paths

**May change:**

- `tests/corpus/golden/*.json` — deleted (the nine retired snapshots).
- `tests/golden/016_features_report.json` — deleted.
- `tests/golden/022_stage3_report.json` — deleted.
- `tests/golden/report_format_contract.json` — new: the shared format fixture.
- `tests/report_format_fixture.py` — new: its hand-written builder.
- `tests/test_126_golden_retirement.py` — this item's test module.
- `tests/test_016_features_json.py` — snapshot test re-pointed at the shared
  fixture.
- `tests/test_022_stage3_serialisation.py` — same.
- `tests/test_042_golden_determinism.py` — seven functions re-pointed, two
  deleted, docstring updated.
- `tests/test_089_fov_aware_coverage_border.py` — AC16 re-pointed.
- `tests/test_090_reference_derived_defaults.py` — AC15 re-pointed.
- `tests/test_094_tptbox_image_layer.py` — AC7 re-pointed.
- `tests/test_098_stray_components.py` — three functions re-pointed, one
  deleted; `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` left verbatim.
- `tests/test_105_golden_decision_table.py` — inventory count, both-directions
  check and the evidence derivation reconciled.
- `tests/test_106_stage19_validation.py` — `test_ac22_nine_goldens_match_corpus_case_ids`
  re-pointed at a regeneration.
- `tests/test_108_affine_faces.py` — AC8 re-pointed.
- `tests/test_111_golden_guard.py` — re-pointed at the new fixture; family list
  reconciled.
- `tests/test_119_curve_formulation.py` — two discharged fences deleted.
- `tests/test_120_leave_one_out_offset.py` — two re-pointed, three deleted.
- `tests/test_121_tangent_orientation.py` — two re-pointed, one deleted.
- `tests/test_122_signed_curvature.py` — one re-pointed, two deleted.
- `tests/test_123_recalibrate_and_regenerate.py` — one test and one helper
  re-pointed, three fences deleted.
- `src/segfacet/synth/golden.py` — required destination, required `--out`,
  constants removed, docstring.
- `src/segfacet/synth/__init__.py` — the two re-exports removed.
- `src/segfacet/heuristics/mislabel.py` — one prose citation re-worded; no
  threshold, no behaviour.
- `.gitattributes` — the retired family's pin removed.
- `docs/aide/golden-decision-table.md` — execution log appended, new keep row,
  stale "asserted by" cells reconciled; signed cells untouched.
- `docs/aide/insights.md` — the append every role is allowed to make.

**Asserts against:**

- `tests/corpus/manifest.json` — read by AC3/AC6/AC7 to drive every case; not
  changed.
- `tests/corpus/fixtures/*.nii.gz` — read by AC3 through the loader; not
  changed.
- `src/segfacet/report_schema_v0.json` — the validation contract AC3/AC6 check
  fresh reports against; not changed.
- `tests/test_116_ras_native_corpus.py` — read by AC17's allowlist as the one
  legitimate in-tree reference to a retired path (it reads git history); not
  changed.
- `docs/aide/progress.md` — read by `test_105`'s AC12 (Stage-19 attestation);
  not changed by this item.

**On the cross-spec conflicts `aide check --queue 018` will report.** Items 127
(`test_111`), 129 (`tests/`, `reference_verse_v1.json`), 132 (`tests/`,
`manifest.json`) and 134 (`golden-decision-table.md`, `.gitattributes`,
`test_105`) all declare paths this item also changes. Every one of them is
sequenced *after* this item by queue-018's prioritisation, and each says so in
its own entry; the collisions are ordering, not contradiction. This item lands
first and they build on its post-retirement state.

## Testing Strategy

Test module: **`tests/test_126_golden_retirement.py`**, one focused test per AC.
Where an AC is about another module's source (AC5, AC12, AC13, AC9), read that
module's text or AST rather than importing it, so a failure names the offending
function instead of erroring at import.

**Adversarial / edge cases.**

- The AC19 both-directions check bites in both directions: a synthetic log
  naming a path that still exists fails, and a synthetic Section-1 row naming an
  absent path with no log line fails.
- AC17's allowlist is proved reachable by a synthetic offending string (the
  pattern in `test_105`'s `test_adv_ac11_signoff_line_pattern_is_actually_reachable`
  is the model) — an allowlist that matches nothing is not evidence.
- The format fixture present but **empty** fails with an `AssertionError`, not a
  crash; present with **CRLF** content is well-defined under `read_text`'s
  universal-newline translation (both carried over from `test_111`).
- The format fixture present but **drifted by one key** fails with a message
  naming the drift.
- `write_goldens(tmp)` into an already-populated directory is still idempotent,
  and `main(["--out", tmp])` still returns 0 and writes nine files — the harness
  works, only the committed store is gone.
- A regenerated report and the fixture's hand-built report share no float: an
  assertion that the format fixture's numbers do not appear in any freshly built
  corpus report, so a future edit cannot quietly re-couple the two.

**Existing tests to reconcile** (the full 2026-08-30 sweep; each row is a
stale assumption that will otherwise fail — or, worse, pass vacuously — on the
first validation round).

| module | function | disposition |
|---|---|---|
| test_042 | `test_ac6_exactly_one_golden_per_manifest_case_no_more_no_fewer` | re-point at `write_goldens(tmp_path)` output |
| test_042 | `test_ac7_every_committed_golden_is_valid_json_and_validates` | re-point at `build_report_for_case` (AC6) |
| test_042 | `test_ac8_committed_golden_case_id_matches_filename` | re-point at the regenerated tmp directory |
| test_042 | `test_ac9_fresh_report_matches_committed_golden_within_tolerance` | delete |
| test_042 | `test_ac13_regeneration_reproduces_committed_goldens_within_tolerance` | delete |
| test_042 | `test_ac16_reconstructed_golden_is_pipeline_blind` | re-point at fresh output |
| test_042 | `test_adv_mode5_remove_level_golden_canonicalises_without_crashing_on_empty_labels` | re-point at fresh output |
| test_042 | `test_adv_clean_control_golden_passes_with_no_findings` | re-point at fresh output |
| test_042 | `test_adv_reconstructed_golden_blindness_is_checked_via_rule_ids_not_empty_findings` | re-point at fresh output |
| test_089 | `test_ac16_committed_corpus_coverage_and_border_findings_unchanged` | re-point: fresh vs `_PRE_098_*`, coverage/border subset |
| test_090 | `test_ac15_all_committed_goldens_still_check_true` | re-point: fresh vs `_PRE_098_*` |
| test_094 | `test_ac7_report_matches_committed_golden_within_tolerance` | re-point: fresh vs `_PRE_098_*` (post-migration identity) |
| test_098 | `test_ac14_every_golden_components_block_has_four_new_keys` | re-point at fresh output |
| test_098 | `test_ac14_every_golden_still_validates_against_schema` | re-point at fresh output |
| test_098 | `test_ac15_golden_verdict_and_findings_unchanged` | re-point at fresh output (AC7) |
| test_098 | `test_ac16_write_goldens_matches_committed_within_tolerance` | delete (its determinism sibling survives) |
| test_105 | `test_ac3_current_tree_has_30_non_py_fixtures` | re-point to 20 (AC20) |
| test_105 | `test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions` | reconcile against the execution log (AC20) |
| test_105 | `test_ac7_golden_row_evidence_is_measured_not_transcribed` | re-point at fresh output (AC22) |
| test_106 | `test_ac22_nine_goldens_match_corpus_case_ids` | re-point at a tmp regeneration |
| test_108 | `test_ac8_border_and_coverage_presence_and_labels_unchanged` | re-point: fresh vs `_PRE_098_*` triples |
| test_111 | AC1–AC3, AC5–AC9 and its three adversarial tests | re-point at `report_format_contract.json` |
| test_119 | `test_ac18_every_manifest_case_matches_committed_golden` | delete (discharged fence) |
| test_119 | `test_ac20_diff_against_committed_goldens_stays_under_stage3` | delete (would iterate an empty glob) |
| test_120 | `test_ac17_threshold_margins_hold_on_corpus` | re-point at fresh output (live calibration margin) |
| test_120 | `test_ac23_border_crop_case_gains_mislabel_finding_border_unchanged` | re-point at fresh output |
| test_120 | `test_ac25_every_manifest_case_matches_committed_golden` | delete |
| test_120 | `test_ac26_regeneration_moves_no_verdict_outside_mode1s_own_deliverable` | delete (subsumed by AC7) |
| test_120 | `test_ac26_changes_confined_to_stage3_and_findings_and_verdict` | delete (would iterate an empty glob) |
| test_121 | `test_ac10_principal_axis_within_0996_of_left_right_on_every_golden` | re-point at fresh output (live property) |
| test_121 | `test_ac10_principal_axis_exactly_left_right_on_seven_of_nine_cases` | re-point at fresh output |
| test_121 | `test_ac12_pca_values_match_fresh_computation_within_tolerance` | delete (becomes fresh-vs-fresh) |
| test_122 | `test_ac20_every_corpus_golden_matches_fresh_build` | delete |
| test_122 | `test_ac20_new_curvature_keys_present_in_every_committed_golden` | re-point at fresh output |
| test_122 | `test_ac21_stage3_report_golden_is_present_and_carries_new_keys` | delete (its subject is retired; the sibling covers the keys) |
| test_123 | `test_ac23_every_manifest_case_matches_committed_golden` | delete |
| test_123 | `test_ac25_seven_non_mislabel_goldens_gain_only_is_terminal` | delete (pre/post fence, item 123 landed) |
| test_123 | `test_ac26_two_changed_goldens_move_only_is_terminal_and_the_threshold_clause` | delete (same) |
| test_123 | `test_ac28_pinned_snapshot_reasons_equal_committed_golden_reasons` | re-point at fresh output |
| test_123 | `_interior_offset_ceiling_over_corpus` (helper) | re-point at fresh output |
| test_116 | `_merge_base_sha` / `_merge_base_golden` and their consumers | leave untouched — reads git history, not the tree (see Assumptions) |

Fourteen deletions, twenty-five re-points, one module left alone. Every deletion
is a fence whose reference state is precisely what the maintainer retired, and
whose item has already merged — the same authorised-removal reasoning item 107
recorded on 2026-08-12 for the `_PRE_099_*` byte-hash fences.

## Validation

Beyond the suite, observe the three claims a green run cannot show. Run from the
repo root on the item branch:

1. **Nothing was regenerated.** `git log --oneline --name-status -- tests/corpus/golden tests/golden` — the newest entry for every retired path must be a `D`, with no `A`/`M` after this item's branch point.
2. **The update path cannot resurrect the store.** `.venv/bin/python -m segfacet.synth.golden` (no `--out`) — must exit non-zero, print a usage error, and leave no `tests/corpus/golden` directory (`ls tests/corpus` afterwards).
3. **The replacement fails loudly.** Delete `tests/golden/report_format_contract.json`, run `.venv/bin/python -m pytest tests/test_016_features_json.py tests/test_022_stage3_serialisation.py` — both snapshot tests must FAIL naming the missing file (never skip, never pass) — then `git restore tests/golden/report_format_contract.json` and confirm the suite is green again.

No `[validation]` profile is needed; all three run in the plain project venv.

## Dependencies

None. This item is queue-018's first and depends on nothing unmerged.

**Downstream:** item 127 (its enforced allowlist describes this item's
post-retirement inventory), item 129 (`mode5_remove_level` is a 4-level fixture
whose snapshot would otherwise need regenerating), item 132
(`mode4_relabel_swap`'s `is_monotonic` likewise), item 133 (the dependency bump's
regression surface), item 134 (the companion count artifact describes the
post-retirement rows) and item 135 (the stage validation replays this item's
retirement audit).

## Decisions & Trade-offs

- **The consumer re-pointing and fixture-building work (nominally the
  test-writer's, per Implementation Steps) was done by the builder.** Only
  `tests/test_126_golden_retirement.py` had been committed when this item's
  builder pass started; `tests/report_format_fixture.py`,
  `tests/golden/report_format_contract.json`, and the ~34 consumer
  re-points/14 fence deletions the disposition table names were still
  outstanding. The orchestrator scoped this explicitly to the builder for
  this item (re-pointing/deleting *existing* consumer tests is "the
  implementation of the retirement", not new test authorship), so it was
  done here rather than handed back. No new test was written for item 126 —
  `tests/report_format_fixture.py` is a fixture-builder module (no `test_`
  functions) and `tests/golden/report_format_contract.json` is a data
  fixture, not a test.

- **Five additional consumers beyond the disposition table's 14+25 were
  discharged**: `test_119_curve_formulation.py::test_ac19_stage3_report_golden_matches_test_022_output`,
  `test_120_leave_one_out_offset.py::test_ac27_stage3_report_golden_matches_test_022_output`
  and `::test_ac27_stage3_report_golden_offset_entries_carry_is_terminal`, and
  `test_123_recalibrate_and_regenerate.py`'s identically-named pair. Each
  compared its own real-feature content against `test_022_stage3_serialisation.py`'s
  `GOLDEN_PATH` module attribute, which now names the shared
  `report_format_contract.json` fixture rather than a per-module snapshot —
  content unrelated to any of these five tests' inputs, so they would fail
  regardless of anything else in this item. None used the `GOLDEN_DIR`/
  `load_golden`/`read_golden_text`/`check_case_golden` markers the item's own
  AST sweep searched for, so the sweep never found them — they surfaced only
  because re-pointing `test_022`'s `GOLDEN_PATH` broke their assumption.
  Discharged as duplicates of `test_022`'s own (already re-pointed)
  comparison, the same reasoning the signed disposition table applies to
  every other discharged fence. Logged as a gap in `insights.md`
  (2026-08-31) so a future fixture-retirement sweep also greps for
  shared-attribute idioms, not just the producing module's own markers.

- **`check_case_golden`'s `golden_dir` became a required keyword-only
  argument (not just required-positional).** Every surviving call site
  already passes it as `golden_dir=...`, so this is behaviour-neutral for
  every caller in the tree and makes a future positional-argument mistake
  (passing a directory where `config` is expected) impossible.

- **The consumer re-pointing, the `src/` harness hardening, the eleven-file
  deletion, and the docs reconciliation landed as four separate commits.**
  Per Implementation Step 7's "single commit that changes nothing else" for
  the deletion specifically — `git log --follow` for each of the eleven
  retired paths shows exactly one commit, a pure `D`, with nothing else in
  it.

- **The corpus-golden rows' "asserted by" cells were reconciled to drop the
  two deleted AC9/AC13 references, without naming this item by number inside
  any Section-1 cell.** AC18's row check forbids the item's own citation in
  *any* Section-1 cell (not only the eleven retired rows'), so the
  reconciliation note reads "AC6-AC8 now compare fresh/regenerated output;
  the fresh-vs-committed AC9/AC13 pair was retired" rather than attributing
  the change to this item by number. The four AC18-protected cells (`what it
  asserts today` / `evidence` / `disposition` / `replacement guarantee`) for
  all eleven retired rows are verified byte-unchanged against their pre-item
  sha256 digests. A full "asserted by" reconciliation across the ~12
  consumer modules the item's own AST sweep found (versus the 6 the table
  names) was judged out of scope for this item — no AC requires it, and it
  is already logged as a gap in `insights.md` (2026-08-30).

- **`src/segfacet/heuristics/mislabel.py`'s prose citation was re-worded, as
  Implementation Step 6 and the Authorised-paths list both name.** The diff
  is prose-only (re-cites the corpus manifest plus a freshly built report
  instead of the retired corpus-golden snapshots); no threshold, margin
  value, or rule behaviour changed.
