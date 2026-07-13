# Item 075 — Stage 10 integration & acceptance closure

> **Created:** 2026-07-14 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 10 — Portable Compute: GPU Acceleration Path
> **Queue:** [`../queue/queue-009.md`](../queue/queue-009.md) · Item 075
> **Objectives:** G6 (Portable execution — identical results CPU-only; optional GPU acceleration path)
> **Suggested branch:** `aide/075-stage10-integration-acceptance`

---

## Description

Close Stage 10 by (a) **wiring backend selection into the `segqc` CLI** so a user
can pick `--backend cpu|gpu|auto` at the point of invocation, and (b) adding a
**Stage-10 acceptance check** that ties items 071–074 together into one coherent,
documented, testable path and records — at runtime — which of the roadmap's two
acceptance clauses (CPU-only, and CPU/GPU verdict-equivalence) were actually
exercised on the host that ran it.

**Part A — CLI `--backend` flag on all three feature-driving subcommands
(human-confirmed scope).** The queue names "`segqc run` (and any other CLI entry
points that invoke the ported feature-extraction code)". All three `segqc`
subcommands reach item 072's ported Stage-2/3 feature functions:

| Subcommand | Handler | Reaches ported feature code via |
|---|---|---|
| `segqc run` | `_handle_run` | `segqc.pipeline.run_qc` / `run_qc_with_reference` / `run_qc_with_intensity` → `extract_feature_record` |
| `segqc evaluate` | `_handle_evaluate` | `segqc.eval.harness.evaluate_cohort` → `run_qc` / `extract_feature_record` |
| `segqc build-reference` | `_handle_build_reference` | `segqc.reference.ingest` → `extract_feature_record` |

So the flag is added to **all three** subparsers uniformly. Each handler, before
it invokes its compute entry point, **eagerly validates/resolves** the requested
backend via item 071's `get_backend(override=<flag value>)` (fail-fast: a clean
`Error:` + exit 1 if GPU is forced but CuPy is unavailable, or the token is
invalid), then sets `os.environ["SEGQC_BACKEND"]` so the **unmodified**
`run_qc` / `extract_feature_record` / eval-harness / reference-ingest entry
points — which item 072 made auto-resolve `backend=None → get_backend()` at call
time — select the chosen backend with **no change to `pipeline.py`, the harness,
the ingest path, or any `features/*.py`**. This is exactly the env-var seam items
073 and 074 already rely on; item 075 just exposes it as a first-class CLI flag.

**Part B — Stage-10 acceptance check.** A test-side acceptance check that:

- **Unconditionally** asserts the roadmap's **CPU-only clause** — the full
  pipeline runs end-to-end under the CPU backend, producing a verdict with **zero
  GPU dependency** — and passes on every host (including this CuPy-absent one).
- **GPU-gated** asserts the roadmap's **CPU/GPU verdict-equivalence clause** —
  reusing item 073's verdict-equivalence mechanism — when CuPy/a GPU is genuinely
  present, and **skips cleanly** (never errors, never vacuously passes) when it is
  absent.
- Emits a **runtime evidence record** (printed to captured test output / returned
  by a helper) that states `cupy_available`, that the CPU clause was exercised
  (always `True`), and whether the GPU clause was exercised (`== cupy_available()`)
  — so the run's own output self-evidently records which of the two clauses were
  verified, rather than a stale committed host-specific note.

**What it is NOT (scope fence):**

- **No new numeric behaviour, heuristic, verdict, or report-schema change.** This
  item only routes an *existing* choice (which backend) to the CLI and asserts the
  stage's acceptance bar. It does not port more features to GPU (that was 072), add
  equivalence tests (073), or add a benchmark (074).
- **No `run_qc` / `extract_feature_record` / harness / ingest signature change.**
  The flag reaches the compute purely through the `SEGQC_BACKEND` environment
  variable (item 071/072's seam); the compute entry points stay untouched.
- **No `progress.md` edit by this item's direct-merge work, and no `roadmap.md`
  edit at all.** Reconciling `docs/aide/progress.md`'s Stage-10 section
  (deliverable bullets, acceptance checkboxes, summary status, G6 row) is the
  **validator's at-merge action via the `aide` CLI** — NOT a pytest-assertable AC
  — mirroring items 049/057/065/070 exactly. `roadmap.md` is a PR-gated framework
  file and is not touched.
- **No new dependency.** `cupy`/`cucim` remain optional (the `gpu` extra, item
  071); the flag and acceptance check add nothing to core `[project].dependencies`.
- **No `segqc benchmark` subcommand.** Item 074 deliberately kept the benchmark a
  standalone `python -m segqc.benchmark`; this item does not promote it to a
  subcommand.

## Acceptance Criteria

_Each criterion is atomic, observable, and directly testable — one focused test
per AC. AC1–AC9 and AC13/AC14 run and pass unconditionally on this CuPy-absent
host; AC10–AC12 concern the GPU-gated acceptance clause (AC10's skip, AC12's
structural skip-proof run here; AC10's positive GPU assertion runs only when CuPy
is present)._

- [ ] **AC1: `--backend cpu|gpu|auto` present on all three subcommands.**
  Parametrised over `run`, `evaluate`, and `build-reference`: each subparser
  exposes a `--backend` option whose accepted values are **exactly** `{"cpu",
  "gpu", "auto"}` and whose default is the sentinel meaning "flag not given"
  (`None`), documented to the user as behaving like `auto`. (Verifiable by
  introspecting `_build_parser()` / parsing `--help`.)

- [ ] **AC2: Invalid `--backend` token is a usage error.** Parametrised over the
  three subcommands: an unrecognised value (e.g. `segqc run … --backend turbo`)
  raises the argparse usage error (`SystemExit` with code `2`) via the `choices`
  constraint — it does not start a run.

- [ ] **AC3: Explicit `--backend` is eagerly validated/resolved via
  `get_backend(override=…)` before the compute runs.** For each subcommand,
  invoking `main([...,"--backend","cpu"])` calls `segqc.backend.get_backend` with
  `override="cpu"` **before** the compute entry point is reached — verifiable by a
  spy/monkeypatch on `segqc.backend.get_backend` asserting it was consulted with
  that override.

- [ ] **AC4: Explicit `--backend` selects the backend for the unmodified compute
  path via `SEGQC_BACKEND`.** When `--backend cpu` is given, `os.environ[
  "SEGQC_BACKEND"] == "cpu"` at the moment the **unmodified** compute entry point
  is invoked — verifiable by a spy on that entry point (`run_qc` for `run`,
  `evaluate_cohort` for `evaluate`, `build_reference` for `build-reference`) that
  records `os.environ.get("SEGQC_BACKEND")` at call time and finds `"cpu"`.

- [ ] **AC5: Forcing GPU without CuPy fails cleanly (Error + exit 1, no output
  written).** Parametrised over the three subcommands on this CuPy-absent host:
  `--backend gpu` prints `Error: <non-empty message>` to **stderr** and returns
  exit code `1` (the eager `get_backend` raises `SegQCBackendError`, caught per the
  established `_handle_*` convention) — **not** a bare traceback, **not** exit `0`,
  and no report/artifact file is written.

- [ ] **AC6: Flag omitted + `SEGQC_BACKEND` unset → env untouched, auto governs,
  no behaviour change.** With `--backend` omitted and `SEGQC_BACKEND` absent from
  the environment, the handler does **not** set `SEGQC_BACKEND` (it is still unset
  when the compute entry point is invoked), the run auto-resolves to CPU on this
  host, and it completes end-to-end exactly as before the flag existed (both
  reports written; exit code driven by the verdict, not by backend selection).

- [ ] **AC7: Flag omitted + ambient `SEGQC_BACKEND` set → ambient value governs
  (not clobbered).** With `--backend` omitted and `SEGQC_BACKEND=cpu` preset in
  the environment, the handler leaves it intact; the compute entry point observes
  `SEGQC_BACKEND == "cpu"` at call time, and the variable is unchanged after the
  run (the CLI flag defers to the ambient env when the flag is not given).

- [ ] **AC8: End-to-end CPU run needs zero GPU dependency.** `segqc run --backend
  cpu` over a committed scan+seg fixture runs to completion, writing both
  `<out>/segqc_report.json` and `<out>/segqc_report.txt`, on this host where
  `cupy` is not installed — and `cupy` is never imported during the run
  (`"cupy" not in sys.modules` afterwards) — demonstrating the tool runs fully
  CPU-only (**G6**).

- [ ] **AC9: Stage-10 acceptance check — CPU clause holds unconditionally.** The
  acceptance check asserts the CPU-only clause (the full pipeline produces a
  verdict under the CPU backend with no GPU present); this assertion **executes and
  passes** on this CuPy-absent host (and is written to hold on every host).

- [ ] **AC10: Stage-10 acceptance check — GPU-equivalence clause is gated.** The
  acceptance check's GPU-equivalence assertion (CPU-vs-GPU verdict identity, reusing
  item 073's verdict-signature mechanism over a representative fixture) is gated on
  `cupy_available()`: it **runs and asserts equivalence when CuPy is importable**,
  and **skips cleanly** (never errors, never vacuously passes) when CuPy is absent —
  on this host it skips.

- [ ] **AC11: Acceptance evidence records which clause was exercised.** The
  acceptance check produces a runtime evidence record (printed to captured test
  output and returned by an importable helper) reporting at least
  `cupy_available` (`bool`), `cpu_clause_exercised` (always `True`), and
  `gpu_clause_exercised` (`bool`). The check asserts `cpu_clause_exercised is True`
  and `gpu_clause_exercised == cupy_available()`, so the run's own output states
  plainly which of the two roadmap clauses were verified on this host.

- [ ] **AC12: The GPU acceptance gate is a genuine skip marker.** The marker
  gating the GPU-equivalence acceptance test is a real `pytest.mark.skipif` whose
  `mark.name == "skipif"` and whose condition `mark.args[0]` is a `bool` that is
  `True` on this CuPy-absent host — never `xfail`, never an unconditional pass —
  mirroring `tests/test_069_container_smoke.py`'s genuine-skip precedent (and items
  073 AC6 / 074 AC14). Proves the GPU clause is *cleanly skipped* here, not
  silently green.

- [ ] **AC13: No new core dependency; CPU-only install unaffected.**
  `pyproject.toml`'s `[project].dependencies` still contains neither `cupy` nor
  `cucim`; adding the `--backend` flag and the acceptance check introduces no new
  runtime dependency.

- [ ] **AC14: Existing CLI behaviour is unchanged when the flag is absent
  (regression guard).** The pre-existing `run` / `evaluate` / `build-reference`
  CLI tests pass **unchanged** — the `--backend` option is optional with a
  `None`/omitted default, so no existing invocation, exit code, or written report
  changes.

## Assumptions  <!-- MANDATORY: pins items 071–074's still-unbuilt interfaces + the confirmed decisions -->

- **A1 — All three subcommands get the flag [human-confirmed, Q1].** The queue's
  "any other CLI entry points that invoke the ported feature-extraction code" is
  resolved to `segqc run`, `segqc evaluate`, **and** `segqc build-reference`
  uniformly — all three reach item 072's ported Stage-2/3 feature functions (see
  the Description table). Not `run` alone. (The standalone `python -m
  segqc.benchmark`, item 074, already gates GPU internally and is not a `segqc`
  subcommand, so it is out of this flag's scope.)

- **A2 — Env-var wiring is the mechanism [confirmed]; the compute entry points are
  never modified.** The `--backend` option has `default=None` (sentinel: "flag not
  given"). When a value **is** given, the handler calls
  `segqc.backend.get_backend(override=<value>)` eagerly to validate/resolve
  (fail-fast on a forced-but-unavailable GPU or an invalid token), then sets
  `os.environ["SEGQC_BACKEND"] = <value>` and calls the **unmodified**
  `run_qc` / `extract_feature_record` / `evaluate_cohort` / `build_reference`,
  which auto-resolve `backend=None → get_backend()` reading that env var (item
  072). When the flag is **omitted** (`None`) the handler leaves `SEGQC_BACKEND`
  untouched so the ambient env var / `auto` governs (AC6/AC7). **Why the env var
  and not a `run_qc`/`extract_feature_record` parameter:** item 072's feature
  functions gained a `backend=None` keyword that auto-resolves via `get_backend()`,
  but `run_qc`/`extract_feature_record`/the harness/ingest were **not** given a
  backend parameter to thread; the env var is therefore the only seam that reaches
  them without editing them — the exact mechanism items 073 (A1) and 074 (A1)
  depend on.

- **A3 — Precedence of an explicit flag over an ambient env var [confirmed].**
  Setting `os.environ["SEGQC_BACKEND"]` from the flag means an explicit
  `--backend auto` (or `cpu`/`gpu`) **overrides** any pre-existing ambient
  `SEGQC_BACKEND`, matching item 071's designed precedence (explicit argument > env
  var > default `auto`, item 071 A1). Omitting the flag defers to the ambient env
  var (AC7). This is the intended, documented behaviour, not a leak.

- **A4 — Eager validation is unconditional; env-setting is conditional.** The
  handler always calls `get_backend(override=getattr(args,"backend",None))` early
  (so even a bad *ambient* `SEGQC_BACKEND` — e.g. `gpu` on a CuPy-absent host —
  surfaces as a clean `Error:` + exit 1 rather than a mid-pipeline traceback), but
  only writes `os.environ["SEGQC_BACKEND"]` when the flag was explicitly given.
  For the normal case (flag omitted, env unset) this resolves to CPU and changes
  nothing observable (AC6). Eagerly resolving `override="gpu"` on a GPU host builds
  a `Backend` (importing `cupy`) that is then discarded — cheap, and the downstream
  path re-resolves identically.

- **A5 — Item 071 interface pinned (specced, NOT yet built — hand back if
  diverged).** Consumed: `get_backend(override=None) -> Backend`,
  `cupy_available() -> bool`, `SegQCBackendError`, the `SEGQC_BACKEND` env var and
  its `cpu`/`gpu`/`auto` vocabulary, and the precedence explicit-arg > env >
  `auto`. If the realised module raises a different type on a forced-but-absent
  GPU, does not honour `SEGQC_BACKEND`, or names these differently, the item-075
  builder **hands back** rather than guessing.

- **A6 — Item 072 interface pinned (specced, NOT yet built — hand back if
  diverged).** Consumed: `run_qc` / `extract_feature_record` (and the harness /
  reference-ingest paths that call them) resolve `backend=None → get_backend()` at
  call time, so a `SEGQC_BACKEND`-selected backend reaches the ported compute with
  **no** change to `pipeline.py`, the harness, or the ingest path. If item 072
  landed such that `SEGQC_BACKEND` is *not* honoured through the unmodified
  entry points, the builder hands back (the flag would then have no effect).

- **A7 — Item 073 mechanism reused for the GPU acceptance clause (specced, NOT yet
  built — hand back if diverged).** The GPU-equivalence acceptance assertion
  (AC10) reuses item 073's verdict-equivalence approach: select the backend via
  `SEGQC_BACKEND=cpu`/`gpu` around an unmodified `run_qc`, compare a categorical
  **verdict signature** (`overall.label` + the findings set) across backends, and
  gate on `cupy_available()` with a genuine `skipif` marker (item 073 A1/A5,
  AC6/AC7). Preferred: import item 073's `verdict_signature` /`requires_cupy`
  helper from `tests/test_073_verdict_equivalence.py`; acceptable equivalent:
  replicate the minimal signature comparison in this item's acceptance module. If
  item 073's helper names differ at build time, the builder adapts or replicates
  (no production coupling either way — item 073 is tests-only). Item 074
  (benchmark) is informational here: the acceptance evidence may *mention* the
  host's CuPy state but does not run the benchmark.

- **A8 — Runtime-output acceptance evidence, NOT a committed host-specific note
  [confirmed].** The "explicitly record whether the host had a GPU/CuPy" bar is met
  by emitting the evidence record at **runtime** (printed to captured pytest output
  + returned by an importable helper, asserted structurally on `cupy_available()`),
  **not** by committing a note file. Rationale mirrors item 074 A6: the host's GPU
  state is machine-specific and non-deterministic, so a committed note would go
  stale and could never be byte-identity-tested; the run's own output is the honest
  record of which clause it exercised.

- **A9 — `progress.md` reconciliation is a validator-at-merge action, not a pytest
  AC [049/057/065/070 precedent].** Updating `docs/aide/progress.md`'s Stage-10
  section — the five deliverable bullets (071–075) to ✅, the two acceptance
  checkboxes, the stage summary status, and the G6 objective-coverage row (line 49)
  — is performed by the **validator via the `aide` CLI at merge**, exactly as for
  the Stage-6/7/8/9 closers (items 049/057/065/070). It is deliberately **not**
  encoded as an acceptance criterion (a spec cannot pytest-assert its own
  progress-doc bookkeeping). `roadmap.md` (PR-gated framework file) is **not**
  edited by this item.

- **A10 — Fixture reuse, no new binaries.** The end-to-end CPU run (AC8) and the
  acceptance CPU/GPU clauses reuse existing committed fixtures: the CLI scan+seg
  fixtures already used by the Stage-1/4 `run` CLI tests, and/or the Stage-5 corpus
  + Stage-0 synthetic builders item 073 uses. No new `.nii`/`.nii.gz` is added.

- **A11 — Process-scoped env mutation is intended; tests stay hermetic.** Setting
  `os.environ["SEGQC_BACKEND"]` persists for the remainder of the short-lived CLI
  process (the intended effect). Tests that exercise the handlers must use
  `monkeypatch.setenv`/`delenv` (and `monkeypatch` for the parser/`os.environ`) so
  no selection leaks across tests.

## Implementation Steps

Code path in `src/segqc` (see `aide.toml` → `project.source_dir`). The only
production edits are to **`src/segqc/cli.py`**; the compute modules are untouched.

1. **`cli.py` — add the flag to all three subparsers.** In `_build_parser()`, add
   to `run_parser`, `evaluate_parser`, and `build_reference_parser` an identical:
   ```
   <sub>_parser.add_argument(
       "--backend",
       default=None,
       choices=["cpu", "gpu", "auto"],
       metavar="<cpu|gpu|auto>",
       help=("Compute backend for feature extraction: 'cpu' (NumPy/SciPy), "
             "'gpu' (CuPy; requires the optional gpu extra + a CUDA device), or "
             "'auto' (GPU when available, else CPU). Omitted = auto (today's "
             "default); forcing gpu without CuPy exits 1 with a clear error."),
   )
   ```
2. **`cli.py` — shared selection helper.** Add a module-level
   `_apply_backend_selection(args) -> Optional[int]`:
   - `import os` (module top) and a **deferred** `from segqc.backend import
     get_backend, SegQCBackendError` inside the helper (matching the deferred-import
     convention that keeps `segqc --help` fast/import-clean).
   - `tok = getattr(args, "backend", None)`.
   - `try: get_backend(override=tok)  except SegQCBackendError as exc: print(
     f"Error: {exc}", file=sys.stderr); return 1` — eager validation/resolution
     (AC3, AC5), fail-fast before any input is loaded.
   - `if tok is not None: os.environ["SEGQC_BACKEND"] = tok` (AC4); leave it
     untouched when `tok is None` (AC6/AC7).
   - `return None` to signal "continue".
3. **`cli.py` — call the helper early in each handler.** Near the top of
   `_handle_run`, `_handle_evaluate`, and `_handle_build_reference` (after
   `setup_logging` where present, and **before** loading inputs / config so a
   forced-GPU error fails fast):
   `code = _apply_backend_selection(args); if code is not None: return code`.
4. **Do NOT modify the compute path.** Leave `pipeline.py` (`run_qc`,
   `run_qc_with_reference`, `run_qc_with_intensity`, `extract_feature_record`),
   `eval/harness.py` (`evaluate_cohort`), `reference/ingest.py`, `backend.py`, and
   every `features/*.py` untouched — the flag reaches them solely through
   `SEGQC_BACKEND` (item 072's auto-resolution).
5. **Acceptance check — `tests/test_075_stage10_acceptance.py`.** Author (test
   side) a module with:
   - A `requires_cupy = pytest.mark.skipif(not cupy_available(), reason="CuPy/GPU
     not available")` marker (import `cupy_available` from `segqc.backend`).
   - An importable helper `stage10_acceptance_record(*, gpu_ran: bool) -> dict`
     returning `{"cupy_available": cupy_available(), "cpu_clause_exercised": True,
     "gpu_clause_exercised": gpu_ran}` (JSON-native), plus a test that `print`s it
     (captured runtime evidence, A8).
   - **CPU clause (unconditional, AC9/AC11):** run the full pipeline under
     `SEGQC_BACKEND=cpu` (via `monkeypatch.setenv`) on a representative fixture,
     assert a verdict is produced with no GPU present; build + assert the evidence
     record (`cpu_clause_exercised is True`, `gpu_clause_exercised ==
     cupy_available()`).
   - **GPU clause (gated, AC10):** `@requires_cupy`; reuse item 073's
     `verdict_signature` mechanism to assert CPU-vs-GPU verdict identity on the same
     fixture; skips cleanly on this host.
   - **Structural skip proof (AC12):** assert the `requires_cupy` marker is a real
     `skipif` with a `bool` condition `True` here (mirror
     `tests/test_069_container_smoke.py`).
6. **CLI wiring tests — `tests/test_075_cli_backend.py`.** Author (test side) the
   AC1–AC8, AC13, AC14 tests (flag surface, eager validation, env wiring, clean
   GPU-force failure, omitted-flag no-op, CPU-only end-to-end, no-new-dep,
   regression guard).
7. **`pyproject.toml` unchanged.** Verify `[project].dependencies` gains nothing
   (AC13); the `gpu` extra from item 071 is the only GPU surface.
8. **No `progress.md` / `roadmap.md` edits here** (A9) — the validator reconciles
   `progress.md` Stage 10 at merge via the `aide` CLI.

## Testing Strategy

_The spec-author does not run `pytest`. The test-writer authors both modules; the
builder edits only `cli.py`; the validator runs the full suite and reconciles
`progress.md`._ Two modules, mirroring the `test_0NN_*.py` convention. All GPU
behaviour is `cupy_available()`/`importorskip`-gated and skips cleanly on this
CuPy-absent host. Use `monkeypatch.setenv`/`delenv`/`setattr` for hermetic env and
spy handling.

**`tests/test_075_cli_backend.py`** — one focused test per AC (AC1–AC8, AC13, AC14):

- **AC1** — parametrise over `{"run","evaluate","build-reference"}`; introspect
  `_build_parser()` (or `--help`) and assert each subparser's `--backend` action
  has `choices == ["cpu","gpu","auto"]` and `default is None`.
- **AC2** — parametrise; `main([sub, …valid required args…, "--backend","turbo"])`
  raises `SystemExit` with code `2`.
- **AC3** — parametrise; monkeypatch `segqc.backend.get_backend` to a spy (returning
  a CPU `Backend`); run each subcommand with `--backend cpu`; assert the spy was
  called with `override="cpu"`.
- **AC4** — parametrise; spy on the subcommand's compute entry (`segqc.pipeline.run_qc`
  for `run`, `segqc.eval.harness.evaluate_cohort` for `evaluate`,
  `segqc.reference.artifact.build_reference` for `build-reference`) recording
  `os.environ.get("SEGQC_BACKEND")` at call time; run with `--backend cpu`; assert
  the recorded value is `"cpu"`.
- **AC5** — parametrise over the three subcommands on this host; `--backend gpu`;
  capture stderr + exit code; assert exit `1`, stderr starts `Error:` and is
  non-empty, no report/artifact file was written to `--out`, and the raised path
  was **not** a bare traceback (`SegQCBackendError` was caught).
- **AC6** — `monkeypatch.delenv("SEGQC_BACKEND", raising=False)`; run `segqc run`
  **without** `--backend` on a scan+seg fixture; spy on `run_qc` asserts
  `os.environ.get("SEGQC_BACKEND") is None` at call time; both reports written;
  `SEGQC_BACKEND` still absent afterwards.
- **AC7** — `monkeypatch.setenv("SEGQC_BACKEND","cpu")`; run `segqc run` **without**
  `--backend`; spy on `run_qc` asserts it saw `"cpu"`; env value unchanged after.
- **AC8** — `segqc run --backend cpu` over a committed scan+seg fixture to a
  `tmp_path` `--out`; assert both `segqc_report.json`/`.txt` exist and
  `"cupy" not in sys.modules` afterwards (this host has no CuPy).
- **AC13** — parse `pyproject.toml` (tomllib); assert `[project].dependencies` has
  no `cupy`/`cucim` and gained nothing versus pre-item.
- **AC14** — a meta-check that existing `run`/`evaluate`/`build-reference` CLI
  tests are unmodified (the validator runs the full suite); optionally re-invoke a
  representative existing no-`--backend` invocation and assert identical exit code +
  report bytes to the pre-flag behaviour.

**`tests/test_075_stage10_acceptance.py`** — the acceptance check (AC9–AC12):

- **AC9** — under `SEGQC_BACKEND=cpu`, drive the full pipeline (`run_qc`) on a
  representative fixture; assert a verdict is produced (CPU clause holds); runs on
  this host.
- **AC10** — `@requires_cupy`; assert CPU-vs-GPU verdict-signature identity
  (item 073 mechanism); skips cleanly here.
- **AC11** — build `stage10_acceptance_record(gpu_ran=…)`; assert
  `cpu_clause_exercised is True` and `gpu_clause_exercised == cupy_available()`;
  a companion test `print`s the record so the run's captured output records the
  host's clause coverage (A8).
- **AC12** — structural: `requires_cupy.mark.name == "skipif"`,
  `isinstance(requires_cupy.mark.args[0], bool)`, `... is True` on this host
  (mirror `tests/test_069_container_smoke.py`).

**Adversarial / edge cases to include:**
- **Env hygiene / no leak** — after each handler test, `SEGQC_BACKEND` is not left
  mutated in `os.environ` (monkeypatch teardown); assert directly for at least one
  case.
- **`--backend auto` explicit vs ambient env** — explicit `--backend auto` with
  `SEGQC_BACKEND=cpu` preset sets the env to `auto` (explicit flag wins, A3);
  assert the compute path saw `"auto"` (which auto-resolves to CPU here), proving
  precedence.
- **Guard-before-GPU-selection** — AC5's `--backend gpu` on a CuPy-absent host must
  fail at the eager `get_backend` step **before** any input is loaded / any report
  is written (assert no `--out` files created).
- **Non-vacuity of the acceptance evidence** — assert the record genuinely tracks
  `cupy_available()` (on this host both `cupy_available` and `gpu_clause_exercised`
  are `False`, `cpu_clause_exercised` is `True`), so "GPU clause verified" can never
  be reported when the GPU clause was in fact skipped.
- **Bad ambient env, flag omitted** — `SEGQC_BACKEND=gpu` preset (CuPy absent) with
  no `--backend`: the eager validation (A4) surfaces a clean `Error:` + exit 1
  rather than a mid-pipeline traceback.

## Dependencies

- **Item 071 — GPU/CPU backend abstraction (specced, NOT yet built; `📋`).**
  Provides `get_backend(override=None) -> Backend`, `cupy_available()`,
  `SegQCBackendError`, and the `SEGQC_BACKEND` env var + `cpu`/`gpu`/`auto`
  vocabulary the flag validates against and sets. Must land (✅/🚧) first; hand
  back if the interface diverges (A5).
- **Item 072 — Port feature extraction to the backend (specced, NOT yet built;
  `📋`).** Provides the `backend=None → get_backend()` auto-resolution on the
  Stage-2/3 feature functions that `run_qc` / `extract_feature_record` /
  `evaluate_cohort` / reference-ingest call, so a `SEGQC_BACKEND`-selected backend
  reaches the compute with no `pipeline.py`/harness/ingest change. Must land
  (✅/🚧) first; hand back if `SEGQC_BACKEND` is not honoured through those
  entry points (A6).
- **Item 073 — CPU-vs-GPU verdict-equivalence suite (specced, NOT yet built;
  `📋`).** Provides the `verdict_signature` comparison + `requires_cupy` genuine-
  skip mechanism the acceptance check's GPU clause reuses (A7). Must land before
  item 075 is built (per the queue sequencing, 075 depends on everything). Tests-
  only, so no production coupling; if helper names differ, the builder adapts.
- **Item 074 — Performance benchmark (specced, NOT yet built; `📋`).**
  Informational only: the acceptance evidence records the host's CuPy state but
  does not run the benchmark; item 074's `cupy_available()`-gating convention is
  the same one reused here.
- **Item 035 (✅)** — `segqc.pipeline.{run_qc, extract_feature_record}` and
  `bundled_default_config`, and the `segqc run` CLI handler the flag wires into.
- **Item 057 (✅)** — `_handle_evaluate` / `segqc.eval.harness.evaluate_cohort`,
  the second flag target and the closest closer-precedent for progress
  reconciliation.
- **Item 045 (✅)** — `_handle_build_reference` / `segqc.reference.artifact.build_reference`
  and `segqc.reference.ingest` (→ `extract_feature_record`), the third flag target.
- **Item 069 (✅)** — `tests/test_069_container_smoke.py`'s genuine-skip proof, the
  precedent AC12 mirrors for the CuPy-gated acceptance marker.
- **Items 049 / 057 / 065 / 070 (✅)** — the Stage-6/7/8/9 closers whose
  `progress.md`-reconciliation-at-merge / no-`roadmap.md`-edit precedent this item
  follows exactly (A9).

## Decisions & Trade-offs

To be updated during implementation.
