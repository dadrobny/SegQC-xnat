# Item 073 — CPU vs GPU verdict-equivalence test suite

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 10 — Portable Compute: GPU Acceleration Path
> **Queue:** [`../queue/queue-009.md`](../queue/queue-009.md) · Item 073
> **Objectives:** G6 (Portable execution — identical results CPU-only; optional GPU acceleration path)
> **Suggested branch:** `aide/073-cpu-gpu-verdict-equivalence-suite`

---

## Description

Add a **CPU-vs-GPU verdict-equivalence test suite** that runs representative
committed fixtures through the **full QC pipeline** (`segqc.pipeline.run_qc`)
under both the CPU backend and — when CuPy/a GPU is genuinely present — the GPU
backend, and asserts the two produce **identical QC verdicts** (categorical:
same overall verdict label, same fired rule IDs, same offending labels, same
severities) with **feature values agreeing within a documented numeric
tolerance** (acknowledging floating-point drift between NumPy/SciPy and CuPy
kernels). This is the direct test for the roadmap's *"CPU/GPU verdict-equivalence
tests pass"* Stage-10 acceptance clause.

The suite is designed for the central Stage-10 hardware constraint (this
dev/CI host has **no GPU and no CuPy**): its CPU-only assertions
(verdict determinism/reproducibility across repeated CPU runs, and the
auto-resolution → CPU path) **execute and pass unconditionally**, while every
GPU-*executing* assertion is gated behind a CuPy-availability check and **skips
cleanly** (never fails, never *vacuously* passes) when CuPy is absent — mirroring
items 060/069's radiomics/Docker-gated precedent. A structural test proves the
skip marker is genuine (a real `skipif`/`importorskip` gate that actually skips
on this host), so a green run here reflects real CPU coverage plus honestly-
skipped GPU coverage, not a hidden vacuous pass.

**How the full pipeline is driven under each backend (the key mechanism).**
Item 072 threads `backend: Optional[Backend] = None` through the Stage-2/3
feature functions such that `None` auto-resolves via `segqc.backend.get_backend()`
**at call time**, honouring the `SEGQC_BACKEND` environment variable (item 071).
`run_qc → extract_feature_record` calls those functions with **no** `backend`
argument, so setting `SEGQC_BACKEND=cpu` / `SEGQC_BACKEND=gpu` in the environment
(via `monkeypatch.setenv`) selects the backend for a whole `run_qc` call with
**no change to `pipeline.py` or `cli.py`** — the `segqc run --backend` flag is
item 075's job and is **not** required here. This is exactly the mechanism item
072's human-confirmed Assumption A1 describes ("On a real GPU host with
`SEGQC_BACKEND` unset, feature extraction would auto-select GPU by default … any
resulting float-tolerance drift is governed by **item 073's** tolerance suite").

**What it delivers:**

- A new test module `tests/test_073_verdict_equivalence.py` and a small,
  importable equivalence-comparison helper (verdict-signature extraction +
  feature-block numeric-tolerance comparison) used by the tests.
- Always-run CPU-only assertions: full-pipeline verdict **reproducibility**
  (repeated CPU runs agree bit-for-bit on verdict + findings), feature-block
  **determinism**, and confirmation that the auto-resolved default backend on
  this CuPy-absent host equals the explicit-CPU backend at the pipeline level.
- A **non-vacuity guard** proving the comparison helper genuinely distinguishes
  a differing verdict / differing feature block (so the equivalence assertions
  are not trivially true).
- A **genuine-skip structural proof** (mirroring item 069 AC2) that the GPU-gate
  marker is a real `skipif`/`importorskip` gate whose condition currently skips
  on this CuPy-absent host.
- GPU-gated assertions (skip cleanly here, run on a GPU host): full CPU-vs-GPU
  verdict identity and feature-value tolerance over the committed Stage-5 corpus
  and the Stage-0 tiny fixtures.

**What it is NOT (scope fence):**

- **No production-code change.** This item adds **tests only** (plus a
  test-side helper). It does not edit `pipeline.py`, `cli.py`, `backend.py`, any
  `features/*.py`, or `pyproject.toml`. Backend abstraction (071) and the
  feature port (072) are its prerequisites, not its work.
- **No CLI `--backend` flag.** Selecting the backend is done via the
  `SEGQC_BACKEND` env var (item 071's programmatic seam); wiring the CLI flag is
  **item 075**.
- **No new binary fixtures.** It reuses the committed Stage-5 corpus
  (`tests/corpus/`) and the Stage-0 synthetic builders (`tests/synthetic.py`) —
  no new `.nii.gz` is added.
- **No performance/timing assertions** (item 074) and **no Stage-10 acceptance
  closure / `progress.md` reconciliation** (item 075).
- **It does not port additional features to GPU.** It observes the equivalence
  of whatever item 072 ported; the un-ported case-level extractors
  (`relationships`, `overlap`, `orientation`, `curvature`, `consistency`) and
  the deliberately-CPU spline steps still run on CPU under a GPU backend — a
  documented partial-GPU-coverage reality (see Assumptions), not a defect this
  item fixes.

## Acceptance Criteria

_Each criterion is atomic, observable, and directly testable — one test per AC.
All live in `tests/test_073_verdict_equivalence.py`. ACs 1–6 run and pass
unconditionally on a GPU-less host; ACs 7–9 are CuPy-gated and skip cleanly when
CuPy is absent._

- [ ] **AC1: Suite module present and collectable GPU-free.** The module
  `tests/test_073_verdict_equivalence.py` exists, imports, and is collectable on
  a host where `cupy` is not installed — importing it does not require `cupy`,
  and none of its GPU-gated tests error at collection time.

- [ ] **AC2: CPU-backend full-pipeline verdict is reproducible.** Running the
  full pipeline (`run_qc`) under `SEGQC_BACKEND=cpu` **twice** over each committed
  Stage-5 corpus case yields an **identical verdict signature** each time — same
  `verdict.overall.label`, and the same set of findings compared as
  `(rule_id, sorted(offending labels), severity)`. (Determinism of the CPU path
  through the backend abstraction.)

- [ ] **AC3: CPU-backend feature block is byte-deterministic.** For a
  representative fixture (a multi-label corpus case), the canonical-JSON form of
  `extract_feature_record(seg_img, cfg)` under `SEGQC_BACKEND=cpu` is
  **byte-identical** across two runs (no run-to-run numeric jitter on the CPU
  path routed through the abstraction).

- [ ] **AC4: Auto-resolved default equals explicit CPU on this CuPy-absent host.**
  On this host (CuPy absent), the verdict signature from `run_qc` with
  `SEGQC_BACKEND` **unset** (auto → CPU) equals the verdict signature with
  `SEGQC_BACKEND=cpu`, for a representative corpus case — routing through
  `get_backend()` does not alter the CPU verdict.

- [ ] **AC5: The equivalence comparison helper is non-vacuous.** The suite's
  verdict-signature / feature-tolerance comparison helper, when fed two
  **deliberately different** verdict signatures (and two feature blocks differing
  by more than the tolerance), reports **not-equivalent** — proving the
  equivalence assertions in ACs 7–9 would genuinely catch a divergence rather
  than pass trivially.

- [ ] **AC6: The GPU gate is a genuine skip marker.** The shared marker/guard
  gating every GPU-executing test (e.g. `requires_cupy =
  pytest.mark.skipif(not cupy_available(), reason=…)`, or an equivalent
  `pytest.importorskip("cupy")` guard) is a **real** `skipif` whose condition is
  a `bool` (asserted structurally: `marker.name == "skipif"` and
  `isinstance(marker.args[0], bool)`) — never `xfail`, never an unconditional
  pass — and on this CuPy-absent host its condition evaluates **truthy** (the
  gated tests *will* skip here), proving the GPU coverage is cleanly skipped, not
  silently green.

- [ ] **AC7: GPU vs CPU verdicts are identical (gated).** When CuPy is importable,
  for **every** committed Stage-5 corpus case the verdict signature from `run_qc`
  under `SEGQC_BACKEND=gpu` is **exactly equal** to the signature under
  `SEGQC_BACKEND=cpu` — same overall label, same fired `rule_id`s, same offending
  label sets, same severities. When CuPy is absent this test **skips** (never
  errors, never vacuously passes).

- [ ] **AC8: GPU vs CPU feature values agree within documented tolerance
  (gated).** When CuPy is importable, for every committed corpus case each numeric
  leaf of the CPU `features` block and the GPU `features` block agrees within a
  **documented** relative/absolute tolerance (`rtol`/`atol` stated in the test —
  see Assumptions), while every categorical/string/integer-count leaf is
  **exactly** equal. When CuPy is absent this test skips cleanly.

- [ ] **AC9: GPU vs CPU equivalence holds on the Stage-0 tiny + anisotropic
  fixtures (gated).** When CuPy is importable, the CPU-vs-GPU verdict identity
  (AC7) and feature tolerance (AC8) also hold for the Stage-0 synthetic builders
  `labelled_blocks_case()` and `anisotropic_case()` (the latter exercising
  non-isotropic `(1,1,3)` mm spacing through the EDT/geometry paths). When CuPy
  is absent this test skips cleanly.

## Assumptions  <!-- MANDATORY -->

- **A1 — Backend selection for a full-pipeline run is driven by `SEGQC_BACKEND`,
  NOT a CLI flag or a `run_qc` parameter (pins the item 071/072 contract; hand
  back if diverged).** The suite sets `SEGQC_BACKEND=cpu`/`gpu` via
  `monkeypatch.setenv` and calls the **unmodified** `run_qc`; item 072's ported
  feature functions resolve `backend=None → segqc.backend.get_backend()` at call
  time, which honours the env var (item 071's `resolve_backend_choice`
  precedence: explicit arg > `SEGQC_BACKEND` > `auto`). **Pinned interfaces
  consumed:** `segqc.backend.get_backend(override=None) -> Backend`,
  `backend_name()`, `cupy_available() -> bool`, the `SEGQC_BACKEND` env var and
  its token vocabulary (`cpu`/`gpu`/`auto`), and item 072's `backend=None`
  auto-resolution on `run_qc`'s feature-extraction call chain. **Both items 071
  and 072 are specced but NOT yet built; if either's realised interface diverges
  (e.g. `SEGQC_BACKEND` is not honoured through `run_qc`, the env-driving seam
  does not exist, or `run_qc` requires an explicit backend argument), the item
  073 builder hands back** to reconcile rather than guessing.

- **A2 — "Identical verdict" is exact and categorical; "feature values" use
  tolerance.** Per the queue one-liner and the roadmap clause, the **verdict**
  (the QC decision) must be **bit-identical** between backends: `overall.label`
  plus the full findings set compared as `(rule_id, sorted(labels), severity)`.
  Only the **numeric feature block** is compared within tolerance (float leaves),
  with categorical/string/integer-count leaves required to match exactly. A
  backend difference that flipped a verdict, changed a fired rule, or changed an
  offending-label set is a **failure**, not tolerated drift.

- **A3 — Documented numeric tolerance (aligns with item 072's convention;
  reconcile if 072 pins different numbers).** Float feature-leaf comparison uses
  `numpy.isclose(cpu, gpu, rtol=1e-5, atol=1e-6)` (stated explicitly in the test
  module and in a Decisions note). This is a defensible default for NumPy-vs-CuPy
  drift on the ported ops (EDT, connected-component labelling, Gaussian
  smoothing, dense reductions). **If item 072's landed spot-check (its AC13) pins
  a materially different `rtol`/`atol`, item 073 adopts item 072's published
  tolerance** for consistency; the builder notes the reconciliation in the
  Decisions log. The tolerance governs only continuous float features; discrete
  counts (voxel counts, component counts, label integers) must be **exactly**
  equal — a GPU that changed an integer count would signify a real algorithmic
  divergence, not float drift.

- **A4 — Partial GPU coverage is expected and is not a suite failure.** Item 072
  ports only a subset of the compute (geometry, connected components,
  centroid/EDT, fragmentation) to `Backend.xp`/`Backend.ndimage`; the spline
  steps deliberately run on CPU/SciPy even under a GPU backend (item 072 A2),
  and `extract_feature_record` additionally calls case-level extractors item 072
  never ported (`compute_spine_relationships`, `detect_overlaps`,
  `compute_vertebra_orientations`, `compute_spine_curvature`,
  `compute_spacing_consistency`, `compute_monotonic_consistency`), which run on
  CPU regardless. Equivalence is therefore expected to hold **easily** (much of
  the block is bit-identical because it never touched the GPU); the tolerance in
  A3 exists for the genuinely GPU-computed leaves. This is a documented reality of
  the current port, recorded here so a reviewer does not mistake it for a gap in
  this suite's rigour.

- **A5 — GPU-executing tests must short-circuit before selecting GPU on a
  CuPy-absent host.** Setting `SEGQC_BACKEND=gpu` and calling `run_qc` on a host
  without CuPy would raise `SegQCBackendError` (item 071 AC7), **not** run. The
  GPU-comparison tests (AC7–AC9) must therefore be gated by the `requires_cupy`
  marker / `importorskip` **before** they ever set `SEGQC_BACKEND=gpu`, so a
  CuPy-absent host skips rather than errors. The always-run tests (AC2–AC4) only
  ever use `SEGQC_BACKEND=cpu` or unset, which are safe everywhere.

- **A6 — Verdict/feature capture reuses the merged Stage-0/4/5 seams.** The suite
  loads committed corpus segs via `segqc.synth.regression.loaded_seg_image(case)`
  (item 041), iterates cases via `segqc.synth.corpus.load_manifest()` (item 040),
  runs `segqc.pipeline.run_qc(seg_img, bundled_default_config())` (item 035), and
  canonicalises the feature block for byte comparison via
  `segqc.synth.golden.canonical_json` (item 042). Findings expose `rule_id` via
  `Finding.to_dict()`. No new production seam is introduced.

- **A7 — Hermetic environment handling.** Every test sets/clears `SEGQC_BACKEND`
  with `monkeypatch.setenv`/`delenv` so tests are order-independent and never
  leak a backend selection into another test or the wider suite; the ambient
  process backend (unset → CPU on this host) is restored automatically by
  `monkeypatch` teardown.

- **A8 — Fixtures reused, none added.** Per the queue item, the suite reuses the
  committed Stage-5 corpus (9 cases) and the Stage-0 synthetic builders; it adds
  **no** new binary fixture and does not regenerate the corpus, manifest, or
  goldens.

## Implementation Steps

_This item adds tests only — see `aide.toml` → `project.tests_dir` (`tests`). No
file under `project.source_dir` (`src/segqc`) is edited._

1. **Create `tests/test_073_verdict_equivalence.py`** with a module docstring
   stating: the `SEGQC_BACKEND`-driven mechanism (A1), the exact-verdict /
   tolerant-feature policy (A2), the documented tolerance (A3), the partial-GPU
   coverage reality (A4), and the GPU-less-host skip behaviour.

2. **Shared gate marker.** Define
   `requires_cupy = pytest.mark.skipif(not cupy_available(), reason="CuPy/GPU not
   available")` (importing `cupy_available` from `segqc.backend`). Every
   GPU-executing test is decorated with it. (An `importorskip`-based helper is an
   acceptable equivalent provided AC6's structural check is adapted accordingly.)

3. **Comparison helpers (module-local, importable by the tests):**
   - `verdict_signature(case_result) -> tuple`: `(verdict.overall.label,
     frozenset((f["rule_id"], tuple(sorted(f["labels"])), f["severity"]) for f in
     [fd.to_dict() for fd in case_result.findings]))` — an order-insensitive,
     hashable, exactly-comparable categorical signature.
   - `feature_leaves_close(cpu_block, gpu_block, *, rtol, atol) -> bool`: walk the
     two nested dicts/lists in lockstep; require identical structure/keys; compare
     `float` leaves with `numpy.isclose(rtol=rtol, atol=atol)` and all other
     leaves (str/int/bool/None) with `==`; return `False` on any structural
     mismatch or out-of-tolerance leaf.

4. **Backend-run helper.**
   `run_under_backend(seg_img, cfg, token, monkeypatch) -> (CaseResult, dict)`:
   set `SEGQC_BACKEND=token` (or `delenv` when `token is None`) via
   `monkeypatch`, then return `run_qc(seg_img, cfg)`.

5. **AC1** — a trivial presence/collectability test (`Path(__file__).is_file()`)
   plus a bare `import segqc.backend` under the ambient (CuPy-absent) condition;
   assert success.

6. **AC2/AC3/AC4 (always run, CPU-only).** Parametrise AC2 over
   `load_manifest()["cases"]`; run each twice under `SEGQC_BACKEND=cpu` and assert
   equal `verdict_signature`. AC3: `canonical_json`-compare two CPU-run feature
   blocks for a multi-label case. AC4: compare the unset-env verdict signature to
   the `cpu` one for a representative case.

7. **AC5 (always run, non-vacuity).** Build two hand-crafted `CaseResult`s /
   feature blocks known to differ (a differing verdict label; a float leaf off by
   `>> atol`) and assert the helpers report **not-equivalent**.

8. **AC6 (always run, structural skip proof).** Assert
   `requires_cupy.mark.name == "skipif"`, `isinstance(requires_cupy.mark.args[0],
   bool)`, and `requires_cupy.mark.args[0] is True` on this CuPy-absent host
   (mirroring `tests/test_069_container_smoke.py`'s `test_ac2_...`).

9. **AC7/AC8/AC9 (CuPy-gated).** Each decorated with `@requires_cupy`. AC7:
   parametrise over corpus cases, assert `verdict_signature(cpu) ==
   verdict_signature(gpu)`. AC8: parametrise over corpus cases, assert
   `feature_leaves_close(cpu_block, gpu_block, rtol=1e-5, atol=1e-6)`. AC9: same
   two assertions over `labelled_blocks_case()` and `anisotropic_case()` seg
   images.

10. **No production edits.** Do not touch `src/segqc/**` or `pyproject.toml`; the
    validator confirms the diff is tests-only.

## Testing Strategy

_The test module IS the deliverable; the test-writer authors it, the builder adds
nothing in `src/`, and the validator runs the full suite. Do **not** run
`pytest` as spec-author._

Module: **`tests/test_073_verdict_equivalence.py`** (mirrors the `test_0NN_*.py`
convention). One focused test per AC:

- **AC1** — module-file presence + `import segqc.backend` under ambient
  (CuPy-absent) conditions; assert no error and that the module collects (the
  gated tests must not raise at import/collection).
- **AC2** — parametrised over all 9 committed corpus cases: two `run_qc` calls
  under `SEGQC_BACKEND=cpu`; assert equal `verdict_signature`. Confirms the CPU
  path through the abstraction is deterministic on the real verdict.
- **AC3** — `canonical_json(extract_feature_record(...))` computed twice under
  `SEGQC_BACKEND=cpu` for a multi-label case (e.g. `clean_control`); assert
  byte-identical.
- **AC4** — verdict signature with env unset vs `SEGQC_BACKEND=cpu` for a
  representative case; assert equal (auto → CPU on this host).
- **AC5** — feed `verdict_signature`-level and `feature_leaves_close`-level
  comparisons two inputs known to differ (different verdict label; a float leaf
  perturbed by `10*atol`); assert the helper returns not-equivalent. Guards
  against a vacuously-passing comparator.
- **AC6** — structural assertions on the `requires_cupy` marker: it is a
  `skipif` with a `bool` condition that is `True` on this host (genuine skip,
  not `xfail`, not vacuous), following item 069's precedent exactly.
- **AC7** — `@requires_cupy`; parametrised over corpus cases; assert
  `verdict_signature` equal across CPU and GPU env selections.
- **AC8** — `@requires_cupy`; parametrised over corpus cases; assert
  `feature_leaves_close(cpu, gpu, rtol=1e-5, atol=1e-6)` and that categorical
  leaves matched exactly (the helper enforces both).
- **AC9** — `@requires_cupy`; over `labelled_blocks_case()` and
  `anisotropic_case()`; assert verdict identity and feature tolerance.

**Adversarial / edge cases to include:**
- **Empty / single-label maps under both backends.** Confirm `empty_case()`
  (0 labels) and a 1-label map produce equal verdict signatures under CPU (always)
  and, gated, under GPU — the degenerate paths (`relationships is None`, no
  `stage3`) route through the abstraction without divergence.
- **Anisotropic spacing** (`anisotropic_case()`, `(1,1,3)` mm) — exercises the
  EDT/geometry physical-scale paths where NumPy-vs-CuPy drift is most plausible;
  covered by AC9.
- **Env hermeticity/determinism** — a test that after the suite runs,
  `SEGQC_BACKEND` is not left set in `os.environ` (monkeypatch teardown), so no
  backend selection leaks into other test modules.
- **Non-vacuity of the skip** (AC6) — the marker's truthy condition on this host
  is asserted directly, so "the GPU tests passed" can never be reported when they
  were in fact skipped, and "skipped" can never hide a missing test (the gated
  tests exist and carry the marker).
- **Guard-before-GPU-selection** (A5) — the gated tests must not set
  `SEGQC_BACKEND=gpu` on a CuPy-absent host; the `@requires_cupy` decorator
  ensures they skip before touching the env, so a CuPy-absent host never triggers
  `SegQCBackendError`.

## Dependencies

- **Item 071 — GPU/CPU backend abstraction (specced, NOT yet built; `📋` in
  `progress.md`).** Provides `segqc.backend`: `get_backend(override=None) ->
  Backend`, `backend_name()`, `cupy_available()`, the `SEGQC_BACKEND` env var and
  its `cpu`/`gpu`/`auto` vocabulary, and `SegQCBackendError`. The suite selects
  backends via `SEGQC_BACKEND` and gates on `cupy_available()`. Must land
  (✅/🚧) before item 073 is built; if the realised interface diverges from
  Assumption A1/A5, the builder hands back.
- **Item 072 — Port feature extraction to the backend (specced, NOT yet built;
  `📋`).** Provides the `backend=None → get_backend()` auto-resolution on the
  Stage-2/3 feature functions that `run_qc → extract_feature_record` calls, so a
  `SEGQC_BACKEND`-selected backend actually reaches the GPU-ported compute
  without any `pipeline.py`/`cli.py` change, plus the numeric-tolerance
  convention (its AC13) this item aligns to (A3). Must land (✅/🚧) before item
  073 is built; if `SEGQC_BACKEND` is not honoured through the unmodified
  `run_qc`, or the landed tolerance differs materially, the builder hands back /
  reconciles per A1/A3.
- **Item 035 (✅)** — `segqc.pipeline.{run_qc, extract_feature_record}` and
  `bundled_default_config`: the full-pipeline entry point driven under each
  backend.
- **Item 034 (✅)** — `segqc.aggregate.CaseResult` / `segqc.verdict.Verdict` /
  `Severity` and `Finding.to_dict()` (rule_id/labels/severity): the verdict and
  findings the signature is built from.
- **Items 040/041/042 (✅)** — `synth.corpus.load_manifest`,
  `synth.regression.loaded_seg_image`, and `synth.golden.canonical_json`: the
  committed corpus ingestion + canonical-JSON byte comparison, untouched.
- **Item 002 (✅)** — `tests/synthetic.py` (`labelled_blocks_case`,
  `anisotropic_case`, `empty_case`): the Stage-0 tiny fixtures reused in AC9 and
  the degenerate edge cases.
- **Item 069 (✅)** — `tests/test_069_container_smoke.py`'s genuine-skip proof
  (`requires_docker` structural assertion): the precedent AC6 mirrors for a
  CuPy-gated marker.
- **Downstream (informational):** item 075 wires `segqc run --backend` and closes
  Stage 10; its GPU-clause acceptance re-runs this suite's GPU-gated tests on a
  GPU-capable host.

## Decisions & Trade-offs

To be updated during implementation.
