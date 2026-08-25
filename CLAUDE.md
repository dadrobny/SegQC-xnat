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
loose bounds. **Note what the golden tests actually assert** (items 042/045/063):
every `read_bytes()` comparison is *run-to-run within one session* (`dest1` vs
`dest2`) — a **determinism** check, independent of dependency versions.
Comparison against the **committed** artifacts goes through `reports_close`, a
**numeric-tolerance** comparison, deliberately relaxed by item 078 because
full-precision floats differ by ~1 ULP across platforms. So `constraints.txt` is
not load-bearing for golden byte-identity, and a numpy-major change is tolerated
(verified 2026-07-25: green on numpy 1.26.4, previously pinned 2.0.2). Structure,
keys, strings, bools and ordering are still compared exactly, so a genuine change
— a changed verdict, a new or removed finding, a meaningfully different feature
value — is still caught. Two **environment-gated** capabilities (PyRadiomics, Docker) skip
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
- **Format contract, claim protocol, command hygiene, git/clarify modes** — see
  [`.aide/conventions.md`](.aide/conventions.md). Follow the command-hygiene rules
  there or unattended runs stall on permission prompts.
- **Document templates** — [`.aide/templates/`](.aide/templates/).
- **CLI** — `python .aide/scripts/aide.py
  {check,progress,gate,queue,claim,merge,env,sync,gc,status,scope,insights}`. If
  a verb covers it, the raw git form is wrong: session preflight is `sync`, branch
  clean-up is `gc`, the state report is `status`, the item's diff-vs-scope
  check is `scope` — the CI job's `scope-check` step (`.github/workflows/ci.yml`)
  invokes it directly — and a queue branch is created by `queue start NNN`, never
  by a hand-typed `git switch -c`. `check --queue NNN` adds the cross-spec checks;
  `gate` resolves human gates, and only a person may run it.
- **Insight inbox** — [`docs/aide/insights.md`](docs/aide/insights.md): append a
  one-line `- [ ] <type> — …` when you learn something out of scope, then return
  to your task. Triaged at the queue boundary by `/aide-feedback-loop`, which
  reads the backlog with `aide insights list --open` and closes an entry with
  `aide insights tick N --pointer "<where it landed>"` rather than hand-editing
  the file; `aide insights archive --before YYYY-MM-DD` moves closed entries out
  to `docs/aide/insights/archive-YYYY-QN.md`.
- **Skills / commands** — `/aide-*` (create-vision … feedback-loop, spec-queue)
  and the `/aide-run-{item,queue,roadmap}` orchestrators.

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

The same applies to any sibling repo in this workspace — it is
[`.aide/conventions.md`](.aide/conventions.md) §8: a repository's own
instructions bind for work inside it, and where two repos disagree about a file,
the repo that owns the file wins. Engine 1.18.0 added a reminder, not a
substitute: `.claude/hooks/sibling_instructions.py` points a session at a
declared sibling's instruction file the first time it touches a path inside that
repo. It delivers a *pointer*, once per repo per session, and never gates a tool
call — reading the file is still on you. The repos it knows about are the ones
named in the gitignored `.aide/loop/loop.local.toml` (`[framework] local_path`
and `[hygiene] extra_repos`); a sibling missing from that file gets no reminder
at all.

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
  `tests/corpus/golden/*.json`; items 040/042). On Windows, `core.autocrlf=true`
  rewrites committed LF text to CRLF **on checkout**, so a file that was byte-clean
  when committed fails its own determinism test after a fresh checkout (e.g. during
  `aide merge`'s branch switch). Any new committed byte-reproducible text fixture
  **must** be pinned in [`.gitattributes`](.gitattributes) with `text eol=lf` (or
  `binary` for compressed blobs like `.nii.gz`), and the generator should write
  bytes with `\n` (`write_bytes`, not `write_text`, since Python 3.9 can't set
  `newline=` on `Path.write_text`). Engine 1.19.0 gave the rule a lint: `aide
  check` resolves a fixture path through the test's AST and warns when nothing in
  `.gitattributes` covers it. It is precise rather than exhaustive by design — a
  path reached through `tmp_path`, a function argument or an imported constant
  resolves to nothing and is skipped in silence — so a warning is authoritative
  and its absence is not a clean bill of health.

## Durable artifacts must read cold

Anything that outlives the session it was written in — item specs, commit
messages, `insights.md` entries, `aide-loop` issues, code comments — has to make
sense to someone who never saw the conversation that produced it. Its context is
this repo and its tracker, not a chat log.

- **No chat-local identifiers.** Labels coined for conversational convenience
  ("A1–A4", "Wave 1", "the D-series") are scaffolding, not names. A reader sees
  "A1" and cannot tell what the A-series was or what happened to B. Name a thing
  by what it *is*, and title by the change, not the batch it was scheduled in.
- **Cross-reference by resolvable identity** — `#25`, a file path, a dated
  `insights.md` entry. Never "the conventions issue" or "the companion PR",
  which resolve only inside the conversation.
- **Record the decision and why it holds, not the route to it.** "My earlier
  lean was wrong", "agreed direction", "settled while drafting" narrate process
  and age badly.

Reread anything before publishing as a person who has never seen the session:
every identifier must be defined in the document or resolvable in the repo.

## Shared vs. personal

- **Shared (committed):** `.aide/` (minus `loop/loop.local.toml`), `aide.toml`,
  `CLAUDE.md`, `docs/aide/` living documents, and under `.claude/`: `agents/`,
  `commands/`, `skills/`, `hooks/`, `scripts/`, `settings.json`,
  `settings.overlay.json` and `default-context.json`.
- **Personal (git-ignored):** `.aide/loop/loop.local.toml`,
  `.claude/settings.local.json`, `docs/aide/permissions/*.jsonl`,
  `docs/aide/status/*`, credentials. Never commit credentials.

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
`auto-merge`. Per [`.aide/conventions.md`](.aide/conventions.md) §4:

| mode | on validator PASS | item status after | item branch becomes a PR? |
|---|---|---|---|
| `auto-merge` *(current)* | direct-merges to the recorded base, deletes the branch | ✅ | no |
| `pr` | pushes and stops for a human to open the PR | 🔍 until the PR lands | **yes** |
| `local` | local merge, no pushes at all | ✅ | no |

Engine 1.20.0 split those two outcomes apart. The validator now marks every item
`in-review` (🔍) regardless of mode, and **`aide merge` writes ✅ only when the
merge actually happens** — so ✅ means *merged* everywhere, and a 🔍 item holds
its stage at 🚧 and its queue open. That matters most for `aide gc`, whose ✅
ground deletes a branch locally *and* on the remote; before 1.20.0 a `pr`-mode
item read ✅ the moment it was pushed, so the exhaustion sweep offered to delete
the head branch of an open PR. Nothing under `auto-merge` — this repo's current
mode — changes behaviour. Since nothing inside the loop observes a merge that
happens on the forge, `aide sync`/`aide status` name any 🔍 item whose work has
since landed in its base and print the `aide progress set NNN done` that closes
it.

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
