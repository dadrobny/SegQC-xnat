# Item 105 — Golden-file decision table + human sign-off

> **Created:** 2026-07-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8)
> **Queue:** [`../queue/queue-015.md`](../queue/queue-015.md) · Item 105
> *(third of four; item 103 built the catalogue this item's evidence column reads,
> item 104 guards that catalogue in CI, item 106 closes the stage)*
> **Objectives:** G7 (a committed exact-match fixture whose guarantee nobody can
> state is not a test, it is a maintenance liability — make every one of them
> reviewable, then review it), G8 (the same status discipline item 103 applies to
> features, applied to the fixtures that pin them)
> **Suggested branch:** `aide/105-golden-file-decision-table`

---

## Description

The repo commits **29 non-`.py` fixture files under `tests/`** plus a handful of
adjacent exact-match artifacts outside it, and several of them are compared
against a *fixed committed value* on every CI run. Nothing anywhere states what
each of those comparisons actually guarantees, which is the precondition for
deciding whether it is still worth its maintenance cost.

This item produces that statement: **one committed document,
`docs/aide/golden-decision-table.md`**, with one row per committed golden —
what it asserts today, which tests assert it, a **keep** or **retire**
disposition, and (for `retire`) the named guarantee that replaces it — plus a
new test module that mechanically enforces the table's completeness and
internal consistency. It delivers **no production code**, deletes **no
fixture**, and changes **no test that exists today**.

### The survey is already done — these are the rows

The queue delegated "survey `tests/` for `reports_close`/byte-identity
assertions" to this spec. It was performed on this tree (2026-07-27) and its
result is reproduced below, so the builder populates a known inventory rather
than rediscovering it. `git ls-files tests/` yields exactly 29 non-`.py` files.

**Group A — the nine whole-record report snapshots** (`tests/corpus/golden/*.json`:
`clean_control`, `mode1_displace`, `mode2_fragment`, `mode3_inject_islands`,
`mode4_relabel_swap`, `mode5_remove_level`, `mode6_crop_at_border`,
`mode7_sequence_break`, `mode8_force_overlap`). Each is the full
`segfacet run` JSON report — verdict, findings, **and the entire features block**
— for one Stage-5 corpus case, produced by `synth/golden.py::write_goldens` and
compared fresh-vs-committed within `reports_close` numeric tolerance. Asserted by
**six** test modules, not one:

| Module | What it uses the goldens for |
|---|---|
| `tests/test_042_golden_determinism.py` | owner (item 042): AC6 one-golden-per-case, AC7 schema validity, AC8 stem↔`case_id`, AC9 `check_case_golden`, AC13 regeneration-vs-committed, AC16 the pipeline-blind fact for the reconstructed-record cases, plus 3 adversarial tests |
| `tests/test_089_fov_aware_coverage_border.py` | `test_ac16_committed_corpus_coverage_and_border_findings_unchanged` — FOV rework changed no coverage/border finding |
| `tests/test_090_reference_derived_defaults.py` | `test_ac15_all_committed_goldens_still_check_true` — reference-derived defaults changed no report |
| `tests/test_094_tptbox_image_layer.py` | `test_ac7_report_matches_committed_golden_within_tolerance` — the goldens *are* the pre-TPTBox-migration snapshot |
| `tests/test_098_stray_components.py` | AC14 (every golden's components block), AC15 (`test_ac15_golden_verdict_and_findings_unchanged`), AC16 (`write_goldens` intra-run + vs-committed) |
| `tests/test_099_per_mode_metrics.py` | `test_ac25_committed_goldens_byte_identical_to_pre_099_state` — a scope fence, not a semantic use |

**Group B — corpus inputs and their indices, byte-identical to regeneration:**
`tests/corpus/manifest.json`, `tests/corpus/fixtures/*.nii.gz` (10 files:
`base_scan` + nine `*_seg`), `tests/corpus/intensity/manifest.json`,
`tests/corpus/intensity/fixtures/*.nii.gz` (5 files). Asserted by
`tests/test_040_synthetic_corpus.py` and `tests/test_058_intensity_fixtures.py`
(`read_bytes()` regenerated-vs-committed *and* regenerated-twice), and read by
`tests/test_094_tptbox_image_layer.py`'s AC3 loader snapshot.

**Group C — the loader-invariance snapshot:**
`tests/corpus/094_pre_migration_snapshot.json` — per fixture,
`{shape, dtype, sha256(data.tobytes()), spacing, affine}` as produced by the
**pre-TPTBox** `io.load_volume`. Asserted by `tests/test_094_tptbox_image_layer.py`
AC3.

**Group D — the report-formatting goldens:** `tests/golden/016_features_report.json`
(`test_016_features_json.py::test_ac5_golden_snapshot`) and
`tests/golden/022_stage3_report.json`
(`test_022_stage3_serialisation.py::test_ac8_golden_snapshot`). Both compare
`serialize_report_json(...)`'s output against the committed file **as text**
(`read_text`, so universal-newline translation applies and the missing
`.gitattributes` LF pin is not currently load-bearing — see Assumptions).

**Adjacent exact-match artifacts outside `tests/`** — omitting them would make the
table misleading, so they get their own section: `src/segfacet/reference/reference_default.json`
(regenerated-vs-committed via `reports_close`, `test_045` AC10 / `test_081` /
sha256-pinned by `test_093`), `src/segfacet/reference/reference_verse_v1.json`
(sha256-pinned by `test_098` AC18; built from mounted VerSe GT and **not**
regenerable in CI), the three JSON schemas (`report_schema_v0.json`,
`eval/eval_report_schema_v0.json`, `eval/per_mode_comparison_schema_v0.json`),
and item 103's `docs/aide/feature_catalogue.generated.{json,md}` (byte-identity
vs regeneration, item 103 AC19).

**In-module frozen snapshots** — committed exact-match expectations that are not
files: `test_098`'s `_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS` and
`_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` (the latter imported by `test_102`), and
the `_PRE_NNN_*` sha256 scope-fence constants in tests 093/098/099/100/101/102.
They get a short narrative section, not rows.

### Why item 103's catalogue is the evidence, not decoration

The roadmap's retire argument is that a whole-record snapshot cannot survive a
feature retune. Item 103 turns that from an argument into a **measurement**: its
spec records that of the **67** schema-level leaf paths in a realised record,
roughly **34 are read by nothing at all** (`stage3.spacing_consistency.*`,
`stage3.curvature.*`, every `bbox_voxel`/`bbox_physical` corner, `centroid_voxel`,
three of item 098's four stray-component fields). Each of the nine goldens pins
*all* of them. So about half of each golden's content asserts values no rule,
no metric and no vocabulary consumes — and the moment Stage 19/20 authorises a
`retune` or `retire` on any of those, all nine regenerate wholesale and the diff
can no longer separate the intended change from a regression.

This item therefore requires the **measured** unwired fraction per golden, taken
from the committed catalogue at execution time (`AC7`), rather than repeating
item 103's prototype number as an estimate.

### What this item is NOT

- **It does not act on any retire decision.** No golden file is deleted,
  regenerated, moved or replaced; no test that consumes one is edited or
  deleted; no `.gitattributes` entry is added or changed. Acting on the
  decision is **Stage 21's** deliverable (`roadmap.md:829`, "Act on Stage 19's
  golden decision"). Stage 19 decides, Stage 21 executes. This is a hard fence
  (AC14), and a builder that "helpfully" retires a golden has broken the item.
- **It does not make the keep/retire call by fiat.** The dispositions the
  builder populates are the **draft** this item exists to put in front of a
  human. The maintainer's call is made when this item is *executed*, against
  the populated table (see Validation).
- **It does not invent a sign-off mechanism.** The attestation that a human
  reviewed and agreed the table is `progress.md`'s Stage-19 third acceptance
  checkbox and nothing else (AC11/AC12).
- **It is not the catalogue** (item 103), **not the drift test** (item 104), and
  **not the stage validation** (item 106).
- **It adds nothing under `src/segfacet/`.** The deliverables are one document
  and one test module.

## Acceptance Criteria

- [ ] **AC1: the document exists with the mandated section structure.**
  `docs/aide/golden-decision-table.md` exists and contains, in this order, the
  level-2 headings `## Section 1 — Committed test fixtures`,
  `## Section 2 — Adjacent exact-match artifacts (outside tests/)`,
  `## Section 3 — In-module frozen snapshots`,
  `## Not about byte reproducibility`, and
  `## Divergences from the roadmap's working assumption`. Written with
  `write_bytes` and `\n` newlines.

- [ ] **AC2: Section 1's table carries exactly the mandated columns, in order.**
  The first pipe-table under the Section 1 heading has the header row
  `| fixture | what it asserts today | asserted by | evidence | disposition | replacement guarantee |`
  (case- and whitespace-normalised), and no other columns.

- [ ] **AC3: Section 1 enumerates every committed test fixture exactly once — no
  omissions, no inventions.** The set of `fixture` cell values in Section 1
  equals, in **both** directions, the set of repo-relative POSIX paths found by
  walking `tests/` for files whose suffix is not `.py`, excluding
  `__pycache__/` and `.pytest_cache/`. No path appears in two rows. On the
  current tree that set has **29** members.

- [ ] **AC4: every Section-1 disposition is from the fixed two-word vocabulary.**
  Every row's `disposition` cell is exactly `keep` or exactly `retire` — never
  empty, never hedged, never a third value.

- [ ] **AC5: `retire` rows name a replacement and `keep` rows do not.** Every row
  whose disposition is `retire` has a `replacement guarantee` cell that is
  non-empty, is not `—`, and names at least one concrete artifact — a test
  module path, a test function name, or a roadmap stage — rather than prose
  alone. Every row whose disposition is `keep` has `—` in that cell.

- [ ] **AC6: every row's `asserted by` cell resolves to real tests.** Each
  `asserted by` cell names at least one `tests/test_*.py` module, and every
  module path named anywhere in Section 1 exists on disk. Every `::`-qualified
  test function named in a cell is present in that module's source.

- [ ] **AC7: the nine corpus-golden rows carry a *measured* unwired fraction.**
  Each of the nine `tests/corpus/golden/*.json` rows has an `evidence` cell
  matching `N/M leaf paths unwired` (two integers, `0 <= N <= M`, `M > 0`), and
  for every one of them those two integers equal the values recomputed at test
  time: `M` is the number of distinct `normalise_leaf_path` values in that
  golden's `features` block, and `N` is how many of those match a
  `build_catalogue()` entry whose `status == "unwired"`. Both are obtained
  through `segfacet.catalogue`'s public API — never a second copy of the walk,
  never a hand-typed number.

- [ ] **AC8: the byte-reproducibility disclaimer names the assertions that
  survive.** The `## Not about byte reproducibility` section states that a
  `retire` disposition does not weaken intra-run determinism, cites
  `src/segfacet/synth/golden.py`, and names by fully-qualified id at least
  these three surviving determinism assertions:
  `tests/test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical`,
  `tests/test_042_golden_determinism.py::test_ac12_main_regenerates_matching_goldens`,
  `tests/test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism`.
  Every id it names resolves to a real test function.

- [ ] **AC9: Section 2 covers every adjacent artifact by name.** Section 2's
  table uses the same six columns as Section 1 and contains exactly one row for
  each of: `src/segfacet/reference/reference_default.json`,
  `src/segfacet/reference/reference_verse_v1.json`,
  `src/segfacet/report_schema_v0.json`,
  `src/segfacet/eval/eval_report_schema_v0.json`,
  `src/segfacet/eval/per_mode_comparison_schema_v0.json`,
  `docs/aide/feature_catalogue.generated.json`,
  `docs/aide/feature_catalogue.generated.md` — and no other rows. Each row obeys
  AC4/AC5/AC6.

- [ ] **AC10: Section 3 names the in-module frozen snapshots.** Section 3's prose
  names the identifiers `_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS`,
  `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`, states that `tests/test_102_stage18_validation.py`
  imports the latter, and states one blanket disposition for the `_PRE_NNN_*`
  sha256 scope-fence constants. Every identifier it names is present in the
  source of the module it attributes it to.

- [ ] **AC11: the document declares `progress.md` as the sole attestation and
  carries no sign-off field of its own.** The document contains the literal
  string `progress.md` in a sentence naming Stage 19's acceptance checkbox as
  the attestation, and its source contains **no** line matching (case-insensitive)
  `^\s*(\*\*)?(signed[- ]off|sign[- ]off|approved by|reviewer|signature)\b` —
  the table records dispositions, not approvals.

- [ ] **AC12: `progress.md`'s Stage-19 sign-off checkbox is either honestly
  unticked or ticked with evidence.** In `docs/aide/progress.md`'s Stage 19
  `**Acceptance.**` list, the item whose text contains
  `golden decision table is complete and signed off` is either (a) `- [ ]` and
  carries no italic `*(...)*` evidence note, or (b) `- [x]` and carries an
  italic evidence note naming `golden-decision-table.md`. A ticked box without
  that evidence note fails.

- [ ] **AC13: divergences from the roadmap's assumption are itemised, not
  buried.** The `## Divergences from the roadmap's working assumption` section
  contains one bullet for **every** Section-1 and Section-2 row whose
  disposition is `keep`, each naming that row's fixture path and giving a
  reason. The set of fixture paths named there equals the set of `keep` rows,
  in both directions.

- [ ] **AC14: the scope fence holds — nothing is retired here.** This item adds,
  deletes or modifies no file under `tests/corpus/**` and no file under
  `src/segfacet/**` (asserted by pinned digests, computed over
  `Path.relative_to(base).as_posix()`, of the `tests/corpus/**` and
  `src/segfacet/**` trees), and adds, deletes or modifies no file under
  `tests/golden/**` (asserted by name set plus a **text**-normalised digest —
  see the Testing Strategy note on why bytes are the wrong comparison there).
  `.gitattributes` is byte-unchanged. The only files this item creates are
  `docs/aide/golden-decision-table.md` and `tests/test_105_golden_decision_table.py`;
  the only file it may otherwise edit is the single `progress.md` line covered
  by AC12.

## Assumptions

Clarify mode for this item was **`interactive`** (Stage 19 carries the human
steering checkpoint). Two questions were answered directly by the maintainer
before authoring and are recorded here as **settled decisions, not
assumptions**; the rest are spec-author defaults.

**Settled by the maintainer (do not re-litigate):**

- **The keep/retire call on the nine corpus goldens is deferred to execution
  time.** The roadmap's tentative "retire most" (`roadmap.md:748-755`) is what
  the builder populates as the **draft** disposition for Group A. The actual
  decision is made by the human maintainer when this item is *executed*, against
  the populated table — not now, during spec authoring, and not by the builder
  on its own authority. This item's deliverable is a correctly-populated draft
  plus the mechanism that captures the decision.
- **Sign-off is recorded as the `progress.md` acceptance checkbox — and nothing
  else.** Stage 19's `**Acceptance.**` list already carries three unticked
  boxes; the third, *"The golden decision table is complete and signed off by
  the human reviewer"*, **is** the sign-off record. No second sign-off file, no
  per-row approval column, no signature block in the table. The table carries
  dispositions; the checkbox carries the attestation. (Verified against the
  repo's history: `grep`ping `progress.md` for sign-off/reviewed language
  returns exactly that one line — there is no prior acceptance-sign-off
  convention to imitate, and `aide progress set` handles only deliverable rows
  (`in-progress|done`), not acceptance checkboxes, so the tick is a plain edit
  to that one line with an italic evidence note, exactly as Stage 18's ticked
  acceptance items are annotated.)

**Spec-author defaults:**

- **Who ticks the box, and what happens if the human does not approve.** The
  tick happens **within item 105's execution**, immediately after the maintainer
  gives explicit approval at the Validation step — not in item 106. Item 106's
  own spec text requires it to *confirm sign-off was recorded before it
  proceeds* and to stop if it is pending, which is only non-circular if the
  record predates it. If approval is **not** granted, the item still lands: the
  table ships with its draft dispositions, the checkbox stays `- [ ]`, and the
  item reports "sign-off pending" — after which item 106 stops, exactly as its
  spec requires. **Nothing may tick that box without an explicit human
  statement of approval in the session transcript.** AC12 is written to pass in
  both states precisely so the honest outcome is never the failing one.
- **"Committed golden" is scoped to committed *non-`.py` files under `tests/`.**
  That is the mechanically checkable definition (AC3) and it matches
  `git ls-files tests/` exactly on this tree (29 files). Artifacts outside
  `tests/` that are nonetheless compared against a fixed committed value get
  Section 2 by enumeration (AC9) rather than by walk, so the completeness check
  stays deterministic and does not couple to unrelated trees.
- **AC3 walks the filesystem, not `git ls-files`.** No subprocess, no git
  dependency, no skip path. The cost is that an untracked scratch `.json`
  someone leaves under `tests/` fails the test — which is the correct alarm,
  since an undocumented fixture appearing under `tests/` is precisely what this
  table exists to catch.
- **AC7 reads item 103's Python API, not its JSON.** Item 103 pins
  `normalise_leaf_path`, `iter_leaf_paths`, `build_catalogue`, and
  `CatalogueEntry.status`'s four-value vocabulary as public surface (its AC1,
  AC3, AC7), but its spec does **not** fix `catalogue_to_dict`'s serialised
  layout — item 104's spec records the same gap. So this item's test calls
  `build_catalogue()` and reads `entry.path` / `entry.status` directly. If the
  builder finds that surface differs from item 103's spec, **hand back** rather
  than adapting silently.
- **Group D's missing LF pin is noted, not fixed.** `tests/golden/*.json` are
  absent from `.gitattributes` while every other committed text fixture is
  pinned. They are compared with `read_text` (universal newlines), so this is
  latent rather than live — but it is exactly the bug class this repo has been
  burnt by three times (`insights.md`, items 099-101). Fixing it would mean
  editing `.gitattributes`, which AC14 forbids; it is recorded in the table's
  Group D rows as a caveat and logged to `insights.md` for the queue-boundary
  triage instead.
- **`tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot` self-heals
  and that weakens its own golden.** If `tests/golden/022_stage3_report.json` is
  absent the test *writes it and skips* — so deleting that golden makes the
  check pass rather than fail. This materially affects that row's "what it
  asserts today" cell (the honest answer is "drift, but only while the file
  happens to exist") and it is logged to `insights.md`. Fixing the test is out
  of scope (AC14 forbids editing it).
- **Item 103 has landed and its catalogue artifacts are committed.** AC7 and
  Section 2's last two rows both require `docs/aide/feature_catalogue.generated.json`
  and `.md` to exist. Item 103 is a hard blocker; if its artifacts are absent
  when this item is claimed, hand back rather than stubbing the evidence column.

## Implementation Steps

There is **no** production change under `source_dir`. The builder writes one
document and the test-writer writes one test module.

1. **Recompute the inventory before populating anything.** Walk `tests/` for
   non-`.py` files (the AC3 rule) and confirm the 29-file set matches the
   Description's survey. If the tree has moved on — a new fixture landed, one
   was renamed — the table gets the *current* set; the Description's list is
   the survey's snapshot, not a hard-coded expectation.

2. **Measure the evidence column** (AC7). For each of the nine
   `tests/corpus/golden/*.json`: parse it, take its `features` block, run it
   through `segfacet.catalogue.iter_leaf_paths` (or `normalise_leaf_path` over a
   local walk of that block if `iter_leaf_paths` expects a full record — pin
   whichever is correct in Decisions & Trade-offs), and intersect the resulting
   path set with `build_catalogue()`'s entries to count how many carry
   `status == "unwired"`. Record `N/M leaf paths unwired` verbatim in the cell.
   Expect roughly half (item 103's prototype measured ~34 of 67); a near-zero
   `N` means the catalogue's attribution is over-matching, not that the goldens
   are healthy — say so rather than recording a number you do not believe.

3. **Write `docs/aide/golden-decision-table.md`.** Header: what the document is,
   who decides, the one-sentence pointer to `progress.md`'s Stage-19 acceptance
   checkbox as the attestation (AC11), and an explicit "Stage 19 decides,
   Stage 21 executes" line citing `roadmap.md:829`. Then the five mandated
   sections (AC1). Populate Section 1's rows from the survey:

   - **Group A (nine goldens) — draft `retire`,** per `roadmap.md:748-755`. Each
     row's `what it asserts today` must be specific ("the full `segfacet run`
     report — verdict, findings and all N features leaf paths — for case X,
     compared within `reports_close` tolerance"), and each row's
     `replacement guarantee` must name what actually takes over: (i) intra-run
     determinism is already independent (AC8's three assertions); (ii) schema
     validity moves to validating a *freshly built* report against
     `report_schema_v0.json` (`test_042` AC7's check re-pointed at
     `build_report_for_case` output); (iii) the load-bearing
     "verdict/findings unchanged by refactor X" use — which is what
     `test_089`/`test_090`/`test_094`/`test_098` actually exercise — moves to a
     **narrow verdict+findings expectation** of the
     `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS` shape, which survives a feature
     retune because it pins no feature values; (iv) Stage 21's real-GT corpus
     plus Stage 20's specificity ratchet. Record explicitly, per
     `roadmap.md`'s Stage 21 deliverable, that the nine are **not** to be
     regenerated against the new corpus.
   - Note in the three rows for `mode1_displace`, `mode4_relabel_swap`,
     `mode8_force_overlap` that `test_042` AC16 pins them as *pipeline-blind*
     (`verdict == "pass"`, no designated rule fires) — their snapshot's content
     is the documented Stage-20 reachability hole, which strengthens the retire
     case for those three specifically.
   - **Group B (16 corpus/intensity inputs + indices) — draft `keep`.** Reason
     for the divergence: they are *inputs*, not report snapshots; their
     assertion is generator reproducibility (`read_bytes` regenerated-vs-committed
     *and* regenerated-twice), which a feature retune cannot invalidate; and
     `roadmap.md`'s Stage 21 rung table explicitly **retains** rung-1 fixtures
     "for fast unit tests only".
   - **Group C (`094_pre_migration_snapshot.json`) — draft `keep`.** It snapshots
     *loaded arrays* (shape/dtype/sha256/spacing/affine), not computed features,
     so it is invariant under every retune this stage or Stage 20 authorises,
     and it remains a live ratchet on any future `io.load_volume` change — not
     merely a discharged one-shot migration fence.
   - **Group D (`tests/golden/016_*`, `022_*`) — draft `keep`,** confirming the
     roadmap's "report-formatting goldens are the likely survivors" guess *with
     the caveat the queue asked for*: both are built from **computed** blocks
     (`_features_for_case`, `_full_block_for_spine`), so a feature retune does
     force their regeneration too — they are only partly formatting goldens.
     Record the honest narrowing (the guarantee worth keeping is key ordering /
     key set / float formatting of `serialize_report_json`, which would be
     better expressed structurally) plus the two caveats from Assumptions (no
     LF pin; `test_022`'s self-healing branch).

4. **Populate Section 2** by enumeration (AC9), with the six columns and the
   same disposition discipline: `reference_default.json` — `keep` (shipped data
   with a live regenerated-vs-committed guarantee); `reference_verse_v1.json` —
   `keep` (unregenerable in CI, so its sha256 pin is the *only* thing standing
   between it and silent corruption); the three schemas — `keep` (validation
   contracts, the roadmap's named survivors); item 103's two generated artifacts
   — `keep` (generated-document determinism, structurally like the corpus
   manifest, not a whole-record snapshot).

5. **Write Section 3** (AC10) as prose: the two `_PRE_098_*` constants, the
   `test_102` import of one of them, and a blanket disposition for the
   `_PRE_NNN_*` sha256 scope fences — `keep`, with a pointer to the open
   `insights.md` entry (item 101) about the missing convention for updating a
   superseded pin when a later item is legitimately authorised to touch the
   same file.

6. **Write the two remaining sections** — `## Not about byte reproducibility`
   (AC8) and `## Divergences from the roadmap's working assumption` (AC13, one
   bullet per `keep` row).

7. **Do NOT touch** any file under `tests/corpus/**`, `tests/golden/**`,
   `src/segfacet/**`, or `.gitattributes` (AC14). Do not delete, regenerate or
   move a golden. Do not edit any test that consumes one.

8. **Append the two out-of-scope findings to `docs/aide/insights.md`** (the
   missing `tests/golden/*.json` LF pin; `test_022`'s self-healing golden
   branch) — one line each, then carry on.

9. **At the Validation step, present the table and capture the decision.** Only
   on explicit human approval, edit the single `progress.md` Stage-19 acceptance
   line to `- [x]` with an italic evidence note naming
   `golden-decision-table.md` and the date (AC12). Without approval, leave it
   `- [ ]` and report sign-off as pending.

## Testing Strategy

- **Framework:** `pytest`. One new module, `tests/test_105_golden_decision_table.py`.
  **No existing test module is modified.**

- **The parser is the module's own foundation.** A ~25-line helper splits a
  fenced section's first pipe table into `list[dict[str, str]]` keyed by the
  normalised header cells, stripping outer pipes and surrounding whitespace and
  ignoring the `|---|` separator row. Every structural AC (AC2-AC7, AC9, AC13)
  runs off that one parse; a malformed table must fail with a message naming the
  offending line, not an `IndexError`.

- **One focused test per AC**, AC1-AC14. The load-bearing ones:
  - **AC3** — the both-directions set comparison against the filesystem walk,
    with a failure message that lists the missing and the extra paths
    separately. This is the "no omissions" guarantee the queue asks for; a bare
    `assert set_a == set_b` is not acceptable.
  - **AC7** — the recomputation. This is the only AC that executes production
    code (`segfacet.catalogue`), and it is what makes the evidence column
    trustworthy rather than transcribed.
  - **AC12** — must pass in both the ticked and unticked states, and fail only
    on a tick without evidence. Write it as an explicit three-branch test, not
    as an `if ticked: assert ...` that silently no-ops.
  - **AC14** — the scope fence; see the platform note below.

- **Adversarial / edge cases:**
  - A row whose `disposition` cell has stray whitespace or a trailing period →
    AC4 fails (the vocabulary is exact after `.strip()`, nothing else).
  - A `retire` row whose replacement cell is `—` or `TBD` or `see above` → AC5
    fails (it must name a module, a test id, or a stage).
  - A duplicated fixture path across two rows → AC3 fails on the duplicate, not
    silently passing because the *sets* still match.
  - An `asserted by` cell naming a module that does not exist, or a `::`
    function absent from the module it names → AC6 fails naming the offender.
  - An `evidence` cell of the form `34/67` without the trailing words, or with
    `N > M` → AC7 fails on the format before it fails on the arithmetic.
  - The document containing a `**Signed off:**` line → AC11 fails (this is the
    regression guard for "do not invent a second sign-off mechanism").
  - `## Divergences ...` naming a fixture that is `retire`, or omitting one that
    is `keep` → AC13 fails in the corresponding direction.
  - Section 1 table present but empty (header row only) → AC3 fails with the
    full missing list rather than trivially passing on two empty sets.

- **Platform hygiene for AC14's scope fence** — this repo has been bitten
  **three times** by byte-hash scope-fence tests (`insights.md`, items 099-101).
  Before writing it: (a) resolve every path from `Path(__file__)`, never an
  absolute literal; (b) hash `Path.relative_to(base).as_posix()`, never
  `str(path)`; (c) only byte-hash files that are already LF-pinned in
  `.gitattributes` — `tests/corpus/**` and `src/segfacet/**` are pinned, so
  bytes are safe there, but **`tests/golden/*.json` is not pinned**, so that
  part of the fence must compare the *name set* plus a digest over
  `read_text(encoding="utf-8")` output (universal-newline normalised), and must
  carry an inline comment saying why. Getting this wrong reproduces a bug that
  is invisible to every gate this loop runs and only surfaces from a human
  reading the Actions tab.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate). This item deletes nothing and edits no test, so the sweep is
  expected to be inert — but confirm rather than assume:
  - `tests/test_042_golden_determinism.py`, `tests/test_089_fov_aware_coverage_border.py`,
    `tests/test_090_reference_derived_defaults.py`, `tests/test_094_tptbox_image_layer.py`,
    `tests/test_098_stray_components.py` — all consume the nine goldens and must
    stay green **unmodified**. Any edit to them is a scope violation, not a fix.
  - `tests/test_099_per_mode_metrics.py::test_ac25_committed_goldens_byte_identical_to_pre_099_state`
    and `tests/test_102_stage18_validation.py`'s `_PRE_ITEM_HASHES` fence — both
    pin committed trees this item must not touch; they are the early-warning
    signal if AC14 is violated.
  - `tests/test_040_synthetic_corpus.py`, `tests/test_058_intensity_fixtures.py`
    — the Group B regeneration checks; read-only here.
  - `tests/test_016_features_json.py`, `tests/test_022_stage3_serialisation.py`
    — Group D; this item documents their weaknesses and fixes neither.
  - `tests/test_103_feature_catalogue.py`, `tests/test_104_feature_catalogue_drift.py`
    — AC7 imports `segfacet.catalogue` read-only; neither module is touched and
    both must stay green.
  - Any test asserting on `progress.md`'s contents (grep `progress.md` under
    `tests/`) — AC12 edits one line there conditionally; if such a test exists
    it must be reconciled *before* the tick, not after.

## Validation

The point of this item is a document a **human decides on**, so the validation
*is* the steering checkpoint. It cannot be delegated to the suite and it must
not be simulated. From the repo root with the venv bootstrapped:

1. Confirm the mechanical layer first:
   ```
   .venv/bin/python -m pytest tests/test_105_golden_decision_table.py -v
   ```
   All fourteen AC tests green. AC12 will be green in its *unticked* branch at
   this point — that is expected.

2. Read `docs/aide/golden-decision-table.md` end to end and check three things
   by inspection: every row's `what it asserts today` cell says something a
   reader could act on (not "snapshot of case X"); the nine `evidence` cells
   carry plausible measured fractions (roughly half unwired — a near-zero
   figure means over-matching attribution, not healthy goldens); and every
   `retire` row's replacement is something that actually exists or is a named
   future stage deliverable.

3. **Present the table to the maintainer and obtain an explicit decision, row by
   row for Group A** — the nine corpus goldens — and as a block for Groups B/C/D
   and Section 2. Show the measured unwired fractions and the six-module
   consumer list, because those are the two facts the decision turns on. Ask
   directly whether each Group-A golden is `keep` or `retire`; do not read
   approval into silence, into a "looks good", or into the absence of an
   objection.

4. On explicit approval: update any dispositions the maintainer changed, then
   tick `progress.md`'s Stage-19 third acceptance checkbox with an italic
   evidence note naming this document and the date. Re-run step 1 — AC12 now
   passes in its *ticked* branch. Commit both edits together.

5. If approval is **not** given (deferred, partial, or the maintainer wants
   changes first): land the table as-is, leave the checkbox `- [ ]`, and report
   "sign-off pending" explicitly in the item's hand-back. Item 106 will then
   stop, which is the correct outcome — a fabricated tick is the one failure
   mode this stage exists to prevent.

No `[validation]` profile is required: everything runs on the plain CPU venv
with no optional dependency. If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified. The one thing that *can* leave this item incomplete is the
absence of a human, and the honest record for that is a pending checkbox, never
a downgraded pass.

## Dependencies

- **Item 103** (`segfacet.catalogue`'s `build_catalogue` / `iter_leaf_paths` /
  `normalise_leaf_path` and `CatalogueEntry.status`, plus the committed
  `docs/aide/feature_catalogue.generated.{json,md}` that Section 2 rows) — the
  hard blocker: AC7's measured evidence column and two Section-2 rows cannot be
  produced without it.
- **Item 042** (`synth/golden.py` — the nine goldens, `write_goldens`,
  `check_case_golden`, `reports_close`, and the determinism assertions AC8
  names) — ✅.
- **Item 040** (the synthetic corpus, its manifest and fixtures — Group B) — ✅.
- **Item 058** (the Stage-8 intensity corpus and its byte-identity checks —
  Group B) — ✅.
- **Item 094** (`094_pre_migration_snapshot.json` — Group C) — ✅.
- **Items 078 / 081 / 098** (the `reports_close` tolerance policy, the reference
  artifact's regenerated-vs-committed comparison, and the
  `_PRE_098_*` frozen-snapshot pattern this item names as the Group-A
  replacement guarantee) — ✅.

**Downstream:** item 106 (stage validation) reads this table's sign-off state
and must stop if it is pending; Stage 21 (`roadmap.md:829`) is what actually
executes any `retire` disposition recorded here. Neither blocks this item.

## Decisions & Trade-offs

To be updated during implementation. Recorded by the spec author where the queue
delegated the choice:

- **One hand-authored Markdown document with a machine-checked table, not a
  generator.** Item 103's generate-then-render pattern is right for a catalogue
  that must track a moving record shape; this table is a one-time judgment
  document whose *inventory* moves rarely and whose *dispositions* are by
  definition not derivable from code. So the completeness and consistency are
  enforced mechanically (AC3, AC5-AC7, AC13) while the content stays authored —
  the drift risk is closed without building a generator for prose.
- **The evidence column is recomputed at test time, not transcribed.** AC7 is
  the only place this item touches production code, and it exists so that the
  single number the retire decision leans on cannot be a stale estimate copied
  from item 103's spec.
- **Section 2 is enumerated, Section 1 is walked.** A walk of `tests/` is
  deterministic and self-maintaining; a walk of the whole repo for
  "exact-match-compared artifacts" is not decidable without executing the suite.
  Enumerating the seven adjacent artifacts keeps the table honest without making
  the completeness AC undecidable.
- **`keep` / `retire` only — no `retune`, no `defer`.** Item 103's four-value
  status vocabulary is about *features*; a fixture is either still earning its
  maintenance cost or it is not. A third value would let a row avoid making the
  call, which is the failure mode this stage exists to prevent. Where the
  disposition depends on later work (Group A depends on Stage 20/21 landing the
  replacements), that dependency lives in the `replacement guarantee` cell, not
  in a hedged disposition.
- **The attestation lives in exactly one place.** Putting a `Signed off by / on`
  block in the table too would create two records that can disagree, and the
  first time they did, neither would be trustworthy. AC11 actively forbids it.
- **Two survey findings are logged, not fixed** — the missing
  `tests/golden/*.json` LF pin and `test_022_stage3_serialisation.py`'s
  self-healing golden branch. Both are real, both are one-line fixes, and both
  are outside a fence the maintainer set deliberately. They go to
  `insights.md` for triage at the queue boundary.
