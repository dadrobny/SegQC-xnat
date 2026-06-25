# Item 009 — JSON Report Schema v0 & Serializer

> **Status:** 🚧 In Progress · **Created:** 2026-06-25
> **Stage:** 1 — End-to-End Thin Slice: Empty Detection + Report
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 009
> **Objectives:** G4 — Per-case QC report (JSON + human-readable)
> **Suggested branch:** `aide/009-json-report-schema`

---

## Description

Define the **versioned JSON report schema v0** (machine-readable) and a
serializer that converts the QC verdict model (item 008) plus case/label
metadata and the heuristic-config version (item 005) into a well-structured,
schema-validated JSON document. This JSON report is the primary machine-readable
output contract that Stage 2 and later stages will extend with a `features`
block.

This item delivers:

1. **JSON schema file** at `src/segqc/report_schema_v0.json` — a
   [JSON Schema draft-07](https://json-schema.org/draft-07/) document that fully
   describes the v0 report structure, including required fields, field types,
   and the `"schema_version": "0.1"` discriminator.

2. **`serialize_report` function** in `src/segqc/report.py` — converts a
   `Verdict` object plus case metadata into a Python `dict` conforming to the
   schema, then validates the dict against the schema before returning it. Also
   provides a `serialize_report_json` convenience wrapper that returns the
   serialized dict as a JSON string.

3. **Schema-validated output contract** — every call to `serialize_report` runs
   `jsonschema.validate(report_dict, schema)` internally, so any serialization
   bug that produces a non-conforming report raises immediately in tests (and in
   production). This ensures the schema and serializer stay in sync.

The v0 report structure has the following top-level keys:

```json
{
  "schema_version": "0.1",
  "config_version": "0.1",
  "case_id": "<string>",
  "verdict": "pass",
  "reasons": [
    {"message": "...", "severity": "pass", "labels": []}
  ],
  "per_label": {
    "42": [
      {"message": "...", "severity": "flagged-for-review", "labels": [42]}
    ]
  }
}
```

Field descriptions:
- `schema_version` (string, required) — always `"0.1"` for this schema.
- `config_version` (string, required) — the `schema_version` field from
  `HeuristicConfig` (i.e. the heuristic config file version), used for
  reproducibility. May differ from the report schema version.
- `case_id` (string, required) — an identifier for the case (scan), supplied by
  the caller. Must be non-empty.
- `verdict` (string, required) — the overall verdict label: one of `"pass"`,
  `"flagged-for-review"`, `"fail"`.
- `reasons` (array, required) — serialized case-level `Reason` objects. Each
  element is an object with `"message"` (string), `"severity"` (string),
  and `"labels"` (array of integers, may be empty).
- `per_label` (object, required) — serialized `per_label` from the `Verdict`.
  Keys are **string** representations of integer label values; values are arrays
  of serialized `Reason` objects (same structure as in `reasons`).

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| QC verdict data model (`Severity`, `Reason`, `Verdict`) | Item 008 | consumed here |
| Heuristic config (`HeuristicConfig.schema_version`) | Item 005 | consumed here |
| Human-readable report renderer | Item 010 | not here |
| CLI wiring (call serializer + write to disk) | Item 010 | not here |
| Stage 2 `features` block | Future item | schema is the extension point |
| File I/O (writing JSON to disk) | Item 010 | serializer returns dict/str only |

---

## Acceptance Criteria

- [ ] **AC-1 Schema file exists** at `src/segqc/report_schema_v0.json` and is
      valid JSON Schema draft-07. The file is importable/loadable with the
      standard `json` module (no parse errors).
- [ ] **AC-2 Schema requires correct fields**: the schema requires `schema_version`,
      `config_version`, `case_id`, `verdict`, `reasons`, and `per_label` at the
      top level. A report missing any of these must fail validation.
- [ ] **AC-3 `serialize_report` importable** as
      `from segqc.report import serialize_report` with no import errors.
- [ ] **AC-4 `serialize_report` returns a conforming dict**: given a `Verdict`
      and valid metadata, the returned dict passes `jsonschema.validate` against
      the v0 schema without raising.
- [ ] **AC-5 `verdict` field maps correctly**: the serialized `verdict` field
      uses `Severity.label` strings — `"pass"`, `"flagged-for-review"`, `"fail"`.
- [ ] **AC-6 `reasons` array is complete**: every case-level `Reason` in
      `verdict.reasons` appears in the `reasons` array with correct `message`,
      `severity` (label string), and `labels` (list of ints, sorted).
- [ ] **AC-7 `per_label` serialization**: every entry in `verdict.per_label` is
      present in the `per_label` dict, keyed by the string representation of the
      integer label (e.g. label `42` → key `"42"`). Reasons within each entry
      are serialized the same way as case-level reasons.
- [ ] **AC-8 `config_version` is included**: the serialized report contains a
      `config_version` field whose value is the `schema_version` string from the
      `HeuristicConfig` passed to the serializer.
- [ ] **AC-9 `case_id` is included**: the serialized report contains a `case_id`
      field whose value is the string passed by the caller.
- [ ] **AC-10 Round-trip stability**: serializing the same `Verdict` and metadata
      twice produces dicts that are equal (same keys, same values). The function
      is deterministic.
- [ ] **AC-11 Empty verdict serializes to `pass`**: a `Verdict` with no reasons
      and no per-label entries serializes to `verdict: "pass"`, an empty `reasons`
      array, and an empty `per_label` object — and still validates against the
      schema.
- [ ] **AC-12 `serialize_report_json` returns valid JSON string**: the
      convenience wrapper `serialize_report_json` returns a `str` that is
      parseable with `json.loads` and equal (after parsing) to the dict returned
      by `serialize_report`.
- [ ] **AC-13 Module location**: the serializer is importable as
      `from segqc.report import serialize_report, serialize_report_json` with no
      import errors.
- [ ] **AC-14 No stdlib-external imports at module level beyond `jsonschema`**:
      `import segqc.report` must not require NumPy, NiBabel, SciPy, or other
      non-stdlib/non-jsonschema packages at import time.

---

## Implementation Steps

1. **Write `src/segqc/report_schema_v0.json`** — JSON Schema draft-07 document
   enforcing the v0 report structure described above. Use `"additionalProperties": false`
   at the top level to catch unexpected keys. The `verdict` field should use an
   `enum` of `["pass", "flagged-for-review", "fail"]`.

2. **Create `src/segqc/report.py`**:
   - Import `json`, `pathlib`, `importlib.resources` (or `pkg_resources`) to
     locate and load the schema at import time. Cache it as a module-level
     `_SCHEMA` constant so the schema file is only read once.
   - Implement `_serialize_reason(reason: Reason) -> dict` — converts a single
     `Reason` to `{"message": ..., "severity": ..., "labels": [...]}` with
     `labels` sorted.
   - Implement `serialize_report(verdict: Verdict, case_id: str, config: HeuristicConfig) -> dict` —
     builds the full report dict, calls `jsonschema.validate(report, _SCHEMA)`,
     then returns it. Raises `ValueError` if `case_id` is empty.
   - Implement `serialize_report_json(verdict: Verdict, case_id: str, config: HeuristicConfig, indent: int = 2) -> str` —
     calls `serialize_report` and returns `json.dumps(result, indent=indent)`.

3. **Export from `src/segqc/__init__.py`**: add
   `from segqc.report import serialize_report, serialize_report_json` to the
   public surface.

4. **Add `jsonschema` to `pyproject.toml` dependencies** if not already present.

5. **Write `tests/test_009_json_report.py`** covering all ACs.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **No fixtures beyond `tmp_path`** (not needed; serializer is pure in-memory).
- **Test module:** `tests/test_009_json_report.py`.
- **Coverage:** all fourteen ACs; adversarial / edge cases: empty reasons, unknown
  label keys, missing `config_version`, future schema version number, malformed
  verdict input, `case_id` edge cases.
- **Schema validation:** every `serialize_report` call in tests is automatically
  schema-validated (the function validates internally); tests that intentionally
  break the contract call `jsonschema.validate` directly.
- **No external services, no I/O, no network.**

---

## Dependencies

- **Upstream:**
  - Item 001 (package skeleton) — ✅ merged
  - Item 005 (heuristic config, `HeuristicConfig`, `schema_version`) — ✅ merged
  - Item 008 (QC verdict model, `Verdict`, `Reason`, `Severity`) — ✅ merged
- **Downstream:**
  - Item 010 (human-readable report + pipeline wiring) — calls `serialize_report`
    and writes the result to disk.

---

## Decisions & Trade-offs

1. **JSON Schema draft-07** chosen for broad `jsonschema` library compatibility
   (the default draft for `jsonschema >= 3`). Draft-07 is sufficient for the v0
   structure; later drafts can be adopted when the schema grows.

2. **Schema validated on every `serialize_report` call** (not only in tests).
   This is slightly slower but catches any implementation drift immediately and
   keeps the schema the single source of truth. A future `validate=False` flag
   can be added for hot paths.

3. **`per_label` keys are strings** (JSON objects only allow string keys). The
   integer label value is `str(label_int)` in the serialized form. Consumers
   must parse the key back to `int` if needed. This is the standard JSON
   convention and what `json.dumps` does automatically for dict keys.

4. **`labels` in each `Reason` are sorted** in the serialized output. This
   ensures deterministic output when the same `frozenset` is serialized twice
   (frozenset iteration order is not guaranteed).

5. **`config_version` name** (not `config_schema_version`) used to keep the
   report concise. Its value is `HeuristicConfig.schema_version` — the version
   of the heuristic-config file format that produced the thresholds, included for
   reproducibility.

6. **Schema file location**: `src/segqc/report_schema_v0.json` is a package data
   file, accessed via `importlib.resources` (Python 3.9+). This avoids hardcoding
   an absolute path and works correctly after installation.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]` — `jsonschema` must be in dependencies.
- **Environment variables / secrets:** none.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` exits 0.
- [ ] **Tests pass:** `python -m pytest tests/test_009_json_report.py` is green.
- [ ] **Import check:** `python -c "from segqc.report import serialize_report; print('ok')"` prints `ok`.
- [ ] **Schema valid:** `python -c "import json, pathlib; s = json.loads(pathlib.Path('src/segqc/report_schema_v0.json').read_text()); print('schema ok')"` prints `schema ok`.

### Expected Outcomes

- `serialize_report` and `serialize_report_json` are importable and behave as specified.
- `pytest tests/test_009_json_report.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–008.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 1 **"JSON report schema…"** deliverable from 📋 → ✅ (mark 🚧
  while in progress).
- Per `CLAUDE.md`: work on branch `aide/009-json-report-schema`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's
  rows, and direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 009` to
implement this work item.
