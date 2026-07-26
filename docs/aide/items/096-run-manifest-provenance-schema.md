# Item 096 — Run-manifest provenance schema

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6)
> **Queue:** [`../queue/queue-013.md`](../queue/queue-013.md) · Item 096
> *(fourth of five; independent of items 093/094/095 — may run in parallel,
> but is sequenced after them in this queue's numbering)*
> **Objectives:** G2 (a real segmenter's failure characterisation is only
> trustworthy if every number is traceable to the exact tool/weights/config
> that produced it — the motivation §17 names for the run-manifest deliverable)
> **Suggested branch:** `aide/096-run-manifest-provenance-schema`

---

## Description

Add a run-manifest provenance record — segmenter version/SHA, weights hash,
post-processing toggles, seed, dataset id, and the resolved `numpy`/`TPTBox`
versions — carried alongside `segfacet run` and `segfacet evaluate` output,
following the existing `EvaluationProvenance` pattern in `eval/report.py`
(frozen dataclass + `.to_dict()`, embedded in a schema-validated report,
written via `Path.write_bytes` per this repo's byte-reproducibility
convention) rather than inventing a new shape. A new module
`segfacet/run_manifest.py` hosts a single `RunManifest` dataclass shared by
both CLI subcommands (rather than duplicating it once per subcommand),
since the fields are identical whether the manifest describes one case
(`run`) or one cohort (`evaluate`).

Every field is **optional** and **caller-supplied via new CLI flags** except
`resolved_versions`, which is **always auto-populated** (via
`importlib.metadata.version(...)`) whenever a manifest is built at all — it
answers "what was actually installed," not something a caller states.
The manifest block is emitted **only when at least one segmenter-identifying
flag is given**; a plain `segfacet run`/`evaluate` invocation against GT
(no segmenter behind the input) omits the block entirely, preserving every
existing report's shape.

**What this item is not:**
- **Not a change to `build-reference`.** That subcommand builds a reference
  distribution from ground truth, with no segmenter behind its input — no
  manifest applies.
- **Not the TPTBox-wheel-sha256 record from item 094's numpy<2 bootstrap
  doc.** That is a one-time *installation* provenance record (which TPTBox
  wheel was installed into a given environment), documented in
  `docs/tptbox-install-numpy1.md`; this item's manifest is a **per-run**
  record (which segmenter produced *this* case/cohort's input). The two are
  related but distinct; `resolved_versions` in this item's manifest reports
  the *currently importable* TPTBox version, not a wheel provenance hash.
- **Not new metrics, new rules, or a new report *format*** — this is
  additive provenance metadata only, following the existing optional-block
  pattern (`features`, `findings`, `reference_delta`, `image_features` in
  `report.py`; `calibration` in `eval/report.py`).

## Acceptance Criteria

- [ ] **AC1: `RunManifest` is a frozen, JSON-serialisable dataclass.**
  `segfacet.run_manifest.RunManifest` has fields `segmenter_version:
  Optional[str]`, `segmenter_sha: Optional[str]`, `weights_hash:
  Optional[str]`, `seed: Optional[int]`, `dataset_id: Optional[str]`,
  `postproc_toggles: Optional[dict]` (a free-form JSON-compatible mapping,
  not a fixed set of named booleans — confirmed with the user: future-proof
  against segmenter-specific toggle sets), and `resolved_versions:
  Dict[str, Optional[str]]`. `.to_dict()` returns a plain, JSON-serialisable
  dict with every field present (using `None` for an unset optional field,
  mirroring `EvaluationProvenance.to_dict()`'s discipline — never omits a
  key based on value).
- [ ] **AC2: `resolved_versions` is auto-populated, not caller-supplied.**
  A helper `build_run_manifest(*, segmenter_version=None, ...) ->
  Optional[RunManifest]` resolves `{"numpy": ..., "tptbox": ...,
  "segfacet": segfacet.__version__}` via `importlib.metadata.version(...)`
  at call time (each entry `None` if that package's metadata is not
  discoverable — never raises), and returns `None` (not a manifest with all
  fields empty) when **none** of the caller-supplied fields
  (`segmenter_version`/`segmenter_sha`/`weights_hash`/`seed`/`dataset_id`/
  `postproc_toggles`) were given.
- [ ] **AC3: `segfacet run --scan/--seg` accepts the new flags and emits a
  `run_manifest` block only when populated.** `--segmenter-version <str>`,
  `--segmenter-sha <str>`, `--weights-hash <str>`, `--seed <int>`,
  `--dataset-id <str>`, `--postproc-toggles <json>` (parsed as JSON; a
  malformed JSON string exits 1 with a clear `Error:` message, mirroring
  the existing `--config`/`--dataset-schema` error-handling style — never a
  raw traceback). Given at least one, the JSON report gains a `run_manifest`
  key; given none, the report is byte-identical to today's shape (no
  `run_manifest` key at all).
- [ ] **AC4: `segfacet evaluate` accepts the same flags with the same
  behaviour**, emitting one cohort-level `run_manifest` block in the
  evaluation report under the same opt-in condition.
- [ ] **AC5: both report schemas validate the new optional block.**
  `report_schema_v0.json` and `eval/eval_report_schema_v0.json` each gain a
  `run_manifest` property (`$ref`'d to a shared-shape `definitions` entry,
  matching the existing `image_features`/`calibration` pattern),
  `additionalProperties: false` preserved, `run_manifest` **not** added to
  either schema's `required` list. A report with an invalid/malformed
  `run_manifest` shape fails `jsonschema.validate` (proving the schema is
  actually enforced, not decorative).
- [ ] **AC6: byte-reproducible serialisation.** Two `build_run_manifest`
  calls with identical arguments (including a fixed, injected
  `resolved_versions` resolution — see Assumptions) produce
  `.to_dict()`-equal output; `serialize_report_json`/
  `serialize_evaluation_report_json`'s existing sorted-key,
  `Path.write_bytes`-based writers require no change to stay
  byte-reproducible with the new block present.
- [ ] **AC7: omission is silent and clean, not a stub.** An invocation with
  zero manifest flags produces a report with **no** `run_manifest` key at
  all (not `"run_manifest": null` or `"run_manifest": {}`) — every existing
  golden/regression fixture that does not pass these new flags is
  byte-identical to its pre-item output.

## Assumptions

Clarify mode was forced to `interactive`; the following were resolved with
the user rather than defaulted:

- **Both `run` and `evaluate` get the flags** (not `run`-only) — confirmed
  with the user: a cohort evaluation typically comes from one segmenter
  invocation, so one manifest per `evaluate` call is a reasonable model.
- **`postproc_toggles` is a free-form JSON blob**, not a fixed set of named
  booleans — confirmed with the user, preferring future-proofing over
  structure tied to one segmenter's documented steps.
- **`resolved_versions` uses `importlib.metadata.version(...)`, not each
  package's own `__version__` attribute** (not all packages reliably expose
  one; `importlib.metadata` is the uniform, stdlib-only mechanism already
  implicitly relied on by this project's packaging). Resolution failures
  (package not installed / metadata not found) yield `None` for that entry
  rather than raising — a manifest must never crash a run because an
  unrelated package's metadata lookup failed.
- **Tests inject a fixed `resolved_versions` resolver** (e.g. a small
  monkeypatch or an optional `_version_resolver` parameter on
  `build_run_manifest`, builder's choice) rather than asserting against
  whatever numpy/TPTBox happen to be installed in the test environment —
  AC6's byte-reproducibility claim must hold independent of the actual
  installed versions, which vary machine-to-machine.
- **No new subcommand and no change to `build-reference`.** Confirmed by
  scope: only `run` and `evaluate` gain the flags.
- **Dependencies:** none within Stage 17 — this item does not depend on
  093/094/095 landing first (it touches `run_manifest.py`, `report.py`,
  `eval/report.py`, `cli.py`, and the two schema files only), though
  `resolved_versions` will naturally start reporting a real TPTBox entry
  once item 094 lands (it reports `None` for `tptbox` until then, which is
  correct and not a bug).

## Implementation Steps

All under `source_dir = src/segfacet`.

1. **New module `src/segfacet/run_manifest.py`**:
   - `RunManifest` frozen dataclass (fields per AC1) + `.to_dict()`.
   - `_resolve_versions(package_names: Sequence[str]) -> Dict[str,
     Optional[str]]`: wraps `importlib.metadata.version(name)` per package,
     `None` on `importlib.metadata.PackageNotFoundError` (never raises).
   - `build_run_manifest(*, segmenter_version=None, segmenter_sha=None,
     weights_hash=None, seed=None, dataset_id=None, postproc_toggles=None,
     _version_resolver=_resolve_versions) -> Optional[RunManifest]`: returns
     `None` if every caller-supplied field is `None`; otherwise builds a
     `RunManifest` with `resolved_versions = _version_resolver(("numpy",
     "tptbox", "segfacet"))` merged with `{"segfacet": segfacet.__version__}`
     for the one entry this project can report without a metadata lookup.
2. **`src/segfacet/report_schema_v0.json`**: add a `runManifest` entry
   under `definitions` (object type; the seven fields, nullable where
   optional, `additionalProperties: false`) and a `"run_manifest":
   {"$ref": "#/definitions/runManifest", "description": "..."}` entry under
   `properties`, not `required`.
3. **`src/segfacet/eval/eval_report_schema_v0.json`**: the same
   `runManifest` definition (duplicated or, if the schema loader supports
   it cleanly, referenced from a shared location — builder's choice;
   duplication mirrors how `report_schema_v0.json` and
   `eval_report_schema_v0.json` are already two independent files with no
   existing cross-reference mechanism) and the same `"run_manifest"`
   property addition.
4. **`src/segfacet/report.py`**: `serialize_report`/`serialize_report_json`
   gain an optional `run_manifest: "dict | None" = None` parameter,
   embedded under `report["run_manifest"]` when not `None` — same pattern
   as the existing `image_features` parameter (`report.py:190-194`).
5. **`src/segfacet/eval/report.py`**: `build_evaluation_report` gains the
   analogous optional `run_manifest` parameter, embedded the same way
   (mirroring the existing `calibration` optional-block handling,
   `eval/report.py:218-219`).
6. **`src/segfacet/cli.py`**:
   - Add a shared `_add_run_manifest_args(parser)` helper (mirroring the
     existing `_add_dataset_schema_args` pattern, `cli.py:79-93`) adding the
     six new flags to both `run_parser` and `evaluate_parser`.
   - In `_handle_run`, after loading args and before serialising the
     report, call `build_run_manifest(...)` from the parsed flags (parsing
     `--postproc-toggles`'s JSON string with a caught `json.JSONDecodeError`
     → `Error:` + exit 1, mirroring existing CLI error-handling style) and
     pass `.to_dict()` (or `None`) into `serialize_report_json`.
   - In `_handle_evaluate`, the same, passed into `build_evaluation_report`.
7. **Do not** touch `build-reference`'s parser/handler, `pipeline.py`,
   `heuristics/`, or any extractor.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_096_run_manifest.py`.
- **AC1**: construct a `RunManifest` with every field populated and with
  every field `None`; assert `.to_dict()`'s key set and `None`-vs-value
  handling in both cases.
- **AC2**: call `build_run_manifest()` with no arguments → `None`; call
  with one field set and an injected fake `_version_resolver` returning a
  fixed dict → the returned manifest's `resolved_versions` matches exactly
  including a `None` entry for a "not installed" package name passed
  through the fake resolver.
- **AC3/AC4**: CLI-level tests (subprocess or direct `_build_parser()` +
  handler invocation, matching this project's existing CLI test style)
  covering: no flags → no `run_manifest` key; one flag → key present with
  the rest `null`; all flags → key present and fully populated; malformed
  `--postproc-toggles` JSON → exit code 1 and an `Error:` message on
  stderr, no traceback.
- **AC5**: `jsonschema.validate` on a report/eval-report dict with a
  deliberately malformed `run_manifest` (e.g. `seed` as a string) raises
  `jsonschema.ValidationError`; a well-formed one validates cleanly.
- **AC6**: two `build_run_manifest` calls with identical arguments and the
  same injected resolver produce `.to_dict()`-equal results; run twice in
  the same test to rule out any hidden nondeterminism (e.g. dict ordering —
  `to_dict()`'s output should be a plain dict compared by value, not by
  insertion order, since `serialize_report_json` already sorts keys).
- **AC7**: run the full existing Stage-5/Stage-7 golden/regression suites
  unmodified — confirm zero output diff, since none of those fixtures pass
  the new flags.
- **Adversarial / edge cases:**
  - `--seed 0` (falsy but meaningful) must still populate the manifest
    (falsy-but-not-`None` distinguished correctly — a common off-by-bug
    class: `if seed:` vs `if seed is not None:`).
  - `--postproc-toggles '{}'` (an explicitly empty-but-present JSON object)
    still counts as "a flag was given" and triggers manifest emission
    (distinguishing "flag omitted" from "flag given an empty value").
  - `--postproc-toggles` given a JSON **array** or scalar (not an object) —
    decide and test a clear behaviour (reject with `Error:`, since the
    field's declared type is a mapping; document the choice).
  - A `resolved_versions` lookup for a package name not on `PYTHONPATH` at
    all returns `None` for that entry without raising, for every one of
    the three lookup targets independently (numpy/tptbox/segfacet each
    tested missing in isolation via the injected resolver).

## Dependencies

- **None within Stage 17** for landing — this item's code has no import
  dependency on 093/094/095, though `resolved_versions["tptbox"]` only
  starts resolving to a real value once item 094 lands (correct `None`
  before then, not a defect).
- **Item 056/`eval/report.py`'s `EvaluationProvenance`, and item 009's
  `report.py` optional-block pattern (both ✅ merged) — the two established
  precedents this item's design directly mirrors.**
- **Downstream: item 097** (stage validation) may exercise `run_manifest`
  when demonstrating a real-SPINEPS round-trip, populating
  `segmenter_version`/`dataset_id` for that case — not a hard dependency,
  but the natural place the manifest gets its first real-world use.

## Decisions & Trade-offs

To be updated during implementation.
