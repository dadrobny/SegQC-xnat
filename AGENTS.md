# AGENTS.md — SegFACET

This repo **uses** the AIDE framework; it is not the framework. `.aide/`
and `.claude/` are installed copies from `dadrobny/aide-loop`, replaced
wholesale by `install.py --update` — never edit them here, and never
report them in review; a defect in them becomes a `framework` line in
`docs/aide/insights.md` and is handed upstream.

What the project is: **FACET**, a CPU-only, torch-free library that
analyses instance segmentations of spine imaging — feature extraction
over label maps, a synthetic failure corpus, reference distributions,
and an explainable heuristic rule engine. `README.md` and `CLAUDE.md`
orient; `docs/aide/` (vision, roadmap, progress) is the source of truth
for scope, plan and status — noting that its pre-pivot documents still
describe the XNAT-era `segqc` project as deliberate provenance. Source
lives in `src/segfacet/`, tests in `tests/`; the suite runs as
`.venv/bin/python -m pytest` and must pass cross-platform (Windows,
macOS, Linux) with no GPU — PyRadiomics and Docker are environment
-gated capabilities that skip cleanly when absent.

## Code Review Rules

Apply `REVIEW.md` at the repo root — it defines the review unit,
severity, what to check, and what not to report. Non-negotiable
highlights:

- Review item by item against `docs/aide/items/NNN-*.md`, not the
  flattened queue diff.
- Never flag `.aide/…` or `.claude/…` files, completed item specs,
  `docs/aide/insights.md` entries, or `docs/aide/`'s pre-pivot XNAT
  language — installed, immutable, or provenance by design.
- Important = a result that would be wrong or silently incomplete:
  tests that degrade to a silent skip, false-negative gates,
  non-determinism or Windows/platform traps in anything regenerated or
  byte-compared (missing `.gitattributes` pins, subprocess captures
  without `encoding=`), verdict or threshold changes the item's spec
  did not name, diffs outside the spec's authorised paths.
- No style, formatting, linter, or dependency-upgrade suggestions —
  there is deliberately no linter, and `pytest` is the only gate.
