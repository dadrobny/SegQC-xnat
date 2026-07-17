# Item 089 — FOV-aware `coverage` and `border` rules

> **Created:** 2026-07-17 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 14 — Real-Data Grounding & Heuristic Recalibration (G3, G7)
> **Queue:** [`../queue/queue-012.md`](../queue/queue-012.md) · Item 089 *(first of
> three; opens Stage 14 — rule semantics fixed **before** any threshold is tuned to
> fit real data, so a mis-specified rule is not laundered into a calibrated constant)*
> **Objectives:** G3 (distinguish failure from legitimate variation — a partial
> field of view is legitimate variation, not a defect) and G7 (evaluable /
> regression-testable — the fix is proven on committed synthetic fixtures, no real
> data required)
> **Suggested branch:** `aide/089-fov-aware-coverage-and-border`

---

## Description

Teach the Stage-4 `coverage` (item 029, §6 mode 5) and `border` (item 031, §6
mode 6) rules the difference between **absence** and **absence of evidence**.
Real spine CT scans are legitimately *partial* — cervical-only, lumbar-only,
mid-thoracic, thoraco-lumbar — so a vertebra level that lies **outside the
scan's field of view (FOV)** is not a *missing level*, and the topmost /
bottommost segmented vertebra **abutting the FOV boundary** is not a *border
defect*. On the first real held-out VerSe19 measurement (2026-07-17) these two
rules contributed to 5/6 of the false positives (`coverage` 3/6, `border` 2/6);
the recalibration that follows (items 090/091) cannot succeed until the rules
stop counting a partial FOV as a failure.

The fix is **rule semantics, not a threshold**, and needs **no new external
data**: the FOV-covered level span is derived from the label map + image
geometry already in the per-case record — the **extremal segmented levels**
(`relationships.present_levels`) and their **proximity to the volume bounds**
(each label's `geometry.touches_*` border-contact flags, item 011). This item
introduces that derivation as a single **shared, unit-tested abstraction** and
threads it through both rules so they agree on one FOV-covered span:

- **`coverage`** — the expected-sequence check (check 2, item 029) is restricted
  to levels **expected inside the covered FOV**. A level absent *beyond* a span
  end that abuts the volume boundary (the FOV is truncated there) is outside the
  covered FOV → **not flagged**; a level absent immediately beyond a span end
  that sits *inside* the volume with headroom beyond it (the FOV demonstrably
  extends past the last segmented vertebra) **should have been captured** → still
  flagged. The always-on **missing-interior check (check 1, §6 mode 5) is
  unchanged**: an interior gap is bracketed above *and* below by segmented
  vertebrae, so the FOV provably covers it and it is always a genuine failure.

- **`border`** — a label touching an image border **at the ends of the covered
  span** (the terminal segmented vertebra abutting its cranio-caudal FOV-end
  face) is **normal** and suppressed, exactly as today; a label touching a
  **lateral / anterior / posterior (in-plane)** face, or an **interior** (non-
  terminal) label touching **any** face, **remains suspicious** and is flagged
  (§6 mode 6, genuine border truncation).

### The central new concept — the FOV-covered span

A new pure helper `derive_fov_coverage(record)` returns, from the per-case
record and nothing else, a small immutable descriptor of the covered span:

```
FovCoverage:
    superior_end_level : str | None   # relationships.present_levels[0]  (most superior present)
    inferior_end_level : str | None   # relationships.present_levels[-1] (most inferior present)
    superior_truncated : bool         # superior_end_level's geometry.touches_superior
    inferior_truncated : bool         # inferior_end_level's geometry.touches_inferior
    has_span           : bool         # present_levels non-empty and a span is determinable
```

Anatomy → image-face mapping is item 011's documented convention (unchanged):
the **cranio-caudal** axis is superior/inferior (`x == shape[0]-1` /
`x == 0`); the other four faces (`left`/`right`/`anterior`/`posterior`) are
**in-plane**. `present_levels` is in canonical head-to-tail order, so
`present_levels[0]` is the most-superior present level and `present_levels[-1]`
the most-inferior. "Proximity to the volume bound" is realised as the already-
computed exact border-contact flag (`touches_superior` / `touches_inferior`):
a truncated end is one whose extremal segmented vertebra abuts the corresponding
cranio-caudal volume face. Both rules read that one descriptor, so they can
never disagree about where the covered span ends.

### What this item is **not**

- **Not a threshold change / calibration.** No numeric threshold moves here.
  Re-deriving `bounds` / `fragmentation` tolerances from real per-level variation
  is **item 090**; the recalibration run + sensitivity guard is **item 091**.
- **Not a change to the always-on missing-interior semantics (§6 mode 5).** A
  genuinely missing interior level still fires `coverage` (requirement preserved
  and pinned by AC). Only the *beyond-a-span-end* (expected-sequence) firing
  becomes FOV-aware.
- **Not a change to what makes a `border` clip suspicious (§6 mode 6).** In-plane
  touches and interior cranio-caudal touches still fire; only the terminal
  covered-span-end truncation stays suppressed — its existing behaviour, now
  sourced from the shared descriptor.
- **Not an orientation / axis-detection feature.** The item keeps item 011's
  fixed cranio-caudal = `x`-axis convention (the convention the synthetic corpus
  and the new FOV fixtures are built in). Data-driven spine-axis detection for
  arbitrarily-oriented real volumes is a separate concern, out of scope, and
  recorded in Assumptions.
- **Not a voxel-margin "near the bound" proximity.** A tolerance-based proximity
  (extremal vertebra *within N voxels* of the bound without touching) would need
  the image shape threaded into the record (items 011/016) and risks the
  byte-reproducible golden fixtures; proximity is realised as the existing exact
  contact flag (see Assumptions). 
- **Not new synthetic-corpus generators or new committed goldens.** The FOV
  fixtures for this item are hand-built per-case records in the test module (the
  rules read only the record), mirroring items 029/031. The existing Stage-5
  corpus + its committed goldens must stay **byte-identical** under the default
  config (AC) — the change is behaviour-preserving on the default path and only
  manifests for partial-FOV inputs / an active expected sequence.

### The records these rules consume (unchanged shape)

```
record["relationships"] : {                 # item 014, or None
    "present_levels":  [str, ...],           # canonical head-to-tail order
    "missing_levels":  [str, ...],           # absent levels WITHIN the span (interior), canonical order
    ...
}
record["per_label"] : { "<label_int>": {
    "label": int,
    "level_name": str,                       # locates a level's geometry
    "geometry": {
        "touches_superior": bool,            # item 011 — superior (head) cranio-caudal face
        "touches_inferior": bool,            # item 011 — inferior (tail) cranio-caudal face
        "touches_left": bool, "touches_right": bool,
        "touches_anterior": bool, "touches_posterior": bool,
        ...
    },
    ...
} }
```

`per_label` is keyed by **integer label string**, not level name, so a span-end
level's geometry is located by scanning for a matching `level_name` (the pinned
lookup convention items 029/031 already use; a missing entry ⇒ treated as **not**
truncated — conservative, surfaces rather than hides).

### Config shape (read via `config.rule_param`, unchanged keys)

```yaml
rules:
  coverage:
    params:
      border_aware: true          # true (default): FOV-restrict the expected-sequence check.
                                   #   false: legacy behaviour — flag every absent
                                   #   expected level beyond a span end, ignoring the FOV.
      expected_levels: []          # opt-in expected canonical sequence (unchanged; disabled by default)
      expected_count: null         # opt-in raw minimum (unchanged; NOT border/FOV-aware)
      severity: flagged-for-review
  border:
    params:
      severity: flagged-for-review
      report_expected_ends: false  # unchanged
      end_severity: pass           # unchanged
```

No config keys are added or removed (so `default_config.yaml`, item 035's
exact-rule-id / default-materialisation tests, and item 045's `config_hash`
provenance are untouched). The behavioural change is entirely in how the two
rules interpret the record they already read.

---

## Acceptance Criteria

_Each criterion is atomic and directly testable — one test each. Tests
hand-build minimal per-case records (a `relationships` sub-dict with
`present_levels` / `missing_levels`, and a `per_label` map carrying `label`,
`level_name`, and a `geometry` dict of the six `touches_*` booleans) plus a
`HeuristicConfig` (via `default_config()` or a crafted `rules.<rule>.params`),
exactly as items 029/031 do. "Partial-FOV record" = a contiguous present span
whose extremal present levels touch their corresponding cranio-caudal faces
(the FOV cropped through them)._

### The shared FOV-covered-span helper

- [ ] **AC1: `derive_fov_coverage` reports the covered-span ends and their
      truncation.** For a record with `present_levels == ["T5", "T6", "T7"]`
      where `T5`'s geometry has `touches_superior == True` and `T7`'s has
      `touches_inferior == True`, the returned descriptor has
      `superior_end_level == "T5"`, `inferior_end_level == "T7"`,
      `superior_truncated == True`, `inferior_truncated == True`, and
      `has_span == True`.

- [ ] **AC2: a span end sitting inside the volume is reported not-truncated.**
      For the AC1 present span but with `T5.touches_superior == False` (headroom
      above the topmost present vertebra) and `T7.touches_inferior == True`, the
      descriptor has `superior_truncated == False` and `inferior_truncated ==
      True`.

- [ ] **AC3: the helper is conservative on a degenerate record.** For a record
      with `relationships` `None`/absent, or `present_levels == []`, or an empty
      `per_label`, `derive_fov_coverage` returns a descriptor with `has_span ==
      False` and both truncation flags `False`, and raises nothing. (A missing
      span-end `geometry`/`level_name` entry likewise yields `*_truncated ==
      False` — conservative: not truncated ⇒ nothing suppressed / surfaced.)

- [ ] **AC4: the helper is pure and deterministic.** Two calls on the same
      record return equal descriptors, and a deep before/after comparison shows
      the record is unmutated.

### `coverage` — FOV-aware expected-sequence check (§6 mode 5 preserved)

- [ ] **AC5: a genuinely missing interior level still fires (§6 mode 5
      unchanged).** For a record with `relationships.missing_levels == ["L3"]`
      (an interior gap bracketed by present neighbours), under `default_config()`,
      `coverage.evaluate` emits exactly one missing-interior `Finding`
      (`rule_id == "coverage"`, reason begins with the missing-interior tag,
      naming `L3`, `labels == frozenset()`) — identical to item 029's AC3.

- [ ] **AC6: an interior gap is never FOV-suppressed, even beside a clipped
      end.** For a record with an interior gap (`missing_levels == ["L3"]`) whose
      superior-most present level is FOV-truncated (`touches_superior == True`),
      under `default_config()` the missing-interior finding for `L3` **still
      fires** — the FOV-covered-span logic never suppresses an interior gap
      (bracketed levels are provably inside the FOV).

- [ ] **AC7: a clean partial-FOV scan fires no coverage finding (default
      config).** For a partial-FOV record — a contiguous present span (e.g.
      cervical-only `C1…C7`, lumbar-only `L1…L5`, or mid-thoracic `T5…T9`) with
      `missing_levels == []` and the extremal present levels touching their FOV-
      end faces — under `default_config()` (opt-in checks disabled),
      `coverage.evaluate` returns `[]`.

- [ ] **AC8: an out-of-FOV expected level beyond a truncated end is not
      flagged.** With `rules.coverage.params.expected_levels` set to a sequence
      that extends **beyond** the present span (e.g. present `L1…L5`, expected
      `C1…L5`) and the superior end FOV-truncated (`L1.touches_superior ==
      True`), `coverage.evaluate` emits **no** incomplete-span finding for the
      out-of-FOV levels (`C1…T12` are beyond a truncated end → outside the
      covered FOV).

- [ ] **AC9: an expected level immediately beyond a non-truncated end IS
      flagged.** With the same `expected_levels` extending beyond the present
      span but the span end sitting inside the volume (`present_levels[0]` does
      **not** touch its FOV-end face — headroom beyond the last segmented
      vertebra), the **immediately-adjacent** absent expected level beyond that
      end is flagged with an incomplete-span `Finding` (it should have been
      captured — a genuine miss inside the covered FOV).

- [ ] **AC10: expected levels far beyond a non-truncated end are not flagged.**
      In the AC9 configuration, absent expected levels ranked **more than one
      canonical step** beyond the non-truncated span end are **not** flagged —
      only the single adjacent level fires; the rest are outside the covered FOV
      (there is no evidence the FOV reached them).

- [ ] **AC11: `border_aware: false` reverts the expected-sequence check to
      legacy behaviour.** With `rules.coverage.params.border_aware == False` and
      `expected_levels` extending beyond a **truncated** span end (the AC8
      record), the rule flags **all** absent expected levels beyond the span end
      regardless of truncation — confirming the FOV-restriction is driven by the
      `border_aware` toggle, not an unconditional skip.

### `border` — covered-span-end truncation normal, everything else suspicious (§6 mode 6 preserved)

- [ ] **AC12: a clean partial-FOV scan fires no border finding (default
      config).** For a partial-FOV record whose terminal present vertebrae touch
      **only** their covered-span-end faces (`present_levels[0].touches_superior`
      and/or `present_levels[-1].touches_inferior`, no in-plane touch), under
      `default_config()`, `border.evaluate` returns `[]`.

- [ ] **AC13: an in-plane touch on a terminal vertebra still fires (§6 mode 6
      unchanged).** For the superior-most present level touching **both**
      `touches_superior` **and** `touches_left` (a lateral clip at the covered-
      span end), `border.evaluate` emits exactly one `border` finding — an
      in-plane/lateral touch is suspicious even at a covered-span end (item 031
      AC8 preserved).

- [ ] **AC14: an interior vertebra touching a cranio-caudal face still fires (§6
      mode 6 unchanged).** For a vertebra that is neither `present_levels[0]` nor
      `present_levels[-1]` and touches `touches_superior` (or `touches_inferior`),
      `border.evaluate` emits exactly one `border` finding — a mid-span (interior)
      truncation is suspicious (item 031 AC7 preserved).

- [ ] **AC15: `border` and `coverage` agree on the covered-span ends.** For one
      partial-FOV record, the terminal vertebra `border` suppresses as an
      expected covered-span-end truncation is the same level `derive_fov_coverage`
      reports as the (truncated) `superior_end_level` / `inferior_end_level` —
      both rules resolve the covered span through the one shared helper (verified
      by asserting the helper's descriptor matches the vertebra `border` treats
      as terminal for the same record).

### Consistency / regression

- [ ] **AC16: the default path is behaviour-preserving — Stage-5 goldens stay
      byte-identical.** Running the existing Stage-5 full-pipeline regression
      suite + golden-snapshot comparison (items 041/042) under `default_config()`
      after this change produces **no** change to any committed golden — the
      `coverage` / `border` output for every existing corpus fixture is
      unchanged (the FOV-restriction only alters output for partial-FOV inputs or
      an active `expected_levels`, neither exercised by the default-config
      goldens). *If a golden must change, it is re-recorded with an explicit
      justification per the queue's Stage-5 clause — not silently.*

- [ ] **AC17: neither rule mutates the record and both stay deterministic.**
      `coverage.evaluate` and `border.evaluate` each leave the record (including
      nested `relationships`, `per_label`, and `geometry`) unchanged under deep
      equality, and two successive `run_rules(record, cfg)` calls return equal
      finding lists in the same order — the standard item-029/031 contract holds
      after the refactor.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

Clarify mode is `assume` (unattended). Each defensible default taken to turn the
one-line queue entry into a concrete, testable design is recorded here for the
validator to surface at the queue boundary.

- **"Proximity to the volume bounds" is realised as the existing exact border-
  contact flag (`touches_superior` / `touches_inferior`), not a voxel margin.**
  The per-case record carries per-label `bbox_voxel` and the six `touches_*`
  booleans but **not** the image shape, so a tolerance-based "within N voxels of
  the bound without touching" proximity is not computable inside the rule layer.
  A truncated end is therefore one whose extremal segmented vertebra *abuts* the
  cranio-caudal volume face. A margin-based proximity would require threading the
  image shape into the record (items 011/016) and re-recording the byte-golden
  fixtures — out of scope for this heuristics-only item. **Pinned:** if a later
  item adds a case-level image-shape/margin field, the helper can be upgraded
  without changing its call sites.

- **The FOV-covered span is `[present_levels[0] .. present_levels[-1]]`, bounded
  by the extremal *segmented* levels.** Levels beyond that span are outside the
  covered FOV **unless** the span end is non-truncated (headroom), in which case
  the FOV demonstrably extends past the last segmented vertebra and the **single
  immediately-adjacent** canonical level beyond that end is treated as inside the
  covered FOV (a plausible genuine miss). Flagging only the one adjacent level
  (not the whole remaining sequence) is the conservative floor available without
  a measurable FOV extent — it directly prevents the failure mode where a
  lumbar-only scan whose `L1` merely fails to touch the top voxel face flags the
  entire absent cervico-thoracic spine. Recorded as a trade-off (see Decisions).

- **The always-on missing-interior check (§6 mode 5) is left semantically
  unchanged.** An interior gap is bracketed above and below by segmented
  vertebrae, so the FOV provably covers it — it is always genuine and is never
  FOV-suppressed (AC6). Only the beyond-a-span-end (expected-sequence) firing
  becomes FOV-aware. The queue's "restrict coverage's expected-sequence check to
  levels expected inside the FOV" names exactly that check; "keep the existing
  failure semantics intact for genuinely missing interior levels" names check 1.

- **`border`'s expected-vs-unexpected classification is preserved; only its
  terminal-end determination is re-sourced from the shared helper.** Item 031's
  behaviour — in-plane touch ⇒ flag; interior cranio-caudal touch ⇒ flag;
  terminal cranio-caudal touch (only) ⇒ suppress — already matches the queue's
  requirement 3. This item routes the "is this the covered-span end?" decision
  through `derive_fov_coverage` so `border` and `coverage` share one source of
  truth, without changing `border`'s output on any existing fixture.

- **Item 011's fixed cranio-caudal = `x`-axis convention is retained.** The
  synthetic corpus and the new FOV fixtures are built in that convention. On a
  real arbitrarily-oriented volume the FOV-end axis may not be `x`; robust,
  data-driven spine-axis detection is a **separate** concern (a candidate future
  item), explicitly out of scope here and noted so the validator does not read
  its absence as a miss. This item's testable bar is stated over synthetic
  fixtures, which this convention satisfies.

- **A new pure helper module `src/segqc/heuristics/fov.py` hosts the shared
  derivation.** It registers no rule (so `heuristics/__init__.py`'s registration
  imports and the item-035 rule-id set are untouched); `coverage.py` and
  `border.py` import `derive_fov_coverage` from it. Placing the derivation in one
  module (rather than duplicating it in each rule) is what makes the two rules
  provably agree (AC15) and lets AC1–AC4 test the derivation in isolation.

- **No config keys are added or removed and `default_config.yaml` is not
  edited.** `coverage.border_aware`, `expected_levels`, `expected_count`,
  `severity` and `border.severity`, `report_expected_ends`, `end_severity` are
  the existing keys (item 029/031/035). Keeping the parsed config dict identical
  preserves item 035's default-materialisation / exact-rule-id tests and item
  045's `config_hash` provenance. If reality diverges (e.g. a key was renamed),
  the builder/validator hands back.

- **Dependencies 029, 031, 011, 014, 016, 026, 034 are `✅` (merged).** The rules,
  the engine core, the geometry border flags, the relationships block, and the
  assembler all exist in the merged tree. This item consumes their record shapes
  and modifies only the two rule modules plus the new helper.

## Implementation Steps

Intended code path — all under `source_dir = src/segqc`: one new pure helper
module plus focused edits to the two existing rule modules. **No** change to the
engine core, `config.py`, `default_config.yaml`, the report/schema, the
extractors, or `heuristics/__init__.py`'s registration block.

1. **Create `src/segqc/heuristics/fov.py`** (pure; registers nothing):
   - Import `CANONICAL_ORDER` from `segqc.labels` (for the adjacent-level
     comparison) and build a module-level `_CANONICAL_RANK` map, mirroring
     `coverage.py`.
   - Define a frozen `FovCoverage` dataclass with the fields in the Description
     (`superior_end_level`, `inferior_end_level`, `superior_truncated`,
     `inferior_truncated`, `has_span`), plus convenience methods/attributes the
     rules need — e.g. the canonical ranks of the two end levels and predicates
     `is_beyond_superior(rank)` / `is_beyond_inferior(rank)` and
     `superior_adjacent_rank` / `inferior_adjacent_rank` (the one-step-beyond
     ranks) — the builder's choice, but keep the surface minimal and documented.
   - Implement `derive_fov_coverage(record) -> FovCoverage`:
     - Read `rel = record.get("relationships")`; if not a mapping or
       `present_levels` empty ⇒ return `FovCoverage(has_span=False, ...,
       superior_truncated=False, inferior_truncated=False)` (AC3).
     - `superior_end_level = present_levels[0]`, `inferior_end_level =
       present_levels[-1]`.
     - Locate each end level's `geometry` by scanning `record.get("per_label",
       {})` for a matching `level_name` (reuse item 029's `_find_entry_by_level_
       name` pattern — factor it here or duplicate the tiny helper); a missing
       entry ⇒ that flag is `False`.
     - `superior_truncated = bool(geom_of(superior_end_level).get(
       "touches_superior"))`; `inferior_truncated = bool(geom_of(inferior_end_
       level).get("touches_inferior"))`.
     - Never mutate the record; build only fresh values (AC4).

2. **Edit `src/segqc/heuristics/coverage.py`** — make check 2 FOV-aware:
   - Import `derive_fov_coverage` from `segqc.heuristics.fov`.
   - Leave **check 1 (missing interior)** and **check 3 (expected count)**
     exactly as they are (AC5, AC6; count stays raw / non-FOV-aware).
   - In **check 2 (expected span)**: when `border_aware` (default `True`), call
     `fov = derive_fov_coverage(record)` once, then for each absent expected
     level beyond a span end:
     - beyond the **superior** end (`rank < rank(present_levels[0])`): flag it
       **iff** `not fov.superior_truncated` **and** it is the immediately-adjacent
       level (`rank == fov.superior_adjacent_rank`); otherwise suppress (AC8, AC9,
       AC10).
     - beyond the **inferior** end: symmetric with `inferior_truncated` /
       `inferior_adjacent_rank`.
     - interior ranks (strictly between the two ends) remain excluded from check
       2 (owned by check 1), as today.
   - When `border_aware` is `False`, keep the **legacy** behaviour: flag every
     absent expected level beyond a span end regardless of truncation (AC11).
   - Preserve the fixed finding order, tags, case-level `labels == frozenset()`,
     severity handling, and record-immutability (AC17).

3. **Edit `src/segqc/heuristics/border.py`** — re-source terminal-end detection
   from the shared helper:
   - Import `derive_fov_coverage`. Replace the local
     `superior_end`/`inferior_end` derivation (`present_levels[0]`/`[-1]`) with
     the descriptor's `superior_end_level` / `inferior_end_level`.
   - Keep the classification identical: `expected` iff `not in_plane` **and**
     (`touches_superior` absent or this label is the superior covered-span end)
     **and** (`touches_inferior` absent or this label is the inferior covered-span
     end). In-plane touches and interior cranio-caudal touches stay unexpected
     (AC13, AC14). Suppress the expected terminal covered-span-end truncation by
     default (AC12), preserving `report_expected_ends` / `end_severity`.
   - The observable behaviour on existing fixtures is unchanged — this is a
     consistency refactor that guarantees `border` and `coverage` share one
     covered-span source (AC15) and keeps the goldens byte-identical (AC16).

4. **Do not** touch `heuristics/__init__.py` registration, `config.py`,
   `default_config.yaml`, `runner.py`, `rule.py`, `finding.py`, `feature_report.py`,
   `report.py`, `geometry.py`, `relationships.py`, or any extractor. All params
   flow through the existing `rule_param` accessors; the only new import edges are
   `coverage.py → fov.py` and `border.py → fov.py`.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_089_fov_aware_coverage_border.py`
  (naming matches the `test_0NN_*` siblings). Use the item-026 registry
  snapshot/restore fixture (save/restore `segqc.heuristics.rule._RULES`) as
  `tests/test_029_*` / `tests/test_031_*` do.
- **Hand-built records:** a small helper assembles a record from
  `(present_levels, missing_levels, touched_faces_by_level)` — a `relationships`
  sub-dict plus a `per_label` map keyed by integer-label string, each entry
  carrying `label`, `level_name`, and a `geometry` dict with the six `touches_*`
  booleans (default all `False`, set only the named touched faces). The rules
  read only these fields, so no extractor stack or NIfTI I/O is needed (mirrors
  items 029/031). Use the default convention's integer labels where label
  attribution matters.
- **One focused test per AC (AC1–AC17):**
  - Helper: end-level + truncation reporting (AC1), non-truncated end (AC2),
    degenerate/conservative (AC3), purity/determinism (AC4).
  - Coverage: interior gap fires (AC5); interior gap beside a clipped end still
    fires (AC6); clean cervical-only / lumbar-only / mid-thoracic partial-FOV
    records silent under default config (AC7 — one parametrised test across the
    three crops); out-of-FOV beyond a truncated end suppressed (AC8); adjacent
    beyond a non-truncated end flagged (AC9); far-beyond a non-truncated end
    suppressed (AC10); `border_aware: false` legacy (AC11).
  - Border: clean partial-FOV silent (AC12); terminal + in-plane fires (AC13);
    interior cranio-caudal fires (AC14); helper/border agree on the covered-span
    end (AC15).
  - Consistency: Stage-5 goldens byte-identical under default config (AC16 —
    assert by running the existing item-041/042 regression path, or by a targeted
    equivalence check that the default-config `coverage`/`border` findings for the
    committed corpus fixtures are unchanged); immutability + determinism (AC17).
- **Adversarial / edge cases (beyond the ACs):**
  - **Single-present-level record** (`present_levels` length 1): `has_span` is
    still derivable (both ends the same level); no crash; coverage/border behave
    sensibly (no beyond-end firing without an expected sequence).
  - **Span end whose `geometry`/`level_name` is missing from `per_label`**:
    treated as not-truncated (conservative) — coverage does not suppress, border
    surfaces (no crash) — pins AC3's conservative branch.
  - **`expected_levels` containing the adjacent level on BOTH a truncated and a
    non-truncated end in one record**: only the non-truncated end's adjacent
    level fires (isolates the two ends independently).
  - **A transitional level (e.g. `T13`, `L6`) as the immediately-adjacent beyond-
    end canonical neighbour**: the adjacency comparison is by `CANONICAL_ORDER`
    rank and does not crash on transitional entries (documents the interaction
    without expanding scope — transitional-anatomy handling is a separate
    concern).
  - **`border_aware: false` with a non-truncated end**: legacy flags all
    beyond-end absent expected levels (complements AC11's truncated-end case).
  - Severity override + unrecognised-severity `ValueError` paths for both rules
    still hold (item 029/031 contract regression).

## Dependencies

- **Item 029 (✅ merged) — MODIFIED.** The `coverage` rule; this item makes its
  check-2 expected-sequence firing FOV-aware and leaves checks 1/3 intact.
- **Item 031 (✅ merged) — MODIFIED.** The `border` rule; this item re-sources its
  terminal-end determination from the shared helper, preserving its behaviour.
- **Item 011 (✅ merged) — consumed.** Per-label `geometry.touches_*` border-
  contact flags — the "proximity to the volume bound" signal the helper reads.
- **Item 014 (✅ merged) — consumed.** `relationships.present_levels` (canonical
  order) — the extremal segmented levels bounding the covered span — and
  `missing_levels` (interior gaps) that check 1 keeps firing on.
- **Item 016 (✅ merged) — consumed.** `build_features_block` assembles the
  `per_label` + `relationships` record shape both rules read.
- **Item 026 / 034 (✅ merged) — used, not modified.** The engine core
  (`Rule`, `register_rule`, `run_rules`, `Finding`) and verdict aggregation that
  the (unchanged) rule surfaces plug into.
- **Items 041 / 042 (✅ merged) — regression target.** The Stage-5 full-pipeline
  regression suite + golden snapshots that AC16 must keep green under the default
  config.
- **Downstream:** **090** (reference-derived bounds/tolerances by default) and
  **091** (recalibration run + anti-gaming sensitivity guard, Stage-14 closure)
  depend on this item's FOV-aware semantics being in place first — a partial FOV
  must be a non-defect before any threshold is tuned to fit real data. Item 091's
  sensitivity guard also relies on §6 modes 5/6 still firing on genuine failures
  (AC5, AC6, AC13, AC14).

## Decisions & Trade-offs

To be updated during implementation.

Initial design decisions carried from this spec (confirm or revise while
building):

- **One shared, unit-tested `FovCoverage` abstraction, not duplicated logic.**
  The item's whole point is that `coverage` and `border` agree on *one*
  FOV-covered span; a shared helper (AC1–AC4, AC15) makes that structural rather
  than coincidental, and lets the derivation be tested in isolation.
- **Proximity == exact border contact** (no voxel margin), because the image
  shape is not in the record. Documented in Assumptions; upgradeable later
  without changing call sites. Trade-off: a partial vertebra clipped to a 1–2
  voxel background gap (not touching the exact face) reads as non-truncated —
  the conservative direction (may surface a borderline case rather than hide it).
- **Beyond a non-truncated end, flag only the single immediately-adjacent level.**
  Without a measurable FOV extent this is the conservative floor that still
  honours the queue's "a level that should be inside the covered FOV is a genuine
  failure" while preventing the catastrophic over-flag (a lumbar-only scan whose
  topmost vertebra merely fails to touch the top voxel face flagging the entire
  absent cervico-thoracic spine). Trade-off: under-reports when a non-truncated
  FOV genuinely had room for two or more missed levels — accepted as the safe
  direction for a false-positive-reduction item, and revisitable if a measurable
  FOV extent becomes available.
- **§6 mode 5 (interior gaps) and mode 6 (in-plane / interior clips) semantics
  are deliberately preserved** (AC5, AC6, AC13, AC14) so item 091's sensitivity
  guard cannot regress on the genuine-failure side — the anti-gaming constraint
  the queue names explicitly.
- **No config surface change** (Assumptions) so item 035's default tests and item
  045's `config_hash` provenance, and the committed Stage-5 goldens (AC16), stay
  green — the FOV-awareness is a semantic refinement of how the existing record
  and config are interpreted, not a new knob.
