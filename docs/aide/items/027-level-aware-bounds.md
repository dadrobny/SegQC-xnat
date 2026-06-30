# Item 027 — Level-Aware Min/Max Bounds Rules (Volume & Extent)

> **Status:** 📋 Planned · **Created:** 2026-06-30
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 027
> **Objectives:** G2 (detect §6 failure modes — mode 2, gross over-/under-segmentation),
> supporting G4 (per-case reasons + offending labels)
> **Suggested branch:** `aide/027-level-aware-bounds`

---

## Description

Implement the **first concrete rule family** for the Stage 4 heuristic rule
engine: a **level-aware min/max bounds rule** over per-label **physical volume**
and **physical extent (x/y/z)**. It plugs into the item-026 engine core by
subclassing `segqc.heuristics.Rule`, registering itself via `register_rule`, and
emitting `segqc.heuristics.Finding` objects through the standard runner.

For each present vertebra label the rule:

1. resolves the label's **anatomical level group** — *cervical* / *thoracic* /
   *lumbar* — from its `level_name` (which the feature record already derives via
   the item-004 label convention);
2. looks up the **level-aware bounds** for that group from the heuristic config
   section `rules.bounds.params.<group>`, falling back to **shipped hand-set
   defaults** baked into this module when a config key is absent;
3. compares the label's **physical** measurements — `physical_volume_mm3`,
   `extent_x_mm`, `extent_y_mm`, `extent_z_mm` (so anisotropic spacing is
   respected; voxel counts are *not* used for the comparison) — against the
   group's `min_*` / `max_*` bounds;
4. emits one `Finding` **per violated metric per label**, carrying the offending
   label, a human-readable reason naming the level, the metric, and the measured
   value vs the expected range, at a configurable severity (default
   `flagged-for-review`).

Targets **§6 failure mode 2** (gross over-/under-segmentation: a fused vertebra
is grossly oversized, a fragmented or clipped one grossly undersized).

### What this item is **not**

- Not reference-derived bounds — those come from VerSe in **Stage 6 / item 006**.
  Item 027 ships **hand-set** placeholder bounds only.
- Not verdict aggregation — combining findings into a `pass`/`flag`/`fail`
  verdict is **item 034**.
- Not the shipped default config **file** — item 035 ships the documented YAML;
  here the defaults live as Python constants used as `rule_param` fallbacks.
- Does not modify the item-026 engine core, `config.py` schema, `verdict.py`, or
  the feature extractors. It only *consumes* their public APIs.

### The feature record this rule consumes

The per-case record passed to `evaluate(record, config)` is the
`build_features_block` dict (item 016). This rule reads only:

```
record["per_label"] : { "<label_int>": {
    "label": int,
    "level_name": str,            # e.g. "L1", "C3", "T13", "S", "unknown"
    "geometry": {
        "physical_volume_mm3": float,
        "extent_x_mm": float,
        "extent_y_mm": float,
        "extent_z_mm": float,
        "voxel_count": int,       # present but deliberately NOT used for bounds
        ...
    },
    ...
} }
```

### Level-group resolution

`level_name` strings come from `segqc.labels` (`CANONICAL_ORDER`): `C1..C7`
(cervical), `T1..T13` (thoracic), `L1..L6` (lumbar), plus `S`, `Cocygis`, and the
`unknown` sentinel. The rule maps a `level_name` to one of the three bounded
groups (`cervical` / `thoracic` / `lumbar`); any name not in those three groups
(`S`, `Cocygis`, `unknown`, or a custom-convention name) has **no bounds** and is
**skipped** (never flagged by this rule).

### Config shape (read via `config.rule_param`)

```yaml
rules:
  bounds:
    enabled: true                       # honoured by the runner (item 026)
    params:
      severity: flagged-for-review      # optional; default flagged-for-review
      cervical:
        min_volume_mm3: <float>
        max_volume_mm3: <float>
        min_extent_x_mm: <float>
        max_extent_x_mm: <float>
        min_extent_y_mm: <float>
        max_extent_y_mm: <float>
        min_extent_z_mm: <float>
        max_extent_z_mm: <float>
      thoracic: { ... same keys ... }
      lumbar:   { ... same keys ... }
```

Each group dict is read via `config.rule_param("bounds", "<group>",
default=DEFAULT_BOUNDS["<group>"])`; each individual bound key falls back to the
shipped default for that group when absent (per-key merge), so a **partial**
config override (e.g. only `lumbar.max_volume_mm3`) leaves the other bounds at
their defaults.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "bounds"`.**
      Importing `segqc.heuristics` makes a `BoundsRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("bounds")`
      returns the registered instance and `bounds` appears in `iter_rules()`.

- [ ] **AC2: No findings when every label is within its level-aware bounds.**
      For a feature record whose every per-label `physical_volume_mm3` and
      `extent_*_mm` lie inside the group's bounds, `run_rules(record, cfg)`
      returns **no** findings with `rule_id == "bounds"` (an empty list when
      `bounds` is the only rule).

- [ ] **AC3: An oversized volume fires a finding for the correct label and level.**
      Given a label whose `physical_volume_mm3` exceeds its group's
      `max_volume_mm3`, the rule emits a `Finding` with `rule_id == "bounds"`,
      `labels == frozenset({that_label})`, and a `reason` naming the label's
      `level_name` and the volume metric.

- [ ] **AC4: An undersized volume fires a finding for the correct label and level.**
      Given a label whose `physical_volume_mm3` is below its group's
      `min_volume_mm3`, the rule emits a `Finding` with
      `labels == frozenset({that_label})` and a `reason` naming the level and the
      volume metric.

- [ ] **AC5: An out-of-range extent fires a finding for the correct label.**
      Given a label whose `extent_x_mm` (or `_y_`/`_z_`) is above the group's
      `max_extent_*_mm` or below the `min_extent_*_mm`, the rule emits a `Finding`
      with `labels == frozenset({that_label})` whose `reason` names the offending
      extent axis.

- [ ] **AC6: Bounds are level-aware (the same measurement is judged per group).**
      A `physical_volume_mm3` value that lies **inside** the lumbar bounds but
      **above** the cervical `max_volume_mm3` produces a finding when carried by a
      cervical label and **no** finding when carried by a lumbar label (using the
      same config). This proves the rule selects bounds by the label's level.

- [ ] **AC7: Bounds are read from config and override the defaults.**
      With a config that sets `rules.bounds.params.<group>.max_volume_mm3` to a
      value tighter than the shipped default, a label that passes under the
      defaults now **fires**; with a config that loosens that bound, a label that
      fires under the defaults now **passes**. (Demonstrates the config value is
      used in preference to the built-in default.)

- [ ] **AC8: Shipped hand-set defaults apply when no config is supplied.**
      With `default_config()` (no `rules` section), a label whose volume is
      grossly larger than any plausible vertebra still **fires** a finding, and a
      label with an anatomically plausible volume does **not** — i.e. the rule's
      built-in default bounds are in effect without any config file.

- [ ] **AC9: Physical (mm) volume is used, not voxel count (anisotropy respected).**
      Two labels with the **same** `voxel_count` but different
      `physical_volume_mm3` are judged differently: the one whose
      `physical_volume_mm3` exceeds `max_volume_mm3` fires while the one whose
      `physical_volume_mm3` is in range does not — confirming the comparison keys
      off the physical (mm) field, so anisotropic spacing is respected.

- [ ] **AC10: Each finding's reason reports the measured value and expected range.**
      Every `bounds` finding has a non-empty `reason` string that contains the
      measured numeric value and the violated bound (min or max) for that metric,
      so a reader can see *what* was out of range and *by reference to which*
      limit.

- [ ] **AC11: Labels in unbounded groups are skipped.**
      A label whose `level_name` is `S`, `Cocygis`, or `unknown` (no bounds
      group) produces **no** `bounds` finding regardless of its volume/extent.

- [ ] **AC12: The default finding severity is `FLAG`, and severity is config-driven.**
      With no `severity` param, every `bounds` finding has
      `severity == Severity.FLAG`. With `rules.bounds.params.severity` set to
      `fail`, emitted findings have `severity == Severity.FAIL`.

- [ ] **AC13: The rule is deterministic.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return
      equal finding lists in the same order (findings ordered by ascending label,
      then by a fixed metric order).

- [ ] **AC14: The rule tolerates a label-free / empty record without crashing.**
      `evaluate` on a record whose `per_label` is empty (or absent) returns `[]`
      and raises nothing.

---

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/bounds.py`:**
   - Import `Rule`, `register_rule`, `Finding` from `segqc.heuristics` (or the
     submodules `rule` / `finding`) and `Severity` from `segqc.verdict`.
   - Define **level-group resolution**: a mapping from each `CANONICAL_ORDER`
     vertebra name to its group (`C* → "cervical"`, `T* → "thoracic"`,
     `L* → "lumbar"`; `S`, `Cocygis` → unbounded) and a helper
     `_level_group(level_name: str) -> Optional[str]` returning the group or
     `None` for unbounded / unknown names. Prefer building the map from
     `segqc.labels.CANONICAL_ORDER` so it stays in step with the convention.
   - Define **shipped hand-set defaults** `DEFAULT_BOUNDS: dict[str, dict[str,
     float]]` for `cervical` / `thoracic` / `lumbar`, each with the eight keys
     `min_volume_mm3`, `max_volume_mm3`, `min_extent_{x,y,z}_mm`,
     `max_extent_{x,y,z}_mm`. Pick conservative, clearly-documented placeholder
     ranges (wide enough that plausible vertebrae pass; tight enough that gross
     fusions/fragments fail). Comment that these are hand-set and superseded by
     reference-derived bounds in Stage 6.
   - Define a small list of metrics to check, each as
     `(record_field, min_key, max_key, human_name)` — e.g.
     `("physical_volume_mm3", "min_volume_mm3", "max_volume_mm3", "volume")`,
     and one entry per extent axis — so the comparison loop and the reason text
     are data-driven and ordered deterministically.

2. **Implement `class BoundsRule(Rule)`** with `rule_id = "bounds"` and
   `evaluate(self, record, config) -> list[Finding]`:
   - Read the optional severity once:
     `sev = _severity_from_param(config.rule_param("bounds", "severity",
     default="flagged-for-review"))`, mapping the label string back to a
     `Severity` member (reuse the same label→member lookup style as `Finding`),
     defaulting to `Severity.FLAG`.
   - Iterate `record.get("per_label", {})` in **ascending integer-label order**.
   - For each entry resolve `group = _level_group(entry["level_name"])`; if
     `None`, skip the label (AC11).
   - Read the group's bounds: start from `DEFAULT_BOUNDS[group]`, then overlay
     `config.rule_param("bounds", group, default={})` **per key** (config value
     wins where present; default fills the rest).
   - Read the label's `geometry` sub-dict; for each metric compare the measured
     value to `min`/`max`. On a violation, append a `Finding(rule_id="bounds",
     severity=sev, reason=<level + metric + measured vs limit>,
     labels=frozenset({label_int}))`. Emit **one finding per violated metric**
     (so a label out of range on both volume and an extent yields two findings).
   - Guard missing geometry keys defensively (skip a metric whose field is
     absent rather than raising) so a partially-populated record cannot crash the
     rule (AC14).
   - Return the aggregated list.

3. **Register the rule:** call `register_rule(BoundsRule)` at module import.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import bounds  # noqa: F401` to
   `src/segqc/heuristics/__init__.py` so importing `segqc.heuristics` makes the
   `bounds` rule discoverable via the registry/runner. (This is the first rule
   family, establishing the import-for-registration pattern items 028–033 follow.)

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`, or any
   feature extractor. All thresholds flow through the existing
   `rule_enabled` / `rule_param` accessors.

---

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_027_level_aware_bounds.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (import `segqc.heuristics.rule._RULES`, save and restore) so registering
  `BoundsRule` does not leak across tests, and re-registration does not raise a
  duplicate-id error.
- **Record fixtures:** build minimal `per_label` dicts by hand matching the
  `build_features_block` shape (a helper that takes `label`, `level_name`,
  `volume_mm3`, `extent_x/y/z_mm`, `voxel_count`), rather than running the full
  extractor stack — the rule only reads those fields. Provide:
  - an **all-in-bounds** record across cervical/thoracic/lumbar labels (AC2);
  - records with a single deliberately **oversized** and **undersized** label
    (AC3, AC4);
  - a record with an out-of-range **extent** (AC5);
  - a record carrying the **same** measured volume under a cervical vs a lumbar
    label (AC6);
  - two labels with **equal `voxel_count`** but different `physical_volume_mm3`
    (AC9);
  - labels with `level_name` in `{"S", "Cocygis", "unknown"}` (AC11);
  - an **empty** / `per_label`-absent record (AC14).
- **Config fixtures:** `default_config()` for the defaults path (AC8); a
  `HeuristicConfig` (constructed in-process or via `load_config` on a temp YAML)
  with a `rules.bounds.params.<group>` override (AC7), a `severity` override
  (AC12), and a partial override leaving other keys defaulted.
- **Coverage map:** one focused test per AC1–AC14 above.
- **Adversarial / edge cases:**
  - A value exactly **equal** to a bound — assert the documented inclusive/
    exclusive convention is honoured consistently (decide and pin: bounds are
    treated as **inclusive** ranges, so equality does *not* fire).
  - A label out of range on **two** metrics (volume *and* an extent) yields
    **two** findings, each naming its own metric and the same offending label.
  - A `level_name` from a custom convention not in the three groups is skipped,
    not crashed.
  - A geometry sub-dict missing one metric key does not raise; only present
    metrics are checked.
  - Severity param with an unrecognised string raises a clear `ValueError`
    (reuse the `Finding.from_dict` severity-label validation behaviour) — or, if
    chosen instead, falls back to the default; pin whichever in the Decisions log.
  - Determinism: assert two runs are equal and that multi-label/multi-metric
    output order is stable (AC13).

---

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 004** — `segqc.labels` (`CANONICAL_ORDER`, level naming) for
    level-group resolution.
  - **Item 011** — per-label geometry (`physical_volume_mm3`, `extent_*_mm`,
    `voxel_count`) whose serialised form (item 016 `build_features_block`) is the
    record this rule reads.
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.bounds` config and the
    §6-mode-2 end-to-end test.

This item is **parallel-independent** of the other rule families (028–033); they
share only the already-merged item-026 interface.

---

## Decisions & Trade-offs

Pinned during implementation (2026-06-30):

- **One finding per violated metric (confirmed).** Each `Finding` carries
  exactly one `(label, metric)` violation — `labels == frozenset({label_int})`
  and `reason` names that single metric plus its measured value vs the
  violated bound. A label out of range on both volume and extent therefore
  yields two separate findings. This maximises explainability and lets
  downstream item 034 weight individual metrics independently.

- **Inclusive bounds (confirmed).** A value strictly `< min` or strictly
  `> max` fires. A value exactly equal to `min` or `max` passes. This is the
  conventional "closed interval" interpretation and is tested and pinned.

- **Default severity is `Severity.FLAG` (`"flagged-for-review"`).** Bounds
  violations are suspicious but not categorically fatal; the final
  pass/flag/fail verdict is item 034's job. Severity is config-overridable
  via `rules.bounds.params.severity`.

- **Unrecognised severity string raises `ValueError` (raises path pinned).**
  If `rules.bounds.params.severity` is not a recognised Severity label
  (`"pass"`, `"flagged-for-review"`, or `"fail"`), `evaluate` raises
  `ValueError` immediately. Falling back to the default was considered but
  rejected: a misconfigured severity string is more likely a typo that should
  surface loudly than a deliberate choice that should degrade silently.

- **Hand-set default bound magnitudes.** Placeholder ranges chosen from
  published vertebra morphometry. Stage 6 (item 006) will supersede them with
  VerSe-derived distributions:
  - Cervical (C1–C7): volume 3 000–35 000 mm3; extents 10–80 mm (x/y), 5–60 mm (z).
  - Thoracic (T1–T13): volume 5 000–70 000 mm3; extents 15–100 mm (x/y), 8–80 mm (z).
  - Lumbar (L1–L6): volume 8 000–120 000 mm3; extents 20–120 mm (x/y), 15–100 mm (z).

- **Level-group map built from `CANONICAL_ORDER`.** `_LEVEL_GROUP` is derived
  at module import time by inspecting each canonical name's prefix (C/T/L),
  so the mapping stays in step with any future extension to the label
  convention without a separate maintenance point.

- **Metric order is fixed by `_METRICS` list.** Output order within a label
  is volume → extent_x → extent_y → extent_z, making the rule deterministic
  (AC13) regardless of dict-iteration order in the geometry sub-dict.

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md) (scoped to
this item's rows only; `git pull --rebase` first):

- Flip the Stage 4 deliverable sub-row **"min/max bounds (volume, extent),
  level-aware"** (line ~150) from 📋 → ✅.
- Leave the Stage 4 **acceptance checkboxes** (lines ~161–163) and the **stage
  rollup** (line 143, and the index row at line 29) as they are — Stage 4 closes
  only when item 035 lands the per-failure-mode end-to-end tests; the validator
  reconciles the stage ✅ at that point.
- Per `CLAUDE.md`: work on branch `aide/027-level-aware-bounds`, keep
  `progress.md` edits scoped to this item, and direct-merge (no PR) once green.
