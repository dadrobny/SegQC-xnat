# Item 128 — Relocate the `reference_verse_v1` integrity pin and rename the `test_102` fence header

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 128
> **Objectives:** G7 (evaluable & regression-testable — test-artifact hygiene)
> **Suggested branch:** `aide/128-relocate-the-reference-verse-v1`

---

## Description

Two located test-hygiene defects, routed 2026-08-25 and scoped as Stage 29 **D3**.
Both are cases of a test whose *name* describes a bygone item's scope fence while
its *body* asserts a durable invariant, so a reader learns the wrong thing about
what would break if it went red.

**1. The `reference_verse_v1` integrity pin lives under an item-098 name.**
`tests/test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged`
sha256-pins `src/segfacet/reference/reference_verse_v1.json`. The invariant is
legitimate and load-bearing — that artifact is built from mounted VerSe19 ground
truth, is **not regenerable in CI**, and the digest is the only thing standing
between it and silent corruption
([`../golden-decision-table.md`](../golden-decision-table.md) Section 2 row,
disposition `keep`). But it is named for item 098's scope fence, sits at the
bottom of a 1200-line module about stray connected components, and its docstring
says "byte-identical to its **pre-098** state" — a claim item 123 already
falsified when it rebuilt the artifact and moved the digest. Relocate the pin to
a module named for the artifact, beside `reference/artifact.py`'s own tests, with
its real purpose in the docstring.

**2. `tests/test_102_stage18_validation.py`'s `# AC24: the scope fence -- no
production code changed by this item` header sits over an intra-run
non-mutation check.** `test_ac24_src_tree_is_byte_identical_across_the_test_run`
hashes `src/segfacet/**` at module-collection time and again during the test: it
detects a test run that mutates production source, and can say nothing whatever
about what item 102 did or did not change. Renaming the header (and correcting
the docstring's "pre-102 state" claim) to name the property actually checked is
the whole fix — the assertion is correct and stays exactly as it is.

**Carrying the `.gitattributes` pin across is a deliberate act, not an
inference.** Engine 1.19.0's `aide check` lint resolves a fixture path through
the test's AST and skips in silence anything it cannot resolve — and the current
pin reaches the artifact through `bundled_production_reference_path()`, a plain
function call. So the lint is silent today and would be equally silent if the
relocation dropped the pin (see [`CLAUDE.md`](../../../CLAUDE.md) Gotchas). This
item therefore (a) asserts `.gitattributes` coverage explicitly via
`git check-attr`, and (b) resolves the artifact in the new module from a
repo-root-relative literal path so both the lint and item 127's
`tests/committed_artifact_guard.py` classifier can *see* the comparison instead
of skipping it. Silence stops being the answer.

**What this is NOT.** No production code changes: nothing under `src/segfacet/**`
is touched, and `reference_verse_v1.json`'s bytes must not move (the pin is the
proof). No new invariant is introduced and none is retired — the digest literal
is carried across verbatim. `test_102`'s assertion is not rewritten, only its
comment and docstring. The item does not tick, untick or reword any acceptance
box in `progress.md`.

## Acceptance Criteria

- [ ] **AC1: the pin has a module named for the artifact.**
  `tests/test_128_reference_verse_v1_integrity.py` exists, and its module
  docstring states that it guards `src/segfacet/reference/reference_verse_v1.json`
  against silent change, naming both that the artifact is a released production
  artifact and that it is not regenerable in CI.

- [ ] **AC2: the pin's identifiers say what they protect.** The new module
  defines the digest as `_RELEASED_REFERENCE_VERSE_V1_SHA256`, and no identifier
  defined in the module contains `PRE_098`, `pre_098` or `ac18`.

- [ ] **AC3: the digest literal is carried across verbatim.**
  `_RELEASED_REFERENCE_VERSE_V1_SHA256` equals
  `2048804f60208a4dea0cbe8d0980e1e6228c68b52b6331375f768254fc73b5da` — the value
  `test_098` carried at spec time.

- [ ] **AC4: the pin holds against the committed artifact.** The sha256 of
  `src/segfacet/reference/reference_verse_v1.json`'s bytes equals
  `_RELEASED_REFERENCE_VERSE_V1_SHA256`.

- [ ] **AC5: the pin still fails when a byte of the artifact changes.** Given a
  copy of the artifact with exactly one byte altered, the module's digest
  computation yields a value that is **not** equal to
  `_RELEASED_REFERENCE_VERSE_V1_SHA256`.

- [ ] **AC6: the comparison is statically visible to item 127's classifier.**
  With `committed_artifact_guard.ALLOWLIST` replaced by an empty tuple,
  `classify_module` on the new module's source reports at least one violation
  whose `committed_path` is exactly
  `src/segfacet/reference/reference_verse_v1.json` — i.e. the pin is reached
  through a resolvable repo-root-relative literal path, not skipped in silence
  behind a helper call.

- [ ] **AC7: the pin covers the artifact the package actually ships.**
  `bundled_production_reference_path().resolve()` equals the resolved
  repo-root-relative path the new module pins.

- [ ] **AC8: the load-and-score companion moves with the pin.** The new module
  contains a test that loads the artifact via the public reference API and scores
  the `mode6_crop_at_border` corpus case through `run_qc_with_reference`,
  asserting at least one `bounds` finding carrying label 22.

- [ ] **AC9: `test_098` no longer defines the pin.**
  `tests/test_098_stray_components.py` defines neither
  `_PRE_098_REFERENCE_VERSE_V1_SHA256` nor
  `test_ac18_reference_verse_v1_bytes_unchanged` nor
  `test_ac18_reference_verse_v1_still_loads_and_scores_a_case`.

- [ ] **AC10: the old identifier is gone from the whole test tree.** No `*.py`
  file under `tests/` contains the string `_PRE_098_REFERENCE_VERSE_V1_SHA256`.

- [ ] **AC11: `test_098`'s docstring points at the new home.** The AC18 bullet in
  `tests/test_098_stray_components.py`'s module docstring no longer claims the
  module carries the `reference_verse_v1.json` byte pin, and names
  `tests/test_128_reference_verse_v1_integrity.py` as where it now lives.

- [ ] **AC12: item 123's reconciliation test follows the pin.**
  `tests/test_123_recalibrate_and_regenerate.py` imports the recorded digest from
  `test_128_reference_verse_v1_integrity` and not from
  `test_098_stray_components`.

- [ ] **AC13: Stage 26's one-fence cap holds at the new location.**
  `tests/test_115_stage26_validation.py::test_ac8_no_hardcoded_literal_fence_remains`
  still finds at most one `fence`-classified sha256 comparison under `tests/`,
  and where one is found it asserts the module is
  `test_128_reference_verse_v1_integrity.py`.

- [ ] **AC14: `.gitattributes` coverage is asserted, not assumed.**
  `git check-attr text eol -- src/segfacet/reference/reference_verse_v1.json`
  (run as a subprocess from the repo root) reports `text: set` and `eol: lf`.

- [ ] **AC15: the artifact-specific pin line survives.** `.gitattributes`
  contains a line whose pattern matches `reference_verse_v1.json` and is more
  specific than the catch-all `src/segfacet/**/*.json` rule (today:
  `src/segfacet/reference/reference_verse_*.json text eol=lf`), so coverage does
  not depend on the catch-all alone.

- [ ] **AC16: `test_102`'s section header names the real property.** The comment
  header immediately preceding
  `test_ac24_src_tree_is_byte_identical_across_the_test_run` in
  `tests/test_102_stage18_validation.py` describes intra-run non-mutation of
  `src/segfacet/**` and contains neither `scope fence` nor `no production code
  changed by this item`.

- [ ] **AC17: `test_102`'s docstring drops the false pre-102 claim.** That test's
  docstring no longer contains the string `pre-102`, and states that the
  comparison is against the hash taken at module-collection time.

- [ ] **AC18: `test_102`'s assertion is behaviourally unchanged.**
  `test_ac24_src_tree_is_byte_identical_across_the_test_run`'s body still
  compares `_combined_hash(_src_tree_files(), _SEGFACET_SRC)` against
  `_SRC_TREE_HASH_AT_COLLECTION`, and the module still defines
  `_SRC_TREE_HASH_AT_COLLECTION` at module scope.

- [ ] **AC19: the decision table's pointer resolves to the new home.**
  [`../golden-decision-table.md`](../golden-decision-table.md)'s Section 2 row for
  `src/segfacet/reference/reference_verse_v1.json` names the relocated test id in
  its `asserted by` cell and no longer names `test_098_stray_components.py`.

- [ ] **AC20: the decision table's signed cells are untouched.** That same row's
  `what it asserts today`, `evidence`, `disposition` and `replacement guarantee`
  cells are character-for-character equal to their pre-item text (compared as
  strings — see the Testing Strategy's note on why this must not be done with a
  digest literal).

- [ ] **AC21: item 127's guard stays clean.**
  `committed_artifact_guard.iter_violations(tests/)` yields zero violations over
  the post-item tree.

- [ ] **AC22: item 127's allowlist entry is unchanged.**
  `committed_artifact_guard.ALLOWLIST` still contains an entry with
  `path == "src/segfacet/reference/reference_verse_v1.json"` and
  `ground == "integrity-pin"`, and `tests/committed_artifact_guard.py` does not
  appear in this item's diff.

- [ ] **AC23: `aide check` reports no new warning.**
  `python .aide/scripts/aide.py check` emits the same three warnings it emitted
  on the base commit (32 specs missing Assumptions; human gates 1 and 2 awaiting
  a decision) and no `.gitattributes` lint warning for the new module. *Verified
  by executing the Validation section, not by a unit test.*

## Assumptions

- **Clarify mode is `assume`** (`aide.toml` `loop.clarify`); every default below
  was taken without blocking and is recorded here for audit.
- **Module name and location.** The queue says "a test named for the artifact,
  beside `reference/artifact.py`'s tests". Taken as a **new** module
  `tests/test_128_reference_verse_v1_integrity.py` rather than an append to
  `tests/test_045_reference_artifact.py`, on two grounds: the repo's convention
  is one `tests/test_0NN_*.py` module per item, and `test_045` tests the
  `reference/artifact.py` *module* (build/write/load round-trips) whereas this
  pins one shipped *file*. `tests/` is flat, so "beside" is satisfied by both.
- **The companion load-and-score test moves too.** The queue names only the byte
  pin, but `test_ac18_reference_verse_v1_still_loads_and_scores_a_case` shares
  the same `# AC18` header in `test_098` and is likewise about the artifact
  rather than about stray components; leaving it behind would strand an orphaned
  header. Assumed both move (AC8, AC9).
- **The `.gitattributes` pin is keyed by the *artifact* path, not the test
  path**, so relocating the consuming test cannot break it. Measured 2026-08-31:
  `src/segfacet/reference/reference_verse_*.json text eol=lf` is present and the
  broader `src/segfacet/**/*.json text eol=lf` rule also covers the file.
  "Carrying the pin across deliberately" is therefore discharged by *asserting*
  coverage (AC14/AC15), not by editing `.gitattributes` — which is consequently
  in **Asserts against**, not **May change**. If the builder finds coverage
  absent, that is a diverged assumption: hand back rather than widening scope
  silently.
- **The artifact is resolved from a repo-root-relative literal in the new
  module** (`Path(__file__).resolve().parent.parent / "src" / "segfacet" /
  "reference" / "reference_verse_v1.json"`, the shape `test_125` already uses),
  *and* AC7 asserts that path is the same file `bundled_production_reference_path()`
  returns. This is a deliberate improvement over the status quo, not a
  transcription: the helper-call form is invisible to both `aide check`'s
  `.gitattributes` lint and item 127's classifier, which is exactly why the queue
  warns that their silence proves nothing. The literal form makes both able to
  see it (AC6). Under this repo's editable install the two paths are the same
  file; AC7 is what catches it if that ever stops being true.
- **Item ordering: 127 landed before 128, inverting the queue's stated
  preference.** Queue-018 asked for 128 first so item 127's enforced allowlist
  would "name the pin at its final home". This costs nothing, because the
  allowlist is keyed by the **artifact** path
  (`src/segfacet/reference/reference_verse_v1.json`, ground `integrity-pin`), not
  by the consuming test module — so relocating the test requires no allowlist
  edit at all. `tests/committed_artifact_guard.py` is therefore pinned unchanged
  (AC22), and item 127's AC13 (no stale allowlist entry) and AC14 (every
  allowlisted path is `git check-attr`-covered) stay green untouched.
- **`docs/aide/golden-decision-table.md`'s `asserted by` cell is the mutable
  pointer column.** Queue-018's whole-queue scope fence forbids rewriting signed
  text from inside an item, and item 126 drew that line precisely: its
  `_AC18_PRE_ITEM_ROW_DIGESTS` pins *what it asserts today / evidence /
  disposition / replacement guarantee* as byte-unchanged and **explicitly
  excludes `asserted by`** as the cell an item reconciles. This item edits that
  one cell (AC19) and pins the other four (AC20). No disposition, reasoning or
  Section-3/prose text moves.
- **Stage 26's unticked acceptance box is left exactly as it is.** Renaming
  `_PRE_098_REFERENCE_VERSE_V1_SHA256` removes the last `_PRE_NNN_*`-shaped
  identifier from `tests/`, which is the *literal wording* of `progress.md`'s
  Stage-26 acceptance box ("No `_PRE_NNN_*` byte-hash fence remains"). The fence
  survives in substance under a new name, so the criterion's intent is still
  unmet and ticking it would be ticking around the mechanism. Item 128 must not
  edit `progress.md`; AC13 keeps the mechanism-based cap (`test_115`'s AST
  classifier, which keys on shape rather than name) honest and still reporting
  one fence. The wording mismatch is captured in
  [`../insights.md`](../insights.md) for the queue-boundary triage.
- **`aide check`'s baseline is three warnings**, measured on the base commit
  2026-08-31 (32 specs without an Assumptions block; human gates 1 and 2). AC23
  means "the same three", not "zero".

## Implementation Steps

The bulk of this item is test-side; there is no production code path. Steps 6–7
are the only non-test edits.

1. **Create `tests/test_128_reference_verse_v1_integrity.py`.** Module docstring
   states the purpose per AC1: a released production reference-distribution
   artifact, built from mounted VerSe19 ground truth, not regenerable in CI, so
   its recorded digest is the only guard against silent corruption; cite
   `golden-decision-table.md`'s Section 2 `keep` disposition, and note that item
   123 rebuilt the artifact and moved the digest (so the digest pins the
   *item-123 rebuilt state*, and only whoever reruns the rebuild against the real
   cohort may move it again).
2. Define, at module scope, `_ARTIFACT = Path(__file__).resolve().parent.parent /
   "src" / "segfacet" / "reference" / "reference_verse_v1.json"` and
   `_RELEASED_REFERENCE_VERSE_V1_SHA256 =
   "2048804f60208a4dea0cbe8d0980e1e6228c68b52b6331375f768254fc73b5da"`, carrying
   across the explanatory comment from `test_098` (updated to drop the "pre-098"
   framing). Two `.parent` steps are required for item 127's classifier to treat
   the chain as a repo root — see `committed_artifact_guard._is_file_root_chain`.
3. Add the pin itself (AC4) as a direct
   `hashlib.sha256(_ARTIFACT.read_bytes()).hexdigest() ==
   _RELEASED_REFERENCE_VERSE_V1_SHA256` comparison — this exact shape is what the
   classifier and the lint resolve, so do not wrap the read in a helper.
4. Move `test_ac18_reference_verse_v1_still_loads_and_scores_a_case` across
   verbatim except for its name and docstring (AC8), which should say it is a
   liveness check on the shipped artifact rather than an item-098 fence.
5. **Strip the old home.** Delete the `# AC18` section header, the constant and
   both tests from `tests/test_098_stray_components.py`; replace the module
   docstring's AC18 bullet with a one-line pointer to
   `tests/test_128_reference_verse_v1_integrity.py` (AC9, AC11). Leave
   `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`, `_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS`
   and `_FACE_NAME_SENSITIVE_CASES` alone — five other modules import them.
6. **Reconcile the three downstream consumers** (each fails outright otherwise —
   see the Testing Strategy's "existing tests to reconcile"):
   `tests/test_123_recalibrate_and_regenerate.py` (import source, and rename
   `test_ac33_test098_digest_fence_matches_committed_file` to drop the stale
   module reference); `tests/test_115_stage26_validation.py` (the expected fence
   module name, plus its comment explaining which fence remains);
   `docs/aide/golden-decision-table.md` Section 2's `asserted by` cell for
   `reference_verse_v1.json`.
7. **Rename `test_102`'s header and docstring.** In
   `tests/test_102_stage18_validation.py`, replace the `# AC24: the scope fence
   -- no production code changed by this item` banner with one naming intra-run
   non-mutation of `src/segfacet/**`, update the comment above
   `_SRC_TREE_HASH_AT_COLLECTION` in the same terms, and correct
   `test_ac24_src_tree_is_byte_identical_across_the_test_run`'s docstring to say
   the comparison is against the collection-time hash (AC16–AC17). **Change no
   executable line** (AC18).
8. Run `python .aide/scripts/aide.py check` and `python .aide/scripts/aide.py
   scope --item 128`, then the Validation section.

## Authorised paths

**May change:**

- `tests/test_128_reference_verse_v1_integrity.py` — the relocated pin's new home
  (AC1–AC8).
- `tests/test_098_stray_components.py` — remove the constant, the two AC18 tests
  and the section header; repoint the docstring bullet (AC9–AC11).
- `tests/test_102_stage18_validation.py` — comment/docstring wording only
  (AC16–AC18).
- `tests/test_115_stage26_validation.py` — the fence cap's expected module name
  and its explanatory comment (AC13).
- `tests/test_123_recalibrate_and_regenerate.py` — the AC33 test's import source
  and name (AC12).
- `docs/aide/golden-decision-table.md` — Section 2's `asserted by` cell for
  `src/segfacet/reference/reference_verse_v1.json`, and nothing else (AC19–AC20).
- `docs/aide/insights.md` — the one-line capture named in the Assumptions block.

**Asserts against:**

- `src/segfacet/reference/reference_verse_v1.json` — AC4/AC5/AC7 pin its bytes
  and its identity with the packaged path; **never modified by this item**. The
  digest matching AC3's literal is what proves the artifact did not move.

Three further files are read and pinned by this item's tests but are recorded
here in prose rather than as bullets, because `aide check --queue`'s
`changes-pinned-state` comparison does not skip items that have already merged
and reports a hard error against items 126/127's `May change` entries for a
landing that happened on 2026-08-31 (the false positive is captured in
[`../insights.md`](../insights.md), item 127, 2026-08-31; item 127's own spec
took the same route). None of the three is edited by this item, and the diff
against **May change** is what proves it:

The repository's git-attributes file is pinned by AC14, which asserts effective
coverage of the artifact via `git check-attr`, and by AC15, which asserts the
artifact-specific pin line survives alongside the catch-all rule. Item 127's
guard module is pinned by AC6 (which drives its `classify_module`), AC21 (its
`iter_violations`) and AC22 (its `ALLOWLIST` entry, which AC22 also requires be
absent from this item's diff). And the entire production tree is pinned by
omission: this item makes no production-code change at all, while `test_102`'s
relocated-header test continues to hash that tree intra-run.

## Testing Strategy

One focused test per AC in `tests/test_128_reference_verse_v1_integrity.py`,
which is both the new home of the relocated pin and this item's own test module.
Source-level ACs (AC2, AC9–AC13, AC16–AC18) read the target module's text or AST
the way `tests/test_126_golden_retirement.py` already does; do not re-implement a
parser where `ast` will do.

**Adversarial / edge cases:**

- **AC5's mutation case** — copy the artifact to `tmp_path`, flip one byte, and
  assert the digest differs. This is the test that would catch a relocation that
  quietly turned the pin into a tautology.
- **AC6's allowlist-emptied classification** — monkeypatch
  `committed_artifact_guard.ALLOWLIST` to `()` and assert the violation appears
  with the artifact's repo-relative path. A relocation that reverted to
  `bundled_production_reference_path()` would report **zero** violations here and
  the AC would fail — which is the point.
- **AC15's specificity case** — assert the surviving pin line is not merely the
  `src/segfacet/**/*.json` catch-all, so a future edit that deletes the
  artifact-specific line is caught even though `git check-attr` would still say
  `lf`.
- **AC18's no-op check** — assert the two identifiers are still compared, so a
  "tidy-up" that rewrote the assertion while renaming the comment is caught.
- **Determinism** — the digest computation is called twice in one test and must
  return the same value (guards against a helper that consumes a stream).

**Do not use a digest literal for AC20.** `tests/test_115_stage26_validation.py`'s
classifier reports any `hashlib.sha256(...) == <string constant>` under `tests/`
as a `fence` and caps the corpus at **one**, which after this item is the pin
itself. Implementing AC20 as `assert _row_cell_digest(row) ==
"<literal>"` would introduce a second fence and turn AC13 red. Compare the four
cells as plain strings against expected literals instead. (Item 126 evaded this
only incidentally, by holding its digests in a dict the classifier resolves as
`external`.)

**Existing tests to reconcile** — each fails outright on the relocation, and each
is a stale assumption this item must clear rather than discover during
validation:

- `tests/test_123_recalibrate_and_regenerate.py::test_ac33_test098_digest_fence_matches_committed_file`
  — `from test_098_stray_components import _PRE_098_REFERENCE_VERSE_V1_SHA256`
  becomes an `ImportError` (collection error, not a failure).
- `tests/test_115_stage26_validation.py::test_ac8_no_hardcoded_literal_fence_remains`
  — asserts `fences[0].path.name == "test_098_stray_components.py"`; the one
  surviving fence moves to the new module.
- `tests/test_105_golden_decision_table.py::test_ac6_asserted_by_cells_resolve_to_real_tests`
  — resolves every `tests/test_NNN*.py::func` in an `asserted by` cell against
  the file on disk; Section 2's `reference_verse_v1.json` row names the moved
  test, so the cell must be updated in the same commit or this goes red.

**Confirmed *not* affected** (checked 2026-08-31, so the builder need not
re-derive it): `tests/test_111_golden_guard.py` (its
`_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` is keyed by fixture family, not test
module); `tests/test_107_item_scope_check.py` (its `_FENCE_ITEM_NUMBERS` covers
099/100/101/103/105 only); `tests/test_126_golden_retirement.py` (its
`test_098_stray_components` uses concern `_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`,
and its `_AC18_PRE_ITEM_ROW_DIGESTS` covers Section-1 rows only);
`tests/test_127_committed_artifact_tolerance.py` AC13/AC14 (allowlist is keyed by
artifact path); `golden-decision-table.md` Section 3 (covers the two hand-set
`_PRE_098_*` snapshot constants, neither of them this digest).

## Validation

Beyond the unit suite, three things must be *observed*, since each is a claim
about a tool's behaviour rather than about library code. No `[validation]`
profile is required — all three run on any machine with the repo and its venv.

1. **The lint's silence is no longer the answer.** Run
   `python .aide/scripts/aide.py check` and confirm the output is the same three
   warnings as on the base commit (32 specs without an Assumptions block; human
   gates 1 and 2) — in particular, **no** `.gitattributes` warning naming
   `tests/test_128_reference_verse_v1_integrity.py`. Record the exact warning
   count in the Decisions log (AC23).
2. **`.gitattributes` coverage, read from git rather than from the file.** Run
   `git check-attr text eol -- src/segfacet/reference/reference_verse_v1.json`
   and confirm it prints `text: set` and `eol: lf`. This is the check that would
   have caught a relocation which dropped the pin.
3. **The scope fence, proved by diff.** Run `python .aide/scripts/aide.py scope
   --item 128` and confirm every changed path is in **May change** above — in
   particular that no path under `src/segfacet/` and neither
   `tests/committed_artifact_guard.py` nor `.gitattributes` appears (AC22, and
   the standing rule that scope is proved by the diff, never by a test hashing
   another file's bytes).

## Dependencies

- **Item 126** (✅) — executed the golden retirement; the post-retirement
  inventory is what `test_115`'s and `test_126`'s surviving assertions describe,
  and item 126 established the `asserted by`-cell-is-mutable convention this item
  relies on for AC19/AC20.
- **Item 127** (✅) — provides `tests/committed_artifact_guard.py`, whose
  `classify_module` / `iter_violations` / `ALLOWLIST` are the subject of AC6,
  AC21 and AC22. Queue-018 expected this item to land *first*; it did not, and
  the Assumptions block records why that costs nothing.

**Downstream:** item 135 (Stage 29 validation) replays this item's
"fails before the fix" claim and re-runs `aide check`.

## Decisions & Trade-offs

To be updated during implementation.
