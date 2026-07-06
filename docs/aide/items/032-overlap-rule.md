# Item 032 — Overlap Rule

> **Created:** 2026-07-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 032
> **Objectives:** G2 (detect §6 failure modes — mode 8, *overlapping segments:
> voxels assigned to more than one vertebra label*), supporting G4 (per-case
> reasons + offending labels)
> **Suggested branch:** `aide/032-overlap-rule`

---

## Description

Implement an **overlap rule** for the Stage 4 heuristic rule engine that consumes
the pre-computed **overlap-detection results** (item 015, exposed at the top-level
`overlaps` key of the per-case feature record) to detect **§6 failure mode 8 —
overlapping segments: voxels assigned to more than one vertebra label, or labels
whose masks intersect**. The rule plugs into the item-026 engine core exactly like
the sibling bounds (item 027), fragmentation (item 028), coverage (item 029),
sequence (item 030), and border (item 031) rules: it subclasses
`segqc.heuristics.Rule`, registers itself via `register_rule`, reads its severity
and threshold from the versioned config through `config.rule_param`, and emits
`segqc.heuristics.Finding` objects through the standard runner. It follows every
convention those siblings pinned — per-case determinism, a fixed output order,
default severity `FLAG` (config-overridable), an unrecognised severity string
raising `ValueError`, and **never mutating** the input record.

### The signal this rule consumes

Item 015 (`segqc.features.overlap.detect_overlaps`) computes, per overlapping
label pair, an `OverlapPair` — serialised by `overlap_to_dict` (item 016) into the
per-case feature record's top-level `overlaps` list (assembled by
`build_features_block`, item 016). Item 015 **omits** any pair with zero shared
voxels, so every entry in `overlaps` already represents a genuine intersection
(`overlap_voxels >= 1`), and the list is **pre-sorted** by `(label_a, label_b)`:

```
record["overlaps"] : [ {
    "label_a":        int,    # lower  integer label of the pair (label_a < label_b, enforced by item 015)
    "label_b":        int,    # higher integer label of the pair
    "name_a":         str,    # anatomical name for label_a (may be UNKNOWN)
    "name_b":         str,    # anatomical name for label_b
    "overlap_voxels": int,    # count of voxels shared by both labels (>= 1)
}, ... ]                      # sorted by (label_a, label_b); [] when no pairs overlap
```

The rule reads **only** this `overlaps` list. It never reads `per_label`,
`relationships`, `geometry`, any mm/spacing/extent/volume field, or the raw label
map, so it is **inherently spacing-agnostic** — its output depends solely on the
voxel-count overlap results.

> **Record-shape note (defensive).** In the sibling rule-family unit tests the
> per-case record often carries `"overlaps": {}` (an empty dict placeholder) when
> overlaps are irrelevant to that rule. In a *real* record built by
> `build_features_block`, `overlaps` is always a **list** (possibly empty). The
> rule therefore treats any non-list `overlaps` (absent, `None`, `{}`) as "no
> overlaps" and returns no finding, rather than assuming a list (AC13).

### What the rule does

The rule iterates the `overlaps` entries in `(label_a, label_b)` order and, for
each pair whose `overlap_voxels` meets the configured minimum, emits **one**
`Finding` (`rule_id == "overlap"`):

- **`labels`** — the pair's two offending integer labels, i.e.
  `frozenset({label_a, label_b})` (label-attributed, mirroring item 030/031's
  label-attributed findings and in deliberate contrast to item 029's case-level
  missing-level findings — overlapping vertebrae are both *present* and carry real
  integer labels).
- **`severity`** — the configured `severity` (default `Severity.FLAG`).
- **`reason`** — a human-readable string naming both offending labels (integer
  label and anatomical name) and the **overlap magnitude** (the shared-voxel
  count), e.g. `"Overlapping segments: labels 20 (L1) and 21 (L2) share 37
  voxel(s)."`.

A **config-driven minimum-overlap threshold** (`min_overlap_voxels`, default `1`)
gates each finding: a pair is flagged only when `overlap_voxels >=
min_overlap_voxels`. With the default of `1`, every present overlap fires (item
015 already omits zero-voxel pairs); raising the threshold suppresses trivial
single-/few-voxel touches without code changes. Targets **§6 failure mode 8**.

### Scope boundary — what this item is **not**

- **Not overlap *detection*.** Computing which label pairs share voxels and by how
  much is **item 015** (`detect_overlaps`), already merged. This rule only
  *consumes* the pre-computed `overlaps` results; it never re-derives them and
  never touches a mask stack or label map.
- **Not border / coverage / sequence / bounds / fragmentation / mislabel.** Those
  are §6 modes 6 / 5 / 7 / 2 / 2–3 / 1&4, items 031 / 029 / 030 / 027 / 028 / 033.
- **Not verdict aggregation.** Combining findings into a `pass` / `flag` / `fail`
  verdict is **item 034**.
- **Not the shipped default config file.** Item 035 ships the documented YAML; here
  the defaults live as `rule_param` fallbacks.
- Does **not** touch the item-026 engine core, `config.py`, `verdict.py`,
  `feature_report.py`, `segqc.features.overlap`, or any extractor.

### Config shape (read via `config.rule_param`)

```yaml
rules:
  overlap:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review — severity of overlap findings
      min_overlap_voxels: 1             # optional; default 1 — minimum shared-voxel count for a pair to be flagged
```

An absent `rules.overlap` section leaves the rule fully operational: it flags every
present overlap (threshold `1`) at the default `FLAG` severity.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "overlap"`.**
      Importing `segqc.heuristics` makes an `OverlapRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("overlap")`
      returns the registered instance and `overlap` appears in `iter_rules()`.

- [ ] **AC2: No finding for disjoint labels.**
      For a record whose `overlaps` list is empty (`[]`), under
      `default_config()`, `evaluate` returns `[]` — no overlap finding.

- [ ] **AC3: A finding fires for two deliberately intersecting labels.**
      Given a record with a single `overlaps` entry
      (`label_a=20, label_b=21, overlap_voxels=37`), the rule emits exactly
      **one** `Finding` with `rule_id == "overlap"`.

- [ ] **AC4: The offending pair is attributed by both integer labels.**
      For the AC3 entry, the emitted finding's
      `labels == frozenset({20, 21})` — label-attributed with **both** members of
      the pair, not an empty case-level frozenset.

- [ ] **AC5: The overlap magnitude appears in the reason.**
      For the AC3 entry, the finding's `reason` contains the shared-voxel count
      (`"37"`) — a sensible magnitude the report can surface.

- [ ] **AC6: Both offending labels are named in the reason.**
      For the AC3 entry (`name_a="L1"`, `name_b="L2"`), the finding's `reason`
      names both offending labels — the integer labels `20` and `21` both appear.

- [ ] **AC7: Multiple overlapping pairs each yield one finding, in ascending
      `(label_a, label_b)` order.** Given three `overlaps` entries — `(19, 21)`,
      `(19, 20)`, `(20, 21)` — the rule emits exactly **three** findings, one per
      pair, ordered `(19,20)`, `(19,21)`, `(20,21)`; each finding's `labels`
      matches its pair.

- [ ] **AC8: `min_overlap_voxels` suppresses sub-threshold pairs and is
      config-driven.** With `rules.overlap.params.min_overlap_voxels == 5`, a pair
      with `overlap_voxels == 4` yields **no** finding while a pair with
      `overlap_voxels == 5` yields exactly **one** finding.

- [ ] **AC9: The default threshold flags any present overlap.**
      With no `min_overlap_voxels` param (`default_config()`), a pair with
      `overlap_voxels == 1` yields exactly **one** finding.

- [ ] **AC10: Default severity is `FLAG`, and severity is config-driven.**
      With no `severity` param, an overlap finding has
      `severity == Severity.FLAG`. With `rules.overlap.params.severity` set to
      `fail`, the emitted finding has `severity == Severity.FAIL`.

- [ ] **AC11: An unrecognised `severity` string raises `ValueError`.**
      If `rules.overlap.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, `"fail"`), `evaluate` raises `ValueError`
      immediately — before any per-record processing (verified with an empty
      `overlaps` record, so the raise cannot come from entry iteration).

- [ ] **AC12: The rule is deterministic.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return
      equal finding lists in the same order.

- [ ] **AC13: The rule tolerates degenerate / malformed records.**
      `evaluate` returns a list and raises nothing when: `overlaps` is absent,
      `None`, an empty list, or a non-list placeholder (`{}`); an `overlaps` entry
      is missing `overlap_voxels` (treated as `0`, hence suppressed under the
      default threshold); an entry is missing a label field (contributes no
      finding); the record carries no `per_label` / `relationships` keys.

- [ ] **AC14: The rule reads only the `overlaps` block.**
      Two records carrying an identical `overlaps` list but differing in every
      other field (`per_label`, `relationships`, `stage3`, mm/spacing values)
      yield **identical** finding lists (equal `rule_id`, `severity`, `labels`,
      and `reason`) — the rule's output depends solely on `overlaps` and is
      therefore spacing-agnostic.

- [ ] **AC15: The rule does not mutate the input record.**
      Calling `evaluate(record, config)` leaves `record` (including the
      `overlaps` list and every entry dict) unchanged — verified by deep equality
      against a pre-call copy.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **Overlap results are read from the record's top-level `overlaps` list (item
  015), not re-derived.** Pinned interface (via `overlap_to_dict`, item 016): each
  entry is a dict with `label_a`, `label_b`, `name_a`, `name_b`, and
  `overlap_voxels` (int shared-voxel count), the list sorted by
  `(label_a, label_b)` and containing **no** zero-overlap pairs. If that shape
  diverged, the builder/validator hands back.
- **`overlaps` may be a non-list placeholder in hand-built records.** In real
  records `build_features_block` always emits a list, but sibling unit-test
  records use `"overlaps": {}` as a placeholder. The defensible default under
  clarify=`assume` is to treat any non-list `overlaps` (absent / `None` / `{}`) as
  "no overlaps" and return no finding — never crash, never assume a list.
- **`min_overlap_voxels` defaults to `1` (flag every present overlap).** The queue
  requires "any minimum-overlap threshold is config-driven." Since item 015 already
  omits zero-voxel pairs, a default of `1` flags every intersection the detector
  reports; the threshold exists so operators can suppress trivial single-/few-voxel
  touches (e.g. label-boundary quantisation) without code changes. This is the most
  material design default; the validator surfaces it at the queue boundary. The
  threshold comparison is inclusive: a pair fires iff `overlap_voxels >=
  min_overlap_voxels`.
- **Findings are label-attributed with the *pair* (`frozenset({label_a,
  label_b})`).** Both overlapping vertebrae are present and carry real integer
  labels, so — unlike item 029's *absent*-level findings (case-level, empty
  frozenset) — this rule attaches both offenders, mirroring items 030/031's
  label-attributed findings. One finding per overlapping pair.
- **One finding per pair, emitted in ascending `(label_a, label_b)` order.** The
  item-015 list is already sorted, but the rule re-sorts defensively (mirroring
  `build_features_block`'s defensive re-sort) so ordering never depends on caller
  input — for determinism (AC12).
- **The overlap magnitude in the `reason` is the `overlap_voxels` count.** The
  queue asks for "the overlap magnitude in the reason"; the voxel count is the
  magnitude item 015 provides. Anatomical names (`name_a` / `name_b`) and integer
  labels are also included for report readability.
- **Default severity is `flagged-for-review` (`Severity.FLAG`)**, matching the
  sibling rules (items 027–031); overridable via `severity`, with an unrecognised
  string raising `ValueError` **before** any per-record processing (read up-front).
  `min_overlap_voxels` is coerced via `int(...)`.
- **The rule never mutates the input record** — it only reads `overlaps` and
  builds fresh `Finding`s.
- **Item 026's `forbidden_stems` guard test still lists `"overlap"`.**
  `tests/test_026_rule_engine_core.py::test_ac18_no_concrete_rule_family_module_in_package`
  asserts no `overlap.py` exists in `segqc/heuristics/` (its `forbidden_stems` set
  is `{"overlap", "mislabel", "misalignment"}`). Landing this module makes that
  assertion fail, so **`"overlap"` must be removed from that set** — the same
  established precedent by which `bounds` / `fragmentation` / `coverage` /
  `sequence` / `border` were already removed as each family landed. The
  **test-writer** handles this edit (this spec author writes no tests).

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/overlap.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, and `Severity` from `segqc.verdict`.
   - Define a stable, testable reason-tag constant, e.g.
     `_OVERLAP_TAG = "Overlapping segments:"`, and a default threshold constant
     `_DEFAULT_MIN_OVERLAP_VOXELS = 1`.
   - Reuse the sibling `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}`
     lookup and a `_severity_from_param(label) -> Severity` helper that raises
     `ValueError` on an unrecognised label (mirror `sequence.py` / `coverage.py`).

2. **Implement `class OverlapRule(Rule)`** with `rule_id = "overlap"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read `severity` once via `_severity_from_param(config.rule_param("overlap",
     "severity", default="flagged-for-review"))` (raises on a bad string before any
     per-record processing — AC11). Read `min_overlap = int(config.rule_param(
     "overlap", "min_overlap_voxels", default=_DEFAULT_MIN_OVERLAP_VOXELS))`.
   - Read `overlaps = record.get("overlaps")`; if `not isinstance(overlaps, list)`,
     return `[]` (AC2, AC13 — tolerates absent / `None` / `{}` placeholder).
   - Build a normalised, sorted working list: for each `entry` in `overlaps` that
     is a mapping, read `label_a = entry.get("label_a")`,
     `label_b = entry.get("label_b")`; skip the entry if **either** is `None`
     (AC13 — both labels are required to attribute a finding). Coerce both via
     `int(...)`. Read
     `voxels = int(entry.get("overlap_voxels", 0) or 0)`. Read `name_a`, `name_b`
     (default to `str(label)` / `"?"` when absent).
   - Sort the working entries by `(label_a, label_b)` with `None` sorted last, for
     deterministic ascending order (AC7, AC12) independent of caller input.
   - For each entry with `voxels >= min_overlap` (AC8, AC9): append
     `Finding(rule_id="overlap", severity=severity, reason=f"{_OVERLAP_TAG} labels
     {label_a} ({name_a}) and {label_b} ({name_b}) share {voxels} voxel(s).",
     labels=frozenset({l for l in (label_a, label_b) if l is not None}))`.
   - Return the accumulated list. **Do not mutate** `record`, `overlaps`, or any
     entry (AC15): only read, and build fresh `Finding`s.

3. **Register the rule:** decorate `OverlapRule` with `@register_rule`.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import overlap  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds`,
   `fragmentation`, `coverage`, `sequence`, and `border` imports, so importing
   `segqc.heuristics` makes the `overlap` rule discoverable via the
   registry/runner. (Optionally update the package docstring's "no concrete rule
   family … overlap …" wording — it is prose, not asserted.)

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `feature_report.py`, `segqc/features/overlap.py`, or any extractor. All
   parameters flow through the existing `rule_enabled` / `rule_param` accessors.

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_032_overlap.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering `OverlapRule`
  does not leak across tests and re-registration does not raise a duplicate-id
  error (mirror `tests/test_031_border_partial_vertebra.py` /
  `test_030_sequence_continuity.py`).
- **Record fixtures:** build minimal per-case records by hand matching the
  `build_features_block` shape — a top-level `overlaps` list of dicts, each with
  `label_a`, `label_b`, `name_a`, `name_b`, `overlap_voxels` — rather than running
  the full extractor stack (the rule reads only `overlaps`). Provide a small helper
  to assemble an overlap entry from `(label_a, label_b, overlap_voxels,
  name_a=?, name_b=?)` and a record from a list of entries. Use the default
  convention's integer labels where attribution is asserted (e.g. `T12 == 19`,
  `L1 == 20`, `L2 == 21`). Fixtures:
  - **disjoint** — `overlaps == []` — AC2;
  - **single pair** — one entry `(20, 21, 37)` — AC3, AC4, AC5, AC6;
  - **multi-pair** — three entries `(19,21)`, `(19,20)`, `(20,21)` fed in
    non-sorted order, asserting ascending `(label_a, label_b)` output — AC7;
  - **threshold pair** — a `4`-voxel and a `5`-voxel entry under
    `min_overlap_voxels == 5` — AC8;
  - **one-voxel** — a `1`-voxel entry under `default_config()` — AC9;
  - **field-isolation pair** — two records with identical `overlaps` but different
    `per_label` / `relationships` / mm fields — AC14;
  - **degenerate records** — `overlaps` absent / `None` / `[]` / `{}`; an entry
    missing `overlap_voxels`; an entry missing a label field — AC13.
- **Config fixtures:** `default_config()` for the defaults path (AC2, AC9, AC10);
  an in-process `HeuristicConfig` (or `load_config` on a temp YAML) with a
  `severity` override (AC10), a `min_overlap_voxels` override (AC8), and an invalid
  `severity` string (AC11).
- **Coverage map:** one focused test per AC1–AC15 above.
- **Adversarial / edge cases:**
  - Determinism: two `run_rules` calls return equal lists; findings appear in
    ascending `(label_a, label_b)` order (AC12, AC7).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC15).
  - An entry missing `overlap_voxels` is treated as `0` and suppressed under the
    default threshold amid other flagged pairs (AC13).
  - A non-list `overlaps` placeholder (`{}`) yields `[]` without crashing (AC13).
- **Item-026 guard edit (test-writer):** remove `"overlap"` from the
  `forbidden_stems` set in
  `tests/test_026_rule_engine_core.py::test_ac18_no_concrete_rule_family_module_in_package`
  so that guard passes once `overlap.py` lands — the same edit made when `bounds` /
  `fragmentation` / `coverage` / `sequence` / `border` landed. Leave `"mislabel"`
  and `"misalignment"` in place (item 033 not yet built).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027 / 028 / 029 / 030 / 031** — sibling rule families, the canonical
    pattern this item mirrors (registration, `_severity_from_param`, reason tag,
    deterministic ordering, no record mutation, label attribution).
  - **Item 015** — overlap detection (`detect_overlaps`, `OverlapPair`); computes
    the per-pair shared-voxel counts (the signal this rule consumes).
  - **Item 016** — `build_features_block` / `overlap_to_dict`; assembles the
    per-case record's top-level `overlaps` list (the field the rule reads).
  - **Item 004** — label convention; defines the integer labels / anatomical names
    the overlapping vertebrae carry (`overlaps` entries carry them, so the rule
    reads them from the record rather than importing the convention).
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.overlap` config and the
    §6-mode-8 end-to-end test.

This item is **parallel-independent** of the other rule families (027–031, 033);
they share only the already-merged item-026 interface.

## Decisions & Trade-offs

Implemented exactly per the Implementation Steps: a single new module
`src/segqc/heuristics/overlap.py` plus a one-line registration import in
`src/segqc/heuristics/__init__.py`. No changes to engine core, config schema,
or extractors.

- `OverlapRule.evaluate` reads `severity` and `min_overlap_voxels` once
  up-front (via `_severity_from_param`, mirroring `border.py` /
  `sequence.py` / `coverage.py`), so an invalid severity string raises
  `ValueError` before any per-record processing, satisfying AC11 even for a
  record with an empty/absent `overlaps`.
- `record.get("overlaps")` is checked with `isinstance(..., list)`; any
  non-list value (absent, `None`, `{}`) short-circuits to `[]`, satisfying
  AC2/AC13 without inspecting the value further.
- Entries are normalised into `(label_a, label_b, voxels, name_a, name_b)`
  tuples with `int(...)` coercion; an entry missing **either** `label_a` or
  `label_b` is skipped entirely (AC13 requires both labels to attribute a
  finding — corrected in round 2 after validation found the original
  Implementation Steps wording, "skip if both are `None`", contradicted the
  binding AC13 text; an entry with exactly one label present previously
  produced a bogus `None (?)`-labelled `Finding`). A missing `overlap_voxels`
  on a fully-labelled entry still coerces to `0` via
  `int(entry.get("overlap_voxels", 0) or 0)`, which the default threshold of
  `1` then suppresses.
- The normalised list is defensively re-sorted by `(label_a, label_b)` with
  `None` sorted last (`_sort_key`), independent of the input order — matching
  item 015's own sort but re-derived for determinism (AC7/AC12) per the
  build_features_block precedent.
- `labels` on each `Finding` is `frozenset({label_a, label_b})` filtering out
  any `None` member defensively, though after the round-2 fix both members are
  always present for any entry that reaches finding construction (entries
  missing either label are now skipped earlier, per AC13).
- No mutation: the rule only reads from `record`/`overlaps`/entries and
  builds fresh tuples and `Finding` objects (AC15).
