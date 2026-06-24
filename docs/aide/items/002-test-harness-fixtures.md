# Item 002 — Test Harness & Synthetic NIfTI Fixtures

> **Status:** 📋 Planned · **Created:** 2026-06-24
> **Stage:** 0 — Project Scaffolding & I/O Foundation
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 002
> **Objectives:** Foundation (enables G1, G4, G7 and every later test-driven stage)
> **Suggested branch:** `aide/002-test-harness-fixtures`

---

## Description

Stand up the project's **shared test infrastructure**: a small, well-documented
**synthetic NIfTI fixture builder** plus the `pytest` plumbing (`conftest.py`
fixtures) that exposes it to every test module. The builder generates tiny
scan + instance-label-map pairs — fully in-memory and writable on disk — with
controllable shape, voxel spacing, and label layout.

These fixtures are the **reusable substrate for every subsequent item**: the
NIfTI loader (003), label convention (004), CLI wiring (006), empty detection
(007), verdict/report items (008–010), and all later feature/heuristic stages
build their tests on top of them. Getting a clean, deterministic, well-typed
fixture API in place now prevents each later item from re-inventing throwaway
test data.

Item 001 already created the minimal harness skeleton — `tests/` exists,
`tests/test_smoke.py` passes, and `pyproject.toml` declares
`[tool.pytest.ini_options]` (`testpaths = ["tests"]`, `addopts = "-ra"`) and a
`dev = ["pytest>=7"]` extra. **This item extends that skeleton; it does not
re-create it.** `numpy` and `nibabel` are already declared runtime dependencies
(item 001), so no new dependency is required.

### Scope boundary (what this item does *not* do)

To avoid overlap with later items:

| Concern | Owned by | This item |
|---|---|---|
| **Reading** NIfTI into the in-memory representation | Item 003 | only **writes/builds** synthetic NIfTI; no production loader |
| Label → anatomy mapping | Item 004 | fixtures use plain integer labels; no anatomical naming |
| Empty / near-empty *detection logic* | Item 007 | provides an *empty* fixture, but no detector |
| Synthetic **failure** corpus (relabel, fragment, swap, overlap…) | Stage 5 / Item TBD | only **valid, well-formed** baseline fixtures here |
| CI matrix / multi-OS pipeline | later (deferred) | local `pytest` green; cross-platform by design |

> The fixtures produced here are **well-formed, "happy-path" volumes**. The
> deliberately-broken cases that exercise failure modes are the Stage 5 synthetic
> corpus and are out of scope. The one exception is a single *empty* / *near-empty*
> label map, included because Stage 1 (item 007) needs it and it is trivially
> well-defined.

---

## Acceptance Criteria

- [ ] A synthetic-fixture module exists (recommended: `tests/synthetic.py`) with
      documented builder functions that return **valid NiBabel `Nifti1Image`**
      objects for both a *scan* (intensity volume) and an *instance label map*
      (integer-labelled volume), with caller-controllable **shape**, **voxel
      spacing**, and **label layout**.
- [ ] The builder encodes voxel **spacing into the affine** correctly, including
      an **anisotropic** case (e.g. `(1.0, 1.0, 3.0)` mm); the spacing recovered
      from the image header/affine matches what was requested.
- [ ] At least these canonical cases are available as ready-to-use builders /
      pytest fixtures:
  - **labelled-blocks** — a few (≥3) distinct integer labels as separated
    rectangular blocks in an otherwise-zero volume (isotropic spacing).
  - **empty** — a label map of all zeros (no foreground labels).
  - **anisotropic** — a labelled volume with non-uniform spacing.
- [ ] `conftest.py` exposes the canonical cases as `pytest` fixtures usable by
      any test module, including an **on-disk variant** that writes valid `.nii`
      / `.nii.gz` files into pytest's `tmp_path` and yields their paths.
- [ ] Fixtures are **deterministic** — identical content across runs (fixed seed
      / no randomness, or seeded RNG); no network, no external services.
- [ ] Tests in this item assert the builder's own contract: produced volumes have
      the **expected shape, dtype, label set, voxel count per label, and affine /
      spacing**; the on-disk variant round-trips through `nibabel.load` to the
      same array and affine.
- [ ] `pytest` collects and runs green (existing smoke tests from item 001 still
      pass alongside the new tests).
- [ ] Pure-Python / NumPy / NiBabel only — runs CPU-only on Windows, macOS, and
      Linux with no platform-specific code.
- [ ] A short note on **how to use the fixtures** is added (README "Testing"
      subsection or a docstring at the top of `tests/synthetic.py`) so later items
      know the API.

---

## Implementation Steps

1. **Create `tests/synthetic.py`** — the reusable, framework-agnostic builder
   (plain functions, no pytest import) so it can also be called from ad-hoc
   scripts or docs:
   - `affine_from_spacing(spacing) -> np.ndarray` — build a 4×4 affine with the
     given voxel sizes on the diagonal (RAS-ish, identity rotation, zero origin).
   - `make_scan(shape, spacing=(1,1,1), *, dtype=np.int16, fill=...) -> Nifti1Image`
     — an intensity volume (constant or simple gradient; deterministic).
   - `make_labelmap(shape, blocks, spacing=(1,1,1)) -> Nifti1Image` — where
     `blocks` describes `{label: (slices/bbox)}`; paints integer labels into a
     zero volume. Use an integer dtype suitable for label maps (e.g. `uint16`).
   - Convenience builders returning a `(scan, labelmap)` pair (or a small
     dataclass/`namedtuple` bundling `scan_img`, `seg_img`, and metadata such as
     `expected_labels`, `voxel_counts`, `spacing`):
     - `labelled_blocks_case()` — ≥3 labels, isotropic spacing.
     - `empty_case()` — zero label map (+ a matching scan).
     - `anisotropic_case()` — labelled, non-uniform spacing.
   - An on-disk helper: `write_nifti(img, path) -> Path` (thin wrapper over
     `nibabel.save`), used to materialise fixtures under `tmp_path`.
2. **Add `tests/conftest.py`** exposing the canonical cases as pytest fixtures:
   - In-memory fixtures: `labelled_blocks`, `empty_labelmap`, `anisotropic_case`
     (return the bundle from step 1).
   - On-disk fixtures (function-scoped, use `tmp_path`): e.g.
     `labelled_blocks_files` yielding `(scan_path, seg_path)` after writing.
   - Keep fixtures small (e.g. ~16³ or smaller volumes) so the suite stays fast.
3. **Author `tests/test_synthetic.py`** validating the builder's contract
   (see Testing Strategy). This is the deliverable's self-test.
4. **Document the fixture API** — a "Testing & fixtures" subsection in `README.md`
   (or a module docstring) describing the available builders/fixtures and the
   bundle's attributes, so items 003–010 reuse them rather than rolling their own.
5. **Confirm `pyproject.toml` pytest config is sufficient** (it is, from item
   001). Only adjust if a marker or extra `testpaths` entry is genuinely needed;
   document any change here.
6. **Verify** the manual validation checklist below: `pytest` green locally.

---

## Testing Strategy

- **Framework:** `pytest` (already configured in `pyproject.toml` by item 001;
  installed via the `dev` extra). This item adds `tests/conftest.py`,
  `tests/synthetic.py`, and `tests/test_synthetic.py`.
- **Tests authored here** (`tests/test_synthetic.py`):
  - `test_affine_encodes_spacing` — `affine_from_spacing((1,1,3))` yields a 4×4
    affine whose diagonal voxel sizes are `(1,1,3)`.
  - `test_labelled_blocks_shape_and_labels` — the labelled-blocks case has the
    expected `shape`, the expected **set of integer labels**, and the expected
    **voxel count per label** (hand-computed from the block definitions).
  - `test_empty_case_has_no_foreground` — the empty label map is all zeros
    (`labelmap.max() == 0`, label set `{0}` / no foreground labels).
  - `test_anisotropic_spacing_roundtrip` — spacing recovered from the
    image header/zooms matches the requested anisotropic spacing.
  - `test_on_disk_roundtrip` — write a fixture with `write_nifti`, reload with
    `nibabel.load`, and assert array-equality and affine-equality (this proves
    the on-disk fixtures are valid NIfTI without depending on item 003's loader).
  - `test_determinism` — building the same case twice yields byte-for-byte equal
    arrays (no uncontrolled randomness).
- **Determinism / portability:** no network, no services, no GPU; fixed/seeded
  content. On-disk fixtures live only under pytest's `tmp_path`. Pure-Python +
  NumPy + NiBabel → identical behaviour on Windows, macOS, Linux.
- **Note on independence from item 003:** validation deliberately uses
  `nibabel.load` directly (not the future `segqc` loader) so this item is
  self-contained and does not pre-empt item 003's design.

---

## Dependencies

- **Upstream (blocks this item):** Item 001 (package skeleton, `tests/` dir,
  pytest config, `numpy`/`nibabel` declared). No code dependency on items 003+.
- **Downstream (this item unblocks):** effectively **every later test-driven
  item** — Item 003 (loader tests load these fixtures), Item 004 (label-mapping
  tests over the label sets), Item 006 (CLI end-to-end uses on-disk fixtures),
  Item 007 (empty detection uses the empty fixture), Items 008–010 and all
  feature/heuristic stages. Getting this API stable early reduces churn later.
- **New runtime/dev dependencies:** **none** — `numpy` and `nibabel` are already
  declared (item 001); `pytest` is already in the `dev` extra.

---

## Decisions & Trade-offs

Open implementation choices for this item, with recommendations. **Final
decisions recorded below (execution 2026-06-24).**

1. **Where the builder lives — `tests/synthetic.py` vs a shipped `segqc.testing`
   module.** **Decided: `tests/synthetic.py`** (plain functions, no pytest
   import) + `tests/conftest.py` for the pytest-fixture layer. Keeps test
   helpers out of the installed wheel and signals these are *baseline* fixtures,
   not the Stage 5 failure corpus. Trade-off: a future non-test consumer would
   need to promote them to `segqc.testing`; deferred until such a consumer
   exists.
2. **Fixture exposure — `conftest.py` fixtures vs direct function calls.**
   **Decided: both.** Pure builder functions in `synthetic.py` (callable
   anywhere) *and* thin `conftest.py` fixtures (`labelled_blocks`,
   `empty_labelmap`, `anisotropic`, plus `*_files` on-disk variants) wrapping
   them for ergonomic reuse.
3. **Bundle type — `@dataclass` vs `namedtuple` vs tuple.** **Decided: a frozen
   `@dataclass` `SyntheticCase`** (`scan_img`, `seg_img`, `expected_labels`,
   `voxel_counts`, `spacing`, `shape`, `description`, `blocks`) with a `.write()`
   helper. Self-documenting; later items assert against its known-good metadata.
4. **Label-map dtype.** **Decided: `uint16` for label maps, `int16` for scans**
   (typical CT-like). Exposed as `LABEL_DTYPE` / `SCAN_DTYPE` constants.
5. **Affine convention.** **Decided: minimal diagonal affine** (identity
   rotation, zero origin, voxel sizes on the diagonal) via
   `affine_from_spacing`. Item 003 owns faithful/oblique real-world affines —
   these fixtures intentionally do **not** cover rotated affines.
6. **`.nii` vs `.nii.gz` on-disk.** **Decided: support both** via the path
   suffix (NiBabel infers compression); `SyntheticCase.write` / the `*_files`
   fixtures **default to `.nii.gz`** to exercise the compressed path real
   VerSe/TotalSegmentator data uses. `test_on_disk_roundtrip` is parametrised
   over both extensions.
7. **Volume size.** **Decided: `16³` (`DEFAULT_SHAPE`)** — tiny/fast yet roomy
   enough for ≥3 non-touching 4³ blocks. Canonical block layouts are
   non-touching so per-label voxel counts are trivially hand-verifiable
   (count = product of box edge lengths: 64 for the isotropic blocks, 48 for the
   anisotropic ones).

### Implementation notes

- `tests/` has no `__init__.py`, so under pytest's default prepend import mode
  the directory is on `sys.path` and the module imports bare as `synthetic`
  (not `tests.synthetic`). Docstring/README examples reflect this.
- `make_labelmap` overlap semantics are **last-block-wins**; covered by a test.
  The canonical cases use non-overlapping boxes.
- `pyproject.toml` pytest config from item 001 was sufficient — **no change**
  needed (no new markers or `testpaths` entries).
- Final suite: **17 passed** (10 contract + 2 conftest-fixture + 5 item-001
  smoke), `pytest` green.

---

## Testing Prerequisites

### Required Services

**None.** This item produces test-support code and self-tests only — no
databases, APIs, message queues, or external services. (Row included because the
template requires it; Stage 9 introduces the first services.)

### Environment Configuration

- **Python:** 3.9 or newer on `PATH`.
- **Virtual environment:** the same venv from item 001 (`pip install -e .[dev]`),
  which provides `pytest`, `numpy`, and `nibabel`.
  - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`
- **Environment variables / secrets:** none.
- **Configuration files:** none beyond the existing `pyproject.toml`.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` is up to date (no new deps).
- [ ] **Tests pass:** `pytest` (or `python -m pytest`) is green — new
      `test_synthetic.py` tests **and** item 001's smoke tests.
- [ ] **Services started:** N/A — no services.
- [ ] **Application runs:** N/A — no CLI behaviour changes in this item.
- [ ] **Feature verified:**
  - Builders return valid `Nifti1Image` objects with the requested shape, label
    set, and spacing.
  - The anisotropic case reports the requested non-uniform spacing.
  - On-disk fixtures written under `tmp_path` reload via `nibabel.load` to the
    same array + affine.
- [ ] **Data verified:** label sets and per-label voxel counts match the
      hand-computed expectations encoded in the test assertions.
- [ ] **Health checks pass:** N/A — no server/health endpoint.

### Expected Outcomes

Concrete, verifiable results:

- `import`ing the builder and calling each canonical case returns a populated
  bundle (scan image, label-map image, expected metadata).
- `labelled_blocks_case()` → a volume with ≥3 distinct integer labels, each with
  a known voxel count, on isotropic spacing.
- `empty_case()` → a label map whose only value is `0` (no foreground labels).
- `anisotropic_case()` → spacing recovered from the header equals the requested
  anisotropic tuple (e.g. `(1.0, 1.0, 3.0)`).
- Writing any case with `write_nifti` then `nibabel.load` round-trips array and
  affine exactly.
- `pytest` reports all test modules passing with `0` failures (item 001's smoke
  tests included).

### Validation Documentation Template

```markdown
## Validation Results
- [ ] Service started: N/A (no services)
- [ ] Application started successfully: N/A (no CLI change)
- [ ] Database tables verified: N/A
- [ ] Seed data verified: N/A
- [ ] API endpoints verified: N/A
- [ ] Screenshots captured: N/A (no UI)
- [ ] `pytest` green: <N passed> (incl. item 001 smoke tests)
- [ ] Verified on OS: <OS + Python version>
```

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"`pytest` harness + tiny synthetic NIfTI fixtures"**
  deliverable from 📋 → ✅ (mark 🚧 while in progress).
- Do **not** mark Stage 0 *Acceptance* checkboxes that depend on later items
  (loader, label inventory, stub JSON) — those close with Items 003/004/006.
- Per `CLAUDE.md`: work on branch `aide/002-test-harness-fixtures`, push it
  **before** real work to claim the item, `git pull --rebase` before editing
  `progress.md`, and keep the edit scoped to this item's row. A work item may
  merge **straight to `main` (no PR)** once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 002` to
implement this work item.
