# Item 008 — QC Verdict Model

> **Status:** 📋 Planned · **Created:** 2026-06-25
> **Stage:** 1 — End-to-End Thin Slice: Empty Detection + Report
> **Queue:** [`../queue/queue-001.md`](../queue/queue-001.md) · Item 008
> **Objectives:** G4 — Per-case QC report (JSON + human-readable)
> **Suggested branch:** `aide/008-qc-verdict-model`

---

## Description

Define the **QC verdict data model** — the central data structure that carries
every quality-control decision made on a single scan. The model expresses a
per-case verdict of `pass` / `flagged-for-review` / `fail` and records the
individual reasons that drove the verdict, with **per-vertebra attribution** so
that later consumers (JSON serialiser, human-readable renderer, XNAT integrations)
can display exactly which vertebra triggered each flag.

This item delivers:

1. **`Severity` enum** — three ordered levels (`PASS`, `FLAG`, `FAIL`) with a
   well-defined total order (`PASS < FLAG < FAIL`) and a mapping to the string
   labels used in outputs (`"pass"`, `"flagged-for-review"`, `"fail"`).

2. **`Reason` dataclass** — a single human-readable string with an associated
   `Severity` and an optional set of offending label integers. No raw library
   internals in the `message` string.

3. **`Verdict` dataclass** — the per-case result:
   - `overall: Severity` — the maximum severity of all contributing reasons.
   - `reasons: list[Reason]` — case-level reasons (not tied to a specific label).
   - `per_label: dict[int, list[Reason]]` — reasons keyed by integer label value.
   - Factory/builder API so callers add reasons incrementally and then finalise.

4. **Aggregation rule** — `Verdict.overall` is always the maximum severity across
   all reasons (case-level + per-label). An empty reason set yields `PASS`.

The module lives at `src/segqc/verdict.py`. It has **no runtime dependencies
beyond the Python standard library** — no NumPy, no NiBabel, no I/O.

### Scope boundary

| Concern | Owned by | This item |
|---|---|---|
| Empty / near-empty detection logic | Item 007 | `Verdict` objects constructed *by* 007; model defined here |
| JSON serialisation (`verdict` key in report) | Item 009 | model only; no `to_dict()` / `to_json()` here |
| Human-readable rendering | Item 010 | model only; no string formatting beyond `Reason.message` |
| Heuristic rule engine | Stage 4 | model is the *output* contract; rules are defined later |
| CLI wiring | Item 010 | no CLI changes in this item |

---

## Acceptance Criteria

- [ ] **AC-1 `Severity` enum exists** with exactly three members (`PASS`, `FLAG`,
      `FAIL`) and supports total ordering such that `PASS < FLAG < FAIL`
      (i.e. `Severity.PASS < Severity.FLAG < Severity.FAIL` evaluates to `True`).
- [ ] **AC-2 `Severity` string labels** map correctly: `str(Severity.PASS)` or
      `.label` yields `"pass"`, `FLAG` → `"flagged-for-review"`, `FAIL` → `"fail"`.
- [ ] **AC-3 `Reason` dataclass** has at minimum: `message: str`,
      `severity: Severity`, `labels: frozenset[int]` (empty by default). The
      `message` must be a non-empty string.
- [ ] **AC-4 `Verdict` dataclass** has: `overall: Severity`,
      `reasons: list[Reason]` (case-level), `per_label: dict[int, list[Reason]]`.
      `overall` is always the maximum severity across all contained reasons.
- [ ] **AC-5 Empty reasons → `PASS`**: a `Verdict` constructed with no case-level
      reasons and no per-label reasons has `overall == Severity.PASS`.
- [ ] **AC-6 Aggregation by severity**: given a mix of `PASS`, `FLAG`, and `FAIL`
      reasons, `overall` equals the maximum (`FAIL` wins). Removing the single
      `FAIL` reason yields `FLAG`; removing all non-`PASS` reasons yields `PASS`.
- [ ] **AC-7 Per-vertebra attribution**: adding reasons to `per_label[42]` is
      reflected in `overall` (if that reason's severity exceeds the current
      `overall`). Per-label reasons do not appear in `reasons`.
- [ ] **AC-8 Immutability contract**: after a `Verdict` is finalised,
      mutating the list or dict returned by `.reasons` / `.per_label` does not
      change the `overall` verdict (i.e. the `overall` field is computed at
      construction/finalisation time, not lazily on every access, *or* the
      returned collections are copies/immutable views).
- [ ] **AC-9 Module location**: the model is importable as
      `from segqc.verdict import Severity, Reason, Verdict` with no import errors.
- [ ] **AC-10 No stdlib-external runtime imports**: `import segqc.verdict` must
      not require NumPy, NiBabel, SciPy, or any non-stdlib package.

---

## Implementation Steps

1. **Create `src/segqc/verdict.py`**:
   - Define `Severity` using `enum.IntEnum` (gives total ordering for free) or
     `enum.Enum` with `functools.total_ordering`. Add a `.label` property
     returning the output string.
   - Define `Reason` as a `dataclasses.dataclass(frozen=True)` with `message: str`,
     `severity: Severity`, and `labels: frozenset[int] = field(default_factory=frozenset)`.
   - Define `Verdict` as a `dataclasses.dataclass`. Provide a class method
     `Verdict.build(reasons, per_label)` (or `__init__`) that computes `overall`
     from all supplied reasons. Store `reasons` as a `tuple` (immutable) and
     `per_label` as a `dict[int, tuple[Reason, ...]]` to satisfy AC-8.

2. **Export from `src/segqc/__init__.py`**: add
   `from segqc.verdict import Severity, Reason, Verdict` to the public surface,
   or add to the existing `__all__` list.

3. **Wire into item 007**: when item 007's empty-detection logic fires, it should
   construct a `Verdict` with the appropriate `Severity` and `Reason.message`.
   (This wiring may be done in item 007 or in item 010; document in decisions.)

4. **Write `tests/test_008_verdict.py`** covering all ten ACs.

---

## Testing Strategy

- **Framework:** `pytest` (item 002 harness).
- **No fixtures needed beyond `tmp_path`** (but `tmp_path` is not needed here
  at all — the model is pure Python).
- **Test module:** `tests/test_008_verdict.py`.
- **Coverage:** all ten ACs; adversarial / edge cases: empty reason sets,
  single-member sets, large sets, boundary severity comparisons, mutation after
  finalisation.
- **No external services, no I/O, no network.**

---

## Dependencies

- **Upstream:**
  - Item 001 (package skeleton, `src/segqc/` exists) — ✅ merged
  - Item 007 (empty / near-empty detection) — item 007 will *use* this model;
    strictly, 007 and 008 can be developed in parallel. 008 has no code
    dependency on 007.
- **Downstream:**
  - Item 009 (JSON report schema) — serialises the `Verdict` produced here.
  - Item 010 (human-readable report + pipeline wiring) — renders and wires
    the `Verdict`.

---

## Decisions & Trade-offs

To be updated during implementation.

---

## Testing Prerequisites

### Required Services

**None.** Pure Python; no external services.

### Environment Configuration

- **Python:** 3.9+ in `.venv` at project root.
- **Install:** `pip install -e .[dev]` (no new deps expected).
- **Environment variables / secrets:** none.
- **Ports:** none.

### Manual Validation Checklist

- [ ] **Build succeeds:** `pip install -e .[dev]` exits 0.
- [ ] **Tests pass:** `python -m pytest tests/test_008_verdict.py` is green.
- [ ] **Import check:** `python -c "from segqc.verdict import Severity, Reason, Verdict; print('ok')"` prints `ok`.
- [ ] **Severity order:** `python -c "from segqc.verdict import Severity; assert Severity.PASS < Severity.FLAG < Severity.FAIL; print('order ok')"` prints `order ok`.

### Expected Outcomes

- `Severity`, `Reason`, and `Verdict` are importable and behave as specified.
- `pytest tests/test_008_verdict.py` reports 0 failures.
- `pytest` (full suite) reports 0 failures — no regressions in items 001–007.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md):

- Flip the Stage 1 **"QC verdict model…"** deliverable from 📋 → ✅ (mark 🚧
  while in progress).
- Per `CLAUDE.md`: work on branch `aide/008-qc-verdict-model`, `git pull
  --rebase` before editing `progress.md`, keep edits scoped to this item's
  rows, and direct-merge (no PR required) once green.

---

## Next Step

Start a **new chat session** and run `/speckit-aide-execute-item 008` to
implement this work item.
