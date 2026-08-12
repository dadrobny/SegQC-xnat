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

## Decisions & Trade-offs

- **Enforcement is validator + CI, not validator alone** (maintainer, 2026-08-12).
  An agent can skip a spec obligation; a required CI check cannot. The job is
  pure git, so it adds no dependency surface — deliberately unlike the
  environment-gated jobs whose flakiness item 113 is separately fixing.
- The eventual home for this check is the framework (`aide-loop`), where it
  belongs to every consumer rather than to this repo. Prototyping it here first
  is deliberate: the upstream change becomes a port of something already proven
  in use rather than a design sketch.

To be updated during implementation.
