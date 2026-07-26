# Item 098 — Promote stray-component metrics to first-class `components` fields

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 18 — Failure-Mode-Specific Metric Surface (G2, G7)
> **Queue:** [`../queue/queue-014.md`](../queue/queue-014.md) · Item 098
> *(first of five; items 099 and 100 read the fields this item names, so it
> lands first — it is also the only item in the batch that changes the
> persisted feature-record shape)*
> **Objectives:** G2 (each §6 failure mode needs ≥1 *named* metric that
> isolates it; mode 3 — "foreground beyond the dominant connected component" —
> currently has no name anywhere in the feature record), G7 (the refactor is
> behaviour-preserving and must be *proven* so by regression, not asserted)
> **Suggested branch:** `aide/098-promote-stray-component-metrics-to`

---

## Description

The quantity that isolates §6 mode 3 — how much foreground lives outside a
label's dominant connected component — exists nowhere as a named field.
`ComponentsInfo` (`features/components.py:61-98`) exposes `component_count`,
`component_sizes`, `component_volumes_mm3`, `largest_component_fraction` and
`small_fragments`; the *stray* population is reconstructed privately inside
`heuristics/fragmentation.py` as `sizes[1:]` (`fragmentation.py:442-443`), so
nothing outside that rule can read it and no per-mode metric can be built on it.

This item **names that population and its metrics** and makes the fragmentation
rule a *reader* of them:

1. Add four fields to `ComponentsInfo` — `stray_component_count`,
   `stray_component_sizes`, `stray_volume_mm3`, `stray_volume_fraction` —
   populated in `compute_components` alongside the existing
   `component_volumes_mm3` / `largest_component_fraction` computation
   (`components.py:181-196`).
2. Serialise all four in `components_to_dict` (`feature_report.py:145-163`),
   the single serialisation site.
3. Admit all four in the report schema's `components` definition
   (`report_schema_v0.json:237-271`) — `additionalProperties` is `false` and
   `required` is exhaustive, so **both** lists must be extended or every report
   fails validation.
4. Refactor the fragmentation rule's hand-set island branch
   (`fragmentation.py:438-464`) to read `stray_component_sizes` instead of
   rebuilding `non_dominant` from `sizes[1:]`, and refresh the module
   docstring's now-stale design note (`fragmentation.py:45-47`).
5. Regenerate the nine `tests/corpus/golden/*.json` whole-record snapshots via
   `synth/golden.py::write_goldens` (`golden.py:268`, one-command path
   `python -m segfacet.synth.golden`).

"Stray" means **every component other than the dominant one** —
`component_sizes[1:]`, the exact population the rule reconstructs today — so
`stray_volume_fraction` is the arithmetic complement of
`largest_component_fraction` and is **derived from it**, not recomputed by a
second route (which would let the two drift by float noise and give two
disagreeing answers to the same question).

**The rule's behaviour must not change (G7 acceptance).** The
`island_min_voxels` voxel-floor semantics, the reference-derived
`max_component_count` branch (`fragmentation.py:413-437`), the within-label
finding order and every `reason` string stay exactly as they are. The refactor
changes *where the stray population comes from*, nothing else.

**What this item is NOT:**

- **Not a change to the reference vocabulary.** `INGESTED_MORPHOLOGY_FEATURES`
  (`reference/ingest.py:146-150`) stays exactly
  `("largest_component_fraction", "component_count", "eigenvalue_ratio")`.
  Adding a stray metric there would invalidate the committed
  `reference_verse_v1.json` and force a re-fit of the 80-subject VerSe19
  distribution. Stage 23 owns the normative-model rework.
- **Not a new rule, a new threshold, or a retune.** No rule fires on the new
  fields in this item; they are a measurement surface for items 099/100.
- **Not the per-mode metric API** (item 099) nor the monotonicity harness
  (item 100).
- **Not a `FEATURE_CATALOG` update.** `scripts/aide_status_report.py`'s
  hand-maintained catalogue (lines ~877-893) will drift by four entries; Stage
  19 replaces it with a *generated* catalogue plus a drift test, which is the
  right place to close that gap. Recorded in `insights.md`.

## Acceptance Criteria

- [ ] **AC1: `ComponentsInfo` carries four new stray fields.**
  `segfacet.features.components.ComponentsInfo` has, appended after
  `small_fragments` (so existing positional/`astuple` ordering of the five
  current fields is unchanged): `stray_component_count: int`,
  `stray_component_sizes: List[int]`, `stray_volume_mm3: float`,
  `stray_volume_fraction: float`. The dataclass is still `frozen=True`.

- [ ] **AC2: the stray population is `component_sizes[1:]`.** For every label
  of every `tests/corpus` case, `info.stray_component_sizes ==
  info.component_sizes[1:]` (same values, same descending order), and the
  returned list is not the same object as (does not alias) `component_sizes`.

- [ ] **AC3: `stray_component_count` is the non-dominant component count.**
  For every label of every corpus case, `info.stray_component_count ==
  info.component_count - 1 == len(info.stray_component_sizes)`.

- [ ] **AC4: `stray_volume_mm3` is the summed physical volume of the stray
  components.** For every label of every corpus case,
  `info.stray_volume_mm3 == sum(info.component_volumes_mm3[1:])` within
  `1e-9` absolute tolerance (it is *derived from* the already-computed
  per-component volumes, not from a second `voxel_volume` multiplication).

- [ ] **AC5: `stray_volume_fraction` is the complement of
  `largest_component_fraction`.** For every label of every corpus case,
  `info.stray_volume_fraction + info.largest_component_fraction == 1.0`
  within `1e-12` absolute tolerance, and `0.0 <= stray_volume_fraction <= 1.0`.

- [ ] **AC6: a single-component label reports an empty stray population.** For
  a label that is one connected piece, `stray_component_count == 0`,
  `stray_component_sizes == []`, `stray_volume_mm3 == 0.0` (a `float`, not the
  `int` `0`), and `stray_volume_fraction == 0.0`.

- [ ] **AC7: hand-computed values on a multi-component fixture.** On a
  synthetic label map with a known dominant body plus ≥2 known stray pieces
  and known non-isotropic voxel spacing, all four fields equal the values
  computed by hand from the fixture's construction (not from the
  implementation's own output).

- [ ] **AC8: `components_to_dict` emits the four new keys.**
  `feature_report.components_to_dict(info)` returns a dict whose key set is
  exactly the six existing keys plus `stray_component_count`,
  `stray_component_sizes`, `stray_volume_mm3`, `stray_volume_fraction`, with
  values equal to the dataclass's; the emitted `stray_component_sizes` list is
  a shallow copy that does not alias the dataclass's list (mutating the
  returned dict's list leaves `info.stray_component_sizes` unchanged).

- [ ] **AC9: the report schema admits and requires the four new fields.**
  `report_schema_v0.json`'s `components` definition lists all four under
  `properties` **and** under `required`, keeps `additionalProperties: false`,
  and types them as `integer`/`array of integer`/`number`/`number` with
  `stray_volume_fraction` bounded `minimum: 0, maximum: 1`. A components block
  missing any one of the four fails `jsonschema.validate`; a block carrying an
  unknown extra key still fails.

- [ ] **AC10: the fragmentation rule reads the named field rather than
  recomputing it.** Given a record whose `components.stray_component_sizes`
  deliberately **disagrees** with `components.component_sizes[1:]` (e.g.
  `component_sizes = [1000, 500]` but `stray_component_sizes = [5]`), the
  hand-set island finding is derived from `stray_component_sizes` — it fires,
  and its `reason` names the sizes from `stray_component_sizes`.

- [ ] **AC11: a legacy components dict without the new keys behaves exactly as
  today.** Given a record whose `components` sub-dict carries only the six
  pre-098 keys, the fragmentation rule emits the same findings (count, order,
  `rule_id`, `severity`, `labels`, `reason` strings) it emits today, by falling
  back to `component_sizes[1:]` — the same primary-key/fallback-alias
  discipline the rule already uses for `fragmentation_index` /
  `largest_component_fraction`.

- [ ] **AC12: hand-set island findings are byte-identical across the corpus.**
  For all nine `tests/corpus` cases under `bundled_default_config()` (which
  attaches no `reference`, so the hand-set branch is the one exercised), the
  `fragmentation` findings produced by `run_rules` match a frozen
  pre-refactor snapshot **exactly** — same count, same order, same `rule_id`,
  `severity`, `labels`, and character-for-character identical `reason` strings.

- [ ] **AC13: the reference-derived branch is untouched.** For a record with a
  `reference` attached that covers the label's level for `component_count`,
  the excess-`component_count` finding (reason, threshold, percentile text) is
  character-for-character identical to a frozen pre-refactor snapshot, and the
  `island_min_voxels` floor is still bypassed (not ANDed) for that level.

- [ ] **AC14: the nine committed goldens carry the new fields and validate.**
  Every `tests/corpus/golden/*.json` is regenerated; each per-label
  `components` block in each of the nine files carries the four new keys, and
  each whole file validates against the updated `report_schema_v0.json`.

- [ ] **AC15: the goldens' verdicts and findings are unchanged.** For each of
  the nine regenerated goldens, the top-level `verdict` block and the
  `findings` array (length, order, and every `rule_id`/`severity`/`reason`/
  `labels` value) are identical to the pre-098 committed golden's — only the
  `features` block grew.

- [ ] **AC16: intra-run determinism still holds.** `write_goldens` into two
  fresh directories within one session produces byte-identical files
  (`dest1 == dest2`) for all nine cases, and `reports_close(fresh, committed)`
  is true for each.

- [ ] **AC17: the reference vocabulary is fenced off.**
  `reference.ingest.INGESTED_MORPHOLOGY_FEATURES` is unchanged
  (`("largest_component_fraction", "component_count", "eigenvalue_ratio")`),
  no `stray_*` name appears in it, and
  `compute_morphology_reference_delta` over a features block whose
  `components` blocks carry the four new fields produces per-feature deltas
  for **only** those three names — no `stray_*` key appears anywhere in the
  delta output.

- [ ] **AC18: `reference_verse_v1.json` is untouched.** The committed
  `src/segfacet/reference/reference_verse_*.json` artifacts are byte-identical
  to their pre-098 state, and they load and score a case without change.

- [ ] **AC19: the stale design note is corrected.**
  `heuristics/fragmentation.py`'s module docstring no longer claims the stray
  population is "recomputed from `component_sizes`"; it states that the
  hand-set island branch reads `components.stray_component_sizes` (falling back
  to `component_sizes[1:]` for a legacy record shape) while still not relying
  on `small_fragments`. `features/components.py`'s module docstring documents
  all four new fields, including the "stray == every component but the
  dominant one" definition and the complement relationship.

## Assumptions

Clarify mode is `assume` (`aide.toml`'s `loop.clarify`). Defaults taken:

- **Four fields, not the three the queue names.** The queue lists "stray
  volume in mm³, stray component count, and stray volume fraction". Those three
  alone **cannot** satisfy the queue's other two requirements simultaneously:
  the hand-set island branch filters the stray population against the
  `island_min_voxels` voxel floor and prints the surviving sizes verbatim in
  its `reason` (`fragmentation.py:443,457`), so reading only a *count*, a
  *volume* and a *fraction* would either change behaviour (forbidden by G7) or
  leave `sizes[1:]` recomputed in the rule (defeating the deliverable). A
  fourth field, `stray_component_sizes` (the named population itself), is the
  minimum that makes "reads rather than recomputes" true *and*
  behaviour-preserving. It is the field items 099/100 will most likely want
  anyway (mode-3 magnitude is a distribution, not just a total).

- **`stray_volume_fraction` is `1.0 - largest_component_fraction`**, not
  `sum(sizes[1:]) / sum(sizes)`. The queue mandates deriving it "consistently
  with" `largest_component_fraction` rather than by a second route; the
  complement form guarantees the two never disagree by float noise. AC5 states
  the invariant with a `1e-12` tolerance rather than exact equality because
  IEEE-754 `fl(1-x) + x` is not exactly `1.0` for every `x`.

- **`stray_volume_mm3` is `sum(component_volumes_mm3[1:])`**, reusing the
  already-computed per-component volumes rather than multiplying
  `sum(component_sizes[1:])` by `voxel_volume` a second time — same
  "one route to a physical volume" reasoning. May differ from the second
  route by ULPs; AC4 states `1e-9` absolute tolerance.

- **The rule uses primary-key-with-fallback, not a hard read.** The refactored
  branch reads `comp.get("stray_component_sizes")` and falls back to
  `comp.get("component_sizes", [])[1:]` when the key is **absent** (AC11) —
  mirroring the rule's existing `fragmentation_index` →
  `largest_component_fraction` alias discipline and its documented
  "skip gracefully if `components` is absent or not a mapping" tolerance
  (`fragmentation.py:350-352`). This is load-bearing: five existing test
  modules feed hand-built pre-098 `components` dicts straight into `run_rules`
  (see Testing Strategy), and a hard read would silently stop firing on them.
  The fallback is on **absence only** — a present-but-disagreeing value is
  honoured (AC10), which is what proves the rule genuinely reads the field.

- **No default values on the new dataclass fields.** `compute_components`
  (`components.py:198`) is the only construction site in `src/` or `tests/`
  (verified by grep), so appending four required fields breaks nothing and
  keeps the dataclass honest — every `ComponentsInfo` is fully populated.

- **`component_count >= 1` always**, since `compute_components` raises
  `ValueError` for an absent label (`components.py:156-163`), so
  `stray_component_count = component_count - 1` is never negative. The schema
  still declares `minimum: 0` for it, consistent with how `component_count`
  itself is declared.

- **Goldens are regenerated with the committed one-command path**
  (`python -m segfacet.synth.golden`, `golden.py:294-315`) and *not* by hand,
  and `tests/corpus/golden/*.json` is already pinned `text eol=lf` in
  `.gitattributes`, so no new `.gitattributes` entry is needed.

- **`scripts/aide_status_report.py`'s `FEATURE_CATALOG` is deliberately left
  stale** by four entries. It is a hand-maintained dev-script table that Stage
  19 replaces with a generated catalogue plus a drift test; patching it here
  would be busywork against a table already scheduled for deletion. Recorded
  as an insight.

## Implementation Steps

All production changes are under `source_dir = src/segfacet`.

1. **`src/segfacet/features/components.py`**
   - Append the four fields to `ComponentsInfo` (AC1) after `small_fragments`,
     with full docstring entries in the class `Attributes` block: definition of
     "stray", the `component_sizes[1:]` identity, the complement relationship,
     and the single-component zero case.
   - In `compute_components`, immediately after the existing
     `largest_component_fraction` computation (`components.py:190-192`),
     compute:
     - `stray_component_sizes = list(component_sizes[1:])`
     - `stray_component_count = len(stray_component_sizes)` (== `n_components - 1`)
     - `stray_volume_mm3 = float(sum(component_volumes_mm3[1:]))`
     - `stray_volume_fraction = 1.0 - largest_component_fraction`
   - Pass all four into the `ComponentsInfo(...)` constructor
     (`components.py:198-204`).
   - Extend the module docstring's bullet list (`components.py:6-15`) with the
     four fields (AC19).

2. **`src/segfacet/feature_report.py`** — add the four keys to
   `components_to_dict`'s returned dict (`feature_report.py:156-163`), with
   `list(c.stray_component_sizes)` (shallow copy, per the function's documented
   no-aliasing contract) and `float(...)` casts on the two scalars. Extend the
   function docstring.

3. **`src/segfacet/report_schema_v0.json`** — in the `components` definition
   (lines 237-271): add the four names to `required` (append, keeping the
   existing six in place) and to `properties`:
   `stray_component_count` → `{"type": "integer", "minimum": 0}`;
   `stray_component_sizes` → `{"type": "array", "items": {"type": "integer"}}`;
   `stray_volume_mm3` → `{"type": "number", "minimum": 0}`;
   `stray_volume_fraction` → `{"type": "number", "minimum": 0, "maximum": 1}`,
   each with a one-line `description` naming the item (098) and the "every
   component but the dominant one" definition. Leave
   `additionalProperties: false` untouched. Update the definition's top-level
   `description` to read `(items 012, 025, 098)`.

4. **`src/segfacet/heuristics/fragmentation.py`** — in the `else:` (hand-set)
   branch at lines 438-464, replace

   ```
   non_dominant = sizes[1:]
   ```

   with a read of the named field plus an absence-only fallback:
   `stray = comp.get("stray_component_sizes")`; when `stray` is `None` (not
   when it is an empty list), fall back to `sizes[1:]`. Everything downstream
   — the `s < island_min` filter, the `if tiny_islands:` guard, the `Finding`
   construction and every `f"..."` fragment of the `reason` (which still prints
   `component_sizes={sizes!r}`, unchanged) — stays exactly as written.
   Then rewrite the stale docstring bullet at lines 45-47 (AC19).

5. **Regenerate the goldens** — run `python -m segfacet.synth.golden` from the
   venv (`.venv/bin/python -m segfacet.synth.golden` on Linux/macOS,
   `.venv\Scripts\python -m segfacet.synth.golden` on Windows) and commit the
   nine changed `tests/corpus/golden/*.json`. **Before committing, diff them**:
   the only changes must be four added keys per per-label `components` block —
   any change to `findings`, `verdict`, or an existing feature value is a
   regression, not an expected diff (AC15).

6. **Do NOT touch** `reference/ingest.py`, `reference/delta.py`,
   `reference/reference_verse_*.json`, `eval/`, any other rule, or
   `scripts/aide_status_report.py`.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_098_stray_components.py`;
  existing modules are read for regression, not rewritten (see "existing tests
  to reconcile" below).

- **AC1-AC8 (feature layer)** — build fixtures with `tests/synthetic.py`-style
  helpers plus a purpose-built multi-component map (dominant body + two stray
  pieces of known voxel counts, non-isotropic spacing such as `(0.5, 1.0, 2.0)`
  so a wrong `voxel_volume` cannot pass by accident). One focused test per AC;
  AC2/AC3/AC5 are asserted as invariants swept over **every label of every
  corpus case**, not just the fixture.

- **AC9 (schema)** — three tests: a well-formed components block validates; a
  block with each of the four new keys removed in turn fails
  `jsonschema.ValidationError` (parametrised over the four); a block with an
  extra unknown key fails (proving `additionalProperties: false` survived).

- **AC10/AC11 (the refactor's semantics)** — hand-built record dicts fed
  straight to `run_rules`, following the `_components()` helper style already
  in `tests/test_028_fragmentation_island.py:72-90`:
  - AC10: `component_sizes=[1000, 500]`, `stray_component_sizes=[5]`,
    `island_min_voxels=50` → the island finding **fires** and its reason
    contains `[5]` (recomputation from `sizes[1:]` would not fire at all).
  - AC11: a six-key legacy dict → identical findings to today's.
  - Edge: `stray_component_sizes=[]` present-and-empty with
    `component_sizes=[1000, 5]` → **no** island finding (an explicitly empty
    named population is honoured, not treated as "absent" and fallen back on).
    This is the boundary between AC10 and AC11 and must be tested directly.

- **AC12/AC13 (G7 regression — the load-bearing test)** — a **frozen
  characterisation snapshot**: the test module embeds a literal, hard-coded
  copy of the pre-098 fragmentation findings (in order:
  `rule_id`, `severity.label`, sorted `labels`, and the full `reason` string)
  for each of the nine corpus cases under `bundled_default_config()`, and
  asserts equality against freshly computed `run_rules` output. Snapshot the
  literals from the **current, unmodified** code before the builder touches
  anything — the committed goldens are being regenerated, so they cannot serve
  as the reference. AC13 does the same for a reference-attached record
  mirroring the scenarios in `tests/test_090_reference_derived_defaults.py`.

- **AC14-AC16 (goldens)** — reuse the existing `tests/test_042_golden_
  determinism.py` machinery rather than duplicating it: per-case schema
  validation, `write_goldens(tmp_path_1)` vs `write_goldens(tmp_path_2)`
  byte-identity, and `reports_close(fresh, committed)`. Add one new test that
  asserts every per-label `components` block in every committed golden carries
  the four keys. AC15's "verdict/findings unchanged" is asserted against a
  frozen literal snapshot of the pre-098 goldens' `verdict` + `findings`,
  captured the same way as AC12's.

- **AC17/AC18 (scope fence)** — assert
  `INGESTED_MORPHOLOGY_FEATURES == ("largest_component_fraction",
  "component_count", "eigenvalue_ratio")` exactly; assert no key starting with
  `stray_` appears anywhere in `compute_morphology_reference_delta`'s output
  for a features block built from a multi-component fixture; load
  `reference_verse_v1.json` and score a case, asserting the delta values match
  a pre-098 snapshot.

- **Adversarial / edge cases:**
  - Single-voxel label (`component_count == 1`, `component_sizes == [1]`) →
    all four stray fields at their zero values, `stray_volume_mm3` is `0.0` and
    `isinstance(..., float)`.
  - Many equal-sized components (e.g. five pieces of 100 voxels each) — the
    "dominant" component is `component_sizes[0]` under the existing descending
    sort even though the choice is arbitrary among ties; assert the stray
    fields stay self-consistent (`count == 4`, fraction `== 0.8`) and
    **deterministic** across repeated calls on the same input.
  - A label whose stray components dominate (e.g. `[10, 100, 100]` is
    impossible post-sort, so instead `[100, 90, 90]`) →
    `stray_volume_fraction > 0.5`, still `<= 1.0`.
  - Immutability: `compute_components` called twice on the same image returns
    equal `ComponentsInfo` values and never mutates `seg_img`;
    `run_rules` never mutates the record or its `components` sub-dict
    (compare a deep copy before/after), preserving the existing AC18 contract
    of item 028.
  - `components_to_dict` round-trips through `json.dumps`/`json.loads`
    unchanged (the two new scalars must be plain `float`/`int`, not
    `numpy.float64`/`numpy.int64`, which would break canonical-JSON output —
    `sum()` over a list of Python floats is safe, but assert it).

- **Existing tests to reconcile** (grep sweep for pinned pre-098 assumptions;
  all are expected to stay green **unmodified**, and their staying green is
  itself the AC11 fallback proof — the validator should treat any edit to them
  as a red flag, not routine):
  - `tests/test_028_fragmentation_island.py` — `_components()` helper (line 72)
    and the hand-built dicts at lines ~955, ~969, ~1106, ~1122 all emit the
    six-key legacy shape and feed `run_rules` directly. Covered by AC11.
  - `tests/test_035_failure_modes.py:106-124` (`_mode3_record`) and
    `tests/test_035_default_config.py:210-245` (`_gt_record`) — same legacy
    shape, `run_rules` only, never schema-validated. Covered by AC11.
  - `tests/test_016_features_json.py:442,454` — compares
    `dataclasses.astuple(ComponentsInfo)` before/after; self-relative, so the
    four extra tuple entries are harmless, but confirm.
  - `tests/test_025_fragmentation_index.py:294-345` — asserts
    `components_to_dict` *contains* `fragmentation_index`; check none of these
    assert an exhaustive key set (an `== {...}` on `d.keys()` would break).
  - `tests/test_042_golden_determinism.py` — every test here reads the nine
    goldens; all must stay green after regeneration.
  - `tests/test_036_clean_gt.py:249-255` — asserts `component_count == 1` and
    `small_fragments == []` per label; a natural place to also see the stray
    zero-case, but no change required.

## Validation

Beyond the unit suite, observe the new fields end-to-end through the CLI:

```
.venv/bin/python -m segfacet run --scan tests/corpus/fixtures/<case>.nii.gz --seg tests/corpus/fixtures/mode3_inject_islands.nii.gz --out /tmp/098-check/
```

(substitute the actual fixture names from `tests/corpus/manifest.json`;
`--scan` is only needed if the invocation requires it — a seg-only `run` is
sufficient to exercise the components block).

Then confirm, by inspecting `/tmp/098-check/`'s JSON report:

1. Each per-label `components` block carries `stray_component_count`,
   `stray_component_sizes`, `stray_volume_mm3`, `stray_volume_fraction`.
2. On `mode3_inject_islands` the stray fields are **non-zero** for the
   perturbed label(s) — i.e. the named metric actually isolates mode 3, which
   is the whole point of the stage.
3. `stray_volume_fraction + largest_component_fraction ≈ 1.0` for every label.
4. The report's `findings` and `verdict` blocks match the corresponding
   committed golden's (the G7 acceptance observed at report level, not just at
   the rule's unit level).

No `[validation]` profile is required — this runs on the plain CPU venv with
no optional dependency. If the venv is not bootstrapped, run
`python .aide/scripts/aide.py env --bootstrap` first rather than recording the
step as unverified.

## Dependencies

- **Item 012** (connected components — `ComponentsInfo`/`compute_components`,
  the dataclass being extended) — ✅.
- **Item 025** (`fragmentation_index` alias and the primary-key/fallback
  serialisation pattern this item mirrors) — ✅.
- **Item 028** (the fragmentation rule and its hand-set island branch, and its
  no-mutation contract) — ✅.
- **Item 042** (`synth/golden.py`, `write_goldens`, `reports_close`, and the
  nine committed whole-record goldens) — ✅.
- **Item 090** (the reference-derived `max_component_count` branch that must
  stay untouched) — ✅.
- **Item 097** (Stage 17 closure — level names must be right before per-level
  metrics mean anything; the stage's stated dependency) — ✅.

**Downstream:** item 099 (per-mode metric API) reads these fields as §6 mode
3's magnitude metric; item 100's mode-3 severity ladder is measured with them;
item 102 (stage validation) replays the CLI check in the Validation section
above. None of these block this item.

## Decisions & Trade-offs

Implementation notes (builder, 2026-07-26):

- Followed the spec's Implementation Steps directly: the four fields were
  computed in `compute_components` immediately after the existing
  `largest_component_fraction` line, and passed positionally into
  `ComponentsInfo(...)` after `small_fragments`, preserving the dataclass's
  frozen-ness and the pre-098 field ordering (verified: `dataclasses.fields`
  order still starts with the five original names).
- The fragmentation rule's fallback test is `"stray_component_sizes" in comp`
  (key-presence check) rather than `comp.get(...) is None`, so a present value
  of any shape (including an explicitly empty list) is always honoured and
  only genuine key-absence triggers the `sizes[1:]` fallback — this is the
  literal reading of "absence-only fallback" and matches the AC10/AC11
  boundary test (`stray_component_sizes=[]` present must NOT fall back).
- Regenerating the nine goldens via `python -m segfacet.synth.golden`
  introduced, beyond the four new `stray_*` keys per components block, a
  handful of ULP-level float diffs in unrelated fields (`eigenvalue_ratio`,
  `principal_axis` components on a couple of labels) — pre-existing
  run-to-run floating-point noise from the eigen-decomposition step, not
  something this item's changes touch. `verdict` and `findings` are
  unchanged for all nine cases (verified by diffing against the pre-098
  committed goldens and against the frozen snapshots embedded in
  `tests/test_098_stray_components.py`), consistent with `CLAUDE.md`'s note
  that golden comparisons are numeric-tolerance (`reports_close`), not
  byte-identity, across sessions.
- No change made to `scripts/aide_status_report.py`'s `FEATURE_CATALOG` or to
  `reference/ingest.py` / `reference_verse_*.json`, per the spec's explicit
  scope fence; the `FEATURE_CATALOG` drift was already recorded in
  `docs/aide/insights.md` by the spec author.
