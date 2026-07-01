---
name: speckit-aide-status-report
description: Generate an evolving HTML project-status summary from the AIDE documents, test suite, and QC outputs.
compatibility: Requires spec-kit project structure with docs/aide/ AIDE documents
metadata:
  author: SegQC-xnat
  source: aide:local/status-report
---

# AIDE Status Report

Generate a single, self-contained **HTML project-status summary** for Seg-QC-xnat
from the living AIDE documents, the test suite, and (when available) QC image and
feature-distribution outputs. It is a **living artifact**: re-run it as
development progresses and the summary extends itself.

## When to use

- **Standalone** — whenever you want a visual, high-level snapshot of project
  maturity: what is finished, what is queued, how items map to roadmap stages and
  vision objectives, and how the test suite and QC outputs currently look.
- **Embedded in a workflow** — as an optional final step of
  `/speckit-aide-feedback-loop` (see that skill's step 6), or after a queue/roadmap
  run, to refresh the status page.

## What it produces

A single HTML file (default `docs/aide/status/index.html`) with these sections:

1. **Work-Queue Overview** — finished, in-progress, and upcoming work items, each
   mapped to its roadmap stage.
2. **Project Phase Alignment** — the roadmap stage table with completion status
   and an overall progress bar.
3. **Vision Objective Coverage** — G1…G8 objectives and their delivery status.
4. **Testing Overview** — test-file and test-function counts; pass/fail/skip
   outcomes when a pytest JUnit-XML report is supplied.
5. **Project Feature Highlights** — QC overlay images and feature-distribution
   plots. These are **extension points**: they render an explicit
   "not yet available" placeholder until the artifacts they depend on
   (roadmap Stages 5–7 — synthetic corpus, reference distributions, evaluation
   harness) exist, then auto-populate when pointed at an output folder.

The generator (`scripts/aide_status_report.py`) is deterministic given the same
inputs (only the timestamp varies), so re-runs produce stable diffs.

## How to run

Use the project venv (see `CLAUDE.md`). From the repo root:

```bash
# Windows (Git Bash)
.venv/Scripts/python scripts/aide_status_report.py
# macOS / Linux
.venv/bin/python scripts/aide_status_report.py
```

Useful options:

- `--out <path>` — write somewhere other than `docs/aide/status/index.html`.
- `--junit <results.xml>` — include pass/fail outcomes. Produce the XML with
  `.venv/Scripts/python -m pytest --junitxml=results.xml`.
- `--qc-images <dir>` — embed QC overlay PNG/SVG images from a run's output folder
  (e.g. the sagittal projections from item 021).
- `--distributions <dir>` — embed feature-distribution plots.
- `--no-embed` — reference images by path instead of base64-embedding them.

## Instructions for the agent

1. Ensure the venv is current (`.venv/Scripts/python -c "import segqc"`; rebuild
   per `CLAUDE.md` if it fails).
2. Optionally run `pytest --junitxml=results.xml` first so the Testing Overview
   shows real outcomes.
3. Run the generator with any relevant `--qc-images` / `--distributions` folders
   that exist for the current work.
4. Report the output path. Open `docs/aide/status/index.html` to view.

## Output is a per-machine artifact

The generated HTML (and any embedded images) under `docs/aide/status/` is a
**derived, regenerable artifact** and is **gitignored** — like the permission
logs, a committed generated file written from several machines would be a
merge-conflict hotspot. Only the generator and this skill are version-controlled.
Regenerate locally whenever you need a fresh snapshot.
