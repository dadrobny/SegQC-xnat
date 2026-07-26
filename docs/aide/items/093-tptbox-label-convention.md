# Item 093 — Adopt the TPTBox vertebra label convention as default

> **Created:** 2026-07-26 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 17 — Foreign-Convention Interop & Orientation-Safe Image Layer (G2, G6)
> **Queue:** [`../queue/queue-013.md`](../queue/queue-013.md) · Item 093 *(first
> of five; independent of the environment/image-layer work and unblocks every
> downstream item that touches level names)*
> **Objectives:** G2 (detect catalogued failure modes — every level-aware rule
> and the reference artifact depend on level names being correct; today they
> are silently wrong for values 25/26/29)
> **Suggested branch:** `aide/093-tptbox-label-convention`

---

## Description

Replace `segfacet.labels`'s `DEFAULT_LABEL_MAP`/`CANONICAL_ORDER` — which
today defines **25 = `S`, 26 = `Cocygis`, 29 = `L6`** — with the TPTBox
vertebra table (`TPTBox.core.vert_constants.v_idx2name`, values 1–33: **25 =
`L6`, 26 = `S1`, 27 = `Cocc`, 28 = `T13` (unchanged), 29 = `S2`, 30 = `S3`,
31 = `S4`, 32 = `S5`, 33 = `S6`**), adopting the **full** TPTBox range rather
than only renaming the six values FACET already had — real cohorts commonly
segment only a subset of the fine-grained sacral/coccygeal range (a single
generic sacrum, or `S1` plus a merged rest), but the *convention* should be
able to name any value a TPTBox-convention segmenter emits, even when a given
case's inventory only populates a few of them. This is a **data swap at the
source table**, not new plumbing: `LabelConvention` (`labels.py:139-266`) is
already a fully-replacing, immutable, overridable abstraction reached via
`LabelConvention.default()` / `LabelConvention.from_mapping(...)`, and the 15
modules that consume it read the convention object, not the raw table.

This item does **not** add TPTBox as a dependency — it hardcodes the
TPTBox-derived table as a literal Python dict (TPTBox itself is not installed
until item 094, sequenced after this item and after the item-095 environment
migration). It also mechanically re-keys the two places the string `"S"`
appears in the committed `reference_verse_v1.json` artifact (the top-level
`levels` dict key, and the nested `level_name` field of that entry) to `"L6"`
— the underlying per-level percentile statistics are **not** recomputed; only
what those statistics are *called* changes, correcting a pre-existing naming
bug rather than re-fitting a distribution. `reference_default.json` (the
synthetic Plane-1 baseline) needs no change: its fixed cohort only ever
segments `L1`–`L5` and never touches the sacral/coccygeal range.

**What this item is not:**
- **Not the image/I/O layer.** `segfacet.io`'s `Volume`/`Case` and
  `_spacing_from_affine` are untouched — that is item 094.
- **Not an environment/dependency change.** No `pyproject.toml` edit; TPTBox
  is not imported anywhere by this item.
- **Not a rebuild of `reference_verse_v1.json` from real VerSe data.** The
  artifact's percentile *values* are untouched — only the `"S"` key/field is
  renamed to `"L6"` in place.
- **Not axis/orientation handling.** Nothing here touches how a volume is
  oriented or resampled.

## Acceptance Criteria

- [ ] **AC1: `DEFAULT_LABEL_MAP` matches the TPTBox vertebra table for 1–33.**
  For every integer 1–33, `LabelConvention.default().name_of(value)` equals
  TPTBox's `v_idx2name[value]` restricted to the vertebra range (in
  particular `25 -> "L6"`, `26 -> "S1"`, `27 -> "Cocc"`, `28 -> "T13"`,
  `29 -> "S2"`, `30 -> "S3"`, `31 -> "S4"`, `32 -> "S5"`, `33 -> "S6"`, and
  every C/T/L value 1–24 unchanged from today).
- [ ] **AC2: `CANONICAL_ORDER` places the new entries in head-to-tail
  anatomical order.** The tuple reads `..., "L5", "L6", "S1", "S2", "S3",
  "S4", "S5", "S6", "Cocc"` after the existing lumbar run — `L6` is the
  transitional vertebra between `L5` and the sacrum; `S1`–`S6` are ordered
  sacral segments; `Cocc` (coccyx) is the final entry.
- [ ] **AC3: bidirectional lookup is exact and case-insensitive, matching the
  existing contract.** `LabelConvention.default().value_of("L6") == 25`,
  `.value_of("s1") == 26` (case-insensitive per the existing `_normalise_name`
  contract), `.value_of("Cocc") == 27`; `is_known` is `True` for all of
  1–33 and `False` for an unmapped value (e.g. `34`).
- [ ] **AC4: `LabelConvention.from_mapping` overriding still works unchanged.**
  A custom convention built via `LabelConvention.from_mapping({25: "MyName"})`
  resolves `name_of(25) == "MyName"`, independent of the new default table —
  the override mechanism itself is untouched by this item.
- [ ] **AC5: `reference_verse_v1.json` is re-keyed, not re-fit.** After the
  swap, `load_artifact(bundled_production_reference_path())` has no `"S"` key
  under `levels`; `levels["L6"]["all"]["level_name"] == "L6"`; and
  `levels["L6"]["all"]["feature_stats"]` is **byte-for-byte identical** to the
  pre-rename artifact's `levels["S"]["all"]["feature_stats"]` (same
  percentile values, only the name changed) — no other key in the artifact
  changes.
- [ ] **AC6: `reference_default.json` is unaffected.** The synthetic Plane-1
  baseline's `levels` keys (`L1`...`L5` only) and every value are unchanged —
  confirmed by loading it before/after this item and comparing byte-for-byte.
- [ ] **AC7: the reference-delta rule resolves the renamed level correctly.**
  A per-case record whose label 25 resolves (via the new default convention)
  to `level_name == "L6"` and is scored against `bundled_production_reference()`
  finds a matching `reference.levels.get("L6")` entry (not `None`) — the
  rename keeps `reference_delta`'s label→artifact join surface consistent
  with the new convention (item 046's join, `reference/delta.py:333-339`).
- [ ] **AC8: existing label/heuristic/pipeline tests stay green with only the
  expected renamed-label assertions updated.** Running the full suite after
  the swap shows failures *only* in tests that hard-coded the old
  `"S"`/`"Cocygis"`/`"L6"(=29)` names as literal expected strings (updated as
  part of this item); no other test regresses.

## Assumptions

Clarify mode was forced to `interactive` for this batch; the following were
resolved with the user rather than defaulted:

- **Full TPTBox range (1–33) is adopted, not just the six previously-defined
  values.** Confirmed with the user, who noted real cohorts will often
  populate only a subset of the fine-grained sacral/coccygeal entries (a
  single generic sacrum, or `S1` + a merged rest) — this is expected and
  requires no special-casing: `LabelConvention` only defines what a *value*
  is called, and a given case's `label_inventory` is free to be sparse.
  Datasets using a genuinely different sacral scheme (e.g. one merged `"S"`
  label) remain served by `LabelConvention.from_mapping(...)`, unaffected by
  this item.
- **`reference_verse_v1.json`'s `"S"`-keyed entry is renamed to `"L6"` in
  place** (top-level `levels` key + nested `level_name` field), leaving the
  `feature_stats` percentile values untouched — confirmed with the user
  in preference to a code-level alias/compat table. This is the literal
  reading of the roadmap's "loads and scores unchanged — no re-fit ...
  required," and is correct because the artifact's `"S"`-named statistics
  were always built from raw label-25 voxels; under the legacy convention
  those voxels were mis-named `"S"`, and TPTBox's table shows they are
  actually `L6`. Renaming the key is fixing a pre-existing label-naming bug,
  not re-deriving anything. `reference_default.json` needs no equivalent
  edit because its fixed synthetic cohort never populates the sacral range
  (verified: `levels` keys are exactly `L1`...`L5`).
- **TPTBox is not imported by this item.** The table is hardcoded as a
  literal `Dict[int, str]` in `labels.py`, sourced from (but not read at
  runtime from) `TPTBox.core.vert_constants.v_idx2name`. Item 094 is what
  adds TPTBox as an installed dependency; sequencing the label-table swap
  first (queue-013's stated order: 093 → 095 → 094) means this item must not
  depend on TPTBox being installed.
- **`v_idx2name`'s subregion entries (`Location` enum values ≥ 40, merged
  into the raw TPTBox dict) are excluded.** Only the 1–33 vertebra range is
  adopted; TPTBox's own dict is a superset used only as the *source* of the
  literal values copied into `DEFAULT_LABEL_MAP`, not imported wholesale.
- **Dependency 044/045 (✅ merged) — the committed `reference_verse_v1.json`
  artifact and its schema.** This item edits the committed JSON file directly
  (a one-time re-key, checked in as a text diff, not regenerated via
  `build_reference`) rather than rebuilding it from a mounted real-VerSe
  cohort — no such cohort is guaranteed present in this environment, and
  rebuilding is unnecessary since the statistics do not change.

## Implementation Steps

All under `source_dir = src/segfacet`.

1. **`src/segfacet/labels.py`**:
   - Replace the `DEFAULT_LABEL_MAP` literal (currently `labels.py:71-105`)
     with the full TPTBox-derived 1–33 table. Keep the existing C1–T12
     (1–19) and `T13` (28) entries unchanged; change `25: "S"` → `25: "L6"`,
     `26: "Cocygis"` → `26: "S1"`; add `27: "Cocc"`, `29: "S2"`, `30: "S3"`,
     `31: "S4"`, `32: "S5"`, `33: "S6"`.
   - Update the module comment above `DEFAULT_LABEL_MAP` (currently
     documents the legacy "contiguous 1..26 block is classic VerSe
     ordering... TotalSegmentator's published label scheme") to instead
     name the TPTBox vertebra convention as the source, and note that
     integer order still does not equal anatomical order (kept for `L6`/`T13`).
   - Replace `CANONICAL_ORDER` (currently `labels.py:110-116`) with the new
     head-to-tail tuple per AC2.
   - No change to `LabelConvention`, `UNKNOWN`, `_normalise_name`,
     `_order_key`, `summarise_inventory`, or any other symbol in the module.
2. **`src/segfacet/reference/reference_verse_v1.json`**: re-key the `"S"`
   entry under `levels` to `"L6"`, and within that entry's value, change
   `"level_name": "S"` to `"level_name": "L6"`. No other field, key order
   (the file is a `sort_keys=True` JSON dump per `write_artifact`), or byte
   elsewhere changes. Regenerate the file's canonical serialization via
   `segfacet.reference.schema.to_json_text` after the edit (or hand-edit and
   verify byte-for-byte equivalence to what that function would produce) so
   the file stays in the exact format `write_artifact` emits — do **not**
   rebuild the artifact from a cohort.
3. **`src/segfacet/reference/reference_default.json`**: no edit (AC6 is a
   verification-only criterion).
4. Update any test module that hard-codes the legacy names (`"S"`,
   `"Cocygis"`, or label 29 named `"L6"`) as literal expected strings —
   search `tests/` for these three tokens used as label names (not, e.g.,
   as part of an unrelated word) and update the expected values to match
   the new convention.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_093_tptbox_label_convention.py`.
- **AC1/AC2/AC3:** parametrised tests over the full 1–33 range comparing
  `LabelConvention.default().name_of(v)` against a literal expected table
  (transcribed from TPTBox's `v_idx2name`, not imported from TPTBox);
  `CANONICAL_ORDER` compared as a literal tuple; a handful of
  `value_of`/`is_known` round-trips including a case-insensitive lookup and
  an explicitly unmapped value (`34`).
- **AC4:** a `LabelConvention.from_mapping` test exercising an override,
  unaffected by the default-table change (mirrors the existing override
  test in `tests/test_labels.py`, if one exists — reuse rather than
  duplicate).
- **AC5:** load `reference_verse_v1.json` via `load_artifact`, assert `"S"
  not in dist.levels`, `dist.levels["L6"]["all"].level_name == "L6"`, and
  compare `dist.levels["L6"]["all"].feature_stats` against a **pinned
  snapshot of the pre-rename `"S"` entry's `feature_stats`** (captured
  before editing the file, e.g. via `git show HEAD:...` in the test setup
  or a small fixture recorded ahead of the edit) for byte/value equality.
- **AC6:** load `reference_default.json` before/after (i.e. via `git diff`
  in a repo-level check, or a snapshot comparison) and assert no change.
- **AC7:** build a minimal per-case record with label 25 (resolving to
  `"L6"` under the new default convention) and call the existing
  `reference_delta` per-level lookup path (`reference/delta.py`) against
  `bundled_production_reference()`; assert the lookup succeeds (non-`None`)
  and returns a delta rather than an "unmatched level" outcome.
- **AC8:** run the full suite; grep the diff of failing tests before the
  fix-up to confirm every failure is a literal old-name assertion (not a
  new, unexpected failure), then update those assertions and confirm green.
- **Adversarial / edge cases:**
  - A raw label value present in a real inventory but outside 1–33 (e.g.
    an artifact/noise label) still resolves to `UNKNOWN`/`is_known() ==
    False`, unchanged.
  - `summarise_inventory` on an inventory containing only `{25: n}` sorts
    the single recognised entry using the new `CANONICAL_ORDER` rank
    without raising (exercises `_order_key`/`_CANONICAL_RANK` against the
    larger table).
  - Loading `reference_verse_v1.json` after the edit still passes
    `load_artifact`'s `schema_version` check and general JSON validity
    (the edit is a value/key change only, not a structural one).

## Dependencies

- **Items 044/045 (✅ merged) — consumed/edited.** Cohort ingestion +
  versioned-artifact machinery that originally produced
  `reference_verse_v1.json`; this item re-keys the committed file directly.
- **Item 046 (✅ merged) — consumed, unmodified.** The `reference_delta`
  per-level lookup (`reference/delta.py`) this item's AC7 exercises against
  the renamed artifact key.
- **Item 090 (✅ merged) — consumed, unmodified.** `bundled_production_reference()`
  / `bundled_production_reference_path()`, the accessor this item's AC5/AC7
  read through.
- **None** on any Stage-17 sibling item — this item is first in the queue's
  execution order specifically because nothing else in the stage depends on
  it, while items 094/096/097 (and any later stage touching level names)
  depend on this item landing first.

## Decisions & Trade-offs

To be updated during implementation.
