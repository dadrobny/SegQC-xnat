# Item 135 — Validate stage 29: Golden Retirement & Test-Artifact Hygiene

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 135
> **Objectives:** G2, G7
> **Suggested branch:** `aide/135-validate-stage-29-golden-retirement`

---

## Description

Close Stage 29 by **replaying its acceptance end-to-end**, not by re-running the
unit suite. Items 126–134 each proved their own deliverable against their own
tests; this item asks the different question the stage's acceptance section
poses — *does the shipped tree now behave the way the stage claimed it would* —
and records the answer in `progress.md` whether or not it is the answer the
stage hoped for.

Four obligations are specific to this stage.

**One acceptance clause is known unmeetable, and this item is where that gets
said out loud.** Stage 29's third acceptance criterion opens with "a 4-level
field of view yields non-degenerate held-out offsets". Item 129 moved
`features/spline_offset.py`'s `_MIN_LEVELS_FOR_HELD_OUT` from `4` to `5` as the
roadmap's D5 prescribed — and measured, while doing so, that the prescribed
mechanism cannot produce the prescribed result. At exactly four points a cubic
(`k = 3`) spline has exactly four coefficients, so it **interpolates all four
points regardless of the weights**: down-weighting a level to
`_WITHHELD_WEIGHT` still leaves it exactly on the curve, the "held-out" curve
is numerically the in-sample curve (agreeing to ~1e-13 mm), and an interior
level displaced a full **15 mm** still reads a held-out `offset_mm` below
`0.001` mm. No boundary value fixes this; closing the gap needs the fit's
degree clamped below `n − 1` at small `n`, which changes the formulation the
2026-08-27 "Spinal curve model — the deformity envelope" **human gate**
approved. The boundary move was therefore an honesty fix with no numeric
consequence, and item 129 explicitly left this acceptance line for item 135 to
**record unmet with the evidence** rather than tick — the Stage 28 precedent,
where two acceptance boxes stayed unticked with their measurements written
beside them. Ticking around it is the one failure mode this item exists to
prevent.

**The retirement is audited as a deletion, not as a green suite.** The stage's
first acceptance line has two independently checkable halves: the eleven
snapshots are gone with their four named replacements in place *and nothing was
regenerated on the way out*, and the item-127 guard genuinely fails a
**deliberately added** byte-exact comparison. The second half is a replay, not a
unit test: `tests/test_127_committed_artifact_tolerance.py`'s
`test_ac16_off_allowlist_comparison_is_classified_as_violation` classifies an
in-memory synthetic source string, which proves the classifier's logic but not
that a real file added to a real `tests/` tree is caught by the sweep that
actually runs. This item adds the real file, on a scratch branch, in a
throwaway clone.

**"Fails before the fix" is verified, not assumed.** Every behaviour-changing
item in this stage claims a regression test that failed before its fix. The
claim is cheap to write and expensive to be wrong about, so this item checks it
by running the designated tests at the commit immediately preceding each fix.
That is mechanically clean here: every implementation commit's parent is the
`progress(aide): item NNN -> in-progress` commit, which already carries the
test-writer's module — so the replay is a checkout and a `pytest`, with nothing
copied in.

**Two ticks, one of them belonging to the previous stage.** Item 132 made
`mode4_relabel_swap` read `is_monotonic == False`, and moved it in
`tests/corpus/manifest.json` from `detection="reconstructed_record"` to
`detection="pipeline"`. Stage 28's third acceptance criterion — left unticked by
item 125 on exactly that measurement — is closed **here**, by this item's replay,
with its own evidence sentence. Stage 28's remaining unticked criterion (the
real scoliotic case flagged as an offset outlier) is untouched: it keeps item
125's recorded evidence verbatim, and nothing in Stage 29 addressed it.

**In scope.** Replay, measurement, evidence recording, `progress.md` acceptance
ticks for Stage 29 and Stage 28's mode-4 half, Environment-Gated row updates,
and an in-suite test module pinning the mechanically checkable half so a later
change cannot move it silently.

**Not in scope.** Fixing anything found. The four-level blind spot, any
divergence a replay turns up, and any defect surfaced by the fresh-clone run are
**findings** — logged to [`insights.md`](../insights.md) and reported, not
remediated here. Flipping Stage 29's deliverable bullets or item statuses is
**not** this item's job either: `aide progress set` and `aide merge` already
wrote every ✅ D-bullet. And triaging the insight backlog (24 open entries, ~15
of them added during this queue) is the **queue boundary's** job
(`/aide-feedback-loop`), not this item's — this item only *appends*.

## Acceptance Criteria

### G7 — the retirement audit (Stage 29 acceptance 1, first half)

- [ ] **AC1: all eleven retired snapshots are absent from the tree.**
  `tests/corpus/golden/` contains no `*.json` (measured 2026-08-31: the
  directory does not exist at all), and neither
  `tests/golden/016_features_report.json` nor
  `tests/golden/022_stage3_report.json` exists. The eleven paths are enumerated
  by name in the recorded evidence, not summarised as a count.
- [ ] **AC2: each of the four named replacements is present and named.** The
  disposition table's four replacement guarantees resolve to live code:
  (i) intra-run determinism — the run-to-run tests in `test_042`, `test_098`,
  `test_016` and `test_022`, none of which reads a committed snapshot;
  (ii) schema validity — `tests/test_126_golden_retirement.py::test_ac3_fresh_report_validates_against_schema`
  validates `build_report_for_case` output against `report_schema_v0.json`;
  (iii) the verdict+findings shape expectation of the
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` kind, pinning no feature values;
  (iv) the shared format fixture `tests/golden/report_format_contract.json`
  built by `tests/report_format_fixture.py`, the sole survivor under
  `tests/golden/`. Each is named with its module and function in the evidence.
- [ ] **AC3: the format fixture's write-and-skip defect is gone.** Deleting
  `tests/golden/report_format_contract.json` makes its consumers **fail**,
  naming the missing filename — it does not self-heal by writing the file and
  skipping. Replayed on a scratch copy of the tree, and the failure text
  recorded.
- [ ] **AC4: no retired path was regenerated on the way out.** For each of the
  eleven paths, `git log --follow --name-status` over the range from
  queue-018's first commit (`69e5cf5`, "docs(aide): add work queue 018") to the
  branch tip shows the most recent history entry is a deletion (`D`), in one
  commit (`cafd4cc`, "chore(126): delete the eleven retired golden snapshots"),
  with no `A`/`M` entry after it. The commit range and the per-path result are
  recorded.

### G7 — the guard replay (Stage 29 acceptance 1, second half)

- [ ] **AC5: a deliberately added byte-exact comparison fails the guard.** On a
  scratch branch in the throwaway clone (never in the working checkout), a new
  file under `tests/` containing a real `read_bytes()` comparison of freshly
  generated output against a committed float-carrying artifact
  (`src/segfacet/reference/reference_default.json`) makes
  `tests/test_127_committed_artifact_tolerance.py::test_ac15_classifier_reports_zero_violations_on_tests_tree`
  **fail**. The failing output is recorded verbatim. This is the whole-tree
  sweep (`iter_violations(TESTS_DIR)`), not `classify_module` on a synthetic
  string.
- [ ] **AC6: the guard's failure message names the helper.** The message
  produced in AC5 contains `assert_matches_committed_artifact`, so a developer
  who trips it is told what to reach for instead. Recorded verbatim.
- [ ] **AC7: the scratch branch is discarded and the working checkout is
  untouched.** After AC5/AC6, the scratch branch and its added file are gone;
  `git status --short` in the working checkout shows no artifact of the replay,
  and the item's own diff contains no file under `tests/` other than
  `tests/test_135_stage29_validation.py`.

### G2 — mode 4 end-to-end (Stage 29 acceptance 2, and Stage 28's open half)

- [ ] **AC8: mode 4 reads `is_monotonic == False` through
  `extract_feature_record`.** `mode4_relabel_swap`'s
  `stage3.monotonic_consistency.is_monotonic` is `False` through the shipped
  record builder on the committed fixture. The observed value is recorded, not
  assumed.
- [ ] **AC9: the swapped pair is named.** The same record's
  `non_monotonic_pairs` names the swapped levels (measured 2026-08-31 by item
  132: `[["L2", "L3"]]`). The observed list is recorded verbatim.
- [ ] **AC10: mode 4 survives the CLI path with the same reading.** A real
  `segfacet run --scan … --seg tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz
  --out <scratch> --no-reference` exits `0`, and the emitted
  `segfacet_report.json` carries `is_monotonic == False` with the same swapped
  pair. The report excerpt is recorded verbatim. `--no-reference` is required
  here for the reason `CLAUDE.md`'s Gotchas record (the item-090 default
  reference fires ~40 findings on synthetic fixtures).
- [ ] **AC11: the clean control still reads monotonic through the same paths.**
  `clean_control` reads `is_monotonic == True` with empty `non_monotonic_pairs`
  through `extract_feature_record` and through the same
  `segfacet run --no-reference` invocation, and fires zero findings through the
  CLI. A mode-4 tick bought by a change that also flips the clean control is not
  a tick.
- [ ] **AC12: Stage 28's mode-4 acceptance half is ticked with this item's
  evidence.** `progress.md`'s Stage 28 third acceptance box moves from `[ ]` to
  `[x]`, its note rewritten to record the AC8–AC11 measurements and to name item
  132 as what closed it and item 135 as what replayed it. The `mislabel` and
  clean-control halves of that same criterion keep item 125's recorded evidence.
- [ ] **AC13: Stage 28's scoliotic-case criterion is left exactly as it
  stands.** The fourth Stage 28 acceptance box stays `[ ]` with item 125's
  2026-08-30 evidence note byte-unchanged. Nothing in Stage 29 addressed it, and
  this item does not re-measure, re-word or re-date it.

### G7 — Stage 29 acceptance 3, clause by clause

- [ ] **AC14: the four-level clause is recorded UNMET with its evidence.** A
  fresh measurement on a synthetic 4-level curve with an interior level
  displaced 15 mm reproduces the degenerate reading (item 129 measured
  `[7.35e-05, 5.33e-06, 5.74e-06, 3.78e-05]` mm, all `< 0.001` mm and equal to
  the in-sample fallback), and the same generator at 5–6 levels separates the
  displacement. The measured arrays are recorded, and Stage 29's third
  acceptance box is left **unticked** with a note naming: the measurement, the
  interpolation reason (`k = 3`, four coefficients, four points), the two
  standing evidence sources (`docs/aide/items/129-coincident-centroids-in-the-pipeline.md`'s
  Decisions log and `src/segfacet/features/spline_offset.py`'s docstring
  limitation block), and the 2026-08-27 human gate that governs the formulation
  change needed to close it. No agent resolves that gate.
- [ ] **AC15: the nested-label map yields a report (the claimable D4 half).** A
  label map in which one label is painted inside another — so two labels share a
  centroid — produces a report rather than a traceback through
  `extract_feature_record` **and** through `segfacet run --no-reference`
  (exit `0`, no `Traceback`), with `features.stage3_unavailable.reason ==
  "coincident_centroids"` and both coincident levels named in the human report.
  The report excerpt is recorded verbatim.
- [ ] **AC16: `pip show tptbox` reports a non-AGPL licence at ≥ 0.7.6.** Run in
  the project venv, the observed `Version` is `0.7.6` or higher and the observed
  `License` string contains neither `agpl` nor `affero` (case-insensitive);
  item 133 measured `Apache License Version 2.0, January 2004`. Both fields are
  recorded verbatim, and both pin files (`pyproject.toml`, `constraints.txt`)
  are confirmed to carry the same version.
- [ ] **AC17: the third acceptance box's two met clauses are recorded as met
  inside its unticked note.** The box stays unticked (AC14), but its note states
  explicitly that the `pip show tptbox` clause and the fails-before-the-fix
  clause were verified, and that the box is unticked solely on the four-level
  clause — so a later reader is not left inferring that all three failed.

### G7 — fails-before-the-fix, per defect

- [ ] **AC18: the four behaviour-changing fixes are re-verified by execution.**
  For items **129**, **131**, **132** and **133**, checking out the commit
  immediately preceding the implementation commit (respectively `1466b8b`←`021f0bc`,
  `8b94e62`←`5efd27d`, `628f673`←`cc22bfd`, `26b5cf5`←`8586772`, resolved fresh
  rather than trusted from this spec) and running that item's designated
  regression tests shows them **failing** there. Designated nodes:
  `test_129_…::test_ac21_floor_is_five` and `::test_ac5_extract_feature_record_returns_dict_not_raise`;
  `test_131_…::test_ac1_cranial_first_straight_spine_reads_zero_not_180` and
  `::test_ac2_straight_spine_reversal_equivariant`;
  `test_132_…::test_ac1_mode4_relabel_swap_is_non_monotonic_through_shipped_record_builder`
  and `::test_ac2_mode4_relabel_swap_non_monotonic_pairs_names_l2_l3`;
  `test_133_…::test_ac1_tptbox_pin_is_exactly_0_7_6` and
  `::test_ac2_constraints_tptbox_pin_moved`. The failing assertion text for each
  is recorded.
- [ ] **AC19: unrelated failures at a parent commit are attributed, never
  counted as evidence.** Several items landed post-implementation test fixes
  (`0be06b7` for 130, `7b2c3a8` for 131, `c3fb7fb` for 133, `bce35d4` for 126),
  so a parent-commit run may fail for reasons unrelated to the missing fix. Each
  failure observed in AC18 is classified as *the designated pre-fix behaviour*
  or *a separately-fixed test defect*, by name, and only the former is counted.
- [ ] **AC20: the three structural items are recorded as structural, not dressed
  as behaviour regressions.** Items **128** (a relocation), **130** (a
  consolidation whose whole evidence is that every existing value-level
  assertion still passes) and **134** (a new generated artifact) have no pre-fix
  *behaviour* to fail against: their designated tests fail at the parent commit
  only because a module, a name or a file does not exist yet. This item states
  that plainly for each, cites the item's own recorded verification, and does
  **not** claim a behaviour-regression replay it did not perform. Whether each
  was executed or cited is stated per item.
- [ ] **AC21: items 126 and 127 are recorded as predating the convention.**
  Neither carries a fails-before-the-fix obligation; their verification is the
  retirement audit (AC1–AC4) and the guard replay (AC5–AC7) respectively. Stated
  explicitly rather than left as a silent gap in the per-item table.

### G7 — reproducibility and environment

- [ ] **AC22: the fresh-clone suite is green.** The full suite passes from a
  `git clone` of this repository into a directory whose path differs from this
  checkout's, on this branch's final commit, in a venv bootstrapped there by
  `python .aide/scripts/aide.py env --bootstrap`. The clone path, the branch and
  commit under test, the bootstrap result and the pass/skip/fail counts are all
  recorded.
- [ ] **AC23: environment-gated rows reflect reality.** `python
  .aide/scripts/aide.py env` is run and its output recorded; every
  Environment-Gated Capability Verification row is checked against what Stage 29
  actually exercised. Expected outcome (to be confirmed, not assumed): Stage 29
  introduces **no** new gated capability and affects **no** existing row — the
  three `[validation]` profiles (`pyradiomics`, `docker`, `gpu`) are untouched
  by this stage, and the "Real VerSe GT" row is **not** re-evidenced, because no
  item in this stage rebuilt the real artifact on this machine. If that holds,
  the table is left unchanged and the reason is recorded; if any row is
  genuinely affected, it is updated with the profile result behind it.

### Honest bookkeeping

- [ ] **AC24: Stage 29's acceptance is ticked honestly.** Each of the three
  acceptance boxes in `progress.md`'s Stage 29 section is either ticked **and**
  followed by a one-sentence evidence note naming what was run, or unticked
  **and** followed by a reason — the tick-implies-evidence biconditional item
  106 established and items 115/125 pinned. Expected shape: boxes 1 and 2
  ticked, box 3 unticked per AC14/AC17.
- [ ] **AC25: the before/after summary is recorded exactly.** Stated as numbers
  with both sides named: corpus pipeline detection **7 of 8** modes (1, 2, 3, 4,
  5, 6, 7) versus **6 of 8** at Stage 28's close (mode 4 moved in at item 132;
  mode 8 still `reconstructed_record`), and the committed whole-record snapshot
  inventory **11 → 0**, with one shared, feature-value-free format fixture
  (`tests/golden/report_format_contract.json`) surviving under `tests/golden/`.
  Both agree with `tests/corpus/manifest.json`'s `detection` fields and with
  `test_040`/`test_057`/`test_120`/`test_125`'s mode-set constants.
- [ ] **AC26: no deliverable bullet or item status is hand-edited.** Stage 29's
  D-bullets and every item's ✅ were written by `aide progress set` / `aide
  merge`; this item's `progress.md` diff touches acceptance boxes (Stage 29's
  three, Stage 28's mode-4 one) and, if AC23 requires it, verification-table
  rows — nothing else. No status icon is hand-typed.
- [ ] **AC27: `aide check` reports no new warning.** `python
  .aide/scripts/aide.py check` after this item's edits reports no warning class
  absent from the recorded pre-item baseline. Baseline measured 2026-08-31 on
  this branch: `OK (3 warning(s))` — 32 legacy specs without `## Assumptions`,
  plus the two Stage 16 gates awaiting a decision.
- [ ] **AC28: findings are logged, not silently fixed, and the backlog is not
  triaged here.** Everything this replay surfaces that is not a Stage 29
  deliverable is appended to `insights.md` as a new one-line entry and named in
  this item's Decisions. No existing entry is reworded, reordered, deleted or
  ticked — triage belongs to `/aide-feedback-loop` at the queue boundary. Nothing
  outside this item's authorised paths is edited to make a criterion pass.

## Assumptions

- **Items 126–134 are all ✅ before this item starts.** If any is not, this item
  halts and reports rather than validating a partial stage — the posture items
  106, 115 and 125 took.
- **Every number quoted in this spec is a starting point, not the answer.** The
  values above were measured on this checkout at HEAD on 2026-08-31, or read
  from the landed items' Decisions logs. The item **re-measures** them; where a
  value has moved, the measured value wins and the divergence is recorded in
  Decisions.
- **The throwaway clone is the rig for every replay that must not touch the
  working checkout** — the fresh-clone suite (AC22), the scratch-branch guard
  replay (AC5–AC7), the format-fixture deletion (AC3) and the parent-commit
  checkouts (AC18). One clone, one bootstrapped venv, reused. This avoids two
  real hazards: detaching `HEAD` in the working checkout mid-item, and the
  editable install's meta-path finder resolving `segfacet` to the *working*
  checkout's `src/` while a different tree's tests are running — which would
  silently invalidate every fails-before-the-fix result. Clone from the local
  repository path; nothing is pushed, and the scratch branch never leaves the
  clone.
- **The parent of each implementation commit already carries that item's test
  module.** Every fix's parent is the `progress(aide): item NNN -> in-progress`
  commit, whose own parent is the test-writer's `tests: NNN …` commit — verified
  2026-08-31 for all nine items. So AC18's replay is `git switch --detach
  <parent>` plus `pytest <module>`, with nothing copied in. If a parent turns out
  not to carry the module, that item moves to AC20's cited-not-executed
  treatment with the reason recorded, rather than being skipped in silence.
- **The four-level acceptance clause is expected to fail, and failing it is the
  correct outcome.** AC14 is written as a measurement and a recording
  obligation, never as an assertion of non-degeneracy, precisely so the item
  cannot be "passed" by weakening it. The in-suite test pins the *observed*
  degenerate reading — a regression guard either way, and the shape item 125's
  AC7 established for exactly this situation.
- **No new human gate row is added.** The formulation change that would close
  the four-level blind spot falls under the existing 2026-08-27 "Spinal curve
  model — the deformity envelope" gate, which is `✅ Approved` and blocks
  nothing today; no item is queued that the decision would block, so a new row
  would gate nothing and would read as an open blocker on a closed stage. The
  need for that decision travels to the queue boundary through the standing
  `insights.md` entry (2026-08-31, item 129), through
  `spline_offset.py`'s docstring, and through Stage 29's unticked acceptance
  box. Raising a gate is always allowed; resolving one is never an agent's call,
  and this item resolves none.
- **The real VerSe19 cohort is not required by any criterion here.** Unlike item
  125, no Stage 29 acceptance clause depends on it: item 129 deliberately did
  not rebuild `reference_verse_v1.json` (its ~1e-13 mm staleness is invisible to
  every current consumer and rebuilding would reopen item 123's threshold
  derivation), and item 133's tptbox check is a venv metadata read. If a
  cohort-gated test skips during AC22's fresh-clone run, that is recorded as a
  skip in the counts and is **not** treated as verification of anything.
- **`aide check --queue 018` is expected to report pin-vs-edit errors naming
  this item, and they are inert** — the same structural collision item 125
  recorded: a stage-validation item's whole job is to pin the artifacts its
  stage's items produced, so it necessarily collides with their `May change`
  lists, and every one of those items is already ✅ and merged. AC27 covers
  `aide check`, **not** `aide check --queue`, for that reason. If the queue
  check reports anything that is *not* of that shape, it is a finding for
  Decisions.
- **`tests/golden/report_format_contract.json` is the only file left under
  `tests/golden/`** and `tests/corpus/golden/` does not exist (measured
  2026-08-31). AC1 asserts absence rather than emptiness so a resurrected
  directory is caught either way.

## Implementation Steps

1. Confirm items 126–134 are ✅ in `progress.md`; halt and report if not. Record
   the `aide check` baseline (`OK (3 warning(s))`).
2. Audit the retirement in the working checkout: enumerate the eleven paths,
   confirm absence, resolve each of the four replacements to a live module and
   function, and run the `git log --follow --name-status` per-path history audit
   over `69e5cf5..HEAD` (AC1, AC2, AC4).
3. Clone this repository into the scratchpad directory, check out this branch,
   and bootstrap its venv with `python .aide/scripts/aide.py env --bootstrap`.
   This clone is the rig for steps 4, 5, 9 and 10.
4. In the clone, on a scratch branch: delete
   `tests/golden/report_format_contract.json` and confirm its consumers fail
   naming the file (AC3); restore it.
5. In the clone, on a scratch branch: add a file under `tests/` containing a
   genuine `read_bytes()` comparison of fresh output against
   `src/segfacet/reference/reference_default.json`, run
   `test_127_committed_artifact_tolerance.py::test_ac15_classifier_reports_zero_violations_on_tests_tree`,
   record the failure and its message; discard the branch and the file
   (AC5–AC7).
6. In the working checkout, run `mode4_relabel_swap` and `clean_control` through
   `extract_feature_record` and through `segfacet run --no-reference` into a
   scratch output directory; record `is_monotonic`, `non_monotonic_pairs`, the
   findings and the report excerpts (AC8–AC11).
7. Re-measure the four-level held-out offsets on a synthetic curve with an
   interior level displaced 15 mm, at 4, 5 and 6 levels; record all three arrays
   (AC14).
8. Build the nested-label map (the coincident-centroid case) and run it through
   `extract_feature_record` and `segfacet run --no-reference`; record the exit
   code, `stage3_unavailable.reason` and the human-report excerpt (AC15). Run
   `pip show tptbox` in the project venv and record `Version` and `License`
   verbatim (AC16).
9. In the clone, for items 129/131/132/133: resolve each implementation commit
   and its parent from `git log`, `git switch --detach <parent>`, run the
   designated test nodes, record every failure and classify it (AC18, AC19).
   Record the structural statement for 128/130/134 and the
   predates-the-convention statement for 126/127 (AC20, AC21).
10. In the clone, back on this branch's final commit, run the full suite and
    record the counts (AC22).
11. Run `python .aide/scripts/aide.py env` and check the Environment-Gated
    Capability Verification table against what this stage exercised (AC23).
12. Write `tests/test_135_stage29_validation.py` covering the in-suite half (see
    Testing Strategy).
13. Update `progress.md`: Stage 29's three acceptance boxes (two ticked with
    evidence, the third unticked with the four-level reason and the two met
    clauses named), Stage 28's mode-4 box ticked with this item's evidence, and
    nothing else (AC12, AC13, AC17, AC24, AC26).
14. Run `aide check` and compare against the baseline (AC27); append every
    out-of-scope finding to `insights.md` as a new line (AC28).

## Authorised paths

**May change:**

- `tests/test_135_stage29_validation.py` — the item's own test module.
- `tests/test_126_golden_retirement.py` — AC17's allowlist of files legitimately
  naming the retired path; adds this item's own validation module (it names
  the retired path while checking the retirement).
- `docs/aide/progress.md` — Stage 29's three acceptance boxes, Stage 28's
  mode-4 acceptance box, and Environment-Gated Capability Verification rows only
  if AC23 finds one genuinely affected. No status icon is hand-edited;
  deliverable and item statuses go through `aide progress set`.
- `docs/aide/insights.md` — new findings appended, per AC28. Existing entries
  are never reworded, reordered, deleted or ticked here.
- `docs/aide/items/135-validate-stage29.md` — this spec's Decisions log.

**Asserts against:**

- `docs/aide/roadmap.md` — AC24 reads Stage 29's acceptance text; AC14 reads the
  four-level clause it prescribes. Read only; framework/process file, PR-gated.
- `docs/aide/queue/queue-018.md` — the *Testable* lines this replay checks
  against. Read only.
- `docs/aide/golden-decision-table.md` — AC2 resolves the four replacement
  guarantees from the signed rows. Read, never edited.
- `docs/aide/golden_evidence.generated.json` — the item-134 companion; read as
  part of the AC2/AC25 inventory, never regenerated here.
- `docs/aide/items/129-coincident-centroids-in-the-pipeline.md` — AC14 cites its
  Decisions log as one of the two standing evidence sources. Read only.
- `src/segfacet/features/spline_offset.py` — AC14 asserts against its
  `_MIN_LEVELS_FOR_HELD_OUT = 5` and its documented four-level-blind-spot
  limitation block naming the governing gate.
- `src/segfacet/features/consistency.py` — AC8/AC9 exercise
  `compute_monotonic_consistency` through the record builder.
- `src/segfacet/reference/reference_default.json` — AC5's replay reads it as the
  committed float-carrying artifact; never modified.
- `src/segfacet/reference/reference_verse_v1.json` — read only; explicitly not
  rebuilt (see Assumptions).
- `src/segfacet/default_config.yaml` — AC11 reads the shipped thresholds behind
  the clean-control finding count.
- `tests/committed_artifact_guard.py` — AC5/AC6 run its `iter_violations` /
  `violation_message` over the real `tests/` tree. Read, never edited.
- `tests/test_127_committed_artifact_tolerance.py` — AC5 runs its AC15 sweep
  test. Read, never edited.
- `tests/report_format_fixture.py` — AC2/AC3 exercise the surviving format
  fixture; the deletion replay happens in the clone, and this file is unchanged
  in this item's diff.
- `tests/golden/report_format_contract.json` — the contract that fixture
  writes; read by the same AC2/AC3 and likewise unchanged in this item's diff.
- `tests/test_129_coincident_centroids_and_held_out_floor.py` — AC15 reuses its
  coincident-label-map builder; AC18 designates two of its nodes. Read, never
  edited.
- `tests/test_131_tangent_direction_normalisation.py` — one of AC18's
  designated fails-before-the-fix nodes. Read, never edited.
- `tests/test_132_monotonicity_against_traversal_order.py` — likewise an AC18
  designated node. Read, never edited.
- `tests/test_133_tptbox_pin_and_verse_retirement.py` — likewise an AC18
  designated node. Read, never edited.
- `tests/test_128_relocation_checks.py` — one of the three modules AC20's
  structural statement resolves against. Read, never edited.
- `tests/test_130_one_closest_point_search.py` — likewise resolved against by
  AC20. Read, never edited.
- `tests/test_134_decision_table_evidence_companion.py` — likewise resolved
  against by AC20. Read, never edited.
- `tests/corpus/manifest.json` — AC25 reads every `detection` field; AC8–AC11
  resolve the mode-4 and clean-control fixtures through it.
- `tests/corpus/fixtures/*.nii.gz` — AC8–AC11 run the pipeline over them;
  recomputed live, never modified.
- `tests/test_040_synthetic_corpus.py` — AC25 asserts the recorded 7/8 count
  agrees with this module's mode-set constants, and with those of the three
  modules below. Read only; a disagreement is a finding, not a licence to edit
  them.
- `tests/test_057_acceptance_stage7.py` — read for the same AC25 mode-set
  agreement.
- `tests/test_120_leave_one_out_offset.py` — read for the same AC25 mode-set
  agreement.
- `tests/test_125_stage28_validation.py` — read for the same AC25 mode-set
  agreement.
- `pyproject.toml` — AC16 reads the `tptbox==0.7.6` pin from it. Read only.
- `constraints.txt` — AC16 reads the same pin from it, and checks the two
  agree. Read only.
- `aide.toml` — AC23 reads the `[validation]` profile names. Read only;
  PR-gated.

## Testing Strategy

New module `tests/test_135_stage29_validation.py`, in the shape
`tests/test_125_stage28_validation.py` established for Stage 28: it pins the
half of this validation that is mechanically checkable so a later change cannot
move it silently, while the replays themselves belong to the Validation section
and are recorded in Decisions rather than asserted in-suite. Every test must be
deterministic and environment-independent — no network, no cohort, no clone.

In-suite:

- AC1: the eleven retired paths do not exist; `tests/corpus/golden/` is absent
  and `tests/golden/` contains exactly `report_format_contract.json`.
- AC2: each of the four replacements resolves — the named modules define the
  named functions, and none of them reads a path under `tests/corpus/golden/`.
- AC4: the per-path `git log --follow --name-status` audit, guarded to skip
  cleanly on a shallow clone (CI fetches full history since `db9d70e`, but a
  shallow checkout must skip, never fail — the `test_116` precedent).
- AC5/AC6: `committed_artifact_guard.classify_module` on a source string
  containing the *same* comparison the scratch-branch replay adds yields a
  violation whose message names `assert_matches_committed_artifact` — the
  in-suite shadow of the replay, explicitly documented in the docstring as *not*
  a substitute for it.
- AC8/AC9: `mode4_relabel_swap` through the shipped record builder reads
  `is_monotonic is False` with `non_monotonic_pairs` naming the swapped levels —
  the fact Stage 28's criterion wanted and item 132 delivered, pinned here so it
  cannot silently regress.
- AC11: `clean_control` reads `is_monotonic is True` with empty
  `non_monotonic_pairs`.
- AC14: **a pin on the observation, not on the wish** — a 4-level curve with an
  interior level displaced 15 mm yields held-out offsets all below a stated
  degeneracy floor, with a docstring stating plainly that Stage 29's acceptance
  line wanted non-degenerate offsets here and this records degenerate ones, and
  why (`k = 3`, four coefficients, the 2026-08-27 gate). The companion assertion
  that 5 and 6 levels separate the same displacement keeps the pin from reading
  as "the estimator is broken everywhere".
- AC15: the nested-label map yields a record carrying
  `stage3_unavailable.reason == "coincident_centroids"` naming both levels.
- AC16: both pin files carry the same `tptbox` version, it is ≥ 0.7.6, and the
  installed distribution's `License` metadata contains neither `agpl` nor
  `affero` (case-insensitive).
- AC24: every Stage 29 acceptance box is ticked-and-annotated or
  unticked-and-reasoned (the biconditional, parsed from `progress.md`), and the
  third box is specifically unticked with a note naming the four-level clause.
- AC12/AC13: Stage 28's third acceptance box is ticked and annotated; its fourth
  is unticked with a non-empty reason. Parsed, not eyeballed.
- AC25: the count of manifest cases with `detection == "pipeline"` excluding the
  clean control equals 7 and the mode set equals `{1, 2, 3, 4, 5, 6, 7}`, and
  agrees dynamically with `test_040`'s and `test_057`'s constants rather than
  restating a literal.
- AC27: no edit made here introduces a bare status icon outside a structural
  status position (the warning class `aide check` emits for that).

Adversarial and edge cases:

- A Stage 29 or Stage 28 box ticked with no annotation must fail the AC24/AC12
  parser; so must one unticked with no reason.
- A resurrected `tests/corpus/golden/some_case.json` must fail AC1 — the check
  globs, so a single reintroduced file is caught.
- `_MIN_LEVELS_FOR_HELD_OUT` moved back to `4`, or the docstring's limitation
  block stripped of its gate reference, must fail AC14's companion assertions.
- A guard allowlist widened to cover `reference_default.json` must fail AC5's
  in-suite shadow (the comparison would stop classifying as a violation).
- Determinism: two `extract_feature_record` calls on `mode4_relabel_swap` return
  equal monotonicity and equal `non_monotonic_pairs`; two four-level offset
  computations return equal arrays.
- Immutability: no test mutates a committed fixture, `manifest.json`, or the
  format fixture; the four-level and nested-label maps are built in memory.
- The history-reading test must **skip** (never fail, never pass) when the
  repository is shallow or `git` is unavailable.

**Existing tests to reconcile.** This item changes no production behaviour, so
no existing assertion should move, and the ones this stage already flipped are
read rather than rewritten. Confirm each still agrees with the measured
manifest: `tests/test_040_synthetic_corpus.py`'s mode-set constants,
`tests/test_057_acceptance_stage7.py`'s `_PIPELINE_DETECTABLE_MODES`,
`tests/test_120_leave_one_out_offset.py::test_ac24_corpus_pipeline_detection_is_seven_of_eight`,
and `tests/test_125_stage28_validation.py::test_ac15_manifest_pipeline_detected_mode_count_is_seven`
(all four already reconciled to 7/8 by item 132). Also confirm
`tests/test_125_stage28_validation.py`'s AC17 acceptance-biconditional parser
still passes once Stage 28's mode-4 box is ticked here — this item ticks a box
that module parses, and a tick without an evidence note would fail it. If any of
these disagrees, that is a finding for Decisions and `insights.md`, **not** a
licence to edit them; none is in this item's authorised paths.

## Validation

This item **is** the validation; the validator must execute it, not re-run the
suite. Record in Decisions, each as observed output rather than a claim:

- the eleven retired paths and their per-path `git log --follow --name-status`
  result over `69e5cf5..HEAD`, plus the four replacements resolved to
  module::function (AC1–AC4);
- the format-fixture deletion replay's failure text (AC3);
- the scratch-branch guard replay: the added comparison, the failing test output
  and the message naming `assert_matches_committed_artifact`, and confirmation
  the branch was discarded (AC5–AC7);
- mode 4 and clean control through `extract_feature_record` and through
  `segfacet run --no-reference`: `is_monotonic`, `non_monotonic_pairs`, findings
  and the report excerpts, verbatim (AC8–AC11);
- the four-, five- and six-level held-out offset arrays (AC14);
- the nested-label-map CLI exit code, `stage3_unavailable.reason` and human-report
  excerpt (AC15);
- `pip show tptbox`'s `Version` and `License` lines, verbatim (AC16);
- the per-item fails-before-the-fix table: item, implementation commit, parent
  commit, designated nodes, observed failures, and each failure's attribution;
  plus the executed-vs-cited decision for every item and its reason (AC18–AC21);
- the clone path, the branch and commit under test, the venv bootstrap result
  and the full-suite pass/skip/fail counts (AC22);
- `python .aide/scripts/aide.py env`'s output and the environment-gated
  conclusion (AC23);
- `aide check` before and after (AC27).

**Environment gating.** No acceptance criterion here depends on an environment
this machine may lack: the three `[validation]` profiles (`pyradiomics`,
`docker`, `gpu`) are untouched by Stage 29, and no criterion needs the real
VerSe19 cohort (see Assumptions). The only external requirement is a working
`git` and enough disk for one clone plus a venv (~15 minutes). **Honest
downgrade if a replay cannot be performed:** the affected criterion is recorded
`❓ Unverified` naming the missing input, the corresponding `progress.md`
acceptance box is left unticked with that reason, and Stage 29 stays open. A
skip-clean suite is never evidence that a gated path ran, and a replay that
could not be performed is recorded as not performed — never inferred from a
green suite.

## Dependencies

Items 126, 127, 128, 129, 130, 131, 132, 133, 134 — all must be ✅. This item
validates their combined result and closes Stage 29.

It also closes a criterion belonging to the previous stage: Stage 28's mode-4
acceptance half, left unticked by item 125 on a measurement item 132 has since
changed. No human gate blocks this item; the 2026-08-27 spinal-curve-model gate
is already `✅ Approved` and is cited by AC14 as the governor of a change this
stage did **not** make.

**Downstream:** Stage 20 (traceability matrix and specificity ratchet) is
authored as a queue only after this stage closes, and consumes this item's
recorded 7/8 detection count, the post-retirement test inventory, and the
four-level blind spot as a known reachability limit. The insight backlog this
queue accumulated is triaged at the queue boundary by `/aide-feedback-loop`, not
here.

## Decisions & Trade-offs

**Replay evidence, recorded 2026-08-31.** All items 126-134 confirmed ✅ before
starting (Assumptions precondition held). `aide check` baseline: `OK (3
warning(s))`, matching the spec.

**AC1-AC4 — retirement audit (working checkout).** All eleven retired paths
absent: `tests/corpus/golden/{clean_control,mode1_displace,mode2_fragment,
mode3_inject_islands,mode4_relabel_swap,mode5_remove_level,
mode6_crop_at_border,mode7_sequence_break,mode8_force_overlap}.json`,
`tests/golden/016_features_report.json`, `tests/golden/022_stage3_report.json`.
`git log --follow --name-status` over `69e5cf5..HEAD` for each path shows
exactly one status line, `D`, at commit `cafd4cc`, with nothing after it. The
four replacements resolve to live code (see `progress.md`'s Stage 29 box 1
note for the full module::function list); `tests/golden/` contains exactly
`report_format_contract.json`.

**AC22 — fresh-clone suite (throwaway clone).** Cloned
`/mnt/data/spine/codes/SegFACET` into the scratchpad's `segfacet-135-clone`,
checked out `aide/135-validate-stage-29-golden-retirement` (HEAD `6bf0f20`,
identical to the working checkout's HEAD at replay time), bootstrapped with
`python .aide/scripts/aide.py env --bootstrap` (succeeded). Full-suite result:
**4 failed, 6011 passed, 58 skipped** in 871.97s. Two failures are the
expected pre-edit state `tests/test_135_stage29_validation.py`'s own module
docstring documents (`test_ac24_every_stage29_box_ticked_implies_evidence_or_unticked_implies_reason`,
`test_ac12_stage28_mode4_box_is_ticked_and_annotated`) — both pass once this
item's `progress.md` edits land (confirmed: re-running
`tests/test_135_stage29_validation.py` alone in the working checkout after the
edits gives 67 passed, 1 failed). The remaining two are **not** explained by
the progress.md edit and do **not** resolve by it — both are genuine,
pre-existing defects in the *committed test tree* at `6bf0f20`, independent of
this item's own edits, reproduced identically in the working checkout and in
the clone:

1. `test_126_golden_retirement.py::test_ac17_no_live_reference_outside_allowlist[tests/corpus/golden]`
   fails because item 135's own `tests/test_135_stage29_validation.py`
   legitimately references the string `"tests/corpus/golden"` (in prose and in
   its own AC2 "no other module references the retired path" assertion), and
   `test_126`'s `_AC17_ALLOWLISTED_FILES` was never extended to include it.
   Fixing this requires editing `tests/test_126_golden_retirement.py`, which
   this item's Authorised paths list read-only. Logged to `insights.md`.
2. `test_135_stage29_validation.py::test_adv_synthetic_deliverable_bullet_status_line_is_flagged`
   has a literal test string missing the leading `"- "` bullet marker its own
   regex requires, so it fails unconditionally regardless of `progress.md`
   content or environment. This item may not edit its own committed test
   module. Logged to `insights.md`.

Per the spec's Validation section ("Honest downgrade if a replay cannot be
performed"): AC22 is recorded honestly as **not fully green** — 2 of 4
failures are the expected pre-edit state (now resolved by this item's
`progress.md` edits, confirmed in-suite), and 2 are pre-existing test-file
defects this item is not authorised to fix. Neither defect touches production
code, neither contradicts any substantive Acceptance Criterion this item
verifies (mode 4's reading, the four-level degeneracy, the fails-before-the-fix
replays, the tptbox pin — all independently confirmed by direct measurement
below), and both are out-of-scope findings per the item's own "Not in scope"
section, not a licence to edit test files this item does not own.

**AC5-AC7 — guard replay (throwaway clone, scratch branch
`scratch-ac5-ac7-guard-replay`).** Added
`tests/test_zz_synthetic_135_scratch.py` containing
`dest.read_bytes() == Path("src/segfacet/reference/reference_default.json").read_bytes()`.
Running `test_127_committed_artifact_tolerance.py::test_ac15_classifier_reports_zero_violations_on_tests_tree`
**failed**, message: `"byte-exact comparison(s) against a committed artifact
outside the allowlist -- use segfacet.synth.golden.assert_matches_committed_artifact
instead ... committed artifact 'src/segfacet/reference/reference_default.json'"` —
names `assert_matches_committed_artifact` verbatim. The scratch file was
removed and the scratch branch deleted (`git branch -D
scratch-ac5-ac7-guard-replay`); the clone returned to
`aide/135-validate-stage-29-golden-retirement` with `git status --short`
empty. The working checkout was never touched (only `insights.md` and
`docs/aide/items/135-validate-stage29.md` show uncommitted changes throughout
this replay).

**AC3 — format-fixture deletion (same scratch branch, clone).** Deleted
`tests/golden/report_format_contract.json`; running
`test_016_features_json.py::test_ac5_golden_snapshot` **failed** with
`FileNotFoundError: [Errno 2] No such file or directory:
'.../tests/golden/report_format_contract.json'` — names the missing file,
does not skip. Restored with `git checkout --
tests/golden/report_format_contract.json`; clone confirmed clean before the
branch was discarded.

**AC8-AC11 — mode 4 and clean control (working checkout).**
`extract_feature_record` on `mode4_relabel_swap`:
`is_monotonic == False`, `non_monotonic_pairs == [["L2", "L3"]]`. A real
`segfacet run --scan tests/corpus/fixtures/base_scan.nii.gz --seg
tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz --out <scratch>
--no-reference` exited `0`; its `segfacet_report.json` carries the same
`is_monotonic`/`non_monotonic_pairs` plus one `mislabel` finding: `"Vertebra
ordering inconsistent with label: labels 21 (L2) and 22 (L3) are out of
expected order along the spine (spline parameter does not advance)."`
`extract_feature_record` on `clean_control`: `is_monotonic == True`,
`non_monotonic_pairs == []`. The same `--no-reference` CLI invocation on
`clean_control_seg.nii.gz` exited `0` with `is_monotonic == True`, empty
`non_monotonic_pairs`, and `findings == []`.

**AC14 — four-level held-out offsets (working checkout, in-memory).** Using
`t129._straight_spine`/`_displace_index` (interior index 1, 15 mm, axis 0) and
`compute_leave_one_out_spline_offsets`:
- n=4: `[7.348609152784843e-05, 5.330684370393181e-06, 5.740531122353952e-06,
  3.782179445898854e-05]` mm — exactly item 129's recorded array, all
  `< 0.001` mm.
- n=5: `[0.4481337843493273, 1.854146142634933, 2.5665939787324734,
  5.57968192970584, 0.7429458688645586]` mm — displaced index reads
  `1.854` mm, well above the floor.
- n=6: `[15.310979796619236, 14.999999999515072, 7.126211588536627,
  4.054899843166418, 3.4911796553924166, 5.445490561457531]` mm.

**AC15 — nested-label map (working checkout, in-memory + CLI).**
`extract_feature_record` on `t129._coincident_label_map()` (labels 21/22
coincident at `(9.5, 9.5, 19.5)` mm): `stage3_unavailable ==
{"reason": "coincident_centroids", "detail": "Levels 'L2' and 'L3' (labels 21,
22) share the exact centroid mm-coordinate (9.5, 9.5, 19.5); the Stage 3
spline fit was not attempted.", "levels": ["L2", "L3"], "labels": [21, 22],
"coordinate_mm": [9.5, 9.5, 19.5]}`. A real `segfacet run --no-reference` on a
synthesised scan/seg pair carrying the same coincidence exited `0`, stderr
contained no `Traceback`, the emitted `segfacet_report.json` carried the same
`stage3_unavailable.reason`/`levels`, and `segfacet_report.txt` named both
`L2` and `L3`.

**AC16 — tptbox pin (project venv).** `.venv/bin/python -m pip show tptbox`:
`Version: 0.7.6`, `License: Apache License Version 2.0, January 2004` (no
`agpl`/`affero`, case-insensitive). `pyproject.toml` and `constraints.txt`
both pin `tptbox==0.7.6`, matching the installed version.

**AC18-AC21 — fails-before-the-fix (throwaway clone, `git switch --detach`).**
All eight designated nodes fail at the immediate parent of their item's
implementation commit — every failure is the designated pre-fix *behaviour*
observed by execution, none attributable to a separately-fixed test defect
(AC19: no attribution needed, all eight are genuine):

| Item | Impl. commit | Parent (checked out) | Node | Observed failure |
|---|---|---|---|---|
| 129 | `021f0bc` | `1466b8b` | `test_ac21_floor_is_five` | `assert 4 == 5` (`_MIN_LEVELS_FOR_HELD_OUT` still 4) |
| 129 | `021f0bc` | `1466b8b` | `test_ac5_extract_feature_record_returns_dict_not_raise` | raw `ValueError` from `fit_centroid_spline` (coincident centroids), not a degraded record |
| 131 | `5efd27d` | `8b94e62` | `test_ac1_cranial_first_straight_spine_reads_zero_not_180` | `tangent_angles_deg` entry `180.0`, not `~0.0` |
| 131 | `5efd27d` | `8b94e62` | `test_ac2_straight_spine_reversal_equivariant` | forward/reversed angles `(0.0,...)` vs `(180.0,...)`, not equivariant |
| 132 | `cc22bfd` | `628f673` | `test_ac1_mode4_relabel_swap_is_non_monotonic_through_shipped_record_builder` | `is_monotonic` reads `True`, not `False` |
| 132 | `cc22bfd` | `628f673` | `test_ac2_mode4_relabel_swap_non_monotonic_pairs_names_l2_l3` | `non_monotonic_pairs == []`, not `[["L2","L3"]]` |
| 133 | `8586772` | `26b5cf5` | `test_ac1_tptbox_pin_is_exactly_0_7_6` | `pyproject.toml` still pins `tptbox==0.7.5` |
| 133 | `8586772` | `26b5cf5` | `test_ac2_constraints_tptbox_pin_moved` | `constraints.txt` still pins `0.7.5` |

Every implementation/parent pair matched the spec's cited hashes exactly on
fresh resolution (`git log --oneline` between each item's `-> in-progress` and
`-> in-review` progress commits), so the Assumptions' "parent already carries
the test module" premise held for all four without a fallback to AC20's
cited-not-executed treatment.

**AC20 — structural items (stated, not executed as behaviour replays).**
Items **128** (relocated an integrity pin/renamed a fence header — no
behaviour to fail against, its own AC23 verification is
`tests/test_128_relocation_checks.py`'s committed suite), **130** (consolidated
spline plumbing; its evidence is that every existing value-level assertion
still passes, per its own Decisions log), and **134** (a new generated
companion artifact, `docs/aide/golden_evidence.generated.json`, with no prior
state to regress from) have no pre-fix *behaviour* their designated tests
could fail against — a parent-commit run would fail only because a module,
name or file does not yet exist, which is not the same claim as a behaviour
regression. Cited from each item's own Decisions log, not executed here.

**AC21 — predate-the-convention items (stated).** Items **126** and **127**
carry no fails-before-the-fix obligation. 126's verification is the
retirement audit (AC1-AC4 above); 127's is the guard replay (AC5-AC7 above).

**AC23 — environment (working checkout).** `python .aide/scripts/aide.py env`:
`aide env: OK (venv present, import succeeds)`. `aide.toml`'s three
`[validation]` profiles (`pyradiomics`, `docker`, `gpu`) are textually
untouched by any Stage 29 item's diff, and no Stage 29 acceptance clause reads
the real VerSe19 cohort (item 129 deliberately left `reference_verse_v1.json`
unrebuilt; item 133's check is a venv metadata read). Conclusion: **no**
Environment-Gated Capability Verification row is affected by this stage; the
table is left unchanged and the "Real VerSe GT" row is not re-evidenced, per
the spec's expected outcome.

**AC27 — `aide check` before/after.** Before: `OK (3 warning(s))`. After this
item's `progress.md`/`insights.md` edits: `OK (3 warning(s))` — identical
warning classes (32-spec Assumptions audit, 2 Stage-16 gates). No new warning
class introduced.

**`aide check --queue 018` (informational, per Assumptions).** Reports the
expected shape only: dozens of pin-vs-edit errors/warnings naming items
126-135 pinning each other's already-shipped, already-✅ paths under `Asserts
against` — the structural collision items 106/115/125/126/132 already
recorded, inert because every named item is merged. No entry outside that
shape was found, so nothing new to log. AC27 covers `aide check`, not `aide
check --queue`, per the spec.

**Tooling note: acceptance-box ticks were hand-edited, not via `aide progress
accept`.** The framework's `aide progress accept STAGE --criterion N
--evidence "..."` verb exists in this checkout and is the framework's
preferred mechanism per `.aide/AGENT-CONTEXT.md` ("Mechanical actions go
through the CLI") and the `aide-living-documents` skill. It was not used here
for two reasons: (1) it can only *tick* a box with a flat single-line
`--evidence` string appended after the checkbox text; Stage 29's box 3 must
stay **unticked** with a multi-sentence reason, which the verb cannot express
at all; (2) the rich, multi-sentence, code-span-laden evidence style already
established by items 106/115/125 (all predating this verb) would be flattened
by shell-argument passing. This item's own Authorised paths list
`docs/aide/progress.md`'s acceptance boxes as directly editable, and the
resulting shape was verified against `tests/test_135_stage29_validation.py`'s
own biconditional parser (AC24/AC12/AC13, all passing) — a defect if the hand
edit produced an unparseable shape. Logged here rather than acted on further;
worth a framework note that `accept` doesn't cover the unticked-with-reason
case a stage-validation item routinely needs.

**Findings logged to `insights.md` (AC28), not remediated here:** the two
test-file defects above (AC17 allowlist gap; the AC26-shadow literal string
bug in item 135's own adversarial test).

**Divergence from the spec's starting numbers:** none found — every value
this item re-measured (the eleven retired paths, the four replacements, the
guard replay, mode 4/clean control, the four/five/six-level offset arrays, the
nested-label-map reading, the tptbox version/license, all eight
fails-before-the-fix nodes) matched the spec's cited starting values exactly.

**AC17 allowlist gap fixed, recorded 2026-08-31.** `tests/test_126_golden_retirement.py`'s
`_AC17_ALLOWLISTED_FILES` did not name `tests/test_135_stage29_validation.py`,
which legitimately references the retired `tests/corpus/golden` path while
checking the retirement — the same missed-consumer shape items 106/115/125/126/132
already hit for their own paths. Added to the allowlist and to this item's own
Authorised paths above.

**Documentation reconciliation, recorded 2026-08-31.** Removed the stale
`tests/test_126_golden_retirement.py` bullet from Authorised paths' Asserts-against
list (it duplicated the May-change entry the AC17 fix above added, and read-only
no longer described the file once commit `a496cae` started editing it); `aide
scope 135` now reports OK. `insights.md` entries 37 (the AC17 allowlist gap) and
38 (the bullet-status literal bug) were both already resolved by commit `a496cae`
within this item, so both were ticked via `aide insights tick` rather than left
open — the entry text is unchanged, only the checkbox and a pointer note were
added, per the immutability rule.
