# Item 065 — Stage 8 integration & acceptance suite *(completes Stage 8)*

> **Created:** 2026-07-13 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 8 — Image-Based / Radiomics Features (Phase 2)
> **Queue:** [`../queue/queue-007.md`](../queue/queue-007.md) · Item 065
> **Objectives:** Closes Stage 8 (Phase 2 image-based features); extends the
> explainable failure-mode detection arm (G2-style) to scan **intensities**.
> **Suggested branch:** `aide/065-stage-8-integration-acceptance-suite`

---

## Description

Wire the already-merged Stage-8 image-feature family **end-to-end into the real
`segqc run` pipeline** and prove the roadmap's Stage-8 acceptance bar over item
058's committed intensity corpus. This is the **integration + acceptance-closure**
item: **no new feature or rule logic** is written here — every computational piece
already exists and is ✅:

- item 058 — `segqc.synth.intensity`: HU-painted clean + implausible scan
  fixtures, committed at `tests/corpus/intensity/` (`load_intensity_manifest`).
- item 059 — `segqc.features.intensity.compute_intensity_features`: per-label
  first-order HU stats.
- item 060 — `segqc.features.radiomics.compute_radiomics_features`: optional
  PyRadiomics adapter that degrades to first-order-only when absent.
- item 061 — `segqc.feature_report.build_image_features_block` +
  `serialize_report(..., image_features=…)` + `render_feature_table(...,
  image_features=…)`: report/feature-table fusion.
- item 062 — `segqc.heuristics.intensity.IntensityRule` (`rule_id="intensity"`),
  reads `record["image_features"]`, fires on absolute-band implausible HU.
- item 063 — `segqc.reference.*`: bundled reference (schema `1.1`) now carries
  per-level `intensity_*` distributions.
- item 064 — `segqc.reference.delta.compute_intensity_reference_delta` +
  `segqc.heuristics.intensity_reference_delta.IntensityReferenceDeltaRule`
  (`rule_id="intensity_reference_delta"`), reads
  `record["intensity_reference_delta"]`, fires on level-aware outliers.

Items 062 and 064 explicitly deferred the *pipeline/CLI/config wiring* to this
item: their rules are registered and enabled-by-default but **inert** because
nothing populates `record["image_features"]` / `record["intensity_reference_delta"]`
yet. This item does exactly that wiring, plus the acceptance suite.

**What it does.**
1. A new additive pipeline entry point `run_qc_with_intensity` (sibling of item
   049's `run_qc_with_reference`) that composes geometric features + intensity /
   radiomics features + the `image_features` block + (optionally) the geometric
   and intensity reference-deltas into the record fed to the rule engine.
2. A `--intensity` CLI toggle on `segqc run` (mirroring `--reference`) that turns
   the intensity path on; **OFF by default**, so today's geometric-only output —
   and the item-042 golden snapshots — stay byte-identical.
3. Documentation of the intensity knobs in `default_config.yaml` (comment blocks,
   mirroring the existing `reference:` mode block) plus a top-level `intensity:`
   mode section + `intensity_param` accessor mirroring item 049's reference mode.
4. A Stage-8 acceptance suite driving item 058's committed corpus through the
   real pipeline **and the CLI**: clean scan passes with no intensity finding;
   the metal / soft-tissue / degenerate variants each fire an intensity finding on
   the target label; everything round-trips through the JSON report.

**What it is NOT.** No new statistic, rule, extractor, fixture, schema field, or
reference rebuild. `run_qc` and `run_qc_with_reference` are **not modified** (the
intensity path is a new sibling). `default_config.yaml`'s parsed `rules`/`verdict`
dict is **not changed** (so `config_hash`, the committed `reference_default.json`,
and item-035's rule-id-count test do not regress — see Assumptions). No
`roadmap.md` edit (PR-gated). No `progress.md` edit (the builder sets 🚧; the
validator reconciles ✅ via the CLI).

## Acceptance Criteria

- [ ] **AC1: `run_qc_with_intensity` returns the composed 5-tuple.**
  `segqc.pipeline.run_qc_with_intensity(seg_img, scan_img, config)` (no
  `reference`) returns `(case_result, features_block, image_features_block,
  reference_delta, intensity_reference_delta)` where `reference_delta is None`
  and `intensity_reference_delta is None`, and `image_features_block["available"]
  is True` with a `first_order` sub-dict for every present non-zero label.

- [ ] **AC2: existing entry points are byte-for-byte unchanged.** For the same
  `seg_img`/`config`, `run_qc` still returns its 2-tuple and
  `run_qc_with_reference` still returns its 3-tuple, each equal to the pre-065
  result (the intensity path is purely additive; no shared code path is mutated).

- [ ] **AC3: clean fixture is intensity-silent.** Running the committed
  `clean_hu` intensity case (scan + shared seg from
  `load_intensity_manifest()`) through `run_qc_with_intensity` yields **no**
  finding with `rule_id == "intensity"`.

- [ ] **AC4: metal variant fires "too high".** On the committed
  `implausible_metal` case, `run_qc_with_intensity` emits ≥1 finding with
  `rule_id == "intensity"` whose `labels == frozenset({22})` and whose reason
  denotes an above-band (too-high) median.

- [ ] **AC5: soft-tissue variant fires "too low".** On `implausible_soft_tissue`,
  an `intensity` finding fires on label 22 whose reason denotes a below-band
  (too-low) median.

- [ ] **AC6: degenerate variant fires "degenerate/uniform".** On
  `degenerate_uniform`, an `intensity` finding fires on label 22 whose reason
  denotes the degenerate/uniform (near-zero std) condition.

- [ ] **AC7: only the target label is intensity-flagged.** On each implausible
  variant, every `intensity` finding names exactly label 22 and no other label
  is flagged by the intensity rule (the untouched levels stay plausible).

- [ ] **AC8: CLI emits `image_features` on a clean run.** `segqc run --scan
  <clean_hu scan> --seg <shared seg> --intensity --out <dir>` exits `0` and writes
  `<dir>/segqc_report.json` whose `image_features` block is present,
  `available == True`, and carries a per-label `first_order` dict; the report's
  `findings` list contains no `intensity` finding.

- [ ] **AC9: CLI flags the metal variant end-to-end.** `segqc run --scan
  <implausible_metal scan> --seg <shared seg> --intensity --out <dir>` writes a
  report whose `findings` include ≥1 entry with `rule_id == "intensity"` naming
  label 22, and whose `image_features` block is present.

- [ ] **AC10: `--intensity` off preserves geometric-only output.** `segqc run
  --scan <scan> --seg <seg> --out <dir>` (no `--intensity`, no config
  `intensity.enabled`) writes a report with **no** `image_features` key and no
  `intensity` finding — identical to the pre-065 report on the same inputs.

- [ ] **AC11: the intensity path is config/flag toggleable.** With the flag/config
  off, `image_features` is absent; with `--intensity` (or config
  `intensity.enabled: true`) it is present. `config.intensity_param("enabled",
  False)` returns the parsed config value and defaults to `False` when the
  `intensity:` section is absent.

- [ ] **AC12: no config-hash / rule-id-count regression.**
  `set(load_config(default_config_path()).rules.keys())` still equals the seven
  active rule ids `{bounds, fragmentation, coverage, sequence, border, overlap,
  mislabel}`, and `reference.artifact.config_hash(bundled_default_config())`
  equals the `config_hash` embedded in the committed
  `src/segqc/reference/reference_default.json`
  (`87c73ab35da9707054b300e15664c391ce50851c5d11490c89125381c1c96ac8`) — i.e.
  adding the intensity wiring changes neither `config.rules` nor the bundled
  reference artifact.

- [ ] **AC13: reference-grounded intensity rule participates.** With a reference
  supplied, `run_qc_with_intensity(seg_img, scan_img, config, reference=ref)`
  returns a non-`None` `intensity_reference_delta` dict whose `per_label`
  entries carry an `available` flag, and the `intensity_reference_delta` rule is
  run over the composed record (it stays **silent** on the clean `clean_hu`
  fixture — no spurious level-aware flag).

- [ ] **AC14: intensity delta is inert without intensity reference data.** Given a
  reference that carries no `intensity_*` distributions, `run_qc_with_intensity(...,
  reference=ref)` does not raise and emits no `intensity_reference_delta` finding
  (backward compatibility).

- [ ] **AC15: end-to-end determinism.** Two `run_qc_with_intensity` calls on the
  same inputs return equal findings and an equal `image_features_block`; two CLI
  `segqc run --intensity` invocations on the same inputs write byte-identical
  `segqc_report.json`.

- [ ] **AC16: Stage-8 acceptance suite present and green.** A dedicated module
  `tests/test_065_acceptance_stage8.py` drives item 058's **committed** intensity
  corpus through the real pipeline/CLI and asserts the roadmap Stage-8 bar —
  image features computed on fixtures, ≥1 intensity heuristic firing on the
  implausible variants and silent on clean GT — with every assertion passing.

## Assumptions  <!-- MANDATORY -->

- **`--scan` already exists; the toggle is `--intensity`.** `segqc run` has
  required `--scan`/`--seg` since items 006/010 and already loads the scan via
  `io.load_case` (`case.scan.data`/`case.scan.affine`), so **no new scan-loading
  flag is introduced**. A new `--intensity` store-true flag (mirroring
  item 049's `--reference`) gates the intensity path; it is **OFF by default** so
  every reference-less/intensity-less caller and the item-042 golden snapshots are
  untouched. Interface pinned: `case.scan.data` is the intensity array,
  `case.scan.affine` its affine.

- **`default_config.yaml` keeps its seven active `rules.*` sections — the intensity
  rules stay section-less (code defaults), mirroring `reference_delta`.** This is
  the pivotal design decision. The registered rules `reference_delta`, `intensity`,
  and `intensity_reference_delta` **already ship enabled-by-default with no active
  YAML section**, reading their thresholds via `config.rule_param(id, key,
  default=…)` (items 047/062/064). Adding active `rules.intensity` /
  `rules.intensity_reference_delta` sections would change `config.rules` → change
  `reference.artifact.config_hash(bundled_default_config())` → make the committed
  `reference_default.json` (whose provenance embeds that hash) stale and force a
  reference **rebuild**, and would break item-035's exact-seven-rule-id test
  (`tests/test_035_default_config.py::test_ac2_no_extra_or_missing_rule_ids`). The
  queue note "mirroring how items 047/049 deferred their YAML" is honoured
  literally: item 049 added a **comment-documented mode block + CLI flag + param
  accessor** and relied on code defaults for the rule itself — it did **not** add
  a `rules.reference_delta` section. This item does the same: a comment-documented
  `intensity:` mode block + commented example `rules.intensity` /
  `rules.intensity_reference_delta` threshold blocks (documenting the item-062/064
  code defaults for operators to uncomment/tune), with the parsed `rules` dict
  unchanged. Result: `config_hash`, the bundled reference artifact, the item-042
  goldens, and item-035's rule-id test all stay green with zero regression
  (AC12). *If the human reviewer instead wants the two rules discoverable as
  active `rules.*` sections, that additionally requires regenerating
  `reference_default.json` and updating item-035's rule-id-set assertion — call it
  out at the queue boundary and hand back before doing so.*

- **A top-level `intensity:` mode section is added to the config model, excluded
  from `config_hash`.** Mirroring `reference`: a new `HeuristicConfig.intensity:
  Dict[str, Any] = {}` field, a `"intensity": {}` entry in `config._DEFAULTS`, and
  an `intensity_param(key, default)` accessor. Like `reference`, the `intensity`
  field is **not** in `config_hash`'s canonical field list
  (`reference/artifact.py::config_hash` — schema_version, min_foreground_voxels,
  min_label_count, min_fragment_voxels, rules, verdict), so it never affects an
  artifact's provenance hash, and an absent `intensity:` section leaves
  `load_config(default_config_path()) == default_config()` intact.

- **`run_qc_with_intensity` is a new additive sibling.** It composes
  `extract_feature_record` + `compute_radiomics_features` +
  `build_image_features_block`, and when a `reference` is passed also
  `compute_reference_delta` + `compute_intensity_reference_delta`, attaching
  `image_features` (always) and `reference`/`reference_delta`/
  `intensity_reference_delta` (reference mode) to the **transient** rule record.
  `run_qc`/`run_qc_with_reference` are not edited (preserving ~40 call sites and
  the goldens, per item 049's precedent).

- **`intensity_reference_delta` is a transient rule-record key, not a new report
  block.** Like `reference` in `run_qc_with_reference`, it feeds `run_rules` but is
  not serialized into the JSON report — avoiding a `report_schema_v0.json` change.
  `image_features` **is** serialized (item 061 already added that schema property
  and the `serialize_report(..., image_features=…)` param). Level-aware intensity
  findings still surface in the report's `findings`. (A future item may add an
  `intensity_reference_delta` report block behind a schema bump.)

- **Radiomics defaults on and auto-degrades.** `run_qc_with_intensity` calls the
  item-060 adapter with `enable_pyradiomics=True`; PyRadiomics is absent in CI, so
  the builtin first-order path runs and `image_features.backend == "builtin"`,
  `radiomics_available == False`. The acceptance suite runs with PyRadiomics
  absent. A config knob (`intensity_param("radiomics", True)`) can force-disable it.

- **Grid alignment.** Intensity extraction requires scan↔seg identical shape +
  affine within tolerance (item 059 `_check_alignment`); the committed intensity
  corpus satisfies this (item 058 paints on the seg grid/affine). The CLI catches
  the `ValueError` a misaligned real case would raise and reports a clean error
  (exit 1), not a traceback.

- **Corpus specifics (item 058).** Target label L3 = integer **22**
  (`intensity._TARGET_LABEL`); cases are `clean_hu`, `implausible_metal`,
  `implausible_soft_tissue`, `degenerate_uniform`; the shared seg fixture is
  `fixtures/clean_spine_seg.nii.gz`, scans are `fixtures/<case_id>_scan.nii.gz`,
  paths relative to `tests/corpus/intensity/`.

- **Threshold sanity (items 062 + 058).** IntensityRule defaults (min 100 / max
  2000 HU; degenerate std ≤ 1.0) fire as intended on the corpus fills — metal
  mean 3000 > 2000 (AC4), soft-tissue mean 40 < 100 (AC5), degenerate std 0 ≤ 1
  (AC6) — and pass clean (cancellous ~200 / cortical ~600 medians sit inside
  `(100, 2000)`, AC3). If a builder finds a fixture median that lands off these
  expectations, hand back rather than retuning item-062 defaults here.

## Implementation Steps

_All paths under `src/segqc` (`source_dir`)._

1. **`config.py`** — add `intensity: Dict[str, Any] = field(default_factory=dict)`
   to `HeuristicConfig`; add `"intensity": {}` to `_DEFAULTS`; add an
   `intensity_param(self, key, default)` accessor mirroring `reference_param`.
   Do **not** touch `reference/artifact.py::config_hash` (the `intensity` field is
   intentionally outside its canonical list). Confirm
   `load_config(default_config_path()) == default_config()` still holds.

2. **`pipeline.py`** — add
   `run_qc_with_intensity(seg_img, scan_img, config, *, reference=None,
   base_reasons=(), base_per_label=None, enable_pyradiomics=True, stratum="all",
   lower_pct=1, upper_pct=99) -> Tuple[CaseResult, dict, dict, Optional[dict],
   Optional[dict]]`:
   - `features_block = extract_feature_record(seg_img, config)`.
   - `radiomics = compute_radiomics_features(scan_img, seg_img,
     enable_pyradiomics=enable_pyradiomics)`; build
     `image_features = build_image_features_block(
       intensity={lbl: r.first_order for lbl, r in radiomics.items()},
       extended={lbl: r.extended for lbl, r in radiomics.items()},
       backend=("pyradiomics" if any(r.radiomics_available for r in
       radiomics.values()) else "builtin"),
       radiomics_available=any(r.radiomics_available for r in radiomics.values()))`.
   - `rule_record = {**features_block, "image_features": image_features}`.
   - When `reference is not None`: compute geometric `reference_delta` (item 046)
     and `intensity_reference_delta` (item 064's
     `compute_intensity_reference_delta(features_block, image_features, reference,
     …)`), `reference_delta_to_dict` both, and add `"reference"`,
     `"reference_delta"`, `"intensity_reference_delta"` to `rule_record`; else the
     two delta returns are `None`.
   - `findings = run_rules(rule_record, config)`;
     `case_result = build_case_result(findings, config, base_reasons=…,
     base_per_label=…)`.
   - Return the 5-tuple; add the symbol to `__all__`. **Leave `run_qc` and
     `run_qc_with_reference` untouched.**

3. **`cli.py`** (`run` subcommand) — add a `--intensity` store-true flag (help
   text mirroring `--reference`). In `_handle_run`, compute
   `intensity_enabled = bool(args.intensity) or bool(cfg.intensity_param("enabled",
   False))`. When enabled: build `scan_img = nib.Nifti1Image(case.scan.data,
   case.scan.affine)`; dispatch to `run_qc_with_intensity` (threading `reference`
   when `reference_enabled`, else `reference=None`); wrap the call to catch the
   grid-alignment `ValueError` → `print("Error: …"); return 1`. Thread the
   returned `image_features` into `serialize_report_json(..., image_features=…)`
   and into `render_human_report(..., image_features=…)`. When disabled, the
   existing `run_qc` / `run_qc_with_reference` branch is unchanged (no
   `image_features`).

4. **`human_report.py`** — add an optional `image_features: dict | None = None`
   parameter to `render_human_report`, delegating to the existing item-061
   `_render_image_features_section` so an intensity section renders when present;
   default `None` keeps the item-010/035 output byte-identical.

5. **`default_config.yaml`** — add a comment-documented `intensity:` mode block
   (mirroring the `reference:` comment block: `enabled: false`, `radiomics: true`)
   and commented example `rules.intensity` / `rules.intensity_reference_delta`
   threshold blocks echoing the item-062/064 code defaults (min/max plausible HU,
   max_degenerate_std, max_robust_z, max_distribution_distance, severity).
   **Comments only** — the parsed `rules`/`verdict` mappings, and thus
   `config_hash`, are unchanged.

6. _(test-writer, separate)_ — `tests/test_065_acceptance_stage8.py` plus focused
   unit/CLI modules (see Testing Strategy). The test-writer also owns any assertion
   updates; item-035's rule-id-count test should **not** need changing under this
   spec (verify it stays green).

## Testing Strategy

_One focused test per AC, plus adversarial/edge/determinism cases. Mirror the
item-049 (`test_049_acceptance_stage6.py` + `test_049_reference_integration.py`)
and item-057 (`test_057_acceptance_stage7.py` + `test_057_evaluate_cli.py`) split._

- **`tests/test_065_acceptance_stage8.py`** (the Stage-8 closer, AC3–AC7, AC16):
  load the committed intensity corpus via `load_intensity_manifest()` /
  `INTENSITY_CORPUS_DIR`, load each case's scan + shared seg as `Nifti1Image`s,
  drive `run_qc_with_intensity`, and assert: clean → no `intensity` finding;
  metal/soft-tissue/degenerate → an `intensity` finding on label 22 with the
  expected reason class; only label 22 flagged. Include a docstring stating the
  roadmap Stage-8 bar this closes.
- **`tests/test_065_intensity_pipeline.py`** (AC1, AC2, AC13, AC14, AC15):
  5-tuple shape/None-ness; `run_qc`/`run_qc_with_reference` outputs unchanged
  vs. a saved expectation; reference-mode composition returns a populated
  `intensity_reference_delta` and the rule stays silent on clean GT; a
  no-`intensity_*` reference stays inert (no raise, no finding); two calls equal.
- **`tests/test_065_cli_intensity.py`** (AC8–AC11, AC15): invoke `cli.main([...])`
  into a `tmp_path` out dir; parse `segqc_report.json`; assert `image_features`
  presence/absence per flag, `intensity` finding presence on the metal variant,
  geometric-only output identical without `--intensity`, and byte-identical JSON
  across two invocations.
- **`tests/test_065_config_intensity.py`** (AC11, AC12): `intensity_param`
  default/override; `set(cfg.rules.keys())` unchanged; `config_hash(
  bundled_default_config())` equals the committed `reference_default.json` hash;
  `load_config(default_config_path()) == default_config()`.
- **Adversarial / edge:** scan↔seg shape/affine mismatch → CLI clean error + exit
  1 (no traceback); a seg with a label absent from the scan-painted region still
  produces a well-formed sentinel `first_order` (item 059) and no crash;
  `--intensity` with a 0/1-label map (no Stage 3) still emits a valid
  `image_features` block; determinism of the acceptance corpus across two runs.

## Dependencies

- **Item 058** ✅ — committed intensity corpus + `load_intensity_manifest`
  (test inputs; target label 22; case ids).
- **Item 059** ✅ — `compute_intensity_features` / `LabelIntensity` (first-order
  stats; grid-alignment guard).
- **Item 060** ✅ — `compute_radiomics_features` / `LabelRadiomics` (optional
  PyRadiomics, auto-degrade; the single extraction entry `run_qc_with_intensity`
  calls).
- **Item 061** ✅ — `build_image_features_block`, `serialize_report(...,
  image_features=…)`, `render_feature_table(..., image_features=…)` /
  `_render_image_features_section` (report + human fusion).
- **Item 062** ✅ — `IntensityRule` (`rule_id="intensity"`; absolute-band firing;
  code-default thresholds).
- **Item 063** ✅ — reference schema `1.1` with per-level `intensity_*`
  distributions (bundled `reference_default.json`).
- **Item 064** ✅ — `compute_intensity_reference_delta` +
  `IntensityReferenceDeltaRule` (`rule_id="intensity_reference_delta"`;
  level-aware firing; code-default thresholds).

All ✅ in `progress.md`. Direct structural precedent: items 049 and 057
(`run_qc_with_reference` / `_handle_evaluate` + their acceptance suites).

## Decisions & Trade-offs

To be updated during implementation.
