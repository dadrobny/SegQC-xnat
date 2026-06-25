# VerSe19 Training Dataset Reference

> **Status:** Living reference — extend as more is learned.
> **Source:** `dataset-verse19training.zip` from `https://s3.bonescreen.de/public/VerSe-complete/`
> **DOI:** 10.17605/OSF.IO/NQJYW
> **Last updated:** 2026-06-25

---

## Git / versioning policy

**Data files are not committed to this repo.**

The `.gitignore` already excludes `dataset-verse19training/` at the root level. This is correct and intentional:

- NIfTI CT volumes are large binary blobs (~6.6 GB total); VCS is the wrong storage layer.
- The directory *structure* is also not committed (no `.gitkeep` files). Committing empty directories would imply a guaranteed local path contract that does not hold on machines where data has not been downloaded. Instead, this document is the contract.

**To reproduce:** download and unzip the archive into the project root so the path `dataset-verse19training/dataset-verse19training/` exists. No path configuration is required; code should reference the dataset relative to this expected root or via a configurable path variable.

---

## Directory structure

```
dataset-verse19training/                      ← gitignored (zip extraction wrapper)
└── dataset-verse19training/                  ← actual dataset root
    ├── rawdata/
    │   └── sub-verseNNN/
    │       ├── sub-verseNNN_ct.nii.gz        ← CT scan (NIfTI, gzipped)
    │       └── sub-verseNNN_ct.json          ← scan metadata (scanner, KVP)
    └── derivatives/
        └── sub-verseNNN/
            ├── sub-verseNNN_seg-vert_msk.nii.gz    ← vertebra segmentation mask (NIfTI)
            ├── sub-verseNNN_seg-subreg_ctd.json    ← vertebra centroid coordinates (JSON)
            └── sub-verseNNN_seg-vert_snp.png       ← 2-D preview snapshot (PNG)
```

For split subjects (400-series), files include a `_split-verseMMM` infix:

```
rawdata/sub-verseNNN/sub-verseNNN_split-verseMMM_ct.nii.gz
derivatives/sub-verseNNN/sub-verseNNN_split-verseMMM_seg-vert_msk.nii.gz
...
```

---

## Naming convention (BIDS-inspired)

| Token | Meaning | Example |
|---|---|---|
| `sub-verseNNN` | Subject ID (NNN = 3-digit zero-padded integer) | `sub-verse004` |
| `_split-verseMMM` | Split FOV infix for 400-series multi-volume subjects | `_split-verse201` |
| `_ct` | Raw CT image modality | `_ct.nii.gz` |
| `_seg-vert` | Vertebra-level segmentation | `_seg-vert_msk.nii.gz` |
| `_seg-subreg` | Sub-region / centroid data | `_seg-subreg_ctd.json` |
| `_msk` | Binary or labelled mask volume | `_seg-vert_msk.nii.gz` |
| `_ctd` | Centroid coordinates file | `_seg-subreg_ctd.json` |
| `_snp` | 2-D snapshot / preview | `_seg-vert_snp.png` |

---

## Counts and size

| Metric | Value |
|---|---|
| Subject folders | 67 (55 standard + 12 split-parent) |
| Scan instances (CT volumes) | **80** |
| Total files | 400 (80 × 5 files per scan) |
| Total disk size | ~6.6 GB |

**Subject ID ranges:**

- Standard (single-FOV): sub-verse004 – sub-verse257 (non-contiguous; IDs are not sequential).
- Split-parent: sub-verse401 – sub-verse415 (12 folders); each contains 2–3 split scans using IDs in the 200–275 range as the `split-verseMMM` infix.

**Split-subject detail** (parent → split IDs):

| Parent | Splits |
|---|---|
| sub-verse401 | verse201, verse253 |
| sub-verse402 | verse202, verse251 |
| sub-verse403 | verse208, verse255 |
| sub-verse405 | verse212, verse258, verse259 |
| sub-verse406 | verse214, verse261 |
| sub-verse407 | verse215, verse262 |
| sub-verse408 | verse223, verse265 |
| sub-verse409 | verse226, verse266 |
| sub-verse410 | verse227, verse267 |
| sub-verse411 | verse232, verse270 |
| sub-verse413 | verse239, verse272 |
| sub-verse415 | verse243, verse275 |

---

## File formats

### `rawdata/sub-verseNNN/sub-verseNNN_ct.json` — scan metadata

Small JSON object with scanner provenance:

```json
{
    "dataset": "VERSE  - DOI 10.17605/OSF.IO/NQJYW",
    "KVP": "120",
    "Manufacturer": "Philips",
    "ManufacturerModelName": "Brilliance 64"
}
```

**Scanner distribution across 80 scans:**

| Manufacturer | Count | Models |
|---|---|---|
| Philips | 58 | Brilliance 64 (27), iCT 256 (19), IQon Spectral CT (12) |
| Siemens | 22 | SOMATOM Definition AS+ (20), SOMATOM Definition AS (2) |

All scans acquired at 120 kVp.

### `rawdata/sub-verseNNN/sub-verseNNN_ct.nii.gz` — CT image

NIfTI 1.1, gzip-compressed. Spine CT, varying FOV and orientation. Spacing is anisotropic; resolution varies across scanners.

### `derivatives/sub-verseNNN/sub-verseNNN_seg-vert_msk.nii.gz` — segmentation mask

NIfTI label map. Integer labels identify individual vertebrae. Label convention matches the centroid JSON (see below).

### `derivatives/sub-verseNNN/sub-verseNNN_seg-subreg_ctd.json` — centroids

JSON array. First element is orientation metadata; subsequent elements are per-vertebra centroid entries:

```json
[
  {"direction": ["P", "I", "R"]},
  {"label": 20, "X": 63.4, "Y": 141.0, "Z": 31.1},
  {"label": 21, "X": 53.0, "Y": 167.7, "Z": 30.3},
  ...
]
```

- `X`, `Y`, `Z` are in **voxel coordinates** (not physical mm).
- `direction` encodes axis labels: Posterior, Inferior, Right.

**Vertebra label → anatomy mapping** (provided by dataset authors):

```python
v_dict = {
    1: 'C1', 2: 'C2', 3: 'C3', 4: 'C4', 5: 'C5', 6: 'C6', 7: 'C7',
    8: 'T1', 9: 'T2', 10: 'T3', 11: 'T4', 12: 'T5', 13: 'T6', 14: 'T7',
    15: 'T8', 16: 'T9', 17: 'T10', 18: 'T11', 19: 'T12', 20: 'L1',
    21: 'L2', 22: 'L3', 23: 'L4', 24: 'L5', 25: 'L6', 26: 'Sacrum',
    27: 'Cocc', 28: 'T13'
}
```

Label integers map directly to both the segmentation mask and the centroid JSON.

### `derivatives/sub-verseNNN/sub-verseNNN_seg-vert_snp.png` — snapshot

2-D PNG preview of the segmentation overlaid on the CT. Useful for quick visual inspection; not used programmatically.

---

## FOV coverage notes

Most subjects show only partial spine coverage. Lumbar and lower thoracic (labels ~16–24, i.e. T9–L5) are the most common FOV. Full-spine coverage (cervical through sacral) is seen in some subjects (e.g. sub-verse009: labels 9–24, sub-verse033: labels 7–24). Code must not assume any specific vertebra range is present.

---

## Role in the project

VerSe19 training data serves two purposes:

1. **Reference distribution** — extract feature distributions from verified ground-truth segmentations to calibrate QC heuristics (per vision §5.3 and §8).
2. **Positive-control test corpus** — GT segmentations should pass QC at a high rate; deviations surface false positives (vision §8, goal G3).

Synthetic failure injection (vision §8) modifies copies of these ground-truth files to create the negative-control corpus.
