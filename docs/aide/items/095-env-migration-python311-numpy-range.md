# Item 095 — Environment migration: Python 3.11+ and a numpy range

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6)
> **Queue:** [`../queue/queue-013.md`](../queue/queue-013.md) · Item 095 *(second
> of five; sequenced before item 094 so TPTBox is installed once, directly into
> the final Python-3.11+/numpy-range environment, rather than twice)*
> **Objectives:** G6 (portable execution — the suite stays green across
> supported numpy majors; CPU-only, no GPU requirement)
> **Suggested branch:** `aide/095-env-migration-python311-numpy-range`

---

## Description

Raise `pyproject.toml`'s `requires-python` from `>=3.9` to `>=3.11`, replace
the unbounded `numpy>=1.21` lower bound with a range (`numpy>=1.26,<3`), and
regenerate `constraints.txt` (the Stage-9 Docker lockfile, item 066) for the
new floor — all **before** item 094 adds TPTBox, so TPTBox installs directly
into the final target environment rather than into a Python-3.9-compatible
one that is about to be replaced. Add a CI job that runs the full suite
against **two numpy legs — `1.26.4` and `2.0.2`** — so the project stays
demonstrably numpy-major-agnostic. This is not speculative: `CLAUDE.md`
already documents that the golden-file/reference comparisons are
numeric-tolerance (`reports_close`), not byte-identity against a pinned
numpy, and this session's own measurement confirms it empirically — FACET's
full suite run **3703 passed, 53 skipped** under numpy 1.26.4, matching the
previously-CI-pinned numpy 2.0.2 baseline. `1.26.4`/`2.0.2` are the two
concrete versions chosen for the CI legs specifically because both are now
independently measured-green, not merely declared-supported.

**Why this floor, concretely.** Python 3.11 and numpy 1.26.4 are not
arbitrary choices — they match the real working `spineps` conda environment
(`~/miniconda3/envs/spineps`: Python 3.11.15, torch 2.4.1+cu121, numpy
1.26.4, monai 1.4.0, antspyx 0.4.2, SPINEPS 2.0.0, TPTBox 0.6.1, nibabel
5.4.2) that produces the real candidate segmentations Stage 16/21 will
eventually consume. The binding constraint in that environment is
`sm_61 GPU → torch 2.4.1 ceiling → monai ≤ 1.4.0 → numpy<2.0` — numpy 1.26.4
is *forced* there, not merely convenient. FACET declaring a numpy **range**
rather than a pin is what lets the identical FACET code run unmodified in
that workstation environment (numpy 1.26) and in a numpy-2.x cluster/CI
environment without a fork.

This item does **not** add TPTBox — that is item 094, landing immediately
after. `constraints.txt` is therefore regenerated **twice** across the two
items: this item regenerates it for the *pre-TPTBox* six-package core
(numpy, scipy, scikit-image, nibabel, PyYAML, jsonschema) on the new Python
floor; item 094 regenerates it again once TPTBox's transitive dependency set
is added. This item's own suite must be green with no TPTBox installed —
TPTBox's own install-time complications (below) do not arise for this item.

**A forward note for item 094, recorded here because it was discovered
while scoping this item's numpy-major matrix.** TPTBox 0.7.5's declared
metadata (`numpy>=2.0` for `python>=3.11`) is **not a real code
requirement** — measured, not assumed: TPTBox 0.7.5 installed with
`--no-deps` into a Python 3.11 venv on numpy 1.26.4 passes its own test
suite (417 passed, 4 skipped — all four gated on an on-disk BIDS dataset, 81
subtests, zero failures), including the two `antspyx`-exercising tests in
`test_nrrd.py` (the one C-extension in that stack with real numpy ABI
coupling); an exact-attribute AST scan of the TPTBox source for both the
~30 numpy-2.0-only APIs and the ~20 APIs removed in numpy 2.0 finds zero
uses either way. TPTBox 0.7.5 (not the older 0.6.1, which lacks 8 `NII`
methods FACET needs, including `dilate_msk_euclid`/`erode_msk_euclid`/
`from_numpy`/`to_stl`, and every upstream fix since) is therefore
numpy-major-agnostic in practice despite its declared marker. Because pip's
resolver honours the *declared* marker regardless, item 094 will need to
install TPTBox from a **wheel built from the pinned 0.7.5 checkout with
`--no-deps`** (recording the wheel's sha256) rather than a plain
`pip install tptbox==0.7.5`, specifically for any environment (this item's
own future numpy-1.26.4 CI leg, once item 094 adds TPTBox; the real
`spineps` conda env) where a strict resolver would otherwise refuse to
coexist `numpy<2` with TPTBox's declared `numpy>=2.0` marker. This item's
own two CI legs need no such workaround (no TPTBox is installed by this
item), but the note is captured here since it was surfaced while grounding
this item's numpy range and directly determines whether item 097's stage
validation can still exercise both numpy legs after item 094 lands.

**What this item is not:**
- **Not the TPTBox install or image-layer migration** (item 094).
- **Not the label-convention swap** (item 093, already merged when this
  item lands per queue order).
- **Not a change to what the OS matrix (`ubuntu-latest`/`windows-latest`)
  tests today** — the existing `test` job's byte-identity-sensitive install
  via `constraints.txt` is regenerated in place, not restructured; the new
  numpy-major matrix is an **additive** job, mirroring the existing
  `verify-environment-gated` job's posture (a separate job, not a change to
  `test`'s OS matrix).

## Acceptance Criteria

- [ ] **AC1: `requires-python` is raised and classifiers updated.**
  `pyproject.toml`'s `requires-python = ">=3.11"`; the `Programming Language
  :: Python :: 3.9` / `3.10` classifiers are removed (3.11/3.12 retained,
  matching what CI actually tests).
- [ ] **AC2: the numpy dependency is a range, not an unbounded lower bound.**
  `pyproject.toml`'s core `dependencies` reads `"numpy>=1.26,<3"` (replacing
  `"numpy>=1.21"`); no other core dependency's bound changes as part of this
  item.
- [ ] **AC3: a `python<3.11` install is rejected cleanly.** `pip install`
  against a Python 3.10 interpreter fails with pip's own clear
  `requires-python`/"not compatible" error — no partial install, no
  downstream `ImportError` deep in a module.
- [ ] **AC4: `constraints.txt` is regenerated for the new floor and reflects
  only the pre-TPTBox core.** Following the file's own documented recipe
  (clean venv, `pip install .` project-only, `pip freeze`, filtered to the
  six declared core dependencies + their transitives), regenerated on Python
  3.11; the file's header comment is unchanged (still accurate); no TPTBox
  or TPTBox-transitive package appears (that is item 094's edit).
- [ ] **AC5: the existing `test` CI job passes unchanged in shape.** The
  `ubuntu-latest`/`windows-latest` matrix, Python 3.11 setup, and
  `pip install -e .[dev] -c constraints.txt` install step are structurally
  unchanged (only `constraints.txt`'s pinned versions move); the job is
  green.
- [ ] **AC6: a new CI job runs the suite against two concrete numpy legs.**
  A job (e.g. `test-numpy-majors`, `ubuntu-latest`, Python 3.11) installs
  the project via `pip install -e .[dev]`, then in one leg pins
  `numpy==1.26.4` and re-runs `pytest`; in the other, pins `numpy==2.0.2`
  (the version `constraints.txt` previously pinned) and re-runs `pytest`.
  Both legs are green — matching this session's own measurement (3703
  passed, 53 skipped under 1.26.4).
- [ ] **AC7: `verify-environment-gated` is unaffected.** The existing
  pyradiomics/Docker job's install steps and behaviour are unchanged by this
  item (no Python-floor-related edit needed there, since it already targets
  Python 3.11).

## Assumptions

Clarify mode was forced to `interactive` for this batch. The exact numpy
legs and CI job shape were not raised as user-facing questions (they are
tightly bounded, low-ambiguity implementation choices); the following
resolves a **substantive** ambiguity that *was* raised and answered:

- **A genuine numpy-1.x-vs-2.x matrix stays meaningful even after TPTBox
  becomes a required dependency (item 094).** Initial research found that
  the sibling `TPTBox` checkout's `pyproject.toml` declares
  `numpy>=2.0,<3.0` for `python>=3.11` (and `<2.0` only for `python<3.11`),
  which read as a hard conflict with a "numpy major" CI matrix once Python
  is raised to `>=3.11` and TPTBox is required. Raised with the user, who
  supplied a **direct empirical measurement** (not just a claim): TPTBox
  0.7.5 installed with `--no-deps` on numpy 1.26.4 passes its own test suite
  (417/4/81 pass/skip/subtests-pass, zero failures, including the
  `antspyx`-exercising `test_nrrd.py` cases) and an AST scan finds zero uses
  of any numpy-2.0-only or numpy-2.0-removed API across the TPTBox source.
  The declared `numpy>=2.0` marker is therefore not a real code requirement.
  **Pinned:** item 094 pins `tptbox==0.7.5` (not `0.6.1`, which lacks 8
  needed `NII` methods and every fix since), installed from a **wheel built
  from the pinned checkout with `--no-deps`** (recording the wheel's
  sha256) rather than a plain `pip install`, precisely because pip's
  resolver honours the declared-but-not-code-real marker and would
  otherwise refuse to coexist with `numpy<2` — a documented bootstrap step,
  not a fork, with an upstream issue to relax the marker tracked
  separately. This item's own numpy-1.26.4 leg needs no such workaround
  (no TPTBox present yet); item 094/097 inherit the workaround where it
  actually applies.
- **The two CI legs are the two versions this session directly measured
  green: numpy `1.26.4`** (matching the real `spineps` conda environment's
  monai-forced ceiling, and confirmed via a full FACET suite run this
  session — 3703 passed, 53 skipped) **and numpy `2.0.2`** (the version
  `constraints.txt` previously pinned, the prior CI baseline). Both are
  concrete, already-measured-green versions rather than "whatever resolves
  today," so the CI job is reproducible and not silently dependent on
  PyPI's latest release at any given moment. No numpy `3.x` leg exists
  because none is a declared-supported version yet.
- **The new numpy-major job is additive, not a restructuring of the
  existing `test` job's OS matrix.** Running the byte-identity-sensitive
  `test` job across a numpy axis too would multiply OS × numpy-major
  combinations and risk destabilising the already-carefully-scoped
  arm64-exclusion rationale documented in `ci.yml`'s comments; a separate
  `ubuntu-latest`-only job (mirroring `verify-environment-gated`'s existing
  posture) keeps the numpy-major check additive and low-risk.
- **`constraints.txt` is regenerated twice across items 095/094**, not once
  — this item's regeneration reflects only the pre-TPTBox six-package core;
  item 094 regenerates it again once TPTBox's transitive dependencies
  (SimpleITK, scikit-learn, connected-components-3d, fill-voids, pynrrd,
  dill, requests, matplotlib per the queue's dependency-footprint note) are
  added. Pinned so item 094's builder does not read this item's
  `constraints.txt` edit as already-final.
- **Dependencies:** none within Stage 17 — this item has no code dependency
  on item 093 (the label-convention swap touches only `labels.py` and the
  reference artifact, neither Python-version- nor numpy-bound-sensitive),
  but is sequenced after it per the queue's stated item order.

## Implementation Steps

1. **`pyproject.toml`**:
   - `requires-python = ">=3.9"` → `">=3.11"`.
   - Remove the `"Programming Language :: Python :: 3.9"` and `"... :: 3.10"`
     classifiers; keep `3.11`/`3.12`.
   - `dependencies` list: `"numpy>=1.21"` → `"numpy>=1.26,<3"`.
   - Update the comment above `dependencies` (currently: "Lower-bound pins
     are chosen for Python 3.9 compatibility...") to reflect the new
     Python-3.11 floor.
2. **`constraints.txt`**: regenerate per the file's own documented recipe
   (`python -m venv .venv-lock` on a **Python 3.11** interpreter,
   `.venv-lock/bin/pip install .` project-only, `pip freeze`, filtered to
   the six core dependencies + transitives — same filtering discipline as
   today, header comment otherwise unchanged). Do **not** add TPTBox or any
   TPTBox-transitive package here.
3. **`.github/workflows/ci.yml`**:
   - No structural change to the `test` job (it already targets Python
     3.11; only `constraints.txt`'s resolved versions move under it).
   - Add a new job `test-numpy-majors`: `ubuntu-latest`, Python 3.11, a
     matrix axis over the two numpy versions `1.26.4` and `2.0.2`; each leg
     runs `pip install -e .[dev]`, then `pip install numpy==<that leg's
     pinned version>` (interpolated from the matrix axis via the workflow's
     normal expression syntax), then `python -m pytest`. Comment the job
     explaining why it exists
     (numpy-major agnosticism, item 095; the two pinned versions are the
     ones directly measured green — the real `spineps` environment's
     monai-forced 1.26.4 ceiling, and the prior `constraints.txt` 2.0.2
     baseline) and cross-reference `CLAUDE.md`'s existing note on
     `reports_close` numeric-tolerance comparisons being what makes this
     safe.
4. **`CLAUDE.md`**: no edit required by this item (the existing "Note what
   the golden tests actually assert" paragraph already documents the
   numeric-tolerance rationale this item's CI addition exercises for real,
   continuously, rather than as a one-off manual verification).

## Testing Strategy

- **AC1–AC3** are packaging-metadata/CI-observable, not `pytest`-observable
  in the usual sense:
  - AC1/AC2: a small `tests/test_095_env_migration.py` reads
    `pyproject.toml` (via `tomllib`/`tomli`, stdlib on 3.11+) and asserts
    `project.requires-python == ">=3.11"`, the numpy dependency string, and
    that no 3.9/3.10 classifier remains.
  - AC3: documented as a **Validation** step (see below), not a unit test —
    it requires an actual Python 3.10 interpreter, which the CI runner may
    or may not have available; if unavailable, note the honest limitation
    rather than fabricating a test.
- **AC4**: `tests/test_095_env_migration.py` also asserts
  `constraints.txt` contains a `numpy==` line whose version satisfies
  `>=1.26,<3`, and that none of TPTBox's known package names (`TPTBox`,
  `SimpleITK`, `connected-components-3d`, `fill-voids`, `pynrrd`) appear.
- **AC5/AC6/AC7**: verified by CI itself running (this item's Testing
  Strategy explicitly relies on the CI workflow as the test surface, since
  the object under test — cross-environment installability — is not
  expressible as a single local `pytest` run). Locally, the builder should
  additionally run the full suite once with numpy pinned to `1.26.4` and
  once with `2.0.2` in the active venv, both green, before committing —
  this reproduces the 3703-passed/53-skipped measurement already taken
  this session under 1.26.4.
- **Adversarial / edge cases:**
  - A `numpy==2.5` (hypothetical future release still `<3`) install should
    still be accepted by the declared range — not asserted by an automated
    test (no such release may exist yet), but confirmed by re-reading the
    range boundary logic (`<3`, not a narrower upper pin).
  - Confirm `pip install -e .[dev] -c constraints.txt` (the exact `test`
    job invocation) still succeeds end-to-end after the regeneration —
    a stale/inconsistent `constraints.txt` (referencing a package version
    no longer resolvable under the new Python floor) would fail this step
    loudly rather than silently.

## Validation

Beyond the tests above, this item needs an **actual CI run** to demonstrate
the new `test-numpy-majors` job passes both legs — the point of the item is
cross-environment installability, which a local single-environment `pytest`
run cannot fully substitute for. The validator should push the item branch
and confirm the new job appears and is green in the resulting CI run (or, if
CI cannot be triggered from the validation environment, note this
explicitly as the honest limitation — `❓ Unverified` for the CI-run
observation specifically, not a silent pass).

## Dependencies

- **Item 093 (expected ✅ by the time this item lands, per queue order) —
  no code dependency**, sequenced after per the queue's stated order.
- **None** otherwise — this item touches only `pyproject.toml`,
  `constraints.txt`, and `.github/workflows/ci.yml`.
- **Downstream: item 094** depends on this item landing first (TPTBox
  installs directly into the final Python-3.11+/numpy-range environment);
  item 094 will regenerate `constraints.txt` a second time to add TPTBox's
  transitive dependencies. **Item 097** (stage validation) depends on this
  item's CI job existing and passing, to confirm at stage close.

## Decisions & Trade-offs

To be updated during implementation.
