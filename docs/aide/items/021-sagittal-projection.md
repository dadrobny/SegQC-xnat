# Item 021 — Sagittal Projection of Centroids & Spline (Human-Report Visual)

> **Status:** 📋 Planned · **Created:** 2026-06-26
> **Stage:** 3 — Spinal Curve: Spline Fit & Geometric Deviation Features
> **Queue:** [`../queue/queue-002.md`](../queue/queue-002.md) · Item 021
> **Objectives:** Optional 2-D sagittal projection figure (centroids + spline)
> for the human-readable report; graceful no-op when matplotlib is unavailable.
> **Suggested branch:** `aide/021-sagittal-projection`

---

## Description

Render an **optional** 2-D sagittal projection of the vertebra centroids and the
fitted spline (item 017) for inclusion in the human-readable report (item 010).

The function:

1. Takes an ordered sequence of `LabelCentroid` objects (item 013) and a
   `SplineFit` (item 017) as inputs.
2. Projects each centroid onto the **sagittal plane** (x–z view, where x is the
   left–right axis and z is the superior–inferior axis; all mm coordinates).
3. Samples the fitted spline at a configurable number of points (default 200)
   and draws the resulting curve in the same plane.
4. Annotates each centroid marker with its `level_name` (e.g. `"T8"`, `"L3"`).
5. Saves the figure as a **PNG** file to a caller-supplied output path and
   returns that path.
6. **Graceful degradation**: when matplotlib is not importable (or when the
   `Agg` backend cannot be initialised), the function returns `None` **without
   raising any exception** and without crashing the surrounding pipeline.

### Public API

Expose the result as a single function in
`segqc/features/sagittal_projection.py`:

```python
def render_sagittal_projection(
    centroids: Sequence[LabelCentroid],
    spline_fit: SplineFit,
    output_path: Union[str, Path],
    *,
    n_spline_points: int = 200,
    dpi: int = 150,
) -> Optional[Path]:
    """Render a 2-D sagittal projection of centroids and the spline.

    Parameters
    ----------
    centroids:
        Ordered sequence of LabelCentroid objects (item 013).
    spline_fit:
        Fitted spline through the centroids (item 017).
    output_path:
        Destination file path for the PNG image.  The parent directory must
        already exist.  The file is overwritten if it already exists.
    n_spline_points:
        Number of parameter values at which to sample the spline for the
        curve overlay (default 200).
    dpi:
        Resolution of the saved figure in dots per inch (default 150).

    Returns
    -------
    Path
        Absolute path of the written PNG file, as a :class:`pathlib.Path`.
    None
        When matplotlib is unavailable or the backend cannot be initialised;
        the function returns ``None`` without raising.

    Raises
    ------
    ValueError
        When ``centroids`` is empty.
    """
```

### Scope boundary

| Concern | Owned by |
|---------|----------|
| Ordered centroid sequence | Item 014 (`SpineRelationships`) |
| Centroid mm-coordinates | Item 013 (`LabelCentroid.centroid_mm`) |
| Spline fit | Item 017 (`SplineFit`, `evaluate_spline`) |
| Human-readable report file I/O | Item 010 (`human_report.py`) |
| Wiring projection path into the report | Item 022 / pipeline wiring |
| Stage 3 JSON serialisation | Item 022 |

---

## Acceptance Criteria

- [ ] **AC1: PNG image artifact is produced for a fixture**: calling
      `render_sagittal_projection` with a valid centroid sequence and `SplineFit`
      writes a non-empty PNG file to the specified path and returns that path as
      a `pathlib.Path`.

- [ ] **AC2: Returned path matches the output_path argument**: the returned
      `Path` (when not `None`) is equal to `Path(output_path).resolve()` or at
      minimum points to the same file on disk.

- [ ] **AC3: Output file exists and is non-empty**: after a successful call the
      output file exists on disk and its size is > 0 bytes.

- [ ] **AC4: Output file is a valid PNG**: the written file starts with the PNG
      magic bytes (`b'\x89PNG'`), confirming it is a real PNG and not a truncated
      or corrupt file.

- [ ] **AC5: Output path is recorded / returned so callers can add it to the
      report**: the function return value is the concrete `Path` of the written
      file (or `None`), enabling the caller to embed the path in the
      human-readable report without further string manipulation.

- [ ] **AC6: Graceful degradation when matplotlib is unavailable**: when
      matplotlib cannot be imported (simulated by temporarily patching the import
      to raise `ImportError`), `render_sagittal_projection` returns `None`
      without raising any exception.

- [ ] **AC7: No crash when matplotlib Agg backend is unavailable**: when the
      `matplotlib.use("Agg")` call raises (simulated by patching), the function
      returns `None` without raising.

- [ ] **AC8: ValueError for empty centroid list**: calling
      `render_sagittal_projection` with an empty `centroids` list raises
      `ValueError` with a non-empty, human-readable message (this is a
      programmer error, not a backend-availability issue).

- [ ] **AC9: Determinism — same inputs produce the same file size**: calling
      the function twice with identical inputs writes files of identical byte
      size (pixel content is reproducible for the same data with the Agg
      backend).

- [ ] **AC10: Single-centroid input does not crash**: a sequence containing
      exactly one centroid is handled without raising an uncaught exception
      (either produces a valid PNG or raises `ValueError` with a clear message —
      the behaviour must be documented in the function docstring).

---

## Implementation Steps

1. **Create `src/segqc/features/sagittal_projection.py`**:
   - Guard all matplotlib imports inside `try/except ImportError` — never
     import matplotlib at module level (this preserves graceful degradation).
   - Implement `render_sagittal_projection(centroids, spline_fit, output_path, *,
     n_spline_points=200, dpi=150) -> Optional[Path]`:
     - Validate: raise `ValueError` if `len(centroids) == 0`.
     - `try: import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt`
       inside the function body; `except (ImportError, Exception): return None`.
     - Extract `(x_mm, z_mm)` from each `centroid.centroid_mm` (indices 0 and 2).
     - Sample the spline: `u_vals = np.linspace(0, 1, n_spline_points)`,
       `pts = evaluate_spline(spline_fit, u_vals)` → columns 0 and 2 are the
       sagittal-plane coordinates.
     - Plot: scatter centroid markers, annotate with `level_name`, overlay the
       spline curve; invert the y axis so superior is up (z decreases toward
       image bottom in some conventions — document the chosen convention).
     - Save to `output_path` with `plt.savefig(..., dpi=dpi)`, then `plt.close()`.
     - Return `Path(output_path)`.

2. **Export from `segqc/features/__init__.py`** (optional, consistent with
   siblings — at minimum a comment pointing to the module).

---

## Testing Strategy

- **Framework:** `pytest` with `tmp_path` for on-disk PNG output.
- **Unit tests** (`tests/test_021_sagittal_projection.py`): all ten ACs;
  adversarial inputs (empty list, single centroid, collinear centroids,
  anisotropic spacing, very large mm coordinates, output path with deep parent,
  existing file overwrite); graceful degradation via `unittest.mock.patch`;
  import contract; determinism; PNG magic-byte validation.
- **No NIfTI loading** — tests use inline `LabelCentroid` objects and
  `fit_centroid_spline` (item 017 helper), same as items 017–020.

---

## Dependencies

- **Upstream (all merged):**
  - Item 001 (package scaffold)
  - Item 002 (synthetic fixtures)
  - Item 013 (`LabelCentroid`)
  - Item 017 (`SplineFit`, `fit_centroid_spline`, `evaluate_spline`)
  - `matplotlib` (optional soft dependency — `[dev]` extras only, never required)
  - `numpy` (already a hard dependency)
- **Downstream:** Item 022 (Stage 3 serialisation / report wiring).

---

## Decisions & Trade-offs

1. **Matplotlib is an optional soft dependency** — never imported at module level
   so `import segqc` does not fail on headless servers without a display.  The
   `try/except` guard is inside the function body.

2. **Sagittal plane = x–z (mm)** — the x axis is left–right and z is
   superior–inferior in the NIfTI convention used by this project.  Tests
   should not depend on a specific axis orientation but should verify that 2
   dimensions of the 3-D centroid coordinates are plotted.

3. **Agg backend enforced** — `matplotlib.use("Agg")` is called before any
   pyplot import to guarantee headless rendering.  Failure to set the backend
   is caught and returns `None`.

4. **`plt.close()` always called** — prevents memory leaks when the function is
   called in a loop (one figure per case).

5. **`ValueError` for empty list** — consistent with items 017 and 020; a
   zero-centroid call is a programmer error, not a backend-availability issue,
   so it raises rather than silently returns `None`.

6. **Single-centroid behaviour** — a single point cannot define a spline
   (item 017 raises `ValueError`), so `render_sagittal_projection` with one
   centroid should also raise `ValueError` with a clear message.  This is an
   edge case the pipeline must guard against upstream.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python + NumPy + optional matplotlib (Agg); no external services,
no network, no display.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]` (includes matplotlib).
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_021_sagittal_projection.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–020.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 3 **"Sagittal projection"** deliverable from 📋 → ✅.
- Per `CLAUDE.md`: work on branch `aide/021-sagittal-projection`,
  `git pull --rebase` before editing `progress.md`, keep edits scoped to this
  item's rows, and direct-merge (no PR required) once green.
