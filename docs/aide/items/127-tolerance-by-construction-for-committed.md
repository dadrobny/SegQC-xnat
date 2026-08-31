# Item 127 — Tolerance by construction for committed-artifact comparisons

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene (deliverable **D2**)
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 127
> **Objectives:** G7 (evaluable & regression-testable — what the suite actually
> guarantees, and what it merely pins)
> **Suggested branch:** `aide/127-tolerance-by-construction-for-committed`

---

## Description

Comparing freshly generated output against a **committed** artifact is byte-exact
only by accident. Item 078 established that: full-precision floats in a committed
report differ by ~1 ULP across NumPy versions, platform BLAS/SIMD and libm
rounding, so the fresh-vs-committed comparison must be numeric-tolerance
(`reports_close`) while structure, keys, strings, bools and list order stay
exact. That decision is currently applied **by reviewer vigilance**: four test
modules each open-code the same four lines (`build …` → `json.loads(fresh)` →
`json.loads(committed)` → `assert reports_close(...)`), and nothing stops the
next test-writing pass from writing `assert fresh.read_bytes() ==
committed.read_bytes()` instead. It did not stop three of them: items 119, 120
and 123 each reintroduced byte-exact comparisons against committed
float-carrying artifacts that only PR #56's CI matrix caught.

This item makes the decision structural, in two parts.

**Part 1 — one helper, named for what it does.** A single comparison helper
whose name says it compares against a *committed artifact*, living beside
`reports_close` in `src/segfacet/synth/golden.py`, applying `reports_close`
semantics (numeric leaves within tolerance; dict key sets, list length and
order, strings, bools and `None` exact) and reporting *where* two structures
first diverge. The four existing open-coded comparisons become calls to it:

| module | line (2026-08-31) | committed artifact |
|---|---|---|
| `tests/test_063_reference_intensity.py` | 579 | `reference_default.json` |
| `tests/test_081_reference_morphology.py` | 647 | `reference_default.json` |
| `tests/test_120_leave_one_out_offset.py` | 851 | `reference_default.json` |
| `tests/test_123_recalibrate_and_regenerate.py` | 937 | `reference_default.json` |

**Part 2 — an enforced allowlist.** `tests/test_111_golden_guard.py`'s
`_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` is today a *hand-surveyed* tuple serving one
purpose: proving every byte-read committed fixture carries a `.gitattributes`
LF pin (item 111 AC4). This item adds a second, **enforcing** structure: a
classifier that walks every module under `tests/` and reports each byte-exact
comparison of freshly generated output against a committed artifact, and an
allowlist that says which of those are legitimate and why. A comparison against
a committed artifact that is not on the allowlist fails, and the failure message
names the helper the author should have used.

`src/segfacet/reference/reference_default.json` is the worked negative case and
is deliberately **not** allowlisted: 454 of its 1133 float leaves are
full-precision computed statistics (measured 2026-08-31), which is exactly the
shape item 078 proved is not byte-stable. That is the artifact item 135's
scratch-branch replay uses to demonstrate the guard fires.

### The rule for what legitimately stays byte-compared

Recorded here as the spec's standing rule, and carried in the guard module so a
future author meets it where the decision is made. An artifact that reports a
**raw float measurement alongside its own "meaningfully nonzero" threshold**
must clamp sub-threshold values to a fixed sentinel at the **serialisation
boundary** before it can be byte-compared. Quantisation is not sufficient:
`float(f"{v:.6g}")` cannot stabilise a value that is cancellation-scale
numerical residue rather than signal — six significant digits of noise are still
noise (measured 2026-08-30, PR #56: the identical revision run twice against
numpy 1.26.4 produced two byte-exact results on `principal_axis`-family paths).
`segfacet.observed_range.emission_range` is the shipped example: a covered but
not-`informative` population emits `(0.0, 0.0, 0.0, 0.0)` while
`PopulationRange` keeps the raw measurement for every caller that classifies on
it. Four other grounds make byte comparison legitimate — floats that are exact
declared parameters or exact binary values rather than measurements;
hand-written literals serialised straight through; a binary fixture with an
exact payload; and an integrity pin with no fresh side at all. Every allowlist
entry names its ground and carries a one-line reason.

### The consumer-survey rule

Also recorded here and in the guard module: a spec that changes a feature the
reference artifact aggregates must survey its consumers **mechanically** —
`grep -l build_and_write_default tests/` — never by hand-listing. Item 123's
recalibration is the precedent: the same four-line comparison exists in four
unrelated modules, and hand-listing found three of them.

**Not in scope.** No feature, extractor, rule or threshold changes. No committed
artifact is regenerated or edited — every artifact this item names is read only.
The guard is a static classifier over test *sources*; it does not execute the
comparisons it classifies. `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` keeps its
existing meaning and its existing AC4 survey; this item adds a structure beside
it rather than repurposing it.

## Acceptance Criteria

- [ ] **AC1: the helper exists and is exported.**
  `segfacet.synth.golden.assert_matches_committed_artifact` exists, is listed in
  that module's `__all__`, and is re-exported from `segfacet.synth`.

- [ ] **AC2: a 1-ULP float difference passes.** Given a parsed structure equal to
  a committed artifact except that one float leaf differs by one ULP,
  `assert_matches_committed_artifact` returns without raising.

- [ ] **AC3: a differing string fails.** A structure differing from the committed
  artifact only in a string leaf raises `AssertionError`.

- [ ] **AC4: a differing bool fails, and `True` is never `1.0`.** A structure
  differing only in a bool leaf raises `AssertionError`, and so does one where a
  committed `true` is met by a fresh `1` or `1.0`.

- [ ] **AC5: a missing or extra key fails.** A structure with one key absent
  from — or one key extra to — the committed artifact raises `AssertionError`.

- [ ] **AC6: list order is exact.** A structure whose list elements are a
  permutation of the committed artifact's raises `AssertionError`.

- [ ] **AC7: the fresh side accepts a path or a parsed object.** Called with a
  `Path`/`str` to a freshly written JSON file, and called with the already-parsed
  equivalent, the helper reaches the same verdict; the committed side is always a
  path, read as UTF-8 and parsed as JSON.

- [ ] **AC8: a missing committed artifact fails loudly.** When the committed path
  does not exist the helper raises `FileNotFoundError` naming that path — it does
  not skip, does not pass, and does not write the file.

- [ ] **AC9: the failure message locates the difference.** The `AssertionError`
  message names the committed artifact's path and the JSON pointer of the first
  differing leaf, together with both values.

- [ ] **AC10: the helper's verdict agrees with `reports_close`.** Over a table of
  structural cases, `assert_matches_committed_artifact` raises `AssertionError`
  if and only if `reports_close` on the same two parsed structures is `False`.

- [ ] **AC11: the four existing comparisons go through the helper.**
  `tests/test_063_reference_intensity.py`,
  `tests/test_081_reference_morphology.py`,
  `tests/test_120_leave_one_out_offset.py` and
  `tests/test_123_recalibrate_and_regenerate.py` call the helper for their
  fresh-vs-committed comparison, and no module under `tests/` calls
  `reports_close` directly on a structure loaded from a committed artifact.
  (Fresh-vs-fresh `reports_close` calls are untouched.)

- [ ] **AC12: the allowlist is structured and reasoned.** A module-level
  allowlist exists in which every entry carries a repo-relative path or glob, a
  `ground` drawn from a closed vocabulary, and a non-empty single-line `reason`;
  a test asserts all three fields are populated for every entry and that every
  `ground` is a member of the vocabulary.

- [ ] **AC13: no stale allowlist entry.** Every allowlist path or glob matches at
  least one file present in the working tree.

- [ ] **AC14: every allowlisted path is line-ending pinned.** Each allowlist path
  or glob is covered by a `.gitattributes` rule — `text eol=lf` for text
  artifacts, `binary` for binary ones.

- [ ] **AC15: the classifier reports zero violations on the tree as it stands.**
  Run over every module under `tests/`, the classifier finds no byte-exact
  fresh-vs-committed comparison whose committed artifact is outside the
  allowlist.

- [ ] **AC16: an off-allowlist comparison is classified as a violation.** A
  synthetic module source asserting byte equality between a freshly written file
  and `src/segfacet/reference/reference_default.json` is classified as a
  violation by the classifier.

- [ ] **AC17: the violation message names the helper.** The guard's failure
  message contains the string `assert_matches_committed_artifact`.

- [ ] **AC18: an unchanged-fence is not a violation.** A synthetic module source
  of the shape `before = P.read_bytes()` … `assert P.read_bytes() == before`,
  where `P` resolves to a committed path, is classified as *not* a violation —
  both operands come from the same committed file within the same run.

- [ ] **AC19: a fresh-vs-fresh comparison is not a violation.** A synthetic
  module source comparing the bytes of two files written under `tmp_path` in the
  same run is classified as *not* a violation.

- [ ] **AC20: `reference_default.json` is excluded by name.**
  `src/segfacet/reference/reference_default.json` does not appear in the
  allowlist, and the guard module records why (full-precision computed
  statistics; the four comparisons against it use the helper).

- [ ] **AC21: the `reference_verse_v1` integrity pin is allowlisted by path.**
  `src/segfacet/reference/reference_verse_v1.json` is an allowlist entry with
  ground `integrity-pin`; the entry is keyed by the artifact path, not by the
  name or location of the test that consumes it.

- [ ] **AC22: both standing rules are recorded where an author meets them.** The
  guard module records the emission-clamp rule naming
  `segfacet.observed_range.emission_range`, and the consumer-survey rule naming
  the literal command `grep -l build_and_write_default tests/`.

- [ ] **AC23: item 111's `.gitattributes` survey still holds.**
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` and
  `test_ac4_survey_every_byte_exact_fixture_family_is_pinned` keep their existing
  meaning and pass unchanged.

## Assumptions

- **The helper is named `assert_matches_committed_artifact`** and lives in
  `src/segfacet/synth/golden.py` beside `reports_close`, which already owns
  `GOLDEN_REL_TOL`/`GOLDEN_ABS_TOL` and `check_case_golden`. The queue's phrase
  "a test utility beside `reports_close`" is read as *the same module*, not
  `tests/`: every consumer already imports `reports_close` from there, and
  keeping the pair together means the builder owns one production surface while
  the test-writer owns the guard. An assert-style helper (rather than a
  predicate) is chosen so the failure message — AC9 — is the reason to reach for
  it.
- **The allowlist and classifier live in a new `tests/committed_artifact_guard.py`**,
  imported by `tests/test_111_golden_guard.py` (which gains the enforcement test)
  and by this item's own test module. A static analyser over test sources does
  not belong in shipped library code, and `tests/synthetic.py` /
  `tests/report_format_fixture.py` are the established precedent for a
  non-`test_*` helper module under `tests/`. "Extending
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` into an enforced allowlist" is honoured in
  substance: the existing tuple keeps its `.gitattributes` job (AC23) and the new
  allowlist carries the ground + reason per entry.
- **The classifier is precise, not exhaustive** — the same contract engine
  1.19.0's fixture lint declares. It resolves an operand to a committed path only
  through: a string literal, a module-level constant built from `Path(__file__)`
  / a `_REPO_ROOT`-style constant joined with literal segments, a local variable
  assigned from one of those in the same function, and the recognised read shapes
  `.read_bytes()`, `.read_text(...)` and
  `hashlib.sha256(<path>.read_bytes()).hexdigest()`. Anything it cannot resolve
  (a loop variable, a function argument, a path built from `tmp_path`, a value
  reached through `json.loads`) is skipped **in silence**. A reported violation
  is therefore authoritative; a clean run is not a proof of absence. This
  limitation is stated in the guard module's docstring.
- **A comparison counts as fresh-vs-committed when exactly one operand resolves
  to a committed path** and the other does not resolve to the *same* committed
  path. This is what keeps the ~6 existing "committed file untouched" fences
  (`tests/test_056_eval_report.py:666-673`,
  `tests/test_083_refresh_reference.py:297-303`, and the `test_082`/`test_090`/
  `test_093`/`test_125` equivalents) out of the violation set — AC18.
- **Item 128 has not landed.** It relocates
  `test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged`
  to a test named for the artifact, beside `reference/artifact.py`'s tests.
  Because the allowlist is keyed by **fixture path**
  (`src/segfacet/reference/reference_verse_v1.json`), 128 moves the consuming
  test without changing the allowlisted entry, and this item needs no edit when
  it lands — AC21 pins exactly that. If 128 lands first, nothing here changes; if
  it lands after, nothing here needs revisiting.
- **The allowlist inventory is the post-item-126 one.** Item 126 retired the nine
  `tests/corpus/golden/*.json` snapshots and the two `tests/golden/0NN_*.json`
  snapshots and replaced them with `tests/golden/report_format_contract.json`;
  the retired paths are absent from the allowlist and the format fixture is on it
  with ground `hand-written-literals`.
- **The ground vocabulary is closed** at five members:
  `exact-parameter-floats`, `emission-clamped`, `hand-written-literals`,
  `binary-fixture`, `integrity-pin`. Adding a sixth is a deliberate edit an
  author must justify, which is the point.
- **`docs/aide/golden-decision-table.md`** stays in
  `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` (it is byte-read and LF-pinned) but is
  **not** an allowlist entry: nothing regenerates it and compares fresh bytes
  against the committed copy. Item 134's generated companion artifact will be a
  new allowlist candidate; that is 134's call, not this item's.

## Implementation Steps

1. **Helper** — in `src/segfacet/synth/golden.py`, beside `reports_close`:
   - Add a private `_first_difference(a, b, *, rel_tol, abs_tol) -> Optional[Tuple[str, object, object]]`
     that walks the two structures with exactly `reports_close`'s rules (bool
     identity first, then dict key sets, then list length + order, then
     `math.isclose` on numeric leaves, then `==`) and returns the JSON pointer of
     the first divergence with both values, or `None`.
   - Add `assert_matches_committed_artifact(fresh, committed_path, *, rel_tol=GOLDEN_REL_TOL, abs_tol=GOLDEN_ABS_TOL) -> None`:
     resolve `fresh` (a `Path`/`str` is read UTF-8 and `json.loads`-ed; anything
     else is used as-is), read and parse `committed_path` (letting
     `FileNotFoundError` propagate with the path in its message), then raise
     `AssertionError` naming the committed path, the pointer, and both values
     when `_first_difference` returns non-`None`.
   - Docstring: state that byte comparison against a committed artifact is the
     wrong default and why (item 078), and point at the guard module for the
     allowlist. Add the name to `__all__` and to
     `src/segfacet/synth/__init__.py`'s import list and `__all__`.
2. **Migrate the four call sites** to `assert_matches_committed_artifact`,
   deleting the open-coded `json.loads` pair in each. Leave every
   fresh-vs-fresh byte-identity assertion in those modules untouched — those are
   determinism checks and stay byte-exact.
3. **Guard module** — new `tests/committed_artifact_guard.py`:
   - `AllowlistEntry` (path/glob, ground, reason) and the allowlist tuple below.
   - `GROUNDS`, the closed vocabulary.
   - `classify_module(source, module_path) -> list[Violation]`: `ast.parse` the
     source, walk every `Compare` with `Eq`/`NotEq`, resolve each operand per the
     Assumptions' resolution rules, and emit a violation for each comparison with
     exactly one committed-resolving operand whose path matches no allowlist
     entry. `iter_violations(tests_dir)` maps it over `tests/*.py`.
   - `violation_message(violations) -> str`, containing
     `assert_matches_committed_artifact` and, per violation, the module, line and
     committed path.
   - Module docstring: the emission-clamp rule (naming
     `segfacet.observed_range.emission_range`), the consumer-survey rule (naming
     `grep -l build_and_write_default tests/`), the precise-not-exhaustive
     limitation, and the `reference_default.json` exclusion and its reason.
4. **Enforcement test** — add to `tests/test_111_golden_guard.py` a test calling
   `iter_violations` over `tests/` and asserting it is empty, failing with
   `violation_message(...)`. Leave `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` and its
   AC4 survey as they are.

**The allowlist** (measured 2026-08-31; float-leaf counts from a walk of each
committed JSON):

| path / glob | ground | reason |
|---|---|---|
| `tests/corpus/manifest.json` | `exact-parameter-floats` | 36 float leaves, all declared generator parameters or exact binary values (`6.0`, `1.0`); no computed measurement. |
| `tests/corpus/intensity/manifest.json` | `exact-parameter-floats` | Same generator, 16 float leaves, all exact. |
| `tests/corpus/094_pre_migration_snapshot.json` | `exact-parameter-floats` | 285 float leaves, all affine/spacing components that are exact binary values; the array payloads are carried as digests, not floats. |
| `tests/corpus/fixtures/*.nii.gz` | `binary-fixture` | Integer label and scan volumes; gzip of an exact byte payload, pinned `binary` in `.gitattributes`. |
| `tests/corpus/intensity/fixtures/*.nii.gz` | `binary-fixture` | Same, for the intensity corpus. |
| `docs/aide/feature_catalogue.generated.json` | `emission-clamped` | Observed-range floats are quantised to six significant figures and sub-floor noise is clamped to `0.0` at emission (`emission_range`, item 124). |
| `docs/aide/feature_catalogue.generated.md` | `emission-clamped` | The rendered form of the same clamped values. |
| `tests/golden/report_format_contract.json` | `hand-written-literals` | Item 126's feature-value-free format fixture: every number is a literal serialised straight through, so the comparison is a formatting guarantee, not a measurement. |
| `src/segfacet/reference/reference_verse_v1.json` | `integrity-pin` | A released production artifact compared against a recorded digest; there is no freshly computed side, so no cross-platform recomputation is involved and a change must be deliberate. |

## Authorised paths

**May change:**

- `src/segfacet/synth/golden.py` — the helper and its docstring (AC1-AC10).
- `src/segfacet/synth/__init__.py` — re-export (AC1).
- `tests/committed_artifact_guard.py` — new: allowlist, classifier, recorded
  rules (AC12-AC22).
- `tests/test_111_golden_guard.py` — the enforcement test (AC15, AC17); the
  existing `_KNOWN_BYTE_EXACT_FIXTURE_FAMILIES` block is left as-is (AC23).
- `tests/test_127_committed_artifact_tolerance.py` — new: this item's tests.
- `tests/test_063_reference_intensity.py` — migrate one comparison (AC11).
- `tests/test_081_reference_morphology.py` — migrate one comparison (AC11).
- `tests/test_120_leave_one_out_offset.py` — migrate one comparison (AC11).
- `tests/test_123_recalibrate_and_regenerate.py` — migrate one comparison (AC11).
- `docs/aide/items/127-tolerance-by-construction-for-committed.md` — this spec.

**Asserts against:**

- `tests/corpus/manifest.json`, `tests/corpus/intensity/manifest.json`,
  `tests/corpus/094_pre_migration_snapshot.json`,
  `tests/corpus/fixtures/*.nii.gz`, `tests/corpus/intensity/fixtures/*.nii.gz`,
  `docs/aide/feature_catalogue.generated.json`,
  `docs/aide/feature_catalogue.generated.md`,
  `tests/golden/report_format_contract.json`,
  `src/segfacet/reference/reference_verse_v1.json` — AC13 pins that each
  allowlist entry still matches a file present in the tree; read only, never
  regenerated or edited.
- `src/segfacet/reference/reference_default.json` — read by AC2/AC10's helper
  cases and by AC16's synthetic violation; AC20 pins its absence from the
  allowlist. Never regenerated or edited.
- `src/segfacet/observed_range.py` — AC22 names `emission_range` as the shipped
  clamp; read only.

## Testing Strategy

`tests/test_127_committed_artifact_tolerance.py` — one focused test per AC.

**Two files are read as input to a property, not pinned**, which is why neither
appears under **Asserts against**. Every module under `tests/` is parsed by
AC15's sweep, which pins no module's content and stays green as those modules
change — the only way a later item trips AC15 is by adding a byte-exact
comparison against a committed artifact, which is the whole point. And
`.gitattributes` is read by AC14, which asserts only that each *allowlisted* path
is covered by a `text eol=lf` or `binary` rule; adding, removing or editing any
other rule leaves AC14 green, and this item changes the file not at all (`aide
scope` enforces that from its absence under **May change**).

**Helper (AC1-AC10).** Build the comparison cases as small in-memory structures
written to `tmp_path`, never by regenerating a committed artifact: AC2 uses
`math.nextafter` on one leaf of a copied structure so the difference is exactly
one ULP; AC3-AC6 mutate one string, one bool, one key and one list order
respectively; AC4 additionally asserts `True` vs `1` and `True` vs `1.0` both
fail. AC7 runs the same structure through both entry shapes and asserts the two
verdicts agree. AC8 points at a non-existent path under `tmp_path` and asserts
`FileNotFoundError` (not a skip, not a pass) with the path named, and asserts
the file was not created. AC9 asserts the message contains the committed path
and the pointer of the injected difference. AC10 drives a table of ~12 case
pairs and asserts `raises(AssertionError) == (not reports_close(a, b))` for each.

**Classifier (AC15-AC19).** Exercise `classify_module` against **synthetic
module sources** written to `tmp_path` — never by adding a real violating
comparison to the suite: the off-allowlist case (AC16), the unchanged-fence
shape (AC18), the fresh-vs-fresh shape (AC19). AC15 runs the real sweep over
`tests/`. AC17 asserts on `violation_message`'s text for AC16's violation.

**Allowlist (AC12-AC14, AC20-AC22).** Data-driven over the allowlist tuple:
every field populated and every ground in the vocabulary; every glob resolves to
≥1 existing file; every path covered by a `.gitattributes` rule (`text eol=lf`
or `binary`). AC20/AC21 assert one absence and one presence by path. AC22 greps
the guard module's docstring for `emission_range` and for
`grep -l build_and_write_default tests/`.

**Adversarial / edge cases.**

- A test source that is not valid Python (or is empty) — the classifier reports
  no violation and does not raise.
- A comparison whose operands are entirely unresolvable (a loop variable, a
  function argument) — skipped in silence, no violation, no crash; this pins the
  documented precise-not-exhaustive contract.
- `assert_matches_committed_artifact` on a committed artifact that is present but
  empty or not valid JSON — raises cleanly (`json.JSONDecodeError`), not a silent
  pass.
- Deeply nested and empty containers (`{}`, `[]`, `{"a": []}`) — pointer
  reporting is well-defined and the helper agrees with `reports_close`.
- A `NaN`/`Infinity` leaf — the helper's verdict still agrees with
  `reports_close` (AC10's table includes one), so the two cannot drift apart.
- Determinism: `classify_module` over the same source twice returns identical,
  identically ordered violations.

**Existing tests to reconcile.** The four migrated modules'
`reports_close`-based tests (`test_063::test_ac15_bundled_artifact_regenerates_byte_identically`,
`test_081`'s AC17 regeneration test,
`test_120::test_ac28_reference_default_matches_fresh_build_within_tolerance`,
`test_123::test_ac21_reference_default_matches_fresh_build_within_tolerance`)
keep their names and their meaning — only the comparison call changes, and each
must still pass. `tests/test_111_golden_guard.py`'s AC1-AC9 and its adversarial
tests must pass unchanged (AC23). No existing test pins the absence of
`assert_matches_committed_artifact` from `segfacet.synth`'s public surface
(`tests/test_126_golden_retirement.py:598-608` asserts only that `GOLDEN_DIR`
and `GOLDEN_DIRNAME` are *not* exported), so adding the name breaks nothing.
`tests/test_115_stage26_validation.py`'s AC8 caps the corpus at exactly one
sha256-versus-hardcoded-literal fence — this item adds none, and AC21
allowlists that one fence's artifact rather than duplicating it.

## Validation

Beyond the unit suite, replay the guard the way item 135 will, in the working
tree rather than on a branch:

1. Append to a scratch copy of a test module (e.g. `cp
   tests/test_120_leave_one_out_offset.py /tmp/...`, or a temporary
   `tests/test_zz_scratch.py`) a comparison of the shape
   `assert dest.read_bytes() == default_artifact_path().read_bytes()` after a
   `build_and_write_default(dest)`.
2. Run `.venv/bin/python -m pytest tests/test_111_golden_guard.py -k allowlist`
   and confirm it **fails**, that the message names the scratch module and line,
   and that it contains `assert_matches_committed_artifact`.
3. Delete the scratch file and confirm the guard is green again.

No `[validation]` profile is required — the guard is pure static analysis over
test sources and runs anywhere the suite runs.

## Dependencies

- **Item 126** (✅) — executed the golden retirement. The allowlist describes the
  post-retirement inventory: the nine `tests/corpus/golden/*.json` snapshots and
  the two `tests/golden/0NN_*.json` snapshots are gone and
  `tests/golden/report_format_contract.json` is the surviving entry.

**Downstream:** item 128 relocates the `reference_verse_v1` integrity pin to a
test named for the artifact; because the allowlist is keyed by fixture path,
that move needs no edit here. Item 134's generated decision-table companion is a
future allowlist candidate. Item 135 replays this item's guard on a scratch
branch as part of the Stage 29 acceptance.

## Decisions & Trade-offs

- **`AllowlistEntry` for the format fixture is keyed by the `.gitattributes`
  glob, not the filename.** `tests/golden/*.json` (matching the existing
  `.gitattributes` line verbatim), not the spec table's illustrative
  `tests/golden/report_format_contract.json`, because AC14's check is a plain
  string `line.startswith(entry.path)` over `.gitattributes` text — a literal
  filename entry does not match a glob line that begins with `*`. No AC pins
  the exact string for this entry, so this substitution is free. `AC13`
  (`REPO_ROOT.glob(entry.path)`) still resolves the glob to the one file that
  exists.

- **`src/segfacet/reference/reference_verse_v1.json`'s allowlist entry cannot
  satisfy AC14 as written, and this is a real spec/`.gitattributes` gap, not
  an implementation bug.** AC21 requires the entry's `path` to equal the
  literal string `"src/segfacet/reference/reference_verse_v1.json"` exactly.
  `.gitattributes` pins that file only via the glob line
  `src/segfacet/reference/reference_verse_*.json text eol=lf` — a *different*
  string that does not start with the literal AC21 requires character-for-
  character (`*` vs `v1` at the same offset), so AC14's `line.startswith(entry.path)`
  check fails for this one entry regardless of how the allowlist is built.
  Fixing it needs a `.gitattributes` line that literally begins with
  `src/segfacet/reference/reference_verse_v1.json` (e.g. an additive,
  behaviour-preserving pin alongside the existing glob — `git check-attr`
  already resolves `eol=lf` for this file via the glob, so this would not
  change any git-checkout behaviour). `.gitattributes` is not in this item's
  **Authorised paths**, so it was left untouched rather than silently
  widening scope; the entry itself is built with the literal path AC21
  requires, and this known AC14 failure was verified directly (not just
  inferred) before being recorded here. Resolving it needs either the spec to
  add `.gitattributes` to **May change** with that one additive line, or a
  human decision to relax AC14/AC21's coupling.

- **`_is_file_root_chain` requires at least two `.parent` steps past
  `Path(__file__)`, not "any depth."** A single `.parent` denotes a module's
  *own* containing directory (`tests/`, for every module directly under it),
  not the repo root, and the classifier has no notion of a module's real
  on-disk depth (documented limitation). Treating a one-`.parent` chain as
  "the root" produced a real false positive on
  `tests/test_126_golden_retirement.py`'s `_TESTS_DIR = Path(__file__).resolve().parent`
  → `_FORMAT_FIXTURE = _TESTS_DIR / "golden" / "report_format_contract.json"`,
  which resolves to `golden/report_format_contract.json` (missing the
  `tests/` prefix every allowlist entry assumes) under the naive model.
  Requiring ≥2 `.parent` steps matches every real `_REPO_ROOT`/`REPO_ROOT`
  constant actually used to reach committed artifacts across `tests/`
  (verified 2026-08-31: `iter_violations` over the real tree drops from 1
  false positive to 0 with this change) and still resolves the item's own
  three-`.parent` alias-resolution edge case (AC-adjacent adversarial test).

- **Local-variable "read-result" tracking (`local_reads`) was added beyond the
  literal Implementation Steps text** to make the AC18 "unchanged fence" idiom
  (`before = p.read_bytes()` ... `assert p.read_bytes() == before`) resolve
  correctly: `before` itself is not a second `.read_bytes()` call, so without
  tracking that it was *derived from* one, the classifier would see only one
  resolvable operand and misclassify the fence as a violation. This is the
  concrete mechanism behind the Assumptions' "local variable assigned from
  one of those in the same function" clause.
