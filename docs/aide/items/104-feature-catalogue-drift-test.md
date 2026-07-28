# Item 104 — Feature-catalogue drift test

> **Created:** 2026-07-27 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 19 — Generated Feature & Rule Catalogue + Steering Review (G7, G8)
> **Queue:** [`../queue/queue-015.md`](../queue/queue-015.md) · Item 104
> *(second of four; item 103 built the catalogue this item guards, item 105 is the
> golden-file decision table, item 106 closes the stage)*
> **Objectives:** G7 (the feature set must be *reviewable and verifiable* — a
> generated catalogue nothing re-checks on every CI run decays into the same
> hand-maintained table it replaced)
> **Suggested branch:** `aide/104-feature-catalogue-drift-test`

---

## Description

Item 103 replaced `FEATURE_CATALOG`'s hand-typed literals with a generator
(`src/segfacet/catalogue.py` + `src/segfacet/feature_docs.py`) and made a
catalogue/record mismatch raise: `build_catalogue(strict=True)` raises
`FeatureDocMissing` when a realised leaf path has no `FEATURE_DOCS` entry
(item 103 AC16) and `CatalogueError` when a `FEATURE_DOCS` key matches no
realised path (AC17).

That mechanism lives in **production code**. Nothing yet guarantees a CI run
*executes* it, and nothing guarantees that when it does fire the result is a
legible, actionable failure rather than an incidental collection-time error in
whichever unrelated module happened to import the catalogue first. This item
closes that gap with one new test module, `tests/test_104_feature_catalogue_drift.py`,
and **no production change at all**.

The module is built in two layers, deliberately:

1. **A pre-diagnosed structural comparison** that never raises. It computes the
   realised leaf-path set `U` — the union of `iter_leaf_paths(record)` over
   `iter_driver_records()`, both **imported from `segfacet.catalogue`**, never
   reimplemented — and compares it in **both directions** against the authored
   documentation key set `D = set(segfacet.feature_docs.FEATURE_DOCS)` (which
   item 103 AC17 pins as exactly equal to `U` on a healthy tree) and against the
   committed artifact `docs/aide/feature_catalogue.generated.json`. Every
   difference is rendered by one shared reporter into a message that **names each
   offending path**, says which direction detected it, names the file to edit and
   the command to regenerate. The assertion is `assert message is None, message`
   — never a bare `assert set_a == set_b`.
2. **An exercise of the production mechanism itself.** `build_catalogue(strict=True)`
   is called inside a guard that converts `CatalogueError` (and its
   `FeatureDocMissing` subclass) into a `pytest.fail` carrying the exception text,
   so the strict path is provably reached under CI and, when it fires, reports as
   a *named test failure* rather than an error escaping from a fixture.

Layer 1 exists because layer 2 alone gives a raised exception whose diagnosis
depends on the generator's message quality and whose failure location is a
fixture. Layer 2 exists because layer 1 alone would let the shipped strict-mode
guard rot untested. The redundancy is intentional and recorded in Decisions &
Trade-offs.

The module also carries **self-guards** — it asserts against its own source that
it imports the shared walk, contains no hand-typed path table, hard-codes no
absolute path, and does no byte/hash comparison of a committed file. The first
two exist because item 103's spec names a second copy of the walk as "exactly how
the two would drift"; the last two exist because this repo has been burnt three
times by exactly those two patterns in test code (`docs/aide/insights.md`, items
099–101).

**What this item is NOT:**

- **Not a production change.** No file under `src/segfacet/**`, `scripts/**`,
  `.github/**`, `.gitattributes` or `docs/aide/feature_catalogue.generated.*` is
  touched (AC22). The item's entire deliverable is one test module.
- **Not a re-test of item 103's generator.** `tests/test_103_feature_catalogue.py`
  owns AC-by-AC coverage of `normalise_leaf_path`, the tracer, the AST scanners,
  the evidence tags, byte-reproducibility of the artifacts and the status-report
  render path. This module asserts exactly one property — catalogue ≡ record —
  and asserts it in the shape CI needs.
- **Not a byte-identity check.** Item 103's AC19 owns "the committed artifacts
  match a fresh regeneration byte-for-byte". This module compares **parsed path
  sets**, so it is immune to line-ending and path-separator differences across CI
  runners (AC5, and see Decisions).
- **Not the keep/retire judgment** (item 105) and **not the stage validation**
  (item 106). Item 106 replays this module's "prove it can fail" rehearsal; this
  item only has to make that rehearsal possible and repeatable.

### The four comparisons, stated once

Let `U` = the realised set, `D` = `set(FEATURE_DOCS)`, `C` = the committed
artifact's entry paths and `C_record` = those of its entries with
`origin == "record"`.

| # | Assertion | Detects |
|---|---|---|
| 1 | `U - D` is empty | a feature landed in the record with no documentation |
| 2 | `D - U` is empty | a documented feature is no longer produced |
| 3 | `U - C` is empty | the committed artifact is stale (missing a realised path) |
| 4 | `C_record - U` is empty | the committed artifact carries an orphaned record-tier entry |

Comparisons 1/2 are the primary drift check (they are what strict mode itself
tests, restated as importable data). 3/4 additionally catch "the code and
`feature_docs.py` were both updated but nobody re-ran the generator", which 1/2
cannot see. `origin == "augmented"` entries are exempt from direction 4 by
design — item 103 AC6 confines its both-directions equality to the record tier —
and AC18 pins that exemption explicitly so a later refactor cannot silently
widen or vacate it.

## Acceptance Criteria

- [ ] **AC1: the drift module exists and is ungated.**
  `tests/test_104_feature_catalogue_drift.py` exists and imports cleanly. An AST
  scan of its own source finds **no** `pytest.importorskip` call, **no**
  `pytest.mark.skip`/`skipif`/`xfail` decorator, and no `os.environ`-conditional
  skip; its import statements name only standard-library modules, `pytest`, and
  `segfacet.*` modules — never `radiomics`, `cupy`, `docker` or `subprocess`. It
  therefore runs in the default `python -m pytest` invocation with no optional
  dependency present.

- [ ] **AC2: the walk is imported, never reimplemented.** An AST scan of the
  module's own source finds an `ImportFrom` of `segfacet.catalogue` binding both
  `iter_leaf_paths` and `iter_driver_records`, and the module defines no function
  of its own that recurses over a record (no function in the module both takes a
  record-shaped argument and calls itself).

- [ ] **AC3: no hand-typed path table.** No list/tuple/set/frozenset display
  anywhere in the module's AST contains **12 or more** string constants that look
  like leaf paths (contain a `.` or the substring `[]`). The largest legitimate
  such literal in the module is AC7's six-path sentinel tuple.

- [ ] **AC4: no absolute path literal.** No string constant in the module's AST
  starts with `/` or `\\`, or matches a Windows drive-letter prefix (`^[A-Za-z]:`).
  The repository root is resolved as `Path(__file__).resolve().parents[1]` and the
  committed artifact is addressed relative to it.

- [ ] **AC5: no byte or hash comparison of a committed file.** The module's
  imports do not include `hashlib`, and its AST contains no call to
  `Path.read_bytes`. Byte-identity of the generated artifacts is item 103 AC19's
  job; this module compares parsed path sets only.

- [ ] **AC6: `covered_paths()` is the union over the driver set, and is
  deterministic.** The module exposes `covered_paths() -> frozenset[str]`
  returning the union of `iter_leaf_paths(record)` over every
  `(driver_id, record)` pair from `iter_driver_records()`. Two calls return equal
  frozensets.

- [ ] **AC7: the check cannot pass vacuously.** `iter_driver_records()` yields at
  least **3** pairs; `covered_paths()` is non-empty and contains all six sentinel
  paths `features_version`,
  `per_label.{label}.geometry.touches_superior`,
  `per_label.{label}.components.fragmentation_index`,
  `relationships.out_of_order_labels[]`,
  `stage3.per_label_offsets[].offset_mm`,
  `overlaps[].overlap_voxels`; and `set(FEATURE_DOCS)` is non-empty. (Each
  sentinel is pinned by item 103 AC4/AC5, so this cannot rot silently.)

- [ ] **AC8: direction 1 — an undocumented realised feature fails, naming it.**
  On the current tree `covered_paths() - set(FEATURE_DOCS)` is empty. Given a
  realised set carrying one path absent from the documented set, `drift_report`
  returns a non-`None` message containing that exact path verbatim and wording
  identifying it as realised-but-undocumented.

- [ ] **AC9: direction 2 — a documented feature no longer produced fails, naming
  it.** On the current tree `set(FEATURE_DOCS) - covered_paths()` is empty. Given
  a documented set carrying one path absent from the realised set,
  `drift_report` returns a non-`None` message containing that exact path verbatim
  and wording identifying it as documented-but-no-longer-produced.

- [ ] **AC10: both directions are reported together, completely and in sorted
  order.** Given inputs that differ in both directions simultaneously, the single
  message returned by `drift_report` names **every** path from both differences
  under two distinct labels, each group listed in `sorted()` order, with no
  truncation or ellipsis. `drift_report` returns `None` — never an empty string —
  when both differences are empty.

- [ ] **AC11: every drift message is actionable.** Every non-`None` message
  `drift_report` can return contains the literal string
  `src/segfacet/feature_docs.py` and the literal regeneration command
  `python -m segfacet.catalogue`.

- [ ] **AC12: the strict production mechanism is exercised and never escapes as
  an error.** The module exposes `strict_build_message(build_fn=...) -> str | None`
  which calls its build function and returns `None` on success or, on
  `CatalogueError` (including `FeatureDocMissing`), a message containing
  `type(exc).__name__` and `str(exc)`. Called with the real
  `functools.partial(build_catalogue, strict=True)` on the current tree it returns
  `None`; called with a stub raising
  `FeatureDocMissing("undocumented leaf path: per_label.{label}.geometry.zzz")` it
  returns a message containing that exact path; called with a stub raising
  `CatalogueError("stale FEATURE_DOCS key: relationships.gone")` it returns a
  message containing `relationships.gone`. No `CatalogueError` propagates out of
  any test or fixture in the module.

- [ ] **AC13: the committed artifact exposes the fields the check needs.**
  `docs/aide/feature_catalogue.generated.json` parses as JSON, and every entry it
  yields has a non-empty `str` `path` and a `str` `origin` drawn from
  `{"record", "augmented"}`. If either field is missing the failure message names
  the entry and states that item 103's `catalogue_to_dict` must emit `path` and
  `origin`.

- [ ] **AC14: the artifact reader tolerates either serialisation layout.**
  `iter_committed_entries(doc)` yields every entry mapping when entries are a
  top-level `"entries"` list, and likewise when they are nested under
  `"groups"[*]["entries"]`. Given a document with neither, it fails with a message
  listing the document's actual top-level keys.

- [ ] **AC15: direction 3 — a stale committed artifact missing a realised path
  fails, naming it.** On the current tree `covered_paths() - C` is empty (where
  `C` is the committed artifact's entry-path set). Given an artifact path set
  missing one realised path, the reported message names that path and the
  regeneration command.

- [ ] **AC16: direction 4 — an orphaned record-tier artifact entry fails, naming
  it.** On the current tree `C_record - covered_paths()` is empty (where
  `C_record` is the artifact's entries with `origin == "record"`). Given an
  artifact carrying one record-tier path absent from the realised set, the
  reported message names that path and the regeneration command.

- [ ] **AC17: the committed artifact has no duplicate paths.** The number of
  entries yielded by `iter_committed_entries` equals the size of their path set;
  on failure the message names each repeated path.

- [ ] **AC18: the augmented-tier exemption never excuses a record-tier path
  — vacuously true today, and this item asserts that fact rather than assuming
  it.** **Every** path in `C - covered_paths()` (which is empty on the current
  tree per item 103's builder decision — see Assumptions) belongs to an entry
  with `origin == "augmented"`. This item does **not** require at least one
  `origin == "augmented"` entry to exist: item 103's committed implementation
  tags every entry `"record"` (a documented, AC6/AC17-forced consequence of
  folding the augmented drivers into `iter_driver_records()`'s union rather
  than a second code-level tier), so `C - covered_paths()` is empty and the
  exemption is exercised zero times today. The AC stays meaningful as a
  forward-compatible ratchet: if a future item introduces a real
  `origin == "augmented"` entry, this AC still catches one that isn't excused
  correctly.

- [ ] **AC19: injected drift is detected end-to-end from real inputs.** Starting
  from the real `covered_paths()` result: adding one synthetic path
  (`per_label.{label}.geometry.zzz_drift_probe`) produces a message naming exactly
  that path and no other path under direction 1; removing one real path produces a
  message naming exactly that path and no other path under direction 2. Both are
  built from local copies of the real sets — no shipped module, mapping or driver
  record is modified.

- [ ] **AC20: nothing shipped is mutated.** A `copy.deepcopy` snapshot of
  `dict(FEATURE_DOCS)` and of the first driver record, taken before the module's
  checks run, still compares equal afterwards; and `FEATURE_DOCS` itself rejects
  item assignment (it is a read-only mapping per item 103's `MappingProxyType`
  wrapping).

- [ ] **AC21: the whole check is idempotent.** Running the module's four
  comparisons twice in one session yields identical results (`None` twice, or the
  identical message string twice) for each.

- [ ] **AC22: the scope fence holds.** This item adds exactly one file,
  `tests/test_104_feature_catalogue_drift.py`, and modifies no other file in the
  repository — in particular nothing under `src/segfacet/**`, `scripts/**`,
  `tests/**` (other than the new module), `tests/corpus/**`, `.github/**`,
  `.gitattributes`, or `docs/aide/feature_catalogue.generated.{json,md}`. Verified
  by the validator from `git diff --name-only <merge-base>..HEAD`, which must list
  only the new test module and this spec — **not** by a byte-hash test (see
  Decisions & Trade-offs).

## Assumptions

Clarify mode for this item was **`interactive`** (Stage 19 carries the human
steering checkpoint), but the queue itself calls item 104 the low-ambiguity item
of the batch and item 103's spec had already settled every load-bearing design
question. **No question was put to the maintainer.** Everything below is either a
fact taken from item 103's committed spec (marked *[103]*) or a spec-author
default.

**Taken as settled from item 103's spec — do not re-litigate:**

- *[103 AC1]* **`segfacet.catalogue` exports `iter_leaf_paths`,
  `iter_driver_records`, `build_catalogue`, `catalogue_to_dict`,
  `CatalogueError` and `FeatureDocMissing` (a subclass of `CatalogueError`).**
  This module imports the first two for the walk and the last two for the strict
  guard, and **never reimplements the walk** — item 103's spec names a second copy
  as "exactly how the two would drift" (AC2, AC3 enforce this mechanically).
- *[103 Assumptions]* **Leaf-path granularity is schema-level**
  (`per_label.<int>` → `per_label.{label}`, list elements → `[]`), measured at 67
  paths for a 5-label corpus case on the current tree. **Neither 67 nor the
  roadmap's 185 is a target this item asserts** — the count is expected to move as
  the feature tree moves; what must not move is exact set equality. No AC in this
  item pins a cardinality other than the non-vacuity floors in AC7.
- *[103 AC6 / Assumptions]* **Coverage is defined against the union of
  `iter_driver_records()`, not a single record.** `overlaps` is empty on all nine
  corpus records and only becomes non-empty on a dedicated driver; `stage3` is
  absent on degenerate maps. This module therefore never builds its own reference
  record from `tests/corpus/**` or `tests/synthetic.py`.
- *[103 AC17]* **`set(FEATURE_DOCS) == U` on a healthy tree**, and `strict=True`
  raises in either direction otherwise. This is what makes comparisons 1 and 2
  above a faithful restatement of strict mode using importable pure data, with no
  dependence on `build_catalogue`'s internal entry construction.
- *[103 AC2]* **`segfacet.feature_docs` is stdlib-only and importable without
  NumPy/SciPy/NiBabel**, and its public mappings are `MappingProxyType`-wrapped
  (AC20's immutability assertion relies on this).
- *[103 Decisions & Trade-offs, builder]* **In the shipped implementation,
  `origin` is always `"record"` — the "two tiers" language in item 103's
  Assumptions describes how the *drivers* are built (real pipeline extraction
  vs. hand-constructed placeholder dataclasses through the existing
  converters), not a second code-level `origin` value. Both `image_features.*`
  and `reference_delta.*` paths are yielded by `iter_driver_records()` (via its
  two augmented drivers) and therefore land in `U`, so under AC6/AC17's literal
  equality every entry `build_catalogue()` produces has `origin == "record"` by
  construction — introducing a real `"augmented"` value would break that
  equality the moment such a path existed. `CatalogueEntry.origin` remains a
  field (forward-compatible), but no entry in the committed artifact carries
  `"augmented"` today. Direction 4 and AC18 are still phrased in terms of the
  exemption (never vacuously dropped) so a future real second tier is still
  caught correctly, but this item asserts no entry currently uses it.
- *[CI]* **`.github/workflows/ci.yml` already runs the bare `python -m pytest`**
  on every push/PR across four legs (ubuntu, windows, numpy 1.26.4, numpy 2.0.2),
  and `pyproject.toml` sets `testpaths = ["tests"]`. "Fails CI" therefore requires
  **no workflow edit** — adding the module is sufficient. AC22 forbids touching
  `.github/**` for this reason.

**Spec-author defaults (the interfaces item 103's spec left open):**

- **`catalogue_to_dict`'s JSON layout is not pinned by item 103.** Its AC18
  pins determinism and the absence of timestamps, and AC24 pins the *Markdown*
  columns, but no AC fixes the JSON document's shape. This item therefore reads
  the artifact through a **tolerant reader** (AC14) accepting a top-level
  `"entries"` list or entries nested under `"groups"[*]["entries"]`, and asserts
  per-entry `path` + `origin` as an explicit precondition with a self-explaining
  failure (AC13). If item 103's realised `catalogue_to_dict` emits neither layout,
  or omits `origin`, the correct response is to **hand back to item 103** (the
  status report and this drift test both need those fields) — not to widen this
  reader further or to weaken the record-tier direction.
- **Whether `iter_driver_records()` yields the two augmented drivers is left
  ambiguous by item 103's AC5/AC17 read together**, so no assertion here depends
  on the answer. Every comparison is phrased to hold under both readings:
  direction 3 is `U - C` (a subset test, not equality), direction 4 filters on
  `entry.origin` from the artifact side, and AC18 tolerates `C - U` being empty.
  The test must never infer a tier from a `driver_id` string.
- **The primary comparison uses `FEATURE_DOCS`, not `build_catalogue(strict=False)`'s
  entries.** Under item 103 AC16 a non-strict build emits an entry (with
  `documented is False`) for an undocumented realised path, so `U ⊆ entries` stays
  true under exactly the drift this item must catch — a comparison against the
  non-strict entry set would be silently vacuous in direction 1. `FEATURE_DOCS` is
  the surface strict mode actually checks and is the one compared here.
- **`build_catalogue` is called exactly once, with `strict=True`, inside the AC12
  guard.** No fixture in this module performs a non-strict build; nothing here
  needs one, and a second full build (tracing ten rules over the driver set plus
  two AST scans) would double the module's runtime for no assertion.
- **The self-guards (AC2–AC5) scan the module's own source**, read as text from
  `Path(__file__)` and parsed with `ast`. This is the pattern
  `tests/test_features_intensity.py` already uses in this repo; it needs no new
  dependency and no committed constant that could rot.
- **The failure-message wording is the spec author's call, constrained only by
  AC11's two literal substrings** (`src/segfacet/feature_docs.py` and
  `python -m segfacet.catalogue`) and AC10's completeness/ordering rule. The
  recommended shape, one block per non-empty direction:
  `"<N> leaf path(s) realised by the record but absent from FEATURE_DOCS:\n  - <path>\n  …\nAdd them to src/segfacet/feature_docs.py, then regenerate: python -m segfacet.catalogue"`.
- **The threshold in AC3 is 12.** It is chosen to sit clear of the six-path
  sentinel tuple (AC7) while catching the realistic regression — someone pasting a
  block of the 67-path catalogue into the test to avoid importing the walk. It is
  a guard-rail, not a measurement, and a future item that legitimately needs a
  longer literal should raise it deliberately rather than delete the guard.

## Implementation Steps

This item writes **no production code**. Its single deliverable lives under
`tests_dir` (`tests/`), and the ordinary builder step is a no-op — see AC22 and
the Testing Strategy note on the split.

1. **Create `tests/test_104_feature_catalogue_drift.py`** with a module docstring
   in the house style used by `tests/test_099_per_mode_metrics.py`: what the module
   guards, the AC1–AC22 map, and the adversarial cases covered.

2. **Imports** — `from __future__ import annotations`; stdlib `ast`, `copy`,
   `functools`, `json`, `re`, `pathlib.Path`; `pytest`; and from `segfacet`:
   `from segfacet.catalogue import (CatalogueError, FeatureDocMissing,
   build_catalogue, iter_driver_records, iter_leaf_paths)` and
   `from segfacet.feature_docs import FEATURE_DOCS`. Nothing else (AC1).

3. **Path constants** — `_TESTS_DIR = Path(__file__).resolve().parent`,
   `_REPO_ROOT = _TESTS_DIR.parent`,
   `_ARTIFACT = _REPO_ROOT / "docs" / "aide" / "feature_catalogue.generated.json"`.
   No absolute literal anywhere (AC4); no `read_bytes`, no `hashlib` (AC5).

4. **Module-level helpers** (the surface the AC tests exercise directly):
   - `covered_paths() -> frozenset[str]` — union of `iter_leaf_paths(record)` over
     `iter_driver_records()` (AC6).
   - `documented_paths() -> frozenset[str]` — `frozenset(FEATURE_DOCS)`.
   - `drift_report(*, realised, documented, realised_label, documented_label) -> str | None`
     — the one reporter every direction routes through; returns `None` iff both
     differences are empty, else the two labelled sorted blocks plus the
     remediation line (AC8–AC11).
   - `strict_build_message(build_fn) -> str | None` — the AC12 guard.
   - `load_committed_catalogue() -> object` and
     `iter_committed_entries(doc) -> list[Mapping[str, object]]` (AC13, AC14).
   - `_module_ast() -> ast.Module` — parses this module's own source for the
     self-guards (AC2–AC5).

5. **Module-scoped fixtures** so the expensive work happens once per session:
   `realised` (calls `covered_paths()`), `documented`, `committed` (parsed
   artifact), `committed_entries`, `committed_paths`, `committed_record_paths`.
   `iter_driver_records()` is consumed exactly once outside the AC6/AC7
   determinism tests, and `build_catalogue` is called exactly once (AC12).

6. **The four direction tests** — each asserts
   `assert message is None, message`, never `assert set_a == set_b`. Direction 1
   and 2 come from one `drift_report(realised=U, documented=D, …)` call; directions
   3 and 4 from a second call parameterised over the artifact sets, with direction
   4's "documented" side filtered to `origin == "record"`.

7. **The strict-mechanism test** — `strict_build_message(functools.partial(build_catalogue, strict=True))`
   must return `None`; the assertion carries the message (AC12).

8. **The self-guard tests** (AC2–AC5) over `_module_ast()`.

9. **The positive-control tests** (AC8/AC9/AC12/AC15/AC16/AC19) — synthetic and
   real-derived drift injected into *local copies* of the sets, and stub build
   functions raising `FeatureDocMissing`/`CatalogueError`. These are what prove the
   module can fail; without them a green run is not evidence.

10. **The hygiene tests** (AC20, AC21) — deepcopy snapshots and a
    run-the-comparison-twice idempotence check.

11. **Do NOT touch** `src/segfacet/**`, `scripts/**`, any other file under
    `tests/**`, `tests/corpus/**`, `.github/**`, `.gitattributes`, or the two
    generated `docs/aide/feature_catalogue.generated.*` artifacts (AC22).

## Testing Strategy

This item's deliverable **is** the test module, so this section describes the
module itself rather than a separate suite over it. The repo's normal split still
applies: the test-writer authors `tests/test_104_feature_catalogue_drift.py`
against the ACs above; the builder's production-code step is deliberately empty
and its only obligation is to confirm the scope fence (AC22) holds.

- **Framework:** `pytest`. One new module,
  `tests/test_104_feature_catalogue_drift.py`. **No existing test module is
  modified** — including `tests/test_103_feature_catalogue.py`, which must stay
  green unmodified.

- **One focused test per AC**, AC1–AC22. The load-bearing ones:
  - **AC12** — if the strict guard is not actually reached, the whole item is
    decorative. Assert both the real call returning `None` *and* the two stub-raise
    paths returning a message naming the offending path.
  - **AC19** — the "proves it can fail" pair. This is the in-suite analogue of the
    manual rehearsal item 106 must perform (Validation, below); if AC19 is written
    as a tautology over synthetic sets only, the module can pass on a tree where
    the real comparison is broken.
  - **AC7** — the anti-vacuity floor. A regression in `iter_driver_records()` that
    yields nothing would otherwise make all four directions trivially green.
  - **AC18** — pins the augmented exemption positively; without it, a refactor
    that widened the exemption to record-tier paths would be invisible.

- **Adversarial / edge cases:**
  - `drift_report` with both sides empty → `None`, not `""`.
  - `drift_report` with one side empty and the other a single element → exactly one
    labelled block, and the *absent* direction's label does not appear in the
    message (no empty "0 paths:" section).
  - `drift_report` given unsorted input containers (a `set` built in scrambled
    insertion order, and a `list` with a duplicate) → identical, sorted, duplicate-free
    output, so a CI diff of the failure text is stable.
  - Path-shaped strings containing `{label}` and `[]` survive verbatim into the
    message (they must be greppable by the maintainer, not escaped or reformatted).
  - `iter_committed_entries` on: a flat `{"entries": [...]}`, a nested
    `{"groups": [{"entries": [...]}, {"entries": []}]}`, `{"groups": []}` (empty →
    empty list, no crash), and `{"unexpected": 1}` (→ failure naming
    `unexpected`).
  - `load_committed_catalogue` when the artifact is absent → a failure message
    naming the expected path and the regeneration command, never a bare
    `FileNotFoundError` traceback. (Item 103 AC19 guarantees the file is committed;
    this is the honest message for a partial checkout.)
  - An artifact entry with `origin` set to an unknown string (e.g. `"synthetic"`)
    → AC13 fails naming that entry, rather than the entry being silently dropped
    from both `C` and `C_record`.
  - A stub build function raising a *non*-`CatalogueError` exception (e.g.
    `ValueError`) → `strict_build_message` does **not** swallow it; it propagates,
    because an unexpected error is a genuine bug and must not be reported as a
    tidy drift message.
  - `covered_paths()` called twice → equal frozensets, and the driver records
    unmutated between the two calls (AC6/AC20 in combination).

- **Determinism / platform hygiene.** This module deliberately performs **no**
  byte-identity or SHA-256 comparison and hard-codes **no** absolute path
  (AC4/AC5), because both patterns have produced Linux-green / Windows-red CI
  breaks in this repo that survived the full spec→test→build→validate→merge cycle:
  see `docs/aide/insights.md` — item 099's hardcoded `/mnt/data/...` glob, items
  099–101's missing `.gitattributes` LF pins, and items 099–101's
  `str(path.relative_to(base))` vs `as_posix()` separator bug. Comparing parsed
  JSON path sets is immune to all three classes. The test-writer must read those
  three entries before adding any file-content assertion to this module.

- **Existing tests to reconcile** (grep sweep for assumptions this item could
  invalidate). Measured on this tree: **no test module references `catalogue`,
  `feature_docs` or `FEATURE_CATALOG` today** (the only non-test hits are
  `src/segfacet/eval/metrics.py` and `scripts/aide_status_report.py`), and this
  item changes no default, threshold or behaviour, so there is nothing to
  reconcile in the usual sense. Confirm rather than assume:
  - `tests/test_103_feature_catalogue.py` — created by item 103, and the only
    module with overlapping subject matter. Its AC6 asserts catalogue↔record
    coverage on the *in-memory* catalogue; this module asserts the same property
    against `FEATURE_DOCS` and against the *committed artifact*, in CI-legible
    form. Both must pass; **neither may be edited by this item**, and an edit to
    `test_103_*.py` is a red flag for the validator.
  - `tests/test_aide_status_report.py` — loads `scripts/aide_status_report.py` by
    path and renders HTML from the same committed JSON. Unaffected (this item adds
    no file it reads), but it must stay green unmodified.
  - Any module asserting a package's `__all__` exhaustively — this item adds no
    module to `src/segfacet/**` and changes no `__all__`.

## Validation

The tests alone do not demonstrate the property the queue actually asks for —
"CI fails on an undocumented feature". That needs the drift to be introduced in
the **real code**, not in a local copy of a set. From the repo root with the venv
bootstrapped:

1. **Baseline.** `.venv/bin/python -m pytest tests/test_104_feature_catalogue_drift.py -ra`
   — all tests pass and the summary reports **0 skipped**, proving the module is
   not environment-gated (AC1 in its live form).

2. **Prove it fails on an undocumented realised feature** (the G7 acceptance
   sentence, and the rehearsal item 106 replays). Add one line to
   `src/segfacet/feature_report.py` inserting a key such as
   `"zzz_drift_probe": 0.0` into the per-label geometry dict, then re-run step 1.
   Expected: the direction-1 test and the AC12 strict test both fail, and both
   failure texts contain `per_label.{label}.geometry.zzz_drift_probe` and the
   regeneration command. Then `git checkout -- src/segfacet/feature_report.py` and
   confirm `git status --short` is clean and step 1 is green again.

3. **Prove it fails on a documented feature that is no longer produced.** The
   cheapest faithful probe for this direction is to add a bogus key —
   `relationships.gone_forever` — to `src/segfacet/feature_docs.py`'s
   `FEATURE_DOCS`, which is indistinguishable to the check from a real field whose
   producer was deleted. Re-run step 1. Expected: the direction-2 test and the AC12
   strict test fail, naming `relationships.gone_forever`. Revert with
   `git checkout -- src/segfacet/feature_docs.py`; confirm `git status --short` is
   clean and step 1 green.

4. **Prove it fails on a stale committed artifact.** Delete one entry from
   `docs/aide/feature_catalogue.generated.json` by hand. Re-run step 1. Expected:
   the direction-3 test fails naming that path and the regeneration command, while
   directions 1/2 stay green — demonstrating that the artifact check catches
   something `FEATURE_DOCS` alone cannot. Restore with
   `git checkout -- docs/aide/feature_catalogue.generated.json`.

5. **Full suite.** `.venv/bin/python -m pytest` — green, with item 103's module
   also green and unmodified.

No `[validation]` profile is required: this is a structural check that runs on
the plain CPU venv with **no** optional dependency (PyRadiomics, Docker and GPU
are all irrelevant here, by AC1). If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified. Every step above must leave `git status --short` clean; a
validation run that leaves a probe in the tree is a failed validation.

## Dependencies

- **Item 103** (`src/segfacet/catalogue.py`'s `iter_leaf_paths` /
  `iter_driver_records` / `build_catalogue` / `catalogue_to_dict` /
  `CatalogueError` / `FeatureDocMissing`, `src/segfacet/feature_docs.py`'s
  `FEATURE_DOCS`, and the committed
  `docs/aide/feature_catalogue.generated.json`) — this item is a pure consumer of
  that interface and **cannot start before it lands**. Must be ✅ (or 🚧 with the
  generator module and the committed artifact both present) before this item is
  claimed.
- **Item 035** (`pipeline.extract_feature_record` — the realised record shape both
  the walk and the drift check are ultimately about) — ✅.
- **Items 037–041** (the synthetic perturbation operators `iter_driver_records()`
  builds its records from) — ✅.

**Downstream:** item 106's stage validation replays this module's step-2
rehearsal (deliberately introduce and revert an undocumented field) as the G7
acceptance evidence, and reads its green run as the "drift test passes on the
current tree" half. Item 105's decision table is independent of this item and may
proceed in parallel. Neither blocks this item.

## Decisions & Trade-offs

Recorded by the spec author where item 103's spec or the queue left the choice
open; the builder appends to this section during implementation.

- **Two layers, deliberately redundant.** The structural comparison (directions
  1–4) and the `build_catalogue(strict=True)` guard test overlap: on a healthy tree
  both are green, and on a drifted tree both go red. Keeping both is the point —
  the structural comparison gives a *pre-diagnosed, sorted, complete* message
  (strict mode raises on the first problem it finds), while the strict guard proves
  the **production** mechanism is genuinely reached by CI rather than merely
  believed to work. Dropping either leaves a real gap: without layer 1 a failure is
  an opaque exception from a fixture; without layer 2 the shipped guard is untested
  code.
- **The primary comparison is against `FEATURE_DOCS`, not against
  `build_catalogue(strict=False)`'s entries.** Under item 103 AC16 a non-strict
  build *manufactures* an entry for an undocumented realised path, so comparing `U`
  against the entry set would be green under exactly the drift this item exists to
  catch. `FEATURE_DOCS` is the surface strict mode checks, it is pure stdlib data,
  and item 103 AC17 pins it equal to `U`. See Assumptions.
- **The committed artifact is checked too, and that is not redundant.** Directions
  3/4 catch "the code and `feature_docs.py` were both updated but the generator was
  never re-run", which directions 1/2 structurally cannot see, and they guard the
  exact bytes the HTML status report renders and the maintainer reviews at the
  Stage-19 checkpoint.
- **Parsed path sets, never bytes.** Item 103 AC19 already owns byte-identity of
  the two generated artifacts. Repeating a byte or SHA-256 comparison here would
  re-open the failure class this repo has now hit three times in test code
  (absolute sandbox path; missing `.gitattributes` LF pin; `str(Path)` separator) —
  every one of which was Linux-green, Windows-red, and invisible to every gate in
  this loop. Comparing parsed JSON is immune to all three, so AC5 forbids the
  pattern outright rather than merely cautioning against it.
- **The self-guards (AC2/AC3) are in scope, not gold-plating.** Item 103's spec
  identifies a second copy of the walk as the specific mechanism by which the
  catalogue and the record would drift apart. A test that imports the walk today
  but is "helpfully" made standalone in six months would silently stop testing
  anything; the AST guard makes that regression a test failure. AC3's threshold of
  12 is a guard-rail chosen to clear the six-path sentinel tuple, not a
  measurement.
- **No byte-hash scope fence for AC22.** Items 099–101 each added one and each
  produced a CI break; item 101 additionally proved the pattern self-contradicts as
  soon as a later item is legitimately authorised to touch the pinned file — which
  is exactly what item 105/106 will do to `feature_docs.py`'s `STATUS_OVERRIDES`. A
  hashed fence here would be guaranteed to break within the same stage. The fence
  is therefore stated as a git-diff obligation the validator checks, not as a
  pytest.
- **No CI workflow change.** `.github/workflows/ci.yml` runs the bare
  `python -m pytest` on four legs and `pyproject.toml` sets
  `testpaths = ["tests"]`, so adding the module is sufficient for "fails CI".
  Editing the workflow would also breach AC22 and, being a `.github/**` change,
  would need a reviewed PR.
