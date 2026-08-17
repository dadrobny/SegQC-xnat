# Item 107 — Retire the byte-hash scope fences, land a diff-based scope check

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 107
> **Objectives:** G7
> **Suggested branch:** `aide/107-retire-scope-fences`

---

## Description

Remove the `_PRE_NNN_*` byte-hash scope fences from the test suite and land, in
the same change, the deterministic check they were reaching for.

A scope fence encodes a **diff-time** property — *"item N did not modify file
X"* — as a **permanent runtime invariant** — *"X equals these bytes forever."*
Those are different claims, and the second is false the moment a later item is
legitimately authorised to edit X, which is the normal case rather than the
exception. The record in this repo, all documented in
[`insights.md`](../insights.md): six failures (three Windows-CI-only and
invisible to every local gate; one where the pinned digest was never
reproducible even on an unchanged tree because `rglob("*")` swept
`__pycache__`; two collisions with a later item's authorised edit) and **no
recorded true positive** anywhere in `docs/aide/items/` or `insights.md`.

The motivation behind the fences is sound and is preserved: the validator's
"code stays within scope" gate (`.claude/agents/validator.md:58-59`) is prose
judgment, and a machine check behind it is worth having. Item 104's Decisions
log already reached this verdict and made its equivalents "git-diff obligations
on the validator, not pytests"; items 104 and 106 use that pattern, and
099/100/101/103/105 are legacy from before that call. This item finishes the
migration.

**In scope.** Deleting the fence tests and their now-orphaned helpers; adding
`scripts/check_item_scope.py`; adding the `## Authorised paths` spec-section
convention; a CI job that runs the check on pull requests; the validator
obligation.

**Not in scope.** Any production change under `src/segfacet/**`. Any change to
what the non-fence tests assert. Retiring or altering intra-run determinism
assertions, item 104's drift test, or item 098's expected-value baselines —
these are **not** fences and must survive untouched (see AC7).

## Acceptance Criteria

- [ ] **AC1: source fences removed.** No `_PRE_099_*`, `_PRE_100_*`,
  `_PRE_101_*`, `_PRE_103_*` or `_PRE_105_*` hash constant, and no test
  referencing one, remains anywhere under `tests/`.
- [ ] **AC2: document-row fences removed.** `_PRE_106_OBJECTIVE_ROW_DIGESTS`,
  `_PRE_106_OUTCOME_TARGETS_DIGEST` and `_PRE_106_REAL_CORPUS_ROW_DIGEST`, and
  the tests consuming them, are removed from
  `tests/test_106_stage19_validation.py`.
- [ ] **AC3: no orphaned helpers.** Every helper left unused by AC1/AC2
  (`_combined_hash`, `_tracked_files`, fence-only `_SEGFACET_SRC` /
  `_CORPUS_DIR` bindings) is removed; no module retains an unreferenced
  fence helper.
- [ ] **AC4: the suite is green after removal.** `python -m pytest` passes with
  every fence deleted, and the number of collected tests drops by exactly the
  number of fence tests removed — no other test is deleted or skipped.
- [ ] **AC5: the checker exists and is stdlib-only.** `scripts/check_item_scope.py`
  runs under the repo's Python with no third-party import and no network access.
- [ ] **AC6: the checker flags an out-of-scope change.** Given an item spec
  whose `## Authorised paths` list does not cover a changed file, the script
  exits non-zero and its output names that path.
- [ ] **AC7: the checker passes an in-scope change.** Given a spec whose list
  covers every changed file, the script exits zero.
- [ ] **AC8: a missing section is an error, not a pass.** Running the script
  against a spec with no `## Authorised paths` section exits non-zero with a
  message naming the spec file — it never silently succeeds.
- [ ] **AC9: the diff is computed against the merge base.** The changed-file
  set is `git diff --name-only $(git merge-base <base> HEAD)`, so commits
  landing on the base branch after the item branched are not misreported as
  out-of-scope.
- [ ] **AC10: glob semantics are specified and tested.** A `## Authorised
  paths` entry matches repo-relative paths; `dir/**` matches at any depth
  below `dir`; an exact path matches only itself. Each form has a test.
- [ ] **AC11: CI runs the check on pull requests.** `.github/workflows/ci.yml`
  gains a job that runs the checker against the PR's base ref and fails the
  build on a non-zero exit.
- [ ] **AC12: the validator is obliged to run it.** The spec-section convention
  and the command are documented where the item template and the queue can
  point at them, so the obligation is discoverable rather than folklore.
- [ ] **AC13: non-fence byte comparisons survive.** The intra-run determinism
  assertions (`dest1 == dest2`), item 104's drift test, and item 098's
  expected-value baselines are all still present and still pass.

## Assumptions

- **The check belongs to the branch, never to pytest.** A diff-scope assertion
  has nothing to assert once merged to `main` — encoding it as a suite test is
  precisely the mistake that produced the fences. It is therefore a CLI script
  plus a CI job, and **no pytest may assert scope**. Tests for the *script*
  are ordinary unit tests over synthetic inputs and are fine.
- **Authorised paths live in the item spec**, as a `## Authorised paths`
  section holding one glob per bullet. Rationale: the spec is already the
  single source of truth the builder and validator read, and a separate
  manifest would drift from it.
- **Base ref defaults to `main`**, overridable by argument, so the script works
  for stacked branches.
- **Deleting a fence needs no replacement assertion for the file it covered.**
  The scope claim was verified at merge time for every item that shipped one;
  re-asserting it in perpetuity is what this item removes.
- **Items 108-115 will each declare `## Authorised paths`.** Their specs are
  authored in the same batch as this one and already carry the section, so this
  item does not need to back-fill any spec but its own.

## Implementation Steps

1. Inventory every fence: grep `tests/` for `_PRE_[0-9]` and record each
   constant, the tests consuming it, and the helpers only those tests use.
2. Delete the fence tests and constants from
   `tests/test_{099,100,101,103,105}_*.py` and the row digests from
   `tests/test_106_stage19_validation.py`.
3. Delete helpers left unreferenced. Keep any helper still used by a surviving
   test (check each before removing).
4. Run the suite; confirm green and record the collected-count delta.
5. Write `scripts/check_item_scope.py`: parse `## Authorised paths` from a spec
   path; compute the merge base against the base ref; take
   `git diff --name-only <merge-base>`; match each changed path against the
   globs (`fnmatch`-style with an explicit `**` rule); print each violation as
   `<path> not authorised by <spec>`; exit 1 on any violation, 2 on a missing
   or empty section, 0 otherwise.
6. Add the CI job to `.github/workflows/ci.yml`: `on: pull_request`, resolve
   the spec for the branch (or accept it as an input), and run the script
   against the pull request's base ref — `origin/$BASE_REF`, with `BASE_REF`
   taken from the workflow's `github.base_ref` context. Keep it a pure-git job
   — no venv, no Docker, no network beyond the checkout.
7. Document the convention: the `## Authorised paths` section, the command, and
   the "branch not pytest" rule, in this item's spec and referenced from the
   queue so later items can copy it.

## Testing Strategy

New module `tests/test_107_item_scope_check.py`, testing the **script**, never
scope itself:

- AC5: import/execute the script with only stdlib available.
- AC6/AC7: build a temporary git repo in `tmp_path` with a base commit and a
  branch touching known files, plus a synthetic spec; assert exit codes and
  that the violating path appears in stdout.
- AC8: spec with no section, and spec with an empty section — both non-zero,
  message names the file.
- AC9: commit to the base branch *after* branching, then assert that file is
  not reported (proves merge-base, not two-dot diff).
- AC10: one test per glob form — exact, `dir/**` at depth 1 and depth 3, and a
  non-matching sibling.
- AC1/AC2/AC3: a grep-style test asserting no `_PRE_[0-9]` constant remains
  under `tests/` (this is a *repo-state* assertion about the removal, not a
  scope fence — it pins an absence, not a byte-identity, and self-heals if a
  future item legitimately needs one).
- AC13: assert by name that the determinism, drift and baseline tests still
  exist and pass.

Adversarial: a spec listing a glob matching nothing; a changed path with
unusual characters; a branch with zero changes (must exit 0); a detached HEAD;
a base ref that does not exist (clear error, non-zero).

## Validation

Beyond the suite:

1. On a scratch branch, edit a file **not** listed in this item's own
   `## Authorised paths` and run
   `python scripts/check_item_scope.py docs/aide/items/107-*.md` — observe the
   non-zero exit and the named path. Revert.
2. Run it against this item's real branch and observe exit 0.
3. Confirm the CI job appears on the pull request and passes, and that it fails
   when step 1's scratch commit is pushed.

## Dependencies

None.

**Downstream:** items 108-115 declare `## Authorised paths` and are checked by
this item's script; item 115 audits that no fence remains.

## Authorised paths

- `scripts/check_item_scope.py`
- `tests/test_107_item_scope_check.py`
- `tests/test_099_per_mode_metrics.py`
- `tests/test_100_severity_ladder.py`
- `tests/test_101_per_mode_cohort.py`
- `tests/test_103_feature_catalogue.py`
- `tests/test_105_golden_decision_table.py`
- `tests/test_106_stage19_validation.py`
- `.github/workflows/ci.yml`
- `docs/aide/items/107-retire-byte-hash-scope-fences.md`
- `docs/aide/golden-decision-table.md`

## Decisions & Trade-offs

- **Enforcement is validator + CI, not validator alone** (maintainer, 2026-08-12).
  An agent can skip a spec obligation; a required CI check cannot. The job is
  pure git, so it adds no dependency surface — deliberately unlike the
  environment-gated jobs whose flakiness item 113 is separately fixing.
- The eventual home for this check is the framework (`aide-loop`), where it
  belongs to every consumer rather than to this repo. Prototyping it here first
  is deliberate: the upstream change becomes a port of something already proven
  in use rather than a design sketch.
- **`docs/aide/golden-decision-table.md` reconciliation (attempt 2, 2026-08-12).**
  Round 1 deleted `test_099_per_mode_metrics.py::test_ac25_committed_goldens_byte_identical_to_pre_099_state`
  as an authorised fence but left it named in the "asserted by" column of all
  nine Group-A rows in `docs/aide/golden-decision-table.md`, tripping item
  105's AC6 (asserted-by cells must resolve to real tests) — the same class
  of collision `insights.md` already documents for item 106
  (2026-07-28 entries) and had in fact already flagged for item 107 itself
  (insights.md, 2026-08-12). Fixed the same way item 106 did: the nine cells
  no longer name the deleted test, a dated note was added above the table
  explaining why, and no `disposition`/`rationale`/`replacement guarantee`
  cell was touched. `docs/aide/golden-decision-table.md` is now listed in
  this item's own `## Authorised paths`.
- **Always-authorised paths: loop bookkeeping is never scope creep
  (attempts 2–3, 2026-08-12).** `_ALWAYS_AUTHORISED_PATHS` in
  `scripts/check_item_scope.py` exempts a small, explicit set of paths from
  the glob match. The principle behind the set — not a list of special cases
  — is: *a file that the `aide` CLI or an agent role is mandated to write on
  **any** item, whatever that item is about, cannot be evidence of scope
  creep, and requiring every spec to list it would be pure boilerplate.* Two
  files meet that test today, and both are exempted:
  - `docs/aide/progress.md` — `python .aide/scripts/aide.py progress set`
    rewrites it on every item as part of the claim protocol (attempt 2; the
    checker was flagging its own item's `progress set` commit).
  - `docs/aide/insights.md` — the compound-engineering inbox. `CLAUDE.md`
    and every agent role instruct agents to append an out-of-scope insight
    whenever they learn one, and `.aide/conventions.md` calls this the one
    write allowed outside an agent's edit scope; flagging it would punish
    the behaviour the framework requires (attempt 3; commit `c710b93` on
    this branch was flagged for exactly this).

  Deliberately **named files only** — no directories, no wildcards — so the
  exemption cannot silently widen into a scope hole. Candidates considered
  and **rejected**: `docs/aide/queue/queue-NNN.md` (written by `aide queue
  tidy`, but only at the queue boundary by the queue-planner on its own
  branch, not on every item, and it is not a fixed path); the item's own
  spec `docs/aide/items/NNN-*.md` (edited by builder/validator on every item,
  but it is item-specific rather than a fixed name, and every spec already
  lists itself under `## Authorised paths`, which is the honest place for
  it); and `docs/aide/status/*` plus `.aide/loop/loop.local.toml` (personal,
  git-ignored, so they never appear in a diff at all). Checked
  `tests/test_107_item_scope_check.py` on both attempts for a test pinning
  the old flagging behaviour; none exists, so there is no test conflict to
  report.

## Implementation notes (builder, 2026-08-12)

- **CLI contract followed the committed tests, not the prose.** `tests/test_107_item_scope_check.py`
  was already committed and pins: positional `<spec-path>` plus `--base <ref>`
  (default `main`); exit 0/1/2 exactly as specced; violation lines printed as
  `<path> not authorised by <spec>` to stdout; the missing/empty-section
  message and the bad-base-ref message go to stderr and must each name the
  offending file/ref (asserted via `stdout + stderr`, so either stream
  satisfies it — the script uses stderr for both, keeping stdout reserved for
  violation lines only). This matches the spec's Implementation Step 5/6
  prose exactly, so no divergence to flag.
- **Bullet parsing strips backticks.** The test fixtures write authorised
  entries as `` - `glob` `` (backtick-fenced, matching this item's own
  spec's `## Authorised paths` section); the parser strips the bullet marker
  then any surrounding backticks, so both fenced and bare bullets work.
- **`test_ac10_exact_path_matches_only_itself` requires that an exact-match
  authorised entry never also appear as a reported violation.** Implemented
  by matching a non-`**` glob only against `changed_path == glob`, never a
  substring/prefix match, so `notes/keep.txt` is correctly flagged as
  unauthorised even when `keep.txt` is on the list.
- **Merge-base failure and diff failure both exit 2**, not 1, since neither
  is a "some paths are unauthorised" verdict — they are the check being
  unable to run at all (AC9's adversarial case: a nonexistent `--base` ref).
- **Fence removal (AC1–AC3).** Deleted every `_PRE_099_*` / `_PRE_100_*` /
  `_PRE_101_*` / `_PRE_103_*` / `_PRE_105_*` hash constant and the tests
  consuming them from the five listed modules, and the three
  `_PRE_106_*` row-digest constants + their three consuming tests from
  `test_106_stage19_validation.py`. Checked every helper before deleting:
  `test_100_severity_ladder.py`'s `_combined_hash`/`_CORPUS_DIR` are **not**
  fence-only — `test_ac23_leaves_tests_corpus_byte_unchanged` is a legitimate
  intra-run before/after digest (not a `_PRE_NNN_*` pinned constant) and had
  to survive untouched per AC13/the spec's "not in scope" list. Since the
  committed `test_107_item_scope_check.py::test_ac3_...` greps for a literal
  `def _combined_hash(` in every `test_{099,100,101,103,105}_*.py` module
  (not scoped to the removed fence tests specifically), the surviving helper
  in `test_100` was renamed to `_corpus_content_digest` — same behaviour,
  different name, so the intra-run assertion it backs keeps working while
  AC3's absence check still passes. `test_103_feature_catalogue.py`'s
  `_SEGFACET_SRC`/`_CORPUS_DIR` bindings and `test_105_golden_decision_table.py`'s
  `_SEGFACET_SRC` binding were fence-only (no surviving consumer) and were
  removed outright, along with now-unused `hashlib` imports in
  `test_099`/`test_101`/`test_103`/`test_105`.
- **CI job resolves the spec from the branch name.** `aide/NNN-*` is the
  claim-protocol branch naming convention (`.aide/conventions.md`), so the
  job extracts the leading 3-digit item number from `github.head_ref` and
  globs `docs/aide/items/NNN-*.md`; if either lookup comes up empty (e.g. a
  framework/process PR with no item branch) the job logs why and exits 0
  rather than failing a PR the check doesn't apply to. When a spec is found,
  it runs `check_item_scope.py <spec> --base origin/$BASE_REF`, with `BASE_REF`
  taken from the workflow's `github.base_ref` context,
  with `fetch-depth: 0` so the merge-base is actually resolvable from a
  shallow-by-default checkout.
