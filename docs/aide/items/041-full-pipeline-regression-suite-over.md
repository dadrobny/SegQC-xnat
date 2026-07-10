# Item 041 — Full-pipeline regression suite over the corpus

> **Created:** 2026-07-10 · status tracked in [`progress.md`](../progress.md)
> **Stage:** 5 — Synthetic Failure Corpus & Regression Suite (G7)
> **Queue:** [`../queue/queue-004.md`](../queue/queue-004.md) · Item 041 *(the manifest-driven regression net; depends on 040, gates 042)*
> **Objectives:** G7 (evaluable & regression-testable — the full pipeline is
> asserted against every §6 failure mode) and the regression-coverage half of G2
> (every mode is provably caught by its designated heuristic)
> **Suggested branch:** `aide/041-full-pipeline-regression-suite-over`

---

## Description

Add a **manifest-driven, parametrised regression suite** that, for **every** case
in the committed corpus manifest (item 040), exercises the complete QC pipeline
and asserts that the case's **verdict** and **fired heuristic(s) + offending
labels** match the manifest — the **single source of expectations**. Because the
suite parametrises over `load_manifest()["cases"]` (not one hand-written test per
case), **appending a corpus case automatically extends coverage**. The suite is
the automated safety net that pins Stage 4→5 behaviour so future changes that
regress a mode's detection fail loudly.

Two deliverables:

1. **A small reusable verification library** — a new module
   `src/segqc/synth/regression.py` that turns one manifest case dict into the
   observable facts the suite asserts on: it loads the case's committed seg
   fixture via the Stage 0 loader, runs the pipeline (`run_qc`), and exposes pure
   predicates (`pipeline_verdict_label`, `designated_rule_fired`,
   `offending_labels_match`, `pipeline_hides_designated_rule`,
   `reconstructed_findings`, `verify_case`) that **dispatch on the case's
   `detection` discriminator**. Placing the harness alongside the item-040 corpus
   *generator* in `segqc.synth` keeps all G7 synthetic-corpus tooling in one
   importable subpackage and gives the drift/skip-guard meta-tests real functions
   to exercise (rather than test-file-private helpers).

2. **The parametrised pytest suite** — `tests/test_041_regression_suite.py`,
   parametrised over the committed manifest, that asserts the library's predicates
   hold for every case, plus **negative controls** proving the assertions bite
   (mutating an expectation makes the comparison fail) and a **skip-guard** proving
   no case is silently dropped.

### The two verification paths (the crux — item 040's `detection` field)

Item 040 committed nine cases; its manifest carries a **`detection`** discriminator
because three modes are *structurally invisible* to the plain pipeline (a
single-integer label map cannot encode an overlap; the interpolating /
ascending-label spline refit absorbs a displacement / identity swap). The
regression suite **must branch on `detection`** and must **not** weaken or skip
the three reconstructed cases — it is a genuine, complete net over **all 8 modes**:

- **`detection == "pipeline"` (6 cases: modes 0, 2, 3, 5, 6, 7).** Load the
  committed seg fixture, run `run_qc(seg_img, bundled_default_config())`, and assert
  directly against the manifest: `verdict.overall.label == expected_verdict`, the
  designated rule (`rule_id ∈ expected_rule_ids`) is among the findings, and the
  union of that rule's finding `labels` equals `expected_labels` (empty set for the
  case-level `remove_level` case).

- **`detection == "reconstructed_record"` (3 cases: mode 1 `displace`, mode 4
  `relabel_swap`, mode 8 `force_overlap`).** Assert first that plain `run_qc`
  **does not** surface the designated rule (the documented limitation), then assert
  the designated rule **does** fire via the **reconstruction technique** named in
  the case's `reconstruction` field — exactly the technique items 038/039 used in
  their own tests — with the expected offending labels. The manifest's
  `expected_verdict` for these cases records the *conceptual* outcome
  (`flagged-for-review`); per item 040's Assumptions the suite **must not** assert
  `run_qc(...).verdict == expected_verdict` for them.

The three reconstruction techniques (verbatim from items 038/039's tests, keyed by
the manifest's `reconstruction` value):

| `reconstruction` | mode / case | technique | designated rule | expected labels |
|---|---|---|---|---|
| `leave_one_out_offset` | 1 `displace` | fit the spline through **every other** present centroid, measure the target centroid's spacing-aware offset, overwrite the target entry's `offset_mm` in `record["stage3"]["per_label_offsets"]`, feed to `MislabelRule` | `mislabel` | `{22}` |
| `monotonic_true_spatial_order` | 4 `relabel_swap` | fit the spline through the perturbed centroids ordered by **true spatial (axis-0)** position, compute `compute_monotonic_consistency` of the ascending-label sequence, overwrite `record["stage3"]["monotonic_consistency"]["non_monotonic_pairs"]` + set `is_monotonic=False`, feed to `MislabelRule` | `mislabel` | `{21, 22}` |
| `overlap_mask_stack` | 8 `force_overlap` | build a two-channel one-hot stack `[perturbed==target, clean_base==neighbour]`, `detect_overlaps(...)`, wrap as `{"overlaps": [overlap_to_dict(p) …]}`, feed to `OverlapRule` | `overlap` | `{20, 21}` |

### Scope boundary — what this item is **not**

- **Not new corpus cases, operators, rules, extractors, config, or CLI behaviour.**
  It consumes the merged pipeline (`run_qc`, `extract_feature_record`,
  `MislabelRule`, `OverlapRule`, the feature extractors), the item-040 corpus, and
  the item-040 manifest **unchanged**. It edits no operator/rule/extractor/config/
  CLI/`corpus.py`/`io.py` module and adds no `Perturbation` or `Rule`.
- **Not a fix for the reconstructed-record limitation.** It faithfully verifies the
  three modes via the reconstruction path (as item 040 mandates); it does not
  change the pipeline to surface them.
- **Not the golden-file JSON snapshots (item 042).** This item asserts
  verdict/fired-rule/labels; item 042 pins the emitted JSON bytes.
- **Not a re-implementation of item 040's manifest-structure tests** (AC1–AC18 of
  040 already cover schema/loadability/reproducibility). This item asserts
  *pipeline behaviour* over the corpus.

---

## Public interface (the regression surface)

New module `src/segqc/synth/regression.py`. The public predicates each take a
single manifest **case dict** and an optional config (defaulting to
`bundled_default_config()`), so both the parametrised suite and the drift
meta-tests call the *same* comparison logic (DRY — the assertions the suite makes
are exactly the predicates the drift tests break):

```python
def loaded_seg_image(case: dict, corpus_dir: Path = CORPUS_DIR) -> nib.Nifti1Image:
    """Load the case's committed seg fixture via segqc.io.load_case and rebuild a
    Nifti1Image (with an explicit dtype=) suitable for run_qc / reconstruction."""

def pipeline_findings(case, config=None) -> tuple[Finding, ...]:
    """run_qc(loaded_seg_image(case), config).findings."""

def pipeline_verdict_label(case, config=None) -> str:
    """run_qc(...).verdict.overall.label for a case's committed seg fixture."""

def reconstructed_findings(case, config=None) -> list[Finding]:
    """Dispatch on case['reconstruction'] to the matching technique; feed the
    reconstructed record to the designated rule and return its findings.
    Raises ValueError on an unrecognised technique (never silently skips)."""

def designated_findings(case, config=None) -> list[Finding]:
    """Findings whose rule_id ∈ expected_rule_ids, taken from the run_qc path for
    'pipeline' cases and from reconstructed_findings for 'reconstructed_record'
    cases (dispatch on detection)."""

def designated_rule_fired(case, config=None) -> bool:
    """True iff designated_findings(case) is non-empty."""

def offending_labels_match(case, config=None) -> bool:
    """True iff the union of designated_findings labels == set(expected_labels)."""

def pipeline_hides_designated_rule(case, config=None) -> bool:
    """True iff plain run_qc emits NO finding whose rule_id ∈ expected_rule_ids
    (the documented limitation for reconstructed_record cases)."""

def verify_case(case, config=None) -> bool:
    """The whole per-case check, dispatched on detection:
      - pipeline: verdict label == expected_verdict AND (clean → no findings) OR
        (non-clean → designated_rule_fired AND offending_labels_match);
      - reconstructed_record: pipeline_hides_designated_rule AND
        designated_rule_fired AND offending_labels_match."""
```

`RECONSTRUCTIONS: dict[str, Callable]` maps the three technique names to their
handlers; `reconstructed_findings` looks the technique up there and raises on a
miss. The public names are additively re-exported from `segqc.synth.__init__`.

---

## Acceptance Criteria

_One test per criterion. "Loaded seg of a case" means `loaded_seg_image(case)`
(the committed fixture, via `segqc.io.load_case`). "Designated rule" means a
`rule_id ∈ case["expected_rule_ids"]`. Group B/C tests are `@pytest.mark.parametrize`d
over the relevant subset of `load_manifest()["cases"]` (ids == `case_id`), so a new
manifest case is automatically a new invocation._

### A. Manifest-driven parametrisation (coverage auto-extends; nothing skipped)

- [ ] **AC1: Parametrisation is manifest-driven and complete.** The suite builds
      its case parametrisation from `load_manifest()["cases"]`; the set of
      parametrised test ids equals exactly the set of committed `case_id`s and is
      non-empty (so appending a manifest case adds a test invocation with no code
      change).

- [ ] **AC2: Every case routes to exactly one handled path (no silent skip).** For
      every manifest case, `detection ∈ {"pipeline", "reconstructed_record"}`, and
      every `reconstructed_record` case's `reconstruction` is a key of
      `RECONSTRUCTIONS` (one of `leave_one_out_offset`,
      `monotonic_true_spatial_order`, `overlap_mask_stack`); the count of cases the
      pipeline + reconstruction paths together exercise equals the manifest case
      count.

### B. Pipeline-detectable cases run end-to-end (G7 / G2)

- [ ] **AC3: Positive control passes with no flags.** For the `failure_mode == 0`
      `clean_control` case, `run_qc(loaded seg, bundled_default_config())` returns
      `findings == ()` **and** `verdict.overall.label == "pass"` (== its manifest
      `expected_verdict`).

- [ ] **AC4: Pipeline verdict matches the manifest.** For every
      `detection == "pipeline"` case, `pipeline_verdict_label(case) ==
      case["expected_verdict"]`.

- [ ] **AC5: The designated heuristic fires (pipeline).** For every non-clean
      (`failure_mode != 0`) `detection == "pipeline"` case,
      `designated_rule_fired(case)` is `True` (at least one `run_qc` finding has
      `rule_id ∈ expected_rule_ids`).

- [ ] **AC6: The offending labels match the manifest (pipeline).** For every
      non-clean `detection == "pipeline"` case, `offending_labels_match(case)` is
      `True` — the union of `labels` over findings whose `rule_id ∈
      expected_rule_ids` equals `set(case["expected_labels"])` (the case-level
      `mode5_remove_level` case → empty set == `[]`).

### C. Reconstructed-record cases complete the net over modes 1, 4, 8

- [ ] **AC7: Plain pipeline stays clean of the designated rule (reconstructed
      cases).** For every `detection == "reconstructed_record"` case,
      `pipeline_hides_designated_rule(case)` is `True` — `run_qc` on the loaded seg
      emits no finding whose `rule_id ∈ expected_rule_ids` (the documented
      limitation; mirrors item 040 AC9).

- [ ] **AC8: The designated heuristic fires via the reconstruction with the
      expected labels (reconstructed cases).** For every `detection ==
      "reconstructed_record"` case, driving the technique named by
      `case["reconstruction"]` and feeding the reconstructed record to the
      designated rule yields a finding with `rule_id ∈ expected_rule_ids`, and
      `offending_labels_match(case)` is `True` (its labels ==
      `set(expected_labels)`).

### D. Negative controls (the assertions bite) & skip-guard

- [ ] **AC9: Verdict drift is caught.** For a `detection == "pipeline"` case, a copy
      whose `expected_verdict` is changed to a **different** valid label makes the
      verdict comparison fail — `copy["expected_verdict"] !=
      pipeline_verdict_label(case)` (equivalently `verify_case(copy)` is `False`).

- [ ] **AC10: Fired-rule drift is caught.** For a `detection == "pipeline"` case, a
      copy whose `expected_rule_ids` is changed to a rule id that did **not** fire
      makes `designated_rule_fired(copy)` return `False`.

- [ ] **AC11: Offending-label drift is caught.** For a non-clean case, a copy whose
      `expected_labels` is changed to a wrong label set makes
      `offending_labels_match(copy)` return `False`.

- [ ] **AC12: An unknown reconstruction technique fails loudly.**
      `reconstructed_findings(case)` on a case whose `reconstruction` is an
      unrecognised string raises `ValueError` (rather than returning an empty /
      "passed" result), so a future reconstructed case without a handler cannot be
      silently skipped.

## Assumptions  <!-- MANDATORY: what was assumed when the queued one-liner was ambiguous -->

- **The "complete `segqc run` pipeline end-to-end" is exercised via `run_qc(seg_img,
  bundled_default_config())`** — the in-process entry point that the `segqc run`
  CLI composes ("into a single call for the CLI", per its docstring), consistent
  with how items 038/039/040 drive the pipeline. This runs the real
  feature-extraction → rules → verdict path over each committed fixture. Driving the
  CLI as a subprocess (argv/stdout/JSON) is deliberately **not** used here: the
  reconstructed-record path must feed reconstructed records directly to the rules
  (impossible through the CLI), and end-to-end JSON stability is item 042's job. If
  a reviewer wants an additional CLI-subprocess smoke test, it is a mechanical
  additive follow-up.

- **The seg fed to the pipeline is the committed fixture loaded via `segqc.io.
  load_case`**, then rebuilt as a `nib.Nifti1Image(seg.data, seg.affine,
  dtype=seg.data.dtype)` (the **explicit `dtype=` is mandatory** — item 040's
  Decisions log records that `load_case` returns an `int64` label array and nibabel
  5.3.3 hard-errors on `Nifti1Image(int64_array, affine)` without an explicit
  `dtype`; item 040's own test helper `_seg_nifti_from_case` passes
  `dtype=seg.data.dtype` for exactly this reason). Loading from disk (rather than
  rebuilding in memory via `build_corpus()`) is chosen so the suite exercises the
  committed artefact through the Stage 0 loader — the same path `segqc run` takes.

- **THE MATERIAL BRANCH — the suite dispatches on `detection` and does NOT assert
  `run_qc(...).verdict == expected_verdict` for the three `reconstructed_record`
  cases.** Per item 040's Assumptions, modes 1/4/8 are structurally invisible to
  plain `run_qc`; their manifest `expected_verdict` (`flagged-for-review`) is the
  *conceptual* outcome the reconstruction demonstrates, not what `run_qc` returns
  (`pass`). The suite therefore asserts, for these cases, (a) plain `run_qc` hides
  the designated rule (AC7) and (b) the reconstruction fires it with the expected
  labels (AC8) — but never `pipeline_verdict_label == expected_verdict`. Silently
  skipping or weakening these three is explicitly forbidden; AC2 + AC12 guard
  against a future case slipping through unverified. The validator should surface
  this branch at the queue boundary.

- **The reconstruction techniques are reused verbatim from items 038/039's tests**
  (see the technique table in Description), keyed by the manifest's
  `reconstruction` string. `leave_one_out_offset` / `monotonic_true_spatial_order`
  use `MislabelRule`; `overlap_mask_stack` uses `OverlapRule`. For
  `overlap_mask_stack`, the clean **base** neighbour mask is obtained by rebuilding
  `build_clean_spine(**case["base"])` (the same base the operator was applied to),
  exactly as item 038's `_designated_rule_fires` does. Directionality
  (target vs neighbour) for the overlap reconstruction is read from
  `case["perturbation_params"]` (`target_label` / `neighbour_label`); assertions
  use `case["expected_labels"]`.

- **Assertions are keyed on manifest fields only (rule_id + labels), not on rule
  reason strings.** Items 038/039 additionally matched reason prefixes (e.g.
  "Overlapping segments:"); this suite deliberately asserts only `rule_id ∈
  expected_rule_ids` and `labels == set(expected_labels)` so the manifest stays the
  single source of truth and the suite has no per-case hard-coded prose to drift
  against.

- **Offending-label semantics: union equals the expected set.** `offending_labels_
  match` compares the **union** of `labels` over all designated-rule findings to
  `set(expected_labels)`. This is exact for the canonical cases (each designated
  finding carries exactly the expected labels) and remains correct if a future case
  co-fires the designated rule across several labels. The case-level
  `mode5_remove_level` finding is `labels == frozenset()`, so its union is the empty
  set, matching `expected_labels == []`.

- **The harness library lives in `src/segqc/synth/regression.py` (`source_dir`),
  re-exported from `segqc.synth`.** Consistent with item 040's decision to place the
  corpus *generator* in `source_dir` as importable G7 tooling, the regression
  *harness* is its natural sibling (both are synthetic-corpus evaluation tooling;
  the `synth` subpackage already depends on numpy/nibabel/scipy). The pytest module
  `tests/test_041_regression_suite.py` remains the test-writer's. If a reviewer
  prefers the harness as a `tests/`-local helper (to keep the shipped container
  leaner), the move is mechanical and does not change the ACs.

- **Pinned upstream interfaces (hand back if reality diverged):**
  `segqc.synth.corpus.load_manifest()` / `CORPUS_DIR` and the item-040 manifest
  schema (`case_id`, `detection`, `reconstruction`, `perturbation`,
  `perturbation_params`, `base`, `expected_rule_ids`, `expected_labels`,
  `expected_verdict`, `scan_fixture`, `seg_fixture`); `segqc.io.load_case(scan,
  seg) -> Case` with `.seg.data` / `.seg.affine`; `segqc.pipeline.run_qc(seg_img,
  config) -> (CaseResult, dict)` with `CaseResult.findings` (tuple of `Finding` with
  `.rule_id` / `.reason` / `.labels: frozenset`) and `.verdict.overall.label`;
  `segqc.pipeline.extract_feature_record(seg_img, config) -> dict` with
  `record["stage3"]["per_label_offsets"]` (each `{"label", "offset_mm", …}`) and
  `record["stage3"]["monotonic_consistency"]` (`non_monotonic_pairs`,
  `is_monotonic`); `segqc.features.centroids.compute_centroid`,
  `segqc.features.spline.fit_centroid_spline`,
  `segqc.features.spline_offset.compute_spline_offsets(centroids, fit,
  spacing_mm=…) -> [.offset_mm]`, `segqc.features.consistency.
  compute_monotonic_consistency(centroids, fit) -> .non_monotonic_pairs`,
  `segqc.features.overlap.detect_overlaps(mask_stack, labels) -> [.overlap_voxels]`,
  `segqc.feature_report.overlap_to_dict`; `segqc.heuristics.mislabel.MislabelRule`,
  `segqc.heuristics.overlap.OverlapRule` (each `.evaluate(record, config) ->
  [Finding]`); `segqc.config.bundled_default_config`; `segqc.synth.build_clean_spine`.
  If any diverged, the builder/validator hands back.

## Implementation Steps

Intended code path: new `src/segqc/synth/regression.py` + an additive re-export in
`src/segqc/synth/__init__.py`. No edits to any operator/rule/extractor/config/CLI/
`corpus.py`/`io.py` module.

1. **Create `src/segqc/synth/regression.py`** importing `numpy`, `nibabel`,
   `pathlib`; `load_manifest` / `CORPUS_DIR` from `segqc.synth.corpus`; `load_case`
   from `segqc.io`; `run_qc` / `extract_feature_record` from `segqc.pipeline`;
   `bundled_default_config` from `segqc.config`; `build_clean_spine` from
   `segqc.synth.clean_gt`; the feature helpers (`compute_centroid`,
   `fit_centroid_spline`, `compute_spline_offsets`, `compute_monotonic_consistency`,
   `detect_overlaps`, `overlap_to_dict`); and `MislabelRule` / `OverlapRule`. Import
   from submodules to avoid any circular import through `segqc.synth.__init__`.

2. **`loaded_seg_image(case, corpus_dir=CORPUS_DIR)`** — resolve `scan_fixture` /
   `seg_fixture` under `corpus_dir`, `load_case(...)`, and return
   `nib.Nifti1Image(seg.data, seg.affine, dtype=seg.data.dtype)` (explicit dtype).

3. **`pipeline_findings` / `pipeline_verdict_label`** — `run_qc(loaded_seg_image(
   case), config or bundled_default_config())`, returning `.findings` and
   `.verdict.overall.label` respectively.

4. **The three reconstruction handlers** — one function each, mirroring items
   038/039's test helpers exactly:
   - `_recon_leave_one_out_offset(case, config)`: fit spline through every present
     label's centroid except the target (`perturbation_params["target_label"]`),
     measure the target's spacing-aware `offset_mm`, overwrite that label's entry
     in `extract_feature_record(...)["stage3"]["per_label_offsets"]`, return
     `MislabelRule().evaluate(record, config)`.
   - `_recon_monotonic_true_spatial_order(case, config)`: fit spline through the
     perturbed centroids sorted by `centroid_voxel[0]`, `compute_monotonic_
     consistency` of the ascending-label sequence, overwrite `record["stage3"]
     ["monotonic_consistency"]["non_monotonic_pairs"]` (+ `is_monotonic=False`),
     return `MislabelRule().evaluate(record, config)`.
   - `_recon_overlap_mask_stack(case, config)`: rebuild `build_clean_spine(**case
     ["base"])`; `stack = np.stack([perturbed==target, clean==neighbour])`;
     `detect_overlaps(stack, np.array([target, neighbour]))`; build
     `{"overlaps": [overlap_to_dict(p) …]}`; return `OverlapRule().evaluate(record,
     config)`.
   Register them in `RECONSTRUCTIONS = {name: handler}`.

5. **`reconstructed_findings(case, config=None)`** — look up
   `RECONSTRUCTIONS[case["reconstruction"]]`; `raise ValueError(...)` if the key is
   missing (AC12); call the handler.

6. **`designated_findings` / `designated_rule_fired` / `offending_labels_match` /
   `pipeline_hides_designated_rule`** — `designated_findings` dispatches on
   `case["detection"]` (pipeline → `pipeline_findings`; reconstructed →
   `reconstructed_findings`) and filters to `rule_id ∈ set(expected_rule_ids)`;
   the others derive from it as described in the interface block.

7. **`verify_case(case, config=None)`** — dispatch on `detection` and compose the
   predicates (pipeline clean → no findings + verdict; pipeline non-clean → verdict
   + rule + labels; reconstructed → hidden + rule + labels).

8. **Re-export** the public names from `src/segqc/synth/__init__.py` (additive
   import line + `__all__` entries), matching the item-040 `corpus` re-export style.

9. **Do not** edit any pipeline/operator/rule/extractor/config/CLI/`corpus.py`/
   `io.py` module, and do not add corpus cases or change the manifest.

## Testing Strategy

- **Framework:** `pytest`. New module `tests/test_041_regression_suite.py`, in the
  style of `tests/test_040_synthetic_corpus.py` / `tests/test_039_*`
  (`import segqc.synth`; import `load_manifest`, `CORPUS_DIR`, and the
  `regression` predicates; `bundled_default_config`).
- **Manifest-driven parametrisation:** a module-level `_CASES = load_manifest()
  ["cases"]`; Group B/C tests are `@pytest.mark.parametrize("case", <subset>,
  ids=lambda c: c["case_id"])` over the `pipeline` / non-clean-`pipeline` /
  `reconstructed_record` subsets. AC1 asserts the collected ids equal the committed
  `case_id` set.
- **Group A (AC1–AC2):** parametrisation ids == committed case ids and non-empty
  (AC1); `detection` domain + `reconstruction ∈ RECONSTRUCTIONS` for reconstructed
  cases + exercised-count == manifest-count (AC2).
- **Group B (AC3–AC6):** `clean_control` no-findings + `pass` (AC3); per-pipeline
  verdict equality (AC4); per-non-clean-pipeline designated rule fires (AC5); union
  of designated labels == expected (AC6).
- **Group C (AC7–AC8):** per-reconstructed `pipeline_hides_designated_rule` (AC7);
  per-reconstructed reconstruction fires designated rule + label match (AC8).
- **Group D (AC9–AC12):** verdict drift → mismatch (AC9); rule drift →
  `designated_rule_fired` False (AC10); label drift → `offending_labels_match`
  False (AC11); unknown `reconstruction` → `ValueError` (AC12).
- **Adversarial / edge cases:**
  - `verify_case(case)` is deterministic — two calls on the same case return the
    same result (pipeline determinism carried through).
  - The case-level `mode5_remove_level` case (`expected_labels == []`) passes AC6
    without crashing on the empty union.
  - `loaded_seg_image` succeeds for every case (guards the explicit-`dtype` nibabel
    5.3.3 requirement; a bare `Nifti1Image(int64, affine)` would raise).
  - A drift meta-test targeting a **pipeline** case (e.g. `mode7_sequence_break`) so
    AC9–AC11 exercise the fired path, not a no-op.
  - Every `reconstructed_record` case, when its designated rule is filtered out of
    the plain `run_qc` findings, indeed leaves that rule absent (cross-check of AC7
    against AC8's positive reconstruction).

## Dependencies

- **Upstream (all merged ✅):**
  - **Item 040** — `segqc.synth.corpus`: `load_manifest`, `CORPUS_DIR`, and the
    committed corpus (`tests/corpus/manifest.json` + `tests/corpus/fixtures/*.nii.gz`)
    with the `detection` / `reconstruction` discriminators this suite branches on.
    The manifest is the single source of expectations.
  - **Item 039** — `segqc.synth.identity_ordering_alignment` (`displace`,
    `relabel_swap`, `sequence_break`) and, crucially, the **reconstruction
    techniques** its tests established: `leave_one_out_offset` (mode 1) and
    `monotonic_true_spatial_order` (mode 4), both via `MislabelRule`, plus the
    pipeline-detectable mode-7 `sequence` case.
  - **Item 038** — `segqc.synth.coverage_border_overlap` (`remove_level`,
    `crop_at_border`, `force_overlap`): the pipeline mode-5 (`coverage`, case-level)
    and mode-6 (`border`) cases, and the **`overlap_mask_stack`** reconstruction
    (mode 8) via `detect_overlaps` + `OverlapRule` this suite reuses.
  - **Item 037** — `segqc.synth.component_shape` (`fragment`, `inject_islands`): the
    pipeline mode-2 and mode-3 (`fragmentation`) cases.
  - **Item 036** — `segqc.synth.clean_gt.build_clean_spine` (the base rebuilt for
    the `overlap_mask_stack` reconstruction and the mode-0 clean control) and the
    `segqc.synth.perturbation` framework / `FAILURE_MODE_NAMES` behind the manifest.
  - **Item 003** — `segqc.io.load_case` (the Stage 0 loader each fixture is read
    through, exercising the same path as `segqc run`).
  - **Items 034 / 035 / 026** — `segqc.pipeline.run_qc` /
    `extract_feature_record`, `segqc.config.bundled_default_config`,
    `segqc.aggregate.CaseResult`, `segqc.verdict.Severity`/`Verdict`, the
    `Finding`/rule surfaces (`MislabelRule`, `OverlapRule`, `run_rules`) and the
    feature extractors (`compute_centroid`, `fit_centroid_spline`,
    `compute_spline_offsets`, `compute_monotonic_consistency`, `detect_overlaps`,
    `overlap_to_dict`).
- **Downstream (depend on this item):**
  - **Item 042** — golden-file JSON snapshots & determinism harness; may reuse this
    module's per-case seg-loading and the manifest iteration.
- **Not dependencies:** nothing else in queue-004 is parallel with 041 (041 depends
  on 040; 042 depends on 041).

## Decisions & Trade-offs

To be updated during implementation.
