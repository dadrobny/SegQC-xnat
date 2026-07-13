# Seg-QC-xnat — Work Queue 009

> **Status:** Live · **Created:** 2026-07-13
> Step 4 of the AIDE loop. Derived from [`../vision.md`](../vision.md),
> [`../roadmap.md`](../roadmap.md), and [`../progress.md`](../progress.md).
> Follows [`queue-008.md`](queue-008.md) (items 066–070, Stage 9 — all ✅).

---

## Scope of this queue

Delivers roadmap **Stage 10 — Portable Compute: GPU Acceleration Path (G6)** in
full. Stage 10 is the *third* stage of "Phase 2 — Extensions" — an **optional**
GPU-accelerated compute path (CuPy/cuCIM) for the existing geometric/topological
feature-extraction core (Stages 2–3), with the hard requirement that the CPU-only
path remains the default and fully functional with no GPU present, and that the
two paths are numerically equivalent.

**This is an additive, backend-selection layer — no heuristic, verdict, schema,
or CLI-surface change beyond backend selection itself.** Everything Stage 10
optionally accelerates already exists and stays authoritative: the Stage-2/3
feature-extraction modules (`src/segqc/features/*.py` — `geometry.py`,
`components.py`, `centroids.py`, `spline.py`, etc.), the pipeline that calls
them (`src/segqc/pipeline.py`), and the `segqc` CLI. Stage 10 does not add new
features or heuristics; it adds a **second execution path** for the numeric
compute already covered by Stages 2–3's tests, selected at runtime.

**Milestone delivered:** a `segqc.backend` runtime-selection module that
auto-detects CuPy/cuCIM and falls back to NumPy/SciPy/scikit-image transparently
(with an explicit override and a clear error if GPU is forced but unavailable);
the Stage-2/3 feature-extraction hot paths routed through that abstraction;
a CPU-vs-GPU verdict-equivalence test suite; a performance benchmark; and a
Stage-10 acceptance check tying it together. On completion, Stage 10's roadmap
acceptance criterion holds: *"GPU path is optional + auto-detected; CPU/GPU
verdict-equivalence tests pass; the tool runs fully CPU-only (G6)."*

**Prioritisation rationale.** Stage 10's only roadmap dependency is **Stage 7**
("stable, calibrated pipeline"), ✅ since queue-006, and it does not depend on
Stage 8 or 9. It is independent of Stage 11 (extensibility/classification),
which is sequenced after. Following the roadmap's stage order (`8 → 9 → 10 →
11` in the Phase-2 list), Stage 10 is the next unclaimed stage; Stage 11 remains
for a future queue. The queue is scoped to **exactly Stage 10** and stops at
the stage boundary.

**Local-testability note, and the central hardware constraint.** This
development environment (and likely most contributor/CI machines) has **no
GPU and no CuPy/cuCIM installed**. Every Stage-10 item must therefore be fully
testable, and its acceptance meaningful, **without a GPU present** — mirroring
item 060's `pytest.importorskip`/`skipif`-style graceful degradation for an
optional/environment-dependent capability (already established for the
`radiomics` extra in Stage 8, and for Docker in Stage 9). Concretely:
- The default (no-GPU) path is exercised and asserted directly — this is not a
  skip, it is the primary, always-tested path (GPU is optional, CPU is not).
- Any GPU-*executing* assertion (does CuPy actually get selected, does a real
  GPU kernel run, does its output match CPU bit-for-bit/within-tolerance) is
  gated behind a CuPy-availability check and **skips cleanly**, never fails,
  when CuPy/a GPU is absent.
- Backend-*selection logic itself* (auto-detect, explicit override, clear error
  when GPU is forced but unavailable) is fully unit-testable on a GPU-less host
  by **mocking/monkeypatching the presence or absence of the `cupy` import**
  (`sys.modules` injection or `monkeypatch.setattr`) — no real GPU needed for
  this layer, and it is the bulk of what this queue can prove locally.

### Numbering note — read before picking an item

Items 001–070 are complete (Stages 0–9, all ✅ in `progress.md`). This queue
continues at the next free integer and is strictly monotonic: **071–075**.

**Estimated size:** ~1 week (5 items, well within `loop.queue_cap = 10`). Each
item is independently testable locally without a GPU: the backend-selection
item asserts auto-detect/override/error behaviour via import mocking; the
feature-porting item asserts the existing Stage-2/3 test suite still passes
unchanged under the (default) CPU backend, plus a GPU-gated equivalence spot
check that skips without CuPy; the equivalence-suite item asserts CPU-path
determinism directly and gates the CPU-vs-GPU comparison itself behind CuPy
availability; the benchmark item asserts the benchmark runs and emits a
well-formed timing report regardless of which backend is active; the closing
item asserts the Stage-10 acceptance criterion's CPU-only clause unconditionally
and its GPU-equivalence clause when a GPU is present, documenting the
GPU-less-host result explicitly rather than glossing over it.

**Sequencing note.** Critical path: **071** (backend abstraction + auto-detect/
override/error semantics) is the foundation every other item builds on — merge
first. **072** (porting Stage-2/3 feature extraction to route through the
abstraction) depends on 071 and is the largest item — it must land before **073**
(equivalence tests) can meaningfully compare backends. **074** (performance
benchmark) depends on 071 (needs backend selection to report/compare against)
but is otherwise independent of 072/073's completion — it *can* run in parallel
with 073 once 072 lands, since it only needs a working backend-aware compute
path to benchmark, not the equivalence suite itself. **075** (integration +
acceptance, closes Stage 10) depends on everything. Recommended order:
071 → 072 → (073 ‖ 074) → 075.

### Stage-10 deliverable → item coverage

| Stage-10 deliverable | Delivered by item(s) |
|---|---|
| **Runtime backend selection** (CuPy/cuCIM when present, NumPy/SciPy fallback) | 071 |
| **Backend-aware feature extraction** (Stage 2/3 compute routed through the abstraction) | 072 |
| **Equivalence tests**: CPU vs GPU produce identical verdicts | 073 |
| **Performance benchmark** | 074 |
| **CLI/pipeline integration + Stage-10 acceptance closure** | 075 |

Every deliverable is realised by ≥1 item. Item 071 is the abstraction
foundation; item 075 closes the stage and records the Stage-10 acceptance
evidence, explicitly noting the GPU-availability state of the host it ran on.

---

## Work items

### Item 071: GPU/CPU backend abstraction — runtime selection, auto-detect, explicit override
Add a `segqc.backend` module providing a uniform array/compute-backend
selection layer: auto-detects CuPy (and, where relevant to the ported ops in
item 072, cuCIM) at runtime, falling back to NumPy/SciPy/scikit-image when
absent; exposes a small selection API (e.g. `get_backend()`, an `xp`-style
module handle, a `backend_name()` introspection helper) plus an explicit
override (CLI flag and/or environment variable, e.g. `SEGQC_BACKEND=cpu|gpu|
auto`) so a user or CI can force CPU even when a GPU is present, or request GPU
explicitly. Forcing GPU when CuPy is unavailable must fail with a clear,
actionable error (not an import traceback) — the tool must still run fully
CPU-only by default with **zero** required GPU dependencies (`cupy`/`cucim`
stay optional extras, never core deps in `pyproject.toml`). No feature-
extraction code is migrated yet — this item is pure plumbing/API surface for
item 072 to build on. *Testable:* unit tests exercise backend selection with
CuPy present/absent via import mocking (`sys.modules`/`monkeypatch`, no real
GPU needed) — auto-detect picks GPU only when CuPy is genuinely importable and
otherwise falls back to CPU silently; an explicit `SEGQC_BACKEND=cpu` override
always yields the CPU backend even when CuPy is mocked as present; an explicit
`SEGQC_BACKEND=gpu` override with CuPy mocked absent raises a clear, non-
traceback error; confirm no new required dependency was added to `pyproject.toml`'s
core `dependencies` list.

### Item 072: Port geometric/topological feature extraction to the backend abstraction
Migrate the Stage 2/3 feature-extraction hot paths — per-label volume/extent/
bounding-box (`features/geometry.py`), connected-components (`features/
components.py`), centroid/EDT computations (`features/centroids.py`),
fragmentation (`features/fragmentation.py`), spline fit and offset
(`features/spline.py`, `features/spline_offset.py`) — to route their array
operations through item 071's backend abstraction, so they execute on GPU
(CuPy/cuCIM equivalents of NumPy/SciPy/scikit-image calls) when selected, and
on NumPy/SciPy/scikit-image otherwise, producing numerically equivalent
results in both cases. Do **not** port Stage-8 intensity/radiomics features in
this item (out of scope — radiomics already has its own optional-dependency
path from item 060; keep Stage 10's scope to the Stage-2/3 geometric/
topological core that Stage 10's roadmap entry names). *Testable:* the
existing Stage-2/3 test suite (`tests/test_01[1-9]*`, `tests/test_02*` feature
tests) passes unchanged under the default CPU backend (regression guard — this
item must not change a single CPU-path numeric result); a GPU-gated spot-check
test (skips cleanly without CuPy) computes a representative feature (e.g.
per-label volume and one centroid variant) under both backends on a small
fixture and asserts they agree within a documented numeric tolerance.

### Item 073: CPU vs GPU verdict-equivalence test suite
Add an equivalence test suite that runs representative fixtures (reusing the
existing Stage-5 synthetic corpus and/or Stage-0 tiny fixtures — no new
binaries) through the full pipeline under both the CPU backend and, when
available, the GPU backend, and asserts the two produce **identical QC
verdicts** (and feature values within a documented numeric tolerance,
acknowledging floating-point non-determinism between NumPy/SciPy and CuPy
kernels). This is the direct test for the roadmap's "CPU/GPU verdict-
equivalence tests pass" acceptance clause. The suite must assert real,
meaningful equivalence when a GPU is genuinely present, and skip cleanly (never
fail, never silently vacuously pass) when CuPy/a GPU is absent — mirroring
items 060/069's Docker/radiomics-gated pattern. *Testable:* on a GPU-less host,
the suite's CPU-only assertions (verdict determinism/reproducibility across
repeated CPU runs) still execute and pass, and the GPU-comparison tests report
as cleanly skipped (not vacuously green) via a structural test proving the skip
marker is genuine; on a GPU-present host (not required to be this development
environment, but the code must be ready for one), the full CPU-vs-GPU
comparison actually runs.

### Item 074: Performance benchmark
Add a lightweight, deterministic performance benchmark (script and/or pytest
test) measuring wall-clock time for the Stage-2/3 feature-extraction stages on
a repeatable fixture, reporting timings per active backend (CPU always;
GPU too, when available) in a structured (JSON or Markdown) benchmark report
committed as a documented artifact or regenerable via a CLI/script entry
point. Do not assert on absolute timing thresholds (hardware varies
too much across contributor machines/CI runners to make an absolute-time
assertion meaningful or stable) — assert instead on the benchmark's structural
correctness (it runs to completion, reports timings for the backend(s)
actually available, and the report is well-formed/parseable). *Testable:* the
benchmark runs deterministically-scoped iterations on a small fixture and
emits a report with the expected schema/fields; a test asserts the CPU timing
entry is always present and positive; a GPU timing entry is asserted present
only when CuPy is available, otherwise its absence (not a placeholder zero or
crash) is asserted directly.

### Item 075: Stage 10 integration & acceptance *(completes Stage 10)*
Wire backend selection into the `segqc run` CLI (and any other CLI entry
points that invoke the ported feature-extraction code) so a user can select
`--backend cpu|gpu|auto` (or the item-071 environment-variable equivalent) at
the point of invocation, with `auto` as the default. Add a Stage-10 acceptance
check tying together items 071–074 into one coherent, documented, testable
path, and reconcile `docs/aide/progress.md`'s Stage 10 section (deliverable
bullets, acceptance checkboxes, summary status, G6 objective-coverage row) —
`roadmap.md` itself is a PR-gated framework file and is **not** edited by this
item's direct-merge work (mirror items 049/057/065/070's precedent exactly).
The acceptance check must explicitly record, in its output or a committed note,
**whether the host it ran on had a GPU/CuPy available** — the roadmap's
acceptance bar has a CPU-only clause (unconditionally testable everywhere) and
a GPU-equivalence clause (only actually exercised on a GPU-capable host) that
must not be conflated. *Testable:* the acceptance check asserts (unconditionally)
that `segqc run --backend cpu` (or the CPU auto-detected default) succeeds
end-to-end with no GPU dependency required, and (conditionally, GPU-gated) that
the item-073 equivalence suite's GPU-comparison tests pass when a GPU is
present; the check's own report/test-output states plainly which of the two
clauses were actually exercised on the run that produced it.

---

## Current state (2026-07-13)

Freshly generated; supersedes [`queue-008.md`](queue-008.md) (Stage 9,
items 066–070, all ✅). This is the **third Phase-2 queue** and opens
**Stage 10 — Portable Compute: GPU Acceleration Path** on top of the complete
Phase-1 pipeline and the Stage-8/9 extensions. No Stage 10 items claimed yet.
**071** (backend abstraction) is the shared foundation and should merge first;
**072** (feature porting) is the largest item and depends on 071; **073**
(equivalence suite) and **074** (benchmark) are then parallelisable once 072
lands; **075** (CLI integration + acceptance) closes the stage. This
development environment has no GPU/CuPy installed, so every item's Docker/
GPU-gated tests are expected to skip cleanly here (mirroring items 060/069) —
this is by design, not a gap, and is explicitly called out in item 075's
acceptance reporting. This queue is landing via a human-reviewed queue PR (the
Phase-2 batch checkpoint).

## Next Step

Per `CLAUDE.md`: `git fetch --all --prune` and check `aide/*` branches first, then
branch per item (`aide/NNN-short-name`) and push immediately to claim it;
`git pull --rebase` before any `progress.md` edit. Start with **071**. Two ways
to proceed: spec the whole queue now with `/aide-spec-queue 009` in one
interactive sitting, or spec per-item during execution via `/aide-run-queue 009`.
