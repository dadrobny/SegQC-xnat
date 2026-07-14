# Item 074 — Performance benchmark (CPU/GPU feature-extraction timing)

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 10 — Portable Compute: GPU Acceleration Path
> **Queue:** [`../queue/queue-009.md`](../queue/queue-009.md) · Item 074
> **Objectives:** G6 (Portable execution — identical results CPU-only; optional GPU acceleration path)
> **Suggested branch:** `aide/074-performance-benchmark`

---

## Description

Add a **lightweight, deterministic performance benchmark** that measures
wall-clock time for the Stage-2/3 feature-extraction pass on a repeatable
fixture, under each backend that is actually available (**CPU always; GPU only
when CuPy is genuinely importable**), and emits a **structured, parseable JSON
report**. The benchmark is regenerable via a script entry point
(`python -m segqc.benchmark …`); it is **not** an absolute-performance gate.

This item exists to give Stage 10 a repeatable, structurally-correct timing
artifact — **not** to prove the GPU path is faster. Per the queue one-liner, it
deliberately makes **no absolute-time assertions** (contributor/CI hardware
varies far too much for a fixed second-count threshold to be meaningful or
stable); it asserts only the benchmark's **structural correctness** — that it
runs to completion, reports timings for the backend(s) actually available, and
the report is well-formed and parseable.

**The timed unit and how a backend is selected.** The benchmark times
`segqc.pipeline.extract_feature_record(seg_img, config)` — the whole Stage-2/3
feature-extraction pass over one seg image, which drives every ported hot path
(`geometry`, `components`, `centroids`, `fragmentation`, `spline`,
`spline_offset`). Exactly as in item 073, a backend is selected for that call by
setting the `SEGQC_BACKEND` environment variable (item 071) and invoking the
**unmodified** `extract_feature_record`: item 072's ported feature functions
resolve `backend=None → segqc.backend.get_backend()` at call time, which honours
the env var. No `pipeline.py` / `cli.py` change is needed, and the
`segqc run --backend` flag is item 075's job, not this item's.

**What it delivers:**

- A new module `src/segqc/benchmark.py` with:
  - `run_benchmark(*, case_id=None, iterations=5, warmup=1) -> dict` — loads a
    small committed fixture, runs a fixed warmup + `iterations` timed repeats of
    `extract_feature_record` **per available backend**, and returns a
    schema-valid report dict.
  - `write_report(report, out_path)` — serialise the report to JSON.
  - `main(argv=None) -> int` — an argparse script entry point
    (`python -m segqc.benchmark --out <file> [--iterations N] [--warmup W]
    [--case ID]`) that runs the benchmark and writes the JSON report.
- A JSON **report schema** (documented below) whose `backends` list contains one
  entry **per backend actually run** — always `cpu`, and `gpu` **only when**
  `cupy_available()` is true — plus an explicit top-level `cupy_available` flag
  so a GPU's *absence* is represented directly (never as a placeholder-zero GPU
  entry, never as a crash).
- A pytest module `tests/test_074_benchmark.py` asserting structural correctness
  (schema, CPU entry present + positive, GPU entry present only when CuPy is
  available with its absence asserted directly otherwise, JSON round-trip, script
  entry point, determinism of scope).

**Report schema (JSON).** `run_benchmark` returns / `main` writes a dict with
these **required** top-level keys:

| Key | Type | Meaning |
|---|---|---|
| `benchmark_version` | `str` | Schema version (e.g. `"1"`). |
| `timed_unit` | `str` | The timed callable's name, `"extract_feature_record"`. |
| `iterations` | `int` | Timed repeats per backend (echoes the request). |
| `warmup` | `int` | Warmup (untimed) repeats per backend (echoes the request). |
| `cupy_available` | `bool` | `segqc.backend.cupy_available()` at run time. |
| `fixture` | `object` | `{source, case_id, n_labels, shape, spacing_mm}` — deterministic fixture identity. |
| `backends` | `array` | One entry per backend actually run (see below). |

Each `backends[i]` is an object with required keys: `name` (`"cpu"`/`"gpu"`),
`is_gpu` (`bool`), `iterations` (`int`), `warmup` (`int`), `timings_s`
(`array` of `float`, length `== iterations`), `min_s` (`float`), `mean_s`
(`float`), `median_s` (`float`). The report MAY carry extra metadata keys (e.g.
a timestamp), but MUST carry at least the required set. All leaves are
JSON-native (`str`/`int`/`float`/`bool`/`list`/`dict`) — no NumPy scalars leak.

**What it is NOT (scope fence):**

- **No absolute-time assertion.** No test compares a timing to a fixed
  second-count threshold; the benchmark proves nothing about GPU-vs-CPU speed.
- **No CLI subcommand.** The benchmark is a standalone `python -m segqc.benchmark`
  script — it does **not** add a `segqc benchmark` subcommand and does **not**
  touch `cli.py`. The `segqc run --backend` flag is **item 075**.
- **No production numeric-behaviour change.** It only *reads* existing seams
  (`extract_feature_record`, `segqc.backend`, `segqc.synth`); it does not edit
  `pipeline.py`, any `features/*.py`, `backend.py`, or the numeric results.
- **No CPU-vs-GPU equivalence / tolerance assertions** (that is item 073) and
  **no committed timing artifact** — timings are non-deterministic and
  hardware-specific, so the report is *regenerated on demand* to a caller-chosen
  path, never committed (this respects the repo's byte-reproducible-fixture
  discipline; see Assumptions A6).
- **No new binary fixture.** It reuses the committed Stage-5 corpus via the
  same `segqc.synth` seams item 073 uses.

## Acceptance Criteria

_Each criterion is atomic, observable, and one test per AC. All live in
`tests/test_074_benchmark.py`. AC1–AC12 run and pass unconditionally on a
GPU-less host; AC13 is CuPy-gated and skips cleanly when CuPy is absent._

- [ ] **AC1: Module imports GPU-free.** `import segqc.benchmark` succeeds on a
  host where `cupy` is not installed — no `ImportError`, and the module does not
  import `cupy` at module scope.

- [ ] **AC2: `run_benchmark` returns a report and runs to completion.** On this
  CuPy-absent host, `segqc.benchmark.run_benchmark(iterations=2, warmup=1)`
  returns a `dict` without raising (the benchmark runs to completion on the
  default small fixture).

- [ ] **AC3: Report carries the documented schema.** The returned report has
  every required top-level key (`benchmark_version`, `timed_unit`, `iterations`,
  `warmup`, `cupy_available`, `fixture`, `backends`) of the documented type, and
  `timed_unit == "extract_feature_record"`; each `backends` entry has every
  required key (`name`, `is_gpu`, `iterations`, `warmup`, `timings_s`, `min_s`,
  `mean_s`, `median_s`) of the documented type.

- [ ] **AC4: CPU backend entry always present.** Regardless of GPU availability,
  the `backends` list contains **exactly one** entry with `name == "cpu"` and
  `is_gpu is False`.

- [ ] **AC5: CPU timings are positive.** For the `cpu` entry, every sample in
  `timings_s` is a `float` strictly `> 0`, and `min_s`, `mean_s`, `median_s` are
  each `> 0` (wall-clock time is never zero or negative).

- [ ] **AC6: Iteration scope is deterministic and honoured.** Calling
  `run_benchmark(iterations=k, warmup=w)` for a chosen `k` (e.g. 3) produces a
  `cpu` entry whose `timings_s` has length **exactly `k`**, with the report's
  top-level `iterations == k` and `warmup == w` and the entry's `iterations == k`
  — the timed loop is a fixed, finite count, not adaptive/open-ended.

- [ ] **AC7: GPU entry is absent (not zero, not a crash) when CuPy is absent.**
  On this CuPy-absent host, the report completes without raising, `cupy_available`
  is `False`, and **no** `backends` entry has `name == "gpu"` — the GPU's absence
  is asserted **directly** (there is no placeholder-zero GPU entry and no error).

- [ ] **AC8: Backends reported equal backends available.** The set of `name`s in
  `backends` equals exactly the set of backends actually run: `{"cpu"}` when
  `cupy_available()` is `False`, and `{"cpu", "gpu"}` when it is `True` — the
  report never claims a backend it did not run, nor omits one it did.

- [ ] **AC9: Report is JSON well-formed / round-trippable.**
  `json.loads(json.dumps(report))` succeeds and equals the original report —
  every leaf is a JSON-native type (no NumPy scalar / `Path` / non-serialisable
  object leaks into the report).

- [ ] **AC10: Script entry point writes a parseable JSON file.** Invoking
  `segqc.benchmark.main(["--out", <path>, "--iterations", "2", "--warmup", "1"])`
  returns `0`, writes the file at `<path>`, and that file's contents `json.load`
  back to a schema-valid report (same required keys as AC3) with a positive
  `cpu` `min_s`.

- [ ] **AC11: Fixture is reused, small, and recorded deterministically.** The
  report's `fixture` block identifies a committed corpus case (`source ==
  "corpus"`, a stable `case_id`, `n_labels >= 2`, and `shape`/`spacing_mm`
  matching the loaded seg image); no new binary fixture file is added by this
  item (the diff adds no `.nii`/`.nii.gz`).

- [ ] **AC12: Benchmark is read-only.** Running `run_benchmark` does not mutate
  the loaded fixture seg image — a fresh load of the same case before and after a
  benchmark run yields byte-identical label-array data (the benchmark only reads).

- [ ] **AC13: No new core dependency.** `pyproject.toml`'s `[project].dependencies`
  gains nothing for this item (the benchmark uses only the stdlib `time`/`json`/
  `argparse`/`statistics` plus already-present deps); neither `cupy` nor any new
  package appears in the core dependency list.

- [ ] **AC14: GPU-timing test is genuinely CuPy-gated (real skip, not vacuous).**
  The GPU-executing timing test is guarded by a shared marker
  `requires_cupy = pytest.mark.skipif(not cupy_available(), reason=…)` whose
  `mark.name == "skipif"` and whose condition `mark.args[0]` is a `bool` that is
  `True` on this CuPy-absent host — a genuine skip (never `xfail`, never an
  unconditional pass), mirroring `tests/test_069_container_smoke.py`'s precedent.

- [ ] **AC15: GPU entry present and positive when CuPy is available (gated).**
  Under `@requires_cupy` (skips cleanly on this host): when CuPy is importable,
  the report's `backends` includes an entry with `name == "gpu"`, `is_gpu is
  True`, `timings_s` of length `iterations` with every sample `> 0`, and
  `cupy_available is True`.

## Assumptions  <!-- MANDATORY -->

- **A1 — Backend is selected via `SEGQC_BACKEND`, driving the unmodified
  `extract_feature_record` (pins the item 071/072 contract; hand back if
  diverged).** The benchmark sets `os.environ["SEGQC_BACKEND"] = "cpu"` /
  `"gpu"` around each timed block and calls the **unmodified**
  `segqc.pipeline.extract_feature_record`; item 072's ported feature functions
  resolve `backend=None → segqc.backend.get_backend()` at call time, honouring
  the env var (item 071 precedence: explicit arg > `SEGQC_BACKEND` > `auto`).
  **Pinned interfaces consumed:** `segqc.backend.cupy_available() -> bool`, the
  `SEGQC_BACKEND` env var + its `cpu`/`gpu`/`auto` vocabulary, and item 072's
  `backend=None` auto-resolution reaching `extract_feature_record`'s feature
  calls. **Items 071 and 072 are specced but NOT yet built; if either's realised
  interface diverges (e.g. `SEGQC_BACKEND` is not honoured through
  `extract_feature_record`, or `cupy_available()` is named/shaped differently),
  the item-074 builder hands back** to reconcile rather than guessing.

- **A2 — The timed unit is `extract_feature_record` (the Stage-2/3 feature
  pass), not the full `run_qc` or per-function micro-benchmarks.** The queue
  names "the Stage-2/3 feature-extraction stages"; `extract_feature_record` is
  the single aggregate call that drives every ported hot path, so it is the
  realistic, backend-sensitive unit to time. Per-function breakdown is
  deliberately out of scope (a possible future refinement). If a reviewer wants
  per-stage granularity, that is a follow-up, not this item.

- **A3 — Location: a standalone `python -m segqc.benchmark` module, NOT a
  `segqc` CLI subcommand.** The queue permits "script and/or pytest test …
  regenerable via a CLI/script entry point"; a standalone module satisfies that
  while staying clear of item 075's CLI scope (`segqc run --backend`). The
  benchmark adds **no** subcommand and does **not** edit `cli.py`. **Pinned for
  075:** if item 075 later decides a `segqc benchmark` subcommand is wanted, it
  can wrap `segqc.benchmark.run_benchmark`/`main` — this item deliberately does
  not claim that surface.

- **A4 — Report format is JSON (canonical, machine-parseable); no Markdown.**
  The queue permits "JSON or Markdown"; JSON is chosen because the acceptance
  bar is *parseability / schema correctness*, which JSON supports trivially and
  Markdown does not. A human-readable Markdown rendering is out of scope for
  this item.

- **A5 — Iteration scope: default `warmup=1`, `iterations=5`, both overridable;
  report min/mean/median.** "Deterministically-scoped iterations" is interpreted
  as a **fixed, caller-specified** repeat count (never adaptive). One untimed
  warmup absorbs first-call import/JIT costs; five timed repeats give a stable
  min/mean/median. Both counts are CLI-overridable (`--iterations`, `--warmup`)
  and echoed into the report (AC6). Reported summary stats use the stdlib
  `statistics` module and Python `min`.

- **A6 — The report is regenerated on demand, NOT committed.** The queue permits
  "committed as a documented artifact **or** regenerable via a CLI/script entry
  point"; regeneration is chosen because wall-clock timings are inherently
  non-deterministic and hardware-specific — committing them would violate the
  repo's byte-reproducible-fixture discipline (CLAUDE.md "Gotchas") and could
  never be byte-identity-tested. `main --out <path>` writes to a caller-chosen
  location; tests write to a pytest `tmp_path`. No timing file is added to the
  repo, so **no `.gitattributes` LF pin is required** for this item.

- **A7 — Default fixture: a deterministically-selected multi-label committed
  corpus case, loaded via the item 073 `segqc.synth` seams (no new binary).**
  `run_benchmark` (case_id `None`) picks the **first** case from
  `segqc.synth.corpus.load_manifest()["cases"]` (stable manifest order) whose
  loaded seg has `>= 2` labels, loading it with
  `segqc.synth.regression.loaded_seg_image(case)` and configuring via
  `segqc.config.bundled_default_config()`. `--case ID` overrides. This reuses
  item 073's exact fixture source (committed Stage-5 corpus) and adds no new
  binary — matching the queue's fixture convention. **Pinned seams consumed:**
  `synth.corpus.load_manifest()` (item 040), `synth.regression.loaded_seg_image`
  (item 041), `pipeline.extract_feature_record` + `config.bundled_default_config`
  (item 035) — all ✅. If the manifest schema (`cases` list, `case_id`,
  `scan_fixture`/`seg_fixture` keys) has changed by build time, the builder hands
  back.

- **A8 — GPU timing needs a *real* CuPy; GPU presence cannot be faithfully
  mocked for timing.** Mocking `cupy` present would make `SEGQC_BACKEND=gpu`
  resolve to a `Backend` whose `.xp` is a stub — `extract_feature_record` would
  then attempt real array ops on the stub and crash, not time anything. So the
  GPU-timing assertion (AC15) requires a genuine CuPy install and is
  `requires_cupy`-gated (AC14), skipping cleanly on this host — mirroring item
  073 AC7/AC6 and item 072 AC13/AC12. This item reuses item 073's **cupy-gating
  convention** (`pytest.mark.skipif(not cupy_available(), …)`); item 073's
  *numeric tolerance* (`rtol=1e-5, atol=1e-6`) is **not** relevant here, because
  the benchmark makes no CPU-vs-GPU numeric comparison — it only times.

- **A9 — GPU selection is guarded *before* `SEGQC_BACKEND=gpu` is ever set on a
  CuPy-absent host.** `run_benchmark` computes its backend list as `["cpu"]` +
  (`["gpu"]` iff `cupy_available()`); it never sets `SEGQC_BACKEND=gpu` when CuPy
  is absent (which would raise `SegQCBackendError`, item 071 AC7). This is what
  makes AC7 (clean GPU absence, no crash) hold unconditionally on this host.

- **A10 — Env-var hygiene / device sync.** The benchmark saves and restores any
  pre-existing `SEGQC_BACKEND` around its runs (so it never leaks a selection to
  the wider process/test suite); tests additionally use `monkeypatch` for the
  env where they set it. For accurate GPU timing (CuPy kernels are asynchronous),
  the GPU timed block synchronises the device (e.g.
  `cupy.cuda.Stream.null.synchronize()`) before stopping the timer — guarded so
  it is only referenced on the GPU path (never imported on the CPU-only host).

## Implementation Steps

Code path in `src/segqc` (see `aide.toml` → `project.source_dir`).

1. **Create `src/segqc/benchmark.py`** with a module docstring stating: the timed
   unit (`extract_feature_record`), the `SEGQC_BACKEND`-driven backend selection
   (A1), the no-absolute-timing / structural-correctness intent, the
   regenerate-not-commit policy (A6), and the CuPy-gated GPU path (A8/A9). Import
   only stdlib (`os`, `json`, `time`, `argparse`, `statistics`, `pathlib`) plus
   existing `segqc` modules at module scope — **never** `cupy` at module scope
   (AC1).
2. **Constants.** `BENCHMARK_VERSION = "1"`, `TIMED_UNIT = "extract_feature_record"`,
   `DEFAULT_ITERATIONS = 5`, `DEFAULT_WARMUP = 1`.
3. **Fixture loader** `_load_fixture(case_id) -> (seg_img, config, fixture_meta)`:
   iterate `segqc.synth.corpus.load_manifest()["cases"]`; select the requested
   `case_id` or (when `None`) the first case whose
   `segqc.synth.regression.loaded_seg_image(case)` has `>= 2` distinct non-zero
   labels; build `config = segqc.config.bundled_default_config()`; assemble
   `fixture_meta = {"source": "corpus", "case_id": …, "n_labels": …, "shape":
   list(seg_img.shape), "spacing_mm": [float(z) for z in
   seg_img.header.get_zooms()[:3]]}` (all JSON-native).
4. **Per-backend timing** `_time_backend(token, seg_img, config, *, iterations,
   warmup) -> dict`: save the current `SEGQC_BACKEND`; set it to `token`; run
   `warmup` untimed calls of `extract_feature_record(seg_img, config)`; then
   `iterations` timed calls via `time.perf_counter()` collecting `timings_s`
   (on the GPU path, synchronise the device before stopping each timer, A10);
   restore `SEGQC_BACKEND` in a `finally`; return the entry dict
   (`name`, `is_gpu = token == "gpu"`, `iterations`, `warmup`, `timings_s`,
   `min_s`, `mean_s = statistics.fmean`, `median_s = statistics.median`), all
   floats.
5. **`run_benchmark(*, case_id=None, iterations=DEFAULT_ITERATIONS,
   warmup=DEFAULT_WARMUP) -> dict`:** load the fixture; compute
   `tokens = ["cpu"] + (["gpu"] if segqc.backend.cupy_available() else [])`
   (A9); build `backends = [_time_backend(t, …) for t in tokens]`; assemble and
   return the full report dict per the schema (top-level `benchmark_version`,
   `timed_unit`, `iterations`, `warmup`, `cupy_available = cupy_available()`,
   `fixture`, `backends`).
6. **`write_report(report, out_path)`:** `Path(out_path).write_text(
   json.dumps(report, indent=2) + "\n", encoding="utf-8")` (or `json.dump`).
7. **`main(argv=None) -> int`:** argparse with `--out` (required), `--iterations`
   (int, default `DEFAULT_ITERATIONS`), `--warmup` (int, default
   `DEFAULT_WARMUP`), `--case` (str, default `None`); call `run_benchmark(...)`,
   `write_report(report, args.out)`, print a one-line human summary, return `0`.
   Add `if __name__ == "__main__": raise SystemExit(main())`.
8. **Export `__all__`** (`run_benchmark`, `write_report`, `main`,
   `BENCHMARK_VERSION`, `TIMED_UNIT`).
9. **No other production files change.** Do **not** touch `cli.py`,
   `pipeline.py`, `backend.py`, any `features/*.py`, or `pyproject.toml`
   (verify `[project].dependencies` unchanged — AC13).

## Testing Strategy

_The test-writer authors `tests/test_074_benchmark.py`; do **not** run `pytest`
as spec-author._ New module **`tests/test_074_benchmark.py`** (mirrors the
`test_0NN_*.py` convention). One focused test per AC; keep iteration counts tiny
(`iterations=2, warmup=1`) so the suite stays fast. Use `monkeypatch.setenv`/
`delenv` for any env manipulation so tests are hermetic.

- **AC1** — `import segqc.benchmark` under the ambient (CuPy-absent) condition;
  assert success and that `"cupy"` is not imported at module scope.
- **AC2** — `run_benchmark(iterations=2, warmup=1)` returns a `dict`, no raise.
- **AC3** — assert each required top-level key + type, `timed_unit ==
  "extract_feature_record"`, and each `backends` entry's required keys/types.
- **AC4** — exactly one `cpu` entry, `is_gpu is False`.
- **AC5** — every `cpu` `timings_s` sample `> 0`; `min_s`/`mean_s`/`median_s` `> 0`.
- **AC6** — `run_benchmark(iterations=3, warmup=1)`: `len(cpu["timings_s"]) == 3`,
  top-level `iterations == 3`, `warmup == 1`, entry `iterations == 3`.
- **AC7** — on this host: `report["cupy_available"] is False` and no `gpu` entry
  in `backends`; assert directly (no zero-timing GPU entry, no exception).
- **AC8** — `{b["name"] for b in backends} == ({"cpu"} if not cupy_available()
  else {"cpu", "gpu"})` (on this host, `== {"cpu"}`).
- **AC9** — `json.loads(json.dumps(report)) == report`.
- **AC10** — `main(["--out", str(tmp_path/"r.json"), "--iterations", "2",
  "--warmup", "1"])` returns `0`, file exists, `json.load` gives a schema-valid
  report with `cpu min_s > 0`.
- **AC11** — `fixture["source"] == "corpus"`, `case_id` non-empty,
  `n_labels >= 2`, `shape`/`spacing_mm` match a fresh `loaded_seg_image` of that
  case; assert (via the git diff / a repo scan) no new `.nii`/`.nii.gz` added.
- **AC12** — load the selected case's seg data, run `run_benchmark`, reload the
  same case; assert `np.array_equal` on the label arrays (read-only).
- **AC13** — parse `pyproject.toml` (tomllib); assert `[project].dependencies`
  contains no `cupy` and no dependency not already present pre-item.
- **AC14** — structural assertions on `requires_cupy`: `mark.name == "skipif"`,
  `isinstance(mark.args[0], bool)`, `mark.args[0] is True` on this host
  (mirror `tests/test_069_container_smoke.py`).
- **AC15** — `@requires_cupy`; when CuPy present, assert a `gpu` entry exists,
  `is_gpu is True`, `len(timings_s) == iterations`, all samples `> 0`,
  `cupy_available is True`. Skips cleanly here.

**Adversarial / edge cases to include:**
- **Env hygiene / no leak** — assert `SEGQC_BACKEND` is not left set in
  `os.environ` after `run_benchmark` returns (save/restore in a `finally`), so no
  backend selection leaks into other test modules.
- **`iterations=1`** boundary — a single timed sample still yields well-formed
  `min_s == mean_s == median_s == timings_s[0]`.
- **Explicit `--case`** — passing a known corpus `case_id` selects exactly that
  case in the `fixture` block.
- **Non-vacuity of the GPU gate** (AC14) — the truthy skip condition on this host
  is asserted directly, so "GPU timing passed" can never be reported when it was
  in fact skipped.
- **Determinism of *scope*** (not timing) — two `run_benchmark(iterations=2)`
  calls yield reports with identical structure/field-sets and identical `fixture`
  metadata (the timings differ, the schema and fixture identity do not).

## Dependencies

- **Item 071 — GPU/CPU backend abstraction (specced, NOT yet built; `📋` in
  `progress.md`).** Provides `segqc.backend.cupy_available()`, the `SEGQC_BACKEND`
  env var + `cpu`/`gpu`/`auto` vocabulary, and `SegQCBackendError`. The benchmark
  gates the GPU pass on `cupy_available()` and selects backends via
  `SEGQC_BACKEND`. Must land (✅/🚧) before item 074 is built; if the realised
  interface diverges from Assumption A1/A9, the builder hands back.
- **Item 072 — Port feature extraction to the backend (specced, NOT yet built;
  `📋`).** Provides the `backend=None → get_backend()` auto-resolution on the
  Stage-2/3 feature functions that `extract_feature_record` calls, so a
  `SEGQC_BACKEND`-selected backend actually reaches the (GPU-)ported compute the
  benchmark times, with no `pipeline.py` change. Must land (✅/🚧) before item
  074 is built; if `SEGQC_BACKEND` is not honoured through the unmodified
  `extract_feature_record`, the builder hands back (per A1). Per the queue
  sequencing, 074 can run in parallel with **073** once 072 lands.
- **Item 035 (✅)** — `segqc.pipeline.extract_feature_record` and
  `segqc.config.bundled_default_config`: the timed unit and its config.
- **Items 040/041 (✅)** — `segqc.synth.corpus.load_manifest` and
  `segqc.synth.regression.loaded_seg_image`: the committed-corpus fixture loader
  reused as the benchmark's default fixture (no new binary).
- **Item 069 (✅)** — `tests/test_069_container_smoke.py`'s genuine-skip proof:
  the precedent AC14 mirrors for the CuPy-gated timing marker.
- **Downstream (informational):** item 075 (Stage-10 integration/acceptance) may
  reference or re-run this benchmark and records the host's GPU/CuPy availability
  in its acceptance note; it owns the `segqc run --backend` CLI surface this item
  deliberately avoids.

## Decisions & Trade-offs

To be updated during implementation.
