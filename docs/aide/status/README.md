# AIDE project-status report

This directory holds the generated **HTML project-status summary** produced by
`scripts/aide_status_report.py` (driven by the `/aide-status-report`
skill). It is a *living* artifact: regenerate it as development progresses.

## Generate

```bash
# Windows (Git Bash)
.venv/Scripts/python scripts/aide_status_report.py
# macOS / Linux
.venv/bin/python scripts/aide_status_report.py
```

This writes `index.html` here. Open it in a browser for a high-level snapshot of
work completed, work queued, roadmap-phase and vision-objective alignment, the
test suite, and QC feature highlights. See the `aide-status-report` skill
for options (`--junit`, `--qc-images`, `--distributions`).

## Files

| File | Tracked? | Purpose |
|---|---|---|
| `README.md` | committed | this file |
| `index.html` | **gitignored** | generated status page (per-machine, regenerable) |
| `*.png`, `*.svg` | **gitignored** | any embedded/referenced QC or distribution images |

The generated output is gitignored on purpose: a committed generated file written
from several machines would be a constant merge-conflict hotspot (like
`progress.md` and the permission logs). Only the generator and skill are shared,
via the normal PR; everyone regenerates the HTML locally.
