# Item 031 — Border-Partial-Vertebra Rule

> **Created:** 2026-07-03 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 031
> **Objectives:** G2 (detect §6 failure modes — mode 6, *partial vertebra at the
> image border whose appearance is truncated by the field of view*), supporting
> G4 (per-case reasons + offending labels)
> **Suggested branch:** `aide/031-border-partial-vertebra-rule`

---

## Description

Implement a **border-partial-vertebra rule** for the Stage 4 heuristic rule
engine that consumes the pre-computed per-label **image-border-contact flags**
(item 011, exposed under each `per_label` entry's `geometry` sub-block) to detect
**§6 failure mode 6 — a partial vertebra at the image border whose appearance is
truncated by the field of view (FOV)**. The rule plugs into the item-026 engine
core exactly like the sibling bounds (item 027), fragmentation (item 028),
coverage (item 029), and sequence (item 030) rules: it subclasses
`segqc.heuristics.Rule`, registers itself via `register_rule`, reads its severity
from the versioned config through `config.rule_param`, and emits
`segqc.heuristics.Finding` objects through the standard runner. It follows every
convention those siblings pinned — per-case determinism, a fixed output order,
default severity `FLAG` (config-overridable), an unrecognised severity string
raising `ValueError`, and **never mutating** the input record.

### The signal this rule consumes

Item 011 computes, per label, six boolean **border-contact flags** — one per face
of the image volume — serialised by `geometry_to_dict` (item 016) into each
`per_label` entry's `geometry` sub-block:

```
record["per_label"] : { "<label_int>": {
    "label":      int,                        # integer segmentation label
    "level_name": str,                        # maps a label to its anatomical level
    "geometry": {
        "touches_superior":  bool,            # x == shape[0]-1  (cranio-caudal / FOV top)
        "touches_inferior":  bool,            # x == 0           (cranio-caudal / FOV bottom)
        "touches_left":      bool,            # y == 0           (in-plane)
        "touches_right":     bool,            # y == shape[1]-1  (in-plane)
        "touches_anterior":  bool,            # z == 0           (in-plane)
        "touches_posterior": bool,            # z == shape[2]-1  (in-plane)
        ...                                   # extent/volume/bbox fields — NOT read here
    },
    ...
} }
record["relationships"] : {                   # item 014, or None
    "present_levels": [str, ...],             # canonical head-to-tail order of present levels
    ...                                       # other fields not read here
}
```

Per item 011's documented axis convention, the **cranio-caudal (superior /
inferior)** axis is the one along which the spine runs, so `touches_superior` /
`touches_inferior` are the **FOV-end** faces — the axis the scan's field of view
is truncated along. The other four (`touches_left` / `touches_right` /
`touches_anterior` / `touches_posterior`) are the **in-plane** faces. A vertebra
touching any face has voxels on the boundary of the image volume, i.e. its
segmentation is (potentially) cut off by the FOV.

The rule reads **only** these boolean flags plus `present_levels` (to decide
whether a border-touching vertebra is a terminal one). It never reads any mm /
spacing / extent / volume field, so it is **inherently spacing-agnostic**.

### What the rule does

For each label the rule inspects its `geometry` border-contact flags and, when
one or more faces are touched, classifies the truncation as **expected** or
**unexpected**, then emits **at most one** label-attributed `Finding`
(`rule_id == "border"`) per label according to a config-driven policy:

- **Expected FOV-end truncation** — a border touch on **only** the cranio-caudal
  end face(s), where each touched end face is consistent with the vertebra being
  the terminal one at that end of the present-level span:
  - `touches_superior` is expected **only** for the **superior-most** present
    level (`relationships.present_levels[0]`);
  - `touches_inferior` is expected **only** for the **inferior-most** present
    level (`relationships.present_levels[-1]`).
  The scan must start and end somewhere along the spine, so the topmost and
  bottommost segmented vertebrae legitimately touch the FOV ends. This is
  **suppressed by default** (no finding) — mirroring item 029's coverage rule,
  which likewise *border-suppresses* an expected FOV truncation rather than
  flagging it. It can be surfaced for audit via `report_expected_ends`.

- **Unexpected clipping** — anything else: a touch on **any in-plane** face
  (`left` / `right` / `anterior` / `posterior`, always abnormal — a vertebra
  should never run out of the axial slice FOV), **or** a cranio-caudal end touch
  on a **mid-spine** vertebra (one that is neither the superior-most nor
  inferior-most present level), **or** a superior touch on the inferior-end
  vertebra (and vice versa). This is a genuine QC concern and emits **one**
  `Finding` at the configured `severity` (default `FLAG`), naming the offending
  label and the touched faces in the `reason`.

Findings are **label-attributed** (non-empty `labels` frozenset carrying the
offending vertebra's **integer** label), in deliberate contrast to item 029's
*missing-level* findings, which are case-level (empty frozenset) because an absent
vertebra has no integer label. A border-touching vertebra is **present** and
carries a real integer label. Targets **§6 failure mode 6**.

### Scope boundary — what this item is **not**

- **Not missing-level / coverage detection.** Whether the FOV *should* have
  captured additional vertebrae beyond the span ends is **§6 mode 5 / item 029**
  (already merged), which reads `missing_levels` / `expected_levels`. This rule
  reads only the per-label border flags and `present_levels`; it never reads
  `missing_levels` and never asserts a vertebra is missing.
- **Not sequence continuity.** Ordering reversals / non-anatomical jumps are
  **§6 mode 7 / item 030**.
- **Not geometric mislabel / misalignment.** Centroid outliers, spline offsets,
  and neighbour-spacing consistency are **§6 modes 1 & 4 / item 033**.
- **Not verdict aggregation.** Combining findings into a `pass` / `flag` / `fail`
  verdict is **item 034**.
- **Not the shipped default config file.** Item 035 ships the documented YAML;
  here the defaults live as `rule_param` fallbacks.
- Does **not** recompute geometry, border flags, or relationships — it only
  *consumes* the `geometry` border-contact flags (item 011) and per-case
  `relationships.present_levels` (item 014) already assembled by
  `build_features_block` (item 016). It does not touch the item-026 engine core,
  `config.py`, `verdict.py`, or any extractor.

### Config shape (read via `config.rule_param`)

```yaml
rules:
  border:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review — severity of unexpected-clip findings
      report_expected_ends: false       # optional; default false — also emit a finding for an EXPECTED FOV-end truncation
      end_severity: pass                # optional; default pass — severity used for expected-end findings (only when report_expected_ends is true)
```

Border contact is a **structural / boolean** property, so the rule ships **no**
numeric thresholds. An absent `rules.border` section leaves the rule fully
operational: it flags any unexpected clip at the default `FLAG` severity and
suppresses expected FOV-end truncations.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "border"`.**
      Importing `segqc.heuristics` makes a `BorderRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("border")`
      returns the registered instance and `border` appears in `iter_rules()`.

- [ ] **AC2: No finding for a fully-interior label.**
      For a record whose single `per_label` entry has all six `geometry`
      `touches_*` flags `False`, under `default_config()`, `evaluate` returns
      `[]` — no border finding.

- [ ] **AC3: A finding fires for a label touching the volume boundary.**
      Given a `per_label` entry with `geometry.touches_left == True` (an in-plane
      face), the rule emits exactly **one** `Finding` with `rule_id == "border"`.

- [ ] **AC4: The offending vertebra is attributed by its integer label.**
      For a border-touching entry whose `label == 20`, the emitted finding's
      `labels == frozenset({20})` (label-attributed, **not** an empty case-level
      frozenset).

- [ ] **AC5: An expected superior FOV-end truncation is suppressed by default.**
      For a record whose superior-most present level (`present_levels[0]`) is the
      only present vertebra flagged, touching **only** `touches_superior`, under
      `default_config()`, `evaluate` returns `[]` — no finding.

- [ ] **AC6: An expected inferior FOV-end truncation is suppressed by default.**
      For a record whose inferior-most present level (`present_levels[-1]`) is
      flagged touching **only** `touches_inferior`, under `default_config()`,
      `evaluate` returns `[]` — no finding.

- [ ] **AC7: A mid-spine cranio-caudal clip IS flagged.**
      For a vertebra that is **neither** `present_levels[0]` **nor**
      `present_levels[-1]` and touches `touches_superior` (or `touches_inferior`),
      the rule emits exactly **one** `border` finding naming that label — an
      unexpected clip.

- [ ] **AC8: An in-plane clip on a terminal vertebra is still flagged.**
      For the superior-most present level touching **both** `touches_superior`
      **and** `touches_left`, the rule emits **one** `border` finding (the
      in-plane contact makes the truncation unexpected even though the vertebra is
      at the FOV end).

- [ ] **AC9: `report_expected_ends` surfaces expected end truncations.**
      For the AC5 record, with `rules.border.params.report_expected_ends == true`,
      the rule emits exactly **one** `border` finding for that terminal vertebra
      at `end_severity` (default `Severity.PASS`), attributed to its integer
      label.

- [ ] **AC10: Multiple border-touching labels each yield one finding, in
      ascending integer-label order.** Given three `per_label` entries — two with
      an unexpected clip (labels `21`, `19`) and one interior — the rule emits
      exactly **two** findings, ordered by ascending integer label (`19` before
      `21`), one per offending label.

- [ ] **AC11: Default severity is `FLAG`, and severity is config-driven.**
      With no `severity` param, an unexpected-clip finding has `severity ==
      Severity.FLAG`. With `rules.border.params.severity` set to `fail`, the
      emitted finding has `severity == Severity.FAIL`.

- [ ] **AC12: An unrecognised `severity` string raises `ValueError`.**
      If `rules.border.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, `"fail"`), `evaluate` raises
      `ValueError` immediately (before any per-record processing).

- [ ] **AC13: The rule is deterministic.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return
      equal finding lists in the same order.

- [ ] **AC14: The rule is spacing-agnostic.**
      Two records that carry identical `touches_*` flags but differ in every
      mm / spacing / extent / volume `geometry` field yield **identical** finding
      lists (equal `rule_id`, `severity`, `labels`, and `reason`) — the rule
      reads only the boolean border flags.

- [ ] **AC15: The rule tolerates degenerate / malformed records.**
      `evaluate` returns a list and raises nothing when: `per_label` is empty or
      absent; a `per_label` entry has no `geometry` sub-block (that entry
      contributes no finding); `record["relationships"]` is `None`/absent or
      `present_levels` is empty (a border-touching label is then treated as
      **unexpected** — the distinction is unavailable, so the contact is surfaced
      rather than hidden — with no crash).

- [ ] **AC16: The rule does not mutate the input record.**
      Calling `evaluate(record, config)` leaves `record` (including every nested
      `per_label` entry, `geometry` sub-block, and `relationships` list)
      unchanged — verified by deep equality against a pre-call copy.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **Border contact is read from `geometry.touches_{superior,inferior,left,right,
  anterior,posterior}` (item 011), not re-derived.** Pinned interface (via
  `geometry_to_dict`, item 016): each `per_label` entry carries a `geometry`
  sub-dict exposing these six booleans, plus a `level_name` and integer `label`.
  If that shape diverged, the builder/validator hands back.
- **Cranio-caudal = FOV-end axis; the other four faces are in-plane.** Per item
  011's documented axis convention (`x` → superior/inferior, `y` → left/right,
  `z` → anterior/posterior), the superior/inferior faces are where the scan's FOV
  is legitimately truncated along the spine, while an in-plane touch (left/right/
  anterior/posterior) is always abnormal clipping. This physical interpretation
  drives the expected-vs-unexpected split. If a project's orientation convention
  differs, the classification (not the mechanism) would need revisiting — recorded
  here for the validator.
- **Expected FOV-end truncation is suppressed by default; unexpected clips always
  flag.** The queue asks the rule to distinguish "an expected first/last-in-FOV
  truncation from a mid-spine label unexpectedly clipped." Since the topmost /
  bottommost segmented vertebra touching the FOV end is unavoidable and normal
  (it would false-flag every ground-truth scan, breaking item 035's
  *GT-fixture-passes* acceptance), the defensible default under clarify=`assume`
  is to **suppress** the expected case — exactly as item 029's coverage rule
  *border-suppresses* an expected FOV truncation rather than emitting it. A
  `report_expected_ends` toggle (default `false`) can surface expected-end
  truncations at a separate `end_severity` (default `pass`) for audit. This is the
  most material assumption; the validator surfaces it at the queue boundary.
- **Terminal-position is decided from `relationships.present_levels` (item 014):**
  a vertebra is the superior end iff its `level_name == present_levels[0]` and the
  inferior end iff its `level_name == present_levels[-1]`. When `relationships` is
  `None`/absent or `present_levels` is empty (which, per item 016, coincides with
  a zero-label map where `per_label` is also empty), the terminal distinction is
  **unavailable**; any border-touching label is then classified **unexpected**
  (surface rather than hide). In practice a non-empty `per_label` always carries a
  populated `present_levels`.
- **Findings are label-attributed (non-empty `labels`).** A border-touching
  vertebra is *present* and carries an integer label, so — unlike item 029's
  *absent*-level findings (case-level, empty frozenset) — this rule attaches the
  offender's integer label, read from the entry's `label` field.
- **One finding per offending label**, emitted in ascending integer-label order
  (sorted `per_label` keys) for determinism; each finding names the touched faces
  in a fixed face order in its `reason`.
- **Default severity is `flagged-for-review` (`Severity.FLAG`)**, matching the
  sibling rules (items 027–030); overridable via `severity`, with an unrecognised
  string raising `ValueError`. Border contact is boolean/structural, so the rule
  ships **no** numeric thresholds. `end_severity` is validated only when
  `report_expected_ends` is `true` (an unused, malformed `end_severity` on the
  default path does not raise).
- **The rule never mutates the input record** — it only reads and builds fresh
  `Finding`s.

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/border.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, and `Severity` from `segqc.verdict`.
   - Define module constants for the two axis groups and the reason tags, so they
     are stable and testable, e.g.
     `_END_FACES = ("touches_superior", "touches_inferior")`,
     `_IN_PLANE_FACES = ("touches_left", "touches_right", "touches_anterior",
     "touches_posterior")`, `_ALL_FACES = _END_FACES + _IN_PLANE_FACES` (fixed
     iteration order for the `reason` face list),
     `_UNEXPECTED_CLIP_TAG = "Partial vertebra clipped by FOV:"`,
     `_EXPECTED_END_TAG = "Partial vertebra at FOV end (expected):"`.
   - Reuse the sibling `_LABEL_TO_SEVERITY = {sev.label: sev for sev in Severity}`
     lookup and a `_severity_from_param(label) -> Severity` helper that raises
     `ValueError` on an unrecognised label (mirror `coverage.py`).

2. **Implement `class BorderRule(Rule)`** with `rule_id = "border"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read `severity` once via `_severity_from_param(config.rule_param("border",
     "severity", default="flagged-for-review"))` (raises on a bad string before
     any per-record processing — AC12). Read `report_expected_ends =
     bool(config.rule_param("border", "report_expected_ends", default=False))`.
   - Read `per_label = record.get("per_label") or {}`; if not a mapping or empty,
     return `[]` (AC15). Read `rel = record.get("relationships")`;
     `present_levels = list(rel.get("present_levels") or [])` when `rel` is a
     mapping, else `[]`. Compute `superior_end = present_levels[0] if
     present_levels else None` and `inferior_end = present_levels[-1] if
     present_levels else None`.
   - Iterate `per_label` entries in **ascending integer-label order** (sort by
     `int(key)`; fall back to the entry's `label`). For each entry:
     - `geom = entry.get("geometry") or {}`; `touched = [f for f in _ALL_FACES if
       bool(geom.get(f))]`. If `touched` is empty, continue (interior — AC2).
     - `level_name = entry.get("level_name")`;
       `is_sup_end = level_name is not None and level_name == superior_end`;
       `is_inf_end = level_name is not None and level_name == inferior_end`.
     - `in_plane = any(f in _IN_PLANE_FACES for f in touched)`.
       Compute `expected`: `True` iff `not in_plane` **and** (`"touches_superior"
       not in touched or is_sup_end`) **and** (`"touches_inferior" not in touched
       or is_inf_end`). (Since `touched` is non-empty and not in-plane, at least
       one end face is present — so `expected` implies a consistent terminal
       touch.)
     - `label_int = int(entry.get("label", key))`;
       `faces_text = ", ".join(f.removeprefix("touches_") for f in touched)`.
     - If **not** `expected`: append `Finding(rule_id="border",
       severity=severity, reason=f"{_UNEXPECTED_CLIP_TAG} label {label_int}
       ({level_name}) touches image face(s): {faces_text}.",
       labels=frozenset({label_int}))`.
     - Else (`expected`): if `report_expected_ends`, resolve `end_severity =
       _severity_from_param(config.rule_param("border", "end_severity",
       default="pass"))` (validated here, only on this path — AC9) and append a
       `Finding` tagged `_EXPECTED_END_TAG` at `end_severity`, same label
       attribution; otherwise emit nothing (AC5, AC6).
   - Return the accumulated list. **Do not mutate** `record`, `per_label`, any
     entry, `geom`, or `rel` (AC16): only read, and build fresh `Finding`s.

3. **Register the rule:** decorate `BorderRule` with `@register_rule`.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import border  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds`,
   `fragmentation`, `coverage`, and `sequence` imports, so importing
   `segqc.heuristics` makes the `border` rule discoverable via the
   registry/runner.

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `geometry.py`, `feature_report.py`, or any extractor. All parameters flow
   through the existing `rule_enabled` / `rule_param` accessors.

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_031_border_partial_vertebra.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering `BorderRule`
  does not leak across tests and re-registration does not raise a duplicate-id
  error (mirror `tests/test_030_sequence_continuity.py`).
- **Record fixtures:** build minimal per-case records by hand matching the
  `build_features_block` shape — a `per_label` map whose entries carry `label`,
  `level_name`, and a `geometry` sub-dict of the six `touches_*` booleans, plus a
  `relationships` sub-dict carrying `present_levels` — rather than running the
  full extractor stack (the rule reads only those fields). Provide a small helper
  to assemble an entry from `(label, level_name, touched_faces, **other_geom)` and
  a record from `(present_levels, entries)`; default all six flags to `False` and
  set only the named touched faces. Use the default convention's integer labels
  where attribution is asserted (e.g. `T12 == 19`, `L1 == 20`, `L2 == 21`).
  Fixtures:
  - **fully interior** — all flags `False` — AC2;
  - **in-plane clip** — `touches_left == True` on some label — AC3, AC4;
  - **expected superior end** — `present_levels[0]` touching only
    `touches_superior` — AC5;
  - **expected inferior end** — `present_levels[-1]` touching only
    `touches_inferior` — AC6;
  - **mid-spine axial clip** — a non-terminal level touching `touches_superior`
    — AC7;
  - **terminal + in-plane** — `present_levels[0]` touching `touches_superior` and
    `touches_left` — AC8;
  - **expected end + report toggle** — the AC5 record with
    `report_expected_ends == true` — AC9;
  - **mixed multi-label** — two unexpected clips (labels `21`, `19`) plus one
    interior label, asserting ascending-label ordering and one finding per
    offender — AC10;
  - **spacing pair** — two records with identical `touches_*` flags but different
    `physical_volume_mm3` / `extent_*_mm` / bbox values — AC14;
  - **degenerate records** — empty / absent `per_label`; an entry with no
    `geometry`; `relationships` `None`/absent and empty `present_levels` with a
    border-touching label — AC15.
- **Config fixtures:** `default_config()` for the defaults path (AC2, AC5, AC6,
  AC11); an in-process `HeuristicConfig` (or `load_config` on a temp YAML) with a
  `severity` override (AC11), `report_expected_ends: true` + `end_severity`
  (AC9), and an invalid `severity` string (AC12).
- **Coverage map:** one focused test per AC1–AC16 above.
- **Adversarial / edge cases:**
  - A terminal vertebra touching the **opposite** end face (superior-most level
    touching `touches_inferior`) is flagged **unexpected** (mid/opposite-end
    inconsistency) — reinforces AC7's classification.
  - An entry whose `geometry` is present but every flag `False` produces no
    finding even amid other flagged labels (interior amid clipped) — AC2 / AC10.
  - Determinism: two `run_rules` calls return equal lists; findings appear in
    ascending integer-label order (AC13, AC10).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC16).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027 / 028 / 029 / 030** — sibling rule families, the canonical pattern
    this item mirrors (registration, `_severity_from_param`, reason tag,
    deterministic ordering, no record mutation, label attribution). Item 029 in
    particular pins the border-suppression precedent this rule follows.
  - **Item 011** — per-label geometry; supplies the six `touches_*`
    border-contact flags (the signal this rule consumes) under each entry's
    `geometry` sub-block.
  - **Item 014** — inter-vertebra relationships; supplies
    `relationships.present_levels` (canonical head-to-tail order) used to identify
    the terminal (first/last-in-FOV) vertebrae, via `relationships_to_dict`
    (item 016).
  - **Item 016** — `build_features_block` / `geometry_to_dict` /
    `relationships_to_dict`; assembles the per-case record shape (`per_label` with
    `label` + `level_name` + `geometry`, and `relationships`) the rule reads.
  - **Item 004** — label convention; defines the integer labels the offending
    vertebrae carry (`per_label` carries them, so the rule reads them from the
    record rather than importing the convention).
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.border` config and the
    §6-mode-6 end-to-end test.

This item is **parallel-independent** of the other rule families (027–030, 032,
033); they share only the already-merged item-026 interface.

## Decisions & Trade-offs

To be updated during implementation.

Initial design decisions carried from this spec (confirm or revise during
implementation):

- **Cranio-caudal touches are FOV-end truncation; in-plane touches are always
  abnormal.** The expected-vs-unexpected split rests on item 011's axis
  convention (superior/inferior = the axis the FOV is truncated along). An
  in-plane clip (left/right/anterior/posterior) is unconditionally flagged.
- **Suppress expected FOV-end truncations by default; flag everything else.**
  Flagging the topmost/bottommost vertebra of every scan would false-flag every
  ground-truth case and break item 035's *GT-passes* acceptance; suppression
  matches item 029's border-suppression precedent. `report_expected_ends` (with a
  separate `end_severity`) preserves auditability without polluting the default
  verdict.
- **Findings are label-attributed (non-empty `labels`), unlike item 029.** A
  border-touching vertebra is present and carries an integer label, giving the
  item-034 aggregator a concrete per-vertebra offender — the deliberate contrast
  with item 029's case-level missing-level findings.
- **One finding per offending label**, in ascending integer-label order, rather
  than one case-level finding — each partial vertebra is an independent offender
  the report and verdict should attribute individually.
- **No numeric thresholds.** Border contact is boolean; `severity`,
  `report_expected_ends`, and `end_severity` are the only params.
