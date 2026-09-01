# Item 133 — `tptbox` ≥ 0.7.6, and the retirement of `refresh_reference.py --verse-cohort`

> **Created:** 2026-08-31 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 29 — Golden Retirement & Test-Artifact Hygiene
> **Queue:** [`../queue/queue-018.md`](../queue/queue-018.md) · Item 133
> **Objectives:** G7 (evaluable & regression-testable — dependency provenance and tool honesty)
> **Suggested branch:** `aide/133-tptbox-0-7-6-and`

---

## Description

Two maintenance deliverables with no feature semantics, batched because both are
dependency/script upkeep verified by the same kind of test — Stage 29 **D9** and
**D10**. Neither changes anything under `src/segfacet/`.

**1. The dependency (D9).** The pinned `tptbox==0.7.5` wheel publishes
`License: GNU AFFERO GENERAL PUBLIC LICENSE v3.0, 19 November 2007` in its
distribution metadata, while TPTBox's repository `LICENSE` is Apache-2.0.
Upstream corrected the metadata in v0.7.6 (TPTBox PR #119). FACET pins tptbox
exactly, in two places that must move together: `pyproject.toml`'s
`[project.dependencies]` (what CI's `test` and `test-numpy-majors` jobs resolve)
and `constraints.txt` (what the Stage-9 Docker image installs from). A stale
AGPL declaration in the metadata of a library FACET ships against is a
licence-provenance defect regardless of what the repository LICENSE says,
because every automated consumer — SBOM tooling, `pip show`, a downstream
audit — reads the metadata, not the repo.

Measured 2026-08-31 by downloading the wheel and reading its `METADATA` (nothing
installed):

| | 0.7.5 (pinned) | 0.7.6 (target) |
|---|---|---|
| `License:` | `GNU AFFERO GENERAL PUBLIC LICENSE v3.0, 19 November 2007` | `Apache License Version 2.0, January 2004` |
| `Classifier: License ::` | `Other/Proprietary License` | `Other/Proprietary License` (**unchanged upstream**) |
| `Requires-Dist` (all 17) | — | **byte-identical to 0.7.5** |
| wheel | pure-Python, no compiled extensions | pure-Python, `sha256 16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4` |

Only the `Version:` and `License:` header lines differ between the two wheels'
metadata. That is what makes this a safe, narrow bump: the transitive block of
`constraints.txt` needs no regeneration, and no dependency bound moves.

The bump's regression surface used to be the golden corpus; item 126 retired
those snapshots, so what remains is `tests/test_094_tptbox_image_layer.py`'s AC3
loader snapshot (`tests/corpus/094_pre_migration_snapshot.json` — every corpus
fixture's shape/dtype/`sha256(data)`/spacing/affine through `load_volume`, i.e.
through TPTBox's `NII.load` + `reorient` + `zoom`) and its AC7
verdict+findings-shape expectation. **If the new wheel moves any of those, that
is a finding to report and hand back on — never a re-snapshot.**

**2. The script (D10).** `scripts/refresh_reference.py --verse-cohort` cannot
build the real artifact. It hands the cohort root straight to `build_reference`
→ `ingest_cohort`, which walks **one** directory non-recursively and hardcodes
each mask's CT sibling as `<id>_scan.nii.gz`, while the real VerSe19 layout
nests masks under `derivatives/sub-verseNNN/` and names CTs `..._ct.nii.gz`
(`docs/aide/dataset-verse19.md`). Against a real cohort the wrapper therefore
finds nothing and records `verse-build: failed`
(`scripts/refresh_reference.py:217-246`). Item 123 already shipped the tool that
does work — `scripts/rebuild_verse_reference.py`, which discovers masks by
recursive glob, stages a flat link directory satisfying `ingest_cohort`'s
convention, builds the artifact and derives the calibrated threshold — and item
123's spec records the deliberate reason it was a new script rather than a
widening of item 083's contract.

This item **retires** the mode rather than delegating to it (see Decisions). Two
measurements make retirement the smaller and more honest change:

- `--verse-cohort` is not uniformly broken: `tests/test_083_refresh_reference.py`
  AC10 passes a *flat* stand-in cohort (`<id>_seg-vert_msk.nii.gz` +
  `<id>_scan.nii.gz` in one directory) and gets `verse-build: ran`. The mode
  works only for the staging convention a maintainer would have to build by
  hand — i.e. only when the caller has already done the job the mode exists to
  do. So the wrapper's real-cohort claim is the thing being withdrawn.
- The `verse-evaluate` step never reads the VerSe cohort at all. It calls
  `synthesize_eval_cohort(...)` — the same deterministic `build_clean_spine`
  recipe the synthetic step uses — and merely labels the result
  `cohort_id="refresh-verse"`. Retiring it removes no real-data measurement.

**Not in scope:** rewiring `refresh_reference.py` onto `ingest_dataset_cohort` /
`segfacet.datasets.resolve` (the Stage-13 adapter path that ingests nested
layouts with no staging); bumping tptbox past 0.7.6; regenerating
`constraints.txt`'s transitive block; any change under `src/segfacet/`; any
re-snapshotting of `tests/corpus/094_pre_migration_snapshot.json`.

## Acceptance Criteria

- [ ] **AC1: the library pin moves, and stays exact.** `pyproject.toml`'s
  `[project.dependencies]` contains exactly one tptbox specifier and it is the
  literal `tptbox==0.7.6` — an exact pin, not a range (preserving item 094 AC1's
  deliberate choice).
- [ ] **AC2: the lockfile pin moves with it, and nothing else in it does.**
  `constraints.txt` pins `tptbox==0.7.6`, and its complete
  `name → version` pin map is otherwise identical to the pre-item map (every
  other package name and version string unchanged).
- [ ] **AC3: the installed distribution no longer declares AGPL.** The `License`
  field of the installed `tptbox` distribution metadata
  (`importlib.metadata.metadata("tptbox")["License"]`) contains neither
  `agpl` nor `affero`, case-insensitively.
- [ ] **AC4: the environment and both pin files agree.** The installed `tptbox`
  version equals the version pinned in `pyproject.toml`, equals the version
  pinned in `constraints.txt`, and parses as ≥ 0.7.6.
- [ ] **AC5: the install document names only the pinned version.** Every
  `tptbox==<version>` occurrence in `docs/tptbox-install-numpy1.md` names the
  version pinned in `pyproject.toml`, and the document's recorded wheel digest
  is `16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4`.
- [ ] **AC6: no stale version literal survives in the suite.** No file under
  `tests/` contains the literal string `tptbox==0.7.5`.
- [ ] **AC7: the tptbox consumers cannot skip.** Neither
  `tests/test_093_tptbox_label_convention.py` nor
  `tests/test_094_tptbox_image_layer.py` contains a module-level or per-test
  skip guard keyed on tptbox's presence or version (no `importorskip`, no
  `skipif` naming tptbox/TPTBox) — tptbox is a core dependency, so these run
  unconditionally or the suite is broken.
- [ ] **AC8: the retired mode fails loudly with a pointer.**
  `refresh_reference.main(["--out", <dir>, "--verse-cohort", <VerSe-layout dir>])`
  returns `2` and writes a single-line message naming
  `scripts/rebuild_verse_reference.py` to stderr, with no Python traceback in
  the combined stdout+stderr.
- [ ] **AC9: the refused run does no work.** That same invocation leaves no
  `refresh_summary.json` and no artifact under the `--out` directory.
- [ ] **AC10: the summary no longer carries VerSe steps.** For any successful
  `refresh_reference` invocation, `summary["steps"]` is exactly
  `[synthetic-default-rebuild, synthetic-eval-cohort, synthetic-evaluate]` in
  that order, and no step is named `verse-build` or `verse-evaluate`.
- [ ] **AC11: the API stops advertising the mode.** `run_refresh` accepts no
  `verse_cohort` and no `verse_seg_suffix` parameter
  (`inspect.signature`), and its returned summary dict has no `verse_cohort`
  key.
- [ ] **AC12: the docstring stops advertising the mode.**
  `scripts/refresh_reference.py`'s module docstring describes no real-VerSe
  build step, contains no `--verse-cohort` usage example, and names
  `scripts/rebuild_verse_reference.py` as the path for a real cohort.
- [ ] **AC13: the synthetic path is untouched.**
  `refresh_reference.main(["--out", <dir>])` still returns `0`, writes
  `refresh_summary.json`, and reports `status == "ran"` for all three synthetic
  steps.

## Assumptions  <!-- MANDATORY -->

- **tptbox 0.7.6's metadata is Apache-2.0** — measured 2026-08-31 by
  `pip download tptbox==0.7.6 --no-deps` into a scratch directory and reading
  `METADATA` from the wheel (nothing installed into `.venv`):
  `License: Apache License Version 2.0, January 2004`. Wheel sha256
  `16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4`,
  pure-Python (`py3-none-any`), no compiled extensions.
- **The transitive footprint does not move.** 0.7.6's 17 `Requires-Dist` lines
  are byte-identical to 0.7.5's (including the `numpy (>=2.0,<3.0) ;
  python_version >= "3.11"` bound), so `constraints.txt`'s transitive block is
  not regenerated and CI's numpy-majors matrix is affected exactly as much as it
  is today (i.e. not at all — the 1.26.4 leg already force-installs numpy after
  resolution).
- **The pin stays exact.** `tptbox==0.7.6`, not `tptbox>=0.7.6`. Item 094's AC1
  chose an exact pin and `test_094`'s
  `test_ac1_tptbox_pin_is_exact_not_a_range` enforces it; loosening it is a
  separate decision this item does not take.
- **0.7.6, not the latest (0.8.2).** `pip index versions tptbox` on 2026-08-31
  lists 0.8.2 as latest. This item takes the lowest version that fixes the
  metadata; a minor-version jump carries its own API regression surface and
  belongs to its own item.
- **The classifier is still wrong upstream.** 0.7.6 retains
  `Classifier: License :: Other/Proprietary License`. Only the free-text
  `License:` field was corrected, which is why AC3 is phrased against that field
  and not against the classifier. Not fixable from here.
- **`test_093` / `test_094` are not environment-gated.** Neither module has a
  skip guard on tptbox — it is a core dependency, always installed. The queue's
  phrase "gated consumers" is loose; "run, not skip" is structural here, which
  AC7 pins. CI's `verify-environment-gated` job installs PyRadiomics and Docker
  only and neither installs tptbox nor collects these two modules; this item
  adds nothing to that job, because tptbox is not an optional capability.
- **Installing the wheel changes only the gitignored venv.** CI's `test` /
  `test-numpy-majors` jobs resolve from `pyproject.toml` and the Docker image
  installs from `constraints.txt`; no committed artifact records an installed
  version.
- **Hand back rather than walk the pin forward.** If the builder's
  `pip install "tptbox==0.7.6"` yields a `License` field that still contains
  AGPL/Affero — i.e. the measurement above does not reproduce — the item hands
  back for a human decision instead of trying 0.8.x on its own initiative.
- **Retirement is a deliberate behaviour change to a merged item's contract.**
  `refresh_reference.py` gains exit code `2` and loses two summary steps, both
  of which `tests/test_083_refresh_reference.py` pins today. Those pins are
  reconciled here (see Testing Strategy), not worked around.
- **A refused run writes nothing** rather than completing the synthetic half and
  reporting a `retired` step, so a caller that supplied `--verse-cohort` cannot
  mistake a partial run for a full refresh.

## Implementation Steps

`source_dir` (`src/segfacet/`) is **not** touched by this item; the code path is
packaging metadata plus one project tool under `scripts/`.

1. **Install the new wheel locally** (venv only, gitignored):
   `.venv/bin/python -m pip install "tptbox==0.7.6"`, then
   `.venv/bin/python -m pip show tptbox` and record the `License:` line verbatim
   in Decisions & Trade-offs. If it still reads AGPL, stop and hand back.
2. **`pyproject.toml`** — change the single `"tptbox==0.7.5"` entry in
   `[project.dependencies]` to `"tptbox==0.7.6"`. Add a one-line comment above
   the pin recording *why* it is exact and that 0.7.6 is the version whose
   metadata declares Apache-2.0 (dated). No other dependency line moves (AC1).
3. **`constraints.txt`** — change line 29's `tptbox==0.7.5` to `tptbox==0.7.6`.
   Do **not** regenerate the file: 0.7.6's `Requires-Dist` set is identical, so
   a regeneration would silently roll every unrelated transitive pin forward
   (AC2).
4. **`docs/tptbox-install-numpy1.md`** — retarget the document at the new pin:
   the title, every `tptbox==0.7.5` / `v0.7.5` / `tptbox-0.7.5-...whl` string,
   the expected `TPTBox.__version__`, and the `sha256sum` expectation
   (`16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4`). The
   document's *rationale* is unchanged and stays as written — 0.7.6 declares the
   same `numpy>=2.0` bound for `python>=3.11`, so the numpy<2 bypass procedure
   still applies verbatim (AC5).
5. **`scripts/refresh_reference.py` — retire the VerSe mode.**
   - Delete the `STEP_VERSE_BUILD` / `STEP_VERSE_EVALUATE` constants and
     `DEFAULT_VERSE_SEG_SUFFIX`.
   - Drop `verse_cohort` / `verse_seg_suffix` from `run_refresh`'s signature,
     delete the whole `# -- verse-build / verse-evaluate --` block, and remove
     the `"verse_cohort"` key from the returned summary (AC10, AC11).
   - Keep `--verse-cohort` and `--verse-seg-suffix` registered in the parser,
     with help text marking them retired and naming the replacement, so a
     maintainer's existing command line meets a purposeful message rather than
     argparse's generic "unrecognized arguments".
   - In `main`, before any work: if either retired flag was supplied (give
     `--verse-seg-suffix` a `None` default so "supplied" is detectable), print
     one line to stderr naming `scripts/rebuild_verse_reference.py` and the
     equivalent invocation, and `return 2` — no directory created, no summary
     written, no traceback (AC8, AC9).
   - Rewrite the module docstring: step 4 of the numbered list goes; the
     "Usage" block loses its `--verse-cohort` examples; add one sentence
     pointing a real-cohort rebuild at `scripts/rebuild_verse_reference.py`
     (item 123), which owns discovery, staging and threshold calibration
     (AC12).
6. **Reconcile the stale pins** listed under Testing Strategy — four test
   modules, five literal `tptbox==0.7.5` assertions, and `test_083`'s
   VerSe-step group.
7. **Run the full suite** and read `test_094`'s AC3/AC7 results specifically.
   A moved loader digest, spacing or affine is a finding to report, not to
   re-snapshot.

## Authorised paths

**May change:**

- `pyproject.toml` — the tptbox pin (AC1).
- `constraints.txt` — the tptbox pin (AC2).
- `docs/tptbox-install-numpy1.md` — version strings and wheel digest (AC5).
- `scripts/refresh_reference.py` — the retired VerSe mode, its constants, its
  `run_refresh` signature and its docstring (AC8–AC13).
- `tests/test_133_tptbox_pin_and_verse_retirement.py` — the new test module.
- `tests/test_083_refresh_reference.py` — reconcile the VerSe-step tests
  (`test_ac7_…`, `test_ac9_…`, `test_ac10_…`, the `--verse-cohort` half of
  `test_ac12_…`, `test_adversarial_empty_but_present_verse_cohort_no_crash`)
  and the `_build_standin_verse_cohort` helper they use.
- `tests/test_094_tptbox_image_layer.py` — three `tptbox==0.7.5` literals
  (lines 157, 163, 186).
- `tests/test_074_benchmark.py` — one `tptbox==0.7.5` literal (line 329).
- `tests/test_119_curve_formulation.py` — one `"tptbox==0.7.5"` literal
  (line 698).
- `docs/aide/insights.md` — append-only capture (framework convention).

**Asserts against:**

- The installed `tptbox` distribution metadata — AC3 reads its `License` field
  and AC4 its `Version`; environment state, recomputed live, never edited.
- `scripts/rebuild_verse_reference.py` — AC8's message must name it; the new
  test module reads `VERSE_SEG_SUFFIX` from it to build the VerSe-layout
  fixture. Not changed by this item.
- `tests/test_093_tptbox_label_convention.py` — AC7 scans it for skip guards;
  it carries no version literal and is not changed.
- `tests/corpus/094_pre_migration_snapshot.json` — `test_094`'s AC3 recomputes
  every corpus fixture's loader digest/spacing/affine against it under the new
  wheel. Pinned, and explicitly not re-snapshotted by this item.

## Testing Strategy

New module: **`tests/test_133_tptbox_pin_and_verse_retirement.py`**, one focused
test per AC.

- **AC1/AC2/AC4** — parse `pyproject.toml` with `tomllib` and `constraints.txt`
  with the same pin-line regex `test_094` already uses; compare the two pins to
  each other and to `importlib.metadata.version("tptbox")`, and compare the
  constraints pin map (minus tptbox) against the literal pre-item map recorded
  in the test, so a drive-by regeneration of the lockfile fails loudly.
- **AC3** — `importlib.metadata.metadata("tptbox")["License"]`, asserted to
  contain neither `agpl` nor `affero` case-insensitively, with the observed
  string in the failure message.
- **AC5** — read `docs/tptbox-install-numpy1.md`; assert
  `set(re.findall(r"tptbox==([0-9][0-9a-zA-Z.\-]*)", text))` equals the single
  pyproject-pinned version, and that the expected wheel digest appears.
- **AC6** — walk `tests/**/*.py` and assert none contains `tptbox==0.7.5`.
- **AC7** — read `test_093` / `test_094` as text and assert no
  `importorskip` and no `skipif` line mentioning tptbox/TPTBox.
- **AC8/AC9** — build a **two-subject VerSe-layout fixture** under `tmp_path`
  (the real nesting, not the flat stand-in):
  `derivatives/sub-verse000/sub-verse000_seg-vert_msk.nii.gz` +
  `rawdata/sub-verse000/sub-verse000_ct.nii.gz`, likewise `sub-verse001`, built
  from `build_clean_spine` / `paint_clean_scan` with the suffix constants
  imported from `scripts/rebuild_verse_reference.py`. Drive
  `refresh_reference.main([...])` with `--verse-cohort <root>`, capturing
  stdout+stderr as `test_083`'s `_capture_main` does. Assert `rc == 2`, the
  message names `rebuild_verse_reference.py`, no `Traceback (most recent call
  last)` appears, and the `--out` directory holds no `refresh_summary.json`.
  This is the exact invocation the queue requires never to report
  `verse-build: failed` again.
- **AC10/AC13** — one no-flag run: `rc == 0`, the three step names in order,
  every status `ran`, and no step named `verse-build`/`verse-evaluate`.
- **AC11** — `inspect.signature(run_refresh)` parameter names, and the absence
  of a `verse_cohort` key in the returned summary.
- **AC12** — parse `scripts/refresh_reference.py`'s module docstring via
  `ast.get_docstring`; assert it contains `rebuild_verse_reference.py` and no
  `--verse-cohort` usage line.

**Adversarial / edge cases.**

- `--verse-seg-suffix` supplied *without* `--verse-cohort` → same rc 2 and same
  pointer message (a caller migrating a half-remembered command line).
- `--verse-cohort ""` (empty string) → treated as supplied; rc 2, not a silent
  success and not a crash.
- `--verse-cohort <nonexistent path>` → rc 2 with the pointer, **not** the old
  "skipped, path does not exist" outcome; the mode is gone, not conditional.
- `--out` pointing at a not-yet-existing nested parent, combined with the
  retired flag → still rc 2 and the parent is not created.
- Two no-flag runs into different `--out` directories produce equal step
  name/status pairs (item 083 AC11's determinism property, preserved).
- Version-comparison edge: AC4 parses versions as tuples of ints, so a future
  `0.7.10` is correctly ≥ `0.7.6` (a string comparison would not be).

**Existing tests to reconcile** (each pins behaviour this item deliberately
changes; leaving any of them stale costs a guaranteed extra validation round):

| File | What pins the old behaviour |
|---|---|
| `tests/test_094_tptbox_image_layer.py:157` | `assert "tptbox==0.7.5" in dependencies` |
| `tests/test_094_tptbox_image_layer.py:163` | `assert tptbox_specs == ["tptbox==0.7.5"]` (keep the *exactness* claim, move the version) |
| `tests/test_094_tptbox_image_layer.py:186` | `assert pins.get("tptbox") == "0.7.5"` |
| `tests/test_074_benchmark.py:329` | `"tptbox==0.7.5"` inside `expected_deps` for `test_ac13_core_dependencies_unchanged_no_cupy` |
| `tests/test_119_curve_formulation.py:698` | `'"tptbox==0.7.5"'` in `test_ac23_scipy_floor_raised_other_bounds_unchanged` |
| `tests/test_083_refresh_reference.py:200-214` | `test_ac7_verse_build_is_genuine_skip_without_cohort` — asserts `STEP_VERSE_BUILD` exists and is `skipped` |
| `tests/test_083_refresh_reference.py:226-245` | `test_ac9_nonexistent_verse_cohort_is_absent_not_a_crash` — asserts rc 0 and a `skipped` verse step |
| `tests/test_083_refresh_reference.py:247-268` | `test_ac10_verse_build_runs_with_standin_cohort` — asserts `verse-build: ran` on a flat stand-in |
| `tests/test_083_refresh_reference.py:294-315` | `test_ac12_writes_only_into_out_dir` — its `--verse-cohort` invocation |
| `tests/test_083_refresh_reference.py:328-343` | `test_adversarial_empty_but_present_verse_cohort_no_crash` |
| `tests/test_083_refresh_reference.py:65-81` | `_build_standin_verse_cohort`, which reads `rr.DEFAULT_VERSE_SEG_SUFFIX` (a constant this item deletes) |

Reconcile by **deleting** the five retired-mode tests and the helper (the mode
they describe is gone — a rewritten "asserts it is retired" copy would duplicate
AC8/AC9 in a module that no longer owns the behaviour), and by narrowing
`test_ac12_writes_only_into_out_dir` to the no-flag invocation. Record the
deletion in `test_083`'s module docstring as a dated note naming item 133, so a
reader of item 083's AC list learns where AC7/AC9/AC10 went.

**Guards this item must not trip.** The new module introduces no comparison of
freshly generated output against a committed artifact, so item 127's
`tests/committed_artifact_guard.py` allowlist is not touched and
`assert_matches_committed_artifact` is not needed. It commits no new fixture, so
no `.gitattributes` `text eol=lf` pin is required (the VerSe-layout fixture is
built under `tmp_path`). Per item 126's sweep, nothing here regenerates a
retired snapshot.

## Validation

Tests prove the pin files and the retired mode behave; only a real install
demonstrates the licence claim the stage's acceptance line rests on. No
`[validation]` profile applies — tptbox is a core dependency, not an
environment-gated capability.

1. `.venv/bin/python -m pip install "tptbox==0.7.6"` then
   `.venv/bin/python -m pip show tptbox` — copy the `License:` line verbatim
   into Decisions & Trade-offs. Expected:
   `License: Apache License Version 2.0, January 2004`.
2. `.venv/bin/python -m pytest tests/test_093_tptbox_label_convention.py
   tests/test_094_tptbox_image_layer.py -v` — record passed/failed/skipped
   counts. **Zero skips expected**; any skip contradicts AC7, and any failure in
   `test_094`'s AC3/AC7 is a real behaviour change in the new wheel — report it
   and hand back rather than adjusting the snapshot.
3. `.venv/bin/python scripts/refresh_reference.py --out out/refresh-133` —
   expect exit 0 and `synthetic-default-rebuild=ran, synthetic-eval-cohort=ran,
   synthetic-evaluate=ran` with no verse steps in the printed line.
4. `.venv/bin/python scripts/refresh_reference.py --out out/refresh-133-verse
   --verse-cohort /nonexistent` — expect exit 2, the one-line pointer to
   `scripts/rebuild_verse_reference.py`, and no `out/refresh-133-verse`
   contents.

**Honest downgrade.** If the machine has no network access when the item runs,
step 1 cannot execute: record the licence observation as **❓ Unverified** with
that reason, leave the pin files bumped (they are a source change, verifiable by
inspection), and say so plainly — never infer the licence string from this
spec's measurement table as if it had been observed on the venv.

## Dependencies

- **Item 126** (✅) — retired the whole-record snapshot goldens that were this
  bump's regression surface; without it the wheel change would have put nine
  corpus reports and two `tests/golden/` snapshots in play.
- **Item 123** (✅) — `scripts/rebuild_verse_reference.py`, the working
  real-cohort rebuild that AC8's message points at.
- **Item 083** (✅) — `scripts/refresh_reference.py` and its pinned step names,
  the contract this item narrows.
- **Item 094** (✅) — the tptbox pin, its exactness rule, and the loader
  snapshot that is now the bump's regression surface.
- **Item 127** (✅) — the committed-artifact guard the new module must not trip.

**Downstream:** item 135 (Stage 29 validation) replays `pip show tptbox` for the
non-AGPL licence line and checks out this item's parent commit to confirm its
regression tests fail there.

## Decisions & Trade-offs

**Retire, not delegate** (recorded at spec time; the rest of this section is for
the builder to update during implementation).

`refresh_reference.py --verse-cohort` is retired with a pointer rather than
delegated to `scripts/rebuild_verse_reference.py`, because delegation would
re-widen exactly the contract item 123 deliberately declined to widen — item
083's summary step names, its exit-code semantics and its tests — to re-expose a
second entry point for a job a dedicated tool already owns end to end
(discovery, staging, build, threshold calibration, its own
`verse_rebuild_summary.json`). The measured evidence that nothing of value is
lost: the wrapper's `verse-evaluate` step never read the VerSe cohort — it
synthesizes the same deterministic `build_clean_spine` cohort as the synthetic
step — and its `verse-build` step only ever succeeded against a cohort the
caller had already staged into `ingest_cohort`'s flat convention by hand. Two
tools claiming one job is the confusion D10 names; retirement removes it, and
the pointer keeps the capability one command away.

Considered and rejected: rewiring the wrapper onto `ingest_dataset_cohort` /
`segfacet.datasets.resolve` (the Stage-13 adapter that ingests nested layouts
with no staging). It is arguably the best long-term shape for real-cohort
ingestion, but it is a design change to the reference-building path, outside
both options the queue put to this item and outside queue-018's "this stage does
no discovery" fence.

**Implementation notes (2026-08-31).**

- `.venv/bin/python -m pip install "tptbox==0.7.6"` succeeded (network
  available). `importlib.metadata.metadata("tptbox")["License"]` observed
  verbatim: `Apache License Version 2.0, January 2004` — matches the spec's
  measurement exactly; neither `agpl` nor `affero` (case-insensitive)
  appears. `importlib.metadata.version("tptbox")` reports `0.7.6`.
- D9 edits: `pyproject.toml`'s single tptbox specifier moved to the exact
  literal `tptbox==0.7.6` with a one-line dated comment; `constraints.txt`
  line 29 moved the same way with no other line touched (the transitive
  block's 40-entry pin map, minus tptbox, is unchanged — verified against
  `test_133`'s recorded pre-item map); `docs/tptbox-install-numpy1.md`'s
  title, every `tptbox==0.7.5`/`v0.7.5`/wheel-filename occurrence, and the
  `sha256sum` expectation were retargeted to 0.7.6 and
  `16fdbcccf4192447897b41825eb2b7249d2e8a860ce4905e7e6c2a18f1fdf5d4`.
- D10 edits: `scripts/refresh_reference.py` dropped `STEP_VERSE_BUILD`,
  `STEP_VERSE_EVALUATE`, `DEFAULT_VERSE_SEG_SUFFIX`, the whole
  verse-build/verse-evaluate block, and `run_refresh`'s `verse_cohort`/
  `verse_seg_suffix` parameters and the summary's `verse_cohort` key.
  `--verse-cohort`/`--verse-seg-suffix` stay registered (default `None` on
  both, so "supplied" is detectable) with retired-flag help text; `main`
  checks for either before any directory is touched, prints one line to
  stderr naming `scripts/rebuild_verse_reference.py` and `return`s `2`. The
  module docstring's real-VerSe usage step is gone and it now points at
  `scripts/rebuild_verse_reference.py`; note the docstring text itself
  avoids the literal substring `--verse-cohort` (unlike the surrounding
  prose) because AC12's test asserts that substring's absence from the
  docstring specifically.
- Manually verified (not via pytest, per the no-flag-run/retired-flag
  validation steps in this spec): a no-flag run into a scratch dir returns
  0 with exactly the three synthetic steps `ran`, in order, and no
  `verse_cohort` key in the summary; a `--verse-cohort /nonexistent` run
  returns 2, prints exactly one stderr line naming
  `scripts/rebuild_verse_reference.py`, and creates no `--out` directory at
  all (not even empty).
- Also ran (explicitly asked for by this spec's Validation §2, to catch a
  wheel-induced snapshot/behaviour change rather than a general suite run):
  `tests/test_093_tptbox_label_convention.py` +
  `tests/test_094_tptbox_image_layer.py` — **142 passed, 0 skipped**, no
  change to `test_094`'s AC3 loader-snapshot or AC7 verdict/findings-shape
  expectations under the new wheel. Also ran
  `tests/test_083_refresh_reference.py` (13 passed) since D10 changed the
  module it exercises directly.
- **Test defect found, not fixed:** `tests/test_133_…py`'s
  `test_ac6_no_stale_pin_literal_anywhere_under_tests` walks every `*.py`
  under `tests/` — including itself — for the literal `tptbox==0.7.5`. The
  test module's own prose (its docstring and the assertion's failure
  message, e.g. line 21/323/325) contains that literal as documentation of
  what it is checking for, so the test fails against itself regardless of
  what any other file contains (`25 passed, 1 failed` when run in
  isolation). This is a self-referential false positive in the test, not a
  production-code defect — every non-test-133 file is clean, and AC1/AC2/
  AC4/AC5 independently confirm the pin moved correctly. Per the builder
  role's hard limit, this was not fixed here (no test-file edits); flagging
  for the validator/test-writer, since the spec's own Authorised-paths list
  does name `tests/test_133_…py` as changeable — just not by this role.
- **2026-08-31 — validator finding fixed:** the 3-line tptbox pin rationale
  comment had landed *inside* `[project.dependencies]`'s array (above the
  `"tptbox==0.7.6",` line), where `test_084`'s and `test_091`'s
  `test_ac*_no_new_dependency` naive line-by-line array parsers (items
  084/091, out of this item's scope) choke on any `#`-prefixed line. Moved
  the same content up into the existing comment block directly above
  `dependencies = [` instead, leaving the array itself carrying only
  quoted specifier lines. No dependency added or removed; still exactly one
  `tptbox==0.7.6` line. Verified with a non-pytest script mirroring both
  tests' parser: no array line starts with `#`, and the recovered
  dependency-name set is unchanged.
