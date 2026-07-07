# Item 034 — Verdict Aggregation & Severity

> **Created:** 2026-07-07 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 034
> **Objectives:** G2 (culminate the §6 failure-mode rules into a single per-case
> verdict), G4 (per-case QC report — the aggregated `pass` / `flagged-for-review`
> / `fail` verdict plus per-case and per-vertebra reasons the report layer renders)
> **Suggested branch:** `aide/034-verdict-aggregation-severity`

---

## Description

Implement the **verdict-aggregation layer** that folds the `Finding` objects
produced by all Stage 4 rule families (items 027–033, run through the item-026
`run_rules` runner) into the existing Stage 1 **QC verdict** model
(`segqc.verdict.Verdict`: `Severity` `PASS < FLAG < FAIL`, `Reason`, `Verdict`).
The layer maps each finding's severity to the per-case verdict
(`pass` / `flagged-for-review` / `fail`) through a **documented, config-driven
severity policy**, preserves both **per-case** and **per-vertebra** reasons, and
bundles the derived verdict together with the **full finding list** into a small
`CaseResult` container so the report layer (item 035) can render every flag —
including its `rule_id` — verbatim.

This is the join between the rule engine (heuristics) and the report model. It is
pure, deterministic data transformation over already-computed findings: it never
runs a rule, never touches a label map, spline, or feature extractor, and never
performs I/O.

### The inputs this layer consumes

- **`list[Finding]`** — the aggregated output of
  `segqc.heuristics.run_rules(record, config)` (item 026). Each `Finding`
  (`segqc.heuristics.finding.Finding`) carries `rule_id: str`,
  `severity: Severity` (**reuses** `segqc.verdict.Severity`, so no translation is
  needed), `reason: str` (non-empty, human-readable), and
  `labels: frozenset[int]` (the offending vertebra labels; empty for a
  case-level finding).
- **`HeuristicConfig`** — the versioned config (item 005). The severity policy is
  read from a new top-level `verdict` section via a new
  `HeuristicConfig.policy_param(key, default)` accessor (see *Config shape*).
- **Optional base reasons** — the pre-existing Stage 1 reasons (e.g. the
  empty/near-empty check that the CLI already turns into `Reason` objects in
  `cli.py::_handle_run`, step 4). The queue requires the findings be aggregated
  **into the existing verdict**, so the aggregator accepts an optional
  `base_reasons` (case-level) and `base_per_label` (per-vertebra) and merges them
  with the finding-derived reasons rather than replacing them.

### What this layer does

A new module **`src/segqc/aggregate.py`** exposes:

- **`finding_to_reason(finding) -> Reason`** — maps one `Finding` to a
  `segqc.verdict.Reason`: `message = finding.reason`, `severity =
  finding.severity`, `labels = finding.labels` (the full offending set, carried
  verbatim). `rule_id` has no home on `Reason` and is intentionally **not**
  folded into the message — it is preserved on the raw `Finding` inside
  `CaseResult` instead.

- **`aggregate_verdict(findings, config, *, base_reasons=(), base_per_label=None)
  -> Verdict`** — the core aggregator:
  1. Convert each finding to a `Reason`. A finding with an **empty** `labels`
     set becomes a **case-level** reason; a finding with a **non-empty** `labels`
     set is attributed to **every** label in the set — its `Reason` (retaining
     the full label frozenset) is appended to `per_label[label]` for each
     `label` in ascending order.
  2. Merge the optional Stage 1 `base_reasons` (case-level) and `base_per_label`
     (per-vertebra) **before** the finding-derived reasons, preserving input
     order, so the existing verdict is extended, not overwritten.
  3. Apply the **config-driven severity policy** (below) and return
     `Verdict.build(reasons=case_reasons, per_label=per_label)`, which recomputes
     `overall` as the maximum severity across all contained reasons.

- **`CaseResult`** — a frozen dataclass bundling `verdict: Verdict` and
  `findings: tuple[Finding, ...]` — the "case result" the queue asks to attach
  the derived verdict and the full finding list to, so the report layer can
  render both (findings give the report access to `rule_id`, which the flattened
  `Reason`s drop).

- **`build_case_result(findings, config, *, base_reasons=(), base_per_label=None)
  -> CaseResult`** — convenience that calls `aggregate_verdict` and packages the
  derived verdict with `tuple(findings)`.

### The severity policy (documented, config-driven)

**Default — severity dominance.** With no `verdict` config section (or an empty
one), the per-case verdict is the **maximum finding severity**: any
`fail`-severity finding ⇒ `fail`; otherwise one or more `review`-severity
(`FLAG`) findings ⇒ `flagged-for-review`; otherwise ⇒ `pass`. This is exactly the
`max`-severity rule the Stage 1 `Verdict.build` already computes, so the default
behaviour composes cleanly with the existing empty-detection verdict.

**Config knob — `flag_escalation_count`** (int, default `0` = disabled). Motivates
"one or more review-severity findings ⇒ flagged-for-review" while letting an
operator decide that *many* review-level findings signal a bad enough case to
**fail**: when `flag_escalation_count > 0`, the dominance verdict is
`flagged-for-review` (≥1 `FLAG` finding and **no** `FAIL` finding), **and** the
number of `FLAG`-severity findings is `>= flag_escalation_count`, the layer
appends a synthetic **case-level `FAIL` `Reason`** documenting the escalation
(e.g. `"4 review-level findings meet the escalation threshold (3); verdict
escalated to fail."`), which makes `overall` resolve to `fail`. Escalation fires
**only** on a dominance result of `flagged-for-review` — it never downgrades a
`fail`, never touches a `pass`, and adds no synthetic reason otherwise.

This single documented knob is what makes the policy *config-driven*: the same
finding set maps to `flagged-for-review` or `fail` purely by editing config, with
no code change. Additional policy modes (per-rule severity overrides,
count-per-severity thresholds) are explicitly **out of scope** here and left to
future calibration (Stage 6/7).

### Config shape (read via `config.policy_param`)

A new top-level `verdict` section (sibling of the item-026 `rules` section):

```yaml
schema_version: "0.1"
verdict:
  flag_escalation_count: 0   # optional; default 0 (disabled). When > 0, escalate
                             # a flagged-for-review verdict to fail once this many
                             # review-severity findings are present.
```

An absent `verdict` section leaves the layer at pure severity dominance
(`flag_escalation_count == 0`). The documented default file that ships all
thresholds is **item 035**; here the default lives as the `policy_param` fallback
and the `_DEFAULTS["verdict"] = {}` entry.

### Scope boundary — what this item is **not**

- **Not rule execution.** It consumes an already-produced `list[Finding]`; it
  never calls `run_rules`, instantiates a `Rule`, or reads a feature record.
- **Not pipeline / CLI / report wiring.** Editing `cli.py` to call the rule
  engine and pass the `CaseResult` through, extending the JSON schema
  (`report_schema_v0.json` / `report.py`) with a `findings` block, and rendering
  flags in `human_report.py` are all **item 035**. This item ships the
  aggregation machinery and the `CaseResult` container **unit-tested in
  isolation**; it does **not** touch `cli.py`, `report.py`, `human_report.py`,
  `feature_report.py`, the schema file, or any extractor.
- **Not a new severity model.** It reuses `segqc.verdict.Severity` /
  `Reason` / `Verdict` unchanged; `Finding` already carries a `Severity`, so no
  enum translation is introduced.
- **Not reference-derived or per-rule severity calibration.** Only the single
  documented `flag_escalation_count` knob is added; richer policies are Stage 6/7.

---

## Acceptance Criteria

- [ ] **AC1: `segqc.aggregate` public API exists.** Importing `segqc.aggregate`
      exposes `aggregate_verdict`, `build_case_result`, `CaseResult`, and
      `finding_to_reason` (all named in `__all__`).

- [ ] **AC2: No findings ⇒ `pass`.** `aggregate_verdict([], default_config())`
      returns a `Verdict` with `overall == Severity.PASS` (label `"pass"`),
      `reasons == ()`, and `per_label == {}`.

- [ ] **AC3: Only review-severity findings ⇒ `flagged-for-review`.** For findings
      all of `Severity.FLAG` under `default_config()`, the returned verdict has
      `overall == Severity.FLAG` (label `"flagged-for-review"`).

- [ ] **AC4: Any fail-severity finding ⇒ `fail`.** For findings containing at
      least one `Severity.FAIL` mixed with `Severity.FLAG` findings under
      `default_config()`, `overall == Severity.FAIL` (label `"fail"`).

- [ ] **AC5: All-pass findings ⇒ `pass`.** For findings all of `Severity.PASS`
      under `default_config()`, `overall == Severity.PASS` (dominance lower
      bound; no spurious escalation).

- [ ] **AC6: A case-level finding (empty `labels`) becomes a case-level reason.**
      A `Finding` with `labels == frozenset()` yields exactly one entry in
      `verdict.reasons` (and nothing in `verdict.per_label`) whose `message`
      equals the finding's `reason` and whose `severity` equals the finding's
      `severity`.

- [ ] **AC7: A per-vertebra finding is filed under its offending label.** A
      `Finding` with `labels == frozenset({20})` yields a `Reason` under
      `verdict.per_label[20]` — with `message == finding.reason`,
      `severity == finding.severity`, and `labels == frozenset({20})` — and adds
      **no** case-level reason.

- [ ] **AC8: A multi-label finding is attributed to every offending vertebra.** A
      `Finding` with `labels == frozenset({20, 21})` yields a `Reason` under
      **both** `verdict.per_label[20]` and `verdict.per_label[21]`, and each such
      `Reason` retains the full `labels == frozenset({20, 21})`.

- [ ] **AC9: The finding's human-readable reason is carried verbatim.** For every
      derived `Reason`, `message` equals the source `finding.reason` string
      exactly — no reformatting and no `rule_id` prefix injected.

- [ ] **AC10: `CaseResult` bundles the derived verdict and the full finding
      list.** For a findings list `fs`, `build_case_result(fs, cfg).findings ==
      tuple(fs)` (order preserved; each finding's `rule_id`, `severity`, `reason`,
      and `labels` intact) and `build_case_result(fs, cfg).verdict` equals
      `aggregate_verdict(fs, cfg)`.

- [ ] **AC11: Existing Stage-1 reasons are merged, not discarded.** Given
      `base_reasons=[Reason("empty", Severity.FAIL)]` and only `Severity.FLAG`
      findings, the returned verdict contains **both** the base reason and the
      finding-derived reasons, and `overall == Severity.FAIL` (the base reason
      still governs).

- [ ] **AC12: Base reasons precede finding-derived reasons.** In
      `verdict.reasons`, all supplied `base_reasons` appear first in their input
      order, followed by the finding-derived case-level reasons in findings
      order; for a label present in both `base_per_label` and a finding,
      `verdict.per_label[label]` lists the base entries before the finding
      entries.

- [ ] **AC13: Per-label attribution order is deterministic and label-sorted.**
      For a multi-label finding `labels == frozenset({21, 19, 20})`, the layer
      populates `per_label` buckets in ascending label order (`19`, `20`, `21`),
      and repeated calls yield identical `per_label` structure regardless of
      frozenset iteration order.

- [ ] **AC14: Default policy is pure severity dominance.** Under
      `default_config()` (no `verdict` section), ten `Severity.FLAG` findings
      still yield `overall == Severity.FLAG` — no escalation occurs when
      `flag_escalation_count` is absent/`0`.

- [ ] **AC15: `flag_escalation_count` escalates review → fail at the threshold.**
      With a config carrying `verdict.flag_escalation_count == 3` and exactly
      three `Severity.FLAG` findings and no `FAIL` finding, `overall ==
      Severity.FAIL`, and `verdict.reasons` contains a synthetic case-level
      `Severity.FAIL` reason whose message references the escalation.

- [ ] **AC16: Below the escalation threshold the verdict stays
      `flagged-for-review`.** With `verdict.flag_escalation_count == 3` and only
      two `Severity.FLAG` findings, `overall == Severity.FLAG` and **no**
      synthetic escalation reason is added.

- [ ] **AC17: Escalation never fires on an already-`fail` dominance result.**
      With `verdict.flag_escalation_count == 1` and findings containing one
      `Severity.FAIL` plus one `Severity.FLAG`, `overall == Severity.FAIL` and
      `verdict.reasons` contains **no** synthetic escalation reason (escalation
      applies only to a `flagged-for-review` dominance result).

- [ ] **AC18: The severity mapping is config-driven end-to-end.** The **same**
      finding set (three `Severity.FLAG` findings, no `FAIL`) yields
      `overall == Severity.FLAG` under `default_config()` but
      `overall == Severity.FAIL` under a config whose
      `verdict.flag_escalation_count == 3` — the mapping changes via config
      alone, with no code change.

- [ ] **AC19: `aggregate_verdict` does not mutate its inputs.** After a call, the
      passed `findings` sequence, each `Finding`, the `base_reasons` sequence, and
      the `base_per_label` mapping (and its inner lists) are unchanged
      (deep-equality against a pre-call copy); mutating the caller's
      `base_per_label` **after** the call does not alter the returned verdict.

- [ ] **AC20: Deterministic output.** Two `aggregate_verdict` calls (and two
      `build_case_result` calls) on identical inputs return equal results — equal
      `overall`, equal `reasons` in the same order, equal `per_label`, and (for
      `CaseResult`) an equal `findings` tuple.

- [ ] **AC21: `finding_to_reason` maps fields faithfully.** For a `Finding`
      `f`, `finding_to_reason(f)` returns a `Reason` with `message == f.reason`,
      `severity == f.severity`, and `labels == f.labels`.

- [ ] **AC22: `HeuristicConfig.policy_param` reads the `verdict` section with a
      default.** `default_config().policy_param("flag_escalation_count", 0) == 0`;
      a `HeuristicConfig` (or `load_config` of a YAML) with
      `verdict == {"flag_escalation_count": 5}` returns `5`; an absent key returns
      the supplied default; and `load_config` on a temp YAML with no `verdict`
      section still yields `policy_param("flag_escalation_count", 0) == 0`.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **Findings are consumed from `run_rules`, verbatim.** Pinned interface:
  `segqc.heuristics.finding.Finding` with `rule_id: str`, `severity: Severity`
  (the same `segqc.verdict.Severity` enum), `reason: str`, `labels:
  frozenset[int]`. Because `Finding.severity` **is** a `verdict.Severity`, no
  enum translation is introduced; the aggregator maps finding severity to the
  verdict directly. If that shape diverged, the builder/validator hands back.
- **The "severity policy" is severity dominance plus one documented, config-driven
  escalation knob.** The queue's worked example (any fail ⇒ fail; ≥1 review ⇒
  flagged-for-review; none ⇒ pass) is exactly the `max`-severity rule
  `Verdict.build` already implements, so the **default** verdict equals that
  example and composes with the Stage 1 empty-check verdict unchanged. To make
  the policy genuinely *config-driven* (not a no-op wrapper), a single
  `flag_escalation_count` knob is added: it converts a `flagged-for-review`
  dominance result to `fail` once the count of `FLAG` findings reaches the
  threshold. This is the most material default under clarify=`assume`; the
  validator surfaces it at the queue boundary. Richer, per-rule or per-severity
  policies are left to Stage 6/7 calibration.
- **Escalation is additive and explainable.** It is implemented by appending a
  synthetic **case-level `FAIL` `Reason`** (so `Verdict.build`'s existing `max`
  computation resolves `overall` to `fail`) rather than by post-hoc overwriting
  `Verdict.overall` — keeping a single overall-computation path and giving the
  report a human-readable reason for the escalation. It fires only when the
  dominance verdict is `flagged-for-review` (≥1 `FLAG`, no `FAIL`); it never
  downgrades a `fail`, never upgrades a `pass`, and adds no reason otherwise.
- **Multi-label findings are attributed to every offending vertebra.** A finding
  whose `labels` set has more than one member (e.g. an overlap pair `{20, 21}` or
  a mislabel pair) is filed under **each** label's `per_label` bucket, with the
  `Reason` retaining the **full** offending set — mirroring how per-vertebra
  reasons are surfaced so each involved vertebra shows the flag. Buckets are
  populated in ascending-label order for determinism.
- **Case-level vs per-vertebra split follows the `labels` set.** A finding with an
  **empty** `labels` frozenset (a case-level finding, e.g. item 029's missing-level
  flags) becomes a **case-level** `verdict.reasons` entry; a finding with a
  **non-empty** set becomes a per-vertebra `verdict.per_label` entry. This matches
  the `Reason`/`Verdict` split (`reasons` for case-level, `per_label` for
  per-vertebra) already used by the Stage 1 verdict.
- **The existing Stage 1 verdict is extended, not replaced.** The aggregator
  accepts optional `base_reasons` (case-level) and `base_per_label` (per-vertebra)
  and merges them **before** the finding-derived reasons, so the item-034 layer
  can fold rule findings *into* the empty-check verdict the CLI already builds.
  The pipeline wiring that actually passes those base reasons in is **item 035**;
  here the parameters default to empty so the layer is unit-testable in isolation.
- **The policy is read from a new top-level `verdict` config section** via a new
  `HeuristicConfig.policy_param(key, default)` accessor, added alongside the
  item-026 `rules` accessors — with `_DEFAULTS["verdict"] = {}` and a
  `verdict: Dict[str, Any] = field(default_factory=dict)` field. This mirrors the
  precedent by which item 026 extended `config.py` (adding the `rules` section and
  `min_fragment_voxels`). It is a small, backward-compatible edit: the new field
  has a default, `default_config()` (`HeuristicConfig(**_DEFAULTS)`) and
  `load_config`'s key-by-key merge keep working, and `test_005_adversarial.py`'s
  `_DEFAULTS`-immutability assertion still holds (a new key is added to the dict
  literal, and `load_config` still does not mutate `_DEFAULTS`). The reserved
  `verdict` section is a *policy* holder, not a rule, so it is deliberately kept
  out of the `rules` section (the runner never executes it).
- **`CaseResult` is a minimal frozen dataclass** carrying `verdict: Verdict` and
  `findings: tuple[Finding, ...]`. It is the "case result" the report layer (035)
  reads; `case_id`, `features`, and the JSON/human rendering are the report
  layer's concern and are **not** added here.
- **Immutability of the returned verdict.** `Verdict.build` already copies reasons
  into tuples and per-label lists into tuples, so the returned verdict is
  independent of the caller's `base_per_label`/`base_reasons` after construction
  (AC19). `CaseResult.findings` is stored as a `tuple(...)` copy so the caller's
  original list cannot mutate it.
- **`flag_escalation_count` is coerced via `int(...)`** and treated as disabled
  when `<= 0`. The escalation count is over findings of severity **exactly**
  `FLAG` (review-level), not `PASS` or `FAIL`.

## Implementation Steps

Intended code path — one new module plus a small, backward-compatible `config.py`
extension. No changes to the engine core, rule families, extractors, CLI, report,
or schema.

1. **Extend `src/segqc/config.py` with a `verdict` policy section:**
   - Add `"verdict": {}` to the `_DEFAULTS` dict (documented with a comment: the
     case-level verdict-aggregation policy; keys read via `policy_param`).
   - Add a field `verdict: Dict[str, Any] = field(default_factory=dict)` to
     `HeuristicConfig` (after the `rules` field so keyword/`**_DEFAULTS`
     construction is unaffected).
   - Add an accessor
     `def policy_param(self, key: str, default: Any) -> Any: return
     self.verdict.get(key, default)`, docstringed like `rule_param`.
   - Do **not** change `SUPPORTED_SCHEMA_VERSION`, the `load_config` merge loop
     (it already merges any `_DEFAULTS` key present in the file), or existing
     fields.

2. **Create `src/segqc/aggregate.py`:**
   - Imports: `from dataclasses import dataclass`; `from typing import ...`;
     `from segqc.verdict import Reason, Severity, Verdict`;
     `from segqc.heuristics.finding import Finding` (import the leaf module, not
     the `segqc.heuristics` package, to avoid pulling in every rule registration).
   - `__all__ = ["finding_to_reason", "aggregate_verdict", "build_case_result",
     "CaseResult"]`.
   - Define a stable escalation reason template constant, e.g.
     `_ESCALATION_TAG` / a formatter producing
     `f"{n} review-level findings meet the escalation threshold ({threshold}); "
     f"verdict escalated to fail."`.

3. **Implement `finding_to_reason(finding) -> Reason`:** return
   `Reason(message=finding.reason, severity=finding.severity,
   labels=finding.labels)`.

4. **Implement `aggregate_verdict(findings, config, *, base_reasons=(),
   base_per_label=None) -> Verdict`:**
   - Start `case_reasons = list(base_reasons)` and
     `per_label = {int(k): list(v) for k, v in (base_per_label or {}).items()}`
     (fresh copies — never mutate the caller's containers).
   - Iterate `findings` in order; for each, `r = finding_to_reason(finding)`. If
     `finding.labels` is empty, `case_reasons.append(r)`; else, for `label in
     sorted(finding.labels)`, `per_label.setdefault(label, []).append(r)`.
   - Compute dominance flags over **findings** severities: `has_fail = any(f.severity
     == Severity.FAIL ...)`, `n_flag = sum(1 for f in findings if f.severity ==
     Severity.FLAG)`. Also account for base reasons in the dominance decision only
     insofar as `Verdict.build` will `max` over them; escalation itself is gated on
     the **finding**-driven `flagged-for-review` result: `dominance_is_flag =
     (n_flag > 0) and not has_fail and not any base/finding reason is FAIL`. (Keep
     it simple and testable: escalate only when no `FAIL` reason exists anywhere and
     at least one `FLAG` finding exists.)
   - Read `threshold = int(config.policy_param("flag_escalation_count", 0))`.
     If `threshold > 0` and `dominance_is_flag` and `n_flag >= threshold`, append a
     synthetic **case-level** `Reason(message=<escalation message with n_flag and
     threshold>, severity=Severity.FAIL)` to `case_reasons`.
   - Return `Verdict.build(reasons=case_reasons, per_label=per_label)` (it
     recomputes `overall` as the max severity, so the synthetic `FAIL` reason —
     when present — drives `overall` to `fail`).

5. **Define `CaseResult`** as `@dataclass(frozen=True)` with
   `verdict: Verdict` and `findings: Tuple[Finding, ...]`.

6. **Implement `build_case_result(findings, config, *, base_reasons=(),
   base_per_label=None) -> CaseResult`:** compute
   `verdict = aggregate_verdict(findings, config, base_reasons=base_reasons,
   base_per_label=base_per_label)` and return
   `CaseResult(verdict=verdict, findings=tuple(findings))`.

7. **Do not** edit `cli.py`, `report.py`, `human_report.py`,
   `report_schema_v0.json`, `feature_report.py`, the `heuristics` package, or any
   extractor — all pipeline/report wiring is item 035.

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_034_verdict_aggregation.py`.
- **Finding fixtures:** construct `Finding`s directly
  (`Finding(rule_id="stub", severity=Severity.FLAG, reason="...",
  labels=frozenset({...}))`) — no rule execution or feature records needed. Small
  helpers: one to build a `Finding` from `(severity, labels, reason)`, one to build
  a list of N `Severity.FLAG` findings. Reuse the default convention's integer
  labels where attribution is asserted (`T12 == 19`, `L1 == 20`, `L2 == 21`).
- **Config fixtures:** `default_config()` for the dominance/default path (AC2–AC14);
  an in-process `HeuristicConfig` (or `load_config` on a temp YAML) with
  `verdict={"flag_escalation_count": N}` for the escalation ACs (AC15–AC18); a
  temp YAML with **no** `verdict` section for AC22.
- **Coverage map:** one focused test per AC1–AC22 above.
- **Verdict-mapping tests (AC2–AC5):** empty list ⇒ PASS; all-FLAG ⇒ FLAG;
  mixed-with-FAIL ⇒ FAIL; all-PASS ⇒ PASS — asserting `verdict.overall` and its
  `.label`.
- **Attribution tests (AC6–AC9):** empty-labels finding → `verdict.reasons`;
  single-label → `verdict.per_label[label]` (and empty `verdict.reasons`);
  multi-label → present under both labels with the full `labels` retained;
  message carried verbatim (compare exact string).
- **`CaseResult` / `finding_to_reason` (AC10, AC21):** `.findings == tuple(fs)`
  with rule_id preserved; `.verdict == aggregate_verdict(fs, cfg)`;
  `finding_to_reason` field-by-field equality.
- **Merge/order tests (AC11–AC13):** base FAIL reason forces `fail` alongside FLAG
  findings; base reasons precede finding reasons in `reasons` and in a shared
  `per_label` bucket; multi-label finding buckets in ascending-label order,
  independent of frozenset iteration.
- **Policy tests (AC14–AC18):** default → no escalation; threshold met → FAIL plus
  synthetic escalation reason present; below threshold → FLAG, no escalation reason;
  already-FAIL dominance → no escalation reason appended; the *same* finding set
  flips FLAG→FAIL under a config change alone (config-driven end-to-end).
- **Config-accessor tests (AC22):** `policy_param` default, explicit value, absent
  key, and a `load_config` round-trip on a temp YAML with and without a `verdict`
  section; confirm `default_config()` construction still works after the new field.
- **Adversarial / edge cases:**
  - **Determinism (AC20):** two aggregations return equal `overall`, equal
    `reasons` order, equal `per_label`, and equal `CaseResult.findings`.
  - **Immutability (AC19):** deep-copy `findings` / `base_reasons` /
    `base_per_label` before the call and assert deep equality after; mutate the
    caller's `base_per_label` after the call and assert the returned verdict is
    unchanged (independent copy).
  - **Escalation boundary:** exactly `flag_escalation_count` FLAG findings fires
    (inclusive `>=`); one fewer does not.
  - **`flag_escalation_count == 0` and negative:** disabled — no escalation even
    with many FLAG findings.
  - **Empty per_label / empty reasons round-trip:** the no-findings verdict has
    `reasons == ()` and `per_label == {}`.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 008** — `segqc.verdict` (`Severity`, `Reason`, `Verdict`,
    `Verdict.build`): the target verdict model this layer aggregates into and the
    `max`-severity computation the default policy reuses.
  - **Item 026** — engine core: `Finding` (`segqc.heuristics.finding.Finding`,
    reusing `verdict.Severity`) and `run_rules`, whose `list[Finding]` output is
    this layer's input; the `rules` config precedent this item's `verdict` section
    mirrors.
  - **Items 027–033** — the seven rule families whose findings this layer
    aggregates (bounds, fragmentation, coverage, sequence, border, overlap,
    mislabel). It depends only on their common `Finding` output contract, not on
    any one family's internals.
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`, `_DEFAULTS`): extended here with the `verdict` policy section
    and `policy_param` accessor.
- **Downstream (depend on this item):**
  - **Item 035** — pipeline/report integration: wires `run_rules` →
    `build_case_result` into `cli.py`, passes the Stage 1 empty-check reasons as
    `base_reasons`, extends the JSON schema + `report.py` with a `findings` block,
    renders flags in `human_report.py`, and ships the documented default config
    (including the `verdict` section). It consumes the `CaseResult` and the derived
    `Verdict` produced here.

This item depends only on already-merged interfaces; it is the single join point
between the Stage 4 rule families (027–033) and the Stage 1 verdict/report model.

## Decisions & Trade-offs

To be updated during implementation.
