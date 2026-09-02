# CLAUDE.md — FACET

Project-specific notes for Claude Code. The **development workflow** (the AIDE
loop, agents, claim protocol, merge policy, command hygiene, orchestrators) is a
reusable framework that lives in **[`.aide/`](.aide/README.md)** — read that
first. This file holds only what is specific to *this* repository.

## What this project is

**FACET** (Failure Analysis, Characterisation & Evaluation Toolkit) analyses
instance segmentations of spine imaging. It extracts geometric/topological/
intensity features from label maps, fabricates deliberately-broken label maps
carrying a machine-readable record of *what* was broken, scores cases against
reference distributions built from ground truth, and applies an explainable
heuristic rule set that emits JSON + human-readable reports.

> **⚠️ Pivot in progress (2026-07-25).** This repo was `SegQC-xnat`, an
> XNAT-deployed QC gate. It is being refocused as the torch-free library half of
> a failure-mode-driven segmentation-improvement research programme; the GPU /
> SPINEPS / GSTT half lives in a separate private repo. **This rename landed
> first; the AIDE re-vision has not happened yet** — so `docs/aide/` (vision,
> roadmap, progress, 88 item specs, 12 queues) still describes the XNAT project
> and still says `segqc` throughout. That is deliberate: those documents are the
> provenance trail and are annotated, not rewritten. Treat them as history until
> the re-vision lands. XNAT artefacts (`command.json`, `docker/`,
> `docs/deployment.md`) are retained pending relocation to the programme repo.

CPU-only, cross-platform (Windows/macOS/Linux), Python 3.9+.

## Project configuration

All framework↔project settings live in **[`aide.toml`](aide.toml)**: source/test
paths (`src/segfacet`, `tests`), the venv layout and bootstrap, the test command,
the git merge mode, and loop knobs. Agents and scripts read it; edit `aide.toml`
(not the framework) to change project facts. It also carries `[framework] repo`
(where `framework`-typed insights are handed over) and `[validation]` — named
environment profiles (`pyradiomics`, `docker`, `gpu`) that
`aide env --profile <name>` evaluates so a stage validation gated on an absent
capability records **❓ Unverified** instead of silently passing.

**`.claude/settings.json` is a generated artifact.** This repo has adopted
[`.claude/settings.overlay.json`](.claude/settings.overlay.json), so every
`install.py --update` regenerates `settings.json` as a deterministic deep-merge
of the framework default and that overlay. Edit the **overlay**, never
`settings.json` — including permission rules promoted by
`/aide-review-permissions`, which belong in the overlay's
`permissions.allow.add` list. The `src/segfacet/**` and `tests/**` write-scope
globs are templated from `aide.toml` and need no override.

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

## Common commands

```bash
# Full suite (from repo root, venv already bootstrapped)
.venv/bin/python -m pytest                                   # macOS/Linux
.venv\Scripts\python -m pytest                                # Windows

# One file / one test
.venv/bin/python -m pytest tests/test_035_cli_e2e.py
.venv/bin/python -m pytest tests/test_035_cli_e2e.py::test_name -v

# CLI, once installed editable (`pip install -e .[dev]`)
segfacet run --scan scan.nii.gz --seg seg.nii.gz --out out/       # QC one case
segfacet build-reference --cohort cohort/ --out reference.json    # Stage 6 artifact
segfacet evaluate --cohort manifest.json --out out/ [--calibrate] # Stage 7 harness
```

CI (`.github/workflows/ci.yml`) installs with `pip install -e .[dev] -c
constraints.txt` (the Stage-9 Docker lockfile) rather than `pyproject.toml`'s
loose bounds. **Note what the golden tests actually assert** (post item 126's
golden retirement): the committed whole-record report snapshots are gone; the
report *format* (key order, key set, float rendering) is pinned by the
hand-written, feature-value-free `tests/golden/report_format_contract.json`
(sole source: `tests/report_format_fixture.py`; regenerate with
`.venv/bin/python -m tests.report_format_fixture`, never from a test). Byte
(`read_bytes()`) comparisons are *run-to-run within one session* — a
**determinism** check, independent of dependency versions. Fresh-vs-committed
comparisons go through `segfacet.synth.golden.assert_matches_committed_artifact`
(numeric-tolerance leaves per item 078, everything else exact), statically
enforced by `tests/committed_artifact_guard.py` (item 127). So
`constraints.txt` is not load-bearing for byte-identity, and a numpy-major
change is tolerated (verified 2026-07-25: green on numpy 1.26.4, previously
pinned 2.0.2); a genuine change — a changed verdict, a new or removed finding,
a meaningfully different feature value — is still caught. Two **environment-gated** capabilities (PyRadiomics, Docker) skip
cleanly when their dependency is absent; a second CI job
(`verify-environment-gated`) installs both and fails if any gated test merely
skipped instead of running — see `.aide/conventions.md` "Environment-gated
capabilities" before adding a new one. There is no configured linter/formatter
(no ruff/black/mypy) — `pytest` is the only gate.

## Architecture

`segfacet` extracts label-map features, runs an explainable rule engine over
them, and aggregates the findings into a verdict. The stage numbers below
match `docs/aide/roadmap.md`/`progress.md` and the `NNN-*` work-item/test
prefixes (`tests/test_0NN_*.py`) — when in doubt which stage a module belongs
to, its docstring names the item number.

- **Entry points** (`cli.py`): three subcommands — `run` (single-case QC),
  `build-reference` (Stage 6, builds a versioned reference-distribution
  artifact from a cohort), `evaluate` (Stage 7, runs a cohort through the
  pipeline and reports aggregate metrics, optionally calibrating rule
  thresholds). All handlers defer heavy imports (NumPy/SciPy/NiBabel) into the
  function body so `segfacet --help` stays fast.
- **`pipeline.py`** is the orchestration seam: `extract_feature_record` calls
  the Stage 2/3 extractors under `features/` and assembles them (via
  `feature_report.build_features_block`) into one per-case `features` dict —
  the single record shape every rule is written against. `run_qc` /
  `run_qc_with_reference` / `run_qc_with_intensity` layer on top, attaching
  optional `reference` / `reference_delta` / `image_features` keys to a
  *transient* rule-evaluation record (never persisted back onto
  `features_block`) before calling `heuristics.run_rules`.
- **`features/`** — pure, stateless extractors over a NiBabel label map (and,
  for intensity/radiomics, the paired scan): per-label geometry, connected
  components, centroids, case-level relationships/overlaps (Stage 2), then
  centroid-spline fit, per-label spline offset, orientation/curvature,
  spacing/monotonic consistency (Stage 3, only computed when ≥2 labels are
  present), plus intensity/radiomics (Stage 8, `radiomics.py` degrades to a
  builtin first-order-only backend when PyRadiomics isn't installed).
- **`heuristics/`** — the rule engine (Stage 4). `rule.py` defines the `Rule`
  ABC and a module-level registry (`register_rule`/`iter_rules`, sorted by
  `rule_id`); each concrete file (`bounds.py`, `overlap.py`, `mislabel.py`,
  `fragmentation.py`, `coverage.py`, `sequence.py`, `border.py`,
  `intensity.py`, `reference_delta.py`, `intensity_reference_delta.py`)
  registers one rule that reads the `features` record plus `HeuristicConfig`
  thresholds and returns zero or more `Finding`s. `runner.run_rules` executes
  all enabled rules (`config.rule_enabled(rule_id)`) in deterministic order
  and never mutates the record — adding a new rule means adding a new file
  that self-registers, not touching the runner.
- **`aggregate.py` / `verdict.py`** fold `Finding`s (plus Stage-1
  `check_empty` base reasons) into a `CaseResult`/`Verdict` with an overall
  `Severity` (pass / flagged-for-review / fail); `report.py` /
  `human_report.py` serialize that into the JSON and plain-text reports the
  CLI writes.
- **`reference/`** (Stage 6) — ingests a cohort (`ingest.py`), aggregates
  per-label geometric (and, Stage 8, intensity) distributions into a
  `ReferenceDistribution` (`aggregate.py`, `schema.py`), versions it as a JSON
  artifact (`artifact.py`), and computes a case's delta-to-reference
  (`delta.py`) that the `reference_delta`/`intensity_reference_delta` rules
  consume.
- **`eval/`** (Stage 7) — a separate cohort-level harness, not the per-case
  rule engine: `harness.py` runs `pipeline.run_qc*` over every case in a
  manifest (`cohort.py`), `outcome.py`/`overlap.py`/`feature_match.py` compare
  against expected verdicts/ground truth, `metrics.py` aggregates
  FPR/FNR/etc., and `calibrate.py` grid-searches rule thresholds against those
  metrics; `report.py` renders the `segfacet evaluate` output.
- **`backend.py`** (Stage 10) — resolves `"cpu"`/`"gpu"`/`"auto"` (precedence:
  explicit override → `SEGFACET_BACKEND` env var → `"auto"`) to a NumPy- or
  CuPy-backed array-module handle. CuPy is probed with a guarded `import`
  inside the function body on every call (never cached at import time) so
  tests can inject/remove a fake `cupy` module in `sys.modules`. The default
  install and full test suite need **zero** GPU dependencies.
- **`synth/`** (Stage 5) — synthetic failure-corpus generators (deliberately
  broken label maps: fragmentation, coverage/border/overlap defects, identity
  /ordering/alignment issues) used by the regression suite; distinct from
  `tests/synthetic.py`, which builds well-formed happy-path fixtures for unit
  tests (see the README's "Testing & synthetic fixtures" section).

Nearly every stage's module docstring documents its item number, design
decisions, and explicit non-goals ("Scope fence") — read the module docstring
before extending it; the reasoning for *why* it's shaped that way is usually
already written down there rather than in `docs/aide/`.

## The framework, in one line each

- **Loop & agents** — see [`.aide/README.md`](.aide/README.md).
- **The contract** — [`.aide/conventions.md`](.aide/conventions.md), an index:
  `§N` resolves to a file under [`.aide/conventions/`](.aide/conventions/). The
  CLI verbs, command hygiene, and the insight-inbox protocol are delivered into
  every session by `.aide/AGENT-CONTEXT.md` (imported below) and
  `.claude/rules/aide-command-hygiene.md` — this file does not restate them.
- **Document templates** — [`.aide/templates/`](.aide/templates/).
- **One project-specific note on `aide scope`:** the CI `scope-check` job in
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml) invokes it directly —
  see "Branching" below for why it is currently no signal.
- **Skills / commands** — `/aide-*` (create-vision … feedback-loop, spec-queue),
  the `/aide-run-{item,queue,roadmap}` orchestrators, and the
  `/aide-review-{permissions,instructions}` boundary reviews.

## Updating the framework (the `aide-loop` repo)

The framework is **not maintained in-tree here** — it is developed in the
standalone **`aide-loop`** repo — `github.com/dadrobny/aide-loop`, recorded as
`[framework] repo` in [`aide.toml`](aide.toml) — and *materialised* here by its
installer. Where *your* checkout lives is per-machine and deliberately not
recorded in any shared file; the commands below write it as `$AIDE_LOOP`
(Windows: `$env:AIDE_LOOP`). Set it once per shell, or substitute your own path
inline. In `aide-loop`, `core/` is the
provider-agnostic engine (→ `.aide/`) and `adapters/claude/` is the Claude
adapter (→ `.claude/`). **Never hand-edit `.aide/**` or the `aide-*` files under
`.claude/**` in this repo** — they are generated, and a manual edit is silently
overwritten on the next update.

To find out whether this repo is behind the framework, compare versions — it
writes nothing and exits non-zero when behind:

```bash
python "$AIDE_LOOP/install.py" --into . --check
```

`.aide/VERSION` records the installed engine; `aide-loop`'s `CHANGELOG.md` says
what each version changed. The framework bumps its version on every commit that
touches what a consumer installs, so a matching version now genuinely means
up to date.

**Read `$AIDE_LOOP/CLAUDE.md` before changing anything there — it is not in
context.** An agent's instruction files are loaded for the *working directory's*
repo only: this file is read automatically, `aide-loop`'s is not, even though it
is a declared additional working directory. So a session that edits the framework
from here has none of that repo's rules in hand, and they are not inferable from
its code. At minimum it carries a versioning rule enforced by its own suite
(any commit touching `core/` or `adapters/` must bump `core/VERSION` *and* add a
`CHANGELOG.md` entry), a PR-only merge policy, and one trap worth stating twice:
paths like `.aide/…` and `python .aide/scripts/aide.py …` appearing inside
`core/` and `adapters/` are **consumer** paths and are correct — never "fix" them
to that repo's own layout.

The same applies to any sibling repo in this workspace — the rule, the approved
command shapes, and the `sibling_instructions.py` reminder hook are all §8
(`.aide/conventions/8-sibling-repos.md`).

Clean workflow to change the framework (no push required — the installer copies
from the local working tree):

1. **Edit + test in `aide-loop`.** Change `core/…` or `adapters/claude/…`; run its
   suite (`python -m pytest`, stdlib-only core + pytest). Bump `core/VERSION` for
   an engine change. Commit on a branch there.
2. **Reinstall into this repo** from the local checkout:
   ```bash
   python "$AIDE_LOOP/install.py" --adapter claude --into . --update
   ```
   `--update` re-copies the engine + adapter but **never touches `aide.toml` or
   `docs/aide/`** (project-owned). Because this repo has adopted
   `.claude/settings.overlay.json`, `settings.json` is **regenerated** from
   framework-base + overlay on every run — so it needs no reconciliation and no
   `.aide-merge` is emitted; put project-specific permission rules in the
   overlay.
3. **Review the `git diff`** — it should be exactly the intended change (most
   copied files are byte-identical no-ops git shows nothing for). Run the suite.
4. **Land via a reviewed PR** (framework/process files are PR-gated — see the last
   paragraph of this file). Pushing the change to `aide-loop`'s own remote is a
   separate, optional step for sharing the framework itself.

## Gotchas

- **Byte-reproducible committed fixtures need a `.gitattributes` LF pin.** This
  repo commits generated data whose tests assert byte-identity between a
  regenerated file and its committed copy (`tests/corpus/manifest.json`,
  `tests/golden/report_format_contract.json`; items 040/126). On Windows, `core.autocrlf=true`
  rewrites committed LF text to CRLF **on checkout**, so a file that was byte-clean
  when committed fails its own determinism test after a fresh checkout (e.g. during
  `aide merge`'s branch switch). Any new committed byte-reproducible text fixture
  **must** be pinned in [`.gitattributes`](.gitattributes) with `text eol=lf` (or
  `binary` for compressed blobs like `.nii.gz`), and the generator should write
  bytes with `\n` (`write_bytes`, not `write_text`, since Python 3.9 can't set
  `newline=` on `Path.write_text`). Engine 1.19.0 gave the rule a lint: `aide
  check` resolves a fixture path through the test's AST and warns when nothing in
  `.gitattributes` covers it. **That lint says nothing about either fixture named
  above**, and its two silences are §6's to explain, not this file's: both are
  read with `read_text()` and parsed with `json.loads`, the shape §6 records as
  immune and therefore unreported whether or not it is pinned. Their pins are
  held by this gotcha and by `tests/test_111_golden_guard.py`; drop one and
  Windows fails with no warning anywhere.
- **A test that reads the insight inbox must also search its archives.** `aide
  insights archive` moves closed entries from `docs/aide/insights.md` to
  `docs/aide/insights/archive-YYYY-QN.md` as routine housekeeping, so a test
  asserting a captured claim's presence must search the inbox *and* every
  `insights/archive-*.md` (the contract is that the claim survives verbatim and
  ticked — not which of the two files holds it). `tests/test_117_scope_verb_swap.py`'s
  AC4 tests are the worked example; pinning the live inbox alone turns an
  archive sweep into a red suite. Same defect class as pinning a warning's line
  number: asserting what the loop's own verbs are built to move.
- **`segfacet run` with no reference flag runs against the real-VerSe19
  reference by default** (item 090), which is not calibrated for the tiny
  synthetic corpus fixtures — a bare CLI run on `clean_control_seg.nii.gz`
  reports ~40 `bounds`/`reference_delta` findings and `flagged-for-review`,
  not the "zero findings, pass" the corpus documentation describes. To
  reproduce a stage's "clean control fires nothing end-to-end" claim via the
  CLI, pass `--no-reference` (measured 2026-08-30, item 125). Not a
  regression; it is the documented default operating out of its calibration.
- **A "fails before the fix" replay needs a separate clone with its own venv**,
  not a second tree pointed at by `PYTHONPATH` from the working checkout:
  `pip install -e .` installs a meta-path finder that resolves `segfacet`
  ahead of `sys.path`, so the second tree is silently shadowed by the working
  checkout's `src/` and every "pre-fix" result is invalid with no error at
  all. `git switch --detach` in the working checkout avoids the shadowing but
  detaches HEAD mid-item. Item 135's per-defect verification rig (fresh clone
  plus its own venv) is the worked example (2026-08-31).

## What is committed vs. per-machine

The ownership split is the framework's — see "Shared vs. personal" in
[`.aide/README.md`](.aide/README.md) and the managed AIDE block at the end of
[`.gitignore`](.gitignore). One rule worth restating anywhere: never commit
credentials.

## Branching, and what it means for the scope check

Framework/process changes (`.aide/**`, `aide.toml`, `CLAUDE.md`, `vision.md`,
`roadmap.md`, `.claude/**`) land via a **reviewed PR**. Work-item execution
follows the merge policy in [`.aide/README.md`](.aide/README.md). Two settings
vary independently, and conflating them is easy:

**1. Where an item lands (the branch shape).** `aide claim` branches from
whatever is checked out and *records that base*; `aide merge NNN` returns the
item there. So both shapes work with no flag and no config:

```
main                          main
 └── aide/NNN-item             └── aide/queue-NNN        ← one reviewed PR per stage/queue
                                    ├── aide/NNN-item-a  ← claimed from the queue branch,
                                    └── aide/NNN-item-b     merged back into it
```

The stacked shape on the right keeps `main` cohesive — one review per batch
instead of per item — and is what engine 1.8.0's `--base` was built for.
Inference is narrow by design: only a recognised `aide/queue-NNN` /
`aide/specs-queue-NNN` branch is inferred as a base, never an arbitrary
checked-out branch.

**2. Whether a PR is opened per item (`[git] mode` in `aide.toml`).** Currently
**`auto-merge`**. What each mode does — and what ✅ versus 🔍 mean — is §4
(`.aide/conventions/4-git-modes.md`) and §1 → status-icons; this file only
records which mode this repo runs.

**The consequence for CI.** The `scope-check` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml) fires only on a
`pull_request` whose `head_ref` is an `aide/NNN-` claim branch. Under **`pr`**
mode that is exactly what appears, and the job works as designed — including
against a queue branch, since it passes `origin/${{ github.base_ref }}`. Under
**`auto-merge`** (and `local`) no item branch ever becomes a PR, so the job
matches nothing: a queue PR's head is `aide/queue-NNN`, which the anchored
`sed` resolves to nothing **by design**, because a queue branch legitimately
aggregates many items' authorised paths.

So *while this repo stays on `auto-merge`*, a green `item scope check` means
**skipped, not passed** — treat it as no signal. Per-item scope is still
enforced, by `validator.md` step 3 running `aide scope` in-loop. Evidence and
the three options are recorded in
[`docs/aide/insights.md`](docs/aide/insights.md) (2026-08-20, item 117);
switching to `pr` mode is one of the things that would resolve it.

@.aide/AGENT-CONTEXT.md
