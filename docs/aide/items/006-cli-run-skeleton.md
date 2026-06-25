# Item 006 — CLI `segqc run` Skeleton: Load, Inventory, Stub JSON

> **Status:** 📋 Planned · **Created:** 2026-06-25
> **Stage:** 0 — Project Scaffolding & I/O Foundation *(final item, completes Stage 0)*
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 006
> **Objectives:** Foundation — closes the Stage 0 acceptance test (G1, G4 substrate)
> **Suggested branch:** `aide/006-cli-skeleton`

---

## Description

Wire the CLI `segqc run --scan <nii> --seg <nii> --out <dir>` command to invoke
the loader (item 003) + label convention (item 004) and then:

1. **Print the labelled label inventory** — for each present label: the integer
   value, the anatomical name (from `LabelConvention.default()`), and the voxel
   count — to `stdout` in a human-readable table.
2. **Write a stub JSON report** to `<out>/segqc_report.json` containing at
   minimum: scan/seg paths, spacing, number of foreground voxels, the label
   inventory as a list of `{label, name, voxels}` objects, and the config
   `schema_version` (from item 005's `default_config()`).
3. **Wire `--log-level`** — the item 005 spec explicitly defers this flag to
   item 006; call `setup_logging(level)` after parsing.

The current `_handle_run` in `src/segqc/cli.py` is the stub that this item
replaces. Everything else in `cli.py` (argument parser, `main`, dispatch) stays
as-is.

This is the **last item on the critical path** (`001 → 003 → 004 → 006`) for
Stage 0. When it lands, `segqc run` on a fixture prints the labelled inventory
and writes a stub JSON — satisfying the Stage 0 acceptance test in `progress.md`.

### Scope boundary (what this item does *not* do)

| Concern | Owned by | This item |
|---|---|---|
| Empty / near-empty detection | Item 007 | stub JSON records counts only; no pass/fail verdict |
| QC verdict model (`pass`/`flagged-for-review`/`fail`) | Items 008–010 | stub JSON has no `verdict` field — that field lands in item 009 |
| JSON report schema validation | Item 009 | stub JSON is *not* validated against a schema; item 009 defines the schema |
| Human-readable report (Markdown/text) | Item 010 | only the stub JSON and stdout inventory; no rendered `.md` file |
| Config file flag (`--config`) | Item 007+ | `default_config()` is used unconditionally here; no `--config` arg yet |
| Label-convention override | Items 004/005 | uses `LabelConvention.default()` only |
| Geometric features, centroids, CC | Stage 2 | stub JSON records only the raw label inventory + metadata |

---

## Acceptance Criteria

- [ ] `src/segqc/cli.py` is modified: `_handle_run` replaces its "not yet
      implemented" stub body with the real load → inventory → print → write flow.
      All other parts of `cli.py` (parser, `main`, subcommand dispatch) are
      unchanged.
- [ ] **`--log-level` flag** is added to the `run` subparser (choices:
      `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `WARNING`);
      `_handle_run` calls `setup_logging(args.log_level)` before any I/O.
- [ ] On a valid scan + seg pair, `segqc run` **loads both volumes** via
      `load_case(scan, seg)` (item 003) and exits `0`.
- [ ] **Prints the label inventory** to `stdout`: for each present label (in
      anatomical order), a row showing the integer label value, anatomical name
      (or `"unknown"` for unmapped labels), and voxel count. Unknown labels are
      printed after recognised ones, clearly labelled.
- [ ] **Creates `<out>/`** if it does not exist, then **writes
      `<out>/segqc_report.json`** — a UTF-8 JSON file with at minimum:
      `scan_path`, `seg_path`, `spacing`, `foreground_voxels`, `label_inventory`
      (list of `{label, name, voxels}` objects in anatomical order), and
      `config_schema_version` from `default_config().schema_version`.
- [ ] The written JSON is valid (parseable by `json.loads`), with every field
      present and containing the right types; an end-to-end test asserts field
      presence and basic types.
- [ ] On a missing or unreadable input, `segqc run` catches
      `SegQCInputError`, prints a clear error message to `stderr`, and exits `1`
      (not `0`, not an unhandled traceback).
- [ ] `segqc run --help` still exits `0` and lists `--scan`, `--seg`, `--out`,
      `--log-level` (no regression).
- [ ] All existing tests (`pytest`) continue to pass — no regressions in items
      001–005.
- [ ] Runs CPU-only on Windows, macOS, and Linux (no platform-specific code,
      no compiled extensions authored here).

---

## Implementation Steps

1. **Add `--log-level` to the `run` subparser** in `_build_parser()`:
   ```python
   run_parser.add_argument(
       "--log-level",
       default="WARNING",
       choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
       metavar="<level>",
       help="Log level (default: WARNING).",
   )
   ```

2. **Replace `_handle_run`** in `cli.py`. The new body (pseudocode):
   ```python
   def _handle_run(args):
       from segqc._logging import setup_logging
       setup_logging(args.log_level)
       logger = logging.getLogger("segqc.cli")

       from segqc.io import load_case, SegQCInputError
       from segqc.labels import LabelConvention, summarise_inventory
       from segqc.config import default_config

       try:
           case = load_case(args.scan, args.seg)
       except SegQCInputError as exc:
           print(f"Error: {exc}", file=sys.stderr)
           return 1

       convention = LabelConvention.default()
       summary = summarise_inventory(case.label_inventory, convention)
       cfg = default_config()

       _print_inventory(summary)          # to stdout
       _write_stub_json(args.out, case, summary, cfg)  # to <out>/segqc_report.json

       logger.info("segqc run complete — report written to %s", args.out)
       return 0
   ```

3. **Implement `_print_inventory(summary)`** (private helper, same module):
   - Header line: `"Label inventory:"` then a ruled separator.
   - One row per recognised label: `f"  {value:>4}  {name:<10}  {count:>10} voxels"`.
   - If there are unknown labels: a blank line + `"Unknown labels:"` header,
     then one row per unknown: `f"  {value:>4}  (unknown)   {count:>10} voxels"`.
   - If the inventory is empty: `"  (no foreground labels found)"`.

4. **Implement `_write_stub_json(out_dir, case, summary, cfg)`** (private helper):
   - `pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)`.
   - Build the dict:
     ```python
     {
       "scan_path": case.scan.path,
       "seg_path": case.seg.path,
       "spacing": list(case.scan.spacing),
       "foreground_voxels": case.foreground_voxels,
       "label_inventory": [
           {"label": v, "name": n, "voxels": c}
           for v, n, c in summary.recognised
       ] + [
           {"label": v, "name": "unknown", "voxels": c}
           for v, c in summary.unknown
           if isinstance(c, int)          # skip malformed counts from edge cases
       ],
       "config_schema_version": cfg.schema_version,
     }
     ```
   - Write via `json.dumps(data, indent=2)` to
     `Path(out_dir) / "segqc_report.json"` (UTF-8).

5. **Update the module docstring** of `cli.py` to remove the "item 001 scope"
   paragraph and replace with a brief description of the item 006 scope.

6. **Write or extend `tests/test_cli_run.py`** (new file, or extend
   `test_smoke.py` — keep it separate for clarity):
   - `test_run_loads_and_prints` — use `tmp_path` + `synthetic.py` fixtures to
     build a real scan + seg pair; invoke `main(["run", "--scan", ..., "--seg",
     ..., "--out", str(out)])` via `capsys`; assert exit code `0`, stdout
     contains at least one anatomical name, and `out/segqc_report.json` exists.
   - `test_run_json_fields` — open and parse the JSON; assert all required top-
     level keys are present and have the right types.
   - `test_run_missing_scan` — pass a nonexistent path as `--scan`; assert exit
     code `1` and no file written.
   - `test_run_creates_out_dir` — pass a nested `--out` path that doesn't exist;
     assert it is created and the JSON is written.
   - `test_run_log_level_default` — run without `--log-level`; assert exit code
     `0` (no crash from the default).
   - `test_run_help_lists_log_level` — `main(["run", "--help"])` catches
     `SystemExit(0)` and the help text includes `--log-level`.

7. **Run `python -m pytest`** in the project venv; confirm all tests green.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness, already in `.venv`).
- **Fixtures:** use `tests/synthetic.py` (item 002's `make_scan`/`make_seg` or
  equivalent) to build minimal in-memory NIfTI volumes written to `tmp_path`.
  The existing `tests/conftest.py` likely already exposes these; check before
  duplicating.
- **New test module:** `tests/test_cli_run.py` (six tests as above).
- **No external services:** CPU-only, in-memory fixtures, no network.
- **Error-path coverage:** test that a missing file returns exit code `1` (not
  a traceback), so the error-handling path is exercised.
- **Regression guard:** `pytest` must report 0 failures across all existing test
  modules (005 tests, config, labels, io, synthetic, smoke, permission-review).

---

## Dependencies

- **Upstream (blocks this item):**
  - Item 001 (package skeleton, `cli.py` stub) — ✅ merged
  - Item 003 (`segqc.io.load_case`, `SegQCInputError`) — ✅ merged
  - Item 004 (`segqc.labels.LabelConvention`, `summarise_inventory`) — ✅ merged
  - Item 005 (`segqc._logging.setup_logging`, `segqc.config.default_config`) — ✅ merged
- **Downstream (this item unblocks):**
  - Item 007 (empty/near-empty detection) — consumes the same CLI + `load_case`
    chain; uses `HeuristicConfig` thresholds; runs on the same fixture set.
  - Items 008–010 (verdict model, JSON schema, human report) — all extend the
    stub JSON produced here and plug into the same CLI entry point.

---

## Decisions & Trade-offs

*To be updated during implementation.*

Key decisions to record when implementing:

1. **`--log-level` on `run` or on the top-level parser?** Item 005 spec says
   "wired in item 006"; item 001's CLI has top-level `--version` only. Recommended:
   add `--log-level` to the `run` subcommand (it only makes sense when work is
   being done). If later items want it top-level too, that's a small migration.
2. **Stub JSON filename** — `segqc_report.json` (recommended; consistent with
   Stage 1 intent). Record if changed.
3. **Unknown-label count guard** — malformed counts (non-int) from edge-case
   inventory inputs: skip them in the JSON or convert them to `null`. Recommended:
   skip (as shown in step 4 pseudocode) so the JSON stays schema-clean.
4. **`_print_inventory` / `_write_stub_json` placement** — same `cli.py` as
   private helpers (recommended) vs. a new `segqc._report` module. The latter
   would be premature; item 009 owns the real report module.
5. **Spacing representation in JSON** — `list(case.scan.spacing)` (3 floats).
   This is the simplest portable form; record if a different repr is chosen.

---

## Testing Prerequisites

### Required Services

**None.** Self-contained Python package with synthetic NIfTI fixtures. No databases,
APIs, or Docker images needed.

### Environment Configuration

- **Python:** 3.9+ on PATH.
- **Virtual environment:** `.venv` at project root (already bootstrapped from
  earlier items).
  - Windows: `.\.venv\Scripts\Activate.ps1`
  - macOS/Linux: `source .venv/bin/activate`
- **Install:** `pip install -e .[dev]` (already installed; re-run if deps changed).
- **Environment variables / secrets:** none.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` (or `pip install -e .`) exits 0.
- [ ] **Tests pass:** `python -m pytest` is green (0 failures, 0 errors).
- [ ] **Services started:** N/A.
- [ ] **Application runs:** `segqc run --scan <fixture> --seg <fixture> --out /tmp/qc`
       exits 0, prints a label inventory table, and writes `/tmp/qc/segqc_report.json`.
- [ ] **Feature verified:**
  - stdout contains at least one anatomical name (e.g. `L1`, `T12`).
  - `segqc_report.json` is valid JSON with keys: `scan_path`, `seg_path`,
    `spacing`, `foreground_voxels`, `label_inventory`, `config_schema_version`.
  - `segqc run --scan /nonexistent.nii.gz --seg /nonexistent.nii.gz --out /tmp/x`
    exits `1` and prints an error to stderr (no traceback).
  - `segqc run --help` lists `--log-level`.
- [ ] **Data verified:** `cat segqc_report.json` shows the expected structure.
- [ ] **Health checks pass:** N/A.

### Expected Outcomes

- `segqc run` on fixture files: exits `0`, stdout table shows integer label /
  anatomical name / voxel count per present label.
- `<out>/segqc_report.json` written; `python -c "import json; json.load(open(...))"` succeeds.
- `segqc run` on missing files: exits `1`; no JSON written.
- `pytest` reports 0 failures across all test modules.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 0 **"CLI entry point: `segqc run`…"** deliverable from 📋 → ✅
  (mark 🚧 while in progress).
- Tick the Stage 0 acceptance checkboxes:
  - `[ ] segqc run on a fixture loads both volumes, prints labelled inventory, writes a stub JSON.`
  (The other two Stage 0 acceptance items are already covered by items 001–004.)
- Per `CLAUDE.md`: work on branch `aide/006-cli-skeleton`, `git pull --rebase`
  before editing `progress.md`, keep edits scoped to this item's rows, and
  direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 006` to
implement this work item.
