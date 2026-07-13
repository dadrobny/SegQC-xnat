# Item 071 — GPU/CPU backend abstraction: runtime selection, auto-detect, explicit override

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 10 — Portable Compute: GPU Acceleration Path
> **Queue:** [`../queue/queue-009.md`](../queue/queue-009.md) · Item 071
> **Objectives:** G6 (Portable execution — identical results CPU-only; optional GPU acceleration path)
> **Suggested branch:** `aide/071-gpu-cpu-backend-abstraction`

---

## Description

Add a new `segqc.backend` module: a uniform array/compute-backend **selection
layer** that auto-detects CuPy at runtime, falls back to NumPy transparently
when CuPy is absent, and honours an explicit override so a user or CI can force
CPU even on a GPU host, or request GPU explicitly. This is the shared foundation
every other Stage-10 item builds on.

**What it delivers:**

- A capability probe (`cupy_available()`) that reports, at call time, whether
  the `cupy` library is importable — never raising, never requiring a GPU.
- A resolution API that turns a requested choice (`cpu` / `gpu` / `auto`) plus
  the `SEGQC_BACKEND` environment variable into a concrete backend, with a clear
  precedence order (explicit argument > env var > default `auto`), and `auto`
  resolving to GPU only when CuPy is genuinely importable.
- A small `Backend` handle exposing an `xp`-style array-module attribute
  (`numpy` for CPU, `cupy` for GPU) plus name/introspection, ready for item 072
  to route feature-extraction array ops through.
- A typed, actionable error (`SegQCBackendError`) when GPU is explicitly forced
  but CuPy is unavailable — a clean message, **never** a bare `ImportError`
  traceback.
- A `gpu` optional-dependencies extra in `pyproject.toml` (mirroring the item-060
  `radiomics` extra), keeping `cupy`/`cucim` **out** of the core `dependencies`
  so the tool installs and runs fully CPU-only with zero required GPU deps.

**What it is NOT (scope fence):**

- **No feature-extraction code is migrated** — the Stage-2/3 hot paths
  (`features/geometry.py`, `components.py`, `centroids.py`, `spline.py`, …) are
  untouched here; routing them through this abstraction is item **072**.
- **No CLI surface change.** The `segqc run --backend …` flag is **item 075's**
  job; this item stops at the `SEGQC_BACKEND` env var + the programmatic override
  argument that the flag will later feed (queue item 075 explicitly names "the
  item-071 environment-variable equivalent").
- **No real-GPU execution.** Selection *logic* is the deliverable; whether a
  CuPy kernel actually runs and matches CPU bit-for-bit is items 073/075's
  GPU-gated concern. "Available" here means "`cupy` is importable".
- **No pipeline/report/verdict/schema changes.**

## Acceptance Criteria

- [ ] **AC1: Module imports GPU-free.** `import segqc.backend` succeeds on a host
  where `cupy` is not installed — no `ImportError`, and importing the module does
  not require, import at module scope, or otherwise depend on `cupy`.
- [ ] **AC2: Capability probe reports absent.** With `cupy` mocked as absent
  (e.g. `sys.modules["cupy"] = None`), `cupy_available()` returns `False` and
  does not raise.
- [ ] **AC3: Capability probe reports present.** With `cupy` mocked as importable
  (a stub module injected into `sys.modules`), `cupy_available()` returns `True`.
- [ ] **AC4: Auto-detect falls back to CPU.** With no explicit override (argument
  omitted / `None`) and `SEGQC_BACKEND` unset, and `cupy` absent,
  `backend_name()` returns `"cpu"`.
- [ ] **AC5: Auto-detect selects GPU when CuPy present.** With no explicit
  override and `SEGQC_BACKEND` unset, and `cupy` mocked present, `backend_name()`
  returns `"gpu"`.
- [ ] **AC6: Env override forces CPU over an available GPU.** With
  `SEGQC_BACKEND=cpu` and `cupy` mocked present, `backend_name()` returns
  `"cpu"` (an explicit CPU request always wins, even when a GPU is available).
- [ ] **AC7: Forcing GPU without CuPy raises a clear, non-traceback error.** With
  `SEGQC_BACKEND=gpu` (or `override="gpu"`) and `cupy` absent, `get_backend()`
  (and `backend_name()`) raises `SegQCBackendError` — not a bare `ImportError` —
  whose message states the problem and the remediation (install the `gpu` extra
  / a CuPy build).
- [ ] **AC8: Explicit argument beats the env var.** With `SEGQC_BACKEND=gpu`,
  `cupy` mocked present, and an explicit `override="cpu"`, `get_backend` /
  `backend_name` resolves to `"cpu"` (the precedence the item-075 CLI flag relies
  on: explicit argument > env var > `auto`).
- [ ] **AC9: Invalid override token is rejected.** An unrecognised value (e.g.
  `SEGQC_BACKEND=turbo` or `override="turbo"`) raises `SegQCBackendError` whose
  message names the accepted values (`cpu`, `gpu`, `auto`) — not a traceback.
- [ ] **AC10: CPU Backend handle shape.** `get_backend(override="cpu")` returns a
  `Backend` with `.name == "cpu"`, `.is_gpu is False`, and `.xp` bound to the
  `numpy` module.
- [ ] **AC11: GPU Backend handle shape.** With `cupy` mocked present,
  `get_backend(override="gpu")` returns a `Backend` with `.name == "gpu"`,
  `.is_gpu is True`, and `.xp` bound to the (mocked) `cupy` module.
- [ ] **AC12: Token normalisation.** A token with surrounding whitespace and
  mixed case (e.g. `SEGQC_BACKEND=" GPU "`) resolves identically to the canonical
  `gpu`; an empty/whitespace-only env var is treated as unset (→ `auto`).
- [ ] **AC13: Probe reflects current import state (not import-time cache).**
  `cupy_available()` re-probes each call: toggling the `sys.modules` `cupy`
  sentinel between two calls (absent → present, or present → absent) changes the
  returned value within a single process — it is NOT a boolean frozen at module
  load.
- [ ] **AC14: No GPU library in core dependencies.** `pyproject.toml`'s
  `[project].dependencies` list contains neither `cupy` nor `cucim`.
- [ ] **AC15: Optional `gpu` extra present.** `pyproject.toml`'s
  `[project.optional-dependencies]` defines a `gpu` extra whose requirement list
  includes `cupy`.

## Assumptions  <!-- MANDATORY -->

- **A1 — CLI flag is item 075, not here.** Item 071 delivers only the
  `SEGQC_BACKEND` environment variable plus the programmatic `override` argument
  on `get_backend`/`backend_name`; the `segqc run --backend cpu|gpu|auto` flag is
  item **075**'s integration work (queue item 075 says "or the item-071
  environment-variable equivalent"). **Pinned interface for 075:** it calls
  `get_backend(override=<flag value or None>)`; resolution precedence is explicit
  argument (the flag) > `SEGQC_BACKEND` env var > default `auto`. If 075 needs a
  different seam it hands back.
- **A2 — "GPU available" ≡ "`cupy` importable".** Auto-detect keys purely on
  whether `import cupy` succeeds; it does **not** additionally query for a live
  CUDA device (`cupy.cuda.runtime.getDeviceCount`). A genuine device/execution
  check is deferred to items 073/075's GPU-gated tests. This keeps 071 fully
  unit-testable on a GPU-less host by mocking the import alone.
- **A3 — cuCIM deferred to 072; `Backend` extension point pinned.** The `gpu`
  extra ships `cupy` now; `cucim` (Linux/CUDA-only, heavier install friction) is
  added to the same extra by item **072**, when the scikit-image-equivalent ops
  are actually ported. The `Backend` handle exposes only `.xp` (array module),
  `.name`, and `.is_gpu` in this item. **Pinned extension point:** item 072 may
  add scipy.ndimage / scikit-image-equivalent handles (e.g.
  `cupyx.scipy.ndimage`, `cucim.skimage`) to `Backend` when it needs them;
  nothing in 071 forecloses that.
- **A4 — Dynamic probe, by design.** `cupy_available()` performs a guarded
  `import cupy` **inside the function** on each call (honouring `sys.modules`),
  rather than caching a boolean at module import time (contrast the item-060
  `pyradiomics_available()` cache). This is deliberate: it is what makes the
  selection logic unit-testable on a GPU-less host via `sys.modules`
  injection/removal (AC13). A `sys.modules["cupy"] = None` sentinel makes the
  guarded import raise `ImportError`, modelling "absent".
- **A5 — Error type mirrors existing conventions.** A new
  `SegQCBackendError(Exception)` lives in `segqc.backend`, matching the
  `SegQCConfigError` / `SegQCInputError` / `ReferenceArtifactError` pattern; the
  item-075 CLI handler will catch it and print `Error: {exc}` (the established
  `_handle_run` convention). "Non-traceback error" means raising this typed,
  actionable exception instead of letting a raw `ImportError` bubble.
- **A6 — Token vocabulary.** Accepted backend tokens are `cpu`, `gpu`, `auto`,
  matched case-insensitively after `.strip().lower()`; an unset, empty, or
  whitespace-only env var is treated as `auto`.
- **A7 — Extra naming/structure mirrors item 060.** The extra is named `gpu`
  under `[project.optional-dependencies]`, structured and commented like the
  `radiomics` extra. The `cupy` requirement uses a loose lower bound
  (e.g. `cupy>=12`) with a comment noting that the user picks the CUDA-matched
  wheel (`cupy-cuda11x` / `cupy-cuda12x`) or a source build — the extra just
  documents the dependency, it is never installed by default.

## Implementation Steps

Code path in `src/segqc` (see `aide.toml` → `project.source_dir`).

1. **Create `src/segqc/backend.py`** with a module docstring explaining the
   CPU-default / optional-GPU contract, the dynamic-probe rationale (A4), and the
   scope fence (no feature code here).
2. **Constants & error.** Define `BACKEND_CPU = "cpu"`, `BACKEND_GPU = "gpu"`,
   `BACKEND_AUTO = "auto"`, `ENV_VAR = "SEGQC_BACKEND"`, the valid-token set, and
   `class SegQCBackendError(Exception)` with a docstring.
3. **`cupy_available() -> bool`.** Guarded `try: import cupy` (or
   `importlib.import_module("cupy")`) **inside the function**, returning
   `True`/`False`, never raising (AC2, AC3, AC13). Do not cache at module scope.
4. **`Backend` handle.** A small `@dataclass(frozen=True)` (or equivalent
   read-only object) with fields `name: str`, `is_gpu: bool`, and `xp` (the array
   module). Keep it minimal and extensible (A3).
5. **`resolve_backend_choice(override: Optional[str] = None) -> str`.** Normalise
   the effective token: use `override` when non-`None`/non-empty, else
   `os.environ.get(ENV_VAR)`, else `auto`; `.strip().lower()`; empty → `auto`
   (AC12). Reject unknown tokens with `SegQCBackendError` naming the valid values
   (AC9). Resolve `auto` → `gpu` if `cupy_available()` else `cpu` (AC4, AC5).
   If the resolved concrete choice is `gpu` but `not cupy_available()`, raise
   `SegQCBackendError` with an actionable message (AC7).
6. **`backend_name(override=None) -> str`.** Thin wrapper returning the concrete
   resolved name (`"cpu"`/`"gpu"`); propagates `SegQCBackendError` per AC7/AC9.
7. **`get_backend(override=None) -> Backend`.** Resolve via
   `resolve_backend_choice`; for `cpu` build `Backend("cpu", False, numpy)`; for
   `gpu` `import cupy` and build `Backend("gpu", True, cupy)` (AC10, AC11). The
   GPU import happens only on the GPU path.
8. **Export a tidy `__all__`** (`SegQCBackendError`, `Backend`,
   `cupy_available`, `get_backend`, `backend_name`, `resolve_backend_choice`, the
   `BACKEND_*`/`ENV_VAR` constants).
9. **`pyproject.toml`.** Add a `gpu` extra under
   `[project.optional-dependencies]` listing `cupy` (loose lower bound, commented
   per A7). Leave `[project].dependencies` untouched — verify neither `cupy` nor
   `cucim` appears there (AC14, AC15).
10. **No other files change.** Do not touch `cli.py`, `pipeline.py`, or any
    `features/*.py` — those are items 072/075.

## Testing Strategy

New test module: **`tests/test_071_backend.py`** (mirrors the `test_0NN_*.py`
convention). All GPU behaviour is exercised by **mocking `cupy`'s presence via
`sys.modules` / `monkeypatch`** — no real GPU, no real CuPy install. Recommended
helpers:

- A `fake_cupy` fixture that injects a stub module object into
  `sys.modules["cupy"]` (via `monkeypatch.setitem`) to model "present"; the test
  can then assert `Backend.xp is` that exact stub (AC11).
- An "absent" helper that sets `sys.modules["cupy"] = None` (so the guarded
  import raises `ImportError`) — robust even on a host that has CuPy installed.
- Always clear/set `SEGQC_BACKEND` with `monkeypatch.setenv`/`delenv` so tests
  are hermetic and order-independent.

One focused test per AC:

- **AC1** — import the module in a subprocess or plain `import segqc.backend`
  under the absent-CuPy condition; assert success.
- **AC2/AC3** — `cupy_available()` under absent / present mocks.
- **AC4/AC5** — `backend_name()` with env unset, under absent / present.
- **AC6** — `SEGQC_BACKEND=cpu` + present → `"cpu"`.
- **AC7** — `SEGQC_BACKEND=gpu` (and separately `override="gpu"`) + absent →
  `pytest.raises(SegQCBackendError)`; assert the message is non-empty and
  mentions CuPy / the `gpu` extra, and assert the raised type is **not** a bare
  `ImportError`.
- **AC8** — `SEGQC_BACKEND=gpu` + present + `override="cpu"` → `"cpu"`.
- **AC9** — invalid token via env and via argument → `SegQCBackendError` whose
  message contains `cpu`, `gpu`, `auto`.
- **AC10** — `get_backend(override="cpu")`: assert `.name`, `.is_gpu is False`,
  `.xp is numpy`.
- **AC11** — with `fake_cupy`: `get_backend(override="gpu")`: assert `.name`,
  `.is_gpu is True`, `.xp is fake_cupy`.
- **AC12** — `SEGQC_BACKEND=" GPU "` (present) → `"gpu"`; `SEGQC_BACKEND=""` /
  `"   "` (absent) → `"cpu"` (empty treated as `auto`).
- **AC13** — call `cupy_available()` with the sentinel absent, then inject the
  stub and call again; assert the two results differ (proves per-call probing).
- **AC14/AC15** — parse `pyproject.toml` (tomllib/`tomli`) and assert no
  `cupy`/`cucim` substring in `[project].dependencies`, and that
  `optional-dependencies.gpu` exists and contains a `cupy` requirement.

**Adversarial / edge cases to include:** empty and whitespace-only env var
(AC12); explicit `override="auto"` behaving like the default; both the env-var
path and the argument path for the invalid-token and force-GPU-absent cases;
determinism — repeated `get_backend()` calls under a fixed condition return the
same `.name` (no hidden global state beyond the live import status the probe
reads intentionally); and confirming the absent-model (`sys.modules["cupy"] =
None`) genuinely makes the guarded import raise so the test isn't vacuous.

## Dependencies

- **Item-level: None.** Item 071 is the first Stage-10 item and the foundation
  the rest build on; it depends on no prior *item*.
- **Stage-level:** Stage 7 ✅ (stable, calibrated pipeline) is Stage 10's only
  roadmap dependency and is already complete — context only, no code coupling
  here.
- **Downstream (informational):** items 072 (feature porting), 073 (equivalence
  suite), 074 (benchmark), and 075 (CLI integration) all consume this module's
  API — see the pinned interfaces in Assumptions A1/A3.

## Decisions & Trade-offs

To be updated during implementation.
