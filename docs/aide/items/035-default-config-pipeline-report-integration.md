# Item 035 — Default Heuristic Config + Pipeline/Report Integration & Per-Failure-Mode Tests

> **Created:** 2026-07-07 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 4 — Heuristic Rule Engine over the Failure Modes (G2)
> **Queue:** [`../queue/queue-003.md`](../queue/queue-003.md) · Item 035 *(completes Stage 4)*
> **Objectives:** G2 (each §6 failure mode fires ≥1 heuristic on a crafted example;
> a ground-truth example stays clean), G4 (the flags + reasons + offending labels
> surface in both the JSON and human-readable QC reports)
> **Suggested branch:** `aide/035-default-heuristic-config-pipeline-report`

---

## Description

The **capstone of Stage 4**: turn the seven already-merged rule families
(items 027–033), the item-026 rule engine, and the item-034 verdict aggregator
into a working **end-to-end pipeline**, backed by a **documented, versioned default
config file**, and surface every flag in both reports. Three deliverables, one
item:

1. **Ship a documented, versioned default heuristic-config file**
   (`src/segqc/default_config.yaml`, `schema_version: "0.1"`) that materialises the
   thresholds for **all seven** rule families plus the verdict-aggregation policy,
   each with an inline comment justifying the value. It loads through the existing
   item-005 `load_config` loader and is bundled as package data.

2. **Wire the rule engine into the pipeline end-to-end.** Today `segqc run`
   (`cli.py::_handle_run`) only does the Stage 1 empty/near-empty check. This item
   adds a small **feature-extraction + QC orchestration layer** (a new
   `src/segqc/pipeline.py`) that: assembles the per-case **feature record** (the
   Stage 2 block from items 011–016, plus the Stage 3 `stage3` sub-block from items
   018–020 when there are ≥2 centroids) exactly in the shape the rules consume;
   runs the rules over it via `run_rules` (item 026); folds the findings — together
   with the Stage 1 empty-check reasons as `base_reasons` — into a verdict via
   `build_case_result` (item 034). The CLI then renders the **flags + reasons +
   offending labels** into both the **JSON report** (`report.py` /
   `report_schema_v0.json`, extended with a validated `findings` block) and the
   **human-readable report** (`human_report.py`, a new Findings section).

3. **Add the crafted-example acceptance tests the stage gate (G2) requires:** for
   **each of the eight §6 failure modes** a crafted example fires ≥1 heuristic of
   the mapped rule with the expected offending labels, and a crafted **ground-truth**
   example stays clean (`pass` verdict, zero findings — no false flags). Correct
   **firing and non-firing** are both asserted, closing the Stage 4 acceptance boxes.

### The §6 failure-mode → rule mapping this item must demonstrate

Per the queue's coverage table (rule_id in parentheses):

| # | §6 failure mode | Fires rule |
|---|-----------------|------------|
| 1 | Label not aligned with the vertebra it names | `mislabel` (spline-offset detector) |
| 2 | Over-/under-segmentation (fused / fragmented) | `bounds` (volume/extent out of range) |
| 3 | Disconnected components / rogue islands | `fragmentation` (island detector) |
| 4 | Semantic mislabelling (wrong identification) | `mislabel` (order detector) |
| 5 | Not all vertebrae segmented (missing levels) | `coverage` (missing-interior) |
| 6 | Partial vertebra at the image border | `border` (unexpected clip) |
| 7 | Non-continuous label sequence | `sequence` |
| 8 | Overlapping segments | `overlap` |

### The feature record the rules consume (already the `build_features_block` shape)

`run_rules` passes the per-case record straight to each rule. The rules read these
top-level keys (confirmed by reading items 027–033):

- `record["per_label"]` — string-int-keyed; each entry has `label`, `level_name`,
  `geometry` (volume/extent/border flags), `components` (sizes,
  `fragmentation_index`), `centroid`. Consumed by `bounds`, `fragmentation`,
  `border`, and (for level→label resolution) `coverage`/`sequence`/`mislabel`.
- `record["relationships"]` — `present_levels`, `missing_levels`, `is_continuous`,
  `out_of_order_labels`. Consumed by `coverage`, `sequence`, `border`.
- `record["overlaps"]` — list of overlap pairs. Consumed by `overlap`.
- `record["stage3"]` — `per_label_offsets`, `monotonic_consistency`. Consumed by
  `mislabel`.

This is **exactly** the dict `feature_report.build_features_block(...)` already
returns, so the pipeline uses that block, unchanged, as the rule record — no new
record schema is introduced.

### Scope boundary — what this item is **not**

- **Not new rules or new feature extractors.** It only wires the existing
  extractors (011–020) and rules (026–034) together and ships their default config.
  No new `Rule`, no new `compute_*`.
- **Not a threshold calibration.** The shipped values are the existing hand-set
  code defaults, now materialised and documented in one file. Reference-derived
  bounds (Stage 6) and calibrated thresholds (Stage 7) are out of scope.
- **Not the synthetic-corpus generator.** The eight §6 crafted examples here are
  minimal **crafted feature records** (and, for the pipeline-wiring proof, a couple
  of real synthetic label maps); the full failure-generator + committed multi-mode
  NIfTI corpus is **Stage 5**.
- **Not a report schema-version bump.** `findings` is added as an *optional*
  top-level property (mirroring how item 016 added the optional `features` block
  without bumping `schema_version` from `"0.1"`); verdict-only (item 009) and
  features-only (item 016) reports stay valid.

---

## Acceptance Criteria

### A. Default config file

- [ ] **AC1: The bundled default config file exists and loads.**
      `src/segqc/default_config.yaml` exists; `segqc.config.default_config_path()`
      returns its path; and `load_config(default_config_path())` returns a
      `HeuristicConfig` with `schema_version == "0.1"` without raising.

- [ ] **AC2: The file declares every rule family and the verdict policy.** The
      loaded config's `rules` mapping contains an entry for each of the seven rule
      ids — `bounds`, `fragmentation`, `coverage`, `sequence`, `border`, `overlap`,
      `mislabel` — each with `enabled == True`, and the `verdict` section contains a
      `flag_escalation_count` key.

- [ ] **AC3: Documented thresholds match the shipped code defaults.** For a
      representative parameter of each family the file's value equals the rule
      module's default constant, so the file is a faithful materialisation:
      `fragmentation.fragmentation_index_threshold == 0.75`,
      `fragmentation.island_min_voxels == 50`, `overlap.min_overlap_voxels == 1`,
      `mislabel.max_offset_mm == 15.0`, `verdict.flag_escalation_count == 0`, and a
      `bounds` group (e.g. `lumbar.max_volume_mm3 == 120000`) reachable via
      `rule_param`.

- [ ] **AC4: `bundled_default_config()` is a convenience for the file.**
      `segqc.config.bundled_default_config()` returns a `HeuristicConfig` equal to
      `load_config(default_config_path())`.

- [ ] **AC5: The bundled config reproduces the built-in defaults' verdict.**
      Running the pipeline (`run_qc`) over a crafted ground-truth record under
      `bundled_default_config()` and under `default_config()` yields the **same**
      overall verdict and the **same** findings (the file adds no behaviour beyond
      documenting the existing defaults).

### B. Feature-extraction + QC orchestration (`segqc.pipeline`)

- [ ] **AC6: `extract_feature_record` builds a schema-valid feature block.**
      `segqc.pipeline.extract_feature_record(seg_img, config)` on a multi-label
      synthetic case returns a dict with keys `features_version`, `per_label`,
      `relationships`, `overlaps`, and (≥2 labels) `stage3`; embedding it via
      `serialize_report(..., features=block)` validates against the schema.

- [ ] **AC7: `extract_feature_record` is robust to degenerate label maps.** On a
      zero-label (empty) map it returns a block with empty `per_label`, `overlaps
      == []`, `relationships == None`, and **no** `stage3` key, without raising; on
      a single-label map it returns per-label geometry/components/centroid and
      **no** `stage3` key (spline fit needs ≥2 centroids), without raising.

- [ ] **AC8: `run_qc` runs rules + aggregates over the extracted record.**
      `segqc.pipeline.run_qc(seg_img, config, base_reasons=br,
      base_per_label=bpl)` returns a `(CaseResult, features_block)` pair where
      `CaseResult.findings == tuple(run_rules(features_block, config))` and
      `CaseResult.verdict == aggregate_verdict(run_qc-findings, config,
      base_reasons=br, base_per_label=bpl)`.

- [ ] **AC9: `run_qc` threads the Stage 1 base reasons through.** Given a
      `base_reasons` list containing a `Severity.FAIL` reason (the empty-check
      result) and a record that produces no findings, `run_qc`'s returned verdict
      has `overall == Severity.FAIL` and its `reasons` contain that base reason.

### C. JSON report + schema extension

- [ ] **AC10: The schema gains an optional `findings` array.**
      `report_schema_v0.json` defines a top-level optional `findings` array whose
      items require `rule_id` (non-empty string), `severity` (enum
      `pass`/`flagged-for-review`/`fail`), `reason` (string), and `labels` (array
      of integers), with `additionalProperties: false`; `schema_version` stays
      `"0.1"`.

- [ ] **AC11: `serialize_report` embeds findings and still validates.**
      `serialize_report(verdict, case_id, cfg, features=block,
      findings=[f.to_dict() for f in findings])` returns a dict whose `findings`
      list equals the passed dicts and passes schema validation.

- [ ] **AC12: Findings serialise losslessly.** For each embedded finding the JSON
      carries its `rule_id`, its `severity` **string label**, its `reason`
      verbatim, and its `labels` as a **sorted** integer list (matching
      `Finding.to_dict`).

- [ ] **AC13: Omitting findings preserves the prior report shape.**
      `serialize_report(verdict, case_id, cfg)` (no `findings`, no `features`)
      produces a dict with **no** `findings` key that still validates — the
      item-009/016 report shape is unchanged (backward compatible).

### D. Human-readable report

- [ ] **AC14: The human report renders a Findings section.**
      `render_human_report(verdict, case_id, cfg, findings=findings)` returns text
      containing a "Findings" section that lists, for each finding, its `rule_id`,
      its severity label, and its `reason` string **verbatim**, plus its offending
      labels (or an explicit no-label marker for a case-level finding).

- [ ] **AC15: The human report is backward-compatible and non-empty with no
      findings.** `render_human_report(verdict, case_id, cfg)` (findings omitted)
      still returns the item-010 report (Verdict / Reasons / Per-label sections)
      unchanged, and `render_human_report(verdict, case_id, cfg, findings=[])`
      renders the Findings section as "(none)"; both are non-empty and contain no
      raw Python `repr`/`frozenset`/class-name text.

### E. CLI end-to-end wiring

- [ ] **AC16: `segqc run` on a ground-truth-shaped fixture writes both wired
      reports.** `segqc run --scan <gt> --seg <gt> --out <dir>` writes
      `segqc_report.json` and `segqc_report.txt`; the JSON validates against the
      schema and contains both a `features` block and a `findings` array; the run
      exits without error.

- [ ] **AC17: The CLI fires a heuristic end-to-end on a crafted real label map.**
      Running `segqc run` on a crafted synthetic label map exhibiting a failure
      mode reachable through real extraction (two overlapping labels **or** a
      missing interior level) produces a JSON report whose `findings` array is
      non-empty and whose `verdict` is not `pass`, and the process exit code
      reflects the aggregated verdict (0 for `flagged-for-review`, 1 for `fail`).

- [ ] **AC18: The CLI uses the bundled default config and honours `--config`.**
      With no `--config` flag the CLI loads `bundled_default_config()`; with
      `--config <path>` it loads that YAML via `load_config`; a `--config` path
      that does not exist (or fails schema validation) makes the CLI print an error
      to stderr and exit 1 without a traceback.

### F. Per-failure-mode coverage (the Stage 4 G2 gate) — one crafted example each

- [ ] **AC19: §6 mode 1 (misalignment) fires `mislabel`.** A crafted record with a
      `stage3.per_label_offsets` entry whose `offset_mm >= 15.0` for label 20 (L1)
      yields ≥1 `Finding` with `rule_id == "mislabel"` and `labels == frozenset({20})`.

- [ ] **AC20: §6 mode 2 (over-/under-segmentation) fires `bounds`.** A crafted
      record with a lumbar label 20 (L1) whose `geometry.physical_volume_mm3` is far
      above the lumbar `max_volume_mm3` yields ≥1 `Finding` with `rule_id ==
      "bounds"` and `labels == frozenset({20})`.

- [ ] **AC21: §6 mode 3 (rogue islands) fires `fragmentation`.** A crafted record
      whose label 20 has `components.component_sizes == [1000, 5]` (a tiny
      non-dominant component below `island_min_voxels == 50`) yields ≥1 `Finding`
      with `rule_id == "fragmentation"` whose reason starts with the island tag and
      `labels == frozenset({20})`.

- [ ] **AC22: §6 mode 4 (semantic mislabelling) fires `mislabel`.** A crafted
      record with `stage3.monotonic_consistency.non_monotonic_pairs == [["L2","L1"]]`
      and a `per_label` mapping L1→20, L2→21 yields ≥1 `Finding` with `rule_id ==
      "mislabel"` whose reason starts with the ordering tag and whose `labels`
      includes both 20 and 21.

- [ ] **AC23: §6 mode 5 (missing levels) fires `coverage`.** A crafted record with
      `relationships.missing_levels == ["T12"]` yields ≥1 **case-level** `Finding`
      with `rule_id == "coverage"`, `labels == frozenset()`, and the missing level
      named in the reason.

- [ ] **AC24: §6 mode 6 (border-partial) fires `border`.** A crafted record with a
      label 20 whose `geometry.touches_left == True` (an in-plane face) yields ≥1
      `Finding` with `rule_id == "border"` and `labels == frozenset({20})`.

- [ ] **AC25: §6 mode 7 (non-continuous sequence) fires `sequence`.** A crafted
      record with `relationships.out_of_order_labels == ["L1", "T12"]` and a
      `per_label` mapping resolving those names yields ≥1 `Finding` with `rule_id ==
      "sequence"` attributing the offending integer labels.

- [ ] **AC26: §6 mode 8 (overlapping segments) fires `overlap`.** A crafted record
      with `overlaps == [{"label_a": 20, "label_b": 21, "name_a": "L1", "name_b":
      "L2", "overlap_voxels": 40}]` yields ≥1 `Finding` with `rule_id == "overlap"`
      and `labels == frozenset({20, 21})`.

- [ ] **AC27: All eight modes are covered by the run engine together.** Running
      `run_rules` over the union/each of the eight crafted records above, under
      `bundled_default_config()`, produces at least one finding tagged with the
      mapped `rule_id` for **every** mode 1–8 (the single assertion that the stage's
      "each of the 8 §6 failure modes has ≥1 heuristic firing" gate is met).

### G. No false flags + determinism

- [ ] **AC28: A ground-truth crafted example passes with no findings.** A crafted
      in-range GT record (every per-label metric inside the default bounds; single
      component per label; `fragmentation_index == 1.0`; `relationships` continuous
      with no missing/out-of-order levels; no overlaps; all `stage3` offsets `< 15`
      mm; `monotonic_consistency.non_monotonic_pairs == []`; no in-plane border
      touches) yields `run_rules(...) == []` and `build_case_result(...).verdict`
      has `overall == Severity.PASS` (no false flags).

- [ ] **AC29: The wired pipeline is deterministic.** Two `run_qc` calls on the same
      `seg_img` and config return equal findings tuples and equal verdicts; two CLI
      runs on the same inputs produce byte-identical `segqc_report.json`.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **The "feature block" the rules run over is the `build_features_block` dict,
  unchanged.** Pinned interface: `feature_report.build_features_block(...)` returns
  `{features_version, per_label, relationships, overlaps[, stage3]}`, and items
  027–033 read exactly those keys (`per_label`, `relationships`, `overlaps`,
  `stage3.per_label_offsets`, `stage3.monotonic_consistency`). No new record schema
  is created; the pipeline reuses the block as the rule record. If any rule diverged
  from these keys, the builder/validator hands back.

- **No production orchestration existed, so this item adds one.** The current CLI
  computes no features; feature extraction only lives in test helpers
  (`tests/test_016_*::_features_for_case`, `tests/test_022_*::_stage2_for_case` /
  `_build_stage3`). This item promotes that pattern into a production
  `src/segqc/pipeline.py` calling the real extractors:
  `compute_label_geometry`, `compute_components`, `compute_centroid` (items 011–013),
  `compute_spine_relationships` (014), `detect_overlaps` (015), and — when ≥2
  centroids — `fit_centroid_spline` (017), `compute_spline_offsets` (018),
  `compute_vertebra_orientations` / `compute_spine_curvature` (019),
  `compute_spacing_consistency` / `compute_monotonic_consistency` (020), then
  `build_features_block`. This is the smallest new surface that makes `segqc run`
  actually execute the rules.

- **Stage 3 is guarded on ≥2 centroids.** `fit_centroid_spline` raises `ValueError`
  for `< 2` centroids, so the pipeline computes the `stage3` sub-block only when the
  case has ≥2 labelled vertebrae, and omits it otherwise (0/1-label maps still
  produce a valid Stage-2-only block). `mislabel` already tolerates an absent
  `stage3` (returns no findings), so this degrades cleanly.

- **The extractors accept a NiBabel image, so the pipeline takes `seg_img`.** The
  Stage 2/3 `compute_*` functions take a `nib.Nifti1Image` (+ label int). The CLI
  already builds `seg_img = nib.Nifti1Image(case.seg.data.astype("int32"),
  case.seg.affine)`; the pipeline accepts that `seg_img` and derives the present
  labels from its non-zero unique values (excluding 0), matching the existing
  inventory. `compute_components` also takes `config` (item 012), which the pipeline
  threads through.

- **The eight §6 crafted examples are crafted feature *records*, and the GT-pass
  example likewise; a couple of real synthetic label maps prove the CLI wiring.**
  Under clarify `assume`, this is the most defensible reading of "crafted example":
  the honest unit for "a heuristic fires" is the feature record the rule consumes,
  and each rule family's own item-027…033 tests already craft such records —
  reusing that idiom keeps Stage 4 decoupled from the extraction stack (covered by
  its own tests) and from Stage 5's full-NIfTI synthetic corpus. To still prove the
  extraction→rules→report path is genuinely wired, AC16/AC17 additionally drive the
  **real CLI** over synthetic NIfTI fixtures (item 002) for the GT-writes case and
  for at least one extraction-reachable failure mode (overlap or missing-level). The
  validator surfaces this split at the queue boundary.

- **"A ground-truth fixture passes (no false flags)" is demonstrated with a crafted
  in-range GT record, not the raw item-002 synthetic blocks.** The item-002 fixtures
  are geometric placeholders (small cubes) not tuned to the default *anatomical*
  bounds, so feeding them raw through `bounds`/`mislabel` could legitimately flag
  them. Tuning a full NIfTI that passes every default threshold is Stage 6/7's
  calibration job; here the no-false-flag guarantee is asserted on a crafted record
  whose every metric sits inside the shipped defaults (AC28). AC16 therefore asserts
  the CLI *writes valid wired reports* on a real fixture, not that the raw fixture
  scores `pass`.

- **`findings` is an optional top-level report property; `schema_version` stays
  `"0.1"`.** Mirrors item 016's precedent (the `features` block was added as an
  optional property without a version bump). Each finding object is exactly
  `Finding.to_dict()` shape (`rule_id`, `severity` label string, `reason`,
  sorted-int `labels`). Verdict-only and features-only reports remain valid, so
  existing `test_009` / `test_016` report tests are unaffected.

- **The default config is bundled as package data with no `pyproject.toml` change.**
  Hatch already packages the entire `src/segqc` directory
  (`[tool.hatch.build.targets.wheel] packages = ["src/segqc"]`), which is how
  `report_schema_v0.json` ships today; the new `default_config.yaml` beside it is
  included automatically. It is read via `importlib.resources` (the pattern
  `report.py::_load_schema` already uses), so the path is correct from source tree
  and installed wheel alike.

- **The CLI loads the bundled default by default and adds an optional `--config`.**
  This makes "thresholds live in config" literal at the CLI boundary while keeping
  behaviour identical to the built-in defaults (AC5). Because the bundled file
  carries the same empty-detection fields (`min_foreground_voxels`,
  `min_label_count`) at their `0` defaults, the Stage 1 empty-check behaviour and
  exit-code semantics are unchanged; the only report changes are the additive
  `features` + `findings` keys. The builder must keep both report files written on
  every path (including `fail`) and preserve the `fail → 1`, otherwise `0` exit rule,
  now driven by the **aggregated** verdict.

- **Human-report and `serialize_report` gain optional `findings` params** (default
  `None`), so both stay backward-compatible and unit-testable in isolation, matching
  how `features` was threaded as an optional param in item 016.

## Implementation Steps

Intended code path in `src/segqc` (see `aide.toml`). Ordered.

1. **Ship `src/segqc/default_config.yaml`.** Top of file: `schema_version: "0.1"`.
   A `rules:` mapping with an entry per rule id — `bounds`, `fragmentation`,
   `coverage`, `sequence`, `border`, `overlap`, `mislabel` — each `enabled: true`
   with a `params:` block carrying that rule's documented thresholds **equal to its
   code defaults**, one inline comment per value justifying it:
   - `bounds.params`: the three level groups (`cervical`/`thoracic`/`lumbar`) each
     with `min/max_volume_mm3` + `min/max_extent_{x,y,z}_mm` copied from
     `heuristics/bounds.py::DEFAULT_BOUNDS`, plus `severity: flagged-for-review`.
   - `fragmentation.params`: `fragmentation_index_threshold: 0.75`,
     `island_min_voxels: 50`, `severity: flagged-for-review`.
   - `coverage.params`: `border_aware: true`, `expected_levels: []`,
     `expected_count: null`, `severity: flagged-for-review` (opt-in checks stay off).
   - `sequence.params` / `border.params`: `severity: flagged-for-review` (+
     `report_expected_ends: false`, `end_severity: pass` for `border`).
   - `overlap.params`: `min_overlap_voxels: 1`, `severity: flagged-for-review`.
   - `mislabel.params`: `max_offset_mm: 15.0`, `flag_offset_outliers: true`,
     `flag_order_inconsistency: true`, `severity: flagged-for-review`.
   - `verdict:` section with `flag_escalation_count: 0`.
   - Keep `min_foreground_voxels: 0` / `min_label_count: 0` so the empty-check is
     unchanged. Add a header comment documenting the file's role and version policy.

2. **Extend `src/segqc/config.py`.** Add `default_config_path() -> pathlib.Path`
   (via `importlib.resources.files(segqc).joinpath("default_config.yaml")`, mirroring
   `report._load_schema`) and `bundled_default_config() -> HeuristicConfig`
   (= `load_config(default_config_path())`); add both to `__all__`. Do **not** change
   `SUPPORTED_SCHEMA_VERSION`, `_DEFAULTS`, or `load_config`'s merge.

3. **Extend `src/segqc/report_schema_v0.json`.** Add an optional top-level
   `findings` property: `{"type":"array","items":{"$ref":"#/definitions/finding"}}`
   and a `finding` definition (`additionalProperties:false`, required `rule_id`
   (minLength 1), `severity` (enum pass/flagged-for-review/fail), `reason`,
   `labels` (array of integers)). Leave `schema_version.const == "0.1"` and the
   existing `required` list untouched (so `findings` is optional).

4. **Extend `src/segqc/report.py`.** Add `findings: "list[dict] | None" = None` to
   `serialize_report` and `serialize_report_json`; when non-`None`, set
   `report["findings"] = findings` **before** `jsonschema.validate`. Accept dicts
   (as produced by `Finding.to_dict()`) so `report.py` keeps no dependency on the
   heuristics package. Preserve the existing `features` handling.

5. **Extend `src/segqc/human_report.py`.** Add `findings: "list | None" = None` to
   `render_human_report`. When non-`None`, append a "Findings" section: one block
   per finding printing `[severity.label] (rule_id) reason` and an offending-labels
   line (sorted ints, or "case-level" when empty); render "(none)" for an empty
   list. Accept either `Finding` objects or their `to_dict()` dicts (read
   `rule_id`/`severity`/`reason`/`labels` defensively) so the module stays
   stdlib-only. Keep the existing sections and the omitted-`findings` behaviour
   identical.

6. **Create `src/segqc/pipeline.py`.**
   - `extract_feature_record(seg_img, config) -> dict`: derive present labels from
     `seg_img` (sorted non-zero uniques); compute the Stage 2 maps
     (`compute_label_geometry`, `compute_components(…, config)`, `compute_centroid`),
     `compute_spine_relationships` over the ordered centroid sequence (or `None`
     when no labels), `detect_overlaps` over the mask stack (or `[]`); when
     `len(labels) >= 2`, fit the spline and compute the five Stage 3 objects, else
     pass all Stage 3 args as `None`; return `build_features_block(...)`.
   - `run_qc(seg_img, config, *, base_reasons=(), base_per_label=None) ->
     tuple[CaseResult, dict]`: `block = extract_feature_record(seg_img, config)`;
     `findings = run_rules(block, config)`;
     `case_result = build_case_result(findings, config, base_reasons=base_reasons,
     base_per_label=base_per_label)`; return `(case_result, block)`.
   - Import the heavy extractors lazily (inside the functions) to keep
     `import segqc.pipeline` cheap, consistent with the CLI's deferred-import style.

7. **Wire `src/segqc/cli.py::_handle_run`.**
   - Add an optional `--config <yaml>` argument to the `run` subparser.
   - Replace `cfg = default_config()` with: load `--config` via `load_config` when
     given, else `bundled_default_config()`; wrap `SegQCConfigError` into a stderr
     message + `return 1`.
   - Keep the empty-check; turn its `CheckResult` into the same `Reason` list as
     today and use it as `base_reasons` (case-level) for aggregation.
   - Call `case_result, features_block = run_qc(seg_img, cfg,
     base_reasons=base_reasons)`; take `verdict = case_result.verdict`.
   - Write JSON via `serialize_report_json(verdict, case_id, cfg,
     features=features_block, findings=[f.to_dict() for f in case_result.findings])`.
   - Write the human report via `render_human_report(verdict, case_id, cfg,
     findings=case_result.findings)`; optionally append
     `render_feature_table(features_block)`.
   - Exit code from the **aggregated** verdict: `FAIL → 1`, else `0`. Both files are
     written on every path.

8. **Do not** add new rules or extractors, bump `schema_version`, or edit
   `aggregate.py` / the `heuristics` package / any `features/*` extractor.

## Testing Strategy

- **Framework:** `pytest`. New modules:
  `tests/test_035_default_config.py`, `tests/test_035_pipeline.py`,
  `tests/test_035_report_integration.py` (JSON+human), `tests/test_035_cli_e2e.py`,
  and `tests/test_035_failure_modes.py` (the eight §6 crafted examples + GT-pass).
  Reuse `tests/synthetic.py` (`labelled_blocks_case`, `empty_case`,
  `anisotropic_case`, `make_labelmap`) and the crafted-record idioms from the
  per-rule tests (027–033).
- **Config file (AC1–AC5):** load the bundled file; assert version, presence of all
  seven rule sections + the `verdict` section, the representative-threshold equalities
  (AC3) via `rule_param`/`policy_param`, `bundled_default_config()` equality (AC4),
  and equal verdict/findings vs `default_config()` on a crafted GT record (AC5).
- **Pipeline (AC6–AC9):** run `extract_feature_record` on a multi-label case →
  schema-valid block with `stage3` (AC6); on `empty_case()` and a single-label
  `make_labelmap` → robust, no `stage3` (AC7); assert `run_qc` equals
  `run_rules`+`aggregate_verdict` composition (AC8) and threads a FAIL `base_reasons`
  through (AC9).
- **Report integration (AC10–AC15):** schema has the `finding` definition with the
  right required keys (AC10); `serialize_report(..., findings=…)` round-trips +
  validates (AC11) and is lossless field-by-field (AC12); omitting findings keeps the
  prior shape (AC13); `render_human_report(..., findings=…)` shows rule_id + reason
  verbatim + labels (AC14); backward-compat + "(none)" + no-`repr` cleanliness (AC15).
- **CLI e2e (AC16–AC18):** invoke `cli.main(["run", …])` (or the console entry) with
  `tmp_path` out dir over synthetic NIfTI written by `synthetic.write_nifti`; assert
  both files written, JSON validates and carries `features` + `findings` (AC16); a
  crafted overlapping-label / missing-level NIfTI yields non-empty `findings`,
  non-`pass` verdict, and the matching exit code (AC17); `--config` load path, bundled
  default fallback, and a missing/invalid `--config` → exit 1 + stderr, no traceback
  (AC18).
- **Per-failure-mode (AC19–AC27):** build one minimal crafted record per mode (the
  shapes are pinned in the ACs above; labels T12=19, L1=20, L2=21), call
  `run_rules(record, bundled_default_config())`, and assert ≥1 finding of the mapped
  `rule_id` with the expected offending labels / reason tag. AC27 asserts the union
  across all eight modes covers each `rule_id` — the single Stage-4 G2 gate assertion.
- **No false flags + determinism (AC28–AC29):** the crafted in-range GT record →
  `run_rules == []` and `PASS` verdict (AC28); two `run_qc` calls equal and two CLI
  runs byte-identical JSON (AC29).
- **Adversarial / edge cases:** empty and single-label maps through the full CLI (no
  crash, `fail`/`pass` as the empty-check dictates); anisotropic-spacing case (physical
  volumes correct, no spurious bounds flag); a record missing `stage3` fed to
  `mislabel` (no crash, no finding); a malformed `overlaps`/`relationships` placeholder
  (`{}` / `None`) tolerated by the rules; `--config` pointing at a wrong-version YAML
  (clean error); immutability — `extract_feature_record`/`run_qc` do not mutate the
  passed config or leak state between calls.

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 026** — engine core (`run_rules`, `Rule`, registry, `Finding`): the
    runner this pipeline invokes and the record contract it feeds.
  - **Items 027–033** — the seven rule families whose findings this item surfaces;
    their per-rule tests supply the crafted-record idioms reused here.
  - **Item 034** — `segqc.aggregate` (`build_case_result`, `aggregate_verdict`,
    `CaseResult`, `policy_param`): the verdict folding this pipeline calls, plus the
    `verdict` config section this item's default file materialises.
  - **Items 011–020, 016, 022** — the Stage 2/3 extractors and
    `build_features_block` / `feature_report` this pipeline orchestrates into the
    record.
  - **Items 005 / 007 / 008 / 009 / 010** — `config` (`load_config`, `_DEFAULTS`,
    `HeuristicConfig`), the empty-check (source of `base_reasons`), the
    `verdict`/`report`/`human_report` layers this item extends.
  - **Item 002** — the synthetic NIfTI fixtures the CLI e2e and pipeline tests drive.
- **Downstream:** **Stage 5** (synthetic failure corpus + full-pipeline regression +
  golden JSON) builds directly on the `run_qc` pipeline, the `findings` report block,
  and the per-mode coverage established here.

This item integrates only already-merged interfaces; it is the join that makes
`segqc run` execute the Stage 4 rule engine end-to-end and closes Stage 4 (G2).

## Decisions & Trade-offs

To be updated during implementation.
