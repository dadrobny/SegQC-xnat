# Item 005 — Structured Logging & Versioned Heuristic-Config Scaffold

> **Status:** 📋 Planned · **Created:** 2026-06-25
> **Stage:** 0 — Project Scaffolding & I/O Foundation
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 005
> **Objectives:** Foundation (reproducibility + config plumbing for G2, G4)
> **Suggested branch:** `aide/005-structured-logging`

---

## Description

Add **structured logging** (configurable level, machine-parseable where useful)
and a **versioned heuristic-config scaffold** (YAML or JSON) with a loader,
schema version field, and sensible defaults. No heuristics yet — just the config
plumbing that Stage 4 will populate, plus reproducibility hooks (the config
version is recorded in JSON outputs).

### What "structured logging" means here

- A single `logging.getLogger("segqc")` hierarchy; all `segqc.*` loggers are
  children so a caller can configure the top-level logger once.
- Log level selectable at runtime (initially via `setup_logging(level)` in code;
  the CLI flag `--log-level` is wired in Item 006).
- A structured formatter that emits JSON lines (one JSON object per record) when
  requested — machine-parseable, useful for XNAT/container logs and for test
  assertions. The human-readable default stays plain text.
- A `segqc.logging` (or `segqc._logging`) sub-module that other modules import
  cheaply — no heavy transitive deps, no global side-effects on import.

### What "versioned heuristic-config scaffold" means here

- A **YAML** config file format (preferred; requires `PyYAML`, already a common
  dep in scientific Python; may fall back to JSON if we decide not to add
  `PyYAML` — see Decisions).
- A `schema_version` field that the loader validates; if the loaded file's version
  is unsupported, raise a clear `SegQCConfigError`.
- Sensible **defaults** baked into code so a missing key is filled in rather than
  crashing — the Stage 4 heuristic thresholds will live here; for now the defaults
  section is a documented placeholder.
- A `HeuristicConfig` dataclass (or typed dict) that the loader returns; callers
  (Stage 4 rule engine; Item 007 empty-check thresholds; Item 009 report
  serialiser) access fields by name rather than string-keying a raw dict.
- The loaded `schema_version` is surfaced on `HeuristicConfig` so JSON report
  serialisers (Item 009) can embed it for reproducibility.

### Scope boundary (what this item does *not* do)

| Concern | Owned by | This item |
|---|---|---|
| CLI `--log-level` flag wiring | Item 006 | exposes `setup_logging(level)` — **not** wired into `cli.py` here |
| Empty/near-empty thresholds (min voxels, min labels) | Item 007 | ships placeholder defaults; adds the fields when 007 is spec'd |
| Per-vertebra heuristic thresholds (bounds, rules) | Stage 4 | the config schema has **no** heuristic entries yet — just `schema_version` and empty/near-empty stubs |
| JSON report serialiser | Item 009 | exposes `config.schema_version`; serialiser decides how to embed it |
| Label-convention override | Item 004 integration | config *may* carry an optional `label_map` section; initial scaffold may leave it as a placeholder |

---

## Acceptance Criteria

- [ ] A `segqc.logging` (or `segqc._logging`) sub-module exists exposing
      `setup_logging(level: str | int, *, json_format: bool = False) -> None` that
      configures the `"segqc"` logger hierarchy without global side-effects on
      import.
- [ ] The plain-text handler emits `%(levelname)s  %(name)s — %(message)s` (or
      similar) to `stderr`; the JSON handler emits one JSON object per record
      containing at minimum `time`, `level`, `logger`, and `message` fields.
- [ ] A `segqc.config` sub-module exists exposing:
  - `SegQCConfigError(Exception)` — raised on unsupported / malformed configs.
  - `HeuristicConfig` — a typed dataclass holding `schema_version: str` plus
    placeholder fields for empty-detection thresholds (to be populated in Item
    007).
  - `load_config(path: str | Path) -> HeuristicConfig` — reads YAML (or JSON),
    validates `schema_version`, fills in defaults for missing keys, and returns a
    `HeuristicConfig`.
  - `default_config() -> HeuristicConfig` — returns the baked-in defaults without
    reading any file (useful for tests and for callers that don't need a config
    file).
- [ ] `load_config` raises `SegQCConfigError` with a clear message when:
  - The file contains an unsupported `schema_version` (tested for both a future
    version and a past/incompatible one — Decision: what counts as "unsupported").
  - The file is syntactically invalid YAML/JSON.
  - The file does not exist (or a clear `FileNotFoundError` / `SegQCConfigError`
    wrapping it — see Decisions).
- [ ] Missing keys in the config file are silently filled from the coded defaults
      (no crash on a minimal config with only `schema_version`).
- [ ] `HeuristicConfig.schema_version` is accessible to downstream callers (Item
      009 embeds it in reports).
- [ ] Unit tests (in `tests/test_config.py`) cover:
  - Loading a minimal valid YAML (only `schema_version`); defaults applied.
  - Loading a full valid YAML with all current fields explicit; values
    round-trip.
  - Unsupported `schema_version` → `SegQCConfigError`.
  - Syntactically invalid YAML → `SegQCConfigError`.
  - Missing file → `SegQCConfigError` (or `FileNotFoundError` per Decision).
  - `default_config()` returns a valid `HeuristicConfig` with correct
    `schema_version`.
- [ ] Unit tests (in `tests/test_logging_setup.py`) cover:
  - `setup_logging("DEBUG")` and `setup_logging("WARNING")` do not raise.
  - After `setup_logging("DEBUG", json_format=False)`, emitting a log record via
    `logging.getLogger("segqc.test")` produces text to `stderr` (captured with
    `capfd` or `caplog`).
  - After `setup_logging("DEBUG", json_format=True)`, the handler produces a
    valid JSON line for each record.
  - Calling `setup_logging` twice does not duplicate handlers (idempotency).
- [ ] Pure-Python, CPU-only. The only permitted new runtime dependency is `PyYAML`
      (if YAML is chosen — see Decisions). No NiBabel/SciPy/skimage imports.
      Identical behaviour on Windows/macOS/Linux.

---

## Implementation Steps

1. **Decide YAML vs JSON for the config format** (see Decisions). Likely YAML
   (`PyYAML`). Check whether `PyYAML` is already in `pyproject.toml`; add it if
   not.
2. **Author `src/segqc/_logging.py`** (or `logging_setup.py` — see Decisions for
   module name):
   - `setup_logging(level, *, json_format=False)` configures the `"segqc"`
     logger: sets level, installs a `StreamHandler` to `sys.stderr`, and attaches
     either a plain `logging.Formatter` or a custom `JsonFormatter`.
   - `JsonFormatter` subclasses `logging.Formatter`, overriding `format` to emit
     a JSON-serialised dict (`{"time": ..., "level": ..., "logger": ...,
     "message": ...}`).
   - Guard against duplicate handlers: if `setup_logging` is called again, clear
     existing handlers on the `"segqc"` logger before re-adding.
   - No module-level side-effects: calling `import segqc._logging` must not set
     up any handlers.
3. **Decide `schema_version` semantics** (see Decisions). Likely:
   `SUPPORTED_SCHEMA_VERSION = "0.1"` in the module; any file whose
   `schema_version` does not match raises `SegQCConfigError`. Document the
   decision.
4. **Author `src/segqc/config.py`**:
   - `SegQCConfigError(Exception)` with a descriptive message.
   - `HeuristicConfig` — frozen `@dataclass` with:
     - `schema_version: str`
     - Placeholder empty-detection fields (to be populated in Item 007):
       `min_foreground_voxels: int = 0` and `min_label_count: int = 0` (or
       similar — exact names will be decided in Item 007; here they are stubs).
   - `_DEFAULTS` — a module-level `dict` of all default field values (single
     source of truth for `default_config()` and the merge logic in `load_config`).
   - `default_config() -> HeuristicConfig` — returns
     `HeuristicConfig(**_DEFAULTS)`.
   - `load_config(path) -> HeuristicConfig`:
     - Read the file, parse YAML/JSON, catch parse errors → `SegQCConfigError`.
     - Extract and validate `schema_version`; if absent or unsupported →
       `SegQCConfigError`.
     - Deep-merge file values over `_DEFAULTS` (file wins for present keys,
       defaults fill missing ones).
     - Return `HeuristicConfig(**merged)`.
5. **Add a sample config fixture** for tests: a tiny YAML string (in-memory or
   `tmp_path` file) with only `schema_version`. This is the "minimal valid" case.
6. **Write `tests/test_config.py`** (6+ tests per Acceptance Criteria).
7. **Write `tests/test_logging_setup.py`** (4+ tests per Acceptance Criteria).
8. **Update `pyproject.toml`** if `PyYAML` (or another new dep) is added.
9. **Verify** the manual validation checklist (clean venv, `pytest`, REPL check).

---

## Testing Strategy

- **Framework:** `pytest` (item 001 harness). No service dependencies.
- **Fixtures:**
  - `tmp_path` (built-in pytest fixture) for on-disk YAML files.
  - Inline YAML strings passed to `io.StringIO` / written to `tmp_path` for
    parametrised load cases.
  - `caplog` and/or `capfd` for log-output assertions.
  - Item 002 synthetic NIfTI fixtures are **not** needed here (config and logging
    are orthogonal to the NIfTI pipeline).
- **Tests (illustrative):**
  - `test_default_config_is_valid` — `default_config()` returns a `HeuristicConfig`
    with the expected `schema_version` and all placeholder fields at their defaults.
  - `test_load_minimal_yaml` — a config file containing only `schema_version`
    loads cleanly; all other fields take default values.
  - `test_load_all_fields_yaml` — a config file with every current field explicit
    round-trips the values exactly.
  - `test_load_unsupported_version_raises` — a config with a different
    `schema_version` raises `SegQCConfigError`.
  - `test_load_malformed_yaml_raises` — syntactically broken YAML raises
    `SegQCConfigError`.
  - `test_load_missing_file_raises` — a path to a non-existent file raises
    `SegQCConfigError` (or `FileNotFoundError` per Decision).
  - `test_setup_logging_plain_no_raise` — `setup_logging("DEBUG")` completes
    without error.
  - `test_setup_logging_json_emits_valid_json` — after
    `setup_logging("DEBUG", json_format=True)`, a log call produces a parseable
    JSON line on stderr.
  - `test_setup_logging_plain_emits_text` — after
    `setup_logging("DEBUG", json_format=False)`, a log call produces non-JSON text.
  - `test_setup_logging_idempotent` — calling `setup_logging` twice does not
    install duplicate handlers on the `"segqc"` logger.
- **Determinism / portability:** all inputs are in-process (YAML strings / temp
  files); no network, no GPU. Pure-Python — identical on Windows/macOS/Linux.

---

## Dependencies

- **Upstream (blocks this item):**
  - Item 001 (package skeleton, `pyproject.toml`, pytest) — **complete**.
  - Item 002 (synthetic fixtures) — **complete**, though not strictly needed here.
  - Item 003 (loader, `SegQCInputError`) — **complete**; this item may re-use
    the error-handling pattern but adds its own `SegQCConfigError`.
  - Item 004 (label-convention) — **complete**.
- **Not a dependency:** Items 006–010 (not yet started; this item unblocks them).
- **New runtime dependency (if YAML chosen):** `PyYAML` — lightweight, widely
  present in scientific Python environments; add to `pyproject.toml` under
  `[project.dependencies]`.
- **Downstream (this item unblocks or partially enables):**
  - Item 006 (CLI `run`): will call `setup_logging` and, optionally,
    `load_config`; needs `--log-level` and (optionally) `--config` flags.
  - Item 007 (empty/near-empty detection): empty-check thresholds live in
    `HeuristicConfig`; the fields are stubbed here.
  - Item 009 (JSON report): embeds `HeuristicConfig.schema_version` for
    reproducibility.
  - Stage 4 (heuristic rule engine): adds threshold fields to `HeuristicConfig`
    schema; this item defines the pattern they extend.

---

## Decisions & Trade-offs

Recorded during implementation (2026-06-25).

1. **Config file format — YAML chosen.** `PyYAML>=5.4` added to
   `[project.dependencies]` in `pyproject.toml`. Rationale: YAML allows comments
   (useful for annotating threshold values later), is less noisy than JSON, and is
   ubiquitous in scientific Python environments. The `yaml.safe_load` parser is
   used (not `yaml.load`) to avoid arbitrary code execution from untrusted config
   files. Unknown keys in the YAML file are silently ignored, making the loader
   forward-compatible with future schema additions.

2. **Module name `segqc._logging` (not `segqc.logging`).** The name `segqc.logging`
   would shadow the stdlib `logging` module from inside the package (`import
   logging` in sibling modules would resolve to the submodule, not stdlib). The
   `_logging` private name avoids this entirely. Other `segqc` modules use
   `import logging; logger = logging.getLogger(__name__)` with no import of
   `segqc._logging` needed — callers only call `setup_logging` at the application
   entry point (CLI in item 006). The module is part of the public API (importable
   by callers) despite the leading underscore convention.

3. **`schema_version` — strict equality** (`version == SUPPORTED_SCHEMA_VERSION`).
   Any version other than `"0.1"` raises `SegQCConfigError`. Simple and safe for
   an early schema. The migration path: bump `SUPPORTED_SCHEMA_VERSION` and update
   `load_config` (or add a compat shim) when the schema changes. Old configs will
   fail loudly with a clear message, which is preferred over silently misloading a
   stale config.

4. **Missing-file error wrapped as `SegQCConfigError`** (chained from the original
   `FileNotFoundError` via `raise ... from exc`). Callers only need to handle one
   exception type for all config failures. The chaining preserves the original
   traceback for debuggability (`exc_info.value.__cause__` is the
   `FileNotFoundError`). The test `test_load_missing_file_chains_original_exception`
   verifies this.

5. **Placeholder field names `min_foreground_voxels: int = 0` and
   `min_label_count: int = 0`** in `HeuristicConfig`. Defaults of `0` mean "no
   threshold applied" (every segmentation passes). Item 007 gives these fields
   real semantics; if it renames them, it updates the dataclass and `_DEFAULTS` in
   `config.py`. These names are documented here so the Item 007 spec can reference
   them directly.

6. **`setup_logging` idempotency via handler clearing.** On each call, all
   existing handlers on the `"segqc"` logger are removed and closed before the new
   one is added. This means a second call to `setup_logging` (e.g. a test resetting
   log level) always results in exactly one handler — no handler accumulation. The
   test `test_setup_logging_idempotent_no_duplicate_output` confirms output is not
   doubled.

7. **`HeuristicConfig` is a frozen `@dataclass`**, consistent with `segqc.io.Case`
   and `segqc.labels.LabelConvention`. The `_DEFAULTS` dict is the single source
   of truth for both `default_config()` and the merge logic in `load_config`:
   adding a new field requires editing `_DEFAULTS` and the dataclass in one place.

---

## Testing Prerequisites

### Required Services

**None.** Config loading and logging setup are in-process, pure-Python operations.
No databases, APIs, message queues, or external services. (Row included per the
work-item template.)

### Environment Configuration

- **Python:** 3.9 or newer on `PATH`.
- **Virtual environment:** activate an existing one or create fresh:
  ```
  python -m venv .venv
  # Windows: .\.venv\Scripts\Activate.ps1
  # macOS/Linux: source .venv/bin/activate
  ```
- **Install:** `pip install -e .[dev]` (installs `PyYAML` if added to deps).
- **Environment variables / secrets:** none.
- **Configuration files:** the test suite generates its own temp files; no
  committed config needed before running tests.
- **Ports:** none.
- **Test data:** all inline / `tmp_path` YAML strings; nothing committed or
  downloaded.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` completes (including `PyYAML` if
      added) on Python 3.9+.
- [ ] **Tests pass:** `python -m pytest` is green across the whole suite, including
      the new `tests/test_config.py` and `tests/test_logging_setup.py`.
- [ ] **Services started:** N/A.
- [ ] **Application runs:**
  ```python
  from segqc.config import default_config, load_config
  from segqc._logging import setup_logging
  import segqc.config  # no side-effects
  ```
  all import cleanly.
- [ ] **Feature verified (REPL):**
  ```python
  from segqc.config import default_config
  cfg = default_config()
  print(cfg.schema_version)           # e.g. "0.1"
  print(cfg.min_foreground_voxels)    # 0 (placeholder)

  import tempfile, pathlib
  tmp = pathlib.Path(tempfile.mktemp(suffix=".yaml"))
  tmp.write_text("schema_version: '0.1'\n")
  from segqc.config import load_config
  cfg2 = load_config(tmp)
  print(cfg2.schema_version)          # "0.1"

  from segqc._logging import setup_logging
  setup_logging("DEBUG")
  import logging
  logging.getLogger("segqc.test").info("hello")  # should print to stderr
  ```
- [ ] **Data verified:** `SegQCConfigError` is raised for an unknown version and
      for a malformed YAML file.
- [ ] **Health checks pass:** N/A.

### Expected Outcomes

- `import segqc.config` and `import segqc._logging` succeed with no side-effects.
- `default_config()` returns a `HeuristicConfig` with `schema_version` matching
  the supported version string.
- `load_config(path)` with a minimal YAML fills in all defaults; with a full YAML
  the explicit values win.
- `load_config` raises `SegQCConfigError` for unsupported version, malformed
  YAML, and missing file.
- `setup_logging("DEBUG")` installs exactly one `StreamHandler` on the `"segqc"`
  logger without duplicating it on repeated calls.
- `setup_logging("DEBUG", json_format=True)` produces parseable JSON lines.
- `python -m pytest` reports the new test files green with 0 failures.

---

## Validation Results

Executed 2026-06-25 on **Windows 11**, Python 3.9.13 (builder implementation;
final sign-off and merge performed by a separate validator per `CLAUDE.md`).

- [x] Service started: N/A (no services)
- [x] Application started successfully: `import segqc.config` and
      `import segqc._logging` both import cleanly with no side-effects;
      `segqc --help` still exits `0` (unaffected by this item)
- [x] Database tables verified: N/A
- [x] Seed data verified: N/A
- [x] API endpoints verified: N/A
- [x] Screenshots captured: N/A (no UI)
- [x] `pip install -e .[dev]`: `PyYAML` installed cleanly alongside existing deps
- [x] `pytest` green: **150 passed in 0.58s** — 39 new tests in
      `tests/test_config.py` (22) and `tests/test_logging_setup.py` (17), plus
      all prior item 001–004 suites unaffected
- [x] Verified on OS: **Windows 11**, Python 3.9. Pure-Python (stdlib `logging`,
      `json`, `pathlib`, `dataclasses` + `PyYAML`); no platform-specific code —
      macOS/Linux behaviour is identical.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"Structured logging + versioned heuristic-config scaffold
  (YAML/JSON)"** deliverable from 📋 → ✅ (mark it 🚧 while in progress).
- Do **not** tick the Stage 0 *Acceptance* checkboxes that depend on Item 006
  (the `segqc run` end-to-end test).
- Per `CLAUDE.md`: work on branch `aide/005-structured-logging` (push it
  **before** real work to claim the item), `git pull --rebase` before editing
  `progress.md`, and keep the edit scoped to this item's row. A work item may
  merge **straight to `main` once green — no PR required** (here, a separate
  validator performs the merge).

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 005` to
implement this work item.
