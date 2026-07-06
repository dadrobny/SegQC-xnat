# Item 033 — Mislabel / Misalignment Rule

> **Created:** 2026-07-06 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 033
> **Objectives:** G2 (detect §6 failure modes — mode 1, *label not aligned with
> the vertebra it names*, and mode 4, *semantic mislabelling / wrong vertebra
> identification*), supporting G4 (per-case reasons + offending labels)
> **Suggested branch:** `aide/033-mislabel-misalignment-rule`

---

## Description

Implement a **mislabel / misalignment rule** for the Stage 4 heuristic rule
engine that detects two related §6 failure modes by combining the pre-computed
**centroid-ordering** (item 014), **per-vertebra spline-offset** (item 018), and
**monotonic-progression** (item 020) features already assembled into the per-case
feature record:

- **§6 mode 1 — label not aligned with the vertebra it names** (*misalignment*):
  a vertebra whose centroid is a **large outlier from the fitted spinal curve**.
  The signal is the per-vertebra perpendicular **spline offset** (`offset_mm`,
  item 018) exceeding a config-driven threshold.
- **§6 mode 4 — semantic mislabelling / wrong vertebra identification**: a
  vertebra whose physical **position is inconsistent with its anatomical label's
  expected ordering relative to neighbours**. The signal is the **monotonic-
  progression** metric (`non_monotonic_pairs`, item 020) — anatomically
  consecutive labels whose closest-approach spline parameter *u* fails to advance,
  i.e. a label physically out of place for the name it carries (e.g. a swapped
  L1/L2 pair).

The rule plugs into the item-026 engine core exactly like the sibling bounds
(027), fragmentation (028), coverage (029), sequence (030), border (031), and
overlap (032) rules: it subclasses `segqc.heuristics.Rule`, registers itself via
`@register_rule`, reads its severity and thresholds from the versioned config via
`config.rule_param`, and emits `segqc.heuristics.Finding` objects through the
standard runner. It follows every convention those siblings pinned — per-case
determinism, a fixed output order, default severity `FLAG` (config-overridable),
an unrecognised severity string raising `ValueError` **before** any per-record
processing, and **never mutating** the input record.

### The signals this rule consumes

`build_features_block` (item 016, in `segqc.feature_report`) assembles the
per-case record. This rule reads three already-serialised sub-blocks and **never
recomputes** any geometry, offset, spline, or ordering itself:

```
record["stage3"]["per_label_offsets"] : [ {         # item 018 (spline_offset_to_dict)
    "label":      int,        # integer vertebra label
    "level_name": str,        # anatomical name (may be UNKNOWN)
    "offset_mm":  float,      # perpendicular distance (mm) of the centroid from the fitted spline
    "closest_u":  float, "offset_voxel": float,
    "dx_mm": float, "dy_mm": float, "dz_mm": float,
}, ... ]                                             # sorted ascending by label

record["stage3"]["monotonic_consistency"] : {       # item 020 (monotonic_consistency_to_dict)
    "is_monotonic":        bool,
    "non_monotonic_pairs": [ [level_a, level_b], ... ],   # (name, name) pairs where u did NOT advance
    "u_values":            [ float, ... ],
}

record["per_label"] : { "<label>": {                # item 016 — used to resolve level_name -> int label
    "label": int, "level_name": str, ... }, ... }
```

**How all three feature families feed the rule.** Item 020's `non_monotonic_pairs`
is computed from the item-014 **ordered centroid sequence** compared against the
fitted spline, so the item-014 centroid ordering is the anatomical basis the
monotonic-progression metric is evaluated against; item 018 supplies the
perpendicular offset. The rule therefore combines centroid ordering (014), spline
offset (018), and monotonic progression (020) exactly as the queue requires,
while reading each as a pre-serialised field rather than re-deriving it.

### What the rule does

`MislabelRule.evaluate` runs **two independent, config-gated detectors** and
returns their combined findings (`rule_id == "mislabel"`), offset findings first
(ascending label), then order findings (ascending level-name pair):

- **Detector A — spline-offset outlier (misalignment, mode 1).** Iterate
  `stage3.per_label_offsets` in ascending-label order. For each entry whose
  `offset_mm >= max_offset_mm` (config, default `15.0`), emit **one** per-label
  `Finding`: `labels = frozenset({label})`; `reason` names the integer label,
  anatomical name, and the **deviation magnitude** (the offset in mm and the
  threshold), e.g. `"Vertebra misaligned from spinal curve: label 20 (L1)
  centroid lies 41.3 mm off the fitted spinal curve (threshold 15.0 mm)."`.

- **Detector B — ordering / position inconsistency (semantic mislabelling,
  mode 4).** Iterate `stage3.monotonic_consistency.non_monotonic_pairs`. For each
  `[level_a, level_b]` pair, resolve both level names to their integer labels via
  `per_label` and emit **one** per-pair `Finding`: `labels = frozenset({label_a,
  label_b})` (an unresolvable name is omitted from `labels` but still named in the
  `reason`); `reason` names both offending labels and states the nature of the
  inconsistency, e.g. `"Vertebra ordering inconsistent with label: labels 20 (L1)
  and 21 (L2) are out of expected order along the spine (spline parameter does not
  advance)."`. Pairs are emitted in ascending `(level_a, level_b)` order.

**Severity** is read once up-front (`severity`, default `flagged-for-review`) and
applies to both detectors. **Config-driven gates** let an operator disable either
detector without code changes: `flag_offset_outliers` (default `true`) gates
Detector A, `flag_order_inconsistency` (default `true`) gates Detector B. Targets
**§6 failure modes 1 and 4**.

### Scope boundary — what this item is **not**

- **Not feature *computation*.** Spline offsets (item 018), the monotonic-
  progression metric (item 020), centroids/relationships (items 013/014), and the
  spline fit (item 017) are all already merged. This rule only *consumes* the
  serialised `stage3.per_label_offsets`, `stage3.monotonic_consistency`, and
  `per_label` fields; it never re-derives them, never touches a spline, centroid,
  or label map.
- **Not the label-sequence continuity rule (item 030).** Item 030 targets **§6
  mode 7** (non-continuous label *sequence*) by consuming
  `relationships.out_of_order_labels` — the *input name-order* non-monotonicity.
  This rule deliberately does **not** re-read `out_of_order_labels`; it uses the
  distinct **geometric** monotonic-progression signal
  (`stage3.monotonic_consistency.non_monotonic_pairs`) for mode 4 (a label
  physically out of place), avoiding duplicate flags with item 030.
- **Not bounds / fragmentation / coverage / border / overlap.** Those are §6 modes
  2 / 2–3 / 5 / 6 / 8, items 027 / 028 / 029 / 031 / 032.
- **Not verdict aggregation.** Combining findings into a `pass` / `flag` / `fail`
  verdict is **item 034**.
- **Not the shipped default config file.** Item 035 ships the documented YAML;
  here the defaults live as `rule_param` fallbacks.
- Does **not** touch the item-026 engine core, `config.py`, `verdict.py`,
  `feature_report.py`, any `segqc.features.*` extractor, or the neighbourhood
  feature (item 024) — which `build_features_block` does not serialise into the
  record, so it is not available to consume.

### Config shape (read via `config.rule_param`)

```yaml
rules:
  mislabel:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review — severity of all mislabel findings
      max_offset_mm: 15.0               # optional; default 15.0 — offset (mm) at/above which a vertebra is flagged misaligned
      flag_offset_outliers: true        # optional; default true — enable Detector A (spline-offset outliers)
      flag_order_inconsistency: true    # optional; default true — enable Detector B (monotonic-progression inconsistency)
```

An absent `rules.mislabel` section leaves the rule fully operational: both
detectors run at the default `FLAG` severity with `max_offset_mm == 15.0`.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "mislabel"`.**
      Importing `segqc.heuristics` makes a `MislabelRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("mislabel")`
      returns the registered instance and `mislabel` appears in `iter_rules()`.

- [ ] **AC2: No finding for a well-aligned record.**
      For a record whose `per_label_offsets` all have `offset_mm` below the
      default threshold and whose `monotonic_consistency.non_monotonic_pairs` is
      empty (`[]`), under `default_config()`, `evaluate` returns `[]`.

- [ ] **AC3: Detector A fires for a displaced vertebra (large spline offset).**
      Given a record with one `per_label_offsets` entry whose `offset_mm` is at or
      above `max_offset_mm` (e.g. `offset_mm == 41.3`, default threshold `15.0`),
      and an empty `non_monotonic_pairs`, the rule emits exactly **one** `Finding`
      with `rule_id == "mislabel"`.

- [ ] **AC4: Detector A finding is attributed to the single offending label.**
      For the AC3 entry (`label == 20`), the emitted finding's
      `labels == frozenset({20})`.

- [ ] **AC5: Detector A reason carries the offset deviation magnitude.**
      For the AC3 entry, the finding's `reason` contains the offset magnitude
      (the `"41.3"` mm value, formatted to one decimal) — a sensible magnitude the
      report can surface.

- [ ] **AC6: `max_offset_mm` is config-driven and the comparison is inclusive.**
      With `rules.mislabel.params.max_offset_mm == 20.0`, an offset entry with
      `offset_mm == 19.9` yields **no** finding while an entry with
      `offset_mm == 20.0` yields exactly **one** finding.

- [ ] **AC7: The default offset threshold flags a large outlier but not a small
      offset.** Under `default_config()` (`max_offset_mm == 15.0`), an offset
      entry with `offset_mm == 3.0` yields **no** finding while one with
      `offset_mm == 40.0` yields exactly **one** finding.

- [ ] **AC8: Detector B fires for a swapped / mislabelled pair (ordering
      inconsistency).** Given a record with one `non_monotonic_pairs` entry
      `["L1", "L2"]` (and offsets all below threshold), the rule emits exactly
      **one** `Finding` with `rule_id == "mislabel"` for that pair.

- [ ] **AC9: Detector B finding is attributed to both offending labels.**
      For the AC8 pair, with `per_label` mapping `L1 -> 20` and `L2 -> 21`, the
      emitted finding's `labels == frozenset({20, 21})`.

- [ ] **AC10: Both offending levels are named in the Detector B reason.**
      For the AC8 pair, the finding's `reason` names both offending vertebrae —
      the resolved integer labels `20` and `21` both appear.

- [ ] **AC11: Multiple offset outliers each yield one finding, in ascending label
      order.** Given three `per_label_offsets` entries above threshold with labels
      `21`, `19`, `20`, the rule emits exactly **three** offset findings ordered by
      label `19`, `20`, `21`; each finding's `labels` matches its label.

- [ ] **AC12: Multiple non-monotonic pairs each yield one finding, in ascending
      `(level_a, level_b)` order.** Given `non_monotonic_pairs`
      `[["T12","L1"], ["L1","L2"]]` fed in reverse order, the rule emits exactly
      **two** order findings ordered `("L1","L2")` then `("T12","L1")`
      (ascending by the level-name pair).

- [ ] **AC13: Detector A is config-gated by `flag_offset_outliers`.**
      With `rules.mislabel.params.flag_offset_outliers == false`, a record
      carrying an above-threshold offset **and** a non-monotonic pair yields **no**
      offset finding but **still** yields the order finding.

- [ ] **AC14: Detector B is config-gated by `flag_order_inconsistency`.**
      With `rules.mislabel.params.flag_order_inconsistency == false`, a record
      carrying an above-threshold offset **and** a non-monotonic pair yields **no**
      order finding but **still** yields the offset finding.

- [ ] **AC15: Default severity is `FLAG`, and severity is config-driven for both
      detectors.** With no `severity` param, both an offset finding and an order
      finding have `severity == Severity.FLAG`. With
      `rules.mislabel.params.severity` set to `fail`, both emitted findings have
      `severity == Severity.FAIL`.

- [ ] **AC16: An unrecognised `severity` string raises `ValueError`.**
      If `rules.mislabel.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, `"fail"`), `evaluate` raises `ValueError`
      immediately — **before** any per-record processing (verified with a
      degenerate record carrying no `stage3`, so the raise cannot come from
      per-detector iteration).

- [ ] **AC17: The rule is deterministic.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return
      equal finding lists in the same order.

- [ ] **AC18: The rule tolerates degenerate / malformed records.**
      `evaluate` returns a list and raises nothing when: `stage3` is absent,
      `None`, or a non-dict; `per_label_offsets` is absent, `None`, or a non-list;
      `monotonic_consistency` is absent, `None`, or a non-dict;
      `non_monotonic_pairs` is absent, `None`, or a non-list; an offset entry is
      missing `offset_mm` (treated as `0.0`, hence not flagged); an offset entry is
      missing `label` (skipped); a `non_monotonic_pairs` entry is not a
      two-element sequence (skipped); `per_label` is absent (a Detector B name that
      cannot be resolved is omitted from `labels` but still named in the `reason`).

- [ ] **AC19: The rule reads only the offset, monotonic-consistency, and
      per_label blocks.** Two records carrying identical
      `stage3.per_label_offsets`, `stage3.monotonic_consistency`, and `per_label`
      but differing in every other field (`overlaps`, `relationships`,
      `stage3.spacing_consistency`, `stage3.curvature`, geometry mm/spacing values)
      yield **identical** finding lists (equal `rule_id`, `severity`, `labels`, and
      `reason`).

- [ ] **AC20: The rule does not mutate the input record.**
      Calling `evaluate(record, config)` leaves `record` (including the `stage3`
      sub-block and every nested list/dict) unchanged — verified by deep equality
      against a pre-call copy.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **The three feature signals are read from the serialised record, not
  recomputed.** Pinned interfaces: `stage3.per_label_offsets` (item 018 via
  `spline_offset_to_dict` — each entry has `label`, `level_name`, `offset_mm`,
  sorted by label); `stage3.monotonic_consistency.non_monotonic_pairs` (item 020
  via `monotonic_consistency_to_dict` — a list of `[level_a, level_b]` name
  pairs); `per_label["<label>"]` (item 016 — `label` + `level_name`, used to
  resolve names to integer labels). If any of these shapes diverged, the
  builder/validator hands back.
- **Item-014 centroid ordering is combined via the item-020 monotonic-progression
  metric, not via `out_of_order_labels`.** The queue asks to combine centroid
  ordering (014), spline offset (018), and monotonic progression (020). Item 020's
  `non_monotonic_pairs` is derived from the item-014 ordered centroid sequence
  compared to the spline, so item 014's ordering is the anatomical basis of the
  signal this rule consumes. The rule deliberately does **not** re-read
  `relationships.out_of_order_labels`, which is item 030's mode-7 (name-continuity)
  responsibility — reusing it here would double-flag. This is the most material
  design default under clarify=`assume`; the validator surfaces it at the queue
  boundary.
- **Two independent detectors, combined with OR.** Per the queue's phrasing —
  "a vertebra whose centroid is a large outlier ... **or** whose position is
  inconsistent with its anatomical label's expected ordering" — Detector A
  (offset outlier, mode 1) and Detector B (monotonic-progression inconsistency,
  mode 4) fire independently; a record may produce findings from either or both.
- **`max_offset_mm` defaults to `15.0` mm and the comparison is inclusive**
  (`offset_mm >= max_offset_mm` fires). A well-aligned vertebra's perpendicular
  spline offset is near zero; a displaced/misaligned one is many mm off the curve.
  `15.0` mm is a defensible hand-set "large outlier" threshold that leaves normal
  anatomical variation unflagged (reference-derived bounds are Stage 6; item 035
  ships the documented default). Tunable via config without code changes.
- **Findings are label-attributed.** Detector A attaches the single offending
  label (`frozenset({label})`); Detector B attaches both members of the offending
  pair (`frozenset({label_a, label_b})`), mirroring items 030/031/032's
  label-attributed findings. Both offenders are present vertebrae carrying real
  integer labels, so — unlike item 029's *absent*-level findings (case-level,
  empty frozenset) — attribution is non-empty.
- **Detector B resolves level names to integer labels via `per_label`** (scanning
  entries for a matching `level_name`, mirroring `sequence.py::_label_for_level`).
  A name that cannot be resolved is **omitted from `labels`** but **still named in
  the `reason`**, so a finding is never silently dropped for an unmappable name.
- **Deterministic ordering, independent of caller input.** Offset findings are
  emitted in ascending integer-label order; order findings in ascending
  `(level_a, level_b)` name-pair order; the combined list is offset findings
  first, then order findings. Both detectors re-sort defensively so output never
  depends on the input list order (AC17).
- **The deviation magnitude in the `reason` is the spline offset (`offset_mm`)
  for Detector A.** Detector B's finding is categorical (a pair whose spline
  parameter fails to advance) and conveys the offending labels and the nature of
  the inconsistency; it carries no separate scalar magnitude, satisfying the
  queue's "deviation magnitude" requirement through Detector A's offset.
- **Default severity is `flagged-for-review` (`Severity.FLAG`)**, matching the
  sibling rules (items 027–032); a single `severity` param applies to both
  detectors, overridable, with an unrecognised string raising `ValueError`
  **before** any per-record processing (read up-front). `max_offset_mm` is coerced
  via `float(...)`; the gate params via `bool(...)`.
- **The rule never mutates the input record** — it only reads the three consumed
  blocks and builds fresh `Finding`s.
- **Item 026's `forbidden_stems` guard test still lists `"mislabel"`.**
  `tests/test_026_rule_engine_core.py::test_ac18_no_concrete_rule_family_module_in_package`
  asserts no `mislabel.py` exists in `segqc/heuristics/` (its `forbidden_stems`
  set is `{"mislabel", "misalignment"}` after item 032 removed `"overlap"`).
  Landing this module makes that assertion fail, so **`"mislabel"` must be removed
  from that set** — the same established precedent by which `bounds` /
  `fragmentation` / `coverage` / `sequence` / `border` / `overlap` were removed as
  each family landed. This item creates a single `mislabel.py` module (no
  `misalignment.py`), so `"misalignment"` may remain in the set harmlessly. The
  **test-writer** handles this edit (this spec author writes no tests).

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/mislabel.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, and `Severity` from `segqc.verdict`.
   - Define stable, testable reason-tag constants, e.g.
     `_MISALIGN_TAG = "Vertebra misaligned from spinal curve:"` and
     `_MISLABEL_TAG = "Vertebra ordering inconsistent with label:"`, and a default
     threshold constant `_DEFAULT_MAX_OFFSET_MM = 15.0`.
   - Reuse the sibling `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}`
     lookup and a `_severity_from_param(label) -> Severity` helper that raises
     `ValueError` on an unrecognised label (mirror `sequence.py` / `border.py`).
   - Add a `_label_for_level(per_label, level_name) -> Optional[int]` helper that
     scans `per_label` values for a matching `level_name` (mirror
     `sequence.py::_label_for_level`); returns `None` when `per_label` is not a
     mapping or no entry matches.

2. **Implement `class MislabelRule(Rule)`** with `rule_id = "mislabel"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read `severity` once via `_severity_from_param(config.rule_param("mislabel",
     "severity", default="flagged-for-review"))` (raises on a bad string before any
     per-record processing — AC16). Read
     `max_offset = float(config.rule_param("mislabel", "max_offset_mm",
     default=_DEFAULT_MAX_OFFSET_MM))`,
     `flag_offset = bool(config.rule_param("mislabel", "flag_offset_outliers",
     default=True))`, and
     `flag_order = bool(config.rule_param("mislabel", "flag_order_inconsistency",
     default=True))`.
   - Read `stage3 = record.get("stage3")`; treat a non-dict as `{}`.
   - **Detector A (if `flag_offset`):** read
     `offsets = stage3.get("per_label_offsets")`; if not a list, skip. Build a
     normalised working list of `(label, level_name, offset_mm)` — skip an entry
     that is not a mapping or is missing `label`; coerce `label = int(...)`,
     `offset = float(entry.get("offset_mm", 0.0) or 0.0)`, `name =
     entry.get("level_name")`. Sort by `label` ascending. For each with
     `offset >= max_offset`, append a `Finding(rule_id="mislabel",
     severity=severity, reason=f"{_MISALIGN_TAG} label {label} ({name}) centroid
     lies {offset:.1f} mm off the fitted spinal curve (threshold {max_offset:.1f}
     mm).", labels=frozenset({label}))`.
   - **Detector B (if `flag_order`):** read `mono = stage3.get(
     "monotonic_consistency")`; treat a non-dict as `{}`. Read
     `pairs = mono.get("non_monotonic_pairs")`; if not a list, skip. Read
     `per_label = record.get("per_label") or {}`. Build a normalised working list:
     for each `pair` that is a two-element sequence, read `level_a, level_b`;
     resolve `la = _label_for_level(per_label, level_a)` and `lb =
     _label_for_level(per_label, level_b)`. Sort by `(level_a, level_b)` name
     tuple. For each, append a `Finding(rule_id="mislabel", severity=severity,
     reason=f"{_MISLABEL_TAG} labels {la} ({level_a}) and {lb} ({level_b}) are out
     of expected order along the spine (spline parameter does not advance).",
     labels=frozenset({x for x in (la, lb) if x is not None}))`. (Use each level's
     resolved integer in the reason where available; keep the name always present.)
   - Return the concatenation **offset findings first, then order findings**.
     **Do not mutate** `record`, `stage3`, or any nested container (AC20): only
     read, and build fresh `Finding`s.

3. **Register the rule:** decorate `MislabelRule` with `@register_rule`.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import mislabel  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds`,
   `fragmentation`, `coverage`, `sequence`, `border`, and `overlap` imports, so
   importing `segqc.heuristics` makes the `mislabel` rule discoverable via the
   registry/runner. (Optionally update the package docstring's "no concrete rule
   family … mislabel …" wording — it is prose, not asserted.)

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `feature_report.py`, any `segqc.features.*` module, or any extractor. All
   parameters flow through the existing `rule_enabled` / `rule_param` accessors.

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_033_mislabel.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering `MislabelRule`
  does not leak across tests and re-registration does not raise a duplicate-id
  error (mirror `tests/test_032_overlap.py` / `test_031_border_partial_vertebra.py`).
- **Record fixtures:** build minimal per-case records by hand matching the
  `build_features_block` shape — a top-level `per_label` dict plus a `stage3`
  sub-dict carrying `per_label_offsets` (list) and `monotonic_consistency`
  (`{"non_monotonic_pairs": [...], "is_monotonic": bool, "u_values": [...]}`) —
  rather than running the full extractor stack (the rule reads only these fields).
  Provide small helpers: one to assemble an offset entry from
  `(label, offset_mm, level_name)`, one to assemble a `per_label` map from
  `{label: level_name}`, and one to assemble a record from offsets + pairs +
  per_label. Use the default convention's integer labels where attribution is
  asserted (e.g. `T12 == 19`, `L1 == 20`, `L2 == 21`). Fixtures:
  - **well-aligned** — small offsets, `non_monotonic_pairs == []` — AC2;
  - **displaced** — one offset entry `(20, 41.3, "L1")` above threshold, no pairs
    — AC3, AC4, AC5;
  - **threshold offset** — a `19.9`-mm and a `20.0`-mm entry under
    `max_offset_mm == 20.0` — AC6; a `3.0`-mm and a `40.0`-mm entry under
    `default_config()` — AC7;
  - **multi-offset** — three above-threshold entries with labels `21`, `19`, `20`
    fed unsorted — AC11;
  - **swapped pair** — one `non_monotonic_pairs` entry `["L1","L2"]`, `per_label`
    mapping both names, offsets below threshold — AC8, AC9, AC10;
  - **multi-pair** — `[["T12","L1"], ["L1","L2"]]` fed reversed — AC12;
  - **both detectors** — one above-threshold offset **and** one non-monotonic
    pair, toggled via `flag_offset_outliers` / `flag_order_inconsistency` — AC13,
    AC14;
  - **field-isolation** — two records with identical offsets / monotonic /
    per_label but different `overlaps` / `relationships` / `spacing_consistency` /
    geometry mm fields — AC19;
  - **degenerate records** — `stage3` absent / `None` / non-dict;
    `per_label_offsets` absent / `None` / non-list; `monotonic_consistency` absent
    / non-dict; `non_monotonic_pairs` non-list; an offset entry missing
    `offset_mm`; an offset entry missing `label`; a pair that is not a two-element
    sequence; `per_label` absent (unresolvable name) — AC18.
- **Config fixtures:** `default_config()` for the defaults path (AC2, AC7, AC15);
  an in-process `HeuristicConfig` (or `load_config` on a temp YAML) with a
  `max_offset_mm` override (AC6), `severity` overrides (AC15), a
  `flag_offset_outliers`/`flag_order_inconsistency` toggle (AC13, AC14), and an
  invalid `severity` string (AC16).
- **Coverage map:** one focused test per AC1–AC20 above.
- **Adversarial / edge cases:**
  - Determinism: two `run_rules` calls return equal lists; offset findings appear
    in ascending label order, order findings in ascending name-pair order, offset
    findings before order findings (AC17, AC11, AC12).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC20).
  - Inclusive-threshold boundary: an offset exactly equal to `max_offset_mm` fires
    (AC6).
  - Unresolvable Detector B name: a pair whose level name is absent from
    `per_label` still emits a finding naming the level, with that member omitted
    from `labels` (AC18).
  - `ValueError` on bad severity raised even for a `stage3`-less record (AC16).
- **Item-026 guard edit (test-writer):** remove `"mislabel"` from the
  `forbidden_stems` set in
  `tests/test_026_rule_engine_core.py::test_ac18_no_concrete_rule_family_module_in_package`
  so that guard passes once `mislabel.py` lands — the same edit made when `bounds`
  / `fragmentation` / `coverage` / `sequence` / `border` / `overlap` landed.
  `"misalignment"` may stay in the set (no `misalignment.py` module is created).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027 / 028 / 029 / 030 / 031 / 032** — sibling rule families, the
    canonical pattern this item mirrors (registration, `_severity_from_param`,
    reason tag, deterministic ordering, no record mutation, label attribution,
    name→label resolution via `per_label`).
  - **Item 018** — per-vertebra spline offset (`compute_spline_offsets`,
    `VertebralSplineOffset`); supplies `offset_mm`, the Detector A signal.
  - **Item 020** — neighbour-consistency / monotonic-progression metrics
    (`compute_monotonic_consistency`, `MonotonicConsistency`); supplies
    `non_monotonic_pairs`, the Detector B signal.
  - **Item 014** — inter-vertebra relationships / centroid ordering
    (`compute_spine_relationships`); the ordered centroid sequence that item 020's
    monotonic metric is evaluated against (the combined ordering signal).
  - **Item 016 / 022** — `build_features_block` and the `spline_offset_to_dict` /
    `monotonic_consistency_to_dict` converters; assemble the record's
    `stage3.per_label_offsets`, `stage3.monotonic_consistency`, and `per_label`
    fields the rule reads.
  - **Item 004** — label convention; defines the integer labels / anatomical names
    the offset entries and `per_label` carry (the rule reads them from the record).
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.mislabel` config and the
    §6-mode-1 / mode-4 end-to-end tests.

This item is **parallel-independent** of the other rule families (027–032); they
share only the already-merged item-026 interface.

## Decisions & Trade-offs

- Implemented as a single `src/segqc/heuristics/mislabel.py` module with
  `MislabelRule(Rule)` (`rule_id = "mislabel"`), registered via
  `@register_rule` and imported from `segqc/heuristics/__init__.py` alongside
  the other rule families, exactly mirroring the item 027–032 pattern.
- Detector A (`_detect_offset_outliers`) and Detector B
  (`_detect_order_inconsistency`) are implemented as static helper methods on
  the rule class rather than free functions, to keep the shared `severity`
  read-once-up-front logic in `evaluate` and the two detectors clearly
  scoped; both re-sort their normalised working lists defensively so output
  never depends on caller input order (AC11, AC12, AC17).
- Reused the sibling `_LABEL_TO_SEVERITY` / `_severity_from_param` helper
  verbatim (mirroring `border.py` / `sequence.py`) and a `_label_for_level`
  helper identical to `sequence.py`'s, to resolve Detector B's level names to
  integer labels via `per_label`.
- `stage3` is normalised to `{}` once in `evaluate` (non-dict treated as
  absent) and passed to both detector helpers; each detector independently
  re-validates its own sub-fields (`per_label_offsets` a list,
  `monotonic_consistency` a dict, `non_monotonic_pairs` a list) so a
  malformed field in one sub-block cannot suppress the other detector.
- Detector B's `labels` frozenset always excludes `None` (an unresolved
  name), and the reason interpolates the raw resolved label (`la`/`lb`,
  which is `None` when unresolved) alongside the level name string, so an
  unmappable name is never silently dropped from the reason even though it
  is absent from `labels` (AC18).
- No changes were needed to `config.py`, `rule.py`, `runner.py`,
  `finding.py`, `feature_report.py`, or any extractor — all parameters flow
  through the existing `rule_param` accessor with in-line defaults
  (`flagged-for-review`, `15.0`, `True`, `True`).
- Left the package docstring's item-range prose in `segqc/heuristics/__init__.py`
  as-is (a pre-existing "027–035" reference unrelated to this item's own
  concrete-family list, which already named `mislabel`); this is prose only,
  not asserted by any test, so it was not touched to avoid an out-of-scope
  edit.
