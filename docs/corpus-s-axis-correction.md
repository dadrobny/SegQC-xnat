# Corpus S-axis correction — moved/unmoved record

> **Item:** [143](aide/items/143-correct-the-synthetic-corpus-s-axis-stacking.md)
> **Date:** 2026-09-03 (engine 1.37.0)

`src/segfacet/synth/clean_gt.py::build_clean_spine` used to place ascending
labels at ascending array-axis-2 slots, which — because axis 2 is the
affine-resolved superior-inferior axis (item 116) and ascending label is
head-to-tail (item 093) — made every in-repo synthetic fixture advance
*superiorly*, the opposite of real VerSe input read through `segfacet.io`
(item 131). This item reassigns the label↔slot mapping (label `i` moves to
slot `n - 1 - i`) so the corpus advances caudally instead, without reshaping
the physical spine.

For `clean_control` the per-label centroid S coordinate is now the mirror of
the pre-item values (measured 2026-08-31, item 131): `L1` moved from
`S = 27 mm` to `S = 187 mm`, and `L5` from `S = 187 mm` to `S = 27 mm`.

Every row below is one committed artifact in the required set (the corpus
manifests' fixture paths plus the eight non-corpus artifacts named in the
item spec's Testing Strategy).

| path | compared by | verdict | detail |
|---|---|---|---|
| `tests/corpus/manifest.json` | `python -m segfacet.synth.corpus --out <tmp>` + `assert_matches_committed_artifact` | moved | one field's text changed: `mode8_force_overlap`'s `detail` string records the shift as `-18 voxel(s)` instead of `18 voxel(s)` — the same overhang reassignment, now measured toward the mirrored slot. All other manifest content (case ids, expected verdicts/rule ids/labels, recipe parameters) is unchanged. |
| `tests/corpus/fixtures/base_scan.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | unmoved | the scan is a ramp over `shape[2]` only (`np.arange(shape[2])`), independent of which label occupies which slot — byte-identical to the pre-item fixture. |
| `tests/corpus/fixtures/clean_control_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | label blocks mirrored along S: label 20 (L1) now occupies the slot label 24 (L5) used to occupy, and vice versa (labels 21/23 likewise swap, 22 unchanged at the midpoint) — sha256 changed, voxel counts/shape/affine unchanged (AC3). |
| `tests/corpus/fixtures/mode1_displace_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring as `clean_control`, applied before the `displace` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode2_fragment_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `fragment` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode3_inject_islands_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `inject_islands` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode4_relabel_swap_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `relabel_swap` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode5_remove_level_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `remove_level` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode6_crop_at_border_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `crop_at_border` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode7_sequence_break_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `sequence_break` perturbation — sha256 changed. |
| `tests/corpus/fixtures/mode8_force_overlap_seg.nii.gz` | `python -m segfacet.synth.corpus --out <tmp>` + `read_bytes()` | moved | same slot-mirroring, applied before the `force_overlap` perturbation — sha256 changed, and the overlap-inducing shift now moves toward the opposite neighbour (see the `manifest.json` row's sign flip). |
| `tests/corpus/intensity/manifest.json` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | unmoved | byte-identical — this manifest records recipe parameters and expectations, not measured values, and none of those moved. |
| `tests/corpus/intensity/fixtures/clean_hu_scan.nii.gz` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | moved | the seeded per-label HU texture is painted at fixed voxel positions; since each label now occupies a different S slot, the scan's voxel data (and sha256) changed even though the manifest's recipe did not. |
| `tests/corpus/intensity/fixtures/clean_spine_seg.nii.gz` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | moved | same slot-mirroring as the geometric corpus's `clean_control_seg.nii.gz` — sha256 changed. |
| `tests/corpus/intensity/fixtures/degenerate_uniform_scan.nii.gz` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | moved | per-label texture painted at fixed voxel positions moves with the label reassignment — sha256 changed. |
| `tests/corpus/intensity/fixtures/implausible_metal_scan.nii.gz` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | moved | per-label texture painted at fixed voxel positions moves with the label reassignment — sha256 changed. |
| `tests/corpus/intensity/fixtures/implausible_soft_tissue_scan.nii.gz` | `python -m segfacet.synth.intensity --out <tmp>` + `read_bytes()` | moved | per-label texture painted at fixed voxel positions moves with the label reassignment — sha256 changed. |
| `tests/corpus/094_pre_migration_snapshot.json` | throwaway re-capture script (spec Implementation Steps step 5, mirrors `test_094`'s own reader) + `read_bytes()` diff | moved | 14 of 15 entries' `data_sha256` changed (every corpus/intensity segmentation fixture and the intensity scans, which all move with the label reassignment); the 15th entry (`corpus/fixtures/base_scan.nii.gz`) is unchanged, consistent with that fixture's own `unmoved` row above. Shape/dtype/spacing/affine are unchanged for all 15 entries — only voxel content (and therefore its digest) moves. |
| `src/segfacet/reference/reference_default.json` | `build_and_write_default` into `<tmp>` + `assert_matches_committed_artifact` | moved | per-label `spline_offset_mm` distribution statistics (`min`/`max`/`mean`/`std`/percentiles) shift by floating-point noise at the ~1e-9 relative scale (e.g. one level's `mean` moved from `0.11599938990000808` to `0.11599938990000586`) — within `assert_matches_committed_artifact`'s numeric tolerance, the same order of magnitude as the per-case `offset_mm` noise measured directly against `mode5_remove_level` (all differences < 1e-9 absolute). No other block of the artifact moved. |
| `src/segfacet/reference/reference_verse_v1.json` | n/a — no synthetic input feeds this artifact | unmoved | built from the real VerSe19 cohort (`tests/test_128_reference_verse_v1_integrity.py`'s pinned sha256), which no synthetic corpus or `build_clean_spine` output feeds — the expected result for a real-cohort artifact, not an omission. |
| `docs/aide/feature_catalogue.generated.json` | `segfacet.catalogue.main` into `<tmp>` + `assert_matches_committed_artifact` | moved | the observed-range column's corpus `minimum` for two entries moved by 1 in the last digit (`7.67114e-08` -> `7.67113e-08`) — the same floating-point noise as the reference artifact's spline-offset statistics, since both are computed from `iter_driver_records()` / the corrected corpus. |
| `docs/aide/feature_catalogue.generated.md` | `segfacet.catalogue.main` into `<tmp>` + `read_bytes()` | moved | the rendered form of the JSON artifact's moved cells (same two `minimum` values, rendered to 6 significant figures). |
| `docs/aide/traceability_matrix.generated.json` | `python -m segfacet.traceability` into `<tmp>` + `assert_matches_committed_artifact` | unmoved | byte-identical — the matrix records which features each rule reads and per-case firing-set structure, none of which moved (AC9: no rule's firing set moved). |
| `docs/aide/traceability_matrix.generated.md` | `python -m segfacet.traceability` into `<tmp>` + `read_bytes()` | unmoved | byte-identical, the rendered form of the unmoved JSON artifact. |
| `docs/aide/golden_evidence.generated.json` | `python -m segfacet.golden_evidence` into `<tmp>` + `assert_matches_committed_artifact` | unmoved | byte-identical — this artifact records per-case leaf-path *counts*, not measured values, and no case's leaf-path set moved. |

## Round-2 reconciled tests (2026-09-03)

The item's original "existing tests to reconcile" sweep (spec Decisions log)
missed or mismeasured three hardcoded literal tables — all holding a *signed
component* of a curvature/traversal quantity, which is not protected by item
131/132's direction-normalisation invariants the way the corresponding
normalised quantity is. Values below are the round-2 measured corrections;
see the item spec's Decisions log for the full explanation.

| test | table | what moved |
|---|---|---|
| `tests/test_121_tangent_orientation.py` | AC5 `expected` (`coronal_deg`, `clean_control`) | `[8.1644, 4.0746, 0.0, -4.0746, -8.1644]` → `[-8.1644, -4.0746, 0.0, 4.0746, 8.1644]` |
| `tests/test_131_tangent_direction_normalisation.py` | `_PRE_ITEM_OTHER_CURVATURE_FIELDS[*]['coronal_tangent_angles_deg']` / `['sagittal_tangent_angles_deg']` | every one of the 9 cases' signed per-level component arrays sign-flipped element-wise (e.g. `clean_control` coronal `[8.165203, 4.072969, 0.0, -4.072969, -8.165203]` → `[-8.165203, -4.072969, 0.0, 4.072969, 8.165203]`); `total_curvature_deg`/`coronal_curvature_deg`/`sagittal_curvature_deg`/`curvature_plane` unmoved |
| `tests/test_132_monotonicity_against_traversal_order.py` | `_PRE_ITEM_U_VALUES['mode6_crop_at_border']` | middle entry `0.500000024` → `0.499999976` (~4.77e-8 shift, outside `abs=1e-9`); other four entries and every other case's table unmoved |
