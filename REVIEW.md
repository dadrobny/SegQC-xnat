# Review instructions

Review contract for pull requests in this repo. Copilot code review and
Claude Code Review read this file directly; Codex — the cloud reviewer
and the `codex review` CLI alike — applies it via the Code Review Rules
section of `AGENTS.md`; a local Claude `/code-review` subagent does
**not** read it on its own, so its prompt must hand it this file.
Reviewer routing — who reviews, and when — lives in `CLAUDE.md` under
"Code review".

## The unit of review is the item, not the PR

A PR to `main` usually carries a whole work queue: a stack of items, each
built on an `aide/NNN-…` branch and merged into the queue branch in
order. Do not review the flattened diff as one change. Every item has a
spec — `docs/aide/items/NNN-*.md`, with atomic Acceptance Criteria — and
its commits name the item. Review each item's slice of the diff against
its own spec, then check the seams: a later item quietly reworking a
contract an earlier one established, or two items editing the same file
toward different ends.

## What Important means here

CI already runs the suite on Linux, Windows and macOS, across two numpy
majors, plus a job that fails if any environment-gated test merely
skipped — so "would this test pass" is not the reviewer's question. The
reviewer is the first eye on what CI is structurally blind to. Reserve
Important for findings where a result would be wrong or silently
incomplete:

- a gate that passes while the thing it checks is absent — a test that
  degrades to a skip when its precondition quietly disappears (a git
  -history probe whose merge base advances, a capability check that
  never runs loud), or a test asserting state the loop's own verbs are
  built to move (the insight inbox's location, `aide check`'s warning
  set, a warning's line number). This repo's number-one recurring
  defect class (`docs/aide/insights.md`, items 116/128/135);
- non-determinism or platform dependence in anything regenerated,
  hashed, or byte-compared: a committed byte-reproducible fixture with
  no `.gitattributes` pin, a generator using `write_text` where
  `write_bytes` is required, subprocess output captured with
  `text=True` and no `encoding=` (use `tests/run_process.run_utf8`),
  ordering that depends on the filesystem;
- a behavioural change the spec did not name: a changed verdict, a new
  or removed finding, a threshold or calibration edit — the golden
  contract catches value drift, not an intent mismatch;
- a documented numeric or behavioural claim not measured in the same
  change (`docs/aide/insights.md`, item 125, 2026-08-30, is the shape);
- an architecture invariant broken: a rule mutating the record it
  reads, transient rule-evaluation keys (`reference`,
  `reference_delta`, `image_features`) persisted onto
  `features_block`, a new rule wired into `runner.py` instead of
  self-registering, a heavy import (NumPy/SciPy/NiBabel) hoisted to
  `cli.py` module level, `backend.py` caching its CuPy probe;
- an item's diff stepping outside its spec's authorised paths — under
  `auto-merge` the CI `scope-check` job is no signal, so the reviewer
  and the in-loop validator are the only enforcement.

Style, naming, and refactoring suggestions are Nit at most.

## Do not report

- Anything under `.aide/` or `.claude/` — installed framework files,
  owned by `dadrobny/aide-loop` and replaced wholesale by
  `install.py --update`. A real defect in them is captured as one
  `framework` line in `docs/aide/insights.md` and handed upstream,
  never fixed or flagged here.
- Completed item specs (`docs/aide/items/`) and entries in
  `docs/aide/insights.md`. Both are immutable records: a spec documents
  what its item was, an insight line is never reworded even when wrong.
  Follow-ups are new lines or new items, not edits to old ones.
- Pre-pivot language in `docs/aide/` — vision, roadmap, item specs and
  queues still describe the XNAT-era `segqc` project by design: they
  are the provenance trail, annotated rather than rewritten, until the
  re-vision lands. The retained XNAT artefacts (`command.json`,
  `docker/`, `docs/deployment.md`) await relocation, not deletion.
- Formatting and style. There is deliberately no linter or formatter;
  `pytest` is the only gate.
- Suggestions to tighten or defend `constraints.txt` for byte-identity.
  Post item 126 it is not load-bearing for that: fresh-vs-committed
  comparisons run through numeric-tolerance leaves, and a numpy-major
  change is tolerated by design.
- GPU or torch dependencies for the default install. CuPy is optional
  and probed at call time; the default install and full suite need zero
  GPU dependencies.
- Status sections, checklists, or "current focus" headings in any
  document — status lives only in `docs/aide/progress.md`.

## Always check

- Each item's diff does what its spec's Acceptance Criteria say, nothing
  beyond, and stays inside the spec's authorised paths. Hunt
  specifically for regressions the change itself introduces.
- Skip accounting is total: every `skipif` is tied to a named capability
  that the `verify-environment-gated` CI job (or an equivalent loud
  path) exercises; no new test can pass forever by never running. A new
  environment-gated capability follows `.aide/conventions.md`
  "Environment-gated capabilities".
- Determinism and portability of anything committed and regenerated: a
  new byte-reproducible text fixture is pinned in `.gitattributes`
  (`text eol=lf`, or `binary` for compressed blobs) — the `aide check`
  lint misses `read_text()`+`json.loads` shapes, so the pin is the
  reviewer's to check; generators write bytes with `\n`; subprocess
  captures pass `encoding="utf-8"`.
- Coupled edits land in the same PR:
  - the report format contract ↔ its sole source: `tests/golden/
    report_format_contract.json` regenerates only via
    `python -m tests.report_format_fixture`, never from a test
    (`tests/committed_artifact_guard.py` enforces the static half);
  - a new rule file ↔ its `HeuristicConfig` thresholds and
    `rule_enabled` wiring, self-registered, runner untouched;
  - a reference-artifact schema change ↔ its version bump and every
    delta consumer;
  - a claim added to any document ↔ the code or measurement that makes
    it true in the same PR.
- A test that reads the insight inbox also searches
  `docs/aide/insights/archive-*.md` — `aide insights archive` moves
  entries as routine housekeeping.
- Module docstrings carry an item number and often a scope fence; an
  edit extending a module against its own stated fence is a finding
  even when the code works.

## Verification bar

A behaviour claim needs a `file:line` citation in the source, not an
inference from naming. A defect report needs a concrete scenario: the
inputs or state, then the wrong outcome. Report at most five nits;
mention the rest as a count in the summary. A true finding outside the
PR's scope is one line for `docs/aide/insights.md`, not a change
request.
