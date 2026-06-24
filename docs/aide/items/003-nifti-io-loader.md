# Item 003 — NIfTI I/O Loader

> **Status:** 📋 Planned · **Created:** 2026-06-24
> **Stage:** 0 — Project Scaffolding & I/O Foundation
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 003
> **Objectives:** Foundation (I/O substrate for G1–G4 and every later stage)
> **Suggested branch:** `aide/003-nifti-io-loader`

---

## Description

Implement loading of a **scan** and an **instance label map** from NIfTI,
preserving **spacing/affine** and correctly handling **anisotropic** voxels.
Expose a clean, immutable in-memory representation — array + spacing + affine +
label inventory — that every downstream feature, heuristic, and report consumer
reads from. Validate inputs and fail with **clear, actionable errors** on
malformed, missing, or mismatched files.

This item sits on the **critical path** (`001 → 003 → 004 → 006`). Item 001 has
landed the package skeleton (`src/segqc/`, `pyproject.toml` declaring NiBabel,
the `segqc run` argparse stub). This item produces the loading layer that Item
006 wires into the CLI `run` command, and that Items 004 (label convention),
007 (empty detection), and Stage 2 (feature extraction) all build on.

NiBabel is already the declared primary NIfTI library (Item 001, Decision 6);
this item uses it. SimpleITK remains deferred unless a concrete need surfaces
here (record it in Decisions if so).

### Scope boundary (what this item does *not* do)

This item is **I/O + the in-memory volume model only**. To avoid overlap:

| Concern | Owned by | This item |
|---|---|---|
| Integer-label ↔ anatomical-vertebra mapping | Item 004 | exposes the *raw* present label values + counts only; no anatomical names |
| Logging config + heuristic-config scaffold | Item 005 | raises plain exceptions; no logging framework, no config file |
| Wiring loader into the CLI `run` command | Item 006 | provides the callable API; does **not** edit `cli.py`'s `run` body |
| Geometric/topological features (volumes, centroids, CC) | Stage 2 | only a bare label inventory (value → voxel count) |
| Empty / near-empty verdicts | Item 007 | reports facts (counts), makes **no** pass/fail judgement |
| The pytest harness + canonical synthetic fixtures | Item 002 | see *Fixture dependency* below |

### Fixture dependency (Item 002 is in progress on a parallel branch)

Item 002 (`aide/002-test-harness-fixtures`) owns the canonical synthetic-NIfTI
fixture builder and is claimed by another collaborator — **not yet merged to
`main`**. To keep this item independently testable without colliding with Item
002:

- Author this item's tests against **small NIfTI volumes built inline** with
  NiBabel (`nib.Nifti1Image(np.array(...), affine)`) inside `tests/`, written to
  pytest's `tmp_path`. Keep them local and minimal — do **not** create a
  competing shared `tests/fixtures/` builder module.
- When Item 002 merges, a follow-up may migrate these inline volumes onto the
  canonical fixture builder. Note that as a known follow-up rather than blocking
  on it.

---

## Acceptance Criteria

- [ ] A loader module exists (proposed `src/segqc/io.py`) exposing a documented
      public function — proposed `load_volume(path) -> Volume` — and a
      higher-level `load_case(scan_path, seg_path) -> Case` (names finalised in
      Decisions).
- [ ] An immutable in-memory representation (proposed `Volume` dataclass) carries
      at least: the voxel `data` array, `spacing` (3-tuple of physical voxel
      sizes), the 4×4 `affine`, and the source `path`.
- [ ] **Spacing/affine are preserved faithfully** from the NIfTI header — spacing
      is derived from the affine (not assumed isotropic), and the affine
      round-trips equal (within float tolerance) to NiBabel's `img.affine`.
- [ ] **Anisotropic voxels are represented correctly** — a fixture with spacing
      e.g. `(0.5, 0.5, 3.0)` yields exactly that `spacing` tuple in the loaded
      `Volume`.
- [ ] The **label map** loads with an **integer** dtype (label values are not
      silently cast to float); a label inventory is exposed as a mapping
      `{label_value: voxel_count}` over present non-zero labels (zero treated as
      background — confirm in Decisions).
- [ ] `load_case` validates that scan and segmentation share the **same shape**
      and **compatible affine/spacing**, and raises a clear error otherwise
      (see Decisions for strict-vs-tolerant policy).
- [ ] **Clear, typed errors** on failure: missing file → a descriptive error
      naming the path; non-NIfTI / unreadable file → a wrapped error; shape
      mismatch → an error naming both shapes. A small exception type (proposed
      `SegQCInputError`) is defined rather than leaking raw `OSError`/library
      internals.
- [ ] Loading does **not** force the whole dataset into memory more than once and
      does not mutate the caller's arrays (returned arrays are safe to read).
- [ ] Unit tests cover: correct shape, dtype, spacing, affine; anisotropic
      spacing; label inventory; and each error path (missing file, shape
      mismatch, malformed input).
- [ ] Runs CPU-only on Windows, macOS, and Linux (NiBabel is pure-Python; no
      platform-specific code).

---

## Implementation Steps

1. **Confirm the public API surface** (see Decisions). Proposed:
   ```
   src/segqc/io.py
     class SegQCInputError(Exception): ...
     @dataclass(frozen=True)
     class Volume:
         data: np.ndarray
         spacing: tuple[float, float, float]
         affine: np.ndarray         # 4x4
         path: str
     @dataclass(frozen=True)
     class Case:
         scan: Volume
         seg: Volume
         label_inventory: dict[int, int]   # label value -> voxel count
     def load_volume(path, *, integer_labels=False) -> Volume: ...
     def load_case(scan_path, seg_path) -> Case: ...
   ```
2. **Implement `load_volume`** using `nibabel.load`:
   - Resolve/validate the path first; raise `SegQCInputError` naming the path if
     it does not exist or NiBabel cannot read it (wrap the underlying exception).
   - Read the array via `np.asarray(img.dataobj)` (or `get_fdata()` for the scan;
     see Decision on dtype) — for the **label map**, read with the header's
     integer dtype preserved (avoid `get_fdata()`'s float cast).
   - Derive `spacing` from the affine (`nib.affines.voxel_sizes(affine)` or
     `img.header.get_zooms()[:3]`), as a plain `float` 3-tuple.
   - Keep `affine = np.asarray(img.affine, dtype=float)`.
3. **Implement the label inventory**: `np.unique(seg.data, return_counts=True)`,
   excluding background (`0`), as a `dict[int, int]` sorted by label value.
4. **Implement `load_case`**:
   - Load scan and seg.
   - Validate shape equality; validate affine/spacing compatibility within
     tolerance (per Decision). Raise `SegQCInputError` with both values on
     mismatch.
   - Build and attach the label inventory.
5. **Error handling**: a single `SegQCInputError` with clear messages; never let
   a bare `FileNotFoundError`/NiBabel `ImageFileError` escape unwrapped.
6. **Docstrings + type hints** on all public symbols. Keep imports lazy/cheap so
   `import segqc` stays fast (NiBabel import is fine; do not import SciPy/skimage
   here).
7. **Tests** in `tests/test_io.py` building inline NIfTI volumes into `tmp_path`
   (see Testing Strategy). No edits to `cli.py` (that is Item 006).
8. **Verify** the manual validation checklist in a clean venv.

---

## Testing Strategy

- **Framework:** `pytest` (already wired by Item 001; the canonical fixture
  builder is Item 002 — this item uses inline volumes, see Fixture dependency).
- **Fixtures:** build tiny NIfTI files inside tests with NiBabel + NumPy and
  write them to `tmp_path`, e.g.:
  ```python
  import numpy as np, nibabel as nib
  def _write_nii(tmp_path, data, spacing):
      affine = np.diag([*spacing, 1.0])
      p = tmp_path / "vol.nii.gz"
      nib.save(nib.Nifti1Image(data, affine), p)
      return p
  ```
- **Tests authored here:**
  - `test_load_volume_shape_dtype` — array shape and (for the label map) integer
    dtype are preserved.
  - `test_spacing_isotropic` and `test_spacing_anisotropic` — spacing `(1,1,1)`
    and e.g. `(0.5, 0.5, 3.0)` are read back exactly.
  - `test_affine_preserved` — loaded affine equals the written affine
    (`np.allclose`).
  - `test_label_inventory` — a label map with known voxel counts yields the
    expected `{label: count}` (background `0` excluded).
  - `test_load_case_shape_mismatch_raises` — scan/seg of differing shapes raise
    `SegQCInputError` naming both shapes.
  - `test_missing_file_raises` — nonexistent path raises `SegQCInputError`
    naming the path.
  - `test_malformed_file_raises` — a non-NIfTI file (e.g. a text file renamed
    `.nii.gz`) raises `SegQCInputError`.
- **Determinism / portability:** all volumes are generated in-process and written
  to `tmp_path`; no network, no GPU, no committed binaries. Identical behaviour
  on all three OSes.

---

## Dependencies

- **Upstream (blocks this item):** Item 001 (package skeleton, NiBabel declared
  in `pyproject.toml`) — **complete**.
- **Soft dependency:** Item 002 (canonical fixtures) is in progress on
  `aide/002-test-harness-fixtures`. This item does **not** block on it — it uses
  inline `tmp_path` volumes (see Fixture dependency). A follow-up may migrate
  tests onto the shared fixtures after Item 002 merges.
- **Downstream (this item unblocks):** Item 004 (label convention consumes the
  label inventory), Item 006 (CLI `run` calls `load_case`), Item 007 (empty
  detection reads the inventory/foreground), and all of Stage 2 (feature
  extraction reads `Volume.data` + `spacing`).

---

## Decisions & Trade-offs

Open implementation choices for this item, with recommendations. Record the final
decision and rationale here during execution.

*To be updated during implementation.*

1. **NIfTI library — NiBabel (recommended) vs SimpleITK.** Item 001 already chose
   NiBabel as the sole declared NIfTI dependency. *Recommendation: NiBabel.*
   Revisit only if a concrete NiBabel limitation appears (e.g. an orientation or
   compression case it mishandles).
2. **Scan dtype — `get_fdata()` (float64, recommended for the scan) vs
   `dataobj` (native dtype).** Intensity scans benefit from float for later
   intensity features (Stage 8); **label maps must stay integer**. *Recommended:
   float for the scan, native-integer for the segmentation (an `integer_labels`
   flag, or a dedicated `load_label_map`).*
3. **Background label.** Treat `0` as background and exclude it from the label
   inventory. *Recommended: yes* — but expose total foreground voxel count too
   (Item 007 needs it). Confirm whether the inventory should optionally include
   `0`.
4. **Affine/spacing compatibility policy in `load_case` — strict equality vs
   tolerant (recommended).** Real scan/seg pairs can carry tiny float
   differences. *Recommended: compare within an absolute+relative tolerance
   (`np.allclose`), error only on meaningful divergence; always error on shape
   mismatch.* Document the tolerance.
5. **Representation type — frozen `@dataclass` (recommended) vs `NamedTuple` vs
   dict.** *Recommended: frozen dataclass* for immutability + clear typing while
   allowing numpy-array fields.
6. **Module name — `io.py` vs `loaders.py`.** `io` shadows the stdlib module name
   *as a submodule* (`segqc.io` is unambiguous, but some find it confusing).
   *Recommendation: confirm `segqc.io` is acceptable, else `segqc.loaders`.*
7. **Lazy vs eager array read.** `img.dataobj` defers I/O; `get_fdata()` reads
   eagerly and caches. For small QC volumes eager is simplest. *Recommended:
   eager read, returning a concrete `np.ndarray`* (downstream code expects a real
   array). Note memory implications for very large volumes as a future concern.

---

## Testing Prerequisites

### Required Services

**None.** This item is a self-contained Python I/O module. No databases, APIs,
message queues, or other external services. (Row included per the work-item
template; services first appear in Stage 9 XNAT/Docker work.)

### Environment Configuration

- **Python:** 3.9 or newer on `PATH`.
- **Virtual environment:** clean venv recommended (`python -m venv .venv`, then
  activate).
  - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`
- **Install:** `pip install -e .[dev]` (pulls NiBabel + NumPy + pytest).
- **Environment variables / secrets:** none.
- **Configuration files:** none authored by this item.
- **Ports:** none.
- **Test data:** generated in-process to `tmp_path`; nothing committed, nothing
  downloaded.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` completes on Python 3.9+.
- [ ] **Tests pass:** `pytest` (or `python -m pytest`) is green, including the new
      `tests/test_io.py`.
- [ ] **Services started:** N/A — no services.
- [ ] **Application runs:** `python -c "import segqc.io"` imports cleanly (and
      `segqc --help` still exits `0`, unaffected by this item).
- [ ] **Feature verified:** in a Python REPL, `load_case` on two inline-written
      NIfTI volumes returns a `Case` whose `scan.spacing` / `seg.spacing` match
      the written spacing and whose `label_inventory` matches the known counts.
- [ ] **Data verified:** the loaded `affine` equals the written affine
      (`np.allclose`); the anisotropic-spacing volume reports the exact
      `(0.5, 0.5, 3.0)` spacing.
- [ ] **Health checks pass:** N/A — no server/health endpoint.

### Expected Outcomes

- `import segqc.io` succeeds; `load_volume` / `load_case` are importable and
  type-hinted.
- A loaded `Volume` reports the correct `data.shape`, integer dtype for label
  maps, the exact `spacing` (isotropic **and** anisotropic cases), and an
  `affine` equal to the source within float tolerance.
- `label_inventory` is `{label_value: voxel_count}` over present non-zero labels,
  matching hand-computed counts on a crafted fixture.
- Error paths raise `SegQCInputError` with a message naming the offending path or
  the mismatched shapes — no bare `OSError`/NiBabel internals leak.
- `pytest` reports `tests/test_io.py` passing with `0` failures.

---

## Validation Results

> To be completed during execution (record OS, Python version, and `pytest`
> summary).

- [ ] Service started: N/A (no services)
- [ ] Application started successfully: `import segqc.io` clean; `segqc --help`
      still exits `0`
- [ ] Database tables verified: N/A
- [ ] Seed data verified: N/A
- [ ] API endpoints verified: N/A
- [ ] Screenshots captured: N/A (no UI)
- [ ] `pip install -e .[dev]` clean install: _TBD_
- [ ] `pytest` green: _TBD_ (expect `tests/test_io.py` + existing smoke tests)
- [ ] Verified on OS: _TBD_

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"NIfTI loader for scan + label map, preserving
  spacing/affine, handling anisotropy"** deliverable from 📋 → ✅ (mark it 🚧
  while in progress).
- Do **not** tick the Stage 0 *Acceptance* checkboxes that also depend on Items
  004/006 (label inventory with anatomical names, stub JSON) — those close with
  their own items.
- Per `CLAUDE.md`: work on branch `aide/003-nifti-io-loader` (push it **before**
  real work to claim the item), `git pull --rebase` before editing
  `progress.md`, and keep the edit scoped to this item's row. A work item may
  merge **straight to `main` once green — no PR required**.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 003` to
implement this work item.
