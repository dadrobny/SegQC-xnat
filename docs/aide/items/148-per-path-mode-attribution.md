# Item 148 — Per-path mode attribution, so the catalogue stops painting bookkeeping paths

> **Created:** 2026-09-04 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 30 — Failure-Mode Specification: the §6 catalogue as an authored source
> **Queue:** [`../queue/queue-020.md`](../queue/queue-020.md) · Item 148
> **Objectives:** G2 (detect catalogued failure modes), G7 (evaluable and
> regression-testable), G8 (extensible — the generated artifacts become
> conformance reports over one record)
> **Suggested branch:** `aide/148-per-detector-mode-attribution-so`

---

## Description

Stage 30 D4, second half. Item 136's §6 mode attribution is **rule-granular**:
in `segfacet.catalogue.build_catalogue`, every leaf path a declaring rule
consumes inherits that rule's *whole* mode tuple, so
`docs/aide/feature_catalogue.generated.md` paints pure bookkeeping paths with
failure modes they cannot evidence. Measured on the committed catalogue at this
branch's base (2026-09-04): `reference_delta.lower_pct` carries
`failure_modes == [1, 2, 9]`, `reference_delta.{label}.label` and
`reference_delta.{label}.level_name` carry `[1, 2]`, and a reader cannot tell
any of them from `reference_delta.{label}.features.physical_volume_mm3.robust_z`,
which genuinely carries the mode-1/mode-2 signal. The container path `per_label`
carries `[1, 2, 3, 4, 5, 6, 7, 9]` — eight modes on a dict a rule reads only to
iterate. The defect was recorded at `insights.md`, item 138, 2026-09-02, and
routed to this item; item 138's mode → feature direction inherits it and reports
the granularity beside the list (`traceability._GRANULARITY_QUALIFIER`) rather
than filtering, because narrowing needed a per-path mechanism claim no shipped
declaration carried.

This item supplies that claim, at the declaration seam item 147 rewrote. Each
rule's `RuleModeDeclaration` gains a **declared per-path classification** of
every leaf path the catalogue attributes to it, from a closed three-member
vocabulary:

- **`signal`** — the path carries the mode's evidence: its *value* is what a
  finding from this rule asserts about.
- **`bookkeeping`** — the rule reads it, but it cannot evidence a mode: label
  ids, level names, containers iterated, availability gates, band values and
  other message interpolation, context that only gates or exempts.
- **`not-read`** — the rule does **not** read this path at all; the catalogue
  attributes it by mechanism B's last-path-segment name match
  (`catalogue.py`, "Static AST scan of `heuristics/*.py`"). Seven
  `reference_delta.*` paths plus `per_label` reach
  `intensity_reference_delta` this way, and `per_label` reaches `intensity`
  and `reference_delta` this way (see **A2**).

The classification is **declared, never inferred** — no heuristic over path
names, no default. A consumed path with no classification, and a classified
path the rule does not consume, are both test failures naming the path and the
rule. `build_catalogue` then contributes a rule's corpus-derived (mechanism C)
and declared (item 136) modes to a path **only** where that `(rule, path)` pair
is `signal`. The path-keyed Stage-18 anchor term (`per_mode_metric`,
`feature_docs.MODE_ANCHOR_PATHS`) is untouched: it is already per-path, and gate
3 decision 1 keeps it a separate, separately-labelled column.

The catalogue **renders the classification explicitly** rather than silently
dropping the modes: `CatalogueEntry` gains a `mode_roles` column (per consuming
rule, its role for this path) carried into both artifacts, and `mode_evidence`
gains the tags `rule_bookkeeping` and `rule_not_read`, so a reader can tell "a
source spoke and said this path cannot evidence a mode" from `rule_unmapped`
("nobody has said") and from `()` ("no rule reads it") — the distinction item
137 built the evidence column to preserve.

**What this item is not.** It writes no rule logic: under
`src/segfacet/heuristics/` the only changes are the ten `mode_declaration`
**literals** and the minimal declaration type added to `rule.py`. No threshold,
condition, severity, `evaluate` body or registered rule changes, and
`run_rules`' output is invariant on records where each rule fires (**AC16**).
It does not narrow attribution *per detector* — `IntendedRule.detector` stays
where items 144/147 put it and item 149 renders it (see **Decisions**, D2). It
does not touch `segfacet.traceability`: `build_matrix` derives its per-rule path
sets from `CatalogueEntry.consuming_rules`, which this item does not change, so
both matrix artifacts stay byte-identical (**AC18**) — re-pointing the matrix is
item 149's. It adds no corpus case, no rule, no feature, and no committed
non-`.py` fixture under `tests/` (**A7**).

## Acceptance Criteria

- [ ] **AC1: the classification record exists.** `segfacet.heuristics.rule`
  defines a frozen dataclass `ConsumedPath` with exactly the fields
  `(path, role, reason)` and a module-level closed vocabulary
  `PATH_ROLES == ("signal", "bookkeeping", "not-read")`; both are re-exported
  from `segfacet.heuristics` and listed in `rule.__all__`.

- [ ] **AC2: the declaration carries it, additively.** `RuleModeDeclaration`'s
  field set is exactly `{"modes", "evidence", "mode_less_reason",
  "pending_reason", "consumed_paths"}`, and `consumed_paths` defaults to `()`,
  so every existing standalone `RuleModeDeclaration(...)` construction in the
  suite still constructs.

- [ ] **AC3: an ill-formed classification is rejected at construction.**
  `RuleModeDeclaration.__post_init__` raises `ValueError` naming the field and
  the offending path for each of: a non-tuple `consumed_paths` (a bare `str` or
  a `list`); an element that is not a `ConsumedPath`; an empty or non-`str`
  `path`; a `role` outside `PATH_ROLES`; a duplicated `path`; a
  non-ascending-by-`path` order; an empty `reason` on a `bookkeeping` or
  `not-read` element; and a `signal` element on a declaration whose `modes` is
  empty.

- [ ] **AC4: every declaring rule classifies exactly what it consumes.** For
  each of the ten registered rules, the set of `ConsumedPath.path` values equals
  the set of catalogue paths whose `consuming_rules` contain that `rule_id`,
  recomputed live from `build_catalogue(strict=True)` — no consumed path
  unclassified, no classified path unconsumed.

- [ ] **AC5: an unclassified consumed path is reported, naming both.**
  `segfacet.catalogue.path_classification_conflicts()` returns `()` on the
  shipped tree; with one rule's `consumed_paths` monkeypatched to drop an entry,
  it returns a message containing that rule's `rule_id` and that leaf path.

- [ ] **AC6: a classified path the rule does not consume is reported, naming
  both.** With one rule's `consumed_paths` monkeypatched to add a
  `ConsumedPath` for a leaf path the catalogue does not attribute to it,
  `path_classification_conflicts()` returns a message containing that
  `rule_id` and that path; a single call reports **both** directions when both
  are injected at once.

- [ ] **AC7: `not-read` cannot hide a path the rule demonstrably reads.**
  `path_classification_conflicts()` reports, naming the rule and the path, any
  `(rule, path)` pair classified `not-read` whose `rule_evidence` in the
  catalogue carries `"observed"` — mechanism A is a dynamic access trace, so an
  observed read refutes a `not-read` claim. The check is clean on the shipped
  tree, and the message appears when a shipped `bookkeeping`/`signal` pair with
  `"observed"` evidence is monkeypatched to `not-read`.

- [ ] **AC8: only `signal` paths inherit a rule's modes.** For every catalogue
  entry, `failure_modes` equals `anchor_modes(path) | ⋃{corpus_modes(r) ∪
  declared_modes(r) : r ∈ consuming_rules, role(r, path) == "signal"}`,
  recomputed independently in the test from `feature_docs.MODE_ANCHOR_PATHS`,
  `catalogue.scan_synth_rule_mode_map()` and `rule.declaration_for(r)`.

- [ ] **AC9: the classification is rendered, not merely applied.**
  `CatalogueEntry` carries `mode_roles: Tuple[Tuple[str, str], ...]` —
  `(rule_id, role)` pairs ascending by `rule_id` — the JSON artifact carries it
  as a `"mode_roles"` key on every entry, and the Markdown table carries a
  `§6 mode role(s)` column whose cell renders each consuming rule's role for
  that row.

- [ ] **AC10: the evidence column stays complete.** `mode_evidence` gains
  `"rule_bookkeeping"` and `"rule_not_read"`, each present for an entry iff at
  least one of its consuming rules carries that role for that path, and every
  entry's `mode_evidence` is a subsequence of the canonical order
  `("per_mode_metric", "rule_mode_map", "rule_declaration", "rule_mode_less",
  "rule_bookkeeping", "rule_not_read")` or exactly `("rule_unmapped",)`.

- [ ] **AC11: the three named bookkeeping paths are no longer painted, and the
  signal path still is.** In the regenerated catalogue,
  `reference_delta.lower_pct`, `reference_delta.{label}.label` and
  `reference_delta.{label}.level_name` each carry `failure_modes == ()`, while
  `reference_delta.{label}.features.physical_volume_mm3.robust_z` carries
  `failure_modes == (1, 2)`.

- [ ] **AC12: every mode keeps a signal path.** In the regenerated catalogue,
  mode 9 is attributed to exactly
  `image_features.per_label.{label}.first_order.median` and
  `image_features.per_label.{label}.first_order.std`, and each of modes 1–8 is
  attributed to at least one path; the assertion is a recomputation over
  `cat.entries`, not a hand-listed expectation.

- [ ] **AC13: the classification moves the attribution columns and nothing
  else.** A catalogue built from the shipped declarations and a catalogue built
  with every declaration's `consumed_paths` replaced by an all-`signal`
  classification of the same path set (the item-136 rule-granular behaviour)
  have equal group structure, equal entry order, equal `note` and
  `observed_summary`, and per entry every field equal **except**
  `failure_modes`, `mode_evidence` and `mode_roles` — for which at least one
  entry differs.

- [ ] **AC14: both artifacts stay byte-reproducible and match their committed
  copies.** `python -m segfacet.catalogue` writes
  `feature_catalogue.generated.{json,md}` byte-identically on two runs in one
  session, and the fresh pair matches the committed pair through
  `segfacet.synth.golden.assert_matches_committed_artifact`.

- [ ] **AC15: the schema version moves with the shape, and its one consumer
  follows.** `segfacet.catalogue.SCHEMA_VERSION == "1.2"`, the regenerated JSON
  carries it, and `scripts/aide_status_report.py`'s `load_feature_catalog`
  returns a non-empty tuple of `FeatureGroupSpec` for the regenerated committed
  artifact.

- [ ] **AC16: the seam stays metadata — proved where the rules fire.** For each
  of the ten registered rules there is a driven record on which `run_rules`
  emits at least one finding carrying that `rule_id` (asserted non-empty
  **before** any comparison), and on every one of those records `run_rules`'
  output is equal before and after **every** registered rule's
  `mode_declaration` is replaced with a different declaration.

- [ ] **AC17: no rule behaviour changed.** Each of the ten rule modules'
  module-level threshold/default constants holds its pre-item value, and no
  rule's `evaluate` body references `mode_declaration`, `consumed_paths` or
  `ConsumedPath` (asserted by AST over each `heuristics/*.py` rule module).

- [ ] **AC18: the traceability matrix is untouched.**
  `docs/aide/traceability_matrix.generated.{json,md}` regenerate
  byte-identically and match their committed copies, and
  `traceability.build_matrix()`'s per-rule path sets are still derived from
  `CatalogueEntry.consuming_rules` (recomputed in the test, not asserted from
  the source text).

- [ ] **AC19: the realised path universe is unchanged and item 104 still
  passes.** `build_catalogue(strict=True)` yields 138 entries whose path set
  equals the committed artifact's path set, and
  `tests/test_104_feature_catalogue_drift.py` reports no drift in any of its
  four directions.

- [ ] **AC20: the two existing conformance checkers stay clean.**
  `catalogue.rule_declaration_conflicts()` and
  `failure_modes.specification_conflicts()` both return `()` on the shipped
  tree after this item's change.

- [ ] **AC21: the loop's own lint is unmoved.**
  `python .aide/scripts/aide.py check` exits 0 with exactly 7 warnings, and no
  warning names any path this item writes.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **A1 — the chosen shape is (b), per-path classification, not (a) per-detector.**
  The queue allows either. Per-detector attribution would need the catalogue to
  join a rule's declared detector name against
  `failure_modes.SPECIFICATION[m].intended_rules[*].detector`, whose values are
  authored **prose** (`"Vertebra misaligned from spinal curve:"`,
  `"Rogue island(s):"`) — a mechanical join keyed on a free-form string, which
  is the exact defect class `insights.md` (item 136, 2026-09-02) recorded for
  the retired `"corpus"` evidence tag, where a near-miss silently disabled a
  check. Making detectors safe to join on means giving each rule first-class
  detector ids and tagging findings with them — an `evaluate`-body change the
  queue forbids here. Full reasoning, and what per-detector would additionally
  buy, is in **Decisions**, D2.

- **A2 — the vocabulary has three members, not the two the queue names.**
  `signal` / `bookkeeping` alone cannot be declared honestly on this tree.
  `intensity_reference_delta` reads `record["intensity_reference_delta"]` and
  never `record["reference_delta"]`, yet the catalogue attributes seven
  `reference_delta.*` leaf paths to it because mechanism B matches string
  constants by **last path segment**; `intensity` and `reference_delta` reach
  the top-level `per_label` entry the same way (they read
  `image_features.per_label` and `reference_delta.per_label`). Calling those
  pairs `bookkeeping` would ship a false claim — "the rule reads this path" —
  into a declaration, at the seam this stage exists to make truthful. `not-read`
  states what is true, and **AC7** makes it unusable as an escape hatch: a pair
  with mechanism-A `"observed"` evidence may not be declared `not-read`.

- **A3 — the catalogue renders the classification rather than silently
  excluding.** The queue allows either. Excluding only would leave
  `reference_delta.{label}.label` with `failure_modes == []` and
  `mode_evidence == []`, indistinguishable from a path no rule reads — losing
  precisely the "a source spoke and said no" versus "nobody has said"
  distinction item 137 added `rule_mode_less` to preserve. See **Decisions**, D3.

- **A4 — the schema version bumps to `"1.2"` and its one consumer is updated in
  the same item.** Precedent: commit `aa8cbd7` (item 124) bumped
  `SCHEMA_VERSION` `"1.0"` → `"1.1"` when it added the per-entry `observed`
  field, and updated `scripts/aide_status_report.py`'s
  `_FEATURE_CATALOGUE_SCHEMA_VERSION` in the same change. That loader gates on
  **exact equality** and returns `()` for an unrecognised version, so leaving it
  at `"1.1"` would silently empty the HTML status report's Feature Catalogue
  section, and `tests/test_103_feature_catalogue.py::test_ac22_rendered_section_markup_shape`
  would fail on the committed artifact.

- **A5 — the expected movement was measured, not estimated.** Applying the
  classification in **Implementation Steps** step 2 to the committed catalogue
  at this branch's base (2026-09-04) moves **25 of 138** entries and leaves 113
  untouched; the per-mode path counts move 1: 19→8, 2: 21→12, 3: 7→5, 4: 10→6,
  5: 4→2, 6: 9→6, 7: 6→2, 8: 6→1, 9: 12→2, and the `mode_evidence` distribution
  moves as tabulated in **Implementation Steps** step 6. These are the figures
  the reconciled tests in **Testing Strategy** pin. If the builder's
  verification of a classification against a rule's `evaluate` body disagrees
  with the table, **the rule body wins**, the table is corrected, the figures
  are re-measured, and the divergence is recorded in **Decisions**.

- **A6 — this item closes no Stage 30 acceptance criterion.** None of the six
  criteria in `progress.md`'s Stage 30 **Acceptance** block is about the feature
  catalogue's attribution granularity; criterion 4's "two separately labelled
  columns" is about `failure_modes.generated.*` and the traceability matrix
  (items 144/149). No AC above carries a *(closes Stage N criterion M)*
  annotation, and none is intended.

- **A7 — no new committed non-`.py` file under `tests/`.**
  `tests/test_105_golden_decision_table.py::test_ac3_current_tree_has_30_non_py_fixtures`
  pins that census at exactly 20 and
  `test_ac3_section1_fixture_set_equals_filesystem_walk_both_directions`
  requires a matching row in `docs/aide/golden_decision_table.md`. AC13's
  "nothing else moved" claim is therefore expressed as a live invariant over two
  builds (shipped classification vs. all-`signal`), not as a committed snapshot
  of the pre-change artifact — which is also what
  `.aide/conventions.md` §1 → `items.md` requires, since a snapshot of "the
  artifact before this commit" is a bound on the diff, not an invariant over the
  result, and could not be re-checked once the item has merged.

- **A8 — the `signal` / `bookkeeping` split is an authored claim, and this item
  does not mechanically verify it per path.** What *is* mechanically enforced:
  completeness (AC4/AC5), soundness (AC6), the `not-read` guard (AC7), the
  `signal`-requires-`modes` guard (AC3), and column isolation (AC13). Proving
  that each `signal` path can actually move its rule's findings needs a
  per-path perturbation harness with a threshold-crossing mutation per path;
  that is a separate deliverable and is captured as one `insights.md` line
  (**Implementation Steps** step 9), not smuggled in here.

- **A9 (engine 1.37.0) — `aide check` reports exactly 7 warnings on this
  branch**: one "32 item spec(s) have no mandatory '## Assumptions' block", two
  awaiting human gates (1 and 2), and four retracted Stage-20 acceptance
  criteria. This spec carries an `## Assumptions` block, so the 32 does not
  move; this item commits no new byte-reproducible text fixture, so the
  `.gitattributes` lint gains no subject. AC21 pins the count.

## Implementation Steps

1. **`src/segfacet/heuristics/rule.py` — the declaration type.** Add
   `PATH_ROLES = ("signal", "bookkeeping", "not-read")` and the frozen
   `ConsumedPath(path: str, role: str, reason: str = "")`. Add
   `consumed_paths: Tuple[ConsumedPath, ...] = ()` to `RuleModeDeclaration` and
   extend `__post_init__` with AC3's checks, each message naming the field and
   the offending path — following the two tuple checks item 147 put at the top
   of that method. Export both new names from `rule.__all__` and from
   `segfacet/heuristics/__init__.py`. Document in the class docstring that
   `consumed_paths` is read-only metadata that no rule may consult inside
   `evaluate`.

2. **The ten declaration literals.** Add `consumed_paths=(...)` to each rule
   module's `mode_declaration`, ascending by path, `reason` non-empty for every
   `bookkeeping` and `not-read` entry. **Verify each classification against that
   rule's `evaluate` body before writing it** (A5). The authored table, measured
   complete against the committed catalogue's `consuming_rules` on 2026-09-04:

   - **`border.py`** — `signal`: the six
     `per_label.{label}.geometry.touches_*` faces. `bookkeeping`:
     `per_label` (container iterated); `per_label.{label}.level_name` (compared
     against `derive_fov_coverage`'s end levels to exempt an expected terminal
     face, and interpolated into the message — a gate, never mode-6 evidence);
     `relationships.present_levels[]` (same FOV-span derivation).
   - **`bounds.py`** — `signal`: `per_label.{label}.geometry.extent_x_mm`,
     `extent_y_mm`, `extent_z_mm`, `physical_volume_mm3`. `bookkeeping`:
     `per_label`; `per_label.{label}.level_name` (selects the level's expected
     band; the deviation is carried by the geometry values).
   - **`coverage.py`** — `signal`: `relationships.missing_levels[]`,
     `relationships.present_levels[]` (check 2 fires on an expected level absent
     from this list). `bookkeeping`: `relationships` (container), `per_label`.
   - **`fragmentation.py`** — `signal`: the five
     `per_label.{label}.components.*` paths. `bookkeeping`: `per_label`,
     `per_label.{label}.level_name`.
   - **`intensity.py`** — `signal`:
     `image_features.per_label.{label}.first_order.median` and `.std`.
     `bookkeeping`: `image_features.available` (gate),
     `image_features.per_label.{label}.label` (identity). `not-read`:
     `per_label` — the rule reads `image_features.per_label`.
   - **`intensity_reference_delta.py`** — `not-read` for all eight attributed
     paths (`reference_delta.lower_pct`, `.upper_pct`,
     `reference_delta.{label}.distribution_distance`,
     `…features.physical_volume_mm3.percentile_rank`, `.robust_z`, `.value`,
     `reference_delta.{label}.out_of_range_features[]`, `per_label`); the rule
     reads `record["intensity_reference_delta"]`, which no driver realises, so
     it has no catalogued leaf path of its own (**A2**).
   - **`mislabel.py`** — `signal`: `stage3.per_label_offsets[].offset_mm`,
     `.dx_mm`, `.dy_mm`, `.dz_mm`,
     `stage3.monotonic_consistency.non_monotonic_pairs[]`. `bookkeeping`:
     `per_label`; `stage3.per_label_offsets[].is_terminal` (detector A's
     terminal exemption); `.label` and `.level_name` (identity).
   - **`overlap.py`** — `signal`: `overlaps[].overlap_voxels`. `bookkeeping`:
     `overlaps[]` (container), `overlaps[].label_a`, `.label_b`, `.name_a`,
     `.name_b`.
   - **`reference_delta.py`** — `signal`:
     `reference_delta.{label}.distribution_distance`,
     `reference_delta.{label}.out_of_range_features[]`,
     `reference_delta.{label}.features.physical_volume_mm3.robust_z`.
     `bookkeeping`: `reference_delta.lower_pct`, `.upper_pct` (band values,
     interpolated into the message only); `reference_delta.{label}.available`
     (gate); `.label`, `.level_name` (identity);
     `…features.physical_volume_mm3.value` and `.percentile_rank` (interpolated
     into the out-of-range message; the firing decision is
     `out_of_range_features[]`'s membership). `not-read`: `per_label` — the rule
     reads `reference_delta.per_label`.
   - **`sequence.py`** — `signal`:
     `relationships.out_of_order_labels[]`. `bookkeeping`: `relationships`
     (container), `per_label`, `per_label.{label}.label` and
     `per_label.{label}.level_name` (resolving level names to label ids for the
     finding's `labels` set).

3. **`src/segfacet/catalogue.py` — apply.** Build
   `roles_by_rule: Dict[str, Dict[str, str]]` from `iter_rule_declarations()`.
   In `build_catalogue`'s per-path loop, gate the `rule_mode_map` and
   `declared_modes_by_rule` contributions on
   `roles_by_rule.get(rule_id, {}).get(path) == "signal"`, leaving
   `anchor_modes` untouched. A rule with an empty `consumed_paths` contributes
   **nothing** — never a fall-back to the item-136 behaviour, which would be the
   silent default the queue forbids; `path_classification_conflicts()` reports
   it instead.

4. **`src/segfacet/catalogue.py` — render.** Add `mode_roles` to
   `CatalogueEntry`, populated as ascending `(rule_id, role)` pairs over the
   entry's `consuming_rules`; emit it in `catalogue_to_dict` and add the
   `§6 mode role(s)` column to `render_markdown`. Append `"rule_bookkeeping"`
   and `"rule_not_read"` to the canonical `mode_evidence` order and set them per
   AC10. Bump `SCHEMA_VERSION` to `"1.2"` and update the module docstring's
   "Four derivation mechanisms" / `failure_modes` paragraphs to describe the
   classification.

5. **`src/segfacet/catalogue.py` — check.** Add the public
   `path_classification_conflicts() -> Tuple[str, ...]`, mirroring
   `rule_declaration_conflicts()`'s shape (sorted messages, pure, never raises):
   a registered rule with a non-empty `modes` and an empty `consumed_paths`; a
   consumed `(rule, path)` pair with no classification; a classified path the
   rule does not consume; a `not-read` pair carrying mechanism-A `"observed"`
   evidence. Keep it a **separate** function so `rule_declaration_conflicts()`'s
   existing clean-on-this-tree assertions keep their meaning (see **Decisions**,
   D4).

6. **`scripts/aide_status_report.py`** — `_FEATURE_CATALOGUE_SCHEMA_VERSION`
   `"1.1"` → `"1.2"`. Nothing else in that script.

7. **Regenerate** `docs/aide/feature_catalogue.generated.{json,md}` with
   `.venv/bin/python -m segfacet.catalogue` (never by hand). Expected movement
   (**A5**), against the committed base: 25 of 138 entries change
   `failure_modes` and/or `mode_evidence`; every entry gains a `mode_roles`
   key/cell. The `mode_evidence` distribution moves from
   `{(): 86, ("rule_mode_map","rule_declaration"): 26, ("rule_declaration",): 18,
   ("per_mode_metric","rule_mode_map","rule_declaration"): 6,
   ("per_mode_metric",): 2}` to
   `{(): 86, ("rule_bookkeeping",): 16, ("rule_mode_map","rule_declaration"): 14,
   ("rule_declaration",): 6, ("per_mode_metric","rule_mode_map","rule_declaration"): 5,
   ("rule_bookkeeping","rule_not_read"): 5, ("rule_declaration","rule_not_read"): 3,
   ("per_mode_metric",): 2,
   ("per_mode_metric","rule_mode_map","rule_declaration","rule_bookkeeping"): 1}`.
   The 86-entry `()` bucket and the 2-entry `("per_mode_metric",)` bucket do not
   move, and no entry becomes `("rule_unmapped",)`.

8. **Regenerate nothing else.** Confirm
   `docs/aide/traceability_matrix.generated.{json,md}` and
   `docs/aide/failure_modes.generated.{json,md}` are byte-unchanged (AC18); if
   either moves, that is a finding — stop and record it, do not commit the
   regenerated artifact.

9. **`docs/aide/insights.md`** — append exactly one line capturing the
   deliberately-deferred finer form (A8, and **Decisions** D2). The spec-author
   appended it while authoring this item, so the builder only verifies it is
   present and unaltered:

       - [ ] gap — a `signal` path classification (item 148) is an authored claim no shipped check can refute; refuting one needs a per-path perturbation harness (a threshold-crossing mutation per signal path, asserting the rule's finding list moves), and above that per-DETECTOR attribution: mislabel's offset detector serves §6 mode 1 and its monotonicity detector mode 4, fragmentation's two branches modes 2 and 3, so those signal paths stay attributed one mode too wide. Both need rule-side first-class detector ids — IntendedRule.detector is authored prose, and joining a mechanical check on it is the retired "corpus"-tag defect *(item 148, 2026-09-04, engine 1.37.0)*

## Authorised paths

**May change:**

- `src/segfacet/heuristics/rule.py` — `PATH_ROLES`, `ConsumedPath`,
  `RuleModeDeclaration.consumed_paths` and its validation, `__all__`, and the
  class docstring. No registry behaviour changes.
- `src/segfacet/heuristics/__init__.py` — the two new re-exports only.
- `src/segfacet/heuristics/border.py` — the `mode_declaration` literal only.
- `src/segfacet/heuristics/bounds.py` — the same.
- `src/segfacet/heuristics/coverage.py` — the same.
- `src/segfacet/heuristics/fragmentation.py` — the same.
- `src/segfacet/heuristics/intensity.py` — the same.
- `src/segfacet/heuristics/intensity_reference_delta.py` — the same.
- `src/segfacet/heuristics/mislabel.py` — the same.
- `src/segfacet/heuristics/overlap.py` — the same.
- `src/segfacet/heuristics/reference_delta.py` — the same.
- `src/segfacet/heuristics/sequence.py` — the same.
- `src/segfacet/catalogue.py` — the classification gate in `build_catalogue`,
  `CatalogueEntry.mode_roles`, the two new `mode_evidence` tags,
  `catalogue_to_dict`, `render_markdown`, `SCHEMA_VERSION`, the new
  `path_classification_conflicts`, `__all__` and the docstring. No other
  function's behaviour changes.
- `scripts/aide_status_report.py` — `_FEATURE_CATALOGUE_SCHEMA_VERSION` only
  (**A4**).
- `docs/aide/feature_catalogue.generated.json` — regenerated (**A5**).
- `docs/aide/feature_catalogue.generated.md` — regenerated (**A5**).
- `docs/aide/insights.md` — one appended line (Implementation Steps step 9);
  nothing reworded, nothing reordered.
- `tests/test_148_per_path_mode_attribution.py` — this item's tests.
- `tests/test_103_feature_catalogue.py` — reconciliation only, per **Testing
  Strategy**.
- `tests/test_136_rule_mode_declarations.py` — reconciliation only.
- `tests/test_137_mode_less_rule_disposition.py` — reconciliation only.
- `tests/test_146_ninth_mode_and_first_proposed.py` — reconciliation only.

**Asserts against:**

- `src/segfacet/feature_docs.py` — AC8/AC12 read `MODE_ANCHOR_PATHS` live; the
  anchor term is deliberately not filtered and this item writes nothing here.
- `src/segfacet/traceability.py` — AC18 recomputes `build_matrix`'s per-rule
  path sets; unchanged by this item.
- `docs/aide/traceability_matrix.generated.json` — AC18 regenerates and compares
  it; byte-unchanged.
- `docs/aide/traceability_matrix.generated.md` — the same.
- `docs/aide/failure_modes.generated.json` — AC18's second pair; byte-unchanged.
- `docs/aide/failure_modes.generated.md` — the same.
- `src/segfacet/failure_modes.py` — AC20 calls `specification_conflicts()`; this
  item adds no mode, edge or corpus case.
- `src/segfacet/heuristics/runner.py` — AC16 drives `run_rules`.
- `src/segfacet/pipeline.py` — AC16's records come through
  `run_qc_with_intensity` / `run_qc_with_reference`.
- `src/segfacet/synth/regression.py` — AC16 measures both corpora through
  `pipeline_findings` / `intensity_pipeline_findings`.
- `src/segfacet/synth/golden.py` — AC14's committed-artifact comparison helper.
- `tests/corpus/manifest.json` — AC16 reads it; no case is added, removed or
  re-valued.
- `tests/corpus/intensity/manifest.json` — the same.
- `tests/committed_artifact_guard.py` — both catalogue artifacts are already
  allowlisted under the `emission-clamped` ground; read as the guard AC14 runs
  under, and unchanged.
- `tests/test_104_feature_catalogue_drift.py` — AC19 requires it to pass
  unmodified; this item must not edit it.
- `tests/test_105_golden_decision_table.py` — **A7**'s census of 20 non-`.py`
  files under `tests/` must still hold; this item commits no fixture.
- `.gitattributes` — the existing `text eol=lf` pins for both catalogue
  artifacts; this item adds no new path and therefore no line.
- `.aide/VERSION` — **A9**'s engine marker.

## Testing Strategy

New module: **`tests/test_148_per_path_mode_attribution.py`**, one focused test
per AC plus the adversarial cases below. Ungated (stdlib + `pytest` +
`segfacet.*` only), no absolute path literal, no `read_bytes()` outside AC14's
byte comparisons, and every "what the tree contains" claim recomputed from the
primary source rather than hand-listed.

**Per AC.** AC1–AC3 over `rule.py` directly (`dataclasses.fields`, frozen-ness,
and one `pytest.raises(ValueError, match=…)` per malformed construction, each
match naming the field and the path). AC4–AC7 over
`path_classification_conflicts()`, with `monkeypatch.setattr` on
`_RULES[rule_id].mode_declaration` to inject each defect; assert the message
contains **both** the `rule_id` and the path, and that the shipped tree is
clean. AC8 recomputes the whole `failure_modes` column independently
(anchors ∪ signal-gated corpus modes ∪ signal-gated declared modes) and
compares entry by entry — the AC12 pattern of item 136's
`test_ac12_failure_modes_recomputed_independently_matches`, with the role gate
added. AC9/AC10 over `catalogue_to_dict` / `render_markdown` output and the
canonical-order subsequence. AC11/AC12 over the freshly built catalogue.
AC13 builds twice — once shipped, once with every declaration's
`consumed_paths` rewritten to all-`signal` over the same path set — and
compares the two dicts field by field, asserting equality everywhere except the
three attribution fields and inequality in at least one of them. AC14 through
`assert_matches_committed_artifact` plus a two-run byte comparison in `tmp_path`.
AC15 imports the status-report script the way
`tests/test_103_feature_catalogue.py` already does and asserts a non-empty group
tuple. AC16 as below. AC17 by AST over each `heuristics/*.py` rule module plus
direct constant reads. AC18/AC19/AC20/AC21 as stated, AC21 via
`run_process`-style invocation of `python .aide/scripts/aide.py check`.

**AC16 — the invariance test must drive rules that fire.** The item-146 review
finding (`tests/test_146_ninth_mode_and_first_proposed.py::test_ac13_replacing_declaration_leaves_run_rules_output_unchanged`)
is that a clean-spine record produces no findings, so the comparison compares
two empty lists and proves nothing. Here: build the driven records from the two
committed corpora through `segfacet.synth.regression` —
`pipeline_findings(case)` for the geometric cases and
`intensity_pipeline_findings(case, reference=<bundled reference>)` for the
intensity cases, whose `reference` argument makes `run_qc_with_intensity` attach
the `reference_delta` and `intensity_reference_delta` blocks and so drives
`bounds`, `reference_delta` and `intensity_reference_delta`, none of which any
committed corpus case designates. Assert, per rule, that the baseline finding
list is non-empty **and** contains that `rule_id`, before replacing every
declaration and comparing. If a rule cannot be driven from the committed
corpora, a hand-built record in the test is acceptable **only** with the same
non-empty assertion.

**Adversarial / edge.** A `ConsumedPath` with a `role` differing from a
`PATH_ROLES` member by one character is rejected (never matched by prefix or
substring). A declaration built with `consumed_paths` as a `list` or a bare
`str` is rejected before the element loop. A rule whose `consumed_paths` names
the same path twice is rejected. Determinism: two `build_catalogue()` calls
return equal `mode_roles`, `mode_evidence` and `failure_modes` for every entry.
Immutability: a live declaration's `consumed_paths` cannot be reassigned, and
`build_catalogue` does not mutate any declaration. An entry with no consuming
rules carries `mode_roles == ()` and none of the four rule-sourced evidence tags.
An adversarial stub rule registered with `modes` set and `consumed_paths` empty
is reported by `path_classification_conflicts()` and contributes no mode to any
path.

**Existing tests to reconcile.** Every one below fails on the pre-item
assertion and is reconciled in place, with the item number and date in the
docstring, in the house style items 137/146 used:

- `tests/test_103_feature_catalogue.py`
  - `test_ac13_rule_mode_map_effect_on_failure_modes` — its "an entry consumed
    only by rule R carries R's corpus modes" premise now holds only for entries
    R classifies `signal` (e.g. `per_label.{label}.label`, consumed only by
    `sequence`, is `bookkeeping` and carries `()`); restrict the match set by
    role.
  - `test_ac15_declared_mode_less_rule_only_entry_is_honestly_mode_less` — the
    intensity-only, non-anchor entries `image_features.available` and
    `image_features.per_label.{label}.label` are `bookkeeping` and now carry
    `failure_modes == ()` with `mode_evidence == ("rule_bookkeeping",)`;
    restrict to `signal` entries for the `(9,)` claim and add the bookkeeping
    pair as the honest new form.
  - `test_ac24_markdown_has_exact_columns_and_row_count` — add
    `§6 mode role(s)` to `_MD_COLUMNS`.
  - `test_ac22_rendered_section_markup_shape` — passes only once
    `scripts/aide_status_report.py` carries `"1.2"` (AC15); verify, do not
    weaken.
- `tests/test_136_rule_mode_declarations.py`
  - `test_ac1_field_names` — the field set gains `consumed_paths`.
  - `test_ac11_rule_declaration_tag_present_iff_declared_modes_contributed` —
    "contributed" now means "through a `signal`-classified path".
  - `test_ac11_mode_evidence_is_canonical_order_subsequence` — the canonical
    tuple grows to six tags.
  - `test_ac12_failure_modes_recomputed_independently_matches` — add the role
    gate to the corpus and declaration terms.
  - `test_ac13_catalogue_artifacts_regenerate_byte_identically` —
    `payload["schema_version"] == "1.2"`.
  - `test_adv_expected_artifact_movement_counts_from_spec` — `stayed_empty == 86`
    and `stayed_rule_unmapped == 0` both still hold (**A5**); re-verify rather
    than re-measure, and note in the docstring that this item did not move them.
- `tests/test_137_mode_less_rule_disposition.py`
  - the `reference_delta.*` shared-entry test asserting
    `entry.failure_modes == (1, 2, 9)` — its own docstring already says "Item
    148 narrows this rule-granular bookkeeping"; the shared entries now split
    into `(1, 2)` for the three `signal` paths and `()` for the four
    `bookkeeping` ones, with `"rule_not_read"` present on all seven.
  - `test_ac13_bounds_or_reference_delta_consumers_carry_mode_two` — restrict to
    entries those rules classify `signal`.
  - `test_ac14_intensity_only_non_anchor_entries_are_honestly_mode_less` — same
    split as test_103's AC15 above.
  - `test_adv_per_label_container_keeps_corpus_modes_and_gains_declaration_last`
    — the `per_label` container is `bookkeeping` for the six rules that read it
    and `not-read` for the three that do not, so it now carries
    `failure_modes == ()` and
    `mode_evidence == ("rule_bookkeeping", "rule_not_read")`; restate the
    honesty claim in that form.
  - the per-mode count test — `mode2_count` 21→12, `mode1_count` 19→8,
    `mode9_count` 12→2, and the `mode_evidence` distribution replaced by the
    nine-bucket table in **Implementation Steps** step 7. Re-measure from the
    regenerated catalogue; do not transcribe blind.
- `tests/test_146_ninth_mode_and_first_proposed.py`
  - `test_ac34_mode9_catalogue_attribution_equals_declaring_rules_reach` — the
    claim becomes "reached by a mode-9 declarer **that classifies this path
    `signal`**", which is the narrowing this item exists to make; the mode-9
    path set drops from 12 to the two `first_order` paths.
  - `test_ac33_feature_catalogue_matches_committed_via_tolerance_helper` —
    passes against the regenerated artifact; verify, do not weaken.

## Validation

Beyond the suite, observe the review surface directly:

1. `.venv/bin/python -m segfacet.catalogue` — regenerates both artifacts.
2. `git diff --stat docs/aide/` — must name **only**
   `feature_catalogue.generated.json` and `.md`; a moved
   `traceability_matrix.generated.*` or `failure_modes.generated.*` is a finding
   (AC18), not a file to commit.
3. In `docs/aide/feature_catalogue.generated.md`, read the four rows the queue
   names: `reference_delta.lower_pct`, `reference_delta.{label}.label` and
   `reference_delta.{label}.level_name` must show an empty `§6 mode(s)` cell and
   an explicit `reference_delta: bookkeeping` (plus
   `intensity_reference_delta: not-read` on the first) in `§6 mode role(s)`,
   while `reference_delta.{label}.features.physical_volume_mm3.robust_z` must
   still show `1, 2` and `reference_delta: signal`.
4. `python .aide/scripts/aide.py check` — 7 warnings, exit 0 (AC21).

No `[validation]` environment profile is needed: everything above runs on the
default CPU-only install with no optional dependency.

## Dependencies

- **Item 147** (✅ merged) — the declaration seam this item edits: the retired
  `"corpus"` evidence tag, `RuleModeDeclaration.__post_init__`'s tuple checks
  (the pattern AC3's checks follow), and `ModeSpec.short_name` / `mechanism`.
- **Item 146** (✅ merged) — mode 9 and the two intensity rules' declarations,
  whose over-broad reach across `reference_delta.*` is half of what this item
  narrows, plus `synth.regression.intensity_pipeline_findings`, which AC16 uses
  to drive the intensity rules.
- **Item 136** (✅ merged) — `RuleModeDeclaration`, `iter_rule_declarations` and
  the `rule_declaration` evidence tag this item gates.
- **Item 124** (✅ merged) — the `SCHEMA_VERSION` bump precedent A4 follows.

**Downstream:** item 149 re-points `traceability.build_matrix` at the
specification and can then replace `_GRANULARITY_QUALIFIER`'s rule-granular
caveat with the per-path roles this item declares; item 150's sign-off reads the
rendering item 149 completes; item 151 closes the stage and re-measures the
per-status, per-rung counts.

## Decisions & Trade-offs

Recorded at authoring time; the builder appends what it learns.

- **D1 — shape (b), per-path classification, over shape (a), per-detector.**
  Both were on the table (queue-020, item 148). (a) needs the catalogue to map a
  declared detector to modes through
  `failure_modes.SPECIFICATION[m].intended_rules[*].detector`, whose values are
  authored prose finding-tags (`"Rogue island(s):"`). A mechanical join keyed on
  a free-form authored string is the exact failure `insights.md` (item 136,
  2026-09-02) recorded for the reserved `"corpus"` tag — a near-miss silently
  disables the check — and item 147 retired that tag rather than harden it.
  Making detectors joinable means first-class detector ids on the rule side,
  with findings carrying them, which is an `evaluate`-body change the queue
  forbids in this item. (b) is also self-contained: the classification lives
  entirely in `heuristics/`, needs no import from `failure_modes` into the rule
  layer, and answers exactly the question the catalogue's unit poses — "can this
  path evidence a mode?". Finally (a) ⊃ (b): a bookkeeping path belongs to no
  detector, so (a) would need a `bookkeeping` sentinel anyway.

- **D2 — what (a) would additionally have bought, and why it is deferred rather
  than dropped.** Per-detector attribution is strictly finer where a rule has
  two detectors serving different modes: `mislabel`'s offset detector serves §6
  mode 1 and its monotonicity detector mode 4, so under (a)
  `stage3.per_label_offsets[].offset_mm` would carry `(1,)` and
  `stage3.monotonic_consistency.non_monotonic_pairs[]` `(4,)` instead of `(1, 4)`
  each; likewise `fragmentation`'s mode-2 and mode-3 branches. A per-path
  `modes` narrowing field would have delivered the same result as a pure
  declaration literal, but it doubles the authored claim surface for a
  deliverable the queue did not ask for, and a *wrong* narrowing ships a false
  claim, which is worse than a true-but-coarse one. Captured as one
  `insights.md` line (Implementation Steps step 9) instead.

- **D3 — render the classification, do not merely exclude.** The queue allowed
  either. Excluding only would collapse "a rule read this path and declared it
  cannot evidence a mode" into the same empty cells as "no rule reads this path"
  — losing the distinction item 137 added the `rule_mode_less` tag to preserve,
  in the very column that exists to explain the mode cell. The cost is a new
  per-entry field, a twelfth Markdown column, a `SCHEMA_VERSION` bump and a
  one-literal change in `scripts/aide_status_report.py`; item 124 paid exactly
  this cost for the `observed` column and is the precedent.

- **D4 — a separate `path_classification_conflicts()` rather than folding into
  `rule_declaration_conflicts()`.** The latter is asserted clean on this tree by
  `test_136::test_ac6`, `test_137` and `test_146::test_ac11`, and it answers a
  different question (does a declaration agree with the corpus and the
  specification?). Folding the path checks in would change what "clean" means
  for three items' tests at once and blur two independent conformance claims.
  The cost is a second function a caller must remember; AC20 keeps both pinned
  clean.

- **D5 — "no other column moved" is expressed as a live invariant, not a
  snapshot.** The queue's *Testable* asks for the diff against the committed
  copy to be exactly the attribution change. A test that pins the pre-change
  artifact is a bound on this item's diff, which
  `.aide/conventions.md` §1 → `items.md` excludes from acceptance criteria, and
  it could not be re-checked after merge; committing such a snapshot under
  `tests/` would also break `test_105`'s 20-file census (**A7**). AC13 states
  the stronger, permanent claim instead — the classification mechanism can only
  move `failure_modes`, `mode_evidence` and `mode_roles`, proved by building
  twice against the same path universe. The diff-time half of the claim is
  `aide scope`'s, against the **Authorised paths** list above.

- **D6 — the title diverges from the queue's.** The queue entry is headed
  "Per-detector mode attribution…" and the claim branch keeps that slug; the
  shape chosen is per-path (D1), so the spec's title says so. The queue's own
  text already allows both ("Whichever of the two shapes is chosen"), and the
  deliverable — the catalogue stops painting bookkeeping paths — is unchanged.

- **D7 (builder, 2026-09-04) — the classification was authored from the
  Implementation-Steps table and then measured; the table was right in nine
  places out of ten.** `build_catalogue()`'s measured `consuming_rules` reach
  matched step 2's authored path lists exactly for all ten rules (border 9,
  bounds 6, coverage 4, fragmentation 7, intensity 5,
  `intensity_reference_delta` 8, mislabel 9, overlap 6, `reference_delta` 11,
  sequence 5 — 70 pairs). One **role** in the table is wrong and was corrected
  against the rule body per **A5**: `mislabel`'s `per_label` is `bookkeeping`,
  not `not-read`. `MislabelRule.evaluate` reads `record["per_label"]` at
  `src/segfacet/heuristics/mislabel.py:407` and scans it through
  `_label_for_level` to resolve a non-monotonic pair's level names back to
  integer label ids for the finding's `labels` set — so a `not-read` claim
  there would have been false, and AC7 would not have caught it (the pair
  carries mechanism-B `"static"` evidence, not mechanism-A `"observed"`). The
  table's other two `per_label` `not-read` claims (`intensity` reads
  `image_features.per_label`, `reference_delta` reads
  `reference_delta.per_label`) were verified and stand.

- **D8 (builder, 2026-09-04) — every measured figure in A5 held.** The
  regenerated catalogue reproduces the predicted per-mode path counts exactly
  — 1: 19→**8**, 2: 21→**12**, 3: 7→**5**, 4: 10→**6**, 5: 4→**2**,
  6: 9→**6**, 7: 6→**2**, 8: 6→**1**, 9: 12→**2** — and step 7's nine-bucket
  `mode_evidence` distribution exactly, including the unmoved 86-entry `()`
  bucket and 2-entry `("per_mode_metric",)` bucket, with no entry becoming
  `("rule_unmapped",)`. Mode 9 lands on exactly the two
  `image_features.per_label.{label}.first_order.*` paths (AC12), and each of
  modes 1–8 keeps at least one. `path_classification_conflicts()`,
  `rule_declaration_conflicts()` and `failure_modes.specification_conflicts()`
  are all `()` on the shipped tree, and both catalogue artifacts regenerate
  byte-identically across two runs.

- **D9 (builder, 2026-09-04) — the item-147 review's `evidence`-string fix was
  attempted and reverted: it is out of this item's authorised paths.** The
  finding (`insights.md`, item 147, 2026-09-04) is that
  `heuristics/intensity.py` and `heuristics/intensity_reference_delta.py`
  still describe the retired `"corpus"`-tag mechanism as live in their
  declaration `evidence`. Restating both as plain provenance moves the
  Evidence column of `docs/aide/traceability_matrix.generated.{json,md}` —
  measured: 4 changed lines across the pair, the Evidence cells alone, nothing
  else. Those two artifacts are listed under **Asserts against** as
  pinned-not-changed (AC18), so `aide scope 148 --base aide/queue-020` failed
  with four errors naming them. Widening the item's own authorised paths to
  admit the regeneration is exactly the silent scope creep the fence exists to
  prevent, so the edit was reverted, both artifacts regenerate byte-identical
  to their committed copies again (AC18 holds), and the insight stays
  **unticked** for a follow-up item that authorises the matrix pair.

- **D10 (builder, 2026-09-04) — two committed tests fail against this item's
  own spec; neither is a production defect and the builder does not edit
  tests.** (1)
  `tests/test_148_per_path_mode_attribution.py::test_ac15_schema_version_and_status_report_loader`
  raises `AttributeError: 'NoneType' object has no attribute '__dict__'` from
  `dataclasses._is_type` while importing `scripts/aide_status_report.py`: the
  module's `_status_report_module()` helper omits the
  `sys.modules[spec.name] = module` line that the helper it is modelled on
  (`tests/test_103_feature_catalogue.py:861`) carries, and that script's
  `from __future__ import annotations` makes every dataclass field annotation
  a string the `dataclass` decorator then resolves through `sys.modules`.
  Independently verified: with the line added, `load_feature_catalog` returns a
  non-empty tuple of `FeatureGroupSpec` for the regenerated committed artifact,
  which is what AC15 asserts, and `test_103`'s own
  `test_ac22_rendered_section_markup_shape` passes against `"1.2"`. (2)
  `tests/test_103_feature_catalogue.py::test_ac13_rule_mode_map_effect_on_failure_modes[overlap-modes4]`
  asserts a non-anchor, `signal`-classified entry consumed only by each rule
  exists; `overlap`'s only `signal` path under this spec's own step-2 table is
  `overlaps[].overlap_voxels`, which is also `MODE_ANCHOR_PATHS[8]`'s sole
  member, so the match set is empty by construction for `overlap` alone. The
  honest fix is a per-rule exemption in the test, not a wider `overlap`
  classification: calling `overlaps[]` or `overlaps[].label_a` `signal` would
  ship the false claim this item exists to remove.
