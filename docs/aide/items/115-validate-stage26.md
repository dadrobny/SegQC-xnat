# Item 115 — Validate stage 26: Carried-Defect Remediation

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 115
> **Objectives:** G2, G7
> **Suggested branch:** `aide/115-validate-stage26`

---

## Description

Close Stage 26 by **replaying its use cases end-to-end**, not by re-running the
unit suite. Stage 26 exists because eight diagnosed defects had accumulated
without owners — a ninth, item 116, was found during execution and inserted;
the stage's claim is that they are fixed, so this item's job is
to demonstrate each fix against the behaviour it replaced, then record what was
actually exercised in `progress.md`.

Two validation obligations are specific to this stage. First, **red-then-green
evidence**: a remediation stage whose regression tests were written after the
fix proves nothing, so the three cheapest-to-stage defects are re-broken in a
scratch tree and observed failing. Second, a **fresh-clone run in a different
directory** — item 099's absolute-path bug passed every local gate, a from-scratch
`git clone` in another directory, and both validator rounds, and was caught only
by reading the Actions tab; a checkout at a different path is the cheapest
approximation of that.

**In scope.** Replay, evidence recording, `progress.md` acceptance ticks, and
Environment-Gated Capability Verification row updates.

**Not in scope.** Fixing anything found. A genuine defect surfaced here is
logged to `insights.md` and, if it blocks a stage claim, the stage stays open
and this item reports that rather than ticking around it.

## Acceptance Criteria

- [ ] **AC1: every defect has a demonstrably-failing regression test.** For each
  of items 107-114 and 116, the test that pins its fix is identified by name, and its
  relationship to the pre-fix behaviour is recorded.
- [ ] **AC2: red-then-green is observed for item 108.** The affine-driven face
  mapping is reverted in a scratch tree, the face test observed failing, and the
  tree restored.
- [ ] **AC3: red-then-green is observed for item 109.** The attribution scale is
  reverted, the differential-magnitude test observed failing, and restored.
- [ ] **AC4: red-then-green is observed for item 111.** `tests/golden/022_stage3_report.json`
  is deleted in a scratch tree, the snapshot test observed **failing** (not
  skipping), and restored.
- [ ] **AC5: `border`/`fov` name the right face end-to-end (G2).** A full
  `segfacet run` on a fixture cropped at a known anatomical face emits a finding
  naming that face; the report excerpt is recorded.
- [ ] **AC6: attribution follows magnitude end-to-end (G7).** A run-vs-run
  comparison over two runs built with a large move in one mode and a small move
  in another attributes the large one; reversing the magnitudes reverses the
  attribution. Both outputs recorded.
- [ ] **AC7: the neighbourhood fork is fully executed.** Item 110's outcome is
  verified on both sides: the module is reachable from `extract_feature_record`
  **and** present in the regenerated catalogue with `status: "unwired"`, and no
  `progress.md` claim about it remains that observable behaviour does not back.
- [ ] **AC8: no byte-hash fence remains — searched by assertion shape, not by
  name.** A fence is *a SHA-256 taken over a committed file's bytes and compared
  against a hardcoded literal*. Searching for the `_PRE_[0-9]` naming pattern is
  **not sufficient** and must not be the check: item 107's own AC1 did exactly
  that and missed three survivors, one of which
  (`_PRE_ITEM_REFERENCE_DEFAULT_SHA256` in
  `tests/test_093_tptbox_label_convention.py`) then fired on item 116's
  legitimate regeneration of `reference_default.json`. Two are known to remain at
  the time of writing — `tests/test_098_stray_components.py`'s pinned pre-098
  digest of `reference_verse_v1.json`, and
  `tests/test_102_stage18_validation.py`'s path-to-digest dict asserted around
  line 668 — and this item must either retire them or record why each stays.
  **The discriminator:** a digest compared against a *hardcoded constant* is a
  fence; a digest compared against a value *computed in the same run* (hash,
  run the code, re-hash, compare) is an intra-run determinism assertion and must
  survive untouched.
- [ ] **AC9: every queue-016 item declared `## Authorised paths`.** All ten
  specs carry the section (item 116 was inserted mid-execution), and item 107's checker parses each without error.
- [ ] **AC10: the checker catches a real violation.** On a scratch branch, an
  edit outside an item's authorised paths makes
  `scripts/check_item_scope.py` exit non-zero naming that path; the output is
  recorded.
- [ ] **AC11: the fresh-clone suite is green.** The full suite passes from a
  clean `git clone` into a directory whose path differs from this checkout's,
  in a fresh venv. The clone path is recorded.
- [ ] **AC12: Stage 26's acceptance is ticked honestly.** All five acceptance
  criteria in `progress.md`'s Stage 26 section are ticked with a one-sentence
  evidence note naming what was run — or left unticked with the reason.
- [ ] **AC13: verification rows reflect reality.** Any Environment-Gated
  Capability Verification row this stage affects is flipped to ✅ Verified where
  `python .aide/scripts/aide.py env --profile <name>` allows, and otherwise
  records why it stays ❓ Unverified. Item 113 must not have flipped the Docker
  row by reducing where Docker runs.
- [ ] **AC14: `aide check` reports no new warning.**
- [ ] **AC15: findings are logged, not silently fixed.** Anything discovered
  during replay that is not a Stage 26 deliverable is appended to
  `insights.md` and named in this item's Decisions.

## Assumptions

- **Items 107-114 and 116 are all ✅ before this item starts.** If any is incomplete,
  this item halts and reports rather than validating a partial stage — the same
  posture item 106 took on a pending sign-off.
- **Red-then-green is staged in a scratch tree, never on the branch.** Reverts
  are made, observed and discarded; no revert is committed.
- **Three defects are enough for AC2-AC4.** Items 107, 110, 112, 113, 114 and 116 are
  verified by inspection and their own tests rather than by re-breaking, because
  re-breaking them means deleting a script, unwiring a module, or editing CI —
  disproportionate to the evidence gained. The choice is recorded.
- **A "different directory" clone is the available proxy for a different
  platform.** It catches the absolute-path class of bug, not the line-ending or
  path-separator classes; those remain CI's job, and this item records that
  limit rather than implying broader coverage.

## Implementation Steps

1. Confirm items 107-114 and 116 are ✅ in `progress.md`; halt if not.
2. For each item, identify the pinning test by name and record it (AC1).
3. Stage AC2/AC3/AC4's reverts one at a time in a scratch tree, observe the
   failure output, restore, and record each.
4. Run the AC5 and AC6 end-to-end replays; capture the report excerpts.
5. Verify AC7 against the regenerated catalogue and `progress.md`.
6. Search `tests/` for the fence *shape* — a `hashlib.sha256(...)` over a
   committed file compared against a hardcoded literal — not for the
   `_PRE_[0-9]` name (AC8); parse every queue-016 spec with the checker (AC9);
   stage the AC10 violation on a scratch branch.
7. Clone into a fresh directory, build a venv, run the full suite (AC11).
8. Update `progress.md`: Stage 26 acceptance ticks with evidence, verification
   rows, and the deliverable statuses.
9. Run `aide check` (AC14); log anything found to `insights.md` (AC15).

## Testing Strategy

New module `tests/test_115_stage26_validation.py` for the assertions that can be
made in-suite; the replays themselves belong to the Validation section:

- AC8: assert no digest-vs-hardcoded-literal comparison over a committed file
  remains under `tests/`, and that the intra-run before/after digests still do.
- AC9: assert each of the ten specs has a non-empty `## Authorised paths`.
- AC7: assert the neighbourhood paths are in the committed catalogue with
  `status: "unwired"`, and that `progress.md`'s item 024 bullets match.
- AC12: assert every Stage 26 acceptance box is either ticked **and** followed
  by an evidence annotation, or unticked **and** followed by a reason — the
  tick-implies-evidence biconditional item 106 established.
- AC13: assert the Docker verification row is unchanged in state by item 113.

Adversarial: a spec with an `## Authorised paths` heading but no bullets; a
Stage 26 box ticked with no annotation (must fail); a `_PRE_` constant
reintroduced in a comment (decide and document whether that counts).

## Validation

This item **is** the validation. Record, in Decisions: each red-then-green
observation with its failure output; the AC5 and AC6 report excerpts; the AC10
checker output; the AC11 clone path, venv creation and suite result; and the
`aide check` output. A replay that could not be performed is recorded as such,
never inferred from a green suite.

## Dependencies

Items 107, 108, 109, 110, 111, 112, 113, 114 — all must be ✅; this item
validates their combined result and closes the stage.

## Authorised paths

- `tests/test_115_stage26_validation.py`
- `docs/aide/progress.md`
- `docs/aide/insights.md`
- `docs/aide/items/115-validate-stage26.md`

## Decisions & Trade-offs

To be updated during implementation.
