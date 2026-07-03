# Item 029 — Incomplete-Coverage / Missing-Level Rules

> **Created:** 2026-07-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 029
> **Objectives:** G2 (detect §6 failure modes — mode 5, *not all vertebrae
> segmented*), supporting G4 (per-case reasons + offending levels) and Use
> Case C (dataset curation by vertebra count / span)
> **Suggested branch:** `aide/029-incomplete-coverage-missing-level-rules`

---

## Description

Implement a **coverage rule family** for the Stage 4 heuristic rule engine that
checks the set of present vertebra levels against the **expected ordered level
sequence** (the label convention, item 004) to detect **§6 failure mode 5 — not
all vertebrae in the image are segmented**. The rule plugs into the item-026
engine core exactly like the sibling bounds (item 027) and fragmentation
(item 028) rules: it subclasses `segqc.heuristics.Rule`, registers itself via
`register_rule`, reads its parameters from the versioned config through
`config.rule_param`, and emits `segqc.heuristics.Finding` objects through the
standard runner. It follows every convention those siblings pinned — per-case
determinism, a fixed output order, default severity `FLAG` (config-overridable),
an unrecognised severity string raising `ValueError`, and **never mutating** the
input record.

The rule performs up to **three independent checks**, distinguished (as in
item 028) by a stable tag at the start of each finding's `reason` string:

1. **Missing interior level(s)** *(always active)* — consumes the already-computed
   `relationships.missing_levels` (item 014): the anatomical levels absent from
   **within** the observed span `[topmost_present .. bottommost_present]`. Any
   such gap means a vertebra that is bracketed above **and** below by segmented
   vertebrae was itself not segmented. Emits **one** finding per case naming all
   the missing interior levels, in canonical head-to-tail order.

2. **Incomplete coverage vs an expected span** *(active only when configured)* —
   when the operator configures `expected_levels` (an explicit list of canonical
   level names the case is expected to contain), the rule flags expected levels
   that are absent and lie **beyond** the present span's ends. This check is
   **border-aware** (item 011 `touches_superior` / `touches_inferior` flags): an
   expected level that lies beyond a span end which is **truncated by the image
   field-of-view (FOV)** is *not* flagged, because the image simply does not
   cover that region — it is a coverage limitation of the scan, not a
   segmentation failure.

3. **Below an expected count** *(active only when configured)* — when the
   operator configures `expected_count` (a hard minimum number of recognised
   vertebrae, e.g. for Use-Case-C dataset curation), the rule flags a case whose
   number of recognised present levels is below that minimum.

For each fired check the rule emits a `Finding` with a human-readable `reason`
naming the missing levels / counts, at a configurable `severity` (default
`flagged-for-review`). Missing-level findings are **case-level**: they carry an
**empty** `labels` frozenset (there is no integer segmentation label for an
*absent* vertebra — the `Finding` model explicitly supports empty `labels` for
case-level findings), and the offending level names are carried in the `reason`
string. Targets **§6 failure mode 5**.

### The border-awareness principle (the crux of this item)

The queue asks the rule to *"distinguish a genuinely missing interior level from
an image that simply does not cover that region (border-aware …)"*. The design
resolves this cleanly by **where** each check applies border-awareness:

- An **interior** missing level (check 1) is bracketed by a present, segmented
  vertebra **both above and below it**, so the FOV demonstrably covers that
  region. An interior gap is therefore **always a genuine failure** and is
  **never** suppressed by border flags. (By construction `missing_levels`
  contains only levels strictly inside `[min_present .. max_present]`, so this
  check can never fire at a truncated span end.)
- Only the **span ends** can be FOV-truncated. The **expected-span** check
  (check 2) is where border-awareness does its work: a missing expected level
  *beyond* a span end whose vertebra touches the corresponding image face is
  suppressed.

Anatomy → image-face mapping (from item 011 `geometry.py`): the spine's
**superior** (head) end maps to `touches_superior`; the **inferior** (tail) end
maps to `touches_inferior`. In `CANONICAL_ORDER`, `present_levels[0]` is the most
superior present level and `present_levels[-1]` the most inferior. Hence:

- `present_levels[0].touches_superior` ⇒ superior FOV truncation ⇒ suppress
  expected levels ranked **above** (more superior than) `present_levels[0]`.
- `present_levels[-1].touches_inferior` ⇒ inferior FOV truncation ⇒ suppress
  expected levels ranked **below** (more inferior than) `present_levels[-1]`.

### What this item is **not**

- **Not sequence-continuity / ordering** — gaps handled here are *absences within
  a monotonically-ordered span*. Reversals, non-anatomical jumps, and
  out-of-order labels (`relationships.is_continuous` / `out_of_order_labels`) are
  **§6 mode 7 / item 030**.
- **Not empty / near-empty detection** — a zero-/near-empty segmentation is
  Stage 1 / item 007. When no relationship record exists (fewer than the minimum
  needed to define a span), this rule returns no findings rather than duplicating
  empty detection.
- **Not reference-derived expectations** — the rule ships **no** hand-set numeric
  thresholds. Both configurable checks (`expected_levels`, `expected_count`) are
  **disabled by default**; the always-on interior check needs no threshold.
  Reference-derived expected spans/counts are Stage 6.
- **Not verdict aggregation** — combining findings into a `pass`/`flag`/`fail`
  verdict is **item 034**.
- **Not the shipped default config file** — item 035 ships the documented YAML;
  here the disabled-by-default behaviour lives as `rule_param` fallbacks.
- Does **not** recompute geometry, components, or relationships — it only
  *consumes* the `relationships` sub-block (item 014) and per-label
  `geometry.touches_*` flags (item 011) already assembled by
  `build_features_block` (item 016). It does not touch the item-026 engine core,
  `config.py`, `verdict.py`, or any extractor.

### The feature record this rule consumes

The per-case record passed to `evaluate(record, config)` is the
`build_features_block` dict (item 016). This rule reads only:

```
record["relationships"] : {                 # item 014, or None
    "present_levels":  [str, ...],           # canonical head-to-tail order
    "missing_levels":  [str, ...],           # absent levels WITHIN the span, canonical order
    "is_continuous":   bool,                 # (not read here — item 030)
    "out_of_order_labels": [str, ...],       # (not read here — item 030)
    ...
}
record["per_label"] : { "<label_int>": {
    "label": int,
    "level_name": str,                       # used to locate a span-end level's geometry
    "geometry": {
        "touches_superior": bool,            # item 011 — superior (head) image face
        "touches_inferior": bool,            # item 011 — inferior (tail) image face
        ...
    },
    ...
} }
```

`relationships.missing_levels` is **already** exactly *"levels absent within the
observed span `[min .. max]`, in canonical order"* (item 014), so check 1 reads
it directly and does not re-derive it.

### Config shape (read via `config.rule_param`)

```yaml
rules:
  coverage:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review
      expected_levels: []               # optional list of canonical level names;
                                        #   [] / absent => span check disabled
      expected_count: null              # optional int hard minimum;
                                        #   null / absent => count check disabled
      border_aware: true                # optional; default true. When true the
                                        #   span check suppresses expected levels
                                        #   beyond an FOV-truncated span end.
```

Every param is read with a built-in fallback via
`config.rule_param("coverage", "<key>", default=<DEFAULT>)`, so an absent
`rules.coverage` section leaves the rule fully operational: the interior check
runs; the two opt-in checks stay disabled.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "coverage"`.**
      Importing `segqc.heuristics` makes a `CoverageRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("coverage")`
      returns the registered instance and `coverage` appears in `iter_rules()`.

- [ ] **AC2: No finding for a contiguous fixture spanning its range.**
      For a record whose `relationships.missing_levels == []` (present levels are
      contiguous over their span) under `default_config()`, `evaluate` returns
      `[]` — no coverage finding of any kind.

- [ ] **AC3: A missing-interior-level finding fires when an interior level is
      removed.** Given a record with `relationships.missing_levels == ["L3"]`
      (an interior level absent between present neighbours), the rule emits
      exactly one `Finding` with `rule_id == "coverage"`, a `reason` beginning
      with the missing-interior tag and naming `L3`, and `labels == frozenset()`
      (case-level attribution).

- [ ] **AC4: All missing interior levels are named in one finding, in canonical
      order.** Given `relationships.missing_levels == ["T12", "L2"]`, the rule
      emits a **single** missing-interior finding whose `reason` names both
      `T12` and `L2` in canonical head-to-tail order (`T12` before `L2`) — not
      one finding per level.

- [ ] **AC5: No spurious finding when the range is simply truncated at the FOV
      edge.** For a record whose present levels are contiguous (no interior gap)
      but whose bottommost present level touches the inferior image border
      (`geometry.touches_inferior == True`), under `default_config()` `evaluate`
      returns `[]` — an FOV-truncated span produces no interior gap and the
      opt-in checks are disabled by default.

- [ ] **AC6: The expected-span check is config-driven.** With
      `rules.coverage.params.expected_levels` set to a canonical sequence that
      extends **beyond** the present span, where the adjacent span-end vertebra
      does **not** touch the image border, the rule emits an incomplete-span
      `Finding` (`rule_id == "coverage"`) whose `reason` begins with the
      incomplete-span tag and names the absent expected level(s); with
      `expected_levels` absent (default), the same record emits no span finding.

- [ ] **AC7: The expected-span check is border-aware (suppresses FOV-truncated
      ends).** Given the same `expected_levels` extending beyond the present span
      as in AC6, but where the relevant span-end vertebra **does** touch the
      corresponding image border (superior end → `touches_superior`, inferior end
      → `touches_inferior`), and `border_aware` at its default (`True`), the
      expected levels lying beyond that truncated end are **not** flagged — no
      incomplete-span finding for those levels.

- [ ] **AC8: The expected-span check still fires when the span end is not at the
      border.** Identical `expected_levels` to AC7 but with the span-end vertebra
      **not** touching the image border: the absent expected level(s) beyond that
      end **are** flagged with an incomplete-span finding — confirming the
      suppression in AC7 is driven by the border flag, not an unconditional skip.

- [ ] **AC9: The expected-count check is config-driven and fires below the
      minimum.** With `rules.coverage.params.expected_count` set above the number
      of recognised present levels, the rule emits a count-shortfall `Finding`
      (`rule_id == "coverage"`, `labels == frozenset()`) whose `reason` begins
      with the count tag and reports the present count and the expected minimum.

- [ ] **AC10: The expected-count check does not fire when the minimum is met.**
      With `expected_count` set at or below the number of recognised present
      levels, the rule emits no count-shortfall finding.

- [ ] **AC11: Both opt-in checks are disabled by default.** Under
      `default_config()` (no `expected_levels`, no `expected_count`), the rule
      never emits an incomplete-span or a count-shortfall finding — only the
      always-on interior check can fire.

- [ ] **AC12: Default severity is `FLAG`, and severity is config-driven.** With
      no `severity` param, every emitted finding has `severity == Severity.FLAG`.
      With `rules.coverage.params.severity` set to `fail`, emitted findings have
      `severity == Severity.FAIL`.

- [ ] **AC13: An unrecognised severity string raises `ValueError`.** If
      `rules.coverage.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, `"fail"`), `evaluate` raises
      `ValueError` immediately (before any per-record processing).

- [ ] **AC14: The rule is deterministic with a fixed output order.** Two
      successive `run_rules(record, cfg)` calls on the same inputs return equal
      finding lists in the same order. When multiple checks fire for one record,
      the findings appear in the fixed order: **missing-interior**, then
      **incomplete-span**, then **count-shortfall**; level names within any
      finding's `reason` are listed in canonical order.

- [ ] **AC15: The rule tolerates an absent / `None` / empty relationship
      record.** `evaluate` returns `[]` and raises nothing when
      `record["relationships"]` is `None` or absent, when `present_levels` /
      `missing_levels` are absent, and when `per_label` is empty or absent.

- [ ] **AC16: The rule does not mutate the input record.** Calling
      `evaluate(record, config)` leaves `record` (including the nested
      `relationships`, `per_label`, and `geometry` dicts and every list)
      unchanged — verified by deep equality against a pre-call copy.

## Assumptions

- **Interior missing levels are read from `relationships.missing_levels`
  (item 014), not re-derived.** Item 014 already defines `missing_levels` as
  *"levels absent within the observed span `[min_present .. max_present]`, in
  canonical order"* — precisely check 1's input. Pinned interface: the
  `relationships` sub-dict exposes `present_levels: list[str]` and
  `missing_levels: list[str]` (canonical names, canonical order), as emitted by
  `relationships_to_dict` (item 016). If that shape diverged, the builder/
  validator hands back.
- **Border flags come from per-label `geometry.touches_superior` /
  `touches_inferior` (item 011).** The anatomy→face mapping is item 011's:
  superior (head) = `touches_superior`, inferior (tail) = `touches_inferior`;
  `present_levels[0]` is most superior, `present_levels[-1]` most inferior. The
  rule locates a span-end level's geometry by matching `level_name` in
  `record["per_label"]`. If a span-end level's geometry or border flag is absent
  from `per_label`, the rule treats it as **not** touching the border (does not
  suppress) — the conservative choice, surfacing a possible miss rather than
  hiding it.
- **Missing-level findings are case-level (`labels == frozenset()`).** An absent
  vertebra has no integer label in the segmentation map, and the `Finding` model
  documents the empty frozenset as the case-level attribution; offending level
  **names** are carried in the `reason` string. (Alternative — synthesising
  would-be integer labels via the convention — was rejected as misleading to the
  item-034 aggregator, which treats `labels` as *present* offending vertebrae.)
- **`expected_levels` are matched by canonical name; non-canonical / unknown
  names in the configured list are ignored** (not crashed), and the effective
  expected set is ordered by `CANONICAL_ORDER` for deterministic reason text.
- **`expected_count` counts recognised present levels** (`len(present_levels)`),
  i.e. levels in `CANONICAL_ORDER`; it is a **raw** hard minimum and is **not**
  border-aware — a scan that shows too few vertebrae because of a limited FOV is
  a legitimate reject for Use-Case-C curation. Border-awareness applies only to
  the `expected_levels` span check. This split is the item's key design decision
  (see Decisions & Trade-offs).
- **Default severity is `flagged-for-review` (`Severity.FLAG`)**, matching the
  sibling rules (items 027, 028); overridable via `severity`, with an
  unrecognised string raising `ValueError`.

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/coverage.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, `Severity` from `segqc.verdict`, and
     `CANONICAL_ORDER` from `segqc.labels`.
   - Build the canonical-rank map once at import
     (`{name: i for i, name in enumerate(CANONICAL_ORDER)}`) for O(1) ordering
     and "beyond a span end" comparisons.
   - Define the three **reason-tag** module constants so they are stable and
     testable, e.g. `_MISSING_INTERIOR_TAG = "Missing interior level(s):"`,
     `_INCOMPLETE_SPAN_TAG = "Incomplete coverage (span):"`,
     `_COUNT_SHORTFALL_TAG = "Below expected count:"`.
   - Define `DEFAULT_BORDER_AWARE = True`. Ship **no** numeric thresholds
     (coverage is structural; the opt-in checks default to disabled).
   - Reuse the sibling `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}`
     lookup and a `_severity_from_param(label) -> Severity` helper that raises
     `ValueError` on an unrecognised label (mirror `bounds.py` / `fragmentation.py`).

2. **Implement `class CoverageRule(Rule)`** with `rule_id = "coverage"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read severity once via
     `_severity_from_param(config.rule_param("coverage", "severity",
     default="flagged-for-review"))` (raises on a bad string before any
     processing — AC13).
   - Read the opt-in params once: `expected_levels =
     config.rule_param("coverage", "expected_levels", default=[])`,
     `expected_count = config.rule_param("coverage", "expected_count",
     default=None)`, `border_aware = config.rule_param("coverage",
     "border_aware", default=DEFAULT_BORDER_AWARE)`.
   - Read `rel = record.get("relationships")`; if `rel` is not a mapping, return
     `[]` (AC15). Read `present_levels = rel.get("present_levels") or []` and
     `missing_levels = rel.get("missing_levels") or []`.
   - Build the findings list in the **fixed order** below (AC14).
   - **Check 1 — missing interior levels (always):** if `missing_levels` is
     non-empty, sort its entries by canonical rank and append **one** finding
     tagged `_MISSING_INTERIOR_TAG`, naming all of them, `labels=frozenset()`
     (AC3, AC4). These are never suppressed by border flags (interior by
     construction).
   - **Check 2 — expected span (opt-in):** only when `expected_levels` is
     non-empty and `present_levels` is non-empty. Restrict `expected_levels` to
     canonical names, order by rank. Compute the absent expected levels
     (`name not in set(present_levels)`). Partition them into *interior* (rank
     strictly between the present span ends — already reported by check 1, so
     excluded here to avoid double-flagging) and *beyond-a-span-end*. For each
     beyond-end absent level, apply border-awareness when `border_aware`:
     - level ranked above `present_levels[0]` and that top level's
       `touches_superior` is `True` ⇒ **suppress**;
     - level ranked below `present_levels[-1]` and that bottom level's
       `touches_inferior` is `True` ⇒ **suppress**.
     Locate each span-end level's border flags by matching its `level_name` in
     `record.get("per_label", {})`; a missing entry/flag ⇒ treat as not touching
     (do not suppress). If any beyond-end absent expected levels survive
     suppression, append **one** finding tagged `_INCOMPLETE_SPAN_TAG` naming
     them in canonical order, `labels=frozenset()` (AC6, AC7, AC8).
   - **Check 3 — expected count (opt-in):** only when `expected_count` is not
     `None`; if `len(present_levels) < int(expected_count)`, append **one**
     finding tagged `_COUNT_SHORTFALL_TAG` reporting present vs expected count,
     `labels=frozenset()` (AC9, AC10). Not border-aware.
   - Every finding uses `severity=severity` (AC12). Return the aggregated list
     (empty when nothing fires — AC2, AC5, AC11, AC15).
   - **Do not mutate** `record`, `rel`, `per_label`, or any list read from them
     (AC16): only read, and build fresh sorted copies / `Finding`s.

3. **Register the rule:** decorate `CoverageRule` with `@register_rule`.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import coverage  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds` and
   `fragmentation` imports, so importing `segqc.heuristics` makes the `coverage`
   rule discoverable via the registry/runner.

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `relationships.py`, `geometry.py`, or `feature_report.py`. All parameters flow
   through the existing `rule_enabled` / `rule_param` accessors.

## Testing Strategy

- **Framework:** `pytest`. Test module:
  `tests/test_029_coverage_missing_levels.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering `CoverageRule`
  does not leak across tests and re-registration does not raise a duplicate-id
  error.
- **Record fixtures:** build minimal per-case records by hand matching the
  `build_features_block` shape — a `relationships` sub-dict (`present_levels`,
  `missing_levels`) plus a `per_label` map carrying just `level_name` and a
  `geometry` dict with `touches_superior` / `touches_inferior` — rather than
  running the full extractor stack (the rule only reads those fields). Provide a
  small helper to assemble such a record from `(present_levels, missing_levels,
  border_flags)`. Fixtures:
  - **contiguous span**, `missing_levels == []`, no border touch — AC2;
  - **one interior gap**, `missing_levels == ["L3"]` — AC3;
  - **two interior gaps**, `missing_levels == ["T12", "L2"]` — AC4 (canonical
    order in reason);
  - **contiguous but FOV-truncated**, `missing_levels == []`, bottommost present
    level `touches_inferior == True` — AC5;
  - **expected span beyond a non-border end** (e.g. present `L1..L3`, expected
    `L1..L5`, `L3` not touching inferior border) — AC6, AC8;
  - **expected span beyond a border-truncated end** (present `L1..L3`, expected
    `L1..L5`, `L3.touches_inferior == True`) — AC7;
  - **superior-end truncation** variant (present `T2..T5`, expected `T1..T5`,
    `T2.touches_superior == True`) to exercise the superior mapping — AC7;
  - **count fixtures** — a record with fewer recognised present levels than
    `expected_count` (AC9) and one with the count met (AC10);
  - **degenerate records** — `relationships` `None` / absent, `present_levels` /
    `missing_levels` absent, empty `per_label` — AC15.
- **Config fixtures:** `default_config()` for the defaults path (AC2, AC5, AC11);
  in-process `HeuristicConfig` (or `load_config` on a temp YAML) with
  `rules.coverage.params.expected_levels` (AC6–AC8), `expected_count` (AC9,
  AC10), `border_aware: false` to confirm the toggle un-suppresses a truncated
  end, a `severity` override (AC12), and an invalid `severity` string (AC13).
- **Coverage map:** one focused test per AC1–AC16 above.
- **Adversarial / edge cases:**
  - A record that fires **all three** checks at once (interior gap **and**
    expected-span shortfall at a non-border end **and** below `expected_count`)
    yields three findings in the fixed order — pins AC14.
  - `border_aware: false` with a truncated end: the beyond-end expected level is
    flagged despite the border touch (confirms the toggle drives suppression).
  - An `expected_levels` list containing a **non-canonical / unknown** name is
    ignored without crashing.
  - A single-present-level record (`present_levels` length 1, `missing_levels`
    empty) does not crash and fires no interior/span finding.
  - An interior gap whose bracketing neighbour touches a border is **still**
    flagged (interior gaps are never border-suppressed) — pins the crux design.
  - Determinism: two `run_rules` calls return equal lists; multi-check output
    order is stable (AC14).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC16).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027 / 028** — sibling rule families, the canonical pattern this item
    mirrors (registration, `_severity_from_param`, reason tags, deterministic
    ordering, no record mutation, case-vs-label attribution).
  - **Item 014** — inter-vertebra relationships; supplies the `present_levels`
    and `missing_levels` (levels absent within the span) that check 1 consumes
    and checks 2/3 read, via `relationships_to_dict` (item 016).
  - **Item 011** — per-label geometry; supplies the `touches_superior` /
    `touches_inferior` border-contact flags the border-aware span check reads.
  - **Item 004** — label convention; `CANONICAL_ORDER` defines the expected
    ordered level sequence and the canonical ranking used for ordering and
    beyond-span-end comparisons.
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.coverage` config and the
    §6-mode-5 end-to-end test.

This item is **parallel-independent** of the other rule families (027, 028,
030–033); they share only the already-merged item-026 interface.

## Decisions & Trade-offs

To be updated during implementation.

Initial design decisions carried from this spec (confirm or revise during
implementation):

- **Border-awareness lives at the span ends, not the interior check.** An
  interior missing level is bracketed by segmented vertebrae above and below, so
  the FOV covers it and the gap is always genuine; only span *ends* can be
  FOV-truncated. This is why check 1 never consults border flags and check 2
  does. It is also why the mandatory *"no spurious finding when truncated at the
  FOV edge"* behaviour holds under the default config (a truncated span has no
  interior gap, and the opt-in checks are off).
- **Three checks, one `rule_id`, distinguished by reason tags** (mirrors
  item 028's two-kind single-rule pattern). A case can emit up to three findings
  in a fixed order: missing-interior → incomplete-span → count-shortfall.
- **Missing-level findings are case-level (`labels == frozenset()`).** Absent
  vertebrae have no integer segmentation label; names go in the `reason`.
- **`expected_count` is a raw, non-border-aware hard minimum** (Use-Case-C
  curation), whereas the `expected_levels` span check is border-aware
  (segmentation-failure detection). Keeping the two semantics distinct makes each
  independently and unambiguously testable.
- **No shipped numeric thresholds.** Both opt-in checks default to disabled;
  reference-derived expected spans/counts are Stage 6.

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md) (scoped to
this item's rows only; `git pull --rebase` first):

- Flip the Stage 4 deliverable sub-row **"incomplete coverage / missing levels
  (count vs expected sequence)"** (line ~153) from 📋 → ✅, annotating it
  `*(Item 029)*`.
- Leave the Stage 4 **acceptance checkboxes** and the **stage rollup** (the
  Stage 4 index row and the objective-coverage rows) as they are — Stage 4 closes
  only when item 035 lands the per-failure-mode end-to-end tests; the validator
  reconciles the stage ✅ at that point.
- Per `CLAUDE.md`: work on branch
  `aide/029-incomplete-coverage-missing-level-rules`, keep `progress.md` edits
  scoped to this item, and direct-merge (no PR) once green.
