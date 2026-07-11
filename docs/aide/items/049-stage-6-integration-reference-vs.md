# Item 049 — Stage 6 integration & reference-vs-perturbation acceptance tests

> **Created:** 2026-07-11 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 6 — VerSe Reference Distributions & Delta-to-Reference Rules (G3)
> **Queue:** [`../queue/queue-005.md`](../queue/queue-005.md) · Item 049 *(completes Stage 6)*
> **Objectives:** G3 (distinguish failure from legitimate variation — the
> reference-grounded half), G7 (evaluable / regression-testable)
> **Suggested branch:** `aide/049-stage-6-integration-reference-vs`

---

## Description

Close Stage 6 by **wiring the reference artifact and delta-to-reference layer
into the real `segqc run` pipeline** and adding the stage's **acceptance suite**
proving the roadmap's **G3** bar: clean ground-truth sits **inside** the
reference ranges while distorted (perturbed) cases fall **outside** and are
flagged by the new reference-delta mechanisms.

Items 043–048 built every component but left them *dark* in the real pipeline:

- item 046's `compute_reference_delta`/`reference_delta_to_dict` and
  `serialize_report(reference_delta=…)` exist but nothing computes or passes the
  block during a run;
- item 047's `ReferenceDeltaRule` reads `record["reference_delta"]` — **always
  absent** in real runs;
- item 048's reference-mode `BoundsRule` reads `record["reference"]` — **always
  absent** in real runs.

This item is the integration seam that populates those keys, plus the acceptance
tests that exercise the whole path end-to-end.

**What this item does.**
1. Add a **reference-aware pipeline entry point**
   `segqc.pipeline.run_qc_with_reference(seg_img, config, reference, *,
   base_reasons=(), base_per_label=None, stratum="all", lower_pct=1,
   upper_pct=99)` that: extracts the Stage 2/3 feature block (reusing
   `extract_feature_record`), computes the `reference_delta` block via item 046,
   builds a **rule-evaluation record** `{**features_block, "reference":
   reference, "reference_delta": <delta dict>}`, runs the Stage 4 rules over
   *that* record (so item 047's rule fires and item 048's bounds-reference mode
   can source bounds), aggregates the verdict, and returns
   `(case_result, features_block, reference_delta_dict)`.
2. Add a **config switch + CLI flags** so `segqc run` can enable reference mode
   (loading the bundled default artifact by default, or a `--reference-artifact`
   path), rendering the `reference_delta` block into the JSON report and the
   reference-delta findings into the human report.
3. Add the **Stage-6 acceptance suite** — build/load a reference from the
   synthetic GT cohort, then assert clean-GT-in-range (no reference-delta
   findings, low false-positive) and perturbed-out-of-range (reference-delta
   findings on the offending label) over the committed Stage-5 corpus.
4. **Document** the reproducible reference-build + evaluation path.

**Key design decision — reference mode is OFF by default (see Assumptions).**
The existing `run_qc` (2-tuple return) and every caller/test of it stay
**byte-identical**; item 042's committed golden snapshots and item 041's
regression suite are untouched. Reference mode is a *distinct, additive* code
path enabled explicitly (config `reference.enabled` / `--reference` flag / a
direct `run_qc_with_reference` call in the acceptance suite). This satisfies the
roadmap Stage-6 acceptance ("GT within reference ranges; perturbed outside") —
a test-level bar the acceptance suite meets by enabling reference explicitly —
without the report-shape change that on-by-default would force onto every
committed golden.

**In scope:** `run_qc_with_reference` in `pipeline.py`; the `reference` config
section + accessor in `config.py` (comments-only documentation in
`default_config.yaml`); the `--reference`/`--no-reference` +
`--reference-artifact` flags and reference wiring in `cli._handle_run`; the
Stage-6 acceptance test module; the reference-build/evaluation doc snippet.

**Out of scope (do NOT):** change `run_qc`'s signature or 2-tuple return (would
break ~40 existing test unpackings and the golden/regression harnesses);
regenerate or alter the item-042 goldens or `tests/corpus/**`; change
`DEFAULT_BOUNDS`, `SUPPORTED_SCHEMA_VERSION`, the report schema (item 046 already
added `reference_delta`), or the committed `reference_default.json`; add a
dedicated reference-delta *table* to the human report (reference findings already
render via the existing Findings section); alter items 043–048's modules beyond
importing them; flip the default bounds `source` (stays `hand-set` per item 048).

## Acceptance Criteria

_Each criterion is atomic and directly testable. Pipeline/config/CLI ACs:
`tests/test_049_reference_integration.py`. Acceptance-suite ACs:
`tests/test_049_acceptance_stage6.py` (see Testing Strategy)._

- [ ] **AC1: reference-aware entry point exists and returns a 3-tuple.**
  `segqc.pipeline.run_qc_with_reference(seg_img, config, reference, *,
  base_reasons=(), base_per_label=None, stratum="all", lower_pct=1,
  upper_pct=99)` returns `(case_result, features_block, reference_delta)` where
  `case_result` is a `CaseResult`, `features_block` is the same dict shape
  `extract_feature_record` returns, and `reference_delta` is the dict from
  `reference_delta_to_dict(compute_reference_delta(features_block, reference,
  stratum=…, lower_pct=…, upper_pct=…))`.

- [ ] **AC2: the reference is visible to the rules.** In
  `run_qc_with_reference`, the record fed to the rule engine carries
  `record["reference"]` (the passed `ReferenceDistribution`) and
  `record["reference_delta"]` (item 046's dict), so item 047's
  `ReferenceDeltaRule` produces findings for an out-of-distribution label and
  item 048's `BoundsRule` in `source: reference` mode sources its bounds from
  the reference. (Test: a label whose geometry is far outside the reference
  yields ≥1 `rule_id == "reference_delta"` finding in `case_result.findings`.)

- [ ] **AC3: the returned `reference_delta` block is JSON-serializable and
  correct.** The third return value round-trips through `json.dumps` and equals
  `reference_delta_to_dict(compute_reference_delta(features_block, reference,
  stratum=…, lower_pct=…, upper_pct=…))` computed independently for the same
  inputs.

- [ ] **AC4: the returned `features_block` stays clean.** The `features_block`
  (second return value) contains **no** `"reference"` or `"reference_delta"`
  keys, so `serialize_report(…, features=features_block)` still validates
  against the `additionalProperties: false` features schema. (The reference keys
  live only on the transient rule-evaluation record, never on the returned
  block.)

- [ ] **AC5: `segqc run --reference` emits the reference block.** With reference
  mode enabled (via `--reference`, or config `reference.enabled: true`), the
  written `segqc_report.json` contains a top-level `reference_delta` object with
  the item-046 shape, and the whole report validates against
  `report_schema_v0.json`. Reference-delta findings (rule_id
  `reference_delta`) appear in both the JSON `findings` array and the human
  report's Findings section.

- [ ] **AC6: reference mode is OFF by default (report shape unchanged).** With
  no `--reference` flag and the bundled default config, `segqc run`'s
  `segqc_report.json` contains **no** `reference_delta` key and is the same shape
  as before this item (item-035/046 shape), so existing behaviour and the
  item-042 golden snapshots are unaffected.

- [ ] **AC7: `--reference-artifact` overrides the loaded artifact; default loads
  the bundled one.** With `--reference` and no `--reference-artifact`, the run
  uses `bundled_default_reference()`; with `--reference-artifact <path>` it loads
  that artifact via `load_artifact` (and a missing/invalid path is reported as a
  caller error returning exit 1, not a traceback).

- [ ] **AC8: config switch round-trips and leaves parsed default config
  unchanged.** `HeuristicConfig` gains a `reference` section read via
  `config.reference_param(key, default)`; a YAML with `reference: {enabled:
  true, lower_pct: 5, upper_pct: 95}` loads via `load_config` and the accessor
  returns those values, `schema_version` still `"0.1"`. `default_config.yaml`
  documents the section as **comments only**, so
  `load_config(default_config_path()) == default_config()` and
  `reference.config_hash(bundled_default_config())` is unchanged versus a
  pre-item snapshot (protecting item-045 provenance and the goldens).

- [ ] **AC9: the item-042 goldens remain byte-identical.**
  `segqc.synth.golden.write_goldens` (which calls the unchanged `run_qc`, no
  reference) reproduces every committed `tests/corpus/golden/<case_id>.json`
  byte-for-byte; `check_case_golden` is `True` for all cases. (Determinism
  contract of item 042 preserved — reference wiring did not leak into the
  reference-less path.)

- [ ] **AC10: G3 positive control — clean GT sits inside the reference ranges.**
  Running the reference-aware pipeline over the corpus **clean_control** case
  (its committed seg fixture) against a reference built/loaded from the
  synthetic GT cohort yields a `reference_delta` block in which every
  `available: true` label has an **empty** `out_of_range_features` list, and
  `case_result.findings` contains **no** `rule_id == "reference_delta"` finding
  (low false-positive on ground truth).

- [ ] **AC11: G3 detection — size-distorting perturbations fall outside the
  reference.** Running the reference-aware pipeline over the corpus
  **`mode3_inject_islands`** and **`mode6_crop_at_border`** cases (both target
  label 22 = L3) yields, for label 22, a **non-empty** `out_of_range_features`
  list **and** ≥1 `rule_id == "reference_delta"` finding whose `labels` include
  22. (These two modes distort tracked geometry — volume/extent — so the
  reference-delta layer detects them directly; see Assumptions on the other
  modes.)

- [ ] **AC12: reference loading is covered end-to-end.**
  `bundled_default_reference()` loads into a `ReferenceDistribution` covering the
  corpus levels (L1–L5), and a reference built via
  `segqc.reference.build_reference` over a fresh synthetic GT cohort likewise
  covers L1–L5; both are usable as the `reference` argument to
  `run_qc_with_reference`.

- [ ] **AC13: original `run_qc` is unchanged.** `run_qc(seg_img, config,
  base_reasons=…)` still returns the 2-tuple `(case_result, features_block)`,
  attaches no `reference`/`reference_delta` keys, and produces the same findings
  as before this item for the same inputs (the full pre-existing suite —
  test_035/036/037/038/039/040/041/042 — stays green).

- [ ] **AC14: determinism and non-mutation.** Two `run_qc_with_reference` calls
  on the same `(seg_img, config, reference)` return equal `case_result.findings`,
  `features_block`, and `reference_delta`; neither `seg_img`, `config`, nor
  `reference` is mutated (the reference-delta computation and the merged rule
  record never write back into the passed `reference` or `features_block`).

## Assumptions  <!-- MANDATORY -->

- **Reference mode defaults OFF; "load the bundled default by default" means
  *which* artifact, not *whether* to run (clarify `assume`).** The queue
  one-liner says "load the bundled default artifact by default, overridable by
  flag/config." Two readings: (a) reference on-by-default in `segqc run`, or (b)
  reference off-by-default but, *when enabled*, the bundled artifact is what
  loads without extra flags. **This spec takes (b).** Reasoning: on-by-default
  would add a `reference_delta` block (and reference-delta findings for the
  size-distorting corpus cases) to every report, changing the shape of — and
  requiring regeneration of — all nine item-042 golden snapshots, contradicting
  CLAUDE.md's byte-reproducible-fixture contract and item 048's stated guarantee
  that "the Stage 5 golden snapshots [stay] unchanged until reference mode is
  explicitly enabled." The roadmap Stage-6 acceptance ("GT within reference
  ranges; perturbed outside", **G3**) is a *test-level* bar the acceptance suite
  meets by enabling reference explicitly — it does not require production runs to
  default it on. If the reviewer wants on-by-default, that is a follow-up that
  also regenerates the goldens; the builder/validator should hand back to confirm
  before flipping the default. The validator should surface this decision.

- **New `run_qc_with_reference` rather than changing `run_qc` (pins the
  integration interface).** `run_qc`'s 2-tuple return is unpacked at ~40 sites
  across `cli.py`, `synth/golden.py`, `synth/regression.py`, and
  test_035–042. Changing its arity would break all of them and churn the
  goldens. The reference path is therefore an additive sibling returning a
  3-tuple. It reuses `extract_feature_record`, `run_rules`, and
  `build_case_result`; the builder may factor a small shared private helper to
  avoid duplication but must not alter `run_qc`'s observable behaviour.

- **Record-attachment keys match items 047/048 exactly.** The rule-evaluation
  record carries the loaded reference under `record["reference"]` (a
  `segqc.reference.schema.ReferenceDistribution` instance, as item 048's
  `BoundsRule` expects) and the item-046 delta dict under
  `record["reference_delta"]` (the `reference_delta_to_dict` shape, as item 047's
  `ReferenceDeltaRule` expects). These are the interfaces items 047/048 pinned;
  if either diverged from reality, hand back.

- **`spline_offset_mm` and the four geometry metrics come from the same
  `features_block` item 046 already consumes.** No new feature extraction; the
  delta reads `geometry.*` and `stage3.per_label_offsets` exactly as
  `compute_reference_delta` already does.

- **Not every perturbation mode is reference-delta-detectable — and that is
  correct.** The reference-delta layer scores per-vertebra *geometry*
  (volume/extents/spline-offset) against the reference. It reliably flags the
  **size-distorting** modes (`mode3_inject_islands` — adds voxels/extent above
  p99; `mode6_crop_at_border` — removes voxels/extent below p1). The other
  corpus modes are, by construction, **not** geometry-out-of-range against a
  clean reference and remain covered by their native Stage-4 rules (and item
  041's regression suite), not the reference-delta layer:
  `mode5_remove_level` (label simply absent → coverage rule);
  `mode7_sequence_break` (relabel/ordering → sequence/mislabel rules);
  `mode2_fragment` (volume conserved; split → fragmentation rule; its extent
  *may* grow but is not asserted here); and the three `reconstructed_record`
  modes `mode1_displace`/`mode4_relabel_swap`/`mode8_force_overlap` (item 040:
  structurally invisible to plain `run_qc`). AC11 therefore asserts the two
  robustly-detectable modes; the acceptance suite does not over-claim that the
  reference-delta layer catches all eight. The validator should note this scope.

- **The acceptance reference brackets the corpus GT.** The reference used by the
  acceptance suite is built/loaded from a synthetic clean-GT cohort **with
  per-subject variation** spanning L1–L5 (e.g. `bundled_default_reference()`,
  whose bundled cohort varies spacing 0.8–1.2 mm and curve amplitude 3–8 mm, or
  a fresh `build_reference` over a comparable `build_clean_spine` cohort), so the
  corpus base spine (spacing 1.0 mm, amplitude 6 mm, L1–L5) sits **interior** to
  each level's `[p1, p99]` band and `out_of_range` is strict (`value < p1` or
  `value > p99`; a value equal to a bound is in-range). If a chosen reference
  makes the clean control land exactly on a degenerate (single-value) band, the
  test-writer widens the cohort variation.

- **Default percentile pair `(1, 99)` and stratum `"all"`** — matching
  `delta.DEFAULT_LOWER_PCT`/`DEFAULT_UPPER_PCT` and `schema.ALL_STRATUM`, the
  established Stage-6 conventions and item 048's bounds defaults.

- **`config.py` needs a new `reference` section but no schema bump.** The section
  is a free-form dict (like `verdict`/`rules`) accessed via a new
  `reference_param` helper; it is **excluded** from `config_hash`'s canonical
  field list (which enumerates `schema_version`, `min_foreground_voxels`,
  `min_label_count`, `min_fragment_voxels`, `rules`, `verdict`), so adding it
  leaves `config_hash` and the item-045 provenance byte-stable. No
  `SUPPORTED_SCHEMA_VERSION` change.

## Implementation Steps

Code paths in `src/segqc/` (`pipeline.py`, `config.py`, `default_config.yaml`,
`cli.py`) plus the acceptance tests and a doc snippet.

1. **`pipeline.run_qc_with_reference`** (new public function; add to `__all__`).
   Signature per AC1. Body:
   1. `features_block = extract_feature_record(seg_img, config)`.
   2. Deferred import `from segqc.reference import compute_reference_delta,
      reference_delta_to_dict`; `delta = compute_reference_delta(features_block,
      reference, stratum=stratum, lower_pct=lower_pct, upper_pct=upper_pct)`;
      `reference_delta = reference_delta_to_dict(delta)`.
   3. `rule_record = {**features_block, "reference": reference,
      "reference_delta": reference_delta}` (shallow copy; never mutate
      `features_block`).
   4. `findings = run_rules(rule_record, config)`;
      `case_result = build_case_result(findings, config,
      base_reasons=base_reasons, base_per_label=base_per_label)`.
   5. `return case_result, features_block, reference_delta`.
   Optionally factor steps shared with `run_qc` into a private
   `_evaluate(record, config, base_reasons, base_per_label) -> CaseResult`.
   Leave `run_qc` itself **unchanged**.
2. **`config.py`** — add `reference: Dict[str, Any] = field(default_factory=dict)`
   to `HeuristicConfig`; add `"reference": {}` to `_DEFAULTS`; add
   `reference_param(self, key, default)` mirroring `policy_param`. Do **not**
   touch `config_hash` (it lives in `reference/artifact.py` and already
   enumerates fields explicitly — leave it alone).
3. **`default_config.yaml`** — add a top-level **commented** `reference:` block
   documenting `enabled: false` (default), `artifact_path` (default: bundled),
   `lower_pct: 1`, `upper_pct: 99`, `stratum: all`. No active keys (keeps parsed
   config == `default_config()`, AC8/AC9).
4. **`cli.py` `run` subparser** — add `--reference` (store_true) /
   `--no-reference` (or a single flag defaulting to the config value) and
   `--reference-artifact <json>` (optional path). In `_handle_run`: resolve
   `reference_enabled` from the flag, falling back to
   `cfg.reference_param("enabled", False)`. When enabled: load the reference —
   `load_artifact(path)` if `--reference-artifact` given, else
   `bundled_default_reference()`; wrap load errors (`ReferenceArtifactError`,
   `OSError`) into a stderr message + `return 1`. Read `lower_pct`/`upper_pct`/
   `stratum` from config (defaults 1/99/"all"). Call
   `run_qc_with_reference(seg_img, cfg, reference, base_reasons=base_reasons,
   stratum=…, lower_pct=…, upper_pct=…)`, then
   `serialize_report_json(verdict, case_id, cfg, features=features_block,
   findings=findings_dicts, reference_delta=reference_delta)`. When disabled:
   the existing `run_qc` path, unchanged (no `reference_delta` argument).
   Reference-delta findings render in the human report via the existing
   `findings=case_result.findings` argument — no `human_report.py` change.
5. **Acceptance test module(s)** — see Testing Strategy.
6. **Documentation** — add a short "Building & evaluating against a reference"
   note (module docstring in the acceptance test and/or a comment block) giving
   the two reproducible commands already shipped by item 045
   (`segqc build-reference --cohort … --out …` for a mounted VerSe dir;
   `python -m segqc.reference.artifact` to regenerate the bundled default) plus
   `segqc run --reference …` to evaluate a case against it.

## Testing Strategy

Two focused modules (one test per AC plus edge cases):

**`tests/test_049_reference_integration.py`** (pipeline/config/CLI wiring):
- **AC1/AC3/AC4** — build a tiny seg via `build_clean_spine`, a reference via
  `bundled_default_reference()`; assert the 3-tuple shape, that `reference_delta`
  equals an independent `reference_delta_to_dict(compute_reference_delta(...))`,
  is `json.dumps`-able, and that `features_block` has no `reference`/
  `reference_delta` keys.
- **AC2** — hand-build (or perturb) a seg whose target label geometry is far
  outside the reference; assert a `reference_delta` finding fires on that label
  through `run_qc_with_reference`. Optionally assert item 048's bounds-reference
  mode by also setting `rules.bounds.params.source: reference` and checking the
  bounds reason quotes a reference percentile.
- **AC5/AC6/AC7** — drive `cli.main(["run", …])` into a tmp `--out`; parse
  `segqc_report.json`. With `--reference`: assert a `reference_delta` block and
  schema validity (`jsonschema.validate` against `report_schema_v0.json`), and a
  reference-delta finding in `findings` and in `segqc_report.txt`. Without the
  flag: assert no `reference_delta` key. With `--reference-artifact
  <bad path>`: assert exit 1 and no traceback; with a good written artifact path:
  assert it is used.
- **AC8** — round-trip a temp YAML with a `reference` section; assert
  `reference_param` values and that `load_config(default_config_path()) ==
  default_config()` and `config_hash` matches a snapshot.
- **AC13** — assert `run_qc` still returns a 2-tuple and (spot-check) equal
  findings to a pre-item expectation; rely on the full suite staying green.
- **AC14** — call `run_qc_with_reference` twice; assert equal outputs;
  deep-compare `config` and the `reference` object before/after for
  non-mutation.

**`tests/test_049_acceptance_stage6.py`** (the Stage-6 G3 acceptance suite):
- Fixture: a reference covering L1–L5 — `bundled_default_reference()` (primary,
  also covering AC12) and/or `build_reference` over a fresh
  `build_default_cohort`-style synthetic cohort. Load each corpus case's
  committed seg via `segqc.synth.regression.loaded_seg_image(case)` (reusing the
  Stage-0 loader path), then `run_qc_with_reference(seg_img,
  bundled_default_config(), reference)`.
- **AC10** — `clean_control`: every `available` label's
  `out_of_range_features == []`; no `reference_delta` finding.
- **AC11** — `mode3_inject_islands` and `mode6_crop_at_border`: label-22 entry
  has non-empty `out_of_range_features` and ≥1 `reference_delta` finding
  including label 22.
- **AC12** — assert `bundled_default_reference().levels` covers `L1`–`L5` (each
  with the `"all"` stratum and the four geometry features), and a
  `build_reference` result likewise.
- **Determinism** — re-run one case; assert equal `reference_delta`.
- **Edge cases** — a level absent from the reference yields an
  `available: false` label entry (no crash, no finding); an empty/degenerate
  band does not spuriously flag the clean control (widen cohort variation if so).

**`tests/test_042_golden_determinism.py`** must stay green unchanged (AC9); do
not modify it or the committed goldens. If any golden diff appears, the reference
path leaked into `run_qc`/`golden.build_report_for_case` — a bug to fix, not a
golden to regenerate.

## Dependencies

- **Item 046 (✅)** — `compute_reference_delta` / `reference_delta_to_dict` and
  `serialize_report(reference_delta=…)` + the schema's `reference_delta`
  definition: the block this item computes, attaches, and serialises.
- **Item 047 (✅)** — `ReferenceDeltaRule` reading `record["reference_delta"]`:
  the rule this item finally feeds in a real run.
- **Item 048 (✅)** — reference-mode `BoundsRule` reading `record["reference"]`:
  the bounds path this item's record attachment enables.
- **Item 045 (✅)** — `bundled_default_reference` / `load_artifact` /
  `build_reference` + the committed `reference_default.json`: the loaded
  reference and the reproducible build path.
- **Item 043 (✅)** — `segqc.reference.schema.ReferenceDistribution` (+
  `ALL_STRATUM`): the data model attached to the record.
- **Item 035 (✅)** — `pipeline.run_qc` / `extract_feature_record`,
  `cli._handle_run`, `serialize_report`, `default_config.yaml`, `load_config`:
  the pipeline/CLI/config surfaces extended here.
- **Items 040/041/042 (✅)** — the committed synthetic corpus + manifest,
  `synth.regression.loaded_seg_image`, and the golden harness: the acceptance
  suite's inputs and the byte-stability contract this item must not disturb.

## Progress reconciliation (for the validator — not edited by spec-author)

Item 049 completes Stage 6. On validated merge, the validator (via
`python .aide/scripts/aide.py progress …`) should reconcile in `progress.md`:

- the final Stage-6 deliverable bullet — "Reference artifact + delta rules wired
  into `segqc run`; Stage-6 acceptance suite …" — from 📋 to ✅ *(item 049)*;
- the three Stage-6 **Acceptance** checkboxes: "Reference artifact builds
  reproducibly … and is versioned" (items 045/049 doc path), "GT fixtures fall
  within reference ranges; perturbed cases fall outside (**G3**)" (this item's
  acceptance suite), and "Tests cover reference loading + delta rules";
- the **Stage 6** summary-row status 🚧 → ✅;
- the **G3** objective-coverage row — 🚧 → ✅ for the Stage-6 (reference-grounded)
  half (Stage 7 completes G3's calibration half; if the row tracks G3 across both
  stages it stays 🚧 until Stage 7 — the validator applies the row's convention).

## Decisions & Trade-offs

To be updated during implementation.
