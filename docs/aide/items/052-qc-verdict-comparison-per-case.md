# Item 052 — QC-verdict comparison & per-case outcome classification

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 7 — Evaluation, Calibration & Metrics (G3, G7)
> **Queue:** [`../queue/queue-006.md`](../queue/queue-006.md) · Item 052
> **Objectives:** G7 (evaluable / regression-testable — supplies the §8 level-1
> **QC-verdict** comparison primitive); supports G3 (produces the TP/FP/TN/FN
> substrate the Stage-7 FPR-on-GT and per-mode-sensitivity metrics aggregate over)
> **Suggested branch:** `aide/052-qc-verdict-comparison-per-case`

---

## Description

Provide the **QC-verdict** comparison layer — **level 1** of the vision's §8
three-level evaluation (`1. QC pass/fail verdict; 2. segmentation overlap / DICE;
3. feature-set match`). This is the simplest / coarsest level: it compares the
pipeline's **actual** per-case QC verdict against a case's **expected truth** and
classifies the outcome into the four confusion-matrix cells — **TP / FP / TN /
FN** — then, for cases that were *expected to fail*, records the per-§6-mode
**caught / missed** signal and whether the case's **designated rule** fired on the
**expected offending label(s)**.

Deliver a **pure** module `segqc/eval/outcome.py` that, given

- an **expected** side — a `pass` expectation for a clean ground-truth case, or a
  known synthetic/curated failure carrying its expected verdict, §6 failure mode,
  designated Stage-4 rule id(s), and expected offending labels (exactly the shape
  of `segqc.synth.perturbation.Expectation.to_dict()` / a `tests/corpus`
  manifest-case entry, or a hand-built dict for a VerSe / TotalSegmentator
  human-provided expectation); and
- an **actual** side — the pipeline's `segqc.aggregate.CaseResult` (its `Verdict`
  plus the ordered `Finding` list that carries each finding's `rule_id` and
  offending `labels`),

returns a single frozen `CaseOutcome` classifying that one case. The primitive
performs **no pipeline execution and no I/O** — records in, classified outcome
out. Item **053**'s harness runs `segqc run` per case and calls this once per
case; item **054** aggregates the returned `CaseOutcome`s into FPR-on-GT and
per-mode sensitivity.

This is the third of three independent Stage-7 comparison primitives — 050 (DICE /
overlap, level 2), 051 (feature-set match, level 3), **052 (verdict-outcome, level
1)** — that item 053 assembles per case. It follows the sibling primitives' house
style: a pure module in `segqc/eval/`, frozen dataclasses, `SegQCInputError` for
malformed input, and re-export from `segqc/eval/__init__.py`.

**In scope:** `segqc/eval/outcome.py` containing the `Outcome` enum, the frozen
dataclass `CaseOutcome`, and the `classify_outcome(...)` function; a re-export from
`segqc/eval/__init__.py`; and `tests/test_052_outcome.py`.

**Out of scope (do NOT):** running the pipeline / any rule / any label-map or file
I/O (the caller supplies an already-computed `CaseResult` and an expectation
record); any cross-case aggregation, counting, FPR / sensitivity / correlation, or
calibration (items 053–055 — this primitive classifies **one** case and computes
**no** rates); DICE / overlap (item 050) or feature-set divergence (item 051);
defining or changing the §6 failure-mode taxonomy, the `Expectation`/manifest
schema, the `Verdict`/`Finding`/`CaseResult` models, the CLI, the config, or the
report schema (all consumed as-is from merged stages).

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each in
`tests/test_052_outcome.py` (see Testing Strategy)._

- [ ] **AC1: module & public API exist.** `segqc.eval.outcome` exposes
  `classify_outcome(expected, actual, *, positive_severity=Severity.FLAG)
  -> CaseOutcome`, the `Outcome` enum, and the frozen dataclass `CaseOutcome`;
  all three are listed in the module `__all__` and importable both as
  `from segqc.eval.outcome import classify_outcome, Outcome, CaseOutcome` and
  (re-exported) `from segqc.eval import classify_outcome`. `Outcome` has exactly
  the members `TRUE_POSITIVE`, `FALSE_POSITIVE`, `TRUE_NEGATIVE`,
  `FALSE_NEGATIVE`, each with a `.label` property returning `"TP"`, `"FP"`,
  `"TN"`, `"FN"` respectively. `CaseOutcome` carries the fields `outcome: Outcome`,
  `expected_verdict: str`, `actual_verdict: str`, `expected_failure: bool`,
  `actual_flagged: bool`, `caught: Optional[bool]`, `failure_mode: Optional[int]`,
  `failure_mode_name: Optional[str]`, `expected_rule_ids: Tuple[str, ...]`,
  `expected_labels: Tuple[int, ...]`, `fired_rule_ids: Tuple[str, ...]`,
  `designated_rule_fired: bool`, `caught_by_designated_rule: bool`.

- [ ] **AC2: clean GT that passes → TN.** For an expected side with
  `expected_verdict == "pass"` and an actual `CaseResult` whose verdict `overall`
  is `Severity.PASS` (no findings), the result has `outcome is Outcome.TRUE_NEGATIVE`,
  `expected_failure is False`, `actual_flagged is False`, `caught is None`
  (not a failure case), `actual_verdict == "pass"`.

- [ ] **AC3: clean GT wrongly flagged → FP.** For an expected side with
  `expected_verdict == "pass"` and an actual `CaseResult` whose verdict `overall`
  is `Severity.FLAG` **or** `Severity.FAIL`, the result has
  `outcome is Outcome.FALSE_POSITIVE`, `expected_failure is False`,
  `actual_flagged is True`, `caught is None`, and `fired_rule_ids` lists the
  actual findings' rule ids (deduplicated, sorted).

- [ ] **AC4: known failure caught by its designated rule on the expected label →
  TP, mode caught.** For an expected side with `expected_verdict == "fail"` (or
  `"flagged-for-review"`), a `failure_mode` `m > 0`, `expected_rule_ids == {"r"}`,
  and `expected_labels == {L}`, and an actual `CaseResult` that flags the case with
  a `Finding(rule_id="r", labels={L, ...})`, the result has
  `outcome is Outcome.TRUE_POSITIVE`, `expected_failure is True`,
  `actual_flagged is True`, `caught is True`, `failure_mode == m`,
  `failure_mode_name` populated, `designated_rule_fired is True`, and
  `caught_by_designated_rule is True`.

- [ ] **AC5: known failure that passes → FN, mode missed.** For the same expected
  failure side as AC4 but an actual `CaseResult` whose verdict `overall` is
  `Severity.PASS`, the result has `outcome is Outcome.FALSE_NEGATIVE`,
  `expected_failure is True`, `actual_flagged is False`, `caught is False`
  (mode missed), `designated_rule_fired is False`, and
  `caught_by_designated_rule is False`.

- [ ] **AC6: `flag` counts as a raised concern by default (ternary→binary
  reduction).** With the default `positive_severity == Severity.FLAG`, a
  `CaseResult` whose verdict `overall` is `Severity.FLAG` yields
  `actual_flagged is True`; against an `expected_verdict == "fail"` case this is a
  TP (level 1 asks only "did the pipeline raise a concern", not whether the exact
  severity matched). Symmetrically, an `expected_verdict == "flagged-for-review"`
  case yields `expected_failure is True`.

- [ ] **AC7: `positive_severity` raises the bar for "flagged".** With
  `positive_severity=Severity.FAIL`, a `CaseResult` whose verdict `overall` is
  `Severity.FLAG` yields `actual_flagged is False`; so an
  `expected_verdict == "pass"` case with only a `FLAG` verdict is `TRUE_NEGATIVE`
  (not FP), and an `expected_verdict == "fail"` case with only a `FLAG` verdict is
  `FALSE_NEGATIVE`. The expected side is reduced with the **same** threshold, so an
  `expected_verdict == "flagged-for-review"` case yields `expected_failure is False`
  under `positive_severity=Severity.FAIL`.

- [ ] **AC8: flagged by an incidental (non-designated) rule → TP but designated
  rule not credited.** For an expected failure side with `expected_rule_ids ==
  {"r"}` and `expected_labels == {L}`, and an actual `CaseResult` that flags the
  case only via a `Finding(rule_id="other", labels={L})` (rule id ≠ expected), the
  result has `outcome is Outcome.TRUE_POSITIVE`, `caught is True` (the failure was
  raised), but `designated_rule_fired is False` and
  `caught_by_designated_rule is False` (the sensitivity substrate credits only the
  designated rule).

- [ ] **AC9: designated rule fired on the WRONG label → rule fired, not credited
  as caught-by-designated.** For an expected failure side with
  `expected_rule_ids == {"r"}` and `expected_labels == {L}`, and an actual
  `Finding(rule_id="r", labels={K})` where `K != L` (and the case is flagged), the
  result has `designated_rule_fired is True` but `caught_by_designated_rule is
  False` (the designated rule must fire on **≥1 expected label** to count as caught
  by the designated rule); `outcome is Outcome.TRUE_POSITIVE`, `caught is True`.

- [ ] **AC10: partial label match counts (≥1 expected label suffices).** For an
  expected failure side with `expected_labels == {L1, L2}` and an actual
  `Finding(rule_id="r", labels={L1})` matching the expected rule on **one** of the
  two expected labels, `caught_by_designated_rule is True` (intersection is
  non-empty; not every expected label need be hit).

- [ ] **AC11: case-level expected finding (no expected labels) — rule id match
  alone suffices.** For an expected failure side with `expected_rule_ids == {"r"}`
  and `expected_labels == {}` (empty — a case-level failure with no specific label
  attribution) and an actual `Finding(rule_id="r", labels={})` (or any labels),
  `designated_rule_fired is True` and `caught_by_designated_rule is True` (with no
  expected label to intersect, a designated-rule match is sufficient).

- [ ] **AC12: multiple expected rule ids — any one firing credits the mode.** For
  an expected failure side with `expected_rule_ids == {"r1", "r2"}` and an actual
  case flagged with a `Finding(rule_id="r2", labels={L})` on an expected label
  `L`, `designated_rule_fired is True` and `caught_by_designated_rule is True`
  (the union of expected rule ids is matched by intersection).

- [ ] **AC13: expected side accepts the `Expectation.to_dict()` / manifest-case
  mapping, with optional §6 fields defaulting.** `classify_outcome` accepts an
  `expected` **mapping** whose only required key is `expected_verdict`;
  `expected_rule_ids`, `expected_labels`, `failure_mode`, and `failure_mode_name`
  are optional. Given a mapping equal to a `tests/corpus` manifest-case entry (or
  `Expectation.to_dict()`), the corresponding `CaseOutcome` fields are populated
  from it; given a minimal `{"expected_verdict": "pass"}` (a human-provided VerSe
  expectation with no §6 metadata), the result classifies correctly with
  `failure_mode is None`, `failure_mode_name is None`, `expected_rule_ids == ()`,
  `expected_labels == ()`.

- [ ] **AC14: expected/actual rule-id & label sets are order-independent and
  deduplicated.** `expected_rule_ids`, `expected_labels`, and `fired_rule_ids` on
  the returned `CaseOutcome` are deterministically ordered (rule ids sorted lexically,
  labels sorted ascending) and deduplicated, regardless of the input container type
  (list / set / frozenset / tuple) or ordering of the expectation mapping and the
  actual finding list.

- [ ] **AC15: malformed expected input raises `SegQCInputError`.** Calling
  `classify_outcome` when `expected` is not a mapping, or lacks `expected_verdict`,
  or carries an `expected_verdict` that is not one of the three recognised labels
  (`"pass"`, `"flagged-for-review"`, `"fail"`), raises `segqc.io.SegQCInputError`
  with a clear message — not a raw `KeyError` / `TypeError` / `ValueError`.

- [ ] **AC16: malformed actual input raises `SegQCInputError`.** Calling
  `classify_outcome` when `actual` does not expose a `verdict` with a `Severity`
  `overall` and an iterable `findings` of rule-id-bearing findings (e.g. `actual`
  is `None`, or a mapping, or an object missing `.verdict` / `.findings`) raises
  `segqc.io.SegQCInputError` with a clear message — not a raw `AttributeError`.

- [ ] **AC17: pure, deterministic, and non-mutating.** Two `classify_outcome`
  calls on the same inputs return equal `CaseOutcome`s; the `expected` mapping
  (and any nested containers) and the `actual` `CaseResult` are unchanged after
  the call; the function performs no file I/O.

## Assumptions  <!-- MANDATORY: clarify mode = assume -->

- **The `expected` side is a mapping in the `Expectation.to_dict()` /
  manifest-case shape; the `actual` side is a `segqc.aggregate.CaseResult`
  (clarify `assume`).** The queue says "records in, classified outcome out" but
  does not pin the record types. Two facts fix the choice: (1) the expected truth
  is *already serialised as a dict* everywhere it lives — `tests/corpus/
  manifest.json` cases and `Expectation.to_dict()` both emit
  `{expected_verdict, expected_rule_ids, expected_labels, failure_mode,
  failure_mode_name, detail}` — and a VerSe / TotalSegmentator "human-provided
  expected outcome" is naturally a hand-built dict of the same keys; taking a
  **mapping** therefore decouples `segqc.eval` from `segqc.synth` (mirroring item
  051's "features-block dict in" decision) and covers all three expectation
  sources. (2) The actual verdict is produced *in memory* by the pipeline as a
  `CaseResult` (`verdict: Verdict` + `findings: Tuple[Finding, ...]`), which is the
  only object that carries **both** the aggregated verdict severity **and** the
  per-finding `rule_id` / `labels` this item needs (the flattened `Verdict.reasons`
  drop `rule_id`). `actual` is consumed **duck-typed** — any object exposing
  `.verdict.overall: Severity` and an iterable `.findings` of objects with
  `.rule_id: str` and `.labels` works; `CaseResult` is the reference type. If the
  `Expectation`/manifest keys or the `CaseResult`/`Verdict`/`Finding` fields have
  diverged from this description, the builder/validator should hand back.

- **Ternary verdict → binary "flagged" reduction at `positive_severity`
  (default `Severity.FLAG`) (clarify `assume`).** Level 1 is the *coarsest* level:
  the classification is a **2×2** confusion matrix, so the three-level verdict
  (`pass` / `flagged-for-review` / `fail`) is reduced to a binary "did the pipeline
  raise a concern?" signal. `actual_flagged := actual.verdict.overall >=
  positive_severity`; `expected_failure := severity_of(expected_verdict) >=
  positive_severity`. With the default `Severity.FLAG`, both `flagged-for-review`
  and `fail` count as positive (matches the task's "correctly flag/fail a bad case
  (true positive)" and "incorrectly flag a clean case (false positive)"); the
  keyword-only `positive_severity` lets a caller (e.g. a strict calibration sweep)
  raise the bar to `Severity.FAIL`, and is applied to **both** sides identically so
  the comparison stays symmetric. The exact `pass`/`flag`/`fail` strings are
  preserved verbatim in `expected_verdict` / `actual_verdict` for downstream
  reporting; only the binary reduction drives `outcome`.

- **`expected_verdict` is authoritative for `expected_failure`; `failure_mode`
  is recorded metadata (clarify `assume`).** The binary "is this a bad case"
  decision reads `expected_verdict` (the direct statement of the expectation).
  `failure_mode` (§6 key `0..8`, `0` = `CLEAN_CONTROL_MODE`) and
  `failure_mode_name` are carried through as metadata for the per-mode sensitivity
  aggregation (054) but do **not** override the verdict-based `expected_failure`.
  For every corpus case these agree (mode `0` ⇔ `pass`); should a caller ever
  supply a contradictory pair, `expected_verdict` wins and `failure_mode` is still
  recorded as given. `failure_mode`/`failure_mode_name` default to `None` when the
  expectation carries no §6 metadata (a plain VerSe pass/fail expectation).

- **`caught` (per-mode) vs `caught_by_designated_rule` (strict) are distinct,
  documented resolutions of "ambiguous/partial matches" (clarify `assume`).**
  - `caught` is defined **only for failure cases** (`expected_failure is True`);
    it equals `actual_flagged` — i.e. TP ⇒ `caught is True`, FN ⇒ `caught is
    False`. For clean-expected cases `caught is None` (not applicable). This is the
    coarse "was the failure raised at all" signal.
  - `designated_rule_fired` is `True` when the **union** of `expected_rule_ids`
    intersects the set of actual `fired_rule_ids` (any one designated rule firing
    counts — AC12).
  - `caught_by_designated_rule` is `True` when some actual `Finding` has
    `rule_id ∈ expected_rule_ids` **and** either (a) `expected_labels` is empty (a
    case-level expected finding — rule-id match alone suffices, AC11) or (b) that
    finding's `labels` intersect `expected_labels` on **≥1** label (partial match
    counts — AC10; a designated rule firing on the *wrong* label does **not** count
    — AC9). This is the per-mode **sensitivity** substrate 054 aggregates ("fraction
    of each mode's cases caught **by its designated rule**"). It is intentionally
    stricter than `caught`: a case can be TP / `caught is True` yet
    `caught_by_designated_rule is False` when an incidental rule raised the flag
    (AC8). `caught_by_designated_rule` implies `actual_flagged` (a fired finding of
    non-`PASS` severity makes the verdict non-`PASS`), so it is only ever `True` on
    a TP.

- **`fired_rule_ids` is the deduplicated, sorted set of the actual findings'
  `rule_id`s.** Recorded for reporting / debugging so the harness record shows
  *which* rules fired, independent of whether they were the designated ones. Labels
  and rule-id sets on `CaseOutcome` are normalised to sorted, deduplicated tuples
  (AC14) so the dataclass is order-stable and equality-comparable regardless of
  input container/order.

- **Background label `0` is irrelevant here.** This primitive never touches label
  maps; `expected_labels` and finding `labels` are already the non-background
  vertebra ids produced upstream, compared as plain integer sets.

- **Interface pins (dependencies already ✅).** From item 008 `segqc.verdict`:
  `Severity` (`PASS < FLAG < FAIL`, `.label`) and `Verdict` (`.overall:
  Severity`). From item 034 `segqc.aggregate`: `CaseResult` (`.verdict: Verdict`,
  `.findings: Tuple[Finding, ...]`). From item 026 `segqc.heuristics.finding`:
  `Finding` (`.rule_id: str`, `.labels: FrozenSet[int]`, `.severity`). From item
  003 `segqc.io`: `SegQCInputError` (the single malformed-input error type,
  reused as in 050/051). The expected-side mapping shape matches item 036
  `segqc.synth.perturbation.Expectation.to_dict()` and the item 040
  `tests/corpus/manifest.json` case entries. If any of these has diverged, hand
  back.

## Implementation Steps

Code path in `src/segqc/` (`aide.toml` `source_dir = src/segqc`).

1. **`src/segqc/eval/outcome.py` — module docstring + imports.** Docstring
   stating: §8 level-1 QC-verdict comparison; pure, no I/O, no pipeline execution;
   the 2×2 TP/FP/TN/FN classification via the `positive_severity` ternary→binary
   reduction; the distinction between `caught` (any flag) and
   `caught_by_designated_rule` (designated rule on ≥1 expected label); the expected
   mapping shape and the duck-typed `CaseResult` actual side; that it is the
   substrate 054 aggregates. Import `enum`, `dataclasses.dataclass`, typing
   helpers, `Severity` from `segqc.verdict`, and `SegQCInputError` from
   `segqc.io`. Declare `__all__`.

2. **`Outcome` enum.** Members `TRUE_POSITIVE`, `FALSE_POSITIVE`, `TRUE_NEGATIVE`,
   `FALSE_NEGATIVE`; a `.label` property mapping to `"TP"` / `"FP"` / `"TN"` /
   `"FN"` (mirroring `Severity.label`'s pattern). Add a small helper (e.g. a
   classmethod `Outcome.from_flags(expected_failure: bool, actual_flagged: bool)`)
   returning the correct member from the two booleans:
   `(True, True) → TRUE_POSITIVE`, `(False, True) → FALSE_POSITIVE`,
   `(False, False) → TRUE_NEGATIVE`, `(True, False) → FALSE_NEGATIVE`.

3. **`CaseOutcome` frozen dataclass** with the fields listed in AC1.

4. **Severity-label lookup.** A private `_severity_of(label: str) -> Severity`
   mapping the three verdict strings to `Severity` members (reuse the same
   string↔severity mapping shape as `finding._LABEL_TO_SEVERITY`), raising
   `SegQCInputError` for an unrecognised label.

5. **Expected-side validation + extraction.** A private helper that:
   - raises `SegQCInputError` if `expected` is not a `Mapping` or lacks
     `expected_verdict`;
   - reads `expected_verdict` (validated via `_severity_of`);
   - reads optional `expected_rule_ids` → sorted, deduped `Tuple[str, ...]`
     (default `()`), `expected_labels` → sorted, deduped `Tuple[int, ...]`
     (default `()`), `failure_mode` → `Optional[int]` (default `None`),
     `failure_mode_name` → `Optional[str]` (default `None`).

6. **Actual-side validation + extraction.** A private helper that raises
   `SegQCInputError` unless `actual` exposes `.verdict.overall` that is a
   `Severity` and an iterable `.findings` whose items each expose `.rule_id`;
   returns `(overall_severity, findings_tuple)`. Compute
   `fired_rule_ids = tuple(sorted({f.rule_id for f in findings}))`.

7. **`classify_outcome(expected, actual, *, positive_severity=Severity.FLAG)`.**
   1. Extract the expected side (step 5) and actual side (step 6).
   2. `expected_failure = _severity_of(expected_verdict) >= positive_severity`.
   3. `actual_flagged = overall_severity >= positive_severity`.
   4. `outcome = Outcome.from_flags(expected_failure, actual_flagged)`.
   5. `caught = actual_flagged if expected_failure else None`.
   6. `designated_rule_fired = bool(set(expected_rule_ids) & set(fired_rule_ids))`.
   7. `caught_by_designated_rule =` any finding with
      `f.rule_id in expected_rule_ids` and
      `(not expected_labels or set(f.labels) & set(expected_labels))`.
   8. Return a fully-populated `CaseOutcome` (verdict strings preserved verbatim;
      rule-id/label tuples normalised sorted+deduped).

8. **Never mutate inputs.** Read only from the `expected` mapping and the `actual`
   object; build fresh tuples / dataclasses. No file access anywhere in the module.

9. **`src/segqc/eval/__init__.py` — re-export.** Add
   `from .outcome import classify_outcome, Outcome, CaseOutcome` and extend
   `__all__`; update the package docstring to mention the level-1 verdict-outcome
   primitive alongside levels 2 and 3.

## Testing Strategy

One focused test per AC in **`tests/test_052_outcome.py`**. Build the expected side
as small hand-written dicts and the actual side with a tiny in-test helper that
assembles a real `segqc.aggregate.CaseResult` from `segqc.heuristics.finding.Finding`
objects via `segqc.aggregate.build_case_result` (or by constructing a `Verdict`
directly) — no loader, no NIfTI, no pipeline, no disk fixtures. A minimal
`HeuristicConfig`-like stub exposing `policy_param("flag_escalation_count", 0) → 0`
is sufficient for `build_case_result`, or construct the `CaseResult` directly from a
`Verdict.build(...)` + findings tuple to avoid config entirely. Every expected
outcome/flag is hand-reasoned and exact.

- **AC1** — import the three names from both `segqc.eval.outcome` and (the
  function) `segqc.eval`; assert `CaseOutcome` is frozen and exposes the documented
  fields; assert the four `Outcome` members and their `.label` values.
- **AC2** — `{"expected_verdict": "pass"}` + a no-findings `PASS` `CaseResult`;
  assert `TRUE_NEGATIVE`, `caught is None`.
- **AC3** — `pass` expectation + a `FLAG` `CaseResult` (and a second sub-case with
  a `FAIL` `CaseResult`); assert `FALSE_POSITIVE`, `actual_flagged is True`,
  `fired_rule_ids` populated.
- **AC4** — fail expectation (`failure_mode=2`, `expected_rule_ids={"fragmentation"}`,
  `expected_labels={22}`) + a `CaseResult` flagged by `Finding("fragmentation",
  FAIL, "...", {22})`; assert `TRUE_POSITIVE`, `caught is True`,
  `designated_rule_fired`, `caught_by_designated_rule`, `failure_mode == 2`.
- **AC5** — same fail expectation + a `PASS` `CaseResult`; assert `FALSE_NEGATIVE`,
  `caught is False`, both designated flags `False`.
- **AC6** — a `FLAG`-only `CaseResult` vs a `fail` expectation → TP under default
  threshold; a `flagged-for-review` expectation → `expected_failure is True`.
- **AC7** — with `positive_severity=Severity.FAIL`: a `FLAG` `CaseResult` +
  `pass` expectation → `TRUE_NEGATIVE`; a `FLAG` `CaseResult` + `fail` expectation
  → `FALSE_NEGATIVE`; a `flagged-for-review` expectation → `expected_failure is
  False`.
- **AC8** — fail expectation (`expected_rule_ids={"r"}`, `expected_labels={L}`) +
  `CaseResult` flagged only by `Finding("other", FAIL, "...", {L})`; assert
  `TRUE_POSITIVE`, `caught is True`, `designated_rule_fired is False`,
  `caught_by_designated_rule is False`.
- **AC9** — `Finding("r", FAIL, "...", {K})` with `K != L`; assert
  `designated_rule_fired is True`, `caught_by_designated_rule is False`, still TP.
- **AC10** — `expected_labels={L1, L2}` + `Finding("r", FAIL, "...", {L1})`; assert
  `caught_by_designated_rule is True`.
- **AC11** — `expected_labels={}` (empty) + `Finding("r", FAIL, "...", set())`;
  assert `designated_rule_fired` and `caught_by_designated_rule` both `True`.
- **AC12** — `expected_rule_ids={"r1","r2"}` + `Finding("r2", FAIL, "...", {L})`
  on expected `L`; assert both designated flags `True`.
- **AC13** — a full manifest-case-shaped dict (all keys) round-trips into the
  populated fields; a minimal `{"expected_verdict": "pass"}` yields
  `failure_mode is None`, `failure_mode_name is None`, `expected_rule_ids == ()`,
  `expected_labels == ()`.
- **AC14** — pass `expected_rule_ids`/`expected_labels` as unsorted lists with a
  duplicate, and findings out of order; assert the `CaseOutcome`'s
  `expected_rule_ids`/`expected_labels`/`fired_rule_ids` are sorted and
  deduplicated (equality independent of input order).
- **AC15** — `classify_outcome(None, actual)`, `classify_outcome({}, actual)` (no
  `expected_verdict`), and `classify_outcome({"expected_verdict": "bogus"}, actual)`
  → each `pytest.raises(SegQCInputError)`.
- **AC16** — `classify_outcome(exp, None)`, `classify_outcome(exp, {"verdict": ...})`
  (a mapping, not a `CaseResult`), and an object missing `.findings` → each
  `pytest.raises(SegQCInputError)`.
- **AC17** — call twice, assert equal `CaseOutcome`s; deepcopy-snapshot the expected
  dict and confirm the `CaseResult`/expected dict are unchanged after the call.

Adversarial / edge cases folded in: an expected failure with **no**
`expected_rule_ids` (e.g. a reconstructed-record mode) → `designated_rule_fired is
False` and `caught_by_designated_rule is False` even when TP (caught by verdict but
no designated rule to credit); a clean case flagged by multiple rules → `FP` with
all `fired_rule_ids` listed; an actual case with duplicate `rule_id`s across
findings → `fired_rule_ids` deduplicated; `expected_labels` given as a `frozenset`
vs `list` vs `set` (all normalise identically); a `flagged-for-review` **actual**
verdict against a `flagged-for-review` **expected** verdict → `TRUE_POSITIVE` under
default threshold.

## Dependencies

- **Item 008 (✅)** — `segqc.verdict`: `Severity` (ordered `PASS < FLAG < FAIL`,
  `.label`) and `Verdict` (`.overall`) — the actual-verdict model this classifies.
- **Item 026 (✅)** — `segqc.heuristics.finding`: `Finding` (`.rule_id`,
  `.labels`, `.severity`) — the per-finding rule attribution read for the
  designated-rule check.
- **Item 034 (✅)** — `segqc.aggregate`: `CaseResult` (`.verdict`, `.findings`) —
  the reference actual-side type (consumed duck-typed).
- **Item 003 (✅)** — `segqc.io`: `SegQCInputError` (reused malformed-input type).
- **Items 036 / 040 (✅)** — `segqc.synth.perturbation.Expectation.to_dict()` and
  the `tests/corpus/manifest.json` case shape define the expected-side mapping
  (`expected_verdict`, `expected_rule_ids`, `expected_labels`, `failure_mode`,
  `failure_mode_name`); consumed as a mapping, not imported.
- No dependency on the sibling Stage-7 primitives 050 / 051; item **053**
  (harness) depends on this module, not the reverse.

## Decisions & Trade-offs

To be updated during implementation.
