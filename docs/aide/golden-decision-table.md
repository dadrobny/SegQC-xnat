# Golden-file decision table — Stage 19 (item 105)

This document is the deliverable the roadmap's Stage 19 calls "the golden
decision table": one row per committed exact-match fixture under `tests/`
(Section 1), one row per adjacent exact-match artifact that lives outside
`tests/` but would make this table misleading if omitted (Section 2), and a
short narrative for the in-module frozen snapshots that are not files at all
(Section 3). Each row states what the fixture asserts today, which tests
assert it, the measured evidence behind that assertion where one exists, and
a `keep` or `retire` disposition.

**Who decides, and where the decision is recorded.** The dispositions below
were populated as a mechanical draft from the survey performed for this item
(2026-07-27), then reviewed and decided row by row by the human maintainer
(2026-07-28) — every one of the 36 rows across both sections was presented
individually, with two overturned from their drafted disposition (see
Section 1's `tests/golden/016_features_report.json` and
`022_stage3_report.json`, both moved from the draft's `keep` to `retire`) and
the rest confirmed as drafted. The record of that review is `progress.md`'s
Stage 19 acceptance list, third box — the one stating that the golden
decision table is complete and has the human reviewer's approval attached —
and nothing else. This document carries no approval field of its own; see the
"Not about byte reproducibility" section's neighbour, `## Divergences...`,
for where a `keep` call is explained, and `progress.md` for whether that box
has actually been ratified.

**Stage 19 decides, Stage 21 executes.** This item does not delete, move or
regenerate any fixture, and does not edit any test that consumes one — acting
on a `retire` disposition recorded here is Stage 21's deliverable
(`roadmap.md:829`, "Act on Stage 19's golden decision"). Nothing in this
document should be read as having already happened.

**Evidence re-measured 2026-07-28, after this table's own sign-off.** Item
106's separate per-*feature* steering review (distinct from this table's
per-*golden* review — see `progress.md`'s Stage-19 note on the two) recorded
real `retune`/`retire` judgments in `src/segfacet/feature_docs.py`'s
`STATUS_OVERRIDES`, which changes what `segfacet.catalogue.build_catalogue()`
reports as `unwired` (a `retune`/`retire`-overridden path is no longer
`unwired` by definition). Since the Group-A evidence cells below are computed
live from that function (item 105 AC7 — never transcribed), their values
necessarily moved with it: the nine corpus goldens' unwired-leaf-path evidence
fell from `34/67` (measured at this table's original authoring) to `0/67`
(after item 106's steering review). **This does not weaken the retire case**
— if anything the
opposite: the same 41-of-67 paths that were `unwired` are now `retune`/
`retire`, meaning the goldens pin byte-exact values for fields whose
computation is now flagged to change, not merely fields nothing reads. No
`disposition`, `rationale`, or `replacement guarantee` cell was touched by
this re-measurement — only the numeric evidence values, which this table's
own AC7 test recomputes live by design specifically so they cannot go stale
silently.

**Evidence re-measured again 2026-08-14 (item 110).** Item 110 wired the
previously-unrealised `segfacet.features.neighbourhood` module into
`extract_feature_record` as a new, deliberately `unwired`
`stage3.per_label_neighbourhood[]` block (17 new leaf paths per case;
`status == "unwired"` since no rule consumes it), and regenerated all nine
committed corpus goldens to include it. Both `M` (total leaf paths) and `N`
(unwired leaf paths) in the nine Group-A evidence cells below therefore moved
again, purely mechanically, from `0/67` to `17/84` — 17 more total paths (the
new block) and 17 more unwired paths (all of them, since the block is
consumed by no rule). No `disposition`, `rationale`, or `replacement
guarantee` cell changed; this table's own AC7 test recomputed the new values
live against the regenerated goldens and catalogue, the same mechanism that
caught the item 106 drift above.

**"Asserted by" cells reconciled 2026-08-12 (item 107).** Item 107 deleted
`tests/test_099_per_mode_metrics.py::test_ac25_committed_goldens_byte_identical_to_pre_099_state`
as an authorised `_PRE_099_*` scope-fence removal (see that item's Decisions
log and `insights.md`'s item-106-precedent entries). All nine Group-A rows in
Section 1 named that test in their "asserted by" column, so its deletion left
a dangling reference — the same class of collision item 106 hit and fixed
directly. Fixed the same way: the nine "asserted by" cells no longer name the
deleted test; each row's remaining "asserted by" tests (test_042, test_089,
test_090, test_094, test_098) already cover what that fence covered
(intra-run determinism, schema validity, fresh-vs-committed comparison — see
the "Not about byte reproducibility" section below), so no replacement
assertion was needed. No `disposition`, `rationale`, or `replacement
guarantee` cell was touched by this reconciliation — only the nine stale
"asserted by" cells.

**Evidence re-measured again 2026-08-27 (item 122).** Item 122 added five new
leaf paths under `stage3.curvature` (a signed-curvature feature), consumed by
no rule, and regenerated all nine committed corpus goldens to include them.
Both `M` (total leaf paths) and `N` (unwired leaf paths) in the nine Group-A
evidence cells below therefore moved again, purely mechanically, from
`17/84` to `22/89` — 5 more total paths (the new leaves) and 5 more unwired
paths (all of them, since none is consumed by any rule). No `disposition`,
`rationale`, or `replacement guarantee` cell changed; this table's own AC7
test recomputed the new values live against the regenerated goldens and
catalogue, the same mechanism that caught the item 106 and item 110 drift
above.

**Evidence re-measured again 2026-08-29 (item 121).** Item 121 joined
`stage3.per_label_offsets[].closest_u`'s closest-point machinery with the
curve tangent already evaluated for `stage3.curvature`, adding four new leaf
paths (`spline_closest_u`, `spline_tangent[]`, `spline_tangent_coronal_deg`,
`spline_tangent_sagittal_deg`) inside every `stage3.per_label_orientations[]`
entry — a per-vertebra orientation proxy that varies across levels where the
`principal_axis` PCA feature in the same block is measured constant, or
within `0.996` of the left-right axis, on every committed corpus vertebra.
Consumed by no rule, and regenerated all nine committed corpus goldens to
include them. Both `M` (total leaf paths) and `N` (unwired leaf paths) in the
nine Group-A evidence cells below therefore moved again, purely mechanically,
from `22/89` to `26/93` — 4 more total paths (the new leaves) and 4 more
unwired paths (all of them, since none is consumed by any rule). No
`disposition`, `rationale`, or `replacement guarantee` cell changed; this
table's own AC7 test recomputed the new values live against the regenerated
goldens and catalogue, the same mechanism that caught the item 106, item 110
and item 122 drift above.

**One row added by human decision 2026-08-28 (item 119).** Every amendment
above this line is mechanical — a recomputed evidence number, a dangling test
reference — and moves no judgement column. This one is not: it adds a
thirtieth fixture to Section 1 and assigns it a `keep` disposition, so it was
decided by the human maintainer rather than derived. The fixture is
`tests/corpus/119_pre_119_digests.json`, holding two sha256 digests that pin
item 119's blast radius (`src/segfacet/pipeline.py` unchanged, the feature
catalogue's leaf-path set unchanged). It exists because
`tests/test_115_stage26_validation.py::test_ac8_no_hardcoded_literal_fence_remains`
permits exactly one hardcoded-literal digest fence repo-wide, so the two
digests had to live outside the test module's own source — the same external
storage pattern as `tests/corpus/094_pre_migration_snapshot.json`, already a
`keep` row below. **This row is expected to be deleted, not retired.** Both
digests are boundary fences scoped to item 119, and item 120's leave-one-out
promotion edits `pipeline.py` by design, which retires the first assertion and
with it the fixture's reason to exist. When that happens the fixture is
deleted, this row goes with it, and Section 1 returns to 29 — the both-way
completeness check in `tests/test_105_golden_decision_table.py` enforces that
the document and the tree move together in either direction.

## Section 1 — Committed test fixtures

| fixture | what it asserts today | asserted by | evidence | disposition | replacement guarantee |
|---|---|---|---|---|---|
| tests/corpus/golden/clean_control.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block — all 67 schema-level leaf paths) for the clean_control corpus case, compared fresh-vs-committed within `reports_close` numeric tolerance. | tests/test_042_golden_determinism.py (AC6 one-golden-per-case, AC7 schema validity, AC8 stem-to-case_id, AC9 fresh-vs-committed, AC13 regeneration-vs-committed, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14 components block, AC15 test_ac15_golden_verdict_and_findings_unchanged, AC16 write_goldens determinism) | 26/93 leaf paths unwired | retire | (i) intra-run determinism survives independently via test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) schema validity moves to validating a freshly built report (`build_report_for_case` output) against report_schema_v0.json, re-pointing test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates; (iii) the load-bearing "verdict/findings unchanged by refactor X" use moves to a narrow verdict+findings expectation of the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS shape, which pins no feature values and so survives a feature retune; (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet replace the corpus-snapshot role outright. Not to be regenerated against the new corpus per roadmap.md's Stage 21 deliverable. |
| tests/corpus/golden/mode1_displace.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode1_displace corpus case, compared fresh-vs-committed within `reports_close` tolerance. test_042's AC16 pins this case as pipeline-blind (`verdict == "pass"`, no designated rule fires), so its snapshot content is the documented Stage-20 reachability hole. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, AC16 pipeline-blind, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism cover determinism; (ii) schema validity re-points at a freshly built report via test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates; (iii) verdict/findings unchanged moves to the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS shape; (iv) Stage 21's real-GT corpus. The pipeline-blind status strengthens the retire case specifically for this row — its pinned content includes no designated-rule finding to begin with. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode2_fragment.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode2_fragment corpus case, compared fresh-vs-committed within `reports_close` tolerance. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode3_inject_islands.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode3_inject_islands corpus case, compared fresh-vs-committed within `reports_close` tolerance. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape (this case is imported by test_102_stage18_validation.py); (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode4_relabel_swap.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode4_relabel_swap corpus case, compared fresh-vs-committed within `reports_close` tolerance. test_042's AC16 pins this case as pipeline-blind (`verdict == "pass"`, no designated rule fires), so its snapshot content is the documented Stage-20 reachability hole. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, AC16 pipeline-blind, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus. The pipeline-blind status strengthens the retire case specifically for this row. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode5_remove_level.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode5_remove_level corpus case, compared fresh-vs-committed within `reports_close` tolerance. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, plus 3 adversarial tests, including the empty-labels canonicalisation adversarial case), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode6_crop_at_border.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode6_crop_at_border corpus case, compared fresh-vs-committed within `reports_close` tolerance. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet, which is also where Stage 20's recorded mode-6 specificity shortfall gets resolved. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode7_sequence_break.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode7_sequence_break corpus case, compared fresh-vs-committed within `reports_close` tolerance. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus plus Stage 20's specificity ratchet. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/golden/mode8_force_overlap.json | The full `segfacet run` JSON report (verdict, findings, and the entire features block) for the mode8_force_overlap corpus case, compared fresh-vs-committed within `reports_close` tolerance. test_042's AC16 pins this case as pipeline-blind (`verdict == "pass"`, no designated rule fires), so its snapshot content is the documented Stage-20 reachability hole. | tests/test_042_golden_determinism.py (AC6, AC7, AC8, AC9, AC13, AC16 pipeline-blind, plus 3 adversarial tests), tests/test_089_fov_aware_coverage_border.py::test_ac16_committed_corpus_coverage_and_border_findings_unchanged, tests/test_090_reference_derived_defaults.py::test_ac15_all_committed_goldens_still_check_true, tests/test_094_tptbox_image_layer.py::test_ac7_report_matches_committed_golden_within_tolerance, tests/test_098_stray_components.py (AC14, AC15, AC16) | 26/93 leaf paths unwired | retire | Same four replacements as clean_control: (i) test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical and test_ac12_main_regenerates_matching_goldens plus test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism; (ii) test_042_golden_determinism.py::test_ac7_every_committed_golden_is_valid_json_and_validates re-pointed at a freshly built report; (iii) the _PRE_098_GOLDEN_VERDICT_AND_FINDINGS narrow shape; (iv) Stage 21's real-GT corpus. The pipeline-blind status strengthens the retire case specifically for this row. Not to be regenerated against the new corpus per Stage 21. |
| tests/corpus/manifest.json | The Stage-5 synthetic corpus index (case ids, seg fixture paths, expected mode metadata) is byte-identical to a fresh regeneration, checked both regenerated-vs-committed and regenerated-twice for internal reproducibility. | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/base_scan.nii.gz | The clean base scan volume used to derive every corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/clean_control_seg.nii.gz | The clean_control corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode1_displace_seg.nii.gz | The mode1_displace corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode2_fragment_seg.nii.gz | The mode2_fragment corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode3_inject_islands_seg.nii.gz | The mode3_inject_islands corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz | The mode4_relabel_swap corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode5_remove_level_seg.nii.gz | The mode5_remove_level corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode6_crop_at_border_seg.nii.gz | The mode6_crop_at_border corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode7_sequence_break_seg.nii.gz | The mode7_sequence_break corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_040_synthetic_corpus.py | n/a | keep | — |
| tests/corpus/fixtures/mode8_force_overlap_seg.nii.gz | The mode8_force_overlap corpus segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice), and is also read by test_094's AC3 loader-invariance snapshot. | tests/test_040_synthetic_corpus.py, tests/test_094_tptbox_image_layer.py | n/a | keep | — |
| tests/corpus/intensity/manifest.json | The Stage-8 intensity corpus index (case ids, scan/seg fixture paths, expected finding metadata) is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/intensity/fixtures/clean_hu_scan.nii.gz | The clean-HU intensity fixture scan is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/intensity/fixtures/clean_spine_seg.nii.gz | The intensity corpus's shared clean spine segmentation is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/intensity/fixtures/degenerate_uniform_scan.nii.gz | The degenerate uniform-HU intensity fixture scan is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/intensity/fixtures/implausible_metal_scan.nii.gz | The implausible metal-HU intensity fixture scan is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/intensity/fixtures/implausible_soft_tissue_scan.nii.gz | The implausible soft-tissue-HU intensity fixture scan is byte-identical to a fresh regeneration (regenerated-vs-committed and regenerated-twice). | tests/test_058_intensity_fixtures.py | n/a | keep | — |
| tests/corpus/094_pre_migration_snapshot.json | Per corpus fixture, `{shape, dtype, sha256(data.tobytes()), spacing, affine}` as produced by the pre-TPTBox `io.load_volume`, compared against the same quantities recomputed through the post-migration loader. | tests/test_094_tptbox_image_layer.py | n/a | keep | — |
| tests/corpus/119_pre_119_digests.json | One sha256 digest captured while item 119's branch still held the pre-119 tree — the sorted set of leaf `path` values in the committed `docs/aide/feature_catalogue.generated.json` — compared against the same quantity recomputed at test time. The fixture's companion digest (of `src/segfacet/pipeline.py`'s bytes) and its assertion, `test_ac22_pipeline_is_byte_identical_to_pre_119`, were retired by item 120 exactly as this row predicted: item 120 deliberately edits `pipeline.py` (the leave-one-out call-site swap), which is the event this row named as ending that fence's life, so the `pipeline_sha256` key was dropped from the fixture and the test deleted. The remaining `catalogue_leaf_path_set_sha256` digest still backs its own AC. | tests/test_119_curve_formulation.py::test_ac27_catalogue_leaf_path_set_unchanged_from_pre_119 | n/a | keep | — |
| tests/golden/016_features_report.json | `serialize_report_json(...)`'s output for the Stage-2/3 feature report is compared, as text (`read_text`, universal-newline translation applies), against this committed file. | tests/test_016_features_json.py::test_ac5_golden_snapshot | n/a | retire | Overturned from the initial "keep" draft by the human reviewer (2026-07-28): although named a "formatting golden," this fixture is built from a real computed `features` block (`_features_for_case`), so a legitimate feature retune regenerates it too — the same reasoning Group A is retired for. Reviewer's stated principle: computed-feature correctness and report-*format* correctness should be checked by two separate, purpose-built fixtures, not conflated in one whole-record snapshot. Replacement: (i) intra-run determinism is already independent — `test_ac5_deterministic_repeated_serialisation` — and is unaffected by this retirement; (ii) report-format guarantees (key ordering, key set, float formatting) move to a small, hand-constructed, feature-value-free fixture built specifically to exercise `serialize_report_json`'s formatting, so it is immune to feature retunes; (iii) computed-feature correctness for the Stage-2/3 blocks stays covered by this module's many direct value-level assertions (AC1-AC4, AC6-AC8), which do not depend on the golden file at all. Acting on this (building the replacement fixture, deleting this file) is Stage 21's job, not this item's. |
| tests/golden/022_stage3_report.json | `serialize_report_json(...)`'s output for the Stage-3 report is compared, as text (`read_text`, universal-newline translation applies), against this committed file — but the consuming test writes the golden and skips if the file is absent, so deletion currently makes the check pass rather than fail (a logged, unfixed defect; see insights.md). | tests/test_022_stage3_serialisation.py::test_ac8_golden_snapshot | n/a | retire | Same reviewer principle and disposition as `016_features_report.json` (2026-07-28): built from a real computed `stage3` block, so retired on the same "separate feature-correctness from format-correctness" grounds. Replacement: (i) intra-run determinism is already independent — `test_ac8_determinism_two_calls_equal` and `test_ac8_determinism_report_level` — and is unaffected; (ii) report-format guarantees move to the same kind of dedicated, feature-value-free formatting fixture as `016_features_report.json`'s replacement, ideally shared between the two rather than duplicated; (iii) computed Stage-3 correctness stays covered by this module's extensive direct value-level assertions (AC1-AC7, AC9-AC10), independent of the golden file. **Building the replacement must also fix the write-and-skip defect** (`test_ac8_golden_snapshot` self-heals instead of failing on a missing file, logged in insights.md) — the new fixture should not inherit that bug. Acting on this is Stage 21's job, not this item's. |

## Section 2 — Adjacent exact-match artifacts (outside tests/)

| fixture | what it asserts today | asserted by | evidence | disposition | replacement guarantee |
|---|---|---|---|---|---|
| src/segfacet/reference/reference_default.json | The shipped default reference-distribution artifact is compared, regenerated-vs-committed within `reports_close` tolerance, and its content is also exercised directly as reference data. | tests/test_045_reference_artifact.py, tests/test_081_reference_morphology.py, tests/test_093_tptbox_label_convention.py | n/a | keep | — |
| src/segfacet/reference/reference_verse_v1.json | The VerSe-derived reference-distribution artifact built from mounted ground truth is sha256-pinned; it is not regenerable in CI, so the pin is the only thing standing between it and silent corruption. | tests/test_098_stray_components.py::test_ac18_reference_verse_v1_bytes_unchanged | n/a | keep | — |
| src/segfacet/report_schema_v0.json | The v0 per-case report JSON schema, validated against by every committed golden and every fresh report throughout the suite. | tests/test_042_golden_determinism.py | n/a | keep | — |
| src/segfacet/eval/eval_report_schema_v0.json | The Stage-7 `segfacet evaluate` cohort report JSON schema. | tests/test_099_per_mode_metrics.py | n/a | keep | — |
| src/segfacet/eval/per_mode_comparison_schema_v0.json | The Stage-18 per-mode run-vs-run comparison report JSON schema. | tests/test_101_per_mode_cohort.py, tests/test_101_compare_runs_cli.py, tests/test_102_stage18_validation.py | n/a | keep | — |
| docs/aide/feature_catalogue.generated.json | Item 103's generated feature catalogue (machine-readable), compared byte-identical to a fresh regeneration. | tests/test_103_feature_catalogue.py, tests/test_104_feature_catalogue_drift.py | n/a | keep | — |
| docs/aide/feature_catalogue.generated.md | Item 103's generated feature catalogue (human-readable rendering), compared byte-identical to a fresh regeneration. | tests/test_103_feature_catalogue.py | n/a | keep | — |

## Section 3 — In-module frozen snapshots

Not every committed exact-match expectation is a file. Two constants in
`tests/test_098_stray_components.py` are hand-set frozen snapshots that
several later modules treat as pins:

- **`_PRE_098_HAND_SET_FRAGMENTATION_FINDINGS`** — the pre-098 hand-constructed
  expected fragmentation findings per corpus case, used by
  `test_098_stray_components.py` itself as a before/after check that item 098's
  stray-component rework did not change fragmentation's own findings.
- **`_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`** — the pre-098 committed goldens'
  verdict and findings (not features) per corpus case, used by
  `test_098_stray_components.py::test_ac15_golden_verdict_and_findings_unchanged`
  and, critically, **imported by `tests/test_102_stage18_validation.py`**,
  which relies on it as a narrow, feature-value-free expectation. This is the
  exact shape named in Section 1's `replacement guarantee` cells as what
  survives a Group-A `retire`.

Disposition for both: **keep** — they are cheap, narrow, and (for
`_PRE_098_GOLDEN_VERDICT_AND_FINDINGS`) already load-bearing for a downstream
module.

Beyond those two, tests 093/098/099/100/101/102 each carry one or more
`_PRE_NNN_*` sha256 scope-fence constants (e.g.
`_PRE_099_HASHES`/`_PRE_100_HASHES`/`_PRE_101_HASHES`/`_PRE_105_*_HASH`),
each pinning a committed file or tree byte-identical to its state before that
item's own changes, so a later item cannot silently touch what its spec
declared out of scope. Blanket disposition: **keep** — they are cheap and
targeted, one per item rather than one per file, and they are the mechanism
that makes AC14 of this very item checkable. `insights.md` (item 101, logged
2026-07-27) records the open gap this table does not resolve: there is no
documented convention yet for updating a superseded item's pin when a later
item is legitimately authorised to edit the same shared file — leaving that
open here rather than inventing a convention out of scope for this item.

## Not about byte reproducibility

A `retire` disposition recorded above does **not** weaken this repo's
intra-run determinism guarantee. `src/segfacet/synth/golden.py` is what
produces every one of the nine Group-A goldens (`write_goldens`), and the
property that two successive runs of the same pipeline over the same input
produce byte-identical output is asserted independently of whether any
committed golden survives Stage 21. The following three assertions carry that
guarantee regardless of what this table's Group-A rows decide:

- `tests/test_042_golden_determinism.py::test_ac4_two_successive_runs_are_byte_identical`
- `tests/test_042_golden_determinism.py::test_ac12_main_regenerates_matching_goldens`
- `tests/test_098_stray_components.py::test_ac16_write_goldens_intra_run_determinism`

Retiring a whole-record snapshot removes a *committed reference point*, not
the determinism check itself — `dest1 == dest2` never depended on a committed
file existing.

## Divergences from the roadmap's working assumption

The roadmap's working assumption (`roadmap.md:794-797`) is "retire most" of
the committed goldens. Every row above whose disposition is `keep` is
therefore a divergence from that blanket assumption and is itemised here,
with the reason it earns its keep rather than following Group A:

- `tests/corpus/manifest.json` — an input, not a report snapshot; its
  assertion is generator reproducibility, which a feature retune cannot
  invalidate, and the roadmap's Stage 21 rung table retains rung-1 fixtures
  for fast unit tests.
- `tests/corpus/fixtures/base_scan.nii.gz` — same reasoning as the manifest:
  an input fixture, not a computed-feature snapshot.
- `tests/corpus/fixtures/clean_control_seg.nii.gz` — input fixture, not a
  report snapshot.
- `tests/corpus/fixtures/mode1_displace_seg.nii.gz` — input fixture, not a
  report snapshot.
- `tests/corpus/fixtures/mode2_fragment_seg.nii.gz` — input fixture, not a
  report snapshot.
- `tests/corpus/fixtures/mode3_inject_islands_seg.nii.gz` — input fixture,
  not a report snapshot.
- `tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz` — input fixture, not
  a report snapshot.
- `tests/corpus/fixtures/mode5_remove_level_seg.nii.gz` — input fixture, not
  a report snapshot.
- `tests/corpus/fixtures/mode6_crop_at_border_seg.nii.gz` — input fixture,
  not a report snapshot.
- `tests/corpus/fixtures/mode7_sequence_break_seg.nii.gz` — input fixture,
  not a report snapshot.
- `tests/corpus/fixtures/mode8_force_overlap_seg.nii.gz` — input fixture, not
  a report snapshot; also underlies test_094's loader-invariance snapshot.
- `tests/corpus/intensity/manifest.json` — an input index, not a report
  snapshot; generator reproducibility only.
- `tests/corpus/intensity/fixtures/clean_hu_scan.nii.gz` — input fixture, not
  a report snapshot.
- `tests/corpus/intensity/fixtures/clean_spine_seg.nii.gz` — input fixture,
  not a report snapshot.
- `tests/corpus/intensity/fixtures/degenerate_uniform_scan.nii.gz` — input
  fixture, not a report snapshot.
- `tests/corpus/intensity/fixtures/implausible_metal_scan.nii.gz` — input
  fixture, not a report snapshot.
- `tests/corpus/intensity/fixtures/implausible_soft_tissue_scan.nii.gz` —
  input fixture, not a report snapshot.
- `tests/corpus/094_pre_migration_snapshot.json` — it snapshots *loaded
  arrays* (shape/dtype/sha256/spacing/affine), not computed features, so it
  is invariant under every retune this stage or Stage 20 authorises, and it
  remains a live ratchet on any future `io.load_volume` change rather than a
  discharged one-shot migration fence.
- `tests/corpus/119_pre_119_digests.json` — a blast-radius fence, not a
  computed-feature snapshot: it pins that item 119 changed neither
  `src/segfacet/pipeline.py` nor the feature catalogue's set of leaf paths, so
  no feature retune can invalidate it. It diverges from Group A in the
  opposite direction to `094_pre_migration_snapshot.json` — that one earns
  `keep` for being a live ratchet, whereas this one is a discharged one-shot
  fence and earns `keep` only for as long as its item's boundary is still
  worth holding. Expected to be **deleted** rather than retired when item 120
  edits `pipeline.py`, which is the event that ends the first of its two
  assertions.
- `src/segfacet/reference/reference_default.json` — shipped default data with
  a live regenerated-vs-committed guarantee, not a corpus-case snapshot.
- `src/segfacet/reference/reference_verse_v1.json` — unregenerable in CI (built
  from mounted VerSe ground truth); its sha256 pin is the only thing
  standing between it and silent corruption, so it is not a candidate for
  retirement by this stage's reasoning at all.
- `src/segfacet/report_schema_v0.json` — a validation contract, not a
  report snapshot; the roadmap names schemas as survivors.
- `src/segfacet/eval/eval_report_schema_v0.json` — a validation contract, not
  a report snapshot.
- `src/segfacet/eval/per_mode_comparison_schema_v0.json` — a validation
  contract, not a report snapshot.
- `docs/aide/feature_catalogue.generated.json` — generated-document
  determinism, structurally like the corpus manifest, not a whole-record
  snapshot.
- `docs/aide/feature_catalogue.generated.md` — same reasoning as the
  generated JSON catalogue: generated-document determinism, not a
  whole-record snapshot.
