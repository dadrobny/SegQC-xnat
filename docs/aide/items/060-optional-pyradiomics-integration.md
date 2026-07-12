# Item 060 — Optional PyRadiomics integration behind an optional-import adapter

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 060
> **Objectives:** G6 (portable execution — a heavy/finicky lib is never *required*; CPU-only default suite runs with PyRadiomics absent), G8 (extensible — documented path to richer texture/shape features) — enables G2/G7 downstream (richer features for future heuristics; deterministic & regression-testable)
> **Suggested branch:** `aide/060-optional-pyradiomics-integration-behind-an`

---

## Description

Add the **optional PyRadiomics** path for Stage 8 (deliverable 1) behind a
capability/adapter boundary in a new module `src/segqc/features/radiomics.py`.
The adapter sits *alongside* item 059's hand-rolled first-order extractor
(`src/segqc/features/intensity.py`): when the PyRadiomics library is importable it
computes a **documented subset of richer radiomics features** (a texture family —
GLCM — plus shape) per label from the same scan+mask pair; when PyRadiomics is
**absent** it cleanly degrades to the item-059 first-order features only — never a
hard failure, never a hard dependency.

The **normal, designed-for case is PyRadiomics absent** (it is deliberately kept
an *optional extra* in `pyproject.toml` because the library has historically had
install friction across platforms/Python versions — precisely why the roadmap
marks it "optional"). The default test suite therefore runs green and fast with
PyRadiomics **not installed**; the present-path behaviour is exercised only by a
**skippable** test guarded by `pytest.importorskip("radiomics")`.

The adapter normalises its output into a single per-label result shape so
downstream fusion (item 061) is **source-agnostic**: every result carries the
authoritative item-059 first-order block plus an *extended* mapping of
higher-order features (empty when unavailable), and records a **provenance/backend
marker** so a report can state which backend produced the extended features.

**In scope:** the optional-import capability probe; a normalised per-label result
dataclass wrapping the item-059 first-order block + an extended feature mapping +
a backend/provenance marker; graceful degradation (builtin-only) when PyRadiomics
is absent or explicitly disabled; the PyRadiomics wrapper (documented feature
subset, pinned deterministic extractor settings) when present; the per-case
convenience map; grid-alignment and empty-label guards; and declaring the
`radiomics` optional extra in `pyproject.toml`.

**Explicitly NOT in scope** (later Stage-8 items that *consume* this output):
fusion into the JSON `features` block, feature table, or human report (061); any
heuristic/rule firing on intensity or radiomics features (062); reference
distributions or the delta-to-reference rule (063/064); `segqc run` CLI wiring and
the enable/disable **config knob** (065 — this item only exposes the parameter
seam). No thresholds or plausibility judgements are made here — this item only
*measures*.

## Acceptance Criteria

- [ ] **AC1: Module & guarded optional import.** `src/segqc/features/radiomics.py`
  exists and **imports successfully even when PyRadiomics is not installed** (the
  `import radiomics` is wrapped so that a missing dependency never propagates an
  `ImportError` at module import time). It exposes `pyradiomics_available`,
  `LabelRadiomics`, `compute_label_radiomics`, and `compute_radiomics_features`
  (listed in `__all__`).

- [ ] **AC2: Capability probe.** `pyradiomics_available() -> bool` returns `False`
  when the `radiomics` package cannot be imported and `True` when it can; it never
  raises. (In the default CI environment, PyRadiomics is absent, so it returns
  `False`.)

- [ ] **AC3: Normalised per-label result shape.** `LabelRadiomics` is a frozen
  dataclass with exactly: `first_order: LabelIntensity` (the item-059 block),
  `extended: Dict[str, float]` (higher-order features; `{}` when unavailable),
  `backend: str` (provenance marker for the extended features), and
  `radiomics_available: bool`. All fields are JSON-friendly, carry no nibabel
  objects, and the dataclass is comparable with `==`.

- [ ] **AC4: First-order is authoritative & backend-independent (absent path).**
  On the builtin path, `result.first_order` is **equal** to
  `compute_label_intensity(scan_img, seg_img, label)` (item 059) for the same
  inputs — the canonical first-order features are produced by item 059, not by the
  optional backend.

- [ ] **AC5: Graceful degradation when absent (NORMAL case).** When PyRadiomics is
  not importable, `compute_label_radiomics(scan_img, seg_img, label)` returns a
  `LabelRadiomics` with a populated `first_order`, `extended == {}`,
  `backend == "builtin"`, and `radiomics_available is False` — and raises **no**
  `ImportError` or other exception.

- [ ] **AC6: Explicit disable seam.** `compute_label_radiomics(..., enable_pyradiomics=False)`
  forces the builtin (first-order-only) path — `extended == {}`,
  `backend == "builtin"`, `radiomics_available is False` — **even if** PyRadiomics
  happens to be installed, giving a deterministic, backend-independent path (the
  seam item 065's config knob will drive).

- [ ] **AC7: No hard dependency.** PyRadiomics appears **only** as an optional
  extra in `pyproject.toml` `[project.optional-dependencies]` (e.g. a `radiomics`
  extra installable via `pip install segqc[radiomics]`) and **not** in the core
  `dependencies`; importing `segqc`, `segqc.features`, and
  `segqc.features.radiomics` succeeds with PyRadiomics absent.

- [ ] **AC8: Per-case convenience map.** `compute_radiomics_features(scan_img,
  seg_img, *, enable_pyradiomics=True) -> Dict[int, LabelRadiomics]` returns one
  entry per present non-zero label (background `0` excluded); each value equals the
  corresponding `compute_label_radiomics` call with the same arguments.

- [ ] **AC9: Grid-alignment guard.** A scan and segmentation with mismatched array
  shape, or incompatible affine (beyond the item-059 tolerance), raise a clear
  `ValueError` on **both** the builtin and (guarded) present paths; aligned inputs
  do not.

- [ ] **AC10: Empty / absent-label handling.** For an absent or empty label,
  `result.first_order` is the item-059 sentinel (`voxel_count == 0`),
  `result.extended == {}` (the PyRadiomics wrapper is **not** invoked on a
  zero-voxel mask), and no exception is raised — on both paths.

- [ ] **AC11: Determinism & purity (absent path).** Repeated
  `compute_label_radiomics` calls on identical inputs compare equal (`==`), and a
  call does not mutate the scan or segmentation image data (arrays byte-identical
  before and after).

- [ ] **AC12: Documented extended feature subset (present path, skippable).**
  Guarded by `pytest.importorskip("radiomics")`: when PyRadiomics is present,
  `result.extended` is a non-empty `Dict[str, float]` populated with the module's
  **documented** higher-order subset (a GLCM texture family and shape features),
  keyed by documented names, each value a finite `float`.

- [ ] **AC13: Present-path provenance & first-order invariance (skippable).**
  Guarded by `pytest.importorskip("radiomics")`: when PyRadiomics is present and
  enabled, `backend == "pyradiomics"` and `radiomics_available is True`, **and**
  `result.first_order` still equals `compute_label_intensity(...)` (item 059) —
  installing PyRadiomics does not change the canonical first-order features.

- [ ] **AC14: Present-path determinism (skippable).** Guarded by
  `pytest.importorskip("radiomics")`: with pinned extractor settings, two
  extractions on the same scan+mask produce equal `extended` values.

## Assumptions  <!-- MANDATORY -->

- **Clarify mode `assume`** (`aide.toml` `loop.clarify = "assume"`): no blocking
  questions were asked; each ambiguity below is resolved with the most defensible
  default and pinned here for validator audit.
- **First-order stays authoritative from item 059 (pin — key decision).** Even
  when PyRadiomics is present, the canonical `first_order` block is produced by
  item 059's deterministic `compute_label_intensity`, **not** by PyRadiomics.
  Rationale: the item-062 implausible-intensity heuristic and item-064
  delta-to-reference intensity rule consume first-order features; their firing must
  **not** silently change depending on whether an optional library happens to be
  installed. PyRadiomics therefore contributes only the *additional* higher-order
  families into `extended`. (The queue phrase "PyRadiomics computes first-order +
  GLCM + shape" is honoured by *enabling* those classes in the extractor, but the
  first-order values surfaced as `LabelRadiomics.first_order` come from item 059;
  if the builder chooses to also capture PyRadiomics' own first-order values, they
  must be namespaced inside `extended`, never overwriting `first_order`.)
- **Result shape (pin).** The normalised per-label shape is a frozen
  `LabelRadiomics` dataclass wrapping `first_order: LabelIntensity` +
  `extended: Dict[str, float]` + `backend: str` + `radiomics_available: bool`.
  This keeps downstream fusion (061) source-agnostic: it can always read the same
  `first_order` shape and optionally iterate `extended`. `extended` is a flat
  `str -> float` mapping (not a nested dataclass) because the higher-order feature
  set is backend-defined and variable.
- **Provenance model (pin).** `backend` marks the source of the `extended`
  features (`"builtin"` ⇒ none, `"pyradiomics"` ⇒ PyRadiomics). `first_order` is
  documented as always builtin (item 059). Per-feature provenance is therefore
  recoverable from the structure without a separate per-key map; a heavier
  per-feature provenance dict is deliberately avoided as over-engineering for this
  item.
- **Backend marker constants (pin).** `backend` takes the string values
  `"builtin"` and `"pyradiomics"` (exposed as module constants, e.g.
  `RADIOMICS_BACKEND_BUILTIN` / `RADIOMICS_BACKEND_PYRADIOMICS`).
- **Optional extra name & pin (pin).** The extra is named `radiomics` in
  `pyproject.toml` (`pip install segqc[radiomics]`) and pins `pyradiomics` with a
  conservative lower bound (e.g. `pyradiomics>=3.0`); PyRadiomics transitively
  pulls SimpleITK. The PyPI package is `pyradiomics` but its import name is
  `radiomics` — hence `pytest.importorskip("radiomics")` and `import radiomics`.
- **Documented feature subset (pin, documented in module).** The present path
  enables a **GLCM** texture family and **shape** features (plus first-order as
  PyRadiomics computes them, captured only inside `extended`). The exact enabled
  classes and any per-class feature list are documented in the module docstring and
  may be trimmed by the builder so long as AC12 holds (`extended` non-empty with
  documented GLCM + shape keys, finite floats).
- **Pinned deterministic extractor settings (pin).** PyRadiomics is invoked with
  fixed settings (e.g. a fixed `binWidth`, no resampling/interpolation, fixed
  enabled feature classes) declared as module constants, so present-path output is
  reproducible (AC14). Arrays are handed to PyRadiomics as SimpleITK images built
  from the NumPy scan/mask with the label's spacing; no randomness is introduced.
- **Signature & input types (pin).** Public functions take
  `nibabel.Nifti1Image` `scan_img`/`seg_img` (+ `int label` for the single-label
  call) and a keyword-only `enable_pyradiomics: bool = True`, matching item 059's
  `Nifti1Image`-based signature so 061 can call either extractor uniformly.
- **Alignment guard reuse (pin).** The scan↔label grid-alignment guard reuses item
  059's check (same shape-exact / affine `rtol=1e-5, atol=1e-4` tolerance), either
  by reusing `intensity._check_alignment` or transitively via the
  `compute_label_intensity` call that produces `first_order` (which raises before
  any PyRadiomics work). Either is acceptable provided AC9 holds on both paths.
- **Empty/non-finite mask policy (pin).** When the item-059 first-order block has
  `voxel_count == 0` (empty/absent label, or all-non-finite), the PyRadiomics
  wrapper is skipped and `extended == {}` — PyRadiomics is never asked to extract
  from an empty mask (it would error). This makes AC10 hold identically on both
  paths.
- **Dependency 059 is ✅ (verified).** `src/segqc/features/intensity.py` exports
  `LabelIntensity`, `compute_label_intensity`, `compute_intensity_features`, and
  the private `_check_alignment` guard, as this spec assumes. If that interface
  diverged, hand back.

## Implementation Steps

_Intended code path under `src/segqc` (`aide.toml` `source_dir = "src/segqc"`)._

1. **`pyproject.toml`:** add a `radiomics = ["pyradiomics>=3.0"]` entry under
   `[project.optional-dependencies]` (leaving core `dependencies` untouched).
   Document in a comment that it is optional and install-finicky, hence gated.
2. **Create `src/segqc/features/radiomics.py`** with a module docstring
   documenting: the optional-import boundary, the normalised `LabelRadiomics`
   shape, the "first-order always from item 059" decision, the documented enabled
   feature classes (GLCM + shape), the pinned extractor settings, and the
   provenance model. Set `__all__` to the four public names + backend constants.
3. **Guarded import:** attempt `import radiomics` (and the extractor class, e.g.
   `from radiomics.featureextractor import RadiomicsFeatureExtractor`) inside a
   `try/except ImportError`, setting a module-level availability flag. Implement
   `pyradiomics_available() -> bool` over that flag (never raising).
4. **Define `LabelRadiomics`** as a frozen dataclass with the AC3 fields, and the
   `RADIOMICS_BACKEND_BUILTIN` / `RADIOMICS_BACKEND_PYRADIOMICS` constants.
5. **Implement `compute_label_radiomics(scan_img, seg_img, label, *,
   enable_pyradiomics=True)`:**
   - Compute `first_order = compute_label_intensity(scan_img, seg_img, label)`
     (item 059) — this also performs the alignment guard (AC9) and yields the
     sentinel for empty labels (AC10).
   - If `not (enable_pyradiomics and pyradiomics_available())` **or**
     `first_order.voxel_count == 0`: return `LabelRadiomics(first_order,
     extended={}, backend=BUILTIN, radiomics_available=False)`.
   - Otherwise build SimpleITK scan/mask images (numpy arrays + spacing) restricted
     to `label`, run the pinned-settings extractor, normalise the result into a
     `Dict[str, float]` of the documented GLCM + shape keys (finite floats), and
     return `LabelRadiomics(first_order, extended, backend=PYRADIOMICS,
     radiomics_available=True)`.
6. **Implement `compute_radiomics_features(scan_img, seg_img, *,
   enable_pyradiomics=True)`:** enumerate present non-zero labels (as item 059's
   `compute_intensity_features` does) and return
   `{label: compute_label_radiomics(...)}`.
7. **Keep the builtin path pure NumPy/nibabel + item 059** (no PyRadiomics import
   reached). Do **not** touch `features/__init__.py`, `report.py`,
   `feature_report.py`, `heuristics/*`, `config.py`, or the CLI (items 061/062/065).

## Testing Strategy

_One focused test per AC plus adversarial/edge cases; new module
`tests/test_features_radiomics.py`. The absent-path tests are the bulk and must
pass in the default (PyRadiomics-absent) environment; present-path tests are
guarded by `pytest.importorskip("radiomics")` so they skip cleanly in CI._

- **Module import & API (AC1).** Import `segqc.features.radiomics` and assert the
  four public names exist; assert the import itself raised nothing. (Runs with
  PyRadiomics absent — the normal case.)
- **Capability probe (AC2).** `pyradiomics_available()` returns a `bool` and does
  not raise; in the CI env it returns `False`.
- **Result shape (AC3).** On a hand-built `Nifti1Image` scan+seg pair, the result
  is a frozen `LabelRadiomics` with the four documented fields of the documented
  types; `extended` is a `dict`.
- **First-order equality (AC4).** `result.first_order ==
  compute_label_intensity(scan_img, seg_img, label)` for a multi-label fixture.
- **Graceful degradation (AC5).** With PyRadiomics absent, assert `extended == {}`,
  `backend == "builtin"`, `radiomics_available is False`, and no exception.
- **Explicit disable (AC6).** `enable_pyradiomics=False` yields the builtin markers
  regardless of availability (assert the markers; test is meaningful in both envs).
- **No hard dependency (AC7).** Parse `pyproject.toml` and assert `pyradiomics`
  is under the `radiomics` optional extra and **absent** from core `dependencies`;
  assert `import segqc`, `import segqc.features`, `import segqc.features.radiomics`
  all succeed.
- **Per-case map (AC8).** Keys == present non-zero labels; each value equals the
  corresponding single-label call.
- **Alignment guards (AC9).** Mismatched-shape and mismatched-affine pairs raise
  `ValueError` (assert on the builtin path directly; document that the present path
  raises via the shared guard before any PyRadiomics work).
- **Empty/absent label (AC10).** Absent label and all-background mask → sentinel
  `first_order` (`voxel_count == 0`), `extended == {}`, no exception.
- **Determinism & purity (AC11).** Snapshot input arrays (`.copy()`), assert
  byte-equality post-call; call twice and assert `==`.
- **Present-path (AC12/AC13/AC14) — skippable.** `pytest.importorskip("radiomics")`
  at the top of a dedicated test/class: on a small painted fixture assert
  `extended` is non-empty with the documented GLCM + shape keys (finite floats);
  `backend == "pyradiomics"`, `radiomics_available is True`, and `first_order`
  still equals the item-059 result; two extractions produce equal `extended`.
- **Adversarial extras.** `enable_pyradiomics=True` with PyRadiomics absent must
  still degrade (not attempt import of a missing lib mid-call); a single-voxel
  label on the builtin path returns a valid sentinel/degenerate first-order block
  with `extended == {}`.

## Dependencies

- **Item 059 — Per-label first-order intensity feature extractor (✅).** Provides
  `LabelIntensity`, `compute_label_intensity`, `compute_intensity_features`, and
  the `_check_alignment` guard that this adapter wraps and that supply the
  authoritative `first_order` block and the empty/sentinel + alignment behaviour
  (AC4/AC9/AC10). `src/segqc/features/intensity.py`.
- **Item 058 — Intensity-bearing synthetic scan fixtures (✅).** Provides the
  committed `tests/corpus/intensity/` scan+label fixtures used by the present-path
  (skippable) test and as realistic multi-label inputs. `src/segqc/synth/intensity.py`.
- **Item 003 — I/O & volume model (✅).** `segqc.io` spacing/affine conventions and
  the fixture-loading path used in tests.

Gates (do not implement here): 061 (report fusion) consumes `LabelRadiomics`;
062/064 (heuristics/rules) and 065 (CLI + config knob) build on top.

## Decisions & Trade-offs

- **Alignment guard called twice (defense-in-depth), not just transitively.**
  `compute_radiomics_features` calls `intensity._check_alignment` directly
  before enumerating labels (mirroring item 059's `compute_intensity_features`
  pattern), in addition to the guard firing transitively inside each
  `compute_label_radiomics` -> `compute_label_intensity` call. This matters
  for the degenerate case of a mismatched-grid pair with **no** overlapping
  non-zero labels in the (mismatched) segmentation array — without the
  direct call, the label loop could be empty and the function would return
  `{}` instead of raising. Cheap and keeps behaviour identical to item 059's
  convenience-map guard.
- **PyRadiomics extractor settings.** `binWidth=25.0` (fixed, no auto
  `binCount`), `interpolator=None`/`resampledPixelSpacing=None` (no
  resampling — operate on the native grid), `label=1` against a
  single-label-restricted uint8 mask (rather than passing the original
  multi-label segmentation with `label=<value>`), and `normalize=False`.
  Only the `glcm` and `shape` feature classes are enabled (first-order is
  deliberately left disabled on the PyRadiomics side since item 059 already
  owns `first_order`). These are declared as module constants
  (`_PYRADIOMICS_BIN_WIDTH`, `_PYRADIOMICS_ENABLED_FEATURE_CLASSES`) per the
  spec's pin so present-path output is reproducible (AC14).
- **SimpleITK image construction.** NumPy arrays are `(x, y, z)`-ordered
  (NiBabel convention); `SimpleITK.GetImageFromArray` expects `(z, y, x)`, so
  arrays are transposed accordingly before wrapping, with `SetSpacing` set
  from `scan_img.header.get_zooms()[:3]` (matching the `(x, y, z)` spacing
  order SimpleITK expects for `SetSpacing`). This could not be executed in
  this dev environment (PyRadiomics/SimpleITK absent) and is implemented per
  the documented PyRadiomics/SimpleITK API surface for inspection; the
  present-path tests (AC12-14) will validate it once PyRadiomics is
  installed and exercised in an environment that has it.
- **`extended` key filtering.** PyRadiomics' `extractor.execute(...)` result
  dict includes `diagnostics_*` metadata entries (image hashes, timings,
  etc.) alongside the numeric feature values; these are dropped, and any
  non-numeric or non-finite values are also dropped, so `extended` is
  guaranteed to satisfy AC12's "non-empty `Dict[str, float]`, every value a
  finite float" contract.
- **`_check_alignment` reuse.** Imported directly from
  `segqc.features.intensity` (a private module-level function, not in that
  module's `__all__`) rather than re-implemented, per the spec's explicit
  "Alignment guard reuse" pin allowing either approach.
