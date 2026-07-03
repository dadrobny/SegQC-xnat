# CLAUDE.md — SegQC-xnat

Project-specific notes for Claude Code. The **development workflow** (the AIDE
loop, agents, claim protocol, merge policy, command hygiene, orchestrators) is a
reusable framework that lives in **[`.aide/`](.aide/README.md)** — read that
first. This file holds only what is specific to *this* repository.

## What this project is

**SegQC-xnat** is an automated quality-control tool for vertebra instance
segmentations of spine CT. It extracts geometric/topological features from label
maps, applies an explainable heuristic rule set to judge anatomical plausibility,
and emits JSON + human-readable QC reports; it is packaged for deployment as an
XNAT Container Service command. Full intent is in
[`docs/aide/vision.md`](docs/aide/vision.md); the staged plan and status are in
[`roadmap.md`](docs/aide/roadmap.md) and [`progress.md`](docs/aide/progress.md).

CPU-only, cross-platform (Windows/macOS/Linux), Python 3.9+.

## Project configuration

All framework↔project settings live in **[`aide.toml`](aide.toml)**: source/test
paths (`src/segqc`, `tests`), the venv layout and bootstrap, the test command,
the git merge mode, and loop knobs. Agents and scripts read it; edit `aide.toml`
(not the framework) to change project facts.

## Virtual environment

All code (tests, CLI, scripts) runs inside a local **`.venv`** at the project
root — gitignored, built per machine. Bootstrap or verify it with:

```
python .aide/scripts/aide.py env              # check
python .aide/scripts/aide.py env --bootstrap  # create + install if missing/stale
```

Equivalently, by hand:

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .[dev]   # Windows
```
```bash
python -m venv .venv
.venv/bin/pip install -e .[dev]       # macOS / Linux
```

Invoke Python/pytest via the venv in the relative form —
`.venv/Scripts/python -m pytest` (Windows) or `.venv/bin/python -m pytest`
(macOS/Linux). The `aide` CLI itself is stdlib-only and runs on **any** Python
3.11+ via `python .aide/scripts/aide.py …` (it must work before the venv exists).

## The framework, in one line each

- **Loop & agents** — see [`.aide/README.md`](.aide/README.md).
- **Format contract, claim protocol, command hygiene, git/clarify modes** — see
  [`.aide/conventions.md`](.aide/conventions.md). Follow the command-hygiene rules
  there or unattended runs stall on permission prompts.
- **Document templates** — [`.aide/templates/`](.aide/templates/).
- **CLI** — `python .aide/scripts/aide.py {check,progress,queue,claim,merge,env}`.
- **Skills / commands** — `/aide-*` (create-vision … feedback-loop, spec-queue)
  and the `/aide-run-{item,queue,roadmap}` orchestrators.

## Shared vs. personal

- **Shared (committed):** `.aide/` (minus `loop/loop.local.toml`), `aide.toml`,
  `.claude/{agents,commands,skills,hooks,settings.json}`, `CLAUDE.md`,
  `docs/aide/` living documents.
- **Personal (git-ignored):** `.aide/loop/loop.local.toml`,
  `.claude/settings.local.json`, `docs/aide/permissions/*.jsonl`,
  `docs/aide/status/*`, credentials. Never commit credentials.

Framework/process changes (`.aide/**`, `aide.toml`, `CLAUDE.md`, `vision.md`,
`roadmap.md`, `.claude/**`) land via a **reviewed PR**; work-item execution
merges straight to `main` per the merge policy in `.aide/README.md`.
