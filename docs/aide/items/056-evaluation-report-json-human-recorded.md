# Item 056 — Evaluation report (JSON + human) & recorded calibrated results

> **Created:** 2026-07-12 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (*Phase 1 complete*)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 056
> **Objectives:** G3 (distinguish failure from variation — low FPR on GT), G4 (per-case → cohort QC report, JSON + human), G7 (evaluable / regression-testable)
> **Suggested branch:** `aide/056-evaluation-report-json-human-recorded`

---

## Description

Render the Stage-7 cohort **metrics** (item 054, `CohortMetrics`) and the chosen
**calibration** outcome (item 055, `CalibrationResult`) into a versioned
**evaluation report** — a schema-versioned machine-readable **JSON** plus a
**human-readable** plain-text rendering of the same numbers — and provide the
**persistence mechanism** for the calibrated results: (1) a byte-reproducible
JSON report artifact carrying provenance, and (2) a way to write the chosen
thresholds into a versioned `HeuristicConfig` file that round-trips through
`load_config`.

This is the Stage-7 analogue of the Stage-1 per-case report (`segqc.report`,
items 009/010): a new module **`src/segqc/eval/report.py`** that mirrors the
established conventions — a bundled versioned JSON schema loaded via
`importlib.resources` and validated on every serialise (item 009), a stdlib-only
plain-text renderer (item 010), and the byte-reproducible, caller-supplied-
`build_date` artifact write of `segqc.reference.artifact` (items 043/045).

**What "recorded calibrated results" means here (scope split — read carefully).**
The queue one-liner says this item writes the headline metrics into
`progress.md`'s "Calibrated metrics" block. In this framework that block is
filled at **Stage-7 completion**, which is item **057**'s job (queue-006:
"Record the final calibrated numbers in `progress.md`'s 'Calibrated metrics'
block and mark Phase 1 complete"), and `progress.md` is edited via the `aide`
CLI by the builder/validator — never hand-edited in a spec/build. `roadmap.md`
is additionally a **PR-gated framework/process file** (per `CLAUDE.md`), so it
cannot be touched by this item's direct-merge work item at all. Therefore item
056's "recording" is strictly **the production of the persistable artifacts** —
the versioned JSON evaluation report and the calibrated-config file — which are
the machine-readable substrate that item 057 (and its Stage-7-closing reviewed
PR) transcribes into `progress.md`. This item writes **no** `progress.md` and
**no** `roadmap.md` edits.

**In scope.**
- A versioned JSON evaluation-report **schema** (`eval_report_schema_v0.json`),
  bundled as `segqc.eval` package data.
- `build_evaluation_report(metrics, provenance, *, calibration=None)` → a
  schema-validated report dict bundling `CohortMetrics` + provenance + an
  optional calibration summary.
- A byte-reproducible JSON serialiser/writer for that report.
- A stdlib-only human-readable plain-text renderer of the same report.
- `record_calibrated_config(...)` — apply the chosen thresholds onto a
  `HeuristicConfig` (via item 055's `apply_assignment`) and write it as a YAML
  config that round-trips through `load_config`.

**Out of scope (fenced).**
- No `segqc evaluate` CLI subcommand / entry point, no cohort assembly, and no
  Stage-7 acceptance suite — that is item **057**.
- No new metrics maths (reuse 054) and no new calibration logic (reuse 055).
- No mutation of the **shipped** `src/segqc/default_config.yaml` — the recording
  mechanism writes to a **caller-supplied path**; whether the shipped default is
  overwritten with real calibrated numbers is item 057's decision (behind its
  acceptance suite and the reviewed PR).
- No `progress.md` / `roadmap.md` edits (see the scope split above).
- No pipeline execution or label-map I/O of its own.

## Acceptance Criteria

_Each criterion atomic, observable, and directly testable — one test per AC._

- [ ] **AC1: A versioned evaluation-report schema ships as package data.** A JSON
  schema file `eval_report_schema_v0.json` lives alongside `segqc.eval` and is
  loadable via `importlib.resources` (mirroring `segqc.report._load_schema`); it
  declares a top-level `schema_version` discriminator with the constant value
  `"0.1"` and requires the keys `schema_version`, `provenance`, and `metrics`.

- [ ] **AC2: `build_evaluation_report` bundles metrics + provenance into a
  schema-valid dict.** Given a `CohortMetrics` (item 054) and an
  `EvaluationProvenance`, `build_evaluation_report(...)` returns a plain dict
  with `schema_version == "0.1"`, a `provenance` block, and a `metrics` block
  equal to `metrics.to_dict()`; the returned dict validates against the bundled
  schema (validated inside the call, as `serialize_report` does).

- [ ] **AC3: The calibration block is optional.** When a `CalibrationResult`
  (item 055) is passed, the report dict has a `calibration` key summarising the
  chosen outcome; when `calibration` is omitted (`None`), the report has **no**
  `calibration` key and still validates against the schema.

- [ ] **AC4: Provenance is captured and cohort size is consistent.** The
  `provenance` block carries a cohort identity string, `cohort_size`, a
  `config_version`, and a caller-supplied `build_date`; `cohort_size` equals
  `metrics.n_cases`, and `config_version` equals the supplied
  `HeuristicConfig.schema_version`.

- [ ] **AC5: `build_date` is caller-supplied, never wall-clock.** Building a
  report twice with the same inputs (including the same `build_date`) yields
  equal `provenance.build_date`; the module reads no wall clock (no
  `date.today()` / `datetime.now()` in the build path), so identical inputs give
  identical output.

- [ ] **AC6: The report exposes the three headline metrics.** From a built
  report dict the false-positive rate on GT, the per-§6-mode sensitivity
  entries, and the DICE-vs-flag correlation coefficient are all reachable at
  documented JSON paths (under `metrics`) and equal the corresponding
  `CohortMetrics` fields.

- [ ] **AC7: The report exposes the chosen thresholds when calibrated.** When a
  feasible `CalibrationResult` is passed, the `calibration` block exposes the
  chosen threshold assignment (`best.assignment`) and the metrics that
  assignment achieved (`best.metrics`), plus the calibration `status`.

- [ ] **AC8: Schema validation rejects a malformed report.** Passing a report
  dict missing a required key (e.g. `provenance`) to the serialise/validate
  entry point raises `jsonschema.ValidationError` (never silently produces an
  invalid artifact).

- [ ] **AC9: JSON serialisation is deterministic / byte-reproducible.** The JSON
  serialiser (`serialize_evaluation_report_json` and/or `write_evaluation_report`)
  produces byte-identical output across repeated calls on the same inputs (keys
  sorted, UTF-8, exactly one trailing `"\n"`), and a written artifact round-trips
  through `json.loads` back to the built dict.

- [ ] **AC10: A human-readable rendering reproduces the same numbers.**
  `render_evaluation_report(...)` returns a non-empty plain-text string that
  contains the same FPR, per-mode sensitivity, and DICE-vs-flag correlation
  values as the JSON report (and the chosen threshold assignment when a
  calibration result is supplied); it contains no raw Python class names,
  dataclass `repr()`, tuples, or enum reprs (same discipline as `human_report`).

- [ ] **AC11: The human renderer handles `None` metric sentinels.** When a
  metric is `None` (e.g. FPR with no expected-pass cases, or a correlation
  coefficient with fewer than two usable pairs — item 054's documented
  sentinels), the rendering shows an explicit placeholder (e.g. `"n/a"`) rather
  than the string `"None"` or raising.

- [ ] **AC12: Recording writes calibrated thresholds into a config that
  round-trips.** `record_calibrated_config(base_config, calibration_result,
  axes, path)` writes a YAML `HeuristicConfig` with `best.assignment` applied
  (via item 055's `apply_assignment`) to `path`; `load_config(path)` yields a
  config whose swept parameters equal the chosen values and whose other fields
  equal those of `base_config` (load → same values).

- [ ] **AC13: Recording is byte-reproducible.** Writing the same calibrated
  config to two paths yields byte-identical files (canonical key order, UTF-8,
  `"\n"` line endings via `Path.write_bytes`).

- [ ] **AC14: Recording does not mutate inputs and does not touch shipped
  artifacts.** After `record_calibrated_config(...)`, `base_config`,
  `calibration_result`, and `axes` are unchanged (deep-equality), and the
  bundled `src/segqc/default_config.yaml` is not written (only the caller-
  supplied `path` is written).

- [ ] **AC15: "No feasible setting" is handled explicitly, not written blindly.**
  When `calibration_result.best is None` (status `"no-feasible-setting"`),
  `record_calibrated_config(...)` raises `segqc.io.SegQCInputError` (rather than
  applying a `None` assignment or writing a degenerate config).

- [ ] **AC16: The module edits no living documents.** `segqc.eval.report`
  contains no reference to `progress.md` or `roadmap.md` and its public
  functions write only to their explicit `path` argument (recording is
  artifact-production only; the `progress.md` fill-in is item 057's).

- [ ] **AC17: Any committed report/config fixture is LF-pinned.** If the test
  suite commits a byte-reproducible golden artifact (report JSON or config
  YAML), its path is pinned with `text eol=lf` in `.gitattributes` per the
  `CLAUDE.md` determinism gotcha (or no such fixture is committed).

## Assumptions  <!-- MANDATORY -->

Clarify mode is `assume` (per `aide.toml`); the queued one-liner left several
design points open. Defaults taken (validator to surface):

- **The "Calibrated metrics" placeholders live in `progress.md`, not
  `roadmap.md`.** The orchestrator brief located the "Calibrated metrics (to be
  filled at completion)" block in the roadmap; in the current tree it is in
  [`progress.md`](../progress.md) (Stage-7 entry: FPR on VerSe GT, Sensitivity
  per §6 failure mode, DICE-vs-flag correlation). Either way this item does
  **not** fill it in: `roadmap.md` is PR-gated and `progress.md` is CLI-managed
  and completed by item 057. If a builder finds the placeholders elsewhere, the
  scope decision (056 produces artifacts; 057 transcribes at stage close) is
  unchanged.
- **New module path `src/segqc/eval/report.py`**, exported from
  `src/segqc/eval/__init__.py`. Named within the `eval` package to avoid
  colliding with the existing per-case `src/segqc/report.py` (Stage 1).
- **Human rendering is plain text, not Markdown**, matching item 010's decision
  (terminal / XNAT-notes / email friendly) and its stdlib-only, deterministic
  discipline.
- **JSON schema strictness.** The schema is strict (`additionalProperties:
  false`, `required`) at the **top level** and over the `provenance` block; the
  `metrics` and `calibration` blocks are described to at least their required
  keys but may permit their full nested `to_dict()` shape without enumerating
  every leaf (those shapes are already guaranteed by 054/055's `to_dict()`).
  Exact depth is a builder decision recorded in Decisions & Trade-offs; AC2/AC8
  bind the observable behaviour (valid real output passes; a missing required
  key fails).
- **Calibration block content = the chosen summary, not the full sweep.** By
  default the `calibration` block embeds `status`, the `objective`
  (`sensitivity_floor`), `best.assignment`, and `best.metrics` (achieved
  metrics), keeping the artifact focused. Embedding the full per-candidate list
  (`CalibrationResult.to_dict()["candidates"]`) is optional (builder decision).
- **Provenance is caller-supplied (no wall clock).** `EvaluationProvenance` is a
  frozen dataclass with `cohort_id: str`, `cohort_size: int`,
  `config_version: str`, `build_date: str` (ISO `YYYY-MM-DD`), and optional
  `reference_schema_version: Optional[str]` / `segqc_version: Optional[str]`,
  with a `to_dict()`. `build_date` is always passed in (mirroring
  `segqc.reference.artifact`'s `DEFAULT_BUILD_DATE` / caller-supplied contract),
  so reports are byte-reproducible.
- **Config serialisation for recording.** A `HeuristicConfig` is reduced to a
  plain mapping of its public fields (`schema_version`, `min_foreground_voxels`,
  `min_label_count`, `min_fragment_voxels`, `rules`, `verdict`, `reference`) and
  written as YAML via `yaml.safe_dump(..., sort_keys=True,
  default_flow_style=False)`, encoded UTF-8 and written with `Path.write_bytes`
  on a `"\n"`-terminated string (never `write_text`, per the 043/045 / CLAUDE.md
  determinism gotcha). The mapping is exactly what `load_config` accepts, so the
  round-trip (AC12) holds. This assumes `HeuristicConfig`'s public field set is
  as read from the merged `segqc.config` at build time; the builder/validator
  hand back if it diverged.
- **`record_calibrated_config` signature** is
  `record_calibrated_config(base_config, calibration_result, axes, path)`: it
  needs `axes` because item 055's serialisable `CandidateResult.assignment` is a
  plain `{axis.name: value}` mapping and the `(rule_id, param_path)` addressing
  lives on the `ThresholdAxis` objects (per 055's Decisions log) — the same
  three-arg shape `apply_assignment(base_config, best.assignment, axes)`
  expects.
- **`None` FPR / correlation rendering.** These are item 054's explicit
  sentinels (no expected-pass cases; <2 usable correlation pairs; zero-variance
  inputs). The human renderer maps them to `"n/a"`; the JSON keeps them as JSON
  `null` (as 054's `to_dict()` already emits).

## Implementation Steps

Code path: **`src/segqc/eval/report.py`** (new module), plus
`src/segqc/eval/eval_report_schema_v0.json` (bundled schema) and an export from
`src/segqc/eval/__init__.py`.

1. **Author `eval_report_schema_v0.json`** next to the `segqc/eval` package
   modules: draft-07, `schema_version` const `"0.1"`, `required`
   `["schema_version", "provenance", "metrics"]`, optional `calibration`;
   `provenance` a strict object (`cohort_id`, `cohort_size`, `config_version`,
   `build_date` required; `reference_schema_version`, `segqc_version` optional);
   `metrics` / `calibration` described to their required top-level keys. Follow
   the shape/comment style of `report_schema_v0.json`.
2. **Module docstring** in the style of `report.py`/`harness.py`: state it is the
   Stage-7 evaluation-report renderer/recorder over 054 (+055), that it is
   artifact-production only (no `progress.md`/`roadmap.md`, no CLI — that's 057),
   and its dependencies.
3. **Load + cache the schema** once at import via `importlib.resources`
   (`_load_eval_schema()` → module-level `_SCHEMA`), exactly as
   `segqc.report._load_schema` does.
4. **`EvaluationProvenance`** — frozen dataclass (fields per Assumptions) with a
   `to_dict()` emitting the provenance block.
5. **`build_evaluation_report(metrics, provenance, *, calibration=None) -> dict`**
   — assemble `{"schema_version": "0.1", "provenance": provenance.to_dict(),
   "metrics": metrics.to_dict()}`, add `"calibration"` (chosen summary) when
   `calibration is not None`, `jsonschema.validate` against `_SCHEMA`, return.
6. **`serialize_evaluation_report_json(...) -> str`** — `json.dumps(report,
   indent=2, sort_keys=True)` for a deterministic string; and
   **`write_evaluation_report(report_or_inputs, path) -> Path`** — write the
   JSON as UTF-8 bytes ending in one `"\n"` via `Path.write_bytes` (mirror
   `segqc.reference.artifact.write_artifact`; create parents).
7. **`render_evaluation_report(metrics, provenance, *, calibration=None) -> str`**
   — stdlib-only plain-text builder (line-list + `"\n".join`, like
   `human_report.render_human_report`): a title + provenance summary; an overall
   metrics block (FPR, sensitivity, specificity — `None` → `"n/a"`); a per-mode
   sensitivity table (mode name, n_cases, caught-by-designated-rule,
   sensitivity); the DICE-vs-flag and feature-divergence-vs-flag correlations
   (coefficient + n); and, when `calibration` is present, a calibration block
   (status, objective floor, chosen assignment, achieved FPR/sensitivity).
8. **`record_calibrated_config(base_config, calibration_result, axes, path) ->
   Path`** — raise `SegQCInputError` when `calibration_result.best is None`;
   else `applied = apply_assignment(base_config, calibration_result.best.assignment,
   axes)` (item 055), reduce `applied` to its public-field mapping, `yaml.safe_dump`
   (sorted keys), write UTF-8 bytes with `"\n"` via `Path.write_bytes`; never
   mutate inputs; never write the bundled default. Return `path`.
9. **Export** the public names (`EvaluationProvenance`,
   `build_evaluation_report`, `serialize_evaluation_report_json`,
   `write_evaluation_report`, `render_evaluation_report`,
   `record_calibrated_config`, `EVAL_REPORT_SCHEMA_VERSION`) from
   `segqc/eval/__init__.py` (extend `__all__` + module docstring, mirroring how
   053/054/055 were added).
10. **If** a committed golden artifact is used by tests, pin its path with
    `text eol=lf` in `.gitattributes` (do not commit `.nii.gz` as text).

## Testing Strategy

New test module: **`tests/test_056_eval_report.py`** (mirrors
`tests/test_054_metrics.py` / `tests/test_055_calibrate.py`). One focused test
per AC plus adversarial / edge cases. Build `CohortMetrics` either by running the
merged harness+metrics on a tiny synthetic cohort (bare `ndarray` seg maps via
the harness `_resolve_seg` path) or from hand-built `CaseEvaluation`-shaped
records fed to `compute_cohort_metrics`; build `CalibrationResult` from
`calibrate_thresholds` on a small cohort or a minimal hand-built result.

- **AC1:** load the bundled schema via `importlib.resources`; assert the
  `schema_version` const and the `required` keys.
- **AC2:** build a report from a real `CohortMetrics` + provenance; assert
  `schema_version`, `metrics == metrics.to_dict()`, and that it validates (no
  raise).
- **AC3:** build with and without `calibration`; assert presence/absence of the
  `calibration` key; both validate.
- **AC4:** assert `provenance.cohort_size == metrics.n_cases` and
  `config_version == config.schema_version`.
- **AC5:** build twice with identical inputs → equal `build_date`; grep the
  module source has no `date.today`/`datetime.now` (or assert equality suffices).
- **AC6:** assert FPR / per-mode / DICE-vs-flag coefficient read back at the
  documented paths equal the `CohortMetrics` fields.
- **AC7:** with a feasible `CalibrationResult`, assert the `calibration` block
  carries `best.assignment`, achieved metrics, and `status == "ok"`.
- **AC8:** delete a required key from a built dict (or pass a bad dict) → assert
  `jsonschema.ValidationError`.
- **AC9:** serialise twice → byte-identical; parse the written file → equals the
  built dict; assert single trailing `"\n"`.
- **AC10:** render a report; assert the FPR / a per-mode sensitivity / the
  correlation coefficient (and the chosen assignment when calibrated) appear as
  text; assert no `"CohortMetrics("`, `"<"`, `"Outcome."`, `"(...)"`-tuple, or
  `"frozenset"` substrings.
- **AC11:** metrics with `false_positive_rate is None` and a `None` correlation
  coefficient → rendering contains `"n/a"` and does not contain `"None"`; no
  raise.
- **AC12 (round-trip):** record a calibrated config to a tmp path;
  `load_config(path)` → assert swept params equal chosen values and other fields
  equal `base_config`'s.
- **AC13:** record to two tmp paths → `read_bytes()` byte-identical.
- **AC14 (immutability):** deep-snapshot `base_config`, `calibration_result`,
  `axes` before; assert unchanged after; assert `default_config_path()` file
  mtime/bytes unchanged (or simply that only the tmp path was written).
- **AC15:** a `CalibrationResult` with `best is None` /
  `status == "no-feasible-setting"` → `record_calibrated_config` raises
  `SegQCInputError`.
- **AC16:** assert the module source contains no `"progress.md"` /
  `"roadmap.md"` literals and that build/render functions write nothing (pure).
- **AC17:** if a golden fixture is committed, assert it is listed in
  `.gitattributes` with `text eol=lf`.
- **Adversarial/edge:** empty cohort (`n_cases == 0`) → degenerate metrics
  (`None` FPR/sensitivity) still build, validate, render, and serialise without
  crash; a `per_mode` entry with `n_cases == 0` (sentinel sensitivity) renders
  cleanly; a report built without calibration renders a calibration section
  reading e.g. "(not calibrated)".

## Dependencies

- **Item 054 — `segqc.eval.metrics`** (✅, merged): `CohortMetrics`,
  `compute_cohort_metrics`, `PerModeSensitivity`, `CorrelationResult`,
  `ConfusionCounts`, and `CohortMetrics.to_dict()` — the metrics the report
  renders/serialises and the `None` sentinels it must handle.
- **Item 055 — `segqc.eval.calibrate`** (✅, merged): `CalibrationResult`
  (`best`, `status`, `objective`, `to_dict()`), `CandidateResult`
  (`assignment`, `metrics`), `ThresholdAxis`, and `apply_assignment` — the
  chosen-threshold source and the config-apply used by `record_calibrated_config`.
- **Item 005/035 — `segqc.config`** (✅, merged): `HeuristicConfig` (public
  fields, frozen), `load_config`, `default_config`, `default_config_path` — the
  config recorded and the round-trip target.
- **Items 009/010 — `segqc.report` / `segqc.human_report`** (✅, merged): the
  conventions matched — bundled-schema-via-`importlib.resources` + validate-on-
  serialise, and the stdlib-only deterministic plain-text renderer.
- **Items 043/045 — `segqc.reference.artifact`** (✅, merged): the byte-
  reproducible write pattern (`Path.write_bytes` on a `"\n"`-terminated string;
  caller-supplied `build_date`; `.gitattributes` LF-pin).
- **`segqc.io.SegQCInputError`** (✅): the raised error type, consistent with
  053/054/055.
- **`jsonschema`, `PyYAML`** (✅, already project deps): schema validation and
  config YAML dump.

Consumer (not this item): **057** (`segqc evaluate` entry point + Stage-7
acceptance suite; transcribes the recorded numbers into `progress.md`'s
"Calibrated metrics" block and closes Phase 1 via the reviewed PR).

## Decisions & Trade-offs

To be updated during implementation.
