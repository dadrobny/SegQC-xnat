# Item 030 — Label-Sequence Continuity Rule

> **Created:** 2026-07-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 030
> **Objectives:** G2 (detect §6 failure modes — mode 7, *non-continuous label
> sequence*, e.g. L1 → T12 → L2 → L5), supporting G4 (per-case reasons +
> offending labels)
> **Suggested branch:** `aide/030-label-sequence-continuity-rule`

---

## Description

Implement a **sequence-continuity rule** for the Stage 4 heuristic rule engine
that consumes the pre-computed inter-vertebra relationship record (item 014) to
detect **§6 failure mode 7 — a non-continuous label sequence**: a set of present
vertebrae whose anatomical ordering does **not** progress monotonically along the
spine — reversals and non-anatomical jumps such as `L1 → T12 → L2 → L5`. The rule
plugs into the item-026 engine core exactly like the sibling bounds (item 027),
fragmentation (item 028), and coverage (item 029) rules: it subclasses
`segqc.heuristics.Rule`, registers itself via `register_rule`, reads its severity
from the versioned config through `config.rule_param`, and emits
`segqc.heuristics.Finding` objects through the standard runner. It follows every
convention those siblings pinned — per-case determinism, a fixed output order,
default severity `FLAG` (config-overridable), an unrecognised severity string
raising `ValueError`, and **never mutating** the input record.

### The signal this rule consumes

Item 014 already computes label-sequence continuity and exposes it on the
`relationships` sub-block (serialised by `relationships_to_dict`, item 016):

```
record["relationships"] : {                  # item 014, or None
    "present_levels":      [str, ...],        # canonical head-to-tail order
    "missing_levels":      [str, ...],        # (item 029's domain — not read here)
    "is_continuous":       bool,              # True iff levels progress monotonically
    "out_of_order_labels": [str, ...],        # level names that broke monotonicity,
                                              #   in the sequence order item 014 saw them
    ...
}
record["per_label"] : { "<label_int>": {
    "label":      int,                        # integer segmentation label
    "level_name": str,                        # used to map an offending name -> its label
    ...
} }
```

Per item 014, `is_continuous` is `True` iff the supplied level sequence is
monotonically non-decreasing in `CANONICAL_ORDER` rank, and `out_of_order_labels`
lists the level **names** (in the order item 014 observed them) that broke that
monotonicity. Item 014 guarantees these two fields are coupled:
`out_of_order_labels` is non-empty **iff** `is_continuous` is `False`. This rule
therefore keys its firing decision on `out_of_order_labels` — the field that
directly carries the offending vertebrae the queue asks the rule to identify —
and does not recompute continuity itself.

### What the rule does

Exactly **one** check, emitting at most **one** finding per case:

- When `out_of_order_labels` is non-empty (equivalently `is_continuous is
  False`), emit **one** `Finding` (`rule_id == "sequence"`) whose `reason` begins
  with a stable discontinuity tag and names all offending level names in
  `out_of_order_labels` order, and whose `labels` frozenset carries the **integer
  labels** of those offending vertebrae, resolved from `per_label` by matching
  `level_name`.

Because the offending vertebrae are **present** in the segmentation (they carry
real integer labels — this is a *mis-ordering*, not an *absence*), the finding is
**label-attributed** (non-empty `labels` frozenset), in deliberate contrast to
item 029's *missing-level* findings which are case-level (`labels ==
frozenset()`) because an absent vertebra has no integer label. The offending
level names are additionally carried in the `reason` string for a human-readable
explanation. Targets **§6 failure mode 7**.

### Scope boundary — what this item is **not**

- **Not missing-level / coverage detection.** Absences within a monotonic span
  (`relationships.missing_levels`) are **§6 mode 5 / item 029** (already merged).
  Although the queue one-liner lists "gaps, reversals, or non-anatomical jumps",
  the item-014 data model routes pure **gaps** to `missing_levels` (owned by
  item 029) and **ordering violations** to `out_of_order_labels` (owned here).
  This rule reads **only** the ordering fields and never `missing_levels`, so
  the two rules never double-flag the same phenomenon. (See Assumptions.)
- **Not mislabel / misalignment via geometry.** Detecting a vertebra whose
  *centroid* is a spatial outlier from the fitted spinal curve, or a swapped
  pair inconsistent with neighbour spacing, is **§6 modes 1 & 4 / item 033**;
  this rule uses only the already-computed continuity flag, not centroids,
  spline offsets, or spacing metrics.
- **Not verdict aggregation.** Combining findings into a `pass`/`flag`/`fail`
  verdict is **item 034**.
- **Not the shipped default config file.** Item 035 ships the documented YAML;
  here the defaults live as `rule_param` fallbacks.
- Does **not** recompute continuity, relationships, or centroids — it only
  *consumes* the `relationships` sub-block (item 014) and per-label `level_name`
  already assembled by `build_features_block` (item 016). It does not touch the
  item-026 engine core, `config.py`, `verdict.py`, or any extractor.

### Config shape (read via `config.rule_param`)

```yaml
rules:
  sequence:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review
```

Continuity is a **structural / binary** property, so the rule ships **no**
numeric thresholds — `severity` is its only parameter. An absent `rules.sequence`
section leaves the rule fully operational: it fires on any non-continuous record
at the default `FLAG` severity.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "sequence"`.**
      Importing `segqc.heuristics` makes a `SequenceRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("sequence")`
      returns the registered instance and `sequence` appears in `iter_rules()`.

- [ ] **AC2: No finding for an in-order (continuous) fixture.**
      For a record whose `relationships.out_of_order_labels == []` and
      `relationships.is_continuous == True`, under `default_config()`, `evaluate`
      returns `[]` — no sequence finding.

- [ ] **AC3: A finding fires for a single reversal.**
      Given a record with `relationships.out_of_order_labels == ["T12"]` and
      `is_continuous == False`, the rule emits exactly **one** `Finding` with
      `rule_id == "sequence"`, whose `reason` begins with the discontinuity tag
      and names `T12`.

- [ ] **AC4: The offending vertebra is attributed by its integer label.**
      For the AC3 record, where the offending level `T12` is present in
      `per_label` as integer label `19`, the emitted finding's `labels ==
      frozenset({19})` (label-attributed, **not** an empty case-level frozenset).

- [ ] **AC5: Multiple out-of-order labels are reported in one finding.**
      Given `relationships.out_of_order_labels == ["T12", "L1"]` (in that
      sequence order) with both levels present in `per_label`, the rule emits a
      **single** `sequence` finding whose `reason` names both `T12` and `L1` in
      `out_of_order_labels` order, and whose `labels` equals the frozenset of
      both offending integer labels — not one finding per offender.

- [ ] **AC6: The queue's canonical non-anatomical jump is flagged.**
      For a record modelling `L1 → T12 → L2 → L5` where item 014 reports
      `out_of_order_labels == ["T12"]` and `is_continuous == False`, the rule
      emits exactly one `sequence` finding naming `T12` and carrying `T12`'s
      integer label in `labels`.

- [ ] **AC7: No finding for a single-present-level record.**
      For a record with one present level, `out_of_order_labels == []` and
      `is_continuous == True`, `evaluate` returns `[]` — no finding, no error.

- [ ] **AC8: No finding for an empty / no-present-levels record.**
      For a record with `present_levels == []` and `out_of_order_labels == []`,
      `evaluate` returns `[]` — no finding, no error.

- [ ] **AC9: The rule tolerates an absent / `None` / malformed relationship
      record.** `evaluate` returns `[]` and raises nothing when
      `record["relationships"]` is `None` or absent, and when `out_of_order_labels`
      / `is_continuous` keys are absent (treated as continuous), and when
      `per_label` is empty or absent.

- [ ] **AC10: An offending name with no `per_label` entry is still reported,
      without its integer label.** Given `out_of_order_labels == ["T12"]` where no
      `per_label` entry has `level_name == "T12"`, the rule still emits **one**
      `sequence` finding naming `T12` in its `reason`, with `T12` simply omitted
      from `labels` (a possibly-empty `labels` frozenset) — no crash.

- [ ] **AC11: Default severity is `FLAG`, and severity is config-driven.**
      With no `severity` param, an emitted finding has `severity ==
      Severity.FLAG`. With `rules.sequence.params.severity` set to `fail`, the
      emitted finding has `severity == Severity.FAIL`.

- [ ] **AC12: An unrecognised severity string raises `ValueError`.**
      If `rules.sequence.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, `"fail"`), `evaluate` raises
      `ValueError` immediately (before any per-record processing).

- [ ] **AC13: The rule is deterministic with a fixed output order.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return
      equal finding lists in the same order. Within the single emitted finding,
      offending level names appear in `reason` in `out_of_order_labels` order.

- [ ] **AC14: The rule does not mutate the input record.**
      Calling `evaluate(record, config)` leaves `record` (including the nested
      `relationships`, `per_label`, and every list) unchanged — verified by deep
      equality against a pre-call copy.

## Assumptions  <!-- MANDATORY -->

- **Continuity is read from `relationships.is_continuous` /
  `out_of_order_labels` (item 014), not re-derived.** Pinned interface (via
  `relationships_to_dict`, item 016): the `relationships` sub-dict exposes
  `is_continuous: bool` and `out_of_order_labels: list[str]` (canonical level
  **names**, in the sequence order item 014 observed). If that shape diverged,
  the builder/validator hands back.
- **Item 014's coupling is relied upon:** `out_of_order_labels` is non-empty
  **iff** `is_continuous is False`. The rule keys its firing decision on
  `out_of_order_labels` being non-empty (the field that carries the offending
  labels the queue requires). Should a malformed record ever set
  `is_continuous == False` with an **empty** `out_of_order_labels`, the rule
  emits **no** finding (there is no concrete offender to name/attribute) rather
  than a contentless finding — the conservative choice.
- **Offending findings are label-attributed (non-empty `labels`).** Out-of-order
  vertebrae are *present* in the segmentation and carry integer labels, so unlike
  item 029's *absent*-level findings (case-level, empty frozenset) this rule
  attaches the offenders' integer labels. Each offending level **name** is mapped
  to its integer label by scanning `record["per_label"].values()` for a matching
  `level_name` and reading that entry's `label` (per 029's pinned lookup
  convention — `per_label` is keyed by integer label, not level name, so a direct
  key lookup is not possible). An offending name with **no** matching entry is
  still named in the `reason` but omitted from `labels` (conservative — surfaces
  the discontinuity rather than hiding it on incomplete data).
- **Reason lists offending names in `out_of_order_labels` order**, not canonical
  order, because that reflects the sequence order in which item 014 observed the
  discontinuity and is already deterministic. The `labels` frozenset is
  order-independent.
- **Scope split vs item 029.** This rule reads **only** the ordering fields
  (`is_continuous` / `out_of_order_labels`) and never `missing_levels`. Pure
  missing-level *gaps* remain item 029's domain (§6 mode 5); this rule owns
  ordering *reversals / non-anatomical jumps* (§6 mode 7). This prevents the two
  rules double-flagging the same case for overlapping reasons.
- **Default severity is `flagged-for-review` (`Severity.FLAG`)**, matching the
  sibling rules (items 027–029); overridable via `severity`, with an
  unrecognised string raising `ValueError`. Continuity is binary/structural, so
  the rule ships **no** numeric thresholds.
- **The rule never mutates the input record** — it only reads and builds fresh
  `Finding`s.

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/sequence.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, and `Severity` from `segqc.verdict`. (No
     `CANONICAL_ORDER` needed — the rule preserves item 014's ordering.)
   - Define the reason-tag module constant so it is stable and testable, e.g.
     `_DISCONTINUITY_TAG = "Non-continuous label sequence:"`.
   - Reuse the sibling `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}`
     lookup and a `_severity_from_param(label) -> Severity` helper that raises
     `ValueError` on an unrecognised label (mirror `bounds.py` /
     `coverage.py`).
   - Add a small helper `_label_for_level(per_label, level_name) -> Optional[int]`
     that scans `per_label.values()` for an entry whose `level_name` matches and
     returns `int(entry["label"])`, else `None` (mirror `coverage.py`'s
     `_find_entry_by_level_name`).

2. **Implement `class SequenceRule(Rule)`** with `rule_id = "sequence"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read severity once via
     `_severity_from_param(config.rule_param("sequence", "severity",
     default="flagged-for-review"))` (raises on a bad string before any
     processing — AC12).
   - Read `rel = record.get("relationships")`; if `rel` is not a mapping, return
     `[]` (AC9). Read `out_of_order = list(rel.get("out_of_order_labels") or [])`.
   - If `out_of_order` is empty, return `[]` (AC2, AC7, AC8, and the malformed
     `is_continuous is False` / empty-list case in Assumptions).
   - Otherwise map each offending name to an integer label via
     `_label_for_level(record.get("per_label") or {}, name)`, collecting the
     non-`None` results into a `frozenset` (AC4, AC5, AC10). Preserve
     `out_of_order` order for the names in the reason (AC13).
   - Append **one** `Finding(rule_id="sequence", severity=severity,
     reason=f"{_DISCONTINUITY_TAG} " + names + " out of anatomical order.",
     labels=<frozenset of mapped ints>)` and return `[finding]`.
   - **Do not mutate** `record`, `rel`, or `per_label` (AC14): only read, and
     build fresh copies / `Finding`s.

3. **Register the rule:** decorate `SequenceRule` with `@register_rule`.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import sequence  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds`,
   `fragmentation`, and `coverage` imports, so importing `segqc.heuristics` makes
   the `sequence` rule discoverable via the registry/runner.

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `relationships.py`, or `feature_report.py`. All parameters flow through the
   existing `rule_enabled` / `rule_param` accessors.

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_030_sequence_continuity.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering `SequenceRule`
  does not leak across tests and re-registration does not raise a duplicate-id
  error (mirror `tests/test_029_coverage_missing_levels.py`).
- **Record fixtures:** build minimal per-case records by hand matching the
  `build_features_block` shape — a `relationships` sub-dict (`present_levels`,
  `is_continuous`, `out_of_order_labels`) plus a `per_label` map carrying just
  `label` and `level_name` — rather than running the full extractor stack (the
  rule only reads those fields). Provide a small helper to assemble a record from
  `(present_levels, out_of_order_labels, is_continuous, label_entries)`. Use the
  default convention's integer labels where attribution is asserted (e.g. `T12 ==
  19`, `L1 == 20`, `L2 == 21`, `L5 == 24`). Fixtures:
  - **in-order**, `out_of_order_labels == []`, `is_continuous == True` — AC2;
  - **single reversal**, `out_of_order_labels == ["T12"]`,
    `is_continuous == False`, `per_label` has T12 as label 19 — AC3, AC4;
  - **two offenders**, `out_of_order_labels == ["T12", "L1"]` — AC5;
  - **queue example** `L1 → T12 → L2 → L5`, present levels for all four,
    `out_of_order_labels == ["T12"]` — AC6;
  - **single present level** — AC7;
  - **empty** (`present_levels == []`) — AC8;
  - **degenerate records** — `relationships` `None` / absent,
    `out_of_order_labels` / `is_continuous` absent, empty `per_label` — AC9;
  - **unmappable offender** — `out_of_order_labels == ["T12"]` but no `per_label`
    entry named `T12` — AC10.
- **Config fixtures:** `default_config()` for the defaults path (AC2, AC11); an
  in-process `HeuristicConfig` (or `load_config` on a temp YAML) with a
  `severity` override (AC11) and an invalid `severity` string (AC12).
- **Coverage map:** one focused test per AC1–AC14 above.
- **Adversarial / edge cases:**
  - A record with `is_continuous == False` but an **empty**
    `out_of_order_labels` emits no finding (malformed-record guard).
  - `out_of_order_labels` containing a name that maps to no `per_label` entry is
    reported in the reason with an empty/partial `labels` frozenset (AC10).
  - Determinism: two `run_rules` calls return equal lists; the offending names
    appear in `out_of_order_labels` order in the reason (AC13).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC14).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027 / 028 / 029** — sibling rule families, the canonical pattern this
    item mirrors (registration, `_severity_from_param`, reason tag, deterministic
    ordering, no record mutation, name→label lookup).
  - **Item 014** — inter-vertebra relationships; supplies `is_continuous` and
    `out_of_order_labels` (the continuity signal this rule consumes) via
    `relationships_to_dict` (item 016).
  - **Item 016** — `build_features_block` / `relationships_to_dict`; assembles
    the per-case record shape (`relationships`, `per_label` with `label` +
    `level_name`) the rule reads.
  - **Item 004** — label convention; defines the integer labels the offending
    level names resolve to (`per_label` carries them, so the rule reads them from
    the record rather than importing the convention).
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.sequence` config and the
    §6-mode-7 end-to-end test.

This item is **parallel-independent** of the other rule families (027–029,
031–033); they share only the already-merged item-026 interface.

## Decisions & Trade-offs

Implementation confirmed the spec's initial design decisions below without
deviation. `src/segqc/heuristics/sequence.py` implements `SequenceRule`
mirroring `coverage.py`'s structure (`_severity_from_param`,
`_label_for_level` mirrors `_find_entry_by_level_name`) and is wired into
`src/segqc/heuristics/__init__.py` alongside `bounds`/`fragmentation`/
`coverage`. No changes were needed to `config.py`, `rule.py`, `runner.py`,
`finding.py`, `relationships.py`, or `feature_report.py`.

Initial design decisions carried from this spec (confirm or revise during
implementation):

- **Fire on `out_of_order_labels` non-empty, not on `is_continuous is False`
  directly.** The two are equivalent for well-formed item-014 records, but the
  offender list is what the finding must *name and attribute*, so keying on it
  makes the "no offender ⇒ no finding" behaviour unambiguous and testable, and
  gracefully handles a malformed `is_continuous == False` / empty-list record.
- **Findings are label-attributed (non-empty `labels`), unlike item 029.**
  Out-of-order vertebrae are present in the segmentation, so attaching their
  integer labels gives the item-034 aggregator meaningful per-vertebra offenders
  — the deliberate contrast with item 029's case-level missing-level findings.
- **One finding per case, listing all offenders**, rather than one finding per
  offending label — a discontinuity is a single sequence-level phenomenon; the
  reason names every offender and the `labels` frozenset carries all of them.
- **Scope split vs item 029** (gaps → 029, ordering → 030) keeps §6 modes 5 and 7
  independently testable and prevents double-flagging.
- **No numeric thresholds.** Continuity is binary; `severity` is the only param.
