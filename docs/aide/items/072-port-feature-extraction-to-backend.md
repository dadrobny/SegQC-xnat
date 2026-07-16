# Item 072 — Port geometric/topological feature extraction to the backend abstraction

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 10 — Portable Compute: GPU Acceleration Path
> **Queue:** [`../queue/queue-009.md`](../queue/queue-009.md) · Item 072
> **Objectives:** G6 (Portable execution — identical results CPU-only; optional GPU acceleration path)
> **Suggested branch:** `aide/072-port-feature-extraction-to-backend`

---

## Description

Route the Stage-2/3 geometric/topological feature-extraction hot paths through
item 071's `segqc.backend` abstraction so their array/ndimage operations run on
CuPy when a GPU backend is selected and on NumPy/SciPy otherwise — while keeping
the **default CPU path numerically byte-identical** to today's behaviour.

**In scope — the six Stage-2/3 feature modules and their public compute
functions:**

| Module (`src/segqc/features/…`) | Public entry point(s) that gain `backend` | Heavy numeric ops today |
|---|---|---|
| `geometry.py` | `compute_label_geometry` | `np.asanyarray`, `argwhere`, `unique`, `min`/`max` |
| `components.py` | `compute_components` | **`scipy.ndimage.label`**, `bincount`, `sort`, `unique` |
| `centroids.py` | `compute_centroid`, `compute_edt_centroids` | `argwhere`, `mean`, `argmax`, `unravel_index`, **`distance_transform_edt`**, **`gaussian_filter`** |
| `fragmentation.py` | `compute_fragmentation_index` | (delegates to `compute_components`) |
| `spline.py` | `fit_centroid_spline`, `evaluate_spline` | `scipy.interpolate.splprep` / `splev` |
| `spline_offset.py` | `compute_spline_offsets` | `scipy.optimize.minimize_scalar`, `splev` |

**What it delivers:**

- A `backend: Optional[Backend] = None` keyword parameter on every public compute
  function above. When `None` (the default) the function resolves a backend via
  `segqc.backend.get_backend()` (auto-detect, honouring `SEGQC_BACKEND`); when a
  `Backend` is supplied it is used directly. Backend threading is transitive:
  `compute_fragmentation_index` forwards its backend to `compute_components`;
  `compute_spline_offsets` forwards to `evaluate_spline`.
- Dense array ops (`argwhere`, `unique`, `bincount`, `sort`, `mean`, `argmax`,
  `unravel_index`, comparisons/reductions) routed through `Backend.xp` (`numpy`
  for CPU, `cupy` for GPU), with explicit host marshalling (`.item()` /
  `numpy.asarray`) at the boundaries where Python scalars, tuples, and lists are
  built for the frozen result dataclasses.
- The three `scipy.ndimage` calls (`label`, `distance_transform_edt`,
  `gaussian_filter`) routed through a **new `Backend.ndimage` accessor** added to
  the item-071 `Backend` handle (CPU → `scipy.ndimage`, GPU →
  `cupyx.scipy.ndimage`, which ships inside the `cupy` package — no `cucim`).
- A **documented, deliberate CPU fallback for the spline steps**
  (`splprep` / `splev` in `spline.py`, `minimize_scalar` in `spline_offset.py`):
  these operate on tiny centroid arrays (≤ ~25 points) and have no reliable CuPy
  equivalent, so even under an explicit GPU backend they marshal their inputs to
  host NumPy, run on SciPy/CPU, and return host results — recorded as a known
  partial-GPU-coverage limitation.

**What it is NOT (scope fence):**

- **No CLI or pipeline wiring.** `pipeline.py` keeps calling these functions with
  no `backend` argument (they auto-resolve → CPU on this host, unchanged); the
  `segqc run --backend …` flag and pipeline-level backend threading are **item
  075**. This item only adds the parameter and the internal routing.
- **No Stage-8 intensity/radiomics porting** (`features/intensity.py`,
  `features/radiomics.py`) — radiomics already has its own optional-dependency
  path (item 060); Stage 10's roadmap entry names only the Stage-2/3
  geometric/topological core.
- **No other feature modules** (`overlap.py`, `orientation.py`,
  `neighbourhood.py`, `consistency.py`, `relationships.py`,
  `sagittal_projection.py`) — not named by the queue item and out of scope here.
- **No numeric-result change on the CPU path**, no new heuristic/verdict/schema,
  no CPU-vs-GPU equivalence *suite* (that is item 073 — this item ships only a
  single GPU-gated spot-check).

## Acceptance Criteria

- [ ] **AC1: CPU-path regression guard.** The entire pre-existing Stage-2/3
  feature test suite — `tests/test_011_geometry.py`,
  `tests/test_012_connected_components.py`, `tests/test_013_centroids.py`,
  `tests/test_017_centroid_spline_fit.py`,
  `tests/test_018_per_vertebra_spline_offset.py`,
  `tests/test_023_edt_centroid_depth.py`, `tests/test_025_fragmentation_index.py`
  (and the golden-file / pipeline determinism tests) — passes **unchanged** (no
  edits to those test files) after the port. Not a single CPU-path numeric result
  changes.
- [ ] **AC2: `backend` keyword present on every ported function.** Each of
  `compute_label_geometry`, `compute_components`, `compute_centroid`,
  `compute_edt_centroids`, `compute_fragmentation_index`, `fit_centroid_spline`,
  `evaluate_spline`, and `compute_spline_offsets` accepts a keyword parameter
  named `backend` whose default is `None` (verifiable via `inspect.signature`).
- [ ] **AC3: `None` default auto-resolves via `get_backend()`.** Calling a ported
  function with `backend=None` (the default) invokes
  `segqc.backend.get_backend()` to obtain the backend — verifiable by
  monkeypatching `get_backend` to return a sentinel CPU `Backend` and asserting
  it is consulted exactly when no explicit backend is passed.
- [ ] **AC4: Explicit CPU backend equals the default on this host.** For a
  representative fixture, each ported function called with an explicit
  `get_backend(override="cpu")` returns a result **equal** (`==` on the frozen
  dataclass / `np.array_equal` on arrays) to the same call with `backend=None`,
  on this CuPy-absent host.
- [ ] **AC5: `Backend.ndimage` accessor exists (CPU).** The item-071 `Backend`
  handle, for `override="cpu"`, exposes an `ndimage` accessor that **is** (or
  wraps) `scipy.ndimage`, through which `label`, `distance_transform_edt`, and
  `gaussian_filter` are all callable.
- [ ] **AC6: `compute_components` labels via `Backend.ndimage`.**
  `compute_components` performs its connected-components labelling through
  `backend.ndimage.label` (not a hard-coded `scipy.ndimage` import at the call
  site) — verifiable by passing a `Backend` whose `ndimage.label` is a spy and
  asserting it is invoked, with the 6-connectivity result unchanged.
- [ ] **AC7: `compute_edt_centroids` routes EDT + smoothing via
  `Backend.ndimage`.** `compute_edt_centroids` calls `distance_transform_edt` and
  `gaussian_filter` through `backend.ndimage` — verifiable by spying on those two
  accessor attributes and asserting both are invoked, with the returned
  `CentroidFeatures` unchanged versus the pre-port CPU values.
- [ ] **AC8: Spline steps run on CPU even under an explicit GPU backend.** With a
  **mocked GPU** `Backend` (fake `cupy` injected, `is_gpu is True`),
  `fit_centroid_spline`, `evaluate_spline`, and `compute_spline_offsets` execute
  `splprep`/`splev`/`minimize_scalar` on **SciPy/CPU** (they do not attempt a
  CuPy spline call), and return correct host (`numpy`) results equal to the
  pure-CPU-backend result — the documented deliberate CPU fallback.
- [ ] **AC9: Spline CPU fallback is documented as a known limitation.** The
  `spline.py` and `spline_offset.py` module docstrings state that the spline
  fit/evaluate/optimise steps deliberately run on CPU/SciPy regardless of the
  selected backend (small-array partial-GPU-coverage limitation) — a grep-able,
  asserted docstring statement.
- [ ] **AC10: `backend` threads transitively through wrappers.**
  `compute_fragmentation_index(..., backend=b)` forwards `b` to
  `compute_components`, and `compute_spline_offsets(..., backend=b)` forwards `b`
  to `evaluate_spline` — verifiable by spying on the delegate and asserting it
  received the same backend object.
- [ ] **AC11: Read-only and deterministic under the CPU backend.** Each ported
  function called twice with an explicit CPU backend on the same fixture returns
  equal results, and the input `Nifti1Image` / centroid sequence is not mutated
  (array bytes / sequence identity unchanged) — the pre-port immutability and
  determinism contracts still hold.
- [ ] **AC12: GPU-gated equivalence spot-check skips cleanly without CuPy.** A
  test that compares a representative feature (per-label `physical_volume_mm3`
  from `compute_label_geometry` and one centroid variant from
  `compute_edt_centroids`) between the CPU backend and an explicit GPU backend
  **skips** (via `pytest.importorskip("cupy")` / a CuPy-availability guard) — never
  errors, never vacuously passes — when CuPy is absent (the state of this host).
- [ ] **AC13: GPU-gated equivalence spot-check agrees within tolerance when CuPy
  is present.** When CuPy *is* importable, that spot-check computes the
  representative feature under both backends on a small fixture and asserts they
  agree within a **documented numeric tolerance** (relative/absolute tolerance
  stated in the test), acknowledging NumPy-vs-CuPy floating-point drift.
- [ ] **AC14: No `cucim` dependency introduced.** This item adds **no** `cucim`
  requirement anywhere: `pyproject.toml`'s `[project].dependencies` still contains
  neither `cupy` nor `cucim`, and the `gpu` optional-dependencies extra still lists
  `cupy` **without** `cucim` (the ported ndimage ops use `cupyx.scipy.ndimage`,
  which ships inside `cupy`).

## Assumptions  <!-- MANDATORY -->

- **A1 — Default backend resolution is `None → get_backend()` (auto-resolve),
  Option A [human-confirmed].** A `backend=None` argument means "resolve now via
  `segqc.backend.get_backend()`", which honours `SEGQC_BACKEND` / auto-detect. On
  this CPU-only dev/CI host (CuPy absent) this resolves to CPU and every result is
  byte-identical to today (AC1/AC4). On a real GPU host with `SEGQC_BACKEND`
  unset, feature extraction would auto-select GPU by default when available; any
  resulting float-tolerance drift is governed by **item 073's** tolerance suite,
  not this item's regression guard (which only needs to hold on this CPU-only
  host).
- **A2 — Spline steps deliberately fall back to CPU [human-confirmed].** The
  centroid arrays reaching `splprep`/`splev`/`minimize_scalar` are tiny
  (≤ ~25 points); these are moved to host NumPy, run on SciPy/CPU, and their
  results marshalled back — even under an explicit GPU backend. This is a
  documented, intentional known **partial-GPU-coverage** limitation (AC8/AC9),
  not a defect. `label` / `distance_transform_edt` / `gaussian_filter` still route
  through `Backend.ndimage` (GPU: `cupyx.scipy.ndimage`).
- **A3 — `cupyx.scipy.ndimage` ships inside `cupy`; NO `cucim` dependency.** The
  three ndimage ops this item ports live in `cupyx.scipy.ndimage`, a subpackage of
  the `cupy` package itself — so item 072 adds **no** `cucim` requirement to the
  `gpu` extra or anywhere (AC14). This **corrects** item 071's original
  Assumption A3, which stated item 072 would add `cucim` to the `gpu` extra. See
  Dependencies for how that correction was applied.
- **A4 — Item 071's `Backend` is extended here with `.ndimage`.** Item 071 (spec,
  not yet built) pins its `Backend` handle as extensible (its A3 "pinned extension
  point"). This item adds an `ndimage` accessor to that handle: for a CPU backend
  it yields `scipy.ndimage`; for a GPU backend it yields `cupyx.scipy.ndimage`
  (imported lazily, only on the GPU path). **Pinned interface consumed from 071:**
  `Backend.xp` (array module), `Backend.name`, `Backend.is_gpu`, and
  `get_backend(override=None) -> Backend` / `backend_name()`. If the item-071
  builder ships a differently-shaped `Backend` (e.g. a non-extensible frozen
  dataclass, or a different accessor mechanism), the item-072 builder hands back
  to reconcile.
- **A5 — GPU behaviour is mockable without a real GPU.** Every GPU-selection and
  spline-fallback assertion (AC8) is exercised by injecting a fake `cupy` /
  fake-GPU `Backend` via `monkeypatch` / `sys.modules`, mirroring item 071's test
  approach; only the *numeric-equivalence* spot-check (AC13) needs a genuine CuPy
  install and is `importorskip`-gated (AC12). This host has no CuPy, so AC13 is
  expected to skip here — by design, per the queue's local-testability note.
- **A6 — Signature-compatible, keyword-only addition.** `backend` is added as a
  keyword parameter with a `None` default positioned so existing positional
  callers (notably `pipeline.py`, which calls these functions with no `backend`
  argument) are untouched (AC1). Recommended: keyword-only (after a `*`) where the
  current signature allows it.
- **A7 — Representative fixture reuse.** The regression and spot-check tests reuse
  existing Stage-0/Stage-2/3 fixtures (the tiny synthetic label maps already used
  by `tests/test_011*`/`test_013*`/`test_023*`); no new binary fixtures are added.

## Implementation Steps

Code path in `src/segqc` (see `aide.toml` → `project.source_dir`).

1. **Extend the `Backend` handle (`src/segqc/backend.py`).** Add an `ndimage`
   accessor to item 071's `Backend` (a cached property or attribute): return
   `scipy.ndimage` when `not is_gpu`; return `cupyx.scipy.ndimage` (lazy import,
   only when `is_gpu`) otherwise. Update `Backend`'s docstring/`__all__` as needed.
   Do **not** add `cucim` to `pyproject.toml`.
2. **`geometry.py`.** Add `backend=None` (keyword) to `compute_label_geometry`;
   resolve `backend = backend or get_backend()`. Move the label mask/coords work
   onto `backend.xp` (`xp.asarray(data)`, `xp.argwhere`, `.min()`/`.max()`,
   `xp.unique`) and marshal to Python `int`/`float`/`BBox` via `.item()` /
   `int(...)` at the result boundary. CPU path (`xp is numpy`) stays byte-identical.
3. **`components.py`.** Add `backend=None`; resolve. Replace the local
   `from scipy.ndimage import label` with `backend.ndimage.label(mask)`; route
   `bincount`/`sort`/`unique` through `backend.xp`; marshal component sizes/volumes
   to host `int`/`float` lists. Preserve the 6-connectivity default structure.
4. **`centroids.py`.** Add `backend=None` to **both** `compute_centroid` and
   `compute_edt_centroids`; resolve. In `compute_edt_centroids`, replace the
   module-level `distance_transform_edt`/`gaussian_filter` with
   `backend.ndimage.distance_transform_edt` / `backend.ndimage.gaussian_filter`
   (thread `backend` into `_compute_edt`); route `argwhere`/`mean`/`argmax`/
   `unravel_index` through `backend.xp`; host-marshal the centroid tuples/depths.
5. **`fragmentation.py`.** Add `backend=None` to `compute_fragmentation_index` and
   forward it to `compute_components(seg_img, label, config, backend=backend)`.
6. **`spline.py`.** Add `backend=None` to `fit_centroid_spline` and
   `evaluate_spline` for signature uniformity, but **keep the numeric work on
   CPU**: ensure the `x/y/z` coordinate arrays are host `numpy` (marshalling from
   `backend.xp` if a caller ever supplies device arrays), run `splprep`/`splev` on
   SciPy, and return host `numpy` arrays. Document the CPU-fallback in the module
   docstring (AC9).
7. **`spline_offset.py`.** Add `backend=None` to `compute_spline_offsets`; forward
   it to `evaluate_spline`; keep `minimize_scalar` and the `_find_closest_u`
   scan on CPU/SciPy with host arrays. Document the CPU-fallback in the module
   docstring (AC9).
8. **No pipeline/CLI edits.** Leave `pipeline.py` and `cli.py` untouched — item
   075 wires the flag and pipeline-level backend threading.
9. **`pyproject.toml`.** Verify unchanged: no `cucim`, no new core dependency; the
   `gpu` extra still lists only `cupy` (AC14).

## Testing Strategy

New test module: **`tests/test_072_backend_feature_port.py`** (mirrors the
`test_0NN_*.py` convention). GPU behaviour is exercised by **mocking** a GPU
`Backend` / injecting a fake `cupy` via `monkeypatch` / `sys.modules` (item-071
pattern); the one genuine-CuPy equivalence check is `importorskip`-gated. One
focused test per AC:

- **AC1 (regression guard)** — do **not** modify the existing Stage-2/3 test
  files; the validator runs the full suite and confirms they pass unchanged. A
  thin meta-assertion may additionally re-run a representative existing fixture
  through a ported function and compare to a hard-coded pre-port value.
- **AC2** — `inspect.signature(fn)` for all eight functions asserts a `backend`
  parameter defaulting to `None`.
- **AC3** — monkeypatch `segqc.backend.get_backend` to a spy returning a CPU
  `Backend`; call each function with `backend=None` and assert the spy was
  consulted; call with an explicit backend and assert it was **not**.
- **AC4** — for a small fixture, assert `fn(..., backend=None) == fn(...,
  backend=get_backend(override="cpu"))` (dataclass `==` / `np.array_equal`).
- **AC5** — `get_backend(override="cpu").ndimage` exposes callable `label`,
  `distance_transform_edt`, `gaussian_filter` (identity/wrap of `scipy.ndimage`).
- **AC6** — pass a `Backend` whose `ndimage.label` is a `unittest.mock` spy
  wrapping the real function; assert it is called and the `ComponentsInfo` matches
  the direct-`scipy` result.
- **AC7** — spy on `backend.ndimage.distance_transform_edt` and
  `.gaussian_filter`; assert both invoked and `CentroidFeatures` equals the
  pre-port CPU value.
- **AC8** — build a fake-GPU `Backend` (fake `cupy` module, `is_gpu=True`,
  `ndimage` = a fake); call `fit_centroid_spline`/`evaluate_spline`/
  `compute_spline_offsets`; assert results are host `numpy`, equal the CPU-backend
  result, and that the fake cupy's spline entry points were **never** touched.
- **AC9** — assert the CPU-fallback sentence is present in `spline.py` and
  `spline_offset.py` module docstrings.
- **AC10** — spy on `compute_components` / `evaluate_spline`; assert the wrapper
  forwarded the same `backend` object.
- **AC11** — call twice with a CPU backend → equal; capture input array bytes /
  sequence `id` before and after → unchanged (immutability + determinism).
- **AC12** — the equivalence spot-check test is decorated/guarded with
  `pytest.importorskip("cupy")` (or an explicit `cupy_available()` skip); a
  structural assertion proves the skip is genuine (marker present) on this host,
  not a vacuous pass.
- **AC13** — inside the guarded test, compute `physical_volume_mm3` and a centroid
  variant under CPU and GPU backends; assert agreement within a documented
  `rtol`/`atol` (state the values in the test).
- **AC14** — parse `pyproject.toml` (tomllib) and assert no `cucim` anywhere, no
  new core dependency, `gpu` extra lists `cupy` only.

**Adversarial / edge cases:** empty/degenerate label (absent label still raises
`ValueError` unchanged through the backend path); 2-centroid spline (degree
clamp) under a GPU backend still CPU-falls-back correctly; `SEGQC_BACKEND=cpu`
env set while calling with `backend=None` resolves to CPU; a device-array input to
a spline function is marshalled to host without error; confirm the fake-GPU
`Backend` genuinely differs from CPU (its `xp`/`ndimage` are the fakes) so AC8 is
not vacuous.

## Dependencies

- **Item 071 — GPU/CPU backend abstraction (specced, NOT yet built; `📋` in
  `progress.md`).** Provides `segqc.backend`: `get_backend(override=None) ->
  Backend`, `backend_name()`, and the `Backend` handle (`.xp`, `.name`,
  `.is_gpu`) this item threads through and extends with `.ndimage`. Must land
  (✅/🚧) before item 072 is built. The pinned interfaces consumed are in
  Assumption A4; if 071's realised `Backend` diverges, the builder hands back.
- **cucim-assumption correction to item 071.** Item 071 is still an unbuilt spec,
  so its **Assumption A3** was amended on this branch to remove the incorrect
  claim that item 072 adds `cucim` to the `gpu` extra, replacing it with the
  corrected understanding: the three ported ndimage ops live in
  `cupyx.scipy.ndimage` (inside `cupy`), so **no `cucim` dependency is needed**.
  (Had item 071 already been merged, this file would instead flag the discrepancy
  for the 071 builder to reconcile — but it has not, so the spec was corrected
  directly.) See item 072 Assumption A3 and AC14.
- **Stage-level:** Stages 2 & 3 ✅ (the feature modules being ported) and Stage 7
  ✅ (calibrated pipeline) — the CPU behaviour this item must preserve.
- **Downstream (informational):** item 073 (equivalence suite) needs the ported,
  backend-aware compute path; item 075 (CLI/pipeline integration) wires the
  `--backend` flag through to these functions.

## Decisions & Trade-offs

- **`Backend.ndimage` implemented as a plain dataclass field, not a
  property/cached-property.** `Backend` is a frozen dataclass with only
  simple attributes (`name`, `is_gpu`, `xp`); adding `ndimage: Any` as a
  fourth field, populated once in `get_backend()` (`scipy.ndimage` for CPU,
  lazily-imported `cupyx.scipy.ndimage` for GPU) is the simplest option
  consistent with the existing shape, keeps `Backend` fully duck-typeable
  (the test suite's fake `Backend`s are `types.SimpleNamespace(name=...,
  is_gpu=..., xp=..., ndimage=...)`), and needs no extra caching logic since
  `get_backend()` already resolves once per call.
- **`get_backend` is always called through the module object
  (`_backend_mod.get_backend()`), never via a `from segqc.backend import
  get_backend` bound name.** The test suite's AC3 spy monkeypatches
  `segqc.backend.get_backend` (the module attribute) rather than patching
  each feature module's local name. A `from ... import get_backend`
  statement binds a private reference in the importing module's namespace at
  import time, which a later `monkeypatch.setattr(backend_mod,
  "get_backend", spy)` would not reach. Every ported function therefore does
  `import segqc.backend as _backend_mod` and calls
  `_backend_mod.get_backend()` at the call site, so the attribute lookup
  happens fresh each call and honours the patched spy. `evaluate_spline`
  (imported directly by name into `spline_offset.py`, per the pre-existing
  style) is the one exception, and deliberately so: AC10's spy patches
  `spline_offset_mod.evaluate_spline` itself, which works precisely because
  it *is* a plain "import the name into this module's globals" binding —
  consistent with, not contradicting, the ``_backend_mod`` rule above (two
  different attributes are being spied on, in two different modules, so two
  different import styles are each correct for their own case).
- **Spline steps (`spline.py`, `spline_offset.py`) still resolve
  `backend = backend or _backend_mod.get_backend()` even though the
  resolved value's `xp`/`ndimage` are never used for computation.** This
  keeps AC3 (backend=None auto-resolves; explicit backend does not consult
  `get_backend()`) uniform across all eight ported functions, at the cost of
  one now-otherwise-unused local variable in `fit_centroid_spline` — an
  intentional, documented trade-off favouring interface uniformity over a
  minor unused-value dead-store.
- **`evaluate_spline`'s `u_values` marshalling favours a duck-typed
  `.get()` transfer, falling back to `np.asarray`.** This mirrors the
  CuPy-array `.get()` convention documented in item 071 without adding a
  CuPy import, and satisfies the adversarial "device-array input" test
  (`_FakeDeviceArray`, which exposes both `.get()` and `__array__`) without
  requiring CuPy to be installed.
- **Result-boundary marshalling in `geometry.py`/`components.py`/
  `centroids.py` re-reads `np.asanyarray(seg_img.dataobj)` (host NumPy) for
  the `ValueError`'s "available labels" listing**, rather than routing that
  diagnostic-only path through `backend.xp`. It is off the hot path (raised
  only when the requested label is absent) and keeps that error message
  byte-identical to the pre-port behaviour regardless of backend.
- No deviations from the spec's Implementation Steps; `pipeline.py`,
  `cli.py`, and `pyproject.toml` are unchanged, confirming AC14 and the
  scope fence (items 075 / 073 stay out of scope here).
