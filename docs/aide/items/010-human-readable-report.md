# Item 010 — Human-Readable Report Renderer & Final Pipeline Wiring

> **Status:** 🚧 In Progress · **Created:** 2026-06-25
> **Stage:** 1 — End-to-End Thin Slice: Empty Detection + Report
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 010
> **Objectives:** G1 — Empty fixture flagged `fail`; G4 — Per-case QC report (JSON + human-readable)
> **Suggested branch:** `aide/010-human-readable-report`

---

## Description

Complete Stage 1 by delivering two things:

1. **Human-readable report renderer** — a `render_human_report` function in
   `src/segqc/human_report.py` that converts a `Verdict` object (item 008) plus
   case metadata into a Markdown/plain-text string that a clinician or reviewer
   can read directly.

2. **Full Stage 1 pipeline wiring** — update `segqc run` (CLI, item 006) to run
   the complete pipeline:
   - Load scan + segmentation (item 003)
   - Run the empty/near-empty check (item 007) and build a `Verdict` (item 008)
   - Write the JSON report (item 009) via `serialize_report_json` to
     `<out>/segqc_report.json`
   - Write the human-readable report via `render_human_report` to
     `<out>/segqc_report.txt`
   - Exit with code 0 on pass or flag; exit code 1 on fail (or on input error)

### Human report structure

The plain-text report must contain at minimum:

- A title line (e.g. `SegQC Report — <case_id>`)
- The overall verdict string (`pass`, `flagged-for-review`, or `fail`)
- Every case-level reason message (one per line, with its severity prefix)
- A per-label section listing each flagged/failed label and its reason messages

Example (layout may vary; key strings must be present):

```
SegQC Report — scan-001
=======================
Verdict: fail

Reasons:
  [fail] Segmentation is completely empty (0 foreground voxels)

Per-label findings:
  (none)
```

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| QC verdict data model | Item 008 | consumed here |
| JSON report serializer | Item 009 | consumed here |
| Empty/near-empty check | Item 007 | consumed here |
| Feature extraction | Stage 2+ | not here |
| XNAT integration | Stage 3 | not here |
| Human report file I/O | This item | writes `segqc_report.txt` |
| JSON report file I/O | This item | writes `segqc_report.json` |

---

## Acceptance Criteria

- [ ] **AC-1 `render_human_report` importable** as
      `from segqc.human_report import render_human_report` with no import errors.
- [ ] **AC-2 Returns a non-empty string**: `render_human_report(verdict, case_id,
      config)` returns a `str` with at least one character.
- [ ] **AC-3 Contains verdict string**: the returned string contains the overall
      verdict label — one of `"pass"`, `"flagged-for-review"`, or `"fail"`.
- [ ] **AC-4 Contains reason messages**: every case-level `Reason.message` in the
      `Verdict` appears somewhere in the rendered string.
- [ ] **AC-5 Contains per-label reasons**: every `Reason.message` under
      `verdict.per_label` appears somewhere in the rendered string.
- [ ] **AC-6 Contains case_id**: the `case_id` argument appears somewhere in the
      rendered string (used as the report title/header).
- [ ] **AC-7 Deterministic**: calling `render_human_report` twice with identical
      inputs produces the same string.
- [ ] **AC-8 No raw Python internals in output**: the rendered string must not
      contain raw Python class names (`Severity`, `Reason`, `Verdict`,
      `NoneType`, `frozenset`) or exception text (`Traceback`, `ValueError`).
- [ ] **AC-9 `segqc run` writes `segqc_report.txt`**: after a successful
      `segqc run` invocation the file `<out>/segqc_report.txt` exists in the
      output directory.
- [ ] **AC-10 `segqc run` writes `segqc_report.json`**: after a successful
      `segqc run` invocation the file `<out>/segqc_report.json` exists and
      contains a v0-schema-valid JSON document (not the legacy stub).
- [ ] **AC-11 Empty fixture → `fail` verdict in JSON**: running `segqc run` on the
      empty fixture (all-zero segmentation) produces a JSON report whose `verdict`
      field is `"fail"` (G1 — empty segmentations are always rejected).
- [ ] **AC-12 Empty fixture → human report contains `fail`**: the human-readable
      report for an empty fixture contains the string `"fail"`.
- [ ] **AC-13 Populated fixture → `pass` verdict**: running `segqc run` on the
      labelled-blocks fixture produces a JSON report whose `verdict` field is
      `"pass"` (with default config thresholds, a well-formed segmentation passes
      the empty check).
- [ ] **AC-14 Near-empty fixture → `fail` or `flagged-for-review`**: a fixture
      that is near-empty (small foreground voxel count below threshold) produces a
      non-pass verdict when thresholds are set appropriately.
- [ ] **AC-15 Missing output dir is created**: if `--out` does not exist,
      `segqc run` creates it (and any missing parents) before writing reports.
- [ ] **AC-16 Human report not empty for any verdict**: the written `segqc_report.txt`
      is non-empty (> 0 bytes) for empty, near-empty, and populated fixtures.
- [ ] **AC-17 No stdlib-external imports at module level**: `import
      segqc.human_report` must not require NumPy, NiBabel, SciPy, or any other
      non-stdlib package at import time.

---

## Implementation Steps

1. **Create `src/segqc/human_report.py`**:
   - Implement `render_human_report(verdict: Verdict, case_id: str, config:
     HeuristicConfig) -> str` — produce a structured plain-text report string.
   - The function has no I/O; it is a pure string builder. File writing is done
     in the CLI.

2. **Update `src/segqc/cli.py` `_handle_run`**:
   - After loading the case, call `check_empty` (item 007) to get a
     `CheckResult`.
   - Build a `Verdict` from the `CheckResult` reasons using `Verdict.build`.
   - Write `segqc_report.json` using `serialize_report_json` (item 009).
   - Write `segqc_report.txt` using `render_human_report`.
   - Set exit code 1 if `verdict.overall == Severity.FAIL`.

3. **Export from `src/segqc/__init__.py`**: add
   `from segqc.human_report import render_human_report`.

4. **Write `tests/test_010_human_report.py`** (pure renderer tests, no I/O).
5. **Write `tests/test_010_pipeline.py`** (end-to-end CLI tests).

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **Renderer tests** (`test_010_human_report.py`): pure in-memory; use the same
  `Verdict`/`Reason`/`Severity` helpers as items 008 and 009. No I/O, no tmp_path.
- **Pipeline tests** (`test_010_pipeline.py`): use `tmp_path` and the on-disk
  `conftest.py` fixtures (`labelled_blocks_files`, `empty_labelmap_files`).
  Drive the CLI via `main(args)` (same pattern as `test_cli_run.py`).
- **Coverage:** all seventeen ACs; adversarial: no labels, single-label map,
  missing output dir, deeply-nested output dir, verdict immutability, report
  determinism, human report byte count.

---

## Dependencies

- **Upstream (all ✅ merged):**
  - Item 001 (package skeleton)
  - Item 003 (NIfTI loader, `load_case`, `SegQCInputError`)
  - Item 005 (heuristic config, `HeuristicConfig`, `default_config`)
  - Item 006 (CLI `run` subcommand, `main`)
  - Item 007 (empty detection, `check_empty`, `CheckResult`)
  - Item 008 (verdict model, `Verdict`, `Reason`, `Severity`)
  - Item 009 (JSON serializer, `serialize_report`, `serialize_report_json`)
- **Downstream:** Stage 2 (feature extraction pipeline, extends JSON schema).

---

## Decisions & Trade-offs

1. **Plain text (not Markdown)**: the renderer outputs structured plain text
   compatible with terminal display, XNAT notes, and email. Markdown headings
   are a later option once the output channel is known.

2. **Renderer is pure (no file I/O)**: same pattern as `serialize_report`. The
   CLI is the only place that does I/O, so the renderer is trivially testable.

3. **Exit code 1 on `fail`**: the CLI follows the standard unix convention
   (non-zero exit on failure). `flagged-for-review` exits 0 (the scan is
   usable, just needs human review). Input errors also exit 1.

4. **Both reports always written**: even for a `fail` verdict, both files are
   written before the process exits. Consumers can inspect the report to
   understand why the scan failed.

5. **`case_id` derived from the scan filename stem**: in the CLI, `case_id` is
   set to `pathlib.Path(args.scan).stem` (stripping `.nii` / `.nii.gz`).
   Tests can pass any string.

6. **Empty-detection → Verdict bridge**: `check_empty` returns `CheckResult`
   with `is_empty: bool` and `reasons: tuple[str, ...]`. The CLI bridge creates
   `Reason` objects from the string reasons, using `Severity.FAIL` when
   `is_empty=True` and `Severity.PASS` otherwise.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]`.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Expected Outcomes

- `pytest tests/test_010_human_report.py tests/test_010_pipeline.py` reports 0
  failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–009.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 1 **"Human-readable report & final pipeline wiring"** deliverable
  from 📋 → ✅ (mark 🚧 while in progress).
- Per `CLAUDE.md`: work on branch `aide/010-human-readable-report`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's rows,
  and direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 010` to
implement this work item.
