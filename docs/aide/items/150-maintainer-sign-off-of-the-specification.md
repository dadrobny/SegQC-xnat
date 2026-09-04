# Item 150 — Maintainer sign-off of the failure-mode specification

> **Created:** 2026-09-04 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 150
> **Objectives:** G2 (detect the catalogued failure modes), G8 (extensible — the
> specification is the authored source every conformance artifact reports against)
> **Suggested branch:** `aide/150-maintainer-sign-off-of-the`

---

## Description

Stage 30 **D6**. Items 144–149 authored the failure-mode specification
(`src/segfacet/failure_modes.SPECIFICATION`), collapsed the five partial sources
onto it, and re-pointed the generated artifacts at it as conformance reports.
Nothing in that chain asked a **person** whether the resulting catalogue is
right. This item is that question, and it is the stage's **human checkpoint** in
the sense Stage 19's item-106 steering review was one: the maintainer reads
[`../failure_modes.generated.md`](../failure_modes.generated.md) **entry by
entry** — all ten entries, eight `vision.md` §6 seed modes plus mode 9
(implausible tissue, derived `validated`) and mode 10 (the first `proposed`
entry) — and either accepts the rendering or names the entries to change. The
date and the outcome are then recorded in the specification module's **own
docstring**, exactly where `feature_docs.py`'s `STATUS_OVERRIDES` comment records
the Stage-19 steering review's date and outcome, and the walkthrough itself is
transcribed into this spec under `### Stage-30 maintainer sign-off`.

**This item is a checkpoint, not a build.** It ships no new rule, no new mode, no
schema change and no new behaviour. Its whole deliverable is (a) a human gate in
[`../progress.md`](../progress.md) and (b) the recorded sign-off. The catalogue's
content changes **only** where the maintainer's reading says it must, and such a
change is an edit to an authored `ModeSpec` field followed by a regeneration —
never a new field, a new mode, or a new derivation.

### What is agent work and what is the human's

The split is the point of the item, so it is stated before anything else.

| Step | Who | What |
|---|---|---|
| 1 | agent | Prepare the review surface: regenerate both artifacts, confirm they are byte-identical to the committed copies, and assemble the review pack (below). |
| 2 | agent | Raise the human gate in `../progress.md`'s `## Human gates` table with `Blocks: 139, 140, 141, 142`, `⏳ Awaiting`. |
| 3 | agent | **STOP.** Hand back. Nothing further on this item is agent work until the gate is resolved. |
| 4 | **human** | Read the ten entries and decide. Resolve the gate with `python .aide/scripts/aide.py gate approve <n> --evidence "…"` (or `gate decline`) — see `aide gate list` for `<n>`. |
| 5 | agent | Only after ✅ Approved: apply the changes the maintainer named, regenerate both artifacts, write the `Signed off:` record into the module docstring, transcribe the walkthrough into this spec, append any out-of-scope observation to `../insights.md`, commit. |

**No agent may approve or decline the gate.** Not the builder, not the validator,
not an orchestrator, not a subagent, and not this item's own author. `aide gate
approve` / `aide gate decline` are the maintainer's commands and only the
maintainer's; the gate exists precisely because the decision is not derivable
from the work (`.aide/conventions.md` §1 → Human gates). Resolving it by
hand-editing the table is equally forbidden — AC2 tests the Status cell against
the exact string `set_gate_status()` writes, so a hand edit is detectable and
fails.

**If the gate is declined**, no sign-off is recorded, this item does **not**
complete, and the loop hands back for re-planning. A decline keeps blocking
(`.aide/conventions.md` §1); it is not a route to a green suite.

### The review pack the maintainer is handed

Assembled by step 1, all of it already in-tree:

1. [`../failure_modes.generated.md`](../failure_modes.generated.md) — the review
   surface proper, one `## Mode N` section per entry.
2. [`../traceability_matrix.generated.md`](../traceability_matrix.generated.md) —
   the conformance report item 149 re-pointed at the specification, so the
   maintainer sees expected-vs-measured firing beside each entry.
3. Three **open** `insights.md` entries whose own text defers a decision to this
   item, which the maintainer must be shown rather than left to find:
   - the `derive_status` vacuous-agreement half (`item 145, 2026-09-03`): the
     declaring-rule precondition landed in item 146, but an authored
     `expected_firing=()` on a case that fires nothing still agrees vacuously
     and can validate. Whether that is acceptable lifecycle semantics is
     explicitly *"a lifecycle-semantics call for the maintainer at item 150"*.
   - the `dx_mm` / `dy_mm` / `dz_mm` classification (`item 148, 2026-09-04`):
     classified `signal` for `mislabel` while the firing decision reads
     `offset_mm` alone; the entry records the reclassification as *"a decision
     for item 149/150 rather than a review fix"*.
   - the geometric-only rule-attribution scan (`item 148, 2026-09-04`): the
     matrix's attribution column covers only the geometric corpus, *"leaving the
     seam undocumented at the artifact item 150 signs off"*.
4. Per entry, the eight facets the queue line names: **definition,
   discriminator, expected firing sets, severity, observability, per-edge
   evidence rungs, lifecycle status, provenance**.

### Scope fence

This item does **not**: write or change a rule, threshold, extractor or verdict;
add or remove a mode; change the `ModeSpec` schema, any derivation
(`derive_status`, `derive_mode_rung`, `measured_firing`) or either renderer; add
a corpus case; edit `vision.md` or `roadmap.md`; or tick a Stage-30 acceptance
criterion (see **D1** in Decisions & Trade-offs — the stage acceptance replay is
item 151's, and it requires a clean-tree run this item does not perform).

## Acceptance Criteria

_Every criterion below is an invariant over the resulting content, re-checkable
after merge. **The AC block is expected to be red until the maintainer resolves
the gate** — that redness is the checkpoint working, not a defect to route
around._

- [ ] **AC1: the gate exists, is unique, and reaches the four held items.**
  Parsing `docs/aide/progress.md` with `.aide/scripts/aide.py`'s
  `human_gates()` (imported in-process, the
  `test_114_documentation_corrections.py` idiom) yields **exactly one** row whose
  Gate cell contains the literal `Stage 30 failure-mode specification sign-off`.
  That row's `blocks` list equals `[139, 140, 141, 142]` exactly (measured
  equality, not containment), its `stage` is `None`, its `blocks_all` is `False`,
  and its `kind` is one of `"awaiting"`, `"approved"`, `"declined"` — never
  `None`, which is how the engine reports an unrecognised status cell.

- [ ] **AC2: the gate's Status cell is byte-equal to what `aide gate` writes, so
  a hand edit fails.** Let `d` be the ISO date parsed out of the live Status
  cell. Calling `set_gate_status(text, <this row's 1-based index>, <this row's
  kind>, today=d)` on the committed `progress.md` text reproduces the live line's
  Status cell **character for character**. The Decision cell is non-empty after
  `.strip()`, contains no `|` and no line break, and is not one of the
  placeholders `""`, `"TBD"`, `"n/a"`, `"pending"`. `d` is not in the future
  (`<= datetime.date.today()`).

- [ ] **AC3: the gate is resolved approved, and the block is released only
  there.** The row's `kind` is `"approved"`, and the gate is absent from
  `blocking_gates()` over the same lines. Adversarially: the same lines with only
  this row's Status cell replaced by `⏳ Awaiting` put the gate **back** into
  `blocking_gates()`, and with `❌ Declined` likewise — a declined gate still
  blocks. The adversarial variants are built in memory; `progress.md` is not
  written.

- [ ] **AC4: `aide check` reports the gate's state and warns about no unfilled
  slot.** `run_checks(repo_root, load_config(repo_root))` returns `errors == []`.
  No returned warning matches `unfilled template slot`, and the `## Human gates`
  section of `progress.md` contains no `{{` sequence at all. Classifying every
  returned warning by the shape idiom of
  `test_145_eight_hypothesised_modes.py::_classify_warning`, no warning falls
  outside the recorded baseline classes (`assumptions-block`,
  `awaiting-a-decision`, `branch-state`, `retracted-criterion`). Adversarially:
  with this row's Status cell set to `⏳ Awaiting` in a temporary copy, exactly
  one warning names this gate and it classifies as `awaiting-a-decision` — the
  engine reports the gate's state rather than staying silent about it.

- [ ] **AC5: the module records a sign-off, and the item-144 placeholder is
  gone.** `segfacet.failure_modes.__doc__` contains a `Sign-off` section
  (underlined heading, the shape the module's other sections use) whose body
  contains **exactly one** line matching, anchored,
  `^Signed off: (\d{4}-\d{2}-\d{2}) -- (.+)$`. The literal sentence `No
  maintainer sign-off is recorded yet.` appears nowhere in the module source.
  The docstring still carries item 146's record intact — the literal `item 146`
  and at least one `src/segfacet/*.py` path that resolves to a real file — so the
  edit is additive (this is what `test_146…::test_ac35_…` already pins).

- [ ] **AC6: the recorded date is real and not in the future.**
  `datetime.date.fromisoformat()` parses group 1 of AC5's match; the result is
  `<= datetime.date.today()` **and** `>= date(2026, 9, 4)` — the day item 149
  landed, i.e. the earliest date on which the reviewed rendering existed. A date
  outside either bound fails, naming the bound and the value.

- [ ] **AC7: the recorded outcome is substantive and drawn from the disposition
  vocabulary.** Group 2 of AC5's match, after `.strip()`, is non-empty, is at
  least 40 characters, contains exactly one of the two literals
  `accepted as rendered` / `accepted with changes`, and is not any of
  `"TBD"`, `"n/a"`, `"see review"`, `"pending"`, `"signed off"`, or a bare repeat
  of either disposition literal with nothing else. It also contains the literal
  relative path of this spec, `docs/aide/items/150-maintainer-sign-off-of-the-specification.md`,
  and that path resolves to a real file — the transcript pointer, the
  `STATUS_OVERRIDES` comment's precedent.

- [ ] **AC8: the walkthrough covers every entry, re-derived from the primary
  source.** This spec contains the heading `### Stage-30 maintainer sign-off`.
  The set of integers `N` for which a line matching `^- Mode (\d+) — ` appears
  under that heading (up to the next `###` or `##`) equals
  `set(segfacet.failure_modes.SPECIFICATION)` **exactly** — no missing entry, no
  entry for an id the specification does not carry, and the count is read from
  `SPECIFICATION`, never hardcoded as 10.

- [ ] **AC9: every entry line carries a disposition, and a changed entry names
  what changed.** Each `- Mode N — ` line contains exactly one of the literals
  `confirmed` / `changed`. Every line reading `changed` additionally names at
  least one real authored field: a token drawn from the union of
  `{f.name for f in dataclasses.fields(ModeSpec)}`,
  `{f.name for f in dataclasses.fields(IntendedRule)}` and
  `{f.name for f in dataclasses.fields(CorpusCaseExpectation)}`, recomputed live
  rather than listed by hand. A line reading `changed` that names no such field
  fails, naming the mode id.

- [ ] **AC10: the eight review facets are declared and each resolves onto a real
  field.** The preamble under `### Stage-30 maintainer sign-off` (above the first
  `- Mode ` line) contains all eight facet words verbatim — `definition`,
  `discriminator`, `expected firing`, `severity`, `observability`, `evidence
  rung`, `status`, `provenance` — and a mapping in that preamble binds each to a
  dataclass field name that exists in the live field union of AC9. A facet whose
  named field does not exist fails, naming the facet.

- [ ] **AC11: both artifacts are byte-identical to a fresh regeneration.**
  `segfacet.failure_modes.main(["--json", <tmp>, "--md", <tmp>])` into a tmp
  directory produces a JSON that `segfacet.synth.golden.assert_matches_committed_artifact`
  accepts against `docs/aide/failure_modes.generated.json`, and a Markdown whose
  UTF-8-decoded text equals the committed
  `docs/aide/failure_modes.generated.md`'s. Both committed files contain no
  `\r`, end with exactly one `\n`, and are non-empty. Two successive
  regenerations into different paths agree byte-for-byte (the run-to-run
  determinism half).

- [ ] **AC12: every entry the review changed is present in both artifacts.** For
  every mode in `SPECIFICATION` and every authored string field the renderers
  emit (`name`, `short_name`, `definition`, `discriminator`, `observability`,
  `severity`, `provenance`, `mechanism`), the live value appears in that mode's
  `## Mode N` section of the committed `.md` **and** at the matching key of the
  committed `.json` entry — recomputed from `SPECIFICATION`, never from a
  fixture, so an authored field the maintainer changed and a regeneration that
  was skipped cannot both pass. Empty-string fields are skipped explicitly, and
  the test asserts that at least one field per mode was actually compared, so the
  loop cannot pass vacuously.

- [ ] **AC13: the four held Stage-20 items are still ⏸️ Deferred.** In
  `docs/aide/progress.md`'s Stage 20 section, the deliverable bullet carrying
  `*(Item 139)*`, and likewise 140, 141 and 142, each has `⏸️` as its **leading**
  bullet icon (the structural status position of `.aide/conventions.md` §1 →
  status-icons). Read by locating the four bullets, not by scanning the file for
  the icon. _This is a **dated** claim about the world, true while Stage 20's
  remainder is unqueued and guaranteed to become false when it is queued: the
  first item that lands any of 139–142 **must** list `tests/test_150_maintainer_sign_off.py`
  under its **Authorised paths → May change** and update this test. Recorded here
  so that item's author does not discover it as a red suite._

- [ ] **AC14: every insight this item raised is well-formed and honestly dated.**
  Every line in `docs/aide/insights.md` (and every
  `docs/aide/insights/archive-*.md`, per CLAUDE.md's archive gotcha) whose
  provenance names `item 150` matches the §1 grammar
  `- [ ] <knowledge|defect|gap|automation|framework> — <text> *(item 150, YYYY-MM-DD, engine X.Y.Z)*`,
  carries a date `<= datetime.date.today()`, and carries an engine token equal to
  the contents of `.aide/VERSION` stripped. No pre-existing line is reworded,
  reordered or deleted — the count of non-`item 150` lines is `>=` its value at
  this item's base.

- [ ] **AC15: the zero case is stated, not left silent.** The transcript's
  preamble contains **either** at least one out-of-scope observation whose text
  appears verbatim in `docs/aide/insights.md` (or an archive file), **or** the
  literal words `no out-of-scope observation recorded`. Both being absent fails.
  This is item 106's `no override recorded` discipline: a review that legitimately
  raises nothing passes, and a review that skipped the step does not.

## Assumptions

- **A1 (engine 1.37.0):** `aide gate approve|decline <n> --evidence "…"` writes
  the Status cell as exactly `f"{icon} ({YYYY-MM-DD})"` with icon
  `✅ Approved` / `❌ Declined`, and writes the note into the row's fourth cell,
  rejecting a note containing `|` or a newline (`set_gate_status`,
  `.aide/scripts/aide.py`). AC2 is written against that shape. If a later engine
  changes the rendering, AC2's test re-derives the expected cell by calling
  `set_gate_status` rather than pinning the literal, so it tracks the engine
  instead of breaking on it.
- **A2 (engine 1.37.0):** a `## Human gates` row is four cells
  (`Gate | Blocks | Status | Decision`), the Blocks cell accepts bare item
  numbers, and `blocking_gates()` treats every kind other than `approved` —
  including `declined` — as still blocking. AC1/AC3 rest on this.
- **A3 (engine 1.37.0):** `run_checks` emits the human-gate warning
  `progress.md:<n>: human gate <k> (…) is awaiting a decision — blocks …` for an
  unresolved gate and nothing for a resolved one; the unfilled-slot lint
  (`template_residue_errors`) scans every `*.md` under `docs/aide/` for a bare
  doubled-brace slot marker and reports it as an **error**, not a warning. AC4 asserts `errors ==
  []` for that reason and additionally checks the warning list for the literal
  text, so it holds whichever severity a later engine uses.
- **A4:** the gate index is **5** as of this spec's writing (four rows exist).
  The index is positional and shifts if a row is inserted above, so both the
  human instructions and AC2's test resolve it by matching the Gate cell's
  literal text through `human_gates()`, never by the constant 5. `aide gate list`
  is the authority at the moment of approval.
- **A5:** the sign-off record is read from `segfacet.failure_modes.__doc__`, not
  from the source file's text. The suite is never run under `python -OO`, which
  strips docstrings and would make AC5–AC7 fail for a reason unrelated to the
  claim. This matches `test_146…::test_ac35_…`, which already reads `__doc__`.
- **A6:** the maintainer approves. The docstring record, the transcript and
  AC5–AC12 all presuppose an approval; a decline produces none of them and the
  item hands back unfinished rather than recording a negative sign-off.
- **A7:** the reviewed rendering is the one committed at this item's base — ten
  entries, nine deriving `validated`, mode 10 deriving `proposed` (measured
  2026-09-04 on `aide/queue-020`). If a change the maintainer calls for moves a
  derived status, AC11/AC12 still hold because both sides are recomputed; only
  the transcript's own prose needs to say so.
- **A8:** `.gitattributes` already pins both artifacts `text eol=lf` (lines 60
  and 61), so this item adds no pin and `aide check`'s `.gitattributes` lint has
  nothing new to say. Verified 2026-09-04. Any regeneration must still be written
  with `write_bytes` and `\n` — which `failure_modes.main` already does; this
  item changes no writer.

## Implementation Steps

1. **Confirm the review surface is current.** Regenerate into a scratch
   directory and confirm byte-identity with the committed pair (AC11's
   mechanism). Do **not** rewrite the committed files if they already match.
2. **Assemble the review pack** as listed in the Description: the two generated
   Markdown artifacts plus the three named open `insights.md` entries. Read them
   with `python .aide/scripts/aide.py insights list --open`; do not hand-parse the
   file.
3. **Add the gate row** to `docs/aide/progress.md`'s `## Human gates` table —
   the one hand edit to that document any role may make. Four cells:
   - Gate: `Stage 30 failure-mode specification sign-off — the maintainer reads
     docs/aide/failure_modes.generated.md entry by entry (all ten entries;
     definition, discriminator, expected firing sets, severity, observability,
     per-edge evidence rungs, lifecycle status, provenance) and either accepts
     the rendering or names the entries to change. Date and outcome are recorded
     in src/segfacet/failure_modes.py's own docstring, the
     feature_docs.py::STATUS_OVERRIDES precedent`
   - Blocks: `139, 140, 141, 142`
   - Status: `⏳ Awaiting`
   - Decision: the pointer to this spec's transcript heading and the explicit
     statement that no agent may resolve it.
   No `|` and no line break in any cell.
4. **Verify** with `python .aide/scripts/aide.py gate list` and
   `python .aide/scripts/aide.py check` that the row parses, reaches items
   139–142, and produces exactly one new warning of the `awaiting-a-decision`
   class and no error.
5. **STOP and hand back.** Report the gate's index and the review pack. Do not
   write the docstring record, do not write the transcript, do not run
   `aide gate approve`, and do not attempt to complete the item.

   --- everything below runs only after the human has resolved the gate ---

6. **Read the resolution.** `aide gate list`. If ❌ Declined: stop, record the
   decline's reason in this spec's Decisions log, and hand back — the item does
   not complete.
7. **Apply the changes the maintainer named**, if any: edit the authored
   `ModeSpec` fields in `src/segfacet/failure_modes.py` only — no schema change,
   no new mode, no derivation change, no rule change.
8. **Regenerate** both artifacts:
   `.venv/bin/python -m segfacet.failure_modes`. If step 7 changed a field the
   traceability matrix renders, regenerate that pair too
   (`.venv/bin/python -m segfacet.traceability`) and confirm the two conformance
   artifacts agree.
9. **Write the sign-off record** into the module docstring's `Sign-off` section,
   replacing the item-144 placeholder sentence. One anchored line, then prose:

       Sign-off
       --------
       Signed off: <YYYY-MM-DD> -- <outcome sentence containing exactly one of
       "accepted as rendered" / "accepted with changes", the entry count, and
       the path docs/aide/items/150-maintainer-sign-off-of-the-specification.md
       where the full walkthrough is transcribed>.

       <one paragraph: what the maintainer changed, or that nothing changed.>

10. **Transcribe the walkthrough** into this spec under a new
    `### Stage-30 maintainer sign-off` heading in Decisions & Trade-offs: the
    date; the facet-to-field mapping (AC10); the zero-case sentence or the
    out-of-scope observations (AC15); then one `- Mode N — ` line per entry, each
    reading `confirmed` or `changed`, and a `changed` line naming the field.
11. **Append** any out-of-scope observation as one line each in
    `docs/aide/insights.md`, in the §1 grammar with provenance `item 150` and the
    engine read from `.aide/VERSION`. Append only; reword, reorder and delete
    nothing.
12. **Re-run** `python .aide/scripts/aide.py check` — no error, and the gate
    warning is gone now that the gate is resolved.

## Authorised paths

**May change:**

- `src/segfacet/failure_modes.py` — the module docstring's `Sign-off` section
  (step 9), plus any **authored `ModeSpec` field value** the maintainer's reading
  calls for (step 7). No schema field added or removed, no function body changed.
- `docs/aide/failure_modes.generated.md` — regenerated (step 8).
- `docs/aide/failure_modes.generated.json` — regenerated (step 8).
- `docs/aide/traceability_matrix.generated.md` — regenerated only if step 7
  changed a field this artifact renders.
- `docs/aide/traceability_matrix.generated.json` — the same.
- `docs/aide/progress.md` — the `## Human gates` row only (step 3), plus whatever
  the `aide` CLI writes there (the gate resolution, the item status). No
  acceptance box is ticked by this item — see **D1**.
- `docs/aide/items/150-maintainer-sign-off-of-the-specification.md` — this spec:
  the `### Stage-30 maintainer sign-off` transcript and the Decisions log.
- `tests/test_150_maintainer_sign_off.py` — this item's tests.
- `docs/aide/insights.md` — appended lines only (step 11); nothing reworded,
  reordered or deleted.

**Asserts against:**

- `.aide/scripts/aide.py` — `human_gates`, `blocking_gates`, `set_gate_status`,
  `run_checks` and `load_config` are imported in-process and read live by
  AC1–AC4. Unchanged.
- `.aide/VERSION` — the engine token AC14 compares each `item 150` insight
  against. Unchanged.
- `docs/aide/vision.md` — §6's numbered seed titles, read live through
  `failure_modes.vision_seed_titles()` during regeneration (AC11). Unchanged, and
  framework/process-gated regardless.
- `docs/aide/feature_catalogue.generated.md` — read as part of the review pack
  and unchanged by this item; a change here would mean step 7 exceeded its fence.
- `tests/corpus/manifest.json` — driven live by `measured_firing` /
  `derive_status` on every regeneration (AC11, AC12). Unchanged.
- `tests/corpus/intensity/manifest.json` — the same, for mode 9. Unchanged.
- `src/segfacet/heuristics/rule.py` and the concrete rule modules — the registry
  `derive_status` reads. Unchanged: this item declares no mode and writes no rule.
- `src/segfacet/feature_docs.py` — the `STATUS_OVERRIDES` comment is the recorded
  precedent AC7's transcript-pointer requirement is modelled on; read, never
  written.
- `.gitattributes` — the two `text eol=lf` pins AC11's LF assertions rest on
  (**A8**). Unchanged.

## Testing Strategy

One focused test per AC in a new `tests/test_150_maintainer_sign_off.py`,
grouped into the five blocks the ACs form (gate, sign-off record, walkthrough,
artifacts, housekeeping).

**Adversarial and edge cases to cover explicitly:**

- **Hand-edited gate.** AC2's test must fail on a Status cell that reads
  `✅ Approved` with no date, `✅ approved (2026-09-05)` (wrong case), or a date
  in a non-ISO shape — all built as in-memory variants, never written to
  `progress.md`.
- **A declined gate still blocks.** AC3's `❌ Declined` variant is the case a
  reader most often assumes is "resolved, therefore released".
- **Future and pre-history dates.** AC6 must reject `date.today() +
  timedelta(days=1)` and `2026-09-03` (before item 149 landed) when fed to the
  same parser the live assertion uses — test the parser, not only the live value.
- **A placeholder outcome.** AC7 must reject each of the placeholder strings and
  a bare `accepted as rendered` with nothing else.
- **A vacuous walkthrough.** AC8's set equality must fail both directions: a
  transcript missing mode 10, and one carrying a `- Mode 11 — ` line. AC12 must
  fail if the comparison loop ran zero comparisons.
- **Determinism / immutability.** AC11's two-regeneration comparison, plus a
  check that `specification_to_dict()` called twice returns equal but not
  identical objects (the module's own determinism contract).
- **Empty and degenerate reads.** Every parse (docstring section, transcript
  section, gate row) must fail loudly on "not found" rather than passing over an
  empty match — the failure mode this stage exists to remove.

**Existing tests to reconcile — swept 2026-09-04 on `aide/queue-020`; the sweep
found nothing that breaks, and the evidence is recorded here so the next author
does not re-derive it:**

- `tests/test_114_documentation_corrections.py::test_ac8_no_new_aide_check_warning_beyond_pinned_baseline`
  — **safe.** `_GATE_DECISION_WARNING_RES` excludes every
  `^progress\.md:\d+: human gate \d+ \(` warning from the pinned baseline, so a
  new gate row adds nothing the multiset can see.
- `tests/test_145_eight_hypothesised_modes.py::test_ac24_…` and
  `tests/test_146_ninth_mode_and_first_proposed.py::test_ac36_…` — **safe, and
  deliberately so.** Both classify warnings by *shape* rather than count, and
  both carry a comment naming this item: *"item 150 raising its sign-off gate
  would turn it red for an eighth warning that is the stage working as designed"*.
  Neither needs an edit.
- `tests/test_146_ninth_mode_and_first_proposed.py::test_ac35_module_docstring_records_the_change_with_resolvable_paths`
  — **safe if the docstring edit is additive.** It requires the literal
  `item 146`, a `2026-09-0\d` date and at least one resolvable
  `src/segfacet/…\.py` path to survive. Step 9 replaces only the `Sign-off`
  section's placeholder sentence; it must not touch the item-146 record.
- Every `test_14N_*.py` committed-artifact test — **safe unless step 7 changes a
  field.** If it does, the artifacts regenerate and those tests compare against
  the regenerated copies, which is the intended behaviour; a stale committed
  artifact is what they exist to catch.
- `tests/committed_artifact_guard.py` — both `failure_modes.generated.{md,json}`
  are already allowlisted under `no-float-leaf` (item 149). No new ground, no new
  allowlist entry.

## Validation

The human review **is** this item's validation, and it cannot be performed by the
validator agent. What the validator must do instead:

1. Run `python .aide/scripts/aide.py gate list` and confirm the Stage-30 sign-off
   row reads `✅ Approved (<date>)` with a non-empty evidence note. If it reads
   `⏳ Awaiting`, the item is **not** complete: hand back, do not resolve it.
2. Run `python .aide/scripts/aide.py check` and confirm no error and no warning
   naming this gate.
3. Regenerate by hand — `.venv/bin/python -m segfacet.failure_modes --json
   <tmp>/a.json --md <tmp>/a.md` — and diff against the committed pair; the diff
   must be empty.
4. Open `docs/aide/failure_modes.generated.md` and confirm the ten `## Mode N`
   sections are present and that each one the transcript marks `changed` shows
   the changed value.
5. Read the module's `Sign-off` section and confirm the date it names is not in
   the future and matches the gate row's date, or that the transcript explains a
   divergence.

No `[validation]` environment profile is needed: nothing here requires
PyRadiomics, Docker or a GPU. The one prerequisite is a person, and its absence
is not a downgrade to `❓ Unverified` — it is the gate, and the item waits.

## Dependencies

- **Item 144** — the specification module, its schema, `main()` and the two
  generated artifacts. Merged.
- **Item 145** — the eight hypothesised modes, discriminators and per-edge
  evidence rungs. Merged.
- **Item 146** — the ninth mode and the first `proposed` entry; also the
  `Sign-off` docstring section this item fills, and the `test_ac35` docstring pin
  it must not break. Merged.
- **Item 147** — the five partial sources collapsed onto the specification.
  Merged.
- **Item 148** — the per-path mode attribution the review reads. Merged.
- **Item 149** — the traceability matrix as conformance report; the second half
  of the review pack, and the reason the review surface is current. Merged.
- Human gate 3 (`§6 failure-mode taxonomy`, ✅ Approved 2026-09-03) — its
  decision text is what holds items 139–142 pending this sign-off. Quoted here
  with its reach intact: `Blocks: items 139, 140, 141, 142`.

**Downstream:** item 151 replays Stage 30's acceptance from a clean tree and is
the only item authorised to tick this stage's acceptance criteria, including the
sign-off criterion this item makes true. Stage 20's remainder (items 139–142) is
re-queued only after this item completes.

## Decisions & Trade-offs

**D1 — this item ticks no Stage-30 acceptance criterion, and its ACs carry no
`(closes Stage 30 criterion M)` annotation.** Stage 30 has, at this item's base,
**five** recorded instances of one error class: an item's AC positionally mapped
onto a stage acceptance criterion it does not close. Four are visible as
`retracted:` entries in `aide status` (Stage 20 criteria 1, 3, 4 and 5, retracted
2026-09-02); the fifth happened during item 149, when a validator ticked Stage-30
acceptance criteria 2 and 4 on **in-tree** evidence and both were reverted
(`4502119`, `5f94b2f` on `aide/queue-020`) because both are item 151's
deliverables and item 151's queue line requires a **clean-tree** replay. Item 150
does not repeat it. Its deliverable is the gate and the recorded sign-off,
nothing more; the stage acceptance replay — including criterion 6, *"the
specification's rendering is signed off by the maintainer, with the date and
outcome recorded in the module"* — is item 151's to attest, from a clean tree,
against this item's recorded result. Per `.aide/conventions.md` §1 → `items.md`,
**an AC that names no stage criterion closes none**, and the silence above is the
answer, not an omission.

**D2 — the sign-off lives in the module docstring, not in a module constant.**
A constant (`SIGN_OFF_DATE = "…"`) would be easier to parse but would create a
second source of truth about a fact the docstring already has to state for a
human reader, and the queue line names the docstring specifically. The precedent
settles it: Stage 19 recorded its steering review in a **comment** above
`feature_docs.STATUS_OVERRIDES`, with the full transcript in item 106's spec.
This item follows the same two-place shape — a short anchored record where the
code is read, the walkthrough where specs are read — and pays for it with an
anchored regex (AC5) rather than an attribute lookup. Cost: the record is
invisible under `python -OO` (**A5**).

**D3 — AC13 is a dated claim and says so.** "Items 139–142 are still ⏸️ at the
point the gate is raised" is, by construction, a premise about a sibling's
schedule, and `.aide/conventions.md` §1 → `items.md` is explicit that such a
premise is guaranteed to become false. Two options were weighed. A *conditional*
form ("⏸️ unless the gate is approved") is durable but goes vacuous the moment
this item completes — it would pass while the claim it stands for is false, the
exact defect class Stage 30 exists to remove. The *unconditional* form asserts
something real today and breaks honestly later, so it is the one adopted, with
the hand-off written into the AC itself: the item that first lands any of 139–142
lists `tests/test_150_maintainer_sign_off.py` under **May change**. A test that
fails loudly at a known, documented moment beats one that passes forever without
meaning anything.

**D4 — the three deferred insights are review *inputs*, not this item's work.**
Insights 35, 53 and 54 in `docs/aide/insights.md` each name item 150 as the point
of decision. Acting on them is not authorised here (they are code changes to
`derive_status`, to item 148's path classification, and to the corpus scan in
`catalogue.py`); *showing them to the maintainer* is, because a sign-off taken
without them is a sign-off over a catalogue with three known open questions. If
the maintainer decides one, the decision is recorded in the transcript and the
insight is ticked with a pointer by whichever later item implements it — not
here.

**D5 — no doubled-brace template slot anywhere in this spec.** `aide check`'s
`template_residue_errors` scans every `*.md` under `docs/aide/` and reports a
a bare doubled-brace slot marker as an **error**, which would fail AC4's `errors == []`. The
to-be-filled placeholders above are written as `<angle brackets>` for that
reason.

To be updated during implementation.
