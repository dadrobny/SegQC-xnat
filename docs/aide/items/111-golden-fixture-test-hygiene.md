# Item 111 — Golden-fixture test hygiene

> **Created:** 2026-08-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 26 — Carried-Defect Remediation (pre-real-data)
> **Queue:** [`../queue/queue-016.md`](../queue/queue-016.md) · Item 111
> **Objectives:** G7
> **Suggested branch:** `aide/111-golden-fixture-hygiene`

---

## Description

Close two independent defects in how committed goldens are guarded, both found
during item 105's survey and both correctly out of scope there.

**(a) `tests/golden/*.json` is unpinned.** `016_features_report.json` and
`022_stage3_report.json` are the only committed byte-reproducible text fixtures
absent from `.gitattributes`; every other family (`tests/corpus/manifest.json`,
`tests/corpus/golden/*.json`, `tests/corpus/intensity/manifest.json`,
`tests/corpus/094_pre_migration_snapshot.json`, `src/segfacet/**/*.py`,
`src/segfacet/**/*.json`, and more) is pinned `text eol=lf`. It is latent only
because both consumers compare with `read_text()`, whose universal-newline
translation silently normalises a CRLF checkout back to `\n`. The moment any
future comparison switches to `read_bytes()`, it reproduces the Windows-CI-only
failure documented three times over for items 099-101.

**(b) A golden that heals itself cannot fail.**
`tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot` (lines
~786-789) writes the golden and `pytest.skip`s when the file is absent, so
**deleting `tests/golden/022_stage3_report.json` makes the check pass.** That
is the exact opposite of `synth/golden.py::read_golden_text`, whose docstring
states that "a missing golden must fail loudly, never silently pass", and of
`tests/test_042_golden_determinism.py::test_ac14_missing_golden_fails_loudly`,
which pins that behaviour for the corpus goldens. A stale checkout, a
`.gitignore` accident, or a future item retiring the file would each be reported
as green. The sibling `test_016_features_json.py::test_ac5_golden_snapshot` has
no such branch and is the model.

**In scope.** The `.gitattributes` pin; removing the self-healing branch.

**Not in scope.** Retiring either golden. Both carry a **retire** disposition in
`docs/aide/golden-decision-table.md`, but `progress.md` states plainly that
*"Stage 19 decides, Stage 21 executes"* — pre-empting that here would take a
signed-off decision away from its named executor. This item fixes the guards;
Stage 21 retires the files.

## Acceptance Criteria

- [ ] **AC1: the pin exists.** `.gitattributes` contains a rule pinning
  `tests/golden/*.json` as `text eol=lf`.
- [ ] **AC2: the pin is effective.** `git check-attr text eol -- tests/golden/016_features_report.json`
  and the same for `022_stage3_report.json` both report the LF pin.
- [ ] **AC3: the committed bytes are already clean.** Both committed blobs
  contain zero `\r` bytes, verified before the pin is added, so this is a
  `.gitattributes`-only change with no content rewrite.
- [ ] **AC4: no other unpinned byte-reproducible fixture remains.** A survey of
  committed exact-match fixtures finds every family pinned, or names any
  remaining exception with a reason.
- [ ] **AC5: the self-healing branch is gone.**
  `test_022_stage3_serialisation.py::test_ac8_golden_snapshot` no longer writes
  the golden and no longer calls `pytest.skip`.
- [ ] **AC6: a missing golden fails loudly.** With
  `tests/golden/022_stage3_report.json` absent, that test **fails** — it does
  not skip and does not pass.
- [ ] **AC7: the failure names the file.** The failure message identifies the
  missing path, so the cause is legible without reading the test.
- [ ] **AC8: the passing path is unchanged.** With the golden present and
  matching, the test passes exactly as before; its comparison semantics are
  untouched.
- [ ] **AC9: the sibling stays the model.**
  `test_016_features_json.py::test_ac5_golden_snapshot` is unchanged, and the
  two tests' missing-golden behaviour now agrees.

## Assumptions

- **Fix, do not retire** (spec-author default, from the queue's instruction not
  to silently do both). The retire dispositions are Stage 21's to execute.
- **Both goldens' committed blobs are pure LF today.** AC3 makes this a checked
  precondition rather than an assumption; if either contains `\r`, hand back —
  a content rewrite is a different change with different review needs.
- **Regeneration guidance moves to the failure message.** Removing the
  self-healing branch means a developer with a legitimately changed report needs
  to know how to regenerate; the failure message says so, rather than the test
  doing it for them.

## Implementation Steps

1. Verify both committed blobs are `\r`-free (`git show HEAD:<path>` piped to a
   byte check) and record the result.
2. Add `tests/golden/*.json text eol=lf` to `.gitattributes`, in the existing
   commented style that explains why each family is pinned.
3. Confirm with `git check-attr`.
4. Survey `tests/` for any other committed fixture compared byte-exactly, and
   record the result (AC4).
5. Delete the `if not GOLDEN_PATH.exists(): … pytest.skip(...)` branch in
   `test_022_stage3_serialisation.py`, letting `read_text` raise, or raising a
   clear assertion naming the path.
6. Reword the assertion message to state how to regenerate intentionally.

## Testing Strategy

New module `tests/test_111_golden_guard.py`:

- AC1/AC2: parse `.gitattributes` and shell `git check-attr` for both files.
- AC3: assert the committed blobs contain no `\r`.
- AC5: assert the source of `test_ac8_golden_snapshot` contains no
  `pytest.skip` and no write to the golden path.
- AC6/AC7: copy the repo's golden into `tmp_path`, monkeypatch the path to a
  missing file, and assert the test function raises with the path named.
- AC9: assert both snapshot tests agree on missing-golden behaviour.

Adversarial: golden present but empty; golden present with CRLF content
(behaviour must be well-defined); read-only golden directory.

## Dependencies

None.

**Downstream:** Stage 21 executes the retire dispositions for both files.

## Authorised paths

- `.gitattributes`
- `tests/test_022_stage3_serialisation.py`
- `tests/test_111_golden_guard.py`
- `docs/aide/items/111-golden-fixture-test-hygiene.md`

## Decisions & Trade-offs

- **AC3 precondition verified before editing `.gitattributes`.** `git show
  HEAD:tests/golden/016_features_report.json` and the `022_stage3_report.json`
  sibling were each piped through a byte-level `\r` count: zero in both. The
  `.gitattributes` change is therefore pin-only, confirmed with
  `git check-attr text eol -- tests/golden/016_features_report.json
  tests/golden/022_stage3_report.json` reporting `eol: lf` for both after the
  edit.
- **Pin added as a single `tests/golden/*.json text eol=lf` line**, in the same
  commented style as the rest of the file, rather than two separate lines per
  file — the existing `tests/corpus/golden/*.json` entry uses the same glob
  shape.
- **AC4 survey reused, not re-walked.** `tests/test_111_golden_guard.py`'s
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` list is the AC4 survey; no additional
  unpinned family was found during implementation, so no further
  `.gitattributes` entries were needed beyond the one pin.
- **`test_ac8_golden_snapshot`'s self-healing branch was deleted outright**
  (not replaced with an explicit `raise`), matching the sibling
  `test_ac5_golden_snapshot` exactly per AC9 — `GOLDEN_PATH.read_text()` now
  raises `FileNotFoundError` on a missing file, and that exception's message
  already contains the full path (hence the file's name), satisfying AC7
  without extra code.
- **Regeneration guidance moved into the drift-assertion message** rather than
  kept as executable code: the message now spells out writing `produced` to
  `GOLDEN_PATH` and committing the result, and explicitly notes "this test no
  longer does that for you" so a developer used to the old self-healing
  behaviour isn't surprised.
- **Neither golden was retired.** Both carry a `retire` disposition in
  `docs/aide/golden-decision-table.md`, but per `progress.md` that decision is
  Stage 21's to execute, not this item's.
