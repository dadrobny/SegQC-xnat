# Item 001 — Package Scaffolding & Build Configuration

> **Status:** ✅ Complete · **Created:** 2026-06-24 · **Completed:** 2026-06-24
> **Stage:** 0 — Project Scaffolding & I/O Foundation
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 001
> **Objectives:** Foundation (enables G1, G4 and all later stages)
> **Suggested branch:** `aide/001-package-scaffolding`

---

## Description

Create the `segqc/` Python package targeting **Python 3.9+** with a
`pyproject.toml` that declares pinned core dependencies and registers a
console-script entry point for the `segqc` command. Establish the source
layout, package metadata, and a minimal CLI (`segqc --help`, `segqc run --help`)
that parses arguments and exits cleanly.

This is the **first item on the critical path** (`001 → 003 → 004 → 006`) and is
greenfield: the repo currently contains only `docs/`, `.claude/`, `.specify/`,
`README.md`, and `CLAUDE.md` — there is no Python package, `pyproject.toml`, or
test harness yet. Everything in Stage 0 and Stage 1 plugs into the skeleton this
item creates.

### Scope boundary (what this item does *not* do)

This item is **scaffolding only**. To avoid overlap with later items:

| Concern | Owned by | This item |
|---|---|---|
| NIfTI loading | Item 003 | `run` parses `--scan/--seg/--out` then exits cleanly (no loading) |
| Label convention | Item 004 | not implemented |
| Logging + heuristic-config scaffold | Item 005 | not implemented |
| Full pytest harness + synthetic fixtures | Item 002 | one minimal smoke test only |
| `run` actually loading + inventory + stub JSON | Item 006 | `run` is a stub |

The `segqc run` subcommand must **exist and parse its flags**, but on invocation
it should exit cleanly with a clear "not yet implemented" notice (exit code 0)
rather than attempting any I/O. Item 006 replaces that stub body.

---

## Acceptance Criteria

- [x] `segqc/` package exists with the agreed source layout and is importable as
      `import segqc` (and exposes `segqc.__version__`).
- [x] `pyproject.toml` is valid (PEP 621 metadata), declares the pinned core
      runtime dependencies, the build backend, the `requires-python = ">=3.9"`
      floor, and a `[project.scripts]` entry point mapping `segqc` to the CLI.
- [x] `pip install -e .` completes successfully in a clean virtual environment on
      Python 3.9+. *(Verified on Python 3.11.2; deps resolve from `>=3.9` lower
      bounds.)*
- [x] `segqc --help` prints usage including the `run` subcommand and exits `0`.
- [x] `segqc run --help` prints usage listing `--scan`, `--seg`, `--out` and
      exits `0`.
- [x] `segqc run --scan X --seg Y --out Z` parses the arguments and exits cleanly
      with a "not yet implemented" notice (exit `0`); it performs **no** file I/O.
- [x] `segqc --version` (or `segqc --help` footer) reports the package version.
- [x] One smoke test passes (`import segqc`; `segqc --help` exits `0`). *(5 smoke
      tests pass.)*
- [x] Works CPU-only on Windows, macOS, and Linux (no platform-specific code,
      no compiled extensions authored here). *(Verified on Windows; pure-Python,
      stdlib-only CLI — no OS-specific code or compiled extensions.)*
- [x] A short "Development setup" section is added to `README.md` (or a
      `CONTRIBUTING`/`docs` note) describing venv + `pip install -e .[dev]`.

---

## Implementation Steps

1. **Choose and document the project layout** (see Decisions below). Recommended:
   `src/`-layout so tests run against the installed package, not the working
   tree.
   ```
   pyproject.toml
   src/segqc/__init__.py        # __version__ defined here
   src/segqc/cli.py             # argparse-based entry point: main()
   tests/test_smoke.py          # import + --help smoke test
   ```
2. **Write `pyproject.toml`** (PEP 621):
   - `[build-system]` → recommended backend `hatchling`.
   - `[project]`: `name = "segqc"`, `version` (or dynamic from
     `segqc.__version__`), `description`, `readme = "README.md"`, `license`,
     `authors`, `requires-python = ">=3.9"`.
   - `[project.dependencies]`: core scientific stack with **lower-bound pins
     compatible with Python 3.9** (see dependency note below).
   - `[project.optional-dependencies]`: `dev = ["pytest>=7", ...]`.
   - `[project.scripts]`: `segqc = "segqc.cli:main"`.
3. **Implement `src/segqc/__init__.py`**: define `__version__` (single source of
   truth; reference it from `pyproject.toml` via dynamic version if using
   hatchling, or keep both in sync and document).
4. **Implement `src/segqc/cli.py`**:
   - `main(argv=None)` builds an `argparse.ArgumentParser` with `prog="segqc"`,
     a top-level `--version`, and a `run` subcommand.
   - `run` declares `--scan`, `--seg` (required-ish, but allow `--help` to work),
     `--out`.
   - `run` handler prints a clear "not yet implemented (Item 006)" message and
     returns `0`.
   - `main` returns an int exit code; `[project.scripts]` target wraps it with
     `sys.exit(main())` (use a thin wrapper or `raise SystemExit(main())`).
5. **Add `tests/test_smoke.py`**: assert `import segqc` works and that invoking
   the CLI with `--help` exits `0` (catch `SystemExit`, assert code `0`), and
   that `run --scan a --seg b --out c` returns `0`.
6. **Configure dev tooling minimally**: pytest config in `pyproject.toml`
   (`[tool.pytest.ini_options]` with `testpaths = ["tests"]`). Optional: a
   `[tool.ruff]`/formatter config if the team wants it (document if added).
7. **Update `.gitignore`** if needed for build artifacts (`*.egg-info/`,
   `build/`, `dist/`, `__pycache__/`, `.pytest_cache/`) — most are likely
   already present; verify.
8. **Add the README "Development setup" note.**
9. **Verify** the manual validation checklist below in a clean venv.

---

## Testing Strategy

- **Framework:** `pytest` (added as a `dev` extra; the *full* harness/config and
  synthetic NIfTI fixtures are Item 002 — keep this item's tests to a single
  smoke module).
- **Tests authored here:**
  - `test_import_package` — `import segqc` succeeds and `segqc.__version__` is a
    non-empty string.
  - `test_cli_help_exits_zero` — calling `main(["--help"])` raises `SystemExit`
    with code `0` (argparse exits on `--help`).
  - `test_run_subcommand_help` — `main(["run", "--help"])` exits `0`.
  - `test_run_stub_returns_zero` — `main(["run", "--scan", "a", "--seg", "b",
    "--out", "c"])` returns `0` and does **not** touch the filesystem.
- **Determinism / portability:** no external services, no network, no GPU, no
  fixtures on disk. Pure-Python, runs identically on all three OSes.
- **Manual cross-platform check:** install + `--help` on at least the
  developer's OS; rely on the no-platform-specific-code design for the others
  (CI matrix is a later concern, not required to close this item).

---

## Dependencies

- **Upstream (blocks this item):** none. This is the first item.
- **Downstream (this item unblocks):** Item 002 (test harness builds on the
  `tests/` skeleton and dev extra), Item 003 (loader imports into the package),
  Item 005 (config plumbing), Item 006 (fills in the `run` stub). Effectively
  every later item depends on this package skeleton existing.

### Dependency declaration note (core scientific stack)

The queue calls for "pinned core deps (NumPy, SciPy, scikit-image, NiBabel
and/or SimpleITK)". Recommendation for this item:

- Declare **NumPy, SciPy, scikit-image, NiBabel** in `[project.dependencies]`
  with **lower bounds compatible with Python 3.9** (e.g. `numpy>=1.21`,
  `scipy>=1.7`, `scikit-image>=0.19`, `nibabel>=4.0` — confirm against the
  actual resolved 3.9-compatible versions at implementation time).
- Treat **SimpleITK as deferred** — pick NiBabel as the primary NIfTI library
  (lightweight, pure-Python wheels, the de-facto standard for VerSe/NIfTI).
  Revisit in Item 003 if SimpleITK-specific I/O is needed; if so add it then.
- **Exact pinning for reproducibility** (a non-functional requirement in the
  vision) is best handled by a lockfile / constraints file for the **deployable
  container** (Stage 9), not by hard `==` pins in library metadata that would
  fight downstream resolution. Note this so it isn't lost.
- Only `numpy`/`nibabel` are strictly needed before Item 003; importing the
  heavy stack at scaffold time is unnecessary, but declaring them now means the
  environment is ready for Items 003–006. **Do not import** SciPy/scikit-image
  in `cli.py` yet (keeps `segqc --help` fast and import-clean).

---

## Decisions & Trade-offs

These are the open implementation choices for this item, with recommendations.
Record the final decision and rationale here during execution (initialize:
*"To be updated during implementation."*).

1. **Source layout — `src/`-layout (recommended) vs flat `segqc/`.**
   `src/`-layout prevents accidental imports from the working tree and forces
   tests against the installed package; the importable name is still `segqc`.
   The roadmap/queue write `segqc/` informally — `src/segqc/` satisfies that.
   *Decision: **`src/` layout** (confirmed by project owner, 2026-06-24).
   Package lives at `src/segqc/`, importable as `segqc`.*
2. **Build backend — `hatchling` (recommended) vs `setuptools`.** Hatchling is
   modern, minimal, and supports dynamic version from `__init__.py` cleanly.
   *Decision: **`hatchling`.** `[build-system]` requires `hatchling`;
   `[tool.hatch.build.targets.wheel]` declares `packages = ["src/segqc"]` so the
   `src/` layout resolves to the importable name `segqc`.*
3. **CLI framework — stdlib `argparse` (recommended) vs `click`/`typer`.**
   `argparse` adds **zero runtime dependencies**, fits the "minimal" scaffold,
   and is fully cross-platform. *Decision: **stdlib `argparse`.** `main(argv=None)`
   returns an `int`; subcommands dispatch via a `handler` default set with
   `set_defaults`. No third-party CLI dependency added.*
4. **Version single-sourcing — dynamic from `segqc.__version__` (recommended)
   vs duplicated literal.** *Decision: **dynamic.** `__version__` lives only in
   `src/segqc/__init__.py`; `pyproject.toml` declares `dynamic = ["version"]` and
   `[tool.hatch.version]` reads `path = "src/segqc/__init__.py"`. Verified: `pip
   show segqc` and `import segqc` both report `0.0.1`.*
5. **Dependency pinning strategy** — see the dependency note above
   (lower bounds in metadata now; exact pins via lock/constraints at Stage 9).
   *Decision: **lower bounds in metadata.** Declared `numpy>=1.21`, `scipy>=1.7`,
   `scikit-image>=0.19`, `nibabel>=4.0`; `dev = ["pytest>=7"]`. Exact
   reproducibility pins are deferred to the deployable container's
   lockfile/constraints (Stage 9), to avoid fighting downstream resolution.*
6. **Primary NIfTI library — NiBabel (recommended) vs SimpleITK.**
   *Decision: **NiBabel** as the sole declared NIfTI library; **SimpleITK
   deferred**. Revisit in Item 003 if SimpleITK-specific I/O is needed.*
7. **Behaviour of `segqc` with no subcommand.** Not specified by the item.
   *Decision: print full help to stdout and return exit code `1` (a usage
   signal), rather than `0`. `--help`/`--version` still short-circuit via argparse
   with exit code `0`. No test depends on this; chosen for conventional CLI UX.*
8. **`run` flags required vs optional.** *Decision: `--scan`, `--seg`, `--out`
   are `required=True`. argparse processes `--help` before required-arg
   validation, so `segqc run --help` still exits `0`, while `segqc run` with
   missing flags is a clean argparse usage error (exit `2`).*

---

## Testing Prerequisites

### Required Services

**None.** This item produces a self-contained Python package. There are no
databases, APIs, message queues, or other external services to start. (This row
is included because the work-item template requires it; later XNAT/Docker work
in Stage 9 is the first item that introduces services.)

### Environment Configuration

- **Python:** 3.9 or newer on `PATH`.
- **Virtual environment:** a clean venv is strongly recommended
  (`python -m venv .venv` then activate).
  - Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`
- **Install:** `pip install -e .[dev]`
- **Environment variables / secrets:** none required.
- **Configuration files:** only `pyproject.toml` (authored by this item).
- **Ports:** none.

### Manual Validation Checklist

- [x] **Build succeeds:** in a clean venv, `pip install -e .[dev]` completes
      without errors on Python 3.9+. *(Exit 0 in a fresh `python -m venv`.)*
- [x] **Tests pass:** `pytest` (or `python -m pytest`) is green. *(5 passed.)*
- [x] **Services started:** N/A — no services.
- [x] **Application runs:** `segqc --help` exits `0` and lists the `run`
      subcommand.
- [x] **Feature verified:**
  - `segqc --version` prints the package version (`segqc 0.0.1`).
  - `segqc run --help` exits `0` and lists `--scan`, `--seg`, `--out`.
  - `segqc run --scan a --seg b --out c` exits `0` with a clear
    "not yet implemented (Item 006)" message and writes nothing.
- [x] **Data verified:** N/A — no data is read or written by this item; confirmed
      the `--out` directory is **not** created by the stub (`Test-Path` → False).
- [x] **Health checks pass:** N/A — no server/health endpoint.

### Expected Outcomes

Concrete, verifiable results:

- `import segqc` succeeds; `segqc.__version__` is a non-empty string (e.g.
  `"0.0.1"` / `"0.1.0.dev0"`).
- `pip install -e .[dev]` installs `segqc` and its declared deps; `pip show
  segqc` lists the package with the expected version and entry point.
- The `segqc` console script is on `PATH` after install and resolves to
  `segqc.cli:main`.
- `segqc --help` exit code `0`; output contains `run`.
- `segqc run --help` exit code `0`; output contains `--scan`, `--seg`, `--out`.
- `segqc run --scan a --seg b --out c` exit code `0`; no file or directory is
  created at `c` (stub performs no I/O).
- `pytest` reports the smoke test module passing with `0` failures.

---

## Validation Results

> Executed 2026-06-24 in a clean venv (`python -m venv`) on Windows.

- [x] Service started: N/A (no services)
- [x] Application started successfully: `segqc --help` / `segqc run --help`
      exit `0`
- [x] Database tables verified: N/A
- [x] Seed data verified: N/A
- [x] API endpoints verified: N/A
- [x] Screenshots captured: N/A (no UI)
- [x] `pip install -e .[dev]` clean install: **pass** (exit 0; `pip show segqc`
      → version `0.0.1`, entry point `segqc.cli:main`)
- [x] `pytest` green: **pass** — `5 passed in 0.05s`
- [x] Verified on OS: **Windows 11** (Python 3.11.2). No platform-specific code;
      cross-platform behaviour relies on stdlib-only, pure-Python design (CI
      matrix deferred per the item's testing strategy).

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"Python package `segqc/` … `pyproject.toml` …"** deliverable
  from 📋 → ✅ (and mark it 🚧 while in progress).
- Do **not** mark the Stage 0 *Acceptance* checkboxes that depend on later items
  (loader, label inventory, stub JSON) — those close with Items 003/004/006.
- Per `CLAUDE.md`: work on a branch (`aide/001-package-scaffolding`),
  `git pull --rebase` before editing `progress.md`, keep the edit scoped to this
  item's rows, and open a PR rather than committing to `main`.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 001` to
implement this work item.
