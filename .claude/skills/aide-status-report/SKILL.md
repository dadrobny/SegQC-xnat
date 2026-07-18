---
name: aide-status-report
description: Generate an evolving HTML project-status summary from the AIDE documents, test suite, and QC outputs.
---

# AIDE Status Report

Generate a single, self-contained **HTML project-status summary** from the living
AIDE documents, the test suite, and (when available) project image outputs. A
**living artifact**: re-run it as development progresses and the summary extends
itself.

## When to use

- **Standalone** — a visual, high-level snapshot of project maturity: finished vs
  queued items, roadmap-stage and vision-objective alignment, test status.
- **Embedded** — as the optional final step of `/aide-feedback-loop`, or after a
  queue/roadmap run.

## What it produces

A single HTML file (default `docs/aide/status/index.html`). A typical report
includes, at minimum, these framework-derived sections:

1. **Work-Queue Overview** — finished / in-progress / upcoming items, mapped to
   roadmap stages.
2. **Roadmap phase & stage alignment** — stages with completion status and an
   overall progress bar; group stages under their `# Phase N` headers when
   `progress.md` defines phases.
3. **Vision Objective Coverage** — G-code objectives and their delivery status.
4. **Testing Overview** — test counts; pass/fail outcomes when a JUnit XML is
   supplied.
5. **Feature highlights / galleries** — image or plot galleries (extension
   points; they render a placeholder until the artifacts exist).

The generator (`scripts/aide_status_report.py`) is **project-owned** — it is not
part of the framework engine, so each project extends it with **domain-specific
panels** beyond the list above (e.g. a test-corpus coverage table, a
reference-dataset / distributions panel, QC-overlay galleries). When a panel
surfaces data derived from a **stand-in** (a synthetic cohort, a mocked
dependency), label that provenance honestly in the panel rather than implying
the real thing — mirror the "Environment-Gated Capability Verification" honesty
principle. The generator is deterministic given the same inputs (only the
timestamp varies).

## How to run

Use the project venv (bootstrap via `python .aide/scripts/aide.py env
--bootstrap` if needed). From the repo root:

```bash
.venv/Scripts/python scripts/aide_status_report.py    # Windows (Git Bash)
.venv/bin/python scripts/aide_status_report.py        # macOS / Linux
```

Options: `--out <path>`, `--junit <results.xml>` (from
`pytest --junitxml=results.xml`), `--qc-images <dir>`, `--distributions <dir>`,
`--no-embed`.

## Instructions for the agent

1. Ensure the venv is current (`python .aide/scripts/aide.py env`).
2. Optionally run pytest with `--junitxml=results.xml` first for real outcomes.
3. Run the generator with any relevant image folders.
4. Report the output path.

## Output is a per-machine artifact

The generated HTML under `docs/aide/status/` is **derived, regenerable, and
gitignored** — a committed generated file written from several machines would be
a merge-conflict hotspot. Only the generator and this skill are
version-controlled.
