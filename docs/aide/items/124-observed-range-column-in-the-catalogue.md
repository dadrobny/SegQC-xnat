# Item 124 — Observed-range column in the generated feature catalogue

> **Created:** 2026-08-30 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 28 — Spinal Curve Model: Formulation, Offset & Orientation (deliverable **D7**)
> **Queue:** [`../queue/queue-017.md`](../queue/queue-017.md) · Item 124
> **Objectives:** G7 (evaluable & regression-testable — the standing instrument
> that says whether a catalogued feature carries signal at all); G3 indirectly
> (a feature that cannot vary cannot separate failure from variation)
> **Suggested branch:** `aide/124-observed-range-column-in-the`

---

## Description

The generated catalogue (`docs/aide/feature_catalogue.generated.json` / `.md`,
item 103) records, for each of its **138** leaf paths, what a feature *is*:
what it measures, how it is computed, its units, which rules read it, which §6
modes it anchors. Item 104's drift test keeps that current, and the
`computation` column is accurate everywhere. Nothing in it records what a
feature **does**.

That is the gap Stage 28 exists because of. Before item 123,
`stage3.per_label_offsets[].offset_mm` had a perfectly healthy catalogue row —
accurate prose, a named consuming rule (`mislabel`), a mode anchor — while its
value was zero on every case the project had ever run, synthetic and real
alike. Its `status` read `retune`, a value shared with 66 of the 138 rows, so
it discriminated nothing. The defect was found in August 2026 by a hand sweep,
having survived from item 018 and through a reference build over 59 real
VerSe19 subjects.

This item adds the missing column: for every numeric leaf path, the **observed
range** across two independent populations, plus a derived verdict, generated
the same way as the rest of the catalogue and never hand-maintained.

**Why two populations, and why the second one is load-bearing.** A constant
value has two entirely different causes, and the synthetic corpus cannot tell
them apart:

- **Genuinely dead.** The feature is structurally incapable of varying —
  pre-123 `offset_mm`.
- **Legitimately constant here.** All nine corpus fixtures are the same
  30×25×25 box built from one base (Stage 21's premise), so 153 golden paths
  are constant for reasons that say nothing about the feature. Measured on the
  in-package driver set (2026-08-30), 36 of its 99 numeric paths are exactly
  constant — `stage3.per_label_offsets[].dy_mm`, for instance, spans
  `-2.84e-14 .. 3.55e-14` mm because the synthetic curve is planar in x–z, which
  is a property of the fixture, not of the feature.

Only real-GT evidence separates the two, so **only the reference population may
produce the "this feature is dead" verdict**. The corpus population reports its
numbers and explicitly declines to accuse.

**What the verdict is calibrated against.** Measured 2026-08-30 across all
levels of `reference_verse_v1.json`:

| | `spline_offset_mm` global min | global max |
|---|---|---|
| pre-123 (`ae3e9f4`, `splprep(..., s=0)`) | `5.93e-10` mm | **`3.08e-04` mm** |
| post-123 (shipped) | `2.34e-08` mm | **`18.5103` mm** |

The discriminating statistic is the population's **magnitude** —
`max(abs(min), abs(max))` — not its span and not its coefficient of variation.
CoV was `1.3` on the dead pre-123 feature, so a relative measure would have
missed it entirely; what made it dead is that *every* value was indistinguishable
from zero. The magnitude of the smallest legitimate feature in the shipped
reference is `1.0` (`largest_component_fraction`), three decades above the
`3.08e-04` mm of the dead one. The floor is placed inside that gap at **`1e-3`**
— one micron, three orders of magnitude below the finest achievable CT voxel
spacing, and equally negligible read as HU, as a count, or as a dimensionless
ratio.

**What this item is not.** It adds no extractor, no rule, no threshold, and
changes no `status` value or `STATUS_OVERRIDES` entry — `status` remains the
authored/derived field item 103 defined, and the observed range is reported
beside it, never folded into it. It does not recompute anything from the VerSe19
cohort: the reference population is read from the **committed** artifact, so
generation stays hermetic and byte-reproducible on a machine with no dataset. It
does not read `tests/corpus/golden/*.json` (see Assumptions).

## Acceptance Criteria

- [ ] **AC1: Every numeric path carries a corpus range.** For every catalogue
      entry whose driver-record values include at least one numeric value, the
      generated JSON entry has an `observed.corpus` object with `covered: true`
      and non-null `count`, `minimum`, `maximum`, `span` and `magnitude`.

- [ ] **AC2: Every reference feature resolves to exactly one leaf path.** Each
      of the 21 names in `reference_verse_v1.json`'s `features` list resolves to
      exactly one catalogue leaf path, and no name is left unresolved.

- [ ] **AC3: Reference-covered paths carry a reference range.** For every leaf
      path AC2 resolves a reference feature onto, the generated JSON entry has an
      `observed.reference` object with `covered: true` and non-null `count`,
      `minimum`, `maximum`, `span` and `magnitude`, aggregated across every
      (level, stratum) whose `feature_stats` carry that feature.

- [ ] **AC4: An uncovered path is marked uncovered, not zero.** For a leaf path
      no reference feature resolves onto, `observed.reference` has
      `covered: false` and `minimum`, `maximum`, `span`, `magnitude` all `null`
      — never `0`, never omitted.

- [ ] **AC5: A dead reference feature is flagged.** Given a reference
      distribution in which one feature's stats are all within the negligibility
      floor (min `5.93e-10`, max `3.08e-04` — the pre-123 `spline_offset_mm`
      magnitudes), the leaf path that feature resolves onto gets
      `observed.verdict == "degenerate"`.

- [ ] **AC6: A legitimately-constant synthetic path is not flagged.** A leaf
      path whose corpus magnitude is at or below the floor, realised by
      non-placeholder drivers and covered by no reference feature, gets
      `observed.verdict == "constant-synthetic"` — never `"degenerate"`.

- [ ] **AC7: A placeholder-only path is marked as such.** A leaf path realised
      only by the `image_features` / `reference_delta` placeholder drivers and
      covered by no reference feature gets `observed.verdict == "placeholder"`.

- [ ] **AC8: The placeholder driver ids are live.** Every driver id named in the
      placeholder-tier constant appears among the ids `iter_driver_records()`
      actually yields, so renaming a driver fails loudly instead of silently
      reclassifying its paths.

- [ ] **AC9: The verdict vocabulary is closed.** Every entry's
      `observed.verdict` is one of exactly `"varies"`, `"degenerate"`,
      `"constant-synthetic"`, `"placeholder"`, `"non-numeric"`, `"unobserved"`.

- [ ] **AC10: The shipped catalogue reports no degenerate feature.** The
      committed `feature_catalogue.generated.json`, built against the committed
      `reference_verse_v1.json`, contains zero entries with
      `observed.verdict == "degenerate"`.

- [ ] **AC11: `offset_mm` reads as varying.** In the committed artifact,
      `stage3.per_label_offsets[].offset_mm` has
      `observed.verdict == "varies"` and an `observed.reference.magnitude`
      greater than `1.0`.

- [ ] **AC12: The JSON carries a summary block.** The generated JSON has a
      top-level `observed_summary` object whose keys are the AC9 verdict
      vocabulary and whose values are the integer entry counts for each, summing
      to the total number of catalogue entries.

- [ ] **AC13: The Markdown gains an observed-range column.** The generated
      Markdown table header contains a cell `observed range`.

- [ ] **AC14: The Markdown gains an observed-verdict column.** The generated
      Markdown table header contains a cell `observed verdict`, and every data
      row's cell in that column is one of the AC9 vocabulary values.

- [ ] **AC15: Emitted floats are quantised.** Every float emitted under
      `observed` in the JSON equals `float(f"{value:.6g}")` — the value it would
      round-trip to at six significant digits.

- [ ] **AC16: Regeneration is byte-identical run-to-run.** Two successive
      `python -m segfacet.catalogue` runs in one session write byte-identical
      JSON and byte-identical Markdown.

- [ ] **AC17: The committed artifacts match a fresh regeneration.** Both
      committed catalogue documents are byte-identical to a fresh regeneration
      on the current tree.

- [ ] **AC18: The entry set is unchanged.** The regenerated catalogue's sorted
      leaf-path set is exactly the sorted leaf-path set of the pre-item-124
      committed artifact — 138 paths, none added, none removed.

- [ ] **AC19: The schema version is bumped.** The generated JSON's
      `schema_version` is `"1.1"`.

- [ ] **AC20: The status report accepts the new schema.** `scripts/
      aide_status_report.py`'s `load_feature_catalog`, given the committed
      catalogue, returns a non-empty tuple of `FeatureGroupSpec`.

- [ ] **AC21: A missing reference degrades, never raises.** With the reference
      artifact absent or unparseable, the catalogue still builds: every entry's
      `observed.reference.covered` is `false` and no exception is raised.

- [ ] **AC22: The reference source is injectable.** `python -m
      segfacet.catalogue` accepts a `--reference PATH` argument and builds the
      catalogue's reference population from that artifact instead of the bundled
      one.

- [ ] **AC23: No reference feature name is resolved ambiguously.** A reference
      feature name whose last-segment match hits more than one leaf path resolves
      to none of them and contributes no reference coverage, mirroring item 110's
      AC11b discipline for the static rule scan.

## Assumptions

- **The corpus population is `catalogue.iter_driver_records()`, not
  `tests/corpus/golden/*.json`.** The queue calls it "the corpus run", which
  could be read either way; the driver set is the defensible reading for three
  reasons. (1) `catalogue.py` ships inside the installed package and `tests/`
  does not, so a golden-reading generator would produce an empty column from a
  wheel. (2) `iter_driver_records`'s documented contract is that its source
  "names no path under the tests directory", precisely so item 104's drift test
  never needs a second driver set; reading the goldens would retire that
  contract. (3) The goldens are *report*-shaped, not feature-record-shaped, so
  their paths would need a second remapping the catalogue does not have. The
  consequence, which the spec states rather than hides: the "153 paths constant
  across the goldens" figure quoted in `roadmap.md` and `progress.md` is a
  different measurement from this column's corpus population, and the two counts
  will not match.

- **The reference population is the committed `reference_verse_v1.json`,
  read via `reference.artifact.bundled_production_reference()`.** Not
  `reference_default.json` (a five-subject synthetic cohort, which would be a
  second synthetic population rather than an independent one), and not a live
  recomputation over the VerSe19 cohort (reachable only through a gitignored,
  machine-local symlink — generation must stay hermetic and byte-reproducible on
  a machine with no dataset).

- **`NEGLIGIBLE_MAGNITUDE = 1e-3`, applied to `max(abs(min), abs(max))`.**
  Calibrated against the measurement in the Description: it sits `3.2x` above the
  dead pre-123 `spline_offset_mm` magnitude (`3.08e-04` mm) and three decades
  below the smallest legitimate magnitude in the shipped reference (`1.0`,
  `largest_component_fraction`). Magnitude rather than span, and rather than any
  relative measure: the pre-123 feature had CoV `1.3`, so a relative test would
  have passed it. One unit-agnostic floor rather than a per-unit table, because
  `1e-3` is negligible read as mm, as HU, as a count and as a ratio alike.

- **Only the reference population can produce `degenerate`.** The corpus
  population never accuses, however flat it is. This is the queue's explicit
  cry-wolf requirement, and its honest cost is that the instrument guards only
  the **21 of 99** numeric paths the reference vocabulary covers; the other 78
  get their numbers reported and no verdict stronger than
  `constant-synthetic`. That limitation belongs in the generated note, not only
  in this spec.

- **Reference-name to leaf-path resolution is derived, never hand-typed**, in
  three ordered rules: (1) the inverse of `feature_docs.PATH_ALIASES`
  (`spline_offset_mm` → `stage3.per_label_offsets[].offset_mm`); (2) a name in
  `reference.ingest.INGESTED_INTENSITY_FEATURES`, whose `intensity_` prefix
  stripped gives the last segment of a path under
  `image_features.per_label.{label}.first_order` (13 names); (3) otherwise the
  unique leaf path whose last segment equals the name, with no resolution at all
  when the match is ambiguous (AC23). Measured 2026-08-30, these resolve all 21
  reference features: 1 by rule (1), 13 by rule (2), 7 by rule (3).

- **`SCHEMA_VERSION` moves `"1.0"` → `"1.1"`, and
  `scripts/aide_status_report.py`'s `_FEATURE_CATALOGUE_SCHEMA_VERSION` moves
  with it.** That constant is an exact-equality gate: leaving it at `"1.0"` makes
  `load_feature_catalog` return `()` silently, which turns the HTML report's
  Feature Catalogue section empty and fails
  `test_103_feature_catalogue.py::test_ac22_rendered_section_markup_shape`.

- **Emitted floats are quantised to six significant digits.** The committed
  catalogue is compared **byte-exactly** against a fresh regeneration by four
  test modules (103, 106, 119/120/122), unlike the goldens, which item 078
  relaxed to a numeric tolerance. Observed ranges are NumPy/SciPy-derived floats
  and would otherwise put ~1-ULP cross-platform noise into a byte-compared
  artifact. Six significant digits is far more precision than the column's
  purpose needs and removes the noise entirely.

- **Item 123's shipped state is pinned as this item's baseline:** 138 catalogue
  entries; `reference_verse_v1.json` at `build_date 2026-08-29`, 21 features, 23
  levels carrying `spline_offset_mm`, global range `2.34e-08 .. 18.5103` mm. If
  the builder finds any of these has moved, hand back rather than adjusting the
  ACs — the reference population is this item's evidence base.

- **No human gate.** Item 124 is independent of Stage 28's formulation gate
  (approved 2026-08-27) and raises none of its own.

## Implementation Steps

1. **New module `src/segfacet/observed_range.py`.** Public API:
   `NEGLIGIBLE_MAGNITUDE`, `PopulationRange`, `ObservedRange`,
   `iter_leaf_values(record) -> dict[str, list[float | Any]]`,
   `resolve_reference_features(leaf_paths) -> dict[str, str]`,
   `build_observed_ranges(*, driver_records=None, reference=None) -> dict[str, ObservedRange]`.
   Follow `catalogue.py`'s house style: heavy imports (`segfacet.catalogue`,
   `segfacet.reference.*`) deferred into function bodies, so importing this
   module alone stays cheap and no import cycle forms.

2. **`iter_leaf_values`** — a value-collecting sibling of
   `catalogue._walk_leaf_paths`, keyed by the same `normalise_leaf_path` output.
   Differs in one way that matters: for a **scalar list** (e.g.
   `stage3.curvature.tangent_angles_deg[]`) it collects every element's value,
   not just the path. `bool` is never numeric (`isinstance(v, bool)` is checked
   before `isinstance(v, (int, float))`); `None` is skipped.

3. **`PopulationRange`** (frozen dataclass): `population`, `source`, `covered`,
   `count`, `minimum`, `maximum`, `span`, `magnitude`, `informative`.
   `span = maximum - minimum`; `magnitude = max(abs(minimum), abs(maximum))`;
   `informative = magnitude > NEGLIGIBLE_MAGNITUDE`. Every numeric field is
   `None` when `covered` is false (AC4).

4. **The corpus population.** Over `iter_driver_records()`, accumulate each
   path's numeric values and the set of driver ids that realised it. Record the
   driver ids on the `PopulationRange.source` so the audit trail survives into
   the artifact. `_PLACEHOLDER_DRIVER_IDS = ("image_features", "reference_delta")`
   — the two augmented drivers, named in `iter_driver_records`'s "Two augmented
   drivers" block — with a comment pointing there and AC8's guard behind it.

5. **The reference population.** Load through
   `reference.artifact.bundled_production_reference()` (or the injected
   artifact), wrapped so a missing/unparseable/mis-versioned artifact yields an
   uncovered population rather than an exception (AC21). Resolve names to leaf
   paths by the three ordered rules in Assumptions. For each resolved path,
   aggregate across every `(level, stratum)` whose `feature_stats` carry that
   feature: `minimum = min(stats.min)`, `maximum = max(stats.max)`,
   `count = sum(stats.count)`.

6. **`ObservedRange`** (frozen dataclass): `numeric`, `corpus`, `reference`,
   `verdict`. The verdict is derived by these ordered rules, first match wins:
   1. `"unobserved"` — no value of any kind realised, and no reference coverage.
   2. `"non-numeric"` — values realised but none numeric, and no reference
      coverage.
   3. `"degenerate"` — reference covered and **not** `informative`.
   4. `"placeholder"` — no reference coverage, and every driver that realised the
      path is in `_PLACEHOLDER_DRIVER_IDS`.
   5. `"varies"` — corpus `informative` or reference `informative`.
   6. `"constant-synthetic"` — otherwise.

   Order is load-bearing twice: rule 3 must precede rule 5 so real-GT death wins
   over synthetic spread, and rule 4 must precede rule 5 so a hand-typed
   placeholder constant is never reported as varying.

7. **Join into `catalogue.py`.** Add `observed: ObservedRange` to
   `CatalogueEntry`; call `build_observed_ranges` once in `build_catalogue`
   (import deferred into the body) and attach each entry's range by path. Add an
   optional `reference=None` parameter to `build_catalogue`, threaded through.
   Bump `SCHEMA_VERSION` to `"1.1"`. Extend `_CATALOGUE_NOTE` with one sentence
   naming the two populations and the 21-of-99 coverage limit.

8. **Serialisers.** In `catalogue_to_dict`, emit each entry's `observed` block
   through a `_quantise(v) = None if v is None else float(f"{v:.6g}")` helper
   (AC15), and add the top-level `observed_summary` counter (AC12). In
   `render_markdown`, add two columns after `scale sensitivity`: `observed range`
   (e.g. `corpus 7.67e-08–0.673278 · ref 2.33515e-08–18.5103`, with `—` for an
   uncovered population) and `observed verdict`.

9. **`main`** gains `--reference PATH` (AC22), defaulting to the bundled
   production artifact.

10. **`scripts/aide_status_report.py`**: `_FEATURE_CATALOGUE_SCHEMA_VERSION`
    `"1.0"` → `"1.1"`. No other change — the loader already skips unknown entry
    keys.

11. **Regenerate and commit** both `docs/aide/feature_catalogue.generated.json`
    and `.md` with `python -m segfacet.catalogue`. Both are already pinned
    `text eol=lf` in `.gitattributes`; do not add entries.

## Authorised paths

**May change:**

- `src/segfacet/observed_range.py` — new module: the two populations, the
  resolution rules, and the verdict.
- `src/segfacet/catalogue.py` — `CatalogueEntry.observed`, the
  `build_catalogue` join, `SCHEMA_VERSION`, the note, both serialisers, the
  `--reference` flag.
- `scripts/aide_status_report.py` — `_FEATURE_CATALOGUE_SCHEMA_VERSION` only.
- `docs/aide/feature_catalogue.generated.json` — regenerated, never hand-edited.
- `docs/aide/feature_catalogue.generated.md` — regenerated, never hand-edited.
- `tests/test_124_observed_range.py` — this item's test module.

**Asserts against:**

- `src/segfacet/reference/reference_verse_v1.json` — read as the entire
  reference population and pinned unchanged. AC2/AC3/AC10/AC11 read its
  `features` list and per-level `feature_stats`; item 123 owns its contents.
- `src/segfacet/reference/ingest.py` — `INGESTED_INTENSITY_FEATURES` read by the
  rule-(2) resolver (AC2). Not changed.
- `src/segfacet/feature_docs.py` — `PATH_ALIASES` read by the rule-(1) resolver
  (AC2). Not changed; no new alias, no `STATUS_OVERRIDES` entry.

Two files this item deliberately does **not** pin, though it depends on them:
`.gitattributes` (both generated documents are already pinned `text eol=lf`, and
item 103's `test_ac20` already asserts those two lines — a second assertion here
would only duplicate it) and `docs/aide/golden-decision-table.md` (its Section 2
already lists both generated documents; this item neither reads nor changes it).

**On the cross-spec conflicts `aide check --queue 017` reports for this item.**
Every one is of the form "item 119/120/121/122/123 may change P, which item 124
pins". All five are ✅ and already merged into `aide/queue-017`; their edits to
`feature_docs.py`, `reference/ingest.py` and `reference_verse_v1.json` have
landed, and this item's pins are measured against that post-123 state (see
Assumptions). The checker is order-blind and cannot see the merge, so these are
resolved history rather than open conflicts — do not re-litigate them.

## Testing Strategy

Test module: **`tests/test_124_observed_range.py`**. One focused test per AC,
plus the adversarial cases below. Build the full catalogue once per module in a
session-scoped fixture — `build_catalogue()` runs every rule over nine driver
records and is slow.

**Per-AC coverage.** AC1/AC3/AC4/AC9/AC10/AC11/AC12/AC18/AC19 read the freshly
built catalogue or the committed JSON. AC13/AC14 parse the rendered Markdown
header and rows. AC16/AC17 call `main()` into `tmp_path` and compare bytes.
AC20 loads `scripts/aide_status_report.py` by path (the item-103 module fixture
does this already) and asserts a non-empty result.

**Constructed-reference tests — the core of the item.** AC5, AC21 and AC22 all
need an injected reference, never the bundled one:

- **AC5 (the instrument fires).** Build a `ReferenceDistribution` in-memory
  whose `spline_offset_mm` stats carry the *pre-123* magnitudes
  (`min=5.928524174262729e-10`, `max=0.0003081687597848005`) and whose other
  features keep shipped-like magnitudes. Assert
  `stage3.per_label_offsets[].offset_mm` reads `degenerate` and that no other
  path does. Construct the values in the test rather than shelling out to
  `git show ae3e9f4:...` — the test must not depend on git history.
- **AC21 (degrade, never raise).** Point `--reference` at a nonexistent path, at
  a directory, at a file of malformed JSON, and at a well-formed JSON document
  with an unrecognised `schema_version`. Each must build a full catalogue with
  every `observed.reference.covered == false`.
- **AC22.** `main(["--json", ..., "--md", ..., "--reference", str(alt)])`
  produces a catalogue whose reference ranges come from `alt`.

**AC6/AC7 use real shipped paths as witnesses**, so the test fails if the
classification drifts rather than only if the helper is wrong:
`stage3.per_label_offsets[].dy_mm` (corpus `-2.84e-14 .. 3.55e-14`, no reference
coverage) must read `constant-synthetic`;
`reference_delta.{label}.features.physical_volume_mm3.z_score` (realised only by
the `reference_delta` placeholder driver) must read `placeholder`.

**Adversarial / edge cases.**

- **Verdict-rule ordering.** Two direct tests, because both orderings are
  load-bearing: a path that is reference-degenerate *and* corpus-informative must
  read `degenerate`, not `varies` (this is exactly pre-123 `offset_mm`, whose
  driver-set spread was non-zero); a placeholder-only path with a large hand-typed
  constant must read `placeholder`, not `varies`.
- **Floor boundary.** A population with magnitude exactly `1e-3` is **not**
  informative (`>`, not `>=`); `1.000001e-3` is. Assert both.
- **Sign handling.** A population spanning `-500 .. -1` has magnitude `500` and
  is informative — `intensity_min` in the shipped reference is entirely negative
  (`-1298.86 .. -1.73518`) and must not be mistaken for dead.
- **Booleans are not numeric.** `stage3.per_label_offsets[].is_terminal`
  (item 123) and `relationships.is_continuous` must read `non-numeric`, not be
  aggregated as `0`/`1`.
- **Empty containers.** The six paths that realise no value at all —
  `per_label`, `overlaps[]`, `per_label.{label}.components.small_fragments[]`,
  `stage3.monotonic_consistency.non_monotonic_pairs[]`,
  `stage3.spacing_consistency.outlier_pairs[]`,
  `reference_delta.{label}.out_of_range_features[]` — must be classified, never
  dropped and never crash the walk.
- **Scalar lists are collected element-wise.**
  `stage3.curvature.tangent_angles_deg[]` must yield `count > 1`, proving the
  walk descends into scalar lists rather than recording the path alone.
- **Determinism and immutability.** `build_observed_ranges()` twice returns equal
  results; it mutates neither the driver records nor the reference distribution
  (compare a deep copy taken before the call).
- **Quantisation idempotence.** `_quantise(_quantise(v)) == _quantise(v)` over
  the shipped range values.
- **Empty inputs.** `build_observed_ranges(driver_records=[])` returns an empty
  mapping without raising; `iter_leaf_values({})` returns an empty mapping.

**Existing tests to reconcile.** Swept `tests/` on 2026-08-30 for assertions
this item's changes would move:

- `scripts/aide_status_report.py:829` `_FEATURE_CATALOGUE_SCHEMA_VERSION = "1.0"`
  — **must be updated with the bump.** Left alone it silently empties the report
  section and fails
  `test_103_feature_catalogue.py::test_ac22_rendered_section_markup_shape`, which
  asserts `groups` is non-empty. This is the one genuinely breaking coupling.
- `test_103_feature_catalogue.py::test_adv_status_report_loader_unknown_schema_version_returns_empty_tuple`
  — uses the literal `"not-a-real-version-999"`, so it stays green across the
  bump. No change.
- `test_103_feature_catalogue.py::test_ac19_committed_docs_match_fresh_regeneration`,
  `test_106_stage19_validation.py` (lines 596–619),
  `test_119_curve_formulation.py` (line 851),
  `test_120_leave_one_out_offset.py` (lines 435, 898),
  `test_122_signed_curvature.py` (lines 62–63) — all compare the committed
  catalogue documents byte-exactly against a fresh regeneration. Green **only if
  step 11 regenerates and commits both**; a forgotten regeneration fails five
  modules at once, which is the intended alarm.
- `test_103_feature_catalogue.py::test_ac24_markdown_has_exact_columns_and_row_count`
  — despite its name, checks `column in header` (a subset) plus
  `len(table_rows) - 2 == len(entries)`. Two added columns leave both true. No
  change.
- `test_103_feature_catalogue.py::test_ac24_markdown_rows_are_in_catalogue_order`
  — splits each row on `|` and reads index 1 as the path. `path` stays the first
  column, so this holds. No change.
- `test_104_feature_catalogue_drift.py` — validates entries on `path` and
  `origin` only and tolerates unknown keys. No change.
- `test_111_golden_guard.py:53-54` and
  `test_105_golden_decision_table.py:423-424` — both already list the two
  generated catalogue documents in their byte-exact fixture families. No change.

## Validation

Beyond the suite, replay the claim in the item's title — that this column is the
instrument which would have caught Stage 28's defect. No special environment;
no `[validation]` profile applies.

1. Regenerate and read the summary:

       .venv/bin/python -m segfacet.catalogue

   Confirm `git status` shows the two generated documents either unchanged or
   changed only in ways the diff explains, and that the JSON's
   `observed_summary` reports `"degenerate": 0`.

2. Confirm the current state of the feature Stage 28 was opened for — its entry
   in the regenerated JSON must read `observed.verdict == "varies"` with
   `observed.reference.magnitude` near `18.5103`:

       .venv/bin/python -c "import json;d=json.load(open('docs/aide/feature_catalogue.generated.json'));print([e['observed'] for g in d['groups'] for e in g['entries'] if e['path']=='stage3.per_label_offsets[].offset_mm'])"

3. **Replay the defect.** Write the pre-123 reference artifact out of git history
   and regenerate against it, into a scratch directory so nothing committed
   moves:

       git show ae3e9f4:src/segfacet/reference/reference_verse_v1.json > /tmp/pre123_reference.json
       .venv/bin/python -m segfacet.catalogue --json /tmp/pre123_catalogue.json --md /tmp/pre123_catalogue.md --reference /tmp/pre123_reference.json

   `stage3.per_label_offsets[].offset_mm` must read
   `observed.verdict == "degenerate"` in `/tmp/pre123_catalogue.json`, and
   `observed_summary` must report a non-zero `degenerate` count. If it does not,
   the instrument does not do what this item claims and the item fails
   regardless of a green suite.

## Dependencies

- **Item 103** (✅) — the catalogue generator, `iter_driver_records`,
  `normalise_leaf_path`, and both committed artifacts this item extends.
- **Item 104** (✅) — the drift test whose no-tests-directory contract on the
  driver set constrains this item's corpus population.
- **Item 110** (✅) — the ambiguity discipline AC23 mirrors.
- **Item 123** (✅) — the rebuilt `reference_verse_v1.json` that is this item's
  entire reference population, and the recalibration this column audits.

**Downstream:** item 125 (Stage 28 validation) reads this column's
`observed_summary` as part of confirming both reference artifacts were rebuilt
from real GT rather than edited.

## Decisions & Trade-offs

To be updated during implementation.
