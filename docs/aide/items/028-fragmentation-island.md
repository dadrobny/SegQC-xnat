# Item 028 — Connected-Components & Fragmentation / Island Rules

> **Created:** 2026-06-30 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 028
> **Objectives:** G2 (detect §6 failure modes — mode 2 fragmentation, mode 3
> disconnected components / rogue islands), supporting G4 (per-case reasons +
> offending labels)
> **Suggested branch:** `aide/028-fragmentation-island`

---

## Description

Implement a **connected-components rule family** for the Stage 4 heuristic rule
engine, covering two §6 failure modes off the same underlying topology data:

- **Fragmentation (§6 mode 2)** — a single vertebra body that has split into
  comparable pieces. Detected when the label's **fragmentation index**
  (= largest connected component / total label volume) falls **below** a
  configurable threshold.
- **Rogue islands (§6 mode 3)** — a dominant body plus one or more **small
  disconnected components**. Detected when a label has non-dominant connected
  components whose **voxel size** falls **below** a configurable threshold.

The rule plugs into the item-026 engine core by subclassing
`segqc.heuristics.Rule`, registering itself via `register_rule`, and emitting
`segqc.heuristics.Finding` objects through the standard runner. It follows every
convention pinned by the sibling bounds rule (item 027): config-driven
thresholds with shipped hand-set defaults, **inclusive** thresholds, per-label
iteration in ascending integer-label order, deterministic output ordering,
default severity `FLAG` (config-overridable), an unrecognised severity string
raising `ValueError`, and **never mutating** the input record.

For each present vertebra label the rule:

1. reads the label's already-computed **connected-components record** from
   `record["per_label"]["<label>"]["components"]` (item 012 / item 025);
2. runs the **fragmentation check**: if the label's `fragmentation_index`
   (alias of `largest_component_fraction`, in `(0.0, 1.0]`) is strictly below
   the configured `fragmentation_index_threshold`, emits one **fragmentation**
   `Finding`;
3. runs the **island check**: examines the **non-dominant** components
   (every component except the single largest) and, if any has a voxel size
   strictly below the configured `island_min_voxels`, emits one **rogue-island**
   `Finding` summarising the offending islands;
4. attributes every finding to the offending label and writes a human-readable
   `reason` reporting the **component count**, **component sizes**, and
   **fragmentation index**, at a configurable severity (default
   `flagged-for-review`).

Targets **§6 failure mode 2** (fragmentation) and **§6 failure mode 3**
(disconnected components / rogue islands).

### What this item is **not**

- Not reference-derived thresholds — calibrated thresholds come from VerSe in
  **Stage 6 / item 006**. Item 028 ships **hand-set** placeholder thresholds only.
- Not verdict aggregation — combining findings into a `pass`/`flag`/`fail`
  verdict is **item 034**.
- Not the shipped default config **file** — item 035 ships the documented YAML;
  here the defaults live as Python constants used as `rule_param` fallbacks.
- Does not recompute connected components — it only *consumes* the
  `components` sub-dict already assembled by `build_features_block` (item 016)
  from the item-012 extractor. It does not call `compute_components`, touch the
  item-026 engine core, the `config.py` schema, `verdict.py`, or any extractor.

### The feature record this rule consumes

The per-case record passed to `evaluate(record, config)` is the
`build_features_block` dict (item 016). This rule reads only the per-label
`components` sub-dict produced by `components_to_dict` (item 012 + item 025):

```
record["per_label"] : { "<label_int>": {
    "label": int,
    "level_name": str,
    "components": {
        "component_count": int,            # >= 1 for a present label
        "component_sizes": [int, ...],      # voxel count per component, DESC
        "component_volumes_mm3": [float],   # same order as component_sizes
        "largest_component_fraction": float,# in (0.0, 1.0]
        "small_fragments": [int, ...],      # NOT relied on (see Decisions)
        "fragmentation_index": float,       # alias of largest_component_fraction
    },
    ...
} }
```

`component_sizes` is sorted **descending**, so `component_sizes[0]` is the
dominant body and `component_sizes[1:]` are the non-dominant components examined
by the island check.

### Two finding kinds share one `rule_id`

Both finding kinds carry `rule_id == "fragmentation"` (the `Finding` model has
no sub-type field). The two kinds are distinguished by a clear, stable **tag at
the start of the `reason` string** — `"Fragmentation:"` for the fragmentation
finding and `"Rogue island(s):"` for the island finding — so a reader (and a
test) can tell them apart. A single label can emit **both** (at most one of
each); when it does, the fragmentation finding is emitted before the island
finding (fixed order, see AC16).

### Config shape (read via `config.rule_param`)

```yaml
rules:
  fragmentation:
    enabled: true                         # honoured by the runner (item 026)
    params:
      severity: flagged-for-review        # optional; default flagged-for-review
      fragmentation_index_threshold: 0.75 # fire when index strictly below this
      island_min_voxels: 50               # non-dominant component strictly below
                                          # this (voxels) is a rogue island
```

Each param is read with a built-in default fallback via
`config.rule_param("fragmentation", "<key>", default=<DEFAULT>)`, so an absent
`rules.fragmentation` section leaves the rule fully operational on its shipped
defaults.

---

## Acceptance Criteria

- [ ] **AC1: The rule registers under `rule_id == "fragmentation"`.**
      Importing `segqc.heuristics` makes a `FragmentationRule` (subclass of
      `segqc.heuristics.Rule`) available in the registry; `get_rule("fragmentation")`
      returns the registered instance and `fragmentation` appears in `iter_rules()`.

- [ ] **AC2: No finding for a single-component label.**
      For a label whose `components.component_count == 1` (so
      `fragmentation_index == 1.0` and `component_sizes` has a single entry), the
      rule emits **no** finding with `rule_id == "fragmentation"` — neither a
      fragmentation nor an island finding.

- [ ] **AC3: A fragmentation finding fires when the index is below the threshold.**
      Given a label whose `fragmentation_index` is **strictly below**
      `fragmentation_index_threshold` (a body split into comparable pieces, e.g.
      two equal halves → index ≈ 0.5 under a 0.75 threshold), the rule emits a
      `Finding` with `rule_id == "fragmentation"`, `labels == frozenset({that_label})`,
      and a `reason` beginning with the `"Fragmentation:"` tag.

- [ ] **AC4: A fragmentation index exactly equal to the threshold does not fire.**
      Given a label whose `fragmentation_index` equals
      `fragmentation_index_threshold` exactly, the rule emits **no** fragmentation
      finding (inclusive-threshold convention: only strictly below fires).

- [ ] **AC5: A fragmentation index above the threshold does not fire.**
      Given a label whose `fragmentation_index` is strictly above
      `fragmentation_index_threshold`, the rule emits **no** fragmentation finding.

- [ ] **AC6: A rogue-island finding fires for a dominant body plus a tiny component.**
      Given a label with a large dominant component and at least one **non-dominant**
      component whose voxel size (`component_sizes[i]`, `i >= 1`) is **strictly
      below** `island_min_voxels`, the rule emits a `Finding` with
      `rule_id == "fragmentation"`, `labels == frozenset({that_label})`, and a
      `reason` beginning with the `"Rogue island(s):"` tag.

- [ ] **AC7: Comparable pieces produce no island finding.**
      Given a label split into multiple components that are **all at or above**
      `island_min_voxels` (no non-dominant component below the threshold), the rule
      emits **no** island finding (it may still emit a fragmentation finding —
      AC3 — but island detection is independent and silent here).

- [ ] **AC8: A non-dominant component exactly equal to the island threshold does not fire.**
      Given a label whose only sub-dominant component has voxel size exactly equal
      to `island_min_voxels`, the rule emits **no** island finding
      (inclusive-threshold convention: only strictly below fires).

- [ ] **AC9: The fragmentation threshold is config-driven.**
      With a config that **raises** `fragmentation_index_threshold` above a label's
      index, that label now **fires** a fragmentation finding; with a config that
      **lowers** the threshold below the index, the same label does **not** fire —
      demonstrating the config value is used in preference to the built-in default.

- [ ] **AC10: The island voxel threshold is config-driven.**
      With a config that **raises** `island_min_voxels` above a non-dominant
      component's size, that label now **fires** an island finding; with a config
      that **lowers** the threshold below it, the same label does **not** fire.

- [ ] **AC11: Shipped hand-set defaults apply when no config is supplied.**
      With `default_config()` (no `rules.fragmentation` section), a clearly
      fragmented label (e.g. split into two comparable halves) **fires** a
      fragmentation finding, and an intact single-body label does **not** — i.e. the
      rule's built-in default thresholds are in effect without any config file.

- [ ] **AC12: Each finding names the offending label.**
      Every finding the rule emits has `labels == frozenset({that_label})` — the
      single integer label whose components triggered it (no case-level or
      multi-label findings from this rule).

- [ ] **AC13: Each finding's reason reports component count, sizes, and fragmentation index.**
      Every `fragmentation` finding has a non-empty `reason` string that contains
      the label's `component_count`, its `component_sizes`, and its
      `fragmentation_index`, so a reader can see the topology that triggered the flag.

- [ ] **AC14: Default severity is `FLAG`, and severity is config-driven.**
      With no `severity` param, every finding has `severity == Severity.FLAG`. With
      `rules.fragmentation.params.severity` set to `fail`, emitted findings have
      `severity == Severity.FAIL`.

- [ ] **AC15: An unrecognised severity string raises `ValueError`.**
      If `rules.fragmentation.params.severity` is not a recognised `Severity` label
      (`"pass"`, `"flagged-for-review"`, or `"fail"`), `evaluate` raises
      `ValueError` immediately.

- [ ] **AC16: The rule is deterministic with a fixed output order.**
      Two successive `run_rules(record, cfg)` calls on the same inputs return equal
      finding lists in the same order. Findings are ordered by ascending integer
      label; within a single label that triggers both kinds, the **fragmentation**
      finding precedes the **rogue-island** finding.

- [ ] **AC17: The rule tolerates an empty / absent / components-free record.**
      `evaluate` returns `[]` and raises nothing when `per_label` is empty or
      absent, and a per-label entry that is missing its `components` sub-dict (or
      whose `components` lacks `fragmentation_index` / `component_sizes`) is skipped
      gracefully rather than crashing.

- [ ] **AC18: The rule does not mutate the input record.**
      Calling `evaluate(record, config)` leaves `record` (including every nested
      `per_label` / `components` dict and list) unchanged — verified by deep
      equality against a pre-call copy.

---

## Implementation Steps

Intended code path — a single new module plus a one-line registration import; no
changes to engine core, config schema, or extractors.

1. **Create `src/segqc/heuristics/fragmentation.py`:**
   - Import `Rule`, `register_rule` from `segqc.heuristics.rule`, `Finding` from
     `segqc.heuristics.finding`, and `Severity` from `segqc.verdict`.
   - Define **shipped hand-set default constants** (documented as placeholders
     superseded by Stage 6 / item 006):
     - `DEFAULT_FRAGMENTATION_INDEX_THRESHOLD: float` (e.g. `0.75`) — a label
       whose fragmentation index drops below this is judged "split into comparable
       pieces".
     - `DEFAULT_ISLAND_MIN_VOXELS: int` (e.g. `50`) — a non-dominant component
       smaller than this many voxels is judged a rogue island.
   - Reuse the `Finding`-style **label→`Severity` lookup** (`{sev.label: sev for
     sev in Severity}`) and a `_severity_from_param(label) -> Severity` helper that
     raises `ValueError` on an unrecognised label (mirror `bounds.py`).
   - Define the two **reason tags** as module constants
     (`_FRAGMENTATION_TAG = "Fragmentation:"`, `_ISLAND_TAG = "Rogue island(s):"`)
     so they are stable and testable.

2. **Implement `class FragmentationRule(Rule)`** with
   `rule_id = "fragmentation"` and `evaluate(self, record, config) -> list[Finding]`:
   - Read severity once via `_severity_from_param(config.rule_param(
     "fragmentation", "severity", default="flagged-for-review"))` (raises on a
     bad string, AC15).
   - Read the two thresholds once:
     `frag_threshold = config.rule_param("fragmentation",
     "fragmentation_index_threshold", default=DEFAULT_FRAGMENTATION_INDEX_THRESHOLD)`
     and `island_min = config.rule_param("fragmentation", "island_min_voxels",
     default=DEFAULT_ISLAND_MIN_VOXELS)`.
   - Iterate `record.get("per_label", {})` in **ascending integer-label order**
     (`sorted(per_label, key=int)`).
   - For each entry, read `comp = entry.get("components")`; if `comp` is absent
     or not a mapping, **skip** the label (AC17).
   - **Fragmentation check:** read `index = comp.get("fragmentation_index")`,
     falling back to `comp.get("largest_component_fraction")`; if present and
     **strictly less than** `frag_threshold`, append a fragmentation `Finding`
     whose `reason` starts with `_FRAGMENTATION_TAG` and reports the label,
     `component_count`, `component_sizes`, and `index` (AC3, AC4, AC5, AC13).
   - **Island check:** read `sizes = comp.get("component_sizes") or []`; consider
     only the **non-dominant** components `sizes[1:]`; collect those **strictly
     below** `island_min`; if any, append a rogue-island `Finding` whose `reason`
     starts with `_ISLAND_TAG` and reports the label, `component_count`, the full
     `component_sizes`, the offending island sizes, and `fragmentation_index`
     (AC6, AC7, AC8, AC13). A single-component label has empty `sizes[1:]`, so it
     never fires an island finding (AC2).
   - Emit the fragmentation finding **before** the island finding for the same
     label (fixed order, AC16). Every finding sets
     `labels=frozenset({int(label_key)})` (AC12) and `severity=severity` (AC14).
   - Return the aggregated list (empty when nothing fires, AC17).
   - **Do not mutate** `record`, `entry`, `comp`, or any list read from it; only
     read and build fresh `Finding`s (AC18).

3. **Register the rule:** decorate `FragmentationRule` with `@register_rule` (or
   call `register_rule(FragmentationRule)`) at module import.

4. **Trigger registration on package import:** add
   `from segqc.heuristics import fragmentation  # noqa: F401` to
   `src/segqc/heuristics/__init__.py`, alongside the existing `bounds` import, so
   importing `segqc.heuristics` makes the `fragmentation` rule discoverable via the
   registry/runner.

5. **Do not** touch `config.py`, `rule.py`, `runner.py`, `finding.py`,
   `components.py`, `fragmentation.py` (the *features* extractor), or
   `feature_report.py`. All thresholds flow through the existing `rule_enabled` /
   `rule_param` accessors.

---

## Testing Strategy

- **Framework:** `pytest`. Test module: `tests/test_028_fragmentation_island.py`.
- **Registry isolation:** use the item-026 registry snapshot/restore approach
  (save and restore `segqc.heuristics.rule._RULES`) so registering
  `FragmentationRule` does not leak across tests and re-registration does not
  raise a duplicate-id error.
- **Record fixtures:** build minimal `per_label` dicts by hand matching the
  `build_features_block` / `components_to_dict` shape (a helper that takes
  `label`, and a `components` sub-dict with `component_count`, `component_sizes`,
  `component_volumes_mm3`, `largest_component_fraction`, `fragmentation_index`),
  rather than running the full extractor stack — the rule only reads `components`.
  Provide:
  - a **single-component** label (`component_count == 1`, `fragmentation_index ==
    1.0`) — AC2;
  - a **two-equal-halves** label (`component_sizes == [N, N]`, index ≈ 0.5) —
    AC3, AC11;
  - a label with index **exactly equal** to the threshold — AC4;
  - a label with index **above** the threshold — AC5;
  - a **dominant body + tiny island** label (`component_sizes == [big, small]`,
    `small < island_min_voxels`) — AC6;
  - a label split into **comparable large** pieces, none below the island
    threshold — AC7;
  - a label whose only sub-dominant component equals `island_min_voxels` exactly
    — AC8;
  - a multi-label record mixing intact, fragmented, and island labels for
    ordering — AC16;
  - an **empty** / `per_label`-absent record, and a per-label entry **missing**
    its `components` sub-dict (or missing `fragmentation_index` /
    `component_sizes`) — AC17.
- **Config fixtures:** `default_config()` for the defaults path (AC11); a
  `HeuristicConfig` (constructed in-process or via `load_config` on a temp YAML)
  with `rules.fragmentation.params.fragmentation_index_threshold` overrides (AC9),
  `island_min_voxels` overrides (AC10), a `severity` override (AC14), and an
  invalid `severity` string (AC15).
- **Coverage map:** one focused test per AC1–AC18 above.
- **Adversarial / edge cases:**
  - A label that triggers **both** kinds (low index **and** a tiny island) yields
    **two** findings in the fixed order (fragmentation then island), both naming
    the same label — pins AC16.
  - A value exactly equal to a threshold (index == threshold; island size ==
    `island_min_voxels`) does **not** fire — pins the inclusive convention
    consistently with item 027 (AC4, AC8).
  - A `components` sub-dict with `component_sizes == []` or `[0]` (degenerate /
    empty) is skipped gracefully, not crashed.
  - An unrecognised `severity` string raises a clear `ValueError` (AC15).
  - Mutation guard: deep-copy the record before `evaluate`, assert deep equality
    afterwards (AC18).
  - Determinism: assert two `run_rules` calls return equal lists and that
    multi-label/multi-kind output order is stable (AC16).

---

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`Finding`, `Rule`, `register_rule`, `get_rule`,
    `iter_rules`, `run_rules`) and the `HeuristicConfig.rule_enabled` /
    `rule_param` accessors this rule plugs into.
  - **Item 027** — sibling bounds rule, the canonical pattern this item mirrors
    (registration, `_severity_from_param`, inclusive thresholds, deterministic
    ordering, no record mutation). Already merged ✅.
  - **Item 012** — connected-components extractor (`ComponentsInfo`:
    `component_count`, `component_sizes`, `component_volumes_mm3`,
    `largest_component_fraction`, `small_fragments`) whose serialised form
    (item 016 `components_to_dict`) is the `components` sub-dict this rule reads.
  - **Item 025** — fragmentation index (`fragmentation_index`, alias of
    `largest_component_fraction`) exposed in the serialised `components` sub-dict.
  - **Item 008** — `segqc.verdict.Severity` (finding severity + label↔member
    mapping pattern).
  - **Item 005** — `segqc.config` (`HeuristicConfig`, `default_config`,
    `load_config`).
- **Downstream (depend on this item):**
  - **Item 034** — verdict aggregation consumes the `Finding`s emitted here.
  - **Item 035** — ships the documented default `rules.fragmentation` config and
    the §6-mode-2/3 end-to-end tests.

This item is **parallel-independent** of the other rule families (027,
029–033); they share only the already-merged item-026 interface.

---

## Decisions & Trade-offs

Confirmed during implementation (builder, 2026-06-30):

- **One rule, two finding kinds, one `rule_id`.** Both fragmentation and rogue
  islands derive from the same connected-components data, so they live in one
  rule (`rule_id == "fragmentation"`). The two kinds are distinguished by a
  stable tag at the start of the `reason` string (`"Fragmentation:"` vs
  `"Rogue island(s):"`) rather than a new field on the `Finding` model. A label
  can emit at most one of each.

- **Fixed within-label order: fragmentation before island.** When a label
  triggers both, the fragmentation finding is appended first, so multi-kind
  output is deterministic (AC16) regardless of dict-iteration order.

- **Inclusive thresholds (consistent with item 027).** A fragmentation index
  strictly `<` `fragmentation_index_threshold` fires; equality passes. A
  non-dominant component size strictly `<` `island_min_voxels` is a rogue
  island; equality passes.

- **Island = non-dominant component below the voxel threshold.** Because
  `component_sizes` is sorted descending, the dominant body is `sizes[0]` and is
  never itself an island; only `sizes[1:]` are island candidates. This makes a
  single-component label trivially island-free (AC2) and keeps the island and
  fragmentation checks independent (AC7).

- **Voxel-count island threshold (volume reported, not thresholded).** The
  shipped island threshold is `island_min_voxels` (voxel count, always present
  in `component_sizes`); `component_volumes_mm3` may be reported in the reason
  for context but is not the configured knob. A reference-derived /
  volume-based threshold is deferred to Stage 6 (item 006).

- **Does not rely on `components.small_fragments`.** That precomputed list
  depends on the global `config.min_fragment_voxels` field set at feature-compute
  time (default `0` → empty). The rule re-derives islands from `component_sizes`
  using its own `island_min_voxels` rule param, so it is self-contained and not
  coupled to upstream config wiring.

- **Unrecognised severity string raises `ValueError`** (raises path pinned,
  mirroring item 027): a misconfigured severity is treated as a loud error, not
  a silent fallback.

- **Hand-set default magnitudes.** `fragmentation_index_threshold = 0.75` and
  `island_min_voxels = 50` are placeholders chosen for plausibility; Stage 6
  (item 006) supersedes them with VerSe-derived distributions.

- **`or`-chained fallback for fragmentation index.** `index = comp.get("fragmentation_index") or comp.get("largest_component_fraction")` uses Python `or`, so a `0.0` value would fall through to the alias. In practice a label with voxels will never have a 0.0 index, and both keys alias the same value, so this is safe. If `None` is returned (both keys absent), the fragmentation check is skipped (AC17).

- **`isinstance(comp, dict)` guard.** The components value is validated with `isinstance(comp, dict)` before any field access, so a non-mapping value (e.g. a string) is skipped gracefully rather than raising `AttributeError` (AC17).

---

## Completion Reminder

When this item is complete, update [`../progress.md`](../progress.md) (scoped to
this item's rows only; `git pull --rebase` first):

- Flip the Stage 4 deliverable sub-row **"connected-components → fragmentation /
  island flags"** (line ~151) from 📋 → ✅, annotating it `*(Item 028)*`.
- Leave the Stage 4 **acceptance checkboxes** (lines ~161–163) and the **stage
  rollup** (line 143, and the index row near the top) as they are — Stage 4
  closes only when item 035 lands the per-failure-mode end-to-end tests; the
  validator reconciles the stage ✅ at that point.
- Per `CLAUDE.md`: work on branch `aide/028-fragmentation-island`, keep
  `progress.md` edits scoped to this item, and direct-merge (no PR) once green.
</content>
</invoke>
